"""La dashboard Energia letta dal client: `HAClient.energy_prefs()` (piano degli
attori, strato 2, Task 2.1).

**Cosa difende.** Le direzioni dell'energia -- chi e' rete, sole, batteria --
le dichiara l'utente nella dashboard Energia di Home Assistant, e non si
indovinano dai nomi dei sensori (CLAUDE.md: l'energia prodotta letta come
«consumo»). Il client le legge con UN comando, `energy/get_prefs`, e le rende
come Home Assistant le manda, oppure con la busta del guasto della Tappa 2.

**La forma viene dal sorgente, non dalla casa.** Letta il 04/10/2026 al tag
`2026.9.4` (`components/energy/data.py`, `websocket_api.py::ws_get_prefs`):
la risposta e' `manager.data` intero. La rete ha due forme nella storia di
Home Assistant -- i campi singoli di oggi e le liste `flow_from`/`flow_to` di
prima della migrazione (`STORAGE_MINOR_VERSION = 3`) -- e il client le passa
entrambe com'e': a giudicarle e' chi legge. Il Task 2.0 (dal vivo) dira' quale
manda questa casa; il 27/08/2026 era gia' stata misurata a campi singoli.

Mutazioni ESEGUITE (04/10/2026), ognuna rossa per la sua ragione e
ripristinata (`git status` pulito):

- tolto `energy_prefs` da `HAClient` -- rosse tutte (`AttributeError`), e il
  cancello dei costi e delle buste perde il caso: la prova rossa del Passo 1;
- il client che tiene solo le sorgenti con `stat_energy_from` (una «pulizia»
  che non sa della forma vecchia) -- rossa la prova della rete a liste;
- tolto il controllo su `energy_sources` -- rossa la prova della forma;
- `not_found` trasformato in preferenze vuote -- rossa la prova della casa
  senza dashboard: «non dichiarato» diventava «dichiarato niente».
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

from hiris.app.proxy.ha_client import HAClient


def _run(coroutine):
    return asyncio.run(coroutine)


def _grid(**fields) -> dict:
    """Una rete nella forma di oggi (`GridSourceType`): i campi singoli, e le
    chiavi del prezzo che lo schema di Home Assistant scrive sempre."""
    return {"type": "grid", "stat_energy_from": None, "stat_energy_to": None,
            "stat_cost": None, "entity_energy_price": None, "number_energy_price": None,
            "stat_compensation": None, "entity_energy_price_export": None,
            "number_energy_price_export": None, "cost_adjustment_day": 0.0, **fields}


#: Una dashboard intera, nella forma di `EnergyPreferences` al tag `2026.9.4`:
#: rete con prelievo e immissione, sole con la potenza, batteria con lo stato
#: di carica e la capacita', un consumo di dispositivo. Nessun nome vero.
PREFS = {
    "energy_sources": [
        _grid(stat_energy_from="sensor.rete_prelievo", stat_energy_to="sensor.rete_immissione"),
        {"type": "solar", "stat_energy_from": "sensor.sole_energia",
         "stat_rate": "sensor.sole_potenza", "config_entry_solar_forecast": None},
        {"type": "battery", "stat_energy_from": "sensor.batteria_scarica",
         "stat_energy_to": "sensor.batteria_carica", "stat_soc": "sensor.batteria_carica_pct",
         "capacity": 10.0},
    ],
    "device_consumption": [{"stat_consumption": "sensor.lavatrice_energia"}],
    "device_consumption_water": [],
}

#: La rete nella forma di PRIMA della migrazione (`LegacyGridSourceType`):
#: liste di flussi invece di campi singoli. Al tag letto Home Assistant la
#: migra quando carica le preferenze; il client non la traduce e non la perde.
LEGACY_PREFS = {
    "energy_sources": [{
        "type": "grid",
        "flow_from": [{"stat_energy_from": "sensor.rete_prelievo", "stat_cost": None,
                       "entity_energy_price": None, "number_energy_price": None}],
        "flow_to": [{"stat_energy_to": "sensor.rete_immissione", "stat_compensation": None,
                     "entity_energy_price": None, "number_energy_price": None}],
        "cost_adjustment_day": 0.0}],
    "device_consumption": [],
}


def test_dichiara_il_suo_costo():
    assert HAClient.energy_prefs.cost == {"ws": 1, "rest": 0}


def test_rende_le_preferenze_come_le_manda_home_assistant():
    house = CasaFinta({"energy_prefs": PREFS})
    assert _run(house.energy_prefs()) == PREFS
    assert house.calls == [("energy/get_prefs", None)]
    assert house.connections == [("ws", ("energy/get_prefs",))]


def test_la_rete_a_campi_singoli_porta_anche_l_immissione_assente():
    """`stat_energy_to: None` e' una rete che preleva e non immette: la chiave
    c'e' e vale `None`, e il client non la toglie."""
    prefs = {"energy_sources": [_grid(stat_energy_from="sensor.rete_prelievo")],
             "device_consumption": []}
    answer = _run(CasaFinta({"energy_prefs": prefs}).energy_prefs())
    assert answer["energy_sources"][0]["stat_energy_to"] is None
    assert answer == prefs


def test_la_rete_a_liste_passa_com_e():
    answer = _run(CasaFinta({"energy_prefs": LEGACY_PREFS}).energy_prefs())
    assert answer == LEGACY_PREFS


def test_una_casa_senza_dashboard_e_un_rifiuto_col_codice_di_home_assistant():
    """`ws_get_prefs`: `manager.data is None` -> `send_error(ERR_NOT_FOUND,
    "No prefs")`. Non si inventano preferenze vuote."""
    house = CasaFinta({}, refuse={"energy/get_prefs": {"code": "not_found",
                                                       "message": "No prefs"}})
    assert _run(house.energy_prefs()) == {"errore": "No prefs", "causa": "rifiuto",
                                          "codice": "not_found"}


def test_il_silenzio_e_la_busta_del_silenzio():
    answer = _run(CasaFinta({}, silence={"energy/get_prefs"}).energy_prefs())
    assert answer["causa"] == "silenzio"
    assert answer["errore"] and answer["codice"] is None


def test_preferenze_senza_le_sorgenti_sono_una_forma_inattesa():
    """Un oggetto senza `energy_sources` in lista non e' una dashboard vuota
    (quella e' `[]`): e' una risposta che il client non sa leggere."""
    answer = _run(CasaFinta({"energy_prefs": {"device_consumption": []}}).energy_prefs())
    assert answer["causa"] == "forma"
    empty = {"energy_sources": [], "device_consumption": []}
    assert _run(CasaFinta({"energy_prefs": empty}).energy_prefs()) == empty
