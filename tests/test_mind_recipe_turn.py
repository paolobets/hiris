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

    Mutazione: togliere il filtro `in_recipes` da `_operations_catalogue` --
    rossa.
    """
    catalogo = rt._operations_catalogue()
    assert "episodio" not in catalogo
    # E non basta `in_recipes`: `tempo_in_stato` una ricetta saprebbe
    # NOMINARLA, ma non saprebbe consegnarle un periodo -- nessuna operazione
    # offribile ne produce uno. Offrirla sarebbe la stessa trappola, un anello
    # piu' in la'. Mutazione che la uccide: filtrare il catalogo su
    # `in_recipes` invece che su `offerable`.
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
