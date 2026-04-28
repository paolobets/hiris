from __future__ import annotations
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_CLASSIFY_SYSTEM = (
    "Sei un classificatore di entità Home Assistant. "
    "Rispondi SOLO con JSON valido, nessun testo aggiuntivo."
)

_CLASSIFY_ROLES = (
    "energy_meter, solar_production, grid_import, climate_sensor, "
    "presence, lighting, appliance, door_window, electrical, diagnostic, other"
)


def _is_openai_model(model: str) -> bool:
    return bool(re.match(r"^(gpt-|o[1-9])", model))


_STRATEGY_ORDER = {
    # cost_first: prefer free local (Ollama) → cheap cloud → full cloud
    "cost_first":    ["ollama", "openai", "claude"],
    # quality_first: prefer most capable first
    "quality_first": ["claude", "openai", "ollama"],
    # balanced (default): same as quality_first
    "balanced":      ["claude", "openai", "ollama"],
}


class LLMRouter:
    """Routes LLM calls to the appropriate backend (Claude, OpenAI, Ollama).

    strategy controls the backend preference order when model="auto":
      - "balanced" / "quality_first": Claude → OpenAI → Ollama
      - "cost_first": Ollama → OpenAI → Claude
    Fallback: if the primary backend raises an exception and model="auto",
    the next backend in the strategy chain is tried automatically.
    """

    def __init__(
        self,
        claude: Any = None,
        openai: Any = None,
        ollama: Any = None,
        strategy: str = "balanced",
    ) -> None:
        self._claude = claude
        self._openai = openai
        self._ollama = ollama
        self._strategy = strategy if strategy in _STRATEGY_ORDER else "balanced"
        self._all = [r for r in [claude, openai, ollama] if r is not None]

    def _backend_map(self) -> dict[str, Any]:
        return {"claude": self._claude, "openai": self._openai, "ollama": self._ollama}

    def _ordered_backends(self) -> list[Any]:
        """Return available backends in strategy priority order."""
        order = _STRATEGY_ORDER[self._strategy]
        bmap = self._backend_map()
        return [bmap[name] for name in order if bmap[name] is not None]

    def _route(self, model: str) -> Any:
        if model == "auto":
            backends = self._ordered_backends()
            return backends[0] if backends else None
        if model.startswith("claude-"):
            return self._claude
        if _is_openai_model(model):
            return self._openai
        return self._ollama

    # ------------------------------------------------------------------
    # LLM interface (mirrors ClaudeRunner)
    # ------------------------------------------------------------------

    async def chat(self, **kwargs) -> str:
        model = kwargs.get("model", "auto")
        if model != "auto":
            runner = self._route(model)
            if runner is None:
                return "Nessun provider AI configurato per questo modello."
            return await runner.chat(**kwargs)
        # auto: try backends in strategy order with fallback
        for runner in self._ordered_backends():
            try:
                return await runner.chat(**kwargs)
            except Exception as exc:
                logger.warning("Backend %s failed, trying next: %s", type(runner).__name__, exc)
        return "Tutti i provider AI non disponibili. Riprova tra poco."

    async def chat_stream(self, **kwargs):
        runner = self._route(kwargs.get("model", "auto"))
        if runner is None:
            yield f'data: {json.dumps({"type": "error", "message": "Provider AI non configurato"})}\n\n'
            return
        async for chunk in runner.chat_stream(**kwargs):
            yield chunk

    async def run_with_actions(self, **kwargs):
        model = kwargs.get("model", "auto")
        if model != "auto":
            runner = self._route(model)
            if runner is None:
                return "", None, None
            return await runner.run_with_actions(**kwargs)
        for runner in self._ordered_backends():
            try:
                return await runner.run_with_actions(**kwargs)
            except Exception as exc:
                logger.warning("Backend %s failed, trying next: %s", type(runner).__name__, exc)
        return "", None, None

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        runner = self._claude or self._openai or self._ollama
        if runner is None:
            return ""
        return await runner.simple_chat(messages, system=system)

    # ------------------------------------------------------------------
    # Usage (aggregated across all runners)
    # ------------------------------------------------------------------

    @property
    def last_tool_calls(self) -> list:
        for r in reversed(self._all):
            tc = getattr(r, "last_tool_calls", None)
            if tc:
                return tc
        return []

    @property
    def total_input_tokens(self) -> int:
        return sum(getattr(r, "total_input_tokens", 0) for r in self._all)

    @property
    def total_output_tokens(self) -> int:
        return sum(getattr(r, "total_output_tokens", 0) for r in self._all)

    @property
    def total_requests(self) -> int:
        return sum(getattr(r, "total_requests", 0) for r in self._all)

    @property
    def total_cost_usd(self) -> float:
        return sum(getattr(r, "total_cost_usd", 0.0) for r in self._all)

    @property
    def total_rate_limit_errors(self) -> int:
        return sum(getattr(r, "total_rate_limit_errors", 0) for r in self._all)

    @property
    def usage_last_reset(self) -> str:
        resets = [getattr(r, "usage_last_reset", "") for r in self._all]
        return min((s for s in resets if s), default="")

    def get_agent_usage(self, agent_id: str) -> dict:
        result = {
            "input_tokens": 0, "output_tokens": 0,
            "requests": 0, "cost_usd": 0.0, "last_run": None,
            "tokens_today": 0, "tokens_today_date": "",
        }
        for r in self._all:
            u = r.get_agent_usage(agent_id)
            result["input_tokens"] += u.get("input_tokens", 0)
            result["output_tokens"] += u.get("output_tokens", 0)
            result["requests"] += u.get("requests", 0)
            result["cost_usd"] += u.get("cost_usd", 0.0)
            result["tokens_today"] += u.get("tokens_today", 0)
            run_at = u.get("last_run")
            if run_at and (not result["last_run"] or run_at > result["last_run"]):
                result["last_run"] = run_at
        return result

    def reset_agent_usage(self, agent_id: str) -> None:
        for r in self._all:
            r.reset_agent_usage(agent_id)

    def reset_usage(self) -> None:
        for r in self._all:
            r.reset_usage()

    # ------------------------------------------------------------------
    # Entity classification (prefers Ollama for cheap inference)
    # ------------------------------------------------------------------

    async def classify_entities(self, entities: list[dict]) -> dict[str, dict]:
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

        # Ollama is cheapest; fall back to primary runner
        runner = self._ollama or self._claude or self._openai
        if runner is None:
            return {}
        raw = await runner.simple_chat(messages, system=_CLASSIFY_SYSTEM)
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
