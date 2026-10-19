"""Le integrazioni ferme si dicono una volta (richiesta del proprietario,
15/10/2026; proposta in `/mnt/project-files/chiusura/integrazioni-ferme-
proposta.md`, decisioni del 16/10/2026).

**Il fatto.** Il proprietario ha spento un'integrazione con 61 dispositivi e
nessuno gliel'ha detto: l'osservatore taceva per scelta sulle istanze spente
da lui, e Home Assistant non apre una riparazione ne' per un'istanza spenta
ne' per una in `setup_error`/`setup_retry` (letto nel sorgente, tag
2026.9.4: le riparazioni di `config_entries.py` sono la riautenticazione,
l'integrazione sparita e l'id doppio). Nessuna automazione puo' scattare
sul cambio: viaggia come segnale interno, non come evento.

**Da qui.**
- una lettura sola dice perche' un'istanza e' ferma
  (`ha_vocabulary.config_entry_stop`), per l'osservatore, il nucleo e
  l'avviso;
- quando un'istanza si ferma -- spenta dal proprietario o in errore -- parte
  UNA push agli amministratori, con i dispositivi e le stanze che restano
  senza; quando torna, una riga;
- la prima volta, le istanze gia' ferme vanno in una push sola (scelta del
  proprietario);
- un'istanza si dice ferma dopo DUE giri che la vedono ferma, e tornata dopo
  due giri che la vedono caricata: al riavvio di Home Assistant le istanze
  passano da stati di passaggio, e un avviso per giro sarebbe una raffica.
"""
from __future__ import annotations

import pytest

from hiris.app.home_space import briefing, reader
from hiris.app.home_space.ha_vocabulary import (
    CONFIG_ENTRY_FAILURE_STATES,
    CONFIG_ENTRY_STATES,
    ENTRY_BROKEN,
    ENTRY_SWITCHED_OFF,
    ENTRY_UNKNOWN_STATE,
    config_entry_stop,
)
from hiris.app.home_space.house import House
from hiris.app.home_space.topology import live_mirror
from hiris.app.mind import stopped_integrations as si
from hiris.app.mind.store import ObservationsStore
from hiris.app.mind.watcher import Watcher
from tests.test_mind_watcher import _SCOPE_DECISO, _FintoArchivio

# -- la lettura sola -----------------------------------------------------------


def test_spenta_dal_proprietario():
    assert config_entry_stop("not_loaded", "user", "user") == ENTRY_SWITCHED_OFF


def test_ogni_stato_di_guasto_e_in_errore():
    """Chiesto all'enumerazione, non ricopiato."""
    assert len(CONFIG_ENTRY_FAILURE_STATES) >= 4
    for state in CONFIG_ENTRY_FAILURE_STATES:
        assert config_entry_stop(state, None, "user") == ENTRY_BROKEN


def test_gli_altri_stati_noti_non_sono_un_fermo():
    """`not_loaded` senza `disabled_by` e' lo stato da cui ogni istanza passa
    al riavvio (developers.home-assistant.io/docs/config_entries_index/):
    non e' un fermo. Nemmeno gli stati di passaggio."""
    for state in CONFIG_ENTRY_STATES - CONFIG_ENTRY_FAILURE_STATES:
        assert config_entry_stop(state, None, "user") is None, state


def test_una_voce_ignorata_non_e_mai_ferma():
    assert config_entry_stop("setup_error", None, "ignore") is None
    assert config_entry_stop("not_loaded", "user", "ignore") is None


def test_uno_stato_che_il_vocabolario_non_conosce_si_dice_tale():
    assert config_entry_stop("stato_di_domani", None, "user") == ENTRY_UNKNOWN_STATE


# -- l'osservatore apre la condizione anche sull'istanza spenta ---------------

def test_l_osservatore_annota_l_istanza_spenta_dal_proprietario():
    """Mutazione ESEGUITA: l'osservatore torna a scartare le istanze spente
    (la vecchia `config_entry_is_healthy` su `not_loaded`) -- rossa."""
    archivio = _FintoArchivio(scope=_SCOPE_DECISO)
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    scritti = osservatore.watch_system(problems=[], integrations=[
        {"entry_id": "ave", "domain": "ave_domina", "title": "Casa",
         "state": "not_loaded", "disabled_by": "user", "source": "user"}],
        log_entries=[])
    assert scritti == 1
    assert archivio.annotati[0]["subject"] == "integrazione:ave"


# -- il nucleo dice le istanze spente -----------------------------------------

def test_il_nucleo_dice_l_istanza_spenta_e_quella_in_errore():
    """Le istanze dal lettore vero (`reader._integration`), che porta il
    perche' in `fermo`."""
    frase = briefing._integrations_notice([reader._integration(r) for r in (
        {"entry_id": "a", "domain": "ave_domina", "title": "Casa",
         "state": "not_loaded", "disabled_by": "user", "source": "user"},
        {"entry_id": "l", "domain": "lifx", "title": "Lampada",
         "state": "setup_retry", "source": "dhcp"},
        {"entry_id": "f", "domain": "fritz", "title": "Ignorata",
         "state": "not_loaded", "source": "ignore"})])
    assert "ave_domina" in frase and "spenta dal proprietario" in frase
    assert "lifx" in frase and "setup_retry" in frase
    assert "fritz" not in frase


# -- l'avviso -----------------------------------------------------------------

def _casa() -> House:
    home_space = {
        "piani": [], "etichette": [], "categorie": [],
        "aree": [{"id": "soggiorno", "nome": "Soggiorno"},
                 {"id": "cucina", "nome": "Cucina"}],
        "dispositivi": [{"id": "d1", "nome": "Luce 1", "area_id": "soggiorno"},
                        {"id": "d2", "nome": "Luce 2", "area_id": "cucina"},
                        {"id": "d3", "nome": "Lampada", "area_id": None}],
        "entita": [
            {"id": "light.uno", "dispositivo_id": "d1", "config_entry_id": "ave"},
            {"id": "light.uno_b", "dispositivo_id": "d1", "config_entry_id": "ave"},
            {"id": "light.due", "dispositivo_id": "d2", "config_entry_id": "ave"},
            {"id": "light.lampada", "dispositivo_id": "d3", "config_entry_id": "lifx",
             "area_id": "soggiorno"}],
    }
    return House(home_space, live_mirror([]))


AVE = {"entry_id": "ave", "domain": "ave_domina", "title": "Casa",
       "state": "not_loaded", "disabled_by": "user", "source": "user"}
LIFX_ROTTA = {"entry_id": "lifx", "domain": "lifx", "title": "Lampada",
              "state": "setup_retry", "source": "dhcp"}
LIFX_VIVA = {**LIFX_ROTTA, "state": "loaded"}


class _Avvisi:
    """La porta degli avvisi agli amministratori, finta: tiene i testi."""

    def __init__(self, esito=None):
        self.testi = []
        self.esito = esito or {"amministratori": 1, "push": 1, "mancate": [],
                               "senza_telefono": []}

    async def __call__(self, text):
        self.testi.append(text)
        return self.esito


@pytest.fixture()
def archivio(tmp_path):
    return ObservationsStore(str(tmp_path / "mind.db"))


def _dette(archivio) -> dict:
    return {k: r["detta"] for k, r in archivio.integration_notices().items()
            if r["detta"]}


async def _giro(archivio, integrations, avvisi, now):
    return await si.tell(archivio, _casa(), integrations, notify=avvisi, now=now)


@pytest.mark.asyncio
async def test_un_istanza_ferma_si_dice_al_secondo_giro_e_una_volta_sola(archivio):
    """Mutazione ESEGUITA: dire l'istanza al primo giro che la vede ferma --
    rossa (la push parte al giro 1)."""
    avvisi = _Avvisi()
    await _giro(archivio, [AVE, LIFX_VIVA], avvisi, 1_790_000_000.0)
    assert avvisi.testi == []
    await _giro(archivio, [AVE, LIFX_VIVA], avvisi, 1_790_000_600.0)
    await _giro(archivio, [AVE, LIFX_VIVA], avvisi, 1_790_001_200.0)
    assert len(avvisi.testi) == 1
    testo = avvisi.testi[0]
    assert "Casa" in testo and "spenta da te" in testo
    assert "2 dispositivi" in testo
    assert "Cucina" in testo and "Soggiorno" in testo


@pytest.mark.asyncio
async def test_la_prima_volta_le_istanze_gia_ferme_vanno_in_una_push_sola(archivio):
    """La scelta del proprietario (16/10/2026): una riassuntiva."""
    avvisi = _Avvisi()
    for now in (1_790_000_000.0, 1_790_000_600.0):
        await _giro(archivio, [AVE, LIFX_ROTTA], avvisi, now)
    assert len(avvisi.testi) == 1
    assert "Casa" in avvisi.testi[0] and "Lampada" in avvisi.testi[0]
    assert "setup_retry" in avvisi.testi[0]


@pytest.mark.asyncio
async def test_un_passaggio_di_un_giro_non_si_dice(archivio):
    """Al riavvio di Home Assistant un'istanza passa da `setup_retry` e
    torna: un giro solo non e' un fermo."""
    avvisi = _Avvisi()
    await _giro(archivio, [LIFX_ROTTA], avvisi, 1_790_000_000.0)
    await _giro(archivio, [LIFX_VIVA], avvisi, 1_790_000_600.0)
    await _giro(archivio, [LIFX_VIVA], avvisi, 1_790_001_200.0)
    assert avvisi.testi == []
    assert _dette(archivio) == {}


@pytest.mark.asyncio
async def test_quando_torna_una_riga_e_poi_silenzio(archivio):
    """La scelta del proprietario (16/10/2026): al ritorno, una riga.

    Mutazione ESEGUITA: niente riga al ritorno -- rossa."""
    avvisi = _Avvisi()
    for now in (1_790_000_000.0, 1_790_000_600.0):
        await _giro(archivio, [LIFX_ROTTA], avvisi, now)
    for now in (1_790_001_200.0, 1_790_001_800.0, 1_790_002_400.0):
        await _giro(archivio, [LIFX_VIVA], avvisi, now)
    assert len(avvisi.testi) == 2
    assert "Lampada" in avvisi.testi[1] and "tornata" in avvisi.testi[1]
    assert _dette(archivio) == {}


@pytest.mark.asyncio
async def test_se_non_si_sa_a_chi_dirlo_si_riprova_al_giro_dopo(archivio):
    """`notify_admins` torna `{"errore"}` quando non sa chi amministra: non
    si segna come detto ciò che non e' partito."""
    avvisi = _Avvisi({"errore": "utenti di Home Assistant non letti"})
    for now in (1_790_000_000.0, 1_790_000_600.0, 1_790_001_200.0):
        await _giro(archivio, [AVE], avvisi, now)
    assert len(avvisi.testi) == 2
    assert _dette(archivio) == {}


@pytest.mark.asyncio
async def test_un_istanza_sparita_si_dimentica_senza_avviso(archivio):
    avvisi = _Avvisi()
    for now in (1_790_000_000.0, 1_790_000_600.0):
        await _giro(archivio, [AVE], avvisi, now)
    await _giro(archivio, [], avvisi, 1_790_001_200.0)
    assert len(avvisi.testi) == 1
    assert _dette(archivio) == {}


def test_i_dispositivi_di_un_istanza_si_chiedono_alla_casa():
    """Fondamenta 4: la casa sa rispondere a «quali dispositivi ha
    quest'istanza?», e l'avviso lo chiede a lei."""
    assert sorted(d["id"] for d in _casa().instance_devices("ave")) == ["d1", "d2"]
    assert _casa().instance_devices("nessuna") == []


# -- il cablaggio: il giro delle condizioni avvisa -----------------------------

def test_il_giro_delle_condizioni_avvisa_dopo_l_osservatore(archivio):
    """Il giro vero (`watch_system_conditions`) sulla casa finta, col client
    vero sopra: al secondo giro con l'istanza spenta parte una push, con
    l'attore dell'osservatore.

    Mutazione ESEGUITA: tolta la chiamata a `stopped_integrations.tell` dal
    giro -- rossa."""
    import asyncio
    from unittest import mock

    from hiris.app.mind import conditions_round
    from hiris.app.mind.store import OBSERVATIONS_KEY
    from hiris.app.mind.watcher import WATCHER_KEY
    from hiris.app.startup import live_values
    from tests.test_mind_wiring import _announced, _OsservatoreFinto, _system_house

    mandati = []

    async def finto_avviso(app, text, *, actor):
        mandati.append((text, actor))
        return {"amministratori": 1, "push": 1, "mancate": [], "senza_telefono": []}

    app = _announced({**live_values(), WATCHER_KEY: _OsservatoreFinto(),
                      OBSERVATIONS_KEY: archivio}, [AVE])
    house = _system_house([], [AVE])
    with mock.patch.object(conditions_round, "notify_admins", finto_avviso):
        asyncio.run(conditions_round.watch_system_conditions(app, house))
        asyncio.run(conditions_round.watch_system_conditions(app, house))
    assert len(mandati) == 1
    assert "spenta da te" in mandati[0][0]
    assert mandati[0][1] == "osservatore"
