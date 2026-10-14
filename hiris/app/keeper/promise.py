"""La forma di una promessa -- e l'unico posto in cui si decide com'e' fatta.

Puro: nessun I/O, nessun orologio letto qui dentro (`adesso` arriva sempre da
fuori, o i test dovrebbero inseguire il tempo vero). Chi salva e' l'archivio,
chi la sveglia e' l'orologio: qui c'e' solo cosa puo' nascere e come si legge.

`serializza()` e' l'unica forma della promessa, e vale sia per lo strumento del
modello sia per la rotta HTTP. Sono due porte sulla stessa cosa, e la
fondamenta n.3 chiede che ne esca la stessa cosa: due funzioni sarebbero due
verita' che divergono al primo campo aggiunto da una parte sola.

Le chiavi in uscita ci sono SEMPRE, anche a `None`. Una chiave che compare per
un `fai` e sparisce per un `chiedi` obbligherebbe chi legge a sapere gia' di
che specie sta parlando -- cioe' a interpretare il dato con qualcosa che il
dato non porta.
"""
from __future__ import annotations

import json

from ..answer_reasons import NO_ANSWER_REASON
from ..chat_thread import thread_from_columns
from ..home_space.historian import home_space_zone, instant_out
from ..proxy._sanitize import truncate_with_marker
from ..states import CANCELLED, FAILED, KEPT, PENDING, SKIPPED, SUSPENDED, readable

VERB = ("fai", "chiedi")
#: Gli stati che chiudono una promessa. Le parole vivono nel vocabolario
#: (`states.py`, Tappa 8, D4): qui si dice solo quali sono le conclusive di
#: questa coda. L'insieme «in sospeso» e' `states.SUSPENDED`, la sua casa
#: sola: fino all'08/10/2026 ce n'era una copia qui e una in
#: `action/construction/revisions.py`. Dal 13/10/2026 (C-12) la pagina Impegni
#: non ne tiene copie: legge `sospesa` ed `esito` da `serializza`.
STATES_CONCLUSI = (KEPT, SKIPPED, CANCELLED, FAILED)

# Gli stati che sono una NOTIZIA per chi legge -- `STATES_CONCLUSI` meno
# `disdetta`. Sono due insiemi diversi perche' rispondono a due domande
# diverse: `STATES_CONCLUSI` dice «questa promessa e' finita» (e serve a
# potare, a non ridisdire, a riempire lo storico); questo dice «e' successo
# qualcosa che l'utente non sa».
#
# `disdetta` e' l'unica differenza, ed e' l'intera ragione di questa
# costante: una promessa disdetta non e' un esito che ti e' capitato, e' un
# ordine che hai dato tu un istante fa. Contarla fra gli esiti da leggere
# faceva comparire, sotto gli occhi di chi aveva appena premuto «Disdici»,
# una sezione intitolata «da quando non guardavi» -- e accendeva il pallino
# per richiamarlo a leggere cio' che aveva appena ordinato (review
# indipendente della fetta «i menu esecutivi», rilievo 5).
#
# Il difetto era entrato da una scorciatoia, non da una scelta: il filtro
# non nominava gli stati conclusi, li ricavava come complemento di
# `states.SUSPENDED`. Il complemento e' comodo e non ha opinioni -- prende
# dentro tutto cio' che non e' in sospeso, `disdetta` compresa. Percio' qui
# c'e' un elenco esplicito: e' l'unico modo perche' la domanda «questo e'
# una notizia?» abbia una risposta scritta invece che dedotta.
STATES_ESITO = (KEPT, SKIPPED, FAILED)

# Lo stato da cui una promessa si disdice: `store.cancel` lo scrive nella sua
# `UPDATE ... WHERE`, e `serializza` lo manda alla pagina come `disdicibile`.
# Una regola, una casa (C-10, Chiusura, 14/10/2026): fino ad allora la pagina
# Impegni la ricopiava come `stato === 'in_attesa'`. `in_corso` e' in sospeso
# ma non si disdice: l'orologio l'ha gia' presa.
CANCELLABLE = PENDING

# La tolleranza: oltre questa, una promessa scaduta non si mantiene piu' --
# si dichiara `saltata`. Una sola, non configurabile per promessa (spec §7).
# Copre il caso vero per cui esiste: un aggiornamento dell'add-on che cade
# sopra l'orario.
TOLLERANZA_S = 120
# I tetti (spec §9.1.6): non si promette oltre 30 giorni, e non stanno in
# sospeso piu' di 50 promesse. Servono perche' un modello che va in circolo non
# deve poter riempire il disco.
ORIZZONTE_S = 30 * 86400
# **Le 50 sono PER FILO** dalla fetta «il seguito delle chat divise» (spec
# 2026-09-26 §2): con un tetto della casa, le promesse di Marta avrebbero
# potuto togliere a Paolo il diritto di prometterne una -- e il messaggio di
# rifiuto gli avrebbe parlato di promesse che non vede.
SUSPENDED_CAP = 50
# **E il totale resta limitato** (ruling 2.6 della revisione di sicurezza): un
# tetto solo per filo lascerebbe il totale crescere col numero dei fili, e i
# fili li moltiplica chiunque arrivi da un ingresso diverso. 200 tiene il disco
# della scheda SD e il battito dell'orologio (che legge le scadute ogni 15
# secondi) nell'ordine di grandezza di oggi: quattro fili pieni, non di piu'.
HOUSE_SUSPENDED_CAP = 200

_CHIAVI = (
    "id", "specie", "frase", "quando_ts", "quando_detto", "fuso", "chiamata",
    "domanda", "istantanea", "stato", "stato_leggibile", "motivo", "esecuzione_id",
    "testo", "avvisare", "nata_ts", "risvegliata_ts", "esito_letto_ts",
    # `entities_at_birth`: quante entita' toccava il bersaglio alla nascita
    # (reperto B-6, 22/09/2026). In inglese perche' le colonne nuove lo sono.
    "entities_at_birth",
    # Il filo di chi l'ha chiesta (spec 2026-09-26 §2), come `ChatThread` --
    # la stessa forma della coda e delle costruzioni. Serve DENTRO il
    # processo (l'orologio, la consegna dell'esito); le rotte e lo strumento
    # lo tolgono con `chat_thread.without_thread` prima di rispondere.
    "thread",
    # Quando si e' conclusa (G-20, Tappa 8): `risvegliata_ts` e' la presa.
    "closed_ts",
    # Cosa vuol dire lo stato, calcolato qui (C-12, Chiusura, 13/10/2026):
    # in sospeso (`states.SUSPENDED`) e un esito da leggere (`STATES_ESITO`).
    # La pagina Impegni ne teneva le due liste sue.
    "sospesa", "esito",
    # Se si puo' disdire (C-10, Chiusura, 14/10/2026): la regola di
    # `AgendaStore.cancel`, che la pagina Impegni ricopiava in JS. Le
    # uguaglianze semplici (`stato == mantenuta`...) non viaggiano qui: sono
    # `stato` scritto una seconda volta (N159-2), e la pagina le fa con le
    # parole che la rotta le manda (`handlers_agenda.PAGE_STATES`).
    "disdicibile",
)


# Il TITOLO con cui HIRIS si presenta in una notifica di promessa. Uno solo,
# qui, perche' e' parte della forma della chiamata di recapito -- e la forma
# vive in un posto solo (`delivery_call`).
DELIVERY_TITLE = "HIRIS"

# Il tetto del testo che arriva al TELEFONO (vincolo 3.1). Il testo e'
# prodotto dal modello: senza un tetto, un turno andato in circolo
# spingerebbe pagine intere su una notifica. 500 caratteri, anche a 4 byte
# l'uno, stanno sotto i 4096 byte che Apple dichiara come massimo di un
# payload di notifica remota. Nella chat il testo resta intero: li' si
# legge, non si notifica.
PUSH_MESSAGE_CAP = 500
# Il tetto di un motivo o di un errore che entra in un racconto (vincolo
# 3.7): una riga da leggere, non un allegato. E' anche il tetto del motivo che
# cita la risposta del modello (`_quoting`): un tetto solo (B-54).
REASON_CAP = 300
# La frase originale citata nel messaggio d'esito: e' di chi ha chiesto e
# torna a lui, ma resta un campo limitato come gli altri.
PHRASE_CAP = 200
# Al piu' tre servizi per promessa, a ogni risveglio (ruling 3.4). Una
# persona vera ha un telefono e forse un tablet; un recapito che ne
# risolvesse dieci farebbe di un esito dieci notifiche. Il limite
# accettato: nessun freno GLOBALE sulle push in questa fetta -- il numero
# delle promesse e' gia' limitato (`SUSPENDED_CAP`,
# `HOUSE_SUSPENDED_CAP`), e questo tetto limita il resto.
MAX_SERVICES_PER_PROMISE = 3


# I `message` che l'app Companion NON mostra ma ESEGUE come comando sul
# dispositivo. Verificati sulla documentazione ufficiale il 26/09/2026:
# companion.home-assistant.io/docs/notifications/notification-commands
# (iOS: request_location_update, clear_badge, clear_notification,
# update_complications, update_widgets, la famiglia kiosk_*; Android:
# clear_notification, remove_channel, request_location_update, la famiglia
# command_*) e .../notifications-basic (TTS su Android, delete_alert su iOS).
# Il testo della push lo scrive il modello: un esito che fosse esattamente una
# di queste parole diventerebbe un comando al telefono invece di una frase.
_COMPANION_COMMANDS = frozenset({
    "request_location_update", "clear_badge", "clear_notification",
    "update_complications", "update_widgets", "remove_channel", "tts",
    "delete_alert",
})
_COMPANION_COMMAND_PREFIXES = ("command_", "kiosk_")
# Cio' che arriva al telefono al posto di un comando: l'esito intero resta
# nella chat.
COMMAND_REPLACEMENT = "l’esito è nella tua chat."


def push_message(text) -> str:
    """Il testo di una push d'esito: quello del modello, tagliato al tetto
    col marcatore dichiarato -- e mai un comando dell'app Companion."""
    message = truncate_with_marker(text if isinstance(text, str) else "",
                                   PUSH_MESSAGE_CAP)
    word = message.strip().lower()
    # Le famiglie valgono per una parola SOLA (`command_dnd`), come le parole
    # esatte: una frase che comincia cosi' non e' un comando.
    single_word = bool(word) and not any(c.isspace() for c in word)
    if word in _COMPANION_COMMANDS or (
            single_word and word.startswith(_COMPANION_COMMAND_PREFIXES)):
        return COMMAND_REPLACEMENT
    return message


def _phrase(promise: dict) -> str:
    return truncate_with_marker(str(promise.get("frase") or "").strip(), PHRASE_CAP)


def outcome_message(promise: dict, text: str) -> str:
    """Il messaggio di HIRIS nel filo di chi ha chiesto, quando un `chiedi`
    si conclude (spec §2.4): una riga che nomina la promessa -- la frase di
    allora -- e poi la risposta, intera."""
    return f"Esito della promessa «{_phrase(promise)}»:\n{text}"


def kept_message(promise: dict, notice: str | None) -> str:
    """Il racconto di un `fai` mantenuto. `notice` e' l'avviso del bersaglio
    cambiato (`sweeper.target_changed`), gia' una frase di HIRIS."""
    line = f"Ho mantenuto la promessa «{_phrase(promise)}»."
    return f"{line} {notice}" if notice else line


def failure_message(promise: dict, reason) -> str:
    """La riga breve di una promessa che non si e' potuta mantenere (ruling
    3.8): stessa forma da qualunque strada arrivi il fallimento. Il motivo
    entra tagliato al tetto."""
    short = truncate_with_marker(str(reason or "").strip(), REASON_CAP)
    return f"La promessa «{_phrase(promise)}» non si è potuta mantenere: {short}"


def delivery_call(recipient: str, message: str = "") -> dict:
    """La chiamata con cui una promessa arriva a chi l'ha chiesta.

    **La sua UNICA casa**: la forma di una notifica di promessa vive qui e
    in nessun altro posto, cosi' che chi la manda e chi la prova facciano la
    stessa domanda a `action/verification.verification` invece di due domande
    diverse sullo stesso fatto (audit delle fondamenta, rilievo 1, 08/09/2026:
    `notify.send_message` dichiara un `target` e con bersaglio vuoto risponde
    «serve un bersaglio»; `notify.mobile_app_*` no, e passa).

    Il `bersaglio` e' vuoto per costruzione: **il servizio lo sceglie il
    sistema, non il modello**. Dalla fetta «il seguito delle chat divise»
    (spec 2026-09-26 §2.3) non lo sceglie piu' nemmeno alla nascita: si
    risolve al risveglio dal soggetto di chi ha chiesto
    (`keeper/recipient.py::recipients_for`), e il modello ha prodotto un
    testo, mai un indirizzo.
    """
    return {"servizio": recipient, "bersaglio": {},
            "dati": {"message": message, "title": DELIVERY_TITLE}}


def validate(data: dict, *, now: float) -> str | None:
    """Il motivo per cui questa promessa non puo' nascere, o `None`.

    Ritorna una frase da mostrare all'utente, non un codice: chi la riceve e'
    uno strumento che parla a un modello, che a sua volta la deve poter
    spiegare a una persona.
    """
    verb = data.get("specie")
    if verb not in VERB:
        return ("una promessa e' «fai» (un'azione) o «chiedi» (una domanda a cui "
                f"rispondere piu' tardi): «{verb}» non e' ne' l'una ne' l'altra.")

    phrase = data.get("frase")
    if not isinstance(phrase, str) or not phrase.strip():
        return ("serve la frase con cui l'hai chiesto, cosi' com'e': e' cio' che "
                "rende la promessa leggibile anche fra sei mesi.")

    when = data.get("quando_ts")
    if not isinstance(when, (int, float)) or isinstance(when, bool):
        return "serve un momento preciso in cui mantenerla."
    if when <= now:
        return ("quel momento e' gia' passato: intendevi domani? Dimmelo e la "
                "rifaccio.")
    if when > now + ORIZZONTE_S:
        return ("non tengo promesse oltre 30 giorni: e' il tetto che HIRIS si "
                "e' dato.")

    if verb == "fai":
        call = data.get("chiamata")
        if not isinstance(call, dict) or not call.get("servizio"):
            return "una promessa «fai» ha bisogno del servizio da chiamare."
    else:
        domanda = data.get("domanda")
        if not isinstance(domanda, str) or not domanda.strip():
            return "una promessa «chiedi» ha bisogno della domanda a cui rispondere."
    return None


def _load(reading):
    """Un campo JSON dell'archivio, o `None`. Non solleva mai.

    Una riga scritta male non deve rendere illeggibile TUTTA la promessa: la
    frase e lo stato restano veri anche se `chiamata` non si riapre.
    """
    if not reading:
        return None
    try:
        return json.loads(reading)
    except (ValueError, TypeError):
        return None


def _column(row, name):
    """Il valore di una colonna che POTREBBE non esserci ancora.

    `serializza` gira anche su righe lette da un archivio che una migrazione
    non ha ancora toccato: chiedere una colonna assente solleverebbe, e la
    forma promette «stesse chiavi, sempre».
    """
    try:
        return row[name]
    except (IndexError, KeyError):
        return None


def _snapshot_out(snapshot, timezone):
    """L'istantanea come esce: l'istante di ogni misura nell'ora della casa
    (decisione D3, 05/10/2026), col fuso che la promessa porta con se'.

    Le misure nate dall'11/10/2026 portano gia' `quando` in ISO
    (`ToolDispatcher._snapshot`); quelle di prima, portate ai nomi nuovi dalla
    migrazione 6 di `keeper/store.py`, tengono l'epoch di allora. Si cambia la
    resa, non il record: `instant_out` rende uguali le due forme.
    """
    if not isinstance(snapshot, list):
        return snapshot
    zone = None
    out = []
    for measurement in snapshot:
        if isinstance(measurement, dict) and "quando" in measurement:
            zone = zone or home_space_zone(timezone)
            measurement = {**measurement,
                           "quando": instant_out(measurement["quando"], zone)}
        out.append(measurement)
    return out


def serializza(row) -> dict:
    """L'unica forma di una promessa. Stesse chiavi, sempre."""
    fuori = {
        "id": row["id"],
        "specie": row["specie"],
        "frase": row["frase"],
        "quando_ts": row["quando_ts"],
        "quando_detto": row["quando_detto"],
        "fuso": row["fuso"],
        "chiamata": _load(row["chiamata_json"]),
        "domanda": row["domanda"],
        "istantanea": _snapshot_out(_load(row["istantanea_json"]), row["fuso"]),
        "stato": row["stato"],
        # La frase dello stato, dal vocabolario (C-10, Tappa 8): la pagina
        # Impegni la mostra com'e', con la stessa chiave delle costruzioni.
        "stato_leggibile": readable(row["stato"]),
        "motivo": row["motivo"],
        "esecuzione_id": row["esecuzione_id"],
        "testo": row["testo"],
        "avvisare": None if row["avvisare"] is None else bool(row["avvisare"]),
        "nata_ts": row["nata_ts"],
        "risvegliata_ts": row["risvegliata_ts"],
        # Quante entita' toccava il bersaglio ALLA NASCITA (reperto B-6).
        # `None` quando non c'era niente da risolvere -- un bersaglio di sole
        # entita' -- e per le promesse nate prima del 22/09/2026, che quel
        # numero non ce l'hanno: `None` e `0` sono due cose diverse, e «non si
        # applica» non e' «nessuna entita'».
        "entities_at_birth": _column(row, "entities_at_birth"),
        # NULL = non letto. La pagina Impegni ci costruisce sopra la sezione
        # «Esiti da leggere», e il pallino ci conta sopra. E' NULL anche per
        # ogni promessa IN SOSPESO -- che non ha ancora un esito -- quindi da
        # solo non basta a dire «da leggere»: serve anche uno stato concluso.
        "esito_letto_ts": row["esito_letto_ts"],
        # `None` per le promesse nate prima delle promesse divise, finche' il
        # proprietario non le adotta (`chat_thread.adopt_if_owner`).
        "thread": thread_from_columns(_column(row, "subject_key"),
                                      _column(row, "entry_point")),
        "closed_ts": _column(row, "closed_ts"),
        # `disdetta` e' conclusa ma non e' un esito: e' un ordine appena dato
        # (vedi `STATES_ESITO`). Le due domande hanno due risposte.
        "sospesa": row["stato"] in SUSPENDED,
        "esito": row["stato"] in STATES_ESITO,
        "disdicibile": row["stato"] == CANCELLABLE,
    }
    assert set(fuori) == set(_CHIAVI)  # la forma e' una sola, e si controlla qui
    return fuori


def delay_reason(delay_s: float) -> str:
    """Cio' che si e' MISURATO, non una causa inventata (spec §7).

    HIRIS non sa perche' era ferma. Sa di quanto e' in ritardo, e dice solo
    quello.
    """
    minuti = int(delay_s // 60)
    if minuti < 1:
        return "scaduta da meno di un minuto quando l’orologio l’ha vista -- non eseguita."
    return f"scaduta da {minuti} minuti quando l’orologio l’ha vista -- non eseguita."


def bridge_silence_reason(provider_name: str, minutes: int) -> str:
    """Il motivo di una promessa il cui turno sul ponte e' scaduto senza
    risposta (`reasoning/consegna.close_expired_promise`): quanto si e' aspettato, e chi.
    Come `delay_reason`, dice cio' che si e' misurato e nient'altro."""
    return (f"ho aspettato il {provider_name} per {minutes} minuti e non ha "
            "risposto: non so cosa dirti.")


def _quoting(prefix: str, detto: str, suffix: str = "") -> str:
    """Un motivo che cita la risposta del modello: `prefix`, la citazione e
    `suffix`, col tutto dentro il tetto dei motivi (`REASON_CAP`).

    Il motivo finisce in una colonna di SQLite, in una riga della pagina
    Promesse e nel racconto di `failure_message`, che lo taglia a quel tetto:
    si taglia qui la sola citazione, perche' il motivo intero ci stia e il
    secondo taglio non trovi niente. Fino alla Tappa 8 (B-54) la citazione
    aveva un tetto suo dello stesso numero (`_CEILING_RIPORTO`): il motivo
    usciva piu' lungo del tetto, e il racconto lo tagliava di nuovo, perdendo
    la chiusa della citazione."""
    room = max(0, REASON_CAP - len(prefix) - len(suffix))
    return f"{prefix}{truncate_with_marker(detto, room)}{suffix}"


def unfinished_reason(answer) -> str:
    """Il motivo di un turno che NON ha chiamato `conclude`, con dentro cio'
    che il modello aveva risposto al suo posto.

    Vive qui con gli altri motivi di chiusura (D-24, Chiusura): fino al
    13/10/2026 stava in `keeper/exchange.py` come `_senza_conclusione`,
    mentre il suo gemello del silenzio (`bridge_silence_reason`) stava qui.

    Fino al 21/08/2026 questa funzione non esisteva e il motivo era una
    costante: «il turno non ha concluso: non so cosa dirti». Vera, e
    inutilizzabile -- perche' le TRE uscite del ciclo di `claude_runner.chat`
    che portano qui restituiscono tre stringhe DIVERSE (il testo del modello,
    `_MAX_ITERATIONS_NOTICE`, `_TRUNCATION_NOTICE`) e quella stringa era
    l'unica cosa che le distingueva. `interpreta_promise` la scartava: per
    sapere quale delle tre fosse capitata sulla casa vera e' servita
    un'indagine con tre riproduzioni sull'add-on vivo.

    Quando non c'e' proprio niente da riportare si torna alla frase di prima:
    un virgolettato vuoto affermerebbe «ha detto questo», e questo e' niente.
    """
    detto = answer.strip() if isinstance(answer, str) else ""
    if not detto:
        return "il turno non ha concluso: non so cosa dirti."
    return _quoting("il turno non ha concluso. Aveva risposto a parole: «", detto, "»")


def unanswered_reason(answer) -> str:
    """Il motivo di un turno a cui nessun modello ha risposto, con dentro la
    frase del router: e' la diagnosi («credito esaurito», «nessun provider
    utilizzabile»), e senza la pagina direbbe solo che e' andata male."""
    detto = answer.strip() if isinstance(answer, str) else ""
    if not detto:
        return f"{NO_ANSWER_REASON}."
    return _quoting(f"{NO_ANSWER_REASON}: ", detto)
