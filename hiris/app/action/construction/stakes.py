"""Il **livello** di una proposta: quanto conta, in quattro valori chiusi
(D3 del refactor degli attori, 03/10/2026; D13 del piano degli strati 3-4,
approvata dal proprietario il 06/10/2026).

Nel cervello il livello decide **come si chiede**, non se si chiede: una
proposta `alto` avvisa chi amministra la casa, le altre tre vanno fra le
Proposte allo stesso modo. Quando ci saranno gli agenti decidera' anche come
una cosa entra nel loro perimetro. **Non da' autonomia a nessuno**: «il
cervello non tocca la casa senza un si'» resta vero a ogni livello.

**Chi lo assegna.** `alto` lo impone il codice, quando la proposta agisce su
un dominio di `HIGH_STAKES_DOMAINS`; gli altri tre li sceglie il modello, che
non puo' abbassare un `alto` ne' scriverlo da se'. Un modello che sbaglia
potrebbe mettere `lieve` su una serratura: e' la ragione per cui quella parte
non e' sua.

Una casa sola per le due code (fondamenta 2 e 3): le costruzioni dell'officina
(`revisions.py`) e le proposte da fare a mano (`mind/store.py`) portano lo
stesso campo, con lo stesso vocabolario, e lo calcolano con la stessa
funzione. L'inglese e' `stakes` e non `level`: «livello» e' gia' quello di un
messaggio del registro di Home Assistant (`home_space/house_history.py`), e il
livello della casa e' `floor` (`docs/GLOSSARIO.md`, riga «livello
(action)»).
"""
from __future__ import annotations

import re

from ...home_space.ha_vocabulary import domain_of

#: I quattro livelli, dal piu' leggero al piu' pesante. **Chiusi**: una parola
#: nuova arriverebbe da un modello e diventerebbe un livello che nessuna
#: regola sa trattare.
STAKES = ("banale", "lieve", "medio", "alto")

#: Il livello che solo il codice assegna.
HIGH = "alto"

#: Cio' che il modello puo' scegliere: tutti, tranne quello che impone il
#: codice. Derivato, non ricopiato: un livello nuovo entra qui da solo.
CHOSEN_BY_MODEL = tuple(value for value in STAKES if value != HIGH)

#: **I domini su cui una proposta e' sempre `alto`.** Lista d'AMMISSIONE, non
#: una copia: enuncia la decisione del proprietario del 03/10/2026 («serrature
#: e allarme chiedono sempre», D-decisioni del refactor degli attori). Chiude
#: per difetto: un dominio nuovo entra solo scritto qui, con la sua ragione.
#:
#: **Home Assistant non ha una lista sua da chiedere**, ed e' stato verificato
#: prima di scrivere questa (sorgente di `home-assistant/core`, ramo `dev`,
#: letto il 06/10/2026): nessun elenco di domini «sensibili» nel nucleo, e
#: nessuno in `helpers/llm.py`. Le tracce sono sparse per integrazione:
#: Assist non espone di suo `lock` ne' `alarm_control_panel`
#: (`components/homeassistant/exposed_entities.py`, `DEFAULT_EXPOSED_DOMAINS`
#: li lascia fuori -- insieme a molti altri domini, quindi non e' una lista di
#: domini sensibili), e Google Assistant chiede il PIN per aprire una
#: serratura, per armare o disarmare l'allarme e per aprire una tapparella di
#: classe porta, garage o cancello (`components/google_assistant/trait.py`,
#: `_verify_pin_challenge`, `OpenCloseTrait.COVER_2FA`). Le tapparelle di
#: quelle tre classi **non** ci sono: il proprietario non l'ha deciso, e
#: chiedono la classe del dispositivo, che un dominio da solo non porta.
HIGH_STAKES_DOMAINS = ("lock", "alarm_control_panel")

#: Il rifiuto di un oggetto `alto` che agirebbe da solo («Rendila
#: automatica», attori Task 4.5): decisione del proprietario del 06/10/2026,
#: che applica quella del 03/10. Lo legge il modello, che deve capire che non
#: e' un errore da correggere, e lo legge la pagina.
HIGH_UNATTENDED = ("Non si può rendere automatica: agisce su "
                   + ", ".join(HIGH_STAKES_DOMAINS)
                   + ", che chiedono sempre a chi amministra la casa. Non "
                     "riproporla in un'altra forma.")

#: I delimitatori con cui Home Assistant riconosce un modello Jinja in una
#: stringa: `is_template_string` in `homeassistant/helpers/template`, ramo
#: `dev`, letto il 06/10/2026.
_TEMPLATE_MARKS = ("{{", "{%", "{#")


def is_template(value) -> bool:
    """Se `value` e' un modello Jinja, che Home Assistant risolve solo quando
    il passo gira: chi lo legge qui non sa cosa diventera'."""
    return isinstance(value, str) and any(mark in value for mark in _TEMPLATE_MARKS)


#: Il rifiuto di un oggetto che agira' DA SOLO chiamando un servizio scritto
#: come modello (giro di revisione 69, G69-1): `action: "{{ 'lock.unlock' }}"`
#: usciva senza livello. Il nome lo decide Home Assistant quando il passo
#: gira, e da qui non si vede.
TEMPLATE_UNATTENDED = ("Non si può rendere automatica: chiama un servizio "
                       "scritto come modello, e quale sia lo decide Home "
                       "Assistant solo quando gira: potrebbe toccare serrature "
                       "o allarme senza chiedere. Scrivi il servizio per nome.")


def opaque_unattended(opaque) -> str:
    """Il rifiuto di un oggetto che agira' DA SOLO accendendo uno dei domini
    `opaque` (giro di revisione 67, G67-1; consigliata A, 06/10/2026).

    Un'automazione che accende uno script, una scena o un'altra automazione
    agisce su cio' che QUELLI fanno, e `domains_acted_on` non lo vede (lo dice
    la sua docstring): misurato sul ramo, `script.turn_on` su uno script che
    apre la porta usciva `lieve`. I domini non si scrivono qui: sono quelli
    che questo prodotto costruisce (`HAClient.CONFIGURABLE_DOMAINS`), i soli
    il cui corpo e' fatto di altre azioni, e la porta li chiede al suo client."""
    return ("Non si può rendere automatica: accende " + ", ".join(opaque)
            + ", e quello che fanno non si vede da qui: potrebbero toccare "
              "serrature o allarme senza chiedere. Componi l'automazione con "
              "le azioni dirette, o dillo nel perche'.")


def unattended_refusal(level: str | None, acted_on, opaque,
                       services=()) -> str | None:
    """Perche' un oggetto che agira' DA SOLO non si accetta, o `None`
    («Rendila automatica», attori Task 4.5): `alto`, un servizio scritto come
    modello (`services`), o un'azione su un oggetto il cui contenuto non si
    vede (`opaque`). Finche' il codice non legge quei corpi, un oggetto che
    agisce da solo non li chiama."""
    # Il modello prima di `alto`: un servizio scritto come modello e' anche
    # `alto` (`impose`), e il rifiuto deve dire la ragione vera.
    if any(is_template(service) for service in services):
        return TEMPLATE_UNATTENDED
    if level == HIGH:
        return HIGH_UNATTENDED
    if set(acted_on or ()) & set(opaque):
        return opaque_unattended(opaque)
    return None

#: Un `entity_id` come Home Assistant lo scrive: dominio e oggetto, minuscoli,
#: separati da un punto. Un modello che scrive un modello Jinja dentro
#: `entity_id` non porta un dominio, e non si indovina.
_ENTITY_ID = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")

#: Fin dove si scende in un corpo annidato: lo stesso tetto dell'officina
#: (`workshop._MAX_DEPTH`), per la stessa ragione.
_MAX_DEPTH = 50


def stakes_refusal(chosen) -> str | None:
    """Il motivo per cui il livello scelto dal modello non si accetta, o
    `None`. Assente va bene: il codice impone comunque `alto` dove serve."""
    if chosen is None or chosen in CHOSEN_BY_MODEL:
        return None
    if chosen == HIGH:
        return (f"«livello» accetta {', '.join(CHOSEN_BY_MODEL)}: «{HIGH}» lo "
                "mette il codice, da solo, quando la proposta agisce su "
                + ", ".join(HIGH_STAKES_DOMAINS) + ".")
    return f"«livello» accetta solo {', '.join(CHOSEN_BY_MODEL)}, non {chosen!r}."


def acting_part(domain: str, body: dict | None):
    """La parte di un corpo di Home Assistant che AGISCE: le azioni di
    un'automazione, i passi di uno script, gli stati di una scena. Inneschi e
    condizioni guardano la casa, non la toccano.

    Le chiavi sono quelle che Home Assistant salva: `actions` (e `action`,
    la stessa lista prima della forma al plurale, nei corpi letti da una casa
    che li ha scritti prima), `sequence` per uno script, `entities` per una
    scena (`composer.compose_*`, `composer.parts_to_validate`).
    """
    if not isinstance(body, dict):
        return []
    if domain == "automation":
        actions = body.get("actions")
        if actions is None and isinstance(body.get("action"), list):
            actions = body["action"]
        return actions or []
    if domain == "script":
        return body.get("sequence") or []
    if domain == "scene":
        entities = body.get("entities")
        return list(entities) if isinstance(entities, dict) else []
    return []


def domains_acted_on(domain: str, *bodies, services=()) -> set[str]:
    """I domini della casa su cui questi corpi agiscono.

    Tre strade, perche' Home Assistant ne ha tre: il servizio chiamato
    (`lock.unlock`, che il chiamante passa in `services`: l'estrattore e'
    `workshop.services_named`, uno solo), l'entita' bersaglio (`entity_id`,
    dentro `target`, dentro `data` o nudo, e le chiavi degli stati di una
    scena) e l'azione di un dispositivo (`device_id` con il suo `domain`).

    Quello che non vede, ed e' detto: un'azione che accende una scena o
    lancia uno script che a loro volta toccano una serratura. Il bersaglio
    e' un altro oggetto, e il suo contenuto non sta in questo corpo.
    """
    found: set[str] = set()
    # Un servizio ha la stessa grammatica di un `entity_id`, dominio e nome:
    # lo legge la stessa funzione.
    # Un servizio scritto come modello non ha ancora un dominio: lo rifiuta
    # `unattended_refusal`, e qui non diventa un dominio inventato.
    for service in services:
        if isinstance(service, str) and "." in service and not is_template(service):
            found.add(domain_of(service))

    def entity_domain(value) -> None:
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and _ENTITY_ID.match(item):
                found.add(domain_of(item))

    def walk(node, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        if isinstance(node, dict):
            if "device_id" in node and isinstance(node.get("domain"), str):
                found.add(node["domain"])
            for key, value in node.items():
                if key == "entity_id":
                    entity_domain(value)
                    continue
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, str):
                    entity_domain(item)
                else:
                    walk(item, depth + 1)

    for body in bodies:
        walk(acting_part(domain, body), 0)
    return found


def impose(chosen: str | None, acted_on, services=()) -> str | None:
    """Il livello della proposta: `alto` se agisce su un dominio della lista,
    o se chiama un servizio scritto come modello (`services`), altrimenti
    quello scelto dal modello. `None` quando nessuno l'ha detto e il codice
    non ha niente da imporre: e' un fatto («non detto»), non un livello
    inventato.

    Il servizio scritto come modello e' `alto` per scelta del proprietario
    (07/10/2026, scheda «Sì, alto», dopo il giro di revisione 69): quale
    servizio sia lo decide Home Assistant quando il passo gira, e potrebbe
    essere `lock.unlock`. Chi conferma deve saperlo prima, non dopo."""
    if set(acted_on or ()) & set(HIGH_STAKES_DOMAINS):
        return HIGH
    if any(is_template(service) for service in services):
        return HIGH
    return chosen if chosen in CHOSEN_BY_MODEL else None
