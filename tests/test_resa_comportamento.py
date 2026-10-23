"""Un'automazione o uno script si rende in un posto solo (Tappa 9, F4; C-42
e «trovato 1» della Tappa 4).

Fino al 12/10/2026 `queries._view_behavior` (la scheda di `view`) e
`house_query._behavior_row` (le voci di `search`) componevano la stessa
automazione ciascuna per conto suo: la scheda senza `stato`, `attiva` ne'
`ultima_esecuzione`, e con `nome: null` dove le voci scrivevano il nome vivo
con l'id come ripiego.
"""
from zoneinfo import ZoneInfo

from hiris.app.home_space import house_query as hq
from hiris.app.home_space.house import House
from hiris.app.home_space.queries import view
from hiris.app.home_space.render import render_behavior
from hiris.app.home_space.topology import Mirror

T0 = 1_790_700_000.0
#: Un fuso della casa diverso da UTC (N117-1): l'ora che la scheda e le voci
#: dicono deve essere la stessa.
_FUSO = "Europe/Rome"
_ULTIMA = "2026-09-28T06:30:00+00:00"

_CASA = {"piani": [], "aree": [], "dispositivi": [], "entita": [],
         "etichette": [], "categorie": [], "integrazioni": []}


def _comportamento():
    """Due automazioni: una senza nome (l'id e' il ripiego), spenta; e uno
    script. `attiva` la scrive `HomeSpace.behavior` dallo specchio."""
    return [{"id": "automation.senza_nome", "tipo": "automazione", "nome": None,
             "corpo": {"trigger": []}, "attiva": False},
            {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
             "corpo": {"trigger": []}, "attiva": True}]


def _specchio():
    valori = {"last_triggered": _ULTIMA, "mode": "single", "current": 0}
    return Mirror({"automation.senza_nome": "off", "automation.sveglia": "on"},
                  attributes={"automation.senza_nome": {"values": dict(valori)},
                              "automation.sveglia": {"values": dict(valori)}})


def _scheda(ident):
    return view(House(_CASA, _specchio()), _comportamento(), [], "automazione", ident,
                zone=ZoneInfo(_FUSO))


def _voci_medie():
    filtri = hq.parse_filters({"genere": "automazione"})
    return hq.query_house(House(_CASA, _specchio()), _comportamento(), filtri,
                          detail=lambda kind, ref: _scheda(ref), now=T0,
                          timezone=_FUSO)["voci"]


def test_la_stessa_automazione_da_view_e_da_search_ha_lo_stesso_nome_e_gli_stessi_campi():
    """La scheda (`view`, completa) contiene la voce media di `search`, con
    gli stessi valori: il nome vivo con l'id come ripiego, lo `stato`,
    `attiva`, `ultima_esecuzione`, `modalita`, `in_esecuzione`.

    Rossa prima della resa unica (12/10/2026: la scheda con `nome: None`).
    Mutazione ESEGUITA: `render_behavior` col nome grezzo -- rossa. Con il
    fuso della casa fuori da UTC (N117-1, giro 117), mutazione ESEGUITA:
    `view` che non passa il fuso alla scheda -- rossa su
    `ultima_esecuzione`."""
    voci = _voci_medie()
    assert voci and all(v["ultima_esecuzione"].endswith("+02:00") for v in voci), voci
    for voce in voci:
        scheda = _scheda(voce["id"])
        assert scheda["esiste"] is True
        assert {k: scheda.get(k) for k in voce} == voce, (voce, scheda)
    anonima = _scheda("automation.senza_nome")
    assert anonima["nome"] == "automation.senza_nome"
    assert anonima["attiva"] is False and anonima["stato"] == "off"


def test_le_profondita_del_comportamento_si_contengono():
    """corta ⊆ media ⊆ completa, chieste alla resa.

    Mutazione ESEGUITA: `render_behavior` senza `attiva` -- rossa."""
    casa = House(_CASA, _specchio())
    voce = _comportamento()[1]
    corta, media, completa = (set(render_behavior(casa, voce, depth))
                              for depth in ("corta", "media", "completa"))
    assert corta < media < completa
    assert {"id", "nome", "genere", "stato", "attiva", "ultima_esecuzione"} <= corta
    assert {"modalita", "in_esecuzione"} <= media - corta
    assert completa - media == {"corpo"}


def test_con_lo_specchio_illeggibile_lo_stato_manca():
    """N117-2 (giro 117): «`stato` manca se lo specchio non si e' potuto
    leggere» -- la regola delle assenze di `render_entity`. `None` direbbe
    «so che non ha stato».

    Mutazione ESEGUITA: `stato` scritto anche con lo specchio illeggibile --
    rossa."""
    casa = House(_CASA, Mirror({}, readable=False))
    for depth in ("corta", "media", "completa"):
        assert "stato" not in render_behavior(casa, _comportamento()[1], depth), depth


# --- Cosa fa un'automazione (rimedio C delle risposte sbagliate, 23/10/2026):
# la domanda 30 della batteria del 22/10 chiedeva cosa fanno le automazioni, e
# `search` ne dava solo il nome e l'ultima esecuzione.

#: Un corpo come Home Assistant lo restituisce in `raw_config`: la forma nuova
#: (`triggers`, `actions`, `trigger`, `action`) letta nel sorgente di Core al
#: tag 2026.9.4 (`components/automation/config.py`).
_CORPO_NUOVO = {
    "triggers": [{"trigger": "state", "entity_id": "binary_sensor.porta", "to": "on"},
                 {"trigger": "time", "at": "07:00:00"}],
    "actions": [{"action": "light.turn_on", "target": {"entity_id": ["light.ingresso"]}},
                {"delay": "00:05:00"}],
}

#: La forma vecchia, ancora accettata e rinominata da Home Assistant
#: (`cv.renamed`, `platform` per l'innesco, `service` per il passo).
_CORPO_VECCHIO = {
    "trigger": {"platform": "state", "entity_id": "binary_sensor.porta"},
    "action": [{"service": "light.turn_on", "entity_id": "light.ingresso"}],
}


def _voce(corpo):
    return {"id": "automation.luce", "tipo": "automazione", "nome": "Luce",
            "corpo": corpo, "attiva": True}


def test_la_voce_corta_dice_cosa_fa_dal_corpo():
    """Senza `description`, la voce porta il riassunto: inneschi e passi,
    ognuno col tipo di Home Assistant e le entita' che nomina. Le due forme
    del corpo danno lo stesso riassunto.

    Mutazioni ESEGUITE: `render_behavior` senza il riassunto -- rossa;
    `behavior_summary` che legge solo `triggers` (non `trigger`) -- rossa
    sulla forma vecchia; `_entities_of` senza il `target` -- rossa."""
    casa = House(_CASA, _specchio())
    nuovo = render_behavior(casa, _voce(_CORPO_NUOVO), "corta")["riassunto"]
    assert nuovo == {
        "inneschi": [{"tipo": "state", "entita": ["binary_sensor.porta"]}, {"tipo": "time"}],
        "passi": [{"tipo": "light.turn_on", "entita": ["light.ingresso"]}, {"tipo": "delay"}],
    }
    vecchio = render_behavior(casa, _voce(_CORPO_VECCHIO), "corta")["riassunto"]
    assert vecchio == {"inneschi": [{"tipo": "state", "entita": ["binary_sensor.porta"]}],
                       "passi": [{"tipo": "light.turn_on", "entita": ["light.ingresso"]}]}


def test_gli_inneschi_ANNIDATI_si_spianano():
    """Home Assistant accetta, fra gli inneschi, un elenco annidato
    `{"triggers": [...]}` (core 2026.9.4, `config_validation`): nel riassunto
    escono i suoi inneschi, non una riga col tipo «triggers» (R206-2, giro
    206 del revisore).

    Mutazione ESEGUITA (23/10/2026): togliere lo spianamento da
    `behavior_summary` -- rossa."""
    from hiris.app.home_space.render import behavior_summary

    corpo = {"triggers": [
        {"triggers": [{"trigger": "state", "entity_id": "binary_sensor.porta"},
                      {"trigger": "time", "at": "07:00"}]},
        {"trigger": "sun", "event": "sunset"}],
        "actions": []}
    assert behavior_summary(corpo) == {"inneschi": [
        {"tipo": "state", "entita": ["binary_sensor.porta"]}, {"tipo": "time"},
        {"tipo": "sun"}]}


def test_la_descrizione_di_home_assistant_vince_sul_riassunto():
    """Con la `description` scritta dal proprietario, la voce porta lei e non
    il riassunto: e' la sua parola, e costa meno.

    Mutazione ESEGUITA: il riassunto scritto anche con la descrizione -- rossa."""
    casa = House(_CASA, _specchio())
    voce = render_behavior(casa, _voce({**_CORPO_NUOVO, "description": " Luce all'arrivo "}),
                           "corta")
    assert voce["descrizione"] == "Luce all'arrivo"
    assert "riassunto" not in voce


def test_un_blueprint_dice_il_suo_blueprint_e_le_profondita_si_contengono():
    """Un'automazione da blueprint non ha inneschi nel corpo: dice da quale
    blueprint viene. E il riassunto sta a ogni profondita' (corta ⊆ media ⊆
    completa).

    Mutazione ESEGUITA: il riassunto tolto dalla completa -- rossa."""
    casa = House(_CASA, _specchio())
    corpo = {"use_blueprint": {"path": "homeassistant/motion_light.yaml", "input": {}}}
    corta, completa = (render_behavior(casa, _voce(corpo), d) for d in ("corta", "completa"))
    assert corta["riassunto"] == {"blueprint": "homeassistant/motion_light.yaml"}
    assert set(corta) < set(completa)
    full = set(render_behavior(casa, _voce(_CORPO_NUOVO), "completa"))
    assert {"riassunto", "corpo"} <= full
