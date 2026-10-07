"""Il client regge le risposte strane (Tappa 7, Task 14: S-05, S-29, S-34).

Gira il client VERO col trasporto sostituito (`scripts/casa_finta.py`), come
vuole la D8 della Tappa 2: la risposta strana si fabbrica dall'altra parte del
filo, non dentro il metodo che la deve reggere.

- **S-05**: una voce di `lovelace/dashboards/list` che non e' un oggetto non
  fa cadere la lettura di tutte le plance; si dichiara fra i non disponibili.
- **S-34**: una riga di un registro che non e' un oggetto si scarta lei, non
  l'intera lettura (fra le categorie `{**row, ...}` cadeva con `TypeError`).
- **S-29**: l'autenticazione del websocket di lunga vita ha un tetto
  sull'attesa (quello di Home Assistant, `AUTH_MESSAGE_TIMEOUT_S`), e una
  chiusura pulita riparte con la stessa pausa di una caduta.

S-33 (il tetto sulle richieste insieme di `history`) non e' qui: il valore va
misurato sulla casa, e un numero scelto da noi non entra.
"""
import asyncio
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import casa_finta
from casa_finta import CasaFinta

from hiris.app.proxy import ha_client as ha_client_module
from hiris.app.proxy.ha_client import HAClient
from tests._casa_sintetica import synthetic_inputs

#: Il tetto delle attese di una prova: una connessione finta non fa I/O.
CEILING_S = 2


# ── S-05: le plance ─────────────────────────────────────────────────────────

def test_una_voce_dell_elenco_delle_plance_che_non_e_un_oggetto_si_dichiara():
    """Mutazione (eseguita): togliere il controllo `isinstance(d, dict)` --
    rossa, `AttributeError: 'str' object has no attribute 'get'`, e nessuna
    plancia arriva."""
    house = CasaFinta(synthetic_inputs(), answers={
        "lovelace/dashboards/list": lambda extra: ["storta"]})

    dashboards, unavailable = asyncio.run(house.read_dashboards())

    assert [d["url_path"] for d in dashboards] == [None]
    assert any("non e' un oggetto" in reason for reason in unavailable), unavailable


# ── S-34: i registri ────────────────────────────────────────────────────────

def test_una_riga_di_categoria_che_non_e_un_oggetto_non_fa_cadere_la_lettura(caplog):
    """Mutazione (eseguita): togliere il filtro delle righe -- rossa,
    `TypeError` dentro `{**row, "ambito": scope}`."""
    house = CasaFinta(synthetic_inputs(), answers={
        "config/category_registry/list":
            lambda extra: [{"category_id": "c1", "name": "Luci"}, "storta"]})

    with caplog.at_level(logging.WARNING, logger=ha_client_module.logger.name):
        answer = asyncio.run(house.read_registry("categorie"))

    assert "errore" not in answer, answer
    assert answer["categorie"]
    assert all(isinstance(row, dict) for row in answer["categorie"])
    assert "non sono oggetti, scartate" in caplog.text


def test_una_riga_storta_non_arriva_a_chi_legge_un_registro():
    """Negli altri registri la riga storta non faceva cadere niente: arrivava
    a chi legge, che la trattava come un oggetto. Mutazione (eseguita): togliere
    il filtro -- rossa sulla riga `7`."""
    rows = [{"label_id": "cucina", "name": "Cucina"}]
    house = CasaFinta(synthetic_inputs(), answers={
        "config/label_registry/list": lambda extra: [*rows, 7]})

    answer = asyncio.run(house.read_registry("etichette"))

    assert answer["etichette"] == rows


# ── S-29: il websocket di lunga vita ────────────────────────────────────────

class _MuteAtAuth(casa_finta.SilentConnection):
    """Un server che apre la connessione e poi non dice niente: nemmeno
    `auth_required`. La prima connessione e' muta, le altre normali."""

    def __init__(self) -> None:
        super().__init__()
        self.mute_left = 1

    def ws_connect(self, url, **kwargs):
        result = super().ws_connect(url, **kwargs)
        self._mute = self.mute_left > 0
        self.mute_left -= 1
        return result

    async def receive_json(self):
        if self._mute:
            await asyncio.Event().wait()
        return await super().receive_json()


async def _until(condition, what: str) -> None:
    async def poll():
        while not condition():
            await asyncio.sleep(0)
    try:
        await asyncio.wait_for(poll(), CEILING_S)
    except TimeoutError:
        raise AssertionError(f"non e' successo: {what}") from None


async def _stop(client: HAClient) -> None:
    client._ws_task.cancel()
    try:
        await client._ws_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_un_server_muto_all_autenticazione_non_tiene_appeso_il_client(monkeypatch):
    """Mutazione (eseguita): togliere `wait_for` da `_authenticate` -- rossa,
    «non e' successo: la seconda connessione»: il client resta appeso alla
    prima per sempre."""
    monkeypatch.setattr(ha_client_module, "AUTH_MESSAGE_TIMEOUT_S", 0.01)
    monkeypatch.setattr(ha_client_module, "RECONNECT_DELAY_S", 0)
    client = HAClient("http://casa.invalid", "gettone")
    client._session = connection = _MuteAtAuth()

    await client.start_websocket()
    await _until(lambda: connection.listening == 1, "la seconda connessione")

    assert connection.opened == 2
    await _stop(client)


def test_il_tetto_dell_autenticazione_e_quello_di_home_assistant():
    """Il valore non e' nostro: e' `AUTH_MESSAGE_TIMEOUT` di
    `components/websocket_api/http.py` al tag 2026.9.4 (letto il 07/10/2026),
    e il commento accanto lo cita."""
    assert ha_client_module.AUTH_MESSAGE_TIMEOUT_S == 10
    source = Path(ha_client_module.__file__).read_text(encoding="utf-8")
    anchor = source.index("AUTH_MESSAGE_TIMEOUT_S = 10")
    assert "websocket_api/http.py" in source[anchor - 600:anchor]


@pytest.mark.asyncio
async def test_una_chiusura_pulita_riparte_con_la_pausa_di_una_caduta(monkeypatch):
    """Home Assistant che si riavvia chiude il socket senza errori: fino al
    07/10/2026 il client si ricollegava subito, in un giro stretto contro un
    server che non c'e'. Mutazione (eseguita): togliere `pause =
    RECONNECT_DELAY_S` dopo `_listen` -- rossa, nessuna attesa registrata."""
    waited: list[float] = []
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        if seconds:
            waited.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(ha_client_module, "RECONNECT_DELAY_S", 10)
    monkeypatch.setattr(ha_client_module.asyncio, "sleep", sleep)
    client = HAClient("http://casa.invalid", "gettone")
    client._session = connection = casa_finta.SilentConnection()

    await client.start_websocket()
    await _until(lambda: connection.listening == 1, "prima connessione in ascolto")
    connection.drop()
    await _until(lambda: connection.listening == 2, "seconda connessione in ascolto")

    assert waited == [10]
    await _stop(client)
