"""L'osservatore chiede una ricetta per un dispositivo che pesa.

Spec `docs/design/2026-09-10-i-tre-attori.md` §7: *«Chi la scrive. L'osservatore,
quando decide che un dispositivo pesa e non ha una ricetta per lui, chiede al
modello -- **una volta, non ogni giorno** -- mostrandogli il dispositivo con
**tutte le sue entita' insieme** e l'obiettivo. Viste insieme, le sette misure
di un inverter si spiegano da sole; viste una alla volta sono sette
indovinelli.»*

**Perche' esiste, col numero.** Senza questo pezzo il registro delle operazioni
e il motore delle ricette esistono ma nessuno scrive ricette nuove: misurato
sulla casa vera il 13/09/2026, il resoconto avrebbe **~6 misure al giorno**
(tutte dello stesso inverter, l'unica ricetta che il repo porta) contro ~28
fatti di cronaca. L'analista lavora sulle misure, e ne avrebbe il 18%.
"""
import json

import pytest

from hiris.app.mind import recipe_turn as rt
from hiris.app.mind.knowledge import KnowledgeStore

CASA = {
    "dispositivi": [{"id": "dev1", "nome": "Inverter ZCS"},
                    {"id": "dev2", "nome": "Lavatrice"}],
    "entita": [
        {"id": "sensor.prodotta", "nome": "Energia prodotta oggi",
         "dispositivo_id": "dev1", "classe": "energy", "unita": "kWh"},
        {"id": "sensor.consumata", "nome": "Energia consumata oggi",
         "dispositivo_id": "dev1", "classe": "energy", "unita": "kWh"},
        {"id": "switch.lavatrice", "nome": "Lavatrice",
         "dispositivo_id": "dev2"},
    ],
}

RICETTA_BUONA = {
    "why": "l'inverter e' la fonte di casa e pesa sul risparmio energetico",
    "steps": [
        {"name": "prodotta", "operation": "somma_periodo",
         "inputs": ["@sensor.prodotta"], "params": {"unit": "kWh"}},
        {"name": "consumata", "operation": "somma_periodo",
         "inputs": ["@sensor.consumata"], "params": {"unit": "kWh"}},
        {"name": "quota_coperta", "operation": "quota",
         "inputs": ["$prodotta", "$consumata"]},
    ],
}


@pytest.fixture
def sapere(tmp_path):
    s = KnowledgeStore(str(tmp_path / "sapere.db"))
    yield s
    s.close()


# -- la domanda -------------------------------------------------------------

def test_la_domanda_mostra_il_dispositivo_con_TUTTE_le_sue_entita():
    """*«Viste insieme, le sette misure di un inverter si spiegano da sole;
    viste una alla volta sono sette indovinelli»* (spec §7).

    Mutazione che la uccide: mandare una entita' per volta.
    """
    domanda = rt.build_device_question(
        "ottimizzare la casa", CASA, "dev1")

    assert "Inverter ZCS" in domanda
    assert "sensor.prodotta" in domanda
    assert "sensor.consumata" in domanda
    assert "ottimizzare la casa" in domanda


def test_la_domanda_NON_mostra_le_entita_di_un_altro_dispositivo():
    """Un dispositivo per volta: mescolarli produrrebbe una ricetta che nomina
    entita' che non gli appartengono."""
    domanda = rt.build_device_question("ottimizzare la casa", CASA, "dev1")

    assert "switch.lavatrice" not in domanda


def test_un_dispositivo_SENZA_entita_non_si_chiede():
    """Non c'e' niente da mostrare al modello, e chiedere costerebbe un giro
    per una risposta che non puo' esistere."""
    assert rt.build_device_question("x", CASA, "dev_inesistente") is None


# -- la risposta ------------------------------------------------------------

def test_una_ricetta_valida_si_legge():
    dati, motivo = rt.read_recipe(json.dumps(RICETTA_BUONA))

    assert motivo is None
    assert [p["name"] for p in dati["steps"]] == ["prodotta", "consumata",
                                                  "quota_coperta"]


def test_la_staccionata_del_modello_si_tollera():
    """I modelli incorniciano il JSON anche quando si chiede di non farlo:
    buttare il giro per un dettaglio di forma costerebbe un giro intero. E' la
    stessa tolleranza gia' presa da `observer.read_decisions`."""
    dati, motivo = rt.read_recipe(
        "Ecco la ricetta:\n```json\n" + json.dumps(RICETTA_BUONA) + "\n```\n")

    assert motivo is None
    assert dati["why"]


def test_una_risposta_ILLEGGIBILE_non_e_una_ricetta_vuota():
    """**Un guasto e una ricetta vuota sono due cose diverse.** Appiattire il
    primo sulla seconda scriverebbe «per questo dispositivo non c'e' niente da
    calcolare» su un dispositivo che nessuno ha capito."""
    dati, motivo = rt.read_recipe("mi dispiace, non saprei")

    assert dati is None
    assert motivo


# -- si scrive nel sapere, e si rifiuta senza correggere --------------------

def test_una_ricetta_valida_finisce_nel_sapere(sapere):
    """*«Dove vive: nel sapere, con provenienza e prove»* (spec §7).

    Mutazione ESEGUITA: non scrivere la riga -- rossa, la ricetta si
    ricomporrebbe da capo a ogni giro.
    """
    esito = rt.apply_recipe(sapere, CASA, "dev1", json.dumps(RICETTA_BUONA),
                            who="claude-opus-5", when_ts=1789000000.0)

    assert esito["scritta"]
    riga = sapere.get("dispositivo", "dev1", rt.RECIPE_FIELD)
    assert json.loads(riga.value)["steps"][0]["name"] == "prodotta"
    assert riga.provenance == "dedotto"
    assert riga.evidence, "una deduzione senza prove non nascerebbe nemmeno"


def test_una_ricetta_NON_VALIDA_si_rifiuta_e_NON_si_corregge(sapere):
    """*«Il codice la verifica e, se non e' valida, la rifiuta -- non la
    corregge»* (spec §7). Correggere vorrebbe dire indovinare cosa intendeva
    chi l'ha scritta.

    Mutazione ESEGUITA: scrivere comunque la ricetta -- rossa, una ricetta che
    nomina un'entita' inesistente finirebbe in produzione.
    """
    storta = {"why": "x", "steps": [
        {"name": "p", "operation": "somma_periodo",
         "inputs": ["@sensor.mai_esistita"], "params": {"unit": "kWh"}}]}

    esito = rt.apply_recipe(sapere, CASA, "dev1", json.dumps(storta),
                            who="claude-opus-5", when_ts=1789000000.0)

    assert not esito["scritta"]
    assert any("sensor.mai_esistita" in p for p in esito["problemi"])
    assert sapere.get("dispositivo", "dev1", rt.RECIPE_FIELD) is None


def test_un_rifiuto_SI_SCRIVE_col_suo_perche(sapere):
    """**«Non capito» si scrive** (spec §8). Un rifiuto che non lascia traccia
    farebbe richiedere la stessa ricetta ogni notte, per sempre, e il
    proprietario non saprebbe mai che quel dispositivo non e' stato capito.

    Mutazione ESEGUITA: non scrivere la riga del rifiuto -- rossa.
    """
    rt.apply_recipe(sapere, CASA, "dev1", "non saprei",
                    who="claude-opus-5", when_ts=1789000000.0)

    riga = sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD)
    assert riga.verification == "non_capito"
    assert riga.value


# -- una volta, non ogni giorno --------------------------------------------

def test_un_dispositivo_che_HA_GIA_una_ricetta_non_si_richiede(sapere):
    """*«Una volta, non ogni giorno»* (spec §7): un giro del modello costa, e
    ripeterlo ogni notte per un dispositivo gia' capito e' il genere di spesa
    che non si vede finche' non si guarda la bolletta."""
    rt.apply_recipe(sapere, CASA, "dev1", json.dumps(RICETTA_BUONA),
                    who="x", when_ts=1789000000.0)

    assert rt.devices_to_ask(sapere, CASA, {"sensor.prodotta"}) == []


def test_un_dispositivo_gia_NON_CAPITO_non_si_richiede(sapere):
    """Anche il rifiuto vale come risposta data: senza questo, un dispositivo
    che il modello non sa leggere costerebbe un giro ogni notte per sempre.

    Mutazione ESEGUITA: guardare solo il campo della ricetta -- rossa.
    """
    rt.apply_recipe(sapere, CASA, "dev1", "non saprei", who="x",
                    when_ts=1789000000.0)

    assert rt.devices_to_ask(sapere, CASA, {"sensor.prodotta"}) == []


def test_si_chiede_solo_per_i_dispositivi_che_PESANO(sapere):
    """«Pesa» vuol dire che almeno una sua entita' e' dentro lo scope --
    cioe' che l'osservatore ha deciso che quello che fa conta. Chiedere una
    ricetta per un dispositivo che nessuno guarda sarebbe un giro del modello
    per un numero che nessuno leggera'.

    Mutazione ESEGUITA: chiedere per tutti i dispositivi -- rossa, compare la
    lavatrice che nessuno guarda.
    """
    assert rt.devices_to_ask(sapere, CASA, {"sensor.prodotta"}) == ["dev1"]
    assert rt.devices_to_ask(sapere, CASA, set()) == []
