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
ramo sincrono (`claude_runner.py:612-633`): BASE -> persona -> modificatori ->
guida -> contesto. `BASE_SYSTEM_PROMPT` si IMPORTA da `..claude_runner`: una
seconda copia qui sarebbe la "funzione doppia" vietata da CLAUDE.md:70-72.
(Nessun ciclo: `claude_runner.py` importa solo stdlib, `anthropic` e
`.backends.pricing` -- mai `agent/`.)
"""
from ..claude_runner import BASE_SYSTEM_PROMPT

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
# Serve anche a CORREGGERE i prompt che la precedono: al ponte ne arrivano ORA
# DUE, scritti entrambi per il percorso SINCRONO -- `BASE_SYSTEM_PROMPT`
# (claude_runner.py:101: «Usa SEMPRE gli strumenti per dati sulla casa»,
# «chiama ricorda subito») e il system prompt delle impostazioni della chat
# (`impostazioni_chat.DEFAULT_SYSTEM_PROMPT`, via
# `handlers_chat._build_system_prompt`), che nomina i quattro strumenti in
# backtick. Di la' i quattro strumenti di `casa/strumenti.py` esistono
# davvero; QUI no. Senza questa smentita esplicita -- che sta DOPO entrambi,
# ed e' il motivo per cui l'ordine di composizione conta -- il modello
# leggerebbe «usa `cerca` e `guarda`» senza alcun modo di scoprire che non ci
# sono: di nuovo il "preso nota" senza aver salvato, in un'altra forma. La
# disciplina e' quella del nucleo: dichiarare cio' che si ignora invece di
# fingerlo.
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
    "storico) ne' salvare o richiamare ricordi. Se il prompt qui sopra nomina "
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
# Cio' che gli impedisce di diventare vero per sbaglio non e' una convenzione
# ma un pin: `test_argv_del_ponte_non_collega_nessuno_strumento`
# (tests/test_agent_runner_inaddon.py) asserisce che l'argv del ponte non
# porta ne' `--mcp-config` ne' `--allowedTools`, e resta verde per tutta la
# fetta A.
#
# NB per la fetta B: attraverso MCP il modello vede i nomi PREFISSATI dal
# server (`mcp__hiris__cerca`, non `cerca`), e il prefisso dipende dal nome
# che la mcp-config dara' al server -- una decisione della B, non della A. Il
# testo qui sotto nomina entrambe le forme e dichiara che sono gli stessi
# quattro strumenti; la B lo rifinisce quando quel nome e' deciso (riserva 1
# del suo piano).
_GUIDA_CON_STRUMENTI = (
    "In questa conversazione HAI gli strumenti di HIRIS: `cerca` e `guarda` "
    "per lo stato della casa, `ricorda` e `richiama` per la memoria di cio' "
    "che le persone ti hanno detto. Possono comparire col prefisso del server "
    "che te li serve (per esempio `mcp__hiris__cerca`): sono gli STESSI "
    "quattro strumenti nominati qui sopra, non altri.\n"
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
    "Cio' che sai della casa e' la fotografia qui sotto, presa quando e' "
    "arrivato questo messaggio: non e' aggiornabile in questo turno e non "
    "contiene tutto. Usala per rispondere e dichiara apertamente quando cio' "
    "che serve non c'e', ma non presentarla come una lettura fatta adesso."
)

_CONTESTO_ASSENTE = (
    "In questo turno non hai nemmeno la fotografia della casa: questo "
    "messaggio e' arrivato in coda senza il contesto, e non c'e' modo di "
    "recuperarlo ora. Rispondi con cio' che sai dalla conversazione stessa e "
    "dillo apertamente se per rispondere servirebbe conoscere la casa."
)

_CHAT_INSTRUCTION = (
    "Rispondi ORA come l'assistente, proseguendo la conversazione sopra. "
    "Rispondi SEMPRE in italiano, con una risposta breve e pertinente. "
    "Nella risposta finale usa testo semplice: niente blocchi di codice o JSON."
)


def build_chat_messages(system_prompt: str, history: list, *,
                        contesto: str = "",
                        strumenti_attivi: bool = False) -> tuple[str, str]:
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

    L'ordine dei blocchi e' quello del ramo sincrono
    (`claude_runner.py:612-633`), perche' i due percorsi devono comporre le
    stesse cose nello stesso ordine o divergono in silenzio:
    `BASE_SYSTEM_PROMPT` -> `system_prompt` (la persona) -> [i modificatori di
    comportamento, che arrivano al Task 3 di questa fetta] -> la guida ->
    `contesto`. La guida sta DOPO BASE e la persona per poterli smentire:
    sono scritti entrambi per il percorso sincrono e nominano strumenti che
    QUI non esistono.

    `strumenti_attivi` sceglie quale delle due guide entra. Nella fetta A e'
    sempre False (nessun chiamante di produzione lo passa): il ramo True e'
    scritto e non raggiungibile, e lo raccoglie la fetta B -- che cosi' cambia
    un argomento invece di riscrivere il prompt una terza volta."""
    system_parts = [BASE_SYSTEM_PROMPT.strip()]
    if system_prompt:
        system_parts.append(system_prompt.strip())
    # [i modificatori di comportamento -- restrict_to_home, response_mode --
    #  arrivano al Task 3 di questa fetta: nell'ordine del ramo sincrono
    #  stanno fra la persona e il contesto, cioe' esattamente qui.]
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
