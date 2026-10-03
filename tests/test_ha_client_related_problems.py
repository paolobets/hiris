"""Le due porte nuove verso Home Assistant: i legami e i guasti.

Entrambe seguono la stessa disciplina, e la prova che conta e' sempre la
stessa: **un guasto non deve avere la forma di un «niente»**. Un elenco vuoto
significa «questa cosa non la tocca nessuno» o «non c'e' niente che non va»,
che sono affermazioni; un guasto e' un silenzio, e va dichiarato.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

RELATED = "search/related"
ISSUES = "repairs/list_issues"


def _answering(command, result) -> dict:
    """Gli argomenti della casa finta (D8) che risponde `result` a `command`."""
    return {"answers": {command: lambda extra: result}}


#: I tre guasti di una lettura, nella forma che la casa finta inietta sul
#: trasporto vero: la connessione caduta, il rifiuto di Home Assistant (la
#: busta d'errore vera, `{"code", "message"}`), una forma inattesa.
def _failures(command, wrong_shape):
    return [({"silence": {command}}, "connessione caduta"),
            ({"refuse": {command: {"code": "not_found", "message": "non trovato"}}},
             "HA ha rifiutato"),
            (_answering(command, wrong_shape), "forma inattesa")]


# --- i legami -------------------------------------------------------------

@pytest.mark.asyncio
async def test_i_legami_arrivano_ordinati():
    """HA manda INSIEMI, che in JSON viaggiano come liste in ordine
    arbitrario: senza ordinare, due letture della stessa casa producono due
    risposte diverse e nessuno capisce perche'."""
    house = CasaFinta({}, **_answering(RELATED, {
        "automation": ["automation.b", "automation.a"], "scene": []}))
    esito = await house.related("entity", "light.corridoio")
    assert esito == {"automation": ["automation.a", "automation.b"]}
    assert house.calls == [(RELATED,
                            {"item_type": "entity", "item_id": "light.corridoio"})]


@pytest.mark.asyncio
async def test_un_tipo_che_home_assistant_non_conosce_si_rifiuta_prima():
    """I quattordici tipi sono quelli veri di `ItemType`. Mandarne uno
    inventato produrrebbe un rifiuto di HA che arriva come «errore generico»:
    meglio dire subito qual e' il problema."""
    house = CasaFinta({}, **_answering(RELATED, {}))
    esito = await house.related("stanza", "cucina")
    assert "errore" in esito
    assert house.connections == [], "non si chiama HA per un tipo che non accetta"


@pytest.mark.asyncio
@pytest.mark.parametrize("injected,perche", _failures(RELATED, "non un dizionario"))
async def test_un_legame_non_letto_non_diventa_un_elenco_vuoto(injected, perche):
    esito = await CasaFinta({}, **injected).related("entity", "light.x")
    assert "errore" in esito, perche


# --- i guasti -------------------------------------------------------------

@pytest.mark.asyncio
async def test_i_problemi_arrivano_come_home_assistant_li_manda():
    """La scelta di cosa dire e cosa tacere non e' del client: e' di chi
    compone. Qui si legge soltanto -- severita', riparabilita' e la versione
    in cui qualcosa si rompera' restano tutte."""
    house = CasaFinta({}, **_answering(ISSUES, {"issues": [
        {"domain": "reolink", "issue_id": "x", "severity": "error",
         "is_fixable": True, "breaks_in_ha_version": "2026.9", "ignored": False},
    ]}))
    esito = await house.problems()
    assert esito["problemi"][0]["severity"] == "error"
    assert esito["problemi"][0]["breaks_in_ha_version"] == "2026.9"


@pytest.mark.asyncio
async def test_un_problema_IGNORATO_non_esce():
    """L'utente ha gia' detto «non dirmelo», in Home Assistant. Ripeterglielo
    sarebbe disobbedire a una scelta che ha espresso -- ed e' l'unico filtro
    che il client si permette."""
    house = CasaFinta({}, **_answering(ISSUES, {"issues": [
        {"domain": "a", "issue_id": "1", "severity": "warning", "ignored": True},
        {"domain": "b", "issue_id": "2", "severity": "warning", "ignored": False},
    ]}))
    esito = await house.problems()
    assert [p["domain"] for p in esito["problemi"]] == ["b"]


@pytest.mark.asyncio
@pytest.mark.parametrize("injected,perche", _failures(ISSUES, {"issues": "non una lista"}))
async def test_un_guasto_di_lettura_non_diventa_una_casa_sana(injected, perche):
    """La prova che conta: `{"problemi": []}` significa «non c'e' niente che
    non va», ed e' la bugia piu' facile da dire davanti a un guasto."""
    esito = await CasaFinta({}, **injected).problems()
    assert "errore" in esito, perche
    assert "problemi" not in esito
