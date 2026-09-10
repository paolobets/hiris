from unittest.mock import create_autospec

import pytest

from hiris.app.home_space.reader import HomeSpace
from hiris.app.home_space.topology import device_areas, hierarchy, rebuild
from hiris.app.proxy.entity_cache import EntityCache
from hiris.app.proxy.ha_client import HAClient

_REGISTRI = {
    "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
    "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"},
             {"area_id": "solaio", "name": "Solaio", "floor_id": None}],
    "dispositivi": [{"id": "d1", "name": "Frigo", "area_id": "cucina"}],
    "entita": [
        # senza area propria: la eredita dal dispositivo
        {"entity_id": "sensor.frigo_temp", "device_id": "d1", "area_id": None},
        # con area propria: la sua vince su quella del dispositivo
        {"entity_id": "light.faretto", "device_id": "d1", "area_id": "solaio"},
        # senza area e senza dispositivo: senza casa
        {"entity_id": "sensor.orfana", "device_id": None, "area_id": None},
        # disabilitata: non entra nella gerarchia
        {"entity_id": "sensor.spenta", "device_id": "d1", "area_id": None,
         "disabled_by": "user"},
    ],
    "etichette": [], "categorie": [], "integrazioni": [],
}


# La config minima che Home Assistant restituisce a `get_config`: da questa
# fetta la ricostruzione dell'anagrafe legge anche il sistema di riferimento
# della casa (unita', fuso, valuta). Un finto che non la dichiara e' un HA che
# non ha risposto -- e infatti `non_disponibili` lo direbbe. Che sia questo il
# comportamento e' provato a parte, in tests/test_home_space_reference.py.
_CONFIG = {"time_zone": "Europe/Rome", "currency": "EUR", "language": "it",
           "unit_system": {"temperature": "C", "length": "km"}}


def _client(registries, unavailable=(), config=_CONFIG):
    """Un `HAClient` finto, autospec'd sulla classe VERA -- misurato dal
    vivo (review lotto 5): un `AsyncMock()` nudo lasciava passare
    `await client.registers_extra()` (un metodo che `HAClient` non ha)
    in silenzio, `2922 passed` inclusi. `create_autospec` chiude lo stesso
    buco di `_METODI_HA_CLIENT` (`scripts/rinomina.py`) dal lato dei test:
    chiamare un attributo che la classe vera non ha solleva
    `AttributeError` invece di restituire un altro Mock qualunque."""
    client = create_autospec(HAClient, instance=True)
    client.read_registries.return_value = (registries, list(unavailable))
    client.get_config.return_value = config
    return client


async def _specchio(stati=()):
    """Uno specchio dello stato VERO (`EntityCache`), caricato come in
    produzione: `load()` alza `loaded`, e senza quella bandiera `rebuild`
    dichiara `specchio_vivo` fra i non disponibili -- vedi il suo docstring.
    """
    cache = EntityCache()
    client = create_autospec(HAClient, instance=True)
    client.get_states.return_value = list(stati)
    await cache.load(client)
    return cache


@pytest.fixture
def archivio(tmp_path):
    a = HomeSpace(str(tmp_path))
    yield a
    a.close()


@pytest.mark.asyncio
async def test_ricostruisci_riempie_l_archivio_e_riepiloga(archivio):
    client = _client(_REGISTRI)
    esito = await rebuild(client, archivio, await _specchio())
    assert esito["conteggi"]["aree"] == 2
    assert esito["conteggi"]["entita"] == 4
    assert esito["non_disponibili"] == []
    assert archivio.updated_at() is not None


@pytest.mark.asyncio
async def test_ricostruisci_riporta_i_registri_caduti(archivio):
    """Un registro caduto non ferma l'anagrafe, ma non deve sparire: la casa
    senza piani e il registro dei piani caduto danno la stessa lista vuota."""
    client = _client(dict(_REGISTRI, piani=[]), ["piani"])
    esito = await rebuild(client, archivio, await _specchio())
    assert esito["non_disponibili"] == ["piani"]
    assert esito["conteggi"]["aree"] == 2   # il resto e' passato lo stesso


@pytest.mark.asyncio
async def test_una_lettura_del_tutto_fallita_non_cancella_la_casa(archivio):
    """L'utente rinomina un'entita' e subito riavvia HA: l'antirimbalzo scade a
    HA spento. La casa buona di ieri non deve sparire."""
    client = _client(_REGISTRI)
    await rebuild(client, archivio, await _specchio())
    prima = archivio.updated_at()

    vuoti = {chiave: [] for chiave in _REGISTRI}
    client.read_registries.return_value = (vuoti, list(_REGISTRI))
    esito = await rebuild(client, archivio, await _specchio())

    assert archivio.read()["aree"]           # la casa di ieri e' ancora li'
    assert archivio.updated_at() == prima  # e non finge di essere fresca
    assert esito["non_disponibili"] == list(_REGISTRI)


def test_l_entita_eredita_l_area_dal_proprio_dispositivo(archivio):
    archivio.hold_registries(_REGISTRI)
    aree = {a["nome"]: a for a in hierarchy(archivio.read())[0]["aree"]}
    assert "sensor.frigo_temp" in [e["id"] for e in aree["Cucina"]["entita"]]


def test_l_area_dell_entita_vince_su_quella_del_dispositivo(archivio):
    archivio.hold_registries(_REGISTRI)
    piani = hierarchy(archivio.read())
    solaio = next(a for p in piani for a in p["aree"] if a["nome"] == "Solaio")
    assert [e["id"] for e in solaio["entita"]] == ["light.faretto"]


def test_le_aree_senza_piano_stanno_in_un_piano_senza_nome(archivio):
    archivio.hold_registries(_REGISTRI)
    piani = hierarchy(archivio.read())
    senza = next(p for p in piani if p["id"] == "__senza_piano__")
    assert [a["nome"] for a in senza["aree"]] == ["Solaio"]


def test_le_entita_disabilitate_non_entrano_nella_gerarchia(archivio):
    archivio.hold_registries(_REGISTRI)
    tutte = [e["id"] for p in hierarchy(archivio.read())
             for a in p["aree"] for e in a["entita"]]
    assert "sensor.spenta" not in tutte


def test_le_entita_senza_casa_sono_raccolte_a_parte(archivio):
    archivio.hold_registries(_REGISTRI)
    piani = hierarchy(archivio.read())
    fuori = [a for p in piani for a in p["aree"] if a["id"] == "__senza_area__"]
    assert [e["id"] for a in fuori for e in a["entita"]] == ["sensor.orfana"]


def test_un_registro_delle_aree_caduto_non_diventa_una_casa_senza_aree(archivio):
    """Il caso che la review ha riprodotto: se cade il SOLO registro delle aree,
    ogni entita' della casa finiva in «Senza area», e HIRIS presentava «questa
    casa non ha organizzazione» invece di «non ho potuto leggere le aree»."""
    archivio.hold_registries(dict(_REGISTRI, aree=[]), ["aree"])
    piani = hierarchy(archivio.read(), ("aree",))
    aree = [a for p in piani for a in p["aree"]]
    assert [a["nome"] for a in aree] == ["Aree non lette"]
    assert "sensor.frigo_temp" in [e["id"] for e in aree[0]["entita"]]


def test_un_riferimento_penzolante_non_e_una_entita_senza_area(archivio):
    """Un'area letta ma inesistente e' un'incoerenza dell'anagrafe: va vista,
    non confusa con un'entita' che davvero non sta in nessuna stanza."""
    registri = dict(_REGISTRI, entita=[
        {"entity_id": "sensor.fantasma", "device_id": None, "area_id": "area_che_non_esiste"},
        {"entity_id": "sensor.orfana", "device_id": None, "area_id": None},
    ])
    archivio.hold_registries(registri)
    aree = {a["nome"]: a for p in hierarchy(archivio.read()) for a in p["aree"]}
    assert [e["id"] for e in aree["Area sconosciuta"]["entita"]] == ["sensor.fantasma"]
    assert [e["id"] for e in aree["Senza area"]["entita"]] == ["sensor.orfana"]


def test_un_registro_dispositivi_caduto_non_svuota_le_stanze(archivio):
    """Il caso della review: tre luci in Cucina con l'area dichiarata SUL
    DISPOSITIVO — il caso normale in HA. Cade il solo registro dei dispositivi:
    prima la cucina appariva vuota E le luci apparivano senza casa."""
    registri = {
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [],
        "entita": [{"entity_id": f"light.cucina_{i}", "device_id": "d1", "area_id": None}
                   for i in range(3)],
        "etichette": [], "categorie": [], "integrazioni": [],
    }
    archivio.hold_registries(registri, ["dispositivi"])
    piani = hierarchy(archivio.read(), ("dispositivi",))
    aree = {a["nome"]: a for p in piani for a in p["aree"]}
    assert "Dispositivi non letti" in aree
    assert len(aree["Dispositivi non letti"]["entita"]) == 3
    assert "Senza area" not in aree


def test_un_registro_piani_caduto_non_diventa_una_casa_senza_piani(archivio):
    registri = {
        "piani": [],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [], "entita": [],
        "etichette": [], "categorie": [], "integrazioni": [],
    }
    archivio.hold_registries(registri, ["piani"])
    piani = hierarchy(archivio.read(), ("piani",))
    assert [p["id"] for p in piani] == ["__piani_non_letti__"]
    assert [a["nome"] for a in piani[0]["aree"]] == ["Cucina"]


def test_le_entita_nascoste_finiscono_in_una_chiave_a_parte(archivio):
    """Fetta "nascoste fuori dagli elenchi" (2026-08-25): stessa forma delle
    disabilitate -- fuori da `entita` (che conta), dentro `entita_nascoste`
    (raggiungibile, non nei conteggi)."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "light.lampadario_nascosto", "device_id": "d1", "area_id": None,
         "hidden_by": "user"}])
    archivio.hold_registries(registri)
    cucina = next(a for p in hierarchy(archivio.read()) for a in p["aree"]
             if a["nome"] == "Cucina")
    assert "light.lampadario_nascosto" not in [e["id"] for e in cucina["entita"]]
    assert [e["id"] for e in cucina["entita_nascoste"]] == ["light.lampadario_nascosto"]


def test_un_area_senza_nascoste_ha_la_chiave_vuota(archivio):
    """`entita_nascoste` esiste sempre nell'albero (a differenza della porta
    `domande.guarda`, che la omette quando e' vuota): e' una struttura
    interna, non la risposta finale al modello."""
    archivio.hold_registries(_REGISTRI)
    cucina = next(a for p in hierarchy(archivio.read()) for a in p["aree"]
             if a["nome"] == "Cucina")
    assert cucina["entita_nascoste"] == []


def test_una_entita_disabilitata_e_nascosta_resta_fra_le_disabilitate(archivio):
    """Stessa precedenza che `briefing.py` applica gia' al proprio conteggio
    delle nascoste (`nascosta and not disabilitata`): chi e' entrambe le
    cose non duplica il fatto in due chiavi diverse."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "light.morta_e_nascosta", "device_id": "d1", "area_id": None,
         "disabled_by": "user", "hidden_by": "user"}])
    archivio.hold_registries(registri)
    cucina = next(a for p in hierarchy(archivio.read()) for a in p["aree"]
             if a["nome"] == "Cucina")
    assert "light.morta_e_nascosta" not in [e["id"] for e in cucina["entita_nascoste"]]
    assert "light.morta_e_nascosta" not in [e["id"] for e in cucina["entita"]]
    assert "light.morta_e_nascosta" in [e["id"] for e in cucina["entita_disabilitate"]]


def test_i_due_contenitori_hanno_identita_distinte(archivio):
    """Due piani con lo stesso id facevano sparire in silenzio le aree vere
    senza piano, appena qualcuno indicizzava per id."""
    archivio.hold_registries(_REGISTRI)
    piani = hierarchy(archivio.read())
    identita = [p["id"] for p in piani]
    assert len(identita) == len(set(identita))
    per_id = {p["id"]: p for p in piani}
    assert [a["nome"] for a in per_id["__senza_piano__"]["aree"]] == ["Solaio"]
    assert [a["nome"] for a in per_id["__fuori_dalle_aree__"]["aree"]] == ["Senza area"]


# -- U2 bis: le 205 entita' sparite (collaudo-3.22/misure-del-controllore.md) -

def _pseudo_aree(piani, nome_gruppo="__fuori_dalle_aree__"):
    """Le pseudo-aree del contenitore "Fuori dalle aree", per nome."""
    gruppo = next(p for p in piani if p["id"] == nome_gruppo)
    return {a["nome"]: a for a in gruppo["aree"]}


def test_una_disabilitata_senza_area_e_raggiungibile_a_parte(archivio):
    """Il difetto misurato sulla casa vera: il ciclo che smistava "Senza
    area" / "Area sconosciuta" / "Aree non lette" leggeva SOLO `per_area`
    (le attive). Una disabilitata senza area restava dentro
    `per_area_disabled` e da li' non usciva mai -- non finiva ne' in
    `entita` ne' in `entita_disabilitate`: non esisteva.

    Mutazione che uccide questa prova: tornare a
    `for area_id, entries in per_area.items():` come unico ciclo (senza
    `_outside_buckets` sulle altre due mappe). Verificato eseguendo: con
    quella riga la lista `entita_disabilitate` di "Senza area" e' vuota e
    l'assert sotto arrossisce con `AssertionError: assert [] ==
    ['sensor.disabilitata_orfana']`."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "sensor.disabilitata_orfana", "device_id": None, "area_id": None,
         "disabled_by": "user"}])
    archivio.hold_registries(registri)
    aree = _pseudo_aree(hierarchy(archivio.read()))
    senza_area = aree["Senza area"]
    assert "sensor.disabilitata_orfana" not in [e["id"] for e in senza_area["entita"]]
    assert [e["id"] for e in senza_area["entita_disabilitate"]] == ["sensor.disabilitata_orfana"]


def test_una_nascosta_con_area_sconosciuta_e_raggiungibile_a_parte(archivio):
    """Stessa causa del test sopra, sull'altra chiave parallela e sull'altra
    pseudo-area: un riferimento penzolante (`area_id` che non esiste piu' nel
    registro) su un'entita' NASCOSTA.

    Mutazione che uccide questa prova: la stessa di sopra. Verificato
    eseguendo: `entita_nascoste` di "Area sconosciuta" torna `[]` e l'ultimo
    assert arrossisce."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "sensor.nascosta_fantasma", "device_id": None,
         "area_id": "area_che_non_esiste", "hidden_by": "user"}])
    archivio.hold_registries(registri)
    aree = _pseudo_aree(hierarchy(archivio.read()))
    sconosciuta = aree["Area sconosciuta"]
    assert "sensor.nascosta_fantasma" not in [e["id"] for e in sconosciuta["entita"]]
    assert [e["id"] for e in sconosciuta["entita_nascoste"]] == ["sensor.nascosta_fantasma"]


def test_le_aree_non_lette_portano_anche_loro_le_chiavi_parallele(archivio):
    """La terza causa (registro delle aree caduto): una disabilitata che
    avrebbe un `area_id` ignoto finisce in "Aree non lette", non in "Area
    sconosciuta" -- ma deve restare raggiungibile lo stesso, nella chiave
    che le spetta."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "sensor.disabilitata_area_ignota", "device_id": None,
         "area_id": "qualche_area", "disabled_by": "user"}])
    archivio.hold_registries(registri, ["aree"])
    aree = _pseudo_aree(hierarchy(archivio.read(), ("aree",)))
    unread_group = aree["Aree non lette"]
    assert "sensor.disabilitata_area_ignota" not in [e["id"] for e in unread_group["entita"]]
    assert [e["id"] for e in unread_group["entita_disabilitate"]] == \
        ["sensor.disabilitata_area_ignota"]


def test_il_gruppo_senza_area_nasce_anche_con_sole_disabilitate(archivio):
    """Decisione del task: `if without_area:` (solo attive) creava il
    gruppo solo se c'erano entita' attive senza area. Una casa con SOLE
    disabilitate senza area (zero attive) non avrebbe fatto nascere "Senza
    area" -- e quelle disabilitate sarebbero sparite comunque, anche dopo
    aver sistemato lo smistamento sopra.

    Mutazione che uccide questa prova: `if without_area:` al posto di
    `if without_area or without_area_disabled or without_area_hidden:`.
    Verificato eseguendo: con la sola condizione su `without_area`, il
    gruppo "Senza area" non compare affatto (nessuna entita' attiva senza
    area in questa casa) e `next(...)` solleva `StopIteration`."""
    registri = {
        "piani": [], "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": None}],
        "dispositivi": [],
        "entita": [{"entity_id": "sensor.unica_disabilitata_orfana", "device_id": None,
                    "area_id": None, "disabled_by": "user"}],
        "etichette": [], "categorie": [], "integrazioni": [],
    }
    archivio.hold_registries(registri)
    aree = _pseudo_aree(hierarchy(archivio.read()))
    assert "Senza area" in aree
    assert [e["id"] for e in aree["Senza area"]["entita_disabilitate"]] == \
        ["sensor.unica_disabilitata_orfana"]
    assert aree["Senza area"]["entita"] == []


def test_una_disabilitata_col_dispositivo_non_risolvibile_e_raggiungibile_a_parte(archivio):
    """R3 (revisione del tratto v3.22.2..HEAD): "Dispositivi non letti" era
    rimasta l'unica pseudo-area senza le chiavi parallele, con la
    giustificazione "un dispositivo non letto rende l'intera area
    indecidibile, quindi disabilitate e nascoste non sono tracciate nemmeno a
    parte". L'argomento non regge alla propria premessa -- le entita' ATTIVE
    nella stessa condizione sono altrettanto indecidibili quanto ad area, e
    finiscono comunque in `entita`, in un gruppo che porta l'indecisione nel
    proprio nome. Ora anche questo gruppo porta `entita_disabilitate` /
    `entita_nascoste`, stessa forma delle altre tre pseudo-aree "fuori dalle
    aree note".

    Mutazione che uccide questa prova: tornare alla guardia unica di prima
    (`if not entity.get("disabilitata") and not entity.get("nascosta"):
    unloaded_device.append(entity)`) al posto delle tre liste smistate.
    Verificato eseguendo: con quella riga la chiave `entita_disabilitate` non
    esiste piu' sul gruppo e l'assert sotto arrossisce con `KeyError:
    'entita_disabilitate'`.

    `_REGISTRI` porta gia' `sensor.spenta` (disabilitata, dispositivo `d1`,
    senza area propria): col registro dei dispositivi caduto finisce anche
    lei in questo gruppo, insieme alla nuova -- da qui l'insieme invece della
    lista, l'ordine di smistamento non e' la garanzia in prova."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "sensor.disabilitata_dispositivo_ignoto", "device_id": "d1",
         "area_id": None, "disabled_by": "user"}])
    archivio.hold_registries(registri, ["dispositivi"])
    aree = _pseudo_aree(hierarchy(archivio.read(), ("dispositivi",)))
    non_letti = aree["Dispositivi non letti"]
    assert "sensor.disabilitata_dispositivo_ignoto" not in [e["id"] for e in non_letti["entita"]]
    assert {e["id"] for e in non_letti["entita_disabilitate"]} == \
        {"sensor.spenta", "sensor.disabilitata_dispositivo_ignoto"}


def test_una_nascosta_col_dispositivo_non_risolvibile_e_raggiungibile_a_parte(archivio):
    """Stessa causa del test sopra, sull'altra chiave parallela. Prima della
    correzione R3 questa nascosta spariva del tutto: giustamente fuori da
    `entita` (non e' attiva), ma anche fuori da `entita_nascoste`, che per
    questo gruppo non esisteva proprio.

    Mutazione che uccide questa prova: la stessa di sopra. Verificato
    eseguendo: la chiave `entita_nascoste` non esiste e l'ultimo assert
    arrossisce con `KeyError: 'entita_nascoste'`."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "sensor.nascosta_dispositivo_ignoto", "device_id": "d1",
         "area_id": None, "hidden_by": "user"}])
    archivio.hold_registries(registri, ["dispositivi"])
    aree = _pseudo_aree(hierarchy(archivio.read(), ("dispositivi",)))
    non_letti = aree["Dispositivi non letti"]
    assert "sensor.nascosta_dispositivo_ignoto" not in [e["id"] for e in non_letti["entita"]]
    assert [e["id"] for e in non_letti["entita_nascoste"]] == \
        ["sensor.nascosta_dispositivo_ignoto"]


def test_ogni_entita_esce_esattamente_una_volta(archivio):
    """La prova che chiude il caso, quella che deve arrossire da sola alla
    prossima dimenticanza: ogni entita' che entra in `hierarchy()` deve
    ritrovarsi ESATTAMENTE una volta fra `entita`/`entita_disabilitate`/
    `entita_nascoste` di tutte le aree (vere o pseudo) di tutti i piani --
    SENZA ECCEZIONI (R3, revisione del tratto v3.22.2..HEAD: il solo caso
    escluso fin qui -- disabilitata/nascosta col dispositivo non risolvibile
    -- non era piu' difendibile, ed e' proprio perche' questa prova lo teneva
    fuori dal calcolo che il buco non arrossiva da solo).

    Copre le combinazioni che sparivano prima di questa fetta: disabilitata E
    nascosta, sia senza area, sia con un'area sconosciuta, sia col
    dispositivo non risolvibile (registro dei dispositivi caduto).

    Non fissa 1223/1018 (la misura di oggi di una casa che cambia): fissa
    l'invariante -- l'insieme delle entita' in ingresso e l'insieme di quelle
    trovate in uscita devono coincidere, senza doppioni."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "sensor.disabilitata_senza_area", "device_id": None, "area_id": None,
         "disabled_by": "user"},
        {"entity_id": "sensor.nascosta_senza_area", "device_id": None, "area_id": None,
         "hidden_by": "user"},
        {"entity_id": "sensor.disabilitata_area_sconosciuta", "device_id": None,
         "area_id": "area_fantasma_1", "disabled_by": "user"},
        {"entity_id": "sensor.nascosta_area_sconosciuta", "device_id": None,
         "area_id": "area_fantasma_2", "hidden_by": "user"},
        {"entity_id": "sensor.disabilitata_dispositivo_ignoto", "device_id": "d1",
         "area_id": None, "disabled_by": "user"},
        {"entity_id": "sensor.nascosta_dispositivo_ignoto", "device_id": "d1",
         "area_id": None, "hidden_by": "user"},
    ])
    archivio.hold_registries(registri, ["dispositivi"])
    piani = hierarchy(archivio.read(), ("dispositivi",))

    attese = {e["entity_id"] for e in registri["entita"]}

    trovate = []
    for piano in piani:
        for area in piano["aree"]:
            trovate.extend(e["id"] for e in area.get("entita", []))
            trovate.extend(e["id"] for e in area.get("entita_disabilitate", []))
            trovate.extend(e["id"] for e in area.get("entita_nascoste", []))

    assert len(trovate) == len(set(trovate)), "nessuna entita' compare due volte"
    assert set(trovate) == attese, \
        f"mancano: {attese - set(trovate)}, in piu': {set(trovate) - attese}"


# -- `device_areas`: una sola casa per la mappa dispositivo -> area ---------

def test_la_mappa_delle_aree_dei_dispositivi_salta_quelli_senza_id():
    """La mappa serve SOLO a essere interrogata per `dispositivo_id`: un
    oggetto senza id non puo' essere il bersaglio di nessuna entita', quindi
    tenerlo dentro aggiungerebbe una chiave che nessuno puo' chiedere."""
    assert device_areas([{"id": "d1", "area_id": "cucina"},
                         {"nome": "malformato"},
                         {"id": "d2", "area_id": None}]) == {"d1": "cucina", "d2": None}


def test_la_mappa_delle_aree_dei_dispositivi_regge_un_registro_assente():
    """`None` e' cio' che `home_space.get("dispositivi")` restituisce su una
    casa il cui registro dei dispositivi non ha risposto."""
    assert device_areas(None) == {}
    assert device_areas([]) == {}


def test_una_riga_di_registro_senza_id_non_fa_saltare_l_albero():
    """Prima dell'unificazione la comprehension dentro `hierarchy()` diceva
    `d["id"]` senza guardia: una riga di registro malformata sollevava
    `KeyError` e portava via l'INTERO albero della casa, per un oggetto che
    nessuna entita' avrebbe comunque potuto nominare. La gemella in
    `memory/interpretation.py` la guardia ce l'aveva gia' -- ed e' il
    genere di divergenza che due nomi diversi per lo stesso fatto
    (`device_area` contro `device_area`) tengono nascosta."""
    casa = {"piani": [],
            "aree": [{"id": "cucina", "nome": "Cucina", "piano_id": None}],
            "dispositivi": [{"id": "d1", "area_id": "cucina"},
                            {"nome": "riga senza id"}],
            "entita": [{"id": "sensor.frigo", "dispositivo_id": "d1", "area_id": None}]}
    cucina = next(a for p in hierarchy(casa) for a in p["aree"] if a["nome"] == "Cucina")
    assert [e["id"] for e in cucina["entita"]] == ["sensor.frigo"]


@pytest.mark.asyncio
async def test_la_ricostruzione_porta_nell_anagrafe_la_classe_che_solo_lo_specchio_conosce(
        archivio):
    """**La classe non e' nei registri: e' nello stato.** Misurato sulla casa
    vera il 10/09/2026: `config/entity_registry/list` non manda
    `device_class` su nessuna delle 1.227 righe, e lo specchio dello stato ce
    l'ha per ogni entita' che ne dichiara una.

    La ricostruzione deve unirli, o l'anagrafe rinasce senza classi -- ed e'
    l'anagrafe su cui `build_balances` decide quali entita' formano un
    bilancio.

    Mutazione che la uccide: in `rebuild`, non passare lo specchio al lettore.
    """
    specchio = EntityCache()
    stati = create_autospec(HAClient, instance=True)
    stati.get_states.return_value = [
        {"entity_id": "sensor.frigo_temp", "state": "4.2",
         "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"}}]
    await specchio.load(stati)

    await rebuild(_client(_REGISTRI), archivio, specchio)

    entita = next(e for e in archivio.read()["entita"] if e["id"] == "sensor.frigo_temp")
    assert entita["classe"] == "temperature"
    assert entita["unita"] == "°C"


@pytest.mark.asyncio
async def test_senza_specchio_vivo_la_ricostruzione_lo_dichiara_invece_di_tacere(archivio):
    """**La trappola dello stato condiviso caricato pigramente.**
    `entity_cache.load()` all'avvio e' dentro un `try/except` che logga e
    prosegue: se fallisce, lo specchio resta vuoto e ogni entita' nascerebbe
    senza classe -- lo stesso identico difetto di prima, con la stessa
    firma silenziosa.

    Non deve essere silenzioso: `specchio_vivo` entra fra i registri non
    disponibili, accanto a quelli veri, perche' «non ho potuto leggere le
    classi» e «questa casa non ha classi» sono due fatti diversi. E' la stessa
    dottrina di `EntityCache.loaded`, che esiste per non spacciare un
    inventario non pronto per una casa vuota.

    Mutazione che la uccide: costruire lo specchio comunque quando
    `cache.loaded` e' falso.
    """
    esito = await rebuild(_client(_REGISTRI), archivio, EntityCache())

    assert "specchio_vivo" in esito["non_disponibili"]
