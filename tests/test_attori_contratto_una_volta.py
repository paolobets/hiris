"""Sul ponte il contratto di risposta viaggia una volta sola (D-05, Chiusura,
F7, 13/10/2026).

Il ponte riceve la domanda in cronologia e il contratto come `istruzione` di
chiusura (`agent/prompts.build_chat_messages`). Fino al 13/10/2026 analista,
ricette e proponente mettevano il contratto ANCHE in fondo alla domanda: sul
ponte il modello lo leggeva due volte, e pagava due volte i suoi token.
L'osservatore lo evitava gia' (`observer.build_house_question`): gli altri ora
fanno lo stesso, con una domanda senza contratto (`build_*_body`).

**Le due porte mandano lo stesso testo**: sulla catena la domanda col
contratto in fondo, sul ponte la domanda e poi l'istruzione. Lo si confronta
carattere per carattere.

**Gli attori si chiedono alla cartella**, non si elencano: ogni turno per il
ponte e' un dizionario con la chiave `istruzione`, e ogni modulo di `mind/` che
ne scrive uno deve scriverlo dentro un `bridge_turn` e avere qui il suo caso, o
la prova lo nomina. La derivazione ha trovato da se' due copie che il registro
non nominava: `automate_turn` («Rendila automatica») e `proposal_redo`
(«Rifalla», che il turno lo componeva in linea dentro `redo`).

Mutazioni ESEGUITE il 13/10/2026, ripristino verificato con `git status`:
- rimesso `lines.append(ANSWER_CONTRACT)` in `analyst_turn.build_question_body`
  -- rossa (il contratto due volte sul ponte, e la catena con due contratti);
- `recipe_turn.bridge_turn` che chiama di nuovo `build_device_question` --
  rossa;
- il turno del «Rifalla» rimesso in linea dentro `proposal_redo.redo` --
  rossa (`test_ogni_attore_del_ponte_ha_il_suo_caso`: `redo` scrive un
  turno fuori da un `bridge_turn`).
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from hiris.app.home_space.house import House
from hiris.app.home_space.topology import Mirror
from hiris.app.mind import (
    analyst_turn,
    automate_turn,
    observer,
    proposal_redo,
    proposer_turn,
    recipe_turn,
)
from hiris.app.mind.store import ObservationsStore

MIND = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app" / "mind"


def bridge_turns() -> dict[str, set[str]]:
    """modulo di `mind/` -> le funzioni che scrivono un turno per il ponte
    (un dizionario letterale con la chiave `istruzione`): chieste al
    sorgente."""
    found: dict[str, set[str]] = {}
    for path in sorted(MIND.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if isinstance(node, ast.Dict) and any(
                        isinstance(key, ast.Constant) and key.value == "istruzione"
                        for key in node.keys):
                    found.setdefault(path.stem, set()).add(func.name)
    return found


def _series():
    return {"giorni": ["2026-09-12", "2026-09-13"],
            "obiettivi": [{"dal": "2026-09-12", "al": "2026-09-13",
                           "testo": "spendere meno", "scritto_ts": 1.0}],
            "serie": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                       "chiave": None, "operazione": "somma_periodo", "unita": "kWh",
                       "valori": [0.3, 0.74], "coperture": [1.0, 1.0], "perche": [],
                       "scostamento": {"ultimo": 0.74, "mediana": 0.3, "scarto": 0.0,
                                       "quanti_scarti": 2.75, "base": 1}}]}


def _house():
    row = {"id": "sensor.forno_energia", "nome": "Forno Energia", "classe": "energy",
           "unita": "kWh", "translation_key": None, "categoria": None,
           "disabilitata": 0, "nascosta": 0, "area_id": None,
           "dispositivo_id": "dev_forno", "piattaforma": "x"}
    return House({"entita": [row], "aree": [],
                  "dispositivi": [{"id": "dev_forno", "nome": "Forno"}]},
                 Mirror(state={row["id"]: "3.2"}))


def _proposal():
    return {"id": "p1", "testo": "spegni lo scaldabagno di notte",
            "perche": "consuma a vuoto", "prova": {"misura": "prelievo"}, "giri": []}


def _observations():
    return [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
             "chiave": None, "cosa": "il prelievo e' salito", "base": 2}]


@pytest.fixture
def archivio(tmp_path):
    store = ObservationsStore(str(tmp_path / "osservazioni.db"))
    yield store
    store.close()


def _cases(archivio):
    """modulo -> (domanda della catena, turno del ponte, contratto)."""
    house = _house()
    return {
        "observer": (observer.build_question(
                         archivio.objective()["testo"], observer.house_lines(house)),
                     observer.bridge_turn(archivio, house, opening=False),
                     observer.ANSWER_CONTRACT),
        "analyst_turn": (analyst_turn.build_question(_series()),
                         analyst_turn.bridge_turn(_series()),
                         analyst_turn.ANSWER_CONTRACT),
        "recipe_turn": (recipe_turn.build_device_question("x", house, "dev_forno"),
                        recipe_turn.bridge_turn("x", house, "dev_forno"),
                        recipe_turn.ANSWER_CONTRACT),
        "proposer_turn": (proposer_turn.build_question(_observations()),
                          proposer_turn.bridge_turn(_observations()),
                          proposer_turn.ANSWER_CONTRACT),
        "automate_turn": (automate_turn.build_question(_proposal()),
                          automate_turn.bridge_turn(_proposal()),
                          automate_turn.ANSWER_CONTRACT),
        "proposal_redo": (proposal_redo.build_question(
                              _proposal(), "di giorno no", _observations()[0]),
                          proposal_redo.bridge_turn(
                              _proposal(), "di giorno no", _observations()[0]),
                          proposer_turn.ANSWER_CONTRACT),
    }


def test_ogni_attore_del_ponte_ha_il_suo_caso(archivio):
    """La derivazione e i casi coincidono; e non si e' svuotata: i quattro
    attori del ponte di oggi ci sono."""
    found = bridge_turns()
    assert {"observer", "analyst_turn", "recipe_turn", "proposer_turn",
            "automate_turn", "proposal_redo"} <= set(found)
    assert set(_cases(archivio)) == set(found)
    outside = {name: funcs - {"bridge_turn"} for name, funcs in found.items()
               if funcs - {"bridge_turn"}}
    assert not outside, f"turni del ponte scritti fuori da un bridge_turn: {outside}"


def test_sul_ponte_il_contratto_e_solo_l_istruzione(archivio):
    for name, (chain, turn, contract) in _cases(archivio).items():
        content = turn["history"][0]["content"]
        assert contract not in content, f"{name}: il contratto e' anche nella domanda"
        assert turn["istruzione"] == contract, name
        assert chain.count(contract) == 1, f"{name}: la catena non ha un contratto solo"
        assert chain.startswith(content) and chain.endswith(contract), name
        assert not chain[len(content):-len(contract)].strip("\n"), (
            f"{name}: il ponte e la catena non mandano lo stesso testo")
