"""Il tetto in caratteri di una risposta (Tappa 9, F7; R16, D3 della Tappa 9 e
D5 della Tappa 5).

Il tetto di uno strumento e' la sua risposta piu' grande misurata sulla casa
vera (misura M3 dello Sprint, `consumi.db` 24/09-07/10/2026), scritto nella
riga dello strumento con la data. Oltre il tetto `dispatch` riduce la
risposta: prima scende la profondita', poi si tolgono voci dal fondo, con
`oltre` che dice quante restano e come chiederle.
"""
from dataclasses import replace

import pytest

from hiris.app.home_space import tools
from hiris.app.home_space.tools import Ceiling, ToolDispatcher
from hiris.app.proxy.entity_cache import _to_minimal
from hiris.app.usage.giro import pesa_in_caratteri
from tests.test_knowledge_tools import _semina_casa

#: Le sorgenti di un lettore multimediale: l'attributo `source_list` di Home
#: Assistant, una lista che un amplificatore vero porta lunga.
_SORGENTI = [f"Sorgente numero {n:03d}" for n in range(300)]


def _lettori(quanti: int) -> dict:
    return {"piani": [], "aree": [{"id": "sala", "nome": "Sala"}], "dispositivi": [],
            "entita": [{"id": f"media_player.lettore_{n}", "nome": f"Lettore {n}",
                        "area_id": "sala", "dispositivo_id": None, "piattaforma": "x",
                        "categoria": None, "classe": None, "unita": None,
                        "disabilitata": 0, "nascosta": 0} for n in range(quanti)]}


class _Specchio:
    loaded = True

    def __init__(self, quanti: int) -> None:
        self._stati = [_to_minimal({"entity_id": f"media_player.lettore_{n}", "state": "on",
                                    "attributes": {"friendly_name": f"Lettore {n}",
                                                   "source_list": _SORGENTI}})
                       for n in range(quanti)]

    def all_states(self) -> list[dict]:
        return self._stati


def _dispatcher(tmp_path, quanti: int) -> ToolDispatcher:
    return ToolDispatcher(_semina_casa(tmp_path, casa=_lettori(quanti), comportamento=[]),
                          None, cache=_Specchio(quanti))


@pytest.mark.asyncio
async def test_oltre_il_tetto_search_scende_di_profondita_e_tiene_tutte_le_voci(tmp_path):
    """Dieci lettori alla media portano le loro sorgenti, e la risposta passa
    il tetto misurato di `search`. Scesa alla corta ci sta, con tutte e dieci
    le voci.

    Rossa prima: nessun tetto, la risposta usciva alla media. Mutazione
    ESEGUITA: `_under_ceiling` che torna la risposta com'e' -- rossa, coi
    caratteri nel messaggio."""
    tetto = tools._TOOL_PER_NAME["search"].ceiling.chars
    d = _dispatcher(tmp_path, 10)
    piena = await d._search({"dominio": "media_player"}, masked=False)
    assert piena["profondita"] == "media" and pesa_in_caratteri(piena) > tetto, \
        "la casa di prova non supera piu' il tetto: la prova non guarda niente"
    risposta = await d.dispatch("search", {"dominio": "media_player"})
    peso = pesa_in_caratteri(risposta)
    assert peso <= tetto, f"{peso} caratteri, tetto {tetto}"
    assert risposta["profondita"] == "corta"
    assert len(risposta["voci"]) == 10 and "oltre" not in risposta


@pytest.mark.asyncio
async def test_se_non_basta_la_profondita_si_tolgono_voci_e_oltre_lo_dice(tmp_path, monkeypatch):
    """Il tetto si abbassa per la prova sotto la risposta corta: allora si
    tolgono voci dal fondo, e `oltre` dice quante restano e da dove
    ripartire, contando anche quelle che la pagina aveva gia' lasciato fuori.

    Mutazione ESEGUITA: `_rows_under` senza le `restano` della pagina --
    rossa."""
    d = _dispatcher(tmp_path, 30)
    corta = await d._search({"dominio": "media_player", "limite": 20, "salta": 5},
                            masked=False)
    assert corta["profondita"] == "corta" and corta["oltre"]["restano"] == 5
    tetto = pesa_in_caratteri(corta) // 2
    riga = tools._TOOL_PER_NAME["search"]
    monkeypatch.setitem(tools._TOOL_PER_NAME, "search",
                        replace(riga, ceiling=Ceiling(tetto, "12/10/2026")))
    risposta = await d.dispatch("search", {"dominio": "media_player", "limite": 20,
                                           "salta": 5})
    assert pesa_in_caratteri(risposta) <= tetto
    date = len(risposta["voci"])
    assert 0 < date < 20
    assert risposta["voci"] == corta["voci"][:date]
    assert risposta["oltre"]["restano"] == 5 + (20 - date)
    assert risposta["oltre"]["salta"] == 5 + date
    assert "tetto" in risposta["oltre"]["suggerimento"]


def test_ogni_tetto_ha_la_sua_data_e_il_suo_strumento_sa_scendere():
    """D3: il tetto e' una misura, e porta la data. Uno strumento col tetto
    riceve `deepest`, cioe' sa rispondere a una profondita' piu' corta: senza,
    la prima meta' della riduzione (D5) non avrebbe niente da chiedere.

    Mutazione ESEGUITA: `_history` senza `deepest` -- rossa col nome."""
    import inspect
    import re

    misurati = [t for t in tools.TOOLS if t.ceiling is not None]
    assert misurati, "nessuno strumento ha un tetto: la derivazione si e' svuotata"
    for tool in misurati:
        assert tool.ceiling.chars > 0 and re.fullmatch(r"\d\d/\d\d/\d{4}",
                                                       tool.ceiling.measured), tool.name
        assert "deepest" in inspect.signature(tool.handler).parameters, tool.name
