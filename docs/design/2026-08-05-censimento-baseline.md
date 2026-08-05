# Censimento — il verbale del punto zero

**Data:** 5 agosto 2026 · **commit:** `bfb781b` (branch `2.0`) · **comando:** `python scripts/censimento.py`

Questo è il numero da cui parte la demolizione del Refactor 2.0. Ogni fetta successiva rilancia lo
stesso comando e si confronta con questo verbale: se il totale sale invece di scendere, la fetta ha
tradito il refactor.

## 1. Il totale

**47 reperti**, così ripartiti:

| Categoria | Reperti |
|---|---|
| Tabelle create e mai toccate | 2 |
| Tabelle scritte e mai lette | 0 |
| Tabelle lette e mai scritte | 0 |
| Opzioni dell'add-on che nessun codice legge | 0 |
| Variabili d'ambiente lette e mai esportate da `run.sh` | 32 |
| Rotte HTTP che nessuno chiama | 0 |
| Rotte HTTP chiamate solo dai test | 5 |
| Funzioni e classi senza alcun chiamante | 1 |
| Funzioni e classi usate solo dai test | 7 |
| **Totale** | **47** |

**La riga di copertura**, perché un reperto senza denominatore non dice niente: lo strumento ha
esaminato **785 nomi su 854 definizioni** trovate in `hiris/app` (132 file, 27.776 righe) — il 92%
dei simboli definibili è stato effettivamente giudicato. Il resto si divide così: 68 saltati perché
definiti in più punti (l'omonimia rende muto il conteggio delle occorrenze — non sono "vivi", sono
"non giudicabili con questo metodo"), 1 punto d'ingresso escluso per costruzione (`main`/`run`/ecc.),
0 file illeggibili. Per confronto, `tests/` pesa 45.856 righe: più dell'applicazione, come dice
`CLAUDE.md`.

## 2. L'elenco completo dei reperti

Così come lo strumento li ha stampati, per categoria.

### Tabelle create e mai toccate (2)

- `entity_correlations` — `hiris/app/proxy/knowledge_db.py:29`
- `query_patterns` — `hiris/app/proxy/knowledge_db.py:38`

### Tabelle scritte e mai lette (0)

Nessuna.

### Tabelle lette e mai scritte (0)

Nessuna.

### Opzioni dell'add-on che nessun codice legge (0)

Nessuna.

### Variabili d'ambiente lette e mai esportate da `run.sh` (32)

Nota comune a tutte: "il codice la legge, `run.sh` non la esporta: è una costante".

- `BRAIN_SUGGEST_CAP` — `hiris/app/server.py:2452`
- `BRAIN_TUNE_CAP` — `hiris/app/server.py:2469`
- `CHATBOTS_DATA_PATH` — `hiris/app/server.py:1286`
- `CHATBOT_RATE_LIMIT_COOLDOWN_SEC` — `hiris/app/chatbot_engine.py:43`
- `CHATBOT_RATE_LIMIT_THRESHOLD` — `hiris/app/chatbot_engine.py:41`
- `CHATBOT_RATE_LIMIT_WINDOW_SEC` — `hiris/app/chatbot_engine.py:42`
- `CHATBOT_RUN_TIMEOUT` — `hiris/app/chatbot_engine.py:31`
- `HA_BASE_URL` — `hiris/app/server.py:1254`
- `HA_LATITUDE` — `hiris/app/tools/weather_tools.py:94`
- `HA_LONGITUDE` — `hiris/app/tools/weather_tools.py:95`
- `HA_NOTIFY_SERVICE` — `hiris/app/server.py:1370`
- `HIRIS_AGENT_CHAT_MODEL` — `hiris/app/agent/runner.py:133`
- `HIRIS_AGENT_CHAT_TOOLS` — `hiris/app/agent/runner.py:56`
- `HIRIS_AGENT_MCP_CONFIG_PATH` — `hiris/app/agent/runner.py:57`
- `HIRIS_AGENT_MCP_URL` — `hiris/app/agent/runner.py:55`
- `HIRIS_AGENT_MODE` — `hiris/app/agent/runner.py:243`
- `HIRIS_AGENT_MODEL` — `hiris/app/agent/runner.py:169`
- `HIRIS_AGENT_POLL_SECONDS` — `hiris/app/agent/runner.py:216`
- `HIRIS_ALLOW_NO_CSRF` — `hiris/app/api/middleware_csrf.py:28`
- `HIRIS_ALLOW_NO_TOKEN` — `hiris/app/api/middleware_internal_auth.py:22`
- `HIRIS_BASE_URL` — `hiris/app/agent/runner.py:242`
- `HIRIS_HEALTH_SCAN_MINUTES` — `hiris/app/server.py:2535`
- `HIRIS_PORTRAIT_OBSERVE_MINUTES` — `hiris/app/server.py:2548`
- `HIRIS_SLUG` — `hiris/app/server.py:1265`
- `HOME` — `hiris/app/agent/runner.py:115`
- `MAX_TOOL_ITERATIONS` — `hiris/app/backends/openai_compat_runner.py:64`
- `OLLAMA_MAX_TOOL_ITERATIONS` — `hiris/app/backends/openai_compat_runner.py:66`
- `PATH` — `hiris/app/agent/runner.py:115`
- `RETROPANEL_URL` — `hiris/app/server.py:1372`
- `SUPERVISOR_TOKEN` — `hiris/app/server.py:1259`
- `TASKS_DATA_PATH` — `hiris/app/server.py:1385`
- `USAGE_DATA_PATH` — `hiris/app/server.py:1448`

Nota di lettura per due voci: `HOME` e `PATH` (`hiris/app/agent/runner.py:115`) non sono opzioni
mancate, sono variabili di sistema che il processo eredita dal sistema operativo — `run.sh` non le
esporta perché non deve, non perché qualcuno le ha dimenticate. La regola dello strumento le cattura
comunque perché è letterale ("il codice legge X, `run.sh` non lo esporta"), e questa è la sua
definizione dichiarata di "costante travestita": qui il travestimento non c'è, ma il reperto resta
corretto da riportare — è la lettura a dover distinguere caso per caso, non lo strumento a doverlo
indovinare.

### Rotte HTTP che nessuno chiama (0)

Nessuna.

### Rotte HTTP chiamate solo dai test (5)

- `/api/brain/reasoning` — `hiris/app/server.py:3017`
- `/api/gateway/policy` — `hiris/app/server.py:2970`
- `/api/health/ha` — `hiris/app/server.py:2949`
- `/api/health/ha/refresh` — `hiris/app/server.py:2950`
- `/api/status` — `hiris/app/server.py:2923`

### Funzioni e classi senza alcun chiamante (1)

- `get_price` — `hiris/app/backends/pricing.py:27`

### Funzioni e classi usate solo dai test (7)

- `_all_events` — `hiris/app/history/store.py:148` (4 occorrenze nei test, nessuna in produzione)
- `_daily` — `hiris/app/history/store.py:266` (3 occorrenze nei test, nessuna in produzione)
- `add_annotation` — `hiris/app/proxy/knowledge_db.py:87` (1 occorrenza nei test, nessuna in produzione)
- `get_tool` — `hiris/app/mcp/tiers.py:135` (4 occorrenze nei test, nessuna in produzione)
- `is_connected` — `hiris/app/mqtt_publisher.py:32` (1 occorrenza nei test, nessuna in produzione)
- `set_killed` — `hiris/app/mcp/guard.py:23` (3 occorrenze nei test, nessuna in produzione)
- `value_for` — `hiris/app/brain/privacy.py:59` (3 occorrenze nei test, nessuna in produzione)

## 3. Conferme e smentite rispetto alla mappa

Ogni riga qui sotto è stata verificata a mano, non trascritta dal prompt che l'ha proposta.

| La mappa afferma | Cosa ha misurato lo strumento | Verdetto |
|---|---|---|
| Tre tabelle create e mai scritte: `entity_correlations`, `query_patterns`, e quella delle annotazioni | **Due**, non tre. `entity_annotations` è viva: scritta in `hiris/app/proxy/knowledge_db.py:90` (`INSERT INTO entity_annotations`, dentro `add_annotation`), letta in `hiris/app/proxy/knowledge_db.py:98` (`SELECT * FROM entity_annotations`, dentro `get_annotations`) | **Sbagliava la mappa** — confermato leggendo il file: la tabella non è morta, è la funzione che la scrive a non avere chiamanti di produzione |
| `add_annotation` non ha chiamanti | **Confermato**: l'unico chiamante nell'intero repo è `tests/test_knowledge_db.py:33`. Nessun file di produzione la nomina | **La mappa aveva ragione** — ma il difetto è della funzione (nessuno la invoca), non della tabella (che invece si legge da `get_annotations`, verosimilmente su dati mai scritti in produzione) |
| Circa 24 variabili d'ambiente lette e mai esportate | **32**, verificate una per una contro l'elenco `export` di `hiris/run.sh` (52 export totali, nessuno dei 32 nomi ci compare) | **La mappa sottostimava** — di 8 voci. Due di queste 32 (`HOME`, `PATH`) sono variabili di sistema ereditate, non opzioni dimenticate: la sostanza della sottostima resta comunque verificata sulle altre 30 |
| 6 rotte HTTP senza chiamanti | **5**, e nessuna delle 5 è senza chiamanti in assoluto: tutte e 5 sono chiamate **solo dai test** (verificato con grep su `hiris/app/static/` — zero riferimenti — e su `tests/` — 30 riferimenti) | **La mappa era vicina ma non esatta**: il numero era 6 invece di 5, e la categoria "nessun chiamante" era imprecisa — sono chiamate, solo non da un frontend |
| 51 opzioni dell'add-on | **51**, confermato contando le foglie del blocco `options:` di `hiris/config.yaml` con la stessa funzione dello strumento | **Combacia esattamente** |
| ...nessuna irraggiungibile dal codice | **Confermato**: 0 reperti in questa categoria. Tutte e 51 passano da `hiris/run.sh` via `bashio::config` (comprese le opzioni condizionali come `execute_api_read_denylist`, esportata solo se presente in `options.json`) | **La mappa e lo strumento non si contraddicono**: l'affermazione della mappa (Parte 3.6, "51 opzioni... dopo il primo giorno se ne usano due") riguarda **l'uso da parte dell'utente**, non la leggibilità dal codice. Sono due misure diverse: questo strumento certifica che il codice le legge tutte; non dice, e non può dire, quante un utente imposti mai |

## 4. Ciò che lo strumento NON vede

Questi restano lavoro di giudizio umano — non per pigrizia dello strumento, ma perché richiedono di
capire *cosa fa* il codice, non solo *se qualcuno lo chiama*. Costruire un rilevatore approssimativo
per queste categorie produrrebbe rumore e farebbe perdere fiducia nel resto del report.

- **I nomi definiti in più punti** (68, dalla riga di copertura): contare le occorrenze di un nome
  omonimo non direbbe niente, quindi lo strumento li salta in blocco. Fra questi possono nascondersi
  sia simboli vivi che orfani — vanno letti a mano.
- **I nomi citati anche come stringa**: possono essere chiamati dinamicamente (il pattern usato da
  `tools/dispatcher.py`). Lo strumento li segnala nella nota, non li condanna.
- **Le opzioni annidate** (`mqtt.host`, `local_model.url`, ecc.) hanno nomi generici e il confronto è
  prudente: preferisce un falso "vivo" a un falso "morto".
- **Le rotte sono indicizzate per percorso, non per metodo**: un `POST` morto su un percorso il cui
  `GET` è vivo non viene visto.
- **Il frontend non viene analizzato**: solo le rotte HTTP che nomina. Le **funzioni JavaScript
  orfane** — inclusi i due editor da 90 KB che la mappa cita alla voce 3.2, o codice morto negli
  altri file `.js` — non sono nel perimetro di questo strumento e restano da cercare a mano.
- **I doppioni divergenti**: la mappa ha trovato tre implementazioni di «batteria scarica»
  (`hiris/app/watcher/detectors.py`, `hiris/app/brain/health_scan.py`, `hiris/app/brain/health_checks.py`,
  più `hiris/app/brain/briefing.py` che rilegge la prima) e tre di «porta aperta». Nessuna regex le
  trova: hanno tutte chiamanti, tutte compilano, tutte "funzionano" — il problema è che fanno la
  stessa cosa con logiche diverse, e questo si vede solo leggendo cosa calcolano, non chi le chiama.
- **Il codice raggiungibile ma inerte perché spento di fabbrica**: la mappa (Parte 2) ha misurato che
  su un'installazione nuova si muovono da sole quattro cose — il semaforo, i rilevatori, la revisione
  olistica e il resto restano spenti dietro interruttori mai accesi o dati che di fabbrica non
  esistono. Un rilevatore di chiamanti non distingue "chiamato" da "chiamato dentro un ramo che non
  si accende mai": una funzione con cento chiamanti tutti dietro un flag spento risulta "viva" quanto
  una che gira davvero.

## 5. Come si usa d'ora in poi

```
python scripts/censimento.py
```

A fine di ogni sviluppo, si rilancia e si confronta il totale con l'ultimo verbale scritto: se scende,
la fetta ha demolito più di quanto ha aggiunto; se sale, va giustificato prima di proseguire — non
dopo.
