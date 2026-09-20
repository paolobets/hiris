"""Il resoconto giornaliero: due parti, e la separazione e' funzionale.

Spec `docs/design/2026-09-10-i-tre-attori.md` §9, e la forma decisa col
proprietario il 13/09/2026.

## A cosa serve, perche' da li' viene tutto il resto

**Non e' fatto per un umano.** Serve all'**analista** (§10), che ha tre inneschi
e tutti e tre guardano NUMERI:

1. *«qualcosa e' cambiato, e non e' spiegato»* -- la stessa misura su molti
   giorni. L'autosufficienza passata dal 99,2% al 61,3% il 09/09 era il meteo:
   una conferma, non una scoperta;
2. *«qualcosa e' stabile e costa»* -- il VALORE, non lo scostamento: la batteria
   satura al 90% dalle 13 alle 16 mentre l'impianto produce ancora 3.000 W non
   varia mai, ed e' il costo piu' alto di tutta la prova. Un analista che
   guardasse solo cio' che cambia non lo troverebbe mai;
3. *«qualcosa non c'e' piu'»* -- la **copertura** e il «non calcolabile, e
   perche'» devono essere visibili come i numeri. Il caso vero: `bilancio` a
   zero per cinque giorni su cinque, e nessuno se n'e' accorto.

## Le due parti

**Le misure** si leggono **in serie**, molti giorni insieme: sono decine di
numeri, e trenta giorni ci stanno in un prompt.

**La cronaca e' un INDICE** -- quando, chi, cosa -- che l'analista scorre e da
cui poi scava: in Home Assistant se il giorno e' dentro la settimana che lui
ricorda, nel nostro grezzo fino al ventiduesimo giorno, e **dicendo quale dei
due ha usato** (vincolo della spec §10).

**Perche' un indice e non l'episodio intero**, misurato sui 200 oggetti veri
della casa il 13/09/2026: l'episodio pesa **622 byte**, l'indice **109**. Su
trenta giorni sono **521 KB contro 92** -- e con la cronaca intera l'analista
puo' guardare solo il giorno che ha gia' deciso di guardare, mentre per sapere
quale dovrebbe averlo gia' guardato.

**Ma l'indice porta un'ancora.** E' l'unico difetto irreversibile che la forma
nuda avrebbe: cio' che dopo non si recupera piu' perche' dipende da com'era la
casa **allora** -- il nome che l'entita' aveva, la sua classe, gli attributi
raccolti. Home Assistant, richiesto domani, risponde con quelli di domani: e'
la lezione gia' pagata da `friendly_name`, che si salva nel grezzo invece di
risolverlo dopo. Costa 27 byte a voce.

## Il documento

**Si deriva, non si scrive.** Se si derivasse a mano sarebbe una seconda copia
che diverge dalla prima; derivandolo, migliorare il modo di raccontare un
giorno vale anche per i giorni passati -- la stessa promessa per cui il grezzo
dura 22 giorni.

Costa **un terzo** del JSON a parita' di contenuto (misurato: 146 KB contro 46,
su trenta giorni), e le sue sezioni sono il meccanismo delle porzioni: si
consegna `## Le misure` di trenta giorni, poi `## La cronaca` del solo giorno
che e' saltato fuori.
"""
from __future__ import annotations

import logging

from ..home_space.type_vocabulary import SYSTEM_GENRE, unknown_states
from .recipes import Recipe
from .store import READING_RETENTION_S

logger = logging.getLogger(__name__)

#: Le chiavi del corpo di un episodio che entrano nell'indice: **cio' che
#: dopo non si recupera piu'**, perche' dipende da com'era la casa allora.
#:
#: `nome`, `classe` e `attributi` per un'entita'. `dominio`, `titolo` e
#: `comparso_ts` per una condizione di sistema -- aggiunti il 15/09/2026, con
#: l'uscita degli oggetti: «quale integrazione si e' rotta» viveva solo li'
#: dentro, e una voce di configurazione fra tre settimane puo' non esistere
#: piu'. E' la stessa ragione di `friendly_name`, applicata all'altro genere
#: di soggetto.
#:
#: Tutto il resto -- il clima mentre durava, il contesto ricco -- **non entra**,
#: e si va a prendere quando serve.
_ANCHOR = ("nome", "classe", "attributi", "dominio", "titolo", "comparso_ts")


def build_report(*, day: str, episodes, series: dict, recipes: dict,
                 names: dict, objective: dict | None = None,
                 without_statistics: set[str] | None = None,
                 judgment: dict | None = None) -> dict:
    """Il resoconto di un giorno: `{giorno, obiettivo, misure, forme, cronaca,
    giudizio}`.

    **Puro**: nessuna lettura di rete e nessun archivio. Le serie arrivano gia'
    lette dal chiamante, le ricette gia' lette dal sapere, gli episodi gia'
    costruiti da `facts.build_episodes` -- stessa disciplina di
    `build_balance_body`.

    Un giorno vuoto produce un resoconto vuoto, e **va scritto lo stesso**:
    «quel giorno non e' successo niente» e «quel giorno non l'abbiamo
    guardato» sono due cose diverse, e l'analista deve poterle distinguere.

    **`objective` e' la domanda a cui quel giorno risponde** (spec §11), e
    arriva gia' letta da chi chiama -- `store.objective_at(fine del giorno)`.
    Chi legge trenta giorni di misure in serie deve sapere se in mezzo la
    domanda e' cambiata, o legge una tendenza dove c'e' un cambio d'obiettivo:
    e' proprio il modo in cui l'analista le legge.

    **`None` resta `None`**: un resoconto scritto prima che questa riga
    esistesse non deve spacciare l'obiettivo di OGGI per quello di allora --
    la stessa legge gia' pagata da `friendly_name` e dall'ancora della
    cronaca.

    **`without_statistics`** porta le entita' per cui Home Assistant non tiene
    statistiche affatto (spec §6, primo «rifiuta se»): le loro misure escono
    «non calcolabile» dicendo QUELLO, invece di «la serie e' vuota». `None`
    vuol dire «non l'abbiamo potuto chiedere», e allora non si afferma niente.

    **`judgment` e' l'impronta dei giudizi con cui e' nata la cronaca**
    (`{"impronta": ...}`, spec `docs/design/2026-09-16-il-giudizio-dei-tipi.md`
    §6), gia' calcolata da chi chiama: `facts.aggregate_day` e
    `facts.rebuild_chronicle`. Come `objective`, `None` resta `None`: nessuna
    impronta inventata per una cronaca che non dice con quale giudizio e' nata.
    """
    measured, shapes = _measurements(series, recipes, names,
                                     without_statistics)
    return {"giorno": day, "obiettivo": objective, "misure": measured,
            "forme": shapes, "cronaca": [_entry(e) for e in episodes or []],
            "giudizio": judgment}


def _measurements(series: dict, recipes: dict, names: dict,
                  without_statistics: set[str] | None = None
                  ) -> tuple[list[dict], list[dict]]:
    """Le misure e le **forme**, separate: `(misure, forme)`.

    Una riga per numero, una per ogni numero che non si e' potuto fare -- col
    suo perche' -- e a parte quelle il cui risultato **non e' un numero**.

    **Perche' separate, col numero.** Misurato sulla casa vera il 14/09/2026:
    le misure di un giorno pesavano 17.399 byte, e 13.055 -- il **75%** --
    erano otto serie orarie finite dentro `valore`. La spec §9 promette che le
    misure si leggano *in serie, molti giorni insieme*, e che trenta giorni
    stiano in un prompt: con quei numeri erano **522 KB**, e non erano piu'
    decine di numeri -- erano quattro numeri e otto serie.

    Una forma oraria non e' una misura da leggere in serie: e' un **dettaglio
    del giorno**, come la cronaca, e si consegna a richiesta. Non si butta --
    il grezzo scade a 22 giorni e le statistiche di Home Assistant non tornano
    indietro all'infinito, quindi rifarla dopo non si puo'.

    **Una LISTA e' una forma; tutto il resto e' una misura** -- anche un
    dizionario di tre numeri come `{media, minimo, massimo}`: cio' che pesa
    sono le serie, non i valori composti.

    **Un rifiuto resta fra le MISURE**, anche se non ha un numero: e' dove
    l'analista guarda cio' che manca (`as_document` ne fa «cosa non si sa»), e
    spostarlo fra le forme lo nasconderebbe.
    """
    out: list[dict] = []
    shapes: list[dict] = []
    for subject in sorted(recipes or {}):
        recipe = Recipe(recipes[subject])
        base = {"soggetto": subject}
        if names.get(subject):
            base["nome"] = names[subject]
        needed = {e: series.get(e) or [] for e in recipe.entities()}
        try:
            outcomes = recipe.run(series=needed,
                                  without_statistics=without_statistics)
        except ValueError as error:
            # **Una ricetta storta non fa perdere il giorno intero.** Puo'
            # essere stata corretta male a mano, o scritta da un modello che ha
            # sbagliato: si dichiara fra cio' che non si e' potuto calcolare, e
            # le altre restano. Perdere il resoconto di tutta la casa per un
            # dispositivo sarebbe il contrario di cio' che questo strato
            # promette.
            out.append({**base, "misura": "(la ricetta)",
                          "non_calcolabile": str(error)})
            logger.warning("resoconto: ricetta non valida per %s -- %s",
                           subject, error)
            continue
        for step in recipe.steps:
            name = str(step.get("name") or "").strip()
            outcome = outcomes.get(name)
            if outcome is None:
                continue
            row = {**base, "misura": name,
                    "operazione": str(step.get("operation") or "")}
            if outcome.computable:
                row["valore"] = outcome.value
                row["unita"] = outcome.unit
                row["copertura"] = outcome.coverage
                # **Una LISTA e' una forma; tutto il resto e' una misura.**
                # Il criterio della prima stesura era «non e' un numero», e
                # sarebbe stato sbagliato: `media_min_max`, `tendenza` e
                # `confronto_periodi` tornano un dizionario di due o tre
                # numeri, e sono proprio le operazioni che rispondono a «com'e'
                # stata la temperatura» e «di quanto e' cambiato» -- il primo
                # innesco dell'analista. Mandarle fra le forme le toglieva
                # dalle misure che si leggono in serie.
                #
                # Il criterio giusto e' quello che la misura diceva dall'inizio
                # (14/09/2026): cio' che pesa sono le SERIE -- venticinque
                # punti orari, il 75% dei byte -- non il fatto che un valore
                # abbia piu' di un numero dentro.
                if isinstance(outcome.value, list):
                    shapes.append(row)
                    continue
            else:
                row["non_calcolabile"] = outcome.reason
            out.append(row)
    return out, shapes


def _entry(episode: dict) -> dict:
    """Una riga della cronaca: **quando, chi, cosa**, piu' l'ancora.

    `fine_ts` a `None` resta `None` e non sparisce: «ancora in corso» e' un
    fatto, e toglierlo lo confonderebbe con «finito subito».

    **Il genere c'e'** (dal 15/09/2026, quando gli oggetti sono usciti): e' la
    differenza fra «una porta si e' aperta» e «un'integrazione si e' rotta», e
    l'analista le trattera' in modo diverso. Costa dodici byte a voce ed e'
    gia' calcolato -- prima viveva solo nell'oggetto, e sarebbe uscito con lui.
    """
    body = episode.get("corpo_base") or {}
    entry = {"quando_ts": episode.get("inizio"), "fine_ts": episode.get("fine"),
            "chi": episode.get("protagonista"), "genere": episode.get("genere"),
            "cosa": body.get("stato")}
    for key in _ANCHOR:
        if body.get(key) is not None:
            entry[key] = body[key]
    return entry


# -- le misure IN SERIE ------------------------------------------------------


def series_of_measures(reports, names: dict | None = None) -> dict:
    """I resoconti pivotati: **una riga per misura**, coi suoi valori nei giorni.

    Torna `{"giorni": [...], "obiettivi": [...], "serie": [{soggetto, nome,
    misura, chiave, operazione, unita, valori, coperture, perche}]}`.

    **Perche' esiste, col numero.** Misurato sulla casa vera il 15/09/2026 sui
    venti giorni archiviati: i resoconti **come sono**, portati a trenta
    giorni, pesano ~47.600 token -- quattro volte il giro dell'osservatore,
    ogni giorno. Pivotati per misura: **~6.700**. Sette volte meno, perche' il
    soggetto, l'operazione e l'unita' si scrivono una volta invece di trenta.

    E non e' un'ottimizzazione: e' la frase della spec §9 presa alla lettera --
    *«le misure si leggono in serie, molti giorni insieme»* -- ed e' l'unica
    forma su cui si puo' calcolare cio' che l'analista deve calcolare: *«lo
    scostamento contro la storia di quel dato, non contro una soglia
    inventata»* (§10).

    **Un valore composto diventa PIU' serie, non una scelta nascosta.**
    `media_min_max` torna `{media, minimo, massimo}`: mettere in serie «la
    media» sarebbe una regola che nessuno ha dichiarato, e sarebbe sbagliata --
    media, minimo e massimo sono tre storie diverse, e «il massimo di rumore e'
    salito» vale quanto «la media e' salita». Ogni chiave prende la sua riga,
    e `chiave` dice quale; per un valore gia' numerico `chiave` e' `None`.

    **Un giorno senza quella misura resta un BUCO, non sparisce.** E' il terzo
    innesco: «la copertura crolla», «una misura smette di essere calcolabile».
    Il caso vero e' `bilancio` a zero per cinque giorni su cinque, e nessuno
    se n'e' accorto. Il posto nella serie resta col suo `None`, e quando il
    resoconto diceva **perche'** quel perche' si conserva.

    **I giorni senza valore si raccolgono in tratti** (`{dal, al, ragione}`),
    non uno per giorno: vedi `_runs`, col numero che lo giustifica.

    **Ordine stabile**, per soggetto e misura: due letture della stessa storia
    devono dare lo stesso ordine, o un modello che le rilegge vedrebbe un
    cambiamento dove non c'e'.
    """
    ordered = sorted(reports or [], key=lambda r: str(r.get("giorno") or ""))
    days = [str(r.get("giorno") or "") for r in ordered]
    index = {day: i for i, day in enumerate(days)}

    # **Due passate, e la prima serve.** Quali chiavi ha una misura lo dice il
    # giorno in cui si e' calcolata, e un giorno in cui ha rifiutato non lo sa:
    # con una passata sola, `co2` (che si calcola il 13 e rifiuta il 12)
    # produrrebbe QUATTRO serie -- media, minimo, massimo, e una quarta senza
    # chiave col perche' staccato dai valori. Il rifiuto va su tutte e tre:
    # quel giorno mancano tutte e tre, e chi guarda la storia del massimo deve
    # vedere il buco nella SUA serie.
    keys: dict[tuple, list] = {}
    for report in ordered:
        for line in report.get("misure") or []:
            if not isinstance(line, dict):
                continue
            where = (line.get("soggetto"), line.get("misura"))
            for key, value in _split_value(line):
                if value is _MISSING:
                    keys.setdefault(where, [])
                    continue
                known = keys.setdefault(where, [])
                if key not in known:
                    known.append(key)

    rows: dict[tuple, dict] = {}

    def _slot(line, key):
        where = (line.get("soggetto"), line.get("misura"), key)
        found = rows.get(where)
        if found is None:
            found = {"soggetto": line.get("soggetto"), "nome": line.get("nome"),
                     "misura": line.get("misura"), "chiave": key,
                     "operazione": line.get("operazione"), "unita": line.get("unita"),
                     "valori": [None] * len(days), "coperture": [None] * len(days),
                     "perche": {}}
            rows[where] = found
        # **L'archivio dice cio' che sapeva; il lettore risolve cio' che puo'
        # oggi.** Un resoconto che il nome ce l'ha porta quello di ALLORA, ed
        # e' piu' vero di quello di adesso -- un dispositivo si puo'
        # rinominare, e la serie non riscrive il passato col presente. Ma dove
        # il nome manca (i venti giorni archiviati prima del 15/09/2026, che
        # un difetto lasciava senza) risolverlo qui non afferma niente sul
        # passato: la serie e' una VISTA, non un archivio, e all'analista
        # arriva «SOLARE · prelievo» invece di «513a6661 · prelievo».
        if line.get("nome"):
            found["nome"] = line.get("nome")
        elif found.get("nome") is None and names:
            found["nome"] = names.get(line.get("soggetto"))
        if line.get("unita") is not None:
            found["unita"] = line.get("unita")
        return found

    for report in ordered:
        day = str(report.get("giorno") or "")
        for line in report.get("misure") or []:
            if not isinstance(line, dict):
                continue
            wanted = keys.get((line.get("soggetto"), line.get("misura"))) or [None]
            for key, value in _split_value(line):
                if value is _MISSING:
                    # Il rifiuto vale per OGNI chiave di quella misura.
                    reason = line.get("non_calcolabile")
                    for each in wanted:
                        slot = _slot(line, each)
                        if reason:
                            slot["perche"][day] = reason
                    continue
                slot = _slot(line, key)
                slot["valori"][index[day]] = value
                slot["coperture"][index[day]] = line.get("copertura")

    for slot in rows.values():
        slot["perche"] = _runs(days, slot["perche"])
    ordinate = sorted(rows.values(),
                      key=lambda r: (str(r["soggetto"] or ""), str(r["misura"] or ""),
                                     _KEY_ORDER.get(r["chiave"], 9), str(r["chiave"] or "")))
    return {"giorni": days, "obiettivi": _objective_runs(ordered),
            "serie": ordinate}


def _objective_runs(reports) -> list[dict]:
    """Quando la domanda e' cambiata: un tratto per obiettivo.

    **Il vincolo della spec §11, nella forma che l'analista legge.** Senza,
    leggerebbe una tendenza dove invece e' cambiata la domanda: trenta giorni
    di «autosufficienza in calo» possono essere un impianto che peggiora o un
    obiettivo riscritto a meta'.

    Si raggruppa come i buchi, e per la stessa ragione: l'obiettivo cambia
    qualche volta all'anno, non ogni giorno, e ripeterlo trenta volte sarebbe
    la ripetizione che i `perche` hanno gia' pagato -- il 66% del peso, quando
    si misuro'.

    **Un giorno senza obiettivo dichiarato interrompe il tratto**, e non lo
    eredita da chi gli sta accanto: attribuirgli l'obiettivo del giorno dopo
    direbbe che rispondeva a una domanda che non era la sua -- la stessa legge
    dell'ancora della cronaca e di `friendly_name`.
    """
    out: list[dict] = []
    open_run: dict | None = None
    for report in reports:
        day = str(report.get("giorno") or "")
        aim = report.get("obiettivo")
        if not isinstance(aim, dict) or not aim.get("testo"):
            open_run = None
            continue
        if (open_run is not None and open_run["testo"] == aim.get("testo")
                and open_run["scritto_ts"] == aim.get("scritto_ts")):
            open_run["al"] = day
            continue
        open_run = {"dal": day, "al": day, "testo": aim.get("testo"),
                    "scritto_ts": aim.get("scritto_ts")}
        out.append(open_run)
    return out


def _runs(days: list[str], reasons: dict) -> list[dict]:
    """I giorni senza valore, raccolti in **tratti**: `{dal, al, ragione}`.

    **Misurato il 15/09/2026 sui venti giorni veri**: i `perche` erano il 66%
    del peso della serie, ed erano ripetizioni -- 36 serie ripetevano la stessa
    frase 17 volte, tre la ripetevano 20. Raggruppati: 18.150 token per trenta
    giorni invece di 44.163.

    E non e' solo il peso. «Non si calcola dal 26/08 all'11/09, per questa
    ragione» e' il terzo innesco detto bene; diciassette righe identiche lo
    seppelliscono.

    **Due ragioni diverse restano due tratti** -- raggruppare e' comprimere,
    non appiattire -- e **un buco che si riapre dopo un giorno buono e' un
    tratto nuovo**: l'analista deve vedere che la misura era tornata e se n'e'
    andata di nuovo, non un unico buco lungo che non c'e' mai stato.
    """
    out: list[dict] = []
    open_run: dict | None = None
    for day in days:
        reason = reasons.get(day)
        if reason is None:
            open_run = None
            continue
        if open_run is not None and open_run["ragione"] == reason:
            open_run["al"] = day
            continue
        open_run = {"dal": day, "al": day, "ragione": reason}
        out.append(open_run)
    return out


#: Il segnaposto di «quel giorno quella misura non aveva un valore». Non e'
#: `None`: `None` e' un valore legittimo dentro una serie gia' allineata, e
#: confonderli renderebbe indistinguibile un buco da uno zero letto davvero.
_MISSING = object()

#: L'ordine in cui le chiavi di un valore composto si leggono. Scritto, non
#: alfabetico: «media, minimo, massimo» e' come l'operazione le racconta, e
#: alfabeticamente uscirebbe «massimo, media, minimo» -- lo stesso dato, detto
#: in un ordine che nessuno userebbe parlando.
_KEY_ORDER = {"media": 0, "minimo": 1, "massimo": 2,
              "verso": 0, "pendenza": 1, "punti": 2,
              "differenza": 0, "variazione": 1}


def _split_value(line: dict):
    """Le coppie `(chiave, valore)` di una riga di misura.

    Una sola, con `chiave` a `None`, quando il valore e' gia' un numero; una
    per chiave quando e' composto; una sola col segnaposto quando quel giorno
    la misura non si e' potuta calcolare.
    """
    if "valore" not in line:
        return [(None, _MISSING)]
    value = line["valore"]
    if isinstance(value, dict):
        return [(k, value[k]) for k in sorted(
            value, key=lambda k: (_KEY_ORDER.get(k, 9), str(k)))]
    return [(None, value)]

def measured_value(line: dict) -> str:
    """Il valore di una misura **a parole**, composto o no.

    **Trovato dal vivo il 20/09/2026**, sul resoconto del 19: 36 misure su 67
    hanno un valore composto -- 23 `media_min_max` e 13 `tendenza` -- e il
    documento le stampava cosi' come sono, `{'media': 24.12, 'minimo': 23.4,
    'massimo': 24.3} °C`, dentro la tabella che l'analista legge. La regola per
    scomporle (`_split_value`, `_KEY_ORDER`) esisteva dal 13/09 ed era usata
    dalle SERIE: una regola gia' scritta che il suo vicino non chiamava.

    **L'unita' si attacca solo quando TUTTE le parti sono numeri.** `tendenza`
    porta `verso` (una parola) e `punti` (un conteggio): scriverci «°C» in
    fondo direbbe che ventiquattro punti sono ventiquattro gradi.
    """
    parts = _split_value(line)
    unit = str(line.get("unita") or "").strip()
    if len(parts) == 1 and parts[0][0] is None:
        value = parts[0][1]
        return f"{value} {unit}".strip()
    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                  for _, v in parts)
    said = " · ".join(f"{k} {v}" for k, v in parts)
    return f"{said} {unit}".strip() if numeric and unit else said


# -- il documento -----------------------------------------------------------

#: I titoli delle sezioni. Sono l'indice che l'analista scorre, e la porzione
#: che gli si puo' consegnare da sola: vivono qui in un posto solo perche'
#: `section()` li cerca per nome e un letterale ripetuto due volte sarebbe un
#: refuso che non fallisce -- restituirebbe una sezione vuota.
SEZIONE_MISURE = "Le misure"
SEZIONE_CRONACA = "La cronaca"
SEZIONE_IGNOTO = "Cosa non si sa"


def as_document(report: dict, *, current_fingerprint: str | None = None) -> str:
    """Il resoconto reso come documento, **derivato e mai scritto a mano**.

    Tre sezioni, e la terza non e' una ripetizione della prima: *«cosa non si
    sa»* e' il terzo innesco dell'analista, e in fondo a una tabella di numeri
    buoni non salterebbe all'occhio.

    **`current_fingerprint` e' l'impronta dei giudizi di adesso** (spec
    2026-09-16 §6). Quando arriva ed e' diversa da quella del resoconto -- o il
    resoconto non ne ha nessuna, perche' e' nato prima che l'impronta esistesse
    -- sotto «La cronaca» una riga lo dice. La frase vale sia per un giorno
    oltre il grezzo, che resta com'e', sia per uno recente che il recupero non
    ha ancora rifatto: questa funzione non sa quale dei due sia, e non lo
    afferma. Senza `current_fingerprint` non si afferma niente.
    """
    measurements = [m for m in report.get("misure") or [] if "valore" in m]
    unknown = [m for m in report.get("misure") or [] if "valore" not in m]
    chronicle = report.get("cronaca") or []

    lines = [f"# Resoconto del {report.get('giorno')}", ""]
    # **L'obiettivo sta in cima**, prima dei numeri: e' la domanda a cui quel
    # giorno risponde, e chi legge la serie di trenta giorni deve incontrarla
    # prima di leggere una tendenza che potrebbe essere un cambio di domanda.
    aim = (report.get("obiettivo") or {}).get("testo")
    if aim:
        lines += [f"*La domanda di quel giorno: {aim}*", ""]
    lines += [f"## {SEZIONE_MISURE}", ""]
    if measurements:
        lines += ["| chi | misura | valore | copertura |",
                  "|---|---|---|---|"]
        lines += [f"| {m.get('nome') or m['soggetto']} | {m['misura']} | "
                  f"{measured_value(m)} | {m['copertura']:.0%} |"
                  for m in measurements]
    else:
        lines.append("Nessuna misura: nessun dispositivo ha una ricetta, "
                     "oppure nessuna ha potuto calcolarsi.")
    lines.append("")

    lines += [f"## {SEZIONE_CRONACA}", ""]
    fingerprint = (report.get("giudizio") or {}).get("impronta")
    if current_fingerprint is not None and fingerprint != current_fingerprint:
        lines += [("*Questa cronaca e' raccontata con un giudizio diverso da quello "
                   "di adesso. Il recupero la rifa' finche' il grezzo di quel giorno "
                   f"c'e' tutto ({READING_RETENTION_S // 86400} giorni); oltre, resta "
                   "com'e'.*"), ""]
    if chronicle:
        lines += ["| when | chi | cosa |", "|---|---|---|"]
        for v in chronicle:
            end = v.get("fine_ts")
            when = (f"{v.get('quando_ts')}"
                      + (f" → {end}" if end is not None else " → in corso"))
            attributes = v.get("attributi") or []
            tail = f" ({len(attributes)} cambi di attributo)" if attributes else ""
            lines.append(f"| {when} | {v.get('nome') or v.get('chi')} | "
                         f"{v.get('cosa')}{tail} |")
    else:
        lines.append("Nessun fatto: quel giorno non e' cambiato niente di "
                     "cio' che si guarda.")
    lines.append("")

    if unknown:
        lines += [f"## {SEZIONE_IGNOTO}", ""]
        lines += [f"- **{m.get('nome') or m['soggetto']} · {m['misura']}**: "
                  f"{m['non_calcolabile']}" for m in unknown]
        lines.append("")
    return "\n".join(lines)


def section(document: str, title: str) -> str:
    """Una sezione sola del documento, o `""` se non c'e'.

    E' il meccanismo delle porzioni: l'analista scorre le misure di trenta
    giorni, trova il giorno, e chiede **solo la cronaca di quello**. Una
    sezione che non c'e' torna vuota e non solleva: un resoconto senza «cosa
    non si sa» e' un buon resoconto, non un errore.
    """
    opening = f"## {title}"
    if opening not in document:
        return ""
    rest = document.split(opening, 1)[1]
    end = rest.find("\n## ")
    return (opening + (rest if end == -1 else rest[:end])).strip()


# ---------------------------------------------------------------------------
# Il resoconto come lo legge la PAGINA (spec 2026-09-18 §3).
#
# `as_document` rende lo stesso archivio per un modello; qui si rende per un
# umano. Due rese, un archivio solo: e' la ragione per cui il documento si
# deriva invece di essere scritto, applicata una seconda volta.
#
# **Niente di tutto questo si salva.** La cronaca archiviata si rifa' solo
# quando cambia un giudizio, e l'impronta dice quali giorni rifare: se «esce
# dal solito» stesse nella cronaca, il giorno in cui si cambia idea su cosa
# merita il primo piano -- e si cambiera' idea -- servirebbe rifare ventidue giorni
# per una decisione che col sapere non c'entra. In lettura costa una riga.
# ---------------------------------------------------------------------------

#: Le tre sorte del primo piano, **nell'ordine in cui si leggono**. Non e'
#: l'ordine di arrivo, ed e' una decisione del proprietario: «un allarme
#: scattato e' la prima cosa da sapere; una luce accesa e' la seconda, non la
#: prima». I guasti vengono prima degli avvisi perche' il livello lo dice Home
#: Assistant, non noi.
FRONT_PAGE_ORDER = ("da_sapere_subito", "guasto", "avviso")

#: Il solo livello di Home Assistant che il primo piano declassa ad avviso
#: (`record.levelname`, maiuscolo come HA lo scrive). **Tutto il resto pesa
#: come un guasto, `CRITICAL` compreso**: un livello che non conosciamo puo'
#: portare una riga in piu' in primo piano, mai una in meno.
_WARNING_LEVEL = "WARNING"

#: I due prefissi con cui un logger di Home Assistant nomina l'integrazione da
#: cui viene: `homeassistant.components.hydrawise` -> «Hydrawise»,
#: `custom_components.alarmo.alarm_control_panel` -> «Alarmo». Il segmento
#: SUBITO DOPO il prefisso e' l'integrazione; quelli ancora dopo sono la
#: piattaforma dentro di lei, e non sono il suo nome.
_INTEGRATION_PREFIXES = ("homeassistant.components.", "custom_components.")

#: Il nucleo di Home Assistant quando il logger non nomina nessuna
#: integrazione (`homeassistant.helpers.entity`, misurato sulla casa vera il
#: 17/09/2026). **E' una citazione, non una resa**: il prodotto si chiama
#: cosi', e «Homeassistant.helpers.entity» non e' il nome di niente.
_CORE_LOGGER_PREFIX = "homeassistant."
_CORE_SLUG = "homeassistant"
_CORE_NAME = "Home Assistant"


def _integration_slug(domain: str) -> str | None:
    """Il nome breve (**`slug`**) dell'integrazione da cui viene una voce di sistema:
    `homeassistant.components.hassio.handler` -> `hassio`,
    `custom_components.hacs.x` -> `hacs`, `frontend.js.modern.202608267` ->
    `frontend`, `homeassistant.helpers.entity` -> `homeassistant`.

    **Un segmento solo, sempre**, e da qui viene tutto il resto: e' il soggetto
    su cui la casa scrive il giudizio `impalcatura`, ed e' anche cio' che il
    nome rende leggibile. Misurato il 20/09/2026: il Supervisor ha fatto sei
    righe di primo piano in una settimana da **tre logger diversi**, e il
    frontend porta nel proprio la versione del pacchetto -- un giudizio scritto
    sul percorso intero avrebbe voluto una riga per modulo, e sarebbe scaduto
    al prossimo aggiornamento di Home Assistant.
    """
    domain = str(domain or "").strip()
    if not domain:
        return None
    for prefix in _INTEGRATION_PREFIXES:
        if domain.startswith(prefix):
            found = domain[len(prefix):].split(".")[0]
            return found or None
    if domain.startswith(_CORE_LOGGER_PREFIX):
        return _CORE_SLUG
    # Una libreria di terze parti (`aioamazondevices`, `habluetooth.scanner`)
    # non e' un'integrazione di Home Assistant, ma il primo segmento e' lo
    # stesso appiglio stabile: `habluetooth.scanner` e `habluetooth.manager`
    # sono la stessa cosa per chi legge.
    return domain.split(".")[0]


def _integration_name(domain: str) -> str | None:
    """Il nome leggibile dell'integrazione da cui viene una voce di sistema.

    **Si ricava da cio' che la voce gia' porta** -- `dominio`, scritto
    dall'osservatore insieme al titolo -- e mai dall'identificativo del
    soggetto: quello e' la chiave con cui Home Assistant deduplica (logger piu'
    posizione nel sorgente), e leggerlo come un nome darebbe
    `log:...@handler.py:108` in cima alla pagina, che e' esattamente cio' che
    la pagina faceva prima del 18/09.
    """
    slug = _integration_slug(domain)
    if slug is None:
        return None
    if slug == _CORE_SLUG:
        return _CORE_NAME
    # Una libreria di terze parti (`aioamazondevices`) non e' un'integrazione e
    # il suo nome intero e' piu' vero di qualunque pezzo se ne possa tagliare:
    # per lei il `slug` E' il nome.
    return _rendered(slug)


def _rendered(slug: str) -> str:
    """`alexa_devices` -> «Alexa devices». Una maiuscola e gli spazi: la
    minima resa che fa di un identificatore un nome, senza fingere di sapere
    come quell'integrazione si scriva davvero (`FRITZ!Box` lo sa solo HA)."""
    words = slug.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def integration_of(domain: str) -> tuple[str, str] | None:
    """`(nome, identificativo)` dell'integrazione da cui viene un dominio di
    registro, o `None` se non se ne ricava nessuno.

    La porta pubblica delle due regole che questo modulo usa per il primo
    piano (`_integration_name`, `_integration_slug`): la usa la rotta dello
    scope per raggruppare i soggetti tecnici, cosi' le due schede della stessa
    pagina dicono lo stesso nome per lo stesso logger.
    """
    identifier = _integration_slug(domain)
    if not identifier:
        return None
    return _integration_name(domain), identifier


def as_page(report: dict, *, judgments, names: dict | None = None) -> dict:
    """Il resoconto di un giorno **con il nome sempre e il primo piano**, per la
    pagina dell'osservatore (spec §3).

    Torna una copia: il resoconto che arriva non si tocca. Il contratto
    **cresce di chiavi e non ne perde nessuna** -- chi legge gia' questa rotta
    continua a funzionare.

    - **`nome`, sempre.** Chi ce l'ha tiene il suo (e' quello di ALLORA, ed e'
      piu' vero: un dispositivo si puo' rinominare); una voce di sistema lo
      ricava dal `dominio` che gia' porta; un'entita' lo prende da `names`, i
      nomi vivi. Chi non ha nessuna delle tre resta **senza**: la pagina mostra
      l'identificativo dicendo che e' un identificativo, e nessuno inventa un
      nome dall'`entity_id`.
    - **`primo_piano`** -- le righe che escono dal solito, raggruppate, nell'ordine
      di `FRONT_PAGE_ORDER`. La stessa marca sta anche sulla voce di cronaca, cosi'
      la cronaca in fondo la disegna com'e' in cima senza ricalcolarla.

    **Qui non c'e' nessun criterio.** Per un'entita' la domanda va al sapere
    (`TypeJudgments.stato_da_sapere_subito`), che risponde leggendo righe che
    la casa puo' correggere; per una condizione di sistema si cita il livello
    che Home Assistant ha scritto. Correggere un giudizio cambia il primo piano dalla
    lettura successiva, senza un rilascio.

    `judgments` puo' essere `None` (avvio a meta', archivio non collegato):
    allora gli episodi non entrano in primo piano -- «non lo so» non e' «non c'e'
    niente da sapere» -- mentre le condizioni di sistema restano, perche' il
    loro livello non dipende dai giudizi.
    """
    page = dict(report)
    chronicle = report.get("cronaca")
    if chronicle is None:
        page["primo_piano"] = []
        return page
    seen, band = [], []
    for entry in chronicle:
        entry = dict(entry)
        name = _resolved_name(entry, names)
        if name:
            entry["nome"] = name
        mark = _front_page_mark(entry, judgments)
        if mark is not None:
            entry["primo_piano"] = mark
            band.append(entry)
        seen.append(entry)
    page["cronaca"] = seen
    page["primo_piano"] = _grouped(band)
    return page


def _resolved_name(entry: dict, names: dict | None) -> str | None:
    stored = entry.get("nome")
    if stored:
        return stored
    if entry.get("dominio"):
        return _integration_name(entry["dominio"])
    return (names or {}).get(entry.get("chi"))


def _front_page_mark(entry: dict, judgments) -> dict | None:
    """La marca di una voce, o `None` se quella voce non esce dal solito.

    Due strade, e la differenza non e' un caso: una condizione di **sistema**
    porta gia' il suo livello da Home Assistant, un episodio di un'**entita'**
    va chiesto al sapere.
    """
    state = entry.get("cosa")
    if entry.get("genere") == SYSTEM_GENRE:
        # **L'impalcatura non sveglia nessuno** (decisione del proprietario,
        # 20/09/2026): Home Assistant che parla di se' -- il Supervisor, HACS,
        # il frontend -- resta nella cronaca e non sale in cima. Chi lo dice e'
        # un giudizio sull'integrazione, non questo file: la casa lo corregge
        # da «Cosa ho capito» e la lettura dopo cambia. Senza istantanea non si
        # zittisce niente: «non lo so» non diventa «taci».
        slug = _integration_slug(entry.get("dominio"))
        if judgments is not None and slug and judgments.is_scaffolding(slug):
            return None
        level = str(state or "").strip().upper()
        return {"sorta": "avviso" if level == _WARNING_LEVEL else "guasto"}
    subject = str(entry.get("chi") or "")
    if judgments is None or "." not in subject:
        return None
    domain = subject.split(".")[0]
    device_class = entry.get("classe")
    # **La condizione d'uso di `stato_da_sapere_subito`, custodita qui invece
    # che data per scontata**: `mind/facts.py` non scrive mai una cronaca con
    # `unavailable`/`unknown`, ma un tipo senza `lavoro` li leggerebbe come
    # «non e' un riposo» e li farebbe entrare in primo piano. Una riga «il sensore
    # non risponde» in cima alla pagina, col vestito di un allarme.
    if str(state).strip().lower() in unknown_states():
        return None
    if not judgments.stato_da_sapere_subito(domain, device_class, state,
                                            entity_id=subject):
        return None
    mark = {"sorta": "da_sapere_subito"}
    # La ragione la scrive il GIUDIZIO, accanto allo stato di lavoro; quando il
    # giudizio e' un elenco (`lock: ["jammed"]`) non c'e' nessuna ragione, e la
    # riga resta muta invece di guadagnare una frase nostra.
    reason = judgments.working_of(domain, device_class).get(str(state).strip().lower())
    if reason:
        mark["perche"] = reason
    return mark


#: Le chiavi con cui due voci sono **la stessa cosa** e diventano una riga
#: sola. Il soggetto e lo stato, piu' il titolo per le voci di sistema: due
#: guasti diversi della stessa integrazione restano due righe -- si raggruppa
#: cio' che e' uguale, non cio' che viene dallo stesso posto.
_FRONT_PAGE_KEY = ("chi", "cosa", "titolo")


def _grouped(entries: list[dict]) -> list[dict]:
    """Le voci in primo piano, raggruppate e in ordine di sorta.

    **Il raggruppamento non e' un abbellimento**: l'osservatore apre un
    episodio nuovo a ogni sfarfallio -- misurato sulla casa vera, venticinque
    episodi per una sola integrazione rotta -- e un primo piano che le elencasse
    tutti sarebbe il rumore che il primo piano esiste per togliere. `volte` dice
    quante, e la finestra e' il giorno che si sta leggendo.
    """
    rows: dict[tuple, dict] = {}
    for entry in entries:
        key = tuple(entry.get(k) for k in _FRONT_PAGE_KEY) + (entry["primo_piano"]["sorta"],)
        row = rows.get(key)
        if row is None:
            row = {**entry["primo_piano"], "volte": 0,
                   "quando_ts": entry.get("quando_ts"), "ultimo_ts": entry.get("quando_ts"),
                   "fine_ts": entry.get("fine_ts")}
            for field in ("nome", "chi", "cosa", "titolo", "dominio"):
                if entry.get(field):
                    row[field] = entry[field]
            rows[key] = row
        row["volte"] += 1
        # L'ultima volta, e come e' finita QUELLA: un episodio piu' recente
        # racconta lo stato di adesso, uno piu' vecchio no.
        if (entry.get("quando_ts") or 0) >= (row["ultimo_ts"] or 0):
            row["ultimo_ts"] = entry.get("quando_ts")
            row["fine_ts"] = entry.get("fine_ts")
        moments = [v for v in (row["quando_ts"], entry.get("quando_ts")) if v is not None]
        row["quando_ts"] = min(moments) if moments else None
    order = {kind: i for i, kind in enumerate(FRONT_PAGE_ORDER)}
    return sorted(rows.values(), key=lambda r: order.get(r["sorta"], len(order)))
