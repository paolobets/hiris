# HIRIS — Use Cases & Examples

> Version: 0.6.9 · Updated: 2026-04-28

This document contains real-world HIRIS configurations with full agent YAML, example conversations, and step-by-step setup for each scenario.

---

## 1. Morning Briefing

**Goal:** Every morning at 7:00 AM, receive a summary of yesterday's energy consumption, today's weather, and any anomalies detected overnight.

**Agent type:** Preventive (cron-scheduled)

**Configuration:**
```json
{
  "name": "Morning Briefing",
  "type": "preventive",
  "trigger": {
    "type": "preventive",
    "cron": "0 7 * * *"
  },
  "system_prompt": "You are a daily home briefing agent. Every morning, retrieve yesterday's energy data, today's weather forecast for the next 12 hours, and any unusual events from overnight (doors left open, unexpected consumption). Write a concise briefing in 3-4 lines, suitable for a push notification. End with one practical suggestion for the day.",
  "strategic_context": "Family home, 4 people, solar panels 6kWp, heat pump for heating and hot water.",
  "allowed_tools": ["get_energy_history", "get_weather_forecast", "get_home_status", "send_notification"],
  "model": "auto",
  "actions": [
    {
      "type": "notify",
      "channel": "ha_push",
      "message": "{{result}}"
    }
  ]
}
```

**Example output (notification):**
```
☀️ Good morning! Yesterday: 18.2 kWh consumed, 12.4 kWh produced (solar covered 68%).
Today: partly cloudy, 14→22°C. Solar forecast moderate from 10:00.
No anomalies overnight.
💡 Tip: run the dishwasher between 11:00 and 14:00 to maximize solar self-consumption.
```

---

## 2. Energy Anomaly Detection

**Goal:** Detect unusual consumption patterns and alert before the bill arrives.

**Agent type:** Monitor (periodic)

**Configuration:**
```json
{
  "name": "Energy Monitor",
  "type": "monitor",
  "trigger": {
    "type": "schedule",
    "interval_minutes": 20
  },
  "system_prompt": "You are an energy monitoring agent. Check the current home consumption. Compare it against the time of day and typical usage patterns (described in context). Flag ANOMALIA if: total consumption exceeds 3kW when no one should be cooking; washing machine or dishwasher running past midnight; any single appliance drawing more than expected. Respond with VALUTAZIONE: OK if nothing unusual, VALUTAZIONE: ANOMALIA if intervention is needed.",
  "strategic_context": "Normal night consumption (23:00-07:00): 200-400W (fridge + standby). Normal daytime: 400-1200W. Cooking peaks: 1500-3500W lasting 20-40 minutes.",
  "allowed_tools": ["get_home_status", "get_entities_by_domain", "get_energy_history"],
  "allowed_entities": ["sensor.*power*", "sensor.*energy*", "switch.*"],
  "model": "auto",
  "trigger_on": ["ANOMALIA"],
  "actions": [
    {
      "type": "notify",
      "channel": "ha_push",
      "message": "⚡ Energy anomaly detected: {{result}}"
    }
  ]
}
```

**Example alert:**
```
⚡ Energy anomaly: it's 02:30 and the house is drawing 1.8kW.
The washing machine (1.4kW) has been running for 2h 15min — this is unusual at this hour.
Current total: 1.8kW vs expected 350W.
```

---

## 3. Door Left Open

**Goal:** When the front door has been open for more than 5 minutes, check context and notify if needed.

**Agent type:** Reactive (state_changed)

**Configuration:**
```json
{
  "name": "Door Monitor",
  "type": "reactive",
  "trigger": {
    "type": "state_changed",
    "entity_id": "binary_sensor.front_door"
  },
  "system_prompt": "The front door state just changed. If it opened: check how long it has been open (use current time), check if anyone is home via presence sensors, check if it's an unusual hour (between 23:00 and 07:00 is unusual). Only notify if the door has been open more than 5 minutes AND either no one is detected inside OR it's nighttime. If the door just closed, no action needed.",
  "strategic_context": "Front door: binary_sensor.front_door. Presence sensors: binary_sensor.pir_hallway, binary_sensor.pir_living_room, binary_sensor.pir_kitchen.",
  "allowed_tools": ["get_entity_states", "send_notification"],
  "allowed_entities": ["binary_sensor.front_door", "binary_sensor.pir_*"],
  "require_confirmation": false,
  "model": "auto",
  "trigger_on": ["ANOMALIA"],
  "actions": [
    {
      "type": "notify",
      "channel": "ha_push",
      "message": "🚪 {{result}}"
    }
  ]
}
```

**Example notification:**
```
🚪 Front door has been open for 8 minutes.
No motion detected inside for the last 15 minutes.
Current time: 23:42. This is unusual — please check.
```

---

## 4. Pre-heat Before Arrival

**Goal:** Every afternoon, check the forecast and start heating in advance if it's going to be cold when you arrive home.

**Agent type:** Preventive (cron)

**Configuration:**
```json
{
  "name": "Pre-heat Optimizer",
  "type": "preventive",
  "trigger": {
    "type": "preventive",
    "cron": "30 16 * * 1-5"
  },
  "system_prompt": "It's 16:30 on a weekday. The family typically arrives home around 18:30. Check the weather forecast for 18:00-19:00. If the outdoor temperature will be below 10°C, and the living room thermostat is currently in 'away' or 'off' mode, turn on heating now so the house is warm on arrival. Set living room to 21°C. If already heating or temperature is mild (>15°C outside), take no action.",
  "strategic_context": "Living room thermostat: climate.living_room. Away mode setpoint: 17°C. Comfort setpoint: 21°C.",
  "allowed_tools": ["get_weather_forecast", "get_entity_states", "call_ha_service"],
  "allowed_entities": ["climate.living_room", "climate.*"],
  "allowed_services": ["climate.*"],
  "model": "auto"
}
```

**What happens:** at 16:30 HIRIS checks the 18:00 forecast. If it's 8°C, it calls `climate.set_temperature` and `climate.set_hvac_mode` automatically. No notification unless it takes action.

---

## 5. Night Security Check

**Goal:** Every night at 23:00, verify all doors and windows are closed and nothing unusual is happening.

**Agent type:** Preventive (cron)

**Configuration:**
```json
{
  "name": "Night Security",
  "type": "preventive",
  "trigger": {
    "type": "preventive",
    "cron": "0 23 * * *"
  },
  "system_prompt": "It's 23:00. Perform a nightly security check: 1) List all door and window sensors that are currently open. 2) Check if any external lights are still on. 3) Check if the alarm (if present) is armed. Write a brief security report. If everything is OK, say so in one line. If anything needs attention, list it clearly.",
  "strategic_context": "Door/window sensors: binary_sensor.front_door, binary_sensor.back_door, binary_sensor.kitchen_window, binary_sensor.bedroom_window. External lights: light.garden, light.garage.",
  "allowed_tools": ["get_entities_by_domain", "get_entity_states", "send_notification"],
  "allowed_entities": ["binary_sensor.*door*", "binary_sensor.*window*", "light.garden", "light.garage"],
  "model": "auto",
  "trigger_on": ["ANOMALIA", "ATTENZIONE"],
  "actions": [
    {
      "type": "notify",
      "channel": "ha_push",
      "message": "🔒 {{result}}"
    }
  ]
}
```

**Example notification when something is open:**
```
🔒 Night check — attention needed:
• Kitchen window: OPEN
• Garden light: ON (forgot to turn off)
Everything else secured. Alarm: armed.
```

---

## 6. Chat Agent for Guests

**Goal:** A restricted chat agent that guests can use to control lights and temperature, without accessing sensitive data.

**Agent type:** Chat

**Configuration:**
```json
{
  "name": "Guest Assistant",
  "type": "chat",
  "trigger": { "type": "manual" },
  "system_prompt": "You are a helpful home assistant for guests. You can control lights and room temperature. Always be polite and confirm before making changes. Do not discuss energy costs, family schedules, or security information. If asked about something outside lights and temperature, politely decline.",
  "strategic_context": "Guest bedroom: light.guest_room, climate.guest_room. Living room: light.living_room, climate.living_room.",
  "allowed_tools": ["get_entity_states", "call_ha_service"],
  "allowed_entities": ["light.guest_room", "light.living_room", "climate.guest_room", "climate.living_room"],
  "allowed_services": ["light.*", "climate.set_temperature"],
  "restrict_to_home": true,
  "require_confirmation": true,
  "budget_eur_limit": 1.00,
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

---

## 7. Solar Self-consumption Optimizer

**Goal:** When solar production is high, automatically run high-consumption appliances.

**Agent type:** Reactive (state_changed on solar sensor)

**Configuration:**
```json
{
  "name": "Solar Optimizer",
  "type": "reactive",
  "trigger": {
    "type": "state_changed",
    "entity_id": "sensor.solar_production"
  },
  "system_prompt": "The solar production has changed. Check current production (W) and current home consumption (W). Calculate net surplus (production - consumption). If surplus > 1500W for more than 10 minutes: check if the water heater (switch.water_heater) is off — if so, turn it on to use the free solar energy. If surplus drops below 500W: turn the water heater back off to avoid importing from the grid. Only act if the change in surplus is significant (>300W from last state).",
  "strategic_context": "Solar: sensor.solar_production. Grid import/export: sensor.grid_power (positive = importing, negative = exporting). Water heater: switch.water_heater (1800W when on).",
  "allowed_tools": ["get_entity_states", "call_ha_service"],
  "allowed_entities": ["sensor.solar_production", "sensor.grid_power", "switch.water_heater"],
  "allowed_services": ["switch.turn_on", "switch.turn_off"],
  "model": "auto"
}
```

---

## 8. Multi-room Climate from a Single Message

**Goal:** Use the chat agent to control multiple rooms with one natural language command.

**Example conversation:**
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

---

## Tips for writing effective system prompts

**Be explicit about conditions:** instead of "notify if something is wrong", write "notify if consumption exceeds 3kW between 23:00 and 07:00".

**Give context about your home:** include entity IDs, typical consumption values, family schedule. Claude uses this to calibrate its reasoning.

**Define the output format for monitors:** always end monitor prompts with the required `VALUTAZIONE: OK|ATTENZIONE|ANOMALIA` format — this is what drives action chaining.

**Use `require_confirmation` for irreversible actions:** any agent that controls heating, appliances, or security should have this enabled.

**Set a budget:** even a 5 EUR/month limit on each agent prevents runaway costs from bugs or unexpected behavior.
