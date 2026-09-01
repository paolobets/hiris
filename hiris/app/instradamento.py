"""Chi risponde a questo turno: il ponte, o la catena.

**Una domanda sola, una casa sola.** Fino al 22 agosto 2026 la regola viveva
dentro `api/handlers_chat.handle_chat`, intrecciata con la persistenza del
turno e con la coda -- e il turno di una promessa, che quella funzione non la
attraversa mai, ne aveva per forza una seconda: andava dritto a `llm_router`,
dove il ponte non e' nemmeno un anello (`_VALID_BACKEND_NAMES` conosce claude,
openai, openrouter, ollama).

Non era una svista di chi ha scritto lo Schedulatore: era la struttura a
imporlo. Il difetto si e' visto dal vivo il 21/08/2026 su una casa che gira
INTERAMENTE sul Piano Claude Max -- chat perfetta, promesse tutte fallite su
due chiavi API esaurite, e l'abbonamento sano li' accanto che le promesse non
potevano usare, senza che nessuna pagina lo dicesse.

Da qui in poi le due porte chiedono alla stessa funzione, e una terza porta
che nascesse domani non potrebbe inventarsene una terza senza accorgersene.

## Le due ragioni per cui si scende alla catena non sono la stessa cosa

- **Il ponte non e' in gioco** -- spento, o coda non cablata. Non c'e' nessun
  ripiego da dichiarare: e' la configurazione che l'utente ha scelto.
  Annunciarlo a ogni turno direbbe che sta perdendo qualcosa che non ha mai
  avuto. Motivo vuoto.
- **Il ponte c'e' e non puo' rispondere** -- niente token, o tetto pieno.
  Quello e' un ripiego vero, dal forfait al consumo, e **si annuncia ogni
  volta** (decisione del proprietario, 13 agosto): un passaggio silenzioso a
  un provider a pagamento si scopre a fine mese.

Il motivo e' una **chiave** di `decisione_modelli._DOWNGRADE_REASONS`, mai una
frase: la frase la compone `downgrade_note`, e un motivo fuori vocabolario non
produce un errore -- produce silenzio, cioe' esattamente il prelievo non
annunciato che la regola esiste per evitare.

`_bridge_on` e `_piano_puo_rispondere` vivono QUI e non piu' in
`handlers_chat`: sono pezzi della stessa decisione, e lasciarle di la' avrebbe
reso circolare l'import (la chat chiama questo modulo, questo modulo chiamava
la chat).
"""
from __future__ import annotations

import logging

from .api.handlers_models import _STORE_DEFAULTS
from .decisione_modelli import subscription_has_token

logger = logging.getLogger(__name__)


def _bridge_on(app) -> bool:
    """Se il ponte della coda di ragionamento e' cablato in questa app.

    `server._on_startup` crea `app["reasoning_queue"]` sempre; `ponte.attivo`
    (nell'archivio) governa la spazzata e `app["ponte_attivo"]`, non
    l'esistenza dell'oggetto coda. Quindi la presenza della chiave e' il
    segnale giusto -- ed e' anche il modo in cui i test entrano e escono dal
    ramo senza toccare variabili d'ambiente.
    """
    return app.get("reasoning_queue") is not None


def _subscription_can_answer(app) -> tuple[bool, str]:
    """Il piano puo' servire un turno adesso? E, se no, con quali parole.

    Le due condizioni sono quelle che fino alla 2.4.1 facevano finire il turno
    con un errore: il token assente (senza cui il lavoratore del ponte non
    parte affatto, e il messaggio finirebbe in una coda che nessuno serve) e il
    tetto giornaliero pieno.

    Il tetto si legge dall'ARCHIVIO (`ponte.tetto_giornaliero`), dove l'utente
    lo cambia: quella che si cambia dev'essere quella che il turno subisce.
    """
    if not subscription_has_token():
        return False, "manca il token"
    ceiling = int(
        (app.get("models_config") or {})
        .get("ponte", {})
        .get("tetto_giornaliero",
             _STORE_DEFAULTS["ponte"]["tetto_giornaliero"]))
    if app["reasoning_queue"].count_exchanges_today() >= ceiling:
        logger.warning(
            "Tetto giornaliero del ponte raggiunto (%d turni): il turno passa "
            "alla catena.", ceiling)
        return False, "tetto giornaliero"
    return True, ""


def who_answers(app) -> tuple[str, str]:
    """`("ponte", "")` oppure `("catena", motivo)`.

    Il motivo e' vuoto quando non c'e' nessun ripiego da dichiarare, ed e' una
    chiave di `_DOWNGRADE_REASONS` quando ce n'e' uno. Vedi il docstring del
    modulo per la distinzione, che non e' una sfumatura: e' la differenza fra
    una configurazione e un prelievo.
    """
    if not (app.get("ponte_attivo") and _bridge_on(app)):
        return "catena", ""
    can, reason = _subscription_can_answer(app)
    if not can:
        return "catena", reason
    return "ponte", ""
