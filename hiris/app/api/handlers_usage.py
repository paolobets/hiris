"""I consumi -- e il caso, legittimo, in cui non c'e' niente da misurare.

Questa vista ha DUE risposte vere, non una risposta e un guasto.

Quando un runner a consumo esiste (API Claude/OpenAI/OpenRouter, o Ollama),
i contatori esistono e si leggono. Quando NON esiste -- l'add-on gira
sull'abbonamento Claude, o non ha ancora nessun provider configurato --
i consumi non sono azzerati: **non vengono misurati affatto**, perche' non
c'e' nessun contatore da leggere. E' una proprieta' della configurazione, non
un servizio caduto.

Perche' 200 e non 503 (scelta della fetta "fix pre-UAT", voce C-1):

  - il 503 e' semantica di trasporto, e dice «riprova»: un fatto permanente
    della configurazione descritto come indisponibilita' temporanea invita
    ogni chiamante a ripetere per sempre una domanda che non avra' mai una
    risposta diversa. E' esattamente quello che succedeva: il riquadro
    "Utilizzo" della chat ripeteva la chiamata ogni 30 secondi;
  - un errore HTTP viene raccolto dai rami `!r.ok`/`catch` che ogni frontend
    ha gia' scritti per i guasti di rete, e li' diventa una frase generica --
    da cui la pagina #/usage che diceva soltanto «Errore caricamento consumi.»
    su una configurazione perfettamente sana;
  - il fatto «i consumi non si misurano su questo percorso» e' un fatto di
    dominio, e i fatti di dominio stanno nel corpo della risposta, dove si
    possono dichiarare per esteso e mostrare all'utente parola per parola.

Il campo che porta la distinzione e' `misurata`. I contatori restano nel
corpo ma valgono `null`, non `0`: `0` affermerebbe «misurato, e non hai
consumato niente» -- lo stesso difetto a tre stati che tutto l'archivio
della casa e' stato scritto per non commettere.

`POST /api/usage/reset` risponde invece **409**: azzerare un contatore che
non esiste non e' una richiesta che il servizio non riesce a servire, e' una
richiesta in conflitto con lo stato della risorsa. Il frontend, in questo
stato, non mostra affatto il pulsante.
"""
from aiohttp import web
from ..config import EUR_RATE as _EUR_RATE

# La frase che l'utente legge. Vive qui, accanto al fatto, e non in tre
# frontend che potrebbero divergere: la pagina #/usage e il riquadro della
# chat mostrano ENTRAMBI questa stringa, non una propria parafrasi.
_MSG_ABBONAMENTO = (
    "Sul percorso abbonamento i consumi non si misurano: la chat gira "
    "sull'abbonamento Claude, che non espone né i token né il costo della "
    "singola risposta. Non è un consumo azzerato, è un consumo che non "
    "viene misurato."
)
_MSG_NESSUN_PROVIDER = (
    "Nessun provider AI configurato: non c'è ancora nessun modello che "
    "risponda, quindi non c'è nessun consumo da misurare. Configura una "
    "chiave API o il token dell'abbonamento nelle opzioni dell'add-on."
)


def _non_misurata(app) -> dict:
    """Il corpo che dichiara l'indisponibilità della misura, col suo perché."""
    if app.get("chat_via_subscription"):
        motivo, messaggio = "abbonamento", _MSG_ABBONAMENTO
    else:
        motivo, messaggio = "nessun_provider", _MSG_NESSUN_PROVIDER
    return {
        "misurata": False,
        "motivo": motivo,
        "messaggio": messaggio,
        # `null`, non `0`: vedi la docstring del modulo.
        "total_requests": None,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cost_usd": None,
        "cost_eur": None,
        "rate_limit_errors": None,
        "last_reset": None,
    }


async def handle_usage(request: web.Request) -> web.Response:
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response(_non_misurata(request.app))

    inp = getattr(runner, "total_input_tokens", 0)
    out = getattr(runner, "total_output_tokens", 0)
    reqs = getattr(runner, "total_requests", 0)
    cost_usd = getattr(runner, "total_cost_usd", 0.0)
    rate_limit_errors = getattr(runner, "total_rate_limit_errors", 0)
    cost_eur = cost_usd * _EUR_RATE

    return web.json_response({
        "misurata": True,
        "total_requests": reqs,
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "cost_usd": round(cost_usd, 6),
        "cost_eur": round(cost_eur, 6),
        "rate_limit_errors": rate_limit_errors,
        "last_reset": getattr(runner, "usage_last_reset", None),
    })


async def handle_reset_usage(request: web.Request) -> web.Response:
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        corpo = _non_misurata(request.app)
        corpo["reset"] = False
        return web.json_response(corpo, status=409)
    runner.reset_usage()
    return web.json_response({"reset": True, "last_reset": runner.usage_last_reset})
