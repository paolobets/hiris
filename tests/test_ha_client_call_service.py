import pytest

from hiris.app.proxy.ha_client import HAClient


class FintaRisposta:
    def __init__(self, payload, stato=200):
        self._payload = payload
        self.status = stato

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self._payload


class FintaSessione:
    def __init__(self, payload, stato=200):
        self.payload = payload
        self.stato = stato
        self.chiamate = []

    def post(self, url, json=None):
        self.chiamate.append((url, json))
        return FintaRisposta(self.payload, self.stato)


@pytest.mark.asyncio
async def test_call_service_compone_url_e_corpo():
    client = HAClient("http://ha.local:8123", "token")
    client._session = FintaSessione([{"entity_id": "light.salotto", "state": "off"}])
    cambiati = await client.call_service(
        "light", "turn_off", {"entity_id": "light.salotto"})
    url, corpo = client._session.chiamate[0]
    assert url == "http://ha.local:8123/api/services/light/turn_off"
    assert corpo == {"entity_id": "light.salotto"}
    assert cambiati == [{"entity_id": "light.salotto", "state": "off"}]


@pytest.mark.asyncio
async def test_call_service_propaga_il_rifiuto_di_home_assistant():
    client = HAClient("http://ha.local:8123", "token")
    client._session = FintaSessione({}, stato=400)
    with pytest.raises(RuntimeError):
        await client.call_service("light", "turn_off", {"entity_id": "light.x"})


# -- la forma della risposta, che nessuno aveva mai misurata (2.2.1) --------
#
# Il ritorno di questa funzione ha smesso di essere decorativo: e' la fonte
# del «dopo» di `azione/porta.py`, cioe' l'unica misura del prodotto presa nel
# momento giusto. Da qui in avanti una forma buttata via in silenzio non e'
# piu' un dato inutilizzato: e' un comando riuscito raccontato come fallito.

@pytest.mark.asyncio
async def test_la_forma_con_changed_states_non_viene_buttata_via():
    """Da Home Assistant 2023.7, un servizio con dati di risposta risponde una
    MAPPA (`{"changed_states": [...], "service_response": {...}}`) invece della
    lista storica. HIRIS non chiede `return_response` e quindi si aspetta la
    lista -- ma il codice di prima (`isinstance(..., list) else []`) su quella
    mappa avrebbe buttato via proprio gli stati cambiati, cioe' avrebbe fatto
    dire «non e' cambiato niente» a un comando riuscito."""
    client = HAClient("http://ha.local:8123", "token")
    client._session = FintaSessione({
        "changed_states": [{"entity_id": "light.salotto", "state": "off"}],
        "service_response": {"qualcosa": 1}})
    cambiati = await client.call_service("light", "turn_off", {})
    assert cambiati == [{"entity_id": "light.salotto", "state": "off"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, {}, "una stringa", 42,
                                     {"changed_states": "non una lista"}])
async def test_una_forma_che_non_si_sa_leggere_diventa_nessun_cambiamento(payload):
    """Difensiva come il lettore del registro: cio' che non si sa leggere
    diventa «nessun cambiamento riportato», mai un'eccezione e mai un dato
    indovinato. L'entita' ricadra' sullo specchio, e al peggio sull'onesto
    «non so dire cosa sia cambiato»."""
    client = HAClient("http://ha.local:8123", "token")
    client._session = FintaSessione(payload)
    assert await client.call_service("light", "turn_off", {}) == []


@pytest.mark.asyncio
async def test_cio_che_non_e_uno_stato_viene_saltato():
    client = HAClient("http://ha.local:8123", "token")
    client._session = FintaSessione(["non un dizionario", {"senza": "id"},
                                     {"entity_id": "light.salotto", "state": "off"}])
    assert await client.call_service("light", "turn_off", {}) == [
        {"entity_id": "light.salotto", "state": "off"}]


@pytest.mark.asyncio
async def test_la_forma_vera_viene_dichiarata_nel_log_al_primo_uso(caplog):
    """La disciplina della prova 1 del foglio (`docs/prova-azione.md`), qui
    applicata alla seconda forma non misurata: invece di indovinare com'e'
    fatta, la si dichiara nel log alla prima chiamata su un impianto vero,
    cosi' la prossima prova sulla casa ce lo DICE."""
    import hiris.app.proxy.ha_client as modulo

    modulo._changed_form_declared = False
    client = HAClient("http://ha.local:8123", "token")
    client._session = FintaSessione([
        {"entity_id": "light.salotto", "state": "off", "attributes": {}}])
    with caplog.at_level("INFO", logger="hiris.app.proxy.ha_client"):
        await client.call_service("light", "turn_off", {})
        righe = [r.getMessage() for r in caplog.records
                 if "call_service: la risposta" in r.getMessage()]
        assert len(righe) == 1, "la forma non viene dichiarata al primo uso"
        assert "'entity_id'" in righe[0] and "'state'" in righe[0], (
            "la riga non porta le chiavi vere: dichiarare che «c'e' una "
            "risposta» senza dire com'e' fatta non misura niente")
        # e una volta sola: un log per ogni comando della casa sarebbe rumore
        caplog.clear()
        await client.call_service("light", "turn_off", {})
        assert not [r for r in caplog.records
                    if "call_service: la risposta" in r.getMessage()]
