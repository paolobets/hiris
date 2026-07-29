# Agenti v1.1 — Fase 2: modalità obiettivo reale + perimetro minimo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendere la **modalità obiettivo** davvero utilizzabile — un agente che legge, ragiona ed emette **Task dichiarativi** — dentro un **perimetro** che oggi non esiste. Niente fiducia progressiva: ogni azione fuori dal verde chiede conferma, sempre.

**Architecture:** Il grounding ha ribaltato l'assunto di partenza. Il ragionatore **non è senza tool**: ha già i 16 di `EVALUATION_ONLY_TOOLS`, `create_task` incluso. Quindi la modalità obiettivo **esiste già a metà** — quello che manca non è la capacità di emettere task, ma il **perimetro** e l'**attribuzione**. `Task` possiede già `allowed_entities`/`allowed_services` e li fa rispettare in esecuzione: il meccanismo c'è, nessuno lo alimenta. Questa fase lo **collega**, non lo costruisce.

**Tech Stack:** Python 3.11/3.12, aiohttp, APScheduler, pytest; JS vanilla senza build step + suite comportamentale `node --test` + jsdom.

## Global Constraints

- **L'invariante vero è «nessun tool che ATTUA», non «nessun tool».** `EVALUATION_ONLY_TOOLS` esclude deliberatamente `call_ha_service`, `send_notification`, `trigger_automation`, `toggle_automation`, `http_request` per impedire che un'iniezione via stato HA scateni azioni reali. **Quell'esclusione non si tocca, mai, per nessuna modalità.**
- **Nessuna fiducia progressiva in questa fase.** Nessun "Sempre", nessuno store di concessioni. Un'azione che il semaforo classifica `confirm` **chiede sempre**. La fiducia progressiva è la Fase 3, progettata sull'attrito reale di questa.
- **Non si tocca il semaforo** (`security/semaphore.py`), né la denylist, né `force_notify_only=(action_type != "service")` (il fail-closed sulla forma introdotto in Fase 1).
- **Validatore per primo.** `validate_agentbot` scarta le chiavi sconosciute **con un 201 di successo** — un campo introdotto altrove prima sparisce senza errori. Ordine: validatore → runtime → FE.
- Suite verde a ogni task: baseline **pytest 1905**, **npm 62**.
- Commit per task. Nessun merge senza conferma esplicita. **Nessun tag**: la v1.1 si tagga a fine Fase 4.

### Grounding (verificato 2026-07-29 su master `34789c7`)

| Fatto | Dove | Conseguenza |
|---|---|---|
| `allowed_tools=[]` è **falsy** → il filtro di restrizione viene **saltato** → il ragionatore riceve **tutti** gli `EVALUATION_ONLY_TOOLS` | `claude_runner.py:894-896` | «nessun tool» era falso: sono 16 |
| `EVALUATION_ONLY_TOOLS` contiene `create_task`, `cancel_task`, `list_tasks` + letture; **esclude** i 5 tool che attuano | `claude_runner.py:210-224` | l'invariante corretto è «niente attuazione diretta» |
| Il commento a fianco della chiamata dice «performs NO home actions» | `server.py:1322` | **falso e pericoloso**: ha ingannato ogni review di questa sessione |
| `_llm_reason` **non passa** `allowed_entities`/`allowed_services` | `server.py:1331-1334` | i tool del ragionatore sono **senza perimetro** |
| I task creati dal ragionatore prendono `agent_id = chatbot_id or "hiris-default"` | `dispatcher.py:378` | **non sono attribuiti** all'agente che li ha creati |
| `Task` ha già `allowed_entities`/`allowed_services` **e li fa rispettare** | `task_engine.py` (dataclass + `_run_action`) | il perimetro esiste: va alimentato |
| `normalize_target` **fail-closed** su target di gruppo (area/device/label/floor) | `semaphore.py:64-65`, applicato in `task_engine` | un intento «tutte le luci di X» va espanso in id espliciti |
| Objective è **irraggiungibile** a runtime (gate di Fase 1) | `handlers_agentbots.py` `get_event_agentbots`, `server.py` `register_agentbot_schedules` | va aperto **solo** per la pianificazione, mai per gli eventi |
| Al più **una OTP viva per utente**, TTL 5 min, monouso | `handlers_gateway_pending.py:28,153-177` | una richiesta cumulativa dovrà essere UN pending con N azioni (Fase 3) |

---

## Task 1: correggere il commento che ha ingannato tutti

Piccolo ma primo: un commento di sicurezza falso è **peggio di nessun commento**, perché ferma chi verrebbe a guardare.

**Files:** `hiris/app/server.py`, `hiris/app/watcher/agentbot_runner.py` (docstring del modulo), `docs/design/2026-07-29-design-agenti-v1.1.md`

- [ ] **Step 1:** In `server.py:1322` sostituire il commento con la verità verificabile: `allowed_tools=[]` **non** restringe (è falsy, `claude_runner.py:894-896`) — il ragionatore riceve tutti gli `EVALUATION_ONLY_TOOLS`. L'invariante è che quel set **esclude i tool che attuano**; l'attuazione passa solo dall'executor, gated dal semaforo. Citare i due file:riga.
- [ ] **Step 2:** Allineare la docstring di `agentbot_runner.py` (dichiara le invarianti «non negoziabili» e ripete l'affermazione sbagliata).
- [ ] **Step 3:** Allineare il design doc: dove dice «ragionamento **senza tool liberi**», precisare «**senza tool che attuano**: legge liberamente, non attua mai direttamente».
- [ ] **Step 4:** Aggiungere un test che **pinna il comportamento reale**, così non torna a essere folklore:
```python
# tests/test_claude_runner.py (o dove vivono i test del runner)
def test_empty_allowed_tools_does_not_narrow_evaluation_set():
    """allowed_tools=[] e' falsy: NON restringe. Il ragionatore riceve tutti
    gli EVALUATION_ONLY_TOOLS. L'invariante e' che quel set esclude i tool
    che attuano -- non che i tool siano zero."""
    from hiris.app.claude_runner import EVALUATION_ONLY_TOOLS
    for actuating in ("call_ha_service", "send_notification", "trigger_automation",
                      "toggle_automation", "http_request"):
        assert actuating not in EVALUATION_ONLY_TOOLS
    assert "create_task" in EVALUATION_ONLY_TOOLS   # la capacita' c'e': documentala
```
- [ ] **Step 5:** `pytest -q --maxfail=10` verde. **Commit:** `docs(security): il ragionatore non ha zero tool, ha zero tool che attuano`

---

## Task 2: perimetro nello schema dell'agente

**Files:** `hiris/app/watcher/agentbots.py`; test `tests/test_user_agentbots_store.py`

**Interfaces:** `validate_agentbot` accetta e restituisce un blocco `perimeter`:
```
perimeter: {
  allowed_entities: [str],   # glob o id espliciti; default []
  allowed_services: [str],   # glob di dominio;    default []
  max_tier: "green"|"yellow",# tetto: cosa puo' fare senza chiedere; default "green"
  budget_tokens: int,        # per esecuzione; default sensato
  deadline_min: int          # per esecuzione; default sensato
}
```
Regole: **obbligatorio in `mode="objective"`** (assente ⇒ default espliciti, non rigetto — un obiettivo senza perimetro è comunque confinato dal semaforo, ma va reso visibile); **vietato in `mode="rule"`** (una regola ha già la sua entità dichiarata). `max_tier` non può essere `"red"` né `"off"`: il tetto dice fin dove l'agente arriva **senza chiedere**, e il rosso chiede sempre.

- [ ] **Step 1:** Test che falliscono (default applicati in objective; rigetto in rule; `max_tier: "red"` rifiutato; bound su budget/deadline).
- [ ] **Step 2:** Verifica che falliscano.
- [ ] **Step 3:** Implementa `_validate_perimeter` sullo stile di `_validate_reasoning` (non solleva mai, normalizza) ma con rigetto sui valori inammissibili, coerente con `severity`/`enabled`/`mode`. Aggiungere `perimeter` al dict di ritorno (whitelist 9 → 10 chiavi). **Attenzione:** `mode: null` e `objective: ""` sono trattati come assenti (fix di Fase 1) — mantenere la stessa convenzione.
- [ ] **Step 4:** `pytest` mirato + suite piena. **Commit:** `feat(agentbot): blocco perimeter nello schema (ambito, tetto tier, budget, scadenza)`

---

## Task 3: attribuire e confinare i task che l'agente emette

**Il cuore della fase.** Oggi i task creati dal ragionatore sono attribuiti a `"hiris-default"` e nascono **senza perimetro**. `Task` sa già farlo rispettare: va alimentato.

**Files:** `hiris/app/server.py` (`_llm_reason`, `_run_decision`), `hiris/app/watcher/agentbot_runner.py`, `hiris/app/tools/dispatcher.py`; test `tests/test_run_agentbot.py`, `tests/test_task_engine.py`

**Interfaces:**
- `_llm_reason` accetta e propaga **identità** (`agent_id`) e **perimetro** (`allowed_entities`, `allowed_services`) fino a `run_with_actions`.
- Un task creato durante il ragionamento di un agente nasce con `agent_id` = quell'agente e `allowed_entities`/`allowed_services` = il suo perimetro.

- [ ] **Step 1: Test che fallisce** — il più importante della fase:
```python
def test_task_emitted_by_an_agent_inherits_its_identity_and_perimeter():
    """Oggi il task nasce come 'hiris-default' e senza perimetro: puo' agire
    su entita' fuori dall'ambito dell'agente che lo ha creato."""
    # far ragionare un agentbot objective con perimetro {allowed_entities: ["light.cucina"]}
    # e un LLM che emette create_task su light.salotto
    # -> il task deve nascere con agent_id dell'agente E allowed_entities del perimetro
    # -> e alla sua esecuzione l'azione su light.salotto deve essere RIFIUTATA
```
- [ ] **Step 2:** Verifica che fallisca (oggi il task nasce non attribuito e senza confini).
- [ ] **Step 3:** Propaga identità e perimetro lungo la catena. **Non toccare** `force_notify_only` né la re-iniezione di `suggested`: quelle guardie restano come sono.
- [ ] **Step 4:** Verifica che il rifiuto avvenga **dove già esiste** (l'enforcement in `task_engine`), non con un controllo nuovo e parallelo.
- [ ] **Step 5:** `pytest -q --maxfail=10`. **Commit:** `feat(agentbot): i task emessi ereditano identita' e perimetro dell'agente`

---

## Task 4: rendere raggiungibile la modalità obiettivo (solo pianificata)

**Files:** `hiris/app/server.py` (`register_agentbot_schedules`), `hiris/app/api/handlers_agentbots.py` (`get_event_agentbots`); test dedicati

Da design: **gli eventi restano dominio delle regole**. Si apre **solo** la pianificazione (e in Fase 4 l'invocazione dal Brain).

- [ ] **Step 1:** Test che falliscono: un agente objective **pianificato** viene registrato ed eseguito; un agente objective con trigger a evento resta **non dispatchato** (ma il validatore lo rifiuta già a monte — verificare la difesa in profondità).
- [ ] **Step 2-3:** Rimuovere il gate `mode == "rule"` **solo** nella comprehension delle pianificazioni, lasciandolo su `get_event_agentbots`.
- [ ] **Step 4:** Verifica + **Commit:** `feat(agentbot): la modalita' obiettivo gira su pianificazione (gli eventi restano alle regole)`

---

## Task 5: budget e scadenza per esecuzione

**Files:** `hiris/app/server.py` (percorso di ragionamento), `hiris/app/watcher/agentbot_runner.py`; test

Oggi esistono contatori **cumulativi** giornalieri e un timeout per-run del Chatbot, ma nulla che limiti una singola esecuzione di ragionamento di un agente. Un agente che valuta, ri-valuta ed emette task può girare a lungo.

- [ ] **Step 1:** Test: un'esecuzione che supera `budget_tokens` o `deadline_min` **si ferma** e lascia un esito leggibile (non un'eccezione, non un silenzio).
- [ ] **Step 2-3:** Implementa il bound. **Fermarsi è un esito, non un errore**: l'esecuzione va marcata come interrotta con il motivo.
- [ ] **Step 4:** Verifica + **Commit:** `feat(agentbot): budget e scadenza per esecuzione, con esito leggibile`

*(La domanda all'80% e il resoconto strutturato completo sono Fase 3: qui basta che si fermi in modo pulito e dica perché.)*

---

## Task 6: crearlo e vederlo dall'interfaccia

**Files:** `static/config/agentbot-editor.js` (ramo modalità), `static/config/create-wizard.js` (il wizard goal-first è il posto naturale per «obiettivo»), `config.html` se serve; test `tests/js/agentbot-editor.test.mjs` + wiring pytest

- [ ] **Step 1:** Test comportamentali (`node --test` + jsdom): scegliendo la modalità obiettivo l'editor mostra obiettivo + perimetro e **nasconde** trigger-evento e azione; il payload salvato contiene `mode`, `objective`, `perimeter` e **nessun** `action`.
- [ ] **Step 2-3:** Implementa. **Attenzione (backlog di Fase 1):** `buildPayload` costruisce un payload whitelistato da zero — se non gli si aggiungono `mode`/`objective`/`perimeter`, **un salvataggio dalla SPA riconverte un agente-obiettivo in regola**. È il difetto più probabile di questo task.
- [ ] **Step 4:** `npm test` + `node --check` + `pytest`. **Commit:** `feat(fe): creazione e modifica di un agente in modalita' obiettivo`

---

## Verifica finale & handoff (conferma utente prima di merge)

- [ ] `pytest -q` e `npm test` verdi.
- [ ] **Comportamento invariato per le regole:** un Agentbot esistente non cambia di una virgola (notify non attua; service attua la sua azione dichiarata).
- [ ] Review whole-branch: l'esclusione dei tool che attuano è intatta per ogni modalità; nessun percorso nuovo verso `execute()`; il perimetro è applicato **dove già esisteva** e non da un controllo parallelo; nessuna fiducia progressiva è entrata di straforo.
- [ ] **Live-verify utente:** creare un agente-obiettivo («valuta i consumi»), farlo girare, vedere i task che emette, verificare che un'azione fuori perimetro venga rifiutata e che una in giallo chieda conferma.
- [ ] Conferma esplicita → merge. **Nessun tag.**

## Copertura (self-review)

- Commento di sicurezza falso → Task 1 ✓ (+ test che pinna il comportamento vero)
- Perimetro nello schema → Task 2 ✓ · attribuzione + confinamento dei task → Task 3 ✓
- Objective raggiungibile solo su pianificazione → Task 4 ✓ · budget/scadenza → Task 5 ✓ · FE → Task 6 ✓
- Invariante «niente tool che attuano» → Global Constraints, verificato in review finale ✓
- Nessuna fiducia progressiva → Global Constraints ✓ (è Fase 3, per scelta: si progetta sull'attrito reale)
- Trappola nota `buildPayload` che riconverte objective→rule → Task 6 Step 2 ✓
