"""fetta "il ponte riceve il nucleo" (parita' A, Task 4): il modello del
ponte e' quello scelto per la chat, non piu' `HIRIS_AGENT_CHAT_MODEL` --
quella env non era mai esportata da `run.sh` (censimento -> "Variabili
d'ambiente lette e mai esportate", voce su `agent/runner.py`, dove
`_reason_chat` la leggeva: oggi la voce non c'e' piu' perche' non c'e' piu'
la lettura): in produzione era SEMPRE "sonnet", qualunque cosa l'utente
scegliesse per la chat.

`agent.runner.modello_cli(modello_risolto)` traduce il modello GIA' RISOLTO
(via `claude_runner.resolve_model`, che puo' restituire un modello di
QUALUNQUE provider configurato in `provider_models`) in un alias della CLI
`claude` -- l'unica cosa con cui il ponte parla. Un modello non-Anthropic
ricade su "sonnet" con un log esplicito (silenzio dichiarato (2) della
fetta): mai un rc!=0 muto ad ogni turno.

I test [1]-[4] coprono `modello_cli` (piu' `resolve_model` a monte, per
mostrare la stessa composizione che fa `handlers_chat._enqueue_chat_job`).
Il test [5] e' end-to-end: il job accodato dal ramo async porta il modello
gia' risolto e tradotto, e `_chat_claude_args` lo mette in argv dopo
`--model` esattamente come per il ramo sincrono.
"""
import logging

import pytest

from hiris.app.agent import runner
from hiris.app.claude_runner import resolve_model


# ---------------------------------------------------------------------------
# [1]-[4]: modello_cli (+ resolve_model a monte)
# ---------------------------------------------------------------------------

def test_auto_senza_models_config_da_sonnet():
    # "auto" senza un default di provider (nessun `models_config` salvato,
    # o provider_models["claude"] vuoto) risolve via AUTO_MODEL_MAP["chat"]
    # -> "claude-sonnet-4-6", che modello_cli traduce nell'alias "sonnet".
    modello_risolto = resolve_model("auto", "chat", "")
    assert runner.modello_cli(modello_risolto) == "sonnet"


def test_modello_opus_esplicito_da_opus():
    modello_risolto = resolve_model("claude-opus-4-7", "chat", "")
    assert modello_risolto == "claude-opus-4-7"  # resolve_model non tocca un modello non "auto"
    assert runner.modello_cli(modello_risolto) == "opus"


def test_modello_haiku_esplicito_da_haiku():
    modello_risolto = resolve_model("claude-haiku-4-5-20251001", "chat", "")
    assert runner.modello_cli(modello_risolto) == "haiku"


def test_modello_non_anthropic_ricade_su_sonnet_e_lo_dichiara_nel_log(caplog):
    # gpt-4o: un modello configurabile per la chat (provider_models ha anche
    # "openai"/"openrouter", handlers_models.py) che la CLI dell'abbonamento
    # non puo' MAI parlare -- passarlo a `claude --model` darebbe rc!=0 ad
    # ogni turno. Il ripiego su "sonnet" non e' silenzioso: un log.warning
    # nomina il valore configurato.
    modello_risolto = resolve_model("gpt-4o", "chat", "")
    assert modello_risolto == "gpt-4o"

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        esito = runner.modello_cli(modello_risolto)

    assert esito == "sonnet"
    rec = [r for r in caplog.records if r.name == "hiris.agent"]
    assert len(rec) == 1, "il ripiego deve essere dichiarato una volta sola"
    assert rec[0].levelno == logging.WARNING
    messaggio = rec[0].getMessage()
    assert "gpt-4o" in messaggio
    assert "sonnet" in messaggio


# ---------------------------------------------------------------------------
# [5]: end-to-end -- il job accodato porta il modello risolto, e
# _chat_claude_args lo mette in argv dopo --model
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_accodato_porta_il_modello_risolto_in_argv(tmp_path):
    import os

    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from hiris.app.api.handlers_chat import handle_chat
    from hiris.app.chat_store import close_all_stores
    from hiris.app.impostazioni_chat import ImpostazioniChat
    from hiris.app.reasoning.queue import ReasoningQueue

    close_all_stores()
    try:
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir, exist_ok=True)

        # Un modello Anthropic esplicito (non "auto"): niente risoluzione via
        # AUTO_MODEL_MAP, cosi' il test dimostra che il valore che ARRIVA da
        # `ImpostazioniChat` e' quello che finisce, tradotto, in argv.
        impostazioni = ImpostazioniChat(
            nome="test-agent", system_prompt="Sei HIRIS.",
            model="claude-opus-4-7",
        )

        app = web.Application()
        app["impostazioni_chat"] = impostazioni
        app["data_dir"] = data_dir
        app["chat_via_subscription"] = True
        q = ReasoningQueue(str(tmp_path / "reasoning.db"))
        app["reasoning_queue"] = q
        # nessun app["models_config"]: come una install dove non e' mai
        # stato salvato -- il codice deve degradare a provider_models
        # vuoto, non sollevare.
        app.router.add_post("/api/chat", handle_chat)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat", json={"message": "ciao"})
            assert resp.status == 202
            body = await resp.json()

        job = q.get(body["job_id"])
        assert job["context"]["model"] == "opus"

        argv = runner._chat_claude_args("SYS", "USER", job["context"]["model"])
        assert argv[argv.index("--model") + 1] == "opus"
    finally:
        close_all_stores()
