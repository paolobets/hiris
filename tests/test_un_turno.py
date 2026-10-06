"""Un turno verso un modello passa da un posto solo (Tappa 6, Task 7; R4, R18).

**R4.** Fino al 06/10/2026 ogni mestiere chiamava `runner.chat` a mano, a
modo suo: misurato su `eea18be`, **otto** chiamate in sei file (piano della
Tappa 6, «Misurato prima di disegnare»). Da qui la chiamata vive in
`steering.chain_turn`, e una prova la cerca nel sorgente: chiede al codice,
non a una lista.

**R18.** Le regole sugli strumenti andavano a ogni turno della catena,
anche a chi non ha strumenti: 6.044 caratteri all'analista, all'attuatore,
all'osservatore e alle ricette, che non possono usarne nessuno. Ora il
compositore (`steering.compose_base`) le da' solo a chi ha strumenti, e solo
quelle degli strumenti che ha: la promessa non legge di `execute`.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app import steering
from hiris.app.claude_runner import BASE_TOOL_RULES, ClaudeRunner
from hiris.app.home_space.tools import TOOLS

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"


def _chat_calls() -> list[tuple[str, int]]:
    """Le chiamate `<qualcosa>.chat(...)` del prodotto, **chieste al
    sorgente**. Si saltano quelle DENTRO un metodo `chat`: e' il router che
    passa ai backend la chiamata che gli e' gia' arrivata dal modulo dei
    turni, non un turno nuovo."""
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forwarding = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "chat":
                forwarding.update(id(n) for n in ast.walk(node))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "chat"
                    and id(node) not in forwarding):
                found.append((path.relative_to(APP).as_posix(), node.lineno))
    return found


def test_nessun_runner_chat_fuori_dal_modulo_dei_turni():
    """Rossa su `eea18be` con otto chiamate, nominate per file e riga.

    **La prova della derivazione**: la ricerca deve trovare la chiamata del
    modulo dei turni. Se non trova nemmeno quella, e' rotta, e la parte
    «fuori» sarebbe vuota per la ragione sbagliata.

    Mutazione ESEGUITA il 06/10/2026: un `runner.chat` aggiunto in fondo a
    `server.py` -- rossa, col file e la riga."""
    calls = _chat_calls()
    inside = [c for c in calls if c[0] == "steering.py"]
    outside = [f"{f}:{n}" for f, n in calls if f != "steering.py"]
    assert inside, f"la ricerca delle chiamate e' rotta: {calls}"
    assert outside == [], f"turni che non passano dal modulo dei turni: {outside}"


# -- R18: le regole sugli strumenti, solo a chi ne ha ---------------------------

#: Le righe delle regole, chieste al testo: abbastanza lunghe da non essere
#: un titolo o una riga vuota.
_RULE_LINES = [r.strip() for r in BASE_TOOL_RULES.split("\n") if len(r.strip()) > 20]

#: I nomi degli strumenti, chiesti alla tabella.
_TOOL_NAMES = [t.definition["name"] for t in TOOLS]


def _system_text(system) -> str:
    if isinstance(system, str):
        return system
    return "\n".join(b.get("text", "") for b in system if b.get("type") == "text")


async def _sent_system(tools) -> str:
    """Il prompt di sistema che la catena spedisce DAVVERO all'API."""
    runner = ClaudeRunner(api_key="test-key")
    message = MagicMock()
    message.stop_reason = "end_turn"
    message.content = [MagicMock(type="text", text="ok")]
    api = MagicMock()
    api.messages.create = AsyncMock(return_value=message)
    runner._client = api
    await runner.chat("ciao", system_prompt="Sei il mestiere.", max_tokens=64,
                      tools=tools)
    return _system_text(api.messages.create.call_args.kwargs["system"])


def test_le_righe_delle_regole_si_trovano():
    """Derivazione: se le righe fossero poche, le prove qui sotto
    guarderebbero il niente."""
    assert len(_RULE_LINES) >= 20, _RULE_LINES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "species", sorted(n for n, s in steering.SPECIES.items() if s.self_contained))
async def test_un_mestiere_senza_strumenti_riceve_zero_caratteri_di_regole(species):
    """Rossa su `eea18be`: la catena emetteva `BASE_SYSTEM_PROMPT` intero a
    ogni turno, 6.044 caratteri di regole per un turno che non ha strumenti.

    I mestieri si chiedono alle dichiarazioni (`steering.SPECIES`), non si
    scrivono qui.

    Mutazione ESEGUITA il 06/10/2026: il compositore che da' tutte le regole a
    tutti -- rossa per i quattro mestieri senza strumenti e per la promessa."""
    assert steering.SPECIES[species].tools_for_turn() == ()
    system = await _sent_system(None)
    present = [r for r in _RULE_LINES if r in system]
    assert present == [], f"«{species}» riceve {sum(map(len, present))} caratteri di regole"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "species", sorted(n for n, s in steering.SPECIES.items() if not s.self_contained))
async def test_le_regole_parlano_solo_degli_strumenti_del_mestiere(species):
    """Rossa su `eea18be` per la promessa: riceveva le regole di `execute`,
    `remember`, `propose` e `confirm`, che non puo' chiamare. Ogni riga di
    regola che arriva a un mestiere nomina solo strumenti che quel mestiere
    ha."""
    from hiris.app.home_space.tools import KNOWLEDGE_TOOLS

    names = steering.SPECIES[species].tools_for_turn()
    tools = [d for d in KNOWLEDGE_TOOLS if d["name"] in names]
    system = await _sent_system(tools)
    for line in (r for r in _RULE_LINES if r in system):
        named = {n for n in _TOOL_NAMES if re.search(rf"\b{n}\b", line)}
        assert named <= set(names), (species, sorted(named - set(names)), line[:80])
    # E qualcosa arriva: un mestiere con strumenti ha le sue regole.
    assert any(r in system for r in _RULE_LINES), species


@pytest.mark.asyncio
async def test_la_chat_riceve_le_regole_intere_byte_per_byte():
    """La chat ha tutti gli strumenti: il suo blocco e' quello di prima,
    identita' e regole, byte per byte."""
    from hiris.app.claude_runner import BASE_IDENTITY
    from hiris.app.home_space.tools import KNOWLEDGE_TOOLS

    system = await _sent_system(KNOWLEDGE_TOOLS)
    assert (BASE_IDENTITY + BASE_TOOL_RULES) in system


# -- la partenza unica ----------------------------------------------------------

class _Runner:
    """Un runner che risponde e tiene cio' che ha ricevuto."""

    def __init__(self):
        self.ricevuto = None

    async def chat(self, **kwargs):
        self.ricevuto = kwargs
        return "ok"


@pytest.mark.asyncio
async def test_un_mestiere_senza_strumenti_non_puo_riceverne():
    """L'elenco d'ammissione: l'attuatore non tocca la casa, e un turno che
    gli desse `execute` non parte. Il runner non viene nemmeno chiamato.

    Mutazione ESEGUITA il 06/10/2026: tolto il controllo da `chain_turn` --
    rossa, il runner riceve `execute`."""
    from hiris.app.home_space.tools import KNOWLEDGE_TOOLS

    runner = _Runner()
    execute = [d for d in KNOWLEDGE_TOOLS if d["name"] == "execute"]
    with pytest.raises(ValueError, match="execute"):
        await steering.chain_turn(runner, steering.ACTUATOR_SPECIES, usage=None,
                                  max_tokens=64, user_message="?", tools=execute)
    assert runner.ricevuto is None


@pytest.mark.asyncio
async def test_la_promessa_riceve_i_suoi_strumenti_e_non_altri():
    from hiris.app.home_space.tools import KNOWLEDGE_TOOLS
    from hiris.app.keeper.exchange import promise_tools

    runner = _Runner()
    answer, turn = await steering.chain_turn(
        runner, steering.PROMISE_SPECIES, usage=None, max_tokens=64,
        user_message="?", tools=promise_tools())
    assert answer == "ok" and turn.truncated is False
    assert runner.ricevuto["max_tokens"] == 64
    with pytest.raises(ValueError, match="execute"):
        await steering.chain_turn(runner, steering.PROMISE_SPECIES, usage=None,
                                  max_tokens=64, user_message="?",
                                  tools=KNOWLEDGE_TOOLS)


def test_la_partenza_dichiara_il_ripiego_solo_se_il_turno_parte(monkeypatch):
    """`start` chiede chi risponde e, sulla catena, dichiara il ripiego. Un
    giro senza nessun modello non e' passato dal forfait al consumo."""
    dichiarati = []
    monkeypatch.setattr(steering, "who_answers", lambda app: ("catena", "tetto"))
    monkeypatch.setattr(steering, "declare_downgrade",
                        lambda app, *, agent, reason: dichiarati.append((agent, reason)))

    runner = _Runner()
    assert steering.start({"claude_runner": runner}, "analista") == ("catena", "tetto", runner)
    assert dichiarati == [("analista", "tetto")]
    assert steering.start({}, "analista") == ("catena", "tetto", None)
    assert dichiarati == [("analista", "tetto")]

    monkeypatch.setattr(steering, "who_answers", lambda app: ("ponte", ""))
    assert steering.start({"claude_runner": runner}, "analista") == ("ponte", "", None)


class _Coda:
    def __init__(self):
        self.accodati = []

    def enqueue(self, kind, wake, context, deadline, *, now=None, thread=None,
                priority=None):
        self.accodati.append({"kind": kind, "wake": wake, "context": context,
                              "deadline": deadline, "now": now,
                              "thread": thread, "priority": priority})
        return "job-1"


@pytest.mark.parametrize("species", sorted(steering.SPECIES))
def test_l_accodamento_prende_tutto_dalla_dichiarazione(species):
    """Il `kind`, la precedenza, il modello e la scadenza: nessun mestiere
    li scrive piu' a mano."""
    app = {"reasoning_queue": _Coda(),
           "models_config": {"ponte": {"modello": "opus", "scadenza_min": 7}}}
    job_id, minuti = steering.enqueue_turn(app, species, {"w": 1}, {"c": 2},
                                           thread="filo", now=1000.0)
    (job,) = app["reasoning_queue"].accodati
    declared = steering.SPECIES[species]
    assert (job_id, minuti) == ("job-1", 7)
    assert job == {"kind": declared.kind, "wake": {"w": 1},
                   "context": {"c": 2, "model": "opus"},
                   "deadline": 1000.0 + 7 * 60, "now": 1000.0,
                   "thread": "filo", "priority": declared.priority}


def test_le_viste_del_ponte_vengono_dalle_dichiarazioni():
    """`_SELF_CONTAINED_KINDS`, `RAGIONABILI` e `JOB_SPECIES` non si scrivono
    piu' in `agent/runner.py`.

    Mutazione ESEGUITA il 06/10/2026: la promessa dichiarata senza strumenti
    in `steering.SPECIES` -- il suo `kind` entra in `_SELF_CONTAINED_KINDS`
    senza toccare `agent/runner.py`."""
    from hiris.app.agent import runner as ponte

    assert ponte.JOB_SPECIES is steering.JOB_SPECIES
    assert set(ponte.RAGIONABILI) == {s.kind for s in steering.SPECIES.values()}
    assert set(ponte._SELF_CONTAINED_KINDS) == {
        s.kind for s in steering.SPECIES.values() if s.self_contained}
    assert len(ponte._SELF_CONTAINED_KINDS) >= 4
