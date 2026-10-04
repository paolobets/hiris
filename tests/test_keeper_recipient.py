"""`recipients_for` -- il recapito del soggetto (spec §2.3, Task 1).

Home Assistant e' la casa finta (`scripts/casa_finta.py`): il client VERO
col trasporto sostituito, che serve `GET /api/states`, i registri e `GET
/api/services` da ingressi sintetici costruiti qui. La forma delle tre letture
che la funzione usa (`get_states`, `read_registry`, `get_services`) e' quindi
quella del client per costruzione, guasti compresi: la busta, mai
un'eccezione (D3). I servizi arrivano dal registro dei servizi
(`ServiceRegistry`, A-04): ogni prova ne passa uno nuovo, che alla prima
domanda legge `/api/services` dalla casa finta. I casi che contano -- un orologio `mobile_app` senza
servizio notify proprio, un tracker che non e' `mobile_app` -- vengono dalla
misura sulla casa vera del 25/09/2026 (vedi `hiris/app/keeper/recipient.py`),
con nomi sintetici."""
import logging
import sys
from pathlib import Path

import aiohttp
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import CasaFinta

from hiris.app.action.registry import ServiceRegistry
from hiris.app.keeper.recipient import (
    _REASON_HA_DOWN,
    Recipients,
    _slugify,
    recipients_for,
)
from hiris.app.proxy.ha_client import HAClient
from tests._casa_sintetica import synthetic_inputs

USER_ID = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"

#: I comandi dei registri, chiesti alla tabella del client: tacerli tutti e'
#: Home Assistant che non risponde alla lettura dei registri.
REGISTRY_COMMANDS = tuple(msg_type for _key, msg_type, _extra in HAClient._REGISTRIES)


def _registry_commands(registry):
    """I comandi che `HAClient.read_registry(registry)` manda, chiesti alla
    stessa tabella del client (Tappa 2, Task 5: un registro, un comando)."""
    return tuple(msg_type for key, msg_type, _extra in HAClient._REGISTRIES
                 if key == registry)

#: I servizi notify della casa sintetica: tre dispositivi `mobile_app` con il
#: proprio servizio, e uno (`portatile_uno`) senza tracker fra quelli provati.
NOTIFY_SERVICES = [{"domain": "notify", "services": {
    "mobile_app_telefono_uno": {}, "mobile_app_tablet_uno": {},
    "mobile_app_telefono_due": {}, "mobile_app_portatile_uno": {}}}]


def _person_state(user_id, trackers):
    return {"entity_id": "person.persona_uno", "state": "home",
            "attributes": {"user_id": user_id, "device_trackers": trackers}}


def _house(*, states=(), entities=(), devices=(), services=None, **faults):
    """La casa finta sugli ingressi sintetici, con gli stati, le entita', i
    dispositivi e i servizi della prova al posto dei loro. `faults` sono i
    `refuse=`/`silence=`/`answers=` di `CasaFinta`."""
    inputs = synthetic_inputs()
    inputs["states"] = list(states)
    inputs["registries"]["entita"] = list(entities)
    inputs["registries"]["dispositivi"] = list(devices)
    inputs["services"] = NOTIFY_SERVICES if services is None else services
    return CasaFinta(inputs, **faults)


_THREE_TRACKERS = [
    {"entity_id": "device_tracker.telefono_uno", "platform": "mobile_app",
     "device_id": "d1"},
    {"entity_id": "device_tracker.tablet_uno", "platform": "mobile_app",
     "device_id": "d2"},
    {"entity_id": "device_tracker.telefono_uno_orologio", "platform": "mobile_app",
     "device_id": "d3"},
]


@pytest.mark.asyncio
async def test_persona_collegata_due_servizi_l_orologio_cade_da_se():
    """Tre tracker `mobile_app`, uno (l'orologio) senza servizio notify
    proprio -- com'era misurato sulla casa vera il 25/09/2026. Il risultato
    porta i DUE servizi che esistono davvero, e nessun motivo (non e' un
    fallimento)."""
    ha = _house(
        states=[_person_state(USER_ID, [
            "device_tracker.telefono_uno", "device_tracker.tablet_uno",
            "device_tracker.telefono_uno_orologio"])],
        entities=_THREE_TRACKERS)
    subject = {"specie": "persona", "id": USER_ID}

    esito = await recipients_for(subject, ha, ServiceRegistry())

    assert esito == Recipients(
        services=("notify.mobile_app_telefono_uno", "notify.mobile_app_tablet_uno"),
        reason=None)


@pytest.mark.asyncio
async def test_tracker_non_mobile_app_ignorato():
    """Un tracker che NON e' `mobile_app` (un'altra integrazione di
    geolocalizzazione) non genera nessun candidato: non si prova nemmeno a
    indovinargli un servizio notify."""
    ha = _house(
        states=[_person_state(USER_ID, [
            "device_tracker.telefono_uno", "device_tracker.gps_logger_esterno"])],
        entities=_THREE_TRACKERS + [
            {"entity_id": "device_tracker.gps_logger_esterno",
             "platform": "gpslogger", "device_id": "d9"}])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients(services=("notify.mobile_app_telefono_uno",), reason=None)


@pytest.mark.asyncio
async def test_entity_id_con_suffisso_non_slug_non_diventa_un_candidato():
    """Guardia difensiva (vincolo di sicurezza 1.1): un `entity_id` che non
    rispettasse la forma slug (mai vera su una casa reale, ma il registro
    potrebbe mentire) non deve MAI diventare un servizio da chiamare, anche
    se per assurdo un servizio con quel nome esistesse davvero."""
    ha = _house(
        states=[_person_state(USER_ID, ["device_tracker.Telefono Strano!"])],
        entities=[{"entity_id": "device_tracker.Telefono Strano!",
                   "platform": "mobile_app", "device_id": "d1"}],
        services=[{"domain": "notify",
                   "services": {"mobile_app_Telefono Strano!": {}}}])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_persona_senza_user_id_collegato_zero_con_motivo_di_collegamento():
    """Una `person` con `user_id` vuoto (un caso misurato sulla casa vera):
    nessuno stato corrisponde all'id del soggetto, e il motivo dice di
    collegare la persona all'utente in Home Assistant."""
    ha = _house(states=[_person_state(None, ["device_tracker.telefono_due"])])

    esito = await recipients_for({"specie": "persona", "id": "id-della-persona-due"},
                                 ha, ServiceRegistry())

    assert esito.services == ()
    assert esito.reason is not None
    assert "collega" in esito.reason and "Persone" in esito.reason


@pytest.mark.asyncio
async def test_due_persone_collegate_allo_stesso_utente_zero_con_motivo_ambiguo():
    """Una casa mal configurata dove due `person` portano lo stesso
    `user_id`: la prima trovata sarebbe una scelta indovinata, non dedotta
    (security review 26/09/2026, vincolo 1.5) -- zero servizi, un motivo
    distinto da quello di «non collegata»."""
    stato_2 = {"entity_id": "person.persona_uno_bis", "state": "home",
               "attributes": {"user_id": USER_ID,
                              "device_trackers": ["device_tracker.tablet_uno"]}}
    ha = _house(states=[
        _person_state(USER_ID, ["device_tracker.telefono_uno"]), stato_2])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito.services == ()
    assert esito.reason is not None
    assert esito.reason != ""
    # Il motivo di ambiguita' NON e' quello di «non collegata»: sono due
    # fatti diversi e chi legge deve poterli distinguere.
    assert "più di una persona" in esito.reason


@pytest.mark.asyncio
async def test_soggetto_persona_senza_id_stesso_motivo_di_collegamento():
    """Una persona anonima (l'ingress non ha portato `X-Remote-User-Id`): non
    c'e' nessun id da cercare, il motivo e' lo stesso della mancata
    collega."""
    ha = _house()

    esito = await recipients_for({"specie": "persona", "id": None}, ha, ServiceRegistry())

    assert esito.services == ()
    assert "collega" in esito.reason
    assert ha.calls == []  # nessuna lettura: non c'e' niente da cercare


@pytest.mark.asyncio
async def test_soggetto_luogo_zero_con_motivo_del_servizio():
    """Retro Panel (`specie == "luogo"`): nessuna strada oggi, e il motivo e'
    esattamente quello della spec §2.3."""
    ha = _house()

    esito = await recipients_for({"specie": "luogo", "id": "retro-panel"}, ha, ServiceRegistry())

    assert esito == Recipients((), "il servizio non ha ancora dichiarato come si avvisa.")
    assert ha.calls == []


@pytest.mark.asyncio
async def test_soggetto_integrazione_zero_con_motivo_del_servizio():
    """Un'integrazione firmata: stessa frase di `luogo`, stessa non-strada."""
    ha = _house()

    esito = await recipients_for({"specie": "integrazione", "id": "mcp-gateway"},
                                 ha, ServiceRegistry())

    assert esito.reason == "il servizio non ha ancora dichiarato come si avvisa."
    assert esito.services == ()


@pytest.mark.asyncio
async def test_soggetto_nessuno_zero_con_motivo():
    """Il ponte (`specie == "nessuno"`, es. lo schedulatore): non e' una
    persona, zero servizi, un motivo leggibile."""
    ha = _house()

    esito = await recipients_for({"specie": "nessuno", "id": None}, ha, ServiceRegistry())

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_soggetto_none_zero_con_motivo():
    """Nessun soggetto affatto (mai dovrebbe capitare in produzione, ma la
    funzione non deve sollevare)."""
    esito = await recipients_for(None, _house(), ServiceRegistry())

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_persona_senza_device_trackers_zero_con_motivo_app():
    """La persona e' collegata ma non ha nessun `device_tracker`: zero
    servizi, il motivo parla di app collegata (non di notifiche attive --
    qui non c'e' nessuna app da attivare, fix round 1, 26/09/2026, vincolo
    4: i due motivi ora si distinguono)."""
    ha = _house(states=[_person_state(USER_ID, [])])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito.services == ()
    assert "collegato con l'app" in esito.reason


@pytest.mark.asyncio
async def test_persona_solo_orologio_notifiche_non_attive():
    """La persona ha un dispositivo `mobile_app` (l'orologio), ma nessuno dei
    suoi tracker risolve a un servizio notify esistente: qui l'app C'E',
    manca l'attivazione -- motivo diverso da «nessun dispositivo» (fix round
    1, 26/09/2026, vincolo 4)."""
    ha = _house(
        states=[_person_state(USER_ID, ["device_tracker.telefono_uno_orologio"])],
        entities=[_THREE_TRACKERS[2]])  # solo l'orologio

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito.services == ()
    assert "notifiche attive" in esito.reason
    assert "collegato con l'app" not in esito.reason


@pytest.mark.asyncio
async def test_dispositivo_rinominato_risolve_dal_nome_del_registro_dispositivi():
    """Il dispositivo e' stato rinominato nell'app Companion DOPO la prima
    registrazione: l'entity_id resta congelato al nome vecchio
    (`device_tracker.telefono_uno`, mai piu' cambiato da Home Assistant --
    `mobile_app/config_flow.py::async_step_registration`), ma Home Assistant
    registra il servizio SUL NOME NUOVO
    (`mobile_app/webhook.py::webhook_update_registration` riscrive
    `device_registry.name` e ricarica notify -- vedi il docstring del
    modulo). Il candidato giusto viene dal registro dei DISPOSITIVI, non
    dalla coda dell'entity_id (fix round 1, 26/09/2026, vincolo 1)."""
    ha = _house(
        states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
        entities=[{"entity_id": "device_tracker.telefono_uno", "platform": "mobile_app",
                   "device_id": "d1"}],
        devices=[{"id": "d1", "name": "Il Telefono Nuovo di Casa"}],
        services=[{"domain": "notify", "services": {
            "mobile_app_il_telefono_nuovo_di_casa": {}}}])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients(
        services=("notify.mobile_app_il_telefono_nuovo_di_casa",), reason=None)


@pytest.mark.asyncio
async def test_dispositivo_mai_rinominato_degrada_sull_entity_id():
    """Il registro dei dispositivi non porta il device (o non e' arrivato):
    si degrada sul secondo candidato, l'entity_id -- che regge finche' il
    dispositivo non e' mai stato rinominato (il caso comune, misurato sulla
    casa vera)."""
    ha = _house(
        states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
        entities=[{"entity_id": "device_tracker.telefono_uno", "platform": "mobile_app",
                   "device_id": "d1"}],
        devices=[])  # nessun dispositivo "d1" nel registro

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients(services=("notify.mobile_app_telefono_uno",), reason=None)


@pytest.mark.asyncio
async def test_nome_dispositivo_preferito_al_entity_id_quando_entrambi_esistono():
    """Se per assurdo ENTRAMBI i candidati risultassero fra i servizi notify
    (un registro incoerente: il vecchio servizio non e' ancora sparito dopo
    una rinomina), si sceglie UNO solo -- quello dal nome del dispositivo,
    che e' la fonte di oggi -- mai due push per lo stesso telefono."""
    ha = _house(
        states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
        entities=[{"entity_id": "device_tracker.telefono_uno", "platform": "mobile_app",
                   "device_id": "d1"}],
        devices=[{"id": "d1", "name": "Nome Nuovo"}],
        services=[{"domain": "notify", "services": {
            "mobile_app_nome_nuovo": {}, "mobile_app_telefono_uno": {}}}])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients(services=("notify.mobile_app_nome_nuovo",), reason=None)


@pytest.mark.parametrize("nome,atteso", [
    ("iPhone Bet", "iphone_bet"),
    ("iPad mini", "ipad_mini"),
    ("iPhone di Marta", "iphone_di_marta"),
    ("iPhone Bet Apple Watch", "iphone_bet_apple_watch"),
    ("Città più bella", "citta_piu_bella"),
])
def test_slugify_replica_quella_di_home_assistant(nome, atteso):
    """Pinnata coi quattro nomi misurati sulla casa vera (25/09/2026) piu' un
    caso con spazi e accenti (fix round 1, 26/09/2026, vincolo 1)."""
    assert _slugify(nome) == atteso


def test_slugify_vuoto_e_solo_simboli():
    """Stessi due casi limite di `homeassistant.util.slugify`: testo vuoto o
    `None` -> stringa vuota; testo che si riduce al niente -> `"unknown"`."""
    assert _slugify("") == ""
    assert _slugify(None) == ""
    assert _slugify("!!!") == "unknown"


@pytest.mark.asyncio
async def test_guasto_get_states_zero_con_motivo_mai_eccezione():
    """Home Assistant tace sugli stati: il client rende la busta del silenzio,
    e non deve MAI diventare un'eccezione che risale -- zero servizi, il
    motivo del guasto, e nessuna lettura dopo."""
    ha = _house(silence={"/api/states"})

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients((), _REASON_HA_DOWN)
    assert [command for command, _extra in ha.calls] == ["/api/states"]


@pytest.mark.asyncio
async def test_guasto_get_states_il_testo_dell_eccezione_non_finisce_nel_registro(caplog):
    """Vincolo di sicurezza 1.2: il registro porta la CAUSA del guasto, mai il
    suo testo -- un messaggio di eccezione di rete potrebbe portare dentro
    di se' un frammento sensibile della richiesta che l'ha causato.

    Il trasporto cade con un testo che porta un segreto: il client vero lo
    mette nella busta (`errore`), e la prova lo verifica prima di guardare il
    registro -- altrimenti sarebbe verde perche' il segreto non c'era."""

    def _dropped(path):
        raise aiohttp.ClientConnectionError(
            "connessione persa (token=SEKRET-TOKEN-123)")

    ha = _house(answers={"/api/states": _dropped})
    assert "SEKRET-TOKEN-123" in (await ha.get_states([]))["errore"]

    with caplog.at_level(logging.WARNING):
        esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients((), _REASON_HA_DOWN)
    assert "recipients_for" in caplog.text
    assert "SEKRET-TOKEN-123" not in caplog.text


@pytest.mark.asyncio
async def test_guasto_read_registries_zero_con_motivo_mai_eccezione():
    """Home Assistant tace su tutti i registri. Il client vero non solleva:
    `read_registry` rende la busta del guasto, ed e' quel segnale a fermare
    la funzione -- non un'eccezione, che non arriva piu' (D3)."""
    ha = _house(states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
                entities=_THREE_TRACKERS, silence=set(REGISTRY_COMMANDS))

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients((), _REASON_HA_DOWN)
    assert "/api/services" not in [command for command, _extra in ha.calls]


@pytest.mark.asyncio
async def test_guasto_get_services_zero_con_motivo_mai_eccezione():
    ha = _house(states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
                entities=_THREE_TRACKERS, silence={"/api/services"})

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients((), _REASON_HA_DOWN)


@pytest.mark.asyncio
async def test_servizi_rifiutati_zero_con_motivo():
    """Il rifiuto (HA risponde 500) e' un guasto come il silenzio: nessun
    servizio si inventa da un registro che non e' arrivato."""
    ha = _house(states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
                entities=_THREE_TRACKERS, refuse={"/api/services": 500})

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients((), _REASON_HA_DOWN)


@pytest.mark.asyncio
async def test_registro_entita_non_disponibile_zero_con_motivo():
    """Home Assistant rifiuta il SOLO registro delle entita':
    `read_registry("entita")` risponde con la busta del guasto (lo stesso
    segnale che usa `workshop.py`): non si inventano candidati da un registro
    che non e' arrivato, anche se gli altri registri ci sono."""
    ha = _house(states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
                entities=_THREE_TRACKERS,
                refuse={"config/entity_registry/list": {
                    "code": "unknown_error", "message": "Unknown error"}})

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients((), _REASON_HA_DOWN)


@pytest.mark.asyncio
async def test_registro_dispositivi_rifiutato_degrada_sull_entity_id():
    """Il registro dei DISPOSITIVI non e' fatale (al contrario di quello delle
    entita', qui sopra): Home Assistant lo rifiuta, la busta del guasto arriva,
    e si degrada sul solo candidato dell'entity_id -- che regge finche' il
    dispositivo non e' mai stato rinominato. Il registro c'e' e porta il
    dispositivo col nome NUOVO: se il rifiuto non arrivasse, il servizio
    trovato sarebbe l'altro."""
    (command,) = _registry_commands("dispositivi")
    ha = _house(
        states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
        entities=[{"entity_id": "device_tracker.telefono_uno", "platform": "mobile_app",
                   "device_id": "d1"}],
        devices=[{"id": "d1", "name": "Il Telefono Nuovo di Casa"}],
        services=[{"domain": "notify", "services": {
            "mobile_app_telefono_uno": {}, "mobile_app_il_telefono_nuovo_di_casa": {}}}],
        refuse={command: {"code": "unknown_error", "message": "Unknown error"}})

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients(services=("notify.mobile_app_telefono_uno",), reason=None)
    assert command in [name for name, _extra in ha.calls]


@pytest.mark.asyncio
async def test_una_sola_lettura_per_lettore():
    """`get_states`, i due registri e `get_services` si chiamano UNA volta
    sola a esecuzione, in quest'ordine -- non un poll, non una rilettura per
    tracker.

    Le connessioni attese non si ricopiano: sono quelle che le quattro letture
    aprono, chiamate una volta ciascuna, su una casa identica."""
    def house():
        return _house(
            states=[_person_state(USER_ID, [
                "device_tracker.telefono_uno", "device_tracker.tablet_uno"])],
            entities=_THREE_TRACKERS)

    once = house()
    await once.get_states([])
    await once.read_registry("entita")
    await once.read_registry("dispositivi")
    await once.get_services()
    ha = house()

    await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert ha.connections == once.connections
    assert ("ws", _registry_commands("entita")) in ha.connections
    assert ("ws", _registry_commands("dispositivi")) in ha.connections


@pytest.mark.asyncio
async def test_due_tracker_che_convergono_sullo_stesso_servizio_danno_un_servizio_solo():
    """Extra 5 del Task 3: due `device_trackers` della stessa persona che
    portano allo STESSO `notify.mobile_app_*` (qui: il telefono nuovo ha
    preso il nome di quello vecchio, che resta collegato alla persona) non
    devono dare due push per un esito. Deduplicato qui, all'origine, in
    ordine stabile: il primo tracker che lo trova lo tiene."""
    ha = _house(
        states=[_person_state(USER_ID, ["device_tracker.telefono_uno",
                                        "device_tracker.telefono_nuovo",
                                        "device_tracker.tablet_uno"])],
        entities=[{"entity_id": "device_tracker.telefono_uno", "platform": "mobile_app",
                   "device_id": "d1"},
                  {"entity_id": "device_tracker.telefono_nuovo",
                   "platform": "mobile_app", "device_id": "d2"},
                  {"entity_id": "device_tracker.tablet_uno", "platform": "mobile_app",
                   "device_id": "d3"}],
        devices=[{"id": "d1", "name": "Telefono Uno"},
                 {"id": "d2", "name": "Telefono Uno"},
                 {"id": "d3", "name": "Tablet Uno"}])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, ServiceRegistry())

    assert esito == Recipients(
        services=("notify.mobile_app_telefono_uno", "notify.mobile_app_tablet_uno"),
        reason=None)


def _services_read(ha) -> int:
    return sum(1 for command, _extra in ha.calls if command == "/api/services")


@pytest.mark.asyncio
async def test_al_risveglio_col_registro_dei_servizi_fresco_nessuna_lettura():
    """A-04 (Tappa 2, Task 8): il recapito chiede i servizi `notify` al
    registro dei servizi (`action/registry.py::ServiceRegistry`), lo stesso
    che verifica i comandi -- non a Home Assistant per conto suo. Col
    registro fresco, il risveglio di una promessa non rilegge
    `/api/services`.

    Contato sul codice del 04/10/2026, prima di questa prova: ogni
    `recipients_for` di una persona collegata leggeva l'elenco INTERO dei
    servizi per cercarne i soli `notify.*`, anche alla nascita della promessa,
    subito dopo che lo strumento aveva scaldato il registro.

    Mutazione (verificata eseguendola): rimettere `ha.get_services()` al
    posto del registro -- rossa (`assert 1 == 0`)."""
    from hiris.app import server
    from hiris.app.action.registry import ServiceRegistry

    ha = _house(states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
                entities=_THREE_TRACKERS)
    registry = ServiceRegistry()
    await registry.ensure_fresh(ha)
    before = _services_read(ha)
    app = {"ha_client": ha, "service_registry": registry}

    esito = await server._promise_delivery(app)["recipients"](
        {"specie": "persona", "id": USER_ID})

    assert _services_read(ha) - before == 0
    assert esito == Recipients(services=("notify.mobile_app_telefono_uno",), reason=None)


@pytest.mark.asyncio
async def test_un_rinfresco_fallito_tiene_il_registro_di_prima():
    """Il cambio dichiarato di A-04: il registro gia' letto sopravvive a un
    rinfresco fallito (`ServiceRegistry.ensure_fresh`), e il recapito usa
    quello -- prima ogni guasto di `/api/services` dava «Home Assistant non
    ha risposto». Un registro mai letto, invece, resta un guasto
    (`test_guasto_get_services_zero_con_motivo_mai_eccezione`).

    Mutazione (verificata eseguendola): il recapito rilegge sempre e da' il
    guasto su ogni rinfresco fallito (`refresh` al posto di `ensure_fresh`,
    la regola di prima) -- rossa."""
    from hiris.app.action.registry import ServiceRegistry

    ha = _house(states=[_person_state(USER_ID, ["device_tracker.telefono_uno"])],
                entities=_THREE_TRACKERS)
    registry = ServiceRegistry()
    await registry.ensure_fresh(ha)
    registry.invalidate()          # un evento `service_registered`
    ha.mute("/api/services")       # e Home Assistant non risponde

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha, registry)

    assert _services_read(ha) == 2
    assert esito == Recipients(services=("notify.mobile_app_telefono_uno",), reason=None)
