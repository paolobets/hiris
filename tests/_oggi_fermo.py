"""«Oggi» fermo per la durata di una prova.

Le prove dei giri scrivono l'analisi sotto il giorno di oggi e il giro la cerca
con `historian.today`: se ognuno legge l'orologio da se', a cavallo della
mezzanotte (UTC, il fuso di una casa senza fuso) la prova scrive ieri e il giro
cerca oggi. Calcolato al caricamento del modulo, il giorno della prova poteva
essere vecchio di tutta la raccolta: riprodotto il 14/10/2026 con la raccolta
alle 01:59 di Roma e le prove 90 secondi dopo, 26 prove rosse in tre file.

`ferma_oggi` legge l'orologio UNA volta e da' quell'istante a tutti e due: a
`historian.today` (per chi non passa `now`) e ai moduli delle prove, che
ricevono il loro `OGGI`: anche a quello da cui una prova prende in prestito le
fixture, che leggono il proprio.
"""
from __future__ import annotations

import sys
import time

from hiris.app.home_space import historian


def ferma_oggi(monkeypatch, *moduli: str) -> str:
    adesso = time.time()
    vero = historian.today
    monkeypatch.setattr(historian, "today",
                        lambda timezone, now=None: vero(timezone, adesso if now is None else now))
    oggi = vero(historian.house_timezone(None), adesso).isoformat()
    for modulo in moduli:
        monkeypatch.setattr(sys.modules[modulo], "OGGI", oggi)
    return oggi
