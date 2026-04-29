# HIRIS — MQTT Integration

> Version: 0.7.0 · Updated: 2026-04-29

HIRIS publishes native Home Assistant entities via MQTT discovery, making every agent's status, budget, and run controls available as first-class HA entities — usable in dashboards, automations, and scripts without any manual YAML configuration.

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

For each configured agent, HIRIS publishes the following entities via MQTT auto-discovery. Replace `{agent_id}` with the agent's ID (hyphens are converted to underscores in entity IDs — e.g. agent ID `hiris-default` → entity IDs use `hiris_default`).

### `sensor.hiris_{agent_id}_status`

Current operational state of the agent.

| Value | Meaning |
|-------|---------|
| `idle` | Agent is waiting for its next trigger |
| `running` | Agent is currently executing |
| `error` | Last run failed |

### `sensor.hiris_{agent_id}_budget_remaining_eur`

Budget remaining for the agent in EUR. Counts down from `budget_eur_limit` as the agent accumulates costs. When this reaches 0 the agent auto-disables.

- Unit of measurement: `EUR`
- State class: `measurement`

### `sensor.hiris_{agent_id}_tokens_used_today`

Total tokens consumed by the agent since UTC midnight.

- Resets daily at 00:00 UTC

### `switch.hiris_{agent_id}_enabled`

Enables or disables the agent. Writable — turning the switch off pauses the agent without deleting its configuration or history.

**Control from an HA automation:**

```yaml
service: switch.turn_off
target:
  entity_id: switch.hiris_monitor_enabled
```

### `sensor.hiris_{agent_id}_last_result`

Text output of the agent's most recent run. Updated after every execution.

### `button.hiris_{agent_id}_run_now`

Pressing this button triggers an immediate execution of the agent outside its normal schedule. Useful for testing or forcing a run from a dashboard or automation.

**Trigger from an HA automation:**

```yaml
service: button.press
target:
  entity_id: button.hiris_morning_briefing_run_now
```

---

## Controlling agents via MQTT

In addition to HA service calls, you can publish MQTT messages directly to control agents:

| Topic | Payload | Action |
|-------|---------|--------|
| `hiris/agents/{agent_id}/enabled/set` | `ON` / `OFF` | Enable or disable the agent |
| `hiris/agents/{agent_id}/run_now/set` | `ON` | Trigger an immediate run |

---

## Using entities in dashboards

Once MQTT is configured and the add-on has started, all entities appear in HA automatically. A minimal agent status card in YAML:

```yaml
type: entities
title: HIRIS Agents
entities:
  - entity: sensor.hiris_default_status
    name: Status
  - entity: sensor.hiris_default_budget_remaining_eur
    name: Budget remaining
  - entity: sensor.hiris_default_tokens_used_today
    name: Tokens today
  - entity: switch.hiris_default_enabled
    name: Enabled
  - entity: button.hiris_default_run_now
    name: Run now
```

---

## Example: alert when budget runs low

This automation sends a notification when an agent's remaining budget drops below €0.50:

```yaml
alias: HIRIS budget warning
description: Notify when the default agent is nearly out of budget
trigger:
  - platform: numeric_state
    entity_id: sensor.hiris_default_budget_remaining_eur
    below: 0.50
condition: []
action:
  - service: notify.notify
    data:
      title: "HIRIS — Budget Warning"
      message: >
        Agent "hiris-default" has only
        €{{ states('sensor.hiris_default_budget_remaining_eur') }} remaining.
        Top up the budget limit or disable the agent to avoid unexpected costs.
mode: single
```

---

## Troubleshooting

**Entities do not appear in HA after starting the add-on:**
- Verify the MQTT integration is set up in HA (Settings → Devices & Services → MQTT)
- Confirm the broker host and port in the HIRIS add-on configuration
- Check the add-on log (Supervisor → HIRIS → Log) for connection errors

**Switch state is not updating:**
HIRIS publishes state on every enable/disable event. If the switch appears stale, restart the add-on to re-publish discovery messages.

**`run_now` button is not triggering execution:**
- Ensure the agent is enabled (`switch.hiris_{agent_id}_enabled` is ON)
- Check the add-on log for any execution errors on the agent
