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
import base64
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hiris.app.api import canali
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
        # `method` e `path` ci sono sempre in una richiesta vera, e il confine
        # li nomina: una finta senza si difenderebbe da un mondo che non esiste.
        self.method = "GET"
        self.path = "/api/entities"
        self.app = {"internal_token": token,
                    "supervisor_ingress_cidrs": ["172.30.32.0/23"],
                    "canali_visti": {}, "canali_registrati": {}}


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


# --- il ramo della FIRMA, e la convivenza col token -------------------------

class _Firmata(_Richiesta):
    """Come `_Richiesta`, ma con un corpo: la firma lo copre."""

    def __init__(self, *, headers, remote, token="", corpo=b"",
                 metodo="GET", percorso="/api/entities", registrate=None):
        super().__init__(headers=headers, remote=remote, token=token)
        self._corpo = corpo
        self.method = metodo
        self.path = percorso
        self.app["canali_visti"] = {}
        self.app["canali_registrati"] = registrate or {}

    async def read(self):
        return self._corpo


def _firmante(ruolo="lettore", nome="sviluppo"):
    privata = Ed25519PrivateKey.generate()
    pubblica = base64.b64encode(
        privata.public_key().public_bytes_raw()).decode("ascii")
    return privata, {nome: {"ruolo": ruolo, "chiave": pubblica}}


def _richiesta_firmata(privata, registrate, *, canale="sviluppo", metodo="GET",
                       percorso="/api/entities", corpo=b"", unico="u-1"):
    momento = time.time()
    firma = base64.b64encode(privata.sign(
        canali.materia_firmata(metodo, percorso, momento, unico, corpo))
    ).decode("ascii")
    return _Firmata(
        headers={"X-HIRIS-Canale": canale, "X-HIRIS-Momento": str(int(momento)),
                 "X-HIRIS-Unico": unico, "X-HIRIS-Firma": firma},
        remote="192.168.1.31", token="s3greto", corpo=corpo,
        metodo=metodo, percorso=percorso, registrate=registrate)


@pytest.mark.asyncio
async def test_una_richiesta_FIRMATA_passa_e_dice_quale_canale():
    """Da qui il registro può dire QUALE integrazione ha chiamato, e con quale
    ruolo -- cosa che col segreto condiviso non era possibile.

    Mutazione: ignorare le intestazioni della firma -- rossa."""
    privata, registrate = _firmante()

    esito, visto = await _passa(_richiesta_firmata(privata, registrate))

    assert esito == "ok"
    assert visto["auth_via"] == "canale"
    assert visto["soggetto"]["id"] == "sviluppo"
    assert visto["soggetto"]["ruolo"] == "lettore"
    assert visto["soggetto"]["specie"] == "integrazione"


@pytest.mark.asyncio
async def test_una_firma_SBAGLIATA_non_passa_nemmeno_col_token_giusto():
    """**Il cuore della convivenza.** Chi *prova* a firmare e sbaglia non deve
    scivolare sul ripiego del token: sarebbe una porta aperta da qualunque
    firma storta, cioe' il contrario di una difesa.

    Mutazione ESEGUITA: ricadere sul token quando la firma non regge --
    rossa."""
    privata, registrate = _firmante()
    richiesta = _richiesta_firmata(privata, registrate)
    richiesta.headers["X-HIRIS-Firma"] = base64.b64encode(b"x" * 64).decode()
    # **Il token VALIDO, davvero.** Senza questa riga il 401 arriverebbe dal
    # ramo del token per assenza, non dal rifiuto della firma: la prova
    # asserirebbe il fatto giusto per la ragione sbagliata, e resterebbe verde
    # anche togliendo il rifiuto. Misurato con la mutazione, non supposto.
    richiesta.headers["X-HIRIS-Internal-Token"] = "s3greto"

    esito, visto = await _passa(richiesta)

    assert esito != "ok", (
        "una firma storta e' scivolata sul ripiego del token: chi prova a "
        "firmare e sbaglia non deve avere una seconda strada")
    assert esito.status == 401
    assert visto.get("auth_via") is None


@pytest.mark.asyncio
async def test_un_LETTORE_non_scrive():
    """La porta di sviluppo, decisa dal proprietario: misurare sì, comandare
    no. Il soffitto del metodo morde al confine, prima di ogni rotta.

    Mutazione ESEGUITA: non guardare il metodo -- rossa."""
    privata, registrate = _firmante(ruolo="lettore")

    esito, _ = await _passa(_richiesta_firmata(
        privata, registrate, metodo="POST", percorso="/api/chat",
        corpo=b'{"message":"spegni tutto"}'))

    assert esito.status == 403


@pytest.mark.asyncio
async def test_un_UTENTE_scrive():
    """Il contrario, o la difesa sarebbe il prodotto rotto per tutti.

    Mutazione: negare a ogni ruolo -- rossa."""
    privata, registrate = _firmante(ruolo="utente")

    esito, visto = await _passa(_richiesta_firmata(
        privata, registrate, metodo="POST", percorso="/api/chat", corpo=b"{}"))

    assert esito == "ok"
    assert visto["soggetto"]["ruolo"] == "utente"


@pytest.mark.asyncio
async def test_il_TOKEN_continua_a_valere_e_si_misura_chi_lo_usa(caplog):
    """La convivenza (spec §8): per una fetta il token resta, perché gateway e
    Retro Panel vivono in due repository separati e un taglio netto li
    spegnerebbe. Ma **chi lo usa si misura**, o la fine della convivenza la
    deciderebbe una speranza invece di un dato.

    Mutazione ESEGUITA: accettare il token senza dichiararlo -- rossa."""
    richiesta = _Firmata(headers={"X-HIRIS-Internal-Token": "s3greto",
                                  "X-HIRIS-Canale": "gateway"},
                         remote="192.168.1.31", token="s3greto")

    with caplog.at_level("INFO"):
        esito, visto = await _passa(richiesta)

    assert esito == "ok"
    assert visto["auth_via"] == "token"
    assert "gateway" in caplog.text


@pytest.mark.asyncio
async def test_chi_usa_il_token_SENZA_dirsi_finisce_come_ignoto(caplog):
    """Chi non dichiara il canale non deve passare inosservato: sarebbe
    l'integrazione che nessuno sa di dover aggiornare.

    Mutazione: tacere quando il canale non è dichiarato -- rossa."""
    richiesta = _Firmata(headers={"X-HIRIS-Internal-Token": "s3greto"},
                         remote="192.168.1.31", token="s3greto")

    with caplog.at_level("INFO"):
        esito, _ = await _passa(richiesta)

    assert esito == "ok"
    assert "ignoto" in caplog.text.lower()


# --- la credenziale EFFIMERA del ponte --------------------------------------

@pytest.mark.asyncio
async def test_una_credenziale_di_TURNO_apre_e_dice_che_non_c_e_nessuno():
    """Il ponte non e' una persona e non e' un'integrazione registrata: e'
    HIRIS che lavora per conto suo, per il tempo di un turno.

    Mutazione: non riconoscere le credenziali effimere -- rossa (il ponte si
    spegne appena il segreto condiviso esce)."""
    from hiris.app.api import credenziali

    richiesta = _Firmata(headers={}, remote="127.0.0.1", token="s3greto")
    richiesta.app["credenziali"] = {}
    segreto = credenziali.conia(richiesta.app["credenziali"], mestiere="ponte",
                                durata_s=60, adesso=time.time())
    richiesta.headers["X-HIRIS-Internal-Token"] = segreto

    esito, visto = await _passa(richiesta)

    assert esito == "ok"
    assert visto["auth_via"] == "turno"
    assert visto["soggetto"]["specie"] == "nessuno"


@pytest.mark.asyncio
async def test_una_credenziale_SCADUTA_non_apre_piu():
    """E' tutto il punto della credenziale effimera: cio' che resta nella riga
    di comando dopo il turno non deve aprire niente.

    Mutazione ESEGUITA: ignorare la scadenza -- rossa."""
    from hiris.app.api import credenziali

    richiesta = _Firmata(headers={}, remote="127.0.0.1", token="s3greto")
    richiesta.app["credenziali"] = {}
    segreto = credenziali.conia(richiesta.app["credenziali"], mestiere="ponte",
                                durata_s=60, adesso=time.time() - 3600)
    richiesta.headers["X-HIRIS-Internal-Token"] = segreto

    esito, _ = await _passa(richiesta)

    assert esito != "ok"
    assert esito.status == 401


@pytest.mark.asyncio
async def test_la_credenziale_si_guarda_PRIMA_del_segreto_condiviso():
    """L'ordine conta: finche' il segreto condiviso esiste, chi ce l'ha non
    avrebbe motivo di usare una credenziale effimera -- e la convivenza non
    finirebbe mai. Stessa ragione per cui la firma si guarda prima del token.

    Mutazione: invertire i due rami -- rossa (il ponte risulterebbe
    «integrazione» invece che «nessuno», e la cronaca direbbe la cosa
    sbagliata)."""
    from hiris.app.api import credenziali

    richiesta = _Firmata(headers={}, remote="127.0.0.1", token="s3greto")
    richiesta.app["credenziali"] = {}
    # lo stesso valore vale come credenziale effimera E come segreto condiviso
    vive = richiesta.app["credenziali"]
    vive["s3greto"] = {"mestiere": "ponte", "scade": time.time() + 60}
    richiesta.headers["X-HIRIS-Internal-Token"] = "s3greto"
    assert credenziali.riconosci(vive, "s3greto", adesso=time.time())

    _, visto = await _passa(richiesta)

    assert visto["auth_via"] == "turno", (
        "il segreto condiviso ha vinto sulla credenziale effimera")
