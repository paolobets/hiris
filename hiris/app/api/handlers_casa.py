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
        # Difesa, non stato atteso: in produzione questo ramo non dovrebbe mai
        # scattare. Se `_on_startup` fallisce, l'add-on non parte affatto; un
        # Home Assistant non ancora pronto all'avvio produce un archivio
        # VUOTO (create_app() lo istanzia comunque), non assente. Resta qui
        # come rete di sicurezza per un futuro in cui l'ordine di avvio
        # cambiasse -- una difesa che non scatta e' giusta, non va tolta.
        #
        # `non_disponibili: None`, non `[]`: `[]` afferma "tutti i registri
        # ok", e qui non lo sappiamo -- non abbiamo nemmeno letto niente.
        return web.json_response({
            # Nome proprio, non "aggiornata_il" generico: tre sezioni di
            # questa risposta hanno ciascuna la propria data (anagrafe,
            # comportamento, plance) e un unico campo di primo livello senza
            # nome che dica di cosa parla prometterebbe una freschezza che
            # vale solo per una delle tre.
            "anagrafe_letta_il": None, "non_disponibili": None, "conteggi": {}, "piani": [],
            # Stesso principio di "non_disponibili" qui sopra, applicato al
            # comportamento: `senza_corpo: 0` affermerebbe "conosco tutto",
            # e senza archivio non lo sappiamo -- resta `None`. `conteggi` e
            # `voci`, come `conteggi`/`piani` sopra, sono contenitori naturali
            # e restano vuoti. `problemi`/`file_non_letti` restano `None` per
            # lo stesso motivo di `senza_corpo`: un elenco vuoto affermerebbe
            # "nessun problema", e senza archivio non lo sappiamo.
            "comportamento": {"letto_il": None, "conteggi": {}, "senza_corpo": None,
                              "problemi": None, "file_non_letti": None, "voci": []},
            "plance": {"lette_il": None, "non_disponibili": None, "voci": []},
        })
    casa = archivio.leggi()
    non_disponibili = archivio.non_disponibili()
    voci_comportamento = archivio.comportamento()
    conteggi_comportamento: dict[str, int] = {}
    for v in voci_comportamento:
        conteggi_comportamento[v["tipo"]] = conteggi_comportamento.get(v["tipo"], 0) + 1
    return web.json_response({
        "anagrafe_letta_il": archivio.aggiornata_il(),
        # I registri che non hanno risposto all'ultima lettura. Senza questo
        # campo una casa senza piani e un registro dei piani caduto sarebbero
        # la stessa schermata.
        "non_disponibili": non_disponibili,
        "conteggi": {chiave: len(valore) for chiave, valore in casa.items()},
        "piani": gerarchia(casa, non_disponibili),
        "comportamento": {
            "letto_il": archivio.comportamento_letto_il(),
            "conteggi": conteggi_comportamento,
            # Il campo che conta di piu': quante voci HIRIS conosce solo di
            # nome. Le automazioni scritte a mano non stanno nei file, e di
            # quelle sa il nome e non il corpo -- e' la misura onesta di
            # quanto sa davvero della casa. `corpo is None` e non falsy:
            # un corpo vuoto (`{}`, presente ma senza niente dentro) e' un
            # fatto diverso da un corpo assente, e non va confuso con esso.
            "senza_corpo": sum(1 for v in voci_comportamento if v["corpo"] is None),
            # Cio' che l'ultima lettura NON ha potuto concludere con
            # certezza (id duplicati, script vuoti, voci malformate) e i
            # file che non si sono letti, con la ragione. Costruiti con
            # cura da comportamento.componi()/rileggi() -- prima morivano in
            # una riga di log, invisibili a chi guarda solo /api/casa.
            "problemi": archivio.problemi_comportamento(),
            "file_non_letti": archivio.file_non_letti(),
            "voci": voci_comportamento,
        },
        "plance": {
            "lette_il": archivio.plance_lette_il(),
            # Le plance/percorsi che l'ultima lettura non e' riuscita a
            # risolvere -- stesso principio di "non_disponibili" sopra,
            # applicato alle plance invece che ai registri.
            "non_disponibili": archivio.non_disponibili_plance(),
            "voci": archivio.plance(),
        },
    })
