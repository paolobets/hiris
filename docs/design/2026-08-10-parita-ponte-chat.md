# Parità del ponte: il percorso in abbonamento riceve il nucleo e i quattro strumenti

**Data:** 2026-08-10 · **Ramo:** `2.0` · **HEAD di riferimento:** `33bb672`
**Stato:** progetto, non implementazione. Nessuna riga di codice di produzione è stata scritta per
questo documento.

**La decisione del proprietario, che questo documento progetta:** HIRIS ha oggi due chat con due
livelli di conoscenza diversi. Il percorso sincrono conosce la casa e ha quattro strumenti; il ponte
(abbonamento Claude Max) non conosce niente e non ha niente. Si sceglie la **parità piena**: il ponte
riceve **il nucleo** e **i quattro strumenti**, così le due chat diventano la stessa chat.

**Il vincolo:** il server MCP interno è **uscito** con la fetta E2 Task 3 (`2e78354`). Non si
ripristina: si riprogetta. *Ciò che rientra, rientra rifatto e con un progetto* — e le sicurezze non
si ereditano (`CLAUDE.md:79-93`).

**Cosa è stato verificato dal vivo per scrivere questo documento** (dettaglio in §3.4): la CLI
`claude` 2.1.226 — lo stesso major pinnato nel `Dockerfile` (`@anthropic-ai/claude-code@2`) — accetta
un server MCP **stdio** e uno **HTTP con header di autenticazione**, entrambi via `--mcp-config` +
`--strict-mcp-config` + `--allowedTools`, e in entrambi i casi il modello chiama davvero lo strumento
e ne usa il risultato. E soprattutto: **con `--output-format json` il fallimento del server MCP è
invisibile** (`is_error: false`, `subtype: "success"`, nessun campo che lo dica), **con
`--output-format stream-json --verbose` è dichiarato** (`system/init` → `mcp_servers: [{"name":
"hiris", "status": "failed"}]`). Questa differenza è il perno del §3.5.

---

## 1. Come funziona oggi il ponte, per davvero

### 1.1 Il giro completo

| # | Chi | Dove | Cosa fa |
|---|-----|------|---------|
| 1 | `handle_chat` | `hiris/app/api/handlers_chat.py:151` | Legge il body, valida `message` (≤4000 char), legge `impostazioni_chat` dall'app. |
| 2 | idem | `handlers_chat.py:191-199` | Applica `max_chat_turns` **prima** del bivio: vale per entrambi i percorsi. |
| 3 | idem | `handlers_chat.py:208` | Il bivio: `if request.app.get("chat_via_subscription") and _bridge_on(request.app)`. |
| 4 | idem | `handlers_chat.py:213-227` | Due guardie **solo** sul ramo ponte: `has_pending_chat()` → 409, `count_chat_today() >= chat_daily_cap` (default 50) → 429. |
| 5 | `_enqueue_chat_job` | `handlers_chat.py:74-111` | Persiste **subito** il turno utente (`append_messages`, riga 93), rilegge la cronologia (99), la taglia (`_trim_history`, 100), compone il system prompt (101), accoda. |
| 6 | idem | `handlers_chat.py:106-110` | **Il contenuto del job**: `context = {"history": …, "system_prompt": …}`. Due chiavi. `wake` è `{}`. `deadline = now + BRIDGE_DEADLINE_MIN·60` (default 5 minuti). `kind="chat"`. |
| 7 | idem | `handlers_chat.py:111` | Risponde `202 {"status": "pending", "job_id": …}`. |
| 8 | `ReasoningQueue.enqueue` | `hiris/app/reasoning/queue.py:39-48` | Riga in `reasoning.db` (SQLite), `status='pending'`, `context_json` serializzato. |
| 9 | `run_loop` | `hiris/app/agent/runner.py:145-164` | Il worker in-addon, avviato da `server.py:1465-1477` **solo** se `should_start_agent_worker()`. Ogni `HIRIS_AGENT_POLL_SECONDS` (default 3) esegue `run_once` **in un thread executor** — il loop asyncio dell'add-on resta libero (commento a `runner.py:145-152`). |
| 10 | `run_once` | `runner.py:125-139` | `POST /api/reasoning/claim` su `http://127.0.0.1:8099` con header `X-HIRIS-Internal-Token` (`build_headers`, `runner.py:118-123`). |
| 11 | `handle_reasoning_claim` | `hiris/app/api/handlers_reasoning.py:13-17` → `queue.py:50-63` | Prende il job `pending` più vecchio non scaduto, lo marca `claimed`, genera un `nonce`. |
| 12 | `reason` → `_reason_chat` | `runner.py:91-116`, `53-89` | Se `kind != "chat"`: log e decisione **vuota**. Se `mode != "live"`: `{"reply": "[mock] risposta di prova"}`. |
| 13 | `build_chat_messages` | `hiris/app/agent/prompts.py` | Compone `system` = `system_prompt` del job + `_CHAT_TOOL_GUIDANCE`; `user` = trascrizione `"Utente: … / Assistente: …"` + `_CHAT_INSTRUCTION`. |
| 14 | `_chat_claude_args` | `runner.py:24-29` | `claude -p <user> --model <m> --system-prompt <system> --exclude-dynamic-system-prompt-sections --disallowedTools <deny locali> --permission-mode default --output-format json`. **Nessun `--mcp-config`, nessun `--allowedTools`.** |
| 15 | idem | `runner.py:63` | Il modello è `HIRIS_AGENT_CHAT_MODEL`, default `"sonnet"` — **e quella variabile non è esportata in `run.sh`**: in produzione è sempre `"sonnet"`. |
| 16 | idem | `runner.py:66-67`, `41-51` | `subprocess.run(timeout=300)` con un env ripulito: passano solo `HOME`, `PATH` e le `ANTHROPIC_*`/`CLAUDE_*` **tranne** `CLAUDE_API_KEY` e `ANTHROPIC_API_KEY` (perché l'abbonamento non deve poter ricadere sulla chiave a consumo). |
| 17 | idem | `runner.py:69-89` | rc≠0 → `{"reply": "[errore runner rc=…] …"}`. rc=0 → `json.loads(stdout)["result"]`, oppure lo stdout grezzo, oppure `"[vuoto]"`. Timeout/eseguibile assente → `{"reply": "[runner non disponibile]"}`. **Non solleva mai.** |
| 18 | `run_once` | `runner.py:136-139` | `POST /api/reasoning/submit` con `job_id`, `nonce`, `decision`. |
| 19 | `handle_reasoning_submit` | `handlers_reasoning.py:20-60` | `queue.submit` (scrive sempre `decision_json`, `status='decided'`), poi per `kind=="chat"` chiama `app["submit_chat_reply"]`. |
| 20 | `_submit_chat_reply` | `hiris/app/server.py:1190-1220` | Detokenizza con mappa vuota, scarta se `_is_toxic_assistant`, altrimenti `append_messages([{"role":"assistant",…}])`. Uno scarto qui è **silenzioso** per costruzione (non c'è più una risposta HTTP da usare). |
| 21 | `handle_chat_reply_poll` | `handlers_chat.py:114-148` | La UI interroga `GET /api/chat/reply/{job_id}`. `expired`/`failed`/`decided-senza-reply` → *«La risposta non è arrivata in tempo. Riprova.»*; altrimenti `pending` o `done` + `reply`. |
| 22 | `_reasoning_sweep` | `server.py:1295-1307` | Ogni 2 minuti marca `expired` i job scaduti e pota quelli oltre i 7 giorni. |

### 1.2 Come ci si finisce senza saperlo

`provider_subscription=true` **implica** il percorso ponte anche se `chat_via_subscription` è rimasta
`false`:

- `server.py:907` — `_sub_first_class = _active["subscription"]`, cioè il toggle `provider_subscription`
  **e** la presenza di `CLAUDE_CODE_OAUTH_TOKEN` (`model_activation.py:14-34`);
- `server.py:1332-1339` — `_bridge_enabled = env_bool("BRIDGE_ENABLED") or _sub_first_class` e
  `_chat_via_subscription_cfg = env_bool("CHAT_VIA_SUBSCRIPTION") or _sub_first_class`;
- `server.py:1340` — `app["chat_via_subscription"] = _chat_subscription_active(cfg, bridge)`, che è un
  `and` (`server.py:71-81`): con l'abbonamento attivo entrambi gli operandi sono veri.
- Simmetricamente, `should_start_agent_worker()` (`server.py:375-383`) accende il worker.

Quindi: **chi accende l'abbonamento come provider finisce sul ponte**, cioè su una chat che non
conosce la casa, senza che nulla glielo dica. È il motivo per cui questo lavoro esiste.

### 1.3 Cosa NON arriva al ponte, una per una

Le sette impostazioni di `ImpostazioniChat` (`hiris/app/impostazioni_chat.py:56-70`) e il resto del
contesto, confrontando il ramo sincrono con il ramo ponte:

| Cosa | Sul percorso sincrono | Sul ponte | Prova |
|---|---|---|---|
| `system_prompt` | sì, blocco system | **sì** (unica cosa che passa) | `handlers_chat.py:101` / `256` |
| `max_chat_turns` | sì | **sì** (controllo a monte del bivio) | `handlers_chat.py:191-199` |
| `restrict_to_home` | sì → `RESTRICT_PROMPT` | **no** | `handlers_chat.py:402`, `claude_runner.py:250-254, 616-617` |
| `response_mode` | sì → modificatore `compact`/`minimal` | **no** | `handlers_chat.py:403`, `claude_runner.py:622-628` |
| `thinking_budget` | sì → parametro `thinking` | **no** | `handlers_chat.py:404`, `claude_runner.py:673`, `180-225` |
| `model` | sì (`impostazioni.model`, risolto da `AUTO_MODEL_MAP`) | **no** — il ponte usa `HIRIS_AGENT_CHAT_MODEL`, di fatto sempre `"sonnet"` | `handlers_chat.py:366` vs `runner.py:63` + `run.sh` (variabile assente) |
| `max_tokens` | sì, `CHAT_MAX_TOKENS = 16000` | **no** — non c'è un equivalente passato alla CLI | `handlers_chat.py:401`, `claude_runner.py:154` |
| `nome` | non letto da nessuno dei due | — | — |
| **`BASE_SYSTEM_PROMPT`** (la persona HIRIS e le regole fondamentali, incluso *«non dire "preso nota" se non hai salvato»*) | sì, primo blocco system | **no** | `claude_runner.py:101-122`, `612` |
| **Il nucleo** (la casa compatta) | sì, in coda al system come `context_str` | **no** | `handlers_chat.py:317, 330-335, 425/485` |
| **Le sessioni precedenti** (`get_past_summaries`) | sì, dentro `context_str` | **no** | `handlers_chat.py:262-269, 333-334` |
| **I quattro strumenti** | sì (`STRUMENTI_CONOSCENZA` + `DispatcherConoscenza`) | **no** | `handlers_chat.py:360-364, 438-439, 493-494` |
| Cronologia | sì, come turni veri della conversazione | **sì**, ma **appiattita** in un'unica trascrizione dentro il prompt utente | `handlers_chat.py:242` vs `prompts.build_chat_messages` |
| `debug` (`tools_called`, `thinking_blocks`) | sì, nella risposta | **no** — il poll restituisce solo `reply` | `handlers_chat.py:544-547` vs `140-148` |

Il ponte oggi **dichiara** questa assenza al modello, invece di lasciarlo mentire:
`prompts._CHAT_TOOL_GUIDANCE` gli dice esplicitamente che non ha strumenti, che non deve inventare
stati e che non deve dire di aver preso nota. È la cosa giusta fatta su un guscio vuoto — e va
riscritta appena il guscio smette di essere vuoto (§6).

> **Nota di metodo.** `hiris/app/agent/prompts.py` e `tests/test_agent_runner_inaddon.py` sono in
> lavorazione da parte di un altro agente mentre questo documento viene scritto: i riferimenti a
> `prompts.py` sono per **simbolo** (`_CHAT_TOOL_GUIDANCE`, `_CHAT_INSTRUCTION`,
> `build_chat_messages`), non per riga, perché il file è cambiato fra due letture successive.

---

## 2. Cosa serve per il nucleo (la parte facile)

### 2.1 Chi lo compone oggi

Una funzione sola, condivisa da due chiamanti:

- `hiris/app/api/handlers_casa.py:97-187` — `costruisci_nucleo(app) -> (testo, riepilogo)`. Prende
  `app`, non `request` (riga 109-112: *«un chiamante che non ha una request in corso può comunque
  chiamarla»*), legge `archivio_casa`, `archivio_memoria`, `entity_cache`, e chiama:
- `hiris/app/casa/nucleo.py:427-432` — `componi(casa, comportamento, ricordi, stato, tetto=6000, …)`,
  **pura**: nessun archivio, nessuna rete.

I due chiamanti sono `handle_get_nucleo` (`GET /api/nucleo`, `handlers_casa.py:190-206`, rotta a
`server.py:1670`) e `handle_chat` (`handlers_chat.py:317`). La condivisione è deliberata e
documentata: *«la STESSA composizione, non due che potrebbero divergere»* (`handlers_casa.py:100-107`).
**Un terzo chiamante non deve ricomporlo: deve chiamare la stessa funzione, o leggerne il risultato.**

### 2.2 Dove va inserito — due innesti possibili

**Innesto A — al momento dell'accodamento (dentro l'add-on).**
`_enqueue_chat_job` (`handlers_chat.py:74-111`) ha già `request.app`. Si aggiungono due chiavi al
`context`:

```
context = {
    "history": sanitized_history,
    "system_prompt": system_prompt,
    "nucleo": nucleo_testo,                  # da costruisci_nucleo(request.app)
    "sessioni_precedenti": past_str,         # da get_past_summaries(data_dir)
}
```

Il `try/except` che oggi protegge la composizione del nucleo sul ramo sincrono
(`handlers_chat.py:316-329`, con il testo di degrado *«non è una casa vuota — è un guasto»*) va
**estratto in una funzione unica** e usato da entrambi i rami: due copie di quel testo sarebbero
esattamente la «funzione doppia» che `CLAUDE.md:71-72` vieta.

- **Pro:** nessuna chiamata di rete in più; il runner resta ignaro degli archivi; il nucleo è
  esattamente quello che l'utente vedrebbe su `/api/nucleo` in quell'istante.
- **Contro:** il nucleo viene **scritto in `reasoning.db`** (`context_json`, `queue.py:44-46`) e ci
  resta fino alla potatura a 7 giorni (`server.py:1303`). Sono i nomi delle aree, i conteggi e **i
  ricordi per intero** duplicati in un secondo file su disco. E può invecchiare fino alla `deadline`
  (5 minuti di default).

**Innesto B — al momento del claim (dentro il runner).**
`run_once` (`runner.py:125-139`) ha già un `httpx.Client` e gli header giusti: dopo il claim fa un
`GET /api/nucleo` su `http://127.0.0.1:8099` e usa `testo`.

- **Pro:** nucleo **fresco al momento del ragionamento**; niente conoscenza della casa duplicata in
  `reasoning.db`; riusa una rotta che esiste già.
- **Contro:** una chiamata HTTP in più per turno; un guasto della rotta è un secondo modo di fallire
  e va dichiarato (non può degradare a «rispondi senza casa» in silenzio); e il nucleo del ponte
  potrebbe **non coincidere** con quello che l'utente ha appena visto in UI.

**Raccomandazione:** **A**, per la ragione che vale più delle altre in questo ramo — il ponte è già
un percorso asincrono con troppi modi di fallire in silenzio, e A non ne aggiunge nessuno. Il costo
(nucleo in `reasoning.db`) va chiuso riducendo la potatura per i job `chat` risolti, non rinunciando
a A. **Da decidere dal proprietario**, perché è una scelta su dove finiscono i dati di casa.

### 2.3 Dove va nel prompt

Il ramo sincrono mette il nucleo **in coda al system**, dopo i blocchi stabili e dopo il
`cache_control` (`claude_runner.py:612-633`): `[BASE_SYSTEM_PROMPT] [system_prompt] [modificatori]
⟨breakpoint⟩ [context_str]`. Il ponte deve replicare lo **stesso ordine** dentro l'unica stringa che
passa a `--system-prompt`, perché è quell'ordine che il `BASE_SYSTEM_PROMPT` presuppone (parla degli
strumenti prima che il nucleo dica cosa c'è in casa).

Quindi `build_chat_messages` cambia firma e diventa, in sostanza:

```
build_chat_messages(system_prompt, history, *, nucleo="", sessioni="", strumenti_attivi=False)
    -> (system, user)
```

con `system` = `BASE_SYSTEM_PROMPT` + `system_prompt` + modificatori (`RESTRICT_PROMPT` se
`restrict_to_home`, la riga `compact`/`minimal` se `response_mode`) + **guida sugli strumenti,
dipendente da `strumenti_attivi`** + `## La casa` (nucleo) + `## Sessioni precedenti`.

`BASE_SYSTEM_PROMPT` e `RESTRICT_PROMPT` **non si ricopiano** in `prompts.py`: si importano da
`claude_runner.py:101` e `:250`. Sono già l'unica fonte e devono restare tale.

### 2.4 Il tetto del prompt

Non c'è un tetto complessivo sul prompt del ponte. Ci sono tre tetti separati, tutti già in vigore:

- **Il nucleo**: `componi(..., tetto=6000)` — 6000 **caratteri**, ≈1500 token, e il taglio è
  **dichiarato dentro il nucleo stesso** (`nucleo.py:23-26, 401-417`), non nascosto in un riepilogo.
  `costruisci_nucleo` non passa `tetto`, quindi vale il default.
- **La cronologia**: `_MAX_HISTORY_TOKENS = 6000` stimati (`handlers_chat.py:21, 24-39`), la stessa
  funzione per entrambi i rami.
- **L'uscita**: `CHAT_MAX_TOKENS = 16000` (`claude_runner.py:154`) vale **solo** sul ramo sincrono. La
  CLI ha il proprio default di `max_tokens` e non lo esponiamo. Non è un problema di parità del
  contesto, ma va detto: non c'è nessuna riga di codice che allinei i due tetti d'uscita.

Sommando: nucleo ~1.5k token + cronologia ~6k + `BASE_SYSTEM_PROMPT` e affini ~0.4k + (con gli
strumenti) ~1.5k di schemi = **~9-10k token di ingresso per turno**, contro i ~6k di oggi. Nessuno
dei due si avvicina alla finestra del modello. Il problema del prompt non è la dimensione: è il
costo (§5.2).

---

## 3. Cosa serve per gli strumenti (la parte vera)

### 3.1 Cosa faceva il server MCP interno uscito in E2

Ricostruito da `git show 2e78354^:hiris/app/mcp/*` — quattro file, ~264 righe.

- **`tiers.py`** (136 righe): **il terzo catalogo**. 17 `ToolDef`, ciascuno con un `Tier`
  (`READ`/`SCHEDULE`/`ACTION`) e un `hiris_tool` (il nome passato alla execute-API). Conteneva
  `get_home_status`, `get_area_entities`, `get_entity_states`, `get_history`,
  `get_automation_config`, `get_advisories`, `get_logbook`, `recall_memory`, e poi i tier
  `SCHEDULE`/`ACTION` — cioè **strumenti che agiscono**. Descrizioni proprie, divergenti da quelle
  degli altri due cataloghi.
- **`server.py`** (46 righe): costruiva un `FastMCP("HIRIS", instructions=…)` e registrava un handler
  per ogni `ToolDef`; l'`_INSTRUCTIONS` parlava di semaforo, di *«conferma su iPhone»* e di
  *«verde=eseguita, giallo=…, rosso=…»*. Trasporto: **HTTP** (`mcp.http_app()`), montato come app
  ASGI.
- **`local_client.py`** (54 righe): `LocalExecuteClient`, il ponte verso il dispatcher. **Non
  chiamava il dispatcher: faceva un `POST /api/execute` su loopback**, con
  `X-HIRIS-Internal-Token` più un `LOCAL_CHAT_HEADER` (il `local_execute_token`, segreto di processo)
  che marcava la chiamata come «chat in-addon» per esentarla dalla *denylist di lettura* pensata per
  la superficie remota.
- **`guard.py`** (28 righe): `McpGuard`, kill-switch in memoria + coda di audit da 200 voci.

Cablaggio (da `git show 2e78354 -- hiris/app/server.py`): `build_internal_mcp_server()` costruiva
client + `uvicorn.Config(host="127.0.0.1", port=INTERNAL_MCP_PORT|8199)`; `_EmbeddedMCPServer`
sovrascriveva `install_signal_handlers()` a no-op perché **uvicorn dentro l'add-on avrebbe altrimenti
dirottato i segnali di shutdown del processo**; `_run_internal_mcp()` catturava `SystemExit` perché
`uvicorn.Server.serve()` chiama `sys.exit()` se non riesce a fare bind — e quel `SystemExit`, sullo
stesso loop asyncio dell'add-on, **avrebbe ucciso HIRIS intero per una funzione opzionale**.

**Autenticazione:** nessuna sulla connessione `claude → MCP`. Il docstring del vecchio
`agent/runner.py` lo diceva: *«l'MCP interno è raggiungibile solo da 127.0.0.1 e non richiede auth
(FastMCP auth=None) → nessun bearer/JWT nella mcp-config scritta su disco»*. Il token c'era solo sul
salto successivo, MCP → `/api/execute`.

**Come lo raggiungeva il runner:** `configure_chat_mcp()` scriveva `/tmp/hiris-mcp.json` (0600) con
`{"mcpServers": {"hiris": {"type": "http", "url": "http://127.0.0.1:8199/mcp"}}}`, e
`_chat_claude_args` aggiungeva `--mcp-config <path> --strict-mcp-config --allowedTools
<_DEFAULT_CHAT_TOOLS>`, dove `_DEFAULT_CHAT_TOOLS` erano **13 nomi** `mcp__hiris__*` fra cui
`call_service`, `send_notification`, `create_task`, `save_memory`.

**Perché è stato tolto.** Il piano E2 lo dice per esteso
(`docs/superpowers/plans/2026-08-07-escono-gli-strumenti.md:89-110`): era *«il consumatore più
esterno»*, esponeva *«un terzo catalogo (17 strumenti) che raggiunge il dispatcher passando da HTTP
su /api/execute»*, e la mappa del prodotto aveva già dato il verdetto **UNIFICA** al server MCP
interno e **ESCE** al gateway esterno e al kill-switch
(`docs/design/2026-08-05-mappa-funzionalita.md:220-222`). Il proprietario aveva chiuso la questione:
*«ora MCP non è più servito a Claude, io non posso utilizzarlo dalla chat di Claude»*. Il messaggio di
commit aggiunge che kill-switch e audit *«erano già morti: nessun endpoint, nessun chiamante»*, e che
il percorso `claude --mcp-config` andava disattivato **insieme** o sarebbe rimasto «a puntare al
nulla».

**Cosa è uscito insieme, e che oggi non esiste più a HEAD** (verificato con
`grep -rn "local_execute_token|read_denylist|handlers_execute|/api/execute" hiris/app/` → **zero
occorrenze**):

- `hiris/app/api/handlers_execute.py` e la rotta `POST /api/execute` (E2 Task 4);
- `hiris/app/api/read_denylist.py`, con `LOCAL_CHAT_HEADER`;
- `app["local_execute_token"]`;
- `fastmcp` e `uvicorn` da `requirements.txt` (verificato: `hiris/requirements.txt` a HEAD non li
  contiene);
- `internal_mcp_port` da `config.yaml`, e `HIRIS_AGENT_MCP_URL` / `HIRIS_AGENT_MCP_CONFIG_PATH` /
  `HIRIS_AGENT_CHAT_TOOLS` da `run.sh`.

**Conseguenza operativa: il vecchio disegno non è ripristinabile nemmeno volendo.** Il suo unico
modo di raggiungere la logica degli strumenti era un endpoint HTTP che non esiste più.

### 3.2 Cosa NON va ereditato, e perché

La regola è del proprietario (`CLAUDE.md:79-93`): *«creiamo le strutture e poi applichiamo le
sicurezze. […] Non ereditiamo queste dalla versione precedente»*, perché le difese della `1.x`
*«sono state costruite per un altro prodotto: uno con un Brain che produceva duecento insight,
chatbot multipli e un gateway esposto verso l'esterno»*.

| Cosa | Perché **non** rientra |
|---|---|
| **`tiers.py` — il catalogo proprio** | È l'errore da cui è nata l'intera fetta E2: tre cataloghi divergenti della stessa cosa. Il catalogo è **uno**, `casa/strumenti.py::STRUMENTI_CONOSCENZA` (`casa/strumenti.py:250-252`). Il nuovo `tools/list` lo **ri-forma**, non lo ri-dichiara (§3.3). |
| **I `Tier` READ/SCHEDULE/ACTION** | Classificavano azioni. La chat 2.0 **conosce e non agisce** (`casa/strumenti.py:10-12`): non c'è niente da classificare. Un tier su quattro strumenti di sola lettura è una struttura senza contenuto. |
| **`McpGuard` — kill-switch + audit** | Era già morto quando è uscito (nessun endpoint, nessun chiamante). E proteggeva **le azioni**: uno stop d'emergenza su una superficie che non tocca la casa è teatro. Se un giorno servirà un interruttore, spegne **la chat**, non l'MCP. |
| **`LocalExecuteClient` + `/api/execute`** | Un salto HTTP verso un endpoint costruito per una superficie **remota** (il gateway esterno che *non esiste in questo repository*). Il nuovo consumatore è un sottoprocesso del nostro stesso container. |
| **La denylist di lettura + `LOCAL_CHAT_HEADER` + `local_execute_token`** | Esistevano per **distinguere il locale dal remoto**. Non c'è più un remoto da cui distinguersi: quella distinzione oggi non ha un lato. |
| **`fastmcp` + `uvicorn` + un secondo server HTTP con porta propria** | Una dipendenza nuova, una porta nuova (`INTERNAL_MCP_PORT`), un modo nuovo di non partire (bind fallito → `SystemExit` → add-on giù), e una sovrascrittura dei signal handler del processo. Tutto questo per servire quattro strumenti a un sottoprocesso che parla con noi da `127.0.0.1`. **Il disegno nuovo non ne ha bisogno** (§3.3, verificato in §3.4). |
| **L'`_INSTRUCTIONS` del vecchio server MCP** | Parlava di semaforo, conferme e *«verde/giallo/rosso»*: il semaforo è uscito (E3 Task 7), l'OTP è uscito (E2 Task 5). Sarebbero tre falsità al presente in quindici righe — il difetto ricorrente di questo prodotto. |
| **`_DEFAULT_CHAT_TOOLS` (13 nomi)** | Nominava `call_service`, `send_notification`, `create_task`, `save_memory`. **Nessuno dei quattro esiste più.** |
| **`--mcp-config` come file scritto su disco (`/tmp/hiris-mcp.json`, 0600)** | Il file esisteva perché non conteneva segreti. Il disegno nuovo **ha** un segreto nella config (§3.3), quindi il file va evitato: la CLI accetta `--mcp-config` anche come **stringa JSON** (verificato: *«Load MCP servers from JSON files or strings»*), e una stringa non resta su disco. |

### 3.3 Il disegno nuovo

**Trasporto: HTTP, servito dalla stessa `web.Application` dell'add-on.** Una rotta nuova sul listener
che c'è già (`127.0.0.1:8099`), non un server nuovo.

```
POST /api/mcp        →  adattatore JSON-RPC 2.0  →  DispatcherConoscenza.dispatch(nome, argomenti)
```

L'adattatore gestisce tre metodi e basta:

| Metodo | Risposta |
|---|---|
| `initialize` | `{protocolVersion (rimandato indietro), capabilities: {tools: {}}, serverInfo: {name: "hiris", version: <version.py>}}` |
| `tools/list` | `STRUMENTI_CONOSCENZA` ri-formato: `name`/`description` invariati, `input_schema` → `inputSchema`. **Trasformazione meccanica, nessun testo nuovo.** |
| `tools/call` | `DispatcherConoscenza(app["archivio_casa"], app["archivio_memoria"], cache=app["entity_cache"]).dispatch(name, arguments)` → `{"content": [{"type": "text", "text": json.dumps(risultato)}]}` |

Le notifiche (`notifications/initialized`, senza `id`) si accettano con `202` e nient'altro.

**Perché gli strumenti raggiungono `DispatcherConoscenza` senza duplicarne la logica.** Perché
l'handler **è dentro l'add-on** e costruisce il dispatcher dagli **stessi oggetti** che usa
`handlers_chat.py:360-364`: `archivio_casa`, `archivio_memoria`, `entity_cache`. Nessuna copia,
nessun salto HTTP verso un endpoint intermedio, nessuna riscrittura degli schemi. È lo stesso
principio già applicato al nucleo (`costruisci_nucleo` condivisa fra `/api/nucleo` e la chat): **una
composizione, non due che potrebbero divergere.** Un test deve fissarlo: l'insieme dei nomi
restituiti da `tools/list` è **identico** a `{d["name"] for d in STRUMENTI_CONOSCENZA}`.

**Perché NON un sottoprocesso stdio.** Funziona (verificato in §3.4), ma un processo separato **non
ha** gli archivi aperti dell'add-on: dovrebbe aprire una seconda connessione a `casa.db`/`memoria.db`
(un secondo scrittore su `ricorda`) e soprattutto **non avrebbe la `entity_cache`**, che vive nella
memoria del processo add-on. `guarda` risponderebbe `stato_non_letto: True` sempre
(`casa/strumenti.py:385-386, 389-414`). Sarebbe la ricreazione esatta del difetto che il nucleo esiste
per uccidere: due intelligenze nella stessa casa che ne vedono due diverse. L'unica variante sensata
di stdio è «un processo sottile che riproxa in HTTP verso l'add-on» — cioè il disegno HTTP **più** un
processo inutile.

**Autenticazione: il token interno che il runner ha già.** La rotta cade sotto
`internal_auth_middleware` (`server.py:1548-1552`, middleware globale, nessuna esenzione), che
richiede `X-HIRIS-Internal-Token` (`api/middleware_internal_auth.py:66-98`). Il runner lo compone già
(`runner.py:118-123`); la `--mcp-config` lo trasporta nel campo `headers` (verificato in §3.4).
**Nessun segreto nuovo, nessun meccanismo nuovo.** Da valutare in fase «poi le sicurezze»: un token
per-invocazione, di validità pari al turno, invece del token interno permanente — struttura prima,
irrobustimento poi.

**Ciclo di vita del processo: nessuno.** Non c'è niente da avviare, niente da fermare, nessuna porta
da occupare, nessun `SystemExit` da contenere, nessun signal handler da neutralizzare. Tutto
l'apparato `_EmbeddedMCPServer` / `_run_internal_mcp` / `internal_mcp_task` / `internal_mcp_client`
non ha un equivalente qui.

**Rientranza — la condizione che rende possibile tutto questo.** Mentre `claude` gira, il loop
asyncio dell'add-on deve poter servire la callback MCP. È già così: `run_loop` esegue `run_once`
tramite `loop.run_in_executor` **proprio** per non bloccare l'add-on durante i 300 secondi di
`subprocess.run` (`runner.py:145-152, 158-159`). Se un giorno qualcuno «semplificasse» chiamando
`run_once` direttamente nella coroutine, la chat andrebbe in **stallo circolare**: il modello chiama
lo strumento, l'HTTP non viene servito, il timeout scatta. **Va scritto un test che lo impedisca.**

### 3.4 Cosa è stato verificato dal vivo

CLI locale `claude 2.1.226` — stesso major del pin `@anthropic-ai/claude-code@2` nel `Dockerfile`.

1. **`--permission-mode default` è accettato** anche se non compare fra le scelte documentate
   (`--help` elenca `acceptEdits, auto, bypassPermissions, manual, dontAsk, plan`). L'argomento di
   `runner.py:28` non è un bug latente.
2. **Server MCP stdio scritto a mano, zero dipendenze** (~45 righe di JSON-RPC su stdin/stdout):
   `--mcp-config cfg.json --strict-mcp-config --allowedTools "mcp__hiris__guarda"` → il modello ha
   chiamato lo strumento e ha risposto col valore restituito (`21.5 °C`). **Non serve `fastmcp`.**
3. **Server MCP HTTP scritto a mano, zero dipendenze** (`http.server`, risposta
   `application/json`), configurato con
   `{"type": "http", "url": "http://127.0.0.1:8199/mcp", "headers": {"X-HIRIS-Internal-Token": "…"}}`
   → `mcp_servers: [{"name": "hiris", "status": "connected"}]`, tool chiamato, risposta corretta
   (`19.5 °C`). **Gli header di autenticazione nella `--mcp-config` funzionano.**
4. **Il nome esposto al modello è `mcp__<server>__<tool>`**, quindi `mcp__hiris__cerca`,
   `mcp__hiris__guarda`, `mcp__hiris__ricorda`, `mcp__hiris__richiama`.
5. **La CLI inserisce un passaggio `ToolSearch`** per risolvere gli schemi degli strumenti MCP
   (osservato nel flusso `stream-json`). `_LOCAL_TOOLS_DENY` (`runner.py:21`) **non** contiene
   `ToolSearch` e non deve contenerlo, o gli strumenti diventano irraggiungibili. Serve un test che
   lo fissi, perché quella stringa è esattamente il genere di cosa che qualcuno «completa».
6. **Il fallimento del server MCP è INVISIBILE con `--output-format json`.** Config puntata a un
   comando inesistente: la CLI ha risposto `is_error: false`, `subtype: "success"`, e **nessun campo**
   del JSON dice che gli strumenti non c'erano. Solo il testo del modello lo ammetteva — per fortuna,
   non per contratto.
7. **È DICHIARATO con `--output-format stream-json --verbose`**: l'evento `{"type": "system",
   "subtype": "init"}` porta `mcp_servers: [{"name": "hiris", "status": "connected"|"failed"}]` **e**
   la lista `tools` risolta (con o senza i `mcp__hiris__*`). Arriva **prima** del primo token del
   modello. L'evento finale `{"type": "result"}` porta lo stesso `result` di oggi.
8. **Non esiste una sonda di salute a parte**: `claude mcp list --mcp-config …` →
   `error: unknown option '--mcp-config'`.

### 3.5 Cosa succede se il server MCP non parte — degradare **dichiarando**

Il difetto numero uno di questo prodotto è il silenzio: *«un silenzio non dichiarato è
indistinguibile da un'assenza di problemi»* (`handlers_chat.py:295-297`). Il §3.4/6 dice che la forma
attuale dell'invocazione **rende quel silenzio la condizione di default**. Tre difese, in ordine di
costo:

**① Sonda in-processo, prima di invocare la CLI (obbligatoria).**
Prima di lanciare `claude`, il runner fa un `POST /api/mcp` con `{"method": "tools/list"}` sul suo
`httpx.Client` (la stessa connessione loopback, gli stessi header, ~1 ms, zero token). Se la risposta
non contiene i quattro nomi attesi: **non si passa `--mcp-config`**, si invoca con la guida «senza
strumenti» già esistente (`_CHAT_TOOL_GUIDANCE`, che continua a servire), e **si scrive un avviso
nella `reply`** — non solo in un log che nessuno legge.

**② Lettura dell'evento `init` (obbligatoria).**
Serve comunque, perché la sonda dice che *l'add-on* sta bene, non che *la CLI ci è arrivata*. Si passa
a `--output-format stream-json --verbose`, si legge il primo evento `system/init` e si verifica
`mcp_servers[*].status == "connected"` **e** la presenza dei quattro `mcp__hiris__*` in `tools`. Se
non tornano: si termina il sottoprocesso e si ri-invoca **una volta** senza `--mcp-config`, con la
guida «senza strumenti». Costo: una invocazione sprecata, solo quando il guasto c'è davvero.

**③ Il testo che l'utente legge.**
In entrambi i casi la risposta è preceduta da una riga esplicita, nello stile già adottato per il
nucleo che non si compone (`handlers_chat.py:320-329`): *«In questo turno non ho potuto usare gli
strumenti per guardare la casa: rispondo con ciò che so dal nucleo e dalla conversazione»*. Non un
`[errore runner]` criptico, e **mai** una risposta che sembra normale.

**Il prezzo di ② va detto in chiaro:** cambiare `--output-format` da `json` a `stream-json` cambia il
parsing di **ogni** risposta del ponte, inclusi i rami d'errore (`runner.py:69-89`). È il pezzo più
rischioso di tutto il lavoro, ed è il motivo principale per cui il §6 propone di separarlo dal
nucleo.

---

## 4. Le alternative scartate

### 4.1 Si può avere la parità senza MCP?

**Per il nucleo: sì, e non serve nemmeno discuterne** — è testo, va nel `--system-prompt` (§2).

**Per gli strumenti: no, non con lo stesso risultato.** Tre vie esaminate.

**(a) Il ponte chiama gli strumenti dal lato Python *prima* di invocare la CLI.**
Cioè: HIRIS indovina quali strumenti servirebbero, li esegue, e infila i risultati nel prompt.
Scartata perché **non è ciò che gli strumenti fanno**. `cerca` esiste perché il modello deve poter
disambiguare («due *Bagno* su piani diversi», `casa/strumenti.py:62-78`); `guarda` esiste perché il
modello sceglie **cosa** guardare **dopo** aver visto i candidati; `richiama` dipende da un
`riferimento` che solo un turno precedente può aver prodotto. Precalcolare significa sostituire la
scelta del modello con un'euristica nostra — cioè costruire un quinto pezzo di logica che oggi non
esiste, per ottenere un risultato peggiore. E `ricorda` **non è precalcolabile per definizione**:
dipende da cosa l'utente ha appena detto e da come il modello lo interpreta.

**(b) Giro a due passaggi: prima invocazione «di cosa hai bisogno?», poi esecuzione, poi seconda
invocazione.**
Tecnicamente funziona senza MCP. Scartata perché: raddoppia le invocazioni (e il ponte è l'opzione
economica); non supporta l'**incatenamento** vero (`cerca` → `guarda` → `richiama` è più di un giro,
`MAX_TOOL_ITERATIONS = 10` sul ramo sincrono, `claude_runner.py:155`); costringe il modello a
produrre un blocco JSON che noi dobbiamo interpretare — **esattamente il `parse_decision` uscito
alla fetta E4 Task 8**, che questo ramo ha cancellato per motivi che non sono cambiati; e ogni
passaggio è un nuovo modo di fallire in silenzio.

**(c) Usare l'SDK/`--input-format stream-json` invece di `-p`, e gestire i tool a mano.**
Sposterebbe il problema dal protocollo MCP al protocollo dei messaggi, riscrivendo l'intero
`_reason_chat`. Più codice nostro, non meno. Ma **è la via giusta se un domani si vorrà la vera
cronologia a turni** invece della trascrizione appiattita: va segnata come possibile evoluzione, non
come alternativa a questo lavoro.

**(d) Il vecchio disegno: MCP + un endpoint HTTP intermedio.**
Scartata: l'endpoint (`/api/execute`) non esiste più, e ricrearlo significherebbe rimettere in piedi
un salto pensato per un consumatore remoto che non esiste.

**Conclusione onesta.** MCP non è un'aggiunta architetturale: è **il solo modo in cui la CLI `claude`
accetta strumenti nostri**. E nel disegno del §3.3 «adottare MCP» costa un adattatore JSON-RPC di
tre metodi su una rotta aiohttp — meno codice di qualunque alternativa, senza dipendenze nuove
(verificato dal vivo, §3.4/2-3), e senza processi da governare. **La via più semplice è quella con
MCP.**

### 4.2 Altre scelte scartate dentro il disegno

- **Rimettere `fastmcp`** — verificato che non serve; una dipendenza in meno è un aggiornamento in
  meno da inseguire, e il repo l'ha appena tolta.
- **Un secondo listener con porta propria** — reintrodurrebbe `INTERNAL_MCP_PORT`, il bind fallibile
  e il contenimento del `SystemExit`. Non c'è nulla che una porta separata dia in cambio.
- **`--mcp-config` come file su disco** — il vecchio disegno lo faceva perché la config era senza
  segreti; la nostra ha il token interno. Si passa la stringa JSON.
- **`mode=mock` come degrado quando MCP fallisce** — sarebbe una risposta finta presentata come vera.
  Il mock resta legato a `HIRIS_AGENT_MODE`, ed è già dichiarato nel testo (`"[mock] …"`).

---

## 5. I rischi

### 5.1 Cosa vede il modello che prima non vedeva

Sul ponte, il modello passa da «la trascrizione e nient'altro» a:

- la mappa della casa (piani, aree, conteggi per dominio), le automazioni e gli script conosciuti,
  «cosa è notevole adesso» — cioè quali entità sono in uno stato degno di nota **in questo momento**;
- **i ricordi per intero**: il nucleo non li riassume (`casa/nucleo.py:14-16`, *«Entrano interi»*).
  Sono frasi dette da persone in casa;
- e, con gli strumenti, la possibilità di **leggere a richiesta** qualunque area, entità,
  dispositivo, automazione (col corpo, quando lo conosciamo) o ricordo.

Sul percorso sincrono tutto questo va all'API Anthropic sotto la chiave a consumo dell'utente. Sul
ponte va agli stessi modelli **attraverso la CLI, sotto l'abbonamento**. È lo stesso destinatario ma
non necessariamente le stesse condizioni d'uso e di conservazione. **Il codice non può rispondere a
questo: è una domanda per il proprietario** (§8, domanda aperta 4). Va scritto nella pagina delle
impostazioni prima che l'utente accenda l'abbonamento, non dopo.

### 5.2 Il costo — e il ponte è l'opzione «economica»

Per turno, in ingresso, si aggiungono: il nucleo (≤6000 caratteri, ~1.5k token), gli schemi dei
quattro strumenti (le descrizioni di `casa/strumenti.py` sono deliberatamente lunghe: ~4-5k
caratteri complessivi, ~1.3k token), `BASE_SYSTEM_PROMPT` e i modificatori (~0.4k token). Circa
**+3k token fissi per turno**, più **i giri di tool**: ogni `cerca`→`guarda` è un turno di modello in
più.

Tre precisazioni che cambiano il senso del numero:

1. **Sull'abbonamento non si spendono dollari, si spendono limiti.** Il tetto vero sono le finestre
   di utilizzo del piano Max. L'unico freno esistente è `chat_daily_cap` (default 50,
   `server.py:1226`, `config.yaml`), che conta i **turni accodati**, non i token né i giri di tool. Un
   turno con cinque chiamate di strumento consuma come cinque, e il contatore ne vede uno.
2. **La cache del prompt non è nostra da controllare.** Sul ramo sincrono i blocchi stabili hanno
   `cache_control` espliciti (`claude_runner.py:629-631, 652-654`), quindi il prefisso fisso si paga
   una volta. Sul ponte ogni `claude -p` è una sessione nuova e la politica di cache è della CLI.
   Nelle prove il `cache_read_input_tokens` era > 0 anche fra invocazioni distinte, quindi qualcosa si
   riusa — ma **non è un contratto su cui costruire una stima** (§8, domanda aperta 2).
3. **Il costo cresce con la casa**, non col traffico: una casa grande produce un nucleo al tetto e
   più giri di `cerca`.

**Mitigazione minima da mettere nella fetta B:** contare i giri, non solo i turni — un tetto per
turno analogo a `MAX_TOOL_ITERATIONS`, e il conteggio esposto dove l'utente lo vede.

### 5.3 `ricorda` diventa scrivibile anche dal ponte

Oggi un turno del ponte può produrre solo testo: `_submit_chat_reply` scrive una riga in
`chat_store`, e nient'altro. Dopo questo lavoro, **un turno del ponte può scrivere in `memoria.db`**
(`DispatcherConoscenza._ricorda`, `casa/strumenti.py:418-461`) e quella scrittura **entra nel nucleo
di ogni turno successivo, su entrambi i percorsi**. È il primo effetto duraturo che il ponte è in
grado di produrre. Non è un difetto — è il punto — ma cambia la classe del rischio, ed è ciò che
rende grave il §5.4.

Nota su ciò che c'è già di buono e va conservato: `_ricorda` **non** accetta ancore inventate (il
cancello di `memoria/interpretazione.valida`, `casa/strumenti.py:443-453`) e dichiara gli scarti in
`problemi`. È un filtro sulla **forma** dell'interpretazione, non sul **testo**: `testo` si salva
sempre, per intero e senza riscritture (per progetto, `casa/strumenti.py:140-142`).

### 5.4 L'anti prompt-injection è irraggiungibile — e dagli strumenti passa da lì

**Il fatto, verificato.** `hiris/app/proxy/_sanitize.py` (85 righe, `sanitize_text` /
`sanitize_ha_value`) **non ha nessun chiamante di produzione**. `grep -rn "_sanitize|sanitize_text|
sanitize_ha_value" --include=*.py .` restituisce: i **test** (`tests/test_sanitize.py`,
`tests/test_sanitize_text.py`), le definizioni nel file stesso, e **un commento** —
`claude_runner.py:405`, che lo ammette per iscritto: *«va alla fase "poi le sicurezze" insieme a
proxy/_sanitize.py»*.

**Cosa vuol dire in pratica, oggi, già senza questo lavoro.** I nomi amichevoli delle entità e delle
aree, gli stati, e il testo dei ricordi arrivano al modello **non filtrati**, su **entrambi** i
percorsi. Chiunque possa scrivere un nome in Home Assistant — o far entrare un testo in `memoria.db`
— può scrivere istruzioni che il modello legge come tali. Il nucleo, che è l'unica rappresentazione
della casa, li porta **in ogni turno**.

**Perché questo lavoro lo aggrava.** Con `ricorda` disponibile anche dal ponte, il giro si chiude:
un'iniezione in un nome HA induce il modello a chiamare `ricorda` con un testo scelto
dall'attaccante → quel testo entra in `memoria.db` → il nucleo lo ripropone **a ogni turno
successivo, su entrambe le chat**. **L'iniezione diventa permanente.** Oggi la stessa catena esiste
già sul percorso sincrono: questo lavoro non la crea, **raddoppia le porte** e la porta su un
percorso dove non c'è nemmeno il `debug.tools_called` a mostrare cosa è stato scritto
(`handlers_chat.py:544-547` esiste solo sul ramo sincrono).

**Va detto al proprietario in questi termini: dare gli strumenti al ponte significa dare anche
questo.**

**Dove va chiuso** (fase «poi le sicurezze», non qui — ma il posto va deciso ora):

1. **All'ingresso, non all'uscita.** Il testo che viene da Home Assistant va filtrato quando **entra
   nella rappresentazione di HIRIS**: `proxy/entity_cache.py` e `casa/archivio.py`/`casa/anagrafe.py`
   quando l'anagrafe viene letta. Filtrare in `nucleo.componi()` coprirebbe il nucleo ma **non** le
   risposte di `cerca`/`guarda`, che portano gli stessi nomi al modello per un'altra strada.
2. **In scrittura, su `_ricorda`.** Il `testo` di un ricordo non va riscritto (è un contratto,
   `casa/strumenti.py:140-142`) — ma i **marcatori di iniezione** non sono il testo di nessuno: si
   neutralizzano al salvataggio, e lo si **dichiara** in `problemi`, la chiave che quel percorso
   già usa per dire cosa ha scartato e perché.
3. **Non nel runner e non in `prompts.py`.** Un filtro lì coprirebbe una porta su due, ed è
   esattamente il genere di difesa a metà che questo ramo sta smontando.

Va aperta una fetta a sé, con il suo progetto. **Questo documento la nomina; non la contiene.**

### 5.5 Rischi minori, ma da tenere in conto

- **La cronologia del ponte è una trascrizione, non turni veri.** Con gli strumenti, il modello vedrà
  i propri `tool_use` di **questo** turno ma non quelli dei turni precedenti (la trascrizione riporta
  solo il testo). Può quindi rifare la stessa `cerca` a ogni turno. Costo, non correttezza.
- **`internal_token` vuoto.** Il middleware è globale e non ha esenzioni: con `internal_token: ""` e
  senza `HIRIS_ALLOW_NO_TOKEN=1`, **anche `/api/reasoning/claim` risponde 401 oggi**, il ponte non
  claima mai, e la chat resta in `pending` fino alla scadenza. `config.yaml:136` dichiara
  `internal_token: password` (senza `?`, quindi obbligatorio), ma `config.yaml:66` ha come default
  `""`. Non verificato dal vivo (§8, domanda aperta 3). La rotta MCP **eredita esattamente questo
  comportamento**: non lo peggiora, ma lo rende più visibile.
- **`agent/runner.py::main()`** (righe 166-183) è un entrypoint standalone che nessuno invoca: `run.sh`
  esegue solo `python3 -m app.main`, e l'add-on usa `run_loop` (`server.py:1468`). Non è un rischio di
  questo lavoro; è codice orfano notato durante la ricognizione, da valutare nella review di ramo.
- **`--exclude-dynamic-system-prompt-sections`** (`runner.py:27`) è, per la sua stessa
  documentazione, **ignorato quando si usa `--system-prompt`**. È già inerte oggi.

---

## 6. Una proposta di sequenza

### Opzione 1 — Due fette

**Fetta A — «il ponte riceve il nucleo».**
Tocca: `handlers_chat._enqueue_chat_job` (nucleo + sessioni precedenti nel `context`, con il
`try/except` di degrado **estratto e condiviso** col ramo sincrono), `agent/prompts.py`
(`build_chat_messages` ricomposta nell'ordine di `claude_runner.py:612-633`, con `BASE_SYSTEM_PROMPT`
e `RESTRICT_PROMPT` **importati**, non ricopiati; `_CHAT_TOOL_GUIDANCE` riscritta da «non sai niente e
non hai strumenti» a «conosci la casa dal nucleo, ma in questa conversazione non hai strumenti per
leggere lo stato vivo»), `agent/runner._reason_chat` (legge le nuove chiavi del contesto e passa le
impostazioni). Più: `restrict_to_home`, `response_mode`, e `impostazioni.model` al posto di
`HIRIS_AGENT_CHAT_MODEL`.

Non tocca: il trasporto, le rotte, i flag della CLI, il parsing dell'output.

**Verificabile e pubblicabile da sola**: si accende l'abbonamento, si chiede *«quante luci ho in
cucina?»* e si guarda se risponde. Chiude la metà più visibile del divario.

**Fetta B — «il ponte riceve gli strumenti».**
Rotta `POST /api/mcp` + adattatore JSON-RPC + ri-formatura di `STRUMENTI_CONOSCENZA` +
`--mcp-config`/`--strict-mcp-config`/`--allowedTools` + **passaggio a `--output-format stream-json`**
+ sonda + lettura dell'evento `init` + degrado dichiarato + test (incluso quello che vieta di
chiamare `run_once` fuori dall'executor, e quello che fissa `tools/list == STRUMENTI_CONOSCENZA`).

**Costi di questa opzione:**
- Il prompt del ponte si scrive **due volte** — e `prompts.py` documenta da solo di essere già stato
  sbagliato due volte, con affermazioni false al presente. È il rischio serio del taglio in due.
  **Si neutralizza così:** in A si scrive `build_chat_messages(..., strumenti_attivi: bool)` con
  **entrambi** i rami del testo già dentro; A passa `False`, B passa `True`. La composizione si
  scrive una volta sola, B cambia un argomento. Con questo accorgimento il costo del taglio scende
  quasi a zero.
- Fra A e B esiste uno stato intermedio pubblicabile ma imperfetto: il modello conosce la casa e non
  può leggerne un valore corrente. È dichiarato, quindi accettabile — ma è un giro di feedback in cui
  qualcuno dirà «sa tutto ma non sa che temperatura fa».

### Opzione 2 — Una fetta sola

**Costi:** il cambio di `--output-format` da `json` a `stream-json` riscrive il parsing di **ogni**
risposta del ponte, compresi i rami d'errore (`runner.py:69-89`). Se sbaglia, il ponte risponde
`[vuoto]` o `[errore runner]` a tutto — **e non si può distinguere se ha sbagliato il nucleo o il
parsing**, perché sono nella stessa release. Il ponte è già il percorso con la diagnosi più povera
(nessun `debug`, solo un `reply` dopo un poll): unire i due cambiamenti toglie l'unica cosa che rende
diagnosticabile una release, cioè la separazione.

**Guadagni:** una sola riscrittura del prompt; un solo giro di verifica dal vivo; il proprietario ha
il risultato pieno subito, invece di uno stato intermedio spiegabile ma insoddisfacente.

### Cosa raccomanda questo documento

**L'opzione 1, con la composizione del prompt scritta una volta sola in A.** Non per prudenza
generica, ma per una ragione specifica di questo codice: **A e B falliscono in modi diversi e in
posti diversi.** Un nucleo sbagliato si vede leggendo la risposta; un `stream-json` sbagliato si vede
solo confrontando due formati di output su un percorso che non ha pannello di debug. Separarle
significa che, quando qualcosa non va, si sa già dove guardare.

**La decisione resta del proprietario**, e il costo dell'opzione 2 è reale e non enorme: chi
preferisce un solo giro di rilascio non sta scegliendo male, sta scegliendo di pagare la diagnosi.

**Stima onesta dell'ordine di grandezza** (fette di questo ramo, non giornate d'ufficio): A è una
fetta piccola — quattro file, nessuna struttura nuova. B è una fetta media — un modulo nuovo, una
rotta nuova, un cambio di formato d'uscita, e una verifica dal vivo che **deve** girare sull'add-on
vero, perché nulla di ciò che riguarda MCP si può dichiarare funzionante da una suite verde.

---

## 7. Cosa NON entra in questo lavoro

- **Nessuna azione.** Gli strumenti restano **quattro**. Niente `call_service`, `send_notification`,
  `create_task`, `toggle_automation`. *HIRIS conosce e non agisce* (`casa/strumenti.py:10-12`).
- **Nessun secondo catalogo.** `tools/list` **ri-forma** `STRUMENTI_CONOSCENZA`; non lo ridichiara.
  Un test lo fissa.
- **Nessun `Tier`, nessun semaforo, nessun kill-switch, nessun audit MCP.** Sono usciti e non
  rientrano (§3.2).
- **Nessuna superficie remota.** Niente gateway esterno, niente port mapping, niente esposizione
  fuori da `127.0.0.1`. Nessuna opzione `Network` nuova.
- **Nessuna dipendenza nuova.** Niente `fastmcp`, niente `uvicorn`, niente porta nuova.
- **Nessun ripristino di `/api/execute` o della denylist di lettura.**
- **La chiusura del buco anti-injection non è qui** (§5.4). Va nominata, tracciata, e fatta nella
  fase «poi le sicurezze» — con il suo progetto, perché riguarda **entrambi** i percorsi e non solo
  il ponte.
- **Nessun ripristino della pseudonimizzazione** (inerte per intero, `claude_runner.py:394-408`):
  stesso debito, stessa fase.
- **Nessuna cronologia a turni veri sul ponte** (`--input-format stream-json`): resta la trascrizione
  appiattita. Segnata come evoluzione possibile (§4.1c), non come obiettivo.
- **Nessun frontend.** Il pannello di debug del ponte, l'indicatore «sto usando l'abbonamento» e la
  visibilità di `provider_subscription → chat_via_subscription` appartengono alla E5.
- **Nessuna revisione dell'implicazione `provider_subscription` → ponte** (§1.2): è un difetto vero e
  va chiuso, ma **rendendola visibile all'utente**, che è un lavoro di configurazione e di interfaccia,
  non di parità. Domanda aperta 6.
- **Nessuna pulizia di `agent/runner.py::main()`** né di `--exclude-dynamic-system-prompt-sections`
  (§5.5): notati, non in perimetro.

---

## 8. Domande aperte

1. **La CLI dentro il container si comporta come quella verificata?** Tutte le prove del §3.4 sono su
   `claude 2.1.226` su Windows. Il `Dockerfile` pinna `@anthropic-ai/claude-code@2` su Alpine e
   installa **l'ultima 2.x al momento della build**. Va riverificato **sull'add-on vero** che
   `system/init` porti `mcp_servers` e che `--mcp-config` accetti una stringa JSON con `headers`.
   *Nessuna suite verde può rispondere a questa domanda.*
2. **La cache del prompt fra invocazioni `claude -p` separate.** Non è sotto il nostro controllo e non
   è documentata come contratto. Se il prefisso fisso (nucleo + schemi) **non** viene riusato, il costo
   del §5.2 è quello pieno a ogni turno. Da misurare sull'add-on leggendo
   `usage.cache_read_input_tokens` nell'evento `result`.
3. **`internal_token` vuoto è uno stato raggiungibile?** `config.yaml:136` lo dichiara obbligatorio
   (`password` senza `?`) ma `config.yaml:66` lo default a `""`. Se è raggiungibile, **il ponte è già
   rotto oggi in silenzio** (§5.5) e va chiuso prima, non dopo.
4. **Le condizioni d'uso dei dati di casa via abbonamento vs via API.** Domanda di prodotto, non di
   codice. Va risposta prima di pubblicare, perché determina cosa scrivere accanto all'interruttore.
5. **Il ponte deve restituire il `debug` (`tools_called`) come il ramo sincrono?** Oggi il poll
   restituisce solo `reply` (`handlers_chat.py:140-148`). Con gli strumenti attivi, sapere *cosa* ha
   chiamato il modello è ciò che rende diagnosticabile una risposta sbagliata — e, dato il §5.4, è
   anche ciò che rende visibile una scrittura in memoria che non doveva avvenire. Decisione del
   proprietario: è superficie nuova.
6. **`provider_subscription` che implica il ponte senza dirlo** (§1.2): si chiude in questo lavoro o
   in una fetta di configurazione a sé? Il proprietario l'ha nominato, ma non è parità.
7. **La potatura di `reasoning.db`** (7 giorni, `server.py:1303`) va accorciata per i job `chat` già
   risolti, se si adotta l'innesto A del §2.2? Con quel disegno il nucleo — ricordi inclusi — resta su
   disco in un secondo file per una settimana.
