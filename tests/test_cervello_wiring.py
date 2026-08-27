"""L'osservatore esiste nell'app vera, e nasce DOPO cio' che gli serve.

Meta' di questo file prova il CABLAGGIO e non il comportamento, ed e'
deliberato: questo progetto ha gia' scoperto che uno strumento perfetto e non
cablato e' indistinguibile da uno assente.

L'altra meta' prova i due difetti che il mandato originale del Task 5
avrebbe lasciato nascere (task-5-correzioni.md):

  A. `guarda_sistema` senza nessun chiamante -- codice morto dal primo
     giorno, e la spec §6 diventata una frase falsa;
  A.1. un errore di lettura passato a `guarda_sistema` come lista vuota --
       peggio di non sapere, sapere il falso e scriverlo nell'archivio.
"""
import asyncio
import inspect
import logging
import re
import textwrap

from hiris.app import server
from hiris.app.cervello.archivio import CONSERVAZIONE_CAMBI_S
from hiris.app.server import guarda_condizioni_di_sistema
from tests.test_cervello_comprimari import _ClienteLegami


# --------------------------------------------------------------------------
# Il cablaggio dichiarato dal mandato (task-5-brief.md, Step 1)
# --------------------------------------------------------------------------

def test_l_archivio_e_l_osservatore_sono_cablati():
    sorgente = inspect.getsource(server)
    assert 'app["osservazioni"] = ArchivioOsservazioni(' in sorgente
    assert 'app["osservatore"] = Osservatore(' in sorgente


def test_l_osservatore_e_agganciato_allo_STESSO_rubinetto_dello_specchio():
    """Non si apre un secondo rubinetto: due sorgenti degli stessi eventi
    sarebbero due cose che possono divergere."""
    sorgente = inspect.getsource(server)
    assert "ha_client.add_state_listener(app[\"osservatore\"].guarda_cambio)" in sorgente
    assert sorgente.index("ha_client.add_state_listener(entity_cache.on_state_changed)") \
        < sorgente.index("ha_client.add_state_listener(app[\"osservatore\"].guarda_cambio)")


def test_l_osservatore_nasce_dopo_il_suo_archivio():
    sorgente = inspect.getsource(server)
    assert sorgente.index('app["osservazioni"] = ArchivioOsservazioni(') \
        < sorgente.index('app["osservatore"] = Osservatore(')


def test_i_due_lavori_periodici_sono_registrati():
    """L'aggregazione notturna e la potatura. Senza il primo il grezzo si
    accumula e nessun oggetto nasce; senza il secondo l'archivio cresce per
    sempre."""
    sorgente = inspect.getsource(server)
    assert 'id="hiris_cervello_aggregazione"' in sorgente
    assert 'id="hiris_cervello_potatura"' in sorgente


def test_l_archivio_si_chiude_nello_spegnimento():
    sorgente = inspect.getsource(server._on_cleanup)
    assert 'if "osservazioni" in app:' in sorgente
    assert 'app["osservazioni"].close()' in sorgente


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
    assert _kwargs_add_job(sorgente, "hiris_cervello_aggregazione") == {
        "hour": 0, "minute": 20}


def test_la_potatura_gira_alle_03_00():
    """Stessa tecnica, stesso difetto possibile: qui l'ora e' quella della
    notte (03:00), lontana dall'aggregazione (00:20) apposta -- l'una deve
    finire prima che l'altra cominci a leggere il grezzo."""
    sorgente = inspect.getsource(server)
    assert _kwargs_add_job(sorgente, "hiris_cervello_potatura") == {
        "hour": 3, "minute": 0}


# --------------------------------------------------------------------------
# Correzione A: la terza voce che il mandato originale dimenticava --
# `guarda_sistema` deve avere un chiamante vero, non restare morto.
# --------------------------------------------------------------------------

def test_il_terzo_lavoro_periodico_delle_condizioni_e_registrato():
    """Senza questo lavoro `guarda_sistema` non ha nessun chiamante di
    produzione: nasce codice morto lo stesso giorno in cui viene scritto, e
    la spec §6 (i guasti diventano oggetti dal primo giorno) diventa una
    frase falsa (task-5-correzioni.md, punto A)."""
    sorgente = inspect.getsource(server)
    assert 'id="hiris_cervello_condizioni"' in sorgente
    blocco = sorgente[sorgente.index('id="hiris_cervello_condizioni"') - 400:
                      sorgente.index('id="hiris_cervello_condizioni"') + 200]
    assert "minutes=10" in blocco
    assert "guarda_condizioni_di_sistema" in sorgente


def test_le_condizioni_si_leggono_anche_una_volta_all_avvio():
    """«Ogni 10 minuti, e una volta all'avvio» (punto A): senza la prima
    lettura all'avvio, un guasto gia' aperto da prima del boot resterebbe
    invisibile fino a dieci minuti dopo."""
    sorgente = inspect.getsource(server._on_startup)
    assert sorgente.count("guarda_condizioni_di_sistema(app, ha_client)") >= 2


def test_l_osservatore_ricostruisce_le_condizioni_all_avvio():
    """Punto B: senza questa chiamata, a ogni riavvio dell'add-on -- che
    succede a ogni aggiornamento -- i guasti gia' aperti verrebbero
    riscritti come nati adesso, e l'oggetto «guasto» perderebbe la sua unica
    informazione utile: da quando dura."""
    sorgente = inspect.getsource(server._on_startup)
    assert 'app["osservatore"].ricostruisci_condizioni()' in sorgente
    assert sorgente.index('app["osservatore"] = Osservatore(') \
        < sorgente.index('app["osservatore"].ricostruisci_condizioni()') \
        < sorgente.index('guarda_condizioni_di_sistema(app, ha_client)')


def _estrai_funzione_innestata(nome_funzione: str) -> str:
    """Il sorgente VERO di una funzione innestata in `_on_startup` (`async
    def <nome_funzione>...`), dalla sua riga di definizione alla riga vuota
    che la separa dal codice seguente (tipicamente `scheduler.add_job(...)`)
    -- la stessa tecnica di `tests/test_avvio_websocket.py` e
    `tests/test_potatura_notturna.py`: si esegue il sorgente vero isolato,
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
    ricorrente di questo progetto): oltre a tornare un numero da `pota()`,
    deve poter SOLLEVARE a comando, per provare che la potatura ha una rete
    propria (punto 3 del mandato)."""

    def __init__(self, quanti: int = 0, *, pota_solleva: bool = False):
        self._quanti = quanti
        self._pota_solleva = pota_solleva
        self.chiamate = 0

    def pota(self, adesso_ts):
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
    verificava che la riga `giorni = CONSERVAZIONE_CAMBI_S // 86400`
    ESISTESSE nel sorgente, non che la riga di log la USASSE davvero -- un
    mutante che tiene l'assegnazione morta e passa `21` letterale al posto
    di `giorni` restava verde. Qui si esegue la funzione vera e si legge il
    messaggio prodotto.

    Mutazione provata a mano: nella riga di log, `giorni` sostituito con
    `21` letterale (l'assegnazione morta restava). Rosso:
    `AssertionError: assert 'cervello: 5 cambi oltre i 21 giorni sono
    usciti' == 'cervello: 5 cambi oltre i 22 giorni sono usciti'`.
    Ripristinato subito dopo."""
    assert CONSERVAZIONE_CAMBI_S // 86400 == 22
    finto = _ArchivioOsservazioniFinto(quanti=5)
    logger_test = logging.getLogger("test_potatura_giorni")
    job = _carica_funzione_innestata("_pota_osservazioni", {
        "app": {"osservazioni": finto}, "_time": _tempo_fisso(0.0),
        "logger": logger_test, "CONSERVAZIONE_CAMBI_S": CONSERVAZIONE_CAMBI_S,
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
    job = _carica_funzione_innestata("_pota_osservazioni", {
        "app": {"osservazioni": finto}, "_time": _tempo_fisso(0.0),
        "logger": logger_test, "CONSERVAZIONE_CAMBI_S": CONSERVAZIONE_CAMBI_S,
    })

    with caplog.at_level(logging.INFO, logger="test_potatura_silenziosa"):
        asyncio.run(job())

    assert caplog.records == []


def test_la_potatura_non_lascia_uscire_l_eccezione(caplog):
    """Punto 3 del mandato: `_pota_osservazioni` era l'unico dei tre lavori
    SENZA un try/except suo -- un guasto di SQLite alle tre di notte finiva
    nel registro di apscheduler senza il prefisso 'cervello:', a differenza
    dei due lavori fratelli. Qui si prova che un errore di `pota()` sia
    catturato e loggato con quel prefisso, non lasciato propagare.

    La mutazione, qui, e' lo stato originale (nessun try/except): e' cio'
    che questo test trova rosso PRIMA della correzione -- `asyncio.run(job())`
    solleva `RuntimeError('disco pieno')` invece di tornare, e il test fallisce
    con quell'eccezione."""
    finto = _ArchivioOsservazioniFinto(pota_solleva=True)
    logger_test = logging.getLogger("test_potatura_rete")
    job = _carica_funzione_innestata("_pota_osservazioni", {
        "app": {"osservazioni": finto}, "_time": _tempo_fisso(0.0),
        "logger": logger_test, "CONSERVAZIONE_CAMBI_S": CONSERVAZIONE_CAMBI_S,
    })

    with caplog.at_level(logging.WARNING, logger="test_potatura_rete"):
        asyncio.run(job())  # non deve sollevare

    assert finto.chiamate == 1
    assert any(r.getMessage().startswith("cervello:") for r in caplog.records)


# --------------------------------------------------------------------------
# Correzione A.1: un errore di lettura non e' «tutto a posto». Qui si
# esercita `guarda_condizioni_di_sistema` per davvero, non solo il sorgente.
# --------------------------------------------------------------------------

class _OsservatoreFinto:
    def __init__(self):
        self.chiamate: list[dict] = []

    def guarda_sistema(self, *, problemi, integrazioni):
        self.chiamate.append({"problemi": problemi, "integrazioni": integrazioni})
        return len(problemi) + len(integrazioni)


class _ClienteFinto:
    """Un `HAClient` finto: `problemi_esito` e' cio' che torna `problemi()`,
    `registri_esito` la coppia `(registri, non_disponibili)` di
    `leggi_registri()`."""

    def __init__(self, problemi_esito, registri_esito):
        self._problemi_esito = problemi_esito
        self._registri_esito = registri_esito

    async def problemi(self):
        return self._problemi_esito

    async def leggi_registri(self):
        return self._registri_esito


def test_guarda_condizioni_chiama_guarda_sistema_quando_le_due_letture_riescono():
    osservatore = _OsservatoreFinto()
    app = {"osservatore": osservatore}
    cliente = _ClienteFinto(
        {"problemi": [{"domain": "hue", "issue_id": "x"}]},
        ({"integrazioni": [{"entry_id": "y", "state": "not_loaded"}]}, []))

    esito = asyncio.run(guarda_condizioni_di_sistema(app, cliente))

    assert esito == 2
    assert len(osservatore.chiamate) == 1
    assert osservatore.chiamate[0]["problemi"] == [{"domain": "hue", "issue_id": "x"}]
    assert osservatore.chiamate[0]["integrazioni"] == [{"entry_id": "y", "state": "not_loaded"}]


def test_un_errore_di_problemi_salta_il_giro_per_intero():
    """La prova per mutazione (task-5-correzioni.md, punto A.1): con
    `problemi()` che torna `{"errore": ...}`, `guarda_sistema` non viene
    chiamato. La mutazione (passare `[]` invece di saltare il giro) e' stata
    provata a mano durante l'implementazione e fa arrossire questa prova --
    non e' un'affermazione a vuoto."""
    osservatore = _OsservatoreFinto()
    app = {"osservatore": osservatore}
    cliente = _ClienteFinto(
        {"errore": "Home Assistant non ha risposto"},
        ({"integrazioni": []}, []))

    esito = asyncio.run(guarda_condizioni_di_sistema(app, cliente))

    assert esito is None
    assert osservatore.chiamate == []


def test_le_integrazioni_non_disponibili_saltano_il_giro_per_intero():
    """Identico per `leggi_registri`: se `"integrazioni"` e' in
    `non_disponibili`, quella lista e' vuota per guasto, non perche' vada
    tutto bene -- passarla cosi' com'e' chiuderebbe ogni integrazione gia'
    rotta come se si fosse appena risolta."""
    osservatore = _OsservatoreFinto()
    app = {"osservatore": osservatore}
    cliente = _ClienteFinto(
        {"problemi": []},
        ({"integrazioni": []}, ["integrazioni"]))

    esito = asyncio.run(guarda_condizioni_di_sistema(app, cliente))

    assert esito is None
    assert osservatore.chiamate == []


def test_senza_osservatore_non_scrive_niente():
    """Un `app` senza `"osservatore"` (avvio a meta', o un test che non lo
    costruisce): il giro tace invece di sollevare."""
    cliente = _ClienteFinto({"problemi": []}, ({"integrazioni": []}, []))

    esito = asyncio.run(guarda_condizioni_di_sistema({}, cliente))

    assert esito is None


# --------------------------------------------------------------------------
# Correzione punto 2 (task-5-fix-brief.md): se il fuso non si legge, quel
# giorno non viene aggregato MAI PIU' -- `fuso` e `ieri` erano calcolati
# FUORI dal try di `_aggrega_ieri`. Due correzioni distinte: (a) il minimo,
# le due righe dentro il try; (b) la cura vera, la riaggregazione
# incondizionata degli ultimi due giorni pieni all'avvio.
# --------------------------------------------------------------------------

class _ArchivioCasaCheSolleva:
    """`sistema_di_riferimento()` che solleva -- la sua query SQL, dice il
    mandato, non e' protetta: qui si simula il guasto vero, non solo
    l'assenza di `archivio_casa`."""

    def sistema_di_riferimento(self):
        raise RuntimeError("sqlite del sistema di riferimento irraggiungibile")


def test_l_aggregazione_notturna_logga_col_prefisso_cervello_anche_se_il_fuso_non_si_legge(caplog):
    """Punto 2(a): se `sistema_di_riferimento()` solleva, il warning
    contestualizzato ('cervello: ...') deve partire comunque -- non finire
    nel registro di apscheduler senza prefisso, cosa che succede quando
    `fuso`/`ieri` sono calcolati FUORI dal try.

    Prima della correzione questo test e' rosso per davvero, non per un
    assert: `asyncio.run(job())` solleva `RuntimeError`, perche' l'eccezione
    di `sistema_di_riferimento()` esce dalla funzione innestata prima ancora
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
        "app": {"archivio_casa": _ArchivioCasaCheSolleva()},
        "ha_client": None, "logger": logger_test,
        "aggrega_giorno": server.aggrega_giorno, "datetime": server.datetime,
        "timedelta": server.timedelta, "zona_casa": server.zona_casa,
        "confini_giorno": server.confini_giorno,
        "costruisci_comprimari": server.costruisci_comprimari,
        "_fuso_da_archivio_casa": server._fuso_da_archivio_casa,
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
    oggetti. Qui `ha_client=_ClienteLegami()`: senza `mappa`, ogni `legami`
    torna vuoto (nessun legame, non un guasto -- vedi il suo docstring),
    quindi nessun soggetto fallisce e la riparazione gira per intero come se
    fosse incondizionata. Deliberatamente non e' `ha_client=None`: con
    `None`, `costruisci_comprimari` chiamerebbe `None.legami(...)`,
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

    Nessun `from ... import riaggrega_gli_ultimi_due_giorni` in cima al
    file: se la funzione non esistesse ancora, l'errore deve fermare SOLO
    questo test (AttributeError a questa riga), non far fallire la
    collection dell'intero file -- la lezione del giro precedente."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=timezone.utc)
        for delta, soggetto in ((3, "vecchio"), (2, "l_altro_ieri"),
                                (1, "ieri"), (0, "oggi")):
            quando = (oggi - timedelta(days=delta)).replace(hour=10)
            archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                            soggetto=f"light.{soggetto}", da="off", a="on")

        asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
            {"archivio_casa": None, "osservazioni": archivio}, ha_client=_ClienteLegami(),
            adesso=lambda tz: oggi.astimezone(tz)))

        giorni_scritti = {o["giorno"] for o in archivio.oggetti(limite=10)}
        assert giorni_scritti == {"2026-08-22", "2026-08-23"}
        # Esplicito, non solo dedotto dall'uguaglianza sopra: oggi
        # ("2026-08-24") non deve avere NESSUN oggetto, nonostante il grezzo
        # per costruirlo ci sia.
        assert archivio.oggetti(giorno="2026-08-24") == []

        # Idempotente (`sostituisci_giorno`, non un doppio inserimento): un
        # secondo giro non deve raddoppiare gli oggetti dei due giorni.
        asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
            {"archivio_casa": None, "osservazioni": archivio}, ha_client=_ClienteLegami(),
            adesso=lambda tz: oggi.astimezone(tz)))
        assert len(archivio.oggetti(limite=10)) == 2
    finally:
        archivio.close()


def test_la_riparazione_all_avvio_costruisce_i_comprimari(tmp_path):
    """CRITICAL, punto 1 del mandato (riparazione-impoverisce-brief.md): la
    riparazione all'avvio costruisce i comprimari come fa la notte -- non
    piu' `comprimari=None`.

    Mutazione ESEGUITA: rimettere `comprimari=None` al posto della lambda
    che legge `mappa`, nel corpo di `riaggrega_gli_ultimi_due_giorni`.
    Arrossisce: `corpo["comprimari"]` di `light.principale` torna `[]`
    invece di `["light.secondario"]`."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=timezone.utc)
        quando = (oggi - timedelta(days=1)).replace(hour=10)
        archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                        soggetto="light.principale", da="off", a="on")
        archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                        soggetto="light.secondario", da="off", a="on")

        cliente = _ClienteLegami({"light.principale": {"entity": ["light.secondario"]}})
        asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
            {"archivio_casa": None, "osservazioni": archivio}, ha_client=cliente,
            adesso=lambda tz: oggi.astimezone(tz)))

        ieri = (oggi - timedelta(days=1)).strftime("%Y-%m-%d")
        [oggetto] = [o for o in archivio.oggetti(giorno=ieri)
                    if o["protagonista"] == "light.principale"]
        assert oggetto["corpo"]["comprimari"] == ["light.secondario"]
    finally:
        archivio.close()


def test_se_i_comprimari_non_si_costruiscono_l_archivio_resta_intatto(tmp_path):
    """CRITICAL, punto 2 del mandato -- **il test che conta**: e' l'unico che
    distingue «non guarisco» da «peggioro». Si semina il grezzo di ieri e
    l'altro ieri, si scrive PRIMA un oggetto ricco (con comprimari, come
    farebbe la notte) per entrambi i giorni -- poi si riaggrega con un
    client che risponde SEMPRE `{"errore": ...}`, non uno che solleva. Gli
    oggetti di prima devono restare ESATTAMENTE com'erano: quando i
    comprimari non si riescono a costruire, la riparazione non deve toccare
    l'archivio.

    **Correzione del CRITICAL vero (grilletto-brief.md).** La versione
    precedente di questo test monkeypatchava `costruisci_comprimari` per
    farla sollevare -- ma la funzione vera CONTIENE ogni guasto di `legami`
    (mette `[]`, conta un fallito, non rilancia mai), quindi quel ramo
    `except` in `riaggrega_gli_ultimi_due_giorni` era irraggiungibile dal
    collaboratore vero. Il test passava per un motivo che la produzione non
    incontra mai. Qui si usa `_ClienteLegami(default={"errore": ...})`, che
    risponde come risponde Home Assistant quando non c'e' davvero per
    QUALUNQUE soggetto, e nessun monkeypatch: la catena e' quella vera,
    `legami` -> `costruisci_comprimari` -> il contatore dei falliti che ora
    torna al chiamante.

    Mutazione ESEGUITA: nel corpo di `riaggrega_gli_ultimi_due_giorni`, il
    controllo `if falliti:` sostituito con `if False:` (ignorare il
    contatore, come prima della correzione). Arrossisce: gli oggetti ricchi
    vengono sostituiti da oggetti senza comprimari -- `dopo != prima` --
    esattamente il peggioramento che il mandato descrive. Ripristinato
    subito dopo."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=timezone.utc)
        l_altro_ieri = (oggi - timedelta(days=2)).strftime("%Y-%m-%d")
        ieri = (oggi - timedelta(days=1)).strftime("%Y-%m-%d")
        for giorno, delta in ((l_altro_ieri, 2), (ieri, 1)):
            quando = (oggi - timedelta(days=delta)).replace(hour=10)
            archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                            soggetto="light.principale", da="off", a="on")

        # Il "gia' fatto dalla notte": un oggetto CON comprimari, per
        # entrambi i giorni bersaglio.
        ricco = [{"genere": "funzionamento", "protagonista": "light.principale",
                  "inizio_ts": 0.0, "fine_ts": 1.0,
                  "corpo": {"stato": "on", "comprimari": ["light.secondario"],
                           "misure": {}}}]
        archivio.sostituisci_giorno(l_altro_ieri, ricco)
        archivio.sostituisci_giorno(ieri, ricco)
        prima = {g: archivio.oggetti(giorno=g) for g in (l_altro_ieri, ieri)}

        asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
            {"archivio_casa": None, "osservazioni": archivio},
            ha_client=_ClienteLegami(default={"errore": "Home Assistant non ha risposto"}),
            adesso=lambda tz: oggi.astimezone(tz)))

        dopo = {g: archivio.oggetti(giorno=g) for g in (l_altro_ieri, ieri)}
        assert dopo == prima
    finally:
        archivio.close()


def test_una_risposta_malformata_ferma_la_riparazione_senza_scrivere(tmp_path, caplog):
    """Punto 1 (difesa-profondita-brief.md): il ramo protettivo di «difesa in
    profondita'» attorno alla chiamata a `costruisci_comprimari`, dentro
    `riaggrega_gli_ultimi_due_giorni`, non lo sorvegliava nessun test. Una
    mutazione che lo facesse proseguire con `mappa` vuota e `falliti == 0` --
    esattamente il peggioramento che il ramo esiste per impedire -- restava
    verde in tutta la suite.

    **L'innesco e' producibile SENZA monkeypatch.** Un client che risponde
    `{"entity": 5}` -- un intero al posto della lista che Home Assistant
    manda sempre -- fa uscire un `TypeError` VERO dalla catena vera: non da
    `costruisci_comprimari` (che CONTIENE solo il guasto di `HAClient.legami`
    stesso, non la forma della sua risposta buona), ma da
    `casa/domande.py::legami` (`_legami_leggibili`, chiamata da
    `costruisci_comprimari` FUORI dal suo `try/except` interno): `list(5)`
    solleva mentre traduce le chiavi. E' il controesempio del punto 2: la
    frase «nessuna `Exception` esce mai da qui» era falsa esattamente per
    questo caso, corretta in questo stesso giro.

    Mutazione ESEGUITA: nel corpo di `riaggrega_gli_ultimi_due_giorni`, il
    blocco `except Exception as errore: logger.warning(...); return`
    sostituito con `except Exception: mappa, falliti = {}, 0` (proseguire con
    la mappa vuota invece di fermarsi, come se il guasto non fosse successo).
    Arrossisce su entrambi gli assert: l'oggetto ricco viene sostituito da un
    oggetto senza comprimari (`dopo != prima`), e il messaggio atteso non
    compare piu' nel log. Ripristinato subito dopo."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=timezone.utc)
        l_altro_ieri = (oggi - timedelta(days=2)).strftime("%Y-%m-%d")
        ieri = (oggi - timedelta(days=1)).strftime("%Y-%m-%d")
        for giorno, delta in ((l_altro_ieri, 2), (ieri, 1)):
            quando = (oggi - timedelta(days=delta)).replace(hour=10)
            archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                            soggetto="light.principale", da="off", a="on")

        # Il "gia' fatto dalla notte": un oggetto CON comprimari, per
        # entrambi i giorni bersaglio.
        ricco = [{"genere": "funzionamento", "protagonista": "light.principale",
                  "inizio_ts": 0.0, "fine_ts": 1.0,
                  "corpo": {"stato": "on", "comprimari": ["light.secondario"],
                           "misure": {}}}]
        archivio.sostituisci_giorno(l_altro_ieri, ricco)
        archivio.sostituisci_giorno(ieri, ricco)
        prima = {g: archivio.oggetti(giorno=g) for g in (l_altro_ieri, ieri)}

        # La risposta MALFORMATA: un intero al posto della lista.
        cliente = _ClienteLegami({"light.principale": {"entity": 5}})
        with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
            asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
                {"archivio_casa": None, "osservazioni": archivio}, ha_client=cliente,
                adesso=lambda tz: oggi.astimezone(tz)))

        dopo = {g: archivio.oggetti(giorno=g) for g in (l_altro_ieri, ieri)}
        assert dopo == prima

        assert any(
            r.getMessage() == "cervello: comprimari non costruiti, riparazione "
                              "all'avvio saltata -- si riprova al prossimo riavvio "
                              "(TypeError: 'int' object is not iterable)"
            for r in caplog.records)
    finally:
        archivio.close()


def test_un_guasto_parziale_dei_comprimari_non_tocca_l_archivio(tmp_path):
    """Rilievo n.2 del referto (grilletto-brief.md): **quanto parziale e'
    troppo, per la riparazione, e' qualunque.** Un soggetto su due fallisce,
    l'altro riesce -- ma quel soggetto verrebbe comunque riscritto con `[]`
    mentre la notte l'aveva letto. La riparazione deve fermarsi lo stesso,
    non solo sul guasto totale provato sopra."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=timezone.utc)
        ieri = (oggi - timedelta(days=1)).strftime("%Y-%m-%d")
        quando = (oggi - timedelta(days=1)).replace(hour=10)
        for soggetto in ("light.buono", "light.rotto"):
            archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                            soggetto=soggetto, da="off", a="on")

        ricco = [{"genere": "funzionamento", "protagonista": "light.rotto",
                  "inizio_ts": 0.0, "fine_ts": 1.0,
                  "corpo": {"stato": "on", "comprimari": ["light.secondario"],
                           "misure": {}}}]
        archivio.sostituisci_giorno(ieri, ricco)
        prima = archivio.oggetti(giorno=ieri)

        cliente = _ClienteLegami({
            "light.rotto": {"errore": "Home Assistant non ha risposto"},
            "light.buono": {"entity": ["sensor.buono"]}})
        asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
            {"archivio_casa": None, "osservazioni": archivio},
            ha_client=cliente,
            adesso=lambda tz: oggi.astimezone(tz)))

        assert archivio.oggetti(giorno=ieri) == prima
    finally:
        archivio.close()


def test_il_salto_per_falliti_logga_il_messaggio_preciso(tmp_path, caplog):
    """Punto 3 (difesa-profondita-brief.md): il warning che avvisa che la
    riparazione e' stata saltata per `falliti` (non per un'eccezione: quello
    e' il test gemello sopra) e' l'unica traccia visibile all'operatore di un
    mancato recupero -- storpiarlo lascerebbe tutto verde, e nessun test in
    tutta la codebase lo asserisce ancora sul testo preciso. Stesso schema
    gia' chiuso per `_aggrega_ieri` (vedi il test omonimo piu' sopra, che
    assertava solo `startswith` prima della sua correzione): chiuderlo su un
    messaggio e lasciarlo aperto sul suo gemello sarebbe la fondamenta della
    consistenza, rotta fra due righe vicine.

    Mutazione ESEGUITA: nel corpo di `riaggrega_gli_ultimi_due_giorni`, tolte
    le parole "per intero" dal testo del warning nel ramo `if falliti:`.
    Arrossisce: nessun record col testo atteso in `caplog`. Ripristinato
    subito dopo."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=timezone.utc)
        quando = (oggi - timedelta(days=1)).replace(hour=10)
        archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                        soggetto="light.rotto", da="off", a="on")

        cliente = _ClienteLegami(default={"errore": "Home Assistant non ha risposto"})
        with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
            asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
                {"archivio_casa": None, "osservazioni": archivio}, ha_client=cliente,
                adesso=lambda tz: oggi.astimezone(tz)))

        assert any(
            r.getMessage() == "cervello: comprimari parziali (1 falliti), "
                              "riparazione all'avvio saltata per intero -- "
                              "si riprova al prossimo riavvio"
            for r in caplog.records)
    finally:
        archivio.close()


def test_l_aggregazione_notturna_prosegue_con_lo_stesso_guasto_parziale(tmp_path):
    """L'altra meta' della regola (grilletto-brief.md): **chi costruisce dal
    nulla tollera il parziale.** Nello STESSO scenario del test sopra (un
    soggetto su due fallisce), l'aggregazione notturna (`_aggrega_ieri`) non
    deve fermarsi -- costruisce l'oggetto del giorno da zero, e un oggetto
    con un comprimare mancante e' meglio di nessun oggetto. Senza questo
    test, la correzione del CRITICAL potrebbe fermare anche la notte insieme
    alla riparazione all'avvio -- lo stesso `if falliti:` messo nel punto
    sbagliato lo farebbe.

    `_aggrega_ieri` legge `datetime.now()` per davvero (non e' iniettabile
    come `adesso` di `riaggrega_gli_ultimi_due_giorni`): il grezzo si semina
    per "ieri" vero, rispetto all'orologio reale del test."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        adesso_reale = datetime.now(timezone.utc)
        ieri = adesso_reale - timedelta(days=1)
        quando = ieri.replace(hour=10, minute=0, second=0, microsecond=0)
        for soggetto in ("light.buono", "light.rotto"):
            archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                            soggetto=soggetto, da="off", a="on")

        logger_test = logging.getLogger("test_aggrega_ieri_parziale")
        cliente = _ClienteLegami({
            "light.rotto": {"errore": "Home Assistant non ha risposto"},
            "light.buono": {"entity": ["sensor.buono"]}})
        job = _carica_funzione_innestata("_aggrega_ieri", {
            "app": {"archivio_casa": None, "osservazioni": archivio},
            "ha_client": cliente,
            "logger": logger_test,
            "aggrega_giorno": server.aggrega_giorno, "datetime": server.datetime,
            "timedelta": server.timedelta, "zona_casa": server.zona_casa,
            "confini_giorno": server.confini_giorno,
            "costruisci_comprimari": server.costruisci_comprimari,
            "_fuso_da_archivio_casa": server._fuso_da_archivio_casa,
        })

        asyncio.run(job())

        ieri_str = ieri.strftime("%Y-%m-%d")
        oggetti = archivio.oggetti(giorno=ieri_str)
        assert {o["protagonista"] for o in oggetti} == {"light.buono", "light.rotto"}
        rotto = [o for o in oggetti if o["protagonista"] == "light.rotto"][0]
        assert rotto["corpo"]["comprimari"] == []
        buono = [o for o in oggetti if o["protagonista"] == "light.buono"][0]
        assert buono["corpo"]["comprimari"] == ["sensor.buono"]
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
    `app["archivio_casa"]` -- esiste gia'. E' esattamente cosi' che il
    CRITICAL del punto 1 e' rimasto invisibile per due giri: la chiamata
    stava "dopo le condizioni" (verificato, verde) ma anche 87 righe PRIMA
    della creazione di `archivio_casa` (non verificato, mai stato rosso).
    La sorveglianza vera, per COMPORTAMENTO, e' il test qui sotto,
    `test_la_riparazione_di_avvio_riceve_archivio_casa_gia_costruito`, che
    esegue la fetta reale del sorgente e legge cosa la riparazione riceve
    DAVVERO."""
    sorgente = inspect.getsource(server._on_startup)
    assert "riaggrega_gli_ultimi_due_giorni(app, ha_client)" in sorgente
    assert sorgente.index('app["osservatore"].ricostruisci_condizioni()') \
        < sorgente.index("riaggrega_gli_ultimi_due_giorni(app, ha_client)")
    pos = sorgente.index("riaggrega_gli_ultimi_due_giorni(app, ha_client)")
    blocco = sorgente[pos - 80:pos + 200]
    assert "try:" in blocco
    assert "except Exception" in blocco


def _estrai_blocco_riparazione_avvio() -> str:
    """Il sorgente VERO di `_on_startup`, dalla creazione di `archivio_casa`
    alla fine del try/except della riparazione all'avvio -- stessa tecnica di
    `_estrai_funzione_innestata`, ma su una FETTA contigua invece che su una
    funzione innestata: e' il modo di eseguire per davvero l'ordine fra le
    due righe, invece di dedurlo confrontando due indici di stringa.

    Se la chiamata alla riparazione torna a stare PRIMA della creazione di
    `archivio_casa` (la regressione del punto 1), il marcatore di fine non si
    trova piu' DOPO quello di inizio, e `sorgente.index(marcatore_fine,
    inizio)` solleva `ValueError` -- un rosso esplicito sull'estrazione
    stessa, non un'asserzione che potrebbe passare per la ragione sbagliata."""
    src = inspect.getsource(server._on_startup)
    marcatore_inizio = 'archivio_casa = ArchivioCasa(os.path.join(data_dir, "casa.db"))'
    marcatore_fine = '"fallita (%s: %s)", type(exc).__name__, exc)'
    inizio = src.index(marcatore_inizio)
    # Dall'INIZIO DELLA RIGA, non dal marcatore: altrimenti la prima riga
    # perderebbe la sua indentazione (il marcatore comincia dopo gli spazi)
    # e `textwrap.dedent` calcolerebbe un prefisso comune vuoto -- ogni riga
    # successiva, ancora indentata, diventerebbe un `IndentationError`.
    inizio_riga = src.rfind("\n", 0, inizio) + 1
    fine = src.index(marcatore_fine, inizio) + len(marcatore_fine)
    return textwrap.dedent(src[inizio_riga:fine])


def test_la_riparazione_di_avvio_riceve_archivio_casa_gia_costruito(tmp_path):
    """La sorveglianza per COMPORTAMENTO del punto 1 (CRITICAL,
    cancello-rilascio-brief.md): si esegue la fetta VERA di `_on_startup` che
    crea `archivio_casa`, lo mette in `app`, e subito dopo chiama la
    riparazione -- con la riparazione sostituita da una spia che registra
    cosa ha ricevuto. Non un `assert` su una posizione di stringa: la prova
    che, quando la riparazione gira per davvero, il collaboratore che le
    serve per leggere il fuso della casa (`archivio_casa`, non `None`) e'
    gia' li'.

    Le finte di TUTTI gli altri test di questo file (sopra) passano
    `"archivio_casa": None` a `riaggrega_gli_ultimi_due_giorni` -- fedeli
    alla produzione ROTTA, come rilevato dal cancello del rilascio: nessuna
    di loro poteva vedere questo difetto, per costruzione. Questo test e' il
    solo che guarda l'ORDINE VERO invece di darlo per assunto.

    Mutazione ESEGUITA: spostando a mano la chiamata alla riparazione (e il
    suo blocco di commento) di nuovo sopra la riga `archivio_casa =
    ArchivioCasa(...)`, com'era prima di questo giro -- `_estrai_blocco_
    riparazione_avvio` solleva `ValueError: substring not found`, perche' il
    marcatore di fine non compare piu' dopo quello di inizio. Rosso,
    esplicito. Ripristinato subito dopo."""
    import os as os_reale

    ricevuto: dict = {}

    async def _spia(app, ha_client):
        ricevuto["archivio_casa"] = app.get("archivio_casa")

    namespace = {
        "os": os_reale, "data_dir": str(tmp_path), "ArchivioCasa": server.ArchivioCasa,
        "app": {}, "ha_client": None,
        "riaggrega_gli_ultimi_due_giorni": _spia,
        "logger": logging.getLogger("test_riparazione_riceve_archivio_casa"),
    }
    corpo = _estrai_blocco_riparazione_avvio()
    func_src = "async def _check():\n" + textwrap.indent(corpo, "    ")
    exec(compile(func_src, "<_on_startup riparazione avvio>", "exec"), namespace)

    try:
        asyncio.run(namespace["_check"]())
        assert ricevuto.get("archivio_casa") is not None
        assert isinstance(ricevuto["archivio_casa"], server.ArchivioCasa)
        assert ricevuto["archivio_casa"] is namespace["app"]["archivio_casa"]
    finally:
        namespace["app"]["archivio_casa"].chiudi()


def test_le_due_porte_sullo_stesso_grezzo_producono_gli_stessi_oggetti(tmp_path):
    """Fondamenta n.3 (cancello-rilascio-brief.md, punto 1, CRITICAL -- la
    terza volta che questa fondamenta si rompe sulla stessa funzione): le due
    porte che aggregano il grezzo in oggetti -- l'aggregazione notturna
    (mimata qui chiamando `aggrega_giorno` col fuso letto da `archivio_casa`,
    come fa `_aggrega_ieri`) e la riparazione all'avvio -- devono produrre GLI
    STESSI oggetti dato lo STESSO grezzo.

    **La porta 2 non chiama `riaggrega_gli_ultimi_due_giorni` a mano**: esegue
    la fetta VERA di `_on_startup` (`_estrai_blocco_riparazione_avvio`, sopra)
    con la funzione VERA -- non una finta, non un `app` costruito a mano con
    `archivio_casa` gia' dentro. E' la differenza che conta: un `app`
    preparato a mano da questo test "sa" gia' come va a finire, e non
    avrebbe potuto vedere il difetto del punto 1 (la chiamata era 87 righe
    PRIMA che `archivio_casa` esistesse in `app`) -- sarebbe stato un test
    che non puo' fallire per la ragione sbagliata, esattamente il vizio che
    ha lasciato vivere questo difetto per due giri precedenti. Qui `app`
    parte con solo `"osservazioni"`, come nel vero `_on_startup` in quel
    punto, e `archivio_casa` nasce dentro l'estratto, esattamente come nasce
    nel sorgente vero.

    Il fuso arriva a `archivio_casa` non da una chiamata di rete (il finto
    `ha_client` non la sa fare), ma da cio' che e' gia' scritto su
    `casa.db`: `sistema_di_riferimento()` legge il fuso PERSISTITO dalle
    sessioni precedenti, esattamente come lo leggerebbe un vero riavvio
    dell'add-on (`casa.db` sopravvive ai riavvii). Il file si semina una
    volta, PRIMA di eseguire l'estratto, con una `ArchivioCasa` separata che
    viene chiusa subito dopo: l'estratto ne apre una sua, fresca, sullo
    stesso percorso.

    **Provato eseguendo** (revisore, 26/08/2026, ripetuto qui): un
    riscaldamento acceso 00:30-01:30 ora di Roma (CEST, UTC+2 in agosto --
    che in UTC ricade nella sera del giorno PRIMA) piu' un ciclo pomeridiano
    nello stesso giorno di Roma. Prima della correzione del punto 1, la
    notte produceva 2 oggetti per quel giorno e la riparazione (che leggeva
    sempre `fuso=None`, cioe' UTC, perche' `archivio_casa` non esisteva
    ancora in `app` nel punto vero della chiamata) ne produceva 1: l'episodio
    notturno spariva dal giorno a cui appartiene davvero.

    Mutazione ESEGUITA: rimettendo a mano, in `server.py`, la chiamata alla
    riparazione dov'era prima di questo giro (87 righe piu' in alto, prima
    della creazione di `archivio_casa`) -- questo test arrossisce con
    `ValueError: substring not found` dentro `_estrai_blocco_riparazione_
    avvio` (lo stesso rosso di `test_la_riparazione_di_avvio_riceve_
    archivio_casa_gia_costruito`, verificato li' per esteso). Verificato a
    mano anche qui, ripristinato subito dopo."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from hiris.app.casa.archivio import ArchivioCasa
    from hiris.app.cervello.archivio import ArchivioOsservazioni

    roma = ZoneInfo("Europe/Rome")
    # Due giorni fa: e' uno dei due bersagli della riparazione all'avvio
    # (`giorni = [oggi-2, oggi-1]`), e resta stabile anche se il test
    # attraversa la mezzanotte fra la semina e l'esecuzione.
    giorno_bersaglio_data = datetime.now(roma).date() - timedelta(days=2)
    giorno_bersaglio = giorno_bersaglio_data.strftime("%Y-%m-%d")

    casa_db = str(tmp_path / "casa.db")
    osservazioni_db = str(tmp_path / "osservazioni.db")

    seme = ArchivioCasa(casa_db)
    seme.sostituisci({}, [], sistema_di_riferimento={"fuso": "Europe/Rome"})
    seme.chiudi()

    archivio = ArchivioOsservazioni(osservazioni_db)
    try:
        base = datetime(giorno_bersaglio_data.year, giorno_bersaglio_data.month,
                        giorno_bersaglio_data.day, tzinfo=roma)
        cambi = [
            (base.replace(hour=0, minute=30), "off", "heat"),
            (base.replace(hour=1, minute=30), "heat", "off"),
            (base.replace(hour=15, minute=0), "off", "heat"),
            (base.replace(hour=16, minute=0), "heat", "off"),
        ]
        for quando, da, a in cambi:
            archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                            soggetto="climate.soggiorno", da=da, a=a)

        # Porta 1 -- la notte: fuso letto da `archivio_casa` gia' presente,
        # come farebbe `_aggrega_ieri` alle 00:20.
        server.aggrega_giorno(archivio=archivio, giorno=giorno_bersaglio,
                              fuso="Europe/Rome", comprimari=lambda s: [])
        oggetti_notte = archivio.oggetti(giorno=giorno_bersaglio)
        assert len(oggetti_notte) == 2

        # Si riparte dal grezzo puro: la riparazione deve arrivare allo
        # STESSO risultato per conto suo, non ereditare il lavoro della notte.
        archivio.sostituisci_giorno(giorno_bersaglio, [])

        # Porta 2 -- la riparazione all'avvio, per DAVVERO: la fetta vera del
        # sorgente, con la funzione vera. `app` parte senza `archivio_casa`,
        # come nel vero `_on_startup` in quel punto.
        import os as os_reale
        cliente = _ClienteLegami()
        namespace = {
            "os": os_reale, "data_dir": str(tmp_path), "ArchivioCasa": server.ArchivioCasa,
            "app": {"osservazioni": archivio}, "ha_client": cliente,
            "riaggrega_gli_ultimi_due_giorni": server.riaggrega_gli_ultimi_due_giorni,
            "logger": logging.getLogger("test_due_porte"),
        }
        corpo = _estrai_blocco_riparazione_avvio()
        func_src = "async def _check():\n" + textwrap.indent(corpo, "    ")
        exec(compile(func_src, "<_on_startup riparazione avvio -- due porte>", "exec"),
            namespace)
        try:
            asyncio.run(namespace["_check"]())
        finally:
            namespace["app"]["archivio_casa"].chiudi()

        oggetti_riparazione = archivio.oggetti(giorno=giorno_bersaglio)

        def _normalizza(elenco):
            return sorted(
                ({k: v for k, v in o.items() if k != "id"} for o in elenco),
                key=lambda o: (o["protagonista"], o["inizio_ts"]))

        assert _normalizza(oggetti_notte) == _normalizza(oggetti_riparazione)
    finally:
        archivio.close()


def test_se_la_riaggregazione_solleva_l_avvio_prosegue(caplog):
    """Comportamento, non testo: si esegue il VERO try/except del punto di
    chiamata, con `riaggrega_gli_ultimi_due_giorni` sostituita da una finta
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
    `try:` PRECEDENTE (quello di `guarda_condizioni_di_sistema`, qui
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
                '        await riaggrega_gli_ultimi_due_giorni(app, ha_client)')
    inizio = sorgente.index(marcatore)
    fine = sorgente.index("\n\n", inizio)
    corpo = textwrap.dedent(sorgente[inizio:fine])

    async def _che_solleva(app, ha_client):
        raise RuntimeError("archivio irraggiungibile")

    logger_test = logging.getLogger("test_riaggrega_avvio_non_blocca")
    namespace = {"app": {}, "ha_client": None,
                "riaggrega_gli_ultimi_due_giorni": _che_solleva,
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
# parziale, chi sostituisce (`riaggrega_gli_ultimi_due_giorni`) no.
# --------------------------------------------------------------------------

def test_l_aggregazione_notturna_chiede_le_direzioni_una_volta(tmp_path):
    """`_aggrega_ieri` chiama `ha_client.direzioni_energia()` -- una volta
    sola per il giro, non per soggetto -- e la usa per gli episodi di
    energia del giorno."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        adesso_reale = datetime.now(timezone.utc)
        ieri = adesso_reale - timedelta(days=1)
        for ora, valore in ((1, "10.0"), (20, "25.0")):
            quando = ieri.replace(hour=ora, minute=0, second=0, microsecond=0)
            archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                            soggetto="sensor.energia_prodotta", da=None, a=valore,
                            device_class="energy")

        cliente = _ClienteLegami(direzioni={
            "sensor.energia_prodotta": {"direzione": "produzione", "provenienza": "dichiarata"}})
        logger_test = logging.getLogger("test_aggrega_ieri_direzioni")
        job = _carica_funzione_innestata("_aggrega_ieri", {
            "app": {"archivio_casa": None, "osservazioni": archivio},
            "ha_client": cliente, "logger": logger_test,
            "aggrega_giorno": server.aggrega_giorno, "datetime": server.datetime,
            "timedelta": server.timedelta, "zona_casa": server.zona_casa,
            "confini_giorno": server.confini_giorno,
            "costruisci_comprimari": server.costruisci_comprimari,
            "_fuso_da_archivio_casa": server._fuso_da_archivio_casa,
        })

        asyncio.run(job())

        assert cliente.direzioni_chieste == 1
        ieri_str = ieri.strftime("%Y-%m-%d")
        [oggetto] = archivio.oggetti(giorno=ieri_str)
        assert oggetto["corpo"]["direzione"] == "produzione"
        assert oggetto["corpo"]["provenienza"] == "dichiarata"
    finally:
        archivio.close()


def test_l_aggregazione_notturna_prosegue_se_le_direzioni_non_si_leggono(tmp_path):
    """**Chi costruisce dal nulla tollera il parziale**, identico alla regola
    gia' presa per i comprimari (vedi i test gemelli piu' sopra): un guasto
    di `direzioni_energia()` non deve fermare la notte. L'episodio nasce
    comunque, senza `direzione`/`provenienza` -- non un oggetto in meno,
    solo un oggetto piu' povero."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        adesso_reale = datetime.now(timezone.utc)
        ieri = adesso_reale - timedelta(days=1)
        quando = ieri.replace(hour=10, minute=0, second=0, microsecond=0)
        archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                        soggetto="sensor.energia_x", da=None, a="5.0",
                        device_class="energy")

        cliente = _ClienteLegami(direzioni_errore="Home Assistant non ha risposto")
        logger_test = logging.getLogger("test_aggrega_ieri_direzioni_guasto")
        job = _carica_funzione_innestata("_aggrega_ieri", {
            "app": {"archivio_casa": None, "osservazioni": archivio},
            "ha_client": cliente, "logger": logger_test,
            "aggrega_giorno": server.aggrega_giorno, "datetime": server.datetime,
            "timedelta": server.timedelta, "zona_casa": server.zona_casa,
            "confini_giorno": server.confini_giorno,
            "costruisci_comprimari": server.costruisci_comprimari,
            "_fuso_da_archivio_casa": server._fuso_da_archivio_casa,
        })

        asyncio.run(job())  # non deve sollevare

        ieri_str = ieri.strftime("%Y-%m-%d")
        [oggetto] = archivio.oggetti(giorno=ieri_str)
        assert oggetto["genere"] == "energia"
        assert "direzione" not in oggetto["corpo"]
        assert "provenienza" not in oggetto["corpo"]
    finally:
        archivio.close()


def test_la_riparazione_all_avvio_applica_le_direzioni(tmp_path):
    """Simmetrico al test dei comprimari (`test_la_riparazione_all_avvio_
    costruisce_i_comprimari`): quando la lettura riesce, gli episodi di
    energia riscritti dalla riparazione portano `direzione`/`provenienza`."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=timezone.utc)
        quando = (oggi - timedelta(days=1)).replace(hour=10)
        archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                        soggetto="sensor.energia_prelievo", da=None, a="12.0",
                        device_class="energy")

        cliente = _ClienteLegami(direzioni={
            "sensor.energia_prelievo": {"direzione": "prelievo", "provenienza": "dichiarata"}})
        asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
            {"archivio_casa": None, "osservazioni": archivio}, ha_client=cliente,
            adesso=lambda tz: oggi.astimezone(tz)))

        ieri = (oggi - timedelta(days=1)).strftime("%Y-%m-%d")
        [oggetto] = archivio.oggetti(giorno=ieri)
        assert oggetto["corpo"]["direzione"] == "prelievo"
        assert oggetto["corpo"]["provenienza"] == "dichiarata"
    finally:
        archivio.close()


def test_la_riparazione_all_avvio_si_ferma_se_le_direzioni_non_si_leggono(tmp_path):
    """**Il test che conta, gemello di `test_se_i_comprimari_non_si_
    costruiscono_l_archivio_resta_intatto`**: qui i COMPRIMARI si leggono
    benissimo (`falliti == 0`), ma le DIREZIONI no. La riparazione SOSTITUISCE
    -- e un episodio di energia riscritto senza `direzione` sarebbe piu'
    povero di quello che la notte aveva gia' scritto CON `direzione`. Deve
    fermarsi lo stesso, per la stessa asimmetria gia' decisa per i comprimari:
    chi sostituisce non tollera nessun guasto, nemmeno uno dei due letture.

    Mutazione ESEGUITA: nel corpo di `riaggrega_gli_ultimi_due_giorni`, il
    controllo sull'esito di `direzioni_energia()` sostituito con un `pass`
    (ignorare il guasto). Arrossisce: l'oggetto ricco (con `direzione`) viene
    sostituito da uno senza -- `dopo != prima`. Ripristinato subito dopo."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=timezone.utc)
        l_altro_ieri = (oggi - timedelta(days=2)).strftime("%Y-%m-%d")
        ieri = (oggi - timedelta(days=1)).strftime("%Y-%m-%d")
        for giorno, delta in ((l_altro_ieri, 2), (ieri, 1)):
            quando = (oggi - timedelta(days=delta)).replace(hour=10)
            archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                            soggetto="sensor.energia_prelievo", da=None, a="12.0",
                            device_class="energy")

        # Il "gia' fatto dalla notte": un episodio di energia CON direzione,
        # per entrambi i giorni bersaglio.
        ricco = [{"genere": "energia", "protagonista": "sensor.energia_prelievo",
                  "inizio_ts": 0.0, "fine_ts": 1.0,
                  "corpo": {"valore_iniziale": "1.0", "valore_finale": "2.0",
                           "differenza": 1.0, "comprimari": [], "misure": {},
                           "direzione": "prelievo", "provenienza": "dichiarata"}}]
        archivio.sostituisci_giorno(l_altro_ieri, ricco)
        archivio.sostituisci_giorno(ieri, ricco)
        prima = {g: archivio.oggetti(giorno=g) for g in (l_altro_ieri, ieri)}

        cliente = _ClienteLegami(direzioni_errore="Home Assistant non ha risposto")
        asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
            {"archivio_casa": None, "osservazioni": archivio}, ha_client=cliente,
            adesso=lambda tz: oggi.astimezone(tz)))

        dopo = {g: archivio.oggetti(giorno=g) for g in (l_altro_ieri, ieri)}
        assert dopo == prima
    finally:
        archivio.close()


def test_la_riparazione_chiede_le_direzioni_una_volta_per_i_due_giorni(tmp_path):
    """Come i comprimari (Task 6): una connessione sola per l'intero giro
    della riparazione, non una per giorno."""
    from datetime import datetime, timedelta, timezone

    from hiris.app.cervello.archivio import ArchivioOsservazioni

    archivio = ArchivioOsservazioni(str(tmp_path / "osservazioni.db"))
    try:
        oggi = datetime(2026, 8, 24, tzinfo=timezone.utc)
        for delta in (2, 1):
            quando = (oggi - timedelta(days=delta)).replace(hour=10)
            archivio.annota(quando_ts=quando.timestamp(), fonte="entita",
                            soggetto="sensor.energia_prelievo", da=None, a="12.0",
                            device_class="energy")

        cliente = _ClienteLegami()
        asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
            {"archivio_casa": None, "osservazioni": archivio}, ha_client=cliente,
            adesso=lambda tz: oggi.astimezone(tz)))

        assert cliente.direzioni_chieste == 1
    finally:
        archivio.close()


# --------------------------------------------------------------------------
# Punto 5 del mandato: il doppione con `hiris_problemi_ha` (`repairs/
# list_issues` letto due volte, per conto proprio) NON si unifica -- ma
# resta documentato accanto al lavoro del cervello, o la seconda lettura
# sembra una svista a chi legge dopo.
# --------------------------------------------------------------------------

def test_il_doppione_con_hiris_problemi_ha_e_documentato():
    sorgente = inspect.getsource(server)
    pos = sorgente.index('id="hiris_cervello_condizioni"')
    blocco = sorgente[pos - 1000:pos]
    assert "hiris_problemi_ha" in blocco
    assert 'app["problemi_ha"]' in blocco
