# HIRIS — Flusso Funzionale

> Come si comporta HIRIS da quando riceve una richiesta a quando risponde o agisce.
> Versione: 0.3.17 · Aggiornato: 2026-04-24

---

## 1. Richiesta Chat (utente → risposta)

### Fase 1 — Ricezione

L'utente scrive un messaggio nella UI. Il frontend invia:

```
POST /api/chat
{ "message": "Accendi le luci del salotto", "agent_id": "hiris-default" }
```

HIRIS identifica l'agente da usare. Se `agent_id` non viene trovato, cade sull'agente default (`hiris-default`, tipo `chat`).

---

### Fase 2 — Preparazione del contesto

HIRIS costruisce il **system prompt** per Claude in 3 layer distinti, ognuno con politica di caching diversa:

```
[1] BASE_SYSTEM_PROMPT  ← iniettato a runtime da claude_runner.py
    Lista tool disponibili + regole anti-allucinazione
    Uguale per tutti gli agenti — cache_control: ephemeral (90% sconto dopo il primo turno)

[2] Agent prompt  ← strategic_context + system_prompt dell'agente (da agents.json)
    "Sei l'assistente della famiglia Rossi. La casa ha 3 piani..."
    Stabile per agente — cache_control: ephemeral (cacheable se > 1024 token)

[3] context_str  ← SemanticContextMap, calcolata per QUESTA query
    CASA — 5 aree [agg. 14:32]
      Soggiorno: Luce×3 · Termostato
      Bagno: Luce · Termostato · Umidità
    ...
    SOGGIORNO [agg. 14:32]         ← sezione dettaglio (se l'area è menzionata)
      Luce    Lampada angolo   spenta
      Luce    Luce soffitto    accesa 60%
    Varia per query — NON cacheable (cache miss garantito)
```

La **SemanticContextMap** funziona così: HIRIS classifica tutte le entità HA per area e tipo (`climate`, `light`, `door`, ecc.), poi per ogni messaggio utente estrae le aree e i concetti menzionati e inietta solo la sezione pertinente. Claude vede i dati live **prima di chiamare qualsiasi tool**.

Vengono caricati anche gli ultimi **30 messaggi** della cronologia della conversazione. I messaggi più vecchi sono su disco ma non vengono inviati a Claude.

---

### Fase 3 — Agentic loop

Claude riceve: system prompt (3 layer) + storia + messaggio utente.

```
Loop (max 10 iterazioni):

  Claude ragiona...
  │
  ├─ Se risponde con testo → fine, risposta all'utente
  │
  └─ Se chiama un tool:
       HIRIS esegue il tool
       HIRIS manda il risultato a Claude
       Claude ragiona di nuovo...
```

**Esempio concreto** per "Accendi le luci del salotto":

```
Turno 1:
  Claude vede nel context_str che light.soggiorno è "spenta"
  Claude chiama: call_ha_service("light", "turn_on", {"entity_id": "light.soggiorno"})

  HIRIS esegue il servizio HA → true
  HIRIS manda il risultato a Claude

Turno 2:
  Claude risponde: "Ho acceso le luci del salotto."
  → fine loop, risposta all'utente
```

**Esempio con ricerca prima di agire** — "Spegni tutto in cucina":

```
Turno 1:
  Claude chiama: get_area_entities()
  HIRIS restituisce: {"Cucina": ["light.cucina", "light.isola", "switch.cappa"]}

Turno 2:
  Claude chiama: call_ha_service("light", "turn_off", {"entity_id": ["light.cucina", "light.isola"]})
  Claude chiama: call_ha_service("switch", "turn_off", {"entity_id": "switch.cappa"})
  (Claude può fare più tool call nello stesso turno)

Turno 3:
  Claude risponde: "Ho spento le 2 luci e la cappa in cucina."
```

---

### Fase 4 — Filtri di sicurezza

Durante il tool dispatch, HIRIS applica i filtri configurati per l'agente:

**Filtro entità** (`allowed_entities`):
Se l'agente ha `allowed_entities: ["light.*", "climate.soggiorno"]`, Claude non può vedere né controllare `switch.*`, `sensor.*` ecc. Le entità non permesse vengono silenziosamente escluse dai risultati.

**Filtro servizi** (`allowed_services`):
Se l'agente ha `allowed_services: ["light.*"]`, la chiamata a `switch.turn_off` viene bloccata e Claude riceve: `{"error": "Service switch.turn_off not permitted by policy"}`. Claude può decidere di informare l'utente.

**Modalità conferma** (`require_confirmation: true`):
Claude deve chiedere conferma prima di eseguire `call_ha_service`:
```
"Proposta: spegnere light.soggiorno e light.cucina. Confermi? (sì/no)"
```
L'azione viene eseguita solo se il messaggio successivo contiene sì/ok/yes.

**Modalità solo-casa** (`restrict_to_home: true`):
Claude risponde solo a domande relative alla domotica. Per domande fuori ambito:
```
"Non posso aiutarti su questo argomento."
```

---

### Fase 5 — Risposta e salvataggio

La risposta torna al frontend:
```json
{
  "response": "Ho acceso le luci del salotto.",
  "debug": {"tools_called": [{"tool": "call_ha_service", "input": {...}}]}
}
```

Il turno viene salvato nella cronologia (`/data/chat_history_<agent_id>.json`).
I token usati vengono contabilizzati per agente e modello, inclusi i token di cache write/read.

---

## 2. Agenti Automatici

Gli agenti automatici **non aspettano un messaggio utente**: si attivano da soli in base a eventi o schedule.

### Monitor (schedule)

**Trigger:** ogni N minuti (APScheduler).

```
[ogni 15 min]
    │
    ▼
HIRIS costruisce il "messaggio utente" sintetico:
  "[Agent trigger: schedule]
   [CONTESTO ENTITÀ]
   - Potenza rete: 3420 W
   - Fotovoltaico: 0 W
   - Lavatrice: on
   - Soggiorno: on
   ..."
    │
    ▼
Claude ragiona sul contesto
    │
    ├─ Tool call se serve approfondimento
    │   es: get_energy_history(days=1) per vedere la curva di consumo
    │
    └─ Risposta strutturata obbligatoria:
        "Consumo anomalo rilevato: la lavatrice è accesa da 3h,
         potenza rete 3.4kW. Verifica se il ciclo è bloccato.
         VALUTAZIONE: ANOMALIA
         AZIONE: send_notification — allerta lavatrice"
    │
    ▼
HIRIS parsa VALUTAZIONE e AZIONE
HIRIS salva nel log di esecuzione dell'agente
```

Il contesto entità iniettato è filtrato per `allowed_entities` dell'agente — un monitor energetico vede solo i sensori energia, non tutte le entità della casa.

**Risposta strutturata** (solo se l'agente ha `actions` configurate):

```
VALUTAZIONE: [OK | ATTENZIONE | ANOMALIA]
AZIONE: [descrizione azione, o "nessuna azione necessaria"]
```

Queste due righe vengono rimosse dalla risposta visibile e salvate separatamente nel log (campo `eval_status`, `action_taken`).

---

### Reactive (state_changed)

**Trigger:** quando una specifica entità HA cambia stato (WebSocket).

```
HA emette: state_changed → binary_sensor.porta_ingresso → "on"
    │
    ▼
HIRIS intercetta l'evento WebSocket
HIRIS cerca tutti gli agenti reactive con entity_id = binary_sensor.porta_ingresso
    │
    ▼
Agente attivato (asyncio task):
  Messaggio utente sintetico:
    "[Agent trigger: state_changed]
     Context: {entity_id: 'binary_sensor.porta_ingresso', new_state: {state: 'on'}, ...}
     [CONTESTO ENTITÀ]
     ..."
    │
    ▼
Claude ragiona: "La porta d'ingresso si è aperta alle 23:47.
                 Verifico chi è in casa..."
    │
    ├─ Tool: get_entity_states(["binary_sensor.pir_salotto", "device_tracker.telefono_paolo"])
    │
    └─ Azione: send_notification("Porta aperta alle 23:47. PIR salotto: off. Telefono di Paolo: away.")
```

**Nota:** il reactive viene attivato per ogni cambio di stato, inclusi i "flap" (on→off→on rapidi). Va usato con entità che cambiano raramente (porte, presenza, allarmi).

---

### Preventive (cron)

**Trigger:** orario fisso via cron (`"0 7 * * *"` = ogni giorno alle 7:00).

Funziona identicamente al monitor, ma con trigger temporale preciso invece che a intervallo.

```
Ogni giorno alle 07:00:
  "[Agent trigger: preventive]
   [CONTESTO ENTITÀ — meteo + energia]"
    │
    ▼
Claude: "Previsioni di oggi: 18°C, nuvoloso. Consumi ieri: 12 kWh.
         Fotovoltaico produrrà poco oggi. Suggerisco di anticipare
         la lavatrice a questa mattina per usare la tariffa bassa."
    │
    ▼
send_notification(...)
```

---

## 3. Selezione automatica del modello

HIRIS sceglie il modello Claude in base al tipo di agente:

| Tipo agente | Modello usato | Motivazione |
|---|---|---|
| `chat` | claude-sonnet-4-6 | Massima qualità, conversazione libera |
| `monitor` | claude-haiku-4-5 | Gira ogni N minuti: economico, veloce |
| `reactive` | claude-haiku-4-5 | Si attiva spesso: basso costo per evento |
| `preventive` | claude-haiku-4-5 | Analisi giornaliera: qualità sufficiente |

Se l'agente ha `model: "claude-sonnet-4-6"` esplicitamente, viene usato quello. `model: "auto"` (default) usa la tabella sopra.

---

## 4. Gestione del budget

Ogni agente può avere un limite di spesa in euro (`budget_eur_limit`).

Dopo ogni esecuzione:
```
costo_run = (input_tokens * prezzo_input + output_tokens * prezzo_output) / 1_000_000
            + (cache_write_tokens * prezzo_cache_write) / 1_000_000
            + (cache_read_tokens  * prezzo_cache_read)  / 1_000_000
costo_totale_eur = somma_storica_costo_usd * 0.92

se costo_totale_eur >= budget_eur_limit:
    agent.enabled = False   ← si auto-disabilita
    log: "Agent X auto-disabled: cost €0.35 >= limit €0.30"
```

L'agente smette di girare finché non viene riabilitato manualmente.

---

## 5. Retry e gestione errori

**Rate limit API (HTTP 429/529):**
```
Tentativo 1 → fallisce → attesa 5s
Tentativo 2 → fallisce → attesa 15s
Tentativo 3 → fallisce → attesa 45s
Tentativo 4 → fallisce → errore propagato
```

**Tool che fallisce:**
Il tool non lancia eccezione — restituisce `{"error": "messaggio"}`. Claude riceve l'errore nel contesto e può:
- Informare l'utente
- Provare un approccio alternativo
- Procedere con le informazioni disponibili

**Loop infinito di tool:** il loop si ferma dopo 10 iterazioni e restituisce `"Max tool iterations reached."`.

**Disconnessione WebSocket HA:** riconnessione automatica ogni 10 secondi.

---

## 6. Cosa vede Claude nel contesto

Riepilogo di tutto quello che Claude riceve per un turno di chat (v0.3.17):

```
SYSTEM PROMPT (3 blocchi separati, caching indipendente):
┌─────────────────────────────────────────────────────────────┐
│ [BASE_SYSTEM_PROMPT]           ← cache_control: ephemeral   │
│ Tool disponibili: get_home_status(), get_area_entities()...  │
│ Regole: usa sempre i tool, non dichiarare azioni mai fatte   │
│                                                              │
│ [agent prompt]                 ← cache_control: ephemeral   │
│ strategic_context: "Sei l'assistente della famiglia Rossi..." │
│ system_prompt: "Analizza i consumi..."                       │
│                                                              │
│ [context_str]                  ← NO cache (dinamico)        │
│ CASA — 5 aree [agg. 14:32]                                   │
│   Soggiorno: Luce×3 · Termostato                             │
│   Bagno: Termostato · Umidità                                │
│ SOGGIORNO [agg. 14:32]         ← dettaglio se area menzionata│
│   Luce    Lampada angolo   spenta                            │
│   Luce    Luce soffitto    accesa 60%                        │
└─────────────────────────────────────────────────────────────┘

MESSAGES (ultimi 30):
[{"role": "user",      "content": "Buongiorno, com'è il meteo oggi?"},
 {"role": "assistant", "content": "Buongiorno! Verifico subito..."},
 ...
 {"role": "user",      "content": "Accendi le luci del salotto"}]   ← messaggio corrente
```

Per gli agenti automatici il "messaggio utente" è sintetico:
```
[Agent trigger: schedule]

[CONTESTO ENTITÀ]
- Potenza rete: 3420 W
- Lavatrice: on
...
```

---

## 7. Log di esecuzione agenti

Ogni run di un agente automatico viene loggato (ultimi 20):

```json
{
  "timestamp": "2026-04-24T14:30:00Z",
  "trigger": "schedule",
  "tool_calls": ["get_energy_history", "send_notification"],
  "input_tokens": 1243,
  "output_tokens": 187,
  "result_summary": "Consumo anomalo rilevato: la lavatrice è accesa da 3h...",
  "success": true,
  "eval_status": "ANOMALIA",
  "action_taken": "Notifica inviata — allerta lavatrice"
}
```

Il log è consultabile via `GET /api/agents/{id}` nel campo `execution_log`.

---

## 8. Memoria conversazionale (roadmap v0.4.x)

### Situazione attuale (v0.3.x)

La storia chat è salvata su file JSON (`/data/chat_history_<agent_id>.json`) senza limite di lunghezza, ma **solo gli ultimi 30 messaggi** vengono inviati a Claude per tenere il contesto bounded. Al riavvio del container Docker l'add-on riparte ma la storia è già persistita su disco — quindi sopravvive ai restart.

**Limite attuale:** nessun riassunto automatico delle sessioni passate. Conversazioni molto lunghe (>30 turni) perdono i turni più vecchi nel contesto di Claude, anche se rimangono su disco.

### Piano (v0.4.x)

Migrazione da JSON a **SQLite** con schema:

```sql
CREATE TABLE chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    role        TEXT NOT NULL,           -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    token_count INTEGER,
    session_id  TEXT                     -- per raggruppare sessioni distinte
);
CREATE TABLE chat_summaries (
    agent_id    TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    summary     TEXT NOT NULL,           -- riassunto Claude dei messaggi vecchi
    covered_up_to INTEGER NOT NULL,      -- id dell'ultimo messaggio riassunto
    created_at  TEXT NOT NULL
);
```

**Strategia di finestra contestuale:**

```
Storia completa (SQLite, illimitata)
    │
    ├─ Ultimi 30 messaggi → inviati a Claude (conversazione corrente)
    │
    └─ Messaggi più vecchi → riassunti in batch da Claude → summary iniettato nel system prompt
                              "Nelle sessioni precedenti: hai gestito l'irrigazione il 20/04,
                               hai rilevato anomalia lavatrice il 22/04..."
```

**Caching messaggi stabili:**
I messaggi conversation più vecchi di 5 minuti sono invariabili → possono ricevere `cache_control: ephemeral` (terzo strato di caching dopo BASE + agent prompt). Risparmio stimato: ~40% sui token di storia per conversazioni attive.

---

## 9. Tool aggiuntivi (roadmap v0.4.x)

I tool attuali coprono il controllo HA e le notifiche base. Il piano aggiunge integrazioni esterne che ampliano le capacità di ragionamento e azione di Claude.

### `send_email(to, subject, body, attachments?)`

**Canale:** SMTP configurato nelle opzioni add-on.

```python
# Configurazione (config.yaml options):
smtp_host: "smtp.gmail.com"
smtp_port: 587
smtp_user: "casa@gmail.com"
smtp_password: ""   # encrypted by HA Supervisor

# Uso tipico (agente preventive):
# "Manda report energetico settimanale ogni lunedì alle 8:00"
# → Claude genera il testo, chiama send_email con il riepilogo
```

**Caso d'uso principale:** report periodici (consumi settimanali, sommario presenze, alert aggregati), digest per chi non usa Telegram.

---

### `http_request(url, method, headers?, body?, timeout?)`

**Integrazioni esterne via HTTP** — qualsiasi API REST.

```python
# Esempi:
# Leggi prezzo energia in tempo reale (GME spot):
http_request("https://api.energia.example.it/spot-price", "GET")

# Invia dato a dashboard esterna:
http_request("https://mia-dashboard.local/api/update", "POST",
             body={"sensor": "climate.soggiorno", "value": 21.5})

# Trigger webhook n8n / Make / Home Assistant:
http_request("https://hook.eu1.make.com/xyz", "POST", body={"event": "anomalia_energia"})
```

**Sicurezza:** lista URL permessi configurabile per agente (`allowed_urls`), stesso modello di `allowed_services`. URL non in lista → errore bloccato prima della chiamata HTTP.

---

### `get_calendar_events(days, calendar_id?)`

**Sorgente:** HA calendario (integrazione Google Calendar / CalDAV già presente in HA).

```python
# Esempio risposta:
[
  {"summary": "Rientro Paolo", "start": "2026-04-25T18:00:00", "end": "..."},
  {"summary": "Ospiti a cena", "start": "2026-04-26T20:00:00", "end": "..."},
]

# Uso tipico (agente preventive mattutino):
# Claude legge il calendario + meteo + consumi → decide se pre-riscaldare,
# se preparare l'irrigazione, se inviare reminder
```

**Integrazione con HA:** usa il servizio `calendar.get_events` già esposto dall'integrazione HA calendario, senza bisogno di token Google aggiuntivi.

---

### `set_input_helper(entity_id, value)`

Scrive su `input_boolean`, `input_number`, `input_text`, `input_select` — entità HA usate come variabili di stato condivise tra HIRIS e le automazioni HA esistenti.

```python
# Pattern: HIRIS decide, HA esegue via automazione già configurata
set_input_helper("input_boolean.modalita_notte", True)
# → l'automazione HA "Modalità notte" si attiva e spegne tutto

set_input_helper("input_number.temperatura_target_soggiorno", 21.5)
# → l'automazione HA aggiorna il termostato
```

**Valore:** permette a HIRIS di collaborare con le automazioni HA esistenti senza doverle reimplementare come tool.

---

## 10. Roadmap implementativa

| Versione | Contenuto | Stato |
|---|---|---|
| v0.3.x | Phase 1 completa: SemanticContextMap, task engine, caching, budget, execution log | ✅ rilasciato |
| v0.4.0 | Memoria conversazionale SQLite + finestra contestuale dinamica | pianificato |
| v0.4.1 | Tool aggiuntivi: `send_email`, `http_request` | pianificato |
| v0.4.2 | Tool aggiuntivi: `get_calendar_events`, `set_input_helper` | pianificato |
| v0.5.x | Integrazione Retro Panel (plugin embedded, chat nel kiosk) | futuro |
| v1.0 | Canvas drag-and-drop designer, HACS distribution | futuro |

**Prossimi passi immediati (pre-v0.4.0):**

1. **Conversation history caching** — `cache_control: ephemeral` sui messaggi più vecchi di 5 min (terzo strato, nessuna modifica architetturale)
2. **HA area discovery** — popolamento automatico SemanticContextMap da HA area registry al boot
3. **UI agent designer** — token counter live, anteprima context_str prima del salvataggio
4. **Onboarding wizard** — prima apertura: guida creazione primo agente con template
