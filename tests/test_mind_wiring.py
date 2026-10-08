"""L'osservatore esiste nell'app vera, e nasce DOPO cio' che gli serve.

Meta' di questo file prova il CABLAGGIO e non il comportamento, ed e'
deliberato: questo progetto ha gia' scoperto che uno strumento perfetto e non
cablato e' indistinguibile da uno assente.

L'altra meta' prova i due difetti che il mandato originale del Task 5
avrebbe lasciato nascere (task-5-correzioni.md):

  A. `watch_system` senza nessun chiamante -- codice morto dal primo
     giorno, e la spec §6 diventata una frase falsa;
  A.1. un errore di lettura passato a `watch_system` come lista vuota --
       peggio di non sapere, sapere il falso e scriverlo nell'archivio.
"""
import asyncio
import logging
import re
import sqlite3
import sys
from datetime import UTC, timedelta
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import CasaFinta

from hiris.app import server
from hiris.app.home_space import historian
from hiris.app.home_space.reader import HomeSpace
from hiris.app.home_space.type_vocabulary import REPO_JUDGMENTS
from hiris.app.mind.facts import chronicle_mark
from hiris.app.mind.store import READING_RETENTION_S
from hiris.app.mind.watcher import Watcher
from hiris.app.proxy.entity_cache import _to_minimal
from hiris.app.server import integration_follower, watch_system_conditions
from tests._avvio import SERVER_LOGGER, started_app  # noqa: F401
from tests._casa_sintetica import synthetic_inputs
from tests._contracts import assert_stessa_firma
from tests._mirror_by_id import MirrorById

# --------------------------------------------------------------------------
# Il cablaggio dichiarato dal mandato (task-5-brief.md, Step 1) -- l'archivio
# e l'osservatore, il rubinetto degli stati, la ricostruzione delle condizioni
# prima del primo giro, l'ordine col sapere e con la riparazione d'avvio, la
# chiusura allo spegnimento -- si guarda sull'app avviata, in
# `tests/test_cablaggio_dell_avvio.py`. I lavori periodici si chiedono allo
# schedulatore dell'app avviata (`tests/test_lavori_periodici.py`).
# --------------------------------------------------------------------------

def _job(app, job_id: str):
    """Il lavoro VERO che l'avvio ha registrato sullo schedulatore. Fino al
    03/10/2026 la funzione si ritagliava dal testo di `_on_startup` e si
    eseguiva con le sue variabili libere ricopiate a mano in un dizionario."""
    job = app["scheduler"].get_job(job_id)
    assert job is not None, f"il lavoro {job_id} non e' registrato"
    return job.func


def _server_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == SERVER_LOGGER]


#: Il registro della conservazione: la potatura e' uscita da `server.py`
#: l'08/10/2026 (Tappa 8, Task 6), e scrive col nome del suo modulo.
CONSERVATION_LOGGER = "hiris.app.conservazione"


def _conservation_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == CONSERVATION_LOGGER]


_FINTA = {"finta": (1, "una prova", "DELETE FROM finta WHERE ts < ?")}


class _ArchivioFinto:
    """Un archivio come li cerca `conservazione.archives`: dichiara la sua
    conservazione, sa potarsi e tiene una connessione (da cui si chiede il
    nome del file). La finta deve saper produrre il difetto che sorveglia
    (feedback ricorrente di questo progetto): oltre a tornare un numero da
    `prune()`, deve poter SOLLEVARE a comando, per provare che un archivio
    guasto non ferma gli altri."""

    CONSERVAZIONE = _FINTA

    def __init__(self, path, quanti: int = 0, *, pota_solleva: bool = False):
        self._conn = sqlite3.connect(str(path))
        self._quanti = quanti
        self._pota_solleva = pota_solleva
        self.chiamate = 0

    def prune(self, now):
        self.chiamate += 1
        if self._pota_solleva:
            raise RuntimeError("disco pieno")
        return self._quanti


async def _nightly_with(app, finti: dict, caplog, level):
    """Il lavoro notturno `hiris_retention` dell'app avviata, con gli archivi
    finti aggiunti all'app per la durata della prova (gli archivi veri
    dell'app, appena aperti, non hanno niente da potare)."""
    with mock.patch.dict(app, finti), \
            caplog.at_level(level, logger=CONSERVATION_LOGGER):
        await _job(app, "hiris_retention")()


def _lines_about(caplog, name: str) -> list[str]:
    return [line for line in _conservation_lines(caplog) if name in line]


@pytest.mark.asyncio(loop_scope="module")
async def test_la_potatura_logga_il_numero_vero_di_righe(started_app, caplog, tmp_path):
    """Il lavoro notturno (Tappa 8, Task 6) dice quale archivio ha potato e
    quante righe: il numero e' quello che `prune()` ha tornato, non un
    letterale. Fino all'08/10/2026 la riga era quella del solo grezzo
    (`cervello: N cambi oltre i 22 giorni`): adesso la finestra di ogni
    archivio sta nella sua dichiarazione, e si legge da `/api/health`."""
    finto = _ArchivioFinto(tmp_path / "finto.db", quanti=5)

    await _nightly_with(started_app, {"finto": finto}, caplog, logging.INFO)

    assert finto.chiamate == 1
    assert _lines_about(caplog, "finto.db") == [
        "conservazione: finto.db, 5 righe oltre la finestra sono uscite"]


@pytest.mark.asyncio(loop_scope="module")
async def test_la_potatura_non_logga_niente_quando_non_pota_niente(started_app, caplog, tmp_path):
    """`if removed:` -- una notte senza niente da potare non deve produrre
    una riga di log vuota di significato.

    Mutazione ESEGUITA (08/10/2026, su `conservazione.nightly`): `if
    removed:` -> `if True:` -- rossa."""
    finto = _ArchivioFinto(tmp_path / "finto.db", quanti=0)

    await _nightly_with(started_app, {"finto": finto}, caplog, logging.INFO)

    assert finto.chiamate == 1
    assert _conservation_lines(caplog) == []


@pytest.mark.asyncio(loop_scope="module")
async def test_un_archivio_guasto_non_ferma_gli_altri(started_app, caplog, tmp_path):
    """Un errore di `prune()` alle tre di notte si cattura, si dice quale
    archivio e perche', e gli archivi dopo di lui si potano lo stesso: e'
    igiene, e un disco che non collabora su un archivio non deve lasciar
    crescere tutti gli altri.

    Mutazione ESEGUITA (08/10/2026): `continue` -> `raise` nella rete di
    `conservazione.nightly` -- rossa (`RuntimeError: disco pieno` esce dal
    lavoro e il secondo archivio non si pota)."""
    guasto = _ArchivioFinto(tmp_path / "guasto.db", pota_solleva=True)
    sano = _ArchivioFinto(tmp_path / "sano.db", quanti=2)

    await _nightly_with(started_app, {"guasto": guasto, "sano": sano},
                        caplog, logging.INFO)  # non solleva

    assert (guasto.chiamate, sano.chiamate) == (1, 1)
    [riga] = _lines_about(caplog, "guasto.db")
    assert "disco pieno" in riga
    assert _lines_about(caplog, "sano.db") == [
        "conservazione: sano.db, 2 righe oltre la finestra sono uscite"]


# --------------------------------------------------------------------------
# Correzione A.1: un errore di lettura non e' «tutto a posto». Qui si
# esercita `watch_system_conditions` per davvero, non solo il sorgente.
# --------------------------------------------------------------------------

class _OsservatoreFinto:
    def __init__(self):
        self.chiamate: list[dict] = []

    # `log_entries` senza default, come nel `Watcher` vero (Task 2, «le
    # tracce e il log»): una finta che accettasse un default nasconderebbe
    # esattamente il difetto che quel parametro esiste per impedire, vedi il
    # docstring di `watcher.py::watch_system`.
    def watch_system(self, *, problems, integrations, log_entries):
        self.chiamate.append({"problemi": problems, "integrazioni": integrations,
                              "voci_di_log": log_entries})
        return len(problems) + len(integrations) + len(log_entries)


#: I comandi delle due letture di sistema, come il client vero li manda:
#: `problems()` -> `repairs/list_issues`, `system_log()` -> `system_log/list`
#: (letti in `proxy/ha_client.py`). Le integrazioni non si leggono: arrivano
#: dall'iscrizione `config_entries/subscribe` (Tappa 2, Task 7), qui
#: `_announced`.
_PROBLEMS = "repairs/list_issues"
_LOG = "system_log/list"

#: Il rifiuto che Home Assistant manda quando il gestore di un comando
#: solleva un'eccezione qualunque: `websocket_api/connection.py`,
#: `ActiveConnection.async_handle_exception` -- `ERR_UNKNOWN_ERROR`
#: («unknown_error») e il messaggio «Unknown error» (letto sul tag `2026.9.4`
#: il 03/10/2026).
_UNKNOWN_ERROR = {"code": "unknown_error", "message": "Unknown error"}

#: I due modi in cui una lettura non riesce davvero: Home Assistant tace, o
#: risponde con un rifiuto. Prima del 03/10/2026 la finta tornava a mano
#: `{"errore": "Home Assistant non ha risposto"}`, cioe' solo il primo.
_FAILURES = {"silenzio": lambda command: {"silence": {command}},
             "rifiuto": lambda command: {"refuse": {command: _UNKNOWN_ERROR}}}


def _system_house(problems, integrations, log_entries=(), **faults) -> CasaFinta:
    """La casa sintetica col client vero sopra (`scripts/casa_finta.py`), con
    i problemi, le integrazioni e le voci di log dati qui.

    Fino al 03/10/2026 era `_ClienteFinto`, che imitava a mano `problems()`,
    `read_registries()` e `system_log()` e ne restituiva gli esiti gia'
    tradotti: la traduzione dal messaggio grezzo (e il guasto come busta) non
    era provata. Qui gli ingressi sono cio' che Home Assistant manda, e la
    busta del guasto la costruisce il client vero (`faults`: `silence=` o
    `refuse=` della casa finta)."""
    inputs = synthetic_inputs()
    inputs["problems"] = {"problemi": list(problems)}
    inputs["registries"]["integrazioni"] = list(integrations)
    inputs["system_log"] = {"voci": list(log_entries)}
    return CasaFinta(inputs, **faults)


def _announced(app: dict, integrations) -> dict:
    """L'elenco iniziale dell'iscrizione alle integrazioni, nella forma di
    Home Assistant, passato all'ascoltatore che l'avvio iscrive: e' cosi' che
    le integrazioni arrivano in `app["ha_integrations"]`."""
    integration_follower(app)([{"type": None, "entry": row} for row in integrations])
    return app


def _asked(house: CasaFinta) -> list[str]:
    """I comandi che il giro ha chiesto, nell'ordine."""
    return [command for command, _extra in house.calls]


def test_the_fake_observer_matches_watcher_watch_system():
    """Il revisore indipendente ha provato dal vivo che un default aggiunto
    su UN SOLO lato (`log_entries: list[dict] | None = None` sulla finta)
    lasciava la suite verde: la regola per cui quel parametro non ha un
    default sul `Watcher` vero era protetta solo dalla prosa del docstring,
    non da nessuna prova. `assert_stessa_firma` confronta anche i default
    dei keyword-only (`tests/_contracts.py`, punto 3): e' la guardia
    giusta.

    Mutazione: dare a `_OsservatoreFinto.watch_system` un default
    `log_entries=None` -- il test torna rosso.
    """
    assert_stessa_firma(Watcher.watch_system, _OsservatoreFinto.watch_system,
                        nome="Watcher.watch_system")


# Qui stavano due guardie di firma (`HAClient.read_registries` e
# `HAClient.system_log` contro `_ClienteFinto`): la finta e' uscita il
# 03/10/2026, e con lei le guardie -- il client delle prove E' `HAClient`.


def test_guarda_condizioni_chiama_guarda_sistema_quando_le_due_letture_riescono():
    """Mutazione ESEGUITA (03/10/2026, Tappa 2, Task 12): in
    `HAClient.problems()` il filtro delle ignorate rovesciato (`and
    p.get("ignored")`) -- rossa (`assert 1 == 2`: il problema non arriva
    all'osservatore). La finta di prima restituiva l'esito gia' tradotto, e
    quella traduzione non la guardava."""
    osservatore = _OsservatoreFinto()
    app = _announced({"watcher": osservatore}, [{"entry_id": "y", "state": "not_loaded"}])
    house = _system_house([{"domain": "hue", "issue_id": "x"}], [])

    esito = asyncio.run(watch_system_conditions(app, house))

    assert esito == 2
    assert len(osservatore.chiamate) == 1
    assert osservatore.chiamate[0]["problemi"] == [{"domain": "hue", "issue_id": "x"}]
    assert osservatore.chiamate[0]["integrazioni"] == [{"entry_id": "y", "state": "not_loaded"}]


@pytest.mark.parametrize("failure", sorted(_FAILURES))
def test_un_errore_di_problemi_salta_il_giro_per_intero(failure):
    """La prova per mutazione (task-5-correzioni.md, punto A.1): con
    `problems()` che non riesce, `watch_system` non viene chiamato. La
    mutazione (passare `[]` invece di saltare il giro) e' stata provata a
    mano durante l'implementazione e fa arrossire questa prova -- non e'
    un'affermazione a vuoto.

    Dal 03/10/2026 il guasto e' quello vero, nei due modi in cui arriva (il
    silenzio e il rifiuto di Home Assistant), e la busta la fa il client. E il
    giro si salta PRIMA delle altre due letture: `house.calls` lo dice."""
    osservatore = _OsservatoreFinto()
    app = _announced({"watcher": osservatore}, [])
    house = _system_house([], [], **_FAILURES[failure](_PROBLEMS))

    esito = asyncio.run(watch_system_conditions(app, house))

    assert esito is None
    assert osservatore.chiamate == []
    assert _asked(house) == [_PROBLEMS]


def test_le_integrazioni_non_ancora_annunciate_saltano_il_giro_per_intero():
    """Identico per le integrazioni: finche' l'iscrizione non ha mandato
    l'elenco iniziale non c'e' una lista da passare -- una lista vuota
    chiuderebbe ogni integrazione gia' rotta come se si fosse appena risolta.
    Fino al Task 7 (03/10/2026) il guasto era `read_registry("integrazioni")`
    che rendeva la busta; adesso il giro non le legge piu'.

    Mutazione ESEGUITA (03/10/2026, Task 7): in `watch_system_conditions`
    `app.get("ha_integrations")` diventato `app.get("ha_integrations", [])`
    -- rossa (`assert 0 is None`: il giro gira sulle integrazioni vuote)."""
    osservatore = _OsservatoreFinto()
    app = {"watcher": osservatore}
    house = _system_house([], [])

    esito = asyncio.run(watch_system_conditions(app, house))

    assert esito is None
    assert osservatore.chiamate == []
    assert _LOG not in _asked(house)


@pytest.mark.parametrize("failure", sorted(_FAILURES))
def test_a_broken_log_read_skips_the_round_entirely(failure):
    """Stessa disciplina di `test_un_errore_di_problemi_salta_il_giro_per_intero`,
    estesa alla terza lettura (Task 2, «le tracce e il log»): se
    `system_log()` non riesce, `watch_system` non viene chiamato -- un
    registro non letto trattato come vuoto chiuderebbe ogni voce di log gia'
    aperta al secondo giro di isteresi.

    Mutazione: togliere il controllo `if "errore" in log_report` da
    `watch_system_conditions` -- `log_entries` diventa `[]` (nessuna voce
    nel report d'errore) e il giro NON si salta piu': il test torna rosso
    su `assert esito is None` (diventa `0`, il conteggio di
    `_OsservatoreFinto.watch_system` su tre liste vuote).

    Mutazione ESEGUITA (03/10/2026, Tappa 2, Task 12), lo stesso difetto un
    piano piu' sotto: in `HAClient.system_log()` il guasto reso come
    `{"voci": []}` -- rossa nei due casi (`assert 0 is None`).
    """
    osservatore = _OsservatoreFinto()
    # Le integrazioni annunciate: senza, il giro si salterebbe PRIMA di
    # leggere il registro di errori, e la prova sarebbe verde a vuoto.
    app = _announced({"watcher": osservatore}, [])
    house = _system_house([], [], **_FAILURES[failure](_LOG))

    esito = asyncio.run(watch_system_conditions(app, house))

    assert esito is None
    assert osservatore.chiamate == []


def test_senza_osservatore_non_scrive_niente():
    """Un `app` senza `"watcher"` (avvio a meta', o un test che non lo
    costruisce): il giro tace invece di sollevare -- e non chiede niente a
    Home Assistant."""
    house = _system_house([], [])

    esito = asyncio.run(watch_system_conditions({}, house))

    assert esito is None
    assert house.calls == []


# --------------------------------------------------------------------------
# Correzione punto 2 (task-5-fix-brief.md): se il fuso non si legge, quel
# giorno non viene aggregato MAI PIU' -- `fuso` e `ieri` erano calcolati
# FUORI dal try di `_aggrega_ieri`. Due correzioni distinte: (a) il minimo,
# le due righe dentro il try; (b) la cura vera, la riaggregazione
# incondizionata degli ultimi due giorni pieni all'avvio.
# --------------------------------------------------------------------------

class _ArchivioCasaCheSolleva:
    """`reference_frame()` che solleva -- la sua query SQL, dice il
    mandato, non e' protetta: qui si simula il guasto vero, non solo
    l'assenza di `home_space_store`."""

    def reference_frame(self):
        raise RuntimeError("sqlite del sistema di riferimento irraggiungibile")


# Se `HomeSpace.reference_frame` cambia firma, questa riga cade invece
# di lasciare che il finto imiti un contratto che non esiste piu'.
assert_stessa_firma(HomeSpace.reference_frame, _ArchivioCasaCheSolleva.reference_frame,
                     nome="reference_frame")


@pytest.mark.asyncio(loop_scope="module")
async def test_l_aggregazione_notturna_logga_col_prefisso_cervello_anche_se_il_fuso_non_si_legge(
        started_app, caplog):
    """Punto 2(a): se `reference_frame()` solleva, il warning
    contestualizzato ('cervello: ...') deve partire comunque -- non finire
    nel registro di apscheduler senza prefisso, cosa che succede quando
    `fuso`/`ieri` sono calcolati FUORI dal try.

    L'assert e' sul messaggio preciso, non sul solo prefisso: un errore
    diverso inghiottito dallo stesso `except` (un `NameError`, un refuso)
    produrrebbe anche lui un messaggio che inizia per 'cervello:'.

    Fino al 03/10/2026 la funzione si ritagliava dal testo e si eseguiva con
    le sue variabili libere ricopiate a mano; adesso gira il lavoro
    `hiris_mind_aggregation` dell'app avviata, con l'anagrafe sostituita.

    Mutazione ESEGUITA (03/10/2026): la riga del fuso spostata FUORI dal
    try -- rossa (`RuntimeError` esce dal lavoro)."""
    with mock.patch.dict(started_app, {"home_space_store": _ArchivioCasaCheSolleva()}), \
            caplog.at_level(logging.WARNING, logger=SERVER_LOGGER):
        await _job(started_app, "hiris_mind_aggregation")()  # non deve sollevare

    assert any(
        "cervello: aggregazione notturna fallita (RuntimeError: sqlite del "
        "sistema di riferimento irraggiungibile)" in line
        for line in _server_lines(caplog))


@pytest.mark.asyncio
async def test_l_aggregazione_notturna_ARRIVA_al_resoconto_di_ieri(tmp_path, caplog):
    """**Il giro della notte, eseguito fino in fondo.**

    Nessuna prova lo eseguiva fino al resoconto: quella sopra solleva alla
    prima riga. E il corpo e' tutto dentro un `except Exception` che logga e
    basta -- un nome che non esiste piu' (un `build_balances` dimenticato
    dopo la sua uscita, il 01/10/2026) diventerebbe un `NameError` ogni notte,
    inghiottito, e nessun resoconto nascerebbe senza che niente diventi rosso.

    Dal 03/10/2026 gira il lavoro VERO dell'app avviata (un'app sua: scrive
    un resoconto nel suo archivio), sulla casa sintetica -- con l'anagrafe
    vera, che la prova di prima sostituiva con `None`. La casa congelata non
    ha statistiche: l'anagrafe e' tolta per la durata del giro, come prima,
    perche' `_report_ingredients` non le chieda; e la riparazione d'avvio e'
    spenta, perche' il resoconto di ieri lo scriva il giro e non lei.

    Mutazione ESEGUITA (03/10/2026): rimessa la chiamata
    `await build_balances(ha_client, ...)` prima di `_report_ingredients` --
    rossa (il resoconto di ieri non c'e', e il log dice `NameError`).
    """
    from tests._avvio import started_with

    async def _no_repair(app, ha_client, **kwargs):
        """La riparazione d'avvio scriverebbe gia' ieri e l'altro ieri: qui
        si guarda cio' che scrive il giro della notte, e lui solo."""

    with mock.patch.object(server, "reaggregate_last_two_days", _no_repair):
        async with started_with(tmp_path) as app:
            assert app["observations"].reports(limit=5) == []
            with mock.patch.dict(app, {"home_space_store": None}), \
                caplog.at_level(logging.INFO, logger=SERVER_LOGGER):
                await _job(app, "hiris_mind_aggregation")()
            ieri = (historian.today(None) - timedelta(days=1)).isoformat()
            avvisi = [r.getMessage() for r in caplog.records
                      if r.name == SERVER_LOGGER and r.levelno >= logging.WARNING]
            assert not avvisi, avvisi
            assert [r["giorno"] for r in app["observations"].reports(limit=5)] == [ieri]


def test_riaggrega_gli_ultimi_due_giorni_rifa_esattamente_ieri_e_l_altro_ieri(tmp_path):
    """Punto 2(b), la cura vera: all'avvio si riaggregano gli ultimi due
    giorni pieni (oggi escluso, che non e' ancora finito) -- non 'i giorni
    senza oggetti' (un giorno senza oggetti e' un esito legittimo, vedi il
    mandato). Si popola il grezzo di QUATTRO giorni, OGGI compreso, e si
    verifica che solo i due piu' recenti FRA I FINITI vengano scritti come
    oggetti. Qui `ha_client=_repair_house()`, il client vero sulla casa
    sintetica (vedi il suo docstring): senza anagrafe non gli si chiede
    niente, quindi nessun soggetto fallisce e la riparazione gira per intero come se
    fosse incondizionata. Deliberatamente non e' `ha_client=None`: con
    `None`, `build_companions` chiamerebbe `None.related(...)`,
    prenderebbe `AttributeError`, la CONTERREBBE e conterebbe ogni soggetto
    come fallito -- il contrario di "incondizionata" (correzione del
    CRITICAL, grilletto-brief.md).

    Il giorno di oggi va seminato per davvero (cablaggio-pulizia-brief.md,
    punto 1: sesta ricomparsa del difetto n.1) -- prima di questa riga il
    test lasciava «oggi» senza niente da trovare, e la mutazione `for delta
    in (2, 1)` -> `(2, 1, 0)` (aggregare anche il giorno ancora in corso)
    restava verde perche' nessun assert la distingueva. Con `light.oggi`
    seminato, quella mutazione scrive un oggetto per "2026-08-24" e
    l'uguaglianza sotto arrossisce per davvero.

    Nessun `from ... import reaggregate_last_two_days` in cima al
    file: se la funzione non esistesse ancora, l'errore deve fermare SOLO
    questo test (AttributeError a questa riga), non far fallire la
    collection dell'intero file -- la lezione del giro precedente."""
    from datetime import datetime, timedelta

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=UTC)
        for delta, soggetto in ((3, "vecchio"), (2, "l_altro_ieri"),
                                (1, "ieri"), (0, "oggi")):
            quando = (oggi - timedelta(days=delta)).replace(hour=10)
            # Dentro lo scope: dal 05/10/2026 si eredita solo chi e' guardato.
            archivio.decide_scope(f"light.{soggetto}", inside=True, reason="prova",
                                  author="observer")
            archivio.record(quando_ts=quando.timestamp(), source="entita",
                            subject=f"light.{soggetto}", da="off", a="on")

        asyncio.run(server.reaggregate_last_two_days(
            {"home_space_store": None, "observations": archivio,
             "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS},
            ha_client=_repair_house(),
            now=lambda tz: oggi.astimezone(tz)))

        giorni_scritti = {o["giorno"] for o in _cronaca_intera(archivio)}
        assert giorni_scritti == {"2026-08-22", "2026-08-23"}
        # Esplicito, non solo dedotto dall'uguaglianza sopra: oggi
        # ("2026-08-24") non deve avere NESSUN oggetto, nonostante il grezzo
        # per costruirlo ci sia.
        assert ((archivio.report("2026-08-24") or {}).get("cronaca") or []) == []

        # Idempotente (`replace_day`, non un doppio inserimento): un
        # secondo giro non deve raddoppiare gli oggetti dei due giorni.
        #
        # **Si confronta cio' che c'e', non un numero fisso.** Fino al
        # 10/09/2026 la riga diceva `== 2`, e quel numero e' cambiato per una
        # ragione giusta: `light.vecchio` e' acceso dal giorno 21 e non si e'
        # piu' mosso, quindi da quando l'aggregazione semina cio' che era gia'
        # in corso a mezzanotte compare -- correttamente -- in entrambi i
        # giorni. Un conteggio fisso avrebbe fatto passare per regressione un
        # difetto riparato.
        prima = _cronaca_intera(archivio)
        asyncio.run(server.reaggregate_last_two_days(
            {"home_space_store": None, "observations": archivio,
             "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS},
            ha_client=_repair_house(),
            now=lambda tz: oggi.astimezone(tz)))
        dopo = _cronaca_intera(archivio)

        def senza_id(oggetti):
            return sorted(({k: v for k, v in o.items() if k != "id"} for o in oggetti),
                          key=lambda o: (o["giorno"], o["chi"]))

        assert senza_id(dopo) == senza_id(prima)
        assert {o["chi"] for o in dopo} == {"light.vecchio", "light.l_altro_ieri",
                                                     "light.ieri"}
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_la_riparazione_di_avvio_riceve_home_space_store_gia_costruito(tmp_path):
    """La sorveglianza per COMPORTAMENTO del punto 1 (CRITICAL,
    cancello-rilascio-brief.md): quando la riparazione gira per davvero, il
    collaboratore che le serve per leggere il fuso della casa
    (`home_space_store`, non `None`) e' gia' li' -- e l'anagrafe e' gia'
    LETTA, non solo costruita.

    Fino al 03/10/2026 la prova ritagliava dal testo di `_on_startup` la
    fetta fra la creazione dell'anagrafe e la riparazione, e la eseguiva con
    doppi. Adesso l'avvio gira davvero (`tests/_avvio.py::started_with`, sulla
    casa sintetica), con la riparazione sostituita da una spia che registra
    cosa ha ricevuto. (Che l'anagrafe e il sapere esistano gia' in `app` lo
    guarda anche `test_cablaggio_dell_avvio.py`; questa guarda che l'anagrafe
    sia PIENA e sia quella dell'app.)

    Mutazione ESEGUITA (03/10/2026, sull'avvio vero): la riparazione (col
    suo try/except) spostata sopra `await rebuild(...)` dell'anagrafe --
    rossa («la riparazione ha ricevuto un'anagrafe vuota»)."""
    from tests._avvio import started_with

    ricevuto: dict = {}

    async def _spia(app, ha_client, **kwargs):
        casa = app.get("home_space_store")
        ricevuto["home_space_store"] = casa
        ricevuto["anagrafe"] = casa.read() if casa is not None else None

    with mock.patch.object(server, "reaggregate_last_two_days", _spia):
        async with started_with(tmp_path) as app:
            assert ricevuto.get("home_space_store") is not None
            assert isinstance(ricevuto["home_space_store"], server.HomeSpace)
            assert ricevuto["home_space_store"] is app["home_space_store"]
    # **E l'anagrafe dev'essere gia' LETTA, non solo costruita.** Misurato
    # dal vivo il 10/09/2026 sulla v3.24.0: la riparazione girava prima di
    # `rebuild`, quindi leggeva una casa vuota -- e `build_balances`
    # (uscito il 01/10/2026) non trovava un solo candidato: i due giorni
    # riparati all'avvio nascevano SENZA bilancio. Oggi a leggerla e'
    # `_report_ingredients`, che su una casa vuota non trova nessun
    # dispositivo e quindi nessuna ricetta: il resoconto riparato
    # nascerebbe senza misure.
    assert ricevuto["anagrafe"].get("entita"), (
        "la riparazione ha ricevuto un'anagrafe vuota: gira prima di rebuild")


# Qui stava `test_se_la_riaggregazione_solleva_l_avvio_prosegue`, che
# ritagliava dal testo il try/except intorno alla riparazione d'avvio. E'
# uscito il 03/10/2026: la stessa cosa la guarda, sull'avvio vero,
# `tests/test_cablaggio_dell_avvio.py::
# test_a_failing_startup_repair_does_not_stop_startup` -- la riparazione
# solleva, l'avvio arriva in fondo, e il registro porta quel preciso errore
# col prefisso «cervello:» (l'ultima parte e' stata aggiunta li', perche'
# questa la guardava e quella no).


#: I sapere aperti dalle prove, chiusi alla fine della sessione.
_SAPERI_APERTI = []


@pytest.fixture(scope="module", autouse=True)
def _chiusura_saperi():
    yield
    for sapere in _SAPERI_APERTI:
        sapere.close()
    _SAPERI_APERTI.clear()


def _cronaca_intera(archivio):
    """Le voci di cronaca di tutti i giorni archiviati.

    Sostituisce `archivio.facts(limit=...)`: lo strato degli oggetti e' uscito
    (spec §13, 15/09/2026) e gli episodi vivono dentro i resoconti.
    """
    return [{**v, "giorno": r["giorno"]}
            for r in archivio.reports(limit=50) for v in (r.get("cronaca") or [])]


def _repair_house() -> CasaFinta:
    """Il client che la riparazione d'avvio riceve: la casa sintetica col
    client vero sopra (`scripts/casa_finta.py`).

    Era `_ClienteStatistiche`, una finta che imitava `hourly_statistics` e
    rispondeva `{"serie": {}}` a qualunque domanda (prima ancora
    `_ClienteLegami`, uscita coi comprimari il 15/09/2026). `_report_
    ingredients` chiede le statistiche solo quando c'e' un'anagrafe -- e in
    queste prove `home_space_store` e' `None`, quindi non ci arriva mai.
    Adesso quella promessa e' sorvegliata invece di essere scritta: gli
    ingressi sintetici NON servono `recorder/statistics_during_period`, e una
    domanda di statistiche solleverebbe `UnservedCommand` (che non e' un
    `Exception`: nessun `except` del giro la inghiotte). `None` resta
    escluso per la stessa ragione di prima: non e' un client, e un
    `AttributeError` finirebbe dietro un `except`.

    Mutazione ESEGUITA (03/10/2026, Tappa 2, Task 12): in `server.py::
    _report_ingredients` una richiesta di `hourly_statistics` PRIMA della
    guardia sull'anagrafe -- rossa (`UnservedCommand: la casa finta non serve
    recorder/statistics_during_period`); con la finta di prima era verde.
    """
    return CasaFinta(synthetic_inputs())


def _sapere(tmp_path):
    """Un sapere vero, aperto e vuoto.

    Le prove di cablaggio costruiscono un'app a mano: se quella e' piu' povera
    di quella che gira davvero, difendono un cablaggio che non esiste. La
    riparazione e il recupero leggono le ricette dal sapere
    (`_report_ingredients`), e un'app senza sapere non e' una semplificazione
    -- e' un'altra app.

    **Vuoto, e non seminato come all'avvio** (01/10/2026). Fino a quel giorno
    qui si seminavano le direzioni dell'energia, uscite dal seme. Il seme che
    resta (significati, attributi, giudizi) non scrive ricette, e nessuna
    prova di questo file le legge dal sapere: provato togliendolo, le 67 prove
    del file restano verdi. Seminarlo qui sarebbe una fedelta' che non regge
    niente.
    """
    from hiris.app.mind.knowledge import KnowledgeStore

    sapere = KnowledgeStore(str(tmp_path / "sapere.db"))
    # Si annota per chiuderlo a fine sessione: quindici prove che aprono un
    # sqlite e non lo chiudono lasciano quindici descrittori aperti, e su
    # Windows il file resta bloccato (revisione indipendente, 13/09/2026).
    _SAPERI_APERTI.append(sapere)
    return sapere


# --------------------------------------------------------------------------
# Task 4 di «le tracce e il log»: l'evento segna, la cadenza breve raccoglie
# l'errore. Qui il comportamento (`watch_automation_outcomes` esercitata per
# davvero con dei finti); che l'avvio iscriva l'evento all'osservatore lo
# prova l'app avviata
# (`tests/test_cablaggio_dell_avvio.py::test_the_automation_event_marks_the_automation`).
# --------------------------------------------------------------------------

class _FakeAutomationWatcher:
    """Un `Watcher` finto per `watch_automation_outcomes`: `marked` e' cio'
    che torna `marked_automations()` (l'ORDINE e' quello dato qui, non
    ordinato da capo -- il vero `Watcher.marked_automations` ordina da solo,
    provato altrove in `tests/test_mind_watcher.py`); ogni chiamata a
    `watch_automation_outcome` si ricorda, senza toccare un archivio vero.
    `result` e' cio' che quella chiamata deve tornare -- di default `True`,
    cosi' il conteggio di ritorno di `watch_automation_outcomes` combacia
    col numero di tracce forgiate, senza dover replicare qui il giudizio
    vero (aperto/chiuso/ignorato) che appartiene al `Watcher` reale e che
    questo file NON riprova."""

    def __init__(self, marked, *, result=True):
        self._marked = list(marked)
        self.calls: list[tuple] = []
        self._result = result

    def marked_automations(self):
        return list(self._marked)

    def watch_automation_outcome(self, entity_id, outcome, *, title=None):
        self.calls.append((entity_id, outcome, title))
        return self._result


#: Il comando che `HAClient.traces()` manda per ogni automazione
#: (`proxy/ha_client.py`): `trace/list` con `{"domain": "automation",
#: "item_id": <id>}`.
_TRACE_LIST = "trace/list"


def _traces_house(traces_by_automation_id) -> CasaFinta:
    """Il client vero di Home Assistant (`scripts/casa_finta.py`) con le
    tracce di `traces_by_automation_id`: **l'id di CONFIGURAZIONE** -- non
    l'`entity_id` -- mappato alle righe che `trace/list` manda.

    **La chiave e' l'id di configurazione dal Task 6**, e non e' un dettaglio
    della finta: e' la proprieta' che questi test sorvegliano. Home Assistant
    archivia le tracce sotto `automation.<id della configurazione>` (catena
    verificata sui tag `2024.7.0` e `2026.9.0`, nel docstring di
    `HAClient.traces()`), quindi un collettore che passasse
    l'`entity_id` -- come faceva la prima stesura -- non troverebbe nessuna
    traccia qui, esattamente come non ne trova nessuna sulla casa vera.

    **Un id che non c'e' rende una lista VUOTA**, perche' e' cio' che Home
    Assistant fa: `trace/websocket_api.py::websocket_trace_list` ricompone
    `key = f"{domain}.{item_id}"` e `trace/util.py::_get_debug_traces` torna
    `[]` quando `hass.data[DATA_TRACE].get(key)` non trova niente (letto sul
    tag `2026.9.4` il 03/10/2026). Fino al 03/10/2026 la finta
    (`_FakeTracesClient`) rendeva un guasto, «per non nascondere un errore di
    battitura»: era un caso che Home Assistant non produce. L'errore di
    battitura lo prende adesso `_traces_asked`, che dice quale id e' stato
    chiesto.

    Le righe passano dal client vero: la busta `{"tracce": ...}` la fa lui
    (`HAClient._trace_list`), non la prova.

    Mutazione ESEGUITA (03/10/2026, Tappa 2, Task 12), un difetto che la
    finta di prima non poteva vedere perche' sostituiva il client: in
    `HAClient.automation_traces()` (uscito il 04/10/2026: oggi le tracce si
    leggono con `HAClient.traces()`) l'`item_id` mandato come
    `f"automation.{automation_id}"` -- rosse sei prove (`assert 0 == 3`,
    `['automation.1771346155970'] == ['1771346155970']`, ...)."""
    traces = dict(traces_by_automation_id)

    def _trace_list(extra):
        assert extra.get("domain") == "automation", extra
        return list(traces.get(extra.get("item_id"), []))

    return CasaFinta(synthetic_inputs(), answers={_TRACE_LIST: _trace_list})


def _traces_asked(house: CasaFinta) -> list[str]:
    """Gli id di configurazione chiesti a `trace/list`, nell'ordine."""
    return [extra["item_id"] for command, extra in house.calls if command == _TRACE_LIST]


class _FakeMirror(MirrorById):
    """Lo specchio dello stato, ridotto a cio' che il collettore gli chiede:
    `loaded` e `all_states()`.

    Le righe le costruisce `proxy/entity_cache._to_minimal`, la proiezione
    VERA, a partire da stati grezzi veri -- non a mano. Se un domani la
    proiezione smettesse di portare `automation_id`, questi test
    arrossirebbero invece di continuare a provare una finta che nessuno
    produce piu'.

    Un `entity_id` mappato a `None` e' un'automazione **senza `id:` nella
    configurazione** (YAML scritto a mano): esiste, e' viva, e non e'
    risolvibile -- `capability_attributes` torna `None` quando `unique_id is
    None` (tag `2024.7.0` e `2026.9.0`), quindi nello stato vero non c'e'
    proprio nessun `attributes["id"]`.
    """

    loaded = True

    def __init__(self, config_id_by_entity, names=None):
        self._rows = []
        for entity_id, config_id in config_id_by_entity.items():
            attributes = {"friendly_name": (names or {}).get(entity_id, entity_id)}
            if config_id is not None:
                attributes["id"] = config_id
            self._rows.append(_to_minimal(
                {"entity_id": entity_id, "state": "on", "attributes": attributes}))

    def all_states(self):
        return list(self._rows)


def test_fake_automation_watcher_matches_watcher_marked_automations():
    assert_stessa_firma(
        Watcher.marked_automations, _FakeAutomationWatcher.marked_automations,
        nome="Watcher.marked_automations")


def test_fake_automation_watcher_matches_watcher_watch_automation_outcome():
    assert_stessa_firma(
        Watcher.watch_automation_outcome,
        _FakeAutomationWatcher.watch_automation_outcome,
        nome="Watcher.watch_automation_outcome")


def test_without_a_watcher_the_traces_round_returns_none():
    result = asyncio.run(server.watch_automation_outcomes({}, _traces_house({})))
    assert result is None


def test_no_marked_automation_reads_no_trace():
    """`marked_automations()` vuota: il giro non deve chiedere
    nessuna traccia, nemmeno una connessione -- non c'e' niente da rileggere.
    (Giro di correzioni, rilievo 6, secondo punto: le chiamate si
    registrano -- oggi `house.calls` della casa finta, letta da
    `_traces_asked` -- quindi questa promessa e' davvero sorvegliata, non
    solo scritta nel docstring.)"""
    watcher = _FakeAutomationWatcher([])
    client = _traces_house({})
    result = asyncio.run(server.watch_automation_outcomes({"watcher": watcher}, client))
    assert result == 0
    assert watcher.calls == []
    assert _traces_asked(client) == []
    assert client.connections == []


def test_every_trace_of_a_marked_automation_is_forwarded_in_order():
    """Tre tracce nella stessa risposta, con `run_id` diversi (nuovi al
    cursore): ognuna deve arrivare a `watch_automation_outcome`,
    nell'ordine in cui `traces()` le ha restituite -- l'ordine
    conta (vedi il docstring di `watch_automation_outcomes` per la fonte HA
    che lo garantisce), e questa prova lo sorveglia direttamente
    sull'inoltro, non sul giudizio (quello e' provato su `Watcher` vero,
    non su questo finto).

    Mutazione (verificata eseguendola): `reversed(report.get("tracce") or
    [])` invece dell'ordine diretto -- il test torna rosso sul primo
    elemento di `assert [c[:2] for c in watcher.calls] == [...]`
    (`("automation.luci_sera", "error")` al posto di
    `("automation.luci_sera", "finished")`)."""
    watcher = _FakeAutomationWatcher(["automation.luci_sera"])
    client = _traces_house({
        "1771346155970": [
            {"run_id": "1", "script_execution": "finished"},
            {"run_id": "2", "script_execution": "failed_conditions"},
            {"run_id": "3", "script_execution": "error"},
        ],
    })
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.luci_sera": "1771346155970"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert result == 3
    assert [c[:2] for c in watcher.calls] == [
        ("automation.luci_sera", "finished"),
        ("automation.luci_sera", "failed_conditions"),
        ("automation.luci_sera", "error"),
    ]


def test_the_title_is_the_name_the_house_gives_at_the_outcome():
    """A-18 (Tappa 3, Task 12): il titolo dell'automazione e' il nome che la
    casa da' ADESSO (`House.name`: il `friendly_name` dello specchio), non
    quello che l'evento portava al primo scatto -- un'automazione rinominata
    in Home Assistant si scrive col nome nuovo. Un'automazione che la casa
    sa nominare solo con l'id viaggia senza titolo, come prima.

    Mutazione ESEGUITA (04/10/2026): il titolo sempre `None` (il collettore
    che non chiede alla casa) -- rossa."""
    watcher = _FakeAutomationWatcher(["automation.luci_sera", "automation.senza_nome"])
    client = _traces_house({
        "1771346155970": [{"run_id": "1", "script_execution": "error"}],
        "1771346155971": [{"run_id": "2", "script_execution": "error"}],
    })
    app = {"watcher": watcher, "entity_cache": _FakeMirror(
        {"automation.luci_sera": "1771346155970",
         "automation.senza_nome": "1771346155971"},
        names={"automation.luci_sera": "Luci della sera (rinominata)"})}

    asyncio.run(server.watch_automation_outcomes(app, client))

    assert {c[0]: c[2] for c in watcher.calls} == {
        "automation.luci_sera": "Luci della sera (rinominata)",
        "automation.senza_nome": None}


def test_a_not_triggered_trace_is_not_forwarded():
    """Una traccia il cui `script_execution` non e' una stringa -- il caso
    vero e' una traccia ANCORA IN CORSO (`ActionTrace._script_execution`
    resta `None` finche' `finished()` non viene chiamato, `trace/
    models.py`, tag `2026.9.0`), NON un `not_triggered`: quella, da HA
    2026.7.0 in poi, vale la stringa `"not_triggered"` (verificato alla
    fonte, `automation/__init__.py::_handle_not_triggered`,
    `script_execution_set("not_triggered")`) e passerebbe questo
    controllo -- verrebbe comunque scartata, ma perche' non e' `"error"` ne'
    `"finished"`, dentro `Watcher.watch_automation_outcome`, non qui.

    Mutazione (verificata eseguendola): togliere `if not isinstance(outcome,
    str): continue` -- il test torna rosso su `assert result == 0`
    (tornerebbe `1`: la finta `_FakeAutomationWatcher`, che non discrimina
    l'`outcome` come il `Watcher` vero, riceverebbe comunque `None` e lo
    conterebbe come inoltrato)."""
    watcher = _FakeAutomationWatcher(["automation.x"])
    client = _traces_house({
        "1771346155970": [
            {"run_id": "1", "script_execution": None},
        ],
    })
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.x": "1771346155970"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert result == 0
    assert watcher.calls == []


def test_a_trace_older_than_process_boot_is_not_forwarded():
    """Una traccia con `timestamp.start` precedente all'avvio di QUESTO
    processo (`app["automation_traces_boot_ts"]`, scritto in `_on_startup`)
    e' scattata mentre HIRIS era spento, o in un avvio precedente: non si
    recupera -- stessa disciplina di `watch_system_conditions`, "meglio un
    buco nella storia che una bugia nella storia". `timestamp.start` e' un
    `datetime` di HA serializzato ISO-8601 (`helpers/json.py`,
    `JSONEncoder.default`), letto con `instant_epoch` -- gia' importato in
    `server.py`.

    Mutazione (verificata eseguendola): togliere `if start_ts is not None
    and start_ts < boot_ts: continue` -- il test torna rosso su
    `assert result == 0` (tornerebbe `1`: la traccia di sei anni fa
    aprirebbe comunque un episodio, come se fosse appena successa)."""
    watcher = _FakeAutomationWatcher(["automation.x"])
    client = _traces_house({
        "1771346155970": [
            {"run_id": "1", "script_execution": "error",
             "timestamp": {"start": "2020-01-01T00:00:00+00:00"}},
        ],
    })
    app = {"watcher": watcher, "automation_traces_boot_ts": 1787572800.0,
           "entity_cache": _FakeMirror({"automation.x": "1771346155970"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert result == 0
    assert watcher.calls == []


def test_a_failed_read_for_one_automation_does_not_stop_the_others():
    """Una delle due automazioni segnate non si legge: quella si salta,
    l'altra si legge lo stesso -- e' la disciplina del "parziale tollerato"
    (come `build_companions`), non quella del "tutto o niente" delle tre
    letture di sistema di `watch_system_conditions`.

    Dalla Tappa 2, Task 8 (A-21) le tracce arrivano in una raffica sola
    (`HAClient.traces`), e una chiave che non si legge sta in `non_letti` col
    suo motivo. Qui Home Assistant manda per l'automazione rotta una
    risposta che non e' la lista nuda di `trace/list`: il client vero la
    mette in `non_letti` («risposta in forma inattesa»). Prima la casa finta
    non sapeva far fallire una chiave sola, e la prova usava un client finto
    (`_FakeTracesClient`), uscito con questa conversione.

    Mutazione (verificata eseguendola): `return written` invece di
    `continue` sul ramo della chiave non letta -- interrompe il giro INTERO
    alla prima automazione rotta invece di saltare solo quella. Il test
    torna rosso su `assert result == 1` (tornerebbe `0`: `automation.buona`
    non verrebbe mai raggiunta, `watcher.calls` resterebbe vuota)."""
    watcher = _FakeAutomationWatcher(["automation.rotta", "automation.buona"])

    def _trace_list(extra):
        if extra["item_id"] == "1771346155970":
            return {"non": "una lista nuda"}
        return [{"run_id": "1", "script_execution": "error"}]

    client = CasaFinta(synthetic_inputs(), answers={_TRACE_LIST: _trace_list})
    app = {"watcher": watcher, "entity_cache": _FakeMirror({
        "automation.rotta": "1771346155970",
        "automation.buona": "1771346155971"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert result == 1
    assert [c[:2] for c in watcher.calls] == [("automation.buona", "error")]
    # Il cursore dell'automazione non letta non si tocca: resta quello
    # dell'ultimo giro riuscito (qui: nessuno).
    assert "automation.rotta" not in app["automation_trace_cursors"]


def test_marked_automations_are_read_in_one_connection():
    """A-21 (Tappa 2, Task 8): tre automazioni segnate, UNA connessione per
    giro, con i tre `trace/list` dentro.

    Contato sul codice del 04/10/2026, prima di questa prova: il giro
    chiamava `HAClient.automation_traces` una volta per automazione segnata,
    e ognuna era un `_ws_send` suo -- una connessione WebSocket nuova, con
    handshake e autenticazione -- ogni due minuti; e l'insieme dei segnati
    non si svuota mai (`Watcher.marked_automations`).

    Mutazione (verificata eseguendola): rimettere una lettura per
    automazione dentro il ciclo -- rossa sulle connessioni (`assert 4 ==
    1`)."""
    watcher = _FakeAutomationWatcher(
        ["automation.a", "automation.b", "automation.c"])
    client = _traces_house({
        "1771346155970": [{"run_id": "1", "script_execution": "error"}],
        "1771346155971": [{"run_id": "1", "script_execution": "error"}],
        "1771346155972": [{"run_id": "1", "script_execution": "error"}],
    })
    app = {"watcher": watcher, "entity_cache": _FakeMirror({
        "automation.a": "1771346155970",
        "automation.b": "1771346155971",
        "automation.c": "1771346155972"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert len(client.connections) == 1
    assert client.connections == [("ws", (_TRACE_LIST, _TRACE_LIST, _TRACE_LIST))]
    assert _traces_asked(client) == ["1771346155970", "1771346155971", "1771346155972"]
    assert result == 3
    assert [c[:2] for c in watcher.calls] == [
        ("automation.a", "error"), ("automation.b", "error"), ("automation.c", "error")]


def test_a_silent_batch_writes_nothing_and_keeps_every_cursor(caplog):
    """La raffica intera non parte (Home Assistant muto): nessun fatto, e
    nessun cursore toccato -- per nessuna automazione. E' «non ho potuto
    guardare», non «non e' successo niente».

    Mutazione (verificata eseguendola): togliere il ritorno sul ramo
    `"errore" in report` -- rossa (`KeyError: 'tracce'`)."""
    watcher = _FakeAutomationWatcher(["automation.a", "automation.b"])
    client = CasaFinta(synthetic_inputs(), silence={_TRACE_LIST})
    app = {"watcher": watcher,
           "automation_trace_cursors": {"automation.a": {"vecchio"}},
           "entity_cache": _FakeMirror({
               "automation.a": "1771346155970",
               "automation.b": "1771346155971"})}

    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert result == 0
    assert watcher.calls == []
    assert app["automation_trace_cursors"] == {"automation.a": {"vecchio"}}
    assert any("non lette" in r.getMessage() for r in caplog.records)


def test_traces_are_asked_for_by_configuration_id_not_by_entity_id():
    """La proprieta' che tutta questa fetta esiste per garantire, isolata:
    il collettore riceve un `entity_id` (e' quello che l'evento
    `automation_triggered` porta, ed e' quello che
    `Watcher.marked_automations()` restituisce) e chiede le tracce con l'id
    di CONFIGURAZIONE, risolto dallo specchio.

    Sulla casa vera i due valori non coincidono mai -- l'interfaccia di HA
    genera timbri numerici -- e HA cerca la chiave `automation.<id di
    configurazione>` con un `.get(key)` nudo (`trace/util.py::
    _get_debug_traces`, tag `2024.7.0` e `2026.9.0`): con l'`object_id` non
    si sbaglia UNA traccia, non se ne legge mai nessuna. Qui l'`entity_id` e
    l'id sono deliberatamente diversi, cosi' la differenza si vede.

    Mutazione (verificata eseguendola il 04/10/2026, sulla raffica
    `traces`): `resolved.append((entity_id, entity_id))` invece di
    `(entity_id, automation_id)` -- il test torna rosso su
    `assert _traces_asked(client) == ["1771346155970"]`, che riceve
    `["automation.luci_sera"]`; e anche su `assert result == 1`, che riceve
    `0`, perche' la finta non ha nessuna traccia sotto quella chiave
    (proprio come HA non ne ha).
    """
    watcher = _FakeAutomationWatcher(["automation.luci_sera"])
    client = _traces_house({
        "1771346155970": [{"run_id": "1", "script_execution": "error"}],
    })
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.luci_sera": "1771346155970"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert _traces_asked(client) == ["1771346155970"]
    assert result == 1
    # Il `Watcher` continua a ragionare per `entity_id`: la traduzione serve
    # a Home Assistant, non all'osservatore, che deve poter ricollegare il
    # fatto all'automazione col nome che l'utente vede.
    assert [c[:2] for c in watcher.calls] == [("automation.luci_sera", "error")]


def test_an_unresolvable_automation_is_skipped_without_writing_anything():
    """Un'automazione segnata il cui id non si risolve -- YAML senza `id:`,
    oppure specchio non ancora pronto -- si SALTA: non si chiedono le sue
    tracce (non c'e' niente da chiedere) e soprattutto non si scrive nessun
    fatto. Un id irrisolto e' «non ho potuto guardare», non «non ha mai
    girato»: la distinzione e' la ragione di questa fetta.

    Le altre automazioni proseguono, come per una lettura fallita: e' la
    stessa disciplina del "parziale tollerato".

    Mutazione (verificata eseguendola): ripiegare sull'`object_id` quando la
    risoluzione fallisce (`automation_id = automation_config_id(...) or
    entity_id.partition(".")[2]`) -- il test torna rosso su
    `assert _traces_asked(client) == ["1771346155971"]`, che riceve
    `["scritta_a_mano", "1771346155971"]`: Home Assistant risponderebbe con
    una lista vuota per quella chiave (e la casa finta con lui), cioe' un
    «non ha mai girato» detto di un'automazione che non si e' potuta
    guardare.
    """
    watcher = _FakeAutomationWatcher(
        ["automation.scritta_a_mano", "automation.buona"])
    client = _traces_house({
        "1771346155971": [{"run_id": "1", "script_execution": "error"}],
    })
    app = {"watcher": watcher, "entity_cache": _FakeMirror({
        "automation.scritta_a_mano": None,
        "automation.buona": "1771346155971"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert _traces_asked(client) == ["1771346155971"]
    assert result == 1
    assert [c[:2] for c in watcher.calls] == [("automation.buona", "error")]


def test_an_unresolvable_automation_is_shouted_once_then_whispered(caplog):
    """Un'automazione irrisolvibile lo resta per tutta la vita del processo
    (`marked_automations()` non si svuota mai): un WARNING a ogni cadenza
    sarebbero 720 avvisi al giorno per una condizione che non puo' cambiare a
    caldo -- il rumore sano che seppellisce la rotta, applicato ai log. Il
    fatto non si tace, cambia di livello: WARNING la prima volta per entita',
    DEBUG le successive.

    **Il livello si asserisce, non il testo**: un test che guardasse solo «e'
    stato loggato qualcosa» resterebbe verde con tre WARNING di fila, che e'
    esattamente il difetto.

    Mutazione (verificata eseguendola): togliere `unresolved.add(entity_id)`
    (cioe' non ricordarsi mai di aver gia' segnalato) -- il test torna rosso
    su `assert levels == ["WARNING", "DEBUG", "DEBUG"]`, che riceve
    `["WARNING", "WARNING", "WARNING"]`.
    """
    watcher = _FakeAutomationWatcher(["automation.scritta_a_mano"])
    client = _traces_house({})
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.scritta_a_mano": None})}

    with caplog.at_level(logging.DEBUG, logger="hiris.app.server"):
        for _ in range(3):
            asyncio.run(server.watch_automation_outcomes(app, client))

    levels = [r.levelname for r in caplog.records
              if "non si risolve dallo specchio" in r.getMessage()]
    assert levels == ["WARNING", "DEBUG", "DEBUG"]
    assert _traces_asked(client) == []


def test_an_automation_that_starts_resolving_again_is_shouted_again(caplog):
    """L'altra meta', e la ragione per cui `unresolved` si SVUOTA su
    successo: «la prima volta per entita'» non deve voler dire «una volta
    sola per sempre». Un'automazione che si risolve (inventario arrivato) e
    che domani torna irrisolvibile (HA riavviato, ricarica andata male) e' un
    guasto NUOVO, e deve farsi sentire -- non restare muta perche' mesi fa
    aveva gia' avuto il suo unico WARNING.

    Mutazione (verificata eseguendola): togliere `unresolved.discard(
    entity_id)` dopo la risoluzione riuscita -- il test torna rosso su
    `assert levels == ["WARNING", "WARNING"]`, che riceve
    `["WARNING", "DEBUG"]`.
    """
    watcher = _FakeAutomationWatcher(["automation.luci_sera"])
    client = _traces_house({
        "1771346155970": [{"run_id": "1", "script_execution": "error"}],
    })
    blind = _FakeMirror({"automation.luci_sera": None})
    seeing = _FakeMirror({"automation.luci_sera": "1771346155970"})
    app = {"watcher": watcher, "entity_cache": blind}

    with caplog.at_level(logging.DEBUG, logger="hiris.app.server"):
        asyncio.run(server.watch_automation_outcomes(app, client))   # cieco
        app["entity_cache"] = seeing
        asyncio.run(server.watch_automation_outcomes(app, client))   # risolve
        app["entity_cache"] = blind
        asyncio.run(server.watch_automation_outcomes(app, client))   # cieco di nuovo

    levels = [r.levelname for r in caplog.records
              if "non si risolve dallo specchio" in r.getMessage()]
    assert levels == ["WARNING", "WARNING"]


def test_an_unresolvable_automation_does_not_touch_its_cursor():
    """Il secondo tempo del test qui sopra, e la ragione per cui NON basta
    quello: uno specchio che diventa pronto DOPO -- il caso vero, l'add-on
    appena partito -- non deve trovare il cursore gia' riempito da un giro
    che non ha letto niente.

    Se il giro cieco scrivesse `cursors[entity_id] = set()` (o peggio, un
    insieme parziale), le tracce viste al primo giro utile risulterebbero
    «gia' processate» o «mai viste» in modo arbitrario. Non toccarlo
    significa che il primo giro che risolve davvero vede tutte le tracce
    ancora conservate come nuove.

    Mutazione (verificata eseguendola): azzerare il cursore anche quando non
    si e' letto nulla, cioe' `cursors[entity_id] = set()` subito prima del
    `continue` dell'id irrisolto -- il test torna rosso su
    `assert "automation.luci_sera" not in app.get("automation_trace_cursors",
    {})`.
    """
    watcher = _FakeAutomationWatcher(["automation.luci_sera"])
    client = _traces_house({
        "1771346155970": [{"run_id": "1", "script_execution": "error"}],
    })
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.luci_sera": None})}

    blind_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert blind_round == 0
    assert _traces_asked(client) == []
    assert "automation.luci_sera" not in app.get("automation_trace_cursors", {})

    # Lo specchio arriva: la traccia gia' conservata da HA e' NUOVA per il
    # cursore, e il fatto si scrive adesso invece di essere perso per sempre.
    app["entity_cache"] = _FakeMirror({"automation.luci_sera": "1771346155970"})
    seeing_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert seeing_round == 1
    assert _traces_asked(client) == ["1771346155970"]


# --------------------------------------------------------------------------
# Giro di correzioni, rilievo 1 (CRITICO): il cursore per automazione, e la
# prova che mancava. Qui il `Watcher` e' VERO (non finto): l'idempotenza e'
# una proprieta' del suo stato reale (`_automation_faults`), e una finta che
# torna sempre `True` non la potrebbe mai catturare.
# --------------------------------------------------------------------------

class _CountingStore:
    """Un archivio che conta le scritture senza salvarle: basta a
    verificare CHE non si riscriva una seconda volta, non serve rileggerle
    (quello lo fa gia' `tests/test_mind_watcher.py` sul `Watcher` da
    solo)."""

    def __init__(self) -> None:
        self.count = 0

    def record(self, **kwargs) -> None:
        self.count += 1


def test_rereading_a_fixed_finished_then_error_window_stays_at_one_write():
    """La finestra che il revisore ha misurato scrivere **2 a ogni giro**
    senza cursore: `[finished, error]` fissa (lo stesso `error` non ancora
    espulso da HA, letto insieme a un `finished` PIU' VECCHIO che lo
    precede sempre nello stesso ordine). Senza cursore, ogni giro
    rivedrebbe il `finished` (che non avrebbe niente da chiudere la prima
    volta, ma richiuderebbe l'errore ancora aperto a ogni giro successivo)
    e poi l'`error` (che riaprirebbe). Con il cursore, solo il PRIMO giro
    vede entrambe le tracce come nuove; i giri successivi non ne vedono
    nessuna.

    Mutazione (verificata eseguendola): togliere `if run_id in
    already_seen: continue` -- il test torna rosso su
    `assert second_round == 0` (tornerebbe `2`: il `finished` chiuderebbe
    di nuovo e l'`error` riaprirebbe di nuovo, ogni giro, per sempre)."""
    store = _CountingStore()
    watcher = Watcher(store, now=lambda: 1787572800.0)
    watcher.mark_automation("automation.rotta")
    client = _traces_house({
        "1771346155970": [
            {"run_id": "1", "script_execution": "finished"},
            {"run_id": "2", "script_execution": "error"},
        ],
    })
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.rotta": "1771346155970"})}

    first_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert first_round == 1  # il "finished" iniziale non chiude niente; l'"error" apre
    assert store.count == 1

    second_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert second_round == 0
    assert store.count == 1


def test_rereading_a_fixed_error_then_finished_window_stays_at_two_writes():
    """L'altra finestra fissa misurata dal revisore, ordine opposto: un
    errore che la STESSA finestra di due minuti ha gia' visto guarire
    (`[error, finished]`). Il primo giro scrive DUE volte (apre, poi
    chiude subito nello stesso giro -- un episodio completo, la storia
    vera: «rotto, poi guarito»); senza cursore, ogni giro successivo
    RIAPRIREBBE e richiuderebbe lo stesso episodio gia' concluso -- «una
    bugia nella storia» per un'automazione che in realta' funziona da un
    pezzo.

    Mutazione (verificata eseguendola): togliere `if run_id in
    already_seen: continue` -- il test torna rosso su
    `assert second_round == 0` (tornerebbe `2`: la stessa coppia
    apre/chiude si ripeterebbe a ogni giro)."""
    store = _CountingStore()
    watcher = Watcher(store, now=lambda: 1787572800.0)
    watcher.mark_automation("automation.guarita")
    client = _traces_house({
        "1771346155970": [
            {"run_id": "1", "script_execution": "error"},
            {"run_id": "2", "script_execution": "finished"},
        ],
    })
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.guarita": "1771346155970"})}

    first_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert first_round == 2  # apre e chiude nello stesso giro
    assert store.count == 2

    second_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert second_round == 0
    assert store.count == 2


# --------------------------------------------------------------------------
# Il sapere: i significati entrano da dove le traduzioni si leggono gia'
# --------------------------------------------------------------------------

class _CacheTraduzioni:
    """La finta di `StateTranslations`: un esito etichettato, come il vero."""

    def __init__(self, esito):
        self.esito = esito
        self.letture = 0

    async def read(self, *, ha_version, language):
        self.letture += 1
        return dict(self.esito)


class _CasaConFuso:
    def __init__(self, versione="2026.9.1", lingua="it"):
        self._frame = {"versione_ha": versione, "lingua": lingua}

    def reference_frame(self):
        return dict(self._frame)


def test_i_significati_delle_classi_entrano_nel_sapere_dalle_TRADUZIONI(tmp_path):
    """**Nessuna lettura di rete in piu', e nessuna seconda tabella.**

    Le traduzioni si leggono gia' all'avvio per rendere gli stati: i
    significati delle classi escono da quello stesso dizionario. Misurato il
    12/09/2026: il repo ne scriveva a mano 18 su 62 per `sensor` e zero su 28
    per `binary_sensor`.

    Mutazione ESEGUITA: togliere il blocco `sapere.seed(...)` da
    `prime_state_translations` -- rossa, il significato non arriva.
    """
    from hiris.app.mind.knowledge import KnowledgeStore

    sapere = KnowledgeStore(str(tmp_path / "sapere.db"))
    try:
        app = {
            "knowledge": sapere,
            "home_space_store": _CasaConFuso(),
            "state_translations": _CacheTraduzioni({
                "lette": True, "lingua": "it", "appena_lette": True, "risorse": {
                    "component.binary_sensor.entity_component.gas.name": "Gas"}}),
        }

        asyncio.run(server.prime_state_translations(app))

        riga = sapere.get("tipo", "binary_sensor.gas", "significato")
        assert riga.value == "Gas"
        assert riga.provenance == "importato"
        assert "2026.9.1" in riga.source and "it" in riga.source
    finally:
        sapere.close()


def test_se_le_traduzioni_NON_si_leggono_il_sapere_resta_com_era(tmp_path):
    """Un guasto non scrive righe vuote: «non ho potuto leggere» non e'
    «questa classe non significa niente»."""
    from hiris.app.mind.knowledge import KnowledgeStore

    sapere = KnowledgeStore(str(tmp_path / "sapere.db"))
    try:
        app = {"knowledge": sapere, "home_space_store": _CasaConFuso(),
               "state_translations": _CacheTraduzioni(
                   {"lette": False, "motivo": "HA non ha risposto"})}

        asyncio.run(server.prime_state_translations(app))

        assert sapere.summary()["totale"] == 0
    finally:
        sapere.close()


def test_senza_sapere_la_lettura_delle_traduzioni_non_si_rompe(tmp_path):
    """L'avvio costruisce il sapere prima, ma la funzione non deve dipendere
    da un ordine che nessuno le garantisce: senza `knowledge` legge e basta."""
    app = {"home_space_store": _CasaConFuso(),
           "state_translations": _CacheTraduzioni(
               {"lette": True, "lingua": "it", "risorse": {}})}

    esito = asyncio.run(server.prime_state_translations(app))

    assert esito["lette"] is True


def test_L_AGGREGAZIONE_NOTTURNA_scrive_anche_il_RESOCONTO(tmp_path):
    """**La fetta 5 cablata**: gli stessi episodi che producono gli oggetti
    scrivono anche il resoconto del giorno. Non e' una seconda lettura del
    grezzo ne' un secondo giudizio -- e' un'altra forma dello stesso lavoro, e
    farne due passate sarebbe aprire la porta a due verita' sullo stesso
    giorno.

    Mutazione ESEGUITA: togliere il blocco `store.replace_report(...)` da
    `aggregate_day` -- rossa.
    """
    from datetime import datetime

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        giorno = "2026-08-24"
        base = datetime(2026, 8, 24, 10, tzinfo=UTC)
        archivio.record(quando_ts=base.timestamp(), source="entita",
                        subject="light.cucina", da="off", a="on")
        archivio.record(quando_ts=base.timestamp() + 3600, source="entita",
                        subject="light.cucina", da="on", a="off")

        server.aggregate_day(store=archivio, day=giorno, timezone="Europe/Rome",
                             recipes={}, series={}, names={})

        resoconto = archivio.report(giorno)
        assert resoconto["giorno"] == giorno
        assert resoconto["misure"] == []
        [voce] = resoconto["cronaca"]
        assert voce["chi"] == "light.cucina"
        assert voce["cosa"] == "on"
    finally:
        archivio.close()


def test_la_riparazione_all_avvio_riscrive_anche_il_RESOCONTO_dei_due_giorni(tmp_path):
    """**Difetto trovato dal vivo il 14/09/2026**, aggiornando la casa vera
    alla 3.33.0: `GET /api/mind/report` tornava `{"resoconti": []}` e ogni
    giorno 404. La riparazione all'avvio rifaceva gli oggetti dei due giorni
    e **non** il loro resoconto -- passava `recipes=None`, e quel ramo
    saltava la scrittura -- quindi il primo resoconto sarebbe comparso solo
    alle 00:20 del giorno dopo.

    Con gli `oggetti` fuori (spec §13) lo stesso ramo non scriverebbe
    **niente**: il giorno sparirebbe, e «quel giorno non e' successo niente»
    e «quel giorno non l'abbiamo guardato» tornerebbero a essere la stessa
    cosa.

    Mutazione: rimettere la chiamata senza gli ingredienti del resoconto
    (`aggregate_day(..., )` senza `recipes=`) -- rossa su
    `assert archivio.report("2026-08-23") is not None`.
    """
    from datetime import datetime, timedelta

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=UTC)
        for delta, soggetto in ((2, "l_altro_ieri"), (1, "ieri"), (0, "oggi")):
            quando = (oggi - timedelta(days=delta)).replace(hour=10)
            archivio.record(quando_ts=quando.timestamp(), source="entita",
                            subject=f"light.{soggetto}", da="off", a="on")

        asyncio.run(server.reaggregate_last_two_days(
            {"home_space_store": None, "observations": archivio,
             "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS},
            ha_client=_repair_house(),
            now=lambda tz: oggi.astimezone(tz)))

        for giorno in ("2026-08-22", "2026-08-23"):
            scritto = archivio.report(giorno)
            assert scritto is not None, f"il resoconto di {giorno} manca"
            assert scritto["giorno"] == giorno
            # Anche la riparazione d'avvio scrive la cronaca, quindi anche lei
            # scrive l'impronta (spec 2026-09-16 §6). Mutazione ESEGUITA: in
            # `aggregate_day` non passare `judgment=` a `build_report` -- rossa.
            # **Che l'impronta sia QUESTA e non un'altra e' vero per
            # costruzione** (giro di correzioni 1, punto 7): `app` porta
            # `REPO_JUDGMENTS`, quindi non si prova che l'istantanea VIVA
            # arrivi fin qui, si prova che un'impronta ci sia. La proprieta'
            # vera -- «l'impronta scritta e' quella dei giudizi ricevuti» --
            # la difende `tests/test_mind_facts.py`, con un'istantanea
            # diversa da quella del repo.
            assert scritto["giudizio"] == chronicle_mark(REPO_JUDGMENTS)
        # E OGGI no: non e' finito, e un resoconto di mezza giornata direbbe
        # il falso su cio' che quel giorno e' stato.
        assert archivio.report("2026-08-24") is None
    finally:
        archivio.close()

def test_il_recupero_scrive_UN_giorno_mancante_per_giro_partendo_dal_piu_vecchio(tmp_path):
    """**Misurato dal vivo il 14/09/2026**: sulla casa vera esistevano i
    resoconti del 12 e del 13 e basta. Il 7, l'8, il 9, il 10 e l'11 avevano
    oggetti e grezzo e **nessun resoconto**, perche' la riparazione d'avvio
    guarda solo gli ultimi due giorni pieni e la notturna solo ieri.

    Un giorno per giro, dal piu' vecchio: le statistiche di Home Assistant si
    chiedono una volta per giorno, e ventidue richieste all'avvio
    ritarderebbero la partenza per un lavoro che non ha nessuna fretta. Dal
    piu' vecchio perche' e' quello che sta per scadere: il suo grezzo sparisce
    per primo.

    Mutazione: partire dal piu' recente -- rossa su
    `assert scritto == "2026-08-22"`.
    """
    from datetime import datetime, timedelta

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 25, tzinfo=UTC)
        for delta in (3, 2, 1):
            quando = (oggi - timedelta(days=delta)).replace(hour=10)
            archivio.record(quando_ts=quando.timestamp(), source="entita",
                            subject=f"light.g{delta}", da="off", a="on")
        archivio.replace_report("2026-08-24", {
            "giorno": "2026-08-24", "misure": [], "forme": [], "cronaca": [],
            "giudizio": chronicle_mark(REPO_JUDGMENTS)})
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}

        scritto = asyncio.run(server.backfill_one_report(
            app, ha_client=_repair_house(), now=lambda tz: oggi.astimezone(tz)))
        assert scritto == "2026-08-22", scritto
        assert archivio.report("2026-08-22") is not None

        # Il giro dopo prende il successivo, e salta quello gia' scritto.
        assert asyncio.run(server.backfill_one_report(
            app, ha_client=_repair_house(),
            now=lambda tz: oggi.astimezone(tz))) == "2026-08-23"
    finally:
        archivio.close()


def test_il_recupero_TACE_quando_non_manca_piu_niente(tmp_path):
    """Finito il recupero, il giro non deve fare niente e non deve dirlo: un
    lavoro che stampa «niente da fare» ogni cinque minuti per sempre e' rumore
    sano che seppellisce cio' che e' rotto.

    Mutazione: tornare il giorno anche quando c'e' gia' -- rossa.

    **Dal 17/09/2026 «non manca piu' niente» vuol dire anche «nessuna cronaca
    e' nata con un altro giudizio»** (spec 2026-09-16 §6): il resoconto della
    prova porta l'impronta dell'istantanea corrente. Senza, il giro lo
    rifarebbe -- ed e' giusto, lo prova la prova accanto.
    """
    from datetime import datetime, timedelta

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 25, tzinfo=UTC)
        quando = (oggi - timedelta(days=1)).replace(hour=10)
        archivio.record(quando_ts=quando.timestamp(), source="entita",
                        subject="light.a", da="off", a="on")
        archivio.replace_report("2026-08-24", {
            "giorno": "2026-08-24", "misure": [], "forme": [], "cronaca": [],
            "giudizio": chronicle_mark(REPO_JUDGMENTS)})
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}

        assert asyncio.run(server.backfill_one_report(
            app, ha_client=_repair_house(), now=lambda tz: oggi.astimezone(tz))) is None
    finally:
        archivio.close()


def test_il_recupero_NON_va_oltre_il_grezzo(tmp_path):
    """Un giorno si rifa' solo finche' il suo grezzo esiste. Andare piu'
    indietro scriverebbe resoconti **vuoti** per giorni in cui era successo di
    tutto -- e un resoconto vuoto dice «non e' successo niente», che sarebbe
    una bugia archiviata.

    Mutazione: partire da `oggi - 22 giorni` invece che dal primo grezzo --
    rossa: scriverebbe un giorno prima del 22.
    """
    from datetime import datetime, timedelta

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 25, tzinfo=UTC)
        quando = (oggi - timedelta(days=2)).replace(hour=10)
        archivio.record(quando_ts=quando.timestamp(), source="entita",
                        subject="light.a", da="off", a="on")
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}

        assert asyncio.run(server.backfill_one_report(
            app, ha_client=_repair_house(),
            now=lambda tz: oggi.astimezone(tz))) == "2026-08-23"
    finally:
        archivio.close()


def test_il_recupero_rifa_la_CRONACA_di_un_giorno_con_un_altra_impronta(tmp_path, caplog):
    """Spec 2026-09-16 §6. Mutazioni ESEGUITE: (1) lasciare la condizione a «il
    resoconto manca» -- rossa (torna `None`); (2) rifare il giorno intero con
    `aggregate_day` -- rossa (le misure del resoconto spariscono); (3) non
    loggare la riga con la durata -- rossa.

    **L'impronta asserita qui e' vera per costruzione** (giro di correzioni 1,
    punto 7): `app["type_judgments"]` porta `REPO_JUDGMENTS`, quindi
    l'uguaglianza dice «la cronaca rifatta ha scritto un'impronta», non «ha
    scritto quella dei giudizi che ha ricevuto». Che sia proprio quella --
    con un'istantanea diversa da quella del repo -- lo difende
    `tests/test_mind_facts.py`. Qui si prova il CABLAGGIO: che sia il recupero
    a far partire il rifacimento, che tocchi solo cronaca e impronta, e che
    logghi la durata."""
    from datetime import datetime, timedelta

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 25, tzinfo=UTC)
        quando = (oggi - timedelta(days=2)).replace(hour=10)
        archivio.record(quando_ts=quando.timestamp(), source="entita",
                        subject="light.g", da="off", a="on")
        # Il grezzo comincia ESATTAMENTE a mezzanotte del 23: il giorno e'
        # tutto nel grezzo, e non e' quello a cavallo della potatura che il
        # recupero non rifa' (fix round 1, prova accanto).
        archivio.record(quando_ts=quando.replace(hour=0).timestamp(), source="entita",
                        subject="sensor.t", da="20", a="21")
        for giorno in ("2026-08-23", "2026-08-24"):
            archivio.replace_report(giorno, {
                "giorno": giorno, "misure": [{"soggetto": "d", "misura": "m", "valore": 1,
                                              "unita": "kWh", "copertura": 1.0}],
                "forme": [], "cronaca": [], "giudizio": {"impronta": "vecchia"}})
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}
        with caplog.at_level(logging.INFO, logger=server.logger.name):
            scritto = asyncio.run(server.backfill_one_report(
                app, ha_client=_repair_house(), now=lambda tz: oggi.astimezone(tz)))
        assert scritto == "2026-08-23"
        rifatto = archivio.report("2026-08-23")
        assert rifatto["misure"]
        assert rifatto["giudizio"]["impronta"] == REPO_JUDGMENTS.chronicle_fingerprint()
        assert len(rifatto["cronaca"]) == 1
        assert any(re.search(r"rifatta la cronaca di 2026-08-23 .* in \d+\.\d\d s$",
                             r.getMessage()) for r in caplog.records), caplog.text
    finally:
        archivio.close()


def test_il_recupero_NON_rifa_il_giorno_a_cavallo_della_potatura_e_TIENE_gli_ereditati(tmp_path):
    """Fix round 1, lo scenario che la revisione di Fable ha ESEGUITO: un
    resoconto scritto col grezzo intero (tre voci), poi la potatura, poi un giro
    di recupero -- ne restava una.

    Due meccanismi, due regole: (1) il giorno piu' vecchio sta a cavallo del
    taglio, e le sue righe prima del taglio non ci sono piu': **non si rifa'**;
    (2) il giorno dopo eredita il termostato acceso da giorni, la cui riga
    d'origine e' potata: rifatto, **tiene** la voce ereditata.

    Mutazioni ESEGUITE: (1) togliere il salto del giorno a cavallo -- rossa
    (torna il 23 e la sua cronaca perde `light.a`); (2) togliere la fusione
    degli ereditati in `rebuild_chronicle` -- rossa (il 24 perde il termostato).

    **L'orologio del giro e' quello della potatura** (giro di correzioni 1,
    punto 1): `prune(taglio + READING_RETENTION_S)` e' la potatura che gira
    ventidue giorni dopo il taglio, quindi `oggi` e' quell'istante li'. La
    prima stesura potava col taglio del 23/08 e poi chiedeva il recupero al
    25/08: uno stato che la produzione non puo' mai avere -- a due giorni
    dall'installazione non e' stato potato niente -- e **indistinguibile** da
    quello di una casa giovane (la prova qui sotto), dove il primo giorno si
    rifa' eccome. Le due prove chiedono l'opposto sulla stessa terna di
    numeri: e' l'orologio a separarle, ed e' per questo che dev'essere vero.
    """
    from datetime import datetime

    from hiris.app.mind.facts import aggregate_day
    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 9, 14, 5, tzinfo=UTC)

        def _ts(giorno, ora):
            return datetime(2026, 8, giorno, ora, tzinfo=UTC).timestamp()

        # Dentro lo scope: dal 05/10/2026 si eredita solo chi e' guardato.
        for soggetto in ("climate.camera", "light.b"):
            archivio.decide_scope(soggetto, inside=True, reason="prova",
                                  author="observer")
        archivio.record(quando_ts=_ts(20, 10), source="entita", subject="climate.camera",
                        da="off", a="heat")
        archivio.record(quando_ts=_ts(23, 1), source="entita", subject="light.a",
                        da="off", a="on")
        archivio.record(quando_ts=_ts(23, 2), source="entita", subject="light.a",
                        da="on", a="off")
        archivio.record(quando_ts=_ts(23, 10), source="entita", subject="light.b",
                        da="off", a="on")
        scritti = {}
        for giorno in ("2026-08-23", "2026-08-24"):
            aggregate_day(store=archivio, day=giorno, timezone=None, judgments=REPO_JUDGMENTS)
            scritti[giorno] = {**archivio.report(giorno), "giudizio": {"impronta": "vecchia"}}
            archivio.replace_report(giorno, scritti[giorno])
        assert [v["chi"] for v in scritti["2026-08-23"]["cronaca"]] == [
            "light.a", "climate.camera", "light.b"]
        assert [v["chi"] for v in scritti["2026-08-24"]["cronaca"]] == [
            "climate.camera", "light.b"]

        # Il taglio alle 05:00 del 23: via il termostato e `light.a`.
        archivio.prune(_ts(23, 5) + READING_RETENTION_S)
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}
        scritto = asyncio.run(server.backfill_one_report(
            app, ha_client=_repair_house(), now=lambda tz: oggi.astimezone(tz)))

        assert scritto == "2026-08-24"
        assert archivio.report("2026-08-23") == scritti["2026-08-23"]
        rifatto = archivio.report("2026-08-24")
        assert rifatto["giudizio"] == chronicle_mark(REPO_JUDGMENTS)
        assert rifatto["cronaca"] == scritti["2026-08-24"]["cronaca"]
    finally:
        archivio.close()


def test_su_una_casa_GIOVANE_il_primo_giorno_rifa_la_cronaca(tmp_path):
    """Giro di correzioni 1, punto 1 (revisione 1, IMPORTANT): su una casa
    **mai potata** il primo giorno del grezzo si rifa' come tutti gli altri.

    La guardia della potatura confrontava l'inizio del giorno con
    `oldest_reading_ts()`. Su una casa potata quello e' l'istante del taglio;
    su una casa **giovane** e' soltanto l'ora d'installazione -- il primo
    giorno comincia a mezzanotte, la prima riga arriva alle 10:00, e quel
    giorno restava al giudizio vecchio **per sempre**, senza un rigo di log,
    finche' non usciva dalla finestra. La condizione vera e' «nessuna riga di
    questo giorno puo' essere stata potata», cioe' l'inizio del giorno dentro
    la ritenzione (`mind/store.prune` taglia esattamente li').

    Rossa prima della correzione: i tre giri tornavano
    `['2026-09-11', None, None]` e il 10/09 restava a `impronta: vecchia`.
    """
    from datetime import datetime

    from hiris.app.mind.facts import aggregate_day, chronicle_is_stale
    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 9, 12, tzinfo=UTC)

        def _ts(giorno, ora):
            return datetime(2026, 9, giorno, ora, tzinfo=UTC).timestamp()

        # L'add-on e' installato il 10/09 alle 10:00: la riga piu' vecchia e'
        # quella, mezzanotte del 10 e' PRIMA -- e non e' stato potato niente.
        archivio.record(quando_ts=_ts(10, 10), source="entita", subject="light.a",
                        da="off", a="on")
        archivio.record(quando_ts=_ts(11, 10), source="entita", subject="light.b",
                        da="off", a="on")
        assert archivio.prune(oggi.timestamp()) == 0, "niente e' scaduto: la casa ha due giorni"

        scritti = {}
        for giorno in ("2026-09-10", "2026-09-11"):
            aggregate_day(store=archivio, day=giorno, timezone=None, judgments=REPO_JUDGMENTS)
            scritti[giorno] = {**archivio.report(giorno), "giudizio": {"impronta": "vecchia"}}
            archivio.replace_report(giorno, scritti[giorno])

        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}
        giri = [asyncio.run(server.backfill_one_report(
            app, ha_client=_repair_house(), now=lambda tz: oggi.astimezone(tz)))
            for _ in range(3)]

        assert giri == ["2026-09-10", "2026-09-11", None]
        for giorno in ("2026-09-10", "2026-09-11"):
            assert not chronicle_is_stale(archivio.report(giorno), REPO_JUDGMENTS), giorno
    finally:
        archivio.close()


def test_una_cronaca_che_NON_si_rifa_NON_ferma_i_giorni_dopo(tmp_path, monkeypatch):
    """Fix round 1: dal piu' vecchio, un giorno che fallisce sempre allo stesso
    modo (un difetto locale, non la rete) fermerebbe per sempre tutti quelli
    dopo -- e al primo avvio sono vecchi tutti. Si logga e si passa al giorno
    dopo, nello stesso giro. Mutazione ESEGUITA: `return None` dopo il warning
    del ramo della cronaca -- rossa (torna `None`)."""
    from datetime import datetime, timedelta

    from hiris.app.mind import facts
    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 25, tzinfo=UTC)
        quando = (oggi - timedelta(days=2)).replace(hour=10)
        archivio.record(quando_ts=quando.timestamp(), source="entita",
                        subject="light.g", da="off", a="on")
        archivio.record(quando_ts=quando.replace(hour=0).timestamp(), source="entita",
                        subject="sensor.t", da="20", a="21")
        for giorno in ("2026-08-23", "2026-08-24"):
            archivio.replace_report(giorno, {
                "giorno": giorno, "misure": [], "forme": [], "cronaca": [],
                "giudizio": {"impronta": "vecchia"}})

        def _rotta(*, store, day, timezone, judgments, house=None):
            if day == "2026-08-23":
                raise ValueError("un difetto locale")
            return facts.rebuild_chronicle(store=store, day=day, timezone=timezone,
                                           judgments=judgments, house=house)

        monkeypatch.setattr(server, "rebuild_chronicle", _rotta)
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}
        scritto = asyncio.run(server.backfill_one_report(
            app, ha_client=_repair_house(), now=lambda tz: oggi.astimezone(tz)))
        assert scritto == "2026-08-24"
        assert archivio.report("2026-08-23")["giudizio"] == {"impronta": "vecchia"}
    finally:
        archivio.close()


@pytest.mark.asyncio(loop_scope="module")
async def test_il_giro_ogni_5_minuti_CHIAMA_backfill_one_report(started_app, caplog):
    """Giro di correzioni 1, punto 8 (MEDIO): **il lavoro periodico non era
    pinnato da nessuna prova**.

    `_recupero_resoconti` (in `_on_startup`, registrato ogni 5 minuti come
    `hiris_mind_backfill`) chiama `backfill_one_report` dentro un
    `except Exception` che logga e passa. Un nome sbagliato -- ed e'
    esattamente cio' che il rinominare del Task 6 rischiava, `server.py`
    chiamava `backfill_one_missing_report` fino a ieri -- diventerebbe un
    `NameError` inghiottito da quel ramo e loggato ogni cinque minuti per
    sempre: la casa smetterebbe di recuperare i giorni e **tutta la suite
    resterebbe verde**.

    Dal 03/10/2026 gira il lavoro VERO dello schedulatore dell'app avviata,
    con una finta al posto di `backfill_one_report` nel modulo: se il nome
    nel corpo non e' quello, la finta non viene chiamata e il ramo di
    guardia scrive il suo warning.

    Mutazione ESEGUITA (03/10/2026): `await backfill_one_report(app,
    ha_client)` -> `await backfill_one_missing_report(app, ha_client)` --
    rossa (`assert [] == [...]` sulle chiamate).
    """
    chiamate = []

    async def _finta(app, ha_client):
        chiamate.append((app, ha_client))
        return "2026-08-23"

    with mock.patch.object(server, "backfill_one_report", _finta), \
            caplog.at_level(logging.WARNING, logger=SERVER_LOGGER):
        await _job(started_app, "hiris_mind_backfill")()

    assert chiamate == [(started_app, started_app["ha_client"])], (
        "il giro deve chiamare `backfill_one_report` con l'app e il cliente di HA")
    assert _server_lines(caplog) == [], (
        "un nome che non esiste finisce nel ramo di guardia invece che in un errore: "
        f"{_server_lines(caplog)}")


def test_una_cronaca_che_NON_si_rifa_si_logga_UNA_volta_ogni_quattro_ore_per_giorno(
        tmp_path, monkeypatch, caplog):
    """Decisione del proprietario, 17/09/2026 (Task 7b): il giorno che non si
    rifa' si scrive nel log una volta, poi si tace per 4 ore **per quel
    giorno**; dopo, se fallisce ancora, si riscrive. Il giro gira ogni cinque
    minuti: senza, lo stesso warning uscirebbe 48 volte in quattro ore.

    Mutazioni ESEGUITE: (1) togliere la soglia (loggare sempre) -- rossa al
    secondo giro; (2) stato unico invece che per giorno -- rossa quando fallisce
    il secondo giorno."""
    from datetime import datetime, timedelta

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        start = datetime(2026, 8, 25, 1, 0, tzinfo=UTC)
        first = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
        archivio.record(quando_ts=first.timestamp(), source="entita",
                        subject="sensor.t", da="20", a="21")
        archivio.record(quando_ts=first.replace(hour=10).timestamp(), source="entita",
                        subject="light.g", da="off", a="on")
        archivio.replace_report("2026-08-23", {
            "giorno": "2026-08-23", "misure": [], "forme": [], "cronaca": [],
            "giudizio": {"impronta": "vecchia"}})
        archivio.replace_report("2026-08-24", {
            "giorno": "2026-08-24", "misure": [], "forme": [], "cronaca": [],
            "giudizio": chronicle_mark(REPO_JUDGMENTS)})

        def _broken(*, store, day, timezone, judgments, house=None):
            raise ValueError(f"un difetto locale del {day}")

        monkeypatch.setattr(server, "rebuild_chronicle", _broken)
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}

        def _round(after):
            caplog.clear()
            clock = start + after
            with caplog.at_level(logging.WARNING, logger=server.logger.name):
                asyncio.run(server.backfill_one_report(
                    app, ha_client=_repair_house(), now=lambda tz: clock.astimezone(tz)))
            return sorted(re.search(r"cronaca di (\S+) non rifatta", r.getMessage()).group(1)
                          for r in caplog.records if "non rifatta" in r.getMessage())

        assert _round(timedelta(0)) == ["2026-08-23"]
        assert _round(timedelta(minutes=5)) == []
        # Un altro giorno comincia a fallire: il SUO warning esce, quello del 23 no.
        archivio.replace_report("2026-08-24", {
            "giorno": "2026-08-24", "misure": [], "forme": [], "cronaca": [],
            "giudizio": {"impronta": "vecchia"}})
        assert _round(timedelta(minutes=10)) == ["2026-08-24"]
        assert _round(timedelta(hours=3, minutes=59)) == []
        assert _round(timedelta(hours=4, minutes=1)) == ["2026-08-23"]
    finally:
        archivio.close()


def _one_stale_day(tmp_path):
    """Un archivio col solo 2026-08-23 da rifare (il 24 ha l'impronta corrente)."""
    from datetime import datetime

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    first = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
    archivio.record(quando_ts=first.timestamp(), source="entita",
                    subject="sensor.t", da="20", a="21")
    archivio.record(quando_ts=first.replace(hour=10).timestamp(), source="entita",
                    subject="light.g", da="off", a="on")
    archivio.replace_report("2026-08-23", {
        "giorno": "2026-08-23", "misure": [], "forme": [], "cronaca": [],
        "giudizio": {"impronta": "vecchia"}})
    archivio.replace_report("2026-08-24", {
        "giorno": "2026-08-24", "misure": [], "forme": [], "cronaca": [],
        "giudizio": chronicle_mark(REPO_JUDGMENTS)})
    return archivio


def test_un_giorno_che_RIESCE_riapre_il_suo_warning(tmp_path, monkeypatch, caplog):
    """Fix round 1 del Task 7b: fallisce, poi riesce, poi torna a fallire entro
    le 4 ore -- e' un fatto nuovo, e si dice. Mutazione ESEGUITA: togliere il
    `pop` sulla riuscita -- rossa (l'ultimo giro tace)."""
    from datetime import datetime, timedelta

    from hiris.app.mind import facts

    archivio = _one_stale_day(tmp_path)
    try:
        start = datetime(2026, 8, 25, 1, 0, tzinfo=UTC)
        failing = {"2026-08-23"}

        def _chronicle(*, store, day, timezone, judgments, house=None):
            if day in failing:
                raise ValueError("un difetto locale")
            return facts.rebuild_chronicle(store=store, day=day, timezone=timezone,
                                           judgments=judgments, house=house)

        monkeypatch.setattr(server, "rebuild_chronicle", _chronicle)
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}

        def _warnings(after):
            caplog.clear()
            clock = start + after
            with caplog.at_level(logging.WARNING, logger=server.logger.name):
                asyncio.run(server.backfill_one_report(
                    app, ha_client=_repair_house(), now=lambda tz: clock.astimezone(tz)))
            return [r for r in caplog.records if "non rifatta" in r.getMessage()]

        assert len(_warnings(timedelta(0))) == 1
        failing.clear()
        assert _warnings(timedelta(minutes=5)) == []
        assert archivio.report("2026-08-23")["giudizio"] == chronicle_mark(REPO_JUDGMENTS)
        # Di nuovo vecchia, di nuovo rotta: entro le 4 ore dal primo warning.
        archivio.replace_report("2026-08-23", {
            "giorno": "2026-08-23", "misure": [], "forme": [], "cronaca": [],
            "giudizio": {"impronta": "vecchia"}})
        failing.add("2026-08-23")
        assert len(_warnings(timedelta(minutes=10))) == 1
    finally:
        archivio.close()


def test_un_resoconto_che_NON_si_recupera_si_logga_UNA_volta_ogni_quattro_ore(
        tmp_path, monkeypatch, caplog):
    """Decisione del proprietario, 17/09/2026 (fix round 1 del Task 7b): la
    quiete vale anche per il ramo «manca» -- Home Assistant irraggiungibile
    scriveva lo stesso warning ogni cinque minuti. Il ramo resta com'era: torna
    `None` e riprova al giro dopo. La voce del giorno e' la STESSA del ramo
    della cronaca, e una riuscita in un ramo la toglie anche per l'altro.

    Mutazioni ESEGUITE: (1) togliere la soglia nel ramo «manca» -- rossa al
    giro dei 5 minuti; (2) togliere la pulizia sulla riuscita del ramo «manca»
    -- rossa sull'ultimo giro (la cronaca che fallisce tace)."""
    from datetime import datetime, timedelta

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        start = datetime(2026, 8, 25, 1, 0, tzinfo=UTC)
        first = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)
        archivio.record(quando_ts=first.timestamp(), source="entita",
                        subject="sensor.t", da="20", a="21")
        archivio.record(quando_ts=first.replace(hour=10).timestamp(), source="entita",
                        subject="light.g", da="off", a="on")
        broken = {"ingredients": True, "chronicle": False}
        real_ingredients = server._report_ingredients
        real_chronicle = server.rebuild_chronicle

        async def _ingredients(app, ha_client, *, giorno, timezone):
            if broken["ingredients"]:
                raise ConnectionError("Home Assistant non risponde")
            return await real_ingredients(app, ha_client, giorno=giorno, timezone=timezone)

        def _chronicle(*, store, day, timezone, judgments, house=None):
            if broken["chronicle"]:
                raise ValueError("un difetto locale")
            return real_chronicle(store=store, day=day, timezone=timezone, judgments=judgments)

        monkeypatch.setattr(server, "_report_ingredients", _ingredients)
        monkeypatch.setattr(server, "rebuild_chronicle", _chronicle)
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
               "backfill_quiet": {}}

        def _round(after):
            caplog.clear()
            clock = start + after
            with caplog.at_level(logging.WARNING, logger=server.logger.name):
                done = asyncio.run(server.backfill_one_report(
                    app, ha_client=_repair_house(), now=lambda tz: clock.astimezone(tz)))
            return done, [r.getMessage() for r in caplog.records
                          if "non recuperato" in r.getMessage()
                          or "non rifatta" in r.getMessage()]

        assert _round(timedelta(0)) == (None, [(
            "cervello: resoconto di 2026-08-24 non recuperato (ConnectionError: Home "
            "Assistant non risponde) -- per questo giorno il log tace per 4 ore")])
        assert _round(timedelta(minutes=5)) == (None, [])
        done, logged = _round(timedelta(hours=4, minutes=1))
        assert done is None and len(logged) == 1 and "non recuperato" in logged[0]
        # Riesce: il resoconto si scrive, e la voce del giorno se ne va.
        broken["ingredients"] = False
        assert _round(timedelta(hours=4, minutes=6)) == ("2026-08-24", [])
        # Lo stesso giorno, poi, ha una cronaca di un altro giudizio che non si
        # rifa': e' un fatto nuovo, entro 4 ore dall'ultimo warning -- si dice.
        archivio.replace_report("2026-08-24", {
            **archivio.report("2026-08-24"), "giudizio": {"impronta": "vecchia"}})
        broken["chronicle"] = True
        done, logged = _round(timedelta(hours=4, minutes=11))
        assert done is None and len(logged) == 1 and "non rifatta" in logged[0]
    finally:
        archivio.close()


def test_la_quiete_NON_cambia_lo_stato_di_un_app_aiohttp_avviata(tmp_path, monkeypatch):
    """Fix round 1 del Task 7b (revisione Fable, misurato su aiohttp 3.14.3): il
    giro gira ad app avviata e congelata; creare la chiave li'
    (`app.setdefault`) emette «Changing state of started or joined application
    is deprecated» -- con aiohttp 4 un errore. La chiave nasce in `_on_startup`,
    che aiohttp esegue PRIMA del `freeze` (`AppRunner._make_server`).

    Due meta', perche' una sola non basta: (1) il giro su un'app VERA congelata,
    con la chiave gia' creata, non emette l'avviso -- questa prova; (2)
    `_on_startup` crea la chiave -- l'app avviata,
    `tests/test_cablaggio_dell_avvio.py::test_backfill_quiet_is_born_at_startup`.
    Con la chiave gia' presente anche `setdefault` tacerebbe: la meta' che lo
    scopre e' la (2).
    Mutazioni ESEGUITE: (a) `setdefault` nel giro e niente chiave in
    `_on_startup` -- rossa sulla (2); (b) il giro che riassegna
    `app["backfill_quiet"]` -- rossa sulla (1)."""
    import warnings
    from datetime import datetime

    from aiohttp import web

    archivio = _one_stale_day(tmp_path)
    try:
        def _broken(*, store, day, timezone, judgments, house=None):
            raise ValueError("un difetto locale")

        monkeypatch.setattr(server, "rebuild_chronicle", _broken)
        app = web.Application()
        for key, value in (("home_space_store", None), ("observations", archivio),
                           ("knowledge", None), ("type_judgments", REPO_JUDGMENTS),
                           ("backfill_quiet", {})):
            app[key] = value
        quiet = app["backfill_quiet"]
        app.freeze()
        clock = datetime(2026, 8, 25, 1, 0, tzinfo=UTC)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            asyncio.run(server.backfill_one_report(
                app, ha_client=_repair_house(), now=lambda tz: clock.astimezone(tz)))
        assert not [w for w in caught if "Changing state" in str(w.message)], \
            [str(w.message) for w in caught]
        assert app["backfill_quiet"] is quiet and "2026-08-23" in quiet
    finally:
        archivio.close()

def test_i_punti_orari_NON_buttano_media_minimo_e_massimo():
    """**La frase fondativa della spec, dentro il codice nuovo.** Il client
    legge gia' `mean`/`min`/`max` di Home Assistant e li traduce in
    `media`/`minimo`/`massimo`; i punti orari (oggi `hourly_points`)
    tenevano solo `cambio` e buttavano gli altri tre. Le ricette ricevevano
    una serie di `None` e rifiutavano dicendo «la serie e' vuota»: misurato
    sulla casa vera il 14/09/2026, **21 misure su 32 in un giorno solo**,
    tutte su temperatura, umidita',
    CO2, rumore, segnale e potenza -- le **56** entita' della casa che hanno
    una statistica di tipo `measurement` e nessun `change`.

    Mutazione: tornare a tenere il solo `cambio` -- rossa.
    """
    from hiris.app.mind.recipes import hourly_points

    punti = hourly_points([
        {"inizio": 0.0, "fine": 3600.0, "media": 25.2, "minimo": 25.1,
         "massimo": 25.3},
        {"inizio": 3600.0, "fine": 7200.0, "cambio": 1.4},
    ])
    istantanea, contatore = punti
    assert istantanea["media"] == 25.2
    assert istantanea["minimo"] == 25.1
    assert istantanea["massimo"] == 25.3
    assert istantanea["valore"] is None, "una misura istantanea non ha un cambio"
    # E il contatore resta com'era: `valore` e' il cambio, niente media.
    assert contatore["valore"] == 1.4
    assert contatore["media"] is None
