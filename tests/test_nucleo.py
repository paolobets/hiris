import pytest

from hiris.app.casa.nucleo import componi

_CASA = {
    "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
    "aree": [{"id": "cucina", "nome": "Cucina", "piano_id": "terra", "alias": [], "etichette": []},
             {"id": "sala", "nome": "Sala", "piano_id": "terra", "alias": [], "etichette": []}],
    "dispositivi": [],
    "entita": [
        {"id": "light.cucina_1", "nome": "Faretti", "area_id": "cucina", "dispositivo_id": None,
         "classe": None, "unita": None, "disabilitata": 0},
        {"id": "light.cucina_2", "nome": "Tavolo", "area_id": "cucina", "dispositivo_id": None,
         "classe": None, "unita": None, "disabilitata": 0},
        {"id": "sensor.cucina_t", "nome": "Temperatura", "area_id": "cucina", "dispositivo_id": None,
         "classe": "temperature", "unita": "°C", "disabilitata": 0},
        {"id": "binary_sensor.porta", "nome": "Porta", "area_id": "sala", "dispositivo_id": None,
         "classe": "door", "unita": None, "disabilitata": 0},
    ],
    "etichette": [], "categorie": [], "integrazioni": [],
}
_COMPORTAMENTO = [
    {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
     "corpo": {"trigger": []}, "origine": "file"},
    {"id": "script.buonanotte", "tipo": "script", "nome": "Buonanotte",
     "corpo": None, "origine": "solo_stato"},
]
_RICORDI = [
    {"id": 1, "testo": "d'inverno la sala la preferisco fra 19 e 20 gradi",
     "detto_da": "paolo", "ancore": [], "condizioni": [], "forza": "preferenza"},
]
_STATO = {"light.cucina_1": "on", "light.cucina_2": "off",
          "sensor.cucina_t": "19.5", "binary_sensor.porta": "on"}


def test_il_nucleo_conta_invece_di_elencare():
    """Con trecento entita' elencarle tutte sfonderebbe il contesto: il nucleo
    dice quante ce ne sono per tipo, e il dettaglio si va a chiedere."""
    testo, _ = componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert "Cucina" in testo
    assert "2 luci" in testo or "luci: 2" in testo
    assert "light.cucina_1" not in testo          # i singoli id non ci stanno


def test_cio_che_e_notevole_adesso_si_vede():
    testo, _ = componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert "Faretti" in testo                     # accesa: e' notevole
    assert "Tavolo" not in testo                  # spenta: non lo e'
    assert "Porta" in testo                       # aperta


def test_i_ricordi_dichiarati_entrano_interi():
    """L'unica cosa che non si va a cercare: se il modello dovesse ricordarsi
    di cercarli, si dimenticherebbe -- ed e' il difetto da cui e' nato tutto."""
    testo, _ = componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert "fra 19 e 20 gradi" in testo
    assert "paolo" in testo


def test_i_nomi_di_cio_che_la_casa_fa_da_sola_ci_sono_i_corpi_no():
    testo, _ = componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert "Sveglia" in testo and "Buonanotte" in testo
    assert "trigger" not in testo                 # il corpo si va a chiedere


def test_cio_che_non_si_conosce_si_dichiara():
    """Un'automazione di cui non abbiamo il corpo, e un'anagrafe letta a meta':
    il modello deve sapere cosa HIRIS non sa, o lo dara' per assente."""
    testo, _ = componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert "Buonanotte" in testo
    # la voce senza corpo e' marcata in qualche modo leggibile
    riga = [r for r in testo.splitlines() if "Buonanotte" in r][0]
    assert riga != f"- Buonanotte"


def test_il_taglio_non_e_mai_silenzioso():
    """Un nucleo troncato in silenzio e' un HIRIS che crede di sapere."""
    tanti = [dict(_RICORDI[0], id=i, testo=f"ricordo numero {i} " + "x" * 200)
             for i in range(200)]
    testo, riepilogo = componi(_CASA, _COMPORTAMENTO, tanti, _STATO, tetto=2000)
    assert len(testo) <= 2000 * 1.1
    assert riepilogo["troncato"] is True
    assert riepilogo["ricordi_esclusi"] > 0
    assert "non" in testo.lower()                 # il taglio e' scritto NEL nucleo


def test_una_casa_vuota_non_produce_un_nucleo_bugiardo():
    vuota = {chiave: [] for chiave in _CASA}
    testo, riepilogo = componi(vuota, [], [], {})
    assert riepilogo["troncato"] is False
    assert testo.strip()                          # dice qualcosa, non e' vuoto


def test_le_entita_disabilitate_non_si_contano():
    casa = dict(_CASA, entita=_CASA["entita"] + [
        {"id": "light.spenta", "nome": "Spenta", "area_id": "cucina", "dispositivo_id": None,
         "classe": None, "unita": None, "disabilitata": 1}])
    testo, _ = componi(casa, _COMPORTAMENTO, _RICORDI, _STATO)
    assert "3 luci" not in testo                  # restano 2


def test_un_registro_caduto_si_dichiara_nel_nucleo():
    """La lacuna piu' grave che esista: una casa letta a meta' che il nucleo
    racconterebbe come una casa piccola. La sezione «cio' che HIRIS ignora»
    esiste apposta, ma senza questo parametro non poteva nominarla."""
    testo, riepilogo = componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                               non_disponibili=("aree", "dispositivi"))
    assert "aree" in testo and "dispositivi" in testo
    assert any("non hanno risposto" in a for a in riepilogo["avvisi"])


def test_senza_registri_caduti_non_si_inventa_un_avviso():
    _, riepilogo = componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert not any("non hanno risposto" in a for a in riepilogo["avvisi"])
