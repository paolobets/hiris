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


def test_guarda_un_ricordo_da_la_sua_interpretazione():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "ricordo", 1)
    assert dettaglio["esiste"] is True
    assert dettaglio["testo"] == _RICORDI[0]["testo"]
    assert dettaglio["interpretazione"]["forza"] == "preferenza"


def test_guarda_un_ricordo_che_non_esiste_lo_dice():
    dettaglio = guarda(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, "ricordo", 999)
    assert dettaglio["esiste"] is False
    assert "interpretazione" not in dettaglio


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
    casa = {"aree": [], "dispositivi": [],
            "entita": [{"id": "light.a", "nome": None, "alias": []}]}
    voci = cerca(costruisci_indice(casa, {"light.a": "Abat-jour"}), "abat-jour")
    candidato = voci[0]["candidati"][0]
    assert candidato["nome"] == "Abat-jour" and candidato["nome_dedotto"] is True


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
