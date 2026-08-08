from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ..brain.knowledge_store import confronta_significati

if TYPE_CHECKING:
    from ..brain.knowledge_store import KnowledgeStore
    from ..backends.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# Il messaggio che il modello legge -- e che quindi arriva all'utente. Dice
# cosa NON e' successo e perche' conta, mai il dettaglio tecnico: l'eccezione
# resta nel log del server (regola del repo, mai echo di str(exc)).
_ERRORE_SALVATAGGIO = (
    "Non sono riuscito a salvare questo ricordo. Riprova più tardi."
)

# Rifiutato ad alta voce (mai troncato in silenzio): il modello deve poter
# reagire, quindi il messaggio dice anche cosa fare -- accorciare il testo o
# dividerlo in più ricordi -- non solo che il limite e' stato superato.
_ERRORE_LUNGHEZZA = (
    "Il contenuto supera il limite di 1000 caratteri. Accorcialo oppure "
    "dividilo in più ricordi separati."
)

# Idem per un `kind` fuori vocabolario: 'insight' o 'brain-action' scrivono
# nei namespace del digest storico e delle tracce del Brain -- indistinguibili
# da righe generate dalla macchina, condivise con tutta la casa, senza
# scadenza. Anthropic filtra sull'enum dello schema, ma i backend
# OpenAI-compatibili e il gateway MCP potrebbero non farlo: va controllato qui.
_ERRORE_KIND = (
    "Tipo di ricordo non valido: '{kind}'. Usa uno tra: {validi}."
)

# `kind` che il modello puo' scegliere. 'memory' e' il default (ricordo
# generico di questo agente, kind fisso del vecchio save_memory); gli altri
# cinque sono il vocabolario del vecchio save_knowledge -- vivono nella
# stessa colonna, quindi nello stesso enum.
_KINDS_VALIDI = ("memory", "fact", "preference", "obligation", "expense", "note")

# `LEGACY_TOOL_ALIASES` e `normalize_tool_names` sono state spostate in
# chatbot_engine.py: non sono uno strumento, sono una normalizzazione di
# alias legacy dei nomi di tool, usata anche da api/handlers_execute.py.

RECALL_MEMORY_TOOL_DEF = {
    "name": "recall_memory",
    "description": (
        "Cerca in ciò che HIRIS ricorda: preferenze, fatti, scadenze, spese, "
        "appunti e ricordi di conversazioni passate -- un unico archivio, non uno "
        "per ogni tipo. Usa questo strumento prima di rispondere a domande dove "
        "il contesto passato potrebbe aiutare. Se la memoria semantica non è "
        "disponibile (nessun embedder configurato, o il calcolo del vettore "
        "fallisce), il risultato porta `degraded: true` e restituisce i ricordi "
        "più recenti invece dei più pertinenti: in quel caso vanno presentati "
        "come 'i più recenti', non come 'i più pertinenti', perché il confronto "
        "dei significati non è avvenuto. In quella modalità l'archivio documenti "
        "non viene affatto consultato: i risultati riguardano solo ciò che è "
        "stato scritto come testo (mai i documenti caricati), e questo va detto "
        "invece di lasciar intendere che l'archivio sia stato controllato."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query in linguaggio naturale per la ricerca semantica",
            },
            "k": {
                "type": "integer",
                "description": "Numero massimo di risultati da restituire (default 5, max 20)",
                "default": 5,
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Filtro opzionale per tag — restituisce solo ricordi "
                    "con almeno uno di questi tag"
                ),
            },
        },
        "required": ["query"],
    },
}

SAVE_MEMORY_TOOL_DEF = {
    "name": "save_memory",
    "description": (
        "Salva qualcosa che vale la pena ricordare: una preferenza, un fatto, "
        "una scadenza, una spesa o un appunto -- un solo strumento per tutto, "
        "senza chiedere permesso: si salva SUBITO, non c'è coda di approvazione. "
        "Usa `kind` per dire di cosa si tratta ('fact', 'preference', "
        "'obligation', 'expense', 'note'); omesso, vale 'memory' — un ricordo "
        "generico legato a questo agente. Per una scadenza o una spesa valorizza "
        "anche `due_date`/`amount`/`category` quando li conosci: sono ciò che "
        "permette di chiedere poi 'quali scadenze questo mese' invece di "
        "cercare a tentoni. Un ricordo di kind='memory' non scade mai, "
        "esattamente come ogni altro tipo: ciò che dici lo sa HIRIS, non "
        "scompare perché è passato del tempo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Testo da ricordare (max 1000 caratteri)",
            },
            "kind": {
                "type": "string",
                "enum": list(_KINDS_VALIDI),
                "description": (
                    "Tipo di ricordo. Omesso = 'memory' (ricordo generico "
                    "legato a questo agente, non scade mai)."
                ),
            },
            "title": {"type": "string"},
            "amount": {"type": "number"},
            "due_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
            "category": {"type": "string"},
            "sensitivity": {"type": "string", "enum": ["normal", "sensitive"]},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Tag opzionali per categorizzare il ricordo, "
                    "es. ['preferenza', 'utente', 'orario']"
                ),
            },
        },
        "required": ["content"],
    },
}


async def handle_save_memory(
    store: "KnowledgeStore",
    # `None` e' un valore previsto, non una svista: il dispatcher passa
    # l'embedder cablato, che puo' non esserci (provider non configurato). Il
    # codice qui sotto lo controlla gia'; l'annotazione lo dichiara.
    embedder: "EmbeddingProvider | None",
    tool_input: dict,
    *,
    owner: str,
    chatbot_id: str,
    source: str = "chat",
) -> dict:
    """Unico strumento di salvataggio (Task 2 -- fetta memoria unica): scrive
    nella stessa KnowledgeStore che scriveva il vecchio save_memory (ricordo
    generico dell'agente, kind fisso 'memory') E il vecchio save_knowledge
    (fatto/preferenza/scadenza/spesa/nota, kind scelto dal modello). Erano la
    stessa funzione su due nomi: qui sono una sola.

    status='approved' SEMPRE (design memoria-unica §2①): niente più coda di
    approvazione. E' un cambio di comportamento per cio' che prima passava da
    save_knowledge (nasceva 'pending'); save_memory scriveva gia' cosi'.

    Scadenza: NESSUNA, per qualunque kind (Task 6, "la memoria non evapora" --
    design memoria-unica §2③). Un kind='memory' guadagnava una scadenza da
    `retention_days` (il vecchio save_memory calcolava `valid_until` a 90
    giorni per impostazione predefinita); quel calcolo e' stato rimosso
    perché ciò che HIRIS sa della casa non deve svanire perché è passato un
    trimestre -- le tre memorie reali di produzione (chi amministra la casa,
    come rispondere a "chi c'è in casa", il modulo meteo esterno guasto)
    erano tutte a un passo dallo sparire per questa stessa ragione. Ogni
    kind resta senza scadenza, esattamente come già faceva il vecchio
    save_knowledge per i suoi.

    Ambito: chi ha scritto la riga si registra ancora (`chatbot_id` per un
    kind='memory', provenienza -- azzerata dalla pulizia alla cancellazione
    di un chatbot, vedi `KnowledgeStore.detach_chatbot_id`), ma dalla Task 3
    (memoria unica) NON delimita piu' chi puo' vedere la riga:
    `_clausole_di_scope` non la legge. Cio' che dici lo sa HIRIS, non il
    chatbot con cui parlavi -- un ricordo kind='memory' e' visibile a
    chiunque condivida l'owner della riga, parlando con qualunque chatbot,
    esattamente come lo era gia' ogni altro kind. Da questa fetta i due
    rami sotto differiscono solo per la provenienza registrata (chatbot_id
    o niente), non piu' anche per la scadenza: e' lo stesso strumento a
    decidere quale dei due, guardando `kind` invece del nome del tool
    chiamato.

    I campi strutturati (title/amount/due_date/category/sensitivity) sono
    sempre opzionali e si applicano a qualunque kind, memory incluso: sono
    una proprieta' dell'elemento, non un privilegio di alcuni tipi.

    Senza embedding il ricordo resta comunque scritto: `KnowledgeStore.search`
    degrada a `recent()` (piu' recenti prima, stessi filtri di riservatezza)
    quando non c'e' un vettore di query, quindi resta comunque ritrovabile.
    Se un embedder c'e' e funziona, il vettore si calcola e si salva; se non
    c'e', non risponde, o solleva, si salva comunque senza vettore.

    `source` (Fix 1, whole-branch review, final fix wave): il dispatcher lo sceglieva in
    base a CHI aveva chiamato, non a cosa era stato salvato -- "chat" per ogni
    chiamante locale (chat in-addon, chat-via-abbonamento via MCP interno),
    "gateway" per una richiesta arrivata dal gateway MCP remoto
    (`ToolDispatcher.dispatch(from_remote_gateway=True)`, thread da
    `api/handlers_execute.py` -- entrambi gia' usciti: l'MCP remoto in fetta
    E2 Task 4, il dispatcher in Task 7). Il default resta "chat" per chi chiama questa
    funzione direttamente (nessun chiamante di produzione lo fa: passa sempre
    da dispatch()). Solo "chat" e' in `DECLARED_SOURCES`
    (brain/knowledge_store.py): una riga scritta dal gateway resta
    richiamabile via recall_memory ma non entra mai nel blocco "dichiarato da
    una persona" iniettato in automatico in ogni prompt.
    """
    content = tool_input["content"]
    if len(content) > 1000:
        return {"error": _ERRORE_LUNGHEZZA}
    kind = tool_input.get("kind") or "memory"
    if kind not in _KINDS_VALIDI:
        return {"error": _ERRORE_KIND.format(
            kind=kind, validi=", ".join(_KINDS_VALIDI),
        )}
    tags = tool_input.get("tags") or []
    try:
        embedding = await embedder.embed(content) if embedder is not None else None
    except Exception:
        logger.exception("save_memory: embedding non calcolato, salvo senza vettore")
        embedding = None

    # Provenienza, non ambito (Task 3): azzerata dalla pulizia alla
    # cancellazione di un chatbot, non letta da _clausole_di_scope -- vedi
    # KnowledgeStore.detach_chatbot_id. Nessuna scadenza per nessun kind
    # (Task 6): valid_until non si calcola piu' qui, per nessun ramo.
    provenance_chatbot_id: str | None = chatbot_id if kind == "memory" else None

    loop = asyncio.get_running_loop()
    try:
        item_id = await loop.run_in_executor(
            None,
            lambda: store.add_item(
                kind=kind,
                content=content,
                owner=owner,
                chatbot_id=provenance_chatbot_id,
                title=tool_input.get("title", ""),
                data={"tags": tags},
                amount=tool_input.get("amount"),
                due_date=tool_input.get("due_date"),
                category=tool_input.get("category"),
                embedding=embedding or None,
                sensitivity=tool_input.get("sensitivity", "normal"),
                source=source,
                status="approved",
            ),
        )
    except Exception:
        # Il dettaglio (percorsi, host, stringhe di connessione) resta nel log
        # del server: al modello va il fatto, non il messaggio dell'eccezione.
        logger.exception("save_memory: scrittura fallita")
        return {"error": _ERRORE_SALVATAGGIO}
    return {"saved": True, "id": item_id}


async def handle_recall_memory(
    store: "KnowledgeStore",
    embedder: "EmbeddingProvider | None",   # None previsto: vedi handle_save_memory
    tool_input: dict,
    *,
    owner: str,
    allow_sensitive: bool = False,
    kinds: list[str] | str | None = None,
    pseudonymizer: Any = None,
    cloud: bool = True,
    pseudonym_map: dict[str, str] | None = None,
) -> dict:
    """Unico strumento di richiamo (Task 2): sostituisce il vecchio
    recall_memory (forzava kinds=['memory']) E il vecchio recall_knowledge
    (kinds libero, chunk documentali, pseudonimizzazione cloud). Qui non c'e'
    piu' un kind forzato -- di default (kinds=None) la ricerca copre tutto
    cio' che questo owner puo' vedere, memory compresa: e' il punto
    dell'unificazione, non un effetto collaterale.

    Il vecchio recall_memory forzava kinds=['memory'] per proteggere il
    filtro di egress per-kind di un agente (knowledge_access.kinds) da un
    bypass: un agente ristretto a kinds=['fact'] non doveva poter leggere
    spese passando dal tool "memoria" invece che da quello "conoscenza".
    Con un solo strumento quel meccanismo non serve piu' come automatismo
    incorporato nel nome del tool -- il chiamante (dispatcher, dal config
    knowledge_access.kinds dell'agente) puo' ancora restringere passando
    `kinds` esplicitamente, e la restrizione resta rispettata.

    Niente piu' `chatbot_id` (Task 3, memoria unica): non c'e' piu' nulla da
    passare a `KnowledgeStore.search`, che non lo legge -- cio' che dici lo
    sa HIRIS, non il chatbot con cui parlavi, quindi il richiamo copre tutto
    cio' che questo owner puo' vedere a prescindere da quale chatbot lo
    chiede."""
    k = min(max(1, int(tool_input.get("k", 5))), 20)
    tags = tool_input.get("tags") or None
    # Senza vettore di ricerca non si e' potuto confrontare i significati.
    # `KnowledgeStore.search` degrada da se' a `recent()` quando riceve un
    # vettore vuoto (stessi filtri di riservatezza, ordine per recenza), quindi
    # qui non serve un ramo: si passa il vettore per quel che e' -- vuoto o
    # pieno -- e il segnale di degradazione arriva nel ritorno.
    # `search_chunks` invece non ha un percorso degradato equivalente (nessuna
    # nozione di "chunk piu' recenti"): senza vettore i chunk vengono
    # semplicemente saltati, invece di restituirli in un ordine arbitrario che
    # sembrerebbe un confronto di significati senza esserlo.
    try:
        qv = await embedder.embed(tool_input["query"]) if embedder is not None else None
    except Exception:
        logger.exception("recall_memory: vettore di ricerca non calcolato")
        qv = None

    loop = asyncio.get_running_loop()

    def _search_and_merge() -> list[dict]:
        # Over-fetch when a tag filter is active so post-filtering doesn't
        # starve the result set below k.
        search_k = k * 4 if tags else k
        items = store.search(
            query_vec=qv or [], k=search_k, owner=owner,
            allow_sensitive=allow_sensitive, kinds=kinds,
        )
        if tags:
            tag_set = set(tags)
            items = [
                r for r in items
                if tag_set.intersection((r.get("data") or {}).get("tags") or [])
            ]
        items = items[:k]
        chunks = store.search_chunks(
            query_vec=qv, k=k, owner=owner, allow_sensitive=allow_sensitive,
        ) if confronta_significati(qv) else []
        # Merge: items carry their own "kind"; chunks use kind="document_chunk".
        merged: list[tuple[float, dict]] = []
        for r in items:
            merged.append((r.get("score", 0.0), {
                "id": r["id"], "kind": r["kind"], "content": r["content"],
                "sensitivity": r.get("sensitivity"),
                "tags": (r.get("data") or {}).get("tags") or [],
                "created_at": r.get("created_at"),
            }))
        for c in chunks:
            merged.append((c.get("score", 0.0), {
                "id": c["id"], "kind": "document_chunk", "content": c["content"],
                "sensitivity": c.get("sensitivity"),
            }))
        merged.sort(key=lambda x: x[0], reverse=True)
        out = []
        for _score, row in merged[:k]:
            sens = row.pop("sensitivity")
            content = row["content"]
            # Mirror the store's own semantics (knowledge_store.search/
            # search_chunks gate on `sensitivity='normal'` -- i.e. ANY
            # non-'normal' value is treated as sensitive there), not an exact
            # match on the literal string "sensitive".
            is_sensitive = (sens or "normal") != "normal"
            if is_sensitive and cloud:
                if pseudonymizer is not None:
                    # Record token->value into the caller's per-request
                    # mapping so ONLY this exchange's own detokenize call can
                    # ever expand these tokens back.
                    content = pseudonymizer.pseudonymize(content, pseudonym_map)
                else:
                    content = "[contenuto sensibile non disponibile]"
            row["content"] = content
            out.append(row)
        return out

    out = await loop.run_in_executor(None, _search_and_merge)
    return {"results": out, "count": len(out), "degraded": not confronta_significati(qv)}
