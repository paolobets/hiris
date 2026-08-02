# HIRIS — Use Cases & Examples

> Version: 1.0.0 · Updated: 2026-07-29

HIRIS gives you two entities to build behavior with, both gated by the same
safety semaforo, both feeding the **Brain** (the home screen, `#/`, which
observes the house and proposes new Agentbots or automations):

- **Agentbot** — the proactive layer. Fires on its own, on a trigger (event
  or schedule), and either notifies you or runs one **declared** action —
  never an action the AI invents. Two flavors live on the same `#/agentbots`
  page: a fixed set of **built-in detectors/situations** (enable + tune
  thresholds, no authoring) and **custom Agentbots** you author yourself
  (trigger + action + optional AI reasoning step).
- **Chatbot** — the chat layer. A configuration (prompt, tool/entity/service
  scope, memory scope, conversation policy) used on demand by the user; it
  has no trigger of its own and never runs unless you ask it something.

This document collects realistic examples for both.

---

## Agentbot — built-in detectors, situations & preparation

The `#/agentbots` page's "Detector", "Situazioni" and "Preparazione" cards
expose a fixed set of built-in checks — enable and tune them (entities,
thresholds), no authoring required:

| Detector | What it detects | Tunable parameters |
|---|---|---|
| `opening` | Door/window left open past a threshold | entities, minutes |
| `fridge_temp` | Fridge/freezer temperature out of range for too long | entities, max °C, duration (min) |
| `power` | Instantaneous consumption above a threshold | entities, max watts |
| `battery` | A sensor/device battery below a threshold | entities, min % |

| Situation / preparation | What it does | Tunable parameters |
|---|---|---|
| `hot_and_away` | It's hot outside and nobody is home → runs one action (e.g. irrigation) for a few minutes | outdoor temp sensor, threshold °C, valve/switch entity, run minutes, skip if rain forecast |
| `away_alarm_off` | Flags when the alarm gets disarmed while everyone is away | alarm entity |
| `holistic` | Daily house summary at a fixed hour | hour, times per day |
| `evening_arrival` (preparation) | Prepares a scene ahead of an expected evening arrival | target scene/entity, sun entity, "not before" hour |

Every built-in follows the same pattern: **detector/situation → signal →
reasoner (Claude Haiku by default) → semaforo → notification and/or action**.
There is no system prompt to write: the reasoner has one fixed prompt shared
by every built-in, and always replies with the same internal JSON schema
(`verdict`, `severity`, `message`, `action`).

### Example — `opening` detector (formerly "Door Left Open")

**Goal:** be alerted if the front door stays open too long.

**Configuration (`#/agentbots` → Detector card):**
```json
{
  "detectors": {
    "opening": {
      "enabled": true,
      "entities": ["binary_sensor.front_door"],
      "open_minutes": 10
    }
  }
}
```

**What happens:** when `binary_sensor.front_door` flips to `on`, the detector
emits a signal with a 10-minute threshold. If the door stays open past the
threshold, the reasoner evaluates the context and — if it judges it worth
flagging — notifies.

```
🚪 The front door has been open for 12 minutes.
```

### Example — `power` detector (formerly "Energy Anomaly Detection")

**Goal:** be alerted to unusual consumption before the bill arrives.

```json
{
  "detectors": {
    "power": {
      "enabled": true,
      "entities": ["sensor.grid_power"],
      "max_watt": 3000
    }
  }
}
```

**What happens:** when `sensor.grid_power` exceeds 3000 W, the reasoner
evaluates the signal and notifies if it judges it an anomaly:
```
⚡ Unusual consumption: 3.8 kW at 02:30.
```

### Example — `hot_and_away` situation (formerly "Smart Irrigation Scheduler")

**Goal:** when it's hot outside and nobody is home, run something (e.g.
irrigation) for a few minutes without scheduling anything manually.

```json
{
  "situations": {
    "presence_entity": "binary_sensor.home_presence",
    "hot_and_away": {
      "enabled": true,
      "outside_temp_entity": "sensor.outdoor_temperature",
      "hot_threshold_c": 32,
      "valve_entity": "switch.lawn_irrigation",
      "run_minutes": 5,
      "skip_if_rain": true
    }
  }
}
```

**What happens:** every time HIRIS's periodic home snapshot runs (every
`sentinel_ronda_min` minutes), if the outdoor temperature is above 32°C,
nobody is home, and no rain is forecast, it suggests turning on
`switch.lawn_irrigation` for 5 minutes.

**Note:** this is not a multi-zone scheduler — it evaluates a single
threshold/relay with one decision, not a per-zone plan with durations
computed from rainfall/soil-moisture/orientation for each bed. That level of
custom reasoning needs a real read of forecast/history data, which is what a
**Chatbot**'s tool access is for (see below), not a built-in situation.

---

## Agentbot — custom (user-defined) rules

Beyond the built-ins, `#/agentbots/new` (or the goal-first flow at `#/nuovo`)
lets you author your own Agentbot: a **trigger** (event on an entity, or a
schedule — cron or interval), a **declared action** (`notify`, or a
concrete `service` call with `domain`/`service`/`entity_id`), an optional
**AI reasoning step**, and a severity.

The reasoning step, when enabled, runs **without any tool access** and can
only produce a verdict/severity/message — it can never invent or change the
action. The action that actually fires is always the one declared in the
Agentbot's own configuration; if the model's own JSON output includes an
`action`, it's discarded. A `notify`-type Agentbot can therefore never
execute anything on your home, reasoning-enabled or not.

### Example — custom door alert with a phrased message

**Goal:** get a naturally-worded alert (not a flat template) when the front
door stays open too long — same trigger as the built-in `opening` detector,
but as a standalone Agentbot with its own reasoning.

```json
{
  "name": "Front door check",
  "trigger": {
    "type": "event",
    "entity_id": "binary_sensor.front_door",
    "operator": "==",
    "threshold": "on",
    "duration_min": 10
  },
  "action": { "type": "notify" },
  "severity": "warn",
  "reasoning": { "enabled": true, "model": "auto" }
}
```

### Example — turn something off on a fixed schedule

**Goal:** turn the garden lights off every night at 23:30, no AI reasoning
needed.

```json
{
  "name": "Garden lights off",
  "trigger": { "type": "schedule", "cron": "30 23 * * *" },
  "action": {
    "type": "service",
    "domain": "light",
    "service": "turn_off",
    "entity_id": "light.garden"
  },
  "reasoning": { "enabled": false },
  "severity": "info"
}
```

---

## What's still not achievable as an autonomous Agentbot

An Agentbot's trigger reads **one** entity (plus, for a schedule trigger, one
optional secondary condition), and its optional reasoning step has **no tool
access** — it only ever sees the evidence HIRIS hands it, never a live
lookup of the weather, your calendar, or a second/third sensor. That rules
out, as an autonomous rule:

- A morning briefing that pulls yesterday's energy use, today's forecast,
  and calendar events into one message.
- Pre-heating decided dynamically against tomorrow's forecast.
- A combined nightly check across several door/window/presence sensors in a
  single evaluation.
- Anything that needs to reason over multiple live data sources at once.

You can still get the same result **on demand**, by asking a Chatbot in chat
(see below) — or by proposing it to yourself: the **Brain** watches for
patterns like these and may propose a matching Agentbot or HA automation for
you to approve, but the AI never runs free-form multi-source reasoning on a
recurring, unattended basis.

---

## Chatbot — chat agents

A Chatbot is defined by:
- **Prompt** — `system_prompt` + `strategic_context` (home/family context).
- **Tool scope** — `allowed_tools`.
- **Entity/service scope** — `allowed_entities`, `allowed_services`, `allowed_endpoints`.
- **Memory scope** — `knowledge_access` (sensitive data, which categories).
- **Conversation policy** — `max_chat_turns`, `require_confirmation`, `response_mode`.
- **Model override** — `model`, `max_tokens`, `thinking_budget`.

A Chatbot has no `trigger`, no scheduling, no autonomous execution — that's
what an Agentbot is for. Cost is tracked (`budget_eur` per Chatbot) but with
no per-Chatbot cap and no auto-disable.

### Example — Guest Assistant

**Goal:** a restricted Chatbot that guests can use to control lights and
temperature, without accessing sensitive data.

```json
{
  "name": "Guest Assistant",
  "system_prompt": "You are a helpful home assistant for guests. You can control lights and room temperature. Always be polite and confirm before making changes. Do not discuss energy costs, family schedules, or security information. If asked about something outside lights and temperature, politely decline.",
  "strategic_context": "Guest bedroom: light.guest_room, climate.guest_room. Living room: light.living_room, climate.living_room.",
  "allowed_tools": ["get_entity_states", "call_ha_service"],
  "allowed_entities": ["light.guest_room", "light.living_room", "climate.guest_room", "climate.living_room"],
  "allowed_services": ["light.*", "climate.set_temperature"],
  "restrict_to_home": true,
  "require_confirmation": true,
  "model": "auto"
}
```

**Example conversation:**
```
Guest: "Can you turn on the bedroom light and set it to 40%?"
HIRIS: "I'll turn on the guest bedroom light at 40% brightness. Shall I proceed?"
Guest: "Yes"
HIRIS: "Done — guest bedroom light is on at 40%."

Guest: "What's the electricity bill this month?"
HIRIS: "I'm set up to help with lights and temperature only. For other questions, ask the homeowner."
```

### Example — Multi-room Climate from a Single Message

**Goal:** use a Chatbot to control multiple rooms with one natural language
command.

```
You: "It's getting cold, set all the thermostats to 21 degrees"
HIRIS: [calls get_entities_by_domain("climate")]
HIRIS: "I found 4 thermostats: living room (currently 19°C), kitchen (20°C),
        master bedroom (18°C), guest room (17°C). Setting all to 21°C..."
        [calls call_ha_service for each thermostat]
HIRIS: "Done — all 4 thermostats set to 21°C. The master bedroom and guest room
        will take the longest to heat (currently furthest from target)."

You: "Actually leave the guest room at 18, it's empty"
HIRIS: [calls call_ha_service for climate.guest_room with temperature: 18]
HIRIS: "Guest room thermostat updated to 18°C. The other three remain at 21°C."
```

### Example — asking for a summary on demand (formerly "Morning Briefing")

**Goal:** get the same kind of summary an Agentbot can't produce on its own
(see above), by asking a Chatbot explicitly.

```
You:   "Give me yesterday's energy summary and today's weather"
HIRIS: [calls get_energy_history(days=1), get_weather_forecast(hours=12)]
HIRIS: "Yesterday: 18.2 kWh consumed, 12.4 kWh produced (solar covered 68%).
        Today: partly cloudy, 14→22°C."
```

Unlike a scheduled Agentbot, this request has to be made when you want it —
it doesn't run on its own at a fixed time. If you want it every morning, ask
the Brain: it may propose turning this into a recurring Agentbot once it
notices the pattern, within what an Agentbot can actually evaluate (a
schedule trigger, a declared notify action, no live multi-source lookup).

---

## Tips for configuring Agentbot and Chatbot

**Proactive behavior is tuned or authored, not prompted:** built-in
detectors/situations aren't programmed by writing a prompt — they're
enabled and tuned (entities, thresholds) from the `#/agentbots` page. A
custom Agentbot's *action* is always declared explicitly in its config; its
optional reasoning step only ever judges verdict/severity/message.

**Not sure whether you need a Chatbot or an Agentbot?** Start at `#/nuovo`
and describe your goal in plain language — HIRIS suggests the right type
deterministically (no LLM call involved), and you can always override it.

**Be explicit in a Chatbot's prompt:** instead of "tell me if something is
wrong", write "tell me if consumption exceeds 3kW".

**Give context about your home:** include entity IDs, typical values, family
schedule in `strategic_context`. Claude uses this to calibrate its replies.

**Use `require_confirmation` for irreversible actions:** any Chatbot that
controls heating, appliances, or security should have this enabled. It is an
instruction to the model, not a hard block: it does not replace the semaphore,
which is the safeguard that holds on its own for `call_ha_service`,
`trigger_automation`, `toggle_automation` and `set_input_helper`. One
exception, `create_ha_config`: the semaphore does not cover it, so there this
confirmation is the only step before the effect. Set both.

**Keep scope tight:** `allowed_tools`/`allowed_entities`/`allowed_services` as
narrow as possible for each Chatbot — especially for assistants shared with
guests.
