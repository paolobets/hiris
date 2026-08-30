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

from hiris.app.casa import anagrafe, nucleo
from hiris.app.casa.nucleo import componi

# Le finte vivono gia' in `test_nucleo.py`: si riusano invece di riscriverle.
# Due finte che fingono la stessa casa sono la seconda rappresentazione in
# miniatura, e divergono come tutte le seconde rappresentazioni.
from tests.test_nucleo import _CASA, _COMPORTAMENTO, _RICORDI, _STATO


def _sezione_notevole(testo: str) -> str:
    return testo.split("## Notevole adesso")[1].split("## ")[0]


def _con(entita, stato_extra):
    casa = dict(_CASA, entita=_CASA["entita"] + entita)
    return componi(casa, _COMPORTAMENTO, _RICORDI, dict(_STATO, **stato_extra))[0]


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
    assert "bagnato" in sezione
    assert "Perdita bagno (acceso)" not in sezione


# I nomi-stringa VERI, dalla sorgente di Home Assistant
# (homeassistant/components/binary_sensor/__init__.py), non dalla pagina di
# documentazione -- che elenca i NOMI DELLE COSTANTI e non i valori.
# Tutte tranne una coincidono col nome in minuscolo. L'eccezione:
# `BinarySensorDeviceClass.CO = "carbon_monoxide"`.
_ALLARMI = [
    ("moisture", "bagnato"),
    ("smoke", "fumo rilevato"),
    ("gas", "gas rilevato"),
    ("carbon_monoxide", "monossido rilevato"),
    ("safety", "non sicuro"),
    ("tamper", "manomissione rilevata"),
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
    assert parola in sezione, (
        f"la classe {classe!r} entra ma non si traduce: manca da "
        f"_SIGNIFICATO_CLASSE, e si legge «acceso»")


def test_ogni_classe_di_evento_ha_anche_un_significato():
    """Le due tabelle non possono divergere: una classe che entra nel digesto e
    non ha un significato si leggerebbe «acceso» -- cioe' rientrerebbe proprio
    il difetto che questa fetta chiude, su una riga sola. `_CLASSI_EVENTO` vive
    in `nucleo`, `_SIGNIFICATO_CLASSE` nella sua unica casa, `anagrafe`."""
    senza = sorted(nucleo._CLASSI_EVENTO - set(anagrafe._CLASS_MEANING))
    assert not senza, f"classi che entrano nel digesto senza significato: {senza}"


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
    assert not hasattr(nucleo, "_CLASSI_APERTURA"), (
        "la tabella vecchia deve sparire, non restare accanto alla nuova")
    sezione = _sezione_notevole(componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)[0])
    assert "Porta" in sezione and "aperto" in sezione


# ── Cio' che Home Assistant dichiara non primario ──────────────────────────

def test_un_entita_diagnostic_non_entra_qualunque_sia_il_suo_stato():
    """Il caso da 179 unita' su 300. Home Assistant DICHIARA che queste non
    sono primarie, e la sua documentazione dice che sono normalmente nascoste
    dalle viste principali. HIRIS legge gia' il campo (`casa/archivio.py:135`)
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
    from hiris.app.casa.domande import guarda
    voce = _voce("device_tracker.paolo", "Telefono di Paolo")
    sezione = _sezione_notevole(_con([voce], {"device_tracker.paolo": "home"}))
    assert "Telefono di Paolo" not in sezione

    casa = dict(_CASA, entita=_CASA["entita"] + [voce])
    dettaglio = guarda(casa, _COMPORTAMENTO, _RICORDI,
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
    sezione = _sezione_notevole(componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)[0])
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
        componi(_CASA, _COMPORTAMENTO, _RICORDI, _STATO)[0])


def test_una_nascosta_DISABILITATA_non_si_conta_due_volte():
    """Un'entita' disabilitata e' gia' fuori da tutto: contarla anche fra le
    nascoste direbbe un numero che non corrisponde a niente di cercabile."""
    testo = _con([_voce("light.spenta", "Luce disabilitata",
                        nascosta=1, disabilitata=1)], {"light.spenta": "on"})
    assert "nascost" not in _sezione_lacune(testo)


# ── R9: il vocabolario del nucleo pinnato alla fonte ───────────────────────
#
# `_STATI_ATTIVI`, `_DOMINI_EVENTO` e `_CLASSI_EVENTO` sono scritte a mano in
# nucleo.py. Senza queste prove, togliere una voce (o non aggiungerne una
# quando Home Assistant introduce un dominio o una device_class nuova) non
# farebbe rosso nessun test -- lo stesso rischio gia' pagato con
# `carbon_monoxide`/`co` (vedi in cima a questo file). `_SIGNIFICATO_CLASSE`
# in anagrafe.py aveva gia' avuto questo trattamento; qui lo stesso.
#
# LIMITE DICHIARATO: nucleo.py e' PURO e non installa Home Assistant (vedi
# il suo docstring), quindi non c'e' un enum vero da importare e confrontare
# a runtime -- come per `_PIATTAFORME_HA` in test_vocabolario_domini.py,
# l'elenco sotto e' ricopiato A MANO dalla fonte (vedi i commenti sopra le
# tre liste in nucleo.py per dove ciascuna voce e' verificata). La prova non
# si accorge se Home Assistant cambia la fonte da sola: va RIVISTA a mano
# quando si aggiorna Home Assistant, o quando entra un dominio/classe nuova
# nel prodotto.

_STATI_ATTIVI_HA = {"on", "open", "unlocked", "playing", "cleaning"}


def test_stati_attivi_e_pinnato_alla_fonte():
    """Mutazione: togliere uno stato da `_STATI_ATTIVI` deve far rosso
    questo test."""
    senza = sorted(_STATI_ATTIVI_HA - nucleo._STATI_ATTIVI)
    extra = sorted(nucleo._STATI_ATTIVI - _STATI_ATTIVI_HA)
    assert not senza and not extra, (
        f"_STATI_ATTIVI e' cambiato senza aggiornare questo pin -- mancanti: "
        f"{senza}, in piu': {extra}")


_DOMINI_EVENTO_HA = {
    "light", "switch", "cover", "lock", "fan",
    "media_player", "valve", "remote", "siren", "vacuum",
}


def test_domini_evento_e_pinnato_alla_fonte():
    """Mutazione: togliere un dominio da `_DOMINI_EVENTO` deve far rosso
    questo test."""
    senza = sorted(_DOMINI_EVENTO_HA - nucleo._DOMINI_EVENTO)
    extra = sorted(nucleo._DOMINI_EVENTO - _DOMINI_EVENTO_HA)
    assert not senza and not extra, (
        f"_DOMINI_EVENTO e' cambiato senza aggiornare questo pin -- "
        f"mancanti: {senza}, in piu': {extra}")


def test_domini_evento_sono_tutte_piattaforme_vere_di_home_assistant():
    """Coerenza fra le liste: ogni dominio trattato come «evento» deve essere
    una piattaforma che Home Assistant riconosce davvero -- altrimenti
    l'eccezione descriverebbe un dominio che non esiste. Sottoinsieme, come
    quello gia' pinnato fra `_CLASSI_EVENTO` e `_SIGNIFICATO_CLASSE`."""
    from tests.test_vocabolario_domini import _PIATTAFORME_HA
    sconosciuti = sorted(nucleo._DOMINI_EVENTO - set(_PIATTAFORME_HA))
    assert not sconosciuti, f"domini che Home Assistant non ha: {sconosciuti}"


_CLASSI_EVENTO_HA = {
    "moisture", "smoke", "gas", "carbon_monoxide", "safety", "tamper",
    "problem", "heat", "cold", "door", "window", "garage_door", "opening",
}


def test_classi_evento_e_pinnato_alla_fonte():
    """Mutazione: togliere una classe da `_CLASSI_EVENTO` deve far rosso
    questo test -- la mutazione che il brief della fetta chiede esplicitamente
    («togliere una classe dall'elenco»)."""
    senza = sorted(_CLASSI_EVENTO_HA - nucleo._CLASSI_EVENTO)
    extra = sorted(nucleo._CLASSI_EVENTO - _CLASSI_EVENTO_HA)
    assert not senza and not extra, (
        f"_CLASSI_EVENTO e' cambiato senza aggiornare questo pin -- "
        f"mancanti: {senza}, in piu': {extra}")
