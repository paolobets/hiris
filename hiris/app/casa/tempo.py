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
from datetime import datetime, timedelta, timezone

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
    if numero != numero:  # NaN: non confrontabile, vale come assente
        return default
    return min(float(tetto), max(1.0, numero))


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


def _zona(fuso: str | None):
    """Il fuso della casa, o UTC se non lo sappiamo. Non inventa mai.

    Un fuso sbagliato sposta le ore di una risposta senza che nessuno se ne
    accorga: e' peggio di non averlo. Con UTC almeno l'offset e' scritto
    nell'istante, e chi legge puo' fare i conti.
    """
    if not fuso:
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(fuso)
    except Exception:
        logger.warning("fuso della casa non riconosciuto (%r): finestra in UTC", fuso)
        return timezone.utc


def finestra(*, ore: float, adesso_ts: float, fuso: str | None) -> tuple[str, str]:
    """`(da_iso, a_iso)` nel fuso della casa, con l'offset SEMPRE scritto.

    Un istante senza fuso e' la stessa classe di difetto di un numero senza
    unita': «alle 17» di quale fuso? E' la regola che `strumenti._istante`
    applica gia' in ingresso, applicata qui in uscita.
    """
    zona = _zona(fuso)
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
_NOTA_NESSUNA_REGISTRAZIONE = (
    "Home Assistant non ha registrazioni per questa entita' in questa "
    "finestra: potrebbe essere esclusa dalla registrazione (in quel caso non "
    "ne restera' mai), oppure non esistere piu'."
)
_NOTA_FASCE = (
    "valori a fasce orarie (minimo, massimo, media di ogni ora), non le "
    "singole misure: la finestra chiesta e' piu' lunga di un giorno."
)


async def andamento(*, ha, entita: str, ore, unita: str | None,
                    ha_statistiche: bool, adesso_ts: float,
                    fuso: str | None) -> dict:
    """Un valore nel tempo, con la grana e la finestra DAVVERO coperte.

    Ritorna `{"entita", "grana", "unita", "finestra_chiesta_ore",
    "finestra_coperta", "punti", "nota"}`, oppure `{"entita", "errore"}` --
    mai `punti: []` per un guasto (spec §3.3).

    **La finestra coperta si misura dai dati tornati**, non si deduce da
    `purge_keep_days`: quel valore non e' leggibile da nessuna API di Home
    Assistant, e una costante scritta qui sarebbe un'assunzione che questa
    casa puo' smentire in silenzio.
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
        da_ts = _epoch(da_iso) or 0.0
        fasce = [f for f in esito["serie"].get(entita, [])
                 if (_epoch(f.get("inizio")) or 0.0) >= da_ts]
        return {**base, "grana": "oraria",
                "finestra_coperta": _coperta(fasce, "inizio", a_iso),
                "punti": fasce[-MAX_PUNTI_IN_RISPOSTA:],
                "nota": _NOTA_FASCE if fasce else _NOTA_NESSUNA_REGISTRAZIONE}

    esito = await ha.storico([entita], da_iso, a_iso)
    if "serie" not in esito:
        return {**base, "errore": esito.get("errore", "storico non disponibile")}
    punti = esito["serie"].get(entita, [])
    if not punti:
        return {**base, "grana": "dettaglio", "finestra_coperta": None,
                "punti": [], "nota": _NOTA_NESSUNA_REGISTRAZIONE}
    nota = None
    if len(punti) == 1:
        nota = _NOTA_MAI_CAMBIATO
    ridotti = punti
    if len(punti) > MAX_PUNTI_IN_RISPOSTA:
        ridotti = _assottiglia(punti, MAX_PUNTI_IN_RISPOSTA)
        # Il numero VERO, non «molti»: e' cio' che permette a chi legge di
        # capire che sta guardando un campione e non l'elenco intero.
        nota = (f"{len(punti)} cambi nella finestra, ridotti a "
                f"{len(ridotti)} punti distribuiti nel tempo.")
    return {**base, "grana": "dettaglio",
            "finestra_coperta": _coperta(punti, "quando", a_iso),
            "punti": ridotti, "nota": nota}


def _epoch(grezzo) -> float | None:
    """Un ISO-8601 col fuso -> epoch. `None` se non si legge o se il fuso manca.

    Un istante SENZA fuso viene rifiutato invece di essere letto come locale:
    «alle 17» di quale fuso? E' la stessa regola dell'unita' di misura
    applicata al tempo, gia' scritta in `strumenti._istante` per gli istanti
    in INGRESSO -- questa e' la sua gemella per quelli che arrivano da Home
    Assistant.
    """
    if not isinstance(grezzo, str) or not grezzo.strip():
        return None
    try:
        momento = datetime.fromisoformat(grezzo.strip())
    except ValueError:
        return None
    return None if momento.tzinfo is None else momento.timestamp()


def _coperta(punti: list[dict], chiave: str, a_iso: str) -> dict | None:
    """La finestra che i dati coprono DAVVERO -- dal primo istante tornato.

    `da` si riscrive nel fuso di `a`: le statistiche tornano in UTC e la
    finestra nasce nel fuso della casa, e due estremi della STESSA finestra
    con due offset diversi sono la fondamenta 3 rotta dentro un dizionario di
    due chiavi. Se l'istante non si legge si restituisce com'e' arrivato --
    meglio un formato inatteso che un istante inventato.
    """
    if not punti:
        return None
    grezzo = punti[0].get(chiave)
    quando = _epoch(grezzo)
    if quando is None:
        return {"da": grezzo, "a": a_iso}
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
    passo = (len(punti) - 1) / (quanti - 1)
    scelti = [punti[int(round(i * passo))] for i in range(quanti)]
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
    if cronaca is not None:
        try:
            atti = cronaca.elenca(da_ts=adesso_ts - ore_vere * 3600,
                                  a_ts=adesso_ts, entita=entita)
        except Exception as errore:
            # L'attribuzione e' un di piu': un archivio che non risponde non
            # deve togliere all'utente la risposta sulla casa.
            logger.warning("cronaca illeggibile durante «accaduto» (%s: %s)",
                           type(errore).__name__, errore)
            atti = []
    voci = [_abbina(v, atti) for v in esito["voci"]]
    note = []
    if esito.get("troncato"):
        note.append("le voci piu' vecchie della finestra non sono in questo elenco.")
    if ore_vere < ore:
        note.append(f"il diario copre al piu' {int(ore_vere)} ore, non le "
                    f"{int(ore)} chieste.")
    return {"voci": voci, "troncato": bool(esito.get("troncato")),
            "ore": int(ore_vere), "nota": " ".join(note) or None}


def _abbina(voce: dict, atti: list[dict]) -> dict:
    """La voce del diario, piu' l'atto di HIRIS che PROBABILMENTE l'ha causata."""
    quando = _epoch(voce.get("quando"))
    if quando is None:
        return voce
    entita_voce = voce.get("entita")
    for atto in atti:
        if entita_voce and entita_voce not in (atto.get("entita") or []):
            continue
        if abs(float(atto.get("quando_ts") or 0.0) - quando) > TOLLERANZA_ABBINAMENTO_S:
            continue
        return {**voce, "per_mano_di": "HIRIS", "abbinamento": "probabile",
                "atto": {"id": atto.get("id"), "origine": atto.get("origine"),
                         "servizio": atto.get("servizio")}}
    return voce
