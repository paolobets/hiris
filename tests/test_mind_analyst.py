"""L'analista (spec §10): legge i resoconti e dice cosa si potrebbe fare.

**Il codice calcola, il modello sceglie.** Qui vive solo la prima meta': valore,
storia, scostamento, copertura. Cosa merita di essere detto lo decide il
modello, e questo modulo non lo sa e non deve saperlo.
"""

from hiris.app.mind import analyst as an


def _serie(valori, **extra):
    riga = {"soggetto": "dev1", "nome": "Inverter", "misura": "produzione",
            "chiave": None, "operazione": "somma_periodo", "unita": "kWh",
            "valori": list(valori), "coperture": [1.0] * len(valori),
            "perche": []}
    riga.update(extra)
    return {"giorni": [f"2026-09-{i + 1:02d}" for i in range(len(valori))],
            "obiettivi": [], "serie": [riga]}


def test_lo_scostamento_si_misura_contro_la_STORIA_di_quel_dato():
    """***\u00abNon si inventa una soglia: si archivia e si interpreta\u00bb*** (spec
    §10, 09/09). Il numero di oggi non si confronta con un valore scelto da
    noi: si confronta con **cio' che quel dato ha fatto finora**.

    Mutazione: confrontare con una costante scritta nel codice -- rossa.
    """
    esito = an.with_deviation(_serie([10.0, 12.0, 9.0, 11.0, 30.0]))
    s = esito["serie"][0]["scostamento"]
    assert s["ultimo"] == 30.0
    assert s["mediana"] == 10.5
    assert s["base"] == 4, "la storia sono i giorni PRIMA dell'ultimo"
    assert s["quanti_scarti"] is not None and s["quanti_scarti"] > 0


def test_la_MEDIANA_e_non_la_media_regge_a_un_giorno_storto():
    """Con venti punti un solo giorno storto sposta la media e nasconde tutto
    il resto. La mediana no, ed e' per questo che la storia si riassume cosi'.

    Mutazione: usare la media -- rossa (la mediana resta 10, la media sarebbe
    ~28).
    """
    esito = an.with_deviation(_serie([10.0, 10.0, 10.0, 100.0, 10.0, 11.0]))
    assert esito["serie"][0]["scostamento"]["mediana"] == 10.0


def test_una_storia_PIATTA_che_oggi_cambia_e_il_primo_innesco_non_un_rifiuto_muto():
    """**Difetto di disegno preso durante la scrittura.** Quattro giorni
    identici e poi un salto: lo scarto della storia è zero, quindi «quanti
    scarti» non si può dividere -- ma e' il segnale **piu' forte che esista**,
    il primo innesco: *«qualcosa e' cambiato»*. Rifiutarlo con «non varia mai»
    direbbe il contrario di quello che e' successo.

    Due fatti diversi, due ragioni diverse. Il numero resta non calcolabile --
    dividere per zero sarebbe inventarlo -- ma la frase dice **cos'e'
    successo**, e mediana e ultimo sono li' per leggerne la differenza.

    Mutazione: dare a questo caso la stessa ragione di quello piatto -- rossa.
    """
    esito = an.with_deviation(_serie([10.0, 10.0, 10.0, 10.0, 20.0]))
    s = esito["serie"][0]["scostamento"]
    assert s["quanti_scarti"] is None
    assert s["mediana"] == 10.0 and s["ultimo"] == 20.0
    assert "identica" in s["non_calcolabile"], s["non_calcolabile"]
    assert "non varia mai" not in s["non_calcolabile"]


def test_una_storia_che_NON_VARIA_MAI_non_da_uno_scostamento_e_lo_DICE():
    """**E il rifiuto E' il secondo innesco.** Se lo scarto e' zero, qualunque
    differenza diviso zero sarebbe infinito: non si inventa un numero. Ma
    \u00abquesta cosa non varia mai\u00bb e' precisamente cio' che la spec chiede di
    notare -- *\u00abqualcosa e' stabile e costa\u00bb*, la batteria satura al 90% dalle
    13 alle 16 mentre l'impianto produce ancora 3.000 W: nessuna variazione, e
    il costo piu' alto di tutta la prova.

    Mutazione: tornare `0.0` invece del rifiuto -- rossa.
    """
    esito = an.with_deviation(_serie([5.0, 5.0, 5.0, 5.0, 5.0]))
    s = esito["serie"][0]["scostamento"]
    assert s["quanti_scarti"] is None
    assert "non varia" in s["non_calcolabile"]
    assert s["mediana"] == 5.0, "la mediana c'e' lo stesso: e' il valore stabile"


def test_una_storia_troppo_CORTA_lo_dice_invece_di_fingere():
    """Due punti non sono una storia. Un numero calcolato su due giorni con la
    faccia di uno calcolato su trenta e' il difetto che questo prodotto vieta.

    Mutazione: calcolare comunque -- rossa.
    """
    esito = an.with_deviation(_serie([10.0, 20.0]))
    s = esito["serie"][0]["scostamento"]
    assert s["quanti_scarti"] is None
    # **`"storia" in ragione` NON basta, e l'ha detto la mutazione**: anche la
    # ragione della storia piatta contiene «la storia e' identica», quindi il
    # test restava verde togliendo del tutto la guardia sulla base. Si asserisce
    # il NUMERO, che e' l'unica cosa che quella guardia produce.
    assert f"sotto {an.MINIMUM_HISTORY}" in s["non_calcolabile"], s["non_calcolabile"]
    assert s["base"] == 1
    # E la mediana c'e' lo stesso: e' cio' che si sa, e «la base e' sottile»
    # e' un numero da consegnare, non una ragione per tacere.
    assert s["mediana"] == 10.0


def test_la_BASE_si_dice_sempre_perche_con_ventotto_giorni_e_sottile():
    """*\u00abCon 28 giorni di storia va detto che la base e' sottile\u00bb* (§10). Non
    e' una soglia da applicare: e' un numero da consegnare al modello, che
    decide quanto pesarlo. Quindi `base` c'e' **sempre**, anche quando lo
    scostamento si calcola benissimo.

    Mutazione: mettere `base` solo nei rifiuti -- rossa.
    """
    esito = an.with_deviation(_serie([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert esito["serie"][0]["scostamento"]["base"] == 4


def test_i_giorni_SENZA_valore_non_contano_nella_storia():
    """Un buco non e' uno zero. Contarlo abbasserebbe la mediana di una misura
    che semplicemente non si e' potuta calcolare -- e la copertura che crolla
    e' gia' il terzo innesco, detto altrove.

    Mutazione: trattare `None` come zero -- rossa.
    """
    esito = an.with_deviation(_serie([10.0, None, 10.0, None, 12.0]))
    s = esito["serie"][0]["scostamento"]
    assert s["base"] == 2
    assert s["mediana"] == 10.0


def test_un_valore_che_NON_E_UN_NUMERO_non_ha_uno_scostamento():
    """`tendenza.verso` vale \u00abin salita\u00bb: non si sottrae. Si dice, invece di
    saltare la riga -- saltarla toglierebbe all'analista una serie che potrebbe
    volere lo stesso.

    Mutazione: sollevare, o omettere la riga -- rossa.
    """
    esito = an.with_deviation(_serie(["in salita", "in salita", "piatta"],
                                     chiave="verso", operazione="tendenza"))
    s = esito["serie"][0]["scostamento"]
    assert s["quanti_scarti"] is None
    assert "numero" in s["non_calcolabile"]


def test_with_deviation_NON_tocca_il_resto_della_serie():
    """Aggiunge una chiave e non riscrive niente: i valori, le coperture e i
    buchi restano quelli che erano, o due letture della stessa storia
    direbbero cose diverse.

    Mutazione: ricostruire le righe da capo -- rossa se perde `perche`.
    """
    prima = _serie([1.0, 2.0])
    prima["serie"][0]["perche"] = [{"dal": "x", "al": "x", "ragione": "y"}]
    dopo = an.with_deviation(prima)
    riga = dopo["serie"][0]
    assert riga["valori"] == [1.0, 2.0]
    assert riga["perche"] == [{"dal": "x", "al": "x", "ragione": "y"}]
    assert dopo["giorni"] == prima["giorni"]
