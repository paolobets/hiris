"""Il resoconto giornaliero: due parti, e la separazione e' funzionale.

Spec `docs/design/2026-09-10-i-tre-attori.md` §9, e la forma decisa col
proprietario il 13/09/2026.

## A cosa serve, perche' da li' viene tutto il resto

**Le misure servono all'analista** (§10), che ha tre inneschi
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

**La cronaca e' un INDICE** -- quando, chi, cosa. Oggi la legge la pagina
(`as_page`): l'analista riceve l'indice delle misure, una riga per misura
coi numeri gia' calcolati (`analyst.index`, dal 06/10/2026), e non ha ancora
strumenti con cui scavare (piano degli attori, Task 3.6). La spec §10
lo voleva capace di partire dall'indice e scavare in Home Assistant o nel
nostro grezzo, dicendo quale dei due ha usato: non e' costruito.

**Perche' un indice e non l'episodio intero**, misurato sui 200 oggetti veri
della casa il 13/09/2026: l'episodio pesa **622 byte**, l'indice **109**. Su
trenta giorni sono **521 KB contro 92**.

**Ma l'indice porta un'ancora.** E' l'unico difetto irreversibile che la forma
nuda avrebbe: cio' che dopo non si recupera piu' perche' dipende da com'era la
casa **allora** -- il nome che l'entita' aveva, la sua classe, gli attributi
raccolti. Home Assistant, richiesto domani, risponde con quelli di domani: e'
la lezione gia' pagata da `friendly_name`, che si salva nel grezzo invece di
risolverlo dopo. Costa 27 byte a voce.

## Le rese

**Si derivano, non si scrivono.** Una resa scritta a mano sarebbe una seconda
copia che diverge dalla prima; derivandola, migliorare il modo di raccontare
un giorno vale anche per i giorni passati -- la stessa promessa per cui il
grezzo dura 22 giorni. Oggi la resa e' una: quella per la pagina (`as_page`).
Quella per l'analista -- un documento markdown a sezioni, un terzo dei byte
del JSON -- non aveva lettori ed e' uscita il 02/10/2026; cosa faceva e'
scritto nel BACKLOG, alla voce sugli attori.
"""
from __future__ import annotations

import logging

from ..home_space.ha_vocabulary import domain_of, is_entity_id
from ..home_space.log_source import (
    integration_name,
    integration_slug,
)
from ..home_space.type_vocabulary import SYSTEM_GENRE, unknown_states
from .operations import RECIPE_BROKEN, NotComputable
from .recipes import Recipe

logger = logging.getLogger(__name__)

#: Quando si scrive il resoconto di ieri: l'aggregazione notturna (`server.py`,
#: lavoro `hiris_mind_aggregation`) gira a quest'ora, nel fuso della casa. Le
#: 00:20 e non la mezzanotte: aggregare a mezzanotte esatta prenderebbe un
#: giorno ancora aperto. Scritte qui e non nella chiamata allo schedulatore
#: perche' le dice anche la pagina «Il giorno», che le riceve da
#: `GET /api/mind/report` (C-11, Tappa 4, Task 5).
NIGHTLY_HOUR = 0
NIGHTLY_MINUTE = 20

#: Ogni quanto il recupero (`server.backfill_one_report`, lavoro
#: `hiris_mind_backfill`) scrive, o rifa', un giorno di resoconto. Anche questa
#: la dice una pagina: «Cosa ho capito» spiega quanto costa rifare la cronaca,
#: e la riceve da `GET /api/mind/knowledge`.
BACKFILL_EVERY_MINUTES = 5

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
#: `chiusa_dalla_fonte` (05/10/2026, Task 1.4 degli attori): perche' un
#: episodio e' finito quando non l'ha chiuso uno stato visto -- la fonte che
#: Home Assistant non nomina piu', con la sua causa (`facts.build_episodes`).
#: Senza, la voce direbbe una fine normale.
#:
#: `interrotto` e `assenti` (06/10/2026, Task 1.4, Passo 3): un episodio
#: finito perche' la fonte ha smesso di rispondere, e le entita' di
#: un'istanza sparita tutta insieme. Senza, la prima voce direbbe una fine
#: vista e la seconda non direbbe di chi era l'assenza.
#:
#: Tutto il resto -- il clima mentre durava, il contesto ricco -- **non entra**,
#: e si va a prendere quando serve.
_ANCHOR = ("nome", "classe", "attributi", "dominio", "titolo", "comparso_ts",
           "chiusa_dalla_fonte", "interrotto", "assenti")


def build_report(*, day: str, episodes, series: dict, recipes: dict,
                 names: dict, objective: dict | None = None,
                 silent: dict[str, NotComputable] | None = None,
                 judgment: dict | None = None,
                 muted: dict[str, dict] | None = None) -> dict:
    """Il resoconto di un giorno: `{giorno, obiettivo, misure, forme, cronaca,
    giudizio}`.

    **Puro**: nessuna lettura di rete e nessun archivio. Le serie arrivano gia'
    lette dal chiamante, le ricette gia' lette dal sapere, gli episodi gia'
    costruiti da `facts.build_episodes`.

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

    **`silent`** porta le entita' che non daranno una serie, ognuna col suo
    rifiuto (spec §6, primo «rifiuta se»; `recipes.silent_entities`,
    `recipes.unread_series`): le loro misure escono «non calcolabile»
    dicendo QUELLO, con la sua causa, invece di «la serie e' vuota». `None`
    vuol dire «non l'abbiamo potuto chiedere», e allora non si afferma niente.

    **`judgment` e' l'impronta dei giudizi con cui e' nata la cronaca**
    (`{"impronta": ...}`, spec `docs/design/2026-09-16-il-giudizio-dei-tipi.md`
    §6), gia' calcolata da chi chiama: `facts.aggregate_day` e
    `facts.rebuild_chronicle`. Come `objective`, `None` resta `None`: nessuna
    impronta inventata per una cronaca che non dice con quale giudizio e' nata.

    **`muted`** porta le ricette che non possono produrre niente perche' ogni
    loro entita' tace per una causa che non passa da sola
    (`recipes.muted_recipes`, piano degli attori, Task 1.5; G-02, G-03):
    `{dispositivo: {non_calcolabile, causa}}`. Escono con UNA riga per
    dispositivo, non con un rifiuto per passo; chi chiama non le mette fra
    `recipes`.
    """
    measured, shapes = _measurements(series, recipes, names, silent, muted)
    return {"giorno": day, "obiettivo": objective, "misure": measured,
            "forme": shapes, "cronaca": [_entry(e) for e in episodes or []],
            "giudizio": judgment}


def _measurements(series: dict, recipes: dict, names: dict,
                  silent: dict[str, NotComputable] | None = None,
                  muted: dict[str, dict] | None = None
                  ) -> tuple[list[dict], list[dict]]:
    """Le misure e le **forme**, separate: `(misure, forme)`.

    Una riga per numero, una per ogni numero che non si e' potuto fare -- col
    suo perche', `non_calcolabile`, e la sua `causa` dal vocabolario chiuso
    (`operations.CAUSES`, B-26) -- e a parte quelle il cui risultato **non e'
    un numero**.

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
    l'analista guarda cio' che manca, e spostarlo fra le forme lo
    nasconderebbe.
    """
    out: list[dict] = []
    shapes: list[dict] = []
    muted = muted or {}
    for subject in sorted({*(recipes or {}), *muted}):
        base = {"soggetto": subject}
        if names.get(subject):
            base["nome"] = names[subject]
        if subject in muted:
            # Il dispositivo tace tutto: una riga, non un rifiuto per passo.
            out.append({**base, "misura": "(la ricetta)",
                        "non_calcolabile": muted[subject]["non_calcolabile"],
                        "causa": muted[subject]["causa"]})
            continue
        recipe = Recipe(recipes[subject])
        needed = {e: series.get(e) or [] for e in recipe.entities()}
        try:
            outcomes = recipe.run(series=needed, silent=silent)
        except ValueError as error:
            # **Una ricetta storta non fa perdere il giorno intero.** Puo'
            # essere stata corretta male a mano, o scritta da un modello che ha
            # sbagliato: si dichiara fra cio' che non si e' potuto calcolare, e
            # le altre restano. Perdere il resoconto di tutta la casa per un
            # dispositivo sarebbe il contrario di cio' che questo strato
            # promette.
            out.append({**base, "misura": "(la ricetta)",
                        "non_calcolabile": str(error), "causa": RECIPE_BROKEN})
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
                # Le ore lasciate fuori, con la misura che ha lasciate
                # (il dato fermo, 08/10/2026): la chiave c'e' solo se ce ne
                # sono, come `causa` c'e' solo su un rifiuto.
                if outcome.excluded:
                    row["esclusi"] = [x.out() for x in outcome.excluded]
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
                row["causa"] = outcome.cause
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
    misura, chiave, operazione, unita, valori, coperture, perche, esclusi}]}`.
    `esclusi` e' `{giorno: [{dal, al, causa, perche}]}`: le ore che il
    resoconto di quel giorno ha lasciato fuori dal valore (il dato fermo,
    08/10/2026), accanto al valore che hanno cambiato.

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

    **I giorni senza valore si raccolgono in tratti** (`{dal, al, ragione,
    causa}`), non uno per giorno: vedi `_runs`, col numero che lo giustifica.
    `causa` e' la parola del vocabolario chiuso (B-26, attori Task 1.2);
    `None` per i resoconti scritti prima che la riga la portasse.

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
                     "perche": {}, "esclusi": {}}
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
                            slot["perche"][day] = (reason, line.get("causa"))
                    continue
                slot = _slot(line, key)
                slot["valori"][index[day]] = value
                slot["coperture"][index[day]] = line.get("copertura")
                if line.get("esclusi"):
                    slot["esclusi"][day] = line["esclusi"]

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
    """I giorni senza valore, raccolti in **tratti**: `{dal, al, ragione,
    causa}`. `reasons` e' `{giorno: (ragione, causa)}`.

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
    andata di nuovo, non un unico buco lungo che non c'e' mai stato. Lo stesso
    per due cause diverse con la stessa frase.
    """
    out: list[dict] = []
    open_run: dict | None = None
    for day in days:
        found = reasons.get(day)
        if found is None:
            open_run = None
            continue
        reason, cause = found
        if (open_run is not None and open_run["ragione"] == reason
                and open_run["causa"] == cause):
            open_run["al"] = day
            continue
        open_run = {"dal": day, "al": day, "ragione": reason, "causa": cause}
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

# ---------------------------------------------------------------------------
# Il resoconto come lo legge la PAGINA (spec 2026-09-18 §3).
#
# L'archivio si rende per un umano, e la resa si deriva invece di essere
# scritta.
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
        return integration_name(entry["dominio"])
    return (names or {}).get(entry.get("chi"))


def _front_page_mark(entry: dict, judgments) -> dict | None:
    """La marca di una voce, o `None` se quella voce non esce dal solito.

    Due strade, e la differenza non e' un caso: una condizione di **sistema**
    porta gia' il suo livello da Home Assistant, un episodio di un'**entita'**
    va chiesto al sapere.
    """
    state = entry.get("cosa")
    if entry.get("genere") == SYSTEM_GENRE:
        # **L'assenza di un'entita' sola resta nella cronaca** (G17-1,
        # decisione del proprietario del 06/10/2026, «Solo integrazione»):
        # in primo piano sale la voce dell'ISTANZA sparita insieme
        # (`integrazione:` piu' l'id, `facts._absences`), non la luce che non
        # ha risposto per dieci minuti. Il genere e' lo stesso -- la voce
        # parla della fonte -- ma il soggetto no: una condizione di sistema
        # non ha mai per soggetto un `entity_id`, un'assenza di entita' si'.
        if is_entity_id(entry.get("chi")):
            return None
        # **Nemmeno la finestra in cui l'add-on e' rimasto scollegato**
        # (riallineamento alla riconnessione, 06/10/2026): un riavvio di Home
        # Assistant non e' un guasto della casa, e la decisione del
        # proprietario esiste perche' le assenze del riavvio non sembrino
        # guasti. Resta nella cronaca, con le assenze che ha raccolto.
        # Importata qui e non in cima: `facts` importa questo modulo.
        from .facts import DISCONNECTION_SUBJECT
        if entry.get("chi") == DISCONNECTION_SUBJECT:
            return None
        # **L'impalcatura non sveglia nessuno** (decisione del proprietario,
        # 20/09/2026): Home Assistant che parla di se' -- il Supervisor, HACS,
        # il frontend -- resta nella cronaca e non sale in cima. Chi lo dice e'
        # un giudizio sull'integrazione, non questo file: la casa lo corregge
        # da «Cosa ho capito» e la lettura dopo cambia. Senza istantanea non si
        # zittisce niente: «non lo so» non diventa «taci».
        slug = integration_slug(entry.get("dominio"))
        if judgments is not None and slug and judgments.is_scaffolding(slug):
            return None
        level = str(state or "").strip().upper()
        return {"sorta": "avviso" if level == _WARNING_LEVEL else "guasto"}
    subject = str(entry.get("chi") or "")
    if judgments is None or "." not in subject:
        return None
    domain = domain_of(subject)
    device_class = entry.get("classe")
    # **La condizione d'uso di `stato_da_sapere_subito`, custodita qui invece
    # che data per scontata**: `mind/facts.py` non scrive mai l'EPISODIO di
    # un'entita' con `unavailable`/`unknown` (dal 06/10/2026 un'assenza e' una
    # voce col genere di sistema, e passa dal ramo sopra), ma un tipo senza
    # `lavoro` li leggerebbe come
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
