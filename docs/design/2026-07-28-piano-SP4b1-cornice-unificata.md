# SP-4 Fase B — Piano B: cornice unificata + rebuild verso 1.0

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un **editor unico** per Chatbot e Agentbot con creazione **goal-first**, costruito su un layer front-end sano; più il rebuild delle superfici chat. Chiude SP-4 e porta HIRIS alla **1.0**.

**Architecture:** Il layer editor attuale è tenuto insieme da tre puntelli che si alimentano a vicenda: iniezione di 7 script a runtime, un selettore entità **singleton** con stato globale e id hardcoded, e `rewireLegacyAfterMount()` che **reimplementa** ciò che quegli script già fanno (perché `populate*()` sostituisce i nodi a cui erano agganciati). Si smonta in ordine: prima il componente entità istanziabile, poi il collasso del loader (che rende il cache-busting corretto **gratis**), poi il kit condiviso, poi i due editor sopra di esso, infine le superfici chat.

**Tech Stack:** vanilla JS ES5-style (nessun build step, nessun bundler), `<script src>` con fingerprint per-file lato server; aiohttp; pytest (i test FE sono asserzioni di testo sul sorgente).

## Global Constraints

- **Target 1.0, nessuna retrocompatibilità richiesta.** Dove esistono due implementazioni, ne resta **una**. Non aggiungere shim.
- **Grounding autorevole:** ogni task DEVE leggere `C:/Users/Betse/.claude/projects/C--Users-Betse--local-bin/0c0038fd-68cf-413d-9024-d4aeaab6d833/tool-results/toolu_014VexRMtQTM5wd8gyAqWRXm.json` (sezioni A1-A5, B6-B8, C9-C10): contiene i numeri di riga verbatim, le copie duplicate con le loro differenze semantiche, e il censimento completo dei global.
- **Contratti da onorare (C9)** — romperli rompe pagine fuori scope:
  - `window.HirisChatbotEditor.mount(id|null)` è chiamato **senza guardia** da `main.js:136,141`.
  - `HirisState` chiavi `unsaved`, `activeChatbotId`, `chatbots` (`dashboard.js:273` legge `chatbots` per decidere empty-state; `main.js:55` e `chatbots-list.js:26` la scrivono).
  - Route hash pubbliche: `#/chatbots`, `#/chatbots/new`, `#/chatbots/{id}`, `#/agentbots` (linkate da `dashboard.js`, `chatbots-list.js`, `models-route.js:543`, `usage-route.js:92`).
  - Breadcrumb `#chrome-here`; nav `data-route="chatbots"`/`"agentbots"` + `#nav-chatbots-count`.
  - Header **`X-Requested-With: fetch`** su ogni scrittura (guardia CSRF).
  - Path API **relativi** (`api/...`, mai leading slash — Ingress).
- **`tests/test_fe_rename_regression.py:45-52` fissa i nomi dei 4 file FE**: rinominare o eliminarli fa fallire la CI → va aggiornato **nello stesso task** che li tocca.
- `escHtml`/`esc` su ogni valore interpolato (XSS).
- Suite completa verde dopo ogni task (baseline **1816**); `node --check` su ogni JS toccato.
- Commit per task. Nessun merge/tag senza conferma esplicita utente.

### Bug live che il rebuild deve chiudere (scoperti nel grounding)
1. **Le modifiche a chip entità / tool / azioni non attivano "Salva"** — `setupStickyActions` fa `querySelectorAll` **una volta** al mount, quindi i controlli creati dopo (chip, checkbox di `buildToolChecks`) non sono mai agganciati a `markDirty`.
2. **Navigare via con modifiche non salvate le perde in silenzio** — `unsaved` è letto solo da `btn-cancel`; il router non lo controlla e non esiste `beforeunload`.
3. **Il dropdown suggerimenti non si chiude più al click-fuori dopo il primo mount** — l'handler a livello documento (`permessi.js:159-163`) cattura nodi che diventano detached.
4. **Cache-busting sbagliato per gli script iniettati** — ereditano l'hash di `chatbot-editor.js`, non il proprio: modificare solo `permessi.js` non invalida la cache.

---

## Task 1: componente selettore entità istanziabile

**Perché prima:** è il blocco fisico all'editor unico — l'Agentbot ne serve **tre** per riga (entità trigger, entità condizione, entità target), ma oggi lo stato è un `Set` a livello di modulo e ogni accesso è `document.getElementById(<literal>)`.

**Files:**
- Create: `hiris/app/static/config/entity-picker.js`
- Modify: `hiris/app/static/config.html` (aggiungi lo `<script>`), `hiris/app/static/config/permessi.js` (rimuovi il selettore singleton, tieni tool/azioni per ora)
- Test: `tests/test_entity_picker.py` (asserzioni di testo) + `tests/static/test_entity_picker.html` (harness manuale, opzionale, come gli altri in `tests/static/`)

**Interfaces:**
- Produces: `window.HirisEntityPicker.create(rootEl, opts) -> instance`
  - `opts`: `{ initial?: string[], onChange?: (patterns: string[]) => void, pills?: string[], placeholder?: string, single?: boolean }`
  - `instance`: `{ getValue(): string[], setValue(patterns: string[]), add(pattern), remove(pattern), destroy() }`
  - `single: true` → modalità **una sola entità** (per trigger/target Agentbot): niente chip multipli, il valore è `[]` o `[uno]`.
  - Ogni istanza genera i propri id (contatore interno) e non tocca alcun id globale. `destroy()` **deve** rimuovere l'handler documento del click-fuori.
  - Fetch: `api/entities?q=<term>` (forma canonica `{entities:[{entity_id, friendly_name, domain, ...}]}`), debounce 300ms, `X-Requested-With` non serve (GET).

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_entity_picker.py
from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_entity_picker_module_exists_and_is_instance_scoped():
    js = (BASE / "config" / "entity-picker.js").read_text(encoding="utf-8")
    assert "HirisEntityPicker" in js
    assert "create" in js
    # nessun id hardcoded del vecchio singleton
    for legacy_id in ("entity-chips", "entity-search", "entity-suggestions", "f-entities"):
        assert "'" + legacy_id + "'" not in js and '"' + legacy_id + '"' not in js, \
            f"{legacy_id}: il picker deve generare i propri id, non riusare quelli globali"
    # deve esporre destroy (per staccare il listener documento)
    assert "destroy" in js
    assert "api/entities" in js and "entities" in js and "entity_id" in js


def test_permessi_no_longer_owns_the_entity_selector():
    js = (BASE / "config" / "permessi.js").read_text(encoding="utf-8")
    assert "_entitySelectionSet" not in js, "il selettore singleton deve essere rimosso"


def test_config_html_includes_entity_picker():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/entity-picker.js" in html
```

- [ ] **Step 2: Verifica che fallisca** — `pytest tests/test_entity_picker.py -v` → FAIL (modulo assente).

- [ ] **Step 3: Implementa il componente**

Scrivi `entity-picker.js` come IIFE che espone `window.HirisEntityPicker`. Struttura (adatta lo stile a quello degli altri moduli `config/*.js`):

```javascript
(function() {
  var _seq = 0;

  function create(rootEl, opts) {
    opts = opts || {};
    var id = 'ep' + (++_seq);
    var single = !!opts.single;
    var selection = [];                       // stato PER ISTANZA
    var searchTimer = null;
    var destroyed = false;

    rootEl.innerHTML =
      '<div class="ep-pills" id="' + id + '-pills"></div>' +
      '<div class="ep-chips" id="' + id + '-chips"></div>' +
      '<input class="ep-search" id="' + id + '-search" type="text" autocomplete="off" placeholder="' +
        escHtml(opts.placeholder || 'Cerca entità…') + '">' +
      '<div class="ep-suggestions" id="' + id + '-sugg" style="display:none"></div>';

    var chipsEl = rootEl.querySelector('#' + id + '-chips');
    var searchEl = rootEl.querySelector('#' + id + '-search');
    var suggEl = rootEl.querySelector('#' + id + '-sugg');
    var pillsEl = rootEl.querySelector('#' + id + '-pills');

    function emit() { if (opts.onChange) opts.onChange(getValue()); }

    function render() {
      chipsEl.innerHTML = '';
      selection.forEach(function(p) {
        var chip = document.createElement('span');
        chip.className = 'entity-chip';
        chip.innerHTML = '<span>' + escHtml(p) + '</span><span class="chip-remove">×</span>';
        chip.querySelector('.chip-remove').addEventListener('click', function() { remove(p); });
        chipsEl.appendChild(chip);
      });
    }

    function add(pattern) {
      if (!pattern) return;
      if (single) { selection = [pattern]; }
      else if (selection.indexOf(pattern) === -1) { selection.push(pattern); }
      else { return; }
      render(); emit();
    }
    function remove(pattern) {
      var i = selection.indexOf(pattern);
      if (i === -1) return;
      selection.splice(i, 1); render(); emit();
    }
    function getValue() { return selection.slice(); }
    function setValue(patterns) {
      selection = Array.isArray(patterns) ? patterns.filter(Boolean).slice() : [];
      if (single) selection = selection.slice(0, 1);
      render();               // setValue NON emette: è il caricamento, non una modifica utente
      searchEl.value = ''; suggEl.style.display = 'none';
    }

    (opts.pills || []).forEach(function(p) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'domain-pill'; b.textContent = p;
      b.addEventListener('click', function() { add(p); searchEl.value = ''; });
      pillsEl.appendChild(b);
    });

    searchEl.addEventListener('input', function() {
      var q = searchEl.value.trim();
      clearTimeout(searchTimer);
      if (!q) { suggEl.style.display = 'none'; return; }
      searchTimer = setTimeout(function() {
        fetch('api/entities?q=' + encodeURIComponent(q))
          .then(function(r) { return r.json(); })
          .then(function(data) {
            if (destroyed) return;
            var items = (data && data.entities) || [];
            suggEl.innerHTML = '';
            if (!items.length) { suggEl.style.display = 'none'; return; }
            items.slice(0, 20).forEach(function(item) {
              var div = document.createElement('div');
              div.className = 'ep-suggestion';
              div.innerHTML = '<span>' + escHtml(item.entity_id) + '</span>' +
                '<span class="s-name">' + escHtml(item.friendly_name || '') + '</span>';
              div.addEventListener('click', function() {
                add(item.entity_id); searchEl.value = ''; suggEl.style.display = 'none';
              });
              suggEl.appendChild(div);
            });
            suggEl.style.display = '';
          })
          .catch(function() { suggEl.style.display = 'none'; });
      }, 300);
    });

    searchEl.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); add(searchEl.value.trim()); searchEl.value = ''; suggEl.style.display = 'none'; }
      if (e.key === 'Escape') { suggEl.style.display = 'none'; }
    });

    function onDocClick(e) { if (!rootEl.contains(e.target)) suggEl.style.display = 'none'; }
    document.addEventListener('click', onDocClick);

    setValue(opts.initial || []);

    return {
      getValue: getValue, setValue: setValue, add: add, remove: remove,
      destroy: function() {
        destroyed = true;
        clearTimeout(searchTimer);
        document.removeEventListener('click', onDocClick);   // chiude il leak del click-fuori
        rootEl.innerHTML = '';
      }
    };
  }

  window.HirisEntityPicker = { create: create };
})();
```

Aggiungi `<script src="static/config/entity-picker.js"></script>` in `config.html` **dopo `api.js`** (usa `escHtml`) e prima di `chatbot-editor.js`. Aggiungi le classi `.ep-*` a `hiris-config.css` riusando lo stile esistente di `.entity-chip`/`.domain-pill`/`#entity-suggestions`.

In `permessi.js` **rimuovi** `_entitySelectionSet`, `_entitySelectorRender/Add/Load` e i loro listener IIFE-time; lascia per ora `buildToolChecks`/`buildActionChecks`/`getSelectedTools`/`getSelectedActions` (li assorbe il Task 3). L'editor non è ancora migrato: in questo task il selettore vecchio smette di esistere e l'editor **userà il nuovo componente** — quindi aggiorna anche i suoi punti di aggancio (`chatbot-editor.js` `populatePermessi` + `rewireLegacyAfterMount` righe ~347-403 e `chatbot-form.js:43,78`) per istanziare `HirisEntityPicker.create(...)` e leggere `getValue()` invece del campo nascosto `#f-entities`.

- [ ] **Step 4: Verifica** — `pytest tests/test_entity_picker.py tests/test_entities_frontend_wiring.py -v`, poi `pytest -q --maxfail=10`, poi `node --check` su `entity-picker.js`, `permessi.js`, `chatbot-editor.js`, `chatbot-form.js`.

- [ ] **Step 5: Commit** — `feat(fe): componente entity-picker istanziabile (sostituisce il selettore singleton)`

---

## Task 2: collassa il loader dinamico (e il cache-busting si aggiusta da solo)

**Perché:** `ensureLegacy()` inietta 7 script dopo il mount; `populate*()` sostituisce i nodi, quindi i listener agganciati a IIFE-time puntano a nodi detached; `rewireLegacyAfterMount()` esiste solo per rattoppare, **reimplementando** 6 comportamenti. In più il regex server-side del fingerprint (`_ASSET_REF_RE`) vede solo i `src=` letterali in HTML → gli script iniettati hanno il bust sbagliato.

**Files:**
- Modify: `hiris/app/static/config.html` (aggiungi i 7 come `<script src>` nell'ordine giusto), `hiris/app/static/config/chatbot-editor.js` (elimina loader, rewire, shim), `permessi.js`, `usage.js`, `logs.js`, `chatbot-form.js`, `log-row.js`, `templates.js`, `proposals.js`, `main.js:150-166` (il secondo loader ad-hoc per `proposals.js`)
- Test: `tests/test_fe_loader_collapse.py` (nuovo), aggiorna `tests/test_fe_rename_regression.py` se cambi nomi file

**Vincitori da scegliere** (le copie NON sono identiche — dettaglio in A1 del grounding):
| Comportamento | Tieni | Nota |
|---|---|---|
| pill/ricerca/Enter-Escape entità | **il componente del Task 1** | entrambe le vecchie copie spariscono |
| reset consumi (`#u-ag-reset-btn`) | la versione **editor** (usa `HirisState.get('activeChatbotId')`, non il global `currentId`) | |
| toggle abilitato (`#u-ag-toggle-btn`) | la versione **usage.js** (ha il `confirm()` e ricarica la lista + riapre l'agente) — quella dell'editor oggi vince e **non** ricarica | è un miglioramento reale |
| token counter | quella dell'editor (l'originale in logs.js è già stato rimosso) | |
| click-fuori suggerimenti | il `destroy()` del componente | chiude il leak |

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_fe_loader_collapse.py
from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

LEGACY = ["templates.js", "permessi.js", "log-row.js", "logs.js", "usage.js",
          "proposals.js", "chatbot-form.js"]


def test_no_runtime_script_injection():
    js = (BASE / "config" / "chatbot-editor.js").read_text(encoding="utf-8")
    for token in ("LEGACY_SCRIPTS", "ensureLegacy", "rewireLegacyAfterMount", "addLegacyShims"):
        assert token not in js, f"{token} deve sparire: gli script sono <script src> in config.html"
    main = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "data-legacy" not in main, "anche il loader ad-hoc di proposals.js deve sparire"


def test_all_editor_scripts_are_declared_in_html():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    for f in LEGACY:
        assert "config/" + f in html, f"{f} deve essere un <script src> (cache-busting per-file)"
```

- [ ] **Step 2: Verifica che fallisca.**

- [ ] **Step 3: Dichiara gli script in `config.html`**

Aggiungi i 7 file come `<script src="static/config/<f>"></script>` rispettando le dipendenze reali: `state → router → api → entity-picker → templates → permessi → log-row → logs → usage → proposals → chatbot-form → drawer → popover → chatbot-editor → (route) → main`. **Prima** però rendi ciascuno di quei file safe-at-load: oggi alcuni fanno `getElementById(...).addEventListener(...)` senza guardia a IIFE-time (es. `permessi.js:119`) e lancerebbero un TypeError caricati a shell vuota. Converti quelle registrazioni in **event delegation** sul contenitore stabile (`#route-outlet`) o in funzioni `init(root)` chiamate dall'editor al mount.

- [ ] **Step 4: Elimina i tre puntelli**

In `chatbot-editor.js` rimuovi `V6_CACHE_BUST`, `LEGACY_SCRIPTS`, `loadScript`, `ensureLegacy`, `rewireLegacyAfterMount`, `addLegacyShims` (e gli stub `#no-selection`/`#form`/`#form-title`/`#delete-btn`/`#usage-reset-btn` + i no-op `resetToFirstTab`/`switchTab`). Applica la tabella dei vincitori: dove tieni la versione "originale", cancella quella dell'editor e viceversa — **una sola copia deve restare**. In `main.js:150-166` togli il loader ad-hoc (`proposals.js` è ora un `<script src>`).

- [ ] **Step 5: Verifica** — `pytest tests/test_fe_loader_collapse.py -v`, poi `pytest -q --maxfail=10`; `node --check` su tutti i file toccati. **Verifica manuale consigliata:** apri `#/chatbots/<id>`, naviga via e torna — al secondo mount i controlli devono ancora rispondere (era esattamente ciò che `rewireLegacyAfterMount` mascherava).

- [ ] **Step 6: Commit** — `refactor(fe): elimina l'iniezione di script a runtime — un solo owner per comportamento, cache-busting per-file corretto`

---

## Task 3: kit editor condiviso (campi, modello, dirty tracking, salvataggio)

**Files:**
- Create: `hiris/app/static/config/editor-kit.js`
- Modify: `hiris/app/static/config.html`, `permessi.js` (assorbi tool/azioni nel kit), `api.js` (sposta `loadModels`/`_setModelValue`: sono codice editor dentro un file condiviso)
- Test: `tests/test_editor_kit.py`

**Interfaces:**
- Produces `window.HirisEditorKit`:
  - `field.text(parent, {label, value, id?})`, `.number(...)`, `.checkbox(...)`, `.select(parent, {label, options, value})`, `.textarea(...)` → ognuno ritorna l'elemento input.
  - `modelSelect(parent, {label, value})` → usa **una sola** fetch `api/models` **condivisa e cachata** (oggi `agentbot-route.js` ne fa una **per riga**), con optgroup per provider, hint `• free` e gestione del modello orfano (`(provider non configurato)`).
  - `checkGroup(parent, {items, selected})` per tool/azioni (istanza-scoped, non `#tool-checks` globale).
  - `dirty.track(rootEl, onDirty)` → **MutationObserver + delegation** su `rootEl`, così i controlli creati *dopo* il mount (chip, checkbox) marcano dirty. Chiude il bug live #1.
  - `dirty.guard(isDirtyFn)` → installa un guard di navigazione (hashchange + `beforeunload`) che chiede conferma. Chiude il bug live #2.
  - `saveBar(rootEl, {onSave, onCancel, onDelete?, onTestRun?})` → barra sticky unica con stato `disabled` legato a dirty.

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_editor_kit.py
from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_kit_exists_with_shared_blocks():
    js = (BASE / "config" / "editor-kit.js").read_text(encoding="utf-8")
    assert "HirisEditorKit" in js
    for fn in ("modelSelect", "dirty", "saveBar", "checkGroup"):
        assert fn in js, f"il kit deve esporre {fn}"


def test_dirty_tracking_is_not_a_one_shot_snapshot():
    js = (BASE / "config" / "editor-kit.js").read_text(encoding="utf-8")
    assert "MutationObserver" in js or "addEventListener('change'" in js
    # il guard di navigazione deve esistere (perdita silenziosa di modifiche)
    assert "beforeunload" in js or "hashchange" in js


def test_models_fetch_is_cached_not_per_row():
    js = (BASE / "config" / "editor-kit.js").read_text(encoding="utf-8")
    assert "api/models" in js
    assert "cache" in js.lower() or "_modelsPromise" in js
```

- [ ] **Step 2: Verifica che fallisca.**

- [ ] **Step 3: Implementa il kit.** Porta dentro le fabbriche di campo oggi duplicate fra `agentbot-route.js:128-268` e l'editor Chatbot; una sola implementazione. Il `modelSelect` mantiene **una** promise condivisa:

```javascript
  var _modelsPromise = null;
  function loadModelsOnce() {
    if (!_modelsPromise) {
      _modelsPromise = fetch('api/models')
        .then(function(r) { return r.ok ? r.json() : { providers: [] }; })
        .catch(function() { return { providers: [] }; });
    }
    return _modelsPromise;
  }
```

Il dirty tracking deve osservare il sottoalbero, non fotografarlo:
```javascript
  function track(rootEl, onDirty) {
    function wire(el) {
      if (el.__hkWired) return;
      el.__hkWired = true;
      el.addEventListener('change', onDirty);
      el.addEventListener('input', onDirty);
    }
    rootEl.querySelectorAll('input, select, textarea').forEach(wire);
    var mo = new MutationObserver(function(muts) {
      muts.forEach(function(m) {
        Array.prototype.forEach.call(m.addedNodes, function(n) {
          if (n.nodeType !== 1) return;
          if (n.matches && n.matches('input, select, textarea')) wire(n);
          if (n.querySelectorAll) n.querySelectorAll('input, select, textarea').forEach(wire);
        });
      });
    });
    mo.observe(rootEl, { childList: true, subtree: true });
    return { stop: function() { mo.disconnect(); } };
  }
```
Nota: il picker del Task 1 notifica via `onChange` (i chip non sono input) — collegalo a `onDirty` esplicitamente.

Sposta `loadModels`/`_setModelValue` fuori da `api.js` dentro il kit (sono codice editor: vedi C9).

- [ ] **Step 4: Verifica** — test mirati, `pytest -q --maxfail=10`, `node --check`.
- [ ] **Step 5: Commit** — `feat(fe): editor-kit condiviso (campi, modello cachato, dirty tracking reale, save bar)`

---

## Task 4: editor Chatbot sul kit (+ knowledge_access, mai avuto UI)

**Files:**
- Rewrite: `hiris/app/static/config/chatbot-editor.js` (assorbe `chatbot-form.js`: unico owner del payload)
- Delete: `hiris/app/static/config/chatbot-form.js` (aggiorna `tests/test_fe_rename_regression.py`!)
- Modify: `hiris/app/static/config.html` (`tpl-agent-editor` → sezioni generate dal kit o template aggiornato), `hiris/app/api/handlers_chatbots.py` (validazione `knowledge_access`)
- Test: `tests/test_chatbot_editor.py`, `tests/test_handlers_chatbots.py`

**Interfaces:**
- Consumes: Task 1 (`HirisEntityPicker`), Task 3 (`HirisEditorKit`).
- Produces: `window.HirisChatbotEditor.mount(id|null)` (contratto invariato — `main.js` lo chiama senza guardia); payload che ora include **`knowledge_access`** (`{allow_sensitive: bool, kinds: "all"|string[]}`).

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_chatbot_editor.py
from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_editor_uses_kit_and_picker_and_owns_payload():
    js = (BASE / "config" / "chatbot-editor.js").read_text(encoding="utf-8")
    assert "HirisEditorKit" in js and "HirisEntityPicker" in js
    assert "HirisChatbotEditor" in js and "mount" in js
    assert not (BASE / "config" / "chatbot-form.js").exists(), "il form deve essere assorbito"


def test_knowledge_access_is_finally_editable():
    js = (BASE / "config" / "chatbot-editor.js").read_text(encoding="utf-8")
    assert "knowledge_access" in js, "il dial knowledge non deve piu' essere solo-API"
    assert "allow_sensitive" in js
```
```python
# tests/test_handlers_chatbots.py  (aggiungi)
def test_knowledge_access_is_validated():
    """Prima accettava qualunque tipo JSON (setattr grezzo)."""
    from hiris.app.api.handlers_chatbots import _validate_chatbot_payload
    assert _validate_chatbot_payload({"knowledge_access": "nope"}) is not None
    assert _validate_chatbot_payload({"knowledge_access": {"allow_sensitive": "si"}}) is not None
    assert _validate_chatbot_payload({"knowledge_access": {"allow_sensitive": True, "kinds": "all"}}) is None
```

- [ ] **Step 2: Verifica che fallisca.**
- [ ] **Step 3: Riscrivi l'editor** sulle sezioni: Identità · Istruzioni · Modello · Scope (picker multi) · Permessi (tool/azioni dal kit) · **Knowledge** (nuovo) · Autonomia (riepilogo semaforo + conferma) · Abilitazione · Log · Test Run · Consumi. Assorbi `openAgent`/`buildPayload` da `chatbot-form.js` (unico owner, niente più `window.currentId` in parallelo a `HirisState`). Mantieni: refresh di `HirisState.chatbots` dopo create/delete (lo legge `dashboard.js:273`), breadcrumb `#chrome-here`, route hash.
- [ ] **Step 4: Valida `knowledge_access` lato backend** in `_validate_chatbot_payload` (oggi accetta qualsiasi tipo): dict, `allow_sensitive` bool, `kinds` `"all"` o lista di stringhe.
- [ ] **Step 5: Verifica** — test mirati + `pytest -q --maxfail=10` + `node --check`.
- [ ] **Step 6: Commit** — `feat(fe): editor Chatbot ricostruito sul kit + UI knowledge_access (con validazione)`

---

## Task 5: editor Agentbot per-entità + split della pagina Sentinella

**Files:**
- Create: `hiris/app/static/config/agentbot-editor.js`
- Modify: `hiris/app/static/config/agentbot-route.js` (resta **solo** policy Sentinella + osservabilità), `main.js` (route `#/agentbots/new`, `#/agentbots/{id}`), `config.html`
- Test: `tests/test_agentbot_editor.py`, aggiorna `tests/test_agentbot_frontend_wiring.py`

**Split (righe dal grounding A5):** si sposta **solo il blocco 4** (`340-605`, le regole Agentbot: hanno id, CRUD, save per riga). Restano in `agentbot-route.js`: blocchi 1-3+5 (detector, situazioni, preparazione, con il loro **unico** POST `api/sentinel/policy`) e 6-7 (timeline + suggerimenti). Nota: oggi la card "Situazioni" scrive il suo status tramite il bottone dei Detector, e "Preparazione" non ha bottone proprio — dopo lo split **dai a ciascuna card il suo Salva** oppure lascia il salvataggio unico ma con un solo status chiaro; dichiara quale scegli.

- [ ] **Step 1: Test che fallisce**
```python
# tests/test_agentbot_editor.py
from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_agentbot_editor_is_its_own_route_on_the_kit():
    js = (BASE / "config" / "agentbot-editor.js").read_text(encoding="utf-8")
    assert "HirisAgentbotEditor" in js and "HirisEditorKit" in js
    assert "HirisEntityPicker" in js, "trigger/condizione/target devono usare il picker istanziabile"
    assert "api/agentbots" in js
    main = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "#/agentbots/" in main


def test_sentinel_page_no_longer_owns_agentbot_crud():
    js = (BASE / "config" / "agentbot-route.js").read_text(encoding="utf-8")
    assert "api/sentinel/policy" in js
    assert "buildAgentbotRow" not in js and "emptyLens" not in js
```
- [ ] **Step 2: Verifica che fallisca.**
- [ ] **Step 3: Implementa** l'editor per-entità (Identità/severità · Trigger evento|schedulato con picker per entità e condizione · Modello (`reasoning.model`) · Verdetto (prompt) · Azione notify|service con picker target · Abilitazione · Osservabilità). **Vincolo di sicurezza invariato:** l'azione resta **dichiarata in config**, il ragionamento resta `allowed_tools=[]`, il semaforo resta l'unico gate. Attenzione (grounding): `validate_agentbot` **scarta in silenzio** i campi sconosciuti — qualunque campo nuovo va aggiunto anche lì o sparisce al primo salvataggio.
- [ ] **Step 4: Alleggerisci `agentbot-route.js`** rimuovendo il blocco 4 e le fabbriche ormai nel kit.
- [ ] **Step 5: Verifica** + [ ] **Step 6: Commit** — `feat(fe): editor Agentbot per-entita' + pagina Sentinella ridotta a policy e osservabilita'`

---

## Task 6: creazione goal-first (deterministica)

**Files:** Create `hiris/app/static/config/create-wizard.js`; modify `main.js` (`#/nuovo`), `chatbots-list.js`/`dashboard.js` (le CTA puntano al wizard), `config.html`; Test `tests/test_create_wizard.py`.

**Contratto:** 1) Obiettivo (nome + missione in linguaggio naturale) → 2) **derivazione del tipo** deterministica (euristica leggera + scelta esplicita sempre modificabile; **nessun LLM**) → 3) step guidati per tipo (Chatbot: tool+scope+knowledge; Agentbot: trigger+azione+scope) → 4) apre l'editor completo ("Avanzate") con i valori precompilati. La **linea rossa E.2** resta: mai un'entità con tool liberi + trigger + attuazione.

- [ ] **Step 1: Test che fallisce** (asserisce: il wizard esiste, deriva il tipo, non chiama alcun endpoint LLM, e le CTA `#/chatbots/new` sono state reindirizzate)
- [ ] **Step 2-4: implementa + verifica** (il passo 3 crea l'entità con `POST api/chatbots` o `POST api/agentbots` secondo il tipo)
- [ ] **Step 5: Commit** — `feat(fe): creazione goal-first guidata (deriva il tipo, poi editor avanzato)`

---

## Task 7: rebuild della card Lovelace

**Files:** Rewrite `hiris/app/static/hiris-chat-card.js` (1459 righe); Test `tests/test_lovelace_registration.py` (già copre registrazione/editor/stub — mantienilo verde).

Da preservare: i due custom element + `getConfigElement`/`getStubConfig`/`getCardSize`/`customCards`; i **tre modi di risposta** (202+polling, SSE, JSON); ingress base discovery + `_ensureIngressSession`; persistenza localStorage; `X-Requested-With` sulle scritture. Da cambiare: solo `chatbot_id` (via il fallback `agent_id` — 1.0, niente retrocompat); niente filtri su campi inesistenti; una sola copia di `_esc`/`IRIS_CSS` fra card ed editor; copy allineata a Chatbot/Agentbot/Brain.

- [ ] Step 1 test → Step 2 fail → Step 3 rewrite → Step 4 verifica (`pytest tests/test_lovelace_registration.py -v` + suite + `node --check`) → Step 5 commit `refactor(card): rebuild hiris-chat-card sulle specifiche 1.0`

---

## Task 8: rebuild della pagina chat

**Files:** Rewrite `hiris/app/static/index.html` (811 righe, ~610 di script inline); estrai il JS in `static/chat/*.js` così il fingerprint per-file lo copre; Test `tests/test_chat_page.py`.

Blocchi da riportare: chat + turn limit, lista chatbot, tasks panel, usage widget, onboarding. Da eliminare: le copie private di `esc`/`applyTheme`/`loadUsage`/`pollChatReply` (usa i moduli condivisi), gli `onclick=` inline. Da usare: `chatbot_id` sul wire.

- [ ] Step 1 test → Step 2 fail → Step 3 rewrite → Step 4 verifica → Step 5 commit `refactor(chat): rebuild pagina chat, JS estratto e deduplicato`

---

## Task 9: 1.0

**Files:** `hiris/config.yaml` (togli `stage: experimental`, version `1.0.0`), `CHANGELOG.md`, `PRODUCT.md`, `docs/*` (IT+EN).

- [ ] Rimuovi `stage: experimental`; bump `1.0.0`.
- [ ] CHANGELOG 1.0 riassuntivo: le tre entità (Chatbot/Agentbot/Brain), la home del Brain, il layer Modelli, la cornice unificata, la creazione goal-first; nota operativa su cosa cambia per chi aggiorna.
- [ ] Doc: sezione sulla creazione goal-first e sull'editor unico; verifica che i doc di architettura restino veri dopo i rebuild (i file FE sono cambiati).
- [ ] Verifica finale: `pytest -q` verde; `node --check` su tutti i JS; grep di coerenza nomi.
- [ ] Commit — `chore: HIRIS 1.0.0 — prima versione definitiva (via stage experimental)`

---

## Verifica finale & handoff (conferma utente prima di merge/tag)

- [ ] Suite verde; nessun residuo dei puntelli (`ensureLegacy`, `rewire`, `addLegacyShims`, `_entitySelectionSet`).
- [ ] Review whole-branch indipendente: contratti C9 onorati (mount unguarded, HirisState, route, CSRF, path relativi); linea rossa E.2 intatta; i 4 bug live chiusi con test.
- [ ] **Live-verify utente**: creare un Chatbot e un Agentbot dal wizard; la ricerca entità funziona in tutti e tre i punti dell'Agentbot; Salva si attiva modificando chip/tool; navigare via con modifiche chiede conferma; la card Lovelace e la pagina chat funzionano.
- [ ] Conferma esplicita → merge + tag **v1.0.0** + release.

## Copertura (self-review)

- Selettore entità istanziabile → T1 ✓ (sblocca i 3 picker per Agentbot) · loader/duplicazioni/cache-bust → T2 ✓ · kit + dirty reale + guard navigazione → T3 ✓
- Editor unico Chatbot (+knowledge_access UI e validazione) → T4 ✓ · Agentbot per-entità + split pagina → T5 ✓ · goal-first → T6 ✓
- Rebuild card → T7 ✓ · rebuild pagina chat → T8 ✓ · 1.0 → T9 ✓
- Bug live #1 (dirty) → T3 ✓ · #2 (perdita silenziosa) → T3 ✓ · #3 (click-fuori) → T1 `destroy()` ✓ · #4 (cache-bust) → T2 ✓
- Blocchi E.1 condivisi: identità/modello/scope/autonomia/knowledge/osservabilità → T3+T4+T5 ✓ · E.2 distinti (prompt libero vs verdetto-JSON) → T5 vincolo esplicito ✓
