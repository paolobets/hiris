"""«Da quando?» -- il campo che arrivava a ogni evento e veniva buttato.

Non e' uno strumento nuovo: e' un campo che Home Assistant manda a ogni cambio
di stato e che la proiezione della cache scartava. Il prodotto sapeva che in
camera ci sono 22,4 gradi e non sapeva da quando.

La fondamenta 3 e' il cuore di questo file: se lo stato esce da un punto di
`guarda` con il suo istante e da un altro senza, la stessa domanda ha due
risposte diverse a seconda di come ci si arriva. I punti sono quattro, e il
test che li CONTA e' quello che impedisce al sesto di nascere senza.
"""
from hiris.app.home_space.topology import live_mirror
from hiris.app.proxy.entity_cache import _to_minimal


def test_la_proiezione_conserva_l_istante_del_cambio():
    minimo = _to_minimal({
        "entity_id": "sensor.camera", "state": "22.4",
        "last_changed": "2026-08-24T11:00:00+00:00",
        "attributes": {"unit_of_measurement": "°C"},
    })
    assert minimo["last_changed"] == "2026-08-24T11:00:00+00:00"


def test_uno_stato_senza_istante_non_inventa_niente():
    minimo = _to_minimal({"entity_id": "sensor.x", "state": "1", "attributes": {}})
    assert minimo["last_changed"] is None


def test_lo_specchio_porta_l_istante_accanto_allo_stato():
    mirror = live_mirror([
        {"id": "sensor.camera", "state": "22.4", "name": "Camera",
         "unit": "°C", "device_class": "temperature",
         "last_changed": "2026-08-24T11:00:00+00:00"},
    ])
    assert mirror.state["sensor.camera"] == "22.4"
    assert mirror.since["sensor.camera"] == "2026-08-24T11:00:00+00:00"


def test_ogni_punto_di_guarda_che_emette_uno_stato_emette_anche_l_istante():
    """La fondamenta 3, resa impossibile da dimenticare.

    Fino all'08/10/2026 lo stato si scriveva in tre punti di `queries.py`, e
    questa prova legava con una regex ogni `"stato": mirror.state.get(` al
    suo `da_quando` nelle righe vicine. Dalla Tappa 9 (F2) lo stato di
    un'entita' lo scrive una funzione sola, `render.render_entity`, e
    l'istante si chiama `ultimo_cambio` (D1 della Tappa 4): la prova
    guarda le PORTE, non il testo -- la scheda di un'entita', le righe di
    un'area e le voci di `search`, a ogni profondita'.
    Mutazione ESEGUITA: `render_entity` senza `ultimo_cambio` -- rossa."""
    from hiris.app.home_space.house import House
    from hiris.app.home_space.house_query import parse_filters, query_house
    from hiris.app.home_space.queries import view
    from hiris.app.home_space.render import DEPTHS, render_entity
    from hiris.app.home_space.topology import Mirror

    casa = {"aree": [{"id": "camera", "nome": "Camera"}], "piani": [],
            "dispositivi": [], "entita": [
                {"id": "sensor.camera", "nome": "Camera", "area_id": "camera",
                 "dispositivo_id": None}]}
    specchio = Mirror(state={"sensor.camera": "22.4"},
                      since={"sensor.camera": "2026-08-24T11:00:00+00:00"})
    house = House(casa, specchio)
    righe = [render_entity(house, "sensor.camera", d) for d in DEPTHS]
    righe.append(view(house, [], [], "entita", "sensor.camera"))
    righe.extend(view(house, [], [], "area", "camera")["entita"])
    # Una voce sola apre la scheda (`render.depth_for`): `detail` la chiede a `view`.
    voci = query_house(house, [], parse_filters({"tipo": "sensor"}),
                       detail=lambda genere, rif: view(house, [], [], genere, rif),
                       now=0.0)["voci"]
    righe.extend(voci)
    assert len(righe) == 6
    for riga in righe:
        assert riga["stato"] == "22.4"
        assert riga["ultimo_cambio"].startswith("2026-08-24T11:00:00"), riga
