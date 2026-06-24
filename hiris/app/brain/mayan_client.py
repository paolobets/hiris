# hiris/app/brain/mayan_client.py
from __future__ import annotations
import logging
import time
import httpx

logger = logging.getLogger(__name__)

_MAYAN_CIRCUIT_THRESHOLD = 3
_MAYAN_CIRCUIT_COOLDOWN_SEC = 60

# ── Endpoint v4 (VERIFICARE contro la propria istanza Mayan) ────────────────
# Filtro documenti per tag e recupero testo OCR variano per versione: questi
# sono i path best-known per Mayan v4.x. Se differiscono, correggere QUI.
_EP_TAG_DOCUMENTS = "/tags/{tag_id}/documents/"          # GET → {results:[{id,label}]}
_EP_DOCUMENT_OCR = "/documents/{doc_id}/ocr/"            # GET → testo OCR concatenato


class MayanClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 20.0) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"Authorization": f"Token {token}"},
            timeout=httpx.Timeout(timeout, connect=5.0),
        )
        self._conn_fail = 0
        self._circuit_until = 0.0

    def _circuit_open(self) -> bool:
        return time.monotonic() < self._circuit_until

    def _record_fail(self) -> None:
        self._conn_fail += 1
        if self._conn_fail >= _MAYAN_CIRCUIT_THRESHOLD and not self._circuit_open():
            self._circuit_until = time.monotonic() + _MAYAN_CIRCUIT_COOLDOWN_SEC
            logger.warning("Mayan unreachable (%d fails) — circuit open %ds",
                           self._conn_fail, _MAYAN_CIRCUIT_COOLDOWN_SEC)

    def _record_ok(self) -> None:
        self._conn_fail = 0
        self._circuit_until = 0.0

    async def _get(self, path: str):
        if self._circuit_open():
            return None
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
            self._record_ok()
            return resp
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException) as exc:
            self._record_fail()
            logger.warning("Mayan GET %s connection error: %s", path, exc)
            return None
        except Exception as exc:
            logger.error("Mayan GET %s failed: %s", path, exc)
            return None

    async def list_tag_documents(self, tag_id: int) -> list[dict]:
        resp = await self._get(_EP_TAG_DOCUMENTS.format(tag_id=tag_id))
        if resp is None:
            return []
        data = resp.json()
        return [{"id": r["id"], "label": r.get("label", "")}
                for r in data.get("results", [])]

    async def get_ocr_text(self, doc_id: int) -> str:
        resp = await self._get(_EP_DOCUMENT_OCR.format(doc_id=doc_id))
        if resp is None:
            return ""
        try:
            data = resp.json()
            # alcune versioni ritornano {content: "..."}; altre testo grezzo
            return data.get("content", "") if isinstance(data, dict) else str(data)
        except Exception:
            return resp.text or ""

    async def aclose(self) -> None:
        await self._client.aclose()
