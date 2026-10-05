"""La regola del tema: una sola, in `static/common.js`.

La risoluzione del tema viveva in cinque punti, e due erano gia' divergenti:
la pagina di configurazione onorava `?theme=light|dark`, la chat no. E quel
ramo non aveva nessuno scrittore: il suo unico produttore era la card
Lovelace, uscita per intero con la fetta E5 -- una copia divergente di una
regola, per servire un chiamante che non esiste piu'.

Poi ne restavano due copie in linea, tenute identiche da questa prova: si
pensava che non si potessero fondere in un modulo, perche' girano prima del
primo disegno. Dalla Tappa 4 (Task 3, registro C-16) common.js e' caricato
nell'<head>, prima di loro, e uno script sincrono nell'<head> ferma il
disegno finche' non ha girato: il lampo non c'e'. Le due righe in linea
chiamano `paintSavedTheme()` e basta; che chiamino solo funzioni di common.js
lo prova `tests/js/common.test.mjs`.
"""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def _blocco_inline(nome: str) -> str:
    html = (BASE / nome).read_text(encoding="utf-8")
    m = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert m, f"lo script inline del tema non si trova in {nome}"
    return re.sub(r"\s+", " ", m.group(1)).strip()


def test_le_due_pagine_dipingono_il_tema_allo_stesso_modo():
    assert _blocco_inline("config.html") == _blocco_inline("index.html")


def test_nessuna_pagina_onora_un_parametro_che_nessuno_scrive():
    """Il ramo `?theme=` serviva la card Lovelace, uscita per intero. Un ramo
    vivo per un chiamante morto e' peggio del codice morto: e' una regola in
    piu' da tenere allineata, che nessuno esercita mai."""
    for nome in ("config.html", "index.html"):
        assert "searchParams.get('theme')" not in (BASE / nome).read_text(encoding="utf-8")
