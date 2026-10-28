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
  nelle altre righe della STESSA tabella -- lo stesso blocco di righe
  `- nome: ...` consecutive dello stesso testo -- e' una cella, non un
  doppione; fuori da quel blocco conta come ogni altra. Gli elenchi di regole
  della guida (`- Usa SEMPRE...`) non sono tabelle: due loro righe che
  finiscono con la stessa frase sono un doppione (R213-1, giro 213: con le
  celle ammesse per POSTO passavano).

Mutazioni ESEGUITE il 25/10/2026, senza toccare questa prova:
- rimessa in `claude_runner.TOOL_RULES` una regola di `execute` presa dalla
  sua descrizione («`entita` vuole gli id ESATTI...») -- rossa, con la frase e
  i due posti. Una prima versione di questa prova teneva intera ogni riga
  d'elenco, e la stessa mutazione era INERTE: la guida e' fatta di righe
  «- ...», e la riga intera non combaciava con nessuna frase;
- messa nella guida una cella del catalogo di `compute` («Ingressi: serie del
  periodo.») -- rossa: fuori dal suo elenco una cella e' una frase;
- rimesso «Il massimo e' 365.» nei due parametri di `calendar` -- rossa;
- «Vale sempre.» in coda a due righe «- » delle regole fondamentali di
  `TOOL_RULES` -- rossa (era verde prima di R213-1).
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


#: La riga di una tabella: `- nome: ...`, come quelle del catalogo di `compute`.
_TABLE_ROW = re.compile(r"^- [\w.`-]+: ")


def _sentences(text: str, text_id: int) -> list[tuple[str, tuple[int, int] | None]]:
    """Le frasi di un testo, ognuna col blocco di tabella di cui e' una cella
    -- una frase di una riga `- nome: ...` che non ne e' la testa -- o
    `None`. Il blocco e' `(testo, n)`: l'n-esima corsa di righe consecutive
    di quel testo che sono TUTTE righe di tabella. Un elenco di regole (`- Usa
    SEMPRE...`) non e' una tabella: le sue frasi contano come prosa."""
    lines = [line.strip() for line in text.splitlines()]
    runs: list[list[int]] = []
    for index, line in enumerate(lines):
        if line.startswith("- "):
            if runs and runs[-1][-1] == index - 1:
                runs[-1].append(index)
            else:
                runs.append([index])
    table_of = {index: (text_id, n) for n, run in enumerate(runs)
                if all(_TABLE_ROW.match(lines[i]) for i in run) for index in run}
    out = []
    for index, line in enumerate(lines):
        pieces = [s for s in re.split(r"(?<=[.!?])\s+", line.removeprefix("- ")) if s]
        out += [(piece, table_of.get(index) if n > 0 else None)
                for n, piece in enumerate(pieces)]
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
    where: dict[str, list[tuple[str, tuple[int, int] | None]]] = defaultdict(list)
    for text_id, (place, text) in enumerate(_fixed_context()):
        for sentence, cell in _sentences(text, text_id):
            where[sentence].append((place, cell))

    def allowed(seen) -> bool:
        places = {place for place, _cell in seen}
        if len(places) > 1:
            return False
        if next(iter(places)).startswith("parametro"):
            return True  # lo stesso parametro in due strumenti
        blocks = {cell for _place, cell in seen}
        return None not in blocks and len(blocks) == 1  # le celle di un elenco

    twice = {sentence: [place for place, _cell in seen]
             for sentence, seen in where.items() if len(seen) > 1 and not allowed(seen)}
    assert twice == {}, "\n".join(f"{places}: {sentence!r}"
                                  for sentence, places in twice.items())
