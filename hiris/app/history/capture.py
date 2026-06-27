from __future__ import annotations

import logging
from typing import Any

from ..api.handlers_history_policy import should_capture

logger = logging.getLogger(__name__)


class HistoryCapture:
    """Registered as a HA state_changed listener. Filters by policy and appends
    matching state changes to the HistoryStore. Never raises (capture must not
    crash the WS loop)."""

    def __init__(self, store: Any, policy: dict) -> None:
        self._store = store
        self._policy = policy or {}

    def set_policy(self, policy: dict) -> None:
        self._policy = policy or {}

    def on_state_changed(self, data: dict) -> None:
        try:
            entity_id = (data or {}).get("entity_id")
            new_state = (data or {}).get("new_state")
            if not entity_id or not isinstance(new_state, dict):
                return
            if not should_capture(entity_id, self._policy):
                return
            state = new_state.get("state", "")
            ts = new_state.get("last_changed") or new_state.get("last_updated") or ""
            self._store.append(entity_id, ts, state)
        except Exception as exc:
            logger.debug("history capture skipped an event: %s", exc)
