"""L'osservatore chiede al modello una ricetta per un dispositivo che pesa.

Spec `docs/design/2026-09-10-i-tre-attori.md` §7.

**Perche' esiste, col numero.** Il registro delle operazioni e il motore delle
ricette sono arrivati con la fetta 4, ma nessuno scriveva ricette nuove: il
repo ne porta **una**, quella del bilancio dell'energia. Misurato sulla casa
vera il 13/09/2026, il resoconto giornaliero avrebbe avuto **~6 misure al
giorno** -- tutte dello stesso inverter -- contro ~28 fatti di cronaca. Tutti e
tre gli inneschi dell'analista (§10) lavorano sulle misure: gliene sarebbe
arrivato il 18%.

**Come, e perche' cosi'.** *«Mostrandogli il dispositivo con tutte le sue
entita' insieme»*: viste insieme, le sette misure di un inverter si spiegano da
sole; viste una alla volta sono sette indovinelli. E **una volta, non ogni
giorno** -- un giro del modello costa, e ripeterlo ogni notte per un
dispositivo gia' capito e' la spesa che non si vede finche' non si guarda la
bolletta.

**Il meccanismo e' lo stesso dello scope**, non un secondo accanto: una specie
di turno, una domanda montata da funzioni che il ponte e la catena
condividono, una risposta letta con la stessa tolleranza (`mind/observer.py`).
La spec lo chiede per nome -- *«un meccanismo solo per due problemi»*.

**Il soggetto e' il DISPOSITIVO**, ed e' il quarto genere del sapere. La spec
§8 esclude una colonna `ambito` perche' il genere dice gia' se una riga e'
universale: `tipo` e `integrazione` lo sono, `entita` e `dispositivo` sono di
questa casa. Una ricetta scritta guardando le entita' vere di questa casa e'
locale per costruzione, e non ha nessun altro soggetto onesto: non e'
dell'integrazione (nomina entita' che un'altra casa non ha) e non e' di
un'entita' sola (ne mette insieme sette).

**Si rifiuta, e non si corregge.** Una ricetta che nomina un'operazione
inesistente o un'entita' che non c'e' non si aggiusta indovinando cosa
intendeva chi l'ha scritta: si scarta, e il rifiuto **si scrive** col suo
perche' (spec §8, *«non capito si scrive»*). Senza quella riga la stessa
domanda tornerebbe ogni notte, e il proprietario non saprebbe mai che quel
dispositivo non e' stato capito.
"""
from __future__ import annotations

import json
import logging
import re

from .knowledge import Fact
from .operations import REGISTRY_VERSION
from .recipes import Recipe

logger = logging.getLogger(__name__)

#: Come si chiama, nella coda del ragionamento, un turno che chiede una
#: ricetta. Sta accanto a `observer.SCOPE_TURN_KIND` per la stessa ragione per
#: cui quello sta li': il nome vive dove il turno nasce.
RECIPE_TURN_KIND = "ricetta"

#: Il campo del sapere che porta la ricetta di un dispositivo.
RECIPE_FIELD = "ricetta"

#: Il campo che porta il RIFIUTO, quando una ricetta non si e' potuta scrivere.
#:
#: **Due campi e non uno**, perche' sono due cose: `ricetta` porta una ricetta
#: eseguibile, `ricetta_non_capita` porta il perche' non ce n'e' una. Metterle
#: nello stesso campo vorrebbe dire che il suo valore significa due cose
#: diverse a seconda di un altro campo -- e chi legge senza guardare l'altro
#: eseguirebbe un elenco di problemi come se fosse una sequenza di passi.
UNDERSTOOD_FIELD = "ricetta_non_capita"

#: Il campo che porta il rifiuto **RAGIONATO**: il modello ha capito, e dice
#: che non c'e' niente che valga la pena misurare.
#:
#: **Tre campi e non due, per la stessa ragione per cui erano due e non uno.**
#: «Non ho capito questo dispositivo» e «ho capito, e non c'e' una misura da
#: ricavarne» sono due fatti diversi: il primo e' un lavoro per il
#: proprietario, il secondo e' una risposta completa. Misurato sulla casa vera
#: il 15/09/2026, il giorno in cui la porta del sapere si e' aperta: **18
#: righe su 21** marcate «non capito» erano rifiuti ragionati, e portavano una
#: frase nostra -- «nessuno ha finito di scrivere» -- che le prove archiviate
#: accanto smentivano parola per parola. Il proprietario avrebbe letto
#: ventuno problemi dove ce n'erano tre.
#:
#: La `verification` resta NULLA, non `non_capito`: quella colonna dice cosa
#: ha detto il CONTROLLO (spec §8), e qui il controllo non ha niente da ridire.
DECLINED_FIELD = "ricetta_non_serve"

#: Contro quale registro il rifiuto e' stato deciso.
#:
#: **I rifiuti sono importanti, e per questo non sono definitivi** (decisione
#: del proprietario, 13/09/2026). Un dispositivo che oggi il modello non sa
#: misurare potrebbe diventare misurabile domani, per una ragione che non ha
#: niente a che vedere con lui: il registro delle operazioni cresce. Il giorno
#: in cui arriva `correlazione` -- o qualunque altro mattone che mancava --
#: ogni «non capito» deciso contro un registro piu' povero e' un giudizio da
#: rifare, non un verdetto.
#:
#: Quindi il rifiuto porta la versione del registro contro cui e' stato preso,
#: e vale finche' quella versione e' quella corrente. E' anche cio' che
#: finalmente da' un LETTORE a `VERSIONE_REGISTRO`, che fino a oggi era un
#: numero scritto e mai interrogato.
REFUSAL_SOURCE = "registro delle operazioni v"

#: Il tetto della risposta. Una ricetta e' una decina di passi: 4.000 token
#: sono larghi il doppio del necessario, e un tetto largo costa solo quando
#: serve davvero.
MAX_ANSWER_TOKENS = 4000

SYSTEM = """Sei l'osservatore di HIRIS, un sistema che guarda una casa domotica.

Il tuo mestiere qui e' UNO: guardare un dispositivo con tutte le sue entita'
insieme, e dire **come si misura** rispetto all'obiettivo della casa.

Non devi decidere se il dispositivo conta -- quello e' gia' stato deciso. Non
devi fare conti: i numeri li calcola il codice. Devi dire QUALI conti vanno
fatti, con quali entita', e perche'.

Quello che scrivi diventa un dato che gira ogni notte, e che si puo' correggere
senza toccare il codice. Se sbagli un'entita' o un'operazione, il codice
**rifiuta** la ricetta e non la aggiusta: meglio una ricetta piu' corta e
giusta che una lunga e storta.

Se guardando questo dispositivo non sai cosa valga la pena misurare, dillo: e'
una risposta legittima, e viene scritta com'e'. Inventare passi che non
servono e' peggio che non risponderne nessuno.
"""

ANSWER_CONTRACT = """
Rispondi con UN SOLO oggetto JSON, senza testo attorno e senza blocchi di
codice, in questa forma:

{"why": "perche' questo dispositivo va misurato, in una frase",
 "steps": [
   {"name": "un nome tuo per questo numero",
    "operation": "il nome di un'operazione dell'elenco qui sotto",
    "inputs": ["@entity_id" oppure "$nome_di_un_passo_precedente"],
    "params": {"unit": "kWh"}}
 ]}

Le regole, e il codice le fa rispettare:
- `operation` deve essere una delle operazioni elencate sopra: nessun'altra;
- `@qualcosa` e' l'identificatore di un'entita' DI QUESTO DISPOSITIVO;
- `$qualcosa` e' il nome di un passo **precedente**, mai successivo;
- ogni passo ha un nome diverso dagli altri;
- niente cicli, niente condizioni: e' una sequenza, non un programma.

Se non sai cosa misurare, rispondi con {"why": "...", "steps": []}.
"""

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _device_entities(home_space: dict, device_id: str) -> list[dict]:
    return [e for e in (home_space.get("entita") or [])
            if e.get("dispositivo_id") == device_id]


def _device_name(home_space: dict, device_id: str) -> str:
    for d in home_space.get("dispositivi") or []:
        if d.get("id") == device_id:
            return str(d.get("nome") or device_id)
    return device_id


def device_lines(home_space: dict, device_id: str) -> list[str]:
    """Una riga per entita' del dispositivo, nella forma gia' usata per lo scope.

    Stessi campi e stesso separatore di `observer.house_lines`: **due forme
    della stessa riga sarebbero due verita' libere di divergere**, e la prima
    volta che qualcuno ne arricchisce una sola il modello leggerebbe due case
    diverse a seconda della domanda.
    """
    lines = []
    for e in _device_entities(home_space, device_id):
        parts = [str(e.get("id") or "")]
        for field in ("nome", "classe", "unita"):
            if e.get(field):
                parts.append(str(e[field]))
        lines.append(" · ".join(parts))
    return lines


def _operations_catalogue() -> str:
    """Le operazioni che esistono, con cosa prendono e quando rifiutano.

    **Si legge dal registro, non si riscrive qui.** Un elenco copiato a mano
    diverge al primo cambio del registro, e il modello proporrebbe operazioni
    che non esistono piu' -- che il codice rifiuterebbe, bruciando un giro.
    """
    from .operations import REGISTRY

    lines = []
    for name, operation in REGISTRY.items():
        # **Solo cio' che una ricetta puo' davvero scrivere.** Il registro e' il
        # vocabolario del prodotto e contiene voci che un dato non sa portare
        # (`episodio` vuole `is_on`, una funzione; `tempo_in_stato` vuole un periodo,
        # che dentro una ricetta nessuno sa produrre). Offrirle qui e' una trappola:
        # il modello le usa, il validatore le rifiuta sempre, il giro e' bruciato
        # e il dispositivo resta senza ricetta per sempre -- `devices_to_ask` non
        # richiede a chi una risposta l'ha gia' data. Misurato dal vivo il
        # 14/09/2026: la prima ricetta che il modello abbia mai scritto.
        if not operation.offerable:
            continue
        entry = (f"- `{name}`: prende {', '.join(operation.inputs)}; "
                f"restituisce {operation.returns}")
        # E si dice cosa PRETENDE. Elencare l'operazione senza i suoi parametri
        # obbligatori e' meta' informazione: il modello scrive `somma_periodo`
        # senza `unit`, il validatore rifiuta, e il giro e' bruciato lo stesso.
        # Si leggono dalla firma di `run`, quindi non possono divergere da cio'
        # che il motore chiede davvero.
        if operation.required_params:
            entry += ("; vuole i parametri obbligatori "
                     + ", ".join(f"`{n}`" for n in operation.required_params))
        lines.append(entry)
    return "\n".join(lines)


def build_device_question(objective: str, home_space: dict, device_id: str,
                          *, with_series: set[str] | None = None) -> str | None:
    """La domanda intera per un dispositivo, o `None` se non c'e' da chiedere.

    `None` quando il dispositivo non ha entita': non ci sarebbe niente da
    mostrare al modello, e la domanda costerebbe un giro per una risposta che
    non puo' esistere.

    **`with_series` dice quali entita' sanno produrre una serie**, ed e' la
    cosa che mancava. Home Assistant tiene statistiche orarie solo per le
    entita' che dichiarano uno `state_class` -- misurato sulla casa vera il
    15/09/2026, **130 su 1206, tutte `sensor`** -- e il modello non ha nessun
    modo di dedurlo dalla riga di un'entita'. Senza, scrive «quanto e' stata
    accesa la lavastoviglie»: la domanda giusta sul dispositivo giusto, contro
    una fonte che per quell'entita' non esiste. Nel resoconto del 14/09/2026
    erano **18 rifiuti su 28**.

    Il fatto si dice **una volta, a parte**, e non dentro la riga
    dell'entita': quella riga e' la stessa di `observer.house_lines`
    (`device_lines` qui sopra), e due forme della stessa riga sarebbero due
    verita' libere di divergere.

    `None` -- e non l'insieme vuoto -- vuol dire «non l'abbiamo potuto
    chiedere»: allora non si dice niente, invece di affermare che nessuna
    entita' ha una serie.
    """
    lines = device_lines(home_space, device_id)
    if not lines:
        return None
    return (
        f"L'obiettivo di questa casa e':\n\n  {objective}\n\n"
        f"Il dispositivo si chiama «{_device_name(home_space, device_id)}» e ha "
        f"{len(lines)} entita'. Ogni riga e':\n"
        "identificatore · nome · classe · unita'\n"
        "(i campi che mancano sono assenti, non vuoti).\n\n"
        + "\n".join(lines)
        + _series_block(home_space, device_id, with_series)
        + "\n\nLe operazioni che sai chiedere sono queste, e nessun'altra:\n\n"
        + _operations_catalogue()
        + "\n" + ANSWER_CONTRACT
    )


def _series_block(home_space: dict, device_id: str,
                 with_series: set[str] | None) -> str:
    """Quali entita' del dispositivo hanno una serie, e quali non l'avranno.

    Vuota quando non lo sappiamo: vedi `build_device_question`.
    """
    if with_series is None:
        return ""
    ids = [str(e.get("id") or "") for e in _device_entities(home_space, device_id)]
    con = [i for i in ids if i in with_series]
    mute = [i for i in ids if i and i not in with_series]
    if not mute:
        return ("\n\nTutte queste entita' hanno una serie oraria: puoi "
                "chiedere qualunque operazione su ciascuna.")
    parts = [("\n\n**Solo alcune di queste entita' hanno una SERIE.** Home "
             "Assistant tiene statistiche orarie soltanto per chi dichiara uno "
             "`state_class`: sulle altre ogni operazione rifiuterebbe, oggi e "
             "sempre.")]
    parts.append("Hanno una serie: "
                 + (", ".join(con) if con else "nessuna di queste entita'") + ".")
    parts.append("NON ne hanno, e non chiederle: " + ", ".join(mute) + ".")
    if not con:
        parts.append("Se nessuna entita' di questo dispositivo ha una serie, "
                     "rispondi con `steps: []` e scrivi nel `why` che non c'e' "
                     "niente da misurare: e' una risposta giusta, non una resa.")
    return "\n".join(parts)


def read_recipe(answer: str) -> tuple[dict | None, str | None]:
    """La ricetta letta dalla risposta, e la ragione per cui NON si e' letta.

    **Una risposta illeggibile e una ricetta vuota sono due cose diverse.** La
    seconda afferma «ho guardato questo dispositivo e non c'e' niente da
    misurare»; la prima non afferma niente. Appiattirle sarebbe la bugia che
    questo prodotto rifiuta ovunque.

    **La staccionata si tollera**, come in `observer.read_decisions`: i modelli
    incorniciano il JSON anche quando si chiede di non farlo, e buttare il giro
    per un dettaglio di forma costerebbe una domanda intera.
    """
    text = (answer or "").strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError) as error:
        return None, f"la risposta non e' un JSON leggibile ({type(error).__name__})"
    if not isinstance(parsed, dict):
        return None, "la risposta non e' una ricetta"
    return parsed, None


def _only_answer(store, device_id: str, kept: str) -> None:
    """Cancella le risposte VECCHIE di questo dispositivo, tenendo `kept`.

    **Un dispositivo non puo' essere «non capito» e avere una ricetta che gira
    ogni notte.** `apply_recipe` scriveva il suo campo e lasciava gli altri
    dov'erano: il giorno in cui un rifiuto scade e il modello risponde bene,
    la riga vecchia resta, e la **porta del sapere** continua a elencare quel
    dispositivo fra i «non capiti» -- cioe' fra le cose su cui il proprietario
    dovrebbe intervenire -- mentre non c'e' piu' niente da fare.
    `devices_to_ask` era corretto; era la pagina a mentire. Trovato dalla
    revisione indipendente il 15/09/2026.
    """
    for field in (RECIPE_FIELD, UNDERSTOOD_FIELD, DECLINED_FIELD):
        if field != kept:
            store.forget("dispositivo", device_id, field)


def apply_recipe(store, home_space: dict, device_id: str, answer: str, *,
                 who: str, when_ts: float) -> dict:
    """Cosa si fa della risposta: si valida, e si scrive cio' che ne esce.

    Torna `{"scritta": bool, "problemi": [...]}`.

    **Si rifiuta, non si corregge** (spec §7). E il rifiuto **si scrive**
    (spec §8): senza quella riga la stessa domanda tornerebbe ogni notte, e il
    proprietario non saprebbe mai che quel dispositivo non e' stato capito.

    **Ma «il modello non ha capito» e «nessuno ha chiesto al modello» sono due
    cose**, e questa funzione ha scritto la prima al posto della seconda per
    un'ora intera, il 13/09/2026. Il ponte non sapeva ragionare la specie di
    turno, restituiva una decisione VUOTA, e quella risposta inesistente
    veniva scritta come `non_capito` -- un'affermazione sulla comprensione di
    un modello che non era mai stato interpellato. E siccome un rifiuto vale
    come risposta data, quel dispositivo non sarebbe stato chiesto **mai
    piu'**.

    Quindi: una risposta **vuota** non si scrive affatto. Non consuma il
    colpo, e il giro successivo richiede. Non c'e' bisogno di un freno --
    quando il ponte rifiuta una specie lo fa in millisecondi, senza chiamare
    nessun modello: il giro a vuoto costa zero.
    """
    if not str(answer or "").strip():
        logger.warning(
            "ricette: nessuna risposta per «%s» -- non si scrive niente, si "
            "richiede al giro dopo (una risposta che non c'e' non e' un «non "
            "capito»)", device_id)
        return {"scritta": False, "problemi": ["il modello non ha risposto"],
                "risposta": False}
    entities = {str(e.get("id")) for e in _device_entities(home_space, device_id)}
    data, reason = read_recipe(answer)
    problems = [reason] if reason else []
    if data is not None:
        outcome = Recipe(data).validate(entities=entities)
        problems = list(outcome.problems)
        if outcome.valid:
            store.write(Fact(
                subject_kind="dispositivo", subject=device_id,
                field=RECIPE_FIELD, value=json.dumps(data, ensure_ascii=False),
                provenance="dedotto",
                evidence=("il dispositivo con le sue " f"{len(entities)} entita', "
                          "mostrate insieme al modello con l'obiettivo della casa"),
                who=who, when_ts=when_ts))
            _only_answer(store, device_id, RECIPE_FIELD)
            return {"scritta": True, "problemi": [], "risposta": True}
        # **Il rifiuto ragionato si separa QUI, alla fonte.** Il modello ha
        # usato il contratto: un `why` pieno e `steps` esplicitamente vuoto.
        # Non e' una ricetta monca, e' una risposta -- «questo dispositivo non
        # ha niente che valga la pena misurare» -- e va archiviata come tale,
        # con LE SUE parole. Separarla a valle (leggendo le prove e cercando
        # un `why` dentro il testo della risposta) vorrebbe dire ricostruire
        # per indovinelli cio' che qui si sa con certezza.
        if _is_declined(data):
            store.write(Fact(
                subject_kind="dispositivo", subject=device_id,
                field=DECLINED_FIELD, value=str(data.get("why")).strip(),
                provenance="dedotto",
                evidence=f"il modello ha risposto: {str(answer).strip()[:1500]}",
                source=f"{REFUSAL_SOURCE}{REGISTRY_VERSION}",
                who=who, when_ts=when_ts))
            _only_answer(store, device_id, DECLINED_FIELD)
            return {"scritta": False, "problemi": problems, "risposta": True,
                    "declinata": True}
    # **Il rifiuto porta cosa il modello ha DETTO**, non solo cosa non andava.
    # Senza, il proprietario legge «l'entita' non e' fra quelle consegnate» e
    # non puo' sapere se il modello avesse capito il dispositivo e sbagliato un
    # identificatore, o non avesse capito niente. Sono due cose diverse, e la
    # seconda la risolve lui in dieci secondi.
    store.write(Fact(
        subject_kind="dispositivo", subject=device_id, field=UNDERSTOOD_FIELD,
        value=" · ".join(problems) or "il modello non ha proposto nessun passo",
        provenance="dedotto",
        evidence=f"il modello ha risposto: {str(answer).strip()[:1500]}",
        source=f"{REFUSAL_SOURCE}{REGISTRY_VERSION}",
        verification="non_capito", who=who, when_ts=when_ts))
    _only_answer(store, device_id, UNDERSTOOD_FIELD)
    return {"scritta": False, "problemi": problems, "risposta": True}


def _is_declined(data: dict) -> bool:
    """Se la risposta e' un rifiuto **ragionato** e non una ricetta monca.

    Due condizioni, e servono tutte e due: il `why` c'e' e non e' vuoto, e
    `steps` e' una lista **esplicitamente vuota**. Una risposta senza `why`
    non ha detto «non serve»: ha smesso di parlare a meta', e quella resta un
    «non capito» -- il confine e' provato da
    `test_una_risposta_senza_passi_e_SENZA_perche_resta_NON_CAPITA`.
    """
    if not isinstance(data, dict):
        return False
    steps = data.get("steps")
    return (isinstance(steps, list) and not steps
            and bool(str(data.get("why") or "").strip()))


def devices_to_ask(store, home_space: dict, watched: set[str]) -> list[str]:
    """I dispositivi che **pesano** e non hanno ancora una risposta.

    «Pesa» = almeno una sua entita' e' dentro lo scope, cioe' l'osservatore ha
    gia' deciso che quello che fa conta. Chiedere per un dispositivo che
    nessuno guarda sarebbe un giro del modello per un numero che nessuno
    leggera'.

    «Non ha ancora una risposta» guarda **tutti e tre** i campi: una ricetta
    scritta, un rifiuto ragionato, oppure un «non capito» gia' registrato.
    Guardarne uno solo farebbe richiedere ogni notte, per sempre, i
    dispositivi che il modello non ha saputo leggere.

    **Ma un rifiuto NON e' definitivo** (decisione del proprietario,
    13/09/2026): vale finche' vale il registro contro cui e' stato deciso. Il
    giorno in cui il registro delle operazioni cresce, ogni «non capito» preso
    con un registro piu' povero torna una domanda aperta -- perche' il
    dispositivo non e' cambiato, e' cambiato cio' che sappiamo calcolare.
    """
    to_ask = []
    for device in home_space.get("dispositivi") or []:
        device_id = str(device.get("id") or "")
        if not device_id:
            continue
        entities = {str(e.get("id")) for e in _device_entities(home_space, device_id)}
        if not entities & watched:
            continue
        if store.get("dispositivo", device_id, RECIPE_FIELD) is not None:
            continue
        answers = (store.get("dispositivo", device_id, UNDERSTOOD_FIELD),
                   store.get("dispositivo", device_id, DECLINED_FIELD))
        if any(r is not None and _still_valid(r) for r in answers):
            continue
        to_ask.append(device_id)
    return to_ask


def who_to_ask(to_ask: list[str], turn: int) -> tuple[str | None, int]:
    """A chi chiedere in questo giro, e il contatore per il prossimo.

    **Chiedere sempre al primo della lista e' una trappola.** Se la risposta
    non arriva -- il modello solleva, il ponte torna una decisione vuota --
    non si scrive niente, e il giro dopo ripesca lo stesso dispositivo. Per
    sempre: gli altri non vengono chiesti mai. Il freno che esiste rallenta a
    un giro all'ora, non cambia dispositivo.

    Trovata dalla revisione indipendente il 15/09/2026, e diventata attuale il
    giorno dopo: alzando la versione del registro sono tornati **31
    dispositivi** da chiedere in una volta.

    Il contatore vive in memoria e riparte da capo al riavvio. Non e' una
    promessa di equita' perfetta -- e' la garanzia che nessuno resti dietro a
    uno rotto.
    """
    if not to_ask:
        return None, turn
    return to_ask[turn % len(to_ask)], turn + 1


def drop_recipes_without_series(store, home_space: dict,
                               *, with_series: set[str] | None) -> int:
    """Toglie le ricette le cui entita' **non hanno nessuna serie**, e torna
    quante ne ha tolte.

    **Dire la verita' nel rifiuto non bastava.** Dalla 3.47.0 una misura su
    un'entita' senza statistiche dice perche'; ma il dispositivo ha una
    ricetta, e `devices_to_ask` salta chi una risposta l'ha gia' data: quelle
    ricette avrebbero prodotto lo stesso nulla ogni notte, per sempre, solo
    con una frase migliore. Misurato sulla casa vera il 15/09/2026: **dieci
    dispositivi**, 18 misure rifiutate al giorno.

    Tolta la riga, il dispositivo torna fra quelli da chiedere -- e stavolta
    la domanda gli dice quali entita' abbiano una serie, cosi' puo' rispondere
    `steps: []` col suo perche', che e' la risposta giusta.

    **Solo quando NESSUNA entita' della ricetta ha una serie.** Una ricetta
    con un passo buono e uno muto porta ancora un numero vero: toglierla
    costerebbe una misura certa per una possibile.

    **`None` non e' l'insieme vuoto**: se non si e' potuto chiedere a Home
    Assistant quali entita' abbiano statistiche non si cancella niente. Con
    l'insieme vuoto si cancellerebbero tutte le ricette della casa al primo
    guasto del websocket.
    """
    if with_series is None:
        return 0
    dropped = 0
    for device in home_space.get("dispositivi") or []:
        device_id = str(device.get("id") or "")
        if not device_id:
            continue
        written = recipe_for(store, device_id)
        if written is None:
            continue
        named = Recipe(written).entities()
        if named and not (named & with_series):
            store.forget("dispositivo", device_id, RECIPE_FIELD)
            dropped += 1
            logger.info(
                "ricette: tolta la ricetta di «%s» -- nessuna delle sue %d "
                "entita' ha statistiche in Home Assistant, quindi non poteva "
                "produrre nemmeno un numero. Torna fra quelle da chiedere",
                device_id, len(named))
    return dropped


def _still_valid(rejection) -> bool:
    """Se un rifiuto vale ancora, cioe' se il registro non e' cambiato.

    Un rifiuto senza la versione scritta e' di prima di questa regola: vale
    come scaduto, e il dispositivo torna fra quelli da chiedere. E' la scelta
    prudente nel verso giusto -- chiedere una volta di piu' costa un turno,
    non chiedere mai piu' costa un dispositivo.
    """
    expected = f"{REFUSAL_SOURCE}{REGISTRY_VERSION}"
    return (rejection.source or "") == expected


def recipe_for(store, device_id: str) -> dict | None:
    """La ricetta di un dispositivo, o `None` se non ne ha una valida."""
    fact = store.get("dispositivo", device_id, RECIPE_FIELD)
    if fact is None or not fact.value:
        return None
    try:
        return json.loads(fact.value)
    except (ValueError, TypeError):  # pragma: no cover - riga corrotta a mano
        logger.warning("sapere: la ricetta di %s non si legge come JSON", device_id)
        return None


def bridge_turn(objective: str, home_space: dict, device_id: str,
                *, with_series: set[str] | None = None) -> dict | None:
    """Il turno da accodare al ponte, o `None` se non c'e' da chiedere.

    Stessa forma di `observer.bridge_turn`, e per le stesse ragioni: il ponte
    gira altrove e non ha gli archivi, e `istruzione` serve perche' altrimenti
    l'istruzione di chiusura della chat gli vieta il JSON che qui si chiede.
    """
    question = build_device_question(objective, home_space, device_id,
                                     with_series=with_series)
    if question is None:
        return None
    return {"history": [{"role": "user", "content": question}],
            "system_prompt": SYSTEM,
            "istruzione": ANSWER_CONTRACT}


async def ask(runner, store, home_space: dict, device_id: str, *,
              objective: str, who: str, when_ts: float,
              model: str = "auto",
              with_series: set[str] | None = None) -> dict:
    """Un giro intero sulla catena: mostra il dispositivo, chiede, applica.

    **Questa e' la porta della catena, non l'unica porta**: quando
    `steering.who_answers` risponde «ponte», il giro passa da `bridge_turn` e
    questa funzione non viene chiamata affatto.
    """
    question = build_device_question(objective, home_space, device_id,
                                     with_series=with_series)
    if question is None:
        return {"scritta": False, "problemi": ["il dispositivo non ha entita'"]}
    try:
        answer = await runner.chat(user_message=question, system_prompt=SYSTEM,
                                   model=model, agent_type="observer",
                                   max_tokens=MAX_ANSWER_TOKENS)
    except Exception as error:
        logger.warning("ricetta: il giro non e' partito (%s: %s)",
                       type(error).__name__, error)
        return {"errore": f"il modello non ha risposto: {type(error).__name__}"}
    return apply_recipe(store, home_space, device_id, answer,
                        who=who, when_ts=when_ts)
