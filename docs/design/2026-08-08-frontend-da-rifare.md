# Frontend da rifare — l'elenco per la fetta E5

Prodotto dal Task 15 della fetta E3 («Esce la casa vecchia»), che **non tocca `static/`**: qui si
elenca e si verifica, non si ripara e non si nasconde (vincolo esplicito del brief).

## Metodo

Ogni `fetch(...)`/`api(...)` che compare in `hiris/app/static/` è stato estratto con un grep mirato
e confrontato con la tabella di routing viva, cioè l'elenco reale delle `app.router.add_*` in
`hiris/app/server.py` **a HEAD di questa fetta** (35 rotte):

> **Correzione del Task 9 della fetta E4 (fix round 1), verificata col comando e non a memoria:**
> il numero giusto è **36**, non 35 — `git show 64e4457:hiris/app/server.py | grep "app.router.add_"`
> dà **37** righe, di cui una `add_static`. L'elenco puntato qui sotto è corretto e completo; è solo
> il totale a essere sbagliato di uno. Lasciata la riga originale per non riscrivere il verbale di
> un altro task.

```
/  /config  /api/health  /api/status  /api/config  /api/usage  /api/usage/reset
/api/chat  /api/chat/reply/{job_id}
/api/chatbots  /api/chatbots/{agent_id}[/run|/usage|/usage/reset|/chat-history]
/api/entities
/api/models  /api/models/config
/api/knowledge/pending  /api/knowledge/{id}/approve  /api/knowledge/{id}/reject  /api/knowledge
/api/history/policy
/api/reasoning/claim  /api/reasoning/submit
/api/casa  /api/memoria  /api/memoria/{id}  /api/nucleo
```

Ogni endpoint chiamato dal frontend che **non** compare in questa lista risponde 404. Nessuna delle
pagine sotto mostra un errore visibile per questo: sono tutte scritte per degradare in silenzio
(`.catch(() => [])`, `r.ok ? r.json() : []`, badge che restano a `—`), che è esattamente la causa
per cui il censimento del prodotto non le vede da solo — **il frontend non viene analizzato**
(limite dichiarato dello strumento).

Verificato anche il rovescio: gli endpoint frontend **ancora vivi** (`/api/chatbots*`,
`/api/entities`, `/api/models*`, `/api/usage*`, `/api/knowledge*`, `/api/history/policy`,
`/api/casa`, `/api/config`, `/api/health`, `/api/chat*`) hanno tutti almeno un chiamante nello
`static/` — nessuna rotta viva orfana dal lato frontend.

## Tabella

| # | Pagina / pezzo | File JS | Endpoint morti chiamati | Uscito con | Come si rompe |
|---|---|---|---|---|---|
| 1 | Dashboard `#/` — zona 3 "Azioni" (ragionamenti, segnalazioni, proposte) | `config/dashboard.js` (righe 180, 206, 259, 294), `config/main.js` (righe 107, 116, 127) | `/api/brain/feed`, `/api/brain/advisories*`, `/api/proposals*`, `/api/tasks*` | Task 5 (brain/feed), Task 6 (brain/advisories), Task 9 (tasks), Task 10 (proposals) | I tre pannelli e i tre badge di navigazione (`nav-adv-count`, `nav-proposals-count`, `nav-tasks-count`, e i badge inline di `main.js:107,116,127`) restano vuoti/a `—`: ogni `fetch` fallisce ma il codice degrada su array/oggetto vuoto, nessun `alert`/errore mostrato. |
| 2 | `#/tasks` (pagina intera) | `config/tasks-route.js` (righe 29, 33, 92) | `/api/tasks*` | Task 9 | La lista task è sempre vuota (`.catch(() => [])`); il pulsante di cancellazione (riga 33) fallisce silenziosamente allo stesso modo. |
| 2b | Pannello Task della chat + voce nav | `chat/tasks.js` (righe 30, 54), voce `#nav-tasks` in `index.html:76` | `/api/tasks*` | Task 9 | Stesso pannello che in `1.x` mostrava i task pendenti: oggi il fetch iniziale (riga 30) fallisce, il pannello resta vuoto senza errore. |
| 3 | `#/proposals` (pagina intera, tab In attesa/Archivio) | `config/proposals-route.js` (righe 19, 20), `config/proposals-core.js` (righe 71, 78, 84, 96, 106), `config/proposals.js` (workflow legacy, non più montato da nessuna route ma ancora `<script src>` in `config.html:205`) | `/api/proposals*`, `/api/dashboards/*` | Task 10 | Entrambi i tab restano vuoti (`{proposals:[]}` di fallback); Applica/Rifiuta e il ripristino plance da `dashboard_backups.json` (`api/dashboards/backups`, `api/dashboards/{path}/restore`) rispondono 404 mostrato come "Errore" solo se l'utente clicca un'azione — l'elenco iniziale non segnala nulla. |
| 3b | Pannello Proposte della chat + voce nav | `chat/proposals.js` (usa `HirisProposalsCore`, quindi transitivamente `/api/proposals*`), voce `#nav-proposals` in `index.html:83` | `/api/proposals*` | Task 10 | Stesso fallback silenzioso di 3, lato chat. |
| 4 | `#/agentbots` (lista) + editor Agentbot | `config/agentbot-route.js` (righe 121, 173, 348, 409, 427, 459, 491), `config/agentbot-editor.js` (righe 183, 500, 803, 827) | `/api/agentbots*`, `/api/sentinel/policy`, `/api/sentinel/timeline`, `/api/suggestions*` | Task 3 (agentbots), Task 7 (sentinel/policy, sentinel/timeline — il semaforo), Task 5 (suggestions) | La pagina non ha più nessuna via di ingresso dalla sidebar (vedi sotto), ma resta raggiungibile via URL diretto: lista sempre vuota, editor non salva/carica, timeline e suggerimenti muti. `api('api/entities?...')` (riga 173) resta vivo — solo il resto della pagina è morto. |
| 4b | Voce di navigazione Agentbots | `config.html:106` (`<a class="nav-item" href="#/agentbots" data-route="agentbots">`) | — | Task 3 | **Non elencata nel brief**, trovata durante la verifica: la sidebar del Designer ha ancora una voce "Agentbots" che porta a una pagina i cui dati sono tutti morti (vedi riga 4). |
| 5 | `#/gateway` (pagina intera) | `config/gateway-route.js` (righe 67, 192, 214, 337, 357 — tutte passano dal wrapper `api()` a riga 61, che prependa `api/gateway`) | `/api/gateway/pending`, `/api/gateway/pending/{id}/{verb}`, `/api/gateway/policy` | Task 7 | L'intera pagina "Accessi Gateway" (coda approvazioni + policy) è vuota/non salvabile. Nota: `gateway-route.js:5` nomina ancora `HA_NOTIFY_SERVICE`, opzione uscita al Task 13 — commento morto oltre a rotta morta. |
| 6a | Editor Chatbot — riquadro «Autonomia» | `config/chatbot-editor.js:382` | `/api/gateway/autonomy-summary` | Task 7 | Il riquadro non mostra mai un riepilogo di autonomia (era il residuo diretto del semaforo). |
| 6b | Editor Chatbot — riquadro «Context preview» | `config/logs.js:48` (montato da `chatbot-editor.js`) | `/api/chatbots/{id}/context-preview` | Task 2 (fetta E3) | 404 muto, dichiarato già dal report del Task 2: "il pannello ora riceve 404 e la pagina lo mostra vuoto senza errore visibile". |
| 7 | Wizard di creazione — ramo Agentbot | `config/create-wizard.js:730` (`POST api/agentbots` quando `state.type === 'agentbot'`) | `/api/agentbots` | Task 3 | Il quarto step del wizard, se l'utente sceglie "Agentbot" invece di "Chatbot", fallisce alla creazione: `errorEl` mostra l'errore HTTP (unico caso della lista con un errore visibile, perché qui il codice testa esplicitamente `r.ok`). |
| 8 | Catalogo a checkbox del Designer (creazione/editor Chatbot) | `config/templates.js` (righe 71 `send_notification`, 88 `create_automation_proposal`, e le altre voci dei 34 strumenti ex-catalogo) | — (non è un `fetch`, è una lista statica di nomi-tool offerti come checkbox) | Task 8 della fetta **E2** ("escono i trentaquattro") | Le checkbox restano nell'editor Chatbot e sono persistibili (`Chatbot.allowed_tools`), ma **nessun runner filtra più per nome** (rimosso Task 9 di questa fetta): selezionarle o no non ha alcun effetto sul comportamento in chat. Non è una rotta 404, è una configurazione inerte — stessa famiglia di difetto, forma diversa. |

## Non rotte (verificato, non toccare in E5)

- **Chat** (`index.html` + `chat/*.js` tranne `chat/tasks.js` e `chat/proposals.js` sopra): `/api/chat`,
  `/api/chat/reply/{job_id}`, `/api/chatbots*`, `/api/knowledge*` — tutte vive.
- **`#/models`**, **`#/usage`**, **`#/history`**: `/api/models*`, `/api/usage*`, `/api/history/policy`
  — tutte vive.
- **`#/chatbots`** (lista + editor), meno i due riquadri della riga 6: `/api/chatbots*` vivo.
- **Pannello Conoscenza** (`chat/knowledge.js`, `chat/knowledge-core.js`): `/api/knowledge*` resta
  (Decisione 2 del brief — `knowledge_store` non esce con questa fetta).
- **Entity-picker** (`config/entity-picker.js`): `/api/entities` resta.

## Riepilogo per chi pianificherà la E5

Sette pagine/pannelli rotti dal brief (voci 1-7), più due trovati durante la verifica di questo
task (4b: la voce di sidebar Agentbots resta linkata a una pagina morta; 8: il catalogo a checkbox
di `templates.js` non è una rotta rotta ma una configurazione senza più effetto). In totale, 14 file
JS coinvolti: `dashboard.js`, `main.js`, `tasks-route.js`, `chat/tasks.js`, `proposals-route.js`,
`proposals-core.js`, `proposals.js`, `chat/proposals.js`, `agentbot-route.js`, `agentbot-editor.js`,
`gateway-route.js`, `chatbot-editor.js`, `logs.js`, `create-wizard.js`, più le due voci di sidebar
(`config.html:106` per Agentbots, le voci nav di `index.html:76,83` per Task/Proposte) e il catalogo
di `templates.js`. Nessuno di questi file è stato toccato da questo task.

---

# Aggiunte della fetta E4 — «Un bot solo»

Prodotte dal **Task 9** della fetta E4, con lo stesso metodo e lo stesso vincolo (`static/` non si
tocca: qui si elenca e si verifica). Ogni voce sotto è stata **verificata contro la tabella di
routing viva a HEAD della E4**, non copiata dal brief: due voci del brief sono risultate imprecise e
sono corrette qui sotto (righe 10 e 13).

## La tabella di routing viva a HEAD della fetta E4 (28 rotte + `/static`)

Estratta con `grep -n "app.router.add_" hiris/app/server.py` (29 righe, di cui una `add_static`):

```
$ git show 64e4457:hiris/app/server.py | grep -c "app.router.add_"     # base della fetta
37                                                                      # -> 36 rotte + /static
$ grep -c "app.router.add_" hiris/app/server.py                         # HEAD
29                                                                      # -> 28 rotte + /static
```

```
/  /config  /api/health  /api/config  /api/usage  /api/usage/reset
/api/chat  /api/chat/reply/{job_id}
/api/chatbots                                   <- GET, lista a UN elemento (compatibilità)
/api/chatbots/{agent_id}/chat-history           <- GET + DELETE, {agent_id} ignorato (compatibilità)
/api/entities
/api/models  /api/models/config
/api/knowledge/pending  /api/knowledge/{id}/approve  /api/knowledge/{id}/reject  /api/knowledge
/api/history/policy
/api/reasoning/claim  /api/reasoning/submit
/api/casa  /api/memoria  /api/memoria/{id}  /api/nucleo
```

**Uscite con la fetta E4** rispetto all'elenco della E3: `/api/status` (Task 4), `POST /api/chatbots`
(Task 3), `GET`/`PUT`/`DELETE /api/chatbots/{id}` (Task 3), `POST /api/chatbots/{id}/run` (Task 2),
`/api/chatbots/{id}/usage` e `/api/chatbots/{id}/usage/reset` (Task 3).

**Il conto delle rotte: 36 alla base della fetta -> 28 a HEAD, delta -8.** Le otto sono esattamente
quelle elencate qui sopra, verificate col diff dei percorsi fra le due versioni di `server.py`:
`GET`/`PUT`/`DELETE /api/chatbots/{agent_id}`, `GET /api/chatbots/{agent_id}/usage`,
`POST /api/chatbots/{agent_id}/usage/reset`, `POST /api/chatbots/{agent_id}/run`,
`POST /api/chatbots`, `GET /api/status`. *(Fix round 1: la prima stesura dichiarava una base di 35
e un delta di -7 -- in contraddizione con la propria lista, che ne contava otto.)*

## Tabella (seguito)

| # | Pagina / pezzo | File JS | Endpoint morti chiamati | Uscito con | Come si rompe |
|---|---|---|---|---|---|
| 9 | **Onboarding della chat** (overlay «Benvenuto in HIRIS») | `chat/onboarding.js` (righe 17, 47), overlay `index.html:28`, script `index.html:232` | `POST /api/chatbots` (riga 47) | E4 Task 3 | `check()` (riga 17) chiama `GET api/chatbots`, che è **vivo**: la lista torna con l'unico bot, `is_default: true`, quindi `nonDefault.length === 0` e **l'overlay si apre**. Prima della fetta bastava creare un secondo bot perché non riapparisse mai più; ora quel ramo è irraggiungibile per costruzione — l'unica uscita è `localStorage['hiris_onboarding_v1']`. «Crea» (riga 47) prende 404 e mostra `alert('Errore nella creazione assistente. Riprova.')`: **errore visibile**. «Salta» chiude e scrive il localStorage, quindi su un'installazione già usata l'overlay non ricompare. Il caso rotto è l'**installazione fresca**, o un browser nuovo. |
| 7bis | **Wizard di creazione — ramo Chatbot** (estende la riga 7) | `config/create-wizard.js:729-731` (`var url = isAgentbot ? 'api/agentbots' : 'api/chatbots'`) | `POST /api/chatbots` | E4 Task 3 | La riga 7 registrava morto solo il ramo Agentbot. Ora **entrambi i rami del ternario** puntano a rotte inesistenti: qualunque scelta faccia l'utente al primo step, «Crea» fallisce con l'errore visibile di `errorEl` («Errore nella creazione: HTTP 404»). Il wizard non ha più nessun esito riuscito. |
| 10 | **`#/chatbots` — editor** | `config/chatbot-editor.js` (righe 641 salva, 732 Test Run, 757 refresh post-run, 778 elimina) | `PUT /api/chatbots/{id}`, `POST /api/chatbots/{id}/run`, `GET /api/chatbots/{id}` | E4 Task 3 (PUT/DELETE/GET-single), E4 Task 2 (`/run`) | **Correzione al brief: l'editor CARICA.** Il caricamento non passa da `GET /api/chatbots/{id}` ma dalla **lista viva** (`loadChatbots()` a riga 105 e il fallback a riga 810), quindi la pagina si apre e mostra i campi che la lista compat espone (`id`, `name`, `enabled`, `status`, `is_default`, `max_chat_turns`). Tutto il resto dei riquadri (istruzioni, modello, permessi, budget, strumenti) si disegna sui **default vuoti**, senza dire che non li ha letti. Morti: **Salva** (riga 641 -> alert «Errore salvataggio Chatbot (HTTP 404)»), **Elimina** (riga 778 -> alert), **Test Run** `#btn-test-run` (riga 732 -> `r.json()` su un 404 `text/plain` rigetta, ramo `.catch` -> «Errore: …»). La riga 757 (refresh log+usage dopo il run) non viene mai raggiunta, perché il run fallisce prima. |
| 11 | **`#/chatbots` — lista** | `config/chatbots-list.js:9` | — (`GET /api/chatbots` è vivo) | — | Non è rotta: mostra **una riga sola**, che è il vero stato del prodotto. Elencata per completezza, perché la E5 la smonterà insieme all'editor. |
| 12 | **Card Lovelace** | `hiris-chat-card.js` (righe 785-796 stato/budget, 977 toggle, 713 sensore budget, 1317 selettore) | `PUT /api/chatbots/{id}` (riga 977) | E4 Task 3 | **Toggle «abilitato»: revert silenzioso.** La card fa il flip ottimistico, il `PUT` prende 404, `resp.ok` è falso e lo stato torna indietro **senza alcun messaggio** — l'utente vede l'interruttore rimbalzare. Il **chip budget resta a 0/—**: `GET api/chatbots` è vivo ma il payload compat non porta più `budget_eur`/`usage` (`agent.budget_eur` in OR con `0`, riga 796). Trovato durante la verifica e **non nel brief**: la riga 713 legge anche `sensor.hiris_{agentId}_budget_eur`, un'entità HA che veniva pubblicata via MQTT — uscito con la fetta **E3 Task 14**: quel sensore non esiste più in Home Assistant, quindi anche la seconda fonte del budget è morta. |
| 13 | **`#/usage` — sezione «Per Chatbot»** | `config/usage-route.js:58-105` | — (`GET /api/chatbots` è vivo) | E4 Task 6 (contabilità per-chatbot) | **Correzione al brief: non è una rotta morta.** La sezione si popola (la lista compat risponde) e mostra «1 totali» con una riga «Attivo» e `0 run · 0 tok · €0.000`: i campi `usage`/`budget_limit_eur`/`_rate_limit_paused` non esistono più nel payload e degradano tutti a zero/falso. È **una tabella che mente per omissione**, non una tabella vuota: sembra un consumo azzerato, ed è invece un consumo non misurato. Il contatore globale sopra (`api/usage`, righe 35 e 115) è vivo e vero. |
| 14 | **Blocco `designer:` di `hiris/translations/{it,en}.yaml`** (righe 118-186, fino a fine file) | — | — | E4 Task 2 (`section_testrun`, `test_run`), E4 Task 6 (`section_usage`), fette E2/E3 (`section_actions`, `section_permissions`, `log:`, `action:`, `proposal:`, `cron:`) | **Trovato durante la verifica, diverso da come lo poneva il brief.** Non è un blocco che «esce con le pagine in E5»: **non ha nessun lettore già oggi**. Verificato con grep su tutto `hiris/app/` (Python e JS): nessun file legge `hiris/translations/*.yaml`; le stringhe del Designer sono hard-coded in italiano dentro i `.js`. Il file `translations/` è il canale delle traduzioni **dell'add-on** (Supervisor), e lì l'unico blocco con un significato dichiarato è `configuration:` — quello sì, vivo e allineato. Il blocco `designer:` è quindi peso morto puro, non una dipendenza del frontend: la E5 può cancellarlo senza toccare nessuna pagina. *(Limite dichiarato: che il Supervisor ignori un blocco non previsto dal suo schema non è verificabile da questo repo — qui è verificata solo l'assenza di lettori in-repo.)* |

## La superficie di compatibilità da smontare in E5

Non è rotta: è **tenuta apposta viva** perché la pagina chat e la card ne dipendono davvero
(dichiarato al Task 3 della E4). La E5 la smonta insieme alle pagine che la chiamano:

1. **`GET /api/chatbots`** — restituisce una lista di **un solo elemento** costruita a mano da
   `handlers_chatbots.py::handle_list_chatbots` a partire da `ImpostazioniChat` (`id` costante,
   `status: "idle"` letterale, `enabled: true` letterale). Chiamanti: `chat/agents.js:83`,
   `chatbot-editor.js:105,810`, `chatbots-list.js:9`, `usage-route.js:58`, `onboarding.js:17`,
   `hiris-chat-card.js:785,1317`.
2. **`GET`/`DELETE /api/chatbots/{agent_id}/chat-history`** — il placeholder `{agent_id}` è
   **accettato e ignorato**: non è nemmeno più letto da `match_info`, perché dal Task 5 esiste una
   sola cronologia. Chiamanti: `chat/agents.js:116` (GET) e `chat/agents.js:37` (DELETE).
3. **`chatbot_id` nel corpo di `POST /api/chat`** — letto in `handlers_chat.py:179`
   (`_chatbot_id_ignorato`) e **mai usato per selezionare niente**. Letto invece di scartato di
   proposito, così una richiesta che porta la chiave non si comporta diversamente da una che la
   omette.

## Riepilogo per chi pianificherà la E5 (aggiornato a fine E4)

Alle 9 voci della E3 se ne aggiungono **6** (9, 7bis, 10, 12, 13, 14) più una riga di sola
completezza (11) e la superficie di compatibilità qui sopra. File JS nuovi rispetto all'elenco della
E3: `chat/onboarding.js`, `chatbots-list.js`, `usage-route.js`, `hiris-chat-card.js`, più
`hiris/translations/{it,en}.yaml` (blocco `designer:`) che non è un file JS ma esce con le stesse
pagine. `chatbot-editor.js` e `create-wizard.js` erano già in elenco e peggiorano.

**Le uniche due voci con un errore visibile all'utente** restano l'onboarding («Crea») e il wizard;
tutto il resto degrada in silenzio — che è, di nuovo, il motivo per cui il censimento non le vede.

Nessuno di questi file è stato toccato dalla fetta E4.

---

# Chiusura — la fetta E5 ha eseguito questo elenco (Task 12, 11 agosto 2026)

Prodotta dal **Task 12** della fetta E5 («Il frontend»), il conto della fetta. **Questo documento si
chiude qui: ha fatto il suo lavoro.** Non va ampliato — quello che resta aperto sta in fondo, per
nome, e vive nel CHANGELOG e nel ledger, non qui.

Range della fetta: `1e14382..9f43316`. Tutti i numeri sotto sono **misurati col comando a
`9f43316`**, non ricordati.

## Le quattordici voci della tabella, e come sono state risolte

| # | Voce | Esito | Con quale task |
|---|---|---|---|
| 1 | Dashboard `#/` — zona «Azioni» | **ricostruita** — la home non è più un pannello di controllo di cose che non esistono: è «Cosa HIRIS sa» (casa letta, comportamento, plance, nucleo verbatim). I tre badge di navigazione sono usciti col loro codice | Task 6 (badge e pannelli), Task 8 (la pagina nuova) |
| 2 | `#/tasks` (pagina intera) | **uscita** — rotta SPA, file, voce di menu | Task 6 |
| 2b | Pannello Task della chat + voce nav | **uscito** (`chat/tasks.js`) | Task 6 |
| 3 | `#/proposals` (pagina intera) | **uscita** (`proposals-route.js`, `proposals.js`; `proposals-core.js` è uscito al Task 8, non al 6: la Dashboard vecchia lo usava ancora, e cancellarlo al Task 6 avrebbe rotto la home) | Task 6, Task 8 |
| 3b | Pannello Proposte della chat + voce nav | **uscito** (`chat/proposals.js`) | Task 6 |
| 4 | `#/agentbots` (lista) + editor Agentbot | **uscita** (`agentbot-route.js`, `agentbot-editor.js`) | Task 6 |
| 4b | Voce di navigazione Agentbots | **uscita** | Task 6 |
| 5 | `#/gateway` (pagina intera) | **uscita** (`gateway-route.js`, e con essa il commento morto su `HA_NOTIFY_SERVICE`) | Task 6 |
| 6a | Editor Chatbot — riquadro «Autonomia» | **uscito col suo editor**; il blocco Agentbot superstite dentro `mount()` — che non era di nessun task — è stato rimosso al fix del Task 6 | Task 6 |
| 6b | Editor Chatbot — riquadro «Context preview» | **uscito col suo editor** (`logs.js` cancellato) | Task 6 |
| 7 | Wizard di creazione — ramo Agentbot | **uscito** (`create-wizard.js` intero) | Task 6 |
| 8 | Catalogo a checkbox del Designer | **uscito** (`templates.js` intero). *Nota: erano **33** voci in `TOOLS`, non 34 — vedi le correzioni sotto* | Task 6 |
| 9 | Onboarding della chat («Benvenuto in HIRIS») | **uscito per primo**, perché era il Critical: il primo gesto del primo utilizzo dava un errore. `chat/onboarding.js`, l'overlay e lo script di `index.html` | Task 1 |
| 7bis | Wizard — ramo Chatbot | **uscito col wizard** | Task 6 |
| 10 | `#/chatbots` — editor | **uscito** (`chatbot-editor.js`, `editor-kit.js`, `entity-picker.js`, `permessi.js`, `drawer.js`, `popover.js`, `log-row.js`; `labels.js` al Task 8) | Task 6, Task 8 |
| 11 | `#/chatbots` — lista | **uscita** (`chatbots-list.js`) | Task 6 |
| 12 | Card Lovelace | **uscita per intero, non ripulita** — decisione del proprietario dell'11 agosto: rientrerà **rifatta** quando il prodotto sarà completo. E con un **disinstallatore**: l'add-on toglie da Home Assistant la risorsa Lovelace e i file che *lui* aveva installato, idempotente, e se HA non risponde non fallisce l'avvio ma logga quale risorsa è rimasta e dove toglierla a mano | Task 5 |
| 13 | `#/usage` — sezione «Per Chatbot» | **corretta, non cancellata a metà**: la tabella che mentiva per omissione esce, e il sottotitolo **dichiara** che il dato per assistente non è misurato — non lo nasconde | Task 7 |
| 14 | Blocco `designer:` delle traduzioni | **uscito** da `it.yaml` e `en.yaml` nello stesso commit. Righe reali `it.yaml:174`→fine e `en.yaml:139`→fine (non 118-186, e nemmeno 154/133: vedi sotto) | Task 11 |

## Le due voci che questo elenco non aveva

Entrambe trovate col grep completo di `fetch(`/`api(` su `static/` mentre si scriveva il piano E5, e
**non** presenti nella tabella sopra:

- **`config/usage.js`** (92 righe, caricato staticamente da `config.html`) — il riquadro «Consumi»
  *dentro* l'editor Chatbot: tre chiamate, tutte e tre 404 dalla E4 Task 3
  (`GET api/chatbots/{id}/usage`, `POST .../usage/reset`, `PUT api/chatbots/{id}`).
  **Uscito col suo editor** al Task 6, insieme ai suoi 4 test JS e al suo test Python.
- **`config/models-route.js:572`** — ogni cambio di select nella sezione 3 di `#/models` faceva
  `PUT api/chatbots/{id}` → 404, `sel.value = prev` e badge rosso. `#/models` era dichiarata «non
  rotta» in questo stesso documento. **Corretta al Task 7**: la sezione dell'assegnazione per entità
  esce (i suoi due controlli erano *sempre* fallimentari), e il modello della chat si cambia dalla
  pagina Impostazioni chat, dove ha sempre dovuto stare.

## Le tre correzioni a questo documento

Dal piano E5 §0, tutte e tre confermate durante l'esecuzione:

1. **Il blocco `designer:` non era alle righe 118-186.** Il piano lo correggeva in `it.yaml:154` /
   `en.yaml:133`; il Task 11, ricontando prima di tagliare, ha trovato **174** e **139** (fino a fine
   file: 242 e 207). *Anche la correzione era invecchiata.*
2. **Gli strumenti a checkbox erano trentatré, non trentaquattro** (`templates.js`, `TOOLS`).
3. **La card Lovelace non mostrava «Card non configurata» a un tester**: `getStubConfig()` restituiva
   già un `chatbot_id`, quindi una card aggiunta dal picker di HA renderizzava sempre. Il guasto vero
   era un altro — ed è diventato irrilevante, perché la card è uscita per intero.

## Il conto delle rotte a fine fetta

`grep -c "app.router.add_" hiris/app/server.py` → **31 righe**, di cui una `add_static`:
**30 registrazioni di rotta + `/static`**, contate con la stessa convenzione delle sezioni sopra.

Il confronto con le **28** di fine E4 non è diretto: fra la E4 e la E5 c'è stata la parità del ponte,
che ha aggiunto `POST /api/mcp` (**29** alla base della fetta, `1e14382`, verificato col comando).
Da 29 a 30, dentro la E5:

- **fuori 3**: `GET /api/chatbots`, `GET` e `DELETE /api/chatbots/{agent_id}/chat-history` — l'intera
  superficie di compatibilità che la E4 aveva contratto **con la scadenza scritta** (Task 4, Task 10);
- **dentro 4**: `GET` e `DELETE /api/chat/cronologia` (Task 4: la cronologia ha una rotta onesta, senza
  un id di bot accettato e ignorato), `GET` e `PUT /api/impostazioni-chat` (Task 2: la pagina che non
  c'era).

**Delta netto +1 registrazione, ma quattro rotte nuove e tre morte in meno:** la superficie non è
cresciuta, si è spostata da quella del prodotto vecchio a quella del prodotto vero.

Sul lato SPA il conto è l'opposto e più netto: `grep -rn "HirisRouter.register" hiris/app/static/`
dà **6** rotte a HEAD contro **14** alla base — dieci uscite (`#/chatbots`, `#/chatbots/new`,
`#/chatbots/:id`, `#/nuovo`, `#/agentbots`, `#/agentbots/new`, `#/agentbots/:id`, `#/proposals`,
`#/tasks`, `#/gateway`) e due nate (`#/memoria`, `#/impostazioni`). Restano `#/` («Cosa HIRIS sa»),
`#/memoria`, `#/models`, `#/usage`, `#/history`, `#/impostazioni`.

## Cosa resta aperto (non è un difetto: è la mappa del dopo)

1. **`knowledge_store` e le tre rotte `/api/knowledge*` senza faccia.** `GET /api/knowledge/pending`,
   `POST /api/knowledge/{id}/approve`, `POST /api/knowledge/{id}/reject` hanno perso l'unico
   chiamante frontend col pannello Conoscenza della chat (Task 9). Restano vive perché lo store è
   materia della **fetta conoscenza**, non di questa. Sono tre delle cinque voci «rotte chiamate solo
   dai test» del censimento.
2. **`/api/entities` come superficie API senza pagina.** L'entity-picker era il suo ultimo chiamante
   frontend ed è uscito al Task 6. La rotta resta perché è superficie API interna, non una pagina — e
   il docstring della rotta lo dice, così il reperto non sembra un difetto a chi non ha il conto in
   mano.
3. **I due CSS monolitici, potati ma non riscritti.** `hiris-config.css` e `hiris-chat.css` sono
   condivisi da tutte le viste: non c'è un file per pagina. La potatura del Task 6 ha retto a una
   verifica formale (148 token estratti dalle righe rimosse e incrociati con quelli davvero usati dal
   frontend superstite, comprese le famiglie composte a runtime), ma **restano tre regole orfane note
   e non tolte** — `.task-section-title`, `.task-empty`, `.pp-warn` in `hiris-chat.css`, orfanate dal
   pannello Task uscito al Task 6. Nessuno strumento del repo le vede: il censimento dichiara di non
   guardare il frontend.
4. **`#/history` resta, e configura un motore acceso.** `HistoryCapture` è cablato all'avvio, la
   compattazione è schedulata, il digest gira: la pagina non è morta. La sua sorte **di prodotto** la
   discute la mappa delle funzionalità, non questa fetta.
5. **L'assenza totale di i18n della UI web.** L'add-on parla due lingue (`translations/it.yaml` e
   `en.yaml`, canale Supervisor); la sua interfaccia web ne parla **una sola**, con le stringhe
   scritte in italiano dentro i `.js`. Non è una regressione di questa fetta: è una mancanza che
   questa fetta ha reso visibile, perché ha riscritto le pagine e ha dovuto scrivere ogni frase in
   una lingua sola.

---

**Nessuna delle voci qui sopra è un guasto che un tester UAT possa incontrare.** Ciò che un tester
incontra, e che questa fetta ha chiuso, è nel CHANGELOG alla voce `[2.0.0]`.
