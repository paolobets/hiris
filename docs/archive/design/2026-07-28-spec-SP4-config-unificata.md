# SP-4 — Config entità unificata · Spec

**Data:** 2026-07-28 · Repo: `hiris` (+ `retro-panel` in lockstep) · Base: `master`
@ `c1d384e` (SP-3 v0.101.0) · North-star:
`docs/design/2026-07-27-north-star-brain-chatbot-agentbot.md` (§«Config entità
unificata», roadmap SP-4). Baseline config:
`docs/design/2026-07-27-mappa-config-agenti-lenti.md` (branch `analysis/config-agenti-lenti`).

## Obiettivo

Chiudere l'incoerenza fra le due famiglie di entità AI — **Chatbot** (oggi
"agente"/persona, chat) e **Agentbot** (oggi "lente", proattivo) — con **nomi puliti
ovunque** e **una cornice di configurazione condivisa**: stessi blocchi comuni,
disclosure progressiva, creazione manuale coerente e **goal-first**. Porta l'Agentbot
alla pari del Chatbot (modello/scope/knowledge/osservabilità oggi assenti in UI).

Target: **prosumer Home Assistant**, disclosure progressiva. Due fasi indipendenti e
rilasciabili.

## Decomposizione: due fasi

- **Fase A — Rename profondo (SP-1b):** `agente→Chatbot`, `lente→Agentbot` in
  codice/API/route/DB, + eliminazione del triplo significato di "lens". **Taglio netto
  API** + aggiornamento di Retro Panel (`hiris_proxy.py`) **in lockstep** + migrazioni
  dati one-time. Release intermedia **v0.102.0** (+ bump RP).
- **Fase B — Cornice unificata:** editor **unico** con creazione **goal-first
  guidata**, blocchi condivisi (E.1), Agentbot portato alla pari, disclosure
  progressiva. Release **v0.103.0**.

## Scope

### Dentro (SP-4)

1. **Rename completo e coerente** su nomi puliti (Fase A).
2. **Editor unico** Chatbot/Agentbot con **creazione goal-first guidata**
   (deterministica): obiettivo in NL → derivazione/suggerimento del tipo → step
   guidati → editor strutturato come "Avanzate".
3. **Blocchi condivisi (E.1)**, resa identica per entrambi: identità/stato, **modello**
   (Agentbot prende la UI sul dato `reasoning.model` di SP-2), **scope** (selettore
   entità/aree riusato), **knowledge** (espone `knowledge_access`), **autonomia**
   (riepilogo coerente, semaforo intatto), **osservabilità base** per-entità
   (log/consumi).
4. **Creazione manuale duale coerente** (scegli/deriva il tipo → editor unico).
5. Pulizia vestigia pre-Slice-5 in `agent_engine` (placeholder "Monitor energia", hint
   "non gira automaticamente", 5 template autonomi).

### Fuori (SP-4) — confini espliciti

- **Wizard Brain-assistito** (obiettivo NL → il Brain **inferisce/propone** l'intera
  config, LLM-assisted) → **fase Riprogettazione Agentbot** (slice dopo). SP-4 fa solo
  la versione **guidata deterministica**.
- **Brain-propone→Agentbot** (generazione automatica di un Agentbot dal Brain) →
  **Riprogettazione Agentbot**.
- **"Perché non è scattato"** (diagnosi cooldown/cap invisibili) → **SP-5**. SP-4 mostra
  log/consumi base, non il diagnostico profondo.
- **Fusione vera** dell'autonomia (semaforo ↔ conferma) → **non si fa** (solo superficie
  coerente).
- **Fusione dei detector/situazioni built-in** nel modello Agentbot → Riprogettazione
  Agentbot. SP-4 sposta solo le **lenti user-defined** su `#/agentbots`.
- **Nuovi tool esterni** (es. web search / egress) → fuori scope; il perimetro tool
  resta **HA + knowledge**. Un'eventuale capability esterna richiede un design di
  sicurezza/egress dedicato.

## Linea rossa di sicurezza (non negoziabile)

Il confine **E.2** è un pilastro di sicurezza, non un dettaglio UI:
- **Agentbot** = contratto a **verdetto-JSON senza tool liberi**; l'azione è
  **dichiarata** in config e gated dal **semaforo**; l'AI non sceglie mai l'azione;
  `allowed_tools=[]` nel reasoning.
- **Chatbot** = tool liberi (dentro allowlist) + conferma opzionale, **senza trigger
  autonomi**.
- **Vietato** creare un'entità unica con **tool-liberi + trigger autonomi + attuazione**
  (è l'"Agent" bifronte ritirato dallo Slice 5). Il wizard goal-first mappa l'obiettivo
  sull'entità **giusta**, non fonde i due contratti.

## Fase A — Rename profondo

### Mappa del rename

| Ambito | Oggi | Nuovo |
|---|---|---|
| Entità 1 | "agente"/persona, dataclass `Agent` | **Chatbot** (dataclass `Chatbot`) |
| Entità 2 | "lente"/lens | **Agentbot** |
| API CRUD | `/api/agents`, `PUT /api/agents/{id}` | `/api/chatbots`, `PUT /api/chatbots/{id}` |
| API | `/api/lenses`, `PUT/DELETE /api/lenses/{id}` | `/api/agentbots`, `PUT/DELETE /api/agentbots/{id}` |
| API chat | `/api/chat`, `/api/chat/reply/{job}` | **invariato** (conversazione, non entità) |
| Route SPA | `#/agents`, `#/agents/new`, `#/agents/{id}`, `#/sentinel` | `#/chatbots`, `#/chatbots/new`, `#/chatbots/{id}`, `#/agentbots` |
| Storage | `agents.json`, `sentinel_lenses.json` | `chatbots.json`, `agentbots.json` |
| DB | colonna `lens` in `knowledge_items` (= id agente/Chatbot) | `chatbot_id` |
| FE files | `agent-editor.js`, `agent-form.js`, `agents-list.js`, `sentinel-route.js` | rinominati coerentemente |
| Retro Panel | `hiris_proxy.py` → HIRIS `/api/agents` | → `/api/chatbots` (+ toggle su `/api/chatbots/{id}`) |

Il triplo "lens" si scioglie: (1) lente-watcher → **Agentbot**; (2) colonna DB `lens`
→ **`chatbot_id`** (è l'id del Chatbot che scopa la memoria); (3) termine
architetturale "lenti" → **Agentbot**. Restano invariati i concetti interni non
user-facing solo dove il rename introdurrebbe rischio sproporzionato senza valore — da
decidere puntualmente nel piano (default: rinominare).

### Invariante Fase A

Il rename è **behavior-preserving**: contratti E.2, semaforo, runner, memoria,
scheduling, ragionamento **invariati** — solo nomi. Nessun cambiamento funzionale.

### Migrazioni dati (one-time, idempotenti, non-fatali al boot)

Pattern Slice 3 (marker `.migrated` controllato per primo, non solleva al boot):
- `agents.json` → `chatbots.json` (rinomina/rilettura retro-compat).
- `sentinel_lenses.json` → `agentbots.json`.
- Colonna `knowledge_items.lens` → `chatbot_id`: migrazione `user_version` via
  `storage.py`; la query di scope memoria aggiornata al nuovo nome colonna.
- Righe/riferimenti legacy caricati e riscritti senza perdita; agents.json/lenti legacy
  letti in retro-compat una volta.

### Retro Panel (lockstep)

`retro-panel/app/api/hiris_proxy.py` aggiorna gli URL upstream verso HIRIS
(`/api/agents` → `/api/chatbots`, toggle su `/api/chatbots/{id}`; `/api/chat`
invariato). Le route browser-facing di RP (`/api/hiris/*`) restano invariate (naming
interno RP). Test `hiris_proxy` di RP aggiornati. **Rilascio congiunto:** HIRIS v0.102.0
+ bump RP nella stessa tornata (nessun alias di compatibilità).

## Fase B — Cornice unificata

### Creazione goal-first guidata (deterministica)

Un unico flusso di creazione:
1. **Obiettivo** — nome + missione in linguaggio naturale.
2. **Derivazione tipo** — il wizard suggerisce **Chatbot** (conversa quando lo chiami)
   o **Agentbot** (agisce/segnala da solo su un evento), con scelta esplicita
   modificabile. Derivazione **deterministica** (heuristica leggera + scelta utente),
   **nessun LLM**.
3. **Step guidati** per tipo:
   - Chatbot → **tool** (HA/knowledge) + **scope** (entità/aree) + **knowledge**.
   - Agentbot → **trigger** (evento/cron/intervallo + condizione) + **azione dichiarata**
     (notify/service) + **scope**.
4. **Editor strutturato** (blocchi E.1/E.2) come livello **"Avanzate"** — stessa entità,
   accesso pieno alla granularità.

Il selettore di tipo esplicito diventa quindi **derivato dall'obiettivo**; l'editor
unico resta il substrato. Ponte naturale verso il **wizard Brain-assistito** (fase
dopo).

### Blocchi condivisi (E.1) — resa identica per entrambi

- **Identità/stato** — nome, descrizione, `enabled` (stessa semantica, stesso copy,
  timestamp/ultimo esito).
- **Modello** — un selettore "chi ragiona" per-entità con `auto` **spiegato** (catena di
  fallback visibile), sorgente `/api/models`. Chatbot → `model`; Agentbot →
  `reasoning.model` (dato SP-2, gli diamo la UI). Copy coerente (basta "auto — segue
  tipo agente" quando il tipo non esiste più).
- **Scope** — il selettore entità/aree (pill + ricerca + chips) riusato: Chatbot →
  `allowed_entities`; Agentbot → entità trigger + target azione (oggi campi testo grezzi).
- **Autonomia** — sezione che **spiega** cosa può fare in autonomia: riepilogo del tier
  semaforo delle entità toccate (pagina Gateway resta la fonte) + setting conferma.
  **Semaforo intatto, nessuna fusione.**
- **Knowledge** — espone `knowledge_access` (`allow_sensitive` + `kinds`), oggi solo-API,
  per entrambi.
- **Osservabilità base** — log per-entità + consumi (Chatbot ce l'ha; Agentbot nuovo:
  timeline filtrata per Agentbot + usage). Il diagnostico "perché non è scattato" resta
  SP-5.

### Sezioni specifiche (E.2) — distinte

- **Chatbot** — Istruzioni (`strategic_context` + `system_prompt` + template ripuliti),
  Tool (`allowed_tools`/`allowed_services`), Sessione (`max_chat_turns`, `response_mode`,
  `thinking_budget`, `max_tokens`, `restrict_to_home`).
- **Agentbot** — Trigger (evento/cron/intervallo + condizione), Verdetto (`reasoning` +
  prompt, **contratto JSON invariato**, `allowed_tools=[]`), Azione (notify/service
  **dichiarata**, gated dal semaforo).

### Disclosure progressiva

Default semplici visibili; sezione **"Avanzate"** per la granularità (thinking budget,
`allowed_endpoints`, `kinds`, `off_after_min`, ecc.). L'Agentbot rende visibili i limiti
runtime **condivisi** (cooldown/cap Sentinella) come informazione (il diagnostico
puntuale = SP-5).

### Consolidamento `#/sentinel`

Le **lenti user-defined** diventano `#/agentbots` (editor unico). I **detector/
situazioni/preparazione built-in** restano config Sentinella (tuning invariato); la loro
fusione nel modello Agentbot è materia della Riprogettazione Agentbot.

## Invarianti di sicurezza (pinnati da test)

1. Rename **behavior-preserving**: nessun cambiamento a semaforo/contratti/runner/
   memoria; suite verde con i nomi nuovi + test migrazione old→new.
2. Confine **E.2** intatto: Agentbot `allowed_tools=[]` nel reasoning, azione solo
   dichiarata+gated; Chatbot senza trigger autonomi; nessuna entità con
   tool-liberi+trigger+attuazione.
3. Semaforo **non toccato** (Fase B lo riepiloga, non lo rimodella).
4. `knowledge_access` esposto in UI **non allarga** i default (resta `allow_sensitive:
   false`); nessun nuovo egress; tool perimetro HA+knowledge.
5. Migrazioni non-fatali al boot, nessuna perdita dati.

## Test

- **Fase A:** rename → suite completa verde con nomi nuovi; test di **migrazione**
  (`agents.json`/`sentinel_lenses.json` legacy → nuovi store; colonna `lens→chatbot_id`
  con dati preesistenti; scope memoria corretto post-migrazione); `hiris_proxy` RP
  aggiornato e verde. Grep di regressione: nessun `/api/agents`/`/api/lenses`/`"lens"`
  residuo fuori dai path di migrazione.
- **Fase B:** wiring FE — l'editor rende **entrambi** i tipi; blocchi condivisi
  presenti; modello/scope/knowledge Agentbot **persistiti** end-to-end; flusso goal-first
  deriva il tipo corretto; `node --check`; render XSS-safe.
- **Sicurezza (discriminanti):** un Agentbot creato dal wizard non ottiene mai
  `allowed_tools` non vuoti; un Chatbot non ottiene mai trigger; il semaforo gate resta
  l'unico gate azioni.

## Processo & rilascio

- Branch: `feat/sp4a-rename-profondo` (Fase A), `feat/sp4b-cornice-unificata` (Fase B).
  RP: branch/bump coordinato con Fase A.
- Build **subagent-driven** con review Fable/Opus per-task + whole-branch (pattern
  HIRIS).
- **Bump:** HIRIS v0.102.0 (Fase A) → v0.103.0 (Fase B); RP bump in lockstep con Fase A.
- Doc IT/EN aggiornate dove cambiano nomi/UI; `PRODUCT.md` allineato ai nomi definitivi
  (chiude il TODO north-star).
- **Conferma esplicita** utente prima di ogni merge/tag/release e prima della
  live-verify.

## Riferimenti (grounding, da riverificare in fase di piano)

- Config attuale: `agent_engine.py` (dataclass `Agent`, `UPDATABLE_FIELDS`),
  `api/handlers_agents.py`, `watcher/lenses.py`, `api/handlers_lenses.py`,
  `watcher/lens_runner.py`, `brain/knowledge_store.py` (colonna `lens`),
  `server.py` (route in `create_app`, storage in `_on_startup`).
- FE: `static/config/main.js` (router), `agent-editor.js`/`agent-form.js`/
  `agents-list.js`, `sentinel-route.js`, `permessi.js`, `templates.js`.
- Modello per-entità (SP-2): `Chatbot.model`, `agentbot.reasoning.model`.
- Retro Panel: `retro-panel/app/api/hiris_proxy.py`.
- Semaforo: `security/semaphore.py` (invariato).
