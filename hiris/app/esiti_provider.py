"""Cosa è successo davvero, per provider: l'ultimo esito osservato.

La pagina Modelli sapeva dire «Claude è primo in catena» e non sapeva dire «e
sta rifiutando da quaranta richieste». È il caso del proprietario per intero:
la sua chiave Claude è a credito zero -- l'API risponde `400 credit balance too
low` -- e per giorni la pagina l'ha mostrata come funzionante mentre
OpenRouter, che paga a consumo, serviva ogni turno al posto suo. Non mancava un
dato di configurazione: mancava **cosa è successo**.

Prima di questo modulo HIRIS buttava via quell'informazione. `LLMRouter.chat`
logga «Backend … failed, trying next» e va avanti; i runner collassano ogni
errore in `RunnerBackendError("Errore temporaneo del servizio AI. Riprova tra
poco.")`, perdendo il codice e la causa. Il log del Supervisor le aveva
entrambe, per chi sapesse dove guardare; la pagina che l'utente apre per
decidere dove spendere, no.

**Un fatto su ciò che si è potuto vedere, mai un'ipotesi sulla causa.** Qui si
registra CHE COSA è successo -- questo provider ha rifiutato, con questo
codice, a quest'ora -- e non PERCHÉ. La regola è nata quando HIRIS, davanti a
un comando riuscito, inventò un guasto del dispositivo e mandò il proprietario
a cercarlo.

**Chi legge deve poter distinguere «non ha risposto» da «non l'ho
interrogato».** Sono due cose diverse e si scrivono in due modi diversi:
`esito(provider)` restituisce `None` finché non c'è stata NESSUNA osservazione,
e un dizionario appena ce n'è una. Non esiste un terzo valore, e soprattutto non
esiste un valore di comodo che faccia sembrare osservato ciò che non lo è.

**Nessuna persistenza, e nessuna scadenza.** Il registro vive in memoria e
muore col processo: «da quando l'add-on è partito» è un'età dichiarabile
(progetto §11.2). E un esito di due ore fa RESTA lì, vecchio, perché la pagina
ne dica l'età invece di regalare una freschezza che la produzione non ha -- il
difetto più grave della settimana è sopravvissuto a 1207 test proprio perché
una cache finta si aggiornava da sola.

**L'orologio è iniettato.** `RegistroEsiti(orologio=...)` prende una funzione,
e nei test è una lista mutabile che avanza solo quando il test lo dice: con un
`time.time()` cotto dentro, «3 min fa» non sarebbe provabile.

Le parole che l'utente legge NON stanno qui: stanno in
`decisione_modelli.frase_esito`, dove stanno tutte le altre affermazioni sul
prodotto. Qui ci sono solo i fatti misurati.
"""
from __future__ import annotations

import time

# Le famiglie d'errore, e non una di più. Sono tre cause distinte più il ramo
# di scorta, e la ragione per cui sono separate è che chiedono tre azioni
# diverse a chi legge: ricaricare il credito / rifare la chiave (credenziale),
# scegliere un altro modello (modello), accendere la macchina o correggere
# l'indirizzo (irraggiungibile). Collassarle in «errore temporaneo del servizio
# AI» è ciò che il codice faceva fino a questa fetta, ed è la ragione per cui
# il proprietario non ha mai saputo del credito esaurito.
# `scaduto` e' la quinta, ed e' nata col ripiego (Task 14). Non e' un rifiuto:
# il Piano Claude Max non risponde con un codice, non solleva un'eccezione e
# non chiude una connessione -- semplicemente il turno accodato non viene
# servito entro la scadenza. Chiamarlo «ha rifiutato» (il ramo di scorta)
# sarebbe una parola piu' larga del fatto, cioe' il difetto che questa fetta
# esiste per chiudere: il piano non ha rifiutato, non ha risposto. Chiede a chi
# legge un'azione ancora diversa dalle altre tre -- guardare se il worker del
# ponte sta girando -- ed e' per questo che e' separata.
FAMILIES = ("credenziale", "modello", "irraggiungibile", "scaduto", "altro")

# La sola tabella di questo modulo, e sta qui e non in `frase_esito` perché è
# una MISURA (che cosa ha risposto il server), non una parola. 402 è il codice
# canonico del credito; Anthropic risponde 400 con «credit balance too low»,
# che è il caso del proprietario; 401 e 403 sono la chiave rifiutata. Tutti e
# quattro sono «la credenziale non ti fa passare», e la frase li distingue.
_CREDENTIAL = (400, 401, 402, 403)


def family_from_code(code: int | None) -> str:
    """La famiglia di uno stato HTTP.

    Tutto ciò che non è credenziale o modello è `"altro"`, compreso il 429 e
    il 500: sono guasti veri, ma non dicono a chi legge che cosa fare, e
    fingere che lo dicano sarebbe l'ipotesi sulla causa che questo prodotto non
    fa. `None` (nessun codice) è `"altro"` per la stessa ragione.
    """
    if code in _CREDENTIAL:
        return "credenziale"
    if code == 404:
        return "modello"
    return "altro"


def error_family(exc: Exception) -> str:
    """La famiglia di un'eccezione sollevata da un runner.

    La connessione VINCE sul codice: `openai.APIConnectionError` porta
    `status_code` a `None`, ma un endpoint che non risponde è un fatto
    diverso da un endpoint che risponde male, e sarebbe letto dall'utente in
    modo diverso (Ollama spento contro credito finito).

    `_is_conn_error` è quella di `openai_compat_runner`, RIUSATA e non
    riscritta: è la stessa condizione che fa scattare il circuito, e due
    definizioni di «irraggiungibile» in due file sarebbero due
    rappresentazioni della stessa regola -- la forma esatta del difetto che
    questa fetta chiude. L'import è dentro la funzione perché
    `openai_compat_runner` importa `claude_runner`, che importa questo modulo:
    a livello di modulo sarebbe un ciclo.
    """
    from .backends.openai_compat_runner import _is_conn_error

    if _is_conn_error(exc):
        return "irraggiungibile"
    code = getattr(exc, "status_code", None)
    return family_from_code(code if isinstance(code, int) else None)


class OccurrenceRegistry:
    """L'ultimo esito osservato, per provider, e da quante richieste dura.

    Un dizionario in memoria, alimentato dal ciclo di ripiego del router --
    cioè dal TRAFFICO VERO, non da una sonda. Nessuna sonda automatica
    all'apertura della pagina (progetto §11.2): sondare cinque provider a ogni
    apertura costa denaro e quota per un'informazione che scade subito, e
    trasformerebbe questa pagina in una cosa che conviene non aprire.

    `da_quante` conta le richieste consecutive con lo STESSO esito, dove
    «stesso» include la famiglia e il codice: la frase che ne nasce è «ha
    rifiutato le ultime N richieste — <causa dell'ultima>», e se N contasse
    anche rifiuti di un'altra famiglia attribuirebbe quella causa a richieste
    che l'hanno avuta diversa.
    """

    def __init__(self, clock=time.time) -> None:
        # Una funzione, non un modulo: nei test è una lista mutabile che avanza
        # quando il test lo dice. Un orologio che avanza da solo renderebbe
        # invisibile proprio la cosa che questo registro esiste per dire --
        # quanto è vecchia l'ultima osservazione.
        self._clock = clock
        self._per_provider: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Scrittura: la fa il router, a ogni turno, per l'anello che ha provato
    # ------------------------------------------------------------------

    def successo(self, provider: str) -> None:
        precedente = self._per_provider.get(provider)
        continua = bool(precedente) and precedente["tipo"] == "risposto"
        self._per_provider[provider] = {
            "tipo": "risposto",
            # Un successo non ha una causa e non ha un codice: i campi restano
            # vuoti invece di portare quelli del rifiuto di prima, che
            # racconterebbero un guasto già finito.
            "famiglia": "",
            "codice": None,
            "messaggio": "",
            "quando": float(self._clock()),
            "da_quante": (precedente["da_quante"] + 1) if continua else 1,
            "durata_s": 0.0,
        }

    def fallimento(self, provider: str, *, family: str, code: int | None,
                   message: str, durata_s: float) -> None:
        precedente = self._per_provider.get(provider)
        continua = (bool(precedente)
                    and precedente["tipo"] == "rifiutato"
                    and precedente["famiglia"] == family
                    and precedente["codice"] == code)
        self._per_provider[provider] = {
            "tipo": "rifiutato",
            "famiglia": family,
            "codice": code,
            "messaggio": message,
            "quando": float(self._clock()),
            "da_quante": (precedente["da_quante"] + 1) if continua else 1,
            "durata_s": float(durata_s),
        }

    # ------------------------------------------------------------------
    # Lettura: la fa l'handler della pagina, una volta per richiesta
    # ------------------------------------------------------------------

    def occurrence(self, provider: str) -> dict | None:
        """L'ultimo esito, o `None` se non c'è mai stata un'osservazione.

        `None` non è «non lo so»: è «non l'ho interrogato», che è un fatto e la
        pagina lo dice con parole sue. Restituisce una COPIA -- un lettore che
        modificasse il dizionario ricevuto riscriverebbe la storia osservata
        dell'add-on da dentro un handler HTTP.
        """
        entry = self._per_provider.get(provider)
        return dict(entry) if entry is not None else None

    def occurrences(self) -> dict[str, dict]:
        """Le voci di CHI È STATO OSSERVATO, e nessun'altra.

        Un provider mai interrogato non compare: mettercelo con un esito vuoto
        sarebbe affermare un'osservazione che non c'è stata.
        """
        return {name: dict(entry) for name, entry in self._per_provider.items()}
