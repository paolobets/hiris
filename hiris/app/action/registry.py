"""Il registro dei servizi: cosa Home Assistant sa fare, in questa casa.

Non e' un catalogo scritto da noi -- e' lo specchio di `/api/services`. Per
questo copre le integrazioni installate dopo, senza che nessuno tocchi HIRIS:
e' l'invariante «verificare, non insegnare» della spec dell'azione.

Non solleva mai (tranne al primissimo caricamento, vedi `ensure_fresh`): un
registro mai caricato, o caricato da una risposta malformata, risponde `None` a
chi lo interroga. Chi decide cosa dire all'utente e' la verifica, non questo
modulo.

Attenzione a come si legge `servizio()`: il suo `dict` vuoto significa «il
servizio esiste ma non ne conosciamo il dettaglio», che e' diverso da `None`
(«non esiste»). Chi lo interroga confronta con `is None`, mai con la verita'
booleana del risultato.

La forma di `/api/services` presa per buona qui e' una lista di
`{"domain": str, "services": {nome: dettaglio}}`. E' la forma **attesa**, non
ancora misurata su un'installazione vera: per questo ogni chiave e ogni tipo
sono verificati prima dell'uso e una voce che non torna viene saltata invece
di far cadere l'intero aggiornamento.

La verifica arriva **fino ai parametri**, e non si ferma un livello sopra come
faceva prima della revisione della fetta: `fields` viene normalizzato qui
(`_fields`), cosi' che chi legge il registro trovi sempre o una mappa di nomi o
un `None` dichiarato, mai una forma da indovinare. Erano due difetti misurati,
non ipotesi: un `fields` che non fosse una mappa faceva risalire un `TypeError`
fino al modello (`unhashable type: 'dict'` come motivo di un rifiuto), e un
`fields` **a sezioni** -- la forma che Home Assistant >= 2024.6 manda per
parecchi domini core -- faceva rifiutare un parametro legittimo offrendo
`advanced_fields` come «uno di quelli veri».

**`target` non viene toccato, ed e' voluto** (review finale, rilievo CRITICO
①). A differenza di `fields`, che va appiattito per essere letto,
`_detail()` lo lascia esattamente come Home Assistant lo manda -- spreads
`**grezzo`, quindi la chiave sopravvive intera, `None` compreso -- perche' qui
serve il dato grezzo, non una sua interpretazione: e' `action/verification.py` a
decidere cosa significhi «un servizio senza `target`» (vedi
`verifica._declare_target`), non questo modulo. `servizio("light", "turn_on") ==
{"target": {}}` (con) e `servizio("light", "toggle") == {}` (senza -- la chiave non
compare affatto) sono ENTRAMBI casi gia' pinnati da un test (`tests/test_action_registry.py::
test_un_servizio_senza_campi_non_ne_guadagna_uno_finto`).
"""
import logging
import time

from ..proxy.state_translations import known, unreachable

logger = logging.getLogger(__name__)


def _fields(reading) -> dict | None:
    """I parametri di un servizio, appiattiti di un livello.

    Tre esiti, e il terzo e' il motivo per cui questa funzione esiste:

    - **forma piatta** -- `{"brightness_pct": {...}, "transition": {...}}`:
      resta com'e';
    - **forma a sezioni** (Home Assistant >= 2024.6) -- i campi avanzati
      stanno raggruppati: `{"advanced_fields": {"collapsed": true, "fields":
      {"rgbw_color": {...}}}}`. Letta piatta faceva due danni in una frase
      sola: rifiutava `rgbw_color`, che e' un parametro **vero**, e offriva al
      modello `advanced_fields` come parametro -- che il modello avrebbe
      provato, per un secondo rifiuto. Qui la sezione si apre e i suoi campi
      salgono di un livello. Appiattire e' **innocuo dove le sezioni non ci
      sono**: senza un `fields` annidato dentro, non c'e' niente da aprire.
      Un livello solo, di proposito: le sezioni di Home Assistant non si
      annidano, e scendere all'infinito trasformerebbe un parser in
      un'ipotesi.
    - **forma illeggibile** -- `fields` c'e' ma non e' una mappa: `None`.
      `None` NON e' `{}`, ed e' la stessa distinzione che questo modulo usa
      gia' per `servizio()` e `age_seconds()`: `{}` dice «letto: nessun
      parametro» e autorizza a rifiutare un parametro in piu', `None` dice
      «non l'ho potuto leggere» -- e su cio' che non si e' potuto misurare
      non si rifiuta.

    Cosa distingue una sezione da un campo: il valore e' una mappa che
    contiene a sua volta un `fields` che e' una mappa. Il descrittore di un
    campo (`selector`, `required`, `example`, `default`...) non ha un
    `fields`; una sezione ce l'ha per definizione, ed e' li' che stanno i
    nomi veri.
    """
    if not isinstance(reading, dict):
        return None
    piatti: dict = {}
    for name, detail in reading.items():
        internal = detail.get("fields") if isinstance(detail, dict) else None
        if isinstance(internal, dict):
            for nested_name, nested_detail in internal.items():
                if isinstance(nested_name, str):
                    piatti[nested_name] = nested_detail
        elif isinstance(name, str):
            piatti[name] = detail
    return piatti


# --------------------------------------------------------------------------
# IL `filter` DI HOME ASSISTANT: a quali entita' un parametro si applica
# --------------------------------------------------------------------------
#
# Ogni campo di `/api/services` puo' portare un `filter`, ed e' **Home
# Assistant a dichiarare a quali entita' quel parametro si applica** -- non lo
# deduciamo noi. Due forme sole, e sono quelle che lo schema ammette
# (`script/hassfest/services.py:57-66` al tag `2026.9.1`, `vol.Exclusive`):
#
#   filter: {attribute: {supported_color_modes: [color_temp, hs, ...]}}
#   filter: {supported_features: [32]}
#
# Nello YAML del componente i valori sono NOMI (`light.LightEntityFeature.
# EFFECT`); l'API li consegna gia' risolti in interi
# (`homeassistant/helpers/service.py:156-181`, `validate_supported_feature`).
# Misurato su questa casa il 07/09/2026: 52 campi con filtro su 604, 30 per
# capacita' e 22 per attributo, e ogni valore un intero o una stringa -- mai
# una forma composta.
#
# **La regola di confronto non e' inventata qui**: e' quella che il frontend
# di Home Assistant applica per decidere se disegnare il campo
# (`home-assistant/frontend`, tag `20260826.6`, `src/components/
# ha-service-control.ts:386-424` `_filterField` e `:51-59` `attributeFilter`,
# piu' `src/common/entity/supports-feature.ts`):
#
#   - capacita': `(attributi.supported_features & bit) !== 0` per almeno un
#     bit dell'elenco -- una MASCHERA, non un'uguaglianza;
#   - attributo: il nome dev'essere PRESENTE fra gli attributi, e il suo
#     valore -- o, se e' un elenco, almeno un suo elemento -- dev'essere fra
#     quelli ammessi. Un valore che e' un dizionario non corrisponde mai;
#   - fra piu' entita' bersagliate basta che UNA lo accetti (`.some(...)`).
#     Vale anche per il rifiuto: si dice di no solo quando NESSUNA lo accetta.
#
# **Perche' `field_applies` ha TRE esiti e non due.** `None` non e' «no»:
# significa «non l'ho potuto misurare» -- il dettaglio non e' leggibile, il
# filtro e' in una forma che non conosciamo, o dell'entita' non abbiamo nessun
# attributo. E' la stessa disciplina che questo modulo usa gia' per `fields`
# (`{}` e `None` non sono la stessa cosa) e che `action/verification.py`
# dichiara per i parametri: **su cio' che non si e' potuto misurare non si
# rifiuta**, perche' rifiutare una chiamata legittima e' peggio che lasciar
# passare un valore che Home Assistant rigetta con un errore chiaro.


def field_filter(reading) -> dict | None:
    """Il `filter` di un campo, o `None` se non ne ha uno leggibile.

    Sta qui e non nella verifica per la stessa ragione di `_fields`: questo
    modulo e' l'unico posto in cui la forma di `/api/services` va capita. Chi
    lo interroga riceve un dizionario o un `None`, mai una forma da
    indovinare.
    """
    if not isinstance(reading, dict):
        return None
    reading = reading.get("filter")
    return reading if isinstance(reading, dict) else None


def _attribute_matches(admitted, value) -> bool:
    """La regola di `attributeFilter` del frontend, trascritta.

    Un elenco corrisponde se ALMENO UN suo elemento e' fra gli ammessi (una
    luce `[color_temp, hs]` accetta un parametro che chiede `hs`); un valore
    singolo corrisponde se e' lui stesso fra gli ammessi; un dizionario non
    corrisponde mai -- e' la riga `return false` del sorgente, non una
    dimenticanza.
    """
    if not isinstance(admitted, list):
        return False
    if isinstance(value, (list, tuple)):
        return any(item in admitted for item in value)
    if isinstance(value, dict):
        return False
    return value in admitted


def field_applies(reading, attributes) -> bool | None:
    """Se questo parametro si applica a un'entita' con QUESTI attributi.

    `True` sempre quando il campo non dichiara nessun filtro: e' Home
    Assistant a dire quando un parametro e' ristretto, e il silenzio significa
    «vale per tutte».

    `None` -- «non l'ho potuto misurare» -- in quattro casi, e nessuno dei
    quattro e' un no:

    1. il dettaglio del campo non e' un dizionario;
    2. degli attributi dell'entita' non sappiamo niente (`attributes` vuoto o
       non leggibile). E' il caso che protegge di piu': uno specchio che non
       ha ancora visto quell'entita' non deve far dire «questa luce non fa
       colore»;
    3. il filtro non porta nessuna delle due chiavi note -- una forma futura
       non deve poter far rifiutare cio' che oggi passa;
    4. il filtro chiede una capacita' e l'entita' non dichiara nessun
       `supported_features` leggibile. **Qui ci si scosta da Home Assistant di
       proposito**: il frontend nasconderebbe il campo (`undefined & bit` vale
       zero in JavaScript), noi non rifiutiamo -- nascondere un cursore e
       negare un comando non costano la stessa cosa, e un'integrazione che non
       manda quel numero non e' un'integrazione che non sa fare la cosa.
    """
    reading = field_filter(reading)
    if reading is None:
        return True
    if not isinstance(attributes, dict) or not attributes:
        return None
    known = False
    features = reading.get("supported_features")
    if isinstance(features, list):
        declared = attributes.get("supported_features")
        # `bool` e' una sottoclasse di `int`: senza l'esclusione `True`
        # passerebbe per una maschera di bit. Stessa guardia di
        # `topology.decoded_capabilities`.
        if isinstance(declared, int) and not isinstance(declared, bool):
            known = True
            if any(isinstance(bit, int) and not isinstance(bit, bool) and declared & bit
                   for bit in features):
                return True
    per_attribute = reading.get("attribute")
    if isinstance(per_attribute, dict):
        known = True
        for name, admitted in per_attribute.items():
            if name in attributes and _attribute_matches(admitted, attributes[name]):
                return True
    return False if known else None


def _detail(reading) -> dict:
    """Il dettaglio di un servizio, coi suoi `fields` gia' normalizzati.

    Un dettaglio che non e' un dizionario diventa `{}` -- «il servizio esiste,
    non sappiamo com'e' fatto» -- e non fa cadere il dominio intero. Un
    dettaglio senza `fields` resta tale e quale: aggiungere una chiave che
    Home Assistant non ha mandato sarebbe insegnare invece di specchiare.
    """
    if not isinstance(reading, dict):
        return {}
    if "fields" not in reading:
        return reading
    return {**reading, "fields": _fields(reading["fields"])}


class ServiceRegistry:
    def __init__(self, max_age_s: float = 300.0) -> None:
        self._per_domain: dict[str, dict[str, dict]] = {}
        self._caricato_a: float | None = None
        self._max_age_s = max_age_s
        # Il segno di «rileggi appena serve», messo da `invalidate()`. E' un
        # campo SUO e non un azzeramento di `_caricato_a`: quello significa
        # «mai letto» (vedi `empty()`), e fingerlo farebbe SOLLEVARE
        # `ensure_fresh` al primo rinfresco fallito invece di tenere il
        # registro vecchio -- cioe' il contrario esatto di cio' che quel
        # metodo dichiara di volere.
        self._da_rileggere = False

    async def refresh(self, ha_client) -> None:
        """Rilegge `/api/services` e **sostituisce** cio' che sapevamo.

        Sostituisce, non fonde: un'integrazione disinstallata deve sparire
        anche da qui, altrimenti il registro smetterebbe di essere lo
        specchio di HA e diventerebbe un archivio di cio' che un tempo era
        possibile.
        """
        reading = await ha_client.get_services()
        new: dict[str, dict[str, dict]] = {}
        for entry in reading or []:
            if not isinstance(entry, dict):
                continue
            domain = entry.get("domain")
            services = entry.get("services")
            if not isinstance(domain, str) or not isinstance(services, dict):
                continue
            new[domain] = {n: _detail(d)
                              for n, d in services.items() if isinstance(n, str)}
        self._per_domain = new
        self._caricato_a = time.monotonic()
        self._da_rileggere = False
        logger.info("registro servizi: %d domini, %d servizi",
                    len(new), sum(len(s) for s in new.values()))
        # Una risposta che c'era e da cui non si e' capito NIENTE e' l'unico
        # esito che il resto del prodotto non sa raccontare: l'utente si sente
        # dire «non sono riuscito a leggerlo, riprova fra poco» per sempre, e
        # nel log c'era solo un `INFO: 0 domini, 0 servizi` che assomiglia a
        # una casa senza servizi. E' il fallimento numero 1 del foglio delle
        # prove: qui diventa una diagnosi invece di un silenzio.
        if reading and not new:
            logger.warning("registro servizi: la risposta di /api/services non era "
                           "vuota (%s voci) ma non se ne e' capita nessuna -- la sua "
                           "forma non e' quella attesa (lista di {domain, services})",
                           len(reading) if isinstance(reading, list) else "?")

    async def ensure_fresh(self, ha_client) -> None:
        """Ricarica se serve. Un guasto NON svuota cio' che sapevamo.

        Un registro vecchio e' meno peggio di un registro assente: col primo
        HIRIS puo' ancora rifiutare un servizio che non esiste, col secondo
        non puo' verificare niente. Se il rinfresco fallisce si logga e si
        tiene il vecchio -- e `age_seconds()` resta grande, cosi' chi vuole
        saperlo puo' chiederlo.

        Al **primo** caricamento non c'e' nessun vecchio da proteggere:
        li' il guasto risale, perche' un registro mai caricato e un registro
        caricato e vuoto rispondono uguale a chi li interroga, e chi chiama
        deve poterli distinguere.
        """
        age = self.age_seconds()
        if age is not None and age < self._max_age_s and not self._da_rileggere:
            return
        try:
            await self.refresh(ha_client)
        except Exception as error:
            if self.empty():
                raise
            logger.warning("registro servizi: rinfresco fallito (%s: %s), "
                           "tengo quello di %.0fs fa",
                           type(error).__name__, error, age or 0.0)

    def invalidate(self) -> None:
        """«Rileggi appena serve», non «dimentica».

        Lo chiama chi ascolta `service_registered`/`service_removed`. Azzera
        solo l'ETA', non il contenuto: fra l'evento e la rilettura HIRIS deve
        poter ancora verificare qualcosa, e un registro assente e' peggio di
        uno vecchio -- la stessa ragione scritta in `ensure_fresh`, applicata
        al caso opposto.

        E non rilegge da se': installare un'integrazione emette una raffica di
        eventi, e una lettura per ognuno sarebbe una tempesta per un dato che
        serve solo al prossimo comando.
        """
        self._da_rileggere = True

    def service(self, domain: str, name: str) -> dict | None:
        """Il dettaglio di un servizio, o `None` se qui non esiste.

        Quando c'e', il suo `fields` -- se c'e' -- e' gia' normalizzato da
        `_fields`: o una mappa di nomi di parametro, o `None` («c'era, ma in
        una forma che non so leggere»). Chi lo interroga non deve piu'
        indovinare la forma, ed e' l'unico posto in cui quella forma va
        capita.
        """
        return self._per_domain.get(domain, {}).get(name)

    def domains(self) -> list[str]:
        return sorted(self._per_domain)

    def services_for(self, domain: str) -> list[str]:
        return sorted(self._per_domain.get(domain, {}))

    def age_seconds(self) -> float | None:
        """Da quanti secondi il registro e' quello che e'. `None` = mai letto."""
        if self._caricato_a is None:
            return None
        return time.monotonic() - self._caricato_a

    def empty(self) -> bool:
        """Vero finche' nessun caricamento e' mai riuscito.

        Non dice «zero servizi»: dice «mai letto». Un `/api/services` che
        rispondesse una lista vuota lascerebbe questo `False`.
        """
        return self._caricato_a is None


# --------------------------------------------------------------------------
# COSA QUESTO REGISTRO DICE SUI TIPI, e non solo sui singoli servizi
# --------------------------------------------------------------------------
#
# Il registro dei servizi non serve solo a verificare una chiamata: **e' la
# seconda fonte viva dell'anagrafe dei tipi** (spec §4, C11 e C13), e costa
# zero chiamate nuove -- e' gia' in memoria, e si invalida gia' da se' sugli
# eventi `service_registered`/`service_removed` (`proxy/ha_client.py:68`).
#
# Due materie, misurate sulla casa vera l'08/09/2026 (HA `2026.9.1`, 84 domini
# di servizio, 604 campi):
#
#   bit di capacita' per dominio   16 domini bersaglio, `media_player` 22
#                                  valori distinti, `cover` 10
#   domini che si accendono        16: automation, camera, climate, cover, fan,
#                                  homeassistant, humidifier, input_boolean,
#                                  light, media_player, remote, script, siren,
#                                  switch, valve, water_heater
#
# **LA TRAPPOLA, ed e' misurata.** I valori che il registro porta sono
# COMBINATI, non singoli: `cover.toggle` dichiara `supported_features: [3]`,
# che e' `OPEN|CLOSE`; `media_player.media_play_pause` dichiara `[16385]`, che
# e' `PLAY|PAUSE`; ci sono anche `[48]` (`OPEN_TILT|CLOSE_TILT`), `[384]`,
# `[3]` su `siren` e su `valve`. Confrontarli tali e quali con una tabella di
# bit singoli non trova NIENTE e non fallisce: dice «questo dominio non ha
# capacita' che conosciamo» su un dominio che le ha tutte. **Si scompone
# prima**, sempre, e la scomposizione sta qui -- non in ogni chiamante.
#
# **Il dominio giusto e' quello del BERSAGLIO, non quello del servizio**, e
# anche questo e' misurato: `reolink.ptz_move` dichiara
# `target.entity[0] = {integration: reolink, domain: [button],
# supported_features: [2]}`. Attribuirlo a `reolink` -- che non e' un dominio
# di entita' -- perderebbe l'unica capacita' che questa casa dichiara su
# `button`, e la perderebbe in silenzio. Dove il bersaglio non dichiara nessun
# dominio non si attribuisce a nessuno: sulla casa vera non capita mai (zero
# casi su 604 campi), e indovinare il dominio del servizio sarebbe la stessa
# bugia detta al contrario.

#: I servizi che, presi insieme, dicono «questo dominio si accende e si
#: spegne». Sono i nomi che Home Assistant registra, non una nostra idea di
#: interruttore: `turn_on` **e** `turn_off`, oppure `toggle`.
_SWITCH_SERVICES = ("turn_on", "turn_off")
_TOGGLE_SERVICE = "toggle"


def single_bits(value) -> frozenset[int]:
    """Un valore di `supported_features` -> i bit che lo compongono.

    `3` -> `{1, 2}`, `16385` -> `{1, 16384}`, `48` -> `{16, 32}`. Un bit solo
    resta se stesso.

    `bool` e' una sottoclasse di `int`: senza l'esclusione, `True` diventerebbe
    il bit 1 e `False` un insieme vuoto -- la stessa guardia che
    `field_applies` qui sopra e `topology.decoded_capabilities` gia' hanno, per
    la stessa ragione. Zero e i negativi non portano nessun bit: Home Assistant
    non ne emette, e inventarne uno sarebbe una capacita' che non esiste.
    """
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return frozenset()
    return frozenset(1 << position for position in range(value.bit_length())
                     if value >> position & 1)


def _target_domains(detail) -> frozenset[str]:
    """I domini di entita' che questo servizio dichiara di bersagliare."""
    if not isinstance(detail, dict):
        return frozenset()
    target = detail.get("target")
    if not isinstance(target, dict):
        return frozenset()
    entities = target.get("entity")
    if isinstance(entities, dict):
        entities = [entities]
    if not isinstance(entities, list):
        return frozenset()
    domains: set[str] = set()
    for entry in entities:
        if not isinstance(entry, dict):
            continue
        declared = entry.get("domain")
        if isinstance(declared, str):
            domains.add(declared)
        elif isinstance(declared, list):
            domains.update(name for name in declared if isinstance(name, str))
    return frozenset(domains)


def _bits_declared_by(detail) -> frozenset[int]:
    """I bit che questo servizio nomina, **gia' scomposti**, dalle due sedi in
    cui Home Assistant li mette.

    1. `target.entity[*].supported_features` -- «questo servizio si applica
       alle entita' che sanno fare X»;
    2. `fields[*].filter.supported_features` -- «questo PARAMETRO si applica
       alle entita' che sanno fare X». `fields` e' gia' appiattito da
       `_fields`, quindi le sezioni di Home Assistant >= 2024.6 sono gia'
       aperte e nessun parametro avanzato si perde qui.
    """
    bits: set[int] = set()
    if not isinstance(detail, dict):
        return frozenset()
    target = detail.get("target")
    entities = target.get("entity") if isinstance(target, dict) else None
    if isinstance(entities, dict):
        entities = [entities]
    for entry in entities if isinstance(entities, list) else ():
        if not isinstance(entry, dict):
            continue
        declared = entry.get("supported_features")
        for value in declared if isinstance(declared, list) else ():
            bits |= single_bits(value)
    fields = detail.get("fields")
    for reading in fields.values() if isinstance(fields, dict) else ():
        per_field = field_filter(reading)
        declared = per_field.get("supported_features") if per_field else None
        for value in declared if isinstance(declared, list) else ():
            bits |= single_bits(value)
    return frozenset(bits)


def _capability_bits(registry) -> dict[str, frozenset[int]]:
    """Dominio di entita' -> i bit di capacita' che questa casa dichiara.

    Una vista sul registro, non un secondo elenco: si ricostruisce a ogni
    domanda dalle stesse righe che `service()` restituisce, cosi' non puo'
    restare indietro rispetto a un'integrazione installata cinque minuti fa.
    """
    per_domain: dict[str, set[int]] = {}
    for service_domain in registry.domains():
        for name in registry.services_for(service_domain):
            detail = registry.service(service_domain, name)
            bits = _bits_declared_by(detail)
            if not bits:
                continue
            for domain in _target_domains(detail):
                per_domain.setdefault(domain, set()).update(bits)
    return {domain: frozenset(bits) for domain, bits in per_domain.items()}


def capability_bits(registry) -> dict:
    """I bit di capacita' per dominio, etichettati coi tre silenzi.

    `unreachable` quando il registro non e' mai stato letto: un registro
    assente e un registro senza bit rispondono uguale a chi guarda un
    dizionario vuoto, e sono due fatti opposti -- lo stesso motivo per cui
    `ServiceRegistry.empty()` esiste.
    """
    if registry is None:
        return unreachable("il registro dei servizi non e' collegato a questa istanza")
    if registry.empty():
        return unreachable("il registro dei servizi non e' mai stato letto da "
                           "Home Assistant")
    return known(_capability_bits(registry))


# `capability_bits_of` (i bit di UN dominio solo) e' stata cancellata (R6,
# revisione del tratto v3.23.0..HEAD, 08/09/2026): nessun chiamante di
# produzione la usava, solo le prove. `capability_bits()` qui sopra -- usata
# da `scripts/istantaneo_pubblicato.py` -- resta la sola porta viva; chi
# vuole i bit di un dominio solo fa `capability_bits(registro)["valore"].
# get(dominio)` e distingue da se' «letto» da «non letto» sull'esito di
# `capability_bits`, senza bisogno di una seconda funzione mai chiamata.


def switchable_domains(registry) -> dict:
    """I domini che Home Assistant dichiara accendibili -- 16, misurati.

    **E' una DERIVAZIONE, non un giudizio**, e non sostituisce il nostro: la
    spec (§4) lo dice per esteso -- questa lista guadagna `automation`,
    `script`, `input_boolean`, `camera`, `remote`, `siren` e `homeassistant`,
    dove `on` significa «abilitata» e non «accesa», e perde `vacuum`, che Home
    Assistant comanda con `start`/`stop`. Serve a SORVEGLIARE il giudizio, e
    chi la legge come un elenco di interruttori riapre il difetto che
    `briefing._EVENT_DOMAINS` documenta di aver gia' pagato.

    **Sono domini di SERVIZIO**, non di entita': `homeassistant` sta qui e non
    e' un dominio di entita'. E' un fatto della derivazione, non un difetto --
    ed e' una delle sette eccezioni che il censore dovra' motivare.
    """
    if registry is None:
        return unreachable("il registro dei servizi non e' collegato a questa istanza")
    if registry.empty():
        return unreachable("il registro dei servizi non e' mai stato letto da "
                           "Home Assistant")
    domains = set()
    for domain in registry.domains():
        names = set(registry.services_for(domain))
        if _TOGGLE_SERVICE in names or set(_SWITCH_SERVICES) <= names:
            domains.add(domain)
    return known(frozenset(domains))
