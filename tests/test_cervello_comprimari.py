"""Chi sta insieme a chi -- e non si indovina dal nome.

Il caso misurato: `light.lampadario_fake_lampadario_fake` sembrava un residuo di
prova. E' l'interruttore fisico che comanda il gruppo LIFX, e `legami` dice che
e' l'innesco di `automation.interruttore_gruppo_lifx`. Quelle quattro entita'
nascoste sono UN SISTEMA SOLO.

**La finta e' stata riscritta per essere fedele al contratto VERO di
`HAClient.legami`** (`proxy/ha_client.py`), non a come lo descriveva il
mandato originale del Task 6 (correzione del Critical trovato dalla review
de «l'osservatore», 26/08/2026). La finta precedente accettava QUALUNQUE
`tipo` e rispondeva gia' nella busta TRADOTTA `{"legami": {...}}` -- che e'
la forma di `casa/domande.py::legami`, non quella del client. Con quella
finta, `costruisci_comprimari` poteva chiamare `ha_client.legami("entita",
...)` (la chiave ITALIANA: il client vero la rifiuta prima di toccare la
rete, perche' `RELATED_ITEM_TYPES` ha i valori inglesi) e leggere `esito["legami"]`
da una risposta che il client vero non manda mai -- **inerte in produzione,
zero chiamate di rete utili, `mappa` sempre vuota** -- e questi cinque test
restavano tutti verdi, perche' la finta non validava `tipo` e rispondeva
gia' nella forma che il codice (sbagliato) si aspettava. E' un difetto
ricorrente di questa fetta: una finta che accetta un parametro e lo ignora.

**Il ritorno e' cambiato** (correzione del CRITICAL «il grilletto non lo
preme nessuno», 26/08/2026): `costruisci_comprimari` tornava solo `mappa`.
Il contatore dei falliti esisteva gia' -- serviva al warning di log -- ma
moriva dentro la funzione: il chiamante non poteva mai sapere se il giro
era stato parziale, solo se una `Exception` era uscita -- e in generale non
esce: la `legami` vera CONTIENE i guasti di canale in `{"errore": ...}`, non
solleva. Eccetto un caso, vero anche lui: una risposta malformata fa uscire
un `TypeError` vero dalla catena vera, perche' la traduzione
(`casa/domande.py::legami`, chiamata da `costruisci_comprimari`) sta FUORI
da quel contenimento -- il quarto esito che `_ClienteLegami` sa produrre, piu'
sotto. Ora torna `(mappa, falliti)`: ogni test qui sotto legge la coppia."""
import pytest

from hiris.app.proxy.ha_client import HAClient
from hiris.app.server import costruisci_comprimari


class _ClienteLegami:
    """L'UNICA finta di `HAClient` per `legami`, importata anche da
    `test_cervello_wiring.py`.

    **Perche' una sola** (difesa-profondita-brief.md, punto 4). Prima ce
    n'erano quattro, indipendenti, fra questo file e quello -- una delle
    quali definita due volte nello stesso file -- e potevano divergere dal
    contratto vero ciascuna per conto proprio. E' esattamente cosi' che la
    finta infedele originale (quella che accettava `legami("entita", ...)`,
    la chiave ITALIANA che il client vero rifiuta, e rispondeva gia' nella
    busta tradotta `{"legami": {...}}`) e' sopravvissuta abbastanza a lungo
    da rendere invisibile il Critical dei comprimari: nessuna delle quattro
    copie l'avrebbe presa da sola, ma nessuna era IL posto dove correggerla
    una volta per tutte.

    Valida `tipo` come fa il client vero (i valori INGLESI di
    `HAClient.RELATED_ITEM_TYPES`, importati -- non ricopiati) e risponde nella
    forma GREZZA del client: chiavi inglesi, nessuna busta `{"legami": ...}`.

    Costruita sui quattro esiti che `HAClient.legami` produce davvero:

    - **risposta buona**: `mappa[identifier]` un dizionario grezzo
      (es. `{"entity": ["sensor.x"]}`);
    - **risposta vuota**: `identifier` assente da `mappa` (o mappato a
      `{}`) -- "nessun legame", non un guasto. E' anche il default quando
      non si passa `mappa`: un client che non fallisce mai e non ha niente
      da dire, per i test che vogliono la riparazione INCONDIZIONATA
      (nessun soggetto fallito). Deliberatamente non e' `ha_client=None`:
      con `None`, `costruisci_comprimari` chiamerebbe `None.legami(...)`,
      prenderebbe `AttributeError`, la CONTERREBBE e conterebbe ogni
      soggetto come fallito -- il contrario di "incondizionata";
    - **dizionario d'errore**: `mappa[identifier] = {"errore": ...}`, o
      `default={"errore": ...}` per farlo rispondere cosi' a QUALUNQUE
      identificatore senza doverli elencare tutti;
    - **risposta malformata**: `mappa[identifier]` un dizionario la cui
      traduzione (`casa/domande.py::legami`, chiamata da
      `costruisci_comprimari`) non e' contenuta -- es. `{"entity": 5}`, un
      intero al posto della lista che Home Assistant vero manda sempre. E'
      l'innesco del punto 1 (difesa-profondita-brief.md): fa uscire un
      `TypeError` vero dalla catena vera, senza monkeypatch.

    **Cresciuta il 27/08/2026 (mandato "le direzioni dell'energia") per
    fingere anche `direzioni_energia()`**, non una seconda finta a fianco:
    e' la stessa disciplina "una sola finta per `HAClient`" del paragrafo
    sopra, e i due lavori dell'aggregazione (`_aggrega_ieri`,
    `riaggrega_gli_ultimi_due_giorni`) chiamano ORA entrambi i metodi sullo
    STESSO client. `direzioni` e' la mappa che `direzioni_energia()` torna
    (default vuota: nessuna direzione nota, non un guasto); `direzioni_errore`
    -- se dato -- la fa rispondere `{"errore": ...}`, fedele al contratto
    vero (mai un dizionario vuoto travestito da «non ho potuto leggere»)."""

    def __init__(self, mappa: dict[str, dict] | None = None, *, default=None,
                direzioni: dict[str, dict] | None = None,
                direzioni_errore: str | None = None,
                statistiche: dict[str, list[dict]] | None = None,
                statistiche_errore: str | None = None,
                statistiche_per_finestra: (
                    dict[tuple[str, str], dict[str, list[dict]]] | None
                ) = None,
                ):
        self._mappa = mappa or {}
        self._default = {} if default is None else default
        self._direzioni = direzioni or {}
        self._direzioni_errore = direzioni_errore
        # `statistiche` -- **cresciuta il 27/08/2026 (mandato «il bilancio
        # dell'energia») per fingere anche `statistiche_orarie()`**, stessa
        # disciplina "una sola finta" del paragrafo sopra: `{statistic_id:
        # [punto, ...]}` gia' nella forma TRADOTTA (chiavi italiane, come le
        # manda `HAClient._request_statistics` per davvero) -- fedele al
        # contratto vero: `costruisci_bilanci` (server.py) legge SOLO il
        # ritorno di `statistiche_orarie`, mai la richiesta grezza a HA.
        self._statistiche = statistiche or {}
        self._statistiche_errore = statistiche_errore
        # `statistiche_per_finestra` -- **la decima finta corretta per
        # mutazione (mandato, punto 4, 27/08/2026)**: prima di questa
        # correzione `statistiche_orarie` REGISTRAVA `da_iso`/`a_iso` in
        # `statistiche_chieste` (sotto) ma li IGNORAVA nel calcolo della
        # risposta -- tornava sempre `self._statistiche`, qualunque fosse la
        # finestra chiesta. Mutazione ESEGUITA dal revisore: far leggere alla
        # riparazione le statistiche del PRIMO giorno per ENTRAMBI i giorni
        # -> archivio byte-identico a quello corretto, nessun test se ne
        # accorgeva. `statistiche_per_finestra` SELEZIONA DAVVERO per
        # finestra -- se non c'e' una voce per quella finestra ricade su
        # `self._statistiche` (il comportamento di sempre, per i test a cui
        # la finestra non interessa).
        #
        # **Chiave `(da_iso, a_iso)`, non piu' solo `da_iso`** (residuo
        # minore del mandato, punto 6, 27/08/2026): selezionare solo
        # sull'inizio lasciava una `a_iso` sbagliata passare inosservata --
        # stessa famiglia del difetto n.1 (una finta che accetta un
        # parametro e non lo verifica davvero), gravita' minima perche' nella
        # vita vera `day_boundaries` non produce mai lo stesso `da_iso` per
        # due giorni diversi. Chiuso perche' costava poco: una tupla al
        # posto di una stringa come chiave.
        self._statistiche_per_finestra = statistiche_per_finestra or {}
        self.chiesti = []
        self.direzioni_chieste = 0
        self.statistiche_chieste: list[tuple[list[str], str, str]] = []

    async def legami(self, tipo, identifier):
        self.chiesti.append((tipo, identifier))
        if tipo not in HAClient.RELATED_ITEM_TYPES:
            return {"errore": f"tipo non riconosciuto da Home Assistant: {tipo}"}
        return self._mappa.get(identifier, self._default)

    async def direzioni_energia(self):
        self.direzioni_chieste += 1
        if self._direzioni_errore is not None:
            return {"errore": self._direzioni_errore}
        return dict(self._direzioni)

    async def statistiche_orarie(self, identificatori, da_iso, a_iso):
        self.statistiche_chieste.append((list(identificatori), da_iso, a_iso))
        if self._statistiche_errore is not None:
            return {"errore": self._statistiche_errore}
        fonte = self._statistiche_per_finestra.get((da_iso, a_iso), self._statistiche)
        return {"serie": {k: v for k, v in fonte.items() if k in identificatori}}


@pytest.mark.asyncio
async def test_i_comprimari_arrivano_da_legami():
    ha = _ClienteLegami({"climate.camera_t": {
        "entity": ["sensor.camera_temperatura"], "area": ["camera_da_letto"]}})
    mappa, falliti = await costruisci_comprimari(ha, ["climate.camera_t"])
    assert mappa["climate.camera_t"] == ["sensor.camera_temperatura"]
    assert falliti == 0


@pytest.mark.asyncio
async def test_si_chiede_sempre_il_tipo_giusto_a_home_assistant():
    """Il Critical vero: `costruisci_comprimari` chiedeva `"entita"` (la
    chiave ITALIANA), che il client vero rifiuta prima di toccare la rete --
    `"entita" not in HAClient.RELATED_ITEM_TYPES`. Qui si legge cosa e' stato
    chiesto DAVVERO, non solo cosa e' tornato.

    Mutazione ESEGUITA: `tipo_ha = TIPO_LEGAME_HA["entita"]` sostituito con
    la stringa letterale `"entita"` in `costruisci_comprimari` -- arrossisce,
    perche' `ha.chiesti` torna `[("entita", "climate.camera_t")]` invece di
    `[("entity", "climate.camera_t")]`, e la `mappa` risultante e' vuota
    (il client finto rifiuta il tipo)."""
    ha = _ClienteLegami({"climate.camera_t": {"entity": ["sensor.camera_temperatura"]}})
    mappa, falliti = await costruisci_comprimari(ha, ["climate.camera_t"])
    assert ha.chiesti == [("entity", "climate.camera_t")]
    assert mappa["climate.camera_t"] == ["sensor.camera_temperatura"]
    assert falliti == 0


@pytest.mark.asyncio
async def test_aree_piani_e_dispositivi_NON_sono_comprimari():
    """Un'area non e' una cosa che fa qualcosa mentre il termostato scalda:
    e' dove sta. Metterla fra i comprimari riempirebbe ogni oggetto di
    identificatori che non misurano niente."""
    ha = _ClienteLegami({"climate.camera_t": {
        "area": ["camera"], "floor": ["terra"], "device": ["abc"],
        "integration": ["ave_domina"], "entity": ["sensor.t"]}})
    mappa, falliti = await costruisci_comprimari(ha, ["climate.camera_t"])
    assert mappa["climate.camera_t"] == ["sensor.t"]
    assert falliti == 0


@pytest.mark.asyncio
async def test_un_guasto_di_sistema_non_si_chiede_a_legami():
    """`problema:sonos.x` non e' un'entita' di Home Assistant: chiederlo
    produrrebbe una chiamata di rete per ogni guasto, tutte fallite."""
    ha = _ClienteLegami({})
    mappa, falliti = await costruisci_comprimari(ha, ["problema:sonos.x", "integrazione:abc"])
    assert mappa == {}
    assert falliti == 0
    assert ha.chiesti == []


@pytest.mark.asyncio
async def test_un_guasto_di_legami_non_ferma_l_aggregazione():
    """Se `legami` non risponde si perdono i comprimari, non la giornata: un
    oggetto senza contesto e' peggio di uno completo, ma infinitamente meglio
    di nessun oggetto. Qui la finta risponde gia' nella forma vera del
    client (`{"errore": ...}`): non serviva toccarla.

    Il conteggio dei falliti torna al chiamante ora (era il CRITICAL: moriva
    qui dentro): questa e' la prova diretta che `falliti` sale a 1 quando
    QUESTA funzione -- non un mandante che ha monkeypatchato -- incontra il
    guasto vero."""
    ha = _ClienteLegami(default={"errore": "Home Assistant non ha risposto"})
    mappa, falliti = await costruisci_comprimari(ha, ["climate.camera_t"])
    assert mappa == {"climate.camera_t": []}
    assert falliti == 1


@pytest.mark.asyncio
async def test_un_guasto_di_legami_logga_col_prefisso_cervello(caplog):
    """Punto C del Critical (review de «l'osservatore», 26/08/2026): un
    guasto di lettura non e' «non c'e' niente» -- deve lasciare traccia nel
    log, non finire nello stesso `[]` di un'entita' che davvero non ha
    comprimari, senza che nessuno se ne accorga.

    **Correzione del residuo 2 (grilletto-brief.md, appendice):** l'assert
    controllava solo `startswith("cervello:")`, lo stesso schema gia'
    corretto nel test gemello di `test_cervello_wiring.py` -- un messaggio
    DIVERSO col prefisso giusto sarebbe passato ugualmente. Qui si legge il
    messaggio preciso."""
    import logging

    ha = _ClienteLegami(default={"errore": "Home Assistant non ha risposto"})
    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        await costruisci_comprimari(ha, ["climate.camera_t"])

    assert any(
        r.getMessage() == "cervello: comprimari non letti per 1 soggetti su 1 "
                          "-- il contesto di questo giro e' parziale"
        for r in caplog.records)


@pytest.mark.asyncio
async def test_si_chiede_una_volta_sola_per_soggetto():
    """L'aggregazione chiama i comprimari dentro un ciclo: una chiamata di rete
    per ogni cambio farebbe migliaia di richieste per una giornata."""
    ha = _ClienteLegami({})
    await costruisci_comprimari(ha, ["climate.a", "climate.a", "climate.b"])
    assert len(ha.chiesti) == 2


@pytest.mark.asyncio
async def test_falliti_conta_solo_i_soggetti_rotti_non_tutti():
    """Un guasto PARZIALE (un soggetto su due) deve contare 1, non 2 e non 0
    -- e' esattamente il numero che `riaggrega_gli_ultimi_due_giorni` legge
    per decidere se fermarsi (CRITICAL, grilletto-brief.md): se questo
    numero fosse sbagliato in un senso o nell'altro, la riparazione
    scriverebbe quando non deve o si fermerebbe quando potrebbe procedere."""
    ha = _ClienteLegami({
        "climate.buono": {"entity": ["sensor.buono"]},
        "climate.rotto": {"errore": "Home Assistant non ha risposto"}})

    mappa, falliti = await costruisci_comprimari(
        ha, ["climate.buono", "climate.rotto"])
    assert mappa == {"climate.buono": ["sensor.buono"], "climate.rotto": []}
    assert falliti == 1
