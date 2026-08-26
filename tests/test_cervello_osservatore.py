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
    non si ferma se l'archivio non risponde)."""

    def __init__(self, cambi_esistenti=None, *, cambi_solleva=False):
        self.annotati = []
        self._cambi = list(cambi_esistenti or [])
        self._cambi_solleva = cambi_solleva

    def annota(self, **kw):
        self.annotati.append(kw)

    def cambi(self, *, da_ts, a_ts, soggetto=None, limite=200_000):
        if self._cambi_solleva:
            raise RuntimeError("archivio irraggiungibile")
        righe = [c for c in self._cambi if da_ts <= c["quando_ts"] < a_ts]
        if soggetto is not None:
            righe = [c for c in righe if c["soggetto"] == soggetto]
        return sorted(righe, key=lambda c: c["quando_ts"])


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
                                  "da": "off", "a": "heat"}]


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


def test_un_evento_senza_stato_nuovo_non_solleva(coppia):
    """Un'entita' rimossa manda `new_state: None`. L'osservatore gira per
    sempre: un'eccezione qui lo fermerebbe su un evento solo."""
    archivio, osservatore = coppia
    assert osservatore.guarda_cambio(_evento("climate.camera_t", "heat", None)) is False


def test_un_evento_malformato_non_solleva(coppia):
    archivio, osservatore = coppia
    for ev in [{}, {"entity_id": None}, {"entity_id": "climate.x"}, None]:
        assert osservatore.guarda_cambio(ev) is False


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
