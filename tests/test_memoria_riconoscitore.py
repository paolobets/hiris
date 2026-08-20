import re

import pytest

from hiris.app.memoria.riconoscitore import costruisci_indice

_CASA = {
    "aree": [
        {"id": "sala_pranzo", "nome": "Sala da pranzo", "alias": ["tinello"], "piano_id": "terra"},
        {"id": "cucina", "nome": "Cucina", "alias": [], "piano_id": "terra"},
    ],
    "entita": [
        {"id": "climate.sala", "nome": "Termostato sala da pranzo", "alias": ["caldaia"],
         "area_id": "sala_pranzo", "classe": "temperature", "unita": "°C"},
        {"id": "light.cucina", "nome": "Luce cucina", "alias": [], "area_id": "cucina",
         "classe": None, "unita": None},
    ],
    "dispositivi": [{"id": "d1", "nome": "Frigorifero", "area_id": "cucina"}],
    "piani": [], "etichette": [], "categorie": [], "integrazioni": [],
}


def _casa_con_aree(aree: list[dict]) -> dict:
    """Una casa minima con solo le aree indicate: helper per i casi di
    ambiguita' e di confine di parola, dove non serve altro dell'anagrafe."""
    return {
        "aree": aree,
        "entita": [], "dispositivi": [],
        "piani": [], "etichette": [], "categorie": [], "integrazioni": [],
    }


def _riferimenti(trovata: dict) -> set[str]:
    """I riferimenti di una voce trovata, ambigua o no: helper di comodo per
    i test che non devono conoscere la struttura interna di `candidati`."""
    return {c["riferimento"] for c in trovata["candidati"]}


@pytest.fixture
def indice():
    return costruisci_indice(_CASA)


def test_trova_un_area_per_nome(indice):
    trovate = indice.trova("d'inverno la sala da pranzo sta bene a 19 gradi")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert [(c["tipo"], c["riferimento"]) for c in trovate[0]["candidati"]] == [("area", "sala_pranzo")]
    assert trovate[0]["nome_visto"] == "sala da pranzo"


def test_trova_un_area_per_alias(indice):
    """Gli alias sono sinonimi DICHIARATI dall'utente in Home Assistant per
    l'assistente vocale: significato dato, non dedotto."""
    trovate = indice.trova("nel tinello fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert _riferimenti(trovate[0]) == {"sala_pranzo"}
    assert trovate[0]["nome_visto"] == "tinello"


def test_le_maiuscole_e_gli_accenti_non_contano(indice):
    trovate = indice.trova("LA SALA DA PRANZO")
    assert len(trovate) == 1
    assert _riferimenti(trovate[0]) == {"sala_pranzo"}


def test_trova_piu_cose_in_una_frase(indice):
    trovate = indice.trova("in cucina la luce cucina resta accesa")
    assert {r for t in trovate for r in _riferimenti(t)} == {"cucina", "light.cucina"}
    assert all(t["ambiguo"] is False for t in trovate)


def test_preferisce_il_nome_piu_lungo(indice):
    """«Sala da pranzo» contiene «sala»: se vincesse il piu' corto, l'ancora
    punterebbe alla cosa sbagliata."""
    casa = dict(_CASA, aree=_CASA["aree"] + [{"id": "sala", "nome": "Sala",
                                              "alias": [], "piano_id": "terra"}])
    trovate = costruisci_indice(casa).trova("la sala da pranzo")
    assert len(trovate) == 1
    assert _riferimenti(trovate[0]) == {"sala_pranzo"}


def test_una_parola_dentro_un_altra_non_conta(indice):
    """«cucinare» non nomina la cucina."""
    assert indice.trova("mi piace cucinare la sera") == []


def test_niente_di_riconosciuto_non_e_un_errore(indice):
    assert indice.trova("domani piove") == []


def test_una_casa_vuota_non_esplode():
    vuota = {chiave: [] for chiave in _CASA}
    assert costruisci_indice(vuota).trova("la sala da pranzo") == []


def test_verifica_un_ancora_proposta_dal_modello(indice):
    """La semantica la fa il modello: «salotto» -> area soggiorno lo risolve
    lui, che ha la casa in contesto. Qui si verifica solo che esista."""
    trovata = indice.verifica("area", "sala_pranzo")
    assert trovata["nome"] == "Sala da pranzo"


def test_un_ancora_inventata_dal_modello_non_passa(indice):
    """Il modello propone, il codice restringe: se non esiste, non si scrive."""
    assert indice.verifica("area", "taverna") is None
    assert indice.verifica("entita", "light.inesistente") is None


def test_verifica_non_confonde_i_tipi(indice):
    """Un identificatore di entita' passato come area non deve passare per
    somiglianza: sono spazi di nomi diversi."""
    assert indice.verifica("area", "climate.sala") is None


def test_un_nome_con_la_punteggiatura_si_trova():
    """«Bagno (piano terra)» non veniva trovato MAI, nemmeno sul nome esatto:
    il confine di parola finale pretendeva una lettera dopo la parentesi."""
    casa = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno (piano terra)", "alias": []}])
    indice = costruisci_indice(casa)

    trovate = indice.trova("il bagno (piano terra) e' freddo")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert _riferimenti(trovate[0]) == {"bagno_terra"}

    assert indice.trova("bagno (piano terra)")


def test_due_aree_omonime_sono_ambigue_non_una_sola():
    """Due «Bagno» su piani diversi: prima vinceva il primo inserito, in
    silenzio, e l'altro era irraggiungibile."""
    casa = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno", "alias": []},
                           {"id": "bagno_primo", "nome": "Bagno", "alias": []}])
    trovate = costruisci_indice(casa).trova("il bagno e' sporco")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"bagno_terra", "bagno_primo"}


def test_un_alias_che_collide_col_nome_di_un_altra_area_e_ambiguo():
    """«Soggiorno» ha alias «salotto», ed esiste anche un'area «Salotto»."""
    casa = _casa_con_aree([{"id": "soggiorno", "nome": "Soggiorno", "alias": ["salotto"]},
                           {"id": "salotto_vero", "nome": "Salotto", "alias": []}])
    trovate = costruisci_indice(casa).trova("in salotto fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"soggiorno", "salotto_vero"}


def test_cucinare_non_nomina_ancora_la_cucina():
    """Il fix del confine non deve aprire la porta ai falsi positivi."""
    casa = _casa_con_aree([{"id": "cucina", "nome": "Cucina", "alias": []}])
    assert costruisci_indice(casa).trova("mi piace cucinare la sera") == []


def test_nome_visto_conserva_il_testo_originale():
    """`nome_visto` e' cio' che l'utente ha scritto, non il testo
    normalizzato su cui si cerca -- oggi non morde perche' nessuno lo
    archivia, ma nella fetta E sarebbe gia' una riscrittura silenziosa
    (memoria/archivio.py, regola 1: il testo e' la verita')."""
    casa = _casa_con_aree([{"id": "camera_niccolo", "nome": "Camera di Niccolo'", "alias": []}])
    indice = costruisci_indice(casa)

    trovate = indice.trova("nella Camera di Niccolo' fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["nome_visto"] == "Camera di Niccolo'"


def test_nome_visto_sopravvive_a_spazi_multipli():
    """La compressione degli spazi multipli nel testo normalizzato sposta le
    posizioni: `nome_visto` deve comunque recuperare lo spezzone giusto del
    testo originale, spazi doppi compresi."""
    casa = _casa_con_aree([{"id": "sala_pranzo", "nome": "Sala da pranzo", "alias": []}])
    indice = costruisci_indice(casa)

    trovate = indice.trova("nella sala  da   pranzo fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["nome_visto"] == "sala  da   pranzo"


def test_le_espressioni_non_si_compilano_prima_del_primo_trova():
    """`costruisci_indice()` gira a ogni GET/PATCH di /api/memoria, ma quelle
    rotte usano solo `verifica()` -- un accesso a dizionario. Compilare i
    pattern li' sarebbe lavoro morto (misurato: 16,8 ms a 380 voci): si
    compila pigri, alla prima trova()."""
    casa = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno (piano terra)", "alias": []}])
    indice = costruisci_indice(casa)
    assert indice._termini_compilati is None


def test_le_espressioni_si_compilano_una_volta_sola():
    """Il costo passava da 7 a 76 ms intorno alle 300 entita', perche' la
    cache implicita di CPython ha un tetto di 512 pattern condiviso col
    processo. Un controllo puramente strutturale ("esistono dei
    re.Pattern?") passerebbe anche se trova() li ricompilasse a ogni
    chiamata: qui si prova che gli OGGETTI pattern restano gli STESSI fra
    due chiamate di trova(), non solo che qualche pattern esiste."""
    casa = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno (piano terra)", "alias": []}])
    indice = costruisci_indice(casa)

    indice.trova("il bagno (piano terra) e' freddo")
    prima = indice._termini()
    assert prima
    assert all(isinstance(pattern, re.Pattern) for _, pattern in prima)

    indice.trova("un'altra frase qualsiasi, per chiamare trova() una seconda volta")
    seconda = indice._termini()

    assert [id(pattern) for _, pattern in prima] == [id(pattern) for _, pattern in seconda]


# -- il nome di ripiego: sull'impianto vero e' la strada normale ------------
#
# La finta deve mentire come mente la realta'. Sull'impianto misurato il 14
# agosto il `nome` del REGISTRO e' nullo quasi ovunque (le quattro valvole
# dell'irrigazione, le abat-jour) mentre il `friendly_name` dello specchio
# dello stato vivo c'e' su tutte e 849 le entita' vive. Una finta con i nomi
# del registro popolati proverebbe il caso che su quella casa NON ESISTE:
# ogni test qui sotto parte da un'entita' col nome vuoto o None.


def _casa_senza_nomi() -> dict:
    """Le abat-jour: registro con `name` e `original_name` entrambi vuoti --
    la forma esatta che casa/archivio.py:133 produce su questa casa."""
    return {
        "aree": [{"id": "salotto", "nome": "Salotto", "alias": []}],
        "dispositivi": [],
        "entita": [
            {"id": "light.abat_jour_1", "nome": None, "alias": [],
             "area_id": "salotto", "piattaforma": "shelly"},
            {"id": "light.abat_jour_2", "nome": "", "alias": [],
             "area_id": "salotto", "piattaforma": "shelly"},
        ],
        "piani": [], "etichette": [], "categorie": [], "integrazioni": [],
    }


def test_senza_ripiego_un_entita_senza_nome_non_esiste_nello_spazio_in_cui_si_cerca():
    """Il difetto, pinnato -- e con esso le due scorciatoie che lo
    "risolverebbero" mentendo: l'id usato come nome, tale e quale o
    ingentilito. Un id tecnico non e' un nome che qualcuno ha pronunciato.
    L'entita' pero' NON sparisce: il cancello continua a vederla."""
    indice = costruisci_indice(_casa_senza_nomi())

    # solo l'area, mai le due luci
    assert indice.trova("accendi le abat-jour del salotto") == indice.trova("in salotto")
    assert indice.trova("light.abat_jour_1") == []
    assert indice.trova("abat jour 1") == []
    assert indice.verifica("entita", "light.abat_jour_1") is not None
    assert "nome_dedotto" not in indice.verifica("entita", "light.abat_jour_1")


def test_col_friendly_name_l_entita_senza_nome_si_trova():
    """Il guadagno: e' cio' che sarebbe costato quattro giri di `cerca`."""
    indice = costruisci_indice(_casa_senza_nomi(),
                               {"light.abat_jour_1": "Abat-jour"})

    trovati = indice.trova("accendi l'abat-jour")
    assert [c["riferimento"] for v in trovati for c in v["candidati"]] == ["light.abat_jour_1"]


def test_il_nome_dedotto_e_marcato_e_non_sovrascrive_quello_del_registro():
    """Un nome dedotto non si spaccia per dichiarato: chi confronta i nomi
    che l'utente ha scritto davvero non deve inciampare in uno che non ha
    mai scritto."""
    indice = costruisci_indice(_casa_senza_nomi(),
                               {"light.abat_jour_1": "Abat-jour"})

    voce = indice.verifica("entita", "light.abat_jour_1")
    assert voce["nome_dedotto"] == "Abat-jour"
    assert not (voce.get("nome") or "")


def test_il_nome_dedotto_e_marcato_anche_sulle_voci_di_tutti():
    """`tutti("entita")` e' l'altra porta pubblica sull'anagrafe
    (memoria/interpretazione.py la usa per dedurre l'unita' di un'area): il
    marchio deve esserci anche di la', o "dedotto" si vede da una porta e
    non dall'altra. Il resto della riga del registro sopravvive al marchio:
    la copia e' una copia, non una sostituzione."""
    indice = costruisci_indice(_casa_senza_nomi(),
                               {"light.abat_jour_1": "Abat-jour"})

    per_id = {v["id"]: v for v in indice.tutti("entita")}
    assert per_id["light.abat_jour_1"]["nome_dedotto"] == "Abat-jour"
    assert per_id["light.abat_jour_1"]["area_id"] == "salotto"
    assert per_id["light.abat_jour_1"]["piattaforma"] == "shelly"
    assert "nome_dedotto" not in per_id["light.abat_jour_2"]


def test_il_marchio_non_tocca_la_casa_del_chiamante():
    """`voce` e' il dizionario che `ArchivioCasa.leggi()` ha appena
    costruito per il chiamante: marcarlo in place accoppierebbe l'indice al
    ciclo di vita di una struttura che non gli appartiene -- e il chiamante
    si ritroverebbe un nome dedotto in una casa che credeva del registro."""
    casa = _casa_senza_nomi()
    costruisci_indice(casa, {"light.abat_jour_1": "Abat-jour"})

    assert "nome_dedotto" not in casa["entita"][0]


def test_il_ripiego_non_tocca_chi_un_nome_ce_l_ha():
    """Mutazione uccisa: applicare il ripiego sempre invece che solo sul
    vuoto. Il nome scelto dall'utente vince, e' la regola di
    casa/archivio.py:130-133."""
    casa = {"aree": [], "dispositivi": [],
            "entita": [{"id": "light.x", "nome": "Piantana", "alias": []}]}
    indice = costruisci_indice(casa, {"light.x": "Lampada da terra"})

    assert indice.trova("lampada da terra") == []
    assert indice.trova("la piantana")
    assert "nome_dedotto" not in indice.verifica("entita", "light.x")


def test_il_ripiego_non_si_applica_ad_aree_e_dispositivi():
    """Lo specchio dello stato non ha friendly_name per aree e dispositivi:
    un ripiego li' sarebbe di nuovo un id travestito da nome."""
    casa = {"aree": [{"id": "salotto", "nome": "", "alias": []}],
            "dispositivi": [{"id": "dev1", "nome": None, "alias": []}], "entita": []}
    indice = costruisci_indice(casa, {"salotto": "Salotto", "dev1": "Irrigazione"})

    assert indice.trova("salotto") == [] and indice.trova("irrigazione") == []
    assert "nome_dedotto" not in indice.verifica("area", "salotto")
    assert "nome_dedotto" not in indice.verifica("dispositivo", "dev1")


def test_un_ripiego_a_soli_spazi_non_crea_ne_termine_ne_marchio():
    """Un `friendly_name` fatto di spazi non e' un nome: non deve produrre
    un termine vuoto ne' una voce che si dichiara "dedotta" senza nulla da
    mostrare."""
    indice = costruisci_indice(_casa_senza_nomi(), {"light.abat_jour_1": "   "})

    assert indice.trova("accendi l'abat-jour   del salotto") == indice.trova("in salotto")
    assert "nome_dedotto" not in indice.verifica("entita", "light.abat_jour_1")


def test_un_nome_del_registro_fatto_di_soli_spazi_non_batte_il_ripiego():
    """Un nome che una volta normalizzato non e' nulla non e' un nome: se
    battesse il ripiego, la voce si dichiarerebbe "dedotta" e resterebbe
    comunque introvabile -- marchiata e muta."""
    casa = {"aree": [], "dispositivi": [],
            "entita": [{"id": "light.x", "nome": "   ", "alias": []}]}
    indice = costruisci_indice(casa, {"light.x": "Abat-jour"})

    assert _riferimenti(indice.trova("l'abat-jour")[0]) == {"light.x"}
    assert indice.verifica("entita", "light.x")["nome_dedotto"] == "Abat-jour"


def test_gli_alias_restano_indicizzati_anche_quando_il_nome_e_dedotto():
    """Gli alias sono sinonimi DICHIARATI: il ripiego si aggiunge al nome
    mancante, non prende il posto di cio' che l'utente ha scritto."""
    casa = {"aree": [], "dispositivi": [],
            "entita": [{"id": "light.x", "nome": None, "alias": ["piantana"]}]}
    indice = costruisci_indice(casa, {"light.x": "Abat-jour"})

    assert _riferimenti(indice.trova("la piantana")[0]) == {"light.x"}
    assert _riferimenti(indice.trova("l'abat-jour")[0]) == {"light.x"}


def test_un_nome_dedotto_che_collide_con_un_nome_dichiarato_e_ambiguo():
    """Il dedotto entra nello stesso spazio dei nomi dichiarati, quindi puo'
    collidere con loro -- e su questa casa succedera' spesso, perche' il
    dedotto e' la norma. L'indice non sceglie: dichiara l'ambiguita' come
    farebbe per due aree omonime."""
    casa = {"aree": [{"id": "cucina", "nome": "Cucina", "alias": []}],
            "dispositivi": [],
            "entita": [{"id": "valve.giardino_cucina", "nome": None, "alias": []}]}
    indice = costruisci_indice(casa, {"valve.giardino_cucina": "Cucina"})

    trovate = indice.trova("in cucina")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"cucina", "valve.giardino_cucina"}


def test_le_entita_senza_stato_vivo_restano_senza_nome_e_non_spariscono():
    """Misurato: 849 entita' vive contro 1.225 nel registro. Per le 376
    restanti non esiste un `friendly_name` da nessuna parte, e il ripiego
    non le copre. Restano fuori da `trova()` -- come oggi -- ma non
    spariscono e non si inventa loro un nome: dichiarato, non nascosto."""
    indice = costruisci_indice(_casa_senza_nomi(),
                               {"light.abat_jour_1": "Abat-jour"})

    assert _riferimenti(indice.trova("l'abat-jour")[0]) == {"light.abat_jour_1"}
    senza_stato_vivo = indice.verifica("entita", "light.abat_jour_2")
    assert senza_stato_vivo is not None
    assert not (senza_stato_vivo.get("nome") or "")
    assert "nome_dedotto" not in senza_stato_vivo


# -- R2 (T7): piani, automazioni e script -----------------------------------
#
# Prima di questo task nessuna sequenza di chiamate produceva mai un id di
# piano, automazione o script: `_ARCHIVI` non li conosceva. Vedi
# docs/design/2026-08-20-i-riferimenti.md.


def test_trova_un_piano_per_nome():
    casa = dict(_CASA, piani=[{"id": "terra", "nome": "Piano terra", "livello": 0}])
    trovate = costruisci_indice(casa).trova("accendi tutto al piano terra")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert trovate[0]["candidati"] == [{"tipo": "piano", "riferimento": "terra"}]


def test_verifica_un_piano():
    casa = dict(_CASA, piani=[{"id": "terra", "nome": "Piano terra", "livello": 0}])
    trovato = costruisci_indice(casa).verifica("piano", "terra")
    assert trovato["nome"] == "Piano terra"


def test_due_piani_omonimi_sono_ambigui():
    """Stessa regola delle due «Bagno»: l'ambiguita' si dichiara, non si
    sceglie in silenzio in base all'ordine di raccolta."""
    casa = dict(_CASA, piani=[{"id": "p1", "nome": "Mansarda", "livello": 2},
                              {"id": "p2", "nome": "Mansarda", "livello": 2}])
    trovate = costruisci_indice(casa).trova("in mansarda")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"p1", "p2"}


def test_senza_comportamento_nessuna_automazione_si_indicizza():
    """Il parametro e' opzionale (default `None`): i chiamanti che ancora
    non lo passano (`_ricorda`, le pagine di `handlers_memoria.py`) non
    devono vedere comparire nulla sotto "automazione"/"script"."""
    indice = costruisci_indice(_CASA)
    assert indice.trova("sveglia") == []
    assert indice.verifica("automazione", "automation.sveglia") is None


def test_trova_un_automazione_per_nome():
    comportamento = [{"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
                      "corpo": {"trigger": []}, "origine": "file"}]
    trovate = costruisci_indice(_CASA, comportamento=comportamento).trova("spegni la sveglia")
    assert len(trovate) == 1
    assert trovate[0]["candidati"] == [{"tipo": "automazione", "riferimento": "automation.sveglia"}]


def test_trova_uno_script_per_nome():
    comportamento = [{"id": "script.buonanotte", "tipo": "script", "nome": "Buonanotte",
                      "corpo": None, "origine": "solo_stato"}]
    trovate = costruisci_indice(_CASA, comportamento=comportamento).trova("lancia buonanotte")
    assert len(trovate) == 1
    assert _riferimenti(trovate[0]) == {"script.buonanotte"}
    assert trovate[0]["candidati"][0]["tipo"] == "script"


def test_verifica_un_automazione_e_uno_script():
    comportamento = [
        {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia", "corpo": {}},
        {"id": "script.buonanotte", "tipo": "script", "nome": "Buonanotte", "corpo": None},
    ]
    indice = costruisci_indice(_CASA, comportamento=comportamento)
    assert indice.verifica("automazione", "automation.sveglia")["nome"] == "Sveglia"
    assert indice.verifica("script", "script.buonanotte")["nome"] == "Buonanotte"
    # Spazi di nomi diversi: un id di script non deve passare per un'automazione.
    assert indice.verifica("automazione", "script.buonanotte") is None


def test_automazione_e_script_con_lo_stesso_nome_sono_ambigui():
    comportamento = [
        {"id": "automation.buonanotte", "tipo": "automazione", "nome": "Buonanotte", "corpo": {}},
        {"id": "script.buonanotte", "tipo": "script", "nome": "Buonanotte", "corpo": None},
    ]
    trovate = costruisci_indice(_CASA, comportamento=comportamento).trova("buonanotte")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"automation.buonanotte", "script.buonanotte"}


def test_una_voce_di_comportamento_con_tipo_ignoto_non_si_indicizza():
    """Una voce col `tipo` che non e' ne' "automazione" ne' "script" (o
    senza id) non e' una voce di comportamento valida: si scarta invece di
    inventare un terzo tipo che ne' `guarda` ne' `verifica()` conoscono."""
    comportamento = [{"id": "scene.arrivo", "tipo": "scena", "nome": "Arrivo"},
                     {"id": None, "tipo": "automazione", "nome": "Senza id"}]
    indice = costruisci_indice(_CASA, comportamento=comportamento)
    assert indice.trova("arrivo") == []
    assert indice.trova("senza id") == []


def test_gli_alias_e_le_etichette_valgono_anche_per_il_comportamento():
    """Stessa disciplina degli altri tre archivi: non solo il nome."""
    comportamento = [{"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
                      "alias": ["buongiorno"]}]
    trovate = costruisci_indice(_CASA, comportamento=comportamento).trova("attiva buongiorno")
    assert _riferimenti(trovate[0]) == {"automation.sveglia"}


def test_l_indice_costruito_senza_ripiego_e_identico_a_prima():
    """I quattro chiamanti esistenti (handlers_memoria.py:118 e :184,
    casa/strumenti.py:430 e :512) non passano niente: la firma nuova non
    deve cambiargli nulla sotto i piedi -- e non deve marcare come dedotto
    cio' che il registro dichiara."""
    casa = {"aree": [{"id": "cucina", "nome": "Cucina", "alias": ["sala da pranzo"]}],
            "dispositivi": [], "entita": [{"id": "light.c", "nome": "Luce", "alias": []}]}

    for indice in (costruisci_indice(casa), costruisci_indice(casa, None)):
        trovate = indice.trova("in cucina accendi la luce")
        assert [_riferimenti(t) for t in trovate] == [{"cucina"}, {"light.c"}]
        assert [t["nome_visto"] for t in trovate] == ["cucina", "luce"]
        assert "nome_dedotto" not in indice.verifica("entita", "light.c")


# --- T8 (R2): le etichette stesse, come candidati -------------------------
#
# Prima di questo task un'etichetta entrava nell'indice SOLO come termine
# che porta a chi la porta (vedi test_si_cerca_per_etichetta in
# tests/test_casa_conoscenza_inespressa.py) -- mai come candidato essa
# stessa: il suo `label_id` non usciva da NESSUNA porta, il vicolo cieco
# piu' radicale della famiglia (R2). Vedi
# docs/design/2026-08-20-i-riferimenti.md.


def test_trova_un_etichetta_per_nome():
    casa = dict(_CASA, etichette=[{"id": "da_controllare", "nome": "Da controllare"}])
    trovate = costruisci_indice(casa).trova("segna da controllare")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert trovate[0]["candidati"] == [{"tipo": "etichetta", "riferimento": "da_controllare"}]


def test_verifica_un_etichetta():
    casa = dict(_CASA, etichette=[{"id": "da_controllare", "nome": "Da controllare"}])
    trovato = costruisci_indice(casa).verifica("etichetta", "da_controllare")
    assert trovato["nome"] == "Da controllare"


def test_un_etichetta_orfana_si_trova_lo_stesso():
    """Il caso che dimostra la chiusura del vicolo cieco: un'etichetta che
    NON e' ancora assegnata a niente (nessuna entita', area o dispositivo
    la porta) restava IRRAGGIUNGIBILE con la sola indicizzazione "come
    termine di chi la porta" -- qui si trova comunque, perche' e' indicizzata
    anche come candidato di se stessa."""
    casa = {"aree": [], "entita": [], "dispositivi": [], "piani": [],
            "categorie": [], "integrazioni": [],
            "etichette": [{"id": "vacanza", "nome": "Vacanza"}]}
    trovate = costruisci_indice(casa).trova("vacanza")
    assert _riferimenti(trovate[0]) == {"vacanza"}
    assert costruisci_indice(casa).verifica("etichetta", "vacanza") == {
        "id": "vacanza", "nome": "Vacanza"}


def test_due_etichette_omonime_sono_ambigue():
    """Stessa regola delle due «Bagno» e dei due piani «Mansarda»:
    l'ambiguita' si dichiara, non si sceglie in silenzio."""
    casa = dict(_CASA, etichette=[{"id": "e1", "nome": "Da controllare"},
                                  {"id": "e2", "nome": "Da controllare"}])
    trovate = costruisci_indice(casa).trova("da controllare")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"e1", "e2"}


def test_un_etichetta_senza_nome_si_indicizza_col_suo_id():
    """Stessa disciplina di `nomi_delle_etichette` (anagrafe.py): un
    registro con un'etichetta senza nome non produce un termine muto -- si
    usa l'id, l'unica cosa che si conosce di lei."""
    casa = dict(_CASA, etichette=[{"id": "senza_nome", "nome": None}])
    trovate = costruisci_indice(casa).trova("senza_nome")
    assert _riferimenti(trovate[0]) == {"senza_nome"}
