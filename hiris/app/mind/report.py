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

logger = logging.getLogger(__name__)

#: Le chiavi del corpo di un episodio che entrano nell'indice. Tutto il resto
#: -- i comprimari, il clima mentre durava, il contesto ricco -- **non entra**,
#: e si va a prendere quando serve.
_ANCHOR = ("nome", "classe", "attributi")


def build_report(*, day: str, episodes, series: dict, recipes: dict,
                 names: dict) -> dict:
    """Il resoconto di un giorno: `{giorno, misure, cronaca}`.

    **Puro**: nessuna lettura di rete e nessun archivio. Le serie arrivano gia'
    lette dal chiamante, le ricette gia' lette dal sapere, gli episodi gia'
    costruiti da `aggregate_day` -- stessa disciplina di `build_balance_body`.

    Un giorno vuoto produce un resoconto vuoto, e **va scritto lo stesso**:
    «quel giorno non e' successo niente» e «quel giorno non l'abbiamo
    guardato» sono due cose diverse, e l'analista deve poterle distinguere.
    """
    measured, shapes = _measurements(series, recipes, names)
    return {"giorno": day, "misure": measured, "forme": shapes,
            "cronaca": [_entry(e) for e in episodes or []]}


def _measurements(series: dict, recipes: dict,
                  names: dict) -> tuple[list[dict], list[dict]]:
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
            outcomes = recipe.run(series=needed)
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
                # `bool` e' un `int` in Python, e un vero/falso non e' una
                # grandezza: si controlla prima, o finirebbe fra le misure
                # come se fosse 1.
                if isinstance(outcome.value, bool) or not isinstance(
                        outcome.value, (int, float)):
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
    """
    body = episode.get("corpo_base") or {}
    entry = {"quando_ts": episode.get("inizio"), "fine_ts": episode.get("fine"),
            "chi": episode.get("protagonista"), "cosa": body.get("stato")}
    for key in _ANCHOR:
        if body.get(key) is not None:
            entry[key] = body[key]
    return entry


# -- il documento -----------------------------------------------------------

#: I titoli delle sezioni. Sono l'indice che l'analista scorre, e la porzione
#: che gli si puo' consegnare da sola: vivono qui in un posto solo perche'
#: `section()` li cerca per nome e un letterale ripetuto due volte sarebbe un
#: refuso che non fallisce -- restituirebbe una sezione vuota.
SEZIONE_MISURE = "Le misure"
SEZIONE_CRONACA = "La cronaca"
SEZIONE_IGNOTO = "Cosa non si sa"


def as_document(report: dict) -> str:
    """Il resoconto reso come documento, **derivato e mai scritto a mano**.

    Tre sezioni, e la terza non e' una ripetizione della prima: *«cosa non si
    sa»* e' il terzo innesco dell'analista, e in fondo a una tabella di numeri
    buoni non salterebbe all'occhio.
    """
    measurements = [m for m in report.get("misure") or [] if "valore" in m]
    unknown = [m for m in report.get("misure") or [] if "valore" not in m]
    chronicle = report.get("cronaca") or []

    lines = [f"# Resoconto del {report.get('giorno')}", ""]
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
