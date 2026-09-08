"""Come Home Assistant rende uno stato, e da dove viene la tabella.

**Lo stato si RENDE alla lettura, non si salva.** E' l'opposto della regola
del nome amichevole (`mind/store.py`, colonna `friendly_name`), e non e'
un'incoerenza -- sono due cose di natura diversa:

- il nome puo' SPARIRE con l'entita', quindi si scrive quando lo si sa;
- lo stato non sparisce mai (`heat` e' il fatto, ed e' quello che
  `mind/facts.py` confronta con `_RESTING`/`_UNKNOWN` per aprire e chiudere
  gli episodi), mentre la sua TRADUZIONE migliora: una voce che oggi manca
  domani c'e'. Renderla alla lettura fa arrivare i miglioramenti anche alle
  righe vecchie; congelarla in colonna li perde per sempre. E la lingua e'
  una preferenza MUTABILE della casa (`hass.config.language`): congelare la
  resa congelerebbe anche quella, e chi cambia lingua vedrebbe meta'
  archivio nella vecchia.

**Nessun vocabolario nostro.** Home Assistant PUBBLICA le traduzioni degli
stati e sono consumabili da un add-on: un comando WebSocket solo,
`frontend/get_translations` con `category: "entity_component"`, senza
`@require_admin` (`homeassistant/components/frontend/__init__.py:1007-1019`
al tag `2026.9.1`). Misurato dal vivo su questa casa il 07/09/2026:
**801 chiavi, 53 domini, 65 KB, 13 ms**.

**L'ordine dei gradini non e' un'interpretazione.** E' quello di
`homeassistant/helpers/translation.py:459-491` (`async_translate_state`) al
tag `2026.9.1`, e il frontend di HA usa lo STESSO ordine
(`src/common/entity/compute_state_display.ts:274-292` @ `20260826.6`, col
commento «We don't know! Return the raw state.»). E' l'unico algoritmo che
HA ha.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# La categoria che porta le traduzioni degli stati per DOMINIO. Non e' quella
# che il nome suggerisce: `category: "state"` risponde con zero chiavi
# (misurato dal vivo, 07/09/2026), e `category: "entity"` (134 KB) copre solo
# le entita' con un `translation_key` proprio -- il primo gradino qui sotto.
STATE_TRANSLATIONS_CATEGORY = "entity_component"

#: Il trattino basso con cui Home Assistant scrive «vale per il dominio, senza
#: classe». Scritto una volta: e' una convenzione del fornitore, e ricopiarla a
#: mano in ogni costruzione di chiave e' il modo in cui una delle copie
#: diventerebbe un'altra cosa.
NO_DEVICE_CLASS = "_"


# --------------------------------------------------------------------------
# I TRE SILENZI di una lettura da Home Assistant
# --------------------------------------------------------------------------
#
# Il contratto etichettato di questo modulo -- «chi PRODUCE il motivo lo
# etichetta, non chi lo consuma lo indovina» -- aveva due esiti soli: letto,
# e non letto col motivo. **Ne servono tre**, e il terzo non e' una raffinatura
# teorica: e' MISURATO sulla casa vera l'08/09/2026.
#
#   1. «non ho potuto chiedere»            la rete, l'autenticazione, il rifiuto
#   2. «ho chiesto e non c’e'»             la cosa esiste, quella conoscenza no
#   3. «ho chiesto una cosa che non esiste» il soggetto della domanda non e' fra
#                                          cio' che Home Assistant pubblica
#
# **Il terzo e' quello che si dimentica.** `frontend/get_translations` NON
# valida `category`: chiesta una categoria inventata risponde `success: true`
# con **zero chiavi** -- misurato, non temuto (`categoria_che_non_esiste` ->
# `success=True, chiavi=0`, casa vera, HA `2026.9.1`). Senza il terzo caso un
# refuso nella categoria non produce un errore: produce un HIRIS che dice
# «questa casa non ha domini», che e' una bugia detta con sicurezza.
#
# Le tre etichette sono **le parole italiane della spec** (§4), perche' sono
# cio' che una persona legge in un rapporto: tradurle due volte fra il codice e
# la prosa e' il modo in cui due cose diverse tornano a chiamarsi con una parola
# sola.

SILENCE_UNREACHABLE = "non ho potuto chiedere"
SILENCE_ABSENT = "ho chiesto e non c’e'"
SILENCE_UNDEFINED = "ho chiesto una cosa che non esiste"

#: I tre, scritti una volta perche' una prova possa contarli: un quarto
#: silenzio nato di nascosto e' esattamente il modo in cui «perche' non lo so»
#: tornerebbe a essere un'opinione di chi legge.
SILENCES = (SILENCE_UNREACHABLE, SILENCE_ABSENT, SILENCE_UNDEFINED)


def known(value) -> dict:
    """L'esito pieno: `{"letto": True, "valore": ...}`.

    Le chiavi restano **italiane** come quelle che questo modulo gia' emette
    (`lette`, `motivo`, `risorse`): un contratto che si estende non cambia
    lingua a meta'. Gli identificatori del codice restano inglesi, come vuole
    il glossario.
    """
    return {"letto": True, "valore": value}


def unreachable(reason: str) -> dict:
    """Silenzio 1 -- e il motivo lo dichiara CHI HA FALLITO, non chi legge."""
    return {"letto": False, "silenzio": SILENCE_UNREACHABLE,
            "motivo": reason or "motivo non dichiarato"}


def absent(reason: str) -> dict:
    """Silenzio 2 -- il soggetto esiste, quella conoscenza su di lui no."""
    return {"letto": False, "silenzio": SILENCE_ABSENT,
            "motivo": reason or "motivo non dichiarato"}


def undefined(reason: str) -> dict:
    """Silenzio 3 -- il soggetto stesso non e' fra cio' che HA pubblica."""
    return {"letto": False, "silenzio": SILENCE_UNDEFINED,
            "motivo": reason or "motivo non dichiarato"}


def state_translation(state, *, domain, device_class=None, platform=None,
                      translation_key=None, component_resources,
                      entity_resources=None) -> str | None:
    """La resa di `state`, o `None` quando nessun gradino risponde.

    Trascrizione di `async_translate_state`
    (`homeassistant/helpers/translation.py:459-491`, tag `2026.9.1`), quattro
    gradini nell'ordine esatto:

    1. `component.{platform}.entity.{domain}.{translation_key}.state.{state}`
       nelle risorse di `category: "entity"` (`:472-478`);
    2. `component.{domain}.entity_component.{device_class}.state.{state}`
       (`:480-486`);
    3. `component.{domain}.entity_component._.state.{state}` (`:487-489`);
    4. nessuna traduzione (`:491`).

    **Uno scostamento dichiarato dal sorgente di HA, e ha un perche' che vale
    piu' della fedelta' letterale.**

    **Il quarto gradino torna `None`, non il grezzo.** HA a `:491` fa
    `return state`, e chi lo chiama non puo' piu' distinguere «tradotto» da
    «non traducibile» senza confrontare due stringhe. Qui il buco lo dichiara
    la FONTE, non lo indovina chi consuma: e' la stessa disciplina per cui
    `read_registries` distingue un registro vuoto da un registro caduto, e la
    stessa che rende possibile dire al proprietario «le traduzioni non si sono
    potute leggere» invece di «questo stato non ha traduzione» -- due fatti
    diversi che non devono produrre la stessa risposta. Il grezzo resta cio'
    che il lettore vede: e' una DECISIONE di chi rende (il confine dell'API
    non emette nessun campo, e la pagina mostra `stato`), non un dato.

    **`unavailable`/`unknown` non arrivano mai qui.** HA a `:469-470` li
    restituisce grezzi, prima di ogni gradino, e il suo frontend li rende da
    un bundle proprio che il backend non pubblica -- per un add-on sarebbe
    un buco da colmare. Ma l'UNICO chiamante di questa funzione
    (`api/handlers_mind.py::_with_rendered_states`, dietro `/api/mind/facts`)
    legge oggetti che `mind/facts.py::aggregate_day` ha gia' filtrato: quei
    due stati non aprono ne' chiudono un episodio e sono scartati PRIMA che un
    `corpo.stato` esista (`facts.py`, il filtro su `_UNKNOWN` in cima alla
    funzione). Fino al 07/09/2026 questa funzione portava due etichette
    proprie per quel caso (`_OUR_LABELS`, commit `b68bda11`): un ramo morto,
    mai raggiungibile dal suo unico chiamante -- rimosso dalla revisione
    indipendente del tratto (rilievo R5), insieme alla prova che costruiva a
    mano un `corpo.stato` che l'archivio non produce mai. Se domani un
    secondo chiamante rendesse `stato` per un oggetto NON filtrato da
    `aggregate_day`, il posto giusto per le due etichette e' li' -- non qui,
    dove sarebbero di nuovo irraggiungibili.

    `component_resources` e' obbligatorio ed e' il dizionario piatto di
    `category: "entity_component"`; `entity_resources` (`category: "entity"`)
    e' facoltativo, e senza di esso il primo gradino non puo' rispondere --
    cade sul secondo, che e' esattamente cio' che HA fa quando la cache di
    quella categoria e' vuota.
    """
    if not isinstance(state, str) or not state:
        return None
    if not isinstance(domain, str) or not domain:
        return None
    if platform and translation_key and isinstance(entity_resources, dict):
        key = (f"component.{platform}.entity.{domain}."
               f"{translation_key}.state.{state}")
        if key in entity_resources:
            return entity_resources[key]
    if not isinstance(component_resources, dict):
        return None
    if device_class:
        key = f"component.{domain}.entity_component.{device_class}.state.{state}"
        if key in component_resources:
            return component_resources[key]
    key = f"component.{domain}.entity_component._.state.{state}"
    if key in component_resources:
        return component_resources[key]
    return None


def attribute_value_translation(value, *, domain, attribute, device_class=None,
                                component_resources) -> str | None:
    """La resa del VALORE di un attributo di stato, o `None`.

    Stessa forma della resa di uno stato, un gradino piu' in basso nella
    chiave:

        component.{dominio}.entity_component.{classe|_}.state_attributes.
        {attributo}.state.{valore}

    Serve a un attributo solo, oggi -- `hvac_action` -- e serve **perche' un
    termostato ha due fatti, non uno**: `hvac_mode` dice a cosa e' impostato,
    `hvac_action` dice se sta funzionando adesso. Home Assistant li pubblica
    tutti e due, con NOVE valori per il secondo (`defrosting` e `preheating`
    compresi: due che la tabella scritta a mano non aveva).
    """
    if not isinstance(value, str) or not value:
        return None
    if not isinstance(domain, str) or not domain:
        return None
    if not isinstance(attribute, str) or not attribute:
        return None
    if not isinstance(component_resources, dict):
        return None
    for written_class in _class_steps(device_class):
        key = (f"component.{domain}.entity_component.{written_class}."
               f"state_attributes.{attribute}.state.{value}")
        if key in component_resources:
            return component_resources[key]
    return None


def attribute_name_translation(*, domain, attribute, device_class=None,
                               component_resources) -> str | None:
    """Come Home Assistant CHIAMA un attributo di stato -- «Azione in corso»
    per `hvac_action`.

    Stessa chiave della resa, con `.name` al posto di `.state.{valore}`. Serve
    a non inventare la parola che tiene insieme le due meta' di un termostato:
    l'impostazione e cio' che sta facendo adesso sono due fatti, e chi legge
    deve sapere quale sta leggendo. La parola che li separa la dice HA.
    """
    if not isinstance(domain, str) or not domain or not isinstance(attribute, str):
        return None
    if not isinstance(component_resources, dict):
        return None
    for written_class in _class_steps(device_class):
        key = (f"component.{domain}.entity_component.{written_class}."
               f"state_attributes.{attribute}.name")
        if key in component_resources:
            return component_resources[key]
    return None


def _class_steps(device_class) -> tuple[str, ...]:
    """I gradini di una chiave: prima la classe, poi il `_` del dominio.

    E' l'ordine di `async_translate_state`, sceso di un gradino
    (`state_attributes`): la classe e' piu' specifica del dominio, e un tipo
    che non ne ha cade sul `_` -- che non e' una classe, e' la convenzione con
    cui HA scrive «vale per il dominio intero».
    """
    return ((device_class, NO_DEVICE_CLASS) if device_class else (NO_DEVICE_CLASS,))


#: I due silenzi che parlano della TABELLA, non di un singolo stato: senza
#: traduzioni lette («non ho potuto chiedere») o con una categoria che Home
#: Assistant non pubblica («ho chiesto una cosa che non esiste») nessuno stato
#: si rende, e chi legge lo dichiara una volta sola. Il terzo -- «ho chiesto e
#: non c’e'» -- riguarda quello stato soltanto, e si comporta come si comporta
#: Home Assistant: mostra il grezzo, senza annunciare un guasto che non c'e'.
#:
#: Sta QUI e non in ciascun lettore perche' i lettori sono due (il nucleo e
#: `guarda`) e devono trattarli allo stesso modo: due elenchi identici scritti
#: in due file sono due elenchi che divergono.
TABLE_MISSING_SILENCES = (SILENCE_UNREACHABLE, SILENCE_UNDEFINED)


#: I due stati di cui una coppia si compone, **nell'ordine acceso-spento**. La
#: coppia e' un oggetto con due meta', e cercarle con due stringhe sparse
#: sarebbe il modo in cui una delle due smetterebbe di essere cercata.
PAIR_STATES = ("on", "off")


def published_pair(component_resources, *, domain, device_class=None) -> dict:
    """La coppia acceso/spento di un tipo, **ricostruita** dalle due chiavi di
    Home Assistant -- `("Bagnato", "Asciutto")` per `(binary_sensor, moisture)`.

    **Va ricostruita, non assunta** (spec §6, secondo vincolo). E' l'unica cosa
    che `topology._CLASS_MEANING` portava e che Home Assistant non da' gia'
    fatta: la coppia TENUTA INSIEME. HA pubblica due chiavi indipendenti, e
    fino all'08/09/2026 le due meta' stavano in una tupla scritta a mano --
    dove non potevano divergere, e dove nessuna delle due poteva mancare.

    **E fallisce dichiarandolo quando una delle due manca**, invece di
    consegnare una coppia con dentro un buco. Meta' coppia e' peggio di
    nessuna: renderebbe «Bagnato» per `on` e «Spento» -- la parola generica del
    dominio -- per `off`, cioe' due meta' di due tipi diversi presentate come
    un significato solo. Chi riceve il silenzio scende di un gradino
    DICHIARANDOLO, e le due meta' restano dello stesso tipo.
    """
    if not isinstance(component_resources, dict) or not component_resources:
        return unreachable("le traduzioni di Home Assistant non sono state lette: "
                           "senza di loro nessuna coppia si puo' ricostruire")
    written_class = device_class or NO_DEVICE_CLASS
    words = {}
    for state in PAIR_STATES:
        key = f"component.{domain}.entity_component.{written_class}.state.{state}"
        if key in component_resources:
            words[state] = component_resources[key]
    written = f"({domain}, {device_class})" if device_class else domain
    if len(words) == len(PAIR_STATES):
        return known(tuple(words[state] for state in PAIR_STATES))
    if not words:
        return absent(
            f"il tipo {written} non pubblica ne' `.state.on` ne' `.state.off`: "
            "non e' un tipo che sta acceso o spento")
    present = next(state for state in PAIR_STATES if state in words)
    missing = next(state for state in PAIR_STATES if state not in words)
    return absent(
        f"la coppia di {written} non si ricostruisce: Home Assistant pubblica "
        f"«{words[present]}» per `{present}` e nessuna chiave `.state.{missing}`. "
        "Meta' coppia non si consegna: sarebbe una parola di questo tipo "
        "accanto a una parola di un altro")


def rendered_state(state, *, domain, device_class=None, translations) -> dict:
    """Lo stato in parole **secondo Home Assistant**, o il silenzio col motivo.

    E' cio' che ha sostituito `topology._STATE_TRANSLATION` e
    `topology._CLASS_MEANING` l'08/09/2026, e la differenza che conta e' una
    sola: **il dominio decide**. La tabella cancellata era cieca al dominio --
    rendeva `off` «spento» tanto su una luce quanto su un'entita' di
    aggiornamento, dove Home Assistant dice «Aggiornato»; e rendeva `open`
    «aperta» tanto su una tapparella quanto su una serratura, col genere
    grammaticale scelto per una delle due.

    `translations` e' l'esito etichettato di `StateTranslations.read` --
    `{"lette": True, "risorse": {...}}` oppure `{"lette": False, "motivo":
    ...}`. **Non si accetta il dizionario nudo delle risorse**: chi lo passasse
    non avrebbe modo di distinguere «non ho potuto chiedere» da «questo stato
    non ha resa», ed e' precisamente la distinzione che una tabella scritta a
    mano non poteva avere e che questa fetta esiste per dare.

    I tre esiti sono i tre silenzi del modulo, e arrivano al lettore separati.
    """
    if not isinstance(translations, dict) or not translations.get("lette"):
        reason = translations.get("motivo") if isinstance(translations, dict) else None
        return unreachable(reason or "le traduzioni di Home Assistant non sono "
                                     "ancora state lette da questa casa")
    resources = translations.get("risorse")
    if not isinstance(resources, dict) or not resources:
        return undefined(
            "Home Assistant ha risposto senza errore e con zero chiavi: la "
            "categoria chiesta non e' fra quelle che pubblica")
    text = str(state)
    if device_class and text in PAIR_STATES:
        # **La coppia, non la sola meta' che serve adesso.** Un tipo con classe
        # che pubblica una sola delle due chiavi non e' un tipo con una resa
        # per `on`: e' un tipo di cui non sappiamo dire l'altra meta', e
        # renderne una sola rimetterebbe insieme parole di due tipi diversi --
        # cio' che la tupla scritta a mano impediva per costruzione. Si scende
        # al gradino del dominio, che e' un tipo solo e ce l'ha tutta.
        pair = published_pair(resources, domain=domain, device_class=device_class)
        if pair.get("letto"):
            return known(pair["valore"][PAIR_STATES.index(text)])
        device_class = None
    word = state_translation(text, domain=domain, device_class=device_class,
                             component_resources=resources)
    if word is None:
        written = f"({domain}, {device_class})" if device_class else domain
        return absent("Home Assistant non pubblica nessuna resa per lo stato "
                      f"«{text}» del tipo {written}")
    return known(word)


# --------------------------------------------------------------------------
# COSA QUESTA CASA PUBBLICA ADESSO, distillato dalle stesse 801 chiavi
# --------------------------------------------------------------------------
#
# **Nessuna chiamata in piu'.** Le quattro materie qui sotto escono TUTTE dalla
# risposta che questo modulo gia' scarica per rendere uno stato: un comando
# solo, `frontend/get_translations` con `category: "entity_component"`.
# Misurato sulla casa vera l'08/09/2026 (HA `2026.9.1`, lingua `it`, 801
# chiavi):
#
#   domini caricati                 53
#   tipi con enumerazione di stati  61  (31 domini piu' 30 coppie con classe)
#   domini con `device_class`       12  (`sensor` 62, `number` 58,
#                                        `binary_sensor` 28)
#   valori legali di `state_class`   4  (uno piu' dei tre che HIRIS scriveva)
#
# **La forma delle chiavi non e' indovinata**: e' quella che
# `state_translation` qui sopra gia' trascrive da
# `homeassistant/helpers/translation.py:459-491`.
#
#   component.{dominio}.entity_component._.state.{stato}
#   component.{dominio}.entity_component.{classe}.state.{stato}
#   component.{dominio}.entity_component.{classe}.name
#   component.{dominio}.entity_component.{classe}.state_attributes.{attributo}
#                                                 .state.{valore}
#
# Le funzioni sono PURE: prendono il dizionario piatto e non toccano la rete.
# Una tabella si legge cosi' anche in una prova, senza casa.


def _entity_component_key(key) -> list[str] | None:
    """I pezzi di una chiave di `entity_component`, o `None` se non lo e'.

    Una chiave che non ha questa forma non e' un errore da segnalare: la
    risposta di Home Assistant ne porta anche di altre specie, e saltarle e'
    cio' che fa il suo frontend. Cio' che NON si fa e' indovinare: una chiave
    corta o con un prefisso diverso esce di qui, non entra in una tabella con
    un valore inventato.
    """
    if not isinstance(key, str):
        return None
    parts = key.split(".")
    if len(parts) < 4 or parts[0] != "component" or parts[2] != "entity_component":
        return None
    return parts


def published_domains(resources) -> frozenset[str]:
    """I domini che QUESTA casa ha caricato -- 53, misurati.

    Non e' l'elenco esaustivo delle piattaforme di Home Assistant (quello non
    lo pubblica nessuna API): e' cio' che questa installazione ha acceso, che
    e' la domanda a cui serve rispondere.
    """
    if not isinstance(resources, dict):
        return frozenset()
    return frozenset(parts[1] for parts in
                     (_entity_component_key(key) for key in resources)
                     if parts is not None)


def published_device_classes(resources) -> dict[str, frozenset[str]]:
    """Dominio -> le sue `device_class`, come Home Assistant le pubblica.

    Si leggono dalle chiavi `.name` e non da quelle `.state`, ed e' una
    differenza che si vede sui numeri: `sensor` ha 62 classi e **nessuna** di
    esse enumera stati (sono misure), quindi una tabella costruita dagli stati
    ne perderebbe 62 su 62 senza dirlo.
    """
    per_domain: dict[str, set[str]] = {}
    if not isinstance(resources, dict):
        return {}
    for key in resources:
        parts = _entity_component_key(key)
        if parts is None or len(parts) != 5 or parts[4] != "name":
            continue
        if parts[3] == NO_DEVICE_CLASS:
            continue
        per_domain.setdefault(parts[1], set()).add(parts[3])
    return {domain: frozenset(classes) for domain, classes in per_domain.items()}


def published_states(resources) -> dict[tuple[str, str | None], frozenset[str]]:
    """(dominio, classe o `None`) -> gli stati canonici di quel tipo.

    **La chiave e' il TIPO**, la stessa del vocabolario dei tipi: un dominio, o
    una coppia. Il `_` di Home Assistant -- che significa «vale per il dominio,
    senza classe» -- diventa `None`, cosi' che nessun consumatore debba sapere
    che quel trattino basso e' una convenzione e non una classe di dispositivo.
    """
    per_type: dict[tuple[str, str | None], set[str]] = {}
    if not isinstance(resources, dict):
        return {}
    for key in resources:
        parts = _entity_component_key(key)
        if parts is None or len(parts) < 6 or parts[4] != "state":
            continue
        device_class = None if parts[3] == NO_DEVICE_CLASS else parts[3]
        # Lo stato e' TUTTO cio' che resta: un valore con un punto dentro non
        # si taglia a meta'. Prendere `parts[5]` e basta produrrebbe uno stato
        # che non esiste, senza che niente lo segnali.
        per_type.setdefault((parts[1], device_class), set()).add(".".join(parts[5:]))
    return {type_key: frozenset(states) for type_key, states in per_type.items()}


#: L'attributo di stato di cui si vogliono i valori legali. Uno solo, e scritto
#: qui perche' e' l'unico che decide come si legge un numero: `total_increasing`
#: e `measurement` non si sommano allo stesso modo.
STATE_CLASS_ATTRIBUTE = "state_class"


def published_state_classes(resources) -> frozenset[str]:
    """I valori legali di `state_class`, come questa casa li pubblica.

    **Quattro, non tre**: `measurement`, `measurement_angle`, `total`,
    `total_increasing` (misurati). Il quarto -- `measurement_angle` -- e'
    esattamente il tipo di voce che una lista scritta a mano non guadagna mai:
    e' nato in Home Assistant, e nessuno qui se n'e' accorto.
    """
    values: set[str] = set()
    if not isinstance(resources, dict):
        return frozenset()
    for key in resources:
        parts = _entity_component_key(key)
        if (parts is None or len(parts) < 8 or parts[4] != "state_attributes"
                or parts[5] != STATE_CLASS_ATTRIBUTE or parts[6] != "state"):
            continue
        values.add(".".join(parts[7:]))
    return frozenset(values)


class StateTranslations:
    """La tabella delle traduzioni, letta da Home Assistant e tenuta in cache.

    **Si rilegge quando cambia `versione_ha` o `lingua`**, le due cose che
    HIRIS gia' distilla da `Config.as_dict()` in
    `home_space.topology.reference_frame()` -- non una seconda idea di
    "versione della casa" o di "lingua della casa", le stesse. Fra un cambio e
    l'altro la lettura costa zero: 801 chiavi restano in memoria.

    **Non entra nel batch di `read_registries`.** Quel metodo dichiara nel
    proprio docstring che «una funzione che restituisce registri restituisce
    registri», ed e' la ragione per cui nemmeno `get_config` ci sta dentro.
    Un comando suo, su una connessione sua, 13 ms.

    **Risponde SEMPRE con un esito etichettato**, mai con un dizionario vuoto
    che chi legge deve interpretare: `{"lette": True, "lingua": ..., "risorse":
    {...}}` oppure `{"lette": False, "motivo": "..."}`. Le traduzioni non
    lette e uno stato senza traduzione sono due fatti diversi, e chi PRODUCE
    il motivo deve etichettarlo -- non chi lo consuma indovinarlo.

    **`published_domains`/`published_device_classes`/`published_states`/
    `published_state_classes`** (sopra, in questo stesso modulo) distillano
    dalle stesse chiavi cio' che una casa DICHIARA di avere -- non da questa
    cache, che resta la sola lettura sincrona per rendere uno stato. Il
    censore (`home_space/type_census.py`) e lo script che gli fa da fonte
    (`scripts/istantaneo_pubblicato.py`) le chiamano direttamente sulle
    risorse che leggono da soli, senza passare da qui: sono le due domande
    diverse sulla stessa lettura di cui parla il loro modulo -- «come si rende
    uno stato» qui dentro, «cosa questa casa dichiara di avere» li'.
    (R6, revisione del tratto v3.23.0..HEAD, 08/09/2026: fino a questa
    correzione questa classe portava anche `published()` e `PublishedTypes`,
    un secondo wrapper con gli stessi tre silenzi ma NESSUN chiamante di
    produzione -- il censore e lo script non li usavano mai. Codice vivo per
    le prove e morto per il prodotto, cancellato: se un domani un consumatore
    vero avesse bisogno della cache invece della lettura diretta, si
    ricostruisce da queste quattro funzioni pure, che restano.)
    """

    def __init__(self, client, *, category: str = STATE_TRANSLATIONS_CATEGORY) -> None:
        self._client = client
        self._category = category
        self._key: tuple[str | None, str | None] | None = None
        self._resources: dict | None = None
        self._lock = asyncio.Lock()

    async def read(self, *, ha_version, language) -> dict:
        """L'esito etichettato per questa coppia `(versione_ha, lingua)`.

        Senza `lingua` non si legge affatto, e non si indovina un `"en"`:
        `frontend/get_translations` vuole la lingua come parametro
        OBBLIGATORIO (`frontend/__init__.py:1007-1015`), e sceglierne una noi
        vorrebbe dire rendere la pagina in una lingua che il proprietario non
        ha chiesto. Il motivo lo dice l'esito.

        Un guasto NON invalida la cache buona di prima: se una lettura fallisce
        ma la coppia e' ancora quella gia' letta, si continua a rendere con la
        tabella che si ha. Una tabella che c'e' e' meglio di un vuoto
        dichiarato fresco -- e' la stessa scelta di `topology.rebuild()`.
        """
        key = (ha_version, language)
        if not language:
            return {"lette": False,
                    "motivo": "la lingua della casa non e' nota: l’anagrafe non ha "
                              "ancora letto il sistema di riferimento di Home Assistant"}
        async with self._lock:
            # Il controllo della cache sta DENTRO il lock, e ce n'e' uno solo.
            # Fuori sarebbe stato piu' veloce (chi ha gia' la tabella non
            # aspetta nessuno), ma allora ne servirebbero DUE -- lo stesso
            # confronto e lo stesso ritorno scritti due volte, e quello fuori
            # non lo puo' pinnare nessuna prova: toglierlo lascia il
            # comportamento identico, perche' quello dentro fa gia' lo stesso
            # lavoro. Un doppione che nessuna mutazione puo' vedere rosso e' il
            # peggiore dei doppioni. Il lock qui non e' conteso (due letture
            # della pagina in parallelo sono il caso raro) e serve comunque:
            # senza, due letture simultanee farebbero due chiamate identiche a
            # Home Assistant.
            if self._resources is not None and self._key == key:
                return {"lette": True, "lingua": language, "risorse": self._resources}
            report = await self._client.get_translations(language, category=self._category)
            if "risorse" not in report:
                reason = report.get("errore") or "motivo non dichiarato"
                logger.debug("traduzioni degli stati non lette (%s): %s", language, reason)
                return {"lette": False, "motivo": reason}
            self._resources = report["risorse"]
            self._key = key
            logger.info("traduzioni degli stati lette da Home Assistant: %d chiavi (%s, HA %s)",
                        len(self._resources), language, ha_version)
        return {"lette": True, "lingua": language, "risorse": self._resources}

    def cached(self) -> dict:
        """Cio' che si ha **adesso, senza chiedere niente a nessuno** --
        etichettato coi tre silenzi.

        Esiste per un lettore preciso e per una ragione precisa: **il nucleo si
        compone in una funzione sincrona** (`api/handlers_home_space.
        compose_briefing`, condivisa con il contesto della chat), e da
        quando le quattro tabelle scritte a mano non ci sono piu' quel testo ha
        bisogno delle traduzioni a ogni turno. Renderla `async` avrebbe voluto
        dire rendere `async` la composizione del nucleo e i suoi chiamanti --
        cioe' cambiare la forma di mezzo prodotto per una lettura che
        `_prime_state_translations` (allo `startup`) e il suo giro periodico
        hanno gia' fatto.

        **Non va in rete, mai.** Se nessuno ha ancora letto, risponde «non ho
        potuto chiedere» col motivo -- e il lettore lo DICE, invece di mostrare
        un vuoto. E' esattamente la condizione che la spec (§6) pone alla
        cancellazione delle tabelle: si cancella solo se il consumatore sa dire
        «traduzioni non lette».
        """
        if self._resources is None:
            return {"lette": False,
                    "motivo": "le traduzioni degli stati non sono ancora state "
                              "lette da Home Assistant in questa sessione"}
        return {"lette": True, "lingua": self._key[1] if self._key else None,
                "risorse": self._resources}
