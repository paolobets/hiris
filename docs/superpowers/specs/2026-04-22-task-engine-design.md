# TaskEngine Design

> **Versione:** 1.0 · **Data:** 2026-04-22

## Goal

Aggiungere a HIRIS un sistema di task differite condiviso tra tutti i tipi di agente (chat, monitor, reactive, preventive). Claude crea task tramite tool call; HIRIS le esegue direttamente al trigger senza ripassare per Claude. Le task sopravvivono ai restart. Le task completate/fallite/cancellate vengono ripulite dopo 24 ore.

---

## Trigger supportati

### 1. `at_time` — orario fisso oggi
```json
{"type": "at_time", "time": "18:00"}
```
Se l'orario è già passato per oggi, la task viene schedulata per il giorno dopo.

### 2. `delay` — ritardo da adesso
```json
{"type": "delay", "minutes": 30}
```

### 3. `at_datetime` — data e ora assoluta
```json
{"type": "at_datetime", "datetime": "2026-04-23T18:00:00"}
```
Usato principalmente dalle task create da un'altra task (catene).

### 4. `time_window` — finestra oraria + polling su entità
```json
{
  "type": "time_window",
  "from": "18:00",
  "to": "20:00",
  "check_interval_minutes": 5
}
```
HIRIS controlla la condizione ogni N minuti nella finestra. Quando la condizione è soddisfatta, esegue le azioni e disattiva il job. Se la finestra scade senza soddisfazione, la task passa a `expired`.

---

## Condizione opzionale (evaluata al trigger)

```json
{"entity_id": "sensor.temperatura_bagno", "operator": "<", "value": 19}
```

Operatori supportati: `<`, `<=`, `>`, `>=`, `=`, `!=`

Il valore dell'entità viene letto da `EntityCache` al momento del trigger. Se la condizione non è soddisfatta, la task viene marcata `skipped` (non riprovata, non errore).

---

## Tipi di azione

### `call_ha_service`
```json
{
  "type": "call_ha_service",
  "domain": "climate",
  "service": "set_hvac_mode",
  "data": {"entity_id": "climate.bagno", "hvac_mode": "heat"}
}
```

### `send_notification`
```json
{
  "type": "send_notification",
  "message": "Ho acceso il termostato del bagno (17.2°C)",
  "channel": "ha_push"
}
```

### `create_task` — catena
```json
{
  "type": "create_task",
  "task": {
    "label": "Verifica termostato dopo 1h",
    "trigger": {"type": "delay", "minutes": 60},
    "condition": {"entity_id": "climate.bagno", "operator": "=", "value": "off"},
    "actions": [
      {"type": "send_notification", "message": "Termostato ancora spento dopo 1h", "channel": "ha_push"}
    ]
  }
}
```

La task figlia eredita `agent_id` del genitore e ha `parent_task_id` impostato.

---

## Modello Task

```python
@dataclass
class Task:
    id: str                      # uuid4
    label: str                   # descrizione leggibile
    agent_id: str                # agente che l'ha creata
    created_at: str              # ISO 8601 UTC
    trigger: dict                # vedi sopra
    actions: list[dict]          # lista azioni in sequenza
    condition: dict | None       # condizione opzionale
    one_shot: bool = True        # True → rimuovi dai pending dopo esecuzione
    status: str = "pending"      # pending | running | done | skipped | failed | expired | cancelled
    executed_at: str | None = None
    result: str | None = None    # testo riassuntivo dell'esecuzione
    error: str | None = None
    parent_task_id: str | None = None
```

---

## Ciclo di vita di una task

```
         create_task()
               │
               ▼
           [pending]
               │
    trigger time / condition met
               │
               ▼
           [running]
          /    |    \
         /     |     \
      [done] [skipped] [failed]
      [expired]
               │
     dopo 24h → cleanup automatico
```

---

## TaskEngine (nuovo servizio)

### Responsabilità

- Caricare task da disco all'avvio e rischedulare i job `pending`
- Registrare job APScheduler per trigger `at_time`, `delay`, `at_datetime`
- Registrare job APScheduler per polling `time_window`
- Eseguire le azioni in sequenza senza invocare Claude
- Persistere ogni cambio di stato su disco (atomic write con `.tmp`)
- Cleanup periodico (ogni ora) delle task con `executed_at` > 24h

### Persistenza

`/data/tasks.json`:
```json
{
  "schema_version": 1,
  "tasks": [...]
}
```

### Esecuzione delle azioni

Le azioni vengono eseguite in sequenza. Se un'azione fallisce, la task passa a `failed` e le azioni successive non vengono eseguite. Il campo `error` contiene il messaggio dell'errore.

Le azioni `call_ha_service` e `send_notification` chiamano direttamente il codice esistente (nessun costo Claude).

Le azioni `create_task` creano la task figlia nel `TaskEngine` con i campi ereditati.

---

## Tool Claude (disponibili a tutti gli agenti)

### `create_task`

```python
{
    "name": "create_task",
    "description": "Schedula una task futura con trigger, condizione opzionale e lista di azioni. Restituisce l'id della task creata.",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Descrizione leggibile della task"},
            "trigger": {"type": "object", "description": "Trigger: {type, time?, minutes?, datetime?, from?, to?, check_interval_minutes?}"},
            "actions": {"type": "array", "description": "Lista di azioni da eseguire in sequenza"},
            "condition": {"type": "object", "description": "Condizione opzionale da verificare al trigger: {entity_id, operator, value}"},
            "one_shot": {"type": "boolean", "default": True}
        },
        "required": ["label", "trigger", "actions"]
    }
}
```

### `list_tasks`

```python
{
    "name": "list_tasks",
    "description": "Elenca le task attive (pending, running) e le recenti (done/failed/skipped nelle ultime 24h).",
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Filtra per agente (opzionale)"},
            "status": {"type": "string", "description": "Filtra per stato (opzionale)"}
        }
    }
}
```

### `cancel_task`

```python
{
    "name": "cancel_task",
    "description": "Cancella una task pending. Restituisce errore se la task è già in esecuzione o completata.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"}
        },
        "required": ["task_id"]
    }
}
```

---

## API REST

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/api/tasks` | `GET` | Lista tutte le task (non ancora pulite) |
| `/api/tasks/{id}` | `GET` | Dettaglio task |
| `/api/tasks/{id}` | `DELETE` | Cancella task pending |

Nessun endpoint `POST /api/tasks` — la creazione avviene solo tramite Claude tool o task chain.

---

## UI — sezione "Task"

Nuova tab nella Config UI (o sezione separata nell'index) con:

- **Task attive** (status: pending, running) — label, agente, trigger, azioni, pulsante Annulla
- **Task recenti** (status: done, skipped, failed, expired nelle ultime 24h) — label, esito, timestamp esecuzione, risultato/errore
- Aggiornamento automatico ogni 30 secondi (polling `GET /api/tasks`)
- Badge con conteggio task pending nell'header

---

## Integrazione con gli agenti

`create_task`, `list_tasks`, `cancel_task` vengono aggiunti alla lista tool globale disponibile in `ClaudeRunner`. Il filtro `allowed_tools` per agente si applica normalmente — un agente che non ha `create_task` in `allowed_tools` non può creare task.

Il `DEFAULT_AGENT_ID` (hiris-default) avrà tutti e tre i tool abilitati di default.

---

## Cleanup

Il cleanup viene eseguito:
- All'avvio del `TaskEngine` (una volta)
- Ogni ora tramite job APScheduler

Criteri: `status in {done, skipped, failed, expired, cancelled}` AND `executed_at` (o `created_at` per cancelled) è più vecchio di 24h.

---

## Scenari di esempio

### Chat: termostato condizionale
```
Utente: "Alle 18 accendi il termostato del bagno solo se la temperatura è sotto 19°"

Claude chiama:
create_task(
  label="Termostato bagno alle 18 (condizionale)",
  trigger={"type": "at_time", "time": "18:00"},
  condition={"entity_id": "sensor.temperatura_bagno", "operator": "<", "value": 19},
  actions=[
    {"type": "call_ha_service", "domain": "climate", "service": "set_hvac_mode",
     "data": {"entity_id": "climate.bagno", "hvac_mode": "heat"}},
    {"type": "send_notification", "message": "Termostato bagno acceso (condizione soddisfatta)", "channel": "ha_push"}
  ]
)

Claude risponde: "Perfetto, ho schedulato l'azione per le 18:00. Verificherò la temperatura
                  prima di agire — se supera 19° non farò nulla."
```

### Monitor: catena di follow-up
```
Monitor energetico rileva lavatrice accesa da 3h:
→ send_notification("Lavatrice accesa da 3h — possibile blocco")
→ create_task(
     label="Verifica lavatrice dopo 1h",
     trigger={"type": "delay", "minutes": 60},
     condition={"entity_id": "switch.lavatrice", "operator": "=", "value": "on"},
     actions=[{"type": "send_notification", "message": "Lavatrice ancora accesa dopo 4h!", "channel": "ha_push"}]
   )
```

### Reactive: finestra temporale
```
Utente via chat: "Tra le 18 e le 20, se c'è movimento in salotto, accendi le luci"

Claude chiama:
create_task(
  label="Luci salotto su movimento (18-20)",
  trigger={"type": "time_window", "from": "18:00", "to": "20:00", "check_interval_minutes": 1},
  condition={"entity_id": "binary_sensor.pir_salotto", "operator": "=", "value": "on"},
  actions=[{"type": "call_ha_service", "domain": "light", "service": "turn_on",
            "data": {"entity_id": "light.soggiorno"}}]
)
```

---

## File da creare/modificare

| File | Operazione |
|---|---|
| `hiris/app/task_engine.py` | Nuovo — `Task` dataclass, `TaskEngine` |
| `hiris/app/tools/task_tools.py` | Nuovo — `create_task`, `list_tasks`, `cancel_task` tool definitions |
| `hiris/app/api/handlers_tasks.py` | Nuovo — `GET /api/tasks`, `GET /api/tasks/{id}`, `DELETE /api/tasks/{id}` |
| `hiris/app/server.py` | Modifica — startup wiring TaskEngine, nuove route |
| `hiris/app/claude_runner.py` | Modifica — aggiungere 3 tool task al dispatcher |
| `hiris/app/static/index.html` | Modifica — sezione/tab Task con lista e badge |
| `tests/test_task_engine.py` | Nuovo — unit test TaskEngine |
| `tests/test_api_tasks.py` | Nuovo — integration test API task |
