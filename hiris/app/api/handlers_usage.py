"""I consumi -- e il caso, sempre piu' raro, in cui non c'e' niente da misurare.

Questa vista ha DUE risposte vere, non una risposta e un guasto.

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
    dominio, e i fatti di dominio stanno nel corpo della risposta.

Il campo che porta la distinzione e' `measured`. I contatori restano nel corpo
ma valgono `null`, non `0`: `0` affermerebbe «misurato, e non hai consumato
niente» -- lo stesso difetto a tre stati che tutto l'archivio della casa e'
stato scritto per non commettere.

**Dalla fetta «i consumi, per modello» (22/08/2026) il caso non-misurato e'
UNO SOLO**: non e' mai stato usato niente e non c'e' niente che possa
rispondere. Il ramo «abbonamento» e' uscito con la sua frase: l'abbonamento
adesso si misura -- i token, non il costo del turno, che non esiste -- e ha
una sezione sua nella pagina.

E `POST /api/usage/reset` non risponde piu' 409: azzerare non cancella piu'
niente, sposta un'ancora, e un'ancora c'e' sempre.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime

from aiohttp import web

from ..config import EUR_RATE as _EUR_RATE

_NO_PROVIDER_MSG = (
    "Nessun provider AI configurato e nessun consumo mai registrato: non c'è "
    "ancora nessun modello che risponda, quindi non c'è nessun consumo da "
    "misurare. Configura una chiave API o il token dell'abbonamento nelle "
    "opzioni dell'add-on."
)

# Quanti giorni di storia si danno quando nessuno chiede un intervallo.
_HISTORY_DAYS = 30


def _euro(usd):
    """`None` resta `None`. Uno zero al suo posto sarebbe la bugia della fetta."""
    return None if usd is None else round(usd * _EUR_RATE, 6)


def _can_respond(app) -> bool:
    """Se esiste qualcuno che potrebbe consumare, adesso.

    Con un provider configurato uno ZERO e' un fatto misurato -- «non hai
    ancora consumato niente» -- e non un'assenza di misura. E' la distinzione
    che rende `measured: false` un caso raro invece che la normalita'.
    """
    return bool(app.get("llm_router") or app.get("claude_runner")
                or app.get("ponte_attivo"))


def _unmeasured() -> dict:
    return {
        "measured": False,
        "reason": "nessun_provider",
        "message": _NO_PROVIDER_MSG,
        # `null`, non `0`: vedi la docstring del modulo.
        "total_requests": None,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cost_usd": None,
        "cost_eur": None,
        "partial_cost": False,
        "rate_limit_errors": None,
        "last_reset": None,
        "sections": [],
    }


def _iso(ts: float) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat() if ts else None


def _model_out(m: dict) -> dict:
    """Una riga di modello come la legge la pagina. `token_in` resta PURO.

    A sinistra il nome HTTP, a destra il nome della COLONNA (`usage/store.py`):
    e' il confine, e la legge del progetto lo vuole cosi' -- il dominio in
    italiano, il confine nella lingua del sistema esterno, che qui e' il
    browser. Il database non si tocca: `richieste` resta una colonna e diventa
    `requests` solo uscendo di qui.
    """
    return {
        "model": m["modello"],
        "requests": m["richieste"],
        "token_in": m["token_in"],
        "token_out": m["token_out"],
        "cache_read": m["cache_lettura"],
        "cache_write": m["cache_scrittura"],
        "cost_usd": m["costo_usd"],
        "cost_eur": _euro(m["costo_usd"]),
        "cost_state": m["costo_stato"],
        # Il doppione che questa fetta chiude: lo STESSO numero usciva come
        # `rate_limit_errors` in cima alla risposta e `errori_rate_limit`
        # dentro una sezione. Una cosa, un nome.
        "rate_limit_errors": m["errori_rate_limit"],
        "first_use": m["primo_uso"],
        "last_use": m["ultimo_uso"],
    }


def _bucket_out(b: dict) -> dict:
    """Un secchiello giornaliero come lo legge il grafico.

    **Esisteva come `{**b, ...}`, uno spread crudo della riga di archivio**, ed
    era il motivo per cui le colonne di `consumo_giorno` uscivano su HTTP coi
    loro nomi italiani senza che nessuno l'avesse deciso. Una rotta non deve
    versare fuori la forma della propria tabella senza saperlo: aggiungere una
    colonna la faceva comparire nella risposta da sola, e toglierne una la
    faceva sparire senza che niente diventasse rosso.

    Stessi nomi di `_model_out` -- e' lo stesso fatto, contato per giorno
    invece che per modello, e due nomi per la stessa quantita' sono il
    doppione che questa fetta e' venuta a togliere.
    """
    return {
        "requests": b["richieste"],
        "token_in": b["token_in"],
        "token_out": b["token_out"],
        "cache_read": b["cache_lettura"],
        "cache_write": b["cache_scrittura"],
        "rate_limit_errors": b["errori_rate_limit"],
        "cost_usd": b["costo_usd"],
        "cost_eur": _euro(b["costo_usd"]),
    }


async def handle_usage(request: web.Request) -> web.Response:
    store = request.app.get("consumi")
    if store is None or (store.empty() and not _can_respond(request.app)):
        return web.json_response(_unmeasured())

    # `?from=sempre` chiede la storia intera; senza parametro si conta
    # dall'ancora, che e' cio' che la pagina mostra per primo. Il parametro
    # esiste perche' l'interruttore «da ultimo azzeramento / da sempre» possa
    # davvero cambiare qualcosa: senza, sarebbe un pulsante che non fa niente.
    from_anchor = request.query.get("from") != "sempre"
    sections = store.sezioni(from_anchor=from_anchor)
    totals = store.totali(from_anchor=from_anchor)

    # `input_tokens` in cima e' INCLUSIVO della cache: e' la stessa quantita'
    # che la pagina e il riquadro della chat mostravano prima di questa fetta.
    # Nelle righe `token_in` sono invece i token PURI, perche' la cache ha due
    # tariffe sue ed e' il numero che dice se il prefisso sta lavorando.
    # Sommare qui la sola colonna pura farebbe crollare il totale, e
    # sembrerebbe una perdita di dati invece di un cambio di rappresentazione.
    input_tokens = (totals["token_in"] + totals["cache_lettura"]
                + totals["cache_scrittura"])
    # L'aiutante di `server.py` -- import locale per evitare il ciclo:
    # `server` importa GIA' `handle_usage` da questo modulo (riparazione-
    # impoverisce-brief.md, appendice punto 6). Prima di questa riga c'era
    # una quarta copia a mano della stessa domanda («dov'e' il fuso della
    # casa?»), con in piu' un primo ramo morto (`app["fuso_casa"]`, appendice
    # punto 7): nessun codice di produzione scriveva quella chiave, la
    # riempiva solo la finta di un test -- vedi `tests/test_usage_routes.py`.
    from ..server import _timezone_from_home_space_store
    timezone = _timezone_from_home_space_store(request.app.get("archivio_casa")) or ""

    return web.json_response({
        "measured": True,
        "total_requests": totals["richieste"],
        "input_tokens": input_tokens,
        "output_tokens": totals["token_out"],
        "total_tokens": input_tokens + totals["token_out"],
        "cost_usd": round(totals["costo_usd"], 6),
        "cost_eur": _euro(totals["costo_usd"]),
        # Se anche un solo modello e' senza prezzo, il totale NON e' il costo:
        # e' un pavimento, e la pagina lo scrive con un «>=».
        "partial_cost": totals["costo_parziale"],
        "rate_limit_errors": totals["errori_rate_limit"],
        "last_reset": _iso(store.anchor()),
        "timezone": timezone or "UTC",
        "timezone_known": bool(timezone),
        "sections": [{
            "provider": s["provider"],
            "label": s["etichetta"],
            "note": s["nota"],
            "requests": s["richieste"],
            "token_in": s["token_in"],
            "token_out": s["token_out"],
            "cache_read": s["cache_lettura"],
            "cache_write": s["cache_scrittura"],
            # `None` attraversa: una sezione senza nessun costo noto -- il
            # ponte -- non deve uscire di qui con uno zero che afferma.
            "cost_usd": None if s["costo_usd"] is None else round(s["costo_usd"], 6),
            "cost_eur": _euro(s["costo_usd"]),
            "partial_cost": s["costo_parziale"],
            "models": [_model_out(m) for m in s["modelli"]],
        } for s in sections],
    })


async def handle_usage_history(request: web.Request) -> web.Response:
    """`GET /api/usage/history?from=&to=` -- i secchielli giornalieri, per il grafico.

    Ha una rotta SUA perche' e' una domanda diversa, con parametri suoi: un
    oggetto che si sa interrogare da solo (fondamenta n.4), non un allegato
    del riepilogo. E soprattutto perche' il riquadro della chat richiama
    `/api/usage` a intervalli: appesantirlo con trenta giorni di serie
    storica farebbe pagare a ogni giro una domanda che la chat non fa.
    """
    store = request.app.get("consumi")
    if store is None:
        return web.json_response({"days": [], "from": "", "to": ""})

    today = datetime.fromtimestamp(time.time(), UTC)
    to = request.query.get("to") or today.strftime("%Y-%m-%d")
    since = request.query.get("from") or (
        datetime.fromtimestamp(time.time() - _HISTORY_DAYS * 86400, UTC)
        .strftime("%Y-%m-%d"))

    days = []
    for g in store.storia(da=since, a=to):
        days.append({
            "day": g["giorno"],
            "per_provider": {
                name: _bucket_out(data) for name, data in g["per_provider"].items()
            },
        })
    return web.json_response({"days": days, "from": since, "to": to})


async def handle_reset_usage(request: web.Request) -> web.Response:
    """«Riparti da adesso»: sposta l'ancora. Non cancella una riga.

    Il `409` di prima -- «azzerare un contatore che non esiste e' una
    richiesta in conflitto con lo stato della risorsa» -- e' uscito con la
    ragione che lo giustificava: un'ancora c'e' sempre.
    """
    store = request.app.get("consumi")
    if store is None:
        body = _unmeasured()
        body["deleted"] = False
        return web.json_response(body, status=409)
    when = store.sposta_anchor(time.time())
    return web.json_response({"last_reset": _iso(when), "deleted": False})
