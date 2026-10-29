"""Chi entra, per le prove che montano un gestore senza il cancello vero.

Dal 29/10/2026 (Fase S, S.3) le pagine che si adattano a chi guarda
(`soffitto.restricted_person`) chiedono il gesto `amministrare` al soffitto
della richiesta: una richiesta che non dice chi e' -- niente `auth_via`, niente
ruolo -- e' una persona ignota, che legge e basta, e riceve la lettura
ristretta. Fino ad allora la riceveva solo chi arrivava dall'ingress, e una
richiesta senza `auth_via` vedeva tutto. Le prove che vogliono la pagina
dell'amministratore lo dicono qui, una volta sola.
"""
from aiohttp import web

from hiris.app.chat_thread import new_subject

#: Le chiavi che il cancello vero (`middleware_internal_auth`) lascia sulla
#: richiesta di una persona che amministra.
AMMINISTRATORE = {
    "auth_via": "ingress",
    "ruolo": "amministratore",
    "soggetto": new_subject("persona", ident="u-admin", nome="Admin"),
}


@web.middleware
async def as_admin(request, handler):
    """Ogni richiesta entra come una persona che amministra."""
    for key, value in AMMINISTRATORE.items():
        request[key] = value
    return await handler(request)
