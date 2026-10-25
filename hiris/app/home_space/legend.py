"""La legenda: come si legge una risposta di `search` e di `history`, detto
nella risposta stessa (Fase 2 dello sprint «Il giro snello», approvata da
Paolo il 25/10/2026).

Fino ad allora queste frasi stavano nelle descrizioni dei due strumenti, e
partivano a ogni giro anche quando lo strumento non si chiamava, o si chiamava
e la chiave non usciva. Per la fondamenta 1 chi riceve un valore deve poterlo
leggere da solo: la frase viaggia con la risposta, e solo per le chiavi che
quella risposta porta davvero. Una risposta senza `grana` non parla di fasce.

**Qui stanno solo le chiavi che non si leggono da se'.** Quelle il cui valore
e' gia' una frase (`troncata`, `nessuna_registrazione.perche`,
`cronaca_non_letta`, `conservate`, `consumato_non_calcolato`, la `nota` delle
escluse, il `suggerimento` di `oltre`) non hanno una riga: ripeterle sarebbe
il doppione che questa tabella esiste per togliere. Una frase che sta qui non
sta anche in una descrizione: lo prova `tests/test_legenda.py`.

**Dove si guarda**: le chiavi in cima alla risposta, quelle di `soggetto`, di
ogni riga di `voci` e dei `punti` di una riga. Non piu' in fondo: dentro la
scheda di un'entita' la stessa parola puo' voler dire altro (`membri` porta
il suo `non_letti`, che sono i membri di un gruppo).
"""
from __future__ import annotations

#: Chiave -> come si legge. Una chiave il cui significato dipende dal valore
#: (`grana`) ha una riga per valore, scritta `(chiave, valore)`.
READINGS: dict[str | tuple[str, str], str] = {
    ("grana", "oraria"): ("fasce di un'ora, non istanti: di' «fra le 14 e le 15», "
                          "non «alle 14»"),
    ("grana", "dettaglio"): "i cambi veri, uno per uno, come Home Assistant li ha registrati",
    ("grana", "per serie"): "le serie hanno grane diverse: ogni riga dice la sua",
    "dal": ("su una riga: quella serie, o le esecuzioni conservate, cominciano dopo "
            "l'inizio della finestra, e i conti partono da li'"),
    "al": ("su una riga a fasce: le fasce finiscono li', perche' l'ora in corso Home "
           "Assistant non l'ha ancora compilata"),
    "ore_senza_valore": "le ore senza un numero (per esempio unavailable), fuori dalla media",
    "cambio": "il consumo di quell'ora",
    "a_fine_ora": "la lettura alla fine di quell'ora",
    "somma": "il totale da quando Home Assistant conta",
    "per_mano_di": ("probabile, non certo: un mio atto nello stesso istante. Dillo come "
                    "probabile; su un cambio senza, chi sia stato non lo so"),
    "guasto": "l'errore con cui l'esecuzione si e' fermata",
    "non_letti": "chi non ho potuto leggere: non vuol dire «mai partita»",
    "non_lette_in_tutto": "le non lette contate su tutte le pagine, non solo su questa",
    "volte": ("una causa sola ricomparsa N volte, non N episodi. Il registro tiene poche "
              "voci e si svuota a ogni riavvio: un'assenza non prova niente"),
    "messaggio": ("arriva sigillato: i segreti che conosco sono `<secret nome>`, e il testo "
                  "che somiglia a un'istruzione e' filtrato"),
    "fuori": ("la voce esiste, ma non e' fra le visibili (`classe` dice perche'): non "
              "proporla di tua iniziativa; se la domanda la riguarda, usala e dillo"),
    "nulla_riconosciuto": ("nessun nome combacia: MAI «la cosa non esiste» -- segui il "
                           "`suggerimento`"),
    "stato_non_letto": ("gli stati non si sono potuti leggere: uno `stato` vuoto non dice "
                        "niente della casa"),
}


def _keys(answer: dict) -> list[tuple[str, object]]:
    """Le coppie (chiave, valore) dove si guarda, nell'ordine in cui si
    leggono."""
    pairs = list(answer.items())
    subject = answer.get("soggetto")
    if isinstance(subject, dict):
        pairs += subject.items()
    for row in answer.get("voci") or ():
        if not isinstance(row, dict):
            continue
        pairs += row.items()
        for point in row.get("punti") or ():
            if isinstance(point, dict):
                pairs += point.items()
    return pairs


def legend(answer: dict) -> dict[str, str]:
    """Le righe di `READINGS` per le chiavi che `answer` porta, una volta
    ciascuna. Per una chiave che ha righe per valore, quella del valore che
    esce; due valori diversi danno due frasi, unite."""
    out: dict[str, str] = {}
    for key, value in _keys(answer):
        reading = READINGS.get(key)
        if reading is None and isinstance(value, str):
            reading = READINGS.get((key, value))
        if reading is None or reading in out.get(key, ""):
            continue
        out[key] = f"{out[key]}; {reading}" if key in out else reading
    return out


def with_legend(answer: dict) -> dict:
    """`answer` con la sua `legenda` in fondo, se una chiave ne ha bisogno.
    Una risposta con `errore` resta com'e': non c'e' niente da leggere."""
    if not isinstance(answer, dict) or "errore" in answer:
        return answer
    found = legend(answer)
    return {**answer, "legenda": found} if found else answer
