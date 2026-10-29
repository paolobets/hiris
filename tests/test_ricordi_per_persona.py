"""Ognuno legge i suoi ricordi (Fase S, S.1, 29/10/2026).

La decisione e' del proprietario: D8 del 03/10/2026 («per l'utente che li ha
detti, e anche l'uso in chat diventa per persona») e la scelta del 29/10
(«ognuno vede i suoi», anche quando il ricordo riguarda la casa). Fino al
29/10 la chat leggeva i ricordi di tutti, in due posti: il nucleo
(`compose_briefing`) e gli strumenti (`ToolDispatcher._all_memories`). Chi non
amministrava si faceva ripetere cio' che altri avevano detto, e cio' che faceva
ricordare entrava nei turni di tutti.

La regola vive una volta, in `memory/store.py::_reader_clause`; qui si prova la
regola e ognuna delle porte che la chiedono.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.api.handlers_home_space import compose_briefing
from hiris.app.api.soffitto import consente
from hiris.app.chat_thread import ChatThread, new_subject, subject_key_for
from hiris.app.keeper.exchange import promise_subject
from hiris.app.memory.store import MEMORY_STORE_KEY, MemoryStore
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

PAOLO = new_subject("persona", ident="u-paolo", nome="Paolo")
MARTA = new_subject("persona", ident="u-marta", nome="Marta")
ANONIMO = new_subject("persona")


def _dice(store, chi, testo):
    return store.remember(testo, detto_da=chi.get("nome"), said_by=subject_key_for(chi))


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "memoria.db"))
    _dice(s, PAOLO, "Il regalo per Marta sta nell'armadio")
    _dice(s, MARTA, "La caldaia va spenta a maggio")
    _dice(s, ANONIMO, "Detto da chi non si sa")
    yield s
    s.close()


def _testi(ricordi):
    return {r["testo"] for r in ricordi}


def test_una_persona_legge_solo_i_suoi(store):
    """Mutazione ESEGUITA: `_reader_clause` che per un soggetto con id torna
    `"", ()` -- rossa, Marta legge il regalo."""
    assert _testi(store.fetch_for(MARTA)) == {"La caldaia va spenta a maggio"}
    assert store.count_for(MARTA) == 1
    assert _testi(store.fetch_for(PAOLO)) == {"Il regalo per Marta sta nell'armadio"}


def test_un_turno_senza_soggetto_li_legge_tutti(store):
    """Gli attori di sfondo: lavorano per la casa, e cio' che producono lo
    legge chi amministra."""
    assert store.count_for(None) == 3
    assert len(store.fetch_for(None)) == 3


def test_un_soggetto_senza_id_non_ne_legge_nessuno(store):
    """`persona:-` e' la chiave di nessuno: filtrarci darebbe i ricordi di ogni
    altro soggetto senza id. Mutazione ESEGUITA: senza il ramo `not
    subject.get("id")` -- rossa, l'anonimo legge «Detto da chi non si sa»."""
    assert store.fetch_for(ANONIMO) == []
    assert store.count_for(ANONIMO) == 0
    assert store.fetch_for({}) == []


def test_il_taglio_viene_dopo_il_filtro(store):
    """Il `limit` taglia i SUOI: filtrati dopo, sparirebbero sotto quelli degli
    altri."""
    for i in range(3):
        _dice(store, PAOLO, f"di Paolo {i}")
    [ultimo] = store.fetch_for(MARTA, limit=1)
    assert ultimo["testo"] == "La caldaia va spenta a maggio"


def test_una_promessa_senza_filo_non_legge_i_ricordi_di_tutti(store):
    """Per l'archivio un turno senza soggetto e' un turno di sfondo: una
    promessa senza filo ha un padrone che non si sa, e non legge niente.
    Mutazione ESEGUITA: `promise_subject` che torna `subject_from_thread(...)`
    nudo -- rossa, `None` legge tutti e tre."""
    assert store.fetch_for(promise_subject({"thread": None})) == []
    marta_sees = promise_subject({"thread": ChatThread("persona:u-marta", "pannello")})
    assert _testi(store.fetch_for(marta_sees)) == {"La caldaia va spenta a maggio"}


@pytest.mark.asyncio
async def test_il_nucleo_porta_i_ricordi_di_chi_legge(tmp_path):
    """Mutazione ESEGUITA: `_compose_briefing` con `memory_store.fetch_for(None)`
    -- rossa, il regalo entra nel nucleo di Marta."""
    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
        _dice(app[MEMORY_STORE_KEY], PAOLO, "Il regalo per Marta sta nell'armadio")
        _dice(app[MEMORY_STORE_KEY], MARTA, "La caldaia va spenta a maggio")
        marta_sees, _ = compose_briefing(app, subject=MARTA)
        assert "caldaia" in marta_sees
        assert "regalo" not in marta_sees
        everyone_sees, _ = compose_briefing(app, subject=None)
        assert "caldaia" in everyone_sees and "regalo" in everyone_sees


@pytest.mark.asyncio
async def test_gli_strumenti_leggono_i_ricordi_del_soggetto_del_turno(tmp_path):
    """Mutazione ESEGUITA: `_all_memories` con `self._memory.fetch(limit=...)`
    -- rossa, la ricerca di Marta trova il regalo."""
    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
        _dice(app[MEMORY_STORE_KEY], PAOLO, "Il regalo per Marta sta nell'armadio")
        _dice(app[MEMORY_STORE_KEY], MARTA, "La caldaia va spenta a maggio")
        marta_sees = create_tool_dispatcher(app, soggetto=MARTA,
                                          soffitto=consente(MARTA, ruolo="utente"))
        trovati = await marta_sees.dispatch("search", {"genere": "ricordo"})
        assert [v["testo"] for v in trovati["voci"]] == ["La caldaia va spenta a maggio"]
        cercato = await marta_sees.dispatch("search", {"nome": "regalo"})
        assert cercato["trovate"] == 0, cercato


@pytest.mark.asyncio
async def test_il_contesto_della_chat_porta_i_ricordi_di_chi_parla(tmp_path):
    """La porta della chat, su entrambi i percorsi (il sincrono e il ponte
    chiedono la stessa `compose_chat_context`). Mutazione ESEGUITA:
    `compose_briefing(app, house, subject=None)` -- rossa."""
    from hiris.app.api.handlers_chat import compose_chat_context

    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
        _dice(app[MEMORY_STORE_KEY], PAOLO, "Il regalo per Marta sta nell'armadio")
        _dice(app[MEMORY_STORE_KEY], MARTA, "La caldaia va spenta a maggio")
        contesto = compose_chat_context(
            app, str(tmp_path), thread=ChatThread("persona:u-marta", "pannello"),
            soggetto=MARTA, ruolo="utente")
        assert "caldaia" in contesto
        assert "regalo" not in contesto
