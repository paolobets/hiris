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
dominio, `device_class`, `state_class`. **La seconda, invece, SI'**
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

GENERI = ("funzionamento", "presenza", "consumo", "guasto", "sicurezza")

# I domini che «funzionano»: si accendono e si spengono, si aprono e si
# chiudono. Sono i protagonisti degli oggetti di funzionamento. **Lista
# scritta a mano, dichiaratamente** (vedi il docstring del modulo): mancavano
# `humidifier`, `vacuum`, `valve` e `media_player` -- domini comuni che
# funzionano come gli altri sei, e che prima di questa correzione cadevano in
# silenzio (nessun oggetto, nessun errore).
_FUNZIONANO = frozenset({"climate", "cover", "switch", "light", "fan",
                         "water_heater", "humidifier", "vacuum", "valve",
                         "media_player"})

# Gli stati che valgono «a riposo»: chiudono un oggetto di funzionamento o di
# sicurezza. "locked" e' il riposo della serratura. **"armed_*" e' il riposo
# del pannello dell'allarme, "disarmed" e "triggered" NO** -- correzione al
# rovesciamento della review (punto 3b): e' controintuitivo per chi legge in
# fretta, ma un allarme si INSERISCE per stare a riposo, non il contrario.
# Prima di questa correzione "disarmed" stava qui e "armed_*" non c'era da
# nessuna parte: inserire l'allarme la sera apriva un oggetto, e disinserirlo
# la mattina lo chiudeva -- otto ore di «oggetto» ogni notte per la cosa che
# va bene, e la casa lasciata senza allarme un giorno intero non produceva
# niente. Un solo insieme, non due che si sovrappongono: `_SPENTO` e' usato
# da piu' rami (funzionamento e sicurezza), e i valori qui sotto sono
# esclusivi per dominio (nessuna ambiguita' fra "locked"/"armed_home" e gli
# stati di `_FUNZIONANO`).
_SPENTO = frozenset({"off", "closed", "unavailable", "unknown", "none", "",
                     "locked", "armed_home", "armed_away", "armed_night",
                     "armed_vacation", "armed_custom_bypass"})

# Stati "non lo so", non stati della casa. Un riavvio di Home Assistant fa
# attraversare questi due stati a OGNI entita', comprese le `person`: senza
# questo filtro il ramo `presenza` (che controlla solo `r["a"] == "home"`)
# apriva un oggetto «presenza, stato unavailable» di un minuto per ogni
# persona, a ogni riavvio (correzione del giro di review, punto 2). Il ramo
# `funzionamento` li tiene fuori gia' tramite `_SPENTO` (che li considera «a
# riposo», quindi non apre niente); la presenza non ha un riposo che si
# chiami "off", quindi il filtro va ripetuto qui esplicitamente.
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
    if dominio == "sensor" and gamba_ == "consumo":
        return "consumo"
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
    definizione, non un giudizio nostro: e' cio' che `pavimento.gamba()`
    legge per decidere la gamba di `sensor` e `binary_sensor`.

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
    lettura fallisce: zero direbbe «consumo nullo» per un valore che non si e'
    nemmeno potuto interpretare, e sarebbe un fatto falso travestito da dato.
    """
    try:
        return float(finale) - float(iniziale)
    except (TypeError, ValueError):
        return None


def aggrega_giorno(*, archivio, giorno: str, fuso: str | None,
                         comprimari=None) -> int:
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

    **Il consumo e' un genere a parte** (correzione del giro di review,
    punto 6): non ha un "acceso"/"spento" -- un contatore sale e basta -- e
    non nasce da un ciclo apri/chiudi come gli altri generi. Un oggetto di
    consumo e' il RIEPILOGO del giorno per quel contatore: la prima lettura,
    l'ultima, e la loro differenza. Si chiude sempre dentro la giornata (mai
    `fine_ts: None`), perche' e' gia' cio' che si sa a fine giornata, non
    qualcosa ancora in corso.
    """
    da_ts, a_ts = confini_giorno(giorno, fuso)
    righe = archivio.cambi(da_ts=da_ts, a_ts=a_ts)

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
    consumo_soggetti: set[str] = set()

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
            # `_IGNOTO` (correzione punto 2): "unavailable"/"unknown" non
            # sono uno stato della casa, sono un buco nell'informazione --
            # un riavvio di HA li fa attraversare a ogni `person`. Un ramo
            # che li trattasse come "non home" aprirebbe un oggetto fantasma
            # a ogni riavvio, uno per persona.
            stato = str(r["a"] or "").strip().lower()
            if stato in _IGNOTO:
                continue
            if r["a"] == "home":
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
        if genere == "consumo":
            # Nessun apri/chiudi qui: si annota solo CHE il soggetto e' un
            # contatore visto oggi. Il riepilogo (prima lettura, ultima,
            # differenza) si costruisce dopo il ciclo, da `misure`, che gia'
            # tiene ogni lettura del giorno in ordine cronologico.
            consumo_soggetti.add(soggetto)

    # Cio' che a fine giornata e' ancora in corso resta APERTO: `fine_ts` a
    # `None` e' un fatto, zero direbbe «finita subito».
    for soggetto in list(aperti):
        chiudi(soggetto, None)

    # I consumi si costruiscono ora, dal riepilogo delle misure: un oggetto
    # di consumo del giorno SI CHIUDE sempre (mai `fine_ts: None`, e' gia'
    # cio' che si sa a fine giornata) e porta valore iniziale, finale e la
    # differenza -- non la prima lettura sola con un oggetto perennemente
    # aperto, che era il difetto misurato su 29 contatori della casa.
    for soggetto in sorted(consumo_soggetti):
        punti = misure.get(soggetto, [])
        if not punti:
            continue
        iniziale, finale = punti[0][1], punti[-1][1]
        episodi.append({"genere": "consumo", "protagonista": soggetto,
                        "inizio": punti[0][0], "fine": punti[-1][0],
                        "corpo_base": {"valore_iniziale": iniziale,
                                       "valore_finale": finale,
                                       "differenza": _differenza(iniziale, finale)}})

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
    for lista in prossimi_inizi.values():
        lista.sort()

    def limite_superiore(protagonista: str, inizio: float) -> float:
        successivi = [i for i in prossimi_inizi.get(protagonista, []) if i > inizio]
        return min(successivi) if successivi else a_ts

    costruiti: list[dict] = []
    for e in episodi:
        alto = limite_superiore(e["protagonista"], e["inizio"])
        corpo = {**e["corpo_base"], "comprimari": [], "misure": {}}
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

    return archivio.sostituisci_giorno(giorno, costruiti)
