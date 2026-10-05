"""Il tempo della casa: il fuso, i confini di un giorno e la lettura di un
istante -- le tre cose che ogni parte di HIRIS che parla di tempo deve dire
allo stesso modo.

Non archivia NIENTE. La decisione del proprietario e' esplicita -- «deve
leggere da HA sempre» -- e non e' una preferenza: HIRIS ha gia' avuto un
archivio storico suo (`history.db`), e' uscito perche' scriveva senza che
nessuno leggesse.

Qui stanno le funzioni che il resto del prodotto usa: `house_timezone`,
`home_space_zone`, `local_date`, `today`, `day_boundaries`, `instant_epoch`,
`instant_out`.
La storia che la chat interroga (la superficie, il campione, «per mano di
HIRIS») vive in `home_space/house_history.py`.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime, timedelta

logger = logging.getLogger(__name__)


def house_timezone(home_space) -> str | None:
    """Il NOME del fuso della casa, letto da `HomeSpace.reference_frame()` --
    `None` se l'anagrafe non c'e' ancora (avvio a meta', o un test che non la
    costruisce) o se non lo sa.

    **L'unico lettore** del fuso della casa (Tappa 3, Task 10, B-15). Prima
    ce n'erano due: `server._timezone_from_home_space_store`, chiamato dai
    giri e da due gestori che lo importavano da `server` per nome privato, e
    `ToolDispatcher._timezone`, che rileggeva lo stesso `reference_frame()` per
    conto suo. Lo stesso fatto in due posti: se ne tiene uno, qui, accanto
    alle funzioni che il fuso lo usano.
    """
    return home_space.reference_frame().get("fuso") if home_space else None


def home_space_zone(timezone: str | None):
    """Il fuso della casa, o UTC se non lo sappiamo. Non inventa mai.

    Un fuso sbagliato sposta le ore di una risposta senza che nessuno se ne
    accorga: e' peggio di non averlo. Con UTC almeno l'offset e' scritto
    nell'istante, e chi legge puo' fare i conti.

    **Pubblica**: la importano altri moduli, e un nome con underscore
    attraversato da fuori e' esattamente come nascono i doppioni -- il
    prossimo che ne ha bisogno o importa il nome privato o riscrive il
    calcolo.
    """
    if not timezone:
        return UTC
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(timezone)
    except Exception:
        logger.warning("fuso della casa non riconosciuto (%r): finestra in UTC", timezone)
        return UTC


def local_date(ts: float, timezone: str | None) -> date:
    """Il giorno del calendario in cui cade questo istante, **nel fuso della
    casa** (UTC se non si sa, come `home_space_zone`).

    Le 00:30 del 22 agosto a Roma sono le 22:30 UTC del 21: un giorno letto in
    UTC sbaglierebbe data per due ore ogni notte (un'ora d'inverno). Prima
    della Tappa 3 questo calcolo era scritto in linea in sette punti e
    rifatto con un `ZoneInfo` costruito da se' in altri due; ora lo chiamano.
    """
    return datetime.fromtimestamp(ts, home_space_zone(timezone)).date()


def today(timezone: str | None, now: float | None = None) -> date:
    """«Oggi», nel fuso della casa. `now` (epoch) si passa nei test per
    fermare l'orologio; in produzione nessuno lo passa."""
    return local_date(time.time() if now is None else now, timezone)


def day_boundaries(day: str, timezone: str | None) -> tuple[float, float]:
    """L'inizio e la fine di un giorno **nel fuso della casa**.

    Le 23:30 di Roma sono le 21:30 UTC: un giorno calcolato in UTC spezzerebbe
    ogni serata in due, e la fetta dello schedulatore ha gia' pagato un difetto
    di orologi diversi. Il giorno del cambio d'ora dura 23 o 25 ore, e qui lo
    fa davvero: `start + timedelta(days=1)` somma in ora locale.

    **La finestra e' semi-aperta (`[from_ts, to_ts)`)**, e chi la usa ci conta
    sopra: un `-1` "per stare sicuri" riaprirebbe un buco di un secondo a ogni
    mezzanotte, e con due confini inclusivi un cambio a mezzanotte finirebbe
    contato in due giorni.

    **Spostata qui il 30/09/2026 da `mind/facts.py`**: la storia («oggi»,
    «ieri», spec `2026-09-30-la-storia.md` §2) la usa in `home_space/`, e
    `home_space` non importa da `mind`. Un calcolo solo, in un posto solo.
    """
    zone = home_space_zone(timezone)
    start = datetime.fromisoformat(day).replace(tzinfo=zone)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def _moment(raw) -> datetime | None:
    """Un ISO-8601 col fuso -> `datetime` consapevole del fuso. `None` se non
    si legge o se il fuso manca. La lettura vera, una volta sola: la chiamano
    `instant_epoch` e `instant_out`."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        moment = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return None if moment.tzinfo is None else moment


def instant_epoch(raw) -> float | None:
    """Un ISO-8601 col fuso -> epoch. `None` se non si legge o se il fuso manca.

    Un istante SENZA fuso viene rifiutato invece di essere letto come locale:
    «alle 17» di quale fuso? E' la stessa regola dell'unita' di misura
    applicata al tempo -- l'UNICA lettura di un istante nel prodotto: la usa
    la storia per cio' che arriva da Home Assistant (`house_history`), la
    usa `home_space/tools.py` (`_promise`) per l'istante che arriva dalla
    chat, e dal 05/10/2026 (Tappa 4, A-26) anche l'eta' di un cambio in
    `search` (`house_query._age_s`) e l'importazione dei consumi
    (`usage/store.py`), che prima leggevano per conto loro con
    `datetime.fromisoformat`. Lo sorveglia `tests/test_l_istante.py`.
    Questo modulo e' leggero e non importa quasi niente, quindi resta qui e
    gli altri la importano -- mai il contrario.
    """
    moment = _moment(raw)
    return None if moment is None else moment.timestamp()


def instant_out(raw, zone) -> str | None:
    """Un istante nella forma che HIRIS manda fuori (decisione D3 del
    proprietario, 05/10/2026): ISO 8601 **con l'offset della casa**, per
    esempio `2026-10-04T08:15:00+02:00`.

    - `raw` puo' essere un epoch (il registro di Home Assistant, i nostri
      archivi) o un ISO col fuso (lo storico, le tracce, lo specchio, che Home
      Assistant manda in UTC): escono uguali, perche' sono lo stesso istante.
    - `None` esce `None`, cioe' `null`: «so che non c'e'» -- per esempio
      un'automazione mai eseguita. «Non lo so» si dice togliendo la chiave,
      e lo decide chi compone la risposta, non questa funzione.
    - Cio' che non si legge (un testo senza fuso, un booleano) esce com'e',
      come testo: meglio un formato inatteso che un istante inventato. E' la
      regola che la storia aveva gia' (`house_history._local`, 24/08/2026),
      e che qui diventa di tutti.

    `zone` e' il fuso della casa come lo costruisce `home_space_zone` --
    MAI il fuso del processo: il container dell'add-on ha `TZ` impostato
    dal Supervisor, ma un test, un attrezzo o una macchina di sviluppo no,
    e l'ora che il modello legge non deve dipendere da dove gira il codice.

    Prima di qui la stessa conversione era scritta in tre posti:
    `house_history._local`, `appointments._in_home_zone` e, senza
    conversione, le righe di `search`, che mandavano l'UTC grezzo dello
    specchio (C-32).
    """
    if raw is None:
        return None
    # Al secondo (A15, 05/10/2026): i microsecondi che lo specchio porta non
    # servono a chi legge. `timespec` tronca, non arrotonda.
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return datetime.fromtimestamp(raw, tz=zone).isoformat(timespec="seconds")
    moment = _moment(raw)
    if moment is None:
        return str(raw)
    return moment.astimezone(zone).isoformat(timespec="seconds")
