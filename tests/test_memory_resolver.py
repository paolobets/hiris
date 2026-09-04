import re

import pytest

from hiris.app.memory.resolver import costruisci_indice

_HOME_SPACE = {
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
def lookup():
    return costruisci_indice(_HOME_SPACE)


def test_trova_un_area_per_nome(lookup):
    trovate = lookup.find("d'inverno la sala da pranzo sta bene a 19 gradi")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert [(c["tipo"], c["riferimento"]) for c in trovate[0]["candidati"]] == [
        ("area", "sala_pranzo")
    ]
    assert trovate[0]["nome_visto"] == "sala da pranzo"


def test_trova_un_area_per_alias(lookup):
    """Gli alias sono sinonimi DICHIARATI dall'utente in Home Assistant per
    l'assistente vocale: significato dato, non dedotto."""
    trovate = lookup.find("nel tinello fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert _riferimenti(trovate[0]) == {"sala_pranzo"}
    assert trovate[0]["nome_visto"] == "tinello"


def test_le_maiuscole_e_gli_accenti_non_contano(lookup):
    trovate = lookup.find("LA SALA DA PRANZO")
    assert len(trovate) == 1
    assert _riferimenti(trovate[0]) == {"sala_pranzo"}


def test_trova_piu_cose_in_una_frase(lookup):
    trovate = lookup.find("in cucina la luce cucina resta accesa")
    assert {r for t in trovate for r in _riferimenti(t)} == {"cucina", "light.cucina"}
    assert all(t["ambiguo"] is False for t in trovate)


def test_preferisce_il_nome_piu_lungo(lookup):
    """«Sala da pranzo» contiene «sala»: se vincesse il piu' corto, l'ancora
    punterebbe alla cosa sbagliata."""
    home_space = dict(_HOME_SPACE, aree=_HOME_SPACE["aree"] + [{"id": "sala", "nome": "Sala",
                                              "alias": [], "piano_id": "terra"}])
    trovate = costruisci_indice(home_space).find("la sala da pranzo")
    assert len(trovate) == 1
    assert _riferimenti(trovate[0]) == {"sala_pranzo"}


def test_una_parola_dentro_un_altra_non_conta(lookup):
    """«cucinare» non nomina la cucina."""
    assert lookup.find("mi piace cucinare la sera") == []


def test_niente_di_riconosciuto_non_e_un_errore(lookup):
    assert lookup.find("domani piove") == []


def test_una_casa_vuota_non_esplode():
    vuota = {key: [] for key in _HOME_SPACE}
    assert costruisci_indice(vuota).find("la sala da pranzo") == []


def test_verifica_un_ancora_proposta_dal_modello(lookup):
    """La semantica la fa il modello: «salotto» -> area soggiorno lo risolve
    lui, che ha la casa in contesto. Qui si verifica solo che esista."""
    trovata = lookup.verify("area", "sala_pranzo")
    assert trovata["nome"] == "Sala da pranzo"


def test_un_ancora_inventata_dal_modello_non_passa(lookup):
    """Il modello propone, il codice restringe: se non esiste, non si scrive."""
    assert lookup.verify("area", "taverna") is None
    assert lookup.verify("entita", "light.inesistente") is None


def test_verifica_non_confonde_i_tipi(lookup):
    """Un identificatore di entita' passato come area non deve passare per
    somiglianza: sono spazi di nomi diversi."""
    assert lookup.verify("area", "climate.sala") is None


def test_un_nome_con_la_punteggiatura_si_trova():
    """«Bagno (piano terra)» non veniva trovato MAI, nemmeno sul nome esatto:
    il confine di parola finale pretendeva una lettera dopo la parentesi."""
    home_space = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno (piano terra)", "alias": []}])
    lookup = costruisci_indice(home_space)

    trovate = lookup.find("il bagno (piano terra) e' freddo")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert _riferimenti(trovate[0]) == {"bagno_terra"}

    assert lookup.find("bagno (piano terra)")


def test_due_aree_omonime_sono_ambigue_non_una_sola():
    """Due «Bagno» su piani diversi: prima vinceva il primo inserito, in
    silenzio, e l'altro era irraggiungibile."""
    home_space = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno", "alias": []},
                           {"id": "bagno_primo", "nome": "Bagno", "alias": []}])
    trovate = costruisci_indice(home_space).find("il bagno e' sporco")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"bagno_terra", "bagno_primo"}


def test_un_alias_che_collide_col_nome_di_un_altra_area_e_ambiguo():
    """«Soggiorno» ha alias «salotto», ed esiste anche un'area «Salotto»."""
    home_space = _casa_con_aree([{"id": "soggiorno", "nome": "Soggiorno", "alias": ["salotto"]},
                           {"id": "salotto_vero", "nome": "Salotto", "alias": []}])
    trovate = costruisci_indice(home_space).find("in salotto fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"soggiorno", "salotto_vero"}


def test_cucinare_non_nomina_ancora_la_cucina():
    """Il fix del confine non deve aprire la porta ai falsi positivi."""
    home_space = _casa_con_aree([{"id": "cucina", "nome": "Cucina", "alias": []}])
    assert costruisci_indice(home_space).find("mi piace cucinare la sera") == []


def test_nome_visto_conserva_il_testo_originale():
    """`nome_visto` e' cio' che l'utente ha scritto, non il testo
    normalizzato su cui si cerca -- oggi non morde perche' nessuno lo
    archivia, ma nella fetta E sarebbe gia' una riscrittura silenziosa
    (memory/store.py, regola 1: il testo e' la verita')."""
    home_space = _casa_con_aree(
        [{"id": "camera_niccolo", "nome": "Camera di Niccolo'", "alias": []}])
    lookup = costruisci_indice(home_space)

    trovate = lookup.find("nella Camera di Niccolo' fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["nome_visto"] == "Camera di Niccolo'"


def test_nome_visto_sopravvive_a_spazi_multipli():
    """La compressione degli spazi multipli nel testo normalizzato sposta le
    posizioni: `nome_visto` deve comunque recuperare lo spezzone giusto del
    testo originale, spazi doppi compresi."""
    home_space = _casa_con_aree([{"id": "sala_pranzo", "nome": "Sala da pranzo", "alias": []}])
    lookup = costruisci_indice(home_space)

    trovate = lookup.find("nella sala  da   pranzo fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["nome_visto"] == "sala  da   pranzo"


def test_le_espressioni_non_si_compilano_prima_del_primo_trova():
    """`costruisci_indice()` gira a ogni GET/PATCH di /api/memories, ma quelle
    rotte usano solo `verifica()` -- un accesso a dizionario. Compilare i
    pattern li' sarebbe lavoro morto (misurato: 16,8 ms a 380 voci): si
    compila pigri, alla prima trova()."""
    home_space = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno (piano terra)", "alias": []}])
    lookup = costruisci_indice(home_space)
    assert lookup._termini_compilati is None


def test_le_espressioni_si_compilano_una_volta_sola():
    """Il costo passava da 7 a 76 ms intorno alle 300 entita', perche' la
    cache implicita di CPython ha un tetto di 512 pattern condiviso col
    processo. Un controllo puramente strutturale ("esistono dei
    re.Pattern?") passerebbe anche se trova() li ricompilasse a ogni
    chiamata: qui si prova che gli OGGETTI pattern restano gli STESSI fra
    due chiamate di trova(), non solo che qualche pattern esiste."""
    home_space = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno (piano terra)", "alias": []}])
    lookup = costruisci_indice(home_space)

    lookup.find("il bagno (piano terra) e' freddo")
    prima = lookup._termini()
    assert prima
    assert all(isinstance(pattern, re.Pattern) for _, pattern in prima)

    lookup.find("un'altra frase qualsiasi, per chiamare trova() una seconda volta")
    seconda = lookup._termini()

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
    la forma esatta che home_space/store.py:133 produce su questa casa."""
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
    lookup = costruisci_indice(_casa_senza_nomi())

    # solo l'area, mai le due luci
    assert lookup.find("accendi le abat-jour del salotto") == lookup.find("in salotto")
    assert lookup.find("light.abat_jour_1") == []
    assert lookup.find("abat jour 1") == []
    assert lookup.verify("entita", "light.abat_jour_1") is not None
    assert "nome_dedotto" not in lookup.verify("entita", "light.abat_jour_1")


def test_col_friendly_name_l_entita_senza_nome_si_trova():
    """Il guadagno: e' cio' che sarebbe costato quattro giri di `cerca`."""
    lookup = costruisci_indice(_casa_senza_nomi(),
                               {"light.abat_jour_1": "Abat-jour"})

    trovati = lookup.find("accendi l'abat-jour")
    assert [c["riferimento"] for v in trovati for c in v["candidati"]] == ["light.abat_jour_1"]


def test_il_nome_dedotto_e_marcato_e_non_sovrascrive_quello_del_registro():
    """Un nome dedotto non si spaccia per dichiarato: chi confronta i nomi
    che l'utente ha scritto davvero non deve inciampare in uno che non ha
    mai scritto."""
    lookup = costruisci_indice(_casa_senza_nomi(),
                               {"light.abat_jour_1": "Abat-jour"})

    entry = lookup.verify("entita", "light.abat_jour_1")
    assert entry["nome_dedotto"] == "Abat-jour"
    assert not (entry.get("nome") or "")


def test_il_nome_dedotto_e_marcato_anche_sulle_voci_di_tutti():
    """`tutti("entita")` e' l'altra porta pubblica sull'anagrafe
    (memory/interpretation.py la usa per dedurre l'unita' di un'area): il
    marchio deve esserci anche di la', o "dedotto" si vede da una porta e
    non dall'altra. Il resto della riga del registro sopravvive al marchio:
    la copia e' una copia, non una sostituzione."""
    lookup = costruisci_indice(_casa_senza_nomi(),
                               {"light.abat_jour_1": "Abat-jour"})

    per_id = {v["id"]: v for v in lookup.tutti("entita")}
    assert per_id["light.abat_jour_1"]["nome_dedotto"] == "Abat-jour"
    assert per_id["light.abat_jour_1"]["area_id"] == "salotto"
    assert per_id["light.abat_jour_1"]["piattaforma"] == "shelly"
    assert "nome_dedotto" not in per_id["light.abat_jour_2"]


def test_il_marchio_non_tocca_la_casa_del_chiamante():
    """`voce` e' il dizionario che `HomeSpaceStore.leggi()` ha appena
    costruito per il chiamante: marcarlo in place accoppierebbe l'indice al
    ciclo di vita di una struttura che non gli appartiene -- e il chiamante
    si ritroverebbe un nome dedotto in una casa che credeva del registro."""
    home_space = _casa_senza_nomi()
    costruisci_indice(home_space, {"light.abat_jour_1": "Abat-jour"})

    assert "nome_dedotto" not in home_space["entita"][0]


def test_il_ripiego_non_tocca_chi_un_nome_ce_l_ha():
    """Mutazione uccisa: applicare il ripiego sempre invece che solo sul
    vuoto. Il nome scelto dall'utente vince, e' la regola di
    home_space/store.py:130-133."""
    home_space = {"aree": [], "dispositivi": [],
            "entita": [{"id": "light.x", "nome": "Piantana", "alias": []}]}
    lookup = costruisci_indice(home_space, {"light.x": "Lampada da terra"})

    assert lookup.find("lampada da terra") == []
    assert lookup.find("la piantana")
    assert "nome_dedotto" not in lookup.verify("entita", "light.x")


def test_il_ripiego_non_si_applica_ad_aree_e_dispositivi():
    """Lo specchio dello stato non ha friendly_name per aree e dispositivi:
    un ripiego li' sarebbe di nuovo un id travestito da nome."""
    home_space = {"aree": [{"id": "salotto", "nome": "", "alias": []}],
            "dispositivi": [{"id": "dev1", "nome": None, "alias": []}], "entita": []}
    lookup = costruisci_indice(home_space, {"salotto": "Salotto", "dev1": "Irrigazione"})

    assert lookup.find("salotto") == [] and lookup.find("irrigazione") == []
    assert "nome_dedotto" not in lookup.verify("area", "salotto")
    assert "nome_dedotto" not in lookup.verify("dispositivo", "dev1")


def test_un_ripiego_a_soli_spazi_non_crea_ne_termine_ne_marchio():
    """Un `friendly_name` fatto di spazi non e' un nome: non deve produrre
    un termine vuoto ne' una voce che si dichiara "dedotta" senza nulla da
    mostrare."""
    lookup = costruisci_indice(_casa_senza_nomi(), {"light.abat_jour_1": "   "})

    assert lookup.find("accendi l'abat-jour   del salotto") == lookup.find("in salotto")
    assert "nome_dedotto" not in lookup.verify("entita", "light.abat_jour_1")


def test_un_nome_del_registro_fatto_di_soli_spazi_non_batte_il_ripiego():
    """Un nome che una volta normalizzato non e' nulla non e' un nome: se
    battesse il ripiego, la voce si dichiarerebbe "dedotta" e resterebbe
    comunque introvabile -- marchiata e muta."""
    home_space = {"aree": [], "dispositivi": [],
            "entita": [{"id": "light.x", "nome": "   ", "alias": []}]}
    lookup = costruisci_indice(home_space, {"light.x": "Abat-jour"})

    assert _riferimenti(lookup.find("l'abat-jour")[0]) == {"light.x"}
    assert lookup.verify("entita", "light.x")["nome_dedotto"] == "Abat-jour"


def test_gli_alias_restano_indicizzati_anche_quando_il_nome_e_dedotto():
    """Gli alias sono sinonimi DICHIARATI: il ripiego si aggiunge al nome
    mancante, non prende il posto di cio' che l'utente ha scritto."""
    home_space = {"aree": [], "dispositivi": [],
            "entita": [{"id": "light.x", "nome": None, "alias": ["piantana"]}]}
    lookup = costruisci_indice(home_space, {"light.x": "Abat-jour"})

    assert _riferimenti(lookup.find("la piantana")[0]) == {"light.x"}
    assert _riferimenti(lookup.find("l'abat-jour")[0]) == {"light.x"}


def test_un_nome_dedotto_che_collide_con_un_nome_dichiarato_e_ambiguo():
    """Il dedotto entra nello stesso spazio dei nomi dichiarati, quindi puo'
    collidere con loro -- e su questa casa succedera' spesso, perche' il
    dedotto e' la norma. L'indice non sceglie: dichiara l'ambiguita' come
    farebbe per due aree omonime."""
    home_space = {"aree": [{"id": "cucina", "nome": "Cucina", "alias": []}],
            "dispositivi": [],
            "entita": [{"id": "valve.giardino_cucina", "nome": None, "alias": []}]}
    lookup = costruisci_indice(home_space, {"valve.giardino_cucina": "Cucina"})

    trovate = lookup.find("in cucina")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"cucina", "valve.giardino_cucina"}


def test_le_entita_senza_stato_vivo_restano_senza_nome_e_non_spariscono():
    """Misurato: 849 entita' vive contro 1.225 nel registro. Per le 376
    restanti non esiste un `friendly_name` da nessuna parte, e il ripiego
    non le copre. Restano fuori da `find()` -- come oggi -- ma non
    spariscono e non si inventa loro un nome: dichiarato, non nascosto."""
    lookup = costruisci_indice(_casa_senza_nomi(),
                               {"light.abat_jour_1": "Abat-jour"})

    assert _riferimenti(lookup.find("l'abat-jour")[0]) == {"light.abat_jour_1"}
    senza_stato_vivo = lookup.verify("entita", "light.abat_jour_2")
    assert senza_stato_vivo is not None
    assert not (senza_stato_vivo.get("nome") or "")
    assert "nome_dedotto" not in senza_stato_vivo


# -- R2 (T7): piani, automazioni e script -----------------------------------
#
# Prima di questo task nessuna sequenza di chiamate produceva mai un id di
# piano, automazione o script: `_ARCHIVI` non li conosceva. Vedi
# docs/design/2026-08-20-i-riferimenti.md.


def test_trova_un_piano_per_nome():
    home_space = dict(_HOME_SPACE, piani=[{"id": "terra", "nome": "Piano terra", "livello": 0}])
    trovate = costruisci_indice(home_space).find("accendi tutto al piano terra")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert trovate[0]["candidati"] == [{"tipo": "piano", "riferimento": "terra"}]


def test_verifica_un_piano():
    home_space = dict(_HOME_SPACE, piani=[{"id": "terra", "nome": "Piano terra", "livello": 0}])
    trovato = costruisci_indice(home_space).verify("piano", "terra")
    assert trovato["nome"] == "Piano terra"


def test_due_piani_omonimi_sono_ambigui():
    """Stessa regola delle due «Bagno»: l'ambiguita' si dichiara, non si
    sceglie in silenzio in base all'ordine di raccolta."""
    home_space = dict(_HOME_SPACE, piani=[{"id": "p1", "nome": "Mansarda", "livello": 2},
                              {"id": "p2", "nome": "Mansarda", "livello": 2}])
    trovate = costruisci_indice(home_space).find("in mansarda")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"p1", "p2"}


def test_senza_comportamento_nessuna_automazione_si_indicizza():
    """Il parametro e' opzionale (default `None`): i chiamanti che ancora
    non lo passano (`_remember`, le pagine di `handlers_memory.py`) non
    devono vedere comparire nulla sotto "automazione"/"script"."""
    lookup = costruisci_indice(_HOME_SPACE)
    assert lookup.find("sveglia") == []
    assert lookup.verify("automazione", "automation.sveglia") is None


def test_trova_un_automazione_per_nome():
    behavior = [{"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
                      "corpo": {"trigger": []}, "origine": "file"}]
    trovate = costruisci_indice(_HOME_SPACE, behavior=behavior).find("spegni la sveglia")
    assert len(trovate) == 1
    assert trovate[0]["candidati"] == [{"tipo": "automazione", "riferimento": "automation.sveglia"}]


def test_trova_uno_script_per_nome():
    behavior = [{"id": "script.buonanotte", "tipo": "script", "nome": "Buonanotte",
                      "corpo": None, "origine": "solo_stato"}]
    trovate = costruisci_indice(_HOME_SPACE, behavior=behavior).find("lancia buonanotte")
    assert len(trovate) == 1
    assert _riferimenti(trovate[0]) == {"script.buonanotte"}
    assert trovate[0]["candidati"][0]["tipo"] == "script"


def test_verifica_un_automazione_e_uno_script():
    behavior = [
        {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia", "corpo": {}},
        {"id": "script.buonanotte", "tipo": "script", "nome": "Buonanotte", "corpo": None},
    ]
    lookup = costruisci_indice(_HOME_SPACE, behavior=behavior)
    assert lookup.verify("automazione", "automation.sveglia")["nome"] == "Sveglia"
    assert lookup.verify("script", "script.buonanotte")["nome"] == "Buonanotte"
    # Spazi di nomi diversi: un id di script non deve passare per un'automazione.
    assert lookup.verify("automazione", "script.buonanotte") is None


def test_automazione_e_script_con_lo_stesso_nome_sono_ambigui():
    behavior = [
        {"id": "automation.buonanotte", "tipo": "automazione", "nome": "Buonanotte", "corpo": {}},
        {"id": "script.buonanotte", "tipo": "script", "nome": "Buonanotte", "corpo": None},
    ]
    trovate = costruisci_indice(_HOME_SPACE, behavior=behavior).find("buonanotte")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"automation.buonanotte", "script.buonanotte"}


def test_una_voce_di_comportamento_con_tipo_ignoto_non_si_indicizza():
    """Una voce col `tipo` che non e' ne' "automazione" ne' "script" (o
    senza id) non e' una voce di comportamento valida: si scarta invece di
    inventare un terzo tipo che ne' `guarda` ne' `verifica()` conoscono."""
    behavior = [{"id": "scene.arrivo", "tipo": "scena", "nome": "Arrivo"},
                     {"id": None, "tipo": "automazione", "nome": "Senza id"}]
    lookup = costruisci_indice(_HOME_SPACE, behavior=behavior)
    assert lookup.find("arrivo") == []
    assert lookup.find("senza id") == []


def test_gli_alias_e_le_etichette_valgono_anche_per_il_comportamento():
    """Stessa disciplina degli altri tre archivi: non solo il nome."""
    behavior = [{"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
                      "alias": ["buongiorno"]}]
    trovate = costruisci_indice(_HOME_SPACE, behavior=behavior).find("attiva buongiorno")
    assert _riferimenti(trovate[0]) == {"automation.sveglia"}


def test_l_indice_costruito_senza_ripiego_e_identico_a_prima():
    """I quattro chiamanti esistenti (handlers_memory.py:118 e :184,
    home_space/tools.py:430 e :512) non passano niente: la firma nuova non
    deve cambiargli nulla sotto i piedi -- e non deve marcare come dedotto
    cio' che il registro dichiara."""
    home_space = {"aree": [{"id": "cucina", "nome": "Cucina", "alias": ["sala da pranzo"]}],
            "dispositivi": [], "entita": [{"id": "light.c", "nome": "Luce", "alias": []}]}

    for lookup in (costruisci_indice(home_space), costruisci_indice(home_space, None)):
        trovate = lookup.find("in cucina accendi la luce")
        assert [_riferimenti(t) for t in trovate] == [{"cucina"}, {"light.c"}]
        assert [t["nome_visto"] for t in trovate] == ["cucina", "luce"]
        assert "nome_dedotto" not in lookup.verify("entita", "light.c")


# --- T8 (R2): le etichette stesse, come candidati -------------------------
#
# Prima di questo task un'etichetta entrava nell'indice SOLO come termine
# che porta a chi la porta (vedi test_si_cerca_per_etichetta in
# tests/test_home_space_unexpressed_knowledge.py) -- mai come candidato essa
# stessa: il suo `label_id` non usciva da NESSUNA porta, il vicolo cieco
# piu' radicale della famiglia (R2). Vedi
# docs/design/2026-08-20-i-riferimenti.md.


def test_trova_un_etichetta_per_nome():
    home_space = dict(_HOME_SPACE, etichette=[{"id": "da_controllare", "nome": "Da controllare"}])
    trovate = costruisci_indice(home_space).find("segna da controllare")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert trovate[0]["candidati"] == [{"tipo": "etichetta", "riferimento": "da_controllare"}]


def test_verifica_un_etichetta():
    home_space = dict(_HOME_SPACE, etichette=[{"id": "da_controllare", "nome": "Da controllare"}])
    trovato = costruisci_indice(home_space).verify("etichetta", "da_controllare")
    assert trovato["nome"] == "Da controllare"


def test_un_etichetta_orfana_si_trova_lo_stesso():
    """Il caso che dimostra la chiusura del vicolo cieco: un'etichetta che
    NON e' ancora assegnata a niente (nessuna entita', area o dispositivo
    la porta) restava IRRAGGIUNGIBILE con la sola indicizzazione "come
    termine di chi la porta" -- qui si trova comunque, perche' e' indicizzata
    anche come candidato di se stessa."""
    home_space = {"aree": [], "entita": [], "dispositivi": [], "piani": [],
            "categorie": [], "integrazioni": [],
            "etichette": [{"id": "vacanza", "nome": "Vacanza"}]}
    trovate = costruisci_indice(home_space).find("vacanza")
    assert _riferimenti(trovate[0]) == {"vacanza"}
    assert costruisci_indice(home_space).verify("etichetta", "vacanza") == {
        "id": "vacanza", "nome": "Vacanza"}


def test_due_etichette_omonime_sono_ambigue():
    """Stessa regola delle due «Bagno» e dei due piani «Mansarda»:
    l'ambiguita' si dichiara, non si sceglie in silenzio."""
    home_space = dict(_HOME_SPACE, etichette=[{"id": "e1", "nome": "Da controllare"},
                                  {"id": "e2", "nome": "Da controllare"}])
    trovate = costruisci_indice(home_space).find("da controllare")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"e1", "e2"}


def test_un_etichetta_senza_nome_si_indicizza_col_suo_id():
    """Stessa disciplina di `label_names` (anagrafe.py): un
    registro con un'etichetta senza nome non produce un termine muto -- si
    usa l'id, l'unica cosa che si conosce di lei."""
    home_space = dict(_HOME_SPACE, etichette=[{"id": "senza_nome", "nome": None}])
    trovate = costruisci_indice(home_space).find("senza_nome")
    assert _riferimenti(trovate[0]) == {"senza_nome"}


def test_platforms_key_is_normalized_and_entities_without_one_are_skipped():
    """Prova diretta di `Lookup.platforms()`, senza passare da `search()`:
    prima di questa prova, togliere `_normalize()` da UNO solo dei due lati
    che lo applicano (qui, in `resolver.py`, o dal lato di `queries.py` che
    cerca) lasciava la suite tutta verde -- nessuna prova esercitava la
    normalizzazione della chiave in isolamento, solo indirettamente
    attraverso `search`, dove un secondo `_normalize` sul testo cercato
    poteva mascherare l'assenza del primo.

    Mutazione: togliere `_normalize(dominio)` nella costruzione della mappa
    -- il test torna rosso perche' la chiave resta `"Hydrawise "` (maiuscola
    e spazio in coda) invece di `"hydrawise"`, e
    `platforms["hydrawise"]` solleva `KeyError`."""
    home_space = dict(_HOME_SPACE, entita=[
        {"id": "valve.giardino", "nome": "Irrigazione", "piattaforma": "Hydrawise ",
         "alias": [], "area_id": None, "classe": None, "unita": None},
        {"id": "light.cucina", "nome": "Faretti", "piattaforma": "",
         "alias": [], "area_id": None, "classe": None, "unita": None},
    ])
    platforms = costruisci_indice(home_space).platforms()
    assert platforms == {"hydrawise": ["valve.giardino"]}
