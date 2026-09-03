"""Le classi CSS: che il nome scritto nel JS esista nel foglio, e che sia inglese.

**Il difetto che questi due test chiudono non fa arrossire nient'altro, e non
cambia il comportamento.** Una classe rinominata da un lato solo non solleva
niente: la regola semplicemente non si applica, la pagina continua a
funzionare, e diventa sbagliata *a vedersi*. jsdom non calcola il layout e
nessun test di comportamento puo' accorgersene -- e' il «fallimento muto» nella
sua forma piu' silenziosa.

`test_model_invariants.py` (Task 15) chiudeva la meta' di questo buco per la
sola pagina Modelli. La fetta delle classi CSS (03/09) ha rinominato
sessantotto nomi su quattro fogli, otto file JS e due `.html`: il cancello ha
seguito il perimetro, e quello vecchio e' uscito perche' questo lo contiene.

**La memoria che viene da li', e che non si perde** (G3 della revisione finale
del Task 15): la prima versione leggeva solo il secondo argomento LETTERALE di
`el(`, e in quella pagina le classi che contano non si scrivono cosi' -- sono
composte con un ternario (`'row-provider' + (dentro ? '' : ' row-outside')`) o
passate come variabile a un involucro (`connettore('connector-note', ...)`).
Erano invisibili al test che prometteva di coprirle: cancellando cinque regole
dal foglio -- `.row-muted`, `.status-rejected`, `.model-alias`, `.entry-alias`,
`.row-outside` -- restavano trentaquattro test verdi. Il criterio e' percio' la
FORMA del nome, non la posizione.
"""
import re
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
STATIC = RADICE / "hiris" / "app" / "static"

# Le due pagine, e per ognuna il guscio da cui si leggono i suoi fogli. I file
# non si elencano a mano: si prendono dalla cartella, cosi' una route nuova
# entra nel cancello il giorno in cui nasce invece del giorno in cui qualcuno
# si ricorda di aggiungerla qui.
_SHELLS = {"config": "config.html", "chat": "index.html"}


def _live_css(testo: str) -> str:
    """I fogli di questo ramo CITANO i nomi delle classi per spiegare le
    regole, e una citazione non veste niente: senza questo taglio una classe
    la cui unica traccia e' la spiegazione di una regola cancellata passerebbe
    per vestita."""
    return re.sub(r"/\*.*?\*/", "", testo, flags=re.DOTALL)


def _live_js(testo: str) -> str:
    """Il sorgente senza commenti. I commenti di questo ramo citano le parole
    RITIRATE per spiegare perche' sono uscite: leggerle renderebbe il test
    impossibile da soddisfare senza cancellare la memoria del difetto."""
    testo = re.sub(r"/\*.*?\*/", "", testo, flags=re.DOTALL)
    return "\n".join(r for r in testo.splitlines() if not r.lstrip().startswith("//"))


def _sheets(guscio: str) -> str:
    """I fogli che quel guscio carica DAVVERO, letti da li' e non elencati a
    mano: un foglio aggiunto alla pagina e non a questa lista renderebbe il
    cancello cieco proprio sul codice nuovo."""
    html = (STATIC / guscio).read_text(encoding="utf-8")
    nomi = re.findall(r'href="(?:static/)?([\w.-]+\.css)"', html)
    assert nomi, f"{guscio} non carica nessun foglio di stile: forma cambiata"
    fuori = [n for n in nomi if not (STATIC / n).exists()]
    assert not fuori, f"{guscio} carica fogli che non esistono: {fuori}"
    return _live_css(
        "\n".join((STATIC / n).read_text(encoding="utf-8") for n in nomi))


def _sources(cartella: str) -> list[Path]:
    return sorted((STATIC / cartella).glob("*.js"))


def _dom_ids() -> set[str]:
    """Gli id che il frontend nomina, raccolti da TUTTO il frontend.

    Servono a essere SOTTRATTI: un id e un nome di classe hanno la stessa forma
    -- `route-outlet`, `chain-body`, `usage-7`, `send-btn` -- e nessuna regola
    sintattica li distingue dentro un letterale. Misurato il 03/09: senza
    questa sottrazione il criterio della forma produce **51 falsi orfani su
    195 candidate** (il 26%), e sarebbe nato spento o con un elenco di
    eccezioni piu' lungo di cio' che misura. Con la sottrazione ne restano 6, e
    sono dichiarati qui sotto uno per uno.

    Un id si raccoglie DOVE NASCE E DOVE SI LEGGE, in tutti e due i posti,
    perche' un id composto a runtime (`buildSectionShell('01', 'chain', ...)`
    scrive `chain-card` senza che il letterale esista) si vede solo dal lato
    che lo legge."""
    ids: set[str] = set()
    for guscio in _SHELLS.values():
        ids |= set(re.findall(r'id="([\w-]+)"', (STATIC / guscio).read_text(encoding="utf-8")))
    for cartella in _SHELLS:
        for p in _sources(cartella):
            js = _live_js(p.read_text(encoding="utf-8"))
            for pat in (r"getElementById\(\s*'([^']+)'",
                        r"byId\(\s*'([^']+)'",
                        r"\.id\s*=\s*'([^']+)'",
                        r"querySelector(?:All)?\(\s*'#([\w-]+)",
                        r'id="([\w-]+)"'):
                ids |= set(re.findall(pat, js))
    return ids


# Le chiavi che il frontend salva nel browser hanno anch'esse la forma di una
# classe, e sono UNA: si toglie con una regola (dove si scrive), non con un
# nome scritto qui.
_STORAGE_KEYS = re.compile(r"(?:localStorage|sessionStorage)\.\w+\(\s*'([^']+)'")


def _written_classes(js: str) -> set[str]:
    """Ogni nome che ha la FORMA di una classe, dalle righe vive.

    Il criterio e' la forma invece della posizione: ogni letterale a singolo
    apice fatto di soli nomi in kebab-case, e da quello i pezzi che contengono
    un trattino, piu' le classi scritte dentro un frammento HTML
    (`'<div class="usage-bar">'`, la forma di `usage-route.js`). Il trattino e'
    cio' che distingue un nome di classe da un tag (`div`), da un ruolo
    (`list`, `listitem`), da un id di provider (`claude`) e da un valore
    (`polite`, `balanced`).

    **Il limite, dichiarato**: una classe di UNA parola sola passata come
    variabile resta fuori -- oggi due, `construction` e `connector`, la cui
    gemella `connector-note` e' invece coperta."""
    classi: set[str] = set()
    for letterale in re.findall(r"'([^']*)'", js):
        pezzi = letterale.split()
        if pezzi and all(re.fullmatch(r"[a-z][a-z0-9-]*", p) for p in pezzi):
            classi.update(p for p in pezzi if "-" in p)
    classi.update(re.findall(r"classList\.add\('([^']+)'\)", js))
    for attributo in re.findall(r'class="([^"\']*)', js):
        classi.update(p for p in attributo.split() if "-" in p)
    # I nomi di ATTRIBUTO (`aria-live`, `data-provider`) hanno la forma di una
    # classe e non lo sono: e' l'unica famiglia che il criterio non separa da
    # sola, e si toglie con una regola, non con un elenco.
    return {c for c in classi
            if not c.endswith("-") and not c.startswith(("aria-", "data-"))}


# I nomi che il frontend scrive e che NON hanno (ne' devono avere) una regola
# propria. La lista e' corta apposta: una lista di eccezioni che cresce e' il
# segno che questo test ha smesso di misurare qualcosa. Sono due specie sole:
#
#   * i quattro agganci sui bottoni gia' vestiti da `btn btn-ghost btn-sm` o da
#     `btn-icon-only`, che esistono per i test e per `querySelector`, non per
#     il foglio;
#   * un involucro nato senza regola, e non rimasto senza per una rinomina:
#     `usage-sections` (ex `usage-sezioni`) e' orfano fin dal commit che l'ha
#     creato (`c51f3fa3`, «la pagina -- sezioni per provider»), verificato con
#     `git log -S` sul foglio. **Toglierlo e' una decisione della pagina, non
#     di una rinomina**, ed e' scritto qui perche' si veda invece di sparire.
_INTENTIONALLY_UNSTYLED = {
    "row-use", "row-up", "row-down", "row-leave",
    "usage-sections",
}


@pytest.mark.parametrize("cartella", sorted(_SHELLS))
def test_ogni_classe_che_il_frontend_scrive_ha_una_regola_nel_foglio(cartella):
    """Il difetto che questo test coglie e' l'unico difetto di CSS che si possa
    cogliere senza un browser: il nome scritto in due posti e cambiato in uno
    solo. Non prova che il layout regga -- quello lo prova solo la casa vera,
    `docs/prova-modelli-e-catena.md` -- ma prova che il foglio e la pagina
    parlino della stessa cosa."""
    css = _sheets(_SHELLS[cartella])
    ids = _dom_ids()
    orfane: dict[str, list[str]] = {}
    sorgenti = _sources(cartella) + [STATIC / _SHELLS[cartella]]
    for p in sorgenti:
        testo = p.read_text(encoding="utf-8")
        vive = testo if p.suffix == ".html" else _live_js(testo)
        chiavi = set(_STORAGE_KEYS.findall(vive))
        for c in _written_classes(vive) - ids - chiavi - _INTENTIONALLY_UNSTYLED:
            if not re.search(r"\." + re.escape(c) + r"(?![\w-])", css):
                orfane.setdefault(c, []).append(p.name)
    assert not orfane, (
        f"la pagina «{cartella}» scrive classi che nessun suo foglio veste: "
        f"{ {k: v for k, v in sorted(orfane.items())} }. "
        f"O manca la regola, o il nome e' cambiato in un posto solo"
    )


# I due suffissi che arrivano dal backend e che una classe si porta dentro
# perche' e' COMPOSTA a runtime: `'diagnosis-' + d.gravita` e
# `'source-' + data.fonte`. Sono VALORI DI DOMINIO -- rinviati dal glossario
# con la loro ragione, e viaggiano sul filo -- quindi restano italiani finche'
# resta italiano il valore. E' la stessa legge gia' applicata a `GENRES` e a
# `SPECIE`: il contenitore prende il nome inglese, i valori no.
_DOMAIN_SUFFIXES = {"guasto", "spreco", "fatto", "riserva", "assente", "viva", "fissa"}


def test_nessun_nome_di_classe_porta_una_parola_italiana():
    """La fetta del 03/09 ha portato all'inglese sessantotto classi, e questo e'
    il cancello che le tiene li'.

    **Il limite, e va letto**: il glossario e' l'unico giudice, quindi il
    cancello vede solo le parole che il glossario ha DECISO. `inerte`,
    `compreso`, `rifiutato`, `muto` sono state tradotte in questa fetta senza
    una riga di glossario -- il verbale dice perche' -- e questo test non le
    riprenderebbe se qualcuno le rimettesse. Misurato il 03/09 su 256 classi:
    due sole hanno un pezzo che il glossario conosce, e sono i due suffissi di
    dominio qui sopra. Rumore zero, quindi il cancello si scrive."""
    import sys
    sys.path.insert(0, str(RADICE / "scripts"))
    from rinomina import leggi_glossario

    glossario = leggi_glossario()
    nomi: set[str] = set()
    for guscio in _SHELLS.values():
        for riga in _sheets(guscio).splitlines():
            testa = riga.split("{")[0]
            if "{" not in riga and not testa.rstrip().endswith(","):
                continue
            if testa.strip().startswith("@"):
                continue
            nomi |= set(re.findall(r"\.(-?[_a-zA-Z][\w-]*)", testa))

    italiane = {}
    for c in sorted(nomi):
        for pezzo in c.split("-"):
            if not pezzo or pezzo in _DOMAIN_SUFFIXES:
                continue
            inglese = glossario.per(pezzo.lower(), "static")
            if inglese:
                italiane.setdefault(c, []).append(f"{pezzo} -> {inglese}")
    assert not italiane, (
        f"nomi di classe con un pezzo italiano che il glossario ha gia' "
        f"deciso: {italiane}"
    )
