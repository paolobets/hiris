"""Cio' che QUESTA casa pubblica per rendere uno stato -- misurato, non inventato.

**Perche' un modulo e non un dizionario per prova.** Dall'08/09/2026 le
quattro tabelle scritte a mano di `home_space/topology.py` non esistono piu'
(spec §6):
le parole con cui uno stato si legge le dice Home Assistant, e ogni prova che
tocca uno `stato_leggibile` ha bisogno di quelle chiavi. Sei prove che se le
scrivessero da sole sarebbero sei case diverse, e la prima a divergere non
sarebbe rossa: sarebbe verde su una casa che non esiste.

**La fonte.** `frontend/get_translations`, `category: "entity_component"`,
lingua `it`, letto dalla casa vera l'08/09/2026 (Home Assistant `2026.9.1`).
Delle 801 chiavi restano qui **191** che rendono uno stato (`.state.{valore}`)
piu' le **9** di `hvac_action` (`.state_attributes.hvac_action.state.{valore}`,
un'altra CESTA -- non uno stato) -- **200 chiavi in tutto** (corretto R4,
revisione del tratto v3.23.0..HEAD, 08/09/2026: questo paragrafo diceva "200
che rendono uno stato", contando l'hvac_action due volte; misurato:
`len([k for k in PUBLISHED_STATE_WORDS if ".state." in k and "state_attributes"
not in k]) == 191`). Le sole che un lettore di stati usa. Le altre (nomi delle
classi, nomi degli attributi, altri attributi di stato) non sono tolte per
opinione: nessuna prova le guarda, e una fixture che porta cio' che nessuno
legge invecchia senza che nessuno se ne accorga.

**NON si rigenera da sola** (corretto R5, revisione del tratto
v3.23.0..HEAD, 08/09/2026: questo paragrafo affermava una procedura che non
esiste). `scripts/istantaneo_pubblicato.py` legge le STESSE chiavi HA per
l'istantaneo del censore (`tests/data/pubblicato-dalla-casa.json`), ma non
scrive MAI questo file: sono due letture indipendenti della stessa fonte, non
una rigenerazione dell'una dall'altra, e nessuno strumento aggiorna
`PUBLISHED_STATE_WORDS` in automatico. **Si corregge a mano**, quando la casa
cambia parole -- e la sola verifica dal vivo che le due letture concordino e'
`test_l_istantaneo_e_questa_fixture_nominano_gli_stessi_stati` in
`test_type_census_live.py`, che confronta i TIPI derivabili da queste chiavi
(`derived_state_keys()` sotto) con `stati_per_tipo` dell'istantaneo -- non le
PAROLE: un `triggered` ridetto «Scattato» invece di «Innescato» da Home
Assistant non farebbe arrossire quella prova, perche' nessuna prova dal vivo
confronta le PAROLE di questo file con quelle che la casa dice oggi. Resta un
limite dichiarato, non chiuso da questa correzione: solo la STRUTTURA (quali
stati esistono per tipo) e' verificata dal vivo, il TESTO italiano no.
"""

#: L'esito etichettato che i lettori si aspettano -- la stessa forma che
#: `StateTranslations.read` restituisce. Le prove non costruiscono un
#: dizionario nudo: passare le sole risorse vorrebbe dire saltare proprio la
#: distinzione fra «non ho potuto chiedere» e «questo stato non ha resa», che
#: e' cio' che questa fetta esiste per dare.
HOUSE_LANGUAGE = "it"

PUBLISHED_STATE_WORDS = {
    'component.alarm_control_panel.entity_component._.state.armed': 'Attivo',
    'component.alarm_control_panel.entity_component._.state.armed_away': 'Attivo fuori casa',
    'component.alarm_control_panel.entity_component._.state.armed_custom_bypass':
        'Attivo con esclusione personalizzata',
    'component.alarm_control_panel.entity_component._.state.armed_home': 'Attivo in casa',
    'component.alarm_control_panel.entity_component._.state.armed_night': 'Attivo notte',
    'component.alarm_control_panel.entity_component._.state.armed_vacation': 'Attivo in vacanza',
    'component.alarm_control_panel.entity_component._.state.arming': 'In attivazione',
    'component.alarm_control_panel.entity_component._.state.disarmed': 'Disattivo',
    'component.alarm_control_panel.entity_component._.state.disarming': 'In disattivazione',
    'component.alarm_control_panel.entity_component._.state.pending': 'In attesa',
    'component.alarm_control_panel.entity_component._.state.triggered': 'Innescato',
    'component.assist_satellite.entity_component._.state.idle': 'Inattivo',
    'component.assist_satellite.entity_component._.state.listening': 'In ascolto',
    'component.assist_satellite.entity_component._.state.processing': 'Processing',
    'component.assist_satellite.entity_component._.state.responding': 'Responding',
    'component.automation.entity_component._.state.off': 'Spento',
    'component.automation.entity_component._.state.on': 'Acceso',
    'component.binary_sensor.entity_component._.state.off': 'Spento',
    'component.binary_sensor.entity_component._.state.on': 'Acceso',
    'component.binary_sensor.entity_component.battery.state.off': 'Normale',
    'component.binary_sensor.entity_component.battery.state.on': 'Basso/a',
    'component.binary_sensor.entity_component.battery_charging.state.off': 'Non in carica',
    'component.binary_sensor.entity_component.battery_charging.state.on': 'In carica',
    'component.binary_sensor.entity_component.carbon_monoxide.state.off': 'Assente',
    'component.binary_sensor.entity_component.carbon_monoxide.state.on': 'Rilevato',
    'component.binary_sensor.entity_component.cold.state.off': 'Normale',
    'component.binary_sensor.entity_component.cold.state.on': 'Freddo',
    'component.binary_sensor.entity_component.connectivity.state.off': 'Disconnesso',
    'component.binary_sensor.entity_component.connectivity.state.on': 'Connesso',
    'component.binary_sensor.entity_component.door.state.off': 'Chiuso',
    'component.binary_sensor.entity_component.door.state.on': 'Aperto',
    'component.binary_sensor.entity_component.garage_door.state.off': 'Chiuso',
    'component.binary_sensor.entity_component.garage_door.state.on': 'Aperto',
    'component.binary_sensor.entity_component.gas.state.off': 'Assente',
    'component.binary_sensor.entity_component.gas.state.on': 'Rilevato',
    'component.binary_sensor.entity_component.heat.state.off': 'Normale',
    'component.binary_sensor.entity_component.heat.state.on': 'Caldo',
    'component.binary_sensor.entity_component.light.state.off': 'Nessuna luce',
    'component.binary_sensor.entity_component.light.state.on': 'Luce rilevata',
    'component.binary_sensor.entity_component.lock.state.off': 'Bloccato/a',
    'component.binary_sensor.entity_component.lock.state.on': 'Sbloccato/a',
    'component.binary_sensor.entity_component.moisture.state.off': 'Asciutto',
    'component.binary_sensor.entity_component.moisture.state.on': 'Bagnato',
    'component.binary_sensor.entity_component.motion.state.off': 'Assente',
    'component.binary_sensor.entity_component.motion.state.on': 'Rilevato',
    'component.binary_sensor.entity_component.moving.state.off': 'Non si muove',
    'component.binary_sensor.entity_component.moving.state.on': 'In movimento',
    'component.binary_sensor.entity_component.occupancy.state.off': 'Assente',
    'component.binary_sensor.entity_component.occupancy.state.on': 'Rilevato',
    'component.binary_sensor.entity_component.opening.state.off': 'Chiuso',
    'component.binary_sensor.entity_component.opening.state.on': 'Aperto',
    'component.binary_sensor.entity_component.plug.state.off': 'Scollegato',
    'component.binary_sensor.entity_component.plug.state.on': 'Collegato',
    'component.binary_sensor.entity_component.power.state.off': 'Spento',
    'component.binary_sensor.entity_component.power.state.on': 'Acceso',
    'component.binary_sensor.entity_component.presence.state.off': 'Fuori casa',
    'component.binary_sensor.entity_component.presence.state.on': 'In casa',
    'component.binary_sensor.entity_component.problem.state.off': 'OK',
    'component.binary_sensor.entity_component.problem.state.on': 'Problema',
    'component.binary_sensor.entity_component.running.state.off': 'Non in esecuzione',
    'component.binary_sensor.entity_component.running.state.on': 'In esecuzione',
    'component.binary_sensor.entity_component.safety.state.off': 'Sicuro',
    'component.binary_sensor.entity_component.safety.state.on': 'Non Sicuro',
    'component.binary_sensor.entity_component.smoke.state.off': 'Assente',
    'component.binary_sensor.entity_component.smoke.state.on': 'Rilevato',
    'component.binary_sensor.entity_component.sound.state.off': 'Assente',
    'component.binary_sensor.entity_component.sound.state.on': 'Rilevato',
    'component.binary_sensor.entity_component.tamper.state.off': 'Assente',
    'component.binary_sensor.entity_component.tamper.state.on': 'Rilevata manomissione',
    'component.binary_sensor.entity_component.update.state.off': 'Aggiornato',
    'component.binary_sensor.entity_component.update.state.on': 'Aggiornamento disponibile',
    'component.binary_sensor.entity_component.vibration.state.off': 'Assente',
    'component.binary_sensor.entity_component.vibration.state.on': 'Rilevato',
    'component.binary_sensor.entity_component.window.state.off': 'Chiuso',
    'component.binary_sensor.entity_component.window.state.on': 'Aperto',
    'component.calendar.entity_component._.state.off': 'Spento',
    'component.calendar.entity_component._.state.on': 'Acceso',
    'component.camera.entity_component._.state.idle': 'Inattivo',
    'component.camera.entity_component._.state.recording': 'In registrazione',
    'component.camera.entity_component._.state.streaming': 'In trasmissione',
    'component.climate.entity_component._.state.auto': 'Automatico',
    'component.climate.entity_component._.state.cool': 'Freddo',
    'component.climate.entity_component._.state.dry': 'Deumidificazione',
    'component.climate.entity_component._.state.fan_only': 'Ventilazione',
    'component.climate.entity_component._.state.heat': 'Riscaldamento',
    'component.climate.entity_component._.state.heat_cool': 'Caldo/Freddo',
    'component.climate.entity_component._.state.off': 'Spento',
    'component.climate.entity_component._.state_attributes.hvac_action.name': 'Azione in corso',
    'component.climate.entity_component._.state_attributes.hvac_action.state.cooling':
        'Raffreddando',
    'component.climate.entity_component._.state_attributes.hvac_action.state.defrosting':
        'Defrosting',
    'component.climate.entity_component._.state_attributes.hvac_action.state.drying':
        'In deumidificazione',
    'component.climate.entity_component._.state_attributes.hvac_action.state.fan': 'Ventilatore',
    'component.climate.entity_component._.state_attributes.hvac_action.state.heating':
        'Riscaldamento',
    'component.climate.entity_component._.state_attributes.hvac_action.state.idle': 'Inattivo',
    'component.climate.entity_component._.state_attributes.hvac_action.state.off': 'Spento',
    'component.climate.entity_component._.state_attributes.hvac_action.state.preheating':
        'Preriscaldamento',
    'component.cover.entity_component._.state.closed': 'Chiuso',
    'component.cover.entity_component._.state.closing': 'In chiusura',
    'component.cover.entity_component._.state.open': 'Aperto',
    'component.cover.entity_component._.state.opening': 'In apertura',
    'component.cover.entity_component._.state.stopped': 'Fermato/a',
    'component.device_tracker.entity_component._.state.home': 'In casa',
    'component.device_tracker.entity_component._.state.not_home': 'Fuori casa',
    'component.fan.entity_component._.state.off': 'Spento',
    'component.fan.entity_component._.state.on': 'Acceso',
    'component.group.entity_component._.state.closed': 'Chiuso',
    'component.group.entity_component._.state.home': 'In casa',
    'component.group.entity_component._.state.locked': 'Bloccato/a',
    'component.group.entity_component._.state.not_home': 'Fuori casa',
    'component.group.entity_component._.state.off': 'Spento',
    'component.group.entity_component._.state.ok': 'OK',
    'component.group.entity_component._.state.on': 'Acceso',
    'component.group.entity_component._.state.open': 'Aperto',
    'component.group.entity_component._.state.problem': 'Problema',
    'component.group.entity_component._.state.unlocked': 'Sbloccato/a',
    'component.humidifier.entity_component._.state.off': 'Spento',
    'component.humidifier.entity_component._.state.on': 'Acceso',
    'component.input_boolean.entity_component._.state.off': 'Spento',
    'component.input_boolean.entity_component._.state.on': 'Acceso',
    'component.lawn_mower.entity_component._.state.docked': 'Alla base',
    'component.lawn_mower.entity_component._.state.error': 'Errore',
    'component.lawn_mower.entity_component._.state.mowing': 'Falciatura',
    'component.lawn_mower.entity_component._.state.paused': 'In pausa',
    'component.lawn_mower.entity_component._.state.returning': 'Ritornando',
    'component.light.entity_component._.state.off': 'Spento',
    'component.light.entity_component._.state.on': 'Acceso',
    'component.lock.entity_component._.state.jammed': 'Inceppata',
    'component.lock.entity_component._.state.locked': 'Bloccato/a',
    'component.lock.entity_component._.state.locking': 'In chiusura',
    'component.lock.entity_component._.state.open': 'Aperto',
    'component.lock.entity_component._.state.opening': 'In apertura',
    'component.lock.entity_component._.state.unlocked': 'Sbloccato/a',
    'component.lock.entity_component._.state.unlocking': 'In apertura',
    'component.media_player.entity_component._.state.buffering': 'Precaricamento',
    'component.media_player.entity_component._.state.idle': 'Inattivo',
    'component.media_player.entity_component._.state.off': 'Spento',
    'component.media_player.entity_component._.state.on': 'Acceso',
    'component.media_player.entity_component._.state.paused': 'In pausa',
    'component.media_player.entity_component._.state.playing': 'In esecuzione',
    'component.media_player.entity_component._.state.standby': 'In attesa',
    'component.person.entity_component._.state.home': 'In casa',
    'component.person.entity_component._.state.not_home': 'Fuori casa',
    'component.remote.entity_component._.state.off': 'Spento',
    'component.remote.entity_component._.state.on': 'Acceso',
    'component.schedule.entity_component._.state.off': 'Spento',
    'component.schedule.entity_component._.state.on': 'Acceso',
    'component.script.entity_component._.state.off': 'Spento',
    'component.script.entity_component._.state.on': 'Acceso',
    'component.sensor.entity_component._.state.off': 'Spento',
    'component.sensor.entity_component._.state.on': 'Acceso',
    'component.siren.entity_component._.state.off': 'Spento',
    'component.siren.entity_component._.state.on': 'Acceso',
    'component.sun.entity_component._.state.above_horizon': "Sopra l'orizzonte",
    'component.sun.entity_component._.state.below_horizon': "Sotto l'orizzonte",
    'component.switch.entity_component._.state.off': 'Spento',
    'component.switch.entity_component._.state.on': 'Acceso',
    'component.switch.entity_component.outlet.state.off': 'Spento',
    'component.switch.entity_component.outlet.state.on': 'Acceso',
    'component.switch.entity_component.switch.state.off': 'Spento',
    'component.switch.entity_component.switch.state.on': 'Acceso',
    'component.timer.entity_component._.state.active': 'Attivo',
    'component.timer.entity_component._.state.idle': 'Inattivo',
    'component.timer.entity_component._.state.paused': 'In pausa',
    'component.update.entity_component._.state.off': 'Aggiornato',
    'component.update.entity_component._.state.on': 'Aggiornamento disponibile',
    'component.vacuum.entity_component._.state.cleaning': 'In pulizia',
    'component.vacuum.entity_component._.state.docked': 'Alla base',
    'component.vacuum.entity_component._.state.error': 'Errore',
    'component.vacuum.entity_component._.state.idle': 'Inattivo',
    'component.vacuum.entity_component._.state.off': 'Spento',
    'component.vacuum.entity_component._.state.on': 'Acceso',
    'component.vacuum.entity_component._.state.paused': 'In pausa',
    'component.vacuum.entity_component._.state.returning': 'Ritornando alla base',
    'component.valve.entity_component._.state.closed': 'Chiuso',
    'component.valve.entity_component._.state.closing': 'In chiusura',
    'component.valve.entity_component._.state.open': 'Aperto',
    'component.valve.entity_component._.state.opening': 'In apertura',
    'component.valve.entity_component._.state.stopped': 'Fermato/a',
    'component.water_heater.entity_component._.state.eco': 'Eco',
    'component.water_heater.entity_component._.state.electric': 'Elettrico',
    'component.water_heater.entity_component._.state.gas': 'Gas',
    'component.water_heater.entity_component._.state.heat_pump': 'Heat pump',
    'component.water_heater.entity_component._.state.high_demand': 'High demand',
    'component.water_heater.entity_component._.state.off': 'Spento',
    'component.water_heater.entity_component._.state.performance': 'Prestazione',
    'component.weather.entity_component._.state.clear-night': 'Sereno, notte',
    'component.weather.entity_component._.state.cloudy': 'Nuvoloso',
    'component.weather.entity_component._.state.exceptional': 'Eccezionale',
    'component.weather.entity_component._.state.fog': 'Nebbia',
    'component.weather.entity_component._.state.hail': 'Grandine',
    'component.weather.entity_component._.state.lightning': 'Temporale',
    'component.weather.entity_component._.state.lightning-rainy': 'Temporale, piovoso',
    'component.weather.entity_component._.state.partlycloudy': 'Parzialmente nuvoloso',
    'component.weather.entity_component._.state.pouring': 'Rovescio',
    'component.weather.entity_component._.state.rainy': 'Piovoso',
    'component.weather.entity_component._.state.snowy': 'Nevoso',
    'component.weather.entity_component._.state.snowy-rainy': 'Nevoso, piovoso',
    'component.weather.entity_component._.state.sunny': 'Soleggiato',
    'component.weather.entity_component._.state.windy': 'Ventoso',
    'component.weather.entity_component._.state.windy-variant': 'Ventoso, nuvoloso',
}


def derived_state_keys() -> dict[str, dict[str, list[str]]]:
    """`{dominio: {classe_o_"_": [stati]}}` derivato dalle chiavi di
    `PUBLISHED_STATE_WORDS` -- la stessa FORMA di `stati_per_tipo`
    nell'istantaneo del censore (`tests/data/pubblicato-dalla-casa.json`).

    Serve alla sola verifica dal vivo che questa fixture puo' avere
    (`test_type_census_live.py`): NON le parole -- questa funzione non le
    tocca -- ma la STRUTTURA, cioe' quali stati esistono per quale tipo. Le
    chiavi di `hvac_action` (`.state_attributes.hvac_action.state.*`) restano
    fuori: sono un'altra cesta (l'attributo di uno stato), non lo stato di
    un'entita', e l'istantaneo del censore non le porta in `stati_per_tipo`.
    """
    result: dict[str, dict[str, list[str]]] = {}
    for key in PUBLISHED_STATE_WORDS:
        if "state_attributes" in key:
            continue
        parts = key.split(".")
        # component.<dominio>.entity_component.<classe>.state.<valore>
        domain, device_class, value = parts[1], parts[3], parts[-1]
        result.setdefault(domain, {}).setdefault(device_class, [])
        if value not in result[domain][device_class]:
            result[domain][device_class].append(value)
    return result


def house_translations(resources=None) -> dict:
    """L'esito «lette» con le parole di questa casa.

    `resources` permette a una prova di restringere o rompere di proposito la
    tabella -- e' cio' che serve per far arrossire la ricostruzione della
    coppia quando manca una delle due chiavi.
    """
    return {"lette": True, "lingua": HOUSE_LANGUAGE,
            "risorse": dict(PUBLISHED_STATE_WORDS if resources is None else resources)}


def unread_translations(reason: str = "Home Assistant non ha risposto") -> dict:
    """L'esito «non lette», col motivo dichiarato da chi ha fallito."""
    return {"lette": False, "motivo": reason}
