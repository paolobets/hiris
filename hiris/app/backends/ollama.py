"""La guardia sull'indirizzo di Ollama (`LOCAL_MODEL_URL`).

Il modulo portava anche `OllamaBackend`, un backend di libreria che nessuno
costruiva piu' (voce M-03 del registro): e' uscito con la Tappa 0 dello sprint
«Una fonte sola di verita'». Resta la guardia, che tre punti del prodotto
chiamano: l'avvio, la pagina Modelli e il runner locale.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BLOCKED_HOSTS = frozenset({"169.254.169.254", "100.100.100.200", "metadata.google.internal"})
_DANGEROUS_PORTS = frozenset({22, 23, 25, 110, 143, 3306, 5432, 5672, 6379, 9200, 27017})


def _validate_ollama_url(url: str) -> None:
    """Raise ValueError if the URL is unsafe (non-http/https or points to a metadata endpoint)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"LOCAL_MODEL_URL must use http or https, got: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if host in _BLOCKED_HOSTS:
        raise ValueError(f"LOCAL_MODEL_URL points to a blocked host: {host!r}")
    port = parsed.port
    if port is not None and port in _DANGEROUS_PORTS:
        logger.warning("LOCAL_MODEL_URL uses a dangerous port: %d", port)
        raise ValueError(f"LOCAL_MODEL_URL uses a dangerous port: {port}")
