from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

SEVERITIES = ("info", "warn", "critico")

@dataclass
class Signal:
    kind: str
    entity_id: str
    severity: str
    evidence: dict
    ts: float

@dataclass
class WakeEvent:
    signal_kind: str
    entity_id: str
    severity_hint: str
    evidence: dict
    ts: float

@dataclass
class Decision:
    verdict: str            # "anomalia" | "falso_positivo"
    severity: str           # "info" | "warn" | "critico"
    message: str
    action: Optional[dict] = None   # {"domain","service","entity_id","data"} | None

def wake_from_signal(sig: Signal) -> WakeEvent:
    return WakeEvent(
        signal_kind=sig.kind, entity_id=sig.entity_id,
        severity_hint=sig.severity, evidence=dict(sig.evidence), ts=sig.ts,
    )
