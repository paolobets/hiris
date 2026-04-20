from __future__ import annotations
import asyncio
import logging
import numpy as np

logger = logging.getLogger(__name__)

_FASTEMBED_MODEL = "intfloat/multilingual-e5-small"
_FASTEMBED_CACHE_DIR = "/data/fastembed_cache"


def _entity_text(entity: dict) -> str:
    eid = entity["id"]
    name = (entity.get("name") or "").strip()
    domain, slug = eid.split(".", 1)
    slug_clean = slug.replace("_", " ")
    if name:
        return f"{name} [{domain} {slug_clean}]"
    return f"{domain} {slug_clean}"


class EmbeddingIndex:
    def __init__(self) -> None:
        self._model = None
        self._entity_ids: list[str] = []
        self._matrix: np.ndarray | None = None

    @property
    def ready(self) -> bool:
        return self._matrix is not None

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding  # type: ignore
            self._model = TextEmbedding(_FASTEMBED_MODEL, cache_dir=_FASTEMBED_CACHE_DIR)
        return self._model

    async def build(self, entities: list[dict]) -> None:
        if not entities:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._build_sync, entities)

    def _build_sync(self, entities: list[dict]) -> None:
        model = self._get_model()
        texts = [_entity_text(e) for e in entities]
        self._entity_ids = [e["id"] for e in entities]
        self._matrix = np.array(list(model.embed(texts)), dtype=np.float32)
        logger.info("EmbeddingIndex built: %d entities indexed", len(self._entity_ids))

    def search(self, query: str, top_k: int = 30,
               domain_filter: str | None = None) -> list[str]:
        if self._matrix is None or not self._entity_ids:
            return []
        model = self._get_model()
        q_vec = np.array(list(model.embed([query]))[0], dtype=np.float32)
        scores = self._matrix @ q_vec
        if domain_filter:
            for i, eid in enumerate(self._entity_ids):
                if not eid.startswith(domain_filter + "."):
                    scores[i] = -np.inf
        idx = np.argsort(scores)[::-1]
        # Filter out -inf scores
        valid_idx = [i for i in idx if not np.isinf(scores[i]) or scores[i] > -np.inf]
        n = min(top_k, len(valid_idx))
        return [self._entity_ids[i] for i in valid_idx[:n]]

    def rebuild_entity(self, entity_id: str, friendly_name: str) -> None:
        if self._model is None or entity_id not in self._entity_ids:
            return
        i = self._entity_ids.index(entity_id)
        domain, slug = entity_id.split(".", 1)
        text = f"{friendly_name} [{domain} {slug.replace('_', ' ')}]"
        self._matrix[i] = np.array(list(self._model.embed([text]))[0], dtype=np.float32)
