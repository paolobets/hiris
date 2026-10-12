"""Un dispositivo si rende in un posto solo (Tappa 9, F4; C-02 e M-50 della
Tappa 4).

Fino al 12/10/2026 la scheda di `view` (`queries._view_device`) e le voci di
`search` (`house_query._device_rows`) componevano lo stesso dispositivo
ciascuna per conto suo: la voce con l'area come nome nudo, la scheda senza
area e con `disabilitato: false` su ogni dispositivo acceso, dove il
vocabolario dice `fuori`, solo quando c'e' (D4).
"""
from hiris.app.home_space import house_query as hq
from hiris.app.home_space.house import House
from hiris.app.home_space.queries import view
from hiris.app.home_space.render import render_device
from hiris.app.home_space.topology import Mirror

T0 = 1_790_700_000.0


def _dispositivo(ident, nome, area, **campi):
    return {"id": ident, "nome": nome, "produttore": "Acme", "modello": "X1",
            "area_id": area, "disabilitato": 0, "disabilitato_da": None,
            "etichette": [], **campi}


def _casa():
    return {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
        "aree": [{"id": "lavanderia", "nome": "Lavanderia", "piano_id": "terra",
                  "alias": [], "etichette": []}],
        "dispositivi": [_dispositivo("dev_lavatrice", "Lavatrice", "lavanderia"),
                        _dispositivo("dev_asciugatrice", "Asciugatrice", "lavanderia"),
                        {**_dispositivo("dev_vecchio", "Vecchio", "lavanderia"),
                         "disabilitato": 1, "disabilitato_da": "user"}],
        "entita": [], "etichette": [], "categorie": [], "integrazioni": [],
    }


def _casa_viva():
    return House(_casa(), Mirror({}))


def _scheda(ident):
    return view(_casa_viva(), [], [], "dispositivo", ident)


def test_lo_stesso_dispositivo_da_view_e_da_search_ha_la_stessa_forma():
    """La scheda contiene la voce media di `search`, coi suoi valori: l'area
    come `{id, nome}` (atomicita'), non il nome nudo.

    Rossa prima della resa unica: la voce portava `area: "Lavanderia"` e la
    scheda nessuna area. Mutazione ESEGUITA: `render_device` con l'area come
    nome nudo -- rossa."""
    filtri = hq.parse_filters({"genere": "dispositivo"})
    voci = hq.query_house(_casa_viva(), [], filtri,
                          detail=lambda kind, ref: _scheda(ref), now=T0)["voci"]
    assert {v["id"] for v in voci} == {"dev_lavatrice", "dev_asciugatrice"}
    for voce in voci:
        assert voce["area"] == {"id": "lavanderia", "nome": "Lavanderia"}
        scheda = _scheda(voce["id"])
        assert {k: scheda.get(k) for k in voce} == voce, (voce, scheda)
        # La scheda e' alla completa, la voce sotto (N119-2, giro 119).
        # Mutazioni ESEGUITE: la scheda alla media, le voci alla completa --
        # rossa ognuna.
        assert scheda["piano"] == {"id": "terra", "nome": "Piano terra"}
        assert "piano" not in voce, voce


def test_un_dispositivo_spento_dice_fuori_e_un_acceso_non_dice_niente():
    """M-50 (D4): `fuori: {classe, causa}` solo quando il dispositivo non e'
    fra i visibili; il booleano `disabilitato` esce.

    Rossa prima della resa unica (`disabilitato: false`). Mutazione ESEGUITA:
    `render_device` che torna a scrivere `disabilitato` -- rossa."""
    acceso, spento = _scheda("dev_lavatrice"), _scheda("dev_vecchio")
    assert "fuori" not in acceso and "disabilitato" not in acceso
    assert spento["fuori"] == {"classe": "disabilitata", "causa": "user"}
    assert "disabilitato" not in spento


def test_le_profondita_del_dispositivo_si_contengono():
    """corta ⊆ media ⊆ completa, chieste alla resa."""
    casa = _casa_viva()
    voce = _casa()["dispositivi"][0]
    corta, media, completa = (set(render_device(casa, voce, depth))
                              for depth in ("corta", "media", "completa"))
    assert {"id", "genere", "nome", "area"} <= corta
    assert corta < media <= completa
    assert {"produttore", "modello"} <= media - corta
    assert "piano" in completa - media


def test_un_area_che_l_albero_non_conosce_si_dice_come_per_l_entita():
    """N119-1 (giro 119): un dispositivo con un `area_id` che l'albero non
    conosce usciva SENZA `area` -- la forma di chi un'area non ce l'ha --
    mentre la sua entita', che la eredita, diceva «Area sconosciuta». Lo
    stesso posto, due forme (fondamenta 3). Con il registro delle aree caduto
    la causa e' «Aree non lette», come nell'albero.

    Rossa prima: `area` mancava."""
    from hiris.app.home_space.render import render_entity

    casa = _casa()
    casa["dispositivi"][0]["area_id"] = "sparita"
    casa["entita"] = [{"id": "sensor.lavatrice", "nome": "Lavatrice", "area_id": None,
                       "dispositivo_id": "dev_lavatrice", "disabilitata": 0,
                       "nascosta": 0, "piattaforma": "x"}]
    viva = House(casa, Mirror({"sensor.lavatrice": "on"}))
    sconosciuta = {"id": "__area_sconosciuta__", "nome": "Area sconosciuta"}
    dispositivo = render_device(viva, casa["dispositivi"][0], "completa")
    assert dispositivo["area"] == sconosciuta
    assert "piano" not in dispositivo
    assert render_entity(viva, "sensor.lavatrice", "corta")["area"] == sconosciuta
    caduta = House(casa, Mirror({}), unavailable=("aree",))
    assert render_device(caduta, casa["dispositivi"][0], "corta")["area"] == {
        "id": "__aree_non_lette__", "nome": "Aree non lette"}
