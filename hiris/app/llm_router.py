from __future__ import annotations
import json
import logging
import re
from typing import Any
from .backends.ollama import OllamaBackend

logger = logging.getLogger(__name__)

_CLASSIFY_SYSTEM = (
    "Sei un classificatore di entità Home Assistant. "
    "Rispondi SOLO con JSON valido, nessun testo aggiuntivo."
)

_CLASSIFY_ROLES = (
    "energy_meter, solar_production, grid_import, climate_sensor, "
    "presence, lighting, appliance, door_window, electrical, diagnostic, other"
)


class LLMRouter:
    """Wraps ClaudeRunner with the same public interface + classify_entities() routing."""

    def __init__(
        self,
        runner: Any,
        local_model_url: str = "",
        local_model_name: str = "",
    ) -> None:
        self._runner = runner
        self._local_model_url = local_model_url.strip()
        self._local_model_name = local_model_name.strip()

    async def chat(self, **kwargs) -> str:
        return await self._runner.chat(**kwargs)

    async def run_with_actions(self, **kwargs):
        return await self._runner.run_with_actions(**kwargs)

    @property
    def last_tool_calls(self) -> list:
        return getattr(self._runner, "last_tool_calls", [])

    @property
    def total_input_tokens(self) -> int:
        return getattr(self._runner, "total_input_tokens", 0)

    @property
    def total_output_tokens(self) -> int:
        return getattr(self._runner, "total_output_tokens", 0)

    @property
    def total_requests(self) -> int:
        return getattr(self._runner, "total_requests", 0)

    @property
    def total_cost_usd(self) -> float:
        return getattr(self._runner, "total_cost_usd", 0.0)

    @property
    def total_rate_limit_errors(self) -> int:
        return getattr(self._runner, "total_rate_limit_errors", 0)

    @property
    def usage_last_reset(self) -> str:
        return getattr(self._runner, "usage_last_reset", "")

    def get_agent_usage(self, agent_id: str) -> dict:
        return self._runner.get_agent_usage(agent_id)

    def reset_agent_usage(self, agent_id: str) -> None:
        self._runner.reset_agent_usage(agent_id)

    def reset_usage(self) -> None:
        self._runner.reset_usage()

    async def classify_entities(self, entities: list[dict]) -> dict[str, dict]:
        """Classify entities via LLM. Routes to Ollama if configured, else Claude.

        Returns {entity_id: {role, label, confidence}}.
        """
        if not entities:
            return {}

        batch_text = "\n".join(
            f"- {e['id']}: state={e.get('state', 'unknown')}, "
            f"name={e.get('name', '')}, unit={e.get('unit', '')}"
            for e in entities
        )
        user_msg = (
            f"Classifica queste entità HA. Restituisci JSON:\n"
            f'{{\"entity_id\": {{\"role\": \"...\", \"label\": \"...\", \"confidence\": 0.0}}}}\n\n'
            f"Ruoli validi: {_CLASSIFY_ROLES}\n\n"
            f"Entità:\n{batch_text}\n\n"
            f"Rispondi con SOLO il JSON."
        )
        messages = [{"role": "user", "content": user_msg}]

        if self._local_model_url and self._local_model_name:
            backend = OllamaBackend(url=self._local_model_url, model=self._local_model_name)
            raw = await backend.simple_chat(messages, system=_CLASSIFY_SYSTEM)
        else:
            raw = await self._runner.simple_chat(messages, system=_CLASSIFY_SYSTEM)

        return _parse_classify_response(raw)


_VALID_ROLES = frozenset([
    "energy_meter", "solar_production", "grid_import", "climate_sensor",
    "presence", "lighting", "appliance", "door_window", "electrical",
    "diagnostic", "other", "unknown",
])


def _parse_classify_response(raw: str) -> dict[str, dict]:
    raw = raw[:100_000]
    data: dict | None = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Scan right-to-left for a valid JSON object (avoids greedy regex matching multiple blobs)
        for m in reversed(list(re.finditer(r'\{', raw))):
            try:
                data = json.loads(raw[m.start():])
                break
            except json.JSONDecodeError:
                continue
    if not isinstance(data, dict):
        logger.warning("classify_entities: could not parse JSON from LLM response: %.200s", raw)
        return {}
    result: dict[str, dict] = {}
    for eid, meta in list(data.items())[:500]:
        if not isinstance(meta, dict):
            continue
        role = str(meta.get("role", "other"))
        if role not in _VALID_ROLES:
            role = "other"
        label = str(meta.get("label", ""))[:128] or eid.split(".")[-1]
        try:
            confidence = float(meta.get("confidence", 0.8))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.8
        result[eid] = {"role": role, "label": label, "confidence": confidence}
    return result
