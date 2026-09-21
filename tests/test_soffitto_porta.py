"""Il soffitto applicato alla PORTA della configurazione (invariante I-1).

`handlers_constructions._act` e' il punto unico da cui passano sia «applica» sia
«rimetti com'era»: le due scritture che HIRIS fa sulla configurazione di Home
Assistant dalla pagina. E' li' che il soffitto morde, e in un posto solo.

`reject` non passa di qui e non deve: non scrive niente su Home Assistant, e
chiudere un rifiuto dietro un permesso vorrebbe dire che chi non puo' costruire
non puo' nemmeno dire di no -- cioe' lasciargli in coda per sempre una proposta
che non vuole.
"""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.server import create_app

_INGRESS = {"X-Ingress-Path": "/api/hassio_ingress/abc/"}
_UTENTI = {"utenti": [
    {"id": "u-admin", "nome": "Paolo", "amministratore": True,
     "proprietario": True, "sistema": False},
    {"id": "u-ospite", "nome": "Ospite", "amministratore": False,
     "proprietario": False, "sistema": False}]}


@pytest.fixture(autouse=True)
def chiudi_archivi():
    yield
    close_all_stores()


class _Officina:
    def __init__(self):
        self.applicate = []
        self.soggetti = []

    async def apply(self, ident, *, actor, exchange, now, subject=None):
        self.applicate.append((ident, actor))
        self.soggetti.append(subject)
        return {"applicata": ident}

    async def restore(self, ident, *, actor, exchange, now, subject=None):
        self.applicate.append((ident, actor))
        self.soggetti.append(subject)
        return {"ripristinata": ident}


class _Archivio:
    def read(self, ident):
        return {"id": ident, "stato": "in_attesa"}


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
    app["supervisor_ingress_cidrs"] = ["0.0.0.0/0"]  # il client di prova e' locale
    app["workshop"] = _Officina()
    app["constructions"] = _Archivio()
    app.on_startup.clear()
    app.on_cleanup.clear()
    return await aiohttp_client(app)


def _testate(utente):
    return {**_INGRESS, "X-Remote-User-Id": utente, "X-Requested-With": "fetch"}


@pytest.mark.asyncio
async def test_un_amministratore_applica(cliente):
    """Il proprietario non si accorge di niente: e' il metro con cui si misura
    che la difesa non ha rotto il prodotto."""
    risposta = await cliente.post("/api/constructions/c1/confirm",
                                  headers=_testate("u-admin"))

    assert risposta.status == 200
    assert cliente.app["workshop"].applicate == [("c1", "pagina")]


@pytest.mark.asyncio
async def test_un_utente_qualunque_NON_applica_e_gli_si_dice_perche(cliente):
    """L'amplificazione che questo invariante chiude: senza il soffitto, un
    utente a cui Home Assistant nega di scrivere la configurazione la fa
    scrivere a HIRIS, che parla da amministratore.

    Mutazione ESEGUITA: togliere il controllo da `_act` -- rossa (l'officina
    riceve la chiamata).
    """
    risposta = await cliente.post("/api/constructions/c1/confirm",
                                  headers=_testate("u-ospite"))

    assert risposta.status == 403
    corpo = await risposta.json()
    assert corpo["errore"], "un rifiuto senza motivo e' un ordine"
    assert cliente.app["workshop"].applicate == [], (
        "l'officina ha scritto lo stesso: il soffitto non ha morso")


@pytest.mark.asyncio
async def test_anche_RIMETTI_COM_ERA_passa_dal_soffitto(cliente):
    """Ripristinare riscrive Home Assistant esattamente come applicare: e' la
    stessa porta, e un soffitto che ne guarda una sola e' meta' cancello.

    Mutazione: controllare solo `apply` -- rossa."""
    risposta = await cliente.post("/api/constructions/c1/restore",
                                  headers=_testate("u-ospite"))

    assert risposta.status == 403
    assert cliente.app["workshop"].applicate == []


@pytest.mark.asyncio
async def test_RIFIUTARE_resta_di_tutti(cliente):
    """Chi non puo' costruire deve comunque poter dire di no, o si ritrova in
    coda per sempre una proposta che non vuole. E il rifiuto non scrive niente
    su Home Assistant: non c'e' nessun potere da custodire.

    Mutazione: mettere il soffitto anche sul rifiuto -- rossa."""
    risposta = await cliente.post("/api/constructions/c1/reject",
                                  headers=_testate("u-ospite"))

    assert risposta.status != 403


@pytest.mark.asyncio
async def test_se_il_ruolo_non_si_legge_si_NEGA(cliente):
    """Il verso del dubbio, fino in fondo alla porta: Home Assistant muto non
    vale «e' amministratore».

    Mutazione ESEGUITA: ripiegare su «permesso» quando la lettura fallisce --
    rossa."""
    cliente.app["ha_client"].users = AsyncMock(
        return_value={"errore": "Home Assistant non ha risposto"})

    risposta = await cliente.post("/api/constructions/c1/confirm",
                                  headers=_testate("u-admin"))

    assert risposta.status == 403
    assert cliente.app["workshop"].applicate == []


@pytest.mark.asyncio
async def test_il_ruolo_non_si_richiede_a_ogni_CLIC(cliente):
    """Una lettura verso Home Assistant per ogni richiesta metterebbe il
    pannello alla mercè della latenza di HA, su un percorso che gira a ogni
    clic. Si tiene per un poco, e il «poco» e' dichiarato.

    Mutazione: togliere la cache -- rossa (due letture per due clic)."""
    for _ in range(3):
        await cliente.post("/api/constructions/c1/confirm",
                           headers=_testate("u-admin"))

    assert cliente.app["ha_client"].users.await_count == 1


@pytest.mark.asyncio
async def test_la_cache_dei_ruoli_SCADE(cliente):
    """Un utente promosso o degradato in Home Assistant non deve aspettare un
    riavvio dell'add-on perche' HIRIS se ne accorga.

    Mutazione: cache senza scadenza -- rossa."""
    from hiris.app.api import soffitto

    await cliente.post("/api/constructions/c1/confirm", headers=_testate("u-admin"))
    cliente.app["ruoli"]["quando"] = time.time() - soffitto.RUOLI_VALIDI_S - 1
    await cliente.post("/api/constructions/c1/confirm", headers=_testate("u-admin"))

    assert cliente.app["ha_client"].users.await_count == 2


# --- la stessa porta, dal lato del MODELLO ----------------------------------

class _OfficinaContata:
    def __init__(self):
        self.applicate = []

    async def apply(self, ident, *, actor, exchange, now, subject=None):
        self.applicate.append(ident)
        return {"applicata": ident}


def _dispatcher(officina, soffitto):
    from hiris.app.home_space.tools import ToolDispatcher
    return ToolDispatcher(None, None, workshop=officina, exchange="t-1",
                          soffitto=soffitto)


@pytest.mark.asyncio
async def test_il_modello_non_conferma_per_conto_di_chi_non_puo():
    """La porta della configurazione ha DUE lati: il clic sulla pagina e lo
    strumento `confirm` che il modello chiama in chat. Custodirne uno solo
    lascerebbe l'altro spalancato -- e quello del modello e' il piu' facile da
    attraversare, perche' basta scrivere «conferma» in chat.

    Mutazione ESEGUITA: togliere il controllo da `_confirm` -- rossa.
    """
    officina = _OfficinaContata()
    negato = {"comandare": True, "costruire": False, "rinviato": False,
              "perche": "non sei amministratore"}

    esito = await _dispatcher(officina, negato)._confirm({"proposta_id": "c1"})

    assert "errore" in esito
    assert officina.applicate == [], "l'officina ha scritto lo stesso"


@pytest.mark.asyncio
async def test_un_soffitto_PERMISSIVO_lascia_confermare():
    """Il metro opposto: la difesa non deve rompere il caso normale.

    Mutazione: negare sempre -- rossa."""
    officina = _OfficinaContata()
    ammesso = {"comandare": True, "costruire": True, "rinviato": False,
               "perche": None}

    await _dispatcher(officina, ammesso)._confirm({"proposta_id": "c1"})

    assert officina.applicate == ["c1"]


@pytest.mark.asyncio
async def test_senza_soffitto_il_dispatcher_tiene_il_comportamento_di_ieri():
    """Il dispatcher nasce anche dove non c'e' nessuna persona: il turno di una
    promessa, il ponte, lo schedulatore. Li' `soffitto` e' `None` e vale il
    comportamento di ieri -- **dichiarato, non dedotto**: il perimetro delle
    macchine e' l'invariante dei canali esterni, e stringerlo qui a meta'
    spegnerebbe il gateway senza che nessuno l'abbia deciso.

    Mutazione: trattare `None` come un rifiuto -- rossa (e sarebbe il ponte
    rotto in silenzio)."""
    officina = _OfficinaContata()

    await _dispatcher(officina, None)._confirm({"proposta_id": "c1"})

    assert officina.applicate == ["c1"]


@pytest.mark.asyncio
async def test_la_chat_passa_il_soffitto_al_dispatcher(cliente):
    """Il cablaggio: senza questo, i due controlli sopra sarebbero veri e
    inerti. E' la stessa forma di difetto che l'audit ha trovato altrove --
    una difesa scritta che nessuno chiama.

    Mutazione ESEGUITA: non passare `soffitto=` in `create_tool_dispatcher` --
    rossa.
    """
    from hiris.app.api.handlers_chat import create_tool_dispatcher

    app = cliente.app
    negato = {"comandare": True, "costruire": False, "rinviato": False,
              "perche": "x"}

    dispatcher = create_tool_dispatcher(app, exchange="t-1", soffitto=negato)

    assert dispatcher._soffitto == negato


@pytest.mark.asyncio
async def test_la_porta_porta_anche_il_SOGGETTO_alla_cronaca(cliente):
    """Il soffitto dice cosa si concede; la cronaca deve dire **a chi**. Senza
    questo passaggio l'officina scriverebbe «origine: pagina» e nient'altro --
    cioe' da quale porta, non chi -- e «chi ha scritto quell'automazione»
    resterebbe senza risposta come prima.

    Mutazione ESEGUITA: non passare `soggetto=` a `workshop.apply` -- rossa.
    """
    await cliente.post("/api/constructions/c1/confirm",
                       headers=_testate("u-admin"))

    visto = cliente.app["workshop"].soggetti[-1]
    assert visto["id"] == "u-admin"
    assert visto["specie"] == "persona"
