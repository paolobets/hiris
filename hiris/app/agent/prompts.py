"""I prompt del runner del ponte (agent/runner.py), il percorso
chat-via-abbonamento.

Il ponte riceve `history`, `system_prompt` e il `contesto` -- la STESSA
stringa che il ramo sincrono passa al runner, composta da
`handlers_chat.compose_chat_context` (nucleo + sessioni precedenti). Le parti
stabili del prompt di sistema (identita', regole degli strumenti del turno,
persona, avviso sui nomi di prima, modificatori) e il recinto del contesto non
si compongono qui: li compone `steering` (`compose_system`, `fence_context`),
lo stesso compositore della catena (D-01, D-04, Chiusura, 13/10/2026). Qui
restano solo le cose vere del solo ponte: le due guide (con e senza
strumenti), le frasi sulla fotografia della casa e il trascritto della
conversazione in testo, perche' la CLI non riceve messaggi strutturati.

Il system arriva alla CLI in un file temporaneo (`--system-prompt-file`,
`agent/runner._system_prompt_file`), cosi' il modello E' HIRIS e non Claude
Code. Gli strumenti di HIRIS ci sono quando la sonda li ha trovati
(`active_tools`), serviti da `/api/mcp`; altrimenti entra la guida del ramo
senza strumenti.
"""
from ..steering import compose_system, fence_context

# La guida del ramo SENZA strumenti. Parla di questo TURNO, non del prodotto:
# «non puoi accendere ... perche' lo strumento che lo fa qui non c'e' -- non
# perche' HIRIS non sappia farlo». Senza la seconda proposizione un modello
# negherebbe la capacita' anche a chi gliela chiede per il turno dopo.
#
# Serve anche a CORREGGERE il prompt che la precede: il system prompt delle
# impostazioni della chat (`chat_settings.DEFAULT_SYSTEM_PROMPT`, via
# `handlers_chat._build_system_prompt`) nomina gli strumenti, e qui non ci
# sono. Per questo la smentita sta DOPO la persona -- e' il motivo per cui
# l'ordine di composizione conta -- e nomina gli strumenti PER NEGARLI,
# `execute` compreso. Le regole che ORDINANO di chiamarli
# (`claude_runner.TOOL_RULES`) su questo ramo non vengono emesse affatto:
# `steering.compose_base` le compone per gli strumenti del turno, e un turno
# senza strumenti riceve la sola identita'. Un ordine non emesso e' una
# difesa, una frase che lo contraddice e' una speranza.
#
# Cio' che il testo dice del guardare e' ancorato al TURNO («in questa
# conversazione», «in questo turno») e non a un'ora: la fotografia della casa
# e' presa una volta sola, quando il messaggio e' stato accodato, e in questo
# turno non si aggiorna.
_GUIDE_WITHOUT_TOOLS = (
    "In questa conversazione NON hai alcuno strumento di HIRIS: non puoi "
    "guardare adesso lo stato della casa (entita', aree, dispositivi, meteo, "
    "storico) e non puoi salvare nuovi ricordi ne' andare a cercarne altri "
    "adesso. Se il prompt qui sopra nomina "
    "degli strumenti (per esempio `search`, `remember`, "
    "`execute`) o "
    "ti ordina di chiamarli, qui non ci sono: quelle istruzioni non si "
    "applicano. Non inventare stati, valori o entita', e non dire di aver "
    "guardato o di aver preso nota di qualcosa.\n"
    "In questo turno non puoi nemmeno far succedere niente in casa: non puoi "
    "accendere, spegnere o chiamare un servizio di Home Assistant, perche' "
    "lo strumento che lo fa (`execute`) qui non c'e' -- non perche' HIRIS non "
    "sappia farlo. Non c'e' nessuna conferma da "
    "chiedere, perche' non c'e' nessuna azione in attesa.\n"
    "Se per rispondere servirebbe un valore aggiornato ADESSO, DILLO in una "
    "frase -- che in questa conversazione non puoi andare a guardarlo -- "
    "invece di tirare a indovinare."
)

# La guida del ramo CON gli strumenti. Esce quando la sonda dice che gli
# strumenti ci sono (`agent/runner.py::_reason_chat` passa `active_tools`), e
# cio' che le impedisce di diventare falsa e' l'INVARIANTE nei due versi
# (tests/test_tools_to_bridge.py): `--mcp-config` nell'argv <=> questo testo
# nel system. Mai l'uno senza l'altro.
#
# **Dice solo cio' che e' del ponte** (Tappa 5, Task 5; D-03). Fino al
# 06/10/2026 ripeteva, coi nomi prefissati, sei regole che
# `claude_runner.TOOL_RULES` gia' da' a questo stesso turno (gli id esatti
# per `execute`, gli id fra parentesi, una `search` per piu' nomi, le stanze
# passate a `execute`...): due testi della stessa regola, nello stesso
# prompt. Qui restano i nomi PREFISSATI, la fotografia che non si aggiorna e
# il tetto per chiamata, che sono veri solo sul ponte.
#
# I nomi non sono scritti qui: li compone `guide_with_tools` dagli strumenti
# del turno (D-57). Fino al 06/10/2026 erano un secondo catalogo a mano, e la
# promessa sul ponte leggeva sette strumenti che non aveva e non leggeva
# `conclude`, che e' l'unico modo di finire (D-56).
_GUIDE_WITH_TOOLS = (
    "In questa conversazione HAI gli strumenti di HIRIS. Nell'elenco degli "
    "strumenti li trovi col prefisso del server che te li serve, ed e' quella "
    "l'unica forma in cui puoi chiamarli: quando il testo qui sopra li "
    "nomina col nome nudo (`search`), parla di questi STESSI strumenti, e li "
    "chiami col nome prefissato.\n"
    "Quando serve un valore CORRENTE chiama lo strumento invece di rispondere "
    "con cio' che leggi nel contesto qui sotto: guarda adesso.\n"
    "Qui OGNI chiamata conta nel tetto per-turno, anche quelle parallele: il "
    "risparmio vero e' risolvere piu' nomi con una ricerca sola ed essere "
    "parsimoniosi con le chiamate, non il parallelismo in se'.\n"
)


def guide_with_tools(tools) -> str:
    """La guida del ponte per gli strumenti di QUESTO turno: la parte fissa e
    i nomi prefissati chiesti a `runner.mcp_name` (il prefisso viene dal
    nome del server, `api/handlers_mcp.MCP_SERVER_NAME`). Uno strumento che
    entra nella tabella entra qui da solo. L'avviso sui nomi di prima non sta
    piu' qui: lo da' il compositore, a tutte e due le strade (D-18)."""
    from .runner import mcp_name

    names = ", ".join(f"`{mcp_name(tool)}`" for tool in tools)
    return _GUIDE_WITH_TOOLS + f"I tuoi strumenti in questo turno: {names}.\n"


# Le due frasi sul CONTESTO, complementari fra loro: una sola delle due entra
# nel prompt, e quale lo decide il `contesto` ricevuto.
#
# Stanno FUORI dalle due guide: un job puo' arrivare al runner senza la chiave
# `contesto` (vedi `agent/runner.py::_reason_chat`), e se «la fotografia qui
# sotto» vivesse dentro una guida quel job leggerebbe un prompt che promette
# una fotografia che non c'e'. Tenendole separate la guida resta UNA e la
# frase sul contesto dice sempre il vero.
#
# `_CONTESTO_PRESENTE` esce su entrambi i rami, ed e' vera su entrambi: la
# fotografia esiste, e' presa all'accodamento, non contiene tutto, e non va
# spacciata per una lettura fatta adesso.
#
# Fix del 2026-08-18, da una risposta vera sbagliata. Alla domanda «stato
# casa» il modello ha premesso «dallo snapshot che ho, non e' una lettura in
# tempo reale», ha elencato la fotografia e si e' OFFERTO di guardare adesso.
# Aveva gli strumenti: doveva guardare, non offrirsi.
#
# La riserva qui sotto resta giusta -- la fotografia e' presa all'accodamento
# e non va spacciata per una lettura fatta adesso -- ma da sola insegnava
# soltanto a DIFFIDARNE. Chi diffida di cio' che ha e non usa cio' che puo'
# chiamare produce esattamente quella risposta: un disclaimer al posto di un
# fatto. La riserva e' una ragione per ANDARE A GUARDARE, non per scusarsi.
_CONTESTO_PRESENTE = (
    "Cio' che sai della casa -- e di cio' che le persone ti hanno detto, "
    "ricordi e sessioni precedenti compresi -- e' la fotografia qui sotto, "
    "presa quando e' arrivato questo messaggio: non contiene tutto. Usala per "
    "rispondere e dichiara apertamente quando cio' che serve non c'e', ma non "
    "presentarla come una lettura fatta adesso.\n"
    "Se la domanda riguarda lo STATO CORRENTE della casa -- com'e' adesso, "
    "cosa e' acceso, come sta una stanza -- e hai gli strumenti, CHIAMALI e "
    "rispondi con cio' che ti dicono. Non premettere che la tua e' una "
    "fotografia per poi offrirti di guardare: guarda."
)

_CONTESTO_ASSENTE = (
    "In questo turno non hai nemmeno la fotografia della casa: questo "
    "messaggio e' arrivato in coda senza il contesto, e non c'e' modo di "
    "recuperarlo ora. Rispondi con cio' che sai dalla conversazione stessa e "
    "dillo apertamente se per rispondere servirebbe conoscere la casa."
)

# Fix della review totale della fetta (m-2): questa istruzione diceva
# «Rispondi SEMPRE in italiano». Era l'UNICA istruzione di lingua che il ponte
# riceveva -- "Rispondi nella lingua dell'utente" viveva allora fra le regole
# degli strumenti, che il ponte senza strumenti non emette -- e imponeva al
# ponte una lingua che il percorso sincrono non impone: un utente che scrive
# in inglese riceveva inglese di la' e italiano di qua. Ora quella riga sta in
# `BASE_IDENTITY` (vedi il commento del taglio in claude_runner.py) e arriva
# a ENTRAMBI i percorsi: lasciare qui «SEMPRE in italiano» significherebbe
# contraddirla dentro lo stesso prompt -- il system dice una cosa, l'ultima
# riga dell'utente ne dice un'altra, e vince l'ultima letta. Allineata.
_CHAT_INSTRUCTION = (
    "Rispondi ORA come l'assistente, proseguendo la conversazione sopra. "
    "Rispondi nella lingua di chi ti sta parlando, con una risposta breve e "
    "pertinente. Nella risposta finale usa testo semplice: niente blocchi di "
    "codice o JSON."
)


def build_chat_messages(system_prompt: str, history: list, *,
                        contesto: str = "",
                        active_tools: tuple[str, ...] = (),
                        restrict_to_home: bool = False,
                        response_mode: str = "",
                        istruzione: str = "",
                        hour: str = "") -> tuple[str, str]:
    """Chat-via-abbonamento: separa il SYSTEM prompt dal prompt UTENTE
    (trascritto della conversazione + istruzione di formato). Il system va
    alla CLI in un file (`--system-prompt-file`), cosi' il modello E' HIRIS
    e non Claude Code.

    **Il system lo compone lo stesso compositore della catena** (D-01, D-04,
    D-18; Chiusura, 13/10/2026): le parti stabili da
    `steering.compose_system` (identita', regole degli strumenti di questo
    turno, persona, avviso sui nomi di prima, modificatori), poi la guida del
    ponte, poi il contesto nel recinto di `steering.fence_context`. Fino a
    quel giorno questa funzione accodava a mano persona e modificatori, e
    l'ordine era difeso da una prova (`tests/test_composition_order.py`)
    invece che da un posto solo. La guida sta DOPO la persona per poterla
    smentire quando il turno non ha strumenti: la persona e' scritta per la
    chat e nomina strumenti.

    `contesto` e' una fotografia presa all'accodamento
    (`handlers_chat.compose_chat_context`), non un accesso: per guardare
    adesso servono gli strumenti.

    `active_tools` sono i NOMI degli strumenti di questo turno -- vuoto se
    non ne ha, o se la sonda li ha smentiti -- e sceglie DUE cose insieme:
    quali regole degli strumenti entrano (solo quelle degli strumenti che il
    turno ha: con gli strumenti della chat il blocco e' byte per byte quello
    della catena) e quale delle due guide entra. Il valore viene da
    `agent/runner.py::_reason_chat`: gli strumenti della dichiarazione del
    mestiere se la sonda `probe_tools` li ha trovati, niente altrimenti --
    lo stesso valore che decide l'argv. Il default e' vuoto perche' vuoto e'
    il ramo di DEGRADO, e un degrado deve essere cio' che si ottiene quando
    non si sa.

    `hour` e' l'ora della casa all'accodamento (`steering.house_hour`), che
    il job porta accanto al contesto (la chiave `adesso`): entra nel prompt
    utente, dopo la conversazione."""
    system_parts = [part.strip() for part in compose_system(
        active_tools, persona=system_prompt, restrict_to_home=restrict_to_home,
        response_mode=response_mode)]
    # **Un turno che porta la propria istruzione porta anche il proprio
    # materiale**, e la cornice della chat non lo riguarda (fetta
    # «l'osservatore chiede a chi risponde davvero», 11/09/2026). La coppia
    # guida/contesto parla al modello di una conversazione e di una
    # fotografia della casa: per il turno dell'osservatore la fotografia e'
    # **dentro la domanda** -- 381 righe di entita' con classe, unita', area e
    # chiave di traduzione -- e `_CONTESTO_ASSENTE` gli direbbe il falso
    # («non hai nemmeno la fotografia della casa») invitandolo per giunta a
    # rifiutare invece di rispondere.
    contesto = (contesto or "").strip()
    if not istruzione:
        guida = (guide_with_tools(active_tools) if active_tools
                 else _GUIDE_WITHOUT_TOOLS)
        system_parts.append(
            guida + "\n" + (_CONTESTO_PRESENTE if contesto else _CONTESTO_ASSENTE))
        if contesto:
            # Il contenuto della casa entra RECINTATO e dichiarato materiale
            # (reperto B-2): vedi `steering.APERTURA_CASA` per il perche'.
            system_parts.append(fence_context(contesto))
    system = "\n\n".join(system_parts)

    lines = ["Conversazione finora:"]
    for msg in history or []:
        role = (msg or {}).get("role", "user")
        content = (msg or {}).get("content", "")
        speaker = "Assistente" if role == "assistant" else "Utente"
        lines.append(f"{speaker}: {content}")
    lines.append("")
    # L'ora della casa sta qui, dopo la conversazione, e non nel system: il
    # nucleo resta uguale da un turno all'altro (D-51). Vuota per i turni
    # che non la portano.
    if hour:
        lines.extend((hour, ""))
    # L'istruzione di chiusura della chat impone testo semplice e vieta
    # esplicitamente il JSON; l'osservatore chiede **un solo array JSON**. Il
    # contratto di risposta appartiene a chi pone la domanda, non alla porta
    # che la trasporta.
    lines.append(istruzione or _CHAT_INSTRUCTION)
    user = "\n".join(lines)
    return system, user
