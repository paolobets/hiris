"""La decisione già presa: chi risponde al prossimo messaggio, e perché.

Fino alla 2.4.1 la pagina Modelli riceveva gli INGREDIENTI (`providers[]`,
`llm_strategy`, `chain_order`) e ricostruiva da sola l'esito:
`buildDisplayChain` (static/config/models-route.js) riproduceva a mano
`reconcile_chain` (model_activation.py), e il commento di quest'ultima lo
diceva a voce alta -- «This mirrors the frontend's buildDisplayChain». Due
implementazioni della stessa regola, in due linguaggi: non una svista, la
STRUTTURA con cui la pagina ha potuto essere vera riga per riga e falsa nel
complesso.

Qui si compone la DECISIONE. La pagina disegna ciò che le viene detto e non
calcola niente. Il guadagno non è di stile: il giorno in cui il ponte imparerà
a ripiegare, la pagina lo disegnerà senza che nessuno la modifichi -- e non
esiste nessun momento in cui la pagina possa disegnare un ripiego che il
backend non fa.

LE PAROLE STANNO QUI, non nel frontend, perché sono affermazioni sul
prodotto: vanno pinnate dove si pinnano le altre (stessa scelta di
`api/handlers_usage.py`, che tiene accanto al codice i suoi due messaggi).

«Attivo» NON compare in questo file e non deve comparirci. Significa
«interruttore acceso E credenziale presente» -- una proprietà della
configurazione -- e si legge «funziona», che è una proprietà della capacità.
Una chiave a credito esaurito è «Attivo». È la bugia strutturale che questa
fetta ritira.

Funzioni PURE: nessun accesso a `os.environ`, nessun `app`, nessun orologio.
Chi le chiama porta i fatti già misurati.
"""
from __future__ import annotations

# Un nome per provider, mai due. Prima di questa fetta l'abbonamento ne aveva
# tre -- «Abbonamento (Claude Max)» (models-route.js), «Abbonamento Claude
# (subscription)» (handlers_models.py), «Piano Claude Max» (translations) --
# uno per ogni file che aveva bisogno di nominarlo.
NOMI: dict[str, str] = {
    "subscription": "Piano Claude Max",
    "claude": "Claude API",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "ollama": "Ollama (in casa)",
}

# Quattro categorie, non un prezzo: HIRIS non ha una fonte di listini, e un
# prezzo vecchio è una bugia che sembra un servizio (progetto §12.1). Sono
# l'unica cosa che serve per decidere l'ordine di una catena.
NATURE: dict[str, str] = {
    "subscription": "nel piano",
    "claude": "a consumo",
    "openrouter": "a consumo",
    "openai": "a consumo",
    "ollama": "in casa",
}

# L'ordine di «Fuori dalla catena», dove un ordine non significa niente e
# quindi non può contraddire niente. È lo STESSO di `config.yaml` (l'ordine di
# ripiego di `balanced`, con il piano subito dopo Claude API): una terza lista
# con un terzo ordine sarebbe la stessa incoerenza che questa fetta chiude.
ORDINE_FISSO: tuple[str, ...] = (
    "claude", "subscription", "openrouter", "openai", "ollama",
)


def nome(provider_id: str) -> str:
    return NOMI.get(provider_id, provider_id)


def natura(provider_id: str) -> str:
    return NATURE.get(provider_id, "")


def componi_adesso(
    *,
    catena: list[str],
    credenziali: dict[str, bool],
    modelli: dict[str, str],
    ponte_attivo: bool,
) -> dict:
    """Chi risponde al prossimo messaggio, e perché.

    `catena` è l'ordine EFFETTIVO in cui il runtime prova i provider -- la
    stessa lista che `server.py` passa a `LLMRouter(model_chain=...)` e
    pubblica su `app["catena_modelli"]`, non una seconda derivazione.

    `ponte_attivo` è `app["ponte_attivo"]`. Quando è vero il turno NON entra
    in catena affatto: `api/handlers_chat.handle_chat` dirotta sulla coda
    PRIMA della riga che prende il router, e non c'è ritorno. È per questo che
    il ponte «scavalca» invece di «ripiegare», ed è per questo che la frase
    cambia soggetto invece di cambiare ordine.
    """
    ponte_ha_token = bool(credenziali.get("subscription"))
    diagnosi: list[dict] = []

    if ponte_attivo:
        chi = "subscription"
        via = "ponte"
    else:
        chi = catena[0] if catena else None
        via = "catena" if chi else ""

    if chi is None:
        frase = "HIRIS non può ancora rispondere: la catena è vuota."
        diagnosi.append({
            "gravita": "guasto",
            "testo": ("Non c'è nessun provider in catena: non c'è niente a cui "
                      "chiedere una risposta."),
            "azione": None,
        })
        return {"chi": None, "nome": "", "modello": "", "natura": "", "via": "",
                "frase": frase, "diagnosi": diagnosi}

    modello = modelli.get(chi, "")
    pezzi = ["Il prossimo messaggio va a " + nome(chi)]
    if modello:
        pezzi.append("con " + modello)
    pezzi.append(natura(chi))
    frase = ", ".join(pezzi) + "."

    if ponte_attivo:
        diagnosi.append({
            "gravita": "guasto" if not catena else "spreco",
            "testo": ("Il ponte è acceso: ogni messaggio passa dal Piano Claude "
                      "Max, e la catena qui sotto non viene consultata."),
            "azione": None,
        })
    elif ponte_ha_token:
        # La riga che costa di più: un abbonamento pagato e non usato costa
        # soldi ogni mese, un provider che fallisce costa un secondo di
        # latenza a messaggio. L'azione consigliata è una sola e sta qui
        # (progetto §9.3). `azione` resta None finché il piano non può
        # entrare in catena: il Task 14 la popola, e prometterla prima
        # sarebbe un bottone che non fa niente.
        diagnosi.append({
            "gravita": "spreco",
            "testo": "Il Piano Claude Max ha il token, lo paghi, ed è fuori dalla catena.",
            "azione": None,
        })

    return {"chi": chi, "nome": nome(chi), "modello": modello,
            "natura": natura(chi), "via": via, "frase": frase,
            "diagnosi": diagnosi}
