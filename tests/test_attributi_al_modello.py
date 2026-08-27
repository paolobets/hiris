"""Il difetto trovato dal proprietario usando il prodotto (2026-08-25).

Ha chiesto in chat se il riscaldamento fosse attivo. HIRIS ha risposto che
SI', citando due termostati «in modalita' riscaldamento ("heat")» -- ed era
falso: erano IMPOSTATI su riscaldamento ma `hvac_action: idle`, cioe' fermi.
Misurato in produzione: `guarda` su un termostato tornava
`{"stato": "heat", "stato_leggibile": "heat", ...}` e nient'altro.

La causa non era `entity_cache._to_minimal`: quella funzione raccoglie gia'
`hvac_action`, `current_temperature`, `temperature` dentro
`result["attributes"]` (`_DOMAIN_ATTRS["climate"]`). La causa era un anello
piu' in la': `casa.anagrafe.specchio_vivo` -- il punto da cui passano
`guarda`, `cerca` e il nucleo -- teneva solo `e.get("state")` e buttava
`e.get("attributes")` per intero, su OGNI dominio.

Questo file segua la CATENA INTERA -- dallo stato grezzo di Home Assistant
fino a cio' che `guarda` restituisce -- non i singoli anelli: un test per
anello (come esistevano gia' per `_to_minimal`) non avrebbe mai visto questo
difetto, perche' ogni anello faceva il proprio lavoro.
"""
from hiris.app.casa.anagrafe import specchio_vivo, traduci_stato
from hiris.app.casa.domande import guarda
from hiris.app.proxy.entity_cache import _to_minimal

# Lo stato grezzo COM'E' DAVVERO sull'impianto del proprietario: impostato su
# riscaldamento (`hvac_mode`/`state` = "heat"), ma FERMO (`hvac_action`:
# "idle"), target 17, temperatura reale 25 -- il caso che ha prodotto la
# frase falsa in chat.
_RAW_TERMOSTATO = {
    "entity_id": "climate.matrimoniale", "state": "heat",
    "last_changed": "2026-08-25T09:00:00+00:00",
    "attributes": {
        "friendly_name": "Termostato Matrimoniale",
        "hvac_mode": "heat", "hvac_action": "idle",
        "current_temperature": 25.2, "temperature": 17,
    },
}

_CASA = {
    "aree": [{"id": "camera", "nome": "Camera matrimoniale"}],
    "entita": [
        {"id": "climate.matrimoniale", "nome": "Termostato Matrimoniale",
         "area_id": "camera", "dispositivo_id": None, "classe": None,
         "disabilitata": False},
    ],
    "dispositivi": [],
}


def _specchio_del_termostato():
    return specchio_vivo([_to_minimal(_RAW_TERMOSTATO)])


# --- ogni anello, presi da soli -- gia' passavano prima di questa fetta ---

def test_a_to_minimal_raccoglie_gia_hvac_action():
    minimo = _to_minimal(_RAW_TERMOSTATO)
    assert minimo["attributes"]["hvac_action"] == "idle"
    assert minimo["attributes"]["temperature"] == 17


# --- l'anello che il difetto attraversava --------------------------------

def test_b_lo_specchio_portava_solo_lo_stato_nudo_PRIMA_del_fix():
    """Pinna il comportamento NUOVO: se qualcuno rimette `stato[id] =
    e.get("state")` senza il resto, `attributi` torna vuoto e questo test
    arrossisce."""
    stato, _n, _u, _c, _d, attributi = _specchio_del_termostato()
    assert stato["climate.matrimoniale"] == "heat"
    assert attributi["climate.matrimoniale"]["hvac_action"] == "idle"
    assert attributi["climate.matrimoniale"]["current_temperature"] == 25.2


# --- LA PROVA CHE CONTA: la catena intera fino a guarda -------------------

def test_c_guarda_su_un_entita_non_dice_piu_solo_heat():
    """LA PROVA CHE CONTA. Prima di questa fetta questo dict non aveva la
    chiave "attributi" e "stato_leggibile" valeva "heat" -- la stessa forma
    letta dal proprietario in chat."""
    stato, nomi, unita, classi, da_quando, attributi = _specchio_del_termostato()
    dettaglio = guarda(_CASA, [], [], stato, "entita", "climate.matrimoniale",
                       nomi_di_ripiego=nomi, unita_vive=unita, classi_vive=classi,
                       da_quando_vive=da_quando, attributi_vivi=attributi)
    assert dettaglio["esiste"] is True
    assert dettaglio["stato"] == "heat"
    assert dettaglio["attributi"]["hvac_action"] == "idle"
    assert dettaglio["attributi"]["current_temperature"] == 25.2
    assert dettaglio["attributi"]["temperature"] == 17
    # Il cuore del difetto: lo stato_leggibile non deve poter essere letto
    # come "sta scaldando" quando il termostato e' fermo.
    assert dettaglio["stato_leggibile"] != "heat"
    assert "fermo" in dettaglio["stato_leggibile"]
    assert "sta scaldando" not in dettaglio["stato_leggibile"]


def test_d_guarda_su_un_termostato_che_sta_scaldando_lo_dice_diverso():
    """La prova per mutazione della precedente: una versione del fix che
    scrivesse SEMPRE "fermo" (hardcoded) passerebbe il test C e fallirebbe
    qui -- serve leggere `hvac_action` davvero, non solo dichiararne uno."""
    raw = {**_RAW_TERMOSTATO,
           "attributes": {**_RAW_TERMOSTATO["attributes"], "hvac_action": "heating"}}
    stato, _nomi, _unita, _classi, _da_quando, attributi = specchio_vivo([_to_minimal(raw)])
    dettaglio = guarda(_CASA, [], [], stato, "entita", "climate.matrimoniale",
                       attributi_vivi=attributi)
    assert "sta scaldando" in dettaglio["stato_leggibile"]
    assert "fermo" not in dettaglio["stato_leggibile"]


def test_e_senza_hvac_action_non_si_inventa_un_funzionamento():
    """Un'integrazione che non manda `hvac_action` (o un attributo fuori
    vocabolario): lo stato_leggibile dichiara solo l'impostazione, non
    inventa "fermo" ne' "sta scaldando" -- nessuno dei due sarebbe vero."""
    assert traduci_stato("heat", None, "climate", None) == "impostato su riscaldamento"
    assert "fermo" not in traduci_stato("heat", None, "climate", None)
    assert "sta scaldando" not in traduci_stato("heat", None, "climate", None)


# --- il confine deciso: attributi SOLO sul dettaglio, mai nelle liste -----

def test_f_un_area_NON_porta_gli_attributi_di_ogni_entita():
    """Decisione del proprietario: un'area puo' elencare venti entita', e
    mettere tutti gli attributi di ognuna dentro quell'elenco gonfierebbe la
    risposta di un dato che nessuno ha chiesto per la singola cosa. Il
    dettaglio di UNA entita' (`_guarda_entita`) e' l'unico posto dove esce."""
    stato, _nomi, _unita, _classi, _da_quando, attributi = _specchio_del_termostato()
    dettaglio = guarda(_CASA, [], [], stato, "area", "camera", attributi_vivi=attributi)
    entita = dettaglio["entita"][0]
    assert "attributi" not in entita, (
        "gli attributi grezzi sono usciti in una LISTA: violano il confine deciso")


def test_g_un_area_porta_comunque_lo_stato_leggibile_onesto():
    """Il confine sopra riguarda il BLOB grezzo, non `stato_leggibile`: quel
    campo esce gia' su ogni ramo, e deve restare onesto ovunque -- la stessa
    domanda (Camera: il termostato sta scaldando?) non puo' avere due
    risposte diverse a seconda che si chiami `guarda('area', ...)` o
    `guarda('entita', ...)` (fondamenta 3)."""
    stato, _nomi, _unita, _classi, _da_quando, attributi = _specchio_del_termostato()
    dettaglio = guarda(_CASA, [], [], stato, "area", "camera", attributi_vivi=attributi)
    entita = dettaglio["entita"][0]
    assert entita["stato_leggibile"] == "impostato su riscaldamento, fermo"


def test_h_un_dispositivo_NON_porta_gli_attributi_ma_lo_stato_leggibile_si():
    casa = {
        "aree": [], "dispositivi": [{"id": "dev_t", "nome": "Termostato camera",
                                      "disabilitato": False}],
        "entita": [{"id": "climate.matrimoniale", "nome": "Termostato Matrimoniale",
                    "area_id": None, "dispositivo_id": "dev_t", "classe": None,
                    "disabilitata": False}],
    }
    stato, _nomi, _unita, _classi, _da_quando, attributi = _specchio_del_termostato()
    dettaglio = guarda(casa, [], [], stato, "dispositivo", "dev_t", attributi_vivi=attributi)
    entita = dettaglio["entita"][0]
    assert "attributi" not in entita
    assert entita["stato_leggibile"] == "impostato su riscaldamento, fermo"


def test_i_senza_attributi_vivi_guarda_si_comporta_come_prima():
    """Nessuna rottura per chi non passa `attributi_vivi` (retrocompatibile):
    niente chiave "attributi", e `stato_leggibile` degrada onestamente
    all'impostazione sola -- non torna "heat" nudo, che sarebbe il vecchio
    difetto con un'altra faccia."""
    dettaglio = guarda(_CASA, [], [], {"climate.matrimoniale": "heat"},
                       "entita", "climate.matrimoniale")
    assert "attributi" not in dettaglio
    assert dettaglio["stato_leggibile"] == "impostato su riscaldamento"
