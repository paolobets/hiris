import pytest
from hiris.app.watcher.signals import Decision, WakeEvent
from hiris.app.watcher.executor import execute

def _wake():
    return WakeEvent("power", "switch.stufa", "warn", {"watt": 3500}, 1.0)

class _Rec:
    def __init__(self): self.notified=[]; self.acted=[]; self.proposed=[]
    async def notify(self, message, *, title): self.notified.append((title, message))
    async def act(self, action): self.acted.append(action)
    async def propose(self, decision, wake): self.proposed.append(decision)

@pytest.mark.asyncio
async def test_green_with_optin_acts_and_notifies():
    r = _Rec()
    d = Decision("anomalia","warn","Spengo la stufa",{"domain":"switch","service":"turn_off","entity_id":"switch.stufa","data":{}})
    out = await execute(d, _wake(), tiers={"switch":"green"}, entity_tiers={},
                        notify=r.notify, act=r.act, propose=r.propose, allow_green_auto=True)
    assert out == "act" and r.acted and r.notified

@pytest.mark.asyncio
async def test_green_without_optin_proposes():
    r = _Rec()
    d = Decision("anomalia","warn","Spengo",{"domain":"switch","service":"turn_off","entity_id":"switch.stufa","data":{}})
    out = await execute(d, _wake(), tiers={"switch":"green"}, entity_tiers={},
                        notify=r.notify, act=r.act, propose=r.propose, allow_green_auto=False)
    assert out == "propose" and r.proposed and not r.acted

@pytest.mark.asyncio
async def test_red_only_alerts():
    r = _Rec()
    d = Decision("anomalia","critico","Apri il garage",{"domain":"cover","service":"open_cover","entity_id":"cover.garage","data":{}})
    out = await execute(d, _wake(), tiers={"cover":"red"}, entity_tiers={},
                        notify=r.notify, act=r.act, propose=r.propose, allow_green_auto=True)
    assert out == "alert" and r.notified and not r.acted and not r.proposed

@pytest.mark.asyncio
async def test_injection_via_entity_never_acts_off_domain():
    # il modello propone un'azione su un dominio 'off' (non configurato): mai eseguita
    r = _Rec()
    d = Decision("anomalia","critico","disattivo allarme",{"domain":"alarm_control_panel","service":"alarm_disarm","entity_id":"alarm_control_panel.casa","data":{}})
    out = await execute(d, _wake(), tiers={}, entity_tiers={},   # dominio non in tiers → 'off'
                        notify=r.notify, act=r.act, propose=r.propose, allow_green_auto=True)
    assert out == "alert" and not r.acted and not r.proposed

@pytest.mark.asyncio
async def test_dangerous_domain_never_acts_or_proposes():
    r = _Rec()
    d = Decision("anomalia","critico","Apro il garage",
                 {"domain":"cover","service":"open_cover","entity_id":"cover.garage","data":{}})
    out = await execute(d, _wake(), tiers={"cover":"green"}, entity_tiers={},
                        notify=r.notify, act=r.act, propose=r.propose, allow_green_auto=True)
    assert out == "alert" and not r.acted and not r.proposed

@pytest.mark.asyncio
async def test_no_action_just_notifies():
    r = _Rec()
    d = Decision("anomalia","info","Batteria all'8%", None)
    out = await execute(d, _wake(), tiers={}, entity_tiers={},
                        notify=r.notify, act=r.act, propose=r.propose, allow_green_auto=True)
    assert out == "notify" and r.notified
