"""I **resoconti del giorno**: come si compongono, si recuperano e si riparano.

Nasce il 14/10/2026 col vocabolario della riparazione (N161-1, revisore giro
161): `REPAIR_STATES` e' il gemello di `agent/runner.INIT_STATES` e di
`mind/judgments.SNAPSHOT_STATES`, e non poteva restare in `server.py`. Le
funzioni dei resoconti l'hanno raggiunto qui alla Chiusura (F8 passo 3,
14/10/2026), con un commit di solo spostamento.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from aiohttp import web

from ..home_space.historian import day_boundaries, home_space_zone, house_timezone, local_date
from ..home_space.house import House
from ..home_space.house_history import read_bands, statistic_ids_for_round
from ..home_space.reader import HOME_SPACE_KEY
from ..live_value import LiveValue
from ..proxy.entity_cache import ENTITY_CACHE_KEY
from . import recipe_turn
from .facts import aggregate_day, chronicle_is_stale, rebuild_chronicle
from .flatline import HISTORY_DAYS, frozen_day, mark_excluded, split_at
from .judgments import TYPE_JUDGMENTS_KEY
from .knowledge import KNOWLEDGE_KEY
from .recipes import Recipe, hourly_points, muted_recipes, silent_entities, unread_series
from .store import OBSERVATIONS_KEY, READING_RETENTION_S

#: Le chiavi di `app` che questo modulo possiede: `web.AppKey`, mai una
#: stringa (X-32, Chiusura dello sprint).
BACKFILL_QUIET_KEY = web.AppKey("backfill_quiet")
LAST_REPAIR_KEY = web.AppKey("ultima_riparazione", LiveValue)

logger = logging.getLogger(__name__)

#: Il vocabolario chiuso di `stato` in `app[LAST_REPAIR_KEY]` (C-30): la
#: forma comune degli oggetti diagnostici di `/api/health`, che aprono tutti
#: con `stato` e `perche` (come `agent/runner.INIT_STATES` e
#: `mind/judgments.SNAPSHOT_STATES`). Fino alla Chiusura la chiave era
#: `oggetti`.
REPAIR_DONE, REPAIR_RAISED = "fatta", "sollevata"
REPAIR_STATES = (REPAIR_DONE, REPAIR_RAISED)


#: Quanto tace il log per un giorno di `backfill_one_report` che non si fa, dopo
#: averlo detto una volta. Decisioni del proprietario, 17/09/2026: prima per la
#: cronaca che non si rifa', poi -- lo stesso giorno -- anche per il resoconto
#: che non si recupera (Home Assistant irraggiungibile). Il giro gira ogni
#: cinque minuti: senza, lo stesso warning uscirebbe a ogni giro, in entrambi i
#: rami. Il comportamento dei rami non cambia (il «manca» torna `None` e
#: riprova), cambia solo quante volte lo dicono.
#:
#: **I due rami condividono la voce del giorno**, di proposito: un giorno sta in
#: un ramo solo alla volta (un resoconto che manca non ha una cronaca da rifare),
#: e passa dal primo al secondo solo RIUSCENDO, cioe' togliendo la voce. Due
#: chiavi separate non direbbero niente di piu', e sarebbero due posti per lo
#: stesso fatto: «questo giorno non si riesce a fare».
#:
#: Lo stato vive in `app[BACKFILL_QUIET_KEY]` (giorno ->
#: istante dell'ultimo warning), **creato vuoto da `_on_startup`**, prima che
#: aiohttp congeli l'app: il giro gira ad app avviata, e aggiungere una chiave a
#: quel punto e' «Changing state of started or joined application» (stessa
#: regola di `api/handlers_mcp.create_rounds_per_exchange`, M-2). Un riavvio lo
#: azzera, e il warning si riscrive una volta -- accettato.
#:
#: Una voce per giorno FALLITO; si toglie quando quel giorno riesce, e altrimenti
#: non si pota finche' il processo vive. Il conto e' limitato: un giorno uscito
#: dal grezzo non entra piu' in nessuno dei due rami, e i giorni del grezzo sono 22.
BACKFILL_QUIET_S = 4 * 3600


def _backfill_warning_due(app, day: str, clock: float) -> bool:
    """Se il warning di `day` va scritto adesso: si' la prima volta e dopo
    `BACKFILL_QUIET_S` dall'ultimo, e in quel caso segna l'istante. Una sola
    regola per i due rami di `backfill_one_report`."""
    quiet = app[BACKFILL_QUIET_KEY]
    if clock - quiet.get(day, float("-inf")) < BACKFILL_QUIET_S:
        return False
    quiet[day] = clock
    return True


async def backfill_one_report(app, ha_client, *,
                              now=datetime.now) -> str | None:
    """Il resoconto di **un** giorno che manca o la cui cronaca e' nata con un
    altro giudizio. Torna quale, o `None`.

    **Perche' esiste, col numero.** Misurato sulla casa vera il 14/09/2026,
    appena il resoconto ha cominciato a nascere: esistevano quello del 12 e
    quello del 13, e basta. Il 7, l'8, il 9, il 10 e l'11 avevano oggetti e
    grezzo e **nessun resoconto** -- la riparazione d'avvio guarda solo gli
    ultimi due giorni pieni, e l'aggregazione notturna solo ieri. Nessuno dei
    due percorsi arriva indietro, e per l'analista quei giorni non esistono:
    una misura letta su due giorni non e' una serie.

    **Un giorno per giro.** Le statistiche di Home Assistant si chiedono una
    volta per giorno: ventidue richieste all'avvio ritarderebbero la partenza
    per un lavoro che non ha nessuna fretta. E' la stessa disciplina di
    `recipe_round` -- uno per volta, e in qualche ora si e' coperto tutto.

    **Dal piu' VECCHIO.** E' quello che sta per scadere: il suo grezzo sparisce
    per primo (22 giorni), e dopo non si rifa' piu'. Partire dal piu' recente
    vorrebbe dire perdere proprio i giorni per cui questo lavoro esiste.

    **Non oltre il grezzo.** Un giorno si rifa' solo finche' il suo grezzo
    esiste (spec §9). Andare piu' indietro scriverebbe resoconti VUOTI per
    giorni in cui era successo di tutto, e un resoconto vuoto dice «non e'
    successo niente»: una bugia archiviata, nell'archivio che esiste per non
    dirne.

    **Un giorno mancante si fa intero; uno gia' scritto non si sovrascrive
    mai per intero.** Le misure di un giorno scritto restano quelle: stessa
    asimmetria di `_write_missing_reports` e di `store._migration_8`.

    **Ma la sua cronaca si', quando e' nata con un altro giudizio** (dal
    17/09/2026, spec `docs/design/2026-09-16-il-giudizio-dei-tipi.md` §6):
    l'impronta del resoconto e' diversa da quella dell'istantanea corrente, o
    manca (`facts.chronicle_is_stale`). Allora `facts.rebuild_chronicle`
    sostituisce **solo** `cronaca` e `giudizio` -- nessuna lettura di Home
    Assistant, nessuna ricetta. Stesso giro, stesse regole: un giorno per
    giro, dal piu' vecchio, mai oltre il grezzo.

    **Il giorno a cavallo della potatura non si rifa'** (revisione del
    17/09/2026, eseguita): la potatura taglia a un istante e non a mezzanotte,
    quindi il giorno in cui cade il taglio ha perso le sue voci nate prima. Non
    si possono ricostruire, e rifarlo le cancellerebbe: quel giorno tiene la
    cronaca e l'impronta che ha. Solo per la cronaca: un giorno MANCANTE a cavallo si scrive
    ancora, com'era.

    **La condizione e' «nessuna riga di questo giorno puo' essere stata
    potata»**, cioe' l'inizio del giorno oltre il taglio della potatura
    (`adesso - READING_RETENTION_S`, dov'esso taglia: `mind/store.prune`) --
    **non** un confronto con la riga piu' vecchia dell'archivio (giro di
    correzioni 1, punto 1, riprodotto). Le due condizioni coincidono su una
    casa potata, dove la riga piu' vecchia E' il taglio, e divergono su una
    casa **giovane**: li' la riga piu' vecchia e' soltanto l'ora
    d'installazione, il primo giorno comincia a mezzanotte e con la vecchia
    condizione restava al giudizio vecchio per sempre, in silenzio.

    **Ogni giorno rifatto logga una riga con la durata**: e' la misura vera di
    quanto costa un giorno sull'host di Home Assistant, che la spec (§1,
    misura 12) non ha. Un giro che non ha niente da fare non logga niente.

    Non solleva: gira per sempre. **I due rami falliscono in modo diverso, e
    reagiscono in modo diverso.** Un giorno mancante che non si scrive torna
    `None` e si riprova al giro dopo dallo stesso giorno: i suoi errori sono
    la rete verso Home Assistant, e passano. Una cronaca che non si rifa' e'
    un difetto locale e deterministico -- fallirebbe a ogni giro -- e dal piu'
    vecchio fermerebbe per sempre ogni giorno dopo, al primo avvio tutti: si
    logga e si passa al giorno successivo nello stesso giro. **In entrambi i
    rami** il warning esce una volta per giorno ogni `BACKFILL_QUIET_S`, non a
    ogni giro, e una riuscita toglie la voce del giorno (Task 7b, decisioni del
    proprietario del 17/09/2026).
    """
    archivio = app[OBSERVATIONS_KEY]
    first_ts = archivio.oldest_reading_ts()
    if first_ts is None:
        return None
    timezone = house_timezone(app.get(HOME_SPACE_KEY))
    adesso = now(UTC)
    today = local_date(adesso.timestamp(), timezone)
    first_day = local_date(first_ts, timezone)
    # Il taglio della potatura, calcolato come lo calcola lei
    # (`mind/store.prune`: `quando_ts < now - READING_RETENTION_S`). Un giorno
    # che comincia da qui in poi non puo' aver perso nessuna riga, e si rifa'.
    oldest_intact_ts = adesso.timestamp() - READING_RETENTION_S

    day = first_day
    while day < today:
        as_text = day.strftime("%Y-%m-%d")
        written = archivio.report(as_text)
        if written is None:
            try:
                await write_day_report(app, ha_client, day=as_text, timezone=timezone,
                                       when_ts=now(UTC).timestamp())
            except Exception as error:
                if _backfill_warning_due(app, as_text, now(UTC).timestamp()):
                    logger.warning(
                        "cervello: resoconto di %s non recuperato (%s: %s) -- per questo "
                        "giorno il log tace per %d ore", as_text, type(error).__name__,
                        error, BACKFILL_QUIET_S // 3600)
                return None
            app[BACKFILL_QUIET_KEY].pop(as_text, None)
            logger.info("cervello: recuperato il resoconto di %s", as_text)
            return as_text
        if (chronicle_is_stale(written, app[TYPE_JUDGMENTS_KEY].value)
                and day_boundaries(as_text, timezone)[0] >= oldest_intact_ts):
            started = time.monotonic()
            try:
                rebuild_chronicle(store=archivio, day=as_text, timezone=timezone,
                                  judgments=app[TYPE_JUDGMENTS_KEY].value,
                                  house=House.read(app.get(HOME_SPACE_KEY),
                                                   app.get(ENTITY_CACHE_KEY)),
                                  when_ts=now(UTC).timestamp())
            except Exception as error:
                if _backfill_warning_due(app, as_text, now(UTC).timestamp()):
                    logger.warning(
                        "cervello: cronaca di %s non rifatta (%s: %s) -- per questo "
                        "giorno il log tace per %d ore", as_text, type(error).__name__,
                        error, BACKFILL_QUIET_S // 3600)
                day += timedelta(days=1)
                continue
            app[BACKFILL_QUIET_KEY].pop(as_text, None)
            logger.info(
                "cervello: rifatta la cronaca di %s col giudizio %s in %.2f s",
                as_text, app[TYPE_JUDGMENTS_KEY].value.chronicle_fingerprint(),
                time.monotonic() - started)
            return as_text
        day += timedelta(days=1)
    return None


async def _write_missing_reports(app, ha_client, days, timezone, *,
                                 when_ts: float) -> list[str]:
    """Il resoconto dei giorni che **non ne hanno uno**, e solo quelli.

    La riparazione d'avvio ha quattro uscite anticipate, tutte per la regola
    *«chi SOSTITUISCE non tollera il parziale»*: scrivere oggetti poveri sopra
    oggetti ricchi e' un impoverimento, non una riparazione. La regola e'
    giusta per gli oggetti.

    **Per il resoconto e' il contrario, e si e' misurato dal vivo il
    14/09/2026**: sulla casa vera non esisteva nessun resoconto, perche' una
    di quelle uscite scattava a ogni avvio e l'unico altro scrittore e'
    l'aggregazione delle 00:20. Un resoconto sa dire cio' che non ha potuto
    calcolare -- «non calcolabile, e perche'», che e' il terzo innesco
    dell'analista; un resoconto che non c'e' non dice niente, e non si
    distingue da un giorno in cui non e' successo nulla.

    **Ma l'asimmetria resta, spostata**: si scrivono solo i giorni che un
    resoconto non ce l'hanno. Uno gia' scritto dalla notte ha anche le misure,
    e sostituirlo con una cronaca nuda perche' stamattina la rete era giu'
    sarebbe lo stesso impoverimento, su un altro strato. E' la stessa regola
    di `store._migration_8` per gli oggetti storici.

    Non solleva: e' una consolazione, non il lavoro principale, e non deve
    poter far fallire un avvio.
    """
    archivio = app[OBSERVATIONS_KEY]
    scritti: list[str] = []
    for day in days:
        try:
            if archivio.report(day) is not None:
                continue
            await write_day_report(app, ha_client, day=day, timezone=timezone,
                                   when_ts=when_ts)
            scritti.append(day)
        except Exception as error:
            logger.warning(
                "cervello: resoconto di %s non scritto durante la riparazione "
                "(%s: %s)", day, type(error).__name__, error)
    return scritti


async def reaggregate_last_two_days(app, ha_client, *, now=datetime.now) -> None:
    """La riparazione d'avvio, **che dice sempre com'e' andata**.

    Il corpo vero e' `_reaggregate_days` qui sotto: questa e' la sola cosa che
    gli sta attorno. Il corpo scrive il proprio esito in
    `app[LAST_REPAIR_KEY]` solo se arriva in fondo; **se solleva prima**,
    l'eccezione risale al chiamante, che la ingoia in un warning, e senza
    questo involucro `GET /api/health` resterebbe a `riparazione: null`. Cioe'
    «non e' girata»: falso, ed e' proprio la domanda a cui deve rispondere.

    **L'eccezione continua a propagare**: il contratto col chiamante non
    cambia, e' lui a decidere se contenerla. Qui si aggiunge solo la memoria
    di cio' che e' successo.
    """
    try:
        await _reaggregate_days(app, ha_client, now=now)
    except Exception as error:
        app[LAST_REPAIR_KEY].set({
            "stato": REPAIR_RAISED,
            "perche": f"{type(error).__name__}: {error}",
            "giorni": [], "resoconti_scritti": []})
        raise


async def _reaggregate_days(app, ha_client, *, now=datetime.now) -> None:
    """All'avvio, scrive il resoconto degli ultimi due giorni pieni che non ce
    l'hanno (oggi escluso: non e' ancora finito).

    **Qui il resoconto non si sostituisce mai**: si scrive solo dove manca, ed
    e' `_write_missing_reports` a farlo. L'unica sostituzione e' la sola
    cronaca nata con un altro giudizio, e la fa il recupero
    (`backfill_one_report`).

    **Perche' esiste ancora, accanto al recupero periodico.** Il recupero
    (`backfill_one_report`) scrive un giorno ogni cinque minuti dal
    piu' vecchio: gli ultimi due arriverebbero per ultimi, ore dopo l'avvio.
    Questa li mette davanti subito, che e' cio' che il proprietario guarda
    quando riapre la pagina.

    **L'eccezione si lascia propagare**, come prima: e' il chiamante a
    decidere se contenerla.

    `now` e' iniettabile per i test: nella vita vera nessuno lo passa.
    """
    timezone = house_timezone(app.get(HOME_SPACE_KEY))
    today = local_date(now(UTC).timestamp(), timezone)
    days = [(today - timedelta(days=delta)).strftime("%Y-%m-%d") for delta in (2, 1)]
    written = await _write_missing_reports(app, ha_client, days, timezone,
                                           when_ts=now(UTC).timestamp())
    app[LAST_REPAIR_KEY].set({"stato": REPAIR_DONE, "perche": None,
                              "giorni": days, "resoconti_scritti": written})
    if written:
        logger.info("cervello: resoconti scritti all'avvio per %s",
                    ", ".join(written))


async def _report_ingredients(app, ha_client, *, giorno: str,
                                     timezone: str | None):
    """Le ricette, le serie e i nomi che servono al resoconto di un giorno.

    Torna `(ricette, serie, nomi, silent, mute)`: `silent` sono le entita'
    che non daranno una serie, ognuna col suo rifiuto -- frase e causa
    (`recipes.silent_entities`, B-26) -- o `None` se non si e' potuto
    chiedere; `mute` sono le ricette che non possono produrre perche' ogni
    loro entita' tace per una causa che non passa da sola
    (`recipes.muted_recipes`, piano degli attori, Task 1.5): escono da
    `ricette`, le loro serie non si chiedono, e il resoconto le dice con una
    riga per dispositivo. Ricette vuote -- nessun dispositivo ne ha
    una, o il sapere non e' collegato -- fanno un resoconto con la meta' delle
    misure vuota, ed e' un fatto vero su quella casa: si scrive.

    **Le statistiche si chiedono una volta per tutte le ricette**: le entita'
    che ogni ricetta nomina si raccolgono prima, invece di una richiesta per
    dispositivo. Quali di quelle entita' hanno statistiche lo dice
    `statistic_ids_for_round`, la lettura condivisa col giro delle ricette.
    """
    sapere = app.get(KNOWLEDGE_KEY)
    casa = app.get(HOME_SPACE_KEY)
    if sapere is None or casa is None:
        return {}, {}, {}, None, {}
    # I dispositivi e i loro nomi li dice la casa (Task 12): il nome,
    # altrimenti l'id (`House.name`).
    house = House.read(casa, app.get(ENTITY_CACHE_KEY))
    nomi = {device_id: house.name("dispositivo", device_id)
            for device_id in house.device_ids()}
    # Le ricette di tutti in una lettura (A-38), nell'ordine dell'anagrafe.
    scritte = recipe_turn.recipes(sapere)
    ricette = {device_id: scritte[device_id] for device_id in nomi
               if device_id in scritte}
    # Le ricette di un dispositivo che tace tutto non girano (G-02, G-03):
    # lo stato della fonte si chiede alla stessa casa del giro.
    mute = muted_recipes(house, ricette)
    ricette = {device_id: recipe for device_id, recipe in ricette.items()
               if device_id not in mute}
    if not ricette:
        return {}, {}, nomi, None, mute
    entita = sorted({e for r in ricette.values() for e in Recipe(r).entities()})
    da_ts, a_ts = day_boundaries(giorno, timezone)
    # **Quali di queste entita' non avranno MAI una serie** (spec §6, primo
    # «rifiuta se»). Una lettura sola per giro, come le statistiche: il
    # registro di Home Assistant e' un elenco di nomi, non una serie.
    # `None` -- non l'insieme vuoto -- se non si e' potuto leggere: affermare
    # «nessuna entita' ha statistiche» farebbe rifiutare tutto il resoconto.
    # Si legge PRIMA delle serie (dal 06/10/2026): dice anche le sorelle che
    # la regola del dato fermo chiede (`House.sibling_group`).
    with_statistics = await statistic_ids_for_round(app, ha_client)
    if isinstance(with_statistics, dict):  # la busta del guasto (D3)
        logger.warning("resoconto: elenco delle statistiche non letto (%s): %s",
                       with_statistics.get("causa"), with_statistics.get("errore"))
        list_read = False
        # Senza l'elenco si chiedono TUTTE le sorelle possibili -- dispositivo
        # e istanza -- e chi ha statistiche lo dice la risposta delle serie
        # (sotto). Il ripiego sullo `state_class` dello specchio perdeva i
        # termometri del 29/09 (G7-1, rimisura dello sprint su 413ce7a7,
        # 06/10/2026): nello specchio non lo portavano.
        lette = sorted({c for e in entita for c in house.possible_siblings(e)})
    else:
        list_read = True
        counted = house.with_statistics(with_statistics)
        lette = sorted({s for e in entita for s in counted.siblings(e) or [e]})
    # **Il giorno e la sua storia in UNA lettura, con le sorelle** (attori,
    # Task 1.3; proposta del 06/10/2026): la regola del dato fermo giudica il
    # gruppo di ogni entita' contro la stessa ora dei giorni prima
    # (`mind/flatline.py`). La finestra si allunga di `HISTORY_DAYS` e le
    # sorelle entrano nella stessa richiesta: nessuna richiesta in piu'.
    history_start_ts = da_ts - HISTORY_DAYS * 86400
    report = await read_bands(
        ha_client, lette, datetime.fromtimestamp(history_start_ts, tz=UTC),
        datetime.fromtimestamp(a_ts, tz=UTC))
    if "errore" in report:
        # **Un guasto delle statistiche non e' un resoconto senza misure.** Si
        # scrivono le ricette senza serie: ogni misura esce «non calcolabile»
        # dicendo che le statistiche non si sono potute leggere -- e l'analista
        # la vede sparire, che e' il suo terzo innesco. Fino al 04/10/2026
        # questo commento lo prometteva e la misura diceva invece «la serie
        # e' vuota» (trovato 7 del piano della Tappa 3, S-28).
        logger.warning("resoconto: statistiche non lette per %s (%s)",
                       giorno, report["errore"])
        refusal = unread_series(str(report["errore"]))
        return ricette, {}, nomi, {e: refusal for e in entita}, mute
    if not list_read:
        # **Chi ha statistiche, detto da Home Assistant.** `recorder/
        # statistics_during_period` risponde solo per gli id che hanno righe
        # nella finestra (`recorder/statistics.py::_sorted_statistics_to_dict`,
        # `seen_statistic_ids`, letto sul tag `2026.9.0` il 06/10/2026): la
        # risposta e' un elenco anche lei, quello della finestra letta. La
        # regola resta una, `House.has_statistics`; cambia solo da quale
        # risposta di Home Assistant viene l'elenco.
        counted = house.with_statistics(frozenset(
            e for e, punti in report["serie"].items() if punti))
    gruppi = {}
    for e in entita:
        for sorella in counted.siblings(e) or [e]:
            gruppi[sorella] = counted.sibling_group(sorella)
    finestra = {e: hourly_points(report["serie"].get(e) or []) for e in gruppi}
    # **Una fonte ferma non da' un numero falso** (D4): il 30/09/2026 il
    # resoconto ha scritto produzione 0 con copertura 1.0, e lo zero era
    # falso. Un contatore fermo fino a sera si rifiuta, fra le entita' che
    # tacciono; una misura istantanea perde solo le ore ferme, segnate sui
    # punti (decisione dell'08/10/2026, `mind/flatline.frozen_day`).
    ferme, escluse = frozen_day(finestra, gruppi, day_start_ts=da_ts, entity_ids=entita,
                                zone=home_space_zone(timezone))
    serie = {e: mark_excluded(split_at(finestra[e], da_ts)[1], escluse.get(e))
             for e in entita}
    if ferme or escluse:
        logger.info("resoconto: %d entita' ferme il %s, %d con ore ferme -- le "
                    "loro misure diranno perche'", len(ferme), giorno, len(escluse))
    if not list_read:
        # Di quali entita' non abbiano statistiche non si afferma niente: una
        # serie vuota nella finestra non e' «nessuna statistica». Che una
        # fonte sia ferma si e' visto sulle serie, e resta (G7-1).
        return ricette, serie, nomi, ferme or None, mute
    # Il perche' di ognuna dalla FONTE (B-26; Tappa 3, Task 8): la
    # stessa casa del giro, con l'elenco appena letto -- nessuna seconda
    # lettura di `recorder/list_statistic_ids`.
    silent = silent_entities(counted, entita)
    if silent:
        logger.info(
            "resoconto: %d entita' su %d nominate dalle ricette non hanno "
            "statistiche in Home Assistant -- le loro misure diranno perche'",
            len(silent), len(entita))
    if silent is None:
        return ricette, serie, nomi, ferme or None, mute
    return ricette, serie, nomi, {**ferme, **silent}, mute


async def write_day_report(app, ha_client, *, day: str, timezone: str | None,
                           when_ts: float) -> int:
    """Scrive il resoconto di `day` e torna quante voci di cronaca porta.

    **L'unica strada del resoconto di un giorno** (D-36, 06/10/2026): gli
    ingredienti letti da Home Assistant (`_report_ingredients`) e poi
    `facts.aggregate_day` con l'istantanea viva dei giudizi e la casa di
    adesso -- che serve a chiudere gli episodi di cio' che Home Assistant non
    nomina piu' (`facts.build_episodes`). Fino a quel giorno la stessa coppia
    era scritta tre volte: la notte (`startup.nightly_aggregation_job`), il recupero
    (`backfill_one_report`) e la riparazione d'avvio
    (`_write_missing_reports`). Lo difende
    `tests/test_fonte_unica.py::test_d36_il_resoconto_di_un_giorno_ha_una_strada_sola`.

    **Sostituisce sempre** (`aggregate_day` e' idempotente): se un giorno gia'
    scritto si possa rifare lo decide chi chiama, e cosi' la politica sugli
    errori -- la notte li logga, il recupero li silenzia per giorno, la
    riparazione li conta giorno per giorno. Qui si solleva.

    `when_ts` e' l'istante della scrittura, dall'orologio di chi chiama (G-14):
    il recupero e la riparazione passano il loro `now`, la notte l'ora del
    lavoro.
    """
    ricette, serie, nomi, silent, mute = await _report_ingredients(
        app, ha_client, giorno=day, timezone=timezone)
    return aggregate_day(
        store=app[OBSERVATIONS_KEY], day=day, timezone=timezone,
        recipes=ricette, series=serie, names=nomi,
        silent=silent, muted=mute,
        judgments=app[TYPE_JUDGMENTS_KEY].value,
        house=House.read(app.get(HOME_SPACE_KEY), app.get(ENTITY_CACHE_KEY)),
        when_ts=when_ts)
