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
`app["engine"]` e' diventato `app["chat_settings"]`, e lo scheduler
(APScheduler, che l'engine ospitava solo perche' doveva stare da qualche
parte) e' diventato `app["scheduler"]`, costruito direttamente in
`_on_startup`.

**Dal 03/10/2026 l'avvio gira davvero** (Tappa 1 dello sprint «Una fonte
sola di verita'»). Prima il blocco si ritagliava dal testo di `_on_startup`
fra due marcatori (`await ha_client.start_websocket()` e
`app["scheduler"] = scheduler`) e si eseguiva isolato con doppi: un marcatore
sparito -- e' successo una volta, con `ChatbotEngine` -- rompeva la prova
senza che niente fosse cambiato. Adesso la casa dell'avvio
(`tests/_avvio.py::RecordingHouse`) ricorda quando le si apre il websocket,
e una spia che AVVOLGE i metodi veri ricorda quando lo schedulatore parte e
quando si leggono le impostazioni della chat. L'invariante e' lo stesso: il
WebSocket si apre una volta, incondizionatamente, PRIMA di qualunque cosa
possa dipenderne.
"""
from unittest import mock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from hiris.app.chat_settings import ChatSettings
from tests._avvio import RecordingHouse, started_with


@pytest.mark.asyncio
async def test_lo_startup_apre_il_websocket_prima_di_tutto_il_resto(tmp_path):
    """Mutazione ESEGUITA (03/10/2026): `await ha_client.start_websocket()`
    spostata subito dopo `scheduler.start()` -- rossa (l'ordine registrato
    diventa `chat_settings.load, scheduler.start, start_websocket`)."""
    ordine: list[str] = []

    class House(RecordingHouse):
        async def start_websocket(self) -> None:
            ordine.append("start_websocket")
            await super().start_websocket()

    real_start = AsyncIOScheduler.start
    real_load = ChatSettings.load.__func__

    def start(self, *args, **kwargs):
        ordine.append("scheduler.start")
        return real_start(self, *args, **kwargs)

    def load(cls, data_dir):
        ordine.append("chat_settings.load")
        return real_load(cls, data_dir)

    with mock.patch.object(AsyncIOScheduler, "start", start), \
            mock.patch.object(ChatSettings, "load", classmethod(load)):
        async with started_with(tmp_path, house_class=House) as app:
            assert isinstance(app["chat_settings"], ChatSettings)
            assert isinstance(app["scheduler"], AsyncIOScheduler)

    # Il punto del pin: il websocket parte UNA volta, e PRIMA di qualunque
    # altra cosa che potrebbe dipenderne (oggi: le impostazioni e lo
    # schedulatore) -- indipendentemente dal fatto che lo schedulatore tocchi
    # il websocket lui stesso (non lo fa).
    assert ordine == ["start_websocket", "chat_settings.load", "scheduler.start"]
