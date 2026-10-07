"""Le chiamate di strumento della stessa risposta: le letture insieme, le
scritture una alla volta (Tappa 7, T10; S-12, decisione D15a).

Partivano tutte in fila su entrambi i runner -- otto letture erano otto
attese -- mentre il prompt (`BASE_TOOL_RULES`) insegna al modello a chiederle
in parallelo. Una scrittura invece resta sola: partita insieme a un'altra
potrebbe arrivare in ordine diverso da come il modello l'ha chiesta.

Cos'e' una lettura lo dice la tabella degli strumenti (`Tool.read_only`):
le prove chiedono i nomi a lei, non li ricopiano. I due runner si provano con
la stessa finta, perche' la regola e' una (`claude_runner.dispatch_calls`).
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import ClaudeRunner
from hiris.app.home_space.tools import TOOLS, reads_only

READS = [tool.name for tool in TOOLS if tool.read_only]
WRITES = [tool.name for tool in TOOLS if not tool.read_only]


class _Dispatcher:
    """Conta quante chiamate sono in volo insieme, e chi era in volo quando
    e' partita una scrittura. Le letture chieste prima finiscono DOPO
    (`ritardo` decrescente): e' il caso in cui l'ordine dei risultati
    potrebbe rovesciarsi."""

    def __init__(self, calls: int) -> None:
        self.in_flight = 0
        self.most = 0
        self.crowded_writes = []
        self._delays = iter(range(calls, 0, -1))

    async def dispatch(self, name, arguments):
        if not reads_only(name) and self.in_flight:
            self.crowded_writes.append(name)
        self.in_flight += 1
        self.most = max(self.most, self.in_flight)
        for _ in range(next(self._delays)):
            await asyncio.sleep(0)
        if not reads_only(name) and self.in_flight > 1:
            self.crowded_writes.append(name)
        self.in_flight -= 1
        return {"chiamata": arguments["n"]}


def _claude(calls):
    """Un `ClaudeRunner` la cui prima risposta chiede `calls`, la seconda chiude."""
    runner = ClaudeRunner(api_key="sk-test")
    uses = [MagicMock(type="tool_use", id=f"u{n}", input={"n": n}) for n in range(len(calls))]
    for block, name in zip(uses, calls, strict=True):
        block.name = name
    first = MagicMock(stop_reason="tool_use", content=uses)
    last = MagicMock(stop_reason="end_turn", content=[MagicMock(type="text", text="ok")])
    for response in (first, last):
        response.usage = MagicMock(input_tokens=1, output_tokens=1,
                                   cache_creation_input_tokens=0, cache_read_input_tokens=0)
    runner._client.messages.create = AsyncMock(side_effect=[first, last])

    def results():
        sent = runner._client.messages.create.call_args.kwargs["messages"][-1]["content"]
        return [json.loads(block["content"])["chiamata"] for block in sent]
    return runner, results


def _openai(calls):
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="sk-test")
    tool_calls = []
    for n, name in enumerate(calls):
        call = MagicMock(id=f"c{n}")
        call.function.name = name
        call.function.arguments = json.dumps({"n": n})
        tool_calls.append(call)
    first = MagicMock(choices=[MagicMock(
        finish_reason="tool_calls", message=MagicMock(content=None, tool_calls=tool_calls))])
    last = MagicMock(choices=[MagicMock(
        finish_reason="stop", message=MagicMock(content="ok", tool_calls=None))])
    for response in (first, last):
        response.usage = MagicMock(prompt_tokens=1, completion_tokens=1)
    runner._client.chat.completions.create = AsyncMock(side_effect=[first, last])

    def results():
        sent = runner._client.chat.completions.create.call_args.kwargs["messages"]
        return [json.loads(m["content"])["chiamata"] for m in sent if m["role"] == "tool"]
    return runner, results


async def _turn(make, calls):
    runner, results = make(calls)
    dispatcher = _Dispatcher(len(calls))
    tools = [tool.definition for tool in TOOLS if tool.name in set(calls)]
    await runner.chat("ciao", tools=tools, dispatcher=dispatcher)
    return runner, dispatcher, results()


RUNNERS = pytest.mark.parametrize("make", [_claude, _openai], ids=["claude", "catena"])


def test_la_tabella_dichiara_letture_e_scritture():
    """La prova della derivazione: se la tabella smettesse di dichiarare le
    letture, le prove qui sotto guarderebbero un insieme vuoto e direbbero di
    si'. E una lettura non puo' chiedere `comandare`: chi comanda la casa
    scrive.

    Mutazione ESEGUITA (07/10/2026): `read_only=True` anche su `execute` --
    rossa (`['execute']`). Ripristinata, `git diff` senza la mutazione."""
    assert len(READS) >= 3, READS
    assert len(WRITES) >= 3, WRITES
    commanding = [tool.name for tool in TOOLS if tool.read_only
                  and any(p.gesture == "comandare" for p in tool.permissions)]
    assert commanding == [], commanding


def test_gli_elenchi_di_sola_lettura_dei_mestieri_sono_letture():
    """Gli elenchi d'AMMISSIONE degli attori -- cio' che l'analista e la
    promessa possono chiamare -- si dicono «sola lettura»: devono esserlo
    anche per la tabella, o la parola e il fatto divergerebbero."""
    from hiris.app.keeper.exchange import SOLA_LETTURA
    from hiris.app.mind.analyst_turn import READERS

    assert set(READERS) <= set(READS), set(READERS) - set(READS)
    assert set(SOLA_LETTURA) <= set(READS), set(SOLA_LETTURA) - set(READS)


def test_un_nome_che_la_tabella_non_conosce_e_una_scrittura():
    """Chiude per difetto: `compute` dell'analista, `conclude` della
    promessa, un refuso del modello partono da soli."""
    assert not reads_only("compute")
    assert not reads_only("un-nome-inventato")


@pytest.mark.asyncio
@RUNNERS
async def test_le_letture_della_stessa_risposta_partono_insieme(make):
    """Mutazione ESEGUITA (07/10/2026): in `dispatch_calls`, un `await` per
    chiamata dentro un `for` (la fila di prima) -- rossa su tutti e due i
    runner (`assert 1 == 3`). Ripristinata, `git diff` senza la mutazione."""
    calls = READS[:3]
    _, dispatcher, results = await _turn(make, calls)
    assert dispatcher.most == len(calls)
    assert results == list(range(len(calls))), "l'ordine delle chiamate si e' perso"


@pytest.mark.asyncio
@RUNNERS
async def test_una_scrittura_parte_da_sola_e_nel_suo_posto(make):
    """Due letture, una scrittura, due letture: le letture ai lati partono a
    coppie, la scrittura con niente in volo, e i risultati tornano al modello
    nell'ordine in cui li ha chiesti -- anche se le letture chieste prima
    finiscono dopo.

    Mutazione ESEGUITA (07/10/2026): in `dispatch_calls`, tutte le chiamate
    in un solo `asyncio.gather` -- rossa (la scrittura partita in mezzo alle
    letture). Ripristinata, `git diff` senza la mutazione."""
    calls = [READS[0], READS[1], WRITES[0], READS[2], READS[0]]
    _, dispatcher, results = await _turn(make, calls)
    assert dispatcher.crowded_writes == []
    assert dispatcher.most == 2
    assert results == list(range(len(calls)))


@pytest.mark.asyncio
@RUNNERS
async def test_le_chiamate_si_registrano_nell_ordine_del_modello(make):
    calls = [READS[1], READS[0], WRITES[0]]
    runner, _, _ = await _turn(make, calls)
    assert [c["tool"] for c in runner.last_tool_calls] == calls
