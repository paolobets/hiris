from unittest.mock import AsyncMock

import pytest

from hiris.app.casa.anagrafe import gerarchia, ricostruisci
from hiris.app.casa.archivio import ArchivioCasa

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
# comportamento e' provato a parte, in tests/test_casa_riferimento.py.
_CONFIG = {"time_zone": "Europe/Rome", "currency": "EUR", "language": "it",
           "unit_system": {"temperature": "C", "length": "km"}}


@pytest.fixture
def archivio(tmp_path):
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    yield a
    a.chiudi()


@pytest.mark.asyncio
async def test_ricostruisci_riempie_l_archivio_e_riepiloga(archivio):
    client = AsyncMock()
    client.leggi_registri = AsyncMock(return_value=(_REGISTRI, []))
    client.get_config = AsyncMock(return_value=_CONFIG)
    esito = await ricostruisci(client, archivio)
    assert esito["conteggi"]["aree"] == 2
    assert esito["conteggi"]["entita"] == 4
    assert esito["non_disponibili"] == []
    assert archivio.aggiornata_il() is not None


@pytest.mark.asyncio
async def test_ricostruisci_riporta_i_registri_caduti(archivio):
    """Un registro caduto non ferma l'anagrafe, ma non deve sparire: la casa
    senza piani e il registro dei piani caduto danno la stessa lista vuota."""
    client = AsyncMock()
    client.leggi_registri = AsyncMock(return_value=(dict(_REGISTRI, piani=[]), ["piani"]))
    client.get_config = AsyncMock(return_value=_CONFIG)
    esito = await ricostruisci(client, archivio)
    assert esito["non_disponibili"] == ["piani"]
    assert esito["conteggi"]["aree"] == 2   # il resto e' passato lo stesso


@pytest.mark.asyncio
async def test_una_lettura_del_tutto_fallita_non_cancella_la_casa(archivio):
    """L'utente rinomina un'entita' e subito riavvia HA: l'antirimbalzo scade a
    HA spento. La casa buona di ieri non deve sparire."""
    client = AsyncMock()
    client.leggi_registri = AsyncMock(return_value=(_REGISTRI, []))
    client.get_config = AsyncMock(return_value=_CONFIG)
    await ricostruisci(client, archivio)
    prima = archivio.aggiornata_il()

    vuoti = {chiave: [] for chiave in _REGISTRI}
    client.leggi_registri = AsyncMock(return_value=(vuoti, list(_REGISTRI)))
    client.get_config = AsyncMock(return_value=_CONFIG)
    esito = await ricostruisci(client, archivio)

    assert archivio.leggi()["aree"]           # la casa di ieri e' ancora li'
    assert archivio.aggiornata_il() == prima  # e non finge di essere fresca
    assert esito["non_disponibili"] == list(_REGISTRI)


def test_l_entita_eredita_l_area_dal_proprio_dispositivo(archivio):
    archivio.sostituisci(_REGISTRI)
    aree = {a["nome"]: a for a in gerarchia(archivio.leggi())[0]["aree"]}
    assert "sensor.frigo_temp" in [e["id"] for e in aree["Cucina"]["entita"]]


def test_l_area_dell_entita_vince_su_quella_del_dispositivo(archivio):
    archivio.sostituisci(_REGISTRI)
    piani = gerarchia(archivio.leggi())
    solaio = next(a for p in piani for a in p["aree"] if a["nome"] == "Solaio")
    assert [e["id"] for e in solaio["entita"]] == ["light.faretto"]


def test_le_aree_senza_piano_stanno_in_un_piano_senza_nome(archivio):
    archivio.sostituisci(_REGISTRI)
    piani = gerarchia(archivio.leggi())
    senza = next(p for p in piani if p["id"] == "__senza_piano__")
    assert [a["nome"] for a in senza["aree"]] == ["Solaio"]


def test_le_entita_disabilitate_non_entrano_nella_gerarchia(archivio):
    archivio.sostituisci(_REGISTRI)
    tutte = [e["id"] for p in gerarchia(archivio.leggi())
             for a in p["aree"] for e in a["entita"]]
    assert "sensor.spenta" not in tutte


def test_le_entita_senza_casa_sono_raccolte_a_parte(archivio):
    archivio.sostituisci(_REGISTRI)
    piani = gerarchia(archivio.leggi())
    fuori = [a for p in piani for a in p["aree"] if a["id"] == "__senza_area__"]
    assert [e["id"] for a in fuori for e in a["entita"]] == ["sensor.orfana"]


def test_un_registro_delle_aree_caduto_non_diventa_una_casa_senza_aree(archivio):
    """Il caso che la review ha riprodotto: se cade il SOLO registro delle aree,
    ogni entita' della casa finiva in «Senza area», e HIRIS presentava «questa
    casa non ha organizzazione» invece di «non ho potuto leggere le aree»."""
    archivio.sostituisci(dict(_REGISTRI, aree=[]), ["aree"])
    piani = gerarchia(archivio.leggi(), ("aree",))
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
    archivio.sostituisci(registri)
    aree = {a["nome"]: a for p in gerarchia(archivio.leggi()) for a in p["aree"]}
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
    archivio.sostituisci(registri, ["dispositivi"])
    piani = gerarchia(archivio.leggi(), ("dispositivi",))
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
    archivio.sostituisci(registri, ["piani"])
    piani = gerarchia(archivio.leggi(), ("piani",))
    assert [p["id"] for p in piani] == ["__piani_non_letti__"]
    assert [a["nome"] for a in piani[0]["aree"]] == ["Cucina"]


def test_le_entita_nascoste_finiscono_in_una_chiave_a_parte(archivio):
    """Fetta "nascoste fuori dagli elenchi" (2026-08-25): stessa forma delle
    disabilitate -- fuori da `entita` (che conta), dentro `entita_nascoste`
    (raggiungibile, non nei conteggi)."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "light.lampadario_nascosto", "device_id": "d1", "area_id": None,
         "hidden_by": "user"}])
    archivio.sostituisci(registri)
    cucina = next(a for p in gerarchia(archivio.leggi()) for a in p["aree"]
             if a["nome"] == "Cucina")
    assert "light.lampadario_nascosto" not in [e["id"] for e in cucina["entita"]]
    assert [e["id"] for e in cucina["entita_nascoste"]] == ["light.lampadario_nascosto"]


def test_un_area_senza_nascoste_ha_la_chiave_vuota(archivio):
    """`entita_nascoste` esiste sempre nell'albero (a differenza della porta
    `domande.guarda`, che la omette quando e' vuota): e' una struttura
    interna, non la risposta finale al modello."""
    archivio.sostituisci(_REGISTRI)
    cucina = next(a for p in gerarchia(archivio.leggi()) for a in p["aree"]
             if a["nome"] == "Cucina")
    assert cucina["entita_nascoste"] == []


def test_una_entita_disabilitata_e_nascosta_resta_fra_le_disabilitate(archivio):
    """Stessa precedenza che `nucleo.py` applica gia' al proprio conteggio
    delle nascoste (`nascosta and not disabilitata`): chi e' entrambe le
    cose non duplica il fatto in due chiavi diverse."""
    registri = dict(_REGISTRI, entita=_REGISTRI["entita"] + [
        {"entity_id": "light.morta_e_nascosta", "device_id": "d1", "area_id": None,
         "disabled_by": "user", "hidden_by": "user"}])
    archivio.sostituisci(registri)
    cucina = next(a for p in gerarchia(archivio.leggi()) for a in p["aree"]
             if a["nome"] == "Cucina")
    assert "light.morta_e_nascosta" not in [e["id"] for e in cucina["entita_nascoste"]]
    assert "light.morta_e_nascosta" not in [e["id"] for e in cucina["entita"]]
    assert "light.morta_e_nascosta" in [e["id"] for e in cucina["entita_disabilitate"]]


def test_i_due_contenitori_hanno_identita_distinte(archivio):
    """Due piani con lo stesso id facevano sparire in silenzio le aree vere
    senza piano, appena qualcuno indicizzava per id."""
    archivio.sostituisci(_REGISTRI)
    piani = gerarchia(archivio.leggi())
    identita = [p["id"] for p in piani]
    assert len(identita) == len(set(identita))
    per_id = {p["id"]: p for p in piani}
    assert [a["nome"] for a in per_id["__senza_piano__"]["aree"]] == ["Solaio"]
    assert [a["nome"] for a in per_id["__fuori_dalle_aree__"]["aree"]] == ["Senza area"]
