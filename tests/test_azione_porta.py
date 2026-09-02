"""La porta: l'unico punto del prodotto che esegue qualcosa su Home Assistant.

Task 4 della fetta «comandare». Mette insieme i tre pezzi gia' fatti — il
registro (Task 1, che legge), `call_service` (Task 2, che attua e non verifica
niente), `verifica` (Task 3, pura, che dice di no e dice perche') — nella
sequenza che e' l'invariante centrale della spec: **verifica → chiama →
rilegge → registra**.

Due famiglie di test, e la seconda vale quanto la prima:

1. la sequenza (esegue, rifiuta senza toccare HA, racconta cosa e' cambiato,
   trasforma un guasto in una frase leggibile);
2. **i due buchi che il Task 3 ha lasciato aperti di proposito**, perche' una
   funzione pura non puo' chiuderli: registro vuoto e specchio dello stato
   vuoto. Sono la stessa cosa vista due volte — un ingresso vuoto che fa dire
   al prodotto una frase falsa con sicurezza («Domini disponibili: .»,
   «l'entita' non esiste in questa casa»). `verifica()` non puo' distinguere
   «non c'e'» da «non l'ho letto»; la porta si', ed e' il suo compito.

**Nota sulle finte, ed e' la parte piu' importante di questo file.** Una
finta che regala al prodotto qualcosa che la produzione non ha non e' un
test: e' una conferma. Qui e' successo, e si e' pagato due volte -- la
`FintaCache` prendeva un `dopo=` e mostrava lo stato nuovo alla seconda
lettura, cioe' modellava uno specchio che si aggiorna da solo fra la chiamata
e la rilettura. In produzione lo specchio non fa questo, e 1207 test verdi
descrivevano un prodotto rotto. **Quel parametro non esiste piu'.**

Le finte di adesso mentono come mente la realta' misurata sull'impianto vero:
`call_service` restituisce una lista **vuota** (e' il valore predefinito), lo
specchio si muove **solo** quando arriva un annuncio, e l'annuncio arriva
**dopo** il ritorno della chiamata. Se lo stato deve cambiare, qualcuno deve
annunciarlo -- come in casa.

`EntityCache` (`hiris/app/proxy/entity_cache.py`) espone `all_states()`, che
restituisce una **lista** di dizionari minimali con chiave `id` (non
`entity_id`): la finta e' adattata al metodo vero, il codice di produzione non
e' stato piegato al test. Espone anche `loaded`, la bandiera che distingue
«casa senza entita'» da «inventario non ancora pronto», e da questa versione
`add_state_listener`/`remove_state_listener`, il rubinetto degli annunci.

Come in `tests/test_azione_verifica.py`: niente fixture asincrone — la suite
gira in modalita' `strict` di pytest-asyncio, quindi ogni test async porta il
suo `@pytest.mark.asyncio` e la preparazione sta in un helper `await`ato.
"""
import asyncio
import time

import pytest

from hiris.app.action import actuator as porta_modulo
from hiris.app.action.actuator import ActionActuator
from hiris.app.action.registry import ServiceRegistry
from hiris.app.proxy.entity_cache import _to_minimal

# La scadenza vera e' 2 secondi, e il perche' sta scritto accanto alla
# costante (`porta.STATE_WAIT_S`). Qui si accorcia a 50 ms perche' cio' che
# questi test misurano non e' la DURATA ma il comportamento: che si aspetti,
# che si smetta di aspettare, e che l'avviso dichiari per quanto si e'
# aspettato. Il valore vero resta pinnato da
# `test_la_scadenza_e_dichiarata_finita_e_una_sola`, e nessun test scrive a
# mano il numero: lo leggono dalla costante in vigore, cosi' cambiarla non
# rende bugiardi gli avvisi.
SCADENZA_NEI_TEST = 0.05


@pytest.fixture(autouse=True)
def _scadenza_corta(monkeypatch):
    monkeypatch.setattr(porta_modulo, "STATE_WAIT_S", SCADENZA_NEI_TEST)


RISPOSTA_HA = [
    # `target`, scritto a mano nella forma plausibile di /api/services (NON
    # misurato su un'installazione vera -- vedi la nota sopra
    # `_DOMINI_UNIVERSALI` in `action/verification.py`): senza, dopo la review
    # finale (rilievo CRITICO ①) questi due servizi smetterebbero di
    # richiedere un bersaglio, e i test di questo file che chiamano
    # SPEGNI_IL_SALOTTO smetterebbero di provare cio' che dicono di provare.
    {"domain": "light", "services": {
        "turn_off": {"fields": {"transition": {}},
                     "target": {"entity": [{"domain": ["light"]}]}},
        "turn_on": {"fields": {"brightness": {}},
                    "target": {"entity": [{"domain": ["light"]}]}}}},
    # un servizio parametrico vero, per il confronto che guarda gli attributi
    {"domain": "climate", "services": {
        "set_temperature": {"fields": {"temperature": {}},
                            "target": {"entity": [{"domain": ["climate"]}]}}}},
    # Un servizio SENZA `target`, come i `notify.*` veri -- la famiglia
    # «senza bersaglio», in fondo al file.
    {"domain": "notify", "services": {
        "mobile_app_x": {"fields": {"message": {}, "title": {}}}}},
]


class FintoClient:
    """Home Assistant visto dalla porta, con le **tre bocche** che ha davvero.

    1. **Il ritorno di `call_service`** (`cambiati`): gli stati completi che
       Home Assistant dichiara cambiati durante l'esecuzione. Sull'impianto
       del proprietario e' stato misurato **vuoto**, anche a comando riuscito
       -- ed e' per questo che qui il valore predefinito e' la lista vuota.
    2. **L'annuncio del websocket** (`annuncia`): gli stati, sempre nella
       forma di Home Assistant, che arrivano agli ascoltatori **dopo** il
       ritorno della chiamata -- fra `ritardo` secondi, mai prima. Con
       `ritardo=None` arrivano invece DENTRO la chiamata: e' l'altro caso
       vero, la casa veloce, e serve a provare che un annuncio arrivato
       presto non si perde.
    3. **Il rubinetto** (`add_state_listener`/`remove_state_listener`): vero,
       con la lista ispezionabile in `ascoltatori`. Un ascoltatore effimero
       che non si togliesse resterebbe li' a farsi contare.

    L'annuncio muove lo **specchio** prima di svegliare gli ascoltatori,
    perche' quello e' l'ordine della produzione: `EntityCache` si iscrive
    all'avvio, la porta molto dopo.
    """

    def __init__(self, cambiati=None, annuncia=None, ritardo=0.0, specchio=None):
        self.chiamate = []
        self.ascoltatori = []
        # Cosa mostrava lo specchio nell'istante in cui `call_service` e'
        # tornata. E' il campione che smaschera una finta troppo gentile: se
        # qui si vedesse gia' lo stato nuovo, la freschezza sarebbe di nuovo
        # regalata e questo file tornerebbe a confermare chi l'ha scritto.
        self.specchio_al_ritorno = None
        self._cambiati = cambiati if cambiati is not None else []
        self._annuncia = list(annuncia or [])
        self._ritardo = ritardo
        self._specchio = specchio

    async def get_services(self):
        return RISPOSTA_HA

    def add_state_listener(self, callback):
        self.ascoltatori.append(callback)

    def remove_state_listener(self, callback):
        if callback in self.ascoltatori:
            self.ascoltatori.remove(callback)

    async def call_service(self, domain, service, data):
        self.chiamate.append((domain, service, data))
        if self._annuncia and self._ritardo is None:
            self._annuncia_ora()
        elif self._annuncia:
            asyncio.get_running_loop().create_task(self._annuncia_fra_poco())
        if self._specchio is not None:
            self.specchio_al_ritorno = self._specchio.sbircia()
        return list(self._cambiati)

    async def _annuncia_fra_poco(self):
        await asyncio.sleep(self._ritardo)
        self._annuncia_ora()

    def _annuncia_ora(self):
        for stato in self._annuncia:
            # Prima lo specchio, poi chi ascolta: e' l'ordine con cui il ciclo
            # websocket vero percorre `_state_listeners`.
            if self._specchio is not None:
                self._specchio.annuncio(stato)
            for callback in list(self.ascoltatori):
                callback({"entity_id": stato["entity_id"], "old_state": None,
                          "new_state": stato})


class FintaCache:
    """Lo specchio dello stato vivo. **Si muove solo quando l'evento arriva.**

    Imita `EntityCache`: `all_states()` restituisce una lista di dizionari
    minimali (`id`, `state`, ...), `loaded` dice se la prima lettura da Home
    Assistant e' mai arrivata in fondo, e `annuncio()` fa esattamente cio' che
    fa `on_state_changed` -- l'unico modo in cui questo specchio cambia.

    **Qui c'era la bugia** (vedi il docstring del file): il vecchio `dopo=`
    mostrava lo stato nuovo alla seconda lettura, cioe' regalava alla porta la
    freschezza che la produzione non ha. Non esiste piu'.
    """

    def __init__(self, stati, loaded=True, rompe_dalla_lettura=None):
        self._stati = {eid: _voce(eid, valore) for eid, valore in stati.items()}
        self.loaded = loaded
        self._rompe_dalla_lettura = rompe_dalla_lettura
        self.letture = 0

    def all_states(self):
        self.letture += 1
        if (self._rompe_dalla_lettura is not None
                and self.letture >= self._rompe_dalla_lettura):
            raise RuntimeError("websocket caduto")
        return [dict(voce) for voce in self._stati.values()]

    def annuncio(self, stato_ha):
        """Cio' che fa `EntityCache.on_state_changed`, con la normalizzazione
        VERA (`_to_minimal`): se domani cambiasse la forma della voce
        minimale, questa finta cambierebbe con lei invece di restare indietro
        in silenzio."""
        voce = _to_minimal(stato_ha)
        self._stati[voce["id"]] = voce

    def sbircia(self):
        """Lo stato dello specchio SENZA contare come lettura -- serve ai test
        per dimostrare che al ritorno di `call_service` era ancora indietro."""
        return {eid: voce.get("state") for eid, voce in self._stati.items()}


def _voce(eid: str, valore) -> dict:
    """Una voce minimale come la costruisce `EntityCache._to_minimal`.

    La forma corta (`"light.salotto": "on"`) resta quella dei casi in cui
    conta solo lo stato; quella lunga (`{"state": ..., "attributes": {...}}`)
    serve ai comandi parametrici, dove lo stato NON cambia e cambia un
    attributo -- ed e' la stessa forma che `_to_minimal` produce davvero,
    pinnata da `test_gli_attributi_confrontati_sono_quelli_che_lo_specchio_tiene`.
    """
    if isinstance(valore, dict):
        return {"id": eid, **valore}
    return {"id": eid, "state": valore}


def _casa(stati, *, cambiati=None, annuncia=None, ritardo=0.0, loaded=True,
          rompe_dalla_lettura=None):
    """Il cablaggio di produzione in miniatura: un client, uno specchio, e
    l'unico filo che li lega -- gli annunci. Restituire i due separati serve
    a poterli interrogare entrambi dopo."""
    cache = FintaCache(stati, loaded=loaded,
                       rompe_dalla_lettura=rompe_dalla_lettura)
    client = FintoClient(cambiati=cambiati, annuncia=annuncia, ritardo=ritardo,
                         specchio=cache)
    return client, cache


SALOTTO_ACCESO = {"light.salotto": "on"}
SALOTTO_SPENTO = {"light.salotto": "off"}

SPEGNI_IL_SALOTTO = {"servizio": "light.turn_off",
                     "bersaglio": {"entita": ["light.salotto"]}}

# Gli annunci: stati nella forma di HOME ASSISTANT (`entity_id` e `attributes`
# interi), che e' quella con cui viaggiano sia il ritorno di `call_service`
# sia gli eventi `state_changed`. La porta deve saperli normalizzare entrambi.
ANNUNCIA_IL_SALOTTO_SPENTO = [
    {"entity_id": "light.salotto", "state": "off",
     "attributes": {"friendly_name": "Salotto", "supported_color_modes": ["hs"]}},
]

# Il comando parametrico: `state` resta «heat», cambia solo la temperatura.
CLIMA_A_19 = {"climate.salotto": {"state": "heat", "attributes": {"temperature": 19}}}
CLIMA_A_21 = {"climate.salotto": {"state": "heat", "attributes": {"temperature": 21}}}
METTI_A_21 = {"servizio": "climate.set_temperature",
              "bersaglio": {"entita": ["climate.salotto"]},
              "dati": {"temperature": 21}}
ANNUNCIA_IL_CLIMA_A_21 = [
    {"entity_id": "climate.salotto", "state": "heat",
     "attributes": {"friendly_name": "Salotto", "temperature": 21}},
]

# -- I due difetti misurati sulla prima casa vera (2.2.1) --------------------
#
# Ricostruiti con i dati veri delle due prove, e con lo specchio FERMO --
# com'e' in produzione nell'istante della rilettura.
#
# Gli stati qui sotto sono nella forma di HOME ASSISTANT (`entity_id`, e
# `attributes` INTERI), non nella voce minimale dello specchio: e' cio' che
# `call_service` restituisce davvero, e la porta deve saperlo normalizzare.
HA_RIPORTA_IL_SALOTTO_SPENTO = [
    {"entity_id": "light.salotto", "state": "off",
     "attributes": {"friendly_name": "Salotto",
                    "supported_color_modes": ["hs"]}},
]

# Il termostato della camera: `state` resta «heat», cambia `temperature`, e
# accanto viaggiano i valori con cui il modello ragiona (26.9 in stanza,
# riscaldamento a riposo). La casa vera ha misurato che l'impronta li legge
# bene: cio' che sbagliava era da dove veniva il «dopo».
CAMERA_A_17_5 = {"climate.camera": {"state": "heat", "attributes": {
    "hvac_action": "idle", "current_temperature": 26.9, "temperature": 17.5}}}
METTI_LA_CAMERA_A_19_5 = {"servizio": "climate.set_temperature",
                          "bersaglio": {"entita": ["climate.camera"]},
                          "dati": {"temperature": 19.5}}
HA_RIPORTA_LA_CAMERA_A_19_5 = [
    {"entity_id": "climate.camera", "state": "heat",
     "attributes": {"friendly_name": "Camera", "min_temp": 7, "max_temp": 35,
                    "hvac_modes": ["off", "heat"], "hvac_action": "idle",
                    "current_temperature": 26.9, "temperature": 19.5}},
]


async def _registro_pronto(client):
    registro = ServiceRegistry()
    await registro.refresh(client)
    return registro


async def _porta_pronta():
    """La casa che risponde: il comando parte, e poco dopo l'annuncio arriva.

    `cambiati` resta vuoto -- il valore misurato sull'impianto vero -- quindi
    l'unica cosa che dice com'e' andata e' l'annuncio, e la porta deve
    aspettarlo per vederlo.
    """
    client, cache = _casa(SALOTTO_ACCESO, annuncia=ANNUNCIA_IL_SALOTTO_SPENTO)
    registro = await _registro_pronto(client)
    return ActionActuator(client, registro, cache), client, cache


# --- la sequenza ------------------------------------------------------------

@pytest.mark.asyncio
async def test_esegue_e_racconta_cosa_e_cambiato():
    porta, client, cache = await _porta_pronta()
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is True
    assert client.chiamate == [("light", "turn_off", {"entity_id": ["light.salotto"]})]
    assert esito["servizio"] == "light.turn_off"
    assert esito["entita"] == ["light.salotto"]
    assert esito["prima"] == {"light.salotto": {"state": "on"}}
    assert esito["dopo"] == {"light.salotto": {"state": "off"}}
    assert esito["cambiato"] == ["light.salotto"]
    assert "avviso" not in esito
    assert cache.letture == 2, (
        "lo specchio va letto due volte: prima per verificare, dopo per "
        "raccontare cosa e' successo davvero")


@pytest.mark.asyncio
async def test_un_rifiuto_non_chiama_home_assistant():
    porta, client, _ = await _porta_pronta()
    esito = await porta.execute(
        {"servizio": "light.esplodi", "bersaglio": {"entita": ["light.salotto"]}},
        actor="chat")
    assert esito["eseguito"] is False
    assert "non esiste" in esito["errore"]
    assert client.chiamate == [], (
        "una chiamata rifiutata NON deve arrivare a Home Assistant")


@pytest.mark.asyncio
async def test_se_nulla_cambia_lo_dichiara():
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))  # non cambia
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is True
    assert esito["cambiato"] == []
    assert "avviso" in esito, (
        "una chiamata che non cambia niente non deve passare per un successo muto")


@pytest.mark.asyncio
async def test_i_parametri_della_chiamata_arrivano_a_home_assistant():
    """`dati` non e' decorazione: senza, «spegni fra 5 secondi» diventa «spegni»."""
    porta, client, _ = await _porta_pronta()
    esito = await porta.execute(dict(SPEGNI_IL_SALOTTO, dati={"transition": 5}),
                               actor="chat")
    assert esito["eseguito"] is True
    assert client.chiamate == [
        ("light", "turn_off", {"transition": 5, "entity_id": ["light.salotto"]})]


@pytest.mark.asyncio
async def test_un_guasto_di_home_assistant_diventa_un_errore_leggibile():
    class ClientCheRompe(FintoClient):
        async def call_service(self, domain, service, data):
            raise RuntimeError("HTTP 500")

    client = ClientCheRompe()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is False
    assert "HTTP 500" in esito["errore"]


@pytest.mark.asyncio
async def test_un_registro_illeggibile_diventa_un_errore_leggibile():
    """`ensure_fresh` solleva al primissimo caricamento (contratto del Task 1)."""
    class ClientSenzaServizi(FintoClient):
        async def get_services(self):
            raise RuntimeError("connessione rifiutata")

    client = ClientSenzaServizi()
    porta = ActionActuator(client, ServiceRegistry(), FintaCache(SALOTTO_ACCESO))
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is False
    assert "connessione rifiutata" in esito["errore"]
    assert client.chiamate == []


@pytest.mark.asyncio
async def test_l_origine_non_cambia_l_esito():
    """La porta non sa chi la chiama, ed e' cio' che la rende riusabile.

    Lo schedulatore (fetta 3) e il brain useranno questa stessa porta senza
    modificarla: se l'esito dipendesse dall'origine, non potrebbero.
    """
    esiti = []
    for origine in ("chat", "schedulatore", "brain"):
        porta, client, _ = await _porta_pronta()
        esiti.append(await porta.execute(SPEGNI_IL_SALOTTO, actor=origine))
        assert client.chiamate == [("light", "turn_off", {"entity_id": ["light.salotto"]})]
    assert esiti[0] == esiti[1] == esiti[2]


# --- i due buchi del Task 3 -------------------------------------------------

@pytest.mark.asyncio
async def test_un_registro_vuoto_non_diventa_una_casa_che_non_sa_fare_niente():
    """Buco (a). `verifica()` con un registro vuoto rifiuta dicendo «Domini
    disponibili: .» — una frase falsa detta con sicurezza. La porta deve dire
    che non ha letto, non che Home Assistant non sa fare niente."""
    class ClientMuto(FintoClient):
        async def get_services(self):
            return []

    client = ClientMuto()
    registro = await _registro_pronto(client)
    assert registro.domains() == [], "premessa: il registro e' davvero vuoto"
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is False
    assert "Domini disponibili" not in esito["errore"]
    assert "non so" in esito["errore"], (
        "il motivo dev'essere «non l'ho letto», non «non esiste»")
    assert client.chiamate == []


@pytest.mark.asyncio
async def test_uno_specchio_vuoto_non_nega_un_entita_che_esiste():
    """Buco (b), forma «vuoto». Con `stati == {}` la verifica rifiuta ogni
    entita' con «non esiste in questa casa»: il motivo piu' fuorviante
    possibile, perche' suona definitivo."""
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache({}))
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is False
    assert "non esiste in questa casa" not in esito["errore"]
    assert "non vedo" in esito["errore"]
    assert client.chiamate == []


@pytest.mark.asyncio
async def test_uno_specchio_non_ancora_pronto_non_nega_un_entita_che_esiste():
    """Buco (b), forma «a meta'». `loaded is False` significa che la prima
    lettura da Home Assistant non e' mai arrivata in fondo: cio' che c'e'
    dentro sono le poche entita' mosse dagli eventi, non la casa."""
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro,
                        FintaCache({"light.cucina": "on"}, loaded=False))
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is False
    assert "non esiste in questa casa" not in esito["errore"]
    assert "non vedo" in esito["errore"]
    assert client.chiamate == []


@pytest.mark.asyncio
async def test_senza_specchio_del_tutto_non_nega_un_entita_che_esiste():
    """Terza forma dello stesso buco: la cache non e' proprio cablata."""
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, None)
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is False
    assert "non vedo" in esito["errore"]
    assert client.chiamate == []


@pytest.mark.asyncio
async def test_se_la_rilettura_non_riesce_non_inventa_cosa_e_cambiato():
    """La chiamata **e' partita**: negarlo sarebbe falso quanto affermare un
    cambiamento che non si e' potuto vedere. Si dice l'una e l'altra cosa."""
    client = FintoClient()
    registro = await _registro_pronto(client)
    cache = FintaCache(SALOTTO_ACCESO, rompe_dalla_lettura=2)
    porta = ActionActuator(client, registro, cache)
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is True
    assert client.chiamate == [("light", "turn_off", {"entity_id": ["light.salotto"]})]
    assert esito["cambiato"] == []
    assert "rileggere" in esito["avviso"]
    assert esito["dopo"] == {"light.salotto": None}


# --- il comando parametrico -------------------------------------------------
#
# R-3 della review della fetta. Prima di questi test il confronto guardava il
# solo `state`: «metti il termostato a 21» eseguiva davvero e veniva raccontato
# come «nessuno stato e' cambiato», perche' cio' che cambia e'
# `attributes.temperature`. Non e' il difetto peggiore possibile -- non
# dichiarava un successo mai misurato, sbagliava rifiutando il proprio stesso
# lavoro -- ma e' una frase falsa detta con sicurezza, cioe' la famiglia che
# questa porta esiste per chiudere, e su una casa vera capita tutti i giorni:
# clima, luminosita', tapparelle, volume, ventilatori.

@pytest.mark.asyncio
async def test_un_comando_parametrico_non_viene_raccontato_come_nulla_e_cambiato():
    client, cache = _casa(CLIMA_A_19, annuncia=ANNUNCIA_IL_CLIMA_A_21)
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, cache)
    esito = await porta.execute(METTI_A_21, actor="chat")
    assert esito["eseguito"] is True
    assert esito["cambiato"] == ["climate.salotto"], (
        "la temperatura e' passata da 19 a 21: dire che non e' cambiato niente "
        "sarebbe raccontare cio' che e' stato chiesto invece di cio' che e' "
        "successo, col verso sbagliato")
    assert "avviso" not in esito


@pytest.mark.asyncio
async def test_prima_e_dopo_mostrano_la_differenza_che_cambiato_dichiara():
    """`cambiato` dev'essere sempre spiegabile da `prima` e `dopo`: sono i tre
    campi che il prompt promette al modello, e se il primo affermasse una
    differenza che gli altri due non mostrano il modello avrebbe in mano un
    racconto che si contraddice."""
    client, cache = _casa(CLIMA_A_19, annuncia=ANNUNCIA_IL_CLIMA_A_21)
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, cache)
    esito = await porta.execute(METTI_A_21, actor="chat")
    assert esito["prima"] == {"climate.salotto": {"state": "heat", "temperature": 19}}
    assert esito["dopo"] == {"climate.salotto": {"state": "heat", "temperature": 21}}
    for entita in esito["cambiato"]:
        assert esito["prima"][entita] != esito["dopo"][entita]


@pytest.mark.asyncio
async def test_un_parametrico_che_davvero_non_cambia_niente_lo_dichiara_ancora():
    """L'altra faccia: allargare il confronto agli attributi non deve
    trasformare l'avviso in un ramo morto. Se ne' lo stato ne' gli attributi
    si muovono, e Home Assistant non riporta niente, l'avviso resta -- ed e'
    il caso della valvola termostatica gia' a 21."""
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(CLIMA_A_21))
    esito = await porta.execute(METTI_A_21, actor="chat")
    assert esito["eseguito"] is True
    assert esito["cambiato"] == []
    assert "non ha riportato nessun cambiamento" in esito["avviso"]


def test_gli_attributi_confrontati_sono_quelli_che_lo_specchio_tiene():
    """La guardia contro il difetto piu' silenzioso di questa correzione.

    La porta puo' confrontare solo cio' che `EntityCache` mette nella voce
    minimale (`_DOMAIN_ATTRS`). Le finte di questo file gli attributi se li
    scrivono da sole: se domani `temperature` uscisse da quell'elenco, tutti i
    test qui sopra resterebbero verdi e la casa vera tornerebbe a sentirsi dire
    «non e' cambiato niente». Qui l'impronta si costruisce sulla voce che
    produce il codice VERO dell'inventario.
    """
    from hiris.app.action.actuator import _fingerprint
    from hiris.app.proxy.entity_cache import _to_minimal

    voce = _to_minimal({"entity_id": "climate.salotto", "state": "heat",
                        "attributes": {"temperature": 21, "friendly_name": "Salotto"}})
    assert _fingerprint(voce) == {"state": "heat", "temperature": 21}, (
        "l'attributo che regge «metti il termostato a 21» non arriva piu' "
        "dall'inventario alla porta: o e' uscito da _DOMAIN_ATTRS, o la voce "
        "minimale ha cambiato forma")


# --- la fonte del «dopo» ----------------------------------------------------
#
# **Il primo difetto trovato dal vivo, e il motivo per cui questa famiglia
# esiste.** Sulla prima casa vera, alla prima prova: il proprietario chiede di
# spegnere due abat-jour, si spengono davvero, e HIRIS risponde «entrambi
# risultano ancora accesi sia prima che dopo ... probabile problema di
# comunicazione col dispositivo». Seconda misura, stesso sintomo su un altro
# dominio e un altro tipo di dato: «porta il termostato a 19.5», il termostato
# ci va, e HIRIS dice che e' rimasto a 17.5.
#
# **Perche' nessuno dei 1207 test lo copriva.** Non e' che mancasse un caso:
# la finta lo NEGAVA. La vecchia `FintaCache(..., dopo=...)` mostrava lo stato
# nuovo alla seconda `all_states()` -- cioe' modellava uno specchio che si
# aggiorna da solo fra la chiamata e la rilettura. In produzione non succede:
# lo specchio lo alimentano gli eventi `state_changed` del websocket, che
# arrivano su un'altra connessione e in un altro Task, e la rilettura sincrona
# subito dopo `await call_service` legge quasi sempre il valore di PRIMA. La
# finta forniva, in un solo punto, l'unica cosa che la produzione non puo'
# dare: la freschezza. Il resto della suite era verde a ragione, perche'
# pinnava un meccanismo che, dato uno specchio fresco, funziona -- e uno
# specchio fresco non esiste. In piu' `FintoClient.call_service` restituiva
# `[]` e nessun test ne guardava il ritorno: la fonte giusta non era rotta,
# era ignorata da entrambe le parti.
#
# **La prova per mutazione.** I test di questa famiglia tengono lo specchio
# FERMO -- il caso reale -- e fanno arrivare il cambiamento da Home Assistant.
# Se qualcuno rimette la rilettura dal solo specchio, cadono: e' l'unica forma
# in cui questo difetto puo' essere sorvegliato, perche' e' un difetto di
# FONTE e non di logica.
#
# I due test qui sotto sono quelli della **2.2.1**, e sorvegliano la fonte
# numero due: cio' che `call_service` riporta. Restano validi -- su un impianto
# che la popola, quella fonte e' la piu' economica -- ma non bastano: la
# famiglia 4, in fondo al file, riproduce la casa in cui quella lista e'
# **vuota**, che e' quella del proprietario.

@pytest.mark.asyncio
async def test_un_comando_riuscito_e_raccontato_come_riuscito_con_lo_specchio_indietro():
    """Gli abat-jour. Lo specchio dice ancora «on» in entrambe le letture;
    Home Assistant dice di averli visti passare a «off» mentre il servizio
    girava. Vince Home Assistant, perche' e' l'unica delle due misure presa
    nel momento giusto -- e infatti non si aspetta niente: un'entita' che la
    chiamata ha gia' riportato non ha piu' nessun annuncio da attendere."""
    client = FintoClient(cambiati=HA_RIPORTA_IL_SALOTTO_SPENTO)
    registro = await _registro_pronto(client)
    specchio_fermo = FintaCache(SALOTTO_ACCESO)  # nessun annuncio: non si muove mai
    porta = ActionActuator(client, registro, specchio_fermo)

    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

    assert esito["eseguito"] is True
    assert esito["cambiato"] == ["light.salotto"], (
        "la luce si e' spenta davvero e HA l'ha riportato: raccontarlo come "
        "«nulla e' cambiato» e' l'esatto opposto dell'invariante di questa "
        "fetta, ed e' il difetto misurato sulla casa vera")
    assert esito["prima"] == {"light.salotto": {"state": "on"}}
    assert esito["dopo"] == {"light.salotto": {"state": "off"}}
    assert "avviso" not in esito, (
        "un comando riuscito non porta avvisi: l'avviso era la meta' della "
        "frase da cui il modello ha tratto la diagnosi inventata")


@pytest.mark.asyncio
async def test_lo_stesso_vale_per_un_attributo_e_prima_e_dopo_restano_ricchi():
    """Il termostato. Stessa causa, altro dominio, altro tipo di dato -- ed e'
    la ragione per cui la correzione e' UNA.

    La seconda meta' del test guarda una cosa che non si vede dal difetto: la
    risposta della casa vera conteneva anche un'osservazione BUONA («in stanza
    ci sono 26.9, quindi resta a riposo»). Il modello la ricava da `prima` e
    `dopo`, quindi il cambio di fonte non deve impoverirli -- e non li
    impoverisce, perche' cio' che arriva da Home Assistant passa per la stessa
    `_to_minimal` dello specchio."""
    client = FintoClient(cambiati=HA_RIPORTA_LA_CAMERA_A_19_5)
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(CAMERA_A_17_5))

    esito = await porta.execute(METTI_LA_CAMERA_A_19_5, actor="chat")

    assert esito["cambiato"] == ["climate.camera"]
    assert esito["prima"]["climate.camera"]["temperature"] == 17.5
    assert esito["dopo"]["climate.camera"]["temperature"] == 19.5
    assert "avviso" not in esito
    # i valori con cui il modello ragiona, da entrambi i lati
    for lato in ("prima", "dopo"):
        voce = esito[lato]["climate.camera"]
        assert voce["current_temperature"] == 26.9, (
            f"`{lato}` ha perso la temperatura ambiente: e' il dato con cui il "
            "modello spiega perche' il riscaldamento resta a riposo")
        assert voce["hvac_action"] == "idle"
    # e la prova che le due fonti sono confrontabili: se lo fossero solo a
    # meta', qui differirebbero anche le chiavi, non solo il valore cambiato
    assert (set(esito["prima"]["climate.camera"])
            == set(esito["dopo"]["climate.camera"])), (
        "lo stato riportato da Home Assistant non passa piu' per `_to_minimal`: "
        "insiemi di chiavi diversi fanno risultare cambiata OGNI entita', che e' "
        "inventare col verso opposto")


@pytest.mark.asyncio
async def test_lo_specchio_resta_il_ripiego_di_cio_di_cui_nessuno_ha_detto_niente():
    """Le fonti nuove non cacciano quella vecchia, e qui si vedono tutte e tre
    in una chiamata sola. Due luci: di una arriva l'annuncio, dell'altra non
    dice niente nessuno -- ne' la chiamata ne' il websocket. La seconda non
    diventa un `None`: lo specchio mostra l'ultimo valore noto, ed e' cio' che
    distingue «non e' ancora cambiato» da «non l'ho visto»."""
    client, cache = _casa({"light.salotto": "on", "light.cucina": "on"},
                          cambiati=[], annuncia=ANNUNCIA_IL_SALOTTO_SPENTO)
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, cache)

    esito = await porta.execute(
        {"servizio": "light.turn_off",
         "bersaglio": {"entita": ["light.salotto", "light.cucina"]}},
        actor="chat")

    assert esito["cambiato"] == ["light.salotto"]
    assert esito["dopo"]["light.cucina"] == {"state": "on"}, (
        "l'entita' di cui nessuno ha detto niente e' finita a `None`: il "
        "ripiego sullo specchio e' sparito, e con lui la distinzione fra "
        "«non e' cambiato» e «non l'ho visto»")
    assert "avviso" not in esito
    assert cache.letture == 2, (
        "lo specchio va letto due volte: prima per verificare, dopo -- e DOPO "
        "l'attesa -- per raccontare l'ultimo valore noto di cio' che nessuno "
        "ha annunciato")


@pytest.mark.asyncio
async def test_l_avviso_di_nessun_cambiamento_non_accusa_il_dispositivo():
    """La seconda meta' del difetto, e quella che ha fatto il danno peggiore:
    «probabile problema di comunicazione col dispositivo» ha mandato il
    proprietario a cercare un guasto che non c'era. L'avviso dev'essere un
    fatto su cio' che Home Assistant ha detto, mai un'ipotesi sulla causa --
    e nemmeno un'affermazione sulla CASA, che HIRIS non e' in grado di fare."""
    client = FintoClient(cambiati=[])
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_SPENTO))

    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

    avviso = esito["avviso"].lower()
    assert "home assistant non ha riportato nessun cambiamento" in avviso, (
        "l'avviso non dice piu' QUAL E' il fatto: senza il soggetto («Home "
        "Assistant»), «nessun cambiamento» torna a suonare come un'affermazione "
        "sulla casa")
    for parola in ("guast", "comunicazione", "non risponde", "offline",
                   "irraggiungibil"):
        assert parola not in avviso, (
            f"l'avviso contiene «{parola}»: e' una diagnosi che HIRIS non ha "
            "modo di fare, ed e' esattamente la frase che sulla casa vera ha "
            "mandato il proprietario a cercare un guasto inesistente")


@pytest.mark.asyncio
async def test_un_dispositivo_lento_resta_un_caso_vero():
    """La tapparella che ci mette venti secondi. La chiamata non riporta
    niente, l'annuncio non arriva entro la scadenza, e lo specchio conferma
    che non e' ancora cambiato niente: l'avviso dice il vero, e non e' un
    guasto.

    **La scadenza non lo trasforma in una diagnosi.** Venti secondi sono molti
    piu' di due, quindi questo caso resta esattamente com'era -- con una
    differenza sola, ed e' tutta a favore di chi legge: adesso l'avviso dice
    che si e' aspettato, e per quanto."""
    client, cache = _casa(SALOTTO_ACCESO, cambiati=[])  # nessun annuncio: non si muove
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, cache)

    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

    assert esito["eseguito"] is True
    assert esito["cambiato"] == []
    assert "ho aspettato" in esito["avviso"]
    assert esito["dopo"] == {"light.salotto": {"state": "on"}}, (
        "lo stato che si e' potuto vedere va mostrato lo stesso: e' cio' che "
        "distingue «non e' ancora cambiato» da «non l'ho visto»")


@pytest.mark.asyncio
async def test_un_cambiamento_che_l_impronta_non_sa_mostrare_non_diventa_nulla_e_cambiato():
    """Il colore di una luce non sta in `_DOMAIN_ATTRS`: HA riporta un
    cambiamento, l'impronta non lo mostra. Prima di questa versione il caso
    finiva nell'avviso «nessuno stato e' cambiato», che qui e' FALSO -- il
    comando ha avuto effetto. `cambiato` resta vuoto (dev'essere sempre
    spiegabile da `prima` e `dopo`), ma l'avviso dice l'altra cosa."""
    client = FintoClient(cambiati=[
        {"entity_id": "light.salotto", "state": "on",
         "attributes": {"rgb_color": [255, 0, 0]}}])
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))

    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

    assert esito["cambiato"] == []
    assert "ha riportato un cambiamento" in esito["avviso"]
    assert "non ha riportato nessun cambiamento" not in esito["avviso"], (
        "Home Assistant HA riportato un cambiamento: dire il contrario e' la "
        "stessa frase falsa detta con sicurezza, in un altro caso")


@pytest.mark.asyncio
async def test_una_voce_riportata_illeggibile_non_rompe_e_non_inventa():
    """La forma della risposta di `call_service` non e' mai stata misurata su
    un impianto vero. Cio' che non si sa leggere si salta -- l'entita' ricade
    sullo specchio -- invece di sollevare o di essere indovinato."""
    client = FintoClient(cambiati=["non un dizionario", {"senza": "entity_id"},
                                   {"entity_id": "light.salotto", "state": "off"}])
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))

    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

    assert esito["eseguito"] is True
    assert esito["cambiato"] == ["light.salotto"]


@pytest.mark.asyncio
async def test_cio_che_nessuna_delle_tre_fonti_vede_resta_dichiarato_sconosciuto():
    """Il terzo esito, e l'unico che non e' un fatto sulla casa: la chiamata
    non ha riportato niente, l'annuncio non e' arrivato entro la scadenza e lo
    specchio non e' rileggibile. `cambiato` non prende
    l'entita' -- contarla direbbe che TUTTO e' cambiato -- e l'avviso dichiara
    di non sapere invece di scegliere una delle due frasi false."""
    client = FintoClient(cambiati=[])
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro,
                        FintaCache(SALOTTO_ACCESO, rompe_dalla_lettura=2))

    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

    assert esito["cambiato"] == []
    assert esito["dopo"] == {"light.salotto": None}
    assert "non so dire cosa sia cambiato" in esito["avviso"].lower()


# --- 4. il fatto vero: la chiamata muta, e l'annuncio che arriva dopo -------
#
# **Il terzo tentativo, e la misura che ha smontato il secondo.** Con
# `log_level: debug` sull'impianto del proprietario, mentre le due abat-jour si
# accendevano davvero:
#
#     call_service: la risposta di Home Assistant e' list, 0 voci utilizzabili,
#     chiavi della prima: None
#     azione eseguita [actor=chat] light.turn_on su [...]
#     -- cambiati: nessuno (Home Assistant ne ha riportati 0)
#
# La fonte che la 2.2.1 aveva eletto -- il ritorno di `call_service` -- su
# quella casa **non porta niente**, e il ripiego sullo specchio riportava al
# difetto di partenza. Al ritorno della chiamata non esiste nessuna fonte che
# sappia gia' com'e' andata: bisogna aspettare l'annuncio.
#
# **Cosa nessuna finta faceva, e perche' conta.** La vecchia `FintaCache`
# regalava la freschezza aggiornandosi da se' alla seconda lettura. Le finte di
# adesso mentono come mente la realta': `cambiati=[]`, e lo specchio si muove
# **solo** quando arriva l'annuncio, **dopo** il ritorno della chiamata. Da qui
# la prova per mutazione: se si rimette la lettura immediata senza attesa, il
# primo test di questa famiglia cade -- e cade con lo stesso identico sintomo
# che il proprietario ha visto in chat.

ABAT_JOUR = ["light.abat_jour_sinistra_abat_jour_sinistra",
             "light.abat_jour_destra_abat_jour_destra"]
ABAT_JOUR_SPENTE = {eid: "off" for eid in ABAT_JOUR}
ACCENDI_LE_ABAT_JOUR = {"servizio": "light.turn_on",
                        "bersaglio": {"entita": list(ABAT_JOUR)}}
# `friendly_name` vuoto non e' una svista: e' cio' che quella casa ha davvero
# nel registro, ed e' il motivo per cui il modello ha dovuto trovarle con
# `guarda` dopo quattro `cerca` a vuoto. Qui non cambia l'esito -- la porta
# lavora sugli id -- e resta scritto perche' la finta descriva quella casa.
ANNUNCIA_LE_ABAT_JOUR_ACCESE = [
    {"entity_id": eid, "state": "on",
     "attributes": {"friendly_name": "", "brightness": 255,
                    "supported_color_modes": ["hs"]}}
    for eid in ABAT_JOUR
]


@pytest.mark.asyncio
async def test_le_luci_si_accendono_e_hiris_lo_racconta_anche_se_la_chiamata_tace():
    """**La prova per mutazione di questa versione.**

    Riproduce l'impianto del proprietario: `call_service` restituisce `[]`, e
    lo specchio si aggiorna solo quando l'annuncio arriva -- dopo. Chi
    rimettesse la lettura immediata leggerebbe `off` da uno specchio ancora
    indietro e racconterebbe «non e' cambiato niente» di due luci accese.
    """
    client, cache = _casa(ABAT_JOUR_SPENTE,
                          cambiati=[],  # la lista vuota misurata dal vivo
                          annuncia=ANNUNCIA_LE_ABAT_JOUR_ACCESE,
                          ritardo=0.02)  # l'annuncio arriva DOPO la chiamata
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, cache)

    esito = await porta.execute(ACCENDI_LE_ABAT_JOUR, actor="chat")

    assert client.specchio_al_ritorno == {eid: "off" for eid in ABAT_JOUR}, (
        "la finta sta regalando la freschezza: al ritorno di `call_service` lo "
        "specchio mostra gia' lo stato nuovo, che e' l'unica cosa che la "
        "produzione non puo' fare -- ed e' il motivo per cui 1207 test "
        "passavano su un prodotto rotto")
    assert esito["eseguito"] is True
    assert esito["cambiato"] == ABAT_JOUR, (
        "le luci si sono accese davvero e Home Assistant l'ha annunciato: "
        "raccontarlo come «non e' cambiato niente» e' il difetto che il "
        "proprietario ha visto tre volte")
    assert esito["prima"] == {eid: {"state": "off"} for eid in ABAT_JOUR}
    assert esito["dopo"] == {eid: {"state": "on", "brightness": 255}
                             for eid in ABAT_JOUR}
    assert "avviso" not in esito, (
        "un comando riuscito non porta avvisi: l'avviso era la meta' della "
        "frase da cui il modello ha tratto la diagnosi inventata")


@pytest.mark.asyncio
async def test_un_annuncio_arrivato_durante_la_chiamata_non_si_perde():
    """La casa veloce, ed e' il caso che rende necessario aprire l'ascolto
    PRIMA di chiamare.

    Qui l'annuncio arriva mentre `call_service` e' ancora sospesa. Un
    ascoltatore aperto dopo il ritorno non lo avrebbe mai sentito, e l'attesa
    sarebbe scaduta a vuoto: lo stesso difetto di prima, in una forma piu'
    rara e molto piu' difficile da vedere. Il controllo che `attendi` fa prima
    di mettersi ad aspettare e' cio' che lo chiude.
    """
    client, cache = _casa(SALOTTO_ACCESO, cambiati=[],
                          annuncia=ANNUNCIA_IL_SALOTTO_SPENTO,
                          ritardo=None)  # DENTRO la chiamata
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, cache)

    inizio = time.monotonic()
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    durata = time.monotonic() - inizio

    assert esito["cambiato"] == ["light.salotto"]
    assert esito["dopo"] == {"light.salotto": {"state": "off"}}
    assert "avviso" not in esito
    assert durata < porta_modulo.STATE_WAIT_S, (
        "l'annuncio era gia' arrivato e la porta ha aspettato lo stesso fino "
        "alla scadenza: la scadenza sta diventando un tempo di attesa invece "
        "che un limite, ed e' precisamente la `sleep` che questo modulo vieta")


@pytest.mark.asyncio
async def test_se_l_annuncio_non_arriva_entro_la_scadenza_l_avviso_lo_dichiara():
    """L'altra meta' obbligatoria dell'attesa: cosa si dice quando non arriva.

    L'avviso deve dire **che si e' aspettato e per quanto** -- e' il fatto che
    HIRIS ha in mano -- e non deve ipotizzare niente sul dispositivo. Il test
    misura anche che l'attesa ci sia stata davvero: un avviso che dichiara
    un'attesa mai fatta sarebbe la stessa frase falsa detta con sicurezza, in
    una forma nuova.
    """
    client, cache = _casa(SALOTTO_ACCESO, cambiati=[])  # nessuno annuncia niente
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, cache)

    inizio = time.monotonic()
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    durata = time.monotonic() - inizio

    assert esito["eseguito"] is True
    assert esito["cambiato"] == []
    avviso = esito["avviso"]
    assert "ho aspettato" in avviso, (
        "l'avviso non dice piu' che si e' aspettato: torna a essere «non ho "
        "visto niente», che e' meno di cio' che la porta ha fatto")
    assert f"{porta_modulo.STATE_WAIT_S:g} secondi" in avviso, (
        "l'avviso non nomina la scadenza in vigore: o e' scritta a mano, e "
        "domani sara' falsa, oppure la porta non aspetta piu' quanto dice")
    # margine sul cronometro, non sulla regola: `wait_for` non torna prima
    # della scadenza, ma l'orologio di una macchina carica non e' un cronometro
    assert durata >= porta_modulo.STATE_WAIT_S * 0.9, (
        "l'avviso dichiara un'attesa che non c'e' stata: e' una frase falsa "
        "detta con sicurezza, che e' esattamente cio' che questo modulo esiste "
        "per non fare")
    for parola in ("guast", "comunicazione", "non risponde", "offline",
                   "irraggiungibil"):
        assert parola not in avviso.lower(), (
            f"l'avviso contiene «{parola}»: la scadenza scaduta non autorizza "
            "nessuna diagnosi del dispositivo -- e' un fatto su cio' che Home "
            "Assistant ha detto entro quel tempo, e nient'altro")


@pytest.mark.asyncio
async def test_gli_annunci_delle_altre_entita_non_svegliano_l_attesa():
    """Una casa vera annuncia decine di cambiamenti che non c'entrano niente
    col comando appena dato. Se uno di quelli chiudesse l'attesa, la porta
    smetterebbe di guardare troppo presto -- e se finisse nel «dopo»
    racconterebbe come effetto del comando qualcosa che il comando non ha
    fatto: la stessa invenzione di prima, col verso opposto."""
    annuncio_di_un_altra = [{"entity_id": "light.cucina", "state": "off",
                             "attributes": {"friendly_name": "Cucina"}}]
    client, cache = _casa({"light.salotto": "on", "light.cucina": "on"},
                          cambiati=[], annuncia=annuncio_di_un_altra)
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, cache)

    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

    assert esito["entita"] == ["light.salotto"]
    assert esito["cambiato"] == [], (
        "l'annuncio di un'altra entita' e' finito nell'esito del comando")
    assert "ho aspettato" in esito["avviso"]


@pytest.mark.asyncio
async def test_l_ascoltatore_effimero_si_toglie_sempre():
    """Un ascoltatore per comando, lasciato li', sarebbe una perdita
    silenziosa: la lista cresce a ogni azione e ogni evento della casa la
    percorre tutta. Vale anche -- soprattutto -- quando la chiamata fallisce,
    che e' il ramo in cui ci si dimentica."""
    client, cache = _casa(SALOTTO_ACCESO, annuncia=ANNUNCIA_IL_SALOTTO_SPENTO)
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, cache)

    await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert client.ascoltatori == [], "ascoltatore rimasto dopo un comando riuscito"

    class ClientCheRompe(FintoClient):
        async def call_service(self, domain, service, data):
            raise RuntimeError("HTTP 500")

    client_rotto = ClientCheRompe()
    registro_rotto = await _registro_pronto(client_rotto)
    porta_rotta = ActionActuator(client_rotto, registro_rotto,
                              FintaCache(SALOTTO_ACCESO))
    esito = await porta_rotta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    assert esito["eseguito"] is False
    assert client_rotto.ascoltatori == [], (
        "ascoltatore rimasto dopo una chiamata fallita: e' il ramo in cui una "
        "perdita non si vede mai")


@pytest.mark.asyncio
async def test_un_client_che_non_annuncia_non_blocca_e_non_rifiuta():
    """Se un giorno la porta venisse cablata su un client senza il rubinetto
    degli annunci, l'esito varrebbe meno -- ma il comando resta legittimo, e
    non si aspetta un annuncio che non puo' arrivare. Rifiutarlo sarebbe
    negare una cosa che si sa fare; aspettarlo sarebbe la `sleep` vietata."""
    class ClientSordo(FintoClient):
        add_state_listener = None
        remove_state_listener = None

    client = ClientSordo(cambiati=HA_RIPORTA_IL_SALOTTO_SPENTO)
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))

    inizio = time.monotonic()
    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")
    durata = time.monotonic() - inizio

    assert esito["eseguito"] is True
    assert esito["cambiato"] == ["light.salotto"]
    assert durata < porta_modulo.STATE_WAIT_S


# --- la cronaca --------------------------------------------------------------
#
# Task 3 dello schedulatore: la fetta «comandare» aveva promesso «il registro
# di cio' che e' stato fatto» e non l'aveva costruito. `_porta_di_prova` e' il
# costruttore condiviso di questi due test -- non se ne inventa un secondo
# accanto a `_porta_pronta`, che serve alla famiglia 4 e porta gia' il suo
# `client`/`cache` per test che li ispezionano.

async def _porta_di_prova(*, cronaca=None) -> ActionActuator:
    """Una porta pronta a eseguire `light.turn_on` su `light.studio`, con o
    senza cronaca: la cronaca e' facoltativa, e questo costruttore la passa
    solo se chi chiama la vuole."""
    client, cache = _casa({"light.studio": "off"}, annuncia=[
        {"entity_id": "light.studio", "state": "on", "attributes": {}}])
    registro = await _registro_pronto(client)
    return ActionActuator(client, registro, cache, journal=cronaca)


@pytest.mark.asyncio
async def test_la_porta_registra_in_cronaca_e_restituisce_l_identificatore(tmp_path):
    """L'esito riuscito deve poter essere CHIESTO, non solo loggato (fondamenta n.4)."""
    import os

    from hiris.app.action.journal import Journal

    cronaca = Journal(os.path.join(str(tmp_path), "azioni.db"))
    try:
        porta = await _porta_di_prova(cronaca=cronaca)
        esito = await porta.execute(
            {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.studio"]}},
            actor="chat")
        assert esito["eseguito"] is True
        assert cronaca.read(esito["esecuzione_id"])["origine"] == "chat"
    finally:
        cronaca.close()


@pytest.mark.asyncio
async def test_senza_cronaca_la_porta_si_comporta_come_prima():
    """La cronaca e' facoltativa: nessun chiamante esistente cambia comportamento."""
    porta = await _porta_di_prova(cronaca=None)
    esito = await porta.execute(
        {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.studio"]}},
        actor="chat")
    assert esito["eseguito"] is True
    assert "esecuzione_id" not in esito


@pytest.mark.asyncio
async def test_un_fallimento_di_home_assistant_scrive_comunque_in_cronaca(tmp_path):
    """Il ramo `executed=False` CON cronaca presente, mai esercitato prima
    della review finale (rilievo minore): la chiamata SUPERA la verifica ma
    Home Assistant la rifiuta -- e' un tentativo che e' successo, non un
    errore del modello, quindi deve finire in cronaca (a differenza del
    rifiuto della verifica, provato subito sotto)."""
    import os

    from hiris.app.action.journal import Journal

    class ClientCheRompe(FintoClient):
        async def call_service(self, domain, service, data):
            raise RuntimeError("HTTP 500")

    cronaca = Journal(os.path.join(str(tmp_path), "azioni.db"))
    try:
        client = ClientCheRompe()
        registro = await _registro_pronto(client)
        porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO),
                            journal=cronaca)

        esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

        assert esito["eseguito"] is False
        assert "esecuzione_id" in esito
        riga = cronaca.read(esito["esecuzione_id"])
        assert riga["eseguito"] is False
        assert "HTTP 500" in riga["errore"]
        assert riga["entita"] == ["light.salotto"]
    finally:
        cronaca.close()


@pytest.mark.asyncio
async def test_un_rifiuto_della_verifica_non_finisce_in_cronaca(tmp_path):
    """L'invariante che la spec di `journal.py` dichiara con piu' enfasi: si
    registrano i tentativi che hanno SUPERATO la verifica, riusciti o
    falliti. Un rifiuto della verifica non e' un'esecuzione -- e' un errore
    del modello, gia' detto al modello -- e non deve mai riempire il
    registro di cose che non sono successe.

    `Journal` non ha un elenco (`list()` e' uscita, review indipendente
    punto ④: zero chiamanti di produzione): qui si guarda direttamente la
    tabella con una seconda connessione allo stesso file, che e' cio' che un
    test puo' fare senza chiedere alla classe una capacita' che nessuno usa.
    """
    import os
    import sqlite3

    from hiris.app.action.journal import Journal

    db_path = os.path.join(str(tmp_path), "azioni.db")
    cronaca = Journal(db_path)
    try:
        porta = await _porta_di_prova(cronaca=cronaca)
        esito = await porta.execute(
            {"servizio": "light.esplodi", "bersaglio": {"entita": ["light.studio"]}},
            actor="chat")
        assert esito["eseguito"] is False
        assert "esecuzione_id" not in esito

        ispezione = sqlite3.connect(db_path)
        try:
            conteggio = ispezione.execute(
                "SELECT count(*) FROM esecuzioni").fetchone()[0]
        finally:
            ispezione.close()
        assert conteggio == 0, (
            "un rifiuto della verifica ha scritto una riga in cronaca: sta "
            "registrando cose che non sono successe")
    finally:
        cronaca.close()


def test_la_scadenza_e_dichiarata_finita_e_una_sola():
    """La scadenza vera, quella che gira in casa d'altri.

    I test di questo file la accorciano apposta (vedi `SCADENZA_NEI_TEST`):
    senza questa guardia nessuno guarderebbe piu' il valore di produzione, e
    una scadenza cresciuta a venti secondi -- o azzerata, che rimetterebbe il
    difetto -- passerebbe con la suite verde.
    """
    import inspect

    from hiris.app.action import actuator as modulo_vero

    sorgente = inspect.getsource(modulo_vero)
    assert "STATE_WAIT_S = 2.0" in sorgente, (
        "la scadenza di produzione non e' piu' 2.0 secondi: se e' una "
        "decisione, va cambiata qui insieme al perche' scritto accanto alla "
        "costante")
    assert sorgente.count("STATE_WAIT_S = ") == 1, (
        "la scadenza e' nominata in piu' di un posto: due valori che devono "
        "restare allineati sono un difetto, non una configurazione")
    # e non e' infinita: un'attesa senza scadenza sarebbe una chat appesa
    assert 0 < modulo_vero.STATE_WAIT_S <= 5


# --- 5. i servizi senza bersaglio --------------------------------------------
#
# Review finale, rilievo CRITICO ①. `verifica()` accetta ora un bersaglio
# vuoto per un servizio che non dichiara un `target` (`notify.*`,
# `Verdict.no_target`): questa famiglia prova che la PORTA tratta quel
# verdetto con la stessa onesta' di ogni altro -- niente `entity_id`
# iniettato (sarebbe una cosa diversa da «nessun bersaglio»), niente ascolto
# aperto ne' attesa pagata su zero entita', e un esito che dice solo cio' che
# e' vero: la chiamata e' partita, e non c'era nessuno stato da rileggere.
#
# E' anche la giuntura che la review finale ha trovato rotta: prima di questo
# fix, `verifica()` rifiutava QUALUNQUE bersaglio vuoto -- incondizionatamente
# -- e la promessa che `keeper/sweeper.py::_keep_chiedi` costruisce
# per notificare (`"bersaglio": {}`) non passava mai di qui.

NOTIFICA_HIRIS = {"servizio": "notify.mobile_app_x", "bersaglio": {},
                  "dati": {"message": "ciao", "title": "HIRIS"}}


class ClientCheRegistraGliAscoltatori(FintoClient):
    """Fotografa `self.ascoltatori` nell'ISTANTE in cui `call_service` gira --
    prima che `_close_listen` (nel `finally` della porta) possa svuotarli.
    E' l'unico modo per provare che un ascolto NON e' stato aperto: guardare
    `client.ascoltatori` DOPO `esegui()` sarebbe vuoto comunque, aperto o no,
    perche' la porta lo chiude sempre prima di tornare."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ascoltatori_durante_la_chiamata: list | None = None

    async def call_service(self, domain, service, data):
        self.ascoltatori_durante_la_chiamata = list(self.ascoltatori)
        return await super().call_service(domain, service, data)


@pytest.mark.asyncio
async def test_una_notifica_non_inietta_entity_id():
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))

    esito = await porta.execute(NOTIFICA_HIRIS, actor="schedulatore")

    assert esito["eseguito"] is True
    assert client.chiamate == [
        ("notify", "mobile_app_x", {"message": "ciao", "title": "HIRIS"})], (
        "`entity_id` non deve comparire: iniettare `entity_id: []` direbbe "
        "una cosa diversa da «nessun bersaglio», e questo servizio non ne ha "
        "uno")


@pytest.mark.asyncio
async def test_una_notifica_non_apre_un_ascolto():
    client = ClientCheRegistraGliAscoltatori()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))

    await porta.execute(NOTIFICA_HIRIS, actor="schedulatore")

    assert client.ascoltatori_durante_la_chiamata == [], (
        "l'ascolto si apre PRIMA della chiamata (vedi il docstring del "
        "modulo): se qualcuno lo riaprisse anche per zero entita', lo si "
        "vedrebbe qui -- guardare `client.ascoltatori` DOPO `esegui()` non "
        "basterebbe, perche' la porta lo chiude sempre prima di tornare")


@pytest.mark.asyncio
async def test_l_esito_di_una_notifica_e_onesto_non_una_misura_inventata():
    """Il punto piu' delicato del rilievo: per un servizio senza bersaglio
    NON c'e' nessuno stato da rileggere, e l'esito non deve fingere di
    averlo guardato."""
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))

    esito = await porta.execute(NOTIFICA_HIRIS, actor="schedulatore")

    assert esito["entita"] == []
    assert esito["prima"] == {}
    assert esito["dopo"] == {}
    assert esito["cambiato"] == []
    avviso = esito["avviso"].lower()
    assert "non c'era nessuno stato da rileggere" in avviso
    for parola in ("ho aspettato", "secondi", "cambiamento"):
        assert parola not in avviso, (
            f"l'avviso contiene «{parola}»: e' il linguaggio di un'attesa "
            "mai fatta, cioe' una misura inventata su uno stato che non si "
            "e' mai potuto guardare")


@pytest.mark.asyncio
async def test_una_notifica_fallita_e_un_errore_leggibile():
    class ClientCheRompe(FintoClient):
        async def call_service(self, domain, service, data):
            raise RuntimeError("il servizio di notifica non risponde")

    client = ClientCheRompe()
    registro = await _registro_pronto(client)
    porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO))

    esito = await porta.execute(NOTIFICA_HIRIS, actor="schedulatore")

    assert esito["eseguito"] is False
    assert "non risponde" in esito["errore"]


@pytest.mark.asyncio
async def test_una_notifica_riuscita_finisce_in_cronaca_con_entita_vuote(tmp_path):
    """Anche una notifica e' un'esecuzione (spec §8, «uniforme»): deve poter
    essere CHIESTA come ogni altra, con `entita` onestamente vuote."""
    import os

    from hiris.app.action.journal import Journal

    cronaca = Journal(os.path.join(str(tmp_path), "azioni.db"))
    try:
        client = FintoClient()
        registro = await _registro_pronto(client)
        porta = ActionActuator(client, registro, FintaCache(SALOTTO_ACCESO),
                            journal=cronaca)

        esito = await porta.execute(NOTIFICA_HIRIS, actor="schedulatore")

        assert esito["eseguito"] is True
        riga = cronaca.read(esito["esecuzione_id"])
        assert riga["servizio"] == "notify.mobile_app_x"
        assert riga["entita"] == []
        assert riga["eseguito"] is True
    finally:
        cronaca.close()


@pytest.mark.asyncio
async def test_il_bersaglio_dichiara_un_target_ancora_richiesto():
    """Il rovescio: `light.turn_off` DICHIARA un `target` (vedi
    `RISPOSTA_HA`), quindi il rifiuto di sempre resta -- questo test cade se
    la review finale avesse allargato il bypass oltre i servizi che non
    hanno davvero un bersaglio."""
    porta, client, _ = await _porta_pronta()
    esito = await porta.execute(
        {"servizio": "light.turn_off"}, actor="chat")
    assert esito["eseguito"] is False
    assert "serve un bersaglio" in esito["errore"]
    assert client.chiamate == []
