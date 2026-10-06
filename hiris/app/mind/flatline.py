"""Il dato fermo: dove una serie smette di muoversi, giudicato contro la sua storia.

Piano degli strati 1-2 degli attori, Task 1.1; decisione D3 del proprietario
(03/10/2026). Il caso che lo chiede e' quello del 30/09/2026 (BACKLOG, «Un
contatore CONGELATO non si distingue da un giorno a zero»): l'inverter ha smesso
di aggiornare i contatori, e il resoconto ha scritto produzione 0 con copertura
1.0. La copertura conta le ore che hanno un valore, non se quel valore dice
qualcosa: un'ora con cambio 0 e' un'ora «conosciuta».

**Nessuna soglia scritta da noi** (spec dei tre attori §10: *«Non si inventa
una soglia: si archivia e si interpreta»*). Un'ora e' **immobile** se non varia
-- cambio 0 per un contatore, `minimo == massimo` per una misura istantanea -- e
l'immobilita' e' **anomala** solo se la stessa ora, in **ogni** giorno della
storia che ha un valore, variava. La notte del fotovoltaico e' immobile e non e'
anomala: la sua storia, a quell'ora, e' immobile anche lei.

**Un tratto** sono ore immobili consecutive. E' «ferma» se almeno una sua ora e'
anomala, e allora il tratto comincia dove comincia l'immobilita', non alla prima
ora anomala: il 30/09 la produzione e' immobile dalla mezzanotte, ed e' quello
il «dal» vero, anche se di notte, da sola, non avrebbe detto niente.

**Una storia che non basta dice «non lo so»**, mai «ferma». Quanta storia basta
e' anch'esso un numero, e non lo scriviamo: basta **un** giorno con un valore a
quell'ora -- il minimo sotto cui non c'e' nessuna prova -- e il tratto porta
quanti giorni l'hanno sostenuto (`giorni_di_storia`), perche' chi lo legge sappia
quanto e' sottile la base (§10: *«va detto che la base e' sottile»*).

**Funzione pura**: non legge archivi ne' rete. La serie del giorno e la sua
storia arrivano da chi chiama, nella forma di `server._punti_orari`; la storia e'
una lista sola di punti dei giorni precedenti, e «la stessa ora» e' lo stesso
istante un numero intero di giorni prima.

**Il resoconto la usa dal Task 1.3** (D4 del proprietario, 03/10/2026: una
misura su una fonte ferma si RIFIUTA, «mai un numero plausibile»).
`server._report_ingredients` chiede le statistiche del giorno e della sua
storia in una lettura sola (`HISTORY_DAYS`), le separa con `split_at`, e
`frozen_refusals` trasforma i tratti fermi in rifiuti con causa
`operations.FROZEN`: entrano fra le entita' che tacciono (`silent`), la
strada che `Recipe.run` conosce gia'. Il recupero dei resoconti e la
riparazione d'avvio passano dagli stessi ingredienti, quindi un giorno
rifatto esce con la stessa causa.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..home_space.historian import instant_epoch
from .operations import FROZEN, NotComputable

_DAY_S = 86400

#: Gli esiti di un tratto. Lista di ammissione chiusa. «ferma» e' la parola
#: del vocabolario delle cause (`operations.FROZEN`), e non se ne scrive una
#: seconda copia: il tratto e il rifiuto della misura dicono lo stesso fatto.
UNKNOWN = "non_lo_so"

#: Quanti giorni di storia legge il resoconto per giudicare un giorno. Non e'
#: una soglia del giudizio -- la regola ne vuole almeno uno, e dice su quanti
#: si e' appoggiata (`giorni_di_storia`) -- ma il costo della lettura: la
#: finestra delle statistiche passa da un giorno a otto, sempre in UNA
#: richiesta per giro di resoconto (R16). Una settimana perche' ogni giorno
#: della settimana ci compare una volta: le abitudini della casa hanno quel
#: passo. **Il limite, detto**: la regola chiede che la stessa ora abbia
#: variato in OGNI giorno della storia, quindi una fonte ferma da piu' giorni
#: esce «ferma» solo nel primo -- dal secondo la sua storia contiene gia' il
#: blocco, e lo spiega. Nel caso del 30/09 il blocco e' cominciato quel giorno.
HISTORY_DAYS = 7


def _still(point: dict) -> bool | None:
    """Se l'ora non varia: `True`, `False`, o `None` se di lei non si sa niente.

    Un contatore porta `valore` (il cambio dell'ora); una misura istantanea
    porta `minimo` e `massimo`. Un'ora senza ne' l'uno ne' gli altri e' un buco,
    non un'ora immobile.
    """
    value = point.get("valore")
    if value is not None:
        return value == 0
    low, high = point.get("minimo"), point.get("massimo")
    if low is not None and high is not None:
        return low == high
    return None


def _history_by_hour(history) -> dict[float, list[tuple[float, bool]]]:
    """La storia indicizzata per ora del giorno (secondi dalla mezzanotte UTC).

    Si tiene anche l'istante, perche' vale solo la storia PRECEDENTE all'ora
    giudicata.
    """
    by_hour: dict[float, list[tuple[float, bool]]] = {}
    for point in history or []:
        if not isinstance(point, dict):
            continue
        start = instant_epoch(point.get("inizio"))
        still = _still(point)
        if start is None or still is None:
            continue
        by_hour.setdefault(start % _DAY_S, []).append((start, still))
    return by_hour


def _verdict(start: float, by_hour) -> tuple[bool | None, int]:
    """Se l'immobilita' di quest'ora e' anomala, e su quanti giorni di storia.

    `None` se nessun giorno precedente ha un valore a quest'ora: non lo so.
    """
    past = [still for moment, still in by_hour.get(start % _DAY_S, [])
            if moment < start and (start - moment) % _DAY_S == 0]
    if not past:
        return None, 0
    return not any(past), len(past)


def _stretch(run: list[dict], verdicts) -> dict:
    anomalous = [days for anomaly, days in verdicts if anomaly]
    known = [days for anomaly, days in verdicts if anomaly is not None]
    start, end = run[0]["inizio"], run[-1]["fine"]
    if anomalous:
        days = max(anomalous)
        return {"dal": start, "al": end, "esito": FROZEN,
                "giorni_di_storia": days,
                "perche": (f"non varia dalle {start} alle {end}, e alla stessa "
                           f"ora ha sempre variato in ciascuno dei {days} giorni "
                           f"di storia")}
    return {"dal": start, "al": end, "esito": UNKNOWN,
            "giorni_di_storia": max(known, default=0),
            "perche": (f"non varia dalle {start} alle {end}, e la sua storia non "
                       f"copre queste ore: non si sa se sia normale")}


def split_at(points, instant_ts: float) -> tuple[list[dict], list[dict]]:
    """I punti divisi in `(prima, da li' in poi)` rispetto a `instant_ts`.

    Il resoconto legge giorno e storia in una richiesta sola: questa e' la
    riga che li separa. Un punto senza un istante leggibile resta col giorno,
    dove stava prima del Task 1.3 (le operazioni lo trattano come lo
    trattavano); nella storia non entrerebbe comunque (`_history_by_hour`).
    """
    before: list[dict] = []
    after: list[dict] = []
    for point in points or []:
        start = instant_epoch(point.get("inizio")) if isinstance(point, dict) else None
        (before if start is not None and start < instant_ts else after).append(point)
    return before, after


def frozen_refusals(series: Mapping[str, list],
                    history: Mapping[str, list]) -> dict[str, NotComputable]:
    """Per ogni entita' con almeno un tratto «ferma», il rifiuto delle sue
    misure: `{entity_id: NotComputable(..., cause=FROZEN)}`.

    D4 «rifiutata»: la misura non diventa un numero marcato ma un «non
    calcolabile», con la frase che dice il tratto e perche'. Un tratto «non lo
    so» non rifiuta niente: non c'e' una prova, e una misura non si toglie
    senza prova. Le entita' senza tratti fermi non compaiono.
    """
    refusals: dict[str, NotComputable] = {}
    for entity_id, points in (series or {}).items():
        frozen = [t for t in flatline_stretches(points, history=history.get(entity_id))
                  if t["esito"] == FROZEN]
        if frozen:
            refusals[entity_id] = NotComputable(
                f"{entity_id} e' ferma: " + " · ".join(t["perche"] for t in frozen),
                cause=FROZEN)
    return refusals


def flatline_stretches(series, *, history) -> list[dict]:
    """I tratti in cui la serie non si muove, ognuno col suo giudizio.

    Torna una lista di `{"dal", "al", "esito", "perche", "giorni_di_storia"}`:
    `esito` e' `"ferma"` o `"non_lo_so"`. Un tratto immobile che la storia
    spiega (la notte del fotovoltaico) non esce affatto: e' la serie che fa
    quello che ha sempre fatto.
    """
    by_hour = _history_by_hour(history)
    points = sorted(
        ((start, p) for p in series or [] if isinstance(p, dict)
         for start in [instant_epoch(p.get("inizio"))] if start is not None),
        key=lambda pair: pair[0])
    stretches: list[dict] = []
    run: list[dict] = []
    verdicts: list[tuple[bool | None, int]] = []
    previous_end: float | None = None

    def close() -> None:
        if not run:
            return
        anomalies = [anomaly for anomaly, _ in verdicts]
        # Un tratto spiegato in ogni sua ora dalla storia non esce.
        if any(anomalies) or None in anomalies:
            stretches.append(_stretch(run, verdicts))
        run.clear()
        verdicts.clear()

    for start, point in points:
        # Un'ora mancante fra due presenti spezza il tratto: di lei non si sa
        # niente, e un tratto non attraversa cio' che non si sa.
        if previous_end is not None and start != previous_end:
            close()
        previous_end = instant_epoch(point.get("fine"))
        if _still(point) is not True:
            close()
            continue
        run.append(point)
        verdicts.append(_verdict(start, by_hour))
    close()
    return stretches
