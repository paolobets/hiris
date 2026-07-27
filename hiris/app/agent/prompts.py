import json

_SYSTEM = (
    "Sei il cervello di HIRIS in revisione olistica sull'abbonamento. Ricevi una "
    "fotografia della casa. Segnala SOLO cio' che merita attenzione; non elencare lo "
    "stato normale. Puoi proporre UNA azione a basso rischio pertinente; NON proporre "
    "mai azioni su serrature, allarmi, tapparelle, sirene. Concludi SEMPRE con un blocco "
    "```json``` con i campi verdict('anomalia'|'falso_positivo'), severity('info'|'warn'|"
    "'critico'), message, action(null oppure {domain,service,entity_id,data})."
)

def build_holistic_prompt(snapshot: dict) -> str:
    return f"{_SYSTEM}\n\nFotografia della casa:\n{json.dumps(snapshot, ensure_ascii=False)}\n\nValuta e rispondi col blocco json."

_CHAT_TOOL_GUIDANCE = (
    "Hai accesso a strumenti per leggere lo stato reale della casa (entita', "
    "aree, meteo, storico) e, quando serve, per agire. Usali quando la domanda "
    "richiede dati aggiornati o un'azione. Le azioni possono richiedere una "
    "conferma dell'utente prima di essere eseguite: in quel caso spiega "
    "brevemente che l'azione e' in attesa di conferma."
)

_CHAT_INSTRUCTION = (
    "Rispondi ORA come l'assistente, proseguendo la conversazione sopra. "
    "Rispondi SEMPRE in italiano, con una risposta breve e pertinente. "
    "Nella risposta finale usa testo semplice: niente blocchi di codice o JSON."
)


def build_chat_messages(system_prompt: str, history: list) -> tuple[str, str]:
    """Chat-via-abbonamento: separa il SYSTEM prompt (persona HIRIS + guida
    tool) dal prompt UTENTE (trascritto conversazione + istruzione formato).
    Il system va passato al CLI via --system-prompt cosi' il modello E' HIRIS,
    non Claude Code, e puo' usare i tool MCP."""
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
