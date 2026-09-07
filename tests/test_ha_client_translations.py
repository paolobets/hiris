"""`HAClient.get_translations()`: le traduzioni che Home Assistant pubblica.

Un comando solo, `frontend/get_translations`
(`homeassistant/components/frontend/__init__.py:467`, tag `2026.9.1`), con
`language` e `category` OBBLIGATORI (`:1007-1015`) e risposta
`{"resources": {...}}` (`:1028-1030`). **Non ha `@require_admin`**
(`:1007-1019`), e il proxy WebSocket del Supervisor non filtra il prefisso
`frontend/` (`supervisor/api/middleware/security.py:45-50` @ `2026.09.0`).

**La forma della risposta e' MISURATA sulla casa vera il 07/09/2026** (WS su
`192.168.1.95:8123`, `language: "it"`, `category: "entity_component"`): 801
chiavi, 53 domini, 65.513 byte, 13 ms. Le chiavi qui sotto sono estratte da
quella risposta, non plausibili.

Stessa disciplina di `problems()`/`system_log()`: `{"errore": ...}` su guasto,
mai un dizionario vuoto -- che significherebbe «questa casa non traduce
niente», un'altra cosa dal non aver potuto chiedere.
"""
import pytest

from hiris.app.proxy.ha_client import HAClient

RISPOSTA_VERA = {
    "component.climate.entity_component._.state.heat": "Riscaldamento",
    "component.person.entity_component._.state.not_home": "Fuori casa",
}


class _Finto:
    def __init__(self, risposta=None, *, solleva=False):
        self.risposta = risposta
        self.solleva = solleva
        self.comandi = []

    async def _ws_batch(self, commands, timeout=10.0):
        self.comandi.extend(commands)
        if self.solleva:
            raise OSError("HA muto")
        return [self.risposta]


def _client(finto):
    c = HAClient.__new__(HAClient)
    c._ws_batch = finto._ws_batch
    return c


@pytest.mark.asyncio
async def test_manda_lingua_e_categoria_perche_HA_le_vuole_entrambe():
    """`vol.Required("language")` e `vol.Required("category")`
    (`frontend/__init__.py:1007-1015`): mandarne una sola fa rifiutare il
    comando.

    Mutazione ESEGUITA: togliere `"category": category` dal payload in
    `get_translations` -- il test torna rosso su
    `assert extra == {"language": "it", "category": "entity_component"}`.
    """
    finto = _Finto({"success": True, "result": {"resources": RISPOSTA_VERA}})
    await _client(finto).get_translations("it")
    (msg_type, extra), = finto.comandi
    assert msg_type == "frontend/get_translations"
    assert extra == {"language": "it", "category": "entity_component"}


@pytest.mark.asyncio
async def test_le_risorse_arrivano_cosi_come_HA_le_manda():
    """Qui si LEGGE soltanto: nessuna chiave viene riscritta, filtrata o
    normalizzata. Chi decide cosa farne e' `proxy/state_translations.py`."""
    finto = _Finto({"success": True, "result": {"resources": RISPOSTA_VERA}})
    esito = await _client(finto).get_translations("it")
    assert esito == {"risorse": RISPOSTA_VERA}


@pytest.mark.asyncio
async def test_un_rifiuto_di_HA_porta_il_SUO_motivo_non_uno_nostro():
    """Il motivo lo conosce HA e lo scrive in `error`: buttarlo via
    costringerebbe chi legge a indovinare fra «comando sconosciuto» e «rete
    giu'».

    Mutazione ESEGUITA: `return {"errore": "rifiutato"}` fisso nel ramo
    dell'errore -- il test torna rosso su
    `assert esito == {"errore": "Unknown command."}`.
    """
    finto = _Finto({"success": False,
                    "error": {"code": "unknown_command", "message": "Unknown command."}})
    assert await _client(finto).get_translations("it") == {"errore": "Unknown command."}


@pytest.mark.asyncio
async def test_nessuna_risposta_NON_diventa_una_tabella_vuota():
    """Connessione o autenticazione fallita: `_ws_batch` torna `[None]`. Una
    tabella vuota direbbe «questa casa non traduce niente».

    Mutazione ESEGUITA: `return {"risorse": {}}` al posto di `{"errore": ...}`
    quando `msg is None` -- il test torna rosso su
    `assert "risorse" not in esito`.
    """
    esito = await _client(_Finto(None)).get_translations("it")
    assert "risorse" not in esito
    assert esito["errore"]


@pytest.mark.asyncio
async def test_una_risposta_in_forma_inattesa_e_un_guasto_dichiarato():
    """`result` senza `resources`, o `resources` che non e' un dizionario: e'
    un guasto diverso dal rifiuto, e si dichiara invece di far esplodere il
    primo `in` del gradino successivo."""
    assert "risorse" not in await _client(
        _Finto({"success": True, "result": {}})).get_translations("it")
    assert "risorse" not in await _client(
        _Finto({"success": True, "result": []})).get_translations("it")


@pytest.mark.asyncio
async def test_un_guasto_di_rete_non_solleva_mai():
    """Le traduzioni sono un di piu' sulla pagina: una rotta che esplodesse
    per una tabella non letta toglierebbe al proprietario gli episodi, che
    sono il fatto."""
    esito = await _client(_Finto(solleva=True)).get_translations("it")
    assert esito == {"errore": "Home Assistant non ha risposto"}
