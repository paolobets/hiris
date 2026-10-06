"""Il dato fermo, giudicato contro la sua storia (Task 1.1 degli strati 1-2).

Spec `docs/design/2026-09-10-i-tre-attori.md` §10: *«Non si inventa una
soglia: si archivia e si interpreta»*. Decisione D3 del proprietario
(03/10/2026): una serie e' ferma dove **non varia** mentre **la sua stessa
storia**, alla stessa ora, variava sempre. Nessun N scritto da noi.

**Le serie qui sotto sono sintetiche**, nella forma di `server._punti_orari`,
e senza nomi della casa. Ricalcano il caso del 30/09/2026 descritto nel
BACKLOG («produzione 0 con copertura 1.0» sull'inverter): i numeri veri di
quel giorno li cattura il Task 1.0, sul computer del proprietario, e quando ci
saranno entrano qui come ingresso fisso al posto di queste.
"""

from datetime import UTC, datetime, timedelta

from hiris.app.mind.flatline import flatline_stretches, frozen_refusals, split_at
from hiris.app.mind.operations import FROZEN

DAY = datetime(2026, 9, 30, tzinfo=UTC)
SUN_HOURS = range(7, 19)


def _hour(day, h):
    start = day + timedelta(hours=h)
    return start.isoformat(), (start + timedelta(hours=1)).isoformat()


def counter(day, change_per_hour):
    """Una serie di contatore: `valore` e' il `cambio` dell'ora."""
    points = []
    for h in range(24):
        start, end = _hour(day, h)
        points.append({"inizio": start, "fine": end, "valore": change_per_hour(h),
                      "media": None, "minimo": None, "massimo": None})
    return points


def instant(day, low_high_per_hour):
    """Una serie di misura istantanea: `media`/`minimo`/`massimo`."""
    points = []
    for h in range(24):
        start, end = _hour(day, h)
        low, high = low_high_per_hour(h)
        points.append({"inizio": start, "fine": end, "valore": None,
                      "media": None if low is None else (low + high) / 2,
                      "minimo": low, "massimo": high})
    return points


def history_of(build, per_hour, days=7):
    """I giorni precedenti, in una lista sola: come li darebbe una lettura
    delle statistiche orarie su una finestra piu' lunga."""
    points = []
    for g in range(1, days + 1):
        points.extend(build(DAY - timedelta(days=g), per_hour))
    return points


def normal_production(h):
    return 0.4 + h / 100 if h in SUN_HOURS else 0.0


def normal_consumption(h):
    return 0.2 + h / 1000


def normal_power(h):
    return (100.0, 2500.0 + h) if h in SUN_HOURS else (0.0, 0.0)


def _frozen_only(stretches):
    return [t for t in stretches if t["esito"] == "ferma"]


# ── (a) il 30/09 dell'inverter ──────────────────────────────────────────────


def test_il_30_09_la_produzione_ferma_esce_ferma_dalla_mezzanotte():
    """Di notte la produzione non varia nemmeno nella sua storia; di giorno
    variava sempre. Il tratto fermo comincia dove comincia l'immobilita' --
    la mezzanotte -- non alla prima ora di sole: la serie e' immobile dalle
    00:00, ed e' quello il «dal» vero."""
    day = counter(DAY, lambda h: 0.0)
    stretches = flatline_stretches(day,
                                history=history_of(counter, normal_production))
    assert [(t["dal"], t["al"]) for t in _frozen_only(stretches)] == [
        (day[0]["inizio"], day[-1]["fine"])]
    assert _frozen_only(stretches)[0]["giorni_di_storia"] == 7


def test_il_30_09_il_consumo_fermo_esce_fermo_dalla_mezzanotte():
    day = counter(DAY, lambda h: 0.0)
    stretches = flatline_stretches(day,
                                history=history_of(counter, normal_consumption))
    assert [(t["dal"], t["al"]) for t in _frozen_only(stretches)] == [
        (day[0]["inizio"], day[-1]["fine"])]


def test_il_30_09_la_potenza_ferma_esce_ferma_dalla_mezzanotte():
    """Una misura istantanea e' immobile quando `minimo == massimo`, anche su
    un valore diverso da zero: l'inverter che ripete l'ultima lettura."""
    day = instant(DAY, lambda h: (1234.0, 1234.0))
    stretches = flatline_stretches(day,
                                history=history_of(instant, normal_power))
    assert [(t["dal"], t["al"]) for t in _frozen_only(stretches)] == [
        (day[0]["inizio"], day[-1]["fine"])]


def test_il_tratto_dice_perche_senza_chiedere_altro():
    """Fondamenta 1: chi riceve il tratto lo legge da solo."""
    day = counter(DAY, lambda h: 0.0)
    (stretch,) = flatline_stretches(day,
                                   history=history_of(counter, normal_consumption))
    assert set(stretch) == {"dal", "al", "esito", "perche", "giorni_di_storia"}
    assert "7" in stretch["perche"]


# ── (b) la notte del fotovoltaico non e' un guasto ──────────────────────────


def test_una_notte_del_fotovoltaico_non_esce_ferma():
    day = counter(DAY, normal_production)
    assert flatline_stretches(
        day, history=history_of(counter, normal_production)) == []


def test_un_ora_immobile_anche_in_un_giorno_della_storia_non_e_ferma():
    """«Sempre variato» vuol dire in OGNI giorno della storia: un giorno solo
    in cui quell'ora era immobile anche allora basta a dire che l'immobilita'
    e' una cosa che a questa serie succede."""
    past = history_of(counter, normal_consumption)
    for p in past:
        if p["inizio"].endswith("T12:00:00+00:00") and p["inizio"].startswith(
                "2026-09-27"):
            p["valore"] = 0.0
    day = counter(DAY, lambda h: 0.0 if h == 12 else normal_consumption(h))
    assert flatline_stretches(day, history=past) == []


# ── (c) una storia che non basta dice «non lo so» ───────────────────────────


def test_senza_storia_una_serie_immobile_e_non_lo_so_non_ferma():
    day = counter(DAY, lambda h: 0.0)
    stretches = flatline_stretches(day, history=[])
    assert _frozen_only(stretches) == []
    assert [(t["esito"], t["dal"], t["al"]) for t in stretches] == [
        ("non_lo_so", day[0]["inizio"], day[-1]["fine"])]
    assert stretches[0]["giorni_di_storia"] == 0


def test_una_storia_di_soli_buchi_non_e_una_storia():
    """Un giorno della storia senza valore a quell'ora non e' un giorno che
    «variava»: non dice niente, e non conta."""
    past = history_of(counter, lambda h: None)
    day = counter(DAY, lambda h: 0.0)
    stretches = flatline_stretches(day, history=past)
    assert [t["esito"] for t in stretches] == ["non_lo_so"]


def test_la_storia_di_un_altra_ora_non_vale_per_questa():
    """La storia si legge alla STESSA ora: le ore di sole di ieri non dicono
    niente sulla notte di oggi."""
    past = [p for p in history_of(counter, normal_production)
                  if int(p["inizio"][11:13]) in SUN_HOURS]
    night = [p for p in counter(DAY, lambda h: 0.0)
             if int(p["inizio"][11:13]) < 7]
    stretches = flatline_stretches(night, history=past)
    assert [t["esito"] for t in stretches] == ["non_lo_so"]


# ── (d) una serie che varia non e' ferma ────────────────────────────────────


def test_una_serie_che_varia_non_e_ferma():
    day = counter(DAY, normal_consumption)
    assert flatline_stretches(
        day, history=history_of(counter, normal_consumption)) == []


def test_un_buco_spezza_il_tratto():
    """Un'ora senza valore non e' un'ora immobile: di lei non si sa niente, e
    il tratto non la attraversa."""
    day = counter(DAY, lambda h: None if h == 12 else 0.0)
    stretches = flatline_stretches(day,
                                history=history_of(counter, normal_consumption))
    assert [(t["dal"], t["al"]) for t in _frozen_only(stretches)] == [
        (day[0]["inizio"], day[11]["fine"]),
        (day[13]["inizio"], day[-1]["fine"])]


def test_un_ora_mancante_spezza_il_tratto():
    """Le statistiche saltano un'ora: le due ore ai lati non sono contigue."""
    day = counter(DAY, lambda h: 0.0)
    del day[12]
    stretches = flatline_stretches(day,
                                history=history_of(counter, normal_consumption))
    assert len(_frozen_only(stretches)) == 2


# ── i rifiuti per il resoconto (Task 1.3, D4 «rifiutata») ───────────────────


def test_solo_un_tratto_fermo_rifiuta_le_misure():
    """`frozen_refusals` rifiuta l'entita' con un tratto «ferma» e non quella
    con un tratto «non lo so»: una misura non si toglie senza prova.

    Mutazione ESEGUITA (06/10/2026): il filtro su `esito == FROZEN` tolto --
    rossa, la serie senza storia veniva rifiutata."""
    refusals = frozen_refusals(
        {"sensor.ferma": counter(DAY, lambda h: 0.0),
         "sensor.senza_storia": counter(DAY, lambda h: 0.0),
         "sensor.viva": counter(DAY, normal_consumption)},
        {"sensor.ferma": history_of(counter, normal_consumption),
         "sensor.viva": history_of(counter, normal_consumption)})
    assert set(refusals) == {"sensor.ferma"}
    assert refusals["sensor.ferma"].cause == FROZEN
    assert refusals["sensor.ferma"].reason.startswith("sensor.ferma e' ferma: non varia")


def test_split_at_separa_la_storia_dal_giorno():
    """Il giorno e la storia arrivano in una lettura sola: la separazione e'
    all'istante d'inizio del giorno, che resta col giorno."""
    past = history_of(counter, normal_consumption, days=1)
    day = counter(DAY, normal_consumption)
    before, after = split_at(past + day, DAY.timestamp())
    assert before == past and after == day


def test_split_at_lascia_al_giorno_un_punto_senza_istante():
    odd = {"inizio": None, "fine": None, "valore": 1.0}
    assert split_at([odd], DAY.timestamp()) == ([], [odd])
