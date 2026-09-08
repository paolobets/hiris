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
        if parts[3] == "_":
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
        device_class = None if parts[3] == "_" else parts[3]
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


class PublishedTypes:
    """Cio' che Home Assistant pubblica sui tipi, in QUESTA casa e adesso.

    **Ogni risposta e' etichettata coi tre silenzi**, e la distinzione arriva
    fino a chi legge: `states("light")` su una casa senza `light` risponde
    «ho chiesto una cosa che non esiste», su una casa CON `light` ma senza
    enumerazione risponde «ho chiesto e non c’e'». Sono due fatti diversi, e
    farli collassare in un insieme vuoto e' il difetto che questa classe
    esiste per non commettere: il primo dice che la casa non ha quel tipo, il
    secondo che quel tipo non ha stati enumerabili -- e infatti `sensor` non
    ne ha, misura numeri.

    Porta con se' `(versione_ha, lingua)`: una tabella che non sa di quale
    casa e di quale lingua e' non si sa vecchia, ed e' la stessa disciplina
    che il vocabolario dei tipi impone ai suoi campi importati.
    """

    __slots__ = ("_device_classes", "_domains", "_ha_version", "_language",
                 "_state_classes", "_states")

    def __init__(self, resources, *, ha_version, language) -> None:
        self._domains = published_domains(resources)
        self._device_classes = published_device_classes(resources)
        self._states = published_states(resources)
        self._state_classes = published_state_classes(resources)
        self._ha_version = ha_version
        self._language = language

    @property
    def ha_version(self):
        return self._ha_version

    @property
    def language(self):
        return self._language

    def domains(self) -> dict:
        """I domini caricati. Un elenco vuoto e' un silenzio, non una casa
        senza domini: nessuna installazione di Home Assistant ne ha zero."""
        if not self._domains:
            return undefined(
                "Home Assistant ha risposto senza errore e senza nessun dominio: "
                "la categoria chiesta non e' fra quelle che pubblica")
        return known(self._domains)

    def device_classes(self, domain: str) -> dict:
        if domain not in self._domains:
            return undefined(f"il dominio «{domain}» non e' fra i {len(self._domains)} "
                             "che questa casa ha caricato")
        classes = self._device_classes.get(domain)
        if not classes:
            return absent(f"il dominio «{domain}» non pubblica nessuna `device_class`: "
                          "le sue entita' non si distinguono per classe")
        return known(classes)

    def states(self, domain: str, device_class: str | None = None) -> dict:
        if domain not in self._domains:
            return undefined(f"il dominio «{domain}» non e' fra i {len(self._domains)} "
                             "che questa casa ha caricato")
        if device_class and device_class not in self._device_classes.get(domain, ()):
            return undefined(f"«{device_class}» non e' fra le `device_class` che il "
                             f"dominio «{domain}» pubblica")
        states = self._states.get((domain, device_class))
        if not states:
            return absent(f"il tipo ({domain}, {device_class}) non enumera nessuno "
                          "stato: e' un tipo che misura, non uno che sta in uno stato")
        return known(states)

    def state_classes(self) -> dict:
        if not self._state_classes:
            return absent("questa casa non pubblica nessun valore di `state_class`")
        return known(self._state_classes)


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

    **Dalla fetta del derivato (08/09/2026) la stessa lettura risponde a una
    seconda domanda**: `published()` distilla dalle stesse 801 chiavi cio' che
    questa casa DICHIARA di avere -- 53 domini, gli stati per tipo, le
    `device_class` per dominio, i quattro valori di `state_class`. Non e' una
    seconda lettura e non e' un secondo modulo: e' la stessa risposta guardata
    da un'altra parte, ed e' il motivo per cui i due esiti non possono
    divergere. I due esiti etichettati diventano **tre**, coi tre silenzi in
    cima a questo file.
    """

    def __init__(self, client, *, category: str = STATE_TRANSLATIONS_CATEGORY) -> None:
        self._client = client
        self._category = category
        self._key: tuple[str | None, str | None] | None = None
        self._resources: dict | None = None
        # La distillazione delle stesse risorse (`PublishedTypes`), tenuta
        # accanto a loro e invalidata con loro: e' la stessa tabella guardata
        # da un'altra parte, non una seconda cache con una vita propria che
        # potrebbe restare indietro.
        self._published: PublishedTypes | None = None
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
            # La distillazione segue le risorse: quelle nuove non possono
            # convivere con la lettura vecchia nemmeno per un turno.
            self._published = None
            logger.info("traduzioni degli stati lette da Home Assistant: %d chiavi (%s, HA %s)",
                        len(self._resources), language, ha_version)
        return {"lette": True, "lingua": language, "risorse": self._resources}

    async def published(self, *, ha_version, language) -> dict:
        """Cio' che Home Assistant PUBBLICA sui tipi in questa casa, adesso --
        etichettato coi tre silenzi.

        **Zero chiamate in piu' di `read`**: la stessa risposta, la stessa
        cache, lo stesso lock. Chi vuole rendere uno stato chiama `read`; chi
        vuole sapere cosa questa casa dichiara di avere chiama questa. Due
        domande diverse sulla stessa lettura, non due letture.

        I tre esiti, e sono i tre silenzi della spec (§4):

        - la lettura non e' riuscita -> «non ho potuto chiedere», **col motivo
          dichiarato da chi ha fallito** (il client, non indovinato qui);
        - la lettura e' riuscita e non porta **nessuna** chiave -> «ho chiesto
          una cosa che non esiste»: `frontend/get_translations` non valida
          `category`, e a una categoria inventata risponde `success: true` con
          zero chiavi (misurato). Senza questo ramo un refuso nella categoria
          diventerebbe «questa casa non ha domini»;
        - la lettura e' riuscita -> la tabella, e i «ho chiesto e non c’e'»
          restano da chiedere tipo per tipo a `PublishedTypes`.

        **Un guasto non invalida la tabella buona di prima**: questa funzione
        non ha nessun ramo che azzeri `_resources` o `_published`, e a
        `(versione_ha, lingua)` invariate `read` risponde dalla cache senza
        nemmeno provare a chiamare. Una tabella che c'e' vale piu' di un vuoto
        dichiarato fresco -- la stessa scelta di `topology.rebuild()`.
        """
        report = await self.read(ha_version=ha_version, language=language)
        if not report.get("lette"):
            return unreachable(report.get("motivo"))
        resources = report.get("risorse")
        if not resources:
            return undefined(
                f"la categoria «{self._category}» non e' fra quelle che Home "
                "Assistant pubblica: ha risposto senza errore e con zero chiavi")
        async with self._lock:
            if self._published is None:
                self._published = PublishedTypes(
                    resources, ha_version=ha_version, language=language)
        return known(self._published)
