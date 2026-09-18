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
                  f"{m['valore']} {m['unita']} | {m['copertura']:.0%} |"
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
