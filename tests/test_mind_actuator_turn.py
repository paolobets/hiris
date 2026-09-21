"""Il turno dell'attuatore (spec 2026-09-21 §2): due gesti nella risposta.

Gemello di `test_mind_analyst_turn.py`, e per la stessa ragione: il modello
dice cosa ha trovato e cosa propone, il codice valida e rifiuta. Una risposta
storta non si corregge -- si rifiuta, e il giro dopo riprova.

**Due gesti nella risposta, tre nell'archivio**: indagine e proposta le
rivendica il modello; la riparazione la fa il codice, e lasciargliela
dichiarare vorrebbe dire lasciargli dichiarare una cosa non avvenuta.
"""
import json

from hiris.app.mind import actuator_turn as at


def _osservazioni():
    return [{"soggetto": "dev1", "misura": "prelievo", "chiave": None, "innesco": 1,
             "base": 19, "cosa": "il prelievo si stacca dal solito",
             "cosa_cambierebbe": "spostare i consumi nelle ore di sole"},
            {"soggetto": "dev2", "misura": "consumo", "chiave": None, "innesco": 3,
             "base": 0, "cosa": "la misura non si calcola piu'",
             "cosa_cambierebbe": "ripristinare il calcolo"}]


def _risposta(*esiti):
    return json.dumps({"esiti": list(esiti)})


def test_senza_osservazioni_non_si_fa_NESSUNA_domanda():
    """Un turno senza niente da chiedere e' un giro del modello per una
    risposta che non puo' esistere. Stessa regola di
    `recipe_turn.build_device_question` con un dispositivo senza entita'.

    Mutazione: tornare sempre una domanda -- rossa."""
    assert at.build_question([], []) is None


def test_la_domanda_porta_l_osservazione_E_cosa_cambierebbe():
    """Senza `cosa_cambierebbe` il modello non saprebbe cosa l'analista ha
    gia' concluso, e rifarebbe il suo lavoro.

    Mutazione: comporre la domanda con la sola `cosa` -- rossa."""
    domanda = at.build_question(_osservazioni(), [])

    assert "il prelievo si stacca dal solito" in domanda
    assert "spostare i consumi nelle ore di sole" in domanda


def test_la_domanda_NUMERA_le_osservazioni():
    """Il modello si riferisce a un'osservazione col suo numero, non
    ricopiandone il testo: ricopiare vorrebbe dire poterlo sbagliare, e un
    esito attaccato all'osservazione sbagliata e' peggio di nessun esito.

    Mutazione: togliere i numeri dalla domanda -- rossa."""
    domanda = at.build_question(_osservazioni(), [])

    assert "0" in domanda and "1" in domanda


def test_le_ricette_GIA_RIPARATE_si_dicono_al_modello():
    """La riparazione avviene prima della domanda: se il modello non lo
    sapesse, proporrebbe di riparare una cosa gia' riparata.

    Mutazione: non passare le riparazioni nella domanda -- rossa."""
    domanda = at.build_question(_osservazioni(),
                                [{"soggetto": "dev2", "misura": "consumo"}])

    assert "dev2" in domanda
    assert "consumo" in domanda


def test_una_risposta_che_nomina_un_osservazione_INESISTENTE_si_rifiuta():
    """Stessa disciplina dell'analista: si rifiuta per intero, non si corregge.

    Mutazione: accettare un indice fuori elenco -- rossa (un esito attaccato
    al nulla)."""
    esito = at.apply_actuation(_osservazioni(),
                               _risposta({"osservazione": 9, "gesto": "indagine",
                                          "trovato": "niente"}))

    assert esito["attuazione"] is None
    assert esito["problemi"]


def test_un_GESTO_fuori_dai_due_si_rifiuta():
    """I gesti della risposta sono due e chiusi. Un terzo sarebbe un potere che
    nessuno ha dato a questo attore, e arriverebbe dentro una risposta.

    Mutazione: ammettere qualunque parola -- rossa."""
    esito = at.apply_actuation(_osservazioni(),
                               _risposta({"osservazione": 0, "gesto": "spegni",
                                          "trovato": "fatto"}))

    assert esito["attuazione"] is None


def test_un_INDAGINE_senza_cosa_ha_trovato_si_rifiuta():
    """Un'indagine che non dice cosa ha trovato non e' un'indagine: e' un
    turno speso per niente, archiviato come se fosse stato utile.

    Mutazione: rendere `trovato` facoltativo -- rossa."""
    esito = at.apply_actuation(_osservazioni(),
                               _risposta({"osservazione": 0, "gesto": "indagine"}))

    assert esito["attuazione"] is None


def test_un_indagine_COMPLETA_si_accetta():
    """La contropartita: senza di lei, un `apply_actuation` che rifiuta tutto
    passerebbe le tre prove qui sopra.

    Mutazione: rifiutare sempre -- rossa."""
    esito = at.apply_actuation(
        _osservazioni(),
        _risposta({"osservazione": 0, "gesto": "indagine",
                   "trovato": "il prelievo e' avvenuto fra le 19 e le 22"}))

    assert esito["problemi"] == []
    assert esito["attuazione"]["esiti"][0]["trovato"].startswith("il prelievo")


def test_il_SILENZIO_e_un_esito_legittimo_e_si_archivia():
    """«Ho guardato e non c'era niente da fare» e' diverso da «non ho
    guardato», e la differenza si archivia: e' la stessa legge del resoconto
    vuoto e dell'analisi senza osservazioni.

    Mutazione: rifiutare l'elenco vuoto -- rossa."""
    esito = at.apply_actuation(_osservazioni(), json.dumps({"esiti": []}))

    assert esito["attuazione"] == {"esiti": []}
    assert esito["risposta"] is True


def test_una_risposta_ASSENTE_non_e_un_silenzio():
    """Il modello che non risponde e il modello che dice «niente da fare» sono
    due cose diverse: la prima si riprova, la seconda si archivia.

    Mutazione: trattare la risposta vuota come un elenco vuoto -- rossa."""
    esito = at.apply_actuation(_osservazioni(), "")

    assert esito["attuazione"] is None
    assert esito["risposta"] is False


def test_TUTTI_i_problemi_si_dicono_insieme():
    """Dirne uno per giro costringerebbe a rieseguire il turno per scoprire il
    successivo -- e un turno costa.

    Mutazione: `return` al primo problema -- rossa."""
    esito = at.apply_actuation(
        _osservazioni(),
        _risposta({"osservazione": 9, "gesto": "spegni"},
                  {"osservazione": 0, "gesto": "indagine"}))

    assert len(esito["problemi"]) >= 3


def test_una_RIPARAZIONE_dichiarata_dal_MODELLO_si_rifiuta():
    """**Le riparazioni le fa il codice, non il modello.** Il giro riscrive la
    ricetta prima di chiedere, e aggiunge l'esito come FATTO; se il modello
    potesse dichiararne una, potrebbe dichiararne una che non e' avvenuta --
    e sarebbe una bugia archiviata, indistinguibile da un fatto.

    Per questo i gesti che il modello puo' rivendicare sono DUE, e i gesti che
    esistono nell'archivio sono TRE: la differenza e' esattamente il potere
    che non gli e' stato dato.

    Mutazione: rimettere `riparazione` fra i gesti ammessi nella risposta --
    rossa."""
    esito = at.apply_actuation(
        _osservazioni(),
        _risposta({"osservazione": 1, "gesto": "riparazione", "soggetto": "dev2",
                   "trovato": "l'ho riscritta io"}))

    assert esito["attuazione"] is None
    assert any("riparazione" in p for p in esito["problemi"])


def test_i_gesti_dell_ARCHIVIO_sono_tre_e_quelli_della_RISPOSTA_due():
    """La proprieta' detta sui nomi, perche' il giorno in cui qualcuno
    aggiunge un gesto se ne accorga da qui.

    Mutazione: allineare i due elenchi -- rossa."""
    assert set(at.OUTCOME_GESTURES) - set(at.GESTURES) == {"riparazione"}
