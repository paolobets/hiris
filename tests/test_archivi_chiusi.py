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

RADICE = pathlib.Path(__file__).resolve().parents[1]
_SERVER = RADICE / "hiris" / "app" / "server.py"


def archivi_aperti() -> dict[str, str]:
    """`{«nome in app», «classe»}` per ogni archivio che il server costruisce."""
    albero = ast.parse(_SERVER.read_text(encoding="utf-8"))
    trovati = {}
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
    return trovati


def _corpo_pulizia() -> str:
    sorgente = _SERVER.read_text(encoding="utf-8")
    albero = ast.parse(sorgente)
    pulizia = next(n for n in ast.walk(albero)
                   if isinstance(n, ast.AsyncFunctionDef) and n.name == "_on_cleanup")
    return ast.get_source_segment(sorgente, pulizia) or ""


def test_la_derivazione_trova_davvero_qualcosa():
    """Un cancello che deriva male sembra vivo mentre non guarda piu' niente:
    e' il modo in cui una difesa si spegne senza dirlo.

    Mutazione ESEGUITA: cambiato il suffisso cercato in «Archivio» -- rossa."""
    aperti = archivi_aperti()

    assert len(aperti) >= 4, (
        f"ne ho derivati solo {len(aperti)}: {sorted(aperti)}. La derivazione "
        "si è rotta, e un cancello che deriva male passa senza guardare")


def test_ogni_archivio_aperto_viene_anche_CHIUSO():
    """**Il cancello.**

    Il file resta bloccato e il difetto compare al riavvio successivo, cioè
    lontano da chi ha scritto la riga. Qui non può succedere: l'archivio
    compare da solo nell'insieme derivato, e finché `_on_cleanup` non lo
    nomina questo file è rosso.

    Mutazione ESEGUITA: tolta la chiusura di `agenda` da `_on_cleanup` --
    rossa, col nome dell'archivio nel messaggio. E alla prima scrittura questa
    prova era rossa su `usage` e `servizi`, che è la ragione per cui esiste.
    """
    pulizia = _corpo_pulizia()

    scordati = [nome for nome in archivi_aperti()
                if f'app["{nome}"].close()' not in pulizia]

    assert not scordati, (
        f"archivi aperti e mai chiusi: {sorted(scordati)}. Il file sqlite "
        "resta bloccato e il difetto compare al riavvio successivo — aggiungi "
        "la chiusura a `_on_cleanup`, guardata sulla presenza della chiave "
        "come le altre")


def test_la_chiusura_e_GUARDATA_sulla_presenza():
    """`_on_cleanup` gira anche quando l'avvio si è fermato a metà — un archivio
    che non c'è farebbe cadere la pulizia, e con lei le chiusure che seguono.

    Mutazione ESEGUITA: tolto l'`if` da una delle chiusure -- rossa."""
    pulizia = _corpo_pulizia()

    scoperti = [nome for nome in archivi_aperti()
                if f'if "{nome}" in app:' not in pulizia
                and f'if app.get("{nome}") is not None:' not in pulizia]

    assert not scoperti, (
        f"chiusure non guardate: {sorted(scoperti)}. Se l'avvio si ferma "
        "prima di quell'archivio, la pulizia cade lì e non chiude più niente "
        "di ciò che viene dopo")
