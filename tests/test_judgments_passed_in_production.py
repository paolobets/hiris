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

FUNZIONI = {"aggregate_day", "build_episodes", "rebuild_chronicle", "compose", "view",
            "_view_detail", "commands_for", "ToolDispatcher",
            # La catena interna, dal giro di correzioni 1 (punto 4): sono
            # funzioni con lo stesso predefinito `REPO_JUDGMENTS`, e un inoltro
            # dimenticato a meta' strada e' la stessa ricaduta silenziosa.
            "genre_for", "_is_event", "_highlight_lines", "_view_entity",
            "_command_parameters", "_limits_of_entity"}
RADICE = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"


def test_ogni_chiamata_di_produzione_passa_l_istantanea():
    mancanti = []
    for path in RADICE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in FUNZIONI and not any(k.arg == "judgments" for k in node.keywords):
                mancanti.append(f"{path.relative_to(RADICE)}:{node.lineno} {name}(")
    assert not mancanti, "\n".join(mancanti)
