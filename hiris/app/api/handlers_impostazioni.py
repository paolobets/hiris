"""fetta E5 Task 2 ("il frontend"): le impostazioni della chat tornano ad
avere una superficie.

**Perche' questo file esiste.** I sette campi di `ImpostazioniChat`
(`hiris/app/impostazioni_chat.py`) governano l'unica conversazione che HIRIS
sa avere -- il prompt di sistema, il modello, la forma della risposta, il
budget di ragionamento, il tetto di turni, la restrizione alla casa e il nome.
Fino a questo task si cambiavano **solo scrivendo a mano
`/data/impostazioni_chat.json`**: `ImpostazioniChat.salva()` non aveva nessun
chiamante di produzione (due sole occorrenze in tutto il repo, entrambe in
`tests/test_impostazioni_chat.py`). Per chi installa l'add-on senza aprire una
shell dentro il container, quei sette campi erano di fatto costanti.

**Il contratto e' nuovo, non la superficie di compatibilita' inglese che
c'era.** Il payload usa i nomi italiani dei campi del dataclass (`nome`,
`system_prompt`, `model`, `response_mode`, `thinking_budget`,
`max_chat_turns`, `restrict_to_home`). `GET /api/chatbots`
(`handlers_chatbots.py`) parlava inglese per la card Lovelace e la pagina
chat: questo file non l'ha mai usata, ed e' uscita per intero al Task 10 di
questa fetta, col resto dei suoi ultimi chiamanti in `static/`.

**Cosa si valida, e perche' non di piu'.** Un campo fuori intervallo, di tipo
sbagliato o sconosciuto produce un **400 che dice quale campo e cosa non va**,
mai un 500 e mai un salvataggio a meta': la validazione avviene per intero
PRIMA di toccare il disco, e l'oggetto scritto e' sempre completo (i campi
assenti conservano il valore corrente -- un client che manda meno campi non
azzera gli altri). I due interi hanno come solo limite `>= 0` perche' i limiti
veri stanno gia' a valle e dipendono dal modello:
`claude_runner._thinking_param` disattiva un `thinking_budget` sotto i 1024 o
su un modello non capace e lo clampa contro `max_tokens`; `max_chat_turns` a 0
significa "nessun tetto" (`handlers_chat.py`). Duplicare qui una soglia
numerica che vale solo per un backend sarebbe una dichiarazione falsa al
presente non appena il modello cambia.

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
CAMPI = (
    "nome",
    "system_prompt",
    "model",
    "response_mode",
    "thinking_budget",
    "max_chat_turns",
    "restrict_to_home",
)

# I tre valori che il codice a valle distingue davvero: `prompts.py:315-317`,
# `claude_runner.py:703-705` e `openai_compat_runner.py:523-525/801-803`
# trattano "compact" e "minimal"; qualunque altro valore ricade nel ramo
# neutro, che e' esattamente "auto". Elencarli qui evita che l'utente scriva
# un quarto valore convinto di aver ottenuto qualcosa.
MODI_RISPOSTA = ("auto", "compact", "minimal")

# Il prompt di sistema e' testo libero: l'unico tetto e' quello che impedisce
# a un incollaggio accidentale (un documento intero) di far fallire ogni turno
# di chat contro il limite di contesto del modello, in un punto in cui il
# messaggio d'errore arriverebbe dal provider e non da noi.
MAX_CARATTERI_PROMPT = 20000

# Il nome del modello finisce in `llm_router` e poi nel corpo di una richiesta
# HTTP: caratteri di controllo o spazi non ne fanno parte in nessuno dei
# formati accettati ("auto", "claude-opus-4-7", "openrouter:vendor/modello").
MAX_CARATTERI_MODELLO = 200


class Rifiuto(Exception):
    """Un campo non valido, col nome del campo e il perche' in italiano.

    Esiste per far fallire la validazione INTERA prima di qualunque scrittura:
    il chiamante la cattura e risponde 400, e il file su disco non e' stato
    toccato."""

    def __init__(self, campo: str, motivo: str) -> None:
        super().__init__(motivo)
        self.campo = campo
        self.motivo = motivo


def _tipo(valore) -> str:
    """Il tipo del valore ricevuto, detto in italiano -- mai il valore stesso
    (un prompt di sistema intero dentro un messaggio d'errore sarebbe
    illeggibile in pagina, e finirebbe anche nel log)."""
    return {
        bool: "un booleano", int: "un numero", float: "un numero",
        str: "testo", list: "una lista", dict: "un oggetto",
        type(None): "un valore nullo",
    }.get(type(valore), type(valore).__name__)


def _testo(body: dict, chiave: str, corrente: str) -> str:
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
    if chiave not in body:
        return corrente
    valore = body[chiave]
    if not isinstance(valore, str):
        raise Rifiuto(chiave, f"«{chiave}» deve essere testo, non {_tipo(valore)}.")
    try:
        valore.encode("utf-8")
    except UnicodeEncodeError as exc:
        # Del carattere si dice la POSIZIONE, mai il valore: stessa disciplina
        # di `token_interno.motivo_token_non_valido`, e un prompt di sistema
        # intero dentro un messaggio d'errore sarebbe illeggibile in pagina.
        raise Rifiuto(
            chiave,
            f"«{chiave}» contiene un carattere non rappresentabile in UTF-8 "
            f"(posizione {exc.start}): di solito significa che il testo e' "
            "stato incollato da una sorgente malformata. Ricopialo e riprova.",
        ) from None
    return valore


def _intero_non_negativo(body: dict, chiave: str, corrente: int) -> int:
    if chiave not in body:
        return corrente
    valore = body[chiave]
    # `bool` e' sottoclasse di `int` in Python: senza questo controllo `True`
    # passerebbe per 1 e un errore di tipo del client diventerebbe un
    # salvataggio silenzioso.
    if isinstance(valore, bool) or not isinstance(valore, int):
        raise Rifiuto(chiave, f"«{chiave}» deve essere un numero intero, non {_tipo(valore)}.")
    if valore < 0:
        raise Rifiuto(chiave, f"«{chiave}» non può essere negativo (ricevuto {valore}).")
    return valore


def valida(corrente: ImpostazioniChat, body) -> ImpostazioniChat:
    """Le impostazioni nuove, a partire dalle correnti e dal corpo ricevuto.

    Solleva `Rifiuto` al primo campo che non va, senza aver scritto niente.
    Un campo assente conserva il valore corrente: il PUT e' il salvataggio
    dell'intero oggetto dalla pagina, ma un client che manda meno campi non
    deve distruggere quelli che non nomina."""
    if not isinstance(body, dict):
        raise Rifiuto("", "Il corpo della richiesta deve essere un oggetto JSON.")

    sconosciute = sorted(k for k in body if k not in CAMPI)
    if sconosciute:
        raise Rifiuto(
            sconosciute[0],
            "Campi non riconosciuti: {}. I campi ammessi sono: {}.".format(
                ", ".join(sconosciute), ", ".join(CAMPI)),
        )

    nome = _testo(body, "nome", corrente.nome).strip()
    if not nome:
        raise Rifiuto("nome", "«nome» non può essere vuoto.")

    prompt = _testo(body, "system_prompt", corrente.system_prompt).strip()
    if len(prompt) > MAX_CARATTERI_PROMPT:
        raise Rifiuto(
            "system_prompt",
            f"«system_prompt» supera i {MAX_CARATTERI_PROMPT} caratteri "
            f"(ne ha {len(prompt)}).",
        )
    # Vuoto NON significa "prompt vuoto": significa "rimetti il default nel
    # codice". E' la via di ritorno per chi ha svuotato il campo, o ci ha
    # scritto qualcosa di cui si e' pentito.
    if not prompt:
        prompt = DEFAULT_SYSTEM_PROMPT

    modello = _testo(body, "model", corrente.model).strip() or "auto"
    if len(modello) > MAX_CARATTERI_MODELLO:
        raise Rifiuto(
            "model",
            f"«model» supera i {MAX_CARATTERI_MODELLO} caratteri (ne ha {len(modello)}).",
        )
    if any(ord(c) < 0x20 or ord(c) == 0x7F or c.isspace() for c in modello):
        raise Rifiuto(
            "model",
            "«model» non può contenere spazi o caratteri di controllo: è un "
            "identificatore come «auto», «claude-opus-4-7» oppure "
            "«openrouter:vendor/modello».",
        )

    modo = _testo(body, "response_mode", corrente.response_mode).strip()
    if modo not in MODI_RISPOSTA:
        raise Rifiuto(
            "response_mode",
            "«response_mode» ammette solo {}.".format(", ".join(MODI_RISPOSTA)),
        )

    thinking = _intero_non_negativo(body, "thinking_budget", corrente.thinking_budget)
    turni = _intero_non_negativo(body, "max_chat_turns", corrente.max_chat_turns)

    if "restrict_to_home" in body:
        restrizione = body["restrict_to_home"]
        if not isinstance(restrizione, bool):
            raise Rifiuto(
                "restrict_to_home",
                f"«restrict_to_home» deve essere true o false, non {_tipo(restrizione)}.",
            )
    else:
        restrizione = corrente.restrict_to_home

    return ImpostazioniChat(
        nome=nome,
        system_prompt=prompt,
        model=modello,
        response_mode=modo,
        thinking_budget=thinking,
        max_chat_turns=turni,
        restrict_to_home=restrizione,
    )


def _payload(impostazioni: ImpostazioniChat) -> dict:
    """I sette campi, piu' due cose che la pagina non deve indovinare: i
    valori ammessi per `response_mode` e il prompt di default (per il
    "ripristina"), che vivono nel codice e cambierebbero sotto a una copia
    tenuta nel frontend."""
    return {
        "nome": impostazioni.nome,
        "system_prompt": impostazioni.system_prompt,
        "model": impostazioni.model,
        "response_mode": impostazioni.response_mode,
        "thinking_budget": impostazioni.thinking_budget,
        "max_chat_turns": impostazioni.max_chat_turns,
        "restrict_to_home": impostazioni.restrict_to_home,
        "modi_risposta": list(MODI_RISPOSTA),
        "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
    }


async def handle_get_impostazioni(request: web.Request) -> web.Response:
    """Le impostazioni in vigore ADESSO -- quelle che il prossimo turno di
    chat leggera'. Si prendono da `app["impostazioni_chat"]` e non dal disco:
    e' lo stesso oggetto che usa `handlers_chat.py`, quindi la pagina non puo'
    mostrare qualcosa di diverso da cio' che la chat sta usando."""
    impostazioni = request.app.get("impostazioni_chat") or ImpostazioniChat()
    return web.json_response(_payload(impostazioni))


async def handle_save_impostazioni(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response(
            {"error": "Il corpo della richiesta non è JSON valido.", "campo": ""},
            status=400,
        )

    corrente = request.app.get("impostazioni_chat") or ImpostazioniChat()
    try:
        nuove = valida(corrente, body)
    except Rifiuto as rifiuto:
        # Il rifiuto e' esplicito e dice quale campo: l'alternativa (accettare
        # e ignorare) sarebbe esattamente il salvataggio silenzioso a meta'
        # che questo task esiste per non introdurre.
        logger.info("Impostazioni chat rifiutate: %s", rifiuto.motivo)
        return web.json_response(
            {"error": rifiuto.motivo, "campo": rifiuto.campo}, status=400,
        )

    data_dir = request.app.get("data_dir") or "/data"
    try:
        nuove.salva(data_dir)
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
    request.app["impostazioni_chat"] = nuove
    return web.json_response({"ok": True, **_payload(nuove)})
