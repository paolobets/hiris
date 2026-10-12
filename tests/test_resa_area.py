"""Un'area si rende in un posto solo, e le pseudo-aree hanno la forma delle
aree vere (Tappa 9, F4; C-02 per l'area e C-43 della Tappa 4).
"""
from hiris.app.home_space.topology import hierarchy, is_pseudo_area


def _casa():
    """Un'area vera con le sue entita' di riferimento, e un'entita' per
    ciascuna delle cause «fuori dalle aree note»."""
    return {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
        "aree": [{"id": "cucina", "nome": "Cucina", "piano_id": "terra",
                  "alias": ["angolo cottura"], "etichette": [],
                  "entita_temperatura": "sensor.cucina_t"}],
        "dispositivi": [],
        "entita": [
            {"id": "sensor.cucina_t", "area_id": "cucina", "dispositivo_id": None},
            {"id": "light.senza_area", "area_id": None, "dispositivo_id": None},
            {"id": "light.area_ignota", "area_id": "soffitta", "dispositivo_id": None},
        ],
        "etichette": [], "categorie": [], "integrazioni": [],
    }


def _aree(floors):
    return [area for floor in floors for area in floor.get("aree") or []]


def test_le_pseudo_aree_hanno_le_chiavi_delle_aree_vere():
    """C-43: le quattro pseudo-aree erano dizionari scritti a mano, senza
    `entita_temperatura` ne' `entita_umidita`. Ora nascono dalla stessa
    funzione delle aree vere.

    Rossa prima: le chiavi delle pseudo-aree erano un sottoinsieme.
    Mutazione ESEGUITA: «Senza area» tornata un dizionario scritto a mano --
    rossa."""
    aree = _aree(hierarchy(_casa(), ()))
    vere = [a for a in aree if not is_pseudo_area(a["id"])]
    finte = [a for a in aree if is_pseudo_area(a["id"])]
    assert vere and len(finte) == 2
    for finta in finte:
        assert set(finta) == set(vere[0]), (finta["id"], set(vere[0]) - set(finta))
    # Anche con i registri caduti: «Aree non lette», «Dispositivi non letti».
    caduti = _aree(hierarchy({**_casa(), "aree": []}, ("aree",)))
    assert caduti and all(set(a) == set(vere[0]) for a in caduti)


T0 = 1_790_700_000.0


def _casa_viva():
    from hiris.app.home_space.house import House
    from hiris.app.home_space.topology import Mirror
    casa = _casa()
    casa["aree"].append({"id": "sala", "nome": "Sala", "piano_id": "terra",
                         "alias": [], "etichette": []})
    return House(casa, Mirror({}))


def _scheda(ident):
    from hiris.app.home_space.queries import view
    return view(_casa_viva(), [], [], "area", ident)


def test_la_stessa_area_da_view_e_da_search_ha_la_stessa_forma():
    """C-02 per l'area: la voce di `search` portava il piano come nome nudo,
    la scheda di `view` nessun piano. La scheda contiene la voce media, coi
    suoi valori, e il piano e' `{id, nome}`.

    Rossa prima della resa unica (`piano: "Piano terra"`). Mutazione
    ESEGUITA: `render_area` col piano come nome nudo -- rossa."""
    from hiris.app.home_space import house_query as hq
    filtri = hq.parse_filters({"genere": "area"})
    voci = hq.query_house(_casa_viva(), [], filtri,
                          detail=lambda kind, ref: _scheda(ref), now=T0)["voci"]
    assert {v["id"] for v in voci} == {"cucina", "sala"}
    for voce in voci:
        assert voce["piano"] == {"id": "terra", "nome": "Piano terra"}
        scheda = _scheda(voce["id"])
        assert {k: scheda.get(k) for k in voce} == voce, (voce, scheda)
    assert next(v for v in voci if v["id"] == "cucina")["alias"] == ["angolo cottura"]
    # La scheda e' alla completa, la voce sotto (N120-1, giro 120).
    # Mutazione ESEGUITA: le voci alla completa -- rossa.
    assert _scheda("cucina")["entita_temperatura"] == "sensor.cucina_t"
    assert all("entita_temperatura" not in v for v in voci), voci


def test_la_voce_di_una_pseudo_area_non_ha_piano():
    """N120-1 (giro 120): «piano assente per una pseudo-area». Altrimenti la
    voce di «Senza area» direbbe `piano: {id: "__fuori_dalle_aree__", ...}`,
    la ripetizione che `House.where` evita.

    Mutazione ESEGUITA: il piano dato anche a una pseudo-area -- rossa."""
    from hiris.app.home_space import house_query as hq
    filtri = hq.parse_filters({"genere": "area", "riferimento": "__senza_area__"})
    uscita = hq.query_house(_casa_viva(), [], filtri,
                            detail=lambda kind, ref: _scheda(ref), now=T0)
    voci = uscita.get("voci") or [uscita]
    senza = [v for v in voci if v.get("id") == "__senza_area__"]
    assert senza, uscita
    assert all("piano" not in v for v in senza), senza


def test_le_profondita_dell_area_si_contengono():
    """corta ⊆ media ⊆ completa, chieste alla resa."""
    from hiris.app.home_space.render import render_area
    casa = _casa_viva()
    area = next(a for a in _aree(casa.hierarchy()) if a["id"] == "cucina")
    corta, media, completa = (set(render_area(casa, area, depth))
                              for depth in ("corta", "media", "completa"))
    assert {"id", "genere", "nome", "piano"} <= corta
    assert corta < media < completa
    assert "alias" in media - corta
    assert completa - media == {"entita_temperatura"}
