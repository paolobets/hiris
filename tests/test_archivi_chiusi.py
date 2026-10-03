"""Ogni archivio che l'app apre, l'app lo CHIUDE (cancello derivato, 22/09/2026).

Un archivio SQLite lasciato aperto non si rompe subito: il file resta bloccato,
e il difetto compare **al riavvio successivo** -- che su un add-on di Home
Assistant succede ogni aggiornamento, e lontano da chi ha scritto la riga.

Fino a oggi la disciplina c'era ma era **scritta a mano**: `_on_cleanup`
elencava gli archivi uno per uno, e accanto a ognuno c'era un test che ne
nominava uno. Un elenco scritto a mano e' silenziosamente incompleto per
costruzione -- e infatti lo era: alla scrittura di questo cancello mancavano
**due** archivi, `usage` (da mesi) e `servizi` (dallo stesso giorno). Nessuno
dei test accanto poteva accorgersene, perche' ognuno guardava soltanto cio' che
il suo autore si era ricordato di nominare.

**L'elenco si chiede al codice** (I-0). Un archivio nuovo compare qui il giorno
in cui nasce, non il giorno in cui qualcuno si ricorda di aggiungerlo.

**Cosa questo cancello NON copre, dichiarato.** Vede le costruzioni della forma
`app["nome"] = QualcosaStore(...)`. Un contenitore aperto da una funzione di
fabbrica (`app["journal"] = apri_cronaca(...)`) non si distingue staticamente da
una qualunque altra chiamata: quelli hanno le prove accanto, scritte a mano, e
questo cancello non finge di sostituirle. Il criterio resta quello piu' stretto
che si possa verificare senza indovinare.
"""
import ast
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

RADICE = pathlib.Path(__file__).resolve().parents[1]
_APP = RADICE / "hiris" / "app"


def archivi_aperti() -> dict[str, str]:
    """`{«nome in app», «classe»}` per ogni archivio che il PRODOTTO costruisce.

    Si guarda tutto `hiris/app`, non il solo `server.py` (Tappa 1 dello
    sprint «Una fonte sola di verita'»): quando il cablaggio esce da
    `server.py`, un cancello che guarda un file solo si restringe e resta
    verde. Mutazione ESEGUITA (03/10/2026): `app["prova"] = ProvaStore(...)`
    scritto in un modulo di `api/` -- rossa (prima restava verde)."""
    trovati = {}
    for percorso in sorted(_APP.rglob("*.py")):
        _archivi_in(ast.parse(percorso.read_text(encoding="utf-8")), trovati)
    return trovati


def _archivi_in(albero: ast.AST, trovati: dict[str, str]) -> None:
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.Assign) or not isinstance(nodo.value, ast.Call):
            continue
        chiamata = nodo.value.func
        classe = (chiamata.attr if isinstance(chiamata, ast.Attribute)
                  else chiamata.id if isinstance(chiamata, ast.Name) else "")
        if not classe.endswith("Store"):
            continue
        for bersaglio in nodo.targets:
            if (isinstance(bersaglio, ast.Subscript)
                    and isinstance(bersaglio.value, ast.Name)
                    and bersaglio.value.id == "app"
                    and isinstance(bersaglio.slice, ast.Constant)):
                trovati[bersaglio.slice.value] = classe


def test_la_derivazione_trova_davvero_qualcosa():
    """Un cancello che deriva male sembra vivo mentre non guarda piu' niente:
    e' il modo in cui una difesa si spegne senza dirlo.

    Mutazione ESEGUITA: cambiato il suffisso cercato in «Archivio» -- rossa."""
    aperti = archivi_aperti()

    assert len(aperti) >= 4, (
        f"ne ho derivati solo {len(aperti)}: {sorted(aperti)}. La derivazione "
        "si è rotta, e un cancello che deriva male passa senza guardare")


@pytest.mark.asyncio
async def test_ogni_archivio_aperto_viene_anche_CHIUSO(tmp_path):
    """**Il cancello.**

    Il file resta bloccato e il difetto compare al riavvio successivo, cioè
    lontano da chi ha scritto la riga. Qui non può succedere: l'archivio
    compare da solo nell'insieme derivato, e finché lo spegnimento non lo
    chiude questo file è rosso.

    Fino al 03/10/2026 si cercava `app["nome"].close()` nel testo di
    `_on_cleanup`; adesso l'app si avvia davvero (`tests/_avvio.py`), ogni
    archivio derivato viene avvolto da una spia sul suo `close`, e dopo lo
    spegnimento si guarda chi e' stato chiuso. Una chiusura spostata in un
    altro modulo resta vista; una scritta in un ramo mai preso, no.

    Mutazione ESEGUITA (03/10/2026): tolta la chiusura di `agenda` da
    `_on_cleanup` -- rossa, col nome dell'archivio nel messaggio. E alla prima
    scrittura (22/09) questa prova era rossa su `usage` e `servizi`, che è la
    ragione per cui esiste.
    """
    import contextlib
    from unittest import mock

    from tests._avvio import started_with

    chiusi: list[str] = []

    def _spy(nome, close):
        def spia(*args, **kwargs):
            chiusi.append(nome)
            return close(*args, **kwargs)
        return spia

    with contextlib.ExitStack() as stack:
        async with started_with(tmp_path) as app:
            assenti = [nome for nome in archivi_aperti() if app.get(nome) is None]
            assert not assenti, (
                f"archivi derivati che l'avvio non ha aperto: {sorted(assenti)} -- "
                "la prova non saprebbe dire se si chiudono")
            for nome in archivi_aperti():
                stack.enter_context(mock.patch.object(
                    app[nome], "close", _spy(nome, app[nome].close)))

    scordati = [nome for nome in archivi_aperti() if nome not in chiusi]
    assert not scordati, (
        f"archivi aperti e mai chiusi: {sorted(scordati)}. Il file sqlite "
        "resta bloccato e il difetto compare al riavvio successivo — aggiungi "
        "la chiusura a `_on_cleanup`, guardata sulla presenza della chiave "
        "come le altre")


@pytest.mark.asyncio
async def test_la_chiusura_e_GUARDATA_sulla_presenza():
    """`_on_cleanup` gira anche quando l'avvio si è fermato a metà — un archivio
    che non c'è farebbe cadere la pulizia, e con lei le chiusure che seguono.

    Fino al 03/10/2026 si cercava `if "nome" in app:` nel testo; adesso si
    CHIAMA lo spegnimento vero (`server._on_cleanup`) su un'app a cui manca
    un archivio alla volta. Lo spegnimento non deve cadere, e deve chiudere
    tutti gli altri. (Il sapere puo' anche esserci e valere `None`: quel
    caso ha la sua guardia, `app.get(...) is not None`, e la sua prova in
    `test_mind_judgments.py` -- la forma vecchia accettava l'una o l'altra
    guardia, e cosi' questa.)

    Mutazione ESEGUITA (03/10/2026): `if "usage" in app:` -> `if True:` in
    `_on_cleanup` -- rossa (`KeyError: 'usage'`)."""
    from unittest.mock import MagicMock

    from hiris.app import server

    nomi = sorted(archivi_aperti())
    for mancante in nomi:
        presenti = {nome: MagicMock() for nome in nomi if nome != mancante}
        await server._on_cleanup({**presenti, "ha_client": CasaFinta({})})
        aperti = [nome for nome, archivio in presenti.items()
                  if not archivio.close.called]
        assert not aperti, (
            f"senza `{mancante}` lo spegnimento non ha chiuso {aperti}: la "
            "pulizia e' caduta prima")
