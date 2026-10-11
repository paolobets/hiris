"""«Chi tocca questa cosa»: i legami arrivano fino al modello.

La porta verso Home Assistant (`HAClient.related`) esisteva gia' ed e' provata
altrove (`tests/test_ha_client_related_problems.py`). Qui si prova il tratto
che mancava: dal client al modello, cioe' il vocabolario, la forma della
risposta e -- soprattutto -- le due distinzioni che questo progetto paga da
sempre quando le perde.

1. **Un guasto non e' un «niente».** `legami: {}` afferma «questa cosa non la
   tocca nessuno». Se Home Assistant non ha risposto, quell'affermazione e'
   falsa e nessuno ha il diritto di farla.
2. **«Non lo so aprire» non e' «non esiste».** `related` restituisce
   identificatori veri di scene, gruppi e persone che `view` non sa aprire:
   senza dirlo, il modello legge `esiste: false` e riferisce all'utente che
   quella scena non c'e'.

E la decisione della fetta, provata invece che soltanto scritta: **i legami
non si archiviano**. Sono momentanei quanto lo stato, e una tabella riletta
di rado mentirebbe poche ore dopo.
"""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import CasaFinta

from hiris.app.home_space.ha_vocabulary import LINK_NAME
from hiris.app.home_space.house import House
from hiris.app.home_space.queries import related, view
from hiris.app.home_space.reader import HomeSpace
from hiris.app.home_space.tools import ToolDispatcher
from hiris.app.home_space.topology import Mirror
from hiris.app.memory.store import MemoryStore
from hiris.app.proxy.ha_client import HAClient
from tests._casa_sintetica import synthetic_inputs

#: Il comando che `HAClient.related` manda.
RELATED = "search/related"


def _house(links=None, **faults) -> CasaFinta:
    """Home Assistant sotto il client VERO (`scripts/casa_finta.py`, Tappa 2,
    Task 12): `search/related` risponde `links` -- il `result` grezzo, chiavi
    inglesi, come lo manda Home Assistant -- a qualunque domanda. Il tipo lo
    valida il client vero (`HAClient.RELATED_ITEM_TYPES`), e la busta del
    guasto e' la sua.

    Fino al Task 12 qui c'era `_ClienteLegami` (`tests/_ha_fakes.py`), che
    imitava `related` a mano: validava il tipo con una copia del controllo
    del client e rispondeva la mappa gia' fatta. `faults` sono `silence=` e
    `refuse=` della casa finta."""
    answers = {RELATED: lambda extra: dict(links or {})}
    return CasaFinta(synthetic_inputs(), answers=answers, **faults)


def _asked(house: CasaFinta) -> list[tuple[str, str]]:
    """Cio' che e' partito verso Home Assistant: `(item_type, item_id)`."""
    return [(extra["item_type"], extra["item_id"])
            for command, extra in house.calls if command == RELATED]


class _FintaPorta:
    """La porta vera (`action/actuator.py`) tiene il client in `_ha`: e' da li'
    che il dispatcher lo prende finche' il suo costruttore non glielo passa."""

    def __init__(self, ha):
        self._ha = ha


@pytest.fixture
def memoria(tmp_path):
    m = MemoryStore(str(tmp_path / "memoria.db"))
    yield m
    m.close()


@pytest.fixture
def casa(tmp_path):
    a = HomeSpace(str(tmp_path / "casa.db"))
    yield a
    a.close()


def _dispatcher(casa, memoria, ha=None, actuator=None):
    return ToolDispatcher(casa, memoria, ha=ha, actuator=actuator)


# --- il vocabolario -------------------------------------------------------

#: I valori di `ItemType` (`homeassistant/components/search/__init__.py`, tag
#: `2026.9.1`), RISCRITTI qui e non importati: e' la prova che riporta la
#: tabella alla fonte, e una mutazione della tabella non deve poter muovere
#: anche il proprio metro.
_ITEM_TYPES_AT_SOURCE = {
    "area", "automation", "automation_blueprint", "config_entry", "device",
    "entity", "floor", "group", "integration", "label", "person", "scene",
    "script", "script_blueprint"}


def test_il_vocabolario_copre_ESATTAMENTE_i_tipi_di_home_assistant():
    """La tabella dei legami (`ha_vocabulary.LINK_NAME`) porta i quattordici
    tipi di Home Assistant, e il client accetta esattamente quelli perche' li
    chiede a lei (B-48, 04/10/2026: prima erano due elenchi, e questa prova li
    confrontava fra loro).

    Mutazione ESEGUITA: tolta la voce `"label"` da `LINK_NAME` -- rossa sul
    confronto con la fonte (e il client smette di accettarla con lei)."""
    assert set(LINK_NAME) == _ITEM_TYPES_AT_SOURCE
    assert HAClient.RELATED_ITEM_TYPES == tuple(LINK_NAME)


@pytest.mark.asyncio
async def test_i_legami_escono_nel_vocabolario_della_casa_e_ordinati(casa, memoria):
    """Il modello nomina «entita» e «automazione» ovunque -- in `search`, in
    `view`, nelle ancore dei ricordi. Se qui leggesse `entity` e
    `automation` dovrebbe imparare due vocabolari per la stessa casa, e il
    `riferimento` che passa a `view` verrebbe da una risposta scritta in
    un'altra lingua."""
    ha = _house({"script": ["script.sera"], "automation": ["automation.a"],
                                  "entity": ["light.corridoio"]})
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"genere": "entita", "riferimento": "light.corridoio"})
    assert esito["legami"] == {"automazione": ["automation.a"],
                               "entita": ["light.corridoio"],
                               "script": ["script.sera"]}
    assert list(esito["legami"]) == ["automazione", "entita", "script"], (
        "le chiavi si ordinano: Home Assistant le manda da insiemi, e due "
        "letture uguali produrrebbero due risposte diverse")
    assert esito["genere"] == "entita" and esito["riferimento"] == "light.corridoio"


@pytest.mark.asyncio
async def test_il_tipo_si_traduce_verso_home_assistant(casa, memoria):
    """Il verso opposto della stessa tabella. Senza, il comando partirebbe con
    `item_type: "entita"` e Home Assistant lo rifiuterebbe -- un guasto
    prodotto da noi che arriva al modello come un errore suo."""
    ha = _house()
    await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"genere": "dispositivo", "riferimento": "abc123"})
    assert _asked(ha) == [("device", "abc123")]


@pytest.mark.asyncio
async def test_un_tipo_che_home_assistant_non_conosce_si_ferma_prima_della_rete(
        casa, memoria):
    ha = _house()
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"genere": "stanza", "riferimento": "cucina"})
    assert "errore" in esito
    assert "legami" not in esito
    assert ha.calls == [], "non si disturba Home Assistant per un tipo che rifiuterebbe"


def test_un_tipo_nuovo_di_home_assistant_non_si_perde_per_strada():
    """Una chiave che la tabella non conosce esce col nome di Home Assistant.
    Un nome non tradotto e' un fastidio; una riga buttata sarebbe un legame
    scomparso in silenzio, che e' il difetto contro cui esiste questa fetta."""
    esito = related({"quadro_di_comando": ["x.y"]}, "entita", "light.corridoio")
    assert esito["legami"] == {"quadro_di_comando": ["x.y"]}


# --- un guasto non e' un «niente» -----------------------------------------

@pytest.mark.asyncio
async def test_un_guasto_non_diventa_un_elenco_vuoto(casa, memoria):
    """La prova centrale. `legami: {}` significa «non la tocca nessuno»: e'
    un'affermazione, e su un canale caduto e' falsa."""
    ha = _house(silence={RELATED})
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"genere": "entita", "riferimento": "light.corridoio"})
    assert "errore" in esito
    assert "legami" not in esito, "un guasto con la forma di un elenco vuoto e' il difetto"
    assert "Home Assistant non ha risposto" in esito["errore"], (
        "il motivo vero non si perde: e' cio' che distingue «riprova» da «non insistere»")


@pytest.mark.asyncio
async def test_nessun_legame_resta_dicibile(casa, memoria):
    """L'altra meta': una cosa che davvero non tocca nessuno deve poterlo
    dire. Se il guasto e l'assenza avessero la stessa forma, il rimedio
    sarebbe peggiore del male."""
    ha = _house()
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"genere": "entita", "riferimento": "light.mai_usata"})
    assert esito["legami"] == {}
    assert "errore" not in esito


@pytest.mark.asyncio
async def test_senza_canale_verso_home_assistant_lo_strumento_lo_DICHIARA(casa, memoria):
    """Terza forma dello stesso difetto: senza client, rispondere `{}` direbbe
    «non la tocca nessuno» a chi non ha nemmeno chiesto.

    E il messaggio dev'essere LEGGIBILE. Senza il cancello di
    `_missing_resource` un `errore` arriva lo stesso -- dalla rete di
    sicurezza di `dispatch()` -- ma dice «'NoneType' object has no attribute
    'legami'»: un errore Python travestito da risposta, che il modello non
    sa spiegare all'utente e che lo fa riprovare all'infinito. E' l'unica
    ragione per cui quel cancello esiste (vedi il suo commento), quindi e'
    quello che questa prova sorveglia."""
    esito = await _dispatcher(casa, memoria).dispatch(
        "related", {"genere": "entita", "riferimento": "light.corridoio"})
    assert "errore" in esito
    assert "legami" not in esito
    assert "Home Assistant" in esito["errore"]
    assert "NoneType" not in esito["errore"], esito["errore"]
    assert "attribute" not in esito["errore"], esito["errore"]


@pytest.mark.asyncio
async def test_senza_canale_lo_strumento_lo_DICHIARA_e_non_lo_cerca_altrove(casa, memoria):
    """Il canale arriva da `ha=`, e da nient'altro.

    Per un momento c'e' stato un ripiego che leggeva `porta._ha` -- l'attributo
    PRIVATO di un altro oggetto -- perche' la fetta dei legami non poteva
    toccare l'unico costruttore del dispatcher. E' durato il tempo di
    aggiungere una riga la' (`ha=app.get("ha_client")`) ed e' uscito: un modulo
    che conosce le parti private di un altro e' un accoppiamento che nessun
    test dichiara, e si scopre il giorno in cui l'altro cambia nome a un campo.

    Senza canale lo strumento non tace e non fruga: dichiara. Uno strumento
    muto perche' non ha la connessione e uno muto perche' non ci sono legami
    direbbero la stessa cosa, e sono opposti.
    """
    porta_con_canale = _FintaPorta(_house({"automation": ["automation.a"]}))
    esito = await _dispatcher(casa, memoria, actuator=porta_con_canale).dispatch(
        "related", {"genere": "entita", "riferimento": "light.corridoio"})
    assert "legami" not in esito, (
        "lo strumento ha trovato il canale dentro la porta: il ripiego "
        "sull'attributo privato e' tornato")
    assert "errore" in esito
    assert "attribute" not in esito["errore"], "il messaggio dev'essere leggibile"


@pytest.mark.asyncio
async def test_col_canale_passato_lo_strumento_risponde(casa, memoria):
    """Il verso positivo, e serve quanto l'altro: senza, un dispatcher che non
    risponde MAI farebbe passare la prova qui sopra per il motivo sbagliato."""
    ha = _house({"automation": ["automation.a"]})
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"genere": "entita", "riferimento": "light.corridoio"})
    assert esito["legami"] == {"automazione": ["automation.a"]}


# --- la decisione: i legami non si archiviano ------------------------------

@pytest.mark.asyncio
async def test_i_legami_non_finiscono_in_nessun_archivio(tmp_path, memoria):
    """La decisione di questa fetta, provata invece che soltanto scritta.

    I legami sono momentanei quanto lo stato -- un'automazione salvata un
    minuto fa li cambia -- ed e' la stessa ragione per cui `state` sta fuori
    dal sistema di riferimento (`home_space/topology.sistema_di_riferimento`): «in
    un archivio che si rilegge di rado mentirebbe poche ore dopo, ed e' peggio
    che non saperlo».

    Chi un giorno li salvasse «per non richiederli ogni volta» fa cadere
    questa prova. Si guarda il CONTENUTO del database, non il file: SQLite
    scrive in un giornale a fianco (`casa.db-wal`) e il file principale puo'
    restare identico per un pezzo -- una scrittura vera sarebbe passata
    inosservata. E si guarda anche la cartella, cosi' nemmeno un archivio
    NUOVO nato di fianco puo' sfuggire."""
    archivio = HomeSpace(str(tmp_path))
    try:
        def _impronta():
            tenuto = (archivio.read(), archivio.behavior(), archivio.dashboards(),
                      archivio.reference_frame(), archivio.unread_bodies())
            attorno = sorted((f.name, f.stat().st_size) for f in tmp_path.iterdir())
            return hashlib.sha256(f"{tenuto}{attorno}".encode()).hexdigest()

        prima = _impronta()
        ha = _house({"automation": ["automation.a"], "scene": ["scene.sera"]})
        esito = await _dispatcher(archivio, memoria, ha=ha).dispatch(
            "related", {"genere": "entita", "riferimento": "light.corridoio"})
        assert esito["legami"]
        assert _impronta() == prima, "i legami sono momentanei: non si archiviano"
    finally:
        archivio.close()


# --- «non lo so aprire» non e' «non esiste» -------------------------------

_CASA_MINIMA = {"piani": [], "aree": [], "dispositivi": [], "entita": []}


def test_guarda_dichiara_i_tipi_che_non_sa_aprire():
    """Il buco che questa fetta APRIREBBE se non lo chiudesse: `related`
    restituisce scene, gruppi e persone -- cose vere, che Home Assistant ha
    appena mostrato -- e `view` non le sa aprire. Rispondere `esiste: false`
    e basta significa far dire al modello «quella scena non esiste»."""
    dettaglio = view(House(_CASA_MINIMA, Mirror()), [], [], "scena", "scene.serata")
    assert dettaglio["esiste"] is False
    assert dettaglio["non_so_guardare"] is True


def test_un_tipo_che_guarda_SA_aprire_non_si_scusa():
    """L'altra meta', e la ragione per cui la prima non basta: se
    `non_so_guardare` comparisse sempre, un'area davvero inesistente
    diventerebbe «non l'ho saputa guardare» -- e il modello smetterebbe di
    poter dire che una cosa non c'e'."""
    dettaglio = view(House(_CASA_MINIMA, Mirror()), [], [], "area", "cucina_che_non_esiste")
    assert dettaglio["esiste"] is False
    assert "non_so_guardare" not in dettaglio
