"""Il turno di «chiedi»: guarda, risponde, e non tocca niente."""
import pytest

from hiris.app.casa.strumenti import KNOWLEDGE_TOOLS
from hiris.app.schedulatore.turno import (
    SOLA_LETTURA,
    PromiseDispatcher,
    tools_promise,
)

# Marcatore applicato ai singoli test asincroni sotto, non al modulo: un
# `pytestmark` globale su un file con test SINCRONI (i tre sul catalogo, qui
# sopra) produce un warning pytest-asyncio nuovo -- e la fetta non ne ammette.


def test_il_catalogo_non_contiene_gli_strumenti_che_scrivono():
    nomi = {d["name"] for d in tools_promise()}
    assert "esegui" not in nomi
    assert "ricorda" not in nomi
    assert "prometti" not in nomi
    assert "disdici" not in nomi


def test_il_catalogo_contiene_i_lettori_e_concludi():
    nomi = {d["name"] for d in tools_promise()}
    assert nomi == set(SOLA_LETTURA) | {"concludi"}


def test_ogni_nome_ammesso_esiste_davvero_nel_catalogo_della_chat():
    """Un rinomino altrove non deve poter svuotare questo catalogo in silenzio."""
    veri = {d["name"] for d in KNOWLEDGE_TOOLS}
    assert set(SOLA_LETTURA) <= veri


def test_il_prompt_di_sistema_spiega_gli_id_fra_parentesi_e_il_parallelismo():
    """Fix finale ④ (review 2026-08-20): il turno riceve lo STESSO nucleo
    della chat, coi suoi `(id: X)` accanto ad aree/piani/automazioni/script
    (`costruisci_nucleo`, vedi `interpreta_promise`), ma prima di questo fix
    il prompt non lo spiegava affatto, ne' diceva il conteggio del
    parallelismo -- che QUI e' vero al 100% perche' il turno gira su
    `runner.chat`, lo stesso ciclo di `claude_runner.py`
    (`BASE_REGOLE_STRUMENTI`) che conta un giro per risposta, non per
    chiamata."""
    from hiris.app.schedulatore.turno import _prompt_di_system
    testo = _prompt_di_system()
    assert "(id: X)" in testo, "il prompt non spiega piu' gli id fra parentesi dell'albero"
    assert "IN PARALLELO" in testo, "il prompt non insegna piu' il parallelismo"
    assert "il ciclo conta un giro per risposta, non per chiamata" in testo, (
        "qui la giustificazione del parallelismo e' vera (il turno gira su "
        "runner.chat): deve restare, non diventare la frase falsa del ponte")


def test_concludi_dichiara_che_la_notifica_la_manda_hiris():
    """Il difetto che ha rotto le promesse con notifica (21/08/2026).

    La frase della persona arriva VERBATIM al turno (`_domanda`), e quando
    dice «mandami una notifica» il modello cerca uno strumento per mandarla.
    Non c'e', e non deve esserci: la manda lo Schedulatore DOPO `concludi`,
    sul canale approvato alla nascita. Ma niente glielo diceva -- la
    descrizione di `avvisare` parlava solo del GIUDIZIO («se valga la pena
    disturbarla»), mai del MECCANISMO -- e il modello rispondeva a parole
    invece di concludere. Riprodotto tre volte sull'add-on vero: senza la
    richiesta di notifica il turno conclude, con la richiesta fallisce."""
    from hiris.app.schedulatore.turno import CONCLUDI_TOOL_DEF

    d = CONCLUDI_TOOL_DEF["description"]
    assert "la manda HIRIS per te" in d, (
        "il modello deve sapere che la notifica non la manda lui")
    assert "non esiste uno strumento per notificare" in d, (
        "deve sapere che l'assenza dello strumento e' voluta, non una lacuna "
        "da aggirare rispondendo a parole")


def test_il_prompt_manda_a_concludi_invece_di_dire_solo_nel_testo():
    """«scrivila come proposta nel testo» era ambiguo fra il campo `testo` di
    «concludi» e la propria risposta. Il modello sceglieva la seconda, e il
    turno moriva senza conclusione. Il prompt PUNTA al meccanismo, non lo
    ricopia: la sua casa e' `CONCLUDI_TOOL_DEF` (fondamenta n.2)."""
    from hiris.app.schedulatore.turno import _prompt_di_system

    testo = _prompt_di_system()
    assert "nel campo `testo` di «concludi»" in testo, (
        "«nel testo» da solo si legge come «nella tua risposta»")
    assert "leggi cosa fa `avvisare`" in testo, (
        "il caso «mi era stato chiesto di avvisare» deve portare a concludi")


class DispatcherFinto:
    """Sa rispondere a TUTTO, `esegui` compreso: se il wrapper lasciasse
    passare uno strumento che scrive, questo doppio glielo eseguirebbe."""

    def __init__(self):
        self.chiamati = []

    async def dispatch(self, nome, argomenti):
        self.chiamati.append(nome)
        return {"ok": nome}


@pytest.mark.asyncio
async def test_esegui_non_arriva_al_dispatcher_sottostante():
    sotto = DispatcherFinto()
    d = PromiseDispatcher(sotto)
    esito = await d.dispatch("esegui", {"servizio": "light.turn_on"})
    assert "errore" in esito
    assert sotto.chiamati == []


@pytest.mark.asyncio
async def test_un_lettore_passa_al_dispatcher_sottostante():
    sotto = DispatcherFinto()
    d = PromiseDispatcher(sotto)
    assert await d.dispatch("guarda", {}) == {"ok": "guarda"}
    assert sotto.chiamati == ["guarda"]


@pytest.mark.asyncio
async def test_concludi_non_scende_e_resta_nel_wrapper():
    sotto = DispatcherFinto()
    d = PromiseDispatcher(sotto)
    esito = await d.dispatch("concludi", {"avvisare": True, "testo": "fa caldo"})
    assert "errore" not in esito
    assert sotto.chiamati == []
    assert d.conclusione == {"avvisare": True, "testo": "fa caldo"}


@pytest.mark.asyncio
async def test_concludi_senza_avvisare_e_un_rifiuto_leggibile():
    d = PromiseDispatcher(DispatcherFinto())
    esito = await d.dispatch("concludi", {"testo": "fa caldo"})
    assert "errore" in esito
    assert d.conclusione is None


@pytest.mark.asyncio
async def test_l_ultima_conclusione_vince_e_non_si_accumula():
    d = PromiseDispatcher(DispatcherFinto())
    await d.dispatch("concludi", {"avvisare": False, "testo": "niente"})
    await d.dispatch("concludi", {"avvisare": True, "testo": "invece si'"})
    assert d.conclusione == {"avvisare": True, "testo": "invece si'"}


# --- interpreta_promise, end-to-end ------------------------------------------
#
# Rilievo minore della review finale: `interpreta_promise` non era coperta
# end-to-end. E' la SECONDA giuntura non attraversata da nessun test -- la
# prima (`orologio.py` + `verifica.py`, vedi `test_schedulatore_orologio.py`)
# si e' rivelata rotta, ed e' la priorita' fra i minori per lo stesso motivo:
# ogni test altrove costruisce un `TurnoFinto` che RESTITUISCE gia' la
# conclusione, mai un runner che la produce chiamando `concludi` attraverso
# `PromiseDispatcher` -- il percorso vero.
#
# Un `app` vuoto (`{}`) e' legittimo: `costruisci_nucleo` e
# `costruisci_dispatcher_strumenti` sono "SEMPRE componibili" per contratto
# (vedi i loro docstring in `hiris/app/api/handlers_casa.py` e
# `handlers_chat.py`), anche senza archivi -- e' la stessa disciplina che
# rende `interpreta_promise` provabile senza un server vero.

class _RunnerCheConclude:
    """Un runner finto che CHIAMA `concludi` attraverso il dispatcher che
    riceve -- non lo restituisce gia' pronto: e' cio' che attraversa
    davvero `PromiseDispatcher`, non un suo doppio."""

    def __init__(self, avvisare: bool, testo: str) -> None:
        self._avvisare = avvisare
        self._testo = testo
        self.chiamato_con: dict | None = None

    async def chat(self, **kwargs):
        self.chiamato_con = kwargs
        await kwargs["dispatcher"].dispatch(
            "concludi", {"avvisare": self._avvisare, "testo": self._testo})


class _RunnerCheNonConclude:
    """Il turno che gira e non chiama MAI `concludi`: la promessa "forse e'
    andata bene" che la spec vieta esplicitamente (§6.2)."""

    async def chat(self, **kwargs):
        return None


def _promessa_chiedi(**extra) -> dict:
    dati = {"id": "p1", "frase": "fra un'ora verifica la temperatura",
            "domanda": "e' aumentata?", "istantanea": []}
    dati.update(extra)
    return dati


@pytest.mark.asyncio
async def test_interpreta_promessa_ritorna_cio_che_il_turno_ha_concluso():
    from hiris.app.schedulatore.turno import interpreta_promise

    runner = _RunnerCheConclude(avvisare=True, testo="e' salita di 2 gradi")
    app = {"llm_router": runner}

    esito = await interpreta_promise(app, _promessa_chiedi())

    assert esito == {"avvisare": True, "testo": "e' salita di 2 gradi"}
    # il catalogo che arriva al runner e' quello RISTRETTO (SOLA_LETTURA +
    # concludi), non il catalogo intero della chat -- e' la garanzia
    # strutturale della spec (§6.2), non solo un fatto su questo test
    assert ({d["name"] for d in runner.chiamato_con["strumenti"]}
            == set(SOLA_LETTURA) | {"concludi"})
    assert runner.chiamato_con["agent_type"] == "promessa"


@pytest.mark.asyncio
async def test_interpreta_promessa_senza_concludi_e_un_errore_dichiarato():
    """Il turno che non conclude: `interpreta_promise` non deve inventare un
    "forse e' andata bene" -- deve dichiarare l'errore, cosi' l'orologio
    marca la promessa `fallita` con un motivo vero (vedi
    `sweeper._keep_chiedi`)."""
    from hiris.app.schedulatore.turno import interpreta_promise

    esito = await interpreta_promise({"llm_router": _RunnerCheNonConclude()},
                                      _promessa_chiedi())

    assert "errore" in esito
    assert "non ha concluso" in esito["errore"]


class _RunnerCheRispondeInTesto:
    """Il turno che risponde IN TESTO invece di chiamare `concludi`.

    E' il modo esatto in cui la promessa delle 17:00 del 21/08/2026 e' fallita
    sull'add-on vero, riprodotto poi tre volte di seguito: la frase della
    persona chiedeva una notifica, il turno non ha nessuno strumento per
    mandarla (non ce l'ha per progetto -- la manda lo Schedulatore dopo
    `concludi`), e il modello ha risposto a parole invece di concludere.

    `_RunnerCheNonConclude` NON sapeva produrre questo difetto: restituisce
    `None`, mentre `chat()` in produzione restituisce SEMPRE una stringa -- ed
    e' proprio quella stringa che diceva cosa fosse successo, e che
    `interpreta_promise` buttava via. Una finta che non sa produrre il
    difetto non lo puo' testare.
    """

    def __init__(self, testo: str) -> None:
        self._testo = testo

    async def chat(self, **kwargs) -> str:
        return self._testo


@pytest.mark.asyncio
async def test_il_turno_che_non_conclude_riporta_cio_che_il_modello_aveva_detto():
    """Il motivo che si legge dalla pagina deve dire COSA e' successo.

    «Il turno non ha concluso: non so cosa dirti» e' vero e inutilizzabile:
    HIRIS il testo ce l'aveva in mano e lo scartava, e per sapere quale delle
    tre uscite del ciclo avesse preso il turno e' servita un'indagine di
    un'ora sull'add-on vivo."""
    from hiris.app.schedulatore.turno import interpreta_promise

    app = {"llm_router": _RunnerCheRispondeInTesto(
        "Ho letto le otto stanze, ma da qui non posso mandarti una notifica.")}

    esito = await interpreta_promise(app, _promessa_chiedi())

    assert "errore" in esito
    assert "non ha concluso" in esito["errore"]
    assert "non posso mandarti una notifica" in esito["errore"], (
        "senza cio' che il modello ha risposto, il motivo non distingue "
        "«ha risposto a parole» da «ha esaurito le iterazioni» da «e' stato "
        "troncato»: sono tre guasti diversi con lo stesso messaggio")


@pytest.mark.asyncio
async def test_la_risposta_del_modello_entra_nel_motivo_troncata():
    """Il motivo finisce in una colonna di SQLite e in una pagina: la
    risposta del modello puo' essere lunghissima, e va riportata a misura."""
    from hiris.app.schedulatore.turno import interpreta_promise

    app = {"llm_router": _RunnerCheRispondeInTesto("temperatura " * 2000)}

    esito = await interpreta_promise(app, _promessa_chiedi())

    assert len(esito["errore"]) < 600, (
        "un motivo di ventimila caratteri non e' un motivo, e' un allegato")


@pytest.mark.asyncio
async def test_se_il_modello_non_ha_detto_proprio_niente_il_motivo_lo_dichiara():
    """L'altra meta' del fatto: quando non c'e' NESSUNA risposta da
    riportare, il motivo non deve inventarsi un virgolettato vuoto."""
    from hiris.app.schedulatore.turno import interpreta_promise

    esito = await interpreta_promise({"llm_router": _RunnerCheNonConclude()},
                                      _promessa_chiedi())

    assert "non ha concluso" in esito["errore"]
    assert "«»" not in esito["errore"]


@pytest.mark.asyncio
async def test_interpreta_promessa_senza_runner_e_un_errore_dichiarato():
    from hiris.app.schedulatore.turno import interpreta_promise

    esito = await interpreta_promise({}, _promessa_chiedi())

    assert "errore" in esito
    assert "modello" in esito["errore"]


# --- l'instradamento: la promessa segue la catena, ponte compreso ------------
#
# Fetta «le promesse seguono la catena» (22/08/2026). Prima di qui
# `interpreta_promise` andava SEMPRE a `llm_router`, qualunque cosa dicesse la
# gerarchia dei modelli -- e su una casa che gira interamente sul Piano Claude
# Max le promesse morivano su chiavi API esaurite mentre la chat funzionava.


class _CodaFinta:
    def __init__(self):
        self.accodati = []

    def count_turni_oggi(self, now=None):
        return 0

    def enqueue(self, kind, wake, context, deadline_ts, *, job_id=None, now):
        self.accodati.append({"kind": kind, "context": context,
                              "deadline_ts": deadline_ts, "now": now})
        return "job-1"


class _RouterCheNonDeveRispondere:
    def __init__(self):
        self.chiamato = False

    async def chat(self, **kwargs):
        self.chiamato = True
        return "non dovevi chiedere a me"


def _app_col_ponte(coda=None, router=None):
    return {
        "ponte_attivo": True,
        "reasoning_queue": coda if coda is not None else _CodaFinta(),
        "models_config": {"ponte": {"tetto_giornaliero": 150, "scadenza_min": 10}},
        "llm_router": router if router is not None else _RouterCheNonDeveRispondere(),
    }


@pytest.fixture
def col_token_del_piano(monkeypatch):
    from hiris.app.decisione_modelli import VARIABILE_TOKEN_DEL_PIANO
    monkeypatch.setenv(VARIABILE_TOKEN_DEL_PIANO, "un-token-qualunque")


@pytest.mark.asyncio
async def test_col_ponte_in_testa_il_turno_va_in_coda_e_non_al_router(col_token_del_piano):
    from hiris.app.schedulatore.turno import interpreta_promise

    coda, router = _CodaFinta(), _RouterCheNonDeveRispondere()
    app = _app_col_ponte(coda, router)

    esito = await interpreta_promise(app, _promessa_chiedi())

    assert esito == {"accodata": True}
    assert router.chiamato is False, (
        "il piano era in testa alla catena: il router non doveva rispondere")
    assert len(coda.accodati) == 1
    assert coda.accodati[0]["kind"] == "promessa"


@pytest.mark.asyncio
async def test_il_job_porta_cio_che_serve_a_mantenere_la_promessa(col_token_del_piano):
    """Il ponte gira altrove e non ha gli archivi: cio' che non entra nel job
    non esiste per lui. Senza `promessa_id` la rotta MCP non saprebbe quale
    turno sta parlando, e `concludi` non avrebbe niente da chiudere."""
    from hiris.app.schedulatore.turno import interpreta_promise

    coda = _CodaFinta()
    await interpreta_promise(coda and _app_col_ponte(coda), _promessa_chiedi())

    contesto = coda.accodati[0]["context"]
    assert contesto["promessa_id"] == "p1"
    # Le chiavi che il turno del ponte legge DAVVERO: se il job ne portasse
    # altre, sarebbero dati scritti che nessuno interroga.
    assert contesto["history"][0]["role"] == "user"
    assert "fra un'ora verifica la temperatura" in contesto["history"][0]["content"]
    assert "e' aumentata?" in contesto["history"][0]["content"]
    assert "mantenendo una promessa" in contesto["system_prompt"]


@pytest.mark.asyncio
async def test_senza_il_token_del_piano_il_turno_scende_alla_catena(monkeypatch):
    """Il ripiego della chat, identico: e' la regola sola che la fetta cerca."""
    from hiris.app.decisione_modelli import VARIABILE_TOKEN_DEL_PIANO
    from hiris.app.schedulatore.turno import interpreta_promise

    monkeypatch.delenv(VARIABILE_TOKEN_DEL_PIANO, raising=False)
    coda = _CodaFinta()
    app = _app_col_ponte(coda, _RunnerCheConclude(avvisare=True, testo="fa caldo"))

    esito = await interpreta_promise(app, _promessa_chiedi())

    assert coda.accodati == [], "il piano non poteva: non si accoda a nessuno"
    assert esito["testo"] == "fa caldo"


@pytest.mark.asyncio
async def test_col_ponte_spento_il_turno_resta_sulla_catena_come_sempre():
    from hiris.app.schedulatore.turno import interpreta_promise

    coda = _CodaFinta()
    app = _app_col_ponte(coda, _RunnerCheConclude(avvisare=False, testo="niente"))
    app["ponte_attivo"] = False

    esito = await interpreta_promise(app, _promessa_chiedi())

    assert coda.accodati == []
    assert esito["avvisare"] is False


@pytest.mark.asyncio
async def test_il_ripiego_dal_piano_alla_catena_finisce_nella_promessa(monkeypatch):
    """Il ripiego si annuncia OGNI VOLTA (decisione del proprietario, 13
    agosto): un passaggio dal forfait al consumo che nessuno dichiara si
    scopre a fine mese. In chat lo dice una nota in coda alla risposta; una
    promessa non ha una risposta in cui metterla -- ha il suo motivo, ed e'
    quello che si legge dalla pagina."""
    from hiris.app.decisione_modelli import VARIABILE_TOKEN_DEL_PIANO
    from hiris.app.schedulatore.turno import interpreta_promise

    monkeypatch.delenv(VARIABILE_TOKEN_DEL_PIANO, raising=False)
    app = _app_col_ponte(_CodaFinta(),
                         _RunnerCheConclude(avvisare=True, testo="fa caldo"))

    esito = await interpreta_promise(app, _promessa_chiedi())

    assert esito["testo"] == "fa caldo"
    assert esito.get("nota"), (
        "il turno e' passato dal forfait al consumo e la promessa non lo dice")
    assert "Piano Claude Max" in esito["nota"]


@pytest.mark.asyncio
async def test_senza_ripiego_non_si_annuncia_niente():
    """Ponte spento non e' un ripiego: e' la configurazione. Una nota a ogni
    promessa direbbe all'utente che sta perdendo qualcosa che non ha mai
    avuto."""
    from hiris.app.schedulatore.turno import interpreta_promise

    app = _app_col_ponte(_CodaFinta(),
                         _RunnerCheConclude(avvisare=False, testo="niente"))
    app["ponte_attivo"] = False

    esito = await interpreta_promise(app, _promessa_chiedi())

    assert not esito.get("nota")
