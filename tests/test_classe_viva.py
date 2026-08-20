"""La classe di un'entita' viene dallo SPECCHIO, non dal registro.

Il difetto, misurato sul sorgente di Home Assistant e non ricordato:
`config/entity_registry/list` -- il comando con cui HIRIS legge le entita' --
risponde con `RegistryEntry.as_partial_dict`
(`homeassistant/helpers/entity_registry.py:335`), che NON contiene
`device_class`, ne' `original_device_class`, ne' `aliases`. Quei campi stanno
solo in `extended_dict` (`:369`), che HA manda su `config/entity_registry/get`
e `.../get_entries`.

Quindi la colonna `classe` dell'anagrafe e' **sempre NULL**, su ogni casa. E
da li' a cascata:

- `_e_un_evento("binary_sensor", None, "on")` e' sempre falso: NESSUN sensore
  binario e' mai entrato in «Notevole adesso». Allagamento, fumo, monossido,
  finestra aperta: muti;
- le voci di `_SIGNIFICATO_CLASSE` -- l'intera fetta 3.4.0, `carbon_monoxide`
  compreso e corretto una riga per volta -- erano codice irraggiungibile;
- `guarda` prometteva «l'entita' col suo stato e la sua CLASSE» e rispondeva
  `classe: null` su ogni entita' della casa.

Nessuna prova poteva accorgersene: tutte le finte scrivevano `device_class`
nella riga del registro, cioe' un campo che Home Assistant li' non mette. La
finta non sapeva produrre il difetto -- il difetto n.1 del progetto.

Il rimedio non costa nessuna chiamata: `device_class` e' gia' in RAM, in ogni
voce dello specchio dello stato (`entity_cache._to_minimal`). E' anche la fonte
che Home Assistant stesso preferisce (`helpers/entity.py::get_device_class`).
"""
import pytest

from hiris.app.casa.anagrafe import classe_effettiva, specchio_vivo
from hiris.app.casa.domande import guarda
from hiris.app.casa.nucleo import componi

# L'anagrafe COM'E' DAVVERO: `classe` a None, perche' HA non la manda.
_CASA = {
    "aree": [{"id": "bagno", "nome": "Bagno"}],
    "entita": [
        {"id": "binary_sensor.perdita_lavatrice", "nome": "Perdita lavatrice",
         "area_id": "bagno", "classe": None},
    ],
}
# Lo specchio vivo, che la classe ce l'ha.
_SPECCHIO = [{"id": "binary_sensor.perdita_lavatrice", "state": "on",
              "name": "Perdita lavatrice", "device_class": "moisture", "unit": ""}]


def test_la_regola_sta_in_un_posto_solo():
    assert classe_effettiva(None, "moisture") == "moisture"
    assert classe_effettiva("door", "moisture") == "moisture", "la viva vince"
    assert classe_effettiva("door", None) == "door"
    assert classe_effettiva(None, None) is None
    assert classe_effettiva("door", "  ") == "door"


def test_lo_specchio_porta_anche_le_classi():
    _stato, _nomi, _unita, classi = specchio_vivo(_SPECCHIO)
    assert classi["binary_sensor.perdita_lavatrice"] == "moisture"


def test_un_allagamento_entra_nel_digesto():
    """LA PROVA CHE CONTA. Con la classe dal solo registro questa e' rossa:
    il sensore e' `on` e il digesto dice «Niente di notevole al momento»."""
    stato, _n, _u, classi = specchio_vivo(_SPECCHIO)
    testo, _ = componi(_CASA, [], [], stato, classi_vive=classi)
    sezione = testo.split("## Notevole adesso")[1].split("## ")[0]
    assert "bagnato" in sezione, sezione
    assert "Niente di notevole" not in sezione


def test_una_lampadina_accesa_non_diventa_un_allagamento():
    """Il contrario, e serve quanto l'altra: senza, un rimedio che scrivesse
    «bagnato» su tutto farebbe passare la prova di sopra."""
    casa = {"aree": [{"id": "c", "nome": "Cucina"}],
            "entita": [{"id": "light.cucina", "nome": "Faretto", "area_id": "c",
                        "classe": None}]}
    specchio = [{"id": "light.cucina", "state": "on", "name": "Faretto",
                 "device_class": None, "unit": ""}]
    stato, _n, _u, classi = specchio_vivo(specchio)
    testo, _ = componi(casa, [], [], stato, classi_vive=classi)
    sezione = testo.split("## Notevole adesso")[1].split("## ")[0]
    assert "acceso" in sezione
    assert "bagnato" not in sezione


def test_guarda_dice_la_classe_che_prometteva():
    _s, _n, _u, classi = specchio_vivo(_SPECCHIO)
    d = guarda(_CASA, [], [], {"binary_sensor.perdita_lavatrice": "on"},
               "entita", "binary_sensor.perdita_lavatrice", classi_vive=classi)
    assert d["classe"] == "moisture"
    assert d["stato_leggibile"] == "bagnato"


# --- gli altri campi che lo specchio buttava ------------------------------

def test_lo_specchio_tiene_state_class():
    """Misura di adesso o contatore che sale: e' cio' che dice a quali entita'
    ha senso chiedere una statistica, senza doverlo domandare al recorder.
    Arrivava a ogni avvio e la proiezione lo buttava."""
    from hiris.app.proxy.entity_cache import _to_minimal
    voce = _to_minimal({"entity_id": "sensor.consumo", "state": "12",
                        "attributes": {"state_class": "total_increasing"}})
    assert voce["state_class"] == "total_increasing"


def test_lo_specchio_tiene_gli_attributi_del_meteo():
    """`guarda` su un'entita' meteo rispondeva «sereno» e basta: temperatura,
    umidita', vento e pressione sono attributi di stato, gia' dentro
    `get_states`, e nessuna chiamata nuova serviva per averli."""
    from hiris.app.proxy.entity_cache import _to_minimal
    voce = _to_minimal({"entity_id": "weather.casa", "state": "sunny",
                        "attributes": {"temperature": 24.1, "temperature_unit": "°C",
                                       "humidity": 51, "wind_speed": 7.2}})
    assert voce["attributes"]["temperature"] == 24.1
    assert voce["attributes"]["temperature_unit"] == "°C"
    assert voce["attributes"]["humidity"] == 51


def test_l_impronta_di_esegui_porta_l_unita():
    """«adesso e' a 21, in stanza ci sono 69.8» senza scala e' un numero, non
    un fatto -- e il modello non puo' dedurla, perche' il nucleo gli vieta di
    applicare l'unita' della casa a una singola entita'."""
    from hiris.app.azione.porta import _impronta
    impronta = _impronta(
        {"id": "sensor.esterno", "state": "17.5", "unit": "°C"})
    assert impronta["unit"] == "°C"
    assert _impronta({"id": "x", "state": "on", "unit": ""}) == {"state": "on"}
