"""Helper e etichetta: il secondo canale, e la paternita' che sta in casa di HA."""
import pytest

from hiris.app.proxy.ha_client import HAClient


def _client():
    return HAClient("http://ha.local:8123", "token")


def _finto_ws(risposte):
    """`risposte` e' un dict {tipo_comando: messaggio}. Registra cosa e' stato chiesto."""
    visti = []

    async def finto(msg_type, extra=None, timeout=10.0):
        visti.append((msg_type, extra))
        return risposte.get(msg_type)

    return finto, visti


@pytest.mark.asyncio
async def test_crea_helper_usa_il_comando_del_dominio(monkeypatch):
    c = _client()
    finto, visti = _finto_ws({"input_boolean/create": {
        "success": True, "result": {"id": "modalita_notte", "name": "Modalita notte"}}})
    monkeypatch.setattr(c, "_ws_command", finto)
    esito = await c.create_helper("input_boolean", {"name": "Modalita notte"})
    assert visti[0] == ("input_boolean/create", {"name": "Modalita notte"})
    assert esito["helper"]["id"] == "modalita_notte"


@pytest.mark.asyncio
async def test_un_dominio_che_non_e_un_helper_non_si_crea(monkeypatch):
    c = _client()
    finto, visti = _finto_ws({})
    monkeypatch.setattr(c, "_ws_command", finto)
    esito = await c.create_helper("light", {"name": "X"})
    assert visti == []
    assert "light" in esito["errore"]


@pytest.mark.asyncio
async def test_cancella_helper_nomina_la_chiave_del_dominio(monkeypatch):
    """`input_boolean/delete` vuole `input_boolean_id`, non `id`: la chiave porta
    il nome del dominio (StorageCollectionWebsocket di Home Assistant)."""
    c = _client()
    finto, visti = _finto_ws({"timer/delete": {"success": True, "result": None}})
    monkeypatch.setattr(c, "_ws_command", finto)
    esito = await c.delete_helper("timer", "cottura")
    assert visti[0] == ("timer/delete", {"timer_id": "cottura"})
    assert esito == {"cancellato": True}


@pytest.mark.asyncio
async def test_un_comando_ws_fallito_non_diventa_un_successo(monkeypatch):
    c = _client()
    finto, _ = _finto_ws({"counter/create": {
        "success": False, "error": {"code": "invalid_format", "message": "name is required"}}})
    monkeypatch.setattr(c, "_ws_command", finto)
    esito = await c.create_helper("counter", {})
    assert "helper" not in esito
    assert "name is required" in esito["errore"]


@pytest.mark.asyncio
async def test_l_etichetta_si_crea_e_si_elenca(monkeypatch):
    c = _client()
    finto, visti = _finto_ws({
        "config/label_registry/list": {"success": True, "result": [
            {"label_id": "hiris", "name": "HIRIS"}]},
        "config/label_registry/create": {"success": True, "result": {
            "label_id": "hiris", "name": "HIRIS"}},
    })
    monkeypatch.setattr(c, "_ws_command", finto)
    assert (await c.list_labels())["etichette"][0]["label_id"] == "hiris"
    assert (await c.create_label("HIRIS"))["etichetta"]["label_id"] == "hiris"
    assert visti[1] == ("config/label_registry/create", {"name": "HIRIS"})


@pytest.mark.asyncio
async def test_applicare_l_etichetta_non_cancella_quelle_dell_utente(monkeypatch):
    """`config/entity_registry/update` SOSTITUISCE la lista: si legge prima e si
    unisce, o le etichette che l'utente aveva messo a mano spariscono."""
    c = _client()
    finto, visti = _finto_ws({
        "config/entity_registry/get": {"success": True, "result": {
            "entity_id": "automation.tapparelle", "labels": ["casa", "mattina"]}},
        "config/entity_registry/update": {"success": True, "result": {}},
    })
    monkeypatch.setattr(c, "_ws_command", finto)
    esito = await c.add_label_to("automation.tapparelle", "hiris")
    tipo, extra = visti[1]
    assert tipo == "config/entity_registry/update"
    assert sorted(extra["labels"]) == ["casa", "hiris", "mattina"]
    assert esito == {"applicata": True}


@pytest.mark.asyncio
async def test_se_non_si_riesce_a_leggere_le_etichette_non_si_sovrascrive(monkeypatch):
    """Non aver letto non e' «non ce n'erano»: si rinuncia e si dichiara."""
    c = _client()
    finto, visti = _finto_ws({"config/entity_registry/get": None})
    monkeypatch.setattr(c, "_ws_command", finto)
    esito = await c.add_label_to("automation.x", "hiris")
    assert [t for t, _ in visti] == ["config/entity_registry/get"]
    assert "errore" in esito
