from __future__ import annotations
import logging, time
from datetime import datetime
from typing import Awaitable, Callable
from .situations import SITUATIONS
from .signals import WakeEvent
from .wake import maybe_wake

log = logging.getLogger(__name__)

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

class SituationEvaluator:
    def __init__(self, store, get_config: Callable[[], dict], *, build_snapshot,
                 on_situation: Callable[..., Awaitable], holistic_reason: Callable[..., Awaitable],
                 clock: Callable[[], float] = time.time, today: Callable[[], str] = _today,
                 cooldown_sec: int = 1800, daily_cap: int = 20) -> None:
        self._store = store
        self._get_config = get_config
        self._build_snapshot = build_snapshot
        self._on_situation = on_situation
        self._holistic_reason = holistic_reason
        self._clock = clock
        self._today = today
        self._cooldown = cooldown_sec
        self._cap = daily_cap

    async def run_evaluation(self) -> None:
        try:
            cfg = (self._get_config() or {}).get("situations", {})
            snap = await self._build_snapshot()
            for kind, fn in SITUATIONS.items():
                scfg = cfg.get(kind) or {}
                if not scfg.get("enabled"):
                    continue
                merged = {**scfg, "presence_entity": cfg.get("presence_entity")}
                sig = fn(snap, merged)
                if sig is None:
                    continue
                wake = WakeEvent(signal_kind=sig.kind, entity_id=sig.kind,
                                 severity_hint=sig.severity, evidence=sig.evidence, ts=self._clock())
                suggested = sig.suggested_action
                await maybe_wake(self._store, f"situation:{sig.kind}", wake,
                                 on_wake=lambda w, s=suggested: self._on_situation(w, s),
                                 clock=self._clock, today=self._today,
                                 cooldown_sec=self._cooldown, daily_cap=self._cap, cap_scope="situations")
            hol = cfg.get("holistic") or {}
            if hol.get("enabled"):
                async def _run_holistic(_w):
                    await self._holistic_reason(snap)
                await maybe_wake(self._store, "holistic", None, on_wake=_run_holistic,
                                 clock=self._clock, today=self._today, cooldown_sec=0,
                                 daily_cap=int(hol.get("per_day", 1)), cap_scope="holistic")
        except Exception:
            log.exception("situation evaluation failed")
