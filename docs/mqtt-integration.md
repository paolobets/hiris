> ## ⚠️ Superseded document — Refactor 2.0 (4 August 2026)
>
> This document describes HIRIS **before** Refactor 2.0. It talks about *Sentinella*, *Agentbot*,
> a four-colour *semaforo* and a configuration panel for AI entities — all of which the refactor
> has retired or rewritten.
>
> **What HIRIS must be now:** [`docs/design/2026-08-04-scope-hiris.md`](design/2026-08-04-scope-hiris.md) (Italian)
> **What the code does today:** [`docs/design/2026-08-03-analisi-funzionale.md`](design/2026-08-03-analisi-funzionale.md) (Italian)
>
> The purely operational parts (installation, keys, add-on options) are still useful. It will be
> rewritten as the final act of the refactor, against the real product.

# HIRIS — MQTT Integration

> Version: 1.0.0 · Updated: 2026-07-29

HIRIS publishes native Home Assistant entities via MQTT discovery, making every Chatbot's status and usage available as first-class HA entities — usable in dashboards and automations without any manual YAML configuration.

MQTT publishing is **outbound-only** (discovery + state) and covers **Chatbots only** — Agentbots and the Brain are not published as MQTT entities. There is no 2-way command channel: an earlier version exposed a writable `enabled` switch and a `run_now` button over MQTT, wired to the old autonomous-agent scheduler. That scheduler was retired — the proactive layer today is Agentbots (own trigger, own declared action), and Chatbots run only on demand from chat — so there is nothing left to enable/disable or "run now" via a remote command. Both controls were removed; see "Upgrading from an older version" below.

---

## Configuration

Add the MQTT broker details to the HIRIS add-on configuration:

```yaml
mqtt:
  host: core-mosquitto          # hostname or IP of your MQTT broker
  port: 1883                    # default MQTT port
  user: ""                      # leave empty if no authentication is required
  password: ""                  # leave empty if no authentication is required
```

If you use the [Mosquitto add-on](https://github.com/home-assistant/addons/tree/master/mosquitto) for Home Assistant, set `host: core-mosquitto`. For an external broker, use its IP address or hostname.

HIRIS connects to the broker on startup and reconnects automatically with exponential backoff if the connection drops.

---

## Published entities

For each configured Chatbot, HIRIS publishes the following entities via MQTT auto-discovery. Every entity is registered under discovery `unique_id` `chatbot_{id}_{metric}` and state topic `hiris/chatbots/{id}/{metric}`, with device identifier `chatbot_{id}`. The actual `entity_id` Home Assistant assigns is derived from the Chatbot's display name, not from `{id}` directly — check **Settings → Devices & Services → MQTT** for the exact entity IDs on your installation. All published entities are **read-only** (`sensor`) — there is no writable control entity anymore.

### `status`

Current operational state of the Chatbot.

| Value | Meaning |
|-------|---------|
| `idle` | Not currently running |
| `running` | Currently executing a chat turn |
| `error` | Last run failed |

### `budget_eur`

Cumulative cost (EUR) accrued by this Chatbot so far. Informational only.

- Unit of measurement: `EUR`
- Device class: `monetary`

### `budget_remaining_eur`

Always reports `unlimited` — Chatbots have no per-entity budget cap or auto-disable (that mechanism was retired). Kept for backward compatibility with existing dashboards/automations built on this entity.

### `tokens_used_today`

Total tokens consumed by the Chatbot since UTC midnight.

- Resets daily at 00:00 UTC

### `enabled`

Whether the Chatbot is enabled (`ON`/`OFF`). Read-only — enable/disable it from the HIRIS config UI, not via MQTT (see "Upgrading from an older version" below for what changed).

### `last_run`

Timestamp of the Chatbot's most recent run.

### `last_result`

Text output of the Chatbot's most recent run (truncated to 255 characters). Updated after every execution.

---

## Using entities in dashboards

Once MQTT is configured and the add-on has started, all entities appear in HA automatically. Look up the exact entity IDs under **Settings → Devices & Services → MQTT** (search for the device named `HIRIS <chatbot name>`), then reference them in a minimal status card:

```yaml
type: entities
title: HIRIS Chatbots
entities:
  - entity: sensor.hiris_default_status
    name: Status
  - entity: sensor.hiris_default_enabled
    name: Enabled
  - entity: sensor.hiris_default_tokens_used_today
    name: Tokens today
  - entity: sensor.hiris_default_last_result
    name: Last result
```

---

## Upgrading from an older version

Versions before 0.102.0 published entities under the pre-rename scheme: discovery `unique_id` `hiris_{id}_{metric}` and state topic `hiris/agents/{id}/{metric}` (plus a writable `switch.hiris_{id}_enabled` and a `button.hiris_{id}_run_now`, wired to the old autonomous-agent scheduler/executor, which has been retired — flipping the switch or pressing the button did nothing useful even before this doc was updated).

On first restart after upgrading, HIRIS retracts every old-scheme discovery config (both the `sensor` entities and the retired `switch`/`button` entities) and the old retained state topics under `hiris/agents/...`, then republishes everything under the new `chatbot_{id}` / `hiris/chatbots/...` scheme. A reorder of the HIRIS entities in Home Assistant after upgrading is expected. The `enabled` state itself is still available, just as the read-only `enabled` sensor described above — any automation that called `switch.turn_on/off` or `button.press` on the old entities needs to be updated to use the HIRIS config UI instead.

---

## Troubleshooting

**Entities do not appear in HA after starting the add-on:**
- Verify the MQTT integration is set up in HA (Settings → Devices & Services → MQTT)
- Confirm the broker host and port in the HIRIS add-on configuration
- Check the add-on log (Supervisor → HIRIS → Log) for connection errors

**Old `switch`/`button` entities are still visible after upgrading:**
Restart the add-on once to force HIRIS to (re-)publish the removal discovery payload for both retired entities.
