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
import asyncio, json, logging, os, re, subprocess, time
from dataclasses import asdict, dataclass
from typing import Optional
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


# fetta E3 Task 7: l'interpretazione della risposta del modello viveva in
# `watcher.reasoner` ("Consolidamento 1.4: unica implementazione, non due
# copie divergenti"). La Sentinella (guardiano/ragionatore/esecutore) e' uscita
# per intero in questo task -- ma questo runner (il ponte push del Piano A,
# vivo) restava l'ALTRO chiamante di quel parser, quindi il parser si sposta
# qui con lui invece di sparire. E' di nuovo un'unica implementazione: prima
# c'erano due moduli che si spartivano la stessa funzione (uno la definiva,
# uno la usava), ora ce n'e' uno solo perche' l'altro chiamante non esiste
# piu'.
VERDICT_ANOMALY = "anomalia"
VERDICT_FALSE_POSITIVE = "falso_positivo"
VERDICTS = (VERDICT_ANOMALY, VERDICT_FALSE_POSITIVE)

# Soglia per il testo grezzo riportato come messaggio quando non c'e' nulla da
# interpretare (nessun blocco ```json``` valido nella risposta del modello).
FALLBACK_MESSAGE_MAX = 500

_JSON_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)


@dataclass
class Decision:
    verdict: str            # "anomalia" | "falso_positivo"
    severity: str           # "info" | "warn" | "critico"
    message: str
    action: Optional[dict] = None   # {"domain","service","entity_id","data"} | None


def _parse_decision(text: str, default_severity: str = "info",
                    default_verdict: str = VERDICT_FALSE_POSITIVE) -> Decision:
    """Legge l'ultimo blocco ```json``` della risposta del modello e ne ricava
    una Decision. Non solleva mai.

    `default_verdict` e' il verdetto usato quando la risposta non e'
    interpretabile: nessun blocco json, json non valido, json che non e' un
    oggetto, oppure oggetto senza il campo `verdict`. Sono tutti lo stesso
    caso -- il modello non ha detto cosa pensa. Questo runner ragiona in
    remoto: la Decisione arriva a HIRIS attraverso la rete e (da fetta E3
    Task 4) non viene piu' applicata da nessun esecutore automatico --
    `handle_reasoning_submit` (handlers_reasoning.py) si limita a
    REGISTRARLA con un warning. Il fail-closed (`default_verdict=
    "falso_positivo"`) resta comunque la scelta giusta in caso di dubbio --
    difesa in profondita', anche senza un esecutore a valle.

    Un `default_verdict` fuori da VERDICTS ricade sul piu' prudente
    ("falso_positivo"): un valore inatteso non deve poter aprire la strada
    all'attuazione."""
    if default_verdict not in VERDICTS:
        default_verdict = VERDICT_FALSE_POSITIVE
    m = list(_JSON_RE.finditer(text or ""))
    if m:
        try:
            obj = json.loads(m[-1].group(1))
        except (ValueError, TypeError):
            obj = None
        # Il blocco puo' contenere una lista o uno scalare: senza questa
        # guardia `obj.get` sollevava AttributeError, che non e' fra le
        # eccezioni catturate -- il parsing crashava invece di ricadere sul
        # fallback.
        if isinstance(obj, dict):
            action = obj.get("action")
            return Decision(
                verdict=str(obj.get("verdict") or default_verdict),
                severity=str(obj.get("severity") or default_severity),
                message=str(obj.get("message", "")).strip() or "(nessun messaggio)",
                action=action if isinstance(action, dict) else None,
            )
    return Decision(verdict=default_verdict, severity=default_severity,
                    message=(text or "").strip()[:FALLBACK_MESSAGE_MAX] or "(vuoto)",
                    action=None)


def parse_decision(text: str) -> dict:
    """Decisione del runner nella forma che viaggia sulla reasoning API.

    `_parse_decision` ritorna una `Decision` (dataclass); la reasoning API
    vuole un dizionario `{verdict, severity, message, action}` -- `asdict` e'
    l'intera conversione, i campi coincidono uno a uno. Fail-closed:
    `default_severity="info"`, `default_verdict=VERDICT_FALSE_POSITIVE` --
    nel dubbio il livello piu' basso e nessuna azione richiesta."""
    return asdict(_parse_decision(
        text, default_severity="info",
        default_verdict=VERDICT_FALSE_POSITIVE))


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
