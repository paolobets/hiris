"""Nessuna frase del contesto fisso sta in due posti (Fase 2 dello sprint «Il
giro snello», approvata da Paolo il 25/10/2026).

Il contesto fisso e' cio' che parte a ogni giro prima di qualunque domanda: la
guida (`steering.compose_base` con tutti gli strumenti) e le descrizioni degli
strumenti -- quelli della chat (`KNOWLEDGE_TOOLS`), dell'analista e del
proponente. Una frase che ci sta due volte si paga due volte a ogni giro, e il
giorno che una delle due copie cambia, una delle due mente: misurato il
24/10/2026, la guida e la descrizione di `execute` dicevano due cose diverse
su un `cambiato` vuoto.

I testi si CHIEDONO alle loro fonti, non si ricopiano. Due regole di lettura,
scritte qui perche' sono il cancello:

- **un parametro con lo stesso nome e' lo stesso parametro**: `area` di
  `search` e `area` di `history` dicono la stessa cosa per la fondamenta 3
  (stessa cosa, stessa forma da tutte le porte), e non sono un doppione;
- **le righe di uno stesso elenco si ripetono la forma, non la prosa**: nel
  catalogo di `compute` ogni riga dice «Ingressi: ...» perche' e' una
  tabella. Una frase che dopo la testa di una riga (`- nome: ...`) torna
  nelle altre righe dello STESSO elenco e' una cella, non un doppione; fuori
  da quell'elenco conta come ogni altra.

Mutazioni ESEGUITE il 25/10/2026, senza toccare questa prova:
- rimessa in `claude_runner.TOOL_RULES` una regola di `execute` presa dalla
  sua descrizione («`entita` vuole gli id ESATTI...») -- rossa, con la frase e
  i due posti. Una prima versione di questa prova teneva intera ogni riga
  d'elenco, e la stessa mutazione era INERTE: la guida e' fatta di righe
  «- ...», e la riga intera non combaciava con nessuna frase;
- messa nella guida una cella del catalogo di `compute` («Ingressi: serie del
  periodo.») -- rossa: fuori dal suo elenco una cella e' una frase;
- rimesso «Il massimo e' 365.» nei due parametri di `calendar` -- rossa.
"""
from __future__ import annotations

import re
from collections import defaultdict

from hiris.app.home_space.tools import KNOWLEDGE_TOOLS
from hiris.app.mind.analyst_turn import analyst_tools
from hiris.app.mind.proposer_turn import proposer_tools
from hiris.app.steering import compose_base


def _descriptions(node, place: str, out: list[tuple[str, str]]) -> None:
    """Le `description` di uno strumento, ciascuna col suo posto. Quella di
    un parametro ha per posto il NOME del parametro (vedi il docstring del
    modulo)."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "description" and isinstance(value, str):
                out.append((place, value))
            elif key == "properties" and isinstance(value, dict):
                for name, schema in value.items():
                    _descriptions(schema, f"parametro «{name}»", out)
            else:
                _descriptions(value, place, out)
    elif isinstance(node, list):
        for value in node:
            _descriptions(value, place, out)


def _fixed_context() -> list[tuple[str, str]]:
    texts = [("la guida", compose_base([t["name"] for t in KNOWLEDGE_TOOLS]))]
    tools = {}
    for tool in KNOWLEDGE_TOOLS + analyst_tools() + proposer_tools():
        tools.setdefault(tool["name"], tool)
    for name, tool in tools.items():
        _descriptions(tool, f"lo strumento «{name}»", texts)
    return texts


def _sentences(text: str) -> list[tuple[str, bool]]:
    """Le frasi di un testo, ognuna con «e' una cella»: una frase di una riga
    d'elenco che non ne e' la testa."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        row = line.startswith("- ")
        pieces = [s for s in re.split(r"(?<=[.!?])\s+", line.removeprefix("- ")) if s]
        out += [(piece, row and n > 0) for n, piece in enumerate(pieces)]
    return out


def test_la_derivazione_guarda_davvero_il_contesto():
    """Un contesto improvvisamente piccolo e' un cancello che sembra vivo e
    non guarda piu' niente. Il pavimento e' cio' che deve esserci per forza:
    la guida, ogni strumento della chat, `compute` e `propose`."""
    places = {place for place, _text in _fixed_context()}
    assert "la guida" in places
    for name in [t["name"] for t in KNOWLEDGE_TOOLS] + ["compute", "propose"]:
        assert f"lo strumento «{name}»" in places, name


def test_nessuna_frase_del_contesto_fisso_sta_in_due_posti():
    where: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    for place, text in _fixed_context():
        for sentence, cell in _sentences(text):
            where[sentence].append((place, cell))

    def allowed(seen: list[tuple[str, bool]]) -> bool:
        places = {place for place, _cell in seen}
        if len(places) > 1:
            return False
        # Lo stesso parametro in due strumenti, o le celle di un elenco.
        return next(iter(places)).startswith("parametro") or all(c for _p, c in seen)

    twice = {sentence: [place for place, _cell in seen]
             for sentence, seen in where.items() if len(seen) > 1 and not allowed(seen)}
    assert twice == {}, "\n".join(f"{places}: {sentence!r}"
                                  for sentence, places in twice.items())
