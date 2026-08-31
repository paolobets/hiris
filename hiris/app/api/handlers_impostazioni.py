"""fetta E5 Task 2 ("il frontend"): le impostazioni della chat tornano ad
avere una superficie.

**Perche' questo file esiste.** I sette campi di `ImpostazioniChat`
(`hiris/app/impostazioni_chat.py`) governano l'unica conversazione che HIRIS
sa avere -- il prompt di sistema, la forma della risposta, il budget di
ragionamento, il tetto di turni, la restrizione alla casa, il nome e (dalla
fetta "Modelli" (2.0), Task 12) i giorni di conservazione. Il modello NON e'
fra loro: si sceglie per provider, nella pagina Modelli (fetta "la catena
diventa l'unica verita'", Task 4 -- il campo `model` che stava qui scavalcava
la catena e annullava il ripiego).
Fino alla fetta E5 Task 2 si cambiavano **solo scrivendo a mano
`/data/impostazioni_chat.json`**: `ImpostazioniChat.salva()` non aveva nessun
chiamante di produzione (due sole occorrenze in tutto il repo, entrambe in
`tests/test_impostazioni_chat.py`). Per chi installa l'add-on senza aprire una
shell dentro il container, quei campi erano di fatto costanti.

**Il contratto e' nuovo, non la superficie di compatibilita' inglese che
c'era.** Il payload usa i nomi italiani dei campi del dataclass (`nome`,
`system_prompt`, `response_mode`, `thinking_budget`, `max_chat_turns`,
`restrict_to_home`, `giorni_conservazione`). `GET /api/chatbots`
(`handlers_chatbots.py`) parlava inglese per la card Lovelace e la pagina
chat: questo file non l'ha mai usata, ed e' uscita per intero al Task 10 di
questa fetta, col resto dei suoi ultimi chiamanti in `static/`.

**Cosa si valida, e perche' non di piu'.** Un campo fuori intervallo, di tipo
sbagliato o sconosciuto produce un **400 che dice quale campo e cosa non va**,
mai un 500 e mai un salvataggio a meta': la validazione avviene per intero
PRIMA di toccare il disco, e l'oggetto scritto e' sempre completo (i campi
assenti conservano il valore corrente -- un client che manda meno campi non
azzera gli altri). I tre interi hanno come solo limite `>= 0` perche' i limiti
veri stanno gia' a valle e dipendono dal modello (o, per `giorni_conservazione`,
non esistono affatto -- vedi sotto):
`claude_runner._thinking_param` disattiva un `thinking_budget` sotto i 1024 o
su un modello non capace e lo clampa contro `max_tokens`; `max_chat_turns` a 0
significa "nessun tetto" (`handlers_chat.py`). Duplicare qui una soglia
numerica che vale solo per un backend sarebbe una dichiarazione falsa al
presente non appena il modello cambia.

**`giorni_conservazione` (Task 12).** Arrivato da `history_retention_days`,
l'opzione dell'add-on -- non e' aspetto, non e' una chiave, non e' rete: e'
una decisione sulla conversazione, come le altre sei. Fa DUE lavori: la
potatura notturna (`server.py::_run_retention`) e quanto HIRIS rilegge della
conversazione in corso (`chat_store.load_context`, chiamato da
`handlers_chat.py` con questo stesso valore). `0` non attiva mai nessuno dei
due -- non cancella e non limita niente, il contrario di cio' che ci si
aspetterebbe da una "conservazione" a zero, e per questo la descrizione in
pagina lo dice esplicitamente invece di lasciarlo dedurre. Dalla **versione
B** (3.0.0) `history_retention_days` NON e' piu' un'opzione dell'add-on: il
valore vive solo qui, e ci e' arrivato con la versione A -- `carica()` lo
copiava dall'ambiente quando l'archivio non aveva ancora la chiave, e l'avvio
lo SCRIVEVA su disco (`il_file_non_porta_i_giorni`), che e' la meta' senza cui
la copia non sarebbe sopravvissuta a questa versione.

**Il caso speciale del prompt di sistema.** E' il campo piu' delicato del
prodotto: arriva verbatim nel prompt di ogni turno, sia sul percorso sincrono
sia sul ponte. Un utente che lo svuota non deve ritrovarsi una chat con prompt
vuoto e non deve reinstallare per tornare indietro: un `system_prompt` vuoto
(o di soli spazi) **ripristina `DEFAULT_SYSTEM_PROMPT`**, cioe' il default nel
codice -- la stessa regola che `ImpostazioniChat.carica()` applica gia' a un
file con la chiave vuota. Il default viaggia anche nel GET
(`default_system_prompt`) cosi' che la pagina possa offrire "ripristina" senza
tenerne una copia propria destinata a invecchiare.

**L'aggiornamento a caldo.** Dopo il salvataggio si riassegna
`request.app["impostazioni_chat"]`: senza, il file su disco cambierebbe e la
chat continuerebbe a usare i valori vecchi fino al riavvio dell'add-on -- un
salvataggio riuscito e senza effetto, il difetto n.1 di questo prodotto sotto
altra forma. E' lo stesso hot-update di
`handlers_models.handle_save_models_config` e produce la stessa
`DeprecationWarning` di aiohttp ("Changing state of started or joined
application is deprecated") che quella riga produce gia' oggi in suite:
aiohttp scoraggia la mutazione di `app` dopo l'avvio, ma qui non esiste un
canale alternativo senza cambiare il tipo di `app["impostazioni_chat"]`, letto
per riferimento da `handlers_chat.py` (`handlers_chatbots.py` la leggeva
anche lui, finche' non e' uscito al Task 10 della E5). Dichiarato,
non taciuto.
"""
from __future__ import annotations

import logging

from aiohttp import web

from ..impostazioni_chat import DEFAULT_SYSTEM_PROMPT, ImpostazioniChat

logger = logging.getLogger(__name__)

# I sette campi, nell'ordine in cui la pagina li mostra. E' anche l'elenco
# delle chiavi ammesse nel corpo del PUT: tutto cio' che non e' qui dentro e'
# un errore parlante, non un silenzio (una chiave scritta male -- `modello`
# invece di `model` -- verrebbe altrimenti accettata e ignorata, e l'utente
# leggerebbe "salvato" senza che nulla sia cambiato).
FIELDS = (
    "nome",
    "system_prompt",
    "response_mode",
    "thinking_budget",
    "max_chat_turns",
    "restrict_to_home",
    "giorni_conservazione",
)

# I tre valori che il codice a valle distingue davvero: `prompts.py:315-317`,
# `claude_runner.py:703-705` e `openai_compat_runner.py:523-525/801-803`
# trattano "compact" e "minimal"; qualunque altro valore ricade nel ramo
# neutro, che e' esattamente "auto". Elencarli qui evita che l'utente scriva
# un quarto valore convinto di aver ottenuto qualcosa.
RESPONSE_MODES = ("auto", "compact", "minimal")

# Il prompt di sistema e' testo libero: l'unico tetto e' quello che impedisce
# a un incollaggio accidentale (un documento intero) di far fallire ogni turno
# di chat contro il limite di contesto del modello, in un punto in cui il
# messaggio d'errore arriverebbe dal provider e non da noi.
MAX_PROMPT_CHARS = 20000


class Rejection(Exception):
    """Un campo non valido, col nome del campo e il perche' in italiano.

    Esiste per far fallire la validazione INTERA prima di qualunque scrittura:
    il chiamante la cattura e risponde 400, e il file su disco non e' stato
    toccato."""

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(reason)
        self.field = field
        self.reason = reason


def _type(value) -> str:
    """Il tipo del valore ricevuto, detto in italiano -- mai il valore stesso
    (un prompt di sistema intero dentro un messaggio d'errore sarebbe
    illeggibile in pagina, e finirebbe anche nel log)."""
    return {
        bool: "un booleano", int: "un numero", float: "un numero",
        str: "testo", list: "una lista", dict: "un oggetto",
        type(None): "un valore nullo",
    }.get(type(value), type(value).__name__)


def _text(body: dict, key: str, current: str) -> str:
    """Il valore di un campo di testo, verificato ANCHE come scrivibile.

    Fix round 1, I-1. `isinstance(valore, str)` verifica il TIPO, non la
    CODIFICABILITA': una stringa Python puo' contenere un surrogato spaiato
    (un U+D800 isolato) -- JSON valido in ingresso, `str` a tutti gli effetti
    -- che il `json.dump` di `ImpostazioniChat.salva()` rifiuta con
    `UnicodeEncodeError`. Quell'eccezione NON e' un `OSError`, quindi non
    veniva catturata dal chiamante e usciva come 500 col traceback: era
    l'unico buco nella promessa «ogni corpo sbagliato produce un 400 che dice
    quale campo». E non e' teorico -- e' cio' che si prende un tester che
    incolla nel prompt di sistema del testo copiato da una sorgente
    malformata.

    Si controlla QUI, dentro la validazione, invece di allargare l'`except` a
    valle: il rifiuto deve nominare il campo come tutti gli altri, e la regola
    «si valida tutto prima di toccare il disco» resta vera per costruzione,
    non per fortuna.
    """
    if key not in body:
        return current
    value = body[key]
    if not isinstance(value, str):
        raise Rejection(key, f"«{key}» deve essere testo, non {_type(value)}.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        # Del carattere si dice la POSIZIONE, mai il valore: stessa disciplina
        # di `token_interno.motivo_token_non_valido`, e un prompt di sistema
        # intero dentro un messaggio d'errore sarebbe illeggibile in pagina.
        raise Rejection(
            key,
            f"«{key}» contiene un carattere non rappresentabile in UTF-8 "
            f"(posizione {exc.start}): di solito significa che il testo e' "
            "stato incollato da una sorgente malformata. Ricopialo e riprova.",
        ) from None
    return value


def _non_negative_integer(body: dict, key: str, current: int) -> int:
    if key not in body:
        return current
    value = body[key]
    # `bool` e' sottoclasse di `int` in Python: senza questo controllo `True`
    # passerebbe per 1 e un errore di tipo del client diventerebbe un
    # salvataggio silenzioso.
    if isinstance(value, bool) or not isinstance(value, int):
        raise Rejection(key, f"«{key}» deve essere un numero intero, non {_type(value)}.")
    if value < 0:
        raise Rejection(key, f"«{key}» non può essere negativo (ricevuto {value}).")
    return value


def validate(current: ImpostazioniChat, body) -> ImpostazioniChat:
    """Le impostazioni nuove, a partire dalle correnti e dal corpo ricevuto.

    Solleva `Rifiuto` al primo campo che non va, senza aver scritto niente.
    Un campo assente conserva il valore corrente: il PUT e' il salvataggio
    dell'intero oggetto dalla pagina, ma un client che manda meno campi non
    deve distruggere quelli che non nomina."""
    if not isinstance(body, dict):
        raise Rejection("", "Il corpo della richiesta deve essere un oggetto JSON.")

    unknown_fields = sorted(k for k in body if k not in FIELDS)
    if unknown_fields:
        raise Rejection(
            unknown_fields[0],
            "Campi non riconosciuti: {}. I campi ammessi sono: {}.".format(
                ", ".join(unknown_fields), ", ".join(FIELDS)),
        )

    name = _text(body, "nome", current.nome).strip()
    if not name:
        raise Rejection("nome", "«nome» non può essere vuoto.")

    prompt = _text(body, "system_prompt", current.system_prompt).strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise Rejection(
            "system_prompt",
            f"«system_prompt» supera i {MAX_PROMPT_CHARS} caratteri "
            f"(ne ha {len(prompt)}).",
        )
    # Vuoto NON significa "prompt vuoto": significa "rimetti il default nel
    # codice". E' la via di ritorno per chi ha svuotato il campo, o ci ha
    # scritto qualcosa di cui si e' pentito.
    if not prompt:
        prompt = DEFAULT_SYSTEM_PROMPT

    mode = _text(body, "response_mode", current.response_mode).strip()
    if mode not in RESPONSE_MODES:
        raise Rejection(
            "response_mode",
            "«response_mode» ammette solo {}.".format(", ".join(RESPONSE_MODES)),
        )

    thinking = _non_negative_integer(body, "thinking_budget", current.thinking_budget)
    turns = _non_negative_integer(body, "max_chat_turns", current.max_chat_turns)

    if "restrict_to_home" in body:
        restriction = body["restrict_to_home"]
        if not isinstance(restriction, bool):
            raise Rejection(
                "restrict_to_home",
                f"«restrict_to_home» deve essere true o false, non {_type(restriction)}.",
            )
    else:
        restriction = current.restrict_to_home

    # Stesso `_intero_non_negativo` dei due campi sopra: `0` e' un valore
    # AMMESSO (Task 12 -- "non cancella e non limita mai niente"), non un
    # errore. Nessun tetto superiore: `config.yaml` ne porta uno
    # (`int(0,3650)`) solo perche' e' l'opzione dell'add-on -- qui, come per
    # `thinking_budget`/`max_chat_turns`, il limite vero non esiste o non e'
    # di competenza di questa validazione.
    giorni_conservazione = _non_negative_integer(
        body, "giorni_conservazione", current.giorni_conservazione)

    return ImpostazioniChat(
        nome=name,
        system_prompt=prompt,
        response_mode=mode,
        thinking_budget=thinking,
        max_chat_turns=turns,
        restrict_to_home=restriction,
        giorni_conservazione=giorni_conservazione,
    )


def _payload(settings: ImpostazioniChat) -> dict:
    """I sette campi, piu' due cose che la pagina non deve indovinare: i
    valori ammessi per `response_mode` e il prompt di default (per il
    "ripristina"), che vivono nel codice e cambierebbero sotto a una copia
    tenuta nel frontend."""
    return {
        "nome": settings.nome,
        "system_prompt": settings.system_prompt,
        "response_mode": settings.response_mode,
        "thinking_budget": settings.thinking_budget,
        "max_chat_turns": settings.max_chat_turns,
        "restrict_to_home": settings.restrict_to_home,
        "giorni_conservazione": settings.giorni_conservazione,
        "modi_risposta": list(RESPONSE_MODES),
        "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
    }


async def handle_get_settings(request: web.Request) -> web.Response:
    """Le impostazioni in vigore ADESSO -- quelle che il prossimo turno di
    chat leggera'. Si prendono da `app["impostazioni_chat"]` e non dal disco:
    e' lo stesso oggetto che usa `handlers_chat.py`, quindi la pagina non puo'
    mostrare qualcosa di diverso da cio' che la chat sta usando."""
    settings = request.app.get("impostazioni_chat") or ImpostazioniChat()
    return web.json_response(_payload(settings))


async def handle_save_settings(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response(
            {"error": "Il corpo della richiesta non è JSON valido.", "campo": ""},
            status=400,
        )

    current = request.app.get("impostazioni_chat") or ImpostazioniChat()
    try:
        updated = validate(current, body)
    except Rejection as rejection:
        # Il rifiuto e' esplicito e dice quale campo: l'alternativa (accettare
        # e ignorare) sarebbe esattamente il salvataggio silenzioso a meta'
        # che questo task esiste per non introdurre.
        logger.info("Impostazioni chat rifiutate: %s", rejection.reason)
        return web.json_response(
            {"error": rejection.reason, "campo": rejection.field}, status=400,
        )

    data_dir = request.app.get("data_dir") or "/data"
    try:
        updated.salva(data_dir)
    except OSError as exc:
        # Mai un "salvato" davanti a un disco che non ha accettato niente, e
        # mai un 500 muto: si dice cosa e' successo, e le impostazioni in
        # memoria restano quelle di prima (nessun hot-update qui sotto).
        logger.error(
            "Impostazioni chat: salvataggio in %s fallito (%s: %s). "
            "Le impostazioni in memoria restano quelle di prima.",
            data_dir, type(exc).__name__, exc,
        )
        return web.json_response(
            {"error": "Non è stato possibile scrivere le impostazioni su disco. "
                      "Controlla il log dell'add-on.", "campo": ""},
            status=500,
        )

    # Hot-update: vedi la docstring in cima al file. Senza questa riga il
    # salvataggio riesce e la chat continua a usare i valori vecchi fino al
    # riavvio.
    request.app["impostazioni_chat"] = updated
    return web.json_response({"ok": True, **_payload(updated)})
