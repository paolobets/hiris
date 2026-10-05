"""Un lettore solo per le risposte JSON dei mestieri (Tappa 6, Task 3; D-11).

**Perche' esiste, misurato il 05/10/2026 su `5bce65d`.** Quattro mestieri --
osservatore, ricette, analista, attuatore -- cavavano il JSON dalla risposta
del modello con quattro lettori, e i lettori non erano d'accordo: i primi due
tolleravano il testo intorno al JSON (la staccionata, poi la ricerca per
parentesi), gli altri due toglievano solo una staccionata **iniziale**. Una
risposta come «Ecco l'analisi: {...}» era buona per le ricette e illeggibile per
l'analista. Un quinto lettore, gemello degli ultimi due, viveva nel «Rifalla»
delle proposte (`api/handlers_proposals._read_proposal`).

Queste prove chiedono a OGNI mestiere di accettare cio' che gli altri
accettano. Sono scritte sul comportamento del mestiere -- la funzione che
applica la risposta -- e non sul lettore, cosi' sopravvivono alla sua
unificazione: se un mestiere tornasse ad avere un lettore suo, piu' stretto,
arrossirebbero.
"""
import json

import pytest

from hiris.app.api import handlers_proposals
from hiris.app.mind import actuator_turn, analyst_turn, observer
from hiris.app.mind import recipe_turn as rt
from hiris.app.mind.knowledge import KnowledgeStore
from tests.test_mind_actuator_turn import _osservazioni as osservazioni_attuatore
from tests.test_mind_analyst_turn import _serie as serie_analista
from tests.test_mind_recipe_turn import CASA, RICETTA_BUONA

DECISIONI = [{"id": "climate.camera_t", "dentro": True, "motivo": "scalda"}]
ANALISI = {"osservazioni": [{"quale": 0, "innesco": 1,
                             "cosa": "il prelievo e' salito", "spiegato": None,
                             "cosa_cambierebbe": "meno prelievo, meno spesa"}]}
ATTUAZIONE = {"esiti": [{"osservazione": 0, "gesto": "indagine",
                         "trovato": "il sensore era fermo"}]}
PROPOSTA = {"testo": "spegni lo scaldabagno alle 23", "perche": "costa meno"}


def _osservatore(testo):
    decisioni, guasto = observer.read_decisions(testo)
    return guasto is None and [d["id"] for d in decisioni] == ["climate.camera_t"]


def _ricette(testo, tmp_path):
    sapere = KnowledgeStore(str(tmp_path / "sapere.db"))
    try:
        return rt.apply_recipe(sapere, CASA, "dev1", testo, who="prova",
                               when_ts=1_758_000_000.0)["scritta"]
    finally:
        sapere.close()


def _analista(testo):
    return analyst_turn.apply_analysis(serie_analista(), testo)["problemi"] == []


def _attuatore(testo):
    return actuator_turn.apply_actuation(osservazioni_attuatore(),
                                         testo)["problemi"] == []


def _rifalla(testo):
    return handlers_proposals._read_proposal(testo)[0] == PROPOSTA["testo"]


MESTIERI = {
    "osservatore": (DECISIONI, lambda t, _p: _osservatore(t)),
    "ricette": (RICETTA_BUONA, _ricette),
    "analista": (ANALISI, lambda t, _p: _analista(t)),
    "attuatore": (ATTUAZIONE, lambda t, _p: _attuatore(t)),
    "rifalla": (PROPOSTA, lambda t, _p: _rifalla(t)),
}

#: Le forme che un modello usa davvero per incorniciare il JSON. Ognuna e'
#: accettata da almeno un lettore di partenza: la prova chiede che lo sia da
#: tutti.
FORME = {
    "nudo": "{j}",
    "staccionata json": "```json\n{j}\n```",
    "staccionata senza linguaggio": "```\n{j}\n```",
    "testo prima e dopo": "Ecco la risposta:\n{j}\nSpero sia utile.",
    "testo intorno alla staccionata": "Ecco:\n```json\n{j}\n```\nFine.",
}


@pytest.mark.parametrize("forma", sorted(FORME))
@pytest.mark.parametrize("mestiere", sorted(MESTIERI))
def test_ogni_mestiere_legge_cio_che_gli_altri_leggono(mestiere, forma, tmp_path):
    """Rossa su `5bce65d` per l'analista, l'attuatore e il «Rifalla» sul testo
    prima del JSON: toglievano solo una staccionata iniziale."""
    dato, applica = MESTIERI[mestiere]
    testo = FORME[forma].format(j=json.dumps(dato, ensure_ascii=False))

    assert applica(testo, tmp_path), (
        f"il mestiere «{mestiere}» non legge la forma «{forma}»: {testo!r}")
