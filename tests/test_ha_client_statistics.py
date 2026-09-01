import pytest

from hiris.app.proxy.ha_client import HAClient


@pytest.mark.asyncio
async def test_statistiche_returns_dict(monkeypatch):
    ha = HAClient("http://ha.local:8123", "tok")
    captured = {}

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        captured["msg_type"] = msg_type
        captured["extra"] = extra
        return {"sensor.temp": [{"start": "2026-06-20T00:00:00+00:00",
                                 "mean": 21.6, "min": 19.1, "max": 24.3}]}

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.statistics(["sensor.temp"], period="day", days=30)
    assert captured["msg_type"] == "recorder/statistics_during_period"
    assert captured["extra"]["statistic_ids"] == ["sensor.temp"]
    assert captured["extra"]["period"] == "day"
    assert "sensor.temp" in out["serie"]


@pytest.mark.asyncio
async def test_statistiche_un_guasto_non_e_una_serie_vuota(monkeypatch):
    """Prima un risultato non-dict (websocket giu') valeva {} -- indistinguibile
    da "nessuna statistica per queste entita'". Adesso e' un guasto dichiarato."""
    ha = HAClient("http://ha.local:8123", "tok")

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        return None

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.statistics(["sensor.temp"], period="hour", days=1)
    assert "serie" not in out
    assert "errore" in out


# --------------------------------------------------------------------------
# Il bilancio dell'energia (mandato 27/08/2026): `state`/`change` tradotti
# ora, e la sorella `hourly_statistics` con la finestra ESPLICITA.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stato_e_cambio_sono_tradotti(monkeypatch):
    """**Misurato il 27/08/2026 sull'impianto vero**: senza `types` esplicito
    Home Assistant manda gia' `state`/`change` insieme a `min`/`max`/`mean`/
    `sum` -- prima di questa correzione il traduttore li scartava in
    silenzio. Forma vera, misurata su `sensor.ze1es030n5e528_energia_
    prodotta_oggi`, ora 07-08."""
    ha = HAClient("http://ha.local:8123", "tok")

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        return {"sensor.energia_prodotta_oggi": [
            {"start": 1787724000000, "end": 1787727600000,
             "min": None, "max": None, "mean": None,
             "sum": 173.77, "state": 0.27, "change": 0.27,
             "last_reset": None}]}

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.statistics(["sensor.energia_prodotta_oggi"], period="hour", days=1)
    [voce] = out["serie"]["sensor.energia_prodotta_oggi"]
    assert voce["stato"] == 0.27
    assert voce["cambio"] == 0.27
    assert voce["somma"] == 173.77
    assert voce["fine"] == "2026-08-26T07:00:00+00:00"


@pytest.mark.asyncio
async def test_stato_e_cambio_assenti_non_diventano_null(monkeypatch):
    """Una misura istantanea (`state_class: measurement`, es. la potenza) non
    ha ne' `state` ne' `change` in HA -- **misurato**: entrambi tornano
    `None` dalla WS. Devono restare OMESSI dalla voce tradotta, come gia'
    vale per `somma`: un `None` esplicito direbbe "azzerato", un campo
    assente dice "non richiesto a questo statistic_id".

    Mutazione ESEGUITA: `if f.get("state") is not None: voce["stato"] = ...`
    sostituito con un'assegnazione incondizionata (`voce["stato"] =
    f.get("state")`) in `_translate_statistics` -- arrossisce, perche' "stato"
    compare nella voce con valore `None` invece di mancare del tutto.
    Ripristinato subito dopo."""
    ha = HAClient("http://ha.local:8123", "tok")

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        return {"sensor.potenza": [
            {"start": 1787724000000, "end": 1787727600000,
             "min": 10.0, "max": 20.0, "mean": 15.0,
             "sum": None, "state": None, "change": None}]}

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.statistics(["sensor.potenza"], period="hour", days=1)
    [voce] = out["serie"]["sensor.potenza"]
    assert "stato" not in voce
    assert "cambio" not in voce
    assert "somma" not in voce
    assert voce["media"] == 15.0


@pytest.mark.asyncio
async def test_statistiche_orarie_manda_la_finestra_esplicita(monkeypatch):
    """`hourly_statistics` non calcola nessuna finestra da sola: prende
    `da_iso`/`a_iso` gia' pronti dal chiamante (come `history()`), e chiede
    sempre `period="hour"`."""
    ha = HAClient("http://ha.local:8123", "tok")
    captured = {}

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        captured["msg_type"] = msg_type
        captured["extra"] = extra
        return {}

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.hourly_statistics(
        ["sensor.a", "sensor.b"], "2026-08-26T00:00:00+02:00", "2026-08-27T00:00:00+02:00")
    assert captured["msg_type"] == "recorder/statistics_during_period"
    assert captured["extra"] == {
        "statistic_ids": ["sensor.a", "sensor.b"],
        "start_time": "2026-08-26T00:00:00+02:00",
        "end_time": "2026-08-27T00:00:00+02:00",
        "period": "hour",
    }
    assert out == {"serie": {}}


@pytest.mark.asyncio
async def test_statistiche_orarie_un_guasto_e_dichiarato(monkeypatch):
    ha = HAClient("http://ha.local:8123", "tok")

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        return None

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.hourly_statistics(["sensor.a"], "2026-08-26T00:00:00+00:00",
                                      "2026-08-27T00:00:00+00:00")
    assert "serie" not in out
    assert "errore" in out


@pytest.mark.asyncio
async def test_statistiche_e_statistiche_orarie_condividono_la_traduzione(monkeypatch):
    """Fondamenta 2 (nessun doppione), provata: le due entrate rispondono
    IDENTICHE a chiavi HA identiche -- non ci sono due tabelle di traduzione
    che potrebbero divergere."""
    ha = HAClient("http://ha.local:8123", "tok")
    fascia = {"start": 1787724000000, "end": 1787727600000,
             "min": 1.0, "max": 2.0, "mean": 1.5, "sum": 9.0,
             "state": 3.0, "change": 0.5}

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        return {"sensor.x": [dict(fascia)]}

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    a = await ha.statistics(["sensor.x"], period="hour", days=1)
    b = await ha.hourly_statistics(["sensor.x"], "2026-08-26T00:00:00+00:00",
                                    "2026-08-27T00:00:00+00:00")
    assert a["serie"] == b["serie"]
