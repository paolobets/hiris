from __future__ import annotations
import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens on spaces, underscores, dots, brackets, hyphens."""
    return [t for t in re.split(r"[\s_.\-\[\]]+", text.lower()) if t]


def _entity_text(entity: dict) -> str:
    eid = entity["id"]
    name = (entity.get("name") or "").strip()
    domain, slug = eid.split(".", 1)
    slug_clean = slug.replace("_", " ")
    if name:
        return f"{name} [{domain} {slug_clean}]"
    return f"{domain} {slug_clean}"


def _score(query_tokens: list[str], candidate_tokens: list[str]) -> float:
    """Score a candidate against a query using token overlap."""
    if not query_tokens or not candidate_tokens:
        return 0.0
    candidate_set = set(candidate_tokens)
    hits = sum(1 for t in query_tokens if t in candidate_set)
    if hits == 0:
        return 0.0
    recall = hits / len(query_tokens)
    # Bonus when every query token matches
    bonus = 0.5 if hits == len(query_tokens) else 0.0
    # Slight penalty for long candidates: prefer precise matches
    length_penalty = 1.0 / (1.0 + len(candidate_set) * 0.05)
    return (recall + bonus) * length_penalty


class EmbeddingIndex:
    """
    Lightweight keyword-based entity search index.

    Drop-in replacement for the previous fastembed/onnxruntime-based index.
    Uses pure-Python token overlap scoring — no external dependencies,
    works on Alpine/musllinux, instant startup, zero model downloads.
    """

    def __init__(self) -> None:
        self._entity_ids: list[str] = []
        self._tokens: list[list[str]] = []   # parallel to _entity_ids

    @property
    def ready(self) -> bool:
        return len(self._entity_ids) > 0

    async def build(self, entities: list[dict]) -> None:
        if not entities:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._build_sync, entities)

    def _build_sync(self, entities: list[dict]) -> None:
        self._entity_ids = [e["id"] for e in entities]
        self._tokens = [_tokenize(_entity_text(e)) for e in entities]
        logger.info("EmbeddingIndex built: %d entities indexed", len(self._entity_ids))

    def search(self, query: str, top_k: int = 30,
               domain_filter: Optional[str] = None) -> list[str]:
        if not self._entity_ids:
            return []
        query_tokens = _tokenize(query)
        if not query_tokens:
            if domain_filter:
                filtered = [e for e in self._entity_ids if e.startswith(domain_filter + ".")]
                return filtered[:top_k]
            return self._entity_ids[:top_k]

        scored: list[tuple[float, str]] = []
        for i, eid in enumerate(self._entity_ids):
            if domain_filter and not eid.startswith(domain_filter + "."):
                continue
            sc = _score(query_tokens, self._tokens[i])
            if sc > 0:
                scored.append((sc, eid))

        scored.sort(key=lambda x: -x[0])
        return [eid for _, eid in scored[:top_k]]

    def rebuild_entity(self, entity_id: str, friendly_name: str) -> None:
        if entity_id not in self._entity_ids:
            return
        i = self._entity_ids.index(entity_id)
        entity = {"id": entity_id, "name": friendly_name, "state": "", "unit": ""}
        self._tokens[i] = _tokenize(_entity_text(entity))
