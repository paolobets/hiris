"""Il filtro di riservatezza della porta che legge la casa (spec
`2026-09-29-una-porta-sola-per-la-casa.md` §3).

**Un punto solo**, e sulla PORTA, non sullo specchio: lo specchio serve anche
a chi agisce e a chi verifica, che hanno bisogno dello stato vero. Cio' che
qui si toglie e' cio' che il modello non deve ricevere, in nessuna
profondita' -- decisione del proprietario, 29/09/2026:

- le credenziali mai (la cesta `credentials` di `_to_minimal`, dove lo
  specchio mette gia' anche `ip`, `mac`, `host_name`);
- la posizione della casa si' (`zone.home`): serve a sole, meteo, orari;
- di persone e dispositivi che si spostano, solo in casa / fuori casa: niente
  coordinate, niente zone, e il nome di una zona («Lavoro») diventa
  `not_home`, perche' direbbe gia' dove sono.
"""
from __future__ import annotations

import re

from ..proxy.entity_cache import CREDENTIALS
from .ha_vocabulary import domain_of
from .queries import WITHHELD_BASKET
from .reference import NO_SLUG, slugify
from .type_vocabulary import domains_by_genre, unknown_states

#: I due soli domini il cui genere e' "presenza", ricavati dalla dichiarazione
#: nel vocabolario dei tipi.
MOVING_DOMAINS = domains_by_genre("presenza")
#: Le chiavi che dicono DOVE si trova una persona o un dispositivo. Le usano
#: anche gli argomenti salvati nel registro dei turni (`usage/store.py`, spec
#: §7: «dallo stesso filtro di §3»): `gps` e `location_name` sono i campi di
#: `device_tracker.see`, e `location_name` porta il nome di una zona.
POSITION_ATTRIBUTES = frozenset({"latitude", "longitude", "gps_accuracy",
                                 "in_zones", "gps", "location_name"})
HOME_ZONE = "zone.home"
#: Gli stati che non dicono dove si trova qualcuno: restano come sono. In
#: casa, fuori casa, e i due «non lo so» del vocabolario (B-07; Tappa 3, Task
#: 8, 04/10/2026: fino a quel giorno li riscriveva qui a mano).
_NEUTRAL_STATES = frozenset({"home", "not_home"}) | unknown_states()


def redact_state(entity_id: str, state: str | None) -> str | None:
    if state is None or domain_of(entity_id) not in MOVING_DOMAINS:
        return state
    return state if state in _NEUTRAL_STATES else "not_home"


#: Le chiavi che portano credenziali o i loro NOMI, nelle due forme in cui
#: gli attributi arrivano alla porta: le ceste dello specchio (`_to_minimal`)
#: e il dettaglio di `queries.view` (`valori`, `campo_di_manovra`,
#: `non_interpretati`, `trattenuti`).
_NEVER_BASKETS = frozenset({CREDENTIALS, WITHHELD_BASKET})


def _hides_position(entity_id: str) -> bool:
    """Chi perde le coordinate: persone e dispositivi che si spostano, e zone
    che non siano `zone.home` (le altre direbbero dove vanno le persone). Un
    punto solo per `redact_attributes` e `redact_nested` (30/09/2026)."""
    domain = domain_of(entity_id)
    return domain in MOVING_DOMAINS or (domain == "zone" and entity_id != HOME_ZONE)


def redact_attributes(entity_id: str, attributes: dict | None) -> dict | None:
    if not attributes:
        return attributes
    redact_position = _hides_position(entity_id)
    kept: dict = {}
    for basket, values in attributes.items():
        if basket in _NEVER_BASKETS:
            continue
        if redact_position and isinstance(values, dict):
            values = {k: v for k, v in values.items()
                      if k not in POSITION_ATTRIBUTES}
            if not values:
                continue
        kept[basket] = values
    return kept


#: Le chiavi che portano gli attributi di UNA voce: il filtro li passa da
#: `redact_attributes`, non li attraversa come elenchi di righe.
_ATTRIBUTE_KEYS = ("attributi", "attributes")
#: Lo stato in parole accanto al grezzo (`queries._enrich_entity`). Quando il
#: grezzo si riduce a `not_home`, la resa del grezzo non vale piu' e il suo
#: motivo potrebbe ripeterlo: escono con lui.
_RENDERED_STATE_KEYS = ("stato_leggibile", "stato_non_reso")


def redact_row(row: dict) -> dict:
    """Il filtro su UNA voce, e -- ricorsivo -- su ogni riga che la voce porta
    dentro di se'.

    **In tutte le profondita'** (spec §3), e il dettaglio completo ne ha piu'
    d'una: un dispositivo, un'area o un'integrazione portano le loro entita'
    in `entita` e `entita_nascoste`, righe con il loro `id` e il loro `stato`
    grezzo. Fino al 30/09/2026 il filtro guardava solo il primo livello, e
    `search(nome="iphone")` -- un telefono con l'app di Home Assistant ha
    SEMPRE un `device_tracker` -- consegnava «Lavoro» dentro il dispositivo
    (review finale della fetta, C1). Un punto solo resta un punto solo: la
    discesa e' qui, non in ogni ramo che costruisce un elenco."""
    entity_id = str(row.get("id") or "")
    out = dict(row)
    if "stato" in out:
        seen = redact_state(entity_id, out["stato"])
        if seen != out["stato"]:
            for key in _RENDERED_STATE_KEYS:
                out.pop(key, None)
        out["stato"] = seen
    for key, value in out.items():
        if key in _ATTRIBUTE_KEYS:
            out[key] = redact_attributes(entity_id, value)
        elif isinstance(value, list):
            out[key] = [redact_row(item) if isinstance(item, dict) else item
                        for item in value]
    return out


def redact_nested(value):
    """Ogni stato di Home Assistant annidato in una struttura, ridotto.

    La traccia di un'esecuzione porta `trigger.to_state`/`from_state` interi,
    e li ripete nelle `changed_variables` dei passi: la zona di chi si muove
    come stato, e le coordinate fra gli attributi (spec «la storia» §5,
    Review Focus 1, 30/09/2026). `redact_row` guarda le righe della porta,
    con `id` e `stato`; qui si guarda la forma di Home Assistant (`entity_id`,
    `state`, `attributes`) a ogni profondita', e si restituisce una copia.

    Le stesse fonti di `redact_attributes`, nessuna seconda lista:
    `MOVING_DOMAINS` per lo stato, `_hides_position` e `POSITION_ATTRIBUTES`
    per le coordinate -- anche quelle della zona di un innesco `zone`."""
    if isinstance(value, list | tuple):
        return [redact_nested(item) for item in value]
    if not isinstance(value, dict):
        return value
    out = {key: redact_nested(item) for key, item in value.items()}
    entity_id = out.get("entity_id")
    if not isinstance(entity_id, str):
        return out
    if "state" in out and isinstance(out["state"], str | None):
        out["state"] = redact_state(entity_id, out["state"])
    if _hides_position(entity_id) and isinstance(out.get("attributes"), dict):
        out["attributes"] = {key: item for key, item in out["attributes"].items()
                             if key not in POSITION_ATTRIBUTES}
    return out


#: Perche' il corpo di un'automazione non va a chi non amministra. Verificato
#: il 27/09/2026 su Core 2026.9.3 (fix round 1 del Task 2, L-2):
#: `automation/config` (`components/automation/__init__.py`) e'
#: `@websocket_api.require_admin`; `script/config` no, e il corpo degli
#: script resta visibile a tutti.
AUTOMATION_BODY_ADMIN_ONLY = ("Home Assistant mostra il corpo delle "
                              "automazioni solo agli amministratori: si sa "
                              "che c'e' e come si chiama, non cosa fa")


def cover_automation_body(entry: dict, *, kind: str) -> dict:
    """La voce com'e' per chi non amministra: un'automazione col corpo lo
    perde e dice perche'. Tutto il resto -- uno script, un'automazione di cui
    il corpo non si conosce -- resta com'e': «coperto» e «non letto» sono due
    fatti diversi.

    **Una regola, due porte**: la chiamano lo strumento della chat
    (`tools.py`, il dettaglio di `view`) e la rotta `GET /api/home-space`,
    che fino alla 3.73.0 consegnava i corpi a un servizio firmato «lettore».
    """
    if kind != "automazione" or entry.get("corpo") is None:
        return entry
    return {**entry, "corpo": None, "corpo_non_disponibile": AUTOMATION_BODY_ADMIN_ONLY}


# ── I nomi delle persone verso un attore (decisione 12, estesa il 06/10/2026)

#: Il segno del SEGNAPOSTO che prende il posto di un identificatore che porta
#: il nome di una persona (decisione 12 della spec «Una fonte sola di
#: verita'», Tappa 6, Task 6, 05/10/2026). Il `#` non puo' collidere con
#: un'entita' vera: Home Assistant ammette nell'object_id solo cifre,
#: minuscole e `_` (`homeassistant/core.py`, `_OBJECT_ID`, Core 2026.9.3,
#: letto il 05/10/2026). Viveva in `mind/observer.py` fino al 06/10/2026.
PRESENCE_MARK = "#"


def handles(ids) -> dict[str, str]:
    """`entity_id` -> segnaposto `<dominio>.#N`, numerato dominio per dominio
    nell'ordine degli id: cio' che lo rende ricostruibile, a partire dallo
    stesso insieme, senza archiviare una tabella di corrispondenze."""
    out: dict[str, str] = {}
    counters: dict[str, int] = {}
    for entity_id in sorted(ids):
        domain = domain_of(entity_id)
        counters[domain] = counters.get(domain, 0) + 1
        out[entity_id] = f"{domain}.{PRESENCE_MARK}{counters[domain]}"
    return out


def person_bound(house) -> tuple[list[str], list[str]]:
    """`(entita', dispositivi)` che portano il nome di una persona: le
    presenze (`MOVING_DOMAINS`: `person` e i `device_tracker`) e, per ogni
    dispositivo che porta una presenza, TUTTE le sue entita' -- la batteria
    del telefono, accanto al suo tracker -- e quelle il cui id porta il nome
    di una persona (`named_after_person`, G26-1).

    Il legame si chiede a Home Assistant, non si indovina dai nomi: e' il
    `device_id` del registro delle entita' (`config/entity_registry/list`),
    che l'anagrafe tiene come `dispositivo_id` (`House.device_entities`).
    Decisione del proprietario del 06/10/2026 («Segnaposto», dopo la misura
    del Task 3.0, Passo 4: `search` portava un nome di persona in 4 risposte
    su 35, quasi sempre dentro il nome di un'entita')."""
    moving = {e for e in house.entity_ids() if domain_of(e) in MOVING_DOMAINS}
    devices = [d for d in house.device_ids()
               if any(e["id"] in moving for e in house.device_entities(d))]
    sisters = {e["id"] for d in devices for e in house.device_entities(d)}
    return sorted(moving | sisters | named_after_person(house)), devices


def named_after_person(house) -> set[str]:
    """Le entita' il cui `entity_id` porta il nome di una persona: un
    `automation.paolo_arriva_a_casa`, un `input_boolean.giulia_in_ferie`, un
    sensore senza dispositivo (G26-1, giro 26 della revisione, 06/10/2026).

    Nessun legame del registro le unisce alla persona -- non hanno il suo
    dispositivo -- ma l'id porta il nome, e `search` e `history` restituiscono
    gli id. Il nome e' quello delle persone dichiarate in Home Assistant
    (`person.*`), col loro object_id, nella forma che Home Assistant stesso
    ne ricava per un id
    (`reference.slugify`, la replica di `homeassistant.util.slugify`): uno o
    piu' pezzi interi dell'object_id, fra un `_` e l'altro, mai un pezzo di
    parola («paolone» non e' «paolo»). Un nome che non da' uno slug (un
    alfabeto che la replica non traslittera: `"unknown"`) non copre niente,
    invece di coprire ogni id con «unknown» dentro."""
    slugs = set()
    for person in house.entity_ids():
        if domain_of(person) != "person":
            continue
        # Il nome dichiarato e l'object_id della persona (G28-1, giro 28):
        # l'object_id e' cio' che Home Assistant ha ricavato dal nome quando
        # la persona e' nata, e vale anche quando il nome amichevole manca
        # (`House.name` ripiega sull'id, che non e' un nome).
        name = house.name("entita", person)
        for text in {name if name != person else "", person.partition(".")[2]}:
            slug = slugify(text)
            if slug and slug != NO_SLUG:
                slugs.add(slug)
    if not slugs:
        return set()
    pieces = re.compile(rf"(?:^|_)(?:{'|'.join(map(re.escape, slugs))})(?:_|$)")
    return {e for e in house.entity_ids()
            if pieces.search(e.partition(".")[2])}


class PresenceMask:
    """Il filtro dei nomi delle persone **per le risposte degli strumenti di un
    attore** (decisione 12 estesa: «Segnaposto», 06/10/2026). La chat resta
    com'e': qui passa solo il guardiano di un mestiere di sfondo
    (`mind/analyst_turn.AnalystDispatcher`).

    `mask` sostituisce, a ogni profondita' e anche nelle chiavi, l'id di
    un'entita' legata a una persona (`person_bound`) col suo segnaposto, e
    con lo stesso segnaposto il suo nome; il nome di un suo dispositivo
    diventa `dispositivo.#N`. `unmask` riporta i segnaposto agli id veri
    negli argomenti che il modello manda: il turno legge la cosa giusta senza
    averne mai visto il nome.

    Un nome si sostituisce solo intero (non dentro un'altra parola), e prima
    i piu' lunghi: «iPhone di Paolo Batteria» diventa un segnaposto solo,
    non «dispositivo.#1 Batteria». **Senza badare alle maiuscole** (G26-1,
    giro 26 della revisione): il nome e' quello che Home Assistant dichiara,
    ma una risposta lo puo' portare scritto «paolo» o «PAOLO» -- e resta il
    suo nome. Gli id e i segnaposto, che sono gia' in minuscolo per Home
    Assistant (`_OBJECT_ID`), si confrontano allo stesso modo senza danno."""

    def __init__(self, house) -> None:
        ids, devices = person_bound(house)
        self.handles = handles(ids)
        words: dict[str, str] = {}
        for entity_id, handle in self.handles.items():
            words[entity_id] = handle
            name = house.name("entita", entity_id)
            if name and name != entity_id:
                words.setdefault(name, handle)
        for number, device_id in enumerate(devices, start=1):
            name = house.name("dispositivo", device_id)
            if name and name != device_id:
                words.setdefault(name, f"dispositivo.{PRESENCE_MARK}{number}")
        self._mask = _alternation(words)
        back = {handle: entity_id for entity_id, handle in self.handles.items()}
        self._unmask = _alternation(back, after=r"(?!\d)")

    def mask(self, value):
        return _replace(value, self._mask)

    def unmask(self, value):
        return _replace(value, self._unmask)


def _alternation(words: dict[str, str], *, after: str = r"(?!\w)"):
    """`(espressione, valori)`: un'espressione sola per tutte le parole, le
    piu' lunghe prima, ognuna solo intera e in qualunque maiuscolo; `None` se
    non c'e' niente da sostituire.

    **Ogni forma e' un gruppo con nome, e il valore lo dice il gruppo**
    (`m.lastgroup`), mai una ricerca del testo trovato in un dizionario
    (G27-1 e G27-2, giro 27 della revisione, 06/10/2026). Per ogni parola le
    forme sono due, quella dichiarata e quella `casefold`, perche'
    `re.IGNORECASE` usa le corrispondenze semplici e `casefold` quelle
    piene: «Strauß» diventa «strauss» (che non trova «Strauß»), e «IŞIL»
    cercato come «işil» dava `KeyError`. Con le due forme fra le alternative,
    «Strauß», «STRAUSS» e «strauss» si coprono tutti, e niente solleva."""
    if not words:
        return None
    forms = sorted({(form, value) for word, value in words.items()
                    for form in (word, word.casefold())},
                   key=lambda pair: (-len(pair[0]), pair[0]))
    alternatives = "|".join(f"(?P<w{i}>{re.escape(form)})"
                            for i, (form, _value) in enumerate(forms))
    pattern = re.compile(rf"(?<![\w.#])(?:{alternatives}){after}", re.IGNORECASE)
    return pattern, [value for _form, value in forms]


def _replace(value, matcher):
    if matcher is None:
        return value
    if isinstance(value, str):
        pattern, values = matcher
        return pattern.sub(lambda m: values[int(m.lastgroup[1:])], value)
    if isinstance(value, dict):
        return {_replace(k, matcher): _replace(v, matcher) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_replace(item, matcher) for item in value]
    return value
