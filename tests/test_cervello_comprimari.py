"""Chi sta insieme a chi -- e non si indovina dal nome.

Il caso misurato: `light.lampadario_fake_lampadario_fake` sembrava un residuo di
prova. E' l'interruttore fisico che comanda il gruppo LIFX, e `legami` dice che
e' l'innesco di `automation.interruttore_gruppo_lifx`. Quelle quattro entita'
nascoste sono UN SISTEMA SOLO.
"""
import pytest

from hiris.app.server import costruisci_comprimari


class _FintoHA:
    def __init__(self, risposte):
        self.risposte = risposte
        self.chiesti = []

    async def legami(self, tipo, identificatore):
        self.chiesti.append((tipo, identificatore))
        return self.risposte.get(identificatore, {"legami": {}})


@pytest.mark.asyncio
async def test_i_comprimari_arrivano_da_legami():
    ha = _FintoHA({"climate.camera_t": {"legami": {
        "entita": ["sensor.camera_temperatura"], "area": ["camera_da_letto"]}}})
    mappa = await costruisci_comprimari(ha, ["climate.camera_t"])
    assert mappa["climate.camera_t"] == ["sensor.camera_temperatura"]


@pytest.mark.asyncio
async def test_aree_piani_e_dispositivi_NON_sono_comprimari():
    """Un'area non e' una cosa che fa qualcosa mentre il termostato scalda:
    e' dove sta. Metterla fra i comprimari riempirebbe ogni oggetto di
    identificatori che non misurano niente."""
    ha = _FintoHA({"climate.camera_t": {"legami": {
        "area": ["camera"], "piano": ["terra"], "dispositivo": ["abc"],
        "integrazione": ["ave_domina"], "entita": ["sensor.t"]}}})
    mappa = await costruisci_comprimari(ha, ["climate.camera_t"])
    assert mappa["climate.camera_t"] == ["sensor.t"]


@pytest.mark.asyncio
async def test_un_guasto_di_sistema_non_si_chiede_a_legami():
    """`problema:sonos.x` non e' un'entita' di Home Assistant: chiederlo
    produrrebbe una chiamata di rete per ogni guasto, tutte fallite."""
    ha = _FintoHA({})
    mappa = await costruisci_comprimari(ha, ["problema:sonos.x", "integrazione:abc"])
    assert mappa == {}
    assert ha.chiesti == []


@pytest.mark.asyncio
async def test_un_guasto_di_legami_non_ferma_l_aggregazione():
    """Se `legami` non risponde si perdono i comprimari, non la giornata: un
    oggetto senza contesto e' peggio di uno completo, ma infinitamente meglio
    di nessun oggetto."""
    class _Rotto:
        async def legami(self, tipo, identificatore):
            return {"errore": "Home Assistant non ha risposto"}

    mappa = await costruisci_comprimari(_Rotto(), ["climate.camera_t"])
    assert mappa == {"climate.camera_t": []}


@pytest.mark.asyncio
async def test_si_chiede_una_volta_sola_per_soggetto():
    """L'aggregazione chiama i comprimari dentro un ciclo: una chiamata di rete
    per ogni cambio farebbe migliaia di richieste per una giornata."""
    ha = _FintoHA({})
    await costruisci_comprimari(ha, ["climate.a", "climate.a", "climate.b"])
    assert len(ha.chiesti) == 2
