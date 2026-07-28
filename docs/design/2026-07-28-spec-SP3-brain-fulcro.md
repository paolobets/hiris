# SP-3 — Brain come fulcro (v1) · Spec

**Data:** 2026-07-28 · Repo: `hiris` · Base: `master` @ `e741fe5` (SP-2 v0.100.0) ·
North-star: `docs/design/2026-07-27-north-star-brain-chatbot-agentbot.md` (§«Il Brain
come fulcro» + roadmap SP-3).

## Obiettivo

Realizzare la **home del Brain**: la vista centrale dell'app dove il Brain mostra
in chiaro cosa osserva e deduce, segnala problemi chiedendo l'intervento, e raccoglie
in un unico posto le proposte da approvare/rifiutare. SP-3 **consolida** pezzi già
esistenti (ragionamento sentinella, proposte automazioni, storico/second-brain) e
aggiunge due capacità nuove: la **cattura del rationale** e un **rilevatore di
problemi** deterministico.

Target: **prosumer Home Assistant**, disclosure progressiva. Rilasciabile in modo
indipendente (v0.101.0).

## Scope

### Dentro (v1)

1. **Cattura del rationale** — ogni giro olistico del Brain (`_holistic_reason` /
   coverage-review) persiste il ragionamento in chiaro ("cosa ho osservato / cosa ho
   dedotto") in uno store dedicato, sanitizzato e retention-capped. Il testo è
   **catturato dall'output di ragionamento che il Brain già produce** — **nessuna
   nuova chiamata LLM, nessun nuovo egress**.
2. **Rilevatore di problemi (health-scan)** — set **chiuso e curato** di 5 check
   read-only. Ogni problema → **advisory** con evidenza deterministica + fix proposto
   + richiesta d'intervento.
3. **Feed unificato del Brain** — aggregatore **a lettura** che fonde in un'unica
   timeline tipizzata: rationale + advisory + proposte (`ProposalStore`) + suggerimenti
   (`SuggestionStore`) + timeline sentinella + tracce `brain-action` (oggi invisibili
   via HTTP). **Nessuna migrazione dei 4 store**: consolidamento al livello di
   presentazione.
4. **`#/` (Dashboard) → home del Brain** — supervisione casa + stream ragionamenti +
   feed proposte/advisory con approva/rifiuta/ack. Assorbe le tile/peek/log utili di
   oggi.

### Fuori (v1) — confini espliciti

- **Apprendimento di abitudini** o rilevamento di anomalie aperte → **SP-5**. Il
  rilevatore di SP-3 è un **set chiuso e deterministico**, non un motore generativo.
- Diagnosi "perché un Agentbot non è scattato" (cooldown/cap invisibili) → **SP-5**.
- Nessuna fusione/migrazione dei 4 store esistenti.
- Nessuna nuova esposizione pubblica; embeddings invariati.
- Rename profondo codice/API (`api/agents` → brain/chatbot, route, colonne DB) →
  resta **SP-1b**. SP-3 **non** tocca gli identificatori: usa `/api/brain/*` per il
  nuovo, lascia intatto il resto.

## Invarianti di sicurezza (cardine)

Pinnate da test discriminanti (vedi §Test):

1. **Health-scan e advisory sono sola-lettura: non attuano MAI.** Nessun percorso da
   `health_scan` verso `call_ha_service`/attuazione. `ack`/`dismiss`/`resolve` di una
   advisory è **solo cambio di stato**, zero effetto su HA.
2. **Ogni fix che tocca HA passa dal percorso esistente** proposta →
   `POST /api/proposals/{id}/apply` → **semaforo** (gate tier + denylist). Nessun nuovo
   percorso di apply. Una advisory promuovibile crea una riga `ProposalStore` standard.
3. **Rationale = solo-display.** I campi free-text sono sanitizzati con `_san` in
   ingresso, **mai** passati a runner/tool/LLM come istruzione, `ts` ISO-validato,
   `related_refs` solo id/entità (no free-text esterno). Retention-capped con prune.
4. **Nessun egress aggiuntivo.** La cattura del rationale riusa l'output del giro
   olistico già eseguito (già gated da `automatic_allows_sensitive`); non introduce
   una chiamata LLM di riassunto.
5. **Nuovi endpoint** dietro `internal_auth_middleware` + `csrf_middleware`. Reasoning
   e advisory sono **scope `home`**; il feed rispetta lo scoping di ogni sorgente.

## Architettura

### Backend — 3 componenti nuovi + 1 aggregatore

| Modulo | Ruolo | Store | Endpoint |
|---|---|---|---|
| `hiris/app/brain/reasoning_log.py` | Cattura+persiste il rationale dei giri olistici | nuova tabella `brain_reasoning` (via `storage.connect`, migrazione `user_version`) | `GET /api/brain/reasoning` |
| `hiris/app/brain/health_scan.py` | 5 check read-only → advisory (dedup + auto-resolve) | nuovo `AdvisoryStore` (SQLite) | `GET /api/brain/advisories`, `POST /api/brain/advisories/{id}/ack`, `POST /api/brain/advisories/{id}/dismiss` |
| `hiris/app/brain/feed.py` | Aggregatore read-time: merge tipizzato cronologico dei flussi | — (legge gli altri) | `GET /api/brain/feed` (paginato, `?type=`) |
| (gap chiuso) | Espone le tracce `brain-action` (oggi solo via ricerca semantica) | `KnowledgeStore` (esistente, `list_items(kind="brain-action")`) | folded in `feed` |

Handler nuovi in `hiris/app/api/handlers_brain.py`, registrati in `server.py::create_app`.

**Scheduling:** riusa la **ronda** esistente (`hiris_sentinel_ronda`, default 15 min) e
i job briefing/nudge. L'health-scan gira nel giro della ronda (o job dedicato a
intervallo separato se serve tarare la frequenza). La cattura del rationale si aggancia
**dentro** `_holistic_reason` dove il ragionamento già avviene.

### Front-end — `#/` (Dashboard) → Brain home

Riscrittura di `static/config/dashboard.js` (`HirisDashboard.mount`) in 3 zone
dall'alto:

1. **Supervisione casa** — striscia compatta: casa notevole (aperture correnti,
   # dispositivi offline) + stato Brain (ultimo giro, provider attivo). Riusa
   `api/status`/`api/entities`, **zero logica nuova**. Le tile utili di oggi
   (agenti/esecuzioni/token/costo) rientrano in riga secondaria.
2. **Stream ragionamenti** — card reverse-cronologiche ("Alle 08:00 ho osservato…
   ho dedotto…"), da `GET /api/brain/reasoning` (+ feed), ognuna linkabile alla
   proposta/advisory correlata.
3. **Azioni** — due liste raggruppate: **Proposte** (approva/rifiuta, riusa il flusso
   esistente) + **Advisory** (ho capito / ignora / "crea proposta" se `fix_kind`
   promuovibile). Empty-state reali. Onboarding first-run (`renderEmpty`) preservato.

`#/proposals` resta per il lifecycle completo. Cache-busting per-file hash invariato
(`_asset_fingerprint`), render XSS-safe come le route esistenti, `node --check` in CI.

### Data flow

```
ronda / giro olistico
  ├─ reasoning_log.capture(...)   → persiste rationale (sanitizzato, no nuovo LLM)
  ├─ health_scan.run(...)         → emette/aggiorna advisory (dedup, auto-resolve)
  └─ coverage/proposte            → come oggi (SuggestionStore / ProposalStore)
                                        │
GET /api/brain/feed ── feed.py aggrega a richiesta i 6 flussi ──► home `#/` (3 zone)
                                                                       │
utente: approva proposta → apply gated dal semaforo
        ack/ignora advisory → solo stato
        promuovi advisory → nuova riga ProposalStore → apply gated
```

## Health-scan — set chiuso di 5 check (v1)

Ogni check è una **funzione pura read-only** che, dati gli stati HA + la config HIRIS,
ritorna 0..N advisory. Dedup per `source_ref` stabile (pattern supersede/`ReminderSeen`
già in casa): una advisory `open` con lo stesso `source_ref` non viene ricreata.
**Auto-resolve:** al rescan, se la condizione di una advisory `open` non regge più →
`status=resolved`, `resolved_auto=true`. Registro estensibile (stile `LEARNABLE`).

| # | `check_id` | Legge | Condizione | Severity | Fix | `fix_kind` |
|---|---|---|---|---|---|---|
| 1 | `entity_unavailable` | HA states + history | entità `unavailable`/`unknown` da ≥ N giorni (def. 2) | `warn` | "controlla dispositivo/integrazione" | `manual` |
| 2 | `low_battery` | sensori `device_class=battery` | livello < soglia % (def. 15) | `warn` | "sostituisci le pile" (riusa logica briefing) | `manual` |
| 3 | `automation_broken` | HA automation registry/state | automazione disabilitata o `unavailable` | `high` | "ri-abilita / verifica" | `manual` |
| 4 | `dangerous_domain_green` | **config semaforo HIRIS** | dominio pericoloso (lock/alarm_control_panel/cover/siren/script) in tier verde/auto | `high` | "alza il tier" → proposta config HIRIS | `hiris_config` |
| 5 | `entity_no_area` | HA entity/area registry | entità senza area assegnata | `info` | "assegna un'area" | `manual` |

Note:
- **#4** è auto-diagnosi della **propria** postura di sicurezza (allineato al modello
  semaforo per-dominio/per-entità). Riusa `DANGEROUS_DOMAINS` da
  `security/semaphore.py` e la policy semaforo caricata.
- **#5** parte con `severity=info` ed è **silenziabile** (può essere rumoroso in case
  grandi); non genera notifiche push, vive solo nel feed.
- Le soglie (N giorni, % batteria) sono costanti con default sensati; l'esposizione in
  UI delle soglie è fuori scope v1 (eventuale in SP-4/config).

## Modelli dati

### `brain_reasoning` (nuova tabella SQLite)

| Campo | Tipo | Note |
|---|---|---|
| `id` | TEXT (uuid) | PK |
| `ts` | TEXT (ISO) | validato ISO all'ingresso |
| `mode` | TEXT | `holistic` \| `ronda` \| `coverage` |
| `summary` | TEXT | sanitizzato `_san` |
| `observations` | TEXT | sanitizzato `_san` |
| `deductions` | TEXT | sanitizzato `_san` |
| `related_refs` | TEXT (JSON) | solo id proposte/advisory + entity_id (no free-text) |

Retention: prune job (riusa lo scheduler) — cap a max righe **o** N giorni (default:
tieni ~500 righe / 30 giorni, la più stretta). `user_version`/migrazione via
`storage.py`.

### Advisory (`AdvisoryStore`, nuova tabella SQLite)

| Campo | Tipo | Note |
|---|---|---|
| `id` | TEXT (uuid) | PK |
| `check_id` | TEXT | uno dei 5 |
| `ts_created` | TEXT (ISO) | |
| `ts_updated` | TEXT (ISO) | |
| `severity` | TEXT | `info` \| `warn` \| `high` |
| `title` | TEXT | deterministico (no LLM) |
| `evidence` | TEXT (JSON) | fatti deterministici (entità, valori, soglie) |
| `suggested_fix` | TEXT | deterministico |
| `fix_kind` | TEXT | `manual` \| `hiris_config` \| `ha_proposal` |
| `fix_ref` | TEXT (null) | id `ProposalStore` se promossa |
| `status` | TEXT | `open` \| `acknowledged` \| `resolved` \| `dismissed` |
| `source_ref` | TEXT | chiave dedup stabile per (check, target) |
| `resolved_auto` | INTEGER | 1 se auto-risolta al rescan |

Lifecycle: `open` → (utente) `acknowledged`/`dismissed`, oppure (rescan) `resolved`
(`resolved_auto=1`). `dismissed` sopprime la ricreazione per lo stesso `source_ref`
(dedup) fino a scadenza retention.

### Feed item (read-time, **non persistito**)

`type` (`reasoning` \| `advisory` \| `proposal` \| `suggestion` \| `sentinel_event`),
`ts`, `title`, `body`, `refs`, `actions[]`, `status`. Le `actions` dipendono dal tipo:
proposta→approva/rifiuta; advisory→ack/ignora/(promuovi); suggestion→undo;
reasoning/sentinel_event→nessuna (sola lettura). Ordinamento reverse-cronologico,
paginazione, filtro `?type=`.

## API (nuova, namespace `/api/brain/*`)

Tutti dietro `internal_auth_middleware` + `csrf_middleware`.

| Metodo | Path | Ruolo |
|---|---|---|
| `GET` | `/api/brain/feed` | Feed unificato paginato (`?type=`, `?limit=`, `?before=`) |
| `GET` | `/api/brain/reasoning` | Stream ragionamenti (paginato) |
| `GET` | `/api/brain/advisories` | Advisory (`?status=`) |
| `POST` | `/api/brain/advisories/{id}/ack` | → `acknowledged` (solo stato) |
| `POST` | `/api/brain/advisories/{id}/dismiss` | → `dismissed` (solo stato) |
| `POST` | `/api/brain/advisories/{id}/promote` | crea `ProposalStore` da advisory `hiris_config`/`ha_proposal`, setta `fix_ref` (l'apply resta sull'endpoint proposte, gated) |

La promozione **non** applica nulla: crea la proposta; l'utente poi la applica dal
flusso proposte esistente (semaforo).

## Test

**Sicurezza (discriminanti):**
- Nessun percorso `health_scan` → attuazione HA (assert su assenza di `call_ha_service`).
- `ack`/`dismiss`/`promote` non producono effetti HA; `promote` crea solo la proposta.
- Proposta nata da advisory → apply colpisce comunque il semaforo (riuso test gate).
- `_san` su tutti i campi free-text del rationale con stringhe d'iniezione IT/EN;
  rationale mai passato a runner/tool (test di isolamento).
- Prune retention `brain_reasoning` (righe oltre soglia/età rimosse).
- Endpoint nuovi: 401 senza `internal_auth`, 403 senza CSRF token.

**Funzionali:**
- Ogni check: fixture stati HA/config → advisory attese (0..N), dedup su rescan,
  auto-resolve quando la condizione rientra.
- Lifecycle advisory: open→ack/dismiss/resolve; dismissed sopprime ricreazione.
- Feed: merge, ordinamento reverse-cronologico, paginazione, filtro `?type=`.
- Front-end: `node --check` su dashboard.js e nuovi moduli; render XSS-safe.

**Live-verify (utente):** aggiornamento addon su HA reale; la home `#/` mostra le 3
zone; una advisory reale (es. batteria scarica) appare e si auto-risolve.

## Processo & rilascio

- Branch `feat/sp3-brain-fulcro`, base `master` @ `e741fe5`.
- Build **subagent-driven** con review Fable/Opus per-task + review whole-branch
  finale (pattern consolidato HIRIS).
- **Bump versione → v0.101.0** (o i tablet/addon non aggiornano).
- Doc IT/EN aggiornate dove la home cambia; `PRODUCT.md` **non** in scope qui (resta
  il TODO SP-1b/north-star).
- **Conferma esplicita** dell'utente prima di merge / tag / release e prima della
  live-verify.

## Riferimenti codice (grounding, da riverificare in fase di piano)

- Proposte: `proxy/proposal_store.py`, `api/handlers_proposals.py`,
  `server.py` (`create_automation_proposal`, `_propose`, `_mk_proposal`).
- Suggerimenti Brain: `brain/suggestions.py`, `api/handlers_suggestions.py`,
  `brain/cognitive_loop.py` (auto-tune, `trace_applied_coverage`).
- Tracce ragionamento: `brain/brain_trace.py` (`record_brain_action`,
  kind=`brain-action` in `KnowledgeStore`).
- Ragionamento olistico: `server.py::_holistic_reason`, `brain/coverage_review.py`.
- Sentinella: `watcher/guardian.py`, `watcher/lenses.py`, `watcher/situations.py`,
  `api/handlers_sentinel.py` (`/api/sentinel/timeline`).
- Storico: `history/store.py`, `api/handlers_history_policy.py`.
- Semaforo: `security/semaphore.py` (`DANGEROUS_DOMAINS`, `gate_action`).
- Front-end: `static/config/main.js` (router), `static/config/dashboard.js`,
  `static/config/router.js`; fingerprint asset `server.py::_asset_fingerprint`.
