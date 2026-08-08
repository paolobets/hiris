import pytest
from hiris.app.watcher.signals import Decision, WakeEvent
from hiris.app.watcher.executor import execute

def _wake():
    return WakeEvent("power", "switch.stufa", "warn", {"watt": 3500}, 1.0)

class _Rec:
    def __init__(self): self.notified=[]; self.proposed=[]
    async def notify(self, message, *, title): self.notified.append((title, message))
    async def propose(self, decision, wake): self.proposed.append(decision)

@pytest.mark.asyncio
async def test_green_proposes():
    # La 2.0 conosce e non agisce (fetta E2, Task 6): il tier "green" non ha
    # piu' un ramo di attuazione automatica -- propone sempre, come "yellow".
    r = _Rec()
    d = Decision("anomalia","warn","Spengo la stufa",{"domain":"switch","service":"turn_off","entity_id":"switch.stufa","data":{}})
    out = await execute(d, _wake(), tiers={"switch":"green"}, entity_tiers={},
                        notify=r.notify, propose=r.propose)
    assert out == "propose" and r.proposed

@pytest.mark.asyncio
async def test_red_only_alerts():
    r = _Rec()
    d = Decision("anomalia","critico","Apri il garage",{"domain":"cover","service":"open_cover","entity_id":"cover.garage","data":{}})
    out = await execute(d, _wake(), tiers={"cover":"red"}, entity_tiers={},
                        notify=r.notify, propose=r.propose)
    assert out == "alert" and r.notified and not r.proposed

@pytest.mark.asyncio
async def test_injection_via_entity_never_acts_off_domain():
    # il modello propone un'azione su un dominio 'off' (non configurato): mai eseguita
    r = _Rec()
    d = Decision("anomalia","critico","disattivo allarme",{"domain":"alarm_control_panel","service":"alarm_disarm","entity_id":"alarm_control_panel.casa","data":{}})
    out = await execute(d, _wake(), tiers={}, entity_tiers={},   # dominio non in tiers → 'off'
                        notify=r.notify, propose=r.propose)
    assert out == "alert" and not r.proposed

@pytest.mark.asyncio
async def test_dangerous_domain_never_proposes():
    r = _Rec()
    d = Decision("anomalia","critico","Apro il garage",
                 {"domain":"cover","service":"open_cover","entity_id":"cover.garage","data":{}})
    out = await execute(d, _wake(), tiers={"cover":"green"}, entity_tiers={},
                        notify=r.notify, propose=r.propose)
    assert out == "alert" and not r.proposed

@pytest.mark.asyncio
async def test_no_action_just_notifies():
    r = _Rec()
    d = Decision("anomalia","info","Batteria all'8%", None)
    out = await execute(d, _wake(), tiers={}, entity_tiers={},
                        notify=r.notify, propose=r.propose)
    assert out == "notify" and r.notified

@pytest.mark.asyncio
async def test_dangerous_entity_with_spoofed_domain_never_proposes():
    r = _Rec()
    # spoofed non-dangerous domain but the ENTITY is a lock; tier light=green
    d = Decision("anomalia","critico","apri",
                 {"domain":"light","service":"turn_on","entity_id":"lock.porta","data":{}})
    out = await execute(d, _wake(), tiers={"light":"green"}, entity_tiers={},
                        notify=r.notify, propose=r.propose)
    assert out == "alert" and not r.proposed

@pytest.mark.asyncio
async def test_falso_positivo_verdict_skips_execution():
    """fetta E3 Task 5 (raccoglie la riserva della review E3 blocco 1, I-1):
    spostato da tests/test_reasoning_wiring.py::
    test_missing_verdict_decision_does_not_execute_action, dove il verdetto
    "falso_positivo" veniva costruito passando da uno specchio locale
    (`_resolve_verdict`) di una risoluzione che un tempo viveva in
    `_execute_decision` (server.py, cancellata dal Task 4). Il fail-closed
    VERO vive qui, dentro execute() stessa (vedi executor.py: `if
    decision.verdict == "falso_positivo": return "skip"`), quindi il test si
    sposta al suo vero soggetto invece di continuare a passare per uno
    specchio morto. Un verdetto "falso_positivo" deve saltare l'esecuzione
    per intero -- nessuna notifica, nessuna proposta -- anche quando
    l'azione porta un'entita' concreta su un tier "green" che altrimenti
    proporrebbe sempre (vedi test_green_proposes sopra)."""
    r = _Rec()
    d = Decision("falso_positivo", "info", "runner sent garbage",
                 {"domain": "light", "service": "turn_on", "entity_id": "light.x", "data": {}})
    out = await execute(d, _wake(), tiers={"light": "green"}, entity_tiers={},
                        notify=r.notify, propose=r.propose)
    assert out == "skip"
    assert not r.proposed and not r.notified
