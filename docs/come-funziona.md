> ## ⚠️ Documento superato — Refactor 2.0 (4 agosto 2026)
>
> Questo documento descrive HIRIS **prima** del Refactor 2.0. Parla di *Sentinella*, *Agentbot*,
> *semaforo* a quattro colori e di un pannello di configurazione di entità AI: tutte cose che il
> refactor ha mandato in pensione o riscritto.
>
> **Cosa HIRIS deve essere oggi:** [`docs/design/2026-08-04-scope-hiris.md`](design/2026-08-04-scope-hiris.md)
> **Cosa fa oggi il codice:** [`docs/design/2026-08-03-analisi-funzionale.md`](design/2026-08-03-analisi-funzionale.md)
>
> Restano utili le parti puramente operative (installazione, chiavi, opzioni dell'add-on). Sarà
> riscritto come atto finale del refactor, sul prodotto vero.

# HIRIS — Come funziona

> Versione: 1.0.0 · Aggiornato: 2026-07-29

---

## Cos'è HIRIS

**HIRIS** (Home Intelligent Reasoning & Integration System) è un Add-on per Home Assistant che aggiunge un layer di intelligenza artificiale alla smart home. Espone una chat in linguaggio naturale configurata tramite **Chatbot**, ed esegue un livello proattivo — la **Sentinella** — che sorveglia situazioni tarabili built-in ("lenti") e **Agentbot** definiti dall'utente, ragionando su di esse tramite Claude (o OpenAI / Ollama) come motore di ragionamento.

HIRIS **non sostituisce** Home Assistant — si affianca a esso. Le automazioni semplici (luci al tramonto, sveglie) restano nel Layer 1 locale. Il ragionamento complesso, le anomalie, e le domande in linguaggio libero vanno al Layer 2 AI.

---

## Architettura a due livelli

```
┌───────────────────────────────────────────────────────┐
│  LAYER 2 — AI Agentic Loop                            │
│  • Chat in linguaggio naturale (Chatbot)                │
│  • Sentinella: Agentbot (built-in + definiti dall'utente)│
│    (opening, fridge_temp, power, battery,              │
│     hot_and_away, arrival, ...)                         │
│  • Ragionamento multi-sorgente (meteo + energia + HA) │
│  • Memoria e RAG pre-fetch                            │
│  Modello: Claude Sonnet (chat) / Haiku (Sentinella)   │
│  Fallback: OpenAI GPT-4o / Ollama locale              │
└───────────────────────────────────────────────────────┘
          ↕  tool calls
┌───────────────────────────────────────────────────────┐
│  LAYER 1 — Python Flow Engine (locale, offline)       │
│  • Listener WebSocket HA: state_changed (detector)     │
│  • Snapshot periodico: situazioni/arrival               │
│  • Task engine: azioni differite                       │
│  • Semaforo: gate tier + denylist domini pericolosi   │
└───────────────────────────────────────────────────────┘
          ↕  REST + WebSocket
┌───────────────────────────────────────────────────────┐
│  HOME ASSISTANT CORE                                  │
└───────────────────────────────────────────────────────┘
```

---

## Flusso di una richiesta chat

Quando l'utente scrive un messaggio, HIRIS esegue questi passi in sequenza:

### 1. Ricezione e routing

`POST /api/chat` → `handlers_chat.py`

- Legge `{message, chatbot_id}` dal body JSON (accetta anche il legacy `agent_id`, retro-compat)
- Identifica il Chatbot richiesto (o usa `hiris-default`)
- Carica la cronologia della conversazione da SQLite (`chat_history.db`)
- Recupera le memorie rilevanti dallo store vettoriale (RAG injection)

### 2. Costruzione del system prompt

Il system prompt è composto a strati, nell'ordine:

```
[1] strategic_context del Chatbot  ("Sei il controllore della casa Rossi…")
[2] system_prompt del Chatbot      (istruzioni, tool, regole)
[3] --- separatore ---
[4] Semantic Map Snippet           (snapshot live della casa, ~5 righe)
[5] --- separatore ---
[6] Memorie RAG                    (interazioni passate rilevanti, marcate untrusted)
[7] RAG pre-fetch entità           (stati live delle entità rilevanti per questo messaggio)
```

Esempio di system prompt che Claude riceve:

```
Sei HIRIS, assistente per la smart home…

---

CASA [mappa agg. 14:30]
Energia: sensor.potenza_rete(W), sensor.fotovoltaico(W)
Clima: climate.soggiorno(21.5°→22°C heating), climate.camera(20°→21°C idle)
Presenze: PIR Ingresso(off), PIR Salotto(on)
Luci: 18 entità / 5 stanze
Elettrodomestici: switch.lavatrice, switch.lavastoviglie

---

Entità rilevanti (dati in tempo reale):
- Luce Soggiorno [light.soggiorno]: on
- Termostato Salotto [climate.soggiorno]: heat, corrente 21.5°C → setpoint 22°C
- Potenza Rete [sensor.potenza_rete]: 1243 W
```

### 3. Agentic loop (Claude + tool use)

Claude riceve: system prompt + cronologia + messaggio utente.

Claude risponde con una di queste modalità:
- **Testo diretto** → risposta all'utente, fine
- **Tool call** → HIRIS esegue il tool, manda il risultato a Claude, Claude decide di nuovo

Il loop si ripete fino a **10 iterazioni** (protezione da loop infiniti). Claude decide autonomamente quando ha abbastanza informazioni per rispondere.

**Gestione errori API:**
- 429/529 (rate limit): 3 retry con backoff esponenziale (5s → 15s → 45s)
- Tool che fallisce: restituisce `{error: "..."}` invece di lanciare eccezione — Claude vede l'errore e può gestirlo

### 4. Risposta e persistenza

- La risposta torna al frontend come `{response: "...", debug: {tools_called: [...]}}`
- Il turno (utente + assistente) viene scritto atomicamente su SQLite
- I token usati vengono contabilizzati per modello e per Chatbot

---

## I tool disponibili

| Tool | Descrizione |
|---|---|
| `get_entity_states(ids)` | Stato live di specifiche entità HA |
| `get_home_status()` | Snapshot strutturato compatto della casa |
| `get_area_entities()` | Tutte le entità raggruppate per stanza |
| `get_entities_on()` | Tutte le entità attualmente in stato `on` |
| `get_entities_by_domain(domain)` | Entità filtrate per dominio |
| `get_energy_history(days)` | Storico consumi dall'HA History API |
| `get_weather_forecast(hours)` | Previsioni da Open-Meteo (gratis, no chiave) |
| `call_ha_service(domain, service, data)` | Chiama qualsiasi servizio HA (filtrato da `allowed_services`) |
| `send_notification(message, channel)` | Push via HA, Telegram, Apprise (80+ canali) |
| `get_ha_automations()` | Lista automazioni HA |
| `trigger_automation(id)` | Esegue un'automazione HA |
| `toggle_automation(id, enabled)` | Abilita/disabilita un'automazione |
| `get_calendar_events(hours, calendar)` | Eventi calendario HA |
| `set_input_helper(entity_id, value)` | Imposta input_boolean / input_number / input_text |
| `create_task(...)` / `list_tasks()` / `cancel_task(id)` | Gestione task interni |
| `recall_memory(query, k, tags)` | Ricerca memorie passate (similarità vettoriale) |
| `save_memory(content, tags)` | Salva una nuova memoria (solo Chatbot) |
| `http_request(url, method, headers, body)` | Chiamata HTTP verso endpoint approvati |
| `get_ha_health(sections)` | Snapshot salute HA: entità non disponibili, errori integrazioni, log, salute nativa per integrazione, stato add-on e spazio disco dal Supervisor, aggiornamenti disponibili per core/OS/Supervisor/add-on. **Sola lettura**: non avvia, non ferma e non aggiorna nulla |
| `get_advisories(severity)` | Segnalazioni di salute aperte rilevate dal Brain: batterie scariche, entità non disponibili da giorni, automazioni rotte, domini pericolosi lasciati abilitati, entità senza area. Sola lettura: non chiude né archivia una segnalazione |
| `get_logbook(entity_id, hours)` | Cronologia eventi HA: chi ha acceso cosa e quando è cambiato uno stato. Per gli andamenti numerici si usa invece `get_history` |
| `render_template(template)` | Valuta un template Jinja di HA per verificare una condizione al volo. Sola lettura; **solo Chatbot**, escluso dagli agenti autonomi |
| `create_automation_proposal(type, name, description, config, routing_reason)` | Propone una nuova automazione per revisione umana (solo Chatbot) |

---

## Chatbot e Agentbot

Non esiste più un unico concetto di "agente" diviso in tipi (`chat` /
`monitor` / `reactive` / `preventive`) con regole e stati personalizzati.
HIRIS oggi distingue due entità, con comportamento inequivocabile: il
**Chatbot** (conversazionale, a interrogazione) e l'**Agentbot** (autonomo,
a trigger).

### Chatbot — conversazionale

Attivato dall'utente tramite UI (o la card Lovelace). Ogni Chatbot è una
configurazione — system prompt + contesto strategico, scope tool/entità/
servizi, scope memoria (`knowledge_access`), politica chat
(`max_chat_turns`, `require_confirmation`, `response_mode`) — mai uno
scheduling autonomo. Usa Claude Sonnet per la massima qualità di default.

### Agentbot — proattivo (motore Sentinella)

Un set di detector/situazioni **built-in** (tarabili, ciascuno abilitabile
singolarmente con selettore entità + soglie dalla pagina di configurazione
Sentinella: `opening` — apertura prolungata, `fridge_temp` — catena del
freddo, `power` — consumo anomalo, `battery` — batteria scarica,
`hot_and_away` — fa caldo e non c'è nessuno → suggerisce di accendere una
valvola/relè per N minuti, `evening_arrival` — rientro serale → suggerisce
una scena) **più** gli **Agentbot definiti dall'utente** (`/api/agentbots`,
persistiti in `agentbots.json` — nati da una proposta del Brain oppure
creati a mano), ciascuno con il proprio trigger (cron/interval/evento). Un
segnale/trigger sveglia un reasoner LLM single-shot (Claude Haiku di
default, ristretto a tool di sola lettura) che decide se notificare e/o
suggerire un'unica azione a basso rischio, filtrata dal semaforo (tier +
denylist domini pericolosi) prima che venga davvero eseguita. Contratto a
**verdetto** (JSON); niente tool liberi (pilastro di sicurezza).

Esempio della risposta strutturata del reasoner (interna — non una sintassi
da scrivere nel prompt utente):
```json
{"verdict": "anomalia", "severity": "warn", "message": "Consumo anomalo — lavatrice attiva da 3 ore", "action": null}
```

---

## Creazione goal-first ed editor unico (`#/nuovo`)

Chatbot e Agentbot condividono lo stesso editor (stesso kit front-end:
selettore entità, dirty-tracking, guard di navigazione, picker modello) —
non due form separati con logica duplicata. La via di creazione di default
è **goal-first**, su `#/nuovo`:

1. L'utente scrive l'obiettivo in linguaggio naturale (es. "avvisami se il
   garage resta aperto di notte" oppure "un assistente che risponde sui
   consumi").
2. HIRIS **deriva il tipo** (Chatbot o Agentbot) con un'euristica
   deterministica lato client — nessuna chiamata LLM in questo passo. La
   scelta proposta resta sempre modificabile dall'utente prima di
   procedere.
3. Segue una manciata di step guidati specifici per il tipo scelto.
4. Alla conferma, HIRIS crea l'entità (`POST /api/chatbots` o
   `POST /api/agentbots`) e apre subito l'**editor avanzato** completo
   (`#/chatbots/{id}` o `#/agentbots/{id}`) per rifinire prompt, tool,
   permessi, trigger.

Chi preferisce partire subito dall'editor vuoto, senza passare dal
wizard, può farlo da `#/chatbots/new` (Chatbot) o `#/agentbots/new`
(Agentbot) — due percorsi diretti sulla stessa entità, non un alias del
wizard.

Nell'editor Chatbot, lo **scope memoria** (`knowledge_access` — quali
categorie di conoscenza il Chatbot può leggere, se includere dati
sensibili) è configurabile direttamente dalla UI, con la stessa
validazione applicata lato backend — prima andava impostato via API.

---

## La home del Brain (`#/`)

La **Dashboard** (raggiungibile da `#/`) è la home del Brain — il luogo dove HIRIS mostra
in chiaro cosa osserva e ragiona sulla casa, segnala problemi che richiedono intervento,
e raccoglie in un unico posto le azioni proposte per l'approvazione.

### Tre zone

1. **Supervisione casa** — striscia compatta con stato generale: aperture/presenze attuali,
   dispositivi offline, ultimo giro di ragionamento, provider AI attivo.
2. **Stream ragionamenti** — card reverse-cronologiche che mostrano il rationale del Brain:
   "Alle 08:00 ho osservato…" con deduzione e osservazioni correlate. Nessuna nuova
   chiamata LLM — il testo è catturato dal ragionamento già eseguito dalla Sentinella.
3. **Azioni e segnalazioni** — due liste: **Proposte** (automazioni suggerite, approva/rifiuta)
   e **Segnalazioni** (5 check read-only: entità non disponibili, batterie scariche,
   automazioni rotte, domini pericolosi, entità senza area). Le segnalazioni si risolvono
   automaticamente quando il problema scompare; l'utente può anche ackizzarle manualmente.

Dietro le quinte: `brain/health_scan.py` esegue i 5 check e scrive/aggiorna le righe
advisory (`advisory.db`); `brain/feed.py` assembla lo stream unico che la Dashboard
mostra combinando ragionamenti (`brain_reasoning.db`), segnalazioni aperte/ack e
proposte, servito da `GET /api/brain/feed`.

---

## Il layer Modelli (`#/models`)

La pagina **Modelli** (SP-2) è il punto unico in cui l'utente vede e governa quale
provider/modello LLM viene usato dove, senza dover editare variabili d'ambiente o
opzioni add-on. Legge/scrive `GET`/`PUT /api/models/config` (`handlers_models.py`,
persistito in `/data/models_config.json`) e si divide in quattro parti:

1. **Provider attivi** — tutti e 5 i provider (Abbonamento Claude Max, Claude API,
   OpenAI, OpenRouter, Ollama) in ordine fisso, con badge di stato (attivo /
   manca credenziale / disattivo) e, per i provider già credenziati, un picker
   per scegliere il modello di default (`provider_models`).
2. **Catena automatica** — l'ordine di fallback (`chain_order`) usato quando un
   Chatbot o un Agentbot ha `model="auto"`: riordinabile con le frecce, con
   preset che rispecchiano le strategie di `LLMRouter` (`cost_first` /
   `quality_first` / `balanced`).
3. **Assegnazione per entità** — il modello di un Chatbot si imposta
   nell'editor del Chatbot stesso (`PUT /api/chatbots/{id}`); quello del Brain
   si imposta qui (`brain_model` in `models_config.json`, usato dal reasoner
   proattivo/cognitivo quando non è "auto"); quello di un Agentbot rimanda
   all'editor Agentbot (`#/agentbots`, campo `reasoning.model` per-Agentbot).
4. **Embeddings** — riga informativa in sola lettura (provider/modello embedding
   attivo), utile per capire chi alimenta la ricerca vettoriale del second brain.

Implementazione frontend: `static/config/models-route.js`. Nessun segreto (API
key) viene mai restituito dal backend — solo `has_credential: true/false` per
provider.

---

## La Semantic Map

La Semantic Map è il "modello cognitivo" che HIRIS costruisce della casa. Mappa ogni entità HA a un **ruolo semantico** e una **label leggibile**.

### Pipeline di classificazione

```
Entità HA
    │
    ▼
[Regole keyword]  ← _solar, _temp, _motion, _door, domain rules…
    │
    ├─ Match trovato → classificata subito (ms, no LLM)
    │
    └─ No match → coda pending
                    │
                    ▼
            [Batch LLM, 20 entità/chiamata]
                    ├── Ollama locale (se configurato) → gratis, veloce
                    └── Claude (fallback) → preciso
```

La mappa è:
- Costruita al primo avvio (tutte le entità processate)
- Aggiornata in real time quando HA aggiunge nuove entità (`entity_registry_updated`)
- Persistente su `/data/home_semantic_map.json`, ricaricata ai riavvii

---

## LLM Router

`LLMRouter` è il layer di astrazione tra HIRIS e i modelli linguistici.

### Strategy e fallback

```
HIRIS (handlers, chatbots/agentbots)
        │
        ▼
   LLMRouter (strategy: balanced / quality_first / cost_first)
   ├── claude  → ClaudeRunner (Anthropic SDK)
   ├── openai  → OpenAICompatRunner (OpenAI API)
   └── ollama  → OpenAICompatRunner (Ollama locale)
```

Con `model="auto"`:
- **balanced**: Claude → OpenRouter → OpenAI → Ollama
- **quality_first**: Claude → OpenAI → OpenRouter → Ollama
- **cost_first**: Ollama → OpenRouter → OpenAI → Claude

Se il backend primario fallisce, viene tentato automaticamente il successivo nella catena.

---

## Memoria e RAG

HIRIS salva le memorie dei Chatbot in SQLite con ricerca per similarità vettoriale (coseno puro Python — nessuna estensione nativa, compatibile Alpine/ARM).

- `recall_memory(query, k, tags)` — recupera le top-k memorie più simili alla query
- `save_memory(content, tags)` — salva una nuova memoria (solo Chatbot, per sicurezza)
- Le memorie sono marcate come dati non fidati nel system prompt (protezione prompt injection)
- Retention configurabile (default 90 giorni)

---

## Sicurezza e permessi

Ogni Chatbot può essere limitato tramite:

| Campo | Funzione | Esempio |
|---|---|---|
| `allowed_tools` | Whitelist tool utilizzabili | `["get_entity_states", "call_ha_service"]` |
| `allowed_entities` | Glob sugli entity ID accessibili | `["light.*", "climate.soggiorno"]` |
| `allowed_services` | Glob sui servizi chiamabili | `["light.*", "switch.turn_*"]` |
| `allowed_endpoints` | URL approvati per `http_request` | `[{"url": "https://api.example.com", ...}]` |
| `restrict_to_home` | Rifiuta domande off-topic | `true` |
| `require_confirmation` | Istruzione al modello di chiedere "sì/ok" prima di agire. Oggi la chat offre solo strumenti di conoscenza (cerca, guarda, ricorda, richiama): nessuno agisce sulla casa, quindi l'opzione resta configurabile ma non ha al momento alcun effetto osservabile | `true` |
| `knowledge_access` | Scope memoria (dati sensibili, quali kind) | `{"allow_sensitive": false, "kinds": "all"}` |
| `max_chat_turns` | Limita lunghezza conversazione | `20` |

Costi/token restano tracciati per Chatbot (visibili nella UI di
configurazione e via MQTT), ma non esiste più un tetto di budget per
Chatbot né un auto-disable — quel meccanismo è stato ritirato insieme ai
vecchi campi ritirati in Slice 5.

Protezione SSRF su `http_request`: range RFC1918, IPv6 mapped-IPv4, loopback e link-local bloccati. Redirect disabilitati. Risposta cappata a 4KB.

---

## Persistenza su disco

| File | Contenuto |
|---|---|
| `/data/chatbots.json` | Configurazione di tutti i Chatbot |
| `/data/agentbots.json` | Configurazione degli Agentbot definiti dall'utente |
| `/data/usage.json` | Contatori token e costi per Chatbot |
| `/data/home_semantic_map.json` | Classificazione semantica entità HA |
| `/data/chat_history.db` | SQLite: cronologia conversazioni + memorie |
| `/data/ha_health.json` | Snapshot salute HA (HealthMonitor — entità non disponibili, errori integrazioni, aggiornamenti) |
| `/data/proposals.db` | SQLite: proposte automazione con lifecycle (pending → applied/rejected/archived → eliminato) |

Tutti i file vengono scritti atomicamente (temp file + rename o commit SQLite via executor) per resistere ai crash.

---

## Costi e tracciamento

HIRIS traccia ogni richiesta per modello e per Chatbot:

| Modello | Input (1M tok) | Output (1M tok) |
|---|---|---|
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-haiku-4-5 | $0.25 | $1.25 |
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| Ollama (locale) | gratis | gratis |

I dati sono consultabili via `/api/usage` e visibili nella UI di configurazione HIRIS per ogni Chatbot.
