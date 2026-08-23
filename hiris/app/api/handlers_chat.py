import json
import logging
import os
import secrets
import time

from aiohttp import web

from ..casa.strumenti import STRUMENTI_CONOSCENZA, DispatcherStrumenti
from ..chat_store import (
    load_history, append_messages, get_past_summaries, count_user_turns,
    _is_toxic_assistant,
)
# `modello_cli` e `resolve_model` sono usciti da qui con la fetta «il modello
# del piano»: servivano a comporre il modello del ponte da
# `provider_models["claude"]`, e adesso quel modello e' un campo che si legge.
# `modello_cli` ha un solo chiamante rimasto -- il validatore del campo, in
# `handlers_models._pulisci_modello_del_piano` -- e questo import in meno
# scioglie anche mezzo ciclo: era `handlers_chat` -> `agent.runner` la meta'
# che obbligava `agent/runner._nome_server_mcp` a un import differito.
from ..claude_runner import CHAT_MAX_TOKENS, RunnerBackendError
from ..api.handlers_models import _PREDEFINITI_ARCHIVIO
from ..decisione_modelli import nota_ripiego
from ..instradamento import chi_risponde
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


def costruisci_dispatcher_strumenti(app, turno: str | None = None) -> DispatcherStrumenti:
    """L'UNICO punto del prodotto in cui `DispatcherStrumenti` viene costruito.

    Gli undici strumenti della chat (`casa/strumenti.py`) -- non il catalogo
    di trentaquattro di ALL_TOOL_DEFS: cinque conoscono la casa (`cerca`,
    `guarda`, `legami`, `ricorda`, `richiama`), il sesto, `esegui`, la comanda
    passando per la porta unica (vedi il docstring di quel modulo), tre
    (`prometti`, `promesse`, `disdici`, fetta «lo schedulatore») la impegnano
    per un momento futuro passando per l'archivio delle promesse
    (`schedulatore/archivio.py`), e gli ultimi due (`costruisci`, `conferma`,
    fetta «costruire») scrivono CONFIGURAZIONE -- non un servizio, un'entita'
    nuova -- passando per l'officina (`azione/costruzione/officina.py`). Il
    dispatcher si costruisce dagli stessi oggetti dell'app che alimentano
    `costruisci_nucleo()` (`archivio_casa`, `archivio_memoria`,
    `entity_cache`), piu' `porta_azione` e `officina` -- lo stesso specchio
    dello stato vivo, non uno ricalcolato a mano -- ed e' SEMPRE costruibile,
    anche quando archivi, porta e officina sono assenti: i suoi gestori non
    sollevano mai, dichiarano un `errore` per strumento invece (vedi
    `DispatcherStrumenti.dispatch`).

    `turno` (fetta «costruire», facoltativo e `None` per default: ogni
    chiamante che non lo passa non cambia comportamento) e' l'identita' di
    QUESTO turno, coniata UNA volta dal chiamante e non una per strumento --
    serve alla guardia dell'officina, che rifiuta di confermare una proposta
    nel turno stesso in cui e' nata. Sul ramo sincrono la conia
    `handle_chat`/`_ripiega_sulla_catena` (`secrets.token_urlsafe(8)`, una
    volta per richiesta); sulla rotta MCP e' `X-HIRIS-Turno`, che
    `handlers_mcp.py` legge gia' per il tetto dei giri di strumento e
    ripropone qui.

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

    Task B7 -- `cache_indice=app.get("cache_indice_strumenti")`: l'oggetto di
    vita lunga costruito accanto a `entity_cache` in `server.py`, non uno
    nuovo per turno. Il dispatcher stesso nasce a ogni turno (e' il motivo per
    cui questa funzione esiste), ma la cache dell'indice che gli si passa
    dentro no -- e' cosi' che il riuso vale FRA i turni, non solo dentro uno
    (vedi `memoria/cache_indice.py` per la chiave e il perche').
    """
    return DispatcherStrumenti(
        app.get("archivio_casa"),
        app.get("archivio_memoria"),
        cache=app.get("entity_cache"),
        porta=app.get("porta_azione"),
        cache_indice=app.get("cache_indice_strumenti"),
        # Il canale verso Home Assistant, per `legami`: quello strumento non
        # legge l'archivio, chiede a HA chi tocca una cosa
        # (`search/related`). Senza questa riga sarebbe uno strumento sempre
        # «non disponibile» -- un dato che c'e' e che nessuno puo' chiedere,
        # cioe' la fondamenta 4 al contrario.
        #
        # E' lo STESSO oggetto che usa la porta dell'azione, non un secondo
        # canale: due connessioni verso HA sarebbero due stati di
        # riconnessione da tenere allineati.
        ha=app.get("ha_client"),
        # Il registro dei servizi (`azione/registro.py`), la STESSA istanza
        # che riceve `porta_azione` qui sopra -- mai una seconda costruzione.
        # Serve a `prometti` per verificare un `fai` ADESSO
        # (`DispatcherStrumenti._verifica_ora`) e un `recapito`.
        registro=app.get("registro_servizi"),
        # L'archivio delle promesse (`schedulatore/archivio.py`): la casa di
        # `prometti`/`promesse`/`disdici`.
        promesse=app.get("promesse"),
        # L'officina (`azione/costruzione/officina.py`, fetta «costruire»):
        # la casa di `costruisci`/`conferma`. Sorella di `porta_azione`, non
        # sua sostituta -- due canali diversi, spec «un canale, una porta».
        officina=app.get("officina"),
        # L'identita' di QUESTO turno -- vedi il docstring qui sopra per chi
        # la conia e perche' non e' mai il dispatcher stesso a farlo.
        turno=turno,
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


# fetta «le promesse seguono la catena» (22/08/2026): `_bridge_on` e
# `_piano_puo_rispondere` sono USCITE da qui e vivono in `app/instradamento.py`,
# insieme alla decisione che compongono. Restavano importabili da questo nome
# per due soli chiamanti -- questa funzione e i suoi test -- e lasciarle qui
# avrebbe reso circolare l'import: la chat chiede a `instradamento`, e
# `instradamento` avrebbe dovuto chiedere alla chat.
#
# Non sono un doppione ri-esportato: si importano da dove vivono.


def _nota_di_chi_ha_risposto(request: web.Request, *, motivo: str) -> str:
    """La riga che dichiara un ripiego, o "" se non c'è niente da dichiarare.

    Decisione del proprietario, 13 agosto: **il ripiego si annuncia ogni
    volta**. Quando il turno passa dal piano a forfait a un provider a consumo,
    la risposta lo dice -- una riga, non un avviso invadente -- perché un
    ripiego silenzioso dal forfait al consumo si scopre a fine mese.

    **«Chi ha risposto» si MISURA, non si deduce.** La tentazione è leggere
    `app["catena_modelli"][0]`, cioè «ha risposto il primo della catena»:
    sarebbe falso proprio nel caso che conta, perché il router RIPIEGA, quindi
    il primo può aver fallito e aver risposto il secondo. Si legge quindi il
    registro degli esiti (Task 11), che il ciclo di ripiego del router aggiorna
    per nome di backend subito dopo ogni chiamata -- riuscita o no -- e si
    prende il primo della catena il cui ultimo esito è un successo.

    **Va chiamata DOPO la chiamata al modello**, mai prima: prima misurerebbe
    l'esito del turno PRECEDENTE.

    Se non si può stabilire chi ha risposto -- registro assente (nessun router:
    `app["claude_runner"]` da solo non registra niente), catena vuota, nessun
    successo osservato -- si restituisce "" e la nota NON si scrive. Meglio
    nessuna nota che una che nomina il provider sbagliato: questa riga parla di
    soldi, e una riga falsa sui soldi è peggio del silenzio.
    """
    registro = request.app.get("registro_esiti")
    if registro is None:
        return ""
    for nome_backend in (request.app.get("catena_modelli") or []):
        esito = registro.esito(nome_backend)
        if esito and esito["tipo"] == "risposto":
            return nota_ripiego(motivo=motivo, chi_ha_risposto=nome_backend)
    return ""


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
    # Task 12: stesso secondo lavoro di `giorni_conservazione` del ramo
    # sincrono qui sotto (`handle_chat`) — il ponte non deve rileggere piu'
    # conversazione di quanto l'utente abbia scelto.
    history = load_history(data_dir, giorni=impostazioni.giorni_conservazione)
    sanitized_history = _trim_history(history)
    system_prompt = _build_system_prompt(impostazioni)

    reasoning_queue = request.app["reasoning_queue"]
    now = time.time()
    # La scadenza viene dall'ARCHIVIO, riletto a ogni turno come il modello
    # qui sopra. Fino alla 2.4.1 veniva da `BRIDGE_DEADLINE_MIN`, cioè
    # dall'opzione dell'add-on, mentre `models_config["ponte"]["scadenza_min"]`
    # ne teneva una copia (Task 6) che nessuno leggeva e che la pagina Modelli
    # poteva riscrivere: due rappresentazioni dello stesso numero, e quella che
    # l'utente cambiava non era quella che il turno subiva.
    _scadenza_min = ((request.app.get("models_config") or {})
                     .get("ponte", {}).get("scadenza_min",
                                      _PREDEFINITI_ARCHIVIO["ponte"]["scadenza_min"]))
    deadline = now + int(_scadenza_min) * 60
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
        # Il modello del piano e' un CAMPO, letto dall'archivio a ogni turno
        # come la scadenza qui sopra e il tetto piu' su: e' il TERZO valore che
        # questo punto legge da `models_config["ponte"]`.
        #
        # Fino alla 3.1.0 qui si componeva
        # `modello_cli(resolve_model("auto", "chat", provider_models["claude"]))`,
        # e lo stesso identico calcolo viveva anche in
        # `handlers_models._modelli_in_uso`: due implementazioni della stessa
        # regola, libere di divergere. Peggio della duplicazione era cio' che
        # diceva -- il modello del piano era un effetto collaterale del modello
        # di CLAUDE API, cioe' di un altro provider, con l'incentivo opposto:
        # a consumo si sceglie il modello frugale, nel piano il modello non
        # costa di piu'. Il proprietario si ritrovava il piano che aveva pagato
        # a girare con `haiku`.
        #
        # La traduzione ai tre alias non e' sparita, e' salita all'INGRESSO del
        # campo (`handlers_models._pulisci_modello_del_piano`): cio' che si
        # legge qui e' gia' un alias della CLI, e non c'e' niente da tradurre.
        # Il predefinito `"sonnet"` e' quello di `_PREDEFINITI_ARCHIVIO` e vale
        # solo per un'app senza archivio (i test): sull'impianto la semina
        # (`migrazione_opzioni.semina_modello_del_piano`) ha gia' scritto il
        # campo prima che un turno possa arrivare qui.
        "model": ((request.app.get("models_config") or {})
                  .get("ponte", {}).get("modello", "sonnet")),
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


async def _ripiega_sulla_catena(request: web.Request, job_id: str):
    """Rifà sulla catena il turno che il piano non ha servito in tempo.

    È qui e non nello sweep di `server.py` per una ragione misurata: lo sweep
    gira ogni 2 minuti, e `static/chat/send.js` smette di interrogare dopo
    `CHAT_POLL_MAX_MS` (5 minuti). Con la scadenza predefinita di 5 minuti, un
    ripiego fatto dallo sweep arriverebbe fra il quinto e il settimo minuto --
    cioè, quasi sempre, dopo che il browser ha smesso di guardare. Il poll passa
    ogni 3,5 secondi: il ripiego parte subito, e non c'è nessun intervallo da
    tenere accordato con una costante del frontend.

    **Il prezzo, dichiarato:** una chiamata al modello finisce dentro una
    richiesta HTTP nata per essere istantanea, e può durare decine di secondi.
    Il browser ha già una richiesta in volo e non ne apre una seconda finché
    quella non torna, quindi non si accavallano -- ma la rotta di poll smette di
    essere sempre veloce, e chi legge i tempi di risposta del server deve
    saperlo.

    Restituisce `None` quando un altro poll ha già reclamato questo turno: si
    continua ad aspettare lui invece di ripiegare due volte.
    """
    coda = request.app["reasoning_queue"]
    adesso = time.time()
    job = coda.reclama_scaduto(job_id, adesso)
    if job is None:
        return None

    # Il registro degli esiti, per il piano, era VUOTO PER COSTRUZIONE: il
    # ponte non passa dal router (`handle_chat` accoda prima di prenderlo),
    # quindi nessuno registrava mai un esito per `subscription` e la sua riga
    # nella pagina Modelli diceva per sempre «non l'hai ancora usato». Questo è
    # l'unico punto del prodotto in cui si osserva qualcosa sul piano, ed è
    # QUI che si registra -- prima della chiamata alla catena, perché è un
    # fatto già avvenuto e non dipende da come andrà il ripiego.
    #
    # La famiglia è `scaduto` e non `altro`: il ramo di scorta di
    # `frase_esito` direbbe «ha rifiutato», e il piano non ha rifiutato -- non
    # ha risposto. È la stessa parola più larga del fatto che questa fetta
    # esiste per togliere.
    registro = request.app.get("registro_esiti")
    if registro is not None:
        registro.fallimento(
            "subscription", famiglia="scaduto", codice=None,
            # Il messaggio è per chi legge un log, non per la pagina: la frase
            # che l'utente vede la compone `decisione_modelli.frase_esito`.
            messaggio="nessuna risposta entro la scadenza del ponte",
            # Quanto il piano ha AVUTO, misurato sul job e non riletto
            # dall'archivio: la scadenza può essere stata cambiata mentre il
            # turno era in volo, e quel numero racconterebbe un'attesa che non
            # c'è stata.
            durata_s=float(job.get("deadline_ts", adesso))
            - float(job.get("created_ts", adesso)))

    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    contesto = job.get("context") or {}
    data_dir = request.app.get("data_dir", "/data")
    if runner is None:
        # Nessuna nota: non c'è stato nessun ripiego da annunciare -- non ha
        # risposto nessuno. La nota parla di CHI ha risposto al posto del piano.
        # Il job si chiude comunque, altrimenti resterebbe in 'ripiego' fino
        # allo sweep e ogni poll ritenterebbe.
        coda.risolvi_ripiego(job_id, {"reply": ""}, time.time())
        return web.json_response({
            "status": "error",
            "message": ("Il Piano Claude Max non ha risposto in tempo, e non c'è "
                        "nessun altro provider in catena a cui chiedere."),
        })

    logger.warning(
        "Il Piano Claude Max non ha risposto entro la scadenza: il turno %s "
        "passa alla catena. Il costo cambia -- dal forfait al consumo.", job_id)

    cronologia = contesto.get("history") or []
    ultimo = cronologia[-1]["content"] if cronologia else ""
    try:
        # L'identita' di QUESTO turno, coniata UNA volta qui e non dentro il
        # dispatcher: questa funzione risponde a UNA sola richiesta HTTP (il
        # poll che ha scoperto la scadenza), quindi una sola identita' le
        # basta -- vedi il docstring di `costruisci_dispatcher_strumenti` per
        # la guardia che la usa.
        #
        # Review indipendente (I3, fetta «costruire»): CONVERSAZIONALMENTE
        # e' lo stesso turno del lavoro sul ponte che e' appena scaduto, ma
        # riceve un'identita' NUOVA, diversa da quella (se mai ce n'e' stata
        # una) che il ponte aveva coniato per quel job. Oggi non morde: la
        # cronologia del ripiego (`contesto.get("history")`, sopra) porta
        # solo messaggi utente/assistente, un `proposta_id` non ci arriva
        # mai, e questo ramo non puo' quindi confermare una proposta nata sul
        # ponte. Ma e' a un cambiamento di distanza dall'aprire il cancello
        # in silenzio: se un giorno il contesto del ripiego portasse anche lo
        # stato di una `costruisci` in sospeso, questa identita' nuova la
        # renderebbe confermabile qui -- fuori dal turno che l'ha proposta,
        # ed e' esattamente cio' che la guardia esiste per impedire. Chi
        # tocca questo contesto deve saperlo.
        id_turno = secrets.token_urlsafe(8)
        risposta = await runner.chat(
            user_message=ultimo,
            system_prompt=contesto.get("system_prompt", ""),
            context_str=contesto.get("contesto", ""),
            # La cronologia del job CONTIENE GIÀ il turno dell'utente (pinnato
            # da `test_job_context_history_includes_current_user_turn`):
            # passarla intera come `conversation_history` E ripetere il
            # messaggio come `user_message` lo manderebbe due volte.
            conversation_history=cronologia[:-1],
            # L'unico valore che fa girare il ciclo di ripiego del router: con
            # un modello esplicito `_route()` sceglie una volta sola e non
            # ripiega mai. Dal Task 4 è già l'unico che esiste, ma qui va
            # SCRITTO, non ereditato.
            model="auto",
            max_tokens=CHAT_MAX_TOKENS,
            agent_type="chat",
            restrict_to_home=bool(contesto.get("restrict_to_home")),
            response_mode=contesto.get("response_mode", "auto"),
            # Il contesto del job NON porta `thinking_budget` (sei chiavi,
            # pinnate da `test_context_del_job_porta_esattamente_queste_sei_
            # chiavi_ne_una_di_piu`): inventarne uno qui significherebbe
            # applicare al ripiego un'impostazione che il ponte aveva
            # dichiarato inapplicabile, con un log, al momento
            # dell'accodamento.
            thinking_budget=0,
            strumenti=STRUMENTI_CONOSCENZA,
            dispatcher=costruisci_dispatcher_strumenti(request.app, turno=id_turno),
        )
    except RunnerBackendError as exc:
        # Stessa rete del ramo sincrono, e per la stessa ragione: `runner` può
        # essere `app["claude_runner"]`, cioè un backend diretto che SOLLEVA.
        risposta = exc.friendly_message

    # L'annuncio: chi ha davvero risposto, non chi è primo in catena.
    nota = _nota_di_chi_ha_risposto(request, motivo="scadenza")
    # La nota entra nel JOB, così un poll che arriva DOPO il ripiego, o un
    # ricaricamento della pagina, la ritrova invariata: ciò che il turno ha
    # prodotto vive nel job, non nella richiesta che per caso lo ha raccolto.
    coda.risolvi_ripiego(job_id, {"reply": risposta, "nota": nota}, time.time())
    if not _is_toxic_assistant(risposta):
        # SOLO la risposta: il turno dell'utente è già in cronologia da prima
        # dell'accodamento (`_enqueue_chat_job`), e riscriverlo lo
        # duplicherebbe. E SOLO la risposta anche rispetto alla nota: una nota
        # persistita diventa contesto che il modello rilegge al turno dopo e su
        # cui ragiona -- è la stessa famiglia del difetto dichiarato su «Errore
        # temporaneo del servizio AI», che in cronologia ci finisce e non
        # dovrebbe.
        append_messages([{"role": "assistant", "content": risposta}], data_dir)
    payload = {"status": "done", "reply": risposta}
    if nota:
        payload["nota"] = nota
    return web.json_response(payload)


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
    if status in ("pending", "claimed") and job.get("deadline_ts", 0) <= time.time():
        # Il piano non ha risposto in tempo. Fino alla 2.4.1 finiva qui, con
        # «La risposta non è arrivata in tempo. Riprova.» -- il messaggio era
        # perso e la catena non veniva consultata mai. Adesso il turno scende al
        # provider successivo, e la risposta arriva in QUESTA stessa
        # conversazione, su QUESTO stesso job: il browser non deve cambiare
        # niente, perché la forma della risposta è quella che già aspetta.
        risposta = await _ripiega_sulla_catena(request, job_id)
        if risposta is not None:
            return risposta
        # `None` = un altro poll ha già reclamato: si continua ad aspettare lui,
        # invece di ripiegare due volte.
        return web.json_response({"status": "pending"})
    if not reply:
        # Compreso lo stato 'ripiego': un ripiego in corso è un turno in corso,
        # e si aspetta come si aspettava il piano. Quando finisce, il job è
        # 'decided' con la sua `reply` e questo poll passa oltre; se non
        # finisce mai (processo caduto a metà chiamata) lo raccoglie
        # `fallisci_ripieghi_bloccati`, chiamata dallo sweep, che lo porta a
        # 'failed' -- e 'failed' esce dal ramo di errore qui sopra.
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
    # Gli strumenti del turno vanno nei LOG a livello debug, non nella risposta.
    #
    # Fino al 17/08/2026 finivano in `payload["debug"]["tools_called"]` e il
    # frontend ne disegnava una targhetta per ciascuno, col nome e -- al click --
    # con gli ARGOMENTI: per `ricorda` il testo del ricordo, per `esegui`/`cerca`
    # gli id delle entita' di casa. Erano nate per rendere OSSERVABILE una
    # scrittura di `ricorda` fatta dal ponte (parita' B, I-7), e quella ragione
    # resta buona: per questo l'osservabilita' non e' stata tolta ma spostata
    # qui. Toglierla e basta avrebbe distrutto la capacita' per cui esisteva.
    #
    # Solo i NOMI, mai gli argomenti: un log e' un posto in cui i dati di casa
    # restano scritti, e il nome dello strumento basta a sapere che cosa il
    # turno ha fatto.
    if decision.get("tools_called"):
        logger.debug("strumenti del turno [job_id=%s]: %s", job_id,
                     ", ".join(str(t.get("tool") or "?")
                               for t in decision["tools_called"]
                               if isinstance(t, dict)))
    # fetta «la catena diventa l'unica verità» (Task 14): un turno ripiegato
    # porta anche la nota che lo dichiara. Sta nel `decision` del job -- ce
    # l'ha scritta `risolvi_ripiego` -- quindi un poll che arriva DOPO il
    # ripiego, o un ricaricamento della pagina, la ritrova invariata.
    # Esattamente come `tools_called` qui accanto, e per lo stesso motivo: ciò
    # che il turno ha prodotto vive nel job, non nella richiesta che per caso
    # lo ha raccolto.
    if decision.get("nota"):
        payload["nota"] = decision["nota"]
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
    # turn limit is silently bypassed whenever the bridge is on
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

    # Il motivo del ripiego a monte, `None` quando non c'è stato: lo legge il
    # fondo di questa funzione per comporre la nota, DOPO aver saputo chi ha
    # davvero risposto.
    _motivo_ripiego = None

    # Slice 4b (chat via abbonamento), Task 2: when subscription mode is on
    # AND the reasoning-queue bridge is wired, hand the turn to the async
    # queue instead of calling a local runner — subscription mode may have
    # no runner/API key configured at all locally, that's the point. Task 1
    # built the receiving end (kind="chat" submit -> chat_store); this is
    # the sending end. Checked BEFORE the runner-required guard below so
    # subscription mode works even without CLAUDE_API_KEY.
    #
    # fetta «la catena diventa l'unica verità», Task 14: questo `if` non è più
    # un BIVIO. Fino alla 2.4.1 chi entrava qui non tornava indietro -- la riga
    # che prende il router sta sotto, e la si saltava -- quindi «il piano non è
    # disponibile» finiva in un errore invece che nel provider successivo. Il
    # ramo `else` più sotto è il ritorno: si scende alla catena, che è la riga
    # subito dopo questo blocco.
    _via, _motivo_del_piano = chi_risponde(request.app)
    if _via == "ponte" or _motivo_del_piano:
        # Slice 4b Task 3: two guards on the async path ONLY -- the sync path
        # above/below is unaffected when the flag is off. Checked before
        # anything is persisted/enqueued so a blocked turn leaves no trace.
        reasoning_queue = request.app["reasoning_queue"]
        # La guardia «una risposta per volta» resta PRIMA, e adesso conta il
        # doppio. NON ripiega: due risposte in volo sulla stessa conversazione
        # sarebbero peggio del 409 -- la seconda arriverebbe in una cronologia
        # che la prima sta per riscrivere. Sopra il piano che non può
        # rispondere, perché il caso «tetto pieno E una risposta in volo» è
        # raggiungibile (il turno numero N sta ancora aspettando quando arriva
        # l'N+1): ripiegando lì si manderebbe un turno sincrono sulla catena
        # mentre il ponte ne ha uno in volo che scriverà la sua risposta in
        # cronologia da solo (`server._submit_chat_reply`).
        if reasoning_queue.has_pending_chat():
            return web.json_response(
                {"error": "C'è già una risposta in arrivo per questa conversazione."},
                status=409,
            )
        if _motivo_del_piano:
            # Ripiego a monte: il piano NON PUÒ rispondere a questo turno --
            # gli manca il token (il worker non parte, `should_start_agent_
            # worker`) oppure il tetto giornaliero è pieno. Non si accoda un
            # messaggio in una coda che nessuno servirà, e non si risponde 429:
            # si scende alla catena. È il ripiego col rapporto migliore fra
            # costo e valore di tutta la fetta, e non tocca nessuna forma di
            # risposta -- il turno esce 200, sincrono, come sempre. Il 429 e la
            # sua stringa ESCONO: un utente che ieri leggeva «Limite
            # giornaliero raggiunto» oggi riceve una risposta, a consumo, senza
            # averlo chiesto -- ed è esattamente il caso per cui il ripiego si
            # annuncia (la `nota` in fondo a questa funzione). Senza quella
            # riga questo cambio sarebbe un prelievo silenzioso.
            _motivo_ripiego = _motivo_del_piano
            logger.warning(
                "Il piano non può rispondere a questo turno (%s): il turno "
                "passa alla catena. Il costo cambia -- dal forfait al consumo.",
                _motivo_del_piano)
        else:
            return await _enqueue_chat_job(request, impostazioni, message, data_dir)

    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        # E' la PRIMA cosa che legge chi installa HIRIS e apre la chat senza
        # aver ancora configurato niente. Prima diceva, in inglese, «set
        # CLAUDE_API_KEY»: un nome di variabile d'ambiente che NON e'
        # un'opzione dell'add-on (l'opzione si chiama `claude_api_key`) e che
        # chi usa il piano a forfait non deve compilare affatto.
        #
        # Le etichette fra «» sono i nomi VERI dei campi in
        # `translations/it.yaml`, e devono restarlo: fino alla 2.4.1 erano
        # quelli di una versione precedente («Attiva provider: Abbonamento
        # (Claude Max)» e altre tre), cioe' questo messaggio mandava chi aveva
        # appena installato HIRIS a cercare campi che nella sua pagina non
        # esistevano. Debito dichiarato dal Task 5 di questa fetta e chiuso dal
        # Task 15, con il pin che impedisce alla deriva di ripetersi:
        # `tests/test_invarianti_modelli.py::test_il_messaggio_di_primo_avvio_
        # nomina_campi_che_esistono_davvero`, che confronta ogni «...» con i
        # `name` delle traduzioni. Chi cambia un'etichetta cambia anche questo
        # messaggio, o il test cade.
        #
        # VERSIONE B (3.0.0): erano QUATTRO, e due sono uscite dallo schema --
        # «Provider · Piano Claude Max (a forfait)» e «Provider · Claude API
        # (a consumo)», cioe' i due interruttori. Il pin ha fatto il suo
        # mestiere e ha fatto cadere il test. Restano le due credenziali, che
        # e' cio' che si custodisce li'; e il messaggio dice adesso anche il
        # SECONDO gesto, che prima non c'era: incollare la chiave non basta
        # piu' a far rispondere la chat, perche' un provider e' usato se e solo
        # se sta in catena. Dirne uno solo lascerebbe l'utente davanti a una
        # chat ancora muta dopo aver fatto tutto quello che gli era stato detto.
        return web.json_response(
            {"error": (
                "Nessun provider AI configurato: HIRIS non ha ancora un modello a "
                "cui chiedere. Apri Impostazioni → Add-on → HIRIS → Configurazione "
                "e incolla una credenziale: col piano a forfait il token in "
                "«Provider · Piano Claude Max — token», con l'API a consumo la "
                "chiave in «Provider · Claude API — chiave». Poi, dentro HIRIS, "
                "apri la pagina Modelli: col piano usa «Mettilo primo» nel riquadro "
                "in cima, con l'API a consumo usa «Usa» sulla riga di Claude API. "
                "Un provider risponde se e solo se sta in catena."
            )},
            status=503,
        )

    # Load server-side history (client-sent history field is ignored).
    # Task 12: `giorni_conservazione` fa qui il suo SECONDO lavoro -- non solo
    # la potatura notturna, ma anche quanto di questa conversazione HIRIS
    # rilegge adesso. Riletto a ogni turno dall'archivio come il modello
    # (vedi il commento sulla scadenza del ponte qui sotto), non catturato
    # all'avvio: un utente che lo abbassa in `#/impostazioni` lo vede avere
    # effetto dal messaggio successivo, senza riavviare.
    history = load_history(data_dir, giorni=impostazioni.giorni_conservazione)

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

    # Gli undici strumenti della chat -- il perche' di ogni riga sta
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
    #
    # fetta «costruire»: l'identita' di QUESTO turno si conia UNA volta qui,
    # non dentro il dispatcher -- questa funzione risponde a UNA richiesta
    # HTTP sola (sincrona o in streaming, mai entrambe), quindi un turno le
    # basta. Serve alla guardia dell'officina (`costruisci`/`conferma`, vedi
    # il docstring di `costruisci_dispatcher_strumenti`).
    id_turno = secrets.token_urlsafe(8)
    dispatcher_strumenti = costruisci_dispatcher_strumenti(request.app, turno=id_turno)

    # fetta "la catena diventa l'unica verita'": qui c'era
    # `agent_model = impostazioni.model`. Il campo e' uscito con la decisione
    # del proprietario del 13 agosto: il modello si sceglie per provider, nella
    # pagina Modelli, e la chat chiede SEMPRE `auto`. Non e' una costante di
    # comodo: `auto` e' l'UNICO valore che fa passare il turno dal ciclo di
    # ripiego di `LLMRouter.chat` invece che da `_route()`, che sceglie una
    # volta sola e non ripiega mai.
    agent_model = "auto"
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
        # engages — reproduce the exact same string-shaped degraded response
        # so everything below (toxicity/persistence/serialization) is
        # unaffected.
        #
        # fetta "la catena diventa l'unica verita'" (Task 4): questo commento
        # diceva «that loop only ever raises here when `agent_model` pins an
        # explicit non-"auto" model». Non e' piu' vero, perche' `agent_model`
        # e' SEMPRE "auto" (sopra): quel ramo di `LLMRouter.chat` non esiste
        # piu' per nessun turno. Sul ramo "auto" il router cattura ogni
        # eccezione di ogni backend e restituisce una stringa, quindi
        # attraverso `app["llm_router"]` questo `except` non e' piu'
        # raggiungibile. Resta perche' `runner` puo' anche essere
        # `app["claude_runner"]` (handle_chat, la riga che sceglie il
        # runner), cioe' un backend diretto che invece SOLLEVA: e' li' che
        # questa rete serve ancora. Detto, non taciuto: un ramo che non si sa
        # se e' vivo e' esattamente cio' che questa fetta chiude altrove.
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
    # Stessa scelta del ramo del ponte qui sopra: i nomi degli strumenti vanno
    # nei log a debug, non nella risposta. `thinking_blocks` resta -- e' il
    # ragionamento che l'utente ha chiesto di vedere, non un nome di funzione.
    if tools_called:
        logger.debug("strumenti del turno: %s",
                     ", ".join(str(t.get("tool") or "?") for t in tools_called))
    debug_payload: dict = {}
    if thinking_blocks:
        debug_payload["thinking_blocks"] = thinking_blocks
    payload = {"response": response, "debug": debug_payload}
    # L'annuncio del ripiego a monte. Si compone QUI e non nel ramo che ha
    # deciso di ripiegare, perché prima della chiamata qui sopra non si sa
    # ancora CHI ha risposto -- il router ripiega a sua volta, e il primo della
    # catena può aver fallito. `_motivo_ripiego` resta `None` quando il turno
    # non ha ripiegato, e allora non si scrive niente. La forma della risposta
    # NON cambia: `response` e `debug` restano identici e `nota` è facoltativa,
    # quindi un client che la ignori continua a funzionare.
    if _motivo_ripiego:
        nota = _nota_di_chi_ha_risposto(request, motivo=_motivo_ripiego)
        if nota:
            payload["nota"] = nota
    return web.json_response(payload)
