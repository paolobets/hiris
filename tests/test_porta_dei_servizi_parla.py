"""La porta dei servizi parla come la configurazione (Tappa 7, Task 1: E-10,
E-03, E-02, E-09, E-13, A-30).

- **E-10**: il motivo che Home Assistant scrive nel corpo di un rifiuto arriva
  intatto a chi ha chiesto; un guasto di trasporto non si dice «rifiutato».
- **E-03**: in `action/actuator.py` c'e' un solo «ha rifiutato» e un solo
  successo.
- **E-02**: la cronaca ha un solo scrittore, col `genere`.
- **E-09, E-13**: chi verifica senza eseguire chiede `ActionActuator.verify`;
  nessuno fuori dalla porta chiama il suo `_resolve`.

Gira il client VERO sul trasporto finto (`scripts/casa_finta.py`): il rifiuto e
il silenzio si fabbricano dall'altra parte del filo.
"""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import Refused

from hiris.app.action.actuator import ActionActuator
from tests.test_action_actuator import (
    SALOTTO_ACCESO,
    SPEGNI_IL_SALOTTO,
    FintaCache,
    _chiamate,
    _client,
    _registro_pronto,
)

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"
ACTUATOR = APP / "action" / "actuator.py"

#: Il corpo di un 400 di `POST /api/services/...`, nella forma di
#: `HomeAssistantView.json_message` (`{"message": ...}`).
MOTIVO = "Invalid service data: extra keys not allowed @ data['luminosita']"


async def _porta(**faults):
    house = _client(**faults)
    return ActionActuator(house, await _registro_pronto(),
                          FintaCache(SALOTTO_ACCESO)), house


# ── E-10: il motivo di Home Assistant, e il silenzio detto come tale ────────

@pytest.mark.asyncio
async def test_il_motivo_di_un_rifiuto_arriva_intatto_a_chi_ha_chiesto():
    """Fino al 07/10/2026 `call_service` faceva `raise_for_status()`: la chat
    diceva «400, message='Bad Request'» e la frase di Home Assistant si
    perdeva. Mutazione (eseguita): rimettere `resp.raise_for_status()` in
    `call_service` -- rossa, il motivo non c'e'."""
    porta, house = await _porta(refuse={
        "POST /api/services/light/turn_off": Refused(400, MOTIVO)})

    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

    assert esito["eseguito"] is False
    assert MOTIVO in esito["errore"]
    assert "rifiutato" in esito["errore"]
    assert _chiamate(house)  # la chiamata e' partita: e' HA che ha detto no


@pytest.mark.asyncio
async def test_un_trasporto_muto_non_e_detto_rifiutato():
    """Una chiamata senza risposta puo' essere arrivata: dirla «rifiutata»
    sarebbe un fatto inventato. Mutazione (eseguita): nel ramo del silenzio di
    `_failed` la frase del rifiuto -- rossa."""
    porta, _house = await _porta(silence={"POST /api/services/light/turn_off"})

    esito = await porta.execute(SPEGNI_IL_SALOTTO, actor="chat")

    assert esito["eseguito"] is False
    assert "rifiutato" not in esito["errore"]
    assert "Non so se la chiamata e' arrivata" in esito["errore"]


# ── E-03: una frase del rifiuto, un successo ────────────────────────────────

def _strings(path: Path) -> list[str]:
    return [node.value for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def test_una_frase_sola_per_il_rifiuto_di_home_assistant():
    """Mutazione (eseguita): una seconda copia di «Home Assistant ha rifiutato
    la chiamata» in `execute` -- rossa."""
    copies = [s for s in _strings(ACTUATOR) if "ha rifiutato la chiamata" in s]
    assert len(copies) == 1, copies


def test_un_solo_esito_riuscito_nella_porta():
    """Il successo si scrive in `_succeeded`, e lo chiede chi esegue.
    Mutazione (eseguita): costruire `{"eseguito": True, ...}` in linea nel ramo
    senza bersaglio -- rossa."""
    tree = ast.parse(ACTUATOR.read_text(encoding="utf-8"))
    builders = []
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Dict) and any(
                    isinstance(k, ast.Constant) and k.value == "eseguito"
                    and isinstance(v, ast.Constant) and v.value is True
                    for k, v in zip(node.keys, node.values, strict=True)):
                builders.append(func.name)
    assert builders == ["_succeeded"]


# ── E-02: un solo scrittore della cronaca ───────────────────────────────────

def test_la_cronaca_ha_un_solo_scrittore():
    """Chiesto all'albero del prodotto: un solo `INSERT INTO esecuzioni`.
    Mutazione (eseguita): rimettere `log_construction` col suo `INSERT` --
    rossa."""
    found = [f"{p.relative_to(APP).as_posix()}"
             for p in sorted(APP.rglob("*.py"))
             for s in _strings(p) if "INSERT INTO esecuzioni" in s]
    assert found == ["action/journal.py"]


# ── E-09, E-13: chi verifica chiede la porta ────────────────────────────────

def test_nessuno_fuori_dalla_porta_chiama_la_sua_risoluzione():
    """`_resolve` e' della porta: chi deve contare o verificare chiede
    `verify`. Si chiede all'albero di ogni modulo: un `x._resolve` dove `x`
    non e' `self`. Mutazione (eseguita): rimettere
    `self._actuator._resolve(...)` in `home_space/tools.py` -- rossa."""
    found = []
    for path in sorted(APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Attribute) and node.attr == "_resolve"
                    and not (isinstance(node.value, ast.Name) and node.value.id == "self")):
                found.append(f"{path.relative_to(APP).as_posix()}:{node.lineno}")
    assert found == []


def test_la_ricerca_qui_sopra_vede_davvero_i_moduli():
    """La prova che la derivazione non si e' rotta: l'albero contiene la porta
    e gli strumenti, e la porta il suo `_resolve`."""
    names = {p.relative_to(APP).as_posix() for p in APP.rglob("*.py")}
    assert {"action/actuator.py", "home_space/tools.py"} <= names
    assert "def _resolve" in ACTUATOR.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_verificare_non_esegue_e_non_scrive_la_cronaca():
    """`verify` e' il pre-volo e nient'altro: nessuna chiamata parte."""
    porta, house = await _porta()

    answer = await porta.verify(SPEGNI_IL_SALOTTO)

    assert answer == {"servizio": "light.turn_off", "entita": ["light.salotto"]}
    assert _chiamate(house) == []


@pytest.mark.asyncio
async def test_verificare_rifiuta_con_le_frasi_della_porta():
    """La promessa e l'esecuzione rispondono uguale alla stessa chiamata
    sbagliata: la frase e' quella della verifica."""
    porta, _house = await _porta()

    answer = await porta.verify({"servizio": "light.inventato",
                                 "bersaglio": {"entita": ["light.salotto"]}})
    esito = await porta.execute({"servizio": "light.inventato",
                                 "bersaglio": {"entita": ["light.salotto"]}},
                                actor="chat")

    assert answer["errore"] == esito["errore"]
    assert "light.inventato" in answer["errore"]


# ── la consegna di una push non fabbrica un esito della porta ───────────────

@pytest.mark.asyncio
async def test_un_guasto_della_consegna_si_dichiara_e_non_ferma_le_altre():
    """`keeper/delivery.deliver` costruiva un `{"eseguito": False}` suo quando
    la porta sollevava: un esito della porta scritto fuori dalla porta. Ora la
    riga mancata si scrive direttamente, e il servizio dopo parte lo stesso.
    Mutazione (eseguita): `raise` nel ramo dell'eccezione -- rossa."""
    from hiris.app.keeper.delivery import deliver

    asked = []

    async def execute(call, *, actor, subject):
        asked.append(call["servizio"])
        if call["servizio"] == "notify.mobile_app_a":
            raise RuntimeError("un difetto nostro")
        return {"eseguito": True}

    sent, failures = await deliver(
        ["notify.mobile_app_a", "notify.mobile_app_b"], "ciao",
        execute=execute, actor="promessa", subject=None)

    assert sent == 2
    assert asked == ["notify.mobile_app_a", "notify.mobile_app_b"]
    assert failures == ["notify.mobile_app_a (guasto imprevisto: RuntimeError)"]
