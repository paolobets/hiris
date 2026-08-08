import json
import logging
import os
import time

from aiohttp import web

from ..brain.identity import resolve_owner
from ..casa.strumenti import STRUMENTI_CONOSCENZA, DispatcherConoscenza
from ..chat_store import (
    load_history, append_messages, get_past_summaries, count_user_turns,
    _is_toxic_assistant,
)
from ..claude_runner import CHAT_MAX_TOKENS, RunnerBackendError
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


def _build_system_prompt(agent) -> str:
    """Static agent persona (strategic_context + system_prompt), same
    assembly used by the sync path and reused for the async job context."""
    static_parts = []
    if agent and agent.strategic_context:
        static_parts.append(agent.strategic_context.strip())
    if agent and agent.system_prompt:
        static_parts.append(agent.system_prompt.strip())
    return "\n\n---\n\n".join(static_parts)


def _bridge_on(app) -> bool:
    """Whether the reasoning-queue bridge is wired into this app.

    server.py's ``_on_startup`` always creates ``app["reasoning_queue"]``
    unconditionally — the holistic path's own ``BRIDGE_ENABLED`` env var only
    gates whether *it* enqueues into that same queue vs. reasoning locally,
    it doesn't control whether the queue object exists. So presence of the
    key is the right signal for chat: it's also how tests opt in/out (wire
    or don't wire ``app["reasoning_queue"]``) without touching env vars.
    """
    return app.get("reasoning_queue") is not None


async def _enqueue_chat_job(
    request: web.Request, agent, effective_chatbot_id: str | None,
    message: str, data_dir: str,
) -> web.Response:
    """Chat-via-abbonamento (Slice 4b, Task 2): hand the turn to the async
    reasoning queue (``kind="chat"``) instead of calling a runner
    synchronously — subscription mode may have no local runner/API key at
    all, that's the point.

    The user turn is persisted to chat_store BEFORE enqueueing (contract
    from Task 1's report): a consumer could claim and resolve the job, and
    ultimately read history back, before this request even returns, and a
    session that opens on an assistant turn is rejected by the Claude API.
    """
    if effective_chatbot_id:
        append_messages(effective_chatbot_id, [
            {"role": "user", "content": message},
        ], data_dir)

    # Built AFTER the append above, so the current user turn is the last
    # entry — the external runner needs it to know what it's replying to.
    history = load_history(effective_chatbot_id, data_dir) if effective_chatbot_id else []
    sanitized_history = _trim_history(history)
    system_prompt = _build_system_prompt(agent)

    reasoning_queue = request.app["reasoning_queue"]
    now = time.time()
    deadline = now + int(os.environ.get("BRIDGE_DEADLINE_MIN", "5")) * 60
    context = {
        "chatbot_id": effective_chatbot_id,
        "history": sanitized_history,
        "system_prompt": system_prompt,
    }
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
    return web.json_response({"status": "done", "reply": reply})


async def handle_chat(request: web.Request) -> web.Response:
    owner = resolve_owner(request)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    message = body.get("message", "").strip()
    if not message:
        return web.json_response({"error": "message required"}, status=400)
    if len(message) > 4000:
        return web.json_response({"error": "message too long (max 4000 chars)"}, status=413)

    # "chatbot_id" is the current wire key (SP-4 Fase A rename); "agent_id" is
    # kept as a retro-compat fallback so existing Lovelace card configs / older
    # clients that still send the pre-rename key keep working unchanged.
    chatbot_id = body.get("chatbot_id") or body.get("agent_id")
    data_dir = request.app.get("data_dir", "/data")
    engine = request.app["engine"]

    agent = None
    if chatbot_id:
        agent = engine.get_chatbot(chatbot_id)
    if agent is None:
        agent = engine.get_default_chatbot()

    effective_chatbot_id = getattr(agent, "id", None) if agent else None

    # Enforce max turns limit (count from DB, not from the trimmed context
    # window). Final-review Fix 1 (Slice 4b): hoisted ABOVE the subscription
    # branch below — this check is branch-independent (it reads the turn
    # count from chat_store, never from the sync path's trimmed history) and
    # must run before anything is persisted/enqueued, otherwise an agent's
    # session turn limit is silently bypassed whenever chat_via_subscription
    # is on (the old position, after the subscription branch's early return,
    # was never reached in that mode).
    max_turns = getattr(agent, "max_chat_turns", 0) if agent else 0
    if max_turns > 0:
        turn_count = count_user_turns(effective_chatbot_id, data_dir) if effective_chatbot_id else 0
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
        if reasoning_queue.has_pending_chat(effective_chatbot_id):
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
        return await _enqueue_chat_job(request, agent, effective_chatbot_id, message, data_dir)

    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response(
            {"error": "Claude runner not configured — set CLAUDE_API_KEY"}, status=503
        )

    # Load server-side history (client-sent history field is ignored)
    history = load_history(effective_chatbot_id, data_dir) if effective_chatbot_id else []

    # (max-turns check now runs above, before the subscription branch — see
    # Fix 1 comment there.)

    context_history = _trim_history(history)

    if agent is None:
        logger.warning("No agent found (requested: %s). BASE_SYSTEM_PROMPT will be used.", chatbot_id)

    # system_prompt = static agent content (strategic_context + system_prompt).
    # Kept separate from context_str so claude_runner can cache it independently.
    system_prompt = _build_system_prompt(agent)

    # Inject closed-session summaries so Claude remembers previous conversations.
    # Le sessioni precedenti restano una fonte A PARTE dal nucleo (Task 3):
    # sono cronologia di conversazioni chiuse, non conoscenza sulla casa --
    # il nucleo non le contiene e non deve contenerle.
    past = get_past_summaries(effective_chatbot_id, data_dir) if effective_chatbot_id else []
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
    # torneranno (vedi il brief). SemanticContextMap, il blocco RAG e
    # KnowledgeStore.declared() non sono stati cancellati: smettono solo di
    # essere chiamati da QUI (escono nella fetta successiva).
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
        nucleo_testo, _nucleo_riepilogo = costruisci_nucleo(request.app)
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
    context_str = "\n\n".join(context_parts)

    # I quattro strumenti che conoscono la casa (casa/strumenti.py) -- non il
    # catalogo di trentaquattro di ALL_TOOL_DEFS: la chat della 2.0 CONOSCE,
    # non agisce (vedi il docstring del modulo). `DispatcherConoscenza` si
    # costruisce dagli stessi archivi/cache che alimentano `costruisci_nucleo()`
    # qui sopra -- lo stesso specchio dello stato vivo, non uno ricalcolato a
    # mano -- ed e' SEMPRE passato, anche quando gli archivi sono assenti: i
    # suoi quattro metodi non sollevano mai, dichiarano un `errore` per
    # strumento invece (vedi `DispatcherConoscenza.dispatch`).
    #
    # Passarlo sempre (mai `None`) tiene chiusa anche un'altra trappola: e'
    # il ramo `self._dispatcher.dispatch(...)` dei runner (il dispatcher di
    # scorta del catalogo vecchio, preso SOLO quando `dispatcher` e' `None`)
    # a leggere `visible_entity_ids` e a degradare APERTO quando e' assente
    # (`if visible_entity_ids: ...` -- nessun filtro quando e' `None`). Con
    # `dispatcher` sempre valorizzato quel ramo non viene mai preso dalla
    # chat, quindi non passare piu' `visible_entity_ids` da qui (la mappa
    # semantica che lo produceva non e' piu' consultata) non riapre nulla.
    # fetta E2 Task 7: quel dispatcher di scorta (ToolDispatcher) e' uscito
    # -- il ramo ora degrada a un errore "non disponibile" per QUALUNQUE
    # chiamante che lo prenda, ma la chat non lo prende mai per il motivo
    # sopra, quindi qui non cambia nulla.
    dispatcher_conoscenza = DispatcherConoscenza(
        request.app.get("archivio_casa"),
        request.app.get("archivio_memoria"),
        cache=request.app.get("entity_cache"),
    )

    agent_model = getattr(agent, "model", "auto") if agent else "auto"
    agent_max_tokens = getattr(agent, "max_tokens", 4096) if agent else 4096
    # Personas are always the chat entity (Slice 5 retired the non-chat
    # "agent" type and the `type` field itself) — no per-type branch needed
    # here. Kept as a literal only because runner.chat/chat_stream still take
    # `agent_type` for model auto-resolution (AUTO_MODEL_MAP).
    agent_type = "chat"
    # Interactive chat gets a higher output ceiling than the per-agent eval cap:
    # complex requests (a multi-view dashboard, a long script) legitimately need
    # more room, and the old 4096 default truncated them mid-tool-call. Floor up.
    if agent_max_tokens < CHAT_MAX_TOKENS:
        logger.info(
            "chat: max_tokens floored %d -> %d (ceiling, not target — no extra cost "
            "on normal replies)", agent_max_tokens, CHAT_MAX_TOKENS,
        )
        agent_max_tokens = CHAT_MAX_TOKENS
    agent_restrict = getattr(agent, "restrict_to_home", False) if agent else False
    agent_require_confirmation = getattr(agent, "require_confirmation", False) if agent else False
    agent_response_mode = getattr(agent, "response_mode", "auto") if agent else "auto"
    agent_thinking_budget = getattr(agent, "thinking_budget", 0) if agent else 0

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
            require_confirmation=agent_require_confirmation,
            chatbot_id=effective_chatbot_id,
            response_mode=agent_response_mode,
            thinking_budget=agent_thinking_budget,
            strumenti=STRUMENTI_CONOSCENZA,
            dispatcher=dispatcher_conoscenza,
            user_id=owner,
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
        # De-tokenize pseudonymized tokens in the accumulated response so
        # persisted history holds real values (consistent with what the user
        # sees in the non-streaming path).
        # Note: individual SSE chunks streamed to the client may still show
        # tokens until a future streaming refactor re-emits de-tokenized text.
        pseudonymizer = request.app.get("pseudonymizer")
        if pseudonymizer is not None and full_response:
            # Only expand tokens THIS exchange's own pseudonymize call minted
            # (review B/#7) — never a global/cross-conversation lookup.
            pseudonym_map = getattr(runner, "last_pseudonym_map", None) or {}
            full_response = pseudonymizer.detokenize(full_response, pseudonym_map)
        # Skip persistence for toxic / synthetic-error responses so the next
        # turn does not see a poisoned history. discard_collected already
        # zeroes collected_tokens for tool-call leaks; this also covers the
        # rare case where the runner returns a known-bad payload some other
        # way (e.g. partial leak that slipped past detection).
        if effective_chatbot_id and full_response and not _is_toxic_assistant(full_response):
            append_messages(effective_chatbot_id, [
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
            require_confirmation=agent_require_confirmation,
            chatbot_id=effective_chatbot_id,
            response_mode=agent_response_mode,
            thinking_budget=agent_thinking_budget,
            strumenti=STRUMENTI_CONOSCENZA,
            dispatcher=dispatcher_conoscenza,
            user_id=owner,
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

    # De-tokenize pseudonymized tokens before toxicity check, persistence,
    # and serialization so both the stored history and the returned JSON
    # contain real values rather than vault tokens.
    pseudonymizer = request.app.get("pseudonymizer")
    if pseudonymizer is not None and isinstance(response, str) and response:
        # Only expand tokens THIS exchange's own pseudonymize call minted
        # (review B/#7) — never a global/cross-conversation lookup.
        pseudonym_map = getattr(runner, "last_pseudonym_map", None) or {}
        response = pseudonymizer.detokenize(response, pseudonym_map)

    # Persist the new user+assistant exchange — but skip when the runner
    # returned a synthetic error / leak sentinel, so the next turn doesn't
    # inherit a degraded history. The user retains the visible error in the
    # current response payload.
    if effective_chatbot_id and not _is_toxic_assistant(response):
        append_messages(effective_chatbot_id, [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response},
        ], data_dir)

    raw = getattr(runner, "last_tool_calls", None)
    # Pass the raw tool-call objects ({tool, input}) — the shape the panel's
    # appendDebug() and the SSE done-event both expect. Previously this used
    # t.get("name"), but last_tool_calls keys are "tool"/"input", so every entry
    # was None; appendDebug then threw on t.input AFTER the answer had rendered,
    # surfacing a spurious "Errore di connessione" with no backend-side error.
    def _debug_input(t: dict):
        # OTP secrecy toward the client: confirm_pending's `input` carries the
        # 6-digit code the user typed in chat. It must never be echoed back in
        # the HTTP response debug payload — this covers the HTTP debug-payload
        # surface (the sibling SSE redaction is `_redact_stream_tool_calls`,
        # claude_runner.py).
        inp = t.get("input")
        if t.get("tool") == "confirm_pending" and isinstance(inp, dict) and "code" in inp:
            return {**inp, "code": "***"}
        return inp

    tools_called = [
        {"tool": t.get("tool", ""), "input": _debug_input(t)}
        for t in raw if isinstance(t, dict)
    ] if isinstance(raw, list) else []
    raw_thinking = getattr(runner, "last_thinking_blocks", None)
    thinking_blocks = list(raw_thinking) if isinstance(raw_thinking, list) else []
    debug_payload: dict = {"tools_called": tools_called}
    if thinking_blocks:
        debug_payload["thinking_blocks"] = thinking_blocks
    return web.json_response({"response": response, "debug": debug_payload})
