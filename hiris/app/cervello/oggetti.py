"""L'aggregazione: dai cambi grezzi agli oggetti.

**Un oggetto e' una cosa compiuta della casa**: qualcosa che e' cominciato, e'
durato, e' finito -- con dentro chi lo ha fatto e cosa c'era attorno mentre
durava.

    Riscaldamento camera: acceso 15:30 -> 17:05. Temperatura da 18,2 a 21,0.

**E' l'unico posto di questa fetta dove si giudica**, ed e' voluto: un giudizio
qui si rifa' finche' il grezzo esiste (22 giorni: 21 di promessa, uno di
guardia -- vedi `archivio.CONSERVAZIONE_CAMBI_S`), uno preso in scrittura non
si corregge piu'.

**L'obiettivo sceglie QUALI entita', la natura decide CHE TIPO di oggetto ne
esce.** La prima non e' una lista scritta a mano: il pavimento (`pavimento.
gamba`) deriva QUALI entita' da cio' che Home Assistant dichiara gia' --
dominio, `device_class`, `source_type` (**non `state_class`**: correzione
di parole della review, mandato «il bilancio dell'energia», punto 7,
27/08/2026 -- dopo la correzione del 27/08, `pavimento.gamba` non lo legge
piu' per decidere nessuna gamba, vedi il suo docstring). **La seconda, invece, SI'**
(correzione del giro di review, punto 9): `_FUNZIONANO` qui sotto e' una
lista scritta a mano dei domini che si accendono e si spengono. Non c'e' modo
di derivarla: Home Assistant non dichiara da nessuna parte «questo dominio
funziona come un interruttore», quindi va mantenuta a mano e tenuta
aggiornata quando un dominio nuovo lo fa -- la vecchia frase di questo
docstring affermava il contrario, ed era falsa quanto una funzione sbagliata.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..casa.tempo import zona_casa
from .pavimento import gamba

# `aggrega_giorno` e' SINCRONA: non fa nessuna lettura di rete. I comprimari
# arrivano gia' risolti dal chiamante (vedi il Task 6), proprio perche' una
# chiamata a `legami` dentro il ciclo farebbe migliaia di richieste per una
# giornata. Renderla `async` "per il futuro" sarebbe generalita' speculativa.
# **Vale identico per `bilanci`** (mandato «il bilancio dell'energia»,
# 27/08/2026): arriva gia' costruito dal chiamante (`server.py::
# costruisci_bilanci`), che ha gia' letto `HAClient.statistiche_orarie()` --
# una lettura di rete per giro, non per giorno ne' per dispositivo.

GENERI = ("funzionamento", "presenza", "energia", "guasto", "sicurezza", "bilancio")

# Le SETTE dimensioni che il bilancio riporta. **Il consumo e' la settima**
# (correzione ALTO della review, mandato «il bilancio dell'energia», punto
# 1, 27/08/2026): prima di questa correzione erano sei, e "consumo" era
# dichiaratamente escluso come "RIDONDANTE con autoconsumo+prelievo" -- una
# frase che era un'ASSUNZIONE, non un fatto misurato, e su questa casa e'
# FALSA. `_momenti_bilancio` sotto usava quell'identita' per calcolare
# `quota_autosufficienza` come `autoconsumo/(autoconsumo+prelievo)`: su
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
# (vedi `_momenti_bilancio`). Dove il sensore del consumo non esiste, la
# quota non si scrive -- campo assente, mai un numero inventato.
DIREZIONI_BILANCIO = ("produzione", "autoconsumo", "immissione",
                      "prelievo", "carica", "scarica", "consumo")

# I domini che «funzionano»: si accendono e si spengono, si aprono e si
# chiudono. Sono i protagonisti degli oggetti di funzionamento. **Lista
# scritta a mano, dichiaratamente** (vedi il docstring del modulo): mancavano
# `humidifier`, `vacuum`, `valve` e `media_player` -- domini comuni che
# funzionano come gli altri sei, e che prima di questa correzione cadevano in
# silenzio (nessun oggetto, nessun errore).
#
# **LA REGOLA (spec, §6, corretta il 26 agosto): un dominio entra QUI
# insieme al suo stato di riposo in `_SPENTO` qui sotto, nella STESSA
# modifica. Le due cose non si toccano separatamente.** E' la terza volta in
# questa fetta che lo stesso difetto nasce dal separarle: l'allarme
# rovesciato (punto 3b), l'energia che non chiudeva mai (punto 6), e questi
# quattro domini aggiunti QUI, al giro precedente, senza guardare i LORO
# riposi -- il vacuum che torna alla base (`docked`) e il media_player fermo
# (`idle`, `standby`) restavano oggetti aperti per sempre (`fine_ts: None`).
# Un dominio dimenticato cade in silenzio (nessun oggetto); un dominio
# aggiunto a meta' produce oggetti che non si chiudono mai -- lo stesso
# costo, dai due lati opposti dello stesso elenco.
_FUNZIONANO = frozenset({"climate", "cover", "switch", "light", "fan",
                         "water_heater", "humidifier", "vacuum", "valve",
                         "media_player"})

# Gli stati che valgono «a riposo»: chiudono un oggetto di funzionamento o di
# sicurezza. Ogni dominio in `_FUNZIONANO` ha il SUO qui dentro -- e' la
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
# Un solo insieme, non due che si sovrappongono: `_SPENTO` e' usato da piu'
# rami (funzionamento e sicurezza). Non e' piu' un insieme esclusivo per
# dominio in senso stretto -- "idle" chiude sia il vacuum sia il
# media_player -- ma resta senza ambiguita': ogni valore ha lo stesso
# significato («questo episodio e' finito») in qualunque dominio compaia.
# **"unavailable"/"unknown" NON stanno qui** (vedi `_IGNOTO` sotto, e la
# correzione del punto 2): non sono un riposo, sono «non lo sappiamo» --
# trattarli come riposo li faceva CHIUDERE un episodio in corso, e il
# ritorno dello stato vero ne apriva un secondo.
_SPENTO = frozenset({"off", "closed", "none", "",
                     "locked", "armed_home", "armed_away", "armed_night",
                     "armed_vacation", "armed_custom_bypass",
                     "docked", "returning", "error",
                     "idle", "standby"})

# Stati "non lo so", non stati della casa. Un riavvio di Home Assistant fa
# attraversare questi due stati a OGNI entita'. **Non sono in `_SPENTO`**
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
# salto vive in un punto solo, in cima ad `aggrega_giorno`, prima di ogni
# ramo e prima delle misure (correzione punto 3: senza il salto in cima,
# un'`unavailable` da riavvio a bordo giornata finiva come prima o ultima
# lettura di un'energia) -- non piu' duplicato con una semantica diversa in
# ogni ramo che lo tocca.
_IGNOTO = frozenset({"unavailable", "unknown"})


def genere_di(soggetto: str, gamba_: str | None) -> str | None:
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
    tutta la gamba omonima. Qui il criterio e' `gamba_ == "sicurezza"`,
    qualunque sia il dominio, cosi' non serve ripetere l'elenco dei domini/
    classi che il pavimento gia' tiene.

    **Eccezione dichiarata (correzione del giro di review, punto 7): un
    `sensor` numerico della gamba sicurezza NON genera un oggetto.** Oggi
    l'unico caso raggiungibile e' il monossido misurato in concentrazione
    (`carbon_monoxide` su `sensor`, non su `binary_sensor`): una lettura come
    "0.4" non e' mai in `_SPENTO`, quindi userebbe `_acceso` per aprire un
    oggetto che non chiuderebbe mai -- un guasto perennemente aperto al
    giorno, per ogni sensore CO numerico della casa. Un sensore che MISURA
    non e' un sensore che SCATTA: servirebbe una soglia per decidere quando
    la concentrazione diventa una minaccia, e non ne abbiamo una onesta.
    **Restare fuori e' la decisione**, non una dimenticanza: il
    `binary_sensor` di monossido -- che scatta davvero, con uno stato on/off
    -- resta dentro senza bisogno di nessuna soglia.
    """
    if soggetto.startswith(("problema:", "integrazione:")):
        return "guasto"
    dominio = soggetto.split(".")[0]
    if dominio in _FUNZIONANO:
        return "funzionamento"
    if dominio in ("person", "device_tracker"):
        return "presenza"
    if dominio == "sensor" and gamba_ == "energia":
        return "energia"
    if gamba_ == "sicurezza":
        if dominio == "sensor":
            return None
        return "sicurezza"
    return None


def _gamba_del_cambio(soggetto: str, riga: dict) -> str | None:
    """La gamba del soggetto, ricostruita dal grezzo.

    Il grezzo non porta il CONTESTO attorno (§3 della spec: temperatura,
    presenza, tutto cio' che cambierebbe il giudizio) ma porta, da questa
    correzione, le tre classi che Home Assistant dichiara sull'entita' --
    `device_class`, `state_class`, `source_type` -- perche' sono grezzo per
    definizione, non un giudizio nostro. **`pavimento.gamba()` legge solo
    `device_class` e `source_type`** per decidere la gamba di `sensor` e
    `binary_sensor` (correzione di parole della review, mandato «il
    bilancio dell'energia», punto 7, 27/08/2026: prima di questa
    correzione questo docstring diceva che le leggeva tutte e tre --
    `state_class` NON e' fra i criteri, dalla correzione del 27/08 sul
    traffico di rete, vedi il docstring di `gamba`). Resta comunque nel
    grezzo, non e' tolta dallo schema: e' `pavimento.gamba()` che non la
    legge, non `archivio.py` che smette di conservarla -- i 22 giorni di
    grezzo permettono di rifare il giudizio anche se un domani tornasse a
    servire.

    **Non si salva la gamba gia' calcolata.** Sarebbe piu' comodo, ed e' la
    scelta sbagliata: la gamba e' un giudizio, e il giudizio sta tutto qui,
    nell'aggregazione, precisamente perche' i 22 giorni di grezzo permettano
    di rifarlo. Congelarlo in scrittura toglierebbe quella possibilita' il
    giorno in cui il pavimento cambiasse.
    """
    if soggetto.startswith(("problema:", "integrazione:")):
        return None
    return gamba(soggetto, {
        "device_class": riga.get("device_class"),
        "state_class": riga.get("state_class"),
        "source_type": riga.get("source_type"),
    })


def confini_giorno(giorno: str, fuso: str | None) -> tuple[float, float]:
    """L'inizio e la fine di un giorno **nel fuso della casa**.

    Le 23:30 di Roma sono le 21:30 UTC: un giorno calcolato in UTC spezzerebbe
    ogni serata in due, e la fetta dello schedulatore ha gia' pagato un difetto
    di orologi diversi.

    **La finestra di `archivio.cambi` e' semi-aperta (`[da_ts, a_ts)`)**, e
    questi confini ci contano sopra cosi' come sono: un `-1` o un `-0.001` "per
    stare sicuri" riaprirebbe un buco di un secondo a ogni mezzanotte, e con
    due confini inclusivi un cambio esattamente a mezzanotte finirebbe contato
    in due giorni.

    **Pubblica (correzione del giro di review, punto 4).** Prima era `_confini`
    e importava `_zona`, un'altra privata, da `casa/tempo.py`: due nomi con
    underscore attraversati da fuori dal solo import. Il calcolo e' uno solo
    (nessun doppione nel prodotto); tenerlo privato avrebbe solo obbligato chi
    ne ha bisogno a importare comunque il nome privato, o a riscrivere il
    calcolo -- che e' esattamente come nascono i doppioni.
    """
    zona = zona_casa(fuso)
    inizio = datetime.fromisoformat(giorno).replace(tzinfo=zona)
    return inizio.timestamp(), (inizio + timedelta(days=1)).timestamp()


def _acceso(valore) -> bool:
    return str(valore or "").strip().lower() not in _SPENTO


def _differenza(iniziale, finale) -> float | None:
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
        return round(float(finale) - float(iniziale), 2)
    except (TypeError, ValueError):
        return None


# ── Il bilancio: undici frammenti diventano un oggetto solo ────────────────
#
# E' IL GENERE che decide la forma (spec §3): l'episodio -- protagonista,
# inizio, fine -- e' lo stampo giusto per «riscaldamento acceso 15:30 ->
# 17:05», sbagliato per «com'e' andata l'energia della casa ieri», che e'
# una QUANTITA' CON UNA FORMA, un giorno intero, non un apri/chiudi. E OGNI
# GENERE PORTA CON SE' LA SUA FONTE (spec §4): qui non e' il grezzo -- e'
# `HAClient.statistiche_orarie()`, che HA gia' tiene, corretta per gli
# azzeramenti dei contatori, e conservata piu' a lungo dei nostri 22 giorni.
#
# Le funzioni qui sotto sono PURE (nessuna lettura di rete, nessun accesso
# all'archivio): prendono le statistiche GIA' lette e tradotte
# (`HAClient._richiedi_statistiche`, chiavi italiane) e i collegamenti
# dispositivo/direzione GIA' risolti, e tornano il corpo di un bilancio.
# Chi legge la rete e chi risolve il dispositivo e' `server.py::
# costruisci_bilanci` -- stessa separazione di `comprimari`/`direzioni`
# sopra: la rete sta fuori, il giudizio sta qui, dove i 21 giorni di grezzo
# (o, per il bilancio, le settimane di statistiche che HA conserva)
# permettono di rifarlo.

def _kwh(valore) -> float | None:
    """Un numero della gamba energia -> kWh arrotondati a 2 decimali.

    2 decimali (0,01 kWh = 10 Wh, mandato punto 6): i contatori di questa
    casa non scrivono mai piu' di due cifre dopo la virgola (misurato:
    `0.27`, `3.11`, `23.8`...) -- un terzo decimale sarebbe precisione che
    lo strumento non ha, e il difetto misurato in pagina (`+0.
    010000000000000009`) e' rumore di virgola mobile ben sotto quella
    soglia. `None` -- non zero -- quando il valore manca o non e' un
    numero: e' la stessa distinzione di `_differenza` sopra.
    """
    if valore is None:
        return None
    try:
        return round(float(valore), 2)
    except (TypeError, ValueError):
        return None


def _percento(valore) -> float | None:
    """Una percentuale di batteria -> arrotondata a 1 decimale.

    1 decimale (56,6%): lo stato istantaneo della batteria e' un intero
    (misurato: `"12"`, `"96"`...), ma la MEDIA oraria che il bilancio legge
    (`media`, statistiche di tipo `measurement`) e' un numero continuo -- un
    decimale distingue due ore vicine senza inventare una precisione che lo
    strumento non ha.
    """
    if valore is None:
        return None
    try:
        return round(float(valore), 1)
    except (TypeError, ValueError):
        return None


def _quota(numeratore, denominatore) -> float | None:
    """Un rapporto -> frazione fra 0 e 1, arrotondata a 3 decimali.

    3 decimali (0,712): un RAPPORTO merita piu' cifre di un kWh -- 71,2% e
    71,3% sono un fatto leggibile, non rumore. `None` se il denominatore
    manca o e' zero: zero produzione non significa «zero autoconsumo», e'
    «non lo so» (mandato, «cosa NON si salva» -- mai uno zero al posto di un
    dato che non si puo' calcolare).
    """
    if not denominatore:
        return None
    try:
        return round(float(numeratore) / float(denominatore), 3)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _punti_dimensione(serie: dict[str, list[dict]], soggetto: str | None) -> list[dict]:
    """I punti orari di un'entita', ridotti a `{"inizio","fine","valore"}` --
    `valore` e' il `cambio` di quell'ora (il delta GIA' calcolato da HA,
    corretto per gli azzeramenti: vedi `HAClient._richiedi_statistiche`),
    arrotondato in kWh. Un'ora senza `cambio` (dato mancante per QUELL'ora,
    non per l'intero `statistic_id`) resta `valore: None` -- mai uno zero
    inventato -- ma non toglie le altre ore dalla lista.
    """
    if soggetto is None:
        return []
    punti = serie.get(soggetto) or []
    return [{"inizio": p.get("inizio"), "fine": p.get("fine"),
             "valore": _kwh(p.get("cambio")) if isinstance(p, dict) else None}
            for p in punti if isinstance(p, dict)]


def _momenti_bilancio(punti_per_dimensione: dict[str, list[dict]],
                      totali: dict[str, dict]) -> dict:
    """I momenti derivati dalla forma e dai totali -- vedi
    `costruisci_corpo_bilancio` per il contratto completo. Separata per
    restare leggibile: ogni momento e' un piccolo giudizio a se'.
    """
    momenti: dict = {}

    attive_produzione = [p for p in punti_per_dimensione.get("produzione", [])
                         if (p["valore"] or 0) > 0]
    if attive_produzione:
        momenti["prima_ora_produzione"] = attive_produzione[0]["inizio"]
        momenti["ultima_ora_produzione"] = attive_produzione[-1]["inizio"]
        picco = max(attive_produzione, key=lambda p: p["valore"])
        momenti["picco_produzione"] = {"valore": picco["valore"], "ora": picco["inizio"]}

    attive_scarica = [p for p in punti_per_dimensione.get("scarica", [])
                      if (p["valore"] or 0) > 0]
    if attive_scarica:
        momenti["fine_scarica_batteria"] = attive_scarica[-1]["fine"]

    quota_autoconsumo = _quota(totali.get("autoconsumo", {}).get("valore"),
                               totali.get("produzione", {}).get("valore"))
    if quota_autoconsumo is not None:
        momenti["quota_autoconsumo"] = quota_autoconsumo

    # **Correzione ALTO della review (mandato «il bilancio dell'energia»,
    # punto 1, 27/08/2026): NON PIU' `autoconsumo/(autoconsumo+prelievo)`.**
    # Quella formula ASSUMEVA che il consumo della casa fosse la somma di
    # autoconsumo e prelievo -- un'identita' falsa su questa integrazione
    # (vedi il commento sopra `DIREZIONI_BILANCIO`: «autoconsumata» esclude
    # la batteria, quindi la somma perde la scarica, oltre meta' del
    # consumo vero). La correzione non aggiunge la scarica alla somma --
    # sarebbe di nuovo DEDURRE un'identita' specifica di questa
    # integrazione. Si legge il consumo MISURATO (il settimo totale, vedi
    # sopra) e si calcola quanta parte NON viene dalla rete:
    # `(consumo - prelievo) / consumo`. Misurato il 26/08/2026: consumo
    # 14,72, prelievo 0,22 -> 0,985 (il numero vero; la vecchia formula
    # diceva 0,964). Senza il consumo misurato, niente quota: mai un
    # numero dedotto al posto di uno letto.
    consumo = totali.get("consumo", {}).get("valore")
    prelievo = totali.get("prelievo", {}).get("valore")
    if consumo is not None and prelievo is not None:
        quota_autosufficienza = _quota(consumo - prelievo, consumo)
        if quota_autosufficienza is not None:
            momenti["quota_autosufficienza"] = quota_autosufficienza

    return momenti


def costruisci_corpo_bilancio(*, serie: dict[str, list[dict]],
                              entita_per_dimensione: dict[str, str],
                              provenienza_per_dimensione: dict[str, str],
                              entita_batteria: str | None = None) -> dict:
    """Il corpo di un bilancio, dalle statistiche orarie GIA' lette e tradotte.

    **Pura**: nessuna lettura di rete. `serie` arriva gia' risolta dal
    chiamante (`HAClient.statistiche_orarie()`, chiavi italiane) -- stessa
    disciplina di `comprimari`/`direzioni` in `aggrega_giorno`.

    `entita_per_dimensione`: `{"produzione": "sensor.x", ...}`, quale
    entita' del dispositivo rappresenta quale delle `DIREZIONI_BILANCIO`
    -- scelta dal chiamante (`server.py::costruisci_bilanci`) fra le entita'
    del dispositivo che hanno quella direzione **e** la classe energia
    dichiarata (non potenza: il bilancio riporta kWh del giorno, non W
    istantanei). Una dimensione assente da questo dizionario significa
    «nessuna entita' di questo dispositivo ha quella direzione» -- il
    totale, la forma e i momenti che ne dipendono non compaiono: **mai uno
    zero al posto di "non lo so"** (mandato, «cosa NON si salva»).

    Il totale di una dimensione e' la somma delle ore CONOSCIUTE (quelle con
    `cambio` non nullo): un'ora mancante non azzera il totale, ma zero ore
    conosciute tolgono la dimensione per intero -- e' la stessa regola gia'
    presa da `_differenza` per una sola lettura nel giorno.

    Ritorna `{"totali": {dimensione: {"valore","provenienza"}}, "forma":
    {dimensione: [{"ora","valore"}, ...]}, "momenti": {...},
    ["batteria_percentuale_oraria": [24 % o None]]}` -- ogni chiave presente
    solo se c'e' almeno un fatto da dirla (dizionario vuoto altrimenti, mai
    una chiave con un valore fittizio).

    **`forma[dimensione]` porta l'ORA di ogni punto, non solo il valore**
    (correzione MEDIA della review, mandato «il bilancio dell'energia»,
    punto 2, 27/08/2026): prima di questa correzione era una lista NUDA di
    valori (`[1.0, 2.0, ...]`), e Home Assistant OMETTE le ore senza dati --
    quindi l'indice non era l'ora, e una giornata che comincia alle 7 aveva
    il primo valore in posizione zero. L'oggetto salvato, da solo, non
    sapeva piu' dire «alle 13», che e' l'unica ragione per cui la forma
    esiste (spec §1, §3). **La chiave nuova e' `ora`** (lo stesso nome gia'
    usato da `picco_produzione` in `_momenti_bilancio` -- fondamenta 3,
    consistenza), un ISO-8601 con fuso preso da `inizio` dello stesso punto
    -- l'istante GIA' letto e tradotto da `HAClient.statistiche_orarie()`,
    non ricalcolato. Non porta anche `fine`: la grana e' fissa a un'ora
    (`period="hour"`, l'unico chiamante), la durata e' sempre la stessa, e
    raddoppiare il payload per dirla a ogni punto non permetterebbe nessuna
    frase in piu' (spec §1, «se un dato non serve a nessuna frase in piu',
    non va salvato»).
    """
    totali: dict[str, dict] = {}
    forma: dict[str, list] = {}
    punti_per_dimensione: dict[str, list[dict]] = {}

    for dimensione in DIREZIONI_BILANCIO:
        punti = _punti_dimensione(serie, entita_per_dimensione.get(dimensione))
        conosciuti = [p["valore"] for p in punti if p["valore"] is not None]
        if not conosciuti:
            continue
        punti_per_dimensione[dimensione] = punti
        forma[dimensione] = [{"ora": p["inizio"], "valore": p["valore"]} for p in punti]
        totali[dimensione] = {"valore": round(sum(conosciuti), 2),
                              "provenienza": provenienza_per_dimensione.get(dimensione)}

    corpo: dict = {}
    if totali:
        corpo["totali"] = totali
    if forma:
        corpo["forma"] = forma
    momenti = _momenti_bilancio(punti_per_dimensione, totali)
    if momenti:
        corpo["momenti"] = momenti

    if entita_batteria is not None:
        punti_batteria = serie.get(entita_batteria) or []
        valori_batteria = [_percento((p or {}).get("media")) for p in punti_batteria]
        if any(v is not None for v in valori_batteria):
            corpo["batteria_percentuale_oraria"] = valori_batteria

    return corpo


def aggrega_giorno(*, archivio, giorno: str, fuso: str | None,
                         comprimari=None, direzioni=None, bilanci=None) -> int:
    """Costruisce gli oggetti di un giorno. Torna quanti ne ha scritti.

    **Idempotente**: rifare un giorno lo SOSTITUISCE, non lo accoda. Gli
    oggetti si accumulano in una lista e si consegnano tutti insieme, in una
    volta sola, ad `archivio.sostituisci_giorno` -- cancellare e poi inserire
    uno per uno, con un commit per ciascuno, lascerebbe un giorno mezzo
    scritto indistinguibile da uno completo se qualcosa muore a meta'. E'
    esattamente il difetto gemello che il vecchio «costruire» ha gia' pagato
    (accodava invece di sostituire, e le ancore YAML lo nascondevano).

    `comprimari(soggetto) -> list[str]` dice quali altre cose stanno con il
    protagonista. E' iniettabile perche' nella vita vera lo chiede a `legami`
    (una chiamata di rete) e nei test no. **Non si indovina dal nome**: e' il
    caso misurato del lampadario, dove tre lampade, il loro gruppo e
    l'interruttore fisico sono un sistema solo.

    `direzioni(soggetto) -> dict | None` dice la direzione di un contatore di
    energia -- `{"direzione": ..., "provenienza": "dichiarata" | "dedotta"}`,
    o `None` se non si conosce. **Stessa forma di `comprimari`, stessa
    ragione**: nella vita vera lo chiede a `HAClient.direzioni_energia()`
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
    (mandato «le direzioni dell'energia» -- vedi `pavimento.py::_ENERGIA`
    per la storia): il riepilogo qui sotto era lo STESSO per un contatore
    che PRODUCE e uno che PRELEVA, entrambi `device_class: energy`/`power`.
    La GAMBA resta "energia" (non si sdoppia: e' vera per tutti e 17 i
    sensori dell'inverter, produzione compresa -- `pavimento.py`), ma il
    CORPO di un episodio di energia ora porta `direzione`/`provenienza`
    quando `direzioni()`, sopra, le sa dire -- lette da `energy/get_prefs`
    (la dashboard Energia, dichiarata) e da `translation_key` (dedotta
    dall'integrazione, dove la dichiarata tace). Non e' un debito chiuso
    del tutto: la dichiarata copre 6 delle 17 entita' di questa casa, la
    dedotta le copre tutte ma solo su questa integrazione (`zcsazzurro`) --
    un episodio senza `direzione` resta possibile, ed e' un fatto onesto
    («non lo sappiamo»), non un buco silenzioso.

    `bilanci: list[dict] | None` -- **terzo debito, CHIUSO il 27/08/2026**
    (mandato «il bilancio dell'energia»): undici frammenti di energia dello
    stesso dispositivo diventano UN oggetto, di genere `"bilancio"`. Ogni
    elemento e' `{"dispositivo_id", "nome", "entita": [...], "corpo": {...}}`
    -- gia' costruito dal chiamante (`server.py::costruisci_bilanci`, che
    legge `HAClient.statistiche_orarie()`: **il bilancio non dipende dal
    grezzo**, viene dalle statistiche di HA, che sono piu' corrette
    (gestiscono gli azzeramenti) e piu' durature dei nostri 22 giorni). E'
    lo STESSO principio di `comprimari`/`direzioni`: la rete sta fuori da
    questa funzione, che resta sincrona.

    **Le entita' elencate in `entita` di un bilancio VALIDO (con almeno un
    totale) smettono di produrre il loro episodio di energia individuale**
    -- e' il punto per cui questa fetta esiste: se restassero entrambi,
    avremmo undici frammenti *PIU'* l'oggetto, peggio di prima. Un bilancio
    senza nemmeno un totale (le statistiche non hanno detto niente per
    nessuna delle sue dimensioni) NON sopprime niente e non si scrive: e'
    la stessa regola di `direzioni`, mai un oggetto vuoto al posto di
    quello che c'era. Le entita' di energia FUORI da ogni bilancio (nessun
    dispositivo, o un dispositivo la cui unica direzione e' "consumo", che
    non basta a costruirne uno -- vedi `DIREZIONI_BILANCIO`) continuano a
    produrre il loro episodio come prima: **e' il genere a decidere la
    forma**, e un'entita' senza un bilancio da entrare non ha nessuna forma
    migliore di quella che gia' aveva.
    """
    da_ts, a_ts = confini_giorno(giorno, fuso)
    righe = archivio.cambi(da_ts=da_ts, a_ts=a_ts)

    # Solo i bilanci VALIDI (con almeno un totale) sopprimono i loro membri
    # -- vedi il docstring di `bilanci` sopra: un bilancio vuoto sarebbe un
    # peggioramento puro (undici frammenti in meno, zero fatti in piu').
    bilanci_validi = [b for b in (bilanci or [])
                      if isinstance(b, dict) and (b.get("corpo") or {}).get("totali")]
    entita_in_bilancio: set[str] = {e for b in bilanci_validi for e in (b.get("entita") or [])}

    # `unavailable`/`unknown` si saltano QUI, una volta sola, prima di ogni
    # ramo e prima delle misure (`_IGNOTO`, correzione dei punti 2 e 3 del
    # secondo giro di review): un riavvio di Home Assistant li fa
    # attraversare a OGNI entita'. Filtrarli a valle -- come prima, con
    # `_SPENTO` per funzionamento/sicurezza e un `if` locale per presenza --
    # li faceva significare due cose diverse nello stesso modulo: riposo in
    # un ramo (chiude un episodio in corso), salto nell'altro. La riga che
    # si perde qui e' un buco nell'informazione, non un fatto sulla casa:
    # non deve ne' aprire ne' chiudere niente, in NESSUN ramo, e non deve
    # contaminare il riepilogo di un'energia (`misure`, sotto) con
    # "unavailable" come prima o ultima lettura del giorno.
    righe = [r for r in righe
             if str(r["a"] or "").strip().lower() not in _IGNOTO]

    # Prima passata: le misure, per soggetto. Servono come contesto e non
    # generano oggetti da sole.
    misure: dict[str, list[tuple[float, str]]] = {}
    for r in righe:
        misure.setdefault(r["soggetto"], []).append((r["quando_ts"], r["a"]))

    aperti: dict[str, dict] = {}
    # Gli episodi: inizio/fine di ogni oggetto, SENZA ancora i comprimari.
    # Si separano dal corpo apposta (vedi sotto): il limite superiore delle
    # misure di un comprimario dipende dal PROSSIMO episodio dello stesso
    # protagonista, che a meta' del ciclo non e' ancora noto.
    episodi: list[dict] = []
    energia_soggetti: set[str] = set()

    def chiudi(soggetto: str, quando: float | None) -> None:
        o = aperti.pop(soggetto, None)
        if o is None:
            return
        episodi.append({"genere": o["genere"], "protagonista": soggetto,
                        "inizio": o["inizio"], "fine": quando,
                        "corpo_base": {"stato": o["stato"]}})

    for r in righe:
        soggetto = r["soggetto"]
        genere = genere_di(soggetto, _gamba_del_cambio(soggetto, r))
        if genere is None:
            continue
        if genere == "guasto":
            # Solo condizioni di sistema arrivano qui (vedi `genere_di`):
            # convenzione di `osservatore.guarda_sistema` -- "aperto" nasce,
            # "chiuso" e nient'altro finisce.
            if r["a"] == "aperto":
                aperti[soggetto] = {"genere": genere, "inizio": r["quando_ts"],
                                    "stato": "aperto"}
            else:
                chiudi(soggetto, r["quando_ts"])
            continue
        if genere == "sicurezza":
            # Sesta gamba, entita' vera: stessa logica acceso/spento del
            # funzionamento -- il genere e' diverso, la forma no.
            if _acceso(r["a"]):
                if soggetto not in aperti:
                    aperti[soggetto] = {"genere": genere, "inizio": r["quando_ts"],
                                        "stato": r["a"]}
            else:
                chiudi(soggetto, r["quando_ts"])
            continue
        if genere == "presenza":
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
            # Il confronto normalizza (strip, minuscole) come `_acceso` fa
            # per gli altri rami -- pulizia del secondo giro di review: qui
            # confrontava il valore grezzo, mentre il filtro degli stati
            # ignoti, prima di questa correzione, normalizzava tre righe
            # sopra. Due convenzioni per lo stesso valore, ora una sola.
            if str(r["a"] or "").strip().lower() == "home":
                chiudi(soggetto, r["quando_ts"])
            elif soggetto not in aperti:
                aperti[soggetto] = {"genere": genere, "inizio": r["quando_ts"],
                                    "stato": r["a"]}
            continue
        if genere == "funzionamento":
            if _acceso(r["a"]):
                if soggetto not in aperti:
                    aperti[soggetto] = {"genere": genere, "inizio": r["quando_ts"],
                                        "stato": r["a"]}
            else:
                chiudi(soggetto, r["quando_ts"])
            continue
        if genere == "energia":
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
            if soggetto not in entita_in_bilancio:
                energia_soggetti.add(soggetto)

    # Cio' che a fine giornata e' ancora in corso resta APERTO: `fine_ts` a
    # `None` e' un fatto, zero direbbe «finita subito».
    for soggetto in list(aperti):
        chiudi(soggetto, None)

    # Le energie si costruiscono ora, dal riepilogo delle misure: un
    # oggetto di energia del giorno SI CHIUDE sempre (mai `fine_ts: None`,
    # e' gia' cio' che si sa a fine giornata) e porta valore iniziale,
    # finale e la differenza -- non la prima lettura sola con un oggetto
    # perennemente aperto, che era il difetto misurato su 29 contatori
    # della casa.
    for soggetto in sorted(energia_soggetti):
        punti = misure.get(soggetto, [])
        if not punti:
            continue
        iniziale, finale = punti[0][1], punti[-1][1]
        # Una sola lettura nel giorno non dice quanto e' cambiato: e'
        # "non lo sappiamo" -- la stessa distinzione del punto 2, e il
        # codice la fa gia' altrove restituendo `None` quando `_differenza`
        # non riesce a leggere un valore come numero (pulizia del secondo
        # giro di review). Con un solo punto, iniziale e finale sono la
        # STESSA riga: il conto tornerebbe 0.0, il fatto falso "non e'
        # cambiato niente" travestito da dato. **La parola resta neutra**
        # (26/08/2026): "consumato" sarebbe falso per la meta' dei sensori
        # di un impianto fotovoltaico con accumulo, che PRODUCONO.
        differenza = _differenza(iniziale, finale) if len(punti) > 1 else None
        episodi.append({"genere": "energia", "protagonista": soggetto,
                        "inizio": punti[0][0], "fine": punti[-1][0],
                        "corpo_base": {"valore_iniziale": iniziale,
                                       "valore_finale": finale,
                                       "differenza": differenza}})

    # Il limite superiore delle misure di un comprimario e' l'inizio del
    # PROSSIMO episodio dello STESSO protagonista, e la fine della giornata
    # SOLO se non ce n'e' uno (correzione del giro di review, punto 5). Prima
    # di questa correzione il limite era sempre `a_ts`: un riscaldamento
    # acceso 15:30-17:05 e di nuovo 19:00-20:00, con la temperatura misurata
    # fino alle 23:00, faceva riportare al PRIMO episodio come temperatura
    # finale quella delle 23:00 -- il clima del secondo episodio e oltre.
    prossimi_inizi: dict[str, list[float]] = {}
    for e in episodi:
        prossimi_inizi.setdefault(e["protagonista"], []).append(e["inizio"])

    def limite_superiore(protagonista: str, inizio: float) -> float:
        successivi = [i for i in prossimi_inizi.get(protagonista, []) if i > inizio]
        return min(successivi) if successivi else a_ts

    costruiti: list[dict] = []
    for e in episodi:
        alto = limite_superiore(e["protagonista"], e["inizio"])
        corpo = {**e["corpo_base"], "comprimari": [], "misure": {}}
        if e["genere"] == "energia":
            # Solo l'energia porta una direzione (mandato, punto 2): un
            # `direzioni` troppo largo, o un refuso nel confronto del
            # genere, non deve poter far comparire `direzione` su un
            # funzionamento o una presenza.
            info = direzioni(e["protagonista"]) if direzioni else None
            if info:
                corpo["direzione"] = info["direzione"]
                corpo["provenienza"] = info["provenienza"]
        for altro in (comprimari(e["protagonista"]) if comprimari else []):
            # Il limite INFERIORE e' l'inizio dell'oggetto: una misura presa
            # PRIMA che l'episodio cominciasse non e' cio' che si sapeva
            # della grandezza collegata mentre l'oggetto durava, e' il clima
            # di prima. Il limite SUPERIORE e' il prossimo episodio dello
            # stesso protagonista (sopra), o la fine della giornata se non ce
            # n'e' uno: cio' che si sapeva della grandezza mentre l'oggetto
            # durava e subito dopo, prima del prossimo episodio DI QUESTO
            # protagonista -- non del prossimo cambio di un argomento
            # qualunque.
            punti = [(t, v) for t, v in misure.get(altro, [])
                     if e["inizio"] <= t < alto]
            corpo["comprimari"].append(altro)
            if punti:
                corpo["misure"][altro] = {"da": punti[0][1], "a": punti[-1][1]}
        costruiti.append({"genere": e["genere"], "protagonista": e["protagonista"],
                          "inizio_ts": e["inizio"], "fine_ts": e["fine"],
                          "corpo": corpo})

    # I bilanci: un oggetto al giorno per dispositivo, protagonista =
    # `dispositivo_id` (stabile nel registro di HA -- non l'entita', che il
    # bilancio riassume, ne' il nome, che l'utente puo' cambiare: si
    # RISOLVE in aggregazione, non si congela nel grezzo, la stessa ragione
    # di `comprimari`/`direzioni`). Si CHIUDE sempre dentro la giornata (mai
    # `fine_ts: None`, come l'energia individuale sopra): e' gia' cio' che
    # si sa a fine giornata.
    for b in bilanci_validi:
        costruiti.append({
            "genere": "bilancio", "protagonista": b["dispositivo_id"],
            "inizio_ts": da_ts, "fine_ts": a_ts,
            "corpo": {**b["corpo"], "dispositivo": b.get("nome"),
                     "entita": sorted(b.get("entita") or [])},
        })

    return archivio.sostituisci_giorno(giorno, costruiti)
