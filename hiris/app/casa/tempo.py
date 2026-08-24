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
    """
    try:
        numero = float(grezzo)
    except (TypeError, ValueError):
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
