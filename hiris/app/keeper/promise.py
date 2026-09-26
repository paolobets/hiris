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

from ..chat_thread import ChatThread
from ..proxy._sanitize import truncate_with_marker

VERB = ("fai", "chiedi")
STATES_CONCLUSI = ("mantenuta", "saltata", "disdetta", "fallita")
# L'insieme «in sospeso» -- la sua UNICA casa (review finale, rilievo ②).
# Prima viveva scritto a mano in due punti di `store.py` (due `WHERE
# stato IN (...)` SQL letterali) e una terza volta in
# `static/config/agenda-route.js::STATI_SOSPESO`, senza niente che li
# legasse: uno stato non conclusivo aggiunto qui un domani sarebbe sparito
# in silenzio dalla sezione azionabile della pagina, senza che niente
# fallisse -- precisamente il rischio che la spec §12 nomina per la fetta
# successiva (i lavori di sistema, «la specie e' un campo, non un `if`»).
# `tests/js/agenda-route-vocabulary.test.mjs` lega questo insieme al
# JavaScript: e' quello che rende la divergenza NON silenziosa
# (`scripts/doppioni.py`, `_costanti_gia_legate`).
STATES_SOSPESO = ("in_attesa", "in_corso")

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
# `STATES_SOSPESO`. Il complemento e' comodo e non ha opinioni -- prende
# dentro tutto cio' che non e' in sospeso, `disdetta` compresa. Percio' qui
# c'e' un elenco esplicito: e' l'unico modo perche' la domanda «questo e'
# una notizia?» abbia una risposta scritta invece che dedotta.
STATES_ESITO = ("mantenuta", "saltata", "fallita")

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
CEILING_IN_SOSPESO = 50
# **E il totale resta limitato** (ruling 2.6 della revisione di sicurezza): un
# tetto solo per filo lascerebbe il totale crescere col numero dei fili, e i
# fili li moltiplica chiunque arrivi da un ingresso diverso. 200 tiene il disco
# della scheda SD e il battito dell'orologio (che legge le scadute ogni 15
# secondi) nell'ordine di grandezza di oggi: quattro fili pieni, non di piu'.
HOUSE_CEILING_IN_SOSPESO = 200
# Quanto si conserva una promessa CONCLUSA (spec §8.1). Un registro che cresce
# per sempre su una scheda SD e' un guasto rimandato. E' una politica di
# QUESTO strato (lo Schedulatore), indipendente da quella della cronaca delle
# esecuzioni (`action/journal.py::EXECUTIONS_RETENTION_S`, nello strato
# sotto): oggi vale lo stesso numero, 90 giorni, ma sono due fatti distinti --
# per quanto si conserva una PROMESSA conclusa, per quanto si conserva
# un'ESECUZIONE -- che possono divergere in futuro senza che l'uno debba
# inseguire l'altro.
CONSERVAZIONE_S = 90 * 86400

_CHIAVI = (
    "id", "specie", "frase", "quando_ts", "quando_detto", "fuso", "chiamata",
    "domanda", "istantanea", "stato", "motivo", "esecuzione_id",
    "testo", "avvisare", "nata_ts", "risvegliata_ts", "esito_letto_ts",
    # `entities_at_birth`: quante entita' toccava il bersaglio alla nascita
    # (reperto B-6, 22/09/2026). In inglese perche' le colonne nuove lo sono.
    "entities_at_birth",
    # Il filo di chi l'ha chiesta (spec 2026-09-26 §2), come `ChatThread` --
    # la stessa forma della coda e delle costruzioni. Serve DENTRO il
    # processo (l'orologio, la consegna dell'esito); le rotte e lo strumento
    # lo tolgono con `chat_thread.without_thread` prima di rispondere.
    # `recapito` e' uscito da qui: la colonna resta per le righe vecchie, ma
    # nessuno la legge piu' per recapitare (vedi lo schema in `store.py`).
    "thread",
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
# 3.7): stesso numero di `exchange._CEILING_RIPORTO`, per la stessa ragione --
# una riga da leggere, non un allegato.
REASON_CAP = 300
# La frase originale citata nel messaggio d'esito: e' di chi ha chiesto e
# torna a lui, ma resta un campo limitato come gli altri.
PHRASE_CAP = 200
# Al piu' tre servizi per promessa, a ogni risveglio (ruling 3.4). Una
# persona vera ha un telefono e forse un tablet; un recapito che ne
# risolvesse dieci farebbe di un esito dieci notifiche. Il limite
# accettato: nessun freno GLOBALE sulle push in questa fetta -- il numero
# delle promesse e' gia' limitato (`CEILING_IN_SOSPESO`,
# `HOUSE_CEILING_IN_SOSPESO`), e questo tetto limita il resto.
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
        "istantanea": _load(row["istantanea_json"]),
        "stato": row["stato"],
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
        "thread": (ChatThread(row["subject_key"], row["entry_point"])
                   if _column(row, "subject_key") else None),
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
