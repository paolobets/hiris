"""La verifica dei componenti al rilascio.

Nasce da un fatto misurato: `hiris/Dockerfile` porta scritta, per esteso, la
disciplina del pin della CLI -- «la riga va guardata a ogni giro di rilascio» --
e non e' stata guardata ne' nella 3.0.0, ne' nella 3.1.0, ne' nella 3.2.0. Una
disciplina scritta non e' una disciplina eseguita: una nota si legge solo se
qualcuno va a cercarla, e al momento del rilascio nessuno ci va.

Il cuore e' PURO: riceve cio' che e' scritto nei file e cio' che i registri
hanno risposto, e restituisce gli scarti. Uno scarto si fabbrica passando due
dizionari -- ed e' per questo che queste prove possono PRODURRE il difetto
invece di descriverlo.

Spec: docs/design/2026-08-15-verifica-dei-componenti.md
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

_SORGENTE = Path(__file__).parent.parent / "scripts" / "verifica_componenti.py"
_spec = importlib.util.spec_from_file_location("verifica_componenti", _SORGENTE)
vc = importlib.util.module_from_spec(_spec)
sys.modules["verifica_componenti"] = vc
_spec.loader.exec_module(vc)


# ── Il confronto fra versioni ──────────────────────────────────────────────

@pytest.mark.parametrize("a,b,atteso", [
    ("2.1.228", "2.1.233", True),
    ("2.1.233", "2.1.228", False),
    ("2.1.233", "2.1.233", False),
    # IL caso che un confronto lessicografico sbaglia, e l'unico: "2.1.9" >
    # "2.1.10" come stringhe, ed e' falso come versioni.
    ("2.1.9", "2.1.10", True),
    ("2.1.10", "2.1.9", False),
    # Lunghezze diverse: 2.1 e' piu' vecchia di 2.1.1, non uguale.
    ("2.1", "2.1.1", True),
])
def test_le_versioni_si_confrontano_da_versioni_non_da_stringhe(a, b, atteso):
    assert vc.piu_vecchia(a, b) is atteso


# ── La funzione pura ───────────────────────────────────────────────────────

def _letti(**sovrascritture):
    base = {
        "cli": {"versione": "2.1.233", "dove": "hiris/Dockerfile"},
        "azioni": {"actions/setup-node": {"major": 7,
                                          "dove": ".github/workflows/tests.yml"}},
        "tetti": {"anthropic": {"major_escluso": 1,
                                "dove": "hiris/requirements.txt"}},
        "pavimenti": {"anthropic": {"minimo": "0.87.0", "installato": "0.122.0"}},
    }
    base.update(sovrascritture)
    return base


def _registri(**sovrascritture):
    base = {
        "cli": {"versione": "2.1.233"},
        "azioni": {"actions/setup-node": {"major": 7}},
        "pypi": {"anthropic": {"versione": "0.122.0"}},
    }
    base.update(sovrascritture)
    return base


def test_quando_e_tutto_allineato_l_elenco_e_VUOTO():
    """Un elenco che dice sempre qualcosa e' un elenco che si smette di
    leggere. E' il difetto che questa fetta chiude, e la prova che impedisce di
    reintrodurlo."""
    assert vc.componi_scarti(_letti(), _registri()) == []


def test_la_cli_indietro_viene_nominata_coi_due_numeri():
    scarti = vc.componi_scarti(
        _letti(cli={"versione": "2.1.228", "dove": "hiris/Dockerfile"}),
        _registri())
    assert len(scarti) == 1
    assert scarti[0].componente == "CLI del ponte"
    assert scarti[0].scritto == "2.1.228"
    assert scarti[0].disponibile == "2.1.233"
    assert scarti[0].dove == "hiris/Dockerfile"


def test_una_cli_PIU_NUOVA_del_registro_non_e_uno_scarto():
    """Un rilascio ritirato fa regredire il registro. «Diverso da» produrrebbe
    uno scarto falso e manderebbe a valle un downgrade."""
    assert vc.componi_scarti(
        _letti(cli={"versione": "2.1.240", "dove": "hiris/Dockerfile"}),
        _registri()) == []


def test_un_azione_indietro_di_major_viene_nominata():
    scarti = vc.componi_scarti(
        _letti(azioni={"actions/setup-node": {"major": 4, "dove": "w.yml"}}),
        _registri())
    assert len(scarti) == 1
    assert scarti[0].componente == "actions/setup-node"
    assert scarti[0].scritto == "v4"
    assert scarti[0].disponibile == "v7"


def test_un_major_sopra_il_tetto_python_e_uno_scarto():
    """Il tetto `<1.0.0` mentre PyPI passa a 1.x sta CONGELANDO la dipendenza
    in silenzio: CI resta verde, l'immagine si costruisce, e nessuno vede che
    una linea intera e' esclusa."""
    scarti = vc.componi_scarti(
        _letti(), _registri(pypi={"anthropic": {"versione": "1.4.0"}}))
    assert len(scarti) == 1
    assert "anthropic" in scarti[0].componente
    assert scarti[0].disponibile == "1.4.0"


@pytest.mark.parametrize("uscita", ["0.122.0", "0.999.3"])
def test_un_minor_o_una_patch_sopra_il_PAVIMENTO_non_sono_scarti(uscita):
    """LA PROVA CHE DIFENDE LA SPEC §2.1. Un pavimento sta per definizione
    sotto l'ultima uscita: confrontarli produrrebbe undici scarti su undici
    dipendenze, a ogni rilascio, per sempre -- cioe' l'elenco che dice sempre
    qualcosa, reintrodotto una sezione dopo averlo dichiarato inaccettabile.
    Il tetto e' `<1.0.0` e nessuna di queste uscite lo supera."""
    assert vc.componi_scarti(
        _letti(), _registri(pypi={"anthropic": {"versione": uscita}})) == []


def test_un_pacchetto_installato_sotto_il_pavimento_e_uno_scarto():
    """Il difetto misurato il 15/08/2026: `anthropic` 0.40.0 installato contro
    un pavimento `>=0.87.0`. La suite locale provava qualcosa di diverso da CI
    e dall'immagine, e il verde valeva meno di quanto sembrava."""
    scarti = vc.componi_scarti(
        _letti(pavimenti={"anthropic": {"minimo": "0.87.0",
                                        "installato": "0.40.0"}}),
        _registri())
    assert len(scarti) == 1
    assert scarti[0].scritto == "0.40.0"
    assert scarti[0].disponibile == "0.87.0"


def test_un_registro_che_non_risponde_e_uno_SCARTO_non_un_via_libera():
    """«non c'e'» e «non ho potuto guardare» sono due risposte diverse, e
    nessuna delle due e' «tutto a posto». Un controllo che passa in silenzio
    quando la rete cade e' un controllo che si disattiva staccando il cavo."""
    scarti = vc.componi_scarti(_letti(), _registri(cli={"errore": "timeout"}))
    assert len(scarti) == 1
    assert scarti[0].motivo == "timeout"
    assert scarti[0].disponibile == ""


# ── La lettura dei file VERI del repo ──────────────────────────────────────

def test_legge_la_cli_pinnata_dal_dockerfile_vero():
    """Non una finta: il file del repo. Se qualcuno cambia la forma della riga
    `npm install -g`, questo test lo dice invece di far tornare vuoto a valle
    -- che sarebbe il modo in cui questo strumento diventa inutile senza
    rompersi."""
    letti = vc.leggi_i_file()
    assert re.match(r"^\d+\.\d+\.\d+$", letti["cli"]["versione"]), letti["cli"]
    assert letti["cli"]["dove"].endswith("Dockerfile")


def test_legge_le_azioni_del_workflow_vero():
    letti = vc.leggi_i_file()
    assert "actions/setup-node" in letti["azioni"]
    assert isinstance(letti["azioni"]["actions/setup-node"]["major"], int)


def test_legge_tetti_e_pavimenti_da_requirements():
    letti = vc.leggi_i_file()
    assert letti["tetti"]["anthropic"]["major_escluso"] == 1
    assert letti["pavimenti"]["anthropic"]["minimo"] == "0.87.0"
    # `installato` puo' essere None (pacchetto assente): e' un fatto, non un
    # errore, e a valle si salta invece di inventare uno scarto.
    assert "installato" in letti["pavimenti"]["anthropic"]


def test_una_dipendenza_senza_tetto_non_finisce_fra_i_tetti():
    """`model2vec>=0.8.0` non ha un `<`: non c'e' nessun major da escludere, e
    inventarne uno produrrebbe uno scarto permanente su una riga sana."""
    letti = vc.leggi_i_file()
    assert "model2vec" not in letti["tetti"]
    assert "model2vec" in letti["pavimenti"]


# ── I registri: un guasto non solleva, diventa un motivo ───────────────────

def test_un_registro_irraggiungibile_diventa_un_motivo_non_un_eccezione(monkeypatch):
    """L'hook gira dentro `git push`: un'eccezione qui non sarebbe un blocco
    leggibile, sarebbe un traceback in mezzo a un rilascio."""
    def esplode(*a, **k):
        raise OSError("rete assente")
    monkeypatch.setattr(vc.urllib.request, "urlopen", esplode)
    registri = vc.interroga_i_registri(vc.leggi_i_file())
    assert registri["cli"]["errore"]
    assert "rete assente" in registri["cli"]["errore"]


# ── Il cancello: la variabile che sblocca ─────────────────────────────────

@pytest.mark.parametrize("valore,sblocca", [
    ("1", True),
    ("si", False), ("true", False), ("0", False), ("", False), (None, False),
])
def test_solo_il_valore_ESATTO_sblocca(valore, sblocca):
    """Una variabile che accetta qualunque cosa non vuota si finisce per
    lasciarla esportata nel profilo -- e allora il cancello e' aperto per
    sempre senza che nessuno lo abbia deciso."""
    assert vc.risposta_accettata(valore) is sblocca


# ── --aggiorna: scrive il workflow, e SOLO quello ─────────────────────────

def test_aggiorna_porta_le_azioni_all_ultimo_major_e_non_tocca_altro(tmp_path, monkeypatch):
    """Le due astensioni hanno ragioni DIVERSE, e nessuna e' prudenza generica.

    `requirements.txt`: gli scarti Python non si correggono cambiando un
    numero. Un major sopra il tetto e' una DECISIONE (si alza e si prova, o si
    resta); un pacchetto installato sotto il pavimento si ripara
    nell'AMBIENTE, non nel file.

    `Dockerfile`: un confronto di numeri non puo' vedere se la CLI nuova smette
    di emettere `mcp_servers` nell'init -- nel qual caso HIRIS non si rompe,
    diventa CIECO. Quel controllo lo fa `sonda_strumenti` a runtime.
    """
    flusso = tmp_path / ".github" / "workflows"
    flusso.mkdir(parents=True)
    (flusso / "tests.yml").write_text(
        "jobs:\n  a:\n    steps:\n      - uses: actions/setup-node@v4\n",
        encoding="utf-8")
    dentro = tmp_path / "hiris"
    dentro.mkdir()
    (dentro / "Dockerfile").write_text(
        "RUN npm install -g @anthropic-ai/claude-code@2.1.228\n", encoding="utf-8")
    (dentro / "requirements.txt").write_text("anthropic>=0.87.0,<1.0.0\n",
                                             encoding="utf-8")
    monkeypatch.setattr(vc, "RADICE", tmp_path)

    letti = vc.leggi_i_file()
    registri = {"cli": {"versione": "2.1.233"},
                "azioni": {"actions/setup-node": {"major": 7}},
                "pypi": {"anthropic": {"versione": "0.122.0"}}}
    toccati = vc.aggiorna_azioni(letti, registri)

    assert toccati == ["actions/setup-node"]
    assert "actions/setup-node@v7" in (flusso / "tests.yml").read_text(encoding="utf-8")
    assert "2.1.228" in (dentro / "Dockerfile").read_text(encoding="utf-8"), (
        "il Dockerfile non si tocca senza --cli")
    assert (dentro / "requirements.txt").read_text(encoding="utf-8") == \
        "anthropic>=0.87.0,<1.0.0\n", "requirements.txt non si tocca mai"


def test_con_cli_il_dockerfile_si_tocca_eccome(tmp_path, monkeypatch):
    """La polarita' opposta: senza questa prova, un `aggiorna_cli` che non fa
    niente passerebbe il test qui sopra."""
    flusso = tmp_path / ".github" / "workflows"
    flusso.mkdir(parents=True)
    (flusso / "tests.yml").write_text(
        "      - uses: actions/setup-node@v7\n", encoding="utf-8")
    dentro = tmp_path / "hiris"
    dentro.mkdir()
    (dentro / "Dockerfile").write_text(
        "RUN npm install -g @anthropic-ai/claude-code@2.1.228\n", encoding="utf-8")
    (dentro / "requirements.txt").write_text("anthropic>=0.87.0,<1.0.0\n",
                                             encoding="utf-8")
    monkeypatch.setattr(vc, "RADICE", tmp_path)

    nuova = vc.aggiorna_cli(vc.leggi_i_file(), {"cli": {"versione": "2.1.233"}})
    assert nuova == "2.1.233"
    assert "claude-code@2.1.233" in (dentro / "Dockerfile").read_text(encoding="utf-8")
