from datetime import datetime, timezone, timedelta
from hiris.app.brain import health_checks as hc


def test_entity_unavailable_flags_old_only():
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    states = [
        {"entity_id": "sensor.old", "state": "unavailable",
         "last_changed": "2026-07-20T00:00:00+00:00", "attributes": {"friendly_name": "Vecchio"}},
        {"entity_id": "sensor.recent", "state": "unavailable",
         "last_changed": "2026-07-27T23:00:00+00:00", "attributes": {}},
        {"entity_id": "sensor.ok", "state": "22.5",
         "last_changed": "2026-07-01T00:00:00+00:00", "attributes": {}},
    ]
    out = hc.check_entity_unavailable(states, now=now, days=2)
    refs = {o["source_ref"] for o in out}
    assert refs == {"entity_unavailable:sensor.old"}
    assert out[0]["fix_kind"] == "manual" and out[0]["severity"] == "warn"


def test_entita_non_disponibili_e_la_fonte_del_fatto():
    """La lista di chi non risponde ADESSO nasce dagli stati veri di HA.

    `since` viene da `last_changed`, non dall'istante in cui HIRIS se n'e'
    accorto: la durata dell'assenza e' quella di Home Assistant, uguale per
    chiunque la legga.
    """
    states = [
        {"entity_id": "sensor.giu", "state": "unavailable",
         "last_changed": "2026-07-20T00:00:00+00:00",
         "attributes": {"friendly_name": "Giu"}},
        {"entity_id": "light.ignota", "state": "unknown",
         "last_updated": "2026-07-27T23:00:00+00:00", "attributes": {}},
        {"entity_id": "sensor.ok", "state": "22.5",
         "last_changed": "2026-07-01T00:00:00+00:00", "attributes": {}},
    ]
    voci = hc.entita_non_disponibili(states)
    assert [v["entity_id"] for v in voci] == ["sensor.giu", "light.ignota"]
    assert voci[0] == {
        "entity_id": "sensor.giu", "domain": "sensor",
        "since": "2026-07-20T00:00:00Z", "state": "unavailable", "name": "Giu",
    }
    # Senza nome amichevole si ripiega sull'identificativo.
    assert voci[1]["name"] == "light.ignota"
    assert voci[1]["domain"] == "light"


def test_segnalazione_e_un_sottoinsieme_di_chi_non_risponde_adesso():
    """Le due letture non possono contraddirsi sulla stessa entita'.

    La segnalazione del Brain e' un FILTRO per durata sopra l'unica lista di
    chi non risponde adesso, non un secondo calcolo: cio' che segnala e'
    sempre anche nello snapshot istantaneo.
    """
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    states = [
        {"entity_id": "sensor.old", "state": "unavailable",
         "last_changed": "2026-07-20T00:00:00+00:00",
         "attributes": {"friendly_name": "Vecchio"}},
        {"entity_id": "sensor.recent", "state": "unavailable",
         "last_changed": "2026-07-27T23:00:00+00:00", "attributes": {}},
    ]
    adesso = {v["entity_id"] for v in hc.entita_non_disponibili(states)}
    segnalate = {o["evidence"]["entity_id"]
                 for o in hc.check_entity_unavailable(states, now=now, days=2)}
    assert segnalate <= adesso
    assert segnalate == {"sensor.old"}
    assert adesso == {"sensor.old", "sensor.recent"}


def test_senza_istante_resta_nell_elenco_ma_non_si_segnala():
    """HA puo' non portare un istante leggibile: l'entita' non risponde lo
    stesso (resta nello snapshot), ma da quanto non si sa, quindi il Brain non
    puo' affermare che manchi da giorni."""
    states = [{"entity_id": "sensor.senza_ts", "state": "unavailable",
               "attributes": {}}]
    voci = hc.entita_non_disponibili(states)
    assert len(voci) == 1 and voci[0]["since"] is None
    assert hc.check_entity_unavailable(
        states, now=datetime(2026, 7, 28, tzinfo=timezone.utc), days=2) == []


def test_titolo_e_evidenza_dichiarano_la_soglia_e_l_istante_normalizzato():
    """Il titolo dice da quanto, cosi' chi lo legge accanto allo snapshot
    istantaneo capisce perche' le due liste hanno lunghezze diverse."""
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    states = [{"entity_id": "sensor.old", "state": "unavailable",
               "last_changed": "2026-07-20T00:00:00+00:00",
               "attributes": {"friendly_name": "Vecchio"}}]
    out = hc.check_entity_unavailable(states, now=now, days=2)
    assert out[0]["title"] == "Vecchio non disponibile da più di 2 giorni"
    assert out[0]["evidence"]["since"] == "2026-07-20T00:00:00Z"
    uno = hc.check_entity_unavailable(states, now=now, days=1)
    assert uno[0]["title"] == "Vecchio non disponibile da più di un giorno"


def test_soglia_batteria_unica_fra_brain_e_sentinella():
    """Una sola soglia predefinita di batteria scarica in tutto il prodotto.

    Il controllo del Brain (sempre attivo, su tutte le batterie) e il
    rilevatore della Sentinella (opt-in per entita') restano due meccanismi
    distinti, ma non possono partire da due numeri diversi: a 12% l'utente si
    sentirebbe dire "scarica" da uno e nulla dall'altro. Il valore in vigore
    per la Sentinella resta modificabile dall'utente; qui si blocca solo il
    punto di partenza.
    """
    from hiris.app.watcher.detectors import detect_low_battery
    from hiris.app.watcher.policy import DEFAULT_POLICY

    assert DEFAULT_POLICY["detectors"]["battery"]["min_pct"] == hc.SOGLIA_BATTERIA_PCT
    sotto = str(hc.SOGLIA_BATTERIA_PCT - 1)
    pari = str(hc.SOGLIA_BATTERIA_PCT)
    assert detect_low_battery("sensor.b", None, {"state": sotto}, {}, 1.0) is not None
    assert detect_low_battery("sensor.b", None, {"state": pari}, {}, 1.0) is None


def test_low_battery():
    states = [
        {"id": "sensor.door_bat", "state": "8", "name": "Porta", "unit": "%", "device_class": "battery"},
        {"id": "sensor.full", "state": "90", "name": "Pieno", "unit": "%", "device_class": "battery"},
        {"id": "sensor.temp", "state": "5", "name": "Temp", "unit": "C", "device_class": "temperature"},
    ]
    out = hc.check_low_battery(states, threshold=15)
    assert {o["source_ref"] for o in out} == {"low_battery:sensor.door_bat"}


def test_low_battery_evidenza_porta_nome_e_percentuale():
    """L'evidenza contiene il nome amichevole e la carica residua come DATI.

    Chi rilegge la segnalazione (il briefing quotidiano) non deve ricavare il
    nome spellando all'indietro il titolo, che e' testo per l'utente e un
    giorno puo' essere riscritto o tradotto.
    """
    out = hc.check_low_battery(
        [{"id": "sensor.door_bat", "state": "8", "name": "Porta ingresso",
          "unit": "%", "device_class": "battery"}],
        threshold=15,
    )
    assert len(out) == 1
    assert out[0]["evidence"] == {
        "entity_id": "sensor.door_bat", "name": "Porta ingresso", "pct": 8.0,
    }


def test_low_battery_evidenza_ripiega_sull_identificativo_senza_nome():
    """Senza nome amichevole l'evidenza porta l'identificativo, cosi' che chi
    la rilegge abbia sempre qualcosa da citare."""
    out = hc.check_low_battery(
        [{"id": "sensor.senza_nome", "state": "3", "name": "", "unit": "%",
          "device_class": "battery"}],
        threshold=15,
    )
    assert len(out) == 1
    assert out[0]["evidence"]["name"] == "sensor.senza_nome"


def test_automation_broken_severity():
    autos = [
        {"entity_id": "automation.a", "state": "off", "attributes": {"friendly_name": "A"}},
        {"entity_id": "automation.b", "state": "unavailable", "attributes": {}},
        {"entity_id": "automation.c", "state": "on", "attributes": {}},
    ]
    out = {o["source_ref"]: o for o in hc.check_automation_broken(autos)}
    assert set(out) == {"automation_broken:automation.a", "automation_broken:automation.b"}
    assert out["automation_broken:automation.a"]["severity"] == "warn"
    assert out["automation_broken:automation.b"]["severity"] == "high"


def test_dangerous_domain_green_domain_and_entity():
    tiers = {"lock": "green", "cover": "yellow", "light": "green"}
    entity_tiers = {"alarm_control_panel.home": "green", "light.k": "green"}
    out = {o["source_ref"] for o in hc.check_dangerous_domain_green(tiers, entity_tiers)}
    assert out == {
        "dangerous_domain_green:domain:lock",
        "dangerous_domain_green:entity:alarm_control_panel.home",
    }


def test_entity_no_area_aggregates():
    out = hc.check_entity_no_area(["light.a", "light.b"])
    assert len(out) == 1
    assert out[0]["severity"] == "info"
    assert out[0]["evidence"]["count"] == 2
    assert out[0]["source_ref"] == "entity_no_area:all"
    assert hc.check_entity_no_area([]) == []


# --- Controlli di sistema (Supervisor) -------------------------------------

def test_addon_down_stato_e_severita():
    addons = [
        {"slug": "core_mosquitto", "name": "Mosquitto", "state": "started"},
        {"slug": "a0d7b954_nodered", "name": "Node-RED", "state": "error"},
        {"slug": "core_samba", "name": "Samba", "state": "stopped"},
        {"slug": "core_ssh", "name": "SSH", "state": "unknown"},
        {"slug": "core_zwave", "name": "Z-Wave", "state": "startup"},
    ]
    out = {o["source_ref"]: o for o in hc.check_addon_down(addons)}
    assert set(out) == {"addon_down:a0d7b954_nodered", "addon_down:core_samba"}
    rotto = out["addon_down:a0d7b954_nodered"]
    fermo = out["addon_down:core_samba"]
    assert rotto["severity"] == "high"
    assert fermo["severity"] == "warn"
    assert rotto["check_id"] == "addon_down" and rotto["fix_kind"] == "manual"
    assert fermo["evidence"] == {"slug": "core_samba", "state": "stopped"}
    assert "Samba" in fermo["title"]


def test_addon_down_idempotente_e_input_malformato():
    addons = [{"slug": "core_samba", "name": "Samba", "state": "stopped"}]
    primo = hc.check_addon_down(addons)
    secondo = hc.check_addon_down(addons)
    assert [o["source_ref"] for o in primo] == [o["source_ref"] for o in secondo]
    assert hc.check_addon_down(None) == []
    assert hc.check_addon_down([]) == []
    # Voci non-dict, senza slug o senza stato non devono sollevare
    assert hc.check_addon_down(["non un dict", {}, {"state": "error"},
                                {"slug": "x"}, None]) == []


def test_disk_space_soglie():
    alto = hc.check_disk_space({"disk_total": 100, "disk_used": 95, "disk_free": 5})
    assert len(alto) == 1
    assert alto[0]["severity"] == "high"
    assert alto[0]["check_id"] == "disk_space"
    assert alto[0]["source_ref"] == "disk_space:host"
    assert alto[0]["evidence"]["free_pct"] == 5.0
    assert alto[0]["fix_kind"] == "manual"

    avviso = hc.check_disk_space({"disk_total": 200, "disk_used": 170, "disk_free": 30})
    assert len(avviso) == 1 and avviso[0]["severity"] == "warn"
    assert avviso[0]["source_ref"] == "disk_space:host"

    # Esattamente sulle soglie: "sotto" e' stretto
    assert hc.check_disk_space({"disk_total": 100, "disk_free": 20}) == []
    assert hc.check_disk_space({"disk_total": 100, "disk_free": 10})[0]["severity"] == "warn"
    # Ampiamente sopra: nessuna segnalazione
    assert hc.check_disk_space({"disk_total": 100, "disk_used": 40, "disk_free": 60}) == []


def test_disk_space_soglia_su_valore_grezzo_non_arrotondato():
    """Fix wave 1 (FIX 2): la soglia va confrontata sul rapporto grezzo, non su
    quello gia' arrotondato a un decimale per la UI. Con 9.96% libero il vecchio
    codice arrotondava a 10.0 PRIMA del confronto e degradava un caso grave
    (sotto il 10%) ad avviso: proprio il caso peggiore, perche' una segnalazione
    che dovrebbe essere notificabile smette di esserlo."""
    out = hc.check_disk_space({"disk_total": 10000, "disk_free": 996})
    assert len(out) == 1
    assert out[0]["severity"] == "high"
    # L'arrotondamento resta per titolo ed evidenza mostrati all'utente.
    assert out[0]["evidence"]["free_pct"] == 10.0
    assert "10.0%" in out[0]["title"]


def test_disk_space_input_malformato():
    assert hc.check_disk_space(None) == []
    assert hc.check_disk_space({}) == []
    assert hc.check_disk_space("non un dict") == []
    assert hc.check_disk_space({"disk_total": 0, "disk_free": 0}) == []
    assert hc.check_disk_space({"disk_total": "x", "disk_free": "y"}) == []
    assert hc.check_disk_space({"disk_total": 100, "disk_free": -1}) == []
    # disk_free assente si ricava da totale - usato
    ricavato = hc.check_disk_space({"disk_total": 100, "disk_used": 96})
    assert len(ricavato) == 1 and ricavato[0]["severity"] == "high"


def test_updates_available_voce_unica_aggregata():
    updates = [{"name": f"Add-on {i}", "update_type": "addon", "version_latest": "1.0"}
               for i in range(12)]
    out = hc.check_updates_available(updates)
    assert len(out) == 1
    voce = out[0]
    assert voce["severity"] == "info"
    assert voce["check_id"] == "updates_available"
    assert voce["source_ref"] == "updates_available:all"
    assert voce["evidence"]["count"] == 12
    assert len(voce["evidence"]["items"]) == hc.MAX_UPDATES_EVIDENZA
    assert hc.MAX_UPDATES_EVIDENZA < 12
    # Fix wave 1 (FIX 4a): il source_ref e' fisso ("updates_available:all"),
    # non deve dipendere dal conteggio -- altrimenti ogni variazione nel
    # numero di aggiornamenti disponibili aprirebbe una nuova segnalazione
    # invece di riconciliare quella esistente. E' la stessa proprieta' gia'
    # pinnata per disk_space al variare della percentuale.
    assert voce["source_ref"] == "updates_available:all"


def test_updates_available_input_vuoto_o_malformato():
    assert hc.check_updates_available(None) == []
    assert hc.check_updates_available([]) == []
    assert hc.check_updates_available(["x", None]) == []
    out = hc.check_updates_available(["x", {"name": "Core", "update_type": "core"}])
    assert len(out) == 1 and out[0]["evidence"]["count"] == 1
    assert out[0]["title"] == "1 aggiornamento disponibile"
    # Stesso source_ref con 1 solo aggiornamento e con 12 (vedi test sopra):
    # la deduplica e' stabile al variare del conteggio.
    assert out[0]["source_ref"] == "updates_available:all"
