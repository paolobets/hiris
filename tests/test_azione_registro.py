"""Il registro dei servizi: cosa Home Assistant sa fare, in questa casa.

Task 1 della fetta «comandare». Copre tre cose distinte:

1. il **lettore** (`HAClient.get_services`), che apre `/api/services`;
2. il **registro** (`ServiceRegistry`), che tiene quella risposta in memoria
   e non solleva mai su cio' che non c'e';
3. la **freschezza** (`ensure_fresh`), perche' le integrazioni di Home
   Assistant si installano a caldo e un registro letto una volta sola
   diventa una bugia in attesa.

Nota sulla forma della risposta: `RISPOSTA_HA` qui sotto e' la forma
**attesa** di `/api/services`, non una misurata su un'installazione vera (al
momento della scrittura non c'era accesso a una). Per questo il parser e' e
deve restare difensivo, ed esiste
`test_una_risposta_malformata_non_solleva`: se la forma vera differisce,
HIRIS resta muto invece di rompersi.
"""
import inspect

import pytest

from hiris.app.azione.registro import ServiceRegistry
from hiris.app.proxy.ha_client import HAClient

RISPOSTA_HA = [
    {"domain": "light", "services": {
        "turn_on": {"fields": {"brightness_pct": {}, "transition": {}},
                    "target": {"entity": [{"domain": ["light"]}]}},
        "turn_off": {"fields": {"transition": {}}, "target": {"entity": [{"domain": ["light"]}]}},
    }},
    {"domain": "switch", "services": {"turn_on": {"fields": {}, "target": {}}}},
]


class FintoClient:
    def __init__(self, risposta):
        self.risposta = risposta
        self.chiamate = 0

    async def get_services(self):
        self.chiamate += 1
        return self.risposta


def test_il_finto_combacia_con_la_firma_vera():
    """La rete contro la deriva: se `HAClient.get_services` cambia firma,
    questo test cade invece di lasciare che il finto menta -- stesso metodo
    gia' usato per `get_states` in `test_casa_comportamento.py`."""
    vera = inspect.signature(HAClient.get_services)
    finta = inspect.signature(FintoClient.get_services)
    assert list(vera.parameters) == list(finta.parameters)


@pytest.mark.asyncio
async def test_il_registro_conosce_i_servizi_che_esistono():
    registro = ServiceRegistry()
    await registro.refresh(FintoClient(RISPOSTA_HA))
    assert registro.service("light", "turn_on") is not None
    assert sorted(registro.services_for("light")) == ["turn_off", "turn_on"]
    assert "switch" in registro.domains()


@pytest.mark.asyncio
async def test_il_registro_non_inventa_cio_che_non_c_e():
    registro = ServiceRegistry()
    await registro.refresh(FintoClient(RISPOSTA_HA))
    assert registro.service("light", "esplodi") is None
    assert registro.service("inesistente", "turn_on") is None
    assert registro.services_for("inesistente") == []


@pytest.mark.asyncio
async def test_un_registro_mai_caricato_lo_dichiara():
    registro = ServiceRegistry()
    assert registro.empty() is True
    assert registro.age_seconds() is None
    # e non solleva: chi lo interroga prima del caricamento riceve None,
    # non un'eccezione
    assert registro.service("light", "turn_on") is None


@pytest.mark.asyncio
async def test_una_risposta_malformata_non_solleva():
    registro = ServiceRegistry()
    await registro.refresh(FintoClient([{"domain": "light"}, {"services": {}}, "spazzatura"]))
    assert registro.service("light", "turn_on") is None
    assert registro.empty() is False  # ha caricato: e' vuoto di CONTENUTO, non di tentativo


@pytest.mark.asyncio
async def test_una_voce_di_servizio_che_non_e_un_dizionario_non_solleva():
    """La forma di `/api/services` e' un'ipotesi (vedi il docstring del
    modulo): se il dettaglio di un servizio non fosse un dizionario, il
    servizio deve restare *conoscibile* -- esiste, non sappiamo com'e'
    fatto -- e non far cadere l'intero dominio."""
    registro = ServiceRegistry()
    await registro.refresh(FintoClient(
        [{"domain": "light", "services": {"turn_on": "non un dizionario", "turn_off": {}}}]
    ))
    assert registro.service("light", "turn_on") == {}
    assert sorted(registro.services_for("light")) == ["turn_off", "turn_on"]


@pytest.mark.asyncio
async def test_un_aggiornamento_sostituisce_e_non_accumula():
    """Il registro e' lo SPECCHIO di `/api/services`, non un archivio che
    cresce: un'integrazione disinstallata deve sparire anche da qui, o HIRIS
    continuerebbe a credere possibile un servizio che non c'e' piu'."""
    registro = ServiceRegistry()
    finto = FintoClient(RISPOSTA_HA)
    await registro.refresh(finto)
    finto.risposta = [{"domain": "light", "services": {"turn_on": {}}}]
    await registro.refresh(finto)
    assert registro.domains() == ["light"]
    assert registro.services_for("light") == ["turn_on"]


@pytest.mark.asyncio
async def test_il_registro_si_rinfresca_quando_e_vecchio():
    finto = FintoClient(RISPOSTA_HA)
    registro = ServiceRegistry(max_age_s=100)
    await registro.ensure_fresh(finto)
    await registro.ensure_fresh(finto)
    assert finto.chiamate == 1, "un registro fresco non si ricarica"

    registro._caricato_a -= 200  # lo invecchiamo a mano
    await registro.ensure_fresh(finto)
    assert finto.chiamate == 2, "un registro vecchio si ricarica"


@pytest.mark.asyncio
async def test_se_il_rinfresco_fallisce_si_tiene_il_vecchio():
    class ClientCheRompe(FintoClient):
        async def get_services(self):
            self.chiamate += 1
            if self.chiamate > 1:
                raise RuntimeError("HA non risponde")
            return self.risposta

    finto = ClientCheRompe(RISPOSTA_HA)
    registro = ServiceRegistry(max_age_s=100)
    await registro.ensure_fresh(finto)
    registro._caricato_a -= 200
    await registro.ensure_fresh(finto)   # non deve sollevare
    assert registro.service("light", "turn_on") is not None, (
        "un rinfresco fallito non deve svuotare cio' che sapevamo")


@pytest.mark.asyncio
async def test_se_il_primo_caricamento_fallisce_il_guasto_si_vede():
    """L'altra faccia del test qui sopra: tenersi il vecchio ha senso solo
    se un vecchio c'e'. Al primo caricamento non c'e' niente da proteggere,
    e ingoiare l'errore renderebbe un registro mai caricato
    indistinguibile da uno caricato e vuoto -- il silenzio non dichiarato
    che questo ramo esiste per chiudere."""
    class ClientSempreRotto(FintoClient):
        async def get_services(self):
            self.chiamate += 1
            raise RuntimeError("HA non risponde")

    registro = ServiceRegistry(max_age_s=100)
    with pytest.raises(RuntimeError):
        await registro.ensure_fresh(ClientSempreRotto(RISPOSTA_HA))
    assert registro.empty() is True


@pytest.mark.asyncio
async def test_l_eta_cresce_e_parte_da_zero_al_caricamento():
    registro = ServiceRegistry()
    await registro.refresh(FintoClient(RISPOSTA_HA))
    eta = registro.age_seconds()
    assert eta is not None and eta < 5.0
    registro._caricato_a -= 42
    assert registro.age_seconds() >= 42


@pytest.mark.asyncio
async def test_get_services_legge_l_endpoint_dei_servizi():
    """Il lettore vero: `/api/services` e nient'altro. Senza questo test
    l'URL sbagliato passerebbe la suite e fallirebbe solo sulla casa vera."""
    from unittest.mock import AsyncMock, MagicMock

    client = HAClient(base_url="http://supervisor/core", token="t")
    risposta = AsyncMock()
    risposta.raise_for_status = MagicMock()
    risposta.json = AsyncMock(return_value=RISPOSTA_HA)
    client._session = MagicMock()
    client._session.get = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=risposta),
        __aexit__=AsyncMock(return_value=False),
    ))

    assert await client.get_services() == RISPOSTA_HA
    (url,), _ = client._session.get.call_args
    assert url == "http://supervisor/core/api/services"
    assert risposta.raise_for_status.called, (
        "un 401/500 deve sollevare, non diventare un registro vuoto")


def test_il_registro_e_agganciato_all_app():
    """Pin sorgente sull'aggancio in `_on_startup` (stessa tecnica dei pin
    di wiring gia' presenti in `tests/test_coverage_wiring.py`): senza
    questa riga il registro esiste ma nessuno lo trova, e HIRIS resta cieco
    su cio' che HA sa fare."""
    from hiris.app import server

    assert server.ServiceRegistry is ServiceRegistry
    assert 'app["registro_servizi"] = ServiceRegistry()' in inspect.getsource(
        server._on_startup)


# --- la forma di `fields`, un livello piu' sotto ----------------------------
#
# R-1 e R-2 della review della fetta. Il parser era difensivo sulla forma
# ESTERNA (lista, voci, domini) e cieco su quella INTERNA: il docstring del
# modulo prometteva che «ogni chiave e ogni tipo sono verificati prima
# dell'uso» ed era falso di un livello. Due esiti misurati, non ipotesi.

@pytest.mark.asyncio
async def test_i_campi_a_sezioni_salgono_di_un_livello():
    """R-2. Da Home Assistant 2024.6 i campi avanzati arrivano raggruppati in
    sezioni. Letti piatti, `rgbw_color` -- un parametro **vero** -- veniva
    rifiutato, e al modello si offriva `advanced_fields` come «uno di quelli
    veri»: un rifiuto sbagliato e un nome interno spacciato per parametro,
    nella stessa frase."""
    registro = ServiceRegistry()
    await registro.refresh(FintoClient([{"domain": "light", "services": {"turn_on": {"fields": {
        "brightness_pct": {"selector": {}},
        "advanced_fields": {"collapsed": True, "fields": {"rgbw_color": {}, "effect": {}}},
    }}}}]))
    campi = registro.service("light", "turn_on")["fields"]
    assert sorted(campi) == ["brightness_pct", "effect", "rgbw_color"]
    assert "advanced_fields" not in campi, (
        "il nome della sezione non e' un parametro: offerto al modello, lo "
        "proverebbe e riceverebbe un secondo rifiuto")


@pytest.mark.asyncio
async def test_appiattire_non_tocca_i_campi_gia_piatti():
    """La difesa dev'essere innocua dove le sezioni non ci sono -- che e' la
    sola forma che qualcuno abbia mai scritto in una finta."""
    registro = ServiceRegistry()
    await registro.refresh(FintoClient(RISPOSTA_HA))
    assert sorted(registro.service("light", "turn_on")["fields"]) == [
        "brightness_pct", "transition"]
    assert registro.service("switch", "turn_on")["fields"] == {}


@pytest.mark.asyncio
async def test_un_campo_che_non_e_una_mappa_diventa_none_e_non_solleva():
    """R-1. `fields` che non e' una mappa (p.es. una lista di oggetti) faceva
    risalire un `TypeError` da `ActionActuator.execute`, e il modello riceveva
    «unhashable type: 'dict'» come **motivo del rifiuto**: un errore Python
    travestito da spiegazione.

    `None`, non `{}`: `{}` significa «letto, nessun parametro» e autorizza a
    rifiutare un parametro in piu'. Qui non abbiamo letto niente."""
    registro = ServiceRegistry()
    await registro.refresh(FintoClient(
        [{"domain": "light", "services": {"turn_on": {"fields": [{"name": "brightness_pct"}]}}}]))
    assert registro.service("light", "turn_on")["fields"] is None
    assert registro.services_for("light") == ["turn_on"], (
        "il servizio esiste: una forma non capita non deve farlo sparire")


@pytest.mark.asyncio
async def test_un_servizio_senza_campi_non_ne_guadagna_uno_finto():
    """Il registro e' lo SPECCHIO di `/api/services`: aggiungere una chiave che
    Home Assistant non ha mandato sarebbe insegnare invece di specchiare."""
    registro = ServiceRegistry()
    await registro.refresh(FintoClient(
        [{"domain": "light", "services": {"turn_on": {"target": {}}, "toggle": {}}}]))
    assert registro.service("light", "turn_on") == {"target": {}}
    assert registro.service("light", "toggle") == {}


@pytest.mark.asyncio
async def test_una_risposta_letta_e_non_capita_lo_dice(caplog):
    """m-3 della review. Una risposta che c'era e da cui non si e' capito
    niente e' l'unico esito che il resto del prodotto non sa raccontare:
    all'utente si dice «non sono riuscito a leggerlo, riprova fra poco» -- per
    sempre -- e nel log c'era solo `INFO: 0 domini, 0 servizi`, che assomiglia
    a una casa senza servizi. E' il fallimento numero 1 del foglio delle prove;
    chi non ha il foglio in mano deve poterlo diagnosticare dal log."""
    import logging
    registro = ServiceRegistry()
    with caplog.at_level(logging.WARNING, logger="hiris.app.azione.registro"):
        # un dizionario, non una lista
        await registro.refresh(FintoClient({"light": {"turn_on": {}}}))
    assert registro.domains() == []
    assert any("non e' quella attesa" in r.getMessage() for r in caplog.records), caplog.text


@pytest.mark.asyncio
async def test_una_casa_senza_servizi_non_viene_dichiarata_un_guasto(caplog):
    """Il complemento: la diagnosi qui sopra deve distinguere «non ho capito»
    da «non c'era niente da capire», o sarebbe un allarme che urla sempre."""
    import logging
    registro = ServiceRegistry()
    with caplog.at_level(logging.WARNING, logger="hiris.app.azione.registro"):
        await registro.refresh(FintoClient([]))
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
