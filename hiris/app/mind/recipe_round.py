"""Il giro delle **ricette**: chiede al modello, per un dispositivo alla
volta, come si misura, e raccoglie la risposta del ponte.

Spostato da `server.py` senza una riga di logica cambiata (Chiusura dello
sprint, F8 passo 2, 14/10/2026): la regola del proprietario del 06/10/2026
vuole che `server.py` registri e avvii, non che ospiti i giri.
"""
from __future__ import annotations

import logging
import time

from aiohttp import web

from ..home_space.energy import energy_dashboard
from ..home_space.house import House
from ..home_space.house_history import statistic_ids_for_round
from ..home_space.reader import HOME_SPACE_KEY
from ..proxy.entity_cache import ENTITY_CACHE_KEY
from ..proxy.ha_client import HA_CLIENT_KEY
from ..reasoning.queue import REASONING_QUEUE_KEY, turn_answer
from ..steering import RECIPES_SPECIES, enqueue_turn, start, too_soon_to_ask_again, turn_in_flight
from ..usage.store import USAGE_KEY
from . import recipe_turn
from .knowledge import KNOWLEDGE_KEY
from .store import OBSERVATIONS_KEY

#: Le chiavi di `app` che questo modulo possiede: `web.AppKey`, mai una
#: stringa (X-32, Chiusura dello sprint).
RECIPE_CURSOR_KEY = web.AppKey("recipe_turn_cursor")

logger = logging.getLogger(__name__)


async def recipe_round(app) -> dict | None:
    """L'anello delle ricette: **«c'e' un dispositivo che pesa e non ho ancora
    capito come si misura? e allora chiedilo»** (spec §7).

    Torna il resoconto del giro, o `None` se non c'era da farlo.

    **Perche' esiste, col numero.** Il registro delle operazioni e il motore
    delle ricette sono arrivati con la fetta 4, ma nessuno scriveva ricette
    nuove: il repo ne portava una, quella del bilancio (uscita il
    01/10/2026, le ricette gia' seminate restano). Misurato sulla casa vera
    il 13/09/2026, il resoconto giornaliero avrebbe avuto **~6 misure al
    giorno** -- tutte dello stesso inverter -- contro ~28 fatti di cronaca, e
    tutti e tre gli inneschi dell'analista lavorano sulle misure.

    **Uno per volta, e non e' prudenza generica.** Trenta dispositivi che
    pesano sono trenta turni del modello: chiesti insieme, svuoterebbero da
    soli il tetto giornaliero del piano (`count_exchanges_today` contro
    `ponte.tetto_giornaliero`) e da li' in poi ogni turno -- chat compresa --
    passerebbe ai provider a pagamento. Uno per giro, ogni dieci minuti, copre trenta
    dispositivi in cinque ore e non si vede nella bolletta. E' anche la
    ragione per cui `devices_to_ask` guarda **tutti e due** i campi: un
    dispositivo che il modello non ha saputo leggere non si richiede mai piu'.

    **Dalla stessa porta dello scope**: chi risponde lo decide
    `steering.who_answers`, la stessa funzione che lo decide per la chat, per
    le promesse e per l'osservatore. Una quarta porta che nascesse domani non
    potrebbe inventarsene una quarta senza accorgersene.

    Non solleva mai: gira per sempre, e un avvio a meta' non deve fermare lo
    schedulatore.
    """
    store = app.get(OBSERVATIONS_KEY)
    sapere = app.get(KNOWLEDGE_KEY)
    home_space_store = app.get(HOME_SPACE_KEY)
    if store is None or sapere is None or home_space_store is None:
        return None
    try:
        house = House.read(home_space_store, app.get(ENTITY_CACHE_KEY))
        collected = _collect_recipe_turn(app, sapere, house)
        if collected is not None and collected.get("risposta"):
            return collected
        # **Una risposta che non c'e' non chiude il giro**, e senza questa riga
        # la promessa scritta in `apply_recipe` -- «non consuma il colpo, il
        # giro successivo richiede» -- era falsa: il turno vecchio veniva
        # ri-raccolto ogni dieci minuti, sempre vuoto, e non se ne accodava mai
        # uno nuovo. Trovato dal vivo il 13/09/2026 alle 21:05, dieci minuti
        # dopo aver rilasciato la correzione che quella promessa la scriveva.
        if collected is not None and too_soon_to_ask_again(
                app, recipe_turn.RECIPE_TURN_KIND):
            return collected
        if turn_in_flight(app, recipe_turn.RECIPE_TURN_KIND):
            return None

        watched = {s for s, riga in (store.scope() or {}).items()
                   if riga.get("dentro")}
        to_ask = recipe_turn.devices_to_ask(sapere, house, watched)
        # **Niente da riparare ne' da chiedere: niente da leggere** (A-20,
        # Tappa 2, Task 8). Fino al 04/10/2026 l'elenco delle statistiche si
        # leggeva qui sotto a ogni passaggio, prima di sapere se servisse.
        if not to_ask and not recipe_turn.has_named_recipes(sapere, house):
            return None

        # **Quali entita' sanno produrre una serie**: serve due volte, e si
        # legge una sola (spec §6, primo «rifiuta se»), condivisa con gli
        # ingredienti del resoconto (`statistic_ids_for_round`). `None` se non
        # si e' potuto leggere, e allora non si dice niente al modello e non si
        # ripara niente.
        with_series = None
        cliente = app.get(HA_CLIENT_KEY)
        if cliente is not None:
            reading = await statistic_ids_for_round(app, cliente)
            if isinstance(reading, dict):  # la busta del guasto (D3)
                logger.info("ricette: elenco delle statistiche non letto (%s): %s",
                            reading.get("causa"), reading.get("errore"))
            else:
                with_series = reading

        # **La dashboard Energia** (piano degli attori, Task 2.2-2.3, D6, D8):
        # letta una volta per giro dell'anagrafe, e solo quando c'e' qualcosa
        # da chiedere o da riparare. Serve due volte: citata a parte nella
        # domanda, e per sapere se una ricetta e' stata scritta contro ruoli
        # che la dashboard non dichiara piu' (o non dichiarava ancora).
        dashboard = (await energy_dashboard(cliente, home_space_store, house,
                                            with_series=with_series)
                     if cliente is not None else None)

        # **La ricetta rotta si ripara QUI, nel suo giro** (attori, Task 1.6;
        # D2 del proprietario, 03/10/2026). Decide il codice, dalla causa
        # (`recipe_turn.recipes_to_repair`): un dispositivo che pesa e la cui
        # ricetta nomina un'entita' sparita, ricreata o senza statistiche, o
        # e' stata scritta contro un'altra dashboard Energia (Task 2.3), torna
        # fra quelli da chiedere, con la domanda che dice perche'. Fino al
        # 05/10/2026 la riparava solo l'attuatore, in pausa dal 01/10: nessuno.
        to_repair = {device_id: broken for device_id, broken
                     in recipe_turn.recipes_to_repair(
                         sapere, house, with_series=with_series,
                         energy=dashboard).items()
                     if set(house.entities_of(device_id)) & watched}
        if to_repair:
            logger.info("ricette: %d ricette da riparare -- %s", len(to_repair),
                        ", ".join(sorted(to_repair)))
            # Nell'ordine dell'anagrafe, su cui ruota `who_to_ask`.
            asked = set(to_ask) | set(to_repair)
            to_ask = [d for d in house.device_ids() if d in asked]
        if not to_ask:
            return None
        # A chi chiedere: **si ruota**, o un dispositivo che non risponde
        # affama tutti gli altri (vedi `recipe_turn.who_to_ask`).
        device_id, app[RECIPE_CURSOR_KEY] = recipe_turn.who_to_ask(
            to_ask, int(app.get(RECIPE_CURSOR_KEY) or 0))
        if device_id is None:
            return None
        repair = to_repair.get(device_id)
        objective = store.objective()["testo"]

        route, downgrade, runner = start(app, RECIPES_SPECIES)
        if route == "ponte":
            return _enqueue_recipe_turn(app, house, device_id,
                                        objective=objective,
                                        with_series=with_series, energy=dashboard,
                                        repair=repair)
        if runner is None:
            logger.info("ricette: nessun modello a cui chiedere (%s)", downgrade)
            return None
        logger.info("ricette: chiedo come si misura «%s» (%s)%s", device_id, route,
                    " -- riparazione" if repair else "")
        esito = await recipe_turn.ask(
            runner, sapere, house, device_id, objective=objective,
            who=f"modello ({route})", when_ts=time.time(),
            with_series=with_series, energy=dashboard, repair=repair,
            measurements=app.get(USAGE_KEY))
        logger.info("ricette: giro finito -- %s", esito)
        return esito
    except Exception as exc:
        logger.warning("ricette: giro fallito (%s: %s)", type(exc).__name__, exc)
        return None


def _enqueue_recipe_turn(app, house: House, device_id: str, *,
                         objective: str,
                         with_series: set[str] | None = None,
                         energy: dict | None = None,
                         repair: recipe_turn.Repair | None = None) -> dict | None:
    """Accoda al piano la domanda su un dispositivo, e torna subito."""
    job = recipe_turn.bridge_turn(objective, house, device_id,
                                  with_series=with_series, energy=energy,
                                  repair=repair)
    if job is None:
        return None
    _job_id, deadline_min = enqueue_turn(
        app, RECIPES_SPECIES,
        # **Nella sveglia va il dispositivo**: il ponte risponde minuti dopo,
        # da un altro processo, e chi raccoglie deve sapere di CHI era la
        # domanda. `submit` azzera il contesto e non la sveglia. E, per una
        # riparazione, le entita' che la risposta non puo' nominare (`None`:
        # non e' una riparazione; `[]`: lo e', per la dashboard), e la
        # dashboard contro cui la domanda e' scritta: chi raccoglie le applica
        # come la catena (`apply_recipe`, `repairing` e `written_against`).
        {"dispositivo": device_id,
         "riparare": None if repair is None else sorted(repair.silent),
         "scritta_contro": recipe_turn.written_against(house, device_id, energy)},
        job)
    logger.info("ricette: turno accodato al piano per «%s» (scadenza %d min)",
                device_id, deadline_min)
    return {"accodata": True, "dispositivo": device_id}


def _collect_recipe_turn(app, sapere, house: House) -> dict | None:
    """La risposta che il piano ha dato alla domanda su un dispositivo.

    **Un turno gia' letto non si rilegge**, e qui la traccia e' il sapere
    stesso: se il dispositivo ha gia' una ricetta o un rifiuto scritto dopo
    che il turno e' stato deciso, quella risposta e' gia' stata applicata.
    """
    queue = app.get(REASONING_QUEUE_KEY)
    if queue is None:
        return None
    turn = queue.latest_if_decided(recipe_turn.RECIPE_TURN_KIND)
    if turn is None:
        return None
    device_id = (turn.get("wake") or {}).get("dispositivo")
    if not device_id:
        return None
    decided_ts = turn.get("decided_ts") or turn.get("created_ts") or 0
    # **Tutti e tre i campi**: dalla 3.46.0 una risposta puo' finire anche in
    # `ricetta_non_serve` (il rifiuto ragionato), e guardarne due su tre
    # avrebbe fatto riapplicare lo stesso turno del ponte una seconda volta.
    for campo in (recipe_turn.RECIPE_FIELD, recipe_turn.UNDERSTOOD_FIELD,
                  recipe_turn.DECLINED_FIELD):
        riga = sapere.get("dispositivo", device_id, campo)
        if riga is not None and riga.when_ts >= decided_ts:
            return None
    reply = turn_answer(turn)
    wake = turn.get("wake") or {}
    # Una sveglia di prima del 06/10/2026 porta `[]` anche fuori da una
    # riparazione: letta come riparazione, tiene la ricetta vecchia davanti a
    # una risposta storta, e un dispositivo chiesto la prima volta non ne ha.
    repairing = (None if wake.get("riparare") is None
                 else frozenset(wake["riparare"]))
    esito = recipe_turn.apply_recipe(sapere, house, device_id, reply,
                                     who="modello (ponte)", when_ts=time.time(),
                                     repairing=repairing,
                                     written_against=wake.get("scritta_contro"))
    if not esito.get("risposta"):
        # Il ponte ha restituito una decisione vuota: non e' una risposta, e
        # non si scrive niente. Il giro successivo richiede.
        return esito
    logger.info("ricette: risposta del piano applicata per «%s» -- %s",
                device_id, esito)
    return esito
