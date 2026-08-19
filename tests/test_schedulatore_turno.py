"""Il turno di «chiedi»: guarda, risponde, e non tocca niente."""
import pytest

from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA
from hiris.app.schedulatore.turno import (
    SOLA_LETTURA, DispatcherPromessa, strumenti_promessa,
)

# Marcatore applicato ai singoli test asincroni sotto, non al modulo: un
# `pytestmark` globale su un file con test SINCRONI (i tre sul catalogo, qui
# sopra) produce un warning pytest-asyncio nuovo -- e la fetta non ne ammette.


def test_il_catalogo_non_contiene_gli_strumenti_che_scrivono():
    nomi = {d["name"] for d in strumenti_promessa()}
    assert "esegui" not in nomi
    assert "ricorda" not in nomi
    assert "prometti" not in nomi
    assert "disdici" not in nomi


def test_il_catalogo_contiene_i_lettori_e_concludi():
    nomi = {d["name"] for d in strumenti_promessa()}
    assert nomi == set(SOLA_LETTURA) | {"concludi"}


def test_ogni_nome_ammesso_esiste_davvero_nel_catalogo_della_chat():
    """Un rinomino altrove non deve poter svuotare questo catalogo in silenzio."""
    veri = {d["name"] for d in STRUMENTI_CONOSCENZA}
    assert set(SOLA_LETTURA) <= veri


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
    d = DispatcherPromessa(sotto)
    esito = await d.dispatch("esegui", {"servizio": "light.turn_on"})
    assert "errore" in esito
    assert sotto.chiamati == []


@pytest.mark.asyncio
async def test_un_lettore_passa_al_dispatcher_sottostante():
    sotto = DispatcherFinto()
    d = DispatcherPromessa(sotto)
    assert await d.dispatch("guarda", {}) == {"ok": "guarda"}
    assert sotto.chiamati == ["guarda"]


@pytest.mark.asyncio
async def test_concludi_non_scende_e_resta_nel_wrapper():
    sotto = DispatcherFinto()
    d = DispatcherPromessa(sotto)
    esito = await d.dispatch("concludi", {"avvisare": True, "testo": "fa caldo"})
    assert "errore" not in esito
    assert sotto.chiamati == []
    assert d.conclusione == {"avvisare": True, "testo": "fa caldo"}


@pytest.mark.asyncio
async def test_concludi_senza_avvisare_e_un_rifiuto_leggibile():
    d = DispatcherPromessa(DispatcherFinto())
    esito = await d.dispatch("concludi", {"testo": "fa caldo"})
    assert "errore" in esito
    assert d.conclusione is None


@pytest.mark.asyncio
async def test_l_ultima_conclusione_vince_e_non_si_accumula():
    d = DispatcherPromessa(DispatcherFinto())
    await d.dispatch("concludi", {"avvisare": False, "testo": "niente"})
    await d.dispatch("concludi", {"avvisare": True, "testo": "invece si'"})
    assert d.conclusione == {"avvisare": True, "testo": "invece si'"}
