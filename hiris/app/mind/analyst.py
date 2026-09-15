"""L'**analista** (spec §10): la meta' che il codice sa fare.

*«Il codice calcola, il modello sceglie.»* Qui vive solo la prima meta' --
valore, storia, scostamento, copertura -- e cosa merita di essere detto lo
decide il modello. Questo modulo non lo sa, e **non deve saperlo**: e' lo
stesso schema delle ricette, un meccanismo solo per due problemi.

## Perche' lo scostamento sta qui e non nel registro

Il registro delle operazioni (`mind/operations.py`) e' il vocabolario delle
**ricette**: legge le ore di un giorno e produce la misura di quel giorno.
Lo scostamento legge **molti giorni** della stessa misura -- un altro strato, e
un'altra forma. Metterlo nel registro lo offrirebbe al modello come se una
ricetta potesse scriverlo, che e' esattamente la trappola gia' pagata il
14/09/2026 con `episodio`.

## Le due regole della spec, e come si rispettano

***«Non si inventa una soglia: si archivia e si interpreta»*** -- qui non c'e'
nessun numero scelto da noi contro cui confrontare: si confronta con cio' che
quel dato ha fatto finora, e **non si classifica**. «Alto», «anomalo»,
«preoccupante» non compaiono: escono i numeri, e sceglie il modello.

***«Con 28 giorni di storia va detto che la base e' sottile»*** -- `base` c'e'
sempre, anche quando lo scostamento si calcola benissimo: e' un numero da
consegnare, non una soglia da applicare.
"""
from __future__ import annotations

#: Quanti giorni di storia servono per parlare di scostamento. **Due punti non
#: sono una storia**, e un numero calcolato su due giorni con la faccia di uno
#: calcolato su trenta e' il difetto che questo prodotto vieta. Tre e' il
#: minimo perche' sotto non esiste nemmeno una mediana che significhi qualcosa.
#: **Non e' una soglia di giudizio** -- quelle la spec le vieta -- e' il punto
#: sotto il quale il conto non si puo' fare affatto.
MINIMUM_HISTORY = 3


def with_deviation(series: dict) -> dict:
    """La stessa serie, con lo **scostamento** dell'ultimo valore su ogni riga.

    Non riscrive niente: aggiunge una chiave. I valori, le coperture e i buchi
    restano quelli che erano, o due letture della stessa storia direbbero cose
    diverse.
    """
    rows = []
    for row in series.get("serie") or []:
        rows.append({**row, "scostamento": _deviation(row.get("valori") or [])})
    return {**series, "serie": rows}


def _deviation(values: list) -> dict:
    """Quanto l'ultimo valore si discosta dalla **sua** storia.

    Torna `{ultimo, mediana, scarto, quanti_scarti, base}`, e
    `non_calcolabile` con la ragione quando il conto non si puo' fare.

    **Mediana e scarto assoluto mediano, non media e deviazione standard.** Con
    venti punti un solo giorno storto sposta la media e nasconde tutto il
    resto; la mediana regge. E' la stessa dottrina del registro: si sceglie la
    forma che non mente quando i dati sono pochi.

    **Se la storia non varia mai, lo scostamento non si calcola -- e quel
    rifiuto E' il secondo innesco.** Lo scarto e' zero, e qualunque differenza
    diviso zero sarebbe un numero inventato. Ma *«questa cosa non varia mai»* e'
    precisamente cio' che la spec chiede di notare: la batteria satura al 90%
    dalle 13 alle 16 mentre l'impianto produce ancora 3.000 W -- nessuna
    variazione, e il costo piu' alto di tutta la prova. Un analista che
    guardasse solo cio' che cambia non lo troverebbe mai.
    """
    last = values[-1] if values else None
    history = [v for v in values[:-1] if isinstance(v, (int, float))
               and not isinstance(v, bool)]
    out: dict = {"ultimo": last, "mediana": None, "scarto": None,
                 "quanti_scarti": None, "base": len(history)}

    if not isinstance(last, (int, float)) or isinstance(last, bool):
        out["non_calcolabile"] = (
            "l'ultimo valore non e' un numero: non si puo' sottrarre da una "
            "storia")
        return out
    # **La mediana si calcola comunque**, anche su una storia troppo corta: e'
    # cio' che si sa, e «la base e' sottile» e' un numero da consegnare al
    # modello, non una ragione per tacere.
    if history:
        middle = _median(history)
        out["mediana"] = middle
        out["scarto"] = _median([abs(v - middle) for v in history])

    if len(history) < MINIMUM_HISTORY:
        out["non_calcolabile"] = (
            f"la storia e' di {len(history)} giorni: sotto {MINIMUM_HISTORY} "
            "non c'e' niente da cui discostarsi")
        return out

    middle = out["mediana"]
    spread = out["scarto"]
    if not spread:
        # **Due fatti diversi, e confonderli direbbe il contrario di quello
        # che e' successo.** Lo scarto e' zero in tutti e due i casi, e in
        # tutti e due il numero resta non calcolabile -- dividere per zero
        # sarebbe inventarlo. Ma una storia identica che OGGI cambia e' il
        # primo innesco, il segnale piu' forte che esista; una storia identica
        # che oggi e' ancora uguale e' il secondo. Le frasi lo dicono, e
        # mediana e ultimo sono li' perche' la differenza si legga.
        if last != middle:
            out["non_calcolabile"] = (
                "la storia e' identica tutti i giorni e oggi no: non c'e' uno "
                "scarto da cui misurare, e il cambiamento e' la notizia")
        else:
            out["non_calcolabile"] = (
                "questa misura non varia mai nella sua storia: non c'e' uno "
                "scarto da cui misurare, e il fatto stesso e' la notizia")
        return out
    out["quanti_scarti"] = round((last - middle) / spread, 2)
    return out


def _median(values: list) -> float:
    """La mediana, scritta qui e non presa da `statistics`.

    Tre righe contro un import, e in cambio il conto che sta sotto un numero
    che l'analista consegnera' al modello si legge senza uscire dal file.
    """
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2
