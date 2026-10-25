"""Il nucleo porta cio' che e' stabile, non lo stato del momento (spec §5).

Misurato il 29/09/2026: la #18 («come sta la casa») e' stata risposta SENZA
strumenti e SBAGLIATA su tutte e due le strade, prendendo per buona la
fotografia di «Notevole adesso».
"""
from tests.test_briefing import _CASA, _COMPORTAMENTO, _RICORDI, _STATO, compose


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
    `DEFAULT_CAP = 4000` -- VERDE. Diciassette nomi corti su una casa di
    quattro entita' pesano meno di mille caratteri: nessun tetto di quelli
    provati li tocca, e l'ordine del taglio non si vede. La prova che quella
    mutazione fa davvero arrossire e' la seguente."""
    comportamento = [{"id": f"automation.a{i}", "tipo": "automazione",
                      "nome": f"Automazione {i}"} for i in range(17)]
    testo, _ = compose(_CASA, comportamento, _RICORDI, _STATO)
    assert all(f"automation.a{i}" in testo for i in range(17))


def test_il_nucleo_non_dice_piu_cosa_si_puo_chiedere_alle_cose():
    """«Cosa si può chiedere alle cose di casa» e' uscita il 25/10/2026 (Fase
    2 dello sprint «Il giro snello», decisione di Paolo): sulla casa vera il
    taglio la riduceva gia' alla sola intestazione, e le capacita' di
    un'entita' le da' `search` nel dettaglio. Con lei e' uscito dal taglio il
    suo avviso («cosa sanno fare»).

    Mutazione ESEGUITA: rimessa in `print_order` una sezione
    `("## Cosa si può chiedere alle cose di casa", ["- 150 luci"])` -- rossa."""
    from hiris.app.proxy.entity_cache import CAPABILITIES

    luci = [{"id": f"light.l{n}", "nome": f"L{n}", "area_id": "sala",
             "dispositivo_id": None, "classe": None, "unita": None,
             "disabilitata": 0} for n in range(150)]
    casa = dict(_CASA, entita=_CASA["entita"] + luci)
    attributi = {f"light.l{n}": {CAPABILITIES: {"effect_list": [f"effetto{n}"]}}
                 for n in range(150)}
    testo, riepilogo = compose(casa, _COMPORTAMENTO, _RICORDI, _STATO,
                               attributes=attributi, cap=100_000)
    assert "Cosa si può chiedere" not in testo
    assert "cosa sanno fare" not in " ".join(riepilogo["notices"])


def test_il_tetto_di_default_e_quello_che_compose_usa_davvero():
    """Un default dichiarato in una costante e non usato nella firma sarebbe
    una decisione scritta due volte. Portata qui il 25/10/2026 da
    `test_briefing_capabilities.py`, uscito con la sezione.

    Mutazione ESEGUITA: `cap: int = 6000` nella firma di `compose()` -- rossa."""
    import inspect

    from hiris.app.home_space import briefing

    assert (inspect.signature(briefing.compose).parameters["cap"].default
            == briefing.DEFAULT_CAP)


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
    testo, _ = compose(_CASA, comportamento, _RICORDI, _STATO, cap=3000)
    assert 'search(genere="automazione")' in testo or "genere=automazione" in testo


def test_gaps_mention_search():
    """Mutazione ESEGUITA: aggiungere «`view`» all'avviso dei corpi mancanti
    -- rossa. (Verde gia' prima di questa fetta: il Task 5 aveva riscritto i
    testi che nominavano `view`; la prova tiene la porta chiusa.)"""
    testo, _ = compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)
    assert "`view`" not in testo


def test_senza_area_dice_il_totale_e_come_chiederle():
    """«Senza area» non e' la mappa, e' cio' che sta fuori: dal 25/10/2026 il
    nucleo ne dice il totale e come ritrovarle (`search` con l'id della
    pseudo-area, che `_place_matches` riconosce), non i conti per tipo.

    Mutazione ESEGUITA: tolto il ramo `is_pseudo_area` in `_home_space_lines`
    -- rossa (tornano «2 luci, 1 sensore»)."""
    fuori = [{"id": f"light.fuori{n}", "nome": f"F{n}", "area_id": None,
              "dispositivo_id": None, "classe": None, "unita": None,
              "disabilitata": 0} for n in range(2)]
    fuori.append({"id": "sensor.fuori", "nome": "S", "area_id": None,
                  "dispositivo_id": None, "classe": None, "unita": None,
                  "disabilitata": 0})
    casa = dict(_CASA, entita=_CASA["entita"] + fuori)
    testo, _ = compose(casa, _COMPORTAMENTO, _RICORDI, _STATO)
    riga = next(r for r in testo.splitlines() if "Senza area" in r)
    assert "3 entità" in riga and "«__senza_area__»" in riga, riga
    assert "luci" not in riga and "sensor" not in riga, riga


def test_l_id_che_il_nucleo_suggerisce_search_lo_ritrova():
    """Il suggerimento della riga qui sopra e' vero solo se la selezione di
    `search` lo capisce: si chiede alla casa, non si suppone. Ritrova le tre
    di «Senza area» e nessun'altra.

    Mutazione ESEGUITA: in `_place_matches` confrontato solo il nome
    dell'area (non l'id) -- rossa, zero righe."""
    from hiris.app.home_space.house import House
    from hiris.app.home_space.house_query import HouseFilters
    from hiris.app.home_space.topology import Mirror

    fuori = [{"id": f"light.fuori{n}", "nome": f"F{n}", "area_id": None,
              "dispositivo_id": None, "classe": None, "unita": None,
              "disabilitata": 0} for n in range(3)]
    casa = dict(_CASA, entita=_CASA["entita"] + fuori)
    house = House(casa, Mirror(state=_STATO, attributes={}), ())
    scelte = house.select(HouseFilters(area="__senza_area__"), ("entita",), None,
                          now=0.0).entities
    assert sorted(entry["id"] for entry, _a, _w in scelte) == [
        "light.fuori0", "light.fuori1", "light.fuori2"]
