"""Le quattro caselle: il linguaggio chiuso in cui il modello scrive
un'interpretazione di un ricordo.

Un linguaggio aperto il modello lo compila male; uno piccolo lo compila
bene. Per questo l'interpretazione che il modello propone non ha campi
liberi: ha esattamente quattro caselle, e il vocabolario di ognuna viene da
qualcosa che esiste gia', non da un elenco inventato qui:

- **a chi si riferisce** (`ancore`): area, entita', dispositivo. Il
  vocabolario e' l'ANAGRAFE -- `Lookup.verify()` (resolver.py). Un
  ancora senza riscontro non si scrive: e' la stessa regola per cui il
  modello propone e il codice restringe.
- **cosa chiede** (`grandezza`/`minimo`/`massimo`): una grandezza e' quello
  che Home Assistant chiama un `device_class` (temperature, humidity, ...),
  e non ha un vocabolario chiuso qui -- l'elenco e' quello di HA, che
  cambia senza che questo modulo debba saperlo. Il valore associato e' un
  numero o un intervallo.
- **quando vale** (`condizioni`): ora, giorno, presenza, sole, meteo,
  stagione. Le prime cinque sono le condizioni che Home Assistant gia'
  conosce (trigger/condition delle sue automazioni); la sesta, la
  stagione, e' l'unica aggiunta di HIRIS, perche' HA non ce l'ha. Questa
  casella non e' estetica: parlando gia' la lingua di HA, un'interpretazione
  si traduce in un'automazione senza che nessuno la reinterpreti (Legge I).
- **che forza ha** (`forza`): preferenza, divieto, fatto, regola. Quattro
  parole, chiuse: non "importanza" su scala libera, non testo.

`VOCABULARY` e' l'unico posto in cui questo si legge -- non sparso nel
codice -- e `test_il_vocabolario_e_chiuso` lo tiene esattamente a queste
tre caselle e questi valori: se domani ne serve una quinta, quel test cade
apposta, perche' aggiungerne una in silenzio e' la stessa deriva che ha
reso ingestibili i campi liberi della 1.x.

**Il principio di validazione** (docs/design/2026-08-05, gia' pagato dodici
volte su questo ramo): un silenzio non dichiarato e' indistinguibile da
un'assenza di problemi. Quindi `validate()` non inventa, non lascia passare
in silenzio e non butta via senza dirlo: cio' che non riconosce lo SCARTA e
lo DICHIARA in un problema leggibile da una persona.

**L'unita' si deduce, non si chiede al modello.** Se l'ancora e' un'entita'
con una `unita`, e' quella. Se e' un'area, si guarda l'entita' di
quell'area la cui `classe` combacia con la `grandezza` proposta. Se non si
riesce a dedurla, resta `None`: inventarla sarebbe peggio di non averla.
"""
from __future__ import annotations

from ..casa.anagrafe import actual_area, actual_unit, device_areas

# Le quattro... anzi tre caselle con un vocabolario chiuso: "a chi si
# riferisce" e "che forza ha" restano qui elencate per intero; "cosa
# chiede" non ha voce perche' il suo vocabolario e' quello di Home
# Assistant (device_class), non uno nostro -- vedi la docstring del
# modulo. "quando vale" aggiunge "stagione" alle condizioni che HA gia'
# conosce.
VOCABULARY: dict[str, frozenset[str]] = {
    "forza": frozenset({"preferenza", "divieto", "fatto", "regola"}),
    "condizioni": frozenset({"ora", "giorno", "presenza", "sole", "meteo", "stagione"}),
    "ancore": frozenset({"area", "entita", "dispositivo"}),
}


def validate(interpretation: dict, lookup,
           tipi_non_verificabili: frozenset[str] = frozenset(),
           reported_unit: dict[str, str] | None = None
           ) -> tuple[dict, list[str], list[str]]:
    """Ripulisce un'interpretazione proposta dal modello, contro il
    vocabolario chiuso e l'anagrafe di `indice`.

    Restituisce `(interpretazione_ripulita, problemi, correzioni)`.

    **`problemi` e `correzioni` sono cose diverse, e confonderle produce
    due comportamenti opposti per la stessa situazione.** Un problema e'
    qualcosa che e' stato SCARTATO: chi riceve deve poter rifiutare. Una
    correzione e' qualcosa che e' stato RIPARATO e dichiarato: il dato c'e',
    e rifiutarlo punirebbe l'utente per un refuso che abbiamo gia' sistemato.
    Prima erano un elenco solo, e un intervallo raddrizzato -- riparato con
    successo -- faceva rifiutare tutta la correzione.

    La ripulita ha
    sempre tutte le chiavi (`forza`, `grandezza`, `minimo`, `massimo`,
    `unita`, `ancore`, `condizioni`), anche quando l'input era vuoto o
    parziale: un'interpretazione a meta' e' legittima (Regola 3 -- "mi
    piace il caffe'" non ha ne' ancore ne' condizioni, e non e' un errore).
    `problemi` e' vuota solo se davvero non c'era nulla da scartare.

    `tipi_non_verificabili` (default vuoto, per non rompere chi chiama con
    due soli argomenti) sono i tipi di ancora (`area`/`entita`/`dispositivo`)
    per cui `indice` non puo' dare una risposta affidabile -- l'anagrafe non
    e' mai stata letta, o quel registro specifico non ha risposto
    all'ultima lettura (`HomeSpaceStore.non_disponibili()`). Restano
    scartate lo stesso (fail-closed: un'ancora senza riscontro non si
    scrive), ma con la ragione vera -- "non si puo' verificare", non "non
    esiste", che sarebbe falso quando semplicemente non si e' potuto
    guardare.
    """
    problemi: list[str] = []
    correzioni: list[str] = []

    modality = _validate_modality(interpretation.get("forza"), problemi)
    grandezza = interpretation.get("grandezza")
    minimum, maximum = _validate_intervallo(
        interpretation.get("minimo"), interpretation.get("massimo"),
        problemi, correzioni)
    ancore = _validate_ancore(interpretation.get("ancore") or [], lookup,
                             tipi_non_verificabili, problemi)
    conditions = _validate_conditions(interpretation.get("condizioni") or [], problemi)
    unit = deduci_unit(ancore, grandezza, lookup, reported_unit)

    pulita = {
        "forza": modality,
        "grandezza": grandezza,
        "minimo": minimum,
        "massimo": maximum,
        "unita": unit,
        "ancore": ancore,
        "condizioni": conditions,
    }
    return pulita, problemi, correzioni


def _validate_modality(modality, problemi: list[str]):
    """`forza` e' opzionale: non fornita non e' un problema, fornita ma
    fuori vocabolario si' -- e si dichiara con la parola che il modello
    aveva scritto, cosi' chi legge il problema capisce cosa e' stato
    scartato."""
    if modality is None:
        return None
    if modality not in VOCABULARY["forza"]:
        problemi.append(
            f"forza «{modality}» non e' nel vocabolario "
            f"({', '.join(sorted(VOCABULARY['forza']))}) -- scartata")
        return None
    return modality


def _validate_intervallo(minimum, maximum, problemi: list[str],
                       correzioni: list[str]) -> tuple[float | None, float | None]:
    """Un valore o un intervallo, mai un testo: qui si converte a numero e
    si raddrizza un intervallo scritto al contrario, che e' un errore di
    battitura del modello, non un'intenzione -- si corregge, ma si
    dichiara comunque, perche' un raddrizzamento silenzioso e' comunque
    un silenzio non dichiarato."""
    try:
        minimum = None if minimum is None else float(minimum)
        maximum = None if maximum is None else float(maximum)
    except (TypeError, ValueError):
        problemi.append(
            f"intervallo non numerico (minimo={minimum!r}, massimo={maximum!r}) -- scartato")
        return None, None

    if minimum is not None and maximum is not None and minimum > maximum:
        # CORREZIONE, non problema: il dato c'e' ed e' stato riparato. Metterlo
        # fra i problemi faceva rifiutare l'intera richiesta -- cioe' punire
        # l'utente per un refuso che avevamo gia' sistemato, e per giunta solo
        # quando ne correggeva meta': lo stesso intervallo mandato intero
        # veniva raddrizzato e accettato.
        correzioni.append(
            f"minimo ({minimum}) maggiore di massimo ({maximum}): "
            "intervallo invertito -- raddrizzato"
        )
        minimum, maximum = maximum, minimum
    return minimum, maximum


def _validate_ancore(ancore, lookup, tipi_non_verificabili: frozenset[str],
                    problemi: list[str]) -> list[dict]:
    """Ogni ancora deve avere un tipo del vocabolario ED esistere
    nell'anagrafe -- le due condizioni sono indipendenti e vengono
    dichiarate separatamente, cosi' il problema dice davvero cosa non ha
    funzionato invece di un generico "ancora non valida".

    Un terzo caso, distinto da entrambi: il tipo e' valido ma non si puo'
    nemmeno controllare (`tipi_non_verificabili` -- l'anagrafe non e' mai
    stata letta, o quel registro non ha risposto). Si scarta comunque
    (fail-closed), ma dirlo come "non esiste" sarebbe falso: si dice "non
    si puo' verificare"."""
    pulite: list[dict] = []
    for tether in ancore:
        type = tether.get("tipo")
        reference = tether.get("riferimento")
        label = tether.get("nome_visto") or reference or "?"

        if type not in VOCABULARY["ancore"]:
            problemi.append(
                f"ancora «{label}» ha un tipo («{type}») fuori dal vocabolario "
                f"({', '.join(sorted(VOCABULARY['ancore']))}) -- scartata")
            continue
        if type in tipi_non_verificabili:
            problemi.append(
                f"ancora {type} «{label}» non si puo' verificare: l'anagrafe della casa "
                f"non e' disponibile -- scartata (un'ancora che non si puo' controllare "
                f"non si scrive)")
            continue
        if reference is None or lookup.verify(type, reference) is None:
            # R5: si scarta comunque (il ricordo si salva, il testo resta
            # la verita' -- decisione del proprietario), ma il problema deve
            # INSEGNARE la correzione, non solo dichiarare lo scarto: stesso
            # pattern gia' in `azione/verifica.py::_no` per un bersaglio non
            # risolto («Usa "cerca" per trovare il nome giusto e ripeti il
            # comando»), esteso qui a `remember`.
            problemi.append(
                f"ancora {type} «{label}» non esiste nell'anagrafe -- scartata "
                f"(un'ancora senza riscontro non si scrive). Se «{label}» e' un "
                f"nome (non un id), chiama «search» per trovare l'id giusto e ripeti "
                f"«remember» con quello.")
            continue
        pulite.append({"tipo": type, "riferimento": reference,
                        "nome_visto": tether.get("nome_visto")})
    return pulite


def _validate_conditions(conditions, problemi: list[str]) -> list[dict]:
    """`valore` non ha un vocabolario chiuso qui: e' il modello che lo
    riempie con cio' che Home Assistant intende per quella condizione
    (es. `sole: tramontato`), e la traduzione in automazione verifica il
    resto. Qui si restringe il `tipo` della condizione, e si richiede che
    `valore` ci sia: la colonna `condizioni.valore` e' `NOT NULL`
    (memoria/archivio.py), quindi una condizione senza valore che
    superasse questo cancello finirebbe a spaccare la scrittura con un
    `IntegrityError` invece di essere scartata e dichiarata qui -- ed e'
    esattamente il silenzio che questo cancello esiste per evitare."""
    pulite: list[dict] = []
    for condizione in conditions:
        type = condizione.get("tipo")
        value = condizione.get("valore")
        if type not in VOCABULARY["condizioni"]:
            problemi.append(
                f"condizione «{type}» non e' nel vocabolario "
                f"({', '.join(sorted(VOCABULARY['condizioni']))}) -- scartata")
            continue
        if value is None:
            problemi.append(f"condizione «{type}» senza valore -- scartata")
            continue
        pulite.append({"tipo": type, "valore": value})
    return pulite


def deduci_unit(ancore: list[dict], grandezza, lookup,
                 reported_unit: dict[str, str] | None = None) -> str | None:
    """L'unita' non si chiede al modello, si deduce da cio' che l'anagrafe
    gia' sa:

    - un'ancora `entita` porta gia' la sua `unita`: e' quella, senza
      bisogno che `grandezza` la confermi (l'entita' e' gia' la fonte piu'
      precisa che esista).
    - un'ancora `area` non ha un'unita' propria: si cerca, fra le entita'
      di quell'area, quella la cui `classe` (il `device_class` di HA)
      combacia con la `grandezza` proposta, e si prende la sua unita'.

    Si usa solo la superficie pubblica di `Lookup`: `verify()` per la ricerca
    per identificatore, `tutti()` per l'enumerazione. Leggere `_per_type`
    funzionava, ma accoppiava a un dettaglio interno -- e un accoppiamento del
    genere si propaga in silenzio al modulo successivo.

    Se non si trova nulla, resta `None`: **non si inventa**.
    """
    reported = reported_unit or {}
    for tether in ancore:
        if tether["tipo"] == "entita":
            entity = lookup.verify("entita", tether["riferimento"])
            if entity:
                unit = actual_unit(entity.get("unita"), reported.get(entity.get("id")))
                if unit is not None:
                    return unit
        elif tether["tipo"] == "area" and grandezza is not None:
            area_id = tether["riferimento"]
            # L'area EREDITATA dal dispositivo conta quanto quella propria --
            # anzi, di piu': in una casa vera e' il caso normale. La regola sta
            # in `casa.anagrafe.actual_area`, la stessa che usa `hierarchy()`
            # per costruire l'albero: qui prima si confrontava il solo
            # `area_id` proprio, e su una casa vera non si trovava mai niente.
            device_area = device_areas(lookup.tutti("dispositivo"))
            for entity in lookup.tutti("entita"):
                if entity.get("classe") != grandezza:
                    continue
                if actual_area(entity, device_area) != area_id:
                    continue
                unit = actual_unit(entity.get("unita"), reported.get(entity.get("id")))
                if unit is not None:
                    return unit
    return None
