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
    oggetti. Qui `ha_client=None`: `costruisci_comprimari` non solleva (i
    guasti per soggetto sono suoi, non del chiamante -- vedi il suo
    docstring), quindi la riparazione gira per intero come se fosse
    incondizionata.

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
            {"archivio_casa": None, "osservazioni": archivio}, ha_client=None,
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
            {"archivio_casa": None, "osservazioni": archivio}, ha_client=None,
            adesso=lambda tz: oggi.astimezone(tz)))
        assert len(archivio.oggetti(limite=10)) == 2
    finally:
        archivio.close()


class _ClienteLegami:
    """HAClient finto per `costruisci_comprimari`, **fedele al contratto
    vero** di `HAClient.legami` (`proxy/ha_client.py`) -- non a come lo
    descriveva il mandato originale del Task 6. E' la correzione al Critical
    trovato dalla review de «l'osservatore» (26/08/2026): la finta di prima
    accettava `legami("entita", ...)` e rispondeva con la busta
    `{"legami": {...}}` che e' la forma di `casa/domande.py::legami` (lo
    strato TRADOTTO), non quella del client -- e per questo non avrebbe MAI
    potuto arrossire, nemmeno con `costruisci_comprimari` completamente
    inerte in produzione. Questa finta valida `tipo` contro i VERI valori di
    `HAClient.TIPI_LEGAME` (importati, non ricopiati -- una terza tabella
    sarebbe il doppione che questo progetto insegue da stanotte) e risponde
    nella forma grezza del client: chiavi inglesi, nessuna busta."""

    def __init__(self, mappa: dict[str, dict[str, list[str]]]):
        # soggetto -> {tipo_inglese: [identificatori]}, come la manda HA.
        self._mappa = mappa

    async def legami(self, tipo, identificatore):
        from hiris.app.proxy.ha_client import HAClient
        if tipo not in HAClient.TIPI_LEGAME:
            return {"errore": f"tipo non riconosciuto da Home Assistant: {tipo}"}
        return dict(self._mappa.get(identificatore, {}))


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


class _ClienteSempreRotto:
    """Fedele al contratto VERO di `HAClient.legami`: un guasto di rete NON
    solleva, torna `{"errore": ...}` -- esattamente come fa `HAClient.legami`
    quando `_ws_batch` solleva (`proxy/ha_client.py`, contenuto in un
    `try/except` interno). Il giro precedente su questo pezzo aveva
    monkeypatchato `costruisci_comprimari` con una versione che SOLLEVA: una
    finta che produce un difetto che il collaboratore vero quasi mai
    produce (il difetto n.1 di questo progetto, rientrato dentro la sua
    stessa correzione -- grilletto-brief.md). Questa finta non tocca
    `costruisci_comprimari`: passa dalla catena vera."""

    async def legami(self, tipo, identificatore):
        return {"errore": "Home Assistant non ha risposto"}


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
    incontra mai. Qui si usa `_ClienteSempreRotto`, che risponde come
    risponde Home Assistant quando non c'e' davvero, e nessun monkeypatch:
    la catena e' quella vera, `legami` -> `costruisci_comprimari` -> il
    contatore dei falliti che ora torna al chiamante.

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
            ha_client=_ClienteSempreRotto(),
            adesso=lambda tz: oggi.astimezone(tz)))

        dopo = {g: archivio.oggetti(giorno=g) for g in (l_altro_ieri, ieri)}
        assert dopo == prima
    finally:
        archivio.close()


class _ClienteParzialmenteRotto:
    """Un guasto PARZIALE: un soggetto risponde `{"errore": ...}`, gli altri
    rispondono come Home Assistant fa davvero (chiavi inglesi, nessuna
    busta) -- non un client tutto rotto o tutto sano."""

    def __init__(self, soggetto_rotto: str):
        self._rotto = soggetto_rotto

    async def legami(self, tipo, identificatore):
        if identificatore == self._rotto:
            return {"errore": "Home Assistant non ha risposto"}
        return {"entity": ["sensor.buono"]}


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

        asyncio.run(server.riaggrega_gli_ultimi_due_giorni(
            {"archivio_casa": None, "osservazioni": archivio},
            ha_client=_ClienteParzialmenteRotto("light.rotto"),
            adesso=lambda tz: oggi.astimezone(tz)))

        assert archivio.oggetti(giorno=ieri) == prima
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
        job = _carica_funzione_innestata("_aggrega_ieri", {
            "app": {"archivio_casa": None, "osservazioni": archivio},
            "ha_client": _ClienteParzialmenteRotto("light.rotto"),
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
    ('non deve bloccare l'avvio')."""
    sorgente = inspect.getsource(server._on_startup)
    assert "riaggrega_gli_ultimi_due_giorni(app, ha_client)" in sorgente
    assert sorgente.index('app["osservatore"].ricostruisci_condizioni()') \
        < sorgente.index("riaggrega_gli_ultimi_due_giorni(app, ha_client)")
    pos = sorgente.index("riaggrega_gli_ultimi_due_giorni(app, ha_client)")
    blocco = sorgente[pos - 80:pos + 200]
    assert "try:" in blocco
    assert "except Exception" in blocco


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
