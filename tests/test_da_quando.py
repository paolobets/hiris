"""«Da quando?» -- il campo che arrivava a ogni evento e veniva buttato.

Non e' uno strumento nuovo: e' un campo che Home Assistant manda a ogni cambio
di stato e che la proiezione della cache scartava. Il prodotto sapeva che in
camera ci sono 22,4 gradi e non sapeva da quando.

La fondamenta 3 e' il cuore di questo file: se lo stato esce da un punto di
`guarda` con il suo istante e da un altro senza, la stessa domanda ha due
risposte diverse a seconda di come ci si arriva. I punti sono quattro, e il
test che li CONTA e' quello che impedisce al sesto di nascere senza.
"""
import re
from pathlib import Path

from hiris.app.casa.anagrafe import specchio_vivo
from hiris.app.proxy.entity_cache import _to_minimal

_SORGENTE_DOMANDE = Path(__file__).parent.parent / "hiris" / "app" / "casa" / "domande.py"


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
    stato, _n, _u, _c, da_quando = specchio_vivo([
        {"id": "sensor.camera", "state": "22.4", "name": "Camera",
         "unit": "°C", "device_class": "temperature",
         "last_changed": "2026-08-24T11:00:00+00:00"},
    ])
    assert stato["sensor.camera"] == "22.4"
    assert da_quando["sensor.camera"] == "2026-08-24T11:00:00+00:00"


def test_ogni_punto_di_guarda_che_emette_uno_stato_emette_anche_l_istante():
    """La fondamenta 3, resa impossibile da dimenticare.

    Un'asserzione che si accontentasse di vedere «da_quando» da qualche parte
    nel file non difenderebbe niente: qui si LEGA ogni occorrenza di
    `"stato": stato.get(` alla presenza del suo gemello nelle righe
    immediatamente seguenti.
    """
    sorgente = _SORGENTE_DOMANDE.read_text(encoding="utf-8")
    righe = sorgente.splitlines()
    punti = [i for i, r in enumerate(righe) if re.search(r'"stato":\s*stato\.get\(', r)]
    # Quattro, verificati col grep sul sorgente vero al 24/08/2026 (righe 430,
    # 442, 495, 533). Il conteggio serve solo a impedire che una regex che non
    # trova NIENTE passi per verde: la difesa vera e' il ciclo qui sotto, che
    # lega ogni occorrenza al suo gemello.
    assert len(punti) >= 4, "i punti che emettono uno stato sono cambiati: rileggi"
    for i in punti:
        vicinato = "\n".join(righe[max(0, i - 2):i + 3])
        assert "da_quando" in vicinato, f"riga {i + 1}: stato senza istante"
