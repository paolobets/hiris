"""Il turno troncato si vede, si conta, e non si legge (Tappa 6, Task 3).

**Perche' esiste, misurato.** In `docs/misure/2026-10-tappa-0.md` 7 turni
dell'analista su 8 si fermano al tetto di 4.096 token -- e il registro dei
turni li chiamava tutti «riusciti» (D-58): `ClaudeRunner` e
`OpenAICompatRunner` trasformavano `stop_reason="max_tokens"` e
`finish_reason="length"` in un testo, e il segnale finiva li'. Chi leggeva il
JSON di quella risposta provava a cavarne decisioni da meta' testo.

Da qui (D2, approvata il 05/10/2026):
- i runner DICONO la troncatura (`last_truncated`, per chiamata), e il testo
  che restituiscono non cambia;
- `steering.misura_turno` la registra con l'esito `troncato` e la consegna al
  mestiere;
- il lettore unico non legge una risposta troncata;
- un freno ferma il mestiere dopo N troncati di fila -- spento finche' N non
  e' misurato dal vivo.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app import server, steering
from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import _TRUNCATION_NOTICE, ClaudeRunner
from hiris.app.home_space import historian
from hiris.app.llm_router import LLMRouter
from hiris.app.mind import analyst_turn, observer, proposer_turn
from hiris.app.mind import recipe_turn as rt
from hiris.app.mind.knowledge import KnowledgeStore
from hiris.app.mind.store import ObservationsStore
from hiris.app.usage.store import UsageStore
from tests.test_mind_analyst_round import _resoconto
from tests.test_mind_analyst_turn import _serie as serie_analista
from tests.test_mind_observer import _casa
from tests.test_mind_recipe_turn import CASA, RICETTA_BUONA
from tests.test_proponente import osservazioni as osservazioni_proponente

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"


# -- il lettore unico ----------------------------------------------------------

def test_un_turno_troncato_NON_si_legge_nemmeno_se_il_JSON_si_chiude():
    """**La decisione D2.** Un JSON tagliato a meta' che per caso si chiude --
    l'array di 380 giudizi fermato dopo il centesimo, con la `]` che il
    modello aveva gia' scritto in un esempio -- e' l'unico modo di inventare
    decisioni da una risposta che il modello non ha finito.

    Mutazione ESEGUITA: ignorare `truncated` nel lettore -- rossa (esce il
    dato)."""
    dato, ragione = steering.read_json('[{"id": "a"}]', shape=list,
                                       what="un elenco", truncated=True)

    assert dato is None
    assert ragione == steering.TRUNCATED_REASON


def test_una_risposta_ILLEGGIBILE_e_un_guasto_non_un_dato_vuoto():
    """La distinzione a tre stati: un dato vuoto afferma qualcosa, un guasto
    no. Era la prova di `read_recipe`, uscito col lettore."""
    dato, ragione = steering.read_json("mi dispiace, non saprei", shape=dict,
                                       what="una ricetta")

    assert dato is None
    assert "JSON" in ragione


def test_una_risposta_VUOTA_dice_che_il_modello_non_ha_risposto():
    assert steering.read_json("  ", shape=dict, what="x") == (
        None, steering.NO_ANSWER_REASON)


def test_la_forma_sbagliata_si_rifiuta_con_le_parole_del_mestiere():
    dato, ragione = steering.read_json('{"a": 1}', shape=list,
                                       what="un elenco di decisioni")

    assert dato is None
    assert ragione == "la risposta non e' un elenco di decisioni"


# -- i runner dicono la troncatura ---------------------------------------------

def _risposta_anthropic(stop_reason: str, testo: str = "inizio della risp"):
    risposta = MagicMock(stop_reason=stop_reason)
    risposta.content = [MagicMock(type="text", text=testo)]
    return risposta


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason,troncato", [
    ("max_tokens", True),
    ("model_context_window_exceeded", True),
    ("end_turn", False),
])
async def test_ClaudeRunner_dice_la_troncatura(stop_reason, troncato):
    """Fonte dei valori: SDK `anthropic` 1.11.0, `types/message.py` (letto il
    05/10/2026; vedi `claude_runner._current_truncated`).

    Mutazione ESEGUITA: `ClaudeRunner` che ignora `stop_reason` (il ramo
    `max_tokens` non scrive `last_truncated`) -- rossa sul primo caso."""
    runner = ClaudeRunner(api_key="sk-prova")
    runner._client.messages.create = AsyncMock(
        return_value=_risposta_anthropic(stop_reason))

    testo = await runner.chat("ciao", model="claude-sonnet-4-6")

    assert runner.last_truncated is troncato
    if stop_reason == "max_tokens":
        # Il testo di oggi non cambia: nessun chiamante si rompe.
        assert _TRUNCATION_NOTICE in testo


@pytest.mark.asyncio
async def test_ClaudeRunner_azzera_il_segnale_a_ogni_chiamata():
    """Il turno dopo un troncato non e' troncato: il segnale e' della
    chiamata, non dell'oggetto (che vive quanto l'add-on)."""
    runner = ClaudeRunner(api_key="sk-prova")
    runner._client.messages.create = AsyncMock(side_effect=[
        _risposta_anthropic("max_tokens"), _risposta_anthropic("end_turn")])

    await runner.chat("uno", model="claude-sonnet-4-6")
    assert runner.last_truncated is True
    await runner.chat("due", model="claude-sonnet-4-6")
    assert runner.last_truncated is False


def _risposta_openai(finish_reason: str):
    messaggio = MagicMock(content="inizio della risp", tool_calls=None)
    risposta = MagicMock(choices=[MagicMock(finish_reason=finish_reason,
                                            message=messaggio)])
    risposta.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    return risposta


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason,troncato", [("length", True),
                                                    ("stop", False)])
async def test_OpenAICompatRunner_dice_la_troncatura(finish_reason, troncato):
    """Fonte: SDK `openai` 3.24.0, `types/chat/chat_completion.py`; OpenRouter
    e Ollama usano lo stesso `"length"` (letti il 05/10/2026).

    Mutazione ESEGUITA: `OpenAICompatRunner` che ignora `finish_reason` (il
    ramo `length` non scrive `last_truncated`) -- rossa sul primo caso."""
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1",
                                api_key="sk-prova")
    runner._client.chat.completions.create = AsyncMock(
        return_value=_risposta_openai(finish_reason))

    await runner.chat(user_message="ciao", model="gpt-4o")

    assert runner.last_truncated is troncato


@pytest.mark.asyncio
async def test_il_router_dice_la_troncatura_di_chi_ha_risposto():
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1",
                                api_key="sk-prova")
    runner._client.chat.completions.create = AsyncMock(
        return_value=_risposta_openai("length"))
    router = LLMRouter(openai=runner, model_chain=["openai"])

    await router.chat(user_message="ciao", model="auto")

    assert router.last_truncated is True


@pytest.mark.asyncio
async def test_il_router_senza_nessuno_che_risponde_non_eredita_il_segnale():
    """Un troncato di una chiamata PRECEDENTE dello stesso compito non deve
    leggersi come di questa, quando il router risponde da se'."""
    primo = MagicMock()
    primo.chat = AsyncMock(side_effect=RuntimeError("giu'"))
    router = LLMRouter(claude=primo, model_chain=["claude"])
    # La chiamata di prima, nello stesso compito, era troncata: il segnale e'
    # la ContextVar condivisa, e un runner qualunque la scrive.
    ClaudeRunner(api_key="sk-prova").last_truncated = True

    await router.chat(user_message="ciao", model="auto")

    assert router.last_truncated is False


def _runner_classes() -> dict[str, Path]:
    """Le classi del prodotto che definiscono `chat`: i runner. **Chieste al
    sorgente**, non elencate: un runner nuovo entra nella prova da solo."""
    trovate = {}
    for percorso in APP.rglob("*.py"):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.ClassDef) and any(
                    isinstance(f, ast.AsyncFunctionDef) and f.name == "chat"
                    for f in nodo.body):
                trovate[nodo.name] = percorso
    return trovate


def test_ogni_runner_espone_il_segnale_di_troncatura():
    """**La regola di CLAUDE.md, per un attributo**: cio' che `ClaudeRunner`
    offre al chiamante comune lo offre anche ogni altro runner, o il turno
    servito da un backend non-Claude si dichiarerebbe «riuscito» in silenzio.

    Derivazione: le classi si chiedono al sorgente. Mutazione ESEGUITA: tolto
    `last_truncated` da `LLMRouter` -- rossa, nominandolo."""
    import importlib

    classi = _runner_classes()
    assert {"ClaudeRunner", "OpenAICompatRunner", "LLMRouter"} <= set(classi), (
        f"la ricerca dei runner e' rotta: ha trovato solo {sorted(classi)}")
    for nome, percorso in classi.items():
        modulo = ".".join(percorso.relative_to(APP.parents[1]).with_suffix("").parts)
        classe = getattr(importlib.import_module(modulo), nome)
        assert hasattr(classe, "last_truncated"), (
            f"{nome} ({percorso.name}) non espone `last_truncated`")


# -- l'imbuto lo registra e lo consegna ----------------------------------------

class _Troncato:
    """Un runner che risponde un JSON valido MA dichiara la troncatura."""

    def __init__(self, risposta: str, troncato: bool = True):
        self.risposta = risposta
        self.last_truncated = troncato
        self.last_tool_calls = []
        self.chiamate = 0

    async def chat(self, **kwargs):
        self.chiamate += 1
        return self.risposta


@pytest.fixture()
def consumi(tmp_path):
    archivio = UsageStore(str(tmp_path / "consumi.db"))
    yield archivio
    archivio.close()


@pytest.mark.asyncio
async def test_il_registro_dei_turni_scrive_TRONCATO(consumi):
    """Mutazione ESEGUITA: `misura_turno` che non legge il segnale -- rossa
    («riuscito»)."""
    runner = _Troncato("x")
    async with steering.misura_turno(consumi, runner, specie="analista",
                                     canale="catena") as turno:
        await runner.chat()

    assert turno.truncated is True
    assert consumi.turns()[0]["outcome"] == steering.TRUNCATED


@pytest.mark.asyncio
async def test_il_troncato_arriva_al_mestiere_anche_senza_archivio():
    runner = _Troncato("x")
    async with steering.misura_turno(None, runner, specie="analista",
                                     canale="catena") as turno:
        await runner.chat()

    assert turno.truncated is True


@pytest.mark.asyncio
async def test_l_osservatore_troncato_non_decide_niente(tmp_path):
    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        runner = _Troncato(json.dumps(
            [{"id": "climate.camera_t", "dentro": True, "motivo": "scalda"}]))

        esito = await observer.reconsider(runner, archivio, _casa(),
                                          reason="prova", now=1000.0)

        assert esito == {"errore": steering.TRUNCATED_REASON}
        assert archivio.scope() == {}
        assert archivio.last_reconsideration() is None
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_la_ricetta_troncata_non_si_scrive_ma_si_dice_perche(tmp_path):
    sapere = KnowledgeStore(str(tmp_path / "sapere.db"))
    try:
        runner = _Troncato(json.dumps(RICETTA_BUONA))

        esito = await rt.ask(runner, sapere, CASA, "dev1", objective="x",
                             who="prova", when_ts=1_758_000_000.0)

        assert esito["scritta"] is False
        assert esito["problemi"] == [steering.TRUNCATED_REASON]
    finally:
        sapere.close()


@pytest.mark.asyncio
async def test_l_analista_troncato_non_scrive_l_analisi(tmp_path):
    """Il caso misurato (7 su 8). Mutazione ESEGUITA: `analyst_round` che non
    passa `truncated` -- rossa (l'analisi si scrive da una risposta che il
    modello non aveva finito)."""
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        for giorno in ("2026-09-15", "2026-09-16", "2026-09-17"):
            store.replace_report(giorno, _resoconto(giorno))
        runner = _Troncato(json.dumps({"osservazioni": []}))
        app = {"observations": store, "llm_router": runner, "bridge_active": False}

        esito = await server.analyst_round(app)

        assert runner.chiamate == 1
        assert esito["problemi"] == [steering.TRUNCATED_REASON]
        oggi = historian.today(historian.house_timezone(None)).isoformat()
        assert store.analysis(oggi) is None
    finally:
        store.close()


def test_il_proponente_troncato_non_scrive_esiti():
    esito = proposer_turn.apply_outcomes(
        osservazioni_proponente(), json.dumps({"esiti": []}), truncated=True)

    assert esito["esiti"] == []
    assert esito["problemi"] == [steering.TRUNCATED_REASON]


def test_l_analista_troncato_al_livello_della_risposta():
    esito = analyst_turn.apply_analysis(
        serie_analista(), json.dumps({"osservazioni": []}), truncated=True)

    assert esito["analisi"] is None
    assert esito["problemi"] == [steering.TRUNCATED_REASON]


# -- il freno ------------------------------------------------------------------

def _troncati(consumi, specie, quanti, *, ts=1_758_000_000.0):
    for i in range(quanti):
        consumi.log_turn(species=specie, provider="claude", model="m",
                         channel="catena", duration_ms=1, iterations=1,
                         tools=[], outcome=steering.TRUNCATED, now=ts + i)


def test_il_freno_e_SPENTO_finche_N_non_e_misurato(consumi):
    """«Un numero non misurato non si scrive»: N si fissa dal vivo (T9)."""
    assert steering.TRUNCATION_BRAKE is None
    _troncati(consumi, "analista", 50)

    assert steering.brake_engaged(consumi, "analista") is False


@pytest.mark.asyncio
async def test_il_freno_ferma_il_mestiere_dopo_N_troncati_di_fila(consumi, monkeypatch):
    """Mutazione ESEGUITA: `brake_engaged` che conta anche un turno riuscito
    in mezzo -- rossa sul secondo `assert`."""
    monkeypatch.setattr(steering, "TRUNCATION_BRAKE", 2)
    _troncati(consumi, "analista", 2)

    with pytest.raises(steering.TurnBraked):
        async with steering.misura_turno(consumi, _Troncato("x"),
                                         specie="analista", canale="catena"):
            pytest.fail("il turno non doveva partire")

    consumi.log_turn(species="analista", provider="claude", model="m",
                     channel="catena", duration_ms=1, iterations=1, tools=[],
                     outcome="riuscito", now=1_758_000_100.0)
    assert steering.brake_engaged(consumi, "analista") is False


def test_il_freno_non_ferma_la_chat(consumi, monkeypatch):
    """La chat ha una persona davanti che vede la troncatura."""
    monkeypatch.setattr(steering, "TRUNCATION_BRAKE", 2)
    _troncati(consumi, "chat", 5)

    assert steering.brake_engaged(consumi, "chat") is False


def test_il_freno_conta_UN_mestiere_alla_volta(consumi, monkeypatch):
    monkeypatch.setattr(steering, "TRUNCATION_BRAKE", 2)
    _troncati(consumi, "analista", 2)
    consumi.log_turn(species="osservatore", provider="claude", model="m",
                     channel="catena", duration_ms=1, iterations=1, tools=[],
                     outcome="riuscito", now=1_758_000_500.0)

    assert steering.brake_engaged(consumi, "analista") is True
