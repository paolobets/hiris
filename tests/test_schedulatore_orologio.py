"""Il battito: mai in ritardo, mai due volte, e il silenzio e' un esito riuscito."""
import os

import pytest

from hiris.app.azione.porta import ActionActuator
from hiris.app.schedulatore.archivio import AgendaStore
from hiris.app.schedulatore.promise import TOLLERANZA_S
from hiris.app.schedulatore.sweeper import Sweeper
from tests._contratti import assert_stessa_firma

ADESSO = 1_755_600_000.0
pytestmark = pytest.mark.asyncio


class PortaFinta:
    """Una porta che sa RIUSCIRE e sa FALLIRE: se sapesse solo riuscire, i test
    sul fallimento non potrebbero diventare rossi."""

    def __init__(self, occurrence=None):
        self.chiamate = []
        self._occurrence = occurrence or {"eseguito": True, "cambiato": ["light.studio"],
                                "esecuzione_id": "e1"}

    async def __call__(self, chiamata, *, actor):
        self.chiamate.append((chiamata, actor))
        return self._occurrence


def test_la_porta_finta_combacia_con_la_firma_vera():
    """Se `ActionActuator.execute` cambia firma, questo test cade invece
    di lasciare che il finto imiti un contratto che non esiste piu'."""
    assert_stessa_firma(ActionActuator.execute, PortaFinta.__call__, nome="execute")


class TurnoFinto:
    def __init__(self, answer=None):
        self.viste = []
        self._answer = answer or {"avvisare": True, "testo": "e' salita di 2 gradi"}

    async def __call__(self, promessa):
        self.viste.append(promessa)
        return self._answer


class ArchivioConCorsaSuPrendi:
    """Involucro attorno all'archivio vero, che sa produrre ESATTAMENTE la corsa che
    "mai due volte" deve chiudere: `scadute()` si comporta come sempre (la
    promessa e' ancora `in_attesa` quando l'orologio la legge), ma `prendi()`
    risponde sempre `False` -- come se un altro giro fosse arrivato prima nella
    finestra fra la lettura e la presa. Se l'orologio ignorasse il risultato di
    `prendi()` (invece di fermarsi con un `continue`), questo involucro e' cio'
    che lo fa vedere: la porta verrebbe chiamata comunque su una promessa che
    non e' mai stata presa."""

    def __init__(self, archivio):
        self._archivio = archivio

    def scadute(self, now):
        return self._archivio.scadute(now)

    def prendi(self, promise_id, *, now):
        return False  # qualcuno e' arrivato prima, sempre

    def concludi(self, *args, **kwargs):
        return self._archivio.concludi(*args, **kwargs)


@pytest.fixture()
def archivio(tmp_path):
    a = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    yield a
    a.close()


def _crea_fai(archivio, *, quando, recapito=None):
    return archivio.create({
        "specie": "fai", "frase": "alle 17 accendi lo studio", "quando_ts": quando,
        "chiamata": {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.studio"]}},
        "recapito": recapito,
    }, now=ADESSO)["promessa"]["id"]


def _crea_chiedi(archivio, *, quando, recapito=None):
    return archivio.create({
        "specie": "chiedi", "frase": "fra un'ora verifica la temperatura",
        "quando_ts": quando, "domanda": "e' aumentata?", "recapito": recapito,
    }, now=ADESSO)["promessa"]["id"]


async def test_un_fai_scaduto_passa_dalla_porta_con_origine_schedulatore(archivio):
    ident = _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta()
    await Sweeper(archivio, execute=porta, interpreta=TurnoFinto()).batti(ADESSO + 11)

    assert len(porta.chiamate) == 1
    assert porta.chiamate[0][1] == "schedulatore"
    p = archivio.read(ident)
    assert p["stato"] == "mantenuta"
    assert p["esecuzione_id"] == "e1"


async def test_oltre_la_tolleranza_non_si_esegue_mai_e_il_motivo_misura(archivio):
    ident = _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta()
    await Sweeper(archivio, execute=porta, interpreta=TurnoFinto()).batti(
        ADESSO + 10 + TOLLERANZA_S + 60)

    assert porta.chiamate == []          # la luce NON si accende in ritardo
    p = archivio.read(ident)
    assert p["stato"] == "saltata"
    assert "non eseguita" in p["motivo"]


async def test_dentro_la_tolleranza_si_esegue(archivio):
    """Il confine dall'altro lato: senza questo, «tolleranza» potrebbe essere zero.

    Include anche il confine esatto (ritardo == TOLLERANZA_S): la spec dice
    "oltre" quella soglia, quindi a ritardo esattamente pari alla tolleranza la
    promessa si mantiene ancora -- una mutazione `>` -> `>=` non sarebbe colta
    senza questo caso.
    """
    _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta()
    await Sweeper(archivio, execute=porta, interpreta=TurnoFinto()).batti(
        ADESSO + 10 + TOLLERANZA_S - 1)
    assert len(porta.chiamate) == 1

    _crea_fai(archivio, quando=ADESSO + 20)
    await Sweeper(archivio, execute=porta, interpreta=TurnoFinto()).batti(
        ADESSO + 20 + TOLLERANZA_S)
    assert len(porta.chiamate) == 2


async def test_due_battiti_ravvicinati_non_la_mantengono_due_volte(archivio):
    _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta()
    orologio = Sweeper(archivio, execute=porta, interpreta=TurnoFinto())
    await orologio.batti(ADESSO + 11)
    await orologio.batti(ADESSO + 12)
    assert len(porta.chiamate) == 1


async def test_una_presa_persa_non_esegue_e_non_conclude(archivio):
    """Il cuore di "mai due volte": non basta che due batti() sequenziali non la
    rieseguano (`scadute()` non la ripropone perche' e' gia' conclusa) -- serve
    che l'orologio si fermi anche quando la promessa E' ancora `in_attesa` alla
    lettura ma qualcun altro la prende un istante dopo. L'involucro sopra simula
    esattamente questa finestra: se l'orologio ignorasse il risultato di
    `prendi()`, la porta verrebbe chiamata comunque."""
    ident = _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta()
    involucro = ArchivioConCorsaSuPrendi(archivio)
    await Sweeper(involucro, execute=porta, interpreta=TurnoFinto()).batti(ADESSO + 11)

    assert porta.chiamate == []
    p = archivio.read(ident)
    assert p["stato"] == "in_attesa"      # non presa, non eseguita, non conclusa


async def test_una_porta_che_fallisce_lascia_la_promessa_fallita_col_motivo(archivio):
    ident = _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta({"eseguito": False, "errore": "quel servizio non esiste"})
    await Sweeper(archivio, execute=porta, interpreta=TurnoFinto()).batti(ADESSO + 11)

    p = archivio.read(ident)
    assert p["stato"] == "fallita"
    assert "non esiste" in p["motivo"]


async def test_una_porta_che_solleva_non_ferma_il_battito(archivio):
    """Un guasto su una promessa non deve impedire alle altre di essere mantenute."""
    rotta = _crea_fai(archivio, quando=ADESSO + 10)
    sana = _crea_fai(archivio, quando=ADESSO + 11)

    chiamate = []

    async def porta(chiamata, *, actor):
        chiamate.append(chiamata)
        if len(chiamate) == 1:
            raise RuntimeError("la rete e' caduta")
        return {"eseguito": True, "cambiato": [], "esecuzione_id": "e2"}

    await Sweeper(archivio, execute=porta, interpreta=TurnoFinto()).batti(ADESSO + 12)

    assert archivio.read(rotta)["stato"] == "fallita"
    assert archivio.read(sana)["stato"] == "mantenuta"


async def test_un_chiedi_con_recapito_notifica_e_registra_cio_che_ha_detto(archivio):
    ident = _crea_chiedi(archivio, quando=ADESSO + 10, recapito="notify.mobile_app_x")
    porta = PortaFinta()
    turno = TurnoFinto({"avvisare": True, "testo": "e' salita di 2 gradi"})
    await Sweeper(archivio, execute=porta, interpreta=turno).batti(ADESSO + 11)

    assert len(porta.chiamate) == 1
    chiamata, actor = porta.chiamate[0]
    assert chiamata["servizio"] == "notify.mobile_app_x"
    assert "2 gradi" in chiamata["dati"]["message"]
    assert actor == "schedulatore"

    p = archivio.read(ident)
    assert (p["stato"], p["avvisare"], p["testo"]) == ("mantenuta", True, "e' salita di 2 gradi")


async def test_la_notifica_fallita_lascia_il_testo_e_dichiara_la_consegna_mancata(archivio):
    """Un recapito VALIDO il cui invio fallisce: non e' il caso "nessun canale"
    (quello e' gia' provato altrove) -- qui il canale c'e', ma la porta non ce
    la fa. La promessa resta comunque mantenuta (l'ho guardata, ho una
    risposta), il testo resta leggibile, e il motivo dichiara la consegna
    mancata riportando l'errore vero della porta."""
    ident = _crea_chiedi(archivio, quando=ADESSO + 10, recapito="notify.mobile_app_x")
    porta = PortaFinta({"eseguito": False, "errore": "il servizio di notifica non risponde"})
    turno = TurnoFinto({"avvisare": True, "testo": "e' salita di 2 gradi"})
    await Sweeper(archivio, execute=porta, interpreta=turno).batti(ADESSO + 11)

    assert len(porta.chiamate) == 1       # il tentativo c'e' stato
    p = archivio.read(ident)
    assert p["stato"] == "mantenuta"
    assert p["testo"] == "e' salita di 2 gradi"
    assert "non e' partita" in p["motivo"]
    assert "non risponde" in p["motivo"]


async def test_il_silenzio_non_notifica_ma_resta_scritto(archivio):
    ident = _crea_chiedi(archivio, quando=ADESSO + 10, recapito="notify.mobile_app_x")
    porta = PortaFinta()
    turno = TurnoFinto({"avvisare": False, "testo": "non e' cambiata: 21,4 gradi come prima"})
    await Sweeper(archivio, execute=porta, interpreta=turno).batti(ADESSO + 11)

    assert porta.chiamate == []          # nessuno e' stato disturbato
    p = archivio.read(ident)
    assert p["stato"] == "mantenuta"     # il silenzio e' un esito RIUSCITO
    assert p["avvisare"] is False
    assert "21,4" in p["testo"]


async def test_avvisare_senza_recapito_non_inventa_un_canale_e_lo_dichiara(archivio):
    ident = _crea_chiedi(archivio, quando=ADESSO + 10, recapito=None)
    porta = PortaFinta()
    await Sweeper(
        archivio, execute=porta,
        interpreta=TurnoFinto({"avvisare": True, "testo": "fa caldo"}),
    ).batti(ADESSO + 11)

    assert porta.chiamate == []
    p = archivio.read(ident)
    assert p["stato"] == "mantenuta"
    assert "nessun modo" in p["motivo"]


async def test_un_turno_che_non_conclude_lascia_la_promessa_fallita(archivio):
    ident = _crea_chiedi(archivio, quando=ADESSO + 10)
    await Sweeper(archivio, execute=PortaFinta(),
                   interpreta=TurnoFinto({"errore": "il turno non ha concluso"})).batti(ADESSO + 11)

    p = archivio.read(ident)
    assert p["stato"] == "fallita"
    assert "non ha concluso" in p["motivo"]


# --- la cucitura vera: nessuna finta dai due lati -----------------------------
#
# Review finale, rilievo CRITICO ①. Ogni test qui sopra usa `PortaFinta`, che
# verifica solo la FORMA della chiamata che l'orologio costruisce -- mai che
# quella forma sia ACCETTABILE per la `verifica` vera. La stringa `"bersaglio":
# {}` che `sweeper._keep_chiedi` costruisce per notificare compariva una
# sola volta in tutto il repo -- la riga che la genera -- e mai in un test
# contro `azione/verifica.py` vera: e' cosi' che il difetto e' sopravvissuto a
# nove task e alla loro review.
#
# Questo test attraversa la giuntura per davvero: la STESSA `Sweeper`, con la
# `ActionActuator` VERA (non un doppio), un registro VERO caricato da un
# `notify.*` vero (senza `target`, com'e' in Home Assistant), e nessuna finta
# a meta' strada. Se qualcuno rimettesse il rifiuto incondizionato su
# bersaglio vuoto in `verification()`, questo test torna rosso -- e non per un
# assert su una stringa isolata, ma perche' la promessa non risulterebbe piu'
# "mantenuta" con un motivo onesto.

class _ClientSoloNotifica:
    """Home Assistant, ridotto al minimo che serve a questa cucitura: UN
    servizio, `notify.mobile_app_x`, che come i `notify.*` veri non dichiara
    un `target`. Nessun `add_state_listener`/`remove_state_listener`: la
    riparazione di `porta.py` non deve aprirne uno per una chiamata senza
    bersaglio, e questo doppio lo dimostra non avendoli affatto -- se la
    porta provasse a chiamarli, la sospensione griderebbe `AttributeError`
    invece di restare silenziosa."""

    def __init__(self) -> None:
        self.chiamate = []

    async def get_services(self):
        return [{"domain": "notify", "services": {
            "mobile_app_x": {"fields": {"message": {}, "title": {}}}}}]

    async def call_service(self, domain, service, data):
        self.chiamate.append((domain, service, data))
        return []


class _CasaMinima:
    """Lo specchio dello stato vivo, con una sola entita' -- basta a
    soddisfare la guardia (b) di `ActionActuator.execute` (uno specchio VUOTO e
    uno MAI CALDO valgono uguale, vedi il suo docstring); la notifica non
    guarda nessuna entita', ma la porta deve comunque poter dire di aver
    visto la casa prima di rifiutare o proseguire."""

    def all_states(self):
        return [{"id": "sun.sun", "state": "above_horizon"}]


async def test_la_notifica_dello_schedulatore_attraversa_la_verifica_vera(archivio):
    from hiris.app.azione.porta import ActionActuator
    from hiris.app.azione.registro import ServiceRegistry

    ident = _crea_chiedi(archivio, quando=ADESSO + 10, recapito="notify.mobile_app_x")
    client = _ClientSoloNotifica()
    registro = ServiceRegistry()
    await registro.refresh(client)
    porta = ActionActuator(client, registro, _CasaMinima())
    turno = TurnoFinto({"avvisare": True, "testo": "e' salita di 2 gradi"})

    await Sweeper(archivio, execute=porta.execute, interpreta=turno).batti(ADESSO + 11)

    assert client.chiamate == [
        ("notify", "mobile_app_x",
         {"message": "e' salita di 2 gradi", "title": "HIRIS"})], (
        "la chiamata non e' arrivata a Home Assistant: la guardia sul "
        "bersaglio vuoto ha rifiutato una notifica che non ha un bersaglio")
    p = archivio.read(ident)
    assert p["stato"] == "mantenuta"
    assert p["motivo"] is None, (
        f"la notifica non e' partita, ed e' esattamente il difetto CRITICO "
        f"della review finale: {p['motivo']!r}")


async def test_la_nota_del_ripiego_finisce_nel_motivo_della_promessa(archivio):
    """Fetta «le promesse seguono la catena»: quando il turno scende dal piano
    alla catena, la promessa lo dichiara -- e' l'unico posto in cui l'utente
    puo' leggerlo, perche' una promessa non ha una risposta in chat."""
    ident = _crea_chiedi(archivio, quando=ADESSO + 10)
    turno = TurnoFinto({"avvisare": False, "testo": "tutto fermo",
                        "nota": "Il Piano Claude Max non ha un token con cui "
                                "rispondere: questo turno l'ha mantenuto la "
                                "catena, a consumo."})

    await Sweeper(archivio, execute=PortaFinta(), interpreta=turno).batti(ADESSO + 11)

    p = archivio.read(ident)
    assert p["stato"] == "mantenuta"
    assert p["testo"] == "tutto fermo"
    assert "a consumo" in (p["motivo"] or ""), (
        "il passaggio dal forfait al consumo non e' scritto da nessuna parte")


async def test_senza_nota_il_motivo_resta_pulito(archivio):
    ident = _crea_chiedi(archivio, quando=ADESSO + 10)
    turno = TurnoFinto({"avvisare": False, "testo": "tutto fermo"})

    await Sweeper(archivio, execute=PortaFinta(), interpreta=turno).batti(ADESSO + 11)

    assert archivio.read(ident)["motivo"] is None


# --- il riavvio: la stessa decisione, due parole diverse ----------------------

def test_al_riavvio_un_fai_e_un_chiedi_dicono_cose_DIVERSE(archivio):
    """`risana()` non riprova NESSUNA delle due, e fa bene: il momento della
    promessa e' passato, e rieseguire «il delta rispetto a un'ora fa» tre ore
    dopo darebbe una risposta confidentemente falsa. E' la stessa ragione per
    cui esiste la tolleranza dei 120 secondi.

    Cio' che cambia e' cosa l'utente puo' CONCLUDERE. Per un `fai` il dubbio e'
    se la casa sia stata toccata -- una serranda. Per un `chiedi` la casa non
    e' stata toccata di sicuro (il turno ha solo strumenti di lettura, per
    costruzione: `SOLA_LETTURA`), e l'unico dubbio e' se la notifica fosse gia'
    partita. Due dubbi diversi meritano due frasi diverse: una sola le
    appiattisce e fa cercare all'utente un problema che non ha."""
    fai = _crea_fai(archivio, quando=ADESSO + 10)
    chiedi = _crea_chiedi(archivio, quando=ADESSO + 10)
    assert archivio.prendi(fai, now=ADESSO + 11)
    assert archivio.prendi(chiedi, now=ADESSO + 11)

    assert archivio.risana(now=ADESSO + 20) == 2

    p_fai = archivio.read(fai)
    p_chiedi = archivio.read(chiedi)
    assert p_fai["stato"] == "fallita" and p_chiedi["stato"] == "fallita"

    assert "non so se fosse gia' partita" in p_fai["motivo"], (
        "per un'azione il dubbio e' se la casa sia stata toccata: resta")
    assert "non so se fosse gia' partita" not in p_chiedi["motivo"], (
        "un `chiedi` non tocca la casa: quel dubbio li' non esiste")
    assert "non ho toccato niente" in p_chiedi["motivo"]
    assert "notifica" in p_chiedi["motivo"], (
        "l'unico dubbio vero di un `chiedi`: la notifica poteva essere gia' "
        "partita, perche' parte prima che la promessa si chiuda")
