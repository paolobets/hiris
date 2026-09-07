"""Ogni nome delle due tabelle degli attributi, pinnato contro la fonte -- non
contro se stesso.

Le tabelle vivono in `home_space/type_vocabulary.py` (metrica 4) e dicono, per
dominio, quali attributi Home Assistant classifica come CAPACITA' (cosa
l'entita' puo' fare) e quali come VALORE CORRENTE (com'e' adesso). Sono una
trascrizione, non un giudizio: chi le scrive copia, e chi le legge deve poter
sapere che sono ancora quelle.

Gli elenchi qui sotto sono **riscritti a mano** dal sorgente al tag `2026.9.1`
-- lo stesso che la casa esegue, mai `dev` -- e NON importati dal vocabolario:
una mutazione della tabella implementativa non deve poter portarsi dietro
anche il metro che dovrebbe scoprirla. E' la stessa disciplina di
`test_feature_tables_pinned_to_source.py`, che fa lo stesso per i bit di
`supported_features`.

**Dove ho letto**, dominio per dominio: `homeassistant/components/<dominio>/
const.py`, classi `<Dominio>EntityCapabilityAttribute` e
`<Dominio>EntityStateAttribute`. Tre eccezioni di forma, verificate una per
una perche' una classe che si chiama in un altro modo e' esattamente il tipo
di cosa che si perde in silenzio:

- `water_heater` le chiama `WaterHeaterCapabilityAttribute` e
  `WaterHeaterStateAttribute`, **senza `Entity`** nel nome;
- `device_tracker` ne ha TRE: `DeviceTrackerEntityStateAttribute`,
  `ScannerEntityStateAttribute` (`ip`/`mac`/`host_name`) e
  `TrackerEntityStateAttribute` (le tre di posizione);
- `script` e `sun` non hanno nessuna classe: i loro nomi sono costanti
  (`components/script/const.py:7-8` + `helpers/script.py:135-136` +
  `homeassistant/const.py:388`, assemblate in
  `components/script/__init__.py:591-604`; `components/sun/const.py:35-43`).
  Sono DICHIARATI lo stesso, e questo e' cio' che conta: la forma non decide
  chi pubblica il significato.

**Due nomi deprecati restano dentro, e la data e' scritta**: `climate.
temperature` verso `TARGET_TEMPERATURE`, rimozione annunciata per `2027.2.0`
(`components/climate/const.py:159-166`); `water_heater.temperature` per
`2027.3.0`. A `2026.9.1` sono ancora quelli che arrivano nel payload -- il
giorno in cui spariscono, questa prova lo dice.
"""
import pytest

from hiris.app.home_space.type_vocabulary import (
    UNIVERSAL_CAPABILITY_ATTRIBUTES,
    UNIVERSAL_CAPABILITY_ATTRIBUTES_ADDED,
    UNIVERSAL_STATE_ATTRIBUTES,
    capability_attribute_tables,
    capability_attributes,
    dropped_capability_attributes,
    state_attribute_tables,
    state_attributes,
)

# --------------------------------------------------------------------------
# `<Dominio>EntityCapabilityAttribute` -- cosa l'entita' PUO' fare.
# --------------------------------------------------------------------------
_PINNED_CAPABILITIES: dict[str, set[str]] = {
    "automation": {"id"},
    "climate": {"hvac_modes", "min_temp", "max_temp", "target_temp_step",
                "min_humidity", "max_humidity", "target_humidity_step",
                "fan_modes", "preset_modes", "swing_modes",
                "swing_horizontal_modes"},
    "cover": {"supported_speeds"},
    "device_tracker": {"tracking_type"},
    "event": {"event_types"},
    "fan": {"preset_modes"},
    "humidifier": {"min_humidity", "max_humidity", "target_humidity_step",
                   "available_modes"},
    "light": {"min_color_temp_kelvin", "max_color_temp_kelvin", "effect_list",
              "supported_color_modes"},
    "media_player": {"source_list", "sound_mode_list"},
    "number": {"min", "max", "step", "mode"},
    "select": {"options"},
    "sensor": {"state_class", "options"},
    "siren": {"available_tones"},
    "text": {"mode", "min", "max", "pattern"},
    "vacuum": {"fan_speed_list"},
    "water_heater": {"min_temp", "max_temp", "target_temp_step",
                     "operation_list"},
}

# --------------------------------------------------------------------------
# `<Dominio>EntityStateAttribute` -- com'e' ADESSO.
# --------------------------------------------------------------------------
_PINNED_STATES: dict[str, set[str]] = {
    "alarm_control_panel": {"code_format", "changed_by", "code_arm_required"},
    "automation": {"last_triggered", "mode", "current", "max"},
    "calendar": {"message", "all_day", "start_time", "end_time", "location",
                 "description"},
    "camera": {"access_token", "model_name", "brand", "motion_detection"},
    "climate": {"current_temperature", "temperature", "target_temp_high",
                "target_temp_low", "current_humidity", "humidity", "fan_mode",
                "hvac_action", "preset_mode", "swing_mode",
                "swing_horizontal_mode"},
    "cover": {"is_closed", "current_position", "current_tilt_position"},
    "device_tracker": {"source_type", "in_zones", "ip", "mac", "host_name",
                       "latitude", "longitude", "gps_accuracy"},
    "event": {"event_type"},
    "fan": {"direction", "oscillating", "percentage", "percentage_step",
            "preset_mode"},
    "humidifier": {"action", "current_humidity", "humidity", "mode"},
    "image": {"access_token"},
    "input_boolean": {"editable"},
    "input_number": {"initial", "editable"},
    "input_select": {"editable"},
    "input_text": {"editable"},
    "light": {"effect", "color_mode", "brightness", "color_temp_kelvin",
              "hs_color", "rgb_color", "xy_color", "rgbw_color",
              "rgbww_color"},
    "lock": {"changed_by", "code_format"},
    "media_player": {"volume_level", "is_volume_muted", "media_content_id",
                     "media_content_type", "media_duration", "media_position",
                     "media_position_updated_at", "media_title",
                     "media_artist", "media_album_name", "media_album_artist",
                     "media_track", "media_series_title", "media_season",
                     "media_episode", "media_channel", "media_playlist",
                     "app_id", "app_name", "source", "sound_mode", "shuffle",
                     "repeat", "group_members", "entity_picture_local"},
    "person": {"editable", "id", "device_trackers", "in_zones", "gps_accuracy",
               "source", "user_id"},
    "remote": {"activity_list", "current_activity"},
    "script": {"last_action", "last_triggered", "mode", "current", "max"},
    "sensor": {"last_reset"},
    "sun": {"azimuth", "elevation", "rising", "next_dawn", "next_dusk",
            "next_midnight", "next_noon", "next_rising", "next_setting"},
    "tag": {"tag_id", "last_scanned_by_device_id"},
    "update": {"auto_update", "display_precision", "installed_version",
               "in_progress", "latest_version", "release_summary",
               "release_url", "skipped_version", "title", "update_percentage"},
    "vacuum": {"fan_speed"},
    "valve": {"is_closed", "current_position"},
    "water_heater": {"current_temperature", "temperature", "target_temp_high",
                     "target_temp_low", "operation_mode", "away_mode"},
    "weather": {"temperature", "apparent_temperature", "dew_point",
                "temperature_unit", "humidity", "ozone", "cloud_coverage",
                "uv_index", "pressure", "pressure_unit", "wind_bearing",
                "wind_gust_speed", "wind_speed", "wind_speed_unit",
                "visibility", "visibility_unit", "precipitation_unit"},
    "zone": {"radius", "passive", "persons", "editable"},
}

# `homeassistant/const.py:464-467` e `:470-483` -- le due classi che valgono su
# QUALUNQUE entita', qualunque sia il suo dominio.
_PINNED_UNIVERSAL_CAPABILITIES = {"group_entities"}
_PINNED_UNIVERSAL_STATES = {
    "assumed_state", "attribution", "device_class", "entity_picture",
    "friendly_name", "icon", "latitude", "longitude", "restored",
    "supported_features", "unit_of_measurement",
}


@pytest.mark.parametrize("domain", sorted(_PINNED_CAPABILITIES),
                         ids=sorted(_PINNED_CAPABILITIES))
def test_every_capability_attribute_matches_the_source(domain):
    """Mutazione (per ogni riga): togliere o rinominare un nome nella tabella
    implementativa -- per esempio `light` senza `supported_color_modes` -- e
    la riga di quel dominio torna rossa, perche' l'atteso qui e' riscritto a
    mano e non deriva dalla tabella che sta verificando."""
    assert capability_attribute_tables()[domain] == _PINNED_CAPABILITIES[domain]


@pytest.mark.parametrize("domain", sorted(_PINNED_STATES),
                         ids=sorted(_PINNED_STATES))
def test_every_state_attribute_matches_the_source(domain):
    """Come sopra, per la meta' «com'e' adesso». Mutazione: togliere
    `hvac_action` da `climate` -- la riga `climate` arrossisce."""
    assert state_attribute_tables()[domain] == _PINNED_STATES[domain]


def test_no_domain_is_pinned_without_being_implemented_and_the_other_way():
    """Non basta «ogni nome pinnato e' corretto»: serve anche «ogni dominio
    implementato e' pinnato». Un dominio aggiunto alla tabella senza una riga
    gemella qui passerebbe questo file senza protezione -- la stessa falsa
    sicurezza che ha lasciato passare tre mutazioni sulle tabelle dei bit.

    Mutazione: aggiungere `"lawn_mower": frozenset({"activity_list"})` a
    `_CAPABILITY_ATTRIBUTE_TABLES` senza toccare questo file -- il test torna
    rosso sulla differenza fra i due insiemi di domini."""
    assert set(capability_attribute_tables()) == set(_PINNED_CAPABILITIES)
    assert set(state_attribute_tables()) == set(_PINNED_STATES)


def test_the_two_classes_that_hold_for_every_entity_are_pinned_too():
    """`EntityCapabilityAttribute` e `EntityStateAttribute` di
    `homeassistant/const.py` non appartengono a nessun dominio: si perderebbero
    fra le righe per dominio, e con loro il gruppo e l'`entity_picture` che
    qualunque entita' puo' portare.

    Mutazione: togliere `entity_picture` da `UNIVERSAL_STATE_ATTRIBUTES` -- il
    test arrossisce, e a valle quell'attributo smetterebbe di essere
    riconosciuto come dichiarato."""
    assert UNIVERSAL_CAPABILITY_ATTRIBUTES.value == _PINNED_UNIVERSAL_CAPABILITIES
    assert UNIVERSAL_STATE_ATTRIBUTES.value == _PINNED_UNIVERSAL_STATES


def test_the_imported_tables_declare_the_version_they_come_from():
    """Un fatto importato senza la versione da cui viene non si sa vecchio, e
    un fatto che non si sa vecchio si continua a credere per sempre. Il tipo
    `Imported` lo esige alla costruzione; questa prova verifica che la
    versione sia quella del sorgente letto, non una qualunque.

    Mutazione: costruire una delle due tabelle con `Ours(...)` invece di
    `Imported(...)` -- il test torna rosso su `ha_version`
    (`AttributeError`)."""
    from hiris.app.home_space import type_vocabulary as tv
    for domain in _PINNED_CAPABILITIES:
        field = tv._vocabulary.field(domain, None, tv.CAPABILITY_ATTRIBUTES)
        assert field.ha_version == "2026.9.1"
        assert "2026.9.1" in field.source
    for domain in _PINNED_STATES:
        field = tv._vocabulary.field(domain, None, tv.STATE_ATTRIBUTES)
        assert field.ha_version == "2026.9.1"


# --------------------------------------------------------------------------
# I DUE GIUDIZI NOSTRI -- dichiarati come nostri, fuori dalla trascrizione.
# --------------------------------------------------------------------------

def test_the_legacy_group_key_survives_and_it_is_declared_as_our_judgment():
    """Il gruppo di luci di questa casa esce sotto `entity_id`, non
    `group_entities`, anche a `2026.9.1`: `components/group/entity.py:43-45`
    nomina entrambe (`_unrecorded_attributes = frozenset({ATTR_ENTITY_ID,
    EntityCapabilityAttribute.GROUP_ENTITIES})`). Una tabella costruita solo
    dagli enum nuovi perderebbe `light.lampadario_sala_da_pranzo` IN SILENZIO.

    E il nome aggiunto sta in un campo `Ours` separato, non dentro la
    trascrizione: se l'avessi infilato in `UNIVERSAL_CAPABILITY_ATTRIBUTES`,
    la prova pinnata qui sopra avrebbe dovuto mentire con me.

    Mutazione: togliere `entity_id` da `UNIVERSAL_CAPABILITY_ATTRIBUTES_ADDED`
    -- il test torna rosso su `assert "entity_id" in capability_attributes(
    "light")`."""
    assert "entity_id" in UNIVERSAL_CAPABILITY_ATTRIBUTES_ADDED.value
    assert "entity_id" not in UNIVERSAL_CAPABILITY_ATTRIBUTES.value
    assert "entity_id" in capability_attributes("light")
    assert "entity_id" in capability_attributes("sensor")


def test_number_mode_is_ours_to_drop_and_the_reason_travels_with_it():
    """`number.mode` e' nella fonte fra le capacita', e ne esce per giudizio
    nostro: «Defines how the number should be displayed in the UI»
    (`docs/core/entity/number.md:17`) e la casa che ne traduce i valori in
    `Automatico`/`Input field`/`Cursore`. Due fonti indipendenti, non
    un'opinione.

    **Ma resta un attributo DICHIARATO**: passa fra i valori correnti, non fra
    i non interpretati. Scavalcare Home Assistant sulla presentazione non ci
    autorizza a dire che non sappiamo cosa sia -- sarebbe la seconda bugia
    presa per curare la prima.

    Mutazione: togliere `mode` da `_CAPABILITY_ATTRIBUTES_DROPPED["number"]`
    -- il test torna rosso su `assert "mode" not in capability_attributes(
    "number")`."""
    assert "mode" in _PINNED_CAPABILITIES["number"]
    assert "mode" not in capability_attributes("number")
    assert "mode" in state_attributes("number")


def test_every_dropped_capability_carries_a_written_reason():
    """Un'eccezione senza motivo e' un permesso, e un permesso non si rilegge
    mai. Vale qui come per le eccezioni del vocabolario dei tipi.

    Mutazione: mettere `""` come ragione di `number.mode` -- arrossisce."""
    dropped = dropped_capability_attributes()
    assert dropped, "nessuna eccezione dichiarata: questa prova sarebbe muta"
    for domain, names in dropped.items():
        for name, reason in names.items():
            assert len(reason) > 40, (
                f"la ragione per cui `{domain}.{name}` esce dalle capacita' "
                "non spiega niente")


def test_alarm_code_attributes_follow_home_assistant_even_where_it_grates():
    """Il caso opposto, e la ragione per cui i due esiti sono coerenti.

    `code_format` e `code_arm_required` sono funzionalmente dei LIMITI («serve
    un codice per inserire l'allarme?») e non cambiano mai -- verrebbe da
    metterli fra le capacita'. Restano invece fra i valori, dove Home
    Assistant li mette (`AlarmControlPanelEntityStateAttribute`), perche' la
    regola e' che **il fornitore comanda sulla classificazione finche' non e'
    smentito da una fonte, non finche' non e' smentito dal nostro senso**. Su
    `number.mode` avevo due fonti; qui nessuna.

    Mutazione: promuoverli a capacita' del dominio -- il test arrossisce, e a
    ragione: sarebbe un giudizio nostro travestito da trascrizione."""
    declared = state_attributes("alarm_control_panel")
    assert "code_format" in declared
    assert "code_arm_required" in declared
    assert "code_format" not in capability_attributes("alarm_control_panel")
