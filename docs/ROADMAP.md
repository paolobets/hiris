# HIRIS — Roadmap

> Last updated: 2026-04-29 | Current version: **v0.6.11**

---

## Current state — v0.6.3

### What's working today

| Area | Details |
|---|---|
| **Backend** | aiohttp server · 23+ API endpoints · HA REST + WebSocket + History + Calendar client |
| **AI layer** | Claude (Sonnet/Haiku/Opus) + OpenAI (GPT-4o, GPT-4.1, o-series) + Ollama local |
| **LLM Router** | Strategy routing (balanced / quality_first / cost_first) · automatic fallback chain |
| **Agent engine** | 4 agent types · APScheduler · HA WebSocket reactive triggers · action chaining · TaskEngine |
| **Tools** | 17+ tools: entity states, energy history, weather, HA services, notifications, calendar, memory, HTTP |
| **Memory & RAG** | SQLite vector store · `recall_memory` / `save_memory` tools · RAG injection before every AI call |
| **Notifications** | HA push · Telegram · Apprise unified layer (80+ channels via `apprise_urls`) |
| **MQTT bridge** | Publishes agent state as native HA entities via MQTT Discovery · 2-way subscribe |
| **Lovelace card** | `hiris-chat-card` · auto-deploy · SSE streaming · budget bar · typing indicator |
| **Security** | Per-agent filters · SSRF protection · auth middleware · prompt injection mitigation |
| **Budget** | Per-agent EUR limit · auto-disable on overspend · daily token tracking · usage dashboard |
| **UI** | Chat interface · Agent designer · Onboarding wizard · Mobile-optimized |

---

## Upcoming

### Sprint E — Lovelace agent card + HACS (v0.8.x)

| Feature | Description |
|---|---|
| `hiris-agent-card` | Custom Lovelace card: status badge, budget bar, last output, Run Now button |
| HACS packaging | `hacs.json`, `repository.json`, release notes for HACS store |
| Blueprint starter pack | Ready-to-use YAML: morning briefing, energy anomaly, door reactive |

---

### Phase 2 — Automation intelligence (v0.9.x)

| Feature | Description |
|---|---|
| **Automation proposals** | Claude proposes automations → review queue → Approve/Reject via mobile notification |
| **Anomaly baseline** | Rolling stats per numeric entity; findings triggered on N×stddev deviation |
| **Dashboard generator** | `generate_dashboard(description)` → Lovelace YAML, preview before applying |

---

### Phase 3 — Canvas (v1.0)

| Feature | Description |
|---|---|
| **Canvas designer** | n8n-style drag-and-drop agent designer |
| **HA Services** | Native `hiris.run_agent`, `hiris.chat`, `hiris.enable_agent` services |

---

### Phase 4 — Extended integrations (post v1.0)

| Feature | Description |
|---|---|
| **Email tool** | `send_email(to, subject, body)` via SMTP |
| **Vision tool** | `analyze_image(source)` — camera snapshots via Claude multimodal |
| **Telegram bot** | Long-polling bot with `/agent`, `/status`, streaming responses |

---

## Out of scope

| Feature | Reason |
|---|---|
| WhatsApp integration | Twilio compliance — Apprise covers this channel |
| Face recognition | Privacy concerns, out of scope |
| LangChain / LangGraph | Heavy dependency without proportional benefit |
| Full LiteLLM | Too heavy for Raspberry Pi — custom shim chosen |

---

## Definition of Done — v1.0

- [ ] CI passing on master for 30 consecutive days
- [ ] HACS distribution working
- [ ] Multi-provider (Claude + OpenAI + Ollama) all tested
- [ ] README + docs updated with demo video
- [ ] 20+ active beta users
- [ ] Zero open critical bugs
- [ ] Test coverage ≥70% on all modules
