"""«Struttura reale» di `CLAUDE.md` dice cio' che sta sul disco.

**Perche' esiste.** Il blocco descrive il codice, e un elenco che descrive
codice si deriva o non si scrive (`CLAUDE.md`, «Un cancello CHIEDE il suo
elenco»). Scritto a mano il 02/10/2026, il 14/10 nominava ancora
`model_activation.py` e `mind/actuator.py`, usciti nella 3.78.0, e taceva i
moduli nati dopo: nessuno se n'era accorto, perche' nessuno lo confrontava.
Il blocco resta scritto per le persone (un nome con la sua ragione); questa
prova chiede l'elenco al disco e li confronta, nelle due direzioni:

- ogni modulo del prodotto, ogni cartella di `hiris/app/` e ogni attrezzo di
  `scripts/` e' nominato nel blocco;
- ogni nome del blocco esiste.

Un modulo di una cartella si nomina nella riga della cartella (`api/`,
`mind/`...), un modulo di primo livello nella sua riga. `handlers_*.py` e
`chat/*.js` sono forme: valgono per i file che prendono, e ne devono prendere
almeno uno.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
APP = RADICE / "hiris" / "app"
SCRIPTS = RADICE / "scripts"

#: Un nome di file nel blocco: un percorso relativo con un'estensione, o una
#: forma (`*`). Un nome che finisce con `/` e' una cartella.
_NOME = re.compile(r"(?<![\w/.*])((?:[\w*]+/)*[\w*.-]*\.(?:py|mjs|ps1|js|json|html|css|svg)|"
                   r"[\w]+/)(?![\w/])")
_VOCE = re.compile(r"[├└]── (\S+)")


def blocco() -> str:
    """Il primo blocco recintato dopo l'intestazione «## Struttura reale»."""
    testo = (RADICE / "CLAUDE.md").read_text(encoding="utf-8")
    inizio = testo.index("```\n", testo.index("## Struttura reale")) + 4
    return testo[inizio:testo.index("```\n", inizio)]


def voci() -> dict[str, str]:
    """`{testa: testo}`: una voce comincia a una riga con `├──`/`└──` o a una
    riga a colonna zero (`scripts/`), e prende le righe di seguito."""
    trovate: dict[str, str] = {}
    corrente = None
    for riga in blocco().splitlines():
        voce = _VOCE.search(riga)
        if voce:
            corrente = voce.group(1)
        elif riga and not riga[0].isspace() and riga[0] not in "│":
            corrente = riga.split()[0]
        if corrente is None:
            continue
        trovate[corrente] = trovate.get(corrente, "") + riga + "\n"
    return trovate


def nomi(testo: str) -> set[str]:
    """I nomi di file e di cartella di una voce, senza i rimandi alle prove
    (`tests/...`), che si controllano a parte."""
    return {n for n in _NOME.findall(testo) if not n.startswith("tests/")}


def rimandi() -> set[str]:
    """I rimandi alle prove: nominati nel blocco, devono esistere."""
    return {n for n in _NOME.findall(blocco()) if n.startswith("tests/")}


def _file(cartella: Path) -> list[str]:
    """I file sotto `cartella`, relativi, senza `__init__.py`, cache e file
    nascosti (`static/.gitkeep`)."""
    return sorted(p.relative_to(cartella).as_posix() for p in cartella.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts
                  and p.name != "__init__.py" and not p.name.startswith("."))


def _prende(forma: str, percorso: str) -> bool:
    if forma.endswith("/"):
        return percorso.startswith(forma)
    return fnmatch.fnmatchcase(percorso, forma) and percorso.count("/") == forma.count("/")


def _confronta(dove: str, forme: set[str], file: list[str]) -> list[str]:
    rilievi = [f"{dove}: `{f}` esiste e il blocco non lo nomina"
               for f in file if not any(_prende(forma, f) for forma in forme)]
    rilievi += [f"{dove}: il blocco nomina `{forma}`, che non prende nessun file"
                for forma in sorted(forme) if not any(_prende(forma, f) for f in file)]
    return rilievi


def rilievi() -> list[str]:
    tutte = voci()
    cartelle = {testa for testa in tutte if testa.endswith("/")} - {"hiris/", "app/", "scripts/"}
    trovati: list[str] = []

    vere = sorted(p.name + "/" for p in APP.iterdir()
                  if p.is_dir() and p.name != "__pycache__")
    trovati += [f"hiris/app/{c}: la cartella esiste e il blocco non la nomina"
                for c in vere if c not in cartelle]
    trovati += [f"hiris/app/{c}: il blocco la nomina e non esiste"
                for c in sorted(cartelle) if c not in vere]

    primo_livello = set()
    for testa, testo in tutte.items():
        if testa in cartelle or testa in {"hiris/", "scripts/"}:
            continue
        primo_livello |= {n for n in nomi(testo) if n.endswith(".py")}
    trovati += _confronta("hiris/app", primo_livello,
                          [f for f in _file(APP) if "/" not in f and f.endswith(".py")])

    for cartella in sorted(cartelle & set(vere)):
        forme = {n for n in nomi(tutte[cartella]) if n != cartella}
        trovati += _confronta(f"hiris/app/{cartella}", forme, _file(APP / cartella))

    trovati += _confronta("scripts", {n for n in nomi(tutte["scripts/"]) if n != "scripts/"},
                          [f for f in _file(SCRIPTS) if "/" not in f])
    trovati += [f"il blocco rimanda a `{r}`, che non esiste"
                for r in sorted(rimandi()) if not (RADICE / r).is_file()]
    return trovati


def test_il_blocco_e_il_disco_dicono_le_stesse_cose():
    trovati = rilievi()
    assert not trovati, (
        "«Struttura reale» di CLAUDE.md non dice cio' che sta sul disco. Il blocco "
        "si aggiorna insieme al codice, con la ragione di ogni nome nuovo:\n  "
        + "\n  ".join(trovati))


def test_la_lettura_del_blocco_non_si_e_rotta():
    """Un blocco letto male darebbe insiemi vuoti, e la prova sopra direbbe si'
    guardando niente: si controlla che ogni voce porti i suoi nomi."""
    tutte = voci()
    for testa in ("api/", "home_space/", "mind/", "action/", "static/", "scripts/"):
        assert len(nomi(tutte[testa])) > 1, f"la voce {testa} e' stata letta vuota"
    assert {"main.py", "server.py", "startup.py"} <= set().union(*map(nomi, tutte.values()))
