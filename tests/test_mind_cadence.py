"""La cadenza di riconsiderazione: **ogni quanto l'osservatore ripensa tutta
la casa**, e perche' il numero non sta nel codice.

**La regola (spec §5.2).** *«L'osservatore riconsidera l'intera casa piu'
spesso di quanto duri la memoria di Home Assistant»*. Se ripensa il proprio
campo entro quella finestra, tutto cio' che aveva scartato e' ancora
recuperabile; se la supera, cio' che ha scartato e' perduto per sempre --
riscrivere l'obiettivo fra tre mesi non fa ricomparire i tre mesi mancanti.
E' cio' che sostituisce il pavimento: non una lista di cose da guardare
comunque, ma **la garanzia di potersi ricredere in tempo**.

**E la finestra non si assume: si misura.** Verificato dal vivo l'11/09/2026,
Home Assistant non la dichiara da nessuna porta -- `recorder/info` risponde e
non la contiene, `recorder/config` e `recorder/statistics_info` non esistono.
Si cala una sonda e si guarda se torna su con qualcosa
(`HAClient.recorded_changes`).

**Misura sulla casa vera, 11/09/2026**: finestra **7,000 giorni**, cadenza
**3,5 giorni (84 ore)**, in due raffiche da 646 ms e 557 KB in tutto.
"""
import os

import pytest

from hiris.app.mind import cadence
from hiris.app.mind.store import ObservationsStore

GIORNO = 86400.0
ORA = 1_000_000.0


class _Casa:
    """Una casa finta con una memoria di durata NOTA.

    Non porge risposte scritte a mano: risponde come risponderebbe Home
    Assistant, cioe' «c'e' qualcosa registrato qui?» calcolato dalla memoria
    che ha davvero. Cosi' la prova esercita l'algoritmo della misura invece di
    ricevere il risultato gia' fatto -- e un algoritmo sbagliato sbaglia.
    """

    def __init__(self, memoria_s, *, buchi=(), muta=False, sonde_mute=()):
        self.memoria_s = memoria_s
        self.buchi = buchi          # tratti (da_profondita', a_profondita') spenti
        self.muta = muta            # Home Assistant non risponde affatto
        self.sonde_mute = sonde_mute  # profondita' a cui la singola domanda cade
        self.raffiche = []

    async def recorded_changes(self, entity_ids, windows):
        self.raffiche.append([ORA - start for start, _ in windows])
        if self.muta:
            return [None] * len(windows)
        out = []
        for start, _fine in windows:
            profondita = ORA - start
            if any(abs(profondita - m) < 1.0 for m in self.sonde_mute):
                out.append(None)
                continue
            spenta = any(a <= profondita <= b for a, b in self.buchi)
            out.append(0 if (profondita > self.memoria_s or spenta) else 42)
        return out


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


# -- la misura ---------------------------------------------------------

@pytest.mark.asyncio
async def test_la_finestra_misurata_non_e_mai_piu_lunga_di_quella_vera():
    """**La direzione che conta.** Una finestra misurata piu' CORTA del vero
    fa riconsiderare piu' spesso: costa un giro in piu'. Una misurata piu'
    LUNGA fa riconsiderare quando il grezzo e' gia' stato potato, e cio' che
    l'osservatore aveva scartato non torna piu' -- il danno che la spec §5.2
    esiste per impedire.

    Mutazione che la uccide: tornare la profondita' della prima sonda VUOTA
    invece dell'ultima piena.
    """
    for veri in (7 * GIORNO, 10 * GIORNO, 30 * GIORNO, 12 * 3600.0):
        casa = _Casa(veri)
        misurata = await cadence.measure_memory_window(casa, ["a"], now=ORA)
        assert misurata is not None
        assert misurata <= veri, f"memoria vera {veri}, misurata {misurata}"


@pytest.mark.asyncio
async def test_e_non_e_nemmeno_inutilmente_corta():
    """Misurare «un giorno» su una casa che ne ricorda sette farebbe
    riconsiderare quattordici volte di piu' del necessario: ogni giro e'
    una lettura dell'intera casa al modello (**≈26.600 token**).

    Su sette giorni veri la misura torna **7,000 giorni esatti**, come dal
    vivo: la scala grossa ferma il tratto fra 4 e 8, la seconda raffica lo
    divide in otto.
    """
    casa = _Casa(7 * GIORNO)
    assert await cadence.measure_memory_window(casa, ["a"], now=ORA) == 7 * GIORNO


@pytest.mark.asyncio
async def test_un_buco_nella_memoria_non_accorcia_la_finestra():
    """Home Assistant spento due giorni lascia un tratto vuoto in mezzo alla
    storia. Fermarsi alla prima sonda vuota leggerebbe quel buco come il
    confine della memoria, e la casa riconsidererebbe ogni dodici ore per
    sempre senza che nessuno capisca perche'.

    **Si prende la sonda PIENA piu' profonda, non la prima vuota.** Qui il
    buco copre il gradino dei 2 giorni; quello dei 4 lo scavalca, ed e' da li'
    che riparte la misura.

    **Il limite, dichiarato**: un buco che inghiotte un gradino INTERO della
    scala (fra i 2 e gli 8 giorni, per esempio) accorcia la misura, perche'
    nessuna sonda atterra oltre. Accorcia -- non allunga: si riconsidera piu'
    spesso del necessario finche' il buco non esce dalla memoria da solo. E'
    la stessa direzione sicura di tutto il resto del modulo, e il caso si
    ripara da se'.

    Mutazione che la uccide: uscire dal giro al primo conteggio zero.
    """
    casa = _Casa(7 * GIORNO, buchi=[(1.5 * GIORNO, 3.5 * GIORNO)])

    misurata = await cadence.measure_memory_window(casa, ["a"], now=ORA)

    assert misurata == 7 * GIORNO


@pytest.mark.asyncio
async def test_una_casa_che_non_ricorda_niente_non_si_scrive_come_misurata():
    """`None`, e chi chiama lo sa. Un `0` sarebbe una cadenza di zero secondi:
    l'osservatore rileggerebbe tutta la casa a ogni giro del lavoro periodico.
    """
    assert await cadence.measure_memory_window(_Casa(0.0), ["a"], now=ORA) is None


@pytest.mark.asyncio
async def test_una_sonda_muta_non_diventa_una_memoria_corta():
    """Se Home Assistant non risponde, non si e' misurato niente: la
    differenza fra «non ricorda» e «non ha risposto» e' la stessa che
    `recorded_changes` tiene con `None` invece di `0`, e va fino in fondo.

    Mutazione che la uccide: leggere `None` come «vuoto», cioe' come confine.
    """
    assert await cadence.measure_memory_window(_Casa(7 * GIORNO, muta=True),
                                               ["a"], now=ORA) is None


@pytest.mark.asyncio
async def test_una_sola_sonda_caduta_non_diventa_il_confine():
    """**La differenza fra «non ricorda» e «non ha risposto», fino in fondo.**
    Una sonda sola che cade -- rete lenta, raffica troncata -- non e' ne' piena
    ne' vuota: non deve spostare il confine in nessuna delle due direzioni.
    Leggerla come vuota la farebbe passare per il fondo della memoria, e
    l'intera misura si fermerebbe li'.

    Qui la memoria e' di sette giorni e cade la sonda dei quattro. Il confine
    vero resta oltre, e la misura deve superare il gradino caduto.

    Mutazione che la uccide (eseguita, ed era VERDE prima di questa prova):
    `not count` invece di `count == 0` nella ricerca del confine.
    """
    casa = _Casa(7 * GIORNO, sonde_mute=[4 * GIORNO])

    misurata = await cadence.measure_memory_window(casa, ["a"], now=ORA)

    assert misurata is not None
    assert misurata > 4 * GIORNO


@pytest.mark.asyncio
async def test_una_memoria_lunghissima_torna_un_limite_inferiore_non_un_niente():
    """Un recorder configurato per tenere anni supera l'ultimo gradino della
    scala. Non e' un guasto: e' una memoria di cui sappiamo solo che arriva
    **almeno** fin li', e una cadenza calcolata su quel limite e' comunque
    dentro la memoria vera. Tornare `None` qui fermerebbe la riconsiderazione
    proprio sulla casa che ricorda di piu'.
    """
    casa = _Casa(10 * 365 * GIORNO)

    misurata = await cadence.measure_memory_window(casa, ["a"], now=ORA)

    assert misurata is not None
    assert misurata >= 256 * GIORNO
    assert len(casa.raffiche) == 1     # nessun tratto da dividere: niente seconda raffica


@pytest.mark.asyncio
async def test_la_seconda_raffica_cerca_dentro_il_tratto_trovato_dalla_prima():
    """La scala grossa raddoppia -- 1, 2, 4, 8 giorni -- e su sette giorni
    lascia un tratto largo quattro. Ripartire da zero con la seconda raffica
    ricomprerebbe cio' che la prima ha gia' pagato.

    Mutazione che la uccide: dividere `(0, hi)` invece di `(lo, hi)`.
    """
    casa = _Casa(7 * GIORNO)

    await cadence.measure_memory_window(casa, ["a"], now=ORA)

    assert len(casa.raffiche) == 2
    fine = casa.raffiche[1]
    assert all(4 * GIORNO < p < 8 * GIORNO for p in fine), fine


@pytest.mark.asyncio
async def test_le_sonde_non_scendono_nel_futuro():
    """Ogni finestra parte indietro nel tempo: una sonda calata in avanti
    tornerebbe sempre vuota e falserebbe il confine."""
    casa = _Casa(7 * GIORNO)

    await cadence.measure_memory_window(casa, ["a"], now=ORA)

    assert all(p > 0 for raffica in casa.raffiche for p in raffica)


# -- la regola ---------------------------------------------------------

def test_la_cadenza_e_meta_della_finestra():
    """**Perche' una frazione e non una sottrazione.** «La finestra meno un
    giorno» diventa negativa su una casa che ricorda dodici ore, e nessuno se
    ne accorgerebbe finche' l'osservatore non gira in continuazione. Meta'
    regge qualunque recorder, e lascia un fattore due di margine: anche un
    giro saltato -- add-on fermo, Home Assistant irraggiungibile -- resta
    dentro la memoria.
    """
    assert cadence.cadence_from(7 * GIORNO) == 3.5 * GIORNO
    assert cadence.cadence_from(12 * 3600.0) == 6 * 3600.0


def test_senza_finestra_non_c_e_cadenza():
    """Non si inventa un numero di ripiego: una cadenza finta sarebbe
    indistinguibile da una misurata, e nella pagina direbbe al proprietario
    una cosa che nessuno ha verificato."""
    assert cadence.cadence_from(None) is None
    assert cadence.cadence_from(0.0) is None


def test_mai_riconsiderato_vuol_dire_adesso():
    """Al primo avvio non c'e' niente da aspettare: l'osservatore non ha
    ancora deciso niente, e senza scope non guarda nulla."""
    assert cadence.due(last_ts=None, cadence_s=3.5 * GIORNO, now=ORA) is True


def test_si_riconsidera_quando_la_cadenza_e_passata_non_prima():
    """Il confine e' incluso: a cadenza esatta si rifa'. Un `>` stretto
    rimanderebbe di un intero giro del lavoro periodico ogni volta.

    Mutazione che la uccide: `>` invece di `>=`.
    """
    cad = 3.5 * GIORNO
    assert cadence.due(last_ts=ORA - cad + 1, cadence_s=cad, now=ORA) is False
    assert cadence.due(last_ts=ORA - cad, cadence_s=cad, now=ORA) is True
    assert cadence.due(last_ts=ORA - 10 * GIORNO, cadence_s=cad, now=ORA) is True


def test_senza_cadenza_misurata_non_si_riconsidera_a_caso():
    """Se la finestra non si e' potuta misurare, la domanda «e' ora?» non ha
    risposta. Dire di si' farebbe rileggere tutta la casa a ogni giro; dire
    di no la fermerebbe finche' la misura non riesce. **Si dice di no, e la
    pagina dira' perche'** -- la prima e' una spesa che si ripete ogni minuto
    e nessuno la vede, la seconda si vede e si ripara.

    Il primo avvio non ci casca: `measure_memory_window` gira PRIMA, e se la
    misura manca l'osservatore non ha comunque niente con cui decidere.
    """
    assert cadence.due(last_ts=ORA - 30 * GIORNO, cadence_s=None, now=ORA) is False
    assert cadence.due(last_ts=None, cadence_s=None, now=ORA) is False


# -- cio' che l'archivio ricorda della riconsiderazione -----------------

def test_prima_di_tutto_non_c_e_nessuna_riconsiderazione(archivio):
    assert archivio.last_reconsideration() is None


def test_la_riconsiderazione_si_annota_con_la_finestra_che_l_ha_decisa(archivio):
    """Non basta «l'ho fatto il 9»: la pagina deve poter dire **perche' ogni
    84 ore**, e quel numero viene da una misura che cambia se il proprietario
    cambia il recorder. Scritto accanto alla riconsiderazione, resta vero per
    quella riconsiderazione anche quando la misura successiva dara' altro.
    """
    archivio.record_reconsideration(when_ts=ORA, window_s=7 * GIORNO,
                                  cadence_s=3.5 * GIORNO)

    ultima = archivio.last_reconsideration()
    assert ultima["quando_ts"] == ORA
    assert ultima["finestra_s"] == 7 * GIORNO
    assert ultima["cadenza_s"] == 3.5 * GIORNO


def test_si_annota_anche_la_riconsiderazione_senza_misura(archivio):
    """La finestra puo' non essere misurabile -- Home Assistant muto -- e
    l'osservatore gira lo stesso al primo avvio. La riga si scrive con la
    misura mancante DICHIARATA, invece di non scriverla: senza, la pagina
    direbbe «mai riconsiderato» di una casa appena riconsiderata."""
    archivio.record_reconsideration(when_ts=ORA, window_s=None, cadence_s=None)

    ultima = archivio.last_reconsideration()
    assert ultima["quando_ts"] == ORA
    assert ultima["finestra_s"] is None
    assert ultima["cadenza_s"] is None


def test_l_ultima_e_l_ultima_non_la_prima(archivio):
    """Mutazione che la uccide: ordinare per `quando_ts` crescente."""
    archivio.record_reconsideration(when_ts=ORA, window_s=7 * GIORNO, cadence_s=3.5 * GIORNO)
    archivio.record_reconsideration(when_ts=ORA + GIORNO, window_s=6 * GIORNO,
                                  cadence_s=3 * GIORNO)

    assert archivio.last_reconsideration()["quando_ts"] == ORA + GIORNO
    assert archivio.last_reconsideration()["finestra_s"] == 6 * GIORNO
