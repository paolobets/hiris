"""Il dato fermo, giudicato con le sorelle (Task 1.1 e 1.3 degli strati 1-2;
proposta del 06/10/2026 dopo la revisione del giro 4).

Spec `docs/design/2026-09-10-i-tre-attori.md` §10: *«Non si inventa una
soglia: si archivia e si interpreta»*. La prima forma della regola guardava
ogni serie da sola, e sulle catture dal 03/09 al 03/10 dava 325 falsi su 360
rifiuti; questa guarda il gruppo (`House.sibling_group`), e sulle stesse
catture ne da' 15 su 73 (rigioco dello sprint, 06/10/2026).

**Le serie sono sintetiche**, nella forma di `recipes.hourly_points`, e senza
nomi della casa. Gli scenari sono quelli del prototipo della proposta
(`/mnt/project-files/attori/2026-10-06-dato-fermo-prototipo.py`), che lo
sprint ha fatto girare sulle catture.

Mutazioni ESEGUITE (06/10/2026), ognuna ripristinata (`git status`), tutte
rosse per la ragione giusta:
- tolta la condizione «diverso da zero» -- rossa la presa spenta (la prima
  stesura, con un uso di due ore, era INERTE: l'ora vicina lo spiegava gia';
  ora l'uso dura cinque ore);
- tolta la condizione «la casa si muove» -- rossa la casa ferma tutta;
- `NEIGHBOUR_HOURS = 0` -- rosso il tramonto che anticipa;
- basta un'entita' ferma invece del gruppo intero -- rossa l'ora piatta di un
  sensore solo;
- il contatore rifiutato anche quando il tratto non arriva a fine giornata --
  rossa la prova del contatore che recupera.

Mutazioni ESEGUITE l'08/10/2026 (giro 90 del revisore), ripristinate:
- `Recipe._run_step` che dice `ferma` per ogni rifiuto con ore escluse --
  rossa la prova della copertura bassa che resta tale (G90-1);
- `frozen_day` senza il taglio dell'inizio alla mezzanotte -- rossa la prova
  del blocco di tre giorni (G90-2).

Dall'08/10/2026 (decisione del proprietario sul dato fermo) una misura
istantanea non si rifiuta piu': perde le ore del tratto (`frozen_day` ->
esclusioni). Le prove qui sotto contano chi e' toccato -- rifiutato o con ore
escluse -- e quelle in fondo dicono quali ore e cosa resta del conto.
"""

from datetime import UTC, datetime, timedelta

from hiris.app.mind.flatline import HISTORY_DAYS, frozen_day, mark_excluded, split_at
from hiris.app.mind.operations import COVERAGE_LOW, FROZEN, Measurement
from hiris.app.mind.recipes import Recipe

DAY = datetime(2026, 9, 30, tzinfo=UTC)
FROZEN_FROM = DAY.timestamp()
WINDOW = [DAY - timedelta(days=HISTORY_DAYS) + timedelta(hours=h)
          for h in range((HISTORY_DAYS + 1) * 24)]


def series(kind, value_at):
    """Una serie della finestra intera: `contatore` porta `valore` (il cambio
    dell'ora), `istantanea` porta `minimo`/`massimo`."""
    out = []
    for moment in WINDOW:
        v = value_at(moment)
        point = {"inizio": moment.isoformat(),
                 "fine": (moment + timedelta(hours=1)).isoformat(),
                 "valore": None, "media": None, "minimo": None, "massimo": None}
        if kind == "contatore":
            point["valore"] = v
        else:
            point["minimo"], point["massimo"] = v
            point["media"] = sum(v) / 2
        out.append(point)
    return out


def after(moment) -> bool:
    return moment.timestamp() >= FROZEN_FROM


def sun(moment) -> bool:
    return 5 <= moment.hour < 17


#: Il resto della casa: un contatore che si muove ogni ora.
REST = {"sensor.casa": series("contatore", lambda m: 0.1 + m.hour / 1000)}


def verdicts(group_series, *, rest=REST, entity_ids=None):
    groups = {e: "gruppo" for e in group_series}
    groups.update({e: None for e in rest})
    return frozen_day({**group_series, **rest}, groups, day_start_ts=FROZEN_FROM,
                      entity_ids=entity_ids)


def judge(group_series, *, rest=REST):
    """Chi la regola tocca: `{entita': rifiuto}` per i contatori fermi fino a
    sera, `{entita': [esclusioni]}` per le misure istantanee."""
    refusals, exclusions = verdicts(group_series, rest=rest)
    assert not set(refusals) & set(exclusions)
    return {**refusals, **exclusions}


# -- i blocchi veri -----------------------------------------------------------

INVERTER = {
    "sensor.prodotta": series("contatore", lambda m: 0.0 if after(m)
                              else (0.4 if sun(m) else 0.0)),
    "sensor.soc": series("istantanea", lambda m: (74, 74) if after(m)
                         else (50 + m.hour, 51 + m.hour)),
    "sensor.carico": series("istantanea", lambda m: (10, 10) if after(m) else (200, 900)),
}


def test_il_30_09_tutto_l_inverter_fermo_e_toccato():
    """Il contatore fermo fino a sera si rifiuta; le misure istantanee perdono
    le ore del tratto, che qui e' il giorno intero."""
    refusals, exclusions = verdicts(INVERTER)
    assert set(refusals) == {"sensor.prodotta"}
    assert {r.cause for r in refusals.values()} == {FROZEN}
    assert set(exclusions) == {"sensor.soc", "sensor.carico"}
    for found in exclusions.values():
        [whole] = found
        assert (whole.start_ts, whole.end_ts) == (FROZEN_FROM, FROZEN_FROM + 86400)
        assert whole.cause == FROZEN


def test_il_rifiuto_dice_il_gruppo_e_perche():
    [exclusion] = judge(INVERTER)["sensor.soc"]
    reason = exclusion.reason
    assert reason == judge(INVERTER)["sensor.prodotta"].reason.replace(
        "sensor.prodotta", "sensor.soc", 1)
    assert reason.startswith("sensor.soc e' ferma: dalle 2026-09-30T00:00:00+00:00 ")
    assert "nessuna delle 3 entita' del suo gruppo" in reason
    assert "mentre il resto della casa si muove" in reason
    assert f"nei {HISTORY_DAYS} giorni di storia" in reason


def test_un_blocco_di_tre_giorni_arriva_fino_a_oggi():
    """Un tratto sull'intera finestra: il blocco cominciato due giorni fa non e'
    spiegato dalla sua stessa storia."""
    start = FROZEN_FROM - 2 * 86400
    block = {"sensor.e": series("contatore", lambda m: 0.0 if m.timestamp() >= start else 0.3),
             "sensor.w": series("istantanea", lambda m: (7, 7) if m.timestamp() >= start
                                else (100, 300))}
    found = judge(block)
    assert set(found) == set(block)
    # G90-2: l'esclusione comincia alla mezzanotte del giorno, non dove
    # comincia il tratto -- un'ora detta fuori dal giorno sarebbe falsa.
    [stretch] = found["sensor.w"]
    assert stretch.start_ts == FROZEN_FROM
    assert stretch.out()["dal"] == "2026-09-30T00:00:00+00:00"
    assert stretch.reason.startswith("sensor.w e' ferma: dalle 2026-09-28T00:00:00+00:00 ")


def test_il_contatore_che_recupera_tiene_il_suo_totale():
    """G4-2: il contatore si ferma alle 8-10 e alle 11 riparte; il suo totale e'
    giusto, la sua potenza ferma no."""
    meter = {"sensor.m_energia": series("contatore", lambda m: 0.0 if (
                 after(m) and 8 <= m.hour < 11) else 0.3),
             "sensor.m_potenza": series("istantanea", lambda m: (5, 5) if (
                 after(m) and 8 <= m.hour < 11) else (100, 300))}
    assert set(judge(meter)) == {"sensor.m_potenza"}


# -- cio' che non e' una fonte ferma -----------------------------------------


def test_uno_scaldabagno_spento_con_la_tensione_viva_non_e_fermo():
    boiler = {"sensor.b_energia": series("contatore", lambda m: 0.0 if after(m)
                                         else (1.0 if 10 <= m.hour < 15 else 0.0)),
              "sensor.b_tensione": series("istantanea", lambda m: (228, 232))}
    assert judge(boiler) == {}


def test_un_ora_piatta_di_un_sensore_solo_non_e_ferma():
    station = {"sensor.t": series("istantanea", lambda m: (21, 21)
                                  if m == DAY + timedelta(hours=9) else (20.5, 21.5)),
               "sensor.u": series("istantanea", lambda m: (50, 52))}
    assert judge(station) == {}


def test_la_notte_di_un_fotovoltaico_senza_batteria_si_spiega_da_se():
    pv = {"sensor.pv_e": series("contatore", lambda m: 0.4 if sun(m) else 0.0),
          "sensor.pv_w": series("istantanea", lambda m: (100, 2500) if sun(m) else (3, 3))}
    assert judge(pv) == {}


def test_una_presa_spenta_ferma_a_zero_e_riposo_non_silenzio():
    plug = {"sensor.p_e": series("contatore", lambda m: 0.0 if after(m)
                                 else (1.0 if 10 <= m.hour < 15 else 0.0)),
            "sensor.p_w": series("istantanea", lambda m: (0, 0) if after(m)
                                 else ((900, 1100) if 10 <= m.hour < 15 else (0, 0)))}
    assert judge(plug) == {}


def test_il_cambio_dell_ora_non_ferma_un_apparecchio_a_orario():
    hour = lambda m: 5 if after(m) else 4
    shifted = {"sensor.d_e": series("contatore", lambda m: 0.5 if m.hour == hour(m) else 0.0),
               "sensor.d_w": series("istantanea", lambda m: (800, 1000) if m.hour == hour(m)
                                    else (0, 0))}
    assert judge(shifted) == {}


def test_il_tramonto_che_anticipa_non_e_un_blocco():
    """Due sensori di luce fermi su un valore basso ogni notte: oggi il buio
    arriva un'ora prima. «La stessa ora» comprende l'ora vicina."""
    def lux(m):
        dark_from = 16 if after(m) else 17
        return (3, 3) if m.hour >= dark_from or m.hour < 5 else (100, 400)
    light = {"sensor.luce_a": series("istantanea", lux),
             "sensor.luce_b": series("istantanea", lux)}
    assert judge(light) == {}


def test_se_si_ferma_tutta_la_casa_non_e_una_fonte():
    still = {"sensor.casa": series("contatore", lambda m: 0.0 if after(m)
                                   else 0.1 + m.hour / 1000)}
    assert judge(INVERTER, rest=still) == {}


def test_un_gruppo_di_una_sola_entita_non_si_giudica():
    alone = {"sensor.soc": INVERTER["sensor.soc"]}
    assert judge(alone) == {}


def test_si_rifiutano_solo_le_entita_chieste():
    refusals, exclusions = verdicts(INVERTER, entity_ids=["sensor.prodotta"])
    assert set(refusals) == {"sensor.prodotta"} and exclusions == {}


# -- la separazione fra giorno e storia ---------------------------------------


def test_split_at_separa_la_storia_dal_giorno():
    points = INVERTER["sensor.soc"]
    before, day = split_at(points, FROZEN_FROM)
    assert len(before) == HISTORY_DAYS * 24 and len(day) == 24
    assert day[0]["inizio"] == DAY.isoformat()


def test_split_at_lascia_al_giorno_un_punto_senza_istante():
    odd = {"inizio": None, "fine": None, "valore": 1.0}
    assert split_at([odd], FROZEN_FROM) == ([], [odd])


# -- solo le ore ferme (decisione dell'08/10/2026) ---------------------------

METER = {"sensor.m_energia": series("contatore", lambda m: 0.0 if (
             after(m) and 8 <= m.hour < 11) else 0.3),
         "sensor.m_potenza": series("istantanea", lambda m: (5, 5) if (
             after(m) and 8 <= m.hour < 11) else (100, 300))}


def _day(entity_id, exclusions):
    return mark_excluded(split_at(METER[entity_id], FROZEN_FROM)[1],
                         exclusions.get(entity_id))


def test_l_esclusione_e_il_tratto_detto_nell_ora_della_casa():
    _refusals, exclusions = verdicts(METER)
    [stretch] = exclusions["sensor.m_potenza"]
    assert (stretch.start_ts, stretch.end_ts) == (FROZEN_FROM + 8 * 3600,
                                                 FROZEN_FROM + 11 * 3600)
    assert stretch.out() == {"dal": "2026-09-30T08:00:00+00:00",
                             "al": "2026-09-30T11:00:00+00:00",
                             "causa": FROZEN, "perche": stretch.reason,
                             "in_breve": (
                                 "Dalle 08:00 alle 11:00 tutti i sensori di questo "
                                 "dispositivo sono rimasti uguali mentre il resto "
                                 "della casa si muoveva: quelle ore non entrano nel "
                                 "calcolo.")}


def test_il_contatore_fermo_che_recupera_tiene_il_totale_e_la_potenza_perde_tre_ore():
    _refusals, exclusions = verdicts(METER)
    recipe = Recipe({"why": "prova", "steps": [
        {"name": "energia", "operation": "somma_periodo",
         "inputs": ["@sensor.m_energia"], "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "potenza", "operation": "media_min_max",
         "inputs": ["@sensor.m_potenza"], "params": {"unit": "W", "expected_parts": 24}}]})
    results = recipe.run(series={e: _day(e, exclusions) for e in METER})
    # Il contatore: tutte le ore contano, le ferme con il loro cambio 0.
    assert results["energia"] == Measurement(round(0.3 * 21, 2), unit="kWh", coverage=1.0)
    # La potenza: le tre ore ferme escono, e la misura lo dice.
    potenza = results["potenza"]
    assert potenza.coverage == 21 / 24
    assert potenza.value["minimo"] == 100
    assert [x.out()["dal"] for x in potenza.excluded] == ["2026-09-30T08:00:00+00:00"]


def test_un_passo_che_legge_una_misura_con_ore_escluse_le_eredita():
    """Una quota fatta su un totale senza tre ore e' anche lei senza quelle
    ore: l'esclusione passa ai passi che leggono il risultato. (Le ore sono
    messe a mano su un contatore: `Recipe.run` non sa di che genere sia la
    serie, sa solo quali punti portano un'esclusione.)"""
    _refusals, exclusions = verdicts(METER)
    marked = mark_excluded(split_at(METER["sensor.m_energia"], FROZEN_FROM)[1],
                           exclusions["sensor.m_potenza"])
    recipe = Recipe({"why": "prova", "steps": [
        {"name": "parte", "operation": "somma_periodo",
         "inputs": ["@sensor.a"], "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "tutto", "operation": "somma_periodo",
         "inputs": ["@sensor.b"], "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "quota", "operation": "quota", "inputs": ["$parte", "$tutto"]}]})
    results = recipe.run(series={
        "sensor.a": marked, "sensor.b": split_at(METER["sensor.m_energia"], FROZEN_FROM)[1]})
    assert (list(results["parte"].excluded) == exclusions["sensor.m_potenza"]
            == list(results["quota"].excluded))
    assert results["tutto"].excluded == ()


def test_se_rifiuta_anche_con_le_ore_ferme_il_perche_resta_la_copertura():
    """G90-1: un giorno che ha dato solo dodici ore -- sotto il minimo anche
    senza togliere niente -- e dentro tre ore ferme. Il rifiuto e' la
    copertura bassa, non il dato fermo: dire `ferma` sarebbe una causa falsa."""
    _refusals, exclusions = verdicts(METER)
    day = _day("sensor.m_potenza", exclusions)
    thin = [p if p.get("inizio") < "2026-09-30T12" else {"inizio": p["inizio"],
                                                          "fine": p["fine"]}
            for p in day]
    recipe = Recipe({"why": "prova", "steps": [
        {"name": "potenza", "operation": "media_min_max",
         "inputs": ["@sensor.m_potenza"], "params": {"unit": "W", "expected_parts": 24}}]})
    result = recipe.run(series={"sensor.m_potenza": thin})["potenza"]
    assert result.cause == COVERAGE_LOW, result


def test_il_contatore_fermo_fino_a_sera_si_rifiuta():
    refusals, exclusions = verdicts(INVERTER)
    assert refusals["sensor.prodotta"].cause == FROZEN
    assert "sensor.prodotta" not in exclusions


def test_la_frase_per_la_pagina_dice_l_integrazione_e_la_fine_del_giorno():
    """Un gruppo d'istanza (entita' sole sul loro dispositivo) si dice
    «integrazione», non «dispositivo»; un tratto che arriva a mezzanotte
    finisce alle «24:00», non alle «00:00»."""
    evening = {"sensor.t1": series("istantanea", lambda m: (21, 21) if (
                   after(m) and m.hour >= 20) else (19 + m.hour / 10, 19.2 + m.hour / 10)),
               "sensor.t2": series("istantanea", lambda m: (55, 55) if (
                   after(m) and m.hour >= 20) else (40 + m.hour, 41 + m.hour))}
    groups = {**{e: ("istanza", "e_hub") for e in evening}, "sensor.casa": None}
    _refusals, exclusions = frozen_day({**evening, **REST}, groups, day_start_ts=FROZEN_FROM)
    [stretch] = exclusions["sensor.t1"]
    assert stretch.summary == (
        "Dalle 20:00 alle 24:00 tutti i dispositivi di questa integrazione sono "
        "rimasti uguali mentre il resto della casa si muoveva: quelle ore non "
        "entrano nel calcolo.")
