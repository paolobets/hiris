"""Il nucleo dice cosa si puo' CHIEDERE alle cose di casa.

Fino alla 3.23.0 HIRIS sapeva rispondere che l’Alberello fa colore fra 1500 e
9000 K, ma **solo se il modello guardava quell’entita'**: il nucleo -- il testo
che il modello ha davanti a ogni messaggio -- non portava niente delle
capacita'. Sapeva rispondere, e non sapeva **di poter chiedere**.

I numeri di questo file sono misurati sulla casa vera l'08/09/2026 (841
entita'): 19 firme di capacita' distinte per 1.096 caratteri, ridotte dal
tetto della sezione a **12 firme e 671 caratteri**, che coprono 196 entita'
su 205. Il tetto del nucleo era 6.000 e ne erano gia' occupati 5.676, con un
taglio gia' in corso: e' il vincolo che ha deciso la forma di questa sezione.
**Dall'08/09/2026 il tetto e' 6.800** (`briefing.DEFAULT_CEILING`), deciso dal
proprietario proprio perche' a 6.000 questa sezione sfrattava «Notevole
adesso» per intero -- vedi in fondo a questo file la prova che lo pinna.
La suite gira senza la casa: qui gli attributi sono quelli letti allora,
ridotti ai casi che decidono.
"""
from hiris.app.home_space import briefing
from hiris.app.home_space.briefing import compose
from hiris.app.proxy.entity_cache import CAPABILITIES, UNINTERPRETED, VALUES
from tests._house_translations import house_translations

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


# ---------------------------------------------------------------------------
# IL TETTO: cosa il numero compra, misurato sulla casa vera
# ---------------------------------------------------------------------------
#
# La casa qui sotto e' la casa del proprietario in miniatura, e le sue
# proporzioni non sono scelte a occhio: 26 aree, 156 luci di cui quattro
# accese, 36 automazioni, una firma di capacita' diversa per ogni luce. Con
# queste, il nucleo pesa 6.178 caratteri -- fra i due tetti che questa prova
# confronta -- e si comporta come si comporta quello vero:
#
#   a 6.000  «Notevole adesso» resta la sola intestazione (4 elementi fuori)
#            e quattro automazioni su 36 non entrano;
#   a 6.800  entrambe intere, la mappa delle capacita' pure, nessun taglio.
#
# Sulla casa vera, ricomposta in locale sugli ingressi veri l'08/09/2026:
# a 6.000 «Notevole adesso» passava da quattro righe a ZERO e sette voci di
# comportamento su venti restavano fuori; a 6.800 «Notevole adesso» sale a sei
# righe e il comportamento esce completo (20 su 20).

_AREE_TETTO = 26
_LUCI_TETTO = 156
_AUTOMAZIONI_TETTO = 36

_CASA_TETTO = {
    "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
    "aree": [{"id": f"area{n}", "nome": f"Stanza numero {n}", "piano_id": "terra",
              "alias": [], "etichette": []} for n in range(_AREE_TETTO)],
    "dispositivi": [],
    "entita": [{"id": f"light.luce{n}", "nome": f"Luce {n}",
                "area_id": f"area{n % _AREE_TETTO}", "dispositivo_id": None,
                "classe": None, "unita": None, "disabilitata": 0}
               for n in range(_LUCI_TETTO)],
    "etichette": [], "categorie": [], "integrazioni": [],
}
_STATO_TETTO = {f"light.luce{n}": ("on" if n < 4 else "off")
                   for n in range(_LUCI_TETTO)}
_ATTRIBUTI_TETTO = {f"light.luce{n}": {CAPABILITIES: {"effect_list": [f"effetto{n}"]}}
                       for n in range(_LUCI_TETTO)}
_COMPORTAMENTO_TETTO = [
    {"id": f"automation.automazione_numero_{i}", "tipo": "automazione",
     "nome": f"Automazione numero {i} con un nome di lunghezza realistica",
     "corpo": {"trigger": []}, "origine": "file"}
    for i in range(_AUTOMAZIONI_TETTO)]


def _nucleo_tetto(ceiling=None):
    extra = {} if ceiling is None else {"ceiling": ceiling}
    # Le traduzioni ci sono: questa misura riguarda il TETTO, e un nucleo che
    # dichiara «traduzioni non lette» porterebbe una riga in piu' che non
    # c'entra niente col taglio -- e la falserebbe di un rigo.
    return compose(_CASA_TETTO, _COMPORTAMENTO_TETTO, [], _STATO_TETTO,
                   attributes=_ATTRIBUTI_TETTO,
                   translations=house_translations(), **extra)


def test_a_seimila_le_capacita_sfrattavano_notevole_adesso_per_intero():
    """La misura che ha fatto alzare il tetto, e sta qui perche' il numero
    nuovo si legga insieme a cio' che il vecchio costava.

    Non e' una prova sul passato: e' l'oracolo dell'altra. Senza di lei, la
    prova qui sotto passerebbe anche su una casa che al tetto vecchio ci
    stava comoda -- e non direbbe piu' niente sul tetto.
    """
    testo, riepilogo = _nucleo_tetto(ceiling=6000)
    assert riepilogo["truncated"] is True
    notevole = _sezione(testo, "## Notevole adesso").splitlines()
    assert notevole[1:] == [], (
        "a 6.000 «Notevole adesso» deve restare la sola intestazione: "
        f"invece porta {len(notevole) - 1} righe")
    automazioni = _sezione(testo, "## Cio' che la casa fa gia'").splitlines()[1:]
    assert len(automazioni) < _AUTOMAZIONI_TETTO


def test_al_tetto_di_adesso_notevole_adesso_e_il_comportamento_restano_interi():
    """**Il tetto di default e' 6.800, e questa prova dice cosa compra.**
    Senza chiamante che lo sovrascriva, e' questo numero a decidere quanto il
    modello sa della casa a ogni turno.

    Mutazione ESEGUITA: `DEFAULT_CEILING = 6000` in `briefing.py` --
    «Notevole adesso» torna a zero righe e la prova arrossisce su
    `assert 0 == 4`.
    """
    testo, riepilogo = _nucleo_tetto()
    notevole = _sezione(testo, "## Notevole adesso").splitlines()[1:]
    assert len(notevole) == 4, (
        "al tetto di adesso le quattro luci accese devono entrare tutte: "
        f"ne sono entrate {len(notevole)}")
    automazioni = _sezione(testo, "## Cio' che la casa fa gia'").splitlines()[1:]
    assert len(automazioni) == _AUTOMAZIONI_TETTO
    assert "## Cosa si puo' chiedere" in testo
    assert riepilogo["truncated"] is False


def test_il_tetto_di_default_e_quello_che_compose_usa_davvero():
    """Un default dichiarato in una costante e non usato nella firma sarebbe
    una decisione scritta due volte, e la seconda potrebbe restare indietro.

    Mutazione ESEGUITA: rimettere `ceiling: int = 6000` nella firma di
    `compose()` lasciando `DEFAULT_CEILING = 6800` -- i due testi divergono e
    la prova arrossisce.
    """
    predefinito, _ = _nucleo_tetto()
    esplicito, _ = _nucleo_tetto(ceiling=briefing.DEFAULT_CEILING)
    assert predefinito == esplicito


# ---------------------------------------------------------------------------
# R1 (revisione del tratto v3.23.0..HEAD, 08/09/2026): la sezione conta
# l'ANAGRAFE, non lo specchio intero della cache -- «la casa» e «cosa si puo'
# chiedere» devono raccontare lo stesso numero per la stessa parola.
# ---------------------------------------------------------------------------

_CASA_R1 = {
    "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
    "aree": [{"id": "sala", "nome": "Sala da pranzo", "piano_id": "terra",
              "alias": [], "etichette": []}],
    "dispositivi": [],
    "entita": [
        {"id": "light.visibile", "nome": "Visibile", "area_id": "sala",
         "dispositivo_id": None, "classe": None, "unita": None, "disabilitata": 0},
        # La nascosta: presente in anagrafe, tolta dalle viste dall'utente.
        {"id": "light.nascosta", "nome": "Nascosta", "area_id": "sala",
         "dispositivo_id": None, "classe": None, "unita": None, "disabilitata": 0,
         "nascosta": 1},
        # La `diagnostic`: entita' di servizio, stessa regola delle nascoste.
        {"id": "number.config", "nome": "Soglia", "area_id": "sala",
         "dispositivo_id": None, "classe": None, "unita": None, "disabilitata": 0,
         "categoria": "diagnostic"},
    ],
    "etichette": [], "categorie": [], "integrazioni": [],
}
_STATO_R1 = {"light.visibile": "off", "light.nascosta": "off", "number.config": "5"}
_ATTRIBUTI_R1 = {
    "light.visibile": {CAPABILITIES: {"supported_color_modes": ["onoff"]}},
    "light.nascosta": {CAPABILITIES: {"supported_color_modes": ["onoff"]}},
    "number.config": {CAPABILITIES: {"min": 0, "max": 10, "step": 1}},
    # La terza forma del difetto: presente SOLO in cache, mai arrivata
    # nell'anagrafe (o rimossa da Home Assistant fra una lettura e l'altra).
    "light.solo_cache": {CAPABILITIES: {"supported_color_modes": ["onoff"]}},
}


def test_r1_la_sezione_conta_come_la_casa_non_come_lo_specchio_della_cache():
    """R1 (revisione del tratto v3.23.0..HEAD): prima di questa correzione
    `_capability_lines` iterava lo specchio INTERO della cache
    (`topology.live_mirror`) senza ricevere l'anagrafe -- contava una luce
    nascosta, una luce presente solo in cache e le capacita' di un'entita' di
    servizio (`categoria: diagnostic`) che «La casa» e «Notevole adesso» non
    considerano. Sulla casa vera: quattro luci nascoste in piu' in sala da
    pranzo e 113 `config` + 66 `diagnostic` in tutta la casa -- lo stesso
    testo dava due totali diversi per la stessa parola, tre sezioni piu'
    sotto ("1 luce" in «La casa», "3 luci" in «Cosa si puo' chiedere»).

    **Questa casa ha una nascosta e una `diagnostic`** (spec della
    revisione): la prova verifica che «La casa» e «Cosa si puo' chiedere»
    concordino sul numero di luci -- una sola, la visibile -- e che
    l'entita' di servizio non compaia affatto nella sezione delle capacita'.

    Mutazione ESEGUITA: in `_capability_lines`, rimuovere il filtro `if
    entity_id not in visible_entity_ids: continue` -- la sezione torna a
    contare 3 luci (visibile + nascosta + solo-cache) invece di 1, e il
    numero `diagnostic` vi ricompare: la prova arrossisce su entrambe le
    asserzioni.
    """
    testo, _ = compose(_CASA_R1, [], [], _STATO_R1, attributes=_ATTRIBUTI_R1)
    assert "Sala da pranzo (id: sala): 1 luce, 1 numero" in _sezione(testo, "## La casa")
    sezione = _sezione(testo, "## Cosa si puo' chiedere")
    # Concordanza: la STESSA "1 luce" che dice «La casa» -- non le tre della
    # cache (visibile + nascosta + solo-cache).
    assert sezione.splitlines()[1:] == ["- 1 luce: supported_color_modes=[onoff]"]
    # L'entita' di servizio non compare affatto: le sue capacita' non sono
    # "cio' che si puo' chiedere" in un digesto che non la annuncia.
    assert "numero" not in sezione


def test_r1_mutazione_senza_il_filtro_dell_anagrafe_i_due_totali_divergono():
    """La stessa prova al CONTRARIO, per mostrare il rosso che la correzione
    ha chiuso -- non un doppione della prova sopra: qui si ricostruisce a
    mano il conteggio non filtrato (esattamente cio' che `_capability_lines`
    faceva prima di R1) e si dimostra che diverge da «La casa».

    Mutazione DICHIARATA e ESEGUITA dal vivo durante lo sviluppo di questa
    correzione (vedi il rapporto della fetta): rimuovere il filtro in
    `_capability_lines` faceva **arrossire**
    `test_r1_la_sezione_conta_come_la_casa_non_come_lo_specchio_della_cache`
    esattamente cosi': `sezione.splitlines()[1:]` diventava
    `["- 3 luci: supported_color_modes=[onoff]", "- 1 numero: min, max, step"]`
    contro l'"1 luce, 1 numero" di «La casa» -- due totali diversi per
    "luce" nello stesso testo. Il file e' stato ripristinato riscrivendolo
    (mai `git checkout`), e la prova sopra e' quella che resta a
    dimostrarlo in CI.
    """
    conteggio_grezzo = {}
    for entity_id, baskets in _ATTRIBUTI_R1.items():
        capabilities = baskets.get(CAPABILITIES)
        if not capabilities:
            continue
        from hiris.app.home_space.topology import domain_of
        conteggio_grezzo[domain_of(entity_id)] = conteggio_grezzo.get(domain_of(entity_id), 0) + 1
    assert conteggio_grezzo == {"light": 3, "number": 1}, (
        "l'oracolo di questa prova: senza filtro dell'anagrafe la cache "
        "porta 3 luci e 1 numero, non 1 e 1 come «La casa»")


# ---------------------------------------------------------------------------
# R2 (revisione del tratto v3.23.0..HEAD, 08/09/2026): il rinvio "altre N
# entita'..." o sopravvive al taglio, o il suo peso entra nell'avviso -- mai
# nessuno dei due.
# ---------------------------------------------------------------------------

def _attributi_firme_rare(n):
    """`n` luci, `n` firme di capacita' DISTINTE: ognuna rara per costruzione,
    cosi' il tetto interno della sezione (`_CAPABILITY_SECTION_BUDGET`) lascia
    fuori un `left_out` misurabile con un solo rinvio a coda."""
    return {f"light.luce{i}": {CAPABILITIES: {"effect_list": [f"effetto_raro_{i}"]}}
            for i in range(n)}


_AREE_R2 = [{"id": f"area{n}", "nome": f"Stanza {n}", "piano_id": "terra",
             "alias": [], "etichette": []} for n in range(12)]
_CASA_R2 = {
    "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
    "aree": _AREE_R2,
    "dispositivi": [],
    "entita": [_luce(n, f"area{n % 12}") for n in range(60)],
    "etichette": [], "categorie": [], "integrazioni": [],
}
_STATO_R2 = {f"light.luce{n}": "off" for n in range(60)}


def test_r2_il_rinvio_ha_peso_e_l_avviso_non_sottostima_quando_cade():
    """R2 (revisione del tratto v3.23.0..HEAD): la riga «(altre N entita' con
    capacita' rare non elencate qui...)» stava in CODA con peso ZERO. Il
    taglio del nucleo (`_pop`) morde dalla coda, quindi con un tetto stretto
    quella riga era la PRIMA a cadere -- e con peso zero cadeva senza far
    salire `excluded_per_pool["capacita"]`: le entita' che dichiarava
    sparivano da ogni conteggio, testo e avviso insieme.

    **La prova**: 60 firme rare (una per luce) producono un `left_out`
    interno alla sezione; un tetto abbastanza stretto da mordere anche il
    pool "capacita'" dall'esterno fa cadere ulteriori firme vere. L'avviso
    finale deve contare TUTTE le entita' senza capacita' dichiarate --
    quelle gia' fuori dal budget interno della sezione PIU' quelle cadute nel
    taglio esterno -- non solo le seconde.

    Mutazione ESEGUITA: in `_capability_lines`, tornare a `weights.append(0)`
    per la riga di rinvio -- l'avviso torna a contare solo le firme cadute
    nel taglio ESTERNO, sottostimando il totale vero, e questa prova
    arrossisce sul confronto fra l'avviso e il totale delle luci senza una
    firma superstite.
    """
    attributi = _attributi_firme_rare(60)
    # Tetto stretto: abbastanza per un pugno di firme, non per tutte e 60.
    testo, riepilogo = compose(_CASA_R2, [], [], _STATO_R2, ceiling=1300,
                               attributes=attributi)
    assert riepilogo["truncated"] is True
    sezione = _sezione(testo, "## Cosa si puo' chiedere")
    firme_superstiti = [riga for riga in sezione.splitlines()[1:]
                        if riga.startswith("- ") and "effetto_raro_" in riga]
    n_superstiti = len(firme_superstiti)
    # Il rinvio puo' essere sopravvissuto o no: in ENTRAMBI i casi l'avviso
    # deve dire quante luci restano senza una firma nel testo.
    attese_orfane = 60 - n_superstiti
    avvisi = " ".join(riepilogo["notices"])
    numeri_avviso = [int(tok) for tok in avvisi.replace(".", " ").split()
                          if tok.isdigit()]
    assert attese_orfane in numeri_avviso, (
        f"l'avviso di taglio non nomina {attese_orfane} (le luci senza "
        f"una firma nel testo, su 60): {avvisi!r}")


def test_r2_il_rinvio_sopravvive_quando_non_serve_tagliare_oltre():
    """Cio' che NON deve rompersi: quando il tetto ESTERNO non morde piu' il
    pool "capacita'" (ci sta la sezione col suo taglio interno, non oltre),
    il rinvio resta nel testo con la stessa cifra di prima -- il peso nuovo
    non lo rende piu' fragile, perche' un peso non nullo non lo fa cadere
    prima: lo fa contare correttamente SE cade."""
    attributi = _attributi_firme_rare(60)
    testo, riepilogo = compose(_CASA_R2, [], [], _STATO_R2, attributes=attributi)
    sezione = _sezione(testo, "## Cosa si puo' chiedere")
    assert "non elencate qui" in sezione
    assert riepilogo["truncated"] is False
