"""Gli alias delle entita': la parola con cui l'utente chiama le sue cose.

`config/entity_registry/list` risponde con `as_partial_dict`, che NON contiene
`aliases` (verificato sul sorgente di HA: stanno solo in `extended_dict`).
Quindi la colonna `alias` delle entita' era vuota su ogni casa, sempre — e la
«spina dorsale di `cerca`» reggeva solo per le AREE, che invece li mandano
davvero nel proprio registro.

Un utente che aveva scritto «lampada della nonna» come alias in Home Assistant
non trovava niente cercandola: HIRIS gli chiedeva di ripetere a parole cio' che
aveva gia' dichiarato una volta.
"""
import pytest


class _Client:
    """Un client che si comporta come Home Assistant: la lista NON manda gli
    alias, `get_entries` si'. Se la finta li mettesse nella lista, la prova non
    potrebbe fallire -- ed e' esattamente cosi' che questo difetto e' passato
    inosservato per mesi."""

    def __init__(self, estese=None, solleva=False):
        self.estese = estese
        self.solleva = solleva
        self.chiamate = []

    async def _ws_batch(self, comandi, timeout=10.0):
        risposte = []
        for tipo, _extra in comandi:
            if tipo == "config/entity_registry/list":
                risposte.append({"result": [
                    {"entity_id": "light.salotto", "name": "Piantana"},
                ]})
            else:
                risposte.append({"result": []})
        return risposte

    async def _ws_request(self, msg_type, extra=None, timeout=10.0):
        self.chiamate.append((msg_type, extra))
        if self.solleva:
            raise OSError("HA muto")
        return self.estese


def _client_vero(finto):
    from hiris.app.proxy.ha_client import HAClient
    c = HAClient.__new__(HAClient)
    c._ws_batch = finto._ws_batch
    c._ws_request = finto._ws_request
    return c


@pytest.mark.asyncio
async def test_gli_alias_arrivano_dal_comando_esteso():
    finto = _Client(estese={"light.salotto": {"aliases": ["lampada della nonna"]}})
    registri, non_disponibili = await _client_vero(finto).leggi_registri()
    assert registri["entita"][0]["aliases"] == ["lampada della nonna"]
    assert non_disponibili == []
    assert finto.chiamate[0][0] == "config/entity_registry/get_entries"
    assert finto.chiamate[0][1] == {"entity_ids": ["light.salotto"]}


@pytest.mark.asyncio
async def test_un_comando_esteso_fallito_si_dichiara():
    """Non si ingoia, e non si chiama `entita`: quella dicitura significa «il
    registro delle entita' non ha risposto», e farebbe credere alla casa di non
    avere entita' affatto."""
    finto = _Client(solleva=True)
    _registri, non_disponibili = await _client_vero(finto).leggi_registri()
    assert non_disponibili == ["entita:alias"]


@pytest.mark.asyncio
async def test_un_entita_senza_alias_non_ne_guadagna_uno_vuoto():
    finto = _Client(estese={"light.salotto": {"aliases": []}})
    registri, _ = await _client_vero(finto).leggi_registri()
    assert "aliases" not in registri["entita"][0]


@pytest.mark.asyncio
async def test_gli_alias_arrivano_fino_alla_ricerca(tmp_path):
    """La prova che conta: dall'anagrafe fino a `cerca`. Senza, l'alias
    sarebbe letto e salvato e non porterebbe a niente -- la fondamenta 4."""
    from hiris.app.casa.archivio import ArchivioCasa
    from hiris.app.memoria.riconoscitore import costruisci_indice

    a = ArchivioCasa(str(tmp_path / "casa.db"))
    try:
        a.sostituisci({"entita": [
            {"entity_id": "light.salotto", "name": "Piantana",
             "aliases": ["lampada della nonna"]},
        ]}, [])
        indice = costruisci_indice(a.leggi())
        trovati = indice.trova("lampada della nonna")
        candidati = [c for t in trovati for c in t["candidati"]]
        assert {"tipo": "entita", "riferimento": "light.salotto"} in candidati
    finally:
        a.chiudi()
