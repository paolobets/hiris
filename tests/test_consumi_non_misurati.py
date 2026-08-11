"""GET /api/usage quando non c'è nessun contatore da leggere — voce C-1.

Nella configurazione dell'UAT (abbonamento acceso, nessuna chiave API, nessun
Ollama) `server.py` lascia `llm_router` e `claude_runner` a `None`, e questa
rotta rispondeva **503**. Il frontend lo raccoglieva nei rami che ha già
scritti per i guasti di rete e mostrava un errore generico: «Errore caricamento
consumi.» su `#/usage`, e quattro «—» ripetuti ogni 30 secondi nel riquadro
della chat.

Il fatto è legittimo — in abbonamento i consumi non si misurano — e va
DICHIARATO, non travestito da guasto. Qui si pinna la forma della
dichiarazione: 200, `misurata: false`, un `motivo` che il frontend può leggere
e un `messaggio` che l'utente può leggere. I contatori restano `null` e non
`0`: `0` affermerebbe «misurato, e non hai consumato niente».
"""
import asyncio
import json

from hiris.app.api.handlers_usage import handle_usage, handle_reset_usage


class _Req:
    """Il minimo che i due handler usano: `request.app`, `.get()`-abile."""

    def __init__(self, app):
        self.app = app


class _RunnerFinto:
    total_input_tokens = 1200
    total_output_tokens = 800
    total_requests = 42
    total_cost_usd = 2.0
    total_rate_limit_errors = 1
    usage_last_reset = "2026-07-01T00:00:00"

    def __init__(self):
        self.azzerato = False

    def reset_usage(self):
        self.azzerato = True
        self.usage_last_reset = "2026-08-11T00:00:00"


def _corpo(risposta):
    return json.loads(risposta.body.decode("utf-8"))


def _chiama(handler, app):
    return asyncio.run(handler(_Req(app)))


# ── senza runner: si dichiara, non si sbaglia ─────────────────────────────


def test_senza_runner_risponde_200_e_dichiara_che_non_si_misura():
    r = _chiama(handle_usage, {"chat_via_subscription": True})
    assert r.status == 200, (
        "503 dice «riprova» su un fatto permanente della configurazione: e' "
        "cosi' che una pagina viva e' diventata un vicolo cieco"
    )
    corpo = _corpo(r)
    assert corpo["misurata"] is False
    assert corpo["motivo"] == "abbonamento"
    assert "non si misurano" in corpo["messaggio"]


def test_i_contatori_restano_null_e_non_zero():
    corpo = _corpo(_chiama(handle_usage, {"chat_via_subscription": True}))
    for campo in ("total_requests", "input_tokens", "output_tokens",
                  "total_tokens", "cost_usd", "cost_eur",
                  "rate_limit_errors", "last_reset"):
        assert corpo[campo] is None, (
            f"{campo} a 0 affermerebbe «misurato, e non hai consumato niente»: "
            "e' lo stesso difetto a tre stati che l'archivio della casa evita"
        )


def test_il_motivo_distingue_abbonamento_da_nessun_provider():
    """Due assenze diverse, due frasi diverse: chi non ha configurato niente
    deve leggere «configura», non «l'abbonamento non espone i token»."""
    abbonamento = _corpo(_chiama(handle_usage, {"chat_via_subscription": True}))
    vuoto = _corpo(_chiama(handle_usage, {}))
    assert abbonamento["motivo"] == "abbonamento"
    assert vuoto["motivo"] == "nessun_provider"
    assert abbonamento["messaggio"] != vuoto["messaggio"]
    assert "provider" in vuoto["messaggio"].lower()


def test_azzerare_un_contatore_inesistente_e_un_conflitto_non_un_guasto():
    r = _chiama(handle_reset_usage, {"chat_via_subscription": True})
    assert r.status == 409
    corpo = _corpo(r)
    assert corpo["reset"] is False
    assert corpo["misurata"] is False
    assert corpo["messaggio"]


# ── col runner: niente cambia, e si dichiara che SI misura ────────────────


def test_col_runner_i_numeri_ci_sono_e_misurata_e_vero():
    corpo = _corpo(_chiama(handle_usage, {"llm_router": _RunnerFinto()}))
    assert corpo["misurata"] is True
    assert corpo["total_requests"] == 42
    assert corpo["input_tokens"] == 1200
    assert corpo["output_tokens"] == 800
    assert corpo["total_tokens"] == 2000
    assert corpo["cost_usd"] == 2.0
    assert corpo["cost_eur"] > 0
    assert corpo["last_reset"] == "2026-07-01T00:00:00"


def test_col_runner_il_reset_azzera_davvero():
    runner = _RunnerFinto()
    r = _chiama(handle_reset_usage, {"llm_router": runner})
    assert r.status == 200
    assert runner.azzerato is True
    assert _corpo(r)["reset"] is True
