"""«Rifalla» e' un turno del proponente (piano degli attori, strato 4, Task
4.4; D16, con le scelte del proprietario del 06/10/2026).

Il turno ha gli strumenti e il contratto del proponente, e chiude il
rifacimento con uno dei suoi tre esiti. Sul ponte si accoda con la precedenza
della chat, e lo stato «in rifacimento» lo dice la coda. Una proposta decisa
mentre il turno e' in volo scarta in silenzio la risposta che arriva dopo.
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from hiris.app import steering
from hiris.app.mind import proposal_redo as redo
from hiris.app.mind import proposer_round as pr
from hiris.app.mind import proposer_turn as pt
from hiris.app.mind.analyst import evidence_of, observation_key
from hiris.app.reasoning.consegna import consegna
from hiris.app.reasoning.queue import PRIORITY_CHAT, ReasoningQueue
from tests.test_proponente import (
    _INTENZIONE_BUONA,
    OGGI,
    _id_nato,
    _Modello,
    casa,  # noqa: F401 -- la fixture, la stessa del giro
    osservazioni,
)

RICHIESTA = "non toccare il termostato, prova con lo scaldabagno"


def _manuale(casa):
    riga = osservazioni()[0]
    return casa["observations"].add_proposal(
        text="Abbassa il termostato di notte", perche="il prelievo notturno sale",
        fingerprint=observation_key(riga), prova=evidence_of(riga),
        stakes=None, now_ts=1.0)


def _seconda(casa):
    riga = osservazioni()[1]
    return casa["observations"].add_proposal(
        text="Sposta la lavatrice dopo le 21", perche="alle 19 costa di piu'",
        fingerprint=observation_key(riga), prova=evidence_of(riga),
        stakes=None, now_ts=2.0)


def _proposta(casa, ident):
    return next(p for p in casa["observations"].proposals() if p["id"] == ident)


def _esiti(**esito):
    return json.dumps({"esiti": [{"osservazione": 0, **esito}]})


# -- La catena -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_il_secondo_giro_vede_la_forma_SCARTATA_e_la_richiesta(casa):
    """Spec dell'attuatore, §7: il filo del «Rifalla» si prova sul contenuto.
    Al secondo giro il modello vede l'osservazione, la forma scartata al primo
    e la richiesta di adesso -- e la vede col catalogo del proponente.

    Mutazione ESEGUITA (06/10/2026): `build_question` senza il filo dei giri
    -- rossa, la forma scartata non arriva."""
    ident = _manuale(casa)
    casa["llm_router"] = _Modello(
        ([], _esiti(esito="a_mano", testo="Spegni lo scaldabagno alle 23",
                    perche="di notte non serve acqua calda")),
        ([], _esiti(esito="a_mano", testo="Spegni lo scaldabagno alle 22",
                    perche="un'ora prima costa meno")))

    await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)
    await redo.redo(casa, casa["observations"], _proposta(casa, ident), "un'ora prima")

    seconda = casa["llm_router"].domande[1]
    assert "[0] Scaldabagno" in seconda, "l'osservazione non e' arrivata"
    assert "Abbassa il termostato di notte" in seconda, "la forma scartata non c'e'"
    assert RICHIESTA in seconda and "un'ora prima" in seconda
    assert "propose" in casa["llm_router"].strumenti[1]
    riga = _proposta(casa, ident)
    assert riga["testo"] == "Spegni lo scaldabagno alle 22"
    assert riga["perche"] == "un'ora prima costa meno"
    assert [g["esito"] for g in riga["giri"]] == ["a_mano", "a_mano"]
    assert riga["stato"] == "attesa", "un giro a mano non chiude niente"


@pytest.mark.asyncio
async def test_il_giro_si_conta_come_PROPONENTE_non_come_chat(casa):
    """D16: e' un turno del proponente, e il suo costo sta con i suoi. Fino al
    06/10/2026 si contava come chat.

    Mutazione ESEGUITA (06/10/2026): `chain_turn` con specie «chat» -- rossa."""
    ident = _manuale(casa)
    casa["llm_router"] = _Modello(([], _esiti(esito="niente", perche="x")))

    await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)

    assert [t["species"] for t in casa["usage"].turns()] == [steering.PROPOSER_SPECIES]


@pytest.mark.asyncio
async def test_NIENTE_lascia_la_proposta_com_era_e_lo_scrive_nel_filo(casa):
    """Scelta del proprietario: «niente» entra nel filo come un giro
    qualunque, col perche', e la proposta resta aperta e invariata."""
    ident = _manuale(casa)
    casa["llm_router"] = _Modello(([], _esiti(
        esito="niente", perche="senza il termostato non c'e' altro da spostare")))

    esito = await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)

    riga = _proposta(casa, ident)
    assert esito["esito"] == pt.NOTHING
    assert riga["testo"] == "Abbassa il termostato di notte"
    assert riga["stato"] == "attesa"
    assert riga["giri"][-1]["perche"].startswith("senza il termostato")


@pytest.mark.asyncio
async def test_COSTRUITA_chiude_la_proposta_SUPERATA_e_lega_la_costruita(casa):
    """Scelta del proprietario, come D24-1: se il rifacimento diventa un
    oggetto di Home Assistant, la proposta a mano si chiude `superata`
    all'arrivo, e la costruita porta l'impronta e la prova della domanda.

    Mutazione ESEGUITA (06/10/2026): `settle` senza `close_proposal` -- rossa,
    la proposta resta «attesa»."""
    ident = _manuale(casa)
    casa["llm_router"] = _Modello((
        [("propose", _INTENZIONE_BUONA)],
        lambda risultati: _esiti(esito="costruita", proposta_id=_id_nato(risultati))))

    await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)

    riga = _proposta(casa, ident)
    nata = _id_nato(casa["llm_router"].risultati)
    assert riga["stato"] == "superata"
    assert riga["esito_nota"] == pt.SUPERSEDED_WHY
    assert riga["giri"][-1]["proposta_id"] == nata
    costruita = casa["constructions"].read(nata, now=time.time())
    assert costruita["impronta"] == observation_key(osservazioni()[0])


@pytest.mark.asyncio
async def test_una_COSTRUITA_inventata_non_chiude_niente(casa):
    """Il contratto del proponente vale anche qui: un id che non e' nato in
    questo turno si rifiuta, e la risposta e' illeggibile."""
    ident = _manuale(casa)
    casa["llm_router"] = _Modello(([], _esiti(esito="costruita", proposta_id="finto")))

    esito = await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)

    assert esito["esito"] == redo.UNREADABLE
    assert _proposta(casa, ident)["stato"] == "attesa"
    assert _proposta(casa, ident)["giri"] == []


@pytest.mark.asyncio
async def test_sulla_CATENA_due_pressioni_ravvicinate_fanno_UN_turno_solo(casa):
    """Sulla catena il turno non passa dalla coda, e la coda non puo' dire che
    e' in volo: lo dice `CHAIN_IN_FLIGHT`, finche' la richiesta e' aperta. Un
    secondo «Rifalla» mentre il primo aspetta il modello non parte (rilievo
    N68-1 del giro 68).

    Mutazione ESEGUITA (06/10/2026): `redo` senza il controllo su
    `CHAIN_IN_FLIGHT` -- rossa, il secondo parte e il modello e' chiamato due
    volte."""
    ident = _manuale(casa)
    partito, libera = asyncio.Event(), asyncio.Event()

    class _Lento:
        def __init__(self):
            self.chiamate = 0
            self.last_tool_calls: list = []

        async def chat(self, **_kwargs):
            self.chiamate += 1
            if self.chiamate == 1:
                partito.set()
                await libera.wait()
            return _esiti(esito="niente", perche="x")

    casa["llm_router"] = _Lento()
    primo = asyncio.create_task(
        redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA))
    await asyncio.wait_for(partito.wait(), 5)

    with pytest.raises(redo.InFlight):
        await redo.redo(casa, casa["observations"], _proposta(casa, ident), "di nuovo")
    libera.set()
    await primo

    assert casa["llm_router"].chiamate == 1
    assert ident not in casa[redo.CHAIN_IN_FLIGHT], "finita la richiesta, si libera"


# -- Il ponte ---------------------------------------------------------------------

@pytest.fixture()
def ponte(casa, tmp_path, monkeypatch):
    coda = ReasoningQueue(str(tmp_path / "coda.db"))
    casa["reasoning_queue"] = coda
    casa["models_config"] = {}
    monkeypatch.setattr(steering, "who_answers", lambda app: ("ponte", ""))
    monkeypatch.setattr("hiris.app.mind.proposal_redo.start",
                        lambda app, species: steering.Start("ponte", "", None))
    try:
        yield casa, coda
    finally:
        coda.close()


def _risposta_piano(coda, risposta, *, exchange="turno-ponte"):
    turno = coda.claim(time.time())
    return turno, {"reply": risposta, "outcome": "riuscito", "exchange_id": exchange}


@pytest.mark.asyncio
async def test_sul_PONTE_si_accoda_con_la_precedenza_della_CHAT(ponte):
    """Scelta del proprietario: c'e' una persona che aspetta davanti alla
    pagina, e la ragione di D4 («la chat passa avanti») e' quella.

    Mutazione ESEGUITA (06/10/2026): `enqueue_turn` senza `priority` --
    rossa, la precedenza e' quella di sfondo."""
    casa, coda = ponte
    ident = _manuale(casa)

    esito = await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)

    turno = coda.latest(pt.PROPOSAL_TURN_KIND, wake_key=redo.WAKE_KEY,
                        wake_value=ident)
    assert esito["esito"] is None
    assert turno["priority"] == PRIORITY_CHAT
    assert turno["wake"] == {"proposta": ident, "richiesta": RICHIESTA}
    assert "Abbassa il termostato di notte" in turno["context"]["history"][0]["content"]


@pytest.mark.asyncio
async def test_lo_stato_IN_CORSO_lo_dice_la_coda_e_un_secondo_giro_aspetta(ponte):
    """Lo stato non ha una seconda casa (fondamenta 2): lo dice la coda, e
    quindi sopravvive a una ricarica. Un secondo «Rifalla» mentre il primo e'
    in volo non parte."""
    casa, _coda = ponte
    ident = _manuale(casa)
    await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)

    stato = redo.state(casa, _proposta(casa, ident))

    assert stato["stato"] == redo.RUNNING
    assert stato["richiesta"] == RICHIESTA
    with pytest.raises(redo.InFlight):
        await redo.redo(casa, casa["observations"], _proposta(casa, ident), "altro")


@pytest.mark.asyncio
async def test_la_CONSEGNA_scrive_il_giro_una_volta_sola(ponte):
    """Il ponte risponde minuti dopo, e nessun giro periodico passa a
    raccogliere: la consegna scrive l'esito nel filo. Una seconda lettura
    dello stesso turno non scrive un secondo giro.

    Mutazione ESEGUITA (06/10/2026): `consegna` senza il ramo del «Rifalla»
    -- rossa, il giro non c'e' e la riga resta «illeggibile»."""
    casa, coda = ponte
    ident = _manuale(casa)
    await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)
    turno, decisione = _risposta_piano(coda, _esiti(
        esito="a_mano", testo="Spegni lo scaldabagno alle 23", perche="di notte"))

    esito = await consegna(casa, turno["job_id"], turno["nonce"], decisione, time.time())
    redo.deliver(casa, coda.get(turno["job_id"]), decisione)

    riga = _proposta(casa, ident)
    assert esito == "rifalla_a_mano"
    assert riga["testo"] == "Spegni lo scaldabagno alle 23"
    assert len(riga["giri"]) == 1 and riga["giri"][0]["turno"] == turno["job_id"]
    assert redo.state(casa, riga) is None, "un giro scritto non e' piu' in corso"


@pytest.mark.asyncio
async def test_una_proposta_DECISA_mentre_il_giro_e_in_volo_scarta_la_risposta(ponte):
    """Scelta del proprietario: si puo' rifiutare mentre il rifacimento e' in
    volo, e la risposta che arriva dopo si scarta in silenzio.

    Mutazione ESEGUITA (06/10/2026): `settle` senza il controllo dello stato
    -- rossa, un giro scritto su una proposta rifiutata."""
    casa, coda = ponte
    ident = _manuale(casa)
    await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)
    casa["observations"].close_proposal(ident, "rifiutata")
    turno, decisione = _risposta_piano(coda, _esiti(
        esito="a_mano", testo="Spegni lo scaldabagno", perche="x"))

    esito = await consegna(casa, turno["job_id"], turno["nonce"], decisione, time.time())

    assert esito == "rifalla_" + redo.DISCARDED
    assert _proposta(casa, ident)["giri"] == []


@pytest.mark.asyncio
async def test_SCADUTO_e_VUOTO_si_dicono_e_la_richiesta_resta(ponte):
    """Alla scadenza si dice, senza ripiegare a consumo (scelta del
    proprietario), e la richiesta scritta resta per riprovare. Un turno
    deciso senza risposta e' un fallimento, non una proposta illeggibile."""
    casa, coda = ponte
    ident = _manuale(casa)
    await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)
    coda.sweep_expired(time.time() + 24 * 3600)

    scaduto = redo.state(casa, _proposta(casa, ident))
    assert scaduto["stato"] == redo.EXPIRED and scaduto["richiesta"] == RICHIESTA

    await redo.redo(casa, casa["observations"], _proposta(casa, ident), "di nuovo")
    turno, decisione = _risposta_piano(coda, "")
    await consegna(casa, turno["job_id"], turno["nonce"], decisione, time.time())
    assert redo.state(casa, _proposta(casa, ident))["stato"] == redo.FAILED


@pytest.mark.asyncio
async def test_un_rifacimento_NON_ferma_e_non_nasconde_il_giro_orario(ponte):
    """Il giro e i rifacimenti stanno nella stessa specie: un «Rifalla» in volo
    non e' il turno del giro, e un «Rifalla» appena finito non lo fa aspettare
    un'ora (`RETRY_HOLD_S`).

    Mutazione ESEGUITA (06/10/2026): il giro senza `wake_key=ROUND_KEY` --
    rossa, nessun turno del giro accodato."""
    casa, coda = ponte
    ident = _manuale(casa)
    await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)

    await pr.proposer_round(casa)

    giro = coda.latest(pt.PROPOSAL_TURN_KIND, wake_key=pr.ROUND_KEY)
    assert giro is not None and giro["wake"]["giorno"] == OGGI


@pytest.mark.asyncio
async def test_un_rifacimento_di_A_non_tocca_lo_stato_ne_la_partenza_di_B(ponte):
    """La coda distingue il rifacimento di una proposta da quello di
    un'altra per il valore della sveglia. Senza, con «Rifalla» in volo su A la
    riga di B direbbe «in corso» con la richiesta di A, e un «Rifalla» su B
    avrebbe un 409 (rilievo G68-1 del giro 68).

    Mutazione ESEGUITA (06/10/2026): `ReasoningQueue.latest` che ignora
    `wake_value` -- rossa, B si legge «in corso» con la richiesta di A."""
    casa, coda = ponte
    a, b = _manuale(casa), _seconda(casa)
    await redo.redo(casa, casa["observations"], _proposta(casa, a), RICHIESTA)

    assert redo.state(casa, _proposta(casa, b)) is None
    await redo.redo(casa, casa["observations"], _proposta(casa, b), "piu' tardi")

    assert redo.state(casa, _proposta(casa, a))["richiesta"] == RICHIESTA
    assert redo.state(casa, _proposta(casa, b))["richiesta"] == "piu' tardi"
    assert coda.latest(pt.PROPOSAL_TURN_KIND, wake_key=redo.WAKE_KEY,
                       wake_value=b)["wake"]["proposta"] == b


@pytest.mark.asyncio
async def test_un_turno_ATTESO_oltre_la_scadenza_si_dice_SCADUTO(ponte, monkeypatch):
    """Fra la scadenza e la spazzata la coda tiene il turno `pending`: la
    pagina non deve dire «in corso» per un turno che il ponte non consegnera'
    piu' (rilievo N68-1 del giro 68). E un turno scaduto non ferma un nuovo
    «Rifalla».

    Mutazione ESEGUITA (06/10/2026): `state` con `RUNNING` anche oltre
    `deadline_ts` -- rossa, il turno scaduto si legge «in corso»."""
    casa, coda = ponte
    ident = _manuale(casa)
    await redo.redo(casa, casa["observations"], _proposta(casa, ident), RICHIESTA)
    job = coda.latest(pt.PROPOSAL_TURN_KIND, wake_key=redo.WAKE_KEY,
                      wake_value=ident)
    oltre = job["deadline_ts"] + 1
    monkeypatch.setattr(redo.time, "time", lambda: oltre)

    stato = redo.state(casa, _proposta(casa, ident))

    assert job["status"] == "pending"
    assert stato["stato"] == redo.EXPIRED and stato["richiesta"] == RICHIESTA
    await redo.redo(casa, casa["observations"], _proposta(casa, ident), "di nuovo")
