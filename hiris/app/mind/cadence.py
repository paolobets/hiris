"""Ogni quanto l'osservatore ripensa tutta la casa, e perche' il numero non e'
scritto qui dentro.

**La regola (spec §5.2).** *«L'osservatore riconsidera l'intera casa piu'
spesso di quanto duri la memoria di Home Assistant»*. Se ripensa il proprio
campo entro quella finestra, tutto cio' che aveva scartato e' ancora
recuperabile; se la supera, cio' che ha scartato e' perduto -- riscrivere
l'obiettivo fra tre mesi non fa ricomparire i tre mesi mancanti. **E' questo
che sostituisce il pavimento**: non una lista di cose da guardare comunque,
ma la garanzia di potersi ricredere in tempo.

**La finestra non si assume: si misura.** Verificato dal vivo l'11/09/2026:
Home Assistant non la dichiara da nessuna porta -- `recorder/info` risponde e
porta altro (`backlog`, `max_backlog`, `recording`, le migrazioni),
`recorder/config` e `recorder/statistics_info` non esistono proprio
(`unknown_command`). Resta il modo diretto: **calare una sonda e guardare se
torna su con qualcosa** (`HAClient.recorded_changes`).

**Come si cala.** Due raffiche, non una ricerca a tentoni:

1. una **scala grossa** che raddoppia -- 1, 2, 4, ... giorni -- e trova il
   tratto dentro cui sta il confine;
2. una **seconda raffica** che divide quel tratto in otto.

Ogni raffica e' una connessione sola. Misurato sulla casa vera l'11/09/2026:
**7,000 giorni** di memoria, **646 ms e 557 KB** in tutto, e la cadenza che ne
esce e' **3,5 giorni (84 ore)**.

**Si prende sempre la sonda PIENA piu' profonda, mai la prima vuota.** Home
Assistant spento due giorni lascia un tratto vuoto in mezzo alla storia:
fermarsi li' leggerebbe un buco come il confine della memoria, e la casa
riconsidererebbe ogni dodici ore per sempre senza che nessuno capisca perche'.

**Cio' che questa misura promette, e cio' che no.** Promette di non essere mai
piu' LUNGA della memoria vera: e' la sola direzione che fa danno, perche' una
cadenza oltre la memoria butta via cio' che l'osservatore aveva scartato. Non
promette di essere la piu' lunga possibile: un buco che copre un gradino
intero della scala la accorcia, e si riconsidera piu' spesso del necessario
finche' quel buco non esce dalla memoria da solo.
"""
from __future__ import annotations

import time

#: Quanto e' larga ogni sonda. Non e' la risposta -- e' lo spessore del
#: campione: troppo stretta e un'ora tranquilla sembrerebbe memoria finita,
#: troppo larga e ogni sonda costa. Misurato sulla casa vera l'11/09/2026:
#: dieci minuti tornano **300-450 righe** a ogni profondita' che la memoria
#: copra ancora, e **zero** oltre il confine -- un segnale che non e' mai
#: marginale, per 25 KB a sonda.
PROBE_SECONDS = 600.0

#: I gradini della scala grossa, in giorni, raddoppiando. L'ultimo (512
#: giorni, un anno e mezzo) non e' una previsione su quanto un recorder possa
#: tenere: e' dove la scala si ferma, e oltre quel punto la misura torna un
#: limite INFERIORE dichiarato invece di un niente.
LADDER_RUNGS = 10

#: In quante parti si divide il tratto trovato dalla scala grossa. Otto lascia
#: una risoluzione di **mezza giornata** su un tratto di quattro -- quanto
#: basta, visto che la cadenza sara' comunque la meta'.
FINE_STEPS = 8

DAY = 86400.0


def _deepest_remembered(depths: list[float],
                        counts: list[int | None]) -> tuple[float, float | None]:
    """Il tratto dentro cui sta il confine: `(l'ultima piena, la prima vuota
    oltre di essa)`.

    `None` -- la sonda che non ha ricevuto risposta -- non e' ne' piena ne'
    vuota: non sposta il confine in nessuna direzione. Leggerlo come «vuota»
    farebbe di un guasto di rete una memoria corta.
    """
    full = 0.0
    for depth, count in zip(depths, counts, strict=True):
        if count:
            full = depth
    empty = None
    for depth, count in zip(depths, counts, strict=True):
        if depth > full and count == 0:
            empty = depth
            break
    return full, empty


async def measure_memory_window(client, entity_ids: list[str], *,
                                now: float | None = None) -> float | None:
    """Quanti secondi indietro arriva la memoria di Home Assistant, o `None`.

    `None` vuol dire **non misurata** -- Home Assistant muto, o una casa che
    non ricorda niente affatto -- e non si confonde con un numero piccolo: una
    finestra finta sarebbe indistinguibile da una misurata e finirebbe nella
    pagina come se qualcuno l'avesse verificata.

    Il risultato e' sempre una profondita' **provata**: li' dentro c'e' ancora
    qualcosa di registrato. Se la memoria e' piu' lunga dell'ultimo gradino
    della scala, si torna il gradino -- un limite inferiore, che e' comunque
    dentro la memoria vera e quindi sicuro da dimezzare.
    """
    now = time.time() if now is None else now

    def _windows(depths):
        return [(now - d, now - d + PROBE_SECONDS) for d in depths]

    coarse = [DAY * 2 ** k for k in range(LADDER_RUNGS)]
    counts = await client.recorded_changes(entity_ids, _windows(coarse))
    if all(c is None for c in counts):
        return None
    full, empty = _deepest_remembered(coarse, counts)
    if empty is None:
        # La memoria supera l'ultimo gradino: non c'e' nessun tratto da
        # dividere, e la seconda raffica non si paga.
        return full or None

    fine = [full + (empty - full) * k / FINE_STEPS for k in range(1, FINE_STEPS)]
    counts = await client.recorded_changes(entity_ids, _windows(fine))
    finer, _ = _deepest_remembered(fine, counts)
    return max(full, finer) or None


def cadence_from(window_s: float | None) -> float | None:
    """La cadenza di riconsiderazione: **meta'** della finestra misurata.

    **Perche' una frazione e non una sottrazione.** «La finestra meno un
    giorno» diventa negativa su una casa che ricorda dodici ore, e nessuno se
    ne accorge finche' l'osservatore non gira in continuazione. Meta' regge
    qualunque recorder, e lascia un fattore due di margine: anche un giro
    saltato -- add-on fermo, Home Assistant irraggiungibile -- resta dentro
    la memoria.
    """
    if not window_s:
        return None
    return window_s / 2


def due(*, last_ts: float | None, cadence_s: float | None, now: float) -> bool:
    """Se **la cadenza** e' scaduta. Una delle quattro cause, non la domanda
    intera: quella la pone `reason_to_reconsider` qui sotto.

    Mai riconsiderato e' sempre «si'»: al primo avvio l'osservatore non ha
    ancora deciso niente, e senza scope non guarda nulla.

    **Senza cadenza misurata si dice di no.** Questa domanda non ha risposta, e
    delle due bugie possibili questa e' quella che si vede: dire di si' farebbe
    rileggere l'intera casa al modello a ogni giro del lavoro periodico, per
    sempre, senza che nessuno se ne accorga. Le altre tre cause restano in
    piedi lo stesso -- una casa che cresce non deve aspettare che una sonda
    torni a rispondere.
    """
    if not cadence_s:
        return False
    if last_ts is None:
        return True
    return now - last_ts >= cadence_s


def _hours(seconds: float) -> str:
    """Ore, senza decimali inutili: «84», non «84.0»."""
    hours = seconds / 3600
    return f"{hours:.0f}" if abs(hours - round(hours)) < 0.05 else f"{hours:.1f}"


def _days(seconds: float) -> str:
    days = seconds / DAY
    return f"{days:.0f}" if abs(days - round(days)) < 0.05 else f"{days:.1f}"


def reason_to_reconsider(*, last: dict | None, cadence_s: float | None,
                         objective_ts: float | None, undecided: list[str],
                         now: float) -> str | None:
    """**Perche'** l'osservatore dovrebbe ripensare tutta la casa adesso, o
    `None` se non deve.

    Le quattro cause della spec §5.1 -- il primo avvio, l'obiettivo cambiato,
    qualcosa di nuovo in casa, la cadenza -- sono **una domanda sola**, e
    tenerle in quattro controlli sparsi fra chi chiama sarebbe il modo di
    dimenticarne una senza accorgersene.

    **Torna una ragione, non un `True`.** Finisce accanto alla riconsiderazione
    nell'archivio e nella pagina che il proprietario legge: un booleano
    costringerebbe la pagina a reinventare la frase, e la reinventerebbe
    diversa da quella che l'ha davvero provocata.

    **L'ordine delle cause non e' casuale: e' quello della forza.** L'obiettivo
    cambiato viene prima di tutto il resto perche' lo scope e' una risposta a
    una domanda, e cambiata la domanda ogni risposta data prima e' sospetta --
    comprese quelle che escludevano. Le cose nuove vengono prima della cadenza
    perche' non possono aspettare: cio' che non e' osservato non esiste piu', e
    i giorni mancanti non tornano.
    """
    if last is None:
        return "non e' mai stata fatta: l'osservatore non ha ancora deciso niente"

    if objective_ts is not None and last["quando_ts"] < objective_ts:
        return "l'obiettivo e' cambiato dopo l'ultima riconsiderazione"

    if undecided:
        # Si NOMINANO: «ci sono cose nuove» non e' una frase su cui il
        # proprietario possa fare niente. Tre bastano a riconoscere di cosa si
        # parla senza che la ragione diventi un elenco di 400 righe il giorno
        # in cui si installa un'integrazione nuova.
        first = ", ".join(undecided[:3])
        tail = ", e altri" if len(undecided) > 3 else ""
        return (f"{len(undecided)} soggetti in casa su cui nessuno ha ancora "
                f"deciso: {first}{tail}")

    if due(last_ts=last["quando_ts"], cadence_s=cadence_s, now=now):
        return (f"sono passate {_hours(now - last['quando_ts'])} ore dall'ultima "
                f"volta, e la cadenza e' {_hours(cadence_s)} -- meta' dei "
                f"{_days(last['finestra_s'] or cadence_s * 2)} giorni di memoria "
                f"misurati su Home Assistant")

    return None
