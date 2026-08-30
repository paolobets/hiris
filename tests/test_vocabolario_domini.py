"""I nomi italiani delle tipologie di Home Assistant.

Il digesto conta le cose per tipo ("3 luci, 2 tapparelle"). I tipi che non
sapeva nominare li stampava com'erano: "4 water_heater", "2 lawn_mower". Non
e' un difetto estetico -- e' HIRIS che parla la lingua della macchina in un
prodotto che esiste per parlare quella di casa, e sono anche i tipi meno
ovvi, quelli in cui una parola inglese aiuta meno.

L'elenco delle tipologie NON e' inventato: sono le 45 piattaforme dichiarate
da `homeassistant/generated/entity_platforms.py` piu' i domini degli helper e
delle cose che HA crea da se' (`input_*`, `counter`, `timer`, `zone`, `sun`,
...). Ognuno e' stato verificato come componente vero del sorgente di Home
Assistant, non ricordato.
"""
from hiris.app.casa.nucleo import _DOMAIN_NAMES, _domain_name

# Le 45 piattaforme di `homeassistant/generated/entity_platforms.py`,
# copiate dalla fonte. Se HA ne aggiunge una, questa prova lo dice il giorno
# in cui qualcuno aggiorna l'elenco -- e non il giorno in cui un utente legge
# "2 wake_word" nel digesto.
_PIATTAFORME_HA = (
    "ai_task", "air_quality", "alarm_control_panel", "assist_satellite",
    "binary_sensor", "button", "calendar", "camera", "climate", "conversation",
    "cover", "date", "datetime", "device_tracker", "event", "fan",
    "geo_location", "humidifier", "image", "image_processing", "infrared",
    "lawn_mower", "light", "lock", "media_player", "notify", "number",
    "radio_frequency", "remote", "scene", "select", "sensor", "siren", "stt",
    "switch", "text", "time", "todo", "tts", "update", "vacuum", "valve",
    "wake_word", "water_heater", "weather",
)

# I domini che non sono piattaforme ma esistono come entita' in ogni casa:
# gli helper che l'utente crea dall'interfaccia e le cose che HA crea da se'.
_DOMINI_NON_PIATTAFORMA = (
    "automation", "script", "person", "zone", "group", "sun", "tag", "plant",
    "counter", "timer", "schedule", "persistent_notification",
    "input_boolean", "input_number", "input_select", "input_text",
    "input_datetime", "input_button",
)


def test_ogni_piattaforma_di_home_assistant_ha_un_nome_italiano():
    senza = sorted(d for d in _PIATTAFORME_HA if d not in _DOMAIN_NAMES)
    assert senza == [], f"tipologie che il digesto stamperebbe in inglese: {senza}"


def test_ogni_dominio_non_piattaforma_ha_un_nome_italiano():
    senza = sorted(d for d in _DOMINI_NON_PIATTAFORMA if d not in _DOMAIN_NAMES)
    assert senza == [], f"tipologie che il digesto stamperebbe in inglese: {senza}"


def test_il_vocabolario_non_contiene_domini_inventati():
    """Il contrario della prova sopra, e serve quanto quella: un nome per un
    dominio che in Home Assistant non esiste e' una riga che nessuno leggera'
    mai, e nessuno la cancellera' perche' sembra utile."""
    conosciuti = set(_PIATTAFORME_HA) | set(_DOMINI_NON_PIATTAFORMA)
    inventati = sorted(d for d in _DOMAIN_NAMES if d not in conosciuti)
    assert inventati == [], f"tipologie che Home Assistant non ha: {inventati}"


def test_singolare_e_plurale_sono_dichiarati_non_dedotti():
    """L'italiano non fa il plurale aggiungendo una lettera: «aspirapolvere»
    resta «aspirapolvere», «analisi» resta «analisi». Dedurlo produrrebbe
    «aspirapolveres». Sono dichiarati uno per uno, ed e' il motivo per cui il
    vocabolario e' una tabella e non una funzione."""
    for dominio, coppia in _DOMAIN_NAMES.items():
        assert isinstance(coppia, tuple) and len(coppia) == 2, dominio
        singolare, plurale = coppia
        assert singolare.strip() and plurale.strip(), dominio


def test_un_dominio_sconosciuto_esce_com_e_invece_di_sparire():
    """Home Assistant puo' aggiungere una piattaforma domani. Meglio «2
    quantum_flux» che una riga che sparisce: un conteggio mancante e' una
    casa raccontata piu' piccola di com'e'."""
    assert _domain_name("quantum_flux", 2) == "quantum_flux"


def test_i_nomi_non_ripetono_una_parola_gia_presa():
    """CONSISTENZA: «etichetta» in HIRIS significa gia' un'altra cosa -- le
    label che l'utente scrive in Home Assistant, che ora escono da `guarda` e
    si cercano. Chiamare cosi' anche il dominio `tag` (i bollini NFC) darebbe
    due significati alla stessa parola, nella stessa risposta."""
    assert "etichetta" not in _DOMAIN_NAMES["tag"][0]
