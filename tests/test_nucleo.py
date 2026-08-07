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
    # CRITICAL ①: non basta che l'avviso lo dica due paragrafi dopo -- «La
    # casa» stessa (la prima cosa che il modello legge) non deve affermare
    # che il registro delle aree e' andato bene quando e' caduto. Con un
    # entita' senza area risolta, deve comparire "Aree non lette" (mai
    # "Senza area", che afferma un dato che non abbiamo).
    casa_con_orfana = dict(_CASA, entita=_CASA["entita"] + [
        {"id": "light.orfana", "nome": "Orfana", "area_id": None, "dispositivo_id": None,
         "classe": None, "unita": None, "disabilitata": 0}])
    testo_orfana, _ = componi(casa_con_orfana, _COMPORTAMENTO, _RICORDI, _STATO,
                              non_disponibili=("aree", "dispositivi"))
    sezione_casa = testo_orfana.split("## Notevole adesso")[0]
    assert "Aree non lette" in sezione_casa
    assert "Senza area" not in sezione_casa


def test_senza_registri_caduti_non_si_inventa_un_avviso():
    _, riepilogo = componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert not any("non hanno risposto" in a for a in riepilogo["avvisi"])


def test_registro_aree_caduto_non_dice_senza_area():
    """CRITICAL ①, riproduzione esatta del difetto: `_righe_casa` chiamava
    `gerarchia(casa)` SENZA `non_disponibili`, che invece serve solo alla
    frase in fondo. Un'entita' senza area risolta, col registro delle aree
    caduto, deve finire in "Aree non lette" -- MAI in "Senza area", che
    afferma un dato che non abbiamo (e che «Cio' che HIRIS ignora» due
    paragrafi dopo contraddirebbe)."""
    casa = dict(_CASA, entita=_CASA["entita"] + [
        {"id": "light.orfana", "nome": "Orfana", "area_id": None, "dispositivo_id": None,
         "classe": None, "unita": None, "disabilitata": 0}])
    testo, _ = componi(casa, _COMPORTAMENTO, _RICORDI, _STATO, non_disponibili=("aree",))
    sezione_casa = testo.split("## Notevole adesso")[0]
    assert "Aree non lette" in sezione_casa
    assert "Senza area" not in sezione_casa


def test_notevole_usa_lo_stesso_albero_della_casa():
    """CRITICAL ①, seconda meta': `_righe_notevole` non deve ricalcolare
    l'area a mano (`e.get("area_id") or area_del_dispositivo.get(...)`) --
    quella logica non sa distinguere un riferimento penzolante da
    un'assenza vera, e lascia l'entita' senza prefisso in silenzio. Deve
    usare lo STESSO albero di «La casa», che a un'area_id sconosciuta da'
    un nome esplicito ("Area sconosciuta")."""
    casa = dict(_CASA, entita=_CASA["entita"] + [
        {"id": "light.penzolante", "nome": "Penzolante", "area_id": "non_esiste",
         "dispositivo_id": None, "classe": None, "unita": None, "disabilitata": 0}])
    stato = dict(_STATO, **{"light.penzolante": "on"})
    testo, _ = componi(casa, _COMPORTAMENTO, _RICORDI, stato)
    assert "Area sconosciuta: Penzolante" in testo


def test_stato_vuoto_non_e_niente_di_notevole():
    """CRITICAL ②: stato={} con la casa piena (HIRIS non ha ancora letto lo
    stato) non deve produrre "Niente di notevole al momento." -- non ho
    guardato e' diverso da ho guardato e va tutto bene."""
    testo, riepilogo = componi(_CASA, _COMPORTAMENTO, _RICORDI, {})
    assert "Niente di notevole al momento." not in testo
    assert any("non e' stato letto" in a or "non attendibile" in a for a in riepilogo["avvisi"])


def test_tutte_entita_unknown_non_e_niente_di_notevole():
    """"unknown" e' lo stato comunissimo di un'entita' subito dopo un
    riavvio di Home Assistant, prima che il primo aggiornamento arrivi --
    non e' un dato, e' l'assenza di un dato."""
    stato_unknown = {e["id"]: "unknown" for e in _CASA["entita"]}
    testo, _ = componi(_CASA, _COMPORTAMENTO, _RICORDI, stato_unknown)
    assert "Niente di notevole al momento." not in testo


def test_chiamante_puo_dichiarare_stato_non_affidabile():
    """CRITICAL ②: anche con uno stato che sembra a posto, il chiamante deve
    poter dire esplicitamente "non ti fidare" -- una lettura iniziata ma
    non ancora conclusa, per esempio."""
    calma = {"light.cucina_1": "off", "light.cucina_2": "off",
              "sensor.cucina_t": "19.5", "binary_sensor.porta": "off"}
    testo_dichiarato, _ = componi(_CASA, _COMPORTAMENTO, _RICORDI, calma,
                                  stato_affidabile=False)
    assert "Niente di notevole al momento." not in testo_dichiarato
    # la stessa identica casa calma, SENZA la dichiarazione, produce
    # legittimamente la frase di quiete -- la firma di prima non lasciava
    # scelta al chiamante.
    testo_normale, _ = componi(_CASA, _COMPORTAMENTO, _RICORDI, calma)
    assert "Niente di notevole al momento." in testo_normale


def test_casa_vuota_con_stato_vuoto_resta_niente_di_notevole():
    """Una casa senza entita' non e' un silenzio: non c'e' nulla da
    guardare, quindi "niente di notevole" resta vero."""
    vuota = {chiave: [] for chiave in _CASA}
    testo, _ = componi(vuota, [], [], {})
    assert "Niente di notevole al momento." in testo


def test_stato_alarm_non_e_uno_stato_reale():
    """MINOR ⑤: "alarm" non e' mai stato uno stato reale di
    alarm_control_panel in Home Assistant -- era voce morta."""
    from hiris.app.casa.nucleo import _STATI_NOTEVOLI
    assert "alarm" not in _STATI_NOTEVOLI
    assert "triggered" in _STATI_NOTEVOLI


def test_allarme_scattato_e_notevole_armato_no():
    """MINOR ⑤: solo "triggered" e' notevole per un allarme -- "armed_away"
    fa parte della routine quotidiana (si arma e si disarma piu' volte al
    giorno) tanto quanto accendere e spegnere una luce, non e' un'eccezione
    rispetto al riposo."""
    casa = dict(_CASA, entita=_CASA["entita"] + [
        {"id": "alarm_control_panel.ingresso", "nome": "Allarme", "area_id": "sala",
         "dispositivo_id": None, "classe": None, "unita": None, "disabilitata": 0}])
    stato_scattato = dict(_STATO, **{"alarm_control_panel.ingresso": "triggered"})
    testo, _ = componi(casa, _COMPORTAMENTO, _RICORDI, stato_scattato)
    assert "Allarme" in testo.split("## Cio' che la casa fa")[0]

    stato_armato = dict(_STATO, **{"alarm_control_panel.ingresso": "armed_away"})
    testo_armato, _ = componi(casa, _COMPORTAMENTO, _RICORDI, stato_armato)
    sezione_notevole = testo_armato.split("## Notevole adesso")[1].split(
        "## Cio' che la casa fa")[0]
    assert "Allarme" not in sezione_notevole


def test_i_ricordi_tagliati_sono_ordinati_esplicitamente_dal_codice():
    """MINOR ④: se il chiamante li passasse in un ordine diverso da quello
    di `ArchivioMemoria.richiama()` (che oggi e' gia' "il piu' recente
    prima" per coincidenza, `ORDER BY id DESC`), il taglio deve comunque
    scartare il PIU' VECCHIO, non l'ultimo della lista che gli e' arrivata."""
    ricordi_in_ordine_sbagliato = [
        dict(_RICORDI[0], id=1, testo="RICORDO-VECCHISSIMO " + "x" * 200),
        dict(_RICORDI[0], id=2, testo="RICORDO-DI-MEZZO " + "x" * 200),
        dict(_RICORDI[0], id=3, testo="RICORDO-FRESCHISSIMO " + "x" * 200),
    ]
    testo, riepilogo = componi(_CASA, _COMPORTAMENTO, ricordi_in_ordine_sbagliato, _STATO,
                               tetto=1100)
    assert riepilogo["ricordi_esclusi"] >= 1
    assert "RICORDO-VECCHISSIMO" not in testo
    assert "RICORDO-FRESCHISSIMO" in testo


def _casa_grande(n_aree: int = 20, entita_per_area: int = 15) -> dict:
    """Casa deterministica con almeno 200 entita' (IMPORTANT ③): abbastanza
    grande da dimostrare che, col tetto di default, la mappa delle aree
    sopravvive al taglio invece di essere svuotata per intero per tenere
    quasi intatta la lista dei notevoli."""
    piani = [{"id": "terra", "nome": "Piano terra", "livello": 0},
             {"id": "primo", "nome": "Primo piano", "livello": 1}]
    aree, entita = [], []
    domini = ["light", "switch", "sensor", "binary_sensor", "cover"]
    for i in range(n_aree):
        piano_id = "terra" if i % 2 == 0 else "primo"
        area_id = f"area{i}"
        aree.append({"id": area_id, "nome": f"Area {i}", "piano_id": piano_id,
                     "alias": [], "etichette": []})
        for j in range(entita_per_area):
            dominio = domini[j % len(domini)]
            entita.append({
                "id": f"{dominio}.a{i}_e{j}", "nome": f"Entita {i}-{j}",
                "area_id": area_id, "dispositivo_id": None,
                "classe": None, "unita": None, "disabilitata": 0,
            })
    return {"piani": piani, "aree": aree, "dispositivi": [], "entita": entita,
            "etichette": [], "categorie": [], "integrazioni": []}


def test_una_casa_grande_la_mappa_sopravvive_al_taglio():
    """IMPORTANT ③: 300 entita', 20 aree, 40 automazioni, ~200 notevoli --
    col tetto di DEFAULT il nucleo deve ancora contenere la mappa completa
    delle aree e le automazioni. Prima del fix, il taglio svuotava per
    intero "La casa" e "Cio' che la casa fa gia' da sola" pur di tenere
    quasi intatta la lista dei notevoli, il contrario di quanto dichiara il
    docstring del modulo ("il nucleo CONTA, non elenca")."""
    casa = _casa_grande()
    assert len(casa["entita"]) >= 200
    stato = {e["id"]: ("on" if i < 200 else "off") for i, e in enumerate(casa["entita"])}
    comportamento = [
        {"id": f"automation.a{i}", "tipo": "automazione", "nome": f"Automazione {i}",
         "corpo": {"trigger": []}, "origine": "file"}
        for i in range(40)
    ]
    testo, riepilogo = componi(casa, comportamento, [], stato)

    sezione_casa = testo.split("## Notevole adesso")[0]
    righe_area = [l for l in sezione_casa.splitlines() if l.strip().startswith("- Area")]
    assert len(righe_area) == 20, "la mappa delle aree deve sopravvivere col tetto di default"

    sezione_comportamento = testo.split("## Cio' che la casa fa gia' da sola")[-1].split(
        "## Cio' che le persone")[0]
    righe_automazioni = [l for l in sezione_comportamento.splitlines()
                         if l.strip().startswith("- Automazione")]
    assert len(righe_automazioni) == 40, "le automazioni devono sopravvivere col tetto di default"

    # La sezione notevole, essendo grande, conta invece di elencare una per
    # una -- coerente col docstring del modulo.
    sezione_notevole = testo.split("## Notevole adesso")[1].split("## Cio' che la casa fa")[0]
    righe_notevole_singole = [l for l in sezione_notevole.splitlines()
                              if l.strip().startswith("- Area") and "acceso" in l]
    assert len(righe_notevole_singole) < 200, "oltre soglia, i notevoli si raggruppano"
    assert "elementi notevoli" in sezione_notevole
