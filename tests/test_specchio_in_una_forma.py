"""Lo specchio dello stato in UNA forma (B-41, A-25; Tappa 3, Task 3).

Fino al 04/10/2026 lo specchio aveva tre forme -- la tupla di sei dizionari
di `topology.live_mirror`, la settupla di `ToolDispatcher._mirror` (con
`letto` in coda) e sei argomenti separati nelle firme di `queries.view` -- e
chi lo riceveva lo leggeva per posizione: `mirror[1]` i nomi, `mirror[5]` gli
attributi. «Leggibile» si componeva a mano cinque volte in `tools.py`
(`letto and inventory_is_readable(cache)`), e la guardia di `_mirror` diceva
«letto» con la cache assente mentre `inventory_is_readable` diceva falso.

Qui si prova la proprieta', non la forma: (1) lo specchio ha i campi per
nome; (2) `readable` si calcola in un posto, `topology.read_mirror`, e dice
la stessa cosa nei quattro casi che i chiamanti distinguevano; (3) nessuno
nel prodotto indicizza uno specchio per posizione.

**La prova (3) chiede i suoi file** alla cartella `hiris/app` (non un elenco
a mano), e una seconda prova verifica che la derivazione non si sia
svuotata. Cosa conta come «specchio»: un nome, un attributo o una chiamata che
contiene `mirror`. Indicizzare con un intero (o una fetta), o spacchettare
in una tupla, e' il difetto: una `Mirror` non e' una tupla, quindi `mirror[1]` solleverebbe
comunque -- ma solo sul ramo che lo esegue, e la prova lo vede prima.

Rosso visto il 04/10/2026 su `7deaaaed` (prima del codice):
`ImportError: cannot import name 'Mirror'` per le prove (1) e (2), e per la
(3) diciannove letture per posizione: undici indici o fette (fra cui
`house_history.py:335`, `mirror[1]`, e `handlers_mind.py:446`,
`live_mirror(...)[1]`) e otto spacchettamenti (`tools.py`, `house_query.py`,
`handlers_home_space.py`, `topology.py`).

Mutazioni ESEGUITE il 04/10/2026, ognuna ripristinata (`git status`):
- rimesso `names = mirror[1]` in `house_history.choose` -- rossa la (3),
  «home_space/house_history.py:335: mirror[1]»;
- `read_mirror` che restituisce lo specchio senza chiedere
  `inventory_is_readable` -- rossa la (2), `readable` vero su una cache mai
  caricata.
"""
import ast
from pathlib import Path

from hiris.app.home_space.topology import Mirror, live_mirror, read_mirror

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"

ROWS = [{"id": "light.cucina", "state": "on", "name": " Luce cucina ",
         "unit": "", "device_class": "", "last_changed": "2026-10-01T10:00:00+00:00"},
        {"id": "sensor.t", "state": "21.5", "name": "Temperatura", "unit": "°C",
         "device_class": "temperature", "last_changed": "2026-10-01T09:00:00+00:00",
         "attributes": {"values": {"precision": 1}}, "state_class": "measurement"}]


class _Cache:
    def __init__(self, rows, *, loaded=True, broken=False):
        self._rows, self.loaded, self._broken = rows, loaded, broken

    def all_states(self):
        if self._broken:
            raise RuntimeError("specchio guasto")
        return self._rows


def test_lo_specchio_ha_i_campi_per_nome():
    mirror = live_mirror(ROWS)
    assert isinstance(mirror, Mirror)
    assert mirror.state == {"light.cucina": "on", "sensor.t": "21.5"}
    assert mirror.names == {"light.cucina": "Luce cucina", "sensor.t": "Temperatura"}
    assert mirror.units == {"sensor.t": "°C"}
    assert mirror.classes == {"sensor.t": "temperature"}
    assert mirror.since["light.cucina"] == "2026-10-01T10:00:00+00:00"
    assert mirror.attributes == {"sensor.t": {"values": {"precision": 1}}}
    # Dal Task 4: lo `state_class`, che la storia leggeva dalle righe grezze.
    assert mirror.state_classes == {"sensor.t": "measurement"}
    assert mirror.readable is True


def test_leggibile_si_calcola_in_un_posto_e_dice_la_stessa_cosa_dei_chiamanti():
    # Cache assente: fino al 04/10 `_mirror` diceva «letto», e ogni chiamante
    # lo correggeva con `inventory_is_readable`, che diceva falso.
    assert read_mirror(None) == Mirror(readable=False)
    # Una finta che non e' uno specchio vale come assente.
    assert read_mirror(object()).readable is False
    # Lettura che solleva: niente dizionari, e non leggibile.
    assert read_mirror(_Cache(ROWS, broken=True)) == Mirror(readable=False)
    # Mai caricata: cio' che c'e' resta (le entita' mosse dagli eventi), ma
    # non vale come fotografia della casa.
    unloaded = read_mirror(_Cache(ROWS, loaded=False))
    assert unloaded.readable is False and unloaded.state["sensor.t"] == "21.5"
    # Caricata: lo specchio intero.
    loaded = read_mirror(_Cache(ROWS))
    assert loaded == live_mirror(ROWS) and loaded.readable is True


def _is_mirror(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        return "mirror" in name.lower()
    if isinstance(node, ast.Name):
        return "mirror" in node.id.lower()
    if isinstance(node, ast.Attribute):
        return "mirror" in node.attr.lower()
    return False


def _sources() -> list[Path]:
    return sorted(APP.rglob("*.py"))


def _positional_reads() -> list[str]:
    found = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # Lo spacchettamento e' una lettura per posizione come l'indice:
            # `stato, nomi, ... = mirror`.
            if isinstance(node, ast.Assign) and _is_mirror(node.value) \
                    and any(isinstance(target, ast.Tuple) for target in node.targets):
                found.append(f"{path.relative_to(APP)}:{node.lineno}: "
                             f"{ast.unparse(node.targets[0])} = ...")
                continue
            if not isinstance(node, ast.Subscript) or not _is_mirror(node.value):
                continue
            index = node.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, int) \
                    or isinstance(index, ast.Slice):
                found.append(f"{path.relative_to(APP)}:{node.lineno}: "
                             f"{ast.unparse(node)}")
    return found


def test_la_derivazione_guarda_il_prodotto():
    sources = _sources()
    assert len(sources) > 100, len(sources)
    names = {path.name for path in sources}
    assert {"tools.py", "house_query.py", "house_history.py",
            "handlers_mind.py"} <= names, names


def test_nessuno_legge_lo_specchio_per_posizione():
    assert _positional_reads() == []
