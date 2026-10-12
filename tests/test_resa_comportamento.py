"""Un'automazione o uno script si rende in un posto solo (Tappa 9, F4; C-42
e «trovato 1» della Tappa 4).

Fino al 12/10/2026 `queries._view_behavior` (la scheda di `view`) e
`house_query._behavior_row` (le voci di `search`) componevano la stessa
automazione ciascuna per conto suo: la scheda senza `stato`, `attiva` ne'
`ultima_esecuzione`, e con `nome: null` dove le voci scrivevano il nome vivo
con l'id come ripiego.
"""
from hiris.app.home_space import house_query as hq
from hiris.app.home_space.house import House
from hiris.app.home_space.queries import view
from hiris.app.home_space.render import render_behavior
from hiris.app.home_space.topology import Mirror

T0 = 1_790_700_000.0
_ULTIMA = "2026-09-28T06:30:00+00:00"

_CASA = {"piani": [], "aree": [], "dispositivi": [], "entita": [],
         "etichette": [], "categorie": [], "integrazioni": []}


def _comportamento():
    """Due automazioni: una senza nome (l'id e' il ripiego), spenta; e uno
    script. `attiva` la scrive `HomeSpace.behavior` dallo specchio."""
    return [{"id": "automation.senza_nome", "tipo": "automazione", "nome": None,
             "corpo": {"trigger": []}, "attiva": False},
            {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
             "corpo": {"trigger": []}, "attiva": True}]


def _specchio():
    valori = {"last_triggered": _ULTIMA, "mode": "single", "current": 0}
    return Mirror({"automation.senza_nome": "off", "automation.sveglia": "on"},
                  attributes={"automation.senza_nome": {"values": dict(valori)},
                              "automation.sveglia": {"values": dict(valori)}})


def _scheda(ident):
    return view(House(_CASA, _specchio()), _comportamento(), [], "automazione", ident)


def _voci_medie():
    filtri = hq.parse_filters({"genere": "automazione"})
    return hq.query_house(House(_CASA, _specchio()), _comportamento(), filtri,
                          detail=lambda kind, ref: _scheda(ref), now=T0)["voci"]


def test_la_stessa_automazione_da_view_e_da_search_ha_lo_stesso_nome_e_gli_stessi_campi():
    """La scheda (`view`, completa) contiene la voce media di `search`, con
    gli stessi valori: il nome vivo con l'id come ripiego, lo `stato`,
    `attiva`, `ultima_esecuzione`, `modalita`, `in_esecuzione`.

    Rossa prima della resa unica (12/10/2026: la scheda con `nome: None`).
    Mutazione ESEGUITA: `render_behavior` col nome grezzo -- rossa."""
    for voce in _voci_medie():
        scheda = _scheda(voce["id"])
        assert scheda["esiste"] is True
        assert {k: scheda.get(k) for k in voce} == voce, (voce, scheda)
    anonima = _scheda("automation.senza_nome")
    assert anonima["nome"] == "automation.senza_nome"
    assert anonima["attiva"] is False and anonima["stato"] == "off"


def test_le_profondita_del_comportamento_si_contengono():
    """corta ⊆ media ⊆ completa, chieste alla resa.

    Mutazione ESEGUITA: `render_behavior` senza `attiva` -- rossa."""
    casa = House(_CASA, _specchio())
    voce = _comportamento()[1]
    corta, media, completa = (set(render_behavior(casa, voce, depth))
                              for depth in ("corta", "media", "completa"))
    assert corta < media < completa
    assert {"id", "nome", "genere", "stato", "attiva", "ultima_esecuzione"} <= corta
    assert {"modalita", "in_esecuzione"} <= media - corta
    assert completa - media == {"corpo"}
