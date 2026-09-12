"""L'aggregazione: dai cambi grezzi agli oggetti.

**Un oggetto e' una cosa compiuta della casa**: qualcosa che e' cominciato, e'
durato, e' finito -- con dentro chi lo ha fatto e cosa c'era attorno mentre
durava.

    Riscaldamento camera: acceso 15:30 -> 17:05. Temperatura da 18,2 a 21,0.

**E' l'unico posto di questa fetta dove si giudica**, ed e' voluto: un giudizio
qui si rifa' finche' il grezzo esiste (22 giorni: 21 di promessa, uno di
guardia -- vedi `archivio.READING_RETENTION_S`), uno preso in scrittura non
si corregge piu'.

**L'obiettivo sceglie QUALI entita', la natura decide CHE TIPO di oggetto ne
esce.** La prima non e' una lista scritta a mano: lo scope (`mind/watcher.py`, `store.is_watched`
gamba`) deriva QUALI entita' da cio' che Home Assistant dichiara gia' --
dominio, `device_class`, `source_type` (**non `state_class`**: correzione
di parole della review, mandato «il bilancio dell'energia», punto 7,
27/08/2026 -- dopo la correzione del 27/08, `type_vocabulary.aspect_of` non lo legge
piu' per decidere nessuna gamba, vedi il suo docstring). **La seconda, invece,
e' un giudizio nostro**: quali tipi «si accendono e si spengono», e quali loro
stati valgono «a riposo», nessuna API di Home Assistant lo dice.

**Dal 07/09/2026 quel giudizio non vive piu' qui.** `_OPERABLE`, `_RESTING` e
`_UNKNOWN` erano tre elenchi scritti a mano in questo modulo; sono diventati
righe del **vocabolario dei tipi** (`home_space/type_vocabulary.py`), interrogate
con la metrica «accendibile + riposi». Questo modulo resta il LETTORE:
`genre_for` chiede se un tipo e' accendibile, `_is_on` chiede se uno stato e'
un riposo, e il salto in cima ad `aggregate_day` chiede quali stati sono
«non lo so». La regola che questo file portava in un commento -- «un tipo
entra fra gli accendibili INSIEME al suo riposo, nella stessa modifica» -- e'
diventata una condizione di costruzione del vocabolario: chi la viola non fa
passare nemmeno un `import`. Spec:
`docs/design/2026-09-07-l-anagrafe-dei-tipi.md`.

**Una frase che questo docstring ha portato fino a oggi era falsa**, e vale la
pena lasciarne traccia: diceva che Home Assistant «non dichiara da nessuna
parte quale dominio funziona come un interruttore». Lo dichiara -- il registro
dei servizi isola i domini con `turn_on` **e** `turn_off`, o `toggle` (spec
§4, misurato sulla casa vera il 07/09/2026: 16 domini). La derivazione non
coincide con il giudizio nostro e sbaglia in entrambi i versi, quindi non lo
sostituisce: lo **sorveglia**, ed e' lavoro delle fette 3 e 4.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..home_space.historian import home_space_zone
from ..home_space.type_vocabulary import (
    aspect_of,
    is_operable,
    resting_states,
    unknown_states,
)
from .operations import REGISTRY, UNKNOWN_UNIT

# `aggregate_day` e' SINCRONA: non fa nessuna lettura di rete. I comprimari
# arrivano gia' risolti dal chiamante (vedi il Task 6), proprio perche' una
# chiamata a `legami` dentro il ciclo farebbe migliaia di richieste per una
# giornata. Renderla `async` "per il futuro" sarebbe generalita' speculativa.
# **Vale identico per `balances`** (mandato «il bilancio dell'energia»,
# 27/08/2026): arriva gia' costruito dal chiamante (`server.py::
# costruisci_bilanci`), che ha gia' letto `HAClient.statistiche_orarie()` --
# una lettura di rete per giro, non per giorno ne' per dispositivo.

GENRES = ("funzionamento", "presenza", "energia", "guasto", "sicurezza", "bilancio")

# Le SETTE dimensioni che il bilancio riporta. **Il consumo e' la settima**
# (correzione ALTO della review, mandato «il bilancio dell'energia», punto
# 1, 27/08/2026): prima di questa correzione erano sei, e "consumo" era
# dichiaratamente escluso come "RIDONDANTE con autoconsumo+prelievo" -- una
# frase che era un'ASSUNZIONE, non un fatto misurato, e su questa casa e'
# FALSA. `_balance_moments` sotto usava quell'identita' per calcolare
# `self_sufficiency_share` come `autoconsumo/(autoconsumo+prelievo)`: su
# questa integrazione «autoconsumata» ESCLUDE la batteria (verificato:
# e' esattamente prodotta-esportata-carica), quindi la somma mancava la
# scarica -- oltre meta' del consumo vero della casa. Misurato il
# 26/08/2026: consumata 14,72 kWh contro autoconsumata+prelievo 6,21 (la
# differenza, 8,51, e' esattamente la scarica della batteria quel giorno).
# Il bilancio avrebbe scritto ogni notte un numero FALSO sull'autosufficienza
# (0,964 invece di 0,985 -- e con piu' ciclo di batteria la forbice esplode:
# 0,167 invece di 0,41).
#
# **La correzione non aggiusta la formula aggiungendo la scarica**: sarebbe
# di nuovo DEDURRE, e la relazione fra autoconsumo e batteria e' semantica
# di QUESTA integrazione -- un altro inverter potrebbe includere la batteria
# gia' dentro "autoconsumata". Il consumo e' un dato MISURATO che gia'
# avevamo (`energia_consumata_oggi`, la direzione "consumo" nella mappa
# delle direzioni) e lo si buttava via in nome di una derivazione sbagliata:
# ora si SMETTE di derivarlo, si legge, e le quote si calcolano su quello
# (vedi `_balance_moments`). Dove il sensore del consumo non esiste, la
# quota non si scrive -- campo assente, mai un numero inventato.
BALANCE_DIRECTIONS = ("produzione", "autoconsumo", "immissione",
                      "prelievo", "carica", "scarica", "consumo")

#: I quattro prefissi con cui un `protagonista` NON e' un'entita' di Home
#: Assistant, ma una condizione di sistema: una voce del registro di errori
#: (`problema:`, `integrazione:`, `log:` -- Task 2 «le tracce e il log») o
#: un'esecuzione di automazione in errore (`automazione:`, Task 4 dello
#: stesso verticale). Scritto UNA volta perche' e' la stessa domanda posta da
#: tre lettori diversi -- `genre_for` (qui sotto, decide il genere),
#: `_reading_aspect` (qui sotto, decide la gamba) e
#: `api/handlers_mind.py::_with_rendered_states` (decide se cercare una
#: traduzione di stato) -- e fino al 09/09/2026 (audit delle fondamenta) la
#: stessa tupla era scritta a mano in tutti e tre i posti: un quarto prefisso
#: aggiunto a due su tre sarebbe stato invisibile a qualunque prova che non
#: confrontasse i tre elenchi lettera per lettera.
NOT_ENTITY_PREFIXES = ("problema:", "integrazione:", "log:", "automazione:")

# Le tre liste che vivevano qui -- `_OPERABLE` (i domini che «funzionano»),
# `_RESTING` (gli stati che valgono «a riposo») e `_UNKNOWN` (gli stati «non lo
# so») -- sono righe del vocabolario dei tipi dal 07/09/2026. Le tre funzioni che
# le leggevano restano, con la stessa firma e lo stesso risultato: cambia da
# dove viene la risposta, non quale sia.
#
# **Perche' l'unione e non il riposo del singolo tipo.** `_is_on` non sa a
# quale dominio appartenga il valore che riceve -- lo riceve nudo -- e
# `type_vocabulary.resting_states()` restituisce esattamente l'unione che
# `_RESTING` era: un solo insieme, non due che si sovrappongono. Ogni valore
# ha lo stesso significato («questo episodio e' finito») in qualunque tipo
# compaia; cio' che il vocabolario aggiunge e' che ogni valore ha ora un tipo che
# lo rivendica, invece di stare in un elenco piatto di cui nessuno sa piu' chi
# vi abbia aggiunto cosa. Passare al riposo per-tipo sarebbe un cambio di
# comportamento, non una rifattorizzazione, e questa fetta non ne fa nessuno.


def genre_for(subject: str, aspect_: str | None) -> str | None:
    """Che tipo di oggetto puo' nascere da questo soggetto, o `None` se non ne
    nasce nessuno.

    **I sensori da soli non generano oggetti**: «la temperatura e' salita» non
    e' una cosa compiuta, e' il CONTESTO di qualcosa che e' successo. Se ne
    generassero, una giornata ne produrrebbe migliaia e nessuno sarebbe
    leggibile.

    **La sesta gamba (sicurezza) ha un genere proprio, non un buco.**
    Serrature, pannello dell'allarme, sirene, e i sensori di fumo/gas/
    monossido/allagamento/manomissione/guasto/calore/gelo sono una minaccia,
    non un funzionamento normale: hanno la stessa FORMA di una condizione di
    sistema -- nascono, durano, finiscono o restano aperti -- ma non sono la
    STESSA cosa. Una porta aperta con la chiave e un'integrazione Sonos rotta
    non sono lo stesso genere di fatto, e l'analista le trattera' in modo
    diverso: `"guasto"` resta per le condizioni di sistema (`problema:`,
    `integrazione:`, `log:` -- una voce del registro di errori, Task 2 «le
    tracce e il log» -- e `automazione:`, un'esecuzione in errore, Task 4
    dello stesso verticale -- un confine netto e facile da spiegare), `"sicurezza"` per
    tutta la gamba omonima. Qui il criterio e' `aspect_ == "sicurezza"`,
    qualunque sia il dominio, cosi' non serve ripetere l'elenco dei domini/
    classi che il pavimento gia' tiene.

    **Eccezione dichiarata (correzione del giro di review, punto 7): un
    `sensor` numerico della gamba sicurezza NON genera un oggetto.** Oggi
    l'unico caso raggiungibile e' il monossido misurato in concentrazione
    (`carbon_monoxide` su `sensor`, non su `binary_sensor`): una lettura come
    "0.4" non e' mai fra gli stati di riposo, quindi userebbe `_is_on` per
    aprire un oggetto che non chiuderebbe mai -- un guasto perennemente
    aperto al giorno, per ogni sensore CO numerico della casa. Un sensore che
    MISURA non e' un sensore che SCATTA: servirebbe una soglia per decidere
    quando la concentrazione diventa una minaccia, e non ne abbiamo una
    onesta.
    **Restare fuori e' la decisione**, non una dimenticanza: il
    `binary_sensor` di monossido -- che scatta davvero, con uno stato on/off
    -- resta dentro senza bisogno di nessuna soglia.
    """
    if subject.startswith(NOT_ENTITY_PREFIXES):
        return "guasto"
    domain = subject.split(".")[0]
    # **La gamba «sicurezza» viene PRIMA di «accendibile», e l'ordine e' il
    # giudizio.** Fino all'08/09/2026 nessun tipo era insieme accendibile e di
    # sicurezza, quindi l'ordine non si vedeva; quel giorno il proprietario ha
    # dichiarato `siren` accendibile (nona domanda del censore) e una sirena che
    # suona sarebbe diventata un oggetto di «funzionamento» -- cioe' l'evento
    # piu' importante che questa casa possa produrre declassato a «una cosa si
    # e' accesa», in silenzio, come effetto collaterale di una decisione che
    # parlava d'altro. Il docstring qui sopra lo diceva gia' -- «`sicurezza` per
    # tutta la gamba omonima, QUALUNQUE sia il dominio» -- e il codice lo
    # smentiva.
    if aspect_ == "sicurezza":
        if domain == "sensor":
            return None
        return "sicurezza"
    if is_operable(domain):
        return "funzionamento"
    if domain in ("person", "device_tracker"):
        return "presenza"
    if domain == "sensor" and aspect_ == "energia":
        return "energia"
    return None


def _reading_aspect(subject: str, row: dict) -> str | None:
    """La gamba del soggetto, ricostruita dal grezzo.

    Il grezzo non porta il CONTESTO attorno (§3 della spec: temperatura,
    presenza, tutto cio' che cambierebbe il giudizio) ma porta, da questa
    correzione, le tre classi che Home Assistant dichiara sull'entita' --
    `device_class`, `state_class`, `source_type` -- perche' sono grezzo per
    definizione, non un giudizio nostro. **`type_vocabulary.aspect_of()` legge solo
    `device_class` e `source_type`** per decidere la gamba di `sensor` e
    `binary_sensor` (correzione di parole della review, mandato «il
    bilancio dell'energia», punto 7, 27/08/2026: prima di questa
    correzione questo docstring diceva che le leggeva tutte e tre --
    `state_class` NON e' fra i criteri, dalla correzione del 27/08 sul
    traffico di rete, vedi il docstring di `gamba`). Resta comunque nel
    grezzo, non e' tolta dallo schema: e' `type_vocabulary.aspect_of()` che non la
    legge, non `store.py` che smette di conservarla -- i 22 giorni di
    grezzo permettono di rifare il giudizio anche se un domani tornasse a
    servire.

    **Non si salva la gamba gia' calcolata.** Sarebbe piu' comodo, ed e' la
    scelta sbagliata: la gamba e' un giudizio, e il giudizio sta tutto qui,
    nell'aggregazione, precisamente perche' i 22 giorni di grezzo permettano
    di rifarlo. Congelarlo in scrittura toglierebbe quella possibilita' il
    giorno in cui il pavimento cambiasse.

    **`log:` e `automazione:` sono un terzo e un quarto prefisso senza
    gamba, non due volte lo stesso controllo.** Una voce del registro di
    errori (Task 2) o un'esecuzione di automazione in errore (Task 4) non
    sono un'entita': cercarne la gamba con `type_vocabulary.aspect_of()` andrebbe a
    leggere `subject` come se fosse un `entity_id` (`sensor.qualcosa`) che
    non e' -- per `automazione:automation.x` in particolare, spaccarlo su
    `"."` darebbe il dominio `"automazione:automation"`, che non e' un
    `entity_id` valido di nessuna casa -- per un soggetto che ha gia' preso
    la sua strada in `genre_for` un rigo sopra nel file -- lo stesso
    confine, in DUE funzioni diverse: qui decide la gamba (nessuna), la'
    decide il genere (`"guasto"`).
    """
    if subject.startswith(NOT_ENTITY_PREFIXES):
        return None
    return aspect_of(subject, {
        "device_class": row.get("device_class"),
        "state_class": row.get("state_class"),
        "source_type": row.get("source_type"),
    })


def day_boundaries(day: str, timezone: str | None) -> tuple[float, float]:
    """L'inizio e la fine di un giorno **nel fuso della casa**.

    Le 23:30 di Roma sono le 21:30 UTC: un giorno calcolato in UTC spezzerebbe
    ogni serata in due, e la fetta dello schedulatore ha gia' pagato un difetto
    di orologi diversi.

    **La finestra di `archivio.cambi` e' semi-aperta (`[from_ts, to_ts)`)**, e
    questi confini ci contano sopra cosi' come sono: un `-1` o un `-0.001` "per
    stare sicuri" riaprirebbe un buco di un secondo a ogni mezzanotte, e con
    due confini inclusivi un cambio esattamente a mezzanotte finirebbe contato
    in due giorni.

    **Pubblica (correzione del giro di review, punto 4).** Prima era `_confini`
    e importava `_zona`, un'altra privata, da `home_space/historian.py`: due nomi con
    underscore attraversati da fuori dal solo import. Il calcolo e' uno solo
    (nessun doppione nel prodotto); tenerlo privato avrebbe solo obbligato chi
    ne ha bisogno a importare comunque il nome privato, o a riscrivere il
    calcolo -- che e' esattamente come nascono i doppioni.
    """
    zone = home_space_zone(timezone)
    start = datetime.fromisoformat(day).replace(tzinfo=zone)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def _is_on(value) -> bool:
    """Se questo stato NON e' un riposo -- cioe' se l'episodio e' ancora in
    corso. L'insieme dei riposi e' l'unione che il vocabolario dei tipi tiene:
    `_RESTING` era esattamente quella, elencata a mano."""
    return str(value or "").strip().lower() not in resting_states()


def _as_number(value) -> float | None:
    """Una lettura del grezzo -> un numero, o `None` se non lo e'.

    **E' il confine, non un calcolo**: un contatore scrive stringhe
    (`"1234.5"`), e il registro delle operazioni parla numeri. La traduzione
    fra i due mondi vive dove i due si toccano, cioe' qui.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _kwh(value) -> float | None:
    """Un numero della gamba energia -> kWh arrotondati a 2 decimali.

    2 decimali (0,01 kWh = 10 Wh, mandato punto 6): i contatori di questa
    casa non scrivono mai piu' di due cifre dopo la virgola (misurato:
    `0.27`, `3.11`, `23.8`...) -- un terzo decimale sarebbe precisione che
    lo strumento non ha, e il difetto misurato in pagina (`+0.
    010000000000000009`) e' rumore di virgola mobile ben sotto quella
    soglia. `None` -- non zero -- quando il valore manca o non e' un
    numero: e' la stessa distinzione che `primo_ultimo_differenza` fa nel
    registro delle operazioni (`mind/operations.py`).
    """
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _percent(value) -> float | None:
    """Una percentuale di batteria -> arrotondata a 1 decimale.

    1 decimale (56,6%): lo stato istantaneo della batteria e' un intero
    (misurato: `"12"`, `"96"`...), ma la MEDIA oraria che il bilancio legge
    (`media`, statistiche di tipo `measurement`) e' un numero continuo -- un
    decimale distingue due ore vicine senza inventare una precisione che lo
    strumento non ha.
    """
    if value is None:
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _dimension_points(series: dict[str, list[dict]], subject: str | None) -> list[dict]:
    """I punti orari di un'entita', ridotti a `{"inizio","fine","valore"}` --
    `valore` e' il `cambio` di quell'ora (il delta GIA' calcolato da HA,
    corretto per gli azzeramenti: vedi `HAClient._request_statistics`),
    arrotondato in kWh. Un'ora senza `cambio` (dato mancante per QUELL'ora,
    non per l'intero `statistic_id`) resta `valore: None` -- mai uno zero
    inventato -- ma non toglie le altre ore dalla lista.
    """
    if subject is None:
        return []
    points = series.get(subject) or []
    return [{"inizio": p.get("inizio"), "fine": p.get("fine"),
             "valore": _kwh(p.get("cambio")) if isinstance(p, dict) else None}
            for p in points if isinstance(p, dict)]


def _balance_moments(points_per_dimension: dict[str, list[dict]],
                      measures: dict[str, object]) -> dict:
    """I momenti derivati dalla forma e dalle misure -- vedi
    `build_balance_body` per il contratto completo. Separata per
    restare leggibile: ogni momento e' un piccolo giudizio a se'.

    **Prende le MISURE del registro, non i numeri gia' spogliati** (correzione
    della revisione indipendente, 12/09/2026): le quote si calcolano
    componendo operazioni -- `quota(differenza_fra(consumo, prelievo),
    consumo)`, che e' letteralmente la ricetta della spec §7 -- e cosi' la
    copertura dei totali arriva fino alla quota invece di perdersi. Prima di
    questa correzione una quota calcolata su un totale coperto all'80%
    usciva dichiarando copertura piena.
    """
    moments: dict = {}

    active_produzione = [p for p in points_per_dimension.get("produzione", [])
                         if (p["valore"] or 0) > 0]
    if active_produzione:
        moments["prima_ora_produzione"] = active_produzione[0]["inizio"]
        moments["ultima_ora_produzione"] = active_produzione[-1]["inizio"]
        peak = max(active_produzione, key=lambda p: p["valore"])
        moments["picco_produzione"] = {"valore": peak["valore"], "ora": peak["inizio"]}

    active_scarica = [p for p in points_per_dimension.get("scarica", [])
                      if (p["valore"] or 0) > 0]
    if active_scarica:
        moments["fine_scarica_batteria"] = active_scarica[-1]["fine"]

    autoconsumo = measures.get("autoconsumo")
    produzione = measures.get("produzione")
    if autoconsumo is not None and produzione is not None:
        autoconsumo_share = REGISTRY["quota"].run(autoconsumo, produzione)
        if autoconsumo_share.computable:
            moments["quota_autoconsumo"] = autoconsumo_share.value

    # **Correzione ALTO della review (mandato «il bilancio dell'energia»,
    # punto 1, 27/08/2026): NON PIU' `autoconsumo/(autoconsumo+prelievo)`.**
    # Quella formula ASSUMEVA che il consumo della casa fosse la somma di
    # autoconsumo e prelievo -- un'identita' falsa su questa integrazione
    # (vedi il commento sopra `BALANCE_DIRECTIONS`: «autoconsumata» esclude
    # la batteria, quindi la somma perde la scarica, oltre meta' del
    # consumo vero). La correzione non aggiunge la scarica alla somma --
    # sarebbe di nuovo DEDURRE un'identita' specifica di questa
    # integrazione. Si legge il consumo MISURATO (il settimo totale, vedi
    # sopra) e si calcola quanta parte NON viene dalla rete:
    # `(consumo - prelievo) / consumo`. Misurato il 26/08/2026: consumo
    # 14,72, prelievo 0,22 -> 0,985 (il numero vero; la vecchia formula
    # diceva 0,964). Senza il consumo misurato, niente quota: mai un
    # numero dedotto al posto di uno letto.
    consumo = measures.get("consumo")
    prelievo = measures.get("prelievo")
    if consumo is not None and prelievo is not None:
        self_produced = REGISTRY["differenza_fra"].run(consumo, prelievo)
        self_sufficiency_share = REGISTRY["quota"].run(self_produced, consumo)
        if self_sufficiency_share.computable:
            moments["quota_autosufficienza"] = self_sufficiency_share.value

    return moments


def build_balance_body(*, series: dict[str, list[dict]],
                              entity_per_dimension: dict[str, str],
                              provenance_per_dimension: dict[str, str],
                              battery_entity: str | None = None,
                              expected_hours: int | None = None) -> dict:
    """Il corpo di un bilancio, dalle statistiche orarie GIA' lette e tradotte.

    **Pura**: nessuna lettura di rete. `serie` arriva gia' risolta dal
    chiamante (`HAClient.hourly_statistics()`, chiavi italiane) -- stessa
    disciplina di `companions`/`directions` in `aggregate_day`.

    `entity_per_dimension`: `{"produzione": "sensor.x", ...}`, quale
    entita' del dispositivo rappresenta quale delle `BALANCE_DIRECTIONS`
    -- scelta dal chiamante (`server.py::build_balances`) fra le entita'
    del dispositivo che hanno quella direzione **e** la classe energia
    dichiarata (non potenza: il bilancio riporta kWh del giorno, non W
    istantanei). Una dimensione assente da questo dizionario significa
    «nessuna entita' di questo dispositivo ha quella direzione» -- il
    totale, la forma e i momenti che ne dipendono non compaiono: **mai uno
    zero al posto di "non lo so"** (mandato, «cosa NON si salva»).

    Il totale di una dimensione e' la somma delle ore CONOSCIUTE (quelle con
    `cambio` non nullo): un'ora mancante non azzera il totale, ma zero ore
    conosciute tolgono la dimensione per intero. **Dal 12/09/2026 la regola
    non vive piu' qui**: il totale passa da `somma_periodo` del registro
    (`mind/operations.py`), che rifiuta sotto la copertura minima invece di
    sommare le poche ore note con la faccia di un totale completo.

    Ritorna `{"totali": {dimensione: {"valore","provenienza"}}, "forma":
    {dimensione: [{"ora","valore"}, ...]}, "momenti": {...},
    ["batteria_percentuale_oraria": [{"ora","valore"}, ...]]}` -- ogni
    chiave presente solo se c'e' almeno un fatto da dirla (dizionario vuoto
    altrimenti, mai una chiave con un valore fittizio).

    **`forma[dimensione]` porta l'ORA di ogni punto, non solo il valore**
    (correzione MEDIA della review, mandato «il bilancio dell'energia»,
    punto 2, 27/08/2026): prima di questa correzione era una lista NUDA di
    valori (`[1.0, 2.0, ...]`), e Home Assistant OMETTE le ore senza dati --
    quindi l'indice non era l'ora, e una giornata che comincia alle 7 aveva
    il primo valore in posizione zero. L'oggetto salvato, da solo, non
    sapeva piu' dire «alle 13», che e' l'unica ragione per cui la forma
    esiste (spec §1, §3). **La chiave nuova e' `ora`** (lo stesso nome gia'
    usato da `picco_produzione` in `_balance_moments` -- fondamenta 3,
    consistenza), un ISO-8601 con fuso preso da `inizio` dello stesso punto
    -- l'istante GIA' letto e tradotto da `HAClient.hourly_statistics()`,
    non ricalcolato. Non porta anche `fine`: la grana e' fissa a un'ora
    (`period="hour"`, l'unico chiamante), la durata e' sempre la stessa, e
    raddoppiare il payload per dirla a ogni punto non permetterebbe nessuna
    frase in piu' (spec §1, «se un dato non serve a nessuna frase in piu',
    non va salvato»).

    **`batteria_percentuale_oraria` ha la STESSA forma di `forma[dimensione]`,
    per la STESSA ragione** (correzione MEDIA della review, mandato «il
    bilancio dell'energia», punto 2, 27/08/2026 -- «cerca i fratelli»: la
    correzione precedente aveva sistemato solo `forma`, e questo campo
    accanto e' rimasto una lista NUDA con lo stesso difetto). Con un buco
    del recorder gli indici non sono le ore, e la curva della batteria si
    disallineava in silenzio mentre quella dell'energia, accanto, era gia'
    giusta. Il docstring di questo campo prometteva anche «24 valori»: su
    una giornata bucata la lista non ne ha 24 -- frase falsa, tolta.
    """
    totals: dict[str, dict] = {}
    form: dict[str, list] = {}
    points_per_dimension: dict[str, list[dict]] = {}
    # Le misure intere, non solo il loro numero: servono ai momenti, che
    # compongono operazioni fra loro e hanno bisogno della copertura.
    measures: dict[str, object] = {}

    # **Il totale e la forma passano dal REGISTRO** (fetta «le operazioni»,
    # 12/09/2026): erano un `sum()` e una lista costruiti qui, e adesso sono
    # `somma_periodo` e `per_ora` -- gli stessi conti, in un posto solo, e la
    # copertura, che prima non si calcolava affatto, adesso esce nel corpo.
    #
    # **Cambia un comportamento, e va dichiarato**: una dimensione con pochi
    # punti conosciuti veniva sommata lo stesso e il totale aveva la faccia di
    # uno completo. Adesso, sotto la copertura minima, `somma_periodo` rifiuta
    # e la dimensione non compare -- che e' la stessa regola gia' applicata
    # qui a «zero ore conosciute», estesa a «troppo poche».
    #
    # **`expected_hours` e' il denominatore della copertura, e senza di lui
    # quel numero mentirebbe**: Home Assistant OMETTE le ore senza dati dalle
    # statistiche (fatto gia' scritto piu' sopra, correzione del 27/08/2026),
    # quindi contare i punti ricevuti darebbe copertura 100% a un giorno che
    # ne ha consegnate tre. Chi chiama lo sa davvero -- `server.py` lo ricava
    # da `day_boundaries`, che porta anche le giornate da 23 e 25 ore del
    # cambio d'ora. Quando non arriva, la copertura parla del campione e il
    # registro lo dichiara nel suo docstring.
    for dimension in BALANCE_DIRECTIONS:
        points = _dimension_points(series, entity_per_dimension.get(dimension))
        total = REGISTRY["somma_periodo"].run(
            points, unit="kWh", expected_parts=expected_hours)
        if not total.computable:
            continue
        profile = REGISTRY["per_ora"].run(
            points, unit="kWh", expected_parts=expected_hours)
        points_per_dimension[dimension] = points
        measures[dimension] = total
        form[dimension] = profile.value
        # **`copertura` viaggia col totale** (correzione della revisione
        # indipendente, 12/09/2026): prima il registro la calcolava e
        # `build_balance_body` la buttava, quindi «con la copertura che prima
        # non usciva» era una frase falsa scritta accanto al codice. La spec
        # (§9) vuole che ogni misura del resoconto porti anche la sua
        # copertura; la pagina non la mostra ancora -- quello e' lavoro della
        # fetta del resoconto -- ma il dato c'e' e si puo' chiedere, che e'
        # cio' che la quarta fondamenta richiede.
        totals[dimension] = {"valore": total.value,
                              "copertura": total.coverage,
                              "provenienza": provenance_per_dimension.get(dimension)}

    body: dict = {}
    if totals:
        body["totali"] = totals
    if form:
        body["forma"] = form
    moments = _balance_moments(points_per_dimension, measures)
    if moments:
        body["momenti"] = moments

    if battery_entity is not None:
        # Stessa forma di `forma[dimensione]` sopra, stessa ragione: `ora`
        # e' l'istante GIA' letto e tradotto (`inizio` del punto), non un
        # indice di posizione -- un buco del recorder non deve disallineare
        # la curva della batteria mentre quella dell'energia, accanto, resta
        # giusta (correzione punto 2 del mandato, «cerca i fratelli»).
        battery_points = [p for p in (series.get(battery_entity) or [])
                          if isinstance(p, dict)]
        battery_values = [{"ora": p.get("inizio"), "valore": _percent(p.get("media"))}
                           for p in battery_points]
        if any(v["valore"] is not None for v in battery_values):
            body["batteria_percentuale_oraria"] = battery_values

    return body


def aggregate_day(*, store, day: str, timezone: str | None,
                         companions=None, directions=None, balances=None) -> int:
    """Costruisce gli oggetti di un giorno. Torna quanti ne ha scritti.

    **Idempotente**: rifare un giorno lo SOSTITUISCE, non lo accoda. Gli
    oggetti si accumulano in una lista e si consegnano tutti insieme, in una
    volta sola, ad `archivio.replace_day` -- cancellare e poi inserire
    uno per uno, con un commit per ciascuno, lascerebbe un giorno mezzo
    scritto indistinguibile da uno completo se qualcosa muore a meta'. E'
    esattamente il difetto gemello che il vecchio «costruire» ha gia' pagato
    (accodava invece di sostituire, e le ancore YAML lo nascondevano).

    `companions(subject) -> list[str]` dice quali altre cose stanno con il
    protagonista. E' iniettabile perche' nella vita vera lo chiede a `legami`
    (una chiamata di rete) e nei test no. **Non si indovina dal nome**: e' il
    caso misurato del lampadario, dove tre lampade, il loro gruppo e
    l'interruttore fisico sono un sistema solo.

    `directions(subject) -> dict | None` dice la direzione di un contatore di
    energia -- `{"direzione": ..., "provenienza": "dichiarata" | "dedotta"}`,
    o `None` se non si conosce. **Stessa forma di `companions`, stessa
    ragione**: nella vita vera lo chiede a `HAClient.energy_directions()`
    (due letture di rete, `energy/get_prefs` + il registro entita'), nei
    test no. **Non si scrive nel grezzo** (mandato «le direzioni
    dell'energia», 27/08/2026, punto 2): la direzione e' una CONFIGURAZIONE
    -- la dashboard Energia dell'utente puo' cambiare -- e congelarla in
    scrittura la renderebbe irrecuperabile per i 21 giorni in cui il grezzo
    permette di rifare il giudizio, la stessa ragione per cui il grezzo
    porta `device_class` e non la gamba gia' calcolata (vedi il docstring
    del modulo). **Quando la direzione non si conosce, il campo non c'e'**
    nel corpo -- non una `"sconosciuta"` travestita da dato.

    **Il corpo porta `nome`, quando il grezzo del giorno lo portava**
    (fetta «il nome», 07/09/2026): il nome amichevole SALVATO al momento
    del cambio (`store.py::_migration_5`), non risolto ora dall'anagrafe --
    un oggetto sopravvive ai 22 giorni del grezzo e all'entita' stessa, e
    un nome risolto dopo tornerebbe a essere l'`entity_id` grezzo proprio
    sugli oggetti piu' vecchi. Il campo **tace** quando non c'e' (le righe
    scritte prima della colonna, le condizioni di sistema, le entita' su cui
    HA non scrive l'attributo): mai un `nome: null`, e chi legge mostra
    allora l'identificatore DICENDO che e' un identificatore.

    **Il corpo porta `classe`, quando il grezzo del giorno la portava**
    (fetta «lo stato», 07/09/2026): la `device_class` che Home Assistant
    dichiarava sull'entita' al momento del cambio. Non e' un dato in piu'
    «per ogni evenienza»: e' il secondo dei quattro gradini con cui HA
    traduce uno stato, e senza di lei un rilevatore di fumo scattato si
    leggerebbe «Acceso» invece di «Rilevato» (misurato dal vivo il
    07/09/2026). Tace come `nome` quando non c'e'. Vedi `close()` qui
    sotto e `proxy/state_translations.py`.

    **L'energia e' un genere a parte** (correzione del giro di review,
    punto 6): non ha un "acceso"/"spento" -- un contatore sale e basta -- e
    non nasce da un ciclo apri/chiudi come gli altri generi. Un oggetto di
    energia e' il RIEPILOGO del giorno per quel contatore: la prima lettura,
    l'ultima, e la loro differenza. Si chiude sempre dentro la giornata (mai
    `fine_ts: None`), perche' e' gia' cio' che si sa a fine giornata, non
    qualcosa ancora in corso.

    **Debito dichiarato** (secondo giro di review, punto 5): la spec (§6)
    promette che un'energia dica «quanto, in che periodo, COME DISTRIBUITO».
    Questo riepilogo dice le prime due e non la terza -- prima lettura,
    ultima e la loro differenza non dicono se il contatore e' salito piano
    per tutto il giorno o e' scattato tutto in un'ora. Quella forma (a
    bucket orari, o i punti intermedi) non c'e' ancora: la scelta e' onesta
    finche' lo dice qui, non solo nel rapporto di un giro di correzioni che
    fra un mese non legge piu' nessuno.

    **Secondo debito, dichiarato il 26/08/2026, CHIUSO il 27/08/2026**
    (mandato «le direzioni dell'energia» -- vedi le righe `energia` del vocabolario dei tipi
    per la storia): il riepilogo qui sotto era lo STESSO per un contatore
    che PRODUCE e uno che PRELEVA, entrambi `device_class: energy`/`power`.
    La GAMBA resta "energia" (non si sdoppia: e' vera per tutti e 17 i
    sensori dell'inverter, produzione compresa -- `home_space/type_vocabulary.py`), ma il
    CORPO di un episodio di energia ora porta `direzione`/`provenienza`
    quando `directions()`, sopra, le sa dire -- lette da `energy/get_prefs`
    (la dashboard Energia, dichiarata) e da `translation_key` (dedotta
    dall'integrazione, dove la dichiarata tace). Non e' un debito chiuso
    del tutto: la dichiarata copre 6 delle 17 entita' di questa casa, la
    dedotta le copre tutte ma solo su questa integrazione (`zcsazzurro`) --
    un episodio senza `direzione` resta possibile, ed e' un fatto onesto
    («non lo sappiamo»), non un buco silenzioso.

    `balances: list[dict] | None` -- **terzo debito, CHIUSO il 27/08/2026**
    (mandato «il bilancio dell'energia»): undici frammenti di energia dello
    stesso dispositivo diventano UN oggetto, di genere `"bilancio"`. Ogni
    elemento e' `{"dispositivo_id", "nome", "entita": [...], "corpo": {...}}`
    -- gia' costruito dal chiamante (`server.py::build_balances`, che
    legge `HAClient.hourly_statistics()`: **il bilancio non dipende dal
    grezzo**, viene dalle statistiche di HA, che sono piu' corrette
    (gestiscono gli azzeramenti) e piu' durature dei nostri 22 giorni). E'
    lo STESSO principio di `companions`/`directions`: la rete sta fuori da
    questa funzione, che resta sincrona.

    **Le entita' elencate in `entita` di un bilancio VALIDO (con almeno un
    totale) smettono di produrre il loro episodio di energia individuale**
    -- e' il punto per cui questa fetta esiste: se restassero entrambi,
    avremmo undici frammenti *PIU'* l'oggetto, peggio di prima. Un bilancio
    senza nemmeno un totale (le statistiche non hanno detto niente per
    nessuna delle sue dimensioni) NON sopprime niente e non si scrive: e'
    la stessa regola di `directions`, mai un oggetto vuoto al posto di
    quello che c'era. Le entita' di energia FUORI da ogni bilancio (nessun
    dispositivo, o un dispositivo di cui NESSUNA entita' ha una direzione
    riconosciuta fra `BALANCE_DIRECTIONS`) continuano a produrre il loro
    episodio come prima. **Non piu' "un dispositivo la cui unica direzione
    e' 'consumo' non basta a costruirne uno"** (frase corretta dal mandato
    «il bilancio dell'energia», punto 4, 27/08/2026: era gia' falsa da
    quando "consumo" e' entrata in `BALANCE_DIRECTIONS` come settimo totale
    -- vedi il commento sopra la costante -- ed era contraddetta da un test
    dello stesso giro, `test_server_balances.py::
    test_il_consumo_da_solo_ora_basta_e_diventa_un_candidato`: un
    dispositivo con la sola direzione "consumo" e' gia' un candidato
    valido, e produce un bilancio, non piu' il suo episodio individuale).
    **E' il genere a decidere la forma**, e un'entita' senza un bilancio da
    entrare non ha nessuna forma
    migliore di quella che gia' aveva.
    """
    from_ts, to_ts = day_boundaries(day, timezone)
    rows = store.readings(from_ts=from_ts, to_ts=to_ts)

    # Solo i bilanci VALIDI (con almeno un totale) sopprimono i loro membri
    # -- vedi il docstring di `balances` sopra: un bilancio vuoto sarebbe un
    # peggioramento puro (undici frammenti in meno, zero fatti in piu').
    valid_balances = [b for b in (balances or [])
                      if isinstance(b, dict) and (b.get("corpo") or {}).get("totali")]
    entities_in_balance: set[str] = {e for b in valid_balances for e in (b.get("entita") or [])}

    # `unavailable`/`unknown` si saltano QUI, una volta sola, prima di ogni
    # ramo e prima delle misure (`type_vocabulary.unknown_states()`, correzione
    # dei punti 2 e 3 del secondo giro di review): un riavvio di Home
    # Assistant li fa attraversare a OGNI entita'. Filtrarli a valle -- come
    # prima, con gli stati di riposo per funzionamento/sicurezza e un `if`
    # locale per presenza -- li faceva significare due cose diverse nello
    # stesso modulo: riposo in un ramo (chiude un episodio in corso), salto
    # nell'altro. La riga che
    # si perde qui e' un buco nell'informazione, non un fatto sulla casa:
    # non deve ne' aprire ne' chiudere niente, in NESSUN ramo, e non deve
    # contaminare il riepilogo di un'energia (`misure`, sotto) con
    # "unavailable" come prima o ultima lettura del giorno.
    ignored = unknown_states()
    rows = [r for r in rows
             if str(r["a"] or "").strip().lower() not in ignored]

    # Prima passata: le misure, per soggetto. Servono come contesto e non
    # generano oggetti da sole.
    measurements: dict[str, list[tuple[float, str]]] = {}
    # Il nome amichevole del soggetto, preso dal GREZZO di questo giorno --
    # mai dall'anagrafe di oggi (`store.py::_migration_5`: risolverlo dopo
    # attribuirebbe a ieri il nome di oggi, e per un oggetto piu' vecchio
    # dei 22 giorni di grezzo non ci sarebbe piu' niente da risolvere).
    #
    # **Il primo non vuoto vince**, e la regola vale per tutti e due i modi
    # in cui un episodio nasce qui sotto (il ciclo apri/chiudi e il
    # riepilogo dell'energia): uno solo, non due che possono divergere. Un
    # `None` non e' un nome, e' l'assenza di uno -- saltarlo per prendere il
    # nome che una riga successiva dello STESSO soggetto, nello STESSO
    # giorno, dichiara davvero non inventa niente. E' anche il caso vero del
    # giorno dell'aggiornamento: i cambi scritti prima della colonna non lo
    # portano, quelli scritti dopo si', e il proprietario legge la pagina
    # proprio quel giorno.
    names: dict[str, str] = {}
    for r in rows:
        measurements.setdefault(r["soggetto"], []).append((r["quando_ts"], r["a"]))
        name = r.get("friendly_name")
        if name and r["soggetto"] not in names:
            names[r["soggetto"]] = name

    open_episodes: dict[str, dict] = {}
    # **Cio' che era gia' in corso quando il giorno e' cominciato.** Un fatto
    # che DURA non ha cambi dentro il giorno: comincia prima. Leggere solo la
    # finestra del giorno lo rende invisibile, e non e' un caso di scuola --
    # misurato sulla casa vera il 10/09/2026, gli otto termostati hanno
    # prodotto otto oggetti il 06/09 (il loro ultimo cambio vero) e **zero**
    # il 07, l'08 e il 09, mentre erano accesi tutto il tempo.
    #
    # L'episodio nasce con la sua data d'inizio **vera**, non con la
    # mezzanotte: dire che il riscaldamento e' partito alle 00:00 sarebbe una
    # bugia sul quando, ed e' proprio il quando che l'analista guarda.
    #
    # Solo i generi che aprono e chiudono (`funzionamento`, `sicurezza`,
    # `presenza`): l'energia e' un riepilogo di letture DENTRO il giorno, e
    # una lettura di ieri non ne fa parte. Il `guasto` ha gia' il suo
    # meccanismo attraverso i riavvii (`watcher.rebuild_conditions`), e
    # riseminarlo anche qui sarebbero due risposte alla stessa domanda.
    for r in store.last_before(from_ts):
        subject = r["soggetto"]
        genre = genre_for(subject, _reading_aspect(subject, r))
        state = str(r["a"] or "").strip().lower()
        if genre not in ("funzionamento", "sicurezza", "presenza") or state in ignored:
            continue
        still_open = (state != "home") if genre == "presenza" else _is_on(state)
        if still_open:
            open_episodes[subject] = {
                "genere": genre, "inizio": r["quando_ts"], "stato": r["a"],
                "classe": r.get("device_class")}
            if r.get("friendly_name") and subject not in names:
                names[subject] = r["friendly_name"]
    # Gli episodi: inizio/fine di ogni oggetto, SENZA ancora i comprimari.
    # Si separano dal corpo apposta (vedi sotto): il limite superiore delle
    # misure di un comprimario dipende dal PROSSIMO episodio dello stesso
    # protagonista, che a meta' del ciclo non e' ancora noto.
    episodes: list[dict] = []
    energy_subjects: set[str] = set()

    def close(subject: str, when: float | None) -> None:
        o = open_episodes.pop(subject, None)
        if o is None:
            return
        base_body = {"stato": o["stato"]}
        # Il nome amichevole, quando il grezzo del giorno lo portava. Tace
        # come ogni altra chiave che non ha niente da dire: un `nome: null`
        # sarebbe un buco travestito da dato, e la pagina ha gia' la sua
        # regola per quando il nome manca (mostra l'identificatore DICENDO
        # che e' un identificatore, mai un nome dedotto dall'`entity_id`).
        subject_name = names.get(subject)
        if subject_name:
            base_body["nome"] = subject_name
        # La classe che Home Assistant dichiarava sull'entita' al momento del
        # cambio (`device_class` nel grezzo, `classe` qui -- il nome italiano
        # che l'anagrafe usa gia' ovunque per la stessa cosa). Non e' un
        # doppione del grezzo: gli `oggetti` vivono piu' a lungo dei `cambi`
        # (22 giorni), esattamente come per `nome`.
        #
        # **Perche' serve, e non e' un "per ogni evenienza"**: e' il SECONDO
        # gradino con cui Home Assistant traduce uno stato
        # (`helpers/translation.py:480-486`, trascritto in
        # `proxy/state_translations.py`), e senza di lei quel gradino non
        # potrebbe mai rispondere. Misurato dal vivo il 07/09/2026 sulla casa:
        # `component.binary_sensor.entity_component.smoke.state.on` e'
        # «Rilevato», mentre `..._.state.on` -- l'unico gradino raggiungibile
        # senza classe -- e' «Acceso». Un rilevatore di fumo scattato
        # leggerebbe «Acceso».
        #
        # Tace quando non c'e', come ogni altra chiave del corpo. Gli oggetti
        # aggregati PRIMA di questa riga non la portano e non si riempiono a
        # posteriori: cadono sul terzo gradino, che e' la verita' («di quella
        # riga non sappiamo la classe»), non un'invenzione.
        if o.get("classe"):
            base_body["classe"] = o["classe"]
        # `dominio`/`titolo` esistono solo per un guasto (sopra), e solo
        # quando la riga che ha aperto l'episodio li portava: tacciono come
        # ogni altra chiave del corpo che non ha niente da dire, non
        # diventano mai `null`.
        if o.get("dominio"):
            base_body["dominio"] = o["dominio"]
        if o.get("titolo"):
            base_body["titolo"] = o["titolo"]
        # `comparso_ts`: SOLO una voce di log lo porta (`_reading_row`
        # rilegge `None` per un `problema:`/`integrazione:`/`automazione:`,
        # che non lo dichiarano mai). Non e' `inizio`: `inizio` e' quando NOI l'abbiamo
        # scritto (l'orologio del giro, vedi `watcher.py::watch_system` e
        # `store.py::_migration_4`), `comparso_ts` e' quando HA dice che e'
        # cominciato -- «rilevato stamattina, va avanti dal 2» invece di una
        # data sola. `is not None`, non un controllo di verita': uno zero
        # epoch sarebbe un istante vero (per quanto assurdo su una casa
        # vera), non un campo vuoto.
        if o.get("comparso_ts") is not None:
            base_body["comparso_ts"] = o["comparso_ts"]
        episodes.append({"genere": o["genere"], "protagonista": subject,
                        "inizio": o["inizio"], "fine": when,
                        "corpo_base": base_body})

    for r in rows:
        subject = r["soggetto"]
        genre = genre_for(subject, _reading_aspect(subject, r))
        if genre is None:
            continue
        if genre == "guasto":
            # Solo condizioni di sistema arrivano qui (vedi `genre_for`). La
            # convenzione si rovescia con la fetta «il guasto e il
            # riavvio»: prima "aperto" apriva e tutto il resto chiudeva.
            # Ora `a` porta la CONDIZIONE VERA (`setup_retry`,
            # `setup_error`, ...), quindi chiude solo "chiuso" ed e' tutto
            # il resto ad aprire. Le righe scritte prima della migrazione 3
            # portano ancora "aperto" e continuano ad aprire: non serve
            # nessun caso a parte.
            if r["a"] == "chiuso":
                close(subject, r["quando_ts"])
            else:
                # Sovrascrive senza `if subject not in open_episodes` (a
                # differenza di `sicurezza`/`funzionamento` sotto): due
                # aperture di fila per lo stesso soggetto perderebbero la
                # prima data d'inizio. Non per una guardia qui, ma per la
                # disciplina dello SCRITTORE, in un altro file:
                # `watcher.py::watch_system` scrive una nascita solo per
                # `set(open_now) - self._conditions`, quindi un soggetto gia'
                # malato (in `self._conditions`) che passa da `setup_retry` a
                # `setup_error` non produce una seconda riga d'apertura --
                # SALVO l'eccezione che `watcher.py::rebuild_conditions`
                # dichiara nel suo docstring: se l'archivio non risponde
                # all'avvio, `self._conditions` riparte da vuoto, e
                # `watch_system` tratta di proposito ogni guasto gia' aperto
                # come nuovo (e' il prerequisito della garanzia attraverso i
                # riavvii: senza la riseminatura, sarebbe la regola, non
                # l'eccezione). E' un'eccezione dichiarata e voluta, non un
                # buco silenzioso -- e non e' una ragione per una guardia qui.
                open_episodes[subject] = {
                    "genere": genre, "inizio": r["quando_ts"],
                    "stato": r["a"],
                    "dominio": r.get("domain"), "titolo": r.get("title"),
                    "comparso_ts": r.get("first_occurred"),
                }
            continue
        if genre == "sicurezza":
            # Sesta gamba, entita' vera: stessa logica acceso/spento del
            # funzionamento -- il genere e' diverso, la forma no.
            if _is_on(r["a"]):
                if subject not in open_episodes:
                    open_episodes[subject] = {"genere": genre, "inizio": r["quando_ts"],
                                        "stato": r["a"], "classe": r.get("device_class")}
            else:
                close(subject, r["quando_ts"])
            continue
        if genre == "presenza":
            # «home» e' il riposo, come «off» lo e' per un funzionamento:
            # l'oggetto e' l'ASSENZA, «fuori casa dalle 8:10 alle 17:34», non
            # il ritorno. Trattare anche il ritorno come un secondo oggetto
            # aperto duplicherebbe lo stesso fatto (l'orario del rientro e'
            # gia' `fine_ts` dell'assenza) e a fine giornata lascerebbe per
            # sempre un oggetto «in casa» ancora aperto, per ogni persona,
            # ogni notte -- rumore, non un fatto compiuto.
            #
            # "unavailable"/"unknown" sono gia' fuori da `righe` (il filtro
            # in cima alla funzione): un riavvio di HA non apre ne' chiude
            # niente qui, per nessuna `person`.
            #
            # Il confronto normalizza (strip, minuscole) come `_is_on` fa
            # per gli altri rami -- pulizia del secondo giro di review: qui
            # confrontava il valore grezzo, mentre il filtro degli stati
            # ignoti, prima di questa correzione, normalizzava tre righe
            # sopra. Due convenzioni per lo stesso valore, ora una sola.
            if str(r["a"] or "").strip().lower() == "home":
                close(subject, r["quando_ts"])
            elif subject not in open_episodes:
                open_episodes[subject] = {"genere": genre, "inizio": r["quando_ts"],
                                    "stato": r["a"], "classe": r.get("device_class")}
            continue
        if genre == "funzionamento":
            if _is_on(r["a"]):
                if subject not in open_episodes:
                    open_episodes[subject] = {"genere": genre, "inizio": r["quando_ts"],
                                        "stato": r["a"], "classe": r.get("device_class")}
            else:
                close(subject, r["quando_ts"])
            continue
        # Nessun apri/chiudi qui: si annota solo CHE il soggetto e' un
        # contatore visto oggi. Il riepilogo (prima lettura, ultima,
        # differenza) si costruisce dopo il ciclo, da `misure`, che gia'
        # tiene ogni lettura del giorno in ordine cronologico.
        #
        # **Un soggetto dentro un bilancio VALIDO non produce il suo
        # episodio individuale** (mandato «il bilancio dell'energia»,
        # punto principale + punto 4): il bilancio lo sostituisce. Senza
        # questo salto avremmo undici frammenti PIU' l'oggetto -- peggio
        # di adesso, non meglio.
        if genre == "energia" and subject not in entities_in_balance:
            energy_subjects.add(subject)

    # Cio' che a fine giornata e' ancora in corso resta APERTO: `fine_ts` a
    # `None` e' un fatto, zero direbbe «finita subito».
    for subject in list(open_episodes):
        close(subject, None)

    # Le energie si costruiscono ora, dal riepilogo delle misure: un
    # oggetto di energia del giorno SI CHIUDE sempre (mai `fine_ts: None`,
    # e' gia' cio' che si sa a fine giornata) e porta valore iniziale,
    # finale e la differenza -- non la prima lettura sola con un oggetto
    # perennemente aperto, che era il difetto misurato su 29 contatori
    # della casa.
    for subject in sorted(energy_subjects):
        points = measurements.get(subject, [])
        if not points:
            continue
        # **Iniziale, finale e differenza parlano delle STESSE due letture.**
        # Il registro salta i punti che non si leggono come numero (li conta
        # sulla copertura, non li inventa): se `valore_iniziale` restasse la
        # prima riga grezza, un contatore con una lettura illeggibile a bordo
        # giornata scriverebbe «iniziale: garbage, finale: 115, differenza:
        # 15» -- tre campi che non stanno insieme. Trovato dalla revisione
        # indipendente del 12/09/2026. Se NIENTE si legge come numero restano
        # le righe grezze: sono comunque cio' che si e' visto, e la differenza
        # sara' assente.
        readable = [(when, v) for when, v in points if _as_number(v) is not None]
        edges = readable or points
        initial, final = edges[0][1], edges[-1][1]
        # Una sola lettura nel giorno non dice quanto e' cambiato: e'
        # "non lo sappiamo" -- la stessa distinzione del punto 2, e il
        # codice la fa gia' altrove restituendo `None` quando un valore non
        # si legge come numero (pulizia del secondo giro di review). Con un
        # solo punto, iniziale e finale sono la STESSA riga: il conto
        # tornerebbe 0.0, il fatto falso "non e' cambiato niente" travestito
        # da dato. **La parola resta neutra**
        # (26/08/2026): "consumato" sarebbe falso per la meta' dei sensori
        # di un impianto fotovoltaico con accumulo, che PRODUCONO.
        # Il conto passa dal registro: la guardia «un punto solo» vive li'
        # dentro, con la sua ragione scritta, invece di essere un `if` qui.
        # L'unita' non e' una dimenticanza: la tabella `cambi` non ce l'ha
        # (vedi `UNKNOWN_UNIT`). Inventare `kWh` qui sarebbe una
        # motivazione falsa su un contatore che potrebbe essere in Wh o in m3.
        rise = REGISTRY["primo_ultimo_differenza"].run(
            [{"valore": _as_number(v)} for _, v in points],
            unit=UNKNOWN_UNIT)
        difference = rise.value if rise.computable else None
        # Stessa regola di `close()` (il nome dal grezzo del giorno, il
        # campo tace quando non c'e'): l'energia nasce da un'altra strada,
        # non da un'altra legge.
        energy_body = {"valore_iniziale": initial, "valore_finale": final,
                       "differenza": difference}
        subject_name = names.get(subject)
        if subject_name:
            energy_body["nome"] = subject_name
        episodes.append({"genere": "energia", "protagonista": subject,
                        "inizio": points[0][0], "fine": points[-1][0],
                        "corpo_base": energy_body})

    # Il limite superiore delle misure di un comprimario e' l'inizio del
    # PROSSIMO episodio dello STESSO protagonista, e la fine della giornata
    # SOLO se non ce n'e' uno (correzione del giro di review, punto 5). Prima
    # di questa correzione il limite era sempre `to_ts`: un riscaldamento
    # acceso 15:30-17:05 e di nuovo 19:00-20:00, con la temperatura misurata
    # fino alle 23:00, faceva riportare al PRIMO episodio come temperatura
    # finale quella delle 23:00 -- il clima del secondo episodio e oltre.
    next_starts: dict[str, list[float]] = {}
    for e in episodes:
        next_starts.setdefault(e["protagonista"], []).append(e["inizio"])

    def upper_limit(protagonist: str, start: float) -> float:
        later = [i for i in next_starts.get(protagonist, []) if i > start]
        return min(later) if later else to_ts

    built: list[dict] = []
    for e in episodes:
        upper_bound = upper_limit(e["protagonista"], e["inizio"])
        body = {**e["corpo_base"], "comprimari": [], "misure": {}}
        if e["genere"] == "energia":
            # Solo l'energia porta una direzione (mandato, punto 2): un
            # `directions` troppo largo, o un refuso nel confronto del
            # genere, non deve poter far comparire `direzione` su un
            # funzionamento o una presenza.
            info = directions(e["protagonista"]) if directions else None
            if info:
                body["direzione"] = info["direzione"]
                body["provenienza"] = info["provenienza"]
        for other in (companions(e["protagonista"]) if companions else []):
            # Il limite INFERIORE e' l'inizio dell'oggetto: una misura presa
            # PRIMA che l'episodio cominciasse non e' cio' che si sapeva
            # della grandezza collegata mentre l'oggetto durava, e' il clima
            # di prima. Il limite SUPERIORE e' il prossimo episodio dello
            # stesso protagonista (sopra), o la fine della giornata se non ce
            # n'e' uno: cio' che si sapeva della grandezza mentre l'oggetto
            # durava e subito dopo, prima del prossimo episodio DI QUESTO
            # protagonista -- non del prossimo cambio di un argomento
            # qualunque.
            points = [(t, v) for t, v in measurements.get(other, [])
                     if e["inizio"] <= t < upper_bound]
            body["comprimari"].append(other)
            if points:
                body["misure"][other] = {"da": points[0][1], "a": points[-1][1]}
        built.append({"genere": e["genere"], "protagonista": e["protagonista"],
                          "inizio_ts": e["inizio"], "fine_ts": e["fine"],
                          "corpo": body})

    # I bilanci: un oggetto al giorno per dispositivo, protagonista =
    # `dispositivo_id` (stabile nel registro di HA -- non l'entita', che il
    # bilancio riassume, ne' il nome, che l'utente puo' cambiare: si
    # RISOLVE in aggregazione, non si congela nel grezzo, la stessa ragione
    # di `companions`/`directions`). Si CHIUDE sempre dentro la giornata (mai
    # `fine_ts: None`, come l'energia individuale sopra): e' gia' cio' che
    # si sa a fine giornata.
    for b in valid_balances:
        built.append({
            "genere": "bilancio", "protagonista": b["dispositivo_id"],
            "inizio_ts": from_ts, "fine_ts": to_ts,
            "corpo": {**b["corpo"], "dispositivo": b.get("nome"),
                     "entita": sorted(b.get("entita") or [])},
        })

    return store.replace_day(day, built)
