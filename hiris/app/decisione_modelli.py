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

# Che cosa manca, quando manca. Sono TRE credenziali diverse e la parola le
# distingue: il piano ha un token OAuth, tre provider hanno una chiave, Ollama
# ha un indirizzo. Stanno qui e non nel frontend per la stessa ragione dei nomi
# (Task 5) e delle frasi di `componi_adesso`: sono affermazioni sul prodotto, e
# ognuna corrisponde a un ramo di `api/handlers_models._config_has_credential`.
# Scritte nella pagina sarebbero una seconda descrizione della regola di
# credenziale, in un altro linguaggio, libera di divergere dalla prima -- che è
# la forma esatta del difetto che questa fetta chiude.
MANCANZE: dict[str, str] = {
    "subscription": "manca il token",
    "claude": "manca la chiave",
    "openrouter": "manca la chiave",
    "openai": "manca la chiave",
    "ollama": "manca l'indirizzo",
}

# Cosa c'è dopo l'ultimo anello. È una frase sulla CATENA e non su una riga --
# quale sia l'ultima riga cambia con un gesto, e la pagina riordina da sé fra
# un gesto e la risposta del server: attaccata a una riga, dopo un riordino si
# ritroverebbe in mezzo, a dire «ultimo della catena» di uno che non lo è più.
# Resta vera anche dopo il Task 14: l'ultimo che non risponde è la fine della
# strada, col ponte o senza.
FINE_CATENA = "ultimo della catena: se non risponde, la chat dà errore"

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


def manca(provider_id: str) -> str:
    return MANCANZE.get(provider_id, "manca la credenziale")


def componi_adesso(
    *,
    catena: list[str],
    credenziali: dict[str, bool],
    modelli: dict[str, str],
    ponte_attivo: bool,
    scadenza_ponte_min: int = 5,
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

    `scadenza_ponte_min` è `BRIDGE_DEADLINE_MIN`, i minuti dopo i quali un
    turno accodato sul ponte muore senza risposta. Lo passa il chiamante
    perché questo modulo non legge `os.environ`: il numero è LO STESSO che
    `api/handlers_chat._enqueue_chat_job` usa per scrivere la scadenza, non
    un secondo default che può divergere da quello vero.
    """
    ponte_ha_token = bool(credenziali.get("subscription"))
    diagnosi: list[dict] = []

    ponte_muto = ponte_attivo and not ponte_ha_token
    if ponte_attivo and not ponte_muto:
        chi = "subscription"
        via = "ponte"
    elif ponte_muto:
        # Il quarto stato: «non può rispondere». Non è ipotetico -- è
        # raggiungibile oggi e non lascia traccia. `server._ponte_attivo` è
        # `BRIDGE_ENABLED or _sub_first_class`, ma il worker che risponde
        # parte solo da `should_start_agent_worker()`, che pretende il token:
        # il turno viene accodato e nessuno lo reclama.
        chi = None
        via = ""
    else:
        chi = catena[0] if catena else None
        via = "catena" if chi else ""

    if chi is None:
        if ponte_muto:
            frase = ("HIRIS non può rispondere: il ponte è acceso e manca il "
                     "token del Piano Claude Max.")
            diagnosi.append({
                "gravita": "guasto",
                "testo": ("Il ponte è acceso ma manca il token: ogni messaggio "
                          "viene accodato e scade dopo {} minuti senza "
                          "risposta.".format(int(scadenza_ponte_min))),
                "azione": None,
            })
        else:
            frase = "HIRIS non può ancora rispondere: la catena è vuota."
            diagnosi.append({
                "gravita": "guasto",
                "testo": ("Non c'è nessun provider in catena: non c'è niente a "
                          "cui chiedere una risposta."),
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
        # Qui il ponte ha il token (il caso senza è uscito sopra, con
        # `chi = None`): il piano risponde davvero. La gravità dice quanto
        # costa lo scavalco, ed è un fatto misurato sulla catena, non
        # un'ipotesi: con dei provider sotto è SPRECO (li hai configurati e
        # non li usa nessuno), senza niente sotto è GUASTO (il ponte è
        # l'unica cosa che c'è: il giorno che non risponde, non risponde
        # nessuno). Il Task 1 lasciò questa riga senza test; le due prove
        # gemelle stanno in `tests/test_decisione_modelli.py`.
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


def componi_topologia(
    *,
    chain_order: list[str],
    credenziali: dict[str, bool],
    modelli: dict[str, str],
    ponte_attivo: bool,
    scadenza_ponte_min: int = 5,
    timeout_ollama_s: int = 120,
) -> tuple[list[dict], list[dict]]:
    """La topologia effettiva: chi è in catena, in che ordine, e chi ne sta fuori.

    Il piano compare in catena SOLO quando il ponte è acceso, e in posizione 1:
    oggi il ponte non è un anello, è un bivio a monte del router
    (`api/handlers_chat.handle_chat` dirotta prima di prendere il router e non
    ha ritorno). Disegnarlo come un anello sarebbe promettere un ripiego che il
    prodotto non fa -- esattamente il difetto che questa fetta chiude. Quando il
    ripiego esisterà (Task 14), cambierà QUESTA funzione, e la pagina disegnerà
    un anello senza che nessuno la modifichi.

    `riordinabile` è False per il piano, sempre, anche dopo il Task 14. Il piano
    sta IN TESTA O FUORI (decisione del proprietario, 13 agosto): metterlo
    secondo richiederebbe che `handle_chat` accodi a metà turno e risponda 202
    invece di 200 a seconda di dove la catena si rompe -- una fetta sua. Il
    campo viaggia nel payload perché la pagina non debba SAPERLO: disegna le
    frecce che le vengono dette, e non può offrirne di più.

    `riordinabile` governa TUTTI E DUE i gesti che scrivono `chain_order` --
    le frecce e «Usa» -- perché dice una cosa sola: *la presenza e la posizione
    di questa riga in catena si decidono da `chain_order`*. Per il piano è
    falso in entrambi i sensi, e non per simmetria estetica: `save_models_config`
    scarta `subscription` da `chain_order` (`_VALID_BACKENDS` sono quattro
    nomi), quindi un «Usa» sulla riga del piano scriverebbe una PUT che il
    server accetta con 200 e butta via -- un bottone che non fa niente, cioè il
    difetto che questa fetta esiste per chiudere, ricomparso nell'interfaccia.
    Il piano entrerà in catena da un'AZIONE dichiarata dal backend
    (`componi_adesso` -> `diagnosi[].azione`, oggi `None`), quando ci sarà
    qualcosa da fare: Task 13 (`ponte.attivo` letto dall'archivio) e Task 14
    (il ripiego).

    `connettore` è LA FRASE CHE STA SOTTO LA RIGA, e dice l'unica cosa che
    serve per scegliere un ordine: quanto costa passare oltre. Sta qui, e non
    nella pagina, perché è la SOLA affermazione della pagina Modelli che oggi
    sarebbe falsa se fosse scritta bene per domani. Oggi il ponte non ripiega:
    è un bivio a monte del router, e alla scadenza il messaggio va perso.
    Disegnare fra il piano e la riga sotto un «se non risponde, si passa al
    successivo» sarebbe promettere un ripiego che il prodotto non fa -- il
    difetto 3, ricomparso come didascalia. Il giorno del ripiego (Task 14)
    cambia questa stringa e la pagina dice la cosa nuova senza essere toccata:
    è la promessa che il piano del Task 14 fa per iscritto («la prova che il
    frontend non è stato toccato è che nessuno dei suoi test cambia»).

    Regola del connettore (progetto §5.1): mostra un NUMERO solo quando quel
    numero è una decisione di qualcuno. Il tempo del ponte e il timeout di
    Ollama lo sono -- li scrive l'utente -- e i loro valori arrivano dal
    chiamante, che li legge dove li legge il runtime. Un rifiuto immediato non è
    un numero e si dice a parole; un tempo che nessuno ha scelto (i tre
    tentativi su un 429 di Claude, 5+15+45 secondi) non si inventa: lo
    racconterà la riga di stato dopo che è successo (Task 11).

    Il connettore di una riga dice cosa succede se QUELLA riga non risponde, e
    non presume niente su chi viene dopo: la pagina lo disegna fra una riga e
    la successiva, e dopo l'ultima disegna `FINE_CATENA`. La divisione non è
    estetica -- è ciò che permette alla pagina di riordinare da sé fra un gesto
    e la risposta del server senza che una frase finisca a dire il falso.

    `connettore_nota` è il tetto utile che nessuno schema dichiara: la scadenza
    del ponte accetta 1..120 minuti, ma la chat smette di interrogare a
    `CHAT_POLL_MAX_MS` (5 minuti, `static/chat/send.js`), una costante
    indipendente e non collegata. Sopra i cinque il browser dichiara scaduta
    un'attesa che sul server è ancora viva. Questa fetta DICHIARA e non risolve
    (Task 6): è un fatto, non un divieto. Sta accanto al numero perché è del
    numero che parla, ed è composta con lo stesso valore -- due letture non
    potrebbero divergere.

    `manca` e `nota` sono due frasi, non due calcoli, e stanno qui per la
    stessa ragione delle altre parole di questo modulo. `manca` dice QUALE
    credenziale manca (tre credenziali diverse, tre parole diverse, una per
    ogni ramo di `_config_has_credential`); `nota` dice PERCHÉ una riga non
    offre i gesti che offrono le altre -- l'assenza di un gesto, senza una
    parola, si legge come un guasto. Entrambe sono `""` quando non c'è niente
    da dire, e la pagina disegna solo ciò che non è vuoto: nessuna condizione
    sul provider vive nel frontend.
    """
    from .model_activation import provider_in_catena

    # Il piano NON è un membro di `chain_order`, né qui né dopo il Task 14: la
    # sua presenza in testa discende da `ponte.attivo`, che è un'altra chiave
    # dell'archivio. Sul disco lo garantisce già `_VALID_BACKENDS` (quattro
    # nomi, il piano non c'è); qui si ridice, perché questa funzione riceve una
    # lista e non il disco, e una lista può arrivare da chiunque -- il gateway
    # MCP fa PUT su questa rotta.
    dentro = [p for p in provider_in_catena(chain_order, credenziali)
              if p != "subscription"]
    if ponte_attivo:
        dentro = ["subscription"] + dentro

    def nota(pid: str, in_catena: bool, ha_credenziale: bool) -> str:
        """La parola che spiega perché quella riga non ha i gesti delle altre.

        Cambia con la regola, non con la pagina: il giorno in cui il ponte si
        accende da qui (Task 13) e il piano diventa un anello (Task 14), qui
        cambiano queste due stringhe -- e la pagina dice la cosa nuova senza
        che nessuno la tocchi.
        """
        if pid != "subscription":
            return ""
        if in_catena:
            return ("In testa o fuori: ci sta perché il ponte è acceso, e il "
                    "ponte si spegne in Configurazione add-on.")
        if ha_credenziale:
            return ("Entra in catena quando il ponte è acceso, e il ponte si "
                    "accende in Configurazione add-on.")
        return ""

    def connettore(pid: str) -> str:
        if pid == "subscription":
            # Oggi il ponte NON ripiega. Finché è così, la frase dice quello che
            # succede davvero -- il messaggio va perso -- invece di promettere
            # la riga sotto.
            return ("il ponte non ripiega: se non risponde entro {} min il "
                    "messaggio va perso".format(int(scadenza_ponte_min)))
        if pid == "ollama":
            return "se non risponde entro {} s".format(int(timeout_ollama_s))
        return "se rifiuta, subito"

    def connettore_nota(pid: str) -> str:
        if pid != "subscription" or int(scadenza_ponte_min) <= 5:
            return ""
        return ("sopra i 5 minuti la chat smette di aspettare prima: la "
                "risposta la trovi ricaricando")

    def riga(pid: str, posizione: int | None) -> dict:
        ha_credenziale = bool(credenziali.get(pid))
        in_catena = posizione is not None
        return {
            "id": pid,
            "nome": nome(pid),
            "modello": modelli.get(pid, ""),
            "natura": natura(pid),
            "manca": "" if ha_credenziale else manca(pid),
            "nota": nota(pid, in_catena, ha_credenziale),
            "connettore": connettore(pid) if in_catena else "",
            "connettore_nota": connettore_nota(pid) if in_catena else "",
            "ha_credenziale": ha_credenziale,
            "posizione": posizione,
            "riordinabile": pid != "subscription",
        }

    catena = [riga(pid, i + 1) for i, pid in enumerate(dentro)]
    fuori = [riga(pid, None) for pid in ORDINE_FISSO if pid not in dentro]
    return catena, fuori
