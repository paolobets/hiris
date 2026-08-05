"""Runner hiris-agent: polla la coda di ragionamento HIRIS e ragiona (mock|live).

Porta in-addon del runner del gateway esterno (hiris-mcp-gateway/agent/runner.py),
adattata a loopback: l'MCP interno (Piano 2A) e' raggiungibile solo da
127.0.0.1 e non richiede auth (FastMCP auth=None) -> nessun bearer/JWT nella
mcp-config scritta su disco, nessun residuo CF-Access/JWT di servizio.
L'internal token (env INTERNAL_TOKEN) resta usato solo per l'HTTP verso la
reasoning API (`/api/reasoning/claim` e `/api/reasoning/submit`) e, dentro
2A, dal forward MCP->execute-API (LocalExecuteClient) — non dalla connessione
claude->MCP.
"""
import asyncio, json, logging, os, subprocess, time
from dataclasses import asdict
import httpx
from . import prompts
# Consolidamento 1.4: l'interpretazione della risposta del modello vive in un
# solo posto. Qui si importa, non si ricopia.
from ..watcher import reasoner as _reasoner

log = logging.getLogger("hiris.agent")

# Tool del gateway abilitati nella chat (nomi MCP: mcp__hiris__<nome>). Esclude i
# tool ponte-reasoning (claim_reasoning_job/submit_decision), che sono per il
# runner stesso, non per la chat.
_DEFAULT_CHAT_TOOLS = ",".join(
    "mcp__hiris__" + n for n in (
        "get_home_status", "get_area_entities", "get_entity_states", "get_history",
        "get_automation_config", "recall_memory", "create_task", "list_tasks",
        "cancel_task", "create_automation_proposal", "send_notification",
        "save_memory", "call_service",
    )
)
# Tool LOCALI del CLI sempre vietati (il modello non deve toccare shell/fs del
# container addon); i tool mcp__hiris__* NON sono qui e restano permessi.
_LOCAL_TOOLS_DENY = "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,NotebookEdit,NotebookRead,Task"

_CHAT_MCP_CONFIG_PATH: "str | None" = None
_CHAT_TOOLS = _DEFAULT_CHAT_TOOLS


def build_mcp_config(mcp_url: str) -> dict:
    """MCP interno (2A) su loopback, SENZA auth: nessun header Authorization
    né X-HIRIS-Internal-Token nella config passata a `claude --mcp-config`."""
    return {"mcpServers": {"hiris": {"type": "http", "url": mcp_url}}}


def configure_chat_mcp() -> "str | None":
    """Chiamato una volta all'avvio: scrive l'mcp-config (path da
    HIRIS_AGENT_MCP_CONFIG_PATH, default /tmp/hiris-mcp.json) puntando
    all'MCP interno di 2A (default http://127.0.0.1:8199/mcp) e ritorna il
    path (settando anche i global). L'MCP e' senza auth (loopback-only) quindi
    il file non contiene segreti, ma lo si scrive comunque con permessi 0600
    per prudenza."""
    global _CHAT_MCP_CONFIG_PATH, _CHAT_TOOLS
    mcp_url = os.environ.get("HIRIS_AGENT_MCP_URL", "http://127.0.0.1:8199/mcp")
    _CHAT_TOOLS = os.environ.get("HIRIS_AGENT_CHAT_TOOLS", _DEFAULT_CHAT_TOOLS)
    path = os.environ.get("HIRIS_AGENT_MCP_CONFIG_PATH", "/tmp/hiris-mcp.json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(build_mcp_config(mcp_url), fh)
    if os.name != "nt":
        os.chmod(path, 0o600)
    _CHAT_MCP_CONFIG_PATH = path
    log.info("chat MCP configurato: url=%s tools=%d", mcp_url, len(_CHAT_TOOLS.split(",")))
    return path


def _chat_claude_args(system: str, user: str, model: str,
                      mcp_config_path: "str | None", tools: str) -> list:
    args = ["claude", "-p", user, "--model", model,
            "--system-prompt", system,
            "--exclude-dynamic-system-prompt-sections",
            "--disallowedTools", _LOCAL_TOOLS_DENY,
            "--permission-mode", "default", "--output-format", "json"]
    if mcp_config_path:
        args += ["--mcp-config", mcp_config_path, "--strict-mcp-config",
                 "--allowedTools", tools]
    return args

def parse_decision(text: str) -> dict:
    """Decisione del runner nella forma che viaggia sulla reasoning API.

    Consolidamento 1.4: qui NON c'e' piu' un parser. C'e' l'unico parser
    (`watcher.reasoner.parse_decision`) piu' un adattatore di forma: il
    ragionatore ritorna una `Decision` (dataclass), la reasoning API vuole un
    dizionario `{verdict, severity, message, action}` -- `asdict` e' l'intera
    conversione, i campi coincidono uno a uno.

    Il comportamento in caso di dubbio e' dichiarato qui, non ereditato:
    `default_verdict="falso_positivo"` (fail-closed). Questa Decisione
    attraversa la rete e viene applicata da `_execute_decision` (server.py),
    che sul verdetto e' gia' fail-closed; il runner si allinea a monte, cosi'
    una risposta che non si capisce non chiede mai di agire sulla casa.
    `default_severity="info"` per lo stesso motivo: nel dubbio il livello piu'
    basso. La Sentinella in-process dichiara l'opposto ("anomalia"), e sta
    tutto scritto nella docstring del ragionatore."""
    return asdict(_reasoner.parse_decision(
        text, default_severity="info",
        default_verdict=_reasoner.VERDICT_FALSE_POSITIVE))


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
    """Chat-via-abbonamento: risponde come HIRIS con tool HA reali (via MCP
    interno 2A) quando configurato. Fail-safe: mode!=live -> mock; su errore
    torna sempre una {"reply": <str>}."""
    context = job.get("context") or {}
    history = context.get("history") or []
    system_prompt = context.get("system_prompt") or ""
    if mode != "live":           # fail-safe: qualunque valore != "live" = mock
        return {"reply": "[mock] risposta di prova"}
    system, user = prompts.build_chat_messages(system_prompt, history)
    model = os.environ.get("HIRIS_AGENT_CHAT_MODEL", "sonnet")
    argv = _chat_claude_args(system, user, model, _CHAT_MCP_CONFIG_PATH, _CHAT_TOOLS)
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
    if (job or {}).get("kind") == "chat":
        return _reason_chat(job, mode)
    snapshot = (job.get("context") or {}).get("snapshot", {})
    if mode != "live":            # fail-safe: any non-"live" value = mock (no spend)
        return {"verdict": "anomalia", "severity": "info",
                "message": "[mock] revisione olistica", "action": None}
    prompt = prompts.build_holistic_prompt(snapshot)
    model = os.environ.get("HIRIS_AGENT_MODEL", "sonnet")
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", model,
             "--disallowedTools",
             "Bash,Read,Write,Edit,WebFetch,WebSearch,Glob,Grep,NotebookEdit,NotebookRead,Task",
             "--permission-mode", "default", "--output-format", "json"],
            capture_output=True, text=True, timeout=300, env=_safe_subprocess_env())
        if proc.returncode != 0:
            log.warning("claude rc=%s: %s", proc.returncode, proc.stderr[:300])
            return {"verdict": "falso_positivo", "severity": "info",
                    "message": "[errore runner]", "action": None}
        try:
            data = json.loads(proc.stdout)
            text = data.get("result") or ""
        except (ValueError, TypeError):
            text = proc.stdout
        return parse_decision(text)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        log.warning("claude non eseguibile: %s", type(exc).__name__)
        return {"verdict": "falso_positivo", "severity": "info",
                "message": "[runner non disponibile]", "action": None}

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
    configure_chat_mcp()
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
