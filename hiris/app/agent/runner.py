"""Runner hiris-agent: polla la coda di ragionamento HIRIS e ragiona (mock|live).

Porta in-addon del runner del gateway esterno (hiris-mcp-gateway/agent/runner.py).
L'internal token (env INTERNAL_TOKEN) resta usato per l'HTTP verso la reasoning
API (`/api/reasoning/claim` e `/api/reasoning/submit`).

NB (Fetta E2 Task 3): il percorso `claude --mcp-config` verso l'MCP interno
(Piano 2A, hiris/app/mcp/) e' uscito insieme al server che serviva -- era il
terzo catalogo di strumenti della mappa del prodotto, e ora MCP non e' piu'
servito a Claude. `_reason_chat` sotto quindi ragiona in puro testo, senza
poter leggere o controllare la casa: e' un guscio ridotto, non spetta a
questo task rifarlo (arriva con il ponte push, un'altra fetta)."""
import asyncio, json, logging, os, subprocess, time
import httpx
from . import prompts

log = logging.getLogger("hiris.agent")

# Tool LOCALI del CLI sempre vietati (il modello non deve toccare shell/fs del
# container addon).
_LOCAL_TOOLS_DENY = "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,NotebookEdit,NotebookRead,Task"


def _chat_claude_args(system: str, user: str, model: str) -> list:
    return ["claude", "-p", user, "--model", model,
            "--system-prompt", system,
            "--exclude-dynamic-system-prompt-sections",
            "--disallowedTools", _LOCAL_TOOLS_DENY,
            "--permission-mode", "default", "--output-format", "json"]


# M-1 (Plan 2B final review, fast-follow): CLAUDE_API_KEY is HIRIS's own
# METERED Anthropic key (see run.sh) -- it must never reach this subprocess.
# The subscription runner authenticates `claude` via CLAUDE_CODE_OAUTH_TOKEN
# ONLY; forwarding the metered key here would let a subscription-mode `claude`
# silently fall back to spend-incurring API billing instead of the
# subscription, defeating the entire point of Plan 2B. ANTHROPIC_API_KEY is
# excluded for the same reason (a generic metered-API credential, if ever
# present in this env). Everything else prefixed ANTHROPIC_/CLAUDE_ (e.g.
# CLAUDE_CODE_OAUTH_TOKEN, CLAUDE_CONFIG_DIR) still passes through.
_SUBPROCESS_ENV_DENYLIST = {"CLAUDE_API_KEY", "ANTHROPIC_API_KEY"}


def _safe_subprocess_env() -> dict:
    env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", "")}
    for k, v in os.environ.items():
        if k in _SUBPROCESS_ENV_DENYLIST:
            continue
        if k.startswith("ANTHROPIC_") or k.startswith("CLAUDE_"):
            env[k] = v
    return env

def _reason_chat(job: dict, mode: str) -> dict:
    """Chat-via-abbonamento: risponde come HIRIS in puro testo (nessun tool HA:
    l'MCP interno che li serviva e' uscito, Fetta E2 Task 3). Fail-safe:
    mode!=live -> mock; su errore torna sempre una {"reply": <str>}."""
    context = job.get("context") or {}
    history = context.get("history") or []
    system_prompt = context.get("system_prompt") or ""
    if mode != "live":           # fail-safe: qualunque valore != "live" = mock
        return {"reply": "[mock] risposta di prova"}
    system, user = prompts.build_chat_messages(system_prompt, history)
    model = os.environ.get("HIRIS_AGENT_CHAT_MODEL", "sonnet")
    argv = _chat_claude_args(system, user, model)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=300, env=_safe_subprocess_env())
        if proc.returncode != 0:
            # claude -p --output-format json mette gli errori (auth 401, quota,
            # ecc.) su STDOUT come JSON, non su stderr: logga entrambi e prova a
            # estrarre un dettaglio leggibile per non nascondere la causa.
            log.warning("claude rc=%s stderr=%r stdout=%r", proc.returncode,
                        proc.stderr[:300], proc.stdout[:500])
            detail = ""
            try:
                j = json.loads(proc.stdout)
                detail = j.get("result") or j.get("error") or j.get("subtype") or ""
            except (ValueError, TypeError):
                detail = (proc.stdout or proc.stderr or "").strip()
            return {"reply": f"[errore runner rc={proc.returncode}] {str(detail)[:300]}".strip()}
        try:
            data = json.loads(proc.stdout)
            text = data.get("result") or ""
        except (ValueError, TypeError):
            text = proc.stdout
        return {"reply": (text or "").strip() or "[vuoto]"}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        log.warning("claude non eseguibile: %s", type(exc).__name__)
        return {"reply": "[runner non disponibile]"}

def reason(job: dict, mode: str) -> dict:
    """Il runner del ponte ragiona SOLO i job di chat.

    fetta E4 Task 8 ("un bot solo"): il ramo olistico e' uscito, con lui
    `prompts.build_holistic_prompt`/`_SYSTEM` e l'intero apparato che ne
    interpretava la risposta (`Decision`, `VERDICT_*`, `_parse_decision`,
    `parse_decision`). Il motivo e' che nessuno puo' piu' produrre un job
    diverso da "chat": l'unico `enqueue` del repo e' `kind="chat"`
    (api/handlers_chat.py), e il produttore dei job olistici
    (`_holistic_reason`) e' uscito alla fetta E3 Task 4.

    Silenzio dichiarato: un job non-chat puo' arrivare qui SOLO da un
    reasoning.db lasciato da un'installazione precedente questo deploy.
    Non lo si ignora in silenzio -- un pass muto sarebbe indistinguibile da
    un'assenza di problemi: un log esplicito lo dichiara e la decisione
    restituita e' VUOTA (nessun verdetto, nessuna azione). A valle,
    `handle_reasoning_submit` (api/handlers_reasoning.py) la registra e
    basta: non attua piu' nulla da fetta E3 Task 9."""
    kind = (job or {}).get("kind")
    if kind == "chat":
        return _reason_chat(job, mode)
    log.warning(
        "job non-chat in coda: nessun ramo lo ragiona piu' (job_id=%s, kind=%r) -- "
        "decisione vuota, il ramo olistico e' uscito con la fetta E4 Task 8",
        (job or {}).get("job_id"), kind)
    return {}

def build_headers() -> dict:
    """Header per la reasoning API interna (127.0.0.1:8099). Solo loopback:
    nessun residuo CF-Access/JWT di servizio (non serve, non c'e' rete
    esterna in mezzo)."""
    return {"X-HIRIS-Internal-Token": os.environ.get("INTERNAL_TOKEN", ""),
            "X-Requested-With": "hiris-agent"}

def run_once(client, base_url: str, headers: dict, mode: str) -> str:
    r = client.post(f"{base_url}/api/reasoning/claim", headers=headers, json={})
    r.raise_for_status()
    job = (r.json() or {}).get("job")
    if not job:
        return "idle"
    job_id = job.get("job_id"); nonce = job.get("nonce")
    if not job_id or not nonce:
        log.warning("claim malformato (job senza id/nonce)")
        return "failed"
    decision = reason(job, mode)
    sr = client.post(f"{base_url}/api/reasoning/submit", headers=headers,
                     json={"job_id": job_id, "nonce": nonce, "decision": decision})
    sr.raise_for_status()
    return "done" if (sr.json() or {}).get("ok") else "failed"

def poll_seconds() -> int:
    return int(os.environ.get("HIRIS_AGENT_POLL_SECONDS", "3"))


async def run_loop(base_url: str, get_headers, mode: str, poll_seconds: int) -> None:
    """Coroutine per il task asyncio in-addon (server.py, task 4). `run_once`
    resta sincrono (subprocess.run + httpx.Client): girano sullo stesso loop
    asyncio dell'intero addon (aiohttp), quindi vanno eseguiti in un thread
    executor (`run_in_executor`) e MAI chiamati direttamente nella coroutine,
    altrimenti un job claimato blocca l'intero addon fino a ~5 minuti
    (subprocess timeout=300, httpx.Client timeout=330)."""
    loop = asyncio.get_running_loop()
    with httpx.Client(timeout=330) as client:
        while True:
            try:
                headers = get_headers()
                outcome = await loop.run_in_executor(
                    None, run_once, client, base_url, headers, mode)
                if outcome != "idle":
                    log.info("run: %s", outcome)
            except Exception as exc:
                log.warning("run_once errore: %s", exc)
            await asyncio.sleep(poll_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    base_url = os.environ["HIRIS_BASE_URL"].rstrip("/")
    mode = os.environ.get("HIRIS_AGENT_MODE", "mock")
    headers = build_headers()
    interval = poll_seconds()
    log.info("hiris-agent avviato mode=%s poll=%ss", mode, interval)
    with httpx.Client(timeout=330) as client:
        while True:
            try:
                outcome = run_once(client, base_url, headers, mode)
                if outcome != "idle":
                    log.info("run: %s", outcome)
            except Exception as exc:
                log.warning("run_once errore: %s", exc)
            time.sleep(interval)

if __name__ == "__main__":
    main()
