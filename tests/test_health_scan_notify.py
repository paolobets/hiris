"""Notifica push per le sole segnalazioni gravi e nuove.

La scansione gira 48 volte al giorno: il valore di questi test non e' che la
notifica parta, ma che NON riparta a ogni giro per lo stesso problema.
"""

import pytest
import yaml
from datetime import datetime, timezone
from pathlib import Path

from hiris.app.brain.advisory_store import AdvisoryStore
from hiris.app.brain.health_scan import MAX_NOTIFICHE_PER_SCANSIONE, run_health_scan

_ADDON = Path(__file__).resolve().parents[1] / "hiris"

_ORA = datetime(2026, 8, 1, tzinfo=timezone.utc)
_NOTIFY_CONFIG = {"ha_notify_service": "notify.mobile_app_paolo",
                  "ingress_click_path": "/hassio/ingress/hiris"}


class _FakeHA:
    """Home Assistant finto: registra le chiamate a servizio, nessun I/O."""

    def __init__(self):
        self.chiamate = []

    async def get_states(self, ids):
        return []

    async def get_automations(self):
        return []

    async def call_service(self, domain, service, data):
        self.chiamate.append((domain, service, data))
        return True


class _HAKo(_FakeHA):
    """L'invio fallisce: la scansione deve continuare a funzionare."""

    async def call_service(self, domain, service, data):
        raise RuntimeError("notify non disponibile")


class _FakeCache:
    def all_states(self):
        return []

    def get_area_map(self):
        return {}


class _FakeSupervisor:
    def __init__(self, addons=None, host_info=None, updates=None):
        self.addons = addons if addons is not None else []
        self.host_info = host_info if host_info is not None else {}
        self.updates = updates if updates is not None else []

    async def get_addons(self):
        return self.addons

    async def get_host_info(self):
        return self.host_info

    async def get_available_updates(self):
        return self.updates


def _addon(stato):
    return [{"slug": "core_samba", "name": "Samba", "state": stato}]


async def _scan(ha, store, supervisor, **extra):
    return await run_health_scan(
        ha_client=ha, entity_cache=_FakeCache(), tiers={}, entity_tiers={},
        store=store, now=_ORA, supervisor_client=supervisor,
        notify_config=_NOTIFY_CONFIG, **extra)


@pytest.mark.asyncio
async def test_segnalazione_grave_e_nuova_notifica(tmp_path):
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    assert res["inserted"] == 1
    assert len(ha.chiamate) == 1
    dominio, servizio, data = ha.chiamate[0]
    assert (dominio, servizio) == ("notify", "mobile_app_paolo")
    assert "Add-on in errore: Samba" in data["message"]
    # Il tap deve aprire HIRIS, come le altre notifiche
    assert data["data"]["clickAction"] == "/hassio/ingress/hiris"
    store.close()


@pytest.mark.asyncio
async def test_stessa_segnalazione_alla_scansione_dopo_non_notifica(tmp_path):
    """Il cuore del task: 48 giri al giorno, una sola notifica."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    supervisor = _FakeSupervisor(addons=_addon("error"))
    await _scan(ha, store, supervisor)
    await _scan(ha, store, supervisor)
    await _scan(ha, store, supervisor)
    assert len(ha.chiamate) == 1
    store.close()


@pytest.mark.asyncio
async def test_segnalazione_riaperta_notifica_di_nuovo(tmp_path):
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    await _scan(ha, store, _FakeSupervisor(addons=[]))  # rientra da sola
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))  # si ripresenta
    assert len(ha.chiamate) == 2
    store.close()


@pytest.mark.asyncio
async def test_severita_non_alta_non_notifica(tmp_path):
    """Un add-on fermo puo' averlo spento l'utente: e' un avviso, non un allarme."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await _scan(ha, store, _FakeSupervisor(addons=_addon("stopped")))
    assert res["inserted"] == 1
    assert ha.chiamate == []
    store.close()


@pytest.mark.asyncio
async def test_innalzamento_a_grave_notifica(tmp_path):
    """Add-on spento (avviso) che poi si guasta davvero: stesso riferimento di
    deduplica, quindi per reconcile e' un aggiornamento. Deve notificare."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    await _scan(ha, store, _FakeSupervisor(addons=_addon("stopped")))
    assert ha.chiamate == []
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    assert len(ha.chiamate) == 1
    assert "Add-on in errore: Samba" in ha.chiamate[0][2]["message"]
    # e restando grave non deve piu' ripetersi
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    assert len(ha.chiamate) == 1
    store.close()


@pytest.mark.asyncio
async def test_grave_che_cambia_titolo_non_ri_notifica(tmp_path):
    """Il disco pieno cambia percentuale (e titolo) a ogni scansione, ma resta
    lo stesso problema gia' notificato."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    await _scan(ha, store, _FakeSupervisor(host_info={"disk_total": 100, "disk_free": 5}))
    assert len(ha.chiamate) == 1
    await _scan(ha, store, _FakeSupervisor(host_info={"disk_total": 100, "disk_free": 4}))
    assert len(ha.chiamate) == 1
    store.close()


@pytest.mark.asyncio
async def test_opzione_disattivata_non_notifica(tmp_path):
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await _scan(ha, store, _FakeSupervisor(addons=_addon("error")),
                      notify_enabled=False)
    assert res["inserted"] == 1  # la scansione lavora comunque
    assert ha.chiamate == []
    store.close()


@pytest.mark.asyncio
async def test_senza_configurazione_di_notifica_non_notifica(tmp_path):
    """Nessun canale configurato: la scansione resta quella di prima."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await run_health_scan(
        ha_client=ha, entity_cache=_FakeCache(), tiers={}, entity_tiers={},
        store=store, now=_ORA, supervisor_client=_FakeSupervisor(addons=_addon("error")))
    assert res["inserted"] == 1
    assert ha.chiamate == []
    store.close()


@pytest.mark.asyncio
async def test_invio_fallito_non_fa_fallire_la_scansione(tmp_path):
    ha = _HAKo()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    assert res["inserted"] == 1
    assert store.list(status="open")  # la segnalazione resta registrata
    store.close()


@pytest.mark.asyncio
async def test_raffica_di_problemi_gravi_riassunta(tmp_path):
    """Un guasto che ne apre molti in un colpo solo (tipico dopo un riavvio)
    non deve tradursi in una raffica di push: oltre il tetto parte un solo
    messaggio di riepilogo."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    entita = {f"lock.porta_{i}": "green" for i in range(8)}
    res = await run_health_scan(
        ha_client=ha, entity_cache=_FakeCache(), tiers={}, entity_tiers=entita,
        store=store, now=_ORA, supervisor_client=None,
        notify_config=_NOTIFY_CONFIG)
    assert res["inserted"] == 8
    assert len(ha.chiamate) == MAX_NOTIFICHE_PER_SCANSIONE + 1
    riepilogo = ha.chiamate[-1][2]["message"]
    assert str(8 - MAX_NOTIFICHE_PER_SCANSIONE) in riepilogo
    store.close()


def test_opzione_di_disattivazione_cablata():
    """L'opzione deve esistere davvero nell'add-on, non solo nel codice."""
    cfg = yaml.safe_load((_ADDON / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["options"]["brain_notify_high"] is True  # predefinito: attivo
    assert cfg["schema"]["brain_notify_high"] == "bool"
    assert "BRAIN_NOTIFY_HIGH" in (_ADDON / "run.sh").read_text(encoding="utf-8")
    for lingua in ("it.yaml", "en.yaml"):
        testo = (_ADDON / "translations" / lingua).read_text(encoding="utf-8")
        assert "brain_notify_high" in testo


@pytest.mark.asyncio
async def test_un_invio_fallito_non_blocca_gli_altri(tmp_path):
    class _HAPrimaKo(_FakeHA):
        async def call_service(self, domain, service, data):
            if not self.chiamate:
                self.chiamate.append((domain, service, data))
                raise RuntimeError("primo invio fallito")
            self.chiamate.append((domain, service, data))
            return True

    ha = _HAPrimaKo()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    supervisor = _FakeSupervisor(
        addons=_addon("error"),
        host_info={"disk_total": 100, "disk_free": 5},
    )
    res = await _scan(ha, store, supervisor)
    assert res["inserted"] == 2
    assert len(ha.chiamate) == 2
    store.close()
