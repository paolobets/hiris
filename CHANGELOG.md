# HIRIS — Changelog

## [0.0.1] — 2026-04-18

### Added
- Phase 0 scaffold: HA add-on structure with `config.yaml` (ingress, stage: experimental)
- `Dockerfile` based on Python 3.11 HA base image
- `build.yaml`: HA Supervisor base-image declarations for aarch64 and amd64
- `run.sh` entrypoint using bashio for configuration reading
- `app/main.py`: aiohttp server on port 8099
- `app/routes.py`: `GET /` placeholder UI, `GET /api/health` → `{"status": "ok", "version": "0.0.1"}`
- `app/config.py`: configuration reader from environment variables
- `app/ha_client.py`: `HAClient` stub with `get_states`, `call_service`, `get_history`
- `hacs.json`: HACS custom repository metadata
- `LICENSE`: MIT licence
