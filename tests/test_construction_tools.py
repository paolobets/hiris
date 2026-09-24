"""I due strumenti: `propose` propone, `confirm` applica. E il catalogo."""
import pytest

from hiris.app.action.construction.workshop import Workshop
from hiris.app.agent.runner import mcp_names
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS, ToolDispatcher
from hiris.app.keeper.exchange import promise_tools
from tests._contracts import assert_stessa_firma


class FintaOfficina:
    def __init__(self, esito_proponi=None, esito_applica=None):
        self.chiamate = []
        self._proponi = esito_proponi or {"proposta_id": "p1", "anteprima": "farei cosi'"}
        self._applica = esito_applica or {"applicata": True, "esecuzione_id": "e1",
                                          "entita": ["automation.x"], "avviso": None}

    async def propose(self, intento, *, actor, exchange, now):
        self.chiamate.append(("propose", intento, actor, exchange))
        return self._proponi

    async def apply(self, proposta_id, *, actor, exchange, now, subject=None,
                    confirm_phrase=None):
        self.chiamate.append(("apply", proposta_id, actor, exchange))
        return self._applica


def test_la_finta_officina_combacia_con_la_firma_vera():
    """Se `Workshop.propose`/`apply` cambia firma, questo test cade
    invece di lasciare che il finto imiti un contratto che non esiste
    piu' (review indipendente, fetta «la rinomina»: `origine`/`turno`/
    `adesso` erano rimasti su ENTRAMBI i lati, chiamante vero compreso)."""
    assert_stessa_firma(Workshop.propose, FintaOfficina.propose, nome="propose")
    assert_stessa_firma(Workshop.apply, FintaOfficina.apply, nome="apply")


def _dispatcher(**kw):
    return ToolDispatcher(home_space_store=None, memory_store=None, **kw)


def test_i_due_strumenti_sono_nel_catalogo():
    nomi = [d["name"] for d in KNOWLEDGE_TOOLS]
    assert "propose" in nomi
    assert "confirm" in nomi


def test_i_nomi_mcp_li_portano_al_ponte():
    """Difetto 3.10.1: i nomi si DERIVANO dal catalogo, non si riscrivono."""
    assert "mcp__hiris__propose" in mcp_names()
    assert "mcp__hiris__confirm" in mcp_names()


def test_il_turno_di_una_promessa_non_li_riceve():
    """`SOLA_LETTURA`: un turno che gira senza nessuno davanti non costruisce."""
    nomi = [d["name"] for d in promise_tools()]
    assert "propose" not in nomi
    assert "confirm" not in nomi
    assert "mcp__hiris__propose" not in mcp_names(by_promise=True)


@pytest.mark.asyncio
async def test_costruisci_passa_l_intento_e_il_turno_all_officina():
    workshop = FintaOfficina()
    d = _dispatcher(workshop=workshop, exchange="t7")
    esito = await d.dispatch("propose", {
        "gesto": "crea", "dominio": "automation", "alias": "X",
        "descrizione": "d", "innesco": [{"trigger": "sun"}],
        "azioni": [{"action": "cover.open_cover"}]})
    verbo, intento, origine, exchange = workshop.chiamate[0]
    assert verbo == "propose"
    assert intento["dominio"] == "automation"
    assert origine == "chat"
    assert exchange == "t7"
    assert esito["proposta_id"] == "p1"


@pytest.mark.asyncio
async def test_conferma_passa_lo_stesso_turno_cosi_la_guardia_puo_scattare():
    workshop = FintaOfficina()
    d = _dispatcher(workshop=workshop, exchange="t7")
    await d.dispatch("confirm", {"proposta_id": "p1"})
    verbo, proposta_id, _origine, exchange = workshop.chiamate[0]
    assert verbo == "apply"
    assert proposta_id == "p1"
    assert exchange == "t7"


@pytest.mark.asyncio
async def test_una_sola_istanza_da_la_stessa_identita_a_costruisci_e_conferma():
    """La proprieta' su cui si regge la guardia non e' che un turno letterale
    combaci per coincidenza fra due test separati (i due qui sopra
    costruiscono ciascuno un proprio `ToolDispatcher`, ed entrambi
    usano "t7" per caso, non per dimostrazione): e' che LA STESSA istanza --
    quella che il chiamante costruisce UNA volta per turno
    (`create_tool_dispatcher`) -- dia la stessa identita' a
    ENTRAMBI gli strumenti quando li chiama in sequenza nello stesso turno.
    fetta «costruire», review indipendente (I3)."""
    workshop = FintaOfficina()
    d = _dispatcher(workshop=workshop, exchange="stesso-turno-vero")
    await d.dispatch("propose", {"gesto": "crea", "dominio": "automation"})
    await d.dispatch("confirm", {"proposta_id": "p1"})
    assert len(workshop.chiamate) == 2
    turno_costruisci = workshop.chiamate[0][3]
    turno_conferma = workshop.chiamate[1][3]
    assert turno_costruisci == turno_conferma == "stesso-turno-vero"


@pytest.mark.asyncio
async def test_senza_officina_lo_strumento_dichiara_un_errore_e_non_solleva():
    d = _dispatcher()
    esito = await d.dispatch("propose", {"gesto": "crea", "dominio": "automation"})
    assert "errore" in esito


@pytest.mark.asyncio
async def test_conferma_senza_identificatore_NON_sceglie_QUI():
    """**Chi sceglie quale proposta, sceglie in un posto solo.**

    Questa prova garantiva che senza id lo strumento rifiutasse e l'officina
    non venisse nemmeno chiamata (`chiamate == []`). Dal 23/09/2026 non e'
    piu' vero, ed e' deliberato: senza id si conferma l'unica proposta in
    sospeso nata in un turno precedente. Il `proposta_id` nasce in un
    risultato di strumento e la cronologia della chat porta solo testo, quindi
    al turno della conferma il modello non ce l'ha MAI -- misurato sulla casa
    vera, e ogni costruzione costava tre turni invece di due.

    Cio' che non e' cambiato, ed e' la ragione per cui questa prova resta: **il
    dispatcher non sceglie**. Inoltra `None` e lascia decidere l'officina, che
    e' l'unica a conoscere l'archivio e i turni. Se scegliesse anche lui, la
    stessa regola vivrebbe in due posti liberi di divergere -- e quello dei
    due che il modello attraversa non e' sempre lo stesso.

    Mutazione ESEGUITA: far scegliere al dispatcher (passare la prima
    pendente invece di `None`) -- rossa.
    Mutazione ESEGUITA: tornare a rifiutare qui senza chiamare l'officina --
    rossa."""
    workshop = FintaOfficina()
    d = _dispatcher(workshop=workshop, exchange="t7")
    await d.dispatch("confirm", {})
    assert workshop.chiamate == [("apply", None, "chat", "t7")], (
        "il dispatcher non deve ne' rifiutare da solo ne' scegliere: "
        "inoltra None e lascia decidere l'officina")


@pytest.mark.asyncio
async def test_conferma_non_lascia_uscire_guasto_rete_verso_il_modello():
    """Punto 7 (residuo): `guasto_rete` e' dichiarato «interno»
    (`handlers_constructions.py`), e sul percorso HTTP lo e' davvero -- quella
    rotta lo legge per scegliere 503 invece di 409 e poi lo toglie dal corpo.
    Sul percorso chat, prima di questa correzione, lo strumento restituiva il
    dizionario di `apply` tale e quale: il flag usciva integro verso il
    modello. O e' interno da entrambe le porte, o il commento mente su una."""
    workshop = FintaOfficina(esito_applica={
        "errore": "Home Assistant non ha risposto: timeout", "guasto_rete": True})
    d = _dispatcher(workshop=workshop, exchange="t7")
    esito = await d.dispatch("confirm", {"proposta_id": "p1"})
    assert "guasto_rete" not in esito
    assert "errore" in esito
