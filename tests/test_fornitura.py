"""Cosa entra nell'immagine, e da dove (reperti D-4 e D-5, 22/09/2026).

**D-4 · la CLI del ponte si risolveva dal PERCORSO DI RICERCA.** `argv[0]` era
`"claude"`: chi esegue il sottoprocesso lo cercava in `PATH`, e `PATH` non e'
una cosa che questo codice controlla. Adesso l'immagine fissa un percorso suo
-- un collegamento in `/usr/lib/hiris/claude`, accanto al prodotto -- e la
costruzione fallisce se quel collegamento non esiste o non esegue.

**E gli script di post-installazione sono spenti.** Un pacchetto npm puo'
eseguire codice al momento dell'installazione: durante la costruzione
dell'immagine e, nel CI, con il token del lavoro in mano. Non ne serve nessuno
(ripgrep arriva da `apk`, e `USE_BUILTIN_RIPGREP=0` lo dichiara).

**D-5 · il CI ereditava i permessi predefiniti del repository** e usava azioni
a ETICHETTA MOBILE: `actions/checkout@v7` e' un puntatore che qualcuno puo'
spostare, e il giorno in cui lo sposta il CI esegue codice diverso con lo stesso
nome. Adesso i permessi sono di sola lettura e ogni azione e' fissata per
impronta.
"""
import pathlib
import re

RADICE = pathlib.Path(__file__).resolve().parents[1]
DOCKERFILE = (RADICE / "hiris" / "Dockerfile").read_text(encoding="utf-8")
CI = (RADICE / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")


# --- D-4 · la fornitura dell'immagine ---------------------------------------

def test_npm_non_esegue_script_di_POST_INSTALLAZIONE():
    """Un pacchetto puo' eseguire codice mentre si installa. Qui non ne serve
    nessuno, e il costo di vietarlo e' zero.

    Mutazione ESEGUITA: tolto `--ignore-scripts` -- rossa."""
    # I COMMENTI non si contano: uno di loro spiega come si aggiorna il pin,
    # e nominare `npm install -g` li dentro non installa niente.
    installazioni = [r for r in DOCKERFILE.splitlines()
                     if "npm install" in r and not r.lstrip().startswith("#")]

    assert installazioni, "nessuna `npm install` nel Dockerfile: forma cambiata?"
    for riga in installazioni:
        assert "--ignore-scripts" in riga, f"esegue gli script: {riga.strip()}"


def test_la_CLI_del_ponte_ha_un_percorso_FISSO_nell_immagine():
    """Non piu' `PATH`: un collegamento in una cartella nostra, e la
    costruzione che lo verifica.

    **Si guarda il gesto che lo CREA, non il nome che compare**: togliendo la
    riga del collegamento, la stringa restava comunque nel Dockerfile -- la
    usa la verifica sotto -- e questa prova passava verde su un'immagine senza
    collegamento. Misurato con la mutazione, non supposto.

    Mutazione ESEGUITA: tolta la riga `ln -sf` -- rossa (prima era verde)."""
    assert re.search(r"ln -s\w*\s+.+\s+/usr/lib/hiris/claude", DOCKERFILE), (
        "nessuna riga crea il collegamento: la CLI tornerebbe a risolversi "
        "dal percorso di ricerca")


def test_e_la_COSTRUZIONE_fallisce_se_quella_CLI_non_esegue():
    """**La riga che vale piu' di tutte in questo file.** Spegnere gli script
    di post-installazione e' una cosa che non posso provare da qui: se
    rompesse la CLI, il difetto arriverebbe a casa di qualcuno. Con questa
    verifica nella STESSA istruzione, a rompersi e' la costruzione
    dell'immagine -- e non esce niente.

    Mutazione ESEGUITA: tolto `--version` dalla costruzione -- rossa."""
    assert re.search(r"/usr/lib/hiris/claude\s+--version", DOCKERFILE), (
        "la costruzione non prova la CLI che ha appena installato")


def test_la_CLI_si_invoca_da_QUEL_percorso():
    """La meta' che il Dockerfile non puo' garantire da solo: chi costruisce
    l'argv deve usarlo davvero.

    Mutazione ESEGUITA: rimesso `"claude"` nudo -- rossa."""
    runner = (RADICE / "hiris" / "app" / "agent" / "runner.py").read_text(encoding="utf-8")

    assert "/usr/lib/hiris/claude" in runner
    assert 'argv = ["claude"' not in runner, (
        "l'argv torna a cercare la CLI nel percorso di ricerca")


# --- D-5 · il CI -------------------------------------------------------------

def test_il_CI_dichiara_permessi_di_SOLA_LETTURA():
    """Senza, il token del lavoro eredita il default del repository e ogni
    azione di terze parti che gira qui dentro lo riceve. Nessun lavoro di
    questo file ha bisogno di scrivere.

    Mutazione ESEGUITA: tolto il blocco -- rossa."""
    import yaml

    dichiarato = yaml.safe_load(CI)

    assert dichiarato.get("permissions") == {"contents": "read"}


def test_ogni_azione_e_fissata_per_IMPRONTA_non_per_etichetta():
    """Un'etichetta e' un puntatore che qualcuno puo' spostare: il giorno in
    cui lo sposta, il CI esegue codice diverso con lo stesso nome e nessuno se
    ne accorge.

    **L'elenco si deriva dal file**, non si ricopia: un'azione aggiunta domani
    entra in questo cancello il giorno in cui nasce.

    Mutazione ESEGUITA: rimesso `actions/checkout@v7` -- rossa, col nome."""
    usate = re.findall(r"uses:\s*(\S+)", CI)

    assert usate, "nessuna azione trovata: la forma del file e' cambiata?"
    mobili = [u for u in usate if not re.search(r"@[0-9a-f]{40}$", u)]
    assert not mobili, (
        f"azioni a etichetta mobile: {mobili}. Fissale per impronta, con "
        "l'etichetta nel commento accanto perche' resti leggibile")


def test_la_scansione_delle_CVE_gira_anche_a_CALENDARIO():
    """Una misura fatta una volta invecchia in silenzio: il mondo delle
    vulnerabilita' cambia senza che noi tocchiamo una riga, e un avviso nuovo
    su una dipendenza ferma deve trovare qualcuno che glielo chiede.

    Mutazione ESEGUITA: tolto `schedule` -- rossa."""
    import yaml

    dichiarato = yaml.safe_load(CI)
    quando = dichiarato[True] if True in dichiarato else dichiarato["on"]

    assert "schedule" in quando, "le CVE si guardano solo quando qualcuno spinge"
    assert "dipendenze" in dichiarato["jobs"], "non c'e' nessun lavoro che le guardi"


def test_e_guarda_TUTTI_E_DUE_gli_alberi():
    """Produzione e sviluppo: il primo gira a casa di chi usa HIRIS, il secondo
    solo qui -- e tutti e due possono portarsi dentro un avviso.

    Mutazione: guardare solo la produzione -- rossa."""
    import yaml

    lavoro = yaml.safe_load(CI)["jobs"]["dipendenze"]
    passi = str(lavoro["steps"])

    assert "requirements.txt" in passi and "requirements-dev.txt" in passi
    assert "npm audit" in passi, "l'albero JavaScript non lo guarda nessuno"
