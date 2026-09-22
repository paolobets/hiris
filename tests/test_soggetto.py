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
from hiris.app.api.servizi import ServiziStore

_INGRESS = "/api/hassio_ingress/abc123/"
#: Il biscotto che il proxy inoltra. Dal 22/09/2026 non basta piu' scrivere
#: `X-Ingress-Path`: il Supervisor deve riconoscere QUESTA sessione (A-2).
_SESSIONE = {"ingress_session": "s-vera"}
_INTESTAZIONI = {"X-Remote-User-Id": "u-42",
                 "X-Remote-User-Name": "paolo",
                 "X-Remote-User-Display-Name": "Paolo Bets"}


class _Richiesta(dict):
    """Una richiesta finta, quanto basta al middleware."""

    def __init__(self, *, headers, remote, token="", biscotti=None):
        super().__init__()
        self.headers = headers
        self.remote = remote
        # Dal 22/09/2026 il confine legge il biscotto di sessione dell'ingress
        # (reperto A-2): una finta senza `cookies` si difenderebbe da un mondo
        # che non esiste, ed e' proprio il campo su cui si decide.
        self.cookies = dict(biscotti or {})
        # `method` e `path` ci sono sempre in una richiesta vera, e il confine
        # li nomina: una finta senza si difenderebbe da un mondo che non esiste.
        self.method = "GET"
        self.path = "/api/entities"
        self.app = {"internal_token": token,
                    "supervisor_ingress_cidrs": ["172.30.32.0/23"],
                    "canali_visti": {}, "servizi": None,
                    "sessioni_ingress": {}}


@pytest.fixture()
def confine_vero(monkeypatch):
    """La suite tiene accesa `HIRIS_ALLOW_NO_TOKEN`, che spegne il confine.

    Le due prove del reperto A-2 dicono «questa richiesta NON passa», e col
    confine spento passerebbe chiunque: sarebbero verdi senza provare niente —
    il difetto n.1 di questo progetto. Misurato scrivendole: senza questa
    riga passavano con `auth_via` a «no_token».
    """
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)


@pytest.fixture(autouse=True)
def supervisor(monkeypatch):
    """Il Supervisor, ridotto all'unica domanda che il confine gli fa.

    **Autouse, e riconosce UNA sessione sola.** Una finta accomodante che
    dicesse sempre di si' renderebbe verde anche il difetto che il reperto A-2
    esiste per chiudere: un add-on vicino che scrive l'intestazione senza avere
    nessun biscotto.
    """
    from hiris.app.api import ingresso

    async def chiedi(sessione):
        return sessione == "s-vera"

    monkeypatch.setattr(ingresso, "_domanda_supervisor", chiedi)


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
        headers={"X-Ingress-Path": _INGRESS, **_INTESTAZIONI},
        remote="172.30.32.2", biscotti=_SESSIONE))

    assert visto["auth_via"] == "ingress"
    assert visto["soggetto"]["id"] == "u-42"
    assert visto["soggetto"]["nome"] == "Paolo Bets"


@pytest.mark.asyncio
async def test_un_ADD_ON_VICINO_non_diventa_il_proprietario(confine_vero):
    """**Il reperto A-2, e il motivo per cui questo file e' cambiato il
    22/09/2026.**

    La rete «fidata» predefinita non e' l'indirizzo del proxy: e' la rete
    Docker in cui vive OGNI add-on installato. Un add-on vicino sta dentro quel
    `/23` per costruzione, e fino a oggi gli bastava scrivere `X-Ingress-Path`
    -- una stringa, non un segreto -- per ottenere `/api/*` per intero **con
    l'identita' che si sceglieva lui**. E se il tunnel che pubblica la casa
    gira come add-on, il caso normale, quell'indirizzo e' il suo.

    Qui ha tutto: l'intestazione giusta, l'indirizzo giusto, e perfino un
    biscotto -- ma un biscotto che il Supervisor non conosce.

    Mutazione ESEGUITA: tolta la verifica della sessione dal confine -- rossa
    (`auth_via` torna «ingress» e il soggetto diventa «u-42»).
    """
    esito, visto = await _passa(_Richiesta(
        headers={"X-Ingress-Path": _INGRESS, **_INTESTAZIONI},
        remote="172.30.32.9",
        biscotti={"ingress_session": "rubata-mai-esistita"}))

    assert visto.get("auth_via") != "ingress", (
        "un add-on vicino e' diventato una persona di Home Assistant")
    assert esito != "ok", "ed e' pure passato"


@pytest.mark.asyncio
async def test_l_intestazione_SENZA_biscotto_non_basta(confine_vero):
    """La forma piu' semplice dello stesso attacco: nessun biscotto affatto.

    Mutazione: accettare quando il biscotto manca -- rossa."""
    esito, visto = await _passa(_Richiesta(
        headers={"X-Ingress-Path": _INGRESS, **_INTESTAZIONI},
        remote="172.30.32.2"))

    assert visto.get("auth_via") != "ingress"
    assert esito != "ok"


@pytest.mark.asyncio
async def test_gli_stessi_header_FUORI_dall_ingress_non_si_credono(archivio):
    """**Il cuore di questo file.** Chi arriva da un'altra strada puo' scrivere
    `X-Remote-User-Id` a mano: crederlo vorrebbe dire consegnare l'identita'
    del proprietario a chiunque sappia comporre un'intestazione.

    Dal 22/09/2026 «l'altra strada» e' **la firma di un servizio approvato**,
    non piu' il segreto condiviso: un servizio che firma e' autenticato per
    davvero, e proprio per questo e' il caso piu' duro -- se le intestazioni
    si credessero a chiunque sia autenticato, basterebbe essere un servizio
    qualunque per diventare il proprietario.

    Mutazione ESEGUITA: leggere gli header prima di distinguere la strada --
    rossa.
    """
    privata, pubblica = _firmante(archivio, ruolo="utente")
    richiesta = _richiesta_firmata(privata, pubblica, archivio)
    richiesta.headers.update(_INTESTAZIONI)

    _, visto = await _passa(richiesta)

    assert visto["auth_via"] == "canale"
    assert visto["soggetto"]["id"] != "u-42", (
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
        headers={"X-Ingress-Path": _INGRESS}, remote="172.30.32.2",
        biscotti=_SESSIONE))

    assert visto["soggetto"] is not None
    assert visto["soggetto"]["specie"] == "persona"
    assert visto["soggetto"]["id"] is None


@pytest.mark.asyncio
async def test_il_soggetto_dice_sempre_di_che_SPECIE_e(archivio):
    """Una persona di Home Assistant e una macchina che porta un token non si
    autenticano nello stesso modo e non possono avere lo stesso soffitto: la
    specie e' il primo fatto che serve a deciderlo, e c'e' sempre.

    Mutazione: togliere `specie` -- rossa (chi legge dovrebbe dedurla, e
    dedurla e' il modo in cui due strade diventano una per distrazione).
    """
    _, persona = await _passa(_Richiesta(
        headers={"X-Ingress-Path": _INGRESS}, remote="172.30.32.2",
        biscotti=_SESSIONE))
    assert persona["soggetto"]["specie"] == "persona"

    privata, pubblica = _firmante(archivio)
    _, macchina = await _passa(_richiesta_firmata(privata, pubblica, archivio))
    assert macchina["soggetto"]["specie"] == "integrazione"


# --- il ramo della FIRMA, e la convivenza col token -------------------------

class _Firmata(_Richiesta):
    """Come `_Richiesta`, ma con un corpo: la firma lo copre."""

    def __init__(self, *, headers, remote, token="", corpo=b"",
                 metodo="GET", percorso="/api/entities", servizi=None):
        super().__init__(headers=headers, remote=remote, token=token)
        self._corpo = corpo
        self.method = metodo
        self.path = percorso
        self.app["canali_visti"] = {}
        self.app["servizi"] = servizi

    async def read(self):
        return self._corpo


@pytest.fixture()
def archivio(tmp_path):
    """L'archivio VERO dei servizi, non una finta.

    Qui si prova il confine insieme a chi decide se una chiave e' autorizzata:
    e' la giunzione in cui l'accoppiamento diventa un permesso, e una finta
    direbbe di si' anche il giorno in cui il vero dicesse di no.
    """
    store = ServiziStore(str(tmp_path / "servizi.db"))
    yield store
    store.close()


def _firmante(archivio, ruolo="lettore", nome="sviluppo", specie="integrazione"):
    """Una coppia di chiavi **accoppiata davvero**: si presenta e viene
    approvata, perche' e' l'unico modo in cui un servizio esiste."""
    privata = Ed25519PrivateKey.generate()
    pubblica = base64.b64encode(
        privata.public_key().public_bytes_raw()).decode("ascii")
    adesso = time.time()
    archivio.presenta(nome=nome, chiave=pubblica, indirizzo="192.168.1.31",
                      now_ts=adesso)
    archivio.approva(pubblica, ruolo=ruolo, specie=specie, now_ts=adesso)
    return privata, pubblica


def _richiesta_firmata(privata, pubblica, archivio, *, metodo="GET",
                       percorso="/api/entities", corpo=b"", unico="u-1"):
    momento = time.time()
    firma = base64.b64encode(privata.sign(
        canali.materia_firmata(metodo, percorso, momento, unico, corpo))
    ).decode("ascii")
    return _Firmata(
        headers={"X-HIRIS-Servizio": pubblica,
                 "X-HIRIS-Momento": str(int(momento)),
                 "X-HIRIS-Unico": unico, "X-HIRIS-Firma": firma},
        remote="192.168.1.31", token="s3greto", corpo=corpo,
        metodo=metodo, percorso=percorso, servizi=archivio)


@pytest.mark.asyncio
async def test_una_richiesta_FIRMATA_passa_e_dice_quale_servizio(archivio):
    """Da qui il registro può dire QUALE integrazione ha chiamato, e con quale
    ruolo -- cosa che col segreto condiviso non era possibile.

    Mutazione: ignorare le intestazioni della firma -- rossa."""
    privata, pubblica = _firmante(archivio)

    esito, visto = await _passa(_richiesta_firmata(privata, pubblica, archivio))

    assert esito == "ok"
    assert visto["auth_via"] == "canale"
    assert visto["soggetto"]["id"] == "sviluppo"
    assert visto["soggetto"]["ruolo"] == "lettore"
    assert visto["soggetto"]["specie"] == "integrazione"


@pytest.mark.asyncio
async def test_una_firma_SBAGLIATA_non_passa_nemmeno_col_token_giusto(archivio):
    """**Il cuore della convivenza.** Chi *prova* a firmare e sbaglia non deve
    scivolare sul ripiego del token: sarebbe una porta aperta da qualunque
    firma storta, cioe' il contrario di una difesa.

    Mutazione ESEGUITA: ricadere sul token quando la firma non regge --
    rossa."""
    privata, pubblica = _firmante(archivio)
    richiesta = _richiesta_firmata(privata, pubblica, archivio)
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
    assert visto.get("auth_via") is None, (
        "col confine di sviluppo acceso questa prova sarebbe verde comunque: "
        "e' il difetto n.1, e l'ha presa la suite il 22/09/2026")


@pytest.mark.asyncio
async def test_un_LETTORE_non_scrive(archivio):
    """La porta di sviluppo, decisa dal proprietario: misurare sì, comandare
    no. Il soffitto del metodo morde al confine, prima di ogni rotta.

    Mutazione ESEGUITA: non guardare il metodo -- rossa."""
    privata, pubblica = _firmante(archivio, ruolo="lettore")

    esito, _ = await _passa(_richiesta_firmata(
        privata, pubblica, archivio, metodo="POST", percorso="/api/chat",
        corpo=b'{"message":"spegni tutto"}'))

    assert esito.status == 403


@pytest.mark.asyncio
async def test_un_UTENTE_scrive(archivio):
    """Il contrario, o la difesa sarebbe il prodotto rotto per tutti.

    Mutazione: negare a ogni ruolo -- rossa."""
    privata, pubblica = _firmante(archivio, ruolo="utente")

    esito, visto = await _passa(_richiesta_firmata(
        privata, pubblica, archivio, metodo="POST", percorso="/api/chat",
        corpo=b"{}"))

    assert esito == "ok"
    assert visto["soggetto"]["ruolo"] == "utente"


@pytest.mark.asyncio
async def test_il_SEGRETO_CONDIVISO_non_apre_piu_niente(confine_vero):
    """**La fine della convivenza (A-5, fetta 3 dello sprint sicurezza).**

    Per una fetta HIRIS ha accettato «la firma oppure il token», perche'
    gateway e Retro Panel vivevano in due repository separati e un taglio netto
    li avrebbe spenti. La misura ha deciso quando chiudere, come era scritto:
    il registro dell'add-on ha smesso di nominare qualcuno che non fossi io, e
    la porta di sviluppo adesso firma.

    Un segreto condiviso non e' un'identita': e' una parola d'ordine, e chi la
    sente una volta e' tutti. Adesso non e' piu' niente.

    Mutazione ESEGUITA: rimesso il ramo del token nel confine -- rossa."""
    esito, visto = await _passa(_Richiesta(
        headers={"X-HIRIS-Internal-Token": "s3greto"},
        remote="192.168.1.31", token="s3greto"))

    assert esito != "ok", "il segreto condiviso apre ancora"
    assert visto.get("auth_via") != "token"


@pytest.mark.asyncio
async def test_e_chi_lo_manda_riceve_un_rifiuto_che_dice_COSA_FARE(confine_vero):
    """Un'integrazione che non e' stata aggiornata trova una porta chiusa: il
    rifiuto deve dirle dove andare, o chi la mantiene passera' il pomeriggio a
    leggere il registro.

    Mutazione: rifiutare con «unauthorized» e basta -- rossa."""
    esito, _ = await _passa(_Richiesta(
        headers={"X-HIRIS-Internal-Token": "s3greto"},
        remote="192.168.1.31", token="s3greto"))

    corpo = esito.text or ""
    assert "accoppia" in corpo.lower() or "servizi" in corpo.lower(), (
        f"il rifiuto non dice cosa fare: {corpo!r}")


# --- la credenziale EFFIMERA del ponte --------------------------------------

@pytest.mark.asyncio
async def test_una_credenziale_di_TURNO_apre_e_dice_che_non_c_e_nessuno(confine_vero):
    """Il ponte non e' una persona e non e' un'integrazione registrata: e'
    HIRIS che lavora per conto suo, per il tempo di un turno.

    Mutazione: non riconoscere le credenziali effimere -- rossa (il ponte si
    spegne appena il segreto condiviso esce)."""
    from hiris.app.api import credenziali

    richiesta = _Firmata(headers={}, remote="127.0.0.1")
    richiesta.app["credenziali"] = {}
    segreto = credenziali.conia(richiesta.app["credenziali"], mestiere="ponte",
                                durata_s=60, adesso=time.time())
    richiesta.headers["X-HIRIS-Internal-Token"] = segreto

    esito, visto = await _passa(richiesta)

    assert esito == "ok"
    assert visto["auth_via"] == "turno"
    assert visto["soggetto"]["specie"] == "nessuno"


@pytest.mark.asyncio
async def test_una_credenziale_SCADUTA_non_apre_piu(confine_vero):
    """E' tutto il punto della credenziale effimera: cio' che resta nella riga
    di comando dopo il turno non deve aprire niente.

    Mutazione ESEGUITA: ignorare la scadenza -- rossa."""
    from hiris.app.api import credenziali

    richiesta = _Firmata(headers={}, remote="127.0.0.1")
    richiesta.app["credenziali"] = {}
    segreto = credenziali.conia(richiesta.app["credenziali"], mestiere="ponte",
                                durata_s=60, adesso=time.time() - 3600)
    richiesta.headers["X-HIRIS-Internal-Token"] = segreto

    esito, visto = await _passa(richiesta)

    assert esito != "ok"
    assert esito.status == 401
    # E non per un'altra ragione: `auth_via` resta vuoto, cioe' nessun ramo
    # l'ha accolta. Senza questa riga la prova resterebbe verde anche se il
    # rifiuto arrivasse da un ramo che non c'entra.
    assert visto.get("auth_via") is None, (
        "col confine di sviluppo acceso questa prova sarebbe verde comunque: "
        "e' il difetto n.1, e l'ha presa la suite il 22/09/2026")


@pytest.mark.asyncio
async def test_la_credenziale_si_guarda_PRIMA_del_segreto_condiviso():
    """L'ordine conta: finche' il segreto condiviso esiste, chi ce l'ha non
    avrebbe motivo di usare una credenziale effimera -- e la convivenza non
    finirebbe mai. Stessa ragione per cui la firma si guarda prima del token.

    Mutazione: invertire i due rami -- rossa (il ponte risulterebbe
    «integrazione» invece che «nessuno», e la cronaca direbbe la cosa
    sbagliata)."""
    from hiris.app.api import credenziali

    richiesta = _Firmata(headers={}, remote="127.0.0.1")
    richiesta.app["credenziali"] = {}
    # lo stesso valore vale come credenziale effimera E come segreto condiviso
    vive = richiesta.app["credenziali"]
    vive["s3greto"] = {"mestiere": "ponte", "scade": time.time() + 60}
    richiesta.headers["X-HIRIS-Internal-Token"] = "s3greto"
    assert credenziali.riconosci(vive, "s3greto", adesso=time.time())

    _, visto = await _passa(richiesta)

    assert visto["auth_via"] == "turno", (
        "il segreto condiviso ha vinto sulla credenziale effimera")


# --- A-4: le due rotte del ponte, chiuse ------------------------------------

@pytest.mark.asyncio
async def test_le_rotte_del_PONTE_vogliono_una_credenziale_di_turno():
    """**Reperto A-4 dell'audit del 21/09**, chiuso il 22.

    `/api/reasoning/claim` restituisce il job con il `context` deserializzato
    per intero -- il nucleo della casa e i ricordi -- piu' un nonce fresco. Con
    quel nonce, `submit` sul ramo `chat` scrive un testo arbitrario nella
    conversazione **come risposta di HIRIS**: l'utente legge un'istruzione
    ostile credendola l'assistente, ed e' lui a eseguirla.

    La rotta gemella dello stesso worker -- `/api/mcp` -- restringeva
    l'autenticazione da sempre. Queste due no, e non si potevano chiudere
    finche' il gateway MCP le chiamava. Il 22/09 il proprietario ha dichiarato
    quel progetto morto: l'unico chiamante legittimo e' il worker, che porta
    una credenziale di turno.

    Mutazione ESEGUITA: togliere il controllo -- rossa.
    """
    from hiris.app.api.handlers_reasoning import (
        handle_reasoning_claim,
        handle_reasoning_submit,
    )

    for rotta in (handle_reasoning_claim, handle_reasoning_submit):
        richiesta = _Firmata(headers={}, remote="127.0.0.1")
        richiesta["auth_via"] = "ingress"
        richiesta["soggetto"] = {"specie": "persona", "id": "u-1"}

        risposta = await rotta(richiesta)

        assert risposta.status == 401, (
            f"{rotta.__name__} ha risposto a chi non e' il worker del ponte")


@pytest.mark.asyncio
async def test_il_WORKER_del_ponte_le_apre_ancora():
    """La contropartita: senza di lei basterebbe chiudere tutto, e il ponte si
    spegnerebbe in silenzio.

    Mutazione: negare anche al turno -- rossa."""
    from hiris.app.api.handlers_reasoning import handle_reasoning_claim

    richiesta = _Firmata(headers={}, remote="127.0.0.1")
    richiesta["auth_via"] = "turno"
    richiesta["soggetto"] = {"specie": "nessuno", "id": "ponte"}

    risposta = await handle_reasoning_claim(richiesta)

    assert risposta.status == 200
