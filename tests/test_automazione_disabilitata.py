"""Un'automazione spenta dal proprietario non e' un'automazione guasta.

Misurato sulla casa vera il 24/09/2026. Alla domanda «quali automazioni non
scattano da un pezzo?» HIRIS ha risposto: *«Automazione ferma da piu' tempo:
Gestione antimosche. Dovrebbe partire ogni 30 minuti, ma l'ultima esecuzione
registrata e' del 13/09»* -- undici giorni, segnalata come anomalia. Il
proprietario: **e' giusto che sia ferma, e' disabilitata**.

E aveva ragione: `automation.attiva_antimosche_alba` sta a `off`, ed e'
l'unica delle 17 automazioni della casa che ci sta. Lo stato era nello
specchio, in `behavior_states`; `reread()` lo leggeva e lo buttava via
costruendo la voce con `id`, `tipo`, `nome` e `corpo`. Cosi' una scelta del
proprietario e un guasto diventavano indistinguibili, e HIRIS allarmava su
una cosa voluta -- il rumore sano che seppellisce la rotta.

**Perche' il campo esiste solo per le automazioni.** Per un'automazione
`off` vuol dire *disabilitata*; per uno script vuol dire *non in esecuzione
in questo istante*. Sono due fatti diversi detti con la stessa parola, e
darli allo stesso campo insegnerebbe al modello a leggere uno script fermo
-- cioe' ogni script, quasi sempre -- come uno script spento.
"""
import pytest

from hiris.app.home_space.behavior import _BEHAVIOR_DOMAINS, reread


class FintoHomeSpace:
    """Raccoglie cio' che `reread()` deposita, senza archivio."""

    def __init__(self):
        self.voci = None

    def behavior(self):
        return self.voci or []

    def hold_behavior(self, entries, problems=None, unread_bodies=None):
        self.voci = entries


class FintoClient:
    def __init__(self, states):
        self._states = states

    async def get_states(self, entity_ids):
        # `[]` significa «tutte»: la convenzione di `HAClient.get_states`.
        return self._states

    async def behavior_configs(self, entity_ids):
        return {"configurazioni": {e: {"alias": "x"} for e in entity_ids}}


def _stato(entity_id: str, state: str, nome: str) -> dict:
    return {"entity_id": entity_id, "state": state,
            "attributes": {"friendly_name": nome}}


@pytest.fixture
def casa():
    return FintoHomeSpace()


async def _rileggi(casa, states, tmp_path):
    (tmp_path / "secrets.yaml").write_text("", encoding="utf-8")
    return await reread(FintoClient(states), casa, tmp_path)


@pytest.mark.asyncio
async def test_un_automazione_spenta_si_dichiara(casa, tmp_path):
    """Il caso vero: l'antimosche."""
    await _rileggi(casa, [
        _stato("automation.attiva_antimosche_alba", "off", "Gestione antimosche"),
        _stato("automation.rifiuti_carta", "on", "Gestione Rifiuto Carta"),
    ], tmp_path)
    per_id = {v["id"]: v for v in casa.behavior()}
    assert per_id["automation.attiva_antimosche_alba"]["attiva"] is False
    assert per_id["automation.rifiuti_carta"]["attiva"] is True


@pytest.mark.asyncio
async def test_uno_script_non_porta_il_campo(casa, tmp_path):
    """Uno script «off» non e' spento: e' semplicemente fermo adesso."""
    await _rileggi(casa, [_stato("script.buonanotte", "off", "Buonanotte")], tmp_path)
    voce = casa.behavior()[0]
    assert voce["tipo"] == "script"
    assert "attiva" not in voce


@pytest.mark.asyncio
async def test_uno_stato_sconosciuto_non_diventa_spenta(casa, tmp_path):
    """`unavailable` non e' `off`: un'automazione che Home Assistant non sa
    rendere non e' stata disabilitata dal proprietario, e dire «attiva:
    false» sarebbe inventare una sua scelta.
    """
    await _rileggi(casa, [
        _stato("automation.rotta", "unavailable", "Rotta")], tmp_path)
    assert "attiva" not in casa.behavior()[0]


def test_i_domini_del_comportamento_restano_due():
    """La guardia del campo: se un giorno entra un terzo dominio, chi lo
    aggiunge deve decidere cosa significa «attiva» per lui invece di
    ereditare in silenzio la regola dell'automazione."""
    assert set(_BEHAVIOR_DOMAINS) == {"automation", "script"}


# --------------------------------------------------------------------------
# Il campo non serve a niente se non arriva dove il modello guarda
# --------------------------------------------------------------------------

def test_la_riga_del_nucleo_dice_che_e_disabilitata():
    """`_behavior_lines` costruisce cio' che il modello legge a OGNI turno.

    Il campo `attiva` nell'archivio non basta: se la riga del nucleo non lo
    porta, il modello continua a vedere un'automazione uguale a tutte le
    altre e a chiamare «ferma da undici giorni» una che e' stata spenta.
    """
    from hiris.app.home_space.briefing import _behavior_lines

    righe, _pesi = _behavior_lines([
        {"id": "automation.antimosche", "nome": "Gestione antimosche",
         "tipo": "automazione", "corpo": {"alias": "x"}, "attiva": False},
        {"id": "automation.carta", "nome": "Gestione Rifiuto Carta",
         "tipo": "automazione", "corpo": {"alias": "x"}, "attiva": True},
    ])
    assert "disabilitata" in righe[0]
    assert "disabilitata" not in righe[1]


def test_una_voce_senza_il_campo_non_cambia_riga():
    """Gli script, e ogni voce letta prima che il campo esistesse, non
    devono guadagnare una dichiarazione che nessuno ha misurato."""
    from hiris.app.home_space.briefing import _behavior_lines

    righe, _pesi = _behavior_lines([
        {"id": "script.buonanotte", "nome": "Buonanotte", "tipo": "script",
         "corpo": {"alias": "x"}},
    ])
    assert "disabilitata" not in righe[0]
