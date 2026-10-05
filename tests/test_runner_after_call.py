"""Cio' che si legge da un runner DOPO la chiamata (B27, regola allargata il 05/10/2026).

La regola di CLAUDE.md diceva soltanto: un kwarg nuovo di `ClaudeRunner` lo
accetta anche `OpenAICompatRunner`. Ma un runner non si usa solo passandogli
argomenti: dopo `chat()` chi misura ne LEGGE degli attributi --
`last_tool_calls`, `last_truncated`, `last_tool_leaked`, `provider_name` -- e
li legge con `getattr(runner, "...", <ripiego>)`. Un attributo che un backend
non scrive non rompe niente: il ripiego lo copre, e il segnale tace **in
silenzio** proprio sul backend che non lo porta. E' lo stesso guasto della
regola dei kwarg, dall'altra parte della chiamata.

L'elenco NON si scrive: si chiede al sorgente (I-0). Sono le stringhe
passate a `getattr` su un nome che contiene `runner`, in tutto il prodotto.
Si scrive a mano solo cio' che un backend non porta DI PROPOSITO, con la
ragione: e' una lista di ammissione, e chiude per difetto.
"""
import ast
from pathlib import Path

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import ClaudeRunner
from hiris.app.llm_router import LLMRouter

_APP = Path(__file__).resolve().parent.parent / "hiris" / "app"

#: Ammissioni: (classe, attributo) -> perche' quel backend non lo porta.
_DELIBERATELY_ABSENT = {
    ("OpenAICompatRunner", "last_thinking_blocks"):
        "le API compatibili OpenAI non hanno l'Extended Thinking di Anthropic: "
        "`thinking_budget` si accetta e si ignora, e chi legge ripiega su None",
    ("ClaudeRunner", "provider_name"):
        "chi misura riceve il ROUTER, che scrive da se' chi ha risposto "
        "(`LLMRouter.provider_name`, dalla sua ContextVar): Claude e' uno solo, "
        "mentre `OpenAICompatRunner` lo porta perche' una classe serve tre "
        "provider (openai, ollama, openrouter)",
}


def _receiver_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _read_after_call() -> dict[str, set[str]]:
    """Attributo -> i file che lo leggono con `getattr(<...runner...>, "attr")`."""
    found: dict[str, set[str]] = {}
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr" and len(node.args) >= 2):
                continue
            receiver, attr = node.args[0], node.args[1]
            if ("runner" in _receiver_name(receiver).lower()
                    and isinstance(attr, ast.Constant) and isinstance(attr.value, str)):
                found.setdefault(attr.value, set()).add(str(path.relative_to(_APP)))
    return found


def _runners() -> list:
    return [ClaudeRunner(api_key="sk-prova"),
            OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="sk-prova")]


def test_the_derivation_still_sees_what_is_read():
    """Un insieme improvvisamente piccolo e' un cancello che non guarda piu' niente."""
    read = _read_after_call()
    assert {"last_tool_calls", "last_truncated", "last_tool_leaked",
            "provider_name"} <= set(read), sorted(read)


def test_every_runner_carries_what_is_read_after_the_call():
    read = _read_after_call()
    for runner in _runners():
        cls = type(runner).__name__
        for attr, readers in sorted(read.items()):
            if (cls, attr) in _DELIBERATELY_ABSENT:
                continue
            assert hasattr(runner, attr), (
                f"{cls} non porta «{attr}», che {sorted(readers)} legge dopo la "
                "chiamata: su questo backend il segnale tacerebbe in silenzio, "
                "coperto dal ripiego di `getattr`. O lo porta, o entra in "
                "_DELIBERATELY_ABSENT con la ragione")


def test_the_router_carries_everything_that_is_read():
    """Chi misura riceve il router: li' non c'e' ammissione che tenga."""
    for attr, readers in sorted(_read_after_call().items()):
        assert hasattr(LLMRouter, attr), (
            f"LLMRouter non porta «{attr}», che {sorted(readers)} legge dopo la "
            "chiamata")


def test_the_admissions_are_still_true():
    """Un'ammissione per qualcosa che il backend ormai porta, o che nessuno
    legge piu', e' una riga che mente."""
    read = _read_after_call()
    by_name = {type(r).__name__: r for r in _runners()}
    for (cls, attr) in _DELIBERATELY_ABSENT:
        assert attr in read, f"nessuno legge piu' «{attr}»: l'ammissione esce"
        assert not hasattr(by_name[cls], attr), (
            f"{cls} ora porta «{attr}»: l'ammissione esce")


def _reset_in_chat(cls) -> set[str]:
    """Gli attributi che `cls.chat` riscrive con un valore VUOTO (`False`,
    `None`, `[]`): l'azzeramento, non le scritture dell'esito."""
    import inspect
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls.chat)))
    reset = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        empty = ((isinstance(value, ast.Constant) and value.value in (False, None))
                 or (isinstance(value, ast.List) and not value.elts))
        for target in node.targets:
            if (empty and isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name) and target.value.id == "self"):
                reset.add(target.attr)
    return reset


def test_every_per_call_signal_is_reset_when_the_call_starts():
    """Un segnale per chiamata che `chat()` non azzera racconta la chiamata
    PRIMA. Si guarda l'azzeramento, non una scrittura qualunque: `chat()`
    scrive anche l'esito (`= True`), e quella riga non azzera niente."""
    for runner in _runners():
        cls = type(runner)
        reset = _reset_in_chat(cls)
        for attr in sorted(_read_after_call()):
            if attr.startswith("last_") and hasattr(runner, attr):
                assert attr in reset, (
                    f"{cls.__name__}.chat non azzera «{attr}» all'ingresso")
