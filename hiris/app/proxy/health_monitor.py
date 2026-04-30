from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


class HealthMonitor:
    """Mantiene uno snapshot aggregato dello stato di salute di HA.

    Aggiornamento ibrido:
    - WebSocket state_changed → unavailable entities in real-time
    - APScheduler ogni 30 min → full refresh di tutte le sezioni
    - Persistenza JSON su disco → sopravvive ai restart
    """

    def __init__(self, ha_client: Any, data_path: str, scheduler: Any) -> None:
        self._ha = ha_client
        self._data_path = data_path
        self._scheduler = scheduler
        self._snapshot_data: dict = {
            "last_updated": None,
            "unavailable_entities": [],
            "integration_errors": [],
            "error_log_summary": {"errors": 0, "warnings": 0, "top_errors": []},
            "updates_available": [],
            "system_info": {},
        }
        os.makedirs(os.path.dirname(os.path.abspath(self._data_path)), exist_ok=True)
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._data_path):
            try:
                with open(self._data_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._snapshot_data.update(data)
                logger.debug("HealthMonitor: loaded snapshot from %s", self._data_path)
            except Exception as exc:
                logger.warning("HealthMonitor: failed to load snapshot: %s", exc)

    async def _save(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._save_sync)
        except RuntimeError:
            # No running loop (e.g. called from sync context) — save inline
            self._save_sync()

    def _save_sync(self) -> None:
        try:
            with open(self._data_path, "w", encoding="utf-8") as f:
                json.dump(self._snapshot_data, f, ensure_ascii=False)
        except Exception as exc:
            logger.warning("HealthMonitor: failed to save snapshot: %s", exc)

    async def start(self) -> None:
        """Avvia il monitor: register WS hook, schedule polling, initial refresh."""
        self._ha.add_state_listener(self.on_state_changed)
        self._scheduler.add_job(
            self.refresh,
            "interval",
            minutes=30,
            id="health_monitor_poll",
            replace_existing=True,
        )
        await self.refresh()

    async def refresh(self) -> None:
        """Full refresh di tutte le sezioni dalla HA API."""
        updated: dict = {"last_updated": datetime.now(timezone.utc).strftime(_TS_FMT)}

        try:
            updated["error_log_summary"] = await self._ha.get_error_log()
        except Exception as exc:
            logger.debug("HealthMonitor: get_error_log skipped (%s)", exc)

        try:
            updated["integration_errors"] = await self._ha.get_config_entries()
        except Exception as exc:
            logger.debug("HealthMonitor: get_config_entries skipped (%s)", exc)

        try:
            updated["system_info"] = await self._ha.get_system_info()
        except Exception as exc:
            logger.debug("HealthMonitor: get_system_info skipped (%s)", exc)

        try:
            updated["updates_available"] = await self._ha.get_updates()
        except Exception as exc:
            logger.debug("HealthMonitor: get_updates skipped (%s)", exc)

        self._snapshot_data.update(updated)
        await self._save()
        logger.debug("HealthMonitor: snapshot refreshed")

    def on_state_changed(self, event_data: dict) -> None:
        """Callback chiamato da ha_client._ws_loop per ogni state_changed."""
        entity_id = event_data.get("entity_id", "")
        new_state = (event_data.get("new_state") or {}).get("state", "")
        unavailable = self._snapshot_data["unavailable_entities"]

        if new_state in ("unavailable", "unknown"):
            if not any(e["entity_id"] == entity_id for e in unavailable):
                domain = entity_id.split(".")[0] if "." in entity_id else ""
                unavailable.append({
                    "entity_id": entity_id,
                    "domain": domain,
                    "since": datetime.now(timezone.utc).strftime(_TS_FMT),
                })
                logger.debug("HealthMonitor: %s → unavailable", entity_id)
        else:
            before = len(unavailable)
            self._snapshot_data["unavailable_entities"] = [
                e for e in unavailable if e["entity_id"] != entity_id
            ]
            if len(self._snapshot_data["unavailable_entities"]) < before:
                logger.debug("HealthMonitor: %s → recovered", entity_id)

        # Persist state changes (fire-and-forget non-blocking save)
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._save_sync)
        except RuntimeError:
            self._save_sync()

    def get_snapshot(self, sections: list[str]) -> dict:
        """Ritorna snapshot filtrato per sezioni richieste."""
        want_all = "all" in sections
        result: dict = {}
        if want_all or "unavailable" in sections:
            result["unavailable"] = self._snapshot_data["unavailable_entities"]
        if want_all or "integrations" in sections:
            result["integrations"] = self._snapshot_data["integration_errors"]
        if want_all or "logs" in sections:
            result["logs"] = self._snapshot_data["error_log_summary"]
        if want_all or "updates" in sections:
            result["updates"] = self._snapshot_data["updates_available"]
        if want_all or "system" in sections:
            result["system"] = self._snapshot_data["system_info"]
        result["last_updated"] = self._snapshot_data.get("last_updated")
        return result
