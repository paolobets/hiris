"""I prompt del runner del ponte (agent/runner.py), il percorso
chat-via-abbonamento.

fetta E4 Task 8 ("un bot solo"): `_SYSTEM` e `build_holistic_prompt` -- il
prompt della "revisione olistica sull'abbonamento" -- sono usciti con il ramo
che li chiamava. Chiedevano al modello un verdetto e UNA azione a basso
rischio in un blocco ```json```: due cose che HIRIS 2.0 non fa piu' (l'azione
e' uscita con la fetta E2, l'organismo proattivo con la E3) per un job
(`kind="holistic"`) che nessuno puo' piu' accodare.
"""

# Review finale fetta E3, difetto I-1/I-2 dal lato abbonamento: la versione
# precedente diceva al modello «Hai accesso a strumenti per leggere lo stato
# reale della casa (entita', aree, meteo, storico) e, quando serve, per agire
# ... Le azioni possono richiedere una conferma dell'utente» -- tre falsita' in
# tre righe. Questo runner ragiona in PURO TESTO: non riceve alcun catalogo di
# strumenti (l'MCP interno che glieli serviva e' uscito alla fetta E2 Task 3 --
# vedi il docstring in cima a agent/runner.py, e `_chat_claude_args`, che non
# passa ne' `--mcp-config` ne' `--allowedTools`), HIRIS non agisce (fette
# E2/E3), e le conferme sono uscite con l'impianto OTP (fetta E2 Task 5).
#
# fetta E4, fix della review totale (m11): questa riga del prompt diceva
# «HIRIS conosce e non agisce». La formula e' vera del PRODOTTO, non di QUESTO
# percorso: il capoverso immediatamente precedente ha appena detto al modello
# che qui non puo' leggere NULLA della casa. E' una stringa
# di prompt, non un commento: il modello la legge con la stessa autorita' con
# cui gli neghiamo gli strumenti, e «conosce» gli darebbe il permesso di
# credere di sapere. Resta solo «non agisce», che qui e' vero due volte.
#
# Serve anche a CORREGGERE il prompt che lo precede: il system prompt che
# arriva qui e' quello delle impostazioni della chat (`impostazioni_chat.
# DEFAULT_SYSTEM_PROMPT`, via `handlers_chat._build_system_prompt`), scritto
# per il percorso sincrono -- dove i quattro strumenti di
# `casa/strumenti.py` esistono davvero e il nucleo viene appeso al contesto.
# Su QUESTO percorso non esistono ne' gli uni ne' l'altro: il job del ponte
# porta solo `history` + `system_prompt`. Senza questa smentita esplicita il
# modello leggerebbe «usa `cerca` e `guarda`» e non avrebbe modo di scoprire
# che non ci sono -- di nuovo il "preso nota" senza aver salvato, in un'altra
# forma. La disciplina e' quella del nucleo: dichiarare cio' che si ignora
# invece di fingerlo.
_CHAT_TOOL_GUIDANCE = (
    "In questa conversazione NON hai alcuno strumento di HIRIS: non puoi "
    "leggere lo stato della casa (entita', aree, dispositivi, meteo, storico) "
    "ne' salvare o richiamare ricordi. Se il prompt qui sopra nomina degli "
    "strumenti (per esempio `cerca`, `guarda`, `ricorda`, `richiama`) o una "
    "sezione con lo stato della casa, qui non ci sono: quelle istruzioni non "
    "si applicano. Non inventare stati, valori o entita', e non dire di aver "
    "guardato o di aver preso nota di qualcosa.\n"
    "HIRIS non agisce: non accendi, non spegni, non invii notifiche, non "
    "tocchi automazioni. Non c'e' nessuna conferma da "
    "chiedere, perche' non c'e' nessuna azione in attesa.\n"
    "Se per rispondere servirebbe lo stato vivo della casa, DILLO in una "
    "frase -- che in questa conversazione non puoi leggerlo -- invece di "
    "tirare a indovinare. Per il resto rispondi con cio' che sai dalla "
    "conversazione stessa."
)

_CHAT_INSTRUCTION = (
    "Rispondi ORA come l'assistente, proseguendo la conversazione sopra. "
    "Rispondi SEMPRE in italiano, con una risposta breve e pertinente. "
    "Nella risposta finale usa testo semplice: niente blocchi di codice o JSON."
)


def build_chat_messages(system_prompt: str, history: list) -> tuple[str, str]:
    """Chat-via-abbonamento: separa il SYSTEM prompt (persona HIRIS +
    `_CHAT_TOOL_GUIDANCE`) dal prompt UTENTE (trascritto conversazione +
    istruzione formato). Il system va passato al CLI via --system-prompt
    cosi' il modello E' HIRIS e non Claude Code.

    fetta E4 Task 8: questo docstring diceva «e puo' usare i tool MCP» --
    falso dalla fetta E2 Task 3, che ha tolto l'MCP interno insieme al
    server che lo serviva. Il system prompt composto qui e' l'unica cosa
    che il modello riceve, oltre alla trascrizione: nessuno strumento."""
    system_parts = []
    if system_prompt:
        system_parts.append(system_prompt.strip())
    system_parts.append(_CHAT_TOOL_GUIDANCE)
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
