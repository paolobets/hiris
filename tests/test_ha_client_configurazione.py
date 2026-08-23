"""Le primitive del canale di configurazione: nude, e il rifiuto porta il motivo."""
import pytest

from hiris.app.proxy.ha_client import HAClient


class FintaRisposta:
    def __init__(self, payload, stato=200, testo=None):
        self._payload = payload
        self._testo = testo
        self.status = stato

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        if self._testo is not None:
            return self._testo
        import json as _json
        return _json.dumps(self._payload)


class FintaSessione:
    """Registra le chiamate e risponde sempre la stessa cosa."""

    def __init__(self, payload, stato=200, testo=None):
        self._payload = payload
        self._stato = stato
        self._testo = testo
        self.chiamate = []

    def post(self, url, json=None):
        self.chiamate.append(("POST", url, json))
        return FintaRisposta(self._payload, self._stato, self._testo)

    def get(self, url):
        self.chiamate.append(("GET", url, None))
        return FintaRisposta(self._payload, self._stato, self._testo)

    def delete(self, url):
        self.chiamate.append(("DELETE", url, None))
        return FintaRisposta(self._payload, self._stato, self._testo)


def _client():
    return HAClient("http://ha.local:8123", "token")


@pytest.mark.asyncio
async def test_salva_compone_la_rotta_dell_editor():
    c = _client()
    c._session = FintaSessione({"result": "ok"})
    esito = await c.salva_configurazione("automation", "1771346155970", {"alias": "X"})
    metodo, url, corpo = c._session.chiamate[0]
    assert metodo == "POST"
    assert url == "http://ha.local:8123/api/config/automation/config/1771346155970"
    assert corpo == {"alias": "X"}
    assert esito == {"salvato": True}


@pytest.mark.asyncio
async def test_il_rifiuto_di_home_assistant_torna_col_motivo_non_come_eccezione():
    """Il 400 di HA E' il valore di prodotto (spec §2.5): non si solleva, si legge."""
    c = _client()
    c._session = FintaSessione(
        {"message": "Message malformed: required key not provided @ data['triggers']"},
        stato=400)
    esito = await c.salva_configurazione("automation", "123", {})
    assert "salvato" not in esito
    assert "triggers" in esito["errore"]


@pytest.mark.asyncio
async def test_una_chiave_ostile_non_arriva_mai_nell_url():
    c = _client()
    c._session = FintaSessione({"result": "ok"})
    esito = await c.salva_configurazione("automation", "../../core/config", {})
    assert c._session.chiamate == []
    assert "chiave" in esito["errore"]


@pytest.mark.asyncio
async def test_un_dominio_fuori_dai_tre_non_si_scrive():
    c = _client()
    c._session = FintaSessione({"result": "ok"})
    esito = await c.salva_configurazione("light", "x", {})
    assert c._session.chiamate == []
    assert "light" in esito["errore"]


@pytest.mark.asyncio
async def test_leggi_restituisce_il_corpo():
    c = _client()
    c._session = FintaSessione({"id": "123", "alias": "Tapparelle"})
    assert (await c.leggi_configurazione("automation", "123"))["corpo"]["alias"] == "Tapparelle"


@pytest.mark.asyncio
async def test_leggi_distingue_il_non_c_e_dal_non_ho_potuto_leggere():
    """«Assente» e «errore» non sono la stessa cosa: chi genera un id nuovo usa
    questa differenza per non scrivere sopra un'automazione esistente quando
    Home Assistant sta rispondendo male."""
    c = _client()
    c._session = FintaSessione({"message": "not found"}, stato=404)
    assert await c.leggi_configurazione("automation", "999") == {"assente": True}
    c._session = FintaSessione({"message": "boom"}, stato=500)
    esito = await c.leggi_configurazione("automation", "999")
    assert "errore" in esito
    assert "assente" not in esito


@pytest.mark.asyncio
async def test_cancella_usa_il_metodo_delete():
    c = _client()
    c._session = FintaSessione({"result": "ok"})
    esito = await c.cancella_configurazione("script", "buonanotte")
    metodo, url, _ = c._session.chiamate[0]
    assert metodo == "DELETE"
    assert url == "http://ha.local:8123/api/config/script/config/buonanotte"
    assert esito == {"cancellato": True}


@pytest.mark.asyncio
async def test_valida_manda_solo_le_chiavi_presenti_e_riporta_l_esito(monkeypatch):
    c = _client()
    visti = {}

    async def finto(msg_type, extra=None, timeout=10.0):
        visti["tipo"] = msg_type
        visti["extra"] = extra
        return {"success": True, "result": {
            "triggers": {"valid": False, "error": "Unknown trigger 'quando'"}}}

    monkeypatch.setattr(c, "_ws_command", finto)
    esito = await c.valida_config(triggers=[{"trigger": "quando"}])
    assert visti["tipo"] == "validate_config"
    assert visti["extra"] == {"triggers": [{"trigger": "quando"}]}
    assert "conditions" not in visti["extra"]
    assert esito["triggers"]["valid"] is False


@pytest.mark.asyncio
async def test_valida_senza_risposta_non_dichiara_valido(monkeypatch):
    """Il silenzio di HA non e' un «va bene»: e' un errore dichiarato."""
    c = _client()

    async def muto(msg_type, extra=None, timeout=10.0):
        return None

    monkeypatch.setattr(c, "_ws_command", muto)
    esito = await c.valida_config(actions=[{"action": "light.turn_on"}])
    assert "errore" in esito
    assert "valid" not in str(esito.get("actions", ""))
