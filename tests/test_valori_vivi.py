"""Nessuna scrittura in `app[...]` dopo l'avvio (X-31, Chiusura dello sprint).

aiohttp congela l'app quando l'avvio finisce: da li' scrivere in `app[...]`
emette «Changing state of started or joined application is deprecated», e in
aiohttp 4 e' un errore. Fino al 14/10/2026 il prodotto lo faceva in piu' di
quindici punti (le rotte dei modelli, delle impostazioni e dei giudizi, i giri
dei problemi, delle integrazioni, del confronto, della catena e del ponte, il
lucchetto pigro di S-30). Adesso il valore che cambia vive in un `LiveValue`
(`hiris/app/live_value.py`) che l'app porta da `create_app`, e chi lo cambia
chiama `set`.

**Il cancello, chiesto al sorgente.** Chi puo' scrivere in `app[...]` lo dice
`create_app`: le funzioni che chiama, quelle che registra in `on_startup`, e
quelle che queste chiamano a loro volta. Ogni altra funzione del prodotto che
scrive in `app` (con `app[...] =`, `del`, `setdefault`, `pop`, `update`,
`clear`) e' un difetto; e lo e' anche una funzione ammessa che qualcuno
richiama fuori dall'avvio, perche' allora scrive anche ad app congelata.

**Cosa non vede, dichiarato.** Le funzioni si riconoscono per nome: due
funzioni omonime in moduli diversi si confondono (misurato il 14/10/2026:
nessuna fra quelle ammesse). Un'app con un altro nome (`casa`, `ctx`) non e'
vista, come in `tests/test_chiavi_app.py`. La scrittura in un `LiveValue`
(`app[K].set(...)`) non e' una scrittura in `app`, ed e' il punto.
"""
import ast
import pathlib

RADICE = pathlib.Path(__file__).resolve().parents[1]
APP = RADICE / "hiris" / "app"
SCRITTURE = ("setdefault", "pop", "update", "clear", "popitem")


def _is_app(nodo: ast.AST) -> bool:
    if isinstance(nodo, ast.Name):
        return nodo.id in ("app", "application") or nodo.id.endswith("_app")
    return isinstance(nodo, ast.Attribute) and nodo.attr == "app"


def _corpo(funzione: ast.AST):
    """I nodi della funzione, senza entrare nelle funzioni annidate: quelle
    girano quando qualcuno le chiama, e si giudicano da sole."""
    pending = list(funzione.body)
    while pending:
        nodo = pending.pop()
        yield nodo
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            pending.extend(ast.iter_child_nodes(nodo))


def _scrive(nodo: ast.AST) -> bool:
    if isinstance(nodo, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
        bersagli = nodo.targets if isinstance(nodo, (ast.Assign, ast.Delete)) else [nodo.target]
        return any(isinstance(parte, ast.Subscript) and _is_app(parte.value)
                   for bersaglio in bersagli for parte in ast.walk(bersaglio))
    return (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr in SCRITTURE and _is_app(nodo.func.value))


def _chiamati(funzione: ast.AST) -> set[str]:
    """I nomi che la funzione chiama, o che passa a `on_startup.append`."""
    nomi = set()
    for nodo in _corpo(funzione):
        if isinstance(nodo, ast.Call):
            if isinstance(nodo.func, ast.Name):
                nomi.add(nodo.func.id)
            if (isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "append"
                    and isinstance(nodo.func.value, ast.Attribute)
                    and nodo.func.value.attr == "on_startup"):
                nomi |= {a.id for a in nodo.args if isinstance(a, ast.Name)}
    return nomi


def leggi(moduli: dict[str, ast.AST]):
    """`(funzioni, ammesse)`: ogni funzione del prodotto per nome, e i nomi che
    possono scrivere in `app` perche' girano mentre l'app si compone."""
    funzioni: dict[str, list[tuple[str, ast.AST]]] = {}
    for dove, albero in moduli.items():
        for nodo in ast.walk(albero):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funzioni.setdefault(nodo.name, []).append((dove, nodo))
    ammesse = {"create_app"}
    for _ in range(2):
        for nome in list(ammesse):
            for _dove, nodo in funzioni.get(nome, []):
                ammesse |= _chiamati(nodo) & funzioni.keys()
    return funzioni, ammesse


def difetti(moduli: dict[str, ast.AST]) -> list[str]:
    funzioni, ammesse = leggi(moduli)
    trovati = []
    for nome, definizioni in sorted(funzioni.items()):
        for dove, nodo in definizioni:
            righe = sorted(n.lineno for n in _corpo(nodo) if _scrive(n))
            if righe and nome not in ammesse:
                trovati.append(f"{dove}:{righe[0]}: {nome} scrive in app[...] dopo l'avvio")
    # Una funzione ammessa che si chiama anche altrove scrive anche ad app
    # congelata: la si cerca in ogni corpo che non e' quello di un'ammessa.
    for nome in sorted(ammesse - {"create_app"}):
        if not any(_scrive(n) for _d, f in funzioni.get(nome, []) for n in _corpo(f)):
            continue
        for chi, definizioni in funzioni.items():
            if chi in ammesse:
                continue
            for dove, nodo in definizioni:
                if nome in _chiamati(nodo):
                    trovati.append(f"{dove}: {chi} richiama {nome}, che scrive in app[...]")
    return trovati


def _moduli() -> dict[str, ast.AST]:
    return {p.relative_to(APP).as_posix(): ast.parse(p.read_text(encoding="utf-8"))
            for p in sorted(APP.rglob("*.py")) if "__pycache__" not in p.parts}


def test_il_cancello_riconosce_le_forme():
    albero = ast.parse(
        "def create_app():\n    app = {}\n    prepara(app)\n"
        "    app.on_startup.append(avvio)\n"
        "def prepara(app):\n    app['a'] = 1\n"
        "async def avvio(app):\n    app.setdefault('b', 2)\n    apri(app)\n"
        "def apri(app):\n    del app['c']\n"
        "async def rotta(request):\n    request.app['d'] = 3\n"
        "def giro(app):\n    app[K].set(4)\n    prepara(app)\n"
        "def ok(app):\n    app.pop('e')\n")
    assert difetti({"prova.py": albero}) == [
        "prova.py:18: ok scrive in app[...] dopo l'avvio",
        "prova.py:13: rotta scrive in app[...] dopo l'avvio",
        "prova.py: giro richiama prepara, che scrive in app[...]"]


def test_nessuna_scrittura_in_app_dopo_l_avvio():
    """Mutazioni ESEGUITE (14/10/2026): (a) `request.app[CHAT_SETTINGS_KEY] =
    updated` rimessa in `handle_save_settings` -- rossa, col file e la riga;
    (b) `prepara_ruoli(request.app)` chiamata da `handle_save_settings` --
    rossa («richiama prepara_ruoli»)."""
    moduli = _moduli()
    funzioni, ammesse = leggi(moduli)
    scrittori = {nome for nome, definizioni in funzioni.items()
                 for _d, nodo in definizioni if any(_scrive(n) for n in _corpo(nodo))}
    # Pavimenti, non conti: sotto, la derivazione si e' rotta e il cancello
    # non guarda piu' niente. Misurati il 14/10/2026: 12 scrittori, tutti
    # ammessi; `_on_startup` e `create_app` fra loro.
    assert {"create_app", "_on_startup"} <= scrittori & ammesse, sorted(scrittori)
    assert len(scrittori) >= 8, sorted(scrittori)
    assert not difetti(moduli), "\n".join(difetti(moduli))
