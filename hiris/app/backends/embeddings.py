from __future__ import annotations
import logging
import math
import struct
from typing import Protocol, runtime_checkable

import aiohttp

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    @property
    def dimensions(self) -> int: ...
    @property
    def provider_name(self) -> str: ...


class NullEmbedder:
    """Fallback when no embedding provider is configured. Returns empty vectors."""

    async def embed(self, text: str) -> list[float]:
        return []

    @property
    def dimensions(self) -> int:
        return 0

    @property
    def provider_name(self) -> str:
        return "none"


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._api_key = api_key
        self._model = model
        self._dims = 1536  # text-embedding-3-small default

    def _call_sync(self, text: str) -> list[float]:
        import httpx
        resp = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self._model, "input": text},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    async def embed(self, text: str) -> list[float]:
        import asyncio
        return await asyncio.get_running_loop().run_in_executor(None, self._call_sync, text)

    @property
    def dimensions(self) -> int:
        return self._dims

    @property
    def provider_name(self) -> str:
        return f"openai/{self._model}"


class Model2VecEmbedder:
    """Local embeddings via model2vec — pure Python, Alpine/musl compatible.

    All dependencies (numpy, tokenizers, safetensors) ship musllinux_1_2 wheels,
    making this the only fully local option that works on HA add-ons (Alpine 3.21+).
    Models are downloaded from HuggingFace Hub on first use and cached in HF_HOME.
    """

    _DEFAULT_MODEL = "minishlab/potion-base-8M"

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model_name = model
        self._model = None  # lazy — downloaded on first embed()
        self._dims: int = 0

    def _get_model(self):
        if self._model is None:
            from model2vec import StaticModel  # type: ignore[import-untyped]
            self._model = StaticModel.from_pretrained(self._model_name)
        return self._model

    def _embed_sync(self, text: str) -> list[float]:
        return self._get_model().encode([text])[0].tolist()

    async def embed(self, text: str) -> list[float]:
        import asyncio
        vec = await asyncio.get_running_loop().run_in_executor(None, self._embed_sync, text)
        if vec and self._dims == 0:
            self._dims = len(vec)
        return vec

    @property
    def dimensions(self) -> int:
        return self._dims

    @property
    def provider_name(self) -> str:
        return f"model2vec/{self._model_name}"


class FastEmbedEmbedder:
    """Local embeddings via fastembed (ONNX, no server required).

    Model is downloaded on first use and cached in cache_dir.
    """

    _DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    _CACHE_DIR = "/config/hiris/models"

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model_name = model
        self._model = None  # lazy — downloaded on first embed()
        self._dims: int = 0

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding  # type: ignore[import-untyped]
            self._model = TextEmbedding(model_name=self._model_name, cache_dir=self._CACHE_DIR)
        return self._model

    def _embed_sync(self, text: str) -> list[float]:
        return list(self._get_model().embed([text]))[0].tolist()

    async def embed(self, text: str) -> list[float]:
        import asyncio
        vec = await asyncio.get_running_loop().run_in_executor(None, self._embed_sync, text)
        if vec and self._dims == 0:
            self._dims = len(vec)
        return vec

    @property
    def dimensions(self) -> int:
        return self._dims

    @property
    def provider_name(self) -> str:
        return f"fastembed/{self._model_name}"


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str = "nomic-embed-text") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dims: int = 0

    async def embed(self, text: str) -> list[float]:
        url = f"{self._base_url}/api/embeddings"
        timeout = aiohttp.ClientTimeout(total=30, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json={"model": self._model, "prompt": text}) as resp:
                resp.raise_for_status()
                data = await resp.json()
                vec: list[float] = data.get("embedding", [])
                if vec and self._dims == 0:
                    self._dims = len(vec)
                return vec

    @property
    def dimensions(self) -> int:
        return self._dims

    @property
    def provider_name(self) -> str:
        return f"ollama/{self._model}"


def build_embedding_provider(
    provider: str,
    model: str,
    openai_api_key: str = "",
    local_model_url: str = "",
) -> EmbeddingProvider:
    if provider == "openai":
        if not openai_api_key:
            logger.warning("memory_embedding_provider=openai but openai_api_key empty — using NullEmbedder")
            return NullEmbedder()
        return OpenAIEmbedder(api_key=openai_api_key, model=model or "text-embedding-3-small")
    if provider == "ollama":
        if not local_model_url:
            logger.warning("memory_embedding_provider=ollama but local_model_url empty — using NullEmbedder")
            return NullEmbedder()
        return OllamaEmbedder(base_url=local_model_url, model=model or "nomic-embed-text")
    if provider == "model2vec":
        return Model2VecEmbedder(model=model or Model2VecEmbedder._DEFAULT_MODEL)
    if provider == "fastembed":
        try:
            import fastembed  # noqa: F401 — check availability at startup, not on first embed
        except ImportError:
            logger.warning(
                "fastembed is not installed on this platform (Alpine/musl lacks onnxruntime wheels) "
                "— falling back to NullEmbedder. Use 'openai' or 'ollama' as embedding_provider instead."
            )
            return NullEmbedder()
        return FastEmbedEmbedder(model=model or FastEmbedEmbedder._DEFAULT_MODEL)
    if provider:
        logger.warning("Unknown memory_embedding_provider %r — using NullEmbedder", provider)
    return NullEmbedder()


# ── Vector serialisation helpers (shared with memory_store) ─────────────────

def vec_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def blob_to_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
