"""I due strumenti: `costruisci` propone, `conferma` applica. E il catalogo."""
import pytest

from hiris.app.agent.runner import nomi_mcp
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA, DispatcherStrumenti
from hiris.app.schedulatore.turno import strumenti_promessa


class FintaOfficina:
    def __init__(self, esito_proponi=None, esito_applica=None):
        self.chiamate = []
        self._proponi = esito_proponi or {"proposta_id": "p1", "anteprima": "farei cosi'"}
        self._applica = esito_applica or {"applicata": True, "esecuzione_id": "e1",
                                          "entita": ["automation.x"], "avviso": None}

    async def proponi(self, intento, *, origine, turno, adesso):
        self.chiamate.append(("proponi", intento, origine, turno))
        return self._proponi

    async def applica(self, proposta_id, *, origine, turno, adesso):
        self.chiamate.append(("applica", proposta_id, origine, turno))
        return self._applica


def _dispatcher(**kw):
    return DispatcherStrumenti(archivio_casa=None, archivio_memoria=None, **kw)


def test_i_due_strumenti_sono_nel_catalogo():
    nomi = [d["name"] for d in STRUMENTI_CONOSCENZA]
    assert "costruisci" in nomi
    assert "conferma" in nomi


def test_i_nomi_mcp_li_portano_al_ponte():
    """Difetto 3.10.1: i nomi si DERIVANO dal catalogo, non si riscrivono."""
    assert "mcp__hiris__costruisci" in nomi_mcp()
    assert "mcp__hiris__conferma" in nomi_mcp()


def test_il_turno_di_una_promessa_non_li_riceve():
    """`SOLA_LETTURA`: un turno che gira senza nessuno davanti non costruisce."""
    nomi = [d["name"] for d in strumenti_promessa()]
    assert "costruisci" not in nomi
    assert "conferma" not in nomi
    assert "mcp__hiris__costruisci" not in nomi_mcp(per_promessa=True)


@pytest.mark.asyncio
async def test_costruisci_passa_l_intento_e_il_turno_all_officina():
    officina = FintaOfficina()
    d = _dispatcher(officina=officina, turno="t7")
    esito = await d.dispatch("costruisci", {
        "gesto": "crea", "dominio": "automation", "alias": "X",
        "descrizione": "d", "innesco": [{"trigger": "sun"}],
        "azioni": [{"action": "cover.open_cover"}]})
    verbo, intento, origine, turno = officina.chiamate[0]
    assert verbo == "proponi"
    assert intento["dominio"] == "automation"
    assert origine == "chat"
    assert turno == "t7"
    assert esito["proposta_id"] == "p1"


@pytest.mark.asyncio
async def test_conferma_passa_lo_stesso_turno_cosi_la_guardia_puo_scattare():
    officina = FintaOfficina()
    d = _dispatcher(officina=officina, turno="t7")
    await d.dispatch("conferma", {"proposta_id": "p1"})
    verbo, proposta_id, origine, turno = officina.chiamate[0]
    assert verbo == "applica"
    assert proposta_id == "p1"
    assert turno == "t7"


@pytest.mark.asyncio
async def test_una_sola_istanza_da_la_stessa_identita_a_costruisci_e_conferma():
    """La proprieta' su cui si regge la guardia non e' che un turno letterale
    combaci per coincidenza fra due test separati (i due qui sopra
    costruiscono ciascuno un proprio `DispatcherStrumenti`, ed entrambi
    usano "t7" per caso, non per dimostrazione): e' che LA STESSA istanza --
    quella che il chiamante costruisce UNA volta per turno
    (`costruisci_dispatcher_strumenti`) -- dia la stessa identita' a
    ENTRAMBI gli strumenti quando li chiama in sequenza nello stesso turno.
    fetta «costruire», review indipendente (I3)."""
    officina = FintaOfficina()
    d = _dispatcher(officina=officina, turno="stesso-turno-vero")
    await d.dispatch("costruisci", {"gesto": "crea", "dominio": "automation"})
    await d.dispatch("conferma", {"proposta_id": "p1"})
    assert len(officina.chiamate) == 2
    turno_costruisci = officina.chiamate[0][3]
    turno_conferma = officina.chiamate[1][3]
    assert turno_costruisci == turno_conferma == "stesso-turno-vero"


@pytest.mark.asyncio
async def test_senza_officina_lo_strumento_dichiara_un_errore_e_non_solleva():
    d = _dispatcher()
    esito = await d.dispatch("costruisci", {"gesto": "crea", "dominio": "automation"})
    assert "errore" in esito


@pytest.mark.asyncio
async def test_conferma_senza_identificatore_non_indovina():
    officina = FintaOfficina()
    d = _dispatcher(officina=officina, turno="t7")
    esito = await d.dispatch("conferma", {})
    assert "errore" in esito
    assert officina.chiamate == []


@pytest.mark.asyncio
async def test_conferma_non_lascia_uscire_guasto_rete_verso_il_modello():
    """Punto 7 (residuo): `guasto_rete` e' dichiarato «interno»
    (`handlers_costruzioni.py`), e sul percorso HTTP lo e' davvero -- quella
    rotta lo legge per scegliere 503 invece di 409 e poi lo toglie dal corpo.
    Sul percorso chat, prima di questa correzione, lo strumento restituiva il
    dizionario di `applica` tale e quale: il flag usciva integro verso il
    modello. O e' interno da entrambe le porte, o il commento mente su una."""
    officina = FintaOfficina(esito_applica={
        "errore": "Home Assistant non ha risposto: timeout", "guasto_rete": True})
    d = _dispatcher(officina=officina, turno="t7")
    esito = await d.dispatch("conferma", {"proposta_id": "p1"})
    assert "guasto_rete" not in esito
    assert "errore" in esito
