# Spec SP-2 — Layer Modelli (attivazione provider · una catena · modello per-entità)

**Data:** 2026-07-27 · Repo: `hiris` · Branch: `design/sp2-model-layer`
Sotto-progetto **SP-2** della north-star `docs/design/2026-07-27-north-star-brain-chatbot-agentbot.md`. Prerequisito SP-1a (rename user-facing) **shipped v0.99.5**.

## Goal

Rendere la gestione dei modelli AI **chiara e granulare** per un prosumer HA:
attivi i provider con toggle espliciti (incluso l'**Abbonamento** first-class);
esiste **una sola catena auto globale** con failover; ogni entità
(**Chatbot / Agentbot / Brain**) ha **un** campo modello (`auto` o esplicito),
col modello per-Agentbot finalmente **visibile**. Retro-compatibile: nessun
install esistente si rompe.

## Architettura (confine ibrido, deciso in brainstorming)

- **Addon-config (HA, `config.yaml` options):** provider + segreti + toggle
  attivazione (incluso Abbonamento). È dove già stanno le key.
- **In-app SPA (`#/models`):** assegnazione **chi-usa-cosa** — catena auto
  globale (ordine/failover) + override modello **per-entità**. UI minima ma
  funzionale (la config-entità *completa* è SP-4).

## Non-goal / fuori scope

- Config-entità unificata completa (persona+ambito+autonomia+knowledge) → **SP-4**.
- Rename interno profondo di identificatori/API/DB → **SP-1b** (rimandato).
- Embeddings via abbonamento (restano binario separato); nessuna nuova
  esposizione pubblica; nessun cambio al semaforo o al contratto Agentbot.

## Vincoli fermi (invarianti)

- **Semaforo** invariato come gate delle azioni.
- **Agentbot = verdetto-JSON-senza-tool** (pilastro sicurezza) — non si tocca.
- In-addon runner (abbonamento): token OAuth `claude_code_oauth_token` e
  **loopback** invariati; MCP interno unauthenticated su 127.0.0.1 invariato.
- Nessun segreto in chat/log; il campo token resta `password`.

---

## 1. Attivazione provider (addon-config)

### 1.1 Nuovi toggle espliciti
Aggiungere in `config.yaml` options un blocco **Provider** con un flag bool per
provider, più il toggle Abbonamento first-class:

```yaml
# ── AI Providers (attivazione esplicita) ──
provider_subscription: false   # Abbonamento (Claude Max via runner in-addon)
provider_claude: false         # Claude API (usa claude_api_key)
provider_openai: false         # OpenAI API (usa openai_api_key)
provider_openrouter: false     # OpenRouter (usa openrouter_api_key)
provider_ollama: false         # Ollama locale (usa local_model.model)
```

Le key/segreti restano dove sono (`claude_api_key`, `openai_api_key`,
`openrouter_api_key`, `local_model.*`, `claude_code_oauth_token`).

### 1.2 Abbonamento first-class (sostituisce i flag criptici)
Il toggle **`provider_subscription`** sostituisce l'accoppiata
`chat_via_subscription` + `bridge_enabled` + `bridge_deadline_min` +
`bridge_fallback`. Con l'abbonamento attivo, **Chatbot + Brain + Agentbot** in
`auto` girano sull'abbonamento (deciso in brainstorming: "un provider → tutto
auto"). Il "bridge" (estensione al percorso proattivo) diventa comportamento
implicito del toggle, non più un flag separato.

`bridge_deadline_min`/`bridge_fallback` (parametri operativi della coda di
ragionamento) **rimangono** come opzioni avanzate ma **non** sono più gate di
attivazione — solo tuning. Documentare che non vanno toccati di norma.

### 1.3 Regola di validità
Un provider è **usabile** solo se `provider_X = true` **e** il suo credenziale è
presente (key non vuota / `local_model.model` per Ollama / token per
Abbonamento). Se un toggle è ON ma manca il credenziale → l'UI `#/models` mostra
un badge "manca credenziale" e il provider è escluso dalla catena. Un toggle OFF
esclude sempre il provider, anche se la key è presente.

### 1.4 Migrazione silenziosa (retro-compat) — CRITICA
All'avvio, se i nuovi toggle sono **tutti al default false** (install pre-SP-2),
derivarli dallo stato legacy così da preservare il comportamento:

| Condizione legacy | Deriva |
|---|---|
| `claude_api_key` non vuota | `provider_claude = true` |
| `openai_api_key` non vuota | `provider_openai = true` |
| `openrouter_api_key` non vuota | `provider_openrouter = true` |
| `local_model.model` non vuoto | `provider_ollama = true` |
| `chat_via_subscription = true` (o già attivo via bridge) | `provider_subscription = true` |

La derivazione avviene **in memoria** al boot (mapping env→app in
`server.py` ~1732-1747), NON riscrive la config utente. Un install che oggi
funziona continua a funzionare identico al primo avvio su v0.100.0.

---

## 2. Catena auto globale + failover (una sola via)

### 2.1 Consolidamento
Oggi `LLMRouter` (costruito in `server.py:1841`) tiene **due** catene:
`automatic_policy` e `chat_policy`, normalizzate da `_norm_policy(policy,
strategy)` con `llm_strategy` (balanced/cost_first/quality_first).

SP-2 collassa a **una catena auto globale**:
- La catena = ordine dei **provider attivi** (§1.3), derivato da `llm_strategy`
  (che resta come *preset di ordinamento*: balanced/cost_first/quality_first)
  **oppure** riordinato a mano dall'utente in `#/models`.
- Il **failover** percorre la catena in ordine finché un provider risponde.
- `chat_policy` e `automatic_policy` come opzioni **deprecate**: se presenti
  (install legacy), usarle una-tantum per derivare l'ordine iniziale, poi la
  catena unica è la sola fonte. Non più esposte in UI.

### 2.2 Impatto codice
- `LLMRouter`: da `automatic_policy`/`chat_policy` a **una** `model_chain`
  ordinata (+ eventuale ordine manuale persistito). `route(mode)` non varia più
  in base a `mode` chat/automatic per la *catena* (l'entità decide il modello,
  non la funzione). Mantenere retro-compat interna finché il call-site non è
  migrato.
- La distinzione chat-vs-proattivo resta a livello di **esecuzione** (chat =
  risposta sincrona; Agentbot = verdetto su coda), ma **non** guida più la
  scelta modello.

---

## 3. Modello per-entità (in-app `#/models`)

### 3.1 Un campo modello per entità
- **Chatbot:** già ha `model` (default `"auto"`, `agent_engine.py:71`,
  editabile). Invariato concettualmente; la tendina attinge dai modelli dei
  provider attivi.
- **Agentbot:** oggi il modello è **nascosto** — risolto da `agent_type` →
  `AUTO_MODEL_MAP` (`claude_runner.py:236`, `backends/openai_compat_runner.py:52`).
  SP-2 **espone** un campo `model` per Agentbot (default `"auto"`), come per il
  Chatbot. `AUTO_MODEL_MAP` diventa il **fallback** quando `model="auto"` e la
  catena non impone un esplicito — non più l'unica via.
- **Brain:** un campo `model` (default `"auto"`) per il core di ragionamento.

`model = "auto"` ⇒ segue la catena globale (§2). `model = <esplicito>` ⇒ usa
quel modello (con failover alla catena solo se quel provider è giù, se
`bridge_fallback`/failover attivo).

### 3.2 Risoluzione (ordine di precedenza)
1. Se l'entità ha `model` esplicito e il suo provider è attivo → usa quello.
2. Altrimenti (`auto`) → primo provider attivo della catena globale che ha un
   modello idoneo; per Agentbot `auto`, se serve un default concreto, usa
   `AUTO_MODEL_MAP[agent_type]`.
3. Failover lungo la catena su errore/indisponibilità.

### 3.3 Embeddings (dichiarati separati)
`#/models` mostra una riga esplicita **"Embeddings (RAG/memoria)"** legata a
`local_model.embedding_provider`/`embedding_model`, con nota chiara:
**"l'Abbonamento non fa embeddings"**. Nessun cambiamento funzionale al binario
embeddings in SP-2 — solo trasparenza in UI.

---

## 4. UI `#/models` (minima) — UX-first

**Priorità UX (direttiva utente):** in HIRIS **ogni** sviluppo front-end passa
dall'agente **`ux-ui-specialist`** — sia come **design pass** prima di
implementare la sezione `#/models`, sia come **gate di review UX** dopo
l'implementazione (in aggiunta alla review spec+qualità). Obiettivo dichiarato:
la UX della config dell'addom è oggi il punto più debole (frammentata/criptica)
e va **elevata di priorità**; `#/models` è il primo tassello di questa pulizia,
il resto prosegue verso SP-4. Mentre si tocca la config SPA, applicare piccoli
miglioramenti di coerenza UX contigui (etichette/raggruppamenti) se a costo
marginale, **senza** allargare lo scope a un redesign completo (quello è SP-4).

Nuova voce di navigazione **"Modelli"** nella config SPA. Sezioni:
1. **Provider attivi** (read-only riflesso della addon-config): lista con
   stato ON/OFF + badge "manca credenziale" dove applicabile + link a "come si
   attiva nella config dell'addon".
2. **Catena auto** (globale): lista ordinata dei provider attivi, riordinabile
   (drag o frecce), con label del preset `llm_strategy` corrente.
3. **Assegnazione per-entità:** raggruppata — Chatbot (lista), Agentbot (lista),
   Brain (singolo) — ognuno con tendina modello (`auto` + modelli espliciti dei
   provider attivi). Il per-Agentbot qui è la novità.
4. **Embeddings:** riga informativa separata (§3.3).

Coerenza ES6+ ok per `#/config` (non è iOS 12; vedi
`project_retropanel_config_target` — analogo qui: la SPA config non è vincolata
ES5). Nessun emoji nei testi tecnici (coerenza prodotto).

## 5. API

- `GET /api/models/config` → stato provider (attivi/credenziale), catena
  globale ordinata, assegnazioni per-entità, riga embeddings. Nessun segreto nel
  payload (solo booleani "presente/assente").
- `PUT /api/models/config` → aggiorna ordine catena + assegnazioni per-entità
  (i toggle provider + key restano addon-config, **non** modificabili da qui in
  SP-2). Passa dal token interno / stessa auth delle altre API config.
### 5.1 Persistenza
- **Chatbot/Agentbot:** l'assegnazione modello persiste nel loro record entità
  esistente (campo `model`, già presente in `agent_engine.py`). Per Agentbot è
  reso scrivibile/leggibile via API (oggi ignorato a favore di `AUTO_MODEL_MAP`).
- **Brain:** non è (ancora) un record-entità discreto; in SP-2 il suo modello è
  un **singolo setting a livello app** (es. una piccola models-config store lato
  addon, chiave `brain_model`, default `"auto"`). SP-4, quando materializzerà il
  Brain come entità, lo assorbirà.
- **Ordine catena globale + preset:** persistiti in una **models-config store**
  lato addon (stesso store del `brain_model`), non nella addon-config statica
  (così l'utente può riordinare da `#/models` senza toccare `config.yaml`).
  L'ordine di default deriva da `llm_strategy`; l'override manuale, se presente,
  vince.

## 6. Sicurezza

- Nessun segreto esposto da `GET /api/models/config` (solo presenza/assenza).
- Toggle provider e key restano addon-config (superficie segreti invariata).
- Semaforo, contratto Agentbot, loopback MCP, token OAuth: **invariati**.
- Log: mai stampare key/token; verificare che i nuovi log del router non
  logghino modelli con credenziali inline.

## 7. Testing

- **Migrazione:** install legacy (key presenti, `chat_via_subscription=true`,
  toggle a false) → tutti i `provider_*` derivati correttamente; comportamento
  identico. Test unit sul mapping di derivazione.
- **Catena:** una sola catena; failover attraversa i provider attivi in ordine;
  provider OFF escluso anche con key presente; toggle ON senza credenziale
  escluso + badge.
- **Per-entità:** Chatbot/Agentbot/Brain con `auto` → segue catena; con
  esplicito → usa quel provider; Agentbot `model` ora leggibile/scrivibile via
  API ed effettivo a runtime (non più solo AUTO_MODEL_MAP).
- **Abbonamento:** solo `provider_subscription` attivo → Chatbot+Brain+Agentbot
  in auto risolvono sull'abbonamento; runner in-addon `should_start_agent_worker`
  parte con il nuovo gate (`provider_subscription` AND token) invece del vecchio
  `chat_via_subscription`.
- **API:** `GET` non perde segreti; `PUT` valida e persiste; regressione sui
  ~1685 test esistenti verde.
- Deprecati `chat_policy`/`automatic_policy`: test che, se presenti, derivano
  l'ordine iniziale senza rompere.

## 8. Touchpoint codice (per il piano)

- `hiris/config.yaml` — nuovi `provider_*`; deprecare `chat_via_subscription`,
  `bridge_enabled` (mantenere lettura per migrazione).
- `hiris/app/server.py` ~1732-1747 (mapping env→app), ~1841 (costruzione
  `LLMRouter`), ~796/1898 (`should_start_agent_worker` → nuovo gate).
- `hiris/app/llm_router.py` — `_norm_policy`, costruttore, `route`/`_route`:
  da due policy a una `model_chain`.
- `hiris/app/claude_runner.py:236` + `hiris/app/backends/openai_compat_runner.py:52`
  — `AUTO_MODEL_MAP` da unica-via a fallback; onorare `model` esplicito per
  Agentbot.
- `hiris/app/agent_engine.py` — campo `model` già presente per agent; assicurare
  che valga per il tipo Agentbot; persistenza `model` per Brain.
- `hiris/app/api/handlers_chat.py:190` — `chat_via_subscription` → nuovo flag.
- Nuovo handler `hiris/app/api/handlers_models.py` (+ registrazione route).
- Nuova UI `hiris/app/static/config/models-route.js` (+ voce nav in `config.html`/`main.js`).

## 9. Rilascio

Bump **minor** (`0.99.5` → `0.100.0`): cambia la superficie di config (nuovi
toggle, nuova sezione) pur restando retro-compatibile. CHANGELOG dedicato.
Deploy live come SP-1a (push master → update addon in HA). Nessun impatto sul
gateway `.31` dormiente.
