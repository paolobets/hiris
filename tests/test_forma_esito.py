"""Una forma dell'esito per le due porte di scrittura (E-04, Tappa 7, Task 2,
decisione D2a).

La porta dei servizi (`action/actuator.py`) e quella della configurazione
(`action/construction/workshop.py`) rispondono con la stessa forma: `eseguito`
sempre; sul rifiuto `errore` (la frase di HIRIS) e `causa`, la busta del
client col motivo di Home Assistant INTATTO e il suo codice
(`action/write_outcome.py`).

Gira il client VERO sul trasporto finto (`scripts/casa_finta.py`) per tutte e
due le porte: il rifiuto e il silenzio si fabbricano dall'altra parte del filo,
come li manderebbe Home Assistant.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import Refused, Silence

from hiris.app.action.actuator import ActionActuator
from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.workshop import Workshop
from hiris.app.action.journal import Journal
from hiris.app.action.write_outcome import silent
from hiris.app.proxy.ha_client import REFUSAL, REQUEST, SILENCE
from tests.test_action_actuator import (
    SALOTTO_ACCESO,
    SPEGNI_IL_SALOTTO,
    FintaCache,
    _client,
    _registro_pronto,
)
from tests.test_construction_workshop import ADESSO, WorkshopHouse, _intento

#: Il corpo di un 400, nella forma di `HomeAssistantView.json_message`
#: (`{"message": ...}`): lo stesso per le due rotte, cosi' la sola differenza
#: fra i due esiti e' la porta che lo racconta.
MOTIVO = "Message malformed: extra keys not allowed @ data['luminosita']"


@pytest.fixture()
def cronaca(tmp_path):
    journal = Journal(os.path.join(str(tmp_path), "azioni.db"))
    yield journal
    journal.close()


async def _servizi(cronaca, **faults) -> dict:
    """L'esito della porta dei servizi su «spegni il salotto»."""
    porta = ActionActuator(_client(**faults), await _registro_pronto(),
                           FintaCache(SALOTTO_ACCESO), journal=cronaca)
    return await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")


async def _configurazione(tmp_path, cronaca, **override) -> dict:
    """L'esito della porta della configurazione su una proposta confermata
    nel turno dopo."""
    archivio = ConstructionStore(os.path.join(str(tmp_path), "costruzioni.db"))
    try:
        house = WorkshopHouse(**override)
        officina = Workshop(house.client, archivio, cronaca)
        proposta = await officina.propose(_intento(), actor="chat", exchange="t1",
                                          now=ADESSO)
        return await officina.apply(proposta["proposta_id"], actor="chat",
                                    exchange="t2", now=ADESSO + 60)
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_stesso_rifiuto_stessa_forma_due_porte(
        tmp_path, cronaca):
    """Home Assistant dice di no, con lo stesso motivo, alle due porte: i due
    esiti hanno le stesse chiavi, e la stessa `causa` -- il motivo intatto,
    il codice, il tipo.

    Mutazione eseguita il 07/10/2026: in `Workshop._fallita` l'esito senza
    `causa` (`{"eseguito": False, "errore": reason, "esecuzione_id": ...}`)
    -> rossa sul confronto delle chiavi (`{'causa'}` in piu' dai servizi);
    ripristinata, `git diff` di `workshop.py` senza la riga."""
    servizi = await _servizi(cronaca, refuse={
        "POST /api/services/light/turn_off": Refused(400, MOTIVO)})
    configurazione = await _configurazione(tmp_path, cronaca,
                                           salva=Refused(400, MOTIVO))

    assert set(servizi) == set(configurazione) == {
        "eseguito", "errore", "causa", "esecuzione_id"}
    assert servizi["eseguito"] is configurazione["eseguito"] is False
    for esito in (servizi, configurazione):
        assert esito["causa"] == {"errore": MOTIVO, "causa": REFUSAL, "codice": 400}
        assert MOTIVO in esito["errore"]


@pytest.mark.asyncio
async def test_stesso_silenzio_stessa_forma_due_porte(tmp_path, cronaca):
    """Il trasporto si rompe durante la scrittura: tutte e due le porte lo
    dicono silenzio, con la busta del client, e nessuna lo dice «rifiutato».

    Mutazione eseguita il 07/10/2026: in `ActionActuator._failed`
    `refused(message)` senza la busta -> rossa su `silent(servizi)` (la causa
    diventa `richiesta`); ripristinata."""
    servizi = await _servizi(cronaca, silence={"POST /api/services/light/turn_off"})
    configurazione = await _configurazione(
        tmp_path, cronaca, salva=Silence("finta interruzione durante il salvataggio"))

    assert set(servizi) == set(configurazione)
    for esito in (servizi, configurazione):
        assert esito["eseguito"] is False
        assert silent(esito)
        assert esito["causa"]["causa"] == SILENCE
        assert "rifiutat" not in esito["errore"]


@pytest.mark.asyncio
async def test_rifiuto_hiris_causa_richiesta(tmp_path, cronaca):
    """Un no deciso PRIMA della rete -- la verifica dei servizi, il cancello
    del turno dell'officina -- ha la stessa forma, con la causa che la busta
    del client da' a una domanda fermata prima di partire: `richiesta`."""
    porta = ActionActuator(_client(), await _registro_pronto(),
                           FintaCache(SALOTTO_ACCESO), journal=cronaca)
    servizi = await porta.execute({"servizio": "light.non_esiste",
                                   "bersaglio": {"entita": ["light.salotto"]}},
                                  actor="chat")
    archivio = ConstructionStore(os.path.join(str(tmp_path), "costruzioni.db"))
    try:
        officina = Workshop(WorkshopHouse().client, archivio, cronaca)
        proposta = await officina.propose(_intento(), actor="chat", exchange="t1",
                                          now=ADESSO)
        configurazione = await officina.apply(proposta["proposta_id"], actor="chat",
                                              exchange="t1", now=ADESSO + 60)
    finally:
        archivio.close()

    assert set(servizi) == set(configurazione) == {"eseguito", "errore", "causa"}
    for esito in (servizi, configurazione):
        assert esito["eseguito"] is False
        assert esito["causa"]["causa"] == REQUEST


@pytest.mark.asyncio
async def test_successo_eseguito_due_porte(tmp_path, cronaca):
    """Sul successo ogni porta aggiunge i suoi campi, e tutte e due dicono
    `eseguito`: fino al 07/10/2026 l'officina diceva `applicata`."""
    servizi = await _servizi(cronaca)
    configurazione = await _configurazione(tmp_path, cronaca)
    for esito in (servizi, configurazione):
        assert esito["eseguito"] is True
        assert "errore" not in esito and "causa" not in esito
    assert "applicata" not in configurazione
