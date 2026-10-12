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

