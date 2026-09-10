"""`HAClient.behavior_configs()`: il corpo di automazioni e script, letto da
Home Assistant invece che dal file.

**Perche' dal vivo, e perche' proprio questi due comandi.** Verificato sul
sorgente al tag `2026.9.1`: `components/automation/__init__.py` registra
`@websocket_api.websocket_command({"type": "automation/config", "entity_id":
str})` e torna `automation.raw_config` -- la configurazione dell'ENTITA',
quindi funziona qualunque sia la sua origine: `automations.yaml`, un pacchetto,
un `!include`. La rotta HTTP `/api/config/automation/config/{id}`
(`components/config/automation.py`) no: quella legge solo `automations.yaml`,
ed e' il motivo per cui il file lasciava HIRIS senza il corpo delle automazioni
scritte a mano -- un punto cieco che il prodotto dichiarava di avere
(`behavior.py:5`).

**Misurato sulla casa vera il 10/09/2026**: 18 automazioni su 18 e 2 script su
2, tutti in **una raffica sola da 18 ms** (0,9 ms a chiamata, 44 KB).
"""
import pytest

from hiris.app.proxy.ha_client import HAClient


class _Finto:
    """La finta di `_ws_batch`: `risposte` sono i messaggi INTERI che il
    client vero riceverebbe, nell'ordine dei comandi mandati -- `{success,
    result, error}` oppure `None` (comando senza risposta, o connessione
    fallita del tutto). Fedele al contratto vero, non alla forma comoda."""

    def __init__(self, risposte=None, *, solleva=False):
        self.risposte = risposte
        self.solleva = solleva
        self.comandi = []

    async def _ws_batch(self, commands, timeout=10.0):
        self.comandi.extend(commands)
        if self.solleva:
            raise RuntimeError("websocket giu'")
        if self.risposte is None:
            return [None] * len(commands)
        return list(self.risposte)


def _client(finto):
    client = HAClient.__new__(HAClient)
    client._ws_batch = finto._ws_batch
    return client


@pytest.mark.asyncio
async def test_ogni_dominio_chiede_il_comando_suo():
    """`automation/config` per un'automazione, `script/config` per uno script:
    sono due comandi diversi, e mandare il primo per entrambi tornerebbe un
    errore su ogni script.

    Mutazione che la uccide: usare `automation/config` per tutti.
    """
    finto = _Finto([
        {"success": True, "result": {"config": {"alias": "Sveglia"}}},
        {"success": True, "result": {"config": {"alias": "Saluta"}}},
    ])

    esito = await _client(finto).behavior_configs(
        ["automation.sveglia", "script.saluta"])

    assert [tipo for tipo, _ in finto.comandi] == ["automation/config", "script/config"]
    assert finto.comandi[0][1] == {"entity_id": "automation.sveglia"}
    assert esito["configurazioni"] == {
        "automation.sveglia": {"alias": "Sveglia"},
        "script.saluta": {"alias": "Saluta"}}


@pytest.mark.asyncio
async def test_una_configurazione_non_letta_manca_invece_di_essere_vuota():
    """«Non ho letto il corpo» e «il corpo e' vuoto» dicono due cose diverse:
    la prima e' un limite di HIRIS, la seconda un fatto sulla casa. Una voce
    che non risponde **non compare** nella mappa, cosi' chi chiama non puo'
    confonderle.

    Mutazione che la uccide: mettere `{}` per le voci senza risposta.
    """
    finto = _Finto([
        {"success": True, "result": {"config": {"alias": "Sveglia"}}},
        {"success": False, "error": {"code": "not_found"}},
        None,
    ])

    esito = await _client(finto).behavior_configs(
        ["automation.sveglia", "automation.sparita", "script.muto"])

    assert set(esito["configurazioni"]) == {"automation.sveglia"}


@pytest.mark.asyncio
async def test_un_guasto_della_connessione_e_un_errore_non_un_elenco_vuoto():
    """Stessa disciplina di `legami`, `problemi` e `energy_directions`: mai un
    dizionario vuoto che significherebbe «questa casa non ha automazioni»
    quando il websocket e' giu'."""
    esito = await _client(_Finto(solleva=True)).behavior_configs(["automation.x"])

    assert "errore" in esito
    assert "configurazioni" not in esito


@pytest.mark.asyncio
async def test_senza_entita_non_si_apre_nessuna_connessione():
    """Una casa senza automazioni non deve costare un handshake."""
    finto = _Finto()

    esito = await _client(finto).behavior_configs([])

    assert esito == {"configurazioni": {}}
    assert finto.comandi == []


@pytest.mark.asyncio
async def test_un_dominio_che_non_ha_un_comando_di_configurazione_si_salta():
    """`light.cucina` non ha una configurazione da chiedere: non si inventa un
    comando `light/config` che Home Assistant rifiuterebbe."""
    finto = _Finto([{"success": True, "result": {"config": {"alias": "Sveglia"}}}])

    esito = await _client(finto).behavior_configs(
        ["automation.sveglia", "light.cucina"])

    assert [tipo for tipo, _ in finto.comandi] == ["automation/config"]
    assert set(esito["configurazioni"]) == {"automation.sveglia"}
