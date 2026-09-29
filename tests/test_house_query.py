"""La porta che interroga la casa (spec §2): filtri, esclusi dichiarati,
profondita' decisa dallo strumento, paginazione."""
import json

import pytest

from hiris.app.home_space import house_query as hq
from tests.test_briefing import _casa_grande  # 20 aree x 15 entita'

T0 = 1_790_700_000.0


def _luce(i, a, **k):
    """Un'entita' nella forma di `HomeSpace.read()` (la stessa di
    `test_briefing._CASA`, che `topology.hierarchy` accetta), piu' i campi
    del registro che la porta legge: `piattaforma`, `categoria`, `nascosta`."""
    return {"id": i, "nome": "", "area_id": a, "dispositivo_id": None,
            "piattaforma": "ave", "categoria": None, "classe": None,
            "unita": None, "disabilitata": 0, "nascosta": 0, **k}


def _casa():
    """Una casa piccola ma con tutti i casi veri del 29/09: due luci di
    servizio NASCOSTE e senza area, accese; entita' di servizio; una
    disabilitata; una persona fuori casa."""
    return {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
        "aree": [{"id": "soggiorno", "nome": "Soggiorno", "piano_id": "terra",
                  "alias": [], "etichette": []}],
        "dispositivi": [],
        "entita": [
            _luce("light.soggiorno_1", "soggiorno"),
            _luce("light.soggiorno_2", "soggiorno"),
            _luce("light.servizio_sala", None, nascosta=1),
            _luce("light.servizio_cancello", None, nascosta=1),
            _luce("switch.echo_dnd", "soggiorno", categoria="config"),
            _luce("light.vecchia", "soggiorno", disabilitata=1),
            {**_luce("person.marta", None), "piattaforma": "person"},
        ],
        "etichette": [], "categorie": [], "integrazioni": [],
    }


ATTRIBUTI = {"person.marta": {"values": {"latitude": 45.0, "source": "x"}}}


def _specchio(stati):
    nomi = {k: k.split(".")[1].replace("_", " ") for k in stati}
    return (dict(stati), nomi, {}, {}, {k: "2026-09-29T07:11:00+00:00" for k in stati},
            ATTRIBUTI)


STATI = {"light.soggiorno_1": "on", "light.soggiorno_2": "off",
         "light.servizio_sala": "on", "light.servizio_cancello": "on",
         "switch.echo_dnd": "unavailable", "person.marta": "Lavoro"}


def _dettaglio(kind, reference):
    """Il dettaglio completo come lo da' `queries.view`: porta lo stato VERO
    e gli attributi dello specchio, non gia' filtrati -- il filtro e' della
    porta, e la prova deve poterlo vedere mancare."""
    voce = {"esiste": True, "tipo": kind, "id": reference, "completo": True,
            "stato": STATI.get(reference)}
    if reference in ATTRIBUTI:
        voce["attributi"] = ATTRIBUTI[reference]
    return voce


def _chiedi(**argomenti):
    filtri = hq.parse_filters(argomenti)
    assert not isinstance(filtri, dict), filtri
    return hq.query_house(_casa(), [], _specchio(STATI), filtri,
                          detail=_dettaglio, now=T0)


def test_luci_accese_con_le_accese_nascoste_non_e_uno_zero_muto():
    """Il caso della batteria del 29/09 (#4).

    Mutazione ESEGUITA: non contare le nascoste in `escluse` -- rossa."""
    r = _chiedi(tipo="light", stato="on")
    assert [v["id"] for v in r["voci"]] == ["light.soggiorno_1"]
    assert r["escluse"]["nascoste"] == 2
    assert r["escluse"]["disabilitate"] == 0


def test_includi_nascoste_le_riporta_e_dice_che_sono_nascoste():
    r = _chiedi(tipo="light", stato="on", includi_nascoste=True)
    assert r["trovate"] == 3
    nascoste = [v for v in r["voci"] if v.get("nascosta")]
    assert {v["id"] for v in nascoste} == {"light.servizio_sala",
                                           "light.servizio_cancello"}
    assert all(v["area"] is None for v in nascoste)


def test_le_disabilitate_sono_sempre_fuori_e_contate():
    """Mutazione ESEGUITA: lasciarle in `voci` -- rossa."""
    r = _chiedi(tipo="light", includi_nascoste=True)
    assert "light.vecchia" not in {v["id"] for v in r["voci"]}
    assert r["escluse"]["disabilitate"] == 1


def test_le_entita_di_servizio_si_chiedono_esplicitamente():
    assert _chiedi(stato="unavailable")["escluse"]["servizio"] == 1
    r = _chiedi(stato="unavailable", includi_servizio=True)
    assert [v["id"] for v in r["voci"]] == ["switch.echo_dnd"]


def test_area_e_filtri_si_combinano():
    r = _chiedi(area="soggiorno", tipo="light")
    assert {v["id"] for v in r["voci"]} == {"light.soggiorno_1",
                                            "light.soggiorno_2"}


def test_area_mancante_e_un_valore_valido():
    """Il valore «senza area» del filtro `area`."""
    r = _chiedi(area="senza area", includi_nascoste=True, tipo="light")
    assert r["trovate"] == 2


def test_la_profondita_la_decide_lo_strumento():
    """1 voce: completa (il dettaglio del dispatcher); 2-10: media; oltre: corta.

    Mutazione ESEGUITA: soglia media a 9 -- rossa sul caso da 10."""
    uno = _chiedi(riferimento="light.soggiorno_1")
    assert uno["profondita"] == "completa" and uno["voci"][0]["completo"]
    due = _chiedi(tipo="light")
    assert due["profondita"] == "media"
    assert "attributi" in due["voci"][0] or "ultimo_cambio" in due["voci"][0]


def test_dieci_voci_sono_ancora_medie_undici_sono_corte():
    casa = _casa()
    casa["entita"] = [{"id": f"sensor.s{i}", "nome": "", "area_id": "soggiorno",
                       "dispositivo_id": None, "piattaforma": "x",
                       "categoria": None, "classe": None, "unita": None,
                       "disabilitata": 0, "nascosta": 0} for i in range(11)]
    stati = {f"sensor.s{i}": str(i) for i in range(11)}
    f10 = hq.parse_filters({"limite": 50, "sotto": 10})
    f11 = hq.parse_filters({"tipo": "sensor"})
    r10 = hq.query_house(casa, [], _specchio(stati), f10, detail=_dettaglio, now=T0)
    r11 = hq.query_house(casa, [], _specchio(stati), f11, detail=_dettaglio, now=T0)
    assert r10["trovate"] == 10 and r10["profondita"] == "media"
    assert r11["trovate"] == 11 and r11["profondita"] == "corta"
    assert set(r11["voci"][0]) <= {"id", "nome", "area", "stato",
                                   "ultimo_cambio", "nascosta"}


def test_oltre_il_limite_si_dichiara_e_si_scorre_con_salta():
    """Mutazione ESEGUITA: non scrivere `oltre` -- rossa."""
    casa = _casa()
    casa["entita"] = [{"id": f"sensor.s{i:03}", "nome": "", "area_id": None,
                       "dispositivo_id": None, "piattaforma": "x",
                       "categoria": None, "classe": None, "unita": None,
                       "disabilitata": 0, "nascosta": 0} for i in range(120)]
    stati = {f"sensor.s{i:03}": "1" for i in range(120)}
    primo = hq.query_house(casa, [], _specchio(stati),
                           hq.parse_filters({"tipo": "sensor"}),
                           detail=_dettaglio, now=T0)
    assert len(primo["voci"]) == hq.ROWS_MAX and primo["oltre"]["restano"] == 70
    assert primo["oltre"]["salta"] == 50
    terzo = hq.query_house(casa, [], _specchio(stati),
                           hq.parse_filters({"tipo": "sensor", "salta": 100}),
                           detail=_dettaglio, now=T0)
    assert len(terzo["voci"]) == 20 and "oltre" not in terzo


def test_limite_zero_restituisce_solo_i_conteggi():
    """Con UNA sola voce trovata (la luce accesa visibile): `limite=0` vince
    sulla profondita' completa -- nessuna voce, solo i conti.

    Mutazione ESEGUITA: togliere `and f.limit > 0` dalla guardia della
    profondita' completa -- rossa."""
    r = _chiedi(tipo="light", stato="on", limite=0)
    assert r["voci"] == [] and r["trovate"] == 1 and r["escluse"]["nascoste"] == 2


def test_la_persona_fuori_casa_esce_senza_zona_e_senza_coordinate():
    """Review Focus 3. Mutazione ESEGUITA: non passare da `redact_row` -- rossa."""
    r = _chiedi(tipo="person")
    voce = r["voci"][0]
    assert voce["stato"] == "not_home"
    assert "latitude" not in str(voce)


def test_nessun_riepilogo_per_stato():
    """Decisione 5: le voci, non i conti."""
    r = _chiedi(tipo="light", includi_nascoste=True)
    assert set(r) <= {"trovate", "escluse", "profondita", "voci", "oltre"}


def test_solo_il_nome_cerca_in_tutti_i_generi():
    """Review Focus 1: «soggiorno» e' un'AREA, non un'entita'."""
    r = _chiedi(nome="soggiorno")
    assert any(v.get("genere") == "area" for v in r["voci"]) or \
        r["voci"][0].get("tipo") == "area"


def test_le_automazioni_ordinate_dalla_piu_ferma():
    """#31 della batteria. Mutazione ESEGUITA: ordinare per nome -- rossa."""
    comportamento = [
        {"id": "automation.nuova", "tipo": "automazione", "nome": "Nuova"},
        {"id": "automation.vecchia", "tipo": "automazione", "nome": "Vecchia"}]
    specchio = ({"automation.nuova": "on", "automation.vecchia": "on"}, {}, {},
                {}, {}, {"automation.nuova": {"values": {
                    "last_triggered": "2026-09-28T10:00:00+00:00"}},
                    "automation.vecchia": {"values": {
                        "last_triggered": "2026-02-17T10:00:00+00:00"}}})
    r = hq.query_house(_casa(), comportamento, specchio,
                       hq.parse_filters({"genere": "automazione",
                                         "ordina": "ultimo_cambio"}),
                       detail=_dettaglio, now=T0)
    assert [v["id"] for v in r["voci"]] == ["automation.vecchia",
                                            "automation.nuova"]
    assert r["voci"][0]["ultima_esecuzione"].startswith("2026-02-17")


def test_il_filtro_fermo_legge_l_ultima_esecuzione_delle_automazioni():
    """Il filtro `fermo_da` sulle automazioni."""
    comportamento = [{"id": "automation.vecchia", "tipo": "automazione",
                      "nome": "Vecchia"}]
    specchio = ({"automation.vecchia": "on"}, {}, {}, {}, {},
                {"automation.vecchia": {"values": {
                    "last_triggered": "2026-02-17T10:00:00+00:00"}}})
    r = hq.query_house(_casa(), comportamento, specchio,
                       hq.parse_filters({"genere": "automazione",
                                         "fermo_da": "30d"}),
                       detail=_dettaglio, now=T0)
    assert r["trovate"] == 1


@pytest.mark.parametrize("argomenti", [{"limite": 51}, {"fermo_da": "tre giorni"},
                                       {"genere": "piano"}, {"sopra": "x"}])
def test_un_filtro_sbagliato_si_dice_non_si_indovina(argomenti):
    assert "errore" in hq.parse_filters(argomenti)


def test_su_una_casa_grande_nessuna_risposta_supera_la_soglia_del_ponte():
    """Spec §10, su 300 entita'. 25.000 token del ponte ≈ 60.000 caratteri a
    2,5 car/token: si tiene la meta' di margine.

    Mutazione ESEGUITA: `ROWS_MAX = 500` -- rossa."""
    casa = _casa_grande()
    stati = {e["id"]: "on" for e in casa["entita"]}
    for argomenti in ({}, {"stato": "on"}, {"tipo": "light"}, {"salta": 50}):
        r = hq.query_house(casa, [], _specchio(stati),
                           hq.parse_filters(argomenti), detail=_dettaglio, now=T0)
        assert len(json.dumps(r, ensure_ascii=False)) < 30_000, argomenti
