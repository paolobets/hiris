"""L'osservatore al rubinetto: filtra con lo SCOPE e annota, senza giudicare.

Il rubinetto e' lo STESSO che alimenta lo specchio delle entita'
(`HAClient.add_state_listener`): non se ne apre un secondo, per la stessa
ragione per cui non si apre un secondo canale verso Home Assistant.

**Il filtro non e' piu' il pavimento** (11/09/2026, spec §5.1-5.2). Fino a
ieri passava cio' che aveva una gamba -- un giudizio scritto a mano nel
vocabolario dei tipi, uguale per ogni casa, che nessuno rivedeva mai. Adesso
passa cio' che **l'osservatore ha deciso di guardare**, soggetto per soggetto,
con il perche' scritto accanto e la possibilita' di ricredersi alla cadenza di
riconsiderazione (`mind/cadence.py`). La garanzia non e' piu' «queste cose si
guardano comunque», e' «si puo' cambiare idea finche' il grezzo e' ancora li'».
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
                 annota_solleva=False, annota_solleva_per=None, scope=None):
        self.annotati = []
        # Cio' che l'osservatore ha deciso: `soggetto -> dentro`. La finta NON
        # dice di si' a tutto -- il rubinetto E' un filtro, e una finta che
        # passa qualunque cosa non potrebbe mai vederlo rotto. Chi non c'e' e'
        # fuori, esattamente come nell'archivio vero.
        self._scope = dict(scope or {})
        self._cambi = list(cambi_esistenti or [])
        self._cambi_solleva = cambi_solleva
        self._annota_solleva = annota_solleva
        self._annota_solleva_per = set(annota_solleva_per or [])

    def is_watched(self, subject):
        return bool(self._scope.get(subject))

    def scope(self):
        return {s: {"dentro": dentro, "motivo": f"motivo di {s}",
                    "autore": "observer", "deciso_ts": 1787000000.0}
                for s, dentro in self._scope.items()}

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


#: Lo scope che quasi tutte le prove di questo file danno per deciso. Non e'
#: un pavimento travestito: e' cio' che un osservatore avrebbe scelto su
#: questa casa finta, e le prove che provano IL FILTRO lo dicono esplicito.
_SCOPE_DECISO = {
    "climate.camera_t": True,
    "person.marta": True,
    "binary_sensor.fumo_cucina": True,
    "sensor.solare": True,
    "climate.bagno_1p_t_bagno_1p_t": True,
    "climate.senza_nome": True,
    "climate.strana": True,
    "light.lampadario": False,       # deciso, e lasciato fuori
    "device_tracker.nvr": False,
}


@pytest.fixture()
def coppia():
    a = _FintoArchivio(scope=_SCOPE_DECISO)
    return a, Watcher(a, now=lambda: 1787572800.0)


def test_una_cosa_dentro_lo_scope_si_annota(coppia):
    archivio, osservatore = coppia
    assert osservatore.watch_reading(
        _evento("climate.camera_t", "off", "heat")) is True
    assert archivio.annotati == [{"quando_ts": 1787572800.0, "source": "entita",
                                  "subject": "climate.camera_t",
                                  "da": "off", "a": "heat", "device_class": None,
                                  "state_class": None, "source_type": None,
                                  "friendly_name": None}]


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


def test_una_cosa_ESCLUSA_dallo_scope_NON_si_annota(coppia):
    """L'osservatore ha guardato questo soggetto e ha deciso che non pesa. La
    riga non si scrive: e' meta' della promessa del -83%."""
    archivio, osservatore = coppia
    assert osservatore.watch_reading(_evento("light.lampadario", "on", "off")) is False
    assert archivio.annotati == []


def test_un_soggetto_su_cui_NESSUNO_ha_deciso_non_entra(coppia):
    """**Il default e' fuori, ed e' una cosa diversa dall'esclusione.** Al
    primo avvio lo scope e' vuoto: se il rubinetto passasse cio' su cui nessuno
    si e' pronunciato, passerebbe **tutta la casa** -- 833 entita' -- proprio
    nel momento in cui l'osservatore non ha ancora parlato.

    Mutazione che la uccide: far passare il soggetto sconosciuto.
    """
    archivio, osservatore = coppia
    assert osservatore.watch_reading(
        _evento("sensor.mai_considerato", "1", "2")) is False
    assert archivio.annotati == []


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
        integrations=[], log_entries=[])
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
    osservatore.watch_system(problems=p, integrations=[], log_entries=[])
    archivio.annotati.clear()
    # giro 1: isteresi
    assert osservatore.watch_system(problems=[], integrations=[], log_entries=[]) == 0
    # giro 2: chiude
    assert osservatore.watch_system(problems=[], integrations=[], log_entries=[]) == 1
    assert archivio.annotati[0]["a"] == "chiuso"


def test_una_condizione_che_dura_non_si_riscrive(coppia):
    """Il lavoro periodico gira ogni pochi minuti: riscrivere la stessa
    condizione a ogni giro riempirebbe l'archivio di righe identiche e
    renderebbe impossibile sapere QUANDO e' cominciata."""
    archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.watch_system(problems=p, integrations=[], log_entries=[])
    archivio.annotati.clear()
    assert osservatore.watch_system(problems=p, integrations=[], log_entries=[]) == 0
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
                       "domain": "sonos", "state": "loaded"}], log_entries=[])
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
        integrations=[{"entry_id": "abc", "domain": "lifx", "title": "Abat-jour"}], log_entries=[])
    assert scritti == 0
    assert archivio.annotati == []


def test_not_loaded_NON_e_un_guasto(coppia):
    """«NOT_LOADED: The config entry has not been loaded. This is the initial
    state when a config entry is created or when Home Assistant is restarted»
    (developers.home-assistant.io/docs/config_entries_index/).

    Mutazione: aggiungere `not_loaded` a
    `ha_vocabulary.CONFIG_ENTRY_FAILURE_STATES` --
    questo test torna rosso, e l'archivio riprende a registrare come guasto lo
    stato in cui OGNI integrazione si trova subito dopo un riavvio."""
    archivio, osservatore = coppia
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "abc", "domain": "fritz",
                       "state": "not_loaded", "source": "user"}], log_entries=[])
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
                       "state": "setup_error", "source": "ignore"}], log_entries=[])
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
                       "state": "setup_in_progress"}], log_entries=[])
    assert scritti == 0
    assert archivio.annotati == []


def test_una_integrazione_in_unload_non_e_un_guasto(coppia):
    """'unload_in_progress' e' l'altro stato transitorio del boot, gemello
    di 'setup_in_progress': nasce e sparisce da solo in pochi secondi.
    Nessun test lo mandava finora -- toglierlo dalle condizioni sane restava
    verde. Mutazione: togliere 'unload_in_progress' da
    `ha_vocabulary.CONFIG_ENTRY_STATES` -- scriverebbe un guasto di rumore
    per ogni integrazione in fase di ricarica."""
    archivio, osservatore = coppia
    scritti = osservatore.watch_system(
        problems=[],
        integrations=[{"entry_id": "abc", "domain": "fritz",
                       "state": "unload_in_progress"}], log_entries=[])
    assert scritti == 0
    assert archivio.annotati == []


def test_osservate_dice_cosa_guarda_e_PERCHE(coppia):
    """La pagina dice cosa si guarda, **perche'**, e **chi l'ha deciso**: sono
    le tre cose da cui il proprietario puo' togliere qualcosa (spec §5.1/§11).
    Il perche' viene dallo scope, non da un'etichetta di categoria.

    **E non si aspetta un evento per comparire.** Prima l'elenco si riempiva
    osservando: un termostato acceso da giorni non produce cambi, e spariva
    dalla pagina che dichiara cosa si osserva -- cioe' proprio cio' che sta
    fermo. Adesso la fonte e' la decisione, che c'e' da prima dell'evento.

    Mutazione che la uccide: costruire l'elenco dai soggetti gia' visti.
    """
    _archivio, osservatore = coppia

    v = {o["soggetto"]: o for o in osservatore.watching()}

    assert v["climate.camera_t"]["motivo"] == "motivo di climate.camera_t"
    assert v["climate.camera_t"]["autore"] == "observer"
    assert v["climate.camera_t"]["da_quando_ts"] == 1787000000.0
    assert "person.marta" in v
    assert "light.lampadario" not in v      # deciso FUORI: non lo si guarda
    assert "gamba" not in v["climate.camera_t"]


# -- Correzione 5: `_watched` e `_conditions` sono UNA fonte sola per fatto ---

def test_osservate_mostra_una_condizione_dopo_guarda_sistema(coppia):
    _archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.watch_system(problems=p, integrations=[], log_entries=[])
    v = {o["soggetto"]: o for o in osservatore.watching()}
    assert v["problema:sonos.subscriptions_failed"]["autore"] is None


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
    osservatore.watch_system(problems=p, integrations=[], log_entries=[])
    # giro 1: isteresi, resta aperta
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
    soggetti_meta = {o["soggetto"] for o in osservatore.watching()}
    assert "problema:sonos.subscriptions_failed" in soggetti_meta
    # giro 2: si chiude
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
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
    assert soggetti["problema:sonos.subscriptions_failed"]["autore"] is None


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
            integrations=[], log_entries=[])
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
        integrations=[], log_entries=[])
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
        integrations=[], log_entries=[])
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
                       "title": "Abat-jour", "state": "setup_retry"}], log_entries=[])
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
                       "title": "Abat-jour", "state": "setup_retry"}], log_entries=[])
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
        integrations=[], log_entries=[])
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
        integrations=[], log_entries=[])
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
    # giro 1: apre
    osservatore.watch_system(problems=[], integrations=[_broken()], log_entries=[])
    # giro 2: assente
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
    closures = [r for r in archivio.annotati if r["a"] == "chiuso"]
    assert closures == []


def test_two_missing_rounds_close_the_episode(coppia):
    """L'isteresi non e' un rifiuto di chiudere: due giri consecutivi senza
    la condizione la chiudono. Senza questa prova la soglia potrebbe
    crescere all'infinito senza che nessuno se ne accorga.

    Gia' verde col codice di OGGI (che chiude dopo due giri mancanti
    consecutivi, l'isteresi di questo task): la si tiene comunque, perche'
    e' la prova che l'isteresi non diventa un rifiuto di chiudere.

    Mutazione: alzare la soglia a tre giri -- il test torna rosso su
    `assert len(closures) == 1`.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[_broken()], log_entries=[])
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
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
    osservatore.watch_system(problems=[], integrations=[_broken()], log_entries=[])
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
    osservatore.watch_system(problems=[], integrations=[_broken()], log_entries=[])
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
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
    healthy = {"domain": "buona", "issue_id": "b", "severity": "error"}
    broken = {"domain": "rotto", "issue_id": "x", "severity": "error"}
    # giro 1: buona.b apre
    osservatore.watch_system(problems=[healthy], integrations=[], log_entries=[])
    # giro 2: buona.b assente (1)
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
    with pytest.raises(RuntimeError):
        # giro 3: buona.b RICOMPARE (deve azzerarsi) mentre rotto.x NASCE e
        # il suo `record` solleva -- l'eccezione propaga.
        osservatore.watch_system(problems=[healthy, broken], integrations=[], log_entries=[])
    # giro 4: assente (1, non 2)
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
    closures = [r for r in archivio.annotati if r["a"] == "chiuso"]
    assert closures == []


# --------------------------------------------------------------------------
# Task 2 («le tracce e il log»): una voce del registro di errori
# (`HAClient.system_log()`, Task 1) e' una condizione che dura, con lo
# STESSO meccanismo dei due generi qui sopra -- nasce, ricorre, sparisce.
# --------------------------------------------------------------------------

def _log_entry(name="homeassistant.components.hydrawise", level="ERROR",
               count=3, first_occurred=1788595200.0):
    """La forma vera di una riga di `system_log/list`, verificata alla fonte
    dall'implementer del Task 1 (`homeassistant/components/system_log/
    __init__.py`, `LogEntry.to_dict()`): `source` e' una coppia (file, riga),
    non una stringa, l'ordine dell'elenco e' LIFO, e -- verificato di nuovo
    qui per questo task (stessa fonte, `LogEntry.__init__`:
    `self.first_occurred = self.timestamp = record.created`) --
    `first_occurred` e' un epoch in secondi (`float`), NON una stringa
    ISO-8601: e' il motivo per cui questa finta non passa da `instant_epoch`,
    a differenza di `last_changed` per un cambio di stato."""
    return {"name": name, "level": level, "count": count,
            "first_occurred": first_occurred,
            "source": ["hydrawise/coordinator.py", 88],
            "message": ["403 Forbidden"]}


def test_a_log_entry_opens_a_condition_with_its_level(coppia):
    """Il livello e' la condizione vera, come `setup_retry` per
    un'integrazione: `error` e `warning` non sono la stessa cosa, e la
    costante «aperto» direbbe meno di quello che sappiamo.

    Mutazione: scrivere `a="aperto"` invece del livello -- il test torna
    rosso su `assert riga["a"] == "ERROR"`.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[],
                             log_entries=[_log_entry()])
    riga = archivio.annotati[0]
    assert riga["subject"].startswith("log:")
    assert riga["a"] == "ERROR"
    assert riga["domain"] == "homeassistant.components.hydrawise"


def test_a_log_entry_that_stays_does_not_open_twice(coppia):
    """Una voce che ricorre e' lo STESSO episodio: `count` cresce dentro HA,
    non produce righe nuove da noi. E' il motivo per cui `count` non si
    scrive.

    Mutazione: costruire il soggetto includendo `count` -- il test torna
    rosso su `assert len(archivio.annotati) == 1`.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[],
                             log_entries=[_log_entry(count=3)])
    osservatore.watch_system(problems=[], integrations=[],
                             log_entries=[_log_entry(count=9)])
    assert len(archivio.annotati) == 1


def test_a_log_entry_is_born_on_the_round_clock_not_first_occurred(coppia):
    """Correzione del giro di revisione indipendente: la prima stesura usava
    `first_occurred` come istante di nascita ("l'episodio comincia quando HA
    dice che e' cominciato"). Giusto in astratto, rotto contro
    `aggregate_day`, che legge solo la finestra del giorno e ignora in
    silenzio una `chiuso` senza apertura nel giorno -- una nascita scritta
    oggi con l'istante di giorni fa (HA tiene le voci dall'ultimo suo
    riavvio) non sarebbe MAI stata aggregata. `quando_ts` deve significare
    la STESSA cosa per ogni soggetto -- l'orologio del giro -- come per
    `problema:` e `integrazione:`.

    Mutazione: scrivere `quando_ts=first_occurred` invece di `quando_ts=now`
    -- il test torna rosso su `assert riga["quando_ts"] == 1787572800.0`
    (diventa `1788595200.0`, l'istante fissato da `_log_entry`).
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[],
                             log_entries=[_log_entry(first_occurred=1788595200.0)])
    riga = archivio.annotati[0]
    assert riga["quando_ts"] == 1787572800.0  # l'orologio del giro (fixture `coppia`)


def test_a_log_entry_carries_first_occurred_in_its_own_column(coppia):
    """`first_occurred` non si butta -- prende una colonna propria
    (`store.py::_migration_4`), separata da `quando_ts`: un domani il
    lettore potra' avere «rilevato stamattina, va avanti dal 2» invece di
    una data sola (`facts.py::aggregate_day`, chiave `comparso_ts`).

    Mutazione: non passare `first_occurred` a `self._store.record(...)` (o
    passare sempre `None`) -- il test torna rosso su
    `assert riga["first_occurred"] == 1788595200.0`.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[],
                             log_entries=[_log_entry(first_occurred=1788595200.0)])
    riga = archivio.annotati[0]
    assert riga["first_occurred"] == 1788595200.0


def test_first_occurred_is_null_for_repairs_and_integrations(coppia):
    """`first_occurred` e' SOLO per una voce di log: un *repair* o
    un'integrazione non lo dichiarano mai, e la colonna resta `None` --
    non zero, non una data inventata.

    Mutazione: passare `first_occurred=0` (o un'altra costante) invece di
    `None` per un `problema:`/`integrazione:` -- il test torna rosso su
    `assert riga["first_occurred"] is None`.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(
        problems=[{"domain": "sonos", "issue_id": "x", "severity": "error"}],
        integrations=[], log_entries=[])
    riga = archivio.annotati[0]
    assert riga["subject"] == "problema:sonos.x"
    assert riga["first_occurred"] is None


def test_a_log_entry_that_leaves_the_list_closes_after_two_rounds(coppia):
    """Stessa isteresi dei due generi gemelli: un giro solo senza la riga
    non e' «e' finita» -- la deduplicazione di HA e il campionamento a dieci
    minuti si somigliano, e chiudere al primo giro mancante scriverebbe un
    falso positivo per ogni singolo buco di campionamento.

    Mutazione: chiudere al primo giro mancante (rimuovere l'isteresi) -- il
    primo `assert ... == 0` torna rosso.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[], log_entries=[_log_entry()])
    archivio.annotati.clear()
    # giro 1: isteresi
    assert osservatore.watch_system(problems=[], integrations=[], log_entries=[]) == 0
    # giro 2: chiude
    assert osservatore.watch_system(problems=[], integrations=[], log_entries=[]) == 1
    assert archivio.annotati[0]["a"] == "chiuso"


def test_a_log_entry_without_a_readable_first_occurred_writes_none(coppia):
    """`first_occurred` non e' sempre un numero -- una finta HA malformata, o
    un formato che cambiasse un domani: il ripiego dichiarato e' `None` nella
    colonna, non un istante inventato a partire da niente. `quando_ts` non
    dipende comunque da `first_occurred` (vedi il test gemello sopra), quindi
    resta l'orologio del giro in ogni caso.

    Mutazione: `else 0.0` invece di `else None` nel controllo di tipo -- il
    test torna rosso su `assert riga["first_occurred"] is None` (diventa
    `0.0`, un istante fabbricato che HA non ha mai detto).
    """
    archivio, osservatore = coppia
    entry = _log_entry(first_occurred="non-un-numero")
    osservatore.watch_system(problems=[], integrations=[], log_entries=[entry])
    riga = archivio.annotati[0]
    assert riga["quando_ts"] == 1787572800.0
    assert riga["first_occurred"] is None


def test_a_log_entry_with_a_boolean_first_occurred_does_not_become_an_epoch(coppia):
    """`bool` e' un sottotipo di `int` in Python (`isinstance(True, int) is
    True`): senza l'esclusione esplicita, un `first_occurred` malformato a
    `True` diventerebbe l'epoch fabbricato `1.0` (1970-01-01T00:00:01Z)
    invece di `None` -- inventare un istante che HA non ha mai detto.

    Mutazione: togliere `and not isinstance(raw_first_occurred, bool)` dal
    controllo -- il test torna rosso su
    `assert riga["first_occurred"] is None` (diventa `1.0`).
    """
    archivio, osservatore = coppia
    entry = _log_entry(first_occurred=True)
    osservatore.watch_system(problems=[], integrations=[], log_entries=[entry])
    riga = archivio.annotati[0]
    assert riga["first_occurred"] is None


def test_a_log_entry_without_a_readable_source_is_skipped(coppia):
    """Senza logger, livello o posizione nel sorgente leggibile non c'e'
    un'identita' stabile su cui deduplicare -- aprire comunque una
    condizione vorrebbe dire aprirla col soggetto sbagliato, o una nuova a
    ogni giro se la forma cambiasse ogni volta.

    Mutazione: togliere il controllo su `source_file`/`source_line` -- il
    test torna rosso su `assert archivio.annotati == []` (si aprirebbe
    comunque una riga per una voce senza posizione leggibile).
    """
    archivio, osservatore = coppia
    entry = _log_entry()
    entry["source"] = ["hydrawise/coordinator.py"]  # coppia incompleta
    osservatore.watch_system(problems=[], integrations=[], log_entries=[entry])
    assert archivio.annotati == []


def test_a_log_entry_title_is_the_first_message_line(coppia):
    """`domain` e `title` portano il logger e la prima riga del messaggio,
    cosi' il grezzo resta autosufficiente anche quando la voce sara' uscita
    dall'elenco di HA (HA tiene solo le ultime, non l'intera storia).

    Mutazione: tornare `None` invece di `message[0]` -- il test torna rosso
    su `assert riga["title"] == "403 Forbidden"`.
    """
    archivio, osservatore = coppia
    osservatore.watch_system(problems=[], integrations=[], log_entries=[_log_entry()])
    riga = archivio.annotati[0]
    assert riga["title"] == "403 Forbidden"


# ============================================================================
# Task 4 di «le tracce e il log»: l'evento SEGNA (mark_automation), la
# cadenza breve RACCOGLIE l'errore (watch_automation_outcome). L'isteresi per
# assenza di `watch_system` sopra NON si riusa qui -- vedi il docstring di
# `watch_automation_outcome` per il perche' (l'assenza dall'elenco delle
# automazioni segnate significa «non e' scattata», non «e' guarita»).
# ============================================================================

def test_the_event_marks_and_does_not_write(coppia):
    """L'evento scatta all'INIZIO delle azioni (`started_action()`,
    verificato alla fonte su `homeassistant/components/automation/
    __init__.py`, tag rilasciati `2024.7.0` e `2026.9.0`, stesso corpo su
    entrambi): in quell'istante la traccia (`trace/get`) non e' ancora
    completa, e scrivere l'esito qui significherebbe scrivere un esito che
    non esiste ancora. `mark_automation` segna e basta.

    Mutazione: far scrivere l'evento -- aggiungere `self._store.record(
    quando_ts=self._now(), source="sistema",
    subject=f"automazione:{entity_id}", da=None, a="scattata")` dentro
    `mark_automation`, subito dopo l'aggiunta al set -- il test torna rosso
    su `assert archivio.annotati == []`.
    """
    archivio, osservatore = coppia
    assert osservatore.mark_automation("automation.luci_sera") is True
    assert archivio.annotati == []


def test_only_a_failed_run_becomes_a_change(coppia):
    """«Se una cosa funziona non va segnalata»: sessantaquattro esecuzioni
    riuscite al giorno sono il contesto, non fatti compiuti. E una
    `failed_conditions` non e' un errore -- un'automazione che non agisce
    perche' la condizione e' falsa sta funzionando.

    Mutazione: far scrivere anche gli esiti `"finished"` -- togliere `if
    subject not in self._automation_faults: return False` dal ramo
    `"finished"` di `watch_automation_outcome` (lasciando solo la
    scrittura) -- il test torna rosso su
    `assert len(archivio.annotati) == 1`.
    """
    archivio, osservatore = coppia
    osservatore.watch_automation_outcome("automation.luci_sera", "finished")
    osservatore.watch_automation_outcome("automation.luci_sera", "failed_conditions")
    osservatore.watch_automation_outcome("automation.luci_sera", "error")
    assert len(archivio.annotati) == 1
    assert archivio.annotati[0]["a"] == "error"


def test_mark_automation_rejects_a_malformed_entity_id(coppia):
    """La forma `dominio.oggetto` si garantisce A MONTE, in questo metodo
    (Task 4): un identificatore senza punto non deve mai entrare in
    `marked_automations()`, che e' l'insieme riletto OGNI due minuti dalla
    cadenza breve di `server.py` -- e non c'e' nessun altro punto in cui
    filtrarlo dopo.

    (Dal Task 6 non e' piu' vero che raggiungerebbe `HAClient.
    automation_traces()`: quel metodo prende l'id di CONFIGURAZIONE, non
    l'`entity_id`, e un identificatore malformato non si risolve contro lo
    specchio. La guardia resta per la ragione detta sopra -- vedi il
    docstring di `mark_automation`.)

    Mutazione: togliere il controllo di forma (`if not isinstance(...) or
    not _ENTITY_ID_RE.match(entity_id): ...`), accettando qualunque
    stringa -- il test torna rosso su
    `assert osservatore.marked_automations() == []`.
    """
    archivio, osservatore = coppia
    assert osservatore.mark_automation("automazione_senza_punto") is False
    assert osservatore.marked_automations() == []
    assert archivio.annotati == []


def test_marked_automations_is_sorted_and_has_no_duplicates(coppia):
    """`marked_automations()` e' cio' che la cadenza breve di `server.py`
    rilegge a ogni giro: ordinata (non l'ordine di scoperta) perche' chi
    confronta due giri successivi nei log possa farlo a colpo d'occhio, e
    senza doppioni perche' un'automazione che scatta piu' volte resta UNA
    voce sola da rileggere.

    Mutazione (verificata eseguendola): `self._marked_automations` come
    `list` invece di `dict` (init `= []`, `mark_automation` con
    `.append(entity_id)` incondizionato invece del controllo "gia'
    presente? non toccare") -- il test torna rosso su
    `assert osservatore.marked_automations() ==
    ["automation.alfa", "automation.zeta"]` (tornerebbe una lista con
    `"automation.alfa"` ripetuta due volte)."""
    _archivio, osservatore = coppia
    osservatore.mark_automation("automation.zeta")
    osservatore.mark_automation("automation.alfa")
    osservatore.mark_automation("automation.alfa")
    assert osservatore.marked_automations() == ["automation.alfa", "automation.zeta"]


def test_mark_automation_records_the_name_from_the_event(coppia):
    """L'evento porta gia' il nome amichevole (`ATTR_NAME`, verificato alla
    fonte sui due estremi della finestra supportata,
    `automation/__init__.py` tag `2024.7.0` e `2026.9.0`): non usarlo
    ripeterebbe il difetto che questo sprint esiste per chiudere -- un
    soggetto raccontato dall'archivio senza che nessuna riga dica di cosa
    si tratti.

    Mutazione (verificata eseguendola): non salvare `name` (lasciare
    `self._marked_automations[entity_id] = None` incondizionato) -- il
    test torna rosso su
    `assert osservatore.automation_title("automation.luci_sera") ==
    "Luci sera"` (tornerebbe `None`)."""
    _archivio, osservatore = coppia
    osservatore.mark_automation("automation.luci_sera", name="Luci sera")
    assert osservatore.automation_title("automation.luci_sera") == "Luci sera"


def test_automation_title_is_none_for_an_unmarked_automation(coppia):
    """Nessuna mutazione onesta da dichiarare qui: e' il caso base di un
    `dict.get` su una chiave assente, non un ramo di codice dedicato."""
    _archivio, osservatore = coppia
    assert osservatore.automation_title("automation.mai_segnata") is None


def test_the_name_freezes_at_the_first_mark(coppia):
    """Un'automazione rinominata in HA dopo essere gia' stata segnata resta
    col nome VECCHIO fino al prossimo riavvio dell'add-on (quando l'insieme
    riparte vuoto e il prossimo scatto legge il nome nuovo): e' grezzo
    dichiarato, non un difetto -- lo stesso compromesso di
    `rebuild_conditions` con la data d'inizio oltre i 21 giorni di potatura.

    Mutazione (verificata eseguendola): togliere `if entity_id not in
    self._marked_automations:` (aggiornare il nome a ogni chiamata) -- il
    test torna rosso su
    `assert osservatore.automation_title("automation.x") == "Nome vecchio"`
    (tornerebbe `"Nome nuovo"`)."""
    _archivio, osservatore = coppia
    osservatore.mark_automation("automation.x", name="Nome vecchio")
    osservatore.mark_automation("automation.x", name="Nome nuovo")
    assert osservatore.automation_title("automation.x") == "Nome vecchio"


def test_watch_automation_outcome_writes_the_title_only_on_opening(coppia):
    """`domain`/`title` viaggiano verso l'archivio solo sulla riga
    d'APERTURA -- la chiusura non li porta, come gia' fa `watch_system` per
    le sue tre famiglie (nessuna delle quali passa `domain`/`title` alla
    propria chiusura).

    Mutazione (verificata eseguendola): passare `title=title` anche alla
    `record` di chiusura -- il test torna rosso su
    `assert "title" not in archivio.annotati[1]` (la chiave comparirebbe,
    anche se `None`)."""
    archivio, osservatore = coppia
    osservatore.watch_automation_outcome("automation.x", "error", title="Luci sera")
    assert archivio.annotati[0]["title"] == "Luci sera"
    osservatore.watch_automation_outcome("automation.x", "finished")
    assert "title" not in archivio.annotati[1]


def test_an_error_does_not_reopen_while_already_open(coppia):
    """Un errore gia' aperto non deve riscriversi a ogni giro: senza questa
    guardia un'automazione persistentemente rotta produrrebbe una riga
    nuova ogni due minuti (la cadenza di `server.py`), invece di UN
    episodio con una durata che vuol dire qualcosa.

    Mutazione: togliere `if subject in self._automation_faults: return
    False` dal ramo `"error"` -- il test torna rosso (verificato
    eseguendolo) su
    `assert osservatore.watch_automation_outcome("automation.x", "error") is False`
    (la seconda chiamata tornerebbe `True`, riscrivendo l'errore anche se
    l'episodio era gia' aperto).
    """
    archivio, osservatore = coppia
    assert osservatore.watch_automation_outcome("automation.x", "error") is True
    assert osservatore.watch_automation_outcome("automation.x", "error") is False
    assert len(archivio.annotati) == 1


def test_a_finished_run_closes_an_open_fault(coppia):
    """Apre sull'errore, chiude sull'esito riuscito SUCCESSIVO: la scrittura
    di chiusura porta `da=None, a="chiuso"` (la memoria in RAM non ricorda
    l'ultima condizione, solo il soggetto -- stessa disciplina di
    `watch_system`), senza `domain`/`title` (nessuno dei due chiamanti veri
    li passa alla chiusura).

    Nota sull'identita': si confronta `archivio.annotati[-1]` (l'oggetto
    vero appena scritto) e non una copia fatta prima -- qui e' onesto
    perche' la finta non muta MAI le righe gia' scritte (`_FintoArchivio.
    record` fa solo `self.annotati.append(kw)`), a differenza di un caso in
    cui la stessa variabile passata alla finta venisse mutata sul posto
    dopo la chiamata.

    Mutazione (verificata eseguendola): togliere
    `self._automation_faults.discard(subject)` dal ramo `"finished"` -- il
    test torna rosso su
    `assert "automazione:automation.x" not in osservatore._automation_faults`
    (il soggetto resterebbe nell'insieme anche dopo la chiusura).
    """
    archivio, osservatore = coppia
    osservatore.watch_automation_outcome("automation.x", "error")
    assert osservatore.watch_automation_outcome("automation.x", "finished") is True
    assert archivio.annotati[-1] == {
        "quando_ts": 1787572800.0, "source": "sistema",
        "subject": "automazione:automation.x", "da": None, "a": "chiuso"}
    assert "automazione:automation.x" not in osservatore._automation_faults


def test_a_finished_run_with_nothing_open_writes_nothing(coppia):
    """Un'esecuzione riuscita chiude ma non apre MAI: senza un errore aperto
    prima, non c'e' niente da chiudere, e non si scrive niente.

    Mutazione (verificata eseguendola): togliere `if subject not in
    self._automation_faults: return False` dal ramo `"finished"` -- il test
    torna rosso su
    `assert osservatore.watch_automation_outcome("automation.x", "finished") is False`
    (tornerebbe `True`, scrivendo una chiusura senza nessun errore aperto).
    """
    archivio, osservatore = coppia
    assert osservatore.watch_automation_outcome("automation.x", "finished") is False
    assert archivio.annotati == []


def test_an_unhandled_outcome_does_nothing(coppia):
    """`outcome` diversi da `"error"`/`"finished"` -- qui `"aborted"`, uno
    dei valori veri che HA scrive in `script_execution`
    (`helpers/script.py`, tag `2026.9.0`, `script_execution_set("aborted")`
    per un `_AbortScript`/`_ConditionFail`) -- non sono ne' un successo ne'
    un errore per questo verticale (il piano ne discute solo due,
    `"finished"` ed `"error"`): non scrivono e non toccano lo stato.
    Un guasto non misurato non si inventa.

    Mutazione (verificata eseguendola): cambiare `if outcome == "error":`
    in `if outcome != "finished":` (un bug plausibile -- trattare "non e'
    un successo" come sinonimo di "e' un errore") -- il test torna rosso su
    `assert osservatore.watch_automation_outcome("automation.x", "aborted") is False`
    (tornerebbe `True`, aprendo un episodio per un `"aborted"`)."""
    archivio, osservatore = coppia
    assert osservatore.watch_automation_outcome("automation.x", "aborted") is False
    assert archivio.annotati == []
    assert osservatore._automation_faults == set()


def test_a_cancelled_outcome_does_nothing(coppia):
    """`"cancelled"` (giro di correzioni, rilievo 3 di «le tracce e il
    log») e' il settimo valore itemizzato nel docstring, non uno dei sei
    coperti da `"aborted"`: `_ScriptRun.async_run` lo scrive quando una
    run riprende dopo un passo e trova `self._stop` gia' impostato da
    un'altra (`mode: restart` che ne fa ripartire una nuova, o
    `automation.turn_off` che ferma le azioni in corso) -- verificato alla
    fonte agli estremi della finestra supportata, tag `2024.7.0` e
    `2026.9.0`. Stesso trattamento di `"aborted"`: non e' ne' un successo
    ne' un errore per questo verticale, non scrive e non tocca lo stato.

    Mutazione (verificata eseguendola): cambiare `if outcome == "error":`
    in `if outcome != "finished":` -- il test torna rosso su
    `assert osservatore.watch_automation_outcome("automation.x", "cancelled") is False`
    (tornerebbe `True`, aprendo un episodio per un `"cancelled"`)."""
    archivio, osservatore = coppia
    assert osservatore.watch_automation_outcome("automation.x", "cancelled") is False
    assert archivio.annotati == []
    assert osservatore._automation_faults == set()


def test_rebuild_reseeds_an_open_automation_fault():
    """Un `automazione:` gia' aperto (scritto da un giro precedente
    dell'add-on ora spento) deve tornare a far parte di
    `self._automation_faults` dopo la ricostruzione -- altrimenti un esito
    riuscito successivo non troverebbe niente da chiudere, e l'episodio
    resterebbe aperto per sempre anche se l'automazione fosse guarita nel
    frattempo.

    Mutazione: nella ricostruzione, smettere di popolare
    `self._automation_faults` (tornare al comportamento pre-Task-4,
    filtrando solo `self._conditions`) -- il test torna rosso (verificato
    eseguendolo) su
    `assert "automazione:automation.rotta" in osservatore._automation_faults`
    (l'insieme resterebbe vuoto).
    """
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema", "automazione:automation.rotta", None, "error"),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    assert "automazione:automation.rotta" in osservatore._automation_faults
    closed = osservatore.watch_automation_outcome("automation.rotta", "finished")
    assert closed is True
    assert archivio.annotati[-1]["a"] == "chiuso"


def test_rebuild_keeps_automation_faults_out_of_watch_system_hysteresis():
    """L'incompatibilita' vera fra i due insiemi (vedi il commento su
    `self._automation_faults` in `Watcher.__init__`): se un `automazione:`
    finisse mescolato in `self._conditions`, il ciclo dei "mancati" di
    `watch_system` lo chiuderebbe da solo dopo due giri -- anche se
    l'automazione fosse ancora rotta davvero -- perche' quel ciclo non
    guarda mai le tracce, solo l'elenco di problemi/integrazioni/log che
    riceve (che non contiene MAI un soggetto `automazione:`).

    **La precondizione strutturale (l'automazione finisce davvero in
    `_automation_faults`, non in `_conditions`) e' gia' sorvegliata da
    `test_rebuild_reseeds_an_open_automation_fault` qui sopra, e non si
    ripete come assert PRIMA del comportamento** (giro di correzioni,
    rilievo 3: la prima stesura di questo test la ripeteva qui, e pytest si
    fermava li' -- l'assert comportamentale sotto non arrossiva mai per
    primo, quindi non discriminava affatto la mutazione che questo test
    dice di sorvegliare). Resta solo la precondizione che questo scenario
    aggiunge (il problema seminato correttamente), che la mutazione qui
    sotto NON tocca -- non oscura niente.

    Mutazione (verificata eseguendola): nella ricostruzione, rimettere OGNI
    soggetto `sistema` aperto (compreso `automazione:`) in
    `self._conditions`, come prima del Task 4 -- il test torna rosso sul
    PRIMO assert dopo la precondizione, `assert scritti == 1` (tornerebbe
    `2`: `watch_system` chiuderebbe anche l'automazione dopo l'isteresi di
    due giri, non solo il problema).
    """
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema",
                "problema:sonos.subscriptions_failed", None, "aperto"),
        _cambio(1787000000.0, "sistema", "automazione:automation.rotta", None, "error"),
    ])
    osservatore = Watcher(archivio, now=lambda: 1787572800.0)
    osservatore.rebuild_conditions()
    # Precondizione di QUESTO scenario (il problema, non l'automazione: vedi
    # sopra il perche' l'automazione non si ricontrolla qui) -- sopravvive
    # intatta anche sotto la mutazione, quindi non oscura il comportamento.
    assert "problema:sonos.subscriptions_failed" in osservatore._conditions

    # Due giri di `watch_system` senza il problema fra i problemi: lo
    # chiude dopo l'isteresi di due giri -- ma non deve MAI toccare
    # l'automazione, che non passa mai da questo metodo. Questo e' il
    # PRIMO assert che la mutazione puo' arrossire.
    osservatore.watch_system(problems=[], integrations=[], log_entries=[])
    scritti = osservatore.watch_system(problems=[], integrations=[], log_entries=[])
    assert scritti == 1  # solo la chiusura del problema
    assert "automazione:automation.rotta" in osservatore._automation_faults


# -- giro di correzioni sul Task 7: `watching()` mostra anche le automazioni --

def test_watching_shows_an_open_automation_fault(coppia):
    """`watching()` e' cio' che l'osservatore sta guardando ADESSO: un
    guasto di automazione aperto ne fa parte tanto quanto un'integrazione
    rotta, non e' cosa da tenere fuori dalla pagina di prodotto.

    Mutazione (verificata eseguendola): togliere `automation` dalla lista
    che finisce in `sorted([*entity, *system, *automation], ...)` (tornare
    a `[*entity, *system]`) -- il test torna rosso su
    `assert "automazione:automation.rotta" in soggetti` (l'insieme non lo
    conterrebbe piu').
    """
    _archivio, osservatore = coppia
    aperto = osservatore.watch_automation_outcome("automation.rotta", "error")
    assert aperto is True
    soggetti = {o["soggetto"]: o for o in osservatore.watching()}
    assert "automazione:automation.rotta" in soggetti
    assert soggetti["automazione:automation.rotta"]["autore"] is None


# -- Il nome amichevole: la quarta chiave dello STESSO dizionario -----------

def test_il_nome_amichevole_dell_evento_entra_nel_grezzo(coppia):
    """`attributes` e' gia' letto e gia' spremuto per tre chiavi: la quarta
    e' gratis, e senza di lei il nome andrebbe risolto dopo -- cioe' sarebbe
    il nome di oggi attribuito a un fatto di ieri, e sarebbe ASSENTE per un
    oggetto piu' vecchio dei 22 giorni di grezzo.

    E' la stringa che Home Assistant ha GIA' composto
    (`helpers/entity.py:1161` -> `entity_registry.py:592-603` @ `2026.9.1`),
    non una ricomposta da noi da `name`/`original_name`/dispositivo.

    Mutazione ESEGUITA: togliere la riga
    `friendly_name=_text_or_none(attributes.get("friendly_name"))` dalla
    chiamata a `record()` in `watch_reading` (`mind/watcher.py`) -- il test
    torna rosso su `assert riga["friendly_name"] == "Termostato Bagno"`
    (`KeyError: 'friendly_name'`).
    """
    archivio, osservatore = coppia
    assert osservatore.watch_reading(
        _evento("climate.bagno_1p_t_bagno_1p_t", "off", "heat",
                {"friendly_name": "Termostato Bagno"})) is True
    riga = archivio.annotati[0]
    assert riga["friendly_name"] == "Termostato Bagno"
    assert riga["subject"] == "climate.bagno_1p_t_bagno_1p_t"


def test_un_evento_senza_nome_amichevole_annota_none_non_l_entity_id(coppia):
    """Quando l'attributo non c'e' (HA non lo scrive se il nome composto e'
    vuoto), il grezzo porta `None` -- **non** l'`entity_id` messo li' per
    riempire il campo. Inventare un nome dall'id e' esattamente cio' che
    questa fetta rifiuta: se il nome manca, chi legge lo dice.

    Mutazione ESEGUITA: scrivere
    `friendly_name=_text_or_none(attributes.get("friendly_name")) or str(eid)`
    -- il test torna rosso su `assert riga["friendly_name"] is None`.
    """
    archivio, osservatore = coppia
    assert osservatore.watch_reading(
        _evento("climate.senza_nome", "off", "heat")) is True
    riga = archivio.annotati[0]
    assert riga["friendly_name"] is None


def test_un_nome_amichevole_non_testuale_non_entra_nel_grezzo(coppia):
    """`_text_or_none` vale anche per la quarta chiave: un tipo inatteso non
    diventa un `str(valore)` che scriverebbe spazzatura nella colonna. Una
    regola sola per tutti e quattro gli attributi, non una eccezione.

    Mutazione ESEGUITA: passare `attributes.get("friendly_name")` grezzo
    invece che attraverso `_text_or_none` -- il test torna rosso su
    `assert riga["friendly_name"] is None` (diventa la lista `[]`).
    """
    archivio, osservatore = coppia
    assert osservatore.watch_reading(
        _evento("climate.strana", "off", "heat", {"friendly_name": []})) is True
    assert archivio.annotati[0]["friendly_name"] is None


def test_un_evento_di_solo_attributo_non_scrive_una_riga(coppia):
    """**Regola di scrittura §5.3.2 della spec dei tre attori.** Home Assistant
    emette `state_changed` anche quando cambia solo un ATTRIBUTO: lo stato di
    partenza e quello d'arrivo sono lo stesso, e la riga non dice niente su
    cosa e' successo in casa.

    Misurato sulla casa vera il 10/09/2026: gli otto termostati producono
    **6.446 righe al giorno, di cui 8 vere** -- un solo cambio di stato
    ciascuno in 24 ore. Su tutta la casa sono **6.503 righe al giorno** su
    29.227.

    E c'e' un secondo guasto sotto il primo, misurato: `last_changed` **non si
    muove** per un evento di solo attributo, quindi quelle righe nascono
    datate all'ultimo cambio VERO -- il 10/09 tutti e otto i termostati
    portavano `last_changed` del 06/09. Finivano fuori dalla finestra del
    giorno, e l'aggregazione non le vedeva mai.

    Mutazione che la uccide: togliere il confronto `da != a`.
    """
    archivio, osservatore = coppia
    osservatore.watch_reading(_evento("climate.camera_t", "off", "heat"))
    osservatore.watch_reading(_evento("climate.camera_t", "heat", "heat",
                                      {"hvac_action": "heating"}))
    osservatore.watch_reading(_evento("climate.camera_t", "heat", "heat",
                                      {"hvac_action": "idle"}))

    assert [r["a"] for r in archivio.annotati] == ["heat"]


def test_un_soggetto_che_cambia_solo_attributi_resta_fra_quelli_guardati(coppia):
    """Il filtro `da != a` toglie una RIGA, non un soggetto. Un termostato
    acceso da giorni non produce cambi di stato, ma l'osservatore lo sta
    guardando eccome -- e la pagina che dichiara cosa guarda deve dirlo, o
    sparirebbe proprio cio' che sta fermo (ed e' il secondo innesco
    dell'analista: «qualcosa e' stabile e costa»).

    **Dall'11/09/2026 la proprieta' e' strutturale, non piu' un ordine di
    righe.** Prima dipendeva dal segnare il soggetto PRIMA del filtro dentro
    `watch_reading`; adesso la pagina legge lo scope, e un soggetto deciso c'e'
    anche se non e' mai passato un evento. Qui si guarda che le due cose
    convivano: la riga non si scrive, il soggetto resta.
    """
    archivio, osservatore = coppia

    assert osservatore.watch_reading(
        _evento("climate.camera_t", "heat", "heat",
                {"hvac_action": "heating"})) is False

    assert archivio.annotati == []
    assert "climate.camera_t" in {g["soggetto"] for g in osservatore.watching()}
