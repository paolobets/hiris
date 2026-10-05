"""L'osservatore che **si dà lo scope da sé**.

Guarda la casa che gli compete -- con l'obiettivo davanti -- e decide cosa
pesa: soggetto per soggetto, col perché scritto (spec §5.1). Nessuna gamba,
nessun pavimento, nessuna lista nel codice.

**Misurato sulla casa vera il 10/09/2026.** La casa intera, una riga per
entita': 833 entita', 106.433 caratteri, ≈26.600 token. Tolte le entita' di
servizio e le nascoste: **381 entita', 46.098 caratteri, ≈11.500 token** -- le
423 di servizio e le 29 nascoste valevano **15.000 token a ogni giro**, piu'
della meta' del prompt.

**Le entita' di servizio e le nascoste non entrano di default** (decisione del
proprietario, 10/09/2026); se qualcuno le chiede esplicitamente, passano. E'
la stessa legge che il nucleo applica gia' al digesto, e si CHIEDE alla casa
(`House.visible_entities`, che compone `topology.visibility_classes`) invece
di riscriverla: due copie della stessa regola divergono al primo cambiamento
da una parte sola, ed e' gia' successo in questo prodotto (rilievo R1
dell'08/09/2026).

**Quando gira** lo decide `cadence.reason_to_reconsider`: al primo avvio,
quando cambia l'obiettivo, quando compare qualcosa di nuovo, e alla cadenza di
riconsiderazione. Qui dentro non c'e' nessuna delle quattro domande -- questo
modulo sa fare un giro, non sa quando farlo.
"""
from __future__ import annotations

import logging

from ..home_space.ha_vocabulary import domain_of, is_entity_id
from ..home_space.house import House
from ..home_space.privacy import MOVING_DOMAINS
from ..home_space.topology import is_pseudo_area
from ..steering import OBSERVER_SPECIES, misura_turno, read_json
from .scope import OBSERVER

logger = logging.getLogger(__name__)

#: Quanto puo' essere lunga la risposta. Su 381 entita' il modello scrive una
#: riga di giudizio ciascuna -- identificatore, dentro/fuori, motivo -- e a
#: ~80 caratteri di media fa ≈30 KB, cioe' ≈8.000 token. Il tetto sta sopra con
#: margine: una risposta troncata a meta' non e' un giudizio parziale, e' un
#: JSON rotto che si butta intero.
MAX_ANSWER_TOKENS = 16000

#: Come si chiama, nella coda del ragionamento, un turno dell'osservatore.
#: Le altre due specie sono `chat` (`api/handlers_chat.py`) e `promessa`
#: (`keeper/exchange.py`), e come loro il nome vive **dove il turno nasce**:
#: chi lo serve -- `agent/runner.reason` -- dichiara per conto suo quali
#: specie sa ragionare, che e' un'affermazione sua e non una copia di questa.
SCOPE_TURN_KIND = "scope"

SYSTEM = """Sei l'osservatore di HIRIS, un sistema che guarda una casa domotica.

Il tuo mestiere e' UNO: decidere, entita' per entita', se quello che fa merita
di essere registrato rispetto all'obiettivo che ti viene dato -- e scrivere
PERCHE'.

Quello che decidi ha due conseguenze vere, e nessuna delle due e' teorica:
- cio' che lasci DENTRO viene registrato a ogni cambio di stato, e costa spazio
  e attenzione;
- cio' che lasci FUORI **non viene registrato affatto**, e fra un mese non
  esistera': nessuno potra' rispondere a una domanda su quel periodo. Potrai
  ricrederti, ma solo finche' Home Assistant ricorda -- pochi giorni.

Quindi non essere generoso e non essere avaro: chiediti, per ognuna, se la sua
storia servirebbe a capire come la casa risponde all'obiettivo.

Il motivo che scrivi lo legge chi amministra la casa in una pagina. Scrivilo in
italiano, in una riga, concreto: «scalda la camera, e il riscaldamento e' la
voce piu' pesante» va bene; «utile» no, «non rilevante» nemmeno."""


def watched_ids(house: House, only: set[str] | None = None) -> list[str]:
    """Le entita' che competono all'osservatore in questo turno: quelle che
    la casa guarda (`House.visible_entities`, la regola del fuori), ristrette
    al lotto.

    `only` restringe al **lotto** e non puo' allargare: si INTERSECA con la
    regola del fuori, non la sostituisce. Un'entita' di servizio chiesta per
    nome resta fuori lo stesso, perche' cosa competa all'osservatore lo decide
    una legge sola e non chi compone il lotto."""
    return [eid for eid in house.visible_entities() if only is None or eid in only]


#: **Persone e dispositivi che le seguono arrivano al modello senza nome**
#: (decisione 12 della spec «Una fonte sola di verita'», approvata dal
#: proprietario; Tappa 6, Task 6, 05/10/2026). Il nome sta anche
#: nell'identificatore -- `person.paolo`, `device_tracker.iphone_di_paolo` --
#: quindi la riga porta un SEGNAPOSTO al posto dell'id, e la risposta si
#: riporta all'id vero qui dentro (`apply_answer`): il giudizio resta, il nome
#: non esce.
#:
#: Chi e' «persona» non si scrive qui: e' `privacy.MOVING_DOMAINS`, il genere
#: «presenza» del vocabolario dei tipi -- le stesse due specie che Home
#: Assistant dichiara: il dominio `person` (`components/person`, `DOMAIN`) e i
#: `device_tracker` che una persona segue (`ATTR_DEVICE_TRACKERS`, validati con
#: `cv.entities_domain(DEVICE_TRACKER_DOMAIN)`), letti nel sorgente di Core
#: 2026.9.3 il 05/10/2026.
#:
#: Il `#` non puo' collidere con un'entita' vera: Home Assistant ammette
#: nell'object_id solo cifre, minuscole e `_` (`homeassistant/core.py`,
#: `_OBJECT_ID`, Core 2026.9.3, letto il 05/10/2026).
#:
#: **La deroga «salvo che l'obiettivo li chieda» non nasce.** L'obiettivo e'
#: testo libero (`mind/store.objective`): non c'e' un modo per dire «le persone
#: si', per nome» che non sia indovinarlo da una frase. Se servira', nascera'
#: come campo dell'obiettivo, non come lettura della prosa.
PRESENCE_MARK = "#"


def presence_handles(ids) -> dict[str, str]:
    """`entity_id` -> segnaposto, per le sole presenze fra `ids`.

    Il numero e' la posizione nell'ordine degli id, dominio per dominio: e'
    cio' che lo rende ricostruibile quando la risposta torna -- sul ponte
    minuti dopo, da un altro processo -- a partire dallo stesso insieme
    chiesto, senza archiviare una tabella di corrispondenze."""
    handles: dict[str, str] = {}
    counters: dict[str, int] = {}
    for entity_id in sorted(ids):
        domain = domain_of(entity_id)
        if domain in MOVING_DOMAINS:
            counters[domain] = counters.get(domain, 0) + 1
            handles[entity_id] = f"{domain}.{PRESENCE_MARK}{counters[domain]}"
    return handles


def house_lines(house: House, only: set[str] | None = None) -> list[str]:
    """Una riga per entita', **solo quelle che competono all'osservatore**
    (`watched_ids`).

    Ogni riga porta cio' che serve a giudicare e nient'altro: identificatore,
    nome, classe dichiarata da Home Assistant, unita', area, e il
    `translation_key`. Quest'ultimo e' cio' che l'**integrazione dichiara di
    se'** -- `energy_today`, non «Potenza» da indovinare -- ed e' la ragione per
    cui il riconoscimento non e' mai stato il problema di questo prodotto.

    Cio' che NON c'e' e' altrettanto deliberato: `unique_id`,
    `config_entry_id`, `dispositivo_id`, `piattaforma` sono identificatori
    opachi che non aiutano nessun giudizio e costerebbero token su 381 righe.

    **Ogni campo lo chiede alla casa** (Tappa 3, Task 12, 04/10/2026): il nome
    a `House.name` (D1 «vivo»: quello che si vede in Home Assistant), il tipo a
    `House.kind_of` (classe e unita' di adesso), l'area a `House.where` (D3:
    anche quella ereditata dal dispositivo). Fino a quel giorno l'osservatore
    scorreva l'anagrafe da se', col nome del registro e il solo `area_id`
    proprio: 194 entita' guardate su 324 gli arrivavano senza area (cattura
    del 01/10/2026).

    L'area si mostra col **nome**: un `area_id` grezzo in mezzo a un prompt in
    italiano e' rumore. Una pseudo-area («Senza area», «Aree non lette») non
    si mostra: non e' un luogo, e la riga dice gia' l'assenza tacendo. Un nome
    che e' solo l'id ripetuto non si ripete.

    **Una persona o un dispositivo che la segue** (`presence_handles`) ha il
    segnaposto al posto dell'id, e niente nome ne' area -- il nome di
    un'area puo' essere quello di chi ci dorme. Restano classe, unita' e
    chiave di traduzione, che dichiara l'integrazione e non la persona.
    **Una fonte che tace lo dice** (piano degli attori, Task 1.5; G-01):
    `fonte: <stato>` dal vocabolario di `House.source` quando lo stato non e'
    `viva` -- una sparita e' ancora nell'anagrafe, e quindi fra quelle da
    giudicare, ma non parlera'. Una fonte viva, o che lo specchio non ha
    potuto guardare, non costa una parola.
    """
    lines = []
    ids = watched_ids(house, only)
    handles = presence_handles(ids)
    for entity_id in ids:
        kind = house.kind_of(entity_id) or {}
        if entity_id in handles:
            lines.append(" · ".join(
                [handles[entity_id]]
                + [str(value) for value in (kind.get("classe"), kind.get("unita"),
                                            kind.get("translation_key")) if value]))
            continue
        room = ((house.where(entity_id) or {}).get("area")) or {}
        area_name = None if is_pseudo_area(room.get("id")) else room.get("nome")
        name = house.name("entita", entity_id)
        parts = [entity_id]
        for value in (None if name == entity_id else name, kind.get("classe"),
                      kind.get("unita"), area_name, kind.get("translation_key")):
            if value:
                parts.append(str(value))
        state = (house.source(entity_id) or {}).get("stato")
        if state not in (None, _LIVE):
            parts.append(f"fonte: {state}")
        lines.append(" · ".join(parts))
    return lines


#: Lo stato della fonte che parla (`House.source`, Tappa 3, Task 8).
_LIVE = "viva"


def _silent_inside(store, house: House) -> list[tuple[str, dict | None]]:
    """I soggetti decisi DENTRO che la casa non mette piu' davanti
    all'osservatore e la cui fonte tace, con la fonte: `(id, fonte)`.

    Sono quelli che la regola del fuori toglie -- uno spento dal
    proprietario, un'entita' che il registro non conosce piu' -- e che fino al
    05/10/2026 restavano dentro per sempre, perche' nessuna domanda li
    mostrava piu' (G-01). Un soggetto dentro e fuori dalla regola ma VIVO (una
    nascosta che il proprietario ha voluto) non c'entra: parla. Uno che lo
    specchio non ha potuto guardare (`stato: None`) nemmeno: non si sa.
    `House.source` -> `None` (ne' registro ne' stati) si'."""
    if not house.mirror.readable:
        return []
    shown = set(house.visible_entities())
    out = []
    for subject, decision in sorted(store.scope().items()):
        if not decision["dentro"] or not is_entity_id(subject) or subject in shown:
            continue
        source = house.source(subject)
        if source is None or source.get("stato") not in (None, _LIVE):
            out.append((subject, source))
    return out


def gone_lines(store, house: House) -> list[str]:
    """Una riga per soggetto dentro che tace (`_silent_inside`): l'id e la
    fonte. La domanda che apre la campagna li porta a parte, cosi' il modello
    puo' toglierli alla prossima cadenza (piano degli attori, Task 1.5). Il
    codice non toglie niente: nessuna riga dello scope si cancella (D1)."""
    return [f"{subject} · fonte: "
            + (source["stato"] if source is not None
               else "nessuna (ne' nel registro ne' negli stati di Home Assistant)")
            for subject, source in _silent_inside(store, house)]


#: **Il contratto di risposta, e vive una volta sola.** Le due porte lo
#: mettono in due posti diversi -- la catena in coda alla domanda, il ponte
#: come istruzione di chiusura del turno (`agent/prompts.build_chat_messages`,
#: dove l'ultima riga del messaggio e' quella che il modello segue) -- ma il
#: TESTO e' lo stesso, e due copie divergerebbero alla prima correzione fatta
#: da una parte sola.
#:
#: **Il motivo si chiede esplicitamente**, e non e' una cortesia: l'archivio
#: rifiuta una decisione senza ragione (`store.decide_scope`), quindi un
#: contratto che non lo chiedesse si farebbe buttare meta' delle risposte al
#: confine senza che nessuno capisca perche'.
ANSWER_CONTRACT = (
    "Rispondi con un SOLO array JSON, un oggetto per entita':\n"
    '  {"id": "<identificatore>", "dentro": true|false, "motivo": "<una riga in italiano>"}\n'
    "Nessun testo fuori dall'array. Un'entita' su cui davvero non sai "
    "decidere: omettila, invece di inventarti una ragione."
)


def build_question(objective: str, lines: list[str], gone: list[str] = ()) -> str:
    """La domanda intera: l'obiettivo, la casa, e il contratto di risposta.

    E' la forma che serve alla **catena**, dove tutto viaggia in un messaggio
    solo. Il ponte usa gli stessi due pezzi montati diversamente (vedi
    `bridge_turn`): la domanda in cronologia, il contratto come istruzione di
    chiusura.
    """
    return build_house_question(objective, lines, gone) + "\n" + ANSWER_CONTRACT


#: Cosa si dice al modello quando fra le righe ci sono segnaposti: senza,
#: `person.#1` sembrerebbe un identificatore storto da correggere.
PRESENCE_HINT = (
    "Le persone e i dispositivi che le seguono hanno un segnaposto al posto "
    f"dell'identificatore (per esempio person.{PRESENCE_MARK}1) e nessun nome: "
    "giudicali per quello che sono, e nella risposta usa il segnaposto come id.\n")


def build_house_question(objective: str, lines: list[str], gone: list[str] = ()) -> str:
    """L'obiettivo e la casa, **senza** il contratto di risposta.

    `gone` sono le righe di `gone_lines`: i soggetti che guardi e che tacciono
    fuori dalla casa che ti si mostra. Vengono dopo, a parte, solo se ci sono."""
    masked = any(f".{PRESENCE_MARK}" in line.split(" · ", 1)[0] for line in lines)
    question = (
        f"L'obiettivo di questa casa e':\n\n  {objective}\n\n"
        f"Queste sono le {len(lines)} entita' che ti competono. Ogni riga e':\n"
        "identificatore · nome · classe · unita' · area · chiave di traduzione\n"
        "(i campi che mancano sono assenti, non vuoti; «fonte: ...» c'e' solo "
        "quando l'entita' non parla, e dice perche').\n"
        + (PRESENCE_HINT if masked else "")
        + "\n"
        + "\n".join(lines)
        + "\n"
    )
    if gone:
        question += (
            f"\nQuesti {len(gone)} soggetti li guardi gia', ma la loro fonte in "
            "Home Assistant tace e non sono piu' fra quelli sopra. Se non "
            "servono piu', toglili (stesso formato di risposta); se li ometti "
            "restano come sono.\n\n"
            + "\n".join(gone)
            + "\n")
    return question


def read_decisions(answer: str, *,
                   truncated: bool = False) -> tuple[list[dict], str | None]:
    """Le decisioni lette dalla risposta, e la ragione per cui NON si sono
    lette se non si e' potuto.

    **`[]` e un guasto sono due cose diverse.** Un array vuoto afferma «ho
    guardato la casa e non c'e' niente da osservare»; una risposta illeggibile
    non afferma niente, e appiattire la seconda sulla prima e' la bugia che
    questo prodotto rifiuta ovunque.

    **Il JSON lo cava il lettore unico** (`steering.read_json`, D-11), con la
    sua tolleranza -- la staccionata, il testo intorno -- e il suo rifiuto di
    leggere un turno troncato (D2). Qui resta solo la forma della decisione.

    **Una voce storta si salta, le altre restano.** 380 giudizi buoni non si
    perdono per uno malformato -- e la voce saltata resta NON decisa, quindi
    l'impronta la ripresentera' al giro dopo: si ripara da se'.
    """
    parsed, failure = read_json(answer, shape=list,
                                what="un elenco di decisioni",
                                truncated=truncated)
    if failure is not None:
        return [], failure
    decisions = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("id")
        if not isinstance(entity_id, str) or not entity_id:
            continue
        decisions.append({"id": entity_id,
                          "dentro": bool(item.get("dentro")),
                          "motivo": item.get("motivo")})
    return decisions, None


def bridge_turn(store, house: House, only: set[str] | None = None, *,
                opening: bool = True) -> dict:
    """Il turno da accodare al ponte: **la stessa domanda, per un'altra porta**.

    Il ponte gira altrove e non ha gli archivi: cio' che non entra nel job non
    esiste per lui (vedi `keeper/exchange._enqueue_to_bridge`, che fa lo stesso
    per una promessa). Le due chiavi sono quelle che il turno del ponte legge
    davvero -- `agent/runner._reason_chat` -> `prompts.build_chat_messages`.

    **La domanda non si ricompone qui.** Si chiamano `house_lines` e
    `build_house_question`, le stesse che il giro sincrono usa dentro
    `build_question`: due composizioni della stessa domanda sarebbero due
    verita' libere di divergere, e la prima volta che qualcuno aggiunge un
    campo alla riga della casa da una parte sola il ponte e la catena
    giudicherebbero case diverse senza che nessuna pagina lo dica
    (fondamenta 2).

    `opening`: se questo turno apre la campagna (`annota` nella sveglia). Solo
    quello porta i soggetti che tacciono (`gone_lines`): una volta per
    campagna basta, e i lotti dopo non pagano quelle righe.
    """
    return {
        "history": [{"role": "user",
                     "content": build_house_question(
                         store.objective()["testo"], house_lines(house, only),
                         gone_lines(store, house) if opening else [])}],
        "system_prompt": SYSTEM,
        # **Senza questa chiave il ponte gli impone il contrario.** L'istruzione
        # che chiude ogni turno di chat dice «usa testo semplice: niente
        # blocchi di codice o JSON» (`agent/prompts._CHAT_INSTRUCTION`), e
        # l'osservatore chiede esattamente un array JSON: la risposta sarebbe
        # tornata in prosa e `read_decisions` l'avrebbe dichiarata illeggibile
        # -- lo stesso esito del guasto che questa fetta ripara, per un'altra
        # causa. Trovato leggendo il codice l'11/09/2026, prima di rilasciare.
        "istruzione": ANSWER_CONTRACT,
    }


#: Cosa si scrive accanto a un soggetto che il modello ha visto e non ha
#: giudicato. **Non e' una decisione inventata**: la domanda dice «un'entita'
#: su cui davvero non sai decidere: omettila», e questo e' il fatto vero --
#: guardata, e non giudicata. Sta FUORI perche' non c'e' nessun giudizio che
#: la tenga dentro, ed e' visibile nella pagina con la sua ragione, quindi il
#: proprietario puo' rimetterla dentro con un gesto.
OMITTED_REASON = "l'osservatore l'ha guardata e non ha saputo decidere"


def apply_answer(store, house: House, answer: str, *, reason: str = "",
                 window_s: float | None = None, cadence_s: float | None = None,
                 asked: set[str] | None = None,
                 record: bool = True,
                 campaign_ts: float | None = None,
                 now: float | None = None,
                 truncated: bool = False) -> dict:
    """Cosa si fa di una risposta, **da qualunque porta sia arrivata**.

    E' la seconda meta' del giro, separata dalla prima perche' le due meta'
    non avvengono piu' sempre insieme: sulla catena la risposta torna dentro
    la stessa chiamata, sul ponte torna **minuti dopo, da un altro processo**,
    e il giro che la raccoglie e' un altro. Senza questa separazione la
    scrittura delle decisioni esisterebbe in due copie, e la seconda sarebbe
    rimasta indietro alla prima correzione fatta di qua.

    **Un giro fallito non si annota come fatto.** Annotarlo farebbe aspettare
    la cadenza intera -- 84 ore sulla casa vera -- prima di riprovare, su una
    casa di cui non si e' deciso niente.

    **Si accetta solo cio' che era nella domanda.** Un modello puo' inventare
    un identificatore, e un'entita' inventata nello scope sarebbe una riga che
    nessun evento potra' mai accendere e che la pagina mostrerebbe come
    osservata.
    """
    # L'insieme valido e' quello che la casa ha scelto per la domanda, non le
    # righe rilette (Task 12): il separatore e' della resa, non del giudizio.
    # Piu' i soggetti dentro che tacciono (`gone_lines`, Task 1.5): la domanda
    # che apre la campagna li mostra, e una decisione su di loro vale. Non
    # entrano in `asked`: chi li omette li lascia come sono.
    known = set(watched_ids(house, asked)) | {
        subject for subject, _source in _silent_inside(store, house)}
    decisions, failure = read_decisions(answer, truncated=truncated)
    if failure is not None:
        logger.warning("osservatore: %s", failure)
        return {"errore": failure}
    # **Il segnaposto torna id** (decisione 12): si ricostruisce dallo stesso
    # insieme da cui e' nato la domanda -- il lotto, o cio' che la casa guarda.
    handles = {handle: entity_id for entity_id, handle in presence_handles(
        asked if asked is not None else known).items()}
    decisions = [{**decision, "id": handles.get(decision["id"], decision["id"])}
                 for decision in decisions]

    decided = refused = ignored = 0
    for decision in decisions:
        if decision["id"] not in known:
            ignored += 1
            continue
        if store.decide_scope(decision["id"], inside=decision["dentro"],
                              reason=decision["motivo"] or "", author=OBSERVER,
                              when_ts=now):
            decided += 1
        else:
            refused += 1

    # **Cio' che si e' chiesto e il modello ha omesso non resta in sospeso.**
    # Un soggetto non deciso riaccende l'innesco «ci sono cose nuove» al giro
    # dopo, e a quello dopo ancora: la campagna non finirebbe mai e
    # l'osservatore chiederebbe al piano ogni dieci minuti per sempre. Si
    # annota per quello che e' -- guardata, non giudicata -- e resta visibile.
    omitted = 0
    if asked is not None:
        answered = {d["id"] for d in decisions}
        for subject in sorted(asked - answered):
            if subject in known and store.decide_scope(
                    subject, inside=False, reason=OMITTED_REASON,
                    author=OBSERVER, when_ts=now):
                omitted += 1

    if record:
        # **L'istante della campagna, non quello di adesso.** La riconsiderazione
        # segna l'inizio della campagna, e i soggetti giudicati dal primo lotto
        # devono risultare gia' DENTRO di essa: con lo stesso istante finirebbero
        # fra quelli «da rigiudicare», e la campagna girerebbe sul primo lotto
        # per sempre.
        store.record_reconsideration(
            when_ts=campaign_ts if campaign_ts is not None else now,
            window_s=window_s, cadence_s=cadence_s, reason=reason)
    return {"decise": decided, "rifiutate": refused, "ignorate": ignored,
            "omesse": omitted, "candidate": len(known)}


async def reconsider(runner, store, house: House, *, reason: str,
                     window_s: float | None = None, cadence_s: float | None = None,
                     model: str = "auto", only: set[str] | None = None,
                     record: bool = True, campaign_ts: float | None = None,
                     now: float | None = None, measurements=None) -> dict:
    """Un giro intero **sulla catena**: guarda la casa, chiede, e consegna la
    risposta ad `apply_answer`.

    Torna il resoconto del giro, quello di `apply_answer` -- `{"decise",
    "rifiutate", "ignorate", "omesse", "candidate"}` -- o
    `{"errore": ...}` se non si e' potuto fare.

    **Questa e' la porta della catena, non l'unica porta.** Chi decide fra le
    due e' `steering.who_answers`, dalla stessa funzione che lo decide per la
    chat e per le promesse; quando risponde «ponte», il giro passa da
    `bridge_turn` e questa funzione non viene chiamata affatto.
    """
    lines = house_lines(house, only)
    objective = store.objective()["testo"]
    # I soggetti che tacciono solo nella domanda che apre la campagna (quella
    # che annota la riconsiderazione): vedi `bridge_turn`.
    question = build_question(objective, lines,
                              gone_lines(store, house) if record else [])
    try:
        # `user_message=` per nome e non posizionale: `LLMRouter.chat` --
        # il runner vero, quello con la catena di ripiego -- prende `**kwargs`
        # e basta, e un posizionale ci morirebbe sopra al primo giro in
        # produzione senza che nessuna finta lo veda.
        # **La specie si DICHIARA, non si deduce da `agent_type`.** Quello
        # qui sopra vale «observer» e risponde a «quale modello scelgo»; lo
        # passa anche `recipe_turn`, quindi misurare su di lui renderebbe
        # l'osservatore e le ricette indistinguibili -- proprio la
        # distinzione per cui il registro esiste.
        #
        # `misure` e' `None` quando nessuno misura (il caso dei test e di un
        # chiamante che non ha l'archivio): la misura non e' un requisito per
        # girare.
        async with misura_turno(measurements, runner, specie=OBSERVER_SPECIES,
                                canale="catena", modello=model) as turn:
            answer = await runner.chat(
                user_message=question, system_prompt=SYSTEM,
                model=model, agent_type="observer",
                max_tokens=MAX_ANSWER_TOKENS)
    except Exception as error:
        logger.warning("osservatore: il giro non e' partito (%s: %s)",
                       type(error).__name__, error)
        return {"errore": f"il modello non ha risposto: {type(error).__name__}"}

    return apply_answer(store, house, answer, reason=reason,
                        window_s=window_s, cadence_s=cadence_s,
                        asked=set(watched_ids(house, only)),
                        record=record, campaign_ts=campaign_ts, now=now,
                        truncated=turn.truncated)
