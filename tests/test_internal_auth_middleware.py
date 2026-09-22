from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.server import create_app


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


@pytest.fixture(autouse=True)
def confine_vero(monkeypatch):
    """La suite tiene accesa `HIRIS_ALLOW_NO_TOKEN`, che spegne il confine.

    In QUESTO file non si puo': il confine e' il soggetto, e col confine
    spento ogni prova sarebbe verde senza provare niente — il difetto n.1 di
    questo progetto. Misurato il 22/09/2026 togliendo il ramo del segreto
    condiviso: cinque prove di questo file sono diventate verdi per la ragione
    sbagliata, cioe' rispondevano 200 invece di 401 e nessuno se ne
    accorgeva.
    """
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)


def _make_app(tmp_path, cidrs=None):
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    app["ha_client"] = mock_ha
    app["chat_settings"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    # on_startup is cleared below, so wire the CR-1 trusted-CIDR list manually.
    # Default 172.30.32.0/23 does NOT include the test client's loopback IP, so
    # X-Ingress-Path alone must not bypass auth (that is the CR-1 fix).
    app["supervisor_ingress_cidrs"] = cidrs or ["172.30.32.0/23"]
    app.on_startup.clear()
    app.on_cleanup.clear()
    return app


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    """Un client qualunque: la sua sorgente e' loopback, che NON sta nella
    rete del Supervisor. Nessuna credenziale, quindi nessuna strada."""
    return await aiohttp_client(_make_app(tmp_path))


@pytest_asyncio.fixture
async def client_trust_loopback(aiohttp_client, tmp_path):
    """Client la cui rete fidata comprende il loopback della suite, cosi' una
    richiesta di ingress genuina (intestazione + indirizzo fidato + sessione
    che il Supervisor riconosce) passa."""
    return await aiohttp_client(
        _make_app(tmp_path, cidrs=["127.0.0.0/8", "::1/128"])
    )


@pytest.mark.asyncio
async def test_senza_NESSUNA_credenziale_non_si_entra(client):
    """**Il confine, dal 22/09/2026.** Tre strade e nient'altro: la firma di
    un servizio approvato, l'ingress con la sessione verificata, la
    credenziale di turno del ponte. Chi non ne ha nessuna resta fuori.

    Mutazione ESEGUITA: un `return await handler(request)` in fondo al confine
    -- rossa."""
    resp = await client.get("/api/health")

    assert resp.status == 401


@pytest.mark.asyncio
async def test_un_SEGRETO_CONDIVISO_non_apre_piu_niente(client):
    """Il reperto A-5 chiuso: per una fetta il confine ha accettato «la firma
    oppure il token», perche' gateway e Retro Panel vivevano in due repository
    separati. La misura ha deciso quando chiudere — il registro ha smesso di
    nominare chiunque non firmasse.

    Mutazione ESEGUITA: rimesso il ramo `hmac.compare_digest` -- rossa."""
    resp = await client.get(
        "/api/health", headers={"X-HIRIS-Internal-Token": "qualunque-segreto"})

    assert resp.status == 401


@pytest.mark.asyncio
async def test_e_il_rifiuto_dice_COME_SI_ENTRA(client):
    """Un'integrazione non aggiornata trova una porta chiusa: senza una frase
    che dica dove andare, chi la mantiene passa il pomeriggio nel registro.

    Mutazione: rispondere «unauthorized» e basta -- rossa."""
    resp = await client.get(
        "/api/health", headers={"X-HIRIS-Internal-Token": "vecchio"})
    corpo = await resp.json()

    assert "Servizi" in corpo["errore"]
    assert "accoppiare" in corpo["errore"]


@pytest.mark.asyncio
async def test_una_credenziale_di_TURNO_apre(client, tmp_path):
    """La strada del ponte: HIRIS che chiama se stesso su `127.0.0.1` per
    prendere e consegnare i turni. Vive dieci minuti e muore col turno.

    Mutazione: non riconoscere le credenziali effimere -- rossa (il ponte si
    spegne)."""
    from conftest import credenziale_ponte

    intestazioni = credenziale_ponte(client.app, "segreto-di-turno")
    resp = await client.get("/api/health", headers=intestazioni)

    assert resp.status == 200


@pytest.mark.asyncio
async def test_ingress_path_from_trusted_source_bypasses_auth(
    client_trust_loopback, supervisor_ingress
):
    """Genuine ingress bypasses the token check.

    Dal reperto A-2 (22/09/2026) «genuine» vuol dire TRE cose e non due:
    l'intestazione, l'indirizzo sorgente fidato, **e il biscotto di sessione
    che il Supervisor riconosce**. Le prime due le puo' avere anche un add-on
    vicino, che nella rete del Supervisor ci vive.
    """
    resp = await client_trust_loopback.get(
        "/api/health",
        headers={"X-Ingress-Path": "/api/hassio_ingress/hiris",
                 "Cookie": "ingress_session=sessione-che-il-supervisor-conosce"},
    )
    assert resp.status == 200


@pytest.mark.asyncio
async def test_a2_ingress_senza_sessione_valida_non_passa(client_trust_loopback):
    """**Il reperto A-2.** Intestazione giusta, indirizzo fidato, e nessuna
    sessione che il Supervisor conosca: non passa.

    E' il caso dell'add-on vicino, che sta nella rete del Supervisor per
    costruzione -- e se il tunnel che pubblica la casa gira come add-on, il
    caso normale, e' il suo indirizzo.

    Mutazione ESEGUITA: tolta la verifica della sessione dal confine -- rossa
    (200 invece di 401)."""
    resp = await client_trust_loopback.get(
        "/api/health",
        headers={"X-Ingress-Path": "/api/hassio_ingress/hiris",
                 "Cookie": "ingress_session=rubata-mai-esistita"},
    )
    assert resp.status == 401


@pytest.mark.asyncio
async def test_cr1_ingress_path_from_untrusted_ip_does_not_bypass(client):
    """CR-1: a forged X-Ingress-Path from a non-Supervisor source IP must NOT
    bypass auth — it still requires the internal token (401)."""
    resp = await client.get(
        "/api/health",
        headers={"X-Ingress-Path": "/api/hassio_ingress/anything"},
    )
    assert resp.status == 401


@pytest.mark.asyncio
async def test_un_ingress_FALSIFICATO_non_scavalca_la_credenziale_vera(client):
    """Una richiesta da un indirizzo non fidato che porta una credenziale VERA
    passa dal ramo della credenziale, non dal bypass dell'ingress: il token
    di percorso falsificato non le da' niente in piu' e non le toglie niente.

    Prima questa prova usava il segreto condiviso; dal 22/09/2026 la
    credenziale vera e' quella di turno.

    Mutazione: far decidere all'intestazione invece che alla credenziale --
    rossa."""
    from conftest import credenziale_ponte

    resp = await client.get(
        "/api/health",
        headers={
            "X-Ingress-Path": "/api/hassio_ingress/forged",
            **credenziale_ponte(client.app, "segreto-di-turno-2"),
        },
    )
    assert resp.status == 200


@pytest.mark.asyncio
async def test_ingress_path_empty_string_does_not_bypass(client):
    """An empty X-Ingress-Path must not bypass auth."""
    resp = await client.get(
        "/api/health",
        headers={"X-Ingress-Path": ""},
    )
    assert resp.status == 401


@pytest.mark.asyncio
async def test_ingress_path_arbitrary_value_does_not_bypass(client):
    """X-Ingress-Path with arbitrary value (not Supervisor format) must not bypass."""
    resp = await client.get(
        "/api/health",
        headers={"X-Ingress-Path": "/foo/bar"},
    )
    assert resp.status == 401


@pytest.mark.asyncio
async def test_ingress_path_real_supervisor_token_pattern_passes(
    client_trust_loopback, supervisor_ingress
):
    """Real Supervisor format /api/hassio_ingress/<random-token>/ from a trusted
    source, con la sessione che il Supervisor riconosce (A-2), passa."""
    resp = await client_trust_loopback.get(
        "/api/health",
        headers={"X-Ingress-Path": "/api/hassio_ingress/AbCdEf123-XyZ_456/",
                 "Cookie": "ingress_session=sessione-che-il-supervisor-conosce"},
    )
    assert resp.status == 200
