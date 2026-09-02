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
esce.** La prima non e' una lista scritta a mano: il pavimento (`baseline.
gamba`) deriva QUALI entita' da cio' che Home Assistant dichiara gia' --
dominio, `device_class`, `source_type` (**non `state_class`**: correzione
di parole della review, mandato «il bilancio dell'energia», punto 7,
27/08/2026 -- dopo la correzione del 27/08, `baseline.aspect` non lo legge
piu' per decidere nessuna gamba, vedi il suo docstring). **La seconda, invece, SI'**
(correzione del giro di review, punto 9): `_OPERABLE` qui sotto e' una
lista scritta a mano dei domini che si accendono e si spengono. Non c'e' modo
di derivarla: Home Assistant non dichiara da nessuna parte «questo dominio
funziona come un interruttore», quindi va mantenuta a mano e tenuta
aggiornata quando un dominio nuovo lo fa -- la vecchia frase di questo
docstring affermava il contrario, ed era falsa quanto una funzione sbagliata.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..home_space.historian import home_space_zone
from .baseline import aspect

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

# I domini che «funzionano»: si accendono e si spengono, si aprono e si
# chiudono. Sono i protagonisti degli oggetti di funzionamento. **Lista
# scritta a mano, dichiaratamente** (vedi il docstring del modulo): mancavano
# `humidifier`, `vacuum`, `valve` e `media_player` -- domini comuni che
# funzionano come gli altri sei, e che prima di questa correzione cadevano in
# silenzio (nessun oggetto, nessun errore).
#
# **LA REGOLA (spec, §6, corretta il 26 agosto): un dominio entra QUI
# insieme al suo stato di riposo in `_RESTING` qui sotto, nella STESSA
# modifica. Le due cose non si toccano separatamente.** E' la terza volta in
# questa fetta che lo stesso difetto nasce dal separarle: l'allarme
# rovesciato (punto 3b), l'energia che non chiudeva mai (punto 6), e questi
# quattro domini aggiunti QUI, al giro precedente, senza guardare i LORO
# riposi -- il vacuum che torna alla base (`docked`) e il media_player fermo
# (`idle`, `standby`) restavano oggetti aperti per sempre (`fine_ts: None`).
# Un dominio dimenticato cade in silenzio (nessun oggetto); un dominio
# aggiunto a meta' produce oggetti che non si chiudono mai -- lo stesso
# costo, dai due lati opposti dello stesso elenco.
_OPERABLE = frozenset({"climate", "cover", "switch", "light", "fan",
                         "water_heater", "humidifier", "vacuum", "valve",
                         "media_player"})

# Gli stati che valgono «a riposo»: chiudono un oggetto di funzionamento o di
# sicurezza. Ogni dominio in `_OPERABLE` ha il SUO qui dentro -- e' la
# regola scritta sopra. "off"/"closed" per i sei domini originali, "locked"
# per la serratura, "armed_*" per il pannello dell'allarme (**"disarmed" e
# "triggered" NO** -- correzione al rovesciamento della review, punto 3b: e'
# controintuitivo per chi legge in fretta, ma un allarme si INSERISCE per
# stare a riposo, non il contrario). Per i quattro domini aggiunti al giro
# precedente, verificati sulla documentazione Home Assistant -- non
# sull'elenco scritto a mano di un mandato, che e' precisamente il modo in
# cui questo difetto e' nato due volte:
# - `vacuum`: "docked" (in base, eventualmente in carica), "idle" (fermo,
#   non in carica ne' in errore), "returning" (sta rientrando, non sta piu'
#   pulendo), "error". Solo "cleaning" e' acceso.
# - `media_player`: "idle" (acceso ma non riproduce nulla), "standby"
#   (deprecato verso "off"/"idle" dalla 2026.8, ma ancora prodotto da alcune
#   integrazioni -- questa casa ce l'ha). "on" resta acceso (nessun
#   dettaglio sullo stato: trattato come gli altri domini semplici on/off)
#   e cosi' "buffering" (sta per riprodurre, non e' un riposo).
# - `humidifier`: solo "on"/"off", nessuno stato intermedio -- gia' coperto,
#   nessuna aggiunta.
# - `valve`: "open", "opening", "closing" sono TUTTI attivi, come per
#   "cover" (con cui condivide "closed" come unico riposo) -- una valvola a
#   meta' apertura non e' ferma, e "opening"/"closing" qui chiuderebbe
#   l'oggetto a meta' transizione. Nessuna aggiunta.
#
# **"paused" NON e' qui, ne' per il vacuum ne' per il media_player** (giro
# di pulizia del 26 agosto, punto 3 -- deciso ADESSO, contro il mandato
# precedente che l'aveva messo fra i riposi). Un riposo e' «ha finito»: il
# robot e' tornato alla base, la TV non riproduce piu' nulla. Una pausa e'
# un'attivita' SOSPESA, non finita -- il film torna dove si era fermato, la
# pulizia riprende da dove si era interrotta. Trattarla come un riposo
# spezzava un episodio solo in due: un film in pausa cinque minuti diventava
# due oggetti, una pulizia interrotta e ripresa diventava due pulizie -- e
# la spec (§1) giudica gli oggetti da quanto si leggono, non solo da cosa
# fa il codice. Un apparecchio lasciato in pausa a fine giornata produce
# ora un oggetto ancora APERTO (`fine_ts: None`): e' la verita', non ha
# finito.
#
# Un solo insieme, non due che si sovrappongono: `_RESTING` e' usato da piu'
# rami (funzionamento e sicurezza). Non e' piu' un insieme esclusivo per
# dominio in senso stretto -- "idle" chiude sia il vacuum sia il
# media_player -- ma resta senza ambiguita': ogni valore ha lo stesso
# significato («questo episodio e' finito») in qualunque dominio compaia.
# **"unavailable"/"unknown" NON stanno qui** (vedi `_UNKNOWN` sotto, e la
# correzione del punto 2): non sono un riposo, sono «non lo sappiamo» --
# trattarli come riposo li faceva CHIUDERE un episodio in corso, e il
# ritorno dello stato vero ne apriva un secondo.
_RESTING = frozenset({"off", "closed", "none", "",
                     "locked", "armed_home", "armed_away", "armed_night",
                     "armed_vacation", "armed_custom_bypass",
                     "docked", "returning", "error",
                     "idle", "standby"})

# Stati "non lo so", non stati della casa. Un riavvio di Home Assistant fa
# attraversare questi due stati a OGNI entita'. **Non sono in `_RESTING`**
# (correzione punto 2 del secondo giro di review): la versione precedente li
# metteva li' dentro, e "funzionamento"/"sicurezza" li trattavano come
# riposo -- un riavvio a episodio in corso CHIUDEVA l'oggetto, e il ritorno
# dello stato vero ne APRIVA un secondo. Ogni riavvio spezzava in due un
# riscaldamento acceso, o una casa lasciata disarmata. Il commento che
# viveva qui prima diceva che il funzionamento «li tiene fuori, quindi non
# apre niente»: era vero sul non aprire e taceva che chiudevano -- mezza
# frase vera usata come prova di coerenza.
#
# La semantica giusta e' la TERZA, non «e' finito» ne' «e' cominciato»: una
# riga con questo stato si SALTA, e l'episodio in corso resta aperto
# ATTRAVERSO il buco -- che e' la verita', non sappiamo che sia finito. Il
# salto vive in un punto solo, in cima ad `aggregate_day`, prima di ogni
# ramo e prima delle misure (correzione punto 3: senza il salto in cima,
# un'`unavailable` da riavvio a bordo giornata finiva come prima o ultima
# lettura di un'energia) -- non piu' duplicato con una semantica diversa in
# ogni ramo che lo tocca.
_UNKNOWN = frozenset({"unavailable", "unknown"})


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
    `integrazione:`, un confine netto e facile da spiegare), `"sicurezza"` per
    tutta la gamba omonima. Qui il criterio e' `aspect_ == "sicurezza"`,
    qualunque sia il dominio, cosi' non serve ripetere l'elenco dei domini/
    classi che il pavimento gia' tiene.

    **Eccezione dichiarata (correzione del giro di review, punto 7): un
    `sensor` numerico della gamba sicurezza NON genera un oggetto.** Oggi
    l'unico caso raggiungibile e' il monossido misurato in concentrazione
    (`carbon_monoxide` su `sensor`, non su `binary_sensor`): una lettura come
    "0.4" non e' mai in `_RESTING`, quindi userebbe `_is_on` per aprire un
    oggetto che non chiuderebbe mai -- un guasto perennemente aperto al
    giorno, per ogni sensore CO numerico della casa. Un sensore che MISURA
    non e' un sensore che SCATTA: servirebbe una soglia per decidere quando
    la concentrazione diventa una minaccia, e non ne abbiamo una onesta.
    **Restare fuori e' la decisione**, non una dimenticanza: il
    `binary_sensor` di monossido -- che scatta davvero, con uno stato on/off
    -- resta dentro senza bisogno di nessuna soglia.
    """
    if subject.startswith(("problema:", "integrazione:")):
        return "guasto"
    domain = subject.split(".")[0]
    if domain in _OPERABLE:
        return "funzionamento"
    if domain in ("person", "device_tracker"):
        return "presenza"
    if domain == "sensor" and aspect_ == "energia":
        return "energia"
    if aspect_ == "sicurezza":
        if domain == "sensor":
            return None
        return "sicurezza"
    return None


def _reading_aspect(subject: str, row: dict) -> str | None:
    """La gamba del soggetto, ricostruita dal grezzo.

    Il grezzo non porta il CONTESTO attorno (§3 della spec: temperatura,
    presenza, tutto cio' che cambierebbe il giudizio) ma porta, da questa
    correzione, le tre classi che Home Assistant dichiara sull'entita' --
    `device_class`, `state_class`, `source_type` -- perche' sono grezzo per
    definizione, non un giudizio nostro. **`baseline.aspect()` legge solo
    `device_class` e `source_type`** per decidere la gamba di `sensor` e
    `binary_sensor` (correzione di parole della review, mandato «il
    bilancio dell'energia», punto 7, 27/08/2026: prima di questa
    correzione questo docstring diceva che le leggeva tutte e tre --
    `state_class` NON e' fra i criteri, dalla correzione del 27/08 sul
    traffico di rete, vedi il docstring di `gamba`). Resta comunque nel
    grezzo, non e' tolta dallo schema: e' `baseline.aspect()` che non la
    legge, non `store.py` che smette di conservarla -- i 22 giorni di
    grezzo permettono di rifare il giudizio anche se un domani tornasse a
    servire.

    **Non si salva la gamba gia' calcolata.** Sarebbe piu' comodo, ed e' la
    scelta sbagliata: la gamba e' un giudizio, e il giudizio sta tutto qui,
    nell'aggregazione, precisamente perche' i 22 giorni di grezzo permettano
    di rifarlo. Congelarlo in scrittura toglierebbe quella possibilita' il
    giorno in cui il pavimento cambiasse.
    """
    if subject.startswith(("problema:", "integrazione:")):
        return None
    return aspect(subject, {
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
    return str(value or "").strip().lower() not in _RESTING


def _difference(initial, final) -> float | None:
    """`finale - iniziale`, o `None` se uno dei due non si legge come numero.

    Un contatore scrive stringhe (`"1234.5"`). `None` e non zero quando la
    lettura fallisce: zero direbbe «variazione nulla» per un valore che non
    si e' nemmeno potuto interpretare, e sarebbe un fatto falso travestito
    da dato. **La parola resta neutra apposta** (correzione del 26/08/2026,
    gamba "consumo" -> "energia"): questa differenza serve anche ai
    contatori di energia PRODOTTA, e "consumo" per una lettura di
    produzione sarebbe di nuovo la frase falsa che questa correzione toglie.

    **Arrotondata a 2 decimali** (mandato «il bilancio dell'energia»,
    27/08/2026, punto 6 -- misurato: la pagina mostra oggi `+0.
    010000000000000009`). Il valore sbagliato e' gia' nel dato -- la
    sottrazione fra due `float` letti da stringhe HA porta rumore di
    virgola mobile ben sotto il centesimo -- quindi si arrotonda QUI, dove
    il numero nasce, non nella pagina che lo mostra. 2 decimali (0,01):
    la gamba energia copre kWh, m^3 e litri con la stessa funzione, e i
    contatori di questa casa non scrivono mai piu' di due cifre dopo la
    virgola (misurato: `0.27`, `3.11`, `23.8`...).
    """
    try:
        return round(float(final) - float(initial), 2)
    except (TypeError, ValueError):
        return None


# ── Il bilancio: undici frammenti diventano un oggetto solo ────────────────
#
# E' IL GENERE che decide la forma (spec §3): l'episodio -- protagonista,
# inizio, fine -- e' lo stampo giusto per «riscaldamento acceso 15:30 ->
# 17:05», sbagliato per «com'e' andata l'energia della casa ieri», che e'
# una QUANTITA' CON UNA FORMA, un giorno intero, non un apri/chiudi. E OGNI
# GENERE PORTA CON SE' LA SUA FONTE (spec §4): qui non e' il grezzo -- e'
# `HAClient.hourly_statistics()`, che HA gia' tiene, corretta per gli
# azzeramenti dei contatori, e conservata piu' a lungo dei nostri 22 giorni.
#
# Le funzioni qui sotto sono PURE (nessuna lettura di rete, nessun accesso
# all'archivio): prendono le statistiche GIA' lette e tradotte
# (`HAClient._request_statistics`, chiavi italiane) e i collegamenti
# dispositivo/direzione GIA' risolti, e tornano il corpo di un bilancio.
# Chi legge la rete e chi risolve il dispositivo e' `server.py::
# costruisci_bilanci` -- stessa separazione di `companions`/`directions`
# sopra: la rete sta fuori, il giudizio sta qui, dove i 21 giorni di grezzo
# (o, per il bilancio, le settimane di statistiche che HA conserva)
# permettono di rifarlo.

def _kwh(value) -> float | None:
    """Un numero della gamba energia -> kWh arrotondati a 2 decimali.

    2 decimali (0,01 kWh = 10 Wh, mandato punto 6): i contatori di questa
    casa non scrivono mai piu' di due cifre dopo la virgola (misurato:
    `0.27`, `3.11`, `23.8`...) -- un terzo decimale sarebbe precisione che
    lo strumento non ha, e il difetto misurato in pagina (`+0.
    010000000000000009`) e' rumore di virgola mobile ben sotto quella
    soglia. `None` -- non zero -- quando il valore manca o non e' un
    numero: e' la stessa distinzione di `_difference` sopra.
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


def _share(numerator, denominator) -> float | None:
    """Un rapporto -> frazione fra 0 e 1, arrotondata a 3 decimali.

    3 decimali (0,712): un RAPPORTO merita piu' cifre di un kWh -- 71,2% e
    71,3% sono un fatto leggibile, non rumore. `None` se il denominatore
    manca o e' zero: zero produzione non significa «zero autoconsumo», e'
    «non lo so» (mandato, «cosa NON si salva» -- mai uno zero al posto di un
    dato che non si puo' calcolare).

    **Mai negativa** (correzione ALTO della review, mandato «il bilancio
    dell'energia», punto 3, 27/08/2026): il nome e il docstring
    promettevano gia' «fra 0 e 1», ma nessun codice lo garantiva. Il caso
    misurato e' `self_sufficiency_share` (`_balance_moments` sotto),
    calcolata come `(consumo - prelievo) / consumo`: il prelievo PUO'
    superare il consumo di casa quando la batteria si carica dalla rete --
    quell'energia importata va a caricare, non e' consumo della casa, e la
    sottrazione va sotto zero. Oggi su questa casa il prelievo e' minimo e
    il caso non si vede; d'inverno, o con una tariffa che carica di notte,
    si'.

    **Non si CLAMPA a zero**: zero affermerebbe «zero autosufficienza», e
    non lo sappiamo -- l'eccedenza del prelievo (andata a caricare) puo'
    convivere con un'ottima autoproduzione nel resto della giornata, che
    quei due numeri soli non dicono. Quando il rapporto uscirebbe negativo,
    si torna `None`: «non lo so», non un numero inventato su nessuno dei
    due lati -- ne' quello sbagliato di prima ne' un floor che affermerebbe
    il contrario.
    """
    if not denominator:
        return None
    try:
        value = float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if value < 0:
        return None
    return round(value, 3)


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
                      totals: dict[str, dict]) -> dict:
    """I momenti derivati dalla forma e dai totali -- vedi
    `build_balance_body` per il contratto completo. Separata per
    restare leggibile: ogni momento e' un piccolo giudizio a se'.
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

    autoconsumo_share = _share(totals.get("autoconsumo", {}).get("valore"),
                               totals.get("produzione", {}).get("valore"))
    if autoconsumo_share is not None:
        moments["quota_autoconsumo"] = autoconsumo_share

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
    consumo = totals.get("consumo", {}).get("valore")
    prelievo = totals.get("prelievo", {}).get("valore")
    if consumo is not None and prelievo is not None:
        self_sufficiency_share = _share(consumo - prelievo, consumo)
        if self_sufficiency_share is not None:
            moments["quota_autosufficienza"] = self_sufficiency_share

    return moments


def build_balance_body(*, series: dict[str, list[dict]],
                              entity_per_dimension: dict[str, str],
                              provenance_per_dimension: dict[str, str],
                              battery_entity: str | None = None) -> dict:
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
    conosciute tolgono la dimensione per intero -- e' la stessa regola gia'
    presa da `_difference` per una sola lettura nel giorno.

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

    for dimension in BALANCE_DIRECTIONS:
        points = _dimension_points(series, entity_per_dimension.get(dimension))
        known = [p["valore"] for p in points if p["valore"] is not None]
        if not known:
            continue
        points_per_dimension[dimension] = points
        form[dimension] = [{"ora": p["inizio"], "valore": p["valore"]} for p in points]
        totals[dimension] = {"valore": round(sum(known), 2),
                              "provenienza": provenance_per_dimension.get(dimension)}

    body: dict = {}
    if totals:
        body["totali"] = totals
    if form:
        body["forma"] = form
    moments = _balance_moments(points_per_dimension, totals)
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
    (mandato «le direzioni dell'energia» -- vedi `baseline.py::_ENERGIA`
    per la storia): il riepilogo qui sotto era lo STESSO per un contatore
    che PRODUCE e uno che PRELEVA, entrambi `device_class: energy`/`power`.
    La GAMBA resta "energia" (non si sdoppia: e' vera per tutti e 17 i
    sensori dell'inverter, produzione compresa -- `baseline.py`), ma il
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
    # ramo e prima delle misure (`_UNKNOWN`, correzione dei punti 2 e 3 del
    # secondo giro di review): un riavvio di Home Assistant li fa
    # attraversare a OGNI entita'. Filtrarli a valle -- come prima, con
    # `_RESTING` per funzionamento/sicurezza e un `if` locale per presenza --
    # li faceva significare due cose diverse nello stesso modulo: riposo in
    # un ramo (chiude un episodio in corso), salto nell'altro. La riga che
    # si perde qui e' un buco nell'informazione, non un fatto sulla casa:
    # non deve ne' aprire ne' chiudere niente, in NESSUN ramo, e non deve
    # contaminare il riepilogo di un'energia (`misure`, sotto) con
    # "unavailable" come prima o ultima lettura del giorno.
    rows = [r for r in rows
             if str(r["a"] or "").strip().lower() not in _UNKNOWN]

    # Prima passata: le misure, per soggetto. Servono come contesto e non
    # generano oggetti da sole.
    measurements: dict[str, list[tuple[float, str]]] = {}
    for r in rows:
        measurements.setdefault(r["soggetto"], []).append((r["quando_ts"], r["a"]))

    open_episodes: dict[str, dict] = {}
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
        episodes.append({"genere": o["genere"], "protagonista": subject,
                        "inizio": o["inizio"], "fine": when,
                        "corpo_base": {"stato": o["stato"]}})

    for r in rows:
        subject = r["soggetto"]
        genre = genre_for(subject, _reading_aspect(subject, r))
        if genre is None:
            continue
        if genre == "guasto":
            # Solo condizioni di sistema arrivano qui (vedi `genre_for`):
            # convenzione di `osservatore.watch_system` -- "aperto" nasce,
            # "chiuso" e nient'altro finisce.
            if r["a"] == "aperto":
                open_episodes[subject] = {"genere": genre, "inizio": r["quando_ts"],
                                    "stato": "aperto"}
            else:
                close(subject, r["quando_ts"])
            continue
        if genre == "sicurezza":
            # Sesta gamba, entita' vera: stessa logica acceso/spento del
            # funzionamento -- il genere e' diverso, la forma no.
            if _is_on(r["a"]):
                if subject not in open_episodes:
                    open_episodes[subject] = {"genere": genre, "inizio": r["quando_ts"],
                                        "stato": r["a"]}
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
                                    "stato": r["a"]}
            continue
        if genre == "funzionamento":
            if _is_on(r["a"]):
                if subject not in open_episodes:
                    open_episodes[subject] = {"genere": genre, "inizio": r["quando_ts"],
                                        "stato": r["a"]}
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
        initial, final = points[0][1], points[-1][1]
        # Una sola lettura nel giorno non dice quanto e' cambiato: e'
        # "non lo sappiamo" -- la stessa distinzione del punto 2, e il
        # codice la fa gia' altrove restituendo `None` quando `_difference`
        # non riesce a leggere un valore come numero (pulizia del secondo
        # giro di review). Con un solo punto, iniziale e finale sono la
        # STESSA riga: il conto tornerebbe 0.0, il fatto falso "non e'
        # cambiato niente" travestito da dato. **La parola resta neutra**
        # (26/08/2026): "consumato" sarebbe falso per la meta' dei sensori
        # di un impianto fotovoltaico con accumulo, che PRODUCONO.
        difference = _difference(initial, final) if len(points) > 1 else None
        episodes.append({"genere": "energia", "protagonista": subject,
                        "inizio": points[0][0], "fine": points[-1][0],
                        "corpo_base": {"valore_iniziale": initial,
                                       "valore_finale": final,
                                       "differenza": difference}})

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
