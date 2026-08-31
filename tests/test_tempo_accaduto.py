"""«Cosa e' successo, e per mano di chi».

Due fatti diversi che non vanno mai fusi (spec §2.2): cosa e' successo in casa
(il diario di Home Assistant) e cosa ha fatto HIRIS (la cronaca). Restano due
case, e si uniscono al momento della LETTURA.

L'abbinamento e' **probabile e lo dice**. Home Assistant non mette un nostro
identificatore nel logbook: l'unico aggancio e' entita' + istante vicino. Un
prodotto che dicesse «l'ho accesa io» sulla base di una coincidenza temporale,
senza dichiararlo, mentirebbe con sicurezza -- il difetto che questo progetto
paga piu' caro di ogni altro.
"""
import pytest

from hiris.app.azione.cronaca import Journal
from hiris.app.casa.tempo import logbook
from hiris.app.proxy.ha_client import HAClient
from tests._contratti import assert_stessa_firma

NOW = 1787572800.0  # 24 agosto 2026, 12:00 UTC


class _FintoHA:
    def __init__(self, risposta):
        self._risposta = risposta

    async def diario(self, entita, ore):
        return self._risposta


# `HAClient` non e' convertito da questa fetta: se `.diario` cambiasse
# firma (o una finta futura la seguisse a ruota rinominandosi come il
# chiamante, gia' successo una volta in questa fetta -- review Task 8),
# questa riga cade prima che la produzione veda un `AttributeError`.
assert_stessa_firma(HAClient.diario, _FintoHA.diario, nome="diario")


class _FintaCronaca:
    def __init__(self, righe):
        self._righe = righe
        self.chiamate = []

    def list(self, *, from_ts, to_ts, entity=None, limit=200):
        self.chiamate.append((from_ts, to_ts, entity))
        return list(self._righe)


def test_the_fake_journal_matches_the_real_signature():
    """Se `Journal.list` cambia firma, questo test cade invece di
    lasciare che il finto imiti un contratto che non esiste piu'
    (review indipendente, fetta «la rinomina»: `entita=`/`limite=` erano
    rimasti qui mentre `casa/tempo.py::accaduto` chiamava gia' `.list(...
    entity=...)`)."""
    assert_stessa_firma(Journal.list, _FintaCronaca.list, nome="list")
    assert_stessa_firma(Journal.list, _FintaCronacaCheSolleva.list,
                        nome="list (che solleva)")


def _voce(quando, messaggio="acceso", entita="light.cucina"):
    return {"quando": quando, "nome": "Cucina", "messaggio": messaggio,
            "entita": entita}


@pytest.mark.asyncio
async def test_an_act_by_hiris_is_recognized_and_declared_probable():
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    cronaca = _FintaCronaca([{
        "id": "abc", "quando_ts": 1787569200.0,  # 11:00:00 UTC, lo stesso istante
        "origine": "chat", "servizio": "light.turn_on",
        "entita": ["light.cucina"], "eseguito": True, "genere": "comando",
        "cambiato": None, "errore": None, "avviso": None, "oggetto": None}])
    occurrence = await logbook(ha=ha, journal=cronaca, entity="light.cucina",
                           hours=24, now_ts=NOW)
    voce = occurrence["voci"][0]
    assert voce["per_mano_di"] == "HIRIS"
    assert voce["abbinamento"] == "probabile"
    assert voce["atto"]["servizio"] == "light.turn_on"


@pytest.mark.asyncio
async def test_an_entry_far_in_time_does_not_match():
    """Mezz'ora dopo non e' lo stesso gesto. Senza tolleranza, ogni atto di
    HIRIS si prenderebbe il merito di tutto cio' che quella lampada ha fatto
    nella giornata."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:30:00+00:00")],
                   "troncato": False, "ore": 24})
    cronaca = _FintaCronaca([{
        "id": "abc", "quando_ts": 1787569200.0, "origine": "chat",
        "servizio": "light.turn_on", "entita": ["light.cucina"],
        "eseguito": True, "genere": "comando", "cambiato": None,
        "errore": None, "avviso": None, "oggetto": None}])
    occurrence = await logbook(ha=ha, journal=cronaca, entity="light.cucina",
                           hours=24, now_ts=NOW)
    assert "per_mano_di" not in occurrence["voci"][0]


@pytest.mark.asyncio
async def test_an_act_on_another_entity_does_not_match():
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    cronaca = _FintaCronaca([{
        "id": "abc", "quando_ts": 1787569200.0, "origine": "chat",
        "servizio": "light.turn_on", "entita": ["light.salotto"],
        "eseguito": True, "genere": "comando", "cambiato": None,
        "errore": None, "avviso": None, "oggetto": None}])
    occurrence = await logbook(ha=ha, journal=cronaca, entity="light.cucina",
                           hours=24, now_ts=NOW)
    assert "per_mano_di" not in occurrence["voci"][0]


@pytest.mark.asyncio
async def test_without_a_match_the_entry_stays_whole_and_honest():
    """«L'ha accesa qualcuno e non so chi» e' una risposta buona. Non lo e'
    tacere la voce perche' non sappiamo attribuirla."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    occurrence = await logbook(ha=ha, journal=_FintaCronaca([]), entity="light.cucina",
                           hours=24, now_ts=NOW)
    assert len(occurrence["voci"]) == 1
    assert "per_mano_di" not in occurrence["voci"][0]


@pytest.mark.asyncio
async def test_a_diary_failure_is_not_a_quiet_day():
    ha = _FintoHA({"errore": "Home Assistant ha risposto 503"})
    occurrence = await logbook(ha=ha, journal=_FintaCronaca([]), entity=None,
                           hours=24, now_ts=NOW)
    assert "voci" not in occurrence and "503" in occurrence["errore"]


@pytest.mark.asyncio
async def test_the_diary_truncation_reaches_the_note():
    """Una lista tagliata che non dichiara il taglio fa concludere al modello
    «non e' successo altro»."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": True, "ore": 168})
    occurrence = await logbook(ha=ha, journal=_FintaCronaca([]), entity=None,
                           hours=1000, now_ts=NOW)
    assert "piu' vecchie" in occurrence["nota"]
    assert occurrence["ore"] == 168


@pytest.mark.asyncio
async def test_the_journal_is_queried_on_the_same_window_as_the_diary():
    """Due finestre diverse produrrebbero atti senza voce e voci senza atto,
    in modo invisibile. Si chiede una finestra piu' larga di quella che il
    client clampa (`ore=1000`): la finta dichiara `ore: 168`, il vero tetto
    del diario. La finestra della cronaca deve seguire il VERO (`ore_vere`),
    non il chiesto -- con `ore=1000` le due grandezze non possono coincidere
    per caso, a differenza di una finta che dichiarasse le stesse ore chieste."""
    ha = _FintoHA({"voci": [], "troncato": False, "ore": 168})
    cronaca = _FintaCronaca([])
    await logbook(ha=ha, journal=cronaca, entity="light.cucina", hours=1000,
                   now_ts=NOW)
    from_ts, to_ts, entity = cronaca.chiamate[0]
    assert to_ts == NOW
    assert from_ts == pytest.approx(NOW - 168 * 3600)
    assert entity == "light.cucina"


@pytest.mark.asyncio
async def test_without_a_journal_logbook_answers_anyway():
    """`journal=None` e' legittimo (il dispatcher e' SEMPRE costruibile): si
    perde l'attribuzione, non la risposta -- ma la perdita si DICHIARA (F3,
    onda finale): senza questa nota «HIRIS non l'ha fatto» e «non ho potuto
    controllare» hanno la stessa faccia, nessuna voce con `per_mano_di`."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    occurrence = await logbook(ha=ha, journal=None, entity=None, hours=24,
                           now_ts=NOW)
    assert len(occurrence["voci"]) == 1
    assert "cronaca" in occurrence["nota"]


class _FintaCronacaCheSolleva:
    """Un archivio che non risponde: l'attribuzione e' un di piu', non deve
    togliere all'utente la risposta sulla casa."""

    def list(self, *, from_ts, to_ts, entity=None, limit=200):
        raise RuntimeError("database della cronaca non raggiungibile")


@pytest.mark.asyncio
async def test_a_journal_that_raises_degrades_and_does_not_break():
    """Prima di F3 (onda finale) questo test pinnava SOLO la sopravvivenza --
    cioe' pinnava il silenzio: la risposta arrivava comunque, ma senza dire
    che l'attribuzione non era stata verificata. «HIRIS non l'ha fatto» e
    «non ho potuto guardare la mia cronaca» avevano la stessa faccia. Ora
    pretende anche la dichiarazione, nella `nota`."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    occurrence = await logbook(ha=ha, journal=_FintaCronacaCheSolleva(),
                           entity="light.cucina", hours=24, now_ts=NOW)
    assert len(occurrence["voci"]) == 1
    assert "per_mano_di" not in occurrence["voci"][0]
    assert "cronaca" in occurrence["nota"]


@pytest.mark.asyncio
async def test_an_entry_without_entity_never_matches():
    """Il logbook di Home Assistant produce voci senza `entity_id` -- i
    trigger di automazione, per esempio. Senza entita' non c'e' nessun
    aggancio possibile: il solo controllo temporale prenderebbe un atto su
    un'ALTRA entita' e lo marcherebbe `per_mano_di: HIRIS`, un falso positivo
    travestito da probabilita'."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00", entita=None)],
                   "troncato": False, "ore": 24})
    cronaca = _FintaCronaca([{
        "id": "abc", "quando_ts": 1787569200.0, "origine": "chat",
        "servizio": "climate.set_temperature", "entita": ["climate.soggiorno"],
        "eseguito": True, "genere": "comando", "cambiato": None,
        "errore": None, "avviso": None, "oggetto": None}])
    occurrence = await logbook(ha=ha, journal=cronaca, entity=None, hours=24,
                           now_ts=NOW)
    assert "per_mano_di" not in occurrence["voci"][0]


@pytest.mark.asyncio
async def test_among_several_candidates_the_closest_in_time_is_chosen():
    """`Journal.list` ordina per `quando_ts DESC`: con due tentativi
    ravvicinati sulla stessa entita' il primo della lista non e' detto sia
    il gesto giusto."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    cronaca = _FintaCronaca([
        {"id": "lontano", "quando_ts": 1787569200.0 + 50, "origine": "chat",
         "servizio": "light.turn_on", "entita": ["light.cucina"],
         "eseguito": True, "genere": "comando", "cambiato": None,
         "errore": None, "avviso": None, "oggetto": None},
        {"id": "vicino", "quando_ts": 1787569200.0 + 5, "origine": "chat",
         "servizio": "light.turn_on", "entita": ["light.cucina"],
         "eseguito": True, "genere": "comando", "cambiato": None,
         "errore": None, "avviso": None, "oggetto": None},
    ])
    occurrence = await logbook(ha=ha, journal=cronaca, entity="light.cucina",
                           hours=24, now_ts=NOW)
    assert occurrence["voci"][0]["atto"]["id"] == "vicino"
