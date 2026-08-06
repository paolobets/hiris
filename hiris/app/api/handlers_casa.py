"""La vista HTTP dell'anagrafe, in sola lettura.

Esiste perche' in questo progetto una cosa si dichiara funzionante solo dopo
averla vista girare: la suite verde non e' una prova. Senza una vista, nessuno
puo' guardare l'anagrafe su un Home Assistant vero.

Nota per chi legge il censimento: il percorso non compare qui per esteso di
proposito. Lo strumento (`scripts/censimento.py`) spoglia solo i commenti `#`,
non le docstring -- e la sua stessa registrazione (`app.router.add_get(...)`)
viene rimossa dal corpus perche' e' autocitazione. Se la docstring ripetesse
il percorso, la rotta risulterebbe "citata fuori dai test" per colpa delle
proprie parole e sparirebbe dal censimento invece di comparire come solo-test.
"""
from __future__ import annotations

from aiohttp import web

from ..casa.anagrafe import gerarchia


async def handle_get_casa(request: web.Request) -> web.Response:
    archivio = request.app.get("archivio_casa")
    if archivio is None:
        # L'anagrafe puo' non esserci: Home Assistant poteva non essere pronto
        # all'avvio. Vuota e 200, non 500 -- chi guarda deve poter distinguere
        # «non c'e' ancora niente» da «e' rotto».
        return web.json_response({
            "aggiornata_il": None, "non_disponibili": [], "conteggi": {}, "piani": [],
        })
    casa = archivio.leggi()
    non_disponibili = archivio.non_disponibili()
    return web.json_response({
        "aggiornata_il": archivio.aggiornata_il(),
        # I registri che non hanno risposto all'ultima lettura. Senza questo
        # campo una casa senza piani e un registro dei piani caduto sarebbero
        # la stessa schermata.
        "non_disponibili": non_disponibili,
        "conteggi": {chiave: len(valore) for chiave, valore in casa.items()},
        "piani": gerarchia(casa, non_disponibili),
    })
