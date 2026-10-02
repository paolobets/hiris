"""Un commento che nomina un file del prodotto ne nomina uno che esiste.

Molte delle frasi false trovate dall'analisi del 01/10/2026 (capitolo X del
registro dei doppioni) erano la stessa cosa: un commento o un docstring che
manda il lettore a un modulo uscito da mesi -- `anagrafe.py`, `domande.py`,
`internal_token.py`. Chi segue quel rimando non trova niente, e chi non lo
segue crede che ci sia. Questo si verifica con un comando, quindi e' una prova.

**Cosa guarda**: i commenti `#` e i docstring di `hiris/app`, e dentro di
loro ogni percorso di file Python scritto con almeno una cartella
(`home_space/topology.py`, `api/handlers_chat.py`). Un nome nudo (`server.py`)
non si guarda: senza cartella non si sa di quale file si parli.

**Solo i file NOSTRI.** Un commento che cita il sorgente di Home Assistant
o del Supervisor (`homeassistant/helpers/entity.py`, `components/trace/...`)
nomina un file che in questo repository non c'e' e non deve esserci: e' la
citazione della fonte, che le regole del progetto chiedono. Si guarda quindi
un percorso solo se comincia da una cartella nostra -- quelle che `hiris/app`
ha oggi (chieste alla cartella), piu' quelle che ha avuto e non ha piu'.

**Cosa NON guarda**, ed e' dichiarato: una FUNZIONE uscita nominata in un
commento (`type_census.report`), e una frase falsa che non nomina nessun file.
Quelle restano agli occhi.

Mutazione ESEGUITA: aggiunto in `home_space/topology.py` il commento
`# vedi home_space/archivio_vecchio.py` -- rossa, col file e il nome.
"""
import ast
import io
import pathlib
import re
import tokenize

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"

#: Un percorso con almeno una cartella e l'estensione `.py`.
MENTION = re.compile(r"(?<![\w/.])((?:[a-z_]+/)+[a-z_][a-z0-9_]*\.py)\b")

#: Le cartelle che il prodotto HA AVUTO e non ha piu' (CLAUDE.md, «Non
#: esistono piu'»). L'elenco e' il fatto: una cartella cancellata non si puo'
#: chiedere a nessuno. Un rimando che comincia da una di queste e' rosso per
#: costruzione, ed e' cio' che si vuole.
WITHDRAWN_PACKAGES = frozenset({"brain", "history", "mcp", "security", "tools", "watcher",
                                "gateway"})


def _our_packages() -> frozenset[str]:
    """Le cartelle da cui un percorso nostro puo' cominciare."""
    living = {path.name for path in APP.iterdir()
              if path.is_dir() and not path.name.startswith("__")}
    assert len(living) >= 10, sorted(living)
    return frozenset(living | {"hiris", "app", "tests", "scripts"} | WITHDRAWN_PACKAGES)


#: Le sole menzioni ammesse di file che non ci sono, ognuna col suo motivo.
#: Chiude per difetto: un percorso nuovo che non esiste e' rosso finche'
#: qualcuno non lo ammette qui, scrivendo perche'.
ADMITTED: dict[str, str] = {}


def _comments_and_docstrings(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = [token.string for token in tokenize.generate_tokens(io.StringIO(text).readline)
             if token.type == tokenize.COMMENT]
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                found.append(docstring)
    return found


def _existing() -> set[str]:
    """Ogni file Python del repository, come percorso relativo alla radice."""
    return {str(path.relative_to(ROOT)).replace("\\", "/")
            for folder in ("hiris", "scripts", "tests")
            for path in (ROOT / folder).rglob("*.py")}


def _exists(mention: str, existing: set[str]) -> bool:
    return any(known == mention or known.endswith("/" + mention) for known in existing)


def missing_mentions() -> list[str]:
    existing = _existing()
    ours = _our_packages()
    found = []
    for path in sorted(APP.rglob("*.py")):
        for text in _comments_and_docstrings(path):
            for mention in MENTION.findall(text):
                if mention.split("/")[0] not in ours:
                    continue
                if not _exists(mention, existing) and mention not in ADMITTED:
                    found.append(f"{path.relative_to(ROOT).as_posix()}: {mention}")
    return sorted(set(found))


def test_la_derivazione_dei_file_non_si_e_svuotata():
    assert len(_existing()) > 300
    assert _exists("home_space/topology.py", _existing())
    assert not _exists("home_space/archivio_che_non_c_e.py", _existing())


def test_ogni_file_nominato_in_un_commento_esiste():
    missing = missing_mentions()
    assert not missing, (
        f"{len(missing)} rimandi a file che non esistono:\n" + "\n".join(missing))


def test_ogni_ammissione_serve_ancora():
    """Un'ammissione per un percorso che nessun commento nomina piu' e' un
    permesso vuoto: si toglie."""
    mentioned = set()
    for path in APP.rglob("*.py"):
        for text in _comments_and_docstrings(path):
            mentioned.update(MENTION.findall(text))
    stale = sorted(name for name in ADMITTED if name not in mentioned)
    assert not stale, f"ammissioni che non coprono piu' niente: {stale}"
    assert all(len(reason.strip()) >= 15 for reason in ADMITTED.values())
