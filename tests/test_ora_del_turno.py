"""L'ora della casa sta nel messaggio del turno, non nel nucleo (D-51; Chiusura, 13/10/2026).

Il nucleo e' cio' che e' stabile. Con l'ora al minuto dentro, cambiava a ogni
turno, e con lui la cronologia che lo segue: la cache del prompt non poteva
riusare ne' l'uno ne' l'altra. Queste prove guardano cio' che arriva al
modello su ogni strada -- chat sincrona, chat sul ponte, promessa sulla
catena e sul ponte -- e cio' che resta in cronologia.
"""
import pytest

from conftest import SCADENZA_LONTANA
from hiris.app.agent import prompts
from hiris.app.api import handlers_chat
from hiris.app.llm_router import LLM_ROUTER_KEY
from hiris.app.steering import SPECIES, house_hour, with_hour
from tests._runner_finto import RunnerFinto
from tests.test_chat_briefing import _build_chat_client, _semina_casa


def test_l_ora_va_in_coda_al_messaggio_e_senza_ora_il_messaggio_resta():
    assert with_hour("ciao", "Adesso sono le 10:00.") == "ciao\n\nAdesso sono le 10:00."
    assert with_hour("ciao", "") == "ciao"


def test_senza_anagrafe_l_ora_si_dice_in_UTC_scritto():
    """Un turno senza archivio della casa non resta senza ora: la dice in
    UTC, e lo scrive (`briefing.now_line`)."""
    assert house_hour({}, now=0.0).endswith("(fuso UTC).")


@pytest.mark.asyncio
async def test_la_chat_sincrona_porta_l_ora_nel_messaggio_e_non_nel_contesto(
        aiohttp_client, tmp_path, monkeypatch):
    """Mutazione ESEGUITA il 13/10/2026: `user_message=message` senza l'ora
    -- rossa sulla prima asserzione."""
    scritti = []
    monkeypatch.setattr(handlers_chat, "append_messages",
                        lambda messaggi, *a, **kw: scritti.extend(messaggi))
    client, runner = await _build_chat_client(
        aiohttp_client, tmp_path, archivio_casa=_semina_casa(tmp_path))

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    kwargs = runner.ultima
    assert kwargs["user_message"].startswith("ciao\n\nAdesso sono le")
    assert "Adesso sono le" not in kwargs["context_str"]
    # In cronologia resta la frase di chi ha scritto, non l'ora del turno.
    assert [m["content"] for m in scritti] == ["ciao", "ok"]


@pytest.mark.asyncio
async def test_il_dispatcher_riceve_la_frase_senza_l_ora(
        aiohttp_client, tmp_path, monkeypatch):
    """La cronaca registra cio' che la persona ha scritto: l'ora va al modello,
    non alla `frase` del dispatcher (`_chain_chat_turn`). Chiesta dal
    revisore, giro 153 (N153-3).

    Mutazione ESEGUITA il 13/10/2026: `frase=with_hour(phrase, ...)` --
    rossa sulla prima asserzione."""
    vero = handlers_chat.create_tool_dispatcher
    frasi = []

    def _spia(app, *, frase, **altri):
        frasi.append(frase)
        return vero(app, frase=frase, **altri)

    monkeypatch.setattr(handlers_chat, "create_tool_dispatcher", _spia)
    client, runner = await _build_chat_client(
        aiohttp_client, tmp_path, archivio_casa=_semina_casa(tmp_path))

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200
    assert frasi == ["ciao"]
    assert runner.ultima["user_message"].startswith("ciao\n\nAdesso sono le")


def test_il_ponte_mette_l_ora_dopo_la_conversazione():
    """Mutazione ESEGUITA il 13/10/2026: `build_chat_messages` che ignora
    `hour` -- rossa."""
    ora = "Adesso sono le 21:01 del 13/10/2026 (fuso Europe/Rome)."
    system, user = prompts.build_chat_messages(
        "Sei HIRIS.", [{"role": "user", "content": "che ore sono"}],
        contesto="Cucina.", active_tools=SPECIES["chat"].tools_for_turn(),
        hour=ora)
    assert ora not in system
    assert user.index("Utente: che ore sono") < user.index(ora)


@pytest.mark.asyncio
async def test_la_promessa_sulla_catena_porta_l_ora_nella_domanda():
    from hiris.app.keeper.exchange import interpreta_promise

    async def _conclude(_runner, **kwargs):
        await kwargs["dispatcher"].dispatch(
            "conclude", {"avvisare": False, "testo": "niente"})

    modello = RunnerFinto(turno=_conclude)
    await interpreta_promise({LLM_ROUTER_KEY: modello},
                             {"id": "p1", "frase": "dimmi", "domanda": "guarda",
                              "istantanea": []})
    assert "\n\nAdesso sono le" in modello.ultima["user_message"]
    assert "Adesso sono le" not in modello.ultima["context_str"]


def test_la_promessa_sul_ponte_porta_l_ora_nel_job(monkeypatch):
    from hiris.app.keeper import exchange

    accodati = []
    monkeypatch.setattr(exchange, "enqueue_turn",
                        lambda app, species, cols, context, **kw:
                        accodati.append(context) or ("j1", 5))
    exchange._enqueue_to_bridge({}, {"id": "p1", "frase": "dimmi", "domanda": "guarda"})
    assert accodati[0]["adesso"].startswith("Adesso sono le")
    assert "Adesso sono le" not in accodati[0]["contesto"]


def test_il_lavoratore_del_ponte_passa_l_ora_del_job_alla_CLI():
    """La riga di `agent/runner._reason_chat` che legge `adesso` dal job:
    senza, il ponte resterebbe senza ora (la catena la riceve da chi la
    chiama).

    Mutazione ESEGUITA il 13/10/2026: tolta quella riga -- rossa."""
    from unittest.mock import patch

    from hiris.app.agent import runner
    from tests.test_bridge_receives_briefing import _Proc

    ora = "Adesso sono le 21:01 del 13/10/2026 (fuso Europe/Rome)."
    catturato = {}

    def _fake_run(argv, *a, **k):
        catturato["user"] = k.get("input")
        return _Proc()

    job = {"kind": "chat", "deadline_ts": SCADENZA_LONTANA, "job_id": "job-ora",
           "context": {"model": "sonnet", "history": [{"role": "user", "content": "ciao"}],
                       "system_prompt": "Sei HIRIS.", "contesto": "Cucina.",
                       "adesso": ora}}
    with patch.object(runner.subprocess, "run", _fake_run):
        runner._reason_chat(job, "live")
    assert ora in catturato["user"]
