"""VISIBILITA' con la causa e IDENTITA': due domande della casa, una regola
ciascuna (Tappa 3, Task 5, 04/10/2026; B-01, B-02, B-05, B-06, A-16; D1, D7).

La regola del fuori vive in `topology.visibility_classes`, e il cancello
`tests/test_fonte_unica.py` (regola `regola-del-fuori`) vieta di riscriverla
altrove. Qui si prova cio' che la regola dice: la classe, la causa che Home
Assistant ha scritto, la precedenza, e cosa conta ogni porta (D7). Il nome:
cio' che Home Assistant mostra, poi il registro, poi l'id (D1 «vivo»), e per i
dispositivi il nome, altrimenti l'id (A-16).

Mutazioni ESEGUITE (04/10/2026), ognuna ripristinata e verificata con
`git status`:

- `reader._entity` senza `disabilitata_da` -- rossa
  `test_la_classe_porta_la_causa_che_home_assistant_ha_scritto` (la causa
  esce `None`);
- `topology.live_name` col nome del registro prima di quello vivo -- rosse
  `test_il_nome_di_un_entita_e_quello_che_home_assistant_mostra` e le prove
  di `guarda` in `test_queries.py`;
- la partizione di `topology.hierarchy` riscritta in linea con
  `entity.get("disabilitata")` in `briefing.py` -- rossa
  `test_fonte_unica.py::test_nessun_doppione_nuovo` (`briefing.py conta 1 in
  piu'`);
- il conteggio di servizio del nucleo tornato a `visibility_classes` (tutte le
  classi, non la prima) -- rossa
  `test_il_nucleo_conta_una_nascosta_di_servizio_una_volta_sola`;
- `House.select` che ammette la classe e non tutte le classi -- rossa
  `test_search_tiene_fuori_una_nascosta_di_servizio_se_ammetti_solo_le_nascoste`.
"""
from __future__ import annotations

from datetime import UTC

import pytest

from hiris.app.home_space import briefing
from hiris.app.home_space.house import House
from hiris.app.home_space.house_query import HouseFilters
from hiris.app.home_space.queries import view
from hiris.app.home_space.reader import build_home_space
from hiris.app.home_space.render import render_behavior
from hiris.app.home_space.topology import Mirror, visibility
from tests.test_briefing import compose


def _riga(entity_id: str, **campi) -> dict:
    """Una riga grezza del registro delle entita', come la manda HA."""
    return {"entity_id": entity_id, "platform": "prova", "name": None,
            "original_name": None, "area_id": None, "device_id": None,
            "entity_category": None, "disabled_by": None, "hidden_by": None,
            **campi}


def _casa(*righe, dispositivi=()) -> dict:
    return build_home_space({"entita": list(righe), "dispositivi": list(dispositivi)})


# --- VISIBILITA' ----------------------------------------------------------

def test_la_classe_porta_la_causa_che_home_assistant_ha_scritto():
    """`disabled_by` e `hidden_by` arrivano fino alla classe: il lettore non
    li riduce piu' a 1/0 (B-25 comincia qui; la fonte intera e' del Task 8)."""
    casa = House(_casa(
        _riga("light.spenta_da_me", disabled_by="user"),
        _riga("light.spenta_da_lei", disabled_by="integration"),
        _riga("light.nascosta", hidden_by="user"),
        _riga("sensor.batteria", entity_category="diagnostic"),
        _riga("light.viva")), Mirror())
    assert casa.visibility("light.spenta_da_me") == ("disabilitata", "user")
    assert casa.visibility("light.spenta_da_lei") == ("disabilitata", "integration")
    assert casa.visibility("light.nascosta") == ("nascosta", "user")
    assert casa.visibility("sensor.batteria") == ("servizio", "diagnostic")
    assert casa.visibility("light.viva") == ("visibile", None)


def test_un_id_che_l_anagrafe_non_conosce_non_e_visibile():
    assert House(_casa(_riga("light.viva")), Mirror()).visibility("light.altra") is None


def test_la_precedenza_e_disabilitata_nascosta_servizio():
    casa = House(_casa(
        _riga("sensor.tutto", disabled_by="user", hidden_by="integration",
              entity_category="config"),
        _riga("sensor.nascosta_di_servizio", hidden_by="user", entity_category="config")),
        Mirror())
    assert casa.visibility("sensor.tutto") == ("disabilitata", "user")
    assert casa.visibility("sensor.nascosta_di_servizio") == ("nascosta", "user")


def test_una_voce_scritta_a_mano_ha_la_classe_senza_causa():
    """Un'anagrafe senza le cause (una prova, una forma vecchia): la classe
    resta, la causa tace. Non si inventa."""
    assert visibility({"id": "light.a", "disabilitata": 1}) == ("disabilitata", None)


def test_la_gerarchia_mette_ogni_classe_nella_sua_chiave():
    """La partizione chiede la classe: disabilitate e nascoste a parte, le
    visibili e quelle di servizio in `entita` (che conta)."""
    home_space = {"aree": [{"id": "cucina", "nome": "Cucina"}], "entita": [
        {"id": "light.v", "area_id": "cucina"},
        {"id": "sensor.s", "area_id": "cucina", "categoria": "diagnostic"},
        {"id": "light.n", "area_id": "cucina", "nascosta": 1},
        {"id": "light.d", "area_id": "cucina", "disabilitata": 1, "nascosta": 1}]}
    area = House(home_space, Mirror()).hierarchy()[0]["aree"][0]
    assert {e["id"] for e in area["entita"]} == {"light.v", "sensor.s"}
    assert {e["id"] for e in area["entita_nascoste"]} == {"light.n"}
    assert {e["id"] for e in area["entita_disabilitate"]} == {"light.d"}


def _scegli(casa: House, **filtri):
    return casa.select(HouseFilters(**filtri), ("entita",), [], now=0.0)


def test_search_tiene_fuori_una_nascosta_di_servizio_se_ammetti_solo_le_nascoste():
    """D7: ogni porta dichiara le classi che conta, e un'entita' fuori per due
    ragioni resta fuori finche' la porta non le ammette entrambe. Contata
    sotto la PRIMA che la porta non ammette."""
    casa = House(_casa(_riga("sensor.n_s", hidden_by="user", entity_category="config")),
                 Mirror())
    nessuna = _scegli(casa)
    assert not nessuna.entities and nessuna.excluded["nascoste"] == 1
    solo_nascoste = _scegli(casa, include_hidden=True)
    assert not solo_nascoste.entities and solo_nascoste.excluded["servizio"] == 1
    entrambe = _scegli(casa, include_hidden=True, include_service=True)
    assert [e["id"] for e, _a, _w in entrambe.entities] == ["sensor.n_s"]


def _core_text(home_space: dict) -> str:
    testo, _meta = compose(home_space, [], [], {})
    return testo


def test_il_nucleo_conta_una_nascosta_di_servizio_una_volta_sola():
    """D7, il cambio dichiarato: fino al 04/10/2026 un'entita' nascosta E di
    servizio entrava in tutti e due i conteggi del nucleo, e la somma delle
    righe superava le entita' vere. Ora e' fra le nascoste, come in `search`."""
    home_space = _casa(_riga("sensor.n_s", hidden_by="user", entity_category="config"),
                       _riga("sensor.s", entity_category="diagnostic"))
    testo = _core_text(home_space)
    assert "1 entità nascosta" in testo
    assert "1 entità di servizio" in testo


# --- IDENTITA' ------------------------------------------------------------

def test_il_nome_di_un_entita_e_quello_che_home_assistant_mostra():
    casa = House(_casa(_riga("light.a", name="Piantana"), _riga("light.b"),
                       _riga("light.c")),
                 Mirror(names={"light.a": "Soggiorno Piantana", "light.b": "Abat-jour"}))
    assert casa.name("entita", "light.a") == "Soggiorno Piantana"
    assert casa.name("entita", "light.b") == "Abat-jour"
    assert casa.name("entita", "light.c") == "light.c"


def test_senza_specchio_il_nome_e_quello_del_registro():
    casa = House(_casa(_riga("light.a", name="Piantana")), Mirror())
    assert casa.name("entita", "light.a") == "Piantana"


def test_un_automazione_senza_nome_esce_col_suo_id_da_search_come_dalla_storia():
    """D1: `search` la rendeva con `nome: null` e la storia col suo id."""
    riga = render_behavior(House({}, Mirror()),
                           {"id": "automation.x", "nome": None, "tipo": "automazione"},
                           "corta", zone=UTC)
    assert riga["nome"] == "automation.x"
    casa = House({}, Mirror(names={"automation.y": "Luci del giardino"}))
    assert casa.name("automazione", "automation.y") == "Luci del giardino"


def test_un_dispositivo_si_chiama_col_nome_altrimenti_con_l_id():
    """A-16: il ripiego era `None`, assente, `""` o l'id a seconda della
    porta. Ora e' uno, e `guarda` lo usa."""
    casa = House(_casa(dispositivi=[{"id": "dev_a", "name": "Irrigatore"},
                                    {"id": "dev_b", "name": None, "name_by_user": None}]),
                 Mirror())
    assert casa.name("dispositivo", "dev_a") == "Irrigatore"
    assert casa.name("dispositivo", "dev_b") == "dev_b"
    assert casa.name("dispositivo", "dev_z") is None
    assert view(casa, [], [], "dispositivo", "dev_b")["nome"] == "dev_b"


def test_il_nucleo_marca_ancora_come_id_un_dispositivo_senza_nome():
    entita = [{"id": f"valve.v{n}", "dispositivo_id": "dev9"} for n in range(3)]
    assert briefing._device_annotation(entita, "valve", 3, {"dev9": "dev9"}.get) == " (id: dev9)"
    assert briefing._device_annotation(entita, "valve", 3, {"dev9": "Irrigatore"}.get) == \
        " (Irrigatore)"


def test_un_genere_che_la_casa_non_conosce_e_un_errore_non_un_silenzio():
    with pytest.raises(ValueError):
        House({}, Mirror()).name("integrazione", "hue")


# Le parole delle classi che nel prodotto compaiono scritte a mano per un'altra
# ragione: (file, forma, parola) -> perche'. Una lista di AMMISSIONE: una voce
# nuova e' vietata finche' qualcuno non la scrive qui con la ragione, e una
# voce che non trova piu' niente nel prodotto fa arrossire la prova.
_COLLISIONI = {
    ("action/actuator.py", "chiave", "servizio"): "il servizio di una chiamata",
    ("action/journal.py", "chiave", "servizio"): "il servizio di una chiamata",
    ("action/journal.py", "elemento", "servizio"): "la colonna della cronaca",
    ("home_space/house_history.py", "chiave", "servizio"): "il servizio di un atto",
    ("home_space/tools.py", "chiave", "servizio"): "il parametro dello strumento",
    ("keeper/promise.py", "chiave", "servizio"): "il servizio di una chiamata",
    ("home_space/reader.py", "chiave", "disabilitata"): "la colonna dell'anagrafe",
    ("home_space/reader.py", "chiave", "nascosta"): "la colonna dell'anagrafe",
    ("home_space/field_vocabulary.py", "elemento", "disabilitata"): "il campo dell'anagrafe",
    ("home_space/field_vocabulary.py", "elemento", "nascosta"): "il campo dell'anagrafe",
    ("home_space/house_query.py", "chiave", "servizio"):
        "la chiave delle escluse (`house._EXCLUDED_KEY`), non la classe",
    ("home_space/house_query.py", "elemento", "nascosta"): "la parola di una frase",
    ("home_space/house_query.py", "elemento", "disabilitata"): "la parola di una frase",
}


def _handwritten_classes() -> set[tuple[str, str, str, int]]:
    """Dove il prodotto scrive a mano il valore di una classe: confronti
    (anche dentro una tupla o un insieme), chiavi di dizionario, elementi di
    tupla e di insieme. Si guarda l'albero, non il testo (N159-1)."""
    import ast
    from pathlib import Path

    from hiris.app.home_space import topology

    valori = {*topology.OUTSIDE_CLASSES, topology.VISIBLE}
    assert len(valori) == 4

    def parola(nodo):
        return isinstance(nodo, ast.Constant) and nodo.value in valori

    def dentro(nodo):
        if parola(nodo):
            return [nodo]
        if isinstance(nodo, (ast.Tuple, ast.Set, ast.List)):
            return [e for e in nodo.elts if parola(e)]
        return []

    prodotto = Path(topology.__file__).resolve().parents[1]
    trovati = set()
    for sorgente in prodotto.rglob("*.py"):
        if sorgente.name == "topology.py":
            continue
        nome = sorgente.relative_to(prodotto).as_posix()
        for nodo in ast.walk(ast.parse(sorgente.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Compare):
                colpiti = [("confronto", c) for o in (nodo.left, *nodo.comparators)
                           for c in dentro(o)]
            elif isinstance(nodo, ast.Dict):
                colpiti = [("chiave", k) for k in nodo.keys if k is not None and parola(k)]
            elif isinstance(nodo, (ast.Tuple, ast.Set)):
                colpiti = [("elemento", e) for e in nodo.elts if parola(e)]
            else:
                continue
            trovati |= {(nome, forma, c.value, c.lineno) for forma, c in colpiti}
    return trovati


def test_le_classi_del_fuori_si_confrontano_con_le_costanti_di_topology():
    """N158-1 e N159-1 (giri 158 e 159, 14/10/2026): le classi hanno un nome
    in `topology` (`DISABLED`, `HIDDEN`, `SERVICE`, piu' `VISIBLE`), e chi le
    confronta o ne fa una chiave lo importa. I valori si chiedono a
    `topology`; le collisioni vere stanno in `_COLLISIONI`, con la ragione.

    Mutazioni ESEGUITE: `!= "disabilitata"` rimesso in `tools.py`, e
    `cls not in ("disabilitata", "nascosta")` in `queries.py` -- rosse. La
    seconda la prova a testo del giro 158 non la vedeva."""
    trovati = _handwritten_classes()
    fuori = sorted(t for t in trovati if t[:3] not in _COLLISIONI)
    assert not fuori, fuori


def test_ogni_collisione_ammessa_esiste_ancora():
    """La lista di ammissione puo' solo calare: una voce che non trova piu'
    niente e' una porta lasciata aperta per niente."""
    vive = {t[:3] for t in _handwritten_classes()}
    assert not set(_COLLISIONI) - vive, sorted(set(_COLLISIONI) - vive)
