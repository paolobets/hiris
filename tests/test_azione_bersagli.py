"""I bersagli: «spegni tutto in cucina» smette di spegnere quasi tutto.

Fetta 1 di `docs/design/2026-08-17-piano-i-sette-che-mancano.md`.

**Il difetto che questo file sorveglia.** Prima, un bersaglio poteva nominare
solo entita': «spegni tutto in cucina» obbligava il modello a chiamare
`cerca`, raccogliere gli id a mano e passarli tutti a `esegui`. Se ne perdeva
uno -- e su una cucina con quindici entita' ne perdeva uno -- HIRIS ne
spegneva quattordici e **dichiarava di aver spento tutto**: una risposta
sbagliata detta con sicurezza. Adesso il bersaglio si passa com'e' (un'area,
un piano, un'etichetta, un dispositivo) e a dire cosa contiene e' **Home
Assistant**, con `extract_from_target`.

Le prove sono in quattro parti, e ognuna guarda un pezzo diverso della stessa
promessa:

1. **la traduzione** (`verifica.translate_target`, pura): i nomi italiani del
   modello diventano i cinque campi di `cv.TARGET_FIELDS`, e cio' che non si
   sa leggere si dichiara invece di sparire;
2. **il verdetto** (`verifica.verification`, pura): cosa si tocca, cosa resta
   fuori e con che parola lo si dice -- senza rete, in millisecondi;
3. **il client** (`ha_client.extract_from_target`): il comando che parte
   davvero, e le due meta' della risposta;
4. **la porta**: la sequenza intera, e i due modi in cui la domanda a Home
   Assistant puo' non arrivare -- che non devono MAI diventare un bersaglio
   piu' corto.

**I nomi dei campi sono verificati alla fonte**, non ricordati: `TARGET_FIELDS`
sta in `homeassistant/helpers/config_validation.py` e usa le costanti
`ATTR_ENTITY_ID`, `ATTR_DEVICE_ID`, `ATTR_AREA_ID`, `ATTR_FLOOR_ID`,
`ATTR_LABEL_ID`, i cui VALORI (`homeassistant/const.py`) sono `entity_id`,
`device_id`, `area_id`, `floor_id`, `label_id`. In questo progetto il nome di
una costante di Home Assistant e il suo valore hanno gia' divorziato una volta
(`CO` vale `carbon_monoxide`), e un test che pinnasse il nome invece del
valore non proverebbe niente.

Come in `tests/test_azione_verifica.py` e `tests/test_azione_porta.py`:
nessuna fixture asincrona -- la suite gira in modalita' `strict` di
pytest-asyncio, quindi ogni test async porta il suo `@pytest.mark.asyncio` e
la preparazione sta in un helper `await`ato.
"""
import pytest

from hiris.app.action import actuator as porta_modulo
from hiris.app.action.actuator import ActionActuator
from hiris.app.action.registry import ServiceRegistry
from hiris.app.action.verification import TARGETS, translate_target, verification
from hiris.app.proxy.ha_client import HAClient

# Come in `test_azione_porta.py`: cio' che si misura qui non e' la DURATA
# dell'attesa ma cosa si tocca, e due secondi per test non li paga nessuno.
SCADENZA_NEI_TEST = 0.01


@pytest.fixture(autouse=True)
def _scadenza_corta(monkeypatch):
    monkeypatch.setattr(porta_modulo, "STATE_WAIT_S", SCADENZA_NEI_TEST)


RISPOSTA_HA = [
    {"domain": "light", "services": {"turn_off": {"fields": {"transition": {}}},
                                     "turn_on": {"fields": {"brightness": {}}}}},
    {"domain": "switch", "services": {"turn_off": {"fields": {}}}},
    {"domain": "homeassistant", "services": {"turn_off": {"fields": {}}}},
]


class FintoRegistroClient:
    async def get_services(self):
        return RISPOSTA_HA


async def _registro_pronto() -> ServiceRegistry:
    r = ServiceRegistry()
    await r.refresh(FintoRegistroClient())
    return r


# La cucina vera del difetto: quindici cose, di cui nove luci. Il numero non
# e' decorativo -- e' la misura di quanto un elenco raccolto a mano puo'
# sbagliare, ed e' la ragione per cui i test qui sotto contano.
LUCI_CUCINA = [f"light.cucina_{n}" for n in range(1, 10)]
ALTRO_IN_CUCINA = ["switch.cucina_presa", "sensor.cucina_temperatura",
                   "binary_sensor.cucina_movimento", "media_player.cucina",
                   "sensor.cucina_umidita", "climate.cucina"]
TUTTA_LA_CUCINA = LUCI_CUCINA + ALTRO_IN_CUCINA

STATI_CUCINA = {eid: {"id": eid, "state": "on", "attributes": {}}
                for eid in TUTTA_LA_CUCINA}


def _risolto(entita, **resto) -> dict:
    """La risposta di `extract_from_target` nella sua forma piena.

    Le sette chiavi ci sono SEMPRE, come le mette il client vero: un test che
    ne omettesse una proverebbe il codice contro una risposta che nessuno
    produce.
    """
    risolto = {"entita": list(entita), "dispositivi": [], "aree": [],
               "dispositivi_mancanti": [], "aree_mancanti": [],
               "piani_mancanti": [], "etichette_mancanti": []}
    risolto.update(resto)
    return risolto


# ── 1. La traduzione ───────────────────────────────────────────────────────

def test_i_cinque_nomi_italiani_diventano_i_cinque_campi_di_home_assistant():
    """I VALORI di `cv.TARGET_FIELDS`, non i nomi delle costanti.

    Se qualcuno traducesse «aree» in `areas` o `area`, Home Assistant
    risponderebbe `invalid_format` e il bersaglio non si risolverebbe piu':
    un guasto che si vedrebbe solo sulla casa vera.
    """
    tradotto, illeggibili = translate_target({
        "entita": ["light.salotto"], "dispositivi": ["abc123"],
        "aree": ["cucina"], "piani": ["primo"], "etichette": ["notturne"]})
    assert illeggibili == []
    assert tradotto == {"entity_id": ["light.salotto"], "device_id": ["abc123"],
                        "area_id": ["cucina"], "floor_id": ["primo"],
                        "label_id": ["notturne"]}


def test_il_client_e_la_verifica_conoscono_gli_stessi_cinque_campi():
    """Nessun doppione: i campi che il client accetta sono esattamente quelli
    in cui la verifica traduce. Due elenchi scritti a mano nei due moduli
    divergerebbero al primo campo nuovo, e il bersaglio tradotto verrebbe
    scartato in silenzio dall'altro lato."""
    assert set(HAClient.TARGET_FIELDS) == set(TARGETS.values())


def test_una_voce_sola_puo_essere_una_stringa_anche_per_un_area():
    tradotto, illeggibili = translate_target({"aree": "cucina"})
    assert tradotto == {"area_id": ["cucina"]}
    assert illeggibili == []


def test_una_voce_illeggibile_si_dichiara_invece_di_sparire():
    """Il difetto della fetta alla riga sbagliata: tradurre la meta' buona e
    buttare l'altra sarebbe un bersaglio ridotto in silenzio."""
    tradotto, illeggibili = translate_target({"aree": ["cucina", 7]})
    assert tradotto == {"area_id": ["cucina"]}
    assert len(illeggibili) == 1 and "aree" in illeggibili[0]


@pytest.mark.asyncio
async def test_un_bersaglio_scritto_meta_bene_si_rifiuta_intero():
    v = verification({"servizio": "light.turn_off",
                  "bersaglio": {"aree": ["cucina", 7]}},
                 await _registro_pronto(), STATI_CUCINA)
    assert v.ok is False
    assert v.da_risolvere is False, (
        "non si va a chiedere a Home Assistant meta' bersaglio: si rifiuta")
    assert "7" in v.reason


# ── 2. Il verdetto ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_un_bersaglio_per_area_non_si_esegue_senza_aver_chiesto_a_ha():
    """Il verdetto e' NEGATIVO, non «in attesa»: un chiamante che ignorasse
    `da_risolvere` non eseguirebbe niente, invece di eseguire su un elenco
    vuoto -- che sul bersaglio piu' pericoloso e' l'unico verso sicuro in cui
    sbagliare."""
    v = verification({"servizio": "light.turn_off", "bersaglio": {"aree": ["cucina"]}},
                 await _registro_pronto(), STATI_CUCINA)
    assert v.ok is False
    assert v.da_risolvere is True
    assert v.target == {"area_id": ["cucina"]}
    assert v.entity == ()


@pytest.mark.asyncio
async def test_spegni_tutto_in_cucina_tocca_TUTTE_le_luci_della_cucina():
    """**Il test del difetto.** Nove luci in cucina, e nove se ne toccano.

    Un elenco raccolto a mano ne perdeva una e HIRIS dichiarava di aver spento
    tutto. Qui l'elenco lo detta Home Assistant, e il verdetto lo riporta
    intero.
    """
    v = verification({"servizio": "light.turn_off", "bersaglio": {"aree": ["cucina"]}},
                 await _registro_pronto(), STATI_CUCINA,
                 resolved=_risolto(TUTTA_LA_CUCINA, aree=["cucina"]))
    assert v.ok is True, v.reason
    assert sorted(v.entity) == sorted(LUCI_CUCINA)
    assert len(v.entity) == 9


@pytest.mark.asyncio
async def test_cio_che_non_e_del_dominio_del_servizio_si_dichiara():
    """Non si rifiuta -- una cucina contiene sensori e prese, e pretendere che
    siano tutte luci farebbe rifiutare «spegni le luci in cucina» in ogni casa
    vera -- ma nemmeno si tace: l'esito deve poter dire «ho toccato 9 delle 15
    cose che ci sono li' dentro»."""
    v = verification({"servizio": "light.turn_off", "bersaglio": {"aree": ["cucina"]}},
                 await _registro_pronto(), STATI_CUCINA,
                 resolved=_risolto(TUTTA_LA_CUCINA))
    assert sorted(v.scartate) == sorted(ALTRO_IN_CUCINA)


@pytest.mark.asyncio
async def test_un_area_che_non_esiste_e_un_area_vuota_sono_due_frasi_diverse():
    """La distinzione che l'anagrafe fa gia' ovunque, e che qui arriva gratis
    dalla seconda meta' della risposta di Home Assistant. Un solo messaggio
    per i due casi manderebbe il modello a cercare un guasto dove c'e' solo
    un'area vuota, o a dire «e' vuota» di un'area che non esiste."""
    registro = await _registro_pronto()
    non_c_e = verification({"servizio": "light.turn_off",
                        "bersaglio": {"aree": ["tinello"]}},
                       registro, STATI_CUCINA,
                       resolved=_risolto([], aree_mancanti=["tinello"]))
    vuota = verification({"servizio": "light.turn_off",
                      "bersaglio": {"aree": ["ripostiglio"]}},
                     registro, STATI_CUCINA, resolved=_risolto([]))
    assert non_c_e.ok is False and vuota.ok is False
    assert "tinello" in non_c_e.reason
    assert "non esiste" in non_c_e.reason or "non esistono" in non_c_e.reason
    assert non_c_e.reason != vuota.reason
    assert "non contiene nessuna entita'" in vuota.reason


@pytest.mark.asyncio
async def test_un_bersaglio_che_nomina_qualcosa_di_inesistente_non_si_riduce():
    """Due aree, una vera e una che non c'e'. Eseguire sulla meta' buona e
    metterlo in una nota sarebbe il difetto di partenza con un alibi: si
    rifiuta, e il rifiuto dice quale delle due non esiste."""
    v = verification({"servizio": "light.turn_off",
                  "bersaglio": {"aree": ["cucina", "tinello"]}},
                 await _registro_pronto(), STATI_CUCINA,
                 resolved=_risolto(TUTTA_LA_CUCINA, aree=["cucina"],
                                  aree_mancanti=["tinello"]))
    assert v.ok is False
    assert "tinello" in v.reason
    assert v.entity == ()


@pytest.mark.asyncio
async def test_i_quattro_registri_mancanti_si_dichiarano_tutti():
    """Piani, aree, dispositivi ed etichette: quattro meta' della stessa
    risposta, e nessuna delle quattro puo' essere l'unica che si guarda."""
    registro = await _registro_pronto()
    for chiave, nominato in (("piani_mancanti", "attico"),
                             ("aree_mancanti", "tinello"),
                             ("dispositivi_mancanti", "aabbcc"),
                             ("etichette_mancanti", "notturne")):
        v = verification({"servizio": "light.turn_off",
                      "bersaglio": {"aree": ["cucina"]}},
                     registro, STATI_CUCINA,
                     resolved=_risolto(LUCI_CUCINA, **{chiave: [nominato]}))
        assert v.ok is False, f"{chiave} non e' stato guardato"
        assert nominato in v.reason


@pytest.mark.asyncio
async def test_un_area_senza_niente_del_dominio_del_servizio_lo_dice():
    """Diverso da «l'area e' vuota» e diverso da «l'area non c'e'»: la cucina
    esiste, ha sei cose dentro, e nessuna e' una luce."""
    v = verification({"servizio": "light.turn_off", "bersaglio": {"aree": ["cucina"]}},
                 await _registro_pronto(), STATI_CUCINA,
                 resolved=_risolto(ALTRO_IN_CUCINA))
    assert v.ok is False
    assert "6" in v.reason and "light" in v.reason


@pytest.mark.asyncio
async def test_un_entita_senza_stato_si_esclude_e_si_dichiara():
    """Un'entita' disabilitata sta nel registro e non nello specchio: Home
    Assistant non la tocca comunque (non e' fra i candidati del servizio).
    Tenerla nell'elenco non l'accenderebbe, e in cambio farebbe dire all'esito
    «non so cosa sia cambiato» dell'INTERA chiamata, perche' di lei nessuno
    annuncera' mai niente."""
    v = verification({"servizio": "light.turn_off", "bersaglio": {"aree": ["cucina"]}},
                 await _registro_pronto(), STATI_CUCINA,
                 resolved=_risolto(LUCI_CUCINA + ["light.cucina_disabilitata"]))
    assert v.ok is True, v.reason
    assert "light.cucina_disabilitata" not in v.entity
    assert v.sconosciute == ("light.cucina_disabilitata",)
    assert sorted(v.entity) == sorted(LUCI_CUCINA)


@pytest.mark.asyncio
async def test_solo_entita_senza_stato_non_diventa_un_successo_su_niente():
    """Il complemento del test sopra: se DOPO le esclusioni non resta niente,
    non si chiama un servizio su un elenco vuoto raccontandolo come fatto."""
    v = verification({"servizio": "light.turn_off", "bersaglio": {"aree": ["soffitta"]}},
                 await _registro_pronto(), STATI_CUCINA,
                 resolved=_risolto(["light.soffitta_disabilitata"]))
    assert v.ok is False
    assert v.entity == ()


@pytest.mark.asyncio
async def test_un_entita_nominata_male_resta_rifiutata_anche_dentro_un_area():
    """Le entita' che il MODELLO nomina restano strette: un id inventato e'
    una sua affermazione sbagliata, e il rifiuto che dice quale glielo fa
    correggere. Allargare la regola delle entita' risolte anche a queste
    avrebbe spento un controllo che funzionava."""
    v = verification({"servizio": "light.turn_off",
                  "bersaglio": {"aree": ["cucina"], "entita": ["light.fantasma"]}},
                 await _registro_pronto(), STATI_CUCINA)
    assert v.ok is False
    assert v.da_risolvere is False, (
        "non si va a chiedere a Home Assistant un bersaglio gia' sbagliato")
    assert "light.fantasma" in v.reason


@pytest.mark.asyncio
async def test_homeassistant_su_un_area_tocca_tutti_i_domini():
    """«Spegni tutto in cucina», alla lettera: `homeassistant.turn_off` vale
    per ogni dominio, quindi il filtro sul dominio non deve toccarlo."""
    v = verification({"servizio": "homeassistant.turn_off",
                  "bersaglio": {"aree": ["cucina"]}},
                 await _registro_pronto(), STATI_CUCINA,
                 resolved=_risolto(TUTTA_LA_CUCINA))
    assert v.ok is True, v.reason
    assert sorted(v.entity) == sorted(TUTTA_LA_CUCINA)
    assert v.scartate == ()


@pytest.mark.asyncio
async def test_un_bersaglio_di_sole_entita_non_chiede_niente_a_nessuno():
    """La strada di prima non cambia e non costa un giro di rete: `risolto`
    resta `None` e il verdetto e' comunque positivo."""
    v = verification({"servizio": "light.turn_off",
                  "bersaglio": {"entita": ["light.cucina_1"]}},
                 await _registro_pronto(), STATI_CUCINA)
    assert v.ok is True and v.da_risolvere is False
    assert v.entity == ("light.cucina_1",)


# ── 3. Il client: il comando che parte davvero ─────────────────────────────

class FintoWs:
    """Il websocket di Home Assistant visto da `extract_from_target`.

    Registra il messaggio INTERO che gli si manda: e' l'unico modo di provare
    che i due parametri partono davvero, e non che il codice li nomina in un
    commento.
    """

    def __init__(self, risposta):
        self.mandati = []
        self._risposta = risposta

    async def __call__(self, msg_type, extra=None, timeout=10.0):
        self.mandati.append((msg_type, extra))
        return self._risposta


def _client(risposta) -> tuple[HAClient, FintoWs]:
    client = HAClient("http://ha.local:8123", "token")
    ws = FintoWs(risposta)
    client._ws_command = ws
    return client, ws


def _successo(**risultato) -> dict:
    pieno = {"referenced_entities": [], "referenced_devices": [],
             "referenced_areas": [], "missing_devices": [], "missing_areas": [],
             "missing_floors": [], "missing_labels": []}
    pieno.update(risultato)
    return {"id": 1, "type": "result", "success": True, "result": pieno}


@pytest.mark.asyncio
async def test_il_comando_e_quello_di_home_assistant_coi_suoi_due_parametri():
    """`expand_group` e `primary_entities_only` non sono valori di comodo.

    Una chiamata di servizio vera estrae le entita' con
    `async_extract_referenced_entity_ids(hass, target_selection, True)` e
    `primary_entities_only` al suo default `True`
    (homeassistant/helpers/service.py). Il comando WS ha invece `expand_group`
    predefinito a **False**: lasciarglielo produrrebbe un'anteprima che NON
    coincide con cio' che si tocca -- un gruppo nel bersaglio comparirebbe
    come una cosa sola e se ne toccherebbero dieci. E' il difetto di questa
    fetta in una forma nuova, ed e' per questo che il test guarda il messaggio
    che parte.
    """
    client, ws = _client(_successo())
    await client.extract_from_target({"area_id": ["cucina"]})
    tipo, extra = ws.mandati[0]
    assert tipo == "extract_from_target"
    assert extra["target"] == {"area_id": ["cucina"]}
    assert extra["expand_group"] is True
    assert extra["primary_entities_only"] is True


@pytest.mark.asyncio
async def test_le_due_meta_arrivano_tradotte_e_in_ordine():
    """Dall'altra parte quei campi sono `set` di Python e arrivano in ordine
    arbitrario: senza ordinarli la stessa domanda fatta due volte darebbe due
    anteprime diverse senza che in casa sia cambiato niente."""
    client, _ = _client(_successo(
        referenced_entities=["light.cucina_2", "light.cucina_1"],
        referenced_areas=["cucina"],
        missing_areas=["tinello"], missing_floors=["attico"],
        missing_labels=["notturne"]))
    risolto = await client.extract_from_target({"area_id": ["cucina", "tinello"]})
    assert risolto["entita"] == ["light.cucina_1", "light.cucina_2"]
    assert risolto["aree"] == ["cucina"]
    assert risolto["aree_mancanti"] == ["tinello"]
    assert risolto["piani_mancanti"] == ["attico"]
    assert risolto["etichette_mancanti"] == ["notturne"]
    assert "errore" not in risolto


@pytest.mark.asyncio
async def test_un_dispositivo_che_non_esiste_non_finisce_fra_quelli_toccati():
    """Home Assistant lo mette in ENTRAMBI gli insiemi
    (`_resolve_referenced_devices` in homeassistant/helpers/target.py):
    lasciarlo fra i toccati direbbe «questo dispositivo si tocca» di un
    dispositivo che non c'e'. Togliendolo non si nasconde niente, perche'
    resta intero fra i mancanti."""
    client, _ = _client(_successo(referenced_devices=["vero", "fantasma"],
                                  missing_devices=["fantasma"]))
    risolto = await client.extract_from_target({"device_id": ["vero", "fantasma"]})
    assert risolto["dispositivi"] == ["vero"]
    assert risolto["dispositivi_mancanti"] == ["fantasma"]


@pytest.mark.asyncio
async def test_un_rifiuto_di_home_assistant_e_un_errore_non_un_bersaglio_vuoto():
    """Un `unknown_command` su una versione vecchia di Home Assistant si legge
    qui. Se diventasse `{"entita": []}` la porta direbbe «l'area e' vuota» di
    un'area piena: una frase falsa detta con sicurezza."""
    client, _ = _client({"id": 1, "success": False,
                         "error": {"code": "unknown_command",
                                   "message": "non conosco questo comando"}})
    risolto = await client.extract_from_target({"area_id": ["cucina"]})
    assert "errore" in risolto
    assert "unknown_command" in risolto["errore"]
    assert "entita" not in risolto


@pytest.mark.asyncio
async def test_nessuna_risposta_e_un_errore_non_un_bersaglio_vuoto():
    client, _ = _client(None)
    risolto = await client.extract_from_target({"area_id": ["cucina"]})
    assert "errore" in risolto and "entita" not in risolto


# ── 4. La porta: la sequenza intera ────────────────────────────────────────

class FintoClientPorta:
    """Home Assistant visto dalla porta, con in piu' la bocca nuova.

    `sequenza` registra l'ORDINE in cui le due domande partono: l'anteprima
    deve essere calcolata PRIMA della chiamata, o non e' un'anteprima.
    """

    def __init__(self, risolve=None, solleva=False):
        self.sequenza = []
        self.chiamate = []
        self.ascoltatori = []
        self._risolve = risolve
        self._solleva = solleva

    async def get_services(self):
        return RISPOSTA_HA

    async def extract_from_target(self, target):
        self.sequenza.append(("risolvi", target))
        if self._solleva:
            raise RuntimeError("websocket caduto")
        return self._risolve

    def add_state_listener(self, callback):
        self.ascoltatori.append(callback)

    def remove_state_listener(self, callback):
        if callback in self.ascoltatori:
            self.ascoltatori.remove(callback)

    async def call_service(self, domain, service, data):
        self.sequenza.append(("chiama", f"{domain}.{service}"))
        self.chiamate.append((domain, service, data))
        return []


class FintoClientSenzaBocca(FintoClientPorta):
    """Il client che non sa risolvere i bersagli -- chi cablasse questa porta
    su un altro client di Home Assistant. `None` e non un metodo: e'
    esattamente cio' che `getattr` trova e cio' che `callable` rifiuta."""
    extract_from_target = None


class FintaCache:
    """Lo specchio: una lista di voci minimali con chiave `id`, come
    `EntityCache.all_states()`. Fermo -- si muove solo se qualcuno annuncia,
    e qui nessuno annuncia."""

    def __init__(self, stati):
        self._stati = stati
        self.loaded = True

    def all_states(self):
        return [dict(voce) for voce in self._stati.values()]


async def _porta(client) -> ActionActuator:
    registro = ServiceRegistry()
    await registro.refresh(FintoRegistroClient())
    return ActionActuator(client, registro, FintaCache(STATI_CUCINA))


@pytest.mark.asyncio
async def test_la_porta_spegne_tutte_e_nove_le_luci_della_cucina():
    """La sequenza intera, dal bersaglio del modello alla chiamata: nove luci
    in cucina, nove entity_id nella chiamata a Home Assistant."""
    client = FintoClientPorta(risolve=_risolto(TUTTA_LA_CUCINA, aree=["cucina"]))
    porta = await _porta(client)
    esito = await porta.execute({"servizio": "light.turn_off",
                                "bersaglio": {"aree": ["cucina"]}}, actor="prova")
    assert esito["eseguito"] is True, esito.get("errore")
    _dominio, _servizio, dati = client.chiamate[0]
    assert sorted(dati["entity_id"]) == sorted(LUCI_CUCINA)
    assert len(dati["entity_id"]) == 9


@pytest.mark.asyncio
async def test_l_anteprima_si_calcola_prima_di_toccare_qualcosa():
    """«Prima» e' letterale: la domanda a Home Assistant su cosa contiene il
    bersaglio parte PRIMA della chiamata di servizio, non dopo per raccontarla
    meglio."""
    client = FintoClientPorta(risolve=_risolto(TUTTA_LA_CUCINA, aree=["cucina"]))
    porta = await _porta(client)
    await porta.execute({"servizio": "light.turn_off",
                        "bersaglio": {"aree": ["cucina"]}}, actor="prova")
    assert [passo for passo, _ in client.sequenza] == ["risolvi", "chiama"]


@pytest.mark.asyncio
async def test_l_esito_dice_cosa_conteneva_il_bersaglio_e_cosa_e_rimasto_fuori():
    """Senza queste voci un elenco piu' corto passerebbe per l'elenco intero,
    ed e' esattamente il difetto: `toccate` piu' corto di `risolte` e' un
    fatto che l'utente deve sentirsi dire."""
    client = FintoClientPorta(risolve=_risolto(TUTTA_LA_CUCINA, aree=["cucina"]))
    porta = await _porta(client)
    esito = await porta.execute({"servizio": "light.turn_off",
                                "bersaglio": {"aree": ["cucina"]}}, actor="prova")
    bersaglio = esito["bersaglio"]
    assert bersaglio["chiesto"] == {"area_id": ["cucina"]}
    assert sorted(bersaglio["risolte"]) == sorted(TUTTA_LA_CUCINA)
    assert sorted(bersaglio["toccate"]) == sorted(LUCI_CUCINA)
    assert sorted(bersaglio["escluse_altro_dominio"]) == sorted(ALTRO_IN_CUCINA)
    assert bersaglio["escluse_senza_stato"] == []
    assert bersaglio["aree"] == ["cucina"]


@pytest.mark.asyncio
async def test_un_bersaglio_di_sole_entita_non_costa_un_giro_di_rete():
    """E l'esito non porta l'anteprima: non ci sarebbe niente da raccontare
    che `entita` non dica gia', e una chiave in piu' con dentro la copia di
    un'altra e' un doppione."""
    client = FintoClientPorta(risolve=_risolto([]))
    porta = await _porta(client)
    esito = await porta.execute({"servizio": "light.turn_off",
                                "bersaglio": {"entita": ["light.cucina_1"]}},
                               actor="prova")
    assert esito["eseguito"] is True
    assert [passo for passo, _ in client.sequenza] == ["chiama"]
    assert "bersaglio" not in esito


@pytest.mark.asyncio
async def test_un_client_che_non_sa_risolvere_non_esegue_e_lo_dichiara():
    """Il silenzio si dichiara. L'alternativa -- proseguire con le sole
    entita' nominate, che qui sono zero -- sarebbe una chiamata su niente
    raccontata come riuscita."""
    client = FintoClientSenzaBocca()
    # La finta deve DAVVERO non avere la bocca, o questo test non prova
    # niente. Provato per mutazione durante la fetta «la rinomina» (lotto
    # 19c): rinominato `HAClient.extract_from_target` in
    # `extract_from_target`, questo attributo e' rimasto indietro e la
    # finta ha ricominciato a EREDITARE il metodo vero da
    # `FintoClientPorta` -- e il test e' rimasto verde lo stesso, cioe'
    # non misurava piu' cio' che il suo docstring promette.
    assert not callable(getattr(client, "extract_from_target", None)), (
        "la finta ha di nuovo una bocca: questo test non sta piu' "
        "provando il ramo del client che non sa risolvere")
    porta = await _porta(client)
    esito = await porta.execute({"servizio": "light.turn_off",
                                "bersaglio": {"aree": ["cucina"]}}, actor="prova")
    assert esito["eseguito"] is False
    assert client.chiamate == [], "non si tocca niente se non si e' potuto risolvere"
    assert "bersaglio.entita" in esito["errore"], (
        "il rifiuto deve dire cosa fare invece, non solo che non si puo'")


@pytest.mark.asyncio
async def test_un_bersaglio_non_risolto_non_diventa_un_bersaglio_vuoto():
    """Home Assistant risponde, ma con un errore: e' la terza guardia di
    questo modulo, la stessa forma delle due che gia' c'erano (registro muto,
    specchio cieco)."""
    client = FintoClientPorta(risolve={"errore": "Home Assistant non ha risposto"})
    porta = await _porta(client)
    esito = await porta.execute({"servizio": "light.turn_off",
                                "bersaglio": {"aree": ["cucina"]}}, actor="prova")
    assert esito["eseguito"] is False
    assert client.chiamate == []
    assert "non ha risposto" in esito["errore"]


@pytest.mark.asyncio
async def test_una_risoluzione_che_esplode_diventa_un_rifiuto_leggibile():
    """La porta non solleva mai: il suo chiamante e' uno strumento che parla a
    un modello."""
    client = FintoClientPorta(solleva=True)
    porta = await _porta(client)
    esito = await porta.execute({"servizio": "light.turn_off",
                                "bersaglio": {"aree": ["cucina"]}}, actor="prova")
    assert esito["eseguito"] is False
    assert client.chiamate == []
    assert "RuntimeError" in esito["errore"]


@pytest.mark.asyncio
async def test_un_area_che_non_esiste_non_tocca_niente():
    """La meta' `missing_*` della risposta arriva fino al rifiuto, e nessuna
    chiamata parte."""
    client = FintoClientPorta(risolve=_risolto([], aree_mancanti=["tinello"]))
    porta = await _porta(client)
    esito = await porta.execute({"servizio": "light.turn_off",
                                "bersaglio": {"aree": ["tinello"]}}, actor="prova")
    assert esito["eseguito"] is False
    assert client.chiamate == []
    assert "tinello" in esito["errore"]
