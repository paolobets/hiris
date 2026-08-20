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


def test_il_prompt_di_sistema_spiega_gli_id_fra_parentesi_e_il_parallelismo():
    """Fix finale ④ (review 2026-08-20): il turno riceve lo STESSO nucleo
    della chat, coi suoi `(id: X)` accanto ad aree/piani/automazioni/script
    (`costruisci_nucleo`, vedi `interpreta_promessa`), ma prima di questo fix
    il prompt non lo spiegava affatto, ne' diceva il conteggio del
    parallelismo -- che QUI e' vero al 100% perche' il turno gira su
    `runner.chat`, lo stesso ciclo di `claude_runner.py`
    (`BASE_REGOLE_STRUMENTI`) che conta un giro per risposta, non per
    chiamata."""
    from hiris.app.schedulatore.turno import _prompt_di_sistema
    testo = _prompt_di_sistema()
    assert "(id: X)" in testo, "il prompt non spiega piu' gli id fra parentesi dell'albero"
    assert "IN PARALLELO" in testo, "il prompt non insegna piu' il parallelismo"
    assert "il ciclo conta un giro per risposta, non per chiamata" in testo, (
        "qui la giustificazione del parallelismo e' vera (il turno gira su "
        "runner.chat): deve restare, non diventare la frase falsa del ponte")


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


# --- interpreta_promessa, end-to-end ------------------------------------------
#
# Rilievo minore della review finale: `interpreta_promessa` non era coperta
# end-to-end. E' la SECONDA giuntura non attraversata da nessun test -- la
# prima (`orologio.py` + `verifica.py`, vedi `test_schedulatore_orologio.py`)
# si e' rivelata rotta, ed e' la priorita' fra i minori per lo stesso motivo:
# ogni test altrove costruisce un `TurnoFinto` che RESTITUISCE gia' la
# conclusione, mai un runner che la produce chiamando `concludi` attraverso
# `DispatcherPromessa` -- il percorso vero.
#
# Un `app` vuoto (`{}`) e' legittimo: `costruisci_nucleo` e
# `costruisci_dispatcher_strumenti` sono "SEMPRE componibili" per contratto
# (vedi i loro docstring in `hiris/app/api/handlers_casa.py` e
# `handlers_chat.py`), anche senza archivi -- e' la stessa disciplina che
# rende `interpreta_promessa` provabile senza un server vero.

class _RunnerCheConclude:
    """Un runner finto che CHIAMA `concludi` attraverso il dispatcher che
    riceve -- non lo restituisce gia' pronto: e' cio' che attraversa
    davvero `DispatcherPromessa`, non un suo doppio."""

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
    from hiris.app.schedulatore.turno import interpreta_promessa

    runner = _RunnerCheConclude(avvisare=True, testo="e' salita di 2 gradi")
    app = {"llm_router": runner}

    esito = await interpreta_promessa(app, _promessa_chiedi())

    assert esito == {"avvisare": True, "testo": "e' salita di 2 gradi"}
    # il catalogo che arriva al runner e' quello RISTRETTO (SOLA_LETTURA +
    # concludi), non il catalogo intero della chat -- e' la garanzia
    # strutturale della spec (§6.2), non solo un fatto su questo test
    assert ({d["name"] for d in runner.chiamato_con["strumenti"]}
            == set(SOLA_LETTURA) | {"concludi"})
    assert runner.chiamato_con["agent_type"] == "promessa"


@pytest.mark.asyncio
async def test_interpreta_promessa_senza_concludi_e_un_errore_dichiarato():
    """Il turno che non conclude: `interpreta_promessa` non deve inventare un
    "forse e' andata bene" -- deve dichiarare l'errore, cosi' l'orologio
    marca la promessa `fallita` con un motivo vero (vedi
    `orologio._mantieni_chiedi`)."""
    from hiris.app.schedulatore.turno import interpreta_promessa

    esito = await interpreta_promessa({"llm_router": _RunnerCheNonConclude()},
                                      _promessa_chiedi())

    assert "errore" in esito
    assert "non ha concluso" in esito["errore"]


@pytest.mark.asyncio
async def test_interpreta_promessa_senza_runner_e_un_errore_dichiarato():
    from hiris.app.schedulatore.turno import interpreta_promessa

    esito = await interpreta_promessa({}, _promessa_chiedi())

    assert "errore" in esito
    assert "modello" in esito["errore"]
