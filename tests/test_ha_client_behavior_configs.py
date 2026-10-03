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
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta


def _house(configs=None, **injected) -> CasaFinta:
    """La casa finta (D8): il client vero, e Home Assistant che risponde ai
    comandi `automation/config` e `script/config` con il corpo di `configs`,
    e con il suo rifiuto vero (`not_found`) per un'entita' che non c'e'."""
    return CasaFinta({"behavior": {"configurazioni": dict(configs or {})}}, **injected)


@pytest.mark.asyncio
async def test_ogni_dominio_chiede_il_comando_suo():
    """`automation/config` per un'automazione, `script/config` per uno script:
    sono due comandi diversi, e mandare il primo per entrambi tornerebbe un
    errore su ogni script.

    Mutazione che la uccide: usare `automation/config` per tutti.
    """
    house = _house({"automation.sveglia": {"alias": "Sveglia"},
                    "script.saluta": {"alias": "Saluta"}})

    esito = await house.behavior_configs(["automation.sveglia", "script.saluta"])

    assert house.calls == [("automation/config", {"entity_id": "automation.sveglia"}),
                           ("script/config", {"entity_id": "script.saluta"})]
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
    house = _house({"automation.sveglia": {"alias": "Sveglia"}},
                   silence={"script/config"})

    esito = await house.behavior_configs(
        ["automation.sveglia", "automation.sparita", "script.muto"])

    assert set(esito["configurazioni"]) == {"automation.sveglia"}


@pytest.mark.asyncio
async def test_un_guasto_della_connessione_e_un_errore_non_un_elenco_vuoto():
    """Stessa disciplina di `legami` e `problemi`: mai un
    dizionario vuoto che significherebbe «questa casa non ha automazioni»
    quando il websocket e' giu'. La connessione caduta e' `None` per ogni
    comando, come la torna il vero `_ws_send` (che non solleva mai).

    Mutazione ESEGUITA: tolto il controllo `all(reply is None ...)` -- rossa
    (torna `{"configurazioni": {}}`)."""
    house = _house(silence={"automation/config", "script/config"})

    esito = await house.behavior_configs(["automation.x", "script.y"])

    assert esito == {"errore": "Home Assistant non ha risposto",
        "causa": "silenzio", "codice": None}


@pytest.mark.asyncio
async def test_le_voci_non_lette_si_nominano_col_motivo_e_le_altre_restano():
    """Un guasto PARZIALE non spegne le voci lette ne' resta muto: chi e'
    stato rifiutato e chi ha risposto in una forma inattesa finiscono in
    `non_letti` col loro motivo (come `traces`). Il rifiuto e' quello vero di
    Home Assistant per un'entita' che non c'e' (`not_found`, «Entity not
    found»).

    Mutazione ESEGUITA: togliere `non_letti` dalla risposta -- rossa."""
    house = _house({"automation.a": {"alias": "Sveglia"}},
                   answers={"script/config": lambda extra: {"config": "non un dizionario"}})

    esito = await house.behavior_configs(["automation.a", "automation.c", "script.d"])

    assert esito["configurazioni"] == {"automation.a": {"alias": "Sveglia"}}
    assert esito["non_letti"] == {
        "automation.c": "Entity not found",
        "script.d": "risposta in forma inattesa"}


@pytest.mark.asyncio
async def test_la_voce_senza_risposta_si_nomina_e_le_altre_restano():
    """Il terzo motivo di `non_letti`, in una raffica a parte: la casa finta
    fa tacere un COMANDO intero, non una voce sola, e qui tace `script/config`
    mentre `automation/config` risponde."""
    house = _house({"automation.a": {"alias": "Sveglia"}}, silence={"script/config"})

    esito = await house.behavior_configs(["automation.a", "script.b"])

    assert esito["configurazioni"] == {"automation.a": {"alias": "Sveglia"}}
    assert esito["non_letti"] == {"script.b": "Home Assistant non ha risposto in tempo"}


@pytest.mark.asyncio
async def test_senza_entita_non_si_apre_nessuna_connessione():
    """Una casa senza automazioni non deve costare un handshake."""
    house = _house()

    esito = await house.behavior_configs([])

    assert esito == {"configurazioni": {}}
    assert house.connections == []


@pytest.mark.asyncio
async def test_un_dominio_che_non_ha_un_comando_di_configurazione_si_salta():
    """`light.cucina` non ha una configurazione da chiedere: non si inventa un
    comando `light/config` che Home Assistant rifiuterebbe."""
    house = _house({"automation.sveglia": {"alias": "Sveglia"}})

    esito = await house.behavior_configs(["automation.sveglia", "light.cucina"])

    assert [command for command, _ in house.calls] == ["automation/config"]
    assert set(esito["configurazioni"]) == {"automation.sveglia"}
