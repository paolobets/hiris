"""Il dato fermo, giudicato con le sorelle (Task 1.1 e 1.3 degli strati 1-2;
proposta del 06/10/2026 dopo la revisione del giro 4).

Spec `docs/design/2026-09-10-i-tre-attori.md` §10: *«Non si inventa una
soglia: si archivia e si interpreta»*. La prima forma della regola guardava
ogni serie da sola, e sulle catture dal 03/09 al 03/10 dava 325 falsi su 360
rifiuti; questa guarda il gruppo (`House.sibling_group`), e sulle stesse
catture ne da' 15 su 73 (rigioco dello sprint, 06/10/2026).

**Le serie sono sintetiche**, nella forma di `server._punti_orari`, e senza
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
"""

from datetime import UTC, datetime, timedelta

from hiris.app.mind.flatline import HISTORY_DAYS, frozen_refusals, split_at
from hiris.app.mind.operations import FROZEN

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
        out.append(point)
    return out


def after(moment) -> bool:
    return moment.timestamp() >= FROZEN_FROM


def sun(moment) -> bool:
    return 5 <= moment.hour < 17


#: Il resto della casa: un contatore che si muove ogni ora.
REST = {"sensor.casa": series("contatore", lambda m: 0.1 + m.hour / 1000)}


def judge(group_series, *, rest=REST):
    groups = {e: "gruppo" for e in group_series}
    groups.update({e: None for e in rest})
    return frozen_refusals({**group_series, **rest}, groups, day_start_ts=FROZEN_FROM)


# -- i blocchi veri -----------------------------------------------------------

INVERTER = {
    "sensor.prodotta": series("contatore", lambda m: 0.0 if after(m)
                              else (0.4 if sun(m) else 0.0)),
    "sensor.soc": series("istantanea", lambda m: (74, 74) if after(m)
                         else (50 + m.hour, 51 + m.hour)),
    "sensor.carico": series("istantanea", lambda m: (10, 10) if after(m) else (200, 900)),
}


def test_il_30_09_tutto_l_inverter_fermo_si_rifiuta():
    refusals = judge(INVERTER)
    assert set(refusals) == set(INVERTER)
    assert {r.cause for r in refusals.values()} == {FROZEN}


def test_il_rifiuto_dice_il_gruppo_e_perche():
    reason = judge(INVERTER)["sensor.soc"].reason
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
    assert set(judge(block)) == set(block)


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
    groups = {**{e: "inv" for e in INVERTER}, "sensor.casa": None}
    refusals = frozen_refusals({**INVERTER, **REST}, groups, day_start_ts=FROZEN_FROM,
                               entity_ids=["sensor.prodotta"])
    assert set(refusals) == {"sensor.prodotta"}


# -- la separazione fra giorno e storia ---------------------------------------


def test_split_at_separa_la_storia_dal_giorno():
    points = INVERTER["sensor.soc"]
    before, day = split_at(points, FROZEN_FROM)
    assert len(before) == HISTORY_DAYS * 24 and len(day) == 24
    assert day[0]["inizio"] == DAY.isoformat()


def test_split_at_lascia_al_giorno_un_punto_senza_istante():
    odd = {"inizio": None, "fine": None, "valore": 1.0}
    assert split_at([odd], FROZEN_FROM) == ([], [odd])
