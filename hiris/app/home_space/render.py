"""La resa: una funzione per genere di oggetto (Tappa 9, «Una resa per
oggetto»; piano della Tappa 4, Task 7-8).

Ogni oggetto della casa che HIRIS mostra -- al modello, a una pagina, a un
servizio firmato -- esce da UNA funzione di questo modulo, col vocabolario
dei campi (`field_vocabulary`) e a una delle tre profondita' (corta, media,
completa). Le porte chiamano la resa e inoltrano il suo dizionario: non lo
compongono (R3, `tests/test_resa_unica.py`).
"""
from __future__ import annotations

from ..action.registry import field_applies
from ..proxy.entity_cache import (
    ASSUMABLE,
    CAPABILITIES,
    UNINTERPRETED,
    VALUES,
    disclosable_attributes,
    group_members,
)
from ..proxy.state_translations import TABLE_MISSING_SILENCES
from .ha_vocabulary import domain_of
from .topology import (
    HVAC_ACTION_ATTRIBUTE,
    Mirror,
    categories_with_name,
    clean_text,
    decoded_capabilities,
    labels_with_id,
    live_first,
    readable_state,
    visibility_classes,
)
from .type_judgments import MEANING_FIELD, TypeJudgments, type_subject
from .type_vocabulary import REPO_JUDGMENTS

# Chiavi che `entity_cache._to_minimal` mette nello STESSO dizionario grezzo
# di `options` per ragioni di trasporto (arrivano dalla stessa proiezione,
# dominio-agnostiche) ma che hanno gia' una porta propria, DECODIFICATA:
# `supported_features` -> `capacita'` (`decoded_capabilities`, sotto),
# `assumed_state` -> `stato_presunto`. Uscire ANCHE dentro il dizionario
# grezzo di `_view_entity` (`attributi`) le farebbe uscire due volte -- un
# numero senza significato per chi non ha una tabella (`supported_features:
# 27` su un sensore), o un doppione per chi ce l'ha (`capacita': [...]` E
# `attributi: {"supported_features": 36}` per la stessa cosa). Misurato in
# produzione dalla review indipendente di questa fetta: la catena vera
# (`_to_minimal` -> `live_mirror` -> `view`) lo faceva davvero, e nessuna
# prova se ne accorgeva perche' tutte costruivano `reported_attributes` a
# mano, saltando `_to_minimal`.
_RAW_ATTRIBUTES_WITH_THEIR_OWN_DOOR = frozenset({"supported_features", "assumed_state"})

# Come si chiamano le tre ceste degli attributi NEL TESTO CHE IL MODELLO LEGGE.
#
# `campo_di_manovra` e non `capacita'`: `detail["capacita"]` esiste gia', ed e'
# un'altra cosa -- i bit di `supported_features` decodificati in verbi («sa
# fare la transizione», «sa gli effetti»). Le capacita' che arrivano dagli
# ATTRIBUTI sono invece i limiti e gli elenchi entro cui si comanda:
# `hvac_modes`, `min_temp`/`max_temp`, `effect_list`, `options`, `source_list`.
# Chiamarle entrambe «capacita'» sarebbe due cose diverse dette con una parola
# sola, il difetto che questa fetta esiste per non ripetere -- e si separa
# QUI, alla fonte del nome, non a valle.
_BASKET_NAMES = {
    CAPABILITIES: "campo_di_manovra",
    # «Cosa puo' assumere» non e' «cosa le si puo' imporre», e con una parola
    # sola sarebbero la stessa cosa: `sensor.options` e `select.options` si
    # chiamano uguale e Home Assistant li classifica uguale. La separazione e'
    # alla FONTE (`type_vocabulary._ASSUMABLE_ATTRIBUTES`), qui si legge solo
    # il nome che ne esce -- e non e' una sfumatura di `campo_di_manovra`, e'
    # il suo opposto per chi comanda.
    ASSUMABLE: "valori_che_puo_assumere",
    VALUES: "valori",
    UNINTERPRETED: "non_interpretati",
}

#: La cesta che dice cosa e' stato trattenuto, e perche'. Non i valori: i nomi
#: e la ragione. Vedi `entity_cache.withheld_credentials`.
_WITHHELD_BASKET = "trattenuti"
#: Esposto per il filtro di riservatezza: il nome della cesta che raccoglie
#: cio' che non passa la porta al modello.
WITHHELD_BASKET = _WITHHELD_BASKET


def _enrich_entity(entity_detail: dict, entry: dict, mirror: Mirror,
                   label_lookup: dict[str, str] | None = None,
                   category_lookup: dict[tuple[str, str], str] | None = None,
                   translations: dict | None = None) -> dict:
    """LA PORTA UNICA per tutto cio' che si aggiunge a un'entita'.

    Arricchisce `entity_detail` con cio' che lo SPECCHIO VIVO sa e il
    registro no (l'unita' di misura, la classe) e con cio' che il
    registro sa e la proiezione lascerebbe indietro (la piattaforma, le
    etichette e le categorie).

    Prende la VOCE del registro, non il solo `entity_id`: e' il cambiamento
    che rende questa porta capace di portare anche i campi dichiarati. Con il
    solo id, chi aggiungeva un campo nuovo era costretto a scriverlo nel
    proprio ramo -- ed e' esattamente quello che era appena successo con
    `piattaforma` ed `etichette`, uscite da una porta su tre: lo stesso
    difetto (I1) per cui questa funzione era nata.

    Il NOME non passa di qui: lo scrive chi costruisce la riga, con
    `topology.live_name` (D1 «vivo», 04/10/2026). Fino a quel giorno questa
    funzione aggiungeva `nome_dedotto` -- il `friendly_name` -- solo quando il
    registro non aveva un nome, mentre `search` dava il `friendly_name`
    sempre: due nomi per la stessa entita' da due porte.

    `unita`: `_to_minimal`
    la conserva (`proxy/entity_cache.py`) e nessuno la rileggeva, cosi' il
    modello riceveva `72` senza sapere se fossero gradi Celsius o Fahrenheit.
    L'unita' VIVA vince su quella del registro: Home Assistant converte le
    unita' **solo alla prima aggiunta del sensore**, quindi il registro puo'
    portare quella vecchia mentre lo specchio porta quella che HA sta usando
    adesso. La chiave compare solo quando c'e' un'unita': una lampada non ne
    ha, e `unita: null` su ogni luce sarebbe rumore in ogni risposta.

    Condivisa fra i TRE rami di `view` che elencano entita' (I1, review
    finale): prima di quel fix solo `_view_entity` applicava il nome dedotto,
    e le altre due porte mostravano `nome: null` secco. L'unita' entra da
    questa porta unica, per non ripetere quella storia.

    `capacita` e `stato_presunto` vengono dallo SPECCHIO VIVO come `unita`, e
    per la stessa ragione: `_to_minimal` li conserva gia'
    (`proxy/entity_cache.py`), e nessun lettore li metteva davanti a chi
    compone la risposta -- vedi i due commenti sotto, accanto a dove
    escono davvero."""
    entity_id = entry.get("id")
    unit = live_first(entry.get("unita"), mirror.units.get(entity_id))
    if unit:
        entity_detail["unita"] = unit
    # La CLASSE: dallo specchio vivo, perche' il registro delle entita' non la
    # manda affatto (`topology.live_first`). Prima questa riga usciva
    # `null` su ogni entita' della casa, e con lei taceva tutto il vocabolario
    # dei significati.
    device_class = live_first(entry.get("classe"), mirror.classes.get(entity_id))
    if device_class:
        entity_detail["classe"] = device_class
    # Lo stato IN PAROLE, accanto al valore grezzo -- mai al posto suo:
    # `stato` e' il fatto, `readable_state` e' l'interpretazione, e non si
    # sovrascrivono.
    #
    # Senza, `view` rispondeva `on` e basta: un allagamento aveva la forma di
    # una lampadina accesa. Il digesto lo rendeva gia', ma `view` e' la
    # porta che il modello usa quando la domanda e' PRECISA, o quando il
    # digesto ha tagliato, o quando l'entita' e' `config`/`diagnostic` e nel
    # digesto non entra affatto. **La fonte e' la stessa** -- le traduzioni che
    # Home Assistant pubblica, lette una volta e tenute in cache: due tabelle
    # sarebbero due significati, e fino all'08/09/2026 erano scritte a mano.
    #
    # Il DOMINIO e l'`hvac_action` (dallo specchio vivo, mai dal registro:
    # `topology.live_first` vale anche qui) alimentano il solo caso in
    # cui uno stato grezzo mente da solo -- un termostato IMPOSTATO su
    # riscaldamento e FERMO che si legge «heat» com'e' il difetto misurato dal
    # proprietario (2026-08-25, `topology.readable_state`). Passati anche
    # quando l'entita' non e' un termostato: `readable_state` li ignora per
    # ogni altro dominio, e ricalcolarli qui una volta e' piu' semplice che
    # farlo condizionale.
    value = entity_detail.get("stato")
    # `disclosable_attributes` e non una lettura diretta: lo specchio porta
    # gli attributi divisi in ceste (`entity_cache.inherited_attributes`), e
    # chi cerca un attributo per nome non deve sapere in quale sta -- ne'
    # inciampare nelle
    # credenziali, che di qui non passano mai.
    attributes = disclosable_attributes(mirror.attributes.get(entity_id))
    if value is not None:
        hvac_action = attributes.get(HVAC_ACTION_ATTRIBUTE)
        rendered = readable_state(
            value, domain=domain_of(entity_id),
            device_class=entity_detail.get("classe"), hvac_action=hvac_action,
            translations=translations)
        if rendered.get("letto"):
            entity_detail["stato_leggibile"] = rendered["valore"]
        elif rendered.get("silenzio") in TABLE_MISSING_SILENCES:
            # **Il vuoto non si consegna, il motivo si'.** Fino all'08/09/2026
            # una tabella scritta a mano rispondeva sempre, quindi questo ramo
            # non poteva esistere; adesso la fonte e' Home Assistant e puo'
            # tacere -- e «non ho potuto leggere le traduzioni» e «questo stato
            # non ha resa» sono due fatti diversi, che chi legge deve poter
            # distinguere invece di trovarsi una chiave in meno e nessuna
            # spiegazione. Lo `stato` grezzo resta dov'e': e' il fatto.
            #
            # **Solo i due silenzi che riguardano la TABELLA**, e il perche' e'
            # misurato sulla casa vera (08/09/2026): con le traduzioni lette per
            # intero, 431 entita' su 841 -- ogni `sensor`, ogni `number`, ogni
            # `select` -- non hanno una resa e non devono averla, perche'
            # MISURANO invece di stare in uno stato. Dichiararle una per una
            # avrebbe messo 431 blocchi di scusa dentro le risposte di `view`
            # per dire ogni volta la stessa cosa non-notizia, contro la legge di
            # questo prodotto («una chiave senza niente da dire non esce»). La
            # distinzione non si perde, e si legge come proprio qui, dentro
            # `_enrich_entity`: la chiave ASSENTE con lo
            # `stato` grezzo significa «questo stato non ha resa, e Home
            # Assistant stesso mostrerebbe il grezzo»; la chiave PRESENTE
            # significa «non ho potuto chiedere», col motivo dentro.
            entity_detail["stato_non_reso"] = {
                "silenzio": rendered.get("silenzio"),
                "motivo": rendered.get("motivo"),
            }
    # L'integrazione che la fornisce (hue, zwave_js, template): dice perche'
    # una cosa non risponde e cosa le si puo' chiedere.
    platform = (entry.get("piattaforma") or "").strip()
    if platform:
        entity_detail["piattaforma"] = platform
    # `capacita`: COSA UN'ENTITA' SA FARE, decodificato da `supported_features`
    # (`decoded_capabilities`, `topology.py` -- tabelle verificate alla fonte,
    # per dominio). E' il guadagno vero di questa fetta: 181 entita' su 834
    # (misurato il 06/09/2026) lo dichiarano, e la conoscenza non lo citava
    # in NESSUN punto prima d'ora.
    #
    # Solo quando la decodifica produce qualcosa: 653 entita' su 834 non
    # hanno `supported_features` affatto, e una tabella senza fonte per il
    # dominio non decodifica niente -- `capacita: []` (o peggio, `null`) su
    # ognuna sarebbe il rumore che seppellisce le 181 dove c'e' davvero.
    # Stessa disciplina di `unita`/`categoria` due righe sopra.
    capabilities = decoded_capabilities(domain_of(entity_id), attributes.get("supported_features"))
    if capabilities:
        entity_detail["capacita"] = capabilities
    # `stato_presunto`: Home Assistant lo manda SOLO quando e' vero
    # (`assumed_state`, verificato alla fonte -- vedi `entity_cache._to_minimal`).
    # Leggerlo quando c'e' costa zero, ma su questa casa non e' MAI arrivato
    # (0 entita' su 834, misurato il 06/09/2026): non e' -- e non diventa,
    # scrivendo questa riga -- il fondamento su cui HIRIS regge la certezza
    # del dato in generale.
    if attributes.get("assumed_state"):
        entity_detail["stato_presunto"] = True
    # NASCOSTA e CATEGORIA: fuori dalle gestioni, dentro la conoscenza.
    #
    # Il digesto conta le nascoste e scrive «esistono, e `view` le riporta se
    # gliele chiedi» -- una promessa che `view` non poteva mantenere, perche'
    # il campo non usciva da nessuna porta. Alla domanda «quali sono?» il
    # modello o si contraddiceva o inventava.
    #
    # Solo quando sono vere: `nascosta: false` su ogni entita' di una casa da
    # trecento sarebbe rumore in ogni risposta, e `categoria: null` pure.
    #
    # Dalla regola del fuori (`topology.visibility_classes`, B-01): la causa
    # della classe `servizio` E' l'`entity_category`.
    outside = dict(visibility_classes(entry))
    if "nascosta" in outside:
        entity_detail["nascosta"] = True
    if outside.get("servizio"):
        entity_detail["categoria"] = outside["servizio"]
    # `regola` NON esce da questa porta -- review indipendente (Task 5,
    # rigiro): questa funzione e' condivisa da `_view_area`/`_view_device`
    # (elencano entita' a decine) E da `_view_entity` (una sola). Un
    # dispositivo con 53 sensori diagnostici (misurato il 07/09/2026: "Home
    # Assistant", 55 entita' vive) ripeterebbe la STESSA stringa 53 volte in
    # un'unica vista -- ~18 KB, quasi 4.500 token identici che seppellirebbero
    # il resto della vista. Stessa decisione, stessa ragione di `attributi`
    # (sotto in `_view_entity`): solo sul dettaglio di UNA entita' sola.
    _add_categories(entity_detail, entry, category_lookup or {})
    return _add_labels(entity_detail, entry, label_lookup or {})


def _add_categories(detail: dict, entry: dict,
                   category_lookup: dict[tuple[str, str], str]) -> dict:
    """L'altra tassonomia scritta a mano dall'utente in Home Assistant.

    Le categorie stanno alle etichette come una cartella sta a un post-it:
    «Luci esterne», «Vacanza», «Da rifare». HIRIS leggeva il loro registro con
    QUATTRO comandi WebSocket a ogni ricostruzione dell'anagrafe -- uno per
    ambito -- e non le faceva uscire da nessuna porta; l'assegnazione
    per-entita', che arriva GRATIS dentro la risposta del registro delle
    entita' (`RegistryEntry.as_partial_dict`, verificato sul sorgente di HA),
    non la salvava nemmeno. Costo pieno, resa zero.

    Escono col NOME, non col `category_id`: l'unione la fa
    `topology.categories_with_name`, la stessa che usa l'indice dei nomi.
    Senza, HIRIS riferirebbe all'utente un identificativo che l'utente non ha
    mai scritto -- ed e' la trappola gia' pagata una volta con le etichette.

    La forma e' `{ambito: nome}` e non una lista di nomi: l'ambito
    (`automation`, `script`, `scene`, `helpers`) fa parte dell'identita' della
    categoria, e due omonime in ambiti diversi sono due cose diverse.

    Da NON confondere con `categoria` (singolare), che e' l'`entity_category`
    di Home Assistant -- `config` o `diagnostic`, decisa dall'integrazione.

    Compare solo quando ce n'e' almeno una: `categorie: {}` su ogni cosa
    sarebbe rumore in ogni risposta e -- peggio -- indistinguibile da un
    registro delle categorie caduto. Stessa disciplina di `etichette`.
    """
    categories = categories_with_name(entry, category_lookup)
    if categories:
        detail["categorie"] = categories
    return detail


def _add_labels(detail: dict, entry: dict, label_lookup: dict[str, str]) -> dict:
    """Le etichette che l'utente ha scritto a mano in Home Assistant.

    Sono il significato piu' DICHIARATO che esista in quella casa -- «inverno»,
    «da controllare», «piano di sotto» -- e HIRIS le leggeva, le salvava, le
    metteva perfino nell'albero di `hierarchy()`, senza farle uscire da nessuna
    porta. Un'etichetta che non porta a niente costringe l'utente a ripetere a
    parole cio' che aveva gia' dichiarato una volta.

    Escono col NOME protagonista, col `label_id` accanto come dato
    ACCESSORIO -- `Nome (id: X)`, la stessa forma di `topology.name_with_id`
    (T8, R2: fino a questa fetta il `label_id` non usciva da NESSUNA porta,
    eppure `esegui(bersaglio.etichette=[...])` lo pretende -- il vicolo cieco
    piu' radicale della famiglia, docs/design/2026-08-20-i-riferimenti.md).
    La scelta di leggibilita' di questo modulo NON cambia: la parentesi entra
    solo perche' l'id serve, non al posto del nome. L'unione la fa
    `topology.label_names`, la stessa che usa l'indice dei nomi
    (`memory/resolver.py::costruisci_indice`).

    Compare solo quando ce n'e' almeno una: `etichette: []` su ogni cosa
    sarebbe rumore in ogni risposta e -- peggio -- indistinguibile da un
    registro delle etichette caduto. Stessa disciplina di `unita`.
    """
    labels = labels_with_id(entry, label_lookup)
    if labels:
        detail["etichette"] = labels
    return detail



# --------------------------------------------------------------------------
# I COMANDI: cosa si puo' chiedere a QUESTA entita', e con quali limiti
# --------------------------------------------------------------------------
#
# **Il buco che chiude** (spec §13.2, misurato il 07/09/2026): HIRIS ha il
# registro dei servizi, lo tiene in memoria e lo invalida da se' sugli eventi
# `service_registered`/`service_removed` -- **e lo usava solo per RIFIUTARE**.
# Nessuna porta mostrava al modello i parametri di `light.turn_on`: lui li
# scopriva sbagliando, un rifiuto alla volta. Sapevamo la risposta e la
# usavamo solo per dire di no.
#
# **Perche' un campo di `view` e non uno strumento nuovo.** Erano le due forme
# possibili, e la scelta ha tre ragioni misurabili:
#
# 1. **il filtro si risolve SU UN'ENTITA', non su un servizio.** Lo stesso
#    `light.turn_on` accetta `rgb_color` sull'Alberello e non sulla luce della
#    cucina -- e' Home Assistant a dirlo, guardando `supported_color_modes`.
#    Uno strumento che rispondesse «i parametri di `light.turn_on`» senza
#    un'entita' consegnerebbe l'elenco generico, cioe' proprio la conoscenza
#    che fa sbagliare; uno che chiedesse l'entita' sarebbe questa stessa
#    risposta, un turno piu' tardi;
# 2. **i limiti veri sono quelli dell'entita'**, e stanno nell'oggetto che il
#    modello ha gia' in mano: il campo di manovra dell'Alberello dice
#    1500-9000 K una riga piu' su. Separarli in due strumenti significherebbe
#    consegnare due meta' della stessa frase in due turni;
# 3. **non costa un giro**: il registro e' gia' in memoria, e questa vista non
#    chiede niente a nessuno.
#
# Solo sul dettaglio di UNA entita', come `attributi` e `regola`: un'area con
# venti cose ripeterebbe l'elenco dei comandi di ogni dominio venti volte.
#
# **Solo i servizi del dominio dell'entita'.** `homeassistant.*` si applica a
# qualunque dominio (`verification._DOMINI_UNIVERSALI`) e resta fuori
# apposta: quel dominio contiene anche `restart`, `reload_all` e `stop`, e
# metterli davanti al modello accanto a «accendi» sarebbe offrirglieli, non
# descriverli.
_COMMAND_PARAMETERS = "parametri"

#: Quando il registro porta il servizio ma non ha saputo leggerne i parametri
#: (`registry._fields` risponde `None`): «non l'ho letto» non e' «non ne ha».
_COMMAND_PARAMETERS_UNREAD = "parametri_non_letti"

#: Da dove vengono i limiti di un parametro. Due sole risposte, e la
#: differenza e' l'intera ragione per cui questa vista esiste: il selettore
#: descrive il campo di un cursore GENERICO (2000-6500 K per ogni lampadina
#: della casa), l'entita' descrive se stessa (1500-9000 K per l'Alberello).
#: **Vince l'entita'**, e chi legge deve poter vedere quale delle due gli e'
#: stata data.
_LIMITS_FROM_ENTITY = "questa entita'"
_LIMITS_FROM_SERVICE = "il servizio"

#: Oltre questo numero un elenco di valori legali non si scrive per intero:
#: `color_name` ne porta 140. Si dice quanti ne restano, mai «questi sono
#: tutti». Stessa soglia di `verification._list`.
_MOST_VALUES = 12


def _number(value):
    """Un limite numerico, o `None` se quel che c'e' non lo e'.

    `bool` escluso: e' una sottoclasse di `int`, e un `True` letto come
    massimo direbbe «al piu' 1».
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _values_seen(values: list) -> dict:
    """Un elenco di valori legali, tagliato se e' lunghissimo."""
    if len(values) <= _MOST_VALUES:
        return {"valori": list(values)}
    return {"valori": list(values[:_MOST_VALUES]),
            "altri_valori": len(values) - _MOST_VALUES}


def _limits_of_entity(domain: str, parameter: str, attributes: dict,
                      judgments: TypeJudgments = REPO_JUDGMENTS) -> dict:
    """I limiti che l'ENTITA' dichiara per questo parametro, o `{}`.

    Il collegamento parametro -> attributo vive nell'istantanea dei giudizi
    (`judgments.parameter_limits`, spec 2026-09-16 §3, campo `limiti_parametri`
    -- prima era `type_vocabulary.parameter_limits` letto a mano), dove ogni
    nome e' sorvegliato da una prova che lo confronta con le capacita' che
    Home Assistant dichiara per quel dominio: un refuso non diventa un limite
    che non esiste. `judgments` arriva come parametro (D3): in produzione
    l'istantanea viva, il predefinito `REPO_JUDGMENTS` e' il solo seme.

    **Un intervallo si prende solo INTERO.** Con un estremo solo dall'entita'
    e l'altro dal selettore la risposta direbbe «da 1500 a 6500», che non e'
    ne' il cursore ne' la lampadina -- una terza cosa, vera di nessuno.
    """
    linked = judgments.parameter_limits(domain, parameter)
    if not linked:
        return {}
    options_attribute = linked.get("options")
    if options_attribute:
        values = attributes.get(options_attribute)
        if isinstance(values, (list, tuple)) and values:
            return {**_values_seen(list(values)), "valori_da": _LIMITS_FROM_ENTITY}
        return {}
    lowest = _number(attributes.get(linked.get("min")))
    highest = _number(attributes.get(linked.get("max")))
    if lowest is None or highest is None:
        return {}
    return {"minimo": lowest, "massimo": highest, "limiti_da": _LIMITS_FROM_ENTITY}


def _limits_of_selector(detail: dict) -> dict:
    """I limiti che il SERVIZIO dichiara nel suo selettore, o `{}`.

    Il ripiego, non la prima risposta: descrive un cursore uguale per tutta la
    casa. Si leggono le tre sole forme che portano un limite vero -- `number`
    e `color_temp` (minimo, massimo, passo, unita') e `select` (i valori) --
    e di ogni altra forma non si dice niente invece di inventare un campo.
    """
    selector = detail.get("selector") if isinstance(detail, dict) else None
    if not isinstance(selector, dict):
        return {}
    for kind in ("number", "color_temp"):
        shape = selector.get(kind)
        if not isinstance(shape, dict):
            continue
        limits = {}
        lowest, highest = _number(shape.get("min")), _number(shape.get("max"))
        if lowest is not None:
            limits["minimo"] = lowest
        if highest is not None:
            limits["massimo"] = highest
        step = _number(shape.get("step"))
        if step is not None:
            limits["passo"] = step
        unit = clean_text(shape.get("unit_of_measurement") or shape.get("unit"))
        if unit is not None:
            limits["unita"] = unit
        if limits:
            limits["limiti_da"] = _LIMITS_FROM_SERVICE
        return limits
    shape = selector.get("select")
    if isinstance(shape, dict) and isinstance(shape.get("options"), list):
        values = [o for o in shape["options"] if isinstance(o, str)]
        if values:
            return {**_values_seen(values), "valori_da": _LIMITS_FROM_SERVICE}
    return {}


def _command_parameters(domain: str, definition: dict, attributes: dict,
                        judgments: TypeJudgments = REPO_JUDGMENTS) -> dict:
    """I parametri di UN servizio utilizzabili su un'entita' con questi
    attributi, coi loro limiti.

    Un parametro che Home Assistant dichiara non applicabile a questa entita'
    non compare: e' la stessa regola con cui la verifica lo rifiuterebbe
    (`registry.field_applies`), letta al contrario -- e le due non possono
    divergere, perche' sono la stessa funzione. Un `None` («non l'ho potuto
    misurare») lascia il parametro nell'elenco: e' un'informazione in meno,
    non una capacita' in meno.

    I limiti dell'entita' vincono su quelli del selettore, e da un'unita'
    dichiarata solo dal selettore (`kelvin`, `%`) non si rinuncia: e' la sola
    parte del cursore generico che descrive anche il dispositivo. `judgments`
    e' l'istantanea dei giudizi (spec §3): la inoltra soltanto a
    `_limits_of_entity`.
    """
    fields = definition.get("fields")
    if fields is None:
        return {_COMMAND_PARAMETERS_UNREAD: True}
    if not isinstance(fields, dict):
        return {_COMMAND_PARAMETERS: {}}
    parameters: dict = {}
    for name, detail in sorted(fields.items()):
        if not isinstance(name, str) or field_applies(detail, attributes) is False:
            continue
        detail = detail if isinstance(detail, dict) else {}
        limits = _limits_of_selector(detail)
        own = _limits_of_entity(domain, name, attributes, judgments=judgments)
        if own:
            unit = limits.get("unita")
            limits = dict(own)
            if unit and "minimo" in limits:
                limits["unita"] = unit
        parameters[name] = limits
    return {_COMMAND_PARAMETERS: parameters}


def commands_for(entity_id: str, registry, attributes: dict,
                 judgments: TypeJudgments = REPO_JUDGMENTS) -> dict:
    """Cosa si puo' chiedere a questa entita', servizio per servizio.

    `{}` quando non c'e' un registro, o quando questa casa non dichiara
    nessun servizio per il suo dominio: un `comandi: {}` su ogni sensore
    sarebbe rumore in ogni risposta -- stessa disciplina di `unita`,
    `capacita` e `categoria`.

    Pura come tutto questo modulo: il registro glielo passa il chiamante
    (`home_space/tools.py`), gia' scaldato, e qui dentro non si chiede niente
    a nessuno. `judgments` e' l'istantanea dei giudizi sui limiti dei
    parametri (spec 2026-09-16 §3): la inoltra a `_command_parameters`, in
    produzione l'istantanea viva.
    """
    if registry is None or not isinstance(attributes, dict):
        return {}
    domain = domain_of(entity_id)
    services_for = getattr(registry, "services_for", None)
    service = getattr(registry, "service", None)
    if not callable(services_for) or not callable(service):
        return {}
    commands: dict = {}
    for name in services_for(domain):
        definition = service(domain, name)
        if not isinstance(definition, dict):
            continue
        commands[f"{domain}.{name}"] = _command_parameters(
            domain, definition, attributes, judgments=judgments)
    return commands


# I MEMBRI DI UN GRUPPO, e la frase che nessuno diceva.
#
# **Dove stavano prima, e perche' era il posto sbagliato.** Fino al 09/09/2026
# `light.lampadario_sala_da_pranzo` consegnava i suoi tre membri dentro
# `campo_di_manovra`, sotto `entity_id`, accanto a `effect_list` e a
# `supported_color_modes` -- cioe' accanto ai parametri veri di
# `light.turn_on`. L'appartenenza a un gruppo non e' una cosa che si puo'
# chiedere a una luce: e' cio' DI CUI la luce e' fatta. Adesso esce da una
# chiave sua, accanto a `capacita` e a `comandi` e non dentro `attributi`,
# perche' il nome stesso della chiave dica di che fatto si tratta: chi legge
# `membri: {entita: [...]}` non puo' scambiarlo per un parametro.
#
# **E il guadagno vero e' la seconda chiave.** Home Assistant, su un gruppo,
# dichiara l'UNIONE delle capacita' dei membri -- misurato al tag `2026.9.1`,
# `components/group/light.py:283-295` (`set().union(*all_supported_color_modes)`),
# `:263-273` (gli effetti), `:250-261` (`reduce=min`/`max` sui kelvin),
# `:319-328` (l'OR di `supported_features`). Quindi un gruppo di tre luci di
# cui UNA sola sa fare colore dichiara «faccio colore», il controllo lo lascia
# passare, e Home Assistant lo applica **solo a quella che puo'**, ignorando
# le altre IN SILENZIO. Chi ha chiesto di cambiare colore a tre luci ne vede
# cambiare una, e nessuno glielo dice.
#
# Non e' un difetto di Home Assistant e non e' nostro: e' una cosa che HIRIS
# PUO' dire, e il dato per dirla e' esattamente quello che si e' spostato --
# i membri. Con i loro id, le loro capacita' sono gia' nello specchio.
#
# **E quando non lo sono, lo si DICHIARA.** Un membro fuori dallo specchio
# (un gruppo di gruppi, un'entita' che la cache non ha) non e' un membro
# uguale agli altri: e' un membro che non ho guardato. I conteggi dicono
# sempre «dei N membri letti», e i non letti escono con nome e ragione --
# stessa disciplina di `attributi.trattenuti`. Se non ne ho letto NESSUNO, la
# chiave delle capacita' non compare affatto: tacere sarebbe far leggere
# «sono tutti uguali».
_MEMBERS_KEY = "membri"
_MEMBERS_LIST = "entita"
_MEMBERS_NOT_SHARED = "capacita_non_di_tutti"
_MEMBERS_UNREAD = "non_letti"
_MEMBER_UNREAD_REASON = (
    "non e' nello specchio: non ho potuto guardare cosa dichiara, e "
    "«non l'ho guardato» non e' «e' uguale agli altri»")

#: Sotto quale nome esce il disaccordo sui bit di `supported_features`. E' la
#: stessa parola con cui il dettaglio li consegna gia' decodificati in verbi
#: (`detail["capacita"]`), apposta: chi legge la riga sa dove andare a
#: rileggere cosa il gruppo dichiarava.
_DECODED_CAPABILITIES_KEY = "capacita"


def _how_many_members(count: int, read: int) -> str:
    """Quanti membri, sui letti. **Il denominatore dice «letti» sempre**,
    anche quando li ho letti tutti: e' il numero su cui la frase e' vera, e
    scriverlo solo quando qualcuno manca renderebbe la frase piena e quella
    parziale indistinguibili a chi legge."""
    if count == 0:
        return f"nessuno dei {read} membri letti"
    return f"{count} dei {read} membri letti"


def _not_shared_by_all(declared, theirs: list) -> str | None:
    """La frase per UNA capacita' che il gruppo dichiara e i membri non
    condividono, o `None` quando la condividono tutti.

    Due forme sole, e sono le due con cui Home Assistant costruisce un gruppo:
    un ELENCO si unisce voce per voce (`supported_color_modes`, `effect_list`,
    i verbi di `supported_features`), quindi si guarda voce per voce; un
    valore SINGOLO si riduce (`min`/`max` sui kelvin), quindi si guarda per
    intero. Un elenco confrontato per intero direbbe «diversi» di due membri
    che condividono tutto tranne un effetto, che e' meno utile e piu' rumoroso.
    """
    read = len(theirs)
    if not read:
        return None
    items = list(declared) if isinstance(declared, (list, tuple, set, frozenset)) else [declared]
    missing = []
    for item in items:
        count = 0
        for mine in theirs:
            if isinstance(mine, (list, tuple, set, frozenset)):
                count += 1 if item in mine else 0
            else:
                count += 1 if mine == item else 0
        if count < read:
            missing.append(f"«{item}»: {_how_many_members(count, read)}")
    return "; ".join(missing) if missing else None


def group_membership(entity_id: str, reported_attributes: dict | None) -> dict:
    """Di cosa questa entita' e' fatta, e cosa di cio' che dichiara non e' di
    tutti i suoi membri. `{}` quando non e' un gruppo.

    Pura come tutto questo modulo: lo specchio glielo passa il chiamante, e
    qui dentro non si chiede niente a nessuno.
    """
    mirror = reported_attributes if isinstance(reported_attributes, dict) else {}
    baskets = mirror.get(entity_id)
    members = group_members(baskets)
    if not members:
        return {}
    view: dict = {_MEMBERS_LIST: list(members)}
    unread = {member: _MEMBER_UNREAD_REASON for member in members
              if not isinstance(mirror.get(member), dict)}
    if unread:
        view[_MEMBERS_UNREAD] = unread
    read = [member for member in members if member not in unread]
    if not read:
        return view
    declared = dict((baskets.get(CAPABILITIES) or {}) if isinstance(baskets, dict) else {})
    theirs = [dict(mirror[member].get(CAPABILITIES) or {}) for member in read]
    # I bit di `supported_features` entrano nel confronto come una capacita'
    # in piu', decodificati in verbi: Home Assistant li unisce con un OR
    # (`components/group/light.py:319-328`) esattamente come unisce gli
    # elenchi, quindi il difetto e' lo stesso -- e lasciarli fuori avrebbe
    # coperto meta' delle capacita' di un gruppo e taciuto sull'altra meta'.
    domain = domain_of(entity_id)
    own_features = decoded_capabilities(
        domain, disclosable_attributes(baskets).get("supported_features"))
    if own_features:
        declared[_DECODED_CAPABILITIES_KEY] = own_features
        for member, mine in zip(read, theirs):
            mine[_DECODED_CAPABILITIES_KEY] = decoded_capabilities(
                domain, disclosable_attributes(mirror[member]).get("supported_features"))
    not_shared = {}
    for name in sorted(declared):
        phrase = _not_shared_by_all(declared[name],
                                    [mine.get(name, ()) for mine in theirs])
        if phrase:
            not_shared[name] = phrase
    if not_shared:
        view[_MEMBERS_NOT_SHARED] = not_shared
    return view


def _class_meaning(knowledge, domain: str, device_class) -> str | None:
    """Cosa significa questa classe, secondo il sapere. `None` se non si sa.

    **Non solleva mai.** Il dettaglio di un'entita' e' una lettura del
    prodotto: un archivio irraggiungibile deve togliere una riga, non far
    fallire la risposta.
    """
    if knowledge is None or not device_class:
        return None
    # `type_subject` e `MEANING_FIELD` si IMPORTANO, non si riscrivono:
    # `type_judgments.type_subject` e' il solo posto dove il soggetto si
    # compone -- e finche' questo lettore ricomponeva a mano, quella garanzia
    # non esisteva (revisione indipendente, 13/09/2026). Fino al 04/10/2026
    # si importavano da `mind/`, qui dentro la funzione (B-35).
    try:
        fact = knowledge.get("tipo", type_subject(domain, device_class),
                             MEANING_FIELD)
    except Exception:  # pragma: no cover - archivio irraggiungibile
        return None
    return fact.value if fact is not None else None


