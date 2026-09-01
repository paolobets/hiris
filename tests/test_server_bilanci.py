"""`server.build_balances`: il raggruppamento per dispositivo (senza
nessuna lettura di rete, il registro e' gia' replicato in `archivio_casa`) e
UNA connessione sola per tutti i dispositivi candidati (`HAClient.
statistiche_orarie`).
"""
from datetime import UTC, datetime

import pytest

from hiris.app.casa.archivio import HomeSpaceStore
from hiris.app.cervello.oggetti import day_boundaries
from hiris.app.server import build_balances
from tests.test_cervello_comprimari import _ClienteLegami

G = "2026-08-24"


def _casa(tmp_path, *, entita, dispositivi):
    """Un `ArchivioCasa` reale, seminato coi registri GREZZI (chiavi
    inglesi, come li manderebbe `HAClient.read_registries()`): fedele al
    contratto vero di `ArchivioCasa.sostituisci`, non una finta a parte."""
    a = HomeSpaceStore(str(tmp_path / "casa.db"))
    a.replace({"dispositivi": dispositivi, "entita": entita}, [],
                 reference_frame={"fuso": "Europe/Rome"})
    return a


def _iso_giorno(giorno=G, fuso="Europe/Rome"):
    da_ts, a_ts = day_boundaries(giorno, fuso)
    return (datetime.fromtimestamp(da_ts, tz=UTC).isoformat(),
            datetime.fromtimestamp(a_ts, tz=UTC).isoformat())


def _punto(cambio, ora=6):
    """Un punto orario tradotto, con istanti VERI -- non `"x"`/`"y"`
    (correzione del mandato «il bilancio dell'energia», punto 1, secondo
    paragrafo, 27/08/2026): una stringa segnaposto non sa nemmeno
    RAPPRESENTARE un istante, e a quel livello il contenuto della curva
    resta strutturalmente non verificabile."""
    return {"inizio": f"2026-08-24T{ora:02d}:00:00+00:00",
            "fine": f"2026-08-24T{ora + 1:02d}:00:00+00:00",
            "minimo": None, "massimo": None, "media": None, "cambio": cambio}


@pytest.mark.asyncio
async def test_senza_archivio_casa_niente_bilanci_niente_rete():
    cliente = _ClienteLegami()
    bilanci, falliti = await build_balances(
        cliente, None, day=G, timezone="Europe/Rome",
        energy_subjects=["sensor.x"], directions={})
    assert bilanci == []
    assert falliti == 0
    assert cliente.statistiche_chieste == []


@pytest.mark.asyncio
async def test_senza_soggetti_niente_bilanci_niente_rete(tmp_path):
    casa = _casa(tmp_path, entita=[], dispositivi=[])
    cliente = _ClienteLegami()
    try:
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=[], directions={})
        assert bilanci == []
        assert falliti == 0
        assert cliente.statistiche_chieste == []
    finally:
        casa.close()


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
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.energia_prodotta_oggi"],
            directions={"sensor.energia_prodotta_oggi":
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
        casa.close()


@pytest.mark.asyncio
async def test_il_consumo_da_solo_ora_basta_e_diventa_un_candidato(tmp_path):
    """**Correzione ALTO della review (mandato «il bilancio dell'energia»,
    punto 1, 27/08/2026): "consumo" e' entrato in `BALANCE_DIRECTIONS`
    come settimo totale, letto e non piu' derivato.** Un dispositivo la cui
    UNICA direzione utile e' "consumo" ora diventa un candidato come gli
    altri sei -- prima di questa correzione non lo era (il totale veniva
    buttato via in nome di un'identita' che su questa integrazione e'
    falsa: vedi `test_cervello_bilancio.py`)."""
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}],
        entita=[{"entity_id": "sensor.energia_consumata_oggi", "device_id": "dev1",
                "device_class": "energy"}])
    try:
        cliente = _ClienteLegami(statistiche={
            "sensor.energia_consumata_oggi": [_punto(14.72)]})
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.energia_consumata_oggi"],
            directions={"sensor.energia_consumata_oggi":
                      {"direzione": "consumo", "provenienza": "dedotta"}})
        assert falliti == 0
        [b] = bilanci
        assert b["corpo"]["totali"]["consumo"]["valore"] == 14.72
    finally:
        casa.close()


@pytest.mark.asyncio
async def test_senza_nessuna_direzione_utile_niente_bilancio_niente_rete(tmp_path):
    """Un dispositivo la cui unica entita' non ha NESSUNA direzione nota
    (assente da `direzioni`) non diventa un candidato: nessuna chiamata di
    rete, le sue entita' restano fuori da ogni bilancio."""
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}],
        entita=[{"entity_id": "sensor.temperatura_inverter", "device_id": "dev1",
                "device_class": "energy"}])
    try:
        cliente = _ClienteLegami()
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.temperatura_inverter"],
            directions={})
        assert bilanci == []
        assert falliti == 0
        assert cliente.statistiche_chieste == []
    finally:
        casa.close()


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
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.potenza_prodotta"],
            directions={"sensor.potenza_prodotta":
                      {"direzione": "produzione", "provenienza": "dichiarata"}})
        assert bilanci == []
        assert falliti == 0
        assert cliente.statistiche_chieste == []
    finally:
        casa.close()


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
            "sensor.batteria": [{"inizio": "2026-08-24T06:00:00+00:00",
                                 "fine": "2026-08-24T07:00:00+00:00", "minimo": None,
                                 "massimo": None, "media": 55.0, "cambio": None}],
        })
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.energia_prodotta_oggi"],
            directions={"sensor.energia_prodotta_oggi":
                      {"direzione": "produzione", "provenienza": "dichiarata"}})

        assert falliti == 0
        [b] = bilanci
        # `batteria_percentuale_oraria` porta l'ORA di ogni punto, come
        # `forma` (correzione del mandato, punto 2, 27/08/2026): non piu'
        # una lista nuda di percentuali.
        assert b["corpo"]["batteria_percentuale_oraria"] == [
            {"ora": "2026-08-24T06:00:00+00:00", "valore": 55.0}]
        ids, _, _ = cliente.statistiche_chieste[0]
        assert set(ids) == {"sensor.energia_prodotta_oggi", "sensor.batteria"}
    finally:
        casa.close()


@pytest.mark.asyncio
async def test_un_entita_senza_dispositivo_non_e_un_errore_resta_fuori(tmp_path):
    """«Un'entita' senza dispositivo non e' un errore: non entra in nessun
    bilancio e continua per la sua strada» (mandato, punto 3)."""
    casa = _casa(tmp_path, dispositivi=[],
                entita=[{"entity_id": "sensor.orfana", "device_id": None,
                        "device_class": "energy"}])
    try:
        cliente = _ClienteLegami()
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.orfana"],
            directions={"sensor.orfana": {"direzione": "produzione", "provenienza": "dichiarata"}})
        assert bilanci == []
        assert falliti == 0
        assert cliente.statistiche_chieste == []
    finally:
        casa.close()


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
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.dev1_produzione", "sensor.dev2_prelievo"],
            directions={
                "sensor.dev1_produzione": {"direzione": "produzione", "provenienza": "dichiarata"},
                "sensor.dev2_prelievo": {"direzione": "prelievo", "provenienza": "dichiarata"},
            })
        assert falliti == 0
        assert {b["dispositivo_id"] for b in bilanci} == {"dev1", "dev2"}
        assert len(cliente.statistiche_chieste) == 1  # UNA connessione per ENTRAMBI
    finally:
        casa.close()


@pytest.mark.asyncio
async def test_una_serie_vuota_per_un_candidato_conta_come_fallimento(tmp_path):
    """**Punto 3 del mandato (MEDIO, 27/08/2026)**: la richiesta RIESCE
    (nessun `errore`), ma la serie torna vuota per questo dispositivo --
    identificatori rinominati, recorder ripartito (misurato: il database
    del recorder e' gia' rinato una volta, il 13 agosto). Prima di questa
    correzione `falliti` restava a zero: la riparazione all'avvio
    (`reaggregate_last_two_days`, che SOSTITUISCE) avrebbe scritto
    sopra un giorno che aveva gia' un bilancio uno senza -- gli undici
    frammenti tornano. Ora conta come fallito anche senza nessun `errore`
    da Home Assistant."""
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}],
        entita=[{"entity_id": "sensor.energia_prodotta_oggi", "device_id": "dev1",
                "device_class": "energy"}])
    try:
        cliente = _ClienteLegami(statistiche={})  # riesce, ma non c'e' niente
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.energia_prodotta_oggi"],
            directions={"sensor.energia_prodotta_oggi":
                      {"direzione": "produzione", "provenienza": "dichiarata"}})
        assert bilanci == []
        assert falliti == 1
    finally:
        casa.close()


@pytest.mark.asyncio
async def test_i_membri_del_bilancio_sono_solo_i_soggetti_con_una_direzione_vera(tmp_path):
    """**Punto 6 del mandato (BASSO, 27/08/2026)**: nella vita vera
    `soggetti_energia` porta TUTTI i soggetti osservati quel giorno, non
    solo quelli di energia (`server.py::_aggrega_ieri`/`riaggrega_gli_
    ultimi_due_giorni` passano `sorted(soggetti)`, senza filtro). Prima di
    questa correzione un interruttore o un sensore diagnostico dello STESSO
    dispositivo finiva elencato in `entita` come «dentro il bilancio», pur
    continuando a produrre il proprio episodio -- falso su un dispositivo
    misto. Qui il dispositivo ha due entita': una con una direzione vera
    (produzione) e una senza (nessuna voce in `direzioni`) -- `entita` deve
    contenere solo la prima."""
    casa = _casa(
        tmp_path,
        dispositivi=[{"id": "dev1", "name": "Inverter"}],
        entita=[
            {"entity_id": "sensor.energia_prodotta_oggi", "device_id": "dev1",
             "device_class": "energy"},
            {"entity_id": "switch.inverter_relay", "device_id": "dev1",
             "device_class": None},
        ])
    try:
        cliente = _ClienteLegami(statistiche={
            "sensor.energia_prodotta_oggi": [_punto(1.0)]})
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.energia_prodotta_oggi", "switch.inverter_relay"],
            directions={"sensor.energia_prodotta_oggi":
                      {"direzione": "produzione", "provenienza": "dichiarata"}})
        assert falliti == 0
        [b] = bilanci
        assert b["entita"] == ["sensor.energia_prodotta_oggi"]
    finally:
        casa.close()


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
        bilanci, falliti = await build_balances(
            cliente, casa, day=G, timezone="Europe/Rome",
            energy_subjects=["sensor.dev1_produzione", "sensor.dev2_prelievo"],
            directions={
                "sensor.dev1_produzione": {"direzione": "produzione", "provenienza": "dichiarata"},
                "sensor.dev2_prelievo": {"direzione": "prelievo", "provenienza": "dichiarata"},
            })
        assert bilanci == []
        assert falliti == 2
    finally:
        casa.close()
