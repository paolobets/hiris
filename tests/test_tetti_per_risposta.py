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


#: Le chiavi che Home Assistant mette nella forma breve di una traccia
#: (`ActionTrace.as_short_dict`, piu' `trigger` per le automazioni:
#: `components/trace/models.py` e `components/automation/trace.py`, tag
#: `2026.9.0`, letti il 12/10/2026).
_BREVE = {"last_step": "action/1", "run_id": "r1", "state": "stopped",
          "script_execution": "finished",
          "timestamp": {"start": "2026-10-12T08:00:00+00:00",
                        "finish": "2026-10-12T08:00:01+00:00"},
          "domain": "automation", "item_id": "177131", "trigger": "state of sensor.x"}


def _traccia_grande(passi: int = 12) -> dict:
    """Una traccia nella forma di `trace/get` (`as_extended_dict`): ogni passo
    nella forma di `TraceElement.as_dict` (`helpers/trace.py`, stesso tag),
    con le variabili cambiate che ripetono uno stato intero -- quello di un
    lettore con le sue sorgenti."""
    stato = {"entity_id": "media_player.lettore_0", "state": "on",
             "attributes": {"source_list": _SORGENTI}}
    return {**_BREVE,
            "trace": {f"action/{n}": [{"path": f"action/{n}",
                                       "timestamp": "2026-10-12T08:00:00+00:00",
                                       "changed_variables": {"trigger": {"to_state": stato}},
                                       "result": {"params": {"domain": "light"}}}]
                      for n in range(passi)},
            "config": {"id": "177131", "alias": "Prova", "actions": []},
            "blueprint_inputs": None,
            "context": {"id": "c1", "parent_id": None, "user_id": None}}


def _dettaglio(depth: str, traccia: dict) -> dict:
    from hiris.app.home_space import house_history as hh
    from tests.test_house_history import _NESSUNA, _q
    chosen = hh.Chosen(1, dict(_NESSUNA), depth, [hh.Subject("automation.x", "X")])
    return hh.run_detail(_q(cosa="esecuzioni", esecuzione="r1"), chosen, traccia)


def test_traccia_porta_profondita_dichiarata():
    """C-37: `run_detail` dichiarava la profondita' della scelta e rendeva la
    traccia sempre intera -- `profondita: corta` su 90.000 caratteri, e il
    tetto non aveva niente da chiedere. Le tre profondita' sono le forme di
    Home Assistant: la completa e' `trace/get` intera; la media toglie ai
    passi le `changed_variables` (le variabili, non cio' che il passo ha
    fatto); la corta e' la forma breve che Home Assistant stesso da' di una
    traccia (`as_short_dict`).

    Rossa prima: la media e la corta erano la completa. Mutazione ESEGUITA:
    la media che tiene le variabili -- rossa."""
    traccia = _traccia_grande()
    completa, media, corta = (_dettaglio(d, traccia)["voci"][0]
                              for d in ("completa", "media", "corta"))
    assert completa == traccia
    assert set(media) == set(completa)
    for elementi in media["trace"].values():
        for elemento in elementi:
            assert "changed_variables" not in elemento
            assert {"path", "timestamp", "result"} <= set(elemento)
    assert corta == _BREVE
    assert pesa_in_caratteri(corta) < pesa_in_caratteri(media) < pesa_in_caratteri(completa)


@pytest.mark.asyncio
async def test_traccia_troppo_grande_scende_media(tmp_path):
    """La traccia passo per passo sta sotto il tetto di `history` (C-37): oltre,
    si richiede a una profondita' piu' corta.

    Rossa prima: usciva intera, oltre il tetto. Con la mutazione della prova
    qui sopra si ferma alla corta: rossa anche questa."""
    from tests.test_history_tool import _history_dispatcher, _house
    tetto = tools._TOOL_PER_NAME["history"].ceiling.chars
    traccia = _traccia_grande(passi=40)
    assert pesa_in_caratteri(traccia) > tetto, "la traccia di prova sta gia' sotto il tetto"
    ha = _house(answers={"trace/get": lambda extra: traccia})
    risposta = await _history_dispatcher(tmp_path, ha).dispatch(
        "history", {"cosa": "esecuzioni", "riferimento": "automation.rifiuto_vetro",
                    "esecuzione": "r1"})
    peso = pesa_in_caratteri(risposta)
    assert peso <= tetto, f"{peso} caratteri, tetto {tetto}"
    assert risposta["profondita"] == "media"
    assert set(risposta["voci"][0]["trace"]) == set(traccia["trace"])
