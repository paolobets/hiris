"""Task 1 fetta E4 ("Un bot solo"): il WebSocket verso HA e' del server, non
dell'engine.

Prima, `ChatbotEngine.start()` era l'UNICO chiamante di produzione di
`HAClient.start_websocket()` (chatbot_engine.py:173): dal WebSocket dipendono
tutti i sensi di HIRIS (`entity_cache.on_state_changed`, la ricostruzione
dell'anagrafe, la rilettura del comportamento e delle plance -- i listener
registrati in `server.py::_on_startup`, :633-690). Se un task successivo
cancellasse l'engine senza aver spostato questa chiamata, HIRIS smetterebbe
di sapere qualsiasi cosa -- niente stato vivo, niente anagrafe, niente
comportamento -- e nessuna suite se ne accorgerebbe (nessun test avvia il
boot vero, lezione della review finale E3).

Questo file pinna lo spostamento: `_on_startup` apre il websocket da solo,
SUBITO PRIMA di `engine.start()` (dopo la registrazione di tutti i listener
sopra) e ANCHE SE l'engine iniettato non lo fa piu' -- e' esattamente cio'
che protegge un task futuro che tocchi o tolga l'engine (Task 4 di questa
fetta: "quando l'engine uscira', la chiamata restera' li'").

Stessa tecnica di test_startup_legacy_db_silence.py e
test_reasoning_sweep_chat_skip.py: il blocco reale di `_on_startup` viene
estratto via `inspect.getsource` ed eseguito isolato -- il corpo eseguito e'
quello vero spedito nel prodotto, non una parafrasi a mano che potrebbe
divergere in silenzio. Qui il blocco non e' una funzione nidificata (come
`_reasoning_sweep`) ma istruzioni inline, come nei blocchi di silenzio: li
si incapsula in una `async def _check(...)` sintetica che riceve dall'esterno
tutto cio' che il blocco vero legge come variabile libera.
"""
import inspect
import textwrap

import pytest
from unittest.mock import AsyncMock, MagicMock

from hiris.app import server


def _load_avvio_websocket():
    """Estrae dal sorgente vero di `_on_startup` il blocco che costruisce
    l'engine e avvia il websocket -- da `engine = ChatbotEngine(...)` fino a
    (inclusa) `app["engine"] = engine`. Lo incapsula in una funzione che
    riceve `ha_client`/`entity_cache`/`archivio_casa`/`archivio_memoria`/
    `data_path`/`app`/`ChatbotEngine` dall'esterno, cosi' da poterla eseguire
    isolata senza il resto del boot (Supervisor/MQTT/deploy della card...)."""
    src = inspect.getsource(server._on_startup)
    start = src.index("    engine = ChatbotEngine(ha_client=ha_client, data_path=data_path)")
    end_marker = 'app["engine"] = engine'
    end = src.index(end_marker, start) + len(end_marker)
    body = textwrap.dedent(src[start:end])
    func_src = (
        "async def _check(ha_client, entity_cache, archivio_casa, archivio_memoria, "
        "data_path, app, ChatbotEngine):\n" + textwrap.indent(body, "    ")
    )
    namespace: dict = {}
    exec(compile(func_src, "<_on_startup avvio websocket>", "exec"), namespace)
    return namespace["_check"]


class _EngineFinto:
    """Motore finto: il suo `start()` NON tocca il websocket -- e' apposta,
    e' cio' che il test vuole dimostrare: e' il server ad aprirlo, non
    l'engine, quindi la chiamata sopravvive anche a un engine che non la fa
    (o a un engine cancellato del tutto, Task 4)."""

    def __init__(self, ordine, **kwargs):
        self._ordine = ordine
        self.avviato = False

    def set_entity_cache(self, cache) -> None:
        self.entity_cache = cache

    def set_archivi(self, archivio_casa, archivio_memoria) -> None:
        self.archivio_casa = archivio_casa
        self.archivio_memoria = archivio_memoria

    async def start(self) -> None:
        self._ordine.append("engine.start")
        self.avviato = True


@pytest.mark.asyncio
async def test_lo_startup_apre_il_websocket_anche_se_lengine_non_lo_fa(tmp_path):
    check = _load_avvio_websocket()

    ordine: list[str] = []
    ha_client = MagicMock()
    ha_client.start_websocket = AsyncMock(side_effect=lambda: ordine.append("start_websocket"))

    def _fabbrica_engine(**kwargs):
        return _EngineFinto(ordine, **kwargs)

    app: dict = {}
    await check(
        ha_client=ha_client,
        entity_cache=object(),
        archivio_casa=object(),
        archivio_memoria=object(),
        data_path=str(tmp_path / "chatbots.json"),
        app=app,
        ChatbotEngine=_fabbrica_engine,
    )

    ha_client.start_websocket.assert_awaited_once()
    assert app["engine"].avviato, "il blocco estratto deve comunque avviare l'engine"
    # Il punto del pin: il websocket parte una volta, e PRIMA di engine.start()
    # -- l'ordine di oggi alla riga (listener gia' registrati sopra nel vero
    # _on_startup, poi websocket, poi engine) -- indipendentemente dal fatto
    # che l'engine iniettato lo faccia (qui non lo fa affatto).
    assert ordine == ["start_websocket", "engine.start"]
