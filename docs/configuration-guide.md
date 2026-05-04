# HIRIS — Configuration Guide

> Version: 0.9.2 · Updated: 2026-05-04

This guide covers the two configuration areas that require external setup before they work:
**Notifications (Apprise)** and **Memory & RAG**.
All other options (API keys, model selection, log level, theme) are self-explanatory from the add-on UI.

---

## Table of Contents

1. [Notifications (Apprise)](#1-notifications-apprise)
   - [How it works](#how-it-works)
   - [Telegram](#telegram-recommended)
   - [ntfy (self-hosted push)](#ntfy-self-hosted-push)
   - [Gotify](#gotify)
   - [Email](#email)
   - [Discord](#discord)
   - [WhatsApp (Twilio)](#whatsapp-twilio)
   - [Multiple channels](#multiple-channels)
   - [Testing the configuration](#testing-the-configuration)
2. [Memory & RAG](#2-memory--rag)
   - [How it works](#how-it-works-1)
   - [Option A — OpenAI embeddings](#option-a--openai-embeddings-simplest)
   - [Option B — Ollama embeddings (local, free)](#option-b--ollama-embeddings-local-free)
   - [Option C — model2vec (local, no server)](#option-c--model2vec-local-no-server)
   - [Disabling RAG](#disabling-rag)
   - [Tuning parameters](#tuning-parameters)

---

## 1. Notifications (Apprise)

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

## 2. Memory & RAG

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
