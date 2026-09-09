"""Il vocabolario che Home Assistant DOCUMENTA e non manda mai in un payload.

Un'entita' arriva con `device_class: "energy"` o `state_class:
"total_increasing"`: sono STRINGHE, non spiegazioni. Il significato -- che un
`total_increasing` puo' azzerarsi a un nuovo ciclo del contatore invece di
essere un guasto, che un pulsante `identify` fa segnalare il dispositivo, che
`unavailable` e `unknown` sono due fatti diversi -- vive solo nella
documentazione di Home Assistant e nel sorgente che la implementa, mai nella
risposta che il fornitore manda. Questo modulo lo IMPORTA, con la stessa
disciplina con cui `type_vocabulary.py` importa i nomi dei bit di
`supported_features`: "copiato dalla fonte, pinnato da una prova che si accorge
quando diverge", non una seconda forma inventata accanto.

**Non e' un elenco esaustivo di cio' che Home Assistant conosce.** E' il
PERIMETRO che QUESTA casa usa davvero, misurato su
`http://192.168.1.95:8123/api/states` il 07/09/2026: 835 entita' totali, 201
con `device_class`, 130 con `state_class` (gli stessi ordini di grandezza gia'
misurati il 06/09/2026 e riportati nel capitolato: 834/201/130 -- la
differenza di un'entita' sul totale e' il giorno passato fra le due misure,
non un errore di conteggio). Delle 201 con `device_class`, CINQUE classi sono
di `binary_sensor` (`motion`, `connectivity`, `running`, `occupancy`, `plug`
-- 33 entita') e hanno GIA' il proprio significato acceso/spento in
la resa che Home Assistant pubblica per quella classe: un secondo
dizionario che dicesse la stessa cosa sarebbe il doppione che le fondamenta
vietano, quindi non compaiono qui. Restano in questo modulo le 27 coppie
(dominio, classe) delle altre SETTE piattaforme misurate -- 168 entita' --
che non traducono ancora il proprio significato da nessuna parte:
`button` (22), `media_player` (6), `number` (4), `sensor` (105), `switch`
(18), `update` (9), `valve` (4). 22+6+4+105+18+9+4 fa 168, non 164: il
conteggio sbagliava per un'assenza (`valve`, gia' in tabella a riga 302 e
nelle 27 coppie della prova, solo non nominata qui), corretto in questo
giro dalla review indipendente. 33 + 168 fa 201: nessuna entita' misurata
resta scoperta, nessuna coppia qui e' inventata
(`tests/test_ha_vocabulary.py` pinna entrambe le direzioni).

Il capitolato cita anche `unit_of_measurement` (100 entita' misurate): non ha
un proprio dizionario qui. Home Assistant CONVERTE l'unita' all'ingresso
dell'entita' (vedi il docstring di `topology.reference_frame`): l'unita' che
arriva e' gia' quella dichiarata dall'integrazione, non una sigla da
decifrare -- e' un dato, non un significato nascosto. Il numero e' stato
misurato lo stesso per verificare il metodo di misura, non perche' desse
un proprio perimetro da importare.

**Le quattro tabelle di significati non le consuma il digesto, e non le
consuma nemmeno `view`** (corretto il 09/09/2026: la frase precedente diceva
il contrario, ed era falsa il giorno stesso in cui l'ha letta un revisore).
`STATE_CLASS_MEANING`/`DEVICE_CLASS_MEANING` hanno oggi UN lettore --
`type_census.py:177,218`, che le usa per elencare le coppie (dominio, classe)
censite -- e `UNAVAILABLE_MEANING`/`UNKNOWN_MEANING` nessuno: restano
conoscenza per chi legge il codice o interroga la casa a mano, pinnate solo
dalla prova che le confronta con la fonte (`tests/test_ha_vocabulary.py`), non
un fatto che il digesto o `view` ripetono a ogni turno. **Le tre voci arrivate
l'08/09/2026 invece il
digesto le usa**: `config_entry_is_broken` decide la riga degli avvisi,
`config_entry_is_healthy` decide cosa l'osservatore scrive nell'archivio, e
`produces_statistics` decide su quale superficie si legge un andamento. Sono
qui perche' sono vocabolario del fornitore, non perche' nessuno le legga.
Ma `entity_category_measure_rule()` (sotto, insieme a
`ENTITY_CATEGORY_MEANING`) e' il PRIMO consumatore vero a runtime: `queries.
_view_entity` la chiama e cita cio' che ritorna nella chiave `regola`,
sul dettaglio di UN'entita' sola. La fonte e la versione scritte qui sono
cio' che permette a chi legge quella chiave di sapere se e' ancora valida.

**Il confine con `type_vocabulary.py`, dal 07/09/2026.** Il modulo vicino
porta il vocabolario dei TIPI: a quale gamba dell'obiettivo un tipo serve,
se «si accende e si spegne», quali suoi stati valgono «a riposo», che nomi
hanno i bit di `supported_features`. La regola che separa i due, scritta per
intero nel docstring di quel modulo: **una frase che spiega cosa SIGNIFICA un
valore sta qui; un giudizio su cosa un tipo SERVE o quando HA FINITO sta la'.**
`DEVICE_CLASS_MEANING`, indicizzato per `(dominio, classe)`, e' indicizzato
esattamente come un tipo: e' il candidato dichiarato a diventare un campo di
quelle righe, con la sua provenienza `importato`, quando la fetta che collega i
vocabolari arrivera'. Fino ad allora nessun fatto vive di qua e di la'.

**Il pezzo che lo rende duraturo.** Il vocabolario porta scritto DA QUALE
versione di Home Assistant viene (`VOCABULARY_HA_VERSION`), e
`house_is_newer_than_vocabulary()` la confronta con `versione_ha` -- lo
STESSO campo che gia' popola il sistema di riferimento della casa
(`home_space.topology.reference_frame()`, distillato da `Config.as_dict()`
chiave `"version"`) e che il nucleo dichiara in cima a ogni digesto
(`briefing._reference_frame_lines`): non una seconda idea di "versione della
casa", la stessa. Quando la casa supera la versione qui pinnata, la funzione
lo DICE -- un fatto, non un'eccezione, esattamente come i `repairs`
diagnosticati da HA restano avvisi e non eccezioni in
`briefing._integrations_notice`: il vocabolario non si sa sbagliato, si sa
vecchio, e la differenza e' cio' che invita a rileggere la documentazione
invece di continuare a fidarsi in silenzio.
"""
from __future__ import annotations

# --- la fonte, coi tag rilasciati (mai `dev`) ------------------------------
#
# Ogni voce di questo modulo e' stata verificata sul sorgente vero di Home
# Assistant al tag `2026.9.1` -- lo stesso gia' citato da `topology._FEATURE_NAMES`
# e da `tests/test_feature_tables_pinned_to_source.py` per lo stesso principio:
# mai `dev`, mai un ricordo. Le frasi che descrivono ogni classe (non solo il
# nome della costante) sono citate cosi' come compaiono nella documentazione
# per sviluppatori, verificata lo stesso giorno della misura sulla casa.
VOCABULARY_SOURCE = (
    "home-assistant/core, tag 2026.9.1 -- "
    "homeassistant/components/sensor/const.py (SensorDeviceClass, SensorStateClass); "
    "homeassistant/components/number/const.py (NumberDeviceClass); "
    "homeassistant/components/button/__init__.py (ButtonDeviceClass); "
    "homeassistant/components/switch/__init__.py (SwitchDeviceClass); "
    "homeassistant/components/update/__init__.py (UpdateDeviceClass); "
    "homeassistant/components/media_player/const.py (MediaPlayerDeviceClass); "
    "homeassistant/components/valve/const.py (ValveDeviceClass); "
    "homeassistant/const.py (EntityCategory); "
    "homeassistant/config_entries.py (ConfigEntryState); "
    "homeassistant/helpers/entity.py, Entity._stringify_state "
    "(la distinzione fra `unavailable` e `unknown`); "
    "homeassistant/helpers/translation.py:469-470, async_translate_state "
    "(la PROVA che `unavailable`/`unknown` HA non li traduce mai: li "
    "restituisce tali e quali prima di ogni gradino, e il suo frontend li "
    "rende da un bundle proprio che il backend non pubblica -- "
    "src/common/entity/compute_state_display.ts:94-101 @ frontend "
    "20260826.6) -- "
    "e developers.home-assistant.io/docs/core/entity/"
    "{button,switch,media-player,update,valve,sensor}/ (le frasi che "
    "descrivono ogni classe, verificate il 07/09/2026)."
)

# La versione che questo modulo rappresenta: NON la piu' recente possibile,
# la versione DEI TAG SOPRA -- se un domani si riverifica un tag piu' nuovo,
# questa stringa e' cio' che si aggiorna, e nessun altro punto del modulo.
VOCABULARY_HA_VERSION = "2026.9.1"


def _parsed_version(version: str) -> tuple[int, ...]:
    """`"2026.9.1"` -> `(2026, 9, 1)`. Home Assistant usa una versione
    calendariale (CalVer: anno.mese.patch), non semver -- confrontarla come
    STRINGA metterebbe `"2026.10.0"` PRIMA di `"2026.9.1"`: lessicograficamente
    il carattere `'1'` (di `"10"`) e' minore di `'9'`, quindi `"10" < "9"` come
    stringhe anche se `10 > 9` come numeri. Ed e' il confine vero, non un
    caso di scuola: `2026.10.0` e' la release successiva a quella pinnata da
    `VOCABULARY_HA_VERSION` (`tests/test_ha_vocabulary.py` lo attraversa
    apposta).

    Una componente con un suffisso non numerico (`"2026.9.0b0"`, una beta) si
    tronca al primo carattere non cifra, cosi' una beta non supera per
    errore la release finale dello stesso numero -- e non solleva: una
    versione che non si sa leggere del tutto diventa `0`, non un crash."""
    parsed = []
    for piece in version.split("."):
        digits = ""
        for char in piece:
            if not char.isdigit():
                break
            digits += char
        parsed.append(int(digits) if digits else 0)
    return tuple(parsed)


def house_is_newer_than_vocabulary(house_ha_version: str | None) -> dict:
    """Confronta la versione VIVA della casa con `VOCABULARY_HA_VERSION`.

    `house_ha_version` e' lo stesso `versione_ha` che
    `home_space.topology.reference_frame()` distilla dalla config di Home
    Assistant e che il nucleo dichiara in cima a ogni digesto -- non una
    seconda lettura, la stessa: chi chiama passa il campo che gia' possiede.

    Non solleva mai: un vocabolario invecchiato non e' un guasto, e' un
    fatto -- lo stesso principio per cui i `repairs` diagnosticati da HA
    restano AVVISI e non eccezioni in `briefing._integrations_notice`. Detto
    una volta, in una chiave che chi compone la conoscenza puo' leggere
    quando vorra' -- non gridato.

    Senza una versione letta (`None` o vuota: la casa non ha ancora costruito
    il proprio sistema di riferimento) non si dichiara "piu' vecchia": si
    dichiara "non lo so", perche' affermare un confronto su un dato che non
    c'e' sarebbe indovinare una casa piu' nuova che nessuno ha misurato.
    """
    if not house_ha_version:
        return {
            "vocabolario_piu_vecchio_della_casa": False,
            "versione_vocabolario": VOCABULARY_HA_VERSION,
            "versione_casa": None,
        }
    older = _parsed_version(house_ha_version) > _parsed_version(VOCABULARY_HA_VERSION)
    return {
        "vocabolario_piu_vecchio_della_casa": older,
        "versione_vocabolario": VOCABULARY_HA_VERSION,
        "versione_casa": house_ha_version,
    }


# --- cosa significa un `state_class` ---------------------------------------
#
# Home Assistant manda la stringa, mai il significato: un contatore che
# scende non e' spiegato in nessun campo della risposta. Le tre frasi sono
# quelle di `SensorStateClass` (sensor/const.py) e della pagina per
# sviluppatori -- non riformulate a senso, tradotte.
#
# Misurato sulla casa il 07/09/2026: 130 entita' su 130 con `state_class`
# sono `sensor` (l'unico dominio che lo dichiara) -- 57 `total`, 56
# `measurement`, 17 `total_increasing`. Il sorgente (`SensorStateClass`)
# dichiara ANCHE una quarta chiave, `measurement_angle`: zero entita' di
# questa casa la usano, e resta fuori per la stessa regola di sempre --
# "si importa cio' che la casa usa davvero", non "si importa tutto cio' che
# esiste" (`tests/test_ha_vocabulary.py` pinna anche questa esclusione).
STATE_CLASS_MEANING = {
    "measurement": (
        "Il valore rappresenta una misura ISTANTANEA, valida ORA -- non "
        "un'aggregazione storica ne' una previsione (temperatura, umidita', "
        "potenza adesso)."
    ),
    "total": (
        "Il valore e' un TOTALE cumulato che puo' sia CRESCERE che "
        "DECRESCERE (es. un contatore di energia netta, che scende quando "
        "si immette piu' di quanto si consuma): un calo non e' un guasto."
    ),
    "total_increasing": (
        "Il valore e' un totale che CRESCE SOLO in un verso, e puo' "
        "azzerarsi periodicamente a un nuovo ciclo (es. il gas consumato in "
        "un periodo, un contatore sostituito): un calo segnala un nuovo "
        "ciclo del contatore, non un guasto ne' un consumo negativo."
    ),
}


# --- cosa significa un `device_class`, dominio per dominio -----------------
#
# Chiave (dominio, classe): la STESSA stringa di classe cambia significato a
# seconda del dominio che la porta (`"battery"` e' una percentuale misurata
# su `sensor`, e' "carica bassa/normale" su `binary_sensor`) -- un
# dizionario che ignorasse il dominio mentirebbe su meta' delle voci.
#
# Le CINQUE classi di `binary_sensor` misurate su questa casa (`motion`,
# `connectivity`, `running`, `occupancy`, `plug`) NON compaiono: hanno gia'
# il proprio significato acceso/spento dalle traduzioni di Home Assistant
# (verificato il 16/08/2026). Ripeterle qui sarebbe il doppione che le
# fondamenta vietano.
#
# Fonte per ogni riga: `homeassistant/components/<dominio>/const.py` o
# `__init__.py` (tag `2026.9.1`, vedi `VOCABULARY_SOURCE`) per il valore
# della costante e l'unita' dichiarata; per `button`, `switch`,
# `media_player`, `update`, `valve` -- domini le cui classi non portano un
# docstring nel sorgente -- la frase e' quella della pagina per sviluppatori
# corrispondente, citata fra virgolette cosi' com'e'.
DEVICE_CLASS_MEANING = {
    # --- sensor: 18 classi, 105 entita' -------------------------------
    # Il valore che rappresentano e con che unita' -- HA lo converte
    # all'ingresso (vedi `topology.reference_frame`), quindi l'unita' che
    # arriva con l'entita' e' gia' una di queste, non da dedurre.
    ("sensor", "timestamp"): (
        "Un ISTANTE nel tempo (ISO 8601), non una durata: es. l'ultimo "
        "aggiornamento, l'ultimo avvio."
    ),
    # ATTENZIONE (annotato il 09/09/2026, nessun lettore ne oggi risente):
    # questa frase e' la trascrizione FEDELE di Home Assistant
    # (`SensorDeviceClass.ENERGY`, `components/sensor/const.py:236-240` @
    # 2026.9.1) -- non va corretta, sarebbe falsificare la fonte. Ma HA usa
    # la stessa classe per l'energia PRODOTTA da un fotovoltaico e per quella
    # PRELEVATA dalla rete, e su QUESTA casa il fotovoltaico produce:
    # `type_vocabulary.py` (righe intorno a "le direzioni dell'energia",
    # 27/08/2026) e CLAUDE.md lo dichiarano entrambi. Nessuno collega ancora
    # questa tabella alle righe dei tipi (type_census.py e' l'unico lettore,
    # e non la mostra): il giorno in cui qualcuno lo fara', un inverter
    # letto da qui uscirebbe come "energia consumata". La cura e' su quel
    # lettore futuro -- distinguere la direzione prima di citare questa
    # frase -- non su questa riga.
    ("sensor", "energy"): (
        "Energia CONSUMATA, cumulata nel tempo (J, kJ, Wh, kWh, ...): "
        "cresce, non e' un valore istantaneo -- quello e' `power`."
    ),
    ("sensor", "temperature"): "Temperatura (°C, °F, K).",
    ("sensor", "power"): (
        "Potenza ISTANTANEA (mW, W, kW, ...): quanto si sta consumando "
        "ADESSO, non il totale consumato -- quello e' `energy`."
    ),
    ("sensor", "enum"): (
        "Un elenco FISSO di opzioni (`options`): il valore e' sempre una di "
        "quelle, nessuna unita' di misura -- non un numero."
    ),
    ("sensor", "battery"): "Percentuale di carica residua (%).",
    ("sensor", "data_rate"): "Velocita' di trasferimento dati (kbit/s, kB/s, ...).",
    ("sensor", "duration"): (
        "Una DURATA fissa (d, h, min, s, ms, ...): un intervallo di tempo, "
        "non un istante -- quello e' `timestamp`."
    ),
    ("sensor", "illuminance"): "Illuminamento (lx).",
    ("sensor", "voltage"): "Tensione elettrica (V, mV, ...).",
    ("sensor", "humidity"): "Umidita' relativa dell'aria (%).",
    ("sensor", "uptime"): (
        "L'ISTANTE (ISO 8601) in cui il dispositivo o servizio si e' "
        "riavviato l'ultima volta -- NON da quanto tempo e' acceso, "
        "nonostante il nome: piccole derive fra un aggiornamento e l'altro "
        "si sopprimono da sole, per non generare cambi di stato inutili "
        "(verificato sul docstring di `SensorDeviceClass.UPTIME`)."
    ),
    ("sensor", "current"): "Corrente elettrica (A, mA, ...).",
    ("sensor", "carbon_dioxide"): "Concentrazione di CO2 nell'aria (ppm).",
    ("sensor", "atmospheric_pressure"): "Pressione atmosferica.",
    ("sensor", "sound_pressure"): "Pressione sonora (dB, dBA).",
    ("sensor", "data_size"): "Quantita' di dati (GB, MB, ...).",
    ("sensor", "pressure"): (
        "Pressione (mbar, cbar, bar, mPa, Pa, hPa, kPa, inHg, psi, inH2O)."
    ),

    # --- number: 1 classe, 4 entita' -----------------------------------
    # Home Assistant dichiara le classi di `number` allineate a quelle di
    # `sensor` (commento nel sorgente: "should be aligned with
    # SensorDeviceClass"): stesso significato, dominio diverso.
    ("number", "duration"): (
        "Una DURATA fissa (d, h, min, s, ms, ...), stesso significato di "
        "`sensor`/`duration` -- qui e' un valore IMPOSTABILE, non solo letto."
    ),

    # --- button: 2 classi, 22 entita' -----------------------------------
    # Un pulsante non ha un valore da leggere: la classe dice cosa succede
    # quando lo si preme. Frasi citate dalla pagina per sviluppatori
    # dell'entita' button.
    ("button", "identify"): (
        '"The button entity identifies a device" -- premuto, fa si\' che '
        "il dispositivo segnali la propria presenza (il modo dipende "
        "dall'integrazione, Home Assistant non lo standardizza)."
    ),
    ("button", "restart"): (
        '"The button entity restarts the device" -- premuto, riavvia il '
        "dispositivo."
    ),

    # --- switch: 2 classi, 18 entita' ------------------------------------
    ("switch", "outlet"): (
        '"Device is an outlet for power" -- una presa di corrente '
        "comandabile."
    ),
    ("switch", "switch"): (
        '"Device is switch for some type of entity" -- un interruttore '
        "generico, quando nessun'altra classe si applica meglio."
    ),

    # --- update: 1 classe, 9 entita' --------------------------------------
    ("update", "firmware"): (
        '"The update is a firmware update for a device" -- distingue un '
        "aggiornamento del FIRMWARE (tipico di un dispositivo fisico) da un "
        "aggiornamento di un'altra natura (un'integrazione, un add-on)."
    ),

    # --- media_player: 2 classi, 6 entita' ---------------------------------
    ("media_player", "speaker"): '"Device is speakers or stereo type device"',
    ("media_player", "tv"): '"Device is a television type device"',

    # --- valve: 1 classe, 4 entita' -----------------------------------------
    ("valve", "water"): (
        '"Control of a water valve" -- regola un flusso d\'acqua. '
        "(l'altra classe dichiarata da Home Assistant, `gas`, non e' "
        "misurata su questa casa.)"
    ),
}


# --- `unavailable` contro `unknown`: due fatti diversi, non due sinonimi ---
#
# Home Assistant manda la stessa forma per entrambi (una stringa nello
# stato), e senza questa distinzione scritta da qualche parte sembrano lo
# stesso "non lo so". Non lo sono: verificato alla fonte,
# `homeassistant/helpers/entity.py`, `Entity._stringify_state` (tag
# `2026.9.1`) -- l'ordine dei due controlli e' quello del sorgente, non
# un'interpretazione:
#
#   if not available:
#       return STATE_UNAVAILABLE
#   if (state := self.state) is None:
#       return STATE_UNKNOWN
#
# `available` e' una proprieta' che l'INTEGRAZIONE dichiara (vero di
# default): quando e' falsa, HA scrive "unavailable" PRIMA ancora di
# guardare il valore. Solo se l'entita' e' disponibile HA guarda il valore,
# e "unknown" e' cio' che scrive quando quel valore e' `None`.
UNAVAILABLE_MEANING = (
    "L'entita' NON e' raggiungibile: l'integrazione ha dichiarato "
    "`available = False` (dispositivo spento, offline, connessione persa). "
    "Home Assistant scrive lo stato come `unavailable` PRIMA di guardare il "
    "valore -- il collegamento manca, non solo il dato."
)

UNKNOWN_MEANING = (
    "L'entita' E' raggiungibile (`available` e' vero), ma il suo valore non "
    "e' ancora noto: `self.state` e' `None` -- lo stato iniziale prima "
    "della prima lettura, o un valore che l'integrazione stessa non sa "
    "dire. Il collegamento e' sano: manca solo il dato, non e' un guasto."
)

# Le due ETICHETTE BREVI di queste voci (`UNAVAILABLE_LABEL`/`UNKNOWN_LABEL`,
# fino al 07/09/2026) sono state rimosse dalla revisione indipendente del
# tratto v3.22.2..HEAD (rilievo R5): `proxy/state_translations.py` le
# consumava, ma il suo UNICO chiamante (`api/handlers_mind.py`, dietro
# `/api/mind/facts`) legge solo oggetti che `mind/facts.py::aggregate_day` ha
# gia' filtrato -- `unavailable`/`unknown` non aprono ne' chiudono un episodio
# e sono scartati prima che un `corpo.stato` esista. Il ramo che le usava era
# irraggiungibile fin dal commit che lo ha introdotto (`b68bda11`), e la
# prova che lo provava (`tests/test_mind_api.py`) costruiva a mano un corpo
# che l'archivio non produce mai -- codice morto con una prova che non poteva
# fallire per una ragione vera (fondamenta 4: se nessuno puo' chiederlo, non
# esiste). Le spiegazioni lunghe sopra (`UNAVAILABLE_MEANING`/
# `UNKNOWN_MEANING`) restano: sono conoscenza per chi legge il codice o
# interroga la casa a mano (vedi il docstring di testa del modulo), non un
# dato che un confine deve rendere -- non hanno mai avuto un chiamante da
# perdere.

# --- in che condizione e' una voce di configurazione ------------------------
#
# `ConfigEntryState` (`homeassistant/config_entries.py`, tag `2026.9.1`,
# verificato sul sorgente vero). E' vocabolario di Home Assistant come gli
# altri di questo modulo, e come gli altri HA lo manda come stringa senza mai
# dire cosa significhi.
#
# **Il soggetto e' l'INTEGRAZIONE, non il tipo di un'entita'**, quindi una casa
# propria qui e' legittima e non e' una riga del vocabolario dei tipi. Cio' che
# NON era legittimo -- ed e' il doppione che l'08/09/2026 si chiude -- erano le
# **due** copie: `briefing._BROKEN_INTEGRATION_STATES` elencava i quattro stati
# di guasto, `watcher._HEALTHY_INTEGRATION_STATES` i tre non-guasto piu'
# `loaded` trattato a parte, e i due elenchi si tenevano in piedi a vicenda
# senza che niente li confrontasse. Adesso il fatto e' uno: l'enumerazione, e
# quali di quelle condizioni sono un guasto.
#
# **`not_loaded` NON e' un guasto**, ed e' l'errore che costava di piu':
# «NOT_LOADED: The config entry has not been loaded. **This is the initial
# state when a config entry is created or when Home Assistant is restarted.**»
# (developers.home-assistant.io/docs/config_entries_index/). Misurato sulla
# casa vera: il nucleo annunciava «9 integrazioni non stanno funzionando» e
# quella vera era UNA (`lifx / Abat-jour`, `setup_retry`). Otto falsi allarmi
# su nove, letti ogni giorno.
#
# `setup_in_progress` e `unload_in_progress` non sono guasti per la ragione
# opposta: sono momentanei del boot.
CONFIG_ENTRY_STATES = frozenset({
    "loaded", "setup_error", "migration_error", "setup_retry", "not_loaded",
    "failed_unload", "setup_in_progress", "unload_in_progress",
})

CONFIG_ENTRY_FAILURE_STATES = frozenset({
    "setup_error", "setup_retry", "migration_error", "failed_unload",
})


def config_entry_is_broken(state: str | None) -> bool:
    """Se questa condizione dichiara un guasto.

    **Chi non e' elencato NON e' un guasto**, ed e' la prudenza del lettore: il
    nucleo entra nel prompt di ogni messaggio, e una condizione che Home
    Assistant aggiungesse domani verrebbe annunciata al proprietario come una
    cosa rotta senza che nessuno l'abbia mai guardata. Meglio tacere di una
    condizione nuova che gridare al guasto su una che non lo e' -- e' la stessa
    lezione degli otto `not_loaded`.
    """
    return (state or "") in CONFIG_ENTRY_FAILURE_STATES


def config_entry_is_healthy(state: str | None) -> bool:
    """Se questa condizione dichiara che l'integrazione sta bene.

    **Non e' il contrario esatto di `config_entry_is_broken`, e la differenza
    e' voluta**: una condizione che questo modulo non conosce non e' ne' l'una
    ne' l'altra, e i due lettori la trattano in modo opposto **perche' sbagliare
    costa loro cose diverse**. Il nucleo tace (vedi sopra); l'osservatore, che
    non parla a nessuno e SCRIVE NELL'ARCHIVIO, apre una condizione -- un
    guasto non registrato e' perso per sempre, un falso positivo si legge e si
    chiude. Fino all'08/09/2026 questa asimmetria esisteva gia', ma nasceva da
    due elenchi scritti a mano in due moduli: era un caso, non una scelta.
    """
    return (state or "") in CONFIG_ENTRY_STATES - CONFIG_ENTRY_FAILURE_STATES


# --- quali `state_class` producono statistiche a lungo termine --------------
#
# I soli valori di `SensorStateClass` che il recorder aggrega davvero in
# statistiche a lungo termine, verificati alla fonte (non a memoria: e' la
# stessa trappola di `carbon_monoxide`/`co` gia' pagata da questo progetto).
# `measurement_angle` ESISTE come `state_class` (angoli, per esempio la
# direzione del vento) ma NON produce statistiche -- lo documenta Home
# Assistant, non e' un'omissione nostra.
#
# **Un'appartenenza, non un'esclusione della sola `measurement_angle`**: il
# vocabolario di HA non si arrotonda, e domani potrebbe crescere di un'altra
# classe che non aggrega.
#
# **Perche' qui e non accanto a chi lo consuma.** Fino all'08/09/2026 questo
# insieme viveva in `home_space/historian.py`, dove `choose_surface` lo legge.
# E' vocabolario di Home Assistant, e questo modulo e' la casa del vocabolario
# di Home Assistant: `state_class` ce l'ha gia', due righe piu' su. Che le due
# chiavi coincidano oggi con quelle di `STATE_CLASS_MEANING` NON le rende lo
# stesso fatto -- «cosa significa» e «aggrega» sono due domande, e una classe
# nuova puo' benissimo avere un significato e non produrre statistiche:
# derivare l'uno dall'altro sarebbe un'identita' assunta, non misurata.
STATE_CLASSES_WITH_STATISTICS = frozenset({
    "measurement", "total", "total_increasing"})


def produces_statistics(state_class) -> bool:
    """Se questo `state_class` produce DAVVERO una statistica a lungo termine.

    Non `bool(state_class)`: quel cablaggio manderebbe ANCHE
    `measurement_angle` sul ramo statistiche, e una banderuola interrogata
    oltre la soglia di grana riceverebbe un elenco vuoto -- «non e' mai
    cambiata» -- mentre il dettaglio, la superficie giusta per lei, esiste.

    Il nome e' diverso dal parametro `has_statistics` che `historian` passa in
    giro (`trend`, `choose_surface`): quello e' gia' il booleano risolto,
    questa e' la funzione che lo risolve dal vocabolario di HA -- due cose
    diverse, non due nomi per la stessa.
    """
    return state_class in STATE_CLASSES_WITH_STATISTICS


# --- cosa significa un `entity_category` -----------------------------------
#
# Home Assistant manda `config`/`diagnostic` (o niente affatto, per la
# maggioranza delle entita' primarie), mai la spiegazione. Le due frasi sono
# quelle di `EntityCategory` (`homeassistant/const.py`, tag `2026.9.1`,
# verificato scaricando il sorgente vero -- `raw.githubusercontent.com/
# home-assistant/core/2026.9.1/homeassistant/const.py`, non a memoria):
# citate cosi' come compaiono nei commenti che accompagnano le due voci
# dell'enum, non riformulate.
#
# Gia' glossato altrove (`briefing.py`, la riga "entita' di servizio" --
# citazione diversa, developers.home-assistant.io, sulla VISIBILITA'
# nell'interfaccia; `topology._excluded_from_comparison`, un'etichetta breve)
# SENZA questo dizionario: quei due punti ora rimandano qui invece di
# ripetere il significato -- un secondo posto che lo dicesse a parole
# proprie sarebbe il doppione che le fondamenta vietano.
ENTITY_CATEGORY_MEANING = {
    "config": "An entity which allows changing the configuration of a device.",
    "diagnostic": "An entity exposing some configuration parameter, or diagnostics of a device.",
}


def entity_category_measure_rule(domain: str, category: str | None,
                                  device_class: str | None,
                                  unit: str | None) -> str | None:
    """La REGOLA citabile per il caso che ha chiuso lo sprint
    (`sensor.persons`, misurato il 06/09/2026 e riverificato il
    07/09/2026): una diagnostica di servizio senza classe ne' unita' non e'
    una misura della casa -- e' un dato tecnico sull'entita' o sul
    dispositivo (`ENTITY_CATEGORY_MEANING["diagnostic"]`, sopra).

    **Non un buco quando ritorna `None`: la legge.** Ritorna una stringa
    SOLO quando tre fatti sono veri insieme -- `dominio == "sensor"`,
    `categoria == "diagnostic"`, ne' `classe` ne' `unita'` -- e ritorna
    `None` in ogni altro caso, perche' il vocabolario non ha nessuna regola
    citabile li'. Una regola di ripiego sarebbe peggio del silenzio: avrebbe
    l'autorita' di una regola vera.

    **Perche' solo `sensor`.** E' l'UNICO dominio, fra quelli con entita'
    `diagnostic` misurate su questa casa, in cui sia `device_class` sia
    `unit_of_measurement` sono concetti che Home Assistant dichiara davvero
    (`DEVICE_CLASS_MEANING`, sopra) -- un `device_tracker` non li porta MAI
    (misurato il 07/09/2026: 68 `device_tracker` diagnostic su 68 senza
    classe ne' unita', il 100%): dire "non e' una misura" li' sarebbe una
    tautologia sul DOMINIO, non una regola sul DATO -- esattamente la forma
    di rumore (una chiave che scatta quasi sempre) che questo sprint ha gia'
    pagato una volta. Sui `sensor` diagnostici la differenza e' vera: 65 su
    89 non hanno ne' classe ne' unita' (le altre 24 la portano -- voltage,
    current, battery, enum, timestamp -- e su quelle questa funzione ritorna
    `None`, correttamente).

    `classe`/`unita'` vanno passati COSI' COME `queries._enrich_entity` li
    ha gia' risolti (specchio vivo sopra il registro, `actual_class`/
    `actual_unit`): il registro delle entita' non manda ne' l'uno ne'
    l'altro (`topology.py`, il docstring di `live_mirror`), quindi una
    chiamata che leggesse solo il registro troverebbe sempre classe/unita'
    assenti, anche su una diagnostica che una VERA classe/unita' vive
    dichiara -- il fatto misurato dal revisore su questo stesso task."""
    if domain != "sensor" or category != "diagnostic" or device_class or unit:
        return None
    return (
        "diagnostica di servizio (`entity_category: diagnostic` -- Home "
        "Assistant, `EntityCategory`, `homeassistant/const.py`, tag "
        f"`{VOCABULARY_HA_VERSION}`: "
        f"\"{ENTITY_CATEGORY_MEANING['diagnostic']}\"), senza `device_class` "
        "ne' unita' di misura dichiarate: non e' una misura della casa, e' "
        "un dato tecnico sull'entita' stessa."
    )
