"""Il SOGGETTO di una richiesta (invariante I-1, sprint sicurezza 21/09/2026).

Fino a oggi HIRIS sapeva da quale **porta** arriva una richiesta -- `origine` vale
«chat», «pagina», «schedulatore» -- e non sapeva **chi** la fa. Erano nomi di
pezzi di codice, non di persone: la cronaca registrava fedelmente il percorso e
non poteva rispondere a «chi ha spento la luce».

Il pezzo che mancava ce l'ha gia' Home Assistant. Verificato il 21/09 sul
sorgente del Supervisor (`supervisor/api/ingress.py`): il proxy aggiunge
`X-Remote-User-Id`, `X-Remote-User-Name` e `X-Remote-User-Display-Name`, presi da
`session_data.user`, e **filtra via gli stessi header in ingresso** prima di
aggiungere i propri.

**Da cui la regola che questo file custodisce**: quegli header si credono **solo**
quando la richiesta e' passata dall'ingress del Supervisor. Su ogni altra strada
-- la porta di sviluppo, un add-on vicino, un tunnel -- sono testo che il
chiamante ha scritto, e crederli sarebbe consegnare l'identita' a chiunque sappia
scrivere un'intestazione.

E **«non so chi sei» non e' «sei il proprietario»**: un ingress senza identita'
produce un soggetto ANONIMO, non l'assenza di soggetto, perche' un campo vuoto e
un campo mancante si confondono mentre due parole diverse no.
"""
import pytest

from hiris.app.api.middleware_internal_auth import internal_auth_middleware

_INGRESS = "/api/hassio_ingress/abc123/"
_INTESTAZIONI = {"X-Remote-User-Id": "u-42",
                 "X-Remote-User-Name": "paolo",
                 "X-Remote-User-Display-Name": "Paolo Bets"}


class _Richiesta(dict):
    """Una richiesta finta, quanto basta al middleware."""

    def __init__(self, *, headers, remote, token=""):
        super().__init__()
        self.headers = headers
        self.remote = remote
        self.app = {"internal_token": token,
                    "supervisor_ingress_cidrs": ["172.30.32.0/23"]}


async def _passa(richiesta):
    visto = {}

    async def prosegui(r):
        visto["soggetto"] = r.get("soggetto")
        visto["auth_via"] = r.get("auth_via")
        return "ok"

    esito = await internal_auth_middleware(richiesta, prosegui)
    return esito, visto


@pytest.mark.asyncio
async def test_una_richiesta_di_ingress_porta_il_soggetto():
    """Il caso normale: il pannello dentro Home Assistant.

    Mutazione: non leggere gli header -- rossa (la cronaca resterebbe muta su
    chi, che e' tutto il punto di questo invariante).
    """
    _, visto = await _passa(_Richiesta(
        headers={"X-Ingress-Path": _INGRESS, **_INTESTAZIONI}, remote="172.30.32.2"))

    assert visto["auth_via"] == "ingress"
    assert visto["soggetto"]["id"] == "u-42"
    assert visto["soggetto"]["nome"] == "Paolo Bets"


@pytest.mark.asyncio
async def test_gli_stessi_header_FUORI_dall_ingress_non_si_credono():
    """**Il cuore di questo file.** Chi arriva dalla porta di sviluppo, o da un
    add-on vicino, puo' scrivere `X-Remote-User-Id` a mano: crederlo vorrebbe
    dire consegnare l'identita' del proprietario a chiunque sappia comporre
    un'intestazione.

    Mutazione ESEGUITA: leggere gli header prima di distinguere la strada --
    rossa.
    """
    _, visto = await _passa(_Richiesta(
        headers={"X-HIRIS-Internal-Token": "s3greto", **_INTESTAZIONI},
        remote="192.168.1.31", token="s3greto"))

    assert visto["auth_via"] == "token"
    assert visto["soggetto"]["id"] is None, (
        "un'intestazione scritta dal chiamante e' diventata un'identita'")
    assert visto["soggetto"]["specie"] == "integrazione"


@pytest.mark.asyncio
async def test_un_ingress_SENZA_identita_da_un_soggetto_anonimo_non_nessuno():
    """`X-Remote-User-Id` non e' garantito: con provider di autenticazione non
    nativi puo' mancare. Allora il soggetto esiste ed e' ANONIMO.

    Mutazione: lasciare `soggetto` a `None` -- rossa. Un campo mancante e un
    campo vuoto si confondono al primo lettore distratto; due parole diverse no.
    """
    _, visto = await _passa(_Richiesta(
        headers={"X-Ingress-Path": _INGRESS}, remote="172.30.32.2"))

    assert visto["soggetto"] is not None
    assert visto["soggetto"]["specie"] == "persona"
    assert visto["soggetto"]["id"] is None


@pytest.mark.asyncio
async def test_il_soggetto_dice_sempre_di_che_SPECIE_e():
    """Una persona di Home Assistant e una macchina che porta un token non si
    autenticano nello stesso modo e non possono avere lo stesso soffitto: la
    specie e' il primo fatto che serve a deciderlo, e c'e' sempre.

    Mutazione: togliere `specie` -- rossa (chi legge dovrebbe dedurla, e
    dedurla e' il modo in cui due strade diventano una per distrazione).
    """
    for intestazioni, remoto, token, specie in (
            ({"X-Ingress-Path": _INGRESS}, "172.30.32.2", "", "persona"),
            ({"X-HIRIS-Internal-Token": "s"}, "192.168.1.31", "s", "integrazione")):
        _, visto = await _passa(_Richiesta(headers=intestazioni, remote=remoto,
                                           token=token))
        assert visto["soggetto"]["specie"] == specie
