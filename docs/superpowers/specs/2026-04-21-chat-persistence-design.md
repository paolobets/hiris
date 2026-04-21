# HIRIS — Chat Persistence & Max Turns Design

**Date:** 2026-04-21  
**Status:** Approved  
**Scope:** Phase 1 — chat agent improvements

---

## Context

Chat agents currently manage conversation history in browser memory only. On page refresh, all history is lost. Additionally, there is no per-agent limit on conversation length, and no UI indicator of session progress.

---

## Features

### 1. Chat History Persistence

Each chat agent stores its conversation history in a dedicated JSON file on the server. History is shared across all family members accessing the same HA instance (Phase 1 behavior). Per-user isolation (by HA session token) is deferred to Phase 2.

**Storage location:** `/data/chat_history_{agent_id}.json`

**File schema:**
```json
{
  "schema_version": 1,
  "agent_id": "hiris-default",
  "messages": [
    {
      "role": "user",
      "content": "Quante luci sono accese?",
      "timestamp": "2026-04-21T10:00:00Z"
    },
    {
      "role": "assistant",
      "content": "Ci sono 3 luci accese nel salone.",
      "timestamp": "2026-04-21T10:00:05Z"
    }
  ]
}
```

**Auto-cleanup:** Messages older than 30 days are filtered out at load time. No background job required.

**Manual reset:** User can clear history via "Nuova conversazione" button in the chat UI.

**New module:** `app/chat_store.py`
- `load_history(agent_id: str, data_dir: str) -> list[dict]` — reads file, filters 30-day-old messages, returns `[{role, content}]` (no timestamp, for Claude API compatibility)
- `save_history(agent_id: str, messages: list[dict], data_dir: str) -> None` — atomic write (tmp + replace)
- `clear_history(agent_id: str, data_dir: str) -> None` — deletes or empties the history file

### 2. Max Messages Per Session

A new optional field `max_chat_turns` on each chat agent limits how many user-assistant exchanges can occur in a single session. When the limit is reached, the input is disabled until the user starts a new conversation.

**Default:** `0` (unlimited).

**Counter display:** Shown below the input box only when `max_chat_turns > 0`. Format: `"3 / 10 messaggi"`.

**When limit is reached:**
- Input textarea is disabled
- Message shown: `"Sessione completata — avvia una nuova conversazione"`
- "Nuova conversazione" button is highlighted

---

## Architecture

### New module: `app/chat_store.py`

Standalone module with no dependency on `Agent` or `ClaudeRunner`. Operates purely on files. Used by `handlers_chat.py`.

### Agent dataclass change

One new field in `agent_engine.py`:

```python
max_chat_turns: int = 0  # 0 = unlimited
```

Added to:
- `Agent` dataclass
- `UPDATABLE_FIELDS` set
- `_load()` deserialization
- `create_agent()` and `update_agent()` methods

### New API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/agents/{id}/chat-history` | Returns `{messages: [...]}` |
| `DELETE` | `/api/agents/{id}/chat-history` | Clears history, returns `{ok: true}` |

Both endpoints live in a new handler file `app/api/handlers_chat_history.py` to keep `handlers_chat.py` focused.

### Modified: `handlers_chat.py` — `handle_chat`

**Breaking change:** the client-sent `history` field in the POST body is ignored after this change. The server-side history file is authoritative. The frontend no longer needs to track or send history.

**`data_dir`** is read from `request.app["data_dir"]` — the same `/data` directory already used for `agents.json` and `usage.json`, set at startup in `main.py`.

Flow after this change:
1. Load history via `chat_store.load_history(agent_id, data_dir)`
2. Count current turns (number of "user" role messages in history)
3. If `max_chat_turns > 0` and `turns >= max_chat_turns`: return `{"error": "max_turns_reached", "turns": turns, "limit": max_chat_turns}` with HTTP 200
4. Pass history as `conversation_history` to `runner.chat()`
5. On success: append `{role: user, content, timestamp}` and `{role: assistant, content, timestamp}` to history
6. Save updated history via `chat_store.save_history(agent_id, ...)`
7. Return response as before (unchanged shape)

### Modified: `routes.py`

Register two new routes for chat history endpoints.

---

## Frontend Changes

### `index.html`

**On agent selection (chat-type agents):**
- Call `GET /api/agents/{id}/chat-history`
- Populate chat panel with returned messages (same rendering as live messages)
- Scroll to bottom

**Turn counter (below input box, visible only if `max_chat_turns > 0`):**
```
3 / 10 messaggi
```
Updates after each exchange.

**When limit reached:**
- Input `<textarea>` gets `disabled` attribute
- Counter turns red
- Show inline message: `"Sessione completata — avvia una nuova conversazione"`
- "Nuova conversazione" button becomes primary-styled

**"Nuova conversazione" button:**
- Always visible in chat header (not just at limit)
- On click: calls `DELETE /api/agents/{id}/chat-history`, clears chat panel, resets counter, re-enables input

### `config.html` (Agent Designer)

New field visible only when agent type is `chat`:

- **Label:** `Max messaggi per sessione`
- **Type:** numeric input, min 0
- **Placeholder:** `0 = illimitato`
- Positioned in the "Configurazione" section, after the model selector

---

## Data Flow

```
Browser                         handlers_chat.py          chat_store.py
  │                                    │                        │
  │─── POST /api/chat ────────────────►│                        │
  │    {message, agent_id}             │── load_history() ─────►│
  │                                    │◄─ [{role,content}] ────│
  │                                    │                        │
  │                                    │ (check max_chat_turns) │
  │                                    │                        │
  │                                    │── runner.chat() ───────►[Claude API]
  │                                    │◄─ response ────────────│
  │                                    │                        │
  │                                    │── save_history() ─────►│
  │◄─── {response, debug} ────────────│                        │
```

---

## Out of Scope (Phase 1)

- Per-user history isolation (by HA session token) → Phase 2
- Multiple conversation threads per agent → Phase 2 (SQLite migration)
- History export/download → Phase 2
- `restrict_to_home` flag behavior change → not changed (current behavior is acceptable)

---

## Phase 2 Migration Path

When migrating to SQLite (`aiosqlite`):
- `chat_store.py` interface (`load_history`, `save_history`, `clear_history`) stays identical
- Only the internal implementation changes from file I/O to DB queries
- No changes needed in `handlers_chat.py` or frontend
- Per-user isolation: add `session_id` column, derive from HA Supervisor token
