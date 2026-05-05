# HIRIS — Configuration Guide

> Version: 0.9.6 · Updated: 2026-05-05

This guide covers configuration areas that require a conscious choice:
**AI providers and privacy**, **Notifications (Apprise)** and **Memory & RAG**.

---

## Table of Contents

1. [AI providers and privacy](#1-ai-providers-and-privacy)
   - [Which provider to choose](#which-provider-to-choose)
   - [Privacy table per provider](#privacy-table-per-provider)
   - [OpenRouter — unified proxy](#openrouter--unified-proxy-200-models-1-key)
   - [Local models (Ollama)](#local-models-ollama)
2. [Notifications (Apprise)](#2-notifications-apprise)
   - [How it works](#how-it-works)
   - [Telegram](#telegram-recommended)
   - [ntfy (self-hosted push)](#ntfy-self-hosted-push)
   - [Gotify](#gotify)
   - [Email](#email)
   - [Discord](#discord)
   - [WhatsApp (Twilio)](#whatsapp-twilio)
   - [Multiple channels](#multiple-channels)
   - [Testing the configuration](#testing-the-configuration)
3. [Memory & RAG](#3-memory--rag)
   - [How it works](#how-it-works-1)
   - [Option A — OpenAI embeddings](#option-a--openai-embeddings-simplest)
   - [Option B — Ollama embeddings (local, free)](#option-b--ollama-embeddings-local-free)
   - [Option C — model2vec (local, no server)](#option-c--model2vec-local-no-server)
   - [Disabling RAG](#disabling-rag)
   - [Tuning parameters](#tuning-parameters)

---

## 1. AI providers and privacy

HIRIS supports four AI providers. This section explains what leaves your home
with each, so you can choose consciously.

### Which provider to choose

| Use case | Recommended provider |
|----------|----------------------|
| Maximum quality, no privacy concern | **Claude (Anthropic)** |
| Family chat in italian/english | **Claude** or **OpenAI GPT** |
| Want 200+ models with 1 key + free tier option | **OpenRouter** |
| Absolute privacy, nothing leaves home | **Ollama** (local) |
| Mix: family chat on cloud, autonomous agents on Ollama | combine |

### Privacy table per provider

| Provider | What leaves home | Jurisdiction | Cost | Privacy policy |
|----------|------------------|--------------|------|----------------|
| **Claude** (Anthropic) | User messages + system prompt + tool args + HA responses | 🇺🇸 US | Pay-per-token | [anthropic.com/privacy](https://www.anthropic.com/legal/privacy) |
| **OpenAI** (GPT) | same | 🇺🇸 US | Pay-per-token | [openai.com/policies](https://openai.com/policies/) |
| **OpenRouter** | same (flows through OpenRouter US + chosen model's provider) | 🇺🇸 US + variable | Pay-per-token, **':free'** models available | [openrouter.ai/privacy](https://openrouter.ai/privacy) |
| **Ollama** (local) | **Nothing — everything stays on LAN** | 🏠 Your home | Free (HW power consumption) | N/A |

**What HIRIS means by "messages"**:
- For **chat agents**: text typed by the user, recent history, and the HA
  entity context that `SemanticContextMap` attaches (sensor names, states,
  area assignment).
- For **autonomous agents**: the system prompt + strategic context + textual
  representation of HA states filtered by the tools the agent invokes
  (`get_entity_states`, `get_home_status`, etc.).

**What NEVER leaves (for any provider)**:
- Your other service API keys (Anthropic, OpenAI, etc. — they live only in
  add-on internal `/data/options.json`)
- Home Assistant tokens (`SUPERVISOR_TOKEN`)
- HA `/config/.storage/` data
- HIRIS SQLite DBs (`hiris_memory.db`, `chat_history.db`,
  `hiris_knowledge.db`, `proposals.db`) — **never sent as such**;
  only the content requested as context for a specific request leaves.

### OpenRouter — unified proxy 200+ models, 1 key

OpenRouter is a service giving you access to 200+ models from dozens of
providers (Anthropic, OpenAI, Google, Meta, Mistral, Qwen, DeepSeek, ...)
with a **single API key**. Features:

- **Free models** marked `:free` (rate-limited but $0): Llama 3.3 70B,
  Gemma 3 27B, Qwen 2.5 72B, DeepSeek Chat, Mistral Nemo, Hermes 3 405B
- **Automatic failover** on OpenRouter's side: if a model is temporarily
  down, OpenRouter reroutes to backup
- **Unified billing**: you pay OpenRouter, OpenRouter pays providers

**Setup**:
1. Sign up at [openrouter.ai](https://openrouter.ai/) and create an API key
2. Paste the key in HIRIS → add-on options → **OpenRouter API Key**
3. In Agent Designer → **Model** field → type `openrouter:provider/model`
   - Free example: `openrouter:meta-llama/llama-3.3-70b-instruct:free`
   - Paid example: `openrouter:anthropic/claude-sonnet-4-6`

**Privacy trade-off**: your messages flow through OpenRouter (US) **and**
the chosen model's provider. Double hop vs. direct Claude/OpenAI. For strict
GDPR concerns, prefer EU-based providers (Mistral La Plateforme direct) or
local Ollama.

### Local models (Ollama)

See [`docs/full-local-mode.md`](full-local-mode.md) for the full setup guide.
Quick summary:

1. Install Ollama on a LAN-reachable host
2. `ollama pull <model>` to download (e.g. `gemma3:9b`, `mistral-nemo:12b`,
   `qwen2.5:14b`)
3. In HIRIS options → **Ollama URL** (e.g. `http://192.168.1.74:11434`) and
   **Ollama Model Name** (e.g. `gemma3:9b`)

**Models with thinking-by-default** (Gemma 4, Qwen QwQ, DeepSeek R1, ...):
since v0.9.6 HIRIS auto-disables thinking via `think: false` parameter to
avoid timeouts — the model answers directly without emitting its
"stream of consciousness".

---

## 2. Notifications (Apprise)

### How it works

HIRIS uses [Apprise](https://github.com/caronc/apprise) to send notifications through 80+ services.
You configure one or more **Apprise URLs** in the add-on settings — each URL points to a delivery channel.

When an agent calls `send_notification(message, channel="apprise")`, HIRIS sends the message to **all configured URLs** simultaneously.

> **Note:** if `apprise_urls` is empty, notifications fall back to Home Assistant's push notification service (`notify.notify`).

---

### Telegram (recommended)

Telegram is the simplest and most reliable option for home notifications.

**Step 1 — Create a bot**

1. Open Telegram and start a chat with [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the **Bot Token** (format: `1234567890:ABCDef-ghijklmno`)

**Step 2 — Get your Chat ID**

1. Send any message to your new bot
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id": 987654321}` in the JSON — that is your **Chat ID**

**Step 3 — Configure HIRIS**

```yaml
apprise_urls:
  - tgram://1234567890:ABCDef-ghijklmno/987654321
```

For a **group chat**, use the group's Chat ID (negative number, e.g. `-100987654321`):

```yaml
apprise_urls:
  - tgram://1234567890:ABCDef-ghijklmno/-100987654321
```

---

### ntfy (self-hosted push)

[ntfy](https://ntfy.sh) is an open-source push notification service. You can use the free hosted version or self-host it.

**Using ntfy.sh (hosted, free)**

```yaml
apprise_urls:
  - ntfy://ntfy.sh/my-hiris-alerts
```

Replace `my-hiris-alerts` with any unique topic name. Subscribe to the same topic in the ntfy mobile app.

**Using a self-hosted ntfy instance**

```yaml
apprise_urls:
  - ntfys://ntfy.yourdomain.com/my-topic
```

Use `ntfy://` for HTTP or `ntfys://` for HTTPS.

**With authentication**

```yaml
apprise_urls:
  - ntfys://username:password@ntfy.yourdomain.com/my-topic
```

---

### Gotify

[Gotify](https://gotify.net) is a self-hosted notification server.

1. Create an application in the Gotify web UI and copy the **app token**
2. Configure HIRIS:

```yaml
apprise_urls:
  - gotifys://gotify.yourdomain.com/YourAppToken
```

Use `gotify://` for HTTP or `gotifys://` for HTTPS.

---

### Email

**Gmail (with App Password)**

1. Enable 2-Factor Authentication on your Google account
2. Generate an [App Password](https://myaccount.google.com/apppasswords) for "Mail"
3. Configure:

```yaml
apprise_urls:
  - mailtos://youraddress@gmail.com:AppPassword@smtp.gmail.com/recipient@example.com
```

**Generic SMTP**

```yaml
apprise_urls:
  - mailtos://user:password@smtp.yourdomain.com:587/recipient@example.com
```

---

### Discord

1. In your Discord server: **Settings → Integrations → Webhooks → New Webhook**
2. Copy the webhook URL (format: `https://discord.com/api/webhooks/ID/TOKEN`)
3. Configure:

```yaml
apprise_urls:
  - discord://WebhookID/WebhookToken
```

---

### WhatsApp (Twilio)

Requires a [Twilio](https://www.twilio.com) account with WhatsApp enabled.

```yaml
apprise_urls:
  - twilio://AccountSID:AuthToken@+1415xxxxxxx/+39333xxxxxxx
```

Where `+1415xxxxxxx` is your Twilio WhatsApp number and `+39333xxxxxxx` is the recipient.

---

### Multiple channels

You can configure several channels at once — all will receive every notification:

```yaml
apprise_urls:
  - tgram://BotToken/ChatID
  - ntfys://ntfy.yourdomain.com/hiris
  - mailtos://user:pass@smtp.yourdomain.com/boss@example.com
```

---

### Testing the configuration

After saving the add-on configuration, ask HIRIS in chat:

> "Send me a test notification"

HIRIS will call `send_notification` and you should receive the message on all configured channels within a few seconds.

If nothing arrives, check the add-on log (**Supervisor → HIRIS → Log**) for Apprise error messages.

---

## 3. Memory & RAG

### How it works

HIRIS stores conversation memories in a local **SQLite database** (`/config/hiris/memory.db`).
Each memory is saved as text together with a **vector embedding** — a numerical representation of its meaning.

When you or an agent send a message, HIRIS automatically:
1. Converts the message to an embedding
2. Searches the database for the **k most similar** past memories (cosine similarity)
3. Injects the relevant memories into the AI prompt as additional context

This allows HIRIS to remember preferences, facts, and past events across separate conversations.

**Without a configured embedding provider**, the memory tools (`save_memory`, `recall_memory`) still work but semantic search is disabled — only exact keyword matches are returned. RAG injection is effectively turned off.

---

### Option A — OpenAI embeddings (simplest)

Uses the same OpenAI API key already configured for the primary model.

**Requirements:** `openai_api_key` must be set.

**Recommended model:** `text-embedding-3-small` — fast, cheap (~$0.02/1M tokens), excellent quality.

**Configuration:**

```yaml
memory:
  embedding_provider: openai
  embedding_model: text-embedding-3-small
  rag_k: 5
  retention_days: 90
```

**Alternative models:**

| Model | Cost | Notes |
|-------|------|-------|
| `text-embedding-3-small` | $0.02/1M tokens | ✅ Recommended |
| `text-embedding-3-large` | $0.13/1M tokens | Higher quality, slower |
| `text-embedding-ada-002` | $0.10/1M tokens | Legacy, avoid for new setups |

---

### Option B — Ollama embeddings (local, free)

Runs embeddings entirely on your local hardware. No API costs, no data leaves your network.

**Requirements:** Ollama must be reachable from the HIRIS add-on (same network).
The `local_model.url` must also be set (HIRIS reuses it as the Ollama base URL).

**Step 1 — Pull an embedding model in Ollama**

```bash
ollama pull nomic-embed-text
```

Other good options:
- `mxbai-embed-large` — higher quality, larger (670 MB)
- `all-minilm` — very fast and small (23 MB)

**Step 2 — Configure HIRIS**

```yaml
local_model:
  url: http://192.168.1.10:11434   # your Ollama host
  model: ""                        # optional: also set a local chat model

memory:
  embedding_provider: ollama
  embedding_model: nomic-embed-text
  rag_k: 5
  retention_days: 90
```

> **Important:** `local_model.url` is used both for Ollama chat models and for Ollama embeddings.
> You do not need to set `local_model.model` just to use Ollama embeddings.

---

### Option C — model2vec (local, no server)

Runs embeddings entirely in-process with no server, no API key, and no external calls.
**This is the recommended local option for Home Assistant add-ons** — it is the only fully local
embedding solution compatible with Alpine Linux (the base of all HA add-ons).

**Requirements:** none — the model is downloaded from HuggingFace Hub on first startup and cached
in `/config/hiris/models/huggingface/`. Subsequent startups are instant.

**First startup:** HIRIS downloads the model (~30 MB for the default). This happens once.

**Configuration:**

```yaml
memory:
  embedding_provider: model2vec
  embedding_model: minishlab/potion-base-8M
  rag_k: 5
  retention_days: 90
```

Leave `embedding_model` empty to use the default (`minishlab/potion-base-8M`) automatically.

**Available models:**

| Model | Size | Quality (MTEB) | Notes |
|-------|------|----------------|-------|
| `minishlab/potion-base-8M` | ~30 MB | 51.1 | ✅ Recommended — fast and compact |
| `minishlab/potion-base-32M` | ~120 MB | 52.1 | Higher quality, larger |

> **Technical note:** model2vec uses static (distilled) embeddings implemented in pure Python.
> All dependencies (`numpy`, `tokenizers`, `safetensors`) ship Alpine-compatible `musllinux` wheels,
> making this the only local embedding option that works on HA add-ons without modification.

---

### Disabling RAG

Leave `embedding_provider` empty to disable semantic memory search entirely.
Memory tools will still be available but retrieval falls back to simple keyword matching.

```yaml
memory:
  embedding_provider: ""
  embedding_model: ""
  rag_k: 5
  retention_days: 90
```

---

### Tuning parameters

| Parameter | Default | Guidance |
|-----------|---------|----------|
| `rag_k` | 5 | Number of memories injected per request. Increase to 10 for agents with rich history; decrease to 2-3 to save tokens. |
| `retention_days` | 90 | Memories older than this are deleted automatically at 03:00 UTC. Set to 0 to keep forever (not recommended — the store grows unbounded). |
| `history_retention_days` | 90 | Conversation message history retention, independent of vector memories. |

**Typical configurations:**

```yaml
# Minimal token usage
memory:
  embedding_provider: openai
  embedding_model: text-embedding-3-small
  rag_k: 3
  retention_days: 30

# Rich context for power users
memory:
  embedding_provider: openai
  embedding_model: text-embedding-3-large
  rag_k: 10
  retention_days: 365
```
