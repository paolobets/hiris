"""Una promessa che agisce dichiara COSA toccherà (reperto B-6, 22/09/2026).

**Il reperto.** Una promessa che agisce porta una chiamata nella stessa forma di
`execute`, validata alla nascita per *esistenza* ed eseguita al risveglio con la
stessa verifica. Fra i due momenti possono passare **trenta giorni**, e nessuno
dei due chiede niente a nessuno: è l'unico percorso dove l'azione avviene con
certezza **senza nessuno davanti allo schermo**.

E su un bersaglio per AREA la verifica alla nascita si fermava prima:

    if verdict.da_risolvere:
        return None  # bersaglio per area: lo risolvera' la porta, al momento

Cioè: la promessa nasceva **senza che nessuno sapesse quante entità avrebbe
toccato**. «Spegni le luci del piano di sopra» poteva essere tre lampadine alla
nascita e undici al risveglio — una stanza nuova, un dispositivo aggiunto — e
il proprietario non aveva modo di saperlo né prima né dopo.

**Cosa cambia, e cosa NON cambia.** Non si toglie niente: una promessa nata da
una frase esplicita del proprietario resta una sua richiesta, e parte. Si
aggiunge ciò che mancava — il bersaglio si risolve **anche alla nascita**, il
numero si scrive, e al risveglio **si dichiara se è cambiato**.

Per contrasto, le promesse che si limitano a chiedere sono fatte molto bene:
nove strumenti di sola lettura, notifica in forma chiusa sul canale approvato
alla nascita. Il divario fra le due specie dimostrava che il controllo giusto si
sapeva scrivere: era già scritto, per l'altra metà.
"""
import pytest

from hiris.app.chat_thread import ChatThread
from hiris.app.keeper.store import AgendaStore


@pytest.fixture()
def archivio(tmp_path):
    store = AgendaStore(str(tmp_path / "agenda.db"))
    yield store
    store.close()


def _promessa(archivio, **extra):
    """Una promessa che AGISCE, nata adesso. Il `create` vero, non una finta:
    la colonna nuova deve arrivare in fondo davvero."""
    dati = {"specie": "fai", "frase": "spegni le luci di sopra",
            "quando_ts": 2_000_000_000.0,
            "chiamata": {"servizio": "light.turn_off",
                         "bersaglio": {"area": "piano di sopra"}}}
    dati.update(extra)
    esito = archivio.create(dati, thread=ChatThread("persona:paolo", "pannello"),
                            now=1_999_999_000.0)
    assert "errore" not in esito, esito
    return esito["promessa"]["id"]


def test_una_promessa_ricorda_QUANTE_entita_toccava_at_birth(archivio):
    """Il numero che mancava. Senza, «spegni le luci di sopra» non ha modo di
    accorgersi di essere diventata un'altra cosa.

    Mutazione ESEGUITA: non scrivere la colonna -- rossa."""
    ident = _promessa(archivio, entities_at_birth=3)

    letta = archivio.read(ident)

    assert letta["entities_at_birth"] == 3


def test_una_promessa_SENZA_bersaglio_per_area_non_porta_nessun_numero(archivio):
    """Un bersaglio di sole entita' non ha niente da risolvere: inventare un
    numero li' vorrebbe dire affermare una misura che nessuno ha preso.

    `None` e `0` sono due cose diverse -- «non si applica» e «nessuna entita'»
    -- e questa colonna non le confonde.

    Mutazione: scrivere `0` invece di `None` -- rossa."""
    ident = _promessa(archivio)

    assert archivio.read(ident)["entities_at_birth"] is None


def test_le_promesse_di_PRIMA_restano_leggibili(archivio):
    """La colonna si aggiunge, non si riscrive: le promesse nate prima del
    22/09/2026 non hanno quel numero e non devono diventare illeggibili --
    portano `None`, che e' esattamente cio' che sono.

    Mutazione ESEGUITA: `NOT NULL` sulla colonna nuova -- rossa (la migrazione
    fallisce su un archivio con righe dentro)."""
    ident = _promessa(archivio)

    letta = archivio.read(ident)

    assert "entities_at_birth" in letta
    assert letta["entities_at_birth"] is None


# --- e il risveglio lo DICHIARA --------------------------------------------

@pytest.mark.parametrize("at_birth,now,deve_dirlo", [
    (3, 3, False),
    (3, 11, True),
    (3, 1, True),
    (None, 7, False),
])
def test_al_risveglio_si_dichiara_se_il_numero_e_CAMBIATO(
        at_birth, now, deve_dirlo):
    """**La meta' che rende utile il numero.** Trenta giorni dopo, «le luci di
    sopra» possono essere un'altra cosa: se lo sono, chi legge l'esito deve
    poterlo sapere senza andare a contare.

    Si dichiara in TUTTI E DUE i versi: piu' entita' e' il caso che preoccupa,
    meno entita' e' il caso che inganna -- una promessa che tocca una lampadina
    invece di tre ha fatto un terzo del lavoro, e tacerlo la fa sembrare
    riuscita.

    Se alla nascita non c'era un numero (nessun bersaglio per area) non c'e'
    niente da confrontare, e inventare un avviso sarebbe rumore.

    Mutazione ESEGUITA: confrontare solo `adesso > at_birth` -- rossa sul
    terzo caso."""
    from hiris.app.keeper.sweeper import target_changed

    detto = target_changed(at_birth, now)

    assert (detto is not None) is deve_dirlo
    if deve_dirlo:
        assert str(at_birth) in detto and str(now) in detto


def test_e_l_avviso_dice_COSA_e_cambiato_non_solo_CHE_e_cambiato():
    """«Il bersaglio e' cambiato» manda a indovinare. I due numeri accanto
    dicono di quanto, e in che verso.

    Mutazione: un avviso generico -- rossa."""
    from hiris.app.keeper.sweeper import target_changed

    detto = target_changed(3, 11)

    assert "3" in detto and "11" in detto
    assert "nascita" in detto.lower() or "quando" in detto.lower()


# --- e il numero si CALCOLA davvero alla nascita ----------------------------
#
# Le prove sopra danno il numero a mano: dicono che l'archivio lo conserva e che
# il risveglio lo confronta. Nessuna diceva che qualcuno lo CALCOLA -- e una
# mutazione che scriveva `None` al posto del conteggio le lasciava tutte verdi.
# Misurato, non supposto.

class _PortaFinta:
    """L'attuatore, ridotto all'unica cosa che il conteggio gli chiede.

    Il vero risolve il bersaglio contro Home Assistant; qui basta che dica
    quante entita' ci sono dentro -- e che possa dire anche «non ci riesco»,
    che e' il caso che non deve impedire di promettere.
    """

    def __init__(self, entita=(), errore=None, esplode=False):
        self.entita = list(entita)
        self.errore = errore
        self.esplode = esplode
        self.chiesto = []

    async def _resolve(self, target):
        self.chiesto.append(target)
        if self.esplode:
            raise RuntimeError("Home Assistant non risponde")
        if self.errore:
            return {"errore": self.errore}
        return {"entita": self.entita}


def _dispatcher(porta):
    from hiris.app.home_space import tools as _t

    d = _t.ToolDispatcher.__new__(_t.ToolDispatcher)
    d._actuator = porta
    return d


@pytest.mark.asyncio
async def test_un_bersaglio_per_AREA_si_conta_alla_nascita():
    """**Il cuore del reperto B-6.** Prima la verifica alla nascita si fermava
    su `da_risolvere` e tornava `None`: la promessa nasceva senza che nessuno
    sapesse cosa avrebbe toccato.

    Mutazione ESEGUITA: scrivere `None` invece del conteggio -- rossa."""
    porta = _PortaFinta(entita=["light.a", "light.b", "light.c"])

    quante = await _dispatcher(porta)._count_target(
        {"servizio": "light.turn_off", "bersaglio": {"area": "piano di sopra"}})

    assert quante == 3
    assert porta.chiesto == [{"area": "piano di sopra"}]


@pytest.mark.asyncio
async def test_un_bersaglio_di_sole_ENTITA_non_si_conta():
    """Non c'e' niente da risolvere: il numero sarebbe una copia di cio' che il
    modello ha gia' scritto, e al risveglio non potrebbe essere cambiato.
    Contarlo vorrebbe dire chiedere a Home Assistant per niente.

    Mutazione ESEGUITA: contare comunque -- rossa."""
    porta = _PortaFinta(entita=["light.a"])

    quante = await _dispatcher(porta)._count_target(
        {"servizio": "light.turn_off", "bersaglio": {"entita": ["light.a"]}})

    assert quante is None
    assert porta.chiesto == [], "ha chiesto a Home Assistant per niente"


@pytest.mark.asyncio
async def test_se_il_conteggio_NON_RIESCE_la_promessa_nasce_lo_stesso():
    """**La contropartita, e non e' secondaria.** Questa misura serve a
    informare: rifiutare una promessa perche' non si e' potuto contare
    toglierebbe una funzione che il proprietario usa, per un dato che e' un di
    piu'.

    Mutazione ESEGUITA: lasciar propagare l'eccezione -- rossa."""
    for porta in (_PortaFinta(errore="area sconosciuta"), _PortaFinta(esplode=True)):
        quante = await _dispatcher(porta)._count_target(
            {"servizio": "light.turn_off", "bersaglio": {"area": "ignota"}})

        assert quante is None


@pytest.mark.asyncio
async def test_senza_attuatore_non_si_conta_e_non_si_cade():
    """Il dispatcher puo' nascere senza porta -- un turno di sola lettura -- e
    li' non c'e' niente da chiedere.

    Mutazione: indicizzare senza difendersi -- rossa."""
    quante = await _dispatcher(None)._count_target(
        {"servizio": "light.turn_off", "bersaglio": {"area": "x"}})

    assert quante is None


def test_e_la_NASCITA_lo_chiama_davvero():
    """**Il cancello del cablaggio.** Le prove qui sopra dicono che il
    conteggio funziona; questa dice che qualcuno lo USA. Sostituendo la
    chiamata con `None` dentro `_promise`, tutte le altre restano verdi --
    misurato -- e la promessa tornerebbe a nascere al buio senza che niente
    arrossisca.

    Si guarda la FORMA, come per il freno di ritmo: montare un turno intero
    per provarlo costerebbe piu' di quello che prova.

    Mutazione ESEGUITA: `data["entities_at_birth"] = None` -- rossa."""
    import inspect

    from hiris.app.home_space.tools import ToolDispatcher

    sorgente = inspect.getsource(ToolDispatcher._promise)

    assert "_count_target" in sorgente, (
        "la promessa non conta piu' il bersaglio alla nascita: nasce al buio, "
        "ed e' il reperto B-6 che torna")
    assert 'data["entities_at_birth"]' in sorgente, (
        "il numero si calcola e non si scrive: non arrivera' mai all'archivio")
