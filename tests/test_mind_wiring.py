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
import ast
import asyncio
import inspect
import logging
import re
import textwrap
from datetime import UTC
from unittest.mock import create_autospec

import pytest

from hiris.app import server
from hiris.app.home_space.reader import HomeSpace
from hiris.app.mind.store import READING_RETENTION_S
from hiris.app.mind.watcher import Watcher
from hiris.app.proxy.entity_cache import EntityCache, _to_minimal
from hiris.app.proxy.ha_client import HAClient
from hiris.app.server import watch_system_conditions
from tests._contracts import assert_stessa_firma

# --------------------------------------------------------------------------
# Il cablaggio dichiarato dal mandato (task-5-brief.md, Step 1)
# --------------------------------------------------------------------------

def test_l_archivio_e_l_osservatore_sono_cablati():
    sorgente = inspect.getsource(server)
    assert 'app["observations"] = ObservationsStore(' in sorgente
    assert 'app["watcher"] = Watcher(' in sorgente


def test_l_osservatore_e_agganciato_allo_STESSO_rubinetto_dello_specchio():
    """Non si apre un secondo rubinetto: due sorgenti degli stessi eventi
    sarebbero due cose che possono divergere."""
    sorgente = inspect.getsource(server)
    assert "ha_client.add_state_listener(app[\"watcher\"].watch_reading)" in sorgente
    assert sorgente.index("ha_client.add_state_listener(entity_cache.on_state_changed)") \
        < sorgente.index("ha_client.add_state_listener(app[\"watcher\"].watch_reading)")


def test_l_osservatore_nasce_dopo_il_suo_archivio():
    sorgente = inspect.getsource(server)
    assert sorgente.index('app["observations"] = ObservationsStore(') \
        < sorgente.index('app["watcher"] = Watcher(')


def test_i_due_lavori_periodici_sono_registrati():
    """L'aggregazione notturna e la potatura. Senza il primo il grezzo si
    accumula e nessun oggetto nasce; senza il secondo l'archivio cresce per
    sempre."""
    sorgente = inspect.getsource(server)
    assert 'id="hiris_mind_aggregation"' in sorgente
    assert 'id="hiris_mind_pruning"' in sorgente


def test_l_archivio_si_chiude_nello_spegnimento():
    sorgente = inspect.getsource(server._on_cleanup)
    assert 'if "observations" in app:' in sorgente
    assert 'app["observations"].close()' in sorgente


def _kwargs_add_job(sorgente: str, job_id: str) -> dict:
    """Gli argomenti dell'`add_job` che registra `job_id`, letti dal blocco
    fra `scheduler.add_job(` e la parentesi che lo chiude -- non un pezzo di
    sorgente tagliato a un numero fisso di caratteri (task-5-fix-brief.md,
    punto 1): un `blocco` ritagliato a mano intorno all'`id` puo' contenere
    la parola `"cron"` anche quando l'ORA dentro quel blocco e' sbagliata --
    ed e' esattamente il difetto, ricomparso cinque volte in questa fetta,
    che questa funzione chiude leggendo `hour`/`minute` per davvero."""
    marcatore = f'id="{job_id}"'
    pos = sorgente.index(marcatore)
    inizio = sorgente.rindex("scheduler.add_job(", 0, pos)
    fine = sorgente.index(")", pos)
    blocco = sorgente[inizio:fine]
    assert 'trigger="cron"' in blocco, f"{job_id} non e' un lavoro a orario fisso"
    kwargs = {}
    for nome in ("hour", "minute"):
        m = re.search(rf"\b{nome}=(\d+)", blocco)
        if m:
            kwargs[nome] = int(m.group(1))
    return kwargs


def test_l_aggregazione_gira_alle_00_20_della_casa():
    """Aggregare a mezzanotte esatta prenderebbe un giorno ancora aperto: le
    00:20 sono l'ora vera, non solo un blocco che contiene la parola 'cron'
    (task-5-fix-brief.md, punto 1 -- la quinta ricomparsa del difetto n.1 in
    questa fetta: un `hour=23` sarebbe restato verde col test precedente,
    perche' 'cron' resta comunque nel blocco).

    Mutazione provata a mano: `hour=0` -> `hour=23` in `server.py` fa
    fallire questo test (`{'hour': 23, 'minute': 20} != {'hour': 0,
    'minute': 20}`); ripristinato subito dopo."""
    sorgente = inspect.getsource(server)
    assert _kwargs_add_job(sorgente, "hiris_mind_aggregation") == {
        "hour": 0, "minute": 20}


def test_la_potatura_gira_alle_03_00():
    """Stessa tecnica, stesso difetto possibile: qui l'ora e' quella della
    notte (03:00), lontana dall'aggregazione (00:20) apposta -- l'una deve
    finire prima che l'altra cominci a leggere il grezzo."""
    sorgente = inspect.getsource(server)
    assert _kwargs_add_job(sorgente, "hiris_mind_pruning") == {
        "hour": 3, "minute": 0}


# --------------------------------------------------------------------------
# Correzione A: la terza voce che il mandato originale dimenticava --
# `watch_system` deve avere un chiamante vero, non restare morto.
# --------------------------------------------------------------------------

def test_il_terzo_lavoro_periodico_delle_condizioni_e_registrato():
    """Senza questo lavoro `watch_system` non ha nessun chiamante di
    produzione: nasce codice morto lo stesso giorno in cui viene scritto, e
    la spec §6 (i guasti diventano oggetti dal primo giorno) diventa una
    frase falsa (task-5-correzioni.md, punto A)."""
    sorgente = inspect.getsource(server)
    assert 'id="hiris_mind_conditions"' in sorgente
    blocco = sorgente[sorgente.index('id="hiris_mind_conditions"') - 400:
                      sorgente.index('id="hiris_mind_conditions"') + 200]
    assert "minutes=10" in blocco
    assert "watch_system_conditions" in sorgente


def test_le_condizioni_si_leggono_anche_una_volta_all_avvio():
    """«Ogni 10 minuti, e una volta all'avvio» (punto A): senza la prima
    lettura all'avvio, un guasto gia' aperto da prima del boot resterebbe
    invisibile fino a dieci minuti dopo."""
    sorgente = inspect.getsource(server._on_startup)
    assert sorgente.count("watch_system_conditions(app, ha_client)") >= 2


def test_l_osservatore_ricostruisce_le_condizioni_all_avvio():
    """Punto B: senza questa chiamata, a ogni riavvio dell'add-on -- che
    succede a ogni aggiornamento -- i guasti gia' aperti verrebbero
    riscritti come nati adesso, e l'oggetto «guasto» perderebbe la sua unica
    informazione utile: da quando dura."""
    sorgente = inspect.getsource(server._on_startup)
    assert 'app["watcher"].rebuild_conditions()' in sorgente
    assert sorgente.index('app["watcher"] = Watcher(') \
        < sorgente.index('app["watcher"].rebuild_conditions()') \
        < sorgente.index('watch_system_conditions(app, ha_client)')


def _estrai_funzione_innestata(nome_funzione: str) -> str:
    """Il sorgente VERO di una funzione innestata in `_on_startup` (`async
    def <nome_funzione>...`), dalla sua riga di definizione alla riga vuota
    che la separa dal codice seguente (tipicamente `scheduler.add_job(...)`)
    -- la stessa tecnica di `tests/test_websocket_startup.py` e
    `tests/test_nightly_pruning.py`: si esegue il sorgente vero isolato,
    non un suo doppione riscritto a mano che potrebbe divergere da cio' che
    gira davvero."""
    src = inspect.getsource(server._on_startup)
    inizio = src.index(f"async def {nome_funzione}(")
    fine = src.index("\n\n", inizio)
    return textwrap.dedent(src[inizio:fine])


def _carica_funzione_innestata(nome_funzione: str, globali: dict):
    """Compila il blocco estratto in un namespace con le variabili libere
    (closure di `_on_startup`: `app`, `logger`, `_time`, ...) gia' dentro
    `globali` -- cosi' la funzione, una volta chiamata, le risolve da li'
    esattamente come farebbe dentro `_on_startup` vera."""
    namespace = dict(globali)
    exec(compile(_estrai_funzione_innestata(nome_funzione),
                f"<_on_startup {nome_funzione}>", "exec"), namespace)
    return namespace[nome_funzione]


class _ArchivioOsservazioniFinto:
    """La finta deve saper produrre il difetto che sorveglia (feedback
    ricorrente di questo progetto): oltre a tornare un numero da `prune()`,
    deve poter SOLLEVARE a comando, per provare che la potatura ha una rete
    propria (punto 3 del mandato)."""

    def __init__(self, quanti: int = 0, *, pota_solleva: bool = False):
        self._quanti = quanti
        self._pota_solleva = pota_solleva
        self.chiamate = 0

    def prune(self, now_ts):
        self.chiamate += 1
        if self._pota_solleva:
            raise RuntimeError("disco pieno")
        return self._quanti


def _tempo_fisso(valore: float):
    class _Tempo:
        @staticmethod
        def time():
            return valore
    return _Tempo()


def test_la_potatura_logga_il_numero_vero_di_giorni(caplog):
    """Punto 1, seconda meta' (task-5-fix-brief.md): il test precedente
    verificava che la riga `giorni = READING_RETENTION_S // 86400`
    ESISTESSE nel sorgente, non che la riga di log la USASSE davvero -- un
    mutante che tiene l'assegnazione morta e passa `21` letterale al posto
    di `giorni` restava verde. Qui si esegue la funzione vera e si legge il
    messaggio prodotto.

    Mutazione provata a mano: nella riga di log, `giorni` sostituito con
    `21` letterale (l'assegnazione morta restava). Rosso:
    `AssertionError: assert 'cervello: 5 cambi oltre i 21 giorni sono
    usciti' == 'cervello: 5 cambi oltre i 22 giorni sono usciti'`.
    Ripristinato subito dopo."""
    assert READING_RETENTION_S // 86400 == 22
    finto = _ArchivioOsservazioniFinto(quanti=5)
    logger_test = logging.getLogger("test_potatura_giorni")
    job = _carica_funzione_innestata("_prune_observations", {
        "app": {"observations": finto}, "_time": _tempo_fisso(0.0),
        "logger": logger_test, "READING_RETENTION_S": READING_RETENTION_S,
    })

    with caplog.at_level(logging.INFO, logger="test_potatura_giorni"):
        asyncio.run(job())

    assert finto.chiamate == 1
    [messaggio] = [r.getMessage() for r in caplog.records]
    assert messaggio == "cervello: 5 cambi oltre i 22 giorni sono usciti"


def test_la_potatura_non_logga_niente_quando_non_pota_niente(caplog):
    """`if quanti:` -- una notte senza niente da potare non deve produrre
    una riga di log vuota di significato."""
    finto = _ArchivioOsservazioniFinto(quanti=0)
    logger_test = logging.getLogger("test_potatura_silenziosa")
    job = _carica_funzione_innestata("_prune_observations", {
        "app": {"observations": finto}, "_time": _tempo_fisso(0.0),
        "logger": logger_test, "READING_RETENTION_S": READING_RETENTION_S,
    })

    with caplog.at_level(logging.INFO, logger="test_potatura_silenziosa"):
        asyncio.run(job())

    assert caplog.records == []


def test_la_potatura_non_lascia_uscire_l_eccezione(caplog):
    """Punto 3 del mandato: `_prune_observations` era l'unico dei tre lavori
    SENZA un try/except suo -- un guasto di SQLite alle tre di notte finiva
    nel registro di apscheduler senza il prefisso 'cervello:', a differenza
    dei due lavori fratelli. Qui si prova che un errore di `prune()` sia
    catturato e loggato con quel prefisso, non lasciato propagare.

    La mutazione, qui, e' lo stato originale (nessun try/except): e' cio'
    che questo test trova rosso PRIMA della correzione -- `asyncio.run(job())`
    solleva `RuntimeError('disco pieno')` invece di tornare, e il test fallisce
    con quell'eccezione."""
    finto = _ArchivioOsservazioniFinto(pota_solleva=True)
    logger_test = logging.getLogger("test_potatura_rete")
    job = _carica_funzione_innestata("_prune_observations", {
        "app": {"observations": finto}, "_time": _tempo_fisso(0.0),
        "logger": logger_test, "READING_RETENTION_S": READING_RETENTION_S,
    })

    with caplog.at_level(logging.WARNING, logger="test_potatura_rete"):
        asyncio.run(job())  # non deve sollevare

    assert finto.chiamate == 1
    assert any(r.getMessage().startswith("cervello:") for r in caplog.records)


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


class _ClienteFinto:
    """Un `HAClient` finto: `problemi_esito` e' cio' che torna `problems()`,
    `registri_esito` la coppia `(registri, non_disponibili)` di
    `read_registries()`, `log_outcome` cio' che torna `system_log()` (Task 2)
    -- di default un registro vuoto, cosi' i chiamanti esistenti che non
    hanno nulla da dire sul registro di errori non devono aggiornarsi.
    `log_outcome` e' in inglese (i due fratelli qui sopra sono debito, non
    un modello da imitare -- identificatori nuovi in inglese)."""

    def __init__(self, problemi_esito, registri_esito, log_outcome=None):
        self._problemi_esito = problemi_esito
        self._registri_esito = registri_esito
        self._log_outcome = log_outcome if log_outcome is not None else {"voci": []}

    async def problems(self):
        return self._problemi_esito

    async def read_registries(self):
        return self._registri_esito

    async def system_log(self):
        return self._log_outcome


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


def test_il_cliente_finto_combacia_con_haclient_leggi_registri():
    """Guardia contro il buco misurato dal vivo (review lotto 5,
    `home_space/topology.py`): un finto duck-typed puo' rinominare i suoi
    parametri o cambiarne il conteggio senza che nessuno se ne accorga,
    perche' Python non controlla un'interfaccia -- solo che il nome
    esista. Qui `read_registries` non ha parametri oltre `self`, quindi il
    rischio e' basso, ma la guardia costa una riga e vale per ogni
    modifica futura a `HAClient.read_registries`."""
    from hiris.app.proxy.ha_client import HAClient
    assert_stessa_firma(HAClient.read_registries, _ClienteFinto.read_registries,
                        nome="HAClient.read_registries")


def test_the_fake_client_matches_haclient_system_log():
    """Stessa guardia, per la terza lettura (Task 2, «le tracce e il
    log»): se `HAClient.system_log()` acquisisse un parametro, questa finta
    duck-typed lo ignorerebbe in silenzio."""
    from hiris.app.proxy.ha_client import HAClient
    assert_stessa_firma(HAClient.system_log, _ClienteFinto.system_log,
                        nome="HAClient.system_log")


def test_guarda_condizioni_chiama_guarda_sistema_quando_le_due_letture_riescono():
    osservatore = _OsservatoreFinto()
    app = {"watcher": osservatore}
    cliente = _ClienteFinto(
        {"problemi": [{"domain": "hue", "issue_id": "x"}]},
        ({"integrazioni": [{"entry_id": "y", "state": "not_loaded"}]}, []))

    esito = asyncio.run(watch_system_conditions(app, cliente))

    assert esito == 2
    assert len(osservatore.chiamate) == 1
    assert osservatore.chiamate[0]["problemi"] == [{"domain": "hue", "issue_id": "x"}]
    assert osservatore.chiamate[0]["integrazioni"] == [{"entry_id": "y", "state": "not_loaded"}]


def test_un_errore_di_problemi_salta_il_giro_per_intero():
    """La prova per mutazione (task-5-correzioni.md, punto A.1): con
    `problems()` che torna `{"errore": ...}`, `watch_system` non viene
    chiamato. La mutazione (passare `[]` invece di saltare il giro) e' stata
    provata a mano durante l'implementazione e fa arrossire questa prova --
    non e' un'affermazione a vuoto."""
    osservatore = _OsservatoreFinto()
    app = {"watcher": osservatore}
    cliente = _ClienteFinto(
        {"errore": "Home Assistant non ha risposto"},
        ({"integrazioni": []}, []))

    esito = asyncio.run(watch_system_conditions(app, cliente))

    assert esito is None
    assert osservatore.chiamate == []


def test_le_integrazioni_non_disponibili_saltano_il_giro_per_intero():
    """Identico per `read_registries`: se `"integrazioni"` e' in
    `non_disponibili`, quella lista e' vuota per guasto, non perche' vada
    tutto bene -- passarla cosi' com'e' chiuderebbe ogni integrazione gia'
    rotta come se si fosse appena risolta."""
    osservatore = _OsservatoreFinto()
    app = {"watcher": osservatore}
    cliente = _ClienteFinto(
        {"problemi": []},
        ({"integrazioni": []}, ["integrazioni"]))

    esito = asyncio.run(watch_system_conditions(app, cliente))

    assert esito is None
    assert osservatore.chiamate == []


def test_a_broken_log_read_skips_the_round_entirely():
    """Stessa disciplina di `test_un_errore_di_problemi_salta_il_giro_per_intero`,
    estesa alla terza lettura (Task 2, «le tracce e il log»): se
    `system_log()` torna `{"errore": ...}`, `watch_system` non viene
    chiamato -- un registro non letto trattato come vuoto chiuderebbe ogni
    voce di log gia' aperta al secondo giro di isteresi.

    Mutazione: togliere il controllo `if "errore" in log_report` da
    `watch_system_conditions` -- `log_entries` diventa `[]` (nessuna voce
    nel report d'errore) e il giro NON si salta piu': il test torna rosso
    su `assert esito is None` (diventa `0`, il conteggio di
    `_OsservatoreFinto.watch_system` su tre liste vuote).
    """
    osservatore = _OsservatoreFinto()
    app = {"watcher": osservatore}
    cliente = _ClienteFinto(
        {"problemi": []}, ({"integrazioni": []}, []),
        {"errore": "Home Assistant non ha risposto"})

    esito = asyncio.run(watch_system_conditions(app, cliente))

    assert esito is None
    assert osservatore.chiamate == []


def test_senza_osservatore_non_scrive_niente():
    """Un `app` senza `"watcher"` (avvio a meta', o un test che non lo
    costruisce): il giro tace invece di sollevare."""
    cliente = _ClienteFinto({"problemi": []}, ({"integrazioni": []}, []))

    esito = asyncio.run(watch_system_conditions({}, cliente))

    assert esito is None


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


def test_l_aggregazione_notturna_logga_col_prefisso_cervello_anche_se_il_fuso_non_si_legge(caplog):
    """Punto 2(a): se `reference_frame()` solleva, il warning
    contestualizzato ('cervello: ...') deve partire comunque -- non finire
    nel registro di apscheduler senza prefisso, cosa che succede quando
    `fuso`/`ieri` sono calcolati FUORI dal try.

    Prima della correzione questo test e' rosso per davvero, non per un
    assert: `asyncio.run(job())` solleva `RuntimeError`, perche' l'eccezione
    di `reference_frame()` esce dalla funzione innestata prima ancora
    di entrare nel try.

    **Correzione di riparazione-impoverisce-brief.md, appendice punto 4.**
    Prima assertava SOLO il prefisso, come il test gemello sotto assertava
    SOLO 'cervello:' prima della sua correzione: un `NameError` dentro la
    funzione estratta (una variabile libera mancante in `globali`, per un
    refuso futuro in questa lista) e' anch'esso un'`Exception`, viene
    inghiottito dallo stesso `except`, e produce un messaggio che INIZIA per
    'cervello:' esattamente come il `RuntimeError` che questo test dichiara
    di provare -- indistinguibile con un `assert ... .startswith(...)`. Qui
    l'assert e' sul messaggio preciso, come nel test gemello."""
    logger_test = logging.getLogger("test_aggrega_ieri_fuso")
    job = _carica_funzione_innestata("_aggrega_ieri", {
        "app": {"home_space_store": _ArchivioCasaCheSolleva()},
        "ha_client": None, "logger": logger_test,
        "aggregate_day": server.aggregate_day, "datetime": server.datetime,
        "timedelta": server.timedelta, "home_space_zone": server.home_space_zone,
        "day_boundaries": server.day_boundaries,
        "build_balances": server.build_balances,
        "_report_ingredients": server._report_ingredients,
        "_timezone_from_home_space_store": server._timezone_from_home_space_store,
    })

    with caplog.at_level(logging.WARNING, logger="test_aggrega_ieri_fuso"):
        asyncio.run(job())  # non deve sollevare

    assert any(
        "cervello: aggregazione notturna fallita (RuntimeError: sqlite del "
        "sistema di riferimento irraggiungibile)" in r.getMessage()
        for r in caplog.records)


def test_riaggrega_gli_ultimi_due_giorni_rifa_esattamente_ieri_e_l_altro_ieri(tmp_path):
    """Punto 2(b), la cura vera: all'avvio si riaggregano gli ultimi due
    giorni pieni (oggi escluso, che non e' ancora finito) -- non 'i giorni
    senza oggetti' (un giorno senza oggetti e' un esito legittimo, vedi il
    mandato). Si popola il grezzo di QUATTRO giorni, OGGI compreso, e si
    verifica che solo i due piu' recenti FRA I FINITI vengano scritti come
    oggetti. Qui `ha_client=_ClienteStatistiche()`: senza `mappa`, ogni `legami`
    torna vuoto (nessun legame, non un guasto -- vedi il suo docstring),
    quindi nessun soggetto fallisce e la riparazione gira per intero come se
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
            archivio.record(quando_ts=quando.timestamp(), source="entita",
                            subject=f"light.{soggetto}", da="off", a="on")

        asyncio.run(server.reaggregate_last_two_days(
            {"home_space_store": None, "observations": archivio,
             "knowledge": _sapere(tmp_path)}, ha_client=_ClienteStatistiche(),
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
             "knowledge": _sapere(tmp_path)}, ha_client=_ClienteStatistiche(),
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


def test_la_riaggregazione_degli_ultimi_due_giorni_gira_dopo_le_condizioni_e_non_blocca_l_avvio():
    """Punto 2(b): due vincoli separati, entrambi nel mandato -- l'ordine nel
    sorgente ('dopo la ricostruzione delle condizioni') e la protezione
    ('non deve bloccare l'avvio').

    **Cosa NON sorveglia** (cancello-rilascio-brief.md, punto 1, «la
    lezione»): questo test guarda una STRINGA in un certo ordine nel
    sorgente. Non sa dire se, nel punto in cui la chiamata compare, il
    collaboratore di cui la funzione ha davvero bisogno --
    `app["home_space_store"]` -- esiste gia'. E' esattamente cosi' che il
    CRITICAL del punto 1 e' rimasto invisibile per due giri: la chiamata
    stava "dopo le condizioni" (verificato, verde) ma anche 87 righe PRIMA
    della creazione di `home_space_store` (non verificato, mai stato rosso).
    La sorveglianza vera, per COMPORTAMENTO, e' il test qui sotto,
    `test_la_riparazione_di_avvio_riceve_home_space_store_gia_costruito`, che
    esegue la fetta reale del sorgente e legge cosa la riparazione riceve
    DAVVERO."""
    sorgente = inspect.getsource(server._on_startup)
    assert "reaggregate_last_two_days(app, ha_client)" in sorgente
    assert sorgente.index('app["watcher"].rebuild_conditions()') \
        < sorgente.index("reaggregate_last_two_days(app, ha_client)")
    pos = sorgente.index("reaggregate_last_two_days(app, ha_client)")
    blocco = sorgente[pos - 80:pos + 200]
    assert "try:" in blocco
    assert "except Exception" in blocco


def _estrai_blocco_riparazione_avvio() -> str:
    """Il sorgente VERO di `_on_startup`, dalla creazione di `home_space_store`
    alla fine del try/except della riparazione all'avvio -- stessa tecnica di
    `_estrai_funzione_innestata`, ma su una FETTA contigua invece che su una
    funzione innestata: e' il modo di eseguire per davvero l'ordine fra le
    due righe, invece di dedurlo confrontando due indici di stringa.

    Se la chiamata alla riparazione torna a stare PRIMA della creazione di
    `home_space_store` (la regressione del punto 1), il marcatore di fine non si
    trova piu' DOPO quello di inizio, e `sorgente.index(marcatore_fine,
    inizio)` solleva `ValueError` -- un rosso esplicito sull'estrazione
    stessa, non un'asserzione che potrebbe passare per la ragione sbagliata."""
    src = inspect.getsource(server._on_startup)
    marcatore_inizio = 'home_space_store = HomeSpace(data_dir)'
    marcatore_fine = '"fallita (%s: %s)", type(exc).__name__, exc)'
    inizio = src.index(marcatore_inizio)
    # Dall'INIZIO DELLA RIGA, non dal marcatore: altrimenti la prima riga
    # perderebbe la sua indentazione (il marcatore comincia dopo gli spazi)
    # e `textwrap.dedent` calcolerebbe un prefisso comune vuoto -- ogni riga
    # successiva, ancora indentata, diventerebbe un `IndentationError`.
    inizio_riga = src.rfind("\n", 0, inizio) + 1
    fine = src.index(marcatore_fine, inizio) + len(marcatore_fine)
    return textwrap.dedent(src[inizio_riga:fine])


def test_la_riparazione_di_avvio_riceve_home_space_store_gia_costruito(tmp_path):
    """La sorveglianza per COMPORTAMENTO del punto 1 (CRITICAL,
    cancello-rilascio-brief.md): si esegue la fetta VERA di `_on_startup` che
    crea `home_space_store`, lo mette in `app`, e subito dopo chiama la
    riparazione -- con la riparazione sostituita da una spia che registra
    cosa ha ricevuto. Non un `assert` su una posizione di stringa: la prova
    che, quando la riparazione gira per davvero, il collaboratore che le
    serve per leggere il fuso della casa (`home_space_store`, non `None`) e'
    gia' li'.

    Le finte di TUTTI gli altri test di questo file (sopra) passano
    `"home_space_store": None` a `reaggregate_last_two_days` -- fedeli
    alla produzione ROTTA, come rilevato dal cancello del rilascio: nessuna
    di loro poteva vedere questo difetto, per costruzione. Questo test e' il
    solo che guarda l'ORDINE VERO invece di darlo per assunto.

    Mutazione ESEGUITA: spostando a mano la chiamata alla riparazione (e il
    suo blocco di commento) di nuovo sopra la riga `home_space_store =
    HomeSpace(...)`, com'era prima di questo giro -- `_estrai_blocco_
    riparazione_avvio` solleva `ValueError: substring not found`, perche' il
    marcatore di fine non compare piu' dopo quello di inizio. Rosso,
    esplicito. Ripristinato subito dopo."""
    import os as os_reale

    ricevuto: dict = {}

    async def _spia(app, ha_client):
        casa = app.get("home_space_store")
        ricevuto["home_space_store"] = casa
        ricevuto["anagrafe"] = casa.read() if casa is not None else None

    cliente = create_autospec(HAClient, instance=True)
    cliente.read_registries.return_value = (
        {"entita": [{"entity_id": "sensor.frigo", "device_id": "d1"}],
         "dispositivi": [{"id": "d1", "name": "Frigo"}],
         "piani": [], "aree": [], "etichette": [], "categorie": [], "integrazioni": []},
        [])
    cliente.get_config.return_value = {"time_zone": "Europe/Rome"}
    specchio = EntityCache()
    specchio._loaded = True

    namespace = {
        "os": os_reale, "data_dir": str(tmp_path), "HomeSpace": server.HomeSpace,
        "app": {}, "ha_client": cliente, "entity_cache": specchio,
        "rebuild": server.rebuild,
        "schedule_registry_rebuild": lambda *a, **k: (lambda *_: None),
        "reaggregate_last_two_days": _spia,
        "logger": logging.getLogger("test_riparazione_riceve_home_space_store"),
    }
    corpo = _estrai_blocco_riparazione_avvio()
    func_src = "async def _check():\n" + textwrap.indent(corpo, "    ")
    exec(compile(func_src, "<_on_startup riparazione avvio>", "exec"), namespace)

    try:
        asyncio.run(namespace["_check"]())
        assert ricevuto.get("home_space_store") is not None
        assert isinstance(ricevuto["home_space_store"], server.HomeSpace)
        assert ricevuto["home_space_store"] is namespace["app"]["home_space_store"]
        # **E l'anagrafe dev'essere gia' LETTA, non solo costruita.** Misurato
        # dal vivo il 10/09/2026 sulla v3.24.0: la riparazione girava prima di
        # `rebuild`, quindi leggeva una casa vuota -- e `build_balances`, che
        # cerca le entita' con classe `energy`, non trovava un solo candidato.
        # Risultato: i due giorni riparati all'avvio nascevano SENZA bilancio,
        # e `replace_day` li sostituiva a quelli buoni della notte. Finche'
        # l'anagrafe stava su disco il difetto non si vedeva: c'era la copia di
        # ieri.
        assert ricevuto["anagrafe"].get("entita"), (
            "la riparazione ha ricevuto un'anagrafe vuota: gira prima di rebuild")
    finally:
        namespace["app"]["home_space_store"].close()


def test_se_la_riaggregazione_solleva_l_avvio_prosegue(caplog):
    """Comportamento, non testo: si esegue il VERO try/except del punto di
    chiamata, con `reaggregate_last_two_days` sostituita da una finta
    che solleva `RuntimeError`, e si legge che l'avvio prosegue E logga quel
    preciso errore -- non solo un qualunque messaggio con prefisso
    'cervello:' (quella riga sola non distinguerebbe un `RuntimeError`
    catturato per davvero da un errore diverso catturato per sbaglio).

    **Correzione di cablaggio-pulizia-brief.md, punto 2.** La versione
    precedente ancorava il blocco con `sorgente.rindex("try:", 0,
    sorgente.index(chiamata))` -- "il `try:` piu' vicino prima della
    chiamata". Con la correzione presente (il `try/except` qui sotto) quel
    `try:` e' quello giusto, e il test passa -- ma per la ragione sbagliata:
    verificato a mano togliendo il `try/except` che avvolge la chiamata
    (mutazione naturale, lo stato pre-correzione), il `rindex` risale al
    `try:` PRECEDENTE (quello di `watch_system_conditions`, qui
    accanto), e il blocco che ne esce contiene un `await` fuori da una
    funzione `async` -- il test arrossisce con `SyntaxError`, non con
    `RuntimeError`. Rosso per accidente: se il blocco precedente diventasse
    sincrono, o un altro `try` si frapponesse, sarebbe tornato verde senza
    provare niente.

    Qui l'ancora e' il blocco stesso -- il testo letterale che contiene sia
    `try:` sia la chiamata, non "il try piu' vicino" -- quindi non puo' mai
    agganciare un try estraneo: se il `try/except` sparisse, l'ancora non si
    troverebbe piu' e `sorgente.index` solleverebbe, fermando il test con un
    errore invece di un falso verde."""
    sorgente = inspect.getsource(server._on_startup)
    marcatore = ('    try:\n'
                '        await reaggregate_last_two_days(app, ha_client)')
    inizio = sorgente.index(marcatore)
    fine = sorgente.index("\n\n", inizio)
    corpo = textwrap.dedent(sorgente[inizio:fine])

    async def _che_solleva(app, ha_client):
        raise RuntimeError("archivio irraggiungibile")

    logger_test = logging.getLogger("test_riaggrega_avvio_non_blocca")
    namespace = {"app": {}, "ha_client": None,
                "reaggregate_last_two_days": _che_solleva,
                "logger": logger_test}
    func_src = "async def _check():\n" + textwrap.indent(corpo, "    ")
    exec(compile(func_src, "<_on_startup riaggregazione>", "exec"), namespace)

    with caplog.at_level(logging.WARNING, logger="test_riaggrega_avvio_non_blocca"):
        asyncio.run(namespace["_check"]())  # non deve sollevare

    # Il comportamento vero: quel preciso RuntimeError e' stato catturato e
    # loggato, non un altro errore qualsiasi.
    assert any("RuntimeError: archivio irraggiungibile" in r.getMessage()
              for r in caplog.records)
    assert any(r.getMessage().startswith("cervello:") for r in caplog.records)


# --------------------------------------------------------------------------
# Le direzioni dell'energia (mandato 27/08/2026): costruite UNA VOLTA per
# giro di aggregazione, come i comprimari -- e con la STESSA asimmetria gia'
# decisa per loro: chi costruisce dal nulla (`_aggrega_ieri`) tollera il
# parziale, chi sostituisce (`reaggregate_last_two_days`) no.
# --------------------------------------------------------------------------

def _casa_con_un_dispositivo(tmp_path, *, fuso="Europe/Rome"):
    """Un `HomeSpace` reale con un dispositivo e una sua entita' di
    energia -- il minimo che `build_balances` ha bisogno di leggere dal
    registro (fedele al contratto vero, non una finta a parte)."""
    from hiris.app.home_space.reader import HomeSpace

    casa = HomeSpace(str(tmp_path))
    casa.hold_registries(
        {"dispositivi": [{"id": "dev1", "name": "Inverter"}],
         "entita": [{"entity_id": "sensor.energia_prodotta_oggi",
                    "device_id": "dev1", "device_class": "energy"}]},
        [], reference_frame={"fuso": fuso})
    return casa


def _giornata_bilancio(cambi: dict[int, float]):
    """Una giornata INTERA di punti orari: i valori alle ore dette, uno zero
    MISURATO nelle altre.

    Dal 12/09/2026 il totale di una dimensione passa da `somma_periodo` del
    registro (`mind/operations.py`), che rifiuta sotto la copertura minima. Un
    solo punto su ventiquattro ore non e' piu' un bilancio, ed e' giusto cosi':
    queste prove di CABLAGGIO -- che il bilancio nasca, si scriva, si riapplichi
    alla riparazione -- non devono poggiare su un totale che il registro non
    firmerebbe. Il caso «poche ore» ha la sua prova dove e' il soggetto,
    in `test_mind_balance.py`.
    """
    return [_punto_bilancio(cambi.get(ora, 0.0), ora=ora) for ora in range(24)]


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


class _ClienteStatistiche:
    """La finta di `HAClient` che la riparazione d'avvio usa adesso.

    Era `_ClienteLegami`, ed e' uscita coi comprimari (15/09/2026): la
    riparazione non chiede piu' `legami` a nessuno. Le resta `hourly_
    statistics`, che `_report_ingredients` chiama solo quando c'e' un'anagrafe
    -- e in queste prove `home_space_store` e' `None`, quindi non ci arriva
    mai. La finta c'e' lo stesso perche' `None` non e' un client: passarlo
    nasconderebbe un `AttributeError` dietro un `except`.
    """

    async def hourly_statistics(self, identifiers: list[str],
                                from_iso: str, to_iso: str) -> dict:
        # La firma e' quella VERA, non `*args`: il cancello dei contratti
        # (`test_ha_client_contract.py`) non accetta una finta che accetti
        # qualunque cosa -- una finta piu' permissiva del vero nasconde
        # proprio i difetti che sta li' a prendere.
        return {"serie": {}}


def _sapere(tmp_path):
    """Il sapere, seminato come fa l'avvio vero.

    Le prove di cablaggio costruiscono un'app a mano: se quella e' piu' povera
    di quella che gira davvero, difendono un cablaggio che non esiste. Dal
    12/09/2026 `reaggregate_last_two_days` legge le direzioni dal sapere, e
    un'app senza sapere non e' una semplificazione -- e' un'altra app.
    """
    from hiris.app.mind.knowledge import KnowledgeStore
    from hiris.app.mind.seed import direction_seed

    sapere = KnowledgeStore(str(tmp_path / "sapere.db"))
    sapere.seed(direction_seed(1787572800.0))
    # Si annota per chiuderlo a fine sessione: quindici prove che aprono un
    # sqlite e non lo chiudono lasciano quindici descrittori aperti, e su
    # Windows il file resta bloccato (revisione indipendente, 13/09/2026).
    _SAPERI_APERTI.append(sapere)
    return sapere


def _punto_bilancio(cambio, ora=6):
    """Un punto orario tradotto, con istanti VERI -- non `"x"`/`"y"`
    (correzione del mandato «il bilancio dell'energia», punto 1, secondo
    paragrafo, 27/08/2026): una stringa segnaposto non sa nemmeno
    RAPPRESENTARE un istante, e a quel livello il contenuto della curva
    resta strutturalmente non verificabile. Questi test di cablaggio non
    leggono ancora `forma`/`ora` (la verifica del contenuto vive in
    `test_mind_balance.py`, pura), ma la finta deve poter reggere quel
    controllo il giorno in cui un test qui lo chiedesse."""
    return {"inizio": f"2026-08-24T{ora:02d}:00:00+00:00",
            "fine": f"2026-08-24T{ora + 1:02d}:00:00+00:00",
            "minimo": None, "massimo": None, "media": None, "cambio": cambio}


def test_il_doppione_con_hiris_ha_problems_e_documentato():
    sorgente = inspect.getsource(server)
    pos = sorgente.index('id="hiris_mind_conditions"')
    blocco = sorgente[pos - 1000:pos]
    assert "hiris_ha_problems" in blocco
    assert 'app["ha_problems"]' in blocco


# --------------------------------------------------------------------------
# Task 4 di «le tracce e il log»: l'evento segna, la cadenza breve raccoglie
# l'errore. Stessa disciplina del blocco sopra -- meta' cablaggio (il
# sorgente), meta' comportamento (`watch_automation_outcomes` esercitata per
# davvero con dei finti).
#
# Giro di correzioni (rilievo 6, primo punto): una prova di sola presenza
# nel sorgente (`"..." in inspect.getsource(server)`) passa verde anche se
# la riga vera e' commentata via -- un commento e' comunque testo, e la
# ricerca di sottostringa non distingue codice VIVO da un commento morto.
# `_chiamate_reali` sotto parsa il sorgente con `ast` invece di cercarci
# dentro: un commento non esiste per il parser, quindi una riga commentata
# semplicemente non produce nessuna `ast.Call` da trovare.
# --------------------------------------------------------------------------

def _real_calls(source_obj) -> list[str]:
    """Ogni chiamata di funzione REALMENTE presente nel sorgente di
    `source_obj` (non in un commento), come testo (`ast.unparse`)."""
    tree = ast.parse(inspect.getsource(source_obj))
    return [ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Call)]


def test_the_automation_event_is_wired_to_mark_automation():
    """Senza questo cablaggio `Watcher.mark_automation` non ha nessun
    chiamante di produzione: l'evento HA scatterebbe, `_ws_loop` lo
    dispaccerebbe ai suoi ascoltatori, e nessuno lo riceverebbe mai --
    nessuna automazione verrebbe mai segnata.

    Mutazione (verificata eseguendola): commentare via
    `ha_client.add_automation_listener(_mark_triggered_automation)`
    (lasciando il testo nel file, come farebbe chiunque disabiliti una
    riga senza cancellarla) -- il test torna rosso perche' `_real_calls`
    non trova piu' nessuna `ast.Call` che inizi con
    `"ha_client.add_automation_listener("`, mentre una ricerca di
    sottostringa sul sorgente grezzo resterebbe verde."""
    calls = _real_calls(server._on_startup)
    assert any(c.startswith("ha_client.add_automation_listener(") for c in calls)
    # `ast.unparse` normalizza le stringhe in apici singoli, quindi si cerca
    # `'watcher'` e non `"watcher"` (che e' come appare nel sorgente vero).
    assert any("['watcher'].mark_automation(entity_id" in c for c in calls)


def test_the_fourth_periodic_job_for_automation_traces_is_registered():
    """Senza questo lavoro `watch_automation_outcomes` non ha nessun
    chiamante di produzione: le automazioni segnate resterebbero segnate per
    sempre senza che nessuno rileggesse mai le loro tracce."""
    source = inspect.getsource(server)
    assert 'id="hiris_mind_automation_traces"' in source
    block = source[source.index('id="hiris_mind_automation_traces"') - 400:
                   source.index('id="hiris_mind_automation_traces"') + 200]
    assert "minutes=2" in block
    assert "watch_automation_outcomes" in source


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
    questo file NON riprova. `titles` (giro di correzioni, rilievo 5) e'
    cio' che torna `automation_title()` per entity_id -- vuoto di
    default."""

    def __init__(self, marked, *, result=True, titles=None):
        self._marked = list(marked)
        self.calls: list[tuple] = []
        self._result = result
        self._titles = dict(titles or {})

    def marked_automations(self):
        return list(self._marked)

    def automation_title(self, entity_id):
        return self._titles.get(entity_id)

    def watch_automation_outcome(self, entity_id, outcome, *, domain=None, title=None):
        self.calls.append((entity_id, outcome, domain, title))
        return self._result


class _FakeTracesClient:
    """Un `HAClient` finto per `automation_traces()`: `traces_by_automation_id`
    mappa **l'id di CONFIGURAZIONE** -- non l'`entity_id` -- al dizionario che
    il metodo vero deve tornare (`{"tracce": [...]}` o `{"errore": ...}`).

    **La chiave e' l'id di configurazione dal Task 6**, e non e' un dettaglio
    della finta: e' la proprieta' che questi test sorvegliano. Home Assistant
    archivia le tracce sotto `automation.<id della configurazione>` (catena
    verificata sui tag `2024.7.0` e `2026.9.0`, nel docstring di
    `HAClient.automation_traces()`), quindi un collettore che passasse
    l'`entity_id` -- come faceva la prima stesura -- non troverebbe nessuna
    chiave qui, esattamente come non ne trova nessuna sulla casa vera.

    Un id non presente nella mappa torna un guasto, non una lista vuota -- una
    finta che rispondesse `{"tracce": []}` di default nasconderebbe un
    errore di battitura nel test che la usa, e (peggio) farebbe passare verde
    proprio il difetto che questa fetta corregge. `calls` (giro di
    correzioni, rilievo 6, secondo punto) ricorda ogni id chiesto: senza,
    «`automation_traces` non deve mai essere chiamata» era una promessa nel
    docstring del test senza un assert che la sorvegliasse."""

    def __init__(self, traces_by_automation_id):
        self._traces = dict(traces_by_automation_id)
        self.calls: list[str] = []

    async def automation_traces(self, automation_id):
        self.calls.append(automation_id)
        return self._traces.get(
            automation_id, {"errore": f"nessuna finta per {automation_id}"})


class _FakeMirror:
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

    def __init__(self, config_id_by_entity):
        self._rows = []
        for entity_id, config_id in config_id_by_entity.items():
            attributes = {"friendly_name": entity_id}
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


def test_fake_automation_watcher_matches_watcher_automation_title():
    assert_stessa_firma(
        Watcher.automation_title, _FakeAutomationWatcher.automation_title,
        nome="Watcher.automation_title")


def test_fake_automation_watcher_matches_watcher_watch_automation_outcome():
    assert_stessa_firma(
        Watcher.watch_automation_outcome,
        _FakeAutomationWatcher.watch_automation_outcome,
        nome="Watcher.watch_automation_outcome")


def test_fake_traces_client_matches_haclient_automation_traces():
    from hiris.app.proxy.ha_client import HAClient
    assert_stessa_firma(HAClient.automation_traces, _FakeTracesClient.automation_traces,
                        nome="HAClient.automation_traces")


def test_without_a_watcher_the_traces_round_returns_none():
    result = asyncio.run(server.watch_automation_outcomes({}, _FakeTracesClient({})))
    assert result is None


def test_no_marked_automation_reads_no_trace():
    """`marked_automations()` vuota: il giro non deve chiamare
    `automation_traces` nemmeno una volta -- non c'e' niente da rileggere.
    (Giro di correzioni, rilievo 6, secondo punto: `_FakeTracesClient` ora
    registra le sue chiamate, quindi questa promessa e' davvero
    sorvegliata, non solo scritta nel docstring.)"""
    watcher = _FakeAutomationWatcher([])
    client = _FakeTracesClient({})
    result = asyncio.run(server.watch_automation_outcomes({"watcher": watcher}, client))
    assert result == 0
    assert watcher.calls == []
    assert client.calls == []


def test_every_trace_of_a_marked_automation_is_forwarded_in_order():
    """Tre tracce nella stessa risposta, con `run_id` diversi (nuovi al
    cursore): ognuna deve arrivare a `watch_automation_outcome`,
    nell'ordine in cui `automation_traces()` le ha restituite -- l'ordine
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
    client = _FakeTracesClient({
        "1771346155970": {"tracce": [
            {"run_id": "1", "script_execution": "finished"},
            {"run_id": "2", "script_execution": "failed_conditions"},
            {"run_id": "3", "script_execution": "error"},
        ]},
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
    client = _FakeTracesClient({
        "1771346155970": {"tracce": [
            {"run_id": "1", "script_execution": None},
        ]},
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
    client = _FakeTracesClient({
        "1771346155970": {"tracce": [
            {"run_id": "1", "script_execution": "error",
             "timestamp": {"start": "2020-01-01T00:00:00+00:00"}},
        ]},
    })
    app = {"watcher": watcher, "automation_traces_boot_ts": 1787572800.0,
           "entity_cache": _FakeMirror({"automation.x": "1771346155970"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert result == 0
    assert watcher.calls == []


def test_a_failed_read_for_one_automation_does_not_stop_the_others():
    """Una delle due automazioni segnate legge un `{"errore": ...}`: quella
    si salta, l'altra si legge lo stesso -- e' la disciplina del "parziale
    tollerato" (come `build_companions`), non quella del "tutto o niente"
    delle tre letture di sistema di `watch_system_conditions`.

    Mutazione (verificata eseguendola): `return written` invece di
    `continue` sul ramo `"errore" in report` -- interrompe il giro INTERO
    alla prima automazione rotta invece di saltare solo quella. Il test
    torna rosso su `assert result == 1` (tornerebbe `0`: `automation.buona`
    non verrebbe mai raggiunta, `watcher.calls` resterebbe vuota)."""
    watcher = _FakeAutomationWatcher(["automation.rotta", "automation.buona"])
    client = _FakeTracesClient({
        "1771346155970": {"errore": "Home Assistant non ha risposto"},
        "1771346155971": {"tracce": [{"run_id": "1", "script_execution": "error"}]},
    })
    app = {"watcher": watcher, "entity_cache": _FakeMirror({
        "automation.rotta": "1771346155970",
        "automation.buona": "1771346155971"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert result == 1
    assert [c[:2] for c in watcher.calls] == [("automation.buona", "error")]


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

    Mutazione (verificata eseguendola): `report = await
    ha_client.automation_traces(entity_id)` invece di `(automation_id)` -- il
    test torna rosso su `assert client.calls == ["1771346155970"]`, che
    riceve `["automation.luci_sera"]`; e anche su `assert result == 1`, che
    riceve `0`, perche' la finta non ha nessuna traccia sotto quella chiave
    (proprio come HA non ne ha).
    """
    watcher = _FakeAutomationWatcher(["automation.luci_sera"])
    client = _FakeTracesClient({
        "1771346155970": {"tracce": [{"run_id": "1", "script_execution": "error"}]},
    })
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.luci_sera": "1771346155970"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert client.calls == ["1771346155970"]
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
    `assert client.calls == ["1771346155971"]`, che riceve
    `["scritta_a_mano", "1771346155971"]`: la finta risponderebbe con un
    guasto inventato per quella chiave, cioe' esattamente il silenzio che
    Home Assistant produrrebbe davvero.
    """
    watcher = _FakeAutomationWatcher(
        ["automation.scritta_a_mano", "automation.buona"])
    client = _FakeTracesClient({
        "1771346155971": {"tracce": [{"run_id": "1", "script_execution": "error"}]},
    })
    app = {"watcher": watcher, "entity_cache": _FakeMirror({
        "automation.scritta_a_mano": None,
        "automation.buona": "1771346155971"})}

    result = asyncio.run(server.watch_automation_outcomes(app, client))

    assert client.calls == ["1771346155971"]
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
    client = _FakeTracesClient({})
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.scritta_a_mano": None})}

    with caplog.at_level(logging.DEBUG, logger="hiris.app.server"):
        for _ in range(3):
            asyncio.run(server.watch_automation_outcomes(app, client))

    levels = [r.levelname for r in caplog.records
              if "non si risolve dallo specchio" in r.getMessage()]
    assert levels == ["WARNING", "DEBUG", "DEBUG"]
    assert client.calls == []


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
    client = _FakeTracesClient({
        "1771346155970": {"tracce": [{"run_id": "1", "script_execution": "error"}]},
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
    client = _FakeTracesClient({
        "1771346155970": {"tracce": [{"run_id": "1", "script_execution": "error"}]},
    })
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.luci_sera": None})}

    blind_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert blind_round == 0
    assert client.calls == []
    assert "automation.luci_sera" not in app.get("automation_trace_cursors", {})

    # Lo specchio arriva: la traccia gia' conservata da HA e' NUOVA per il
    # cursore, e il fatto si scrive adesso invece di essere perso per sempre.
    app["entity_cache"] = _FakeMirror({"automation.luci_sera": "1771346155970"})
    seeing_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert seeing_round == 1
    assert client.calls == ["1771346155970"]


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
    client = _FakeTracesClient({
        "1771346155970": {"tracce": [
            {"run_id": "1", "script_execution": "finished"},
            {"run_id": "2", "script_execution": "error"},
        ]},
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
    client = _FakeTracesClient({
        "1771346155970": {"tracce": [
            {"run_id": "1", "script_execution": "error"},
            {"run_id": "2", "script_execution": "finished"},
        ]},
    })
    app = {"watcher": watcher,
           "entity_cache": _FakeMirror({"automation.guarita": "1771346155970"})}

    first_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert first_round == 2  # apre e chiude nello stesso giro
    assert store.count == 2

    second_round = asyncio.run(server.watch_automation_outcomes(app, client))
    assert second_round == 0
    assert store.count == 2


def test_il_sapere_nasce_PRIMA_della_riparazione_all_avvio():
    """**Un ordine di costruzione, difeso sul sorgente.**

    Dal 12/09/2026 la riparazione all'avvio legge le direzioni dal sapere
    (`app["knowledge"]`). Se qualcuno spostasse la creazione del sapere sotto
    la riparazione, quest'ultima prenderebbe `KeyError`, e il suo `except`
    largo lo inghiottirebbe: nel log comparirebbe «comprimari non costruiti,
    riparazione saltata» -- un messaggio che parla di un'ALTRA cosa, e due
    giorni di oggetti non si rifarebbero senza che nessuno capisca perche'.

    E' la stessa forma del controllo gia' in questo file su
    `home_space_store`, e nasce dalla stessa lezione: un ordine che vive solo
    nella testa di chi ha scritto il file non e' un ordine.

    Mutazione ESEGUITA: spostare `app["knowledge"] = KnowledgeStore(...)`
    sotto la chiamata a `reaggregate_last_two_days` -- rossa.
    """
    sorgente = inspect.getsource(server)

    assert (sorgente.index('app["knowledge"] = KnowledgeStore(')
            < sorgente.index("reaggregate_last_two_days(app, ha_client)"))


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
                "lette": True, "lingua": "it", "risorse": {
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

        assert sapere.count() == 0
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


def test_l_osservatore_riceve_il_sapere_e_nasce_DOPO_di_lui():
    """L'osservatore legge dal sapere quali attributi tenere (spec §5.4): se
    nascesse prima, prenderebbe `KeyError` all'avvio.

    Mutazione ESEGUITA: spostare `app["watcher"] = Watcher(...)` sopra la
    creazione del sapere -- rossa.
    """
    sorgente = inspect.getsource(server)

    assert 'Watcher(app["observations"], knowledge=app["knowledge"])' in sorgente
    assert (sorgente.index('app["knowledge"] = KnowledgeStore(')
            < sorgente.index('app["watcher"] = Watcher('))


def test_la_ricetta_del_bilancio_SI_SEMINA_nel_sapere_al_primo_giro(tmp_path):
    """**La meta' che mancava alla promessa della spec §7.**

    Finche' la ricetta si ricomponeva a ogni giro dentro il motore, la frase
    «come dato sarebbe correggibile senza un rilascio» era falsa: per cambiare
    quel conto serviva ancora un rilascio, esattamente come il 27/08/2026.

    Adesso il repo la genera dalle direzioni e la **semina**: da li' in poi e'
    una riga del sapere, e chi la corregge non aspetta nessuno. E' anche cio'
    che impedisce all'anello delle ricette di chiederne una seconda per lo
    stesso dispositivo -- due ricette per un dispositivo solo sarebbero la
    seconda fondamenta rotta.

    Mutazione ESEGUITA: togliere la `seed` da `_balance_recipe_for` -- rossa,
    e il dispositivo tornerebbe fra quelli da chiedere al modello.
    """
    from hiris.app.mind.recipe_turn import RECIPE_FIELD, recipe_for

    sapere = _sapere(tmp_path)
    ricetta = server._balance_recipe_for(
        sapere, "dev1", {"produzione": "sensor.p", "consumo": "sensor.c"}, 24)

    assert [p["name"] for p in ricetta["steps"]][:2] == ["produzione", "forma_produzione"]
    assert sapere.get("dispositivo", "dev1", RECIPE_FIELD) is not None
    assert recipe_for(sapere, "dev1")["why"]


def test_una_ricetta_GIA_SCRITTA_vince_su_quella_del_repo(tmp_path):
    """Se qualcuno ha corretto la ricetta -- a mano, o il modello -- il repo
    non la schiaccia: e' il senso di averla messa nel sapere."""
    import json

    from hiris.app.mind.knowledge import Fact
    from hiris.app.mind.recipe_turn import RECIPE_FIELD

    sapere = _sapere(tmp_path)
    sua = {"why": "corretta a mano", "steps": []}
    sapere.write(Fact(subject_kind="dispositivo", subject="dev1",
                      field=RECIPE_FIELD, value=json.dumps(sua),
                      provenance="chiesto", who="proprietario",
                      when_ts=1789000000.0))

    ricetta = server._balance_recipe_for(
        sapere, "dev1", {"produzione": "sensor.p"}, 24)

    assert ricetta["why"] == "corretta a mano"


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
             "knowledge": _sapere(tmp_path)}, ha_client=_ClienteStatistiche(),
            now=lambda tz: oggi.astimezone(tz)))

        for giorno in ("2026-08-22", "2026-08-23"):
            scritto = archivio.report(giorno)
            assert scritto is not None, f"il resoconto di {giorno} manca"
            assert scritto["giorno"] == giorno
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
        archivio.replace_report("2026-08-24", {"giorno": "2026-08-24",
                                               "misure": [], "forme": [],
                                               "cronaca": []})
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path)}

        scritto = asyncio.run(server.backfill_one_missing_report(
            app, ha_client=_ClienteStatistiche(), now=lambda tz: oggi.astimezone(tz)))
        assert scritto == "2026-08-22", scritto
        assert archivio.report("2026-08-22") is not None

        # Il giro dopo prende il successivo, e salta quello gia' scritto.
        assert asyncio.run(server.backfill_one_missing_report(
            app, ha_client=_ClienteStatistiche(),
            now=lambda tz: oggi.astimezone(tz))) == "2026-08-23"
    finally:
        archivio.close()


def test_il_recupero_TACE_quando_non_manca_piu_niente(tmp_path):
    """Finito il recupero, il giro non deve fare niente e non deve dirlo: un
    lavoro che stampa «niente da fare» ogni cinque minuti per sempre e' rumore
    sano che seppellisce cio' che e' rotto.

    Mutazione: tornare il giorno anche quando c'e' gia' -- rossa.
    """
    from datetime import datetime, timedelta

    from hiris.app.mind.store import ObservationsStore

    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 25, tzinfo=UTC)
        quando = (oggi - timedelta(days=1)).replace(hour=10)
        archivio.record(quando_ts=quando.timestamp(), source="entita",
                        subject="light.a", da="off", a="on")
        archivio.replace_report("2026-08-24", {"giorno": "2026-08-24",
                                               "misure": [], "forme": [],
                                               "cronaca": []})
        app = {"home_space_store": None, "observations": archivio,
               "knowledge": _sapere(tmp_path)}

        assert asyncio.run(server.backfill_one_missing_report(
            app, ha_client=_ClienteStatistiche(), now=lambda tz: oggi.astimezone(tz))) is None
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
               "knowledge": _sapere(tmp_path)}

        assert asyncio.run(server.backfill_one_missing_report(
            app, ha_client=_ClienteStatistiche(),
            now=lambda tz: oggi.astimezone(tz))) == "2026-08-23"
    finally:
        archivio.close()

def test_i_punti_orari_NON_buttano_media_minimo_e_massimo():
    """**La frase fondativa della spec, dentro il codice nuovo.** Il client
    legge gia' `mean`/`min`/`max` di Home Assistant e li traduce in
    `media`/`minimo`/`massimo`; `_punti_orari` teneva solo `cambio` e buttava
    gli altri tre. Le ricette ricevevano una serie di `None` e rifiutavano
    dicendo «la serie e' vuota»: misurato sulla casa vera il 14/09/2026,
    **21 misure su 32 in un giorno solo**, tutte su temperatura, umidita',
    CO2, rumore, segnale e potenza -- le **56** entita' della casa che hanno
    una statistica di tipo `measurement` e nessun `change`.

    Mutazione: tornare a tenere il solo `cambio` -- rossa.
    """
    punti = server._punti_orari([
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
