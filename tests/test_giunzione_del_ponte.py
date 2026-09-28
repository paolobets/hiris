"""La giunzione: la riga del ponte + cio' che /api/mcp ha annotato = turno e
giri nel registro. Spec «le misure complete» §4, la scrittura.
"""
from hiris.app.server import _registra_turno_ponte
from hiris.app.usage.bridge_loads import BridgeLoads
from hiris.app.usage.store import UsageStore


def _riga(**extra):
    riga = {"species": "chat", "channel": "ponte", "provider": "subscription",
            "model": "claude-opus-5-5", "duration_ms": 12000, "iterations": 2,
            "tools": ["search"], "outcome": "riuscito", "subject": None,
            "exchange_id": "T1",
            "composition": {"guide_chars": 7000, "core_chars": 7600,
                            "history_chars": 900},
            "exchanges": [
                {"message_id": "a", "input_tokens": 10, "output_tokens": None,
                 "cache_read_tokens": 17722, "cache_write_tokens": 11368,
                 "cache_ttl": "1h", "mcp_calls": 1},
                {"message_id": "b", "input_tokens": 8, "output_tokens": None,
                 "cache_read_tokens": 29090, "cache_write_tokens": 19510,
                 "cache_ttl": "1h", "mcp_calls": 0}],
            "output_tokens": 623, "list_cost_usd": 0.0695702}
    riga.update(extra)
    return riga


def test_turno_e_giri_finiscono_nel_registro_col_risultato_MCP(tmp_path):
    """Il turno e i suoi giri, con definizioni e risultati presi da cio' che
    /api/mcp ha annotato per quel `exchange_id`.

    Mutazione ESEGUITA: non chiamare `carichi.take` (`preso = None`) -- rossa
    (results 0 invece di 1500); ripristinata, verde."""
    archivio = UsageStore(str(tmp_path / "consumi.db"))
    carichi = BridgeLoads()
    carichi.tools_listed("T1", 45388, 16)
    carichi.result_served("T1", 1500)

    _registra_turno_ponte(archivio, carichi)(_riga())

    turno = archivio.turns()[0]
    assert turno["channel"] == "ponte" and turno["output_tokens"] == 623
    assert turno["list_cost_usd"] == 0.0695702
    giri = archivio.payloads(turno["id"])
    assert [g["results_chars"] for g in giri] == [0, 1500]
    assert giri[0]["cache_write_tokens"] == 11368
    assert [g["tools_chars"] for g in giri] == [45388, 0], (
        "le definizioni sul giro in cui tools/list e' stata servita")
    assert carichi.take("T1") is None, "il turno preso si dimentica"


def test_senza_archivio_dei_carichi_i_giri_si_scrivono_lo_stesso(tmp_path):
    """Senza `BridgeLoads` (il worker a processo separato) i giri nascono lo
    stesso, dai token dello stream e dalla composizione.

    Mutazione ESEGUITA: scrivere i giri solo `if carichi is not None` --
    rossa (0 giri invece di 2); ripristinata, verde."""
    archivio = UsageStore(str(tmp_path / "consumi.db"))
    _registra_turno_ponte(archivio)(_riga())
    giri = archivio.payloads(archivio.turns()[0]["id"])
    assert len(giri) == 2 and giri[0]["tools_chars"] == 0


def test_una_riga_VECCHIA_senza_le_chiavi_nuove_scrive_solo_il_turno(tmp_path):
    """La forma di prima (senza exchange_id/composition/exchanges) non deve
    rompere: e' la riga dei test esistenti e di un ponte non aggiornato.

    Mutazione ESEGUITA: `riga.pop("composition")` senza default -- rossa
    (KeyError); ripristinata, verde."""
    archivio = UsageStore(str(tmp_path / "consumi.db"))
    riga = _riga()
    for chiave in ("exchange_id", "composition", "exchanges", "output_tokens",
                   "list_cost_usd"):
        riga.pop(chiave)
    _registra_turno_ponte(archivio)(riga)
    assert len(archivio.turns()) == 1
    assert archivio.payloads(archivio.turns()[0]["id"]) == []


def test_un_giro_che_non_si_scrive_non_fa_cadere_il_turno(tmp_path):
    """La giunzione gira DENTRO il gancio di `runner._measure_turn`: se
    `log_payload` solleva, il turno del proprietario continua.

    Mutazione ESEGUITA: in `_measure_turn` sostituire `except Exception` con
    `except KeyError` -- rossa (RuntimeError esce); ripristinata, verde."""
    from hiris.app.agent import runner as ponte

    class _Rotto(UsageStore):
        def log_payload(self, *args, **kwargs):
            raise RuntimeError("disco pieno")

    archivio = _Rotto(str(tmp_path / "consumi.db"))
    e = ponte.StreamOccurrence()
    e.num_exchanges = 1
    e.exchanges = [_riga()["exchanges"][0]]
    ponte.set_turn_logger(_registra_turno_ponte(archivio, BridgeLoads()))
    try:
        ponte._measure_turn({"job_id": "j", "kind": "chat"}, duration_ms=1,
                            tools=[], occurrence=e, outcome="riuscito",
                            exchange_id="T9",
                            composition={"guide_chars": 1, "core_chars": 1,
                                         "history_chars": 1})
    finally:
        ponte.set_turn_logger(None)
    assert len(archivio.turns()) == 1, "il turno e' scritto prima dei giri"
