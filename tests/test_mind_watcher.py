"""L'osservatore al rubinetto: filtra col pavimento e annota, senza giudicare.

Il rubinetto e' lo STESSO che alimenta lo specchio delle entita'
(`HAClient.add_state_listener`): non se ne apre un secondo, per la stessa
ragione per cui non si apre un secondo canale verso Home Assistant.
"""
import pytest

from hiris.app.mind.watcher import Watcher


class _FintoArchivio:
    """La finta deve saper produrre il difetto che sorveglia: oltre ad
    `record`, tiene righe di `cambi` VERE (per la ricostruzione all'avvio, D1
    del mandato) e puo' sollevare a comando (per provare che la ricostruzione
    non si ferma se l'archivio non risponde, e che `watch_reading` non
    solleva mai se l'archivio e' rotto).

    **`readings()` applica `source` e `limit` davvero, e ordina ASC come quella
    vera**: una finta che accetta questi parametri e li ignora e' una finta
    che non puo' fallire, e non avrebbe potuto sorvegliare D1."""

    def __init__(self, cambi_esistenti=None, *, cambi_solleva=False,
                 annota_solleva=False, annota_solleva_per=None):
        self.annotati = []
        self._cambi = list(cambi_esistenti or [])
        self._cambi_solleva = cambi_solleva
        self._annota_solleva = annota_solleva
        self._annota_solleva_per = set(annota_solleva_per or [])

    def record(self, **kw):
        if self._annota_solleva or kw.get("subject") in self._annota_solleva_per:
            raise RuntimeError("archivio rotto")
        self.annotati.append(kw)

    def readings(self, *, from_ts, to_ts, subject=None, source=None, limit=200_000):
        if self._cambi_solleva:
            raise RuntimeError("archivio irraggiungibile")
        righe = [c for c in self._cambi if from_ts <= c["quando_ts"] < to_ts]
        if subject is not None:
            righe = [c for c in righe if c["soggetto"] == subject]
        if source is not None:
            righe = [c for c in righe if c["fonte"] == source]
        righe = sorted(righe, key=lambda c: c["quando_ts"])
        return righe[:max(1, limit)]


def _evento(eid, da, a, attributi=None):
    """La forma vera di `state_changed` come Home Assistant la manda."""
    return {"entity_id": eid,
            "old_state": None if da is None else {"state": da},
            "new_state": None if a is None else {
                "state": a, "attributes": attributi or {},
                "last_changed": "2026-08-24T12:00:00+00:00"}}


def _cambio(ts, fonte, soggetto, da, a):
    """Una riga di `readings()` come la torna l'archivio vero."""
    return {"quando_ts": ts, "fonte": fonte, "soggetto": soggetto, "da": da, "a": a}


@pytest.fixture()
def coppia():
    a = _FintoArchivio()
    return a, Watcher(a, now=lambda: 1787572800.0)


def test_una_cosa_del_pavimento_si_annota(coppia):
    archivio, osservatore = coppia
    assert osservatore.watch_reading(
        _evento("climate.camera_t", "off", "heat")) is True
    assert archivio.annotati == [{"quando_ts": 1787572800.0, "source": "entita",
                                  "subject": "climate.camera_t",
                                  "da": "off", "a": "heat", "device_class": None,
                                  "state_class": None, "source_type": None}]


# -- Correzione 0: il grezzo porta le tre classi che il pavimento legge -----

def test_guarda_cambio_scrive_le_tre_classi_quando_ci_sono(coppia):
    """Senza le tre classi nel grezzo, `aggregate_day` non puo' sapere che
    `binary_sensor.fumo_cucina` e' un rilevatore di fumo: il genere `energia`
    e la sesta gamba per classe non nascono mai (Task 3, punto 0)."""
    archivio, osservatore = coppia
    ev = _evento("binary_sensor.fumo_cucina", "off", "on",
                 {"device_class": "smoke", "state_class": "measurement",
                  "source_type": "cloud"})
    assert osservatore.watch_reading(ev) is True
    riga = archivio.annotati[0]
    assert riga["device_class"] == "smoke"
    assert riga["state_class"] == "measurement"
    assert riga["source_type"] == "cloud"


def test_guarda_cambio_scrive_none_quando_le_classi_mancano(coppia):
    archivio, osservatore = coppia
    osservatore.watch_reading(_evento("climate.camera_t", "off", "heat"))
    riga = archivio.annotati[0]
    assert riga["device_class"] is None
    assert riga["state_class"] is None
    assert riga["source_type"] is None


# -- Giro di pulizia (26 agosto), punto 6: due residui dell'osservatore ----

def test_guarda_cambio_scrive_none_per_attributi_non_testuali(coppia):
    """`_text_or_none` promette che un tipo inatteso -- numero, lista, dict,
    stringa di soli spazi -- diventi `None`, non un `str(valore)` che
    scriverebbe testo spazzatura nella colonna. Nessun test lo mandava
    finora: un intero finirebbe scritto in una colonna di testo. Mutazione:
    togliere il controllo `isinstance(valore, str)` da `_text_or_none` --
    tornerebbe il valore grezzo cosi' com'e', invece di `None`."""
    archivio, osservatore = coppia
    ev = _evento("climate.camera_t", "off", "heat",
                 {"device_class": 42, "state_class": ["misura"],
                  "source_type": "   "})
    assert osservatore.watch_reading(ev) is True
    riga = archivio.annotati[0]
    assert riga["device_class"] is None
    assert riga["state_class"] is None
    assert riga["source_type"] is None


def test_una_cosa_fuori_dal_pavimento_NON_si_annota(coppia):
    archivio, osservatore = coppia
    assert osservatore.watch_reading(_evento("light.lampadario", "on", "off")) is False
    assert archivio.annotati == []


def test_il_tracker_del_router_non_entra_dal_rubinetto(coppia):
    """La misura del 26/08: e' la classe piu' numerosa fra quelle escluse, e
    passa proprio da qui."""
    _archivio, osservatore = coppia
    assert osservatore.watch_reading(
        _evento("device_tracker.nvr", "home", "not_home",
                {"source_type": "router"})) is False


def test_l_istante_e_quello_del_CAMBIO_non_quello_della_scrittura(coppia):
    """`last_changed` dice quando la casa e' cambiata; l'orologio nostro dice
    quando l'abbiamo saputo. Annotare il secondo sposterebbe ogni oggetto di
    quel tanto, e nessuno se ne accorgerebbe."""
    archivio, osservatore = coppia
    ev = _evento("climate.camera_t", "off", "heat")
    ev["new_state"]["last_changed"] = "2026-08-24T11:30:00+00:00"
    osservatore.watch_reading(ev)
    assert archivio.annotati[0]["quando_ts"] == 1787571000.0  # 2026-08-24T11:30:00+00:00


def test_senza_last_changed_si_usa_l_orologio(coppia, caplog):
    """Il ripiego era muto: se HA smettesse di mandare `last_changed`, ogni
    cambio slitterebbe all'istante in cui l'abbiamo saputo e nessuno se ne
    accorgerebbe. La mutazione 'cancella `or self._now()`' deve arrossire
    questo test, non restare verde."""
    import logging
    archivio, osservatore = coppia
    ev = _evento("climate.camera_t", "off", "heat")
    del ev["new_state"]["last_changed"]
    with caplog.at_level(logging.DEBUG, logger="hiris.app.mind.watcher"):
        assert osservatore.watch_reading(ev) is True
    assert archivio.annotati[0]["quando_ts"] == 1787572800.0  # adesso() iniettato
    assert any("last_changed" in r.message for r in caplog.records)


def test_un_evento_senza_stato_nuovo_non_solleva(coppia):
    """Un'entita' rimossa manda `new_state: None`. L'osservatore gira per
    sempre: un'eccezione qui lo fermerebbe su un evento solo."""
    _archivio, osservatore = coppia
    assert osservatore.watch_reading(_evento("climate.camera_t", "heat", None)) is False


def test_un_evento_malformato_non_solleva(coppia):
    _archivio, osservatore = coppia
    for ev in [{}, {"entity_id": None}, {"entity_id": "climate.x"}, None]:
        assert osservatore.watch_reading(ev) is False


def test_guarda_cambio_con_archivio_rotto_non_solleva():
    """Tutti gli ingressi malformati muoiono sulle guardie in cima al metodo:
    il ramo `except` non era mai raggiunto, e la mutazione 'togli il
    try/except' restava verde. Qui l'archivio stesso solleva."""
    archivio = _FintoArchivio(annota_solleva=True)
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    assert osservatore.watch_reading(_evento("climate.camera_t", "off", "heat")) is False


def test_un_problema_di_HA_diventa_un_cambio(coppia):
    """Un'integrazione rotta non e' un cambio di stato -- ma il suo COMPARIRE
    lo e'. Cosi' la riga del grezzo resta una sola.

    Un `problema:` (un *repair* di Home Assistant) porta `domain` ma non un
    titolo -- `ws_list_issues` non ne manda uno (verificato alla fonte,
    `components/repairs/websocket_api.py`): `title=None` e' un campo vuoto
    dichiarato, non un buco.

    Mutazione: passare `title=domain` invece di `title=None` per i
    `problema:` -- il test torna rosso su `assert ...["title"] is None`.
    """
    archivio, osservatore = coppia
    scritti = osservatore.watch_system(
        problems=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrations=[])
    assert scritti == 1
    assert archivio.annotati[0]["source"] == "sistema"
    assert archivio.annotati[0]["subject"] == "problema:sonos.subscriptions_failed"
    assert archivio.annotati[0]["a"] == "aperto"
    assert archivio.annotati[0]["domain"] == "sonos"
    assert archivio.annotati[0]["title"] is None


def test_un_problema_che_sparisce_diventa_un_cambio(coppia):
    """Con l'isteresi (`_ROUNDS_BEFORE_CLOSING=2`) la chiusura arriva al
    SECONDO giro consecutivo senza il problema, non al primo -- vedi
    `test_one_missing_round_does_not_close_an_episode`.

    Mutazione: chiudere al primo giro mancante (rimuovere l'isteresi) --
    il primo `assert ... == 0` torna rosso.
    """
    archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.watch_system(problems=p, integrations=[])
    archivio.annotati.clear()
    assert osservatore.watch_system(problems=[], integrations=[]) == 0  # giro 1: isteresi
    assert osservatore.watch_system(problems=[], integrations=[]) == 1  # giro 2: chiude
    assert archivio.annotati[0]["a"] == "chiuso"


def test_una_condizione_che_dura_non_si_riscrive(coppia):
    """Il lavoro periodico gira ogni pochi minuti: riscrivere la stessa
    condizione a ogni giro riempirebbe l'archivio di righe identiche e
    renderebbe impossibile sapere QUANDO e' cominciata."""
    archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.watch_system(problems=p, integrations=[])
    archivio.annotati.clear()
    assert osservatore.watch_system(problems=p, integrations=[]) == 0
    assert archivio.annotati == []


def test_un_integrazione_ROTTA_diventa_un_cambio(coppia):
    """Misurato sulla casa vera il 02/09: delle 9 integrazioni «non caricate»
    che questo metodo trattava come guasto, **una sola era rotta davvero**
    (`lifx / Abat-jour`, `setup_retry`). Le altre otto erano `not_loaded` --
    lo stato INIZIALE, non un errore -- e per giunta tutte ignorate dal
    proprietario.

    **Il difetto misurato sulla casa vera**: `integrazione:<entry_id>` era il
    soggetto piu' raccontato dell'intero archivio (34 oggetti su 285 in nove
    giorni) e nessuna riga diceva cosa si fosse rotto -- `domain`, `title` e
    `state` si leggevano per decidere il guasto e poi si scartavano. Qui si
    verifica che restino: `a` porta la condizione VERA (`setup_retry`, non la
    costante `"aperto"`), `domain` e `title` la voce di configurazione.

    Mutazione: tornare a scrivere `a="aperto"` invece della condizione vera --
    il test torna rosso su `assert ...["a"] == "setup_retry"`.
    """
    archivio, osservatore = coppia
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "abc", "title": "Abat-jour",
                       "domain": "lifx", "state": "setup_retry"},
                      {"entry_id": "def", "title": "Sonos",
                       "domain": "sonos", "state": "loaded"}])
    assert scritti == 1
    assert archivio.annotati[0]["subject"] == "integrazione:abc"
    assert archivio.annotati[0]["a"] == "setup_retry"
    assert archivio.annotati[0]["domain"] == "lifx"
    assert archivio.annotati[0]["title"] == "Abat-jour"


def test_una_integrazione_senza_stato_non_apre_nessuna_condizione(coppia):
    """Home Assistant non manda mai uno `state` vuoto (verificato alla
    fonte: `ConfigEntry.as_json_fragment` lo scrive sempre). Se arrivasse
    comunque malformato, non deve aprire una condizione con `a=None` --
    `rebuild_conditions` non la riconoscerebbe mai come aperta (scarta
    None/vuoto, vedi sopra), e scrittore e ricostruttore devono dire la
    stessa cosa.

    Mutazione: togliere `if state is None: continue` -- il test torna rosso
    perche' verrebbe scritta una riga con `a=None`.
    """
    archivio, osservatore = coppia
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "abc", "domain": "lifx", "title": "Abat-jour"}])
    assert scritti == 0
    assert archivio.annotati == []


def test_not_loaded_NON_e_un_guasto(coppia):
    """«NOT_LOADED: The config entry has not been loaded. This is the initial
    state when a config entry is created or when Home Assistant is restarted»
    (developers.home-assistant.io/docs/config_entries_index/).

    Mutazione: togliere `not_loaded` da `_HEALTHY_INTEGRATION_STATES` --
    questo test torna rosso, e l'archivio riprende a registrare come guasto lo
    stato in cui OGNI integrazione si trova subito dopo un riavvio."""
    archivio, osservatore = coppia
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "abc", "domain": "fritz",
                       "state": "not_loaded", "source": "user"}])
    assert scritti == 0
    assert archivio.annotati == []


def test_una_voce_IGNORATA_dal_proprietario_non_e_un_guasto(coppia):
    """`source: "ignore"` e' una decisione, non una rottura -- e si scarta
    anche quando lo stato la direbbe rotta.

    Mutazione: togliere il filtro sull'origine -- questo test torna rosso, e
    l'archivio registra come guasto cio' che il proprietario ha chiesto di non
    sentire piu'."""
    archivio, osservatore = coppia
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "abc", "domain": "fritz",
                       "state": "setup_error", "source": "ignore"}])
    assert scritti == 0
    assert archivio.annotati == []


def test_una_integrazione_in_setup_non_e_un_guasto(coppia):
    """Il boot di HA fa nascere e sparire `setup_in_progress` in pochi
    secondi: se il primo giro del lavoro periodico cadesse durante il boot,
    trattarlo come guasto scriverebbe una coppia di righe di rumore per ogni
    integrazione."""
    archivio, osservatore = coppia
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "abc", "domain": "fritz",
                       "state": "setup_in_progress"}])
    assert scritti == 0
    assert archivio.annotati == []


def test_una_integrazione_in_unload_non_e_un_guasto(coppia):
    """'unload_in_progress' e' l'altro stato transitorio del boot, gemello
    di 'setup_in_progress': nasce e sparisce da solo in pochi secondi.
    Nessun test lo mandava finora -- toglierlo da
    `_HEALTHY_INTEGRATION_STATES` restava verde. Mutazione: togliere
    'unload_in_progress' dall'insieme -- scriverebbe un guasto di rumore
    per ogni integrazione in fase di ricarica."""
    archivio, osservatore = coppia
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "abc", "domain": "fritz",
                       "state": "unload_in_progress"}])
    assert scritti == 0
    assert archivio.annotati == []


def test_osservate_dice_cosa_guarda_e_PERCHE(coppia):
    """La pagina deve poter distinguere cio' che e' nel pavimento (e non si
    toglie) da cio' che l'obiettivo ha aggiunto (e si toglie). Un elenco che
    non li distingue non si puo' usare per decidere."""
    _archivio, osservatore = coppia
    osservatore.watch_reading(_evento("climate.camera_t", "off", "heat"))
    osservatore.watch_reading(_evento("person.marta", "home", "not_home"))
    v = {o["soggetto"]: o for o in osservatore.watching()}
    assert v["climate.camera_t"]["gamba"] == "comfort"
    assert v["climate.camera_t"]["provenienza"] == "pavimento"
    assert v["person.marta"]["gamba"] == "chi c'e'"


# -- Correzione 5: `_watched` e `_conditions` sono UNA fonte sola per fatto ---

def test_osservate_mostra_una_condizione_dopo_guarda_sistema(coppia):
    _archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.watch_system(problems=p, integrations=[])
    v = {o["soggetto"]: o for o in osservatore.watching()}
    assert v["problema:sonos.subscriptions_failed"]["gamba"] == "buono stato"


def test_osservate_non_mostra_piu_una_condizione_chiusa(coppia):
    """All'opposto del difetto gemello: una condizione chiusa non deve
    restare per sempre in cio' che `watching()` mostra.

    Due giri mancanti, non uno solo: con l'isteresi il primo giro senza il
    problema la lascia ancora aperta -- verificato a meta', non solo alla
    fine.

    Mutazione: chiudere al primo giro mancante (rimuovere l'isteresi) -- il
    primo `assert ... in soggetti_meta` torna rosso.
    """
    _archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.watch_system(problems=p, integrations=[])
    osservatore.watch_system(problems=[], integrations=[])  # giro 1: isteresi, resta aperta
    soggetti_meta = {o["soggetto"] for o in osservatore.watching()}
    assert "problema:sonos.subscriptions_failed" in soggetti_meta
    osservatore.watch_system(problems=[], integrations=[])  # giro 2: si chiude
    soggetti = {o["soggetto"] for o in osservatore.watching()}
    assert "problema:sonos.subscriptions_failed" not in soggetti


def test_osservate_include_una_condizione_ricostruita_al_riavvio():
    """Senza seminare `_watched`, un guasto ricostruito dopo un riavvio
    sparirebbe da `watching()` per sempre -- non verra' mai piu' riscritto
    'aperto', che e' proprio lo scopo di D1. Deve derivare da `_conditions`."""
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema",
                "problema:sonos.subscriptions_failed", None, "aperto"),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    soggetti = {o["soggetto"]: o for o in osservatore.watching()}
    assert soggetti["problema:sonos.subscriptions_failed"]["gamba"] == "buono stato"


# -- Correzione 6: `watch_system` aggiorna la memoria in modo incrementale

def test_guarda_sistema_ricorda_solo_cio_che_ha_scritto_davvero(coppia):
    """Se `record` solleva a meta', le righe 'aperto' gia' scritte devono
    restare ricordate (altrimenti il giro dopo le riscriverebbe con una
    seconda data di nascita), e quella fallita NON deve esserlo. La
    mutazione e' rimettere `self._conditions = open_conditions` dopo i due cicli."""
    archivio = _FintoArchivio(annota_solleva_per={"problema:rotto.x"})
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    with pytest.raises(RuntimeError):
        osservatore.watch_system(
            problems=[{"domain": "buona", "issue_id": "a", "severity": "error"},
                      {"domain": "rotto", "issue_id": "x", "severity": "error"}],
            integrations=[])
    # sorted(): "problema:buona.a" viene prima di "problema:rotto.x", quindi
    # e' gia' stata scritta quando "rotto.x" solleva.
    assert "problema:buona.a" in osservatore._conditions
    assert "problema:rotto.x" not in osservatore._conditions


# -- D1: la ricostruzione dello stato di sistema dall'archivio, al riavvio --
#
# `self._conditions` vive solo in RAM. Al riavvio dell'add-on (che succede a
# ogni aggiornamento, non in un caso limite) quel set riparte vuoto, e ogni
# guasto gia' aperto verrebbe riscritto come nato ORA -- l'unica informazione
# utile di un guasto che dura e' la sua data d'inizio.

def test_la_ricostruzione_evita_di_riscrivere_un_guasto_gia_aperto():
    """L'archivio finto contiene gia' `problema:sonos... -> aperto`, come se
    scritto da un giro precedente dell'add-on ora spento. Dopo la
    ricostruzione, lo stesso problema non deve produrre una riga nuova."""
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema",
                "problema:sonos.subscriptions_failed", None, "aperto"),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    scritti = osservatore.watch_system(
        problems=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrations=[])
    assert scritti == 0
    assert archivio.annotati == []


def test_la_ricostruzione_non_semina_una_condizione_gia_chiusa():
    """`aperto` e poi `chiuso` per lo stesso soggetto: la ricostruzione non
    deve seminarla, e se la condizione ricompare deve scrivere una riga
    nuova (e' un guasto nuovo, non la continuazione del vecchio)."""
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema",
                "problema:sonos.subscriptions_failed", None, "aperto"),
        _cambio(1787000100.0, "sistema",
                "problema:sonos.subscriptions_failed", "aperto", "chiuso"),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    scritti = osservatore.watch_system(
        problems=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrations=[])
    assert scritti == 1
    assert archivio.annotati[0]["a"] == "aperto"


# -- Correzione al Ruling 2 (04/09): `a` non e' piu' solo "aperto" ----------
#
# Da Task 1, un'integrazione scrive in `a` la condizione VERA dichiarata da HA
# (`setup_retry`, non la costante), e solo i `problema:` continuano a
# scrivere "aperto". La riga precedente di `rebuild_conditions` cercava
# soltanto `state == "aperto"`: per un guasto di integrazione, gia' aperto da
# un giro precedente, non lo avrebbe MAI ritrovato -- a ogni riavvio
# dell'add-on sarebbe rinato come nuovo, con una data d'inizio falsa. Non e'
# territorio del Task 3 (isteresi): e' la conseguenza diretta del cambio di
# `a` fatto in questo stesso task, e si corregge qui.

def test_la_ricostruzione_riconosce_una_condizione_vera_come_aperta():
    """L'archivio finto contiene gia' `integrazione:01ABC -> setup_retry`,
    come se scritto da un giro precedente dell'add-on ora spento (Task 1: la
    scrittura di apertura porta la condizione vera, non piu' "aperto"). Dopo
    la ricostruzione, la stessa integrazione ancora rotta non deve produrre
    una riga nuova.

    Mutazione: rimettere `state == "aperto"` al posto di `state != "chiuso"`
    -- il test torna rosso su `assert scritti == 0` (la ricostruzione non
    ritroverebbe piu' nessun guasto di integrazione, e ognuno rinascerebbe
    come nuovo a ogni riavvio).
    """
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema", "integrazione:01ABC", None, "setup_retry"),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "01ABC", "domain": "lifx",
                       "title": "Abat-jour", "state": "setup_retry"}])
    assert scritti == 0
    assert archivio.annotati == []


def test_la_ricostruzione_non_considera_aperta_una_condizione_chiusa():
    """Simmetrico al test sopra: una condizione che si e' aperta con una
    condizione vera e poi si e' chiusa (`a="chiuso"`) non deve rientrare fra
    le aperte -- la ricomparsa e' un guasto NUOVO, non la continuazione del
    vecchio, e deve produrre una riga.

    Mutazione: togliere `and state != "chiuso"` (lasciare solo `if state`) --
    il test torna rosso su `assert scritti == 1` (la vecchia chiusura
    resterebbe considerata aperta, e la ricomparsa non scriverebbe niente).
    """
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema", "integrazione:01ABC", None, "setup_retry"),
        # `da=None`, non "setup_retry": e' cio' che `watch_system` scrive
        # davvero alla chiusura (la memoria in RAM non ricorda l'ultima
        # condizione, solo il soggetto).
        _cambio(1787000100.0, "sistema", "integrazione:01ABC", None, "chiuso"),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "01ABC", "domain": "lifx",
                       "title": "Abat-jour", "state": "setup_retry"}])
    assert scritti == 1
    assert archivio.annotati[0]["a"] == "setup_retry"


def test_la_ricostruzione_non_considera_aperta_una_riga_senza_valore():
    """Una riga di sistema con `a=None` o `a=""` non dice niente -- non e' un
    fatto, e' l'assenza di uno (nessuna delle due dovrebbe capitare da
    `watch_system` per un'apertura, ma l'archivio e' testo libero: la
    guardia protegge lo stesso da un ingresso malformato).

    Mutazione: togliere `state and` (lasciare solo `state != "chiuso"`) -- il
    test torna rosso perche' `None`/`""` verrebbero considerati aperti, e
    `osservatore._conditions` non resterebbe vuoto.
    """
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema", "integrazione:senza_valore", None, None),
        _cambio(1787000050.0, "sistema", "integrazione:vuota", None, ""),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    assert osservatore._conditions == set()


def test_la_ricostruzione_non_solleva_se_l_archivio_non_risponde():
    """Un'eccezione qui non deve fermare l'avvio dell'add-on: si riparte da
    vuoto, esattamente come al primo avvio in assoluto."""
    archivio = _FintoArchivio(cambi_solleva=True)
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()  # non deve sollevare
    scritti = osservatore.watch_system(
        problems=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrations=[])
    assert scritti == 1  # riparte da vuoto: la condizione sembra nuova


def test_la_ricostruzione_ignora_le_righe_di_entita():
    """Le finte dei tre test D1 qui sopra contenevano SOLO righe di sistema:
    cancellare `source="sistema"` dalla chiamata a `readings()` restava verde.
    Una riga di entita' con `a="aperto"` basta a farlo notare, se la
    ricostruzione la trattasse come una condizione di sistema."""
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema",
                "problema:sonos.subscriptions_failed", None, "aperto"),
        _cambio(1787000050.0, "entita", "climate.altro_aperto", "off", "aperto"),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    soggetti = {o["soggetto"] for o in osservatore.watching()}
    assert "climate.altro_aperto" not in soggetti
    assert "problema:sonos.subscriptions_failed" in soggetti


def test_la_ricostruzione_vede_condizioni_recenti_nonostante_il_volume_di_entita():
    """Il difetto D1 vero: sui 320.000 cambi/22gg misurati (spec §9②), quasi
    tutti di entita', un LIMIT che non filtrasse per fonte PRIMA di tagliare
    spingerebbe fuori le poche righe di sistema recenti -- che sono proprio
    quelle che decidono l'ultimo stato di una condizione. Qui il volume di
    entita' supera il `limit` esplicito passato da `rebuild_conditions`
    (20.000): se il filtro `source="sistema"` non entrasse nella query PRIMA
    del LIMIT, la riga di sistema (la piu' recente) verrebbe tagliata via."""
    molte_entita = [_cambio(1_700_000_000.0 + i, "entita", "x", "a", "b")
                    for i in range(20_005)]
    archivio = _FintoArchivio(cambi_esistenti=molte_entita + [
        _cambio(1787572700.0, "sistema",
                "problema:sonos.subscriptions_failed", None, "aperto"),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    scritti = osservatore.watch_system(
        problems=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrations=[])
    assert scritti == 0  # gia' seminata come aperta: non e' una novita'


# -- L'isteresi -- due giri prima di chiudere --------------------------------
#
# Il difetto misurato sulla casa vera il 03/09: quattro episodi per un solo
# guasto (`lifx / Abat-jour`), coi tre buchi di esattamente un giro del
# rilevatore (dieci minuti). `setup_retry` per costruzione RITENTA: un giro
# in cui HA non la elenca fra i problemi non vuol dire che sia guarita.

def _broken(entry_id="01ABC", state="setup_retry"):
    return {"entry_id": entry_id, "domain": "lifx", "title": "Abat-jour",
            "state": state, "source": "user"}


def test_one_missing_round_does_not_close_an_episode(coppia):
    """Quattro episodi per un guasto solo il 03/09, coi tre buchi di
    esattamente un giro del rilevatore: era il nostro campionamento, non la
    casa. `setup_retry` per costruzione RITENTA, e in un giro puo' non
    comparire fra i problemi.

    Mutazione: chiudere al primo giro mancante -- il test torna rosso su
    `assert closures == []`.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[_broken()])   # giro 1: apre
    osservatore.watch_system(problems=[], integrations=[])           # giro 2: assente
    closures = [r for r in archivio.annotati if r["a"] == "chiuso"]
    assert closures == []


def test_two_missing_rounds_close_the_episode(coppia):
    """L'isteresi non e' un rifiuto di chiudere: due giri consecutivi senza
    la condizione la chiudono. Senza questa prova la soglia potrebbe
    crescere all'infinito senza che nessuno se ne accorga.

    Gia' verde col codice di OGGI (che chiude al primo giro mancante): la si
    tiene comunque, perche' e' la prova che l'isteresi non diventa un
    rifiuto di chiudere.

    Mutazione: alzare la soglia a tre giri -- il test torna rosso su
    `assert len(closures) == 1`.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[_broken()])
    osservatore.watch_system(problems=[], integrations=[])
    osservatore.watch_system(problems=[], integrations=[])
    closures = [r for r in archivio.annotati if r["a"] == "chiuso"]
    assert len(closures) == 1


def test_the_missing_counter_resets_when_the_condition_returns(coppia):
    """Un giro mancante, poi la condizione torna, poi un altro giro
    mancante: non sono due mancati consecutivi, e l'episodio resta aperto.
    E' la differenza fra «assente due volte» e «assente due volte di
    seguito».

    Mutazione: non azzerare il contatore al ritorno -- il test torna rosso
    su `assert closures == []`.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[_broken()])
    osservatore.watch_system(problems=[], integrations=[])
    osservatore.watch_system(problems=[], integrations=[_broken()])
    osservatore.watch_system(problems=[], integrations=[])
    closures = [r for r in archivio.annotati if r["a"] == "chiuso"]
    assert closures == []


def test_the_reset_survives_a_record_failure_on_a_different_subject(coppia):
    """Il reset dei mancati e' pura RAM (un `dict.pop`) e non puo' fallire,
    a differenza di `record` nel ciclo delle nascite. Qui, nello STESSO
    giro, `buona.b` (gia' aperta, mancante da un giro) RICOMPARE mentre
    `rotto.x` NASCE e il suo `record` solleva: se il reset girasse dopo il
    ciclo delle nascite, l'eccezione lo impedirebbe, e il contatore di
    `buona.b` resterebbe alla quota vecchia -- un mancato consecutivo in
    piu' del vero, che al giro successivo la chiuderebbe dopo un solo
    mancato consecutivo (non due).

    Mutazione: spostare il reset dei mancati DOPO il ciclo delle nascite --
    il test torna rosso su `assert closures == []` (il quarto giro chiude
    `buona.b` di troppo presto).
    """
    archivio = _FintoArchivio(annota_solleva_per={"problema:rotto.x"})
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    buona = {"domain": "buona", "issue_id": "b", "severity": "error"}
    rotta = {"domain": "rotto", "issue_id": "x", "severity": "error"}
    osservatore.watch_system(problems=[buona], integrations=[])   # giro 1: buona.b apre
    osservatore.watch_system(problems=[], integrations=[])        # giro 2: buona.b assente (1)
    with pytest.raises(RuntimeError):
        # giro 3: buona.b RICOMPARE (deve azzerarsi) mentre rotto.x NASCE e
        # il suo `record` solleva -- l'eccezione propaga.
        osservatore.watch_system(problems=[buona, rotta], integrations=[])
    osservatore.watch_system(problems=[], integrations=[])        # giro 4: assente (1, non 2)
    closures = [r for r in archivio.annotati if r["a"] == "chiuso"]
    assert closures == []
