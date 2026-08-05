#!/usr/bin/env python3
"""HIRIS censimento — rilevatore meccanico di codice morto.

Rende eseguibile la «review totale» del Refactor 2.0 (vedi CLAUDE.md): in un
progetto di demolizione la domanda non e' «cio' che hai aggiunto e' corretto?»
ma «cosa hai lasciato orfano?», e le righe morte non stanno dentro il diff.

Legge e stampa. Non modifica niente, ed esce sempre 0: e' uno strumento di
lettura, non un cancello di CI.

Uso:
  python scripts/censimento.py
"""
import argparse
import io
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
APP = ROOT / "hiris" / "app"
TESTS = ROOT / "tests"

_VERDE = "\033[32m"
_GIALLO = "\033[33m"
_GRIGIO = "\033[90m"
_RESET = "\033[0m"


@dataclass
class Reperto:
    """Una cosa che il censimento ha trovato e che qualcuno deve giudicare."""
    categoria: str
    nome: str
    dove: str
    nota: str = ""


_TITOLI: dict[str, str] = {
    "tabella-mai-toccata":       "Tabelle create e mai toccate",
    "tabella-scritta-mai-letta": "Tabelle scritte e mai lette",
    "tabella-letta-mai-scritta": "Tabelle lette e mai scritte",
    "opzione-mai-letta":         "Opzioni dell'add-on che nessun codice legge",
    "envvar-mai-esportata":      "Variabili d'ambiente lette e mai esportate da run.sh",
    "rotta-senza-chiamanti":     "Rotte HTTP che nessuno chiama",
    "rotta-solo-test":           "Rotte HTTP chiamate solo dai test",
}


# ── Helper ──────────────────────────────────────────────────────────────────

def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return p.name


def _riga(testo: str, offset: int) -> int:
    return testo.count("\n", 0, offset) + 1


def _file_py(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _leggi(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _senza_commenti(testo: str) -> str:
    """Il testo con i commenti Python sostituiti da spazi.

    Il SQL vive nei letterali di stringa; i commenti no. Ma un commento che
    *cita* del SQL — `advisory_store.py` spiega a parole perche' il suo
    `CREATE TABLE IF NOT EXISTS` basta — verrebbe letto come una tabella vera.
    Si usa `tokenize` invece di una regex su `#` perche' un cancelletto dentro
    una stringa non e' un commento.

    Le posizioni non cambiano: ogni commento diventa altrettanti spazi, cosi'
    i numeri di riga restano quelli del file originale.
    """
    try:
        token = list(tokenize.generate_tokens(io.StringIO(testo).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return testo  # file non tokenizzabile: meglio scansionarlo com'e'
    righe = testo.splitlines(keepends=True)
    for tok in token:
        if tok.type != tokenize.COMMENT:
            continue
        i = tok.start[0] - 1
        inizio, fine = tok.start[1], tok.end[1]
        righe[i] = righe[i][:inizio] + " " * (fine - inizio) + righe[i][fine:]
    return "".join(righe)


# ── Tabelle ─────────────────────────────────────────────────────────────────
# Le parole chiave SQL si cercano MAIUSCOLE e case-sensitive: la codebase
# scrive CREATE TABLE 25 volte su 25. Cercare "from" senza distinzione di
# maiuscole farebbe combaciare «from pathlib import Path» e una tabella morta
# di nome `pathlib` sembrerebbe viva.

_RE_CREATE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`]?(\w+)")
_RE_INSERT = re.compile(r"(?:INSERT|REPLACE)(?:\s+OR\s+\w+)?\s+INTO\s+[\"'`]?(\w+)")
_RE_UPDATE = re.compile(r"UPDATE\s+[\"'`]?(\w+)[\"'`]?\s+SET")
_RE_DELETE = re.compile(r"DELETE\s+FROM\s+[\"'`]?(\w+)")
_RE_LETTURA = re.compile(r"(?:FROM|JOIN)\s+[\"'`]?(\w+)")


def censisci_tabelle(files: list[Path]) -> list[Reperto]:
    """Tabelle dichiarate con CREATE TABLE, confrontate con chi le usa."""
    create: dict[str, str] = {}
    scritte: set[str] = set()
    lette: set[str] = set()

    for f in files:
        testo = _senza_commenti(_leggi(f))
        for m in _RE_CREATE.finditer(testo):
            create.setdefault(m.group(1).lower(), f"{_rel(f)}:{_riga(testo, m.start())}")
        for rx in (_RE_INSERT, _RE_UPDATE, _RE_DELETE):
            for m in rx.finditer(testo):
                scritte.add(m.group(1).lower())
        # Le letture si cercano DOPO aver rimosso i DELETE FROM, che
        # altrimenti conterebbero come letture pur essendo scritture.
        for m in _RE_LETTURA.finditer(_RE_DELETE.sub(" ", testo)):
            lette.add(m.group(1).lower())

    reperti: list[Reperto] = []
    for nome, dove in sorted(create.items()):
        if nome in scritte and nome in lette:
            continue
        if nome not in scritte and nome not in lette:
            reperti.append(Reperto("tabella-mai-toccata", nome, dove))
        elif nome not in lette:
            reperti.append(Reperto("tabella-scritta-mai-letta", nome, dove,
                                   "si riempie e nessuno la interroga"))
        else:
            reperti.append(Reperto("tabella-letta-mai-scritta", nome, dove,
                                   "la si interroga e nessuno la riempie"))
    return reperti


# ── Opzioni e variabili d'ambiente ──────────────────────────────────────────

_RE_EXPORT = re.compile(r"^\s*export\s+([A-Z_][A-Z0-9_]*)=", re.M)
_RE_ENV = re.compile(
    r"""(?:os\.environ\.get\(|os\.getenv\(|os\.environ\[)\s*["']([A-Z_][A-Z0-9_]*)["']"""
)
_RE_CHIAVE_YAML = re.compile(r"^(\s+)([a-z_][a-z0-9_]*):")
_RE_BASHIO = re.compile(r"""bashio::config\s+['"]([\w.]+)['"]""")


def _opzioni_addon(config_yaml: Path) -> list[tuple[str, int]]:
    """Percorsi puntati delle opzioni FOGLIA del blocco `options:`.

    Restituisce `mqtt.host`, non `mqtt` e `host` separati: una foglia dal nome
    generico (`host`, `url`, `token`) cercata da sola verrebbe dichiarata viva
    dal primo dizionario HTTP che la nomina, e il rilevatore tacerebbe su
    un'opzione davvero morta. I contenitori non sono opzioni: non si segnalano.

    Lettura per indentazione invece che con un parser YAML: lo strumento non
    deve avere dipendenze.
    """
    if not config_yaml.exists():
        return []

    chiavi: list[tuple[int, str, int]] = []  # (indentazione, nome, riga)
    dentro = False
    for i, riga in enumerate(_leggi(config_yaml).splitlines(), 1):
        if riga.startswith("options:"):
            dentro = True
            continue
        if not dentro:
            continue
        if riga and not riga.startswith((" ", "#")):
            break  # e' cominciato un altro blocco di primo livello (schema:)
        m = _RE_CHIAVE_YAML.match(riga)
        if m:
            chiavi.append((len(m.group(1)), m.group(2), i))

    out: list[tuple[str, int]] = []
    pila: list[tuple[int, str]] = []
    for pos, (indentazione, nome, riga) in enumerate(chiavi):
        while pila and pila[-1][0] >= indentazione:
            pila.pop()
        e_contenitore = pos + 1 < len(chiavi) and chiavi[pos + 1][0] > indentazione
        if e_contenitore:
            pila.append((indentazione, nome))
            continue
        out.append((".".join([n for _, n in pila] + [nome]), riga))
    return out


def _chiavi_lette_da_run_sh(run_sh: Path) -> set[str]:
    """Chiavi che `run.sh` legge con bashio::config, come percorsi puntati.

    Il ponte fra le opzioni dell'add-on e il codice e' run.sh: legge
    `bashio::config 'log_level'` e ne esporta LOG_LEVEL. Il Python vede solo la
    variabile d'ambiente e non nomina mai l'opzione, quindi cercarla nel solo
    Python dichiarerebbe morta quasi ogni opzione dell'add-on.

    Ora che _opzioni_addon restituisce percorsi puntati completi, il confronto
    avviene sui percorsi interi: nessuna scomposizione in segmenti.
    """
    if not run_sh.exists():
        return set()
    chiavi: set[str] = set()
    for percorso in _RE_BASHIO.findall(_leggi(run_sh)):
        chiavi.add(percorso)
    return chiavi


def censisci_configurazione(
    config_yaml: Path, run_sh: Path, file_app: list[Path]
) -> list[Reperto]:
    """Opzioni che nessuno legge, e variabili d'ambiente che nessuno esporta."""
    testi = [_senza_commenti(_leggi(f)) for f in file_app]
    reperti: list[Reperto] = []

    da_run_sh = _chiavi_lette_da_run_sh(run_sh)
    corpo = "".join(testi)
    for percorso, riga in _opzioni_addon(config_yaml):
        if percorso in da_run_sh:
            continue
        if f'"{percorso}"' in corpo or f"'{percorso}'" in corpo:
            continue
        reperti.append(Reperto("opzione-mai-letta", percorso,
                               f"{_rel(config_yaml)}:{riga}"))

    esportate = set(_RE_EXPORT.findall(_leggi(run_sh))) if run_sh.exists() else set()
    lette: dict[str, str] = {}
    for f, testo in zip(file_app, testi):
        for m in _RE_ENV.finditer(testo):
            lette.setdefault(m.group(1), f"{_rel(f)}:{_riga(testo, m.start())}")

    for nome, dove in sorted(lette.items()):
        if nome not in esportate:
            reperti.append(Reperto("envvar-mai-esportata", nome, dove,
                                   "il codice la legge, run.sh non la esporta: e' una costante"))
    return reperti


# ── Rotte HTTP ──────────────────────────────────────────────────────────────

_RE_ADD = re.compile(
    r"""add_(get|post|put|delete|patch|head)\(\s*["']([^"']+)["']"""
)
_RE_ADD_ROUTE = re.compile(
    r"""add_route\(\s*["'](\w+)["']\s*,\s*["']([^"']+)["']"""
)


def _file_frontend() -> list[Path]:
    base = APP / "static"
    if not base.exists():
        return []
    return sorted(
        p for p in base.rglob("*")
        if p.suffix in {".js", ".html", ".css"} and "node_modules" not in p.parts
    )


def censisci_rotte(
    file_app: list[Path], file_frontend: list[Path], file_test: list[Path]
) -> list[Reperto]:
    """Rotte registrate confrontate con chi le nomina altrove.

    Il corpus di ricerca esclude le registrazioni stesse: altrimenti ogni
    rotta risulterebbe citata almeno una volta, da se'.
    """
    rotte: dict[str, str] = {}
    corpus_app: list[str] = []

    for f in file_app:
        testo = _leggi(f)
        for m in _RE_ADD.finditer(testo):
            rotte.setdefault(m.group(2), f"{_rel(f)}:{_riga(testo, m.start())}")
        for m in _RE_ADD_ROUTE.finditer(testo):
            rotte.setdefault(m.group(2), f"{_rel(f)}:{_riga(testo, m.start())}")
        corpus_app.append(_RE_ADD_ROUTE.sub(" ", _RE_ADD.sub(" ", testo)))

    fuori = "\n".join(corpus_app + [_leggi(f) for f in file_frontend])
    nei_test = "\n".join(_leggi(f) for f in file_test)

    reperti: list[Reperto] = []
    for percorso, dove in sorted(rotte.items()):
        # Una rotta parametrica si cerca per il pezzo che precede il primo
        # segnaposto: il frontend la compone a pezzi e il percorso completo
        # non compare mai per intero.
        ago = percorso.split("{")[0].rstrip("/")
        if not ago or ago in {"/api", "/"}:
            continue
        # Il frontend scrive le rotte sia con che senza slash iniziale
        ago_senza_slash = ago.lstrip("/")
        if ago in fuori or ago_senza_slash in fuori:
            continue
        if ago in nei_test or ago_senza_slash in nei_test:
            reperti.append(Reperto("rotta-solo-test", percorso, dove,
                                   "la esercitano solo i test"))
        else:
            reperti.append(Reperto("rotta-senza-chiamanti", percorso, dove))
    return reperti


# ── Report ──────────────────────────────────────────────────────────────────

def stampa(reperti: list[Reperto]) -> None:
    per_categoria: dict[str, list[Reperto]] = {}
    for r in reperti:
        per_categoria.setdefault(r.categoria, []).append(r)

    for categoria, titolo in _TITOLI.items():
        gruppo = per_categoria.get(categoria, [])
        if not gruppo:
            print(f"{_VERDE}  0{_RESET}  {titolo}")
            continue
        print(f"\n{_GIALLO}{len(gruppo):>3}{_RESET}  {titolo}")
        for r in sorted(gruppo, key=lambda x: x.nome):
            nota = f"  {_GRIGIO}{r.nota}{_RESET}" if r.nota else ""
            print(f"       {r.nome}  {_GRIGIO}({r.dove}){_RESET}{nota}")

    print(f"\nTotale reperti: {len(reperti)}")


def run() -> int:
    file_app = _file_py(APP)
    reperti = censisci_tabelle(file_app)
    reperti += censisci_configurazione(
        ROOT / "hiris" / "config.yaml", ROOT / "hiris" / "run.sh", file_app
    )
    reperti += censisci_rotte(file_app, _file_frontend(), _file_py(TESTS))
    stampa(reperti)
    return 0


def main() -> None:
    argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    ).parse_args()
    sys.exit(run())


if __name__ == "__main__":
    main()
