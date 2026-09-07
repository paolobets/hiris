"""Il vocabolario che Home Assistant DOCUMENTA e non manda mai in un payload.

Un'entita' arriva con `device_class: "energy"` o `state_class:
"total_increasing"`: sono STRINGHE, non spiegazioni. Il significato -- che un
`total_increasing` puo' azzerarsi a un nuovo ciclo del contatore invece di
essere un guasto, che un pulsante `identify` fa segnalare il dispositivo, che
`unavailable` e `unknown` sono due fatti diversi -- vive solo nella
documentazione di Home Assistant e nel sorgente che la implementa, mai nella
risposta che il fornitore manda. Questo modulo lo IMPORTA, come `_DOMAIN_NAMES`
(briefing.py) importa i nomi delle piattaforme e `_FEATURE_NAMES`
(topology.py) importa le tabelle di `supported_features`: stessa disciplina di
"copiato dalla fonte, pinnato da una prova che si accorge quando diverge", non
una seconda forma inventata accanto.

**Non e' un elenco esaustivo di cio' che Home Assistant conosce.** E' il
PERIMETRO che QUESTA casa usa davvero, misurato su
`http://192.168.1.95:8123/api/states` il 07/09/2026: 835 entita' totali, 201
con `device_class`, 130 con `state_class` (gli stessi ordini di grandezza gia'
misurati il 06/09/2026 e riportati nel capitolato: 834/201/130 -- la
differenza di un'entita' sul totale e' il giorno passato fra le due misure,
non un errore di conteggio). Delle 201 con `device_class`, CINQUE classi sono
di `binary_sensor` (`motion`, `connectivity`, `running`, `occupancy`, `plug`
-- 33 entita') e hanno GIA' il proprio significato acceso/spento in
`_CLASS_MEANING` (topology.py, verificato il 16/08/2026): un secondo
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

**Il digesto non lo consuma -- `view` sì, da "rifiutare e importare" (Task
5, §6c).** `STATE_CLASS_MEANING`/`DEVICE_CLASS_MEANING`/`UNAVAILABLE_MEANING`/
`UNKNOWN_MEANING` restano conoscenza per chi legge il codice o interroga la
casa a mano, non un fatto che il digesto ripete a ogni turno --
diversamente da `_DOMAIN_NAMES`, che il digesto usa per contare a ogni
turno. Ma `entity_category_measure_rule()` (sotto, insieme a
`ENTITY_CATEGORY_MEANING`) e' il PRIMO consumatore vero a runtime: `queries.
_view_entity` la chiama e cita cio' che ritorna nella chiave `regola`,
sul dettaglio di UN'entita' sola. La fonte e la versione scritte qui sono
cio' che permette a chi legge quella chiave di sapere se e' ancora valida.

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
# il proprio significato acceso/spento in `topology._CLASS_MEANING`
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
