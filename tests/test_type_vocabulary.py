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

**Dal 29/09/2026 il nucleo non annuncia piu' lo stato del momento**
(«Notevole adesso» e' uscita, spec «una porta sola per la casa» §5): le prove
che guardavano quella sezione -- l'allagamento che si legge «Bagnato», il
movimento che non entra, le entita' di servizio e nascoste che non si
annunciano, le irraggiungibili contate in una riga, la soglia dei quindici --
sono uscite con lei. Restano le prove sulle PAROLE (`readable_state`), sui
conteggi che il nucleo porta ancora e su cio' che `guarda` riporta a chi chiede.
"""

import pathlib
import sys

from hiris.app.home_space import briefing, topology
from hiris.app.home_space.briefing import compose

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import censore_tipi

from hiris.app.home_space.house import House
from hiris.app.home_space.topology import Mirror

# Le finte vivono gia' in `test_briefing.py`: si riusano invece di riscriverle.
# Due finte che fingono la stessa casa sono la seconda rappresentazione in
# miniatura, e divergono come tutte le seconde rappresentazioni.
from tests._house_translations import house_translations
from tests.test_briefing import _CASA, _COMPORTAMENTO, _RICORDI, _STATO


def _con(entita, stato_extra):
    casa = dict(_CASA, entita=_CASA["entita"] + entita)
    return compose(casa, _COMPORTAMENTO, _RICORDI, dict(_STATO, **stato_extra))[0]


def _voce(eid, nome, **extra):
    base = {"id": eid, "nome": nome, "area_id": "sala", "dispositivo_id": None,
            "classe": None, "unita": None, "disabilitata": 0}
    base.update(extra)
    return base


# ── Cosa significano i valori: la classe decide ────────────────────────────

def test_porte_e_finestre_si_leggono_ancora_aperto_e_chiuso():
    """`_CLASSI_APERTURA` non esiste piu': le sue cinque voci sono cinque righe
    della mappa dei significati. La prova che l'estensione ha ASSORBITO il caso
    particolare invece di affiancarlo -- che e' la differenza fra finire un
    vocabolario e aggiungergliene accanto un secondo."""
    assert not hasattr(briefing, "_CLASSI_APERTURA"), (
        "la tabella vecchia deve sparire, non restare accanto alla nuova")
    # Fino al 29/09/2026 la parola si leggeva in «Notevole adesso»; uscita
    # quella sezione, si chiede alla sola resa che resta (la stessa che usa
    # `guarda`).
    assert topology.readable_state(
        "on", domain="binary_sensor", device_class="door",
        translations=house_translations())["valore"] == "Aperto"


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

def test_service_entities_are_counted_even_when_not_announced():
    """Task 3 di «rifiutare e importare» (§7①): `entity_category` era gia'
    letto (`store.py:385`, e da questa stessa fetta anche da `_enrich_entity`,
    `queries.py`) ma nessun lettore lo metteva DAVANTI -- il digesto le
    escludeva in silenzio da «Notevole adesso» (uscita il 29/09/2026) senza
    mai dire QUANTE fossero. Stessa disciplina delle nascoste due sezioni sopra:
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

    gaps = _sezione_lacune(text)
    assert "2 entita' di servizio" in gaps, (
        "ma il numero c'e', altrimenti la domanda «quante sono di servizio?» "
        "costerebbe una chiamata a `search` per ognuna")


def test_without_service_entities_nothing_is_said():
    """Un avviso che compare sempre non e' un avviso -- stessa lezione delle
    nascoste, stesso file.

    Mutazione: l'avviso "N entita' di servizio" reso incondizionato (fuori
    dall'`if service:` di `briefing.compose`) -- il test torna rosso su
    `assert "servizio" not in _sezione_lacune(...)` (compare "0 entita' di
    servizio...")."""
    assert "servizio" not in _sezione_lacune(
        compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)[0])


# ── Condizioni travestite da eventi ────────────────────────────────────────

def test_un_telefono_in_casa_chi_chiede_lo_vede():
    """LA DIFFERENZA FRA VOCABOLARIO E FILTRO.

    Un `device_tracker` a casa e' una CONDIZIONE, e il nucleo non la annuncia
    (dal 29/09/2026 il nucleo non annuncia nessuno stato del momento: la meta'
    di questa prova che lo verificava su «Notevole adesso» e' uscita con la
    sezione). Ma non e' escluso dal prodotto -- se lo chiedi, `guarda` te lo
    dice, altrimenti HIRIS non saprebbe piu' rispondere a «chi e' in casa?»."""
    from hiris.app.home_space.queries import view
    voce = _voce("device_tracker.paolo", "Telefono di Paolo")

    casa = dict(_CASA, entita=_CASA["entita"] + [voce])
    dettaglio = view(House(casa, Mirror(state=dict(_STATO, **{"device_tracker.paolo": "home"}))),
                     _COMPORTAMENTO, _RICORDI,
                       "area", "sala")
    assert any(e["id"] == "device_tracker.paolo" for e in dettaglio["entita"]), (
        "il digesto tace, ma chi CHIEDE deve vedere: e' la differenza fra "
        "scegliere cosa dire e nascondere")


# ── La salute non e' l'adesso ──────────────────────────────────────────────

# ── La soglia: smette di scattare, non sparisce ────────────────────────────

# ── Le nascoste: fuori dalle gestioni, DENTRO la conoscenza ────────────────

def _sezione_lacune(testo: str) -> str:
    return testo.split("## Cio' che HIRIS ignora")[1]


def test_le_nascoste_si_contano_nel_nucleo_anche_se_non_si_annunciano():
    """«Non la annuncio» e «non so che esiste» sono due cose diverse, e la
    seconda sarebbe una perdita.

    Il nucleo rispetta la scelta dell'utente e non le conta in «La casa». Ma
    alla domanda «quante entita' nascoste ci sono?» HIRIS deve saper
    rispondere -- e senza il numero nel nucleo servirebbe una chiamata a
    `search` per ognuna delle sedici aree, cioe' lo stesso difetto che questa
    fetta chiude."""
    entita, stato = [], {}
    for i in range(3):
        entita.append(_voce(f"light.nascosta_{i}", f"Luce nascosta {i}", nascosta=1))
        stato[f"light.nascosta_{i}"] = "on"
    testo = _con(entita, stato)

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
# `censore_tipi._ACTIVE_STATES` e' scritto a mano. Senza questa prova, togliere
# una voce non farebbe rosso nessun test -- lo stesso rischio gia' pagato con
# `carbon_monoxide`/`co` (vedi in cima a questo file).
#
# I due pin delle liste-evento (dieci domini e tredici classi, il campo
# `notable` del vocabolario dei tipi) sono usciti il 02/10/2026 con le
# dichiarazioni che pinnavano: dal 29/09 nessun codice le leggeva.
#
# LIMITE DICHIARATO: il censore non installa Home Assistant, quindi non c'e'
# un enum vero da importare e confrontare a runtime -- l'elenco sotto e'
# ricopiato A MANO dalla fonte (i riferimenti stanno accanto a
# `_ACTIVE_STATES`). La prova non si accorge se Home Assistant cambia la
# fonte da sola: va RIVISTA a mano quando si aggiorna Home Assistant.


_STATI_ATTIVI_HA = {"on", "open", "unlocked", "playing", "cleaning"}


def test_stati_attivi_e_pinnato_alla_fonte():
    """Mutazione: togliere uno stato da `_ACTIVE_STATES` deve far rosso
    questo test."""
    senza = sorted(_STATI_ATTIVI_HA - censore_tipi._ACTIVE_STATES)
    extra = sorted(censore_tipi._ACTIVE_STATES - _STATI_ATTIVI_HA)
    assert not senza and not extra, (
        f"_STATI_ATTIVI e' cambiato senza aggiornare questo pin -- mancanti: "
        f"{senza}, in piu': {extra}")
