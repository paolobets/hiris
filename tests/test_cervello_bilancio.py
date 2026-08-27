"""Il bilancio dell'energia: undici frammenti diventano un oggetto solo.

Due meta'. La prima prova `costruisci_corpo_bilancio` -- pura, nessuna
lettura di rete: le statistiche orarie arrivano gia' lette e tradotte
(come le manderebbe `HAClient.statistiche_orarie()`, chiavi italiane). La
seconda prova `aggrega_giorno(bilanci=...)`: il punto per cui questa fetta
esiste -- le entita' di un bilancio VALIDO smettono di produrre il loro
episodio di energia individuale, quelle fuori continuano come prima.
"""
import os

import pytest

from hiris.app.cervello.archivio import ArchivioOsservazioni
from hiris.app.cervello.oggetti import (DIREZIONI_BILANCIO, aggrega_giorno,
                                         costruisci_corpo_bilancio)

G = "2026-08-24"
MEZZANOTTE = 1787522400.0   # 2026-08-23T22:00:00+00:00 = 24/08 00:00 +02:00 Roma


def ts(ore, minuti=0):
    return MEZZANOTTE + ore * 3600 + minuti * 60


@pytest.fixture()
def archivio(tmp_path):
    a = ArchivioOsservazioni(os.path.join(str(tmp_path), "o.db"))
    yield a
    a.close()


def _punto(ora, cambio, media=None):
    """Un punto orario tradotto, come lo manda `HAClient.statistiche_orarie()`."""
    return {"inizio": f"2026-08-24T{ora:02d}:00:00+00:00",
            "fine": f"2026-08-24T{ora + 1:02d}:00:00+00:00",
            "minimo": None, "massimo": None, "media": media,
            "somma": None, "stato": None, "cambio": cambio}


# --------------------------------------------------------------------------
# `costruisci_corpo_bilancio` -- pura.
# --------------------------------------------------------------------------

def test_le_sette_dimensioni_note_diventano_totali_e_forma():
    """**Sette, non sei** (correzione ALTO della review, mandato «il
    bilancio dell'energia», punto 1, 27/08/2026): "consumo" e' entrato in
    `DIREZIONI_BILANCIO` come settimo totale, letto e non piu' derivato
    (vedi `test_cervello_bilancio.py::test_quota_autosufficienza_...`
    sotto per la ragione).

    **`forma[d]` porta l'ORA di ogni punto** (correzione MEDIA, punto 2 del
    mandato): non piu' `[1.0, 2.0]`, ma `[{"ora","valore"}, ...]` -- la
    chiave nuova che la pagina deve conoscere e' `ora`."""
    serie = {f"sensor.{d}": [_punto(6, 1.0), _punto(7, 2.0)] for d in DIREZIONI_BILANCIO}
    entita = {d: f"sensor.{d}" for d in DIREZIONI_BILANCIO}
    provenienza = {d: "dichiarata" for d in DIREZIONI_BILANCIO}

    corpo = costruisci_corpo_bilancio(serie=serie, entita_per_dimensione=entita,
                                      provenienza_per_dimensione=provenienza)

    assert set(corpo["totali"]) == set(DIREZIONI_BILANCIO) == {
        "produzione", "autoconsumo", "immissione", "prelievo", "carica",
        "scarica", "consumo"}
    for d in DIREZIONI_BILANCIO:
        assert corpo["totali"][d] == {"valore": 3.0, "provenienza": "dichiarata"}
        assert corpo["forma"][d] == [
            {"ora": "2026-08-24T06:00:00+00:00", "valore": 1.0},
            {"ora": "2026-08-24T07:00:00+00:00", "valore": 2.0},
        ]


def test_una_dimensione_senza_entita_non_compare():
    """Una dimensione VOLUTA (fra le `DIREZIONI_BILANCIO`) ma senza entita'
    del dispositivo (es. "scarica" su un inverter senza batteria)
    semplicemente non compare -- il chiamante non ha messo niente in
    `entita_per_dimensione` per quella dimensione."""
    serie = {"sensor.produzione": [_punto(6, 5.0)]}
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"produzione": "sensor.produzione"},
        provenienza_per_dimensione={"produzione": "dichiarata"})

    assert set(corpo["totali"]) == {"produzione"}
    assert "scarica" not in corpo.get("totali", {})
    assert "scarica" not in corpo.get("forma", {})


def test_zero_ore_conosciute_toglie_la_dimensione_per_intero():
    """Mai uno zero al posto di "non lo so": un'entita' presente ma con
    `cambio` sempre `None` (nessun dato in tutte le 24 ore) non deve
    produrre un totale di 0.0 -- deve sparire, come se non ci fosse."""
    serie = {"sensor.produzione": [_punto(6, None), _punto(7, None)]}
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"produzione": "sensor.produzione"},
        provenienza_per_dimensione={"produzione": "dichiarata"})

    assert corpo == {}


def test_un_ora_mancante_non_azzera_il_totale():
    """Mutazione ESEGUITA: in `costruisci_corpo_bilancio`, `conosciuti = [p[
    "valore"] for p in punti]` (senza filtrare i `None`) al posto del
    filtro vero -- arrossisce, perche' `sum([1.0, None, 3.0])` solleva
    `TypeError` invece di tornare 4.0. Ripristinato subito dopo (verificato
    a mano, non lasciato nel codice)."""
    serie = {"sensor.produzione": [_punto(6, 1.0), _punto(7, None), _punto(8, 3.0)]}
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"produzione": "sensor.produzione"},
        provenienza_per_dimensione={"produzione": "dichiarata"})

    assert corpo["totali"]["produzione"]["valore"] == 4.0
    assert corpo["forma"]["produzione"] == [
        {"ora": "2026-08-24T06:00:00+00:00", "valore": 1.0},
        {"ora": "2026-08-24T07:00:00+00:00", "valore": None},
        {"ora": "2026-08-24T08:00:00+00:00", "valore": 3.0},
    ]


def test_forma_porta_l_ora_vera_anche_su_una_giornata_bucata():
    """**L'undicesima correzione (mandato «il bilancio dell'energia»,
    punto 1, 27/08/2026): il caso che ha generato il difetto non era nella
    suite.** La curva porta l'ora vera su ogni punto -- difetto gia' chiuso
    -- ma un revisore ha rimesso lo STESSO difetto ricostruendo `ora` come
    "primo istante + indice" (l'indice travestito da ora), e 80 test su 80
    restavano verdi: OGNI giornata finta di questo file era CONTIGUA (ore
    6,7 oppure 6,7,8,9,10), e con un indice contiguo "indice == ora" e
    "ora vera" coincidono per caso.

    Qui non coincidono: Home Assistant OMETTE le ore senza dati, quindi
    questa giornata salta le 10 e le 11 (7, 8, 9, poi 12, 13). Se `ora`
    fosse ricostruita dall'indice, il quarto punto (indice 3) diventerebbe
    "10:00" invece della vera "12:00" -- questo test lo becca, quello
    contiguo sopra no."""
    serie = {"sensor.produzione": [
        _punto(7, 1.0), _punto(8, 2.0), _punto(9, 3.0),
        _punto(12, 4.0), _punto(13, 5.0)]}
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"produzione": "sensor.produzione"},
        provenienza_per_dimensione={"produzione": "dichiarata"})

    assert corpo["forma"]["produzione"] == [
        {"ora": "2026-08-24T07:00:00+00:00", "valore": 1.0},
        {"ora": "2026-08-24T08:00:00+00:00", "valore": 2.0},
        {"ora": "2026-08-24T09:00:00+00:00", "valore": 3.0},
        {"ora": "2026-08-24T12:00:00+00:00", "valore": 4.0},
        {"ora": "2026-08-24T13:00:00+00:00", "valore": 5.0},
    ]


def test_i_momenti_prima_ultima_ora_e_picco_di_produzione():
    serie = {"sensor.produzione": [
        _punto(6, 0.0), _punto(7, 1.0), _punto(8, 5.0), _punto(9, 2.0), _punto(10, 0.0)]}
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"produzione": "sensor.produzione"},
        provenienza_per_dimensione={"produzione": "dichiarata"})

    assert corpo["momenti"]["prima_ora_produzione"] == "2026-08-24T07:00:00+00:00"
    assert corpo["momenti"]["ultima_ora_produzione"] == "2026-08-24T09:00:00+00:00"
    assert corpo["momenti"]["picco_produzione"] == {
        "valore": 5.0, "ora": "2026-08-24T08:00:00+00:00"}


def test_fine_scarica_batteria_e_la_fine_dell_ultima_ora_attiva():
    serie = {"sensor.scarica": [
        _punto(20, 1.0), _punto(21, 0.5), _punto(22, 0.0), _punto(23, 0.0)]}
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"scarica": "sensor.scarica"},
        provenienza_per_dimensione={"scarica": "dedotta"})

    # L'ultima ora ATTIVA e' le 21-22: "fine" e' il confine delle 22:00.
    assert corpo["momenti"]["fine_scarica_batteria"] == "2026-08-24T22:00:00+00:00"


def test_scarica_mai_attiva_non_produce_il_momento():
    serie = {"sensor.scarica": [_punto(6, 0.0), _punto(7, 0.0)]}
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"scarica": "sensor.scarica"},
        provenienza_per_dimensione={"scarica": "dedotta"})
    # Zero ore conosciute (tutte 0.0 sono comunque CONOSCIUTE, non None):
    # la dimensione compare con totale 0.0, ma nessuna ora e' "attiva".
    assert corpo["totali"]["scarica"]["valore"] == 0.0
    assert "fine_scarica_batteria" not in corpo.get("momenti", {})


def test_quota_autoconsumo_da_produzione_e_autoconsumo():
    """Invariata dalla correzione del punto 1: `quota_autoconsumo` non
    assume nessuna identita' fra dimensioni diverse, resta autoconsumo/
    produzione."""
    serie = {
        "sensor.produzione": [_punto(6, 10.0)],
        "sensor.autoconsumo": [_punto(6, 6.0)],
    }
    entita = {"produzione": "sensor.produzione", "autoconsumo": "sensor.autoconsumo"}
    provenienza = {d: "dichiarata" for d in entita}

    corpo = costruisci_corpo_bilancio(serie=serie, entita_per_dimensione=entita,
                                      provenienza_per_dimensione=provenienza)

    assert corpo["momenti"]["quota_autoconsumo"] == 0.6
    assert "quota_autosufficienza" not in corpo["momenti"]


def test_quota_autosufficienza_si_calcola_sul_consumo_MISURATO_non_dedotto():
    """**Il difetto ALTO della review, mandato «il bilancio dell'energia»,
    punto 1 (27/08/2026), riprodotto coi numeri misurati sulla casa vera.**

    La vecchia formula era `autoconsumo / (autoconsumo + prelievo)`:
    un'IDENTITA' che assume che il consumo della casa sia autoconsumo piu'
    prelievo. Su questa integrazione e' falsa -- "autoconsumata" ESCLUDE la
    batteria -- e con un ciclo di batteria vero la forbice esplode:
    autoconsumo 2, prelievo 10, scarica 5 -- la vecchia formula direbbe
    2/12 = **0,167**. Il consumo VERO (misurato, il settimo totale) e' 17;
    la quota vera e' `(consumo - prelievo) / consumo` = 7/17 = **0,412**.

    Se qualcuno reintroducesse la vecchia identita' (sommando autoconsumo e
    prelievo invece di leggere il consumo), questo test la becca: i due
    numeri non si somigliano nemmeno lontanamente."""
    serie = {
        "sensor.autoconsumo": [_punto(6, 2.0)],
        "sensor.prelievo": [_punto(6, 10.0)],
        "sensor.scarica": [_punto(6, 5.0)],
        "sensor.consumo": [_punto(6, 17.0)],
    }
    entita = {"autoconsumo": "sensor.autoconsumo", "prelievo": "sensor.prelievo",
              "scarica": "sensor.scarica", "consumo": "sensor.consumo"}
    provenienza = {d: "dichiarata" for d in entita}

    corpo = costruisci_corpo_bilancio(serie=serie, entita_per_dimensione=entita,
                                      provenienza_per_dimensione=provenienza)

    assert corpo["totali"]["consumo"]["valore"] == 17.0
    assert corpo["momenti"]["quota_autosufficienza"] == 0.412
    assert corpo["momenti"]["quota_autosufficienza"] != 0.167


def test_quota_autosufficienza_assente_senza_il_consumo_misurato():
    """**Il cuore della correzione**: anche con autoconsumo E prelievo
    presenti, senza il sensore del consumo la quota NON si scrive -- mai
    dedotta da una somma che su questa integrazione puo' essere falsa.
    Prima della correzione questo stesso caso produceva un numero (0.75,
    dedotto): ora il campo e' assente, non un numero inventato."""
    serie = {
        "sensor.autoconsumo": [_punto(6, 6.0)],
        "sensor.prelievo": [_punto(6, 2.0)],
    }
    entita = {"autoconsumo": "sensor.autoconsumo", "prelievo": "sensor.prelievo"}
    provenienza = {d: "dichiarata" for d in entita}

    corpo = costruisci_corpo_bilancio(serie=serie, entita_per_dimensione=entita,
                                      provenienza_per_dimensione=provenienza)

    assert "quota_autosufficienza" not in corpo.get("momenti", {})


def test_quota_autosufficienza_non_esce_negativa_quando_il_prelievo_supera_il_consumo():
    """**Punto 3 del mandato (27/08/2026): `_quota` promette nel nome e nel
    docstring un valore fra 0 e 1, e non lo garantiva.** Il caso non e'
    teorico: il prelievo puo' superare il consumo di casa quando la
    batteria si carica dalla rete -- quell'energia importata serve a
    caricare, non e' consumo della casa. Consumo 10, prelievo 15 (5 kWh sono
    andati alla carica): la vecchia formula scriverebbe `(10-15)/10 =
    -0,5`, un fatto impossibile travestito da dato.

    **Non si scrive nemmeno uno zero**: zero affermerebbe "zero
    autosufficienza", e non lo sappiamo -- i 5 kWh in piu' di prelievo
    potrebbero convivere con un'ottima autoproduzione nel resto della
    giornata. Quando la premessa non regge, il campo non compare."""
    serie = {
        "sensor.consumo": [_punto(6, 10.0)],
        "sensor.prelievo": [_punto(6, 15.0)],
    }
    entita = {"consumo": "sensor.consumo", "prelievo": "sensor.prelievo"}
    provenienza = {d: "dichiarata" for d in entita}

    corpo = costruisci_corpo_bilancio(serie=serie, entita_per_dimensione=entita,
                                      provenienza_per_dimensione=provenienza)

    assert "quota_autosufficienza" not in corpo.get("momenti", {})


def test_quota_autosufficienza_al_confine_prelievo_uguale_consumo():
    """Il confine resta valido: `prelievo == consumo` non e' il caso rotto
    (nessuna energia e' andata a caricare oltre il consumo), e la quota
    torna zero -- un fatto vero, non omesso per prudenza eccessiva."""
    serie = {
        "sensor.consumo": [_punto(6, 10.0)],
        "sensor.prelievo": [_punto(6, 10.0)],
    }
    entita = {"consumo": "sensor.consumo", "prelievo": "sensor.prelievo"}
    provenienza = {d: "dichiarata" for d in entita}

    corpo = costruisci_corpo_bilancio(serie=serie, entita_per_dimensione=entita,
                                      provenienza_per_dimensione=provenienza)

    assert corpo["momenti"]["quota_autosufficienza"] == 0.0


def test_quota_assente_se_il_denominatore_manca():
    """Zero produzione conosciuta non e' "zero autoconsumo": e' "non lo so"
    -- la quota non compare, non diventa 0.0 ne' un'eccezione."""
    serie = {"sensor.autoconsumo": [_punto(6, 6.0)]}
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"autoconsumo": "sensor.autoconsumo"},
        provenienza_per_dimensione={"autoconsumo": "dichiarata"})
    assert "quota_autoconsumo" not in corpo.get("momenti", {})
    assert "quota_autosufficienza" not in corpo.get("momenti", {})


def test_batteria_percentuale_oraria_arrotondata_a_un_decimale():
    """**`batteria_percentuale_oraria` porta l'ORA di ogni punto, come
    `forma`** (correzione MEDIA della review, mandato «il bilancio
    dell'energia», punto 2, 27/08/2026): prima di questa correzione era
    rimasta una lista NUDA di percentuali (`[56.6, 84.2]`) -- **lo stesso
    difetto di `forma` prima della sua correzione**, un campo piu' in la':
    con un buco del recorder gli indici non sono le ore, e la curva della
    batteria si disallineava in silenzio mentre quella dell'energia,
    accanto, era gia' giusta. La chiave e' `ora`, come per `forma`
    (fondamenta 3, consistenza)."""
    serie = {
        "sensor.produzione": [_punto(6, 1.0)],
        "sensor.batteria": [_punto(6, None, media=56.5833), _punto(7, None, media=84.2)],
    }
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"produzione": "sensor.produzione"},
        provenienza_per_dimensione={"produzione": "dichiarata"},
        entita_batteria="sensor.batteria")
    assert corpo["batteria_percentuale_oraria"] == [
        {"ora": "2026-08-24T06:00:00+00:00", "valore": 56.6},
        {"ora": "2026-08-24T07:00:00+00:00", "valore": 84.2},
    ]


def test_batteria_percentuale_oraria_su_una_giornata_bucata():
    """Il gemello del test di `forma` sopra, sullo stesso campo (punto 2 del
    mandato -- "cerca i fratelli"): batteria vista alle 6 e poi, dopo un
    buco (7 e 8 mancanti), di nuovo alle 9. Un indice posizionale metterebbe
    "07:00" al secondo valore invece della vera "09:00"."""
    serie = {
        "sensor.produzione": [_punto(6, 1.0)],
        "sensor.batteria": [_punto(6, None, media=50.0), _punto(9, None, media=80.0)],
    }
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"produzione": "sensor.produzione"},
        provenienza_per_dimensione={"produzione": "dichiarata"},
        entita_batteria="sensor.batteria")
    assert corpo["batteria_percentuale_oraria"] == [
        {"ora": "2026-08-24T06:00:00+00:00", "valore": 50.0},
        {"ora": "2026-08-24T09:00:00+00:00", "valore": 80.0},
    ]


def test_batteria_assente_dal_corpo_se_non_ha_nessun_dato():
    serie = {
        "sensor.produzione": [_punto(6, 1.0)],
        "sensor.batteria": [_punto(6, None, media=None)],
    }
    corpo = costruisci_corpo_bilancio(
        serie=serie, entita_per_dimensione={"produzione": "sensor.produzione"},
        provenienza_per_dimensione={"produzione": "dichiarata"},
        entita_batteria="sensor.batteria")
    assert "batteria_percentuale_oraria" not in corpo


def test_corpo_vuoto_quando_nessuna_statistica_dice_niente():
    """Le statistiche sono arrivate ma sono vuote per ogni dimensione voluta
    (es. entita' create dopo questo giorno): il corpo torna `{}`, non un
    dizionario con chiavi vuote annidate."""
    corpo = costruisci_corpo_bilancio(
        serie={}, entita_per_dimensione={"produzione": "sensor.x"},
        provenienza_per_dimensione={"produzione": "dichiarata"})
    assert corpo == {}


# --------------------------------------------------------------------------
# `aggrega_giorno(bilanci=...)` -- il punto per cui la fetta esiste.
# --------------------------------------------------------------------------

def _bilancio_valido(dispositivo_id="dev1", nome="Inverter", entita=None):
    entita = entita if entita is not None else [
        "sensor.energia_prodotta_oggi", "sensor.energia_autoconsumata_oggi",
        "sensor.potenza_prodotta", "sensor.totale_energia_prodotta"]
    return {"dispositivo_id": dispositivo_id, "nome": nome, "entita": entita,
            "corpo": {"totali": {"produzione": {"valore": 12.3, "provenienza": "dichiarata"}}}}


def test_un_giorno_con_l_impianto_produce_un_bilancio_e_zero_episodi_per_i_suoi_membri(archivio):
    """**Il test richiesto dal mandato, provato per mutazione**: un giorno
    con l'impianto (quattro entita' dello stesso dispositivo, tre delle
    quali senza nemmeno una direzione utile -- come `totale_energia_
    prodotta`, il contatore di vita) produce UN bilancio e ZERO episodi di
    energia per le entita' che vi sono dentro; un'entita' di energia FUORI
    da ogni bilancio continua a produrre il suo episodio.

    Mutazione ESEGUITA: in `aggrega_giorno`, `if soggetto not in
    entita_in_bilancio:` sostituito con `if True:` (ignorare la
    soppressione) -- arrossisce, perche' tornano 4 episodi di energia
    individuali oltre al bilancio invece di 0. Ripristinato subito dopo."""
    membri = ["sensor.energia_prodotta_oggi", "sensor.energia_autoconsumata_oggi",
             "sensor.potenza_prodotta", "sensor.totale_energia_prodotta"]
    for soggetto in membri:
        archivio.annota(quando_ts=ts(6), fonte="entita", soggetto=soggetto,
                        da=None, a="1.0", device_class="energy")
        archivio.annota(quando_ts=ts(12), fonte="entita", soggetto=soggetto,
                        da=None, a="5.0", device_class="energy")
    # Un'entita' di energia FUORI dal bilancio (un altro dispositivo, o
    # nessuno): deve continuare a produrre il suo episodio come prima.
    archivio.annota(quando_ts=ts(7), fonte="entita", soggetto="sensor.altro_contatore",
                    da=None, a="2.0", device_class="energy")
    archivio.annota(quando_ts=ts(20), fonte="entita", soggetto="sensor.altro_contatore",
                    da=None, a="9.0", device_class="energy")

    quanti = aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome",
                            bilanci=[_bilancio_valido(entita=membri)])

    oggetti = archivio.oggetti(giorno=G)
    assert quanti == len(oggetti)

    bilanci_scritti = [o for o in oggetti if o["genere"] == "bilancio"]
    assert len(bilanci_scritti) == 1
    assert bilanci_scritti[0]["protagonista"] == "dev1"

    energie_scritte = [o for o in oggetti if o["genere"] == "energia"]
    assert {o["protagonista"] for o in energie_scritte} == {"sensor.altro_contatore"}

    assert len(oggetti) == 2  # un bilancio + un episodio (l'entita' fuori)


def test_il_bilancio_porta_il_nome_del_dispositivo_e_i_suoi_membri(archivio):
    membri = ["sensor.energia_prodotta_oggi"]
    for soggetto in membri:
        archivio.annota(quando_ts=ts(6), fonte="entita", soggetto=soggetto,
                        da=None, a="1.0", device_class="energy")
        archivio.annota(quando_ts=ts(12), fonte="entita", soggetto=soggetto,
                        da=None, a="5.0", device_class="energy")

    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome",
                   bilanci=[_bilancio_valido(entita=membri)])

    [o] = [x for x in archivio.oggetti(giorno=G) if x["genere"] == "bilancio"]
    assert o["corpo"]["dispositivo"] == "Inverter"
    assert o["corpo"]["entita"] == membri
    assert o["corpo"]["totali"]["produzione"]["valore"] == 12.3


def test_il_bilancio_si_chiude_sempre_dentro_la_giornata(archivio):
    """Come l'energia individuale: mai `fine_ts: None`, e' gia' cio' che si
    sa a fine giornata, non qualcosa ancora in corso."""
    archivio.annota(quando_ts=ts(6), fonte="entita", soggetto="sensor.x",
                    da=None, a="1.0", device_class="energy")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome",
                   bilanci=[_bilancio_valido(entita=["sensor.x"])])

    [o] = [x for x in archivio.oggetti(giorno=G) if x["genere"] == "bilancio"]
    from hiris.app.cervello.oggetti import confini_giorno
    da_ts, a_ts = confini_giorno(G, "Europe/Rome")
    assert o["inizio_ts"] == da_ts
    assert o["fine_ts"] == a_ts


def test_un_bilancio_senza_totali_non_sopprime_niente_e_non_si_scrive(archivio):
    """La stessa regola gia' presa per `direzioni`: mai un oggetto vuoto al
    posto di quello che c'era. Un bilancio senza nemmeno un totale (le
    statistiche non hanno detto niente per nessuna dimensione) non
    sopprime i suoi membri -- se lo facesse, undici frammenti diventerebbero
    ZERO oggetti, il peggioramento peggiore possibile."""
    archivio.annota(quando_ts=ts(6), fonte="entita", soggetto="sensor.x",
                    da=None, a="1.0", device_class="energy")
    archivio.annota(quando_ts=ts(12), fonte="entita", soggetto="sensor.x",
                    da=None, a="5.0", device_class="energy")

    bilancio_vuoto = {"dispositivo_id": "dev1", "nome": "Inverter",
                      "entita": ["sensor.x"], "corpo": {}}
    quanti = aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome",
                            bilanci=[bilancio_vuoto])

    oggetti = archivio.oggetti(giorno=G)
    assert quanti == 1
    assert len(oggetti) == 1
    assert oggetti[0]["genere"] == "energia"
    assert oggetti[0]["protagonista"] == "sensor.x"


def test_senza_bilanci_il_comportamento_e_identico_a_prima(archivio):
    """`bilanci=None` (il default): nessuna soppressione, nessun oggetto di
    genere bilancio -- il comportamento di sempre, invariato."""
    archivio.annota(quando_ts=ts(6), fonte="entita", soggetto="sensor.x",
                    da=None, a="1.0", device_class="energy")
    archivio.annota(quando_ts=ts(12), fonte="entita", soggetto="sensor.x",
                    da=None, a="5.0", device_class="energy")

    quanti = aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome")

    oggetti = archivio.oggetti(giorno=G)
    assert quanti == 1
    assert oggetti[0]["genere"] == "energia"
