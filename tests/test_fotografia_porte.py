"""Due scatti sugli stessi ingressi sono identici; un cambio di regola si vede.

La fotografia delle porte e' la garanzia 4 dello sprint «Una fonte sola di
verita'»: prima di toccare una regola si salva cio' che esce oggi da ogni
porta, e dopo o e' identico o la differenza e' quella dichiarata. Vale solo se
lo scatto e' DETERMINISTICO -- stessi ingressi, stesso orologio, stessa uscita
-- e se un cambio vero si vede. Queste prove fissano le due cose.

Mutazione ESEGUITA: in `fotografia_porte.shoot` tolto il blocco dell'orologio
(`with frozen_clock(clock)`) -- rossa (`nucleo` diverso fra due scatti presi a
due orologi diversi).
Mutazione ESEGUITA: in `observer.house_lines` aggiunta in coda una riga con
`datetime.now()` -- rossa nella prova dell'orologio di sistema (`osservatore`
fra le differenze). Senza quella prova lo stesso difetto restava verde: lo
aveva dimostrato la revisione indipendente del 01/10/2026.
Mutazione ESEGUITA: in `topology.actual_area` restituita sempre l'area propria
-- 59 differenze sulla casa sintetica: `selezioni` 27, `strumenti` 18,
`albero` 7, `schede` 4, `nucleo` 3 (confronto fra lo scatto prima e dopo).
"""
import asyncio
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import fotografia_porte
from _casa_sintetica import synthetic_inputs

CLOCK = 1_790_000_000.0


def _shot(inputs=None, clock=CLOCK):
    return fotografia_porte.shoot(inputs or synthetic_inputs(), clock=clock)


@pytest.fixture(scope="module")
def shot():
    return _shot()


def test_due_scatti_sugli_stessi_ingressi_sono_identici(shot):
    assert fotografia_porte.compare(shot, _shot()) == []


def test_lo_scatto_usa_l_orologio_che_gli_si_da(shot):
    # Stessi ingressi, orologio diverso: il nucleo porta l'ora, e deve cambiare.
    # E' la prova che `clock` arriva davvero alle porte (e la guardia della
    # mutazione «tolto `frozen_clock`»: senza, i due scatti leggono l'ora vera
    # e a pochi secondi di distanza coincidono).
    later = fotografia_porte.compare(shot, _shot(clock=CLOCK + 3 * 86_400))
    assert any(line.startswith("nucleo") for line in later), later[:3]


def test_nessuna_porta_legge_l_orologio_di_sistema(shot, monkeypatch):
    """`frozen_clock` ferma `time.time`. Una porta che chiedesse l'ora a
    `datetime.now()` gli sfuggirebbe, e due scatti a un giorno di distanza
    differirebbero senza che il codice sia cambiato. Qui OGNI modulo del
    prodotto che ha importato `datetime` ne riceve uno spostato di un giorno:
    lo scatto deve restare identico."""
    import datetime as real
    import sys as system

    class Tomorrow(real.datetime):
        @classmethod
        def now(cls, tz=None):
            return real.datetime.now(tz) + real.timedelta(days=1)

    shifted = [module for name, module in list(system.modules.items())
               if name.startswith("hiris.app")
               and getattr(module, "datetime", None) is real.datetime]
    assert len(shifted) >= 10, f"moduli del prodotto con `datetime`: {len(shifted)}"
    for module in shifted:
        monkeypatch.setattr(module, "datetime", Tomorrow)
    assert fotografia_porte.compare(shot, _shot()) == []


def test_lo_scatto_copre_tutte_le_porte_dichiarate(shot):
    assert set(shot) == set(fotografia_porte.PORTS)


def test_nessuna_porta_e_vuota(shot):
    empty = sorted(name for name, content in shot.items() if not content)
    assert not empty, f"porte che non hanno fotografato niente: {empty}"


def test_gli_strumenti_rispondono_e_non_dichiarano_errori(shot):
    failed = {call: answer["errore"] for call, answer in shot["strumenti"].items()
              if isinstance(answer, dict) and "errore" in answer}
    assert not failed, failed
    assert len(shot["strumenti"]) >= 8, sorted(shot["strumenti"])


def test_un_nome_cambiato_negli_ingressi_si_vede_nelle_schede(shot):
    changed = copy.deepcopy(synthetic_inputs())
    target = next(row for row in changed["registries"]["entita"]
                  if row["entity_id"] == "light.luce_uno")
    target["name"] = "Nome cambiato"
    # Rinominare in Home Assistant cambia anche il `friendly_name`, ed e'
    # quello che le schede mostrano dal Task 5 della Tappa 3 (D1 «vivo»).
    live = next(row for row in changed["states"] if row["entity_id"] == "light.luce_uno")
    live["attributes"]["friendly_name"] = "Nome cambiato"
    differences = fotografia_porte.compare(shot, _shot(changed))
    assert any(line.startswith("schede") for line in differences), differences[:5]


def test_il_confronto_dice_dove_e_cosa_e_tronca_dichiarandolo():
    first = {"porta": {"a": 1, "righe": [1, 2, 3]}}
    second = {"porta": {"a": 2, "righe": [1, 2]}}
    assert fotografia_porte.compare(first, second) == [
        "porta.a: 1 -> 2", "porta.righe: 3 voci -> 2 voci"]
    many_first = {"p": {str(n): n for n in range(500)}}
    many_second = {"p": {str(n): n + 1 for n in range(500)}}
    lines = fotografia_porte.compare(many_first, many_second)
    assert len(lines) == fotografia_porte.DIFFERENCES_SHOWN + 1
    assert lines[-1] == "... e altre 300 differenze (500 in tutto)"


def test_una_porta_che_chiede_altro_a_home_assistant_si_vede():
    """La casa congelata e' il client vero (`scripts/casa_finta.py`): una
    domanda che gli ingressi non portano solleva col suo nome, e non e' un
    `Exception` che il prodotto possa inghiottire."""
    from casa_finta import UnservedCommand

    async def ask():
        house = fotografia_porte.FrozenHouse(synthetic_inputs())
        await house.call_service("light", "turn_on", {})

    with pytest.raises(UnservedCommand, match="/api/services/light/turn_on"):
        asyncio.run(ask())


def test_la_casa_congelata_non_ha_cio_che_la_cattura_non_congela():
    """`UNCAPTURED` e' una lista di ammissione: ogni nome e' un metodo vero del
    client, e la casa congelata non lo ha."""
    from hiris.app.proxy.ha_client import HAClient

    assert fotografia_porte.UNCAPTURED
    for name in fotografia_porte.UNCAPTURED:
        assert callable(getattr(HAClient, name)), name
        assert getattr(fotografia_porte.FrozenHouse(synthetic_inputs()), name) is None


def test_l_app_fotografata_e_quella_dell_avvio_vero():
    """Mutazione ESEGUITA: in `mounted` sostituito l'avvio con un'app montata a
    mano senza `type_judgments` -- rossa (chiave mancante)."""
    async def keys():
        import tempfile
        with tempfile.TemporaryDirectory() as data_dir:
            async with fotografia_porte.mounted(synthetic_inputs(), data_dir) as app:
                return {name for name in ("home_space_store", "entity_cache", "memory_store",
                                          "type_judgments", "state_translations",
                                          "service_registry", "knowledge", "ha_client")
                        if app.get(name) is not None}

    assert asyncio.run(keys()) == {
        "home_space_store", "entity_cache", "memory_store", "type_judgments",
        "state_translations", "service_registry", "knowledge", "ha_client"}


# ── la fotografia dal vivo: le forme ───────────────────────────────────────

def test_la_forma_non_porta_valori():
    shape = fotografia_porte.shape(
        {"nome": "Cucina", "token": "segreto", "righe": [{"id": 7}, {"id": 8}],
         "vuoto": [], "manca": None, "acceso": True, "gradi": 21.5})
    assert shape == {"nome": "str", "token": "str", "manca": "NoneType",
                     "acceso": "bool", "gradi": "float",
                     "righe": {"elenco": 2, "di": {"id": "int"}},
                     "vuoto": {"elenco": 0, "di": None}}
    assert "Cucina" not in repr(shape) and "segreto" not in repr(shape)


def test_la_forma_di_un_elenco_unisce_le_chiavi_di_tutte_le_righe():
    # Guardare solo la prima riga nasconderebbe un campo che compare dalla
    # seconda: e' proprio la specie di differenza che lo sprint cerca.
    shape = fotografia_porte.shape([{"id": 1}, {"id": 2, "unita": "W"}])
    assert shape == {"elenco": 2, "di": {"id": "int", "unita": "str"}}


def test_la_forma_non_dipende_dall_ordine_delle_righe():
    """Mutazione ESEGUITA: in `_merge` restituito `{**first, **second}` per due
    dizionari -- rossa (`area` vale `str` in un ordine e `NoneType`
    nell'altro: rilievo I8 della revisione del 01/10/2026)."""
    rows = [{"area": None, "d": {"p": 1}}, {"area": "x", "d": {"q": 2.0}}]
    forward = fotografia_porte.shape(rows)
    assert forward == fotografia_porte.shape(list(reversed(rows)))
    assert forward["di"] == {"area": ["NoneType", "str"], "d": {"p": "int", "q": "float"}}


def test_le_chiavi_che_sono_identificatori_della_casa_non_restano_nella_forma():
    shape = fotografia_porte.shape(
        {"carichi": {"sensor.cucina_temperatura": {"valore": 1},
                     "sensor.sala_umidita": {"valore": 2, "unita": "%"}}})
    assert shape == {"carichi": {"*": {"valore": "int", "unita": "str"}}}
    assert "cucina" not in repr(shape) and "sala" not in repr(shape)


def test_un_elenco_vuoto_contro_uno_pieno_non_e_un_cambio_di_forma():
    empty = fotografia_porte.shape({"righe": []})
    full = fotografia_porte.shape({"righe": [{"id": 1}]})
    assert fotografia_porte.compare(empty, full, shapes_only=True) == []
    assert fotografia_porte.compare(full, empty, shapes_only=True) == []


def test_le_rotte_dal_vivo_si_derivano_dal_router():
    """Mutazioni ESEGUITE: aggiunta in `server.py` la riga
    `app.router.add_get("/api/prova-mutazione", handle_usage)` -- entra in
    `live_routes()` senza toccare questa prova; tolta, esce. E dal 03/10/2026
    la stessa rotta registrata con `add_route("GET", ...)`, che la lettura del
    sorgente non vedeva: entra anche lei."""
    from aiohttp import web

    async def handler(request):
        return web.json_response({})

    app = web.Application()
    app.router.add_get("/api/uno", handler)
    app.router.add_get("/api/cose/{id}", handler)
    app.router.add_post("/api/scrive", handler)
    app.router.add_get("/", handler)
    app.router.add_route("GET", "/api/due", handler)
    assert fotografia_porte.live_routes(app) == ("/api/due", "/api/uno")
    real = fotografia_porte.live_routes()
    assert "/api/home-space" in real and "/api/health" in real
    assert len(real) >= 15, real
    assert not [route for route in real if "{" in route or not route.startswith("/api/")]


def test_ogni_esclusione_e_una_rotta_che_esiste():
    # Una lista di esclusioni che nomina rotte sparite e' un elenco che
    # invecchia: l'esclusione esce con la rotta.
    every = fotografia_porte.live_routes(excluded=())
    stale = sorted(set(fotografia_porte.EXCLUDED_ROUTES) - set(every))
    assert not stale, f"esclusioni di rotte che non esistono piu': {stale}"


def test_due_forme_dal_vivo_si_confrontano_senza_contare_le_righe():
    """Mutazione ESEGUITA: in `without_lengths` tolta la condizione sul campo
    `elenco` -- rossa (`righe.elenco: 2 -> 3` torna fra le differenze)."""
    first = fotografia_porte.shape({"righe": [{"id": 1}, {"id": 2}]})
    grown = fotografia_porte.shape({"righe": [{"id": 1}, {"id": 2}, {"id": 3}]})
    renamed = fotografia_porte.shape({"righe": [{"entity_id": 1}, {"entity_id": 2}]})
    assert fotografia_porte.compare(first, grown) == ["righe.elenco: 2 -> 3"]
    assert fotografia_porte.compare(first, grown, shapes_only=True) == []
    assert fotografia_porte.compare(first, renamed, shapes_only=True) == [
        "righe.di.entity_id: assente -> presente", "righe.di.id: presente -> assente"]

