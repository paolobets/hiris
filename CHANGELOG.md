# HIRIS — Changelog

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
