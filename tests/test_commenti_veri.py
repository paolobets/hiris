"""Un commento che nomina un file del prodotto ne nomina uno che esiste.

Molte delle frasi false trovate dall'analisi del 01/10/2026 (capitolo X del
registro dei doppioni) erano la stessa cosa: un commento o un docstring che
manda il lettore a un modulo uscito da mesi -- `anagrafe.py`, `domande.py`,
`internal_token.py`. Chi segue quel rimando non trova niente, e chi non lo
segue crede che ci sia. Questo si verifica con un comando, quindi e' una prova.

**Cosa guarda**: i commenti `#` e i docstring dei file Python di `hiris/app`
e di `scripts/`, e dentro di loro ogni percorso di file Python scritto con
almeno una cartella (`home_space/topology.py`, `api/handlers_chat.py`). Un
nome nudo (`server.py`) non si guarda: senza cartella non si sa di quale file
si parli.

**Solo i file NOSTRI.** Un commento che cita il sorgente di Home Assistant
o del Supervisor (`homeassistant/helpers/entity.py`, `components/trace/...`)
nomina un file che in questo repository non c'e' e non deve esserci: e' la
citazione della fonte, che le regole del progetto chiedono. Si guarda quindi
un percorso solo se comincia da una cartella nostra -- quelle che `hiris/app`
ha oggi (chieste alla cartella), piu' quelle che ha avuto e non ha piu'.

**Cosa NON guarda**, ed e' dichiarato (revisione indipendente del 02/10/2026,
ogni caso eseguito e visto verde):

- una FUNZIONE uscita nominata in un commento (`type_census.report`), la
  forma `modulo.funzione`, e una frase falsa che non nomina nessun file;
- i commenti dei file JavaScript, dei file yaml e delle prove (`tests/`): li'
  i percorsi inesistenti sono spesso fixture volute (`hiris/app/a.py`);
- un file che non e' Python nominato in un commento (`static/config/x.js`);
- un percorso spezzato su due righe, e una stringa che non e' un docstring.

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

#: Le cartelle che il prodotto HA AVUTO e non ha piu'. L'elenco e' il fatto:
#: una cartella cancellata non si puo' chiedere alla cartella, e la storia di
#: git non c'e' in un clone superficiale come quello della CI. Chiesto a
#: `git log --all --name-only -- 'hiris/app/*/*'` il 02/10/2026: dodici, coi
#: nomi italiani di prima della rinomina (`casa`, `cervello`, `memoria`...),
#: che la prima stesura non aveva -- e un commento che mandava a
#: `cervello/osservatore.py` passava. `gateway` non e' mai stata una cartella
#: di `hiris/app`: resta perche' i vecchi documenti la nominano cosi'. Un
#: rimando che comincia da una di queste e' rosso per costruzione.
WITHDRAWN_PACKAGES = frozenset({
    "azione", "brain", "casa", "cervello", "consumi", "history", "mcp", "memoria",
    "schedulatore", "security", "tools", "watcher",
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
ADMITTED: dict[str, str] = {
    "hiris/app/env_util.py":
        "scripts/censimento.py dichiara che il file e' uscito, al passato.",
    "hiris/app/home_space/type_census.py":
        "scripts/censore_tipi.py dice da dove viene: era questo file, fino al 02/10/2026.",
    "scripts/doc_check.py":
        "scripts/release.py spiega perche' il passo che lo invocava non c'e' piu'.",
    "consumi/vocabolario.py":
        "scripts/rinomina.py racconta il caso su cui lo strumento fu provato.",
    "mind/baseline.py":
        "scripts/rinomina.py e rinomina_js.py: «file poi cancellato», detto li'.",
}


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


def _watched_files() -> list[pathlib.Path]:
    return sorted(APP.rglob("*.py")) + sorted((ROOT / "scripts").glob("*.py"))


def our_mentions() -> list[tuple[str, str]]:
    """Ogni (file, percorso nominato) che comincia da una cartella nostra."""
    ours = _our_packages()
    return [(path.relative_to(ROOT).as_posix(), mention)
            for path in _watched_files()
            for text in _comments_and_docstrings(path)
            for mention in MENTION.findall(text)
            if mention.split("/")[0] in ours]


def missing_mentions() -> list[str]:
    existing = _existing()
    return sorted({f"{where}: {mention}" for where, mention in our_mentions()
                   if not _exists(mention, existing) and mention not in ADMITTED})


def test_la_derivazione_dei_file_non_si_e_svuotata():
    assert len(_existing()) > 300
    assert _exists("home_space/topology.py", _existing())
    assert not _exists("home_space/archivio_che_non_c_e.py", _existing())


def test_il_cancello_guarda_davvero_dei_commenti():
    """Un estrattore che non trova piu' niente lascia il cancello verde e
    cieco. Misurato il 02/10/2026: 437 menzioni nostre in `hiris/app`, 94 in
    `scripts/`.

    Mutazione ESEGUITA: `_comments_and_docstrings` che torna `[]` -- rossa
    (`0 > 400`). Prima di questa prova restavano verdi tutte e tre le altre,
    anche con un rimando falso piantato (revisione del 02/10/2026)."""
    mentions = our_mentions()
    assert len(mentions) > 400, len(mentions)
    assert any(where.startswith("scripts/") for where, _ in mentions)
    assert any(where.startswith("hiris/app/") for where, _ in mentions)


def test_ogni_file_nominato_in_un_commento_esiste():
    missing = missing_mentions()
    assert not missing, (
        f"{len(missing)} rimandi a file che non esistono:\n" + "\n".join(missing))


def test_ogni_ammissione_serve_ancora():
    """Un'ammissione per un percorso che nessun commento nomina piu' e' un
    permesso vuoto: si toglie."""
    mentioned = {mention for _, mention in our_mentions()}
    stale = sorted(name for name in ADMITTED if name not in mentioned)
    assert not stale, f"ammissioni che non coprono piu' niente: {stale}"
    assert all(len(reason.strip()) >= 15 for reason in ADMITTED.values())
