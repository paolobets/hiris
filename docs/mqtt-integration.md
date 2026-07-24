# HIRIS — MQTT Integration

> Version: 0.33.0 · Updated: 2026-07-24

HIRIS publishes native Home Assistant entities via MQTT discovery, making every Persona's status and usage available as first-class HA entities — usable in dashboards and automations without any manual YAML configuration.

MQTT publishing is **outbound-only** (discovery + state). There is no longer a
2-way command channel: an earlier version exposed a writable `enabled` switch
and a `run_now` button over MQTT, wired to the old autonomous-agent scheduler.
That scheduler was retired — the proactive layer today is the built-in
Sentinella (see `docs/how-it-works.md`), and Personas run only on demand from
chat — so there is nothing left in HIRIS to enable/disable or "run now" via a
remote command. Both controls were removed; see "Upgrading from an older
version" below.

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

For each configured Persona, HIRIS publishes the following entities via MQTT auto-discovery. Replace `{agent_id}` with the Persona's ID (hyphens are converted to underscores in entity IDs — e.g. ID `hiris-default` → entity IDs use `hiris_default`). All of them are **read-only** (`sensor`) — there is no writable control entity anymore.

### `sensor.hiris_{agent_id}_status`

Current operational state of the Persona.

| Value | Meaning |
|-------|---------|
| `idle` | Not currently running |
| `running` | Currently executing a chat turn |
| `error` | Last run failed |

### `sensor.hiris_{agent_id}_budget_eur`

Cumulative cost (EUR) accrued by this Persona so far. Informational only.

- Unit of measurement: `EUR`
- Device class: `monetary`

### `sensor.hiris_{agent_id}_budget_remaining_eur`

Always reports `unlimited` — Personas no longer have a per-agent budget cap or auto-disable (that mechanism was retired along with the old autonomous-agent fields). Kept for backward compatibility with existing dashboards/automations built on this entity.

### `sensor.hiris_{agent_id}_tokens_used_today`

Total tokens consumed by the Persona since UTC midnight.

- Resets daily at 00:00 UTC

### `sensor.hiris_{agent_id}_enabled`

Whether the Persona is enabled (`ON`/`OFF`). Read-only — enable/disable it from the HIRIS config UI, not via MQTT (see "Upgrading from an older version" below for what changed).

### `sensor.hiris_{agent_id}_last_run`

Timestamp of the Persona's most recent run.

### `sensor.hiris_{agent_id}_last_result`

Text output of the Persona's most recent run. Updated after every execution.

---

## Using entities in dashboards

Once MQTT is configured and the add-on has started, all entities appear in HA automatically. A minimal status card in YAML:

```yaml
type: entities
title: HIRIS Personas
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

Versions before this one published a writable `switch.hiris_{agent_id}_enabled` and a `button.hiris_{agent_id}_run_now`, plus two inbound MQTT command topics (`hiris/agents/{agent_id}/enabled/set`, `hiris/agents/{agent_id}/run_now/set`). Both entities and topics were wired to the old autonomous-agent scheduler/executor, which has been retired — flipping the switch or pressing the button did nothing useful even before this doc was updated.

On first restart after upgrading, HIRIS publishes an empty discovery payload on the old `switch`/`button` config topics, which causes HA to remove those two stale entities automatically. The `enabled` state itself is still available, just as the read-only `sensor.hiris_{agent_id}_enabled` described above. Any automation that called `switch.turn_on/off` or `button.press` on the old entities will need to be updated to use the HIRIS config UI instead.

---

## Troubleshooting

**Entities do not appear in HA after starting the add-on:**
- Verify the MQTT integration is set up in HA (Settings → Devices & Services → MQTT)
- Confirm the broker host and port in the HIRIS add-on configuration
- Check the add-on log (Supervisor → HIRIS → Log) for connection errors

**Old `switch`/`button` entities are still visible after upgrading:**
Restart the add-on once to force HIRIS to (re-)publish the removal discovery payload for both retired entities.
