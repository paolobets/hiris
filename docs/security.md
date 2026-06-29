# HIRIS — Security model & safe setup

This document explains how HIRIS protects your home when you connect an AI (the
built-in chat or Claude via MCP) to device control, and how to configure it safely.
Read it **before** exposing the MCP gateway. (Italian version: `sicurezza.md`.)

## In one sentence

HIRIS does not trust the AI: every **action** on devices is authorized
**server-side** by a "traffic-light" you control. **Reads** are free, **actions**
go through the traffic-light, and the AI **cannot change its own permissions**.

---

## 1. The traffic-light (semaforo)

The traffic-light governs **only direct device actions** (the `call_ha_service`
tool: turn on a light, set climate, open a cover, …). Reads (home status, history,
…) are always allowed.

Four levels, set in *Configuration → Gateway Access*:

| Level | Behaviour |
|---|---|
| 🟢 **Green** | runs immediately |
| 🟡 **Yellow** | held; sends an **actionable iPhone notification** (Approve/Deny) |
| 🔴 **Red** | held; **manual confirmation inside HIRIS only** (Approvals) |
| ⚪ **Off** | fully blocked |

### Per domain and per entity
- **Per domain**: pick the level per category (Lights, Climate, Locks, …).
- **Per entity** (advanced, "Per-entity overrides" box): a single entity **beats**
  its domain level. Examples:
  - *Switches* domain green, but `switch.gate off` → the gate stays blocked;
  - *Switches* domain off, but `switch.studio_lamp green` → only that lamp is controllable.

### What does NOT bypass the traffic-light
- A **scheduled task** action may contain **green actions only**: you cannot use a
  task to run a yellow/red/off action (verified and hardened).
- A `call_ha_service` **with no target entity** (broadcast) under an active whitelist
  is **rejected** (no blanket actions).
- The AI has **no tool** to change the traffic-light, apply proposals, or disable the
  kill-switch: those live only in the UI/panel, behind authentication.

---

## 2. Primary recommendation (the most important defence)

**Keep sensitive domains and entities NON-green.** Even if a prompt-injection (e.g.
a manipulated sensor name) convinced the AI to attempt a dangerous action, the
traffic-light holds it unless it is green.

Keep **yellow/red/off** unless truly needed: `lock`, `alarm_control_panel`, `cover`
(garage/critical), `siren`, `valve` (gas/water), and any `switch`/`script` wired to
dangerous loads (boiler, gate, pumps).

Use **per-entity overrides** for targeted exceptions (e.g. domain off but a single
lamp green) instead of making a whole heterogeneous domain green.

---

## 3. The MCP gateway (Claude from the cloud)

- **Connection**: one-time OAuth; the connector authorization is protected by
  **Cloudflare Access** (email policy). It does not reconnect per chat.
- **Transport**: HIRIS is not exposed on the LAN; the gateway reaches it over a
  Cloudflare tunnel with a service token. The HIRIS API port stays closed.
- **The gateway is a "policeman"**: rate-limit + **circuit breaker** (auto-kill on a
  runaway loop) + audit with provenance. **HIRIS is the decision-maker**
  (traffic-light + server-side allowlist).
- **Hard ceiling**: the HIRIS execute-API can run **only** a closed set of tools; no
  tool outside the list is reachable, whatever is configured.
- **Isolation**: Claude cannot read/write secrets, change the traffic-light policy,
  or disable the kill-switch / breaker.

> Note: **reads** (states, history, automation configs) still go to the cloud model.
> Don't put secrets in automations; remember presence/security history is readable
> (you can exclude it from *Historization*).

---

## 4. Proposals and tasks

- **Automations**: the AI never creates them on its own — it **proposes**. Find them
  in *Configuration → Proposals*; when **you** click *Activate*, HIRIS actually writes
  the automation into Home Assistant (config API + reload). Always review a proposal
  before activating it.
- **Tasks**: via MCP the AI can create scheduled tasks **with green actions only**
  (constrained to green domains/entities). `cancel_task` **always** requires your
  confirmation (so a safety task can't be silently disabled).

---

## 5. Data and backup

Data lives in the add-on's `/data`, in separate SQLite DBs: `knowledge.db`,
`history.db`, `proposals.db`, `hiris_memory.db`, **`vault.db`** (holds pseudonymizer
secrets), `chat`, etc. Since v0.20.0 the DBs use **WAL** (crash/power-loss
resilience) and **schema versioning** with safe migrations across add-on upgrades.

**Backup/restore**: **Home Assistant snapshots** include `/data` → take regular
snapshots. Because `vault.db` holds secrets, **protect the snapshots** (encrypted
storage / restricted access). To restore: restore the HA snapshot; HIRIS reopens the
DBs and applies any migrations automatically.

---

## 6. "Safe first start" checklist

1. Set a strong **`internal_token`** in the add-on options.
2. Do NOT expose the API port on the LAN (`debug_expose_port` off) except for diagnostics.
3. In *Gateway Access*: start with everything **off**, then make **green only** the
   low-risk domains (e.g. Lights); keep locks/alarm/gate **yellow/red**.
4. Use **per-entity overrides** for targeted exceptions.
5. Configure the **notification service** (e.g. `notify.iphone_bet`) for the yellow flow.
6. If using the MCP gateway: verify `/authorize` is behind Cloudflare Access (email
   policy) and the panel is behind authentication.
7. Enable periodic **HA snapshots** and protect them.

---

*For general architecture see `architecture.md`; for full configuration `configuration-guide.md`.*
