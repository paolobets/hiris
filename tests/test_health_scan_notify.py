"""Notifica push per le sole segnalazioni gravi e nuove.

La scansione gira 48 volte al giorno: il valore di questi test non e' che la
notifica parta, ma che NON riparta a ogni giro per lo stesso problema.
"""

import logging

import pytest
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hiris.app.brain.advisory_store import AdvisoryStore
from hiris.app.brain.health_checks import CHECK_IDS
from hiris.app.brain.health_scan import (
    ETICHETTE_CONTROLLO, MAX_NOTIFICHE_PER_SCANSIONE, PRIORITA_CONTROLLO,
    SILENZIO_NOTIFICA_ORE, run_health_scan)

_ADDON = Path(__file__).resolve().parents[1] / "hiris"

_ORA = datetime(2026, 8, 1, tzinfo=timezone.utc)
_DOPO_IL_SILENZIO = _ORA + timedelta(hours=SILENZIO_NOTIFICA_ORE + 1)
_NOTIFY_CONFIG = {"ha_notify_service": "notify.mobile_app_paolo",
                  "ingress_click_path": "/hassio/ingress/hiris"}


class _FakeHA:
    """Home Assistant finto: registra le chiamate a servizio, nessun I/O."""

    def __init__(self, automazioni=None):
        self.chiamate = []
        self.automazioni = automazioni or []

    async def get_states(self, ids):
        return []

    async def get_automations(self):
        return self.automazioni

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


def _automazione_ko(quante):
    return [{"entity_id": f"automation.a{i}", "state": "unavailable",
             "attributes": {"friendly_name": f"Automazione {i}"}}
            for i in range(quante)]


async def _scan(ha, store, supervisor, *, now=_ORA, **extra):
    return await run_health_scan(
        ha_client=ha, entity_cache=_FakeCache(), tiers={}, entity_tiers={},
        store=store, now=now, supervisor_client=supervisor,
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
    """Passato il periodo di silenzio, un problema che si ripresenta e' una
    notizia nuova."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    await _scan(ha, store, _FakeSupervisor(addons=[]))  # rientra da sola
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")),
                now=_DOPO_IL_SILENZIO)  # si ripresenta il giorno dopo
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


@pytest.mark.asyncio
async def test_riepilogo_al_singolare(tmp_path):
    """Una sola segnalazione oltre il tetto: il riepilogo resta leggibile."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    entita = {f"lock.porta_{i}": "green"
              for i in range(MAX_NOTIFICHE_PER_SCANSIONE + 1)}
    await run_health_scan(
        ha_client=ha, entity_cache=_FakeCache(), tiers={}, entity_tiers=entita,
        store=store, now=_ORA, supervisor_client=None,
        notify_config=_NOTIFY_CONFIG)
    assert len(ha.chiamate) == MAX_NOTIFICHE_PER_SCANSIONE + 1
    assert "un altro problema grave" in ha.chiamate[-1][2]["message"].lower()
    store.close()


# ── FIX 1: memoria di "ho gia' avvisato" ──────────────────────────────────

@pytest.mark.asyncio
async def test_valore_che_sfarfalla_attorno_alla_soglia_notifica_una_volta(tmp_path):
    """Il caso che il periodo di silenzio esiste per coprire: un disco che
    oscilla attorno al 10% libero scende (grave), risale (avviso) e riscende
    (grave). Senza memoria sarebbero due notifiche, e cosi' a ogni giro."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    grave = _FakeSupervisor(host_info={"disk_total": 100, "disk_free": 9})
    avviso = _FakeSupervisor(host_info={"disk_total": 100, "disk_free": 15})
    await _scan(ha, store, grave)
    assert len(ha.chiamate) == 1
    await _scan(ha, store, avviso, now=_ORA + timedelta(minutes=30))
    await _scan(ha, store, grave, now=_ORA + timedelta(minutes=60))
    await _scan(ha, store, avviso, now=_ORA + timedelta(minutes=90))
    await _scan(ha, store, grave, now=_ORA + timedelta(minutes=120))
    assert len(ha.chiamate) == 1
    store.close()


@pytest.mark.asyncio
async def test_riapertura_dentro_il_silenzio_non_ri_notifica(tmp_path):
    """Un'entita' intermittente che rientra da sola e si ripresenta subito non
    deve produrre una seconda notifica."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    await _scan(ha, store, _FakeSupervisor(addons=[]),
                now=_ORA + timedelta(minutes=30))
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")),
                now=_ORA + timedelta(minutes=60))
    assert len(ha.chiamate) == 1
    store.close()


@pytest.mark.asyncio
async def test_la_memoria_sopravvive_al_riavvio_dell_addon(tmp_path):
    """L'add-on riparte spesso (aggiornamenti, riavvii di Home Assistant): se
    la memoria vivesse in RAM il silenzio non varrebbe nulla."""
    percorso = str(tmp_path / "a.db")
    ha = _FakeHA()
    store = AdvisoryStore(percorso)
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    await _scan(ha, store, _FakeSupervisor(addons=[]),
                now=_ORA + timedelta(minutes=30))
    store.close()

    store2 = AdvisoryStore(percorso)
    await _scan(ha, store2, _FakeSupervisor(addons=_addon("error")),
                now=_ORA + timedelta(minutes=60))
    assert len(ha.chiamate) == 1
    store2.close()


@pytest.mark.asyncio
async def test_il_silenzio_non_copre_un_problema_diverso(tmp_path):
    """Il rischio peggiore del periodo di silenzio: tacere un problema NUOVO
    perche' un altro ha appena notificato."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    assert len(ha.chiamate) == 1
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error"),
                                           host_info={"disk_total": 100, "disk_free": 5}),
                now=_ORA + timedelta(minutes=30))
    assert len(ha.chiamate) == 2
    assert "Spazio su disco" in ha.chiamate[-1][2]["message"]
    store.close()


@pytest.mark.asyncio
async def test_memoria_illeggibile_notifica_comunque(tmp_path):
    """Fail-open: se la memoria non si puo' leggere si avvisa. Meglio una
    notifica di troppo che un guasto taciuto per sempre."""
    class _StoreCieco(AdvisoryStore):
        def notificati_dopo(self, refs, ts_min):
            raise RuntimeError("archivio illeggibile")

    ha = _FakeHA()
    store = _StoreCieco(str(tmp_path / "a.db"))
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    assert len(ha.chiamate) == 1
    store.close()


@pytest.mark.asyncio
async def test_memoria_non_scrivibile_non_fa_fallire_la_scansione(tmp_path):
    """Se l'annotazione fallisce la notifica e' comunque partita e la
    scansione deve concludersi normalmente."""
    class _StoreMuto(AdvisoryStore):
        def registra_notifica(self, source_ref, *, now=None):
            raise RuntimeError("archivio non scrivibile")

    ha = _FakeHA()
    store = _StoreMuto(str(tmp_path / "a.db"))
    res = await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    assert res["inserted"] == 1
    assert len(ha.chiamate) == 1
    store.close()


# ── FIX 2: il tetto deve tagliare i meno importanti ───────────────────────

@pytest.mark.asyncio
async def test_il_tetto_lascia_passare_i_controlli_piu_importanti(tmp_path):
    """Dopo un riavvio di Home Assistant decine di automazioni risultano non
    disponibili. Il controllo sulle automazioni gira prima di quelli su add-on
    e disco: prendere le prime cinque voci significherebbe cinque automazioni e
    il disco quasi pieno silenziato dentro il riepilogo."""
    ha = _FakeHA(automazioni=_automazione_ko(10))
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await _scan(ha, store, _FakeSupervisor(
        addons=_addon("error"), host_info={"disk_total": 100, "disk_free": 5}))
    assert res["inserted"] == 12
    assert len(ha.chiamate) == MAX_NOTIFICHE_PER_SCANSIONE + 1

    individuali = [c[2]["message"] for c in ha.chiamate[:-1]]
    assert any("Spazio su disco" in m for m in individuali)
    assert any("Add-on in errore" in m for m in individuali)
    # e le automazioni non spariscono del tutto: riempiono i posti rimasti
    assert sum(1 for m in individuali if "Automazione" in m) == 3
    store.close()


@pytest.mark.asyncio
async def test_il_riepilogo_dice_di_che_tipo_sono_i_restanti(tmp_path):
    """Un conteggio nudo non aiuta a decidere se aprire l'app."""
    ha = _FakeHA(automazioni=_automazione_ko(10))
    store = AdvisoryStore(str(tmp_path / "a.db"))
    await _scan(ha, store, _FakeSupervisor(
        addons=_addon("error"), host_info={"disk_total": 100, "disk_free": 5}))
    riepilogo = ha.chiamate[-1][2]["message"]
    assert "7" in riepilogo
    assert "automazioni" in riepilogo
    store.close()


def test_ogni_controllo_ha_priorita_ed_etichetta():
    """Un controllo aggiunto in futuro senza priorita' finirebbe in fondo alla
    coda del tetto, e senza etichetta sparirebbe dal dettaglio del riepilogo."""
    assert CHECK_IDS <= set(PRIORITA_CONTROLLO)
    assert CHECK_IDS <= set(ETICHETTE_CONTROLLO)


@pytest.mark.asyncio
async def test_riepilogo_con_gli_accenti_veri(tmp_path):
    """FIX 3: la convenzione senza accenti vale per commenti e codice, non per
    il testo che l'utente legge."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    entita = {f"lock.porta_{i}": "green"
              for i in range(MAX_NOTIFICHE_PER_SCANSIONE + 1)}
    await run_health_scan(
        ha_client=ha, entity_cache=_FakeCache(), tiers={}, entity_tiers=entita,
        store=store, now=_ORA, supervisor_client=None,
        notify_config=_NOTIFY_CONFIG)
    riepilogo = ha.chiamate[-1][2]["message"]
    assert riepilogo.startswith("C'è ")
    assert "C'e'" not in riepilogo
    store.close()


# ── FIX 4: un invio rifiutato deve lasciare traccia ───────────────────────

@pytest.mark.asyncio
async def test_canale_mal_configurato_finisce_nei_log(tmp_path, caplog):
    """`send_notification` ritorna False senza sollevare quando il servizio di
    notifica e' scritto male: senza un avviso, l'utente non riceve nulla e la
    scansione non lascia alcuna traccia del perche'."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    with caplog.at_level(logging.WARNING):
        await run_health_scan(
            ha_client=ha, entity_cache=_FakeCache(), tiers={}, entity_tiers={},
            store=store, now=_ORA,
            supervisor_client=_FakeSupervisor(addons=_addon("error")),
            notify_config={"ha_notify_service": "servizio_senza_dominio"})
    assert ha.chiamate == []
    messaggi = [r.getMessage() for r in caplog.records
                if r.levelno >= logging.WARNING and "health_scan" in r.getMessage()]
    assert any("addon_down:core_samba" in m for m in messaggi)
    store.close()


@pytest.mark.asyncio
async def test_invio_rifiutato_non_consuma_il_silenzio(tmp_path):
    """Un invio mai arrivato non deve valere come "gia' avvisato": alla
    prossima occasione il problema deve poter notificare."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    await run_health_scan(
        ha_client=ha, entity_cache=_FakeCache(), tiers={}, entity_tiers={},
        store=store, now=_ORA,
        supervisor_client=_FakeSupervisor(addons=_addon("error")),
        notify_config={"ha_notify_service": "servizio_senza_dominio"})
    assert store.notificati_dopo(["addon_down:core_samba"],
                                 "2026-07-01T00:00:00Z") == set()
    store.close()


# ── FIX 5a: le segnalazioni messe a tacere restano mute ───────────────────

@pytest.mark.asyncio
async def test_segnalazione_messa_a_tacere_non_notifica_mai_piu(tmp_path):
    """Una delle tre proprieta' cardine del task: se l'utente ha messo a tacere
    una segnalazione, nemmeno una riapertura deve tornare a disturbarlo."""
    ha = _FakeHA()
    store = AdvisoryStore(str(tmp_path / "a.db"))
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")))
    assert len(ha.chiamate) == 1

    identificativo = store.list()[0]["id"]
    assert store.set_status(identificativo, "dismissed") is True

    # rientra e si ripresenta ben oltre il periodo di silenzio: senza il
    # "dismissed" questo sarebbe esattamente lo scenario di riapertura che
    # notifica (vedi test_segnalazione_riaperta_notifica_di_nuovo).
    await _scan(ha, store, _FakeSupervisor(addons=[]),
                now=_DOPO_IL_SILENZIO)
    await _scan(ha, store, _FakeSupervisor(addons=_addon("error")),
                now=_DOPO_IL_SILENZIO + timedelta(minutes=30))
    assert len(ha.chiamate) == 1
    assert store.list()[0]["status"] == "dismissed"
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
