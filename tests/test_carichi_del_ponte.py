"""Cio' che HIRIS consegna alla CLI del ponte, turno per turno.

Le definizioni (`tools/list`) e i risultati (`tools/call`) passano da
`/api/mcp`, e quella rotta sa per quale turno: `X-HIRIS-Turno`. Spec «le
misure complete» §4(2).

**Thread-safe, e non per scrupolo.** La rotta scrive dal thread del loop; chi
legge (`server._registra_turno_ponte`) gira nel thread dell'executor del
ponte. Il contatore dei giri di `handlers_mcp` non ha lock perche' lo tocca
un thread solo: questo ne ha due.

La prova sulla rotta VERA (`handle_mcp` con `X-HIRIS-Turno`) vive in
`tests/test_mcp_route.py`, accanto al fixture `rotta` che costruisce l'app
autenticata a token.
"""
import threading

from hiris.app.usage.bridge_loads import MAX_TRACKED, BridgeLoads


def test_un_turno_raccoglie_definizioni_e_risultati_in_ordine():
    """Mutazione ESEGUITA: `results` come somma invece che lista -- rossa."""
    b = BridgeLoads()
    b.tools_listed("T1", 45388, 16)
    b.result_served("T1", 1200)
    b.result_served("T1", 300)
    assert b.take("T1") == {"tools_chars": 45388, "tools_sent": 16,
                            "results": [1200, 300]}


def test_due_turni_in_parallelo_non_si_mescolano():
    """La chat del proprietario e il giro orario dell'analista insieme.

    Mutazione ESEGUITA: una lista unica senza chiave -- rossa."""
    b = BridgeLoads()
    b.result_served("chat", 10)
    b.result_served("analista", 99)
    b.result_served("chat", 20)
    assert b.take("chat")["results"] == [10, 20]
    assert b.take("analista")["results"] == [99]


def test_prendere_DIMENTICA_il_turno():
    """Mutazione ESEGUITA: `take` con `.get` invece di `.pop` -- rossa."""
    b = BridgeLoads()
    b.result_served("T", 1)
    assert b.take("T") is not None
    assert b.take("T") is None


def test_un_turno_che_non_ha_lasciato_niente_e_None():
    """Mutazione ESEGUITA: `take` che crea la voce vuota (`_entry`) invece di
    restituire `None` -- rossa."""
    assert BridgeLoads().take("mai-visto") is None


def test_senza_identita_non_si_annota_niente():
    """Una `tools/call` senza `X-HIRIS-Turno` (la sonda, un test) non si
    attribuisce a nessun turno.

    Mutazione ESEGUITA: tolte le guardie `if not exchange_id` in
    `tools_listed`, `result_served` e `take` -- rossa."""
    b = BridgeLoads()
    b.result_served("", 5)
    b.tools_listed("", 5, 1)
    assert b.take("") is None


def test_il_tetto_espelle_il_turno_che_tace_da_piu_tempo():
    """Mutazione ESEGUITA: tolto il `move_to_end` (FIFO invece di LRU) --
    rossa: «vivo» viene espulso pur restando in uso.

    La prova del brief asseriva solo `take("vivo") is not None`, e con la
    mutazione restava VERDE: «vivo» veniva espulso e subito ricreato dalla
    scrittura seguente, vuoto. Si asserisce il FATTO -- nessun risultato
    perso -- non la presenza della chiave."""
    b = BridgeLoads()
    b.result_served("vivo", 1)
    for i in range(MAX_TRACKED):
        b.result_served(f"altro{i}", 1)
        b.result_served("vivo", 1)   # resta in uso: non si espelle
    assert len(b.take("vivo")["results"]) == MAX_TRACKED + 1
    assert b.take("altro0") is None


def test_scritture_da_due_thread_non_perdono_niente():
    """Mutazione ESEGUITA: `result_served` che rilegge-e-riassegna la lista
    (`entry["results"] = entry["results"] + [chars]`) con una
    `time.sleep(0)` in mezzo e SENZA lock -- rossa (scritture perse).
    Tolto il solo lock con l'`append` atomico del GIL la prova resta verde:
    cio' che protegge davvero e' il lock sulla sequenza leggi-scrivi."""
    b = BridgeLoads()

    def scrivi():
        for _ in range(500):
            b.result_served("T", 1)

    fili = [threading.Thread(target=scrivi) for _ in range(4)]
    for f in fili:
        f.start()
    for f in fili:
        f.join()
    assert len(b.take("T")["results"]) == 2000
