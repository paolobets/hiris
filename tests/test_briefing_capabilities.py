"""Il nucleo dice cosa si puo' CHIEDERE alle cose di casa.

Fino alla 3.23.0 HIRIS sapeva rispondere che l’Alberello fa colore fra 1500 e
9000 K, ma **solo se il modello guardava quell’entita'**: il nucleo -- il testo
che il modello ha davanti a ogni messaggio -- non portava niente delle
capacita'. Sapeva rispondere, e non sapeva **di poter chiedere**.

I numeri di questo file sono misurati sulla casa vera l'08/09/2026 (841
entita'): 19 firme di capacita' distinte per 1.096 caratteri, ridotte dal
tetto della sezione a **12 firme e 671 caratteri**, che coprono 196 entita'
su 205. Il tetto del nucleo e' 6.000 e ne erano gia' occupati 5.676, con un
taglio gia' in corso: e' il vincolo che decide la forma di questa sezione.
La suite gira senza la casa: qui gli attributi sono quelli letti allora,
ridotti ai casi che decidono.
"""
from hiris.app.home_space import briefing
from hiris.app.home_space.briefing import compose
from hiris.app.proxy.entity_cache import CAPABILITIES, UNINTERPRETED, VALUES

_PIANI = [{"id": "terra", "nome": "Piano terra", "livello": 0}]

# Dodici aree: abbastanza perche' il tetto morda davvero, come morde sulla casa
# vera (20 aree, e il nucleo tronca).
_AREE = [{"id": f"area{n}", "nome": f"Stanza {n}", "piano_id": "terra",
          "alias": [], "etichette": []} for n in range(12)]


def _luce(n, area):
    return {"id": f"light.luce{n}", "nome": f"Luce {n}", "area_id": area,
            "dispositivo_id": None, "classe": None, "unita": None, "disabilitata": 0}


_CASA = {
    "piani": _PIANI,
    "aree": _AREE,
    "dispositivi": [],
    "entita": [_luce(n, f"area{n % 12}") for n in range(48)],
    "etichette": [], "categorie": [], "integrazioni": [],
}
_STATO = {f"light.luce{n}": "off" for n in range(48)}

# Le ceste che `entity_cache.inherited_attributes` produce davvero: le
# capacita' da una parte, i valori correnti dall'altra, il non interpretato in
# una cesta sua.
_SOLO_ACCESO_SPENTO = {CAPABILITIES: {"supported_color_modes": ["onoff"]}}
_CAPACITA_COLORE = {
    CAPABILITIES: {"supported_color_modes": ["color_temp", "hs"],
                   "min_color_temp_kelvin": 1500, "max_color_temp_kelvin": 9000,
                   "effect_list": ["effect_colorloop", "effect_pulse", "effect_stop"]},
    VALUES: {"brightness": 180, "color_temp_kelvin": 2700},
    UNINTERPRETED: {"ave_window_state": "closed"},
}


def _attributi(colorate=4):
    """48 luci: `colorate` sanno fare colore, le altre solo acceso/spento."""
    return {f"light.luce{n}": (_CAPACITA_COLORE if n < colorate else _SOLO_ACCESO_SPENTO)
            for n in range(48)}


def _attributi_tutti_diversi():
    """48 luci, 48 firme distinte: la casa che fa MORDERE il tetto.

    Non e' un caso di laboratorio -- e' la forma della casa vera vista da
    vicino: 19 firme per 841 entita', e le firme rare (una entita' a testa)
    sono la meta' dell'elenco. Serve qui perche' con due sole firme il taglio
    non scatta mai, e una prova sul taglio che non fa tagliare niente non
    dimostra niente.
    """
    return {f"light.luce{n}": {CAPABILITIES: {"effect_list": [f"effetto{n}"]}}
            for n in range(48)}


def _sezione(testo, titolo):
    for blocco in testo.split("\n\n"):
        if blocco.startswith(titolo):
            return blocco
    return ""


def _righe_area(testo):
    return [riga for riga in _sezione(testo, "## La casa").split("\n")
            if riga.startswith("  - Stanza")]


# ---------------------------------------------------------------------------
# LA MAPPA: si conta, non si elenca -- e il modello sa di poter chiedere
# ---------------------------------------------------------------------------

def test_il_nucleo_dice_che_in_questa_casa_qualcosa_sa_fare_colore():
    """La differenza che questa sezione esiste per fare: «in questa casa
    quattro luci sanno fare colore» sta nel nucleo, «l’Alberello arriva a
    9000 K» resta in `view`.

    Mutazione ESEGUITA: togliere `capability_section` da `print_order` in
    `compose()` -- la sezione sparisce e la prova arrossisce su
    `"color_temp" in testo`.
    """
    testo, _ = compose(_CASA, [], [], _STATO, attributes=_attributi())
    sezione = _sezione(testo, "## Cosa si puo' chiedere")
    assert "4 luci" in sezione
    assert "supported_color_modes=[color_temp, hs]" in sezione
    assert "44 luci: supported_color_modes=[onoff]" in sezione


def test_una_firma_aggregata_e_mappa_non_dettaglio():
    """**I valori numerici non entrano** (spec §15.1): il NOME del limite dice
    «di questa luce si puo' cambiare la temperatura», il numero e' cio' che
    `view` dice quando la si guarda. Scriverlo qui costerebbe il doppio
    (2.497 caratteri contro 1.096, misurati) per un’informazione che ha gia'
    una porta sua.

    Mutazione ESEGUITA: far tornare a `_capability_value` `str(value)` anche
    per i valori non elencabili -- `9000` compare nel nucleo e la prova
    arrossisce.
    """
    testo, _ = compose(_CASA, [], [], _STATO, attributes=_attributi())
    sezione = _sezione(testo, "## Cosa si puo' chiedere")
    assert "min_color_temp_kelvin" in sezione      # il nome: e' la mappa
    assert "9000" not in sezione                   # il valore: e' il dettaglio
    assert "1500" not in sezione


def test_i_valori_correnti_e_il_non_interpretato_restano_fuori():
    """Il nucleo continua a non portare **nessun attributo grezzo**: le
    capacita' collassano in 19 firme, i valori no -- `brightness` e'
    diverso per ogni luce accesa, per definizione.

    Mutazione ESEGUITA: in `_capability_lines`, leggere
    `entity_cache.disclosable_attributes(baskets)` invece della sola cesta
    `CAPABILITIES` -- `brightness` e `ave_window_state` entrano nel nucleo e
    la prova arrossisce.
    """
    testo, _ = compose(_CASA, [], [], _STATO, attributes=_attributi())
    assert "brightness" not in testo
    assert "ave_window_state" not in testo


def test_il_nucleo_conta_le_entita_e_non_le_nomina():
    """Quarantotto luci in due righe. Gli `entity_id` non ci stanno, qui come
    in «La casa»."""
    testo, _ = compose(_CASA, [], [], _STATO, attributes=_attributi())
    sezione = _sezione(testo, "## Cosa si puo' chiedere")
    assert "light.luce0" not in sezione
    assert len(sezione.split("\n")) == 3          # intestazione + due firme


# ---------------------------------------------------------------------------
# LA STABILITA': e' la parte del contesto che si rilegge dalla cache
# ---------------------------------------------------------------------------

def test_due_composizioni_della_stessa_casa_danno_lo_stesso_testo():
    """5,6 milioni di token riletti dalla cache contro 662 freschi su 105
    turni: cio' che si aggiunge al nucleo dev'essere STABILE, o quel rapporto
    peggiora. Gli attributi arrivano in ordine diverso -- come arrivano da due
    integrazioni diverse -- e la firma dev'essere la stessa.

    Mutazione ESEGUITA: togliere `sorted` da `_capability_signature` -- le due
    composizioni divergono e la prova arrossisce.
    """
    dritto = _attributi()
    rovescio = {
        entity_id: {cesta: dict(reversed(list(contenuto.items())))
                    for cesta, contenuto in ceste.items()}
        for entity_id, ceste in dritto.items()
    }
    primo, _ = compose(_CASA, [], [], _STATO, attributes=dritto)
    secondo, _ = compose(_CASA, [], [], _STATO, attributes=rovescio)
    assert primo == secondo


def test_a_parita_di_conteggio_l_ordine_non_e_quello_dell_hash():
    """Due firme con lo stesso numero di entita' devono uscire sempre nello
    stesso ordine, o il testo balla senza che la casa sia cambiata.

    Mutazione ESEGUITA: in `_capability_lines`, ordinare per `-count` soltanto
    -- l'ordine diventa quello di inserimento del dizionario e la prova
    arrossisce sulle due composizioni con le chiavi inserite al contrario.
    """
    prima = {f"light.luce{n}": ({CAPABILITIES: {"effect_list": ["a"]}} if n % 2
                                else {CAPABILITIES: {"effect_list": ["b"]}})
             for n in range(48)}
    dopo = {entity_id: prima[entity_id] for entity_id in reversed(list(prima))}
    primo, _ = compose(_CASA, [], [], _STATO, attributes=prima)
    secondo, _ = compose(_CASA, [], [], _STATO, attributes=dopo)
    assert primo == secondo


# ---------------------------------------------------------------------------
# IL TETTO: le capacita' non costano mai un'area
# ---------------------------------------------------------------------------

def test_con_le_firme_dentro_il_nucleo_non_perde_nemmeno_un_area():
    """**Il vincolo che decide la forma.** Il nucleo tronca gia' oggi -- il
    codice lo dichiara misurandolo: «citando tutti i nomi sopravvivono 7 aree
    su 20 invece di 17». Un nucleo che guadagna le capacita' e perde la mappa
    delle stanze e' un peggioramento, e questa prova lo rende impossibile.

    Le capacita' stanno nell'ordine di taglio PRIMA della casa: si esauriscono
    per intero prima che una riga di conteggio venga toccata.

    Mutazione ESEGUITA: in `compose()`, spostare la voce `("capacita", ...)` di
    `cut_order` DOPO quella `("casa", ...)` -- a tetto stretto le aree
    scendono da 12 a 3 (la riserva) e la prova arrossisce.
    """
    senza, _ = compose(_CASA, [], [], _STATO, ceiling=1100)
    con, riepilogo = compose(_CASA, [], [], _STATO, ceiling=1100,
                             attributes=_attributi_tutti_diversi())
    assert len(_righe_area(senza)) == 12, (
        "questa prova presuppone che senza le capacita' le aree ci stiano tutte")
    assert _righe_area(con) == _righe_area(senza)
    # E il tetto ha morso davvero: se non avesse tagliato niente, questa prova
    # non starebbe dimostrando nulla.
    assert riepilogo["truncated"] is True


def test_se_il_tetto_morde_il_nucleo_lo_DICE_invece_di_tacere():
    """Un taglio in silenzio e' un HIRIS che crede di sapere. Quando le
    capacita' non ci stanno, il nucleo dichiara **quante entita'** restano
    senza -- non quante righe, che non direbbe niente a chi legge.

    Mutazione ESEGUITA: togliere la voce `("capacita", ...)` da `cut_labels`
    in `compose()` -- il taglio avviene lo stesso e nessuna frase lo dichiara;
    la prova arrossisce sull'avviso.
    """
    _, riepilogo = compose(_CASA, [], [], _STATO, ceiling=900,
                           attributes=_attributi())
    assert riepilogo["truncated"] is True
    avvisi = " ".join(riepilogo["notices"])
    assert "cosa sanno fare" in avvisi or "cosa sa fare" in avvisi


def test_la_sezione_ha_un_tetto_suo_e_dichiara_cio_che_ci_lascia_fuori():
    """Senza un tetto suo, una casa con molte firme RARE mangerebbe lo spazio
    di tutto il resto per elencare capacita' che riguardano una entita' a
    testa -- il contrario di cio' per cui questa sezione esiste, che e' la
    mappa.

    Mutazione ESEGUITA: alzare `_CAPABILITY_SECTION_BUDGET` a 100000 (togliere il tetto) -- la
    sezione elenca tutte e 300 le firme e la prova arrossisce sul rinvio a
    `view`.
    """
    tante = {f"light.luce{n}": {CAPABILITIES: {"effect_list": [f"effetto{n}"]}}
             for n in range(300)}
    testo, _ = compose(_CASA, [], [], _STATO, ceiling=100000, attributes=tante)
    sezione = _sezione(testo, "## Cosa si puo' chiedere")
    assert len(sezione) <= briefing._CAPABILITY_SECTION_BUDGET + 200
    assert "non elencate qui" in sezione
    assert "`view`" in sezione


# ---------------------------------------------------------------------------
# I SILENZI DEL NUCLEO: «non ho guardato» non e' «non c’e' niente»
# ---------------------------------------------------------------------------

def test_senza_attributi_la_sezione_non_esiste_affatto():
    """`None` significa «il chiamante non ha guardato», ed e' l'unico caso in
    cui tacere non afferma niente -- la stessa regola gia' scritta per
    `problemi` e per `confronto`. Un’intestazione da sola direbbe «ho guardato
    e non c’e' niente», che e' l'altro fatto.

    Mutazione ESEGUITA: far tornare a `_capability_lines` una riga anche per
    `attributes is None` -- l'intestazione compare e la prova arrossisce.
    """
    testo, _ = compose(_CASA, [], [], _STATO)
    assert "Cosa si puo' chiedere" not in testo


def test_attributi_letti_e_vuoti_non_sono_attributi_non_letti():
    """Letto, e nessuna entita' dichiara un campo di manovra: si DICE. E' il
    fatto opposto a quello di sopra, e non deve produrre la stessa risposta.

    Mutazione ESEGUITA: far tornare `([], [], False)` anche per un dizionario
    vuoto -- i due casi collassano e la prova arrossisce.
    """
    testo, _ = compose(_CASA, [], [], _STATO, attributes={})
    assert "Nessuna entita' dichiara un campo di manovra." in testo


def test_a_stato_non_letto_le_capacita_si_dichiarano_e_non_si_tagliano():
    """Quando lo stato non e' stato letto, la sezione porta UNA riga -- la
    dichiarazione stessa di «non ho guardato». Metterla nel pool tagliabile la
    renderebbe la prima cosa a sparire, cioe' ricreerebbe esattamente il
    silenzio che dichiara.

    Mutazione ESEGUITA: in `compose()`, aggiungere la voce `("capacita", ...)`
    a `cut_order` incondizionatamente (senza
    `if capabilities_are_countable`) -- a tetto stretto la riga sparisce e la
    prova arrossisce.
    """
    testo, _ = compose(_CASA, [], [], _STATO, ceiling=900,
                       reliable_state=False, attributes=_attributi())
    assert "non si puo' dire cosa le cose di questa casa sanno fare" in testo
