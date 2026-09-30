"""Il nucleo porta cio' che e' stabile, non lo stato del momento (spec §5).

Misurato il 29/09/2026: la #18 («come sta la casa») e' stata risposta SENZA
strumenti e SBAGLIATA su tutte e due le strade, prendendo per buona la
fotografia di «Notevole adesso».
"""
from hiris.app.home_space.briefing import compose
from tests.test_briefing import _CASA, _COMPORTAMENTO, _RICORDI, _STATO


def test_il_nucleo_non_ha_piu_notevole_adesso():
    """Mutazione ESEGUITA: rimettere highlight_section in print_order -- rossa."""
    testo, _ = compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert "Notevole adesso" not in testo
    assert "non rispondono" not in testo


def test_il_comportamento_esce_intero_quando_c_e_spazio():
    """Oggi 12 su 17 con 6.800 caratteri: senza la sezione dello stato ci sta.

    Mutazione ESEGUITA: togliere `behavior_section` da `print_order` in
    `compose()` -- rossa.

    **La mutazione che il piano dichiarava qui non la fa arrossire**, ed e'
    stata eseguita (29/09/2026): comportamento secondo nel taglio, riserva 0,
    `DEFAULT_CEILING = 4000` -- VERDE. Diciassette nomi corti su una casa di
    quattro entita' pesano meno di mille caratteri: nessun tetto di quelli
    provati li tocca, e l'ordine del taglio non si vede. La prova che quella
    mutazione fa davvero arrossire e' la seguente."""
    comportamento = [{"id": f"automation.a{i}", "tipo": "automazione",
                      "nome": f"Automazione {i}"} for i in range(17)]
    testo, _ = compose(_CASA, comportamento, _RICORDI, _STATO)
    assert all(f"automation.a{i}" in testo for i in range(17))


def test_quando_il_tetto_morde_cadono_le_capacita_non_le_automazioni():
    """La forma che il tetto ha sulla casa vera: una mappa delle capacita'
    piena (150 firme, il tetto proprio della sezione a 600 caratteri) e
    diciassette automazioni dai nomi lunghi. Misurato: senza tetto il nucleo
    pesa 6.881 caratteri, al tetto di 6.800 il taglio morde -- e morde le
    capacita' (145 entita' senza), non una sola automazione.

    Mutazione ESEGUITA: in `compose()`, rimettere `("comportamento", ...)`
    PRIMA di `("capacita", ...)` in `cut_order` (col `DEFAULT_CEILING` a
    4.000, la forma dichiarata dal piano) -- rossa."""
    from hiris.app.proxy.entity_cache import CAPABILITIES

    luci = [{"id": f"light.l{n}", "nome": f"L{n}", "area_id": "sala",
             "dispositivo_id": None, "classe": None, "unita": None,
             "disabilitata": 0} for n in range(150)]
    casa = dict(_CASA, entita=_CASA["entita"] + luci)
    attributi = {f"light.l{n}": {CAPABILITIES: {"effect_list": [f"effetto{n}"]}}
                 for n in range(150)}
    comportamento = [{"id": f"automation.a{i}", "tipo": "automazione",
                      "nome": f"Automazione {i} " + "n" * 250} for i in range(17)]
    testo, riepilogo = compose(casa, comportamento, _RICORDI, _STATO, attributes=attributi)
    assert riepilogo["truncated"] is True, "la prova presuppone che il tetto morda"
    assert all(f"automation.a{i})" in testo for i in range(17))
    assert "cosa sanno fare" in " ".join(riepilogo["notices"])


def test_la_riga_del_comportamento_non_ripete_il_genere():
    """Il genere lo dice gia' l'id (`automation.`, `script.`): il suffisso
    «(automazione)» era un doppione da ~14 caratteri a riga, e sulla casa vera
    (30/09/2026, 19 voci) teneva fuori dal nucleo l'ultima automazione per
    un centinaio di caratteri.

    Mutazione ESEGUITA: rimettere ` ({kind})` in `_behavior_lines` -- rossa."""
    comportamento = [{"id": "automation.a", "tipo": "automazione", "nome": "A", "corpo": {}},
                     {"id": "script.s", "tipo": "script", "nome": "S", "corpo": {}}]
    testo, _ = compose(_CASA, comportamento, _RICORDI, _STATO)
    assert "- A (id: automation.a)\n" in testo
    assert "(automazione)" not in testo and "(script)" not in testo


def test_se_il_comportamento_non_ci_sta_si_dice_come_averlo():
    """Mutazione ESEGUITA: in `cut_labels`, riportare le frasi del
    comportamento a «voci di comportamento non incluse» senza la strada per
    ritrovarle -- rossa."""
    comportamento = [{"id": f"automation.a{i}", "tipo": "automazione",
                      "nome": "x" * 300} for i in range(60)]
    testo, _ = compose(_CASA, comportamento, _RICORDI, _STATO, ceiling=3000)
    assert 'search(genere="automazione")' in testo or "genere=automazione" in testo


def test_gaps_mention_search():
    """Mutazione ESEGUITA: aggiungere «`view`» all'avviso dei corpi mancanti
    -- rossa. (Verde gia' prima di questa fetta: il Task 5 aveva riscritto i
    testi che nominavano `view`; la prova tiene la porta chiusa.)"""
    testo, _ = compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert "`view`" not in testo
