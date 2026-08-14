"""Task 1 fetta E4 ("Un bot solo"): il WebSocket verso HA e' del server, non
dell'entita' Chatbot (ne' di nulla che potesse portarselo via se cancellata).

Prima, `ChatbotEngine.start()` era l'UNICO chiamante di produzione di
`HAClient.start_websocket()`. Dal WebSocket dipendono tutti i sensi di HIRIS
(`entity_cache.on_state_changed`, la ricostruzione dell'anagrafe, la
rilettura del comportamento e delle plance -- i listener registrati in
`server.py::_on_startup`, :633-690). Se un task successivo cancellasse
l'engine senza aver spostato questa chiamata, HIRIS smetterebbe di sapere
qualsiasi cosa -- niente stato vivo, niente anagrafe, niente comportamento --
e nessuna suite se ne accorgerebbe (nessun test avvia il boot vero, lezione
della review finale E3).

Il Task 1 aveva scritto questo file sapendo gia' che sarebbe successo:
"e' esattamente cio' che protegge un task futuro che tocchi O TOLGA l'engine
(Task 4 di questa fetta: 'quando l'engine uscira', la chiamata restera'
li')". Il Task 4 di questa fetta ("un bot solo") ha fatto esattamente
questo: `ChatbotEngine` e il file che lo conteneva sono usciti per intero,
`app["engine"]` e' diventato `app["impostazioni_chat"]`, e lo scheduler
(APScheduler, che l'engine ospitava solo perche' doveva stare da qualche
parte) e' diventato `app["scheduler"]`, costruito direttamente in
`_on_startup`.

**Cosa e' cambiato in questo file, e perche' non poteva restare fermo.**
L'estrazione originale cercava per testo letterale
`"engine = ChatbotEngine(ha_client=ha_client, data_path=data_path)"` e
`'app["engine"] = engine'`: entrambe le stringhe sono sparite dal sorgente
vero insieme all'entita' che descrivevano -- `src.index(...)` su quel
marcatore solleva `ValueError` (sottostringa non trovata), non un fallimento
dell'assert che il pin vuole dimostrare. Tenere in vita quelle due stringhe
solo per soddisfare l'estrazione avrebbe significato lasciare un
`ChatbotEngine` fantasma nel codice di produzione -- esattamente il difetto
che il Task 4 esiste per chiudere. I marcatori sono stati ripuntati sul
codice che c'e' oggi (`await ha_client.start_websocket()` fino ad
`app["scheduler"] = scheduler`), la tecnica (estrazione del sorgente VERO via
`inspect.getsource`, eseguito isolato) e l'invariante pinnato sono rimasti
identici: il WebSocket si apre incondizionatamente in `_on_startup`, PRIMA di
qualunque cosa possa dipenderne (oggi: lo scheduler) -- e lo dimostra
ANCHE quando quel "qualunque cosa" e' un doppio finto che non tocca affatto
il websocket, la stessa identica prova che il Task 1 aveva scritto.
"""
import inspect
import textwrap

import pytest
from unittest.mock import AsyncMock, MagicMock

from hiris.app import server


def _load_avvio_websocket():
    """Estrae dal sorgente vero di `_on_startup` il blocco che apre il
    websocket e costruisce le impostazioni della chat + lo scheduler -- da
    `await ha_client.start_websocket()` fino (inclusa) ad
    `app["scheduler"] = scheduler`. Lo incapsula in una funzione che riceve
    `ha_client`/`data_dir`/`app`/`ImpostazioniChat`/`AsyncIOScheduler`/`os`/
    `logger` dall'esterno, cosi' da poterla eseguire isolata senza il resto
    del boot (Supervisor/MQTT/deploy della card...)."""
    src = inspect.getsource(server._on_startup)
    start = src.index("    await ha_client.start_websocket()")
    end_marker = 'app["scheduler"] = scheduler'
    end = src.index(end_marker, start) + len(end_marker)
    body = textwrap.dedent(src[start:end])
    func_src = (
        "async def _check(ha_client, data_dir, app, ImpostazioniChat, "
        "AsyncIOScheduler, os, logger, il_file_non_porta_i_giorni):\n"
        + textwrap.indent(body, "    ")
    )
    namespace: dict = {}
    exec(compile(func_src, "<_on_startup avvio websocket>", "exec"), namespace)
    return namespace["_check"]


class _SchedulerFinto:
    """Sostituto minimo di `AsyncIOScheduler`: il suo `start()` NON tocca il
    websocket -- e' apposta, e' cio' che il test vuole dimostrare: e' il
    server ad aprirlo, non lo scheduler (ne' l'entita' Chatbot che lo
    ospitava prima del Task 4 di questa fetta, e che non esiste piu' del
    tutto)."""

    def __init__(self, ordine, *a, **kw):
        self._ordine = ordine

    def start(self) -> None:
        self._ordine.append("scheduler.start")


class _ImpostazioniChatFinte:
    """`carica()` non deve toccare il disco per davvero in questo test
    isolato -- solo dimostrare che viene chiamata dopo il websocket, mai
    prima.

    `salva()` e `giorni_conservazione` esistono perche' dalla chiusura C2 il
    blocco estratto PERSISTE `giorni_conservazione` quando il file non lo
    porta ancora (versione A della migrazione applicata a quel campo). Qui non
    tocca il disco e non compare nell'ordine: cio' che questo test misura e'
    solo che il websocket parta per primo."""

    giorni_conservazione = 90

    @classmethod
    def carica(cls, data_dir):
        return cls()

    def salva(self, data_dir):
        return None


@pytest.mark.asyncio
async def test_lo_startup_apre_il_websocket_prima_di_tutto_il_resto(tmp_path):
    check = _load_avvio_websocket()

    ordine: list[str] = []
    ha_client = MagicMock()
    ha_client.start_websocket = AsyncMock(side_effect=lambda: ordine.append("start_websocket"))

    def _fabbrica_scheduler(**kwargs):
        return _SchedulerFinto(ordine, **kwargs)

    app: dict = {}
    import logging
    import os as os_module

    await check(
        ha_client=ha_client,
        data_dir=str(tmp_path),
        app=app,
        ImpostazioniChat=_ImpostazioniChatFinte,
        AsyncIOScheduler=_fabbrica_scheduler,
        os=os_module,
        logger=logging.getLogger("test_avvio_websocket"),
        il_file_non_porta_i_giorni=lambda data_dir: True,
    )

    ha_client.start_websocket.assert_awaited_once()
    assert "impostazioni_chat" in app, "il blocco estratto deve comunque valorizzare le impostazioni"
    assert "scheduler" in app, "il blocco estratto deve comunque avviare lo scheduler"
    # Il punto del pin: il websocket parte una volta, e PRIMA di qualunque
    # altra cosa nel blocco che potrebbe dipenderne (oggi: lo scheduler) --
    # indipendentemente dal fatto che lo scheduler iniettato tocchi il
    # websocket lui stesso (qui non lo fa affatto).
    assert ordine == ["start_websocket", "scheduler.start"]
