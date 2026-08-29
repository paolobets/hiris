"""Il sistema di riferimento della casa: unita', fuso, valuta, lingua.

Un valore senza il suo sistema di riferimento non e' un dato, e' un numero.
"72" non vuol dire niente finche' non si sa se sono gradi Celsius o
Fahrenheit; "domani alle 8" non vuol dire niente senza il fuso. Queste prove
tengono in piedi la fondamenta dell'ATOMICITA': il fatto arriva a chi lo
legge insieme a cio' che serve per interpretarlo.

La prova che conta di piu' e' l'ULTIMA, ed e' una prova di NON-azione: le
unita' della casa non devono MAI diventare l'unita' di un'entita' che non ce
l'ha. Home Assistant converte al momento in cui l'entita' entra, non dopo:
l'unita' vera e' quella dell'entita', e la casa dice solo come la casa
ragiona. Chi le confondesse scriverebbe "gradi Celsius" sotto un numero che
non lo e'.
"""
from unittest.mock import AsyncMock

import pytest

from hiris.app.casa.anagrafe import ricostruisci, sistema_di_riferimento
from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.casa.nucleo import componi
from hiris.app.casa.strumenti import DispatcherStrumenti
from hiris.app.memoria.archivio import MemoryStore
from hiris.app.proxy.ha_client import EVENTI_ANAGRAFE

# La risposta vera di `get_config` di Home Assistant, ridotta ai campi che
# HIRIS legge piu' due che deve buttare via (`components`, `latitude`) --
# senza quelli la prova non potrebbe dimostrare che li butta.
_CONFIG = {
    "location_name": "Casa", "time_zone": "Europe/Rome",
    "currency": "EUR", "language": "it", "country": "IT",
    "version": "2026.8.1",
    "unit_system": {
        "length": "km", "accumulated_precipitation": "mm", "area": "m2",
        "mass": "g", "pressure": "Pa", "temperature": "C",
        "volume": "L", "wind_speed": "m/s",
    },
    "components": ["light", "sensor", "automation"],
    "latitude": 45.4642, "longitude": 9.19,
    "state": "RUNNING",
}


@pytest.fixture
def archivio(tmp_path):
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    yield a
    a.chiudi()


# --- la distillazione: cosa entra, cosa resta fuori ------------------------

def test_tiene_i_campi_del_riferimento():
    rif = sistema_di_riferimento(_CONFIG)
    assert rif["fuso"] == "Europe/Rome"
    assert rif["valuta"] == "EUR"
    assert rif["lingua"] == "it"
    assert rif["paese"] == "IT"
    assert rif["nome"] == "Casa"
    assert rif["versione_ha"] == "2026.8.1"
    assert rif["unita"]["temperature"] == "C"
    assert rif["unita"]["length"] == "km"


def test_non_tiene_cio_che_e_gia_altrove_o_e_momentaneo():
    """`components` e' l'elenco delle integrazioni: l'anagrafe ce l'ha gia'
    nella tabella `integrazioni` (NESSUN DOPPIONE). La posizione non serve a
    nessuna domanda di oggi e non si tiene per ogni evenienza. `state` e'
    momentaneo -- scritto in un archivio che si rilegge di rado mentirebbe
    poche ore dopo, ed e' peggio di non saperlo."""
    rif = sistema_di_riferimento(_CONFIG)
    for campo in ("components", "integrazioni", "latitude", "longitude",
                  "posizione", "state", "stato"):
        assert campo not in rif, f"{campo} non deve entrare nel riferimento"


def test_una_config_illeggibile_non_inventa_un_riferimento():
    """Meglio nessun riferimento che uno inventato: chi legge deve poter
    distinguere «non lo so» da «e' metrico»."""
    assert sistema_di_riferimento(None) == {}
    assert sistema_di_riferimento("non un dizionario") == {}
    assert sistema_di_riferimento({}) == {}


def test_una_config_a_meta_porta_solo_cio_che_c_e():
    rif = sistema_di_riferimento({"time_zone": "Europe/Rome"})
    assert rif == {"fuso": "Europe/Rome"}


# --- l'archivio: dove vive ------------------------------------------------

def test_l_archivio_conserva_e_restituisce_il_riferimento(archivio):
    archivio.sostituisci({}, [], sistema_di_riferimento=sistema_di_riferimento(_CONFIG))
    assert archivio.sistema_di_riferimento()["fuso"] == "Europe/Rome"


def test_senza_riferimento_l_archivio_lo_dice_vuoto(archivio):
    archivio.sostituisci({}, [])
    assert archivio.sistema_di_riferimento() == {}


def test_una_lettura_fallita_non_cancella_il_riferimento_buono(archivio):
    """Stessa dottrina dell'anagrafe intera: una replica vecchia e' meglio di
    un vuoto spacciato per fresco. Se HA non ha risposto, il fuso di ieri e'
    ancora quello giusto."""
    archivio.sostituisci({}, [], sistema_di_riferimento=sistema_di_riferimento(_CONFIG))
    archivio.sostituisci({}, ["sistema_di_riferimento"], sistema_di_riferimento={})
    assert archivio.sistema_di_riferimento()["fuso"] == "Europe/Rome"


# --- la ricostruzione: chi lo va a prendere -------------------------------

@pytest.mark.asyncio
async def test_ricostruisci_legge_anche_il_riferimento(archivio):
    client = AsyncMock()
    client.leggi_registri = AsyncMock(return_value=({"entita": []}, []))
    client.get_config = AsyncMock(return_value=_CONFIG)
    esito = await ricostruisci(client, archivio)
    assert esito["non_disponibili"] == []
    assert archivio.sistema_di_riferimento()["valuta"] == "EUR"


@pytest.mark.asyncio
async def test_un_riferimento_non_letto_si_dichiara(archivio):
    """Non si ingoia: finisce nella stessa lista con cui l'anagrafe dichiara
    ogni altro silenzio -- niente meccanismo nuovo per dire la stessa cosa."""
    client = AsyncMock()
    client.leggi_registri = AsyncMock(return_value=({"entita": []}, []))
    client.get_config = AsyncMock(side_effect=OSError("HA muto"))
    esito = await ricostruisci(client, archivio)
    assert "sistema_di_riferimento" in esito["non_disponibili"]


def test_il_riferimento_si_rilegge_quando_la_casa_lo_cambia():
    """Cambiare fuso o unita' in Home Assistant emette `core_config_updated`.
    Senza questo, HIRIS ragionerebbe sul fuso di quando e' partito."""
    assert "core_config_updated" in EVENTI_ANAGRAFE


# --- il nucleo: chi lo legge ----------------------------------------------

def _nucleo(sistema):
    testo, _ = componi({"entita": []}, [], [], {}, sistema_di_riferimento=sistema)
    return testo


def test_il_nucleo_dichiara_il_riferimento():
    testo = _nucleo(sistema_di_riferimento(_CONFIG))
    # Il nome proprio della casa: entrava nell'archivio, usciva da /api/casa e
    # non arrivava al modello. E' il nome della cosa di cui parla tutto il resto.
    assert "Casa" in testo
    assert "Europe/Rome" in testo
    assert "EUR" in testo
    assert "2026.8.1" in testo


def test_il_nucleo_dichiara_l_istante_presente_nel_fuso_della_casa():
    """«Domani alle 8» non vuol dire niente senza il fuso -- e «fra un'ora»
    non vuol dire niente senza SAPERE CHE ORA E'.

    Difetto misurato sull'add-on vero il 21/08/2026: `prometti` ordina al
    modello «`quando` e' un istante ISO-8601: risolvilo tu da "fra un'ora"»,
    ma nessuno gli diceva l'ora. Alle 21:01 il modello ha creduto fossero le
    23:52 e ha fissato la promessa alle 23:55; se ne e' accorto e l'ha
    disdetta, ma quella sbagliata era gia' stata accettata. Il server l'ora
    ce l'ha esatta -- `crea(dati, adesso=time.time())` la usa per VALIDARE
    l'istante che il modello ha indovinato: si chiedeva al modello un fatto
    che HIRIS possiede, e poi lo si giudicava con la propria copia.

    L'istante sta accanto al fuso perche' e' lo stesso oggetto: un orario
    senza il suo fuso e' il «72» senza i gradi."""
    # 21/08/2026, 17:00:00 a Roma (l'istante del risveglio andato male).
    testo, _ = componi({"entita": []}, [], [], {},
                       sistema_di_riferimento=sistema_di_riferimento(_CONFIG),
                       adesso=1787324400.0)
    assert "17:00" in testo, "senza l'ora il modello se la inventa"
    assert "21/08/2026" in testo, "senza la data «alle 17» e' ambiguo fra oggi e domani"


def test_il_nucleo_VERO_porta_l_orologio_e_non_solo_quello_di_prova(archivio):
    """Chi lo riempie? La domanda che questo progetto ha gia' pagato tre volte.

    `componi` e' pura e riceve `adesso`: se `costruisci_nucleo` -- l'unico
    compositore di produzione, condiviso dalla chat sincrona, dal ponte e da
    GET /api/nucleo -- non gliela passa, il parametro esiste, i test passano,
    e il modello continua a indovinare l'ora esattamente come prima."""
    from hiris.app.api.handlers_casa import costruisci_nucleo

    archivio.sostituisci({}, [], sistema_di_riferimento=sistema_di_riferimento(_CONFIG))

    testo, _ = costruisci_nucleo({"archivio_casa": archivio})

    assert "Adesso sono le" in testo, (
        "il nucleo di produzione non porta l'ora: il parametro c'e' e nessuno "
        "lo riempie")
    assert "(fuso Europe/Rome)" in testo


def test_senza_l_istante_il_nucleo_non_ne_inventa_uno():
    """Stessa disciplina del fuso: tacere e' meglio che affermare un'ora a
    caso. `componi` resta PURA -- non legge l'orologio, lo riceve."""
    testo = _nucleo(sistema_di_riferimento(_CONFIG))
    assert "adesso sono le" not in testo.lower()


def test_senza_riferimento_il_nucleo_non_ne_inventa_uno():
    """Nessuna riga e' meglio di una riga che afferma un fuso a caso: il
    modello che non legge un fuso chiede, quello che ne legge uno sbagliato
    risponde sbagliato con sicurezza."""
    testo = _nucleo({})
    assert "fuso" not in testo.lower()


class _SpecchioFinto:
    """La forma vera di `entity_cache._to_minimal`: `id`, `state`, `unit`.
    L'unita' viva sta QUI e solo qui -- e' il punto del sistema di
    riferimento: la casa dice come ragiona, l'entita' dice cosa e'."""

    loaded = True

    def __init__(self, righe):
        self._righe = righe

    def all_states(self):
        return list(self._righe)


# --- LA PROVA CHE CONTA: il riferimento non e' un ripiego -----------------

@pytest.mark.asyncio
async def test_le_unita_della_casa_non_diventano_l_unita_di_un_entita(tmp_path):
    """Un'entita' senza unita' resta senza unita', anche a sistema noto.

    Home Assistant converte all'INGRESSO dell'entita', non alla lettura: una
    casa metrica puo' contenere benissimo un sensore in Fahrenheit, e un
    sensore senza unita' (un indice, un contatore, uno stato numerico) non e'
    "gradi" solo perche' la casa e' metrica. Scrivere l'unita' della casa
    sotto un valore che non ce l'ha e' peggio che non scrivere niente: chi
    legge non ha modo di accorgersene.

    Questa prova passa dal DISPATCHER, non dal nucleo, perche' e' li' che il
    difetto puo' nascere davvero: `guarda` e' l'unica porta da cui un'unita'
    arriva accanto a un valore (`_con_nome_dedotto` in domande.py), e
    l'archivio che gli sta sotto adesso contiene il sistema di riferimento
    completo -- cioe' la tentazione. Una prova sul nucleo sarebbe passata
    sempre, per il motivo sbagliato: il digesto stampa stati tradotti
    ("acceso", "bagnato"), mai un numero con la sua unita', e non avrebbe
    potuto fallire nemmeno con il difetto dentro.

    Mutazione che la fa fallire: in `domande._con_nome_dedotto`, ripiegare
    sull'unita' della casa quando `unita_vive` non ne ha una.
    """
    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    memoria = MemoryStore(str(tmp_path / "memoria.db"))
    try:
        archivio.sostituisci(
            {"aree": [{"area_id": "cucina", "name": "Cucina"}],
             "entita": [
                 # un indice: un numero senza unita', il caso da proteggere
                 {"entity_id": "sensor.indice", "name": "Indice aria",
                  "area_id": "cucina"},
                 # un termometro con la SUA unita': la prova che il canale
                 # funziona -- senza, la prova sopra sarebbe soddisfatta anche
                 # da un `guarda` che non porta mai nessuna unita'.
                 {"entity_id": "sensor.termo", "name": "Termometro",
                  "area_id": "cucina", "unit_of_measurement": "F"},
             ]},
            [], sistema_di_riferimento=sistema_di_riferimento(_CONFIG))
        assert archivio.sistema_di_riferimento()["unita"]["temperature"] == "C"

        cache = _SpecchioFinto([
            {"id": "sensor.indice", "state": "72", "unit": ""},
            {"id": "sensor.termo", "state": "72", "unit": "F"},
        ])
        d = DispatcherStrumenti(archivio, memoria, cache=cache)
        esito = await d.dispatch("guarda", {"tipo": "area", "riferimento": "cucina"})
        per_id = {e["id"]: e for e in esito["entita"]}

        assert "unita" not in per_id["sensor.indice"], (
            "l'unita' della casa e' finita su un'entita' che non ne ha una")
        assert per_id["sensor.termo"]["unita"] == "F", (
            "l'unita' propria dell'entita' deve arrivare, e vincere su quella "
            "della casa")
    finally:
        archivio.chiudi()
        memoria.close()
