"""Runner hiris-agent: polla la coda di ragionamento HIRIS e ragiona (mock|live).

Porta in-addon del runner del gateway esterno (hiris-mcp-gateway/agent/runner.py).
L'internal token (env INTERNAL_TOKEN) resta usato per l'HTTP verso la reasoning
API (`/api/reasoning/claim` e `/api/reasoning/submit`).

OGGI, in una riga: il ponte LEGGE la casa e la memoria, e da questa fetta puo'
anche AGIRE su di essa -- gli strumenti sono cinque, e il quinto (`esegui`)
chiama un servizio di Home Assistant passando per la porta unica
(`azione/porta.py`), la stessa della chat sincrona. Le note che seguono sono la
STORIA di come ci si e' arrivati, e sono al passato apposta: fino alla review
totale della parita' B la prima di esse affermava al PRESENTE il contrario, ed
era la prima cosa che un lettore di questo file trovava. La riga qui sopra ha
appena smesso a sua volta di dire «e NON agisce» (fetta «comandare», Task 5):
lo stesso difetto, un giro dopo.

STORIA (Fetta E2 Task 3): il percorso `claude --mcp-config` verso l'MCP interno
(Piano 2A, hiris/app/mcp/) usci' insieme al server che serviva -- era il terzo
catalogo di strumenti della mappa del prodotto. Da allora, e fino alla parita'
B, `_reason_chat` ragionava SENZA STRUMENTI: non poteva guardare la casa in quel
momento ne' salvare o richiamare ricordi, e non poteva controllarla.

fetta "il ponte riceve il nucleo" (parita' A, Task 2): questa nota diceva
«ragiona in puro testo, senza poter leggere o controllare la casa». La prima
meta' e' diventata falsa: il job di chat porta ora anche `contesto`, la
STESSA stringa che il ramo sincrono passa al runner
(`handlers_chat.componi_contesto_chat`: nucleo + sessioni precedenti), e
`_reason_chat` la passa a `prompts.build_chat_messages`. Il modello quindi
LEGGE una fotografia della casa, presa quando il messaggio e' stato accodato;
cio' che continua a non poter fare e' guardarla ADESSO e agire su di essa.
Gli strumenti restavano fuori; li ha riattaccati la fetta B
(docs/superpowers/plans/2026-08-10-il-ponte-riceve-gli-strumenti.md), qui sotto.

fetta "il ponte riceve gli strumenti" (parita' B, Task 3): li ha riattaccati.
Le due note qui sopra sono ora vere solo per il ramo di DEGRADO. Il ponte
chiede alla rotta `POST /api/mcp` (Task 1) se gli strumenti ci sono
(`sonda_strumenti`), e da quell'UNICO booleano discendono insieme il prompt
(`prompts.build_chat_messages(strumenti_attivi=...)`) e l'argv
(`_chat_claude_args(strumenti_attivi=..., mcp_config=...)`): non esistono due
decisioni da tenere allineate. Quando la sonda dice di si', il modello puo'
guardare la casa ADESSO, salvare o richiamare ricordi e -- dalla fetta
«comandare» -- far succedere qualcosa in casa, coi nomi che MCP gli
serve (`mcp__hiris__cerca`, ...). Quando dice di no -- ed erano attesi -- il
prompt torna a negarli e la `reply` lo dichiara ANCHE all'utente, in una riga
premessa: mai una risposta che sembra normale.

fetta "il ponte riceve gli strumenti" (parita' B, Task 4): gli stati sono TRE,
non due -- strumenti attivi, strumenti mai attesi, e strumenti attesi e non
arrivati IN QUESTO TURNO. Il terzo nasce quando l'evento `system/init` della CLI
smentisce la sonda (`verifica_init`): li' l'invocazione si BUTTA e se ne
ricompone una senza strumenti, una sola volta. Il terzo stato non ha un terzo
testo di guida -- `_GUIDA_SENZA_STRUMENTI` e' vera anche li' -- e cio' che lo
distingue e' `AVVISO_STRUMENTI_ASSENTI`, la riga che l'utente legge.

fetta "il ponte riceve gli strumenti" (parita' B, Task 5): da qui `ricorda' e'
raggiungibile ANCHE dal ponte, e scrive in `memoria.db` -- il primo effetto
DURATURO che il ponte sappia produrre. Il ramo sincrono lo mostra all'utente
(`handlers_chat.py`, `tools_called`); il ponte no, e con le sicurezze fuori
dall'UAT (decisione del proprietario) quella riga e' l'unica cosa che rende
osservabile una scrittura che non doveva avvenire. `leggi_flusso` la raccoglie
dallo STESSO flusso che gia' legge (nessuna seconda lettura), `_reason_chat`
la mette in `decision["tools_called"]`, nella STESSA forma del ramo sincrono.

fetta "il ponte riceve gli strumenti" (parita' B, Task 6): il ponte ora
manda anche `X-HIRIS-Turno` dentro la `--mcp-config` (`config_mcp`), un
`secrets.token_urlsafe` mintato UNA volta per turno (non per invocazione
della CLI), a prescindere da quante invocazioni il turno finira' per avere
(Task 4). E' il gancio con cui `api/handlers_mcp.py` tiene
il tetto ai giri di strumento per turno (`MAX_GIRI_STRUMENTI = 10`, parita'
col ramo sincrono): il freno che sostituisce un `--max-turns` che la CLI non
ha (verificato su `claude --help`) -- l'unico che l'abbonamento abbia, visto
che `chat_daily_cap` conta i turni accodati e non i giri dentro ciascuno.

Fino alla fetta «comandare» questo docstring si chiudeva su una cosa che il
ponte «continua a non poter fare, e che nessuna fetta di questo ramo cambia:
AGIRE». La fetta l'ha cambiata. Gli strumenti sono cinque e il quinto tocca
Home Assistant (hiris/app/casa/strumenti.py): il ponte agisce quando la sonda
dice di si', esattamente come la chat sincrona, e per la stessa porta. Cio' che
resta vero e' il confine: nessuna autonomia. Ogni esecuzione nasce da una frase
in chat -- non c'e' trigger ne' schedulazione che possa farne partire una."""
import asyncio, json, logging, os, secrets, subprocess, time
from dataclasses import dataclass, field
import httpx
from . import prompts
from ..casa.strumenti import STRUMENTI_CONOSCENZA
from ..chat_store import (PREFISSO_ERRORE_RUNNER, SENTINELLA_FLUSSO_INCOMPLETO,
                          SENTINELLA_MOCK, SENTINELLA_RUNNER_ASSENTE,
                          SENTINELLA_VUOTO)

log = logging.getLogger("hiris.agent")

# Tool LOCALI del CLI sempre vietati (il modello non deve toccare shell/fs del
# container addon).
#
# fetta "il ponte riceve gli strumenti" (parita' B, Task 3): questa stringa NON
# guadagna `ToolSearch`, e l'assenza e' deliberata. La CLI inserisce un
# passaggio `ToolSearch` per RISOLVERE gli schemi degli strumenti MCP (progetto
# 3.4/5): vietarlo qui renderebbe gli strumenti visibili nell'elenco e
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
#
# Task 4: la sonda puo' dire di si' e la CLI fallire lo stesso -- fra i due c'e'
# Node, il parsing della mcp-config e un loopback visto da un altro processo.
# L'evento `system/init` e' l'unico che lo dichiara, e quando smentisce la sonda
# il prompt e' GIA' partito. La risposta non e' una postilla al testo: e'
# rimettere il booleano a `False` e **ricomporre** prompt e argv insieme, una
# volta sola (`verifica_init` + `MAX_INVOCAZIONI_PER_TURNO`). Il tetto e' due
# invocazioni per turno, ed e' asserito.


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
    """I nomi che il modello vede DAVVERO, derivati dal catalogo.

    Attraverso MCP la CLI prefissa ogni strumento col nome del server: `cerca`
    diventa `mcp__hiris__cerca`, ed e' quello -- non il nome nudo -- cio' che il
    modello legge nell'elenco e cio' che `--allowedTools` deve permettere.

    Si DERIVA da `STRUMENTI_CONOSCENZA`: un elenco di stringhe scritto a mano
    qui sarebbe il SECONDO catalogo, l'errore che l'intera fetta E2 e' esistita
    per chiudere (tre cataloghi divergenti della stessa cosa). Cosi' uno
    strumento che entra o esce da `casa/strumenti.py` arriva qui da solo.

    E' una funzione e non una costante di modulo per la stessa ragione
    dell'import differito qui sopra: il prefisso ha bisogno del nome del server,
    che a import-time non si puo' ancora leggere."""
    prefisso = f"mcp__{_nome_server_mcp()}__"
    return tuple(f"{prefisso}{d['name']}" for d in STRUMENTI_CONOSCENZA)


def config_mcp(base_url: str, token: str, id_turno: str = "") -> str:
    """La voce `--mcp-config` del ponte: una STRINGA JSON, mai un file.

    `id_turno` (Task 6 della fetta, facoltativo e vuoto per default) diventa
    l'intestazione `X-HIRIS-Turno` che la CLI ripete su OGNI `tools/call`
    verso `/api/mcp`: e' cosi' che quella rotta sa QUALE turno sta chiamando
    e puo' tenere il tetto ai giri di strumento per turno
    (`api/handlers_mcp.MAX_GIRI_STRUMENTI`) -- il freno che sostituisce un
    `--max-turns` che la CLI non ha (verificato su `claude --help`). **Serve
    solo a contare**: non e' un'autenticazione (quella resta il token qui
    sopra) e non va scambiata per tale -- e' pero' il gancio esatto su cui la
    fase sicurezze potra' innestare il "token per-invocazione di validita'
    pari al turno" che il progetto suggerisce (§3.3), senza dover inventare
    un secondo meccanismo. Il default vuoto (nessuna intestazione aggiunta)
    e' cio' che permette a `test_strumenti_al_ponte.py`/
    `test_agent_runner_inaddon.py` di continuare a chiamare questa funzione
    coi soli due argomenti di sempre: un tetto per-turno non e' niente che
    quei test debbano conoscere.

    **Un'identita' per TURNO, non per invocazione della CLI.** Il chiamante
    (`_reason_chat`, sotto) la conia UNA sola volta per turno, PRIMA di
    sapere se servira' una seconda invocazione (Task 4, `verifica_init`): se
    ne coniasse una diversa a ogni chiamata di `_invoca`, un turno sdoppiato
    finirebbe con due tetti indipendenti invece di uno solo -- il raddoppio
    silenzioso che "un tetto per-turno deve sapere cosa fa quando il turno si
    sdoppia" (Task 6) esiste per escludere. **Oggi la seconda invocazione di
    un turno ritentato riparte SEMPRE senza strumenti** (Task 4: l'`init` ha
    smentito la sonda, e si ricompone `strumenti_attivi=False`), quindi non
    chiama mai `config_mcp` e questa identita' non le arriva comunque -- ma
    e' coniata una volta sola A PRESCINDERE da quel dettaglio, cosi' la
    proprieta' regge anche il giorno in cui una fetta futura ritentasse CON
    gli strumenti ancora attivi.

    Tre scelte sulla config stessa, tutte deliberate:

    (1) **stringa e non file.** La CLI accetta `--mcp-config` sia come percorso
        sia come stringa JSON (`claude --help`: «Load MCP servers from JSON
        files or strings»). Il vecchio disegno (Piano 2A, uscito con la fetta
        E2) scriveva un file 0600 perche' la sua config NON conteneva segreti;
        questa si', e una stringa non resta su disco. **Il residuo e'
        dichiarato e non nascosto**: il token diventa visibile nell'`argv` del
        processo dentro il container (decisione C.3.5 del progetto, consegnata
        alla fase sicurezze). Cio' che invece NON deve succedere e' che finisca
        in un log: per questo `_logga_init` logga nome+stato dei server, la
        versione della CLI e `apiKeySource` -- quattro campi scelti a mano, e
        mai l'evento intero -- e per questo nessun ramo di `_reason_chat`
        stampa l'argv.
    (2) **`X-Requested-With` oltre al token.** Il token da solo basterebbe --
        `csrf_middleware` esenta chi ne porta uno valido -- ma cosi' la rotta
        dipenderebbe da UN SOLO ramo di UN SOLO middleware. Mandandoli entrambi
        passa da qualunque dei due sopravviva (decisione A.3; entrambi i rami
        sono pinnati in tests/test_rotta_mcp.py).
    (3) **il nome del server viene da `_nome_server_mcp()`**, non da una
        stringa scritta qui: e' lo stesso nome da cui discende il prefisso
        degli strumenti."""
    intestazioni = {
        "X-HIRIS-Internal-Token": token,
        "X-Requested-With": "hiris-mcp",
    }
    if id_turno:
        intestazioni["X-HIRIS-Turno"] = id_turno
    return json.dumps({
        "mcpServers": {
            _nome_server_mcp(): {
                "type": "http",
                "url": f"{(base_url or '').rstrip('/')}/api/mcp",
                "headers": intestazioni,
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
    # Dal piu' lungo al piu' corto: una forma che contiene l'altra deve essere
    # sostituita per prima, o la prima passata mangerebbe un pezzo della
    # seconda lasciando in giro il resto.
    for segreto in sorted(set(segreti), key=len, reverse=True):
        if segreto:
            testo = testo.replace(segreto, REDATTO)
    return testo


def forme_del_token(token: str, profondita: int = 2) -> tuple[str, ...]:
    r"""Tutte le forme in cui QUESTO token puo' comparire nell'eco della CLI.

    fetta "il ponte riceve gli strumenti" (parita' B, Task 3, fix round 2).
    La redazione del fix round 1 cercava la forma GREZZA, ma nell'argv il token
    non entra grezzo: entra dentro una stringa JSON (`config_mcp`), quindi
    **JSON-escaped**. Per i token urlsafe le due forme coincidono e la difesa
    sembrava funzionare; per un token che contiene `"` o `\` no, e la
    redazione mancava il bersaglio su tutti e cinque i canali. Riprodotto con
    `token = ab"cd\ef`:

        REPLY: [errore runner rc=1] ... "X-HIRIS-Internal-Token": "ab\\"cd\\ef"

    -- il segreto ricostruibile con un JSON-unescape.

    Che l'opzione `internal_token` possa contenerli non e' un'ipotesi: e' una
    `password` libera in `hiris/config.yaml`, e `token_interno.py` la accetta
    dopo un `.strip()`. Quella validazione ora rifiuta i caratteri di CONTROLLO
    (che rompono l'header), non le virgolette: sono header-safe, e rompevano
    solo la redazione. Questo e' il posto dove quel fronte si chiude.

    **I livelli di annidamento sono DUE, non uno** -- misurato, non stimato:

        profondita' 0  ab"cd\ef            il token come lo teniamo
        profondita' 1  ab\"cd\ef          dentro la stringa JSON di --mcp-config
        profondita' 2  ab\\\"cd\\ef  quando la CLI infila il proprio
                                          messaggio d'errore (che cita la
                                          nostra config) dentro un evento
                                          `stream-json`, cioe' dentro un
                                          SECONDO JSON

    Fermarsi a 1 lasciava scoperti i canali (3) e (5), dove lo stdout grezzo e'
    gia' un JSON che ne contiene un altro. Ci si ferma a 2 perche' oltre non
    esiste un terzo involucro in questa catena: la config sta nell'errore, e
    l'errore sta nell'evento. Il residuo -- un ipotetico terzo annidamento --
    resta possibile solo sul LOG, perche' la `reply` passa da un cancello che
    reda DOPO il parsing, quando il valore e' comunque tornato a profondita' 1.

    Difesa in profondita': vale anche quando la prima difesa regge, perche' le
    difese in profondita' servono esattamente quando la prima cede."""
    if not token:
        return ()
    forme, corrente = [token], token
    for _ in range(profondita):
        corrente = json.dumps(corrente)[1:-1]
        forme.append(corrente)
    viste, uniche = set(), []
    for forma in forme:
        if forma not in viste:
            viste.add(forma)
            uniche.append(forma)
    return tuple(uniche)


def _reda_struttura(valore, *segreti: str):
    """`reda_segreti`, applicata dentro una struttura JSON qualunque
    (dict/list/str/altro), non solo su una stringa.

    fetta "il ponte riceve gli strumenti" (parita' B, Task 5). `tools_called`
    porta l'`input` che il MODELLO ha passato a uno strumento -- per
    `ricorda`, il testo del ricordo -- cioe' testo che noi non controlliamo.
    Il cancello unico in uscita per la reply (`_reply` in `_reason_chat`) vale
    anche per questo canale nuovo: se un giorno un input contenesse per caso
    una delle forme del token (l'utente lo detta a voce a HIRIS e HIRIS lo
    scrive in un `ricorda`, per dire), non deve uscire comunque. Nessuna
    prova nota lo fa succedere oggi: e' difesa in profondita', non una
    riparazione di un buco osservato."""
    if isinstance(valore, str):
        return reda_segreti(valore, *segreti)
    if isinstance(valore, dict):
        return {k: _reda_struttura(v, *segreti) for k, v in valore.items()}
    if isinstance(valore, list):
        return [_reda_struttura(v, *segreti) for v in valore]
    return valore


def _motivo_eccezione(exc: BaseException, token: str | None = None) -> str:
    """Il messaggio di un'eccezione reso stampabile: tipo + testo REDATTO.

    fetta "il ponte riceve gli strumenti" (parita' B, Task 4, nit 1 della
    review del Task 3). Un `log.warning("...: %s", exc)` e' il **settimo
    canale** di perdita del token, e non e' teorico: gli header del claim
    portano `X-HIRIS-Internal-Token`, e con un valore che il protocollo HTTP
    non accetta il client solleva **col valore dentro** (`LocalProtocolError:
    Illegal header value b'...'`, verificato contro un listener vero al fix
    round 2 del Task 3). Fino a oggi quel canale era chiuso da una dipendenza
    scritta in un docstring altrui -- `token_interno.motivo_token_non_valido`
    rifiuta i caratteri di controllo all'avvio -- cioe' da una difesa che sta
    in un altro file e che nessun test legava a questa riga.

    Qui la dipendenza smette di essere l'unica difesa: si passa dalla
    redazione che c'e' gia' (`reda_segreti` su tutte le `forme_del_token`),
    invece di aprire una via nuova. **Il messaggio non si butta**: perdere il
    testo dell'eccezione renderebbe illeggibile il log del giro
    (`run_once errore: HTTPStatusError` non dice quale rotta ne' quale codice),
    e un log che non serve a diagnosticare e' il primo che smette di essere
    letto.

    `token=None` significa "quello di produzione", letto dove lo legge
    `build_headers` -- che e' esattamente il token che i due giri
    (`run_loop`, `main`) mandano nell'header del claim. Chi ne avesse uno
    diverso in mano passa il suo.

    **Dove NON si applica, e perche'**: `sonda_strumenti` continua a mettere
    nel motivo il messaggio grezzo. Non e' una dimenticanza -- vedi la nota
    nel suo docstring: quel comportamento e' pinnato contro un listener vero
    in `tests/test_token_interno.py`, file che questa fetta non tocca."""
    if token is None:
        token = os.environ.get("INTERNAL_TOKEN", "")
    return f"{type(exc).__name__}: {reda_segreti(str(exc), *forme_del_token(token))}"


def sonda_strumenti(client, base_url: str, headers: dict,
                    *, job_id=None) -> tuple[bool, str]:
    """Difesa (1) del progetto: gli strumenti ci sono DAVVERO, in questo turno?

    Un `POST /api/mcp` con `tools/list` sullo STESSO `httpx.Client` e con gli
    STESSI header del claim: loopback, ~1 ms, zero token del modello. E' cio'
    che permette di decidere il prompt e l'argv insieme, PRIMA di spendere un
    turno -- invece di scoprire a risposta arrivata che il modello aveva
    strumenti promessi e non serviti.

    Restituisce `True` **solo** se la risposta porta TUTTI i nomi attesi --
    quelli di `nomi_mcp()`, quindi il catalogo intero, `esegui` compreso. Il 200 non basta, e non e' un dettaglio: la rotta risponde 200 anche
    con gli archivi assenti (l'errore sta DENTRO il risultato della singola
    chiamata, non nello stato HTTP), quindi una sonda che si accontentasse del
    codice non proverebbe niente di cio' che dice di provare.

    Non solleva MAI: connessione rifiutata, timeout, JSON malformato, corpo
    inatteso diventano tutti `False` + un motivo leggibile. Il ponte non deve
    cadere perche' una difesa non ha risposto -- degraderebbe da "risposta senza
    strumenti" a "nessuna risposta", che e' peggio.

    **Silenzio dichiarato (1) della fetta**: ogni `False` produce un
    `log.warning` che nomina il motivo e il `job_id`. Il motivo non nomina mai
    il token: gli header non si loggano e non rientrano nel messaggio, e della
    risposta si stampa solo il codice o i nomi mancanti.

    **Da cosa dipende quella promessa** (fix round 2, e va detto invece che
    sottinteso): il ramo `except` mette nel motivo il messaggio dell'eccezione,
    e con un token che contiene CR/LF/NUL il client HTTP solleva **col valore
    dentro** -- verificato contro un listener vero, `LocalProtocolError: Illegal
    header value b'...'`. La promessa regge perche' un token del genere non
    arriva fin qui: `token_interno.motivo_token_non_valido` lo rifiuta
    all'avvio, lo dichiara nel log e lascia in piedi il rifiuto-per-difetto. Se
    quella validazione sparisse, questo docstring tornerebbe falso.

    Task 4: **questa e' l'unica dipendenza del genere che resta scoperta**, ed
    e' scoperta di proposito. Farla passare da `_motivo_eccezione` (la
    redazione usata per il settimo canale, in `run_once`) chiuderebbe il buco
    da sola -- ma renderebbe rosso
    `tests/test_token_interno.py::test_i_caratteri_rifiutati_sono_ESATTAMENTE_quelli_che_fanno_sollevare_il_client`,
    che pinna contro un listener VERO proprio il fatto che il valore finisce
    nel messaggio dell'eccezione, e quel file e' fra i «cosa RESTA e non si
    tocca» di questa fetta. Provato: la redazione funziona (il motivo diventa
    `Illegal header value b'***'`). Si consegna al task che potra' riscrivere
    quel pin insieme al codice, invece di scavalcarlo qui."""
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
                   f"strumenti a meta', e il prompt li afferma tutti")
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
    `True` si aggiungono due opzioni, e nessuna e' facoltativa:

    - `--mcp-config <stringa>`: la voce del server (vedi `config_mcp`);
    - `--allowedTools <i nomi del catalogo>`: i nomi PREFISSATI di `nomi_mcp()`,
      derivati dal catalogo. Senza, gli strumenti sarebbero visibili e non
      permessi.

    fetta "il ponte riceve gli strumenti", review totale (I-1):
    `--strict-mcp-config` sta FUORI dall'`if`, cioe' su ENTRAMBI i rami, e non
    e' una svista al contrario. Il flag non concede strumenti: li TOGLIE --
    dice alla CLI di usare SOLO i server MCP che le passiamo noi e di ignorare
    quelli dell'ambiente. Sul ramo con strumenti quello che resta e' il nostro;
    sul ramo di degrado non resta NIENTE, che e' esattamente cio' che
    `prompts._GUIDA_SENZA_STRUMENTI` afferma al modello («NON hai alcuno
    strumento di HIRIS»).

    Perche' non bastava lasciarlo dentro l'`if`: riprodotto dal vivo con
    l'argv di produzione, il ramo di degrado caricava SEI server MCP
    dell'ambiente e li offriva al modello mentre il prompt gli diceva di non
    averne nessuno. E non e' un rischio teorico dell'ambiente di sviluppo:
    `run.sh` esporta `CLAUDE_CONFIG_DIR=/data/claude` e `_safe_subprocess_env`
    lo lascia passare, `/data` e' scrivibile dall'host (SSH/Samba/File
    editor), e il giorno in cui qualcosa scrivesse `mcpServers` li' dentro il
    prompt diventerebbe falso SENZA che nessuno tocchi questo codice. Il
    costo e' misurato: col flag su entrambi i rami `mcp_servers = []`, la
    lista `tools` risolta e' identica e `rc` e' identico.

    Con `False` l'argv resta quello del ramo di DEGRADO: nessuna
    `--mcp-config`, nessun `--allowedTools`, e il prompt che nega gli
    strumenti resta vero per costruzione invece che per fortuna."""
    argv = ["claude", "-p", user, "--model", model,
            "--system-prompt", system,
            "--exclude-dynamic-system-prompt-sections",
            "--disallowedTools", _LOCAL_TOOLS_DENY,
            "--permission-mode", "default",
            # Su entrambi i rami: vedi I-1 nel docstring.
            "--strict-mcp-config",
            "--output-format", "stream-json", "--verbose"]
    if strumenti_attivi:
        argv += ["--mcp-config", mcp_config,
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

# Il sentinella del silenzio dichiarato (3) della fetta. Come gli altri quattro
# del ponte, VIENE da `chat_store`: se finisse in chat_history.db tornerebbe al
# modello a ogni turno successivo -- difetto gia' trovato dal vivo e riparato
# una volta su questo ramo.
#
# Importato e non ridigitato: erano cinque stringhe scritte a mano di qua e di
# la', e l'elenco e' gia' andato fuori sincrono una volta. Sta in `chat_store`
# e non qui perche' quello e' una foglia -- lo puo' importare chiunque senza
# rischiare un ciclo, il contrario no.
_SENTINELLA_FLUSSO_INCOMPLETO = SENTINELLA_FLUSSO_INCOMPLETO

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

# fetta "il ponte riceve gli strumenti" (parita' B, Task 4): il TETTO di
# invocazioni della CLI per singolo turno del ponte. E' due perche' esiste
# esattamente un motivo per invocare due volte -- l'`init` ha smentito la sonda
# e il prompt gia' partito va buttato, non rattoppato -- e nessun motivo per
# invocarne tre: un ciclo qui sarebbe peggio del guasto che cerca di riparare,
# perche' moltiplicherebbe per N il costo di un turno che sta gia' fallendo.
# E' un tetto di COSTO oltre che di logica, quindi non e' affidato alla forma
# del codice ma a un contatore, e un test lo asserisce.
#
# Costante di modulo, non opzione dell'add-on (regole della fetta): se un
# giorno servira' configurarla, si fara' il giro dei cinque posti allora.
MAX_INVOCAZIONI_PER_TURNO = 2


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
      niente";
    - `tools_called`: fetta "il ponte riceve gli strumenti" (parita' B, Task 5).
      I blocchi `tool_use` degli eventi `assistant`, NELL'ORDINE in cui la CLI
      li ha emessi -- `[{"tool": nome, "input": argomenti}, ...]`, la STESSA
      forma di `handlers_chat.py` (ramo sincrono): una lista sola da rendere
      per la UI della E5, non due. Lista VUOTA (mai `None`) quando nessuno
      strumento e' stato chiamato: `None` direbbe "non lo so", una lista vuota
      dice "nessuno". Il nome e' quello GREZZO che il modello ha usato
      (`mcp__hiris__ricorda`), MAI normalizzato: normalizzarlo nasconderebbe il
      caso -- il solo che conta per questo task -- in cui il modello chiama
      qualcosa che non gli abbiamo dato. Quando un `tool_result` abbinato
      (stesso `tool_use_id`, in un evento `user` successivo) ARRIVA ed e'
      `is_error: true`, la voce guadagna una terza chiave, `"is_error": True`:
      cosi' una chiamata riuscita (esito arrivato, senza errore) resta
      bit-per-bit la stessa forma del ramo sincrono, e una fallita resta
      DISTINGUIBILE invece di sparire nella stessa forma di una riuscita.

      **Fix round 1, Important**: l'ASSENZA di `is_error` significa "nessun
      esito d'errore VISTO", non "prova di riuscita". Un `tool_use` il cui
      `tool_result` non arriva MAI -- flusso troncato (`risultato_presente`
      `False`), o un `result` di errore/max-turns che chiude il flusso con una
      chiamata ancora aperta pur con `rc == 0` -- e' esattamente il caso (3)
      che questo modulo gia' dichiara altrove, e prima di questo fix
      produceva la STESSA forma di una riuscita: `{"tool", "input"}`, senza
      nessuna terza chiave. Un `ricorda` fallito il cui esito si perde nel
      troncamento sarebbe apparso come un ricordo salvato. Ora quella voce
      guadagna una terza chiave diversa, `"esito": "sconosciuto"`
      (mutualmente esclusiva con `"is_error"`: una voce e' o RISOLTA -- riuscita
      senza terza chiave, o fallita con `is_error` -- o SCONOSCIUTA, mai due
      cose insieme): tre stati, tre forme, e nessuno dei tre si confonde con
      un altro."""

    testo: str = ""
    init: dict | None = None
    usage: dict = field(default_factory=dict)
    righe_saltate: int = 0
    righe_lette: int = 0
    risultato: dict | None = None
    num_turni: int | None = None
    tools_called: list = field(default_factory=list)

    @property
    def risultato_presente(self) -> bool:
        """False = flusso troncato, processo ucciso a meta', o formato cambiato
        da un aggiornamento della CLI. Chi legge DEVE dichiararlo."""
        return self.risultato is not None


@dataclass
class Invocazione:
    """Una singola invocazione della CLI, gia' letta e gia' REDATTA.

    fetta "il ponte riceve gli strumenti" (parita' B, Task 4). Esiste perche'
    da questo task l'invocazione puo' avvenire DUE volte nello stesso turno, e
    i rami che ne interpretano l'esito (rc!=0, flusso senza risultato, testo
    vuoto, testo) devono restare **uno solo**: se il secondo tentativo avesse
    una propria copia di quei rami, il ponte avrebbe due modi di leggere la
    stessa risposta -- che e' la biforcazione che il Task 2 esiste per evitare.

    `stdout`/`stderr` sono le copie redatte: la grezza non sopravvive alla
    funzione che le produce."""

    rc: int = 0
    stdout: str = ""
    stderr: str = ""
    esito: EsitoFlusso = field(default_factory=EsitoFlusso)


def leggi_flusso(stdout: str) -> EsitoFlusso:
    """Legge l'NDJSON di `claude --output-format stream-json --verbose`.

    Non solleva mai: ogni modo di essere malformato (riga non-JSON, JSON che
    non e' un oggetto, flusso vuoto, flusso senza evento finale) diventa un
    campo dell'`EsitoFlusso`, mai un'eccezione che risale a `_reason_chat`."""
    esito = EsitoFlusso()
    # fetta "il ponte riceve gli strumenti" (parita' B, Task 5): gli id dei
    # `tool_use` visti finora, per abbinare il `tool_result` che arriva DOPO
    # (un evento `user` successivo, con lo stesso `tool_use_id`) alla voce
    # gia' accodata in `esito.tools_called`. Un dizionario e non una ricerca
    # lineare: un turno puo' avere piu' chiamate in parallelo, e cercarle a
    # ogni `tool_result` sarebbe quadratico per niente.
    chiamate_per_id: dict[str, dict] = {}
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
        elif tipo == "assistant":
            # I blocchi `tool_use` dentro il messaggio dell'assistente:
            # `{"type":"tool_use","id":...,"name":...,"input":...}`, in mezzo
            # a blocchi `text`/`thinking` che si ignorano qui (non sono lo
            # strumento).
            blocchi = ((evento.get("message") or {}).get("content")
                      if isinstance(evento.get("message"), dict) else None)
            for blocco in (blocchi or []):
                if not (isinstance(blocco, dict) and blocco.get("type") == "tool_use"):
                    continue
                nome = blocco.get("name")
                # Il nome grezzo, MAI normalizzato (vedi il docstring di
                # `EsitoFlusso.tools_called`): riscriverlo nasconderebbe
                # proprio il caso -- il modello che chiama uno strumento che
                # non gli abbiamo dato -- che questo campo esiste per rendere
                # visibile.
                voce = {"tool": nome if isinstance(nome, str) else "",
                       "input": blocco.get("input")}
                esito.tools_called.append(voce)
                id_chiamata = blocco.get("id")
                if isinstance(id_chiamata, str):
                    chiamate_per_id[id_chiamata] = voce
        elif tipo == "user":
            # L'esito che torna al modello, riecheggiato nel flusso come
            # messaggio "user": `{"type":"tool_result","tool_use_id":...,
            # "is_error":...}`. E' l'UNICO punto in cui una chiamata fallita
            # si distingue da una riuscita -- senza, "ricorda" fallito e
            # "ricorda" riuscito produrrebbero la stessa identica voce.
            blocchi = ((evento.get("message") or {}).get("content")
                      if isinstance(evento.get("message"), dict) else None)
            for blocco in (blocchi or []):
                if not (isinstance(blocco, dict) and blocco.get("type") == "tool_result"):
                    continue
                id_chiamata = blocco.get("tool_use_id")
                voce = chiamate_per_id.get(id_chiamata) if isinstance(id_chiamata, str) else None
                if voce is None:
                    continue
                # Fix round 1, Important: l'esito e' ARRIVATO -- si segna
                # SEMPRE (`_risolto`), non solo quando e' un errore. E'
                # questo marcatore, tolto qui sotto dopo il ciclo, che
                # distingue "arrivato e riuscito" da "mai arrivato": senza,
                # i due casi produrrebbero la stessa forma (vedi il
                # docstring di `EsitoFlusso.tools_called`).
                voce["_risolto"] = True
                if blocco.get("is_error"):
                    # Solo quando VERO: cosi' una chiamata riuscita (esito
                    # arrivato, senza errore) resta bit-per-bit
                    # {"tool":..., "input":...}, identica alla forma del
                    # ramo sincrono (Step 2 del brief).
                    voce["is_error"] = True
    # Fix round 1, Important: le voci il cui `tool_result` non e' MAI
    # arrivato (flusso troncato, o un `result` di errore/max-turns che
    # chiude tutto con una chiamata ancora aperta) restano senza il
    # marcatore `_risolto` -- si tolgono a fine ciclo, dopo aver letto
    # TUTTI gli eventi, perche' un `tool_result` puo' arrivare in una riga
    # successiva a quella del `tool_use` che lo attende. Il silenzio
    # dichiarato (6) della fetta: senza questa marcatura un `ricorda`
    # fallito il cui esito si perde nel troncamento sarebbe apparso, nel
    # dato, come un ricordo salvato.
    for voce in esito.tools_called:
        if not voce.pop("_risolto", False):
            voce["esito"] = "sconosciuto"
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


def _server_dichiarati(esito: EsitoFlusso) -> list:
    """Nome e stato di ogni server MCP dell'`init`, e NIENT'ALTRO.

    E' l'unica forma in cui l'evento `init` esce da questo modulo -- verso un
    log o verso un motivo. L'evento intero non si stampa mai: la
    `--mcp-config` porta gli header di autenticazione, e un `%r` generoso e'
    il modo classico di far finire un token nel log."""
    return [{"name": s.get("name"), "status": s.get("status")}
            for s in ((esito.init or {}).get("mcp_servers") or [])
            if isinstance(s, dict)]


def _strumenti_risolti(esito: EsitoFlusso) -> set:
    """I nomi di strumento che la CLI dichiara di aver risolto in questo turno.
    Solo stringhe: una voce di altro tipo non e' un nome e non conta."""
    voci = (esito.init or {}).get("tools")
    if not isinstance(voci, list):
        return set()
    return {v for v in voci if isinstance(v, str)}


def _logga_init(esito: EsitoFlusso, job_id) -> None:
    """L'`init` letto e loggato. Dal Task 4 ci si DECIDE anche sopra:
    `verifica_init` qui sotto e' la difesa (2) del progetto, e questa riga
    resta la misura -- il log dice cosa la CLI ha collegato, in ogni turno,
    anche quando la verifica passa.

    Si logga il nome e lo stato di ogni server, non l'evento intero
    (`_server_dichiarati`).

    Review totale della fetta (I-3): la riga porta anche **due campi che
    l'`init` ha gia'** e che nessun altro posto dice.

    - `claude_code_version`: il `Dockerfile` pinna la CLI a una versione
      esatta, e questo campo e' l'unico posto in cui si legge quella che sta
      girando DAVVERO. La ragione non e' caduta col pin, e' migliorata: prima
      serviva a sapere QUALE CLI fosse capitata dentro l'immagine, perche'
      `@2` ne lasciava entrare una qualunque; adesso serve a PROVARE che il
      pin sia arrivato fino al container -- e a smascherare l'immagine
      installata piu' vecchia di quella che si crede, che il `Dockerfile` da
      solo non puo' dire.
    - `apiKeySource`: e' l'**unica prova a runtime** che questo ponte stia
      parlando con l'ABBONAMENTO e non con una chiave a consumo (`none` =
      abbonamento). La promessa «solo abbonamento, mai API a consumo» e'
      difesa dal codice da una sola cosa, `_SUBPROCESS_ENV_DENYLIST`, che e'
      una denylist di due nomi: una denylist non puo' provare cio' che NON e'
      passato, questo campo si'.

    Review totale della fetta (I-5): il warning dell'`init` assente non manda
    piu' a cercare `--verbose` per primo. La causa piu' frequente e' un'altra
    -- la CLI e' morta prima di emettere l'evento, e allora il campo da
    guardare e' `rc` -- e l'implementer del Task 7 ci ha perso un giro di
    diagnosi dal vivo. Il messaggio elenca le cause senza sceglierne una:
    affermarne una sola e' esattamente il modo in cui questa riga sviava."""
    if esito.init is None:
        log.warning(
            "flusso stream-json senza evento system/init (job_id=%s): l'init "
            "non e' arrivato. Le cause possibili, in nessun ordine di colpa: "
            "la CLI puo' essere morta prima di emetterlo (guardare rc e "
            "stderr, che questo modulo logga a parte), oppure --verbose non e' "
            "arrivato alla CLI, oppure il formato del flusso e' cambiato. "
            "Quando gli strumenti erano attesi questa assenza NON e' una "
            "conferma e vale come guasto: la decide `verifica_init`", job_id)
        return
    strumenti = esito.init.get("tools")
    log.info(
        "init del ponte (job_id=%s): cli=%s, apiKeySource=%s, mcp_servers=%s, "
        "strumenti risolti=%d",
        job_id,
        esito.init.get("claude_code_version"),
        esito.init.get("apiKeySource"),
        _server_dichiarati(esito),
        len(strumenti) if isinstance(strumenti, list) else 0)


def verifica_init(esito: EsitoFlusso) -> tuple[bool, str]:
    """Difesa (2) del progetto: la CLI ci e' ARRIVATA, agli strumenti?

    `sonda_strumenti` (difesa 1) prova che la rotta risponde con tutti i nomi
    **dal nostro lato**, e la prova un istante prima di comporre il prompt. Fra
    quel `200` e il modello restano pero' Node, il parsing della stringa
    `--mcp-config`, `--strict-mcp-config` e il loopback visto da un ALTRO
    processo: tutta la superficie a cui nessuna suite verde puo' rispondere.
    L'evento `system/init` e' l'unico posto in cui la CLI dichiara com'e'
    andata, e arriva PRIMA del primo token.

    Si chiedono **entrambe** le condizioni, e non e' ridondanza:

    - il server col NOSTRO nome dev'esserci fra i `mcp_servers` in stato
      `connected` (un server assente o `failed` e' il guasto conclamato);
    - **tutti** i `mcp__<server>__*` di `nomi_mcp()` devono comparire nella lista
      `tools` risolta. Un server connesso che non espone gli strumenti e' lo
      stesso guasto visto da un'altra parte -- e per il modello e' peggio,
      perche' il prompt li nomina uno per uno.

    **Un `init` assente vale guasto, non successo.** Una CLI piu' vecchia, un
    `--verbose` che non e' arrivato o un formato cambiato producono la stessa
    assenza: trattarla come conferma vorrebbe dire far dipendere la promessa
    del prompt da cio' che NON e' stato detto. Un'assenza non e' una conferma.

    Pura: nessun log, nessuna rete, nessun subprocess -- il motivo lo logga
    (e lo reda) chi la chiama. Restituisce `(True, "")` oppure `(False,
    motivo)`, dove il motivo porta lo stato dei server e i nomi mancanti,
    perche' «non ha funzionato» senza il PERCHE' e' un silenzio con una riga
    di log intorno."""
    nome = _nome_server_mcp()
    if esito.init is None:
        return False, ("il flusso non porta l'evento system/init: un'assenza "
                       "non e' una conferma (CLI piu' vecchia, --verbose non "
                       "arrivato, o formato cambiato)")
    server = _server_dichiarati(esito)
    stato = next((s.get("status") for s in server if s.get("name") == nome), None)
    mancanti = sorted(set(nomi_mcp()) - _strumenti_risolti(esito))
    if str(stato or "").strip().lower() != "connected" or mancanti:
        return False, (f"mcp_servers={server}; server {nome!r} stato={stato!r} "
                       f"(atteso 'connected'); strumenti non risolti dalla CLI="
                       f"{mancanti}")
    return True, ""


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
        # Unico ritorno che non passa da `_reply` (fix round 2): siamo
        # PRIMA che il token sia in mano, e questa stringa e' una
        # costante che non ha mai visto ne' la CLI ne' la sua eco.
        return {"reply": SENTINELLA_MOCK}
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
    # Task 6: l'identita' del turno per il tetto ai giri di strumento, che
    # vive nella rotta (`api/handlers_mcp.py::MAX_GIRI_STRUMENTI`), non qui.
    # Si conia UNA sola volta per TURNO -- questa chiamata di `_reason_chat`,
    # cioe' un job -- e non per invocazione della CLI: se il turno si
    # sdoppia in una seconda invocazione (Task 4: l'`init` smentisce la
    # sonda), quella seconda invocazione riparte SEMPRE senza strumenti e
    # quindi non chiama mai `config_mcp` -- ma se lo facesse, riceverebbe
    # QUESTA STESSA identita' (e' la stessa variabile, passata da `_invoca`,
    # sotto, a ogni chiamata di `config_mcp` a prescindere da quale delle due
    # invocazioni la fa). Se se ne coniasse una diversa per la seconda
    # invocazione, il tetto per-turno raddoppierebbe in silenzio proprio nel
    # turno in cui il ponte ha gia' fallito una volta -- l'opposto di un
    # freno.
    #
    # Un `secrets.token_urlsafe` breve: **serve solo a contare**, non e'
    # un'autenticazione (quella resta il token interno negli stessi header) e
    # non va scambiata per tale -- vedi il docstring di `config_mcp`.
    id_turno = secrets.token_urlsafe(9)
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
    forme = forme_del_token(token)

    # fetta "il ponte riceve gli strumenti" (parita' B, Task 5): l'accumulo per
    # TUTTO il turno, non per la sola invocazione che finisce nella reply.
    #
    # Perche' NON e' la risposta ovvia (riportare solo l'ultima invocazione).
    # Quando il Task 4 butta la prima invocazione (l'`init` smentisce la
    # sonda) e ne ricompone una seconda SENZA strumenti, il testo della prima
    # sparisce -- ma le sue chiamate MCP, se ce ne sono state, sono gia'
    # passate per davvero da `POST /api/mcp` fino a `DispatcherStrumenti`:
    # un `ricorda` chiamato li' ha gia' scritto in `memoria.db`, prima che
    # noi si scoprisse che il prompt prometteva strumenti a meta'. Buttare
    # l'invocazione non disfa quella scrittura. Riportare solo l'ultima
    # invocazione nasconderebbe esattamente il turno in cui questo task
    # esiste per vedere qualcosa: quello in cui la promessa del prompt e i
    # fatti hanno divergito. Si accumula quindi su ENTRAMBE, nell'ordine
    # (primo giro, poi secondo), nella stessa lista che diventa
    # `decision["tools_called"]`.
    #
    # Step 5 del brief -- la nota che va dichiarata, non risolta qui. La
    # fetta A (Task 5, reasoning/queue.py::submit) azzera `context_json` a
    # job risolto, ma NON `decision_json` -- la risposta, che serve al poll.
    # Questa lista vive quindi in `decision["tools_called"]` e resta su
    # disco fino alla potatura a 7 giorni, con gli INPUT che il modello ha
    # passato agli strumenti: per `ricorda`, non solo `testo` ma anche
    # `detto_da` (un identificativo di PERSONA), `ancore` e `condizioni`
    # (`casa/strumenti.py::_ricorda`, `argomenti.get(...)`); per `cerca`, la
    # frase dell'utente. Cambiare la potatura di `decision_json` e' fuori dal
    # perimetro di questa fetta (regole-fetta.md): si dichiara qui, si
    # consegna alla fase sicurezze, con lo stesso perche' con cui il Task 5
    # della fetta A l'aveva appena tolto dal `context`.
    tools_called_turno: list = []

    def _reply(testo: str) -> dict:
        """L'UNICO modo in cui una risposta esce da questa funzione.

        fix round 2, seconda meta' della difesa: redigere il solo stdout GREZZO
        non basta, perche' i rami (3) e (5) ricavano il testo dallo stdout
        PARSATO -- e il parsing riporta il token da profondita' 2 a profondita'
        1, cioe' a una forma che la redazione del grezzo, fatta un livello piu'
        in la', non trova piu'. Con questo cancello la `reply` viene redatta
        DOPO il parsing, quando qualunque eco e' tornata a profondita' 1.

        **Il limite, misurato invece che promesso** (Task 4, nit 2 della review
        del Task 3): la frase che stava qui diceva «indipendente da quanti
        involucri JSON la CLI abbia messo intorno all'eco». Non e' vero, ed e'
        proprio la classe di dichiarazione falsa al presente che questo
        prodotto paga da tre fette. `forme_del_token` si ferma a profondita' 2
        (grezza, dentro la mcp-config, dentro l'evento che la cita): questo
        cancello copre **un involucro in piu'** di quelli che la catena
        conosce, non un numero illimitato. Un terzo involucro non esiste in
        questa catena -- ecco perche' non e' un difetto aperto -- ma se un
        giorno la CLI ne aggiungesse uno, il residuo sarebbe qui e non
        altrove.

        Sei rami di ritorno, una sola redazione: non c'e' un ramo da
        dimenticare, ne' oggi ne' quando ne nascera' un settimo.

        fetta "il ponte riceve gli strumenti" (parita' B, Task 5): la
        `decision` porta anche `tools_called` -- SEMPRE, in modalita' `live`
        (una lista vuota se nessuno strumento e' stato chiamato, mai
        l'assenza della chiave: e' cosi' che `handle_chat_reply_poll` sa
        distinguere "nessun job legacy/mock" da "turno vero senza
        strumenti"). Passa dallo STESSO cancello (`_reda_struttura`, sopra):
        l'`input` e' testo del modello, non nostro, e la regola del progetto
        e' che il token non compare in NESSUN canale nuovo."""
        return {"reply": reda_segreti(testo, *forme),
               "tools_called": _reda_struttura(tools_called_turno, *forme)}

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
    invocazioni = 0

    def _invoca(strumenti_attivi: bool) -> Invocazione | None:
        """UN'invocazione intera della CLI, composta dal SOLO `strumenti_attivi`.

        fetta "il ponte riceve gli strumenti" (parita' B, Task 4). Prima di
        questo task queste righe stavano distese nel corpo di `_reason_chat`;
        ora sono una funzione perche' il turno puo' comporre e invocare **due
        volte**, e la seconda volta deve essere la STESSA composizione con
        l'altro argomento -- non una variante scritta a parte. E' l'interruttore
        unico che regge anche al secondo giro: `mcp_config`, `system` e `argv`
        nascono qui dentro, tutti e tre da `strumenti_attivi`, e non esiste un
        punto in cui il prompt possa restare avanti all'argv.

        `None` = esito (5): la CLI non parte, non c'e', o non finisce in tempo.
        E' l'unico ramo che non ha nemmeno uno stdout da leggere."""
        nonlocal invocazioni
        if invocazioni >= MAX_INVOCAZIONI_PER_TURNO:
            # Irraggiungibile per costruzione oggi (i due punti di chiamata
            # sono in fila, non in un ciclo). Sta qui perche' il tetto non
            # dipenda dalla FORMA del codice: il giorno in cui qualcuno
            # trasformasse questa sequenza in un ciclo, il costo per turno
            # resterebbe due invocazioni invece di diventare illimitato.
            log.warning(
                "tetto di invocazioni della CLI raggiunto (job_id=%s, max=%d): "
                "nessun terzo tentativo", job_id, MAX_INVOCAZIONI_PER_TURNO)
            return None
        invocazioni += 1
        # `id_turno` e' lo STESSO a ogni chiamata di `_invoca` in questo
        # turno (mintato una volta sola sopra, prima di questa funzione): e'
        # cosi' che il tetto per-turno della rotta MCP resta un tetto sul
        # turno anche quando il turno si sdoppia (Task 4).
        mcp_config = config_mcp(base_url, token, id_turno) if strumenti_attivi else ""
        # Le DUE righe che leggono lo stesso booleano, una accanto all'altra.
        # Non esiste un secondo posto in cui il prompt e l'argv possono
        # divergere: se un giorno queste due righe si allontanano, e' li' che
        # rientra il difetto numero uno di questo prodotto.
        system, user = prompts.build_chat_messages(
            system_prompt, history, contesto=contesto,
            strumenti_attivi=strumenti_attivi,
            restrict_to_home=restrict_to_home, response_mode=response_mode)
        argv = _chat_claude_args(system, user, model,
                                 strumenti_attivi=strumenti_attivi,
                                 mcp_config=mcp_config)
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=300, env=_safe_subprocess_env())
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            log.warning("claude non eseguibile: %s", type(exc).__name__)
            return None

        # La redazione, PRIMA di qualunque lettura (fix round 1, Important 2):
        # il token viaggia in `--mcp-config` e la CLI lo riecheggia quando il
        # server MCP non parte. Da qui in giu' `proc.stdout`/`proc.stderr` non
        # si usano piu': si usano queste due copie, e non c'e' nessun canale
        # che possa dimenticarsi di redigere.
        #
        # fix round 2: si redigono TUTTE le forme del token
        # (`forme_del_token`), non la sola grezza. Il commento che stava qui
        # diceva «il token non contiene virgolette: e' generato da
        # secrets.token_urlsafe» -- vero solo sul ramo GENERATO.
        # `internal_token` e' una `password` libera in config.yaml, e con un
        # token che contiene `"` o `\` la redazione mancava il bersaglio su
        # tutti e cinque i canali. Era una dichiarazione falsa al presente
        # dentro un commento, cioe' il secondo difetto ricorrente di questo
        # prodotto.
        #
        # Si reda anche al SECONDO giro, dove il token non e' mai entrato
        # nell'argv: costa una `str.replace` su una stringa che non lo
        # contiene, e vale la regola «nessun canale che possa dimenticarsi».
        stdout = reda_segreti(proc.stdout or "", *forme)
        stderr = reda_segreti(proc.stderr or "", *forme)

        # UNA sola lettura del flusso, prima di qualunque ramo: e' cosi' che il
        # ramo d'errore e quello felice non possono divergere nel modo di
        # leggere la stessa risposta.
        esito = leggi_flusso(stdout)
        # Task 5: si accumula QUI, sull'esito di OGNI invocazione -- anche
        # quella che il ramo dell'`init` (sotto) sta per buttare. Vedi il
        # commento su `tools_called_turno`, sopra: una chiamata MCP di
        # un'invocazione buttata e' gia' successa per davvero.
        tools_called_turno.extend(esito.tools_called)
        _logga_init(esito, job_id)   # la misura, a ogni giro
        _logga_uso(esito, job_id)    # Step 4: la misura per la domanda aperta 2
        if esito.righe_saltate:
            # Una riga di rumore non fa cadere il flusso, ma non sparisce: se
            # la CLI cambia formato, il conto sale prima che qualcosa si rompa.
            log.warning(
                "flusso stream-json con %d riga/righe non-JSON saltate su %d "
                "(job_id=%s): la risposta e' stata letta lo stesso, ma il "
                "formato della CLI non e' piu' esattamente quello atteso",
                esito.righe_saltate, esito.righe_lette, job_id)
        return Invocazione(rc=proc.returncode, stdout=stdout, stderr=stderr,
                           esito=esito)

    # Il degrado dichiarato: gli strumenti erano attesi e non ci sono. Il log
    # l'ha gia' detto (silenzio (1), dentro `sonda_strumenti`); qui si prepara
    # a dirlo anche all'utente, in testa alla risposta che il modello riuscira'
    # comunque a dare sul solo nucleo.
    degrado = attesi and not strumenti

    invocazione = _invoca(strumenti)
    if invocazione is None:
        return _reply(SENTINELLA_RUNNER_ASSENTE)

    # ── LA DIFESA (2): l'`init` smentisce la sonda (Task 4) ────────────────
    # La sonda ha detto di si' DAL NOSTRO LATO; qui parla la CLI. Se le due si
    # contraddicono, il prompt e' gia' partito affermando strumenti che
    # il modello non ha: la regola della fetta e' che **un prompt gia' partito
    # non si corregge con una postilla -- si butta via l'invocazione e si
    # ricompone dal medesimo booleano**, ora `False`.
    #
    # La verifica sta QUI, subito dopo la lettura del flusso e PRIMA dei rami
    # che ne interpretano l'esito, e non solo sul ramo felice: con
    # `--strict-mcp-config` una mcp-config che la CLI non digerisce e' una
    # causa plausibile di `rc != 0`, e in quel caso il secondo tentativo non
    # e' solo piu' onesto -- e' quello che ha qualche probabilita' di dare
    # all'utente una risposta invece di un `[errore runner rc=...]`.
    #
    # L'esito (5) resta fuori di proposito: senza flusso non c'e' nessuna
    # smentita da leggere, e ritentare pagherebbe un secondo timeout da 300s
    # per un guasto che il ritentativo non ripara (la CLI non c'e').
    ritentato = False
    if strumenti:
        confermato, motivo = verifica_init(invocazione.esito)
        if not confermato:
            # Silenzio dichiarato ② della fetta. Il motivo si reda come tutto
            # cio' che nasce dal sottoprocesso: non c'e' una seconda via.
            log.warning(
                "l'evento system/init smentisce la sonda (job_id=%s): %s -- il "
                "prompt era gia' partito affermando gli strumenti, quindi "
                "questa invocazione si BUTTA e se ne ricompone una senza "
                "strumenti (una sola volta, mai una terza); la reply lo "
                "dichiara anche all'utente",
                job_id, reda_segreti(motivo, *forme))
            strumenti = False
            degrado = True
            ritentato = True
            invocazione = _invoca(strumenti)
            if invocazione is None:
                return _reply(SENTINELLA_RUNNER_ASSENTE)

    # Da qui in giu' si legge UNA invocazione: la prima se e' bastata, la
    # seconda se la prima e' stata buttata. I rami sono gli stessi.
    esito = invocazione.esito
    stdout, stderr = invocazione.stdout, invocazione.stderr
    # Step 4 del brief: se si e' arrivati a un esito d'errore DOPO un
    # ri-tentativo, il log lo dice -- o «claude rc=1» sembrerebbe il primo
    # guasto del turno invece dell'ultimo di due.
    coda_log = (" [secondo e ULTIMO tentativo: il primo e' stato buttato perche' "
                "l'init smentiva la sonda]" if ritentato else "")

    if invocazione.rc != 0:
        # Esito (1). `claude -p` mette gli errori (auth 401, quota, ecc.) su
        # STDOUT come JSON, non su stderr: la nota vale ancora con stream-json,
        # dove l'errore arriva nell'evento `result` con `is_error: true`. Logga
        # entrambi i canali e prova a estrarre un dettaglio leggibile, per non
        # nascondere la causa dietro un numero.
        log.warning("claude rc=%s stderr=%r stdout=%r%s", invocazione.rc,
                    stderr[:300], stdout[:500], coda_log)
        risultato = esito.risultato or {}
        dettaglio = (esito.testo or risultato.get("error")
                     or risultato.get("subtype") or "")
        if not dettaglio:
            # Nessun evento finale da cui ricavarlo (processo morto a meta'):
            # meglio il flusso grezzo che un silenzio.
            dettaglio = (stdout or stderr).strip()
        return _reply(
            f"{PREFISSO_ERRORE_RUNNER}{invocazione.rc}] "
            f"{str(dettaglio)[:300]}".strip())

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
            "il ponte NON ha una risposta completa e lo dichiara nella reply%s",
            job_id, invocazione.rc, esito.righe_lette, esito.righe_saltate,
            coda_log)
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
        return _reply(f"{avviso} (ultimo pezzo di flusso letto: {coda})"
                      if coda else avviso)

    # Esiti (2) e (4): il testo del risultato, oppure il sentinella del vuoto.
    testo = esito.testo.strip()
    if not testo:
        return _reply(SENTINELLA_VUOTO)
    if degrado:
        # Solo QUI, e non sugli altri rami: `[errore runner rc=...]`,
        # `[runner non disponibile]`, `[flusso incompleto]` e `[vuoto]` sono
        # gia' dichiarazioni di guasto, e sono riconosciuti PER PREFISSO da
        # `chat_store._TOXIC_ASSISTANT_PREFIXES` -- anteporre qualcosa li
        # renderebbe invisibili a quel filtro, e tornerebbero al modello a ogni
        # turno successivo. Questo caso e' l'opposto: sotto c'e' una risposta
        # vera, che va conservata.
        return _reply(f"{AVVISO_STRUMENTI_ASSENTI}\n\n{testo}")
    return _reply(testo)

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
                # Task 4, nit 1: `%s` sull'eccezione GREZZA e' il settimo
                # canale di perdita del token (gli header del claim lo
                # portano, e un valore non consegnabile risale col valore
                # dentro). Si passa da `_motivo_eccezione`: tipo + messaggio
                # REDATTO, cosi' il log resta diagnosticabile.
                log.warning("run_once errore: %s", _motivo_eccezione(exc))
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
                # Task 4, nit 1: vedi `run_loop` -- stesso canale, stessa
                # chiusura. Sono due punti perche' questo `main()` e' il
                # runner come processo a se' (il gateway esterno), e
                # `run_loop` e' quello in-addon.
                log.warning("run_once errore: %s", _motivo_eccezione(exc))
            time.sleep(interval)

if __name__ == "__main__":
    main()
