# HIRIS — Changelog

## [0.1.0] — 2026-04-18

### Added
- Phase 0 scaffold: HA add-on structure with `config.yaml` (ingress, no external ports)
- `Dockerfile` based on Python 3.11 HA base image
- `run.sh` entrypoint using bashio for configuration reading
- `app/main.py`: aiohttp server on port 8099
- `app/routes.py`: `GET /` placeholder UI, `GET /api/health` → `{"status": "ok"}`
- `app/config.py`: configuration reader from environment variables
- `app/ha_client.py`: `HAClient` stub with `get_states`, `call_service`, `get_history`

---
