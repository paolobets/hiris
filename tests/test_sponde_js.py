"""Il cancello sulle sponde fra file, e la prova che sa arrossire.

**Un cancello verde non dimostra niente finche' non gli si mostra il difetto
che deve trovare.** Tre dei quattro casi qui sotto sono mutazioni: si rompe
l'albero apposta, in una copia, e si controlla che il cancello dica di no. La
regola e' quella della fetta: una rete senza caso e' una speranza.

Cosa questo cancello copre, e perche' non basta `no-undef` (in `.oxlintrc.json`):
`hiris/app/static/` non ha moduli, quindi per restare verde il linter deve
sapere che `HirisRouter` e `fmtNum` esistono -- e quella dichiarazione e' cio'
che lo acceca quando qualcuno ne rinomina il produttore. Misurato: rinominato
`window.HirisRouter` da un lato solo, oxlint tace col cancello come senza.
Questo script guarda i file INSIEME, ed e' l'unica cosa che vede quel caso.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sponde_js


@pytest.fixture
def albero(tmp_path, monkeypatch):
    """Una copia dell'albero vero su cui mutare senza toccare il repo."""
    static = tmp_path / "static"
    static.mkdir()
    for f in sorted((ROOT / "hiris" / "app" / "static").rglob("*")):
        if f.is_dir():
            continue
        dest = static / f.relative_to(ROOT / "hiris" / "app" / "static")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f.read_bytes())
    config = tmp_path / ".oxlintrc.json"
    config.write_bytes((ROOT / ".oxlintrc.json").read_bytes())
    monkeypatch.setattr(sponde_js, "STATIC", static)
    monkeypatch.setattr(sponde_js, "CONFIG", config)
    return static


def test_l_albero_vero_e_verde(albero):
    assert sponde_js.main() == 0


def test_un_produttore_rinominato_da_un_lato_solo_arrossisce(albero):
    """La specie che `no-undef` non puo' vedere: `window.HirisRouter` cambia
    nome, `config/main.js` continua a leggerlo col nome vecchio."""
    f = albero / "config" / "router.js"
    testo = f.read_text(encoding="utf-8")
    assert "window.HirisRouter =" in testo
    f.write_text(testo.replace("window.HirisRouter =", "window.HirisInstradatore =", 1),
                 encoding="utf-8")
    assert sponde_js.main() == 1


def test_una_funzione_nuda_rinominata_da_un_lato_solo_arrossisce(albero):
    """`config/api.js` dichiara `fmtNum` senza `window`, e tre file la
    chiamano. Rinominare la sola `function` lascia tre chiamate orfane."""
    f = albero / "config" / "api.js"
    testo = f.read_text(encoding="utf-8")
    assert "function fmtNum(" in testo
    f.write_text(testo.replace("function fmtNum(", "function fmtNumero(", 1),
                 encoding="utf-8")
    assert sponde_js.main() == 1


def test_l_ordine_dei_tag_script_e_una_dipendenza_e_si_verifica(albero):
    """L'unica dichiarazione di dipendenza che questo frontend possiede e'
    l'ordine dei `<script src>`, e prima di questo cancello non la leggeva
    nessuno: spostare `api.js` dopo chi lo usa non rompeva nessun controllo."""
    html = albero / "config.html"
    testo = html.read_text(encoding="utf-8")
    riga = '  <script src="static/config/api.js"></script>\n'
    assert riga in testo
    testo = testo.replace(riga, "", 1)
    testo = testo.replace('  <script src="static/config/main.js"></script>',
                          riga + '  <script src="static/config/main.js"></script>', 1)
    html.write_text(testo, encoding="utf-8")
    assert sponde_js.main() == 1


def test_i_due_globali_privati_di_api_js_non_sono_dichiarati():
    """`_setUsageText` e `_mostraRigheConsumi` sono globali per accidente --
    script classico, nessun modulo -- ma nessun altro file le legge.

    Dichiararle in `globals` sarebbe un BUCO: il giorno in cui qualcuno
    rinominasse la loro `function` lasciando indietro la chiamata, `no-undef`
    tacerebbe perche' gliel'avremmo detto noi che quel nome esiste. Questo
    test esiste perche' aggiungerle sembra prudenza ed e' una rinuncia."""
    globali = set(sponde_js.leggi_config(ROOT / ".oxlintrc.json")["globals"])
    assert "_setUsageText" not in globali
    assert "_mostraRigheConsumi" not in globali
    assert {"fmtNum", "HirisRouter"} <= globali
    assert len(globali) == 25


def test_la_suite_js_esce_anche_quando_un_cronometro_resta_appeso():
    """`--test-force-exit`, e NON `--test-timeout`.

    Misurato: rinominata da un lato sola una proprieta' che tiene un
    `setInterval` (`intervallo`, `isLoading`, `fermaTutteLeAttese`), le
    asserzioni falliscono subito ma il processo non esce -- il cronometro
    orfano tiene vivo il ciclo di eventi DOPO la fine dei test. Con
    `--test-timeout=20000` la corsa restava appesa oltre 400 s: il limite per
    test non c'entra, perche' l'attesa non e' dentro un test. Con
    `--test-force-exit` le stesse tre mutazioni escono 1 in 34 s."""
    script = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]["test"]
    assert "--test-force-exit" in script, script
