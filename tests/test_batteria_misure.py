"""La batteria: nessun nome della casa nel repo, e il riassunto contato bene."""
import importlib.util
import json
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "batteria_misure.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("batteria_misure", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_le_domande_vengono_da_FUORI(tmp_path):
    """Mutazione ESEGUITA: una lista DOMANDE scritta nello script -- rossa."""
    sorgente = SCRIPT.read_text(encoding="utf-8")
    assert "DOMANDE = [" not in sorgente
    f = tmp_path / "d.json"
    f.write_text(json.dumps([{"n": 1, "aspetto": "a", "domanda": "q",
                              "atteso": "x", "effetto": None,
                              "giudice": "hiris"}]), encoding="utf-8")
    assert _modulo().carica_domande(str(f))[0]["domanda"] == "q"


def test_un_file_di_domande_senza_criterio_si_rifiuta(tmp_path):
    """Il criterio si scrive PRIMA (spec §6): una domanda senza `atteso` non parte."""
    f = tmp_path / "d.json"
    f.write_text(json.dumps([{"n": 1, "aspetto": "a", "domanda": "q",
                              "effetto": None, "giudice": "hiris"}]),
                 encoding="utf-8")
    with pytest.raises(SystemExit):
        _modulo().carica_domande(str(f))


def test_il_riassunto_conta_giudizi_e_tempi_solo_sui_riusciti():
    """Mutazione ESEGUITA: mediana anche sugli scaduti -- rossa."""
    esiti = [{"stato": "ok", "secondi": 10, "giudizio": "giusta"},
             {"stato": "ok", "secondi": 20, "giudizio": "incompleta"},
             {"stato": "ok", "secondi": 30, "giudizio": None},
             {"stato": "scaduto", "secondi": 900, "giudizio": None}]
    r = _modulo().riassunto(esiti)
    assert r["riusciti"] == 3 and r["mediana_s"] == 20
    assert r["giudizi"] == {"giusta": 1, "incompleta": 1, "sbagliata": 0,
                            "da_giudicare": 1}


def test_senza_conferme_le_domande_con_effetto_non_partono():
    """Senza nessuno alla tastiera, una promessa, un ricordo o una luce
    accesa non si fanno: quelle domande restano al proprietario.

    Mutazione ESEGUITA: `domande_ammesse` che restituisce tutto -- rossa."""
    domande = [{"n": 1, "effetto": None}, {"n": 21, "effetto": "promessa"},
               {"n": 27, "effetto": "azione"}]
    m = _modulo()
    assert [d["n"] for d in m.domande_ammesse(domande, conferme=False)] == [1]
    assert len(m.domande_ammesse(domande, conferme=True)) == 3


def test_l_errore_del_turno_arriva_col_suo_testo(monkeypatch):
    """Il poll della chat risponde agli errori con `error_body`: il testo sta
    in `error`, non in `message` (revisione cloud, giro 2, G2-7). Il corpo si
    chiede al confine invece di ricopiarlo.

    Mutazione ESEGUITA: lo script che legge `message` -- rossa."""
    from hiris.app.api.boundary import error_body

    m = _modulo()
    risposte = iter([(202, json.dumps({"job_id": "j1"}).encode()),
                     (200, json.dumps(error_body("non arrivata",
                                                 status="error")).encode())])
    monkeypatch.setattr(m, "_bussa", lambda *a, **k: next(risposte))
    monkeypatch.setattr(m, "PASSO_S", 0)
    _, stato, testo, job = m.chiedi("http://x", "k", "q", attesa=5)
    assert (stato, testo, job) == ("errore", "non arrivata", "j1")


class _FiloFinto:
    """Il filo di chi firma, con le rotte che la batteria usa: una domanda
    scrive nella conversazione attiva (la crea se non c'e'), chiudere la
    lascia nell'elenco col suo riassunto, cancellare la toglie."""

    def __init__(self, gia=0, in_volo=0):
        self.conv = {f"vecchia{i}": [] for i in range(gia)}
        self.attiva = None
        self.in_volo = in_volo
        self.viste = []  # quante conversazioni c'erano a ogni domanda

    def __call__(self, url, chiave, metodo, percorso, corpo=b"", attesa=60):
        if (metodo, percorso) == ("POST", "/api/chat"):
            self.viste.append(len(self.conv))
            if self.attiva is None:
                self.attiva = f"c{len(self.viste)}"
                self.conv[self.attiva] = []
            self.conv[self.attiva].append(json.loads(corpo)["message"])
            return 200, json.dumps({"response": "r"}).encode()
        if (metodo, percorso) == ("POST", "/api/chat/conversations"):
            if self.in_volo:
                self.in_volo -= 1
                return 409, json.dumps({"error": "in arrivo"}).encode()
            self.attiva = None
            return 200, b'{"ok": true}'
        if (metodo, percorso) == ("GET", "/api/chat/conversations"):
            return 200, json.dumps({"conversations": [
                {"id": i, "attiva": i == self.attiva} for i in self.conv]}).encode()
        if metodo == "DELETE":
            ident = percorso.rsplit("/", 1)[1]
            if ident == self.attiva or ident not in self.conv:
                return 404, json.dumps({"error": "nessuna"}).encode()
            del self.conv[ident]
            return 200, b'{"ok": true}'
        raise AssertionError((metodo, percorso))


def _lancia(monkeypatch, tmp_path, filo, *opzioni):
    m = _modulo()
    domande = tmp_path / "d.json"
    domande.write_text(json.dumps([
        {"n": n, "aspetto": "a", "domanda": f"q{n}", "atteso": "x",
         "effetto": None, "giudice": "hiris"} for n in (1, 2, 3)]),
        encoding="utf-8")
    esiti = tmp_path / "e.json"
    monkeypatch.setattr(m, "_bussa", filo)
    monkeypatch.setattr(m, "PASSO_S", 0)
    monkeypatch.setattr("sys.argv", [
        "batteria", "--domande", str(domande), "--chiave", "k", "--url", "u",
        "--etichetta", "ponte", "--esiti", str(esiti), "--automatico", *opzioni])
    m.main()
    return json.loads(esiti.read_text(encoding="utf-8"))


def test_domande_isolate_ogni_domanda_trova_il_filo_vuoto(monkeypatch, tmp_path):
    """Sprint «Il giro snello», 1.1: la storia (e i riassunti delle chiuse,
    che rientrano nel contesto) non passa da una domanda all'altra.

    Mutazioni ESEGUITE: `svuota_filo` che chiude senza cancellare -- rossa
    (viste [0, 1, 2]); `main` che non svuota dopo la domanda -- rossa."""
    filo = _FiloFinto()
    esiti = _lancia(monkeypatch, tmp_path, filo, "--domande-isolate")
    assert filo.viste == [0, 0, 0] and filo.conv == {}
    assert [e["domanda_isolata"] for e in esiti] == [True, True, True]


def test_senza_l_opzione_le_domande_restano_in_un_filo(monkeypatch, tmp_path):
    """Il comportamento di prima non cambia: e' il confronto con le misure
    gia' prese."""
    filo = _FiloFinto()
    esiti = _lancia(monkeypatch, tmp_path, filo)
    assert filo.viste == [0, 1, 1] and filo.conv == {"c1": ["q1", "q2", "q3"]}
    assert not any(e["domanda_isolata"] for e in esiti)


def test_un_filo_gia_pieno_non_parte_senza_svuota_filo(monkeypatch, tmp_path):
    """Le conversazioni di prima non sono della batteria: le cancella solo
    chi lancia, dicendolo.

    Mutazione ESEGUITA: il controllo d'avvio tolto -- rossa."""
    filo = _FiloFinto(gia=2)
    with pytest.raises(SystemExit, match="2 conversazioni"):
        _lancia(monkeypatch, tmp_path, filo, "--domande-isolate")
    assert filo.viste == [] and len(filo.conv) == 2

    filo = _FiloFinto(gia=2)
    _lancia(monkeypatch, tmp_path, filo, "--domande-isolate", "--svuota-filo")
    assert filo.viste == [0, 0, 0] and filo.conv == {}


def test_svuotare_aspetta_la_risposta_in_volo(monkeypatch):
    """Il 409 dice che una risposta sta ancora arrivando: si aspetta, perche'
    svuotare adesso la farebbe atterrare nella domanda dopo. Un rifiuto
    diverso ferma la batteria.

    Mutazione ESEGUITA: il 409 trattato come ogni altro rifiuto -- rossa."""
    m = _modulo()
    monkeypatch.setattr(m, "PASSO_S", 0)
    filo = _FiloFinto(gia=1, in_volo=2)
    monkeypatch.setattr(m, "_bussa", filo)
    assert m.svuota_filo("u", "k", attesa=5) == 1 and filo.conv == {}

    monkeypatch.setattr(m, "_bussa", lambda *a, **k: (403, b'{"error": "no"}'))
    with pytest.raises(SystemExit, match=r"\[403\]: no"):
        m.svuota_filo("u", "k", attesa=5)
