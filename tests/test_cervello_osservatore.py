"""L'osservatore al rubinetto: filtra col pavimento e annota, senza giudicare.

Il rubinetto e' lo STESSO che alimenta lo specchio delle entita'
(`HAClient.add_state_listener`): non se ne apre un secondo, per la stessa
ragione per cui non si apre un secondo canale verso Home Assistant.
"""
import pytest

from hiris.app.cervello.osservatore import Osservatore


class _FintoArchivio:
    """La finta deve saper produrre il difetto che sorveglia: oltre ad
    `annota`, tiene righe di `cambi` VERE (per la ricostruzione all'avvio, D1
    del mandato) e puo' sollevare a comando (per provare che la ricostruzione
    non si ferma se l'archivio non risponde, e che `guarda_cambio` non
    solleva mai se l'archivio e' rotto).

    **`cambi()` applica `fonte` e `limite` davvero, e ordina ASC come quella
    vera**: una finta che accetta questi parametri e li ignora e' una finta
    che non puo' fallire, e non avrebbe potuto sorvegliare D1."""

    def __init__(self, cambi_esistenti=None, *, cambi_solleva=False,
                 annota_solleva=False, annota_solleva_per=None):
        self.annotati = []
        self._cambi = list(cambi_esistenti or [])
        self._cambi_solleva = cambi_solleva
        self._annota_solleva = annota_solleva
        self._annota_solleva_per = set(annota_solleva_per or [])

    def annota(self, **kw):
        if self._annota_solleva or kw.get("soggetto") in self._annota_solleva_per:
            raise RuntimeError("archivio rotto")
        self.annotati.append(kw)

    def cambi(self, *, da_ts, a_ts, soggetto=None, fonte=None, limite=200_000):
        if self._cambi_solleva:
            raise RuntimeError("archivio irraggiungibile")
        righe = [c for c in self._cambi if da_ts <= c["quando_ts"] < a_ts]
        if soggetto is not None:
            righe = [c for c in righe if c["soggetto"] == soggetto]
        if fonte is not None:
            righe = [c for c in righe if c["fonte"] == fonte]
        righe = sorted(righe, key=lambda c: c["quando_ts"])
        return righe[:max(1, limite)]


def _evento(eid, da, a, attributi=None):
    """La forma vera di `state_changed` come Home Assistant la manda."""
    return {"entity_id": eid,
            "old_state": None if da is None else {"state": da},
            "new_state": None if a is None else {
                "state": a, "attributes": attributi or {},
                "last_changed": "2026-08-24T12:00:00+00:00"}}


def _cambio(ts, fonte, soggetto, da, a):
    """Una riga di `cambi()` come la torna l'archivio vero."""
    return {"quando_ts": ts, "fonte": fonte, "soggetto": soggetto, "da": da, "a": a}


@pytest.fixture()
def coppia():
    a = _FintoArchivio()
    return a, Osservatore(a, adesso=lambda: 1787572800.0)


def test_una_cosa_del_pavimento_si_annota(coppia):
    archivio, osservatore = coppia
    assert osservatore.guarda_cambio(
        _evento("climate.camera_t", "off", "heat")) is True
    assert archivio.annotati == [{"quando_ts": 1787572800.0, "fonte": "entita",
                                  "soggetto": "climate.camera_t",
                                  "da": "off", "a": "heat", "device_class": None,
                                  "state_class": None, "source_type": None}]


# -- Correzione 0: il grezzo porta le tre classi che il pavimento legge -----

def test_guarda_cambio_scrive_le_tre_classi_quando_ci_sono(coppia):
    """Senza le tre classi nel grezzo, `aggrega_giorno` non puo' sapere che
    `binary_sensor.fumo_cucina` e' un rilevatore di fumo: il genere `consumo`
    e la sesta gamba per classe non nascono mai (Task 3, punto 0)."""
    archivio, osservatore = coppia
    ev = _evento("binary_sensor.fumo_cucina", "off", "on",
                 {"device_class": "smoke", "state_class": "measurement",
                  "source_type": "cloud"})
    assert osservatore.guarda_cambio(ev) is True
    riga = archivio.annotati[0]
    assert riga["device_class"] == "smoke"
    assert riga["state_class"] == "measurement"
    assert riga["source_type"] == "cloud"


def test_guarda_cambio_scrive_none_quando_le_classi_mancano(coppia):
    archivio, osservatore = coppia
    osservatore.guarda_cambio(_evento("climate.camera_t", "off", "heat"))
    riga = archivio.annotati[0]
    assert riga["device_class"] is None
    assert riga["state_class"] is None
    assert riga["source_type"] is None


# -- Giro di pulizia (26 agosto), punto 6: due residui dell'osservatore ----

def test_guarda_cambio_scrive_none_per_attributi_non_testuali(coppia):
    """`_testo_o_none` promette che un tipo inatteso -- numero, lista, dict,
    stringa di soli spazi -- diventi `None`, non un `str(valore)` che
    scriverebbe testo spazzatura nella colonna. Nessun test lo mandava
    finora: un intero finirebbe scritto in una colonna di testo. Mutazione:
    togliere il controllo `isinstance(valore, str)` da `_testo_o_none` --
    tornerebbe il valore grezzo cosi' com'e', invece di `None`."""
    archivio, osservatore = coppia
    ev = _evento("climate.camera_t", "off", "heat",
                 {"device_class": 42, "state_class": ["misura"],
                  "source_type": "   "})
    assert osservatore.guarda_cambio(ev) is True
    riga = archivio.annotati[0]
    assert riga["device_class"] is None
    assert riga["state_class"] is None
    assert riga["source_type"] is None


def test_una_cosa_fuori_dal_pavimento_NON_si_annota(coppia):
    archivio, osservatore = coppia
    assert osservatore.guarda_cambio(_evento("light.lampadario", "on", "off")) is False
    assert archivio.annotati == []


def test_il_tracker_del_router_non_entra_dal_rubinetto(coppia):
    """La misura del 26/08: e' la classe piu' numerosa fra quelle escluse, e
    passa proprio da qui."""
    archivio, osservatore = coppia
    assert osservatore.guarda_cambio(
        _evento("device_tracker.nvr", "home", "not_home",
                {"source_type": "router"})) is False


def test_l_istante_e_quello_del_CAMBIO_non_quello_della_scrittura(coppia):
    """`last_changed` dice quando la casa e' cambiata; l'orologio nostro dice
    quando l'abbiamo saputo. Annotare il secondo sposterebbe ogni oggetto di
    quel tanto, e nessuno se ne accorgerebbe."""
    archivio, osservatore = coppia
    ev = _evento("climate.camera_t", "off", "heat")
    ev["new_state"]["last_changed"] = "2026-08-24T11:30:00+00:00"
    osservatore.guarda_cambio(ev)
    assert archivio.annotati[0]["quando_ts"] == 1787571000.0  # 2026-08-24T11:30:00+00:00


def test_senza_last_changed_si_usa_l_orologio(coppia, caplog):
    """Il ripiego era muto: se HA smettesse di mandare `last_changed`, ogni
    cambio slitterebbe all'istante in cui l'abbiamo saputo e nessuno se ne
    accorgerebbe. La mutazione 'cancella `or self._adesso()`' deve arrossire
    questo test, non restare verde."""
    import logging
    archivio, osservatore = coppia
    ev = _evento("climate.camera_t", "off", "heat")
    del ev["new_state"]["last_changed"]
    with caplog.at_level(logging.DEBUG, logger="hiris.app.cervello.osservatore"):
        assert osservatore.guarda_cambio(ev) is True
    assert archivio.annotati[0]["quando_ts"] == 1787572800.0  # adesso() iniettato
    assert any("last_changed" in r.message for r in caplog.records)


def test_un_evento_senza_stato_nuovo_non_solleva(coppia):
    """Un'entita' rimossa manda `new_state: None`. L'osservatore gira per
    sempre: un'eccezione qui lo fermerebbe su un evento solo."""
    archivio, osservatore = coppia
    assert osservatore.guarda_cambio(_evento("climate.camera_t", "heat", None)) is False


def test_un_evento_malformato_non_solleva(coppia):
    archivio, osservatore = coppia
    for ev in [{}, {"entity_id": None}, {"entity_id": "climate.x"}, None]:
        assert osservatore.guarda_cambio(ev) is False


def test_guarda_cambio_con_archivio_rotto_non_solleva():
    """Tutti gli ingressi malformati muoiono sulle guardie in cima al metodo:
    il ramo `except` non era mai raggiunto, e la mutazione 'togli il
    try/except' restava verde. Qui l'archivio stesso solleva."""
    archivio = _FintoArchivio(annota_solleva=True)
    osservatore = Osservatore(archivio, adesso=lambda: 1787572800.0)
    assert osservatore.guarda_cambio(_evento("climate.camera_t", "off", "heat")) is False


def test_un_problema_di_HA_diventa_un_cambio(coppia):
    """Un'integrazione rotta non e' un cambio di stato -- ma il suo COMPARIRE
    lo e'. Cosi' la riga del grezzo resta una sola."""
    archivio, osservatore = coppia
    scritti = osservatore.guarda_sistema(
        problemi=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrazioni=[])
    assert scritti == 1
    assert archivio.annotati[0]["fonte"] == "sistema"
    assert archivio.annotati[0]["soggetto"] == "problema:sonos.subscriptions_failed"
    assert archivio.annotati[0]["a"] == "aperto"


def test_un_problema_che_sparisce_diventa_un_cambio(coppia):
    archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.guarda_sistema(problemi=p, integrazioni=[])
    archivio.annotati.clear()
    assert osservatore.guarda_sistema(problemi=[], integrazioni=[]) == 1
    assert archivio.annotati[0]["a"] == "chiuso"


def test_una_condizione_che_dura_non_si_riscrive(coppia):
    """Il lavoro periodico gira ogni pochi minuti: riscrivere la stessa
    condizione a ogni giro riempirebbe l'archivio di righe identiche e
    renderebbe impossibile sapere QUANDO e' cominciata."""
    archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.guarda_sistema(problemi=p, integrazioni=[])
    archivio.annotati.clear()
    assert osservatore.guarda_sistema(problemi=p, integrazioni=[]) == 0
    assert archivio.annotati == []


def test_un_integrazione_non_caricata_diventa_un_cambio(coppia):
    """Misurato sulla casa vera: 9 integrazioni su 53 non sono caricate."""
    archivio, osservatore = coppia
    scritti = osservatore.guarda_sistema(
        problemi=[],
        integrazioni=[{"entry_id": "abc", "title": "Fritz-esterno",
                       "domain": "fritz", "state": "not_loaded"},
                      {"entry_id": "def", "title": "Sonos",
                       "domain": "sonos", "state": "loaded"}])
    assert scritti == 1
    assert archivio.annotati[0]["soggetto"] == "integrazione:abc"


def test_una_integrazione_in_setup_non_e_un_guasto(coppia):
    """Il boot di HA fa nascere e sparire `setup_in_progress` in pochi
    secondi: se il primo giro del lavoro periodico cadesse durante il boot,
    trattarlo come guasto scriverebbe una coppia di righe di rumore per ogni
    integrazione."""
    archivio, osservatore = coppia
    scritti = osservatore.guarda_sistema(
        problemi=[],
        integrazioni=[{"entry_id": "abc", "domain": "fritz",
                       "state": "setup_in_progress"}])
    assert scritti == 0
    assert archivio.annotati == []


def test_una_integrazione_in_unload_non_e_un_guasto(coppia):
    """'unload_in_progress' e' l'altro stato transitorio del boot, gemello
    di 'setup_in_progress': nasce e sparisce da solo in pochi secondi.
    Nessun test lo mandava finora -- toglierlo da
    `_STATI_INTEGRAZIONE_TRANSITORI` restava verde. Mutazione: togliere
    'unload_in_progress' dall'insieme -- scriverebbe un guasto di rumore
    per ogni integrazione in fase di ricarica."""
    archivio, osservatore = coppia
    scritti = osservatore.guarda_sistema(
        problemi=[],
        integrazioni=[{"entry_id": "abc", "domain": "fritz",
                       "state": "unload_in_progress"}])
    assert scritti == 0
    assert archivio.annotati == []


def test_osservate_dice_cosa_guarda_e_PERCHE(coppia):
    """La pagina deve poter distinguere cio' che e' nel pavimento (e non si
    toglie) da cio' che l'obiettivo ha aggiunto (e si toglie). Un elenco che
    non li distingue non si puo' usare per decidere."""
    archivio, osservatore = coppia
    osservatore.guarda_cambio(_evento("climate.camera_t", "off", "heat"))
    osservatore.guarda_cambio(_evento("person.marta", "home", "not_home"))
    v = {o["soggetto"]: o for o in osservatore.osservate()}
    assert v["climate.camera_t"]["gamba"] == "comfort"
    assert v["climate.camera_t"]["provenienza"] == "pavimento"
    assert v["person.marta"]["gamba"] == "chi c'e'"


# -- Correzione 5: `_viste` e `_condizioni` sono UNA fonte sola per fatto ---

def test_osservate_mostra_una_condizione_dopo_guarda_sistema(coppia):
    archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.guarda_sistema(problemi=p, integrazioni=[])
    v = {o["soggetto"]: o for o in osservatore.osservate()}
    assert v["problema:sonos.subscriptions_failed"]["gamba"] == "buono stato"


def test_osservate_non_mostra_piu_una_condizione_chiusa(coppia):
    """All'opposto del difetto gemello: una condizione chiusa non deve
    restare per sempre in cio' che `osservate()` mostra."""
    archivio, osservatore = coppia
    p = [{"domain": "sonos", "issue_id": "subscriptions_failed", "severity": "error"}]
    osservatore.guarda_sistema(problemi=p, integrazioni=[])
    osservatore.guarda_sistema(problemi=[], integrazioni=[])  # si chiude
    soggetti = {o["soggetto"] for o in osservatore.osservate()}
    assert "problema:sonos.subscriptions_failed" not in soggetti


def test_osservate_include_una_condizione_ricostruita_al_riavvio():
    """Senza seminare `_viste`, un guasto ricostruito dopo un riavvio
    sparirebbe da `osservate()` per sempre -- non verra' mai piu' riscritto
    'aperto', che e' proprio lo scopo di D1. Deve derivare da `_condizioni`."""
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema",
                "problema:sonos.subscriptions_failed", None, "aperto"),
    ])
    osservatore = Osservatore(archivio, adesso=lambda: 1787572800.0)
    osservatore.ricostruisci_condizioni()
    soggetti = {o["soggetto"]: o for o in osservatore.osservate()}
    assert soggetti["problema:sonos.subscriptions_failed"]["gamba"] == "buono stato"


# -- Correzione 6: `guarda_sistema` aggiorna la memoria in modo incrementale

def test_guarda_sistema_ricorda_solo_cio_che_ha_scritto_davvero(coppia):
    """Se `annota` solleva a meta', le righe 'aperto' gia' scritte devono
    restare ricordate (altrimenti il giro dopo le riscriverebbe con una
    seconda data di nascita), e quella fallita NON deve esserlo. La
    mutazione e' rimettere `self._condizioni = aperte` dopo i due cicli."""
    archivio = _FintoArchivio(annota_solleva_per={"problema:rotto.x"})
    osservatore = Osservatore(archivio, adesso=lambda: 1787572800.0)
    with pytest.raises(RuntimeError):
        osservatore.guarda_sistema(
            problemi=[{"domain": "buona", "issue_id": "a", "severity": "error"},
                      {"domain": "rotto", "issue_id": "x", "severity": "error"}],
            integrazioni=[])
    # sorted(): "problema:buona.a" viene prima di "problema:rotto.x", quindi
    # e' gia' stata scritta quando "rotto.x" solleva.
    assert "problema:buona.a" in osservatore._condizioni
    assert "problema:rotto.x" not in osservatore._condizioni


# -- D1: la ricostruzione dello stato di sistema dall'archivio, al riavvio --
#
# `self._condizioni` vive solo in RAM. Al riavvio dell'add-on (che succede a
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
    osservatore = Osservatore(archivio, adesso=lambda: 1787572800.0)
    osservatore.ricostruisci_condizioni()
    scritti = osservatore.guarda_sistema(
        problemi=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrazioni=[])
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
    osservatore = Osservatore(archivio, adesso=lambda: 1787572800.0)
    osservatore.ricostruisci_condizioni()
    scritti = osservatore.guarda_sistema(
        problemi=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrazioni=[])
    assert scritti == 1
    assert archivio.annotati[0]["a"] == "aperto"


def test_la_ricostruzione_non_solleva_se_l_archivio_non_risponde():
    """Un'eccezione qui non deve fermare l'avvio dell'add-on: si riparte da
    vuoto, esattamente come al primo avvio in assoluto."""
    archivio = _FintoArchivio(cambi_solleva=True)
    osservatore = Osservatore(archivio, adesso=lambda: 1787572800.0)
    osservatore.ricostruisci_condizioni()  # non deve sollevare
    scritti = osservatore.guarda_sistema(
        problemi=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrazioni=[])
    assert scritti == 1  # riparte da vuoto: la condizione sembra nuova


def test_la_ricostruzione_ignora_le_righe_di_entita():
    """Le finte dei tre test D1 qui sopra contenevano SOLO righe di sistema:
    cancellare `fonte="sistema"` dalla chiamata a `cambi()` restava verde.
    Una riga di entita' con `a="aperto"` basta a farlo notare, se la
    ricostruzione la trattasse come una condizione di sistema."""
    archivio = _FintoArchivio(cambi_esistenti=[
        _cambio(1787000000.0, "sistema",
                "problema:sonos.subscriptions_failed", None, "aperto"),
        _cambio(1787000050.0, "entita", "climate.altro_aperto", "off", "aperto"),
    ])
    osservatore = Osservatore(archivio, adesso=lambda: 1787572800.0)
    osservatore.ricostruisci_condizioni()
    soggetti = {o["soggetto"] for o in osservatore.osservate()}
    assert "climate.altro_aperto" not in soggetti
    assert "problema:sonos.subscriptions_failed" in soggetti


def test_la_ricostruzione_vede_condizioni_recenti_nonostante_il_volume_di_entita():
    """Il difetto D1 vero: sui 320.000 cambi/22gg misurati (spec §9②), quasi
    tutti di entita', un LIMIT che non filtrasse per fonte PRIMA di tagliare
    spingerebbe fuori le poche righe di sistema recenti -- che sono proprio
    quelle che decidono l'ultimo stato di una condizione. Qui il volume di
    entita' supera il `limite` esplicito passato da `ricostruisci_condizioni`
    (20.000): se il filtro `fonte="sistema"` non entrasse nella query PRIMA
    del LIMIT, la riga di sistema (la piu' recente) verrebbe tagliata via."""
    molte_entita = [_cambio(1_700_000_000.0 + i, "entita", "x", "a", "b")
                    for i in range(20_005)]
    archivio = _FintoArchivio(cambi_esistenti=molte_entita + [
        _cambio(1787572700.0, "sistema",
                "problema:sonos.subscriptions_failed", None, "aperto"),
    ])
    osservatore = Osservatore(archivio, adesso=lambda: 1787572800.0)
    osservatore.ricostruisci_condizioni()
    scritti = osservatore.guarda_sistema(
        problemi=[{"domain": "sonos", "issue_id": "subscriptions_failed",
                   "severity": "error"}],
        integrazioni=[])
    assert scritti == 0  # gia' seminata come aperta: non e' una novita'
