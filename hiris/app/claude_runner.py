import asyncio
import contextvars
import json
import logging
import time
from typing import Any

import anthropic

# fetta E3 Task 8 ("esce l'ultimo catalogo"): la E2 aveva lasciato vive le 18
# definizioni sotto (`EVALUATION_ONLY_TOOLS`/`EVALUATION_TOOL_DEFS`) perche'
# erano l'unico catalogo che la Sentinella usava, via `run_with_actions` --
# dichiarato per iscritto: "escono con lei". La Sentinella e' uscita al Task
# 7 di questa fetta: `run_with_actions` non aveva piu' un solo chiamante, e i
# 12 moduli di `tools/` (da cui venivano importate queste definizioni)
# sopravvivevano solo per donargliele. Cataloghi, `run_with_actions` e
# `tools/` escono qui insieme -- la chat riceve il suo catalogo da fuori
# (`strumenti=KNOWLEDGE_TOOLS`, home_space/tools.py: quattro strumenti che
# conoscono la casa, piu' `execute` che la comanda per la porta unica) da prima
# di questo task.
#
# fetta «cosa è successo davvero»: la classificazione dell'errore vive in
# `provider_occurrences`, che non importa niente da qui a livello di modulo (il suo
# unico import di `openai_compat_runner` è dentro `error_family`) -- quindi
# nessun ciclo.
from .provider_occurrences import error_family

logger = logging.getLogger(__name__)


class RunnerBackendError(Exception):
    """Raised by a runner's chat() when the underlying
    provider API call itself failed (rate limit, connection error, timeout,
    auth failure, 5xx, or any other persistent outage) — as opposed to the
    model producing a normal (if unusual) reply.

    Review C/#13: ClaudeRunner/OpenAICompatRunner used to CATCH these errors
    and RETURN a friendly Italian string, indistinguishable from a real
    successful reply to any caller. LLMRouter's ordered-backend fallback loop
    wraps chat() in `except Exception` specifically to
    fail over to the next configured backend on a primary outage — but a
    returned string never raises, so the loop always "succeeded" on the
    first (broken) backend and the fallback chain was dead code.

    `friendly_message` carries the exact user-facing string the runner used
    to return directly. LLMRouter catches this exception to try the next
    backend, and once every backend in the chain has failed, surfaces the
    LAST failure's `friendly_message` to the end user — the router becomes
    the single place that produces the user-facing degradation. Callers that
    bypass the router (e.g. handlers_chat.handle_chat when an agent pins an
    explicit non-"auto" model) catch it directly at their own call site to
    preserve their pre-existing graceful-degradation behavior instead of
    crashing. (ChatbotEngine._run_chatbot used to be the other such caller —
    it's gone, fetta E4 Task 2: the manual "Test Run" it backed was dead by
    construction, see task-2-report.md.)

    `famiglia` e `codice` sono ciò che il provider ha DETTO, e la fetta «cosa è
    successo davvero» li porta fin qui perché fino ad allora andavano persi:
    ogni errore d'API diventava lo stesso `friendly_message` («Errore
    temporaneo del servizio AI. Riprova tra poco.») e il router lo scriveva nel
    log e tirava avanti. Una chiave a credito zero -- `400 credit balance too
    low`, il caso del proprietario -- era indistinguibile da un 500 passeggero,
    e la pagina Modelli non aveva niente da dire.

    `friendly_message` NON cambia: è ciò che l'utente legge in chat, e questi
    due campi non sono per lui. Servono a `LLMRouter` per scrivere nel
    `OccurrenceRegistry` che cosa è successo a quel provider, e da lì alla riga di
    stato della pagina Modelli. I valori di scorta (`"altro"`, `None`) sono
    quelli di un guasto non classificato, non un modo di dire «non lo so»:
    `provider_occurrences.family_from_code(None)` restituisce la stessa cosa.
    """

    def __init__(self, friendly_message: str, *, family: str = "altro",
                 code: int | None = None) -> None:
        super().__init__(friendly_message)
        self.friendly_message = friendly_message
        self.family = family
        self.code = code

    def __str__(self) -> str:  # so `str(exc)` == the friendly text everywhere
        return self.friendly_message


_TOOL_RESULT_COMPRESS_LEN = 300  # chars to keep per old tool result

def _compress_old_tool_results(messages: list[dict], keep_last: int = 2) -> None:
    """Truncate tool_result content in older iterations to save input tokens.

    Keeps the last `keep_last` tool_result sets at full size; earlier ones
    are truncated because Claude has already processed them and they're only
    re-sent for conversation continuity, not for reasoning.
    """
    tr_indices = [
        i for i, m in enumerate(messages)
        if m["role"] == "user"
        and isinstance(m.get("content"), list)
        and m["content"]
        and isinstance(m["content"][0], dict)
        and m["content"][0].get("type") == "tool_result"
    ]
    for idx in tr_indices[:-keep_last] if len(tr_indices) > keep_last else []:
        compressed = []
        for block in messages[idx]["content"]:
            if block.get("type") == "tool_result":
                raw = block.get("content", "")
                if isinstance(raw, str) and len(raw) > _TOOL_RESULT_COMPRESS_LEN:
                    block = {**block, "content": raw[:_TOOL_RESULT_COMPRESS_LEN] + "…[troncato]"}
            compressed.append(block)
        messages[idx] = {**messages[idx], "content": compressed}

# ── Base system prompt ─────────────────────────────────────────────────────
# Always injected at runtime BEFORE any agent-specific instructions.
# Agents configure WHAT to do and HOW to behave; this layer defines the tools
# available and the invariant anti-hallucination rules.
# Review finale fetta E3, Important #1: la versione precedente dichiarava al
# modello «strumenti per leggere stati, controllare dispositivi, inviare
# notifiche, gestire automazioni, calendario, task» e ordinava di chiamare
# `save_memory` -- uno strumento che non esiste piu' (il catalogo di oggi e'
# SOLO cerca/guarda/ricorda/richiama, home_space/tools.py). Un prompt che
# ordina di chiamare uno strumento inesistente riapre dal lato del prompt
# esattamente il bug per cui `remember` e' nato (vedi il docstring in cima a
# home_space/tools.py): il modello puo' rispondere "preso nota" senza aver
# salvato, perche' la chiamata che gli abbiamo insegnato a fare fallisce in
# silenzio. Riscritta perche' descriva cio' che HIRIS e' oggi: conosce la
# casa e la memoria, risponde, non attua.
#
# fetta «comandare» (Task 6): «non attua» non e' piu' vero, e la riscrittura
# di allora e' diventata la falsita' che quel commento vieta -- girata al
# contrario. Il Task 5 ha messo `execute` nel catalogo unico
# (`home_space/tools.py`) e quindi nei tool del ramo sincrono E nell'argv della
# CLI: il modello RICEVE lo strumento, e questa costante gli diceva «non
# controlli dispositivi ... rispondi, non agisci». Un ordine di NON usare uno
# strumento che esiste e' lo stesso difetto dell'ordine di usarne uno che non
# esiste: in un caso il modello dichiara azioni mai avvenute, nell'altro
# rifiuta azioni che poteva fare -- e il sintomo («HIRIS dice che non puo'
# accendere») e' indistinguibile da «gli strumenti sono rotti».
#
# Perche' le regole nuove stanno QUI e non nella guida del ponte
# (`agent/prompts._GUIDE_WITH_TOOLS`, dove il brief le aveva messe): sono
# regole del PRODOTTO, e questa meta' e' l'unico testo emesso SE E SOLO SE
# gli strumenti esistono -- sempre sul percorso sincrono (che le guide non le
# vede MAI: `chat()` qui sotto compone `BASE_SYSTEM_PROMPT`) e sul ponte solo
# con `strumenti_attivi=True`. Scritte nella guida sarebbero arrivate al
# ponte e non alla chat vera, cioe' la divergenza fra i due percorsi che la
# fetta «parita'» ha passato due task a chiudere. Alla guida resta il suo
# mestiere: i nomi PREFISSATI, che qui non avrebbero senso.
#
# Le regole e la ragione di ciascuna stanno in tests/test_action_prompt.py.
# Una sola merita di essere ripetuta accanto al testo: sull'ambiguita'
# («accendi il bagno») HIRIS AGISCE sulla lettura piu' naturale e non chiede
# conferma -- in questa fetta ogni azione e' una chiamata a un servizio e si
# annulla dicendo il contrario, quindi sbagliare costa una frase mentre
# domandare costerebbe su OGNI richiesta, per sempre. La bilancia si ribalta
# nella fetta dei costruttori (un'automazione scritta male non si annulla
# dicendo il contrario): quella regola sara' diversa, e questa non va copiata
# li'. E cio' che si propone di ricordare dev'essere una PREFERENZA GENERALE,
# mai una sostituzione della frase con delle entita': una sostituzione
# toglierebbe all'utente la possibilita' di intendere il riscaldamento con le
# stesse parole, e non varrebbe per nessun'altra stanza. Il vincolo regge
# perche' la memoria di HIRIS non e' una tabella di macro: e' testo che
# rientra nel prompt e che il modello rilegge insieme alla frase di adesso.
# Il prompt lo dice esplicitamente perche' la sostituzione e' la forma che al
# modello viene naturale.
#
# Cio' che il prompt NON dice, e non dira' finche' non esiste: che HIRIS
# chieda conferma prima di agire. Nessun meccanismo di conferma esiste in
# questa fetta -- `execute` verifica e chiama -- e prometterlo sarebbe la
# classe di difetto che questo ramo ha passato settimane a chiudere.
#
# fetta "il ponte riceve il nucleo" (parita' A, Task 2, fix round 1 --
# Critical 1 della review indipendente): la costante e' spezzata in DUE meta',
# e `BASE_SYSTEM_PROMPT` resta la loro concatenazione, byte per byte. NESSUN
# chiamante cambia: `chat()` qui sotto, backends/openai_compat_runner.py
# (`chat` e `chat_stream`) e tests/test_base_prompt_memory.py continuano a
# vedere la STESSA costante con lo STESSO testo (pinnato da
# tests/test_base_prompt_split.py).
#
# Perche' spezzarla: dal Task 2 questa costante arriva ANCHE al ponte (la chat
# in abbonamento, agent/prompts.py), dove gli strumenti NON esistono. La
# prima stesura del task la importava intera e la faceva smentire dal testo che
# la segue -- ma "Usa SEMPRE gli strumenti per dati sulla casa" e "chiama
# ricorda subito" sono ORDINI DI CHIAMARE UNO STRUMENTO INESISTENTE, cioe'
# esattamente cio' che il commento qui sopra dichiara di non voler piu' fare:
# il modello puo' rispondere "preso nota" senza aver salvato -- il bug misurato
# in produzione da cui `remember` e' nato. Una smentita di TESTO non e' un
# meccanismo. Spezzata, il ponte compone la sola meta' VERA quando non ha
# strumenti, ed entrambe quando li avra' (fetta B): la parte falsa non viene
# proprio emessa.
#
# Il criterio del taglio: in `BASE_IDENTITY` cio' che e' vero su ENTRAMBI i
# percorsi (chi e' HIRIS, cosa conosce); in `BASE_TOOL_RULES` tutto cio'
# che nomina, ordina o presuppone la chiamata a uno strumento. Le due meta'
# sono PUBBLICHE (senza underscore) perche' attraversano un confine di modulo:
# `agent/prompts.py` importa `BASE_IDENTITY`.
#
# Fix della review totale della fetta (m-2): "Rispondi nella lingua
# dell'utente" stava nella meta' SBAGLIATA, e il commento del taglio lo
# ammetteva senza chiamarlo per nome ("cade nella seconda meta' perche' la
# concatenazione deve restare ordinata e identica"). Non e' una regola sugli
# strumenti -- non ne nomina, non ne ordina e non ne presuppone nessuno --
# quindi stava di la' per CONTIGUITA' (era l'ultimo trattino dell'elenco), per
# una ragione che il criterio dichiarato qui sopra non contiene: il commento
# descriveva un taglio diverso da quello reale.
#
# La conseguenza non era cosmetica. Stando in `BASE_TOOL_RULES`, la riga
# sul ponte non veniva emessa affatto (il ponte compone la sola
# `BASE_IDENTITY`), e l'unica istruzione di lingua che gli restava era
# `prompts._CHAT_INSTRUCTION`, che imponeva SEMPRE l'italiano: un utente che
# scrive in inglese riceveva inglese dal percorso sincrono e italiano dal
# ponte. In una fetta che si chiama "parita'" quella e' una divergenza, non un
# dettaglio. La riga e' quindi salita qui, dove il criterio la vuole (e' vera
# su ENTRAMBI i percorsi), e `_CHAT_INSTRUCTION` e' stata allineata --
# altrimenti i due blocchi si contraddicevano dentro lo stesso prompt.
#
# Il percorso sincrono non perde nulla: la riga c'e' ancora e
# `BASE_SYSTEM_PROMPT` resta la concatenazione ordinata delle due meta'.
# Cambia la POSIZIONE della riga dentro quel testo -- subito dopo l'identita'
# invece che in coda all'elenco "## Regole fondamentali", dove peraltro era
# l'unico trattino che non parlava di strumenti. Pinnata da
# `tests/test_base_prompt_split.py`, cosi' non migra piu' in silenzio.
BASE_IDENTITY = (
    "Sei HIRIS, assistente AI integrata in Home Assistant: conosci la casa"
    " (aree, entità, dispositivi, automazioni e script) e la memoria di ciò"
    " che le persone ti hanno detto.\n"
    "Rispondi nella lingua dell'utente.\n"
)

# La regola del racconto e la diagnosi inventata (2.2.1). Sulla prima casa
# vera HIRIS ha spento due abat-jour -- si sono spente -- e ha risposto:
# «nulla e' cambiato ... probabile problema di comunicazione col dispositivo.
# Vuoi che riprovi?». Il difetto di FONTE che gli faceva vedere lo stato di
# prima e' chiuso in `action/actuator.py`; ma la seconda meta' della frase --
# quella che ha mandato il proprietario a cercare un guasto inesistente -- e'
# nata QUI, e sarebbe rimasta.
#
# La riga diceva: «Se `cambiato` e' vuoto la chiamata e' riuscita ma nulla e'
# cambiato in casa». Affermava una proprieta' della CASA a partire da un dato
# che parla solo di cio' che HIRIS ha potuto vedere -- lo stesso errore di
# scala dei fix m11/Task 6 sulle guide del ponte, qui su un altro soggetto. E
# un modello a cui si dice, con autorita', che l'utente ha chiesto di spegnere
# e in casa non e' cambiato niente, ha una sola conclusione disponibile: il
# dispositivo. La speculazione non era un capriccio del modello, era l'unica
# uscita che il testo gli lasciava.
#
# Adesso la riga afferma solo il fatto misurato (Home Assistant non ha
# riportato cambiamenti), e la riga dopo vieta esplicitamente la deduzione
# sulla causa nominando le tre ragioni banali che la rendono inutile. E' la
# stessa disciplina del «preso nota»: non dire di sapere cio' che non sai.
BASE_TOOL_RULES = (
    "Hai a disposizione strumenti per cercare e guardare il dettaglio di una"
    " cosa della casa, per salvare e richiamare ciò che ti viene detto e per"
    " far succedere qualcosa: `execute` chiama un servizio di Home Assistant"
    " su una o più entità — accendere, spegnere, impostare. La chiamata viene"
    " verificata contro questa installazione prima di partire, e dopo ti arriva"
    " ciò che Home Assistant ha visto cambiare: quello che ha riportato subito e"
    " quello che ha annunciato un istante dopo, che HIRIS aspetta apposta per un"
    " tempo breve e limitato."
    " `execute` non scrive automazioni, script o scene — per costruirli usa"
    " `propose` (vedi sotto) — e non programma niente per dopo:"
    " ogni sua azione nasce da una richiesta di questa conversazione.\n\n"
    "## Regole fondamentali\n"
    "- Usa SEMPRE gli strumenti per dati sulla casa — non inventare stati, valori o entità.\n"
    "- `execute` vuole gli id ESATTI delle entità, mai il nome con cui le persone le chiamano:"
    " se hai solo un NOME chiama prima search e usa l'id che ti risponde.\n"
    "- Gli id fra parentesi che vedi nell'albero della casa — `Nome (id: X)` — sono già gli"
    " identificatori esatti: se un'area, un piano, un'automazione o uno script li porta con sé"
    " nel contesto, usali direttamente e non chiamare search per qualcosa che hai già.\n"
    "- Se devi risolvere più nomi nella stessa richiesta, chiama search UNA sola volta con"
    " tutto il testo: risolve più frammenti in una frase sola, non serve una chiamata per"
    " nome.\n"
    "- Se devi fare più letture indipendenti — più view, più related — chiamale IN"
    " PARALLELO nella stessa risposta: il ciclo conta un giro per risposta, non per"
    " chiamata.\n"
    "- Se la richiesta riguarda una STANZA, un piano, un'etichetta o un dispositivo,"
    " passali a `execute` cosi' come sono -- `aree`, `piani`, `etichette`,"
    " `dispositivi` -- e NON raccogliere gli id a mano con search: li risolve Home"
    " Assistant, che e' l'unico a saperli tutti. Raccoglierli a mano significa"
    " spegnerne quattordici su quindici e dire di averle spente tutte.\n"
    "- L'esito porta `bersaglio`: se `toccate` e' piu' corto di `risolte`, dillo"
    " all'utente e di' quali sono rimaste fuori e perche'.\n"
    "- Dopo aver eseguito racconta cosa è SUCCESSO, non cosa è stato chiesto: la risposta di"
    " `execute` porta `prima`, `dopo` e `cambiato`, presi da ciò che Home Assistant ha"
    " riportato durante la chiamata o annunciato subito dopo. Se `cambiato` non è vuoto"
    " il comando ha avuto effetto: dillo, e di' da cosa a cosa.\n"
    "- Se `cambiato` è vuoto, l'unica cosa vera è che Home Assistant non ha riportato nessun"
    " cambiamento: dillo così — non «non è cambiato niente in casa», che è una cosa che non"
    " puoi sapere — e riferisci l'`avviso` se c'è.\n"
    "- E NON dedurne una causa. Non dire che il dispositivo non risponde, che c'è un problema"
    " di comunicazione, che è offline o guasto: non hai nessun dato che lo dica, e mandare"
    " qualcuno a cercare un guasto inesistente è peggio che dire «non lo so». Le ragioni vere"
    " sono banali almeno quanto un guasto — era già così, il servizio non cambia nessuno"
    " stato, oppure una tapparella o una valvola si sta ancora muovendo e finirà fra qualche"
    " secondo.\n"
    "- Non dichiarare azioni mai eseguite: se non hai chiamato il tool, non dire di averlo fatto.\n"
    "- Se hai chiamato uno strumento con successo, l'azione è reale:\n"
    "  non aggiungere disclaimers come "
    "'ho inventato', 'ho simulato' o 'non ho realmente eseguito'.\n"
    "- Quando una richiesta ammette più letture — «accendi il bagno», e in bagno ci sono due"
    " luci, uno scaldasalviette e un aspiratore — agisci sulla lettura più naturale e di' cosa"
    " hai fatto: ciò che fai si annulla dicendo il contrario, quindi sbagliare costa una frase"
    " mentre domandare costerebbe a ogni richiesta. Non c'è nessuna conferma da chiedere e"
    " nessuna azione in attesa. Domanda solo quando una lettura naturale non c'è: in quella"
    " stanza non c'è niente del genere, oppure i candidati sono così diversi che nessuno è ovvio.\n"
    "- «Si annulla dicendo il contrario» ha un'eccezione, ed è ciò che non si vede guardando la"
    " casa: **spegnere un'automazione o uno script** (`automation.turn_off`, `script.turn_off`)"
    " non accende e non spegne niente di visibile, e resta così finché qualcuno non lo riattiva"
    " — una regola della casa che smette di valere, e nessuno che sappia perché. Fallo se te lo"
    " chiedono; ma dillo per esteso — quale automazione, e che resterà spenta — e non farlo mai"
    " come effetto collaterale di un'altra richiesta.\n"
    "- Se l'utente ti corregge, proponi di ricordare la sua PREFERENZA GENERALE con remember"
    " — «quando dico di accendere una stanza senza specificare altro, di solito intendo le"
    " luci» — e mai una sostituzione della frase con delle entità («accendi il bagno = queste"
    " due luci»): la sostituzione gli toglierebbe la possibilità di intendere il riscaldamento"
    " con le stesse parole, e non varrebbe per nessun'altra stanza. Ciò che ricordi è testo che"
    " rileggerai insieme alla frase di allora, non una macro che la sostituisce.\n"
    "- Quando l'utente dichiara qualcosa di duraturo su di sé, sulla casa o su come vuole le cose —"
    " una preferenza, un vincolo, un guasto, una regola operativa — chiama remember subito, senza"
    " chiedere il permesso: basta l'affermazione, non serve che dica 'ricordati che'. Non salvare"
    " lo stato di adesso né una richiesta una tantum, né ciò che puoi rileggere da Home Assistant"
    " quando"
    " serve.\n"
    "- 'Preso nota' senza aver chiamato remember è la stessa azione mai eseguita vietata sopra:"
    " non dirlo se non hai salvato.\n\n"
    "Per costruire qualcosa in Home Assistant — un'automazione, uno script, una"
    " scena — usa `propose`: compone e fa validare, ma NON scrive. Mostra"
    " all'utente l'anteprima che ricevi e fermati. Solo quando l'utente ti"
    " risponde di procedere chiami `confirm` con il `proposta_id`. Non"
    " chiamare `confirm` nello stesso turno di `propose`: viene rifiutato,"
    " e la ragione è che il sì deve essere suo. Se l'anteprima contiene una"
    " nota sul mestiere (per esempio: quella cosa è uno script, non"
    " un'automazione), riferiscila."
)

BASE_SYSTEM_PROMPT = BASE_IDENTITY + BASE_TOOL_RULES

# fetta E3 Task 8: `EVALUATION_TOOL_DEFS` (ex `ALL_TOOL_DEFS`, il catalogo da
# 34) e `EVALUATION_ONLY_TOOLS` (le 18 letture concesse alla Sentinella) sono
# uscite insieme a `run_with_actions`, il loro unico chiamante -- vedi il
# commento in testa al file. La chat non ha mai smesso di ricevere il suo
# catalogo dall'esterno (`strumenti=KNOWLEDGE_TOOLS`); ora e' l'UNICO
# modo in cui `chat()` vede dei tool, non piu' il ramo di scorta.

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
# Tetto d'uscita piu' alto per la chat interattiva: una risposta lunga (il
# riepilogo di una casa grande, un elenco di ricordi) supera legittimamente il
# default da 4096 di `chat()`/`chat_stream()` -- `MAX_TOKENS` qui sopra,
# ereditato dall'agente di valutazione uscito con la fetta E3 Task 8
# (`run_with_actions`, vedi il commento su `EVALUATION_TOOL_DEFS` poco sopra;
# stessa uscita annotata in llm_router.py e in backends/openai_compat_runner.py).
# Quel default oggi non lo raggiunge nessun chiamante di produzione:
# `handlers_chat.py` passa SEMPRE `CHAT_MAX_TOKENS`. Kept well under the model
# max so the non-streaming SDK path doesn't hit the request-timeout guard.
#
# fetta E4 Task 8, Step 2: questo commento diceva "complex requests (a
# multi-view dashboard, a long script)" e "per le plance molto grandi il
# modello propone poche viste per volta" -- una dichiarazione falsa al
# presente: HIRIS 2.0 LEGGE le plance (proxy/ha_client.py, casa/
# comportamento.py) e non ne scrive nessuna, e il catalogo della chat e'
# quello di home_space/tools.py -- che dalla fetta «comandare» chiama servizi di
# Home Assistant (`execute`) ma continua a non scrivere plance.
# fix round 1: la riscrittura aveva lasciato dentro un secondo soggetto morto
# -- diceva "il tetto da 4096 dell'agente di valutazione" al PRESENTE, ma
# quell'agente non esiste piu' (fetta E3 Task 8, commento poco sopra): 4096 e'
# rimasto solo come default di firma. Il tetto (16000) non e' mai cambiato in
# nessuno dei due giri: cambia la ragione dichiarata, che ora e' vera.
CHAT_MAX_TOKENS = 16000
# fetta "i riferimenti" (R3): misurato che 8 stanze da guardare una a una
# servono 10 round-trip minimi contro un tetto di 10 -- morte garantita anche
# a esecuzione perfetta, perche' l'ultimo giro serve al modello per scrivere
# la risposta e non ne resta nessuno per il lavoro. Il ciclo qui sotto GIA'
# processa piu' blocchi tool_use della stessa risposta in una sola iterazione
# (vedi il for interno su response.content in chat()); il tetto contava i
# round-trip, non le chiamate. Decisione del proprietario: il parallelismo si
# insegna nel prompt (BASE_TOOL_RULES) E il tetto sale, da 10 a 50 --
# piu' raro restare senza margine, il messaggio di esaurimento resta
# necessario (R4) ma non e' piu' la prima difesa.
MAX_TOOL_ITERATIONS = 50
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]

AUTO_MODEL_MAP: dict[str, str] = {
    "chat": "claude-sonnet-4-6",
    "agent": "claude-haiku-4-5-20251001",
}
# Il turno di una promessa "chiedi" (`keeper/exchange.py::interpreta_promise`)
# ragiona come un turno di chat -- confronta un valore con un'istantanea,
# giudica se una condizione si e' verificata -- e per giunta gira SENZA
# nessuno davanti: e' il caso in cui la qualita' del modello conta di piu',
# non di meno, non un lavoro leggero da ripiegare su "agent" (haiku). Prima
# di questa voce, `resolve_model("auto", "promessa", "")` ripiegava sulla
# costante `MODEL` -- che vale lo stesso di `AUTO_MODEL_MAP["chat"]` solo per
# coincidenza, non perche' le due cose fossero legate: le due costanti
# potevano divergere senza che nessun test se ne accorgesse (review finale
# della fetta «lo schedulatore», rilievo minore). Si punta alla chiave
# "chat", non a una stringa duplicata: nessun doppione.
AUTO_MODEL_MAP["promessa"] = AUTO_MODEL_MAP["chat"]

from .backends.pricing import get_price as _price


def resolve_model(model: str, agent_type: str, default_model: str = "") -> str:
    if model == "auto":
        return default_model or AUTO_MODEL_MAP.get(agent_type, MODEL)
    return model

# Models that support Anthropic Extended Thinking. For others (e.g. Haiku 4.5,
# Sonnet < 4.5) the API errors with 400 if `thinking` is supplied. Pattern-based
# so future model strings (claude-sonnet-4-7, claude-opus-4-8 ...) work without
# editing this list.
_THINKING_CAPABLE_PATTERNS = ("sonnet-4-5", "sonnet-4-6", "sonnet-4-7", "opus-4")


def _build_thinking_param(
    thinking_budget: int, effective_model: str, max_tokens: int
) -> dict | None:
    """Build the `thinking` kwarg for Anthropic messages.create, or None.

    Returns None when thinking is disabled / unsupported by the model.
    The runner silently disables thinking on non-capable models to avoid
    surprising the user with an API 400.

    fetta E4 Task 9 (il conto): qui c'era scritto "frontend validation already
    prevents this for new agents but legacy agents.json may carry stale
    combos". Entrambe le meta' sono false al presente. `agents.json` (e il suo
    successore `chatbots.json`) non ha piu' nessun lettore dalla fetta E4
    Task 4 -- l'unico `thinking_budget` che arriva fin qui e' quello di
    `ChatSettings`, col default nel codice -- e la "frontend validation"
    stava nell'editor Chatbot, che dalla fetta E4 Task 3 non puo' piu'
    persistere niente (PUT /api/chatbots/{id} non esiste). Il guard resta
    perche' la coppia modello/thinking non la riverifica nessuno:
    `thinking_budget` (default 0, cioe' disattivo) puo' diventare non-zero
    solo scrivendo a mano `impostazioni_chat.json`, mentre il modello cambia
    da `#/models`, che e' vivo.
    """
    if thinking_budget <= 0:
        return None
    if not any(p in effective_model for p in _THINKING_CAPABLE_PATTERNS):
        logger.warning(
            "thinking_budget=%d but model %s is not thinking-capable — disabling",
            thinking_budget, effective_model,
        )
        return None
    if thinking_budget < 1024:
        logger.warning(
            "thinking_budget=%d below Anthropic minimum 1024 — disabling", thinking_budget
        )
        return None
    if thinking_budget >= max_tokens:
        clamped = max_tokens - 1
        if clamped < 1024:
            logger.warning(
                "thinking_budget=%d >= max_tokens=%d and max_tokens too small for minimum 1024 "
                "— disabling",
                thinking_budget, max_tokens,
            )
            return None
        logger.warning(
            "thinking_budget=%d >= max_tokens=%d — clamping to %d",
            thinking_budget, max_tokens, clamped,
        )
        thinking_budget = clamped
    return {"type": "enabled", "budget_tokens": thinking_budget}


# fetta E4 Task 8, Step 2: il testo precedente invitava l'utente a farsi
# creare «una dashboard con molte stanze ... prima la dashboard con poche
# viste, poi una vista/stanza alla volta» -- una capacita' che HIRIS 2.0 non
# ha piu' (vedi il commento su CHAT_MAX_TOKENS): il messaggio prometteva
# all'UTENTE cio' che i prompt di sistema promettevano al MODELLO, stesso
# difetto in un'altra superficie. Riscritto su cio' che la chat sa fare oggi:
# conoscere e rispondere.
_TRUNCATION_NOTICE = (
    "⚠️ La risposta è stata troncata perché ha raggiunto il limite di token "
    "(max_tokens). Prova a restringere la domanda — una stanza per volta, un "
    "argomento per volta — invece di chiedere tutto in una risposta sola."
)


def _max_tokens_message(text_blocks: list[str]) -> str:
    """Message returned when generation is cut off by max_tokens. Surfaces the
    truncation explicitly instead of returning a misleading partial preamble
    (which reads as 'done' to the user while nothing was actually executed)."""
    prefix = "\n".join(text_blocks).strip()
    return f"{prefix}\n\n{_TRUNCATION_NOTICE}" if prefix else _TRUNCATION_NOTICE


# fetta "i riferimenti" (R4, Task 6): il gemello di _TRUNCATION_NOTICE qui
# sopra. Prima dell'esaurimento delle iterazioni-strumenti rispondeva la
# stringa inglese hardcoded "Max tool iterations reached." -- identica byte
# per byte nel ramo tool_use di chat() qui sotto e in
# backends/openai_compat_runner.py -- senza nessun log. Una casa sola, non
# due costanti con parentela dichiarata (il pattern usato quando due strati
# NON possono importare l'uno dall'altro senza invertire la gerarchia, come
# action/journal.py::CONSERVAZIONE_ESECUZIONI_S rispetto a
# keeper/promise.py::CONSERVAZIONE_S): qui la gerarchia va gia' in un
# verso solo -- backends/openai_compat_runner.py importa GIA' da questo
# modulo (_TRUNCATION_NOTICE, RESTRICT_PROMPT, COMPACT_PROMPT, MINIMAL_
# PROMPT), mai il contrario -- quindi definirla due volte sarebbe il
# doppione che CLAUDE.md:70-72 vieta, non una necessita' strutturale.
_MAX_ITERATIONS_NOTICE = (
    "⚠️ Il turno si è fermato perché ha esaurito i passi disponibili con gli "
    "strumenti. Quello che ho già verificato o eseguito resta valido — prova "
    "a dividere la richiesta in parti più piccole (una stanza, un controllo "
    "alla volta) e a ripetere quella rimasta in sospeso."
)


RESTRICT_PROMPT = (
    "Sei HIRIS, assistente per la smart home. "
    "Rispondi SOLO a domande relative alla casa, domotica, energia, clima, sicurezza. "
    "Per qualsiasi altro argomento, rispondi educatamente che non puoi aiutare su quel tema."
)

# fetta "il ponte riceve il nucleo" (parita' A, Task 3): i due modificatori di
# `response_mode` erano ricopiati TRE volte -- qui sotto (uso originale) e nei
# due punti gemelli di backends/openai_compat_runner.py (`chat` e
# `chat_stream`). Farli attraversare anche il ponte (agent/prompts.py) senza
# prima unificarli avrebbe aggiunto la QUARTA copia -- il doppione che
# CLAUDE.md:70-72 vieta. Estratti qui accanto a RESTRICT_PROMPT (stessa
# natura: testo di prompt, non logica) e importati dai tre punti d'uso
# esistenti PIU' il quarto (prompts.build_chat_messages). Testo spostato alla
# lettera, byte per byte: invariato rispetto a prima di questo task.
COMPACT_PROMPT = "Rispondi in modo conciso, massimo 2-3 frasi."
MINIMAL_PROMPT = (
    "Rispondi SOLO in formato chiave: valore, una riga per dato. "
    "Esempio:\nStato: acceso\nTemperatura: 21°C"
)

# Review finale fetta E2, I-5: `CONFIRMATION_COVERED_TOOLS` e
# `REQUIRE_CONFIRMATION_PROMPT` sono uscite. Nominavano cinque strumenti che
# ATTUANO (call_ha_service, trigger_automation, toggle_automation,
# set_input_helper, create_ha_config): nessuno dei cinque esiste in un
# catalogo raggiungibile da nessun runner (chat = KNOWLEDGE_TOOLS;
# Sentinella = soli read + task, ne' l'uno ne' l'altro li offre; e quando
# l'azione e' rientrata, alla fetta «comandare», e' rientrata come UNO
# strumento solo, `execute`, e senza conferme -- vedi i vincoli della fetta).
# L'iniezione nel system prompt (qui sotto e nei
# due punti gemelli di backends/openai_compat_runner.py) istruiva il modello
# a chiedere conferma prima di strumenti che non puo' comunque chiamare --
# una promessa vuota. fetta E4 Task 6 ("un bot solo"): il parametro
# `require_confirmation` stesso e' uscito da `chat()`/`chat_stream()` -- il
# `Chatbot` di cui era un campo di configurazione era gia' uscito al Task 4.


# Review finale fetta E2, I-4: `_redact_stream_tool_calls` e' uscita.
# Redigeva l'OTP di `confirm_pending` prima di emetterlo in un evento SSE
# "done" -- ma `confirm_pending` non e' dichiarato in nessun catalogo
# raggiungibile (KNOWLEDGE_TOOLS, EVALUATION_TOOL_DEFS): un modello non
# puo' emettere un tool_use per un tool mai offerto, quindi il ramo che
# redigeva non era mai raggiungibile da nessun input reale -- un OTP dentro
# un tool input non esiste piu' in tutto il prodotto (l'impianto OTP e'
# uscito col Task 5). `handlers_chat.py`'s `_debug_input` (la controparte
# non-streaming) e' uscita per lo stesso motivo.


# ── Per-call tool-call / thinking-block isolation (review A/#3) ────────────
# ClaudeRunner and OpenAICompatRunner are long-lived singletons shared by
# every interactive chat request AND every scheduler-driven agent run on the
# same event loop. `last_tool_calls`/`last_thinking_blocks` used to be plain
# unlocked instance attributes: chat() reset them to [] then appended after
# `await` points. Two overlapping calls on the SAME runner instance (e.g. a
# chat request racing a background persona run) could interleave their
# resets/appends and leak one call's tool-call inputs (entity IDs,
# memory-recall content, HTTP payloads) into a completely different call's
# debug_payload / SSE `done` event, or silently wipe them.
#
# Fix: back both attributes with a contextvars.ContextVar instead of a plain
# instance attribute, via the _PerCallList descriptor below. asyncio.Task
# creation copies the current Context, and ContextVar.set() inside a Task
# mutates only that Task's own copy — never a sibling Task's. Two concurrent
# Tasks calling chat()/chat_stream() on the very same runner instance
# therefore never observe each other's resets or appends, even though they
# share the object. Within a single Task (the normal, non-overlapping case —
# e.g. handlers_chat.py reading `runner.last_tool_calls` right after
# `await runner.chat(...)`), the value set inside chat() is still visible to
# the caller immediately afterward: that is just a regular attribute read
# within the same unmodified Context, so single-call behavior is unchanged.
#
# The ContextVar objects are module-level so ClaudeRunner and
# OpenAICompatRunner (which imports them below) share the exact same
# isolation buffers, and so LLMRouter (llm_router.py) can proxy its own
# last_tool_calls/last_thinking_blocks properties to the SAME per-call state
# instead of scanning its registered backends for "whichever has a
# non-empty list" (the old LLMRouter property — that scan could return a
# totally different caller's tool calls than the one that just ran through
# the router, amplifying the same race).
_current_tool_calls: "contextvars.ContextVar[list | None]" = contextvars.ContextVar(
    "hiris_current_tool_calls", default=None
)
_current_thinking_blocks: "contextvars.ContextVar[list | None]" = contextvars.ContextVar(
    "hiris_current_thinking_blocks", default=None
)
# Fetta "esce il documentale": qui viveva `_current_pseudonym_map`, la
# ContextVar per-Task della mappa token->PII di ogni scambio. Esce con
# brain/privacy.py (VaultStore/Pseudonymizer): il suo unico scrittore -- il
# ramo del dispatcher che passava `pseudonym_map=` a `dispatch()` -- era gia'
# uscito con la fetta E2 Task 7, e i due `detokenize` che la leggevano
# (handlers_chat.py) lavoravano da allora su un dizionario sempre vuoto.


class _PerCallList:
    """Descriptor for a list attribute backed by a contextvars.ContextVar.

    `obj.attr` reads the current Task's buffer (or `[]` if never set in this
    Task); `obj.attr = value` sets it for the current Task only. See the
    module comment above for the full isolation rationale.
    """

    def __init__(self, var: "contextvars.ContextVar[list | None]") -> None:
        self._var = var

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        # `is not None`, NOT `or []` -- the reset step (chat() does
        # `self.last_tool_calls = []` before any appends) legitimately sets
        # the ContextVar to an empty-but-real list. `val or []` would treat
        # that falsy `[]` as "unset" and hand back a throwaway literal `[]`
        # on every read instead of the stored list, silently discarding every
        # subsequent `.append()` (they'd mutate a list nobody keeps a
        # reference to). Only a genuine `None` (never set in this Task) falls
        # back to a fresh empty list.
        val = self._var.get()
        return val if val is not None else []

    def __set__(self, obj, value) -> None:
        self._var.set(value)


# Fetta "esce il documentale": qui viveva `_PerCallDict`, il descriptor
# gemello di `_PerCallList` per un attributo dict. Il suo unico uso era
# `last_pseudonym_map`, uscito con la pseudonimizzazione.


class ClaudeRunner:
    # Per-call, per-asyncio-Task isolated — NOT shared mutable instance state,
    # even though this object is a long-lived singleton (see comment above).
    last_tool_calls = _PerCallList(_current_tool_calls)
    last_thinking_blocks = _PerCallList(_current_thinking_blocks)

    def __init__(
        self,
        api_key: str,
        read_model=None,
        log_usage=None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        # Il runner non conosce l'archivio dei consumi: conosce una funzione.
        # Stessa disciplina di `read_model` qui sotto -- ed e' cio' che
        # tiene i runner provabili senza costruire mezzo add-on.
        # `None` e' il ramo di libreria e dei test: non deve diventare un
        # AttributeError dentro il ciclo del modello.
        self._log_usage = log_usage
        # fetta «la catena diventa l'unica verita'» (Task 10): il modello NON e'
        # piu' un valore ricevuto alla costruzione. Era la meta' nascosta del
        # difetto peggiore trovato dal progetto: lo STESSO valore aveva effetto
        # immediato sul ponte (`api/handlers_chat._enqueue_chat_job` rilegge
        # `app["models_config"]` a ogni turno) e solo al riavvio qui, e la
        # pagina ne dichiarava uno solo -- sbagliata, non imprecisa
        # (invariante 4: «un valore si applica in un modo solo»).
        # Adesso e' una LETTURA, e la didascalia non serve piu': l'assenza di
        # didascalie e' la cosa piu' onesta che la pagina possa dire di se'.
        # `None` = nessuna lettura, cioe' il comportamento che aveva
        # `default_model=""` (ripiego su AUTO_MODEL_MAP).
        self._read_model = read_model
        # Fetta "esce il documentale": qui c'era `self._is_cloud = True`, con
        # accanto la dichiarazione (gia' corretta dalla fetta E4 Task 9) che
        # nessuno lo leggeva e che serviva a un "always pseudonymize
        # sensitive content" che il prodotto non faceva. L'attributo era
        # scritto e mai letto in QUESTA classe -- verificato con grep: gli
        # unici `_is_cloud` vivi sono quelli di OpenAICompatRunner/
        # OpenRouterRunner, letti da `_backend_noun`. Il Task 9 lo aveva
        # lasciato solo perche' era fuori dal suo perimetro (solo commenti);
        # esce qui, insieme alla pseudonimizzazione che lo giustificava.
        # last_tool_calls / last_thinking_blocks are intentionally NOT
        # initialized here — they are per-call/per-Task class-level
        # descriptors (see above); chat() resets them at the start of every
        # call, scoped to the calling Task.
        # fetta «i consumi, per modello» (22/08/2026): qui vivevano i contatori
        # globali (`total_input_tokens`, `total_output_tokens`,
        # `total_requests`, `total_cost_usd`, `total_rate_limit_errors`,
        # `usage_last_reset`), la loro persistenza (`_load_usage`/`_save_usage`
        # su `usage.json`, col lock che ne serializzava le scritture) e
        # `reset_usage`. Erano la SECONDA casa del consumo -- quella che
        # sommava tutto insieme e non sapeva dire di quale modello parlasse --
        # e sono uscite col loro `usage_path`. Il consumo si scrive adesso in
        # `usage/store.py` attraverso `log_usage`, e i vecchi
        # `usage_*.json` ci entrano una volta sola all'avvio come riga
        # «(prima del dettaglio)»: i file restano sul disco, mai dati
        # dell'utente cancellati in silenzio.

    def _chosen_model(self) -> str:
        """Il modello scelto ADESSO, letto dove vive (l'archivio)."""
        return (self._read_model() if self._read_model else "") or ""

    def _resolve_current_model(self) -> str:
        """Il modello che questo runner userebbe adesso con `model="auto"`.

        Esiste per rendere OSSERVABILE la lettura a caldo: senza, l'unico modo
        di provarla sarebbe intercettare la chiamata all'API."""
        return resolve_model("auto", "chat", self._chosen_model())

    # fetta E4 Task 6 ("un bot solo"): il costruttore perdeva un `dispatcher`
    # "di scorta" -- usato SOLO dal ramo `elif self._dispatcher is not None`
    # dentro `chat()`, uscito con lui in questo stesso task. Nessun chiamante
    # di produzione lo passava mai (fetta E2 Task 7, commit 68d3670: la chat
    # passa SEMPRE il proprio ToolDispatcher per-chiamata, il parametro
    # `dispatcher`/`strumenti` che invece resta -- vedi `chat()` sotto). Un
    # tool richiesto senza un dispatcher per-chiamata degrada comunque a "non
    # disponibile", come faceva gia' prima con `self._dispatcher` sempre
    # `None` per costruzione: nessun comportamento osservabile cambia.
    #
    # fetta E3 Task 8: `set_task_engine` era gia' uscito per lo stesso motivo
    # (zero chiamanti di produzione, inoltrava a un metodo che nessun
    # dispatcher di produzione ha mai avuto).

    def _write_usage(self, model: str, inp: int, out: int,
                     cache_write: int, cache_read: int,
                     cost: float) -> None:
        """Una risposta entra nell'archivio dei consumi, col NOME del modello.

        Fino a questa fetta il nome era qui, in mano, e finiva solo dentro il
        calcolo del costo: i contatori del runner sommavano tutto insieme e
        nessuno poteva piu' sapere quale modello avesse consumato che cosa.

        `token_in` sono i token d'ingresso PURI: la cache ha due campi suoi,
        perche' costa due tariffe diverse (`cache_write`/`cache_read` in
        `pricing.py`) ed e' il numero che dice se il prefisso sta lavorando.
        Il totale che la pagina mostra resta la somma dei tre.
        """
        if self._log_usage is None:
            return
        from .usage.vocabulary import cost_state_and_value

        state, cost_usd = cost_state_and_value(
            "claude", model, cost_dichiarato=None, cost_da_listino=cost)
        self._log_usage(
            "claude", model, token_in=inp, token_out=out,
            cache_read=cache_read, cache_write=cache_write,
            cost_usd=cost_usd, cost_state=state, now=time.time())

    def _write_rejection(self, model: str) -> None:
        """Un 429 si conta sulla riga del modello che l'ha preso.

        `richieste=0`: un rifiuto non e' una richiesta servita. Prima di questa
        fetta i rifiuti erano un numero solo per tutto il prodotto, e non
        dicevano CHI stesse rifiutando -- l'unica cosa che serva sapere quando
        succede.
        """
        if self._log_usage is None:
            return
        self._log_usage(
            "claude", model, richieste=0, errori_rate_limit=1,
            cost_usd=None, cost_state="non_noto", now=time.time())

    # fetta E4 Task 6 ("un bot solo"): `_ensure_today_reset`/`get_chatbot_usage`/
    # `reset_chatbot_usage` sono usciti -- zero lettori di produzione (le
    # rotte usage sono uscite al Task 3, ChatbotEngine al Task 4, MQTT in E3;
    # LLMRouter aveva gli stessi due metodi SOLO per aggregarli su piu'
    # runner, usciti con loro). Vedi il commento sul costruttore per la
    # storia completa.

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        """Single API call with no tools and no retry loop — for classification tasks."""
        kwargs: dict = {"model": MODEL, "max_tokens": 1024, "messages": messages}
        if system:
            kwargs["system"] = system
        try:
            response = await self._client.messages.create(**kwargs)
            return next((b.text for b in response.content if b.type == "text"), "")
        except Exception as exc:
            logger.error("simple_chat failed: %s", exc)
            return ""

    async def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        conversation_history: list[dict] | None = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        tools: list[dict] | None = None,
        dispatcher: Any | None = None,
    ) -> str:
        self.last_tool_calls = []
        # ── System prompt blocks with prompt caching ─────────────────────────
        # Anthropic prompt caching is *cumulative*: a single cache_control
        # breakpoint caches everything from the start of the request up to that
        # point. So all stable per-agent content (BASE, agent prompt, behaviour
        # modifiers) is emitted WITHOUT individual breakpoints, and ONE
        # breakpoint on the last stable block captures them all. The volatile,
        # query-dependent context_str is appended after it, uncached.
        #
        # This keeps the request within Anthropic's hard cap of 4 cache_control
        # breakpoints. Previously BASE, the agent prompt and the last modifier
        # each carried their own breakpoint (3); together with the tool-defs
        # breakpoint and the conversation-history breakpoint that reached 5 on
        # follow-up turns, and the API rejected the request with a 400
        # (regression introduced in v0.9.5, surfaced to the user as a generic
        # "Errore temporaneo del servizio AI" on the 2nd message of a chat).
        system_blocks: list[dict] = [{"type": "text", "text": BASE_SYSTEM_PROMPT}]
        if system_prompt:
            system_blocks.append({"type": "text", "text": system_prompt})
        # Behaviour modifiers — stable per agent config, must precede context_str.
        # Fix m-4 della review totale della fetta "il ponte riceve il nucleo":
        # questa invariante era dichiarata QUI e violata negli altri due punti
        # che compongono la stessa cosa (backends/openai_compat_runner.py,
        # `chat` e `chat_stream`, mettevano i modificatori DOPO `context_str`).
        # Verificata invece di essere data per buona -- e' vera, e la ragione
        # e' il caching per prefisso: qui il breakpoint cumulativo va posato
        # sull'ultimo blocco stabile, di la' e' il prefix caching implicito di
        # OpenAI/Ollama. I due punti gemelli sono stati allineati, non il
        # commento, e l'ordine e' ora pinnato per tutti e tre i composers
        # (`tests/test_composition_order.py`).
        if restrict_to_home:
            system_blocks.append({"type": "text", "text": RESTRICT_PROMPT})
        # fetta E4 Task 6 ("un bot solo"): il parametro `require_confirmation`
        # stesso e' uscito -- vedi il commento sopra `CONFIRMATION_COVERED_
        # TOOLS` (Review finale fetta E2, I-5) per il perche' non aveva gia'
        # piu' alcun effetto sul system prompt da prima di questo task.
        if response_mode == "compact":
            system_blocks.append({"type": "text", "text": COMPACT_PROMPT})
        elif response_mode == "minimal":
            system_blocks.append({"type": "text", "text": MINIMAL_PROMPT})
        # Single cumulative cache breakpoint on the last stable block (captures
        # BASE + agent prompt + modifiers), placed before the volatile context_str.
        system_blocks[-1] = {**system_blocks[-1], "cache_control": {"type": "ephemeral"}}
        if context_str:
            system_blocks.append({"type": "text", "text": context_str})
        effective_model = resolve_model(model, agent_type, self._chosen_model())
        if tools is not None:
            # Il catalogo arriva gia' deciso dal chiamante (es. gli
            # strumenti di ToolDispatcher, home_space/tools.py).
            tools = list(tools)
        else:
            # fetta E3 Task 8: non esiste piu' un catalogo di scorta da cui
            # pescare qui. `EVALUATION_TOOL_DEFS`/`EVALUATION_ONLY_TOOLS`
            # (il catalogo a 18 letture della Sentinella, filtrato con
            # `allowed_tools`) sono usciti insieme al loro unico chiamante,
            # `run_with_actions` -- la Sentinella e' uscita al Task 7. Nessun
            # chiamante di produzione arriva fin qui senza passare
            # `strumenti` (verificato: api/handlers_chat.py, l'unico
            # chiamante di produzione rimasto dalla fetta E4 Task 4, lo passa
            # sempre); i test del "loop mechanic" che chiamano `chat()` senza
            # `strumenti` provano apposta che la conversazione regge
            # comunque, senza tool_use.
            tools = []
        # Cache tool definitions — stable per agent config, reused across turns
        if tools:
            tools = tools[:-1] + [{**tools[-1], "cache_control": {"type": "ephemeral"}}]
        hist = list(conversation_history or [])
        messages: list[dict] = []
        if hist:
            for msg in hist[:-1]:
                messages.append({"role": msg["role"], "content": msg["content"]})
            last = hist[-1]
            content = last["content"]
            if isinstance(content, str):
                cached_content = [
                    {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                ]
            elif isinstance(content, list) and content:
                # Preserve structured blocks; attach cache_control to the last block only
                cached_content = content[:-1] + [
                    {**content[-1], "cache_control": {"type": "ephemeral"}}
                ]
            else:
                cached_content = content  # empty list or unexpected type: skip caching
            messages.append({"role": last["role"], "content": cached_content})
        messages.append({"role": "user", "content": user_message})

        thinking_param = _build_thinking_param(thinking_budget, effective_model, max_tokens)
        # Collect thinking blocks across all tool-use iterations for downstream
        # surfacing in the execution log / chat debug panel.
        self.last_thinking_blocks = []

        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                _api_kwargs: dict = {
                    "model": effective_model,
                    "max_tokens": max_tokens,
                    "system": system_blocks,
                    "tools": tools,
                    "messages": messages,
                }
                if thinking_param is not None:
                    _api_kwargs["thinking"] = thinking_param
                response = await self._call_api(**_api_kwargs)
            except anthropic.APIError as exc:
                logger.error("Claude API error: %s", exc)
                # Il codice e la causa smettono di andare persi qui. La frase
                # per l'utente non cambia -- è quella che legge in chat, e non
                # è il posto dove si spiega un guasto di configurazione -- ma
                # `famiglia`/`codice` arrivano al router, che li scrive nel
                # registro degli esiti: è l'unica strada per cui la pagina
                # Modelli possa dire «credito esaurito (400)» invece di
                # «Attivo». `status_code` è l'attributo di `anthropic.APIError`
                # (assente su `APIConnectionError`, che infatti è
                # «irraggiungibile» per un'altra strada).
                _code = getattr(exc, "status_code", None)
                raise RunnerBackendError(
                    "Errore temporaneo del servizio AI. Riprova tra poco.",
                    family=error_family(exc),
                    code=_code if isinstance(_code, int) else None,
                ) from exc

            for block in response.content:
                if getattr(block, "type", None) == "thinking":
                    self.last_thinking_blocks.append(getattr(block, "thinking", ""))

            inp = response.usage.input_tokens
            out = response.usage.output_tokens
            cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            prices = _price(effective_model)
            cost = (
                inp * prices["input"]
                + cache_creation * prices.get("cache_write", prices["input"] * 1.25)
                + cache_read * prices.get("cache_read", prices["input"] * 0.1)
                + out * prices["output"]
            ) / 1_000_000
            self._write_usage(effective_model, inp, out,
                              cache_creation, cache_read, cost)

            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks)

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        if dispatcher is not None:
                            # ToolDispatcher (e affini) espone la stessa
                            # interfaccia minima -- dispatch(nome, argomenti).
                            # fetta E4 Task 6: il ramo "dispatcher di scorta"
                            # (self._dispatcher, con le kwargs allowed_entities/
                            # allowed_services/allowed_endpoints/chatbot_id/
                            # visible_entity_ids/knowledge_allow_sensitive/
                            # knowledge_kinds) e' uscito -- zero chiamanti di
                            # produzione lo popolavano (fetta E2 Task 7,
                            # commit 68d3670).
                            result = await dispatcher.dispatch(block.name, block.input)
                        else:
                            # ne' un dispatcher per-chiamata: lo strumento non
                            # e' eseguibile. Mai sollevare qui: un dizionario
                            # leggibile dal modello, come ogni altro dispatch()
                            # di questo ramo.
                            # Minor #7 review finale: questo degrado e'
                            # dichiarato al modello ma prima non lasciava
                            # traccia in log.
                            logger.debug(
                                "Strumento '%s' richiesto ma nessun dispatcher disponibile "
                                "(degradazione dichiarata, non un errore)", block.name)
                            result = {"error": f"Strumento '{block.name}' non disponibile."}
                        self.last_tool_calls.append({"tool": block.name, "input": block.input})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                messages.append({"role": "user", "content": tool_results})
                _compress_old_tool_results(messages)
            elif response.stop_reason == "max_tokens":
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return _max_tokens_message(text_blocks)
            else:
                logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks) if text_blocks else f"Stopped: {response.stop_reason}"

        # fetta "i riferimenti" (R4, Task 6): l'esaurimento non e' piu' muto.
        # `self.last_tool_calls` e' gia' in mano (popolato ad ogni giro poco
        # sopra) -- riusato qui, non un secondo tracciamento. Solo i NOMI
        # degli strumenti, mai `input`: puo' portare dati personali (nomi di
        # stanza, valori impostati, ...).
        logger.warning(
            "chat(): esaurite %d iterazioni senza risposta finale -- strumenti chiamati: %s",
            MAX_TOOL_ITERATIONS, [c["tool"] for c in self.last_tool_calls],
        )
        return _MAX_ITERATIONS_NOTICE

    async def chat_stream(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        conversation_history: list[dict] | None = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        tools: list[dict] | None = None,
        dispatcher: Any | None = None,
    ):
        """Async generator yielding SSE-formatted lines for the chat response.

        Phase 1 implementation: awaits the full chat() response, then slices it
        into 80-char chunks for SSE framing. The client sees all tokens arrive
        after the full Claude round-trip (same latency as non-streaming).
        Phase 2 will replace this with true Anthropic streaming API calls.

        Yields lines in the form:
          'data: {"type": "token", "text": "<chunk>"}\\n\\n'
          'data: {"type": "done", "tool_calls": [...]}\\n\\n'
          'data: {"type": "error", "message": "<msg>"}\\n\\n'

        fetta E4 Task 6 ("un bot solo"): il campo `agent_id` del done-event e'
        uscito -- il grep su static/ trovava un solo lettore del `done` event
        (la card Lovelace) e leggeva SOLO `evt.type`, mai `evt.agent_id`; la
        pagina chat (send.js) non usa nemmeno lo streaming. Nessun lettore
        vivo, dichiarato per la E5 (docs/design/2026-08-08-frontend-da-
        rifare.md non lo elenca: non c'era nulla da riparare). fetta E5 Task
        5: la card e' uscita dal prodotto, quindi `chat_stream()` non ha
        oggi **nessun** lettore nel frontend -- la pagina chat resta sul
        turno sincrono. Non e' codice morto (il ponte e i test lo usano), ma
        e' una superficie senza superficie: dichiarato per il Task 10.

        fetta E4 Task 6, fix round 1 (Important 1 della review indipendente):
        `user_id` e' uscito anche lui da `chat()`/`chat_stream()` -- il suo
        unico lettore era `user_id=user_id` dentro il ramo di scorta
        `elif self._dispatcher is not None` rimosso da questo stesso task
        (era nel commit iniziale insieme agli altri otto kwarg orfani, ma
        sfuggito al primo giro: verificato ora con lo stesso grep dello
        Step 1, zero lettori in produzione).

        `strumenti`/`dispatcher` (Task 3 of the nucleo-alla-chat slice):
        forwarded to `self.chat()` unchanged -- since this generator is
        already just a thin wrapper around it (see Phase 1 above), accepting
        the two here and passing them through is enough to keep the SSE path
        (Lovelace card) and the non-streaming path (chat page) offering the
        SAME tools/context, instead of the card silently keeping the old
        34-tool catalog while the page switched to the four that know the
        house.
        """
        import json as _json
        try:
            result = await self.chat(
                user_message=user_message,
                system_prompt=system_prompt,
                context_str=context_str,
                conversation_history=conversation_history,
                model=model,
                max_tokens=max_tokens,
                agent_type=agent_type,
                restrict_to_home=restrict_to_home,
                response_mode=response_mode,
                thinking_budget=thinking_budget,
                tools=tools,
                dispatcher=dispatcher,
            )
        except Exception as exc:
            yield f'data: {_json.dumps({"type": "error", "message": str(exc)})}\n\n'
            return

        chunk_size = 80
        for i in range(0, len(result), chunk_size):
            yield f'data: {_json.dumps({"type": "token", "text": result[i:i + chunk_size]})}\n\n'

        tool_calls = self.last_tool_calls if isinstance(self.last_tool_calls, list) else []
        yield f'data: {_json.dumps({"type": "done", "tool_calls": tool_calls})}\n\n'

    # fetta E3 Task 8: `run_with_actions` e' uscito. Girava un passaggio
    # agentico ristretto a `EVALUATION_ONLY_TOOLS` (le 18 letture) per conto
    # di UN solo chiamante: `watcher/reasoner.py::_llm_reason`, la Sentinella
    # -- uscita per intero al Task 7 di questa fetta. Senza quel chiamante,
    # `run_with_actions` non aveva piu' nessuno a cui rispondere; usciva
    # insieme ai due cataloghi che esistevano solo per lui
    # (`EVALUATION_TOOL_DEFS`/`EVALUATION_ONLY_TOOLS`, sopra) e alla cartella
    # `tools/` da cui quei cataloghi pescavano le 18 definizioni.

    async def _call_api(self, **kwargs) -> Any:
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await self._client.messages.create(**kwargs)
            except anthropic.APIStatusError as exc:
                if exc.status_code in (429, 529) and attempt < MAX_RETRIES:
                    self._write_rejection(kwargs.get('model') or '')
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        "Rate limit (attempt %d/%d), retry in %ds", attempt + 1, MAX_RETRIES, delay
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

