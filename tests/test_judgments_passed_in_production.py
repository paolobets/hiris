"""D3: il default `REPO_JUDGMENTS` e' per le prove e per il censore. In
produzione ogni chiamata **nominata in `FUNZIONI`** deve portare `judgments=`,
o una correzione della casa non arriverebbe e nessuno lo vedrebbe.

**Cosa controlla, per davvero.** La prova qui sotto guarda ogni `ast.Call` di
tutto `hiris/app` il cui nome (o attributo) e' in `FUNZIONI`, e pretende che
porti il keyword `judgments=` scritto a mano su QUELLA riga. Non sa e non puo'
sapere se il valore passato sia quello giusto.

**`FUNZIONI` copre ora anche la catena interna** (giro di correzioni 1, punto 4).
Fino al 17/09/2026 elencava solo le funzioni di testa: `genre_for` -- che ha il
predefinito `REPO_JUDGMENTS` come tutte le altre (`mind/facts.py`) -- e le
foglie `_is_event`, `_highlight_lines`, `_view_entity`, `_command_parameters`,
`_limits_of_entity` non c'erano, e una frase qui diceva il falso sostenendo che
le chiamate interne fossero controllate. La revisione di Fable del fix round 1
l'aveva presa eseguendo la mutazione contraria (tolto `judgments=judgments` dalla
chiamata `_highlight_lines(` dentro `compose`: il test resto' **verde**). Con
l'insieme allargato quella stessa mutazione **arrossisce**, ed e' stata
rieseguita. Allargarlo non ha scoperto nessuna chiamata mancante: era copertura
che mancava, non un difetto.

**Resta cio' che questa prova non puo' fare**: guarda il keyword su una riga,
non il valore che ci passa. La proprieta' vera -- che una correzione della casa
arrivi in fondo alla catena -- la difendono due prove **dal lettore**:
`tests/test_briefing.py::
test_una_correzione_su_notevole_arriva_dal_nucleo_intero_non_solo_da_is_event`
(la catena `compose -> _highlight_lines -> _is_event`) e
`tests/test_queries.py::
test_una_correzione_su_limiti_arriva_dalla_vista_intera_non_solo_dalla_foglia`
(la catena `view -> _view_entity -> commands_for -> _command_parameters ->
_limits_of_entity`): chiamano la funzione di TESTA con un'istantanea diversa
dal seme e guardano il TESTO/DETTAGLIO finale, non solo il keyword scritto a
una riga.

Mutazione ESEGUITA: tolto `judgments=` dalla chiamata `compose(` in
`api/handlers_home_space.py` -- rossa, con file e riga nel messaggio;
ripristinato con l'editor (verificato che `git diff` dopo il ripristino
mostri solo le righe volute di questa fetta, nessuna persa -- non c'e' nessun
commit, quindi niente `git status` da dire "pulito").

**`ToolDispatcher` in `FUNZIONI`.** Il costruttore riceve `judgments=None`
(Task 5, `tools.py::ToolDispatcher.__init__`) con una ricaduta interna su
`REPO_JUDGMENTS` quando e' `None` -- la stessa forma degli altri archivi
opzionali della classe (`cache`, `actuator`, ...). Perche' quella ricaduta non
sia la stessa ricaduta silenziosa che questo test esiste per vietare, il suo
UNICO sito di costruzione di produzione deve essere sorvegliato qui esattamente
come `compose`/`view`: e' per questo che `ToolDispatcher` e' nell'insieme,
anche se il piano non lo elencava per nome -- senza, il default della classe
sarebbe garantito da niente.

**`rebuild_chronicle` in `FUNZIONI`.** E' nata con il Task 6 (spec §6,
«l'impronta e la cronaca rifatta», `mind/facts.py`); il Task 5 l'aveva messa
nell'insieme prima che esistesse, perche' il nome era gia' deciso dalla spec.
Oggi la sua sola chiamata di produzione e' in `server.py::backfill_one_report`,
e porta `judgments=`. Mutazione ESEGUITA dal Task 6: tolto `judgments=` da
quella chiamata -- rossa, con file e riga; ripristinato con l'editor.
"""
import ast
import pathlib

#: Le funzioni sorvegliate si CHIEDONO al codice, non si elencano (I-0,
#: 21/09/2026). L'elenco scritto a mano era gia' invecchiato: `as_page`,
#: `_front_page_mark`, `_is_on`, `_status` e `chronicle_is_stale` ricevono
#: `judgments` e non erano sorvegliate -- due delle cinque erano nate tre
#: giorni prima. Un elenco che ricopia una firma non regge il ritmo di chi
#: scrive codice.
#:
#: **La firma e' il fatto**: chi dichiara di ricevere `judgments` deve essere
#: chiamato con `judgments=`. Una funzione nuova entra qui il giorno in cui
#: nasce.
RADICE = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"


def funzioni_sorvegliate() -> frozenset[str]:
    """Chi DICHIARA di ricevere `judgments`, derivato dalle firme.

    Per un costruttore vale il nome della CLASSE, che e' quello che si legge
    al sito di costruzione (`ToolDispatcher(...)`, non `__init__(...)`).
    """
    nomi = set()
    for percorso in RADICE.rglob("*.py"):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.ClassDef):
                for figlio in nodo.body:
                    if (isinstance(figlio, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and figlio.name == "__init__"
                            and _riceve_giudizi(figlio)):
                        nomi.add(nodo.name)
            elif (isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and nodo.name != "__init__" and _riceve_giudizi(nodo)):
                nomi.add(nodo.name)
    assert len(nomi) > 10, (
        f"ne ho derivate solo {len(nomi)}: la derivazione si e' rotta, e un "
        "cancello che deriva male sembra vivo mentre non guarda piu' niente")
    return frozenset(nomi)


def _riceve_giudizi(nodo) -> bool:
    return "judgments" in [a.arg for a in nodo.args.args + nodo.args.kwonlyargs]


def posizioni_giudizi() -> dict[str, set[int]]:
    """Per ogni funzione sorvegliata, in che POSIZIONE sta `judgments`.

    Serve perche' la proprieta' da difendere e' che l'istantanea **arrivi**,
    non che sia scritta in una forma. Sette chiamate di produzione la passano
    per posizione, e sono corrette: pretendere la parola chiave le direbbe
    sbagliate e spingerebbe a cambiare codice che funziona per far tacere un
    cancello -- il modo piu' rapido di insegnare a non fidarsi dei cancelli.

    `None` fra gli indici vuol dire «solo per nome» (parametro dopo `*`): li'
    la parola chiave e' l'unica forma possibile.
    """
    posizioni: dict[str, set] = {}
    for percorso in RADICE.rglob("*.py"):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            corpo = ([(nodo.name, f) for f in nodo.body
                      if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and f.name == "__init__"]
                     if isinstance(nodo, ast.ClassDef) else
                     [(nodo.name, nodo)]
                     if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and nodo.name != "__init__" else [])
            for nome, funzione in corpo:
                if not _riceve_giudizi(funzione):
                    continue
                nomi_posizionali = [a.arg for a in funzione.args.args]
                indice = (nomi_posizionali.index("judgments")
                          if "judgments" in nomi_posizionali else None)
                # `self` non si conta: al sito di chiamata non si scrive
                if indice is not None and nomi_posizionali[:1] == ["self"]:
                    indice -= 1
                posizioni.setdefault(nome, set()).add(indice)
    return posizioni


def test_ogni_chiamata_di_produzione_passa_l_istantanea():
    sorvegliate = funzioni_sorvegliate()
    posizioni = posizioni_giudizi()
    mancanti = []
    for path in RADICE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in sorvegliate:
                continue
            # Per NOME o per POSIZIONE: cio' che conta e' che l'istantanea
            # arrivi, non la forma in cui e' scritta.
            per_nome = any(k.arg == "judgments" for k in node.keywords)
            per_posizione = any(i is not None and len(node.args) > i
                                for i in posizioni.get(name, set()))
            if not (per_nome or per_posizione):
                mancanti.append(f"{path.relative_to(RADICE)}:{node.lineno} {name}(")
    assert not mancanti, "\n".join(mancanti)
