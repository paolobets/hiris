# HIRIS — Use Cases & Examples

> Version: 0.33.0 · Updated: 2026-07-24

As of this version, HIRIS reasons about your home in exactly two ways:

- **Sentinella** — the proactive layer. A fixed set of built-in **lenti**
  (detectors/situations), each independently enabled and tuned (entity
  selector + thresholds) from the Sentinella config page. There are no more
  autonomous agents with custom prompts, rules, and states: when a lens
  detects something, a single-shot LLM reasoner evaluates the signal and —
  filtered by the safety semaforo — may notify and/or suggest one low-risk
  action.
- **Personas** — chat. A Persona is a configuration (prompt, tool/entity/
  service scope, memory scope, conversation policy) used on demand by the
  user; it has no scheduling of its own.

**User-defined lenti** (custom triggers/prompts, to cover scenarios beyond the
built-ins) are planned for a later version — not this one.

This document collects realistic examples for both levels.

---

## Sentinella — built-in lenti

| Lens | What it detects | Tunable parameters |
|---|---|---|
| `opening` | Door/window left open past a threshold | entities, minutes |
| `fridge_temp` | Fridge/freezer temperature out of range for too long | entities, max °C, duration (min) |
| `power` | Instantaneous consumption above a threshold | entities, max watts |
| `battery` | A sensor/device battery below a threshold | entities, min % |
| `hot_and_away` | It's hot outside and nobody is home | outdoor temp sensor, threshold °C, valve/relay entity, run minutes, skip if rain forecast |
| `evening_arrival` | Evening arrival (presence flips to `on` in the evening) | presence entity, scene/target entity, sun entity, hour after which it's "evening" |

Every lens follows the same pattern: **detector/situation → signal →
reasoner (Claude Haiku by default) → semaforo → notification and/or action**.
There is no system prompt to write: the Sentinella reasoner has one fixed
prompt shared by all lenti, and always replies with the same internal JSON
schema (`verdict`, `severity`, `message`, `action`) — not the old
`VALUTAZIONE:`/`AZIONI:` syntax.

### Example — `opening` lens (formerly "Door Left Open")

**Goal:** be alerted if the front door stays open too long.

**Configuration (Sentinella page):**
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
threshold, the Sentinella wakes the reasoner, which evaluates the context
and — if it judges it worth flagging — notifies.

```
🚪 The front door has been open for 12 minutes.
```

### Example — `power` lens (formerly "Energy Anomaly Detection")

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

**What happens:** when `sensor.grid_power` exceeds 3000 W, the Sentinella
evaluates the signal and notifies if it judges it an anomaly:
```
⚡ Unusual consumption: 3.8 kW at 02:30.
```

### Example — `hot_and_away` lens (formerly "Smart Irrigation Scheduler")

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

**What happens:** every time the Sentinella observes the periodic home
snapshot, if the outdoor temperature is above 32°C, nobody is home, and no
rain is forecast, it suggests turning on `switch.lawn_irrigation` for 5
minutes.

**Note — this is not the old multi-zone scheduler:** this lens evaluates a
single threshold/relay with one decision, not a per-zone plan with durations
computed from rainfall/soil-moisture/orientation for each bed. That level of
custom reasoning needs bespoke prompts and triggers — i.e. **user-defined
lenti**, not yet available in this version.

### What's no longer available as an autonomous agent

The old "monitor/reactive/preventive" agents with custom prompts, rules, and
states have been retired along with their execution machinery. Cases like
"automatic 7:00 AM morning briefing", "pre-heat based on the forecast",
"solar self-consumption optimizer", or a "combined nightly security check" no
longer have an autonomous equivalent — the proactive layer today covers only
the built-in lenti above. You can still get the same result **on demand**, by
asking a Persona in chat (see below). User-defined lenti, once they ship,
will close this gap for recurring scenarios.

---

## Personas — chat agents

A Persona is defined by:
- **Prompt** — `system_prompt` + `strategic_context` (home/family context).
- **Tool scope** — `allowed_tools`.
- **Entity/service scope** — `allowed_entities`, `allowed_services`, `allowed_endpoints`.
- **Memory scope** — `knowledge_access` (sensitive data, which categories).
- **Conversation policy** — `max_chat_turns`, `require_confirmation`, `response_mode`.
- **Model override** — `model`, `max_tokens`, `thinking_budget`.

There is no more `type`, `triggers`, `action_mode`, `rules`, `states`, or
`budget_eur_limit`: a Persona has no scheduling or autonomous execution, and
cost is tracked but with no per-persona cap (no auto-disable).

### Example — Guest Assistant

**Goal:** a restricted Persona that guests can use to control lights and
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

**Goal:** use a Persona to control multiple rooms with one natural language
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

**Goal:** get the same kind of summary that used to run on its own every
morning, now by asking a Persona explicitly.

```
You:   "Give me yesterday's energy summary and today's weather"
HIRIS: [calls get_energy_history(days=1), get_weather_forecast(hours=12)]
HIRIS: "Yesterday: 18.2 kWh consumed, 12.4 kWh produced (solar covered 68%).
        Today: partly cloudy, 14→22°C."
```

Unlike the old cron agent, this request has to be made when you want it — it
no longer runs on its own at a fixed time.

---

## Tips for configuring Sentinella and Personas

**Proactive behavior is tuned, not prompted:** Sentinella lenti aren't
programmed by writing a prompt — they're enabled and tuned (entities,
thresholds) from the Sentinella page. There's no `VALUTAZIONE:` to write and
no custom `rules`/`states` to define anymore.

**Be explicit in a Persona's prompt:** instead of "tell me if something is
wrong", write "tell me if consumption exceeds 3kW".

**Give context about your home:** include entity IDs, typical values, family
schedule in `strategic_context`. Claude uses this to calibrate its replies.

**Use `require_confirmation` for irreversible actions:** any Persona that
controls heating, appliances, or security should have this enabled.

**Keep scope tight:** `allowed_tools`/`allowed_entities`/`allowed_services` as
narrow as possible for each Persona — especially for assistants shared with
guests.
