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
