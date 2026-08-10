"""Runner hiris-agent: polla la coda di ragionamento HIRIS e ragiona (mock|live).

Porta in-addon del runner del gateway esterno (hiris-mcp-gateway/agent/runner.py).
L'internal token (env INTERNAL_TOKEN) resta usato per l'HTTP verso la reasoning
API (`/api/reasoning/claim` e `/api/reasoning/submit`).

NB (Fetta E2 Task 3): il percorso `claude --mcp-config` verso l'MCP interno
(Piano 2A, hiris/app/mcp/) e' uscito insieme al server che serviva -- era il
terzo catalogo di strumenti della mappa del prodotto, e ora MCP non e' piu'
servito a Claude. `_reason_chat` sotto quindi ragiona SENZA STRUMENTI: non
puo' guardare la casa in questo momento ne' salvare o richiamare ricordi, e
non puo' controllarla.

fetta "il ponte riceve il nucleo" (parita' A, Task 2): questa nota diceva
«ragiona in puro testo, senza poter leggere o controllare la casa». La prima
meta' e' diventata falsa: il job di chat porta ora anche `contesto`, la
STESSA stringa che il ramo sincrono passa al runner
(`handlers_chat.componi_contesto_chat`: nucleo + sessioni precedenti), e
`_reason_chat` la passa a `prompts.build_chat_messages`. Il modello quindi
LEGGE una fotografia della casa, presa quando il messaggio e' stato accodato;
cio' che continua a non poter fare e' guardarla ADESSO e agire su di essa.
Gli strumenti restano fuori: li riattacca la fetta B
(docs/superpowers/plans/2026-08-10-il-ponte-riceve-gli-strumenti.md).

fetta "il ponte riceve gli strumenti" (parita' B, Task 3): li ha riattaccati.
Le due note qui sopra sono ora vere solo per il ramo di DEGRADO. Il ponte
chiede alla rotta `POST /api/mcp` (Task 1) se i quattro strumenti ci sono
(`sonda_strumenti`), e da quell'UNICO booleano discendono insieme il prompt
(`prompts.build_chat_messages(strumenti_attivi=...)`) e l'argv
(`_chat_claude_args(strumenti_attivi=..., mcp_config=...)`): non esistono due
decisioni da tenere allineate. Quando la sonda dice di si', il modello puo'
guardare la casa ADESSO e salvare o richiamare ricordi, coi nomi che MCP gli
serve (`mcp__hiris__cerca`, ...). Quando dice di no -- ed erano attesi -- il
prompt torna a negarli e la `reply` lo dichiara ANCHE all'utente, in una riga
premessa: mai una risposta che sembra normale.

Cio' che continua a non poter fare, e che nessuna fetta di questo ramo cambia:
AGIRE. Gli strumenti sono quattro e nessuno tocca Home Assistant -- HIRIS
conosce e non agisce (hiris/app/casa/strumenti.py)."""
import asyncio, json, logging, os, subprocess, time
from dataclasses import dataclass, field
import httpx
from . import prompts
from ..casa.strumenti import STRUMENTI_CONOSCENZA

log = logging.getLogger("hiris.agent")

# Tool LOCALI del CLI sempre vietati (il modello non deve toccare shell/fs del
# container addon).
#
# fetta "il ponte riceve gli strumenti" (parita' B, Task 3): questa stringa NON
# guadagna `ToolSearch`, e l'assenza e' deliberata. La CLI inserisce un
# passaggio `ToolSearch` per RISOLVERE gli schemi degli strumenti MCP (progetto
# 3.4/5): vietarlo qui renderebbe i quattro strumenti visibili nell'elenco e
# IRRAGGIUNGIBILI -- il modo peggiore di non averli, perche' il prompt li
# afferma e la chiamata non arriva mai. E' esattamente il genere di stringa che
# qualcuno "completa" leggendo l'elenco: non si completa.
_LOCAL_TOOLS_DENY = "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,NotebookEdit,NotebookRead,Task"


# -- fetta "il ponte riceve gli strumenti" (parita' B, Task 3): L'INTERRUTTORE -
# Da qui in giu' vive un solo booleano. Lo decide `sonda_strumenti` un istante
# prima che si componga qualsiasi cosa, e alimenta INSIEME il prompt
# (`prompts.build_chat_messages(strumenti_attivi=...)`) e l'argv
# (`_chat_claude_args(strumenti_attivi=...)`), nella stessa funzione e a due
# righe di distanza (`_reason_chat`). Non esistono due decisioni da tenere
# allineate: e' l'unica difesa strutturale contro il difetto numero uno di
# questo prodotto -- un prompt che promette capacita' che l'invocazione non da'.
# L'invariante e' pinnato NEI DUE VERSI in tests/test_strumenti_al_ponte.py:
# `--mcp-config` nell'argv  <=>  `_GUIDA_CON_STRUMENTI` nel system.


def _nome_server_mcp() -> str:
    """Il nome con cui il server MCP si presenta alla CLI, dall'UNICA fonte.

    L'import e' DIFFERITO -- dentro la funzione e non in cima al file -- per un
    motivo misurato, non per stile: `api/handlers_chat.py` importa `modello_cli`
    da QUESTO modulo, e `api/handlers_mcp.py` importa `handlers_chat`. Un import
    in cima chiude il cerchio e rompe l'avvio: verificato prima di scrivere
    questa riga, `ImportError: cannot import name 'modello_cli' from partially
    initialized module 'hiris.app.agent.runner' (most likely due to a circular
    import)`.

    Ricopiare "hiris" qui sarebbe il secondo posto da tenere allineato, e non un
    posto qualunque: da questo nome discende il prefisso `mcp__hiris__` che
    finisce sia in `--allowedTools` sia nel TESTO del prompt che il modello
    legge. Due copie divergerebbero in silenzio, e il sintomo sarebbe un modello
    che chiama nomi che non esistono."""
    from ..api.handlers_mcp import NOME_SERVER_MCP
    return NOME_SERVER_MCP


def nomi_mcp() -> tuple[str, ...]:
    """I quattro nomi che il modello vede DAVVERO, derivati dal catalogo.

    Attraverso MCP la CLI prefissa ogni strumento col nome del server: `cerca`
    diventa `mcp__hiris__cerca`, ed e' quello -- non il nome nudo -- cio' che il
    modello legge nell'elenco e cio' che `--allowedTools` deve permettere.

    Si DERIVA da `STRUMENTI_CONOSCENZA`: quattro stringhe scritte a mano qui
    sarebbero il SECONDO catalogo, l'errore che l'intera fetta E2 e' esistita
    per chiudere (tre cataloghi divergenti della stessa cosa). Cosi' uno
    strumento che entra o esce da `casa/strumenti.py` arriva qui da solo.

    E' una funzione e non una costante di modulo per la stessa ragione
    dell'import differito qui sopra: il prefisso ha bisogno del nome del server,
    che a import-time non si puo' ancora leggere."""
    prefisso = f"mcp__{_nome_server_mcp()}__"
    return tuple(f"{prefisso}{d['name']}" for d in STRUMENTI_CONOSCENZA)


def config_mcp(base_url: str, token: str) -> str:
    """La voce `--mcp-config` del ponte: una STRINGA JSON, mai un file.

    Tre scelte, tutte deliberate:

    (1) **stringa e non file.** La CLI accetta `--mcp-config` sia come percorso
        sia come stringa JSON (`claude --help`: «Load MCP servers from JSON
        files or strings»). Il vecchio disegno (Piano 2A, uscito con la fetta
        E2) scriveva un file 0600 perche' la sua config NON conteneva segreti;
        questa si', e una stringa non resta su disco. **Il residuo e'
        dichiarato e non nascosto**: il token diventa visibile nell'`argv` del
        processo dentro il container (decisione C.3.5 del progetto, consegnata
        alla fase sicurezze). Cio' che invece NON deve succedere e' che finisca
        in un log: per questo `_logga_init` logga nome+stato dei server e mai
        l'evento intero, e per questo nessun ramo di `_reason_chat` stampa
        l'argv.
    (2) **`X-Requested-With` oltre al token.** Il token da solo basterebbe --
        `csrf_middleware` esenta chi ne porta uno valido -- ma cosi' la rotta
        dipenderebbe da UN SOLO ramo di UN SOLO middleware. Mandandoli entrambi
        passa da qualunque dei due sopravviva (decisione A.3; entrambi i rami
        sono pinnati in tests/test_rotta_mcp.py).
    (3) **il nome del server viene da `_nome_server_mcp()`**, non da una
        stringa scritta qui: e' lo stesso nome da cui discende il prefisso dei
        quattro strumenti."""
    return json.dumps({
        "mcpServers": {
            _nome_server_mcp(): {
                "type": "http",
                "url": f"{(base_url or '').rstrip('/')}/api/mcp",
                "headers": {
                    "X-HIRIS-Internal-Token": token,
                    "X-Requested-With": "hiris-mcp",
                },
            },
        },
    }, ensure_ascii=False)


REDATTO = "***"


def reda_segreti(testo: str, *segreti: str) -> str:
    """Il token fuori da tutto cio' che esce dal sottoprocesso.

    fetta "il ponte riceve gli strumenti" (parita' B, Task 3, fix round 1,
    Important 2). **Prima di questo task era innocuo**: l'argv del ponte non
    conteneva segreti, quindi qualunque cosa la CLI riecheggiasse poteva essere
    loggata e mostrata cosi' com'era. Da oggi il token interno viaggia dentro
    `--mcp-config`, ed e' esattamente il genere di stringa che una CLI ripete
    quando rifiuta o non riesce a connettere un server MCP:

        claude rc=1 stderr='Error: failed to connect to MCP server from
        --mcp-config {"mcpServers": {... "X-HIRIS-Internal-Token": "<il token>"}}'

    Quello stderr finiva nel log dell'add-on -- cioe' nel file che si incolla in
    una segnalazione -- e, senza un dettaglio strutturato da cui ricavare la
    causa, anche NELLA REPLY che l'utente legge in chat.

    Si reda in UN punto solo, appena il sottoprocesso ha risposto, PRIMA che
    qualunque ramo guardi quei due canali: da li' in giu' non esiste piu' una
    copia grezza da dimenticare. Redigere in quattro punti (il log, il
    dettaglio, la coda del flusso incompleto, il testo del risultato) sarebbe
    stato quattro cose da tenere allineate -- e la quinta, aggiunta domani,
    sarebbe uscita in chiaro.

    Un segreto vuoto si salta: `"".replace("", "***")` sostituirebbe ogni
    posizione della stringa."""
    for segreto in segreti:
        if segreto:
            testo = testo.replace(segreto, REDATTO)
    return testo


def sonda_strumenti(client, base_url: str, headers: dict,
                    *, job_id=None) -> tuple[bool, str]:
    """Difesa (1) del progetto: gli strumenti ci sono DAVVERO, in questo turno?

    Un `POST /api/mcp` con `tools/list` sullo STESSO `httpx.Client` e con gli
    STESSI header del claim: loopback, ~1 ms, zero token del modello. E' cio'
    che permette di decidere il prompt e l'argv insieme, PRIMA di spendere un
    turno -- invece di scoprire a risposta arrivata che il modello aveva
    strumenti promessi e non serviti.

    Restituisce `True` **solo** se la risposta porta tutti e quattro i nomi
    attesi. Il 200 non basta, e non e' un dettaglio: la rotta risponde 200 anche
    con gli archivi assenti (l'errore sta DENTRO il risultato della singola
    chiamata, non nello stato HTTP), quindi una sonda che si accontentasse del
    codice non proverebbe niente di cio' che dice di provare.

    Non solleva MAI: connessione rifiutata, timeout, JSON malformato, corpo
    inatteso diventano tutti `False` + un motivo leggibile. Il ponte non deve
    cadere perche' una difesa non ha risposto -- degraderebbe da "risposta senza
    strumenti" a "nessuna risposta", che e' peggio.

    **Silenzio dichiarato (1) della fetta**: ogni `False` produce un
    `log.warning` che nomina il motivo e il `job_id`. Il motivo non contiene mai
    il token: gli header non si loggano e non rientrano nel messaggio, e della
    risposta si stampa solo il codice o i nomi mancanti."""
    attesi = {d["name"] for d in STRUMENTI_CONOSCENZA}
    url = f"{(base_url or '').rstrip('/')}/api/mcp"

    def _no(motivo: str) -> tuple[bool, str]:
        log.warning(
            "sonda degli strumenti fallita (job_id=%s): %s -- questo turno del "
            "ponte va SENZA strumenti, il prompt torna a negarli e la reply lo "
            "dichiara all'utente", job_id, motivo)
        return False, motivo

    try:
        risposta = client.post(
            url, headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            timeout=15)
    except Exception as exc:
        # `Exception` e non le sole eccezioni di httpx: il chiamante puo'
        # passare qualunque client, e una difesa che solleva non e' una difesa.
        return _no(f"{url} non ha risposto ({type(exc).__name__}: {exc})")

    codice = getattr(risposta, "status_code", None)
    if codice != 200:
        return _no(f"{url} ha risposto {codice} invece di 200 (autenticazione, "
                   f"o rotta non registrata)")
    try:
        corpo = risposta.json()
    except Exception as exc:
        return _no(f"{url} ha risposto 200 ma il corpo non e' JSON "
                   f"({type(exc).__name__}: {exc})")

    voci = ((corpo or {}).get("result") or {}).get("tools")
    if not isinstance(voci, list):
        errore = (corpo or {}).get("error")
        return _no(f"{url} ha risposto 200 ma senza result.tools "
                   f"(error={errore!r})")
    trovati = {v.get("name") for v in voci if isinstance(v, dict)}
    mancanti = attesi - trovati
    if mancanti:
        return _no(f"tools/list non porta {sorted(mancanti)}: il ponte avrebbe "
                   f"strumenti a meta', e il prompt li afferma tutti e quattro")
    return True, ""


def _chat_claude_args(system: str, user: str, model: str, *,
                      strumenti_attivi: bool = False,
                      mcp_config: str = "") -> list:
    """L'argv del ponte.

    fetta "il ponte riceve gli strumenti" (parita' B, Task 2): il formato
    della risposta passa da `json` a `stream-json --verbose`, e NON e' un
    dettaglio di forma. Con `--output-format json` il fallimento del server
    MCP e' INVISIBILE: verificato dal vivo (docs/design/
    2026-08-10-parita-ponte-chat.md, 3.4/6) puntando la config a un comando
    inesistente, la CLI risponde `is_error: false`, `subtype: "success"` e
    NESSUN campo dice che gli strumenti non c'erano. Solo `stream-json
    --verbose` porta, nell'evento `{"type": "system", "subtype": "init"}` e
    PRIMA del primo token, `mcp_servers: [{"name": ..., "status":
    "connected"|"failed"}]` e la lista `tools` risolta.

    `--verbose` e' OBBLIGATORIO: senza, la CLI non emette gli eventi
    intermedi e l'`init` non arriva mai.

    fetta "il ponte riceve gli strumenti" (parita' B, Task 3): `strumenti_attivi`
    e' la META' ARGV dell'interruttore unico -- l'altra meta' e' la guida del
    prompt, e le due si leggono dalla stessa variabile in `_reason_chat`. Con
    `True` si aggiungono tre opzioni, e nessuna e' facoltativa:

    - `--mcp-config <stringa>`: la voce del server (vedi `config_mcp`);
    - `--strict-mcp-config`: senza, la CLI userebbe ANCHE i server MCP
      dell'ambiente, che non sono nostri -- il modello si troverebbe strumenti
      che HIRIS non gli ha dato e che il prompt non nomina;
    - `--allowedTools <i quattro nomi>`: i nomi PREFISSATI di `nomi_mcp()`,
      derivati dal catalogo. Senza, gli strumenti sarebbero visibili e non
      permessi.

    Con `False` l'argv e' ESATTAMENTE quello di prima di questo task: e' il ramo
    di degrado, e deve restare byte per byte quello che il prompt senza
    strumenti descrive."""
    argv = ["claude", "-p", user, "--model", model,
            "--system-prompt", system,
            "--exclude-dynamic-system-prompt-sections",
            "--disallowedTools", _LOCAL_TOOLS_DENY,
            "--permission-mode", "default",
            "--output-format", "stream-json", "--verbose"]
    if strumenti_attivi:
        argv += ["--mcp-config", mcp_config,
                 "--strict-mcp-config",
                 "--allowedTools", ",".join(nomi_mcp())]
    return argv


def modello_cli(modello_risolto: str) -> str:
    """Traduce il modello GIA' RISOLTO della chat (`resolve_model`, che puo'
    restituire un modello di QUALUNQUE provider configurato in
    `provider_models` -- claude, openai, openrouter) in un alias della CLI
    `claude`, l'unica cosa con cui questo ponte parla (solo abbonamento, mai
    API a consumo -- vedi `_SUBPROCESS_ENV_DENYLIST` sopra).

    fetta "il ponte riceve il nucleo" (parita' A, Task 4): passare un modello
    non-Anthropic (es. `gpt-4o`) a `claude --model` fa fallire OGNI turno con
    rc!=0, e l'utente legge solo `[errore runner rc=...]` senza il perche'.
    Si traduce quindi nell'alias con meno modi di essere rifiutato
    (`sonnet`/`opus`/`haiku` -- quello che su un abbonamento segue il modello
    corrente del piano, non un nome di modello puntuale), confronto
    case-insensitive sul nome gia' risolto. Un modello che non contiene
    nessuno dei tre alias non fallisce muto: e' il silenzio dichiarato ②
    della fetta, un `log.warning` che nomina il valore configurato e dice
    perche' si ricade su 'sonnet' -- mai un pass silenzioso."""
    nome = (modello_risolto or "").lower()
    if "opus" in nome:
        return "opus"
    if "haiku" in nome:
        return "haiku"
    if "sonnet" in nome:
        return "sonnet"
    log.warning(
        "modello configurato per la chat (%r) non e' un alias Claude "
        "riconosciuto (ne' opus, ne' haiku, ne' sonnet): il ponte parla "
        "SOLO con la CLI dell'abbonamento Claude Max, non puo' inoltrarlo "
        "a un provider diverso -- ricado su 'sonnet'",
        modello_risolto)
    return "sonnet"


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

# -- fetta "il ponte riceve gli strumenti" (parita' B, Task 2): la lettura del
# flusso, UNA sola ------------------------------------------------------------
# `--output-format stream-json` non restituisce un oggetto JSON ma NDJSON: una
# riga per evento. Cambiare formato riscrive quindi il parsing di OGNI risposta
# del ponte, rami d'errore inclusi -- ed e' il motivo per cui questo pezzo sta
# da solo, PRIMA degli strumenti: uno `stream-json` sbagliato e un MCP che non
# parte, nello stesso commit, sarebbero indistinguibili.
#
# `leggi_flusso` e' l'UNICA strada di lettura: non affianca il vecchio parsing,
# lo sostituisce. `_reason_chat` la chiama una volta sola, PRIMA di guardare il
# returncode, e tutti e cinque i suoi esiti (rc!=0, testo, flusso senza
# risultato, testo vuoto, CLI non eseguibile) si decidono su quell'unico esito.
# Due strade -- una per il vecchio formato e una per il nuovo -- sarebbero la
# biforcazione che questo task esiste per evitare.
#
# La funzione e' PURA: nessun subprocess, nessuna rete, nessun log. E' cio' che
# la rende provabile senza la CLI (tests/test_flusso_stream_json.py).

# Il sentinella del silenzio dichiarato (3) della fetta. Come gli altri tre del
# ponte, e' anche in `chat_store._TOXIC_ASSISTANT_PREFIXES`: senza, finirebbe
# in chat_history.db e tornerebbe al modello a ogni turno successivo -- difetto
# gia' trovato dal vivo e riparato una volta su questo ramo.
_SENTINELLA_FLUSSO_INCOMPLETO = "[flusso incompleto]"

# fetta "il ponte riceve gli strumenti" (parita' B, Task 3), difesa (3) del
# progetto: la riga rivolta ALL'UTENTE quando gli strumenti erano attesi e la
# sonda non li ha trovati. Il degrado si dichiara dove l'utente guarda, non solo
# in un log che nessuno legge -- «mai una risposta che sembra normale».
#
# Perche' NON e' in `chat_store._TOXIC_ASSISTANT_PREFIXES` come gli altri cinque
# sentinella: quelli SOSTITUISCONO la risposta (non c'e' niente da conservare),
# questa la PRECEDE -- sotto c'e' una risposta vera, composta sul nucleo e sulla
# conversazione. Filtrare il turno intero cancellerebbe dalla cronologia una
# risposta legittima, che e' il difetto opposto e altrettanto grave.
#
# Riserva 2 del progetto (sezione D): il terzo stato -- "strumenti assenti IN
# QUESTO TURNO" -- NON ha un terzo testo di prompt. `_GUIDA_SENZA_STRUMENTI` e'
# gia' vera anche qui; cio' che distingue il terzo stato dal secondo e' proprio
# questa riga.
AVVISO_STRUMENTI_ASSENTI = (
    "In questo turno non ho potuto usare gli strumenti per guardare la casa: "
    "rispondo con cio' che so dal nucleo e dalla conversazione.")


@dataclass
class EsitoFlusso:
    """Cio' che si ricava da uno stdout `stream-json`.

    - `testo`: il campo `result` dell'evento finale `{"type": "result"}`;
    - `init`: l'evento `{"type": "system", "subtype": "init"}` INTERO (o
      `None`). Porta `mcp_servers` e la lista `tools` risolta: in questo task
      si logga soltanto -- ci decidera' sopra il Task 4, e per farlo gli serve
      il dato intero, non un riassunto;
    - `usage`: il blocco `usage` del risultato (o `{}`) -- la misura che chiude
      la domanda aperta 2 (costo del prefisso) dopo la prima settimana di UAT,
      invece di lasciarla a un'opinione;
    - `righe_saltate`: quante righe non erano JSON. Una riga illeggibile si
      salta e si CONTA, non fa cadere il flusso: la CLI puo' scrivere una riga
      di rumore senza che la risposta vada persa, ma il fatto non sparisce;
    - `righe_lette`: quante righe non vuote sono arrivate (distingue un flusso
      VUOTO da un flusso pieno di rumore);
    - `risultato`: l'evento finale grezzo, o `None`. La sua ASSENZA e' il
      silenzio dichiarato (3) della fetta e non deve mai diventare una stringa
      vuota in silenzio: sarebbe indistinguibile da "il modello non ha risposto
      niente"."""

    testo: str = ""
    init: dict | None = None
    usage: dict = field(default_factory=dict)
    righe_saltate: int = 0
    righe_lette: int = 0
    risultato: dict | None = None
    num_turni: int | None = None

    @property
    def risultato_presente(self) -> bool:
        """False = flusso troncato, processo ucciso a meta', o formato cambiato
        da un aggiornamento della CLI. Chi legge DEVE dichiararlo."""
        return self.risultato is not None


def leggi_flusso(stdout: str) -> EsitoFlusso:
    """Legge l'NDJSON di `claude --output-format stream-json --verbose`.

    Non solleva mai: ogni modo di essere malformato (riga non-JSON, JSON che
    non e' un oggetto, flusso vuoto, flusso senza evento finale) diventa un
    campo dell'`EsitoFlusso`, mai un'eccezione che risale a `_reason_chat`."""
    esito = EsitoFlusso()
    for riga in (stdout or "").splitlines():
        riga = riga.strip()
        if not riga:
            continue
        esito.righe_lette += 1
        try:
            evento = json.loads(riga)
        except (ValueError, TypeError):
            esito.righe_saltate += 1
            continue
        if not isinstance(evento, dict):
            # JSON valido ma non un evento (una lista, un numero): stessa sorte
            # di una riga illeggibile -- si conta e si va avanti.
            esito.righe_saltate += 1
            continue
        tipo = evento.get("type")
        if tipo == "system" and evento.get("subtype") == "init":
            if esito.init is None:   # il PRIMO init: arriva prima del primo token
                esito.init = evento
        elif tipo == "result":
            esito.risultato = evento  # l'ULTIMO result e' quello finale
    risultato = esito.risultato or {}
    testo = risultato.get("result")
    esito.testo = testo if isinstance(testo, str) else ""
    uso = risultato.get("usage")
    esito.usage = uso if isinstance(uso, dict) else {}
    # `num_turns` sta in cima all'evento `result`, non dentro `usage` (verificato
    # sul flusso vero): si legge di la', con `usage` come ripiego.
    turni = risultato.get("num_turns")
    if turni is None:
        turni = esito.usage.get("num_turns")
    esito.num_turni = turni if isinstance(turni, int) else None
    return esito


def _logga_init(esito: EsitoFlusso, job_id) -> None:
    """L'`init` letto e loggato, ma NON ancora agito (Task 2, Step 5).

    In QUESTO task il valore atteso e' la lista vuota: nessun server MCP e'
    configurato, quindi `mcp_servers` e' `[]` e fra i `tools` non c'e' nessun
    `mcp__hiris__*`. Loggarlo adesso e' cio' che rende il Task 4 una riga di
    decisione invece di un secondo lavoro di parsing -- ed e' la prima misura
    utile quando la build girera' sull'add-on vero.

    Si logga il nome e lo stato di ogni server, non l'evento intero: la
    `--mcp-config` porta gli header di autenticazione, e un `%r` generoso e' il
    modo classico di far finire un token nel log."""
    if esito.init is None:
        log.warning(
            "flusso stream-json senza evento system/init (job_id=%s): o "
            "--verbose non e' arrivato alla CLI, o il formato e' cambiato. In "
            "questo task non c'e' nessun server MCP da controllare, ma dal "
            "Task 4 e' l'informazione su cui si decide se gli strumenti ci "
            "sono davvero", job_id)
        return
    server = [{"name": s.get("name"), "status": s.get("status")}
              for s in (esito.init.get("mcp_servers") or [])
              if isinstance(s, dict)]
    strumenti = esito.init.get("tools")
    log.info("init del ponte (job_id=%s): mcp_servers=%s, strumenti risolti=%d",
             job_id, server,
             len(strumenti) if isinstance(strumenti, list) else 0)


def _logga_uso(esito: EsitoFlusso, job_id) -> None:
    """La misura che chiudera' la domanda aperta 2 (Task 2, Step 4).

    Non e' telemetria e non esce dall'add-on: e' una riga di log per turno,
    l'unico modo perche' "quanto costa il prefisso" smetta di essere
    un'opinione dopo la prima settimana di UAT. Solo conteggi: nessun valore di
    prompt, nessun testo di risposta, nessun segreto."""
    uso = esito.usage
    log.info(
        "uso del ponte (job_id=%s): input_tokens=%s "
        "cache_creation_input_tokens=%s cache_read_input_tokens=%s "
        "output_tokens=%s num_turns=%s",
        job_id, uso.get("input_tokens"), uso.get("cache_creation_input_tokens"),
        uso.get("cache_read_input_tokens"), uso.get("output_tokens"),
        esito.num_turni)


def _reason_chat(job: dict, mode: str, *, client=None, base_url: str = "",
                 headers: dict | None = None) -> dict:
    """Chat-via-abbonamento: risponde come HIRIS CON il contesto della casa --
    il nucleo e le sessioni precedenti che il job porta nella chiave `contesto`
    (fetta "il ponte riceve il nucleo", parita' A, Task 2) -- e, dalla fetta
    "il ponte riceve gli strumenti" (parita' B, Task 3), anche con i QUATTRO
    STRUMENTI, serviti dalla rotta `POST /api/mcp`. Fail-safe: mode!=live ->
    mock; su errore torna sempre una {"reply": <str>}.

    `client`/`base_url`/`headers` sono keyword-only e con default, e i default
    NON sono una comodita' di test: senza di essi non c'e' niente da sondare e
    non c'e' nessun `/api/mcp` a cui puntare la mcp-config, quindi gli strumenti
    non sono nemmeno ATTESI -- il turno vale esattamente quanto valeva prima di
    questo task, senza avvisi e senza righe di degrado. Chi li passa (il solo
    `run_once`, cioe' il percorso di produzione) dichiara con quel gesto che il
    ponte e' configurato per averli: da li' in poi la loro assenza e' un
    guasto, e come tale si dichiara.

    Gli header sono gli STESSI del claim (`run_once` passa i suoi): l'add-on non
    deve avere due modi di autenticarsi verso se' stesso."""
    context = job.get("context") or {}
    history = context.get("history") or []
    system_prompt = context.get("system_prompt") or ""
    if mode != "live":           # fail-safe: qualunque valore != "live" = mock
        return {"reply": "[mock] risposta di prova"}
    # Silenzio dichiarato ① della fetta: un job accodato PRIMA di questo
    # deploy e' stato scritto quando `_enqueue_chat_job` metteva nel context
    # solo `history` + `system_prompt`. Arriva qui senza la chiave `contesto`
    # e non c'e' modo di ricomporla (il runner non ha ne' l'app ne' gli
    # archivi). NON si scrive `context.get("contesto") or ""`: un silenzio non
    # dichiarato e' indistinguibile da un'assenza di problemi, e questo caso
    # limite produce una risposta che al modello -- e all'utente -- sembra
    # normale pur essendo cieca sulla casa. Si distingue la chiave ASSENTE
    # (job legacy: log esplicito) da una chiave presente e vuota (il nucleo
    # non si e' composto: lo dichiara gia' il suo testo, vedi
    # `handlers_chat.componi_contesto_chat`). In entrambi i casi il prompt
    # dice al modello che in questo turno non ha la fotografia della casa
    # (`prompts._CONTESTO_ASSENTE`): il degrado si dichiara anche a valle,
    # non solo in un log che nessuno legge.
    if "contesto" in context:
        contesto = context.get("contesto") or ""
    else:
        log.warning(
            "job di chat senza la chiave 'contesto' (job_id=%s): accodato PRIMA "
            "di questo deploy, quando il ponte non riceveva il nucleo -- verra' "
            "ragionato SENZA la casa, e il prompt lo dichiara al modello",
            (job or {}).get("job_id"))
        contesto = ""
    # fetta "il ponte riceve il nucleo" (parita' A, Task 3): le due
    # impostazioni della chat che sono TESTO di prompt. Stesso trattamento
    # del silenzio ① sopra: un job legacy arriva senza queste due chiavi,
    # col default False/"" -- nessun modificatore, il comportamento di
    # prima di questo task, non un errore.
    restrict_to_home = bool(context.get("restrict_to_home", False))
    response_mode = context.get("response_mode") or ""
    job_id = (job or {}).get("job_id")
    # ── L'INTERRUTTORE UNICO (Task 3, Step 4) ──────────────────────────────
    # Gli strumenti sono ATTESI solo se il chiamante ha passato di che sondarli
    # e di che raggiungerli: senza client o senza base_url non c'e' nessun
    # `/api/mcp` da mettere nella mcp-config, quindi non c'e' nessun guasto da
    # dichiarare -- e' il vecchio comportamento, non un degrado nuovo.
    attesi = client is not None and bool(base_url)
    intestazioni = headers if headers is not None else build_headers()
    if attesi:
        strumenti, _motivo = sonda_strumenti(client, base_url, intestazioni,
                                             job_id=job_id)
    else:
        strumenti = False
    token = intestazioni.get("X-HIRIS-Internal-Token", "")
    mcp_config = config_mcp(base_url, token) if strumenti else ""
    # Le DUE righe che leggono lo stesso booleano, una accanto all'altra. Non
    # esiste un secondo posto in cui il prompt e l'argv possono divergere: se
    # un giorno queste due righe si allontanano, e' li' che rientra il difetto
    # numero uno di questo prodotto.
    system, user = prompts.build_chat_messages(system_prompt, history,
                                               contesto=contesto,
                                               strumenti_attivi=strumenti,
                                               restrict_to_home=restrict_to_home,
                                               response_mode=response_mode)
    # fetta "il ponte riceve il nucleo" (parita' A, Task 4): il modello non
    # e' piu' `HIRIS_AGENT_CHAT_MODEL` (env mai esportata da run.sh --
    # censita fra le "lette e mai esportate": in produzione era SEMPRE
    # "sonnet", qualunque cosa l'utente scegliesse per la chat) ma quello
    # scelto per la chat, gia' risolto e tradotto in alias CLI da
    # `handlers_chat._enqueue_chat_job` (`resolve_model` + `modello_cli`,
    # sopra) prima di entrare nel job. L'`or` qui e' legittimo, non un
    # errore di configurazione mascherato: copre SOLO il job legacy del
    # Task 2 (accodato prima di questo deploy, quando il context non
    # portava affatto la chiave `model`) -- per quel job "sonnet" e'
    # esattamente il comportamento di prima di questo task, non un
    # degrado nuovo, quindi non e' uno dei silenzi dichiarati della fetta.
    model = context.get("model") or "sonnet"
    argv = _chat_claude_args(system, user, model,
                             strumenti_attivi=strumenti, mcp_config=mcp_config)
    # Il degrado dichiarato: gli strumenti erano attesi e non ci sono. Il log
    # l'ha gia' detto (silenzio (1), dentro `sonda_strumenti`); qui si prepara
    # a dirlo anche all'utente, in coda alla risposta che il modello riuscira'
    # comunque a dare sul solo nucleo.
    degrado = attesi and not strumenti
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=300, env=_safe_subprocess_env())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        # Esito (5): il CLI non parte, non c'e' o non finisce in tempo. Resta
        # l'unico ramo che non ha nemmeno uno stdout da leggere.
        log.warning("claude non eseguibile: %s", type(exc).__name__)
        return {"reply": "[runner non disponibile]"}

    # La redazione, PRIMA di qualunque lettura (fix round 1, Important 2): il
    # token viaggia in `--mcp-config` e la CLI lo riecheggia quando il server
    # MCP non parte. Da qui in giu' `proc.stdout`/`proc.stderr` non si usano
    # piu': si usano queste due copie, e non c'e' nessun canale che possa
    # dimenticarsi di redigere. La sostituzione avviene su una stringa JSON e
    # la lascia valida (il token non contiene virgolette: e' generato da
    # `token_interno.secrets.token_urlsafe`).
    stdout = reda_segreti(proc.stdout or "", token)
    stderr = reda_segreti(proc.stderr or "", token)

    # UNA sola lettura del flusso, prima di qualunque ramo: e' cosi' che il
    # ramo d'errore e quello felice non possono divergere nel modo di leggere
    # la stessa risposta.
    esito = leggi_flusso(stdout)
    _logga_init(esito, job_id)   # Step 5: letto e loggato, NON ancora agito
    _logga_uso(esito, job_id)    # Step 4: la misura per la domanda aperta 2
    if esito.righe_saltate:
        # Una riga di rumore non fa cadere il flusso, ma non sparisce: se la
        # CLI cambia formato, il conto sale prima che qualcosa si rompa.
        log.warning(
            "flusso stream-json con %d riga/righe non-JSON saltate su %d "
            "(job_id=%s): la risposta e' stata letta lo stesso, ma il formato "
            "della CLI non e' piu' esattamente quello atteso",
            esito.righe_saltate, esito.righe_lette, job_id)

    if proc.returncode != 0:
        # Esito (1). `claude -p` mette gli errori (auth 401, quota, ecc.) su
        # STDOUT come JSON, non su stderr: la nota vale ancora con stream-json,
        # dove l'errore arriva nell'evento `result` con `is_error: true`. Logga
        # entrambi i canali e prova a estrarre un dettaglio leggibile, per non
        # nascondere la causa dietro un numero.
        log.warning("claude rc=%s stderr=%r stdout=%r", proc.returncode,
                    stderr[:300], stdout[:500])
        risultato = esito.risultato or {}
        dettaglio = (esito.testo or risultato.get("error")
                     or risultato.get("subtype") or "")
        if not dettaglio:
            # Nessun evento finale da cui ricavarlo (processo morto a meta'):
            # meglio il flusso grezzo che un silenzio.
            dettaglio = (stdout or stderr).strip()
        return {"reply":
                f"[errore runner rc={proc.returncode}] {str(dettaglio)[:300]}".strip()}

    if not esito.risultato_presente:
        # Esito (3), IL SILENZIO DICHIARATO della fetta. Il processo e' uscito
        # 0 ma il flusso si e' chiuso senza l'evento finale: troncato, ucciso,
        # o formato cambiato da un aggiornamento della CLI. Restituire "" qui
        # sarebbe indistinguibile da "il modello non ha risposto niente", e
        # restituire il testo parziale degli eventi `assistant` sarebbe peggio:
        # una risposta che SEMBRA normale. Si dichiara nel log e -- come tutti
        # i degradi di questa fetta -- anche all'utente, nel testo della reply.
        log.warning(
            "flusso stream-json chiuso senza evento finale type=result "
            "(job_id=%s, rc=%s): righe lette=%d, righe non-JSON saltate=%d -- "
            "il ponte NON ha una risposta completa e lo dichiara nella reply",
            job_id, proc.returncode, esito.righe_lette, esito.righe_saltate)
        # Quarto canale dello stdout grezzo (introdotto dal Task 2): anche
        # questa coda passa dalla copia redatta, non da `proc.stdout`.
        coda = stdout.strip()[-200:]
        avviso = (
            f"{_SENTINELLA_FLUSSO_INCOMPLETO} In questo turno la risposta si e' "
            "chiusa senza il messaggio finale del modello: quello che e' "
            "arrivato non e' una risposta completa, e non te la presento come "
            "tale. Riprova; se succede a ogni turno, il formato della CLI e' "
            "cambiato e va guardato il log dell'add-on.")
        # Il pezzo grezzo resta nella reply, come faceva il vecchio ramo "JSON
        # non parsabile": e' l'unico modo di diagnosticare dall'interfaccia un
        # cambio di formato durante l'UAT. Compromesso dichiarato: e' brutto da
        # leggere, ma un ramo muto sarebbe peggio.
        return {"reply": f"{avviso} (ultimo pezzo di flusso letto: {coda})"
                if coda else avviso}

    # Esiti (2) e (4): il testo del risultato, oppure il sentinella del vuoto.
    testo = esito.testo.strip()
    if not testo:
        return {"reply": "[vuoto]"}
    if degrado:
        # Solo QUI, e non sugli altri rami: `[errore runner rc=...]`,
        # `[runner non disponibile]`, `[flusso incompleto]` e `[vuoto]` sono
        # gia' dichiarazioni di guasto, e sono riconosciuti PER PREFISSO da
        # `chat_store._TOXIC_ASSISTANT_PREFIXES` -- anteporre qualcosa li
        # renderebbe invisibili a quel filtro, e tornerebbero al modello a ogni
        # turno successivo. Questo caso e' l'opposto: sotto c'e' una risposta
        # vera, che va conservata.
        return {"reply": f"{AVVISO_STRUMENTI_ASSENTI}\n\n{testo}"}
    return {"reply": testo}

def reason(job: dict, mode: str, *, client=None, base_url: str = "",
           headers: dict | None = None) -> dict:
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
        # fetta "il ponte riceve gli strumenti" (parita' B, Task 3): il client e
        # la base_url del giro passano di qui SENZA essere ricostruiti. La sonda
        # degli strumenti deve girare sullo STESSO `httpx.Client` del claim e
        # con gli STESSI header: un secondo client (o un secondo modo di
        # autenticarsi) sarebbe un secondo posto da tenere allineato.
        return _reason_chat(job, mode, client=client, base_url=base_url,
                            headers=headers)
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
    decision = reason(job, mode, client=client, base_url=base_url,
                      headers=headers)
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
