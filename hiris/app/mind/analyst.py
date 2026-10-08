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

import time as _time

from ..home_space.house import ENDED_SOURCE_STATES
from .scope import ANALYST, OWNER

#: Quanti giorni di storia servono per parlare di scostamento. **Due punti non
#: sono una storia**, e un numero calcolato su due giorni con la faccia di uno
#: calcolato su trenta e' il difetto che questo prodotto vieta. Tre e' il
#: minimo perche' sotto non esiste nemmeno una mediana che significhi qualcosa.
#: **Non e' una soglia di giudizio** -- quelle la spec le vieta -- e' il punto
#: sotto il quale il conto non si puo' fare affatto.
MINIMUM_HISTORY = 3


#: Le chiavi che fanno l'IDENTITA' di un'osservazione -- e quindi della domanda
#: che l'attuatore ne fa, e della proposta che ne nasce: chi, cosa si misura, quale
#: chiave dentro la misura, e con quale innesco. **I numeri non ci stanno**: se
#: ci stessero, ogni giorno sarebbe una domanda nuova e una proposta rifiutata
#: ieri tornerebbe oggi con la stessa faccia.
_IDENTITY = ("soggetto", "misura", "chiave", "innesco")

#: Cio' che rende una prova **diversa** da quella contro cui il proprietario ha
#: deciso: su quanti giorni si regge (`base`), quanto si stacca
#: (`quanti_scarti`), e se nel frattempo qualcuno l'ha spiegata. Cambiano
#: questi, la domanda si riapre (spec §4); non cambia niente, tace.
#:
#: **Non a tempo**: il tempo non e' una prova, e riproporre la stessa cosa con
#: gli stessi dati e' insistere, non informare. E' la stessa regola che il
#: sapere usa per i rifiuti delle ricette -- «un rifiuto vale finche' vale il
#: registro contro cui e' stato deciso».
_EVIDENCE = ("base", "quanti_scarti", "spiegato")


def observation_key(observation: dict) -> str:
    """L'impronta identitaria di un'osservazione dell'analista."""
    return "|".join(str(observation.get(name)) for name in _IDENTITY)


def evidence_of(observation: dict) -> dict:
    """La forza della prova su cui quella domanda si regge, adesso."""
    return {name: observation.get(name) for name in _EVIDENCE}


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


def index(series: dict) -> list[tuple[int, dict]]:
    """L'**indice** della domanda (D2 del piano degli attori, 06/10/2026):
    una riga per misura, `(numero, riga)`, coi numeri che il codice ha gia'
    calcolato e **nessun valore della serie**.

    Il numero e' la posizione della misura in `series["serie"]`, la chiave con
    cui il modello se ne riferisce (`analyst_turn.apply_analysis`): l'indice
    cambia l'ordine in cui le righe si leggono, non la loro chiave.

    **In ordine, e nessuna manca** (D3). Prima le misure con lo scostamento
    calcolato, dalla piu' lontana dalla sua storia; poi le altre, nell'ordine
    stabile della serie. Ordinare non e' una soglia; tagliare lo sarebbe, e
    non si taglia: una misura con due giorni di storia e' una riga come le
    altre, coi suoi numeri.
    """
    days = list(series.get("giorni") or [])
    rows = list(series.get("serie") or [])

    def _order(pair):
        number, row = pair
        spread = (row.get("scostamento") or {}).get("quanti_scarti")
        if spread is None:
            return (1, 0.0, number)
        return (0, -abs(spread), number)

    return [(number, index_row(row, days))
            for number, row in sorted(enumerate(rows), key=_order)]


def index_row(row: dict, days: list[str]) -> dict:
    """Una riga dell'indice: chi e' la misura, i numeri di `with_deviation`,
    la copertura riassunta, la causa se oggi non si calcola, e i fatti che la
    rendono candidata a ciascun innesco (`trigger_facts`)."""
    deviation = row.get("scostamento") or {}
    values = list(row.get("valori") or [])
    out = {"nome": row.get("nome"), "misura": row.get("misura"),
           "chiave": row.get("chiave"), "unita": row.get("unita"),
           "ultimo": deviation.get("ultimo"), "mediana": deviation.get("mediana"),
           "scarto": deviation.get("scarto"), "base": deviation.get("base"),
           "quanti_scarti": deviation.get("quanti_scarti"),
           "copertura": coverage_summary(row.get("coperture") or []),
           "giorni_con_valore": sum(v is not None for v in values)}
    if deviation.get("non_calcolabile"):
        out["non_calcolabile"] = deviation["non_calcolabile"]
    cause = cause_today(row, days)
    if cause is not None:
        out["causa_oggi"] = cause
    out["inneschi"] = trigger_facts(row, days)
    return out


def coverage_summary(coverages: list):
    """La copertura dei giorni, riassunta: `"piena"` quando ogni giorno con la
    misura l'ha avuta intera, altrimenti l'ultima, la minima e la mediana.
    `None` se nessun giorno ne porta una."""
    known = [c for c in coverages if c is not None]
    if not known:
        return None
    if all(c == 1.0 for c in known):
        return "piena"
    return {"ultima": known[-1], "minima": min(known), "mediana": _median(known)}


def cause_today(row: dict, days: list[str]) -> dict | None:
    """Perche' l'ultimo giorno la misura non ha valore: il tratto di `perche`
    che lo comprende (`{dal, ragione, causa}`), o `None` se un valore c'e' o
    se il resoconto non ha detto perche'."""
    values = row.get("valori") or []
    if not days or not values or values[-1] is not None:
        return None
    for run in row.get("perche") or []:
        if isinstance(run, dict) and run.get("al") == days[-1]:
            return {"dal": run.get("dal"), "ragione": run.get("ragione"),
                    "causa": run.get("causa")}
    return None


def trigger_facts(row: dict, days: list[str]) -> list[dict]:
    """I fatti che rendono la misura candidata a un innesco (D3): il codice li
    marca, il modello sceglie fra loro. `[{innesco, fatto}]`, vuoto quando non
    ce n'e' nessuno.

    1. lo scostamento si calcola (il fatto e' `quanti_scarti`, che la riga
       porta gia': si nomina, non si ricopia), o la storia e' identica
       tutti i giorni e l'ultimo no;
    2. la storia non varia mai, e l'ultimo giorno nemmeno;
    3. l'ultimo giorno non si calcola e un giorno prima si', o la copertura
       dell'ultimo giorno e' diversa da quella del giorno prima.

    Nessuna soglia: ogni scostamento calcolato e' un fatto, e l'indice lo
    ordina (`index`).
    """
    deviation = row.get("scostamento") or {}
    facts: list[dict] = []
    last = deviation.get("ultimo")
    numeric = isinstance(last, (int, float)) and not isinstance(last, bool)
    if deviation.get("quanti_scarti") is not None:
        facts.append({"innesco": 1, "fatto": "quanti_scarti"})
    elif (numeric and (deviation.get("base") or 0) >= MINIMUM_HISTORY
          and deviation.get("scarto") == 0):
        if last != deviation.get("mediana"):
            facts.append({"innesco": 1, "fatto": "la storia e' identica tutti i "
                          "giorni e l'ultimo giorno no"})
        else:
            facts.append({"innesco": 2, "fatto": "non varia mai nella sua storia"})

    values = list(row.get("valori") or [])
    if values and values[-1] is None:
        before = [i for i, v in enumerate(values[:-1]) if v is not None]
        if before:
            facts.append({"innesco": 3, "fatto": "l'ultimo giorno non si calcola; "
                          f"l'ultimo valore e' del {days[before[-1]]}"})
    coverages = list(row.get("coperture") or [])
    if len(coverages) >= 2 and None not in coverages[-2:] \
            and coverages[-1] != coverages[-2]:
        facts.append({"innesco": 3, "fatto": "la copertura e' passata da "
                      f"{coverages[-2]} a {coverages[-1]} nell'ultimo giorno"})
    return facts


#: Le due risposte alla domanda «l'ha gia' detta?» (D4 del piano degli
#: attori, 06/10/2026). Le scrive il codice (`novelty`), non il modello: se
#: un'impronta e' in memoria lo sanno gli archivi, e chiederlo al modello
#: sarebbe ricopiare un fatto che possiamo leggere (giro 12 del revisore,
#: G12-2; la lezione del 22/09, «il NUMERO, non il nome»).
NOVELTY = ("nuova", "prova cambiata")


def previous_observations(analyses, proposals, *, today: str,
                          series: dict | None = None) -> list[dict]:
    """La **memoria** dell'analista, ricavata dagli archivi (D4): nessuna
    tabella nuova, riferimenti per impronta, mai copie.

    `analyses` sono le analisi archiviate (`MindStore.analyses`, la finestra
    `ANALYST_DAYS` del giro), `proposals` le proposte (`MindStore.proposals`).
    Torna una voce per impronta, in ordine dalla piu' recente: chi e' la
    misura, l'innesco, i giorni in cui e' stata detta, cosa e' stato detto
    l'ultima volta, la prova di allora e l'esito della proposta che ne e'
    nata, se c'e'. Se la misura e' ancora nella serie di oggi, `quale` e' il
    suo numero.

    L'analisi di `today` non e' memoria: e' quella che si sta riscrivendo.
    """
    numbers = {}
    for number, row in enumerate((series or {}).get("serie") or []):
        numbers[(row.get("soggetto"), row.get("misura"), row.get("chiave"))] = number
    outcomes: dict[str, dict] = {}
    for proposal in proposals or []:
        key = proposal.get("impronta")
        if key and key not in outcomes:
            outcomes[key] = {"stato": proposal.get("stato"),
                             "nota": proposal.get("esito_nota")}
    by_key: dict[str, dict] = {}
    ordered = sorted((a for a in analyses or [] if a.get("giorno") != today),
                     key=lambda a: str(a.get("giorno") or ""), reverse=True)
    for analysis in ordered:
        for observation in analysis.get("osservazioni") or []:
            if not isinstance(observation, dict):
                continue
            key = observation_key(observation)
            seen = by_key.get(key)
            if seen is not None:
                seen["giorni"].append(analysis.get("giorno"))
                continue
            entry = {"impronta": key, "nome": observation.get("nome"),
                     "misura": observation.get("misura"),
                     "chiave": observation.get("chiave"),
                     "innesco": observation.get("innesco"),
                     "giorni": [analysis.get("giorno")],
                     "cosa": observation.get("cosa"),
                     "prova": evidence_of(observation),
                     "esito": outcomes.get(key)}
            where = (observation.get("soggetto"), observation.get("misura"),
                     observation.get("chiave"))
            if where in numbers:
                entry["quale"] = numbers[where]
            by_key[key] = entry
    return list(by_key.values())


def novelty(observation: dict, previous: list[dict]) -> str | None:
    """Se un'osservazione e' nuova, ricavato dalla memoria: «nuova» se la sua
    impronta non e' mai stata detta, «prova cambiata» se e' stata detta con
    una prova diversa, `None` se e' **gia' detta con la stessa prova**.

    Il `None` non rifiuta l'analisi: chi chiama toglie quella sola
    osservazione, come `proposer_turn.open_observations` toglie cio' che e' gia' deciso.
    Rifiutare tutto faceva perdere le altre osservazioni del giorno, e la
    domanda dopo era identica: su una misura che non varia mai (innesco 2)
    fino a ventiquattro turni a vuoto (giro 12 del revisore, eseguito).
    """
    key = observation_key(observation)
    said = next((p for p in previous or [] if p.get("impronta") == key), None)
    if said is None:
        return NOVELTY[0]
    if said.get("prova") == evidence_of(observation):
        return None
    return NOVELTY[1]


#: Cosa e' successo a una richiesta di **rimetti dentro** (D9). Stanno
#: nell'analisi archiviata accanto alla richiesta, perche' chi la rilegge
#: sappia cosa ne e' stato senza confrontarla con lo scope di adesso.
BACK_IN = "rientrata"
ALREADY_INSIDE = "gia_dentro"
BACK_IN_REFUSED = "rifiutata"

#: La ragione di un rifiuto che non viene dallo scope ma dalla casa (N65-2):
#: l'id chiesto e' ben scritto, ma ne' il registro ne' gli stati lo
#: conoscono (`House.source` -> `None`). Scriverlo dentro farebbe una riga
#: «decisa dall'analista» che nessun evento accendera' mai.
NOT_IN_HOUSE = "la casa non ha questa entita'"

#: La ragione quando la casa non si e' potuta guardare per intero (G74-1,
#: giro 74 del revisore): «non c'e'» si puo' dire solo con l'anagrafe letta
#: (un'anagrafe mai letta e' `{}`, `reader.py`) E lo specchio leggibile --
#: senza il primo non si conosce il registro, senza il secondo le entita'
#: che vivono solo negli stati (`sun`, `zone`, `conversation`, senza
#: `unique_id`). Il rifiuto si scrive con la ragione vera, e lo scope non si
#: tocca: la prossima analisi puo' chiedere di nuovo.
HOUSE_UNREAD = "la casa non si e' potuta leggere"


def _house_readable(house) -> bool:
    """Se la casa di adesso basta per dire che un'entita' non c'e'."""
    return bool(house.home_space) and house.mirror.readable


def source_ended(state: str) -> str:
    """La ragione di un rifiuto per una fonte finita: l'entita' c'e' nel
    registro, ma Home Assistant non ne parla piu' -- spenta dal proprietario,
    spenta da Home Assistant o sparita dagli stati (`ENDED_SOURCE_STATES`).
    Porta lo stato di `House.source`, col suo nome, perche' la ragione si
    legga da sola."""
    return f"Home Assistant non ne parla piu': {state}"

#: I motivi di ripiego del proprietario, quando dalla pagina toglie o rimette
#: senza scrivere perche'. `store.decide_scope` non scrive una decisione senza
#: motivo; il campo della pagina e' facoltativo, quindi il ripiego vive qui,
#: una volta sola. In terza persona: lo rilegge anche l'analista.
OWNER_REMOVED = "tolto dal proprietario"
OWNER_BROUGHT_BACK = "rimesso dentro dal proprietario"

_AUTHOR_NAME = {OWNER: "il proprietario", ANALYST: "l'analista"}


def bring_back(store, analysis: dict, house, *, when_ts: float | None = None) -> dict:
    """Scrive il **rimetti dentro** dell'analista (D9), e torna l'analisi con
    l'esito di ogni richiesta accanto.

    L'analista ha in mano cio' che l'osservatore non aveva -- come la casa si
    e' comportata -- e puo' far rientrare cio' che l'osservatore ha lasciato
    fuori: scrive con autore `ANALYST`, e `scope.may_overwrite` (dentro
    `store.decide_scope`) lascia fuori cio' che ha tolto il proprietario.
    **Quel rifiuto si scrive con la ragione**: un'analisi che ha chiesto e non
    dice cosa ne e' stato sembrerebbe ascoltata.

    Cio' che e' gia' dentro non si riscrive: il motivo, l'autore e il «dal ...»
    della pagina restano di chi l'ha deciso.

    La forma della richiesta l'ha gia' validata `analyst_turn._back_in`
    (`id` di entita', `perche` non vuoto). **Che la casa l'abbia lo dice
    `house`, la casa di adesso** (N65-2, 07/10/2026): come l'osservatore
    accetta solo cio' che era nella domanda (`observer.apply_answer`, `known`),
    l'analista rimette solo cio' che il registro o gli stati conoscono
    (`House.source`). Un id che la casa non ha esce `rifiutata` con la
    ragione, e lo scope non si tocca. **Lo stesso per una fonte finita**
    (`ENDED_SOURCE_STATES`: disabilitata o sparita dagli stati): e' nel
    registro, ma non avra' mai uno stato, e dentro sarebbe la stessa riga che
    non si accende mai. Ma «non c'e'» si dice solo di una casa letta: con
    l'anagrafe o lo specchio non letti la ragione e' `HOUSE_UNREAD` (G74-1).
    """
    asked = analysis.get("rimetti") or []
    if not asked:
        return analysis
    now = float(when_ts if when_ts is not None else _time.time())
    outcomes = []
    for item in asked:
        subject, why = item["id"], item["perche"]
        standing = store.decision(subject)
        source = house.source(subject)
        if source is None:
            outcomes.append({**item, "esito": BACK_IN_REFUSED,
                             "ragione": (NOT_IN_HOUSE if _house_readable(house)
                                         else HOUSE_UNREAD)})
        elif source["stato"] in ENDED_SOURCE_STATES:
            outcomes.append({**item, "esito": BACK_IN_REFUSED,
                             "ragione": source_ended(source["stato"])})
        elif standing is not None and standing["dentro"]:
            outcomes.append({**item, "esito": ALREADY_INSIDE})
        elif store.decide_scope(subject, inside=True, reason=why, author=ANALYST,
                                when_ts=now):
            outcomes.append({**item, "esito": BACK_IN})
        else:
            who = _AUTHOR_NAME.get(standing["autore"], standing["autore"])
            outcomes.append({**item, "esito": BACK_IN_REFUSED,
                             "ragione": f"l'ha tolta {who}: «{standing['motivo']}»"})
    return {**analysis, "rimetti": outcomes}
