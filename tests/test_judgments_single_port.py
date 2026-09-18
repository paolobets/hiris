"""Spec 2026-09-16 §4: una porta sola. Nessun modulo di produzione, fuori da
`mind/judgments.py` e dal seme, costruisce un `Fact` su un campo dei giudizi --
ne' col nome scritto in chiaro (`field="genere"`) ne' con la costante del
modulo dell'istantanea (`field=GENRE_FIELD`).

**Cosa NON vede, dichiarato**: un campo che arriva da una variabile
(`field=body["campo"]` passato a `knowledge.write`). Una prova lessicale non
segue i valori; quella strada la chiude la lettura, e la regola scritta qui.

Mutazioni ESEGUITE: in `api/handlers_mind.py` scrivere
`store.write(Fact(..., field="genere", ...))` -- rossa; la stessa con
`field=GENRE_FIELD` -- rossa."""
import pathlib
import re

from hiris.app.home_space import type_judgments
from hiris.app.home_space.type_judgments import JUDGMENT_FIELD_NAMES

RADICE = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"
PERMESSI = {"mind/judgments.py", "mind/seed.py"}


def _costanti_campo() -> list[str]:
    return sorted(name for name, value in vars(type_judgments).items()
                  if name.endswith("_FIELD") and value in JUDGMENT_FIELD_NAMES)


def test_costanti_campo_COPRONO_giudizi():
    """Senza questa, una costante nuova sfuggirebbe alla ricerca in silenzio.
    Mutazione ESEGUITA: un campo in `JUDGMENT_FIELD_NAMES` senza la sua
    costante `*_FIELD` -- rossa."""
    assert {getattr(type_judgments, n) for n in _costanti_campo()} == JUDGMENT_FIELD_NAMES


def test_nessuna_seconda_porta():
    letterali = "|".join(sorted(JUDGMENT_FIELD_NAMES))
    costanti = "|".join(_costanti_campo())
    schema = re.compile(rf"field\s*=\s*(?:[\"']({letterali})[\"']|\b({costanti})\b)")
    trovate = []
    for path in RADICE.rglob("*.py"):
        rel = path.relative_to(RADICE).as_posix()
        if rel in PERMESSI:
            continue
        testo = path.read_text(encoding="utf-8")
        if schema.search(testo):
            trovate.append(rel)
    assert not trovate, trovate
