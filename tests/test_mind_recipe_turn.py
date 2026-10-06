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

from hiris.app.home_space.house import House
from hiris.app.home_space.topology import Mirror
from hiris.app.mind import recipe_turn as rt
from hiris.app.mind.knowledge import Fact, KnowledgeStore
from hiris.app.mind.operations import CAUSES, FROZEN, NotComputable

CASA = House({
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
}, Mirror())

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


def test_la_domanda_DICE_quali_entita_hanno_una_serie():
    """**Il modello non puo' indovinarlo, e senza non smette di sbagliare.**

    Home Assistant tiene statistiche orarie solo per le entita' con uno
    `state_class`: misurato il 15/09/2026, **130 su 1206, tutte `sensor`**. Il
    catalogo gli mostrava il dispositivo con tutte le sue entita' e nessuna
    indicazione su quali sapessero produrre una serie -- e lui scriveva «quanto
    e' stata accesa la lavastoviglie», la domanda giusta sul dispositivo
    giusto, contro una fonte che per quell'entita' non esiste. Nel resoconto
    del 14/09: **18 rifiuti su 28** cosi'.

    Mutazione ESEGUITA: non dire quali -- rossa.
    """
    domanda = rt.build_device_question(
        "risparmiare", CASA, "dev1", with_series={"sensor.prodotta"})

    testa = domanda.split("Le operazioni che sai chiedere", 1)[0]
    # **Si guarda DENTRO le due righe, non se il nome compare da qualche
    # parte**: ogni entita' del dispositivo compare comunque nell'elenco che
    # apre la domanda, quindi `"sensor.consumata" in testa` non poteva
    # fallire. L'ha detto la mutazione che toglieva la riga «NON ne hanno» e
    # restava verde: il modello smetteva di sentirsi dire quali entita'
    # evitare -- il fatto per cui questa prova esiste -- e nessuno se ne
    # accorgeva.
    hanno = testa.split("Hanno una serie:", 1)[1].split("NON ne hanno", 1)[0]
    evitare = testa.split("NON ne hanno", 1)[1]

    assert "sensor.prodotta" in hanno
    assert "sensor.consumata" not in hanno
    assert "sensor.consumata" in evitare
    assert "sensor.prodotta" not in evitare


def test_senza_l_insieme_la_domanda_NON_afferma_niente_sulle_serie():
    """Chi non ha potuto chiedere a Home Assistant quali entita' abbiano
    statistiche non lo dice al modello: gli direbbe una cosa che non sa, e il
    modello ci costruirebbe sopra.

    **La prima stesura di questa prova non poteva fallire**: cercava la frase
    «non ha statistiche», che quel blocco non scrive mai -- lui scrive «NON ne
    hanno, e non chiederle». L'ha detto la mutazione, che restava verde
    trattando l'assenza come insieme vuoto. Si asserisce la proprieta' vera:
    **senza l'insieme, delle serie non si parla affatto**.

    Mutazione ESEGUITA: `with_series = set()` invece di non dire niente --
    rossa, il modello si sentirebbe dire che nessuna entita' ha una serie.
    """
    domanda = rt.build_device_question("risparmiare", CASA, "dev1")
    testa = domanda.split("Le operazioni che sai chiedere", 1)[0]

    assert "SERIE" not in testa
    assert "serie oraria" not in testa
    assert "non chiederle" not in testa
    # E le entita' ci sono comunque: e' la domanda di prima, non una monca.
    assert "sensor.prodotta" in testa


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
#
# Le tre prove del lettore (`read_recipe`: la ricetta valida, la staccionata,
# l'illeggibile che non e' una ricetta vuota) sono uscite col lettore, il
# 05/10/2026 (Tappa 6, Task 3): il JSON lo cava `steering.read_json`, e le
# stesse tre proprieta' le difendono `tests/test_lettore_unico.py` (ogni
# mestiere, ogni forma) e `tests/test_turno_troncato.py` (il lettore).


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


# -- il rifiuto ragionato, che non e' un «non capito» -----------------------

#: Cosa risponde il modello quando il dispositivo non ha niente da misurare.
#: **Copiata dalla casa vera** (`sapere`, 15/09/2026): il `why` e' quello che
#: il modello ha davvero scritto per una delle 18 luci.
RIFIUTO_RAGIONATO = {
    "why": ("Una luce ha solo stato acceso/spento: non c'e' una misura di "
            "comfort o efficienza che valga la pena calcolare da un'unica "
            "entita' on/off."),
    "steps": [],
}


def test_un_rifiuto_RAGIONATO_non_si_scrive_come_NON_CAPITO(sapere):
    """**«Ho capito, e non c'e' niente da misurare» non e' «non ho capito».**

    Misurato sulla casa vera il 15/09/2026, appena aperta la porta del sapere:
    **18 righe su 21** marcate `non_capito` erano rifiuti ragionati -- il
    modello aveva risposto col contratto in mano, un `why` pieno e `steps: []`
    -- e portavano una frase NOSTRA, «nessuno ha finito di scrivere», smentita
    dalle prove archiviate un campo piu' in la'.

    Mutazione ESEGUITA: scrivere il rifiuto ragionato nel campo del non
    capito -- rossa.
    """
    rt.apply_recipe(sapere, CASA, "dev1", json.dumps(RIFIUTO_RAGIONATO),
                    who="claude-opus-5", when_ts=1789000000.0)

    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None
    riga = sapere.get("dispositivo", "dev1", rt.DECLINED_FIELD)
    assert riga is not None, "un rifiuto ragionato si scrive, o si richiede per sempre"
    assert riga.verification is None, (
        "la verifica dice cosa ha detto il CONTROLLO, e il controllo non ha "
        "niente da ridire: la risposta era completa")


def test_un_rifiuto_ragionato_porta_il_perche_DEL_MODELLO(sapere):
    """Non la nostra frase: la sua.

    Mutazione ESEGUITA: scrivere i problemi del validatore invece del `why` --
    rossa, tornerebbe «nessuno ha finito di scrivere» su una risposta finita.
    """
    rt.apply_recipe(sapere, CASA, "dev1", json.dumps(RIFIUTO_RAGIONATO),
                    who="claude-opus-5", when_ts=1789000000.0)

    riga = sapere.get("dispositivo", "dev1", rt.DECLINED_FIELD)
    assert riga.value == RIFIUTO_RAGIONATO["why"]
    assert "nessun passo" not in riga.value


def test_una_risposta_senza_passi_e_SENZA_perche_resta_NON_CAPITA(sapere):
    """Il confine, dalla parte opposta: senza il `why` il modello non ha usato
    il contratto, e «non c'e' niente da misurare» non l'ha detto nessuno.

    Mutazione ESEGUITA: trattare ogni `steps: []` come rifiuto ragionato --
    rossa, una risposta monca diventerebbe una decisione.
    """
    rt.apply_recipe(sapere, CASA, "dev1", json.dumps({"steps": []}),
                    who="claude-opus-5", when_ts=1789000000.0)

    assert sapere.get("dispositivo", "dev1", rt.DECLINED_FIELD) is None
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is not None


def test_un_dispositivo_che_ha_DECLINATO_non_si_richiede(sapere):
    """Un rifiuto ragionato vale come risposta data, esattamente come gli
    altri due campi: guardarne due su tre lo richiederebbe ogni notte.

    Mutazione ESEGUITA: togliere il campo nuovo da `devices_to_ask` -- rossa.
    """
    rt.apply_recipe(sapere, CASA, "dev1", json.dumps(RIFIUTO_RAGIONATO),
                    who="x", when_ts=1789000000.0)

    assert rt.devices_to_ask(sapere, CASA, {"sensor.prodotta"}) == []


def test_un_rifiuto_ragionato_SCADE_quando_il_registro_cresce(sapere):
    """Stessa regola del «non capito» (decisione del proprietario, 13/09):
    «non c'e' niente da misurare» e' vero **contro un registro**. Il giorno in
    cui `tempo_in_stato` diventa scrivibile in una ricetta, «una luce on/off
    non ha niente da misurare» smette di essere vero.

    Mutazione ESEGUITA: non guardare la versione del registro sul campo nuovo
    -- rossa, il rifiuto diventerebbe eterno.
    """
    sapere.write(Fact(
        subject_kind="dispositivo", subject="dev1", field=rt.DECLINED_FIELD,
        value="una luce on/off non ha niente da misurare", provenance="dedotto",
        evidence="il modello ha risposto: {\"why\": \"...\", \"steps\": []}",
        source=f"{rt.REFUSAL_SOURCE}un-registro-di-ieri",
        who="x", when_ts=1789000000.0))

    assert rt.devices_to_ask(sapere, CASA, {"sensor.prodotta"}) == ["dev1"]


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


def test_le_risposte_di_tutti_i_dispositivi_si_leggono_in_UNA_lettura(sapere):
    """A-38 (Tappa 3, Task 12): «chi ha gia' una risposta?» era tre SELECT
    per dispositivo a ogni giro (ricetta, non capito, rifiuto ragionato), e
    una per dispositivo nella potatura e nel resoconto. Ora una sola
    (`KnowledgeStore.device_answers`), qualunque sia il numero dei
    dispositivi; l'ordine resta quello dell'anagrafe.

    Mutazione ESEGUITA (04/10/2026): `devices_to_ask` che torna a chiedere
    `store.get` per dispositivo -- rossa (8 SELECT invece di 2: tre per
    ciascuno dei due dispositivi)."""
    rt.apply_recipe(sapere, CASA, "dev2", "non saprei", who="x", when_ts=1789000000.0)
    statements: list[str] = []
    sapere._conn.set_trace_callback(statements.append)
    try:
        asked = rt.devices_to_ask(sapere, CASA, {"sensor.prodotta", "switch.lavatrice"})
        pruned = rt.has_named_recipes(sapere, CASA)
    finally:
        sapere._conn.set_trace_callback(None)
    assert asked == ["dev1"]
    assert pruned is False
    assert sum(1 for q in statements if q.lstrip().upper().startswith("SELECT")) == 2
    answers = sapere.device_answers((rt.RECIPE_FIELD, rt.UNDERSTOOD_FIELD))
    assert set(answers) == {"dev2"}
    assert set(answers["dev2"]) == {rt.UNDERSTOOD_FIELD}


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


# -- una risposta che non c'e' non e' un «non capito» -----------------------

def test_una_risposta_VUOTA_non_si_scrive_e_non_consuma_il_colpo(sapere):
    """**Il difetto trovato dal vivo il 13/09/2026 alle 19:58.**

    Il ponte non sapeva ragionare la specie di turno «ricetta»: restituiva una
    decisione VUOTA, e questa funzione la scriveva come `non_capito` -- cioe'
    un'affermazione sulla comprensione di un modello che non era mai stato
    interpellato. E siccome un rifiuto vale come risposta data, quel
    dispositivo non sarebbe stato chiesto **mai piu'**.

    «Il modello non ha capito» e «nessuno ha chiesto al modello» sono due cose,
    e scriverle con la stessa parola e' il difetto che questo progetto insegue
    per mestiere.

    Mutazione ESEGUITA: togliere la guardia sulla risposta vuota -- rossa, il
    dispositivo sparisce da quelli da chiedere.
    """
    esito = rt.apply_recipe(sapere, CASA, "dev1", "   ",
                            who="modello (ponte)", when_ts=1789000000.0)

    assert not esito["scritta"]
    assert esito["risposta"] is False
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None
    # E il colpo non e' consumato: il giro dopo si richiede.
    assert rt.devices_to_ask(sapere, CASA, {"sensor.prodotta"}) == ["dev1"]


def test_una_risposta_VERA_ma_illeggibile_SI_scrive(sapere):
    """L'altra meta': se il modello **ha** risposto e la sua risposta non si
    legge, quello si' e' un «non capito» -- e va scritto, o la stessa domanda
    tornerebbe ogni giorno."""
    esito = rt.apply_recipe(sapere, CASA, "dev1", "mi dispiace, non saprei",
                            who="modello (ponte)", when_ts=1789000000.0)

    assert esito["risposta"] is True
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is not None


def test_i_rifiuti_scritti_da_un_ponte_MUTO_escono_con_la_migrazione(tmp_path):
    """**Ogni riga di `ricetta_non_capita` esistente era una falsa
    affermazione**, e si puo' dire con certezza: quel campo e' nato con la
    3.31.0 e il suo unico scrittore era rotto dal primo minuto.

    Non sono dati dell'utente -- sono righe che questo programma ha scritto su
    se stesso, sbagliando -- e lasciarle sarebbe lasciare una bugia in un
    archivio che esiste per non dirne.

    Mutazione ESEGUITA: togliere `3: _migration_3` dalla mappa -- rossa, la
    riga sopravvive e il dispositivo non viene chiesto mai piu'.
    """
    from hiris.app.mind.knowledge import KnowledgeStore
    from hiris.app.storage import connect

    db = str(tmp_path / "sapere.db")
    vecchio = KnowledgeStore(db)
    rt.apply_recipe(vecchio, CASA, "dev1", "non saprei", who="x",
                    when_ts=1789000000.0)
    assert vecchio.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is not None
    vecchio.close()
    # Si riporta l'archivio alla versione di prima della correzione.
    conn = connect(db)
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    nuovo = KnowledgeStore(db)
    try:
        assert nuovo.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None
        assert rt.devices_to_ask(nuovo, CASA, {"sensor.prodotta"}) == ["dev1"]
    finally:
        nuovo.close()


def test_le_diciotto_righe_GIA_SCRITTE_si_spostano_col_perche_del_modello(tmp_path):
    """La migrazione recupera cio' che c'e', invece di ricomprarlo.

    **Le 18 righe sulla casa vera portano gia' dentro la risposta del
    modello**, `why` compreso: leggerla e spostarla costa zero, cancellarle
    costerebbe 18 giri del ponte per farsi ridire le stesse parole.

    Mutazione ESEGUITA: togliere `7: _migration_7` dalla mappa -- rossa.
    """
    from hiris.app.mind.knowledge import KnowledgeStore
    from hiris.app.storage import connect

    db = str(tmp_path / "sapere.db")
    vecchio = KnowledgeStore(db)
    # Come stava archiviata, parola per parola, il 15/09/2026.
    vecchio.write(Fact(
        subject_kind="dispositivo", subject="dev1", field=rt.UNDERSTOOD_FIELD,
        value=("la ricetta non ha nessun passo: non e' una ricetta che non "
               "calcola niente, e' una ricetta che nessuno ha finito di scrivere"),
        provenance="dedotto",
        evidence=('il modello ha risposto: {"why": "Una luce ha solo stato '
                  'acceso/spento: nessuna misura di comfort da ricavarne.", '
                  '"steps": []}'),
        source=f"{rt.REFUSAL_SOURCE}{rt.REGISTRY_VERSION}",
        verification="non_capito", who="modello (ponte)", when_ts=1789000000.0))
    # E una che il modello NON aveva capito davvero: deve restare dov'e'.
    vecchio.write(Fact(
        subject_kind="dispositivo", subject="dev2", field=rt.UNDERSTOOD_FIELD,
        value="la risposta non e' un JSON leggibile", provenance="dedotto",
        evidence="il modello ha risposto: ecco la ricetta!",
        source=f"{rt.REFUSAL_SOURCE}{rt.REGISTRY_VERSION}",
        verification="non_capito", who="modello (ponte)", when_ts=1789000000.0))
    vecchio.close()
    conn = connect(db)
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()

    nuovo = KnowledgeStore(db)
    try:
        spostata = nuovo.get("dispositivo", "dev1", rt.DECLINED_FIELD)
        assert spostata is not None, "il rifiuto ragionato cambia campo"
        assert spostata.value.startswith("Una luce ha solo stato acceso/spento")
        assert spostata.verification is None
        assert nuovo.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None
        # **Quella vera resta**: la migrazione sposta i rifiuti ragionati, non
        # svuota il campo.
        assert nuovo.get("dispositivo", "dev2", rt.UNDERSTOOD_FIELD) is not None
        # E nessuno dei due torna fra i da chiedere: entrambi hanno risposto.
        assert rt.devices_to_ask(nuovo, CASA, {"sensor.prodotta"}) == []
    finally:
        nuovo.close()


def test_una_riga_che_NON_si_sa_rileggere_torna_una_domanda(tmp_path):
    """Il caso storto: prove senza un `why` leggibile.

    **Non si indovina e non si tiene.** Si cancella, e il dispositivo torna
    fra quelli da chiedere: un giro del ponte costa meno di una riga che
    afferma qualcosa che nessuno puo' piu' verificare.

    Mutazione ESEGUITA: tenerla dov'e' -- rossa, resterebbe la frase falsa.
    """
    from hiris.app.mind.knowledge import KnowledgeStore
    from hiris.app.storage import connect

    db = str(tmp_path / "sapere.db")
    vecchio = KnowledgeStore(db)
    vecchio.write(Fact(
        subject_kind="dispositivo", subject="dev1", field=rt.UNDERSTOOD_FIELD,
        value="la ricetta non ha nessun passo: non e' una ricetta che non "
              "calcola niente, e' una ricetta che nessuno ha finito di scrivere",
        provenance="dedotto", evidence="il modello ha risposto: ",
        source=f"{rt.REFUSAL_SOURCE}{rt.REGISTRY_VERSION}",
        verification="non_capito", who="modello (ponte)", when_ts=1789000000.0))
    vecchio.close()
    conn = connect(db)
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()

    nuovo = KnowledgeStore(db)
    try:
        assert nuovo.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None
        assert nuovo.get("dispositivo", "dev1", rt.DECLINED_FIELD) is None
        assert rt.devices_to_ask(nuovo, CASA, {"sensor.prodotta"}) == ["dev1"]
    finally:
        nuovo.close()


def test_un_perche_NULLO_non_diventa_la_parola_steps(tmp_path):
    """**Il difetto che la revisione indipendente ha trovato leggendo il
    codice, il 15/09/2026.** `_why_from_evidence` cercava il primo apice dopo
    i due punti di `"why"`: con `{"why": null, "steps": []}` quell'apice e'
    quello della chiave SEGUENTE, e la funzione tornava la stringa `steps`.

    Una riga sarebbe finita in `ricetta_non_serve` col perche' **«steps»**: un
    dispositivo dichiarato «rifiutato ragionatamente» con una ragione che non
    e' una ragione, e mai piu' richiesto.

    Mutazione ESEGUITA: tornare al `find` dell'apice -- rossa.
    """
    from hiris.app.mind.knowledge import KnowledgeStore, _why_from_evidence
    from hiris.app.storage import connect

    assert _why_from_evidence(
        'il modello ha risposto: {"why": null, "steps": []}') == ""
    assert _why_from_evidence(
        'il modello ha risposto: {"why": 42, "steps": []}') == ""
    assert _why_from_evidence(
        'il modello ha risposto: {"why": "perche si", "steps": []}') == "perche si"

    # E fino in fondo: una riga cosi' non si sposta, si cancella.
    db = str(tmp_path / "sapere.db")
    vecchio = KnowledgeStore(db)
    vecchio.write(Fact(
        subject_kind="dispositivo", subject="dev1", field=rt.UNDERSTOOD_FIELD,
        value="la ricetta non dice PERCHE esiste - la ricetta non ha nessun passo",
        provenance="dedotto",
        evidence='il modello ha risposto: {"why": null, "steps": []}',
        source=f"{rt.REFUSAL_SOURCE}{rt.REGISTRY_VERSION}",
        verification="non_capito", who="modello (ponte)", when_ts=1789000000.0))
    vecchio.close()
    conn = connect(db)
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()

    nuovo = KnowledgeStore(db)
    try:
        assert nuovo.get("dispositivo", "dev1", rt.DECLINED_FIELD) is None
        assert nuovo.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None
    finally:
        nuovo.close()


def test_la_migrazione_non_uccide_l_avvio_se_la_riga_nuova_ESISTE_GIA(tmp_path):
    """Chiave primaria `(genere, soggetto, campo)`: spostare una riga da
    `ricetta_non_capita` a `ricetta_non_serve` **collide** se la seconda c'e'
    gia' -- e `init_schema` non cattura, quindi `KnowledgeStore()` solleva e
    l'add-on **non parte**.

    Non e' il percorso normale (chi viene dalla 3.45 non puo' avere la riga
    nuova), ma questo archivio e' fatto per essere corretto a mano, e una
    migrazione che uccide l'avvio per una chiave duplicata non e' accettabile.

    Mutazione ESEGUITA: togliere la guardia -- rossa, `IntegrityError`.
    """
    from hiris.app.mind.knowledge import KnowledgeStore
    from hiris.app.storage import connect

    db = str(tmp_path / "sapere.db")
    vecchio = KnowledgeStore(db)
    for campo, valore in ((rt.UNDERSTOOD_FIELD, "la ricetta non ha nessun passo"),
                          (rt.DECLINED_FIELD, "gia declinata, a mano")):
        vecchio.write(Fact(
            subject_kind="dispositivo", subject="dev1", field=campo,
            value=valore, provenance="dedotto",
            evidence='il modello ha risposto: {"why": "niente da misurare", "steps": []}',
            source=f"{rt.REFUSAL_SOURCE}{rt.REGISTRY_VERSION}",
            who="modello (ponte)", when_ts=1789000000.0))
    vecchio.close()
    conn = connect(db)
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()

    nuovo = KnowledgeStore(db)   # non deve sollevare
    try:
        # Quella scritta a mano vince: e' del proprietario, non nostra.
        assert nuovo.get("dispositivo", "dev1", rt.DECLINED_FIELD).value == "gia declinata, a mano"
        assert nuovo.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None
    finally:
        nuovo.close()


# -- la ricetta si ripara nel suo giro (attori, Task 1.6; D2) -----------------
#
# Mutazioni ESEGUITE (05/10/2026), ognuna rossa per la ragione giusta e
# ripristinata (`git status`): «ferma» ammessa fra le cause riparabili; la
# riparazione che non esclude le entita' mute dalla validazione; la ricetta
# vecchia cancellata da una risposta storta; la guardia del «non capito» tolta;
# `who_to_ask` che torna sempre il primo.


def _casa_viva(spenta: bool = False) -> House:
    """L'inverter con due entita' vive e una SPARITA (nel registro, senza
    stato); la lavatrice con un'entita' spenta dal proprietario, se chiesto.
    Le entita' con statistiche le dice `with_series` di ogni prova."""
    entita = [
        {"id": "sensor.prodotta", "nome": "Energia prodotta oggi",
         "dispositivo_id": "dev1", "classe": "energy", "unita": "kWh"},
        {"id": "sensor.consumata", "nome": "Energia consumata oggi",
         "dispositivo_id": "dev1", "classe": "energy", "unita": "kWh"},
        {"id": "sensor.vecchia", "nome": "Energia (vecchia)",
         "dispositivo_id": "dev1", "classe": "energy", "unita": "kWh"},
        {"id": "sensor.lavatrice", "nome": "Lavatrice energia",
         "dispositivo_id": "dev2", "classe": "energy", "unita": "kWh",
         **({"disabilitata": 1, "disabilitata_da": "user"} if spenta else {})},
    ]
    stati = {"sensor.prodotta": "1.0", "sensor.consumata": "2.0",
             "sensor.lavatrice": "3.0"}
    return House({"dispositivi": [{"id": "dev1", "nome": "Inverter ZCS"},
                                  {"id": "dev2", "nome": "Lavatrice"}],
                  "entita": entita}, Mirror(state=stati))


SERIE_VIVE = {"sensor.prodotta", "sensor.consumata", "sensor.lavatrice"}


def _ricetta(*entita):
    return {"why": "pesa", "steps": [
        {"name": e.split(".")[1], "operation": "somma_periodo",
         "inputs": [f"@{e}"], "params": {"unit": "kWh"}} for e in entita]}


def _scrivi(sapere, house, device_id, ricetta, when_ts=1789000000.0):
    esito = rt.apply_recipe(sapere, house, device_id, json.dumps(ricetta),
                            who="x", when_ts=when_ts)
    assert esito["scritta"], esito


def test_una_ricetta_su_un_entita_SPARITA_torna_una_domanda_e_dice_perche(sapere):
    """Il caso del piano: una ricetta i cui passi rifiutano per una causa
    riparabile torna fra le domande, e la domanda dice PERCHE'. Fino al
    05/10/2026 nessuno la riparava: l'attuatore, che lo faceva, e' in pausa.
    La ricetta vecchia NON si cancella: resta finche' la nuova non e' valida."""
    casa = _casa_viva()
    _scrivi(sapere, casa, "dev1", _ricetta("sensor.prodotta", "sensor.vecchia"))

    rotte = rt.recipes_to_repair(sapere, casa, with_series=SERIE_VIVE)

    assert set(rotte) == {"dev1"}
    assert {e: r.cause for e, r in rotte["dev1"].silent.items()} == {
        "sensor.vecchia": "sparita"}
    assert not rotte["dev1"].dashboard_changed
    domanda = rt.build_device_question("risparmiare", casa, "dev1",
                                       with_series=SERIE_VIVE, repair=rotte["dev1"])
    blocco = domanda.split("non funziona piu'", 1)[1]
    assert "sensor.vecchia" in blocco and "non ha uno stato" in blocco
    assert rt.recipes(sapere).get("dev1") is not None


def test_le_cause_riparabili_sono_una_lista_chiusa_del_vocabolario():
    """Ogni causa riparabile sta nel vocabolario unico (chiesto, non ricopiato);
    `ferma` e le spente NON ci stanno: una fonte muta non si aggira con una
    ricetta nuova, e una richiesta per lei sarebbe un giro del modello buttato
    a ogni passaggio (revisione del piano, punto 4)."""
    assert set(rt.REPAIRABLE_CAUSES) <= CAUSES
    for cause in sorted(CAUSES):
        refusal = NotComputable("perche' si", cause=cause)
        assert rt.repairable(refusal, {"causa": None}) == (cause in rt.REPAIRABLE_CAUSES)
    for mute in (FROZEN, "spenta_dal_proprietario", "integrazione_ferma"):
        assert not rt.repairable(NotComputable("x", cause=mute), {"causa": None})


def test_ricreata_si_ripara_irraggiungibile_no():
    """`non_disponibile` vale due fatti: con `restored` nessuna integrazione
    l'ha aggiunta (tolta, o ricreata con un altro id) e una ricetta nuova la
    aggira; senza, il dispositivo e' solo irraggiungibile e torna da se'."""
    muta = NotComputable("x", cause="non_disponibile")
    assert rt.repairable(muta, {"causa": "restored"})
    assert not rt.repairable(muta, {"causa": "unavailable"})


def test_una_ricetta_su_un_entita_SPENTA_dal_proprietario_non_torna(sapere):
    """Il confine: spenta e' una decisione, non un guasto della ricetta."""
    scritta = _casa_viva()
    _scrivi(sapere, scritta, "dev2", _ricetta("sensor.lavatrice"))
    spenta = _casa_viva(spenta=True)

    assert rt.recipes_to_repair(sapere, spenta,
                                with_series=SERIE_VIVE - {"sensor.lavatrice"}) == {}


def test_senza_sapere_chi_ha_una_serie_non_si_ripara_NIENTE(sapere):
    """`None` vuol dire «non l'abbiamo potuto chiedere»: su quel silenzio non
    si richiede nessuna ricetta della casa (lo diceva gia' la potatura che
    questa funzione sostituisce)."""
    casa = _casa_viva()
    _scrivi(sapere, casa, "dev1", _ricetta("sensor.prodotta", "sensor.vecchia"))

    assert rt.recipes_to_repair(sapere, casa, with_series=None) == {}


def test_la_riparazione_RIFIUTA_una_ricetta_che_nomina_ancora_l_entita_muta(sapere):
    """Una riparazione non deve produrre una ricetta rotta per la stessa
    causa, che tornerebbe a ogni giro: la validazione esclude le entita' che
    la domanda ha dichiarato mute. E una risposta storta NON cancella la
    ricetta di adesso (calcola ancora `prodotta`): il «non capito» le si
    scrive accanto, e ferma la riparazione fino al prossimo registro."""
    casa = _casa_viva()
    _scrivi(sapere, casa, "dev1", _ricetta("sensor.prodotta", "sensor.vecchia"))
    rotte = rt.recipes_to_repair(sapere, casa, with_series=SERIE_VIVE)

    esito = rt.apply_recipe(sapere, casa, "dev1",
                            json.dumps(_ricetta("sensor.consumata", "sensor.vecchia")),
                            who="x", when_ts=1789000100.0,
                            repairing=frozenset(rotte["dev1"].silent))

    assert not esito["scritta"]
    assert any("sensor.vecchia" in p for p in esito["problemi"])
    assert rt.recipes(sapere)["dev1"] == _ricetta("sensor.prodotta", "sensor.vecchia")
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is not None
    assert rt.recipes_to_repair(sapere, casa, with_series=SERIE_VIVE) == {}, (
        "una riparazione fallita contro questo registro si richiede a ogni giro")


def test_una_riparazione_VALIDA_sostituisce_e_non_torna_piu(sapere):
    casa = _casa_viva()
    _scrivi(sapere, casa, "dev1", _ricetta("sensor.prodotta", "sensor.vecchia"))

    esito = rt.apply_recipe(sapere, casa, "dev1",
                            json.dumps(_ricetta("sensor.prodotta", "sensor.consumata")),
                            who="x", when_ts=1789000100.0,
                            repairing=frozenset({"sensor.vecchia"}))

    assert esito["scritta"]
    assert rt.recipes_to_repair(sapere, casa, with_series=SERIE_VIVE) == {}
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None


def test_una_ricetta_TUTTA_muta_non_si_tiene_davanti_a_una_risposta_storta(sapere):
    """Il caso che `drop_recipes_without_series` copriva: nessuna entita' della
    ricetta da' una serie. Tenerla non vale niente -- non calcola -- e una
    risposta storta la sostituisce col suo «non capito», come una domanda
    nuova."""
    casa = _casa_viva()
    _scrivi(sapere, casa, "dev1", _ricetta("sensor.vecchia"))

    rt.apply_recipe(sapere, casa, "dev1", "non saprei", who="x",
                    when_ts=1789000100.0, repairing=frozenset({"sensor.vecchia"}))

    assert rt.recipes(sapere).get("dev1") is None
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is not None


def test_una_risposta_nuova_CANCELLA_quella_vecchia(sapere):
    """**Un dispositivo non puo' essere «non capito» e avere una ricetta che
    gira ogni notte.**

    Trovato dalla revisione indipendente il 15/09/2026: `apply_recipe`
    scriveva il suo campo e lasciava gli altri due dov'erano. Il giorno in cui
    un rifiuto scade e il modello risponde bene, la riga vecchia resta -- e la
    **porta del sapere** continua a elencare quel dispositivo fra i «non
    capiti», cioe' fra le cose su cui il proprietario dovrebbe intervenire,
    mentre non c'e' piu' niente da fare.

    `devices_to_ask` era corretto (la ricetta vince); era la pagina a mentire.

    Mutazione ESEGUITA: non cancellare le risposte vecchie -- rossa.
    """
    rt.apply_recipe(sapere, CASA, "dev1", "non saprei", who="x",
                    when_ts=1789000000.0)
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is not None

    rt.apply_recipe(sapere, CASA, "dev1", json.dumps(RICETTA_BUONA),
                    who="x", when_ts=1789000100.0)

    assert rt.recipes(sapere).get("dev1") is not None
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None, (
        "un dispositivo capito non resta fra i «non capiti» della pagina")


def test_un_rifiuto_ragionato_cancella_il_NON_CAPITO_di_prima(sapere):
    """L'altro verso: il modello aveva sbagliato la risposta, ora dice
    ragionatamente che non c'e' niente da misurare. Restano due righe che
    dicono due cose diverse dello stesso dispositivo.

    Mutazione ESEGUITA: cancellare solo quando si scrive una ricetta -- rossa.
    """
    rt.apply_recipe(sapere, CASA, "dev1", "non saprei", who="x",
                    when_ts=1789000000.0)

    rt.apply_recipe(sapere, CASA, "dev1", json.dumps(RIFIUTO_RAGIONATO),
                    who="x", when_ts=1789000100.0)

    assert sapere.get("dispositivo", "dev1", rt.DECLINED_FIELD) is not None
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None


def test_a_chi_chiedere_RUOTA_e_un_dispositivo_storto_non_affama_gli_altri():
    """**Chiedere sempre al primo della lista e' una trappola**, trovata dalla
    revisione indipendente il 15/09/2026 e diventata attuale il giorno dopo:
    con 31 dispositivi in coda, se al primo la risposta non arriva -- il
    modello solleva, il ponte torna una decisione vuota -- non si scrive
    niente, e il giro successivo ripesca **lo stesso**. Per sempre. Gli altri
    trenta non vengono chiesti mai.

    Il freno che esiste (`_troppo_presto_per_richiedere`) guarda solo la coda
    del ponte: rallenta a un giro all'ora, non cambia dispositivo.

    Si ruota. Il contatore vive in memoria e riparte da capo al riavvio: non e'
    una promessa di equita' perfetta, e' la garanzia che **nessuno resti
    dietro a uno rotto**.

    Mutazione ESEGUITA: tornare a `to_ask[0]` -- rossa.
    """
    coda = ["dev1", "dev2", "dev3"]

    chiesti = [rt.who_to_ask(coda, giro)[0] for giro in range(6)]

    assert chiesti == ["dev1", "dev2", "dev3", "dev1", "dev2", "dev3"]


def test_la_rotazione_regge_una_coda_che_si_accorcia():
    """I dispositivi escono dalla coda man mano che rispondono, e il contatore
    non torna indietro: si prende il resto, non l'indice.

    Mutazione ESEGUITA: `to_ask[giro]` senza il modulo -- rossa, `IndexError`.
    """
    assert rt.who_to_ask(["dev1"], 7) == ("dev1", 8)
    assert rt.who_to_ask([], 7) == (None, 7)


def test_IL_PONTE_dichiara_di_saper_ragionare_questa_specie():
    """**La prova che mancava, e che il difetto del 13/09 ha reso necessaria.**

    Chi produce un turno e chi lo serve sono due moduli diversi, e il secondo
    dichiara per conto suo quali specie sa ragionare (`agent/runner.RAGIONABILI`).
    Accodarne una che lui non conosce non fallisce: produce una decisione vuota
    e un avviso nel log -- cioe' un guasto silenzioso che si vede solo dal vivo,
    ed e' cosi' che questo e' stato trovato.

    Mutazione ESEGUITA: togliere `_RECIPE_KIND` da `RAGIONABILI` -- rossa.
    """
    from hiris.app.agent.runner import RAGIONABILI

    assert rt.RECIPE_TURN_KIND in RAGIONABILI


def test_un_turno_di_ricetta_NON_riceve_gli_strumenti():
    """**E' una questione di sicurezza, non di eleganza.** Senza questa riga la
    sonda girerebbe col catalogo della chat -- `execute` compreso, la porta con
    cui HIRIS accende, spegne e chiama un servizio -- e un turno che deve solo
    proporre dei conti potrebbe agire sulla casa senza che nessun si' lo
    autorizzi.

    E' il rilievo che la review indipendente aveva chiuso per lo scope
    l'11/09/2026, e che il turno delle ricette avrebbe riaperto.

    Mutazione ESEGUITA: togliere `_RECIPE_KIND` da `_SELF_CONTAINED_KINDS` -- rossa.
    """
    from hiris.app.agent.runner import _SELF_CONTAINED_KINDS

    assert rt.RECIPE_TURN_KIND in _SELF_CONTAINED_KINDS


# -- i rifiuti sono importanti, e non sono definitivi -----------------------

def test_un_rifiuto_SCADE_quando_il_registro_cresce(sapere):
    """**Decisione del proprietario, 13/09/2026: «i rifiuti sono importanti».**

    Un dispositivo che oggi il modello non sa misurare puo' diventare
    misurabile domani per una ragione che non ha niente a che vedere con lui:
    il registro delle operazioni cresce. Il giorno in cui arriva il mattone che
    mancava, ogni «non capito» deciso contro un registro piu' povero e' un
    giudizio da rifare, non un verdetto.

    E' anche il primo LETTORE di `VERSIONE_REGISTRO`, che fino a oggi era un
    numero scritto e mai interrogato.

    Mutazione ESEGUITA: far tornare `_ancora_valido` sempre `True` -- rossa,
    il dispositivo resta condannato per sempre.
    """
    from hiris.app.mind.knowledge import Fact

    sapere.write(Fact(
        subject_kind="dispositivo", subject="dev1", field=rt.UNDERSTOOD_FIELD,
        value="non ci riesco", provenance="dedotto", evidence="x",
        source=f"{rt.REFUSAL_SOURCE}0",  # un registro piu' vecchio
        verification="non_capito", who="x", when_ts=1789000000.0))

    assert rt.devices_to_ask(sapere, CASA, {"sensor.prodotta"}) == ["dev1"]


def test_un_rifiuto_del_registro_CORRENTE_vale_ancora(sapere):
    """L'altra meta': finche' il registro e' quello, la domanda e' gia' stata
    fatta e non si ripete."""
    rt.apply_recipe(sapere, CASA, "dev1", "non saprei", who="x",
                    when_ts=1789000000.0)

    assert rt.devices_to_ask(sapere, CASA, {"sensor.prodotta"}) == []


def test_un_rifiuto_porta_COSA_HA_DETTO_il_modello(sapere):
    """Senza, il proprietario legge «l'entita' non e' fra quelle consegnate» e
    non puo' sapere se il modello avesse capito il dispositivo e sbagliato un
    identificatore, o non avesse capito niente. Sono due cose diverse, e la
    seconda la risolve lui in dieci secondi.

    Mutazione ESEGUITA: rimettere `evidence` a una frase generica -- rossa.
    """
    rt.apply_recipe(sapere, CASA, "dev1",
                    "credo sia un contatore dell'acqua ma non ne sono sicuro",
                    who="x", when_ts=1789000000.0)

    riga = sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD)
    assert "contatore dell'acqua" in riga.evidence

def test_il_catalogo_NON_offre_al_modello_cio_che_una_ricetta_non_puo_scrivere():
    """Il modello ha scritto la sua prima ricetta il 14/09/2026 usando
    `episodio`, e non e' colpa sua: gliel'avevamo messa nell'elenco. Offrire
    un'operazione che il validatore rifiutera' sempre brucia un giro e lascia
    il dispositivo senza ricetta per sempre (`devices_to_ask` non richiede chi
    una risposta l'ha gia' data).

    Mutazione: togliere il filtro `offerable` da `_operations_catalogue` --
    rossa.
    """
    catalogo = rt._operations_catalogue()
    assert "episodio" not in catalogo
    # `tempo_in_stato` una ricetta saprebbe NOMINARLA, ma non saprebbe
    # consegnarle un periodo -- nessuna operazione offribile ne produce uno.
    # Offrirla sarebbe la stessa trappola, un anello piu' in la'.
    assert "tempo_in_stato" not in catalogo
    assert "somma_periodo" in catalogo


def test_il_catalogo_DICE_quali_parametri_sono_obbligatori():
    """Elencare l'operazione senza dire cosa pretende e' meta' informazione: il
    modello scrive `somma_periodo` senza `unit`, il validatore rifiuta, e il
    giro e' bruciato lo stesso. I parametri si leggono dalla FIRMA, quindi
    l'elenco non puo' divergere da cio' che il motore chiede davvero.

    Mutazione: non scrivere i parametri obbligatori nel catalogo -- rossa.
    """
    catalogo = rt._operations_catalogue()
    riga = [r for r in catalogo.splitlines() if r.startswith("- `somma_periodo`")]
    assert riga, catalogo
    # **`"unit" in riga` NON basta, e la mutazione l'ha dimostrato**: la riga
    # contiene gia' «l'unita' del contatore» fra gli ingressi, e `unit` ne e'
    # un pezzo. Il test passava anche togliendo del tutto i parametri dal
    # catalogo -- un test che non puo' fallire. Si asserisce la FRASE che li
    # annuncia e il nome fra backtick, che e' la forma in cui li scriviamo.
    assert "parametri obbligatori" in riga[0], riga[0]
    assert "`unit`" in riga[0], riga[0]
    # E un'operazione senza parametri obbligatori non si porta dietro una
    # formula vuota: sarebbe rumore su diciassette righe su diciotto.
    riga_quota = [r for r in catalogo.splitlines() if r.startswith("- `quota`")]
    assert "parametri obbligatori" not in riga_quota[0], riga_quota


def test_sul_PONTE_la_riparazione_arriva_fino_alla_raccolta(sapere, tmp_path):
    """Il ponte risponde minuti dopo, da un altro processo: le entita' che la
    risposta non puo' nominare viaggiano nella sveglia del turno, e chi
    raccoglie le applica come la catena. Senza, sul ponte una riparazione
    accetterebbe di nuovo l'entita' muta e tornerebbe a ogni giro.

    Mutazione ESEGUITA: la raccolta che non legge `riparare` dalla sveglia --
    rossa (la ricetta con `sensor.vecchia` viene scritta)."""
    import time

    from hiris.app import server
    from hiris.app.reasoning.queue import ReasoningQueue

    casa = _casa_viva()
    _scrivi(sapere, casa, "dev1", _ricetta("sensor.prodotta", "sensor.vecchia"))
    rotte = rt.recipes_to_repair(sapere, casa, with_series=SERIE_VIVE)
    coda = ReasoningQueue(str(tmp_path / "coda.db"))
    app = {"reasoning_queue": coda, "models_config": {"ponte": {"scadenza_min": 10}}}

    server._enqueue_recipe_turn(app, casa, "dev1", objective="risparmiare",
                                with_series=SERIE_VIVE, repair=rotte["dev1"])
    preso = coda.claim(time.time())
    assert preso["wake"]["riparare"] == ["sensor.vecchia"]
    assert "non funziona piu'" in preso["context"]["history"][0]["content"]
    coda.submit(preso["job_id"], preso["nonce"],
                {"reply": json.dumps(_ricetta("sensor.consumata", "sensor.vecchia"))},
                time.time())

    esito = server._collect_recipe_turn(app, sapere, casa)

    assert not esito["scritta"]
    assert rt.recipes(sapere)["dev1"] == _ricetta("sensor.prodotta", "sensor.vecchia")


def test_sul_PONTE_un_turno_FALLITO_non_scrive_un_non_capito(sapere, tmp_path):
    """Un turno che il ponte ha fallito (`[runner non disponibile]`, esito
    `fallito`) non e' la risposta del modello. Letto come tale finiva nel
    «non capito», e un dispositivo che il modello non ha saputo leggere non
    si richiede mai piu' (`devices_to_ask`): il guasto del ponte di una notte
    lo toglieva dalle domande per sempre.

    Mutazione ESEGUITA: la raccolta che legge la `reply` senza l'esito --
    rossa (il «non capito» viene scritto)."""
    import time

    from hiris.app import server
    from hiris.app.reasoning.queue import ReasoningQueue

    casa = _casa_viva()
    coda = ReasoningQueue(str(tmp_path / "coda.db"))
    app = {"reasoning_queue": coda, "models_config": {"ponte": {"scadenza_min": 10}}}
    server._enqueue_recipe_turn(app, casa, "dev1", objective="risparmiare",
                                with_series=SERIE_VIVE)
    preso = coda.claim(time.time())
    coda.submit(preso["job_id"], preso["nonce"],
                {"reply": "[runner non disponibile]", "tools_called": [],
                 "outcome": "fallito"}, time.time())

    esito = server._collect_recipe_turn(app, sapere, casa)

    assert esito["risposta"] is False
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None


@pytest.mark.asyncio
async def test_sulla_CATENA_la_frase_del_router_non_scrive_un_non_capito(sapere):
    """Il gemello sulla catena del caso qui sopra (rilievo G29-1, 06/10/2026).
    Quando tutti i backend rifiutano, il router non solleva: consegna una
    frase per la chat (l'errore dell'ultimo backend, o «Tutti i provider AI
    non disponibili...») e alza `last_unanswered`. Letta come risposta del
    modello finiva nel «non capito», e il dispositivo usciva dalle domande
    per sempre.

    Il router e' quello vero, con backend che rifiutano come i veri
    (`RunnerBackendError`): la prova non ricopia la frase, la ottiene.

    Mutazioni ESEGUITE, entrambe rosse (il «non capito» viene scritto, con
    la frase del router come evidenza): `steering.chain_answer` che
    restituisce `answer` anche quando il turno non ha risposto;
    `misura_turno` che non abbassa `TurnOutcome.answered`."""
    from unittest.mock import AsyncMock, MagicMock

    from hiris.app.claude_runner import RunnerBackendError
    from hiris.app.llm_router import LLMRouter

    def _rifiuta(messaggio):
        runner = MagicMock()
        runner.chat = AsyncMock(side_effect=RunnerBackendError(messaggio))
        return runner

    router = LLMRouter(claude=_rifiuta("giu'"), openrouter=_rifiuta("giu'"),
                       strategy="balanced")

    esito = await rt.ask(router, sapere, _casa_viva(), "dev1",
                         objective="risparmiare", who="prova",
                         when_ts=1_758_000_000.0, with_series=SERIE_VIVE)

    assert router.last_unanswered is True
    assert esito["scritta"] is False
    assert sapere.get("dispositivo", "dev1", rt.UNDERSTOOD_FIELD) is None
