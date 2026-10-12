"""Le righe degli attori sono la resa in testo dell'entita' (Tappa 9, F4; D8 e
D9 della Tappa 4).

Fino al 12/10/2026 `observer.house_lines` e `recipe_turn.device_lines`
componevano la riga ciascuna per conto suo, chiedendo nome, tipo, area e
fonte alla casa campo per campo: «stesso separatore e primi quattro campi, ma
NON la stessa riga» (il docstring delle ricette). Ora la riga e'
`render.entity_line`, a due profondita', scritta dal dizionario di
`render_entity`.
"""
from hiris.app.home_space import render
from hiris.app.home_space.house import House
from hiris.app.home_space.topology import Mirror
from hiris.app.mind import observer, recipe_turn


def _entita(ident, nome, area, dispositivo, **campi):
    return {"id": ident, "nome": nome, "classe": None, "unita": None,
            "translation_key": None, "categoria": None, "disabilitata": 0,
            "nascosta": 0, "area_id": area, "dispositivo_id": dispositivo,
            "piattaforma": "x", **campi}


def _casa():
    """Due aree, nell'ordine dell'anagrafe: prima «Studio», poi «Cucina». Le
    entita' in un ordine che non e' quello dell'albero."""
    entita = [
        _entita("sensor.z_cucina", "Z", "cucina", None),
        _entita("sensor.b_cucina", "Forno", None, "dev_forno", classe="energy",
                unita="kWh", translation_key="energy_today"),
        _entita("sensor.a_cucina", "Frigo", None, "dev_frigo"),
        _entita("light.studio", "Lampada", "studio", None),
        _entita("sensor.senza_area", "Fuori", None, None),
    ]
    casa = {"entita": entita,
            "aree": [{"id": "studio", "nome": "Studio"}, {"id": "cucina", "nome": "Cucina"}],
            "dispositivi": [{"id": "dev_forno", "nome": "Forno", "area_id": "cucina"},
                            {"id": "dev_frigo", "nome": "Frigo", "area_id": "cucina"}]}
    return House(casa, Mirror(state={e["id"]: "on" for e in entita}))


def test_le_righe_degli_attori_si_scrivono_dalla_resa(monkeypatch):
    """Si cambia la resa e si guarda se le righe la seguono: una copia fedele
    dei campi darebbe le stesse righe e la prova resterebbe verde.

    Rossa prima: le righe chiedevano il nome a `House.name`. Mutazione
    ESEGUITA: `entity_line` che legge il nome da `House.name` -- rossa."""
    vera = render.render_entity

    def resa(house, entity_id, depth, **kw):
        return {**vera(house, entity_id, depth, **kw), "nome": "DALLA RESA"}

    monkeypatch.setattr(render, "render_entity", resa)
    casa = _casa()
    assert all(" · DALLA RESA" in riga for riga in observer.house_lines(casa))
    assert all(" · DALLA RESA" in riga for riga in recipe_turn.device_lines(casa, "dev_forno"))


def test_la_riga_corta_e_l_inizio_della_media():
    """Due profondita', la seconda contiene la prima (D8): la ricetta porta
    id, nome, classe e unita'; l'osservatore aggiunge area, chiave di
    traduzione e la fonte che tace."""
    casa = _casa()
    corta = render.entity_line(casa, "sensor.b_cucina", "corta")
    media = render.entity_line(casa, "sensor.b_cucina", "media")
    assert corta == "sensor.b_cucina · Forno · energy · kWh"
    assert media == corta + " · Cucina · energy_today"


def test_l_osservatore_legge_la_casa_nell_ordine_dell_albero():
    """D9: area (nell'ordine dell'albero), poi dispositivo, poi id. Stabile
    fra un giro e l'altro, qualunque sia l'ordine dell'anagrafe.

    Rossa prima: le righe uscivano nell'ordine dell'anagrafe. Mutazione
    ESEGUITA: `house_lines` senza l'ordine -- rossa."""
    ordine = [riga.split(" · ")[0] for riga in observer.house_lines(_casa())]
    assert ordine == ["light.studio", "sensor.z_cucina", "sensor.b_cucina",
                      "sensor.a_cucina", "sensor.senza_area"]
