# Agenti v1.1 — Fase 2.5: step-up per Task autonomi + owner minimo + tetto token robusto

> Estende la Fase 2 (modalità obiettivo + perimetro). Chiude i due debiti lasciati aperti
> — `max_tier` inerte a runtime e tetto token cieco sui backend senza `usage` — costruendo
> il pezzo che mancava perché avessero senso: la **conferma out-of-band per un agente
> autonomo**. Anticipa con intenzione un frammento di Fase 3 (step-up autonomo), senza la
> fiducia progressiva (nessun "Sempre", nessuno store di concessioni).

**Data:** 2026-07-30 · **Base:** branch `feat/agenti-v1.1-fase2` @ `1a395ef` · **Nessun tag** (v1.1 si tagga a fine Fase 4).

---

## 1. Perché questa fetta esiste (il grounding che l'ha ribaltata)

La Fase 2 ha lasciato due debiti dichiarati nel design doc (`2026-07-29-design-agenti-v1.1.md`, §4 e §5):

1. **`max_tier` è validato e persistito ma nessun runtime lo legge.** Il campo prometteva un
   tetto che non esisteva.
2. **Il tetto `budget_tokens` è cieco dove il backend non ritorna `usage`** (OpenAI-compat:
   OpenRouter/Ollama). Pieno su Claude, condizionale altrove.

L'utente ha scelto di **chiuderli entrambi ora**, non di rinviarli. Leggendo il codice del
gating è emerso il fatto che ha ridisegnato la fetta:

> **Le azioni vere di un agente-obiettivo sono i Task che emette. E nel path dei Task
> (`task_engine._run_action`) il verdetto del semaforo è secco: `allow` → esegue; qualunque
> altra cosa (`confirm`/`deny_*`) → SKIP. Per un Task NON esiste alcuna conferma step-up.**

Lo step-up tap+OTP della Slice 2 vive sul path della *Decision* dell'agentbot
(`executor.propose`) e su chat/gateway — mai sui Task autonomi. Oggi un Task giallo/rosso
emesso da un agente-obiettivo viene **saltato in silenzio** (loggato).

Conseguenza: "onorare `max_tier` come auto-ceiling" sul path reale è un no-op per il default
verde, e per un tetto più alto diventerebbe **giallo-auto = fiducia progressiva**, vietata in
questa fase. L'unica lettura sensata e conforme è **costruire lo step-up per i Task**: un'azione
oltre il verde **chiede** (tap/OTP all'owner) invece di sparire.

Costruire lo step-up *fatto bene* ha una dipendenza: **serve un canale privato dove recapitare
tap/OTP** — un **owner**. Era rinviato dalla Fase 2. Lo includiamo qui, minimo.

## 2. Cosa esiste già (da riusare, non ricostruire)

Verificato su codice reale (`server.py`, `api/handlers_gateway_pending.py`,
`api/handlers_gateway_policy.py`):

- **`request_confirmation_stepup(app, data_dir, *, tool, inputs, tier, user)`** — congela
  `inputs`, invalida eventuali OTP pending dell'utente, crea il pending con OTP, manda il push
  (tap Approva/Rifiuta per il giallo; **OTP-only per il rosso/pericoloso**, decisione Owner Fix 3),
  e **fallisce-chiuso** (`return None`) se `user` è assente/"home" **o** se non c'è un canale
  notify **privato** per quell'utente. È già la funzione giusta: va solo chiamata dal path Task.
- **`private_notify_service_for_user(app, user)`** — risolve un utente a un servizio notify
  **privato**, SOLO dal mapping esplicito `notify_users`; ritorna `None` per il notify
  condiviso/globale e per `notify.persistent_notification`. È la guardia anti-leak dell'OTP.
- **`execute_pending(app, entry)`** — all'approvazione (tap → `approve` / OTP → `verify_otp`)
  esegue **esattamente l'`inputs` congelato** via il dispatcher, con whitelist ristretta al
  dominio dell'azione e `tier_confirmed=True`. L'OTP sblocca l'azione, non la ridefinisce.
- **`notify_users`** — il mapping utente→canale privato già in config, usato dal path chat.

Quindi l'**owner minimo** non è un nuovo sottosistema: è **un'opzione addon che nomina un
utente già presente in `notify_users`**.

## 3. Design

Quattro componenti, ognuno con un confine netto.

### C1 — Owner minimo (identità + canale privato)

- Nuova opzione addon **`agent_owner`** (stringa, default `""`): l'identità utente a cui
  recapitare le richieste di conferma degli agenti autonomi. Deve corrispondere a una chiave di
  **`notify_users`** perché esista un canale privato; altrimenti lo step-up fallisce-chiuso
  (per costruzione di `private_notify_service_for_user`).
- **Nessuno store nuovo, nessuna materializzazione per-agente.** L'owner è globale
  (un'installazione, un padrone di casa), coerente col design («un owner configurato nelle
  opzioni addon»). Il legame agente→owner è implicito: tutti gli agenti autonomi rispondono
  all'owner configurato.
- Esposto in UI addon nel gruppo delle opzioni Sentinella/agenti, con hint: «Serve un canale
  in *Utenti notifica* per ricevere tap/OTP; senza, le azioni che richiedono conferma vengono
  saltate».

**Confine:** C1 fornisce solo *chi* e *dove*. Non decide *quando* si chiede (è C2) né *cosa*
può essere chiesto (è C3).

### C2 — Step-up per i Task autonomi

Il cuore. In `task_engine._run_action`, sul ramo `call_ha_service`, dopo `normalize_target` e
il gate `gate_action`:

- **Oggi:** `if _v.decision != "allow": return f"skipped: {_v.decision}"`.
- **Nuovo:** un verdetto **`confirm`** (giallo/rosso) non viene più saltato: si tenta lo
  step-up. `deny_dangerous` e `deny_off` **restano skip** (un dominio pericoloso o un tier off
  non è mai confermabile — la denylist è assoluta, invariata).

Meccanismo (dependency injection, come l'executor riceve `propose` — `task_engine` **non**
importa lo store dei pending):

- `TaskEngine` acquisisce un callable opzionale **`request_stepup(*, tool, inputs, tier) →
  Awaitable[dict | None]`**, iniettato in `server.py` come chiusura su
  `request_confirmation_stepup(app, data_dir, ..., user=agent_owner)`.
- Su `confirm`: `_run_action` costruisce l'`inputs` congelato dell'azione (il `domain`,
  `service` e i `normalized.data` **già normalizzati** — gli stessi entity_id gated, mai il
  `data` grezzo) e chiama `request_stepup(tool="call_ha_service", inputs=inputs, tier=_v.tier)`.
  - **ritorna un pending** → l'azione è ora *in attesa*: `_run_action` ritorna
    `"pending: confirmation ({domain}.{service})"`. L'azione **non** viene eseguita ora; verrà
    eseguita fuori banda da `execute_pending` all'approvazione (tap o OTP), esattamente come il
    path chat. **Il Task non blocca lo scheduler** e non attende in-process: l'azione confirm è
    delegata al pending, il resto del Task prosegue.
  - **ritorna `None`** (fail-closed: `request_stepup` non iniettato, owner assente, nessun
    canale privato) → **fallback allo skip di oggi** (`return f"skipped: {_v.decision}"`),
    loggato. **Nessuna regressione**: è il comportamento pre-fetta, ma ora tracciato con il
    motivo.

**Perché delegare l'azione al pending invece di sospendere il Task:** sospendere e riprendere
il control-flow di un Task a metà sequenza (con condizioni, azioni successive, TTL) è un
secondo meccanismo di attesa parallelo a quello dei pending. Riusare `execute_pending` mantiene
**un solo posto** in cui un'azione congelata viene eseguita all'approvazione, e **un solo**
formato di pending. L'azione confirm è un evento out-of-band, non una tappa bloccante del Task.

**Confine:** C2 decide *quando* chiedere (verdetto `confirm`) e *delega* a C1 il recapito e a
`execute_pending` l'esecuzione. Non tocca `gate_action`, la denylist, `force_notify_only`, né
introduce un secondo punto di enforcement del perimetro.

### C3 — `max_tier` onorato (nei limiti della fase)

Con lo step-up disponibile, `max_tier` acquisisce un ruolo runtime **conforme al vincolo
"nessuna fiducia progressiva"**:

- **Auto clampato al verde.** In Fase 2/2.5 l'unico tier auto-eseguito resta il verde
  (`gate_action → allow`). Un `max_tier="yellow"` **non** abilita il giallo-auto: sarebbe
  fiducia progressiva. Quel campo è validato, persistito e **onorato fino al limite della
  fase**; la sua parte "sblocca l'auto per tier più alti" atterra in **Fase 3**.
- **Conseguenza osservabile in Fase 2.5:** `max_tier="green"` e `max_tier="yellow"` si
  comportano identicamente — verde auto, giallo/rosso **chiedono** via step-up (C2),
  pericoloso/off skip. Il valore del campo diventa un discriminatore osservabile solo quando
  la Fase 3 aggiunge la UI e la fiducia progressiva.
- **Onestà nel doc e nel codice:** un commento in `task_engine`/`agentbots` dichiara che
  `max_tier` è onorato-fino-al-verde in questa fase e rimanda a Fase 3, così non torna a essere
  una promessa vuota (il fallimento-modo che la Fase 2 aveva già corretto una volta).

**Confine:** C3 non aggiunge codice di gating oltre il clamp già implicito (il verde è l'unico
`allow`); è soprattutto una *decisione di semantica* e la sua documentazione veritiera. Se in
futuro si volesse dare a `max_tier` un ruolo di **tetto di ciò che può essere chiesto** (rosso
oltre un tetto giallo → skip invece di chiedere), è una riga in C2 — annotata come opzione, non
implementata qui, per non anticipare Fase 3.

### C4 — Tetto token robusto (stima dove `usage` manca)

Chiude il debito §5. Il tetto per-esecuzione (Fase 2 Task 5) misura i token come delta dei
contatori per-agente attorno a `reason()`; su un backend che risponde **senza `usage`** i token
non avanzano e il tetto non morde (`OpenAICompatRunner._track_usage` esce quando manca).

- **Fix:** quando la risposta non porta `usage`, **stimare** i token in modo conservativo dalla
  lunghezza del testo scambiato — euristica `ceil(len(text)/4)` su prompt+risposta — e
  registrarli nello **stesso** contatore per-agente, dentro il blocco che scrive i token. Così
  `budget_tokens` morde anche su OpenRouter/Ollama.
- **Solo `OpenAICompatRunner`.** Claude popola `usage` sempre: invariato.
- La stima è **marcata** (una chiave o un flag) così l'esito leggibile può distinguere
  "interrotto:budget (stimato)" da una misura reale, e il `logger.warning` una-tantum
  esistente (`_AGENT_UNMEASURED_WARNED`) diventa "misurato per stima" invece di "non
  misurabile".
- `deadline_min` resta il bound duro e indipendente: la stima non lo sostituisce, lo affianca.

**Confine:** C4 tocca `openai_compat_runner` (il punto dove i token si scrivono) e il consumo
del contatore lato budget. Non tocca Claude, non cambia la forma pubblica di `usage.json` oltre
ad aggiungere il conteggio stimato al per-agente già esistente.

## 4. Flusso dati (azione confirm di un agente-obiettivo)

```
agente-obiettivo (pianificato) → ragiona → emette create_task(agent_id, perimetro)
  → Task persistito
  → Task scatta → _run_action(call_ha_service)
      → normalize_target → gate_action
          allow (verde)        → esegue subito (invariato)
          confirm (giallo/rosso)→ request_stepup(inputs congelato, tier)
                                     ├─ pending  → push tap/OTP all'owner ; Task ritorna "pending"
                                     │              → owner approva (tap|OTP) → execute_pending → azione eseguita
                                     └─ None (fail-closed) → skip loggato (≈ oggi)
          deny_dangerous/deny_off → skip (invariato)
```

## 5. Invarianti di sicurezza (da preservare e testare)

- **La denylist domini pericolosi è assoluta e invariata.** `deny_dangerous` non passa mai per
  lo step-up: un lock/allarme/cover/sirena/garage non è confermabile da un Task autonomo.
- **Nessun auto sopra il verde.** L'unico `allow` è il verde; nessun percorso di questa fetta
  esegue giallo/rosso senza approvazione umana. Nessuna fiducia progressiva.
- **L'OTP non lascia mai un canale non-privato.** Ereditato da `private_notify_service_for_user`:
  senza mapping `notify_users` per l'owner, lo step-up fallisce-chiuso. L'OTP non viaggia mai su
  `notify.persistent_notification` né su un notify condiviso.
- **L'azione eseguita all'approvazione è quella congelata**, mai ridderivata dal Task o
  dall'LLM: `execute_pending` esegue `entry.inputs`, con whitelist ristretta al proprio dominio
  e `tier_confirmed=True`.
- **Un solo punto di enforcement del perimetro** resta `task_engine` (Fase 2 Task 3); C2 non ne
  aggiunge un secondo. Gli `entity_id` congelati nel pending sono i `normalized.entity_ids`
  **già gated**, non il `data` grezzo (no target-vs-data split).
- **`allowed_tools`/`EVALUATION_ONLY_TOOLS` invariati**: questa fetta non tocca il ragionatore.
- **Fail-closed ovunque**: callable non iniettato, owner assente, canale mancante, `usage`
  assente → tutti degradano a un comportamento sicuro e loggato, mai a un'azione non
  autorizzata né a un tetto silenziosamente disattivato.

## 6. Testing

- **C1 owner:** `agent_owner` senza mapping `notify_users` → `request_stepup` ritorna None →
  skip (test end-to-end sul path Task). `agent_owner` con canale privato → pending creato.
- **C2 step-up Task:** un Task con azione giallo/rosso → pending creato + push (fake notify) +
  Task ritorna "pending", azione **non** eseguita subito; l'approvazione (tap e OTP,
  separatamente) esegue l'azione congelata via `execute_pending`; `deny_dangerous`/`deny_off`
  restano skip; fail-closed → skip loggato (non pending). Non-regressione: verde auto invariato.
- **C3 max_tier:** `max_tier="green"` e `="yellow"` producono lo **stesso** comportamento
  osservabile in questa fase (verde auto, giallo/rosso chiedono); nessun giallo-auto per
  `max_tier="yellow"` (test discriminante che pinna il vincolo).
- **C4 tetto token:** backend fake che risponde **senza** `usage` → il contatore per-agente
  avanza per stima e `budget_tokens` morde (esecuzione interrotta con esito "stimato"); backend
  con `usage` → misura reale invariata; Claude invariato.
- **Suite piena** verde (baseline pytest 2000, npm 74) a ogni task; commit per task.

## 7. Fuori scope (esplicito — è Fase 3)

- **Fiducia progressiva / "Sempre":** nessuna concessione persistente, nessuno store di
  concessioni. Ogni azione oltre il verde chiede, ogni volta.
- **`max_tier` come sblocco dell'auto** per tier più alti (giallo-auto): Fase 3.
- **Domanda all'80% del budget** e resoconto strutturato completo: Fase 3 (qui il budget si
  ferma pulito e dice perché, già da Fase 2 Task 5).
- **Owner multipli / per-agente, ruoli:** un solo owner globale in questa fetta.
- **Riprendere il control-flow del Task** all'approvazione: l'azione confirm è delegata al
  pending, non è una tappa bloccante del Task.

## 8. Ordine dei task (per il piano)

1. **C1** owner minimo (opzione `agent_owner` + UI addon + wiring identità).
2. **C2** step-up Task (callable `request_stepup` iniettato; ramo `confirm` in `_run_action`;
   fallback fail-closed). Il cuore.
3. **C3** `max_tier` onorato-fino-al-verde + documentazione veritiera.
4. **C4** tetto token robusto (stima su `usage` assente, marcatura esito).
5. **Verifica finale & handoff:** whole-branch review (denylist/no-auto-sopra-verde/canale-privato/
   frozen-inputs intatti), live-verify utente, conferma → merge. Nessun tag.
