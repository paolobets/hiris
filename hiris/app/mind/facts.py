"""L'aggregazione: dai cambi grezzi agli oggetti.

**Un oggetto e' una cosa compiuta della casa**: qualcosa che e' cominciato, e'
durato, e' finito -- con dentro chi lo ha fatto e cosa c'era attorno mentre
durava.

    Riscaldamento camera: acceso 15:30 -> 17:05. Temperatura da 18,2 a 21,0.

**E' l'unico posto di questa fetta dove si giudica**, ed e' voluto: un giudizio
qui si rifa' finche' il grezzo esiste (22 giorni: 21 di promessa, uno di
guardia -- vedi `mind/store.READING_RETENTION_S`), uno preso in scrittura non
si corregge piu'.

**L'obiettivo sceglie QUALI entita', la natura decide CHE TIPO di oggetto ne
esce.** La prima non e' una lista scritta a mano: e' lo scope
(`mind/watcher.py`, `store.is_watched`), una decisione presa soggetto per
soggetto dall'osservatore (`mind/observer.py`, spec §5.1) -- non piu' derivata
da `device_class`/`source_type` come faceva la gamba, uscita insieme al
vocabolario dei tipi il 17/09/2026 (spec 2026-09-16 §11). **La seconda,
invece, e' un giudizio nostro**: che genere di episodio nasce da un soggetto,
e quali suoi stati valgono «a riposo», nessuna API di Home Assistant lo dice.

**Dal 07/09/2026 quel giudizio non vive piu' qui.** `_OPERABLE`, `_RESTING` e
`_UNKNOWN` erano tre elenchi scritti a mano in questo modulo; sono diventati
righe del **vocabolario dei tipi** (`home_space/type_vocabulary.py`). Spec:
`docs/design/2026-09-07-l-anagrafe-dei-tipi.md`.

**Dal 17/09/2026 il genere e il riposo si chiedono all'istantanea dei
giudizi** (`home_space/type_judgments.TypeJudgments`, spec
`docs/design/2026-09-16-il-giudizio-dei-tipi.md` §5), di cui il vocabolario e'
il seme. Questo modulo resta il LETTORE: `genre_for` chiede il genere del
soggetto, `_is_on` chiede se uno stato e' un riposo PER QUEL soggetto, e il
salto in cima a `build_episodes` toglie gli stati «non lo so» e le forme
dell'assenza di stato (`type_vocabulary.unknown_states()`,
`type_vocabulary.ABSENT_STATE_FORMS`). L'istantanea arriva come parametro
`judgments=`: in produzione e' `app["type_judgments"]`, il predefinito
`REPO_JUDGMENTS` e' il solo seme.

**Una frase che questo docstring ha portato fino a oggi era falsa**, e vale la
pena lasciarne traccia: diceva che Home Assistant «non dichiara da nessuna
parte quale dominio funziona come un interruttore». Lo dichiara -- il registro
dei servizi isola i domini con `turn_on` **e** `turn_off`, o `toggle` (spec
§4, misurato sulla casa vera il 07/09/2026: 16 domini). La derivazione non
coincide con il giudizio nostro e sbaglia in entrambi i versi, quindi non lo
sostituisce: lo **sorveglia**, ed e' lavoro delle fette 3 e 4.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from ..home_space.historian import home_space_zone
from ..home_space.type_judgments import TypeJudgments
from ..home_space.type_vocabulary import (
    ABSENT_STATE_FORMS,
    CHRONICLE_GENRES,
    REPO_JUDGMENTS,
    SYSTEM_GENRE,
    unknown_states,
)
from .recipes import Recipe
from .report import build_report
from .seed import balance_recipe

# `aggregate_day` e `build_episodes` sono SINCRONE: non fanno nessuna lettura
# di rete. Cio' che viene da Home Assistant -- le serie delle ricette, i nomi
# dei dispositivi -- arriva gia' letto dal chiamante
# (`server.py::_report_ingredients`), una lettura per giro e non una per
# episodio. Renderle `async` "per il futuro" sarebbe generalita' speculativa.

#: I quattro generi che hanno una forma (spec 2026-09-16 §5, D2), spostati in
#: `type_vocabulary.CHRONICLE_GENRES`: una casa sola, `mind/facts` la importa.
#: `energia` e `bilancio` sono usciti il 16/09/2026: nessun ramo di
#: `build_episodes` apre o chiude niente per un contatore (vedi i commenti
#: dentro la funzione, «I bilanci non entrano piu' qui» subito dopo
#: `store.readings` e «Un contatore non apre niente» piu' sotto), e nessun
#: codice produce il genere `"bilancio"`.
GENRES = CHRONICLE_GENRES

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
#: stesso verticale). **Il suo unico lettore e' `genre_for`**, qui sotto, che
#: ne fa un `guasto`. Fino al 09/09/2026 (audit delle fondamenta) la stessa
#: tupla era scritta a mano in tre posti; gli altri due lettori sono usciti:
#: `api/handlers_mind.py::_with_rendered_states` il 15/09/2026 con gli oggetti
#: (commit `b2b2b55e`), `_reading_aspect` il 17/09/2026 con la gamba.
NOT_ENTITY_PREFIXES = ("problema:", "integrazione:", "log:", "automazione:")

# **Il riposo e' del SOGGETTO, non l'unione di tutti i tipi** (17/09/2026, spec
# 2026-09-16 §5). Fino ad allora `_is_on` riceveva lo stato nudo e lo
# confrontava con `type_vocabulary.resting_states()`, l'unione dei riposi di
# ogni tipo; ora riceve anche il soggetto e la sua classe, e chiede
# all'istantanea il riposo di QUEL soggetto (entita', poi coppia, poi dominio).
# **Misurato prima di cambiarlo** (spec §1, misura 7): ripassate 52.123 righe
# di storia di Home Assistant su 304 entita' dei tipi con genere, dal 09/09 al
# 16/09/2026, nessuna riga cambia esito. L'unico cambio che la casa vede e' il
# salto di `none` e del vuoto, dichiarato in `build_episodes`.


def genre_for(subject: str, device_class: str | None, *,
              judgments: TypeJudgments = REPO_JUDGMENTS) -> str | None:
    """Che genere di episodio puo' nascere da questo soggetto, o `None` se non
    ne nasce nessuno.

    **Le condizioni di sistema sono `guasto` qui, nel codice**: `problema:`,
    `integrazione:`, `log:` (una voce del registro di errori) e `automazione:`
    (un'esecuzione in errore) non sono entita' di Home Assistant, e la loro
    forma e' codice. Per ogni entita' il genere e' un **giudizio
    dell'istantanea** (spec 2026-09-16 §5): prima l'entita', poi la coppia
    dominio/`device_class` della riga di grezzo, poi il dominio. Un `nessuno`
    scritto su un livello nega quelli sopra.

    **I sensori da soli non generano episodi**: «la temperatura e' salita» non
    e' una cosa compiuta, e' il CONTESTO di qualcosa che e' successo. Nel seme
    il dominio `sensor` non ha nessuna riga `genere`, e nemmeno le sue coppie.

    **`sicurezza` non e' `guasto`.** Serrature, pannello dell'allarme, sirene e
    i `binary_sensor` di fumo, gas, monossido, allagamento, sicurezza,
    manomissione, problema, calore e gelo hanno la stessa FORMA di una
    condizione di sistema -- nascono, durano, finiscono o restano aperti -- ma
    una porta aperta con la chiave e un'integrazione Sonos rotta non sono lo
    stesso genere di fatto. Nel seme sono righe `genere` `sicurezza`, e una
    sirena (accendibile anche lei) e' `sicurezza`, non `funzionamento`.

    **Il monossido misurato resta fuori, e restare fuori e' la decisione**: un
    `sensor` di classe `carbon_monoxide` MISURA una concentrazione, non SCATTA.
    Una lettura come "0.4" non e' mai un riposo e aprirebbe un episodio che non
    chiude mai; servirebbe una soglia, e non ne abbiamo una onesta. Il seme non
    gli scrive nessun genere; il `binary_sensor` di monossido, che scatta
    davvero, e' `sicurezza`.
    """
    if subject.startswith(NOT_ENTITY_PREFIXES):
        return "guasto"
    return judgments.genre_of(subject, device_class)


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


def _is_on(value, subject: str, device_class: str | None,
           judgments: TypeJudgments) -> bool:
    """Se questo stato NON e' un riposo **per questo soggetto** -- cioe' se
    l'episodio e' ancora in corso. Il riposo e' quello che l'istantanea
    dichiara per l'entita', la coppia o il dominio (vedi il commento sopra
    `genre_for`: misurato, nessuna riga della casa cambia esito)."""
    domain = subject.split(".")[0]
    state = str(value or "").strip().lower()
    return state not in judgments.resting_of(domain, device_class, subject)


def _opening_attributes(row: dict):
    """La foto degli attributi voluti al momento in cui l'episodio si apre.

    E' la riga del cambio di STATO, che l'osservatore scrive gia' con gli
    attributi che il sapere vuole (`mind/watcher.py`, spec §5.4). Senza di
    lei il corpo dell'episodio comincerebbe dal primo cambio SUCCESSIVO, e
    meta' della colonna `attributes` del grezzo resterebbe scritta e non letta
    da nessuno (Fable 5.1, 13/09/2026).

    Lista vuota quando non c'e' niente: mai una voce con un dizionario vuoto,
    che direbbe «li abbiamo guardati e non c'erano».
    """
    raw_attributes = row.get("attributes")
    if not raw_attributes:
        return []
    try:
        values = json.loads(raw_attributes)
    except (TypeError, ValueError):
        return []
    return [(row["quando_ts"], values)] if isinstance(values, dict) and values else []


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
    """Un numero del bilancio dell'energia -> kWh arrotondati a 2 decimali.

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
                      esiti: dict) -> dict:
    """I momenti derivati dalla forma e dagli esiti della ricetta -- vedi
    `build_balance_body` per il contratto completo. Separata per
    restare leggibile: ogni momento e' un piccolo giudizio a se'.

    **Le due quote NON si calcolano qui**: sono passi della ricetta
    (`mind/seed.balance_recipe`), e qui si leggono i loro esiti. Ricalcolarle
    sarebbe una seconda copia dello stesso conto, ed e' esattamente cio' che
    questa fetta esiste per togliere -- la prova storica e' il 27/08/2026,
    quando quel conto viveva solo qui e per correggerlo e' servito un
    rilascio.

    Cio' che resta qui e' cio' che **non e' un'operazione del registro**: il
    primo e l'ultimo istante di produzione, il picco, la fine della scarica.
    Sono letture della forma, non conti -- e inventare un'operazione per
    ciascuna sarebbe il modo in cui un registro «chiuso» smette di esserlo.
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

    autoconsumo_share = esiti.get("quota_autoconsumo")
    if autoconsumo_share is not None and autoconsumo_share.computable:
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
    self_sufficiency_share = esiti.get("quota_autosufficienza")
    if self_sufficiency_share is not None and self_sufficiency_share.computable:
        moments["quota_autosufficienza"] = self_sufficiency_share.value

    return moments


def build_balance_body(*, series: dict[str, list[dict]],
                              entity_per_dimension: dict[str, str],
                              provenance_per_dimension: dict[str, str],
                              battery_entity: str | None = None,
                              expected_hours: int | None = None,
                              recipe: dict | None = None) -> dict:
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
    # **Il conto passa da una RICETTA** (fetta «il sapere e le ricette»,
    # 12/09/2026): non e' piu' un ciclo scritto qui, e' una sequenza di passi
    # con nomi che si legge, si valida e si rifiuta prima di eseguirla
    # (`mind/recipes.py`). La ricetta la compone `mind/seed.balance_recipe`
    # dalla mappa direzione -> entita' che il chiamante ha gia' risolto.
    #
    # **Perche' conta, con una prova storica.** Il 27/08/2026 la quota di
    # autosufficienza era sbagliata: `autoconsumo/(autoconsumo + prelievo)`
    # vale solo su certe integrazioni -- misurato 0,964 invece di 0,985. Era
    # una ricetta specifica di un'integrazione scritta dentro questo motore, e
    # per correggerla e' servito un rilascio.
    # **La ricetta arriva da fuori quando c'e'**, e quella del repo e' il
    # ripiego (13/09/2026): il chiamante la legge dal sapere, dove puo' essere
    # stata corretta a mano o riscritta dal modello. E' la meta' che mancava
    # alla promessa della spec §7 -- *«come dato sarebbe stata correggibile
    # senza un rilascio»* -- e finche' la ricetta si ricomponeva qui a ogni
    # giro quella frase era falsa.
    ricetta = Recipe(recipe if recipe is not None else balance_recipe(
        entity_per_dimension, order=BALANCE_DIRECTIONS,
        expected_hours=expected_hours))
    # **Nessun passo = nessun bilancio, non un'eccezione** (revisione
    # indipendente, 13/09/2026). Un dispositivo senza nemmeno una direzione
    # utile produce una ricetta vuota, e una ricetta vuota `run()` la rifiuta
    # sollevando -- giustamente, perche' per lei e' una ricetta che nessuno ha
    # finito di scrivere. Ma questa funzione promette un dizionario vuoto in
    # quel caso, e il suo chiamante cicla sui dispositivi senza `try`: un solo
    # dispositivo sfortunato avrebbe fatto saltare i bilanci di tutti gli altri.
    if not ricetta.steps:
        return {}
    # **Il perimetro della validazione e' costruito dalla ricetta stessa, e
    # questo va detto** (Fable 5.1, 13/09/2026): il rifiuto «questa entita' non
    # e' fra quelle consegnate» non puo' scattare da qui, perche' le serie si
    # costruiscono dai nomi che la ricetta nomina. Non e' un difetto nascosto:
    # un'entita' che Home Assistant non ha restituito diventa una serie vuota,
    # quindi una dimensione **non calcolabile** -- che e' l'esito giusto per il
    # prodotto (la dimensione non compare) e un esito diverso da «ricetta
    # rifiutata». Il controllo sulle entita' serve a chi scrivera' una ricetta
    # a mano, cioe' alla fetta in cui le ricette arrivano dal modello.
    punti_per_entita = {e: _dimension_points(series, e) for e in ricetta.entities()}
    esiti = ricetta.run(series=punti_per_entita)

    for dimension in BALANCE_DIRECTIONS:
        total = esiti.get(dimension)
        if total is None or not total.computable:
            continue
        profile = esiti[f"forma_{dimension}"]
        points_per_dimension[dimension] = punti_per_entita[
            entity_per_dimension[dimension]]
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
    moments = _balance_moments(points_per_dimension, esiti)
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


def build_episodes(*, store, day: str, timezone: str | None,
                   judgments: TypeJudgments = REPO_JUDGMENTS) -> list[dict]:
    """Gli episodi di un giorno, nella forma che `report.build_report` riceve.

    Ogni episodio e' `{"genere", "protagonista", "inizio", "fine",
    "corpo_base"}`: `fine` a `None` quando a fine giornata e' ancora in corso.
    **Legge soltanto l'archivio** -- `store.readings` (i cambi del giorno) e
    `store.last_before` (cio' che era gia' in corso a mezzanotte) -- e non
    scrive niente: estratta da `aggregate_day` il 17/09/2026 perche' la cronaca
    si possa costruire senza le misure (spec 2026-09-16 §1, misura 10).

    **Il genere e il riposo vengono da `judgments`** (spec §5): in produzione
    l'istantanea viva, `app["type_judgments"]`; il predefinito `REPO_JUDGMENTS`
    e' il solo seme del repo. Un episodio di `funzionamento`, `sicurezza` o
    `presenza` e' aperto quando lo stato non e' a riposo per il suo soggetto
    (`_is_on`); un `guasto` apre su qualunque condizione e chiude su `chiuso`.

    **Il corpo porta `nome`, quando il grezzo del giorno lo portava**
    (fetta «il nome», 07/09/2026): il nome amichevole SALVATO al momento
    del cambio (`store.py::_migration_5`), non risolto ora dall'anagrafe --
    un resoconto sopravvive ai 22 giorni del grezzo e all'entita' stessa, e
    un nome risolto dopo tornerebbe a essere l'`entity_id` grezzo proprio
    sulle voci piu' vecchie. Il campo **tace** quando non c'e' (le righe
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
    """
    from_ts, to_ts = day_boundaries(day, timezone)
    rows = store.readings(from_ts=from_ts, to_ts=to_ts)

    # **I bilanci non entrano piu' qui** (15/09/2026). Servivano a due cose:
    # diventare un oggetto, e sopprimere gli episodi individuali dei loro
    # membri. La prima e' uscita con gli oggetti; la seconda non ha piu'
    # oggetto, perche' gli episodi di energia sono usciti anche loro -- un
    # contatore e' un numero, e i numeri stanno fra le misure, dove il
    # bilancio arriva per la sua ricetta.

    # `unavailable`/`unknown` si saltano QUI, una volta sola, prima di ogni
    # ramo (`type_vocabulary.unknown_states()`, correzione dei punti 2 e 3 del
    # secondo giro di review): un riavvio di Home Assistant li fa attraversare
    # a OGNI entita'. Filtrarli a valle -- come prima, con gli stati di riposo
    # per funzionamento/sicurezza e un `if` locale per presenza -- li faceva
    # significare due cose diverse nello stesso modulo: riposo in un ramo
    # (chiude un episodio in corso), salto nell'altro. La riga che si perde qui
    # e' un buco nell'informazione, non un fatto sulla casa: non deve ne'
    # aprire ne' chiudere niente, in NESSUN ramo. Lo stesso insieme salta lo
    # stato ereditato da prima di mezzanotte (`store.last_before`, sotto).
    #
    # Una riga saltata non porta nemmeno il suo nome ne' i suoi attributi:
    # il filtro la toglie prima della raccolta dei nomi e dei cambi di
    # attributo, qui sotto.
    #
    # **Dal 17/09/2026 si saltano anche `none` e il vuoto**
    # (`type_vocabulary.ABSENT_STATE_FORMS`, spec 2026-09-16 §5): sono un dato
    # che manca, come `unavailable`, non il riposo di nessuno. **Cambio di
    # comportamento dichiarato, misurato** (spec §1, misura 8): in una
    # settimana, dal 09/09 al 16/09/2026, 200 righe `none` da 6 apparati di
    # rete, quasi tutte intorno alle 23. Su un `device_tracker` `none` apriva
    # un'assenza (non era `home`); su uno `switch` chiudeva l'episodio (era
    # nell'unione dei riposi). Ora non apre e non chiude niente.
    ignored = unknown_states() | ABSENT_STATE_FORMS.value
    rows = [r for r in rows
             if str(r["a"] or "").strip().lower() not in ignored]

    # Il nome amichevole del soggetto, preso dal GREZZO di questo giorno --
    # mai dall'anagrafe di oggi (`store.py::_migration_5`: risolverlo dopo
    # attribuirebbe a ieri il nome di oggi, e per un oggetto piu' vecchio
    # dei 22 giorni di grezzo non ci sarebbe piu' niente da risolvere).
    #
    # **Il primo non vuoto vince**, e la regola vale per tutti e due i modi
    # in cui un episodio nasce qui sotto (lo stato ereditato da prima di
    # mezzanotte e il ciclo apri/chiudi del giorno): uno solo, non due che
    # possono divergere. Un
    # `None` non e' un nome, e' l'assenza di uno -- saltarlo per prendere il
    # nome che una riga successiva dello STESSO soggetto, nello STESSO
    # giorno, dichiara davvero non inventa niente. E' anche il caso vero del
    # giorno dell'aggiornamento: i cambi scritti prima della colonna non lo
    # portano, quelli scritti dopo si', e il proprietario legge la pagina
    # proprio quel giorno.
    # **`entity_names`, non `names`: sono due cose diverse.** Qui vivono i
    # nomi amichevoli delle ENTITA', letti dal grezzo e per chiave
    # l'`entity_id`; il parametro `names` di `aggregate_day` porta i nomi dei
    # DISPOSITIVI, per chiave l'id del dispositivo, e serve alle misure.
    #
    # Fino al 15/09/2026 si chiamavano tutt'e due `names`, e questa riga
    # cancellava il parametro. Il risultato si e' letto nella prima analisi
    # vera: l'analista parlava al proprietario in esadecimale -- «513a6661 ·
    # prelievo» -- e sul resoconto del giorno **zero misure su 73** portavano
    # un nome.
    entity_names: dict[str, str] = {}
    for r in rows:
        name = r.get("friendly_name")
        if name and r["soggetto"] not in entity_names:
            entity_names[r["soggetto"]] = name

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
    # Solo i generi che aprono e chiudono sullo stato (`funzionamento`,
    # `sicurezza`, `presenza`), con la stessa regola del ciclo del giorno:
    # aperto se lo stato non e' a riposo per il soggetto. Il `guasto` ha gia'
    # il suo meccanismo attraverso i riavvii (`watcher.rebuild_conditions`), e
    # riseminarlo anche qui sarebbero due risposte alla stessa domanda.
    for r in store.last_before(from_ts):
        subject = r["soggetto"]
        genre = genre_for(subject, r.get("device_class"), judgments=judgments)
        state = str(r["a"] or "").strip().lower()
        if genre not in ("funzionamento", "sicurezza", "presenza") or state in ignored:
            continue
        still_open = _is_on(state, subject, r.get("device_class"), judgments)
        if still_open:
            open_episodes[subject] = {
                "genere": genre, "inizio": r["quando_ts"], "stato": r["a"],
                "classe": r.get("device_class")}
            if r.get("friendly_name") and subject not in entity_names:
                entity_names[subject] = r["friendly_name"]
    # Gli episodi chiusi (o ancora aperti a fine giornata), nell'ordine in cui
    # `close()` li consegna.
    episodes: list[dict] = []
    # I cambi di ATTRIBUTO del giorno, per soggetto: `[(istante, {nome:
    # valore}), ...]` in ordine cronologico. Sono le righe che l'osservatore
    # scrive quando cambia un attributo che il sapere ha dichiarato utile
    # (`mind/watcher.py`, spec §5.4) -- e senza di loro l'esempio fondativo
    # del cervello non e' rispondibile: lo stato di un termostato e' `heat` e
    # resta `heat`, mentre `hvac_action` dice quando la casa e' arrivata in
    # temperatura.
    attribute_changes: dict[str, list[tuple[float, dict]]] = {}

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
        subject_name = entity_names.get(subject)
        if subject_name:
            base_body["nome"] = subject_name
        # La classe che Home Assistant dichiarava sull'entita' al momento del
        # cambio (`device_class` nel grezzo, `classe` qui -- il nome italiano
        # che l'anagrafe usa gia' ovunque per la stessa cosa). Non e' un
        # doppione del grezzo: il `resoconto` vive piu' a lungo dei `cambi`
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
        # Tace quando non c'e', come ogni altra chiave del corpo. Le voci
        # aggregate PRIMA di questa riga non la portano e non si riempiono a
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
        # **Cosa hanno fatto gli attributi MENTRE l'episodio durava.** E'
        # il lettore della colonna `attributes` del grezzo, e la ragione per
        # cui quella colonna esiste: un episodio di riscaldamento che porta
        # `hvac_action: heating -> idle alle 16:30` risponde alla domanda
        # fondativa del cervello, che prima di oggi non era rispondibile.
        #
        # Dentro la finestra dell'episodio, estremi compresi a sinistra e
        # esclusi a destra -- la stessa convenzione di
        # `mind/operations.Period.contains`, una sola in tutto il prodotto.
        # Un episodio ancora aperto (`when is None`) prende tutto cio' che
        # viene dopo il suo inizio.
        # **La foto d'apertura c'e', e senza di lei meta' della colonna
        # `attributes` restava scritta e non letta** (Fable 5.1, 13/09/2026):
        # la riga del cambio di STATO porta gia' gli attributi voluti -- il
        # `hvac_action: heating` delle 15:30 -- e quel primo istante spariva
        # dal corpo, che cominciava dal primo cambio successivo.
        #
        # **La forma e' una FOTO, non un delta**, e va detto: ogni voce porta
        # tutti gli attributi voluti di quel momento, non il solo che si e'
        # mosso. Chi legge due voci vicine vede cosa e' cambiato confrontandole;
        # chi ne legge una sola sa lo stato di tutti. Il delta sarebbe piu'
        # compatto e meno leggibile da solo, e questa e' la cronaca di un
        # giorno, non un flusso da ricostruire.
        during = list(o.get("attributi_apertura") or [])
        during += [(instant, values)
                   for instant, values in attribute_changes.get(subject, [])
                   if instant > o["inizio"] and (when is None or instant < when)]
        if during:
            base_body["attributi"] = [
                {"quando_ts": instant, "valori": values} for instant, values in during]
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
        # **La riga di solo attributo si raccoglie PRIMA di ogni giudizio di
        # genere**, e poi non prosegue: non apre e non chiude niente -- lo
        # stato di partenza e quello d'arrivo sono lo stesso -- ma dice cosa
        # ha fatto la grandezza mentre l'episodio durava (spec §5.4). Senza
        # questa raccolta la colonna `attributes` del grezzo sarebbe scritta
        # e non letta da nessuno.
        if r["da"] == r["a"] and r.get("attributes"):
            try:
                values = json.loads(r["attributes"])
            except (TypeError, ValueError):
                # Una riga vecchia o storta non ferma la giornata: si salta.
                values = None
            if isinstance(values, dict) and values:
                attribute_changes.setdefault(subject, []).append(
                    (r["quando_ts"], values))
            continue
        genre = genre_for(subject, r.get("device_class"), judgments=judgments)
        if genre is None:
            continue
        if genre == SYSTEM_GENRE:
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
                # differenza del ramo dei tre generi di stato, sotto): due
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
        if genre in ("funzionamento", "sicurezza", "presenza"):
            # **Una forma sola per i tre generi** (spec 2026-09-16 §5): aperto
            # quando lo stato non e' a riposo per il soggetto, chiuso quando lo
            # e'. Il genere e' diverso, la forma no.
            #
            # **La presenza non ha piu' un ramo suo.** Fino al 17/09/2026 qui
            # c'era un confronto scritto a mano con `"home"`; ora `home` e' la
            # riga `riposo` di `person` e `device_tracker` nel seme, e l'episodio
            # di una persona resta l'ASSENZA, «fuori casa dalle 8:10 alle
            # 17:34», non il ritorno. Trattare anche il ritorno come un secondo
            # episodio duplicherebbe lo stesso fatto (l'orario del rientro e'
            # gia' `fine_ts` dell'assenza). Un sensore di presenza a cui la
            # casa scrive il genere `presenza` apre a `on` e chiude a `off`,
            # il riposo del suo dominio: lo dicono `cosa` e `classe`.
            #
            # `if subject not in open_episodes`: un cambio fra due stati non a
            # riposo -- una persona che da `not_home` entra nella zona
            # `ufficio`, una TV da `playing` a `paused` -- non riapre
            # l'episodio e non ne azzera inizio e stato.
            if _is_on(r["a"], subject, r.get("device_class"), judgments):
                if subject not in open_episodes:
                    open_episodes[subject] = {"genere": genre, "inizio": r["quando_ts"],
                                              "stato": r["a"], "classe": r.get("device_class"),
                                              "attributi_apertura": _opening_attributes(r)}
            else:
                close(subject, r["quando_ts"])
            continue
        # **Un contatore non apre niente.** Fino al 15/09/2026 qui si
        # annotava che il soggetto era un contatore, per costruirgli dopo
        # un episodio di energia; quell'episodio e' uscito, perche' un
        # contatore non ha uno stato, ha un numero -- e i numeri stanno
        # fra le misure, dove la ricetta li porta con la copertura che
        # l'episodio non aveva. Dal 16/09/2026 nemmeno il genere `energia`
        # esiste piu' (spec 2026-09-16 §5, D2): l'istantanea ammette solo i
        # quattro generi trattati qui sopra, e nessuna riga arriva fin qui.

    # Cio' che a fine giornata e' ancora in corso resta APERTO: `fine_ts` a
    # `None` e' un fatto, zero direbbe «finita subito».
    for subject in list(open_episodes):
        close(subject, None)
    # **L'energia non e' un EPISODIO** (15/09/2026, con gli oggetti).
    # Qui si costruiva un episodio per ogni contatore -- valore iniziale,
    # finale, differenza -- e il suo unico lettore era l'oggetto. Nella
    # cronaca quella voce direbbe «quando, chi, genere: energia, cosa:
    # niente»: un contatore non ha uno stato, ha un numero, e un numero
    # sta fra le MISURE.
    #
    # **Verificato dal vivo prima di toglierlo**: i tre contatori della
    # casa che avevano un episodio di energia sono tutti coperti da una
    # ricetta -- `energia_totale_periodo` (somma_periodo) per la presa,
    # `potenza_media_min_max` per la potenza, il bilancio per l'inverter.
    # I numeri non si perdono: cambiano posto, e prendono la copertura che
    # l'episodio non aveva.

    # **Gli OGGETTI sono usciti** (spec §13, 15/09/2026): qui si costruiva
    # un secondo strato -- episodio piu' comprimari piu' misure -- che viveva
    # accanto al resoconto e diceva le stesse cose in un'altra forma.
    #
    # **Misurato sulla casa vera prima di cancellarlo**: 200 oggetti, e i
    # comprimari erano **zero su 200** -- il campo `misure` vuoto in tutti.
    # La perdita che si temeva non esisteva: non c'era niente da perdere.
    # E ogni giorno che aveva oggetti (26/08 -> 14/09) aveva gia' il suo
    # resoconto, quindi nemmeno la storia si e' persa.
    return episodes


def aggregate_day(*, store, day: str, timezone: str | None,
                  recipes=None, series=None, names=None,
                  without_statistics=None,
                  judgments: TypeJudgments = REPO_JUDGMENTS) -> int:
    """Scrive il resoconto di un giorno. Torna quante voci di cronaca porta.

    **Il resoconto e' la cronaca piu' le misure** (spec §9): la cronaca sono gli
    episodi di `build_episodes`, che legge il grezzo dell'archivio con
    l'istantanea `judgments`; le misure arrivano gia' lette dal chiamante --
    `recipes` (le ricette dal sapere), `series` (le serie delle entita' che le
    ricette nominano), `names` (i nomi dei DISPOSITIVI, per chiave l'id) e
    `without_statistics` -- e si incontrano in `report.build_report`, che e'
    pura. L'obiettivo e' quello che valeva alla fine di QUEL giorno
    (`store.objective_at`), non quello di oggi.

    **Sincrona, nessuna lettura di rete**: tutto cio' che viene da Home
    Assistant l'ha gia' letto il chiamante (`server.py::_report_ingredients`).

    **Idempotente**: rifare un giorno lo SOSTITUISCE, non lo accoda. Il
    resoconto si costruisce tutto in memoria e si consegna in una scrittura
    sola ad `store.replace_report`, che sostituisce la riga del giorno: niente
    giorno mezzo scritto indistinguibile da uno completo se qualcosa muore a
    meta'. E' esattamente il difetto gemello che il vecchio «costruire» ha gia'
    pagato (accodava invece di sostituire, e le ancore YAML lo nascondevano).

    **In produzione `judgments` e' `app["type_judgments"]`**, l'istantanea viva
    (i tre chiamanti in `server.py`); il predefinito `REPO_JUDGMENTS` e' il
    solo seme, per le prove.

    **Il bilancio non entra piu' qui, e non produce un genere `"bilancio"`**
    (15/09/2026, con gli oggetti). Fino ad allora questa funzione riceveva un
    parametro `balances` che faceva nascere un oggetto di genere `"bilancio"`;
    quel parametro non esiste piu', e il bilancio vive fra le MISURE, con la
    sua ricetta (`mind/seed.balance_recipe`).
    """
    episodes = build_episodes(store=store, day=day, timezone=timezone, judgments=judgments)
    _, to_ts = day_boundaries(day, timezone)
    # **Si scrive SEMPRE, anche senza ricette.** Fino al 15/09/2026 un
    # chiamante che non portava le ricette non faceva scrivere niente, e la
    # ragione era buona: un resoconto con meta' delle misure vuota per un
    # motivo che non riguarda la casa resterebbe li' a dire il falso. Ma quella
    # ragione reggeva finche' c'erano gli OGGETTI a tenere il giorno; tolti
    # quelli, non scrivere vuol dire **perdere il giorno**, e «non e' successo
    # niente» tornerebbe a confondersi con «non l'abbiamo guardato» -- la
    # distinzione per cui il resoconto esiste.
    # **L'impronta dei giudizi viaggia con la cronaca** (spec 2026-09-16 §6):
    # e' cio' che permette al recupero di sapere quali giorni sono nati con un
    # altro giudizio, e al documento di dirlo.
    store.replace_report(day, build_report(
        day=day, episodes=episodes, series=series or {},
        recipes=recipes or {}, names=names or {},
        without_statistics=without_statistics,
        objective=store.objective_at(to_ts),
        judgment={"impronta": judgments.chronicle_fingerprint()}))
    # **Torna quante voci di cronaca ha scritto.** Prima tornava quanti
    # oggetti aveva salvato: e' lo stesso numero detto nella lingua che resta.
    return len(episodes)


def chronicle_is_stale(report: dict, judgments: TypeJudgments) -> bool:
    """Una cronaca e' vecchia se non dice con quale giudizio e' nata, o se e'
    nata con un altro (spec 2026-09-16 §6).

    **L'assenza conta come «un altro»**: i resoconti scritti prima del
    17/09/2026 non portano impronta, e sono proprio quelli che il primo avvio
    deve rifare dentro il grezzo.
    """
    fingerprint = ((report or {}).get("giudizio") or {}).get("impronta")
    return fingerprint != judgments.chronicle_fingerprint()


def rebuild_chronicle(*, store, day: str, timezone: str | None,
                      judgments: TypeJudgments = REPO_JUDGMENTS) -> bool:
    """Rifa' **solo** la cronaca di un giorno col giudizio di adesso. Torna
    `True` se ha riscritto, `False` se quel giorno non ha un resoconto.

    Misure, forme e obiettivo restano quelli scritti: **nessuna lettura di Home
    Assistant, nessuna ricetta riletta** -- le statistiche di un giorno vecchio
    possono non esserci piu', e rifare le misure le perderebbe (spec 2026-09-16
    §6). Gli episodi escono da `build_episodes`, la stessa costruzione di
    `aggregate_day`; la voce di cronaca e l'impronta da `build_report`, che
    resta pura: le misure che calcola su serie e ricette vuote si buttano.

    **Gli episodi EREDITATI da prima del giorno si tengono, a una condizione.**
    Misurato dalla revisione del 17/09/2026: un termostato acceso da venticinque
    giorni entra nella cronaca di oggi per la sua riga d'origine
    (`store.last_before`), e quella riga esce dal grezzo prima del giorno che
    la eredita. Rifare quel giorno perdeva la voce. Una voce scritta che
    **comincia prima dell'inizio del giorno** e che la cronaca rifatta non ha
    (stessa identita': `chi` e `quando_ts`) si tiene se:

    - il grezzo **non ha piu' nessuna riga** di quel soggetto prima del giorno
      -- se ce l'ha, l'assenza e' un giudizio nuovo (un riposo cambiato), non
      un grezzo perso, e la voce esce;
    - il soggetto ha **ancora un genere** per i giudizi di adesso
      (`genre_for`, con la `classe` della voce): un `nessuno` la toglie.

    Si inserisce dove la cronaca di oggi la metterebbe: le chiuse per `fine_ts`,
    poi le ancora aperte per `quando_ts`, senza spostare le voci rifatte (vedi
    `_chronicle_position`).

    **Il limite, dichiarato**: una voce tenuta cosi' conserva la forma con cui
    era stata scritta -- non si puo' rifare senza la sua riga d'origine -- e
    resta cosi' anche sotto l'impronta nuova. Le voci che cominciano DENTRO il
    giorno non si tengono mai: per questo il recupero non rifa' un giorno che
    puo' aver perso righe per la potatura -- cioe' che comincia prima del taglio
    (`server.py::backfill_one_report`), non un giorno che comincia prima della
    riga piu' vecchia.

    **Il residuo che le due condizioni non coprono: riposo cambiato E riga
    d'origine potata.** Le due condizioni verificano che il grezzo sia sparito
    e che il soggetto abbia ANCORA un genere -- non che il giudizio di OGGI
    avrebbe aperto quella stessa voce. Una voce ereditata puo' quindi restare
    anche quando il giudizio nuovo non l'avrebbe mai aperta cosi' (un riposo
    diventato piu' largo, per esempio): non c'e' modo di accorgersene senza la
    riga d'origine, ed e' gia' potata. Resta com'e', sotto qualunque impronta,
    finche' il giorno non torna raggiungibile dal grezzo -- cioe', superati i
    22 giorni di ritenzione (`mind/store.READING_RETENTION_S`), mai.

    **Un giorno senza resoconto non si tocca**: farlo intero, con le misure,
    e' lavoro del recupero (`server.py::backfill_one_report`), non di questa
    funzione.
    """
    report = store.report(day)
    if report is None:
        return False
    episodes = build_episodes(store=store, day=day, timezone=timezone, judgments=judgments)
    rebuilt = build_report(day=day, episodes=episodes, series={}, recipes={}, names={},
                           judgment={"impronta": judgments.chronicle_fingerprint()})
    chronicle = list(rebuilt["cronaca"])
    from_ts, _ = day_boundaries(day, timezone)
    rebuilt_ids = {(v.get("chi"), v.get("quando_ts")) for v in chronicle}
    raw_subjects = {r["soggetto"] for r in store.last_before(from_ts)}
    for entry in report.get("cronaca") or []:
        started = entry.get("quando_ts")
        subject = entry.get("chi")
        if (started is None or started >= from_ts or subject is None
                or (subject, started) in rebuilt_ids or subject in raw_subjects
                or genre_for(subject, entry.get("classe"), judgments=judgments) is None):
            continue
        key = _chronicle_position(entry)
        index = next((i for i, v in enumerate(chronicle)
                      if _chronicle_position(v) > key), len(chronicle))
        chronicle.insert(index, entry)
    store.replace_report(day, {**report, "cronaca": chronicle,
                               "giudizio": rebuilt["giudizio"]})
    return True


def _chronicle_position(entry: dict) -> tuple:
    """Dove una voce sta nella cronaca di un giorno, nell'ordine in cui
    `build_episodes` la consegna: prima le chiuse, nell'ordine in cui si sono
    chiuse (`fine_ts`), poi quelle ancora aperte a fine giornata, nell'ordine in
    cui si sono aperte -- le ereditate prima delle nate nel giorno.

    Serve solo a `rebuild_chronicle` per INSERIRE una voce tenuta: le voci
    rifatte non si riordinano, restano nell'ordine di `build_episodes`.
    """
    end = entry.get("fine_ts")
    if end is not None:
        return (0, float(end))
    return (1, float(entry.get("quando_ts") or 0.0))
