"""Il ponte serve anche i risvegli: `kind="promessa"`.

Fetta «le promesse seguono la catena» (22/08/2026). Un turno di promessa e' un
TURNO -- stessa sonda degli strumenti, stesso ritentativo, stessa
`verifica_init`, stessa redazione dei segreti. Cio' che cambia e' il contenuto,
e il contenuto arriva tutto dal contesto del job.

Questi test tengono ferme le due cose che rendono quel riuso corretto invece
che comodo: l'intestazione che dice al `/api/mcp` quale promessa si sta
mantenendo, e il fatto che un `kind` di promessa non finisca nel ramo dei kind
sconosciuti -- dove la decisione tornata sarebbe VUOTA e la promessa morirebbe
senza che nessuno sappia perche'.
"""
from __future__ import annotations

import json

from hiris.app.agent.runner import config_mcp


def _intestazioni(conf: str) -> dict:
    return json.loads(conf)["mcpServers"]["hiris"]["headers"]


def test_un_turno_di_promessa_porta_l_intestazione_della_promessa():
    conf = config_mcp("http://127.0.0.1:8099", "tok", "turno-1", "p1")
    assert _intestazioni(conf)["X-HIRIS-Promessa"] == "p1"


def test_un_turno_di_chat_NON_porta_l_intestazione():
    """La chat non mantiene nessuna promessa: un'intestazione sempre presente
    con valore vuoto sarebbe un campo che chi legge deve interpretare, invece
    di un'assenza che parla da se'."""
    conf = config_mcp("http://127.0.0.1:8099", "tok", "turno-1")
    assert "X-HIRIS-Promessa" not in _intestazioni(conf)


def test_il_token_resta_dov_era_anche_con_la_promessa_accanto():
    """L'intestazione nuova non deve spostare ne' indebolire le due che
    tengono viva la rotta (token interno e X-Requested-With)."""
    intestazioni = _intestazioni(config_mcp("http://127.0.0.1:8099", "tok", "t", "p1"))
    assert intestazioni["X-HIRIS-Internal-Token"] == "tok"
    assert intestazioni["X-Requested-With"] == "hiris-mcp"


def test_un_kind_promessa_NON_finisce_fra_i_kind_sconosciuti(caplog):
    """Il ramo dei kind sconosciuti restituisce una decisione VUOTA: una
    promessa che ci finisse morirebbe senza che nessuno sappia perche'. Il log
    di quel ramo resta -- dichiara un silenzio che serve ancora, per i job di
    un'installazione precedente -- ma non deve piu' vedere le promesse."""
    from hiris.app.agent import runner as ponte

    esito = ponte.reason(
        {"kind": "promessa", "job_id": "j1",
         "context": {"promessa_id": "p1", "history": [], "system_prompt": ""}},
        "mock")

    assert "job non-chat in coda" not in caplog.text
    assert esito != {}, "una decisione vuota e' cio' che il ramo sconosciuto da'"


def test_un_kind_davvero_sconosciuto_resta_dichiarato(caplog):
    """L'altra meta': il ramo non si cancella allargandolo."""
    import logging

    from hiris.app.agent import runner as ponte

    with caplog.at_level(logging.WARNING):
        esito = ponte.reason({"kind": "olistico", "job_id": "j2", "context": {}}, "mock")

    assert esito == {}
    assert "job non-chat in coda" in caplog.text


# --- il catalogo del turno vale su TUTTI e tre i punti ------------------------
#
# Difetto trovato dalla VERIFICA LIVE della 3.10.0, non dalla suite: il ponte
# ha servito il risveglio (l'instradamento era giusto) ma il turno ha
# dichiarato «non ho potuto usare gli strumenti» e ha risposto a parole.
#
# La fetta aveva reso il catalogo PER TURNO nella rotta MCP, e lasciato tre
# punti ancorati a quello della chat: `--allowedTools`, la sonda, e la verifica
# dell'init. Un turno di promessa riceve 5 strumenti (4 lettori + `concludi`),
# la verifica ne pretendeva 9, li dichiarava mancanti, e il ritentativo
# ripartiva senza strumenti. Il modello non aveva `concludi`, quindi non aveva
# nessun modo di finire.


def test_i_nomi_attesi_seguono_il_catalogo_del_turno():
    from hiris.app.agent.runner import mcp_names

    chat = set(mcp_names())
    promessa = set(mcp_names(by_promise=True))

    assert any(n.endswith("__conclude") for n in promessa), (
        "senza «conclude» fra i nomi permessi il turno non ha modo di finire")
    assert not any(n.endswith("__execute") for n in promessa), (
        "un turno che gira senza nessuno davanti non tocca la casa")
    assert any(n.endswith("__execute") for n in chat), "la chat non cambia"
    assert any(n.endswith("__view") for n in promessa), "i lettori restano"


def test_la_verifica_dell_init_non_pretende_gli_strumenti_della_chat():
    """Il punto esatto in cui il turno moriva: 9 attesi contro 5 risolti."""
    from hiris.app.agent.runner import StreamOccurrence, mcp_names, verify_init

    esito = StreamOccurrence()
    esito.init = {
        "mcp_servers": [{"name": "hiris", "status": "connected"}],
        "tools": list(mcp_names(by_promise=True)),
    }

    ok, motivo = verify_init(esito, by_promise=True)
    assert ok is True, motivo

    ok_chat, _motivo_chat = verify_init(esito, by_promise=False)
    n_promessa = len(esito.init["tools"])
    assert ok_chat is False, (
        f"col catalogo della chat quegli stessi {n_promessa} strumenti del turno "
        "di promessa risultano incompleti: e' il difetto che la verifica live ha "
        "colto")


def test_l_argv_permette_concludi_su_un_turno_di_promessa():
    from hiris.app.agent.runner import _chat_claude_args

    argv = _chat_claude_args("sys", "user", "sonnet", active_tools=True,
                             mcp_config="{}", by_promise=True)
    permessi = argv[argv.index("--allowedTools") + 1]
    assert "__conclude" in permessi
    assert "__execute" not in permessi
