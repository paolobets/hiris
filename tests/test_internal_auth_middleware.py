import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import CasaFinta

from hiris.app.api.middleware_internal_auth import _is_supervisor_ingress
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.server import create_app
from tests._casa_sintetica import synthetic_inputs

#: La persona che entra dall'ingress, come la manda `config/auth/list`: attiva
#: e nel gruppo degli amministratori (`HAClient.ADMIN_GROUP`).
ADMIN_ROW = {"id": "u-admin", "name": "Amministratrice", "is_owner": False,
             "is_active": True, "system_generated": False,
             "group_ids": ["system-admin"]}


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
    # Dal 27/09/2026 dietro l'ingress c'e' il cancello al confine (spec
    # 2026-09-27 §3): la persona che entra qui e' un'amministratrice, perche'
    # queste prove guardano la STRADA, non la lista di ammissione
    # (`tests/test_admission.py`). La casa e' quella finta: il ruolo lo legge
    # il client vero da `config/auth/list`.
    app["ha_client"] = CasaFinta(synthetic_inputs(), answers={
        "config/auth/list": lambda extra: [ADMIN_ROW]})
    app["chat_settings"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    # on_startup is cleared below, so wire the CR-1 trusted-CIDR list manually.
    # Default 172.30.32.0/23 does NOT include the test client's loopback IP, so
    # X-Ingress-Path alone must not bypass auth (that is the CR-1 fix).
    # L'indirizzo esatto del proxy: e' cio' che in produzione
    # `reti_di_fiducia` risolve dal nome «supervisor» (reperto A-2).
    #
    # `is None`, non `or` (reperto T-14, 03/10/2026): con `or` un elenco VUOTO
    # diventava in silenzio l'indirizzo del proxy, e nessuna prova poteva
    # chiedere al confine cosa fa quando l'avvio non si fida di nessuno --
    # proprio il caso che l'avvio produce quando le opzioni sono tutte
    # sbagliate (`server.py`, «nessuna rete è fidata»).
    app["supervisor_ingress_cidrs"] = (
        ["172.30.32.2/32"] if cidrs is None else cidrs)
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
        _make_app(tmp_path, cidrs=["127.0.0.1/32", "::1/128"])
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

    assert "Servizi" in corpo["error"]
    assert "accoppiare" in corpo["error"]


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
    client_trust_loopback
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
                 "X-Remote-User-Id": "u-admin"},
    )
    assert resp.status == 200
    # Il ruolo l'ha detto Home Assistant: il cancello l'ha chiesto davvero.
    house = client_trust_loopback.app["ha_client"]
    assert ("config/auth/list", None) in house.calls


@pytest.mark.asyncio
async def test_a2_un_indirizzo_che_non_e_il_proxy_non_passa(client):
    """**Il reperto A-2.** Intestazione giusta, e un indirizzo che non e'
    quello del proxy: non passa.

    `client` si fida solo di `172.30.32.2/32` -- cio' che in produzione
    `reti_di_fiducia` risolve dal nome «supervisor» -- e la suite chiama da
    loopback.

    Qui fino al 03/10/2026 si dichiarava «mutazione ESEGUITA: rimessa la rete
    `/23` fra quelle fidate -- rossa». Rieseguita il 03/10/2026: resta
    VERDE, perche' il loopback non sta nemmeno nella `/23`. Il vicino nella
    rete Docker, che e' il caso di A-2, lo guarda
    `test_a_neighbour_in_the_docker_network_is_not_the_proxy`."""
    resp = await client.get(
        "/api/health", headers={"X-Ingress-Path": "/api/hassio_ingress/hiris"})

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
    client_trust_loopback
):
    """Real Supervisor format /api/hassio_ingress/<random-token>/ from a trusted
    source, con la sessione che il Supervisor riconosce (A-2), passa."""
    resp = await client_trust_loopback.get(
        "/api/health",
        headers={"X-Ingress-Path": "/api/hassio_ingress/AbCdEf123-XyZ_456/",
                 "X-Remote-User-Id": "u-admin"},
    )
    assert resp.status == 200


def _ingress_request_from(remote: str, trusted: list[str]):
    """Una richiesta d'ingress che arriva da `remote`.

    Il client di prova chiama sempre da loopback, e il loopback non sta in
    nessuna rete di Docker: per guardare il confine dall'indirizzo di un
    vicino serve una richiesta costruita, col suo indirizzo sorgente."""
    app = web.Application()
    app["supervisor_ingress_cidrs"] = trusted
    transport = MagicMock()
    transport.get_extra_info = MagicMock(
        side_effect=lambda key, default=None: (
            (remote, 40000) if key == "peername" else default))
    return make_mocked_request(
        "GET", "/api/health", app=app, transport=transport,
        headers={"X-Ingress-Path": "/api/hassio_ingress/hiris"})


@pytest.mark.asyncio
async def test_the_proxy_address_is_trusted():
    """Il controllo delle due prove sotto: la richiesta costruita porta
    davvero il suo indirizzo fino al confine. Senza questa, una richiesta che
    arrivasse senza indirizzo sarebbe rifiutata per un'altra ragione, e le
    prove sotto sarebbero verdi (o attese rosse) per niente."""
    request = _ingress_request_from("172.30.32.2", ["172.30.32.2/32"])

    assert await _is_supervisor_ingress(request) is True


@pytest.mark.asyncio
async def test_a_neighbour_in_the_docker_network_is_not_the_proxy():
    """**Il reperto A-2, dall'indirizzo giusto.** Un add-on vicino vive nella
    rete Docker del Supervisor e puo' scrivere l'intestazione: se l'avvio si
    fida del solo indirizzo del proxy, il vicino resta fuori.

    Mutazione ESEGUITA il 03/10/2026: `_supervisor_cidrs` che torna sempre
    la rete di fabbrica (la `/23`) -- rossa (`assert True is False`),
    mentre `test_a2_un_indirizzo_che_non_e_il_proxy_non_passa` resta verde."""
    request = _ingress_request_from("172.30.32.5", ["172.30.32.2/32"])

    assert await _is_supervisor_ingress(request) is False


@pytest.mark.asyncio
async def test_an_empty_trusted_list_trusts_no_network():
    """**Il reperto T-14: la prova dice cio' che serve, non cio' che c'e'.**

    Quando ogni voce di `supervisor_ingress_cidr` e' sbagliata, l'avvio scrive
    `[]` e dichiara nel registro che «NESSUNA rete è fidata e ogni richiesta
    dovrà autenticarsi» (`server.py`, accanto a `perimetro_fidato`). Il
    confine pero' ripiega sulla `/23`: scrivere male le opzioni ALLARGA il
    perimetro, che e' esattamente cio' che `api/ingresso.py::reti_fidate`
    dice di non fare.

    S-15 e' chiuso il 07/10/2026 (Tappa 7, Task 8): l'`xfail` e' uscito e
    la prova e' verde.

    Mutazione ESEGUITA il 07/10/2026: rimesso il ripiego in
    `_supervisor_cidrs` (`... or ["172.30.32.0/23"]`) -- rossa
    (`assert True is False`)."""
    request = _ingress_request_from("172.30.32.5", [])

    assert await _is_supervisor_ingress(request) is False
