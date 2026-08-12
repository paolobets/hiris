import json
import logging
import os
import time

from aiohttp import web

from ..casa.strumenti import STRUMENTI_CONOSCENZA, DispatcherStrumenti
from ..chat_store import (
    load_history, append_messages, get_past_summaries, count_user_turns,
    _is_toxic_assistant,
)
from ..agent.runner import modello_cli
from ..claude_runner import CHAT_MAX_TOKENS, RunnerBackendError, resolve_model
from .handlers_casa import costruisci_nucleo

logger = logging.getLogger(__name__)

# Trim history by estimated token count (len/4) rather than message count.
# Always keep an even number of messages (user+assistant pairs) to preserve
# conversation structure. Full history is still persisted and counted.
_MAX_HISTORY_TOKENS = 6000


def _trim_history(history: list[dict], max_tokens: int = _MAX_HISTORY_TOKENS) -> list[dict]:
    """Keep the most recent messages within an estimated token budget, always
    starting on a user turn (the Claude API rejects a session/history that
    opens with an assistant turn). Shared by the sync path (as
    ``context_history`` sent to the runner) and the async subscription path
    (as the ``history`` field of the enqueued job context)."""
    trimmed: list[dict] = []
    estimated_tokens = 0
    for msg in reversed(history):
        estimated_tokens += len(msg.get("content", "")) // 4 + 4
        if estimated_tokens > max_tokens:
            break
        trimmed.insert(0, msg)
    if trimmed and trimmed[0].get("role") == "assistant":
        trimmed = trimmed[1:]
    return trimmed


def costruisci_dispatcher_strumenti(app) -> DispatcherStrumenti:
    """L'UNICO punto del prodotto in cui `DispatcherStrumenti` viene costruito.

    I cinque strumenti della chat (`casa/strumenti.py`) -- non il catalogo di
    trentaquattro di ALL_TOOL_DEFS: quattro conoscono la casa e il quinto,
    `esegui`, la comanda passando per la porta unica (vedi il docstring di quel
    modulo). Il dispatcher si costruisce dagli
    stessi oggetti dell'app che alimentano `costruisci_nucleo()`
    (`archivio_casa`, `archivio_memoria`, `entity_cache`), piu' `porta_azione`
    -- lo stesso specchio dello stato vivo, non uno ricalcolato a mano -- ed e'
    SEMPRE costruibile, anche quando archivi e porta sono assenti: i suoi
    gestori non sollevano mai, dichiarano un `errore` per strumento invece (vedi
    `DispatcherStrumenti.dispatch`).

    **Perche' e' una funzione e non tre righe ripetute.** Dalla fetta «il ponte
    riceve gli strumenti» (parita' B, Task 1) i costruttori sarebbero stati DUE:
    il turno sincrono qui e la rotta `POST /api/mcp` (`handlers_mcp.py`), che
    porta gli stessi strumenti al ponte via abbonamento. Due costruzioni
    che possono divergere sono esattamente il difetto da cui e' nata la fetta E2
    (tre cataloghi della stessa cosa): qui ce n'e' una sola, e un
    grep del nome della classe seguito da parentesi su `hiris/app/` lo dimostra
    (e `tests/test_rotta_mcp.py` lo pinna). E' lo stesso
    principio gia' applicato al nucleo con `costruisci_nucleo`
    (`handlers_casa.py`: «la STESSA composizione, non due che potrebbero
    divergere»).

    Passarlo sempre (mai `None`) al runner tiene chiusa anche un'altra trappola:
    senza un `dispatcher` per-chiamata i runner degradano OGNI tool a un errore
    "non disponibile" (vedi il ramo `else` del dispatch loop in
    claude_runner.py/openai_compat_runner.py) -- passarlo sempre e' quello che
    tiene la chat viva.
    """
    return DispatcherStrumenti(
        app.get("archivio_casa"),
        app.get("archivio_memoria"),
        cache=app.get("entity_cache"),
        porta=app.get("porta_azione"),
    )


def _build_system_prompt(impostazioni) -> str:
    """Il prompt statico della chat, condiviso dal ramo sincrono e da quello
    in abbonamento (async job context).

    fetta E4 Task 4 ("un bot solo"): prima componeva `strategic_context` +
    `system_prompt` di un `Chatbot` -- due campi pensati per una molteplicita'
    di persone che non esiste piu'. `ImpostazioniChat` ha un solo campo
    (`system_prompt`): niente piu' da comporre. `impostazioni` non e' mai
    `None` (vedi `ImpostazioniChat.carica`, che non lo restituisce mai) --
    il parametro resta accettabile a `None` solo per i test che passano un
    oggetto costruito a mano."""
    if impostazioni and impostazioni.system_prompt:
        return impostazioni.system_prompt.strip()
    return ""


def componi_contesto_chat(app, data_dir: str) -> str:
    """Il contesto della chat -- nucleo piu' sessioni precedenti -- in
    un'unica stringa.

    Estratta dal corpo di `handle_chat` (fetta "il ponte riceve il nucleo",
    parita' A, Task 1): prima questo blocco viveva SOLO nel ramo sincrono.
    Estratto qui, invariato, perche' il Task 2 deve mettere la STESSA
    stringa nel job del ponte (chat via abbonamento) -- se la ricopiasse, i
    due percorsi avrebbero due composizioni destinate a divergere, la
    "funzione doppia" vietata da CLAUDE.md:70-72. Prende `app` (non
    `request`), stessa ragione di `costruisci_nucleo` in handlers_casa.py:
    nessun motivo di legarla a una request in corso.
    """
    # Inject closed-session summaries so Claude remembers previous conversations.
    # Le sessioni precedenti restano una fonte A PARTE dal nucleo (Task 3):
    # sono cronologia di conversazioni chiuse, non conoscenza sulla casa --
    # il nucleo non le contiene e non deve contenerle.
    past = get_past_summaries(data_dir)
    past_str = ""
    if past:
        lines = ["Sessioni precedenti (memoria):"]
        for s in past:
            dt = s["started_at"][:10]
            lines.append(f"[{dt}] {s['summary']}")
        past_str = "\n".join(lines)

    # Task 3 ("il contesto della chat viene dal nucleo"): una fonte sola.
    # Prima qui c'erano quattro chiamate indipendenti -- KnowledgeStore.
    # declared() per i dichiarati, KnowledgeStore.search() per il RAG,
    # SemanticContextMap.get_context() per "cosa c'e' in giro", e le sessioni
    # precedenti -- e nessuna delle prime tre vedeva mai il ritratto: e' la
    # sovrapposizione n.1 della mappa del prodotto, vista da dentro (due
    # intelligenze nella stessa casa che ne vedono due diverse -- vedi
    # docs/design/2026-08-05-la-conoscenza-di-hiris.md, §7).
    # `costruisci_nucleo()` (condivisa con GET /api/nucleo,
    # handlers_casa.py -- stessa composizione, non due che potrebbero
    # divergere) contiene gia' i dichiarati (come "cio' che le persone hanno
    # detto"), la casa, cosa e' notevole adesso, e cosa la casa fa da sola --
    # ed e' lo stesso testo che vedranno il Brain e gli agenti quando
    # torneranno (vedi il brief). All'epoca del Task 3 il blocco RAG e
    # `KnowledgeStore.declared()` non erano stati cancellati: smettevano solo
    # di essere chiamati da QUI. Dalla fetta "esce il documentale" sono
    # cancellati davvero, insieme all'intero `KnowledgeStore` -- da allora non
    # avevano ripreso nessun chiamante di produzione, e l'archivio che
    # leggevano non aveva piu' nessuno che lo riaprisse. SemanticContextMap
    # era uscita anche prima (fetta E3 Task 2, 2.0): il suo unico altro
    # chiamante era il context-preview dell'editor Chatbot, uscito con lei.
    #
    # Se il nucleo non si compone (nessun archivio della casa, anagrafe mai
    # letta) `componi()` non tace: lo dichiara nel testo stesso ("Nessun
    # piano registrato.", "Stato non letto ... non e' lo stesso di 'niente
    # di notevole'", una voce in "Cio' che HIRIS ignora") -- lo stesso
    # principio gia' verificato per `handle_get_nucleo`
    # (test_api_nucleo_senza_archivi_non_afferma_di_sapere). Un silenzio non
    # dichiarato e' indistinguibile da un'assenza di problemi: qui non puo'
    # scattare, perche' il testo che il modello legge lo dice da solo.
    # Fix E1-①: `costruisci_nucleo()` non e' protetta -- apre `archivio_casa`
    # e `archivio_memoria` (SQLite) e puo' sollevare (file corrotto, o in
    # lock dopo un riavvio sporco: sqlite3.DatabaseError/OperationalError).
    # Il codice pre-fetta avvolgeva OGNI fonte in un try/except con questo
    # stesso commento: "un fallimento qui non deve mai impedire alla chat di
    # rispondere" (vedi git blame -- il blocco RAG e i dichiarati, qualche
    # riga sopra qui in cronologia). Diventare una fonte sola ha fatto
    # sparire quel commento insieme al codice che avvolgeva, e la regola con
    # lui: senza questo try/except un `memoria.db` corrotto o un `casa.db`
    # in lock fa rispondere 500 a OGNI `POST /api/chat`, dove prima -- coi
    # quattro try/except separati -- la chat rispondeva semplicemente SENZA
    # quella fonte. Il fallback qui sotto non e' una stringa vuota (che
    # `if nucleo_testo:` scarterebbe zittendo la chat sul contesto, e che il
    # modello leggerebbe come "casa vuota" invece che "guasto"): e' la
    # stessa distinzione che il nucleo gia' fa per i registri caduti
    # (`non_disponibili`) e per lo stato inaffidabile (`stato_non_letto`),
    # qui applicata al caso in cui comporlo del tutto solleva invece di
    # dichiarare.
    try:
        nucleo_testo, _nucleo_riepilogo = costruisci_nucleo(app)
    except Exception as exc:
        logger.warning("composizione del nucleo fallita, la chat risponde senza: %s", exc)
        nucleo_testo = (
            "## Cio' che HIRIS ignora\n"
            "- il nucleo non si e' potuto comporre: un archivio della casa o "
            "della memoria e' guasto o non leggibile in questo momento. "
            "Nessuna delle sezioni che normalmente lo precedono (la casa, "
            "cio' che e' notevole adesso, cio' che la casa fa da sola, cio' "
            "che le persone hanno detto) e' disponibile in questo turno. "
            "Non e' una casa vuota -- e' un guasto: dillo a chi ti ha "
            "scritto, non rispondere come se conoscessi la casa."
        )
    context_parts: list[str] = []
    if nucleo_testo:
        context_parts.append(nucleo_testo)
    if past_str:
        context_parts.append(f"## Sessioni precedenti\n{past_str}")
    return "\n\n".join(context_parts)


def _bridge_on(app) -> bool:
    """Whether the reasoning-queue bridge is wired into this app.

    server.py's ``_on_startup`` always creates ``app["reasoning_queue"]``
    unconditionally — ``BRIDGE_ENABLED`` only gates whether server.py's
    sweep (``_reasoning_sweep``) actually claims/prunes that queue and
    whether ``chat_via_subscription`` is considered usable (fetta E3 Task 4
    removed the third reader, the holistic path's own enqueue via
    ``_holistic_reason`` — that path is gone entirely now), it doesn't
    control whether the queue object exists. So presence of the key is the
    right signal for chat: it's also how tests opt in/out (wire or don't
    wire ``app["reasoning_queue"]``) without touching env vars.
    """
    return app.get("reasoning_queue") is not None


async def _enqueue_chat_job(
    request: web.Request, impostazioni, message: str, data_dir: str,
) -> web.Response:
    """Chat-via-abbonamento (Slice 4b, Task 2): hand the turn to the async
    reasoning queue (``kind="chat"``) instead of calling a runner
    synchronously — subscription mode may have no local runner/API key at
    all, that's the point.

    The user turn is persisted to chat_store BEFORE enqueueing (contract
    from Task 1's report): a consumer could claim and resolve the job, and
    ultimately read history back, before this request even returns, and a
    session that opens on an assistant turn is rejected by the Claude API.

    fetta E4 Task 5 ("un bot solo"): chat_store non prende piu' un id —
    c'e' UNA cronologia, non piu' una per chatbot. Il parametro
    `effective_chatbot_id` (e con lui il ramo `if effective_chatbot_id:`
    che poteva saltare l'append) sparisce insieme al concetto: append e
    load qui sotto sono sempre incondizionati.
    """
    append_messages([
        {"role": "user", "content": message},
    ], data_dir)

    # Built AFTER the append above, so the current user turn is the last
    # entry — the external runner needs it to know what it's replying to.
    history = load_history(data_dir)
    sanitized_history = _trim_history(history)
    system_prompt = _build_system_prompt(impostazioni)

    reasoning_queue = request.app["reasoning_queue"]
    now = time.time()
    deadline = now + int(os.environ.get("BRIDGE_DEADLINE_MIN", "5")) * 60
    context = {
        "history": sanitized_history,
        "system_prompt": system_prompt,
        # fetta "il ponte riceve il nucleo" (parita' A, Task 2): il job porta
        # anche il contesto della casa -- la STESSA stringa che il ramo
        # sincrono passa al runner, dalla STESSA funzione (non una seconda
        # composizione destinata a divergere). Prima di questo task il ponte
        # riceveva solo `history` + `system_prompt` e rispondeva senza sapere
        # nulla della casa, mentre il percorso sincrono aveva il nucleo: era
        # la disparita' che questa fetta chiude. Si compone QUI, al momento
        # dell'accodamento, perche' e' l'ultimo punto in cui esistono l'app e
        # gli archivi: il runner del ponte gira altrove e non li ha. Da cui
        # l'unica cosa che il prompt puo' promettere al modello e' una
        # fotografia presa in questo istante, non una lettura dal vivo (vedi
        # `agent/prompts.py`).
        "contesto": componi_contesto_chat(request.app, data_dir),
        # fetta "il ponte riceve il nucleo" (parita' A, Task 3): le due
        # impostazioni della chat che SONO testo di prompt -- gli stessi due
        # valori che il ramo sincrono legge qui sotto, a `handle_chat`
        # (`impostazioni.restrict_to_home` / `.response_mode`). Prima di
        # questo task il job non le portava affatto e il ponte rispondeva
        # sempre senza restrizione ne' modificatore di formato, qualunque
        # fosse la configurazione dell'utente.
        "restrict_to_home": impostazioni.restrict_to_home,
        "response_mode": impostazioni.response_mode,
        # fetta "il ponte riceve il nucleo" (parita' A, Task 4): l'ultima
        # delle tre impostazioni mancanti. Il ramo sincrono (sotto,
        # `handle_chat`) risolve `impostazioni.model` con la STESSA
        # `resolve_model` e lo stesso `provider_models["claude"]` di
        # default -- niente di nuovo, solo lo stesso calcolo fatto anche
        # QUI, perche' il runner del ponte gira altrove e non ha ne' l'app
        # ne' `models_config`. La differenza col ramo sincrono e' che il
        # ponte parla SOLO con la CLI dell'abbonamento Claude Max, mai con
        # l'API a consumo di nessun provider: `modello_cli` traduce il
        # modello risolto (che puo' essere di qualunque provider) in un
        # alias della CLI, dichiarando nel log un modello non-Anthropic
        # invece di lasciarlo fallire muto ad ogni turno (vedi il suo
        # docstring in agent/runner.py -- silenzio dichiarato ② della
        # fetta).
        "model": modello_cli(resolve_model(
            impostazioni.model, "chat",
            (request.app.get("models_config") or {}).get("provider_models", {}).get("claude", ""),
        )),
    }
    # fetta E5 Task 2, fix round 1 (I-2): il `context` qui sopra porta sei
    # chiavi e `thinking_budget` NON e' fra loro -- il ponte parla con la CLI
    # dell'abbonamento, che non espone un budget di ragionamento per turno.
    # Finche' quel valore si poteva cambiare solo scrivendo a mano il JSON in
    # /data l'omissione era innocua; da quando l'utente lo imposta dalla
    # pagina «Impostazioni chat» e legge «Salvato», tacere qui significa
    # lasciarlo davanti a un'impostazione che risulta salvata e non fa niente,
    # senza una riga da nessuna parte. Si dichiara al momento
    # dell'accodamento, una volta per turno e solo se e' diverso da zero.
    if impostazioni.thinking_budget:
        logger.warning(
            "thinking_budget=%d NON viene applicato a questo turno: passa dal "
            "ponte per abbonamento, che parla con la CLI di Claude Code e non "
            "espone un budget di ragionamento per richiesta. L'impostazione "
            "resta salvata ma non ha effetto qui: il ragionamento esteso vale "
            "solo con i modelli Claude sul percorso diretto (chat_via_"
            "subscription spento).",
            impostazioni.thinking_budget,
        )

    job_id = reasoning_queue.enqueue("chat", {}, context, deadline, now=now)
    return web.json_response({"status": "pending", "job_id": job_id}, status=202)


async def handle_chat_reply_poll(request: web.Request) -> web.Response:
    """GET /api/chat/reply/{job_id} — the UI polls this after a 202 pending
    response from handle_chat. Reads the SAME queue row Task 1's submit
    branch resolves (``ReasoningQueue.submit`` always writes decision_json,
    independent of whether the chat_store write in that branch succeeded)."""
    job_id = request.match_info.get("job_id", "")
    reasoning_queue = request.app.get("reasoning_queue")
    if reasoning_queue is None:
        return web.json_response({"error": "reasoning queue not configured"}, status=503)
    job = reasoning_queue.get(job_id)
    if job is None:
        return web.json_response({"error": "not found"}, status=404)
    status = job.get("status")
    decision = job.get("decision") or {}
    reply = decision.get("reply")
    if status in ("expired", "failed"):
        # Never spin forever: the ponte-push sweep (server.py's
        # _reasoning_sweep) already left non-holistic jobs in this state
        # without routing them anywhere else -- this is the only place they
        # get surfaced to the user.
        return web.json_response({
            "status": "error",
            "message": "La risposta non è arrivata in tempo. Riprova.",
        })
    if status == "decided" and not reply:
        # Task 1's chat_reply_skipped outcome: a decision was recorded but it
        # carries no usable reply. Same terminal treatment as expired/failed
        # -- pending-forever would strand the UI.
        return web.json_response({
            "status": "error",
            "message": "La risposta non è arrivata in tempo. Riprova.",
        })
    if not reply:
        return web.json_response({"status": "pending"})
    payload = {"status": "done", "reply": reply}
    # fetta "il ponte riceve gli strumenti" (parita' B, Task 5): `tools_called`
    # e' la SOLA cosa che rende osservabile una scrittura di `ricorda` fatta
    # dal ponte -- vedi il docstring in cima a `agent/runner.py`. Compare in
    # `decision` SOLO quando `_reason_chat` ha girato in modalita' `live`
    # (un job mock o un `decision_json` scritto prima di questo deploy non
    # porta la chiave): questo `if` e' l'unico cambio a questa funzione, i
    # rami "pending"/"error" sopra restano identici. Il conteggio dei giri
    # "esposto dove l'utente lo vede" (progetto, Sec5.2) e' len() di questa
    # stessa lista lato client: non serve un secondo contatore qui da tenere
    # allineato con lei.
    if "tools_called" in decision:
        payload["debug"] = {"tools_called": decision["tools_called"]}
    return web.json_response(payload)


async def handle_chat(request: web.Request) -> web.Response:
    # fetta E4 Task 6, fix round 1 (Important 1 della review indipendente):
    # il vecchio calcolo dell'identita' utente e il suo inoltro ai runner
    # (`user_id=`) sono usciti -- `user_id` non aveva piu' nessun lettore nel
    # corpo dei due runner (il suo unico lettore era il ramo di scorta
    # rimosso da questo stesso task), quindi il valore entrava nei runner e
    # veniva buttato in silenzio. Nessun altro punto di questa funzione lo
    # legge: e' uscito con lui, non lasciato come calcolo morto.
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    message = body.get("message", "").strip()
    if not message:
        return web.json_response({"error": "message required"}, status=400)
    if len(message) > 4000:
        return web.json_response({"error": "message too long (max 4000 chars)"}, status=413)

    data_dir = request.app.get("data_dir", "/data")
    impostazioni = request.app["impostazioni_chat"]

    # Enforce max turns limit (count from DB, not from the trimmed context
    # window). Final-review Fix 1 (Slice 4b): hoisted ABOVE the subscription
    # branch below — this check is branch-independent (it reads the turn
    # count from chat_store, never from the sync path's trimmed history) and
    # must run before anything is persisted/enqueued, otherwise a session
    # turn limit is silently bypassed whenever chat_via_subscription is on
    # (the old position, after the subscription branch's early return, was
    # never reached in that mode).
    max_turns = impostazioni.max_chat_turns
    if max_turns > 0:
        turn_count = count_user_turns(data_dir)
        if turn_count >= max_turns:
            return web.json_response({
                "error": "max_turns_reached",
                "turns": turn_count,
                "limit": max_turns,
            })

    # Slice 4b (chat via abbonamento), Task 2: when subscription mode is on
    # AND the reasoning-queue bridge is wired, hand the turn to the async
    # queue instead of calling a local runner — subscription mode may have
    # no runner/API key configured at all locally, that's the point. Task 1
    # built the receiving end (kind="chat" submit -> chat_store); this is
    # the sending end. Checked BEFORE the runner-required guard below so
    # subscription mode works even without CLAUDE_API_KEY.
    if request.app.get("chat_via_subscription") and _bridge_on(request.app):
        # Slice 4b Task 3: two guards on the async path ONLY -- the sync path
        # above/below is unaffected when the flag is off. Checked before
        # anything is persisted/enqueued so a blocked turn leaves no trace.
        reasoning_queue = request.app["reasoning_queue"]
        # In-flight guard first: it's the more specific, more actionable
        # signal for the user (retry once the current answer lands), so it
        # wins even if the daily cap is ALSO exhausted.
        if reasoning_queue.has_pending_chat():
            return web.json_response(
                {"error": "C'è già una risposta in arrivo per questa conversazione."},
                status=409,
            )
        _cap = request.app.get("chat_daily_cap")
        chat_daily_cap = int(_cap) if _cap is not None else 50
        if reasoning_queue.count_chat_today() >= chat_daily_cap:
            return web.json_response(
                {"error": "Limite giornaliero di messaggi chat raggiunto."},
                status=429,
            )
        return await _enqueue_chat_job(request, impostazioni, message, data_dir)

    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        # E' la PRIMA cosa che legge chi installa HIRIS e apre la chat senza
        # aver ancora configurato niente. Prima diceva, in inglese, «set
        # CLAUDE_API_KEY»: un nome di variabile d'ambiente che NON e'
        # un'opzione dell'add-on (l'opzione si chiama `claude_api_key`) e che
        # chi usa l'abbonamento non deve compilare affatto. Ora e' in
        # italiano, nomina i campi come li vede nel Supervisor, e dice le due
        # strade invece di una.
        return web.json_response(
            {"error": (
                "Nessun provider AI configurato: HIRIS non ha ancora un modello a "
                "cui chiedere. Apri Impostazioni → Add-on → HIRIS → Configurazione "
                "e scegli una strada: con l'abbonamento Claude, attiva «Attiva "
                "provider: Abbonamento (Claude Max)» e incolla il token in «Token "
                "OAuth Claude Code (abbonamento)»; con l'API a consumo, attiva "
                "«Attiva provider: API Claude» e incolla la chiave in «Chiave API "
                "Claude». Poi riavvia l'add-on."
            )},
            status=503,
        )

    # Load server-side history (client-sent history field is ignored)
    history = load_history(data_dir)

    # (max-turns check now runs above, before the subscription branch — see
    # Fix 1 comment there.)

    context_history = _trim_history(history)

    # fetta E4 Task 4: il ramo "agent is None -> BASE_SYSTEM_PROMPT senza
    # cronologia" non esiste piu'. Prima, un chatbot seminato mancante (id
    # sbagliato, seed mai girato) faceva silenziosamente cadere `agent` a
    # `None`: il prompt degradava a una stringa vuota E la cronologia
    # smetteva di essere letta/scritta, senza che nessun log lo dicesse.
    # `impostazioni_chat` non e' mai `None` (`ImpostazioniChat.carica` non lo
    # restituisce mai) -- quel ramo di degrado e' impossibile per
    # costruzione, non solo non piu' preso. fetta E4 Task 5 ("un bot solo"):
    # anche l'id transitorio che qui sotto selezionava la cronologia
    # (`effective_chatbot_id`) e' uscito -- chat_store non ha piu' alcuna
    # nozione di id da cui degradare, `load_history`/`get_past_summaries`
    # leggono sempre l'UNICA cronologia che esiste.
    system_prompt = _build_system_prompt(impostazioni)

    # Nucleo + sessioni precedenti, in un'unica stringa: `componi_contesto_chat`
    # (Task 1 della fetta "il ponte riceve il nucleo", parita' A) estrae
    # invariato il blocco che prima viveva qui -- vedi il suo docstring per il
    # perche' (il Task 2 mette la STESSA stringa nel job del ponte, senza
    # ricopiarla) e per il ragionamento storico su nucleo/degrado/sessioni.
    context_str = componi_contesto_chat(request.app, data_dir)

    # I cinque strumenti della chat -- il perche' di ogni riga sta
    # nel docstring di `costruisci_dispatcher_strumenti` (sopra), che dalla
    # parita' B e' l'unico costruttore del dispatcher: qui e nella rotta
    # `/api/mcp` del ponte si chiama la STESSA funzione, non due costruzioni
    # che possono divergere.
    #
    # fix round 1 (Important 3 della review indipendente): il commento che
    # viveva qui descriveva un ramo -- il "dispatcher di scorta"
    # `self._dispatcher`, che leggeva `visible_entity_ids` e degradava APERTO
    # quando assente -- gia' uscito dai runner alla fetta E2 Task 7
    # (`ToolDispatcher`) e i cui ultimi resti (il costruttore `dispatcher=`,
    # l'`elif self._dispatcher is not None`) sono usciti dalla fetta E4,
    # Task 6. `visible_entity_ids` non e' piu' un parametro di nessuna firma:
    # non c'e' piu' niente da riaprire ne' da tenere chiuso su quel fronte, la
    # trappola stessa non esiste piu'.
    dispatcher_strumenti = costruisci_dispatcher_strumenti(request.app)

    agent_model = impostazioni.model
    # Personas are always the chat entity (Slice 5 retired the non-chat
    # "agent" type and the `type` field itself) — no per-type branch needed
    # here. Kept as a literal only because runner.chat/chat_stream still take
    # `agent_type` for model auto-resolution (AUTO_MODEL_MAP).
    agent_type = "chat"
    # fetta E4 Task 4: `max_tokens` era uno dei sette campi che il turno di
    # chat leggeva dal vecchio `Chatbot`, ma GIA' inerte in pratica -- non e'
    # entrato in `ImpostazioniChat`, diventa qui una costante diretta:
    # la chat interattiva ha un tetto d'uscita piu' alto del `MAX_TOKENS` di
    # modulo dei runner (4096), perche' una risposta lunga -- il riepilogo di
    # una casa grande, un elenco di ricordi -- lo supera legittimamente.
    #
    # fetta E4 Task 9 (il conto): questo commento diceva "higher output ceiling
    # than the per-agent eval cap" e "complex requests -- a multi-view
    # dashboard, a long script -- legitimately need more room, and the old 4096
    # default truncated them mid-tool-call". Tre dichiarazioni false al
    # presente, stessa famiglia bonificata al Task 8 in claude_runner.py
    # (`_TRUNCATION_NOTICE`, il commento su `MAX_TOKENS`): l'agente di
    # valutazione col suo tetto e' uscito con la fetta E3 Task 8
    # (`run_with_actions`/`EVALUATION_TOOL_DEFS`) -- non c'e' piu' un "eval cap"
    # con cui confrontarsi; le plance e gli script non sono piu' cose che HIRIS
    # sa fare (l'attuazione e' uscita con la fetta E2), quindi non sono l'uso
    # che riempie il tetto; e nessun tool-call puo' essere troncato "a meta'"
    # per colpa di un default che nessun chiamante di produzione raggiunge piu'
    # (qui si passa SEMPRE `CHAT_MAX_TOKENS`).
    #
    # Il vecchio codice "floorava" un valore persistito fino a
    # CHAT_MAX_TOKENS -- ma senza piu' un editor che possa persisterne uno
    # diverso da 4096 (uscito con la E4 Task 3), il floor scattava SEMPRE:
    # usare direttamente CHAT_MAX_TOKENS e' lo stesso comportamento, senza il
    # giro morto.
    # `require_confirmation` (l'altro dei sette campi, gia' inerte da fetta E2
    # Task 5) e' uscito per intero dalla firma dei runner alla fetta E4 Task 6:
    # non c'e' piu' nulla da passare qui.
    agent_max_tokens = CHAT_MAX_TOKENS
    agent_restrict = impostazioni.restrict_to_home
    agent_response_mode = impostazioni.response_mode
    agent_thinking_budget = impostazioni.thinking_budget

    wants_stream = (
        "text/event-stream" in request.headers.get("Accept", "")
        or body.get("stream") is True
    )

    if wants_stream:
        stream_resp = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
        await stream_resp.prepare(request)
        collected_tokens: list[str] = []
        async for chunk in runner.chat_stream(
            user_message=message,
            system_prompt=system_prompt,
            context_str=context_str,
            conversation_history=context_history,
            model=agent_model,
            max_tokens=agent_max_tokens,
            agent_type=agent_type,
            restrict_to_home=agent_restrict,
            # fetta E4 Task 6 ("un bot solo"): `chatbot_id`/`require_confirmation`
            # sono usciti dalla firma dei runner -- non c'e' piu' nulla da
            # passare qui. `chatbot_id` alimentava solo il tracking dei consumi
            # per-bot (uscito con lui) e il campo di debug `agent_id` del
            # done-event SSE (uscito anche lui, nessun lettore in static/).
            response_mode=agent_response_mode,
            thinking_budget=agent_thinking_budget,
            strumenti=STRUMENTI_CONOSCENZA,
            dispatcher=dispatcher_strumenti,
        ):
            await stream_resp.write(chunk.encode())
            try:
                evt = json.loads(chunk.removeprefix("data: ").strip())
                etype = evt.get("type")
                if etype == "token":
                    collected_tokens.append(evt.get("text", ""))
                elif etype == "discard_collected":
                    # Runner detected a leaked tool-call rendered as text and
                    # asked us to drop the polluted assistant turn before it
                    # reaches chat_store (would corrupt next turn's history).
                    collected_tokens.clear()
            except Exception as exc:
                # Non-JSON chunk (e.g. heartbeat ': keep-alive') is normal in SSE.
                logger.debug("SSE chunk parse skipped: %s", exc)
        await stream_resp.write_eof()
        full_response = "".join(collected_tokens)
        # Fetta "esce il documentale": qui c'era la detokenizzazione della
        # risposta accumulata (`pseudonymizer.detokenize(full_response,
        # runner.last_pseudonym_map)`), uscita con brain/privacy.py. Era un
        # no-op: nessun percorso del prodotto chiamava piu' `pseudonymize()`,
        # quindi `last_pseudonym_map` era sempre vuota e non c'era nessun
        # token da riespandere. Vedi il commento gemello nel ramo sincrono.
        # Skip persistence for toxic / synthetic-error responses so the next
        # turn does not see a poisoned history. discard_collected already
        # zeroes collected_tokens for tool-call leaks; this also covers the
        # rare case where the runner returns a known-bad payload some other
        # way (e.g. partial leak that slipped past detection).
        if full_response and not _is_toxic_assistant(full_response):
            append_messages([
                {"role": "user", "content": message},
                {"role": "assistant", "content": full_response},
            ], data_dir)
        return stream_resp

    try:
        response = await runner.chat(
            user_message=message,
            system_prompt=system_prompt,
            context_str=context_str,
            conversation_history=context_history,
            model=agent_model,
            max_tokens=agent_max_tokens,
            agent_type=agent_type,
            restrict_to_home=agent_restrict,
            # Vedi il commento gemello sul ramo streaming sopra.
            response_mode=agent_response_mode,
            thinking_budget=agent_thinking_budget,
            strumenti=STRUMENTI_CONOSCENZA,
            dispatcher=dispatcher_strumenti,
        )
    except RunnerBackendError as exc:
        # Review C/#13: runners now raise instead of returning a friendly
        # string on API failure, so LLMRouter's auto-fallback loop actually
        # engages. That loop only ever raises here when `agent_model` pins an
        # explicit non-"auto" model (the auto path already turns this into a
        # returned string once every backend is exhausted) — reproduce the
        # exact same string-shaped degraded response so everything below
        # (detokenize/toxicity/persistence/serialization) is unaffected.
        response = exc.friendly_message

    # Fetta "esce il documentale": qui c'era la detokenizzazione della
    # risposta prima del controllo di tossicita', della persistenza e della
    # serializzazione. Esce con brain/privacy.py, e non cambia il testo di un
    # carattere: la pseudonimizzazione era INERTE nell'intero prodotto --
    # l'unico ramo che popolava `last_pseudonym_map` (il dispatcher che
    # passava `pseudonym_map=` a `dispatch()`) e' uscito con la fetta E2
    # Task 7, quindi da allora `detokenize` girava su un dizionario vuoto.
    # Era, testualmente, una promessa di protezione non mantenuta: la stessa
    # famiglia della frase su `mayan.sensitivity` che esce con questa fetta.

    # Persist the new user+assistant exchange — but skip when the runner
    # returned a synthetic error / leak sentinel, so the next turn doesn't
    # inherit a degraded history. The user retains the visible error in the
    # current response payload.
    if not _is_toxic_assistant(response):
        append_messages([
            {"role": "user", "content": message},
            {"role": "assistant", "content": response},
        ], data_dir)

    raw = getattr(runner, "last_tool_calls", None)
    # Pass the raw tool-call objects ({tool, input}) — the shape the panel's
    # appendDebug() and the SSE done-event both expect. Previously this used
    # t.get("name"), but last_tool_calls keys are "tool"/"input", so every entry
    # was None; appendDebug then threw on t.input AFTER the answer had rendered,
    # surfacing a spurious "Errore di connessione" with no backend-side error.
    # Review finale fetta E2, I-4: la redazione dell'OTP di confirm_pending
    # (qui e nella gemella `_redact_stream_tool_calls`, claude_runner.py) e'
    # uscita -- confirm_pending non e' dichiarato in nessun catalogo
    # raggiungibile, quindi un tool_use con quel nome non arriva mai qui:
    # l'impianto OTP e' uscito col Task 5, non esiste piu' un codice da
    # nascondere.
    tools_called = [
        {"tool": t.get("tool", ""), "input": t.get("input")}
        for t in raw if isinstance(t, dict)
    ] if isinstance(raw, list) else []
    raw_thinking = getattr(runner, "last_thinking_blocks", None)
    thinking_blocks = list(raw_thinking) if isinstance(raw_thinking, list) else []
    debug_payload: dict = {"tools_called": tools_called}
    if thinking_blocks:
        debug_payload["thinking_blocks"] = thinking_blocks
    return web.json_response({"response": response, "debug": debug_payload})
