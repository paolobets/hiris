"""Le due domande di dettaglio: guardare una cosa, chiedere i legami.

Il nucleo (briefing.py) dice DOVE sono le cose -- conta, non elenca. Le due
funzioni qui sotto danno il DETTAGLIO, quando il modello (o l'utente dalla
pagina) lo chiede esplicitamente:

- view -- il dettaglio di UNA cosa sola: un'area con le sue entita' e i
  loro stati, un'entita' col suo stato e la sua classe, un'automazione o uno
  script col loro corpo, un dispositivo con le sue entita', un ricordo con
  la sua interpretazione. Dal 29/09/2026 non e' piu' uno strumento: e' la
  voce di `search` quando l'insieme ne ha una sola
  (`house_query.query_house`).
- related -- CHI tocca questa cosa, secondo Home Assistant. Non e' un
  secondo modo di guardare la stessa cosa: view porta il CORPO (cosa fa
  quell'automazione), `related` porta i LEGAMI
  (quali automazioni, script, scene o gruppi nominano questa entita'). Sono
  due fatti diversi sullo stesso oggetto, e tenerli in due risposte e' cio'
  che li tiene distinti -- la confusione fra «dichiarato» e «dedotto» questo
  progetto la paga da sempre.

Fino al 29/09/2026 c'era anche `search(indice, testo)`, la ricerca per nome
sull'indice di `memory/resolver.py`: la porta della casa
(`home_space/house_query.py`) confronta i nomi da se' e l'ha resa codice
morto, cancellato con lei (spec «una porta sola per la casa»).

Un tipo nuovo di "cosa" si aggiunge come un altro `if` dentro view, non
come uno strumento in piu' (vedi docs/design/2026-08-05-la-conoscenza-di-
hiris.md: trentaquattro strumenti con tre copie divergenti).

Tutte e due prendono dati gia' letti dal chiamante (la casa, il
comportamento, i ricordi, lo stato vivo, la risposta che Home Assistant ha
gia' dato) e non chiamano la rete -- la stessa scelta che rende `compose()`
del nucleo verificabile senza finti elaborati (briefing.py). Vale anche per
`related`: la chiamata WebSocket la fa il chiamante (`home_space/tools.py`),
qui arriva solo cio' che ha risposto. **Una lettura d'archivio c'e'**: sul
ramo `entita`, `view` chiede al sapere cosa significa la classe
(`_class_meaning`), quando il chiamante gli passa `knowledge`.

**Un silenzio non dichiarato e' indistinguibile da un'assenza di
problemi** (pagato sedici volte su questo ramo, sempre trovato da una
review, mai dalla suite). Per questo view restituisce SEMPRE la chiave
`esiste`, e quando e' `False` non inventa il resto: nessun `entita: []`,
nessun `corpo: None` che si potrebbe scambiare per un fatto sulla casa
invece che per "non trovato". E «non ho il corpo» (un limite di HIRIS --
`corpo: None` con un `origine` che lo dichiara) resta distinto da «il
corpo e' vuoto» (un fatto sulla casa: `corpo: {}` o simile).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..proxy._sanitize import sanitize_structure, sanitize_text
from ..proxy.entity_cache import (
    disclosable_attributes,
    withheld_credentials,
)
from .behavior import BEHAVIOR_DOMAINS
from .ha_vocabulary import LINK_NAME, domain_of, entity_category_measure_rule
from .historian import instant_epoch
from .reference import normalize
from .render import (
    _BASKET_NAMES,
    _MEMBERS_KEY,
    _RAW_ATTRIBUTES_WITH_THEIR_OWN_DOOR,
    _WITHHELD_BASKET,
    _add_labels,
    _class_meaning,
    _enrich_entity,
    commands_for,
    group_membership,
)
from .topology import (
    Mirror,
    category_names,
    device_name,
    is_pseudo_area,
    label_names,
    live_name,
    visibility,
    visibility_classes,
)
from .type_judgments import TypeJudgments
from .type_vocabulary import REPO_JUDGMENTS, STATE_UNAVAILABLE, STATE_UNKNOWN

if TYPE_CHECKING:
    from .house import House

# I tipi di comportamento che `view` sa mostrare col loro corpo. Un
# "automazione" e uno "script" sono voci dello stesso elenco
# (behavior.py), non due archivi diversi: la distinzione e' nel campo
# `tipo` della voce, non nella provenienza. I due nomi si chiedono a
# `behavior.BEHAVIOR_DOMAINS` (B-23, 04/10/2026), non si riscrivono.
_BEHAVIOR_TYPES = frozenset(BEHAVIOR_DOMAINS.values())



def _tethered_memories(memories: list[dict], kind: str, reference) -> list[dict]:
    """I ricordi di `memories` che portano un'ancora (tipo, riferimento)
    uguale a quella cercata -- stessa chiave di `MemoryStore.per_tether`
    (memory/store.py), ma su una lista gia' in memoria: `view` e'
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


def _search_suggestion(reference) -> str:
    """Il messaggio che accompagna un `esiste: False` sui tre rami che
    possono confondere un NOME con un id -- area, entita', dispositivo.

    R5 (2026-08-20, misurato dal vivo): il modello chiama `view` con un
    nome («Soggiorno») al posto dell'id (`soggiorno`), e riceveva
    `{"esiste": False}` nudo -- indistinguibile da "quest'area non esiste
    davvero", nessun invito a `search`. E' il meccanismo diretto
    dell'incidente che ha generato questa fetta: il modello ritenta uguale
    finche' il turno muore.

    Il pattern esiste gia' in `action/verification.py::_no` per il bersaglio
    non risolto («Usa «search» per trovare il nome giusto e ripeti il
    comando») -- questa funzione lo estende a `view`, non lo reinventa:
    UNA sola sorgente per i tre rami (fondamenta 3, "stessa forma"), cosi'
    che togliere il richiamo da un ramo solo non lascia gli altri due
    invariati -- si nota, perche' la frase e' la stessa ovunque.
    """
    return (f"«{reference}» non e' stato trovato. Se e' un NOME (non un "
            f"id), chiama «search» con questo testo per trovare l'id giusto, "
            f"poi ripeti «search» con quello come `riferimento`.")


def _not_found_detail(kind: str, reference, unavailable: bool) -> dict:
    """Il dict `esiste: False` comune ai rami che possono confondere un
    NOME con un id -- area, entita', dispositivo, e da T7 (R2) anche
    automazione/script (`_view_behavior`, sotto).

    "non trovato" ha due cause DIVERSE (CRITICAL ③, gia' pagato piu' volte
    su questo file): il riferimento non c'e' davvero, oppure il registro
    che lo conterrebbe non ha risposto. Sono anche due RIMEDI diversi, non
    solo due dichiarazioni:

    - riferimento assente -> `suggerimento` (invita a `search`, potrebbe
      essere un nome scambiato per un id);
    - registro caduto -> SOLO `non_disponibile`, MAI `suggerimento`:
      `search` legge la STESSA anagrafe incompleta, quindi "prova a
      cercare" sarebbe una strada altrettanto cieca -- e diluirebbe
      proprio la distinzione che `non_disponibile` esiste per marcare
      (review indipendente Task 3, confermata: suggerire quando la causa
      e' un guasto e' un rischio, non un aiuto).

    Un punto solo per questa scelta: i rami non portano una copia ciascuno
    della stessa condizione, e chi la cambia la cambia qui una volta sola.

    `_view_behavior` chiama questa funzione come gli altri tre rami.
    """
    detail = {"esiste": False, "tipo": kind, "riferimento": reference}
    if kind is None:
        # Un `riferimento` dato alla porta senza genere (`house_query`, dal
        # 30/09/2026): il tipo non si inventa.
        del detail["tipo"]
    if unavailable:
        detail["non_disponibile"] = True
    else:
        detail["suggerimento"] = _search_suggestion(reference)
    return detail


def _entity_rows(entries: list[dict], mirror: Mirror, disabled: bool,
                 label_lookup: dict[str, str],
                 category_lookup: dict[tuple[str, str], str],
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
            {"id": e["id"], "nome": live_name(e["id"], e.get("nome"), mirror),
             "stato": mirror.state.get(e["id"]),
             "da_quando": mirror.since.get(e["id"]),
             "disabilitata": disabled},
            e, mirror, label_lookup, category_lookup, translations)
        for e in entries
    ]


#: Il tetto delle righe di UNA risposta della porta della casa (spec
#: `2026-09-29-una-porta-sola-per-la-casa.md` §2.3): le voci di un insieme
#: (`house_query`) e le entita' annidate nel dettaglio completo di un'area, di
#: un dispositivo o di un'integrazione. Vive qui e non nella porta perche' il
#: dettaglio si costruisce qui, e la porta lo importa: una cifra sola.
ROWS_MAX = 50

#: Gli elenchi di righe annidati nel dettaglio completo, nell'ordine in cui
#: si spende il tetto: prima le visibili, poi le nascoste.
_NESTED_ROWS = ("entita", "entita_nascoste")


def _within_ceiling(detail: dict, hint: str) -> dict:
    """Il dettaglio completo sotto il tetto della porta, per costruzione.

    **Il tetto sta nella regola** (spec §2.3): fino al 30/09/2026 il dettaglio
    di un'area elencava ogni sua entita' -- Telecamere 287, ~64.000
    caratteri; «senza area» ~126.000 -- e sul ponte il risultato superava i
    25.000 token che la CLI accetta, e diventava un rimando a un file che il
    modello non puo' leggere (spec §1, causa 2). Qui le righe annidate si
    fermano a `ROWS_MAX` IN TUTTO, visibili prima; cio' che resta si dichiara
    in `oltre` con il modo di chiederlo -- mai tagliato in silenzio."""
    budget = ROWS_MAX
    left: dict = {}
    for key in _NESTED_ROWS:
        rows = detail.get(key)
        if not rows:
            continue
        kept = rows[:budget]
        budget -= len(kept)
        if len(rows) > len(kept):
            left[key] = len(rows) - len(kept)
        if kept or key == "entita":
            detail[key] = kept
        else:
            del detail[key]
    if left:
        detail["oltre"] = {**left, "suggerimento": hint}
    return detail


def _view_area(house: House, memories: list[dict], reference,
               translations: dict | None = None) -> dict:
    home_space, mirror, unavailable = house.home_space, house.mirror, house.unavailable
    # `unavailable` va PROPAGATO, non solo ricevuto: senza, `hierarchy()`
    # crede che sia andato tutto bene e un'entita' che eredita l'area dal
    # proprio dispositivo -- col registro dispositivi caduto -- finisce in
    # "Senza area" invece che in "Dispositivi non letti". Risultato: una
    # cucina con cinque luci ne mostra quattro, con `esiste: True` e nessun
    # avviso: la stessa forma di una cucina davvero piu' piccola.
    #
    # L'albero e' quello dell'istantanea (`House.hierarchy`), calcolato una
    # volta per turno: fino al 04/10/2026 questa porta se ne rifaceva uno.
    floors = house.hierarchy()
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
    # Le DISABILITATE si contano, non si elencano (30/09/2026, review finale
    # della fetta «una porta sola», C2). Fino ad allora restavano dentro
    # `entita`, marcate: sulla casa vera l'area Telecamere ne porta 120 su
    # 287, con lo stato vuoto -- righe che non dicono niente e che portavano
    # il dettaglio a ~64.000 caratteri, oltre il limite del ponte. E' la
    # regola della porta per ogni insieme («disabilitate sempre escluse e
    # contate», spec §2.4), e `_view_integration` la applicava gia'.
    entity = _entity_rows(area["entita"], mirror, False, label_lookup, category_lookup,
                          translations)
    disabled_count = len(area.get("entita_disabilitate") or [])
    # Le NASCOSTE, invece, in una chiave A PARTE -- non marcate dentro
    # `entita` come le disabilitate qui sopra (fetta "nascoste fuori dagli
    # elenchi", 2026-08-25). Il proprietario ha misurato in produzione che
    # `view("area", "sala_da_pranzo")` elencava sette luci mescolate,
    # quattro nascoste, col campo `nascosta` gia' presente su ognuna: stare
    # nella STESSA lista non ha impedito che venissero nominate lo stesso.
    # La regola voluta -- "HIRIS non considera le nascoste, a meno che non
    # gli vengano chieste esplicitamente" -- si applica per STRUTTURA: il
    # modello che legge `entita` per rispondere "quali luci ci sono in sala
    # da pranzo" non le vede affatto, senza dover ricordare di filtrarle da
    # un campo. Restano pero' COMPLETE e raggiungibili qui, per la stessa
    # domanda esplicita -- "cosa hai nascosto?" -- che il campo `nascosta`
    # serviva gia' quando l'entita' si guarda da sola (`_view_entity`).
    hidden_entities = _entity_rows(area.get("entita_nascoste", []), mirror, False,
                                   label_lookup, category_lookup, translations)
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
    if disabled_count:
        detail["entita_disabilitate"] = disabled_count
    # Il filtro della porta si scrive col nome che il nucleo usa: le
    # pseudo-aree (`__senza_area__` e le sorelle) sono tutte «senza area».
    where = "senza area" if is_pseudo_area(area["id"]) else area["id"]
    _within_ceiling(detail, f"chiedi «search» con area=\"{where}\" e un filtro "
                            "(tipo, stato, classe): l'insieme si restringe, e "
                            "la porta lo pagina con `oltre` e `salta`")
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


def _view_entity(house: House, memories: list[dict], reference,
                 registry=None,
                 translations: dict | None = None,
                 knowledge=None,
                 judgments: TypeJudgments = REPO_JUDGMENTS) -> dict:
    home_space, mirror, unavailable = house.home_space, house.mirror, house.unavailable
    entity = next((e for e in home_space.get("entita") or [] if e.get("id") == reference), None)
    if entity is None:
        # Col registro "entita" caduto (una lettura parziale lascia la
        # tabella vuota), un'entita' vera non trovata qui non e'
        # un'entita' che non esiste -- e' un registro che non ha risposto.
        return _not_found_detail("entita", reference, "entita" in unavailable)
    detail = {
        "esiste": True, "tipo": "entita", "id": entity["id"],
        "nome": live_name(entity["id"], entity.get("nome"), mirror),
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
        # campo dice perche' `view` la trova comunque, senza far credere
        # che sia una stanza arredata (stesso principio di topology.py).
        "disabilitata": visibility(entity)[0] == "disabilitata",
        "stato": mirror.state.get(entity["id"]),
        "da_quando": mirror.since.get(entity["id"]),
        "ricordi": _tethered_memories(memories, "entita", reference),
        # DOVE sta (Tappa 3, Task 6, B-10): area -- ereditata dal
        # dispositivo, se non ne ha una propria --, piano, dispositivo e
        # integrazione, da `House.where`. Fino al 04/10/2026 la scheda di
        # un'entita' non diceva in che stanza fosse: il modello doveva
        # cercarla nell'albero del nucleo, dove una disabilitata non c'e'.
        "dove": house.where(entity["id"]),
        # LA FONTE (Tappa 3, Task 8, B-25; D6): perche' parla o tace --
        # spenta dal proprietario o da Home Assistant, integrazione ferma,
        # non disponibile, senza valore, sparita -- con la causa che Home
        # Assistant scrive, da `House.source`. Fino al 04/10/2026 la scheda
        # diceva solo `disabilitata: true` e lo stato grezzo.
        "fonte": house.source(entity["id"]),
    }
    detail = _enrich_entity(detail, entity, mirror, label_names(home_space),
                            category_names(home_space), translations)
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
        domain_of(entity["id"]), dict(visibility_classes(entity)).get("servizio"),
        detail.get("classe"), detail.get("unita"))
    if rule:
        detail["regola"] = rule
    # COSA SIGNIFICA LA CLASSE, dal sapere (fetta «il sapere e le ricette»,
    # 12/09/2026). E' il lettore che rende vero quell'archivio: fino a ieri il
    # significato di una classe viveva in una tabella a mano di 27 voci, e
    # delle altre HIRIS non sapeva dire niente -- misurate il 12/09, 44 classi
    # di `sensor` su 62 e 28 su 28 di `binary_sensor`.
    #
    # **Dal sapere e non dalle traduzioni**, che pure sono gia' qui: le due
    # cose non coincidono. Home Assistant pubblica un NOME («Potenza»), il
    # repo dove ha guardato porta una frase che dice cosa quel valore E' («la
    # potenza ISTANTANEA, non un'energia»), e il sapere tiene la piu' ricca.
    # Leggere le traduzioni direttamente da qui perderebbe proprio quella.
    #
    # **Tace quando non sa**, come `regola` qui sopra: nessuna chiave, mai una
    # stringa vuota. E non chiede niente per un'entita' senza classe -- sarebbe
    # una domanda su una riga che non puo' esistere, ripetuta per la
    # maggioranza delle entita' di questa casa.
    meaning = _class_meaning(knowledge, domain_of(entity["id"]), detail.get("classe"))
    if meaning:
        detail["significato"] = meaning
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
    # LE CESTE, e perche' sono chiavi distinte e non un dizionario piatto:
    # «cosa puo' fare», «cosa puo' assumere», «com'e' adesso» e «non so cosa
    # sia» sono fatti di qualita' diversa (`_BASKET_NAMES`), e appiattirli
    # consegnerebbe `ave_window_state: 0` accanto a `hvac_modes` come se
    # fossero la stessa qualita' di sapere. In piu' c'e' `trattenuti`: la
    # sola trattenuta di questo prodotto resa VISIBILE -- nome e ragione, mai
    # il valore, mai un silenzio.
    attributes = mirror.attributes.get(entity["id"])
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
    membership = group_membership(entity["id"], mirror.attributes)
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
                            disclosable_attributes(mirror.attributes.get(entity["id"])),
                            judgments=judgments)
    if commands:
        detail["comandi"] = commands
    return detail


def _view_device(house: House, memories: list[dict], reference,
                 translations: dict | None = None) -> dict:
    home_space, mirror, unavailable = house.home_space, house.mirror, house.unavailable
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
    #
    # Le DISABILITATE si contano in `entita_disabilitate`, come nell'area e
    # nell'integrazione (re-review della fetta «una porta sola», 30/09/2026):
    # elencate dentro `entita` spendevano il tetto di `ROWS_MAX` righe con
    # voci senza stato. La regola della porta e' una: «disabilitate sempre
    # escluse e contate» (spec §2.4). `disabilitato` del dispositivo resta.
    raw_device_entities = house.device_entities(reference)
    # La classe dalla regola unica (B-01): qui era scritta in linea.
    classes = [(e, visibility(e)[0]) for e in raw_device_entities]
    disabled_count = sum(1 for _e, cls in classes if cls == "disabilitata")
    raw_hidden = [e for e, cls in classes if cls == "nascosta"]
    raw_visible = [e for e, cls in classes if cls not in ("disabilitata", "nascosta")]
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
            {"id": e["id"], "nome": live_name(e["id"], e.get("nome"), mirror),
             "stato": mirror.state.get(e["id"]),
             "da_quando": mirror.since.get(e["id"]),
             "disabilitata": False},
            e, mirror, label_lookup, category_lookup, translations)
        for e in raw_visible
    ]
    device_hidden_entities = _entity_rows(
        raw_hidden, mirror, False, label_lookup, category_lookup, translations)
    detail = {
        "esiste": True, "tipo": "dispositivo", "id": device["id"],
        "nome": device_name(device),
        "disabilitato": bool(device.get("disabilitato")),
        "entita": device_entities,
        "ricordi": _tethered_memories(memories, "dispositivo", reference),
    }
    # Solo quando ce n'e' almeno una -- stessa disciplina della porta area.
    if device_hidden_entities:
        detail["entita_nascoste"] = device_hidden_entities
    if disabled_count:
        detail["entita_disabilitate"] = disabled_count
    # Lo stesso tetto dell'area: un dispositivo «Home Assistant» ne porta 55.
    _within_ceiling(detail, "chiedi «search» con un filtro (tipo, stato, "
                            "integrazione, area) per restringere l'insieme, o "
                            "con `riferimento` = l'id di un'entita' per il suo "
                            "dettaglio")
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
        # "Non trovato" non e' "non esiste" quando di qualche automazione o
        # script non si conosce il corpo: `unread_bodies` gioca lo stesso
        # ruolo di `unavailable` per area/entita'/dispositivo (un guasto di
        # lettura, non l'assenza della cosa). Non si prova a indovinare se
        # QUESTA voce sia fra quelle: se una qualsiasi manca, l'incertezza si
        # dichiara. Altrimenti il `suggerimento` e' lo stesso degli altri
        # rami, con la stessa frase (`_not_found_detail`).
        return _not_found_detail(kind, reference, bool(unread_bodies))
    return {
        "esiste": True, "tipo": kind, "id": entry["id"], "nome": entry.get("nome"),
        # **Il corpo passa dal confine** (reperto B-1, 22/09/2026), e passa
        # QUI e non in archivio. L'esenzione di prima aveva una ragione
        # scaduta -- «e' un file locale che il proprietario modifica» -- e dal
        # 10/09/2026 il corpo arriva da `automation/config`, quindi anche da
        # un blueprint importato da un indirizzo di community.
        #
        # **Perche' qui e non dove si archivia**, che sarebbe il posto
        # naturale accanto al sigillo dei segreti: quel corpo lo legge anche
        # `action/construction/workshop.py` come «prima» di una modifica, e
        # quel «prima» e' cio' che un ripristino RISCRIVE in Home Assistant.
        # Sanificare in archivio vorrebbe dire mettere «[FILTERED]» dentro
        # un'automazione vera del proprietario. L'archivio tiene la verita';
        # chi compone per il modello la filtra.
        #
        # `None` (HIRIS non l'ha -- e `unread_bodies` dice perche') resta
        # `None`: un corpo assente e un corpo vuoto ma presente sono due
        # valori diversi, e il confine non li confonde riscrivendoli.
        "corpo": (None if entry.get("corpo") is None
                  else sanitize_structure(entry.get("corpo"))),
        "ricordi": _tethered_memories(memories, kind, reference),
    }


def _view_memory(memories: list[dict], reference) -> dict:
    memory = next((r for r in memories if r.get("id") == reference), None)
    if memory is None:
        return {"esiste": False, "tipo": "ricordo", "riferimento": reference}
    # La forma e' PIATTA, la stessa di `fetch` e dei `ricordi` che ogni
    # altro ramo di `view` gia' restituisce (`_tethered_memories`).
    #
    # Prima l'interpretazione era annidata sotto una chiave `interpretazione`
    # e `detto_il` non usciva affatto: lo stesso ricordo aveva due forme a
    # seconda della porta. Il modello ne imparava una dentro
    # `view("area", ...)`, poi chiedeva il dettaglio con
    # `view("ricordo", id)` e leggeva `r["forza"]` -> assente, e riferiva
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
        # La chiave stabile del soggetto (Task 6, decisione 5) -- stessa forma
        # di `fetch` e di `/api/memories`, che la portano gia' perche' leggono
        # la riga intera: qui il dettaglio e' composto a mano, e senza questa
        # riga sarebbe l'unica porta a tacerla (fondamenta 3).
        "said_by": memory.get("said_by"),
        "detto_il": memory.get("detto_il"),
        "forza": memory.get("forza"), "grandezza": memory.get("grandezza"),
        "minimo": memory.get("minimo"), "massimo": memory.get("massimo"),
        "unita": memory.get("unita"),
        "ancore": memory.get("ancore") or [],
        "condizioni": memory.get("condizioni") or [],
    }
    return detail


def sanitized_memories(memories: list[dict] | None, house: House | None = None) -> list[dict]:
    """I ricordi con `testo` passato dal sanitizzatore -- funzione condivisa,
    non una riga ripetuta a ogni porta che restituisce ricordi al modello.

    **Con la casa, ogni ancora porta `nome_attuale` ed `esiste`**
    (`House.tether`, G-21, Tappa 8, Task 1): la stessa forma che la pagina
    Memoria mostra, cosi' il modello puo' dire «quell'entita' non c'e' piu'»
    invece di riferire un'ancora grezza come viva. Il nucleo la chiama senza
    casa: le sue righe non stampano le ancore.

    C-2/I1 (L1-sicurezza.md, review indipendente del 25/08/2026): la prima
    versione di questa correzione sanificava il testo dentro `view()` ma
    non dentro `tools.py::_recall` (che legge `MemoryStore.per_tether`
    direttamente, senza passare da qui) -- lo stesso ricordo usciva filtrato
    da una porta e grezzo dall'altra: la fondamenta 3 (consistenza fra porte)
    rotta dentro la correzione che doveva chiuderla. Un punto SOLO, importato
    da entrambe le porte, e' l'unico modo per cui questo non possa ripetersi
    con una terza porta futura.

    Il testo ARCHIVIATO non cambia (`memory/store.py`, regola 1): questa
    e' una copia, non una riscrittura -- vedi il docstring di `view()`."""
    out = []
    for r in memories or []:
        copy = dict(r, testo=sanitize_text(r["testo"])) if "testo" in r else r
        if house is not None and isinstance(r.get("ancore"), list):
            copy = dict(copy, ancore=[house.tether(a) if isinstance(a, dict) else a
                                      for a in r["ancore"]])
        out.append(copy)
    return out


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


def _view_integration(house: House, reference,
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

    `reference` si normalizza (`reference.normalize`, quella del riferimento)
    prima del confronto -- passata da `str()` prima, perche' lo schema dello
    strumento ammette anche un intero (`riferimento: ["string", "integer"]`,
    tools.py) e `normalize` chiama `.lower()`, che un intero non ha. Il
    modello puo' scrivere questo `riferimento` a mano -- ed e' l'UNICO ramo di
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
    home_space, mirror, unavailable = house.home_space, house.mirror, house.unavailable
    domain = normalize(str(reference or ""))
    matching = [e for e in home_space.get("entita") or []
                if normalize(e.get("piattaforma") or "") == domain]
    entries = [{"titolo": i.get("titolo"), "stato": i.get("stato"), "motivo": i.get("motivo")}
               for i in home_space.get("integrazioni") or []
               if normalize(i.get("dominio") or "") == domain]
    if not matching and not entries:
        return _not_found_detail("integrazione", reference,
                                  "entita" in unavailable or "integrazioni" in unavailable)
    # D7: questa porta conta ogni classe tranne le disabilitate (i totali
    # dell'integrazione sono tutte le sue entita' che hanno uno stato).
    own = [e for e in matching if visibility(e)[0] != "disabilitata"]
    disabled = [e for e in matching if visibility(e)[0] == "disabilitata"]
    # I due stati dal vocabolario, col loro nome (B-09, B-55; Tappa 3, Task 8).
    mute = [e for e in own if mirror.state.get(e["id"]) == STATE_UNAVAILABLE]
    unknown = [e for e in own if mirror.state.get(e["id"]) == STATE_UNKNOWN]
    detail = {
        "esiste": True, "tipo": "integrazione", "dominio": domain,
        "voci": entries,
        "entita_totali": len(own),
        "entita_mute": len(mute),
        # `disabilitata=False` non e' un'ipotesi: `mute` esce da `own`, che
        # ha gia' tolto le disabilitate qualche riga sopra.
        "entita": _entity_rows(mute, mirror, False, label_names(home_space),
                               category_names(home_space),
                               translations),
    }
    # `entita` sono le mute, e `entita_mute` resta il loro numero intero.
    _within_ceiling(detail, f"chiedi «search» con integrazione=\"{domain}\" e "
                            "stato=\"unavailable\": la porta pagina l'insieme con "
                            "`oltre` e `salta`")
    if unknown:
        detail["entita_stato_ignoto"] = len(unknown)
    if disabled:
        detail["entita_disabilitate"] = len(disabled)
    incomplete = sorted(set(unavailable) & {"entita", "integrazioni"})
    if incomplete:
        detail["elenco_incompleto"] = incomplete
    moments = [mirror.since.get(e["id"]) for e in mute]
    if moments and all(moments):
        epochs = [instant_epoch(m) for m in moments]
        if all(ep is not None for ep in epochs):
            earliest, latest = min(epochs), max(epochs)
            if latest - earliest <= _SYNCHRONY_WINDOW_SECONDS:
                detail["mute_da"] = moments[epochs.index(earliest)]
    if "mute_da" in detail:
        ha_start = mirror.state.get("sensor.uptime")
        if ha_start and instant_epoch(ha_start) is not None:
            detail["avvio_home_assistant"] = ha_start
    return detail


def view(house: House, behavior: list[dict], memories: list[dict],
         kind: str, reference,
         unread_bodies: dict[str, str] | None = None,
         registry=None,
         translations: dict | None = None,
         knowledge=None,
         judgments: TypeJudgments = REPO_JUDGMENTS) -> dict:
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
    trattamento delle disabilitate e' voluta: quelle, nel dettaglio di
    un'area, di un dispositivo e di un'integrazione, si CONTANO
    (`entita_disabilitate`, dal 30/09/2026: Telecamere ne elencava 120 con lo
    stato vuoto), perche' non hanno uno stato da dire; le nascoste sono una scelta
    di VISTA dell'utente, e la misura in produzione (`view("area",
    "sala_da_pranzo")`, sette luci mescolate, quattro nascoste) ha mostrato
    che marcarle SENZA separarle non basta -- il campo c'era gia' e non ha
    impedito che venissero elencate. Una singola entita' guardata da sola
    (`_view_entity`) continua a portare il campo `nascosta` invece che una
    chiave a parte: non c'e' un elenco da cui separarla, hai chiesto
    esplicitamente proprio lei.

    Sui rami che possono confondere un NOME con un id -- area, entita',
    dispositivo, automazione e script -- `esiste: False`
    porta anche `suggerimento` (`_search_suggestion`): invita a chiamare
    `search` col riferimento ricevuto. STESSA chiave, STESSA frase su tutti
    questi rami (fondamenta 3) -- non su `_view_memory`, il solo tipo il
    cui id (numerico, interno a HIRIS, mai uno slug di Home Assistant) non
    si scrive mai al posto di un nome.

    MA non quando `non_disponibile` e' vero (`_not_found_detail`): se
    il registro e' caduto, `search` legge la STESSA anagrafe incompleta --
    suggerirlo sarebbe una strada altrettanto cieca, e diluirebbe la
    distinzione fra "non trovato" e "non ho potuto guardare" che questo
    modulo marca come critica. Le due chiavi sono quindi mutuamente
    esclusive su questi tre rami: mai `suggerimento` insieme a
    `non_disponibile`.

    E `esiste: False` ha due cause diverse, che da questa fetta si vedono:
    il riferimento non c'e' (le funzioni `_view_*` qui sopra), oppure il TIPO
    non e' fra quelli che HIRIS sa aprire -- e allora esce anche
    `non_so_guardare: True`, perche' una scena o un gruppo che `related()`
    ha appena mostrato esistono eccome, e dirne «non esiste» sarebbe una
    risposta sbagliata detta con sicurezza.

    `house.unavailable` (registri dell'anagrafe caduti: "aree", "dispositivi",
    "entita") e `unread_bodies` (i corpi non letti, stessa
    forma di `HomeSpace.unread_bodies()`) vanno propagati a OGNI ramo,
    non solo a quello dell'area: un "non trovato" e un "non ho potuto
    guardare" sono due fatti diversi. Chi
    non li passa non e' punito con un errore: resta silenziosamente onesto,
    non silenziosamente sbagliato -- vedi `dettaglio["non_disponibile"]`,
    presente solo quando `esiste` e' `False` E il registro pertinente
    non ha risposto.

    `house` e' l'istantanea della casa di questo turno (`house.House`, dal
    04/10/2026): l'anagrafe (`house.home_space`), i registri caduti
    (`house.unavailable`), la gerarchia calcolata una volta
    (`house.hierarchy()`) e lo specchio dello stato in una forma
    (`house.mirror`, `topology.Mirror`; fino a quel giorno erano sei
    argomenti separati, B-41). Dello specchio:

    `mirror.names` (entity_id -> friendly_name, stessa forma usata da
    `costruisci_indice`) da' il `nome` in OGNI ramo che elenca entita' --
    `entita` da sola, ma anche le entita' di un'`area` e di un `dispositivo`
    (I1, review finale: la stessa entita' e' la stessa cosa da tutte le
    porte) -- con la regola di `topology.live_name` (D1, 04/10/2026): il
    nome che Home Assistant mostra, poi quello del registro, poi l'id.

    `mirror.since` (entity_id -> `last_changed`, stessa forma di
    `mirror.units`/`mirror.classes`) accompagna OGNI `"stato"` che
    esce da questa funzione: il campo che Home Assistant manda a ogni cambio
    di stato e che la proiezione della cache scartava (fondamenta 3 -- la
    stessa domanda non puo' avere due risposte diverse a seconda di quale
    ramo di `view` la porta).

    `mirror.attributes` (entity_id -> le ceste di
    `proxy/entity_cache.inherited_attributes`) alimenta DUE cose
    diverse, e non allo stesso modo:

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

    Legge `house`/`behavior`/`memories` cosi' come arrivano
    dal chiamante (`HomeSpace`, `MemoryStore`, lo stato vivo di Home
    Assistant) e non chiama la rete. Un archivio lo apre in un caso solo: sul
    ramo `entita`, con `knowledge` passato, `_class_meaning` chiede al sapere
    cosa significa la classe.

    C-2 (L1-sicurezza.md): il testo di un ricordo passa dal sanitizzatore
    UNA volta, qui, prima di qualunque ramo -- per id diretto
    (`_view_memory`), ancorato a un'area/entita'/dispositivo
    (`_tethered_memories`, dentro i tre rami sopra) o ancorato a
    un'automazione/script (`_view_behavior`). Un punto solo, non uno
    per ramo: la fondamenta 3 (consistenza fra porte) e' anche questo -- lo
    stesso ricordo non deve poter uscire filtrato da una via e grezzo da
    un'altra. Il testo ARCHIVIATO non cambia (`memory/store.py`, regola
    1): questa e' una copia, non una riscrittura.

    `judgments` e' l'istantanea dei giudizi sui tipi (spec 2026-09-16 §3):
    la inoltra soltanto, a `_view_entity` -> `commands_for` ->
    `_command_parameters` -> `_limits_of_entity` (il solo ramo che li legge).
    Arriva come ARGOMENTO, come `house`. In
    produzione e' sempre l'istantanea viva, `app["type_judgments"]` (via
    `home_space/tools.py::ToolDispatcher._full_detail_sync`); il predefinito
    `REPO_JUDGMENTS` -- il solo seme del repo -- serve alle prove. Una prova
    strutturale (`tests/test_judgments_passed_in_production.py`) boccia ogni
    chiamata di produzione a questa funzione senza `judgments=`; una prova dal
    lettore (`tests/test_queries.py::
    test_una_correzione_su_limiti_arriva_dalla_vista_intera_non_solo_dalla_foglia`)
    sorveglia che la catena interna -- che quella prova strutturale non guarda
    -- lo inoltri davvero fino a `_limits_of_entity`.
    """
    memories = sanitized_memories(memories, house)
    if kind == "area":
        return _view_area(house, memories, reference, translations)
    if kind == "entita":
        return _view_entity(house, memories, reference, registry,
                            translations, knowledge, judgments=judgments)
    if kind == "dispositivo":
        return _view_device(house, memories, reference, translations)
    if kind in _BEHAVIOR_TYPES:
        return _view_behavior(behavior, memories, kind, reference, unread_bodies)
    if kind == "ricordo":
        return _view_memory(memories, reference)
    if kind == "integrazione":
        return _view_integration(house, reference, translations)
    # Un tipo che non conosciamo non e' un errore da sollevare: e' lo
    # stesso caso di "non l'ho trovato", solo con una causa diversa (il
    # modello ha nominato un tipo che non esiste, non un riferimento che
    # manca) -- e va dichiarato con la stessa onesta', non con un'eccezione
    # che gli spezza il turno.
    #
    # `non_so_guardare`: la causa e' un LIMITE DI HIRIS, non un fatto sulla
    # casa, e da quando esistono i legami quella differenza costa. `legami`
    # restituisce identificatori veri di cose vere -- una scena, un gruppo,
    # una persona -- che `view` non sa aprire: senza questa chiave il
    # modello chiedeva `view("scena", ...)`, leggeva `esiste: false` e
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
    `automazione`): sono gli stessi nomi di `search` e di `view`, cosi' un
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
