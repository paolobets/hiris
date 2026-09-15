"""Le finte di `HAClient` condivise fra piu' prove.

**Una sola per contratto.** Prima ce n'erano quattro per `legami`, fra due
file, una delle quali definita due volte nello stesso: potevano divergere dal
contratto vero ciascuna per conto proprio, ed e' cosi' che una finta infedele
ha reso invisibile un difetto per settimane.

Questo file nasce il 15/09/2026, quando `test_mind_companions.py` e' uscito coi
comprimari (spec §13): le prove di `build_companions` sono morte con lui, ma la
finta serviva ancora a chi prova lo STRUMENTO `related` e i bilanci -- cose
vive, che con l'osservatore non c'entrano.
"""
from hiris.app.proxy.ha_client import HAClient


class _ClienteLegami:
    """L'UNICA finta di `HAClient` per `legami`, importata anche da
    `test_mind_wiring.py`.

    **Perche' una sola** (difesa-profondita-brief.md, punto 4). Prima ce
    n'erano quattro, indipendenti, fra questo file e quello -- una delle
    quali definita due volte nello stesso file -- e potevano divergere dal
    contratto vero ciascuna per conto proprio. E' esattamente cosi' che la
    finta infedele originale (quella che accettava `related("entita", ...)`,
    la chiave ITALIANA che il client vero rifiuta, e rispondeva gia' nella
    busta tradotta `{"legami": {...}}`) e' sopravvissuta abbastanza a lungo
    da rendere invisibile il Critical dei comprimari: nessuna delle quattro
    copie l'avrebbe presa da sola, ma nessuna era IL posto dove correggerla
    una volta per tutte.

    Valida `tipo` come fa il client vero (i valori INGLESI di
    `HAClient.RELATED_ITEM_TYPES`, importati -- non ricopiati) e risponde nella
    forma GREZZA del client: chiavi inglesi, nessuna busta `{"legami": ...}`.

    Costruita sui quattro esiti che `HAClient.related` produce davvero:

    - **risposta buona**: `mappa[identifier]` un dizionario grezzo
      (es. `{"entity": ["sensor.x"]}`);
    - **risposta vuota**: `identifier` assente da `mappa` (o mappato a
      `{}`) -- "nessun legame", non un guasto. E' anche il default quando
      non si passa `mappa`: un client che non fallisce mai e non ha niente
      da dire, per i test che vogliono la riparazione INCONDIZIONATA
      (nessun soggetto fallito). Deliberatamente non e' `ha_client=None`:
      con `None`, `build_companions` chiamerebbe `None.related(...)`,
      prenderebbe `AttributeError`, la CONTERREBBE e conterebbe ogni
      soggetto come fallito -- il contrario di "incondizionata";
    - **dizionario d'errore**: `mappa[identifier] = {"errore": ...}`, o
      `default={"errore": ...}` per farlo rispondere cosi' a QUALUNQUE
      identificatore senza doverli elencare tutti;
    - **risposta malformata**: `mappa[identifier]` un dizionario la cui
      traduzione (`home_space/queries.py::legami`, chiamata da
      `build_companions`) non e' contenuta -- es. `{"entity": 5}`, un
      intero al posto della lista che Home Assistant vero manda sempre. E'
      l'innesco del punto 1 (difesa-profondita-brief.md): fa uscire un
      `TypeError` vero dalla catena vera, senza monkeypatch.

    **Cresciuta il 27/08/2026 (mandato "le direzioni dell'energia") per
    fingere anche `energy_directions()`**, non una seconda finta a fianco:
    e' la stessa disciplina "una sola finta per `HAClient`" del paragrafo
    sopra, e i due lavori dell'aggregazione (`_aggrega_ieri`,
    `reaggregate_last_two_days`) chiamano ORA entrambi i metodi sullo
    STESSO client. `direzioni` e' la mappa che `energy_directions()` torna
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
        #: Le mappe con cui `energy_directions` e' stata chiamata, in ordine.
        self.direzioni_mappe: list[dict] = []
        self._default = {} if default is None else default
        self._direzioni = direzioni or {}
        self._direzioni_errore = direzioni_errore
        # `statistiche` -- **cresciuta il 27/08/2026 (mandato «il bilancio
        # dell'energia») per fingere anche `hourly_statistics()`**, stessa
        # disciplina "una sola finta" del paragrafo sopra: `{statistic_id:
        # [punto, ...]}` gia' nella forma TRADOTTA (chiavi italiane, come le
        # manda `HAClient._request_statistics` per davvero) -- fedele al
        # contratto vero: `build_balances` (server.py) legge SOLO il
        # ritorno di `hourly_statistics`, mai la richiesta grezza a HA.
        self._statistiche = statistiche or {}
        self._statistiche_errore = statistiche_errore
        # `statistiche_per_finestra` -- **la decima finta corretta per
        # mutazione (mandato, punto 4, 27/08/2026)**: prima di questa
        # correzione `hourly_statistics` REGISTRAVA `da_iso`/`a_iso` in
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

    # **Cresciuta il 10/09/2026** (fetta «il lettore»), stessa disciplina
    # "una sola finta per `HAClient`": da quando l'anagrafe si legge dal vivo,
    # la fetta d'avvio che i test eseguono per davvero passa da `rebuild()`, e
    # `rebuild` chiede questi tre. Una casa minima ma VERA nella forma:
    # `read_registries` torna `(registri, non_disponibili)` e le righe delle
    # entita' NON portano `device_class` -- il registro non lo manda.
    async def read_registries(self):
        return ({"piani": [], "aree": [], "dispositivi": [],
                 "entita": [], "etichette": [], "categorie": [],
                 "integrazioni": []}, [])

    async def get_config(self):
        return {"time_zone": "Europe/Rome"}

    def add_topology_listener(self, callback):
        self.ascoltatori_topologia = getattr(self, "ascoltatori_topologia", [])
        self.ascoltatori_topologia.append(callback)

    async def related(self, item_type, identifier):
        self.chiesti.append((item_type, identifier))
        if item_type not in HAClient.RELATED_ITEM_TYPES:
            return {"errore": f"tipo non riconosciuto da Home Assistant: {item_type}"}
        return self._mappa.get(identifier, self._default)

    async def energy_directions(self, *, direction_by_translation_key):
        # Il parametro e' OBBLIGATORIO anche nella finta, e la finta se lo
        # ANNOTA: dal 12/09/2026 la mappa `translation_key -> direzione` non
        # vive piu' dentro `HAClient`, arriva dal sapere -- e una finta che
        # accettasse la chiamata senza il parametro lascerebbe passare un
        # chiamante che ha smesso di leggerlo (memoria
        # `hiris_runner_signature_contract`: un kwarg nuovo lo accettano
        # TUTTI i finti di quella firma, o la prova difende un contratto che
        # in produzione non esiste piu').
        self.direzioni_mappe.append(dict(direction_by_translation_key or {}))
        self.direzioni_chieste += 1
        if self._direzioni_errore is not None:
            return {"errore": self._direzioni_errore}
        return dict(self._direzioni)

    async def hourly_statistics(self, identifiers, from_iso, to_iso):
        self.statistiche_chieste.append((list(identifiers), from_iso, to_iso))
        if self._statistiche_errore is not None:
            return {"errore": self._statistiche_errore}
        fonte = self._statistiche_per_finestra.get((from_iso, to_iso), self._statistiche)
        return {"serie": {k: v for k, v in fonte.items() if k in identifiers}}
