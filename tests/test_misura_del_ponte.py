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
    -- e il giorno in cui qualcuno aggiunge una specie ragionabile nuova,
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


def test_il_ponte_registra_gli_argomenti(registro):
    """Spec §7: `tool_args` alla stessa posizione di `tools`, stesso filtro.

    Mutazione ESEGUITA: non emettere `tool_args` da `_measure_turn` -- rossa."""
    ponte._measure_turn(
        {"job_id": "j6", "kind": "chat"}, duration_ms=1,
        tools=[{"tool": "mcp__hiris__search", "input": {"tipo": "light"}},
               {"input": {"scartato": 1}},
               {"tool": "mcp__hiris__view"}],
        occurrence=_occorrenza(), outcome="riuscito")
    assert registro[0]["tools"] == ["search", "view"]
    assert registro[0]["tool_args"] == [{"tipo": "light"}, {}]


def test_la_riga_del_ponte_porta_giri_composizione_e_identita(registro):
    """La riga porta cio' che serve alla giunzione in `server`: l'identita'
    del turno, la composizione, i giri dello stream, l'uscita e il costo a
    listino.

    Mutazione ESEGUITA: non passare `exchanges` nella riga (chiave tolta dal
    dizionario di `_measure_turn`) -- rossa (KeyError); ripristinata, verde."""
    e = _occorrenza(giri=2)
    e.exchanges = [{"message_id": "a", "input_tokens": 10, "output_tokens": None,
                    "cache_read_tokens": 1, "cache_write_tokens": 2,
                    "cache_ttl": "1h", "mcp_calls": 1},
                   {"message_id": "b", "input_tokens": 8, "output_tokens": None,
                    "cache_read_tokens": 3, "cache_write_tokens": 0,
                    "cache_ttl": None, "mcp_calls": 0}]
    e.output_tokens = 623
    e.list_cost_usd = 0.07
    ponte._measure_turn({"job_id": "j6", "kind": "analisi"}, duration_ms=5,
                        tools=[], occurrence=e, outcome="riuscito",
                        exchange_id="TURNO-9",
                        composition={"guide_chars": 1, "core_chars": 2,
                                     "history_chars": 3})
    riga = registro[0]
    assert riga["species"] == "analista"
    assert riga["exchange_id"] == "TURNO-9"
    assert riga["composition"]["history_chars"] == 3
    assert len(riga["exchanges"]) == 2
    assert riga["output_tokens"] == 623
    assert riga["list_cost_usd"] == 0.07


def test_la_composizione_si_pesa_in_TUTTE_le_invocazioni():
    """Il pin della forma: la cella della composizione si scrive dentro
    `_invoca`, accanto a `build_chat_messages`, non su un ramo.

    Mutazione ESEGUITA: non passare `exchange_id` a `_measure_turn` in
    `_reply` -- rossa; ripristinata, verde. (La forma «solo sul ramo con
    strumenti» non e' distinguibile dal conteggio: la prova pinna che la
    cella esista e venga letta, non dove.) Dal fix dopo la revisione
    l'`exchange_id` passa solo se il turno non e' stato ritentato: il
    comportamento lo prova `test_tools_to_bridge.py::
    test_il_turno_ritentato_non_si_prende_i_carichi_dell_invocazione_buttata`."""
    import inspect

    sorgente = inspect.getsource(ponte._reason_chat)
    assert sorgente.count("composition_cell") >= 2
    assert 'exchange_id="" if retried_cell else exchange_id' in sorgente


class _ProcessoFinto:
    """Cio' che `subprocess.run` restituirebbe, senza lanciare la CLI: una
    prova unitaria non spende un turno dell'abbonamento."""

    returncode = 1
    stdout = ""
    stderr = "la CLI non e' stata lanciata: e' una prova"


class _StreamTroncato(_ProcessoFinto):
    """La CLI esce 0 ma il flusso si chiude senza l'evento `result`: un
    giro dell'assistente e poi niente (esito (3) di `_reason_chat`)."""

    returncode = 0
    stdout = ('{"type": "assistant", "message": {"id": "m1", "content": '
              '[{"type": "text", "text": "a meta"}]}}\n')
    stderr = ""


def _attuazione_finta(monkeypatch, processo=_ProcessoFinto, **extra_context):
    """Un turno di attuazione vero fino a `subprocess.run`: specie senza
    strumenti e autosufficiente, quindi nessuna sonda."""
    monkeypatch.setattr(ponte.subprocess, "run",
                        lambda argv, *a, **kw: processo())
    context = {"history": [{"role": "user", "content": "le osservazioni"}],
               "system_prompt": "sei l'attuatore",
               "istruzione": "Rispondi SOLO con un oggetto JSON."}
    context.update(extra_context)
    ponte.reason({"kind": "attuazione", "job_id": "ja", "context": context},
                 "live", client=object(), base_url="http://127.0.0.1:8099")


def test_un_giro_di_fondo_SENZA_strumenti_scrive_la_sua_composizione(
        registro, monkeypatch):
    """Il consumo di osservatore, analista e attuatore sul ponte e' la
    richiesta esplicita del proprietario: una specie senza strumenti deve
    scrivere la composizione come la chat. Il pin sul sorgente non lo vede,
    questa prova si': passa da `reason()` fino alla CLI finta.

    Mutazione ESEGUITA: avvolgere l'append in `_invoca` in `if active_tools:`
    -- rossa (composition None); ripristinata, verde."""
    _attuazione_finta(monkeypatch)
    riga = registro[0]
    assert riga["species"] == "attuatore"
    assert riga["composition"] is not None
    assert riga["composition"]["history_chars"] > 0
    assert riga["exchange_id"]


def test_con_la_propria_istruzione_il_nucleo_consegnato_e_zero(
        registro, monkeypatch):
    """Un turno che porta la propria `istruzione` non riceve il blocco
    guida/contesto (`build_chat_messages`): il `contesto` del job non arriva
    al modello, e contarlo come nucleo direbbe il falso.

    Mutazione ESEGUITA: `core_chars = len((contesto or "").strip())` senza
    guardare l'istruzione -- rossa (core_chars 24); ripristinata, verde."""
    _attuazione_finta(monkeypatch, contesto="il nucleo della casa, 24")
    composizione = registro[0]["composition"]
    assert composizione["core_chars"] == 0
    assert composizione["guide_chars"] > 0


def test_la_CLI_che_esce_con_errore_e_un_turno_FALLITO(registro, monkeypatch):
    """`rc != 0` restituisce `[errore runner rc=...]`: un sentinella, non
    una risposta del modello. Scritto `riuscito`, il registro contava i
    guasti del ponte fra i successi.

    Mutazione ESEGUITA: tolto `outcome="fallito"` dal `_reply` del ramo
    `rc != 0` -- rossa ('riuscito' invece di 'fallito'); ripristinata,
    verde."""
    _attuazione_finta(monkeypatch)
    assert registro[0]["outcome"] == "fallito"


def test_il_flusso_SENZA_result_e_un_turno_FALLITO(registro, monkeypatch):
    """Esito (3): la CLI esce 0 ma il flusso si chiude senza l'evento finale.
    La reply dichiara che non c'e' una risposta completa: e' un fallimento.

    Mutazione ESEGUITA: tolto `outcome="fallito"` dal `_reply` del ramo
    `not occurrence.has_result` -- rossa ('riuscito' invece di 'fallito');
    ripristinata, verde."""
    _attuazione_finta(monkeypatch, processo=_StreamTroncato)
    assert registro[0]["outcome"] == "fallito"
    assert len(registro[0]["exchanges"]) == 1, "il ramo e' davvero il (3)"


def test_senza_num_turns_i_giri_sono_quelli_dello_stream(registro):
    """La CLI uccisa non dichiara `num_turns`: il turno ha comunque fatto i
    suoi giri, e lo stream li ha visti. Zero direbbe «nessun giro».

    Mutazione ESEGUITA: `"iterations": n_cli or 0` (il vecchio) -- rossa
    (0 invece di 2); ripristinata, verde."""
    e = _occorrenza()
    e.num_exchanges = None
    e.exchanges = [{"message_id": "a"}, {"message_id": "b"}]
    ponte._measure_turn({"job_id": "j7", "kind": "chat"}, duration_ms=1,
                        tools=[], occurrence=e, outcome="fallito")
    assert registro[0]["iterations"] == 2


def test_strumenti_in_parallelo_i_giri_sono_le_chiamate_non_num_turns(registro):
    """Misurato dal vivo il 29/09/2026 (turno `og7xwGjc4Yji`, 3.70.0): 16
    strumenti, 12 `view` partiti insieme in UNA chiamata; la CLI dichiara
    `num_turns=17`, lo stream ha 5 `message.id` -- e la somma dei 5 giri
    coincide al token con l'`usage` del turno (10 / 60021 / 79401). Le
    chiamate al modello sono 5: `num_turns` conta altro, e sulla catena
    `iterations` sono le chiamate. Una parola, una cosa sola.

    Mutazione ESEGUITA: `"iterations": n_cli if n_cli is not None else
    n_stream` (il vecchio) -- rossa (17 invece di 5); ripristinata, verde."""
    e = _occorrenza()
    e.num_exchanges = 17
    e.exchanges = [{"message_id": m} for m in "abcde"]
    ponte._measure_turn({"job_id": "j8", "kind": "chat"}, duration_ms=1,
                        tools=[], occurrence=e, outcome="riuscito")
    assert registro[0]["iterations"] == 5
