"""Un turno della catena in cui nessun backend ha risposto si registra «fallito».

Misurato sulla casa vera (registro dei turni, dal 03/10 al 05/10/2026): 61
turni dell'analista scritti `riuscito`, `model: ignoto`, `output_tokens:
None`, circa due secondi ciascuno. Erano turni in cui TUTTI i provider della
catena avevano rifiutato: `LLMRouter.chat` non solleva, restituisce una frase
di cortesia, e `steering.misura_turno` scriveva `fallito` solo quando il
blocco sollevava.

La frase resta: la chat la mostra all'utente, ed e' l'unica cosa che l'utente
legge. Cambia solo cio' che il registro dice del turno.
"""
from __future__ import annotations

import pytest

from hiris.app import steering
from hiris.app.claude_runner import RunnerBackendError
from hiris.app.llm_router import LLM_ROUTER_KEY, LLMRouter
from hiris.app.mind import analyst_round
from hiris.app.mind.store import OBSERVATIONS_KEY
from hiris.app.steering import BRIDGE_ACTIVE_KEY
from hiris.app.usage.store import UsageStore
from tests._runner_finto import RunnerFinto


def _rifiuta(messaggio: str = "Errore Claude.") -> RunnerFinto:
    return RunnerFinto(RunnerBackendError(messaggio))


def _risponde(testo: str = "risposta") -> RunnerFinto:
    return RunnerFinto(testo)


@pytest.fixture()
def consumi(tmp_path):
    archivio = UsageStore(str(tmp_path / "consumi.db"))
    yield archivio
    archivio.close()


@pytest.mark.asyncio
async def test_tutti_rifiutano_il_router_lo_dice_e_la_frase_resta():
    router = LLMRouter(claude=_rifiuta("Errore Claude."), model_chain=["claude"])
    risposta = await router.chat(user_message="ciao", model="auto")
    # La chat continua a mostrare la frase che mostrava.
    assert risposta == "Errore Claude."
    assert router.last_unanswered is True


@pytest.mark.asyncio
async def test_una_catena_vuota_non_ha_risposto():
    router = LLMRouter(claude=_risponde(), model_chain=[])
    risposta = await router.chat(user_message="ciao", model="auto")
    assert "Nessun provider utilizzabile in catena" in risposta
    assert router.last_unanswered is True


@pytest.mark.asyncio
async def test_il_segnale_si_azzera_a_ogni_chiamata():
    """Un turno che risponde dopo uno in cui nessuno ha risposto non eredita
    il segnale: e' per chiamata, come `last_truncated`."""
    giu = LLMRouter(claude=_rifiuta(), model_chain=["claude"])
    await giu.chat(user_message="ciao", model="auto")
    su = LLMRouter(claude=_risponde(), model_chain=["claude"])
    assert await su.chat(user_message="ciao", model="auto") == "risposta"
    assert su.last_unanswered is False


@pytest.mark.asyncio
async def test_il_registro_dei_turni_scrive_fallito(consumi):
    router = LLMRouter(claude=_rifiuta(), openrouter=_rifiuta("giu'"),
                       model_chain=["claude", "openrouter"])
    async with steering.misura_turno(consumi, router,
                                     specie=steering.ANALYST_SPECIES,
                                     canale="catena"):
        await router.chat(user_message="ciao", model="auto")
    assert consumi.turns()[0]["outcome"] == "fallito"


@pytest.mark.asyncio
async def test_un_turno_che_risponde_resta_riuscito(consumi):
    router = LLMRouter(claude=_rifiuta(), openrouter=_risponde(),
                       model_chain=["claude", "openrouter"])
    async with steering.misura_turno(consumi, router,
                                     specie=steering.ANALYST_SPECIES,
                                     canale="catena"):
        await router.chat(user_message="ciao", model="auto")
    riga = consumi.turns()[0]
    assert riga["outcome"] == "riuscito"
    assert riga["provider"] == "openrouter"


# -- chi chiama lo sa (rilievo G29-1) ------------------------------------------
# Il registro scriveva gia' «fallito», ma il turno lo teneva per se': i
# mestieri di sfondo leggevano la frase del router come risposta del modello.
# Il caso delle ricette, il piu' grave, sta in test_mind_recipe_turn.

@pytest.mark.asyncio
async def test_il_turno_dice_che_nessuno_ha_risposto_anche_senza_archivio():
    """Come `truncated`: il mestiere ne ha bisogno anche quando nessuno misura.

    Mutazione ESEGUITA: `misura_turno` che non abbassa `answered` -- rossa."""
    router = LLMRouter(claude=_rifiuta(), model_chain=["claude"])
    async with steering.misura_turno(None, router,
                                     specie=steering.ANALYST_SPECIES,
                                     canale="catena") as turno:
        risposta = await router.chat(user_message="ciao", model="auto")

    assert turno.answered is False
    # La chat ha ancora la sua frase; il mestiere legge «nessuna risposta».
    assert risposta == "Errore Claude."
    assert steering.chain_answer(risposta, turno) == ""


@pytest.mark.asyncio
async def test_un_turno_che_risponde_consegna_la_risposta():
    router = LLMRouter(claude=_rifiuta(), openrouter=_risponde("[]"),
                       model_chain=["claude", "openrouter"])
    async with steering.misura_turno(None, router,
                                     specie=steering.ANALYST_SPECIES,
                                     canale="catena") as turno:
        risposta = await router.chat(user_message="ciao", model="auto")

    assert turno.answered is True
    assert steering.chain_answer(risposta, turno) == "[]"


@pytest.mark.asyncio
async def test_l_analista_sulla_catena_non_legge_la_frase_del_router(tmp_path):
    """Prima: «la risposta non e' un JSON leggibile», a ogni giro, per un
    guasto della catena. Ora il motivo e' quello vero.

    Mutazione ESEGUITA: `analyst_round` che passa `answer` invece di
    `chain_answer(answer, turn)` -- rossa (il motivo torna «non JSON»)."""
    from hiris.app.mind.store import ObservationsStore
    from tests.test_mind_analyst_round import _resoconto

    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        for giorno in ("2026-09-15", "2026-09-16", "2026-09-17"):
            store.replace_report(giorno, _resoconto(giorno))
        router = LLMRouter(claude=_rifiuta(), model_chain=["claude"])
        app = {OBSERVATIONS_KEY: store, LLM_ROUTER_KEY: router,
               BRIDGE_ACTIVE_KEY: False}

        esito = await analyst_round.analyst_round(app)

        assert router.last_unanswered is True
        assert esito["problemi"] == [steering.NO_ANSWER_REASON]
    finally:
        store.close()
