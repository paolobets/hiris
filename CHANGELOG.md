# HIRIS — Changelog

## v0.10.10 — Trigger UI fixes (2026-05-07)

User report 4 bug nella sezione Trigger:
1. **Periodico**: input number con arrows native non in linea col design
2. **Cambio stato entità**: campo stringa free-text — utente vuole autocomplete
3. **Cron**: chip "Ogni giorno alle 06:00" appare ma non cliccabile/modificabile
4. **Manuale**: option mai implementata, da rimuovere

### Fix

1. **Periodico CSS** (`hiris-config.css`): `.nt-num-input` rimuove arrows
   native via `appearance: textfield` + `::-webkit-inner/outer-spin-button`.
   Width 80px center-aligned. Range `min=1 max=1440` (24h).
2. **Cambio stato entità autocomplete** (`agent-editor.js populateIdentita`
   + `rewireLegacyAfterMount`): input ora ha dropdown suggestions sotto.
   Pattern stesso di permessi.js entity-search ma scope locale.
   Fetch `api/entities?q=` con debounce 250ms, max 30 risultati.
   Click suggestion fill input. Outside-click + ESC chiudono.
   CSS `.nt-entity-suggestions` con max-height + scroll.
3. **Cron chip diagnostic** (`cron-popover.js`): aggiunto console.log su
   click + try/catch + alert se `HirisPopover` undefined o errore.
   Future debug istantaneo. Se persiste in v0.10.10 → user vede output
   console + alert con causa.
4. **Manuale rimosso**: `<option value="manual">` eliminato dal select
   `#new-trigger-type`. Triggers esistenti con `type='manual'` non
   vengono toccati lato backend.

### Test

- pytest 562/562 passed
- node -c syntax OK

Bump 0.10.9 → 0.10.10 + V6_CACHE_BUST sync.

## v0.10.9 — Frontend runAgent timeout 90s → 600s (2026-05-07)

User console v0.10.8: `[v6] runAgent error: AbortError: signal is aborted
without reason at agent-editor.js:692:46`. Test Run su agente IRRIGAZIONE
con modello locale gemma4:e4b abortiva al frontend dopo 90s.

### Root cause

`window.runAgent` aveva hardcoded `setTimeout(ctrl.abort, 90000)` (90s)
ma backend è configurato per timeout molto più lunghi:
- `_AGENT_RUN_TIMEOUT` fallback su `OLLAMA_REQUEST_TIMEOUT * 1.2` (v0.10.4)
- User `local_model.request_timeout=600` o `800` → backend permette 720-960s
- Frontend cuttava a 90s anche se backend lavorava → AbortError visibile

### Fix

- `FRONTEND_RUN_TIMEOUT_MS = 600000` (10 min) — allineato al backend.
- Banner "attendere fino a 10 minuti" (era 90s).
- Timeout error message aggiornato con suggerimento debug (Ollama logs).

### Test

- pytest 562/562 passed
- node -c syntax OK

Bump 0.10.8 → 0.10.9 + V6_CACHE_BUST sync.

## v0.10.8 — Test Run feedback visivo + sidebar/sticky-bar redesign (2026-05-07)

Due richieste user combinate in unica release:

1. Test Run "logga in console l'avvio ma 1) nessuna evidenza del test in
   corso 2) la sezione test non si compila 3) posso premere N volte il
   pulsante 4) non sono certo il test venga lanciato".

2. Sidebar footer "non esteticamente corretto": rimuovi voce duplicata
   "Vai alla chat" + icona luna sbagliata. Sposta link Chat in cima
   (sotto HIRIS, sopra Configurazione). Stringi sticky bar simmetrica
   alla parte centrale del page-main: Annulla a sinistra, TestRun/
   Elimina/Salva a destra.

### Root cause (systematic debugging Phase 1)

CSS spinner usava selector legacy `#run-btn`:
```css
#run-btn.running .spinner { display: inline-block; }
```
Ma in v6 il bottone è `#btn-test-run`. Lo spinner non veniva MAI mostrato →
zero feedback visivo. User vedeva solo log console + nessuna animazione →
impressione di "non funziona" → click multipli.

Inoltre `runAgent` non scrollava alla sezione Test Run, quindi l'output
appariva sotto il viewport user (sezione 08, dopo Log esecuzioni in 07).

### Fix

1. **CSS spinner**: regole estese a `#btn-test-run` (oltre `#run-btn` legacy):
   - `.running` → opacity ridotta + cursor not-allowed + **pointer-events:none**
     (impedisce nativamente click multipli)
   - `.spinner` visibile via `inline-block` quando `.running` aggiunto
   - Border-color usa `currentColor` (funziona su qualsiasi tema/colore bottone)

2. **Banner "Test Run in corso"**: nuovo atom CSS `.run-running-banner`
   con icon spinner + testo "Test Run in corso… l'agente sta elaborando,
   attendere fino a 90s." Inserito in cima a `sc-body-run` quando user clicca.
   Il banner viene rimosso a fine esecuzione (success/error/timeout).

3. **JS `window.runAgent`**:
   - Flag `_runInFlight` globale → previene esecuzione doppia anche se click
     handler logga prima del check (race condition).
   - Bottone label cambia in `⏱ In esecuzione…` (visivamente diverso dal
     `▶ Test Run` di base).
   - `requestAnimationFrame` + `scrollIntoView({behavior:'smooth',block:'start'})`
     IMMEDIATO → user vede subito il banner + section Test Run.
   - Console.log esteso (`fetch starting`, `response status=N`, `done`/`error`)
     per debug futuro.
   - Gestione errori: response con `data.error` colorata `run-error-text`,
     prefisso `✗`. Success colorato `✓ ESEGUITO` in verde.
   - `cleanupRunning()` reset stato bottone in TUTTI i path
     (success/error/timeout) — niente più bottone bloccato in stato running.
   - Pre/post output: `<pre>` ora ha sfondo + padding + min-height 60px →
     visibile anche con output vuoto/errore.

### Sidebar redesign

- **Chat link in cima**: voce nav `<a href="./">` con icona speech-bubble,
  inserita SOTTO il brand HIRIS, SOPRA il label "Configurazione".
- **Rimossa voce duplicata in fondo**: vecchia "Vai alla chat" con icona luna
  (sbagliata, era theme toggle icon) eliminata. Niente più nav-spacer.
- **Niente più sezione "Sistema"** vuota (la voce Settings era stata già
  rimossa in v0.10.5).

### Sticky bar redesign — wrap pattern + simmetria

- **Outer `.sticky-actions-wrap`**: position fixed bottom, full-width da
  sidebar a viewport-right. Background blur + border-top → la "barra"
  visiva continua per tutta la larghezza.
- **Inner `.sticky-actions`**: `max-width: var(--shell-content-max)` (1140px)
  + `margin: 0 auto` → contenuto centrato simmetricamente alla `.editor-content`.
- **Layout interno**:
  ```
  [Annulla]  ........spacer.........  [▶ Test Run] [Elimina] [Salva]
  ```
- **Rimosso "Salvato ✓" / "Modifiche non salvate" status text** dalla bar.
  Lo stato dirty/saved è ora indicato dal solo pulsante Salva (`disabled` =
  saved, enabled = pending). Pattern Stripe/Linear: visivamente più pulito,
  meno rumore. `setupStickyActions` aggiornato (`var status` rimosso, guard
  `if (btnSave)` aggiunto).

### Test

- pytest 562/562 passed
- node -c syntax OK

Bump 0.10.7 → 0.10.8 + V6_CACHE_BUST sync.

## v0.10.7 — Route #/tasks per Task pianificati (2026-05-07)

User feedback: "in tutto questo aggiornamento/restyle dove sono finiti i task?"

Gap del v6 redesign: i Task pianificati esistono in chat (`index.html`
sidebar "Task pianificati") + backend (`handlers_tasks.py` + `task_engine.py`)
ma il designer v6 (`config.html`) **non aveva alcuna route** per loro.
Mea culpa nel design doc originale.

### Implementato

- **Voce side-nav "Task"** con icon clock + badge `nav-tasks-count` (count
  task pending), inserita sotto "Consumi" prima del nav-spacer.
- **Route `#/tasks`** mount via `HirisTasksRoute.mount()`:
  - 5 filter chip: tutti / ⏱ in attesa / ✓ eseguiti / ✗ falliti / ⊘ cancellati
    con counter dinamici aggiornati ad ogni render.
  - Lista task: time created / status / agent name / label / trigger summary.
  - Click row → expand inline (pattern log-row v6, accordion).
  - Detail mostra: meta-chip trigger/actions/executed-at/error/parent-task,
    block result (preformattato) se presente, bottone "⊘ Cancella" SOLO per
    task pending, bottone "{} copia raw JSON" sempre.
  - Refresh on demand (↻ aggiorna).
  - Sort: pending+failed prima, poi by created_at desc.
- **Side-nav badge sync**: `nav-tasks-count` aggiornato anche dopo cancel
  (no full reload necessario).

### Backend

- **Zero modifiche**. Endpoints esistenti (`api/tasks` GET con filtri,
  `api/tasks/:id` GET single, `api/tasks/:id` DELETE cancel) usati as-is.

### File

- **Nuovo**: `hiris/app/static/config/tasks-route.js` (~210 LOC)
- **Modificati**: `config.html` (nav voice + script include), `main.js`
  (route handler + nav active 'tasks' + badge fetch), `agent-editor.js`
  (V6_CACHE_BUST 0.10.6 → 0.10.7), `config.yaml` (version bump)

### Test

- pytest 562/562 passed
- node -c syntax OK

## v0.10.6 — Hotfix regressione cleanup v0.10.5 (2026-05-07)

User report v0.10.5 console: due regressioni introdotte dal cleanup.

### Bug 1: `ReferenceError: renderList is not defined`

`agent-form.js openAgent()` linea 142 chiamava ancora `renderList()` ma la
funzione era stata rimossa dal cleanup v0.10.5 (target #agent-list shim
invisibile). Il banner errore "Step openAgent failed" appariva all'apertura
di ogni agente.

**Fix:** rimossa anche la call `renderList()` da openAgent. Commento aggiunto
per spiegare che la lista agenti è ora gestita da agents-list.js sulla
route #/agents.

### Bug 2: `TypeError: Cannot set properties of null (setting 'value')` in `_setModelValue`

`api.js _setModelValue()` (linea 48) faceva `sel.value = val` senza null
guard. Quando `loadModels()` fetch async era in flight e l'utente cambiava
route, `#f-model` veniva rimosso dal DOM e `sel` diventava null al callback.

**Fix:** added `if (!sel) return` guards in `_setModelValue` e all'inizio
di `loadModels`. La function diventa no-op se l'editor non è montato.

### Test

- pytest 562/562 passed
- node -c syntax OK

Bump 0.10.5 → 0.10.6 + V6_CACHE_BUST sync.

## v0.10.5 — Drawer/popover loading + anchor nav + sidebar count + settings + sticky align (2026-05-07)

User feedback su v0.10.4 + console output. Audit systematic-debugging ha
trovato **bug critico mai notato**: drawer.js e popover.js NON ERANO MAI
CARICATI dalla v0.10.0 in poi. Spiegava perché +Aggiungi azione e cron chip
popover non funzionavano.

### Bug critici fixati

1. **`drawer.js` + `popover.js` mai caricati** (CRITICAL, presente fin da v0.10.0)
   - `config.html` non aveva i `<script>` static per questi atom
   - `agent-editor.js LEGACY_SCRIPTS` aveva solo `cron-popover.js`, NON
     i base atom `popover.js` né `drawer.js`
   - Conseguenza: `HirisDrawer` e `HirisPopover` erano `undefined`
   - **+Aggiungi azione** non apriva nulla (script-action.js HirisActionDrawer.open fallisce silently)
   - **Cron chip click** non apriva il popover preset (cron-popover.js HirisPopover.open fallisce)
   - Bug mai catturato perché test browser-based di Phase 3 testavano i moduli isolati ma nessun test integration end-to-end ne ha verificato il caricamento globale
   - **Fix**: aggiunti `<script src="static/config/drawer.js">` e
     `<script src="static/config/popover.js">` in config.html PRIMA di
     agent-editor.js

2. **Anchor nav causa router warnings + service worker errors + remount loop**
   - Click `<a class="anchor-link" href="#sec-X">` cambiava URL hash
   - Browser fires `hashchange` → router.resolveRoute → no route match per `#sec-X` → console.warn
   - HA Ingress service worker prova a fetch `config#sec-X` → 404 → "Uncaught (in promise) Object"
   - Quando user navigava back → remount agent-editor → invalidava reference a `#run-output` → output Test Run non appariva
   - **Fix**: `setupAnchorNav` ora intercetta click anchor con `e.preventDefault()` + `scrollIntoView({behavior:'smooth'})`. Hash invariato, nessun service worker hit, no remount.

3. **Sidebar "Agenti" badge "—" invece del count**
   - main.js mountChrome usava `loadAgents()` (in agent-form.js, legacy)
   - Legacy modules sono caricati solo quando user apre l'editor → al boot `loadAgents` undefined → typeof check skip → badge resta "—"
   - **Fix**: fetch diretto `api/agents` in mountChrome, popola badge + HirisState + window.agents global

4. **Settings menu placeholder "Implementata in Phase 11" confondeva**
   - **Fix**: rimosso voce nav "Impostazioni" da config.html. Re-aggiungeremo quando avrà contenuto reale.

5. **Sticky-actions bar misaligned**
   - v0.10.4 fix usava `left: var(--shell-sidebar-w); right: 0` che spannava la bar da sidebar-edge a viewport-right-edge ignorando il max-width centrato del page-main (1140px)
   - **Fix**: padding-left/right calcolato dinamicamente per allineare il contenuto della bar al page-main centrato.

### Test Run output

Bug Test Run "non si popola" è probabilmente effetto collaterale del **remount loop** causato dall'anchor nav (#3 sopra). Risolto il remount, `out` reference resta valida durante l'intera vita del fetch → output appare.

Se persiste in v0.10.5, il diagnostic logging in console.log `[v6] TestRun clicked, ...` mostra runAgent=function — andremo a debug interno della funzione.

### Dead code cleanup (eseguito in v0.10.5)

- **`tabs.js` ELIMINATO** (~50 LOC): file mai più caricato dopo Phase 4 v6 long-form. Conteneva `switchTab`, `resetToFirstTab`, theme toggle duplicato, version footer fetcher.
- **`agent-form.js` ridotto 333 → 211 LOC** (-122): rimossi handler IIFE `#new-btn`/`#save-btn`/`#delete-btn`/`#run-btn` (erano shimmati a div invisibili, sostituiti da `window.saveAgent`/`runAgent`/`deleteAgent` in agent-editor.js + `initNewAgent` path), rimossa funzione `renderList` (target `#agent-list` shim), rimossa querySelector `#agent-tabs .tab-btn` (markup tab orizzontale rimosso in v6). `loadAgents` resta ma non chiama più `renderList`. `showAgentMode` ora target `#sec-azioni` v6 invece del `#tab-azioni` legacy.
- **`logs.js` ridotto 87 → 60 LOC** (-27): rimossi `toggleLogRow` e click delegate su `#log-body` per `.log-expand-btn`/`.log-thinking-btn` (classi non esistono in v6 — `HirisLogRow.render` produce markup `.log-row`/`.lr-collapsed`/`.lr-detail` con click handler proprio). Rimossi IIFE listener `input` su `#f-strategic`/`#f-prompt` (gestiti ora da `rewireLegacyAfterMount`). Funzioni `updateTokenCounter` e `loadContextPreview` ora null-safe.
- **`addLegacyShims` ridotto da 11 a 5 ID stub** (`no-selection`, `form`, `form-title`, `delete-btn`, `usage-reset-btn`). Rimossi `new-btn`/`save-btn`/`run-btn`/`agent-list`/`agent-tabs`/`tab-azioni` perché i loro consumatori legacy sono stati eliminati.
- **Visibility `btn-delete` per default agents**: aggiornato `agent-editor.js mount()` post-resolveAgent per nascondere il pulsante Elimina su agenti default (es. HIRIS, `is_default=true`).

### Pending v0.10.6+ (se servono)

- `api/scripts` endpoint backend (script picker oggi vuoto, fallback input text)
- Field UI per `fallback_action` e `allowed_endpoints` (orphan in dataclass) — o rimozione dal backend

### Test

- pytest 562/562 passed
- node -c syntax OK su tutti i file modificati

## v0.10.4 — 300s timeout + sticky bar + theme toggle + chat redundant badge (2026-05-07)

User segnala 5 categorie bug. Audit deep ha individuato root cause per ognuno
+ extra dead code. Fix mirati:

### 1. **Bug critico — 300s timeout sui modelli locali ignorato** (HIGH)

User imposta `local_model.request_timeout` a 600 → 800s in HA addon ma riceve
sempre "Timeout dopo 300s — il modello non ha risposto in tempo".

**Root cause** (`hiris/app/agent_engine.py:20`):
```python
_AGENT_RUN_TIMEOUT = int(os.environ.get("AGENT_RUN_TIMEOUT", "300"))
```
La env var `AGENT_RUN_TIMEOUT` è **mai esportata in `run.sh`** → cade sempre
sul default 300. La user setting `local_model.request_timeout` viene
correttamente esportata come `OLLAMA_REQUEST_TIMEOUT` (usata dall'OpenAI SDK
client) ma **non viene letta dal wrapper outer `asyncio.wait_for`**, che cuttava
sempre a 300s anche se il modello locale completava in 500s.

**Fix:** `_AGENT_RUN_TIMEOUT` ora cade su `OLLAMA_REQUEST_TIMEOUT × 1.2` (con
floor 300s) quando `AGENT_RUN_TIMEOUT` non è esplicitamente settata. User che
imposta `local_model.request_timeout=800` ora ha `_AGENT_RUN_TIMEOUT=960`
(800 × 1.2). Margin 20% garantisce che il client SDK timeout scatti per
primo (errore localizzato) invece dell'asyncio wrapper outer (errore generico).

### 2. **Sticky-actions bar layout broken**

CSS bug: `.sticky-actions { position: sticky; bottom: 0; margin: ... -X -X -X }`
dentro `.editor-content` con `align-items:start` causava posizionamento
sbagliato + flicker.

**Fix:** `position: fixed` con `left: var(--shell-sidebar-w)` allinea la bar
alla sidebar v6 (responsive a viewport). `padding-bottom: 80px` su
`.editor-content` previene che la bar copra l'ultima section-card.

### 3. **Log row ANCORA esploso** (defense-in-depth)

Audit conferma codice CSS corretto v0.10.3 — il problema era cache stale.
Ora belt-and-suspenders triplo:
- `.lr-detail { display: none !important }` (CSS)
- `.log-row.expanded .lr-detail { display: flex !important }` (CSS specifico)
- `<div class="lr-detail" style="display:none">` inline (log-row.js)

Anche con cache stale di v0.10.2, il pattern `display:none` inline sul
container resta. La nuova regola `!important + .expanded .lr-detail` sblocca
solo quando expanded.

### 4. **Theme toggle "quadrato" + FOUC** (designer + chat)

- **Designer**: nuovo atom `.btn-icon-only` (36px circolare, transparent,
  hover background). Template `tpl-page-chrome` ora usa questo invece di
  `.btn .btn-ghost`. Icone partono `style="visibility:hidden"` invece di
  `display:none` — `paint()` setta `visibility: visible/hidden` per la icona
  giusta, eliminando FOUC.
- **Chat**: `#theme-toggle` da `border-radius: var(--r-sm)` (quadrato) a
  `border-radius: 50%` (circolare), no border default, hover state coerente
  con designer.

### 5. **Chat — badge "connesso" ridondante**

`#agent-pill` mostrava già il pallino verde "live" indicando connessione.
Il `#conn-dot` con testo "connesso" duplicava info → rumore visivo.

**Fix:** `#conn-dot { display: none }` di default. La classe `.offline` lo
rivela come error chip. Quindi il badge appare SOLO quando offline, mentre
in stato normale (happy path) la connessione è indicata implicitamente
dall'avatar verde dell'agent-pill.

### 6. **Breadcrumb mostra ID invece di nome agente** (cosmetico)

`agent-editor.js mount()` aggiorna ora `chrome-here` con `'Agenti / ' + agent.name`
dopo che `resolveAgent` carica l'oggetto. Il bare ID rimane fallback solo
durante il caricamento iniziale di pochi ms.

### 7. **Audit dead code (info, fix in v0.10.5+)**

Identificato:
- `tabs.js` mai più caricato — pronto per cancellazione
- `agent-form.js` IIFE handlers `#save-btn`/`#delete-btn`/`#run-btn`/`#new-btn` —
  shimmati ma puntano a div invisibili → dead. setupStickyActions chiama
  saveAgent/runAgent/deleteAgent globali che è il path live.
- `agent-form.js` `renderList` — `#agent-list` è shim → dead path.
- `logs.js` `toggleLogRow` + click delegate su `.log-expand-btn` — quelle
  classi non esistono in v6, dead.
- `api/scripts` endpoint **non implementato backend** — `script-action.js`
  fa fetch e fallisce silenziosamente. Picker script vuoto.
- 2 campi Agent dataclass orphan: `fallback_action`, `allowed_endpoints` —
  esistono backend, no UI.

Cleanup pianificato per v0.10.5+ insieme a `api/scripts` decision.

### Test

- pytest 562/562 passed
- node -c syntax OK su tutti i file modificati
- Backend agent_engine.py modifica: prima volta che tocchiamo backend in v6
  redesign. Solo 1 cambio (calcolo default `_AGENT_RUN_TIMEOUT`),
  retro-compat completa (env var override prevale).

### User action

Hard reload browser (Ctrl+Shift+R) post-update per forzare fetch CSS/JS
freschi. Da v0.10.4 il client-side cache-bust più aggressivo previene la
ricomparsa.

## v0.10.3 — Log row collapse di default + diagnostic buttons (2026-05-07)

Due bug user reportati:
1. Sezione log dell'editor appariva ESPLOSA con tutti i dettagli visibili
   invece di compatta + apribile su click.
2. Pulsanti Test Run, Salva, Elimina sembravano non funzionare.

### Fix bug 1 — Log row collapse default

CSS bug in hiris-config.css: `.lr-detail` era `display: flex` di default
invece di `display: none`. La classe `.log-row.expanded` aggiungeva solo
gli stili visivi accent ma il dettaglio era sempre visibile.

### Causa root

Il CSS atom `.lr-detail` (in `hiris-config.css` riga 1593) era `display: flex`
di default invece di `display: none`. La classe `.log-row.expanded` aggiungeva
solo gli stili visivi accent (border + box-shadow) ma il dettaglio era già
visibile, quindi tutti i log apparivano espansi all'apertura.

### Fix

```css
.lr-detail {
  display: none;             /* nascosto di default */
}
.log-row.expanded .lr-detail {
  display: flex;             /* visibile solo quando il row è espanso */
  margin-top, padding-top, border-top, animation… (immutati)
}
```

Click sulla riga aggiunge `.expanded` (logica già in log-row.js) → detail
diventa visibile con animazione slideIn. Click su altra riga collapse la
prima e espande la seconda (accordion). ESC chiude.

### Fix bug 2 — Diagnostic logging pulsanti sticky-actions

Code review statico ha confermato che `window.saveAgent`/`runAgent`/
`deleteAgent` sono correttamente definiti dentro l'IIFE di `agent-editor.js`
(prima della chiusura). I click handler in `setupStickyActions` chiamano
`if (typeof saveAgent === 'function') saveAgent()` che dovrebbe risolvere via
window. Tuttavia user reports che i pulsanti "non funzionano" — diagnosi
necessaria run-time.

Aggiunto **diagnostic console.log** in OGNI click handler:
- Save: logga agentId, typeof saveAgent, typeof buildPayload, return value, promise resolve/reject
- Test Run: logga typeof runAgent, currentId, errori try/catch
- Delete: logga typeof deleteAgent, errori try/catch

Se la funzione globale non è definita, alert + console.warn istruisce su
hard reload (cache stale). Se la funzione throw, alert con messaggio.

Aprendo DevTools console (F12) e cliccando un pulsante, l'output dirà
ESATTAMENTE cosa fallisce: typeof check, throw nella funzione, fetch failure,
ecc. Future debug saranno immediati.

Bump version 0.10.2 → 0.10.3 + V6_CACHE_BUST sync.

## v0.10.2 — Defensive guards + cache-bust + chat link fix (2026-05-07)

User segnala che v0.10.1 aveva ancora il banner "Errore caricamento editor:
Cannot read properties of null (reading 'style')" e un nuovo bug: il bottone
"Vai alla chat" usciva dall'iframe Ingress di Home Assistant.

### Diagnosi

Audit statico ha confermato che il codice v0.10.1 è clean: tutti gli `.style`
access nei moduli legacy puntano a ID coperti dallo shim oppure creati dai
populate*() di agent-editor.js. Il TypeError persistente è quasi certamente
**browser cache stale**: il tablet HA serviva ancora `agent-editor.js` v0.10.0
(senza `addLegacyShims`) anche dopo l'update dell'addon a v0.10.1.

Causa root: la cache-bust HIRIS (`_inject_version` che appende `?v=VERSION`)
agisce solo sui `<script>` del HTML response. Gli script caricati DINAMICAMENTE
da `agent-editor.js loadScript()` (templates, cron, triggers, agent-form, ecc)
NON ricevevano il cache-bust → browser caching aggressivo li manteneva alla
versione precedente.

### Fix

- **Cache-bust client-side** in `agent-editor.js loadScript()`: appende
  `?v=V6_CACHE_BUST` a OGNI dynamic-loaded script. La costante è hardcoded
  in `agent-editor.js` (top) e va bumpata ad ogni release. Forza re-fetch
  sicuro anche con caching aggressivo.
- **Diagnostic logging step-by-step** in `mount()`: ogni passo (clear outlet,
  clone template, populate*, addLegacyShims, ensureLegacy, populateTemplateSelector,
  loadModels, rewireLegacyAfterMount, setupStickyActions, openAgent) è wrapped
  in `step(name, fn)` che logga su console.error il nome dello step se throw,
  e il banner errore mostra "Step: <stepName> · v0.10.2" + suggerimento hard
  reload. Future debug saranno immediati.
- **Null guards difensivi** in `agent-form.js` openAgent + new-btn handler +
  save-btn/delete-btn/run-btn IIFE binding: TUTTI i `getElementById(...).style`
  e `.addEventListener` ora protetti con `var x = getElementById(...); if (x)`.
  Belt-and-suspenders: anche con cache stale, l'app degrada gracefully invece
  di throware.
- **Chat link `target="_top"` rimosso** da side-nav (config.html) e dashboard
  (dashboard.js): il link "Vai alla chat" navigava la TOP frame causando
  uscita dall'iframe Ingress di HA. Senza target, naviga nell'iframe → resta
  in HA.

### Test

- pytest 562/562 passed
- node -c syntax OK su agent-editor.js, agent-form.js, dashboard.js

### User action

Per chi era su v0.10.1 con cache stale: dopo update a v0.10.2 fare hard reload
del browser (Ctrl+Shift+R su PC, clear cache via Settings su tablet) per
forzare fetch del nuovo agent-editor.js. Da v0.10.2 in poi, il cache-bust
client-side previene la ricomparsa del problema.

## v0.10.1 — Hotfix wiring legacy↔v6 (2026-05-07)

Fix comprehensive di **9 bug** di disconnessione tra il long-form v6 e i moduli
legacy (templates, triggers, permessi, action-editor, logs, usage, agent-form):

### Bug fixed

1. **Crash apertura agente** (Cannot read properties of null reading 'style'):
   `agent-form.js openAgent()` accedeva a ID legacy non più presenti
   (`#no-selection`, `#form`, `#form-title`, `#delete-btn`, `#agent-list`,
   `#agent-tabs`, `#tab-azioni`). + `agent-editor.js` passava string id
   invece di agent object.
2. **Templates dropdown vuota**: `populateTemplateSelector()` non veniva
   mai chiamato dal v6 boot (era nel vecchio `main.js` rimosso).
3. **Trigger type switch non funziona**: listener `change` su
   `#new-trigger-type` bound IIFE-time alla prima istanza del nodo, stale
   ad ogni successivo mount perché populate ricrea l'innerHTML del sc-body.
4. **Form si congela al 2° open editor**: stesso pattern del bug 3 affetta
   tutti i 23 listener IIFE-time (triggers, permessi domain pills, entity
   search, f-type/f-action-mode/f-model/f-states change, token counter,
   usage budget buttons).
5. **Save/TestRun/Delete sticky-actions inerti**: `agent-form.js:245` faceva
   `getElementById('save-btn').addEventListener` ma v6 usa `#btn-save`
   → TypeError → IIFE crashava prima di registrare anche `run-btn` /
   `delete-btn`. setupStickyActions cercava `saveAgent`/`runAgent`/
   `deleteAgent` come globali che non venivano definite.
6. **Crash IIFE su `#usage-reset-btn`**: `usage.js:74` setava `.onclick`
   su id legacy global rimosso in v6 → TypeError.
7. **Crash IIFE su `#run-btn`**: stesso pattern, v6 usa `#btn-test-run`.
8. **Path "Nuovo agente" form vuoto**: la sequenza di reset (clear fields,
   `_triggersLoad([])`, `_entitySelectorLoad([])`, `_actionsLoad([])`,
   `buildToolChecks([])`, `buildActionChecks([])`, `_buildTriggerOnChecks`,
   `showAgentMode('agent')`, ecc) era nel `#new-btn` IIFE handler, mai
   chiamato in v6.
9. **Model dropdown vuota**: `loadModels()` non veniva mai chiamato.

### Fix (tutti in `agent-editor.js`)

- **`addLegacyShims` esteso** con `save-btn`, `run-btn`, `usage-reset-btn`
  per evitare TypeError IIFE.
- **`rewireLegacyAfterMount()`**: rebinda via `.onchange/.onclick/.oninput`
  i 23 listener IIFE-time sui nodi v6 attuali ad ogni mount.
- **`populateTemplateSelector()` + `loadModels()`** chiamati dopo
  `ensureLegacy()` (idempotenti, OK al re-mount).
- **`initNewAgent()`** replica la sequenza di reset del vecchio `#new-btn`
  IIFE handler quando `mount(null)`.
- **Globali `window.saveAgent` / `runAgent` / `deleteAgent`** definite in
  agent-editor.js (riusano `buildPayload()` da agent-form.js) — sticky-actions
  callback ora collegate a logica reale.
- **`resolveAgent(agentId)`**: id → agent object via HirisState cache o
  fetch `api/agents`, popola anche `window.agents` per renderList() legacy.

### Test

- pytest 562/562 passed (zero regressioni backend)
- node -c syntax OK su agent-editor.js (733 LOC, +400 vs v0.10.0)

## v0.10.0 — Agent Designer v6 redesign (2026-05-07)

Refactor completo della pagina `config.html` (Agent Designer) come applicazione
multi-route con long-form editor.

### Highlights

- **Multi-route hash router** (`#/`, `#/agents`, `#/agents/:id`, `#/proposals`,
  `#/usage`, `#/settings`) — deep-link supportato, navigazione naturale.
- **Long-form editor** — i 6 tab orizzontali sostituiti da 9 section-card
  scrollabili con anchor nav a destra (IntersectionObserver active state) e
  sticky save bar in fondo.
- **Log row v6** — click ovunque sulla riga espande inline (accordion, una sola
  aperta), mid-truncation per testo lungo, filter chips
  (tutti / ok / err / thinking), copia summary + copia raw JSON, ESC chiude.
- **Action editor in drawer** — il builder azioni esce dall'inline e si apre
  come drawer da destra full-height.
- **Nuovo tipo azione "▶ Esegui script HA"** — wrapper friendly su
  `call_service domain=script` con script picker + variables JSON.
- **Cron chip + popover** — i 5 select inline diventano un chip
  `Ogni giorno alle 06:00` che apre un popover con 6 preset
  (orario/mattino/sera/lunedì/weekend/custom).
- **Dashboard adaptive** — stato vuoto = onboarding + template gallery, stato
  popolato = 4 stat tile + log cross-agent + proposte peek + prossimi trigger.
- **Proposte automazione** — terminologia allineata: badge `→ automazione HA`,
  buttons `Attiva` / `Rifiuta`, una proposta attivata genera una automation HA
  nativa (semantica esistente, ora chiara nella UI).

### Internal

- 13 nuovi moduli JS in `hiris/app/static/config/`: `state.js`, `router.js`,
  `dashboard.js`, `agent-editor.js`, `agents-list.js`, `log-row.js`,
  `drawer.js`, `popover.js`, `script-action.js`, `cron-popover.js`,
  `proposals-route.js`, `usage-route.js`.
- Token v6 additivi in `hiris-theme.css` (spacing scale 4-base, typography
  ramp, layout dims, elevations). Zero rinomine v5.
- Atom CSS v6 in `hiris-config.css`: `.app-shell`, `.section-card`,
  `.anchor-nav`, `.sticky-actions`, `.drawer`, `.popover`, `.log-row`, ecc.
- Translations IT+EN: ~50 nuove chiavi sotto namespace `designer.*`.
- Test browser-based in `tests/static/test_*.html` per moduli JS chiave
  (state, router, drawer, popover, log-row).
- Backend Python: zero modifiche. Suite 562/562 passed invariata.
- Chat surface (`index.html`, `hiris-chat-card.js`): zero impatto.

### Migration

- Nessuna migration richiesta. Schema agent invariato.
- URL `config.html` → ridireziona a `#/`. Bookmark `#/proposals` etc. valido.
- Action `script` salvata come `call_service domain=script`, retro-compat completa.

### Removed

- File backup `config.legacy.html` (era temporaneo per consultazione).
- Regole CSS legacy obsolete (`.tab-btn`, `.agent-tabs`).

### Reference

- Design doc: `docs/superpowers/specs/2026-05-07-hiris-agent-designer-v6-design.md`
- Implementation plan: `docs/superpowers/plans/2026-05-07-hiris-agent-designer-v6.md`

## [0.9.10] — 2026-05-05

### Added — Gestione consapevole modelli OpenRouter `:free`

OpenRouter è il provider HIRIS dedicato all'uso gratuito. I modelli `:free`
hanno però quote giornaliere basse (specialmente con account a $0 di
credito) e vengono routinariamente rate-limited dai provider upstream
(Venice, Together, ecc.). v0.9.10 introduce tre meccanismi per non
bruciare quota e per dare visibilità all'utente:

- **Badge `• free` nel dropdown modelli** (`static/config/api.js`): ogni
  modello con suffisso `:free` viene mostrato con marker visibile + tooltip
  *"quota giornaliera bassa e rate-limit upstream frequenti, sconsigliato
  per agenti schedulati"*.
- **Warning bloccante al save di agente autonomo su `:free`**
  (`handlers_agents._validate_free_model_for_agent_type`): `POST/PUT
  /api/agents` rifiuta con HTTP 400 se `agent.type == "agent"` e
  `agent.model.endswith(":free")`. L'utente può accettare il rischio
  ripetendo il save con `confirm_free_for_agent: true` nel payload. Chat
  agent su `:free` restano consentiti senza attriti (uso a basso volume).
- **Backoff automatico per agente su rate-limit ripetuti**
  (`agent_engine`): nuovo `_record_rate_limit_failure()` /
  `_is_in_rate_limit_pause()`. Quando un agente schedulato riceve
  `AGENT_RATE_LIMIT_THRESHOLD=3` risposte rate-limited entro
  `AGENT_RATE_LIMIT_WINDOW_SEC=600s`, viene messo in **cooldown** per
  `AGENT_RATE_LIMIT_COOLDOWN_SEC=3600s`. Le esecuzioni schedulate durante
  il cooldown vengono saltate (no chiamata al runner) e logged.
- **Toggle "Nascondi modelli :free di OpenRouter"** in *Settings →
  Add-ons → HIRIS → Configurazione*, posizionato subito sotto la chiave
  OpenRouter. Quando attivo, i `:free` non compaiono affatto nel dropdown
  modelli. Implementato come `hide_free_models: bool` in `config.yaml`,
  esportato come `HIRIS_HIDE_FREE_MODELS` da `run.sh`. Stessa env var
  resta disponibile per chi preferisce gestirla via shell.
- **UI checkbox "accetto rischi free-tier"** nel Designer agente
  (`config.html` + `agent-form.js`): nel tab Modello compare un checkbox
  visibile solo quando `type=agent` E `model` termina con `:free`. Quando
  spuntato il save include `confirm_free_for_agent: true` bypassando il
  warning server-side. Caricamento di agente esistente con `:free` →
  pre-checkato (perché il save passato è andato a buon fine).

### Added — Configurazione timeout Ollama da addon UI
- Nuovo campo `local_model.request_timeout` (int, default 120, range
  10–1800) in `config.yaml` schema/options. `run.sh` lo esporta come
  `OLLAMA_REQUEST_TIMEOUT` letto da `OpenAICompatRunner`. Compare
  automaticamente in *Settings → Add-ons → HIRIS → Configurazione*. Utile
  per hardware lento (Pi 5 con `gemma2:9b` in genere richiede 240–300s
  contro il default 120). Translations IT/EN aggiornate.

### Test
- Suite: 543 + 19 nuovi = 562 test, tutti pass.
- Fix #11 e #12 sono modifiche solo a UI/config addon (no logica Python
  nuova) → nessun test aggiunto, copertura esistente sufficiente.

## [0.9.9] — 2026-05-05

### Fixed — Tre buchi residui dopo v0.9.8 (validazione, history, UX errori)

v0.9.8 ha fermato la creazione di nuovi turni "tossici" ma:
- la **chat history già salvata** prima dell'upgrade continuava a essere
  rispedita al modello ad ogni turno → degradazione persistente,
- gli **agenti già configurati** con `nousresearch/hermes-3-llama-3.1-405b:free`
  continuavano a fallire con HTTP 404 finché l'utente non cambiava modello,
- gli errori `429 rate-limited upstream` dei modelli OpenRouter `:free` si
  presentavano come opaco "Errore temporaneo del servizio AI" senza
  istruzioni utili.

#### Fix
- **`chat_store.load_history()`**: filtra automaticamente i messaggi assistant
  tossici (tool-call leakate via pattern `<id><non-ASCII>`, errori sintetici
  noti, prefissi credit-exhausted / tool-leak). Quando un assistant è
  scartato anche il suo user immediatamente precedente viene rimosso, per
  non lasciare turni orfani senza risposta. **Nessuna azione richiesta agli
  utenti**: chat esistenti si auto-puliscono al prossimo caricamento.
- **`PUT/POST /api/agents`**: nuovo `is_openrouter_model_tool_capable()` in
  `handlers_models.py` consulta il campo `supported_parameters` di
  OpenRouter. Se il modello non supporta i tool, il save viene rifiutato
  con HTTP 400 e un messaggio che spiega perché e suggerisce alternative.
  Modelli non-OpenRouter (Claude/OpenAI/Ollama) non triggherano nessuna
  chiamata di rete extra.
- **`handlers_chat.py`**: dopo `runner.chat()` / streaming, se la response
  matcha il filtro tossico, NON viene persistita in chat_store (né user
  né assistant). Future turni non ereditano più storia degradata.
- **`OpenAICompatRunner`**: nuovo `parse_upstream_rate_limit()` traduce
  `qwen/...:free is temporarily rate-limited upstream` in messaggio
  italiano azionabile (suggerisce retry, modello a pagamento, o aggiunta
  API key del provider su openrouter.ai).

### Test
- Suite: 521 + 22 nuovi = 543 test, tutti pass.

## [0.9.8] — 2026-05-05

### Fixed — OpenRouter quality regressions (multi-causa)
Quattro bug indipendenti emersi insieme su agenti chat con OpenRouter
(`mistralai/mistral-large` e modelli `:free`) causavano risposte degradate
o incoerenti turno dopo turno. Tutti corretti in un singolo release.

- **Tool-call leakati come testo** (CRITICO): alcuni provider routati da
  OpenRouter (Mistral, Hermes) non traducono i token speciali nativi del
  modello (es. `[TOOL_CALLS]`) nello schema OpenAI `tool_calls`. La risposta
  arrivava come `content` testuale del tipo `get_ha_healthיׂ{"sections":["all"]}`
  e veniva persistita pari pari in chat history, inquinando il prompt dei
  turni successivi (il modello vedeva la propria robaccia e degradava
  ulteriormente). Fix: nuovo helper `detect_leaked_tool_call()` in
  `OpenAICompatRunner` rileva il pattern `<tool_name><non-ASCII>` e — se il
  nome combacia con un tool effettivamente disponibile — sostituisce la
  risposta con un messaggio chiaro all'utente (cambia modello / disattiva
  tool). Stesso check anche in `chat_stream` con evento SSE
  `discard_collected` per pulire i token già renderizzati nella Lovelace
  card. 8 test regressivi.
- **Mojibake nel context casa**: `proxy/semantic_context_map.py` conteneva
  letterali doppio-encodati (UTF-8 bytes letti come CP1252 e ri-encodati
  come UTF-8): `Umidità` → `UmiditÃ\xa0`, `·` → `Â·`, `°` → `Â°`,
  `→` → `â†→`, `—` → `â€—`, `₂` → `â‚‚`, `×` → `Ã—`. 22 sostituzioni
  applicate. Il context era visibile direttamente nel system prompt di
  ogni turno e degradava le risposte. 3 test di regressione che vietano
  marker mojibake nelle label `ENTITY_TYPE_SCHEMA`, nei concept
  `CONCEPT_TO_TYPES` e nell'output di `get_context()`.
- **Modelli OpenRouter senza tool support nei suggeriti**: il preset
  includeva `nousresearch/hermes-3-llama-3.1-405b:free` che fallisce con
  HTTP 404 `"No endpoints found that support tool use"` su ogni chiamata.
  Fix: `_fetch_openrouter_models` ora filtra usando il campo
  `supported_parameters` di OpenRouter (`tools` o `function_calling`).
  Il preset hermes-3 è stato rimosso. Nuovo file
  `tests/test_handlers_models_openrouter.py` con 8 test.
- **`max_tokens=4096` rigido vs credito OpenRouter limitato**:
  l'errore HTTP 402 `"can only afford 3907"` si propagava come
  `"Errore temporaneo del servizio AI"` opaco. Fix: nuovo
  `parse_afford_limit()` estrae il limite affrontabile dal messaggio,
  e `chat()` / `chat_stream()` riprovano una volta con `max_tokens`
  clampato (-5% safety). Se anche il retry fallisce, errore esplicito
  che indica all'utente di abbassare `max_tokens` dell'agente o
  aggiungere credito.

### Test
- Suite: 496 + 25 nuovi = 521 test, tutti pass.

## [0.9.7] — 2026-05-05

### Fixed (regression hotfix)
- **TypeError su agent non-Claude**: agent autonomi configurati su modelli
  Ollama / OpenAI / OpenRouter crashavano con `TypeError:
  OpenAICompatRunner.chat() got an unexpected keyword argument
  'thinking_budget'` al primo trigger. Regressione introdotta in v0.9.5
  quando il parametro `thinking_budget` è stato aggiunto a `ClaudeRunner`
  per Anthropic Extended Thinking; `LLMRouter` forward `**kwargs` a tutti i
  runner ma `OpenAICompatRunner` non aveva il parametro nella firma.
  Fix: `OpenAICompatRunner.chat`/`chat_stream`/`run_with_actions` ora
  accettano `thinking_budget: int = 0` come parametro silentemente
  ignorato (non esiste un equivalente nell'API OpenAI-compatible).
  `OpenRouterRunner` eredita da `OpenAICompatRunner` → fix automatica.
- 3 test regressivi aggiunti in `test_openai_compat_runner.py`.

## [0.9.6] — 2026-05-05

### Added — OpenRouter provider
- Nuovo backend **OpenRouter** (`hiris/app/backends/openrouter_runner.py`)
  come quarto provider HIRIS, accanto a Claude / OpenAI / Ollama.
  OpenRouter ([openrouter.ai](https://openrouter.ai/)) è un proxy unificato
  che dà accesso a 200+ modelli con una sola API key, inclusi modelli
  gratuiti marcati `:free` (Llama 3.3 70B, Gemma 3 27B, Qwen 2.5 72B,
  DeepSeek Chat, Mistral Nemo, Hermes 3 405B).
- Configurazione: nuovo campo `openrouter_api_key` nelle opzioni dell'addon
  (`config.yaml` + `run.sh` + `translations/{en,it}.yaml`).
- Routing: il prefix `openrouter:` o `openrouter/` davanti al model name
  (es. `openrouter:meta-llama/llama-3.3-70b-instruct:free`) instrada a
  OpenRouter via `LLMRouter`. Strategy chain aggiornata a
  `claude > openai > openrouter > ollama` (balanced/quality_first) e
  `ollama > openrouter > openai > claude` (cost_first).
- `/api/models` espone la lista live dei modelli OpenRouter disponibili
  con preset curati (12 modelli più richiesti) + tutti i `:free` aggiuntivi.

### Fixed — Ollama hang con modelli reasoning (Gemma 4, Qwen QwQ, DeepSeek R1...)
- Bug: agent autonomi configurati su modelli Ollama con thinking-by-default
  timeoutavano dopo 300s con 0/0 token e nessun log diagnostico — il modello
  restava bloccato emettendo solo blocchi `thinking` mentre `content` restava
  vuoto, fino a quando httpx 120s + 2 retry SDK (~360s) superavano il wrapper
  `agent_engine` 300s.
- Fix: tre interventi in `OpenAICompatRunner` quando `fixed_model` (Ollama):
  1. `extra_body={"think": False}` passato via OpenAI SDK a tutte le chiamate
     (`chat`, `chat_stream`, `simple_chat`). I modelli senza thinking lo
     ignorano, quelli con thinking lo disattivano.
  2. `max_retries=0` sul AsyncOpenAI client per Ollama (default SDK = 2).
     Il primo errore/timeout viene loggato e ritornato invece di hang × 2.
     Cloud OpenAI mantiene il retry default (rete cloud più affidabile).
  3. Logging info pre/post chiamata Ollama (model, iter, agent, tools,
     msg_chars, finish_reason, content_len, tool_calls). Per future indagini.

### Added — Documentazione privacy
- Nuova sezione **"Provider AI e privacy"** in `docs/guida-configurazione.md`
  e `docs/configuration-guide.md`, con:
  - Tabella decisione "quale provider scegliere" per use case
  - Tabella privacy per provider (cosa esce di casa, giurisdizione, costo,
    link policy) per Claude / OpenAI / OpenRouter / Ollama
  - Definizione di "cosa intende HIRIS per messages" per chat vs agent autonomi
  - Lista esplicita di "cosa NON esce mai" per nessun provider
- Disclaimer privacy aggiunto alle descrizioni dei campi cloud nelle
  translations IT/EN: l'utente vede in UI HA addon il dettaglio "i dati
  passano da X (giurisdizione Y) — vedi policy Z".

### Tests
- 4 nuovi test in `test_openai_compat_runner.py` (max_retries 0/2,
  extra_body presence/absence per Ollama vs OpenAI cloud)
- 6 nuovi test in `test_llm_router.py` (routing prefix colon/slash,
  Claude precedence, strategy chain, prefix strip helper, runner init)
- Suite ora 493/493 pass

## [0.9.5] — 2026-05-05

### Added
- **Extended Thinking** support per agente. Nuovo campo `thinking_budget`
  sull'Agent (default 0 = disabilitato). Quando >0 e il modello e'
  thinking-capable (sonnet-4.5+/opus-4+) il runner passa
  `thinking={"type":"enabled","budget_tokens":N}` a `messages.create`.
  - I thinking blocks vengono catturati dal runner e salvati in
    `execution_log[].thinking_blocks` (troncati a 2000 char/block).
  - Designer UI: nuovo `<select>` Extended Thinking budget con preset
    0 / 2048 / 4096 / 8192 / 16384.
  - Execution log UI: chip pill `💭 thinking` accanto a ogni row con
    blocchi presenti; click apre un pannello mono con il chain-of-thought
    numerato per step.
  - Validation difensiva (handlers + runner): blocca budget < 1024 o
    >= max_tokens, ignora silenziosamente su modelli non capable invece
    di fallire con un 400 Anthropic.
  - Chat handler include `debug.thinking_blocks[]` nella response JSON
    quando thinking e' attivo (consumabile dal client per debug).

### Changed (perf)
- **Prompt cache reorder** in `claude_runner.chat()`: i prompt di
  comportamento (`RESTRICT_PROMPT`, `REQUIRE_CONFIRMATION_PROMPT`,
  `response_mode` prompts) ora precedono il `context_str` query-dependent.
  Anthropic richiede cache contigue dall'inizio: prima questi blocchi
  cadevano *dopo* il context_str non-cached e venivano riemessi fresh.
  Ora il cache breakpoint si estende a includerli (cumulativo). Risparmio
  tipico: ~250 input token aggiuntivi cached per richiesta su agenti con
  `restrict_to_home` + `response_mode='compact'`.

### Tests
- 14 nuovi test (4 dataclass `thinking_budget`, 10 runner
  `_build_thinking_param` + integration). Suite ora 483 pass.

## [0.9.4] — 2026-05-05

### Fixed (security)
- **CVE-2026-34450** + **CVE-2026-34452**: bump floor `anthropic` da
  `>=0.55.0` a `>=0.87.0`. I due CVE affettano il "Local Filesystem
  Memory Tool" della SDK anthropic nelle versioni 0.55-0.86:
  - CVE-2026-34450 (file permissions 0o666 → leak state agente)
  - CVE-2026-34452 (path validation race → sandbox escape via symlink)

  HIRIS non usa `client.beta.memory.*` (il nostro `memory_tool` è un
  MemoryStore SQLite custom indipendente dall'SDK), quindi non eravamo
  direttamente vulnerabili. Tuttavia il range `>=0.55,<1.0` permetteva
  l'installazione di SDK con la feature vulnerabile presente. Floor
  alzato per igiene security.

## [0.9.3] — 2026-05-04

### Fixed (security)
- **CVE-2026-22815, 34513-34520, 34525**: bump `aiohttp` da `>=3.10.11` a
  `>=3.13.4`. Chiude 10 CVE pubblicati il 2026-04-01: trailer DoS,
  DNS cache DoS, CRLF injection multipart, Windows UNC SSRF/NTLMv2 leak,
  multipart bypass DoS, multipart memory DoS, cookie/proxy-auth leak su
  cross-origin redirect, response splitting, null byte/control char in
  response headers, duplicate Host headers.
- **CVE-2026-28684**: bump `python-dotenv` da `==1.0.1` a `>=1.1.0`.
  Chiude vulnerabilità Link Following.

### Changed (deps refresh)
- `anthropic` da `==0.40.0` (pinned, 57 release indietro) a
  `>=0.55.0,<1.0.0`. Le API in uso (`AsyncAnthropic`, `messages.create`,
  `APIStatusError`) sono stabili da 0.30+, no breaking attesi.
- `apscheduler` da `==3.10.4` a `>=3.11.0,<4.0.0` (3.x stable, 4.x ancora alpha).
- `pytest` da `==8.3.2` a `>=9.0.0,<10.0.0`.
- `pytest-asyncio` da `==0.23.8` a `>=1.0.0,<2.0.0`. La suite usa già
  `@pytest.mark.asyncio` esplicito su ogni test → strict mode 1.x compat.
- `pytest-aiohttp` da `==1.0.5` a `>=1.1.0,<2.0.0`.
- `openai` da `>=1.0.0` (range troppo ampio) a `>=2.0.0,<3.0.0`. API in
  uso (`AsyncOpenAI` con api_key/base_url/timeout) invariata tra 1.x e 2.x.
- `httpx` da `>=0.27.0` a `>=0.28.0,<1.0.0`.

### Removed (dead deps)
- `aiohttp-cors` rimosso dai requirements: era pinned a `==0.7.0` ma mai
  importato dal codice (zero match grep su `aiohttp_cors` / `aiohttp.cors`
  in `hiris/app/`).

### Improved
- `Dockerfile` cache buster aggiornato da `"HIRIS v0.6.12"` (stantio dalle
  release 0.7→0.9.2) a `"HIRIS v0.9.3 — full deps refresh"`. Forza il
  rebuild del layer pip install nel container HA Supervisor in modo che
  le nuove versioni vengano effettivamente installate.

### Verified
- Suite di test 469/469 pass su environment locale che gira già le
  versioni target (aiohttp 3.13.3, openai 2.33.0, httpx 0.28.1,
  pytest 9.0.2, pytest-asyncio 1.3.0).

## [0.9.2] — 2026-05-04

### Fixed (security)
- **SEC-022** `trigger_automation` / `toggle_automation` ora rispettano
  `allowed_services` e `allowed_entities` per agente. Prima un agente con
  whitelist limitata (es. `light.*`) poteva firare qualsiasi automation HA.
- **SEC-022b** `automation_id` validato contro injection: regex `^[a-z0-9_]+$`
  prima di costruire `entity_id` per call_service.
- **SEC-023** Middleware auth interno non si fida più della sola presenza
  dell'header `X-Ingress-Path`: ora valida il pattern reale di HA Supervisor
  (`/api/hassio_ingress/<token>/...`).
- **SEC-024** `SemanticContextMap` ora sanitizza `friendly_name`, `state`,
  `hvac_mode`, `media_title`, area name, e knowledge_db annotations da HA
  prima di iniettarle nel system prompt della chat (prima il filtro era
  applicato solo agli agent autonomi → vector di prompt-injection persistente).
- **SEC-025** Nuovo CSRF middleware globale: richiede `X-Requested-With` su
  POST/PUT/DELETE `/api/*`. Tutti i fetch client lato HIRIS lo inviano.
- `tools/http_tools.py` non logga più la query string dell'URL (token leak).

### Fixed (bug)
- **F-CRIT-1** Task DELETE usa path relativo `api/tasks/...` invece di assoluto
  `/api/tasks/...` (sotto HA Ingress il path assoluto faceva 404).
- **F-CRIT-2** Onboarding: tipi agent allineati a backend (`chat`/`agent`),
  payload `triggers` (plurale) corretto invece di `trigger`. Prima i Monitor
  preset venivano creati senza alcun trigger schedulato.
- **F-ALTO-1** Race condition in `setActiveAgent`: switching rapido tra agenti
  prima del completamento della fetch history non popola più la chat sbagliata.
- `agent_engine.delete_agent` ora pulisce `memory_store` e chat history
  associati (no più dati orfani in `/data/hiris_memory.db` e `/data/chat_history.db`).
- Locking thread-safe per `_save()` JSON in `agent_engine`, `task_engine`,
  `health_monitor`, `semantic_context_map`: due chiamate concorrenti non
  corrompono più il file `.tmp` durante `os.replace`.

### Changed (perf)
- HTML statici (`index.html`, `config.html`) cached a startup invece di
  `open().read()` sync per request — non blocca più l'event loop.

### Removed (dead code)
- `hiris/app/backends/claude.py` (`ClaudeBackend` mai importato in produzione).
- `hiris/app/proxy/home_profile.py` (sostituito da `SemanticContextMap`).
- `KnowledgeDB.record_correlation` / `record_query_hit` mai chiamati.
- `SemanticContextMap.add_entity` / `remove_entity` mai chiamati.
- Selettori CSS `.badge.{chat,monitor,reactive,preventive,cron}` mai emessi.
- Token CSS `--p-indigo` / `--p-blue` / `--p-cyan` / `--p-teal` mai referenziati.

### Improved (a11y)
- Tap target ≥44px (WCAG 2.5.5) su touch device per `#theme-toggle`,
  `.task-cancel-btn`, `.entity-chip .chip-remove`, `.action-item .ai-remove`.
- Lovelace card rispetta `prefers-reduced-motion` (animazione `iris-breathe`,
  `bounce`, `spin` disattivate via media query nel template Shadow DOM).

### Improved (qualità)
- `addEventListener` al posto di `.onclick` / `.onchange` in `agent-form.js`
  (no overwrite silenzioso se più handler vengono attaccati).
- Save / delete agent nel designer mostra ora un messaggio di errore se la
  fetch fallisce (prima falliva in silenzio).
- 7 punti `except Exception: pass` ora loggano almeno a debug/warning.
- Funzione `escapeHtml()` deduplicata in `index.html` (rimasta solo `esc()`).
- Cleanup git: rimossi 4 worktree e 4 branch locali integrati + 4 branch
  remoti orfani (`origin/claude/*`); repo ora ha solo `master`.

### Tests
- Nuovo `tests/test_handlers_smoke.py` (14 test) per handler API senza
  copertura: `status`, `config`, `tasks`, `health`, `run_agent`.
- Nuovi test in `tests/test_security.py` per SEC-022, SEC-022b, SEC-025.
- Nuovi test in `tests/test_internal_auth_middleware.py` per SEC-023.
- Nuovi test in `tests/test_semantic_context_map.py` per SEC-024.
- Suite passata da 446 a 469 test (+23 net; +25 added, –2 obsoleti).

## [0.9.1] — 2026-05-03

### Changed — chat surface aligned to v5 mockup
- **Greeting time-of-day**: l'header del welcome ora dice
  "Buongiorno / Buon pomeriggio / Buonasera / Buonanotte" in base all'ora,
  invece del generico "Ciao". Si aggiorna ogni ora.
- **Agent picker pill** in alto a destra: pillola con avatar gradient
  (violet → fuchsia, prima lettera del nome agente), nome agente troncato
  a 140px, dot live verde. Sostituisce il vecchio "header-title plain".
  Si aggiorna automaticamente quando si seleziona un agente.
- **Quick chips con icona emoji** sul welcome: ⚡ Stato casa, 🌡 Temperatura
  camere, 💡 Consumi energia, ☀️ Briefing del mattino. Più riconoscibili
  a colpo d'occhio.
- **Tool calls come chip pill mono inline** invece del vecchio `<details>` con
  freccia espandi. Click sul chip apre/chiude un pannello arg sotto.
  Allineato al mockup v5.

### Fixed
- Cache-busting confermato funzionante: tutti gli asset (`hiris-chat.css?v=`,
  `static/config/*.js?v=`) ricevono il `?v=VERSION` via `_inject_version()`,
  garantendo refresh dopo upgrade dell'addon.

## [0.9.0] — 2026-05-03

### Changed — Design system v5 (UI overhaul)
- **Tipografia**: stack passato da Inter Tight a **Geist** (sans + Geist Mono),
  con fallback graceful su Inter Tight / system. Mono usato solo nei blocchi
  codice (system prompt, valori tecnici, log).
- **Palette**: tokens iris OKLCH (`hiris-theme.css`) raffinati; nuovo accent
  `--iris-glow` per ombre-luce, atom `.toggle` riusabile in stile iOS,
  petali iris (`--p-violet`/`--p-fuchsia`/…) per gradient send-button.
- **Top chrome moderno** in `index.html` e `config.html`: logo iris animato
  (breathing 6s), brand + version + breadcrumb, theme toggle persistente in
  localStorage (cascade: localStorage > server config > system).
- **Chat (`index.html`)**: greeting con gradient iris→fucsia su "come posso
  aiutarti?", suggerimenti come pill rotonde, input bar ovale con send button
  gradient, bubble user in iris-tint (non più solid accent), theme toggle.
- **Designer (`config.html`)**: spec sheet con tabs moderne (sliding underline
  iris), system prompt come blocco code-styled, contesto come chip filled/outlined,
  azioni primarie con `box-shadow` iris glow, runs timeline.
- **Lovelace card (`hiris-chat-card.js`)**: Shadow DOM aggiornato — header con
  iris breath + glow ambient, send button gradient, user bubble in iris-tint,
  font Geist con fallback.

### Added — Modular split (frontend)
- **CSS estratto** dagli inline `<style>` in file dedicati:
  - `static/hiris-chat.css` (549 righe)
  - `static/hiris-config.css` (1 095 righe — sezione legacy + sezione v5)
- **JS modulare** del Designer suddiviso in `static/config/`:
  - `api.js` — fetch + helpers (esc, fmtNum, fmtTok, applyTheme, loadModels, loadUsage)
  - `templates.js` — TEMPLATES + TOOLS + ACTIONS + populateTemplateSelector
  - `cron.js` — preset, builder, _cronDesc/Apply/InitUI
  - `triggers.js` — _agentTriggers + render/load/value
  - `permessi.js` — buildToolChecks, buildActionChecks, entity selector + domain pills
  - `action-editor.js` — _agentActions + ae-* editor handlers
  - `logs.js` — renderExecutionLog, toggleLogRow, token counter, context preview
  - `usage.js` — loadAgentUsage + budget/toggle/reset handlers
  - `proposals.js` — pending/archived workflow
  - `agent-form.js` — CRUD orchestration: openAgent, save/delete/run, buildPayload
  - `tabs.js` — switchTab, theme toggle, version footer
  - `main.js` — bootstrap
- **Risultato**: `config.html` da 2 779 → 473 righe (−83%); logica invariata,
  solo riorganizzazione di delivery (classic scripts, no bundler, scope globale).
- **Strategic doc** `PRODUCT.md` aggiunto al root (impeccable design context).

### Fixed
- `applyTheme()` ora rispetta `localStorage` come prima sorgente, evitando
  che il config server-side sovrascriva la preferenza utente al refresh.

## [0.8.9] — 2026-05-03

### Fixed
- **Startup crash con OpenAI/Ollama configurato**: `OpenAICompatRunner.__init__`
  passava `total=` a `httpx.Timeout`, che non accetta quel kwarg
  (`TypeError: Timeout.__init__() got an unexpected keyword argument 'total'`).
  Sostituito con argomento posizionale (`httpx.Timeout(timeout, connect=5.0)`),
  comportamento equivalente all'intent originale. Regressione introdotta in 0.8.7.

## [0.8.8] — 2026-05-02

### Fixed
- **Ollama streaming**: `chat_stream` riscritta con `stream=True` e assemblea fragmenti
  tool-call da chunk SSE — i token ora arrivano in tempo reale invece di buffered
- **JSON argomenti malformati**: quando un modello locale invia argomenti JSON non validi,
  viene restituito un errore esplicito al modello invece di passare `{}` al tool
- **Disambiguazione eval_instruction**: etichetta "Comandi AZIONI" ora include
  "(vanno scritti in testo nel blocco AZIONI:, NON come tool calls)" — riduce le
  chiamate spurie come tool OpenAI da parte di Ollama
- **`misfire_grace_time=60`** sui job interval (era già presente su cron) — evita
  skip silenzioso se l'agente parte con ritardo
- **Ollama health check all'avvio**: `server.py` verifica `/api/tags` e logga un warning
  se Ollama non è raggiungibile o il modello non è scaricato, senza bloccare lo startup
- **`MAX_TOOL_ITERATIONS`** e **`OLLAMA_MAX_TOOL_ITERATIONS`** configurabili via env
  (default 10/5)
- **Usage tracking**: log debug quando un modello locale non ritorna informazioni sui token

## [0.8.7] — 2026-05-02

### Fixed
- **Ollama/modelli locali**: `AsyncOpenAI` ora usa `httpx.Timeout(120s)` per Ollama
  (configurabile via `OLLAMA_REQUEST_TIMEOUT`), eliminando i hang fino a 600s su hardware lento
- **Agent engine**: `asyncio.wait_for(300s)` su ogni run di agente (configurabile via
  `AGENT_RUN_TIMEOUT`) come ceiling assoluto; risolve la cascata di
  `max instances reached` che bloccava APScheduler per ore
- **Tool dispatcher**: messaggio di errore direttivo per tool sconosciuti (es. `search_entities`)
  con istruzione esplicita a non inventare nomi; riduce loop di allucinazione sui modelli locali
- **Ollama tool injection**: lista esplicita dei tool disponibili iniettata nel system prompt
  per i modelli locali, prevenendo chiamate a tool inesistenti

## [0.8.6] — 2026-05-01

### Added
- Cron builder ibrido nell'editor agenti: 13 preset comuni, builder visuale
  a 5 campi (min/ora/giorno/mese/sett.) e preview live in italiano;
  i chip nel trigger list mostrano la descrizione leggibile
- Supporto dominio `valve` (HA 2023.9+): classificazione in SemanticContextMap,
  attributi `current_position`/`reports_position` in EntityCache, pill "valvole"
  nel tab Permessi, azione `valve.*` nella whitelist; template irrigazione
  aggiornato con `open_valve`/`close_valve`

### Fixed
- MQTT: errori di autenticazione (code 135/134/5/4) ora loggati con livello
  ERROR e backoff massimo; errori di rete mantengono il backoff esponenziale
- CSS cache-busting: `?v=VERSION` iniettato nei path CSS/JS al serve time,
  forza invalidazione cache browser ad ogni release

## [0.8.5] — 2026-05-01

### Added
- Navigazione a schede nel pannello editor agenti: Identità · Istruzioni · Modello · Permessi · Azioni · Stato. Il tab Azioni si nasconde automaticamente per agenti di tipo "chat".

### Fixed
- Ripristinata palette Iris (OKLch) nella pagina Agent Designer: i blocchi `:root` hex legacy nell'inline `<style>` di `config.html` sovrascrivevano `hiris-theme.css`, rendendo inefficace il restyling grafico.

## [0.8.4] — 2026-04-30

### Changed
- Prompt engineering: `BASE_SYSTEM_PROMPT` ridotto a 5 righe eliminando la lista tool ridondante (già presente negli schemi JSON del parametro `tools`)
- Tool definitions ora cachate via `cache_control` sull'ultimo tool — risparmio su ogni chiamata con configurazione agente stabile
- Tool results vecchi nell'agentic loop compressi a 300 char (si mantengono completi solo gli ultimi 2 set) — riduce il context bloat su catene lunghe di tool calls
- Session summary riscritta come digest conversazionale (ultimi 3 scambi U→A, 120 char ciascuno) invece di troncamento dell'ultima risposta
- `context_str` strutturato con header espliciti (`## Memoria rilevante`, `## Sessioni precedenti`, `## Contesto casa`) per disambiguare la provenienza dei dati
- History truncation basata su token stimati (~6000) invece di conteggio fisso a 30 messaggi — evita esplosioni di contesto con risposte lunghe

## [0.8.3] — 2026-04-30

### Fixed
- `HealthMonitor`: ogni sezione del refresh (error_log, config_entries, system_info, updates) ora è isolata in un proprio try/except — un endpoint non disponibile non blocca più le altre sezioni
- `get_error_log()`: gestisce 403/404 gracefully invece di propagare l'eccezione
- MQTT: strip whitespace dalle credenziali lette da bashio (causa principale del codice 135 "Not Authorized"); client ID fisso `"hiris"` invece di UUID casuale; log di debug con host/user/password_len ad ogni tentativo di connessione

## [0.8.2] — 2026-04-30

### Changed
- `hiris-chat-card`: applicato Iris design system alla Shadow DOM (token `--i-*`, font Inter Tight + JetBrains Mono, bubble chat allineate a `index.html`, composer con focus ring, status pill)
- `hiris-chat-card`: dropdown agenti filtrato solo su `type === 'chat'` con hint "Solo agenti di tipo Chat"

## [0.8.1] — 2026-04-30

### Changed
- Iris design system: nuovo `hiris-theme.css` con palette oklch a 6 petali, tipografia Inter Tight + JetBrains Mono, light/dark automatico
- `index.html` completamente riscritto con il nuovo layout Iris (sidebar 280px, bubble chat, welcome screen con gradient, onboarding con radial glow)
- `config.html` aggiornato tramite `hiris-config-override.css` — zero modifiche alla logica JS esistente
- CSP aggiornata per consentire Google Fonts CDN (`fonts.googleapis.com`, `fonts.gstatic.com`)

## [0.8.0] — 2026-04-30

### Added
- **HealthMonitor**: hybrid health snapshot for HA — real-time unavailability tracking via WebSocket `state_changed` + full refresh every 30 minutes via APScheduler; persists to `/data/ha_health.json` across restarts
- **ProposalStore**: async SQLite store for automation proposals with 7-day archive / 30-day delete lifecycle; states: `pending → applied|rejected` (permanent) or `archived` (after 7d) → deleted (after 30d)
- **Tool `get_ha_health(sections)`**: reads the HealthMonitor snapshot — unavailable entities, integration errors, error log summary, pending HA updates, system info; available to all agent types (in `EVALUATION_ONLY_TOOLS`)
- **Tool `create_automation_proposal(...)`**: agents can propose new HA automations or HIRIS agents for human review instead of executing changes directly; chat agents only
- **REST API**: `GET /api/health/ha`, `POST /api/health/ha/refresh`, `GET /api/proposals`, `GET /api/proposals/{id}`, `POST /api/proposals/{id}/apply`, `POST /api/proposals/{id}/reject`
- **Agent Designer UI**: "Proposte automazione" section with pending/archived tabs; apply (with confirmation dialog) and reject actions; animated row feedback before removal

### Fixed
- **Security — XSS**: `renderProposals` replaced inline `onclick` handlers with `data-pid` attributes and `addEventListener`; `p.id` now escaped via `escHtml()` in HTML attribute context
- **Security — CSRF**: `apply` and `reject` POST endpoints require `X-Requested-With: XMLHttpRequest` header (403 otherwise); frontend fetch calls include the header
- **Validation**: `GET /api/proposals?status=` returns 400 for values outside `pending|applied|rejected|archived`
- **Code quality**: `HealthMonitor.start()` simplified — removed redundant `scheduler` parameter, always uses `self._scheduler`; `except Exception as exc:` cleaned to `except Exception:`
- **UX**: "Attiva" button shows confirmation dialog; `checkEmptyList()` uses active tab label; apply/reject show animated feedback before removing row
- **UI**: `proposal-desc` upgraded from single-line `white-space: nowrap` to 2-line `-webkit-line-clamp: 2`; load errors shown in red distinct from empty state; routing_reason labeled "Motivo:"

### Changed
- `docs/ROADMAP.md` removed from git tracking (added to `.gitignore`); Roadmap section removed from README
- All documentation updated: new tools, new components, new data stores, version headers to 0.8.0

## [0.7.0] — 2026-04-29

### Changed
- Refactored agent model to two types: **chat** (conversational NL) and **agent** (autonomous agentic loop with structured output)
- Post-review fixes to two-agent-type migration (naming, validation, UI consistency)

### Fixed
- Entity ACL bypass: agents can no longer access entities outside their allowed areas
- Prompt injection protection added to user-supplied fields
- CSP headers hardened on all aiohttp responses
- Dead code removed from agent runner and tool dispatcher

## [0.6.16] — 2026-04-29

### Added
- **Custom agent states** (`states` field): each non-chat agent can now declare its own VALUTAZIONE vocabulary instead of the fixed `OK|ATTENZIONE|ANOMALIA`; defaults unchanged for existing agents — fully backward compatible
- **`response_mode` per agent** (`auto` / `compact` / `minimal`): controls verbosity of agent responses; `minimal` uses key:value output for chat and a single-line motivation for non-chat agents
- **Irrigation agent template** ("Irrigazione Giardino"): preventive agent (`0 5 * * *`) that reads precipitation history + soil moisture + 48h forecast and schedules valve on/off via `create_task()`; uses `SKIP|LEGGERA|PIENA` states
- **SemanticContextMap**: added `precipitation`, `soil_moisture`, `weather` entity types; added concepts `irrigazione`, `irrigare`, `sprinkler`, `pioggia`, `piovuto`, `precipitazione`, `umidità suolo`, `giardino`, `meteo`, `previsioni`
- **Docs**: irrigation use case added to `docs/use-cases.md` and `docs/casi-duso.md`; tips sections updated to document custom states

### Changed
- **config.html**: trigger-on checkboxes are now dynamically generated from the agent's `states` field; "Modalità risposta" dropdown added; template selector now applies `type`, `cron`, `states`, `trigger_on` when a template is chosen; `f-states` blur listener rebuilds checkboxes preserving current selections

## [0.6.15] — 2026-04-29

### Changed
- **`config.yaml`**: sidebar icon changed from `mdi:robot` to `mdi:home-automation`

## [0.6.14] — 2026-04-29

### Added
- **`scripts/doc_check.py`**: documentation consistency checker run automatically before every release as step 3c; detects stale config key names (auto-fixes with `--fix`), broken cross-links, missing version headers, untracked docs, and README documentation table gaps; bypass with `--skip-doc-check` for emergencies
- **`scripts/release.py`**: `--skip-doc-check` flag added; step 3c calls `doc_check.py --fix` before the git-clean check so any auto-fixable stale keys are repaired and committed in the same release commit

### Fixed
- **`scripts/release.py`**: `_VERSIONED_DOCS` entry `ROADMAP.md` corrected to lowercase `roadmap.md` to match the actual filename (was working on Windows due to case-insensitive FS but would fail on Linux)

## [0.6.13] — 2026-04-29

### Added
- **`docs/full-local-mode.md`** / **`docs/full-local-mode-it.md`**: new guide for running HIRIS with zero cloud dependencies — Ollama model recommendations (Qwen2.5:27b, Mistral Small 3.1), full configuration example, performance comparison vs Claude, known limitations
- **`docs/mqtt-integration.md`**: new guide for MQTT auto-discovery — all published entities (`status`, `budget_remaining_eur`, `tokens_used_today`, `enabled`, `last_result`, `run_now`), control via MQTT topics, dashboard example, budget-warning automation example

### Fixed
- **README.md**: configuration table now uses correct nested key names (`local_model.url`, `local_model.model`, `mqtt.host`) — flat underscore names were stale since v0.6.6
- **README.md**: local-only mode note corrected — when `local_model.url` + `local_model.model` are set, HIRIS runs fully offline with Ollama (full agentic loop, all agent types); the old note said AI calls were always disabled when `claude_api_key` was empty
- **README.md**: Multi-provider LLM section clarified — automatic model selection (Sonnet for chat, Haiku for monitors) applies only when Claude is the provider; Ollama model is configured per-agent in the designer UI

## [0.6.12] — 2026-04-29

### Added
- **`model2vec` embedding provider**: fully local, no server, no API key required — the only embedding option compatible with Alpine Linux (HA add-ons); models are downloaded from HuggingFace Hub on first startup and cached in `/config/hiris/models/huggingface/`; recommended model is `minishlab/potion-base-8M` (~30 MB)
- **`run.sh`**: `HF_HOME` environment variable set to `/config/hiris/models/huggingface` so HuggingFace models persist across add-on restarts
- **Docs**: `docs/configuration-guide.md` and `docs/guida-configurazione.md` updated — Option C section replaced with model2vec (was fastembed); model2vec marked as recommended local option for HA add-ons

### Changed
- **`requirements.txt`**: replaced `fastembed>=0.3.0` with `model2vec>=0.8.0`
- **`Dockerfile`**: removed best-effort fastembed install step (model2vec installs cleanly on Alpine via musllinux wheels)
- **Translations** (`en.yaml`, `it.yaml`): embedding provider and model descriptions updated to mention model2vec

## [0.6.11] — 2026-04-29

### Fixed
- **Docker build failure**: `fastembed` depends on `onnxruntime` which has no pre-built wheels for Alpine Linux (musl libc) — the add-on image failed to build on all platforms; removed `fastembed` from `requirements.txt` and moved it to a best-effort `pip install || true` step in `Dockerfile` so the build never fails
- **`embeddings.py`**: `build_embedding_provider("fastembed")` now checks if fastembed is importable at startup and falls back to `NullEmbedder` with a log warning if not installed, instead of crashing on first use

## [0.6.10] — 2026-04-28

### Fixed
- **`run.sh`**: `bashio::config --raw` is not a valid bashio flag and caused 12 jq compile errors on every startup; replaced with `jq -c '.apprise_urls // []' /data/options.json` which reads the array directly from the HA options file — Apprise URLs were being silently ignored before this fix

## [0.6.9] — 2026-04-28

### Fixed
- **Chat input (`index.html`)**: textarea now grows dynamically as you type without ever showing a scrollbar (`overflow-y: hidden`); height cap raised to 40% of viewport height instead of the fixed 8rem/128px limit

## [0.6.8] — 2026-04-28

### Added
- **fastembed embedding provider**: fully local RAG with no external server or API key required; uses ONNX Runtime (ARM64/amd64 compatible); models cached in `/config/hiris/models/`; default model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` supports 50+ languages including Italian
- `fastembed>=0.3.0` added to `requirements.txt`
- Configuration guide updated with Option C (fastembed) section; translations updated with fastembed in provider description

## [0.6.7] — 2026-04-28

### Added
- **Configuration guide** (`docs/configuration-guide.md` / `docs/guida-configurazione.md`): step-by-step setup for Apprise notifications (Telegram, ntfy, Gotify, email, Discord, WhatsApp) and Memory/RAG (OpenAI embeddings, Ollama local embeddings, tuning parameters)
- README: links to new configuration guide docs

## [0.6.6] — 2026-04-28

### Changed
- **Config restructure**: options now grouped into logical nested sections (`local_model`, `mqtt`, `memory`) instead of flat underscore-prefixed keys; HA UI renders each group as a collapsible section
- **`run.sh`**: updated all `bashio::config` calls to dotted path notation (`mqtt.host`, `local_model.model`, etc.); added missing `LLM_STRATEGY` export (was always defaulting to `balanced` regardless of config UI)
- **Translations**: added `hiris/translations/en.yaml` and `hiris/translations/it.yaml` with human-readable labels and descriptions for all 18 configuration options in both English and Italian

## [0.6.5] — 2026-04-28

### Fixed
- **Chat UI (`index.html`)**: added `_isLoading` flag — Enter key can no longer trigger a second request while a response is in progress; send button shows a CSS spinner during generation
- **Lovelace card**: text typed in the input field is now preserved across streaming re-renders (previously lost on every token); send button shows a spinner and `title="Elaborazione…"` while loading; input placeholder changes to "Elaborazione…" during generation

## [0.6.4] — 2026-04-28

### Fixed
- `ClaudeRunner.__init__()` crashed on startup due to spurious `entity_cache` and `semantic_map` kwargs passed from `server.py` (introduced in v0.6.3)

## [0.6.3] — 2026-04-28

### Added
- **LLMRouter strategy**: `strategy` param (`balanced` / `quality_first` / `cost_first`) controls backend preference order; wired via `LLM_STRATEGY` env var and `llm_strategy` config option
- **LLMRouter fallback**: when `model="auto"`, if the primary backend raises an exception the next backend in the strategy chain is tried automatically
- `backends/pricing.py`: centralized USD/MTok pricing table for all supported models (Claude 4.x, GPT-4o/4.1/o-series, Ollama free); replaces duplicate `_PRICING` dicts in `ClaudeRunner` and `OpenAICompatRunner`

## [0.6.2] — 2026-04-28

### Fixed
- **SSRF**: `http_tools` now blocks IPv4-mapped IPv6 addresses (`::ffff:127.x`) and always disables redirects (redirects bypassed `_PinnedResolver`)
- **Entity leakage**: `allowed_entities` filter now applied to `get_home_status`, `get_entities_on`, `get_entities_by_domain` (was only enforced on `get_entity_states`)
- **Prompt injection**: RAG memories marked as untrusted data in system context; `debug.tools_called` response redacted to tool names only
- **Path traversal**: `agent_id` validated with regex in chat history handler
- **Auth bypass**: middleware now denies non-ingress requests by default when no `internal_token` is configured
- `ClaudeRunner.run_with_actions` now includes action instructions in augmented prompt (was inconsistent with `OpenAICompatRunner`)
- `openai_compat_runner`: imports hoisted to module top (were dynamic per-call)
- `handlers_agents`: `_validate_agent_payload()` validates type/name/trigger/budget on create and update

### Removed
- Dead `entity_cache`/`semantic_map` params from `ClaudeRunner` (unreachable branch in production)
- Dead `set_notify_config()` / `_notify_config` from `AgentEngine` (written, never read)

## [0.6.1] — 2026-04-28

### Added
- **Sprint D — Multi-provider LLM**: supporto OpenAI e Ollama per-agente; `OpenAICompatRunner`
  con loop agentico completo (tool use, `run_with_actions`); `ToolDispatcher` condiviso tra tutti
  i runner; `LLMRouter` ridisegnato come router reale; endpoint `/api/models` con lista dinamica
  (fetch live da OpenAI, `/api/tags` per Ollama); dropdown modello con `<optgroup>` per provider;
  `_PRICING_OAI` per tracking costi OpenAI/Ollama
- **Sprint C — Memory-RAG**: tabella `agent_memories` in SQLite; tool `recall_memory` / `save_memory`;
  RAG pre-injection nelle chat; `EmbeddingProvider` Protocol + `OpenAIEmbedder` + `OllamaEmbedder`
  + `NullEmbedder`; job APScheduler retention 03:00 UTC; config: `memory_embedding_provider`,
  `memory_embedding_model`, `memory_rag_k`, `memory_retention_days`, `history_retention_days`
- **Sprint B — Tool Expansion**: tool `create_calendar_event`; layer Apprise (80+ canali via
  `apprise_urls`); `EVALUATION_ONLY_TOOLS` frozenset; `Agent.trigger_on` + `AgentEngine._execute_agent_actions`;
  `on_fail: continue|stop` per azione; `TaskEngine` trigger `immediate`; UI: trigger_on checkboxes,
  on_fail dropdown, editor azioni child (wait/verify)
- **Sprint A — HA-Bridge**: MQTT 2-way subscribe (`hiris/agents/+/{enabled,run_now}/set`);
  nuove entità MQTT `last_result`, `budget_remaining_eur`, `tokens_used_today`, `run_now`;
  tool `http_request` con security strutturata (AllowedEndpoint, DNS pinning, RFC1918 DENY_NETS);
  `Agent.allowed_endpoints`

### Fixed
- **Sprint 0 — Bugfixes critici**: `handlers_agents.py` / `handlers_usage.py` usa
  `get("llm_router") or get("claude_runner")`; stub `app/ha_client.py` rimosso; `SemanticContextMap`
  persist/load JSON su restart; `EUR_RATE` centralizzato in `config`; MQTT pubblica stato su
  cambio `enabled`
- I/O file non bloccante: `_save()`, `_save_usage()`, `SemanticContextMap.save()` via
  `run_in_executor`

## [0.5.16] — 2026-04-27

### Fixed
- Lovelace card: server writes `hiris-ingress.json` to `/local/hiris/` at startup so the card discovers the real Supervisor ingress URL — resolves all card 503 errors
- Lovelace card: chat streaming hang fixed — timeout now covers the entire stream lifecycle; `streaming` flag cleared when stream closes even without SSE `done` event
- Lovelace card: replaced blinking cursor with animated typing indicator (HIRIS icon + three bouncing dots) matching the add-on's direct chat UI
- Lovelace card: removed duplicate status indicator from header — only the enable/disable toggle button remains in the top-right
- Lovelace card: switched all API calls from `hass.callApi()` to `fetch()` with explicit Authorization header
- Lovelace card: SyntaxError and constructor render crash blocking the HA card picker
- Docker: `config.yaml` now copied into the container so `read_version()` returns the correct version string instead of "unknown"

## [0.5.15] — 2026-04-27

### Fixed
- La card Lovelace restituiva HTTP 503 per tutte le chiamate API anche con il add-on attivo: il Supervisor HA assegna ad ogni add-on un token casuale come percorso ingress (`/api/hassio_ingress/{token}/`) invece dello slug, quindi il vecchio URL hardcoded `/api/hassio_ingress/hiris/` non veniva riconosciuto da HA
- All'avvio HIRIS interroga il Supervisor (`/addons/self/info`) per ottenere il proprio `ingress_url` reale e lo scrive in `/homeassistant/www/hiris/hiris-ingress.json` (file statico pubblico, nessuna auth richiesta)
- La card legge questo file una volta prima della prima chiamata API e usa l'URL corretto per tutte le operazioni; se il file non è disponibile usa l'URL basato sullo slug come fallback
- `HirisChatCardEditor._loadAgents()` migrato da `hass.callApi()` a `fetch()` con auth esplicita (stesso motivo)

## [0.5.14] — 2026-04-27

### Fixed
- `_fetchStatus()` e `_toggleAgent()` ora usano `fetch()` con auth esplicita invece di `hass.callApi()`: quest'ultimo fallisce su alcuni HA/Supervisor con percorsi di ingress, mostrando "HIRIS non disponibile" anche quando il backend è raggiungibile
- Il messaggio di errore nel chat ora mostra la causa reale dal body JSON del backend (es. "Claude runner not configured — set CLAUDE_API_KEY") invece del generico "HTTP 503"
- Estratti i metodi helper `_hirisUrl(path)` e `_authToken()` per eliminare la duplicazione della logica di autenticazione

## [0.5.13] — 2026-04-27

### Fixed
- `config.yaml` ora viene copiato nel container Docker (`COPY config.yaml /usr/lib/hiris/config.yaml`): `read_version()` restituiva sempre `"unknown"` in produzione perché il file non era presente, rendendo l'URL della risorsa Lovelace sempre `/local/hiris/hiris-chat-card.js?v=unknown` e vanificando il cache-busting introdotto in v0.5.12

## [0.5.12] — 2026-04-27

### Fixed
- La risorsa Lovelace ora viene registrata come `/local/hiris/hiris-chat-card.js?v=VERSION` invece dell'URL senza versione: ad ogni aggiornamento dell'add-on il vecchio URL viene rimosso e quello nuovo creato, forzando il browser a ricaricare il JS aggiornato (cache-busting)
- Migrazione automatica da tre tipi di URL obsoleti: vecchio ingress URL, vecchio URL senza versione, vecchio URL con versione diversa

## [0.5.11] — 2026-04-27

### Fixed
- `set hass()` in `HirisCard` non guardava contro `hass` null/undefined — il card picker di HA istanzia gli elementi e chiama il setter prima di `setConfig`, causando `TypeError` che HA interpreta come "card rotta" e rimuove silenziosamente dal picker
- `set hass()` in `HirisChatCardEditor` idem — impediva il caricamento dell'editor di configurazione
- `_loadAgents()` ora verifica `this._hass` prima di chiamare `callApi`
- `_sendMessage()` ora esce anticipatamente se `this._hass` non è disponibile
- `parseFloat` sul budget ora usa `Number.isFinite` per evitare `NaN.toFixed(2)` in template
- `customElements.define()` ora guarda con `customElements.get()` prima di registrare: se il file viene caricato due volte (hot reload HA) la `define()` non lancia più `NotSupportedError` che bloccava la `window.customCards.push()` sottostante
- `window.customCards.push()` ora deduplica con `.find()`: nessuna doppia registrazione nel picker
- `titleInput.oninput` → `onchange` nell'editor: HA chiama `setConfig` → `_render()` → `innerHTML` ricreato ad ogni tasto, causando perdita del focus; con `onchange` il focus si perde solo al blur
- `getCardSize()` ora restituisce 2 in stato non configurato (era 6: riservava troppo spazio verticale)

## [0.5.10] — 2026-04-27

### Fixed
- `SyntaxError: Identifier 'msgs' has already been declared` in `hiris-chat-card.js`: variabile `msgs` dichiarata due volte nella stessa funzione `_render()`, impediva il parsing del file e rendeva la card completamente invisibile in HA
- Rimosso `this._render()` dai costruttori di `HirisCard` e `HirisChatCardEditor`: il card picker di HA istanzia gli elementi custom prima di connetterli al DOM, causando ricorsione Shadow DOM tramite i mutation observer di Lit (`Maximum call stack size exceeded`)
- Aggiunto `connectedCallback` a `HirisChatCardEditor` in modo che il primo render avvenga nel momento corretto del lifecycle

## [0.5.9] — 2026-04-27

### Fixed
- `get_area_registry()` e `get_entity_registry()` migrati da REST
  (`/api/config/*/list`, restituiva 404 via Supervisor) a WebSocket
  (`config/area_registry/list`, `config/entity_registry/list`);
  il tool Claude `get_area_entities` ora funziona e le aree/stanze
  sono disponibili come contesto per gli agenti

## [0.5.8] — 2026-04-27

### Added
- **Lovelace card picker** — `window.customCards` registration, visual editor
  (`hiris-chat-card-editor`), `getStubConfig` returning `hiris-default`; card
  now appears in the HA "Add Card" picker without manual YAML

### Fixed
- **Lovelace resource registration** — switched from REST API
  (`/api/lovelace/resources`, returned 404 in many HA setups) to WebSocket API
  (`lovelace/resources/create/delete`); works in all storage-mode configurations
- **Card JS deployment** — add-on copies `hiris-chat-card.js` to
  `<ha-config>/www/{slug}/` on startup so `/local/{slug}/hiris-chat-card.js`
  resolves without authentication; probes `/config` then `/homeassistant`
- **Stale ingress URL migration** — removes old `/api/hassio_ingress/` resource
  automatically and registers the new `/local/` URL in its place
- `config:rw` added to add-on map (`config.yaml`) — required for www deployment
- `getCardSize()` implemented; `preview: false` set to prevent HA from
  attempting live renders in the picker

## [0.5.7] — 2026-04-27

### Fixed
- `_deploy_card_to_www()` ora prova sia `/config` che `/homeassistant` per trovare la directory di configurazione HA (il Supervisor monta il volume `config:rw` su `/config` nelle versioni correnti, non su `/homeassistant`); la funzione usa il percorso che contiene effettivamente `configuration.yaml` o `.storage`
- Aggiunta funzione `_find_ha_config_dir()` che individua il percorso corretto in modo robusto tra le versioni di Supervisor

## [0.5.6] — 2026-04-26

### Fixed
- `map: homeassistant:rw` replaced with `map: config:rw` — `homeassistant` is not a recognized HA Supervisor volume key and was silently ignored, leaving `/homeassistant` unmounted inside the container; the card copy appeared to succeed but wrote to the ephemeral container filesystem instead of the HA host, so `/local/hiris/hiris-chat-card.js` always returned 404
- `_deploy_card_to_www()` now verifies the HA config volume is actually mounted (checks for `configuration.yaml` or `.storage` at `/homeassistant`) before copying; logs a clear ERROR with actionable instructions if not, instead of silently "succeeding" with no visible failure

## [0.5.5] — 2026-04-26

### Fixed
- `setConfig` lancia eccezione su config null (contratto HA), resetta messaggi/polling al cambio agente
- Token SSE in `_sendMessage` usa `auth.accessToken` (HA 2024+) con fallback a `data.access_token`
- Rimossa costante `EUR_RATE` inutilizzata

## [0.5.4] — 2026-04-26

### Fixed
- Aggiunto `getCardSize()` → HA alloca la griglia correttamente senza mostrare shimmer di caricamento permanente
- `preview: false` nel registro `window.customCards` → il picker non tenta un render live (che richiede HIRIS attivo)
- `_fetchStatus()` usa `_patchStatus()` invece di `_render()` quando il DOM è già inizializzato → preserva il testo digitato nella chat
- `set hass()` usa `_patchStatus()` per aggiornamenti MQTT → nessuna sostituzione DOM su ogni cambio entity

## [0.5.3] — 2026-04-26

### Fixed
- Lovelace card JS ora servita via `/local/hiris/hiris-chat-card.js` invece dell'URL ingress (che richiedeva auth e restituiva 401 al browser)
- Aggiunto `map: homeassistant:rw` in `config.yaml` per consentire la copia del JS in `/homeassistant/www/hiris/` all'avvio
- Migrazione automatica: l'URL ingress stale viene eliminata da Lovelace resources e sostituita con quella `/local/`

## [0.5.2] — 2026-04-26

### Added
- Lovelace card picker: registrazione custom card, visual editor e stato "unconfigured"
- Lovelace card picker integration completa (v0.6.0 feature set)

### Fixed
- Code review findings post-picker integration

## [0.5.1] — 2026-04-25

### Added
- **Lovelace card auto-registration** — on startup HIRIS calls `POST /api/lovelace/resources` (via Supervisor token) to register `hiris-chat-card.js` as a UI module; idempotent, graceful in YAML-mode HA
- **Single-source versioning** — version read dynamically from `config.yaml` at runtime; `server.py` and `handlers_status.py` no longer hardcode it
- **Release script** — `scripts/release.py`: 10-step mechanical release executor (semver validation → changelog check → tests → git tag → GitHub Release); supports `--dry-run` and `--skip-tests`

## [0.5.0] — 2026-04-25

### Added
- **X-HIRIS-Internal-Token middleware** — HMAC-validated auth for inter-add-on requests (non-Ingress)
- **Enriched `/api/agents` response** — includes `status`, `budget_eur`, `budget_limit_eur` for Lovelace dashboard
- **SSE streaming for `/api/chat`** — Server-Sent Events path when `stream: true` or `Accept: text/event-stream`; Phase 1 pseudo-streaming (full response sliced into 80-char tokens)
- **`hiris-chat-card.js`** — vanilla JS Lovelace custom card (shadow DOM, 30s polling, SSE streaming, budget bar, toggle enable/disable)
- **MQTT Discovery publisher** — publishes `sensor.hiris_*_status/budget_eur/last_run` and `switch.hiris_*_enabled` via aiomqtt; exponential backoff reconnect; discovery messages queue during initial backoff

### Changed
- `config.yaml`: added `internal_token`, `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password` options
- `AgentEngine`: tracks running/error agent status; publishes MQTT state on each run

## [0.4.2] — 2026-04-24

### Fixed
- `internal_token` option uses `password` schema in `config.yaml` (masked in HA UI)
- HMAC comparison uses `hmac.compare_digest` (constant-time, prevents timing attacks)

## [0.4.0] — 2026-04-23

### Added
- **SemanticContextMap** — replaces EmbeddingIndex; organizes entities by area using `device_class` + domain classification; ~60% token reduction vs previous RAG
- **KnowledgeDB** — SQLite persistence for entity classifications, agent annotations, entity correlations
- **TaskEngine** — shared deferred-task system; 4 trigger types (`delay`, `at_time`, `at_datetime`, `time_window`); 3 action types; task persistence in `/data/tasks.json`
- **LLM Router** — routes standard inference to Claude, offloads `classify_entities()` to local Ollama when `LOCAL_MODEL_URL` configured
- **Task UI** — "Task" tab with pending-count badge; active + recent task list; cancel button; auto-refresh every 30s

### Removed
- `EmbeddingIndex` — replaced by `SemanticContextMap`
- `search_entities` Claude tool — removed with EmbeddingIndex dependency

## [0.3.0] — 2026-04-23

### Added
- **SemanticContextMap** — replaces EmbeddingIndex RAG and SemanticMap snippet; organizes all HA entities by area using native `device_class` + domain classification
- **ENTITY_TYPE_SCHEMA** — maps (domain, device_class) → (entity_type, label_it) for 30+ entity types, based on HA documentation
- **ContextSelector** — keyword-based query: extracts area + concept→type matches from user message, injects only relevant sections
- **Two-tier prompt injection** — compact home overview always present (~80 token); area/type detail expanded on match (~150 token); ~60% token reduction vs previous RAG
- **KnowledgeDB** — SQLite persistence for entity classifications, agent annotations, entity correlations, query patterns
- **Unified permission boundary** — `visible_entity_ids` from `SemanticContextMap.get_context()` used to validate all entity tool calls; consistent `allowed_entities` enforcement
- **EntityCache enriched** — `domain`, `device_class`, and typed attributes (hvac_mode, brightness, current_position, etc.) stored per entity for all domains

### Removed
- `EmbeddingIndex` — replaced by `SemanticContextMap` + `ContextSelector`
- `SemanticMap.get_prompt_snippet()` — replaced by `SemanticContextMap._format_overview()` + `_format_detail()`
- `search_entities` Claude tool — removed with EmbeddingIndex dependency

## [0.2.3] — 2026-04-22

### Added
- **TaskEngine** — shared deferred-task system available to all agent types (chat, monitor, reactive, preventive)
- **4 trigger types** — `delay` (minutes from now), `at_time` (wall-clock HH:MM local time), `at_datetime` (ISO datetime), `time_window` (poll every N min within a HH:MM–HH:MM window)
- **Optional condition** — entity state check at trigger time with operators `<`, `<=`, `>`, `>=`, `=`, `!=`; task skipped (not failed) if condition unmet
- **3 action types** — `call_ha_service`, `send_notification`, `create_task` (chaining: child task inherits `agent_id`, sets `parent_task_id`)
- **Task persistence** — tasks saved to `/data/tasks.json` with atomic write; pending tasks rescheduled on restart
- **Automatic cleanup** — terminal tasks (done/skipped/failed/expired/cancelled) deleted after 24h via hourly APScheduler job
- **3 Claude tools** — `create_task`, `list_tasks`, `cancel_task` available in `allowed_tools` per agent
- **REST API** — `GET /api/tasks`, `GET /api/tasks/{id}`, `DELETE /api/tasks/{id}`
- **Task UI** — "Task" tab in sidebar with pending-count badge; active task list + recent (24h) list; Annulla button for pending tasks; auto-refresh every 30s
- **Python 3.13** — upgraded base image from `3.11-alpine3.18` to `3.13-alpine3.21`

### Fixed
- `at_datetime` trigger called removed `_run_task_async` method — changed to `_execute_task`
- `_check_time_window` stored naive local timestamp in `executed_at` — now UTC-aware
- `create_task` tool dispatch now enforces agent's `allowed_services` whitelist on all `call_ha_service` actions before scheduling (previously bypassable via deferred tasks)
- Task UI: `label`, `result`, `error`, `status`, and `id` fields now HTML-escaped before injection into innerHTML (XSS prevention)
- `EntityCache`: added `get_state(entity_id)` method required by `TaskEngine` condition evaluation

## [0.2.2] — 2026-04-22

### Fixed
- `get_weather_forecast`: cast `hours` parameter to `int` to handle Claude passing it as string
- `get_energy_history`: cast `days` parameter to `int` for the same reason

## [0.2.1] — 2026-04-22

### Fixed
- `EntityCache.get_state()` method missing — caused `AttributeError` in `SemanticMap.get_prompt_snippet()` on production

## [0.2.0] — 2026-04-22

### Added
- **Semantic Home Map** — automatic rule-based + LLM-assisted classification of all HA entities into semantic roles (energy_meter, solar_production, climate_sensor, lighting, appliance, presence, door_window, etc.)
- **LLM Router** — thin routing layer that forwards standard inference to Claude and offloads `classify_entities()` to a local Ollama model when `LOCAL_MODEL_URL` is configured
- **LLM Backend abstraction** — `LLMBackend` ABC with `ClaudeBackend` and `OllamaBackend` implementations
- **Semantic prompt snippet** — structured home context injected into every Claude call (energy, climate, lights summary with live state)
- **SemanticMap persistence** — classification saved to disk and reloaded on startup; LLM re-classifies only unknown entities
- **HAClient entity registry listener** — SemanticMap updates automatically when new entities are added to HA
- **`get_home_status` enriched** — returns semantic labels from SemanticMap instead of raw entity IDs
- **Energy tools read SemanticMap** — `get_energy_history` resolves entity IDs from SemanticMap; no manual configuration needed
- **Config options** — `primary_model`, `local_model_url`, `local_model_name` in `config.yaml`
- **SSRF protection** — `OllamaBackend` validates URL and blocks cloud metadata endpoints (169.254.169.254, etc.)

### Security
- **CVE-2024-52304** — upgraded `aiohttp` to `>=3.10.11` (HTTP request smuggling)
- **CVE-2024-42367** — same upgrade covers path traversal via static routes
- **Prompt injection sanitization** — control characters stripped from entity names, states, units, and action fields before injection into system prompt (`handlers_chat.py`, `semantic_map.py`)
- **asyncio race condition** — `SemanticMap._classify_unknown_batch()` protected with `asyncio.Lock`
- **JSON schema validation** — `LLMRouter._parse_classify_response()` validates role against allowlist, clamps confidence, truncates fields; truncates raw response to 100 KB before parse
- **WebSocket reconnect** — `HAClient._ws_loop` now reconnects automatically after any disconnect (10 s backoff); listener callback exceptions are isolated

---

## [0.1.9] — 2026-04-22

### Added
- **RAG pre-fetch** — before each Claude call, HIRIS tokenizes the user message, finds semantically related entities via `EmbeddingIndex` (keyword overlap), fetches their live states from `EntityCache`, and injects them into the system prompt under "Entità rilevanti"
- `EmbeddingIndex` — in-memory keyword index built from entity names and IDs; no ML dependency
- `EntityCache` — in-memory entity state cache updated in real time from HA WebSocket events

### Fixed
- Include climate entity temperatures in EntityCache
- Default agent system prompt updated with correct tool signatures

---

## [0.1.8] — 2026-04-22

### Fixed
- Mobile UI: `100dvh` viewport height, `font-size: 16px` (prevents iOS auto-zoom), 44px send button, `enterkeyhint: send` on message input, safe-area insets for notch/home-bar

---

## [0.1.7] — 2026-04-22

### Added
- **Per-agent usage tracking** — token counts (input/output) and estimated cost in USD tracked per agent and model; reset endpoint available
- **Budget auto-disable** — agent auto-disables when cumulative cost (USD × 0.92) reaches `budget_eur_limit`; logs reason
- **Global usage endpoint** — `GET /api/usage` returns total tokens and cost across all agents
- **Agent usage endpoints** — `GET /api/agents/{id}/usage`, `POST /api/agents/{id}/usage/reset`

### Fixed
- Count global request tokens once per `chat()` call, not once per tool iteration
- Truncate conversation history to last 30 messages sent to Claude API

---

## [0.1.6] — 2026-04-21

### Added
- **Chat persistence** — server-side conversation history stored per agent in `/data/chat_history_<agent_id>.json`
- **Max chat turns** — `max_chat_turns` field on agent; chat returns `{error: "max_turns_reached"}` when limit is hit
- **Chat history endpoints** — `GET /api/agents/{id}/chat-history`, `DELETE /api/agents/{id}/chat-history`
- **New conversation button** — UI clears client-side history and calls delete endpoint
- **Turn counter** — displayed in chat UI header
- **`icon.png`** — add-on icon for HA Supervisor store
- `script.*` added to allowed action domains in agent designer

### Fixed
- Notify channel value corrected from `ha` to `ha_push` in Action Builder
- `agent_id` sanitized in chat store path to prevent path traversal

---

## [0.1.5] — 2026-04-21

### Added
- **Action Builder** — visual step editor for agent actions in the Config UI; supports `call_ha_service`, `send_notification`, and `trigger_automation` actions
- **Per-agent entity chips** — quick entity selector in agent designer; entities filtered by `allowed_entities` patterns
- **`strategic_context`** field on agents — house/family context prepended to every Claude system prompt

### Fixed
- Agent designer improvements merged from feature branch
- Four issues from final branch review

---

## [0.1.4] — 2026-04-20

### Added
- **Chat NL UI** — full conversation interface at `/` with real-time assistant responses, sidebar for agent selection, message history display
- **Agents CRUD API** — `GET/POST /api/agents`, `GET/PUT/DELETE /api/agents/{id}`, `POST /api/agents/{id}/run`
- **Agent Designer UI** — step-based editor at `/config` for creating and editing agents
- **`require_confirmation` mode** — Claude must ask user before executing `call_ha_service`
- **`restrict_to_home` mode** — agent refuses off-topic questions
- **`allowed_entities` filter** — glob-pattern entity whitelist per agent
- **`allowed_services` filter** — glob-pattern service whitelist per agent
- **Default agent seed** — `hiris-default` chat agent created automatically on first startup
- **Execution log** — last 20 runs logged per agent with tokens, tool calls, result summary, `eval_status`, `action_taken`

---

## [0.1.3] — 2026-04-20

### Added
- **Claude agentic loop** — multi-turn tool use loop (max 10 iterations) with retry logic (429/529: 5s → 15s → 45s → error)
- **8 built-in tools**: `get_entity_states`, `get_area_entities`, `get_home_status`, `get_energy_history`, `get_weather_forecast`, `call_ha_service`, `send_notification`, `get_ha_automations`, `trigger_automation`, `toggle_automation`
- **Notify tools** — HA push, Telegram, Retro Panel toast
- **Automation tools** — list, trigger, toggle HA automations
- **Weather tools** — Open-Meteo forecast (no API key needed)
- **Energy tools** — HA History API integration
- **HA tools** — entity states and area grouping

### Fixed
- `AsyncAnthropic` client initialization
- Error handling in chat dispatch and tool calls
- Weather tools zip safety, unused imports

---

## [0.1.2] — 2026-04-19

### Added
- **AgentEngine** — APScheduler-based scheduler for `monitor` and `preventive` agents, WebSocket listener for `reactive` agents, CRUD persistence to `/data/agents.json`
- **Structured response parsing** — `VALUTAZIONE: [OK|ATTENZIONE|ANOMALIA]` and `AZIONE:` fields stripped from agent output and saved to execution log
- REST API handlers for chat, agent CRUD, and status endpoints
- Comprehensive API test coverage

### Fixed
- Cron expression parsing, `last_run` tracking, WebSocket startup, task error callbacks

---

## [0.1.1] — 2026-04-19

### Added
- **HA Client** — REST client for `/api/states`, `/api/services`, History API; WebSocket client for `state_changed` events with auto-reconnect
- Module restructure: `proxy/`, `tools/`, `api/` sub-packages

### Fixed
- HA client error logging, automations endpoint, async WebSocket startup

---

## [0.0.2] — 2026-04-18

### Added
- Restructured app into `proxy/tools/api` module layout
- Static file serving with 503 guard when UI not yet built

---

## [0.0.1] — 2026-04-18

### Added
- Phase 0 scaffold: HA add-on structure with `config.yaml` (ingress, `stage: experimental`)
- `Dockerfile` based on Python 3.11 HA base image
- `build.yaml`: HA Supervisor base-image declarations for `aarch64` and `amd64`
- `run.sh` entrypoint using bashio for configuration reading
- `aiohttp` server on port 8099
- `GET /` placeholder UI, `GET /api/health` → `{"status": "ok"}`
- `hacs.json`: HACS custom repository metadata
- MIT licence
