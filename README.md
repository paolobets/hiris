# HIRIS

**Home Intelligent Reasoning & Integration System**

A standalone Home Assistant Add-on that provides an AI-powered agent platform for smart home management. Combines Claude AI reasoning with HA automation flows.

## Features (Phase 1 roadmap)

- **Chat NL interface** — ask Claude questions about your home in natural language
- **Proactive monitors** — Claude detects anomalies (energy, presence) and notifies
- **Flow engine** — schedule-based and event-driven automations without AI cost
- **Agent designer** — step-based editor to build custom agents

## Installation

Install via the Retro Panel add-on repository. The UI is accessible through HA Supervisor Ingress (no external ports required).

## Configuration

| Option | Type | Description |
|---|---|---|
| `claude_api_key` | `password` | Anthropic Claude API key |
| `log_level` | `list` | Logging verbosity: `debug`, `info`, `warning`, `error` |

## Status

**Phase 0** — scaffold only. Server responds on `/` (placeholder UI) and `/api/health`.
