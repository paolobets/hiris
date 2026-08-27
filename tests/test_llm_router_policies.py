import pytest

from hiris.app.llm_router import LLMRouter


class _R:
    def __init__(self, name):
        self.name = name
        self.calls = []

    async def chat(self, **kw):
        self.calls.append(kw)
        return self.name

    async def chat_stream(self, **kw):
        self.calls.append(kw)
        yield self.name


def _router():
    return LLMRouter(
        claude=_R("claude"), ollama=_R("ollama"),
        chat_policy=["claude", "ollama"],
    )


@pytest.mark.asyncio
async def test_chat_mode_uses_chat_policy_first():
    r = _router()
    out = await r.chat(model="auto")  # chat_policy[0]=claude
    assert out == "claude"


# fetta E3 Task 8: `test_automatic_mode_uses_automatic_policy_first' e'
# uscito, cancellato e non spostato -- provava che chiamare
# `run_with_actions` SENZA `mode` esplicito usasse comunque `automatic_
# policy` (il suo default interno era "automatic", a differenza di `chat()`
# che defaulta a "chat"). Uscito il metodo (con il suo unico chiamante, la
# Sentinella, al Task 7).
#
# fetta E4 Task 7 ("un bot solo"): `test_scheduled_chat_can_force_automatic_
# mode` (il caso gemello esplicito che la nota sopra teneva vivo, passava
# `mode="automatic"` a `chat()`) e' uscito ora insieme a lei -- il pop di
# `mode` in `chat()`/`chat_stream()` e' uscito, `_ordered_backends()` legge
# la sola `chat_policy`: non esiste piu' nessun instradamento da "automatic"
# da provare. Verificato che cadesse per costruzione (con `_router()` privato
# del kwarg `automatic_policy`, l'output tornava "claude" -- chat_policy[0]
# -- invece di "ollama") prima della cancellazione.


# fetta E4 Task 7, fix round 1: `test_mode_not_forwarded_to_runner` e' uscito,
# cancellato e non spostato -- non passava mai `mode`, quindi la sua
# asserzione (`"mode" not in kw`) era vera per costruzione qualunque cosa
# facesse il router: non poteva fallire, esattamente il criterio di vacuita'
# gia' applicato al gemello streaming (sotto). Il `pop` che un tempo dava
# quella garanzia e' uscito insieme al concetto di `mode` -- oggi `chat()`
# inoltra tutto cio' che riceve, quindi se qualcuno passasse `mode` verrebbe
# inoltrato per davvero: il nome del test dichiarava al presente una garanzia
# non piu' vera. Nessun soggetto vivo da spostare: non c'e' piu' nessun pop
# da provare.


# fetta E4 Task 7: `_StrictR` e `test_chat_mode_leak_hardening_strict_runner_
# rejects_mode_kwarg` sono usciti insieme al kwarg costruttore
# `automatic_policy` che il test passava (`LLMRouter.__init__() got an
# unexpected keyword argument 'automatic_policy'`, verificato prima della
# cancellazione) -- la guardia che difendevano (mode="automatic" instradato
# senza leak verso il runner) non ha piu' senso: `mode` non e' piu' un
# kwarg che il router riconosce o instrada, quindi non c'e' piu' nessun pop
# da tenere sotto controllo.


# fetta E3 Task 8: `test_run_with_actions_mode_leak_hardening_strict_runner_
# rejects_mode_kwarg` e' uscito, cancellato e non spostato -- stessa prova
# del test sopra, ma per `run_with_actions`, uscito insieme al suo unico
# chiamante (la Sentinella, uscita al Task 7). `_StrictR.run_with_actions`
# (sopra) e' uscito con lui: nessun altro test in questo file lo chiamava.


@pytest.mark.asyncio
async def test_explicit_model_overrides_policy():
    r = _router()
    out = await r.chat(model="claude-sonnet-4-6")  # explicit -> claude regardless of policy
    assert out == "claude"


@pytest.mark.asyncio
async def test_backward_compat_policies_default_from_strategy():
    r = LLMRouter(claude=_R("claude"), ollama=_R("ollama"), strategy="cost_first")
    # cost_first order: ollama before claude.
    # fetta E3 Task 8: la meta' di questo test su `run_with_actions` e'
    # uscita insieme al metodo (uscito con la Sentinella, Task 7) -- la
    # prova su `chat()` sotto copre lo stesso invariante su un ramo vivo.
    assert await r.chat(model="auto") == "ollama"


@pytest.mark.asyncio
async def test_chat_stream_auto_uses_chat_policy_first_backend():
    r = _router()
    chunks = [c async for c in r.chat_stream(model="auto")]
    assert chunks == ["claude"]


# fetta E4 Task 7: `test_chat_stream_mode_not_forwarded_to_runner' e' uscito,
# cancellato e non spostato -- passava `mode="automatic"` per far scegliere
# `ollama` (automatic_policy=["ollama", "claude"]) e verificava che `mode`
# non arrivasse al SUO runner. Con `automatic_policy` e il pop di `mode`
# usciti, `_ordered_backends()` sceglie sempre il primo di `chat_policy`
# (claude, qui) -- `r._ollama.calls` resta vuota e l'asserzione
# `all("mode" not in kw for kw in r._ollama.calls)` torna vera sul vuoto,
# senza piu' esercitare nulla: un pass silenzioso che non prova piu' cio'
# che il nome promette (il silenzio non dichiarato che le regole della
# fetta vietano). Verificato eseguendolo prima della cancellazione: il
# runner interpellato per davvero era diventato `claude`, non `ollama`, e
# `mode` fluiva senza controllo in `r._claude.calls` (mai controllato da
# questo test).


def test_policy_drops_unknown_backend_names_preserving_order():
    # fetta E4 Task 7: spostato da `automatic_policy`/`r._automatic_policy`
    # (usciti) a `chat_policy`/`r._chat_policy` -- il soggetto (_norm_policy
    # applicato al kwarg del costruttore, non solo alla funzione pura gia'
    # coperta da test_router_backlog_fixes.py) resta vivo, cambia solo la
    # via d'accesso.
    r = LLMRouter(
        claude=_R("claude"), ollama=_R("ollama"),
        chat_policy=["bogus", "ollama", "claude", "also_bogus"],
    )
    assert r._chat_policy == ["ollama", "claude"]
