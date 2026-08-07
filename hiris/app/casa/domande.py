"""Le due domande: cercare per nome, guardare il dettaglio.

Il nucleo (nucleo.py) dice DOVE sono le cose -- conta, non elenca. Le due
funzioni qui sotto danno il DETTAGLIO, quando il modello (o l'utente dalla
pagina) lo chiede esplicitamente:

- `cerca(indice, testo)` -- trovare qualcosa per nome o alias. E' un guscio
  sottile attorno a `Indice.trova()` (memoria/riconoscitore.py): il
  contratto -- `candidati` sempre una lista, `ambiguo` dichiarato -- e' gia'
  li', e riscriverlo qui vorrebbe dire poterlo rompere in due punti invece
  che in uno. Due voci che si normalizzano uguali (due «Bagno» su piani
  diversi, un alias che collide col nome vero di un'altra area) restano
  AMBIGUE: scegliere spetta al modello, che ha la casa in contesto, o
  all'utente, che corregge dalla pagina -- non a questo modulo.
- `guarda(casa, comportamento, ricordi, stato, tipo, riferimento)` -- il
  dettaglio di UNA cosa sola: un'area con le sue entita' e i loro stati,
  un'entita' col suo stato e la sua classe, un'automazione o uno script col
  loro corpo, un dispositivo con le sue entita', un ricordo con la sua
  interpretazione.

Due, non trentaquattro: la mappa del prodotto ha condannato un catalogo di
trentaquattro strumenti con tre copie divergenti (vedi
docs/design/2026-08-05-la-conoscenza-di-hiris.md). Un tipo nuovo di "cosa"
si aggiunge come un altro `if` dentro `guarda`, non come un tool in piu'.

Entrambe sono PURE: prendono dati gia' letti dal chiamante (l'indice, la
casa, il comportamento, i ricordi, lo stato vivo) e non aprono archivi ne'
chiamano la rete -- la stessa scelta che rende `componi()` del nucleo
verificabile senza finti elaborati (nucleo.py).

**Un silenzio non dichiarato e' indistinguibile da un'assenza di
problemi** (pagato sedici volte su questo ramo, sempre trovato da una
review, mai dalla suite). Per questo `guarda` restituisce SEMPRE la chiave
`esiste`, e quando e' `False` non inventa il resto: nessun `entita: []`,
nessun `corpo: None` che si potrebbe scambiare per un fatto sulla casa
invece che per "non trovato". E «non ho il corpo» (un limite di HIRIS --
`corpo: None` con un `origine` che lo dichiara) resta distinto da «il
corpo e' vuoto» (un fatto sulla casa: `corpo: {}` o simile).
"""
from __future__ import annotations

from .anagrafe import gerarchia

# I tipi di comportamento che `guarda` sa mostrare col loro corpo. Un
# "automazione" e uno "script" sono voci dello stesso elenco
# (comportamento.py), non due archivi diversi: la distinzione e' nel campo
# `tipo` della voce, non nella provenienza.
_TIPI_COMPORTAMENTO = {"automazione", "script"}


def cerca(indice, testo: str) -> list[dict]:
    """Trova `testo` per nome o alias, con l'ambiguita' dichiarata.

    E' `Indice.trova()` senza aggiunte: quel metodo GIA' restituisce, per
    ogni frammento riconosciuto, `candidati` (sempre una lista) e `ambiguo`
    (vero quando sono piu' di uno). Scegliere UN candidato qui -- il primo,
    il piu' probabile -- rifarebbe esattamente il difetto che e' gia'
    costato un fix: due «Bagno» su piani diversi, o un alias che collide
    col nome vero di un'altra area, che vincevano in silenzio in base
    all'ordine di raccolta. Chi chiama vede l'ambiguita' dichiarata e la
    passa al modello (che ha la casa in contesto) o all'utente (che
    corregge dalla pagina) -- questa funzione non sceglie per loro.
    """
    return indice.trova(testo)


def _ricordi_ancorati(ricordi: list[dict], tipo: str, riferimento) -> list[dict]:
    """I ricordi di `ricordi` che portano un'ancora (tipo, riferimento)
    uguale a quella cercata -- stessa chiave di `ArchivioMemoria.per_ancora`
    (memoria/archivio.py), ma su una lista gia' in memoria: `guarda` e'
    pura, non interroga l'archivio da sola.

    E' il senso delle ancore: «quali preferenze riguardano questa stanza».
    Un tipo come "automazione", "script" o "ricordo" -- fuori dal
    vocabolario delle ancore (memoria/interpretazione.py: area, entita,
    dispositivo) -- semplicemente non trova mai nulla qui: non e' un
    errore, e' un tipo di "cosa" per cui nessun ricordo si ancora.
    """
    trovati = []
    for r in ricordi:
        for ancora in r.get("ancore") or []:
            if ancora.get("tipo") == tipo and ancora.get("riferimento") == riferimento:
                trovati.append(r)
                break
    return trovati


def _trova_area(piani: list[dict], riferimento) -> dict | None:
    """L'area `riferimento` nell'albero gia' costruito da `gerarchia()`,
    con le entita' che le spettano (ereditarieta' dal dispositivo, esclusi
    i disabilitati) gia' risolte.

    Riusa l'albero invece di rifiltrare `casa["entita"]` a mano: una
    piccola reimplementazione delle stesse regole e' gia' costata un
    Critical al Task 1 -- qui non si ripete.
    """
    for piano in piani:
        for area in piano["aree"]:
            if area["id"] == riferimento:
                return area
    return None


def _guarda_area(casa: dict, ricordi: list[dict], stato: dict, riferimento,
                 non_disponibili: tuple[str, ...] = ()) -> dict:
    # `non_disponibili` va PROPAGATO, non solo ricevuto: senza, `gerarchia()`
    # crede che sia andato tutto bene e un'entita' che eredita l'area dal
    # proprio dispositivo -- col registro dispositivi caduto -- finisce in
    # "Senza area" invece che in "Dispositivi non letti". Risultato: una
    # cucina con cinque luci ne mostra quattro, con `esiste: True` e nessun
    # avviso: la stessa forma di una cucina davvero piu' piccola.
    piani = gerarchia(casa, tuple(non_disponibili))
    area = _trova_area(piani, riferimento)
    if area is None:
        return {"esiste": False, "tipo": "area", "riferimento": riferimento}
    entita = [
        {"id": e["id"], "nome": e.get("nome"), "classe": e.get("classe"),
         "stato": stato.get(e["id"])}
        for e in area["entita"]
    ]
    # L'elenco puo' essere incompleto senza che si veda: si dichiara.
    incompleto = sorted(set(non_disponibili) & {"aree", "dispositivi", "entita"})
    dettaglio = {
        "esiste": True, "tipo": "area", "id": area["id"], "nome": area["nome"],
        "entita": entita,
        "ricordi": _ricordi_ancorati(ricordi, "area", riferimento),
    }
    if incompleto:
        dettaglio["elenco_incompleto"] = incompleto
    return dettaglio


def _guarda_entita(casa: dict, ricordi: list[dict], stato: dict, riferimento) -> dict:
    entita = next((e for e in casa.get("entita") or [] if e.get("id") == riferimento), None)
    if entita is None:
        return {"esiste": False, "tipo": "entita", "riferimento": riferimento}
    return {
        "esiste": True, "tipo": "entita", "id": entita["id"], "nome": entita.get("nome"),
        "classe": entita.get("classe"), "unita": entita.get("unita"),
        # Un'entita' disabilitata resta in anagrafe (e' in Home Assistant e
        # non funziona) ma sparisce dall'albero di `gerarchia()` -- questo
        # campo dice perche' `guarda` la trova comunque, senza far credere
        # che sia una stanza arredata (stesso principio di anagrafe.py).
        "disabilitata": bool(entita.get("disabilitata")),
        "stato": stato.get(entita["id"]),
        "ricordi": _ricordi_ancorati(ricordi, "entita", riferimento),
    }


def _guarda_dispositivo(casa: dict, ricordi: list[dict], riferimento) -> dict:
    dispositivo = next(
        (d for d in casa.get("dispositivi") or [] if d.get("id") == riferimento), None)
    if dispositivo is None:
        return {"esiste": False, "tipo": "dispositivo", "riferimento": riferimento}
    # Stessa ragione per cui `_guarda_entita` porta `disabilitata`: qui si
    # legge `casa["entita"]` grezzo, fuori da `gerarchia()`, che le disabilitate
    # le esclude. Senza dirlo, un dispositivo spento e le sue entita' morte
    # avrebbero la stessa forma di uno che funziona.
    entita_del_dispositivo = [
        {"id": e["id"], "nome": e.get("nome"),
         "disabilitata": bool(e.get("disabilitata"))}
        for e in casa.get("entita") or [] if e.get("dispositivo_id") == riferimento
    ]
    return {
        "esiste": True, "tipo": "dispositivo", "id": dispositivo["id"],
        "nome": dispositivo.get("nome"),
        "disabilitato": bool(dispositivo.get("disabilitato")),
        "entita": entita_del_dispositivo,
        "ricordi": _ricordi_ancorati(ricordi, "dispositivo", riferimento),
    }


def _guarda_comportamento(comportamento: list[dict], ricordi: list[dict],
                           tipo: str, riferimento) -> dict:
    voce = next(
        (v for v in comportamento if v.get("id") == riferimento and v.get("tipo") == tipo), None)
    if voce is None:
        return {"esiste": False, "tipo": tipo, "riferimento": riferimento}
    return {
        "esiste": True, "tipo": tipo, "id": voce["id"], "nome": voce.get("nome"),
        # `corpo` passa cosi' com'e': `None` (HIRIS non l'ha, `origine` lo
        # dichiara) e un corpo vuoto ma presente sono due valori diversi, e
        # questa funzione non li confonde riscrivendoli.
        "corpo": voce.get("corpo"), "origine": voce.get("origine"),
        "ricordi": _ricordi_ancorati(ricordi, tipo, riferimento),
    }


def _guarda_ricordo(ricordi: list[dict], riferimento) -> dict:
    ricordo = next((r for r in ricordi if r.get("id") == riferimento), None)
    if ricordo is None:
        return {"esiste": False, "tipo": "ricordo", "riferimento": riferimento}
    return {
        "esiste": True, "tipo": "ricordo", "id": ricordo["id"], "testo": ricordo["testo"],
        "detto_da": ricordo.get("detto_da"),
        # Le quattro caselle dell'interpretazione (memoria/interpretazione.py),
        # tenute distinte dal testo -- che resta la verita', non riscritta.
        "interpretazione": {
            "forza": ricordo.get("forza"), "grandezza": ricordo.get("grandezza"),
            "minimo": ricordo.get("minimo"), "massimo": ricordo.get("massimo"),
            "unita": ricordo.get("unita"),
            "ancore": ricordo.get("ancore") or [],
            "condizioni": ricordo.get("condizioni") or [],
        },
    }


def guarda(casa: dict, comportamento: list[dict], ricordi: list[dict], stato: dict,
           tipo: str, riferimento,
           non_disponibili: tuple[str, ...] = ()) -> dict:
    """Il dettaglio di UNA cosa sola -- l'area con le sue entita' e i loro
    stati, l'entita' col suo stato e la sua classe, l'automazione o lo
    script col loro corpo, il dispositivo con le sue entita', il ricordo
    con la sua interpretazione.

    Restituisce SEMPRE la chiave `esiste`. Quando e' `False` il resto non
    si inventa: nessun `entita: []`, nessun `corpo: None` che si potrebbe
    scambiare per un fatto sulla casa invece che per "non trovato" -- un
    silenzio non dichiarato e' indistinguibile da un'assenza di problemi.

    Pura: legge `casa`/`comportamento`/`ricordi`/`stato` cosi' come arrivano
    dal chiamante (`ArchivioCasa`, `ArchivioMemoria`, lo stato vivo di Home
    Assistant), non apre archivi ne' chiama la rete.
    """
    if tipo == "area":
        return _guarda_area(casa, ricordi, stato, riferimento, non_disponibili)
    if tipo == "entita":
        return _guarda_entita(casa, ricordi, stato, riferimento)
    if tipo == "dispositivo":
        return _guarda_dispositivo(casa, ricordi, riferimento)
    if tipo in _TIPI_COMPORTAMENTO:
        return _guarda_comportamento(comportamento, ricordi, tipo, riferimento)
    if tipo == "ricordo":
        return _guarda_ricordo(ricordi, riferimento)
    # Un tipo che non conosciamo non e' un errore da sollevare: e' lo
    # stesso caso di "non l'ho trovato", solo con una causa diversa (il
    # modello ha nominato un tipo che non esiste, non un riferimento che
    # manca) -- e va dichiarato con la stessa onesta', non con un'eccezione
    # che gli spezza il turno.
    return {"esiste": False, "tipo": tipo, "riferimento": riferimento}
