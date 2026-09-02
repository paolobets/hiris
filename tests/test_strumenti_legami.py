"""«Chi tocca questa cosa»: i legami arrivano fino al modello.

La porta verso Home Assistant (`HAClient.related`) esisteva gia' ed e' provata
altrove (`tests/test_ha_client_legami_problemi.py`). Qui si prova il tratto
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

import pytest

from hiris.app.casa.archivio import HomeSpaceStore
from hiris.app.casa.domande import LINK_NAME, related, view
from hiris.app.casa.strumenti import ToolDispatcher
from hiris.app.memoria.archivio import MemoryStore
from hiris.app.proxy.ha_client import HAClient
from tests.test_cervello_comprimari import _ClienteLegami

# La finta di `HAClient.related` usata qui e' `_ClienteLegami`, importata da
# `test_cervello_comprimari.py` -- l'UNICA del progetto (vedi il suo
# docstring). Prima di questa correzione questo file ne aveva una propria
# (`_FintoHA`), che accettava QUALUNQUE `tipo` e rispondeva sempre la stessa
# mappa: la nona finta dello stesso contratto, la stessa infedelta' che ha
# reso invisibile il Critical dei comprimari. Qui non serve estenderla: ogni
# prova sotto chiede sempre lo stesso `riferimento` per chiamata, quindi
# `_ClienteLegami(default=...)` -- che risponde a QUALUNQUE identificatore,
# ma valida `tipo` contro `HAClient.RELATED_ITEM_TYPES` prima di rispondere -- basta
# senza bisogno di popolare `mappa` per identificatore.


class _FintaPorta:
    """La porta vera (`azione/porta.py`) tiene il client in `_ha`: e' da li'
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
    a = HomeSpaceStore(str(tmp_path / "casa.db"))
    yield a
    a.close()


def _dispatcher(casa, memoria, ha=None, actuator=None):
    return ToolDispatcher(casa, memoria, ha=ha, actuator=actuator)


# --- il vocabolario -------------------------------------------------------

def test_il_vocabolario_copre_ESATTAMENTE_i_tipi_di_home_assistant():
    """La tabella di `domande.py` e i quattordici tipi del client sono lo
    stesso elenco visto da due parti. Se Home Assistant ne aggiunge uno e il
    client lo accetta mentre la tabella no, il modello riceve un tipo che non
    sa nominare e non puo' richiedere: questa prova cade prima."""
    assert set(LINK_NAME) == set(HAClient.RELATED_ITEM_TYPES)


@pytest.mark.asyncio
async def test_i_legami_escono_nel_vocabolario_della_casa_e_ordinati(casa, memoria):
    """Il modello nomina «entita» e «automazione» ovunque -- in `search`, in
    `view`, nelle ancore dei ricordi. Se qui leggesse `entity` e
    `automation` dovrebbe imparare due vocabolari per la stessa casa, e il
    `riferimento` che passa a `view` verrebbe da una risposta scritta in
    un'altra lingua."""
    ha = _ClienteLegami(default={"script": ["script.sera"], "automation": ["automation.a"],
                                  "entity": ["light.corridoio"]})
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"tipo": "entita", "riferimento": "light.corridoio"})
    assert esito["legami"] == {"automazione": ["automation.a"],
                               "entita": ["light.corridoio"],
                               "script": ["script.sera"]}
    assert list(esito["legami"]) == ["automazione", "entita", "script"], (
        "le chiavi si ordinano: Home Assistant le manda da insiemi, e due "
        "letture uguali produrrebbero due risposte diverse")
    assert esito["tipo"] == "entita" and esito["riferimento"] == "light.corridoio"


@pytest.mark.asyncio
async def test_il_tipo_si_traduce_verso_home_assistant(casa, memoria):
    """Il verso opposto della stessa tabella. Senza, il comando partirebbe con
    `item_type: "entita"` e Home Assistant lo rifiuterebbe -- un guasto
    prodotto da noi che arriva al modello come un errore suo."""
    ha = _ClienteLegami()
    await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"tipo": "dispositivo", "riferimento": "abc123"})
    assert ha.chiesti == [("device", "abc123")]


@pytest.mark.asyncio
async def test_un_tipo_che_home_assistant_non_conosce_si_ferma_prima_della_rete(
        casa, memoria):
    ha = _ClienteLegami()
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"tipo": "stanza", "riferimento": "cucina"})
    assert "errore" in esito
    assert "legami" not in esito
    assert ha.chiesti == [], "non si disturba Home Assistant per un tipo che rifiuterebbe"


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
    ha = _ClienteLegami(default={"errore": "Home Assistant non ha risposto"})
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"tipo": "entita", "riferimento": "light.corridoio"})
    assert "errore" in esito
    assert "legami" not in esito, "un guasto con la forma di un elenco vuoto e' il difetto"
    assert "Home Assistant non ha risposto" in esito["errore"], (
        "il motivo vero non si perde: e' cio' che distingue «riprova» da «non insistere»")


@pytest.mark.asyncio
async def test_nessun_legame_resta_dicibile(casa, memoria):
    """L'altra meta': una cosa che davvero non tocca nessuno deve poterlo
    dire. Se il guasto e l'assenza avessero la stessa forma, il rimedio
    sarebbe peggiore del male."""
    ha = _ClienteLegami()
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"tipo": "entita", "riferimento": "light.mai_usata"})
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
        "related", {"tipo": "entita", "riferimento": "light.corridoio"})
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
    porta_con_canale = _FintaPorta(_ClienteLegami(default={"automation": ["automation.a"]}))
    esito = await _dispatcher(casa, memoria, actuator=porta_con_canale).dispatch(
        "related", {"tipo": "entita", "riferimento": "light.corridoio"})
    assert "legami" not in esito, (
        "lo strumento ha trovato il canale dentro la porta: il ripiego "
        "sull'attributo privato e' tornato")
    assert "errore" in esito
    assert "attribute" not in esito["errore"], "il messaggio dev'essere leggibile"


@pytest.mark.asyncio
async def test_col_canale_passato_lo_strumento_risponde(casa, memoria):
    """Il verso positivo, e serve quanto l'altro: senza, un dispatcher che non
    risponde MAI farebbe passare la prova qui sopra per il motivo sbagliato."""
    ha = _ClienteLegami(default={"automation": ["automation.a"]})
    esito = await _dispatcher(casa, memoria, ha=ha).dispatch(
        "related", {"tipo": "entita", "riferimento": "light.corridoio"})
    assert esito["legami"] == {"automazione": ["automation.a"]}


# --- la decisione: i legami non si archiviano ------------------------------

@pytest.mark.asyncio
async def test_i_legami_non_finiscono_in_nessun_archivio(tmp_path, memoria):
    """La decisione di questa fetta, provata invece che soltanto scritta.

    I legami sono momentanei quanto lo stato -- un'automazione salvata un
    minuto fa li cambia -- ed e' la stessa ragione per cui `state` sta fuori
    dal sistema di riferimento (`casa/anagrafe.sistema_di_riferimento`): «in
    un archivio che si rilegge di rado mentirebbe poche ore dopo, ed e' peggio
    che non saperlo».

    Chi un giorno li salvasse «per non richiederli ogni volta» fa cadere
    questa prova. Si guarda il CONTENUTO del database, non il file: SQLite
    scrive in un giornale a fianco (`casa.db-wal`) e il file principale puo'
    restare identico per un pezzo -- una scrittura vera sarebbe passata
    inosservata. E si guarda anche la cartella, cosi' nemmeno un archivio
    NUOVO nato di fianco puo' sfuggire."""
    archivio = HomeSpaceStore(str(tmp_path / "casa.db"))
    try:
        def _impronta():
            dump = "\n".join(archivio._conn.iterdump())
            attorno = sorted((f.name, f.stat().st_size) for f in tmp_path.iterdir())
            return hashlib.sha256(f"{dump}{attorno}".encode()).hexdigest()

        prima = _impronta()
        ha = _ClienteLegami(default={"automation": ["automation.a"], "scene": ["scene.sera"]})
        esito = await _dispatcher(archivio, memoria, ha=ha).dispatch(
            "related", {"tipo": "entita", "riferimento": "light.corridoio"})
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
    dettaglio = view(_CASA_MINIMA, [], [], {}, "scena", "scene.serata")
    assert dettaglio["esiste"] is False
    assert dettaglio["non_so_guardare"] is True


def test_un_tipo_che_guarda_SA_aprire_non_si_scusa():
    """L'altra meta', e la ragione per cui la prima non basta: se
    `non_so_guardare` comparisse sempre, un'area davvero inesistente
    diventerebbe «non l'ho saputa guardare» -- e il modello smetterebbe di
    poter dire che una cosa non c'e'."""
    dettaglio = view(_CASA_MINIMA, [], [], {}, "area", "cucina_che_non_esiste")
    assert dettaglio["esiste"] is False
    assert "non_so_guardare" not in dettaglio
