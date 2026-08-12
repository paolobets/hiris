<p align="center">
  <img src="hiris/icon.png" alt="HIRIS logo" width="120"/>
</p>

<h1 align="center">HIRIS</h1>
<p align="center"><em>Home Intelligent Reasoning & Integration System</em></p>

<p align="center">
  <a href="https://github.com/paolobets/hiris/releases"><img src="https://img.shields.io/github/v/release/paolobets/hiris?label=version&color=blue" alt="version"/></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2024.7%2B-41BDF5" alt="Home Assistant"/>
  <img src="https://img.shields.io/badge/arch-amd64%20%7C%20aarch64-lightgrey" alt="arch"/>
  <img src="https://img.shields.io/badge/license-Proprietary-red" alt="license"/>
</p>

<p align="center">
  <strong>The knowledge of your home, and a chat to ask it.</strong>
</p>

---

## What HIRIS 2.0 is

> **HIRIS knows, and does not act.**

HIRIS 2.0 is a Home Assistant add-on that builds and keeps a living
representation of your house — floors, areas, devices, entities, and what the
house already does on its own — and gives you one chat to interrogate it.

That is the whole product. It reads Home Assistant and it remembers what you
tell it. It does not turn anything on or off, does not send notifications, and
does not create or modify automations. The HTTP primitive that called an HA
service was removed from the client altogether
(`hiris/app/proxy/ha_client.py:145-151`) — "doesn't act" is not a setting you
could flip, it is the absence of the code.

Periodic work *does* run — seven APScheduler jobs are registered at startup —
but every one of them is internal housekeeping: none of them speaks to you, and
none of them touches the house. They are: the entity-inventory reload every
2 minutes (`hiris/app/server.py:969-974`), the `mtime` sentinel over
`automations.yaml`/`scripts.yaml` every 5 minutes (`:980-985`), chat-history
retention at 03:00, and the reasoning-queue sweep every 2 minutes. The
03:30 history compaction, the 04:00 nightly digest and the Mayan document
poll were removed in 2.1.0 together with the document integration and the
knowledge archive they fed.

2.0 is a reduction to the core. Version 1.x shipped a much wider surface
(autonomous agents, a proactive brain, proposals, an action gate); most of it
has been taken out of the running product on purpose. See
[what is *not* in 2.0](#what-is-not-in-20) below, and the scope document that
governs the refactor:
[`docs/design/2026-08-04-scope-hiris.md`](docs/design/2026-08-04-scope-hiris.md)
(Italian).

---

## What it knows

### The registry of the house

On startup, and again whenever Home Assistant tells it something changed, HIRIS
re-reads the HA registries over the WebSocket API — floors, areas, devices,
entities, labels, categories, config entries — and rebuilds the house from them
(`hiris/app/casa/anagrafe.py:14-50`, `hiris/app/proxy/ha_client.py:564-572`; the
registry-update subscriptions live at `hiris/app/proxy/ha_client.py:26-31`, the
debounced rebuild at `hiris/app/server.py:403`). The meaning is never guessed:
it is whatever you already declared in Home Assistant.

If a registry fails to answer, HIRIS keeps the previous copy and records the
gap rather than replacing a good house with ten empty lists
(`hiris/app/casa/anagrafe.py:39-49`).

### What the house already does by itself

HIRIS reads `automations.yaml` and `scripts.yaml` from your HA config directory
and cross-references them with live state
(`hiris/app/casa/comportamento.py`). The file says what is *written*; the state
says what *exists* — and the difference is information. Automations written by
hand outside those files are known by name but not by body, and HIRIS says so
instead of pretending they are empty.

### The nucleo — one compact house, in every prompt

Everything above is condensed into a single text that goes into the model's
context on every turn (`hiris/app/casa/nucleo.py`, shared with the chat via
`hiris/app/api/handlers_chat.py:317`). With three hundred entities, listing them
all would blow the context window, so the nucleo **counts** rather than
enumerates — "Cucina: 2 luci, 1 sensore", not the entity ids.

It has five sections (`hiris/app/casa/nucleo.py:545-548,648`):

| Section | What it holds |
|---|---|
| `## La casa` | floors → areas → devices → entities, as counts |
| `## Notevole adesso` | what is currently on, open, playing, triggered… |
| `## Cio' che la casa fa gia' da sola` | automations and scripts |
| `## Cio' che le persone hanno detto` | the memories, in full |
| `## Cio' che HIRIS ignora` | **what HIRIS could not read** |

That last section is the point, not a footnote: **HIRIS declares what it does
not know instead of faking it.** When HA is unreachable, the nucleo says
*"Stato non letto (o dichiarato non attendibile): non si puo' dire se in
questo momento c'e' qualcosa di notevole -- non e' lo stesso di 'niente di
notevole'"* (`hiris/app/casa/nucleo.py:321-324`). The same discipline applies when the text
has to be truncated to fit: the cut is written *inside* the nucleo, not only in
a summary nobody reads.

### Anchored memory

Tell the chat something about the house and it is actually stored — with its
strength (preference, prohibition, fact, rule), an optional value or range,
optional conditions, and anchors to the areas/entities/devices it refers to
(`hiris/app/memoria/archivio.py:86`). An anchor that does not exist in the house
is not written, and the response says which one was dropped and why — the
memory itself is still saved in full.

Saved memories come back in the nucleo on the next turn, under
*"Cio' che le persone hanno detto"*.

---

## The chat, and its four tools

The chat is the only surface. The model gets the nucleo plus exactly four tools
(`hiris/app/casa/strumenti.py:57,250`, passed at
`hiris/app/api/handlers_chat.py:438-439,493-494`):

| Tool | What it does |
|---|---|
| `cerca` | finds an area, entity or device from a name or alias — and returns **every** candidate, flagging the ambiguous ones instead of silently picking the first |
| `guarda` | the detail of one single thing: an area with its entities and states, an entity, a device, an automation or script *with its body*, or a memory with its interpretation |
| `ricorda` | saves what a person said, with its anchors to the house |
| `richiama` | the memories anchored to one part of the house |

None of the four touches Home Assistant: they read and they remember. There is
no fifth tool and no allowlist to configure — the catalogue of thirty-four
tools and the action gate that stood in front of them were both removed.

Answers stream token by token (`text/event-stream`) when the client asks for
it, and closed sessions are summarised back into the next conversation
(`hiris/app/api/handlers_chat.py:262-269,330-335`).

---

## AI providers

Five backends, each enabled independently, each used only when it is **both**
switched on **and** credentialed (`hiris/app/model_activation.py:14-35`):

| Provider | Credential |
|---|---|
| Claude API (Anthropic) | `claude_api_key` |
| OpenAI | `openai_api_key` |
| OpenRouter | `openrouter_api_key` |
| Ollama (local) | `local_model.url` + `local_model.model` |
| Claude subscription (Claude Max) | `claude_code_oauth_token` |

**Fallback chain.** With `model="auto"`, if the leading backend is unavailable
the next active one in the strategy order is tried
(`hiris/app/llm_router.py:45-55`):

- `balanced` (default): Claude → OpenRouter → OpenAI → Ollama
- `quality_first`: Claude → OpenAI → OpenRouter → Ollama
- `cost_first`: Ollama → OpenRouter → OpenAI → Claude

You can override the order manually; an active provider missing from a stale
saved order is appended rather than silently dropped
(`hiris/app/model_activation.py:37-78`).

Token counts and cumulative cost are tracked and readable at `GET /api/usage`.

### The second chat path: the subscription bridge

There is a second chat path. When it is active, a chat turn is handed to an
external subscription runner through a queue instead of being answered locally.

It is active when `bridge_enabled` **and** `chat_via_subscription` are both on
— **and also**, regardless of those two options, whenever
`provider_subscription` is enabled and `claude_code_oauth_token` is set: an
active subscription provider implies both flags
(`hiris/app/server.py:907,1332-1340`).

**That path now carries the nucleo, and — when it can — the four tools.** The
turn is enqueued together with the same context the synchronous chat composes
(`handlers_chat.py::_enqueue_chat_job`), and the runner probes `POST /api/mcp`
before it starts (`agent/runner.py::sonda_strumenti`). One boolean comes out of
that probe and decides two things at once: the prompt the model reads and the
arguments the CLI is launched with. When the probe succeeds the model has
`cerca`, `guarda`, `ricorda` and `richiama` under an `mcp__hiris__` prefix and
can look at the current state, not just the snapshot. When it fails, the answer
is prefixed with a line saying the tools were not available this turn
(`AVVISO_STRUMENTI_ASSENTI`) instead of quietly pretending it looked. Either
way it does not act on the home. The tool chips under a reply are drawn on this
path too (`handle_chat_reply_poll` → `send.js::pollChatReply`).

What still differs from the synchronous path: usage is **not** measured (the
subscription exposes neither tokens nor cost — `GET /api/usage` says so instead
of showing zeros), the reply arrives by polling rather than in one response, and
the turn is subject to `bridge_deadline_min` and to a separate daily cap.

---

## Installation

### Home Assistant Add-on Store

1. **Settings → Add-ons → Add-on Store** → ⋮ → **Repositories**
2. Add: `https://github.com/paolobets/hiris`
3. Find **HIRIS** → Install
4. Enable at least one provider and set its credential in the configuration
   tab, then start

### HACS

1. HACS → ⋮ → **Custom repositories**
2. URL: `https://github.com/paolobets/hiris` — Category: **Add-ons**
3. Install from the Add-ons section

---

## Configuration

Every option below exists in [`hiris/config.yaml`](hiris/config.yaml); the full
descriptions are in [`hiris/translations/en.yaml`](hiris/translations/en.yaml)
and are what the add-on UI shows.

### To get answers

| Option | Description |
|---|---|
| `provider_claude` · `provider_openai` · `provider_openrouter` · `provider_ollama` · `provider_subscription` | Enable a provider. A provider is used only if enabled **and** credentialed |
| `claude_api_key` · `openai_api_key` · `openrouter_api_key` | Cloud API keys |
| `claude_code_oauth_token` | OAuth token for the Claude subscription runner |
| `local_model.url` · `local_model.model` · `local_model.request_timeout` | Ollama base URL, model name, per-call timeout (10–1800s) |
| `llm_strategy` | `balanced` (default) · `quality_first` · `cost_first` |
| `chat_policy` | Explicit backend order for the chat, e.g. `claude,ollama` — empty means "use the strategy" |
| `hide_free_models` | Hide OpenRouter `:free` models from the model list |

> With `local_model.url` + `local_model.model` set and `provider_ollama`
> enabled, HIRIS runs offline against Ollama: the chat, the nucleo and the four
> tools all work without any cloud key. If no provider is both enabled and
> credentialed, AI calls are disabled.

### Subscription bridge

| Option | Description |
|---|---|
| `bridge_enabled` | Master switch for the external subscription runner — **unless** `provider_subscription` is on with a token, which forces it on |
| `chat_via_subscription` | Route chat turns to it (see the limit above). Only effective when `bridge_enabled` is on — and likewise forced on by an active subscription provider |
| `bridge_deadline_min` | Minutes before a queued turn expires (1–120, default 5) |
| `chat_daily_cap` | Max chat turns routed per day (0–1000, default 50) |

### General

| Option | Description |
|---|---|
| `theme` | `light` · `dark` · `auto` |
| `log_level` | `debug` · `info` · `warning` · `error` |
| `history_retention_days` | Days of conversation history kept before automatic deletion (default 90) |
| `internal_token` | Shared secret required by `/api/*` when the call does not come from the Supervisor ingress |
| `supervisor_ingress_cidr` | Source ranges treated as genuine Supervisor ingress (default `172.30.32.0/23`) |
| `debug_expose_port` | **Dev only.** Logs a warning at every startup; it does *not* open port 8099 by itself — that is the Network section of the add-on page |

### Carried over from 1.x — read, but inert

| Option | Description |
|---|---|
| `memory.embedding_provider` · `memory.embedding_model` | Read at startup, shown on the Models page — but **nothing in HIRIS computes an embedding today.** Similarity search is a postponed decision, not a cancelled one; when it is turned on, it will be configured from here. |

The `mayan.*` block and `memory.rag_k` were removed in 2.1.0 together with the
document integration and the knowledge archive — see the CHANGELOG.

---

## Lovelace chat card — removed for now

There is **no HIRIS card for your dashboards in this version**. The 1.x card
(`custom:hiris-chat-card`) has been removed from the product and will come back
rewritten, once the rest of 2.0 is finished. Until then, the chat lives in one
place: the add-on's own page.

If you had the card on a dashboard, that tile stops working — see the `[2.0.0]`
entry in [`CHANGELOG.md`](CHANGELOG.md). You do not have to clean up after it:
on first start after the update HIRIS **uninstalls what it had installed** —
the copy under `<ha-config>/www/hiris/` and the registered Lovelace resource —
touching only those, never a resource it did not add, and saying so in the log
(`hiris/app/server.py`, `_disinstalla_card_lovelace`). Removing the now-empty
card tile from your dashboard is the one gesture left to you.

---

## Interface

Opening the add-on shows the chat. A configuration panel is served at
`/config` as a small single-page app with six live routes:

| Route | What it does |
|---|---|
| `#/` | **What HIRIS knows** — the home as it was read (floors, areas, devices, entities) and the exact nucleo the model sees in chat. Says «not read yet» where it has not read, instead of showing a zero |
| `#/memoria` | The remembered facts: read them, correct them, forget them — with the anchors resolved against today's registry |
| `#/impostazioni` | The seven chat settings (system prompt, model, answer shape, reasoning, turn cap, home restriction, name) |
| `#/models` | Active providers, the automatic chain and the default model per provider |
| `#/usage` | Tokens and cost, or the reason why they cannot be measured |
| `#/history` | Historicisation: retention and compaction |

Both surfaces share one stylesheet and one palette. The rebuild inventory in
[`docs/design/2026-08-08-frontend-da-rifare.md`](docs/design/2026-08-08-frontend-da-rifare.md)
(Italian) is closed: all fourteen entries were resolved, and what remains open
is listed at the bottom of that document — none of it is a fault a tester can
run into.

**Stack:** Python 3.13 (Alpine) · aiohttp · Anthropic SDK · OpenAI SDK ·
APScheduler · SQLite · model2vec

---

## What is *not* in 2.0

These existed in 1.x and are deliberately **out of the running product**. The
code largely still sits in git history; anything that comes back will come back
rewritten, with a design of its own.

- **Actions of any kind** — no service calls, no turning things on or off, no
  creating or editing automations, scripts, scenes or dashboards
- **The semaforo** — tiers, denylists, step-up confirmations, per-action gating
- **Agentbot / Sentinella / agents** — nothing is triggered by a schedule or an
  event to reason on its own
- **The Brain**, its proposals and its advisories
- **Multiple chatbots**, their editors, their per-bot budgets and allowlists
- **Notifications** — no Apprise, no HA push, no Telegram/ntfy/…
- **MQTT**, the gateway, Test Run, the sandbox
- **HA health monitoring** — no `get_ha_health`, no `GET /api/health/ha`
- **The thirty-four-tool catalogue** — replaced by the four above

---

## Documentation

| Document | What it is | Language |
|---|---|---|
| [Prova la 2.0](docs/prova-la-2.0.md) | The sheet that goes with the test build: install, options, what to expect, what to report | 🇮🇹 Italiano |
| [Scope — HIRIS 2.0](docs/design/2026-08-04-scope-hiris.md) | The live source of truth: what HIRIS must be | 🇮🇹 Italiano |
| [La conoscenza di HIRIS](docs/design/2026-08-05-la-conoscenza-di-hiris.md) | The knowledge design 2.0 is built on | 🇮🇹 Italiano |
| [Mappa delle funzionalita'](docs/design/2026-08-05-mappa-funzionalita.md) | What survives the refactor, and what does not | 🇮🇹 Italiano |
| [Frontend da rifare](docs/design/2026-08-08-frontend-da-rifare.md) | The inventory of broken UI, for the next slice | 🇮🇹 Italiano |
| [CHANGELOG](CHANGELOG.md) | What changed, slice by slice | 🇮🇹 Italiano |

The guides that used to sit in `docs/` — architecture, how it works, use cases,
configuration, security, MQTT, full local mode, in both languages — have been
**deleted**. They described in the present tense a product that no longer exists:
Agentbot, the semaforo, notifications, MQTT. After this release the main features
are being reinvented, so those pages were not a reference for what comes next
either — and a banner on top of a wrong page is still a wrong page. Git keeps
them all: `git log --diff-filter=D -- docs/` finds them if you ever need one.

What is left under `docs/` is `docs/design/` — the record of the 2.0 refactor,
dated document by dated document — and `docs/archive/`, declared history by its
own README.

---

## License

Copyright © 2026 Paolo Bets. All Rights Reserved.  
Personal non-commercial use permitted. See [LICENSE](LICENSE) for details.
