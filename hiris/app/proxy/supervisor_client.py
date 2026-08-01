"""Client di sola lettura per il Supervisor di Home Assistant.

Espone lo stato degli add-on, lo spazio disco dell'host e gli aggiornamenti
disponibili. Nessun metodo qui dentro scrive o modifica lo stato del
sistema: solo GET verso l'API del Supervisor. Su installazioni standalone
(senza Supervisor) o in caso di qualunque errore, ogni metodo degrada a un
valore vuoto invece di sollevare un'eccezione: HIRIS deve continuare a
funzionare comunque.
"""

import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDI = 10


class SupervisorClient:
    def __init__(self, token: str, base_url: str = "http://supervisor") -> None:
        self._token = token
        self._base = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()

    async def stop(self) -> None:
        if self._session:
            await self._session.close()

    async def _get(self, path: str) -> dict:
        """Esegue una GET autenticata verso il Supervisor.

        Ritorna il contenuto di `data` come dict. Qualunque problema (status
        diverso da 200, JSON non valido, `data` non un dict, eccezione di
        rete) viene loggato a livello debug e degrada a dict vuoto: mai
        un'eccezione verso il chiamante.
        """
        url = f"{self._base}{path}"
        headers = {"Authorization": f"Bearer {self._token}"}
        timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SECONDI)
        try:
            async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.debug("Supervisor GET %s: status %s", path, resp.status)
                    return {}
                payload = await resp.json()
        except Exception:
            logger.debug("Supervisor GET %s: errore di rete o payload non valido", path, exc_info=True)
            return {}
        if not isinstance(payload, dict):
            logger.debug("Supervisor GET %s: risposta non un dict", path)
            return {}
        data = payload.get("data")
        if not isinstance(data, dict):
            logger.debug("Supervisor GET %s: 'data' assente o non un dict", path)
            return {}
        return data

    async def get_addons(self) -> list[dict]:
        data = await self._get("/addons")
        addons = data.get("addons")
        if not isinstance(addons, list):
            return []
        out: list[dict] = []
        for addon in addons:
            if not isinstance(addon, dict):
                continue
            out.append({
                "slug": addon.get("slug"),
                "name": addon.get("name"),
                "state": addon.get("state"),
                "version": addon.get("version"),
                "update_available": addon.get("update_available"),
            })
        return out

    async def get_host_info(self) -> dict:
        data = await self._get("/host/info")
        if not data:
            return {}
        return {
            "disk_total": data.get("disk_total"),
            "disk_used": data.get("disk_used"),
            "disk_free": data.get("disk_free"),
        }

    async def get_available_updates(self) -> list[dict]:
        data = await self._get("/available_updates")
        updates = data.get("available_updates")
        if not isinstance(updates, list):
            return []
        out: list[dict] = []
        for update in updates:
            if not isinstance(update, dict):
                continue
            out.append({
                "name": update.get("name"),
                "update_type": update.get("update_type"),
                "version_latest": update.get("version_latest"),
            })
        return out
