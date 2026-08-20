import pytest

from hiris.app.casa.domande import cerca, guarda
from hiris.app.memoria.riconoscitore import costruisci_indice
from tests.test_nucleo import _CASA, _COMPORTAMENTO, _RICORDI, _STATO

# _CASA, _COMPORTAMENTO, _RICORDI, _STATO sono di tests/test_nucleo.py,
# importati invece di ricopiati -- stessa casa che gia' esercita nucleo.py.


@pytest.fixture
def indice():
    return costruisci_indice(_CASA)


@pytest.fixture
def indice_ambiguo():
    """Due «Bagno» su piani diversi -- la stessa ambiguita' che ha gia'
    costato un fix a Indice.trova() (riconoscitore.py)."""
    casa = {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0},
                  {"id": "primo", "nome": "Primo piano", "livello": 1}],
        "aree": [
            {"id": "bagno_terra", "nome": "Bagno", "piano_id": "terra",
             "alias": [], "etichette": []},
            {"id": "bagno_primo", "nome": "Bagno", "piano_id": "primo",
             "alias": [], "etichette": []},
        ],
        "dispositivi": [], "entita": [], "etichette": [], "categorie": [], "integrazioni": [],
    }
    return costruisci_indice(casa)


def test_cerca_trova_per_nome_e_alias(indice):
    trovate = cerca(indice, "cucina")
    assert any(c["riferimento"] == "cucina"
               for t in trovate for c in t["candidati"])


def test_cerca_non_appiattisce_l_ambiguita(indice_ambiguo):
    """Due «Bagno» su piani diversi: il contratto di Indice.trova e'
    `candidati` sempre lista + `ambiguo`. Appiattirlo qui rifarebbe il difetto
    che e' gia' costato un fix."""
    trovate = cerca(indice_ambiguo, "il bagno")
    assert trovate[0]["ambiguo"] is True
    assert len(trovate[0]["candidati"]) == 2


def test_guarda_un_area_da_le_sue_entita_con_lo_stato():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "area", "cucina")
    ids = {e["id"] for e in dettaglio["entita"]}
    assert ids == {"light.cucina_1", "light.cucina_2", "sensor.cucina_t"}
    assert [e for e in dettaglio["entita"] if e["id"] == "light.cucina_1"][0]["stato"] == "on"


def test_guarda_un_automazione_da_il_corpo():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       "automazione", "automation.sveglia")
    assert dettaglio["corpo"] == {"trigger": []}


def test_guarda_un_automazione_senza_corpo_lo_dice():
    """«Non ho il corpo» e «il corpo e' vuoto» sono due cose diverse: la prima
    e' un limite di HIRIS, la seconda un fatto sulla casa."""
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       "script", "script.buonanotte")
    assert dettaglio["corpo"] is None
    assert dettaglio["origine"] == "solo_stato"


def test_guarda_qualcosa_che_non_esiste_lo_dice():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "area", "taverna")
    assert dettaglio["esiste"] is False


def test_guarda_un_area_porta_anche_cio_che_le_persone_ne_hanno_detto():
    """E' il senso delle ancore: «quali preferenze riguardano questa stanza»."""
    ricordi = [dict(_RICORDI[0],
                    ancore=[{"tipo": "area", "riferimento": "cucina", "nome_visto": "cucina"}])]
    dettaglio = guarda(_CASA, _COMPORTAMENTO, ricordi, _STATO, "area", "cucina")
    assert len(dettaglio["ricordi"]) == 1


# --- Copertura aggiuntiva, oltre i sette test del brief -----------------


def test_guarda_un_entita_da_il_suo_stato_e_la_sua_classe():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "entita", "sensor.cucina_t")
    assert dettaglio["esiste"] is True
    assert dettaglio["classe"] == "temperature"
    assert dettaglio["stato"] == "19.5"


def test_guarda_un_entita_che_non_esiste_lo_dice():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "entita", "light.non_esiste")
    assert dettaglio["esiste"] is False
    assert "stato" not in dettaglio
    assert "classe" not in dettaglio


def test_guarda_un_entita_senza_nome_dichiara_il_nome_dedotto():
    """Stessa porta di `cerca` (B3/B4), qui su `guarda`: un'entita' senza
    nome nel registro non deve uscire con `nome: null` secco quando lo
    specchio dello stato sa come Home Assistant la chiama."""
    casa = {"entita": [{"id": "light.a", "nome": None, "classe": None, "unita": None}]}
    d = guarda(casa, [], [], {"light.a": "off"}, "entita", "light.a",
               nomi_di_ripiego={"light.a": "Abat-jour"})
    assert d["nome"] is None and d["nome_dedotto"] == "Abat-jour"


def test_guarda_non_deduce_un_nome_che_c_e_gia():
    """Dichiarato e dedotto sono due fatti diversi: un nome che l'utente ha
    scelto non si sostituisce mai con uno dedotto, anche se il ripiego lo
    porta."""
    casa = {"entita": [{"id": "light.a", "nome": "Piantana", "classe": None, "unita": None}]}
    d = guarda(casa, [], [], {}, "entita", "light.a",
               nomi_di_ripiego={"light.a": "Lampada da terra"})
    assert d["nome"] == "Piantana" and "nome_dedotto" not in d


def test_guarda_senza_ripiego_si_comporta_come_prima():
    casa = {"entita": [{"id": "light.a", "nome": None, "classe": None, "unita": None}]}
    assert "nome_dedotto" not in guarda(casa, [], [], {}, "entita", "light.a")


# --- I1 (review finale): la stessa disciplina anche per area e dispositivo -


def _casa_area_dispositivo():
    return {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
        "aree": [{"id": "giardino", "nome": "Giardino", "piano_id": "terra",
                  "alias": [], "etichette": []}],
        "dispositivi": [{"id": "dev_irr", "nome": "Irrigazione", "disabilitato": False}],
        "entita": [
            {"id": "switch.irr_1", "nome": None, "classe": None, "unita": None,
             "area_id": "giardino", "dispositivo_id": None, "disabilitata": False},
            {"id": "switch.irr_2", "nome": None, "classe": None, "unita": None,
             "area_id": None, "dispositivo_id": "dev_irr", "disabilitata": False},
        ],
    }


def test_guarda_un_area_dichiara_il_nome_dedotto_delle_sue_entita():
    """Stessa disciplina di `_guarda_entita` (B5), qui su `_guarda_area`:
    prima di questo fix `nomi_di_ripiego` non arrivava affatto a questo
    ramo -- l'entita' usciva con `nome: null` secco anche quando lo
    specchio dello stato sapeva come Home Assistant la chiama."""
    dettaglio = guarda(_casa_area_dispositivo(), [], [], {}, "area", "giardino",
                       nomi_di_ripiego={"switch.irr_1": "Valvola prato"})
    entita = {e["id"]: e for e in dettaglio["entita"]}
    assert entita["switch.irr_1"]["nome"] is None
    assert entita["switch.irr_1"]["nome_dedotto"] == "Valvola prato"


def test_guarda_un_dispositivo_dichiara_il_nome_dedotto_delle_sue_entita():
    """Stesso rilievo I1, sul ramo `_guarda_dispositivo`: e' il percorso che
    la specifica mette come metro della fetta -- la domanda dell'irrigazione
    passa da qui."""
    dettaglio = guarda(_casa_area_dispositivo(), [], [], {}, "dispositivo", "dev_irr",
                       nomi_di_ripiego={"switch.irr_2": "Valvola giardino"})
    entita = {e["id"]: e for e in dettaglio["entita"]}
    assert entita["switch.irr_2"]["nome"] is None
    assert entita["switch.irr_2"]["nome_dedotto"] == "Valvola giardino"


def test_guarda_un_ricordo_da_la_sua_interpretazione_NELLA_STESSA_FORMA():
    """Piatta, come da `richiama` e come dai `ricordi` che ogni altro ramo di
    `guarda` restituisce gia'.

    Prima l'interpretazione era annidata sotto `interpretazione` e `detto_il`
    non usciva: lo stesso ricordo aveva DUE FORME a seconda della porta. Il
    modello ne imparava una dentro `guarda("area", ...)`, poi leggeva
    `r["forza"]` sul dettaglio -> assente, e riferiva «di questo ricordo non
    so la forza» su un ricordo che ce l'ha."""
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "ricordo", 1)
    assert dettaglio["esiste"] is True
    assert dettaglio["testo"] == _RICORDI[0]["testo"]
    assert dettaglio["forza"] == "preferenza"
    assert "interpretazione" not in dettaglio, "il livello annidato non deve tornare"
    # `detto_il` c'era in `richiama` e spariva qui: alla domanda «quando te
    # l'ho detto?» la risposta dipendeva da quale strumento il modello sceglie.
    assert "detto_il" in dettaglio


def test_guarda_un_ricordo_che_non_esiste_lo_dice():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "ricordo", 999)
    assert dettaglio["esiste"] is False
    assert "forza" not in dettaglio


def test_guarda_un_tipo_sconosciuto_non_solleva_e_lo_dice():
    """Un tipo che il modello nomina ma che non conosciamo non e' un'eccezione
    che gli spezza il turno: e' lo stesso "non esiste"."""
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "pianeta", "marte")
    assert dettaglio["esiste"] is False


def test_guarda_un_area_dichiara_se_l_elenco_puo_essere_incompleto():
    """Terza comparsa dello stesso Critical su questo ramo: senza propagare
    `non_disponibili`, `gerarchia()` crede che sia andato tutto bene. Con il
    registro dispositivi caduto, un'entita' che eredita l'area dal proprio
    dispositivo finisce in «Senza area»: una cucina con cinque luci ne mostra
    quattro, con `esiste: True` e nessun avviso.

    E la firma pubblica non aveva nemmeno un punto per farlo entrare: nessun
    chiamante, per quanto diligente, poteva correggerlo dall'esterno.
    """
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "area", "cucina",
                       non_disponibili=("dispositivi",))
    assert dettaglio["esiste"] is True
    assert dettaglio["elenco_incompleto"] == ["dispositivi"]


def test_senza_registri_caduti_l_elenco_non_si_dichiara_incompleto():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "area", "cucina")
    assert "elenco_incompleto" not in dettaglio


def test_guarda_un_dispositivo_dice_se_e_spento_e_quali_entita_sono_morte():
    """Stessa ragione di `_guarda_entita`: qui si legge l'anagrafe grezza, fuori
    da `gerarchia()`, che le disabilitate le esclude. Senza dirlo, un
    dispositivo spento ha la stessa forma di uno che funziona."""
    casa = dict(
        _CASA,
        dispositivi=[{"id": "d1", "nome": "Frigo", "area_id": "cucina", "disabilitato": 1}],
        entita=_CASA["entita"] + [
            {"id": "sensor.frigo", "nome": "Temp frigo", "area_id": None,
             "dispositivo_id": "d1", "classe": "temperature", "unita": "C",
             "disabilitata": 1}])
    dettaglio = guarda(casa, _COMPORTAMENTO, _RICORDI, _STATO, "dispositivo", "d1")
    assert dettaglio["disabilitato"] is True
    assert dettaglio["entita"][0]["disabilitata"] is True


def test_guarda_un_entita_non_trovata_dichiara_il_registro_caduto():
    """CRITICAL ③: `non_disponibili` era inoltrato SOLO a `_guarda_area`.
    Col registro "entita" caduto, un'entita' vera non trovata qui non e'
    un'entita' che non esiste -- e' un registro che non ha risposto. Senza
    dichiararlo il modello legge "quell'entita' non esiste nella tua casa"."""
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       "entita", "light.cucina_0", non_disponibili=("entita",))
    assert dettaglio["esiste"] is False
    assert dettaglio["non_disponibile"] is True


def test_guarda_un_entita_non_trovata_senza_registro_caduto_non_si_inventa_incertezza():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       "entita", "light.non_esiste")
    assert dettaglio["esiste"] is False
    assert "non_disponibile" not in dettaglio


def test_guarda_un_dispositivo_non_trovato_dichiara_il_registro_caduto():
    """CRITICAL ③, stesso difetto sul dispositivo."""
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       "dispositivo", "d_inventato", non_disponibili=("dispositivi",))
    assert dettaglio["esiste"] is False
    assert dettaglio["non_disponibile"] is True


def test_guarda_un_area_non_trovata_dichiara_il_registro_caduto():
    """CRITICAL ③: prima del fix nemmeno il ramo dell'area, l'unico che
    riceveva `non_disponibili`, dichiarava l'incertezza sul CASO "non
    trovata" -- solo sull'elenco di un'area trovata."""
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       "area", "taverna", non_disponibili=("aree",))
    assert dettaglio["esiste"] is False
    assert dettaglio["non_disponibile"] is True


def test_guarda_col_registro_caduto_non_suggerisce_cerca():
    """Review indipendente Task 3 (Important, confermato): quando il
    registro e' caduto (`non_disponibile: True`), la causa non e' un nome
    scambiato per un id -- e' un guasto. `cerca` legge la STESSA anagrafe
    incompleta, quindi suggerirlo sarebbe una strada altrettanto cieca, e
    diluirebbe la distinzione fra "non trovato" e "non ho potuto guardare"
    che questo file marca come critica tre volte (CRITICAL ③). Le due
    chiavi sono mutuamente esclusive sui tre rami: mai insieme."""
    con_registro_caduto = {
        "area": guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       "area", "taverna", non_disponibili=("aree",)),
        "entita": guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                         "entita", "light.cucina_0", non_disponibili=("entita",)),
        "dispositivo": guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                              "dispositivo", "d_inventato", non_disponibili=("dispositivi",)),
    }
    for tipo, dettaglio in con_registro_caduto.items():
        assert dettaglio["esiste"] is False
        assert dettaglio["non_disponibile"] is True
        assert "suggerimento" not in dettaglio, \
            f"il ramo «{tipo}» suggerisce «cerca» anche col registro caduto"
    # Il caso normale (nessun registro caduto) continua ad avere il
    # suggerimento -- la condizione nuova non lo cancella per tutti.
    senza_registro_caduto = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                                   "area", "taverna")
    assert "suggerimento" in senza_registro_caduto


def test_guarda_un_automazione_non_trovata_dichiara_i_file_non_letti():
    """CRITICAL ③, quinto ramo: `_guarda_comportamento` non aveva alcun
    punto d'ingresso per `file_non_letti` -- uno script il cui file non si
    e' letto risultava `esiste: False` secco, indistinguibile da uno script
    che davvero non esiste."""
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       "script", "script.scritto_a_mano",
                       file_non_letti={"scripts.yaml": "assente"})
    assert dettaglio["esiste"] is False
    assert dettaglio["non_disponibile"] is True


def test_guarda_un_automazione_non_trovata_senza_file_non_letti_non_si_inventa_incertezza():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       "automazione", "automation.non_esiste")
    assert dettaglio["esiste"] is False
    assert "non_disponibile" not in dettaglio
    # T7 (R2): da questa fetta `cerca` indicizza le automazioni per nome,
    # quindi "automation.non_esiste" potrebbe essere un NOME scambiato per
    # un id -- lo stesso caso di area/entita'/dispositivo, e insegna la
    # stessa correzione.
    assert "suggerimento" in dettaglio


def test_guarda_non_trovato_suggerisce_cerca_con_la_STESSA_FORMA_in_tutti_i_tipi():
    """R5: il rifiuto nudo (`{"esiste": False}`) e' indistinguibile da "non
    esiste davvero" -- e' il meccanismo diretto dell'incidente che ha
    generato questa fetta (un nome al posto di un id, il modello ritenta
    uguale finche' il turno muore). I rami che possono confondere un nome
    con un id -- area, entita', dispositivo, e da T7 (R2) anche automazione
    e script -- devono insegnare la stessa correzione, con la STESSA chiave
    e la STESSA forma di frase (fondamenta 3): un modello che ha appena
    sbagliato con un nome in un ramo non deve indovinare la differenza per
    gli altri.

    Automazione e script si aggiungono qui perche' `cerca` ora li
    indicizza per nome (test_memoria_riconoscitore.py): fino a T7 restavano
    fuori apposta (decisione del Task 3), perche' suggerire "cerca" quando
    `cerca` non li trovava comunque sarebbe stato un invito a una strada
    cieca -- vedi il docstring di `_dettaglio_non_trovato`.

    Il confronto e' fra i rami stessi (non asserzioni indipendenti): stesso
    `riferimento` per tutti, quindi lo stesso suggerimento deve uscire
    IDENTICO -- se un ramo perde il campo o cambia la frase, l'insieme delle
    forme smette di avere un solo elemento."""
    esiti = {
        "area": guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "area", "Soggiorno"),
        "entita": guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "entita", "Soggiorno"),
        "dispositivo": guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "dispositivo", "Soggiorno"),
        "automazione": guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "automazione", "Soggiorno"),
        "script": guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "script", "Soggiorno"),
    }
    for tipo, dettaglio in esiti.items():
        assert dettaglio["esiste"] is False
        assert "suggerimento" in dettaglio, f"manca il suggerimento nel ramo «{tipo}»"
        assert "cerca" in dettaglio["suggerimento"]
    forme = {dettaglio["suggerimento"] for dettaglio in esiti.values()}
    assert len(forme) == 1, f"i rami non usano la stessa forma: {forme}"


# --- R2 (T7): `cerca` impara piani, automazioni e script -------------------


def test_cerca_poi_guarda_un_automazione_end_to_end():
    """Requisito 2 del brief: `guarda` deve accettare DAVVERO i riferimenti
    che `cerca` ora produce -- non solo un id che il modello sapeva gia'.
    Qui si parte da un nome, si passa da `cerca`, e si chiude il giro con
    `guarda` sul candidato restituito."""
    indice = costruisci_indice(_CASA, comportamento=_COMPORTAMENTO)
    trovati = cerca(indice, "spegni la sveglia")
    candidato = next(c for t in trovati for c in t["candidati"] if c["tipo"] == "automazione")
    assert candidato["riferimento"] == "automation.sveglia"

    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                       candidato["tipo"], candidato["riferimento"])
    assert dettaglio["esiste"] is True
    assert dettaglio["corpo"] == {"trigger": []}


def test_guarda_non_sa_aprire_un_piano():
    """Requisito 2 del brief, il caso negativo che va scritto e non lasciato
    implicito: `cerca` ora risolve un piano per nome, ma `guarda` non ha (e
    non deve avere) un tipo "piano" -- un piano si ESEGUE
    (`esegui(piani=...)`, promesso da `claude_runner.py`), non si apre in
    dettaglio come un'area. `guarda` lo dichiara con la stessa onesta' con
    cui dichiara ogni altro tipo che non sa aprire (`non_so_guardare`),
    invece di un `esiste: False` indistinguibile da "questo piano non
    esiste"."""
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "piano", "terra")
    assert dettaglio["esiste"] is False
    assert dettaglio["non_so_guardare"] is True


def test_guarda_un_area_marca_le_entita_disabilitate_invece_di_nasconderle():
    """MINOR: `_guarda_area` nascondeva le entita' disabilitate senza dirlo,
    mentre `_guarda_dispositivo` le mostra marcate. Per una vista di
    dettaglio e' informazione, non rumore."""
    casa = dict(_CASA, entita=_CASA["entita"] + [
        {"id": "light.cucina_morta", "nome": "Faretto rotto", "area_id": "cucina",
         "dispositivo_id": None, "classe": None, "unita": None, "disabilitata": 1}])
    dettaglio = guarda(casa, _COMPORTAMENTO, _RICORDI, _STATO, "area", "cucina")
    per_id = {e["id"]: e for e in dettaglio["entita"]}
    assert per_id["light.cucina_morta"]["disabilitata"] is True
    assert per_id["light.cucina_1"]["disabilitata"] is False


def test_l_entita_orfana_finisce_nella_pseudo_area_giusta():
    """La bandierina «elenco_incompleto» non basta: difende se stessa, non la
    propagazione. Qui si guarda cosa fa DAVVERO `gerarchia()`.

    Un'entita' senza area propria che eredita quella del dispositivo, col
    registro dispositivi caduto: senza propagare, finisce in «Senza area» --
    un'affermazione FALSA su quell'entita'. Con la propagazione finisce in
    «Dispositivi non letti», che e' la verita': nessuno lo sa.
    """
    casa = dict(_CASA, entita=_CASA["entita"] + [
        {"id": "light.forno", "nome": "Luce forno", "area_id": None,
         "dispositivo_id": "d_forno", "classe": None, "unita": None, "disabilitata": 0}])

    non_letti = guarda(casa, _COMPORTAMENTO, _RICORDI, _STATO,
                       "area", "__dispositivi_non_letti__", non_disponibili=("dispositivi",))
    assert non_letti["esiste"] is True
    assert [e["id"] for e in non_letti["entita"]] == ["light.forno"]

    # e senza dichiarare il registro caduto, la stessa entita' verrebbe
    # affermata «senza area»: e' proprio la bugia che il fix toglie
    senza_area = guarda(casa, _COMPORTAMENTO, _RICORDI, _STATO, "area", "__senza_area__")
    assert [e["id"] for e in senza_area["entita"]] == ["light.forno"]


# --- Task B4: i candidati di `cerca` portano nome e dominio -------------


def test_i_candidati_portano_il_dominio_cosi_un_contatore_non_sembra_una_luce():
    """`cerca("luci")` restituiva `sensor.lights` e niente lo diceva."""
    casa = {"aree": [], "dispositivi": [],
            "entita": [{"id": "sensor.lights", "nome": "Luci", "alias": []},
                       {"id": "light.salotto", "nome": "Luce salotto", "alias": []}]}
    voci = cerca(costruisci_indice(casa), "quante luci")
    domini = {c["riferimento"]: c["dominio"] for v in voci for c in v["candidati"]}
    assert domini == {"sensor.lights": "sensor"}


def test_i_candidati_portano_il_nome():
    casa = {"aree": [{"id": "b1", "nome": "Bagno", "alias": []},
                     {"id": "b2", "nome": "Bagno", "alias": []}],
            "dispositivi": [], "entita": []}
    voci = cerca(costruisci_indice(casa), "in bagno")
    assert [c["nome"] for c in voci[0]["candidati"]] == ["Bagno", "Bagno"]
    assert voci[0]["ambiguo"] is True


def test_un_nome_dedotto_si_dichiara_dedotto():
    """I2 (review finale): `nome_dedotto` e' una forma sola in tutto il
    modulo -- la stringa col nome dedotto, mai un booleano. Prima di questo
    fix `cerca()` scriveva `True` mentre `guarda()` scriveva la stringa: due
    tipi diversi per lo stesso fatto, e un modello che avesse imparato la
    forma da `cerca` avrebbe letto male quella di `guarda` (e viceversa)."""
    casa = {"aree": [], "dispositivi": [],
            "entita": [{"id": "light.a", "nome": None, "alias": []}]}
    voci = cerca(costruisci_indice(casa, {"light.a": "Abat-jour"}), "abat-jour")
    candidato = voci[0]["candidati"][0]
    assert candidato["nome"] == "Abat-jour" and candidato["nome_dedotto"] == "Abat-jour"


def test_un_nome_dichiarato_non_si_dichiara_dedotto():
    """Mutazione uccisa: mettere `nome_dedotto` su tutti."""
    casa = {"aree": [{"id": "c", "nome": "Cucina", "alias": []}],
            "dispositivi": [], "entita": []}
    candidato = cerca(costruisci_indice(casa), "cucina")[0]["candidati"][0]
    assert "nome_dedotto" not in candidato and "dominio" not in candidato


def test_il_nome_dichiarato_vince_sul_dedotto_quando_ci_sono_entrambi():
    """Mutazione uccisa: invertire la precedenza (preferire il nome dedotto
    al dichiarato). `costruisci_indice` non produce mai i due insieme -- il
    ripiego scatta solo quando il nome in registro manca (B1) -- quindi
    nessuna delle case sopra puo' esercitare questo ramo passando per
    l'indice vero. La precedenza si prova qui direttamente sull'oggetto che
    `verifica()` restituisce, con un indice finto che li mette entrambi: e'
    la garanzia che `cerca()` non deleghi la propria correttezza a
    un'invariante di un modulo diverso."""
    class _IndiceFinto:
        def trova(self, testo):
            return [{"nome_visto": testo, "ambiguo": False,
                     "candidati": [{"tipo": "entita", "riferimento": "light.a"}]}]

        def verifica(self, tipo, riferimento):
            return {"nome": "Abat-jour", "nome_dedotto": "Luce salotto"}

    candidato = cerca(_IndiceFinto(), "abat-jour")[0]["candidati"][0]
    assert candidato["nome"] == "Abat-jour"


# --- Le unita': stessa disciplina dei nomi, stessa ragione ------------------
#
# `_to_minimal` conserva `unit` con cura (`proxy/entity_cache.py:88`) e nessuno
# la rilegge: `_specchio()` estrae solo `state` e `name`, e `_guarda_area`
# restituisce `{id, nome, classe, stato, disabilitata}`. Risultato: HIRIS legge
# `72` e non sa se sono gradi Celsius o Fahrenheit.
#
# Non basta il sistema di unita' della casa: Home Assistant converte **solo
# alla prima aggiunta del sensore**, quindi `unit_system` non descrive le
# entita' gia' presenti. Conta l'unita' PER ENTITA', ed e' quella che si
# buttava via.


def _casa_con_sensore():
    return {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
        "aree": [{"id": "sala", "nome": "Sala", "piano_id": "terra",
                  "alias": [], "etichette": []}],
        "dispositivi": [{"id": "dev_t", "nome": "Termometro", "disabilitato": False}],
        "entita": [
            {"id": "sensor.sala_t", "nome": "Temperatura sala", "classe": "temperature",
             "unita": None, "area_id": "sala", "dispositivo_id": "dev_t",
             "disabilitata": False},
            {"id": "light.sala", "nome": "Lampada", "classe": None, "unita": None,
             "area_id": "sala", "dispositivo_id": None, "disabilitata": False},
        ],
    }


def test_guarda_un_area_porta_l_unita_delle_sue_entita():
    """IL BUCO VERO: si chiede una stanza e si ricevono numeri nudi.
    `_guarda_area` restituiva `{id, nome, classe, stato, disabilitata}` --
    nessuna unita' -- ed e' la porta che il modello usa per «com'e' il
    soggiorno?»."""
    d = guarda(_casa_con_sensore(), [], [], {"sensor.sala_t": "27.0"},
               "area", "sala", unita_vive={"sensor.sala_t": "°C"})
    sensore = next(e for e in d["entita"] if e["id"] == "sensor.sala_t")
    assert sensore["stato"] == "27.0"
    assert sensore["unita"] == "°C", "27.0 di cosa?"


def test_guarda_un_entita_preferisce_l_unita_VIVA_a_quella_del_registro():
    """LA FINTA E' SCOMODA DI PROPOSITO: registro e specchio dicono due unita'
    diverse. Il registro puo' essere vecchio -- Home Assistant converte solo
    alla prima aggiunta -- e lo specchio e' cio' che HA sta mandando adesso.
    Con due valori uguali questa prova non distinguerebbe le due sorgenti."""
    casa = _casa_con_sensore()
    casa["entita"][0]["unita"] = "°F"
    d = guarda(casa, [], [], {"sensor.sala_t": "27.0"}, "entita", "sensor.sala_t",
               unita_vive={"sensor.sala_t": "°C"})
    assert d["unita"] == "°C"


def test_guarda_un_dispositivo_porta_l_unita_delle_sue_entita():
    """I1, applicato alle unita': la stessa entita' e' la stessa cosa da tutte
    le porte. Senza questa prova, due porte su tre direbbero l'unita' e la
    terza no -- che e' esattamente il difetto che I1 aveva gia' trovato sui
    nomi."""
    d = guarda(_casa_con_sensore(), [], [], {"sensor.sala_t": "27.0"},
               "dispositivo", "dev_t", unita_vive={"sensor.sala_t": "°C"})
    sensore = next(e for e in d["entita"] if e["id"] == "sensor.sala_t")
    assert sensore["unita"] == "°C"


def test_un_entita_senza_unita_non_guadagna_la_chiave():
    """Una lampada non ha un'unita', e una chiave `unita: null` su ogni luce
    della casa sarebbe rumore in ogni risposta. Stessa disciplina di
    `nome_dedotto`: la chiave compare solo quando il fatto c'e'."""
    d = guarda(_casa_con_sensore(), [], [], {"light.sala": "on"},
               "area", "sala", unita_vive={"sensor.sala_t": "°C"})
    lampada = next(e for e in d["entita"] if e["id"] == "light.sala")
    assert "unita" not in lampada


def test_senza_unita_vive_si_comporta_come_prima():
    d = guarda(_casa_con_sensore(), [], [], {"sensor.sala_t": "27.0"},
               "area", "sala")
    sensore = next(e for e in d["entita"] if e["id"] == "sensor.sala_t")
    assert "unita" not in sensore


# --- R2 (T8): il label_id esce come dato accessorio da cerca/guarda -------


def test_cerca_un_etichetta_da_il_label_id_end_to_end():
    """Requisito 2 del brief T8: un modello che sa solo il NOME di
    un'etichetta arriva al suo `label_id` con UNA chiamata a `cerca` --
    anche quando nessuna entita' la porta ancora, il vicolo cieco piu'
    radicale della famiglia (R2, docs/design/2026-08-20-i-riferimenti.md):
    fino a questa fetta il `label_id` non usciva da NESSUNA porta."""
    casa = {"piani": [], "aree": [], "dispositivi": [], "entita": [],
           "categorie": [], "integrazioni": [],
           "etichette": [{"id": "da_controllare", "nome": "Da controllare"}]}
    indice = costruisci_indice(casa)
    trovati = cerca(indice, "da controllare")
    candidato = next(c for t in trovati for c in t["candidati"]
                     if c["tipo"] == "etichetta")
    assert candidato["riferimento"] == "da_controllare"
    assert candidato["nome"] == "Da controllare"


def test_guarda_un_entita_mostra_il_label_id_accanto_al_nome():
    """Requisito 1 del brief T8: dove un'etichetta compare in una risposta
    di `guarda`, l'id le sta accanto -- il nome resta protagonista, l'id e'
    il dato accessorio (`Nome (id: X)`, la stessa forma dell'albero del
    nucleo per aree/piani/automazioni)."""
    casa = dict(_CASA, entita=[dict(_CASA["entita"][0], etichette=["notturne"])],
               etichette=[{"id": "notturne", "nome": "Notturne"}])
    d = guarda(casa, _COMPORTAMENTO, _RICORDI, _STATO, "entita", _CASA["entita"][0]["id"])
    assert d["etichette"] == ["Notturne (id: notturne)"]


def test_guarda_non_sa_aprire_un_etichetta():
    """Come per i piani (`test_guarda_non_sa_aprire_un_piano`): `cerca` da
    T8 risolve un'etichetta per nome, ma un'etichetta non e' una cosa che
    si apre in dettaglio -- e' un'ancora per `esegui`. `guarda` lo dichiara
    con la stessa onesta' di ogni altro tipo che non sa aprire, invece di
    un `esiste: False` indistinguibile da "questa etichetta non esiste"."""
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "etichetta", "notturne")
    assert dettaglio["esiste"] is False
    assert dettaglio["non_so_guardare"] is True
