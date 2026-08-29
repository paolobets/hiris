"""Il tempo della casa: quale superficie di Home Assistant interrogare, e come
dire cio' che si e' letto.

Non archivia NIENTE. La decisione del proprietario e' esplicita -- «deve
leggere da HA sempre» -- e non e' una preferenza: HIRIS ha gia' avuto un
archivio storico suo (`history.db`), e' uscito perche' scriveva senza che
nessuno leggesse, e l'avvio lo tratta ancora oggi come un residuo da
rimuovere. Ricostruirlo qui non sarebbe una scelta nuova, sarebbe
dissotterrare qualcosa che il prodotto ha gia' seppellito.

Vive in `casa/` e non in `proxy/` perche' non parla il protocollo di Home
Assistant: lo fanno le tre primitive di `proxy/ha_client.py`. Qui si decide
COSA chiedere e si compone la risposta -- ed e' la stessa divisione che il
prodotto ha gia' fra `casa/domande.py` (puro) e chi gli passa lo stato.
"""
from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# Sotto questa finestra «l'andamento» significa i cambi veri; sopra, le fasce
# orarie. **E' una scelta, non una misura**, e la spec la dichiara come tale
# (§4.1): sopra la giornata migliaia di punti sono illeggibili sia per il
# modello sia per chi legge la risposta, e le fasce che Home Assistant ha gia'
# calcolato sono migliori di un riassunto fatto da noi -- oltre a costare una
# chiamata invece di una chiamata piu' un riassunto.
#
# Conseguenza da guardare in faccia: la domanda da cui questa fetta nasce --
# «le temperature delle camere nelle ultime 48 ore» -- cade SOPRA la soglia e
# riceve fasce orarie. Se la si volesse piu' fine, si alza questo numero.
SOGLIA_GRANA_ORE = 24

# Il tetto della finestra richiedibile: 90 giorni. Non e' la conservazione di
# Home Assistant (quella non e' leggibile da nessuna API, vedi
# `finestra_coperta` in `andamento`): e' il limite oltre il quale la domanda
# non e' piu' una domanda sulla casa ma una scansione del database.
MAX_FINESTRA_ORE = 24 * 90

# Quando `ore` non e' interpretabile. Un giorno: la finestra che la parola
# «oggi» significa.
DEFAULT_ORE = 24.0


def normalizza_ore(grezzo, *, tetto: float = MAX_FINESTRA_ORE,
                   default: float = DEFAULT_ORE) -> float:
    """Qualunque cosa -> un numero di ore fra 1 e `tetto`.

    `ore` arriva da una tool-call del modello: puo' essere `None`, una
    stringa, NaN o un numero fuori scala. Si normalizza in spazio float e si
    clampa PRIMA che diventi un `timedelta`, perche' `timedelta(hours=1e12)`
    solleva `OverflowError`.

    E' la normalizzazione centrale per le ore nel prodotto: la usano sia gli
    strumenti del tempo (con tetto di 90 giorni) sia il diario del client
    (con tetto di una settimana). I tetti sono l'unica cosa che cambia fra i
    due usi. Si normalizza in float, e il chiamante puo' convertire in int se
    serve.

    Il contratto e' "qualunque cosa → un numero fra 1 e il tetto": una
    clausola stretta (TypeError, ValueError) trasformerebbe una difesa in un
    buco. `float(10**400)` solleva OverflowError, che non e' ne' TypeError
    ne' ValueError, cioe' esattamente la classe di input che una tool-call
    JSON produce. Una funzione totale per contratto ha diritto a un except
    totale.
    """
    try:
        numero = float(grezzo)
    except Exception:
        return default
    if math.isnan(numero):  # NaN: non confrontabile, vale come assente
        return default
    return min(float(tetto), max(1.0, numero))


# I soli state_class che Home Assistant traduce DAVVERO in statistiche a
# lungo termine -- i valori di `sensor.const.SensorStateClass` che il
# recorder aggrega, verificati alla fonte (non a memoria: e' la stessa
# trappola di `carbon_monoxide`/`co` gia' pagata da questo progetto).
# `measurement_angle` ESISTE come state_class (angoli, es. la direzione del
# vento) ma NON produce statistiche -- e' documentato da Home Assistant, non
# un'omissione nostra (spec §1). Un'appartenenza a questo insieme, non
# un'esclusione della sola `measurement_angle`: il vocabolario di HA non si
# arrotonda, e domani potrebbe crescere di un'altra classe che non aggrega.
STATE_CLASS_CON_STATISTICHE = frozenset({"measurement", "total", "total_increasing"})


def produce_statistiche(state_class) -> bool:
    """Se questo `state_class` produce DAVVERO una statistica a lungo termine.

    Non `bool(state_class)`: quel cablaggio manderebbe ANCHE
    `measurement_angle` sul ramo statistiche, e una banderuola interrogata
    oltre la soglia di grana riceverebbe un elenco vuoto -- «non e' mai
    cambiata» -- mentre il dettaglio, la superficie giusta per lei, esiste.
    Vive qui (pura, senza rete) accanto a `scegli_superficie`, che la
    consuma: e' domanda di vocabolario HA, non di scelta della superficie.

    Il nome e' diverso dal parametro `ha_statistiche` che questo modulo passa
    in giro (`andamento`, `scegli_superficie`): quello e' gia' il booleano
    risolto, questa e' la funzione che lo risolve dal vocabolario di HA --
    due cose diverse, non due nomi per la stessa."""
    return state_class in STATE_CLASS_CON_STATISTICHE


def scegli_superficie(*, ore: float, ha_statistiche: bool) -> str:
    """`"dettaglio"` o `"statistiche"`, e nient'altro puo' deciderlo.

    Due assi soli: quanto e' lunga la finestra, e se l'entita' ha
    `state_class` (cioe' se di lei ESISTE una statistica). Un'entita' senza
    `state_class` resta sul dettaglio anche su finestre lunghe, perche' per
    lei le statistiche non esistono e un elenco vuoto direbbe «non e' mai
    cambiata».

    La soglia e' INCLUSIVA: 24 ore esatte sono ancora dettaglio. «Le ultime
    ventiquattr'ore» e' una domanda su oggi, e su oggi si guardano i cambi.
    """
    if ore <= SOGLIA_GRANA_ORE:
        return "dettaglio"
    return "statistiche" if ha_statistiche else "dettaglio"


def zona_casa(fuso: str | None):
    """Il fuso della casa, o UTC se non lo sappiamo. Non inventa mai.

    Un fuso sbagliato sposta le ore di una risposta senza che nessuno se ne
    accorga: e' peggio di non averlo. Con UTC almeno l'offset e' scritto
    nell'istante, e chi legge puo' fare i conti.

    **Pubblica (giro di correzioni, punto 4):** prima era `_zona`, privata,
    e `cervello/oggetti.py` la importava comunque per calcolare i confini
    del giorno -- un nome con underscore attraversato da fuori e' esattamente
    come nascono i doppioni, perche' il prossimo che ne ha bisogno o importa
    il nome privato o riscrive il calcolo.
    """
    if not fuso:
        return UTC
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(fuso)
    except Exception:
        logger.warning("fuso della casa non riconosciuto (%r): finestra in UTC", fuso)
        return UTC


def finestra(*, ore: float, adesso_ts: float, fuso: str | None) -> tuple[str, str]:
    """`(da_iso, a_iso)` nel fuso della casa, con l'offset SEMPRE scritto.

    Un istante senza fuso e' la stessa classe di difetto di un numero senza
    unita': «alle 17» di quale fuso? E' la stessa regola che `epoch_istante`,
    qui sotto, applica in lettura (e che `casa/strumenti.py` riusa per gli
    istanti in ingresso della chat) -- applicata qui in uscita.
    """
    zona = zona_casa(fuso)
    a = datetime.fromtimestamp(adesso_ts, tz=zona)
    da = a - timedelta(hours=ore)
    return da.isoformat(), a.isoformat()


# Quanti punti arrivano al modello in UNA risposta. Non e' il cap del client
# (`MAX_STORICO_PUNTI`, che protegge la memoria di questo processo): questo
# protegge la LEGGIBILITA'. Per le entita' con statistiche il problema non si
# pone -- sopra la soglia si passa alle fasce -- ma per le altre il dettaglio
# e' l'unica fonte che esista, e li' si riassume di nostro.
MAX_PUNTI_IN_RISPOSTA = 120

_NOTA_MAI_CAMBIATO = "in questa finestra il valore non e' mai cambiato."
# Tre cause producono lo STESSO risultato vuoto, e da qui non si distinguono:
# `purge_keep_days` non e' leggibile da nessuna API, quindi non sappiamo se i
# dati ci sono mai stati e sono scaduti, o non ci sono mai stati. Elencarne
# due e ometterne una terza (la piu' comune: la finestra chiesta e' oltre
# cio' che HA conserva) sarebbe affermare cause sbagliate con sicurezza --
# l'onesto e' dichiarare l'incertezza fra le tre, non risolverla a caso.
# Nessun numero di giorni qui: quel numero non lo sappiamo.
_NOTA_NESSUNA_REGISTRAZIONE = (
    "Home Assistant non ha registrazioni per questa entita' in questa "
    "finestra: puo' darsi che la finestra chiesta vada oltre cio' che Home "
    "Assistant conserva, che l'entita' sia esclusa dalla registrazione "
    "(in quel caso non ne restera' mai), oppure che non esista piu' -- da "
    "qui non possiamo distinguere quale delle tre."
)
_NOTA_FASCE = (
    "valori a fasce orarie (minimo, massimo, media di ogni ora), non le "
    "singole misure: la finestra chiesta e' piu' lunga di un giorno."
)
# F1 (onda finale): un `inizio` che non si legge come ISO-8601 col fuso NON e'
# «nessuna registrazione» -- e' una forma che questo modulo non sa leggere.
# Prima dell'onda finale l'`or 0.0` sulla riga qui sotto trasformava
# `epoch_istante(None)` in zero, il confronto con `da_ts` (~1,7 miliardi)
# scartava la fascia come "prima della finestra", e un'entita' con dati VERI
# finiva su «Home Assistant non ha registrazioni». Non e' un'ipotesi di
# scuola: alcune versioni del recorder rendono `start` come epoch in
# millisecondi (un numero), non come stringa ISO -- MAI misurato dal vivo su
# questo prodotto (spec §7). Fallire rumorosamente qui, invece di convertire
# in silenzio, e' la parte obbligatoria della correzione (vedi il rapporto
# dell'onda finale): il modello deve poter dire «non ho potuto leggere»
# invece di «non c'e' niente».
_ERRORE_FASCIA_ILLEGGIBILE = (
    "Home Assistant ha risposto con fasce orarie il cui istante di inizio "
    "non e' nella forma attesa (ISO-8601 con fuso): non posso dire se i dati "
    "ci sono senza rischiare di leggerli male."
)


async def andamento(*, ha, entita: str, ore, unita: str | None,
                    ha_statistiche: bool, adesso_ts: float,
                    fuso: str | None) -> dict:
    """Un valore nel tempo, con la grana e la finestra DAVVERO coperte.

    Ritorna `{"entita", "grana", "unita", "finestra_chiesta_ore",
    "finestra_coperta", "punti", "nota"}`, oppure `{"entita", "unita",
    "finestra_chiesta_ore", "errore"}` -- mai `punti: []` per un guasto
    (spec §3.3). Le tre chiavi di contesto (`unita`, `finestra_chiesta_ore`)
    viaggiano anche col guasto: sono cio' che il chiamante aveva chiesto, non
    cio' che HA ha risposto, quindi restano note anche quando HA non risponde.

    **La finestra coperta si misura dai dati tornati**, non si deduce da
    `purge_keep_days`: quel valore non e' leggibile da nessuna API di Home
    Assistant, e una costante scritta qui sarebbe un'assunzione che questa
    casa puo' smentire in silenzio.

    **Una fascia oraria con un `inizio` che non si legge come ISO-8601 col
    fuso e' un guasto, non un vuoto** (fix onda finale, F1): convertirla in
    silenzio in «prima della finestra» produrrebbe la stessa frase falsa di
    `_NOTA_NESSUNA_REGISTRAZIONE` su un'entita' che invece ha dati veri.
    """
    ore = normalizza_ore(ore)
    da_iso, a_iso = finestra(ore=ore, adesso_ts=adesso_ts, fuso=fuso)
    superficie = scegli_superficie(ore=ore, ha_statistiche=ha_statistiche)
    base = {"entita": entita, "unita": unita, "finestra_chiesta_ore": ore}

    if superficie == "statistiche":
        esito = await ha.statistiche([entita], "hour", int(ore / 24) + 1)
        if "serie" not in esito:
            return {**base, "errore": esito.get("errore", "statistiche non disponibili")}
        # Il confronto passa per l'epoch, MAI per le stringhe: le statistiche
        # tornano in UTC (`+00:00`) e la finestra nasce nel fuso della casa
        # (`+02:00` d'estate a Roma). Due ISO-8601 con offset diversi non sono
        # ordinabili come testo -- «2026-08-23T13:00:00+00:00» sembra maggiore
        # di «2026-08-23T14:00:00+02:00» e sono lo stesso istante.
        da_ts = epoch_istante(da_iso) or 0.0
        tutte = esito["serie"].get(entita, [])
        # Si separa PRIMA «non si legge» da «e' prima della finestra»: un
        # `or 0.0` unico per i due casi (come c'era) confonde un istante
        # illeggibile con un istante fuori finestra, e il secondo scarta la
        # fascia in silenzio mentre il primo deve fermare la risposta.
        illeggibili = [f for f in tutte if epoch_istante(f.get("inizio")) is None]
        if illeggibili:
            return {**base, "errore": _ERRORE_FASCIA_ILLEGGIBILE}
        fasce = [f for f in tutte if epoch_istante(f.get("inizio")) >= da_ts]
        if not fasce:
            return {**base, "grana": "oraria", "finestra_coperta": None,
                    "punti": [], "nota": _NOTA_NESSUNA_REGISTRAZIONE}
        nota = _NOTA_FASCE
        ridotte = fasce
        if len(fasce) > MAX_PUNTI_IN_RISPOSTA:
            # Stesso gemello del ramo dettaglio, due righe piu' sotto: uno
            # slice secco (`fasce[-N:]`) sposta `punti[0]` avanti nel tempo
            # mentre `finestra_coperta` restava calcolata sull'elenco intero
            # -- una copertura dichiarata e non consegnata (fondamenta 3).
            # `_assottiglia` campiona invece di tagliare, e tiene la prima
            # fascia in indice 0: e' cio' che tiene `finestra_coperta` vera.
            ridotte = _assottiglia(fasce, MAX_PUNTI_IN_RISPOSTA)
            # Il numero VERO delle fasce, non «molte»: la media di un'ora
            # resta una media, l'assottigliamento qui e' un campionamento
            # sulle fasce gia' pronte, mai una media di medie.
            nota = (f"{_NOTA_FASCE} {len(fasce)} fasce nella finestra, ridotte "
                    f"a {len(ridotte)} distribuite nel tempo.")
        return {**base, "grana": "oraria",
                "finestra_coperta": _coperta(fasce, "inizio", a_iso),
                # Stesso motivo del ramo dettaglio: le statistiche tornano in
                # UTC e la finestra nasce nel fuso della casa. Due offset nella
                # stessa risposta sono la fondamenta 3 rotta in un dizionario.
                "punti": _nel_fuso(ridotte, ("inizio", "fine"), a_iso), "nota": nota}

    esito = await ha.storico([entita], da_iso, a_iso)
    if "serie" not in esito:
        return {**base, "errore": esito.get("errore", "storico non disponibile")}
    punti = esito["serie"].get(entita, [])
    if not punti:
        return {**base, "grana": "dettaglio", "finestra_coperta": None,
                "punti": [], "nota": _NOTA_NESSUNA_REGISTRAZIONE}
    # F2 (onda finale): `ha.storico` promette nel proprio docstring che
    # `troncato` c'e' SEMPRE, apposta perche' «chi legge deve poter sapere
    # che e' scattato». Non leggerlo qui butta via quella promessa: dopo il
    # cap del client `len(punti)` e' un PAVIMENTO (il client tiene la CODA --
    # i punti piu' recenti -- e scarta la testa), non il conteggio vero, e
    # spacciarlo per esatto direbbe «5000 cambi» quando ce n'erano 12.000. La
    # stessa ragione per cui `finestra_coperta` si e' ristretta: il taglio ha
    # scartato i cambi piu' vecchi, non la casa ha smesso di generarli.
    troncato_dal_client = bool(esito.get("troncato"))
    conteggio = f"almeno {len(punti)}" if troncato_dal_client else str(len(punti))
    nota = None
    if len(punti) == 1 and not troncato_dal_client:
        nota = _NOTA_MAI_CAMBIATO
    ridotti = punti
    if len(punti) > MAX_PUNTI_IN_RISPOSTA:
        ridotti = _assottiglia(punti, MAX_PUNTI_IN_RISPOSTA)
        # Il numero VERO (o il pavimento dichiarato come tale), non «molti»:
        # e' cio' che permette a chi legge di capire che sta guardando un
        # campione e non l'elenco intero.
        nota = (f"{conteggio} cambi nella finestra, ridotti a "
                f"{len(ridotti)} punti distribuiti nel tempo.")
    if troncato_dal_client:
        nota = (nota or f"{conteggio} cambi nella finestra.") + (
            " Home Assistant ne aveva di piu' di quelli che questo elenco "
            "puo' portare: sono stati tenuti i piu' recenti, e la finestra "
            "davvero coperta e' percio' piu' corta di quella chiesta.")
    return {**base, "grana": "dettaglio",
            "finestra_coperta": _coperta(punti, "quando", a_iso),
            # Gli istanti dei punti si riscrivono nel fuso della casa, come
            # gia' fa `_coperta` per gli estremi della finestra. Visto dal
            # vivo il 24/08/2026: `finestra_coperta` diceva `14:18+02:00` e
            # `punti[0]` diceva `12:18+00:00` -- lo STESSO istante, dentro un
            # dizionario solo. Chi legge (un modello, che poi parla a una
            # persona) puo' concluderne che i dati cominciano due ore dopo
            # l'apertura della finestra. E' la fondamenta 3 dentro una sola
            # risposta, e costa una riscrittura.
            "punti": _nel_fuso(ridotti, ("quando",), a_iso), "nota": nota}


def epoch_istante(grezzo) -> float | None:
    """Un ISO-8601 col fuso -> epoch. `None` se non si legge o se il fuso manca.

    Un istante SENZA fuso viene rifiutato invece di essere letto come locale:
    «alle 17» di quale fuso? E' la stessa regola dell'unita' di misura
    applicata al tempo -- l'UNICA lettura di un istante nel prodotto: la usa
    questo modulo per cio' che arriva da Home Assistant, e la usa
    `casa/strumenti.py` (`_prometti`) per l'istante che arriva dalla chat. Era
    scritta due volte (una in ciascun modulo, letteralmente identica); questo
    modulo e' leggero e non importa quasi niente, quindi resta qui e
    `strumenti.py` la importa -- mai il contrario.
    """
    if not isinstance(grezzo, str) or not grezzo.strip():
        return None
    try:
        momento = datetime.fromisoformat(grezzo.strip())
    except ValueError:
        return None
    return None if momento.tzinfo is None else momento.timestamp()


def _nel_fuso(punti: list[dict], chiavi: tuple[str, ...], a_iso: str) -> list[dict]:
    """Le chiavi temporali di `punti` (`chiavi`) riscritte nel fuso di `a_iso`.

    Lo storico di Home Assistant torna in UTC, la finestra nasce nel fuso
    della casa: senza questa riscrittura la stessa risposta porta due offset
    e chi legge deve fare i conti da solo -- o non li fa.

    **Ogni chiave temporale del punto, non solo la prima** (correzione
    BASSA della review, mandato «il bilancio dell'energia», punto 5,
    27/08/2026): la traduzione unificata ha aggiunto la chiave `fine` a
    ogni fascia delle statistiche, ma questa funzione riscriveva solo
    `inizio` -- lo stesso punto usciva con `inizio` a +02:00 e `fine`
    ancora a +00:00, due fusi nella stessa risposta. E' la rottura della
    consistenza fra le porte dentro un modulo i cui stessi commenti la
    denunciano per `finestra_coperta`/`punti` (vedi `andamento` sopra) e
    non se ne accorgevano per `fine`. Il ramo del dettaglio passa una sola
    chiave (`("quando",)`): le sue righe non portano `fine`, quindi il
    ciclo sotto e' un no-op su quella chiave, non un ramo diverso.

    Cio' che non si sa leggere resta com'e': meglio un istante nel fuso
    sbagliato che uno inventato, e la coppia `finestra_coperta` lo dichiara
    comunque con la stessa regola.
    """
    zona = None
    try:
        zona = datetime.fromisoformat(a_iso).tzinfo
    except ValueError:
        return list(punti)
    riscritti = []
    for p in punti:
        nuovo = dict(p)
        for chiave in chiavi:
            quando = epoch_istante(p.get(chiave))
            if quando is not None:
                nuovo[chiave] = datetime.fromtimestamp(quando, tz=zona).isoformat()
        riscritti.append(nuovo)
    return riscritti


def _coperta(punti: list[dict], chiave: str, a_iso: str) -> dict | None:
    """La finestra che i dati coprono DAVVERO -- dal primo istante tornato.

    `da` si riscrive nel fuso di `a`: le statistiche tornano in UTC e la
    finestra nasce nel fuso della casa, e due estremi della STESSA finestra
    con due offset diversi sono la fondamenta 3 rotta dentro un dizionario di
    due chiavi. Se l'istante non si legge si restituisce com'e' arrivato --
    meglio un formato inatteso che un istante inventato -- ma SEMPRE come
    stringa: `da` e `a` sono la stessa coppia, e un `da` numerico accanto a un
    `a` ISO (fix onda finale, F1) sarebbe una frase vera che significa una
    cosa falsa quanto una grana taciuta.
    """
    if not punti:
        return None
    grezzo = punti[0].get(chiave)
    quando = epoch_istante(grezzo)
    if quando is None:
        return {"da": grezzo if grezzo is None else str(grezzo), "a": a_iso}
    try:
        zona = datetime.fromisoformat(a_iso).tzinfo
        da = datetime.fromtimestamp(quando, tz=zona).isoformat()
    except ValueError:
        da = grezzo
    return {"da": da, "a": a_iso}


def _assottiglia(punti: list[dict], quanti: int) -> list[dict]:
    """Un campione distribuito nel tempo, primo e ultimo sempre compresi.

    Non una media: la media di stati che possono essere `on`/`off` non
    significa niente, e questa funzione serve anche a quelli. Perdere dei
    punti e' dichiarato dalla nota che accompagna la risposta; INVENTARNE uno
    che non e' mai esistito non si dichiara in nessun modo.
    """
    if len(punti) <= quanti:
        return list(punti)
    if quanti <= 1:
        # Con un solo posto non si puo' tenere primo E ultimo: si tiene il
        # piu' recente. Irraggiungibile con `MAX_PUNTI_IN_RISPOSTA` (120), ma
        # la funzione ha un secondo chiamante (il ramo statistiche) e senza
        # questa guardia `quanti - 1` diventerebbe zero al denominatore.
        return [punti[-1]]
    passo = (len(punti) - 1) / (quanti - 1)
    scelti = [punti[round(i * passo)] for i in range(quanti)]
    scelti[-1] = punti[-1]
    return scelti


# Quanto possono distare un atto della cronaca e la voce del diario che
# racconta il suo effetto, perche' si possano considerare lo stesso gesto.
# Home Assistant NON mette un nostro identificatore nel logbook: l'unico
# aggancio e' entita' + istante vicino, e sessanta secondi sono larghi per la
# latenza di una chiamata di servizio e stretti per due gesti distinti sulla
# stessa lampada. E' il motivo per cui l'esito si chiama «probabile».
TOLLERANZA_ABBINAMENTO_S = 60


async def accaduto(*, ha, cronaca, entita: str | None, ore,
                   adesso_ts: float) -> dict:
    """Cosa e' successo in una finestra, e -- dove si puo' dire -- per mano di chi.

    Ritorna `{"voci", "troncato", "ore", "nota"}` oppure `{"errore"}`.

    Le due fonti restano DUE (fondamenta 2): il diario di Home Assistant dice
    cosa e' successo in casa, la cronaca dice cosa ha fatto HIRIS. Si uniscono
    qui, al momento della lettura, e mai in una tabella.

    L'abbinamento e' dichiarato `probabile` e non si finge certo: vedi
    `TOLLERANZA_ABBINAMENTO_S`. Restituire un `esecuzione_id` che il modello
    non puo' risolvere rispetterebbe la lettera della fondamenta 2 violando la
    4, quindi l'atto viaggia con origine e servizio, non col solo numero.

    **Se la cronaca e' assente o non risponde, la nota lo dichiara** (fix
    onda finale, F3): senza questa dichiarazione «HIRIS non l'ha fatto» e
    «non ho potuto guardare la mia cronaca» hanno la stessa faccia -- nessuna
    voce porta `per_mano_di` -- e il modello direbbe con sicurezza «l'ha
    accesa qualcuno, non so chi» anche quando era stato HIRIS e il dato
    c'era, solo illeggibile.
    """
    ore = normalizza_ore(ore)
    esito = await ha.diario(entita, int(ore))
    if "voci" not in esito:
        return {"errore": esito.get("errore", "il diario non e' disponibile")}
    # La finestra dell'abbinamento e' quella che il diario ha DAVVERO coperto
    # (`ore` puo' essere stato clampato dal client): due finestre diverse
    # produrrebbero atti senza voce e voci senza atto, in modo invisibile.
    ore_vere = float(esito.get("ore") or ore)
    atti = []
    # F3 (onda finale): `cronaca_letta` distingue «HIRIS non l'ha fatto» da
    # «non ho potuto guardare la mia cronaca» -- oggi le due hanno la STESSA
    # faccia (l'assenza di `per_mano_di` su ogni voce), e senza questa
    # dichiarazione il modello direbbe «l'ha accesa qualcuno, non so chi»
    # ANCHE quando e' stato HIRIS e il dato c'era, solo illeggibile. E' la
    # stessa ragione per cui `_cerca` costruisce `non_ho_potuto_guardare`
    # (`_cecita` in strumenti.py): due facce diverse per due fatti diversi.
    cronaca_letta = False
    if cronaca is None:
        logger.debug("accaduto: nessuna cronaca disponibile, attribuzione persa")
    else:
        try:
            atti = cronaca.list(da_ts=adesso_ts - ore_vere * 3600,
                                  a_ts=adesso_ts, entity=entita)
            cronaca_letta = True
        except Exception as errore:
            # L'attribuzione e' un di piu': un archivio che non risponde non
            # deve togliere all'utente la risposta sulla casa -- ma deve
            # dichiararsi, non sparire in silenzio (vedi sopra).
            logger.warning("cronaca illeggibile durante «accaduto» (%s: %s)",
                           type(errore).__name__, errore)
            atti = []
    voci = [_abbina(v, atti) for v in esito["voci"]]
    note = []
    if not cronaca_letta:
        note.append(
            "non ho potuto controllare la mia cronaca: una voce senza "
            "«per_mano_di» potrebbe comunque essere mia, e non solo di "
            "un'automazione o di una persona."
        )
    if esito.get("troncato"):
        note.append("le voci piu' vecchie della finestra non sono in questo elenco.")
    if ore_vere < ore:
        note.append(f"il diario copre al piu' {int(ore_vere)} ore, non le "
                    f"{int(ore)} chieste.")
    return {"voci": voci, "troncato": bool(esito.get("troncato")),
            "ore": int(ore_vere), "nota": " ".join(note) or None}


def _abbina(voce: dict, atti: list[dict]) -> dict:
    """La voce del diario, piu' -- dove si puo' dire -- l'atto che PROBABILMENTE
    l'ha causata. Senza abbinamento la voce esce INVARIATA: «e' successo
    qualcosa e non so chi» resta una risposta onesta.

    Senza entita' sulla voce non c'e' nessun aggancio possibile, e non si
    tenta. Il logbook di Home Assistant produce voci senza `entity_id` (i
    trigger di automazione, per esempio): abbinarle sulla sola vicinanza
    temporale prenderebbe un atto su un'ALTRA entita' e lo marcherebbe
    `per_mano_di: HIRIS` -- un falso positivo travestito da probabilita', e
    con `entita=None` (la domanda "cosa e' successo in casa" senza filtro)
    non e' un angolo remoto ma l'uso di prima classe dell'interfaccia.

    Fra i candidati che passano entita' e tolleranza si sceglie quello con lo
    scarto temporale MINORE, non il primo che la cronaca restituisce
    (ordinata per tempo decrescente): con due tentativi ravvicinati sulla
    stessa entita' il primo della lista non e' detto sia il gesto giusto.
    """
    quando = epoch_istante(voce.get("quando"))
    entita_voce = voce.get("entita")
    if quando is None or not entita_voce:
        return voce
    migliore, scarto_migliore = None, None
    for atto in atti:
        if entita_voce not in (atto.get("entita") or []):
            continue
        scarto = abs(float(atto.get("quando_ts") or 0.0) - quando)
        if scarto > TOLLERANZA_ABBINAMENTO_S:
            continue
        if scarto_migliore is None or scarto < scarto_migliore:
            migliore, scarto_migliore = atto, scarto
    if migliore is None:
        return voce
    return {**voce, "per_mano_di": "HIRIS", "abbinamento": "probabile",
            "atto": {"id": migliore.get("id"), "origine": migliore.get("origine"),
                     "servizio": migliore.get("servizio")}}
