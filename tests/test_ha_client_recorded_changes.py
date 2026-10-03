"""`HAClient.recorded_changes()`: «in questa finestra Home Assistant ha ancora
qualcosa di registrato?».

**Perche' esiste, e perche' non e' una lettura di configurazione.** Misurato
dal vivo l'11/09/2026: `recorder/info` risponde -- e non dice la finestra
(`{"backlog", "db_in_default_location", "max_backlog", "migration_in_progress",
"migration_is_live", "recording", "thread_running"}`); `recorder/config` e
`recorder/statistics_info` **non esistono** (`unknown_command`). Home Assistant
non dichiara da nessuna porta quanti giorni conserva: l'unico modo di saperlo
e' **chiederglielo**, e questa e' la domanda.

**Perche' si contano solo le righe DENTRO la finestra.**
`history/history_during_period` rimanda anche lo stato dell'entita' **all'inizio**
della finestra, che e' una riga piu' vecchia della finestra stessa: contarla
direbbe «qui c'e' memoria» in un punto dove la memoria non arriva piu'.

**Misura della forma, casa vera, 11/09/2026**: una finestra di 10 minuti su
839 entita' costa 25-45 ms e 25 KB dove c'e' memoria, **8 ms e 2 byte** dove
non ce n'e'.
"""
import sys
from pathlib import Path

import pytest

from hiris.app.proxy.ha_client import HAClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

HISTORY = "history/history_during_period"


def _house(series=None, **injected) -> CasaFinta:
    """La casa finta (D8): il client vero, e Home Assistant che risponde a
    ogni finestra con `series(extra)` -- la serie che rimanderebbe per quella
    domanda. Le connessioni si contano su `house.connections`: dieci comandi
    sono dieci comandi sia in una raffica sia in dieci."""
    answers = {} if series is None else {HISTORY: series}
    return CasaFinta({}, answers=answers, **injected)


class _Finto:
    """Il trasporto finto che resta, per UNA prova sola: la casa finta fa
    tacere o rifiutare un COMANDO intero, e qui servono tre finestre dello
    stesso comando con tre esiti diversi (vedi la prova)."""

    def __init__(self, risposte):
        self.risposte = risposte

    async def _ws_send(self, commands, timeout=10.0):
        return list(self.risposte)


def _client(finto):
    client = HAClient.__new__(HAClient)
    client._ws_send = finto._ws_send
    return client


@pytest.mark.asyncio
async def test_lo_stato_all_inizio_della_finestra_non_e_memoria_dentro_la_finestra():
    """La riga che Home Assistant mette per prima e' lo stato **a** `da`, e
    porta la data di quando e' stato scritto davvero -- prima della finestra.
    Contarla farebbe dire «qui c'e' ancora memoria» a una sonda calata dove
    la memoria e' gia' finita, e la cadenza di riconsiderazione diventerebbe
    piu' lunga della memoria: esattamente cio' che la spec §5.2 vieta.

    Mutazione che la uccide: contare tutte le righe invece di quelle dopo `da`.
    """
    house = _house(lambda extra: {
        "climate.bagno": [{"s": "heat", "lu": 900.0},     # prima: non conta
                          {"s": "off", "lu": 1500.0}],    # dentro: conta
        "person.marta": [{"s": "home", "lu": 500.0}],     # solo il fossile
    })

    conti = await house.recorded_changes(
        ["climate.bagno", "person.marta"], [(1000.0, 1600.0)])

    assert conti == [1]


@pytest.mark.asyncio
async def test_una_sonda_che_non_risponde_non_e_una_casa_senza_memoria():
    """`None`, non `0`. Zero afferma «qui Home Assistant non ricorda niente»,
    ed e' un'affermazione che non si puo' fare quando la domanda non e'
    nemmeno arrivata: la misura ne dedurrebbe una finestra corta e una cadenza
    stretta, senza che nessuno sappia perche'.

    Mutazione che la uccide: tornare `0` per una risposta mancante.

    **Resta sul trasporto finto** (Tappa 2, Task 12): servono una finestra
    senza risposta, una rifiutata e una buona nella STESSA raffica, e la casa
    finta fa tacere o rifiutare un comando per intero, non una finestra.
    """
    finto = _Finto([None,
                    {"success": False, "error": {"message": "boom"}},
                    {"success": True, "result": {"x": [{"s": "1", "lu": 3500.0}]}}])

    conti = await _client(finto).recorded_changes(
        ["x"], [(1000.0, 1600.0), (2000.0, 2600.0), (3000.0, 3600.0)])

    assert conti == [None, None, 1]


@pytest.mark.asyncio
async def test_tutte_le_sonde_partono_in_una_raffica_sola():
    """Dieci profondita' sono dieci domande, non dieci connessioni: la scala
    grossa della misura le manda tutte insieme (`_ws_send`), e la casa vera
    ci mette **264 ms in tutto**. Ogni raffica in piu' e' un handshake e
    un'autenticazione in piu'.

    **Si contano le connessioni, non i comandi**: tre comandi sono tre
    comandi tanto in una raffica quanto in tre, e la prima stesura di questa
    prova contava proprio quelli -- restava verde con la mutazione sotto,
    eseguita.

    Mutazione che la uccide: un `_ws_send` per finestra.
    """
    house = _house(lambda extra: {})

    await house.recorded_changes(["a", "b"], [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)])

    assert house.connections == [("ws", (HISTORY, HISTORY, HISTORY))]


@pytest.mark.asyncio
async def test_la_domanda_chiede_il_minimo_indispensabile():
    """Gli attributi non servono a sapere SE c'e' memoria, e sono il grosso
    della risposta: senza `no_attributes`, Home Assistant rimanda il
    dizionario intero a ogni riga. Misurato: 25 KB con, contro le centinaia
    che costerebbe senza."""
    house = _house(lambda extra: {})

    await house.recorded_changes(["a"], [(1000.0, 1600.0)])

    ((_, extra),) = house.calls
    assert extra["entity_ids"] == ["a"]
    assert extra["minimal_response"] is True
    assert extra["no_attributes"] is True
    assert extra["start_time"].startswith("1970-01-01T00:16:40")
    assert extra["end_time"].startswith("1970-01-01T00:26:40")


@pytest.mark.asyncio
async def test_la_connessione_caduta_non_solleva_e_non_inventa():
    """Stessa disciplina di ogni lettura del ponte: mai un'eccezione che
    fermi il lavoro periodico. Una raffica che non parte affatto e' la busta
    del silenzio (D3), non una scala di `None` che si leggerebbe come «nessuna
    finestra ricorda niente».

    Fino al Task 12 della Tappa 2 la prova cominciava provando che il
    trasporto FINTO sollevasse: un'asserzione sulla finta, non sul client
    (il vero `_ws_send` non solleva). E' uscita con la finta."""
    house = _house(silence={HISTORY})

    answer = await house.recorded_changes(["a"], [(1.0, 2.0), (3.0, 4.0)])
    assert answer == {"errore": "Home Assistant non ha risposto",
                      "causa": "silenzio", "codice": None}


@pytest.mark.asyncio
async def test_senza_finestre_non_si_va_in_rete():
    house = _house()
    assert await house.recorded_changes(["a"], []) == []
    assert house.connections == []
