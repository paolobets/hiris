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
    from hiris.app.casa.archivio import HomeSpaceStore
    from hiris.app.memoria.resolver import costruisci_indice

    a = HomeSpaceStore(str(tmp_path / "casa.db"))
    try:
        a.replace({"entita": [
            {"entity_id": "light.salotto", "name": "Piantana",
             "aliases": ["lampada della nonna"]},
        ]}, [])
        indice = costruisci_indice(a.read())
        trovati = indice.find("lampada della nonna")
        candidati = [c for t in trovati for c in t["candidati"]]
        assert {"tipo": "entita", "riferimento": "light.salotto"} in candidati
    finally:
        a.close()


@pytest.mark.asyncio
async def test_il_None_di_home_assistant_non_e_un_alias():
    """LA SENTINELLA, e il difetto vero trovato sull'impianto il 2026-08-18.

    Home Assistant dichiara `_serialize_aliases(...) -> list[str | None]` e
    mappa `COMPUTED_NAME` su `None` (`helpers/entity_registry.py`, verificato):
    quel `null` significa «qui va il nome calcolato», che HIRIS ha gia'
    (`original_name`). Non e' una parola che qualcuno ha scritto.

    Preso alla lettera ha riempito l'archivio -- 1030 entita' su 1223 con
    `alias: [null]` -- e ha ucciso `cerca` e `ricorda`, gli unici due che
    costruiscono l'indice: «'NoneType' object has no attribute 'lower'» su
    OGNI chiamata.

    E' il `carbon_monoxide` in un'altra forma: avevo verificato CHE `aliases`
    esistesse in `extended_dict`, non COSA possono contenere i suoi elementi.
    Il tipo lo diceva.
    """
    finto = _Client(estese={"light.salotto": {
        "aliases": [None, "lampada della nonna", "  ", 42]}})
    registri, _ = await _client_vero(finto).leggi_registri()
    assert registri["entita"][0]["aliases"] == ["lampada della nonna"]


@pytest.mark.asyncio
async def test_una_lista_di_sole_sentinelle_non_diventa_un_alias_vuoto():
    """`[None]` deve sparire del tutto, non diventare `[]` salvato: la chiave
    resta assente, come per un'entita' che alias non ne ha."""
    finto = _Client(estese={"light.salotto": {"aliases": [None]}})
    registri, _ = await _client_vero(finto).leggi_registri()
    assert "aliases" not in registri["entita"][0]


def test_l_indice_sopravvive_a_un_archivio_gia_avvelenato():
    """Difesa in profondita', e serve davvero: la causa si chiude a monte, ma
    un'installazione gia' avvelenata tiene `[null]` in archivio finche'
    l'anagrafe non si ricostruisce. Un indice che muore sul dato vecchio
    lascia `cerca` e `ricorda` rotti fino al riavvio successivo."""
    from hiris.app.memoria.resolver import costruisci_indice

    casa = {"entita": [
        {"id": "light.salotto", "nome": "Piantana", "alias": [None, "nonna"]},
    ]}
    indice = costruisci_indice(casa)
    trovati = indice.find("nonna")
    candidati = [c for t in trovati for c in t["candidati"]]
    assert {"tipo": "entita", "riferimento": "light.salotto"} in candidati
    assert indice.find("piantana"), "il nome vero deve restare cercabile"
