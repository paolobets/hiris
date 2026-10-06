"""fetta E5 Task 2 ("il frontend"): le impostazioni della chat tornano ad
avere una superficie.

**Perche' questo file esiste.** I sette campi di `ChatSettings`
(`hiris/app/chat_settings.py`) governano l'unica conversazione che HIRIS
sa avere -- il prompt di sistema, la forma della risposta, il budget di
ragionamento, il tetto di turni, la restrizione alla casa, il nome e (dalla
fetta "Modelli" (2.0), Task 12) i giorni di conservazione. Il modello NON e'
fra loro: si sceglie per provider, nella pagina Modelli (fetta "la catena
diventa l'unica verita'", Task 4 -- il campo `model` che stava qui scavalcava
la catena e annullava il ripiego).
Fino alla fetta E5 Task 2 si cambiavano **solo scrivendo a mano
`/data/impostazioni_chat.json`**: `ChatSettings.save()` non aveva nessun
chiamante di produzione (due sole occorrenze in tutto il repo, entrambe in
`tests/test_chat_settings.py`). Per chi installa l'add-on senza aprire una
shell dentro il container, quei campi erano di fatto costanti.

**Il contratto.** Il payload porta i sette campi del dataclass (`name`,
`system_prompt`, `response_mode`, `thinking_budget`, `max_chat_turns`,
`restrict_to_home`, `retention_days`).

**Cosa si valida, e perche' non di piu'.** Un campo fuori intervallo, di tipo
sbagliato o sconosciuto produce un **400 che dice quale campo e cosa non va**,
mai un 500 e mai un salvataggio a meta': la validazione avviene per intero
PRIMA di toccare il disco, e l'oggetto scritto e' sempre completo (i campi
assenti conservano il valore corrente -- un client che manda meno campi non
azzera gli altri). I tre interi hanno come solo limite `>= 0` perche' i limiti
veri stanno gia' a valle e dipendono dal modello (o, per `retention_days`,
non esistono affatto -- vedi sotto):
`claude_runner._build_thinking_param` disattiva un `thinking_budget` sotto i 1024 o
su un modello non capace e lo clampa contro `max_tokens`; `max_chat_turns` a 0
significa "nessun tetto" (`handlers_chat.py`). Duplicare qui una soglia
numerica che vale solo per un backend sarebbe una dichiarazione falsa al
presente non appena il modello cambia.

**`retention_days` (Task 12).** Arrivato da `history_retention_days`,
l'opzione dell'add-on -- non e' aspetto, non e' una chiave, non e' rete: e'
una decisione sulla conversazione, come le altre sei. Fa DUE lavori: la
potatura notturna (`server.py::_run_retention`) e quanto HIRIS rilegge della
conversazione in corso (`chat_store.load_history`, chiamato da
`handlers_chat.py` con questo stesso valore). `0` non attiva mai nessuno dei
due -- non cancella e non limita niente, il contrario di cio' che ci si
aspetterebbe da una "conservazione" a zero, e per questo la descrizione in
pagina lo dice esplicitamente invece di lasciarlo dedurre. Dalla **versione
B** (3.0.0) `history_retention_days` NON e' piu' un'opzione dell'add-on: il
valore vive solo qui.

**Il caso speciale del prompt di sistema.** E' il campo piu' delicato del
prodotto: arriva verbatim nel prompt di ogni turno, sia sul percorso sincrono
sia sul ponte. Un utente che lo svuota non deve ritrovarsi una chat con prompt
vuoto e non deve reinstallare per tornare indietro: un `system_prompt` vuoto
(o di soli spazi) **ripristina `DEFAULT_SYSTEM_PROMPT`**, cioe' il default nel
codice -- la stessa regola che `ChatSettings.load()` applica gia' a un
file con la chiave vuota. Il default viaggia anche nel GET
(`default_system_prompt`) cosi' che la pagina possa offrire "ripristina" senza
tenerne una copia propria destinata a invecchiare.

**L'aggiornamento a caldo.** Dopo il salvataggio si riassegna
`request.app["chat_settings"]`: senza, il file su disco cambierebbe e la
chat continuerebbe a usare i valori vecchi fino al riavvio dell'add-on -- un
salvataggio riuscito e senza effetto, il difetto n.1 di questo prodotto sotto
altra forma. E' lo stesso hot-update di
`handlers_models.handle_save_models_config` e produce la stessa
`DeprecationWarning` di aiohttp ("Changing state of started or joined
application is deprecated") che quella riga produce gia' oggi in suite:
aiohttp scoraggia la mutazione di `app` dopo l'avvio, ma qui non esiste un
canale alternativo senza cambiare il tipo di `app["chat_settings"]`, letto
per riferimento da `handlers_chat.py`. Dichiarato, non taciuto.
"""
from __future__ import annotations

import logging

from aiohttp import web

from ..chat_settings import DEFAULT_SYSTEM_PROMPT, ChatSettings
from .boundary import error_response, json_object
from .soffitto import restricted_person

# I nomi di HTTP e i nomi del FILE non sono piu' gli stessi, e la differenza e'
# voluta (fetta «la rinomina», lotto dei campi JSON). Il payload e' il confine e
# parla inglese; `impostazioni_chat.json` sul disco resta com'e' -- e' un
# archivio di un utente vero, stessa classe di `models_config.json` e del
# database, e rinominarlo vorrebbe dire scrivere una migrazione del suo dato.
# La traduzione vive dove viveva gia': `ChatSettings.load`/`.save`
# (`chat_settings.py`) mappano `nome`/`giorni_conservazione` del file su
# `name`/`retention_days` del codice, e questo modulo mappa il codice su HTTP.
# Due salti, nessuno dei due nuovo: prima coincidevano per caso.
logger = logging.getLogger(__name__)

# I sette campi, nell'ordine in cui la pagina li mostra. E' anche l'elenco
# delle chiavi ammesse nel corpo del PUT: tutto cio' che non e' qui dentro e'
# un errore parlante, non un silenzio (una chiave scritta male -- `modello`
# invece di `model` -- verrebbe altrimenti accettata e ignorata, e l'utente
# leggerebbe "salvato" senza che nulla sia cambiato).
FIELDS = (
    "name",
    "system_prompt",
    "response_mode",
    "thinking_budget",
    "max_chat_turns",
    "restrict_to_home",
    "retention_days",
)

# I tre valori che il codice a valle distingue davvero: `agent/prompts.py`,
# `claude_runner.py` e `backends/openai_compat_runner.py`
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
    -- che il `json.dump` di `ChatSettings.save()` rifiuta con
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
        # Del carattere si dice la POSIZIONE, mai il valore: un prompt di
        # sistema intero dentro un messaggio d'errore sarebbe illeggibile in
        # pagina.
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


def validate(current: ChatSettings, body) -> ChatSettings:
    """Le impostazioni nuove, a partire dalle correnti e dal corpo ricevuto.

    Solleva `Rejection` al primo campo che non va, senza aver scritto niente.
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

    name = _text(body, "name", current.name).strip()
    if not name:
        raise Rejection("name", "«name» non può essere vuoto.")

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

    # Stesso `_non_negative_integer` dei due campi sopra: `0` e' un valore
    # AMMESSO (Task 12 -- "non cancella e non limita mai niente"), non un
    # errore. Nessun tetto superiore: come per
    # `thinking_budget`/`max_chat_turns`, il limite vero non esiste o non e'
    # di competenza di questa validazione.
    retention_days = _non_negative_integer(
        body, "retention_days", current.retention_days)

    return ChatSettings(
        name=name,
        system_prompt=prompt,
        response_mode=mode,
        thinking_budget=thinking,
        max_chat_turns=turns,
        restrict_to_home=restriction,
        retention_days=retention_days,
    )


def _payload(settings: ChatSettings) -> dict:
    """I sette campi, piu' due cose che la pagina non deve indovinare: i
    valori ammessi per `response_mode` e il prompt di default (per il
    "ripristina"), che vivono nel codice e cambierebbero sotto a una copia
    tenuta nel frontend."""
    return {
        "name": settings.name,
        "system_prompt": settings.system_prompt,
        "response_mode": settings.response_mode,
        "thinking_budget": settings.thinking_budget,
        "max_chat_turns": settings.max_chat_turns,
        "restrict_to_home": settings.restrict_to_home,
        "retention_days": settings.retention_days,
        "response_modes": list(RESPONSE_MODES),
        "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
    }


#: I campi che la pagina della chat legge (`chat/agents.js::loadSettings`):
#: tutto cio' che riceve chi non amministra (spec 2026-09-27, ruling R-2.24).
#: Il prompt di sistema, quello di difetto, la conservazione e il resto sono
#: della pagina Impostazioni, che a lei e' chiusa. Scritto a mano perche' e'
#: una decisione; che coincida con cio' che la chat legge lo prova
#: `test_la_riduzione_e_cio_che_la_CHAT_legge`.
CHAT_PAGE_FIELDS = ("name", "max_chat_turns")


async def handle_get_settings(request: web.Request) -> web.Response:
    """Le impostazioni in vigore ADESSO -- quelle che il prossimo turno di
    chat leggera'. Si prendono da `app["chat_settings"]` e non dal disco:
    e' lo stesso oggetto che usa `handlers_chat.py`, quindi la pagina non puo'
    mostrare qualcosa di diverso da cio' che la chat sta usando."""
    settings = request.app.get("chat_settings") or ChatSettings()
    payload = _payload(settings)
    if restricted_person(request):
        payload = {field: payload[field] for field in CHAT_PAGE_FIELDS}
    return web.json_response(payload)


async def handle_save_settings(request: web.Request) -> web.Response:
    body = await json_object(request, field="")

    current = request.app.get("chat_settings") or ChatSettings()
    try:
        updated = validate(current, body)
    except Rejection as rejection:
        # Il rifiuto e' esplicito e dice quale campo: l'alternativa (accettare
        # e ignorare) sarebbe esattamente il salvataggio silenzioso a meta'
        # che questo task esiste per non introdurre.
        logger.info("Impostazioni chat rifiutate: %s", rejection.reason)
        return error_response(400, rejection.reason, field=rejection.field)

    data_dir = request.app.get("data_dir") or "/data"
    try:
        updated.save(data_dir)
    except OSError as exc:
        # Mai un "salvato" davanti a un disco che non ha accettato niente, e
        # mai un 500 muto: si dice cosa e' successo, e le impostazioni in
        # memoria restano quelle di prima (nessun hot-update qui sotto).
        logger.error(
            "Impostazioni chat: salvataggio in %s fallito (%s: %s). "
            "Le impostazioni in memoria restano quelle di prima.",
            data_dir, type(exc).__name__, exc,
        )
        return error_response(500, "Non è stato possibile scrivere le impostazioni su disco. "
                                   "Controlla il log dell’add-on.", field="")

    # Hot-update: vedi la docstring in cima al file. Senza questa riga il
    # salvataggio riesce e la chat continua a usare i valori vecchi fino al
    # riavvio.
    request.app["chat_settings"] = updated
    return web.json_response({"ok": True, **_payload(updated)})
