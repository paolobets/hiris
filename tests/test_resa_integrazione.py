"""Un'integrazione si rende in un posto solo (Tappa 9, F4; C-02 della Tappa 4).

Fino al 12/10/2026 la scheda di `view` (`queries._view_integration`) non
portava ne' `id` ne' `nome`: l'integrazione si chiamava `dominio`, mentre la
stessa integrazione, vista dall'entita' che ne nasce (`render_entity`, chiave
`integrazione`), era gia' `{id, nome}`. Due porte, due forme dello stesso
oggetto (fondamenta 3).
"""
from hiris.app.home_space.house import House
from hiris.app.home_space.queries import view
from hiris.app.home_space.render import render_entity, render_integration
from hiris.app.home_space.topology import Mirror


def _entita(ident, piattaforma, voce):
    return {"id": ident, "nome": ident, "piattaforma": piattaforma,
            "config_entry_id": voce, "area_id": None, "dispositivo_id": None,
            "classe": None, "unita": None, "disabilitata": 0}


def _casa():
    return {
        "piani": [], "aree": [], "dispositivi": [], "etichette": [], "categorie": [],
        "entita": [_entita("valve.giardino", "hydrawise", "e1"),
                   _entita("light.sala", "hue", "e2"),
                   _entita("light.cucina", "hue", "e3")],
        "integrazioni": [
            {"entry_id": "e1", "dominio": "hydrawise", "titolo": "Giardino",
             "stato": "loaded", "motivo": None},
            {"entry_id": "e2", "dominio": "hue", "titolo": "Ponte sala",
             "stato": "loaded", "motivo": None},
            {"entry_id": "e3", "dominio": "hue", "titolo": "Ponte cucina",
             "stato": "setup_retry", "motivo": "non risponde"},
        ],
    }


def _casa_viva():
    return House(_casa(), Mirror({"valve.giardino": "unavailable",
                                  "light.sala": "on", "light.cucina": "off"}))


def test_la_stessa_integrazione_dalla_scheda_e_dall_entita_ha_lo_stesso_riferimento():
    """La scheda porta `id` e `nome` come il riferimento `integrazione` di
    un'entita' che ne nasce; `dominio`, che era lo stesso fatto di `id`, esce.

    Rossa prima della resa unica (la scheda senza `id`). Mutazione ESEGUITA:
    `render_integration` col nome uguale al dominio -- rossa."""
    casa = _casa_viva()
    scheda = view(casa, [], [], "integrazione", "Hydrawise")
    riferimento = render_entity(casa, "valve.giardino", "completa")["integrazione"]
    assert {k: scheda[k] for k in riferimento} == riferimento == {
        "id": "hydrawise", "nome": "Giardino"}
    assert scheda["genere"] == "integrazione"
    assert "dominio" not in scheda


def test_con_piu_istanze_il_nome_e_il_dominio_e_le_istanze_restano_nelle_voci():
    """Due istanze di hue con due titoli: l'integrazione intera non e' ne'
    l'una ne' l'altra, si chiama col suo dominio; ogni entita' nomina la
    propria istanza (C-62), e le istanze stanno nelle `voci`."""
    casa = _casa_viva()
    scheda = view(casa, [], [], "integrazione", "hue")
    assert (scheda["id"], scheda["nome"]) == ("hue", "hue")
    assert [v["titolo"] for v in scheda["voci"]] == ["Ponte sala", "Ponte cucina"]
    cucina = render_entity(casa, "light.cucina", "completa")["integrazione"]
    assert cucina == {"id": "hue", "nome": "Ponte cucina"}


def test_le_profondita_dell_integrazione_si_contengono():
    """corta ⊆ media ⊆ completa, chieste alla resa."""
    casa = _casa_viva()
    corta, media, completa = (set(render_integration(casa, "hue", depth))
                              for depth in ("corta", "media", "completa"))
    assert corta == {"id", "genere", "nome"}
    assert corta < media <= completa
    assert media - corta == {"voci"}
