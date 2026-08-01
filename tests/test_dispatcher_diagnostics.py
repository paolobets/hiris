"""Instradamento e perimetro dei due tool di diagnosi nel dispatcher.

Gemello di tests/test_dispatcher_history.py: get_logbook accetta un entity_id
dall'LLM, quindi deve rispettare le stesse restrizioni (allowed_entities,
visible_entity_ids) che il dispatcher applica a get_entity_states/get_history.
"""
import pytest

from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    def __init__(self, voci=None):
        self.voci = voci if voci is not None else [
            {"when": "2026-07-31T22:10:00+00:00", "name": "Salotto",
             "message": "acceso", "entity_id": "light.a"},
            {"when": "2026-07-31T22:11:00+00:00", "name": "Ingresso",
             "message": "sbloccata", "entity_id": "lock.front"},
        ]
        self.chiamate_logbook = []
        self.chiamate_template = []

    async def get_logbook(self, entity_id, hours):
        self.chiamate_logbook.append((entity_id, hours))
        if entity_id is None:
            return list(self.voci)
        return [v for v in self.voci if v["entity_id"] == entity_id]

    async def render_template(self, template):
        self.chiamate_template.append(template)
        return {"result": "on"}


@pytest.mark.asyncio
async def test_dispatch_get_logbook_restituisce_le_voci():
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_logbook", {"hours": 6})
    assert ha.chiamate_logbook == [(None, 6)]
    assert out["count"] == 2


@pytest.mark.asyncio
async def test_dispatch_get_logbook_agente_senza_perimetro_vede_tutto():
    # allowed_entities=None (chiamante non ristretto) -> nessun filtro.
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_logbook", {}, allowed_entities=None)
    assert [v["entity_id"] for v in out["entries"]] == ["light.a", "lock.front"]


@pytest.mark.asyncio
async def test_dispatch_get_logbook_filtra_per_allowed_entities():
    # Stesso vincolo di get_history: un agente ristretto a light.* non deve
    # poter leggere la cronologia di serrature/allarme/presenze. Qui l'entita'
    # e' FACOLTATIVA, quindi il filtro deve valere anche sulle voci restituite
    # dalla richiesta senza entita', altrimenti basterebbe ometterla.
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_logbook", {}, allowed_entities=["light.*"])
    ids = [v["entity_id"] for v in out["entries"]]
    assert ids == ["light.a"]
    assert "lock.front" not in ids


@pytest.mark.asyncio
async def test_dispatch_get_logbook_rifiuta_entita_fuori_perimetro():
    # Scartare l'entita' come fa get_history con la sua lista significherebbe
    # qui chiedere il logbook dell'INTERA casa: si allargherebbe il perimetro
    # invece di stringerlo. Quindi si rifiuta, senza toccare HA.
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_logbook", {"entity_id": "lock.front"},
                           allowed_entities=["light.*"])
    assert "error" in out
    assert ha.chiamate_logbook == []


@pytest.mark.asyncio
async def test_dispatch_get_logbook_rifiuta_entita_fuori_dal_contesto_visibile():
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_logbook", {"entity_id": "lock.front"},
                           visible_entity_ids=frozenset({"light.a"}))
    assert "error" in out
    assert ha.chiamate_logbook == []


@pytest.mark.asyncio
async def test_visible_entity_ids_non_filtra_le_voci_e_non_e_un_contenimento():
    # Asimmetria deliberata rispetto ad allowed_entities: visible_entity_ids
    # ferma l'entita' esplicita ma NON filtra le voci restituite, quindi si
    # aggira omettendo il parametro. E' voluto — e' un insieme semantico di
    # rilevanza (SemanticContextMap), non una whitelist di sicurezza: filtrarci
    # le voci svuoterebbe la domanda "cosa e' successo ieri sera?". Questo test
    # pinna il comportamento perche' nessuno lo scambi per una falla.
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_logbook", {},
                           visible_entity_ids=frozenset({"light.a"}))
    assert [v["entity_id"] for v in out["entries"]] == ["light.a", "lock.front"]
    assert "filtered" not in out


@pytest.mark.asyncio
async def test_dispatch_get_logbook_entita_visibile_passa():
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_logbook", {"entity_id": "light.a"},
                           visible_entity_ids=frozenset({"light.a"}))
    assert ha.chiamate_logbook == [("light.a", 24)]
    assert out["count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("inputs", [{}, {"hours": None}])
async def test_dispatch_get_logbook_ore_assenti_valgono_il_default(inputs):
    # Un modello che emette esplicitamente `null` per un parametro facoltativo
    # sta dicendo "non l'ho specificato", non "finestra non valida". La
    # normalizzazione vive nel tool (diagnostics_tools), non qui: questo test
    # verifica che passando per il dispatcher il contratto valga comunque.
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    await d.dispatch("get_logbook", dict(inputs))
    assert ha.chiamate_logbook == [(None, 24)]


@pytest.mark.asyncio
async def test_dispatch_get_logbook_ore_zero_resta_un_errore():
    # `0` e' un input sbagliato e va respinto: tradurlo nel default
    # nasconderebbe l'errore al modello.
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_logbook", {"hours": 0})
    assert "error" in out
    assert ha.chiamate_logbook == []


@pytest.mark.asyncio
async def test_dispatch_get_logbook_ore_non_valide_non_toccano_ha():
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_logbook", {"hours": 5000})
    assert "error" in out
    assert ha.chiamate_logbook == []


@pytest.mark.asyncio
async def test_dispatch_render_template_instrada_al_client():
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("render_template",
                           {"template": "{{ states('light.a') }}"})
    assert ha.chiamate_template == ["{{ states('light.a') }}"]
    assert out == {"result": "on"}


@pytest.mark.asyncio
async def test_dispatch_render_template_senza_template_non_tocca_ha():
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("render_template", {})
    assert "error" in out
    assert ha.chiamate_template == []
