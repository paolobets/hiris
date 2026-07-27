# SP-1a — Rename user-facing (Chatbot/Agentbot/Brain) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rinominare SOLO il testo visibile all'utente (etichette UI della config SPA, breadcrumb, titoli, hint, la chat, `PRODUCT.md`) a **Chatbot / Agentbot / Brain**, lasciando invariati tutti i nomi interni (codice, API, DB, id DOM, chiavi di stato) — zero rotture.

**Architecture:** È un rename di **copy**, non di struttura. Regola unica applicata per-area: si tocca solo la STRINGA VISIBILE renderizzata; NON si toccano identificatori. Ogni task verifica con grep (nessun termine stantìo visibile nell'area) + `node --check` (il JS parsa) e il fatto che i file interni/API restino invariati.

**Tech Stack:** Config SPA vanilla JS + HTML (`hiris/app/static/`), `PRODUCT.md`. Nessun test Python nuovo (è UI copy); verifica = grep mirati + `node --check`.

## Global Constraints

- **Mappa termini (SOLO testo visibile):** "Agente/Agenti" (chat) → **Chatbot** · "Lente/Lenti", "Sentinella" (proattivo) → **Agentbot** · "Cervello" → **Brain**. Mantieni maiuscole/plurali sensati ("Chatbot", "Agentbot", "Brain"; plurale invariato: "i Chatbot").
- **NON toccare MAI** (identificatori, non testo): nomi file (`agent-editor.js`), path API (`/api/agents`, `/api/sentinel*`), chiavi di stato (`HirisState.set('agents'|'activeAgentId'|…)`), **id/class DOM** (`nav-agents-count`, `#agents`, `.agent-…`), nomi funzione/variabile (`populateAgente`, `activeAgentId`), route hash (`#/agents`, `#/sentinel`), chiavi oggetto/JSON, la colonna DB `lens`, i campi API. In dubbio: **non cambiarlo** (è un rename di sola copy).
- **Scope:** SOLO `hiris/app/static/` (config SPA, `index.html`, `hiris-chat-card.js`, `config.html`) + `PRODUCT.md`. **Nessun** file Python, **nessun** cambio API/DB (quello è SP-1b).
- **Verifica per ogni file JS toccato:** `node --check <file>` deve passare (nessun errore di sintassi introdotto dal rename).
- **Coerenza:** il rename è solo IT→nuovi-nomi nel testo mostrato; se una stringa mostra sia label sia un id interno interpolato, cambia solo la parte label.

---

### Task 1: Navigazione & breadcrumb (main.js, config.html, drawer)

**Files:**
- Modify: `hiris/app/static/config/main.js` (breadcrumb `setCrumbHere(...)`, label visibili)
- Modify: `hiris/app/static/config/drawer.js` (voci di menu visibili)
- Modify: `hiris/app/static/config.html` (titoli/voci visibili; NON i `<script src=…>`)

**Interfaces:** nessuna (solo copy). Non cambia rotte/id.

- [ ] **Step 1: Rinomina le stringhe visibili**

In `main.js`, i breadcrumb: `setCrumbHere('Agenti')` → `setCrumbHere('Chatbot')`; `'Agenti / Nuovo'` → `'Chatbot / Nuovo'`; `'Agenti / ' + m[1]` → `'Chatbot / ' + m[1]`; `setCrumbHere('Sentinella')` → `setCrumbHere('Agentbot')`. **NON** toccare `getElementById('nav-agents-count')`, `HirisState.set('agents', …)`, `HirisState.set('activeAgentId', …)`, le route `#/agents`/`#/sentinel`.
In `drawer.js` e `config.html`: rinomina le **voci di menu / titoli visibili** ("Agenti"→"Chatbot", "Sentinella"/"Cervello"→"Agentbot"/"Brain" a seconda del contesto) lasciando `href`/`data-route`/`id`/`src` invariati.

- [ ] **Step 2: Verifica sintassi + assenza termini stantii nel testo**

Run: `cd /c/Work/Sviluppo/hiris && node --check hiris/app/static/config/main.js && node --check hiris/app/static/config/drawer.js`
Run: `grep -nE "setCrumbHere\('Agenti|setCrumbHere\('Sentinella" hiris/app/static/config/main.js` → **nessun match** (breadcrumb rinominati).
Expected: node OK; grep vuoto sui breadcrumb rinominati; `#/agents`/`/api` ancora presenti (id/route intatti).

- [ ] **Step 3: Commit**

```bash
git add hiris/app/static/config/main.js hiris/app/static/config/drawer.js hiris/app/static/config.html
git commit -m "chore(ui): rename nav/breadcrumb -> Chatbot/Agentbot/Brain (SP-1a)"
```

---

### Task 2: Lista + editor Chatbot (agents-list.js, agent-editor.js, agent-form.js)

**Files:**
- Modify: `hiris/app/static/config/agents-list.js`
- Modify: `hiris/app/static/config/agent-editor.js`
- Modify: `hiris/app/static/config/agent-form.js`

- [ ] **Step 1: Rinomina il testo visibile a "Chatbot"**

In questi 3 file, sostituisci nel **testo mostrato** "agente/Agente/agenti/Agenti" → "Chatbot" (es. titoli tipo "Nuovo agente"→"Nuovo Chatbot", "I tuoi agenti"→"I tuoi Chatbot", label/hint/placeholder, il dropdown "Modello" resta). **NON** toccare: nomi funzione (`populateAgente`, `_setModelValue`), `id`/`class` DOM (`f-model`, `agent-…`), chiavi API (`/api/agents`), campi oggetto (`agent.model`, `agent.id`), `activeAgentId`.

- [ ] **Step 2: Verifica**

Run: `cd /c/Work/Sviluppo/hiris && for f in agents-list agent-editor agent-form; do node --check hiris/app/static/config/$f.js || echo FAIL; done`
Run: `grep -rniE ">[^<]*agent[ei][^<]*<|'[^']*[Aa]gent[ei][^']*'|\"[^\"]*[Aa]gent[ei][^\"]*\"" hiris/app/static/config/agents-list.js hiris/app/static/config/agent-editor.js hiris/app/static/config/agent-form.js | grep -viE "api/|href|id=|class=|function|\.js|getElementById|HirisState|activeAgentId|agent\.|agent_id" | head`
Expected: node OK; il grep residuo NON mostra testo visibile "agente/Agenti" (solo eventuali identificatori, che restano). Ispeziona a mano i pochi match per confermare che siano identificatori, non copy.

- [ ] **Step 3: Commit**

```bash
git add hiris/app/static/config/agents-list.js hiris/app/static/config/agent-editor.js hiris/app/static/config/agent-form.js
git commit -m "chore(ui): rename Chatbot editor/list copy (SP-1a)"
```

---

### Task 3: Vista proattiva → "Agentbot" (sentinel-route.js, dashboard.js, proposals*, templates.js)

**Files:**
- Modify: `hiris/app/static/config/sentinel-route.js`
- Modify: `hiris/app/static/config/dashboard.js`
- Modify: `hiris/app/static/config/proposals-route.js`, `hiris/app/static/config/proposals.js`
- Modify: `hiris/app/static/config/templates.js`

- [ ] **Step 1: Rinomina il testo visibile**

Sostituisci nel **testo mostrato**: "Sentinella"/"lente/lenti" → **Agentbot**; "Cervello"/"cervello proattivo" → **Brain**; nelle **proposte**, il linguaggio "l'agente propone…" resta coerente col nuovo modello (una proposta del **Brain** per un nuovo **Agentbot**). In `templates.js` aggiorna il copy dei template stantii (scritti per gli "agenti autonomi" ritirati) al linguaggio Agentbot/Brain. **NON** toccare route `#/sentinel`, `id`/`class`, chiavi API/oggetto.

- [ ] **Step 2: Verifica**

Run: `cd /c/Work/Sviluppo/hiris && for f in sentinel-route dashboard proposals-route proposals templates; do node --check hiris/app/static/config/$f.js || echo FAIL; done`
Run: `grep -rniE "sentinell|lent[ei]\b|cervello" hiris/app/static/config/sentinel-route.js hiris/app/static/config/dashboard.js hiris/app/static/config/templates.js | grep -viE "api/|href|id=|class=|route|#/|function|\.js" | head`
Expected: node OK; nessun testo visibile "Sentinella/lente/cervello" residuo (solo eventuali id/route, che restano).

- [ ] **Step 3: Commit**

```bash
git add hiris/app/static/config/sentinel-route.js hiris/app/static/config/dashboard.js hiris/app/static/config/proposals-route.js hiris/app/static/config/proposals.js hiris/app/static/config/templates.js
git commit -m "chore(ui): rename proactive views -> Agentbot/Brain (SP-1a)"
```

---

### Task 4: Chat full-page + card (index.html, hiris-chat-card.js)

**Files:**
- Modify: `hiris/app/static/index.html`
- Modify: `hiris/app/static/hiris-chat-card.js`

- [ ] **Step 1: Rinomina il testo visibile della chat**

In `index.html` e nella card: dove il testo mostrato dice "agente/Agente" riferito alla persona di chat → **Chatbot** (es. selettore/titolo). **NON** toccare id/class/route/`agent_id`/chiavi API. La label "assistente" generica può restare se non è un identificatore d'entità (valuta caso per caso: se indica l'entità di chat, → Chatbot).

- [ ] **Step 2: Verifica**

Run: `cd /c/Work/Sviluppo/hiris && node --check hiris/app/static/hiris-chat-card.js`
Run: `grep -niE ">[^<]*[Aa]gent[ei][^<]*<|'[^']*[Aa]gent[ei]" hiris/app/static/index.html | grep -viE "api/|id=|class=|agent_id|href|function|activeAgent" | head`
Expected: node OK; nessun testo visibile "agente" residuo riferito all'entità chat.

- [ ] **Step 3: Commit**

```bash
git add hiris/app/static/index.html hiris/app/static/hiris-chat-card.js
git commit -m "chore(ui): rename chat page/card copy -> Chatbot (SP-1a)"
```

---

### Task 5: PRODUCT.md (documentazione)

**Files:**
- Modify: `PRODUCT.md`

- [ ] **Step 1: Riscrivi il linguaggio a Chatbot/Agentbot/Brain**

Aggiorna `PRODUCT.md` al nuovo modello: **Chatbot** (conversazionale, a interrogazione), **Agentbot** (autonomo, agisce da solo), **Brain** (il core che ragiona, evolve e propone nuovi Agentbot). Rimuovi/riscrivi la copy stantìa che descrive "trigger/agenti autonomi" col vecchio linguaggio. Mantieni fedele la sicurezza (semaforo, Agentbot a verdetto-JSON-senza-tool).

- [ ] **Step 2: Verifica**

Run: `grep -niE "\blent[ei]\b|sentinell|cervello" PRODUCT.md` → **nessun match** (o solo in una nota storica esplicita).
Expected: il documento usa Chatbot/Agentbot/Brain coerentemente.

- [ ] **Step 3: Commit**

```bash
git add PRODUCT.md
git commit -m "docs(product): allinea PRODUCT.md a Chatbot/Agentbot/Brain (SP-1a)"
```

---

### Task 6: Verifica finale d'insieme (nessuna rottura, coerenza)

**Files:** nessuna modifica (verifica).

- [ ] **Step 1: Interni/API INTATTI**

Run: `cd /c/Work/Sviluppo/hiris && grep -rnE "/api/agents|#/agents|#/sentinel|activeAgentId|nav-agents-count" hiris/app/static/ | wc -l`
Expected: **> 0** — gli identificatori/route/API sono ancora lì (non li abbiamo toccati).

- [ ] **Step 2: Nessun JS rotto**

Run: `for f in $(ls hiris/app/static/config/*.js hiris/app/static/*.js); do node --check "$f" || echo "FAIL $f"; done`
Expected: nessun FAIL.

- [ ] **Step 3: Suite Python invariata (nessun file Python toccato)**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest -q`
Expected: verde come prima (SP-1a non tocca Python).

- [ ] **Step 4: Commit runbook (se serve una nota)**

Nessun commit se non ci sono modifiche; altrimenti aggiorna questo piano con note e committa.

---

## Note

- **Fuori scope (SP-1b, dopo):** rename INTERNO — `agent_engine`/`/api/agents`→endpoint nuovi, colonna DB, id di stato/DOM, con alias/migrazione e aggiornamento test. Rischioso, slice separata.
- Il rename di copy è **reversibile** e non tocca il comportamento: se un'etichetta ambigua non è chiaramente user-facing, si lascia (principio: in dubbio non toccare).
