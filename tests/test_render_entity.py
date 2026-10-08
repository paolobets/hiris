"""La resa di un'entita' (`render.render_entity`, Tappa 9, F2): le tre
profondita' si contengono, l'integrazione e' un riferimento `{id, nome}`, e
il `fuori` c'e' solo per cio' che sta fuori dai visibili."""
from itertools import pairwise

import pytest

from hiris.app.home_space.house import House
from hiris.app.home_space.render import DEPTHS, depth_for, render_entity, rows_depth
from hiris.app.home_space.topology import Mirror

_CASA = {
    "aree": [{"id": "orto", "nome": "Orto", "piano_id": None}],
    "piani": [], "dispositivi": [],
    "entita": [
        {"id": "valve.aiuola", "nome": "Aiuola", "piattaforma": "hydrawise",
         "config_entry_id": "e1", "area_id": "orto", "dispositivo_id": None},
        {"id": "sensor.diag", "nome": "Diagnostica", "piattaforma": "hydrawise",
         "area_id": "orto", "dispositivo_id": None, "categoria": "diagnostic"},
    ],
    "integrazioni": [{"entry_id": "e1", "dominio": "hydrawise", "titolo": "Giardino"}],
}
_SPECCHIO = Mirror(state={"valve.aiuola": "open", "sensor.diag": "3"},
                   since={"valve.aiuola": 1790000000.0})


def _casa():
    return House(_CASA, _SPECCHIO)


def test_ogni_profondita_contiene_la_precedente():
    """Mutazione ESEGUITA: la media che riparte da un dizionario nuovo --
    rossa (le chiavi della corta mancano)."""
    rese = [render_entity(_casa(), "valve.aiuola", d) for d in DEPTHS]
    for corta, lunga in pairwise(rese):
        assert set(corta) <= set(lunga)
        assert all(lunga[k] == v for k, v in corta.items())
    assert set(rese[0]) < set(rese[-1])


def test_l_integrazione_porta_il_titolo_della_sua_istanza():
    """C-62: il nome e' quello che Home Assistant mostra sotto il dominio."""
    riga = render_entity(_casa(), "valve.aiuola", "media")
    assert riga["integrazione"] == {"id": "hydrawise", "nome": "Giardino"}
    # Senza istanza nota il nome e' il dominio, non un vuoto.
    riga = render_entity(_casa(), "sensor.diag", "media")
    assert riga["integrazione"] == {"id": "hydrawise", "nome": "hydrawise"}


def test_il_fuori_solo_per_cio_che_sta_fuori():
    assert "fuori" not in render_entity(_casa(), "valve.aiuola", "corta")
    assert render_entity(_casa(), "sensor.diag", "corta")["fuori"] == {
        "classe": "servizio", "causa": "diagnostic"}


def test_la_profondita_viene_dal_numero_delle_righe():
    assert depth_for(1) == "completa"
    assert rows_depth(1) == "media" and rows_depth(10) == "media"
    assert rows_depth(11) == "corta"
    with pytest.raises(ValueError):
        render_entity(_casa(), "valve.aiuola", "lunga")
