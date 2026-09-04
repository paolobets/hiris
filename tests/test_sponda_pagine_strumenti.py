"""La sponda fra le descrizioni degli strumenti e le voci del menu.

Il difetto che ha motivato questo file: la chat costruiva una proposta e
rispondeva che restava «in attesa di conferma» **senza dire dove** si
conferma. Chi legge quella frase resta fermo, oppure cerca in Home Assistant
una cosa che in Home Assistant non c'e' ancora -- e la proposta scade
(`ConstructionStore.scadi`) senza che nessuno l'abbia vista. La cura e' stata
nominare la pagina dentro la descrizione dello strumento, che e' il solo
posto che il modello legge quando decide cosa dire.

**Perche' serve un test.** Una descrizione che nomina una pagina e' una
SPONDA: due file dicono la stessa parola e nessuno dei due importa l'altro --
`hiris/app/home_space/tools.py` da una parte, i due gusci HTML dall'altra.
Una sponda non sorvegliata e' vera il giorno in cui si scrive e falsa dal
primo rename in poi, e il rename non se ne accorge: rinominare la voce del
menu non fa arrossire niente in Python, e il modello continuerebbe a mandare
l'utente in una pagina che non si chiama piu' cosi'.

**Perche' legge gli HTML invece di ridigitare le etichette.** Se le parole
«Impegni» e «Proposte» fossero scritte qui, questo file diventerebbe il TERZO
posto da tenere allineato, e sorveglierebbe se stesso invece della sponda.
Le legge dove stanno, e verifica che i due gusci le dicano uguali.

**Perche' in `pytest` e non in `npm test`.** Un lato della sponda e' Python:
una prova sta dove sta il lato che non si puo' leggere dall'altra parte. Gli
HTML sono letti come TESTO -- per verificare che una parola ci sia non serve
un DOM, e montarne uno aggiungerebbe una dipendenza al cancello piu' semplice
del progetto.

**Cio' che questo file NON sorveglia, e non e' una dimenticanza.** La chat
continua a dire «promessa» parlando della cosa: e' la parola giusta in una
conversazione, ed e' proprio per questo che l'etichetta del menu e'
«Impegni» -- *prendere un impegno* e *fare una promessa* sono la stessa mossa
in due registri, e la giuntura regge senza traduzione. Qui si guarda solo che
il NOME DELLA PAGINA sia quello vero, non che il lessico della chat gli si
adegui.
"""
import re
from pathlib import Path

import pytest

from hiris.app.home_space.tools import PROMISE_TOOL_DEF, PROPOSE_TOOL_DEF

STATICI = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

# I due gusci. `config.html` e' quello dove le pagine vivono davvero;
# `index.html` e' quello da cui l'utente ci arriva (la chat), e per questo
# porta gli stessi href con un prefisso: `config#/agenda`.
GUSCI = ("config.html", "index.html")

# Le due rotte, con lo strumento che deve nominarne la pagina.
ROTTE = {"agenda": "promise", "constructions": "propose"}


def _etichetta_menu(guscio: str, rotta: str) -> str:
    """L'etichetta che il menu di `guscio` usa per `#/{rotta}`.

    Solleva invece di restituire vuoto: un'etichetta vuota renderebbe verde
    ogni `in` che la cerca dentro una descrizione, e il cancello direbbe di
    sorvegliare una sponda che non guarda piu'.
    """
    testo = (STATICI / guscio).read_text(encoding="utf-8")
    ancora = re.search(
        r'<a\b[^>]*href="[^"]*#/' + rotta + r'"[^>]*>.*?</a>',
        testo, re.DOTALL)
    if ancora is None:
        pytest.fail(f"{guscio}: nessuna voce di menu punta a #/{rotta}")
    titolo = re.search(r'\btitle="([^"]+)"', ancora.group(0))
    if titolo is None:
        pytest.fail(f"{guscio}: la voce #/{rotta} non porta un title")
    etichetta = titolo.group(1).strip()
    assert etichetta, f"{guscio}: la voce #/{rotta} ha un title vuoto"
    # Il title e' il valore comodo da leggere (identico nei due gusci, mentre
    # il markup visibile non lo e': `<span class="nav-label">` di qua, `<span>`
    # di la'). Ma cio' che l'utente LEGGE e' il testo, e un rename che toccasse
    # solo quello lascerebbe il cancello verde: si pretendono uguali.
    assert f">{etichetta}<" in ancora.group(0), (
        f"{guscio}: la voce #/{rotta} mostra un testo diverso dal suo "
        f"title «{etichetta}»")
    return etichetta


def test_propose_nomina_la_pagina_dove_la_proposta_aspetta():
    """`propose` apre un'attesa: deve dire dove si chiude. La parola e' quella
    del menu, letta dal menu."""
    etichetta = _etichetta_menu("config.html", "constructions")
    assert etichetta in PROPOSE_TOOL_DEF["description"], (
        f"la descrizione di `propose` non nomina la pagina «{etichetta}»: "
        "l'utente non sa dove va a confermare")


def test_promise_nomina_la_pagina_dove_l_impegno_si_ritrova():
    """La promessa parte da sola e non chiede niente, ma sapere dove si
    ritrova e' la differenza fra un impegno preso e uno sperato."""
    etichetta = _etichetta_menu("config.html", "agenda")
    assert etichetta in PROMISE_TOOL_DEF["description"], (
        f"la descrizione di `promise` non nomina la pagina «{etichetta}»")


@pytest.mark.parametrize("rotta", sorted(ROTTE))
def test_i_due_gusci_chiamano_la_pagina_allo_stesso_modo(rotta):
    """Due nomi per una pagina sola sarebbero il difetto di partenza servito
    due volte: il modello ne nominerebbe uno e l'utente vedrebbe l'altro."""
    etichette = {guscio: _etichetta_menu(guscio, rotta) for guscio in GUSCI}
    assert len(set(etichette.values())) == 1, (
        f"#/{rotta} ha etichette diverse nei due gusci: {etichette}")


@pytest.mark.parametrize("rotta,strumento", sorted(ROTTE.items()))
def test_la_sponda_regge_anche_dal_guscio_della_chat(rotta, strumento):
    """L'utente arriva alla pagina dalla chat, non da `config.html`: se un
    rename toccasse solo `index.html` la sponda sarebbe rotta proprio dove si
    legge la frase dello strumento."""
    definizioni = {"promise": PROMISE_TOOL_DEF, "propose": PROPOSE_TOOL_DEF}
    etichetta = _etichetta_menu("index.html", rotta)
    assert etichetta in definizioni[strumento]["description"], (
        f"la descrizione di `{strumento}` non nomina la pagina «{etichetta}» "
        "cosi' come la chiama il guscio della chat")
