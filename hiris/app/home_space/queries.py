"""Le tre domande: cercare per nome, guardare il dettaglio, chiedere i legami.

Il nucleo (nucleo.py) dice DOVE sono le cose -- conta, non elenca. Le tre
funzioni qui sotto danno il DETTAGLIO, quando il modello (o l'utente dalla
pagina) lo chiede esplicitamente:

- `cerca(indice, testo)` -- trovare qualcosa per nome o alias. E' un guscio
  sottile attorno a `Lookup.find()` (memory/resolver.py): il
  contratto -- `candidati` sempre una lista, `ambiguo` dichiarato -- e' gia'
  li', e riscriverlo qui vorrebbe dire poterlo rompere in due punti invece
  che in uno. Due voci che si normalizzano uguali (due «Bagno» su piani
  diversi, un alias che collide col nome vero di un'altra area) restano
  AMBIGUE: scegliere spetta al modello, che ha la casa in contesto, o
  all'utente, che corregge dalla pagina -- non a questo modulo.
- `guarda(casa, comportamento, ricordi, stato, tipo, riferimento)` -- il
  dettaglio di UNA cosa sola: un'area con le sue entita' e i loro stati,
  un'entita' col suo stato e la sua classe, un'automazione o uno script col
  loro corpo, un dispositivo con le sue entita', un ricordo con la sua
  interpretazione.
- `related(risposta, tipo, riferimento)` -- CHI tocca questa cosa, secondo
  Home Assistant. Non e' un terzo modo di guardare la stessa cosa: `guarda`
  porta il CORPO (cosa fa quell'automazione), `legami` porta i LEGAMI (quali
  automazioni, script, scene o gruppi nominano questa entita'). Sono due
  fatti diversi sullo stesso oggetto, e tenerli in due risposte e' cio' che
  li tiene distinti -- la confusione fra «dichiarato» e «dedotto» questo
  progetto la paga da sempre.

Due, non trentaquattro: la mappa del prodotto ha condannato un catalogo di
trentaquattro strumenti con tre copie divergenti (vedi
docs/design/2026-08-05-la-conoscenza-di-hiris.md). Un tipo nuovo di "cosa"
si aggiunge come un altro `if` dentro `guarda`, non come un tool in piu'.

Tutte e tre sono PURE: prendono dati gia' letti dal chiamante (l'indice, la
casa, il comportamento, i ricordi, lo stato vivo, la risposta che Home
Assistant ha gia' dato) e non aprono archivi ne' chiamano la rete -- la
stessa scelta che rende `compose()` del nucleo verificabile senza finti
elaborati (nucleo.py). Vale anche per `legami`: la chiamata WebSocket la fa
il chiamante (`home_space/tools.py`), qui arriva solo cio' che ha risposto.

**Un silenzio non dichiarato e' indistinguibile da un'assenza di
problemi** (pagato sedici volte su questo ramo, sempre trovato da una
review, mai dalla suite). Per questo `guarda` restituisce SEMPRE la chiave
`esiste`, e quando e' `False` non inventa il resto: nessun `entita: []`,
nessun `corpo: None` che si potrebbe scambiare per un fatto sulla casa
invece che per "non trovato". E «non ho il corpo» (un limite di HIRIS --
`corpo: None` con un `origine` che lo dichiara) resta distinto da «il
corpo e' vuoto» (un fatto sulla casa: `corpo: {}` o simile).
"""
from __future__ import annotations

from ..action.registry import field_applies
from ..memory.resolver import _normalize
from ..proxy._sanitize import sanitize_text
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
from .ha_vocabulary import entity_category_measure_rule
from .historian import instant_epoch
from .topology import (
    HVAC_ACTION_ATTRIBUTE,
    actual_class,
    actual_unit,
    categories_with_name,
    category_names,
    decoded_capabilities,
    domain_of,
    hierarchy,
    label_names,
    labels_with_id,
    readable_state,
)
from .type_vocabulary import parameter_limits

# I tipi di comportamento che `guarda` sa mostrare col loro corpo. Un
# "automazione" e uno "script" sono voci dello stesso elenco
# (comportamento.py), non due archivi diversi: la distinzione e' nel campo
# `tipo` della voce, non nella provenienza.
_BEHAVIOR_TYPES = {"automazione", "script"}

# I quattordici tipi che `search/related` sa collegare -- i VALORI di
# `ItemType` (`homeassistant/components/search/__init__.py`, letti sul
# sorgente, non a memoria) -- nel vocabolario di HIRIS.
#
# A sinistra il nome vero di Home Assistant, che e' quello che va dentro il
# comando; a destra il nome italiano con cui quella cosa vive qui dentro.
# Stessa disciplina di `anagrafe._REFERENCE_FRAME_FIELDS`: l'anagrafe parla la
# lingua di HIRIS ovunque, e una risposta meta' inglese sarebbe l'unico posto
# in cui non lo fa -- per giunta proprio quella da cui il modello ricava un
# `riferimento` da passare a `guarda`, che i tipi li nomina in italiano.
#
# Si legge nei DUE versi (`HA_LINK_TYPE` piu' sotto e' la stessa tabella
# rovesciata, non una seconda): il modello nomina «entita», Home Assistant
# vuole «entity». Due elenchi da tenere allineati a mano sarebbero due
# vocabolari, cioe' la forma di difetto che le fondamenta chiamano doppione.
#
# Cinque di questi nomi -- area, entita, dispositivo, automazione, script --
# sono esattamente i tipi che `guarda` sa aprire; gli altri nove no, e
# `guarda` lo DICHIARA invece di rispondere «non esiste» (vedi il ramo finale
# di `guarda`): un id vero preso da qui non deve poter diventare
# un'affermazione falsa sulla casa.
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


def search(lookup, text: str) -> list[dict]:
    """Trova `testo` per nome o alias, con l'ambiguita' dichiarata.

    E' `Lookup.find()` PIU' cio' che serve a non sbagliare cosa si e'
    trovato. Scegliere UN candidato qui -- il primo, il piu' probabile --
    rifarebbe il difetto che e' gia' costato un fix: due «Bagno» su piani
    diversi vincevano in silenzio in base all'ordine di raccolta. Questa
    funzione non sceglie: **rende scegliere possibile**.

    Ogni candidato porta:

    - `nome`, con cui la casa lo conosce. Senza, il modello ha una lista di
      identificatori e nessun modo di riconoscerli;
    - `dominio` (solo per le entita'): `sensor`, `light`, ... E' il rimedio
      alla cecita' al dominio -- `cerca("luci")` restituisce `sensor.lights`,
      un CONTATORE di luci, e nel risultato non c'era niente che lo dicesse.
      Non si filtra (il modello e' quello che sa se un contatore gli serve),
      si dichiara;
    - `nome_dedotto`, presente (col nome dedotto, come STRINGA -- mai un
      booleano: I2, review finale) quando il nome non e' dichiarato nel
      registro ma ricavato dal `friendly_name` dello specchio dello stato
      (vedi `memory/resolver.costruisci_indice`). Un nome dedotto e'
      un fatto diverso da un nome scelto dall'utente e non va spacciato per
      tale -- stessa forma di `nome_dedotto` in `guarda()`/`_view_entity`;
    - `nascosta` (solo per le entita', e solo quando e' vera), fetta
      "nascoste fuori dagli elenchi" (2026-08-25): il proprietario ha
      misurato in produzione che `cerca` non riportava affatto questo campo
      -- «lampadario» trovava tre lampade LIFX nascoste e nulla lo diceva.
      Qui NON si esclude come in `guarda`: un'entita' cercata per nome e'
      una domanda diretta, e togliere dalla lista una cosa che esiste
      sarebbe rispondere «non esiste» di una cosa che c'e' -- la frase che
      questo prodotto non deve mai dire con sicurezza. Si MARCA soltanto, e
      solo quando e' vera: `nascosta: false` su ogni candidato di una casa
      da 1226 entita' sarebbe rumore in ogni risposta -- stessa disciplina
      di `unita`/`categorie` in `guarda()`.

    Un risultato puo' portare anche `piattaforma` (`{dominio, quante_entita}`)
    quando il testo E' il dominio di un'integrazione (`hydrawise`, `sonos`):
    si AFFIANCA ai candidati trovati per nome, non li sostituisce mai --
    review del 04/09, review del brief: una casa vera ha entita' che si
    chiamano come la propria piattaforma («Sonos», «Hue», «Shelly», «Tuya»),
    e tornare subito con `candidati: []` in quel caso le renderebbe
    irraggiungibili da `search`, esattamente la frase vietata sopra per
    `nascosta` applicata a un altro campo.

    `verify()` e' un accesso a dizionario, non una ricerca: farlo per
    candidato costa quanto leggere la lista.

    Il secondo bordo della correzione del 06/09 al §6a -- «la corrispondenza
    su un frammento» -- NON aggiunge una chiave qui: misurato costruendo
    l'indice sulla casa vera (16 aree, 1018 entita') e su due case finte
    realistiche, un campo `solo_una_parte` (`nome_visto` normalizzato diverso
    dall'intero `testo` normalizzato) usciva su 11 frasi su 13 nella prima e
    11 su 15 nella seconda -- su tutto il linguaggio naturale tranne il nome
    nudo. Una dichiarazione quasi sempre vera il modello impara a saltarla,
    anche il giorno in cui conta, che e' l'unico giorno per cui esisterebbe
    -- e non esiste nel repo un elenco di parole vuote («il», «la», «di») da
    cui distinguere un frammento povero da uno che ha perso informazione
    vera: costruirne uno, o mettere una soglia sui caratteri residui,
    sarebbe di nuovo il punteggio che la correzione vieta. Il fatto resta
    vero e gratis in `nome_visto` (gia' il testo del SOLO frammento
    riconosciuto, mai la frase intera): lo dichiara la description dello
    strumento (`tools.py::SEARCH_TOOL_DEF`), non una chiave in piu' qui."""
    results = lookup.find(text)
    whole_phrase = _normalize(text)
    for entry in results:
        for candidate in entry["candidati"]:
            resolved = lookup.verify(candidate["tipo"], candidate["riferimento"]) or {}
            deduced = (resolved.get("nome_dedotto") or "").strip()
            candidate["nome"] = (resolved.get("nome") or "").strip() or deduced
            if deduced:
                # I2 (review finale): `nome_dedotto` e' UNA forma sola in
                # tutto il modulo -- la stringa col nome dedotto, la stessa
                # che porta `guarda()`/`_view_entity`. Prima di questo fix
                # qui usciva un booleano (`True`) mentre `guarda()` usciva la
                # stringa: due tipi diversi per lo stesso fatto, con un
                # modello che poteva imparare la forma sbagliata dall'uno e
                # leggere male l'altro.
                candidate["nome_dedotto"] = deduced
            if candidate["tipo"] == "entita":
                candidate["dominio"] = domain_of(candidate["riferimento"])
                if resolved.get("nascosta"):
                    candidate["nascosta"] = True

    # Una piattaforma si riconosce ACCANTO alla ricerca fra i nomi, mai al
    # suo posto: tornare subito quando il testo e' un dominio (`hydrawise`,
    # `sonos`) cancellava gli omonimi veri di una casa -- un'entita', un'area
    # o un dispositivo chiamati come la propria integrazione. Se il testo
    # normalizzato e' anche il nome di una voce gia' trovata da `find()`, la
    # piattaforma si aggiunge a QUELLA voce; altrimenti diventa una voce sua,
    # con `candidati: []` -- non un candidato in piu' da nessuna parte.
    platforms = lookup.platforms() if hasattr(lookup, "platforms") else {}
    matched = platforms.get(whole_phrase)
    if matched:
        # `dominio` e' la chiave che il modello ripassera' a `view(tipo=
        # "integrazione", riferimento=...)` (Task 3): deve uscire gia'
        # normalizzata, non il testo grezzo digitato dall'utente ("  HYDRAWISE ")
        # -- altrimenti quella `view` non troverebbe mai un'integrazione che
        # pure esiste. Stessa `_normalize` che ha costruito la chiave in
        # `Lookup.platforms()`, cosi' le due sono garantite uguali.
        info = {"dominio": whole_phrase, "quante_entita": len(matched)}
        same_text = next(
            (entry for entry in results if _normalize(entry["nome_visto"]) == whole_phrase),
            None)
        if same_text is not None:
            same_text["piattaforma"] = info
        else:
            results.append({"nome_visto": text, "piattaforma": info,
                             "candidati": [], "ambiguo": False})
    return results


def _tethered_memories(memories: list[dict], kind: str, reference) -> list[dict]:
    """I ricordi di `ricordi` che portano un'ancora (tipo, riferimento)
    uguale a quella cercata -- stessa chiave di `MemoryStore.per_tether`
    (memory/store.py), ma su una lista gia' in memoria: `guarda` e'
    pura, non interroga l'archivio da sola.

    E' il senso delle ancore: «quali preferenze riguardano questa stanza».
    Un tipo come "automazione", "script" o "ricordo" -- fuori dal
    vocabolario delle ancore (memory/interpretation.py: area, entita,
    dispositivo) -- semplicemente non trova mai nulla qui: non e' un
    errore, e' un tipo di "cosa" per cui nessun ricordo si ancora.
    """
    found = []
    for r in memories:
        for tether in r.get("ancore") or []:
            if tether.get("tipo") == kind and tether.get("riferimento") == reference:
                found.append(r)
                break
    return found


def _find_area(floors: list[dict], reference) -> dict | None:
    """L'area `riferimento` nell'albero gia' costruito da `hierarchy()`,
    con le entita' che le spettano (ereditarieta' dal dispositivo, esclusi
    i disabilitati) gia' risolte.

    Riusa l'albero invece di rifiltrare `casa["entita"]` a mano: una
    piccola reimplementazione delle stesse regole e' gia' costata un
    Critical al Task 1 -- qui non si ripete.
    """
    for floor in floors:
        for area in floor["aree"]:
            if area["id"] == reference:
                return area
    return None


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
# (`_to_minimal` -> `live_mirror` -> `guarda`) lo faceva davvero, e nessuna
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


def _enrich_entity(entity_detail: dict, entry: dict,
                        fallback_names: dict[str, str] | None,
                        reported_units: dict[str, str] | None = None,
                        label_lookup: dict[str, str] | None = None,
                        reported_classes: dict[str, str] | None = None,
                        category_lookup: dict[tuple[str, str], str] | None = None,
                        reported_attributes: dict[str, dict] | None = None,
                        translations: dict | None = None) -> dict:
    """LA PORTA UNICA per tutto cio' che si aggiunge a un'entita'.

    Arricchisce `entity_detail` con cio' che lo SPECCHIO VIVO sa e il
    registro no (il nome dedotto e l'unita' di misura) e con cio' che il
    registro sa e la proiezione lascerebbe indietro (la piattaforma, le
    etichette e le categorie).

    Prende la VOCE del registro, non il solo `entity_id`: e' il cambiamento
    che rende questa porta capace di portare anche i campi dichiarati. Con il
    solo id, chi aggiungeva un campo nuovo era costretto a scriverlo nel
    proprio ramo -- ed e' esattamente quello che era appena successo con
    `piattaforma` ed `etichette`, uscite da una porta su tre: lo stesso
    difetto (I1) per cui questa funzione era nata.

    `nome_dedotto` con la disciplina di B5: solo quando `nome` e' vuoto nel
    registro, e mai scritto sopra `nome` -- dichiarato e dedotto restano due
    fatti diversi.

    `unita` con la stessa disciplina, e per la stessa ragione: `_to_minimal`
    la conserva (`proxy/entity_cache.py`) e nessuno la rileggeva, cosi' il
    modello riceveva `72` senza sapere se fossero gradi Celsius o Fahrenheit.
    L'unita' VIVA vince su quella del registro: Home Assistant converte le
    unita' **solo alla prima aggiunta del sensore**, quindi il registro puo'
    portare quella vecchia mentre lo specchio porta quella che HA sta usando
    adesso. La chiave compare solo quando c'e' un'unita': una lampada non ne
    ha, e `unita: null` su ogni luce sarebbe rumore in ogni risposta.

    Condivisa fra i TRE rami di `guarda` che elencano entita' (I1, review
    finale): prima di quel fix solo `_view_entity` applicava il nome dedotto,
    e le altre due porte mostravano `nome: null` secco. L'unita' entra dalla
    stessa porta unica, per non ripetere quella storia.

    `capacita` e `stato_presunto` vengono dallo SPECCHIO VIVO come `unita`, e
    per la stessa ragione: `_to_minimal` li conserva gia'
    (`proxy/entity_cache.py`), e nessun lettore li metteva davanti a chi
    compone la risposta -- vedi i due commenti sotto, accanto a dove
    escono davvero."""
    entity_id = entry.get("id")
    if not (entity_detail.get("nome") or "").strip():
        deduced = ((fallback_names or {}).get(entity_id) or "").strip()
        if deduced:
            entity_detail["nome_dedotto"] = deduced
    unit = actual_unit(entry.get("unita"), (reported_units or {}).get(entity_id))
    if unit:
        entity_detail["unita"] = unit
    # La CLASSE: dallo specchio vivo, perche' il registro delle entita' non la
    # manda affatto (`anagrafe.actual_class`). Prima questa riga usciva
    # `null` su ogni entita' della casa, e con lei taceva tutto il vocabolario
    # dei significati.
    device_class = actual_class(entry.get("classe"), (reported_classes or {}).get(entity_id))
    if device_class:
        entity_detail["classe"] = device_class
    # Lo stato IN PAROLE, accanto al valore grezzo -- mai al posto suo:
    # `stato` e' il fatto, `readable_state` e' l'interpretazione, e non si
    # sovrascrivono (stessa disciplina di `nome`/`nome_dedotto`).
    #
    # Senza, `guarda` rispondeva `on` e basta: un allagamento aveva la forma di
    # una lampadina accesa. Il digesto lo rendeva gia', ma `guarda` e' la
    # porta che il modello usa quando la domanda e' PRECISA, o quando il
    # digesto ha tagliato, o quando l'entita' e' `config`/`diagnostic` e nel
    # digesto non entra affatto. **La fonte e' la stessa** -- le traduzioni che
    # Home Assistant pubblica, lette una volta e tenute in cache: due tabelle
    # sarebbero due significati, e fino all'08/09/2026 erano scritte a mano.
    #
    # Il DOMINIO e l'`hvac_action` (dallo specchio vivo, mai dal registro:
    # `anagrafe.actual_class` vale anche qui) alimentano il solo caso in
    # cui uno stato grezzo mente da solo -- un termostato IMPOSTATO su
    # riscaldamento e FERMO che si legge «heat» com'e' il difetto misurato dal
    # proprietario (2026-08-25, `topology.readable_state`). Passati anche
    # quando l'entita' non e' un termostato: `readable_state` li ignora per
    # ogni altro dominio, e ricalcolarli qui una volta e' piu' semplice che
    # farlo condizionale.
    value = entity_detail.get("stato")
    # `disclosable_attributes` e non una lettura diretta: dalla fetta
    # dell'eredita' (07/09/2026) lo specchio porta CINQUE ceste
    # (`capabilities`/`values`/`uninterpreted`/`credentials`), e chi cerca un
    # attributo per nome non deve sapere in quale sta -- ne' inciampare nelle
    # credenziali, che di qui non passano mai.
    attributes = disclosable_attributes((reported_attributes or {}).get(entity_id))
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
            # avrebbe messo 431 blocchi di scusa dentro le risposte di `guarda`
            # per dire ogni volta la stessa cosa non-notizia, contro la legge di
            # questo prodotto («una chiave senza niente da dire non esce»). La
            # distinzione non si perde, e si legge come in
            # `handlers_mind._with_rendered_states`: la chiave ASSENTE con lo
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
    # Il digesto conta le nascoste e scrive «esistono, e `guarda` le riporta se
    # gliele chiedi» -- una promessa che `guarda` non poteva mantenere, perche'
    # il campo non usciva da nessuna porta. Alla domanda «quali sono?» il
    # modello o si contraddiceva o inventava.
    #
    # Solo quando sono vere: `nascosta: false` su ogni entita' di una casa da
    # trecento sarebbe rumore in ogni risposta, e `categoria: null` pure.
    if entry.get("nascosta"):
        entity_detail["nascosta"] = True
    category = (entry.get("categoria") or "").strip()
    if category:
        entity_detail["categoria"] = category
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
    `anagrafe.categories_with_name`, la stessa che usa l'indice di `cerca`.
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
    ACCESSORIO -- `Nome (id: X)`, la stessa forma di `anagrafe.name_with_id`
    (T8, R2: fino a questa fetta il `label_id` non usciva da NESSUNA porta,
    eppure `esegui(bersaglio.etichette=[...])` lo pretende -- il vicolo cieco
    piu' radicale della famiglia, docs/design/2026-08-20-i-riferimenti.md).
    La scelta di leggibilita' di questo modulo NON cambia: la parentesi entra
    solo perche' l'id serve, non al posto del nome. L'unione la fa
    `anagrafe.label_names`, la stessa che usa l'indice di `cerca` --
    che da T8 conosce anche le etichette stesse come candidati
    (`memory/resolver.py::costruisci_indice`), per chi sa solo il nome
    e non ha ancora nessuna cosa che la porti.

    Compare solo quando ce n'e' almeno una: `etichette: []` su ogni cosa
    sarebbe rumore in ogni risposta e -- peggio -- indistinguibile da un
    registro delle etichette caduto. Stessa disciplina di `unita`.
    """
    labels = labels_with_id(entry, label_lookup)
    if labels:
        detail["etichette"] = labels
    return detail


def _search_suggestion(reference) -> str:
    """Il messaggio che accompagna un `esiste: False` sui tre rami che
    possono confondere un NOME con un id -- area, entita', dispositivo.

    R5 (2026-08-20, misurato dal vivo): il modello chiama `guarda` con un
    nome («Soggiorno») al posto dell'id (`soggiorno`), e riceveva
    `{"esiste": False}` nudo -- indistinguibile da "quest'area non esiste
    davvero", nessun invito a `cerca`. E' il meccanismo diretto
    dell'incidente che ha generato questa fetta: il modello ritenta uguale
    finche' il turno muore.

    Il pattern esiste gia' in `action/verification.py::_no` per il bersaglio
    non risolto («Usa "cerca" per trovare il nome giusto e ripeti il
    comando») -- questa funzione lo estende a `guarda`, non lo reinventa:
    UNA sola sorgente per i tre rami (fondamenta 3, "stessa forma"), cosi'
    che togliere il richiamo da un ramo solo non lascia gli altri due
    invariati -- si nota, perche' la frase e' la stessa ovunque.
    """
    return (f"«{reference}» non e' stato trovato. Se e' un NOME (non un "
            f"id), chiama «search» con questo testo per trovare l'id giusto, "
            f"poi ripeti «view» con quello.")


def _not_found_detail(kind: str, reference, unavailable: bool) -> dict:
    """Il dict `esiste: False` comune ai rami che possono confondere un
    NOME con un id -- area, entita', dispositivo, e da T7 (R2) anche
    automazione/script (`_view_behavior`, sotto).

    "non trovato" ha due cause DIVERSE (CRITICAL ③, gia' pagato piu' volte
    su questo file): il riferimento non c'e' davvero, oppure il registro
    che lo conterrebbe non ha risposto. Sono anche due RIMEDI diversi, non
    solo due dichiarazioni:

    - riferimento assente -> `suggerimento` (invita a `cerca`, potrebbe
      essere un nome scambiato per un id);
    - registro caduto -> SOLO `non_disponibile`, MAI `suggerimento`:
      `cerca` legge la STESSA anagrafe incompleta, quindi "prova a
      cercare" sarebbe una strada altrettanto cieca -- e diluirebbe
      proprio la distinzione che `non_disponibile` esiste per marcare
      (review indipendente Task 3, confermata: suggerire quando la causa
      e' un guasto e' un rischio, non un aiuto).

    Un punto solo per questa scelta: i rami non portano una copia ciascuno
    della stessa condizione, e chi la cambia la cambia qui una volta sola.

    T7 (R2): fino a questa fetta `_view_behavior` costruiva il suo
    `esiste: False` a mano, SENZA `suggerimento` -- una scelta deliberata
    del Task 3 (review indipendente, confermata), perche' allora `cerca`
    non indicizzava automazioni/script: suggerire "chiama cerca" sarebbe
    stato un invito a una strada cieca. Da quando `cerca` li indicizza
    (`memory/resolver.py::costruisci_indice`), quella ragione non
    vale piu', e il confine si sposta: `_view_behavior` chiama
    questa funzione come gli altri tre rami, invece di duplicarne la
    logica con un `file_non_letti` scambiato per `unavailable`.
    """
    detail = {"esiste": False, "tipo": kind, "riferimento": reference}
    if unavailable:
        detail["non_disponibile"] = True
    else:
        detail["suggerimento"] = _search_suggestion(reference)
    return detail


def _entity_rows(entries: list[dict], state: dict, reported_since_when: dict[str, str] | None,
                  disabled: bool, fallback_names: dict[str, str] | None,
                  reported_units: dict[str, str] | None, label_lookup: dict[str, str],
                  reported_classes: dict[str, str] | None,
                  category_lookup: dict[tuple[str, str], str],
                  reported_attributes: dict[str, dict] | None,
                  translations: dict | None = None) -> list[dict]:
    """Un elenco grezzo di voci dell'anagrafe (`entita`/`entita_disabilitate`/
    `entita_nascoste` di `hierarchy()`) arricchito UNA riga alla volta con
    `_enrich_entity` -- il ciclo si scriveva tre volte in `_view_area`
    (una per lista) con la stessa forma, e tre copie sono tre posti in cui la
    stessa correzione si dimentica di una.

    `disabilitata` e' un valore FISSO per l'intero elenco, non letto dalla
    voce: chi chiama sa gia' da quale lista viene (le disabilitate hanno gia'
    lasciato `per_area`/`per_area_hidden` in `hierarchy()`).

    **Niente `classe` qui dentro** (corretto il 09/09/2026, audit delle
    fondamenta -- era `docs/BACKLOG.md`, «`classe: null` esce, `unita`
    assente no»): la stessa ragione per cui questo dizionario non porta
    `unita` -- `_enrich_entity` la aggiunge dallo specchio vivo, e SOLO
    quando c'e' -- vale identica per `classe`, che infatti `_enrich_entity`
    scrive con lo stesso `if device_class: ...`. Pre-seminarla qui a
    `e.get("classe")` (quasi sempre `None`: il registro delle entita' non la
    manda affatto) la faceva uscire come chiave **esplicita**, mentre
    `unita` -- assente nella stessa condizione -- non compariva: due chiavi
    mute trattate in due modi dalla stessa porta."""
    return [
        _enrich_entity(
            {"id": e["id"], "nome": e.get("nome"),
             "stato": state.get(e["id"]),
             "da_quando": (reported_since_when or {}).get(e["id"]),
             "disabilitata": disabled},
            e, fallback_names, reported_units, label_lookup, reported_classes,
            category_lookup, reported_attributes, translations)
        for e in entries
    ]


def _view_area(home_space: dict, memories: list[dict], state: dict, reference,
                 unavailable: tuple[str, ...] = (),
                 fallback_names: dict[str, str] | None = None,
                 reported_units: dict[str, str] | None = None,
                 reported_classes: dict[str, str] | None = None,
                 reported_since_when: dict[str, str] | None = None,
                 reported_attributes: dict[str, dict] | None = None,
                 translations: dict | None = None) -> dict:
    # `non_disponibili` va PROPAGATO, non solo ricevuto: senza, `hierarchy()`
    # crede che sia andato tutto bene e un'entita' che eredita l'area dal
    # proprio dispositivo -- col registro dispositivi caduto -- finisce in
    # "Senza area" invece che in "Dispositivi non letti". Risultato: una
    # cucina con cinque luci ne mostra quattro, con `esiste: True` e nessun
    # avviso: la stessa forma di una cucina davvero piu' piccola.
    floors = hierarchy(home_space, tuple(unavailable))
    label_lookup = label_names(home_space)
    category_lookup = category_names(home_space)
    area = _find_area(floors, reference)
    if area is None:
        # CRITICAL ③: se il registro delle aree non ha risposto, "non
        # trovata" non e' lo stesso di "non esiste" -- potrebbe stare
        # proprio nella parte che non si e' letta. Senza dichiararlo, il
        # modello legge "quest'area non esiste nella tua casa", un'
        # affermazione che nessuno ha il diritto di fare. La scelta fra
        # `non_disponibile` e `suggerimento` e' in `_not_found_detail`.
        return _not_found_detail("area", reference, "aree" in unavailable)
    entity = (
        # Marcate, non nascoste (MINOR): una vista di DETTAGLIO deve poter
        # dire "questa luce c'e' ma e' disabilitata" -- `_view_device`
        # e `_view_entity` lo fanno gia', `_view_area` no. `hierarchy()`
        # le tiene apposta fuori dai conteggi ma raggiungibili qui (vedi
        # anagrafe.py). Restano dentro `entita`, marcate: sapere che quella
        # luce c'e' ma non funziona e' informazione, non rumore.
        _entity_rows(area["entita"], state, reported_since_when, False, fallback_names,
                     reported_units, label_lookup, reported_classes, category_lookup,
                     reported_attributes, translations)
        + _entity_rows(area.get("entita_disabilitate", []), state, reported_since_when, True,
                       fallback_names, reported_units, label_lookup, reported_classes,
                       category_lookup, reported_attributes, translations)
    )
    # Le NASCOSTE, invece, in una chiave A PARTE -- non marcate dentro
    # `entita` come le disabilitate qui sopra (fetta "nascoste fuori dagli
    # elenchi", 2026-08-25). Il proprietario ha misurato in produzione che
    # `guarda("area", "sala_da_pranzo")` elencava sette luci mescolate,
    # quattro nascoste, col campo `nascosta` gia' presente su ognuna: stare
    # nella STESSA lista non ha impedito che venissero nominate lo stesso.
    # La regola voluta -- "HIRIS non considera le nascoste, a meno che non
    # gli vengano chieste esplicitamente" -- si applica per STRUTTURA: il
    # modello che legge `entita` per rispondere "quali luci ci sono in sala
    # da pranzo" non le vede affatto, senza dover ricordare di filtrarle da
    # un campo. Restano pero' COMPLETE e raggiungibili qui, per la stessa
    # domanda esplicita -- "cosa hai nascosto?" -- che il campo `nascosta`
    # serviva gia' quando l'entita' si guarda da sola (`_view_entity`).
    hidden_entities = _entity_rows(area.get("entita_nascoste", []), state, reported_since_when,
                                    False, fallback_names, reported_units, label_lookup,
                                    reported_classes, category_lookup, reported_attributes,
                                    translations)
    # L'elenco puo' essere incompleto senza che si veda: si dichiara.
    incomplete = sorted(set(unavailable) & {"aree", "dispositivi", "entita"})
    detail = {
        "esiste": True, "tipo": "area", "id": area["id"], "nome": area["nome"],
        "entita": entity,
        "ricordi": _tethered_memories(memories, "area", reference),
    }
    # Solo quando ce n'e' almeno una: `entita_nascoste: []` su ogni area
    # (la stragrande maggioranza non ne ha) sarebbe rumore in ogni risposta
    # -- stessa disciplina di `unita`/`etichette`/`categorie` in questo file.
    if hidden_entities:
        detail["entita_nascoste"] = hidden_entities
    # Le entita' di riferimento della stanza: solo quando l'utente le ha
    # dichiarate. Una chiave `null` su ogni area sarebbe rumore, e per giunta
    # indistinguibile da un registro delle aree caduto.
    for key in ("entita_temperatura", "entita_umidita"):
        value = (area.get(key) or "").strip()
        if value:
            detail[key] = value
    _add_labels(detail, area, label_lookup)
    if incomplete:
        detail["elenco_incompleto"] = incomplete
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


def _limits_of_entity(domain: str, parameter: str, attributes: dict) -> dict:
    """I limiti che l'ENTITA' dichiara per questo parametro, o `{}`.

    Il collegamento parametro -> attributo vive nell'anagrafe dei tipi
    (`type_vocabulary.parameter_limits`), dove ogni nome e' sorvegliato da una
    prova che lo confronta con le capacita' che Home Assistant dichiara per
    quel dominio: un refuso non diventa un limite che non esiste.

    **Un intervallo si prende solo INTERO.** Con un estremo solo dall'entita'
    e l'altro dal selettore la risposta direbbe «da 1500 a 6500», che non e'
    ne' il cursore ne' la lampadina -- una terza cosa, vera di nessuno.
    """
    linked = parameter_limits(domain, parameter)
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
        unit = shape.get("unit_of_measurement") or shape.get("unit")
        if isinstance(unit, str) and unit.strip():
            limits["unita"] = unit.strip()
        if limits:
            limits["limiti_da"] = _LIMITS_FROM_SERVICE
        return limits
    shape = selector.get("select")
    if isinstance(shape, dict) and isinstance(shape.get("options"), list):
        values = [o for o in shape["options"] if isinstance(o, str)]
        if values:
            return {**_values_seen(values), "valori_da": _LIMITS_FROM_SERVICE}
    return {}


def _command_parameters(domain: str, definition: dict, attributes: dict) -> dict:
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
    parte del cursore generico che descrive anche il dispositivo.
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
        own = _limits_of_entity(domain, name, attributes)
        if own:
            unit = limits.get("unita")
            limits = dict(own)
            if unit and "minimo" in limits:
                limits["unita"] = unit
        parameters[name] = limits
    return {_COMMAND_PARAMETERS: parameters}


def commands_for(entity_id: str, registry, attributes: dict) -> dict:
    """Cosa si puo' chiedere a questa entita', servizio per servizio.

    `{}` quando non c'e' un registro, o quando questa casa non dichiara
    nessun servizio per il suo dominio: un `comandi: {}` su ogni sensore
    sarebbe rumore in ogni risposta -- stessa disciplina di `unita`,
    `capacita` e `categoria`.

    Pura come tutto questo modulo: il registro glielo passa il chiamante
    (`home_space/tools.py`), gia' scaldato, e qui dentro non si chiede niente
    a nessuno.
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
        commands[f"{domain}.{name}"] = _command_parameters(domain, definition, attributes)
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


def _view_entity(home_space: dict, memories: list[dict], state: dict, reference,
                   unavailable: tuple[str, ...] = (),
                   fallback_names: dict[str, str] | None = None,
                   reported_units: dict[str, str] | None = None,
                 reported_classes: dict[str, str] | None = None,
                 reported_since_when: dict[str, str] | None = None,
                 reported_attributes: dict[str, dict] | None = None,
                 registry=None,
                 translations: dict | None = None) -> dict:
    entity = next((e for e in home_space.get("entita") or [] if e.get("id") == reference), None)
    if entity is None:
        # CRITICAL ③: col registro "entita" caduto (`replace` parziale
        # lascia la tabella vuota), un'entita' vera non trovata qui non e'
        # un'entita' che non esiste -- e' un registro che non ha risposto.
        # Prima di questo fix la firma non aveva nemmeno un punto d'ingresso
        # per dirlo: `non_disponibili` era ricevuto da `guarda()` ma
        # inoltrato SOLO a `_view_area`.
        return _not_found_detail("entita", reference, "entita" in unavailable)
    detail = {
        "esiste": True, "tipo": "entita", "id": entity["id"], "nome": entity.get("nome"),
        # Ne' `unita` ne' `classe` vengono da qui: `config/entity_registry/
        # list` risponde con `as_partial_dict`, che non contiene ne' l'una ne'
        # l'altra ne' gli alias (verificato sul sorgente di HA). Le aggiunge
        # `_enrich_entity` dallo specchio vivo, che ce le ha davvero -- e solo
        # quando ci sono. Fino al 09/09/2026 (audit delle fondamenta,
        # `docs/BACKLOG.md` -- «`classe: null` esce, `unita` assente no») la
        # riga qui sotto pre-seminava `classe` col valore quasi sempre vuoto
        # del registro: una promessa che non ha mai mantenuto niente, e che
        # per giunta usciva come chiave ESPLICITA (`classe: null`) mentre
        # `unita`, assente nella stessa identica condizione, non compariva.
        # Un'entita' disabilitata resta in anagrafe (e' in Home Assistant e
        # non funziona) ma sparisce dall'albero di `hierarchy()` -- questo
        # campo dice perche' `guarda` la trova comunque, senza far credere
        # che sia una stanza arredata (stesso principio di anagrafe.py).
        "disabilitata": bool(entity.get("disabilitata")),
        "stato": state.get(entity["id"]),
        "da_quando": (reported_since_when or {}).get(entity["id"]),
        "ricordi": _tethered_memories(memories, "entita", reference),
    }
    # Stesso rimedio di `costruisci_indice` e per lo stesso motivo: su
    # questa casa `name` e `original_name` sono entrambi vuoti per un'intera
    # famiglia di entita', e un `nome: null` qui e' un'entita' che l'utente
    # chiama per nome e HIRIS non sa nominare. Marcato, mai scritto sopra
    # `nome`: dichiarato e dedotto restano due fatti (`_enrich_entity`).
    detail = _enrich_entity(detail, entity, fallback_names, reported_units,
                                    label_names(home_space), reported_classes,
                                    category_names(home_space), reported_attributes,
                                    translations)
    # `regola`: la vista CITA il vocabolario (Task 4, `ha_vocabulary.py`)
    # invece di lasciare che il modello indovini dal nome -- SOLO qui, sul
    # dettaglio di UNA entita' sola, stessa decisione e stessa ragione di
    # `attributi` (poco sotto): un dispositivo con decine di sensori
    # diagnostici ripeterebbe la STESSA stringa una volta a entita' (review
    # indipendente, misurato il 07/09/2026: il dispositivo "Home Assistant"
    # ne ha 53, ~18 KB di testo identico in un'unica vista) -- il capitolato
    # stesso dice "la vista di UN'entita'".
    #
    # `classe`/`unita'` letti da `detail` (gia' risolti da `_enrich_entity`,
    # specchio vivo sopra registro), NON da `entity["classe"]`/
    # `entity["unita"]` -- il registro non li manda mai (docstring di
    # `topology.live_mirror`), e leggerli da li' troverebbe sempre
    # classe/unita' assenti anche su una diagnostica con una classe VIVA
    # vera (batteria, tensione: 24 diagnostiche su 89 misurate il
    # 07/09/2026) -- il difetto misurato dal revisore su questo stesso task.
    rule = entity_category_measure_rule(
        domain_of(entity["id"]), detail.get("categoria"),
        detail.get("classe"), detail.get("unita"))
    if rule:
        detail["regola"] = rule
    # GLI ATTRIBUTI EREDITATI (`proxy/entity_cache.inherited_attributes`): solo
    # QUI, sul dettaglio di UNA entita' sola -- decisione del proprietario,
    # fetta "attributi al modello" (2026-08-25). `_view_area` e
    # `_view_device` elencano entita' a decine (un'area con venti
    # cose, un dispositivo con le sue entita'): mettere gli attributi di
    # ognuna dentro quegli elenchi gonfierebbe la risposta di un dato che
    # nessuno ha chiesto per la singola cosa. Qui invece il modello ha gia'
    # chiesto IL DETTAGLIO di questa entita' precisa, ed e' il momento in cui
    # l'informazione si paga -- non prima. `hvac_action` (climate) alimenta
    # comunque `readable_state` ovunque, dentro `_enrich_entity`: la
    # differenza qui e' solo se il resto degli attributi grezzi (luminosita',
    # posizione, titolo del brano...) esce come chiave a se'.
    # `supported_features`/`assumed_state` NON escono da qui: vivono nello
    # stesso dizionario grezzo per una ragione di trasporto (arrivano dalla
    # stessa proiezione, `entity_cache._to_minimal`), ma hanno gia' una
    # porta propria e DECODIFICATA -- `capacita'`/`stato_presunto`, poche
    # righe sopra dentro `_enrich_entity`. Lasciarli passare anche QUI
    # sarebbe farli uscire due volte: un numero grezzo (`supported_features:
    # 27` su un sensore senza tabella, `supported_features: 0` su
    # un'entita' che non accende nessun bit) accanto alla stessa cosa gia'
    # detta in parole -- rumore nel primo caso, doppione nel secondo. Vedi
    # `_RAW_ATTRIBUTES_WITH_THEIR_OWN_DOOR` per la lista di chi ha gia' un
    # posto e non deve ripetersi qui, e si applica a OGNI cesta: un
    # `supported_features` che un'integrazione manda fuori standard (un
    # booleano invece di un bitmask) finisce fra i non interpretati, e non
    # deve ricomparire da quella porta.
    #
    # LE CESTE, e perche' sono quattro chiavi e non un dizionario piatto
    # (fetta dell'eredita', 07/09/2026): «cosa puo' fare», «com'e' adesso» e
    # «non so cosa sia» sono tre fatti di qualita' diversa, e appiattirli
    # consegnerebbe `ave_window_state: 0` accanto a `hvac_modes` come se
    # fossero la stessa qualita' di sapere. La quarta -- `trattenuti` -- e' la
    # sola trattenuta di questo prodotto resa VISIBILE: nome e ragione, mai il
    # valore, mai un silenzio.
    attributes = (reported_attributes or {}).get(entity["id"])
    if isinstance(attributes, dict) and attributes:
        baskets: dict = {}
        for basket, italian_name in _BASKET_NAMES.items():
            content = {k: v for k, v in (attributes.get(basket) or {}).items()
                       if k not in _RAW_ATTRIBUTES_WITH_THEIR_OWN_DOOR}
            if content:
                baskets[italian_name] = content
        withheld = withheld_credentials(attributes)
        if withheld:
            baskets[_WITHHELD_BASKET] = withheld
        if baskets:
            detail["attributi"] = baskets
    # I MEMBRI (`group_membership`, poco sopra): DI COSA questa entita' e'
    # fatta, e cosa di cio' che dichiara non e' di tutti i suoi membri. Fuori
    # da `attributi` di proposito -- e' composizione, non un attributo fra gli
    # altri -- e solo qui, sul dettaglio di UNA entita' sola, per la stessa
    # ragione di `attributi` e di `regola`. La chiave non compare su cio' che
    # un gruppo non e': `membri: []` su ogni luce della casa sarebbe rumore in
    # ogni risposta.
    membership = group_membership(entity["id"], reported_attributes)
    if membership:
        detail[_MEMBERS_KEY] = membership
    # I COMANDI (`commands_for`, poco sopra): cosa si puo' CHIEDERE a questa
    # entita', e con quali limiti -- l'altra meta' del requisito del
    # proprietario (spec §13), accanto a cio' che l'entita' e'.
    #
    # Gli attributi che si passano sono quelli PIATTI e senza credenziali
    # (`disclosable_attributes`, gia' calcolati da `_enrich_entity` con la
    # stessa porta): il filtro di Home Assistant nomina l'attributo per nome
    # -- `supported_color_modes` -- e chi lo confronta non deve sapere in
    # quale cesta stia. Senza registro, o senza servizi per questo dominio,
    # la chiave non compare affatto: `comandi: {}` su ogni sensore della casa
    # sarebbe rumore, e per giunta indistinguibile da «questa entita' non si
    # comanda».
    commands = commands_for(entity["id"], registry,
                            disclosable_attributes(
                                (reported_attributes or {}).get(entity["id"])))
    if commands:
        detail["comandi"] = commands
    return detail


def _view_device(home_space: dict, memories: list[dict], state: dict, reference,
                        unavailable: tuple[str, ...] = (),
                        fallback_names: dict[str, str] | None = None,
                        reported_units: dict[str, str] | None = None,
                 reported_classes: dict[str, str] | None = None,
                 reported_since_when: dict[str, str] | None = None,
                 reported_attributes: dict[str, dict] | None = None,
                 translations: dict | None = None) -> dict:
    label_lookup = label_names(home_space)
    category_lookup = category_names(home_space)
    device = next(
        (d for d in home_space.get("dispositivi") or [] if d.get("id") == reference), None)
    if device is None:
        # CRITICAL ③, stesso difetto applicato al dispositivo: col registro
        # "dispositivi" caduto, "non trovato" non e' "non esiste".
        return _not_found_detail("dispositivo", reference,
                                      "dispositivi" in unavailable)
    # Stessa ragione per cui `_view_entity` porta `disabilitata`: qui si
    # legge `casa["entita"]` grezzo, fuori da `hierarchy()`, che le disabilitate
    # le esclude. Senza dirlo, un dispositivo spento e le sue entita' morte
    # avrebbero la stessa forma di uno che funziona.
    #
    # Le NASCOSTE (e non disabilitate: stessa precedenza di `hierarchy()` --
    # una disabilitata e nascosta insieme resta fra le disabilitate, non
    # duplica il fatto in due chiavi) si separano PRIMA di arricchire, con la
    # stessa regola dell'area: fuori da `entita`, dentro `entita_nascoste`
    # (fetta "nascoste fuori dagli elenchi", 2026-08-25) -- STESSA chiave,
    # STESSA forma della porta area, cosi' il modello non impara due
    # vocabolari per lo stesso fatto su due porte diverse.
    raw_device_entities = [
        e for e in home_space.get("entita") or [] if e.get("dispositivo_id") == reference]
    raw_hidden = [e for e in raw_device_entities
                       if e.get("nascosta") and not e.get("disabilitata")]
    raw_visible = [e for e in raw_device_entities
                       if not (e.get("nascosta") and not e.get("disabilitata"))]
    device_entities = [
        _enrich_entity(
            # `stato` come dall'area: la stessa entita' e' la stessa cosa da
            # tutte le porte. Senza lo stato, questa porta usciva con
            # `unita: "C"` e nessun valore -- un'unita' di misura di un numero
            # che non c'e', e il modello o dice "non lo so" o lo inventa.
            #
            # **Niente `classe` pre-seminata qui** (corretto il 09/09/2026,
            # stessa correzione di `_entity_rows` e `_view_entity` qui sopra):
            # `_enrich_entity` la scrive dallo specchio vivo, e solo quando
            # c'e' -- esattamente come fa gia' per `unita`.
            {"id": e["id"], "nome": e.get("nome"),
             "stato": state.get(e["id"]),
             "da_quando": (reported_since_when or {}).get(e["id"]),
             "disabilitata": bool(e.get("disabilitata"))},
            e, fallback_names, reported_units, label_lookup, reported_classes,
            category_lookup, reported_attributes, translations)
        for e in raw_visible
    ]
    device_hidden_entities = _entity_rows(
        raw_hidden, state, reported_since_when, False, fallback_names, reported_units,
        label_lookup, reported_classes, category_lookup, reported_attributes, translations)
    detail = {
        "esiste": True, "tipo": "dispositivo", "id": device["id"],
        "nome": device.get("nome"),
        "disabilitato": bool(device.get("disabilitato")),
        "entita": device_entities,
        "ricordi": _tethered_memories(memories, "dispositivo", reference),
    }
    # Solo quando ce n'e' almeno una -- stessa disciplina della porta area.
    if device_hidden_entities:
        detail["entita_nascoste"] = device_hidden_entities
    # Marca e modello: letti a ogni ricostruzione, e mai usciti da nessuna
    # porta. «Di che marca e' la valvola del bagno? Devo ordinarne un'altra
    # uguale» e' una domanda che si fa davvero, e la risposta era in tabella.
    for key in ("produttore", "modello"):
        value = (device.get(key) or "").strip()
        if value:
            detail[key] = value
    _add_labels(detail, device, label_lookup)
    # L'elenco sopra viene da "entita" grezzo: se quel registro non ha
    # risposto, l'elenco puo' essere incompleto (o vuoto) senza che si veda
    # -- stesso principio di `_view_area`.
    if "entita" in unavailable:
        detail["elenco_incompleto"] = ["entita"]
    return detail


def _view_behavior(behavior: list[dict], memories: list[dict],
                           kind: str, reference,
                           unread_bodies: dict[str, str] | None = None) -> dict:
    entry = next(
        (v for v in behavior if v.get("id") == reference and v.get("tipo") == kind), None)
    if entry is None:
        # CRITICAL ③, quinto ramo: se un file di comportamento non si e'
        # letto (`automations.yaml`/`scripts.yaml`, o uno incluso in un
        # pacchetto), "non trovato" non e' "non esiste" -- potrebbe essere
        # scritto proprio li'. Non si prova a indovinare QUALE file avrebbe
        # contenuto QUESTA voce (le automazioni scritte a mano non stanno
        # per forza nel file principale, vedi comportamento.py): se un file
        # qualsiasi non si e' letto, l'incertezza si dichiara comunque,
        # invece di tacerla come prima -- la firma non aveva nemmeno un
        # punto d'ingresso per riceverlo.
        #
        # T7 (R2): `_not_found_detail`, non piu' un dict a mano --
        # `file_non_letti` gioca lo stesso ruolo di `unavailable` per
        # area/entita'/dispositivo (un guasto di lettura, non l'assenza
        # della cosa), e ora che `cerca` indicizza automazioni e script un
        # NOME al posto dell'id e' un errore possibile anche qui: merita lo
        # stesso `suggerimento` degli altri tre rami, con la stessa frase.
        #
        # **Ogni voce di `unread_bodies` conta.** Fino al 10/09/2026 la fonte
        # era un file, e il file genuinamente assente non nascondeva niente --
        # non c'era contenuto scritto da poter mancare. Adesso il soggetto e'
        # un'entita' che Home Assistant ha caricato per davvero: se non se ne
        # conosce il corpo, cio' che fa e' nascosto, sempre.
        return _not_found_detail(kind, reference, bool(unread_bodies))
    return {
        "esiste": True, "tipo": kind, "id": entry["id"], "nome": entry.get("nome"),
        # `corpo` passa cosi' com'e': `None` (HIRIS non l'ha -- e
        # `unread_bodies` dice perche') e un corpo vuoto ma presente sono due
        # valori diversi, e questa funzione non li confonde riscrivendoli.
        "corpo": entry.get("corpo"),
        "ricordi": _tethered_memories(memories, kind, reference),
    }


def _view_memory(memories: list[dict], reference) -> dict:
    memory = next((r for r in memories if r.get("id") == reference), None)
    if memory is None:
        return {"esiste": False, "tipo": "ricordo", "riferimento": reference}
    # La forma e' PIATTA, la stessa di `fetch` e dei `ricordi` che ogni
    # altro ramo di `guarda` gia' restituisce (`_tethered_memories`).
    #
    # Prima l'interpretazione era annidata sotto una chiave `interpretazione`
    # e `detto_il` non usciva affatto: lo stesso ricordo aveva due forme a
    # seconda della porta. Il modello ne imparava una dentro
    # `guarda("area", ...)`, poi chiedeva il dettaglio con
    # `guarda("ricordo", id)` e leggeva `r["forza"]` -> assente, e riferiva
    # «di questo ricordo non so la forza» su un ricordo che ce l'ha. E alla
    # domanda «quando te l'ho detto?» la risposta dipendeva da quale strumento
    # il modello avesse scelto.
    #
    # Le caselle restano distinte dal TESTO -- che e' la verita' e non si
    # riscrive -- ma la distinzione la fanno i nomi dei campi, non un livello
    # di annidamento in piu' che esiste da una porta sola.
    detail = {
        "esiste": True, "tipo": "ricordo", "id": memory["id"], "testo": memory["testo"],
        "detto_da": memory.get("detto_da"),
        "detto_il": memory.get("detto_il"),
        "forza": memory.get("forza"), "grandezza": memory.get("grandezza"),
        "minimo": memory.get("minimo"), "massimo": memory.get("massimo"),
        "unita": memory.get("unita"),
        "ancore": memory.get("ancore") or [],
        "condizioni": memory.get("condizioni") or [],
    }
    return detail


def sanitized_memories(memories: list[dict] | None) -> list[dict]:
    """I ricordi con `testo` passato dal sanitizzatore -- funzione condivisa,
    non una riga ripetuta a ogni porta che restituisce ricordi al modello.

    C-2/I1 (L1-sicurezza.md, review indipendente del 25/08/2026): la prima
    versione di questa correzione sanificava il testo dentro `guarda()` ma
    non dentro `tools.py::_recall` (che legge `MemoryStore.per_tether`
    direttamente, senza passare da qui) -- lo stesso ricordo usciva filtrato
    da una porta e grezzo dall'altra: la fondamenta 3 (consistenza fra porte)
    rotta dentro la correzione che doveva chiuderla. Un punto SOLO, importato
    da entrambe le porte, e' l'unico modo per cui questo non possa ripetersi
    con una terza porta futura.

    Il testo ARCHIVIATO non cambia (`memory/store.py`, regola 1): questa
    e' una copia, non una riscrittura -- vedi il docstring di `guarda()`."""
    return [dict(r, testo=sanitize_text(r["testo"])) if "testo" in r else r
           for r in (memories or [])]


# Ampiezza (in secondi) fra il primo e l'ultimo istante delle entita' mute di
# una piattaforma, sotto la quale `mute_da` esce -- misurata sui dati veri
# della casa (revisione indipendente, 04/09), dopo che la prima versione
# (uguaglianza esatta) non faceva mai uscire il campo: sulle nove
# piattaforme mute della casa, l'ampiezza vera fra prima e ultima entita'
# muta era fritz 1 ms, spook 3 ms, ave_domina 11 ms, alexa 19 ms, hydrawise
# 21 ms, tuya 22 ms, lifx 71 ms, matter 108 ms -- CONTRO mobile_app e
# reolink, che distano 10,8 ORE: entita' spente una alla volta nell'arco
# della giornata, non un'integrazione caduta. Le due classi stanno a cinque
# ordini di grandezza: 2 secondi sta comodo sopra la piu' larga onda vera
# (matter, 108 ms) e ben sotto la piu' stretta onda falsa (mobile_app,
# 10,8 ore).
_SYNCHRONY_WINDOW_SECONDS = 2.0


def _view_integration(home_space: dict, state: dict, reference,
                      reported_since_when: dict[str, str] | None,
                      unavailable: tuple[str, ...] = (),
                      fallback_names: dict[str, str] | None = None,
                      reported_units: dict[str, str] | None = None,
                      reported_classes: dict[str, str] | None = None,
                      reported_attributes: dict[str, dict] | None = None,
                      translations: dict | None = None) -> dict:
    """Un'integrazione con le sue entita' e quante di esse rispondono.

    **La salute di un'integrazione non e' il suo `stato`** (spec §4): sulla
    casa vera hydrawise e' `loaded` con 24 entita' su 30 mute, e per questo
    l'irrigazione ferma non compariva da nessuna parte. Qui si contano, e la
    frase la dice chi legge.

    `entita_mute` conta SOLO `unavailable` (correzione del 04/09, spec §4,
    "unavailable non e' unknown"): e' lo stato che Home Assistant scrive
    quando non riesce a leggere il dispositivo o il servizio -- "we can't
    fetch data from a device or service" (developer docs, integration
    quality scale, regola "entity-unavailable"). `unknown` e' un'altra cosa:
    l'entita' risponde, ma il valore non e' noto in questo momento -- e
    sulla casa vera lifx ha 0 `unavailable` e 7 `unknown` (spec §4): sono
    lampadine SPENTE, non guaste. Sommarle avrebbe fatto dire a `view lifx`
    "7 entita' non rispondono", proprio la lettura sbagliata che la spec
    elenca fra le due cose dichiarate e non decise ("74 o 148?"). Le
    `unknown` si contano a parte, in `entita_stato_ignoto` (presente SOLO
    quando e' maggiore di zero, stessa disciplina di `entita_disabilitate`
    piu' sotto) -- e non entrano mai nell'elenco `entita`, che resta quello
    delle sole mute vere.

    `mute_da` esce quando le mute (`unavailable`, lo STESSO insieme di
    `entita_mute` -- mai le `unknown`, altrimenti la data si riferirebbe a
    un gruppo diverso dal numero accanto) condividono un istante ABBASTANZA
    vicino (`_SYNCHRONY_WINDOW_SECONDS`, sopra) -- non identico: e' la firma
    della sincronia (§4) che distingue un'integrazione caduta da dispositivi
    spenti uno per volta. Un'entita' muta SENZA `da_quando` continua a
    impedire l'uscita del campo (non si puo' dire se e' dentro o fuori dalla
    finestra senza saperlo): inventare un «da quando» quando non si e'
    sicuri che sia sincrono sarebbe proprio la risposta sicura che questo
    sprint toglie.

    `avvio_home_assistant` esce accanto a `mute_da`, non a una seconda
    chiamata di distanza (spec §4 ③): e' lo stato di `sensor.uptime`, letto
    dallo SPECCHIO degli stati che questa funzione gia' riceve (`state`),
    mai una chiamata nuova verso Home Assistant. L'integrazione Uptime e'
    facoltativa -- verificato sulla documentazione ufficiale
    (home-assistant.io/integrations/uptime/): il sensore, device class
    timestamp, porta «the date and time when Home Assistant was last
    started», scritto una volta all'avvio e fermo fino al riavvio
    successivo. Misurato sulla casa vera (02/09): TRE piattaforme (tuya,
    lifx, matter) condividono lo stesso `mute_da` -- non tre guasti
    simultanei, ma la firma di un riavvio che ha ri-datato tutto insieme;
    sottratto da `sensor.uptime`, lifx e tuya distano meno di un secondo e
    matter -18 s (il riavvio). Alexa NON e' fra queste: e' a +28,4 minuti
    dall'avvio, la zona di mezzo che il §4 ③ prescrive di non chiudere --
    ne' riavvio ne' guasto, si dichiara il dubbio (correzione del 05/09,
    la spec stessa contava "quattro" includendola per errore, docs/design,
    commit `022cb0b2`). Hydrawise -- l'unica integrazione davvero rotta --
    ne dista 47 ore. Il codice non emette QUESTO verdetto: mette solo i due
    istanti fianco a fianco, la frase la dice chi legge (spec §4: "il
    codice calcola i fatti, il modello dice la frase"). La chiave esce SOLO
    quando ENTRAMBE le condizioni valgono: `mute_da` e' gia' nel dettaglio
    (senza un istante da confrontare non c'e' nulla da mettere accanto) e
    `sensor.uptime` porta un istante VALIDO nello specchio degli stati --
    passato per lo stesso `instant_epoch` che valida `mute_da` poche righe
    sotto, non la sola verita' Python. Serve: `unavailable` e `unknown`
    sono STRINGHE PIENE, non `None` ne' stringa vuota, che una guardia di
    sola truthiness lascerebbe passare come se fossero un istante (rilievo
    di revisione, 05/09: la funzione usa gia' quelle due stesse stringhe
    come sentinelle per classificare le entita' mute, poche righe sopra --
    ignorarle qui per lo stesso sensore sarebbe incoerente). Dove
    `sensor.uptime` manca, o e' una di quelle sentinelle, o non e' un
    istante valido, la chiave non esce affatto: l'assenza e' assenza, mai
    un `None` ne' una sentinella spacciata per un fatto.

    `reference` si normalizza (`_normalize`, la stessa di `search`) prima del
    confronto -- passata da `str()` prima, perche' lo schema dello strumento
    ammette anche un intero (`riferimento: ["string", "integer"]`,
    tools.py) e `_normalize` chiama `.lower()`, che un intero non ha: il
    valore che arriva da `search` e' gia' la chiave canonica (fix accanto a
    `info["dominio"]`, sopra), ma il modello puo' scrivere questo
    `riferimento` a mano invece di ripassare quello -- ed e' l'UNICO ramo di
    `view` dove il riferimento e' un dominio tecnico (sempre minuscolo, senza
    accenti, in Home Assistant) invece di un id-slug come per
    area/entita'/dispositivo: normalizzarlo qui non puo' mai confondere due
    domini diversi (a differenza di un nome libero), e recupera un
    "Hydrawise" scritto con la maiuscola senza costringere il modello a
    passare sempre da `search` prima.

    `unavailable` (i registri dell'anagrafe caduti, stessa tupla degli altri
    rami) va propagato QUI come ovunque (CRITICAL, gia' sbagliato quattro
    volte su questo file secondo il docstring di `view`): senza, un dominio
    che non compare in nessuna delle due liste sembra "non esiste" anche
    quando la causa vera e' che `entita`/`integrazioni` non hanno risposto
    -- e un dominio che ESISTE con `entita` caduto uscirebbe con
    `entita_totali: 0, entita_mute: 0`, "nessun problema" detto con
    sicurezza proprio sulla domanda per cui questa fetta esiste. Il secondo
    caso si dichiara con `elenco_incompleto` -- STESSA chiave, stessa forma
    di `_view_area` (`incomplete = sorted(set(unavailable) & {...})`, sopra)
    e di `_view_device`, non un campo nuovo per lo stesso fatto. La prima
    versione di questa fetta (revisione indipendente, giro 2) nominava solo
    `"entita"`: ma `voci` viene dal registro `integrazioni`, non da
    `entita`, e con `integrazioni` caduto e le entita' presenti la risposta
    usciva `esiste: True, voci: []` senza dichiarare nulla -- "questa
    integrazione non ha voci di configurazione" detto come fatto sulla casa,
    quando la verita' e' "non ho potuto leggerle". `elenco_incompleto`
    elenca quindi ENTRAMBI i registri che alimentano questa risposta, non
    solo quello che elenca le entita'.

    Le entita' DISABILITATE (ruling del controller, revisione indipendente):
    non stanno nello state machine di Home Assistant, quindi non "rispondono"
    ne' "non rispondono" -- includerle nel denominatore farebbe sembrare
    l'integrazione piu' sana di quanto sia (o, se il loro stato mancante
    fosse letto come muto, meno sana). Si escludono da `entita_totali` e da
    `entita_mute` e si dichiarano a parte, in `entita_disabilitate` (un
    conteggio, non un elenco: qui la domanda e' "quante", non "quali" --
    diversamente da `entita_nascoste` nelle porte area/dispositivo, dove il
    modello deve poterle nominare), presente solo quando ce n'e' almeno una.
    Una cosa spenta dall'utente non e' una cosa che non risponde.

    **Le righe delle entita' passano da `_enrich_entity`**, come quelle
    dell'area, del dispositivo e dell'entita' singola. Fino all'08/09/2026
    questa funzione se le costruiva in proprio -- `{id, nome, stato,
    da_quando}` e basta -- ed era la seconda casa di una regola che ne ha
    gia' una: `view(integrazione, hydrawise)` sulla casa vera elencava 24
    entita' mute senza `nome_dedotto` (otto valvole col registro muto, quattro
    righe intitolate tutte «Irrigazione»), senza `stato_leggibile`, `classe`,
    `piattaforma`, `categoria`, `nascosta`. Fondamenta 3 e 2 insieme (audit
    delle fondamenta, rilievo 3).
    """
    domain = _normalize(str(reference or ""))
    matching = [e for e in home_space.get("entita") or []
                if _normalize(e.get("piattaforma") or "") == domain]
    entries = [{"titolo": i.get("titolo"), "stato": i.get("stato"), "motivo": i.get("motivo")}
               for i in home_space.get("integrazioni") or []
               if _normalize(i.get("dominio") or "") == domain]
    if not matching and not entries:
        return _not_found_detail("integrazione", reference,
                                  "entita" in unavailable or "integrazioni" in unavailable)
    own = [e for e in matching if not e.get("disabilitata")]
    disabled = [e for e in matching if e.get("disabilitata")]
    mute = [e for e in own if state.get(e["id"]) == "unavailable"]
    unknown = [e for e in own if state.get(e["id"]) == "unknown"]
    detail = {
        "esiste": True, "tipo": "integrazione", "dominio": domain,
        "voci": entries,
        "entita_totali": len(own),
        "entita_mute": len(mute),
        # `disabilitata=False` non e' un'ipotesi: `mute` esce da `own`, che
        # ha gia' tolto le disabilitate qualche riga sopra.
        "entita": _entity_rows(mute, state, reported_since_when, False,
                               fallback_names, reported_units,
                               label_names(home_space), reported_classes,
                               category_names(home_space), reported_attributes,
                               translations),
    }
    if unknown:
        detail["entita_stato_ignoto"] = len(unknown)
    if disabled:
        detail["entita_disabilitate"] = len(disabled)
    incomplete = sorted(set(unavailable) & {"entita", "integrazioni"})
    if incomplete:
        detail["elenco_incompleto"] = incomplete
    moments = [(reported_since_when or {}).get(e["id"]) for e in mute]
    if moments and all(moments):
        epochs = [instant_epoch(m) for m in moments]
        if all(ep is not None for ep in epochs):
            earliest, latest = min(epochs), max(epochs)
            if latest - earliest <= _SYNCHRONY_WINDOW_SECONDS:
                detail["mute_da"] = moments[epochs.index(earliest)]
    if "mute_da" in detail:
        ha_start = state.get("sensor.uptime")
        if ha_start and instant_epoch(ha_start) is not None:
            detail["avvio_home_assistant"] = ha_start
    return detail


def view(home_space: dict, behavior: list[dict], memories: list[dict], state: dict,
           kind: str, reference,
           unavailable: tuple[str, ...] = (),
           unread_bodies: dict[str, str] | None = None,
           fallback_names: dict[str, str] | None = None,
           reported_units: dict[str, str] | None = None,
           reported_classes: dict[str, str] | None = None,
           reported_since_when: dict[str, str] | None = None,
           reported_attributes: dict[str, dict] | None = None,
           registry=None,
           translations: dict | None = None) -> dict:
    """Il dettaglio di UNA cosa sola -- l'area con le sue entita' e i loro
    stati, l'entita' col suo stato e la sua classe, l'automazione o lo
    script col loro corpo, il dispositivo con le sue entita', il ricordo
    con la sua interpretazione.

    Restituisce SEMPRE la chiave `esiste`. Quando e' `False` il resto non
    si inventa: nessun `entita: []`, nessun `corpo: None` che si potrebbe
    scambiare per un fatto sulla casa invece che per "non trovato" -- un
    silenzio non dichiarato e' indistinguibile da un'assenza di problemi.

    Sui due rami che elencano entita' -- area e dispositivo -- `entita` NON
    contiene mai le NASCOSTE (`hidden_by` di Home Assistant, l'utente le ha
    tolte dalle proprie viste): fetta "nascoste fuori dagli elenchi"
    (2026-08-25), decisione del proprietario -- "HIRIS non prende in
    considerazione le entita' nascoste, a meno che non gli vengano chieste
    esplicitamente". Restano complete e raggiungibili nella chiave parallela
    `entita_nascoste` (presente solo quando ce n'e' almeno una), la stessa
    forma di `hierarchy()` per le disabilitate. La differenza col
    trattamento delle disabilitate e' voluta: quelle restano DENTRO `entita`,
    marcate (`disabilitata: true`) -- e' un dato utile su un impianto che
    esiste, "questa luce c'e' ma non funziona"; le nascoste sono una scelta
    di VISTA dell'utente, e la misura in produzione (`guarda("area",
    "sala_da_pranzo")`, sette luci mescolate, quattro nascoste) ha mostrato
    che marcarle SENZA separarle non basta -- il campo c'era gia' e non ha
    impedito che venissero elencate. Una singola entita' guardata da sola
    (`_view_entity`) continua a portare il campo `nascosta` invece che una
    chiave a parte: non c'e' un elenco da cui separarla, hai chiesto
    esplicitamente proprio lei.

    R5: sui rami che possono confondere un NOME con un id -- area, entita',
    dispositivo, e da T7 (R2) anche automazione e script -- `esiste: False`
    porta anche `suggerimento` (`_search_suggestion`): invita a chiamare
    `cerca` col riferimento ricevuto. STESSA chiave, STESSA frase su tutti
    questi rami (fondamenta 3) -- non su `_view_memory`, il solo tipo il
    cui id (numerico, interno a HIRIS, mai uno slug di Home Assistant) non
    si scrive mai al posto di un nome.

    Fino a T7 automazione e script restavano fuori apposta (decisione del
    Task 3, review indipendente): `cerca` non li indicizzava ancora, e
    suggerirlo sarebbe stato un invito a una strada che non portava da
    nessuna parte. Da quando `cerca` li indicizza
    (`memory/resolver.py::costruisci_indice`), quella ragione e'
    caduta, e il confine si e' spostato con lei: vedi il docstring di
    `_not_found_detail`, che ora e' anche la porta di
    `_view_behavior`.

    MA non quando `non_disponibile` e' vero (`_not_found_detail`): se
    il registro e' caduto, `cerca` legge la STESSA anagrafe incompleta --
    suggerirlo sarebbe una strada altrettanto cieca, e diluirebbe la
    distinzione fra "non trovato" e "non ho potuto guardare" che questo
    modulo marca come critica. Le due chiavi sono quindi mutuamente
    esclusive su questi tre rami: mai `suggerimento` insieme a
    `non_disponibile`.

    E `esiste: False` ha due cause diverse, che da questa fetta si vedono:
    il riferimento non c'e' (le cinque funzioni qui sopra), oppure il TIPO
    non e' fra quelli che HIRIS sa aprire -- e allora esce anche
    `non_so_guardare: True`, perche' una scena o un gruppo che `related()`
    ha appena mostrato esistono eccome, e dirne «non esiste» sarebbe una
    risposta sbagliata detta con sicurezza.

    `non_disponibili` (registri dell'anagrafe caduti: "aree", "dispositivi",
    "entita") e `file_non_letti` (i file di comportamento non letti, stessa
    forma di `HomeSpaceStore.file_non_letti()`) vanno propagati a OGNI ramo,
    non solo a quello dell'area: un "non trovato" e un "non ho potuto
    guardare" sono due fatti diversi, e prima di questo fix solo l'area
    poteva dirlo (CRITICAL ③ -- sbagliato quattro volte su questo ramo). Chi
    non li passa non e' punito con un errore: resta silenziosamente onesto,
    non silenziosamente sbagliato -- vedi `dettaglio["non_disponibile"]`,
    presente solo quando `esiste` e' `False` E il registro/file pertinente
    non ha risposto.

    `nomi_di_ripiego` (entity_id -> friendly_name dallo specchio dello
    stato, stessa forma usata da `costruisci_indice` e da `cerca()`) conta
    per OGNI ramo che elenca entita' -- `entita` da sola, ma anche le
    entita' di un'`area` e di un `dispositivo` (I1, review finale: la stessa
    entita' e' la stessa cosa da tutte le porte) -- e solo quando il
    registro non ha un nome: se c'e' esce come `nome_dedotto`, mai scritto
    sopra `nome` -- dichiarato e dedotto restano due fatti diversi.

    `reported_since_when` (entity_id -> `last_changed` dallo specchio dello stato,
    stessa forma di `unita_vive`/`reported_classes`) accompagna OGNI `"stato"` che
    esce da questa funzione: il campo che Home Assistant manda a ogni cambio
    di stato e che la proiezione della cache scartava (fondamenta 3 -- la
    stessa domanda non puo' avere due risposte diverse a seconda di quale
    ramo di `guarda` la porta).

    `reported_attributes` (entity_id -> le CINQUE CESTE dello specchio dello
    stato, `proxy/entity_cache.inherited_attributes`: cosa l'entita' puo' fare,
    com'e' adesso, cio' di cui nessuna fonte dichiara il significato, e le
    credenziali che non escono di qui) alimenta DUE cose diverse, e non allo
    stesso modo:

    - `readable_state` lo legge SEMPRE, su ogni ramo che elenca entita'
      (dentro `_enrich_entity`), perche' e' un campo che gia' usciva
      ovunque e che per un termostato mentiva da solo -- vedi
      `topology.readable_state`. Il difetto misurato dal proprietario
      (2026-08-25): `hvac_mode: heat` con `hvac_action: idle` usciva come
      «heat», indistinguibile da un termostato che sta scaldando davvero.
    - Il dizionario `attributi` INTERO esce solo dal ramo `entita` (decisione
      del proprietario): un'area o un dispositivo elencano entita' a decine,
      e mettere tutti gli attributi di ognuna dentro quegli elenchi
      gonfierebbe la risposta di un dato che nessuno ha chiesto per la
      singola cosa. Il dettaglio di UNA entita' e' il momento in cui il
      modello ha gia' chiesto quella cosa precisa, e l'informazione si paga
      solo li'.

    `registry` (il registro dei servizi, `action/registry.ServiceRegistry`)
    serve al SOLO ramo `entita`, e per la stessa ragione per cui il dizionario
    `attributi` esce solo da li': e' il momento in cui il modello ha gia'
    chiesto quella cosa precisa. Con lui la vista dice anche COSA SI PUO'
    CHIEDERE a quell'entita' -- quali servizi, quali parametri, e i limiti
    veri, che sono quelli dell'entita' e non quelli del cursore generico del
    servizio (spec §13). `None` e' legittimo e non e' un guasto: chi non ce
    l'ha riceve la stessa vista senza la chiave `comandi`, mai una chiave
    vuota che direbbe «non c'e' niente da chiedere».

    Pura: legge `casa`/`comportamento`/`ricordi`/`stato` cosi' come arrivano
    dal chiamante (`HomeSpaceStore`, `MemoryStore`, lo stato vivo di Home
    Assistant), non apre archivi ne' chiama la rete.

    C-2 (L1-sicurezza.md): il testo di un ricordo passa dal sanitizzatore
    UNA volta, qui, prima di qualunque ramo -- per id diretto
    (`_view_memory`), ancorato a un'area/entita'/dispositivo
    (`_tethered_memories`, dentro i tre rami sopra) o ancorato a
    un'automazione/script (`_view_behavior`). Un punto solo, non uno
    per ramo: la fondamenta 3 (consistenza fra porte) e' anche questo -- lo
    stesso ricordo non deve poter uscire filtrato da una via e grezzo da
    un'altra. Il testo ARCHIVIATO non cambia (`memory/store.py`, regola
    1): questa e' una copia, non una riscrittura.
    """
    memories = sanitized_memories(memories)
    if kind == "area":
        return _view_area(home_space, memories, state, reference, unavailable,
                            fallback_names, reported_units, reported_classes,
                            reported_since_when, reported_attributes, translations)
    if kind == "entita":
        return _view_entity(home_space, memories, state, reference, unavailable,
                              fallback_names, reported_units, reported_classes,
                              reported_since_when, reported_attributes, registry,
                              translations)
    if kind == "dispositivo":
        return _view_device(home_space, memories, state, reference, unavailable,
                                   fallback_names, reported_units, reported_classes,
                                   reported_since_when, reported_attributes, translations)
    if kind in _BEHAVIOR_TYPES:
        return _view_behavior(behavior, memories, kind, reference, unread_bodies)
    if kind == "ricordo":
        return _view_memory(memories, reference)
    if kind == "integrazione":
        return _view_integration(home_space, state, reference, reported_since_when,
                                 unavailable, fallback_names, reported_units,
                                 reported_classes, reported_attributes, translations)
    # Un tipo che non conosciamo non e' un errore da sollevare: e' lo
    # stesso caso di "non l'ho trovato", solo con una causa diversa (il
    # modello ha nominato un tipo che non esiste, non un riferimento che
    # manca) -- e va dichiarato con la stessa onesta', non con un'eccezione
    # che gli spezza il turno.
    #
    # `non_so_guardare`: la causa e' un LIMITE DI HIRIS, non un fatto sulla
    # casa, e da quando esistono i legami quella differenza costa. `legami`
    # restituisce identificatori veri di cose vere -- una scena, un gruppo,
    # una persona -- che `guarda` non sa aprire: senza questa chiave il
    # modello chiedeva `guarda("scena", ...)`, leggeva `esiste: false` e
    # riferiva all'utente «quella scena non esiste», che e' una risposta
    # sbagliata detta con sicurezza su una cosa che Home Assistant gli aveva
    # appena mostrato. Stessa disciplina di `non_disponibile`: «non l'ho
    # trovato» e «non ho potuto guardare» sono due fatti diversi.
    return {"esiste": False, "tipo": kind, "riferimento": reference,
            "non_so_guardare": True}


def related(answer: dict, kind: str, reference) -> dict:
    """Chi tocca questa cosa, nella forma che il modello legge.

    Prende la risposta GIA' ottenuta da `HAClient.related()` -- questa
    funzione e' pura come le altre due, la rete la fa il chiamante
    (`home_space/tools.py`) -- e fa tre cose sole: distingue il guasto dal
    niente, traduce i tipi nel vocabolario di HIRIS, e ordina.

    **Il guasto non e' un «niente».** `legami: {}` e' un'affermazione:
    «questa cosa non la tocca nessuno e non sta da nessuna parte». Se Home
    Assistant non ha risposto, quell'affermazione nessuno ha il diritto di
    farla, e la risposta esce con `errore` -- una chiave diversa, non un
    elenco piu' corto. E' lo stesso principio con cui `HAClient.related`
    rifiuta di restituire `{}` su un rifiuto, portato fino al modello: un
    guasto dichiarato al client e appiattito qui sarebbe un guasto taciuto.

    **La traduzione.** Le chiavi arrivano come le manda Home Assistant
    (`entity`, `automation`, ...) ed escono come le nomina HIRIS (`entita`,
    `automazione`): sono gli stessi nomi di `cerca` e di `guarda`, cosi' un
    `riferimento` letto qui si passa di li' senza tradurlo a mano -- e senza
    che il modello debba imparare due vocabolari per la stessa casa
    (fondamenta: consistenza). Una chiave che Home Assistant aggiungesse
    domani e che questa tabella non conosce passa COSI' COM'E': un nome non
    tradotto e' un fastidio, una riga buttata sarebbe una perdita silenziosa.

    **Cosa questa funzione NON fa: raggruppare.** Per un'entita' la risposta
    di Home Assistant mescola chi la USA (automazioni, script, scene, gruppi,
    persone) con dove STA (area, dispositivo, piano, integrazione) --
    verificato sul sorgente, `_async_search_entity` fa entrambe le cose. La
    tentazione e' dividerle in due gruppi, ma il significato delle stesse
    chiavi cambia col tipo chiesto: per un'AREA le entita' elencate sono cio'
    che l'area contiene, non dove l'area sta. Un raggruppamento fisso sarebbe
    giusto per un tipo e falso per gli altri, quindi non si raggruppa: si
    lascia la struttura di Home Assistant e si spiega al modello (nella
    descrizione dello strumento) come leggerla.
    """
    if not isinstance(answer, dict) or "errore" in answer:
        reason = (answer.get("errore") if isinstance(answer, dict)
                  else "risposta in forma inattesa")
        return {"errore": (
            f"non ho potuto sapere chi tocca «{reference}»: {reason}. "
            "Non e' un «non la tocca nessuno»: e' una domanda a cui Home "
            "Assistant non ha risposto, e il legame potrebbe esserci.")}
    translated = {LINK_NAME.get(key, key): list(values)
                for key, values in answer.items()}
    # Ordinate per nome: Home Assistant manda un dizionario costruito da
    # insiemi, e due letture identiche produrrebbero due risposte con le
    # chiavi in ordine diverso. I VALORI li ordina gia' il client, e per la
    # stessa ragione.
    return {"tipo": kind, "riferimento": reference,
            "legami": {name: translated[name] for name in sorted(translated)}}
