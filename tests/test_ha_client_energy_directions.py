"""`HAClient.energy_directions()`: le direzioni vere dell'energia, lette da
Home Assistant -- non indovinate dal nome del sensore.

Due fonti, sulla STESSA connessione (`_ws_batch` con due comandi):

- **dichiarata** (`energy/get_prefs`, la dashboard Energia): vince sempre.
- **dedotta** (`config/entity_registry/list`, `translation_key`): si applica
  SOLO dove la dichiarata tace, ed e' specifica dell'integrazione
  (`zcsazzurro`, su questa casa) -- vale qui, non su un altro impianto.

**Le forme sono MISURATE sulla casa vera il 27/08/2026** (WebSocket diretto,
non dedotte dal mandato): `grid` porta i due sensori in campi SCALARI
(`stat_energy_from`/`stat_energy_to`), non in liste -- la trappola gia'
pagata il 26/08 su un altro script. `solar` porta anche `stat_rate` (la
potenza, non solo l'energia). I `translation_key` misurati sull'integrazione
`zcsazzurro` sono `power_<direzione>` (nessun suffisso `_today`) e
`energy_<direzione>_today` -- non un pattern regex, sette voci esplicite.

Stessa disciplina di `legami`/`problemi` (`test_ha_client_related_problems.py`):
`{"errore": ...}` su guasto, mai un dizionario vuoto che significherebbe
«nessuna direzione esiste»."""
import pytest

from hiris.app.proxy.ha_client import HAClient


class _Finto:
    """La finta di `_ws_batch` per due comandi: `risposte` e' la lista dei
    DUE messaggi interi che il client vero riceverebbe, nell'ordine
    `energy/get_prefs`, `config/entity_registry/list`. Fedele al contratto
    vero: ogni messaggio e' `{success, result, error}` o `None`
    (connessione/autenticazione fallita)."""

    def __init__(self, risposte=None, *, solleva=False):
        self.risposte = risposte if risposte is not None else [None, None]
        self.solleva = solleva
        self.comandi = []

    async def _ws_batch(self, commands, timeout=10.0):
        self.comandi.extend(commands)
        if self.solleva:
            raise OSError("HA muto")
        return list(self.risposte)


def _client(finto):
    c = HAClient.__new__(HAClient)
    c._ws_batch = finto._ws_batch
    return c


def _prefs(*sorgenti):
    return {"result": {"energy_sources": list(sorgenti)}}


def _registro(*righe):
    return {"result": list(righe)}


def _riga(entity_id, translation_key=None, platform="zcsazzurro"):
    return {"entity_id": entity_id, "translation_key": translation_key, "platform": platform}


# --- i due comandi, sulla stessa connessione -------------------------------

@pytest.mark.asyncio
async def test_manda_i_due_comandi_giusti_su_una_connessione_sola():
    finto = _Finto([_prefs(), _registro()])
    await _client(finto).energy_directions()
    assert finto.comandi == [("energy/get_prefs", None),
                             ("config/entity_registry/list", None)]


# --- la fonte dichiarata (energy/get_prefs) --------------------------------

@pytest.mark.asyncio
async def test_grid_produce_prelievo_e_immissione_dai_campi_scalari():
    """La trappola di forma misurata il 26/08 (e ri-misurata il 27/08 su
    questa fetta): `grid` porta `stat_energy_from`/`stat_energy_to` come
    STRINGHE scalari, non liste. Uno script che si aspettasse liste
    leggerebbe una configurazione piena come vuota."""
    prefs = _prefs({"type": "grid",
                    "stat_energy_from": "sensor.ze1_energia_importata_oggi",
                    "stat_energy_to": "sensor.ze1_energia_esportata_oggi"})
    finto = _Finto([prefs, _registro()])
    esito = await _client(finto).energy_directions()
    assert esito["sensor.ze1_energia_importata_oggi"] == {
        "direzione": "prelievo", "provenienza": "dichiarata"}
    assert esito["sensor.ze1_energia_esportata_oggi"] == {
        "direzione": "immissione", "provenienza": "dichiarata"}


@pytest.mark.asyncio
async def test_solar_produce_produzione_sia_da_energia_sia_da_potenza():
    """`solar` porta DUE sensori -- `stat_energy_from` (l'energia) e
    `stat_rate` (la potenza) -- ed entrambi sono la stessa direzione:
    produzione. Misurato: sono due entita' DIVERSE, entrambe da mappare."""
    prefs = _prefs({"type": "solar",
                    "stat_energy_from": "sensor.ze1_energia_prodotta_oggi",
                    "stat_rate": "sensor.ze1_potenza_prodotta"})
    finto = _Finto([prefs, _registro()])
    esito = await _client(finto).energy_directions()
    assert esito["sensor.ze1_energia_prodotta_oggi"] == {
        "direzione": "produzione", "provenienza": "dichiarata"}
    assert esito["sensor.ze1_potenza_prodotta"] == {
        "direzione": "produzione", "provenienza": "dichiarata"}


@pytest.mark.asyncio
async def test_battery_produce_scarica_da_from_e_carica_da_to():
    prefs = _prefs({"type": "battery",
                    "stat_energy_from": "sensor.ze1_energia_scarica_oggi",
                    "stat_energy_to": "sensor.ze1_energia_carica_oggi"})
    finto = _Finto([prefs, _registro()])
    esito = await _client(finto).energy_directions()
    assert esito["sensor.ze1_energia_scarica_oggi"] == {
        "direzione": "scarica", "provenienza": "dichiarata"}
    assert esito["sensor.ze1_energia_carica_oggi"] == {
        "direzione": "carica", "provenienza": "dichiarata"}


@pytest.mark.asyncio
async def test_le_tre_sorgenti_insieme_come_misurato_sulla_casa_vera():
    """La forma esatta misurata il 27/08/2026 sulla casa vera: tre sorgenti,
    sei entita' dichiarate in tutto (grid ne porta due, solar due, battery
    due)."""
    prefs = _prefs(
        {"type": "grid", "stat_energy_from": "sensor.imp", "stat_energy_to": "sensor.esp"},
        {"type": "solar", "stat_energy_from": "sensor.prod_e", "stat_rate": "sensor.prod_p"},
        {"type": "battery", "stat_energy_from": "sensor.scar", "stat_energy_to": "sensor.car"},
    )
    finto = _Finto([prefs, _registro()])
    esito = await _client(finto).energy_directions()
    assert len(esito) == 6
    assert {v["direzione"] for v in esito.values()} == {
        "prelievo", "immissione", "produzione", "scarica", "carica"}
    assert all(v["provenienza"] == "dichiarata" for v in esito.values())


@pytest.mark.asyncio
async def test_una_dashboard_non_configurata_non_e_un_guasto():
    """`energy_sources: []` e' un esito legittimo (nessuna dashboard), non un
    errore -- come un elenco di legami vuoto per un'entita' senza legami."""
    finto = _Finto([_prefs(), _registro()])
    esito = await _client(finto).energy_directions()
    assert esito == {}
    assert "errore" not in esito


# --- la fonte dedotta (translation_key), e solo dove la dichiarata tace ----

@pytest.mark.asyncio
async def test_la_dedotta_riempie_dove_la_dichiarata_non_arriva():
    """Le sette direzioni dedotte dalla tabella esplicita di `translation_key`
    -- misurate sull'integrazione `zcsazzurro` il 27/08/2026, non un pattern."""
    registro = _registro(
        _riga("sensor.ze1_potenza_consumata", "power_consuming"),
        _riga("sensor.ze1_energia_consumata_oggi", "energy_consuming_today"),
        _riga("sensor.ze1_potenza_autoconsumata", "power_autoconsuming"),
        _riga("sensor.ze1_energia_autoconsumata_oggi", "energy_autoconsuming_today"),
    )
    finto = _Finto([_prefs(), registro])
    esito = await _client(finto).energy_directions()
    assert esito["sensor.ze1_potenza_consumata"] == {
        "direzione": "consumo", "provenienza": "dedotta"}
    assert esito["sensor.ze1_energia_consumata_oggi"] == {
        "direzione": "consumo", "provenienza": "dedotta"}
    assert esito["sensor.ze1_potenza_autoconsumata"] == {
        "direzione": "autoconsumo", "provenienza": "dedotta"}
    assert esito["sensor.ze1_energia_autoconsumata_oggi"] == {
        "direzione": "autoconsumo", "provenienza": "dedotta"}


@pytest.mark.asyncio
async def test_le_sette_direzioni_dedotte_al_completo():
    """Mutazione ESEGUITA sulla tabella: rimossa a mano la voce
    `"power_discharging": "scarica"` -- questo test arrossisce
    (`KeyError`/assert su un dizionario che non contiene piu' la chiave),
    perche' `sensor.scarica_power` sparisce dall'esito. Ripristinata subito
    dopo -- prova diretta che la tabella e' quella che il test legge, non
    un'altra copiata a fianco."""
    coppie = [
        ("power_generating", "energy_generating_today", "produzione"),
        ("power_importing", "energy_importing_today", "prelievo"),
        ("power_exporting", "energy_exporting_today", "immissione"),
        ("power_charging", "energy_charging_today", "carica"),
        ("power_discharging", "energy_discharging_today", "scarica"),
        ("power_consuming", "energy_consuming_today", "consumo"),
        ("power_autoconsuming", "energy_autoconsuming_today", "autoconsumo"),
    ]
    righe = []
    for chiave_potenza, chiave_energia, _ in coppie:
        righe.append(_riga(f"sensor.{chiave_potenza}_power", chiave_potenza))
        righe.append(_riga(f"sensor.{chiave_energia}_energy", chiave_energia))
    finto = _Finto([_prefs(), _registro(*righe)])
    esito = await _client(finto).energy_directions()
    assert len(esito) == 14
    for chiave_potenza, chiave_energia, direzione in coppie:
        assert esito[f"sensor.{chiave_potenza}_power"]["direzione"] == direzione
        assert esito[f"sensor.{chiave_energia}_energy"]["direzione"] == direzione
        assert esito[f"sensor.{chiave_potenza}_power"]["provenienza"] == "dedotta"


@pytest.mark.asyncio
async def test_un_translation_key_non_riconosciuto_non_produce_niente():
    """E' un arricchimento, non un requisito: un'integrazione diversa da
    `zcsazzurro` (qui simulata con `translation_key` a caso, o assente) non
    deve rompere niente e non deve comparire nell'esito."""
    registro = _registro(
        _riga("sensor.altro_1", "total_energy", platform="tuya"),
        _riga("sensor.altro_2", None, platform="tuya"),
        _riga("sensor.altro_3", "power", platform="tuya"),
    )
    finto = _Finto([_prefs(), registro])
    esito = await _client(finto).energy_directions()
    assert esito == {}


@pytest.mark.asyncio
async def test_la_dichiarata_vince_sempre_anche_se_la_dedotta_direbbe_altro():
    """Un'entita' presente in ENTRAMBE le fonti: la dashboard Energia
    (dichiarata) deve vincere, anche se -- per costruire un caso che possa
    davvero fallire -- la dedotta la chiamerebbe diversamente. Sulla casa
    vera le due fonti concordano sempre (e' lo stesso sensore), ma il
    CONTRATTO -- «dichiarata vince sempre» -- va provato indipendentemente
    da quella coincidenza."""
    entity_id = "sensor.ze1_energia_prodotta_oggi"
    prefs = _prefs({"type": "solar", "stat_energy_from": entity_id})
    registro = _registro(_riga(entity_id, "energy_consuming_today"))
    finto = _Finto([prefs, registro])
    esito = await _client(finto).energy_directions()
    assert esito[entity_id] == {"direzione": "produzione", "provenienza": "dichiarata"}


# --- i guasti: mai un dizionario vuoto travestito da «niente» --------------

@pytest.mark.asyncio
@pytest.mark.parametrize("finto,perche", [
    (_Finto(solleva=True), "connessione caduta"),
    (_Finto([None, _registro()]), "energy/get_prefs senza risposta"),
    (_Finto([_prefs(), None]), "entity_registry senza risposta"),
    (_Finto([{"error": {"message": "non trovato"}}, _registro()]), "HA ha rifiutato i prefs"),
    (_Finto([_prefs(), {"error": {"code": "unknown_command"}}]), "HA ha rifiutato il registro"),
    (_Finto([{"result": "non un dizionario"}, _registro()]), "prefs in forma inattesa"),
    (_Finto([_prefs(), {"result": "non una lista"}]), "registro in forma inattesa"),
])
async def test_un_guasto_non_diventa_un_dizionario_vuoto(finto, perche):
    esito = await _client(finto).energy_directions()
    assert "errore" in esito, perche
