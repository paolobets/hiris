from __future__ import annotations

import logging
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


#: Cosa si dice a chi ha scelto un provider locale e non ha la sua libreria.
#: **Dice perche' non c'e'** -- il percorso e' inerte -- e cosa funziona
#: davvero: un avviso che dice soltanto «non installata» manda a cercare.
_LIBRERIA_ASSENTE = (
    "il provider di embedding «%s» ha bisogno di una libreria che questo "
    "add-on non installa: il percorso degli embedding è INERTE (nessun codice "
    "di HIRIS chiama embed()), quindi la libreria non entra nell'immagine. "
    "Uso NullEmbedder, che è ciò che quel percorso faceva comunque. Se vuoi "
    "accendere i vettori davvero, «openai» e «ollama» funzionano senza "
    "installare niente; per questo servirebbe %s."
)


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
        return next(iter(self._get_model().embed([text]))).tolist()

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
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(url, json={"model": self._model, "prompt": text}) as resp,
        ):
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
            logger.warning(
                "memory_embedding_provider=openai but openai_api_key empty — using "
                "NullEmbedder"
            )
            return NullEmbedder()
        return OpenAIEmbedder(api_key=openai_api_key, model=model or "text-embedding-3-small")
    if provider == "ollama":
        if not local_model_url:
            logger.warning(
                "memory_embedding_provider=ollama but local_model_url empty — using "
                "NullEmbedder"
            )
            return NullEmbedder()
        return OllamaEmbedder(base_url=local_model_url, model=model or "nomic-embed-text")
    # I due provider LOCALI, e si difendono allo stesso modo (D-2, 22/09/2026).
    #
    # Nessuna delle due librerie e' installata nell'immagine: il percorso degli
    # embedding e' dichiarato inerte -- nessun codice di HIRIS chiama piu'
    # `embed()` -- e `model2vec` da solo si tirava dietro QUINDICI pacchetti su
    # quarantanove (`numpy`, `tokenizers`, `safetensors`, l'albero di
    # HuggingFace), cioe' quindici alberi da sorvegliare per le vulnerabilita'
    # in cambio di zero funzioni.
    #
    # Erano due casi diversi per caso -- `fastembed` si difendeva, `model2vec`
    # no, perche' l'uno era dichiarato e l'altro no. Adesso sono la stessa cosa:
    # chi aveva scelto uno dei due nelle opzioni e aggiorna l'add-on trova un
    # ripiego e una frase, **non un add-on che non parte**.
    if provider == "model2vec":
        try:
            import model2vec  # noqa: F401 — si guarda all'avvio, non al primo embed
        except ImportError:
            logger.warning(_LIBRERIA_ASSENTE, "model2vec", "pip install model2vec")
            return NullEmbedder()
        return Model2VecEmbedder(model=model or Model2VecEmbedder._DEFAULT_MODEL)
    if provider == "fastembed":
        try:
            import fastembed  # noqa: F401 — si guarda all'avvio, non al primo embed
        except ImportError:
            logger.warning(_LIBRERIA_ASSENTE, "fastembed",
                           "pip install fastembed (e su Alpine/musl non ci sono "
                           "wheel di onnxruntime)")
            return NullEmbedder()
        return FastEmbedEmbedder(model=model or FastEmbedEmbedder._DEFAULT_MODEL)
    if provider:
        logger.warning("Unknown memory_embedding_provider %r — using NullEmbedder", provider)
    return NullEmbedder()


# Fetta "esce il documentale": qui vivevano `vec_to_blob`, `blob_to_vec` e
# `cosine_similarity` -- la serializzazione dei vettori e il confronto per
# somiglianza. I loro unici chiamanti erano `brain/knowledge_store.py` e
# `brain/memory_migration.py`, usciti con l'archivio di conoscenza: senza di
# loro erano tre funzioni senza nessun chiamante, ne' di produzione ne' di
# test. Tornano, se e quando i vettori si accenderanno, sopra l'archivio che
# ci sara' allora -- non trascinando il formato blob di knowledge.db.
#
# I provider qui sopra restano, ma sono DICHIARATI INERTI: dopo questa fetta
# nessun percorso di HIRIS chiama piu' `embed()`. Le opzioni
# `memory.embedding_provider`/`memory.embedding_model` restano leggibili e
# visibili nella pagina Modelli, e il CHANGELOG dice che oggi non hanno
# effetto. La decisione "se e quando accendere i vettori" e' esplicitamente
# rimandata dal contratto (docs/design/2026-08-05-la-conoscenza-di-hiris.md,
# sezione 11), quindi non si anticipa qui ne' in un senso ne' nell'altro.
