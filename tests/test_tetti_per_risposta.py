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
from hiris.app.home_space.house_query import page_rows
from hiris.app.home_space.tools import CharCap, ToolDispatcher
from hiris.app.usage.giro import pesa_in_caratteri
from tests._specchio_finto import SpecchioFinto, raw_state
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


def _specchio(quanti: int) -> SpecchioFinto:
    """Lo specchio VERO, coi lettori accesi e le loro sorgenti."""
    return SpecchioFinto(raw_state(f"media_player.lettore_{n}", "on", f"Lettore {n}",
                                   source_list=_SORGENTI)
                         for n in range(quanti))


def _dispatcher(tmp_path, quanti: int) -> ToolDispatcher:
    return ToolDispatcher(_semina_casa(tmp_path, casa=_lettori(quanti), comportamento=[]),
                          None, cache=_specchio(quanti))


@pytest.mark.asyncio
async def test_oltre_il_tetto_search_scende_di_profondita_e_tiene_tutte_le_voci(tmp_path):
    """Dieci lettori alla media portano le loro sorgenti, e la risposta passa
    il tetto misurato di `search`. Scesa alla corta ci sta, con tutte e dieci
    le voci.

    Rossa prima: nessun tetto, la risposta usciva alla media. Mutazione
    ESEGUITA: `_under_cap` che torna la risposta com'e' -- rossa, coi
    caratteri nel messaggio."""
    tetto = tools._TOOL_PER_NAME["search"].cap.chars
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
    rossa (12/10/2026, quando il taglio lo faceva `tools`). Dal giro 124
    (N124-1) pagina e `oltre` li calcola il gestore, richiamato con un
    `limite` piu' piccolo: la mutazione equivalente e' `_rows_under` che
    non passa `limite` al gestore -- rossa."""
    d = _dispatcher(tmp_path, 30)
    corta = await d._search({"dominio": "media_player", "limite": 20, "salta": 5},
                            masked=False)
    assert corta["profondita"] == "corta" and corta["oltre"]["restano"] == 5
    tetto = pesa_in_caratteri(corta) // 2
    riga = tools._TOOL_PER_NAME["search"]
    monkeypatch.setitem(tools._TOOL_PER_NAME, "search",
                        replace(riga, cap=CharCap(tetto, "12/10/2026")))
    risposta = await d.dispatch("search", {"dominio": "media_player", "limite": 20,
                                           "salta": 5})
    assert pesa_in_caratteri(risposta) <= tetto
    date = len(risposta["voci"])
    assert 0 < date < 20
    assert risposta["voci"] == corta["voci"][:date]
    assert risposta["oltre"]["restano"] == 5 + (20 - date)
    assert risposta["oltre"]["salta"] == 5 + date
    assert "tetto" in risposta["oltre"]["suggerimento"]


@pytest.mark.asyncio
async def test_scesa_alla_corta_il_taglio_resta_alla_corta(tmp_path, monkeypatch):
    """D5 della Tappa 5: prima la profondita', poi le righe. Dieci lettori
    partono alla media; col tetto sotto la loro risposta corta, `dispatch`
    scende alla corta e solo dopo taglia, e la pagina tagliata resta alla
    corta: il `deepest` raggiunto passa al gestore richiamato con `limite`.

    Mutazione ESEGUITA (N126-2, giro 126): la discesa che non porta avanti
    `deepest` (`occurrence = shallower` senza aggiornare `options`) -- rossa,
    la risposta tagliata esce alla media."""
    d = _dispatcher(tmp_path, 10)
    media = await d._search({"dominio": "media_player"}, masked=False)
    corta = await d._search({"dominio": "media_player"}, masked=False, deepest="corta")
    assert media["profondita"] == "media" and corta["profondita"] == "corta"
    tetto = pesa_in_caratteri(corta) // 2
    riga = tools._TOOL_PER_NAME["search"]
    monkeypatch.setitem(tools._TOOL_PER_NAME, "search",
                        replace(riga, cap=CharCap(tetto, "12/10/2026")))
    risposta = await d.dispatch("search", {"dominio": "media_player"})
    assert risposta["profondita"] == "corta", risposta["profondita"]
    assert "oltre" in risposta and 0 < len(risposta["voci"]) < 10
    assert pesa_in_caratteri(risposta) <= tetto


def test_ogni_tetto_ha_la_sua_data_e_il_suo_strumento_sa_scendere():
    """D3: il tetto e' una misura, e porta la data. Uno strumento col tetto
    riceve `deepest`, cioe' sa rispondere a una profondita' piu' corta: senza,
    la prima meta' della riduzione (D5) non avrebbe niente da chiedere.

    Mutazione ESEGUITA: `_history` senza `deepest` -- rossa col nome."""
    import inspect
    import re

    misurati = [t for t in tools.TOOLS if t.cap is not None]
    assert misurati, "nessuno strumento ha un tetto: la derivazione si e' svuotata"
    for tool in misurati:
        assert tool.cap.chars > 0 and re.fullmatch(r"\d\d/\d\d/\d{4}",
                                                   tool.cap.measured), tool.name
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
    tetto = tools._TOOL_PER_NAME["history"].cap.chars
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


#: Dieci sonde (la media), e i punti solo alle pari: i valori tengono solo i soggetti
#: con dei punti, quindi le voci sono una SOTTOSEQUENZA delle posizioni della
#: pagina (N124-1, giro 124).
_SONDE = [f"sensor.sonda_{n:02d}" for n in range(10)]


def _storia_sonde(tmp_path):
    import copy
    from datetime import timedelta

    from tests.test_history_tool import (
        _ADESSO,
        _CASA,
        _history_dispatcher,
        _house,
        _righe_grezze,
        _voce,
    )
    casa = copy.deepcopy(_CASA)
    casa["entita"] += [_voce(eid, f"Sonda {eid[-2:]}", "cucina") for eid in _SONDE]
    specchio = SpecchioFinto([
        *_righe_grezze(),
        *[raw_state(eid, "20", unit_of_measurement="°C", state_class="measurement")
          for eid in _SONDE]])
    # Un punto prima della finestra: la serie c'e', ma nella finestra non e'
    # successo niente, e i soggetti si ordinano per id, pari e dispari
    # alternati (`house_history._activity`).
    quando = (_ADESSO - timedelta(hours=30)).isoformat()
    serie = {eid: [{"quando": quando, "valore": "20"}]
             for n, eid in enumerate(_SONDE) if n % 2 == 0}
    return _history_dispatcher(tmp_path, _house(serie=serie), cache=specchio, casa=casa)


async def _pagine(d, argomenti: dict) -> list[list[str]]:
    """Le pagine di una domanda, seguendo `oltre.salta` finche' c'e'."""
    pagine, salta = [], 0
    while salta is not None and len(pagine) < 20:
        risposta = await d.dispatch("history", {**argomenti, "salta": salta})
        assert "errore" not in risposta, risposta
        pagine.append([v["id"] for v in risposta["voci"]])
        salta = (risposta.get("oltre") or {}).get("salta")
    return pagine


@pytest.mark.asyncio
@pytest.mark.parametrize("meno", [300, 600])
async def test_la_pagina_dopo_il_taglio_non_ripete_voci(tmp_path, monkeypatch, meno):
    """N124-1: oltre il tetto `history` toglieva voci dal fondo e diceva
    `salta = offset + tenute`, come se ogni voce fosse una posizione della
    pagina. Per i valori non lo e': la pagina dopo ripeteva `s02` e `s04`.
    Ora il taglio lo fa il gestore, richiamato con un `limite` piu' piccolo,
    e `oltre` lo calcola lui.

    Rossa prima, coi doppioni nel messaggio (lo scenario del revisore)."""
    d = _storia_sonde(tmp_path)
    argomenti = {"cosa": "valori", "nome": "sonda"}
    intera = await d._history(argomenti)
    attese = [v["id"] for v in intera["voci"]]
    assert attese == _SONDE[::2] and "oltre" not in intera
    tetto = pesa_in_caratteri(intera) - meno
    riga = tools._TOOL_PER_NAME["history"]
    monkeypatch.setitem(tools._TOOL_PER_NAME, "history",
                        replace(riga, cap=CharCap(tetto, "12/10/2026")))
    pagine = await _pagine(d, argomenti)
    lette = [ident for pagina in pagine for ident in pagina]
    assert len(pagine) > 1, "il tetto non ha tagliato: la prova non guarda"
    assert lette == attese, pagine


@pytest.mark.asyncio
async def test_il_taglio_tiene_tutte_le_voci_che_entrano(tmp_path, monkeypatch):
    """N124-3: il taglio tiene il massimo di voci sotto il tetto, non una
    pagina qualunque piu' piccola: con una voce in piu', alla stessa
    profondita' e con la stessa frase, passerebbe il tetto.
    Mutazione ESEGUITA: `_rows_fitting` che parte da una voce -- rossa."""
    d = _dispatcher(tmp_path, 30)
    argomenti = {"dominio": "media_player", "limite": 20}
    corta = await d._search(argomenti, masked=False)
    tetto = pesa_in_caratteri(corta) // 2
    riga = tools._TOOL_PER_NAME["search"]
    monkeypatch.setitem(tools._TOOL_PER_NAME, "search",
                        replace(riga, cap=CharCap(tetto, "12/10/2026")))
    risposta = await d.dispatch("search", argomenti)
    date = len(risposta["voci"])
    eccedente = tools._cap_note(
        await d._search({**argomenti, "limite": date + 1}, masked=False),
        CharCap(tetto, "12/10/2026"))
    assert pesa_in_caratteri(risposta) <= tetto < pesa_in_caratteri(eccedente)


@pytest.mark.asyncio
async def test_si_scende_fino_alla_corta_se_la_media_non_basta(tmp_path, monkeypatch):
    """N124-3: un lettore solo e' una scheda completa; alla media porta ancora
    le sue sorgenti, alla corta no. Col tetto fra le due la risposta scende di
    DUE gradini.

    Mutazione ESEGUITA: un gradino solo (completa -> media) -- rossa."""
    d = _dispatcher(tmp_path, 1)
    argomenti = {"riferimento": "media_player.lettore_0"}
    media = await d._search(argomenti, masked=False, deepest="media")
    corta = await d._search(argomenti, masked=False, deepest="corta")
    tetto = (pesa_in_caratteri(media) + pesa_in_caratteri(corta)) // 2
    riga = tools._TOOL_PER_NAME["search"]
    monkeypatch.setitem(tools._TOOL_PER_NAME, "search",
                        replace(riga, cap=CharCap(tetto, "12/10/2026")))
    risposta = await d.dispatch("search", argomenti)
    assert risposta["profondita"] == "corta" and pesa_in_caratteri(risposta) <= tetto


@pytest.mark.asyncio
async def test_history_scende_di_profondita(tmp_path, monkeypatch):
    """N124-3: la discesa di `history` passa `deepest` fino a
    `house_history.choose`. Una sonda sola e' alla completa; col tetto sotto
    la completa e sopra la media, la risposta e' la media.

    Mutazione ESEGUITA: `_history` che non inoltra `deepest` a
    `read_history` -- rossa; `read_history` che non lo inoltra a `choose` --
    rossa."""
    d = _storia_sonde(tmp_path)
    argomenti = {"cosa": "valori", "riferimento": "sensor.sonda_00"}
    completa = await d._history(argomenti)
    media = await d._history(argomenti, deepest="media")
    assert completa["profondita"] == "completa"
    assert pesa_in_caratteri(media) < pesa_in_caratteri(completa)
    tetto = pesa_in_caratteri(media)
    riga = tools._TOOL_PER_NAME["history"]
    monkeypatch.setitem(tools._TOOL_PER_NAME, "history",
                        replace(riga, cap=CharCap(tetto, "12/10/2026")))
    risposta = await d.dispatch("history", argomenti)
    assert risposta["profondita"] == "media" and pesa_in_caratteri(risposta) <= tetto


def test_oltre_la_fine_il_tetto_non_copre_il_suggerimento_della_pagina():
    """C-66 (N156-5, giro 156): oltre la fine `oltre` porta `restano: 0` e
    il suggerimento di `page_rows` («le righe si leggono da salta=0»). La
    frase del tetto parla delle voci che restano, e qui non ne resta
    nessuna: non deve prenderne il posto.

    Mutazione ESEGUITA: `not beyond.get("restano")` riportato a
    `"restano" not in beyond` in `_cap_note` -- rossa."""
    _, beyond = page_rows(["a", "b", "c"], 5, 10)
    assert beyond["restano"] == 0
    risposta = tools._cap_note({"voci": [], "oltre": beyond}, CharCap(10, "12/10/2026"))
    assert risposta["oltre"] == beyond
