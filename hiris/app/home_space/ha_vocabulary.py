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
conteggio sbagliava per un'assenza (`valve`, gia' in tabella e
nelle 27 coppie della prova, solo non nominata qui), corretto
dalla review indipendente. 33 + 168 fa 201: nessuna entita' misurata
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
consuma nemmeno `queries.view`** (corretto il 09/09/2026: la frase precedente diceva
il contrario, ed era falsa il giorno stesso in cui l'ha letta un revisore).
`STATE_CLASS_MEANING` ha oggi UN lettore -- `scripts/censore_tipi.py`, che lo usa per
elencare le coppie (dominio, classe) censite. `DEVICE_CLASS_MEANING` ne ha
**due dal 12/09/2026**: quello e `mind/seed.meaning_seed`, che ne fa il SEME
del sapere (la fetta «il sapere e le ricette»). Sono due domande diverse sulla
stessa tabella -- «cosa il repo rivendica» e «cosa significa» -- e per questo
non sono un doppione. La differenza fra `unavailable` e `unknown` non e' piu'
una tabella: e' il commento accanto alla sua fonte, piu' sotto. **Le tre voci
arrivate l'08/09/2026 invece hanno
un lettore vivo ciascuna, e non e' lo stesso**: `config_entry_is_broken` la
usa il digesto, per la riga degli avvisi; `config_entry_is_healthy`
l'osservatore, per decidere cosa scrive nell'archivio; `bands_are_arithmetic`
la storia (`house_history.value_surface`), per dire su quale superficie si leggono i
valori, e `has_statistics` la casa del giro e il watcher. Sono
qui perche' sono vocabolario del fornitore, non perche' nessuno le legga.
Ma `entity_category_measure_rule()` (sotto, insieme a
`ENTITY_CATEGORY_MEANING`) e' il PRIMO consumatore vero a runtime: `queries.
_view_entity` la chiama e cita cio' che ritorna nella chiave `regola`,
sul dettaglio di UN'entita' sola. La fonte e la versione scritte qui sono
cio' che permette a chi legge quella chiave di sapere se e' ancora valida.

**Il confine con `type_vocabulary.py`, dal 07/09/2026.** Il modulo vicino
porta il vocabolario dei TIPI: che genere di episodio un tipo apre, se «si
accende e si spegne», quali suoi stati valgono «a riposo», che nomi hanno i
bit di `supported_features`. La regola che separa i due, scritta per intero
nel docstring di quel modulo: **una frase che spiega cosa SIGNIFICA un
valore sta qui; un giudizio su cosa un tipo SERVE o quando HA FINITO sta la'.**
`DEVICE_CLASS_MEANING`, indicizzato per `(dominio, classe)`, e' indicizzato
esattamente come un tipo: era **il candidato dichiarato** a diventare un campo
di quelle righe, e la fetta e' arrivata il 12/09/2026. Oggi quel fatto vive in
due posti -- questo dizionario e `sapere.db` -- **ma non e' un doppione
divergente**: il dizionario e' il SEME, il sapere e' cio' che la casa ne ha
fatto, e il seme corregge solo le righe che nessuno ha toccato. E' la forma che
la spec §8 chiede («il repo diventa il seme»).

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

import re

# --- la forma di un `entity_id` ---------------------------------------------
#
# `dominio.oggetto`, minuscole, cifre e `_`. **Una espressione sola, e sempre
# `fullmatch`** (Tappa 3, Task 7, B-24, 04/10/2026). Fino a quel giorno viveva
# in tre copie -- il client (`proxy/ha_client.py`), l'osservatore
# (`mind/watcher.py`), le plance (`home_space/behavior.py`) -- piu' una
# quarta che la importava (`mind/judgments.py`). Tre la provavano con
# `.match` e l'ancora `$`, che in Python accetta anche un `\n` finale
# (`"light.x\n"` passava); la quarta con `.fullmatch`, che no. Due porte, due
# risposte sullo stesso identificatore. Vince `fullmatch`: un id col ritorno a
# capo non e' un id di Home Assistant (cambio dichiarato nel piano).
#
# I commenti delle copie le dicevano «due esigenze contrapposte» -- una
# guardia stretta contro l'iniezione, un riconoscitore largo per le plance --
# ma l'espressione era la stessa carattere per carattere. Il giorno in cui il
# riconoscitore delle plance dovra' davvero essere piu' largo, avra' la sua
# espressione con la sua ragione: oggi sarebbe una copia che aspetta di
# divergere.
#
# NON e' la regola di Home Assistant (`core.valid_entity_id` vieta anche i
# `__` e il `_` ai bordi): e' la guardia di HIRIS, la stessa di prima.
ENTITY_ID_SHAPE = re.compile(r"[a-z][a-z0-9_]*\.[a-z0-9_]+")


def is_entity_id(value) -> bool:
    """Se `value` ha la forma di un `entity_id` (`ENTITY_ID_SHAPE`, intera)."""
    return isinstance(value, str) and ENTITY_ID_SHAPE.fullmatch(value) is not None


def domain_of(entity_id) -> str:
    """Il dominio di un `entity_id`: `light.cucina` -> `light`.

    Lo DICHIARA Home Assistant nell'id stesso -- non e' un elenco nostro -- e
    per questo la lettura e' banale, e sta nel suo vocabolario. Il punto non e'
    la logica: e' che era scritta in piu' moduli e due copie non
    erano d'accordo. Viveva in `topology` fino al 04/10/2026 (Tappa 3, Task
    7, B-24), quando le copie in linea (`split(".")[0]`) hanno cominciato a
    chiamarla: `type_judgments` non poteva importarla da li' senza un ciclo.

    Su un id senza punto -- una riga di registro corrotta, un
    id sintetico di un'integrazione mal formata -- una restituiva l'id intero e
    l'altra la stringa vuota, cosi' il nucleo stampava «1 unknown» fra i
    conteggi della casa e la ricerca sulla stessa entita' rispondeva
    `dominio: ""`. Due porte, due risposte sullo stesso oggetto.

    Vince l'ID INTERO, che era anche la scelta del nucleo: un dominio vuoto
    sparisce dai raggruppamenti e dai conteggi -- cioe' fa raccontare una casa
    piu' piccola di com'e' -- mentre un dominio strano si vede e si va a
    guardare. Stesso principio per cui `_domain_name` lascia uscire un
    dominio che non sa tradurre invece di saltare la riga.
    """
    text = str(entity_id)
    return text.split(".", 1)[0] if "." in text else text


# I quattordici tipi che `search/related` sa collegare -- i VALORI di
# `ItemType` (`homeassistant/components/search/__init__.py`, letti sul
# sorgente, non a memoria) -- nel vocabolario di HIRIS.
#
# A sinistra il nome vero di Home Assistant, che e' quello che va dentro il
# comando; a destra il nome italiano con cui quella cosa vive qui dentro.
# Stessa disciplina di `topology._REFERENCE_FRAME_FIELDS`: l'anagrafe parla la
# lingua di HIRIS ovunque, e una risposta meta' inglese sarebbe l'unico posto
# in cui non lo fa -- per giunta proprio quella da cui il modello ricava un
# `riferimento` da passare a `view`, che i tipi li nomina in italiano.
#
# Si legge nei DUE versi (`HA_LINK_TYPE` piu' sotto e' la stessa tabella
# rovesciata, non una seconda): il modello nomina «entita», Home Assistant
# vuole «entity». Due elenchi da tenere allineati a mano sarebbero due
# vocabolari, cioe' la forma di difetto che le fondamenta chiamano doppione.
#
# Alcuni di questi nomi -- area, entita, dispositivo, automazione, script,
# integrazione -- sono tipi che `view` sa aprire; gli altri no, e
# `view` lo DICHIARA invece di rispondere «non esiste» (vedi il ramo finale
# di `view`): un id vero preso da qui non deve poter diventare
# un'affermazione falsa sulla casa.
#
# **Le chiavi sono anche cio' che il client accetta** (`HAClient.
# RELATED_ITEM_TYPES` le chiede a questa tabella): fino al 04/10/2026 i
# quattordici valori di `ItemType` erano scritti due volte, qui (in
# `home_space/queries.py`) e nel client, e una prova ne confrontava le due
# copie (B-48). Sta in questo modulo perche' e' il vocabolario di Home
# Assistant e il client lo puo' importare senza tirarsi dietro `queries`.
LINK_NAME = {
    "area": "area",
    "automation": "automazione",
    "automation_blueprint": "progetto_di_automazione",
    "config_entry": "voce_di_configurazione",
    "device": "dispositivo",
    "entity": "entita",
    "floor": "piano",
    "group": "gruppo",
    "integration": "integrazione",
    "label": "etichetta",
    "person": "persona",
    "scene": "scena",
    "script": "script",
    "script_blueprint": "progetto_di_script",
}

# La stessa tabella dal verso del modello. Derivata, mai riscritta.
HA_LINK_TYPE = {our: their for their, our in LINK_NAME.items()}


# --- la fonte, coi tag rilasciati (mai `dev`) ------------------------------
#
# Ogni voce di questo modulo e' stata verificata sul sorgente vero di Home
# Assistant al tag `2026.9.1` -- lo stesso gia' citato dalle tabelle di `type_vocabulary`
# e da `tests/test_feature_tables_pinned_to_source.py` per lo stesso principio:
# mai `dev`, mai un ricordo. Le frasi che descrivono ogni classe (non solo il
# nome della costante) sono citate cosi' come compaiono nella documentazione
# per sviluppatori, verificata lo stesso giorno della misura sulla casa.
#
# Era la costante `VOCABULARY_SOURCE`, finche' la leggeva il seme; dal Task 0b
# della Tappa 8 (B-47) il seme cita per dominio (`device_class_source`) e la
# costante era rimasta senza lettori (rilievo N92-2, 08/10/2026): resta la
# citazione, come commento, per chi rilegge il modulo.
#
# Fonte: home-assistant/core, tag 2026.9.1 --
# homeassistant/components/sensor/const.py (SensorDeviceClass,
# SensorStateClass); homeassistant/components/number/const.py
# (NumberDeviceClass); homeassistant/components/button/__init__.py
# (ButtonDeviceClass); homeassistant/components/switch/__init__.py
# (SwitchDeviceClass); homeassistant/components/update/__init__.py
# (UpdateDeviceClass); homeassistant/components/media_player/__init__.py
# (MediaPlayerDeviceClass); homeassistant/components/valve/const.py
# (ValveDeviceClass); homeassistant/const.py (EntityCategory);
# homeassistant/config_entries.py (ConfigEntryState);
# homeassistant/helpers/entity.py, Entity._stringify_state (la distinzione fra
# `unavailable` e `unknown`); homeassistant/helpers/translation.py:469-470,
# async_translate_state (la PROVA che `unavailable`/`unknown` HA non li
# traduce mai: li restituisce tali e quali prima di ogni gradino, e il suo
# frontend li rende da un bundle proprio che il backend non pubblica --
# src/common/entity/compute_state_display.ts:94-101 @ frontend 20260826.6) --
# e developers.home-assistant.io/docs/core/entity/
# {button,switch,media-player,update,valve,sensor}/ (le frasi che descrivono
# ogni classe, verificate il 07/09/2026).

# La versione che questo modulo rappresenta: NON la piu' recente possibile,
# la versione DEI TAG SOPRA -- se un domani si riverifica un tag piu' nuovo,
# questa stringa e' cio' che si aggiorna, e nessun altro punto del modulo.
VOCABULARY_HA_VERSION = "2026.9.1"

#: Il tag piu' vecchio su cui le chiavi importate sono state verificate: e' il
#: minimo che l'add-on dichiara (`hiris/config.yaml: homeassistant`), ma e' un
#: fatto diverso -- dice dove si e' GUARDATO, non cosa si supporta.
OLDEST_VERIFIED_TAG = "2024.7.0"

#: Cosa viene da Home Assistant e cosa no, in una tabella che traduce le sue
#: chiavi (B-47, decisione D8 della Tappa 8, 08/10/2026). La CHIAVE -- un bit
#: di `*EntityFeature`, una coppia (dominio, `*DeviceClass`) -- e' sua, e si
#: cita col tag in cui esiste; la PAROLA italiana che arriva al modello
#: l'abbiamo scritta noi. Fino a quel giorno le due tabelle si dichiaravano
#: «importate» per intero, e la parola nostra passava per una citazione.
IMPORTED_KEY_OUR_WORD = "chiave importata, parola nostra"


def imported_key_source(what: str, domain: str, tags) -> str:
    """La fonte di una tabella «chiave importata, parola nostra»: cosa e' la
    chiave (`what`, la classe di Home Assistant), il dominio, e i tag in cui
    TUTTE le chiavi di quel dominio esistono. Una forma sola per le due
    tabelle (`DEVICE_CLASS_MEANING` qui, le capacita' in `type_vocabulary`)."""
    return (f"{IMPORTED_KEY_OUR_WORD} -- {what} di `{domain}`: home-assistant/core, "
            f"tag {' e '.join(tags)}, homeassistant/components/{domain}/ "
            "(const.py o __init__.py), mai `dev`; la parola italiana e' nostra")


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
# `__init__.py` (tag `2026.9.1`, vedi la fonte in testa al modulo) per il valore
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
    # questa tabella alle righe dei tipi (scripts/censore_tipi.py e' l'unico lettore,
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

#: Per ogni dominio di `DEVICE_CLASS_MEANING`, i tag di Home Assistant in cui
#: **tutte** le sue classi esistono (B-47). Misurato l'08/10/2026 sul sorgente
#: (`raw.githubusercontent.com/home-assistant/core/<tag>/...`, il
#: `*DeviceClass` di ogni dominio): `sensor` a `2024.7.0` non ha `uptime`, che
#: nasce dopo, quindi la sua chiave si cita solo al tag recente. Le altre sei
#: esistono identiche ai due tag. `tests/test_imported_key_tags.py` riscrive
#: la misura a mano e non la importa da qui.
DEVICE_CLASS_TAGS = {
    "sensor": (VOCABULARY_HA_VERSION,),
    "number": (OLDEST_VERIFIED_TAG, VOCABULARY_HA_VERSION),
    "button": (OLDEST_VERIFIED_TAG, VOCABULARY_HA_VERSION),
    "switch": (OLDEST_VERIFIED_TAG, VOCABULARY_HA_VERSION),
    "update": (OLDEST_VERIFIED_TAG, VOCABULARY_HA_VERSION),
    "media_player": (OLDEST_VERIFIED_TAG, VOCABULARY_HA_VERSION),
    "valve": (OLDEST_VERIFIED_TAG, VOCABULARY_HA_VERSION),
}


def device_class_source(domain: str) -> str:
    """La fonte del significato di una classe di `domain`: la coppia e' di
    Home Assistant al tag in cui esiste, la frase e' nostra (B-47)."""
    return imported_key_source("la classe (`*DeviceClass`)", domain,
                               DEVICE_CLASS_TAGS[domain])


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
#
# Quindi i due stati dicono due cose diverse:
#
#   unavailable  l'entita' NON e' raggiungibile: l'integrazione ha dichiarato
#                `available = False` (dispositivo spento, offline, connessione
#                persa). Il collegamento manca, non solo il dato.
#   unknown      l'entita' E' raggiungibile, ma il suo valore non e' ancora
#                noto: `self.state` e' `None` -- lo stato iniziale prima della
#                prima lettura, o un valore che l'integrazione stessa non sa
#                dire. Il collegamento e' sano: manca solo il dato.
#
# Fino al 02/10/2026 queste due spiegazioni erano due costanti
# (`UNAVAILABLE_MEANING`/`UNKNOWN_MEANING`) senza nessun lettore: nessuna porta
# le ha mai rese. Sono conoscenza per chi legge il codice, e per chi legge il
# codice basta un commento.

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
# esiste).

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


#: La condizione di un'istanza caricata: l'unica in cui le sue entita' sono
#: state aggiunte alla macchina degli stati (`ConfigEntryState.LOADED`).
CONFIG_ENTRY_LOADED = "loaded"

#: `source: "ignore"` e' una DECISIONE del proprietario, non un guasto: Home
#: Assistant lo scrive quando qualcuno usa «ignora» sulla scoperta di
#: un'integrazione, e quella voce non si carichera' piu' per scelta sua
#: (developers.home-assistant.io/docs/config_entries_config_flow_handler/).
#: Fino al 04/10/2026 la costante stava due volte, nel nucleo e
#: nell'osservatore, e il secondo toglieva gli spazi e il primo no (B-14).
CONFIG_ENTRY_SOURCE_IGNORE = "ignore"


def config_entry_is_ignored(source: str | None) -> bool:
    """Se il proprietario ha detto a Home Assistant di ignorare questa voce
    (B-14: un lettore solo per il nucleo e per l'osservatore)."""
    return str(source or "").strip() == CONFIG_ENTRY_SOURCE_IGNORE


# --- chi spegne un'entita', e cosa scrive Home Assistant di chi tace ---------
#
# **Letto nel sorgente il 04/10/2026, tag `2026.9.4`** (Tappa 3, Task 8,
# passo 1; B-25, D6):
#
# - `RegistryEntryDisabler` (`helpers/entity_registry.py:123-130`): `user`,
#   `integration`, `config_entry`, `device`, `hass`. `config_entry` e `device`
#   NON dicono chi: dicono che la decisione e' stata presa sopra.
#   `entity_registry.async_config_entry_disabled_by_changed` (`:2578-2604`)
#   spegne con `config_entry` le entita' di un'istanza spenta, e le riaccende
#   solo se portano quel valore.
# - `ConfigEntryDisabler` (`config_entries.py:232-235`): UN valore, `user`.
#   Un'istanza la spegne solo il proprietario. `as_json_fragment`
#   (`config_entries.py:659-685`, la forma di `config_entries/get`) porta
#   `disabled_by` accanto a `state`.
# - `DeviceEntryDisabler` (`helpers/device_registry.py:118-125`):
#   `config_entry`, `device` (il genitore e' spento), `integration`, `user`.
# - **`restored: true`** lo scrive `RegistryEntry.write_unavailable_state`
#   (`helpers/entity_registry.py:443-468`), SEMPRE con lo stato
#   `unavailable`, in tre casi: all'avvio, per ogni voce del registro NON
#   disabilitata che nessuna integrazione ha aggiunto
#   (`_write_unavailable_states`, `:2708-2718`); quando un'entita' viene tolta
#   ma la sua voce resta e non e' disabilitata -- per esempio l'istanza
#   scaricata (`Entity.async_remove`, `helpers/entity.py:1449-1504`); quando
#   un'entita' ricreata cambia id. E' quindi la risposta a «cosa dice lo stato
#   di un'entita' la cui istanza non e' caricata»: `unavailable` con
#   `restored: true`, oppure nessuno stato se l'entita' e' disabilitata
#   (una disabilitata non entra nella macchina degli stati,
#   `helpers/entity_platform.py`, «Not adding entity ... because it's
#   disabled»).
# - Un'entita' senza `unique_id` non entra nel registro
#   (`helpers/entity_platform.py`, ramo `entity.unique_id is None`): negli
#   stati e non nel registro non vuol dire «sparita».
#
# **Misurato sulla casa il 04/10/2026** (`scripts/casa.py`, sola lettura; i
# congelati del 03/10 in parentesi): 1.530 entita' nel registro (1.410);
# `disabled_by` `integration` 441 (401), `config_entry` 69, `device` 22,
# `user` 20, nessuno 978 (898). Le 69 `config_entry` stanno TUTTE su
# un'istanza spenta dal proprietario (2 istanze `disabled_by: user`, su 56), le
# 22 `device` TUTTE su un dispositivo spento da lui. 56 stati con `restored`
# (60), tutti `unavailable`, tutti di istanze `loaded`. Istanze: 45 `loaded`,
# 10 `not_loaded` (8 ignorate, 2 spente), 1 in avvio (`setup_retry` nei
# congelati). 552 voci del registro senza stato (512), tutte disabilitate; 3
# stati senza voce, tutti vivi.
ENTITY_DISABLED_BY_USER = "user"
#: I due valori di `disabled_by` che rimandano a chi sta SOPRA l'entita'.
ENTITY_DISABLED_BY_CONFIG_ENTRY = "config_entry"
ENTITY_DISABLED_BY_DEVICE = "device"
#: L'attributo di uno stato che Home Assistant scrive per chi non ha aggiunto
#: nessuno (`EntityStateAttribute.RESTORED`).
RESTORED_ATTRIBUTE = "restored"


# --- quali `state_class` producono statistiche a lungo termine --------------
#
# **La regola di Home Assistant, letta nel sorgente il 04/10/2026** (tag
# `2026.9.1`, commit `fc034572d0216a04ed40a07154394908a594dfed`; Tappa 3,
# Task 7, passo 1):
#
# - **Un dominio solo compila statistiche: `sensor`.** Il recorder chiama
#   `compile_statistics` e `list_statistic_ids` su ogni piattaforma `recorder`
#   che li dichiara (`components/recorder/statistics.py:775-782`), e al tag le
#   piattaforme `recorder.py` sono due, `sensor` e `stream`: solo la prima li
#   dichiara (`components/sensor/recorder.py:529`, `:829`).
# - **Con quali `state_class`: tutte e quattro quelle di `SensorStateClass`**
#   (`components/sensor/const.py:570-590`). `_get_sensor_states`
#   (`sensor/recorder.py:106-125`) prende i `sensor` con uno `state_class`
#   valido e non esclusi dal filtro del recorder; `DEFAULT_STATISTICS`
#   (`:65-74`) dice cosa ne fa: `measurement` -> media, minimo, massimo;
#   **`measurement_angle` -> media CIRCOLARE**; `total` e `total_increasing`
#   -> somma. Uno stato non numerico non entra nel conto (`_is_numeric`,
#   `:244`).
# - **Non e' tutto.** `recorder.async_import_statistics` lascia a qualunque
#   integrazione importare statistiche sotto un `entity_id`, e le statistiche
#   «esterne» (`dominio:qualcosa`) non sono entita'. Per questo la verita' e'
#   `recorder/list_statistic_ids` della casa, e la regola sopra e' solo il
#   ripiego per quando quella lettura manca (B-12).
#
# **Cio' che il sorgente smentiva** fino al 04/10/2026: questo commento diceva
# che `measurement_angle` NON produce statistiche, e l'insieme qui sotto la
# lasciava fuori. Al tag `2026.9.1` le produce (la media circolare, senza
# minimo ne' massimo): con B-12 l'insieme e' quello del sorgente, e la scelta
# della superficie della storia -- che di quella media circolare non sa che
# farsene -- e' diventata una domanda sua (`bands_are_arithmetic`, sotto).
#
# **Un'appartenenza, non un'esclusione**: il vocabolario di HA non si
# arrotonda, e domani potrebbe crescere di un'altra classe che non aggrega.
#
# **Perche' qui e non accanto a chi lo consuma.** Fino all'08/09/2026 questo
# insieme viveva in `home_space/historian.py`. E' vocabolario di Home
# Assistant, e questo modulo e' la casa del vocabolario di Home Assistant. Che
# le chiavi coincidano oggi con quelle di `STATE_CLASS_MEANING` NON le rende lo
# stesso fatto -- «cosa significa» e «aggrega» sono due domande.
STATE_CLASSES_WITH_STATISTICS = frozenset({
    "measurement", "measurement_angle", "total", "total_increasing"})

#: L'unico dominio che compila statistiche (vedi sopra: `sensor/recorder.py`
#: dichiara `compile_statistics`, `stream` no).
STATISTICS_DOMAIN = "sensor"

#: Le classi le cui fasce orarie portano la media CIRCOLARE e basta:
#: `DEFAULT_STATISTICS` in `components/sensor/recorder.py` (tag `2026.9.1`,
#: righe 64-73, letto il 04/10/2026) da' a `measurement_angle`
#: `{"mean"}` con `StatisticMeanType.CIRCULAR` -- niente minimo, niente
#: massimo, e una media di angoli che i conti di HIRIS (aritmetici) non sanno
#: leggere.
CIRCULAR_MEAN_STATE_CLASSES = frozenset({"measurement_angle"})


def produces_statistics(state_class) -> bool:
    """Se questo `state_class` fa compilare a Home Assistant una statistica a
    lungo termine -- per un `sensor` (vedi `has_statistics`). Le quattro
    classi di `SensorStateClass`, lette nel sorgente il 04/10/2026.

    **E' il ripiego, non la verita'**: la verita' e' l'elenco che Home
    Assistant tiene (`recorder/list_statistic_ids`), e questa regola serve
    solo quando quella lettura manca (B-12)."""
    return state_class in STATE_CLASSES_WITH_STATISTICS


def has_statistics(entity_id, state_class, statistic_ids) -> bool:
    """«Ha statistiche?» (B-12, Tappa 3, Task 7, 04/10/2026): LA regola, per
    chiunque.

    `statistic_ids` e' l'elenco che Home Assistant tiene, letto dal giro
    (`server.statistic_ids_for_round`): quando c'e', la risposta e' la sua --
    comprese le statistiche importate da un'integrazione sotto un
    `entity_id` (`async_import_statistics`), che nessuna regola sul
    `state_class` saprebbe vedere, e esclusi i `sensor` che il recorder non
    registra. `None` vuol dire «non letto»: allora, e solo allora, la regola
    del sorgente -- un `sensor` con uno dei quattro `state_class`.

    Fino a quel giorno le formule erano tre (registro B-12): il watcher
    (`sensor.` e uno `state_class` qualunque), `produces_statistics` (tre
    classi su quattro) e `statistic_ids`."""
    if statistic_ids is not None:
        return entity_id in statistic_ids
    return domain_of(entity_id) == STATISTICS_DOMAIN and produces_statistics(state_class)


def bands_are_arithmetic(state_class) -> bool:
    """Se le fasce orarie di Home Assistant per questo `state_class` portano
    numeri che i conti di HIRIS sanno leggere: media, minimo e massimo
    aritmetici, o la somma. Lo chiede la storia (`house_history.
    value_surface`) per scegliere fra il dettaglio e le fasce.

    Non e' «ha statistiche»: una banderuola (`measurement_angle`) le ha, ma
    con la sola media circolare (`CIRCULAR_MEAN_STATE_CLASSES`), e la
    superficie che la storia le sceglie resta il dettaglio, com'era prima
    di B-12."""
    return (produces_statistics(state_class)
            and state_class not in CIRCULAR_MEAN_STATE_CLASSES)


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
    ha gia' risolti (specchio vivo sopra il registro,
    `topology.live_first`): il registro delle entita' non manda ne' l'uno ne'
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
