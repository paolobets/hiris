"""Il difetto trovato dal proprietario usando il prodotto (2026-08-25).

Ha chiesto in chat se il riscaldamento fosse attivo. HIRIS ha risposto che
SI', citando due termostati «in modalita' riscaldamento ("heat")» -- ed era
falso: erano IMPOSTATI su riscaldamento ma `hvac_action: idle`, cioe' fermi.
Misurato in produzione: `guarda` su un termostato tornava
`{"stato": "heat", "readable_state": "heat", ...}` e nient'altro.

La causa non era `entity_cache._to_minimal`: quella funzione raccoglie gia'
`hvac_action`, `current_temperature`, `temperature` dentro
`result["attributes"]` (`_DOMAIN_ATTRS["climate"]`). La causa era un anello
piu' in la': `home_space.topology.live_mirror` -- il punto da cui passano
`guarda`, `cerca` e il nucleo -- teneva solo `e.get("state")` e buttava
`e.get("attributes")` per intero, su OGNI dominio.

Questo file segua la CATENA INTERA -- dallo stato grezzo di Home Assistant
fino a cio' che `guarda` restituisce -- non i singoli anelli: un test per
anello (come esistevano gia' per `_to_minimal`) non avrebbe mai visto questo
difetto, perche' ogni anello faceva il proprio lavoro.

Aggiornato il 07/09/2026 (fetta dell'eredita' degli attributi): `hvac_action`
e le due temperature escono adesso sotto la cesta `valori` -- Home Assistant
le dichiara `ClimateEntityStateAttribute`, cioe' com'e' ADESSO, non cosa il
termostato PUO' fare. E `hvac_mode` e' sparito dal caso di prova perche' e'
sparito da Home Assistant: la modalita' e' lo `state`, non un attributo
(`components/climate/__init__.py:289-299`). Il difetto che questo file
sorveglia e' identico: lo `state` da solo mente.
"""
from hiris.app.home_space.house import House
from hiris.app.home_space.queries import view
from hiris.app.home_space.topology import Mirror, live_mirror, readable_state
from hiris.app.proxy.entity_cache import _to_minimal
from tests._house_translations import house_translations

# Lo stato grezzo COM'E' DAVVERO sull'impianto del proprietario: impostato su
# riscaldamento (`hvac_mode`/`state` = "heat"), ma FERMO (`hvac_action`:
# "idle"), target 17, temperatura reale 25 -- il caso che ha prodotto la
# frase falsa in chat.
_RAW_TERMOSTATO = {
    "entity_id": "climate.matrimoniale", "state": "heat",
    "last_changed": "2026-08-25T09:00:00+00:00",
    "attributes": {
        "friendly_name": "Termostato Matrimoniale",
        "hvac_action": "idle",
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
    return live_mirror([_to_minimal(_RAW_TERMOSTATO)])


# --- ogni anello, presi da soli -- gia' passavano prima di questa fetta ---

def test_a_to_minimal_raccoglie_gia_hvac_action():
    minimo = _to_minimal(_RAW_TERMOSTATO)
    assert minimo["attributes"]["values"]["hvac_action"] == "idle"
    assert minimo["attributes"]["values"]["temperature"] == 17


# --- l'anello che il difetto attraversava --------------------------------

def test_b_lo_specchio_portava_solo_lo_stato_nudo_PRIMA_del_fix():
    """Pinna il comportamento NUOVO: se qualcuno rimette `stato[id] =
    e.get("state")` senza il resto, `attributi` torna vuoto e questo test
    arrossisce."""
    mirror = _specchio_del_termostato()
    assert mirror.state["climate.matrimoniale"] == "heat"
    valori = mirror.attributes["climate.matrimoniale"]["values"]
    assert valori["hvac_action"] == "idle"
    assert valori["current_temperature"] == 25.2


# --- LA PROVA CHE CONTA: la catena intera fino a guarda -------------------

def test_c_guarda_su_un_entita_non_dice_piu_solo_heat():
    """LA PROVA CHE CONTA. Prima di questa fetta questo dict non aveva la
    chiave "attributi" e "stato_leggibile" valeva "heat" -- la stessa forma
    letta dal proprietario in chat."""
    mirror = _specchio_del_termostato()
    dettaglio = view(House(_CASA, mirror), [], [], "entita", "climate.matrimoniale",
                       translations=house_translations())
    assert dettaglio["esiste"] is True
    assert dettaglio["stato"] == "heat"
    valori = dettaglio["attributi"]["valori"]
    assert valori["hvac_action"] == "idle"
    assert valori["current_temperature"] == 25.2
    assert valori["temperature"] == 17
    # Il cuore del difetto: lo stato_leggibile non deve poter essere letto
    # come "sta scaldando" quando il termostato e' fermo.
    assert dettaglio["stato_leggibile"] != "heat"
    # Le PAROLE sono quelle di Home Assistant, non piu' due verbi scritti a
    # mano: `hvac_action: idle` si rende «Inattivo», e il nome dell'attributo
    # («Azione in corso») e' cio' che tiene separati i due fatti -- in italiano
    # il modo `heat` e l'azione `heating` si rendono con la stessa parola.
    assert dettaglio["stato_leggibile"] == (
        "impostato su Riscaldamento, azione in corso: Inattivo")


def test_d_guarda_su_un_termostato_che_sta_scaldando_lo_dice_diverso():
    """La prova per mutazione della precedente: una versione del fix che
    scrivesse SEMPRE "fermo" (hardcoded) passerebbe il test C e fallirebbe
    qui -- serve leggere `hvac_action` davvero, non solo dichiararne uno."""
    raw = {**_RAW_TERMOSTATO,
           "attributes": {**_RAW_TERMOSTATO["attributes"], "hvac_action": "heating"}}
    mirror = live_mirror([_to_minimal(raw)])
    dettaglio = view(House(_CASA, Mirror(state=mirror.state, attributes=mirror.attributes)), [], [],
                     "entita", "climate.matrimoniale",
                       translations=house_translations())
    assert dettaglio["stato_leggibile"] == (
        "impostato su Riscaldamento, azione in corso: Riscaldamento")
    assert "Inattivo" not in dettaglio["stato_leggibile"]


def test_e_senza_hvac_action_non_si_inventa_un_funzionamento():
    """Un'integrazione che non manda `hvac_action` (o un attributo fuori
    vocabolario): lo stato_leggibile dichiara solo l'impostazione, non
    inventa "fermo" ne' "sta scaldando" -- nessuno dei due sarebbe vero."""
    reso = readable_state("heat", domain="climate", hvac_action=None,
                          translations=house_translations())
    assert reso == {"letto": True, "valore": "impostato su Riscaldamento"}
    # Un valore FUORI dall'enumerazione di Home Assistant vale come nessun
    # valore: non si compone una frase attorno a una parola che il fornitore
    # non pubblica.
    fuori = readable_state("heat", domain="climate", hvac_action="marziano",
                           translations=house_translations())
    assert fuori == {"letto": True, "valore": "impostato su Riscaldamento"}


# --- il confine deciso: attributi SOLO sul dettaglio, mai nelle liste -----

def test_f_un_area_porta_gli_attributi_alla_media_e_non_alla_corta():
    """Il 25/08/2026 il proprietario aveva deciso che un elenco non portasse
    gli attributi di ogni entita'. Il 05/10/2026 ha approvato la regola delle
    profondita' (D1 della Tappa 4, C-34): un elenco fino a
    `render.DETAIL_MEDIUM_MAX` oggetti esce alla MEDIA, con gli attributi
    filtrati come alla completa; oltre esce alla CORTA, senza. La seconda
    decisione vale per ogni elenco -- prima `search` portava le ceste grezze
    alla media e la scheda di un'area niente (fondamenta 3, Tappa 9, F2)."""
    mirror = _specchio_del_termostato()
    dettaglio = view(House(_CASA, Mirror(state=mirror.state, attributes=mirror.attributes)), [], [],
                     "area", "camera")
    entita = dettaglio["entita"][0]
    assert entita["attributi"]["valori"]["hvac_action"] == "idle"
    molte = dict(_CASA, entita=[dict(_CASA["entita"][0], id=f"climate.t{i}")
                                for i in range(11)])
    stati = {f"climate.t{i}": "heat" for i in range(11)}
    attributi = {f"climate.t{i}": mirror.attributes["climate.matrimoniale"]
                 for i in range(11)}
    dettaglio = view(House(molte, Mirror(state=stati, attributes=attributi)), [], [],
                     "area", "camera")
    assert all("attributi" not in e for e in dettaglio["entita"]), (
        "oltre dieci righe l'elenco e' corto: niente attributi")


def test_g_un_area_porta_comunque_lo_stato_leggibile_onesto():
    """Il confine sopra riguarda il BLOB grezzo, non `readable_state`: quel
    campo esce gia' su ogni ramo, e deve restare onesto ovunque -- la stessa
    domanda (Camera: il termostato sta scaldando?) non puo' avere due
    risposte diverse a seconda che si chiami `guarda('area', ...)` o
    `guarda('entita', ...)` (fondamenta 3)."""
    mirror = _specchio_del_termostato()
    dettaglio = view(House(_CASA, Mirror(state=mirror.state, attributes=mirror.attributes)), [], [],
                     "area", "camera",
                       translations=house_translations())
    entita = dettaglio["entita"][0]
    assert entita["stato_leggibile"] == (
        "impostato su Riscaldamento, azione in corso: Inattivo")


def test_h_un_dispositivo_porta_lo_stato_leggibile_e_gli_attributi_filtrati():
    casa = {
        "aree": [], "dispositivi": [{"id": "dev_t", "nome": "Termostato camera",
                                      "disabilitato": False}],
        "entita": [{"id": "climate.matrimoniale", "nome": "Termostato Matrimoniale",
                    "area_id": None, "dispositivo_id": "dev_t", "classe": None,
                    "disabilitata": False}],
    }
    mirror = _specchio_del_termostato()
    dettaglio = view(House(casa, Mirror(state=mirror.state, attributes=mirror.attributes)), [], [],
                     "dispositivo", "dev_t",
                       translations=house_translations())
    entita = dettaglio["entita"][0]
    # Una riga sola: media, come in `test_f_...` qui sopra.
    assert entita["attributi"]["valori"]["hvac_action"] == "idle"
    assert entita["stato_leggibile"] == (
        "impostato su Riscaldamento, azione in corso: Inattivo")


def test_i_senza_attributi_vivi_guarda_si_comporta_come_prima():
    """Nessuna rottura per chi non passa `reported_attributes`: niente chiave
    "attributi", e lo stato in parole degrada onestamente all'impostazione
    sola -- non torna "heat" nudo, che sarebbe il vecchio difetto con un'altra
    faccia."""
    dettaglio = view(House(_CASA, Mirror(state={"climate.matrimoniale": "heat"})), [], [],
                       "entita", "climate.matrimoniale",
                       translations=house_translations())
    assert "attributi" not in dettaglio
    assert dettaglio["stato_leggibile"] == "impostato su Riscaldamento"
