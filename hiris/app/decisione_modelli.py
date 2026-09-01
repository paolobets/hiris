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
calcola niente. Il guadagno non è di stile, ed è stato incassato: il giorno in
cui il ponte ha imparato a ripiegare (Task 14) la pagina lo ha disegnato senza
che nessuno la modificasse -- è cambiata una stringa qui dentro, e nessun test
del frontend. E non esiste nessun momento in cui la pagina possa disegnare un
ripiego che il backend non fa.

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

import os

# LA MISURA DELLA CREDENZIALE DEL PIANO, in un posto solo.
#
# «Il piano ha un token?» era scritta quattro volte, in quattro moduli, e
# governava quattro decisioni diverse: se il worker del ponte PARTE
# (`server.should_start_agent_worker`), se il piano ENTRA nella catena
# (`server._credentials`), cosa la pagina Modelli DICHIARA
# (`handlers_models._config_has_credential`), e se il turno si ACCODA
# (`instradamento._piano_puo_rispondere`).
#
# Oggi erano identiche. Il giorno in cui il token seguisse la strada che hanno
# gia' fatto `ponte.attivo`, `tetto_giornaliero` e `scadenza_min` -- da
# `config.yaml` all'archivio -- si aggiornerebbe il file della pagina, perche'
# e' il file della pagina. La pagina direbbe «Piano Claude Max, funziona, primo
# della catena»; il worker non partirebbe, e la chat ripiegherebbe su Claude
# API a consumo. L'utente pagherebbe a token credendo di essere sul forfait.
#
# E' esattamente il difetto per cui questo modulo esiste -- una pagina vera
# riga per riga e falsa nel complesso -- chiuso a valle (la COMPOSIZIONE della
# decisione) e mai a monte (la MISURA che la alimenta). Il commento a
# `handlers_models._config_has_credential` diceva che due definizioni della
# stessa credenziale «sarebbero la seconda rappresentazione in miniatura»:
# c'erano entrambe, e il commento descriveva il difetto al presente credendo
# di descriverne l'assenza.
SUBSCRIPTION_TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"


def subscription_has_token() -> bool:
    """Vero se la credenziale dell'abbonamento Claude c'e'.

    Solo la PRESENZA, mai il valore: chi chiama non deve poterlo stampare per
    sbaglio in un log o in una risposta.
    """
    return bool(os.environ.get(SUBSCRIPTION_TOKEN_VAR, "").strip())

# Un nome per provider, mai due. Prima di questa fetta l'abbonamento ne aveva
# tre -- «Abbonamento (Claude Max)» (models-route.js), «Abbonamento Claude
# (subscription)» (handlers_models.py), «Piano Claude Max» (translations) --
# uno per ogni file che aveva bisogno di nominarlo.
DISPLAY_NAMES: dict[str, str] = {
    "subscription": "Piano Claude Max",
    "claude": "Claude API",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "ollama": "Ollama (in casa)",
}

# Quattro categorie, non un prezzo: HIRIS non ha una fonte di listini, e un
# prezzo vecchio è una bugia che sembra un servizio (progetto §12.1). Sono
# l'unica cosa che serve per decidere l'ordine di una catena.
NATURES: dict[str, str] = {
    "subscription": "nel piano",
    "claude": "a consumo",
    "openrouter": "a consumo",
    "openai": "a consumo",
    "ollama": "in casa",
}

# Che cosa manca, quando manca. Sono TRE credenziali diverse e la parola le
# distingue: il piano ha un token OAuth, tre provider hanno una chiave, Ollama
# ha un indirizzo. Stanno qui e non nel frontend per la stessa ragione dei nomi
# (Task 5) e delle frasi di `compose_now`: sono affermazioni sul prodotto, e
# ognuna corrisponde a un ramo di `api/handlers_models._config_has_credential`.
# Scritte nella pagina sarebbero una seconda descrizione della regola di
# credenziale, in un altro linguaggio, libera di divergere dalla prima -- che è
# la forma esatta del difetto che questa fetta chiude.
MISSING_REASONS: dict[str, str] = {
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
CHAIN_END = "ultimo della catena: se non risponde, la chat dà errore"

# L'ordine di «Fuori dalla catena», dove un ordine non significa niente e
# quindi non può contraddire niente. È lo STESSO di `config.yaml` (l'ordine di
# ripiego di `balanced`, con il piano subito dopo Claude API): una terza lista
# con un terzo ordine sarebbe la stessa incoerenza che questa fetta chiude.
FIXED_ORDER: tuple[str, ...] = (
    "claude", "subscription", "openrouter", "openai", "ollama",
)

# ── I due gesti sul ponte, e perché sono un PERCORSO e non un tipo ──────────
# Dalla versione B (3.0.0) `ponte.attivo` vive nell'archivio di HIRIS e non fra
# le opzioni dell'add-on: e' la meta' della condizione che mancava al Task 14,
# che per questo aveva lasciato `azione` a `None` su tutte le diagnosi (una PUT
# su un valore letto dall'ambiente sarebbe tornata 200 e sarebbe stata buttata
# via al riavvio -- la lezione del Task 8, che quei bottoni li aveva gia'
# trovati e tolti dalla riga del piano).
#
# `dove` e' il PERCORSO nell'archivio, non un nome di comando, per la stessa
# ragione per cui `compose_panel` manda un percorso invece del nome di una
# chiave (Task 9): cosi' la pagina non sa che cosa sta accendendo. Applica un
# valore a una posizione e rilegge -- nessun `tipo` da riconoscere, nessun
# `if (id === 'subscription')`, nessuna parola del prodotto scritta in
# JavaScript. L'etichetta viaggia col gesto perche' e' un'affermazione sul
# prodotto, e le affermazioni sul prodotto stanno qui.
#
# Sono DUE e non uno: togliere `ponte.attivo` dalle opzioni dell'add-on toglie
# anche l'unico modo che c'era di SPEGNERE il ponte. Un interruttore che si
# accende e non si spegne e' peggio di nessun interruttore.
ACTION_PUT_SUBSCRIPTION_FIRST = {
    "etichetta": "Mettilo primo",
    "dove": ["ponte", "attivo"],
    "valore": True,
}
ACTION_REMOVE_SUBSCRIPTION = {
    "etichetta": "Togli il piano dalla catena",
    "dove": ["ponte", "attivo"],
    "valore": False,
}


def display_name(provider_id: str) -> str:
    return DISPLAY_NAMES.get(provider_id, provider_id)


def nature(provider_id: str) -> str:
    return NATURES.get(provider_id, "")


def missing_reason(provider_id: str) -> str:
    return MISSING_REASONS.get(provider_id, "manca la credenziale")


# ── La riga di stato: l'ultimo esito osservato, in parole ──────────────────
#
# Le parole degli esiti stanno qui, con le altre, per la ragione di sempre:
# sono affermazioni sul prodotto. I FATTI stanno in `esiti_provider.py`, che
# non sa dire niente e non deve: registra che cosa è successo, e questo modulo
# lo racconta.
#
# `adesso` è un PARAMETRO e non `time.time()`: è la sola forma in cui «3 min
# fa» si può provare, ed è la stessa disciplina del resto del file (funzioni
# pure, nessun orologio, nessun `os.environ`).


def _age(seconds: float) -> str:
    """Quanto tempo fa, in parole, senza dire più di quanto si sa.

    Si arrotonda SEMPRE PER DIFETTO: a 90 minuti si dice «1 h fa», perché «2 h
    fa» affermerebbe un tempo che non è passato. È la stessa regola di tutto il
    resto della pagina, applicata a un numero.

    Sotto il minuto non c'è una cifra da dare: «poco fa». Un «0 min fa» sarebbe
    una precisione finta, e un «adesso» ruberebbe la parola al riquadro in cima
    alla pagina, che parla del prossimo messaggio e non dell'ultimo.

    Un valore NEGATIVO è possibile: `adesso` e `quando` vengono da due letture
    diverse dello stesso orologio, e una sincronizzazione NTP fra l'una e
    l'altra può farle scavalcare. Cade nel primo ramo e diventa «poco fa», mai
    un futuro: questa pagina riferisce, non prevede. (Qui c'era un
    `max(0.0, ...)` che difendeva una cosa già difesa: la prova per mutazione
    l'ha tolto e non è caduto niente, perché `s < 60` prende anche i negativi.
    Una guardia che non guarda niente è una riga che insegna a fidarsi delle
    guardie.)
    """
    s = float(seconds)
    if s < 60:
        return "poco fa"
    if s < 3600:
        return f"{int(s // 60)} min fa"
    if s < 86400:
        return f"{int(s // 3600)} h fa"
    if s < 172800:
        return "ieri"
    return f"{int(s // 86400)} giorni fa"


def _count(from_count: int) -> str:
    """«L'ultima richiesta» oppure «le ultime N richieste».

    Il conteggio è la metà che conta: «ha rifiutato le ultime 40 richieste»
    dice una cosa che «ha rifiutato 3 minuti fa» non dice -- che non è un
    incidente, è lo stato. Nel caso del proprietario è la differenza fra «ah,
    un errore» e «ah, sto buttando via una chiamata a messaggio da settimane».
    """
    return "l'ultima richiesta" if int(from_count) <= 1 else (
        f"le ultime {int(from_count)} richieste")


# La causa in parole, per la famiglia `credenziale`. Quattro codici, due azioni
# diverse per chi legge: 400 e 402 dicono che i soldi sono finiti (Anthropic
# risponde 400 con «credit balance too low» -- il caso del proprietario --,
# OpenRouter 402), 401 e 403 dicono che la chiave non va bene. Chiamarle tutte
# «credito esaurito» sarebbe un'ipotesi sulla causa, che è la cosa che questo
# prodotto ha smesso di fare.
_CREDENTIAL_CAUSE: dict[int, str] = {
    400: "credito esaurito",
    402: "credito esaurito",
    401: "la chiave non è accettata",
    403: "la chiave non è accettata",
}


def occurrence_phrase(occurrence: dict | None, *, position: int | None, now: float) -> str:
    """L'ultimo esito osservato, detto a chi guarda la riga (progetto §4.3).

    `esito` è il dizionario di `esiti_provider.RegistroEsiti.esito`, oppure
    `None` quando non c'è mai stata un'osservazione. «Non l'ho interrogato» e
    «non ha risposto» sono due cose diverse e si leggono diverse.

    **«Mai provato» cambia significato con la posizione, e la copia lo segue.**
    In prima posizione è allarmante -- il provider che dovrebbe rispondere a
    ogni messaggio non ha mai risposto a nessuno; in seconda è la notizia buona
    -- il ripiego non è mai servito. Stesso fatto, due frasi, UNA regola sola,
    ed è il parametro `posizione`. Fuori dalla catena una posizione non c'è
    (`None`), e «non è mai servito ripiegare qui» direbbe che quella riga è un
    anello di riserva, che non è.

    Nessuna previsione e nessuna diagnosi: si dice che cosa è successo, con che
    codice, e quanto tempo fa. Perché sia successo non lo sa nessuno qui.
    """
    if occurrence is None:
        if position is None or int(position) <= 1:
            return "non l'hai ancora usato"
        return "non è mai servito ripiegare qui"

    age = _age(float(now) - float(occurrence["quando"]))
    if occurrence["tipo"] == "risposto":
        return "ha risposto " + age

    family = occurrence.get("famiglia") or "altro"
    code = occurrence.get("codice")
    fra_parentesi = f" ({code})" if isinstance(code, int) else ""

    if family == "modello":
        # Quante volte HIRIS abbia chiesto un modello che non esiste non
        # aggiunge niente: il fatto è che non esiste. Il conteggio serve dove
        # distingue l'incidente dallo stato, non dove lo stato è ovvio.
        return f"il modello non esiste più{fra_parentesi}, {age}"
    if family == "scaduto":
        # Il Piano Claude Max, e per ora solo lui: e' l'unico anello che non
        # risponde in linea -- il turno passa da una coda, e un worker altrove
        # lo serve (o non lo serve). «Ha rifiutato» sarebbe piu' largo del
        # fatto e manderebbe a cercare una credenziale che non c'entra: qui
        # non c'e' nessun codice, nessuna risposta e nessun rifiuto, c'e' un
        # silenzio con una data. Il CONTEGGIO c'e' perche' distingue
        # l'incidente dallo stato, che e' la ragione per cui esiste in questo
        # modulo: due scadenze di fila su un piano acceso vogliono dire che il
        # worker non gira, e la pagina lo fa vedere senza dirlo.
        return "non ha risposto in tempo — {}, {}".format(
            _count(occurrence["da_quante"]), age)
    if family == "irraggiungibile":
        # Nessun codice, perché non c'è stata nessuna risposta da cui prenderlo:
        # «non risponde all'indirizzo» è tutto ciò che si è potuto vedere.
        return "non risponde all'indirizzo — ultimo tentativo " + age
    if family == "credenziale":
        # Nessuna causa PREDEFINITA: se il codice non è fra quelli di cui
        # sappiamo il perché, si dice il numero e ci si ferma.
        #
        # Prima il ripiego era «la credenziale non è accettata», ed è una
        # frase che manda l'utente a rigenerare una chiave. Basta che
        # `esiti_provider._CREDENZIALE` guadagni un codice senza che questa
        # tabella lo guadagni — un 429 di quota, per esempio — e HIRIS
        # scriverebbe «la credenziale non è accettata (429)» su un rate limit,
        # mandando a sostituire una chiave che funziona.
        #
        # È esattamente ciò che il ramo `altro` qui sotto dichiara di non
        # voler fare: «inventare una causa qui sarebbe rifare l'errore da cui è
        # nata la regola». Valeva per un ramo e non per l'altro.
        cause = _CREDENTIAL_CAUSE.get(code if isinstance(code, int) else 0)
        if cause is None:
            return "ha rifiutato {}{}, {}".format(
                _count(occurrence["da_quante"]), fra_parentesi, age)
        return "ha rifiutato {} — {}{}, {}".format(
            _count(occurrence["da_quante"]), cause, fra_parentesi, age)
    # `altro`: il ramo di ciò che NON si è saputo classificare. Riporta il
    # numero e si ferma lì. Inventare una causa qui sarebbe rifare l'errore da
    # cui è nata la regola -- il giorno in cui HIRIS, davanti a un comando
    # riuscito, si inventò un guasto del dispositivo e mandò il proprietario a
    # cercarlo.
    if fra_parentesi:
        return f"ha rifiutato {_count(occurrence['da_quante'])} — errore {code}, {age}"
    return "ha rifiutato {}, {}".format(_count(occurrence["da_quante"]), age)


# ── La nota del ripiego: una riga che dice cosa e' successo, non perche' ──
#
# Decisione del proprietario, 13 agosto: **il ripiego si annuncia OGNI VOLTA**,
# e la ragione e' dei soldi -- un ripiego silenzioso dal forfait al consumo si
# scopre a fine mese. Sta qui e non in `api/handlers_chat.py` perche' e'
# un'affermazione sul prodotto, come tutte le altre di questo file: nella pagina
# della chat sarebbe una seconda voce che parla del prodotto, libera di
# divergere dalla prima.

# I tre fatti che il turno puo' aver osservato, e non uno di piu'. Sono le
# STESSE tre parole che `instradamento._piano_puo_rispondere` restituisce e
# che `_downgrade_to_chain` passa: la corrispondenza e' pinnata da un test,
# perche' un motivo che non fosse fra queste chiavi non produrrebbe un errore
# -- produrrebbe silenzio, che e' peggio.
_DOWNGRADE_REASONS: dict[str, str] = {
    "scadenza": "non ha risposto in tempo",
    "manca il token": "non ha un token con cui rispondere",
    "tetto giornaliero": "ha raggiunto il suo tetto di messaggi per oggi",
}


def downgrade_note(*, reason: str, who_answered: str) -> str:
    """La riga che dichiara un ripiego dal piano a forfait alla catena.

    E' un FATTO su cio' che HIRIS ha potuto vedere, mai un'ipotesi sulla causa:
    la stessa regola scritta in `azione/porta.py` per gli avvisi di `esegui`, e
    per lo stesso motivo -- la' una frase che affermava piu' del misurato
    («nessuno stato e' cambiato») produsse sulla casa vera una diagnosi
    inventata («probabile problema di comunicazione col dispositivo») che mando'
    il proprietario a cercare un guasto inesistente.

    Quindi: si dice CHE cosa il piano non ha fatto e CHI ha risposto al suo
    posto, con la sua natura. NON si dice perche' il piano non abbia risposto,
    non si dice se sia normale, non si consiglia niente, e non si allarma --
    non e' un avviso, e a schermo sta in tondo.

    **Due silenzi, e sono la stessa regola.** Un motivo che non e' fra i tre, o
    un provider di cui non si conosce la natura, non producono una frase
    approssimativa: producono `""`, e la nota non si scrive. La natura e' la
    meta' che riguarda i soldi -- e' la ragione per cui questa riga esiste -- e
    una riga falsa sui soldi e' peggio del silenzio. Il chiamante ha gia' la
    stessa regola per «chi ha risposto» (vedi `_who_answered_note`): qui
    si ridice perche' questa funzione puo' essere chiamata da chiunque, e una
    regola che vale solo se il chiamante se la ricorda non e' una regola.
    """
    what_happened = _DOWNGRADE_REASONS.get(reason)
    which_nature = nature(who_answered)
    if not what_happened or not which_nature:
        return ""
    return (f"Il Piano Claude Max {what_happened}: ha risposto "
            f"{display_name(who_answered)}, {which_nature}.")


def compose_now(
    *,
    chain: list[str],
    credentials: dict[str, bool],
    models: dict[str, str],
    bridge_active: bool,
    bridge_deadline_min: int = 5,
) -> dict:
    """Chi risponde al prossimo messaggio, e perché.

    `catena` è l'ordine EFFETTIVO in cui il runtime prova i provider -- la
    stessa lista che `server.py` passa a `LLMRouter(model_chain=...)` e
    pubblica su `app["catena_modelli"]`, non una seconda derivazione.

    `bridge_active` è `app["ponte_attivo"]` -- il parametro segue la
    conversione, la CHIAVE dell'app resta italiana. Quando è vero E c'è il
    token, il turno parte dal piano: `api/handlers_chat.handle_chat` lo accoda invece di
    prendere il router. Dal Task 14 quella strada ha un RITORNO -- se il piano
    non risponde entro la scadenza, la rotta di poll rifà il turno sulla catena
    -- quindi il piano è il primo anello e non più un bivio: la frase cambia
    soggetto perché è lui a provare per primo, non perché la catena non esista.

    `bridge_deadline_min` sono i minuti dopo i quali un turno accodato sul ponte
    passa al successivo della catena. Lo passa il chiamante perché questo
    modulo non legge `os.environ`: il numero è LO STESSO che
    `api/handlers_chat._enqueue_chat_job` usa per scrivere la scadenza (dal
    Task 10 dall'archivio, `ponte.scadenza_min`), non un secondo default che
    può divergere da quello vero.
    """
    bridge_has_token = bool(credentials.get("subscription"))
    diagnosis: list[dict] = []

    bridge_silent = bridge_active and not bridge_has_token
    if bridge_active and bridge_has_token:
        who = "subscription"
        route = "ponte"
    else:
        # Anche quando il ponte è acceso SENZA token. Fino al Task 14 questo
        # era il quarto stato -- «non può rispondere» -- perché il turno veniva
        # accodato in una coda che nessuno serviva (`should_start_agent_worker`
        # pretende il token) e scadeva. Adesso `handle_chat` non lo accoda
        # affatto: se il piano non può rispondere, il turno scende alla catena
        # nella stessa richiesta. Chi risponde è quindi il primo della catena,
        # come col ponte spento -- e ciò che resta da dichiarare non è più un
        # guasto, è un costo (vedi la diagnosi più sotto).
        who = chain[0] if chain else None
        route = "catena" if who else ""

    if who is None:
        if bridge_silent:
            phrase = ("HIRIS non può rispondere: il ponte è acceso, manca il "
                      "token del Piano Claude Max, e sotto di lui non c'è nessuno.")
            diagnosis.append({
                "gravita": "guasto",
                "testo": ("Il ponte è acceso ma manca il token: nessun "
                          "messaggio arriva al Piano Claude Max, e in catena "
                          "non c'è nessun altro a cui passarlo."),
                "azione": None,
            })
        else:
            phrase = "HIRIS non può ancora rispondere: la catena è vuota."
            diagnosis.append({
                "gravita": "guasto",
                "testo": ("Non c'è nessun provider in catena: non c'è niente a "
                          "cui chiedere una risposta."),
                "azione": None,
            })
        return {"chi": None, "nome": "", "modello": "", "natura": "", "via": "",
                "frase": phrase, "diagnosi": diagnosis}

    model = models.get(who, "")
    pezzi = ["Il prossimo messaggio va a " + display_name(who)]
    if model:
        pezzi.append("con " + model)
    pezzi.append(nature(who))
    phrase = ", ".join(pezzi) + "."

    if bridge_active and bridge_has_token:
        # Il piano risponde davvero, ed è il PRIMO ANELLO -- non più un bivio.
        # La gravità resta un fatto misurato sulla catena, non un'ipotesi, ma
        # i due fatti sono cambiati insieme al comportamento: con dei provider
        # sotto non c'è più nessuno spreco da dichiarare (prima «li hai
        # configurati e non li usa nessuno», adesso li usa quando il piano non
        # risponde: è la rete, e funziona), e ciò che resta da dire è quanto si
        # aspetta prima che la rete entri in funzione -- un costo, non un
        # guasto, quindi in tondo. Senza niente sotto è GUASTO, e la frase non
        # promette un successivo che non c'è: il Task 1 lasciò questa riga
        # senza test, le due prove gemelle stanno in
        # `tests/test_decisione_modelli.py`.
        if chain:
            diagnosis.append({
                "gravita": "fatto",
                "testo": ("Il ponte è acceso: il Piano Claude Max prova per "
                          f"primo, e se non risponde entro {int(bridge_deadline_min)} minuti "
                          "il turno "
                          "passa al successivo della catena."
                          ),
                # Il gesto INVERSO di «Mettilo primo», e l'unico che resta per
                # spegnere il ponte da quando `ponte.attivo` non e' piu'
                # un'opzione dell'add-on (versione B). Sta su una riga che non
                # denuncia niente -- il ponte acceso con dei provider sotto e'
                # uno stato sano -- perche' il gesto va dove sta il fatto che
                # si vuole cambiare, non dove c'e' un guasto.
                "azione": dict(ACTION_REMOVE_SUBSCRIPTION),
            })
        else:
            diagnosis.append({
                "gravita": "guasto",
                "testo": ("Il ponte è acceso e sotto il Piano Claude Max non "
                          "c'è nessun altro: "
                          f"se non risponde entro {int(bridge_deadline_min)} minuti, "
                          "il turno non ha dove andare."
                          ),
                "azione": None,
            })
    elif bridge_silent:
        # Il ponte acceso senza token non è più un turno perso (invariante 5,
        # chiuso al Task 3 come silenzio e chiuso qui come perdita): è un turno
        # che passa alla catena. Resta però un fatto che costa, e si dice --
        # per la stessa ragione per cui la chat lo annuncia a ogni risposta
        # (`downgrade_note`): un ripiego silenzioso dal forfait al consumo si
        # scopre a fine mese.
        diagnosis.append({
            "gravita": "spreco",
            "testo": ("Il ponte è acceso ma manca il token: nessun messaggio "
                      "arriva al Piano Claude Max, e ogni turno passa alla "
                      "catena — dal forfait al consumo."),
            "azione": None,
        })
    elif bridge_has_token:
        # La riga che costa di più: un abbonamento pagato e non usato costa
        # soldi ogni mese, un provider che fallisce costa un secondo di
        # latenza a messaggio. L'azione consigliata è una sola e sta qui
        # (progetto §9.3) -- ed è ADESSO un gesto, non più una riga che
        # descrive un guasto che si ripara altrove.
        #
        # Il Task 14 aveva lasciato `azione` a `None` e aveva ragione: metà
        # della condizione mancava. `ponte.attivo` veniva da `BRIDGE_ENABLED`,
        # cioè dall'ambiente, e una PUT su un valore letto dall'ambiente torna
        # 200 e viene buttata via al riavvio successivo -- il bottone che
        # sembra funzionare e non funziona, che questa fetta ha già evitato due
        # volte. Con la versione B (3.0.0) `ponte.attivo` vive nell'archivio,
        # la PUT lo scrive, `_recompute_chain` lo rimette in vigore a caldo
        # (compreso il lavoratore che risponde sul piano) e la rilettura mostra
        # il piano in testa. La metà che mancava è arrivata.
        diagnosis.append({
            "gravita": "spreco",
            "testo": "Il Piano Claude Max ha il token, lo paghi, ed è fuori dalla catena.",
            "azione": dict(ACTION_PUT_SUBSCRIPTION_FIRST),
        })

    return {"chi": who, "nome": display_name(who), "modello": model,
            "natura": nature(who), "via": route, "frase": phrase,
            "diagnosi": diagnosis}


def compose_topology(
    *,
    chain_order: list[str],
    credentials: dict[str, bool],
    models: dict[str, str],
    bridge_active: bool,
    occurrences: dict[str, dict],
    now: float,
    bridge_deadline_min: int = 5,
    ollama_timeout_s: int = 120,
) -> tuple[list[dict], list[dict]]:
    """La topologia effettiva: chi è in catena, in che ordine, e chi ne sta fuori.

    Il piano compare in catena SOLO quando il ponte è acceso, e in posizione 1.
    Dal Task 14 è un ANELLO e non più un bivio: se non risponde entro la
    scadenza, la rotta di poll rifà il turno sulla catena. Il disegno non è
    cambiato -- era già una riga in posizione 1 -- ma la frase che sta sotto sì
    (vedi `connettore`), ed è cambiata QUI, nel backend: la pagina disegna
    l'anello senza che nessuno la modifichi, che è la promessa che il progetto
    §11.1 aveva messo per iscritto.

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
    (`compose_now` -> `diagnosi[].azione`, oggi `None`), quando ci sarà
    qualcosa da fare: Task 13 (`ponte.attivo` letto dall'archivio) e Task 14
    (il ripiego).

    `connettore` è LA FRASE CHE STA SOTTO LA RIGA, e dice l'unica cosa che
    serve per scegliere un ordine: quanto costa passare oltre. Sta qui, e non
    nella pagina, ed è la riga che ha dimostrato perché: fino al Task 14 diceva
    «il ponte non ripiega, il messaggio va perso», perché era vero; il Task 14
    ha cambiato la stringa e la pagina dice la cosa nuova senza essere toccata
    (nessuno dei suoi test cambia). Scritta nel frontend sarebbe rimasta a
    dire la regola di ieri, e a schermo la frase ci sarebbe stata lo stesso.

    Regola del connettore (progetto §5.1): mostra un NUMERO solo quando quel
    numero è una decisione di qualcuno. Il tempo del ponte e il timeout di
    Ollama lo sono -- li scrive l'utente -- e i loro valori arrivano dal
    chiamante, che li legge dove li legge il runtime. Un rifiuto immediato non è
    un numero e si dice a parole; un tempo che nessuno ha scelto (i tre
    tentativi su un 429 di Claude, 5+15+45 secondi) non si inventa: lo
    racconterà la riga di stato dopo che è successo (Task 11).

    Il connettore di una riga dice cosa succede se QUELLA riga non risponde, e
    non presume niente su chi viene dopo: la pagina lo disegna fra una riga e
    la successiva, e dopo l'ultima disegna `CHAIN_END`. La divisione non è
    estetica -- è ciò che permette alla pagina di riordinare da sé fra un gesto
    e la risposta del server senza che una frase finisca a dire il falso.

    `note_connector` è il tetto utile che nessuno schema dichiara: la scadenza
    del ponte accetta 1..120 minuti, ma la chat smette di interrogare a
    `CHAT_POLL_MAX_MS` (5 minuti, `static/chat/send.js`), una costante
    indipendente e non collegata. Sopra i cinque il browser dichiara scaduta
    un'attesa che sul server è ancora viva. Questa fetta DICHIARA e non risolve
    (Task 6): è un fatto, non un divieto. Sta accanto al numero perché è del
    numero che parla, ed è composta con lo stesso valore -- due letture non
    potrebbero divergere.

    `esiti` è `esiti_provider.RegistroEsiti.tutti()`: che cosa è successo
    DAVVERO, per provider, misurato dal traffico vero. Non c'è nessuna voce per
    chi non è mai stato interrogato, e la differenza fra «non ha risposto» e
    «non l'ho interrogato» sopravvive fino allo schermo. `adesso` è
    l'orologio del chiamante, ed è un PARAMETRO perché questo modulo non ne
    legge nessuno: «3 min fa» è provabile solo se il tempo non avanza da solo.
    Entrambi sono OBBLIGATORI: con un valore di comodo, un chiamante che se ne
    dimenticasse produrrebbe una pagina che non dice mai niente sugli esiti --
    e nessun test se ne accorgerebbe, che è la forma di guasto peggiore che
    questa fetta conosca.

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
    dentro = [p for p in provider_in_catena(chain_order, credentials)
              if p != "subscription"]
    if bridge_active:
        dentro = ["subscription"] + dentro

    def without_model(pid: str) -> bool:
        """Ollama con l'indirizzo e senza un modello scelto.

        La credenziale di Ollama è il SOLO indirizzo (fetta «la catena è
        l'unica verità», Task 7): l'indirizzo è ciò che si custodisce, il
        modello è ciò che si decide. Ma per RISPONDERE servono tutti e due --
        `server.py` non costruisce il runner senza un modello -- e fra i due
        fatti si apriva un buco dichiarato dal Task 7: Ollama poteva stare in
        catena senza un backend dietro, cioè comparire come anello numerato in
        una pagina che descrive il runtime mentre `LLMRouter._ordered_backends`
        lo saltava in silenzio. Un anello a schermo che nessuno consulta è
        esattamente la bugia che questa fetta ritira.

        Si chiude senza rimettere il modello dentro la credenziale (sarebbero
        di nuovo due concetti in un posto solo): la riga resta credenziata, il
        pallino resta acceso, e a mancare è un GESTO -- non si entra in catena
        finché non c'è un modello. Le parole lo dicono, e `server.py` filtra la
        catena effettiva con lo stesso fatto.
        """
        return pid == "ollama" and not models.get(pid, "")

    def note(pid: str, in_chain: bool, has_credential: bool) -> str:
        """La parola che spiega perché quella riga non ha i gesti delle altre.

        Cambia con la regola, non con la pagina. Il Task 14 ha fatto del piano
        un anello e NON ha cambiato queste due stringhe: «in testa o fuori»
        resta la decisione del proprietario anche adesso che ripiega, e allora
        ci si entrava ancora accendendo il ponte in Configurazione add-on.

        VERSIONE B (3.0.0): il giorno previsto è arrivato, e le due stringhe
        cambiano perché il fatto è cambiato -- non perché la pagina sia stata
        ridisegnata. `ponte.attivo` non è più un'opzione dell'add-on: mandare
        ancora l'utente lì sarebbe mandarlo a cercare un campo che non esiste,
        cioè lo stesso difetto del messaggio di primo avvio che il Task 15 ha
        chiuso. Il gesto sta nel riquadro in cima, dove la diagnosi lo porta
        (`ACTION_PUT_SUBSCRIPTION_FIRST` / `ACTION_REMOVE_SUBSCRIPTION`), e la
        parola qui rimanda LÌ e non a una pagina esterna.
        """
        if has_credential and without_model(pid):
            return ("L'indirizzo c'è, il modello no: finché manca non c'è "
                    "niente a cui chiedere, e in catena non ci può stare. Si "
                    "sceglie qui accanto.")
        if pid != "subscription":
            return ""
        if in_chain:
            return ("In testa o fuori: ci sta perché il ponte è acceso, e si "
                    "toglie dal riquadro in cima.")
        if has_credential:
            return ("Entra in catena quando il ponte è acceso, e il ponte si "
                    "accende dal riquadro in cima.")
        return ""

    def connettore(pid: str) -> str:
        if pid == "subscription":
            # Il Task 14 ha cambiato QUESTA stringa, ed è il momento in cui il
            # progetto §11.1 si incassa: la pagina disegna un anello invece di
            # un vicolo cieco senza che nessuno tocchi il frontend. Diceva «il
            # ponte non ripiega: se non risponde entro N min il messaggio va
            # perso», e finché è stato vero è stato giusto dirlo.
            return f"se non risponde entro {int(bridge_deadline_min)} min"
        if pid == "ollama":
            return f"se non risponde entro {int(ollama_timeout_s)} s"
        return "se rifiuta, subito"

    def note_connector(pid: str) -> str:
        """Il tetto utile che nessuno schema dichiara, e che il ripiego ha reso
        più caro invece che meno.

        Il ripiego vive nella ROTTA DI POLL (`handlers_chat._ripiega_sulla_
        catena`): parte al primo poll che arriva dopo la scadenza. Ma
        `static/chat/send.js` smette di interrogare a `CHAT_POLL_MAX_MS`
        (5 minuti), quindi con una scadenza sopra i cinque non arriva NESSUN
        poll dopo di lei: il turno non passa al successivo, e lo sweep si
        limita a marcarlo scaduto. Prima di questo task la nota diceva «la
        risposta la trovi ricaricando» -- vero allora (il worker del ponte
        poteva ancora rispondere e `_submit_chat_reply` scriveva in
        cronologia), falso adesso per il ripiego, che non avviene affatto.
        Si dichiara, come il Task 6 ha dichiarato il tetto: è un fatto, non un
        divieto, ed è composta con lo STESSO numero del connettore -- due
        letture non potrebbero divergere."""
        if pid != "subscription" or int(bridge_deadline_min) <= 5:
            return ""
        return ("sopra i 5 minuti la chat smette di aspettare prima della "
                "scadenza, e il turno non passa al successivo")

    def state(pid: str, position: int | None, has_credential: bool) -> str:
        """La riga di stato: l'ultimo esito osservato, e quanto è vecchio.

        Tace SOLO quando non c'è credenziale E non c'è nessuna osservazione:
        lì la riga dice già `manca la chiave`, ed è la spiegazione completa di
        perché non è mai stato interrogato -- «non l'hai ancora usato» sotto
        «manca la chiave» sarebbe la stessa cosa detta due volte, la seconda
        con meno informazione.

        Un'osservazione vecchia invece si mostra SEMPRE, credenziale o no:
        quella riga è stata interrogata davvero, e togliere la chiave a un
        provider non cancella cosa aveva risposto.
        """
        misurato = occurrences.get(pid)
        if misurato is None and not has_credential:
            return ""
        return occurrence_phrase(misurato, position=position, now=now)

    def row(pid: str, position: int | None) -> dict:
        has_credential = bool(credentials.get(pid))
        in_chain = position is not None
        return {
            "id": pid,
            "nome": display_name(pid),
            "modello": models.get(pid, ""),
            # Alias o identificatore: la differenza di NATURA fra i due si
            # legge prima di essere spiegata, e la porta il carattere
            # (progetto §6.2). Sta nel payload e non nella pagina per la stessa
            # ragione di tutto il resto: è un fatto sul prodotto -- il piano
            # sceglie un alias che SEGUE il modello corrente, gli altri un nome
            # che punta a una cosa fissa -- e un `if (id === 'subscription')`
            # nel frontend sarebbe la regola scritta una seconda volta.
            "modello_alias": is_alias(pid),
            "natura": nature(pid),
            "manca": "" if has_credential else missing_reason(pid),
            "nota": note(pid, in_chain, has_credential),
            "connettore": connettore(pid) if in_chain else "",
            "connettore_nota": note_connector(pid) if in_chain else "",
            "ha_credenziale": has_credential,
            # Il fatto grezzo e la frase che lo racconta, accanto. Il fatto
            # viaggia perché la pagina possa DISEGNARE diverso ciò che ha
            # rifiutato (il pallino grigio-ambra, il nome che perde peso) senza
            # dedurlo dal testo -- leggere una regola dentro una frase è come
            # ricostruirla, e questa fetta esiste per non farlo più. `None`
            # quando non c'è mai stata un'osservazione: «non ha risposto» e
            # «non l'ho interrogato» restano due cose diverse fino allo schermo.
            "esito": occurrences.get(pid),
            "stato_testo": state(pid, position, has_credential),
            "posizione": position,
            # `riordinabile` governa TUTTI E QUATTRO i gesti che scrivono
            # `chain_order` (frecce, ✕, «Usa»): dice «la presenza e la
            # posizione di questa riga si decidono da chain_order». Per il
            # piano è falso perché ci si entra dal ponte; per Ollama senza
            # modello perché entrarci produrrebbe un anello che il router salta
            # -- in tutti e due i casi la PUT sarebbe accettata e buttata via.
            # Un impedimento alla volta, e il più esterno per primo: senza
            # l'indirizzo la riga dice già «manca l'indirizzo» e non offre
            # niente (la pagina non disegna «Usa» dove non c'è credenziale),
            # quindi il modello mancante si dichiara solo quando è davvero
            # LUI l'unica cosa che manca.
            "riordinabile": (pid != "subscription"
                             and not (has_credential and without_model(pid))),
        }

    chain = [row(pid, i + 1) for i, pid in enumerate(dentro)]
    fuori = [row(pid, None) for pid in FIXED_ORDER if pid not in dentro]
    return chain, fuori


# ── Il pannello del modello (progetto §6) ──────────────────────────────────
#
# Le parole del pannello stanno QUI per la stessa ragione delle altre: sono
# affermazioni sul prodotto. `provenance` sarebbe già falsa domani se fosse
# scritta nella pagina: dipende da un fatto misurato ADESSO, se la lettura
# dell'elenco è riuscita o no. E `quando` è la prova che il posto era giusto:
# era la confessione dell'invariante 4, ha smesso di essere vera il giorno
# della scrittura a caldo (Task 10) ed è uscita da qui, senza che nessuno
# toccasse il frontend. Scritta nella pagina sarebbe rimasta a dire la regola
# di ieri, e a schermo la frase ci sarebbe stata lo stesso: nessun test se ne
# sarebbe accorto.

# I TRE ALIAS DEL PIANO, e non uno di più. Non è una semplificazione
# dell'interfaccia: `agent/runner.modello_cli` riduce QUALUNQUE modello risolto
# a `opus`/`haiku`/`sonnet` per sottostringa, perché la CLI dell'abbonamento
# non conosce altri nomi. Offrire `claude-opus-4-7` sul piano sarebbe una
# precisione finta: sul ponte `claude-opus-4-7` e `claude-opus-4-1` producono
# lo stesso identico comportamento (misurato, progetto §0.4).
SUBSCRIPTION_ALIAS: tuple[tuple[str, str], ...] = (
    ("haiku", "il più rapido"),
    ("sonnet", "l'equilibrato"),
    ("opus", "il più capace"),
)

# Gli ospiti che si interrogano davvero. Servono a `provenance` per nominare
# CHI non ha risposto: «non ho potuto leggere» senza il nome di chi non ha
# risposto è meno di quanto il sistema sa.
_OSPITI: dict[str, str] = {
    # Claude API è entrata qui con la fetta «il modello del piano». Prima aveva
    # un ramo tutto suo in `provenance`, con una frase che dichiarava
    # inesistente la rotta di elenco di Anthropic: falso, `GET /v1/models`
    # esiste. Cancellato il ramo, il percorso generico produce già le due frasi
    # giuste -- serviva solo il nome dell'ospite. Un caso particolare in meno,
    # non uno in più.
    "claude": "api.anthropic.com",
    "openai": "api.openai.com",
    "openrouter": "openrouter.ai",
}

# DOVE si scrive la scelta, come percorso dentro l'oggetto che la pagina già
# salva. È un dato e non una regola scritta nel frontend: senza, la pagina
# avrebbe bisogno di un `if (id === 'ollama')` per sapere che il modello di
# Ollama non vive in `provider_models` -- cioè di conoscere il caso
# particolare, che è la forma esatta del difetto che questa fetta chiude.
# Qui il piano aveva la tupla VUOTA -- «niente da salvare» -- con la ragione
# scritta accanto: il suo modello era un effetto di quello di Claude API
# (progetto §0.4), non un secondo valore, e un pannello che offrisse di
# scriverlo avrebbe mandato una PUT che nessuno legge.
#
# Era vera, ed era IL DIFETTO. Un campo solo serviva due economie opposte: su
# Claude API si paga a token e `haiku` è la scelta frugale, sul piano il
# modello non costa di più e `opus` è la ragione per cui il piano esiste.
# L'impianto del proprietario girava sul piano con `haiku`. Dalla fetta «il
# modello del piano» il piano ha un campo suo, `ponte.modello`, e questa riga
# è tutto ciò che serve al frontend per accendere i tre radio: `dove` non
# vuoto → `scrivibile` vero. Nessuna riga di JavaScript ha dovuto imparare
# niente -- è ciò per cui `dove` è un percorso e non un nome.
_WHERE_WRITTEN: dict[str, tuple[str, ...]] = {
    "claude": ("provider_models", "claude"),
    "openai": ("provider_models", "openai"),
    "openrouter": ("provider_models", "openrouter"),
    "ollama": ("ollama", "modello"),
    "subscription": ("ponte", "modello"),
}

# La voce «auto», che nell'archivio è la STRINGA VUOTA e non la parola "auto".
# Salvare letteralmente "auto" è un difetto: `claude_runner.resolve_model`
# tratta il default come valore, quindi `resolve_model("auto", "chat", "auto")`
# restituisce "auto" e la richiesta parte con `model="auto"` verso un provider
# che quel nome non lo conosce. Fino a questa fetta `_CLAUDE_MODELS` apriva con
# "auto" e il picker uscito col Task 8 lo offriva come qualunque altro.
AUTO_NOTE = "scelto da HIRIS: oggi {}"


def is_alias(provider_id: str) -> bool:
    """Il valore mostrato per questo provider è un ALIAS o un IDENTIFICATORE?

    Un identificatore punta a una cosa fissa; un alias SEGUE il modello
    corrente del piano -- lo decide Anthropic, e si muove sotto di te quando
    aggiornano. Sono cose di natura diversa e la pagina lo dice col carattere,
    non con una didascalia (progetto §6.2).
    """
    return provider_id == "subscription"


def provenance(provider_id: str, source: str, *, address: str = "",
               free_models_notice: bool = False) -> str:
    """Da dove viene l'elenco che il pannello sta mostrando.

    È il quinto punto del progetto §6.3, quello che il codice ha imposto: le
    tre `_fetch_*` hanno cinque secondi di pazienza e, se falliscono,
    restituiscono una lista scritta a mano nel sorgente con un `logger.warning`
    e niente altro. Senza questa riga si può stare davanti a un elenco che
    sembra vero, che viene da una costante di due anni fa, per un provider che
    non risponderebbe comunque -- e nessuna parte dello schermo lo dice.
    """
    if source == "assente":
        # Non è un errore: è «non c'è niente da leggere, e il perché è la
        # credenziale». Un pannello che si apre deve SEMPRE dare una risposta:
        # nascondere è comodo per chi capisce e crudele per chi non capisce
        # perché una cosa è sparita. La parola è la stessa della riga
        # (`MISSING_REASONS`), perché è lo stesso fatto detto nello stesso vocabolario.
        return f"Non c'è nessun elenco da leggere: {missing_reason(provider_id)}."
    if source == "fissa":
        # Il piano. Non è un ripiego e non si chiama così: i tre alias non
        # possono invecchiare, perché non descrivono il catalogo di qualcun
        # altro -- sono l'insieme esatto che `modello_cli` sa produrre.
        return ("Sono tutti quelli che esistono: il ponte parla con la CLI del "
                "piano, che di nomi ne conosce tre.")
    # Qui viveva un ramo `if provider_id == "claude"` con una frase propria,
    # che diceva all'utente che Anthropic non pubblicherebbe nessun elenco e
    # che quella lista era tutto ciò che HIRIS conosce. È FALSO:
    # `GET /v1/models` esiste (verificato sulla documentazione ufficiale il
    # 15/08/2026). Il ramo è uscito con la fetta «il modello del piano», e
    # Claude API cade nel percorso generico come gli altri due provider che si
    # interrogano davvero.
    #
    # La frase esatta è vietata da `tests/test_elenco_anthropic.py` in TUTTO il
    # sorgente, commenti compresi: un grep assoluto è una trappola più forte di
    # uno che deve distinguere una citazione da un'affermazione -- per questo
    # qui è parafrasata.
    ospite = _OSPITI.get(provider_id) or address or display_name(provider_id)
    if source == "viva":
        if provider_id == "ollama":
            return f"Scaricati su {ospite} — letti adesso."
        return f"Letti da {ospite} adesso."
    cause = ("spento? indirizzo sbagliato?" if provider_id == "ollama"
             else "chiave rifiutata? rete?")
    row = (f"Elenco di riserva: non ho potuto leggere {ospite} ({cause}). Quello che vedi "
           "qui potrebbe non esistere più.")
    if free_models_notice:
        # Il difetto gemello, DICHIARATO invece che nascosto: quando la lettura
        # fallisce il ripiego restituisce i preset non filtrati, quindi i
        # gratuiti ricompaiono anche con la casella spuntata. Non si corregge
        # qui -- filtrarli renderebbe la riserva una lista diversa da quella
        # scritta nel sorgente, cioè una terza cosa -- si rende leggibile.
        row += (" E la casella «nascondi i gratuiti» qui non ha effetto: "
                "l'elenco di riserva li contiene comunque.")
    return row


def explanation(provider_id: str) -> str:
    """La riga che serve solo a chi si chiede perché il pannello è così povero.

    Per il piano è la forma stessa del pannello a spiegare (progetto §10.1);
    per OpenRouter è la ragione per cui l'elenco non è il catalogo.
    """
    if provider_id == "subscription":
        # Qui c'era una frase che mandava l'utente a scegliere sulla riga di
        # Claude API, perché quale dei tre alias fosse in uso discendeva da lì:
        # vera fino alla 3.1.0, e falsa dal momento esatto in cui il piano ha
        # avuto un campo suo. Mandare là adesso vorrebbe dire mandare a
        # cambiare il valore sbagliato.
        return ("Sono alias, non nomi di modello: seguono il modello corrente "
                "del piano invece di puntare a una versione fissa. Qui la "
                "scelta non cambia quanto spendi — è compresa nel piano.")
    if provider_id == "openrouter":
        return ("Solo modelli che sanno usare gli strumenti: HIRIS manda "
                "sempre il catalogo delle azioni, e gli altri rifiuterebbero "
                "ogni richiesta. Qui ci sono quelli scelti da noi: per uno che "
                "non c'è, incollane l'identificatore nel campo qui sopra.")
    if provider_id == "ollama":
        return ("Sono i modelli scaricati su quella macchina: per averne un "
                "altro si fa `ollama pull` di là, non da qui.")
    return ""


def compose_panel(
    *,
    provider_id: str,
    values: list[str],
    source: str,
    chosen: str,
    auto_resolved: str = "",
    address: str = "",
    hide_free_models: bool = False,
) -> dict:
    """Il pannello del modello, già composto: la pagina lo disegna e basta.

    `valori` sono gli identificatori grezzi che la lettura ha restituito;
    `fonte` è "viva" (letta adesso dal provider), "riserva" (elenco scritto nel
    sorgente) o "fissa" (il piano: un elenco che non si legge da nessuna parte
    perché non c'è niente da leggere). `scelto` è il valore in vigore adesso --
    per il piano è l'alias che il ponte userebbe, che nessuno ha scritto lì:
    discende dal modello di Claude API.

    Nessuna delle parole qui dentro è calcolabile dalla pagina, e nessuna delle
    strutture -- `dove`, `casella` -- è una regola travestita: sono percorsi
    dentro l'oggetto che la pagina già salva, così la pagina non ha bisogno di
    sapere che il modello di Ollama non vive in `provider_models`.
    """
    if source == "assente":
        # Nessuna voce, mai: un elenco dichiarato inesistente e disegnato lo
        # stesso sarebbe la pagina che si contraddice in due righe.
        entries: list[dict] = []
    elif is_alias(provider_id):
        entries = [{"valore": v, "nota": n} for v, n in SUBSCRIPTION_ALIAS]
    else:
        entries = []
        if auto_resolved:
            entries.append({"valore": "", "nota": AUTO_NOTE.format(auto_resolved)})
        for v in values:
            entries.append({"valore": v,
                            "nota": "gratuito" if v.endswith(":free") else ""})
    return {
        "id": provider_id,
        "nome": display_name(provider_id),
        "alias": is_alias(provider_id),
        # L'insieme è CHIUSO? Non è la stessa domanda di `alias`, benché oggi
        # le due risposte coincidano: `alias` dice di che NATURA è il valore (e
        # decide il carattere della riga), `elenco_completo` dice se c'è altro
        # da cercare fuori dall'elenco -- cioè se il pannello deve offrire un
        # campo dove incollare un identificatore. Il piano ne ha tre e non
        # esiste un quarto; ogni altro provider ha un catalogo di cui l'elenco
        # è un pezzo.
        #
        # Serve perché accendendo `dove` per il piano si accenderebbe anche il
        # campo di testo libero (nel pannello filtro e campo sono la stessa
        # cosa): si potrebbe incollare `gpt-4o`, salvarlo, e vederselo ridurre
        # a `sonnet` da `_clean_bridge` con un log che nessuno legge. Un
        # controllo abilitato che non fa quello che dice -- la cosa che i tre
        # radio spenti dichiaravano di voler evitare, rientrata dalla porta
        # opposta.
        #
        # Due campi e non uno perché il giorno in cui un provider avesse un
        # insieme chiuso di identificatori veri le due risposte divergono.
        "elenco_completo": is_alias(provider_id),
        "fonte": source,
        "provenienza": provenance(
            provider_id, source, address=address,
            # L'avviso si lega a CIO' CHE C'E' NELL'ELENCO, non a una
            # condizione che lo indovina. Fino al 22/08/2026 bastavano
            # «openrouter + riserva + casella spuntata» per affermare che
            # l'elenco conteneva gratuiti comunque -- vero finche' la riserva
            # ne conteneva cinque. Da quando la riserva e' stata potata dei
            # nomi morti (che erano tutti `:free`) quella condizione avrebbe
            # continuato ad affermarlo su un elenco che non ne ha piu' nemmeno
            # uno: una riga che dice il falso su cio' che si sta guardando.
            free_models_notice=(provider_id == "openrouter"
                                and source == "riserva" and bool(hide_free_models)
                                and any(str(v).endswith(":free") for v in values))),
        "spiegazione": explanation(provider_id),
        # Da quando ha effetto la scelta: NIENTE, perché ha effetto dal
        # prossimo messaggio, e questo vale per OGNI provider e per ogni campo
        # di questa pagina. Qui viveva `quando()`, la confessione
        # dell'invariante 4: lo stesso valore -- il modello di Claude API --
        # aveva effetto immediato sul ponte e solo al riavvio sull'API, e la
        # pagina ne dichiarava uno solo. Il Task 10 ha tolto il problema invece
        # della frase: i runner LEGGONO il modello al momento dell'uso.
        # Il campo resta perché il canale resta -- la pagina disegna la riga
        # solo se il backend gliela manda, e non ne inventa una quando il
        # backend tace -- ma oggi il backend tace su tutti e cinque:
        # l'assenza di didascalia È l'affermazione.
        "quando": "",
        "dove": list(_WHERE_WRITTEN.get(provider_id, ())),
        "scelto": chosen,
        # La casella vive SULLA LISTA CHE FILTRA e non in una pagina di
        # impostazioni: si auto-documenta, e non serve una descrizione per
        # capire cosa fa una casella che sta sotto l'elenco che modifica
        # (progetto §6.3). Viaggia come percorso, non come nome noto alla
        # pagina, per la stessa ragione di `dove`.
        "casella": ({"etichetta": "nascondi i gratuiti",
                     "dove": ["nascondi_gratuiti"]}
                    if provider_id == "openrouter" else None),
        "modelli": entries,
    }
