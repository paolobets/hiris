import pytest
import yaml

from hiris.app.casa.lettura_yaml import carica_file, carica_yaml


def test_yaml_normale():
    assert carica_yaml("- id: '1'\n  alias: Sveglia\n") == [{"id": "1", "alias": "Sveglia"}]


def test_un_tag_di_home_assistant_non_fa_fallire_tutto():
    """Un solo !secret farebbe saltare la lettura di TUTTE le automazioni."""
    testo = """
- id: '1'
  alias: Sveglia
  action:
    - service: notify.telefono
      data:
        message: !secret messaggio_sveglia
- id: '2'
  alias: Buonanotte
"""
    voci = carica_yaml(testo)
    assert [v["alias"] for v in voci] == ["Sveglia", "Buonanotte"]
    # Il valore del tag non si perde in silenzio: si vede che c'era qualcosa.
    assert "secret" in str(voci[0]["action"][0]["data"]["message"]).lower()


def test_un_tag_che_costruisce_oggetti_python_viene_rifiutato():
    """La tolleranza vale per i tag di Home Assistant, NON per l'esecuzione di
    codice. `_CaricatoreHA` eredita da SafeLoader e il costruttore permissivo
    restituisce sempre una stringa: `!!python/object/apply` resta rifiutato.

    Il file lo scrive Home Assistant in una cartella su cui HIRIS ha gia'
    accesso in scrittura, quindi la minaccia e' remota — ma una difesa che
    dipende dall'attenzione di chi legge non e' una difesa."""
    with pytest.raises(yaml.constructor.ConstructorError):
        carica_yaml("!!python/object/apply:os.system ['echo ciao']")

    with pytest.raises(yaml.constructor.ConstructorError):
        carica_yaml("- !!python/object:os.system {}\n")


def test_un_yaml_malformato_solleva_invece_di_tacere():
    """Restituire una lista vuota sarebbe indistinguibile da «nessuna
    automazione»: chi chiama deve poter distinguere il guasto dal vuoto."""
    with pytest.raises(yaml.YAMLError):
        carica_yaml("- id: '1'\n   alias: male indentato\n  altro: x\n")


def test_un_file_assente_e_None_non_una_lista_vuota(tmp_path):
    """`automations.yaml` puo' non esistere: e' diverso da «esiste ed e' vuoto»."""
    assert carica_file(tmp_path / "assente.yaml") is None


def test_un_file_vuoto_e_una_lista_vuota(tmp_path):
    p = tmp_path / "vuoto.yaml"
    p.write_text("", encoding="utf-8")
    assert carica_file(p) == []


def test_un_file_in_un_altro_encoding_solleva_invece_di_sporcare(tmp_path):
    """Con `errors="replace"` un byte non-UTF-8 diventava `�` e il file
    tornava come un dato buono con una macchia dentro: chi legge non poteva
    distinguerlo da un alias scritto male."""
    p = tmp_path / "sporco.yaml"
    p.write_bytes(b"- id: '1'\n  alias: Bagno\xe8\n")
    with pytest.raises(UnicodeDecodeError):
        carica_file(p)
