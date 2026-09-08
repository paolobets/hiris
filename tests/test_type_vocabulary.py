"""Il vocabolario delle tipologie: cosa una cosa E', e cosa significano i suoi
valori.

`_STATI_NOTEVOLI` era un insieme di stringhe di stato CIECO alla tipologia: se
lo stato era in quel set, l'entita' era notevole. Sull'impianto vero produceva
**300 elementi su 845** -- 119 `unavailable`, 49 telefoni `home`, 18 automazioni
abilitate, 99 interruttori (di cui **90 dichiarati `config`/`diagnostic` da Home
Assistant**) -- e sopra i 15 elementi il dettaglio individuale sparisce.

Risultato misurato: HIRIS sapeva CHE due luci erano accese e non QUALI, ha speso
i dieci giri di strumento a cercarle stanza per stanza, e alla domanda «quali
luci sono accese» ha risposto «nessuna».

`_traduci_stato` prendeva GIA' la classe e la usava per porte e finestre
(`_CLASSI_APERTURA`: 5 classi sul totale che HA documenta). Il vocabolario era
nato e si era fermato li'. Queste prove lo finiscono.

**Vocabolario, non filtro.** Un filtro toglie e perde una capacita': escludere
`device_tracker` dal digesto vorrebbe dire non saper piu' rispondere a «chi e'
in casa?». Il vocabolario dice cosa una cosa e', e lascia decidere a chi legge.

Spec: docs/design/2026-08-16-il-vocabolario-delle-tipologie.md
"""
import pytest

from hiris.app.home_space import briefing, topology
from hiris.app.home_space.briefing import compose
from hiris.app.home_space.type_vocabulary import notable_types
from hiris.app.proxy import state_translations

# Le finte vivono gia' in `test_briefing.py`: si riusano invece di riscriverle.
# Due finte che fingono la stessa casa sono la seconda rappresentazione in
# miniatura, e divergono come tutte le seconde rappresentazioni.
from tests._house_translations import house_translations
from tests.test_briefing import _CASA, _COMPORTAMENTO, _RICORDI, _STATO


def _sezione_notevole(testo: str) -> str:
    return testo.split("## Notevole adesso")[1].split("## ")[0]


def _con(entita, stato_extra):
    casa = dict(_CASA, entita=_CASA["entita"] + entita)
    return compose(casa, _COMPORTAMENTO, _RICORDI, dict(_STATO, **stato_extra),
                   translations=house_translations())[0]


def _voce(eid, nome, **extra):
    base = {"id": eid, "nome": nome, "area_id": "sala", "dispositivo_id": None,
            "classe": None, "unita": None, "disabilitata": 0}
    base.update(extra)
    return base


# ── Cosa significano i valori: la classe decide ────────────────────────────

def test_un_allagamento_si_legge_bagnato_e_non_acceso():
    """`moisture` acceso significa BAGNATO -- lo dichiara Home Assistant
    (developers.home-assistant.io/docs/core/entity/binary-sensor/), non lo
    indoviniamo noi. Scritto «acceso», un allagamento e' indistinguibile da una
    lampadina."""
    sezione = _sezione_notevole(_con(
        [_voce("binary_sensor.perdita", "Perdita bagno", classe="moisture")],
        {"binary_sensor.perdita": "on"}))
    assert "Perdita bagno" in sezione
    # La parola e' quella che Home Assistant pubblica per QUELLA classe
    # (`component.binary_sensor.entity_component.moisture.state.on`), non piu'
    # una tupla scritta a mano: dall'08/09/2026 `_CLASS_MEANING` non esiste.
    assert "Bagnato" in sezione
    assert "Perdita bagno (Acceso)" not in sezione


# I nomi-stringa VERI, dalla sorgente di Home Assistant
# (homeassistant/components/binary_sensor/__init__.py), non dalla pagina di
# documentazione -- che elenca i NOMI DELLE COSTANTI e non i valori.
# Tutte tranne una coincidono col nome in minuscolo. L'eccezione:
# `BinarySensorDeviceClass.CO = "carbon_monoxide"`.
#
# **Le parole non sono piu' nostre, dall'08/09/2026**: sono quelle che questa
# casa pubblica (`tests/_house_translations.py`, misurate). Nessuna di esse e'
# «Acceso», che e' la parola del DOMINIO: e' quello il difetto che questa prova
# sorveglia, e la classe e' cio' che lo evita.
_ALLARMI = [
    ("moisture", "Bagnato"),
    ("smoke", "Rilevato"),
    ("gas", "Rilevato"),
    ("carbon_monoxide", "Rilevato"),
    ("safety", "Non Sicuro"),
    ("tamper", "Rilevata manomissione"),
]


@pytest.mark.parametrize("classe,parola", _ALLARMI)
def test_ogni_classe_di_allarme_entra_nel_digesto_e_si_legge_in_parole(classe, parola):
    """TUTTE le classi d'allarme, non una campione.

    Trovato da una review indipendente su questa stessa fetta: `co` era scritto
    col nome della costante invece che col valore, quindi `carbon_monoxide` non
    combaciava con niente -- un allarme monossido non entrava nel digesto e non
    veniva tradotto. **La classe piu' critica dell'elenco, muta, e la suite
    verde.** Una prova su una sola classe campione non lo avrebbe visto: le
    altre ventisette funzionavano.
    """
    sezione = _sezione_notevole(_con(
        [_voce(f"binary_sensor.allarme_{classe}", f"Allarme {classe}", classe=classe)],
        {f"binary_sensor.allarme_{classe}": "on"}))
    assert f"Allarme {classe}" in sezione, (
        f"la classe {classe!r} non entra nel digesto: probabilmente non "
        f"combacia con nessuna voce di _CLASSI_EVENTO")
    assert f"({parola})" in sezione, (
        f"la classe {classe!r} entra ma non si rende con la parola della sua "
        f"classe: Home Assistant la pubblica, e senza di lei si leggerebbe "
        f"«Acceso», cioe' la parola del dominio")
    assert f"Allarme {classe} (Acceso)" not in sezione


def test_ogni_classe_di_evento_ha_anche_un_significato():
    """Ogni classe che entra nel digesto ha, in questa casa, la COPPIA
    acceso/spento pubblicata da Home Assistant -- non mezza.

    Fino all'08/09/2026 questa prova confrontava `briefing._EVENT_CLASSES` con
    `topology._CLASS_MEANING`, cioe' una nostra tabella con un'altra nostra
    tabella: diceva che due elenchi scritti a mano erano d'accordo, non che
    fossero veri. Adesso il metro e' la casa, e la coppia si RICOSTRUISCE (non
    si assume): una classe di cui HA pubblichi solo `on` si leggerebbe con una
    parola sua per l'acceso e con la parola del DOMINIO per lo spento -- due
    meta' di due tipi diversi presentate come un significato solo.

    Mutazione: togliere `component.binary_sensor.entity_component.smoke.state.off`
    dalle risorse -- questa prova nomina `smoke`."""
    risorse = house_translations()["risorse"]
    senza = sorted(
        classe for _, classe in classi_notevoli()
        if not state_translations.published_pair(
            risorse, domain="binary_sensor", device_class=classe).get("letto"))
    assert not senza, f"classi che entrano nel digesto senza la coppia: {senza}"


def test_un_movimento_NON_entra_nel_digesto():
    """La prova gemella della precedente, sullo STESSO dominio: senza,
    «filtrare per dominio» le lascerebbe passare o cadere entrambe. Un
    movimento e' vero per trenta secondi -- non e' cio' che la casa STA
    facendo, e' cio' che e' successo un attimo fa."""
    sezione = _sezione_notevole(_con(
        [_voce("binary_sensor.corridoio", "Movimento corridoio", classe="motion")],
        {"binary_sensor.corridoio": "on"}))
    assert "Movimento corridoio" not in sezione


def test_porte_e_finestre_si_leggono_ancora_aperto_e_chiuso():
    """`_CLASSI_APERTURA` non esiste piu': le sue cinque voci sono cinque righe
    della mappa dei significati. La prova che l'estensione ha ASSORBITO il caso
    particolare invece di affiancarlo -- che e' la differenza fra finire un
    vocabolario e aggiungergliene accanto un secondo."""
    assert not hasattr(briefing, "_CLASSI_APERTURA"), (
        "la tabella vecchia deve sparire, non restare accanto alla nuova")
    sezione = _sezione_notevole(compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                                        translations=house_translations())[0])
    assert "Porta" in sezione and "Aperto" in sezione


def test_a_valve_opening_or_closing_is_not_a_dumb_on_off():
    """`ValveState` (`components/valve/const.py`, tag 2026.9.1 -- verificato
    alla fonte) ha QUATTRO stati: `open`, `closed`, `opening`, `closing`.
    "open"/"closed" erano gia' tradotti in `_STATE_TRANSLATION`;
    "opening"/"closing" mancavano -- trovato durante la revisione del
    vocabolario importato (task "rifiutare e importare" §7②), che cercava
    un doppione con `topology._CLASS_MEANING` per il `valve` e ha trovato
    invece un buco vero: "quali stati ha un dominio", l'esempio letterale
    della spec, restava scoperto proprio li' (4 entita' `valve` su questa
    casa).

    Dall'08/09/2026 le parole le pubblica Home Assistant, e la prova e'
    diventata piu' forte di com'era: non verifica piu' che una nostra tabella
    abbia due voci, verifica che si stia chiedendo **al dominio giusto**.

    Mutazione: rendere `readable_state` cieca al dominio (cercare sempre la
    chiave di `light`) -- il test arrossisce, perche' `light` non pubblica
    nessun `opening`.
    """
    traduzioni = house_translations()
    assert topology.readable_state("opening", domain="valve",
                                   translations=traduzioni)["valore"] == "In apertura"
    assert topology.readable_state("closing", domain="valve",
                                   translations=traduzioni)["valore"] == "In chiusura"


def test_the_domain_decides_which_word_a_state_gets():
    """**Il difetto che ha fatto cancellare `_STATE_TRANSLATION`**: era cieca al
    dominio, e Home Assistant no.

    Due casi misurati su questa casa, e nessuno dei due e' inventato per la
    prova: `off` su un'entita' di aggiornamento si legge «Aggiornato», non
    «Spento»; `returning` su un aspirapolvere e' «Ritornando alla base», su un
    tosaerba «Ritornando». La tabella cancellata dava a tutti e quattro la
    stessa parola -- o nessuna.

    Mutazione: far cadere `readable_state` sul gradino del dominio sbagliato
    (per esempio cercare sempre `light`) -- tutte e quattro le asserzioni
    arrossiscono."""
    traduzioni = house_translations()

    def parola(stato, dominio):
        return topology.readable_state(stato, domain=dominio,
                                       translations=traduzioni)["valore"]

    assert parola("off", "update") == "Aggiornato"
    assert parola("off", "light") == "Spento"
    assert parola("returning", "vacuum") == "Ritornando alla base"
    assert parola("returning", "lawn_mower") == "Ritornando"


# ── Cio' che Home Assistant dichiara non primario ──────────────────────────

def test_un_entita_diagnostic_non_entra_qualunque_sia_il_suo_stato():
    """Il caso da 179 unita' su 300. Home Assistant DICHIARA che queste non
    sono primarie, e la sua documentazione dice che sono normalmente nascoste
    dalle viste principali. HIRIS legge gia' il campo (`home_space/store.py:135`)
    e il digesto lo ignorava."""
    sezione = _sezione_notevole(_con(
        [_voce("switch.led_stato", "LED di stato", categoria="diagnostic")],
        {"switch.led_stato": "on"}))
    assert "LED di stato" not in sezione


def test_un_entita_config_non_entra():
    sezione = _sezione_notevole(_con(
        [_voce("switch.ripeti", "Ripeti segnale", categoria="config")],
        {"switch.ripeti": "on"}))
    assert "Ripeti segnale" not in sezione


def test_service_entities_are_counted_even_when_not_announced():
    """Task 3 di «rifiutare e importare» (§7①): `entity_category` era gia'
    letto (`store.py:385`, e da questa stessa fetta anche da `_enrich_entity`,
    `queries.py`) ma nessun lettore lo metteva DAVANTI -- il digesto le
    escludeva in silenzio da «Notevole adesso» (le due prove sopra) senza mai
    dire QUANTE fossero. Stessa disciplina delle nascoste due sezioni sopra:
    «non le annuncio» e «non so che esistono» sono due cose diverse.

    Mutazione: non contare `service` (o non appenderlo a `notices`) -- il
    test torna rosso su
    `assert "2 entita' di servizio" in gaps` (`AssertionError`, la
    sottostringa non compare)."""
    entities, state = [], {}
    for i in range(2):
        entities.append(_voce(f"switch.servizio_{i}", f"Servizio {i}", categoria="diagnostic"))
        state[f"switch.servizio_{i}"] = "on"
    text = _con(entities, state)

    assert "Servizio 0" not in _sezione_notevole(text), (
        "il digesto rispetta la dichiarazione di Home Assistant")
    gaps = _sezione_lacune(text)
    assert "2 entita' di servizio" in gaps, (
        "ma il numero c'e', altrimenti la domanda «quante sono di servizio?» "
        "costerebbe una chiamata a `view` per ognuna")


def test_without_service_entities_nothing_is_said():
    """Un avviso che compare sempre non e' un avviso -- stessa lezione delle
    nascoste, stesso file.

    Mutazione: l'avviso "N entita' di servizio" reso incondizionato (fuori
    dall'`if service:` di `briefing.compose`) -- il test torna rosso su
    `assert "servizio" not in _sezione_lacune(...)` (compare "0 entita' di
    servizio...")."""
    assert "servizio" not in _sezione_lacune(
        compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)[0])


def test_un_entita_nascosta_dall_utente_non_entra():
    """E' una scelta esplicita dentro Home Assistant: rimetterla davanti da
    un'altra porta sarebbe disfarla."""
    sezione = _sezione_notevole(_con(
        [_voce("switch.roba", "Roba nascosta", nascosta=1)],
        {"switch.roba": "on"}))
    assert "Roba nascosta" not in sezione


# ── Condizioni travestite da eventi ────────────────────────────────────────

def test_un_automazione_abilitata_non_e_una_cosa_accesa():
    """Caso da 18 unita' sull'impianto vero. `on` su un'automazione significa
    ABILITATA: e' il riposo, non un'eccezione rispetto al riposo."""
    sezione = _sezione_notevole(_con(
        [_voce("automation.sveglia_2", "Sveglia infrasettimanale")],
        {"automation.sveglia_2": "on"}))
    assert "Sveglia infrasettimanale" not in sezione


def test_un_telefono_in_casa_non_e_un_evento_MA_guarda_lo_riporta():
    """LA DIFFERENZA FRA VOCABOLARIO E FILTRO, in una prova sola.

    Un `device_tracker` a casa e' una CONDIZIONE: il digesto tace. Ma non e'
    escluso dal prodotto -- se lo chiedi, `guarda` te lo dice, altrimenti HIRIS
    non saprebbe piu' rispondere a «chi e' in casa?». Senza la seconda meta' di
    questa prova avremmo costruito un filtro invece di un vocabolario, e la
    suite sarebbe restata verde."""
    from hiris.app.home_space.queries import view
    voce = _voce("device_tracker.paolo", "Telefono di Paolo")
    sezione = _sezione_notevole(_con([voce], {"device_tracker.paolo": "home"}))
    assert "Telefono di Paolo" not in sezione

    casa = dict(_CASA, entita=_CASA["entita"] + [voce])
    dettaglio = view(casa, _COMPORTAMENTO, _RICORDI,
                       dict(_STATO, **{"device_tracker.paolo": "home"}),
                       "area", "sala")
    assert any(e["id"] == "device_tracker.paolo" for e in dettaglio["entita"]), (
        "il digesto tace, ma chi CHIEDE deve vedere: e' la differenza fra "
        "scegliere cosa dire e nascondere")


# ── La salute non e' l'adesso ──────────────────────────────────────────────

def test_le_irraggiungibili_diventano_UNA_riga_di_conteggio():
    """Erano 119 sull'impianto vero e occupavano 76 righe del digesto. Non sono
    «cosa sta facendo la casa»: sono SALUTE, ed e' una fetta sua. Togliere il
    fatto sarebbe una perdita; ripeterlo settantasei volte e' il rumore."""
    entita, stato = [], {}
    for i in range(12):
        entita.append(_voce(f"sensor.giu_{i}", f"Sensore {i}"))
        stato[f"sensor.giu_{i}"] = "unavailable"
    sezione = _sezione_notevole(_con(entita, stato))
    assert "12 entità non rispondono" in sezione
    assert "Sensore 0" not in sezione, (
        "una riga di conteggio, non una riga per entita'")


# ── La soglia: smette di scattare, non sparisce ────────────────────────────

def test_sotto_la_soglia_le_luci_si_chiamano_per_nome():
    """Il metro della fetta, in piccolo: tolto il rumore il digesto scende
    sotto i 15, il dettaglio individuale torna, e HIRIS puo' dire QUALE luce
    senza chiamare nessuno strumento."""
    sezione = _sezione_notevole(compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)[0])
    assert "Faretti" in sezione


def test_la_soglia_resta_viva_quando_serve_davvero():
    """Non si tara e non si toglie una guardia corretta: con trenta luci accese
    raggruppare e' giusto. Le si toglie il motivo per cui scattava SEMPRE."""
    entita, stato = [], {}
    for i in range(30):
        entita.append(_voce(f"light.festa_{i}", f"Luce {i}"))
        stato[f"light.festa_{i}"] = "on"
    sezione = _sezione_notevole(_con(entita, stato))
    assert "Luce 0" not in sezione
    assert "raggruppat" in sezione.lower()


# ── Le nascoste: fuori dalle gestioni, DENTRO la conoscenza ────────────────

def _sezione_lacune(testo: str) -> str:
    return testo.split("## Cio' che HIRIS ignora")[1]


def test_le_nascoste_si_contano_nel_nucleo_anche_se_non_si_annunciano():
    """«Non la annuncio» e «non so che esiste» sono due cose diverse, e la
    seconda sarebbe una perdita.

    Il digesto rispetta la scelta dell'utente e tace. Ma alla domanda «quante
    entita' nascoste ci sono?» HIRIS deve saper rispondere -- e senza il numero
    nel nucleo servirebbe una chiamata a `guarda` per ognuna delle sedici aree,
    cioe' lo stesso difetto che questa fetta chiude."""
    entita, stato = [], {}
    for i in range(3):
        entita.append(_voce(f"light.nascosta_{i}", f"Luce nascosta {i}", nascosta=1))
        stato[f"light.nascosta_{i}"] = "on"
    testo = _con(entita, stato)

    assert "Luce nascosta 0" not in _sezione_notevole(testo), (
        "il digesto rispetta la scelta dell'utente")
    lacune = _sezione_lacune(testo)
    assert "3 entita' nascoste" in lacune, (
        "ma il numero c'e', altrimenti la domanda «quante ce ne sono?» "
        "costerebbe sedici chiamate")


def test_senza_nascoste_non_si_dice_niente():
    """Un avviso che compare sempre non e' un avviso -- lezione gia' pagata in
    questo prodotto."""
    assert "nascost" not in _sezione_lacune(
        compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)[0])


def test_una_nascosta_DISABILITATA_non_si_conta_due_volte():
    """Un'entita' disabilitata e' gia' fuori da tutto: contarla anche fra le
    nascoste direbbe un numero che non corrisponde a niente di cercabile."""
    testo = _con([_voce("light.spenta", "Luce disabilitata",
                        nascosta=1, disabilitata=1)], {"light.spenta": "on"})
    assert "nascost" not in _sezione_lacune(testo)


# ── R9: il vocabolario del nucleo pinnato alla fonte ───────────────────────
#
# `briefing._ACTIVE_STATES` e il campo `notable` del vocabolario dei tipi sono
# scritti a mano. Senza queste prove, togliere una voce (o non aggiungerne una
# quando Home Assistant introduce un dominio o una device_class nuova) non
# farebbe rosso nessun test -- lo stesso rischio gia' pagato con
# `carbon_monoxide`/`co` (vedi in cima a questo file). `_CLASS_MEANING`
# in topology.py aveva gia' avuto questo trattamento -- e dall'08/09/2026 non
# esiste piu': le parole le pubblica Home Assistant.
#
# **Le due liste-evento non sono piu' due liste, e queste prove lo mostrano.**
# Dall'08/09/2026 `_EVENT_DOMAINS` e `_EVENT_CLASSES` sono lo STESSO campo --
# `notable` -- sulle due granularita' del tipo: i due pin qui sotto
# interrogano `notable_types()` e lo separano in domini e coppie, invece di
# leggere due insiemi che nessuno teneva allineati.
#
# LIMITE DICHIARATO: il vocabolario dei tipi e briefing.py sono PURI e non
# installano Home Assistant (vedi i loro docstring), quindi non c'e' un enum
# vero da importare e confrontare a runtime -- come per `_PIATTAFORME_HA` in
# test_domain_vocabulary.py, gli elenchi sotto sono ricopiati A MANO dalla
# fonte (vedi i commenti accanto a ciascun giudizio per dove ogni voce e'
# verificata). La prova non si accorge se Home Assistant cambia la fonte da
# sola: va RIVISTA a mano quando si aggiorna Home Assistant, o quando entra un
# dominio/classe nuova nel prodotto.


def domini_notevoli() -> set[str]:
    """I domini che il vocabolario dichiara degni di un annuncio."""
    return {dominio for dominio, classe in notable_types() if classe is None}


def classi_notevoli() -> set[tuple[str, str]]:
    """Le coppie (dominio, classe) degne di un annuncio."""
    return {chiave for chiave in notable_types() if chiave[1] is not None}

_STATI_ATTIVI_HA = {"on", "open", "unlocked", "playing", "cleaning"}


def test_stati_attivi_e_pinnato_alla_fonte():
    """Mutazione: togliere uno stato da `_ACTIVE_STATES` deve far rosso
    questo test."""
    senza = sorted(_STATI_ATTIVI_HA - briefing._ACTIVE_STATES)
    extra = sorted(briefing._ACTIVE_STATES - _STATI_ATTIVI_HA)
    assert not senza and not extra, (
        f"_STATI_ATTIVI e' cambiato senza aggiornare questo pin -- mancanti: "
        f"{senza}, in piu': {extra}")


_DOMINI_EVENTO_HA = {
    "light", "switch", "cover", "lock", "fan",
    "media_player", "valve", "remote", "siren", "vacuum",
}


def test_domini_evento_e_pinnato_alla_fonte():
    """Mutazione: togliere `notable` a un dominio del vocabolario deve far
    rosso questo test."""
    senza = sorted(_DOMINI_EVENTO_HA - domini_notevoli())
    extra = sorted(domini_notevoli() - _DOMINI_EVENTO_HA)
    assert not senza and not extra, (
        f"_DOMINI_EVENTO e' cambiato senza aggiornare questo pin -- "
        f"mancanti: {senza}, in piu': {extra}")


def test_domini_evento_sono_tutte_piattaforme_vere_di_home_assistant():
    """Coerenza fra le liste: ogni dominio trattato come «evento» deve essere
    una piattaforma che Home Assistant riconosce davvero -- altrimenti
    l'eccezione descriverebbe un dominio che non esiste. Sottoinsieme, come
    quello gia' pinnato fra le classi notevoli e cio' che la casa pubblica."""
    from tests.test_domain_vocabulary import _PIATTAFORME_HA
    sconosciuti = sorted(domini_notevoli() - set(_PIATTAFORME_HA))
    assert not sconosciuti, f"domini che Home Assistant non ha: {sconosciuti}"


_CLASSI_EVENTO_HA = {
    "moisture", "smoke", "gas", "carbon_monoxide", "safety", "tamper",
    "problem", "heat", "cold", "door", "window", "garage_door", "opening",
}


def test_classi_evento_e_pinnato_alla_fonte():
    """Mutazione: togliere `notable` a una coppia del vocabolario deve far
    rosso questo test -- la mutazione che il brief della fetta chiede
    esplicitamente («togliere una classe dall'elenco»).

    **E tutte e tredici sono coppie di `binary_sensor`**: il campo `notable`
    vive sulla riga del tipo, quindi la classe non e' piu' una stringa nuda
    che qualcuno abbina al dominio giusto a mano."""
    domini = {dominio for dominio, _ in classi_notevoli()}
    assert domini == {"binary_sensor"}, domini
    presenti = {classe for _, classe in classi_notevoli()}
    senza = sorted(_CLASSI_EVENTO_HA - presenti)
    extra = sorted(presenti - _CLASSI_EVENTO_HA)
    assert not senza and not extra, (
        f"_CLASSI_EVENTO e' cambiato senza aggiornare questo pin -- "
        f"mancanti: {senza}, in piu': {extra}")
