# HIRIS

**Home Intelligent Reasoning & Integration System**

> ⚠️ **Experimental** — HIRIS is under active development. APIs and configuration options may change between releases. Not recommended for production smart home setups yet.

A standalone Home Assistant Add-on that provides an AI-powered agent platform for smart home management. Combines Claude AI reasoning with HA automation flows.

## Features (Phase 1 roadmap)

- **Chat NL interface** — ask Claude questions about your home in natural language
- **Proactive monitors** — Claude detects anomalies (energy, presence) and notifies
- **Flow engine** — schedule-based and event-driven automations without AI cost
- **Agent designer** — step-based editor to build custom agents

## Installation via HACS (Custom Repository)

1. Open HACS in your Home Assistant dashboard
2. Click the three-dot menu → **Custom repositories**
3. Add `https://github.com/paolobets/hiris` with category **Add-ons**
4. Go to **Add-ons** → search for **HIRIS** → Install
5. Configure your Anthropic Claude API key in the add-on settings

## Manual Installation

Add this repository to your HA Supervisor add-on store:

1. **Settings** → **Add-ons** → **Add-on Store** → three-dot menu → **Repositories**
2. Add: `https://github.com/paolobets/hiris`
3. Find **HIRIS** in the store and install

## Configuration

| Option | Type | Description |
|---|---|---|
| `claude_api_key` | `password` | Anthropic Claude API key |
| `log_level` | `list` | Logging verbosity: `debug`, `info`, `warning`, `error` |

## Versioning

HIRIS uses semantic versioning. The project will remain at `0.x.x` (experimental) until Phase 1 is fully implemented and tested. Version `1.0.0` marks the first stable release.

## Status

**v0.0.1 (Phase 0)** — scaffold only. Server responds on `/` (placeholder UI) and `/api/health`.

## License

MIT
