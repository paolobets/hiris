# HIRIS — Generazione config HA (dashboard / script / scene)

**Data:** 2026-07-17
**Stato:** Design approvato — pronto per il piano di implementazione

## Obiettivo

Permettere a HIRIS di **generare artefatti di configurazione Home Assistant** — dashboard
Lovelace ("plance"), script e scene — a partire dal linguaggio naturale, con due percorsi
distinti a seconda dell'origine della richiesta:

- **Da chat HIRIS** → creazione **diretta e immediata** su HA (zero attriti).
- **Da MCP** (Claude esterno via execute-API) → **convalida dell'operatore su HIRIS** tramite
  una pagina di review con anteprima del config; nessuna scrittura finché non approvata.

Questo riproduce e generalizza il modello di fiducia già presente in HIRIS: la chat gira
localmente ed è considerata l'operatore fidato; il gateway MCP passa sempre da un'approvazione.

## Contesto esistente (riuso)

- **Pattern proposta**: [`create_automation_proposal`](../../../hiris/app/tools/proposal_tools.py)
  salva in [`ProposalStore`](../../../hiris/app/proxy/proposal_store.py) (SQLite, stato `pending`),
  con lifecycle (pending→archived→delete) e pagina Proposte. Applicazione reale in
  [`handle_apply_proposal`](../../../hiris/app/api/handlers_proposals.py) che chiama
  `ha_client.create_automation`.
- **Due percorsi già cablati**:
  - *Chat/agent*: Claude gira dentro HIRIS → [`dispatcher.dispatch()`](../../../hiris/app/tools/dispatcher.py),
    nessun semaforo, esecuzione diretta.
  - *MCP*: Claude esterno → [`/api/execute`](../../../hiris/app/api/handlers_execute.py) (gated da
    `internal_token`); le azioni gialle/rosse vengono **intercettate prima del dispatch** e messe in
    attesa tramite [`gateway_pending`](../../../hiris/app/api/handlers_gateway_pending.py).
- **WebSocket HA**: [`ha_client._ws_request(msg_type, extra=...)`](../../../hiris/app/proxy/ha_client.py)
  invia un singolo comando WS con parametri e ritorna il `result`. Necessario per Lovelace
  (le dashboard non rispondono su REST).

## Approccio: routing per origine al confine

Un unico tool `create_ha_config` che, **quando viene dispatchato, scrive subito su HA**. La
differenza chat/MCP non sta dentro il tool ma in **chi lo invoca**:

| Origine | Percorso | Comportamento |
|---|---|---|
| Chat / agent | `dispatcher.dispatch("create_ha_config")` | Scrittura immediata su HA |
| MCP | `/api/execute` **intercetta** `create_ha_config` prima del dispatch | Salva proposta `pending`, ritorna `pending_approval` |

**Proprietà di sicurezza**: da MCP il codice di scrittura non viene mai raggiunto — la review
non è bypassabile. Stessa garanzia del semaforo per `call_ha_service`.

Alternative scartate:
- *Tool separati chat-only / MCP-only*: raddoppia la superficie dei tool.
- *Flag `origin` dentro il dispatcher*: rende il dispatcher origin-aware, sporca il confine pulito.

## Componenti

### 1. Write layer — nuovi metodi in `proxy/ha_client.py`

Stesso stile di `create_automation`: ritornano `{"ok": True, ...}` oppure `{"error": ...}`;
gated a monte (mai chiamati direttamente da MCP).

- `create_script(object_id, config)` → POST `/api/config/script/config/{object_id}` +
  `script.reload`. Ritorna `{"ok": True, "id": object_id}`.
- `create_scene(scene_id, config)` → POST `/api/config/scene/config/{scene_id}` +
  `scene.reload`. Ritorna `{"ok": True, "id": scene_id}`.
- `create_dashboard(url_path, title, config, icon=None, show_in_sidebar=True)` → due comandi WS:
  1. `lovelace/dashboards/create` con `{url_path, title, icon, mode: "storage", show_in_sidebar,
     require_admin: False}`
  2. `lovelace/config/save` con `{url_path, config: {...views...}}`
  Ritorna `{"ok": True, "url_path": url_path}`. La dashboard è **additiva**: nuova voce in
  sidebar, non tocca dashboard esistenti.

Validazione slug (riuso pattern `^[a-z0-9_]+$` per script/scene id; slug con trattini per
`url_path` dashboard), `config` deve essere dict non vuoto, cap dimensione config.

### 2. Tool `create_ha_config`

In `tools/config_tools.py` (nuovo modulo dedicato) + branch nel dispatcher.

Schema:
```
create_ha_config(kind, name, config, url_path?, icon?, show_in_sidebar?)
  kind: "dashboard" | "script" | "scene"
  name: titolo leggibile
  config: dict (config Lovelace per dashboard; config script/scene per gli altri)
```

Branch nel dispatcher: valida `kind` e gli id, poi chiama il metodo `ha_client` corrispondente
→ **scrittura diretta**. È ciò che colpisce il percorso chat/agent.

**Chat-only**: escluso agli agent proattivi/reattivi (come `save_memory`). Va aggiunto
all'insieme dei tool esclusi per gli agent non-chat (`EVALUATION_ONLY_TOOLS` / equivalente) e
NON deve comparire nel set tool degli agent di valutazione.

### 3. Intercept MCP in `api/handlers_execute.py`

Nuovo blocco, prima del dispatch generico (accanto a quelli di `call_ha_service` / `create_task`):

```
if tool == "create_ha_config":
    # mappa kind → type proposta (ha_dashboard / ha_script / ha_scene)
    # salva in ProposalStore come pending, con name/description/config/routing_reason
    # (opzionale) notify all'operatore
    # ritorna {"result": {"status": "pending_approval", "proposal_id": ...}}
```

Aggiunto a `PROPOSE_TOOLS` e `_HARD_EXECUTE_ALLOWED` (sicuro: da MCP crea solo una pending,
mai una scrittura). Nessuna `allowed_services`/tier necessaria perché non è `call_ha_service`.

### 4. `proxy/proposal_store.py` + `api/handlers_proposals.py`

- **ProposalStore**: nessuna modifica schema — `type` è già `TEXT` libero e `config` è JSON.
  I nuovi tipi sono `ha_dashboard`, `ha_script`, `ha_scene`.
- **`handle_apply_proposal`**: aggiungere branch per i 3 tipi, analoghi al branch `ha_automation`
  esistente → chiamano `ha_client.create_script/create_scene/create_dashboard`; marcano
  `applied` **solo se HA accetta** (config rifiutata resta `pending`/ritentabile). Per
  `ha_dashboard` i parametri extra (url_path, icon, show_in_sidebar) sono trasportati dentro
  `config` della proposta o in un sottocampo dedicato.

Riusa lifecycle, `list`, `get`, `reject` senza modifiche.

### 5. UI review — `static/config/proposals.js`

Estendere il rendering per i nuovi `type`: label/icona ("Dashboard", "Script", "Scena") e
anteprima leggibile del `config` (YAML/JSON pretty-print). Pulsanti Approva/Rifiuta invariati
(usano gli endpoint proposte già esistenti). Modifica minima, nessun nuovo endpoint.

### 6. Esposizione tool

- **Chat**: aggiungere la tool-def `create_ha_config` al set tool del runner chat (claude_runner).
- **MCP**: `PROPOSE_TOOLS` + `_HARD_EXECUTE_ALLOWED` (vedi §3).

## Sicurezza

- Da MCP: impossibile scrivere direttamente su HA — solo proposte `pending`, applicate solo
  dopo approvazione esplicita dell'operatore in HIRIS.
- Da chat: scrittura diretta, ma tutti gli artefatti sono **additivi** (nuova dashboard/script/
  scene) e cancellabili a mano; nessuna sovrascrittura di config esistenti in v1.
- Validazione slug/id e config prima di qualsiasi scrittura; cap dimensione.
- Tool escluso agli agent non-chat (proattivi/reattivi restano read-only).

## Fuori scope (v1)

- Modifica/sovrascrittura di dashboard, script o scene esistenti (solo creazione additiva).
- Granularità dashboard diversa da "nuova dashboard intera" (no aggiunta vista/card a dashboard
  esistenti).
- Cambio del flusso automazioni esistente (`create_automation_proposal` resta invariato).
- Notifica iPhone actionable per la review MCP (v1 usa la pagina di review; notifica opzionale
  informativa possibile ma non actionable).

## Test

Specchio della struttura di test esistente:
- `ha_client.create_script` / `create_scene` / `create_dashboard` (mock REST + mock WS).
- Tool `create_ha_config`: validazione kind/slug, chiamata al metodo giusto (percorso chat).
- Intercept execute-API: `create_ha_config` da MCP → salva pending, NON scrive su HA.
- `handle_apply_proposal` per i 3 nuovi tipi: applica solo se HA accetta; resta pending su errore.
- Lifecycle/list invariati coi nuovi tipi.
