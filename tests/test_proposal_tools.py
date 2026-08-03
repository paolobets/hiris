import pytest
from unittest.mock import AsyncMock, MagicMock
from hiris.app.proxy.proposal_store import ProposalStore
from hiris.app.tools.proposal_tools import create_automation_proposal


@pytest.fixture
def store(tmp_path):
    s = ProposalStore(
        db_path=str(tmp_path / "proposals.db"),
        scheduler=None,
    )
    yield s
    s.close()


def _sample_args(**overrides):
    base = {
        "proposal_type": "ha_automation",
        "name": "Luci off mezzanotte",
        "description": "Spegne le luci del soggiorno a mezzanotte",
        "config": {"alias": "Luci off", "trigger": [], "action": []},
        "routing_reason": "Trigger orario semplice — Layer 1 è sufficiente",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_create_proposal_injects_automation_id_into_config(store):
    """MODIFY: automation_id is carried INTO the persisted config as 'id', so
    apply overwrites that automation instead of duplicating it."""
    res = await create_automation_proposal(store, **_sample_args(automation_id="1699999999"))
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "1699999999"


@pytest.mark.asyncio
async def test_create_proposal_without_automation_id_leaves_config(store):
    """NEW: no automation_id → no 'id' injected → apply mints a fresh one."""
    res = await create_automation_proposal(store, **_sample_args())
    saved = await store.get(res["proposal_id"])
    assert "id" not in saved["config"]


@pytest.mark.asyncio
async def test_create_proposal_keeps_config_id_as_modify(store):
    """MODIFY (bug #2 fix): l'LLM legge un'automazione con get_automation_config
    e ne riporta il config INCLUSO l'id, ma spesso NON compila il param separato
    automation_id. Prima l'id veniva strippato -> l'apply coniava un id nuovo ->
    DUPLICATO invece di overwrite. Ora l'id presente nel config viene PRESERVATO
    (= modifica). Per una NUOVA automazione l'LLM omette l'id."""
    args = _sample_args(config={"id": "1699999999", "alias": "Modifica", "trigger": [], "action": []})
    res = await create_automation_proposal(store, **args)
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "1699999999"


@pytest.mark.asyncio
async def test_create_proposal_explicit_automation_id_beats_config_id(store):
    """L'automation_id esplicito vince sull'id copiato nel config."""
    args = _sample_args(config={"id": "111", "alias": "x", "trigger": [], "action": []},
                        automation_id="999")
    res = await create_automation_proposal(store, **args)
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "999"


@pytest.mark.asyncio
async def test_create_proposal_normalizes_automation_type_alias(store):
    """BUG #2 root cause: il Chatbot ha usato type='automation' (alias) invece di
    'ha_automation' -> l'apply cadeva nel ramo status-only che non scrive in HA.
    Ora l'alias e' normalizzato a 'ha_automation'."""
    res = await create_automation_proposal(store, **_sample_args(proposal_type="automation"))
    saved = await store.get(res["proposal_id"])
    assert saved["type"] == "ha_automation"


@pytest.mark.asyncio
async def test_create_proposal_rejects_unknown_type(store):
    """Un tipo davvero sconosciuto non viene salvato in silenzio (che poi
    sparirebbe nel ramo status-only): errore chiaro, niente save."""
    res = await create_automation_proposal(store, **_sample_args(proposal_type="banana"))
    assert "error" in res
    assert "proposal_id" not in res


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_type", ["ha_dashboard", "ha_script", "ha_scene"])
async def test_create_proposal_rejects_config_types(store, bad_type):
    """Scorciatoia chiusa: questi tipi qui salterebbero la validazione
    fail-closed di propose_dashboard / create_ha_config (url_path, viste,
    dimensione, titolo). Le plance si propongono solo con propose_dashboard."""
    res = await create_automation_proposal(store, **_sample_args(proposal_type=bad_type))
    assert "error" in res
    assert "proposal_id" not in res
    assert "propose_dashboard" in res["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("alias,expected", [("automation", "ha_automation"),
                                            ("agent", "hiris_agent")])
async def test_create_proposal_aliases_still_accepted(store, alias, expected):
    """La restrizione dei tipi non deve rompere gli alias gia' gestiti."""
    res = await create_automation_proposal(store, **_sample_args(proposal_type=alias))
    saved = await store.get(res["proposal_id"])
    assert saved["type"] == expected


@pytest.mark.asyncio
async def test_create_proposal_hiris_agent_config_untouched(store):
    """A hiris_agent proposal must not have its config['id'] touched (the id
    logic is scoped to ha_automation only)."""
    args = _sample_args(proposal_type="hiris_agent",
                        config={"id": "keep-me", "role": "x"}, automation_id="999")
    res = await create_automation_proposal(store, **args)
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "keep-me"


@pytest.mark.asyncio
async def test_create_proposal_returns_pending(store):
    result = await create_automation_proposal(store, **_sample_args())
    assert "proposal_id" in result
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_create_proposal_saved_in_store(store):
    args = _sample_args(name="Test automation")
    result = await create_automation_proposal(store, **args)
    saved = await store.get(result["proposal_id"])
    assert saved is not None
    assert saved["name"] == "Test automation"


@pytest.mark.asyncio
async def test_create_proposal_no_store_returns_error():
    result = await create_automation_proposal(None, **_sample_args())
    assert "error" in result


@pytest.mark.asyncio
async def test_create_proposal_rejects_non_automation_shape(store):
    """Bug live-verify #3, lato creazione: prima di questa fix il controllo di
    forma (is_automation_config) viveva solo nell'apply (ha_client.py) -- il
    percorso della chat (questo tool) salvava senza verificare nulla, e
    falliva solo dopo, all'apply, con un 502 all'utente al posto di un errore
    al modello che ha scritto la proposta. Gli altri due percorsi autonomi
    (Sentinella, coverage-review) erano gia' coperti."""
    args = _sample_args(config={"alias": "Solo un nome, niente trigger ne' azioni"})
    res = await create_automation_proposal(store, **args)
    assert "error" in res
    assert "proposal_id" not in res


@pytest.mark.asyncio
async def test_create_proposal_accepts_entity_id_as_modify_target(store):
    """L'entity_id e' una forma di id accettata quanto quella numerica: la
    risoluzione vera (che richiede get_automations, quindi HA) resta a
    create_automation all'apply (Correzione 1) -- qui si valida solo la forma,
    senza duplicare quella logica."""
    args = _sample_args(config={
        "id": "automation.avviso_luci_accese_all_uscita_di_casa",
        "alias": "Avviso: luci accese all'uscita di casa",
        "trigger": [], "action": [],
    })
    res = await create_automation_proposal(store, **args)
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "automation.avviso_luci_accese_all_uscita_di_casa"


@pytest.mark.asyncio
async def test_create_proposal_rejects_unresolvable_id_shape(store):
    """Un id che non e' ne' numerico ne' un entity_id non arriva nemmeno a
    essere salvato: fallirebbe comunque all'apply, meglio dirlo subito al
    modello con un errore azionabile invece di lasciare che la proposta
    resti pending e fallisca solo quando l'utente prova ad attivarla."""
    args = _sample_args(config={
        "id": "non e' ne' un numero ne' un entity_id",
        "alias": "X", "trigger": [], "action": [],
    })
    res = await create_automation_proposal(store, **args)
    assert "error" in res
    assert "proposal_id" not in res


@pytest.mark.asyncio
async def test_create_proposal_accepts_bare_object_id_as_modify_target(store):
    """C-2 (TDD, rosso prima di questa fix): create_automation (l'apply)
    accetta da sempre l'object_id nudo (senza prefisso 'automation.') come
    terza forma valida per identificare un'automazione esistente -- lo stesso
    contratto di get_automation_config. Prima di is_automation_id_candidate
    questo gate ne riconosceva solo due (numerico, entity_id) e avrebbe
    rifiutato qui una proposta che l'apply avrebbe applicato senza problemi."""
    args = _sample_args(config={
        "id": "avviso_luci_accese_all_uscita_di_casa",  # object_id nudo
        "alias": "Avviso: luci accese all'uscita di casa",
        "trigger": [], "action": [],
    })
    res = await create_automation_proposal(store, **args)
    assert "error" not in res, res
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "avviso_luci_accese_all_uscita_di_casa"


@pytest.mark.asyncio
async def test_create_proposal_falsy_id_is_stripped_not_persisted(store):
    """M-1 (TDD, rosso prima di questa fix): un id FALSY (es. 0) saltava la
    validazione (`if _id:` e' False) e veniva persistito cosi' com'e' nel
    config -- la proposta salvata mostrava un id che pero' all'apply si
    comporta come assente (create_automation: `automation_id or
    config.get('id') or ''`, e 0 e' falsy). La chiave deve sparire, non
    restare a mentire nella proposta salvata."""
    args = _sample_args(config={"id": 0, "alias": "X", "trigger": [], "action": []})
    res = await create_automation_proposal(store, **args)
    assert "error" not in res, res
    saved = await store.get(res["proposal_id"])
    assert "id" not in saved["config"]


@pytest.mark.asyncio
async def test_create_proposal_id_error_message_is_actionable(store):
    """L'errore parla al modello: deve dirgli l'id che ha scritto, che serve
    quello numerico, e che per una automazione nuova va omesso."""
    args = _sample_args(config={"id": "abc-non-valido", "alias": "X",
                                "trigger": [], "action": []})
    res = await create_automation_proposal(store, **args)
    assert "abc-non-valido" in res["error"]
    assert "get_automation_config" in res["error"]
    assert "entity_id" in res["error"]


@pytest.mark.asyncio
async def test_create_proposal_exception_returns_error():
    """No-leak policy (mirrors dispatcher.py's catch-all): the raw exception
    text must never reach the caller, only a generic-but-useful message."""
    mock_store = MagicMock()
    mock_store.save = AsyncMock(side_effect=Exception("db error"))
    result = await create_automation_proposal(mock_store, **_sample_args())
    assert "error" in result
    assert "db error" not in result["error"]
