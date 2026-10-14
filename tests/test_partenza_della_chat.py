"""La chat parte da `steering.start`, come ogni altro turno (D-06; Chiusura, 13/10/2026).

Giri, promessa, Rifalla, proponente e automatizza chiedevano gia' a
`steering.start` chi risponde; la chat lo scriveva a mano, con
`who_answers`, `chain_runner` e `declare_downgrade`, nella rotta e nel
ripiego a scadenza. Una delle copie dichiarava il ripiego anche quando non
c'era nessun runner a cui scendere: una riga nella pagina dei consumi per
un turno che nessuno ha pagato.
"""
import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from hiris.app.claude_runner import CLAUDE_RUNNER_KEY
from hiris.app.llm_router import LLM_ROUTER_KEY
from hiris.app.steering import BRIDGE_ACTIVE_KEY, start
from hiris.app.usage.store import USAGE_KEY
from tests.test_chat_subscription_path import _make_app

_HANDLERS = (Path(__file__).resolve().parents[1] / "hiris" / "app" / "api"
             / "handlers_chat.py")


def test_la_chat_non_chiede_a_mano_chi_risponde():
    """Mutazione ESEGUITA il 13/10/2026: il ripiego a scadenza che torna a
    chiamare `declare_downgrade` da se' -- rossa."""
    tree = ast.parse(_HANDLERS.read_text(encoding="utf-8"))
    called = {getattr(n.func, "id", getattr(n.func, "attr", None))
              for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not called & {"who_answers", "chain_runner", "declare_downgrade"}
    assert "start" in called


def test_un_motivo_gia_noto_non_chiede_a_who_answers():
    """La scadenza del ponte e' un ripiego gia' avvenuto: la strada e' la
    catena anche col ponte acceso e il piano che, adesso, potrebbe
    rispondere."""
    usage = MagicMock()
    app = {LLM_ROUTER_KEY: object(), USAGE_KEY: usage, BRIDGE_ACTIVE_KEY: True}
    route, downgrade, runner = start(app, "chat", downgrade="scadenza")
    assert (route, downgrade) == ("catena", "scadenza")
    assert runner is app[LLM_ROUTER_KEY]
    usage.log_fallback.assert_called_once()
    assert usage.log_fallback.call_args.args[:2] == ("chat", "scadenza")


@pytest.mark.asyncio
async def test_senza_runner_il_ripiego_non_si_dichiara(tmp_path, monkeypatch):
    """Il piano non ha il token e la catena e' vuota: la chat risponde 503, e
    nessun ripiego entra nella pagina dei consumi.

    Rossa sul codice di prima: `declare_downgrade` partiva prima di sapere
    se c'era un runner."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    app, _q, _runner, _, _ = _make_app(tmp_path, ponte_attivo=True, with_queue=True)
    app[LLM_ROUTER_KEY] = None
    app[CLAUDE_RUNNER_KEY] = None
    app[USAGE_KEY] = usage = MagicMock()
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 503
    usage.log_fallback.assert_not_called()
