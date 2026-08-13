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

**Nota sulla finta cache.** Il brief ipotizzava `cache.snapshot()`. Non
esiste: `EntityCache` (`hiris/app/proxy/entity_cache.py`) espone
`all_states()`, che restituisce una **lista** di dizionari minimali con
chiave `id` (non `entity_id`) — la stessa forma che
`DispatcherStrumenti._stato_vivo` legge gia'. La finta e' stata adattata al
metodo vero; il codice di produzione non e' stato piegato al test.
Espone anche `loaded`, la bandiera che distingue «casa senza entita'» da
«inventario non ancora pronto».

Come in `tests/test_azione_verifica.py`: niente fixture asincrone — la suite
gira in modalita' `strict` di pytest-asyncio, quindi ogni test async porta il
suo `@pytest.mark.asyncio` e la preparazione sta in un helper `await`ato.
"""
import pytest

from hiris.app.azione.porta import PortaAzione
from hiris.app.azione.registro import RegistroServizi

RISPOSTA_HA = [
    {"domain": "light", "services": {"turn_off": {"fields": {"transition": {}}}}},
    # un servizio parametrico vero, per il confronto che guarda gli attributi
    {"domain": "climate", "services": {"set_temperature": {"fields": {"temperature": {}}}}},
]


class FintoClient:
    """Home Assistant visto dalla porta.

    `cambiati` e' cio' che `call_service` restituisce: **gli stati completi**
    (`entity_id`, `state`, `attributes`) che HA dichiara cambiati durante
    l'esecuzione del servizio. Fino alla 2.2.0 questa finta restituiva sempre
    `[]` e nessun test ne guardava il ritorno, perche' la porta lo buttava --
    ed e' esattamente li' che il difetto della 2.2.0 e' passato (vedi il
    commento sopra la famiglia 3 in fondo al file).
    """

    def __init__(self, cambiati=None):
        self.chiamate = []
        self._cambiati = cambiati if cambiati is not None else []

    async def get_services(self):
        return RISPOSTA_HA

    async def call_service(self, dominio, servizio, dati):
        self.chiamate.append((dominio, servizio, dati))
        return list(self._cambiati)


class FintaCache:
    """Lo specchio dello stato vivo, con uno stato che cambia dopo la chiamata.

    Imita `EntityCache`: `all_states()` restituisce una lista di dizionari
    minimali (`id`, `state`, ...), e `loaded` dice se la prima lettura da Home
    Assistant e' mai arrivata in fondo.

    **Attenzione a `dopo`.** Uno specchio che alla seconda lettura mostra gia'
    lo stato nuovo e' cio' che la produzione NON fa: lo alimentano gli eventi
    `state_changed` del websocket, che arrivano dopo. `dopo=None` -- lo
    specchio che resta fermo -- e' quindi il caso REALE, ed e' quello che i
    test della famiglia 3 usano.
    """

    def __init__(self, stati, dopo=None, loaded=True, rompe_dalla_lettura=None):
        self._stati = dict(stati)
        self._dopo = dopo
        self.loaded = loaded
        self._rompe_dalla_lettura = rompe_dalla_lettura
        self.letture = 0

    def all_states(self):
        self.letture += 1
        if (self._rompe_dalla_lettura is not None
                and self.letture >= self._rompe_dalla_lettura):
            raise RuntimeError("websocket caduto")
        sorgente = self._dopo if (self.letture > 1 and self._dopo is not None) else self._stati
        return [_voce(eid, valore) for eid, valore in sorgente.items()]


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


SALOTTO_ACCESO = {"light.salotto": "on"}
SALOTTO_SPENTO = {"light.salotto": "off"}

SPEGNI_IL_SALOTTO = {"servizio": "light.turn_off",
                     "bersaglio": {"entita": ["light.salotto"]}}

# Il comando parametrico: `state` resta «heat», cambia solo la temperatura.
CLIMA_A_19 = {"climate.salotto": {"state": "heat", "attributes": {"temperature": 19}}}
CLIMA_A_21 = {"climate.salotto": {"state": "heat", "attributes": {"temperature": 21}}}
METTI_A_21 = {"servizio": "climate.set_temperature",
              "bersaglio": {"entita": ["climate.salotto"]},
              "dati": {"temperature": 21}}

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
    registro = RegistroServizi()
    await registro.aggiorna(client)
    return registro


async def _porta_pronta():
    client = FintoClient()
    registro = await _registro_pronto(client)
    cache = FintaCache(SALOTTO_ACCESO, dopo=SALOTTO_SPENTO)
    return PortaAzione(client, registro, cache), client, cache


# --- la sequenza ------------------------------------------------------------

@pytest.mark.asyncio
async def test_esegue_e_racconta_cosa_e_cambiato():
    porta, client, cache = await _porta_pronta()
    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")
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
    esito = await porta.esegui(
        {"servizio": "light.esplodi", "bersaglio": {"entita": ["light.salotto"]}},
        origine="chat")
    assert esito["eseguito"] is False
    assert "non esiste" in esito["errore"]
    assert client.chiamate == [], (
        "una chiamata rifiutata NON deve arrivare a Home Assistant")


@pytest.mark.asyncio
async def test_se_nulla_cambia_lo_dichiara():
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = PortaAzione(client, registro, FintaCache(SALOTTO_ACCESO))  # non cambia
    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")
    assert esito["eseguito"] is True
    assert esito["cambiato"] == []
    assert "avviso" in esito, (
        "una chiamata che non cambia niente non deve passare per un successo muto")


@pytest.mark.asyncio
async def test_i_parametri_della_chiamata_arrivano_a_home_assistant():
    """`dati` non e' decorazione: senza, «spegni fra 5 secondi» diventa «spegni»."""
    porta, client, _ = await _porta_pronta()
    esito = await porta.esegui(dict(SPEGNI_IL_SALOTTO, dati={"transition": 5}),
                               origine="chat")
    assert esito["eseguito"] is True
    assert client.chiamate == [
        ("light", "turn_off", {"transition": 5, "entity_id": ["light.salotto"]})]


@pytest.mark.asyncio
async def test_un_guasto_di_home_assistant_diventa_un_errore_leggibile():
    class ClientCheRompe(FintoClient):
        async def call_service(self, dominio, servizio, dati):
            raise RuntimeError("HTTP 500")

    client = ClientCheRompe()
    registro = await _registro_pronto(client)
    porta = PortaAzione(client, registro, FintaCache(SALOTTO_ACCESO))
    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")
    assert esito["eseguito"] is False
    assert "HTTP 500" in esito["errore"]


@pytest.mark.asyncio
async def test_un_registro_illeggibile_diventa_un_errore_leggibile():
    """`assicura_fresco` solleva al primissimo caricamento (contratto del Task 1)."""
    class ClientSenzaServizi(FintoClient):
        async def get_services(self):
            raise RuntimeError("connessione rifiutata")

    client = ClientSenzaServizi()
    porta = PortaAzione(client, RegistroServizi(), FintaCache(SALOTTO_ACCESO))
    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")
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
        esiti.append(await porta.esegui(SPEGNI_IL_SALOTTO, origine=origine))
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
    assert registro.domini() == [], "premessa: il registro e' davvero vuoto"
    porta = PortaAzione(client, registro, FintaCache(SALOTTO_ACCESO))
    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")
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
    porta = PortaAzione(client, registro, FintaCache({}))
    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")
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
    porta = PortaAzione(client, registro,
                        FintaCache({"light.cucina": "on"}, loaded=False))
    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")
    assert esito["eseguito"] is False
    assert "non esiste in questa casa" not in esito["errore"]
    assert "non vedo" in esito["errore"]
    assert client.chiamate == []


@pytest.mark.asyncio
async def test_senza_specchio_del_tutto_non_nega_un_entita_che_esiste():
    """Terza forma dello stesso buco: la cache non e' proprio cablata."""
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = PortaAzione(client, registro, None)
    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")
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
    porta = PortaAzione(client, registro, cache)
    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")
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
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = PortaAzione(client, registro, FintaCache(CLIMA_A_19, dopo=CLIMA_A_21))
    esito = await porta.esegui(METTI_A_21, origine="chat")
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
    client = FintoClient()
    registro = await _registro_pronto(client)
    porta = PortaAzione(client, registro, FintaCache(CLIMA_A_19, dopo=CLIMA_A_21))
    esito = await porta.esegui(METTI_A_21, origine="chat")
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
    porta = PortaAzione(client, registro, FintaCache(CLIMA_A_21))
    esito = await porta.esegui(METTI_A_21, origine="chat")
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
    from hiris.app.azione.porta import _impronta
    from hiris.app.proxy.entity_cache import _to_minimal

    voce = _to_minimal({"entity_id": "climate.salotto", "state": "heat",
                        "attributes": {"temperature": 21, "friendly_name": "Salotto"}})
    assert _impronta(voce) == {"state": "heat", "temperature": 21}, (
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
# la finta lo NEGAVA. `FintaCache(..., dopo=...)` mostra lo stato nuovo alla
# seconda `all_states()` -- cioe' modella uno specchio che si aggiorna da solo
# fra la chiamata e la rilettura. In produzione non succede: lo specchio lo
# alimentano gli eventi `state_changed` del websocket, che arrivano su
# un'altra connessione e in un altro Task, e la rilettura sincrona subito dopo
# `await call_service` legge quasi sempre il valore di PRIMA. La finta
# forniva, e in un solo punto, l'unica cosa che la produzione non puo' dare:
# la freschezza. Il resto della suite era verde a ragione, perche' pinnava un
# meccanismo che, dato uno specchio fresco, funziona -- e uno specchio fresco
# non esiste. In piu' `FintoClient.call_service` restituiva `[]` e nessun test
# ne guardava il ritorno: la fonte giusta non era rotta, era ignorata da
# entrambe le parti.
#
# **La prova per mutazione.** I due test qui sotto tengono lo specchio FERMO
# (`dopo=None`, il caso reale) e fanno riportare il cambiamento a Home
# Assistant. Se qualcuno rimette la rilettura dal solo specchio, cadono
# entrambi -- ed e' l'unica forma in cui questo difetto puo' essere sorvegliato
# da un test, perche' e' un difetto di FONTE e non di logica.

@pytest.mark.asyncio
async def test_un_comando_riuscito_e_raccontato_come_riuscito_con_lo_specchio_indietro():
    """Gli abat-jour. Lo specchio dice ancora «on» in entrambe le letture;
    Home Assistant dice di averli visti passare a «off» mentre il servizio
    girava. Vince Home Assistant, perche' e' l'unica delle due misure presa
    nel momento giusto."""
    client = FintoClient(cambiati=HA_RIPORTA_IL_SALOTTO_SPENTO)
    registro = await _registro_pronto(client)
    specchio_fermo = FintaCache(SALOTTO_ACCESO)  # dopo=None: non si aggiorna mai
    porta = PortaAzione(client, registro, specchio_fermo)

    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")

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
    porta = PortaAzione(client, registro, FintaCache(CAMERA_A_17_5))

    esito = await porta.esegui(METTI_LA_CAMERA_A_19_5, origine="chat")

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
async def test_lo_specchio_resta_il_ripiego_di_cio_che_home_assistant_non_riporta():
    """La fonte nuova non caccia quella vecchia. Se HA non riporta niente --
    un servizio che non cambia stato, o un impianto che risponde con una lista
    vuota -- lo specchio e' cio' che resta, ed e' cio' che distingue «non e'
    cambiato» da «non l'ho visto»."""
    client = FintoClient(cambiati=[])
    registro = await _registro_pronto(client)
    cache = FintaCache(SALOTTO_ACCESO, dopo=SALOTTO_SPENTO)
    porta = PortaAzione(client, registro, cache)

    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")

    assert esito["cambiato"] == ["light.salotto"]
    assert cache.letture == 2, (
        "lo specchio non va piu' letto due volte: il ripiego e' sparito e con "
        "lui la distinzione fra «non e' cambiato» e «non l'ho visto»")


@pytest.mark.asyncio
async def test_l_avviso_di_nessun_cambiamento_non_accusa_il_dispositivo():
    """La seconda meta' del difetto, e quella che ha fatto il danno peggiore:
    «probabile problema di comunicazione col dispositivo» ha mandato il
    proprietario a cercare un guasto che non c'era. L'avviso dev'essere un
    fatto su cio' che Home Assistant ha detto, mai un'ipotesi sulla causa --
    e nemmeno un'affermazione sulla CASA, che HIRIS non e' in grado di fare."""
    client = FintoClient(cambiati=[])
    registro = await _registro_pronto(client)
    porta = PortaAzione(client, registro, FintaCache(SALOTTO_SPENTO))

    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")

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
    """La tapparella che ci mette venti secondi. Home Assistant non riporta
    niente perche' NON e' ancora cambiato niente, e lo specchio conferma:
    l'avviso dice il vero, e non e' un guasto. Nessuna attesa arbitraria --
    e' un problema di fonte, e la fonte adesso e' quella giusta."""
    client = FintoClient(cambiati=[])
    registro = await _registro_pronto(client)
    porta = PortaAzione(client, registro, FintaCache(SALOTTO_ACCESO))

    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")

    assert esito["eseguito"] is True
    assert esito["cambiato"] == []
    assert "avviso" in esito
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
    porta = PortaAzione(client, registro, FintaCache(SALOTTO_ACCESO))

    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")

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
    porta = PortaAzione(client, registro, FintaCache(SALOTTO_ACCESO))

    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")

    assert esito["eseguito"] is True
    assert esito["cambiato"] == ["light.salotto"]


@pytest.mark.asyncio
async def test_cio_che_nessuna_delle_due_fonti_vede_resta_dichiarato_sconosciuto():
    """Il terzo esito, e l'unico che non e' un fatto sulla casa: HA non ha
    riportato niente e lo specchio non e' rileggibile. `cambiato` non prende
    l'entita' -- contarla direbbe che TUTTO e' cambiato -- e l'avviso dichiara
    di non sapere invece di scegliere una delle due frasi false."""
    client = FintoClient(cambiati=[])
    registro = await _registro_pronto(client)
    porta = PortaAzione(client, registro,
                        FintaCache(SALOTTO_ACCESO, rompe_dalla_lettura=2))

    esito = await porta.esegui(SPEGNI_IL_SALOTTO, origine="chat")

    assert esito["cambiato"] == []
    assert esito["dopo"] == {"light.salotto": None}
    assert "non so dire cosa sia cambiato" in esito["avviso"].lower()
