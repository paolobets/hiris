"""A2/A3 — quando una dipendenza manca, il dispatcher deve dirlo.

A2: `recall_knowledge` era un ramo condizionato alla presenza dello store.
Senza store l'esecuzione cadeva nel ramo finale, che risponde «Tool 'X' non
esiste. [...] Non inventare nomi di tool.»: il modello viene rimproverato per
aver chiamato uno strumento che gli era stato elencato, e la reazione tipica
e' smettere di usarlo per il resto della conversazione. I gemelli
`recall_memory`/`save_memory` gestiscono correttamente lo stesso caso.

A3: i tre strumenti che leggono dalla cache delle entita' rispondevano con un
elenco vuoto quando la cache non c'era o non era ancora popolata -- «la casa e'
vuota» al posto di «non ho potuto guardare».
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.proxy.entity_cache import EntityCache
from hiris.app.tools.dispatcher import ToolDispatcher


def _messaggio(res) -> str:
    return res.get("error", "") if isinstance(res, dict) else str(res)


def _disp(**kwargs) -> ToolDispatcher:
    return ToolDispatcher(ha_client=MagicMock(), notify_config={}, **kwargs)


# ── A2 · lo strumento esiste, manca la sua dipendenza ────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool, inputs",
    [
        ("recall_knowledge", {"query": "caldaia"}),
    ],
)
async def test_senza_store_non_accusa_il_modello_di_essersi_inventato_il_tool(tool, inputs):
    res = await _disp(knowledge_store=None).dispatch(tool, inputs)

    testo = _messaggio(res)
    assert testo, f"{tool} deve rispondere con un errore dichiarato"
    assert "non esiste" not in testo, (
        f"{tool} e' elencato nel system prompt: dire al modello che non esiste "
        "lo convince a non usarlo piu' per tutta la conversazione"
    )
    assert "Non inventare nomi di tool" not in testo
    assert "memoria" in testo.lower(), "l'errore deve dire cosa manca davvero"


@pytest.mark.asyncio
async def test_recall_knowledge_senza_embedder_lo_dichiara(tmp_path):
    """Come `recall_memory`: lo store da solo non basta, senza embedder non c'e'
    ricerca semantica possibile."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    res = await _disp(knowledge_store=store, embedder=None).dispatch(
        "recall_knowledge", {"query": "caldaia"})

    testo = _messaggio(res)
    assert testo
    assert "non esiste" not in testo
    store.close()


@pytest.mark.asyncio
async def test_un_tool_davvero_inesistente_resta_tale():
    """Il contrario: il messaggio severo deve restare per chi si inventa
    davvero un nome di strumento."""
    res = await _disp(knowledge_store=None).dispatch("teletrasporto", {})
    assert "non esiste" in _messaggio(res)


# ── A3 · la cache delle entita': assente, non pronta, vuota ──────────────────

_TOOL_CACHE = [
    ("get_home_status", {}),
    ("get_entities_on", {}),
    ("get_entities_by_domain", {"domain": "light"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, inputs", _TOOL_CACHE)
async def test_senza_cache_non_dice_che_la_casa_e_vuota(tool, inputs):
    res = await _disp(entity_cache=None).dispatch(tool, inputs)

    assert isinstance(res, dict) and res.get("error"), (
        f"{tool} senza inventario deve dichiarare il guasto, non rispondere []"
    )
    assert res != []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, inputs", _TOOL_CACHE)
async def test_cache_non_ancora_caricata_lo_dice(tool, inputs):
    """Una cache appena costruita non e' una casa vuota: il caricamento
    iniziale puo' non essere ancora avvenuto (o essere fallito -- server.py
    logga e prosegue). Va detto, non spacciato per «non c'e' nulla»."""
    cache = EntityCache()
    assert cache.loaded is False

    res = await _disp(entity_cache=cache).dispatch(tool, inputs)

    assert isinstance(res, dict) and res.get("error")
    assert "pront" in res["error"].lower(), (
        "il messaggio deve distinguere «non ancora pronto» da «non configurato»"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, inputs", _TOOL_CACHE)
async def test_cache_caricata_e_vuota_e_un_risultato_legittimo(tool, inputs):
    """La casa senza entita' (o senza luci accese) esiste davvero: qui l'elenco
    vuoto e' la verita' e non deve diventare un errore."""

    class _HAVuoto:
        async def get_states(self, ids):
            return []

    cache = EntityCache()
    await cache.load(_HAVuoto())
    assert cache.loaded is True

    res = await _disp(entity_cache=cache).dispatch(tool, inputs)
    assert res == []


@pytest.mark.asyncio
async def test_cache_caricata_e_piena_risponde_con_le_entita():
    class _HA:
        async def get_states(self, ids):
            return [{"entity_id": "light.cucina", "state": "on",
                     "attributes": {"friendly_name": "Cucina"}}]

    cache = EntityCache()
    await cache.load(_HA())

    accese = await _disp(entity_cache=cache).dispatch("get_entities_on", {})
    assert [e["id"] for e in accese] == ["light.cucina"]
