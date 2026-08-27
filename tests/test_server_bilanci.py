"""`server.costruisci_bilanci`: il raggruppamento per dispositivo (senza
nessuna lettura di rete, il registro e' gia' replicato in `archivio_casa`) e
UNA connessione sola per tutti i dispositivi candidati (`HAClient.
statistiche_orarie`).
"""
from datetime import datetime, timezone

import pytest

from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.cervello.oggetti import confini_giorno
from hiris.app.server import costruisci_bilanci
from tests.test_cervello_comprimari import _ClienteLegami

G = "2026-08-24"


def _casa(tmp_path, *, entita, dispositivi):
    """Un `ArchivioCasa` reale, seminato coi registri GREZZI (chiavi
    inglesi, come li manderebbe `HAClient.leggi_registri()`): fedele al
    contratto vero di `ArchivioCasa.sostituisci`, non una finta a parte."""
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    a.sostituisci({"dispositivi": dispositivi, "entita": entita}, [],
                 sistema_di_riferimento={"fuso": "Europe/Rome"})
    return a


def _iso_giorno(giorno=G, fuso="Europe/Rome"):
    da_ts, a_ts = confini_giorno(giorno, fuso)
    return (datetime.fromtimestamp(da_ts, tz=timezone.utc).isoformat(),
            datetime.fromtimestamp(a_ts, tz=timezone.utc).isoformat())


def _punto(cambio):
    return {"inizio": "x", "fine": "y", "minimo": None, "massimo": None,
            "media": None, "cambio": cambio}


@pytest.mark.asyncio
async def test_senza_archivio_casa_niente_bilanci_niente_rete():
    cliente = _ClienteLegami()
    bilanci, falliti = await costruisci_bilanci(
        cliente, None, giorno=G, fuso="Europe/Rome",
        soggetti_energia=["sensor.x"], direzioni={})
    assert bilanci == []
    assert falliti == 0
    assert cliente.statistiche_chieste == []


@pytest.mark.asyncio
async def test_senza_soggetti_niente_bilanci_niente_rete(tmp_path):
    casa = _casa(tmp_path, entita=[], dispositivi=[])
    cliente = _ClienteLegami()
    try:
        bilanci, falliti = await costruisci_bilanci(
            cliente, casa, giorno=G, fuso="Europe/Rome",
            soggetti_energia=[], direzioni={})
        assert bilanci == []
        assert falliti == 0
        assert cliente.statistiche_chieste == []
    finally:
        casa.chiudi()


@pytest.mark.asyncio
async def test_un_dispositivo_con_una_direzione_utile_diventa_un_bilancio(tmp_path):
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}],
        entita=[{"entity_id": "sensor.energia_prodotta_oggi", "device_id": "dev1",
                "device_class": "energy"}])
    try:
        cliente = _ClienteLegami(statistiche={
            "sensor.energia_prodotta_oggi": [_punto(1.0), _punto(2.0)]})
        bilanci, falliti = await costruisci_bilanci(
            cliente, casa, giorno=G, fuso="Europe/Rome",
            soggetti_energia=["sensor.energia_prodotta_oggi"],
            direzioni={"sensor.energia_prodotta_oggi":
                      {"direzione": "produzione", "provenienza": "dichiarata"}})

        assert falliti == 0
        [b] = bilanci
        assert b["dispositivo_id"] == "dev1"
        assert b["nome"] == "Inverter"
        assert b["entita"] == ["sensor.energia_prodotta_oggi"]
        assert b["corpo"]["totali"]["produzione"]["valore"] == 3.0
        assert b["corpo"]["totali"]["produzione"]["provenienza"] == "dichiarata"

        # Una connessione sola, con l'entita' giusta e la finestra del giorno.
        assert len(cliente.statistiche_chieste) == 1
        ids, da_iso, a_iso = cliente.statistiche_chieste[0]
        assert ids == ["sensor.energia_prodotta_oggi"]
        assert (da_iso, a_iso) == _iso_giorno()
    finally:
        casa.chiudi()


@pytest.mark.asyncio
async def test_senza_nessuna_direzione_utile_niente_bilancio_niente_rete(tmp_path):
    """Un dispositivo la cui unica entita' NON ha nessuna direzione fra le
    sei del bilancio -- "consumo" non e' fra `DIREZIONI_BILANCIO` -- non
    diventa un candidato: nessuna chiamata di rete, le sue entita' restano
    fuori da ogni bilancio."""
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}],
        entita=[{"entity_id": "sensor.energia_consumata_oggi", "device_id": "dev1",
                "device_class": "energy"}])
    try:
        cliente = _ClienteLegami()
        bilanci, falliti = await costruisci_bilanci(
            cliente, casa, giorno=G, fuso="Europe/Rome",
            soggetti_energia=["sensor.energia_consumata_oggi"],
            direzioni={"sensor.energia_consumata_oggi":
                      {"direzione": "consumo", "provenienza": "dedotta"}})
        assert bilanci == []
        assert falliti == 0
        assert cliente.statistiche_chieste == []
    finally:
        casa.chiudi()


@pytest.mark.asyncio
async def test_una_direzione_su_potenza_non_basta_serve_la_classe_energy(tmp_path):
    """`potenza_prodotta` ha `device_class: power`, non `energy`: il
    bilancio riporta kWh del giorno, non W istantanei. Se e' l'UNICA entita'
    con quella direzione, il dispositivo non diventa un candidato."""
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}],
        entita=[{"entity_id": "sensor.potenza_prodotta", "device_id": "dev1",
                "device_class": "power"}])
    try:
        cliente = _ClienteLegami()
        bilanci, falliti = await costruisci_bilanci(
            cliente, casa, giorno=G, fuso="Europe/Rome",
            soggetti_energia=["sensor.potenza_prodotta"],
            direzioni={"sensor.potenza_prodotta":
                      {"direzione": "produzione", "provenienza": "dichiarata"}})
        assert bilanci == []
        assert falliti == 0
        assert cliente.statistiche_chieste == []
    finally:
        casa.chiudi()


@pytest.mark.asyncio
async def test_la_batteria_dello_stesso_dispositivo_entra_nella_lettura(tmp_path):
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}],
        entita=[
            {"entity_id": "sensor.energia_prodotta_oggi", "device_id": "dev1",
             "device_class": "energy"},
            {"entity_id": "sensor.batteria", "device_id": "dev1",
             "device_class": "battery"},
        ])
    try:
        cliente = _ClienteLegami(statistiche={
            "sensor.energia_prodotta_oggi": [_punto(1.0)],
            "sensor.batteria": [{"inizio": "x", "fine": "y", "minimo": None,
                                 "massimo": None, "media": 55.0, "cambio": None}],
        })
        bilanci, falliti = await costruisci_bilanci(
            cliente, casa, giorno=G, fuso="Europe/Rome",
            soggetti_energia=["sensor.energia_prodotta_oggi"],
            direzioni={"sensor.energia_prodotta_oggi":
                      {"direzione": "produzione", "provenienza": "dichiarata"}})

        assert falliti == 0
        [b] = bilanci
        assert b["corpo"]["batteria_percentuale_oraria"] == [55.0]
        ids, _, _ = cliente.statistiche_chieste[0]
        assert set(ids) == {"sensor.energia_prodotta_oggi", "sensor.batteria"}
    finally:
        casa.chiudi()


@pytest.mark.asyncio
async def test_un_entita_senza_dispositivo_non_e_un_errore_resta_fuori(tmp_path):
    """«Un'entita' senza dispositivo non e' un errore: non entra in nessun
    bilancio e continua per la sua strada» (mandato, punto 3)."""
    casa = _casa(tmp_path, dispositivi=[],
                entita=[{"entity_id": "sensor.orfana", "device_id": None,
                        "device_class": "energy"}])
    try:
        cliente = _ClienteLegami()
        bilanci, falliti = await costruisci_bilanci(
            cliente, casa, giorno=G, fuso="Europe/Rome",
            soggetti_energia=["sensor.orfana"],
            direzioni={"sensor.orfana": {"direzione": "produzione", "provenienza": "dichiarata"}})
        assert bilanci == []
        assert falliti == 0
        assert cliente.statistiche_chieste == []
    finally:
        casa.chiudi()


@pytest.mark.asyncio
async def test_due_dispositivi_candidati_una_connessione_sola(tmp_path):
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}, {"id": "dev2", "name": "Pompa"}],
        entita=[
            {"entity_id": "sensor.dev1_produzione", "device_id": "dev1", "device_class": "energy"},
            {"entity_id": "sensor.dev2_prelievo", "device_id": "dev2", "device_class": "energy"},
        ])
    try:
        cliente = _ClienteLegami(statistiche={
            "sensor.dev1_produzione": [_punto(1.0)],
            "sensor.dev2_prelievo": [_punto(2.0)],
        })
        bilanci, falliti = await costruisci_bilanci(
            cliente, casa, giorno=G, fuso="Europe/Rome",
            soggetti_energia=["sensor.dev1_produzione", "sensor.dev2_prelievo"],
            direzioni={
                "sensor.dev1_produzione": {"direzione": "produzione", "provenienza": "dichiarata"},
                "sensor.dev2_prelievo": {"direzione": "prelievo", "provenienza": "dichiarata"},
            })
        assert falliti == 0
        assert {b["dispositivo_id"] for b in bilanci} == {"dev1", "dev2"}
        assert len(cliente.statistiche_chieste) == 1  # UNA connessione per ENTRAMBI
    finally:
        casa.chiudi()


@pytest.mark.asyncio
async def test_un_guasto_delle_statistiche_fallisce_tutti_i_candidati_insieme(tmp_path):
    """Una connessione sola -> un guasto solo, che colpisce tutti i
    dispositivi candidati insieme: non c'e' un fallimento parziale con una
    sola richiesta WS."""
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}, {"id": "dev2", "name": "Pompa"}],
        entita=[
            {"entity_id": "sensor.dev1_produzione", "device_id": "dev1", "device_class": "energy"},
            {"entity_id": "sensor.dev2_prelievo", "device_id": "dev2", "device_class": "energy"},
        ])
    try:
        cliente = _ClienteLegami(statistiche_errore="Home Assistant non ha risposto")
        bilanci, falliti = await costruisci_bilanci(
            cliente, casa, giorno=G, fuso="Europe/Rome",
            soggetti_energia=["sensor.dev1_produzione", "sensor.dev2_prelievo"],
            direzioni={
                "sensor.dev1_produzione": {"direzione": "produzione", "provenienza": "dichiarata"},
                "sensor.dev2_prelievo": {"direzione": "prelievo", "provenienza": "dichiarata"},
            })
        assert bilanci == []
        assert falliti == 2
    finally:
        casa.chiudi()
