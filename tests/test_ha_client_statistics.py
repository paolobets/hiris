"""Le statistiche di Home Assistant, lette dal client VERO.

Dal Task 12 della Tappa 2 girano su `scripts/casa_finta.py`: prima `_ws_send`
era sostituito coi costruttori di `tests/_ha_fakes.py`, uscito con loro. La risposta di Home
Assistant e' il `result` del comando (o `SILENT`); cio' che parte si legge in
`house.calls`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import SILENT, CasaFinta

from tests._casa_sintetica import synthetic_inputs

_STATS = "recorder/statistics_during_period"
_IDS = "recorder/list_statistic_ids"


def _house(command: str, result) -> CasaFinta:
    """Home Assistant che a `command` risponde `result` (il `result` grezzo, o
    `SILENT`)."""
    return CasaFinta(synthetic_inputs(), answers={command: lambda extra: result})


_DA = "2026-08-26T00:00:00+00:00"
_A = "2026-08-27T00:00:00+00:00"


# --------------------------------------------------------------------------
# Il bilancio dell'energia (mandato 27/08/2026): `state`/`change` tradotti
# ora, e la sorella `hourly_statistics` con la finestra ESPLICITA.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stato_e_cambio_sono_tradotti():
    """**Misurato il 27/08/2026 sull'impianto vero**: senza `types` esplicito
    Home Assistant manda gia' `state`/`change` insieme a `min`/`max`/`mean`/
    `sum` -- prima di questa correzione il traduttore li scartava in
    silenzio. Forma vera, misurata su `sensor.ze1es030n5e528_energia_
    prodotta_oggi`, ora 07-08."""
    ha = _house(_STATS, {"sensor.energia_prodotta_oggi": [
        {"start": 1787724000000, "end": 1787727600000,
         "min": None, "max": None, "mean": None,
         "sum": 173.77, "state": 0.27, "change": 0.27,
         "last_reset": None}]})
    out = await ha.hourly_statistics(["sensor.energia_prodotta_oggi"], _DA, _A)
    [voce] = out["serie"]["sensor.energia_prodotta_oggi"]
    assert voce["stato"] == 0.27
    assert voce["cambio"] == 0.27
    assert voce["somma"] == 173.77
    assert voce["fine"] == "2026-08-26T07:00:00+00:00"


@pytest.mark.asyncio
async def test_stato_e_cambio_assenti_non_diventano_null():
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
    ha = _house(_STATS, {"sensor.potenza": [
        {"start": 1787724000000, "end": 1787727600000,
         "min": 10.0, "max": 20.0, "mean": 15.0,
         "sum": None, "state": None, "change": None}]})
    out = await ha.hourly_statistics(["sensor.potenza"], _DA, _A)
    [voce] = out["serie"]["sensor.potenza"]
    assert "stato" not in voce
    assert "cambio" not in voce
    assert "somma" not in voce
    assert voce["media"] == 15.0


@pytest.mark.asyncio
async def test_statistiche_orarie_manda_la_finestra_esplicita():
    """`hourly_statistics` non calcola nessuna finestra da sola: prende
    `da_iso`/`a_iso` gia' pronti dal chiamante (come `history()`), e chiede
    sempre `period="hour"`; e la serie tradotta arriva in `serie`.

    Mutazione ESEGUITA: `"period": "day"` in `hourly_statistics` -- rossa
    sull'uguaglianza di `ha.calls`."""
    ha = _house(_STATS, {"sensor.a": [{"start": "2026-08-26T00:00:00+00:00", "mean": 21.6}]})
    out = await ha.hourly_statistics(
        ["sensor.a", "sensor.b"], "2026-08-26T00:00:00+02:00", "2026-08-27T00:00:00+02:00")
    assert ha.calls == [(_STATS, {
        "statistic_ids": ["sensor.a", "sensor.b"],
        "start_time": "2026-08-26T00:00:00+02:00",
        "end_time": "2026-08-27T00:00:00+02:00",
        "period": "hour",
    })]
    assert "sensor.a" in out["serie"]


@pytest.mark.asyncio
async def test_statistiche_orarie_un_guasto_e_dichiarato():
    ha = _house(_STATS, SILENT)
    out = await ha.hourly_statistics(["sensor.a"], "2026-08-26T00:00:00+00:00",
                                      "2026-08-27T00:00:00+00:00")
    assert "serie" not in out
    assert "errore" in out


# --------------------------------------------------------------------------
# Quali entita' abbiano statistiche, spec §6: «rifiuta se l'entita' non ha
# statistiche». Misurato sulla casa vera il 15/09/2026: 130 su 1206.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_le_entita_con_statistiche_si_sanno_chiedere():
    """Il registro delle statistiche di Home Assistant, per nome.

    Serve a dire il primo dei due «rifiuta se» della spec §6: una serie vuota
    puo' voler dire «quel giorno niente» oppure «questa entita' non ne
    produrra' mai», e senza questa lettura le due sono indistinguibili.

    Mutazione ESEGUITA: tornare i messaggi interi invece dei soli nomi --
    rossa.
    """
    ha = _house(_IDS, [{"statistic_id": "sensor.energia", "unit_of_measurement": "kWh"},
                       {"statistic_id": "sensor.potenza", "unit_of_measurement": "W"}])
    out = await ha.statistic_ids()
    assert ha.calls == [(_IDS, None)]
    assert out == {"sensor.energia", "sensor.potenza"}


@pytest.mark.asyncio
async def test_un_guasto_NON_dice_che_nessuna_entita_ha_statistiche():
    """La busta, non l'insieme vuoto. Un insieme vuoto direbbe «nessuna
    entita' di questa casa ha statistiche», e con quella affermazione **ogni
    misura del resoconto rifiuterebbe**. Stessa regola di `statistics` qui
    sopra: un guasto e' un guasto, non un dato. Fino al 03/10/2026 il guasto
    era `None`, una forma sua (D3).

    Mutazione ESEGUITA: tornare `set()` quando il websocket tace -- rossa.
    """
    ha = _house(_IDS, SILENT)
    answer = await ha.statistic_ids()
    assert answer["causa"] == "silenzio" and answer["errore"]
