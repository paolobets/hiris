"""Consolidamento 1.2 — una proposta deve contenere cio' che il suo tipo dichiara.

Due percorsi autonomi (Sentinella e coverage-review del Brain) creavano proposte
di tipo `ha_automation` con dentro tutt'altro: un'azione suggerita, o il
suggerimento grezzo del modello. All'approvazione `create_automation` accettava
qualunque dizionario non vuoto e scriveva in Home Assistant un'automazione senza
trigger ne' azione. Stesso schema del bug di luglio: sembra applicata, non fa
nulla.

La difesa e' su entrambi i lati:
  - chi applica: `create_automation` rifiuta cio' che non ha la forma minima di
    un'automazione HA;
  - chi propone: la Sentinella propone uno script (che e' cio' che ha davvero in
    mano) e la coverage-review propone un'automazione solo quando il
    suggerimento porta davvero una config di automazione.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from hiris.app.proxy.ha_client import HAClient, is_automation_config


# ---------------------------------------------------------------------------
# Chi applica — forma minima di un'automazione Home Assistant
# ---------------------------------------------------------------------------

def _post_mock(status=200):
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value="OK")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _client_with_post_spy():
    client = HAClient(base_url="http://supervisor/core", token="t")
    client.call_service = AsyncMock(return_value=True)   # niente reload reale
    client.get_automations = AsyncMock(return_value=[])  # niente match per alias
    post = MagicMock(return_value=_post_mock(200))
    client._session = MagicMock()
    client._session.post = post
    return client, post


NON_AUTOMATION_CONFIGS = [
    {"suggested_action": {"domain": "switch", "service": "turn_off",
                          "entity_id": "switch.stufa", "data": {}}},   # Sentinella
    {"detector": "power", "entity": "sensor.presa", "max_watt": 2000},  # coverage-review
    {"alias": "Solo un nome"},                                          # niente trigger/azioni
    {"alias": "X", "trigger": [{"platform": "state"}]},                 # niente azioni
    {"alias": "X", "action": [{"service": "light.turn_on"}]},           # niente trigger
    {"alias": "X", "trigger": None, "action": None},                    # chiavi svuotate
    {"title": "Idea di gestione", "rationale": "perche' si'"},          # suggerimento grezzo
]


@pytest.mark.asyncio
@pytest.mark.parametrize("config", NON_AUTOMATION_CONFIGS)
async def test_create_automation_rejects_non_automation_config(config):
    client, post = _client_with_post_spy()
    res = await client.create_automation(config)
    assert "error" in res, res
    post.assert_not_called()   # niente scrittura in HA, nemmeno tentata


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [None, {}, [], "trigger"])
async def test_create_automation_still_rejects_empty_or_non_dict(config):
    client, post = _client_with_post_spy()
    res = await client.create_automation(config)
    assert "error" in res
    post.assert_not_called()


ACCEPTED_CONFIGS = [
    # forma storica (singolare) — l'unica esistente fino a HA 2024.10
    {"alias": "X", "trigger": [], "action": []},
    # forma canonica attuale (plurale), retro-compatibile con la precedente
    {"alias": "X", "triggers": [{"trigger": "state", "entity_id": "light.x"}],
     "actions": [{"service": "light.turn_off", "target": {"entity_id": "light.x"}}]},
    # un solo trigger/azione scritti come mapping invece che come lista
    {"alias": "X", "trigger": {"platform": "state", "entity_id": "light.x"},
     "action": {"service": "light.turn_off"}},
    # forme miste (HA accetta le chiavi indipendentemente l'una dall'altra)
    {"alias": "X", "triggers": [], "action": []},
    # automazione da blueprint: non ha trigger ne' azioni proprie
    {"alias": "X", "use_blueprint": {"path": "motion.yaml", "input": {"a": "b"}}},
]


@pytest.mark.asyncio
@pytest.mark.parametrize("config", ACCEPTED_CONFIGS)
async def test_create_automation_accepts_every_legitimate_form(config):
    client, post = _client_with_post_spy()
    res = await client.create_automation(config)
    assert res.get("ok") is True, res
    post.assert_called_once()


def test_is_automation_config_predicate():
    assert is_automation_config({"trigger": [], "action": []}) is True
    assert is_automation_config({"triggers": [], "actions": []}) is True
    assert is_automation_config({"use_blueprint": {"path": "x.yaml"}}) is True
    assert is_automation_config({"suggested_action": {}}) is False
    assert is_automation_config({"use_blueprint": "x.yaml"}) is False
    assert is_automation_config({}) is False
    assert is_automation_config(None) is False


# ---------------------------------------------------------------------------
# Chi propone (1) — la Sentinella propone uno script, non un'automazione
# ---------------------------------------------------------------------------

from hiris.app.tools.config_tools import apply_ha_config              # noqa: E402
from hiris.app.watcher.sentinel_proposal import (                     # noqa: E402
    build_sentinel_script_proposal,
    propose_sentinel_script,
)

_ACTION = {"domain": "switch", "service": "turn_off",
           "entity_id": "switch.stufa", "data": {}}


_DEFAULT = object()


def _record(action=_DEFAULT, **kw):
    kw.setdefault("signal_kind", "power")
    kw.setdefault("entity_id", "switch.stufa")
    kw.setdefault("message", "Consumo anomalo: propongo di spegnere la stufa")
    kw.setdefault("routing_reason", "Proposta dalla Sentinella (autonomia graduata)")
    return build_sentinel_script_proposal(
        _ACTION if action is _DEFAULT else action, **kw)


def test_sentinel_proposal_declares_a_script_and_contains_a_script():
    rec = _record()
    assert rec is not None
    assert rec["type"] == "ha_script"
    assert rec["config"]["kind"] == "script"
    assert rec["config"]["slug"] == "hiris_sentinella_power_stufa"
    seq = rec["config"]["ha_config"]["sequence"]
    assert seq == [{"service": "switch.turn_off",
                    "target": {"entity_id": "switch.stufa"},
                    "data": {}}]


_NOTA_APPROVAZIONE = ("Approvando crei in Home Assistant uno script pronto all'uso: "
                      "il rimedio non viene eseguito ora, lo esegui tu quando vuoi.")


def test_sentinel_proposal_description_says_what_approving_produces():
    """Il pannello Proposte mostra nome, descrizione, tipo e un bottone "Attiva",
    senza anteprima del contenuto: se la descrizione promette il rimedio, l'utente
    preme "Attiva" e ottiene uno script creato, non la stufa spenta. La descrizione
    deve dire cosa si ottiene approvando, conservando cio' che e' stato rilevato."""
    rec = _record()
    assert rec["description"] == (
        "Consumo anomalo: propongo di spegnere la stufa. " + _NOTA_APPROVAZIONE)


def test_sentinel_proposal_never_claims_an_mcp_origin():
    """Con un messaggio vuoto la descrizione non deve ricadere sul default di
    build_config_proposal, che dichiara un'origine ("via MCP") che non e' la sua."""
    rec = _record(message="")
    assert "MCP" not in rec["description"]
    assert rec["description"] == (
        "Sentinella: power su switch.stufa. " + _NOTA_APPROVAZIONE)


def test_sentinel_proposal_reuses_the_shared_identifier_rules():
    """Le regole di forma di dominio/servizio/entity_id sono quelle di HAClient,
    non una quarta copia scritta a mano qui."""
    import hiris.app.proxy.ha_client as ha_client_mod
    import hiris.app.watcher.sentinel_proposal as sp_mod

    assert sp_mod._IDENTIFIER_RE is ha_client_mod._IDENTIFIER_RE
    assert sp_mod._ENTITY_ID_RE is ha_client_mod._ENTITY_ID_RE


def test_sentinel_proposal_is_not_an_automation_config():
    """Il vecchio contenuto ({"suggested_action": ...}) sarebbe stato scritto in
    HA come automazione senza trigger ne' azione: il nuovo non finisce mai la'."""
    rec = _record()
    assert rec["type"] != "ha_automation"
    assert is_automation_config(rec["config"]) is False


def test_sentinel_proposal_carries_the_delayed_turn_off():
    """Stessa fedelta' del percorso automatico: `off_after_min` diventa un
    ritardo + spegnimento nella sequenza, non si perde per strada."""
    rec = _record({"domain": "switch", "service": "turn_on",
                   "entity_id": "switch.pompa", "data": {}, "off_after_min": 15})
    seq = rec["config"]["ha_config"]["sequence"]
    assert seq[0]["service"] == "switch.turn_on"
    assert seq[1] == {"delay": {"minutes": 15}}
    assert seq[2] == {"service": "switch.turn_off",
                      "target": {"entity_id": "switch.pompa"}}


@pytest.mark.parametrize("action", [
    None,
    {},
    {"entity_id": "switch.stufa"},                       # servizio mancante
    {"entity_id": "switch.stufa", "service": "turn off"},  # servizio non valido
    {"service": "turn_off"},                             # entita' mancante
    {"entity_id": "stufa", "service": "turn_off"},       # entity_id senza dominio
    {"entity_id": "switch.stufa", "service": "turn_off", "data": "non un dict"},
])
def test_sentinel_proposal_none_when_action_is_not_packageable(action):
    assert _record(action) is None


@pytest.mark.asyncio
async def test_sentinel_proposal_actually_creates_the_script_on_apply():
    """Il ramo di apply del tipo scelto fa qualcosa di reale: niente
    "applicata" a vuoto."""
    rec = _record()
    ha = MagicMock()
    ha.create_script = AsyncMock(return_value={"ok": True, "id": "hiris_sentinella_power_stufa"})
    res = await apply_ha_config(ha, rec["config"])
    assert res == {"ok": True, "id": "hiris_sentinella_power_stufa"}
    ha.create_script.assert_awaited_once_with(
        "hiris_sentinella_power_stufa", rec["config"]["ha_config"])


# ---------------------------------------------------------------------------
# Chi propone (1b) — l'esito registrato dice cio' che e' davvero accaduto
# ---------------------------------------------------------------------------

from hiris.app.watcher.executor import execute                        # noqa: E402
from hiris.app.watcher.signals import Decision, WakeEvent             # noqa: E402


def _decision(action=_ACTION):
    return Decision("anomalia", "warn", "Consumo anomalo: propongo di spegnere la stufa",
                    action)


def _wake():
    return WakeEvent("power", "switch.stufa", "warn", {"watt": 3500}, 1.0)


class _Notifier:
    def __init__(self):
        self.notified = []

    async def notify(self, message, *, title):
        self.notified.append((title, message))


async def _propose(decision, *, save, notifier):
    return await propose_sentinel_script(
        decision, _wake(), save=save, notify=notifier.notify,
        notify_title="HIRIS Sentinella",
        routing_reason="Proposta dalla Sentinella (autonomia graduata)")


@pytest.mark.asyncio
async def test_propose_saves_and_reports_propose():
    saved = []

    async def _save(record):
        saved.append(record)

    n = _Notifier()
    outcome = await _propose(_decision(), save=_save, notifier=n)
    assert outcome == "propose"
    assert len(saved) == 1 and saved[0]["type"] == "ha_script"
    assert n.notified == []


@pytest.mark.asyncio
async def test_propose_falls_back_to_the_notification_when_saving_fails():
    """Se il salvataggio solleva non resta nulla: ne' proposta ne' avviso. Ma la
    Sentinella aveva rilevato qualcosa che valeva la pena dire — stesso
    trattamento del ramo "azione non confezionabile"."""
    async def _save(record):
        raise RuntimeError("disco pieno")

    n = _Notifier()
    outcome = await _propose(_decision(), save=_save, notifier=n)
    assert n.notified == [("HIRIS Sentinella",
                           "Consumo anomalo: propongo di spegnere la stufa")]
    assert outcome != "propose", "nessuna proposta esiste: la timeline non deve dire 'propose'"
    assert outcome == "alert"


@pytest.mark.asyncio
async def test_propose_reports_alert_when_the_action_is_not_packageable():
    saved = []

    async def _save(record):
        saved.append(record)

    n = _Notifier()
    outcome = await _propose(_decision({"entity_id": "switch.stufa"}),
                             save=_save, notifier=n)
    assert saved == [] and len(n.notified) == 1
    assert outcome == "alert"


@pytest.mark.asyncio
async def test_executor_records_the_outcome_the_propose_adapter_reports():
    """execute() registrava "propose" comunque: l'esito vero lo conosce solo chi
    ha provato a proporre."""
    n = _Notifier()

    async def _act(action):
        raise AssertionError("giallo: non deve agire")

    async def _propose_alert(decision, wake):
        return "alert"

    out = await execute(_decision(), _wake(), tiers={"switch": "yellow"},
                        entity_tiers={}, notify=n.notify, act=_act,
                        propose=_propose_alert, allow_green_auto=False)
    assert out == "alert"

    async def _propose_legacy(decision, wake):
        return None

    out = await execute(_decision(), _wake(), tiers={"switch": "yellow"},
                        entity_tiers={}, notify=n.notify, act=_act,
                        propose=_propose_legacy, allow_green_auto=False)
    assert out == "propose"


# ---------------------------------------------------------------------------
# Chi propone (2) — la coverage-review propone solo cio' che e' applicabile
# ---------------------------------------------------------------------------

from hiris.app.brain.suggestions import SuggestionStore, apply_suggestions  # noqa: E402

_AUTOMATION = {"alias": "Spegni la stufa di notte",
               "trigger": [{"platform": "time", "at": "23:00:00"}],
               "action": [{"service": "switch.turn_off",
                           "target": {"entity_id": "switch.stufa"}}]}


def _run_management(config, tmp_path):
    store = SuggestionStore(str(tmp_path / "suggestions.db"))
    proposed = []
    try:
        apply_suggestions(
            [{"kind": "management", "title": "T", "rationale": "R", "config": config}],
            data_dir=str(tmp_path), store=store, inventory_ids=set(),
            current_config={}, create_proposal=lambda c, _sid: proposed.append(c), cap=5)
        rows = store.list()
    finally:
        store.close()
    return proposed, rows


def test_management_suggestion_with_real_automation_is_proposed(tmp_path):
    proposed, rows = _run_management(_AUTOMATION, tmp_path)
    assert proposed == [_AUTOMATION]
    assert len(rows) == 1 and rows[0]["status"] == "proposed"


def test_management_suggestion_without_automation_creates_no_proposal(tmp_path):
    """Il suggerimento grezzo non e' un'automazione: niente proposta che
    prometta un'applicazione impossibile. Resta comunque registrato e visibile
    fra i "Suggerimenti del Brain"."""
    raw = {"idea": "raggruppa le luci del piano terra", "entita": ["light.a"]}
    proposed, rows = _run_management(raw, tmp_path)
    assert proposed == []
    assert len(rows) == 1 and rows[0]["config"] == raw


def test_management_suggestion_without_automation_is_not_marked_proposed(tmp_path):
    """Due esiti opposti non possono portare la stessa etichetta: la sezione
    "Suggerimenti del Brain" mostra lo stato cosi' com'e', quindi "proposed" su
    una riga che non ha generato nessuna proposta manda l'utente a cercare nella
    pagina Proposte una cosa che non c'e'."""
    raw = {"idea": "raggruppa le luci del piano terra"}
    _, rows = _run_management(raw, tmp_path)
    assert rows[0]["status"] != "proposed"
    assert rows[0]["status"] == "recorded"


def test_management_suggestion_without_automation_is_logged(tmp_path, caplog):
    """Lo scarto non puo' essere muto: nei log deve restare traccia del perche'
    un suggerimento non e' diventato una proposta, come gia' fa la Sentinella."""
    import logging
    with caplog.at_level(logging.WARNING, logger="hiris.app.brain.suggestions"):
        _run_management({"idea": "niente trigger"}, tmp_path)
    assert any("management" in r.getMessage().lower() or "gestione" in r.getMessage().lower()
               for r in caplog.records), caplog.text


def test_coverage_review_prompt_declares_the_management_contract():
    """Il modello deve sapere che per 'management' il config e' una vera
    configurazione di automazione, altrimenti il filtro sopra scarta sempre."""
    from hiris.app.brain.coverage_review import COVERAGE_REVIEW_SYSTEM
    assert "management" in COVERAGE_REVIEW_SYSTEM
    assert "automazione" in COVERAGE_REVIEW_SYSTEM
    assert "trigger" in COVERAGE_REVIEW_SYSTEM
