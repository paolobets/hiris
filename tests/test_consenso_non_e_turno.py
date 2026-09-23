"""Il turno non è il consenso: la cronaca registra la frase che conferma (B-5).

**Il reperto** (`docs/design/2026-09-21-sicurezza-esposizioni.md`, B-5). Il
cancello dell'officina verifica che la conferma arrivi in un turno **diverso**
dalla proposta. Non verifica che il proprietario abbia detto di sì, e **non
può**: `confirm` è uno strumento del modello. Turno N: propone. Turno N+1
l'utente scrive «grazie». Il modello chiama `confirm`. L'oggetto viene scritto.

«In mezzo c'è stato un turno» e «in mezzo c'è stato un sì» sono due fatti
diversi, e fino a oggi la cronaca ne registrava uno solo.

**La via scelta dal proprietario il 23/09/2026**, fra le due che il registro
proponeva: **registrare la frase**, non togliere `confirm` al modello. Non
impedisce niente — un'autoconferma resta possibile — ma smette di essere
invisibile: chi legge la cronaca vede la frase su cui l'oggetto è nato, e
«grazie» accanto a un'automazione scritta è una domanda che si pone da sola.
L'altra via (confermare solo dalla pagina) costava un uso vero: HIRIS non
avrebbe più potuto completare una costruzione dentro la conversazione.

**Il nome è `confirm_phrase` e non `frase`**, e la distinzione non è
cosmetica: `propose` ha già un campo `frase`, ed è *la frase che ha CHIESTO la
costruzione*. Questa è *la frase che l'ha CONFERMATA*. Sono due fatti diversi,
e due fatti diversi non condividono una parola — si separano alla fonte, mai a
valle.

**In inglese** perché `action/` è un ambito già convertito: un identificatore
italiano nuovo lì è debito che nasce oggi, e `test_rinomina_applica.py` l'ha
preso al primo giro. La chiave finisce anche nel JSON del soggetto, accanto a
`specie`/`nome`/`utente`, che sono italiane: quelle sono il debito vecchio, e
si migrano nella loro fetta — le nuove nascono già dall'altra parte.

**L'assenza è un fatto, e non si finge.** Una conferma dalla pagina non porta
nessuna frase perché il clic **è** il sì; una promessa notturna e un servizio
via MCP non hanno nessuna persona che parli. In tutti e tre i casi la chiave
non c'è — e «non c'è» non è `""`, che si leggerebbe come «ha detto niente».
"""
import os

import pytest

from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.workshop import PHRASE_MAX, Workshop
from hiris.app.action.journal import Journal
from hiris.app.home_space.tools import ToolDispatcher
from tests.test_construction_workshop import FintoHA, _intento

ADESSO = 1_756_000_000.0
SOGGETTO = {"specie": "persona", "id": "u1", "nome": "Paolo",
            "utente": "paolo"}


@pytest.fixture()
def banco(tmp_path):
    archivio = ConstructionStore(os.path.join(str(tmp_path), "costruzioni.db"))
    cronaca = Journal(os.path.join(str(tmp_path), "azioni.db"))
    officina = Workshop(FintoHA(), archivio, cronaca)
    yield officina, archivio, cronaca
    archivio.close()
    cronaca.close()


async def _proposta(officina) -> str:
    esito = await officina.propose(_intento(), actor="chat",
                                   exchange="turno-1", now=ADESSO)
    assert "errore" not in esito, esito
    return esito["proposta_id"]


def _soggetto_scritto(cronaca, esito) -> dict:
    riga = cronaca.read(esito["esecuzione_id"])
    assert riga is not None, "l'atto non è finito in cronaca"
    return riga["soggetto"] or {}


@pytest.mark.asyncio
async def test_la_frase_del_turno_che_conferma_FINISCE_in_cronaca(banco):
    """**Il reperto.** L'oggetto nasce su «grazie», e adesso si vede.

    Mutazione ESEGUITA: non passare `confirm_phrase` a `log_construction` --
    rossa."""
    officina, _, cronaca = banco
    proposta = await _proposta(officina)

    esito = await officina.apply(proposta, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60, subject=SOGGETTO,
                                 confirm_phrase="grazie")

    assert esito.get("applicata"), esito
    assert _soggetto_scritto(cronaca, esito)["confirm_phrase"] == "grazie"


@pytest.mark.asyncio
async def test_la_frase_NON_scalza_chi_ha_chiamato(banco):
    """Si AGGIUNGE al soggetto, non lo sostituisce: «chi» e «cosa ha detto»
    sono due domande, e la seconda non cancella la prima.

    Mutazione ESEGUITA: comporre il soggetto come `{"confirm_phrase": ...}`
    invece di aggiungerlo -- rossa."""
    officina, _, cronaca = banco
    proposta = await _proposta(officina)

    esito = await officina.apply(proposta, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60, subject=SOGGETTO,
                                 confirm_phrase="sì, procedi")

    scritto = _soggetto_scritto(cronaca, esito)
    assert scritto["nome"] == "Paolo"
    assert scritto["specie"] == "persona"
    assert scritto["confirm_phrase"] == "sì, procedi"


@pytest.mark.asyncio
async def test_il_soggetto_ORIGINALE_non_viene_modificato(banco):
    """Il dizionario che arriva dal confine vive quanto la richiesta e lo
    leggono anche altri: scriverci dentro sarebbe un effetto a distanza su un
    oggetto di qualcun altro.

    Mutazione ESEGUITA: `subject["confirm_phrase"] = ...` invece di una copia
    -- rossa."""
    officina, _, _ = banco
    proposta = await _proposta(officina)
    soggetto = dict(SOGGETTO)

    await officina.apply(proposta, actor="chat", exchange="turno-2",
                         now=ADESSO + 60, subject=soggetto,
                         confirm_phrase="vai")

    assert "confirm_phrase" not in soggetto


@pytest.mark.asyncio
async def test_una_conferma_dalla_PAGINA_non_porta_nessuna_frase(banco):
    """Il clic **è** il sì: non c'è nessuna frase da registrare, e inventarne
    una direbbe il falso.

    Mutazione ESEGUITA: scrivere `""` invece di non scrivere la chiave --
    rossa."""
    officina, _, cronaca = banco
    proposta = await _proposta(officina)

    esito = await officina.apply(proposta, actor="pagina",
                                 exchange=None, now=ADESSO + 60,
                                 subject=SOGGETTO)

    assert esito.get("applicata"), esito
    assert "confirm_phrase" not in _soggetto_scritto(cronaca, esito)


@pytest.mark.asyncio
async def test_una_frase_VUOTA_non_diventa_una_frase(banco):
    """Uno spazio, un a-capo, o niente: **«non ha detto niente» non è «ha detto
    una stringa vuota»**. Chi legge la cronaca deve distinguere «nessuno ha
    parlato» da «ha parlato e non si capiva».

    Mutazione ESEGUITA: togliere lo `strip()` dalla guardia -- rossa."""
    officina, _, cronaca = banco
    for vuota in ("", "   ", "\n\t "):
        proposta = await _proposta(officina)
        esito = await officina.apply(proposta, actor="chat",
                                     exchange="turno-2", now=ADESSO + 60,
                                     subject=SOGGETTO, confirm_phrase=vuota)
        assert "confirm_phrase" not in _soggetto_scritto(cronaca, esito), vuota


@pytest.mark.asyncio
async def test_la_frase_si_TAGLIA(banco):
    """La cronaca la rilegge `logbook`, che la porta al modello: un muro di
    testo incollato in chat diventerebbe carico a ogni turno, per novanta
    giorni. Si taglia, e il taglio **si dichiara** invece di far sembrare
    quella la frase intera.

    Mutazione ESEGUITA: togliere il taglio -- rossa.
    Mutazione ESEGUITA: tagliare senza marcatore -- rossa."""
    officina, _, cronaca = banco
    proposta = await _proposta(officina)

    esito = await officina.apply(proposta, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60, subject=SOGGETTO,
                                 confirm_phrase="a" * (PHRASE_MAX + 500))

    scritta = _soggetto_scritto(cronaca, esito)["confirm_phrase"]
    assert len(scritta) <= PHRASE_MAX + 1, len(scritta)
    assert scritta.endswith("…"), "il taglio non si dichiara"


@pytest.mark.asyncio
async def test_una_frase_CORTA_non_si_tocca(banco):
    """Il taglio non deve mangiare l'ultimo carattere di una frase sana.

    Mutazione ESEGUITA: tagliare sempre, anche sotto il tetto -- rossa."""
    officina, _, cronaca = banco
    proposta = await _proposta(officina)
    detta = "sì, procedi pure"

    esito = await officina.apply(proposta, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60, subject=SOGGETTO,
                                 confirm_phrase=detta)

    assert _soggetto_scritto(cronaca, esito)["confirm_phrase"] == detta


@pytest.mark.asyncio
async def test_senza_NESSUN_soggetto_la_frase_nasce_lo_stesso(banco):
    """Un chiamante che non porta un soggetto (i casi normali del ponte) non
    deve far sparire la frase: sono due fatti indipendenti, e legarli
    perderebbe quello che c'è per colpa di quello che manca.

    Mutazione ESEGUITA: comporre la frase solo `if subject` -- rossa."""
    officina, _, cronaca = banco
    proposta = await _proposta(officina)

    esito = await officina.apply(proposta, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60, subject=None,
                                 confirm_phrase="fallo")

    assert _soggetto_scritto(cronaca, esito)["confirm_phrase"] == "fallo"


def test_OGNI_chiamante_del_dispatcher_puo_portare_la_frase():
    """Il contratto della firma: `create_tool_dispatcher` è l'UNICO punto in
    cui si costruisce un `ToolDispatcher`, e i suoi quattro chiamanti devono
    poter passare la frase — due la portano (i due rami della chat), due no
    (MCP e le promesse, che non hanno nessuna persona che parli).

    Un parametro senza default spegnerebbe i due che non la portano; un
    parametro assente spegnerebbe i due che la portano.

    Mutazione ESEGUITA: togliere `frase` dalla firma -- rossa.
    Mutazione ESEGUITA: renderla obbligatoria (senza default) -- rossa."""
    import inspect

    from hiris.app.api.handlers_chat import create_tool_dispatcher

    parametri = inspect.signature(create_tool_dispatcher).parameters
    assert "frase" in parametri, (
        "i due rami della chat non hanno modo di passare la frase che conferma")
    assert parametri["frase"].default is None, (
        "MCP e le promesse non hanno nessuna frase da passare: senza default "
        "questa firma li spegne")


def test_NESSUN_ramo_della_chat_costruisce_un_dispatcher_senza_la_frase():
    """Non basta che la firma lo permetta: i due rami devono FARLO. Il ramo
    sincrono e quello accodato sono due strade per lo stesso turno, e una sola
    delle due che registra sarebbe peggio di nessuna — la cronaca direbbe
    «nessuno ha parlato» a seconda di come è andata la coda.

    **Questa prova contava le parole `frase=` nel sorgente, e non sapeva
    fallire**: togliendo `frase=` da UNO dei due rami ne restavano ancora due
    (l'inoltro dentro la fabbrica, più il ramo superstite) e il conteggio
    tornava. Misurato con la mutazione, non supposto. Adesso si guarda
    l'ALBERO: ogni chiamata a `create_tool_dispatcher` dentro questo modulo
    deve portare `frase`, e sono i CHIAMANTI a essere contati, non le
    occorrenze di una stringa.

    Mutazione ESEGUITA: togliere `frase=` dal ramo accodato -- rossa.
    Mutazione ESEGUITA: togliere `frase=` dal ramo sincrono -- rossa."""
    import ast
    import inspect

    from hiris.app.api import handlers_chat

    albero = ast.parse(inspect.getsource(handlers_chat))
    chiamate = [nodo for nodo in ast.walk(albero)
                if isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "create_tool_dispatcher"]

    assert len(chiamate) == 2, (
        f"i rami della chat che costruiscono un dispatcher sono {len(chiamate)}, "
        "non due: se ne è nato uno nuovo, deve portare la frase anche lui")
    for chiamata in chiamate:
        nomi = {parola.arg for parola in chiamata.keywords}
        assert "frase" in nomi, (
            f"la chiamata alla riga {chiamata.lineno} costruisce un dispatcher "
            "senza la frase che conferma: da quel ramo la cronaca dirà che "
            "nessuno ha parlato")


@pytest.mark.asyncio
async def test_lo_STRUMENTO_confirm_porta_la_frase_fino_in_cronaca(banco):
    """**Il filo intero, non i suoi pezzi.** Le prove qui sopra guardano
    l'officina da una parte e la firma della fabbrica dall'altra: in mezzo c'è
    il dispatcher, e finché nessuno lo attraversava **togliere l'inoltro a
    `confirm` non faceva cadere niente** — misurato con la mutazione. Una
    funzione cablata a metà è una funzione che non c'è.

    Qui si chiama lo strumento vero, con il nome che usa il modello.

    Mutazione ESEGUITA: togliere `confirm_phrase=self._frase` dallo strumento
    `confirm` -- rossa."""
    officina, _, cronaca = banco
    proposta = await _proposta(officina)

    dispatcher = ToolDispatcher(None, None, workshop=officina,
                                exchange="turno-2", subject=SOGGETTO,
                                phrase="sì, scrivila")
    esito = await dispatcher.dispatch("confirm", {"proposta_id": proposta})

    assert esito.get("applicata"), esito
    assert _soggetto_scritto(cronaca, esito)["confirm_phrase"] == "sì, scrivila"
