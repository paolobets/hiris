"""La porta che interroga la casa (spec §2): filtri, esclusi dichiarati,
profondita' decisa dallo strumento, paginazione."""
import json

import pytest

from hiris.app.home_space import house_query as hq
from tests.test_briefing import _casa_grande  # 20 aree x 15 entita'

T0 = 1_790_700_000.0
#: La soglia dei cancelli del peso, in caratteri. **Il tetto vero e' sulle
#: RIGHE** (`ROWS_MAX` = 50, spec §2.3), non sui caratteri: la porta non
#: misura quanto scrive. Il limite da rispettare e' della CLI di Claude Code,
#: 25.000 token per risultato MCP (spec §1 causa 2); a 2,5 caratteri per token
#: sono ~60.000 caratteri, e questa soglia ne tiene la meta'. Non e' una
#: garanzia: un caso di prova con 50 righe ricche arriva a ~32.700 caratteri
#: (re-review, 30/09/2026) -- oltre questa soglia, ma ~13.000 token, ben sotto
#: il limite del ponte. Le case di questi cancelli stanno sotto i 30.000.
BRIDGE_CEILING_CHARS = 30_000


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
    disabilitata; una persona fuori casa. E, come nella casa vera, le
    automazioni stanno ANCHE nel registro delle entita', e i dispositivi nel
    loro registro."""
    return {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
        "aree": [{"id": "soggiorno", "nome": "Soggiorno", "piano_id": "terra",
                  "alias": [], "etichette": []}],
        "dispositivi": [{"id": "dev_lavatrice", "nome": "Lavatrice",
                         "nome_utente": None, "produttore": None, "modello": None,
                         "area_id": "soggiorno", "disabilitato": 0,
                         "etichette": []}],
        "entita": [
            _luce("light.soggiorno_1", "soggiorno"),
            _luce("light.soggiorno_2", "soggiorno"),
            _luce("light.servizio_sala", None, nascosta=1),
            _luce("light.servizio_cancello", None, nascosta=1),
            _luce("switch.echo_dnd", "soggiorno", categoria="config"),
            _luce("light.vecchia", "soggiorno", disabilitata=1),
            {**_luce("person.marta", None), "piattaforma": "person"},
            {**_luce("automation.sveglia", None), "nome": "Sveglia",
             "piattaforma": "automation"},
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


def _automazioni(*coppie):
    """(comportamento, specchio) per automazioni con la loro ultima
    esecuzione (None = mai eseguita)."""
    comportamento = [{"id": f"automation.{n}", "tipo": "automazione",
                      "nome": n.capitalize()} for n, _ in coppie]
    attributi = {f"automation.{n}": {"values": {"last_triggered": t}}
                 for n, t in coppie if t}
    stati = {f"automation.{n}": "on" for n, _ in coppie}
    return comportamento, (stati, {}, {}, {}, {}, attributi)


def _chiedi_automazioni(coppie, argomenti: dict, casa=None):
    comportamento, specchio = _automazioni(*coppie)
    return hq.query_house(casa or _casa(), comportamento, specchio,
                          hq.parse_filters(argomenti), detail=_dettaglio, now=T0)


def test_luci_accese_con_le_accese_nascoste_non_e_uno_zero_muto():
    """Il caso della batteria del 29/09 (#4).

    Mutazione ESEGUITA: non contare le nascoste in `escluse` -- rossa."""
    r = _chiedi(tipo="light", stato="on")
    assert [v["id"] for v in r["voci"]] == ["light.soggiorno_1"]
    assert r["escluse"]["nascoste"] == 2
    assert r["escluse"]["disabilitate"] == 0


def test_includi_nascoste_le_riporta_e_dice_che_sono_nascoste():
    """Mutazione ESEGUITA: non scrivere `nascosta` sulla riga -- rossa."""
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
    """Mutazione ESEGUITA: escluderle anche con `includi_servizio` -- rossa."""
    assert _chiedi(stato="unavailable")["escluse"]["servizio"] == 1
    r = _chiedi(stato="unavailable", includi_servizio=True)
    assert [v["id"] for v in r["voci"]] == ["switch.echo_dnd"]


def test_area_e_filtri_si_combinano():
    """Mutazione ESEGUITA: ignorare il filtro `area` -- rossa (le nascoste
    senza area rientrerebbero)."""
    r = _chiedi(area="soggiorno", tipo="light")
    assert {v["id"] for v in r["voci"]} == {"light.soggiorno_1",
                                            "light.soggiorno_2"}
    r = _chiedi(area="soggiorno", tipo="light", includi_nascoste=True)
    assert {v["id"] for v in r["voci"]} == {"light.soggiorno_1",
                                            "light.soggiorno_2"}


def test_area_mancante_e_un_valore_valido():
    """Il valore «senza area» del filtro `area`.

    Mutazione ESEGUITA: `_area_name` che restituisce il nome anche delle
    pseudo-aree -- rossa."""
    r = _chiedi(area="senza area", includi_nascoste=True, tipo="light")
    assert r["trovate"] == 2


def test_la_profondita_la_decide_lo_strumento():
    """1 voce: completa (il dettaglio del dispatcher); 2-10: media; oltre: corta.

    Mutazione ESEGUITA: righe delle entita' sempre corte (`medium=False`) --
    rossa."""
    uno = _chiedi(riferimento="light.soggiorno_1")
    assert uno["profondita"] == "completa" and uno["voci"][0]["completo"]
    due = _chiedi(tipo="light")
    assert due["profondita"] == "media"
    assert due["voci"][0]["genere"] == "entita"


def test_dieci_voci_sono_ancora_medie_undici_sono_corte():
    """Mutazione ESEGUITA: soglia media a 9 -- rossa sul caso da 10."""
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
    assert "genere" in r10["voci"][0]
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


def test_limite_zero_con_piu_voci_non_promette_un_oltre():
    """Mutazione ESEGUITA: `oltre` scritto anche con `limite=0` -- rossa."""
    r = _chiedi(tipo="light", limite=0)
    assert r["voci"] == [] and r["trovate"] == 2 and "oltre" not in r


def test_la_persona_fuori_casa_esce_senza_zona_e_senza_coordinate():
    """Review Focus 3. Mutazione ESEGUITA: non passare da `redact_row` -- rossa."""
    r = _chiedi(tipo="person")
    voce = r["voci"][0]
    assert voce["stato"] == "not_home"
    assert "latitude" not in str(voce)


def test_lo_stato_si_filtra_su_quello_che_il_lettore_vede():
    """Marta e' «Lavoro» nello specchio, `not_home` alla porta: chi chiede
    `not_home` deve trovarla.

    Mutazione ESEGUITA: confrontare lo stato grezzo -- rossa."""
    r = _chiedi(tipo="person", stato="not_home")
    assert r["trovate"] == 1 and r["voci"][0]["id"] == "person.marta"


def test_nessun_riepilogo_per_stato():
    """Decisione 5: le voci, non i conti. `nota` e' ammessa perche' dichiara
    cio' che NON e' stato dato (le escluse), non riassume cio' che c'e'.

    Mutazione ESEGUITA: aggiungere `per_stato` al risultato -- rossa."""
    r = _chiedi(tipo="light", includi_nascoste=True)
    assert set(r) <= {"trovate", "escluse", "profondita", "voci", "oltre", "nota"}


def test_con_le_escluse_la_nota_dice_il_totale_vero():
    """Batteria del 30/09/2026: «74 non disponibili in totale» (catena) e «72
    in tutto» (ponte), quando le escluse dichiarate erano 179 e 203. Il
    numero dato era vero, il «totale» no: la prosa «leggi sempre `escluse`»
    non e' bastata, quindi il totale sta scritto nella risposta.

    Mutazione ESEGUITA: non scrivere `nota` -- rossa."""
    r = _chiedi(tipo="light", stato="on")
    assert r["trovate"] == 1 and r["escluse"]["nascoste"] == 2
    assert "in tutto sono 3 (1 trovate, 2 nascoste)" in r["nota"]


def test_la_nota_non_dice_date_quando_la_pagina_e_vuota():
    """`trovate` e' il conto prima della pagina: con `limite` 0 non e' stato
    dato niente, e la nota non deve dire il contrario.

    Mutazione ESEGUITA: riscrivere «trovate» come «date» nella nota -- rossa."""
    r = _chiedi(tipo="light", stato="on", limite=0)
    assert r["voci"] == [] and "date" not in r["nota"]
    assert "1 trovate" in r["nota"]


def test_senza_escluse_nessuna_nota():
    """Mutazione ESEGUITA: scrivere `nota` anche con le escluse a zero -- rossa."""
    r = _chiedi(tipo="light", stato="on", includi_nascoste=True)
    assert not any(r["escluse"].values())
    assert "nota" not in r


def test_solo_il_nome_cerca_in_tutti_i_generi():
    """Review Focus 1: «soggiorno» e' un'AREA, e anche due luci.

    Mutazione ESEGUITA: cercare solo fra le entita' -- rossa."""
    r = _chiedi(nome="soggiorno")
    assert r["trovate"] == 3
    assert [v["id"] for v in r["voci"] if v.get("genere") == "area"] == ["soggiorno"]
    assert {v["id"] for v in r["voci"] if v.get("genere") == "entita"} == {
        "light.soggiorno_1", "light.soggiorno_2"}


def test_i_dispositivi_si_trovano_per_nome():
    """Il vecchio `search` trovava «la lavatrice»; la porta nuova pure, e
    una voce sola e' il dettaglio del dispositivo.

    Mutazione ESEGUITA: non cercare fra i dispositivi -- rossa."""
    r = _chiedi(nome="lavatrice")
    assert r["trovate"] == 1 and r["profondita"] == "completa"
    assert r["voci"][0]["tipo"] == "dispositivo"
    assert r["voci"][0]["id"] == "dev_lavatrice"


def test_un_automazione_non_si_conta_due_volte():
    """`automation.sveglia` sta nel registro delle entita' E nel
    comportamento: la riga di comportamento la rappresenta.

    Mutazione ESEGUITA: non saltare le entita' `automation` -- rossa."""
    r = _chiedi_automazioni([("sveglia", "2026-09-28T06:30:00+00:00")],
                            {"nome": "sveglia"})
    assert r["trovate"] == 1 and r["profondita"] == "completa"
    assert r["voci"][0]["tipo"] == "automazione"


def test_le_automazioni_ordinate_dalla_piu_ferma():
    """#31 della batteria: la mai eseguita e' la piu' ferma di tutte.

    Mutazione ESEGUITA: ordinare per nome -- rossa. Mutazione ESEGUITA:
    «mai» ordinato come stringa (in fondo) -- rossa."""
    r = _chiedi_automazioni([("nuova", "2026-09-28T10:00:00+00:00"),
                             ("vecchia", "2026-02-17T10:00:00+00:00"),
                             ("abbandonata", None)],
                            {"genere": "automazione", "ordina": "ultimo_cambio"})
    assert [v["id"] for v in r["voci"]] == ["automation.abbandonata",
                                            "automation.vecchia",
                                            "automation.nuova"]
    assert r["voci"][0]["ultima_esecuzione"] == "mai"
    assert r["voci"][1]["ultima_esecuzione"].startswith("2026-02-17")


def test_il_filtro_fermo_legge_l_ultima_esecuzione_delle_automazioni():
    """Il filtro `fermo_da` sulle automazioni.

    Mutazione ESEGUITA: ignorare `fermo_da` fra le automazioni -- rossa."""
    r = _chiedi_automazioni([("vecchia", "2026-02-17T10:00:00+00:00"),
                             ("nuova", "2026-09-28T10:00:00+00:00")],
                            {"genere": "automazione", "fermo_da": "30d"})
    assert r["trovate"] == 1 and r["voci"][0]["id"] == "automation.vecchia"


def test_tipo_automation_senza_genere_legge_l_ultima_esecuzione():
    """Spec §2.2: per automazioni e script conta l'ultima esecuzione, anche
    quando il modello scrive il dominio (`tipo`) invece del genere.

    Mutazione ESEGUITA: non tradurre `tipo=automation` nel genere -- rossa."""
    r = _chiedi_automazioni([("vecchia", "2026-02-17T10:00:00+00:00"),
                             ("antica", "2026-01-01T10:00:00+00:00"),
                             ("nuova", "2026-09-28T10:00:00+00:00")],
                            {"tipo": "automation", "fermo_da": "30d"})
    assert r["trovate"] == 2
    assert {v["id"] for v in r["voci"]} == {"automation.vecchia",
                                            "automation.antica"}
    assert all(v["ultima_esecuzione"].startswith("2026-0") for v in r["voci"])


def test_nella_profondita_corta_il_comportamento_sta_in_una_riga():
    """Mutazione ESEGUITA: `modalita` scritta anche nelle righe corte -- rossa."""
    coppie = [(f"a{i:02}", "2026-09-28T10:00:00+00:00") for i in range(11)]
    comportamento, specchio = _automazioni(*coppie)
    for voce in specchio[5].values():
        voce["values"]["mode"] = "single"
    r = hq.query_house(_casa(), comportamento, specchio,
                       hq.parse_filters({"genere": "automazione"}),
                       detail=_dettaglio, now=T0)
    assert r["profondita"] == "corta"
    assert all("modalita" not in v for v in r["voci"])


def test_una_domanda_vuota_cerca_solo_le_entita():
    """Spec §2.1: il genere di default e' `entita`.

    Mutazione ESEGUITA: `only_by_name` vero anche senza nome -- rossa."""
    r = _chiedi()
    assert all(v.get("genere") == "entita" for v in r["voci"])
    assert r["trovate"] == 4


T_IERI = "2026-09-28T10:00:00+00:00"


def test_le_automazioni_si_filtrano_per_area_dalla_loro_entita():
    """Spec §2.4: `tipo=automation, area=soggiorno` non puo' dare TUTTE le
    automazioni con sicurezza. L'area e' quella dell'entita' di registro; chi
    non ce l'ha (o non e' nel registro) sta «senza area».

    Mutazione ESEGUITA: non applicare area/piano/integrazione al
    comportamento -- rossa."""
    casa = _casa()
    casa["entita"].append({**_luce("automation.luci_soggiorno", "soggiorno"),
                           "piattaforma": "automation"})
    coppie = [("luci_soggiorno", T_IERI), ("sveglia", T_IERI), ("fantasma", T_IERI)]
    r = _chiedi_automazioni(coppie, {"tipo": "automation", "area": "soggiorno"}, casa)
    assert r["trovate"] == 1 and r["voci"][0]["id"] == "automation.luci_soggiorno"
    r = _chiedi_automazioni(coppie, {"genere": "automazione", "area": "senza area"}, casa)
    assert {v["id"] for v in r["voci"]} == {"automation.sveglia",
                                            "automation.fantasma"}


@pytest.mark.parametrize("argomenti", [{"genere": "automazione", "sopra": 3},
                                       {"tipo": "automation", "sotto": 3},
                                       {"tipo": "script", "classe": "motion"}])
def test_un_filtro_che_non_vale_per_le_automazioni_si_dice(argomenti):
    """Mutazione ESEGUITA: togliere il controllo in `query_house` -- rossa."""
    r = _chiedi_automazioni([("sveglia", T_IERI)], argomenti)
    assert "errore" in r and "voci" not in r


def test_un_automazione_che_il_comportamento_non_conosce_resta_un_entita():
    """Si nasconde solo l'entita' che una riga di comportamento rappresenta.

    Mutazione ESEGUITA: nascondere ogni entita' `automation.*` quando si
    cerca il comportamento -- rossa."""
    r = _chiedi_automazioni([("altra", T_IERI)], {"nome": "sveglia"})
    assert r["trovate"] == 1 and r["voci"][0]["tipo"] == "entita"
    assert r["voci"][0]["id"] == "automation.sveglia"


def test_un_automazione_disabilitata_nel_registro_si_conta():
    """Mutazione ESEGUITA: nascondere ogni entita' `automation.*` quando si
    cerca il comportamento -- rossa."""
    casa = _casa()
    casa["entita"].append({**_luce("automation.spenta", None, disabilitata=1),
                           "nome": "Spenta", "piattaforma": "automation"})
    r = _chiedi_automazioni([("altra", T_IERI)], {"nome": "spenta"}, casa)
    assert r["trovate"] == 0 and r["escluse"]["disabilitate"] == 1


def test_il_nome_di_un_automazione_si_cerca_anche_nell_id():
    """«sveglia» trova `automation.sveglia_mattina` che si chiama «Buongiorno».

    Mutazione ESEGUITA: confrontare solo il nome -- rossa."""
    comportamento = [{"id": "automation.sveglia_mattina", "tipo": "automazione",
                      "nome": "Buongiorno"}]
    specchio = ({"automation.sveglia_mattina": "on"}, {}, {}, {}, {}, {})
    r = hq.query_house(_casa(), comportamento, specchio,
                       hq.parse_filters({"nome": "sveglia"}),
                       detail=_dettaglio, now=T0)
    assert "automation.sveglia_mattina" in {v["id"] for v in r["voci"]}


def test_un_dispositivo_disabilitato_e_fuori_e_contato():
    """Mutazione ESEGUITA: elencare anche i disabilitati -- rossa."""
    casa = _casa()
    casa["dispositivi"].append({**casa["dispositivi"][0], "id": "dev_asciugatrice",
                                "nome": "Asciugatrice", "disabilitato": 1})
    r = hq.query_house(casa, [], _specchio(STATI),
                       hq.parse_filters({"nome": "asciugatrice"}),
                       detail=_dettaglio, now=T0)
    assert r["trovate"] == 0 and r["escluse"]["disabilitate"] == 1


@pytest.mark.parametrize("argomenti", [{"limite": 51}, {"fermo_da": "tre giorni"},
                                       {"genere": "piano"}, {"sopra": "x"}])
def test_un_filtro_sbagliato_si_dice_non_si_indovina(argomenti):
    """Mutazione ESEGUITA, una per caso: togliere il tetto di `limite`, il
    controllo della durata, quello del genere, quello del numero -- ognuna
    rossa sul proprio caso."""
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
        assert len(json.dumps(r, ensure_ascii=False)) < BRIDGE_CEILING_CHARS, argomenti


# -- Review finale della fetta (30/09/2026): alias, filtri, riferimenti -------


def _two_rooms():
    """La casa di `_casa()` con una cucina al primo piano, un suo dispositivo
    hue, e gli alias che l'utente ha scritto in Home Assistant."""
    casa = _casa()
    casa["piani"].append({"id": "primo", "nome": "Primo piano", "livello": 1})
    casa["aree"][0]["alias"] = ["salotto"]
    casa["aree"].append({"id": "cucina", "nome": "Cucina", "piano_id": "primo",
                         "alias": [], "etichette": []})
    casa["dispositivi"].append({**casa["dispositivi"][0], "id": "dev_faretti",
                                "nome": "Faretti", "area_id": "cucina"})
    casa["dispositivi"].append({**casa["dispositivi"][0], "id": "dev_router",
                                "nome": "Router", "area_id": None})
    casa["entita"].append({**_luce("light.faretti", None, dispositivo_id="dev_faretti",
                                   piattaforma="hue"), "nome": "Faretti"})
    casa["entita"].append({**_luce("light.comodino", "soggiorno"),
                           "nome": "Lampada comodino", "alias": ["abat-jour"]})
    return casa


def _ask(casa, **argomenti):
    filtri = hq.parse_filters(argomenti)
    assert not isinstance(filtri, dict), filtri
    return hq.query_house(casa, [], _specchio(STATI), filtri, detail=_dettaglio, now=T0)


def test_un_entita_si_trova_anche_per_il_suo_alias():
    """I1: il vecchio `search` trovava «per nome o alias».

    Mutazione ESEGUITA: `_any_name_matches` che guarda solo il nome -- rossa."""
    r = _ask(_two_rooms(), nome="abat-jour")
    assert [v["id"] for v in r["voci"]] == ["light.comodino"]


def test_un_area_si_trova_anche_per_il_suo_alias():
    """Mutazione ESEGUITA: in `_area_rows` confrontare solo `nome` -- rossa."""
    r = _ask(_two_rooms(), genere="area", nome="salotto")
    assert r["trovate"] == 1 and r["voci"][0]["id"] == "soggiorno"


def test_i_dispositivi_si_filtrano_per_area_piano_e_integrazione():
    """I2: `genere=dispositivo, area=Cucina` restituiva tutti i dispositivi.

    Mutazione ESEGUITA: in `_device_rows` saltare `_place_matches` -- rossa;
    saltare il controllo di `integrazione` -- rossa sull'ultimo caso."""
    casa = _two_rooms()
    assert [v["id"] for v in _ask(casa, genere="dispositivo", area="Cucina")["voci"]] \
        == ["dev_faretti"]
    assert [v["id"] for v in _ask(casa, genere="dispositivo",
                                  piano="primo piano")["voci"]] == ["dev_faretti"]
    assert [v["id"] for v in _ask(casa, genere="dispositivo",
                                  area="senza area")["voci"]] == ["dev_router"]
    assert [v["id"] for v in _ask(casa, genere="dispositivo",
                                  integrazione="hue")["voci"]] == ["dev_faretti"]


def test_le_aree_si_filtrano_per_piano():
    """Mutazione ESEGUITA: in `_area_rows` ignorare `piano` -- rossa."""
    r = _ask(_two_rooms(), genere="area", piano="Primo piano")
    assert [v["id"] for v in r["voci"]] == ["cucina"]


@pytest.mark.parametrize("argomenti", [
    {"genere": "dispositivo", "stato": "on"},
    {"genere": "dispositivo", "tipo": "light"},
    {"genere": "area", "integrazione": "hue"},
    {"genere": "area", "area": "Cucina"},
    {"genere": "ricordo", "stato": "on"},
    {"genere": "integrazione", "area": "Cucina"},
    {"genere": "entita", "in_esecuzione": True},
    {"tipo": "light", "in_esecuzione": False},
    {"genere": "automazione", "tipo": "light"},
    {"genere": "automazione", "classe": "motion"},
])
def test_un_filtro_che_non_vale_per_il_genere_si_dice(argomenti):
    """I2, spec §2.4: mai un filtro lasciato cadere in silenzio.

    Mutazione ESEGUITA: togliere il controllo di `_FILTERS_BY_KIND` in
    `query_house` -- rossa su ogni caso."""
    filtri = hq.parse_filters(argomenti)
    r = hq.query_house(_two_rooms(), [], _specchio(STATI), filtri,
                       detail=_dettaglio, now=T0)
    assert "errore" in r, argomenti
    assert "voci" not in r


def test_i_filtri_che_valgono_non_sono_un_errore():
    """Il gemello: senza, un controllo che rifiutasse tutto passerebbe.

    Mutazione ESEGUITA: `_FILTERS_BY_KIND["dispositivo"]` senza `_PLACE` --
    rossa."""
    for argomenti in ({"genere": "dispositivo", "area": "Cucina", "integrazione": "hue"},
                      {"genere": "area", "piano": "Primo piano"},
                      {"tipo": "light", "stato": "on", "area": "soggiorno"}):
        assert "errore" not in _ask(_two_rooms(), **argomenti), argomenti


def test_un_riferimento_numerico_senza_genere_e_un_ricordo():
    """I3: la descrizione promette «il numero di un ricordo».

    Mutazione ESEGUITA: togliere il ramo `isdigit` di `_missing_reference` --
    rossa."""
    r = _ask(_two_rooms(), riferimento="7")
    assert r["trovate"] == 1 and r["voci"][0]["tipo"] == "ricordo"


def test_il_dominio_di_un_integrazione_senza_genere_e_un_integrazione():
    """Mutazione ESEGUITA: togliere il ramo delle piattaforme -- rossa."""
    r = _ask(_two_rooms(), riferimento="hue")
    assert r["voci"][0]["tipo"] == "integrazione"


def test_un_riferimento_che_non_esiste_lo_dice():
    """I3: prima era `trovate: 0` muto.

    Mutazione ESEGUITA: restituire l'insieme vuoto quando nessuna riga
    combacia -- rossa."""
    r = _ask(_two_rooms(), riferimento="light.inesistente")
    assert r["trovate"] == 0
    voce, = r["voci"]
    assert voce == {"esiste": False, "riferimento": "light.inesistente",
                    "suggerimento": voce["suggerimento"]}
    assert "search" in voce["suggerimento"]


def test_un_riferimento_non_trovato_con_un_registro_caduto_non_dice_non_esiste():
    """Il riferimento potrebbe stare proprio nel registro che non ha risposto.

    Mutazione ESEGUITA: passare `False` a `_not_found_detail` -- rossa."""
    filtri = hq.parse_filters({"riferimento": "light.inesistente"})
    r = hq.query_house(_two_rooms(), [], _specchio(STATI), filtri,
                       detail=_dettaglio, now=T0, unavailable=("entita",))
    voce, = r["voci"]
    assert voce["non_disponibile"] is True and "suggerimento" not in voce


def test_trovate_non_conta_una_voce_che_non_esiste():
    """`trovate: 1` accanto a `esiste: False` era una cosa trovata che non c'e'.

    Mutazione ESEGUITA: `_one` che restituisce sempre 1 -- rossa."""
    def nothing(kind, reference):
        return {"esiste": False, "tipo": kind, "riferimento": reference}
    filtri = hq.parse_filters({"genere": "ricordo", "riferimento": "99"})
    r = hq.query_house(_two_rooms(), [], _specchio(STATI), filtri,
                       detail=nothing, now=T0)
    assert r["trovate"] == 0 and r["voci"][0]["esiste"] is False


def test_un_riferimento_con_altri_filtri_senza_esito_resta_un_insieme_vuoto():
    """La cosa c'e', e' il filtro a non prenderla: nessuna voce «non esiste».

    Mutazione ESEGUITA: `_only_the_reference` sempre vero -- rossa."""
    r = _ask(_two_rooms(), riferimento="light.soggiorno_2", stato="on")
    assert r["trovate"] == 0 and r["voci"] == []
