import os

import pytest_asyncio

# Allow unauthenticated non-ingress requests in the test suite.
# The middleware deny-by-default is for production safety; tests hit the server
# directly without HA Supervisor Ingress forwarding X-Ingress-Path.
os.environ.setdefault("HIRIS_ALLOW_NO_TOKEN", "1")

# Disable CSRF middleware in the test suite: tests use bare TestClient that
# does not inject X-Requested-With (real browsers do, via fetch()).
os.environ.setdefault("HIRIS_ALLOW_NO_CSRF", "1")


# --- Fingere l'ingress del Supervisor --------------------------------------
#
# Qui, per poche ore del 22/09/2026, e' vissuto un Supervisor finto che
# rispondeva alla verifica della sessione. Quella verifica e' uscita: la rotta
# `/ingress/validate_session` e' riservata a Home Assistant Core e risponde 403
# a un add-on -- il proprietario e' rimasto chiuso fuori dal proprio pannello
# finche' la 3.60.1 non l'ha tolta.
#
# **Fingere l'ingress adesso vuol dire una cosa sola**: arrivare dall'indirizzo
# di cui l'app si fida, che ogni prova dichiara in
# `app["supervisor_ingress_cidrs"]`. Non serve nessuna finta, e non averne una
# e' meglio: una finta accomodante renderebbe verde proprio il difetto che A-2
# esiste per chiudere.


def credenziale_ponte(app, segreto: str) -> dict:
    """Mette nel contenitore una credenziale di TURNO col segreto dato, e torna
    le intestazioni che il sottoprocesso `claude` manderebbe.

    Dal 22/09/2026 il segreto condiviso non apre piu' niente (reperto A-5): chi
    finge il ponte deve fingere cio' che il ponte ha davvero, cioe' una
    credenziale che vive un turno.

    Il vero `conia` sceglie lui il segreto -- 256 bit da `secrets` -- e qui
    serve conoscerlo in anticipo per scriverlo in una costante. La riga
    d'asserzione in fondo **pinna la forma contro la deriva**: se `conia` e
    `riconosci` cambiassero contratto, questa finta se ne accorgerebbe invece
    di restare verde imitando un vecchio contratto.
    """
    import time

    from hiris.app.api import credenziali

    if app.get("credenziali") is None:
        credenziali.prepara_credenziali(app)
    adesso = time.time()
    app["credenziali"][segreto] = {"mestiere": "ponte", "scade": adesso + 3600}
    assert credenziali.riconosci(app["credenziali"], segreto, adesso=adesso), (
        "la forma della credenziale finta non combacia più con quella vera"
    )
    return {"X-HIRIS-Internal-Token": segreto}


@pytest_asyncio.fixture
async def ponte_produzione(aiohttp_client, tmp_path, monkeypatch):
    """L'app VERA col confine acceso, come il ponte la trova in produzione.

    Le due valvole della suite (`HIRIS_ALLOW_NO_TOKEN`, `HIRIS_ALLOW_NO_CSRF`)
    sono TOLTE: con quelle accese le prove che usano questa fixture
    passerebbero anche col guasto in piedi.

    Viveva in `tests/test_internal_token.py`, uscito il 22/09/2026 insieme al
    segreto condiviso che quel file sorvegliava. Qui e' la stessa fixture senza
    il blocco d'avvio del token, che non esiste piu': la credenziale del ponte
    si conia, non si legge da un'opzione.

    Torna `(client, coda, app, intestazioni)` — le intestazioni sono quelle di
    una credenziale di turno viva, cioe' cio' che il worker manda davvero.
    """
    from unittest.mock import AsyncMock, MagicMock

    from hiris.app import server
    from hiris.app.chat_settings import ChatSettings
    from hiris.app.reasoning.queue import ReasoningQueue

    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    monkeypatch.setenv("HIRIS_DATA_DIR", str(tmp_path))

    app = server.create_app()
    finto_ha = AsyncMock()
    finto_ha.start = AsyncMock()
    finto_ha.stop = AsyncMock()
    finto_ha.add_state_listener = MagicMock()
    finto_ha.start_websocket = AsyncMock()
    app["ha_client"] = finto_ha
    app["chat_settings"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    # La sorgente del client di test e' un loopback, che NON sta nella rete del
    # Supervisor: nessun bypass dell'ingress, si passa per forza dalla
    # credenziale. E' il caso del worker del ponte, che gira nel container.
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app.on_startup.clear()
    app.on_cleanup.clear()

    intestazioni = credenziale_ponte(app, "credenziale-di-turno-della-prova")
    coda = ReasoningQueue(str(tmp_path / "reasoning.db"))
    app["reasoning_queue"] = coda
    client = await aiohttp_client(app)
    try:
        yield client, coda, app, intestazioni
    finally:
        coda.close()


def servizio_approvato(app, ruolo: str, nome: str = "retropanel",
                       specie: str = "luogo"):
    """Un servizio **accoppiato davvero** nell'archivio `app["servizi"]`: si
    presenta e viene approvato col ruolo dato. Torna la chiave privata e la
    pubblica, che e' la sua identita'."""
    import base64
    import time

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    privata = Ed25519PrivateKey.generate()
    pubblica = base64.b64encode(
        privata.public_key().public_bytes_raw()).decode("ascii")
    adesso = time.time()
    app["servizi"].presenta(nome=nome, chiave=pubblica, indirizzo="192.168.1.31",
                            now_ts=adesso)
    app["servizi"].approva(pubblica, ruolo=ruolo, specie=specie, now_ts=adesso)
    return privata, pubblica


def firma(privata, pubblica, method: str, path: str, body: bytes = b"") -> dict:
    """Le intestazioni di una richiesta firmata, col contratto vero
    (`canali.materia_firmata`). `path` e' il percorso come il server lo vede,
    cioe' decodificato."""
    import base64
    import secrets
    import time

    from hiris.app.api import canali

    momento = time.time()
    unico = secrets.token_hex(8)
    segno = base64.b64encode(privata.sign(
        canali.materia_firmata(method, path, momento, unico, body))).decode("ascii")
    return {"X-HIRIS-Servizio": pubblica, "X-HIRIS-Momento": str(int(momento)),
            "X-HIRIS-Unico": unico, "X-HIRIS-Firma": segno}
