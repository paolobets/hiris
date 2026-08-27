"""La regola del tema: due copie INLINE, identiche e vincolate.

La risoluzione del tema viveva in cinque punti, e due erano gia' divergenti:
la pagina di configurazione onorava `?theme=light|dark`, la chat no. E quel
ramo non aveva nessuno scrittore: il suo unico produttore era la card
Lovelace, uscita per intero con la fetta E5 -- una copia divergente di una
regola, per servire un chiamante che non esiste piu'.

Le due che restano NON si possono fondere in un modulo: girano prima del
primo render, per non far lampeggiare la pagina, e caricare uno script
significherebbe esattamente il lampeggio che esistono per evitare. Quindi si
tengono identiche, e questa prova si rompe il giorno in cui una delle due
cambia da sola.
"""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def _blocco_inline(nome: str) -> str:
    html = (BASE / nome).read_text(encoding="utf-8")
    m = re.search(r"\(function\(\) \{.*?\}\)\(\);", html, re.DOTALL)
    assert m, f"lo script inline del tema non si trova in {nome}"
    return re.sub(r"\s+", " ", m.group(0)).strip()


def test_le_due_pagine_dipingono_il_tema_allo_stesso_modo():
    assert _blocco_inline("config.html") == _blocco_inline("index.html")


def test_nessuna_pagina_onora_un_parametro_che_nessuno_scrive():
    """Il ramo `?theme=` serviva la card Lovelace, uscita per intero. Un ramo
    vivo per un chiamante morto e' peggio del codice morto: e' una regola in
    piu' da tenere allineata, che nessuno esercita mai."""
    for nome in ("config.html", "index.html"):
        assert "searchParams.get('theme')" not in (BASE / nome).read_text(encoding="utf-8")
