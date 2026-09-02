"""Il modello che gira sul ponte, e DA DOVE VIENE.

Fino alla 3.1.0 veniva composto a ogni turno da `provider_models["claude"]`:
`cli_model(resolve_model("auto", "chat", provider_models["claude"]))`, in
`handlers_chat._enqueue_chat_job` e -- identico -- in
`handlers_models._models_in_use`. Due implementazioni dello stesso calcolo, e
un campo solo per due economie opposte: a consumo si sceglie il modello
frugale, nel piano il modello non costa di piu'. L'impianto del proprietario,
misurato il 15 agosto 2026, girava sul piano con `haiku`.

Dalla fetta «il modello del piano» il ponte LEGGE `ponte.modello`, un campo
suo. Questo file inchioda l'INDIPENDENZA -- che e' la cosa che il proprietario
non poteva esprimere.

I test [1]-[4] su `cli_model` restano validi parola per parola: la funzione
non e' sparita, ha cambiato mestiere. Da traduttore chiamato a ogni turno e'
diventata il VALIDATORE del campo (`handlers_models._clean_subscription_model`),
e il suo silenzio dichiarato -- il `log.warning` su un modello non-Anthropic --
serve adesso a chi scrive a mano `/data/models_config.json`. Il campo, la sua
pulizia e la sua semina vivono in `tests/test_subscription_model.py`.
"""
import logging

import pytest

from hiris.app.agent import runner
from hiris.app.claude_runner import resolve_model


@pytest.fixture(autouse=True)
def il_piano_puo_rispondere(monkeypatch):
    """Il token del piano: senza, dal Task 14 il turno NON viene accodato.

    «Ponte acceso senza token» ha smesso di essere uno stato in cui il
    messaggio muore in coda: e' un RIPIEGO, e il turno scende alla catena nella
    stessa richiesta. Un'app di prova col ponte acceso e senza token non
    descrive piu' il ponte, quindi ogni test di questo file che parla del job
    accodato sarebbe diventato un test su un'altra cosa."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token-di-prova")



# ---------------------------------------------------------------------------
# [1]-[4]: modello_cli (+ resolve_model a monte)
# ---------------------------------------------------------------------------

def test_auto_senza_models_config_da_sonnet():
    # "auto" senza un default di provider (nessun `models_config` salvato,
    # o provider_models["claude"] vuoto) risolve via AUTO_MODEL_MAP["chat"]
    # -> "claude-sonnet-4-6", che modello_cli traduce nell'alias "sonnet".
    modello_risolto = resolve_model("auto", "chat", "")
    assert runner.cli_model(modello_risolto) == "sonnet"


def test_modello_opus_esplicito_da_opus():
    modello_risolto = resolve_model("claude-opus-4-7", "chat", "")
    assert modello_risolto == "claude-opus-4-7"  # resolve_model non tocca un modello non "auto"
    assert runner.cli_model(modello_risolto) == "opus"


def test_modello_haiku_esplicito_da_haiku():
    modello_risolto = resolve_model("claude-haiku-4-5-20251001", "chat", "")
    assert runner.cli_model(modello_risolto) == "haiku"


def test_modello_non_anthropic_ricade_su_sonnet_e_lo_dichiara_nel_log(caplog):
    # gpt-4o: un modello configurabile per la chat (provider_models ha anche
    # "openai"/"openrouter", handlers_models.py) che la CLI dell'abbonamento
    # non puo' MAI parlare -- passarlo a `claude --model` darebbe rc!=0 ad
    # ogni turno. Il ripiego su "sonnet" non e' silenzioso: un log.warning
    # nomina il valore configurato.
    modello_risolto = resolve_model("gpt-4o", "chat", "")
    assert modello_risolto == "gpt-4o"

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        esito = runner.cli_model(modello_risolto)

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
    from hiris.app.chat_settings import ChatSettings
    from hiris.app.chat_store import close_all_stores
    from hiris.app.reasoning.queue import ReasoningQueue

    close_all_stores()
    try:
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir, exist_ok=True)

        # La SORGENTE e' cambiata due volte. Prima `ChatSettings(model=)`,
        # che scavalcava la catena; poi `provider_models["claude"]`, cioe' il
        # modello di un ALTRO provider; adesso `ponte.modello`, che e' del
        # piano e di nessun altro.
        impostazioni = ChatSettings(
            name="test-agent", system_prompt="Sei HIRIS.",
        )

        app = web.Application()
        app["impostazioni_chat"] = impostazioni
        app["data_dir"] = data_dir
        app["ponte_attivo"] = True
        q = ReasoningQueue(str(tmp_path / "reasoning.db"))
        app["reasoning_queue"] = q
        # LA FINTA E' SCOMODA DI PROPOSITO: il piano su `opus`, Claude API su
        # haiku. Con la regola vecchia il job porterebbe `haiku`; con quella
        # nuova porta `opus`. Metterli uguali renderebbe questo test incapace
        # di distinguere le due implementazioni -- cioe' incapace di fallire,
        # che e' il difetto n.1 di questo prodotto.
        app["models_config"] = {
            "provider_models": {"claude": "claude-haiku-4-5-20251001"},
            "ponte": {"modello": "opus"},
        }
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


# ---------------------------------------------------------------------------
# [6]-[8]: l'indipendenza, in tutte e due le direzioni
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("alias", ["haiku", "sonnet", "opus"])
def test_il_piano_mostra_il_campo_e_non_una_composizione(alias):
    """Claude API su haiku, il piano su `alias`: la riga del piano dice
    `alias`. Con la regola vecchia direbbe sempre `haiku`."""
    from hiris.app.api import handlers_models
    modelli = handlers_models._models_in_use(
        {"claude": "claude-haiku-4-5-20251001", "openai": "", "openrouter": ""},
        "", alias)
    assert modelli["subscription"] == alias


def test_cambiare_il_modello_di_claude_api_non_tocca_il_piano():
    """L'affermazione centrale della fetta, provata per differenza: due letture
    che differiscono SOLO nel modello di Claude API danno lo stesso piano."""
    from hiris.app.api import handlers_models
    prima = {"claude": "claude-haiku-4-5-20251001", "openai": "", "openrouter": ""}
    dopo = {"claude": "claude-opus-4-7", "openai": "", "openrouter": ""}
    assert handlers_models._models_in_use(prima, "", "sonnet")["subscription"] == "sonnet"
    assert handlers_models._models_in_use(dopo, "", "sonnet")["subscription"] == "sonnet"


def test_e_cambiare_il_piano_non_tocca_claude_api():
    """L'altra meta': due valori indipendenti, non uno rinominato. Senza questo
    test, un'implementazione che facesse scrivere al piano il campo di Claude
    API passerebbe tutto il resto del file."""
    from hiris.app.api import handlers_models
    pm = {"claude": "claude-opus-4-7", "openai": "", "openrouter": ""}
    assert handlers_models._models_in_use(pm, "", "haiku")["claude"] == "claude-opus-4-7"
    assert handlers_models._models_in_use(pm, "", "opus")["claude"] == "claude-opus-4-7"
