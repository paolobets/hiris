"""Il ponte non finiva nel registro dei turni, e nessuno poteva accorgersene.

Misurato il 24/09/2026: 32 domande vere fatte alla casa sull'abbonamento
Max hanno prodotto **zero** righe nel registro. Il registro aveva 37 turni,
tutti della catena, e la colonna `canale` conteneva un solo valore --
"catena" -- perche' e' una COSTANTE scritta in tutti e sette i punti che
misurano. Una colonna che puo' contenere un valore solo non e' una misura:
e' una decorazione, e ci avevo costruito sopra un confronto che appaiava le
domande del ponte ai turni della catena di un'ora prima.

Due difetti, non uno:

1. la chat sul ponte passa dalla coda del ragionamento e non tocca
   `misura_turno`: mezza strada del prodotto era invisibile;
2. `canale` era letterale ovunque, quindi anche un turno misurato sarebbe
   uscito etichettato "catena".

**Cosa queste prove NON dimostrano.** Che il gancio venga davvero chiamato
su un turno vero: quello si vede solo interrogando la casa e leggendo
`/api/misure`, e va fatto a ogni rilascio che tocchi questo file. Qui si
pinna cio' che e' pinnabile a banco -- la forma della riga, la tabella
delle specie, e che una misura rotta non faccia cadere il turno.
"""
from __future__ import annotations

import pytest

from hiris.app.agent import runner as ponte
from hiris.app.steering import SPECIE


@pytest.fixture
def registro():
    righe: list[dict] = []
    ponte.set_turn_logger(righe.append)
    try:
        yield righe
    finally:
        ponte.set_turn_logger(None)


def _occorrenza(giri: int = 3, modello: str = "claude-opus-4-8"):
    e = ponte.StreamOccurrence()
    e.usage = {"input_tokens": 10, "output_tokens": 5}
    e.result = {"modelUsage": {modello: {"inputTokens": 10, "outputTokens": 5}}}
    e.num_exchanges = giri
    return e


def test_un_turno_del_ponte_si_dichiara_ponte(registro):
    """La riga che mancava del tutto."""
    ponte._measure_turn({"job_id": "j1", "kind": "chat"}, duration_ms=1234,
                           tools=[{"tool": "search"}, {"tool": "view"}],
                           occurrence=_occorrenza(), outcome="riuscito")
    riga = registro[0]
    assert riga["channel"] == "ponte"
    assert riga["species"] == "chat"
    assert riga["duration_ms"] == 1234
    assert riga["iterations"] == 3
    assert riga["tools"] == ["search", "view"]
    assert riga["outcome"] == "riuscito"
    # Il modello e' quello che ha RISPOSTO, non quello che si era chiesto:
    # e' la stessa legge di `_logga_uso`.
    assert riga["model"] == "claude-opus-4-8"


def test_ogni_specie_del_ponte_ha_un_nome_nel_registro():
    """Il cancello della tabella.

    Il ponte chiama le sue specie `scope`, `ricetta`, `analisi`; il registro
    le chiama `osservatore`, `ricette`, `analista`. Due vocabolari per gli
    stessi attori esistono davvero, quindi la traduzione esiste in UN posto
    -- e il giorno in cui qualcuno aggiunge una sesta specie ragionabile,
    questa prova diventa rossa invece di far scrivere al registro un nome
    che `misura_turno` rifiuterebbe.
    """
    assert set(ponte.JOB_SPECIES) == set(ponte.RAGIONABILI)
    assert set(ponte.JOB_SPECIES.values()) <= SPECIE


def test_una_specie_mai_vista_non_ferma_il_turno(registro):
    """Un `reasoning.db` di un'installazione precedente puo' portare una
    specie che non esiste piu'. Non si scrive una riga con un nome
    inventato -- renderebbe il registro inservibile proprio sulla domanda
    per cui esiste -- e non si solleva: il turno ha gia' risposto."""
    ponte._measure_turn({"job_id": "j2", "kind": "olistico"}, duration_ms=1,
                           tools=[], occurrence=_occorrenza(),
                           outcome="riuscito")
    assert registro == []


def test_una_misura_rotta_non_fa_cadere_il_turno():
    """Un registro che fa cadere la risposta del proprietario sarebbe
    peggio del buco che chiude -- la stessa legge di `misura_turno`."""
    def esplode(_riga):
        raise RuntimeError("archivio giu'")

    ponte.set_turn_logger(esplode)
    try:
        ponte._measure_turn({"job_id": "j3", "kind": "chat"}, duration_ms=1,
                               tools=[], occurrence=_occorrenza(),
                               outcome="riuscito")
    finally:
        ponte.set_turn_logger(None)


def test_senza_gancio_non_succede_niente():
    """L'add-on puo' girare senza archivio dei consumi: `server.py` collega
    il gancio solo quando c'e'."""
    ponte.set_turn_logger(None)
    ponte._measure_turn({"job_id": "j4", "kind": "chat"}, duration_ms=1,
                           tools=[], occurrence=_occorrenza(),
                           outcome="riuscito")


def test_il_funnel_delle_risposte_misura():
    """`_reply` e' dichiarato «l'UNICO modo in cui una risposta esce da
    questa funzione», ed e' per questo che la misura sta li' e non su sei
    rami. Se un giorno nascesse un settimo ramo che non passa di la', la
    misura lo perderebbe in silenzio: questo pin e' il guardiano di quella
    dichiarazione, non una prova di comportamento.
    """
    import inspect

    sorgente = inspect.getsource(ponte._reason_chat)
    assert sorgente.count("_measure_turn(") == 1, (
        "la misura del turno del ponte non e' piu' nell'imbuto di `_reply`: "
        "o e' sparita, o e' stata copiata su un ramo -- e una copia resta "
        "indietro alla prima correzione fatta sull'altra")


def test_gli_strumenti_hanno_UN_nome_solo(registro):
    """Il registro deve poter SOMMARE le due strade.

    Misurato sul primo turno vero del ponte (24/09/2026, 19:05): gli
    strumenti uscivano come `mcp__hiris__search`, mentre la catena scrive
    `search`. Due nomi per la stessa cosa, e la domanda «quali strumenti
    non vengono mai usati» -- quella che mi aveva gia' fatto sbagliare una
    volta -- sarebbe tornata a contare due volte lo stesso catalogo.

    Il prefisso e' un dettaglio del TRASPORTO (MCP prefissa ogni nome col
    nome del server), non dell'attore: si toglie al confine, dove il
    trasporto finisce. Cio' che NON porta il prefisso -- `ToolSearch` e
    gli altri strumenti della CLI -- resta com'e': e' un attore diverso, e
    fonderlo coi nostri direbbe che HIRIS ha strumenti che non ha.
    """
    ponte._measure_turn(
        {"job_id": "j5", "kind": "chat"}, duration_ms=1,
        tools=[{"tool": "mcp__hiris__search"}, {"tool": "mcp__hiris__view"},
               {"tool": "ToolSearch"}],
        occurrence=_occorrenza(), outcome="riuscito")
    assert registro[0]["tools"] == ["search", "view", "ToolSearch"]
