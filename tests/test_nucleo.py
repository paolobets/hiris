import pytest

from hiris.app.casa import nucleo
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
    # MINOR ⑨: `"non" in testo.lower()` reggeva per coincidenza del corpus
    # (tre lettere comunissime in italiano) -- non dimostrava che il taglio
    # fosse scritto DENTRO il nucleo. Qui si verifica la frase vera, dentro
    # la sezione dedicata, col conteggio giusto.
    sezione_lacune = testo.split("## Cio' che HIRIS ignora")[1]
    assert "ricordi non inclusi" in sezione_lacune or "ricordo non incluso" in sezione_lacune
    assert str(riepilogo["ricordi_esclusi"]) in sezione_lacune


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
    un nome esplicito ("Area sconosciuta").

    IMPORTANT ⑦: "Area sconosciuta" e' una pseudo-area (mai un'area vera di
    Home Assistant), quindi il nucleo mostra anche l'id -- l'unica chiave
    con cui `guarda('area', ...)` la ritrova davvero."""
    casa = dict(_CASA, entita=_CASA["entita"] + [
        {"id": "light.penzolante", "nome": "Penzolante", "area_id": "non_esiste",
         "dispositivo_id": None, "classe": None, "unita": None, "disabilitata": 0}])
    stato = dict(_STATO, **{"light.penzolante": "on"})
    testo, _ = componi(casa, _COMPORTAMENTO, _RICORDI, stato)
    assert "Area sconosciuta (id: __area_sconosciuta__): Penzolante" in testo


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


def test_allarme_scattato_e_notevole_armato_no():
    """MINOR ⑨: era affiancato da `test_stato_alarm_non_e_uno_stato_reale`,
    che asseriva il contenuto della COSTANTE `_STATI_NOTEVOLI` -- difendeva
    la costante, non il comportamento. Il gemello comportamentale (questo
    test) e' l'unico che conta davvero: se "alarm" tornasse per errore in
    quella costante, sarebbe questo test a fallire, non un controllo
    sull'implementazione. Rimosso il ridondante.

    Solo "triggered" e' notevole per un allarme -- "armed_away"
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


def test_il_notevole_raggruppato_tiene_insieme_le_aree():
    """La stessa area finiva sparsa in tre punti diversi dell'elenco, nell'ordine
    in cui capitavano le entita'. Leggibilita' e' un requisito dichiarato: chi
    legge deve vedere una stanza per volta, non ricomporla a mente."""
    entita, stato = [], {}
    for i in range(30):
        area = "cucina" if i % 2 else "sala"
        eid = f"light.e{i}"
        entita.append({"id": eid, "nome": f"Luce {i}", "area_id": area,
                       "dispositivo_id": None, "classe": None, "unita": None,
                       "disabilitata": 0})
        stato[eid] = "on"
    casa = dict(_CASA, entita=entita,
                aree=[{"id": "cucina", "nome": "Cucina", "piano_id": "terra",
                       "alias": [], "etichette": []},
                      {"id": "sala", "nome": "Sala", "piano_id": "terra",
                       "alias": [], "etichette": []}])
    testo, _ = componi(casa, [], [], stato)
    sezione = testo.split("## Notevole adesso")[1].split("##")[0]
    aree_in_ordine = [r.split(":")[0].removeprefix("- ").strip()
                      for r in sezione.splitlines() if r.startswith("- ")]
    assert aree_in_ordine == sorted(aree_in_ordine)   # ogni area in un blocco solo


def test_registro_entita_caduto_rende_lo_stato_inaffidabile():
    """CRITICAL ②: aree e piani letti, registro "entita" caduto (tabella
    vuota, com'e' dopo un `sostituisci` parziale), cinque luci accese nella
    cache viva. Prima del fix: `casa.get("entita", [])` vuota faceva
    scattare il ramo "casa senza entita' = niente da guardare", e
    "Notevole adesso" diceva "Niente di notevole al momento." -- una
    quiete che il nucleo stesso contraddice due sezioni dopo, nell'avviso
    sul registro caduto."""
    casa = {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
        "aree": [{"id": "ingresso", "nome": "Ingresso", "piano_id": "terra",
                  "alias": [], "etichette": []}],
        "dispositivi": [], "entita": [],
        "etichette": [], "categorie": [], "integrazioni": [],
    }
    stato_vivo = {"light.cucina_1": "on", "light.cucina_2": "on", "light.sala": "on",
                  "light.corridoio": "on", "light.bagno": "on"}
    testo, riepilogo = componi(casa, [], [], stato_vivo, non_disponibili=("entita",),
                               stato_affidabile=True)
    assert "Niente di notevole al momento." not in testo
    assert any("non e' stato letto" in a or "non attendibile" in a for a in riepilogo["avvisi"])


def test_avviso_corpi_mancanti_conta_non_elenca():
    """IMPORTANT ④: l'avviso sui corpi mancanti elencava TUTTI i nomi per
    esteso -- con cento script `solo_stato` (il caso comunissimo delle
    scene importate) da solo sfondava il tetto. Il modulo dichiara "si
    conta, non si elenca": applicato a se stesso, l'avviso deve contare."""
    comportamento = [
        {"id": f"script.s{i}", "tipo": "script", "nome": f"Scena importata numero {i}",
         "corpo": None, "origine": "solo_stato"}
        for i in range(100)
    ]
    testo, riepilogo = componi(_CASA, comportamento, [], {})
    avviso = next(a for a in riepilogo["avvisi"] if "senza corpo" in a)
    assert avviso == "100 voci di comportamento senza corpo disponibile (solo il nome)."
    # I nomi restano visibili riga per riga in "Cio' che la casa fa gia' da
    # sola" (`_righe_comportamento` marca ogni voce senza corpo in linea):
    # e' l'AVVISO che non deve piu' duplicarli per esteso, non il nucleo
    # intero a doverli nascondere.
    sezione_lacune = testo.split("## Cio' che HIRIS ignora")[1]
    assert "Scena importata" not in sezione_lacune


def test_rete_di_sicurezza_taglia_anche_senza_ricordi_da_tagliare():
    """IMPORTANT ④: con zero ricordi, la vecchia rete di sicurezza (limitata
    a `while ... and righe_ricordi`) non aveva alcuna leva -- il nucleo
    poteva sfondare il tetto del 94% in silenzio. Cento script `solo_stato`,
    zero ricordi, tetto di default: il testo non deve MAI superare il
    tetto*1.1, con o senza ricordi da tagliare."""
    comportamento = [
        {"id": f"script.s{i}", "tipo": "script", "nome": f"Scena importata numero {i}",
         "corpo": None, "origine": "solo_stato"}
        for i in range(100)
    ]
    testo, riepilogo = componi(_CASA, comportamento, [], {}, tetto=6000)
    assert len(testo) <= 6000 * 1.1
    assert riepilogo["troncato"] is True


def test_intestazione_dei_notevoli_raggruppati_torna_dopo_il_taglio():
    """IMPORTANT ⑤: l'intestazione ("N elementi notevoli") deve corrispondere
    SEMPRE alla somma delle righe che restano sotto, anche dopo il taglio --
    prima del fix l'intestazione restava quella di PRIMA del taglio,
    contraddicendo le righe sotto (es. "150 elementi" con righe che ne
    sommano 95)."""
    casa = _casa_grande(30, 5)
    stato = {e["id"]: "on" for e in casa["entita"]}  # 150 luci accese
    comportamento = [
        {"id": f"automation.a{i}", "tipo": "automazione", "nome": f"Auto {i}",
         "corpo": {"trigger": []}, "origine": "file"}
        for i in range(20)
    ]
    testo, riepilogo = componi(casa, comportamento, [], stato, tetto=6000)
    assert riepilogo["troncato"] is True
    sezione = testo.split("## Notevole adesso")[1].split("## Cio' che la casa fa")[0]
    import re
    righe_non_vuote = [r for r in sezione.strip().splitlines() if r]
    assert righe_non_vuote, "il test presuppone un taglio parziale (righe superstiti)"
    prima_riga = righe_non_vuote[0]
    intestazione_totale = int(re.match(r"\((\d+) element", prima_riga).group(1))
    righe_dati = [r for r in righe_non_vuote[1:] if r.startswith("- ")]
    somma_righe = sum(int(re.search(r": (\d+) ", r).group(1)) for r in righe_dati)
    assert intestazione_totale == somma_righe, (
        f"l'intestazione ({intestazione_totale}) deve corrispondere alla somma delle "
        f"righe rimaste ({somma_righe}), non al totale di prima del taglio")


def test_taglio_dei_notevoli_raggruppati_conta_elementi_non_righe():
    """IMPORTANT ⑤: una riga raggruppata rappresenta N entita' -- tagliarla
    deve dichiarare N elementi esclusi, non 1 riga. Sottostimare l'escluso
    e' peggio di non dichiararlo: sembra onesto e non lo e'."""
    casa = _casa_grande(30, 5)
    stato = {e["id"]: "on" for e in casa["entita"]}
    testo, riepilogo = componi(casa, [], [], stato, tetto=1500)
    assert riepilogo["troncato"] is True
    avviso = next(a for a in riepilogo["avvisi"] if "elementi notevoli non inclusi" in a
                  or "elemento notevole non incluso" in a)
    import re
    n_esclusi = int(re.search(r"(\d+) element", avviso).group(1))
    # Ogni riga raggruppata di questa casa vale 5 elementi (5 domini x 3
    # entita' ciascuno raggruppati diversamente -- comunque un multiplo di
    # 1 riga != 1 elemento): l'esclusione dichiarata deve essere un conteggio
    # di ENTITA', non di righe -- quindi deve poter essere > del numero di
    # righe effettivamente sparite.
    assert n_esclusi > 0
    assert n_esclusi % 5 == 0 or n_esclusi % 3 == 0, (
        "l'escluso dichiarato deve essere un conteggio di elementi (multiplo delle "
        f"dimensioni dei gruppi), non di righe: {n_esclusi}")


def test_mappa_ha_una_riserva_minima_anche_con_una_casa_grande_e_molti_ricordi():
    """IMPORTANT ⑥, il test che mancava: prima del fix, con MOLTI ricordi
    (l'unico caso difeso da `test_i_ricordi_tagliati_...`, che pero' usa
    sempre `ricordi=[]` per la casa grande) la mappa delle aree spariva PER
    INTERO -- zero righe su diciotto -- perche' il taglio la esauriva prima
    di toccare un solo ricordo. Con la riserva minima, "## La casa" non
    puo' mai restare vuota quando c'e' davvero una casa da descrivere."""
    casa = _casa_grande()
    assert len(casa["entita"]) >= 200
    stato = {e["id"]: ("on" if i < 200 else "off") for i, e in enumerate(casa["entita"])}
    comportamento = [
        {"id": f"automation.a{i}", "tipo": "automazione", "nome": f"Automazione {i}",
         "corpo": {"trigger": []}, "origine": "file"}
        for i in range(40)
    ]
    ricordi = [dict(id=i, testo=f"ricordo numero {i} " + "x" * 200,
                    detto_da="paolo", ancore=[], condizioni=[], forza="preferenza")
               for i in range(200)]
    testo, riepilogo = componi(casa, comportamento, ricordi, stato)  # tetto di default
    assert riepilogo["troncato"] is True
    sezione_casa = testo.split("## Notevole adesso")[0]
    righe_area = [l for l in sezione_casa.splitlines() if l.strip().startswith("- Area")]
    assert len(righe_area) >= 1, "la mappa non deve mai sparire per intero, se c'e' una casa"
    assert "Piano terra:" in sezione_casa


def test_taglio_non_lascia_intestazioni_di_piano_orfane():
    """MINOR: il taglio, tagliando dalla coda, poteva lasciare un'intestazione
    di piano ("Primo piano:") senza nessuna riga di area sotto -- un
    artefatto del taglio, non un'informazione."""
    casa = _casa_grande(30, 5)
    stato = {e["id"]: "on" for e in casa["entita"]}
    comportamento = [
        {"id": f"automation.a{i}", "tipo": "automazione",
         "nome": f"Automazione con nome lungo numero {i}",
         "corpo": {"trigger": []}, "origine": "file"}
        for i in range(80)
    ]
    ricordi = [dict(id=i, testo=f"ricordo numero {i} " + "x" * 100,
                    detto_da="paolo", ancore=[], condizioni=[], forza="preferenza")
               for i in range(50)]
    for tetto_prova in (500, 800, 1200, 2000, 3000, 6000):
        testo, _ = componi(casa, comportamento, ricordi, stato, tetto=tetto_prova)
        sezione_casa = testo.split("## Notevole adesso")[0]
        righe = [r for r in sezione_casa.splitlines() if r.strip()][1:]  # senza "## La casa"
        for i, riga in enumerate(righe):
            e_intestazione = riga.endswith(":") and not riga.startswith("  ")
            if e_intestazione:
                assert i + 1 < len(righe) and righe[i + 1].startswith("  "), (
                    f"intestazione di piano orfana con tetto={tetto_prova}: {riga!r}")


# --- l'annotazione di dispositivo (A1) ------------------------------------
#
# Le finte qui sotto devono MENTIRE COME MENTE LA REALTA': una casa con
# un'entita' per dispositivo non prova niente sul raggruppamento, che e'
# esattamente cio' che queste righe difendono.


def _e(entity_id, dispositivo_id=None):
    return {"id": entity_id, "dispositivo_id": dispositivo_id, "nome": entity_id}


def test_quattro_valvole_di_un_solo_dispositivo_si_annotano_col_nome():
    """Il caso del 14 agosto. Senza questa annotazione il modello, per
    raggruppare, dovrebbe indovinare di cercare un dispositivo di cui non
    conosce il nome."""
    entita = [_e(f"valve.v{i}", "dev1") for i in range(4)]
    assert nucleo._annotazione_dispositivo(
        entita, "valve", 4, {"dev1": "Irrigazione giardino"}) == " (Irrigazione giardino)"


def test_una_sola_entita_su_un_solo_dispositivo_non_si_annota():
    """Il 75% delle righe: una presa, una lampadina, un contatto portano
    un'entita' per dominio -- una cosa, un conteggio, niente da aggiungere.

    E' l'UNICO caso che il confronto `>= quante` decide da solo: con piu'
    dispositivi decide gia' `_MAX_NOMI_DISPOSITIVO_IN_RIGA`, quindi la
    mutazione "togliere `>= quante`" sopravvive a tutti gli altri test e
    muore solo qui -- e da qui si vedrebbe subito, perche' e' la riga piu'
    frequente della casa. La presa porta anche un `sensor`: il filtro sul
    dominio deve escluderlo."""
    entita = [_e("light.presa", "dev1"), _e("sensor.presa_w", "dev1")]
    assert nucleo._annotazione_dispositivo(entita, "light", 1, {"dev1": "Presa cucina"}) == ""


def test_quattro_valvole_di_quattro_dispositivi_non_si_annotano():
    """La regola si spegne da sola: quando sono quattro cose separate il
    conteggio e' tutto cio' che serve. Mutazione uccisa: `_portatori` che
    smettesse di distinguere gli id (per esempio tenendo solo il primo)
    annoterebbe qui col nome di una valvola sola, spacciando quattro cose
    per una."""
    entita = [_e(f"valve.v{i}", f"dev{i}") for i in range(4)]
    nomi = {f"dev{i}": f"Valvola {i}" for i in range(4)}
    assert nucleo._annotazione_dispositivo(entita, "valve", 4, nomi) == ""


def test_dodici_sensori_di_tre_dispositivi_contano_e_non_elencano():
    """Sopra `_MAX_NOMI_DISPOSITIVO_IN_RIGA` non si citano nomi. E' la riga
    che tiene il budget: senza, 61 righe come questa citerebbero 344 nomi."""
    entita = [_e(f"sensor.s{i}", f"dev{i % 3}") for i in range(12)]
    nomi = {f"dev{i}": f"Presa {i}" for i in range(3)}
    assert nucleo._annotazione_dispositivo(entita, "sensor", 12, nomi) == ""


def test_un_dispositivo_e_un_entita_libera_non_producono_un_annotazione_parziale():
    """Tre entita', un dispositivo che ne porta due e una senza: il nome
    coprirebbe solo una parte del conteggio. Mutazione uccisa: togliere
    `senza or` dalla condizione."""
    entita = [_e("sensor.a", "dev1"), _e("sensor.b", "dev1"), _e("sensor.c")]
    assert nucleo._annotazione_dispositivo(entita, "sensor", 3, {"dev1": "Presa"}) == ""


def test_un_dispositivo_senza_nome_mostra_l_id_marcato_come_id():
    """`name_by_user or name` sono entrambi nullable in casa/archivio.py. Un
    id tecnico si marca come dedotto, mai spacciato per nome dichiarato --
    ed e' comunque la chiave con cui `guarda("dispositivo", ...)` lo trova.

    Tre casi che arrivano tutti dallo stesso registro: nome vuoto, dispositivo
    assente dalla tabella dei nomi, e nome fatto di soli spazi (un nome che
    non nomina -- mutazione uccisa: togliere `.strip()`, che stamperebbe
    " (   )")."""
    entita = [_e(f"valve.v{i}", "dev9") for i in range(3)]
    assert nucleo._annotazione_dispositivo(entita, "valve", 3, {"dev9": ""}) == " (id: dev9)"
    assert nucleo._annotazione_dispositivo(entita, "valve", 3, {}) == " (id: dev9)"
    assert nucleo._annotazione_dispositivo(entita, "valve", 3, {"dev9": "   "}) == " (id: dev9)"


def test_col_registro_dispositivi_caduto_non_si_annota_niente():
    """`None` non e' `{}`: "non ho potuto guardare" non e' "nessun
    dispositivo". Mutazione uccisa: usare `nomi_dispositivo or {}` invece del
    controllo esplicito, che stamperebbe "(id: ...)" su tutta la casa."""
    entita = [_e(f"valve.v{i}", "dev1") for i in range(4)]
    assert nucleo._annotazione_dispositivo(entita, "valve", 4, None) == ""


def test_i_portatori_contano_le_entita_senza_dispositivo_una_a_testa():
    entita = [_e("sensor.a", "dev1"), _e("sensor.b", "dev1"),
              _e("sensor.c"), _e("light.x", "dev2")]
    assert nucleo._portatori(entita, "sensor") == (["dev1"], 1)
    assert nucleo._portatori(entita, "light") == (["dev2"], 0)


def test_i_portatori_conservano_l_ordine_dell_anagrafe():
    """Una lista, non un `set`: l'ordine dev'essere quello dell'anagrafe, o
    due letture della stessa casa producono due nuclei diversi. Gli id sono
    scelti perche' l'ordine di arrivo non sia ne' alfabetico ne' il suo
    contrario, cosi' anche un `sorted()` messo li' "per stabilita'" cade."""
    arrivo = ["dev_mu", "dev_alfa", "dev_zeta", "dev_beta", "dev_omega"]
    entita = [_e(f"sensor.s{i}", d) for i, d in enumerate(arrivo)]
    entita.append(_e("sensor.s99", "dev_mu"))  # ritorno del primo: non si ripete
    assert nucleo._portatori(entita, "sensor") == (arrivo, 0)
