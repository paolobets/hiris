"""Le finte di `HAClient` condivise fra piu' prove.

**Una sola per contratto.** Prima ce n'erano quattro per `legami`, fra due
file, una delle quali definita due volte nello stesso: potevano divergere dal
contratto vero ciascuna per conto proprio, ed e' cosi' che una finta infedele
ha reso invisibile un difetto per settimane.

Questo file nasce il 15/09/2026, quando `test_mind_companions.py` e' uscito coi
comprimari (spec §13): le prove di `build_companions` sono morte con lui, ma la
finta serviva ancora a chi prova lo STRUMENTO `related` e i bilanci. **I
bilanci sono usciti il 01/10/2026** (`server.build_balances`, con
`tests/test_server_balances.py`): con loro e' uscita la meta' della finta che
fingeva `hourly_statistics` e la lettura dei registri, che nessun'altra prova
chiedeva. Resta lo strumento `related`.
"""
from hiris.app.proxy.ha_client import HAClient


class _ClienteLegami:
    """L'UNICA finta di `HAClient` per `legami`, importata da
    `test_related_tools.py`.

    **Perche' una sola** (difesa-profondita-brief.md, punto 4). Prima ce
    n'erano quattro, indipendenti, fra due file -- una delle quali definita
    due volte nello stesso file -- e potevano divergere dal contratto vero
    ciascuna per conto proprio. E' esattamente cosi' che la finta infedele
    originale (quella che accettava `related("entita", ...)`, la chiave
    ITALIANA che il client vero rifiuta, e rispondeva gia' nella busta
    tradotta `{"legami": {...}}`) e' sopravvissuta abbastanza a lungo da
    rendere invisibile il Critical dei comprimari: nessuna delle quattro
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
      non si passa `mappa`;
    - **dizionario d'errore**: `mappa[identifier] = {"errore": ...}`, o
      `default={"errore": ...}` per farlo rispondere cosi' a QUALUNQUE
      identificatore senza doverli elencare tutti;
    - **risposta malformata**: `mappa[identifier]` un dizionario la cui
      traduzione non e' contenuta -- es. `{"entity": 5}`, un intero al posto
      della lista che Home Assistant vero manda sempre.

    La finta di `energy_directions()` e' uscita il 30/09/2026 col metodo
    vero, che non aveva piu' chiamanti (revisione finale della storia)."""

    def __init__(self, mappa: dict[str, dict] | None = None, *, default=None):
        self._mappa = mappa or {}
        self._default = {} if default is None else default
        self.chiesti = []

    async def related(self, item_type, identifier):
        self.chiesti.append((item_type, identifier))
        if item_type not in HAClient.RELATED_ITEM_TYPES:
            return {"errore": f"tipo non riconosciuto da Home Assistant: {item_type}"}
        return self._mappa.get(identifier, self._default)
