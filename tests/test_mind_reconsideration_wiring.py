"""Il cablaggio dell'anello: **chi chiede «è ora?», e cosa succede se sì**.

Quattro inneschi (spec §5.1) -- il primo avvio, l'obiettivo cambiato, qualcosa
di nuovo in casa, la cadenza -- e una sola funzione che li pone tutti e
quattro (`cadence.reason_to_reconsider`). Qui si prova che il giro periodico
la interroghi davvero e agisca di conseguenza: le prove dei singoli inneschi
stanno in `test_mind_impronta.py`, quelle del giro in `test_mind_observer.py`.
"""
import os

import pytest

from hiris.app.mind.scope import OBSERVER
from hiris.app.mind.store import ObservationsStore
from hiris.app.server import reconsideration_round

GIORNO = 86400.0


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


class _Anagrafe:
    def __init__(self, entita):
        self._entita = entita

    def read(self):
        return {"entita": self._entita, "aree": []}


def _entita(eid, **extra):
    riga = {"id": eid, "nome": eid, "classe": None, "unita": None,
            "translation_key": None, "categoria": None,
            "disabilitata": 0, "nascosta": 0, "area_id": None}
    riga.update(extra)
    return riga


class _Modello:
    def __init__(self, risposta="[]"):
        self.risposta = risposta
        self.chiamate = 0

    async def chat(self, user_message, **kw):
        self.chiamate += 1
        return self.risposta


class _Ponte:
    """Il client di Home Assistant, dal lato della misura della memoria."""

    def __init__(self, memoria_s=7 * GIORNO):
        self.memoria_s = memoria_s
        self.sonde = 0

    async def recorded_changes(self, entity_ids, windows):
        self.sonde += len(windows)
        import time
        adesso = time.time()
        return [0 if (adesso - inizio) > self.memoria_s else 9 for inizio, _ in windows]


def _app(archivio, anagrafe, modello):
    return {"observations": archivio, "home_space_store": anagrafe,
            "llm_router": modello}


@pytest.mark.asyncio
async def test_al_primo_avvio_l_osservatore_gira_e_lascia_traccia(archivio):
    modello = _Modello('[{"id": "climate.x", "dentro": true, "motivo": "scalda"}]')
    anagrafe = _Anagrafe([_entita("climate.x")])

    esito = await reconsideration_round(_app(archivio, anagrafe, modello), _Ponte())

    assert esito == {"decise": 1, "rifiutate": 0, "ignorate": 0, "candidate": 1}
    assert modello.chiamate == 1
    assert archivio.scope()["climate.x"]["dentro"] is True
    ultima = archivio.last_reconsideration()
    assert "mai" in ultima["motivo"]


@pytest.mark.asyncio
async def test_la_finestra_si_MISURA_al_giro_e_finisce_nella_traccia(archivio):
    """Il numero non e' una costante e non e' quello di ieri: si rimisura al
    giro che lo usa, e si scrive accanto alla riconsiderazione che ha
    provocato. Il proprietario puo' cambiare il recorder fra un giro e
    l'altro.

    Mutazione che la uccide: scrivere una cadenza fissa.
    """
    ponte = _Ponte(memoria_s=7 * GIORNO)
    anagrafe = _Anagrafe([_entita("climate.x")])

    await reconsideration_round(_app(archivio, anagrafe, _Modello()), ponte)

    ultima = archivio.last_reconsideration()
    assert ponte.sonde > 0
    # La tolleranza e' **mezza giornata, e non e' generosita'**: e' la
    # risoluzione della misura. La scala grossa lascia un tratto di quattro
    # giorni e la seconda raffica lo divide in otto, quindi il risultato cade
    # sempre su un multiplo di mezza giornata -- e il verso e' sempre lo
    # stesso, verso il basso (vedi `cadence.measure_memory_window`: la misura
    # non e' mai piu' LUNGA della memoria vera).
    assert 6.5 * GIORNO <= ultima["finestra_s"] <= 7 * GIORNO
    assert ultima["cadenza_s"] == pytest.approx(ultima["finestra_s"] / 2)


@pytest.mark.asyncio
async def test_se_non_e_ora_NON_si_paga_ne_il_modello_ne_la_sonda(archivio):
    """**Il costo di non fare niente deve essere zero.** Questo giro scatta
    ogni dieci minuti: una misura della memoria a ogni passaggio sarebbero 144
    misure al giorno -- 80 MB di traffico -- per rispondere «non e' ora».

    Mutazione che la uccide: misurare la finestra prima di chiedersi se e' ora.
    """
    import time
    archivio.decide_scope("climate.x", inside=True, reason="pesa", author=OBSERVER)
    archivio.record_reconsideration(when_ts=time.time(), window_s=7 * GIORNO,
                                    cadence_s=3.5 * GIORNO, reason="fatta")
    modello = _Modello()
    ponte = _Ponte()

    esito = await reconsideration_round(
        _app(archivio, _Anagrafe([_entita("climate.x")]), modello), ponte)

    assert esito is None
    assert modello.chiamate == 0
    assert ponte.sonde == 0


@pytest.mark.asyncio
async def test_un_entita_NUOVA_fa_girare_senza_aspettare_la_cadenza(archivio):
    """Una lampadina installata stamattina non resta invisibile fino a
    giovedi': cio' che non e' osservato non esiste piu', e i giorni mancanti
    non tornano."""
    import time
    archivio.decide_scope("climate.x", inside=True, reason="pesa", author=OBSERVER)
    archivio.record_reconsideration(when_ts=time.time(), window_s=7 * GIORNO,
                                    cadence_s=3.5 * GIORNO, reason="fatta")
    modello = _Modello('[{"id": "light.nuova", "dentro": true, "motivo": "si accende"}]')
    anagrafe = _Anagrafe([_entita("climate.x"), _entita("light.nuova")])

    await reconsideration_round(_app(archivio, anagrafe, modello), _Ponte())

    assert modello.chiamate == 1
    assert "light.nuova" in archivio.scope()


@pytest.mark.asyncio
async def test_le_entita_di_servizio_non_sono_MAI_novita(archivio):
    """**Il difetto che questo giro avrebbe avuto per sempre.** L'osservatore
    non giudica le entita' di servizio e le nascoste (decisione del
    proprietario, 10/09/2026): quindi nessuna di esse finisce mai nello scope,
    quindi sarebbero «nuove» a ogni singolo giro -- 452 su questa casa -- e
    l'osservatore girerebbe ogni dieci minuti per sempre.

    L'impronta si chiede sulle stesse entita' che si mostrano al modello, non
    sull'anagrafe intera.

    Mutazione che la uccide: passare tutte le entita' a `undecided`.
    """
    import time
    archivio.decide_scope("climate.x", inside=True, reason="pesa", author=OBSERVER)
    archivio.record_reconsideration(when_ts=time.time(), window_s=7 * GIORNO,
                                    cadence_s=3.5 * GIORNO, reason="fatta")
    modello = _Modello()
    anagrafe = _Anagrafe([_entita("climate.x"),
                          _entita("sensor.wifi", categoria="diagnostic"),
                          _entita("light.vecchia", nascosta=1)])

    esito = await reconsideration_round(_app(archivio, anagrafe, modello), _Ponte())

    assert esito is None
    assert modello.chiamate == 0


@pytest.mark.asyncio
async def test_senza_modello_o_senza_archivio_il_giro_non_solleva(archivio):
    """Gira ogni dieci minuti per sempre: un'eccezione su un avvio a meta'
    fermerebbe lo schedulatore, non solo questo giro."""
    anagrafe = _Anagrafe([_entita("climate.x")])

    assert await reconsideration_round({"observations": archivio,
                                        "home_space_store": anagrafe}, _Ponte()) is None
    assert await reconsideration_round({"llm_router": _Modello()}, _Ponte()) is None
    assert await reconsideration_round({}, None) is None


@pytest.mark.asyncio
async def test_una_memoria_non_misurabile_non_ferma_il_primo_giro(archivio):
    """Home Assistant muto alla sonda non deve lasciare una casa senza scope:
    il giro si fa lo stesso, e la riconsiderazione **dichiara** che la finestra
    non si e' misurata invece di inventarne una.

    Mutazione che la uccide: fermarsi quando la finestra e' `None`.
    """
    class _Muto:
        async def recorded_changes(self, entity_ids, windows):
            return [None] * len(windows)

    modello = _Modello('[{"id": "climate.x", "dentro": true, "motivo": "scalda"}]')

    await reconsideration_round(
        _app(archivio, _Anagrafe([_entita("climate.x")]), modello), _Muto())

    assert modello.chiamate == 1
    ultima = archivio.last_reconsideration()
    assert ultima["finestra_s"] is None
    assert ultima["cadenza_s"] is None
