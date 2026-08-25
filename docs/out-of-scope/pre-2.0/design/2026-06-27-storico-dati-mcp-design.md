# HIRIS — Dati storici accessibili via MCP — Design

**Data:** 2026-06-27
**Stato:** approvato (brainstorming), pronto per piano implementativo
**Autore:** Paolo Bets + Claude

## Problema

Da Claude/MCP è possibile leggere solo lo **snapshot corrente** delle entità
(`get_home_status`, `get_entity_states`, `get_area_entities`). Non esiste alcuno
strumento per accedere ai **dati storici/time-series**: Claude non può analizzare
trend (temperature dell'ultima settimana, consumi del mese, pattern di presenza,
durate di irrigazione). Internamente HIRIS ha solo `get_energy_history` (energia,
compresso) e il mattone base `ha.get_history()` (recorder HA, ~10 giorni), nessuno
dei due esposto al gateway.

## Obiettivo

Rendere i dati storici accessibili via MCP per analisi da parte di Claude, con un
modello **ibrido** che combina ciò che Home Assistant già conserva con un archivio
storico di proprietà di HIRIS per ciò che HA scarta. Predisporre (senza ancora
implementare) un job schedulato che distilli lo storico in insight per il
*second brain* (KnowledgeStore).

## Decisioni di scope (dal brainstorming)

- **Ambizione storage: ibrido.** HIRIS legge HA per recente + trend numerici lunghi,
  e possiede un proprio store solo per ciò che HA non conserva a lungo.
- **Domini prioritari:** presenza & sicurezza, clima & comfort, energia, irrigazione,
  entità che regolano dispositivi della vita quotidiana — **e la selezione di cosa
  storicizzare deve essere configurabile da UI**, non hardcoded.
- **Second brain:** job di alimentazione **rimandato a Fase 3**; lo store va però
  progettato per renderlo facile.

## Architettura — tre layer dietro un'unica interfaccia

| Layer | Fonte | Copertura | Granularità |
|---|---|---|---|
| Recente generico | HA recorder (`/api/history`, REST già presente) | ~10 gg (retention HA) | ogni cambio stato |
| Trend lunghi numerici | HA Long-Term Statistics (WS `recorder/statistics_during_period`) | mesi/anni | oraria/giornaliera, solo sensori *measurement* |
| Storico proprietario | nuovo `HistoryStore` (SQLite locale) | illimitato | eventi delle entità *selezionate* che HA non tiene |

I primi due layer **leggono HA** (zero storage HIRIS). Il terzo è proprietà di HIRIS
e serve solo per ciò che HA scarta dopo ~10 giorni (binary_sensor, presenza, porte,
valvole/irrigazione, switch on/off, ecc.).

### Componenti

| Componente | Tipo | Ruolo |
|---|---|---|
| `proxy/ha_client.py` | modifica | `get_statistics(ids, period, start, end)` via `_ws_call("recorder/statistics_during_period")`. `get_history` (recorder) già presente. |
| `history/store.py` | nuovo | `HistoryStore` SQLite in `/data/history.db`, separato dal KnowledgeStore (semantico). |
| `history/capture.py` | nuovo | loop di cattura agganciato al WS esistente; ascolta `state_changed`, filtra alle entità selezionate, scrive eventi + rollup giornaliero. |
| `tools/history_tools.py` | nuovo | tool MCP unificato `get_history` + routing ai tre layer + compressione output. |
| `tools/dispatcher.py` | modifica | dispatch `get_history` (tier READ). |
| `api/handlers_history_policy.py` | nuovo | `/api/history/policy` GET/POST (cosa storicizzare, retention). |
| `api/handlers_gateway_policy.py` | modifica | `get_history` aggiunto a `READ_TOOLS`. |
| gateway `app/tiers.py` | modifica | `ToolDef("get_history", Tier.READ, "get_history", …)` nel catalogo MCP. |
| Config SPA | nuovo | pagina "Storicizzazione" (config.html + route + JS). |

### Flusso dati — lettura

```
Claude → MCP get_history(ids, days, resolution)
  → gateway (READ, no semaforo) → HIRIS /api/execute → dispatcher
    → routing:
        recente/raw           → ha_client.get_history (recorder REST)
        trend lungo numerico  → ha_client.get_statistics (WS LTS)
        selezionate non-meas. → HistoryStore (SQLite locale)
    → output compresso uniforme → Claude
```

### Flusso dati — cattura (Fase 2)

```
HA WS state_changed ─(loop esistente)→ capture.py
  → se entity ∈ policy storicizzazione → HistoryStore.append(evento)
  → job periodico → rollup giornaliero + retention (prune raw vecchi)
```

### Isolamento

I tre layer stanno dietro l'unica interfaccia `get_history`: Claude non sa quale
fonte risponde. `HistoryStore` non conosce HA né MCP (riceve eventi, risponde a
query). `capture` non conosce MCP (scrive soltanto). Ogni unità è testabile da sola.

## Interfaccia del tool MCP

```
get_history(
  entity_ids: list[str],          # 1..20 entità
  days: int = 7,                  # 1..365
  resolution: "auto"|"raw"|"hourly"|"daily" = "auto"
) -> list[per-entity series]
```

**Routing interno (trasparente a Claude):**
- `resolution=raw` oppure `days ≤ recorder_window` (~10) → HA recorder.
- entità *measurement* (temp/umidità/potenza/energia) e `days` oltre la finestra
  recorder → HA statistics (hourly/daily).
- entità presente nella policy di storicizzazione → HistoryStore (anche oltre i 10 gg).
- `auto` sceglie la risoluzione più grossa che copre il range richiesto (token-saving).

> `recorder_window` non è interrogabile in modo affidabile da HA: è una **costante
> configurabile** (default 10 giorni, opzione add-on) usata solo come soglia di
> routing. Se una query supera la finestra ma l'entità non ha né statistics né
> HistoryStore, `get_history` restituisce ciò che il recorder ha **più** una nota
> esplicita di copertura parziale (mai un risultato silenziosamente troncato).

**Output uniforme e compresso** (mai serie raw illimitate: cap sui punti, poi
downsampling):

```jsonc
// numerico (temp/energia) aggregato
{ "id": "sensor.temp_salotto", "unit": "°C", "resolution": "daily",
  "buckets": [ {"t":"2026-06-20","min":19.1,"max":24.3,"mean":21.6,"n":288}, … ] }

// on/off (presenza/irrigazione) da HistoryStore
{ "id": "binary_sensor.movimento_ingresso", "resolution": "daily",
  "buckets": [ {"t":"2026-06-20","on_seconds":4120,"transitions":37}, … ] }
```

Claude riceve già min/max/media/durate, non migliaia di punti.

## Schema HistoryStore (SQLite, `/data/history.db`)

```sql
-- eventi grezzi (solo entità selezionate, finestra retention)
CREATE TABLE history_events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL,
  ts        TEXT NOT NULL,          -- ISO UTC
  state     TEXT NOT NULL,
  num       REAL                    -- valore numerico se parsabile (NULL altrimenti)
);
CREATE INDEX idx_he_eid_ts ON history_events(entity_id, ts);

-- rollup giornaliero (sopravvive alla potatura dei grezzi → orizzonte illimitato)
CREATE TABLE history_daily (
  entity_id   TEXT NOT NULL,
  day         TEXT NOT NULL,         -- YYYY-MM-DD
  n           INTEGER NOT NULL,
  min REAL, max REAL, mean REAL,     -- per numerici
  on_seconds  REAL, transitions INTEGER,  -- per on/off
  last_state  TEXT,
  PRIMARY KEY (entity_id, day)
);
```

**Retention/compaction:** i grezzi si tengono N giorni (default 90, configurabile);
un job notturno produce `history_daily` e pota i grezzi più vecchi. Il rollup
giornaliero resta per sempre (≈1 riga/entità/giorno) → analisi mensili/annuali senza
far esplodere il DB.

**Natura numerica vs stato:** il parsing di `num` permette di trattare a runtime un
sensore come numerico (min/max/media) o come stato (durate on/off) a seconda del
valore — non hardcoded.

## Pagina config "Storicizzazione"

Riuso del pattern `gateway_policy.json` → nuovo `history_policy.json`, nuova voce nav
in Configurazione.

```jsonc
{
  "version": 1,
  "domains": { "binary_sensor": true, "climate": true, "valve": true,
               "sensor": true, "switch": false },        // toggle per categoria
  "entities": ["valve.irrigazione_giardino", "sensor.temp_cantina"], // allowlist puntuale
  "exclude": ["sensor.uptime", "sensor.date"],            // rumore escluso
  "retention_days": 90
}
```

**UI:** lista categorie con toggle Storicizza on/off + conteggio entità live (come il
semaforo), textarea per entità puntuali extra, textarea per esclusioni, campo
retention. Granularità: **per-dominio + allowlist/exclude puntuale**.

**Default sicuro:** policy vuota → **nessuna cattura** (store vuoto, opt-in esplicito).

## Sicurezza

- `get_history` è **tier READ** → fuori dal semaforo; con il fix v0.14.9 le letture
  ignorano il whitelist azioni (vede tutte le entità).
- `/api/history/policy` dietro `internal_auth_middleware` + CSRF, come il resto.
- `history.db` è **locale** in `/data`, mai verso il cloud.
- Dati di **presenza/sicurezza** sono privacy-sensibili: restano locali, l'utente può
  escluderli dalla storicizzazione e/o dalle letture. Cattura **opt-in**.
- Cap su `entity_ids` (≤20) e `days` (≤365) per evitare query abusive/loop; il circuit
  breaker del gateway resta a monte.

## Fasi (ognuna rilasciabile e testata da sola)

- **Fase 1** — `get_history` su HA recorder + statistics, esposto via MCP. Sblocca
  subito analisi temperature/energia/recente. Nessuno store, nessuna config.
- **Fase 2** — `HistoryStore` + `capture` + pagina "Storicizzazione"; `get_history`
  instrada anche al locale.
- **Fase 3** — job notturno di distillazione → KnowledgeStore: insight testuali
  ("a maggio consumo +12%", "salotto <19°C mattine feriali"), non numeri grezzi.
  Riuso TaskEngine; rispetta pseudonymizer/sensitivity.

## Test

- **Unit:** routing di `get_history` (quale layer per quale range); parsing/aggregazione
  delle statistics WS; `HistoryStore` append/rollup/retention/query; cap+downsampling
  output.
- **Handler:** `/api/history/policy` GET/POST (validazione, default fail-closed).
- **Integrazione:** dispatcher `get_history` con HA fake; execute-API espone
  `get_history` come READ e bypassa il whitelist azioni (estensione dei test v0.14.9).
- Nessun HA reale richiesto (fake/mocking, come i test esistenti).

## Fuori scope (per ora)

- Long-term statistics *scritte* da HIRIS (usiamo quelle di HA).
- Job di distillazione verso il second brain (Fase 3, progettato ma non implementato).
- Grafici/visualizzazioni nello UI HIRIS (lo storico è per analisi LLM, non dashboard).
- Statistiche a lungo termine per entità non-measurement lato HA (le copre HistoryStore).
