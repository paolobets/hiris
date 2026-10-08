"""La riconciliazione: gli archivi del cervello seguono la casa (Tappa 8, Task 1;
D1 del proprietario, 08/10/2026, la consigliata).

**Il problema.** Lo scope teneva decisioni su entita' che Home Assistant non
conosce piu', e il sapere le risposte (ricetta, «non capita», «non serve») di
dispositivi tolti dal registro. Nessuna delle due si cancellava mai: una riga
senza referente non e' storia, e' un doppione che mente (fondamenta 2). La
storia di quel soggetto vive gia' nel grezzo e nei resoconti.

**Cosa esce, e cosa no.**

- dello **scope**, le righe (dentro e fuori) delle ENTITA' per cui
  `House.source` risponde `None`: ne' il registro ne' gli stati le conoscono.
  Gli altri stati della fonte -- spenta dal proprietario o da Home Assistant,
  integrazione ferma, non disponibile, senza valore, sparita dagli stati ma
  ancora nel registro -- **restano**: sono cose che possono tornare. I
  soggetti che non sono entita' (`log:`, `problema:`, `integrazione:`,
  `automazione:`) non hanno un referente da cercare in `House.source` e
  restano;
- del **sapere**, le risposte per dispositivo (`recipe_turn.ANSWER_FIELDS`)
  dei dispositivi che il registro non ha piu'. Un dispositivo con tutte le
  entita' spente e' ancora nel registro, e le sue righe restano.

Se l'id torna, l'osservatore lo richiede da solo (`ObservationsStore.
undecided`), e le ricette lo richiedono (`recipe_turn.who_to_ask`).

**Le guardie**: senza ognuna di queste una casa letta a meta' si leggerebbe
come una casa svuotata, e la riconciliazione cancellerebbe tutto.

1. l'anagrafe e' stata letta (`HomeSpace.updated_at()` non `None`: vive in
   memoria, e all'avvio e' vuota);
2. i registri `entita` e `dispositivi` non sono fra quelli caduti
   (`House.unavailable`, che porta anche le copie di prima, S-36);
3. lo specchio dello stato e' leggibile (`Mirror.readable`): senza, un'entita'
   senza `unique_id` -- mai nel registro -- risponderebbe `None`;
4. Home Assistant si dichiara avviato (`get_config` risponde `RUNNING`,
   `home_space/topology.ha_running`). Letto nel sorgente di Home Assistant al
   tag 2026.9.4 l'08/10/2026: le integrazioni si impostano in
   `bootstrap._async_set_up_integrations` (stadi con tetto, 120 e 300
   secondi, piu' 300 per la chiusura), POI `core.HomeAssistant.async_start`
   porta lo stato a `starting`, aspetta i compiti dell'avvio e passa a
   `running` subito prima di `homeassistant_started`. Lo stato di un'entita'
   senza `unique_id` nasce quando la sua piattaforma la aggiunge
   (`helpers/entity_platform.py`, `_async_add_entity`, ramo «unique_id is
   None», poi `Entity.add_to_platform_finish` -> `async_write_ha_state` in
   `helpers/entity.py`), e non ha un segnaposto ripristinato come quelle del
   registro: di norma nasce prima di `running`; ma un'integrazione che sfora il tetto di uno
   stadio prosegue in sottofondo ("Setup timed out for stage ... moving
   forward"), e una voce in `setup_retry` riprova piu' tardi: per quelle lo
   stato puo' nascere dopo. La guardia chiude la finestra d'avvio, non quei
   due casi, che restano: la riga esce, e torna con l'osservatore.
   `async_start` manda anche `core_config_updated` appena e' `running`
   (stesse righe), cioe' una ricostruzione dell'anagrafe -- e con lei questa
   riconciliazione -- parte da sola a casa avviata.

**Non ha soglie di tempo**: ha guardie. E dice nel log, una riga per giro,
cosa ha tolto e perche' si e' fermata.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..home_space.ha_vocabulary import is_entity_id
from ..home_space.house import House
from ..home_space.topology import ha_running
from .recipe_turn import ANSWER_FIELDS
from .state_words import prime_state_translations

logger = logging.getLogger(__name__)

#: I due registri senza i quali un referente mancante non si puo' distinguere
#: da un registro non letto. Sono i nomi di `HomeSpace.unavailable()`.
_NEEDED_REGISTRIES = ("entita", "dispositivi")


@dataclass(frozen=True)
class Reconciliation:
    """Cosa togliere: i soggetti dello scope e i dispositivi del sapere.
    `stopped` e' la guardia che l'ha fermata (allora i due elenchi sono
    vuoti), `None` se e' passata."""
    scope: tuple[str, ...] = ()
    devices: tuple[str, ...] = ()
    stopped: str | None = None


def what_to_forget(house: House, *, read_at: str | None, ha_started: bool,
                   scope_subjects, answered_devices) -> Reconciliation:
    """Cosa non ha piu' un referente nella casa di adesso. Pura: non scrive,
    non chiede niente a Home Assistant -- `ha_started` lo dice chi chiama.

    `scope_subjects` sono i soggetti dello scope (dentro e fuori),
    `answered_devices` i dispositivi che hanno una risposta nel sapere."""
    if read_at is None:
        return Reconciliation(stopped="anagrafe non ancora letta")
    fallen = [name for name in _NEEDED_REGISTRIES if name in house.unavailable]
    if fallen:
        return Reconciliation(stopped="registri non riletti: " + ", ".join(fallen))
    if not house.mirror.readable:
        return Reconciliation(stopped="stato delle entita' non leggibile")
    if not ha_started:
        return Reconciliation(stopped="Home Assistant non si e' dichiarato avviato")
    gone_subjects = tuple(sorted(
        subject for subject in scope_subjects
        if is_entity_id(subject) and house.source(subject) is None))
    present = set(house.device_ids())
    gone_devices = tuple(sorted(d for d in answered_devices if d not in present))
    return Reconciliation(scope=gone_subjects, devices=gone_devices)


async def reconcile(app) -> Reconciliation | None:
    """Applica la riconciliazione agli archivi dell'app, e lo dice nel log.
    `None` se manca un archivio (avvio a meta'): non c'e' niente da
    confrontare."""
    store, knowledge = app.get("observations"), app.get("knowledge")
    home_space = app.get("home_space_store")
    if store is None or knowledge is None or home_space is None:
        return None
    house = House.read(home_space, app.get("entity_cache"))
    answers = knowledge.device_answers(ANSWER_FIELDS)
    plan = what_to_forget(
        house, read_at=home_space.updated_at(),
        ha_started=await ha_running(app.get("ha_client")),
        scope_subjects=list(store.scope()), answered_devices=list(answers))
    if plan.stopped is not None:
        logger.info("riconciliazione: niente tolto, %s", plan.stopped)
        return plan
    scope_rows = store.forget_scope(plan.scope)
    knowledge_rows = sum(knowledge.forget("dispositivo", device, field)
                         for device in plan.devices for field in answers[device])
    logger.info(
        "riconciliazione: tolte %d righe dello scope %s e %d risposte del sapere "
        "di %d dispositivi %s", scope_rows, list(plan.scope), knowledge_rows,
        len(plan.devices), list(plan.devices))
    return plan


async def after_rebuild(app) -> None:
    """Il seguito di ogni ricostruzione dell'anagrafe: le parole degli stati
    (che dipendono dalla cornice appena letta, A-14), poi la riconciliazione.
    Le iscrive `server.py`, all'avvio e sull'ascoltatore di topologia
    (`home_space/registry_follower.schedule_registry_rebuild`)."""
    await prime_state_translations(app)
    await reconcile(app)
