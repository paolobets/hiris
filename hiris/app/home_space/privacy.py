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
from .ha_vocabulary import HA_LINK_TYPE, domain_of
from .reference import NO_SLUG, slugify
from .render import WITHHELD_BASKET
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
#: Lo stato in parole accanto al grezzo (`render.render_entity`). Quando il
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


# ── Cosa Home Assistant riserva agli amministratori ───────────────────────
#
# **Una casa sola** (D-43, F-22; Tappa 7, Task 5, 07/10/2026). Fino a quel
# giorno lo stesso fatto -- «questo Home Assistant lo mostra o lo fa fare solo
# a chi amministra» -- stava in quattro posti: i servizi del nucleo negli
# strumenti (`tools._HA_CORE_USER_SERVICES`), le letture della storia
# (`house_history.ADMIN_KINDS`), il corpo nell'anteprima dell'officina
# (`workshop._BODY_ADMIN_ONLY`, automazioni e scene) e il corpo nella porta che
# legge la casa (qui, solo automazioni). Due regole per «il corpo si mostra solo
# a chi amministra»: oggi coincidevano sulla casa perche' la porta non porta
# corpi di scene, non perche' qualcuno le tenesse uguali.
#
# **Riletto nel sorgente di Home Assistant il 07/10/2026, tag `2026.9.4`.**
# Non si ipotizza: ogni insieme qui sotto cita dove HA lo dichiara.

#: I domini il cui CORPO Home Assistant mostra solo agli amministratori.
#: Le due porte da cui si legge un corpo:
#: - REST, `/api/config/{automation,script,scene}/config/<chiave>`:
#:   `BaseEditConfigView.get` e' `@require_admin` per tutti e tre
#:   (`components/config/view.py`, righe 85-86);
#: - WebSocket: `automation/config` e' `@websocket_api.require_admin`
#:   (`components/automation/__init__.py`, righe 1248-1249); `script/config`
#:   no (`components/script/__init__.py`, riga 784); le scene non hanno un
#:   comando WebSocket della configurazione (`components/scene/__init__.py`,
#:   `components/homeassistant/scene.py`): il loro corpo esce solo dalla
#:   porta REST, che chiede l'amministratore.
#: Quindi: il corpo di automazioni e scene si', quello degli script no. I nomi
#: sono quelli di Home Assistant (il confine): chi ha in mano il tipo nostro
#: («automazione», «scena») lo traduce con `HA_LINK_TYPE`, in `body_is_admin_only`.
BODY_ADMIN_ONLY_DOMAINS = frozenset({"automation", "scene"})

#: Perche' una voce della casa arriva senza corpo a chi non amministra.
BODY_ADMIN_ONLY = ("Home Assistant mostra il corpo delle automazioni e delle "
                   "scene solo agli amministratori: si sa che c'e' e come si "
                   "chiama, non cosa fa")
#: La stessa ragione, nell'anteprima di una proposta dell'officina, al posto
#: della riga «Prima:» (com'e' adesso la cosa che si modifica).
BEFORE_ADMIN_ONLY = "com'è adesso lo vedono solo gli amministratori."


def body_is_admin_only(kind: str) -> bool:
    """Il corpo di questo tipo Home Assistant lo mostra solo a chi amministra?

    `kind` e' il dominio di Home Assistant (`automation`, `scene`) oppure il
    tipo nostro (`automazione`, `scena`): la traduzione e' quella del
    confine, `ha_vocabulary.HA_LINK_TYPE`, e non una seconda tabella."""
    return HA_LINK_TYPE.get(kind, kind) in BODY_ADMIN_ONLY_DOMAINS


def cover_reserved_body(entry: dict, *, kind: str) -> dict:
    """La voce com'e' per chi non amministra: se Home Assistant riserva il
    corpo di questo tipo, la voce lo perde e dice perche'. Tutto il resto --
    uno script, una voce di cui il corpo non si conosce -- resta com'e':
    «coperto» e «non letto» sono due fatti diversi.

    **Una regola, tre porte**: la chiamano lo strumento della chat
    (`tools.py`, il dettaglio di `view`), la rotta `GET /api/home-space`, che
    fino alla 3.73.0 consegnava i corpi a un servizio firmato «lettore», e --
    con la sua frase, `BEFORE_ADMIN_ONLY` -- l'anteprima dell'officina.
    """
    if not body_is_admin_only(kind) or entry.get("corpo") is None:
        return entry
    return {**entry, "corpo": None, "corpo_non_disponibile": BODY_ADMIN_ONLY}


#: I servizi del dominio `homeassistant` che Home Assistant concede a chi non
#: amministra. Riletto il 07/10/2026 al tag `2026.9.4`,
#: `components/homeassistant/__init__.py`: `turn_on`, `turn_off`, `toggle`
#: (righe 185-193), `update_entity` (righe 282-287) e `save_persistent_states`
#: (righe 179-181) si registrano con `hass.services.async_register`; `stop`,
#: `restart`, `check_config`, `reload_core_config`, `set_location`,
#: `reload_custom_templates`, `reload_config_entry` e `reload_all` con
#: `async_register_admin_service`. `save_persistent_states` resta fuori per
#: decisione (fix round 1, M-1, 27/09/2026): e' manutenzione del nucleo, non
#: un comando di casa.
HA_CORE_USER_SERVICES = frozenset({"turn_on", "turn_off", "toggle", "update_entity"})

#: I generi della storia (`house_history.KINDS`) che leggono cio' che Home
#: Assistant mostra ai soli amministratori: le esecuzioni (`trace/list`,
#: `trace/get`, `components/trace/websocket_api.py`) e gli errori
#: (`system_log/list`, `components/system_log/__init__.py`, righe 342-343),
#: tutti `@websocket_api.require_admin`. Riletto il 07/10/2026 al tag
#: `2026.9.4`. Che siano generi veri della storia lo prova
#: `tests/test_riservato_agli_amministratori.py`, chiedendolo a `house_history`.
ADMIN_ONLY_HISTORY_KINDS = frozenset({"esecuzioni", "errori"})


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
    invece di coprire ogni id con «unknown» dentro.

    **Limiti dichiarati** (decisione del proprietario del 06/10/2026, «Solo
    nome intero», dopo il giro 28 della revisione):
    - **i pezzi di un nome in piu' parole non si coprono da soli.** «Paolo
      Bets» nata `person.paolo_bets` non copre `automation.paolo_arriva`, e
      «Paolo» da solo in un testo passa. Coprire ogni pezzo prenderebbe anche
      le particelle («de», «di», «la»), e per evitarlo servirebbe un elenco
      o una soglia nostri. Quante persone della casa hanno un nome in piu'
      parole, e quanti id ne portano un pezzo solo, l'ha misurato lo sprint
      sugli ingressi del 03/10/2026: nessuna persona col nome in piu'
      parole, 76 id coperti, 0 id con un pezzo solo;
    - **un nome che e' anche una parola** («Sole») copre gli id che la
      contengono (`sensor.sole_elevazione`): informazione tolta, non una
      fuga, e `unmask` riporta l'id;
    - **lo slug e' quello della replica** (`reference.slugify`): «Strauß» da'
      «strau», dove `python-slugify` di Home Assistant da' «strauss»."""
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
