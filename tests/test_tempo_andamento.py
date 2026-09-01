"""«Com'e' andata»: i quattro esiti che non si confondono mai.

La spec §3.3 li elenca, e sono il motivo per cui questo file e' lungo:
  - il valore non e' mai cambiato
  - oltre cio' che Home Assistant conserva non resta nulla
  - non ci sono registrazioni (l'entita' potrebbe essere esclusa dal recorder)
  - Home Assistant non ha risposto

Un elenco vuoto che li rappresenta tutti e quattro e' una frase falsa detta
con sicurezza -- ed e' cio' che il prodotto diceva prima di questa fetta.

La finta sa produrre TUTTE queste forme. Una finta che risponde sempre bene
non prova nessuno dei quattro.
"""
from datetime import UTC, datetime, timedelta

import pytest

from hiris.app.casa.tempo import (
    MAX_POINTS_PER_ANSWER,
    _covered,
    instant_epoch,
    trend,
)
from hiris.app.proxy.ha_client import HAClient
from tests._contratti import assert_stessa_firma

NOW = 1787572800.0  # 24 agosto 2026, 12:00 UTC = 14:00 a Roma


class _FintoHA:
    """Sa rispondere bene, sa restituire il vuoto, e sa guastarsi -- perche'
    la meta' che conta di questi test riguarda i due esiti che si somigliano
    e non sono la stessa cosa."""

    def __init__(self, *, storico=None, statistiche=None):
        self._storico = storico if storico is not None else {"serie": {}}
        self._statistiche = statistiche if statistiche is not None else {"serie": {}}
        self.calls = []

    async def history(self, entities, from_iso, to_iso):
        self.calls.append(("storico", tuple(entities), from_iso, to_iso))
        return self._storico

    async def statistics(self, identifiers, period, days):
        self.calls.append(("statistiche", tuple(identifiers), period, days))
        return self._statistiche


# `HAClient` e' un ambito che questa fetta non converte: i suoi metodi
# restano in italiano, e questa finta li imita col loro nome vero. Se
# `HAClient.history`/`.statistiche` cambiassero firma (o qualcuno li
# rinominasse insieme al chiamante, come e' gia' successo una volta in
# questa fetta -- review Task 8, `ha.statistics()` diventato
# `ha.statistics()` nel sorgente mentre la finta seguiva a ruota), questa
# riga cade invece di lasciare la suite verde su un contratto che non
# esiste piu'.
assert_stessa_firma(HAClient.history, _FintoHA.history, nome="storico")
assert_stessa_firma(HAClient.statistics, _FintoHA.statistics, nome="statistiche")


@pytest.mark.asyncio
async def test_short_window_reads_real_changes():
    ha = _FintoHA(storico={"serie": {"sensor.camera": [
        {"quando": "2026-08-24T12:00:00+02:00", "valore": "21.0"},
        {"quando": "2026-08-24T13:00:00+02:00", "valore": "21.4"},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=2, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert occurrence["grana"] == "dettaglio"
    assert occurrence["unita"] == "°C"
    assert len(occurrence["punti"]) == 2
    assert ha.calls[0][0] == "storico"


@pytest.mark.asyncio
async def test_forty_eight_hours_of_a_sensor_receive_hourly_bands():
    """La domanda da cui la fetta nasce. Cade SOPRA la soglia e riceve fasce:
    la spec §4.1 lo dichiara, e questo test e' il posto in cui quella scelta
    e' visibile invece che sepolta in una costante."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "minimo": 25.9,
         "massimo": 27.1, "media": 26.5},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=48, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert occurrence["grana"] == "oraria"
    assert occurrence["punti"][0]["media"] == 26.5
    assert ha.calls[0][0] == "statistiche"
    # M5: un refuso su "hour" o nel calcolo dei giorni passerebbe inosservato
    # se nessuno guardasse cosa arriva davvero a `ha.statistics`.
    assert ha.calls[0][2] == "hour"
    assert ha.calls[0][3] == int(48 / 24) + 1


@pytest.mark.asyncio
async def test_hourly_granularity_is_declared_in_the_note():
    """Una media oraria presentata come una misura e' una frase vera che
    significa una cosa falsa (spec §3.2)."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "minimo": 25.9,
         "massimo": 27.1, "media": 26.5},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=48, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert "orarie" in occurrence["nota"]


@pytest.mark.asyncio
async def test_a_failure_is_not_a_value_that_never_changed():
    ha = _FintoHA(storico={"errore": "Home Assistant ha risposto 502"})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=2, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert "punti" not in occurrence
    assert "502" in occurrence["errore"]


@pytest.mark.asyncio
async def test_no_recording_declares_the_doubt_about_the_recorder():
    """Un elenco vuoto DAVVERO vuoto (non un guasto) non e' «non e' mai
    cambiata»: potrebbe essere un'entita' esclusa dalla registrazione, e per
    quelle lo storico e' vuoto per sempre. Non lo sappiamo con certezza, e la
    risposta lo dice cosi': dichiarando il dubbio, non affermando."""
    ha = _FintoHA(storico={"serie": {}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=2, unit="°C",
                            has_statistics=False, now_ts=NOW, timezone="Europe/Rome")
    assert occurrence["punti"] == []
    assert "esclusa" in occurrence["nota"]
    assert "mai cambiat" not in occurrence["nota"]


@pytest.mark.asyncio
async def test_a_single_point_is_a_steady_value_not_an_empty_one():
    ha = _FintoHA(storico={"serie": {"sensor.camera": [
        {"quando": "2026-08-24T12:00:00+02:00", "valore": "21.0"},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=2, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert len(occurrence["punti"]) == 1
    assert "non e' mai cambiato" in occurrence["nota"]


@pytest.mark.asyncio
async def test_the_covered_window_is_MEASURED_not_assumed():
    """`purge_keep_days` non e' leggibile da nessuna API. Se i dati cominciano
    dopo l'inizio della finestra chiesta, la finestra coperta e' quella dei
    dati -- misurata, non dedotta da una costante che potrebbe essere falsa su
    questa casa."""
    ha = _FintoHA(storico={"serie": {"sensor.camera": [
        {"quando": "2026-08-24T13:30:00+02:00", "valore": "21.0"},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=24, unit="°C",
                            has_statistics=False, now_ts=NOW, timezone="Europe/Rome")
    assert occurrence["finestra_coperta"]["da"] == "2026-08-24T13:30:00+02:00"
    assert occurrence["finestra_chiesta_ore"] == 24.0


@pytest.mark.asyncio
async def test_the_volume_is_summarized_and_declared():
    punti = [{"quando": f"2026-08-24T{h:02d}:{m:02d}:00+02:00", "valore": str(20 + m % 5)}
             for h in range(14) for m in range(60)]
    ha = _FintoHA(storico={"serie": {"sensor.camera": punti}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=24, unit="°C",
                            has_statistics=False, now_ts=NOW, timezone="Europe/Rome")
    assert len(occurrence["punti"]) <= MAX_POINTS_PER_ANSWER
    assert "840" in occurrence["nota"]  # il numero VERO dei cambi, non «molti»


@pytest.mark.asyncio
async def test_without_statistics_a_long_window_stays_on_detail():
    ha = _FintoHA(storico={"serie": {"binary_sensor.porta": [
        {"quando": "2026-08-23T20:00:00+02:00", "valore": "on"},
    ]}})
    occurrence = await trend(ha=ha, entity="binary_sensor.porta", hours=72, unit=None,
                            has_statistics=False, now_ts=NOW, timezone="Europe/Rome")
    assert occurrence["grana"] == "dettaglio"
    assert ha.calls[0][0] == "storico"


@pytest.mark.asyncio
async def test_the_covered_window_rewrites_the_timezone_from_the_UTC_source():
    """I3: le statistiche di Home Assistant tornano SEMPRE in UTC -- e' il
    caso NORMALE, non l'eccezione. Nessuno degli altri test lo esercita: se
    la riscrittura del fuso in `_coperta` sparisse, nessuno se ne
    accorgerebbe, perche' gli altri test partono gia' da un sorgente in
    +02:00. 13:00 UTC di agosto sono 15:00 a Roma (CEST, +02:00)."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "minimo": 25.9,
         "massimo": 27.1, "media": 26.5},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=48, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert occurrence["finestra_coperta"]["da"] == "2026-08-23T15:00:00+02:00"


@pytest.mark.asyncio
async def test_bands_beyond_the_max_are_sampled_like_detail():
    """C2: uno slice secco (`fasce[-N:]`) sposta `punti[0]` avanti nel tempo
    mentre `finestra_coperta` restava calcolata sull'elenco INTERO -- una
    copertura dichiarata e mai consegnata. Il ramo statistiche deve
    campionare come il gemello del dettaglio (`_assottiglia`, primo e ultimo
    sempre compresi) e dichiarare il numero VERO di fasce quando riduce.

    Il confronto fra `punti[0]["inizio"]` e `finestra_coperta["da"]` passa
    per `epoch_istante`, non per l'uguaglianza di stringa: le fasce tornano
    in UTC (`+00:00`) mentre `finestra_coperta` e' riscritta nel fuso della
    casa (`+02:00`) -- stesso istante, offset diverso, stessa fondamenta 3
    del test precedente."""
    base = datetime(2026, 8, 15, 9, 0, 0, tzinfo=UTC)
    fasce = [{"inizio": (base + timedelta(hours=i)).isoformat(),
              "minimo": 20.0, "massimo": 21.0, "media": 20.5}
             for i in range(200)]
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": fasce}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=240, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert len(occurrence["punti"]) <= MAX_POINTS_PER_ANSWER
    assert instant_epoch(occurrence["punti"][0]["inizio"]) == \
        instant_epoch(occurrence["finestra_coperta"]["da"])
    assert "200" in occurrence["nota"]  # il numero VERO delle fasce, non «molte»


# -- F1 (onda finale): un istante non leggibile e' un guasto, non un vuoto --

@pytest.mark.asyncio
async def test_band_with_numeric_start_fails_loudly():
    """Alcune versioni del recorder rendono `start` come epoch in
    millisecondi (un numero), non come stringa ISO -- mai misurato dal vivo
    su questo prodotto (spec S7). Prima della correzione l'`or 0.0` faceva
    scambiare questo caso per «prima della finestra»: la fascia spariva in
    silenzio e la risposta diceva con sicurezza «nessuna registrazione» per
    un'entita' che invece aveva dati veri."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": 1787569200000, "minimo": 25.9, "massimo": 27.1, "media": 26.5},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=48, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert "punti" not in occurrence
    assert "errore" in occurrence
    # Non e' la nota del terzo esito (§3.3): un guasto non e' un vuoto.
    assert "non ha registrazioni" not in occurrence["errore"]


@pytest.mark.asyncio
async def test_band_without_start_fails_loudly():
    """Lo stesso guasto, ma con la chiave assente invece che di un tipo
    inatteso: anche qui `epoch_istante` torna `None`, e deve fermare la
    risposta invece di essere confuso con un vuoto legittimo."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"minimo": 25.9, "massimo": 27.1, "media": 26.5},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=48, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert "punti" not in occurrence
    assert "errore" in occurrence


@pytest.mark.asyncio
async def test_truly_empty_statistics_stay_the_no_recording_occurrence():
    """Regressione: senza NESSUNA fascia (non un problema di forma, un vuoto
    vero) l'esito resta il terzo del §3.3, non un errore -- la correzione di
    F1 non deve trasformare ogni assenza in un guasto."""
    ha = _FintoHA(statistiche={"serie": {}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=48, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert "errore" not in occurrence
    assert occurrence["punti"] == []
    assert "esclusa" in occurrence["nota"]


def test_covered_with_unreadable_instant_has_consistent_types():
    """`_coperta` non deve mescolare tipi nella stessa coppia: se l'istante
    grezzo non si legge, sia `da` sia `a` restano stringhe -- un `da`
    numerico accanto a un `a` ISO e' la stessa famiglia di difetto di una
    grana taciuta."""
    result = _covered([{"quando": 1787569200000}], "quando",
                         "2026-08-24T14:00:00+02:00")
    assert isinstance(result["da"], str)
    assert result["da"] == "1787569200000"


def test_covered_with_missing_instant_stays_none():
    """Il caso degenere: nessuna chiave a cui appoggiarsi resta `None`, non
    la stringa letterale "None"."""
    result = _covered([{}], "quando", "2026-08-24T14:00:00+02:00")
    assert result["da"] is None


# -- F2 (onda finale): il troncamento del CLIENT diventa un pavimento -------

@pytest.mark.asyncio
async def test_the_client_truncation_becomes_a_declared_floor():
    """`ha.history` promette `troncato` SEMPRE, apposta perche' «chi legge
    deve poter sapere che e' scattato». Se `tempo.andamento` non lo legge, il
    conteggio nella nota e' un pavimento spacciato per esatto: su 12.000
    cambi veri direbbe «5000 cambi», non «almeno 5000»."""
    punti = [{"quando": f"2026-08-24T00:{m:02d}:00+02:00", "valore": "x"}
             for m in range(60)]
    ha = _FintoHA(storico={"serie": {"sensor.camera": punti}, "troncato": True})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=2, unit=None,
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert f"almeno {len(punti)}" in occurrence["nota"]
    assert "piu' corta" in occurrence["nota"] or "piu' vecchi" in occurrence["nota"]


@pytest.mark.asyncio
async def test_without_truncation_the_count_stays_exact():
    """Regressione: senza `troncato`, la nota non deve mai dire «almeno»."""
    punti = [{"quando": f"2026-08-24T00:{m:02d}:00+02:00", "valore": "x"}
             for m in range(60)]
    ha = _FintoHA(storico={"serie": {"sensor.camera": punti}, "troncato": False})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=2, unit=None,
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert "almeno" not in (occurrence["nota"] or "")


@pytest.mark.asyncio
async def test_points_come_out_in_the_SAME_timezone_as_the_covered_window():
    """Visto dal vivo il 24/08/2026: `finestra_coperta` diceva
    `2026-08-24T14:18+02:00` e `punti[0]` diceva `2026-08-24T12:18+00:00`.
    Sono lo STESSO istante, ma dentro un dizionario solo, e chi legge puo'
    concluderne che i dati cominciano due ore dopo l'apertura della finestra
    -- che e' falso. Lo storico di Home Assistant torna in UTC, la finestra
    nasce nel fuso della casa: e' la fondamenta 3 dentro una risposta sola.
    """
    ha = _FintoHA(storico={"serie": {"sensor.camera": [
        {"quando": "2026-08-24T10:18:50+00:00", "valore": "25.5"},
        {"quando": "2026-08-24T11:00:00+00:00", "valore": "25.6"},
    ]}, "troncato": False})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=6, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert occurrence["punti"][0]["quando"] == "2026-08-24T12:18:50+02:00"
    assert occurrence["punti"][1]["quando"] == "2026-08-24T13:00:00+02:00"
    assert occurrence["finestra_coperta"]["da"] == occurrence["punti"][0]["quando"]


@pytest.mark.asyncio
async def test_bands_also_come_out_in_the_home_space_timezone():
    """Il gemello del test qui sopra sul ramo delle statistiche: stessa
    domanda, stessa forma della risposta (fondamenta 3)."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "minimo": 25.9,
         "massimo": 27.1, "media": 26.5},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=48, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert occurrence["punti"][0]["inizio"] == "2026-08-23T15:00:00+02:00"
    assert occurrence["finestra_coperta"]["da"] == occurrence["punti"][0]["inizio"]


@pytest.mark.asyncio
async def test_the_end_of_a_band_comes_out_in_the_SAME_timezone_as_the_start():
    """Punto 5 del mandato «il bilancio dell'energia» (BASSO, 27/08/2026):
    la traduzione unificata (`HAClient._request_statistics`) ha aggiunto
    la chiave `fine` a ogni fascia, ma `andamento` riscriveva nel fuso della
    casa SOLO `inizio` -- lo stesso punto usciva con `inizio` a +02:00 e
    `fine` ancora a +00:00, due fusi nella stessa risposta (fondamenta 3
    rotta dentro un dizionario solo, gli stessi commenti di questo modulo la
    denunciano per `finestra_coperta`/`punti` e non se ne accorgevano per
    `fine`)."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "fine": "2026-08-23T14:00:00+00:00",
         "minimo": 25.9, "massimo": 27.1, "media": 26.5},
    ]}})
    occurrence = await trend(ha=ha, entity="sensor.camera", hours=48, unit="°C",
                            has_statistics=True, now_ts=NOW, timezone="Europe/Rome")
    assert occurrence["punti"][0]["inizio"] == "2026-08-23T15:00:00+02:00"
    assert occurrence["punti"][0]["fine"] == "2026-08-23T16:00:00+02:00"
