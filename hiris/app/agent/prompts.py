"""I prompt del runner del ponte (agent/runner.py), il percorso
chat-via-abbonamento.

fetta E4 Task 8 ("un bot solo"): `_SYSTEM` e `build_holistic_prompt` -- il
prompt della "revisione olistica sull'abbonamento" -- sono usciti con il ramo
che li chiamava. Chiedevano al modello un verdetto e UNA azione a basso
rischio in un blocco ```json```: due cose che HIRIS 2.0 non fa piu' (l'azione
e' uscita con la fetta E2, l'organismo proattivo con la E3) per un job
(`kind="holistic"`) che nessuno puo' piu' accodare.

fetta "il ponte riceve il nucleo" (parita' A, Task 2): il ponte non riceve
piu' soltanto `history` + `system_prompt`. Riceve anche il `contesto` -- la
STESSA stringa che il ramo sincrono passa al runner, composta da
`handlers_chat.componi_contesto_chat` (nucleo + sessioni precedenti). Da qui
in poi questo file compone il system prompt del ponte NELLO STESSO ORDINE del
ramo sincrono (`claude_runner.py`, `ClaudeRunner.chat`): BASE -> persona ->
modificatori -> guida -> contesto. Le costanti di BASE si IMPORTANO da
`..claude_runner`: una seconda copia qui sarebbe la "funzione doppia" vietata
da CLAUDE.md:70-72. (Nessun ciclo: `claude_runner.py` importa solo stdlib,
`anthropic` e `.backends.pricing` -- mai `agent/`.)

Fix round 1, Critical 1: di BASE il ponte compone la sola META' VERA. Vedi
`build_chat_messages` e il commento sopra `BASE_IDENTITA` in claude_runner.py.
"""
# fix della review totale della fetta (m-3): `BASE_SYSTEM_PROMPT` NON e' piu'
# importata. Questo file non la usa -- il ternario di `build_chat_messages`
# compone `BASE_IDENTITA + BASE_REGOLE_STRUMENTI` -- e l'unico lettore che le
# restava era un assert (`prompts.BASE_SYSTEM_PROMPT is BASE_SYSTEM_PROMPT`,
# tests/test_ponte_riceve_il_nucleo.py), cioe' un import tenuto in vita dal
# test che lo pinnava. I due assert sulle META' restano, e sono quelli che
# contano: sono i simboli che il ponte compone davvero.
from ..claude_runner import (
    BASE_IDENTITA,
    BASE_REGOLE_STRUMENTI,
    RESTRICT_PROMPT,
    COMPACT_PROMPT,
    MINIMAL_PROMPT,
)

# Review finale fetta E3, difetto I-1/I-2 dal lato abbonamento: la versione
# precedente diceva al modello «Hai accesso a strumenti per leggere lo stato
# reale della casa (entita', aree, meteo, storico) e, quando serve, per
# agire ... Le azioni possono richiedere una conferma dell'utente» -- tre
# falsita' in tre righe. Questo runner ragiona in PURO TESTO: non riceve alcun
# catalogo di strumenti (l'MCP interno che glieli serviva e' uscito alla fetta
# E2 Task 3 -- vedi il docstring in cima a agent/runner.py, e
# `_chat_claude_args`, che non passa ne' `--mcp-config` ne' `--allowedTools`),
# HIRIS non agisce (fette E2/E3), e le conferme sono uscite con l'impianto OTP
# (fetta E2 Task 5).
#
# fetta E4, fix della review totale (m11): questa riga del prompt diceva
# «HIRIS conosce e non agisce». La formula e' vera del PRODOTTO, non di QUESTO
# percorso: il capoverso immediatamente precedente ha appena detto al modello
# che qui non puo' leggere NULLA della casa. E' una stringa di prompt, non un
# commento: il modello la legge con la stessa autorita' con cui gli neghiamo
# gli strumenti, e «conosce» gli darebbe il permesso di credere di sapere.
# Resta solo «non agisce», che qui e' vero due volte.
#
# Serve anche a CORREGGERE il prompt che la precede: il system prompt delle
# impostazioni della chat (`impostazioni_chat.DEFAULT_SYSTEM_PROMPT`, via
# `handlers_chat._build_system_prompt`) e' scritto per il percorso SINCRONO e
# nomina i quattro strumenti in backtick. Di la' i quattro strumenti di
# `casa/strumenti.py` esistono davvero; QUI no. Senza questa smentita
# esplicita -- che sta DOPO la persona, ed e' il motivo per cui l'ordine di
# composizione conta -- il modello leggerebbe «usa `cerca` e `guarda`» senza
# alcun modo di scoprire che non ci sono: di nuovo il "preso nota" senza aver
# salvato, in un'altra forma. La disciplina e' quella del nucleo: dichiarare
# cio' che si ignora invece di fingerlo.
#
# Fix round 1, Critical 1: fino a poco fa la smentita doveva coprire anche
# `BASE_SYSTEM_PROMPT`, che il Task 2 aveva cominciato a passare INTERO al
# ponte -- ordini come «Usa SEMPRE gli strumenti per dati sulla casa» e
# «chiama ricorda subito» rivolti a un percorso senza strumenti. Non piu': la
# meta' che nomina gli strumenti (`BASE_REGOLE_STRUMENTI`) qui NON viene
# emessa affatto (vedi `build_chat_messages`). La smentita di testo restava
# l'unica difesa contro un ORDINE di chiamare uno strumento inesistente, ed e'
# esattamente il bug per cui `ricorda` e' nato: un ordine non emesso e' una
# difesa, una frase che lo contraddice e' una speranza.
#
# fetta "il ponte riceve il nucleo" (parita' A, Task 2): la frase «non puoi
# LEGGERE lo stato della casa ... o una sezione con lo stato della casa, qui
# non ci sono» e' uscita, perche' da questo task e' FALSA -- il contesto del
# nucleo arriva davvero, e una sezione con lo stato della casa c'e'. Dirla
# ancora sarebbe la falsita' SPECULARE: lo stesso difetto di prima, girato al
# contrario. Cio' che resta vero, e che il prompt continua a dire, e' che non
# si puo' GUARDARE ADESSO: la fotografia e' stata presa una volta sola, quando
# il messaggio e' stato accodato, e in questo turno non si aggiorna.
# L'affermazione e' ancorata al TURNO e non a un'ora perche' il nucleo non
# timbra (`casa/nucleo.py::componi` e' pura e non compone nessuna data): un
# orario nel prompt sarebbe inventato, mentre "in questo turno" e' l'unica
# formulazione che non puo' diventare falsa.
_GUIDA_SENZA_STRUMENTI = (
    "In questa conversazione NON hai alcuno strumento di HIRIS: non puoi "
    "guardare adesso lo stato della casa (entita', aree, dispositivi, meteo, "
    "storico) e non puoi salvare nuovi ricordi ne' andare a cercarne altri "
    "adesso. Se il prompt qui sopra nomina "
    "degli strumenti (per esempio `cerca`, `guarda`, `ricorda`, `richiama`) o "
    "ti ordina di chiamarli, qui non ci sono: quelle istruzioni non si "
    "applicano. Non inventare stati, valori o entita', e non dire di aver "
    "guardato o di aver preso nota di qualcosa.\n"
    "HIRIS non agisce: non accendi, non spegni, non invii notifiche, non "
    "tocchi automazioni. Non c'e' nessuna conferma da "
    "chiedere, perche' non c'e' nessuna azione in attesa.\n"
    "Se per rispondere servirebbe un valore aggiornato ADESSO, DILLO in una "
    "frase -- che in questa conversazione non puoi andare a guardarlo -- "
    "invece di tirare a indovinare."
)

# fetta "il ponte riceve il nucleo" (parita' A, Task 2), Step 3: il ramo della
# fetta B, scritto ORA e deliberatamente NON raggiungibile dalla produzione.
# E' un ORFANO DICHIARATO: `strumenti_attivi` resta False in tutta la fetta A
# (`agent/runner.py::_reason_chat` non lo passa), quindi il suo unico lettore
# oggi e' un test (tests/test_ponte_riceve_il_nucleo.py). Esiste ora, e non
# dopo, perche' riscrivere questo prompt una TERZA volta e' esattamente il
# difetto che il docstring in cima al file documenta: cosi' la fetta B cambia
# un argomento invece di riscrivere la composizione (vedi
# docs/superpowers/plans/2026-08-10-il-ponte-riceve-gli-strumenti.md).
#
# fetta "il ponte riceve gli strumenti" (parita' B, Task 3): l'orfano e' stato
# RACCOLTO -- `_reason_chat` passa `strumenti_attivi` e questo testo esce
# davvero, quando la sonda dice che i quattro strumenti ci sono. Cio' che gli
# impedisce di diventare falso non e' piu' un pin sull'assenza degli strumenti
# ma l'INVARIANTE nei due versi (tests/test_strumenti_al_ponte.py):
# `--mcp-config` nell'argv <=> questo testo nel system. Mai l'uno senza l'altro.
#
# **La correzione di questo testo (riserva 1 della sezione D del progetto).**
# La fetta A non poteva sapere con quale nome il modello avrebbe visto gli
# strumenti, e aveva scritto «Possono comparire col prefisso del server (per
# esempio `mcp__hiris__cerca`)». Ora il nome e' deciso e la frase e' TROPPO
# DEBOLE per essere vera: `_chat_claude_args` passa
# `--allowedTools mcp__hiris__cerca,mcp__hiris__guarda,mcp__hiris__ricorda,
# mcp__hiris__richiama` (i nomi di `runner.nomi_mcp()`, derivati da
# `casa/strumenti.py`), quindi la forma prefissata non e' una possibilita' fra
# due: e' l'UNICA in cui gli strumenti gli sono serviti e l'unica che potra'
# chiamare. Un «possono comparire» lascerebbe il modello a credere che
# `cerca` nudo sia altrettanto valido -- e una chiamata a un nome che non
# esiste e' proprio il modo in cui questo prodotto ha gia' prodotto un «preso
# nota» senza aver salvato. Il testo nomina quindi i quattro nomi VERI, e
# ricollega a loro i nomi nudi che la persona (il system prompt delle
# impostazioni della chat) continua a usare.
_GUIDA_CON_STRUMENTI = (
    "In questa conversazione HAI gli strumenti di HIRIS. Nell'elenco degli "
    "strumenti li trovi col prefisso del server che te li serve, ed e' quella "
    "l'unica forma in cui puoi chiamarli: `mcp__hiris__cerca` e "
    "`mcp__hiris__guarda` per lo stato della casa, `mcp__hiris__ricorda` e "
    "`mcp__hiris__richiama` per la memoria di cio' che le persone ti hanno "
    "detto. Quando il prompt qui sopra parla di `cerca`, `guarda`, `ricorda` o "
    "`richiama` parla di questi STESSI quattro strumenti, non di altri: usa il "
    "nome prefissato per chiamarli.\n"
    "Quando serve un valore CORRENTE chiama lo strumento invece di rispondere "
    "con cio' che leggi nel contesto qui sotto: guarda adesso. Non inventare "
    "stati, valori o entita', e non dire di aver guardato o di aver preso "
    "nota se non hai chiamato lo strumento.\n"
    "HIRIS non agisce comunque: non accendi, non spegni, non invii notifiche, "
    "non tocchi automazioni. Non c'e' nessuna conferma da chiedere, perche' "
    "non c'e' nessuna azione in attesa."
)

# Le due frasi sul CONTESTO, complementari fra loro: una sola delle due entra
# nel prompt, e quale lo decide il `contesto` ricevuto.
#
# Perche' stanno FUORI dalle due guide invece che dentro: un job accodato
# PRIMA di questo deploy arriva al runner senza la chiave `contesto` (silenzio
# dichiarato ①, vedi `agent/runner.py::_reason_chat`). Se «la fotografia qui
# sotto» vivesse dentro `_GUIDA_SENZA_STRUMENTI`, quel job leggerebbe un
# prompt che promette una fotografia che non c'e' -- la stessa falsita' che
# questo task esiste per chiudere, riaperta dal caso limite. Tenendole
# separate la guida resta UNA (un solo posto dove si dice cosa il modello ha e
# non ha) e la frase sul contesto dice sempre il vero.
_CONTESTO_PRESENTE = (
    "Cio' che sai della casa -- e di cio' che le persone ti hanno detto, "
    "ricordi e sessioni precedenti compresi -- e' la fotografia qui sotto, "
    "presa quando e' arrivato questo messaggio: non e' aggiornabile in questo "
    "turno e non contiene tutto. Se ti chiedono cosa ti hanno detto, cercalo "
    "li' dentro invece di rispondere che non puoi richiamarlo. Usala per "
    "rispondere e dichiara apertamente quando cio' che serve non c'e', ma non "
    "presentarla come una lettura fatta adesso."
)

_CONTESTO_ASSENTE = (
    "In questo turno non hai nemmeno la fotografia della casa: questo "
    "messaggio e' arrivato in coda senza il contesto, e non c'e' modo di "
    "recuperarlo ora. Rispondi con cio' che sai dalla conversazione stessa e "
    "dillo apertamente se per rispondere servirebbe conoscere la casa."
)

# Fix della review totale della fetta (m-2): questa istruzione diceva
# «Rispondi SEMPRE in italiano». Era l'UNICA istruzione di lingua che il ponte
# riceveva -- "Rispondi nella lingua dell'utente" viveva in
# `BASE_REGOLE_STRUMENTI`, la meta' che il ponte non emette -- e imponeva al
# ponte una lingua che il percorso sincrono non impone: un utente che scrive
# in inglese riceveva inglese di la' e italiano di qua. Ora quella riga sta in
# `BASE_IDENTITA` (vedi il commento del taglio in claude_runner.py) e arriva
# a ENTRAMBI i percorsi: lasciare qui «SEMPRE in italiano» significherebbe
# contraddirla dentro lo stesso prompt -- il system dice una cosa, l'ultima
# riga dell'utente ne dice un'altra, e vince l'ultima letta. Allineata.
_CHAT_INSTRUCTION = (
    "Rispondi ORA come l'assistente, proseguendo la conversazione sopra. "
    "Rispondi nella lingua dell'utente, con una risposta breve e pertinente. "
    "Nella risposta finale usa testo semplice: niente blocchi di codice o JSON."
)


def build_chat_messages(system_prompt: str, history: list, *,
                        contesto: str = "",
                        strumenti_attivi: bool = False,
                        restrict_to_home: bool = False,
                        response_mode: str = "") -> tuple[str, str]:
    """Chat-via-abbonamento: separa il SYSTEM prompt (BASE + persona HIRIS +
    guida + contesto della casa) dal prompt UTENTE (trascritto conversazione +
    istruzione formato). Il system va passato al CLI via --system-prompt
    cosi' il modello E' HIRIS e non Claude Code.

    fetta E4 Task 8: questo docstring diceva «e puo' usare i tool MCP» --
    falso dalla fetta E2 Task 3, che ha tolto l'MCP interno insieme al server
    che lo serviva.

    fetta "il ponte riceve il nucleo" (parita' A, Task 2): diceva anche che
    «il system prompt composto qui e' l'unica cosa che il modello riceve,
    oltre alla trascrizione» -- vero finche' il job del ponte portava solo
    `history` + `system_prompt`. Ora porta anche `contesto`, la stessa
    stringa che il ramo sincrono passa al runner
    (`handlers_chat.componi_contesto_chat`: nucleo + sessioni precedenti), e
    quella stringa entra in coda al system. Resta vero -- e la guida continua
    a dirlo -- che gli STRUMENTI non ci sono: `contesto` e' una fotografia,
    non un accesso.

    L'ordine dei blocchi e' quello del ramo sincrono (`ClaudeRunner.chat`),
    perche' i due percorsi devono comporre le stesse cose nello stesso ordine
    o divergono in silenzio: BASE -> `system_prompt` (la persona) -> i
    modificatori di comportamento (`restrict_to_home`, `response_mode`) ->
    la guida -> `contesto`. La guida sta DOPO la persona per poterla
    smentire: e' scritta per il percorso sincrono e nomina strumenti che QUI
    non esistono.

    `restrict_to_home` e `response_mode` (Task 3, "il ponte riceve il
    nucleo"): le due impostazioni della chat che sono TESTO di prompt e che,
    prima di questo task, il ponte non riceveva affatto (`_enqueue_chat_job`
    portava solo `history` + `system_prompt`, mentre il ramo sincrono le
    legge gia' da `impostazioni.restrict_to_home`/`.response_mode`,
    `handlers_chat.py`). `RESTRICT_PROMPT`, `COMPACT_PROMPT` e
    `MINIMAL_PROMPT` si IMPORTANO da `..claude_runner` -- sono gia' l'unica
    fonte per il ramo sincrono E per `backends/openai_compat_runner.py`
    (Task 3, Step 1: erano ricopiate li' tre volte prima di questo task);
    una quarta copia qui sarebbe la "funzione doppia" vietata da
    CLAUDE.md:70-72. Applicati fra `system_prompt` e la guida, come
    `claude_runner.py::ClaudeRunner.chat` fa fra i suoi blocchi stabili e il
    breakpoint di cache.

    `strumenti_attivi` sceglie DUE cose insieme, non una (fix round 1,
    Critical 1 della review indipendente):

    1. **quanto di BASE viene emesso.** `BASE_IDENTITA` (chi e' HIRIS, cosa
       conosce) e' vera su entrambi i percorsi ed entra sempre.
       `BASE_REGOLE_STRUMENTI` -- «Usa SEMPRE gli strumenti per dati sulla
       casa», «chiama ricorda subito», «se hai chiamato uno strumento con
       successo l'azione e' reale» -- e' un ORDINE DI CHIAMARE UNO STRUMENTO
       che sul ponte non esiste, e sul ponte non viene emessa affatto. La
       prima stesura di questo task passava BASE intero e lo faceva smentire
       dalla guida che segue: una smentita di testo non e' un meccanismo, e
       il caso peggiore -- «preso nota» senza aver salvato -- e' il bug
       misurato in produzione da cui `ricorda` e' nato. Con
       `strumenti_attivi=True` i due pezzi tornano contigui e il blocco e'
       byte per byte `BASE_SYSTEM_PROMPT`, come nel ramo sincrono;
    2. **quale delle due guide entra.**

    Nella fetta A era sempre False (nessun chiamante di produzione lo
    passava). La fetta "il ponte riceve gli strumenti" (parita' B, Task 3) ha
    raccolto il ramo True cambiando UN ARGOMENTO, senza riscrivere il prompt
    una terza volta: `agent/runner.py::_reason_chat` lo passa, e il valore
    viene dalla sonda `sonda_strumenti` -- lo stesso booleano che decide
    l'argv, due righe piu' sotto. Il default resta False perche' False e' il
    ramo di DEGRADO, e un degrado deve essere cio' che si ottiene quando non
    si sa: un default True prometterebbe strumenti a chi non li ha chiesti."""
    # Con gli strumenti attivi le due meta' tornano adiacenti e il blocco e'
    # esattamente `BASE_SYSTEM_PROMPT`: nessuna terza variante da mantenere.
    base = BASE_IDENTITA + BASE_REGOLE_STRUMENTI if strumenti_attivi else BASE_IDENTITA
    system_parts = [base.strip()]
    if system_prompt:
        system_parts.append(system_prompt.strip())
    # I modificatori di comportamento -- stesso ordine e stesse costanti
    # IMPORTATE del ramo sincrono (claude_runner.py::ClaudeRunner.chat,
    # `if restrict_to_home: ... if response_mode == "compact": ...`).
    if restrict_to_home:
        system_parts.append(RESTRICT_PROMPT)
    if response_mode == "compact":
        system_parts.append(COMPACT_PROMPT)
    elif response_mode == "minimal":
        system_parts.append(MINIMAL_PROMPT)
    guida = _GUIDA_CON_STRUMENTI if strumenti_attivi else _GUIDA_SENZA_STRUMENTI
    contesto = (contesto or "").strip()
    system_parts.append(
        guida + "\n" + (_CONTESTO_PRESENTE if contesto else _CONTESTO_ASSENTE))
    if contesto:
        system_parts.append(contesto)
    system = "\n\n".join(system_parts)

    lines = ["Conversazione finora:"]
    for msg in history or []:
        role = (msg or {}).get("role", "user")
        content = (msg or {}).get("content", "")
        speaker = "Assistente" if role == "assistant" else "Utente"
        lines.append(f"{speaker}: {content}")
    lines.append("")
    lines.append(_CHAT_INSTRUCTION)
    user = "\n".join(lines)
    return system, user
