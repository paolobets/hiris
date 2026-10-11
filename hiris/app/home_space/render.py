"""La resa: una funzione per genere di oggetto (Tappa 9, «Una resa per
oggetto»; piano della Tappa 4, Task 7-8).

Ogni oggetto della casa che HIRIS mostra -- al modello, a una pagina, a un
servizio firmato -- esce da UNA funzione di questo modulo, col vocabolario
dei campi (`field_vocabulary`) e a una delle tre profondita' (corta, media,
completa). Le porte chiamano la resa e inoltrano il suo dizionario: non lo
compongono (R3, `tests/test_resa_unica.py`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..action.registry import field_applies
from ..proxy.entity_cache import (
    ASSUMABLE,
    CAPABILITIES,
    UNINTERPRETED,
    VALUES,
    disclosable_attributes,
    group_members,
    withheld_credentials,
)
from ..proxy.state_translations import TABLE_MISSING_SILENCES
from .ha_vocabulary import domain_of, entity_category_measure_rule
from .historian import instant_out
from .topology import (
    HVAC_ACTION_ATTRIBUTE,
    VISIBLE,
    categories_with_name,
    clean_text,
    decoded_capabilities,
    labels_with_id,
    live_name,
    readable_state,
    visibility_classes,
)
from .type_judgments import MEANING_FIELD, TypeJudgments, type_subject
from .type_vocabulary import REPO_JUDGMENTS

if TYPE_CHECKING:
    from .house import House

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


# --------------------------------------------------------------------------
# LE PROFONDITA'
# --------------------------------------------------------------------------

#: Fino a quante voci un elenco si rende alla profondita' media; oltre, alla
#: corta. Vive qui dal 08/10/2026 (Tappa 9, F2): la profondita' e' della resa,
#: e la porta della casa (`house_query`) e la storia la chiedono a lei.
DETAIL_MEDIUM_MAX = 10
#: Le tre profondita' di ogni resa (glossario, «Il vocabolario dei campi»):
#: `corta` una riga per oggetto, quando sono tanti; `media` fino a
#: `DETAIL_MEDIUM_MAX` oggetti; `completa` uno solo, la scheda.
DEPTHS = ("corta", "media", "completa")


def rows_depth(count: int) -> str:
    """La profondita' delle righe di un ELENCO di `count` oggetti: media fino
    a `DETAIL_MEDIUM_MAX`, corta oltre. Mai completa: la scheda e' di un
    oggetto chiesto da solo. Vale per le voci di `search` e per le entita'
    annidate nella scheda di un'area, di un dispositivo, di un'integrazione:
    la stessa entita', nello stesso numero di compagne, ha la stessa forma da
    tutte le porte (fondamenta 3)."""
    return "media" if count <= DETAIL_MEDIUM_MAX else "corta"


def depth_for(count: int) -> str:
    """La profondita' di una risposta dal numero di voci trovate, per
    `search` e per `history` (spec §3): 1 -> completa, poi `rows_depth`. Una
    regola sola (B-30, Tappa 5)."""
    return "completa" if count == 1 else rows_depth(count)


# --------------------------------------------------------------------------
# L'ENTITA'
# --------------------------------------------------------------------------

#: Il genere di un'entita' (`house_query.KINDS`, vocabolario: `genere`).
ENTITY = "entita"


def render_entity(house: House, entity_id: str, depth: str, *, zone=None,
                  translations: dict | None = None, registry=None, knowledge=None,
                  judgments: TypeJudgments = REPO_JUDGMENTS) -> dict:
    """UN'ENTITA', a una profondita': la sola funzione che la compone (R3).

    Fino all'08/10/2026 erano circa quattordici (registro, C-01): la scheda di
    `view`, le righe annidate di area e dispositivo, le voci di `search`, la
    pagina della casa, l'istantanea di una promessa... ognuna coi suoi nomi.
    La stessa entita' usciva con `da_quando` da una porta e `ultimo_cambio`
    dall'altra, con `piattaforma` e `dove.integrazione` nella stessa scheda,
    con l'area come nome nudo o come `{id, nome}`.

    **Le tre profondita'** (`DEPTHS`), ognuna contiene la precedente:

    - `corta` -- `id`, `genere`, `nome`, `area`, `stato` con
      `stato_leggibile` (o `stato_non_reso`), `unita`, `ultimo_cambio`,
      `fuori`. Lo stato in parole c'e' gia' qui: un allagamento non deve
      avere la forma di una lampadina accesa in nessuna riga. L'unita'
      pure (fondamenta 1: `72` senza unita' e' un frammento);
    - `media` -- piu' `classe`, `integrazione`, `capacita`,
      `stato_presunto`, `etichette`, `categorie` e gli `attributi`
      filtrati nelle loro ceste, come alla completa (C-34);
    - `completa` -- la scheda: piu' `piano`, `dispositivo`,
      `area_ereditata`, `fonte`, `regola`, `significato`, `membri`,
      `comandi`.

    **L'assenza.** Una chiave assente vuol dire «non lo so» o «non c'e'
    niente da dire»; `null` vuol dire «so che non c'e'» (glossario). Lo
    `stato` e' `null` quando lo specchio e' stato letto e l'entita' non ci
    sta; assente quando lo specchio non si e' potuto leggere. `fuori` c'e'
    solo per un'entita' fuori dai visibili (D4 della Tappa 4: un campo solo,
    al posto di `disabilitata`, `nascosta`, `categoria` e dei loro `_da`).

    Il filtro di riservatezza NON e' qui: e' sulla porta che parla al
    modello (`privacy.redact_row`), un punto solo; la pagina e gli attori
    ricevono lo stato vero.

    `zone` e' il fuso della casa (`historian.home_space_zone`), per gli
    istanti; `translations`, `registry`, `knowledge` e `judgments` servono
    solo cio' che li usa (lo stato in parole; comandi, significato e regola
    della completa)."""
    if depth not in DEPTHS:
        raise ValueError(f"profondita' sconosciuta: {depth!r}")
    mirror = house.mirror
    entry = house.entry(entity_id) or {}
    row: dict = {"id": entity_id, "genere": ENTITY,
                 "nome": live_name(entity_id, entry.get("nome"), mirror)}
    where = house.where(entity_id)
    if where is not None:
        row["area"] = where["area"]
    if mirror.readable:
        row["stato"] = mirror.state.get(entity_id)
    # `disclosable_attributes` e non una lettura diretta: lo specchio porta
    # gli attributi divisi in ceste (`entity_cache.inherited_attributes`), e
    # chi cerca un attributo per nome non deve sapere in quale sta -- ne'
    # inciampare nelle credenziali, che di qui non passano mai.
    attributes = disclosable_attributes(mirror.attributes.get(entity_id))
    kind = house.kind_of(entity_id) or {}
    _state_in_words(row, entity_id, kind.get("classe"), attributes, translations)
    # L'unita' VIVA vince su quella del registro (`House.kind_of`,
    # `topology.live_first`): Home Assistant converte le unita' solo alla
    # prima aggiunta del sensore. La chiave compare solo quando c'e' un'unita':
    # una lampada non ne ha, e `unita: null` su ogni luce sarebbe rumore.
    if kind.get("unita"):
        row["unita"] = kind["unita"]
    since = mirror.since.get(entity_id)
    if since is not None:
        row["ultimo_cambio"] = instant_out(since, zone)
    outside = house.visibility(entity_id)
    if outside is not None and outside[0] != VISIBLE:
        row["fuori"] = {"classe": outside[0], "causa": outside[1]}
    if depth == "corta":
        return row
    # La CLASSE: dallo specchio vivo, perche' il registro delle entita' non la
    # manda affatto (`topology.live_first`, dentro `kind_of`).
    if kind.get("classe"):
        row["classe"] = kind["classe"]
    integration = _integration_of(house, entry)
    if integration is not None:
        row["integrazione"] = integration
    # `capacita`: COSA UN'ENTITA' SA FARE, decodificato da `supported_features`
    # (`decoded_capabilities`, `topology.py` -- tabelle verificate alla fonte,
    # per dominio): 181 entita' su 834 lo dichiarano (misurato il 06/09/2026).
    # Solo quando la decodifica produce qualcosa: `capacita: []` sulle altre
    # 653 sarebbe il rumore che seppellisce quelle dove c'e' davvero.
    capabilities = decoded_capabilities(domain_of(entity_id),
                                        attributes.get("supported_features"))
    if capabilities:
        row["capacita"] = capabilities
    # `stato_presunto`: Home Assistant manda `assumed_state` SOLO quando e'
    # vero (`entity_cache._to_minimal`). Su questa casa non e' MAI arrivato
    # (0 entita' su 834, misurato il 06/09/2026).
    if attributes.get("assumed_state"):
        row["stato_presunto"] = True
    _add_labels(row, entry, house.labels())
    _add_categories(row, entry, house.categories())
    baskets = _baskets(mirror.attributes.get(entity_id))
    if baskets:
        row["attributi"] = baskets
    if depth == "media":
        return row
    if where is not None:
        if where["piano"] is not None:
            row["piano"] = where["piano"]
        if where["dispositivo"] is not None:
            row["dispositivo"] = where["dispositivo"]
        if where["area_ereditata"]:
            row["area_ereditata"] = True
    # LA FONTE (Tappa 3, Task 8, B-25; D6): perche' parla o tace, con la
    # causa che Home Assistant scrive, da `House.source`.
    row["fonte"] = house.source(entity_id)
    # `regola`: la vista CITA il vocabolario (`ha_vocabulary.py`) invece di
    # lasciare che il modello indovini dal nome -- solo nella scheda: un
    # dispositivo con 53 sensori diagnostici ripeterebbe la stessa stringa
    # 53 volte (~18 KB, misurato il 07/09/2026).
    rule = entity_category_measure_rule(
        domain_of(entity_id), dict(visibility_classes(entry)).get("servizio"),
        row.get("classe"), row.get("unita"))
    if rule:
        row["regola"] = rule
    # COSA SIGNIFICA LA CLASSE, dal sapere (fetta «il sapere e le ricette»,
    # 12/09/2026): tace quando non sa, mai una stringa vuota.
    meaning = _class_meaning(knowledge, domain_of(entity_id), row.get("classe"))
    if meaning:
        row["significato"] = meaning
    # I MEMBRI: di cosa questa entita' e' fatta (`group_membership`). La
    # chiave non compare su cio' che un gruppo non e'.
    membership = group_membership(entity_id, mirror.attributes)
    if membership:
        row[_MEMBERS_KEY] = membership
    # I COMANDI: cosa si puo' CHIEDERE a questa entita', e con quali limiti
    # (`commands_for`). Senza registro, o senza servizi per il dominio, la
    # chiave non compare: `comandi: {}` su ogni sensore sarebbe rumore.
    commands = commands_for(entity_id, registry, attributes, judgments=judgments)
    if commands:
        row["comandi"] = commands
    return row


def _integration_of(house: House, entry: dict) -> dict | None:
    """L'integrazione di un'entita' come riferimento `{id, nome}` (C-05,
    C-62): l'id e' il dominio della piattaforma -- quello che
    `search(genere=integrazione, riferimento=...)` ritrova --, il nome e' il
    titolo dell'istanza che l'ha creata, cioe' cio' che Home Assistant mostra
    nella pagina delle integrazioni sotto quel dominio (`reader._integration`,
    `title` della voce di configurazione); senza istanza nota, il dominio.

    Fino all'08/10/2026 usciva due volte nella stessa scheda (`piattaforma` e
    `dove.integrazione`), e come slug nudo, mentre area, piano e dispositivo
    uscivano gia' come `{id, nome}`."""
    platform = (entry.get("piattaforma") or "").strip()
    if not platform:
        return None
    instance = house.instance(entry.get("config_entry_id")) or {}
    return {"id": platform, "nome": instance.get("titolo") or platform}


def _state_in_words(row: dict, entity_id: str, device_class, attributes: dict,
                    translations: dict | None) -> None:
    """Lo stato IN PAROLE, accanto al valore grezzo -- mai al posto suo:
    `stato` e' il fatto, `stato_leggibile` l'interpretazione.

    Senza, una risposta diceva `on` e basta: un allagamento aveva la forma
    di una lampadina accesa. **La fonte e' una** -- le traduzioni che Home
    Assistant pubblica (`topology.readable_state`), lette una volta. Il
    DOMINIO e l'`hvac_action` alimentano il solo caso in cui uno stato grezzo
    mente da solo: un termostato IMPOSTATO su riscaldamento e FERMO
    (misurato dal proprietario il 25/08/2026).

    **Il vuoto non si consegna, il motivo si'**: quando la tabella delle
    traduzioni non si e' potuta leggere, `stato_non_reso` dice perche'. Solo
    per i due silenzi della TABELLA: 431 entita' su 841 (misurato il
    08/09/2026) -- ogni `sensor`, `number`, `select` -- non hanno una resa e
    non devono averla, perche' misurano; la chiave assente con lo `stato`
    grezzo vuol dire esattamente questo."""
    value = row.get("stato")
    if value is None:
        return
    rendered = readable_state(
        value, domain=domain_of(entity_id), device_class=device_class,
        hvac_action=attributes.get(HVAC_ACTION_ATTRIBUTE), translations=translations)
    if rendered.get("letto"):
        row["stato_leggibile"] = rendered["valore"]
    elif rendered.get("silenzio") in TABLE_MISSING_SILENCES:
        row["stato_non_reso"] = {"silenzio": rendered.get("silenzio"),
                                 "motivo": rendered.get("motivo")}


def _baskets(attributes) -> dict:
    """GLI ATTRIBUTI EREDITATI (`proxy/entity_cache.inherited_attributes`)
    nelle loro ceste, coi nomi che il modello legge (`_BASKET_NAMES`).

    «Cosa puo' fare», «cosa puo' assumere», «com'e' adesso» e «non so cosa
    sia» sono fatti di qualita' diversa, e appiattirli consegnerebbe
    `ave_window_state: 0` accanto a `hvac_modes` come se fossero la stessa
    qualita' di sapere. In piu' c'e' `trattenuti`: la sola trattenuta resa
    VISIBILE -- nome e ragione, mai il valore. `supported_features` e
    `assumed_state` non escono da qui: hanno gia' una porta decodificata
    (`capacita`, `stato_presunto`), in ogni cesta.

    Alla media e alla completa la STESSA funzione (C-34): fino all'08/10/2026
    le voci medie di `search` portavano le ceste grezze dello specchio, con le
    credenziali tolte solo dal filtro di riservatezza."""
    if not isinstance(attributes, dict) or not attributes:
        return {}
    baskets: dict = {}
    for basket, italian_name in _BASKET_NAMES.items():
        content = {k: v for k, v in (attributes.get(basket) or {}).items()
                   if k not in _RAW_ATTRIBUTES_WITH_THEIR_OWN_DOOR}
        if content:
            baskets[italian_name] = content
    withheld = withheld_credentials(attributes)
    if withheld:
        baskets[_WITHHELD_BASKET] = withheld
    return baskets


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


# -- ricordo ---------------------------------------------------------------
#
# Fetta F3 della Tappa 9 (08/10/2026): C-41, S-22, D6.

#: Il genere di un ricordo, nella parola di `house_query.KINDS`.
MEMORY_KIND = "ricordo"

#: I campi di un ricordo, nell'ordine in cui la resa li porta: le colonne di
#: `memory/store.py` (tabella `ricordi`), che non si rinominano (spec §9:
#: cambia la resa, non il record), e le due liste che `MemoryStore._compose`
#: scioglie dalle loro tabelle.
_MEMORY_FIELDS = ("id", "testo", "detto_da", "said_by", "detto_il", "forza",
                  "grandezza", "minimo", "massimo", "unita", "corretto_da_utente",
                  "ancore", "condizioni")


def render_memory(memory: dict, house: House) -> dict:
    """La resa di UN ricordo: la stessa forma da ogni porta da cui un ricordo
    esce -- il dettaglio di `search` (`queries._view_memory`), i `ricordi`
    ancorati nelle schede di area, entita', dispositivo e comportamento,
    `fetch` (`tools._recall`) e la pagina Memoria (`GET /api/memories`).
    Fondamenta 3: fino all'08/10/2026 ogni porta lo componeva da se', e
    `corretto_da_utente` usciva dalla pagina (booleano), da `fetch` e dalle
    schede (l'intero della colonna), e dal dettaglio no (C-41).

    `memory` e' la riga di `MemoryStore`, con `ancore` e `condizioni` gia'
    sciolte; `house` e' l'istantanea della casa di chi chiede, e ogni ancora
    porta il nome di oggi e se esiste ancora (`House.tether`, G-21: qui si
    chiama, non si riscrive -- D6 della Tappa 9).

    **Una profondita' sola, la completa**: ogni porta mostra il ricordo
    intero, e nessuna oggi ne chiede uno piu' corto. Il tetto in caratteri
    (R16) arriva con i tetti per risposta (Tappa 9, T6).

    Il vocabolario dei campi (`docs/GLOSSARIO.md`, D1 della Tappa 4):
    `genere` sempre; una chiave assente nella riga resta assente («non lo
    so»), un `NULL` della colonna esce `null` («so che non c'e'»).

    **Il testo esce com'e'.** Il sanitizzatore lo applicano le porte che
    parlano al modello (`queries.sanitized_memories`), prima di questa
    funzione; la pagina mostra al proprietario le sue parole. La memoria non
    si riscrive: questa e' una copia."""
    out: dict = {"genere": MEMORY_KIND}
    for field in _MEMORY_FIELDS:
        if field in memory:
            out[field] = memory[field]
    if "corretto_da_utente" in out:
        out["corretto_da_utente"] = bool(out["corretto_da_utente"])
    if "ancore" in out:
        out["ancore"] = [_shown(house.tether(tether), house)
                         for tether in out["ancore"] or []]
    return out


#: Come si chiama una cosa di cui non si sa il nome, per genere d'ancora: senza
#: nome in Home Assistant, e sparita (08/10/2026, `ux-ui-specialist` sulla
#: pagina Memoria).
_NAMELESS = {"dispositivo": ("dispositivo senza nome", "un dispositivo che non esiste più"),
             "area": ("area senza nome", "un'area che non esiste più"),
             "entita": ("entità senza nome", "un'entità che non esiste più")}

#: Cio' che si aggiunge al nome di allora quando la cosa c'e' ancora ma non ha
#: piu' un nome, e quando non c'e' piu'.
_SEEN_NOW_NAMELESS = " (nome di allora; ora senza nome in Home Assistant)"
_VANISHED = (" — non esiste più in Home Assistant. Il ricordo resta valido, ma non è "
             "più collegato a niente.")


def _shown(tether: dict, house: House) -> dict:
    """Un'ancora col nome PRONTO da mostrare (`nome_mostrato`) e da dove
    viene (`nome_di`: `attuale`, `visto`, `costruttore`, `nessuno`).

    Il ripiego e' uno, e vive qui per ogni porta da cui un ricordo esce: il
    nome di oggi; il nome con cui la persona l'ha nominata, detto come nome di
    allora; per un dispositivo il produttore e il modello, se l'anagrafe li
    ha; altrimenti «dispositivo senza nome». **L'id non e' mai un nome**: fino
    all'08/10/2026 la pagina Memoria ricadeva su `riferimento` e mostrava un
    id di registro a chi aveva detto «la lavatrice» (`ux-ui-specialist`,
    giro su `1d7a909`). Per un'ancora sparita la frase dice che il ricordo
    resta, perche' la memoria non evapora; per una non verificata
    (`esiste: None`) il nome resta quello di allora, e lo stato lo dice chi
    mostra."""
    kind, seen = tether.get("tipo"), tether.get("nome_visto")
    nameless, vanished = _NAMELESS.get(kind, ("senza nome", "una cosa che non esiste più"))
    current = tether.get("nome_attuale")
    if tether.get("esiste") is False:
        shown = (seen + _VANISHED, "visto") if seen else (vanished, "nessuno")
    elif current:
        shown = (current, "attuale")
    elif seen:
        shown = (seen + (_SEEN_NOW_NAMELESS if tether.get("esiste") else ""), "visto")
    else:
        device = (house.device(tether.get("riferimento")) or {}) if kind == "dispositivo" else {}
        maker = " ".join(p for p in (device.get("produttore"), device.get("modello")) if p)
        shown = (maker, "costruttore") if maker else (nameless, "nessuno")
    return {**tether, "nome_mostrato": shown[0], "nome_di": shown[1]}
