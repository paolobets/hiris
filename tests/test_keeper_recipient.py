"""`recipients_for` -- il recapito del soggetto (spec §2.3, Task 1).

Una finta `ha` che riproduce solo i tre lettori che la funzione usa davvero
(`get_states`, `read_registries`, `get_services`), con la stessa forma
misurata sulla casa vera (vedi `hiris/app/keeper/recipient.py` per le fonti e
la misura del 25/09/2026)."""
import logging

import pytest

from hiris.app.keeper.recipient import Recipients, _slugify, recipients_for

USER_ID = "18ee7ec3dfa443929b3b760b30e3ac37"


def _stato_persona(user_id, trackers):
    return {"entity_id": "person.paolo_bettinelli", "state": "home",
            "attributes": {"user_id": user_id, "device_trackers": trackers}}


class FintaHA:
    """Le tre letture che `recipients_for` usa, misurate sulla casa vera
    (192.168.1.95, 25/09/2026): tre tracker `mobile_app` di cui uno -- il
    Watch -- senza servizio notify proprio, e un quarto tracker di controllo
    che non e' `mobile_app`."""

    def __init__(self, *, stati=None, entita=None, dispositivi=None,
                 non_disponibili=None, servizi=None, guasto=None):
        self.stati = stati if stati is not None else []
        self.entita = entita if entita is not None else []
        self.dispositivi = dispositivi if dispositivi is not None else []
        self.non_disponibili = non_disponibili if non_disponibili is not None else []
        self.servizi = servizi if servizi is not None else [
            {"domain": "notify", "services": {
                "mobile_app_iphone_bet": {}, "mobile_app_ipad_mini": {},
                "mobile_app_iphone_di_marta": {}, "mobile_app_nbbet_001": {},
            }}]
        self.guasto = guasto  # nome del lettore che deve sollevare, o None
        self.chiamate = []

    async def get_states(self, entity_ids):
        self.chiamate.append("get_states")
        if self.guasto == "get_states":
            raise TimeoutError("Home Assistant non ha risposto")
        return self.stati

    async def read_registries(self):
        self.chiamate.append("read_registries")
        if self.guasto == "read_registries":
            raise TimeoutError("Home Assistant non ha risposto")
        return {"entita": self.entita, "dispositivi": self.dispositivi}, self.non_disponibili

    async def get_services(self):
        self.chiamate.append("get_services")
        if self.guasto == "get_services":
            raise TimeoutError("Home Assistant non ha risposto")
        return self.servizi


_ENTITA_TRE_TRACKER = [
    {"entity_id": "device_tracker.iphone_bet", "platform": "mobile_app",
     "device_id": "d1"},
    {"entity_id": "device_tracker.ipad_mini", "platform": "mobile_app",
     "device_id": "d2"},
    {"entity_id": "device_tracker.iphone_bet_apple_watch", "platform": "mobile_app",
     "device_id": "d3"},
]


@pytest.mark.asyncio
async def test_persona_collegata_due_servizi_il_watch_cade_da_se():
    """Tre tracker `mobile_app`, uno (il Watch) senza servizio notify proprio
    -- misurato sulla casa vera: `notify.mobile_app_iphone_bet_apple_watch`
    non esiste. Il risultato porta i DUE servizi che esistono davvero, e
    nessun motivo (non e' un fallimento)."""
    ha = FintaHA(
        stati=[_stato_persona(USER_ID, [
            "device_tracker.iphone_bet", "device_tracker.ipad_mini",
            "device_tracker.iphone_bet_apple_watch"])],
        entita=_ENTITA_TRE_TRACKER)
    subject = {"specie": "persona", "id": USER_ID}

    esito = await recipients_for(subject, ha)

    assert esito == Recipients(
        services=("notify.mobile_app_iphone_bet", "notify.mobile_app_ipad_mini"),
        reason=None)


@pytest.mark.asyncio
async def test_tracker_non_mobile_app_ignorato():
    """Un tracker che NON e' `mobile_app` (un'altra integrazione di
    geolocalizzazione) non genera nessun candidato: non si prova nemmeno a
    indovinargli un servizio notify."""
    ha = FintaHA(
        stati=[_stato_persona(USER_ID, [
            "device_tracker.iphone_bet", "device_tracker.gps_logger_esterno"])],
        entita=_ENTITA_TRE_TRACKER + [
            {"entity_id": "device_tracker.gps_logger_esterno",
             "platform": "gpslogger", "device_id": "d9"}])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito == Recipients(services=("notify.mobile_app_iphone_bet",), reason=None)


@pytest.mark.asyncio
async def test_entity_id_con_suffisso_non_slug_non_diventa_un_candidato():
    """Guardia difensiva (vincolo di sicurezza 1.1): un `entity_id` che non
    rispettasse la forma slug (mai vera su una casa reale, ma il registro
    potrebbe mentire) non deve MAI diventare un servizio da chiamare, anche
    se per assurdo un servizio con quel nome esistesse davvero."""
    ha = FintaHA(
        stati=[_stato_persona(USER_ID, ["device_tracker.iPhone Strano!"])],
        entita=[{"entity_id": "device_tracker.iPhone Strano!",
                 "platform": "mobile_app", "device_id": "d1"}],
        servizi=[{"domain": "notify",
                  "services": {"mobile_app_iPhone Strano!": {}}}])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_persona_senza_user_id_collegato_zero_con_motivo_di_collegamento():
    """`person.marta` ha `user_id` vuoto (misurato sulla casa vera): nessuno
    stato corrisponde all'id del soggetto, e il motivo dice di collegare la
    persona all'utente in Home Assistant."""
    ha = FintaHA(stati=[_stato_persona(None, ["device_tracker.iphone_di_marta"])])

    esito = await recipients_for({"specie": "persona", "id": "id-di-marta"}, ha)

    assert esito.services == ()
    assert esito.reason is not None
    assert "collega" in esito.reason and "Persone" in esito.reason


@pytest.mark.asyncio
async def test_due_persone_collegate_allo_stesso_utente_zero_con_motivo_ambiguo():
    """Una casa mal configurata dove due `person` portano lo stesso
    `user_id`: la prima trovata sarebbe una scelta indovinata, non dedotta
    (security review 26/09/2026, vincolo 1.5) -- zero servizi, un motivo
    distinto da quello di «non collegata»."""
    stato_2 = {"entity_id": "person.paolo_secondo", "state": "home",
               "attributes": {"user_id": USER_ID,
                              "device_trackers": ["device_tracker.ipad_mini"]}}
    ha = FintaHA(stati=[
        _stato_persona(USER_ID, ["device_tracker.iphone_bet"]), stato_2])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

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
    ha = FintaHA()

    esito = await recipients_for({"specie": "persona", "id": None}, ha)

    assert esito.services == ()
    assert "collega" in esito.reason
    assert ha.chiamate == []  # nessuna lettura: non c'e' niente da cercare


@pytest.mark.asyncio
async def test_soggetto_luogo_zero_con_motivo_del_servizio():
    """Retro Panel (`specie == "luogo"`): nessuna strada oggi, e il motivo e'
    esattamente quello della spec §2.3."""
    ha = FintaHA()

    esito = await recipients_for({"specie": "luogo", "id": "retro-panel"}, ha)

    assert esito == Recipients((), "il servizio non ha ancora dichiarato come si avvisa.")
    assert ha.chiamate == []


@pytest.mark.asyncio
async def test_soggetto_integrazione_zero_con_motivo_del_servizio():
    """Un'integrazione firmata: stessa frase di `luogo`, stessa non-strada."""
    ha = FintaHA()

    esito = await recipients_for({"specie": "integrazione", "id": "mcp-gateway"}, ha)

    assert esito.reason == "il servizio non ha ancora dichiarato come si avvisa."
    assert esito.services == ()


@pytest.mark.asyncio
async def test_soggetto_nessuno_zero_con_motivo():
    """Il ponte (`specie == "nessuno"`, es. lo schedulatore): non e' una
    persona, zero servizi, un motivo leggibile."""
    ha = FintaHA()

    esito = await recipients_for({"specie": "nessuno", "id": None}, ha)

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_soggetto_none_zero_con_motivo():
    """Nessun soggetto affatto (mai dovrebbe capitare in produzione, ma la
    funzione non deve sollevare)."""
    esito = await recipients_for(None, FintaHA())

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_persona_senza_device_trackers_zero_con_motivo_app():
    """La persona e' collegata ma non ha nessun `device_tracker`: zero
    servizi, il motivo parla di app collegata (non di notifiche attive --
    qui non c'e' nessuna app da attivare, fix round 1, 26/09/2026, vincolo
    4: i due motivi ora si distinguono)."""
    ha = FintaHA(stati=[_stato_persona(USER_ID, [])])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito.services == ()
    assert "collegato con l'app" in esito.reason


@pytest.mark.asyncio
async def test_persona_solo_watch_notifiche_non_attive():
    """La persona ha un dispositivo `mobile_app` (il Watch), ma nessuno dei
    suoi tracker risolve a un servizio notify esistente: qui l'app C'E',
    manca l'attivazione -- motivo diverso da «nessun dispositivo» (fix round
    1, 26/09/2026, vincolo 4)."""
    ha = FintaHA(
        stati=[_stato_persona(USER_ID, ["device_tracker.iphone_bet_apple_watch"])],
        entita=[_ENTITA_TRE_TRACKER[2]])  # solo il Watch

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito.services == ()
    assert "notifiche attive" in esito.reason
    assert "collegato con l'app" not in esito.reason


@pytest.mark.asyncio
async def test_dispositivo_rinominato_risolve_dal_nome_del_registro_dispositivi():
    """Il dispositivo e' stato rinominato nell'app Companion DOPO la prima
    registrazione: l'entity_id resta congelato al nome vecchio
    (`device_tracker.iphone_bet`, mai piu' cambiato da Home Assistant --
    `mobile_app/config_flow.py::async_step_registration`), ma Home Assistant
    registra il servizio SUL NOME NUOVO
    (`mobile_app/webhook.py::webhook_update_registration` riscrive
    `device_registry.name` e ricarica notify -- vedi il docstring del
    modulo). Il candidato giusto viene dal registro dei DISPOSITIVI, non
    dalla coda dell'entity_id (fix round 1, 26/09/2026, vincolo 1)."""
    ha = FintaHA(
        stati=[_stato_persona(USER_ID, ["device_tracker.iphone_bet"])],
        entita=[{"entity_id": "device_tracker.iphone_bet", "platform": "mobile_app",
                 "device_id": "d1"}],
        dispositivi=[{"id": "d1", "name": "Il Telefono Nuovo di Paolo"}],
        servizi=[{"domain": "notify", "services": {
            "mobile_app_il_telefono_nuovo_di_paolo": {}}}])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito == Recipients(
        services=("notify.mobile_app_il_telefono_nuovo_di_paolo",), reason=None)


@pytest.mark.asyncio
async def test_dispositivo_mai_rinominato_degrada_sull_entity_id():
    """Il registro dei dispositivi non porta il device (o non e' arrivato):
    si degrada sul secondo candidato, l'entity_id -- che regge finche' il
    dispositivo non e' mai stato rinominato (il caso comune, misurato sulla
    casa vera)."""
    ha = FintaHA(
        stati=[_stato_persona(USER_ID, ["device_tracker.iphone_bet"])],
        entita=[{"entity_id": "device_tracker.iphone_bet", "platform": "mobile_app",
                 "device_id": "d1"}],
        dispositivi=[])  # nessun dispositivo "d1" nel registro

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito == Recipients(services=("notify.mobile_app_iphone_bet",), reason=None)


@pytest.mark.asyncio
async def test_nome_dispositivo_preferito_al_entity_id_quando_entrambi_esistono():
    """Se per assurdo ENTRAMBI i candidati risultassero fra i servizi notify
    (un registro incoerente: il vecchio servizio non e' ancora sparito dopo
    una rinomina), si sceglie UNO solo -- quello dal nome del dispositivo,
    che e' la fonte di oggi -- mai due push per lo stesso telefono."""
    ha = FintaHA(
        stati=[_stato_persona(USER_ID, ["device_tracker.iphone_bet"])],
        entita=[{"entity_id": "device_tracker.iphone_bet", "platform": "mobile_app",
                 "device_id": "d1"}],
        dispositivi=[{"id": "d1", "name": "Nome Nuovo"}],
        servizi=[{"domain": "notify", "services": {
            "mobile_app_nome_nuovo": {}, "mobile_app_iphone_bet": {}}}])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

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
    """Un guasto di Home Assistant durante la prima lettura non deve MAI
    diventare un'eccezione che risale: zero servizi, motivo del guasto."""
    ha = FintaHA(guasto="get_states")

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_guasto_get_states_il_testo_dell_eccezione_non_finisce_nel_registro(caplog):
    """Vincolo di sicurezza 1.2: il registro porta il TIPO del guasto, mai il
    suo testo -- un messaggio di eccezione di rete potrebbe portare dentro
    di se' un frammento sensibile della richiesta che l'ha causato."""

    class FintaConSegreto(FintaHA):
        async def get_states(self, entity_ids):
            self.chiamate.append("get_states")
            raise TimeoutError("connessione persa (token=SEKRET-TOKEN-123)")

    with caplog.at_level(logging.WARNING):
        esito = await recipients_for({"specie": "persona", "id": USER_ID},
                                     FintaConSegreto())

    assert esito.services == ()
    assert "SEKRET-TOKEN-123" not in caplog.text


@pytest.mark.asyncio
async def test_guasto_read_registries_zero_con_motivo_mai_eccezione():
    ha = FintaHA(stati=[_stato_persona(USER_ID, ["device_tracker.iphone_bet"])],
                 guasto="read_registries")

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_guasto_get_services_zero_con_motivo_mai_eccezione():
    ha = FintaHA(stati=[_stato_persona(USER_ID, ["device_tracker.iphone_bet"])],
                 entita=_ENTITA_TRE_TRACKER, guasto="get_services")

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_registro_entita_non_disponibile_zero_con_motivo():
    """`read_registries` risponde ma dichiara `entita` fra i `non_disponibili`
    (lo stesso segnale che usa `workshop.py`): non si inventano candidati da
    un registro che non e' arrivato."""
    ha = FintaHA(stati=[_stato_persona(USER_ID, ["device_tracker.iphone_bet"])],
                 entita=[], non_disponibili=["entita"])

    esito = await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert esito.services == ()
    assert esito.reason


@pytest.mark.asyncio
async def test_una_sola_lettura_per_lettore():
    """`get_states`, `read_registries` e `get_services` si chiamano UNA volta
    sola a esecuzione -- non un poll, non una rilettura per tracker."""
    ha = FintaHA(
        stati=[_stato_persona(USER_ID, [
            "device_tracker.iphone_bet", "device_tracker.ipad_mini"])],
        entita=_ENTITA_TRE_TRACKER)

    await recipients_for({"specie": "persona", "id": USER_ID}, ha)

    assert ha.chiamate == ["get_states", "read_registries", "get_services"]
