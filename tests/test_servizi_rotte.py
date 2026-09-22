"""Le rotte dell'accoppiamento, e **il cancello sull'unica porta non autenticata**.

`POST /api/services/present` e' l'unica superficie che questo prodotto non puo'
autenticare: un servizio che non hai ancora approvato non ha modo di
autenticarsi, ed e' tutto il punto dell'accoppiamento.

Invece di difenderla per sempre -- tetti, limiti di ritmo, scadenze -- il
proprietario ha scelto il 22/09/2026 di **non farla esistere**: l'esenzione dal
confine vale solo nei dieci minuti in cui ha aperto la finestra. Fuori di li'
quella rotta risponde 401 come qualunque altra.

Una difesa permanente invecchia. Una porta chiusa no.
"""
import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.server import create_app

_INGRESS = {"X-Ingress-Path": "/api/hassio_ingress/abc/",
            "X-Requested-With": "fetch"}
_UTENTI = {"utenti": [
    {"id": "u-admin", "nome": "Paolo", "amministratore": True,
     "proprietario": True, "sistema": False},
    {"id": "u-ospite", "nome": "Ospite", "amministratore": False,
     "proprietario": False, "sistema": False}]}


@pytest.fixture(autouse=True)
def chiudi():
    yield
    close_all_stores()


@pytest.fixture(autouse=True)
def confine_vero(monkeypatch):
    """La suite tiene accesa `HIRIS_ALLOW_NO_TOKEN`, che spegne il confine.

    Qui non si puo': meta' di queste prove dicono «a finestra chiusa non si
    passa», e col confine spento passerebbe chiunque -- sarebbero prove verdi
    che non provano niente, il difetto n.1 di questo progetto.
    """
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)


def _chiave() -> str:
    return base64.b64encode(
        Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode("ascii")


@pytest_asyncio.fixture
async def cliente(aiohttp_client, tmp_path):
    app = create_app()
    ha = AsyncMock()
    ha.start = AsyncMock()
    ha.stop = AsyncMock()
    ha.add_state_listener = MagicMock()
    ha.start_websocket = AsyncMock()
    ha.users = AsyncMock(return_value=_UTENTI)
    app["ha_client"] = ha
    app["chat_settings"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["internal_token"] = ""
    app["supervisor_ingress_cidrs"] = ["0.0.0.0/0"]
    from hiris.app.api.servizi import ServiziStore
    app["servizi"] = ServiziStore(str(tmp_path / "servizi.db"))
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    yield c
    app["servizi"].close()


def _chi(utente):
    return {**_INGRESS, "X-Remote-User-Id": utente}


# --- la porta che esiste solo quando l'hai aperta ---------------------------

@pytest.mark.asyncio
async def test_a_finestra_CHIUSA_presentarsi_non_si_puo(cliente):
    """**La proprieta' che vale piu' di tutte in questo file.**

    Mutazione ESEGUITA: rendere l'esenzione incondizionata -- rossa, e sarebbe
    una superficie non autenticata viva per sempre."""
    risposta = await cliente.post("/api/services/present",
                                  json={"nome": "x", "chiave": _chiave()})

    assert risposta.status == 401
    assert (await cliente.get("/api/services", headers=_chi("u-admin"))
            ).status == 200


@pytest.mark.asyncio
async def test_con_la_finestra_APERTA_un_servizio_si_presenta(cliente):
    """E resta IN ATTESA: presentarsi non e' essere autorizzati.

    Mutazione: autorizzare alla presentazione -- rossa."""
    await cliente.post("/api/services/window/open", headers=_chi("u-admin"))

    risposta = await cliente.post("/api/services/present",
                                  json={"nome": "Retro Panel", "chiave": _chiave()})

    assert risposta.status == 200
    corpo = await risposta.json()
    assert len(corpo["codice"]) == 4
    elenco = await (await cliente.get("/api/services", headers=_chi("u-admin"))).json()
    assert elenco["servizi"][0]["stato"] == "in_attesa"


@pytest.mark.asyncio
async def test_chiudere_la_finestra_richiude_la_porta_SUBITO(cliente):
    """Accoppiato il servizio, i minuti che avanzano sono superficie per
    niente.

    Mutazione ESEGUITA: non chiudere davvero -- rossa."""
    await cliente.post("/api/services/window/open", headers=_chi("u-admin"))
    await cliente.post("/api/services/window/close", headers=_chi("u-admin"))

    risposta = await cliente.post("/api/services/present",
                                  json={"nome": "x", "chiave": _chiave()})

    assert risposta.status == 401


@pytest.mark.asyncio
async def test_la_presentazione_non_rivela_NIENTE_a_chi_non_e_il_servizio(cliente):
    """Torna il codice -- che chi presenta puo' calcolarsi da solo dalla propria
    chiave, quindi non e' una rivelazione -- e nient'altro: non quanti servizi
    ci sono, non chi sono, non se il nome esiste gia'.

    Mutazione: rispondere con l'elenco -- rossa."""
    await cliente.post("/api/services/window/open", headers=_chi("u-admin"))
    await cliente.post("/api/services/present",
                       json={"nome": "primo", "chiave": _chiave()})

    corpo = await (await cliente.post(
        "/api/services/present",
        json={"nome": "secondo", "chiave": _chiave()})).json()

    assert set(corpo) == {"codice", "stato"}


# --- chi puo' aprire, approvare, revocare -----------------------------------

@pytest.mark.asyncio
async def test_un_NON_amministratore_non_apre_la_finestra(cliente):
    """Aprire l'accoppiamento e' esporre una superficie: e' un gesto da
    amministratore come scrivere un'automazione.

    Mutazione ESEGUITA: togliere il soffitto -- rossa."""
    risposta = await cliente.post("/api/services/window/open",
                                  headers=_chi("u-ospite"))

    assert risposta.status == 403
    # e la porta resta chiusa
    assert (await cliente.post("/api/services/present",
                               json={"nome": "x", "chiave": _chiave()})).status == 401


@pytest.mark.asyncio
async def test_un_NON_amministratore_non_approva_e_non_revoca(cliente):
    """Dare a una macchina il diritto di comandare la casa non e' meno che
    scriverci un'automazione.

    Mutazione: lasciar approvare a chiunque -- rossa."""
    for rotta in ("/api/services/approve", "/api/services/revoke"):
        risposta = await cliente.post(rotta, headers=_chi("u-ospite"),
                                      json={"chiave": "x", "ruolo": "utente",
                                            "specie": "luogo"})
        assert risposta.status == 403, rotta


@pytest.mark.asyncio
async def test_il_giro_intero_accoppia_e_poi_revoca(cliente):
    """Apri, il servizio si presenta, tu approvi col ruolo, e poi revochi: e'
    il gesto che questa fetta esiste per rendere possibile.

    Mutazione: non cambiare stato all'approvazione -- rossa."""
    chiave = _chiave()
    await cliente.post("/api/services/window/open", headers=_chi("u-admin"))
    await cliente.post("/api/services/present",
                       json={"nome": "Retro Panel", "chiave": chiave})

    approvato = await cliente.post(
        "/api/services/approve", headers=_chi("u-admin"),
        json={"chiave": chiave, "ruolo": "utente", "specie": "luogo"})
    assert approvato.status == 200
    riga = (await approvato.json())["servizi"][0]
    assert riga["stato"] == "autorizzato" and riga["ruolo"] == "utente"

    revocato = await cliente.post("/api/services/revoke", headers=_chi("u-admin"),
                                  json={"chiave": chiave})
    assert (await revocato.json())["servizi"][0]["stato"] == "revocato"


@pytest.mark.asyncio
async def test_un_ruolo_INVENTATO_si_rifiuta_con_400(cliente):
    """I ruoli sono un insieme chiuso, e il rifiuto dice quali sono: un 400 che
    non dice cosa scrivere costringe a indovinare.

    Mutazione: accettare qualunque stringa -- rossa."""
    chiave = _chiave()
    await cliente.post("/api/services/window/open", headers=_chi("u-admin"))
    await cliente.post("/api/services/present", json={"nome": "x", "chiave": chiave})

    risposta = await cliente.post(
        "/api/services/approve", headers=_chi("u-admin"),
        json={"chiave": chiave, "ruolo": "capo", "specie": "luogo"})

    assert risposta.status == 400
    assert "amministratore" in (await risposta.json())["errore"]


# --- il cancello: UNA sola porta non autenticata ----------------------------

def test_il_confine_esenta_UN_percorso_solo_e_lo_dice():
    """**Il cancello di questa fetta.**

    Una seconda riga nell'esenzione sarebbe una seconda superficie non
    autenticata, e non deve poter nascere per distrazione: deve costringere
    qualcuno a passare di qui e scrivere perche'.

    Mutazione ESEGUITA: aggiunto un secondo percorso all'esenzione -- rossa.
    """
    from hiris.app.api import handlers_servizi

    assert isinstance(handlers_servizi.ROTTA_APERTA, str), (
        "l’esenzione è diventata un insieme: se servono due porte non "
        "autenticate, la seconda va decisa da una persona, non aggiunta a una "
        "lista")
    assert handlers_servizi.ROTTA_APERTA == "/api/services/present"


def test_l_esenzione_e_LEGATA_alla_finestra_nel_codice():
    """La contropartita: l'esenzione potrebbe restare mentre il controllo della
    finestra sparisce, e nessuna prova di comportamento se ne accorgerebbe se
    per caso girasse sempre a finestra aperta.

    Si guarda la FORMA, come per le porte di scrittura dell'attuatore.

    Mutazione ESEGUITA: tolto `finestra_aperta` dal confine -- rossa."""
    import ast
    import pathlib

    sorgente = (pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"
                / "api" / "middleware_internal_auth.py").read_text(encoding="utf-8")
    albero = ast.parse(sorgente)
    confine = next(n for n in ast.walk(albero)
                   if isinstance(n, ast.AsyncFunctionDef)
                   and n.name == "internal_auth_middleware")
    corpo = ast.get_source_segment(sorgente, confine) or ""

    assert "ROTTA_APERTA" in corpo and "finestra_aperta" in corpo, (
        "il confine esenta un percorso senza guardare la finestra: quella "
        "superficie sarebbe viva per sempre")


@pytest.mark.asyncio
async def test_la_finestra_nasce_CHIUSA_a_ogni_avvio(cliente):
    """L'add-on riparte spesso. Se la finestra sopravvivesse, «si apre quando
    lo dici tu» sarebbe falso -- ed e' la ragione per cui vive in memoria e non
    nell'archivio.

    Mutazione: persistere la finestra -- rossa."""
    stato = await (await cliente.get("/api/services", headers=_chi("u-admin"))).json()

    assert stato["finestra"]["aperta"] is False
    assert stato["finestra"]["resta_s"] == 0


@pytest.mark.asyncio
async def test_l_elenco_dice_i_ruoli_e_le_specie_possibili(cliente):
    """La pagina non deve ricopiare il vocabolario: glielo dice chi lo
    possiede. Due elenchi degli stessi valori divergerebbero al primo che se ne
    aggiunge uno.

    Mutazione: non mandarli -- rossa."""
    corpo = await (await cliente.get("/api/services", headers=_chi("u-admin"))).json()

    assert corpo["ruoli"] == ["amministratore", "utente", "lettore"]
    assert corpo["specie"] == ["integrazione", "luogo"]
