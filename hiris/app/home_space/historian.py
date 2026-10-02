"""Il tempo della casa: il fuso, i confini di un giorno e la lettura di un
istante -- le tre cose che ogni parte di HIRIS che parla di tempo deve dire
allo stesso modo.

Non archivia NIENTE. La decisione del proprietario e' esplicita -- «deve
leggere da HA sempre» -- e non e' una preferenza: HIRIS ha gia' avuto un
archivio storico suo (`history.db`), e' uscito perche' scriveva senza che
nessuno leggesse.

Qui stanno le funzioni che il resto del prodotto usa: `home_space_zone`,
`instant_epoch`, `day_boundaries`. La storia che la chat interroga (la
superficie, il campione, «per mano di HIRIS») vive in
`home_space/house_history.py`.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


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


def instant_epoch(raw) -> float | None:
    """Un ISO-8601 col fuso -> epoch. `None` se non si legge o se il fuso manca.

    Un istante SENZA fuso viene rifiutato invece di essere letto come locale:
    «alle 17» di quale fuso? E' la stessa regola dell'unita' di misura
    applicata al tempo -- l'UNICA lettura di un istante nel prodotto: la usa
    la storia per cio' che arriva da Home Assistant (`house_history`), e la
    usa `home_space/tools.py` (`_promise`) per l'istante che arriva dalla
    chat. Questo modulo e' leggero e non importa quasi niente, quindi resta
    qui e gli altri la importano -- mai il contrario.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        moment = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return None if moment.tzinfo is None else moment.timestamp()
