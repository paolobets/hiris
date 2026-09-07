"""**La prova che decide se l'altra meta' del requisito e' soddisfatta.**

Il requisito, dettato dal proprietario il 07/09/2026
(`docs/design/2026-09-07-l-anagrafe-dei-tipi.md` §13):

    «Anche il modello, quindi, con azione deve saper cambiare colore
    all'Alberello o abbassare la luminosita'.»

e il metro del §12: **poter fare cio' che Home Assistant sa fare con lui.**

La forma di questo file e' la tabella del capitolato, riga per riga:

    cambia colore all'Alberello                  ->  funziona
    abbassa la luminosita' dell'Alberello        ->  funziona
    cambia colore alla presa della lavatrice     ->  rifiutato da NOI, detto
    metti l'Alberello a 8000 K                   ->  funziona (la lampadina
                                                     arriva a 9000, anche se
                                                     il cursore generico si
                                                     ferma a 6500)

piu' il caso che la tabella non nomina e che e' il vero banco di prova del
controllo nuovo: **una luce che fa solo acceso/spento**. La presa della
lavatrice si rifiuta gia' sul dominio (e' uno `switch`, e `light.turn_on` non
si applica), quindi da sola non dimostrerebbe niente di nuovo; una luce del
dominio giusto che quel colore non lo sa fare, si'.

**Tutti i payload sono veri e misurati**, mai inventati: `GET /api/states` e
`GET /api/services` su `192.168.1.95:8123`, Home Assistant `2026.9.1`, il
07/09/2026 alle 21:28. E si passa sempre dalla CATENA VERA -- `_to_minimal`,
la costruzione del registro da `/api/services`, `verification` -- mai da un
dizionario di attributi scritto a mano: una finta che scrivesse gli attributi
piatti invece delle ceste renderebbe questo file verde e cieco insieme.

Nessuna rete: la casa arriva qui come dato, esattamente come nella verifica
vera. E nessuna azione parte mai -- ogni prova si ferma al verdetto.
"""
import pytest

from hiris.app.action.registry import ServiceRegistry, field_applies
from hiris.app.action.verification import verification
from hiris.app.home_space import type_vocabulary
from hiris.app.home_space.queries import commands_for, view
from hiris.app.home_space.topology import live_mirror
from hiris.app.proxy.entity_cache import _to_minimal, disclosable_attributes

# --------------------------------------------------------------------------
# I PAYLOAD VERI
# --------------------------------------------------------------------------

# L'Alberello, acceso, il 07/09/2026 alle 21:28. `supported_color_modes` dice
# che sa fare temperatura di colore E tinta; i due limiti in kelvin danno il
# campo VERO (1500-9000), contro i 2000-6500 del cursore generico del
# servizio; `supported_features: 36` accende i bit 4 (effetti) e 32
# (transizione).
LIGHT_ALBERELLO = {
    "entity_id": "light.alberello", "state": "on",
    "last_changed": "2026-09-07T19:09:29.942505+00:00",
    "attributes": {
        "min_color_temp_kelvin": 1500, "max_color_temp_kelvin": 9000,
        "effect_list": ["effect_colorloop", "effect_pulse", "effect_stop"],
        "supported_color_modes": ["color_temp", "hs"],
        "effect": None, "color_mode": "hs", "brightness": 80,
        "color_temp_kelvin": None, "hs_color": [209.924, 94.929],
        "rgb_color": [13, 134, 255], "xy_color": [0.143, 0.147],
        "friendly_name": "Alberello", "supported_features": 36,
    },
}

# Una delle QUARANTA luci `onoff` di questa casa -- la maggioranza assoluta.
# `supported_features: 0` non e' un'assenza: e' un numero vero che dice «non
# so fare niente di piu'». E' il caso che il controllo nuovo esiste per
# chiudere: prima di oggi «cambia colore alla luce della cucina» partiva
# davvero e tornava come errore tecnico di Home Assistant.
LIGHT_CUCINA = {
    "entity_id": "light.cucina_cucina", "state": "off",
    "last_changed": "2026-09-07T16:02:11.000000+00:00",
    "attributes": {
        "supported_color_modes": ["onoff"], "color_mode": None,
        "friendly_name": "Cucina", "supported_features": 0,
    },
}

# La presa della lavatrice, parola per parola dalla casa: uno `switch`, non
# una luce. Nessun `supported_color_modes`, nessun `supported_features`.
SWITCH_LAVATRICE = {
    "entity_id": "switch.lavatrice", "state": "on",
    "last_changed": "2026-09-06T11:23:22.020438+00:00",
    "attributes": {
        "device_class": "outlet", "icon": "mdi:power-plug-outline",
        "friendly_name": "Lavatrice",
    },
}

# Un sensore enumerato: `options` dice cosa il suo STATO potra' valere.
SENSOR_BACKUP = {
    "entity_id": "sensor.backup_backup_manager_state", "state": "idle",
    "last_changed": "2026-09-07T05:00:00.000000+00:00",
    "attributes": {
        "options": ["idle", "create_backup", "blocked", "receive_backup",
                    "restore_backup"],
        "friendly_name": "Stato del gestore dei backup",
    },
}

# Un `select`: `options` dice cosa gli si puo' IMPORRE con
# `select.select_option`. Stesso nome, altra domanda.
SELECT_MODO = {
    "entity_id": "select.modo_di_funzionamento", "state": "auto",
    "last_changed": "2026-09-07T05:00:00.000000+00:00",
    "attributes": {
        "options": ["auto", "manuale", "vacanza"],
        "friendly_name": "Modo di funzionamento",
    },
}

# `/api/services` come la casa lo consegna, ridotto ai servizi che queste
# prove esercitano -- ogni `filter` e ogni `selector` copiati parola per
# parola. `additional_fields` e' una SEZIONE vera (Home Assistant >= 2024.6):
# resta qui perche' il registro la deve appiattire, e `rgbw_color` sta dentro
# di lei.
HA_SERVICES = [
    {"domain": "light", "services": {
        "turn_on": {
            "target": {"entity": [{"domain": ["light"]}]},
            "fields": {
                "transition": {
                    "filter": {"supported_features": [32]},
                    "selector": {"number": {"min": 0.0, "max": 300.0,
                                            "unit_of_measurement": "seconds",
                                            "step": 1.0, "mode": "slider"}}},
                "rgb_color": {
                    "filter": {"attribute": {"supported_color_modes": [
                        "hs", "xy", "rgb", "rgbw", "rgbww"]}},
                    "example": "[255, 100, 100]",
                    "selector": {"color_rgb": {}}},
                "color_temp_kelvin": {
                    "filter": {"attribute": {"supported_color_modes": [
                        "color_temp", "hs", "xy", "rgb", "rgbw", "rgbww"]}},
                    "selector": {"color_temp": {"unit": "kelvin",
                                                "min": 2000, "max": 6500}}},
                "brightness_pct": {
                    "filter": {"attribute": {"supported_color_modes": [
                        "brightness", "color_temp", "hs", "xy", "rgb", "rgbw",
                        "rgbww"]}},
                    "selector": {"number": {"min": 0.0, "max": 100.0,
                                            "unit_of_measurement": "%",
                                            "step": 1.0, "mode": "slider"}}},
                "effect": {
                    "filter": {"supported_features": [4]},
                    "selector": {"state": {"attribute": "effect",
                                           "multiple": False}}},
                "profile": {"example": "relax", "selector": {"text": {}}},
                "additional_fields": {"collapsed": True, "fields": {
                    "rgbw_color": {
                        "filter": {"attribute": {"supported_color_modes": [
                            "hs", "xy", "rgb", "rgbw", "rgbww"]}},
                        "selector": {"object": {"multiple": False}}},
                }},
            }},
        "turn_off": {"target": {"entity": [{"domain": ["light"]}]},
                     "fields": {"transition": {
                         "filter": {"supported_features": [32]},
                         "selector": {"number": {"min": 0.0, "max": 300.0,
                                                 "step": 1.0}}}}},
    }},
    {"domain": "switch", "services": {
        "turn_on": {"target": {"entity": [{"domain": ["switch"]}]}, "fields": {}},
        "turn_off": {"target": {"entity": [{"domain": ["switch"]}]}, "fields": {}},
    }},
    {"domain": "select", "services": {
        "select_option": {
            "target": {"entity": [{"domain": ["select"]}]},
            "fields": {"option": {
                "required": True,
                "selector": {"state": {"hide_states": ["unavailable", "unknown"],
                                       "multiple": False}}}}},
    }},
    {"domain": "sensor", "services": {
        "set_display_precision": {
            "target": {"entity": [{"domain": ["sensor"]}]},
            "fields": {"display_precision": {
                "selector": {"number": {"min": 0, "max": 6, "step": 1}}}}},
    }},
]

_HOME_SPACE = {
    "aree": [{"id": "casa", "nome": "Casa", "piano_id": None}],
    "entita": [
        {"id": "light.alberello", "nome": "Alberello", "area_id": "casa",
         "dispositivo_id": None, "classe": None, "disabilitata": False},
        {"id": "light.cucina_cucina", "nome": "Cucina", "area_id": "casa",
         "dispositivo_id": None, "classe": None, "disabilitata": False},
        {"id": "switch.lavatrice", "nome": "Lavatrice", "area_id": "casa",
         "dispositivo_id": None, "classe": None, "disabilitata": False},
        {"id": "sensor.backup_backup_manager_state", "nome": "Backup",
         "area_id": "casa", "dispositivo_id": None, "classe": None,
         "disabilitata": False},
        {"id": "select.modo_di_funzionamento", "nome": "Modo",
         "area_id": "casa", "dispositivo_id": None, "classe": None,
         "disabilitata": False},
    ],
    "dispositivi": [],
}


class FintoClient:
    async def get_services(self):
        return HA_SERVICES


async def _registro() -> ServiceRegistry:
    """Il registro VERO, costruito dal payload vero di `/api/services`.

    Non una finta: `ServiceRegistry` appiattisce le sezioni e normalizza
    `fields`, ed e' proprio quel passaggio che decide se `rgbw_color` sia un
    parametro o no. Una finta che restituisse i campi gia' piatti salterebbe
    l'unico pezzo di questo giro che sa sbagliare.
    """
    registry = ServiceRegistry()
    await registry.refresh(FintoClient())
    return registry


def _states(*payloads) -> dict[str, dict]:
    """Lo specchio, nella forma vera che la porta consegna alla verifica."""
    return {p["entity_id"]: _to_minimal(p) for p in payloads}


def _attributes(payload: dict) -> dict:
    return disclosable_attributes(_to_minimal(payload).get("attributes"))


def _detail(payload: dict, registry) -> dict:
    """La catena vera fino a cio' che `view` consegna al modello."""
    state, names, unit, classes, since, attributes = live_mirror([_to_minimal(payload)])
    return view(_HOME_SPACE, [], [], state, "entita", payload["entity_id"],
                fallback_names=names, reported_units=unit,
                reported_classes=classes, reported_since_when=since,
                reported_attributes=attributes, registry=registry)


# --------------------------------------------------------------------------
# I QUATTRO CASI DEL CAPITOLATO
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cambia_colore_all_alberello_funziona():
    verdict = verification(
        {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.alberello"]},
         "dati": {"rgb_color": [255, 0, 0]}},
        await _registro(), _states(LIGHT_ALBERELLO))
    assert verdict.ok is True, verdict.reason


@pytest.mark.asyncio
async def test_abbassa_la_luminosita_dell_alberello_funziona():
    verdict = verification(
        {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.alberello"]},
         "dati": {"brightness_pct": 30}},
        await _registro(), _states(LIGHT_ALBERELLO))
    assert verdict.ok is True, verdict.reason


@pytest.mark.asyncio
async def test_cambia_colore_alla_presa_della_lavatrice_lo_rifiutiamo_noi():
    """Rifiutato da NOI, con la ragione detta -- non da Home Assistant con un
    errore tecnico. La ragione qui e' il dominio, ed e' quella vera: la presa
    e' uno `switch`, e nessun `light.turn_on` la riguarda. Il rifiuto NOMINA
    il dominio che ha davvero, cosi' il modello puo' correggersi invece di
    ripetere."""
    verdict = verification(
        {"servizio": "light.turn_on", "bersaglio": {"entita": ["switch.lavatrice"]},
         "dati": {"rgb_color": [255, 0, 0]}},
        await _registro(), _states(LIGHT_ALBERELLO, SWITCH_LAVATRICE))
    assert verdict.ok is False
    assert "switch.lavatrice" in verdict.reason
    assert "switch" in verdict.reason


@pytest.mark.asyncio
async def test_l_alberello_a_8000_kelvin_funziona_anche_se_il_cursore_si_ferma_a_6500():
    """La trappola misurata del §13, e la sola riga della tabella che si puo'
    sbagliare in due modi opposti.

    Il selettore che Home Assistant pubblica per `color_temp_kelvin` dichiara
    2000-6500 K; l'Alberello dichiara 1500-9000. **Vince l'entita'.** Chi
    restringesse sul selettore negherebbe una temperatura che quella
    lampadina sa fare davvero.

    Due asserzioni e non una: che la chiamata passi (nessuno ha restretto sul
    cursore) E che i limiti detti al modello siano quelli della lampadina --
    la prima da sola resterebbe verde anche se al modello raccontassimo
    2000-6500, cioe' facendogli credere di non poter chiedere gli 8000.
    """
    registry = await _registro()
    verdict = verification(
        {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.alberello"]},
         "dati": {"color_temp_kelvin": 8000}},
        registry, _states(LIGHT_ALBERELLO))
    assert verdict.ok is True, verdict.reason

    kelvin = commands_for("light.alberello", registry,
                          _attributes(LIGHT_ALBERELLO))["light.turn_on"]["parametri"][
                              "color_temp_kelvin"]
    assert kelvin["minimo"] == 1500
    assert kelvin["massimo"] == 9000
    assert kelvin["limiti_da"] == "questa entita'"
    # L'unita' resta quella del selettore: e' la sola parte del cursore
    # generico che descrive anche il dispositivo.
    assert kelvin["unita"] == "kelvin"


# --------------------------------------------------------------------------
# IL `filter` DI HOME ASSISTANT DIVENTA UN CONTROLLO VERO
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_il_colore_su_una_luce_che_fa_solo_acceso_e_spento_si_rifiuta_e_si_dice_perche():
    """Il caso che il controllo nuovo esiste per chiudere, e il piu' comune
    di questa casa: quaranta luci su cinquanta sono `onoff`.

    Il rifiuto non e' generico: nomina l'attributo che Home Assistant guarda
    (`supported_color_modes`), i valori che ammette, e cosa quella luce
    dichiara davvero. Senza l'ultima meta' il modello saprebbe cosa serviva e
    non cosa c'e'.
    """
    verdict = verification(
        {"servizio": "light.turn_on",
         "bersaglio": {"entita": ["light.cucina_cucina"]},
         "dati": {"rgb_color": [255, 0, 0]}},
        await _registro(), _states(LIGHT_CUCINA))
    assert verdict.ok is False
    assert "rgb_color" in verdict.reason
    assert "supported_color_modes" in verdict.reason
    assert "onoff" in verdict.reason
    assert "light.cucina_cucina" in verdict.reason


@pytest.mark.asyncio
async def test_una_capacita_che_manca_si_dice_col_suo_nome_non_col_suo_bit():
    """L'altra forma di `filter`, quella per capacita'. La vecchia ragione per
    non verificarla era «richiede di interpretare bitmask dominio per
    dominio»: non serve interpretarla -- Home Assistant consegna il bit gia'
    risolto in numero -- e il NOME lo mette l'anagrafe dei tipi, cosi' il
    rifiuto dice «transizione» invece di «il bit 32»."""
    verdict = verification(
        {"servizio": "light.turn_on",
         "bersaglio": {"entita": ["light.cucina_cucina"]},
         "dati": {"transition": 3}},
        await _registro(), _states(LIGHT_CUCINA))
    assert verdict.ok is False
    assert "transition" in verdict.reason
    assert "transizione" in verdict.reason
    assert "32" not in verdict.reason


@pytest.mark.asyncio
async def test_la_stessa_capacita_sull_alberello_passa():
    """La contropartita: un controllo che dicesse sempre di no sarebbe verde
    sulla prova sopra e inutile. L'Alberello dichiara 36 -- transizione ed
    effetti -- e li usa."""
    registry = await _registro()
    states = _states(LIGHT_ALBERELLO)
    for data in ({"transition": 3}, {"effect": "effect_pulse"},
                 {"rgbw_color": [1, 2, 3, 4]}):
        verdict = verification(
            {"servizio": "light.turn_on",
             "bersaglio": {"entita": ["light.alberello"]}, "dati": data},
            registry, states)
        assert verdict.ok is True, (data, verdict.reason)


@pytest.mark.asyncio
async def test_su_un_bersaglio_misto_basta_che_una_sola_lo_sappia_fare():
    """La regola e' quella di Home Assistant (`.some(...)`), e vale anche per
    il rifiuto: si dice di no solo quando NESSUNA delle entita' bersagliate
    accetta quel parametro. Un bersaglio con l'Alberello e la luce della
    cucina passa -- ed e' dichiarato nel docstring del modulo, non un
    silenzio."""
    registry = await _registro()
    states = _states(LIGHT_ALBERELLO, LIGHT_CUCINA)
    misto = verification(
        {"servizio": "light.turn_on",
         "bersaglio": {"entita": ["light.alberello", "light.cucina_cucina"]},
         "dati": {"rgb_color": [255, 0, 0]}},
        registry, states)
    assert misto.ok is True, misto.reason
    solo_cucina = verification(
        {"servizio": "light.turn_on",
         "bersaglio": {"entita": ["light.cucina_cucina"]},
         "dati": {"rgb_color": [255, 0, 0]}},
        registry, states)
    assert solo_cucina.ok is False


@pytest.mark.asyncio
async def test_su_cio_che_non_si_e_potuto_misurare_non_si_rifiuta():
    """La disciplina che questo modulo dichiara da sempre, applicata al
    controllo nuovo: un'entita' di cui lo specchio non porta nessun attributo
    -- un'integrazione che non li manda, una voce arrivata a meta' -- non fa
    dire «questa luce non fa colore». `field_applies` risponde `None`, e
    `None` non diventa un no."""
    muta = {"entity_id": "light.senza_attributi", "state": "on", "attributes": {}}
    states = _states(muta)
    _HOME_SPACE["entita"].append(
        {"id": "light.senza_attributi", "nome": "Muta", "area_id": "casa",
         "dispositivo_id": None, "classe": None, "disabilitata": False})
    try:
        verdict = verification(
            {"servizio": "light.turn_on",
             "bersaglio": {"entita": ["light.senza_attributi"]},
             "dati": {"rgb_color": [255, 0, 0]}},
            await _registro(), states)
        assert verdict.ok is True, verdict.reason
    finally:
        _HOME_SPACE["entita"].pop()


def test_un_campo_senza_filtro_si_applica_sempre():
    """Il silenzio di Home Assistant significa «vale per tutte»: e' lui a
    dichiarare quando un parametro e' ristretto, e dedurre una restrizione dal
    suo silenzio sarebbe inventarla."""
    assert field_applies({"selector": {"text": {}}}, {"qualunque": 1}) is True
    assert field_applies({"filter": {"buffo": []}}, {"qualunque": 1}) is None


# --------------------------------------------------------------------------
# IL MODELLO SA COSA PUO' CHIEDERE, PRIMA DI PROVARE
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_i_comandi_dell_alberello_dicono_cosa_accetta_e_cosa_no():
    """Il buco del §13.2 chiuso: HIRIS aveva il registro dei servizi e lo
    usava solo per RIFIUTARE.

    E' scritto come un CONFRONTO fra due entita' dello stesso dominio, non
    come un elenco di attese: `rgb_color` c'e' sull'Alberello e non sulla
    luce della cucina, e il servizio e' lo stesso. Un test che si limitasse a
    dire «mi aspetto rgb_color» resterebbe verde il giorno in cui il filtro
    smettesse di filtrare."""
    registry = await _registro()
    alberello = commands_for("light.alberello", registry,
                             _attributes(LIGHT_ALBERELLO))["light.turn_on"]["parametri"]
    cucina = commands_for("light.cucina_cucina", registry,
                          _attributes(LIGHT_CUCINA))["light.turn_on"]["parametri"]

    assert {"rgb_color", "rgbw_color", "color_temp_kelvin", "brightness_pct",
            "effect", "transition"} <= set(alberello)
    assert not ({"rgb_color", "rgbw_color", "color_temp_kelvin",
                 "brightness_pct", "effect", "transition"} & set(cucina))
    # `profile` non ha filtro: vale per entrambe, e la sua presenza dimostra
    # che l'elenco della cucina non e' vuoto per un guasto.
    assert "profile" in alberello and "profile" in cucina


@pytest.mark.asyncio
async def test_i_valori_legali_di_un_parametro_vengono_dall_entita():
    """`effect` ha un selettore che non porta nessun elenco (`state`): i tre
    effetti veri li dichiara l'entita', in `effect_list`. Se questa vista
    leggesse solo il selettore, il modello dovrebbe indovinare il nome di un
    effetto."""
    registry = await _registro()
    effetto = commands_for("light.alberello", registry,
                           _attributes(LIGHT_ALBERELLO))["light.turn_on"][
                               "parametri"]["effect"]
    assert effetto["valori"] == ["effect_colorloop", "effect_pulse", "effect_stop"]
    assert effetto["valori_da"] == "questa entita'"


@pytest.mark.asyncio
async def test_un_servizio_senza_parametri_lo_dice_e_non_tace():
    """`switch.turn_on` non accetta niente, e la vista lo dice con un elenco
    vuoto invece di sparire: «questo servizio non ha parametri» e «questo
    servizio non c'e'» sono due fatti diversi."""
    comandi = commands_for("switch.lavatrice", await _registro(),
                           _attributes(SWITCH_LAVATRICE))
    assert comandi["switch.turn_on"] == {"parametri": {}}
    assert set(comandi) == {"switch.turn_on", "switch.turn_off"}


@pytest.mark.asyncio
async def test_un_servizio_i_cui_parametri_non_si_sono_letti_non_diventa_senza_parametri():
    """Il terzo silenzio, quello che si perde sempre: `registry._fields`
    risponde `None` quando `fields` c'era in una forma che nessuno ha saputo
    leggere. «Non l'ho letto» non e' «non ne ha», e il modello deve poterli
    distinguere -- altrimenti concluderebbe che `light.turn_on` non accetta
    niente."""
    registry = ServiceRegistry()

    class Storto:
        async def get_services(self):
            return [{"domain": "light", "services": {
                "turn_on": {"target": {}, "fields": ["una", "lista"]}}}]

    await registry.refresh(Storto())
    comandi = commands_for("light.alberello", registry, _attributes(LIGHT_ALBERELLO))
    assert comandi["light.turn_on"] == {"parametri_non_letti": True}


@pytest.mark.asyncio
async def test_senza_registro_la_vista_non_promette_niente():
    """`comandi` non compare affatto: una chiave vuota direbbe «non c'e'
    niente da chiedere a questa entita'», che e' un'affermazione sulla casa e
    non su HIRIS. Stessa disciplina di `unita` e `capacita`."""
    assert "comandi" not in _detail(LIGHT_ALBERELLO, None)
    assert "comandi" in _detail(LIGHT_ALBERELLO, await _registro())


@pytest.mark.asyncio
async def test_i_comandi_escono_dalla_vista_di_una_entita_sola():
    """La catena vera, fino a cio' che il modello legge davvero."""
    detail = _detail(LIGHT_ALBERELLO, await _registro())
    parametri = detail["comandi"]["light.turn_on"]["parametri"]
    assert parametri["color_temp_kelvin"]["massimo"] == 9000
    # E la meta' che c'era gia' resta accanto: sapere e fare, nello stesso
    # oggetto.
    assert detail["attributi"]["campo_di_manovra"]["supported_color_modes"] == [
        "color_temp", "hs"]


# --------------------------------------------------------------------------
# «COSA PUO' ASSUMERE» NON E' «COSA LE SI PUO' IMPORRE»
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_le_due_options_non_escono_piu_sotto_la_stessa_etichetta():
    """Lasciato aperto dalla fetta precedente (§15.2). Stesso nome
    (`options`), stessa classificazione di Home Assistant, due domande
    opposte: sul `select` quei valori si impongono con `select.select_option`,
    sul `sensor` descrivono soltanto cosa lo stato potra' valere.

    La prova e' un CONFRONTO fra le due entita' vere, non un'asserzione su
    una sola: mettere entrambe sotto la stessa etichetta -- o entrambe sotto
    etichette diverse ma sbagliate -- fallisce qui."""
    registry = await _registro()
    sensore = _detail(SENSOR_BACKUP, registry)["attributi"]
    scelta = _detail(SELECT_MODO, registry)["attributi"]

    assert sensore["valori_che_puo_assumere"]["options"] == [
        "idle", "create_backup", "blocked", "receive_backup", "restore_backup"]
    assert "campo_di_manovra" not in sensore

    assert scelta["campo_di_manovra"]["options"] == ["auto", "manuale", "vacanza"]
    assert "valori_che_puo_assumere" not in scelta


@pytest.mark.asyncio
async def test_solo_il_select_dice_che_quei_valori_si_possono_imporre():
    """L'altra meta', e quella che conta per chi comanda: `select.select_option`
    riceve i valori dell'entita' come elenco di cio' che si puo' chiedere; il
    sensore non ha nessun servizio che li accetti."""
    registry = await _registro()
    scelta = commands_for("select.modo_di_funzionamento", registry,
                          _attributes(SELECT_MODO))
    assert scelta["select.select_option"]["parametri"]["option"] == {
        "valori": ["auto", "manuale", "vacanza"], "valori_da": "questa entita'"}

    sensore = commands_for("sensor.backup_backup_manager_state", registry,
                           _attributes(SENSOR_BACKUP))
    assert set(sensore) == {"sensor.set_display_precision"}
    assert "options" not in sensore["sensor.set_display_precision"]["parametri"]


def test_ogni_attributo_assumibile_porta_la_sua_ragione_scritta():
    """Un'eccezione senza ragione non passa -- la stessa regola che
    l'anagrafe dei tipi impone gia' agli attributi tolti dalle capacita'."""
    dichiarati = type_vocabulary.declared_assumable_attributes()
    assert dichiarati, "nessun attributo assumibile dichiarato"
    for domain, voci in dichiarati.items():
        for name, ragione in voci.items():
            assert isinstance(ragione, str) and len(ragione) > 40, (domain, name)
            # E dev'essere una capacita' che Home Assistant DICHIARA per quel
            # dominio: un nome inventato qui creerebbe una cesta che non si
            # riempie mai, e nessuno se ne accorgerebbe.
            assert name in type_vocabulary.capability_attribute_tables()[domain], (
                f"«{name}» non e' una capacita' dichiarata da Home Assistant "
                f"per «{domain}»: non c'e' niente da spostare")
        # E i due insiemi sono DISGIUNTI: la separazione sta nell'anagrafe,
        # non nell'ordine con cui `inherited_attributes` guarda le ceste. Se
        # si sovrapponessero, a decidere sarebbe quell'ordine -- cioe' un
        # posto diverso da quello dove la decisione e' scritta.
        assert not (frozenset(voci)
                    & type_vocabulary.capability_attributes(domain)), domain


def test_ogni_limite_preso_dall_entita_nomina_una_capacita_vera():
    """Il collegamento parametro -> attributo e' un giudizio nostro, e per
    questo va sorvegliato: ogni attributo nominato dev'essere una capacita'
    che Home Assistant dichiara per quel dominio (`_CAPABILITY_ATTRIBUTE_
    TABLES`, pinnata al sorgente). Un refuso non diventa un limite che non
    esiste -- diventa rosso.

    Mutazione (eseguita): `min_color_temp` al posto di `min_color_temp_kelvin`
    in `_PARAMETER_LIMITS["light"]` -- questa prova arrossisce nominandolo."""
    tabelle = type_vocabulary.capability_attribute_tables()
    for domain, per_parameter in type_vocabulary.declared_parameter_limits().items():
        assert domain in tabelle, domain
        for parameter, linked in per_parameter.items():
            assert set(linked) in ({"min", "max"}, {"options"}), (domain, parameter)
            for attribute in linked.values():
                assert attribute in tabelle[domain], (
                    f"«{domain}.{parameter}» dice di leggere il limite in "
                    f"«{attribute}», che Home Assistant non dichiara fra le "
                    f"capacita' di «{domain}»")


def test_un_limite_dell_entita_si_prende_solo_intero():
    """Con un estremo dall'entita' e l'altro dal cursore la risposta direbbe
    «da 1500 a 6500»: ne' la lampadina ne' il servizio, una terza cosa vera di
    nessuno. Qui la lampadina dichiara solo il minimo, e la vista ripiega
    INTERAMENTE sul selettore invece di mescolare."""
    meta = {"entity_id": "light.meta", "state": "on", "attributes": {
        "min_color_temp_kelvin": 1500, "supported_color_modes": ["color_temp"],
        "friendly_name": "Meta"}}
    from hiris.app.home_space.queries import _limits_of_entity
    assert _limits_of_entity("light", "color_temp_kelvin",
                             _attributes(meta)) == {}
