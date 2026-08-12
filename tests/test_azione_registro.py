"""Il registro dei servizi: cosa Home Assistant sa fare, in questa casa.

Task 1 della fetta «comandare». Copre tre cose distinte:

1. il **lettore** (`HAClient.get_services`), che apre `/api/services`;
2. il **registro** (`RegistroServizi`), che tiene quella risposta in memoria
   e non solleva mai su cio' che non c'e';
3. la **freschezza** (`assicura_fresco`), perche' le integrazioni di Home
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

from hiris.app.azione.registro import RegistroServizi
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
    registro = RegistroServizi()
    await registro.aggiorna(FintoClient(RISPOSTA_HA))
    assert registro.servizio("light", "turn_on") is not None
    assert sorted(registro.servizi_di("light")) == ["turn_off", "turn_on"]
    assert "switch" in registro.domini()


@pytest.mark.asyncio
async def test_il_registro_non_inventa_cio_che_non_c_e():
    registro = RegistroServizi()
    await registro.aggiorna(FintoClient(RISPOSTA_HA))
    assert registro.servizio("light", "esplodi") is None
    assert registro.servizio("inesistente", "turn_on") is None
    assert registro.servizi_di("inesistente") == []


@pytest.mark.asyncio
async def test_un_registro_mai_caricato_lo_dichiara():
    registro = RegistroServizi()
    assert registro.vuoto() is True
    assert registro.eta_secondi() is None
    # e non solleva: chi lo interroga prima del caricamento riceve None,
    # non un'eccezione
    assert registro.servizio("light", "turn_on") is None


@pytest.mark.asyncio
async def test_una_risposta_malformata_non_solleva():
    registro = RegistroServizi()
    await registro.aggiorna(FintoClient([{"domain": "light"}, {"services": {}}, "spazzatura"]))
    assert registro.servizio("light", "turn_on") is None
    assert registro.vuoto() is False  # ha caricato: e' vuoto di CONTENUTO, non di tentativo


@pytest.mark.asyncio
async def test_una_voce_di_servizio_che_non_e_un_dizionario_non_solleva():
    """La forma di `/api/services` e' un'ipotesi (vedi il docstring del
    modulo): se il dettaglio di un servizio non fosse un dizionario, il
    servizio deve restare *conoscibile* -- esiste, non sappiamo com'e'
    fatto -- e non far cadere l'intero dominio."""
    registro = RegistroServizi()
    await registro.aggiorna(FintoClient(
        [{"domain": "light", "services": {"turn_on": "non un dizionario", "turn_off": {}}}]
    ))
    assert registro.servizio("light", "turn_on") == {}
    assert sorted(registro.servizi_di("light")) == ["turn_off", "turn_on"]


@pytest.mark.asyncio
async def test_un_aggiornamento_sostituisce_e_non_accumula():
    """Il registro e' lo SPECCHIO di `/api/services`, non un archivio che
    cresce: un'integrazione disinstallata deve sparire anche da qui, o HIRIS
    continuerebbe a credere possibile un servizio che non c'e' piu'."""
    registro = RegistroServizi()
    finto = FintoClient(RISPOSTA_HA)
    await registro.aggiorna(finto)
    finto.risposta = [{"domain": "light", "services": {"turn_on": {}}}]
    await registro.aggiorna(finto)
    assert registro.domini() == ["light"]
    assert registro.servizi_di("light") == ["turn_on"]


@pytest.mark.asyncio
async def test_il_registro_si_rinfresca_quando_e_vecchio():
    finto = FintoClient(RISPOSTA_HA)
    registro = RegistroServizi(eta_massima_s=100)
    await registro.assicura_fresco(finto)
    await registro.assicura_fresco(finto)
    assert finto.chiamate == 1, "un registro fresco non si ricarica"

    registro._caricato_a -= 200  # lo invecchiamo a mano
    await registro.assicura_fresco(finto)
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
    registro = RegistroServizi(eta_massima_s=100)
    await registro.assicura_fresco(finto)
    registro._caricato_a -= 200
    await registro.assicura_fresco(finto)   # non deve sollevare
    assert registro.servizio("light", "turn_on") is not None, (
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

    registro = RegistroServizi(eta_massima_s=100)
    with pytest.raises(RuntimeError):
        await registro.assicura_fresco(ClientSempreRotto(RISPOSTA_HA))
    assert registro.vuoto() is True


@pytest.mark.asyncio
async def test_l_eta_cresce_e_parte_da_zero_al_caricamento():
    registro = RegistroServizi()
    await registro.aggiorna(FintoClient(RISPOSTA_HA))
    eta = registro.eta_secondi()
    assert eta is not None and eta < 5.0
    registro._caricato_a -= 42
    assert registro.eta_secondi() >= 42


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

    assert server.RegistroServizi is RegistroServizi
    assert 'app["registro_servizi"] = RegistroServizi()' in inspect.getsource(
        server._on_startup)
