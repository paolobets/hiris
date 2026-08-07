"""Le quattro caselle: il linguaggio chiuso in cui il modello scrive
un'interpretazione di un ricordo.

Un linguaggio aperto il modello lo compila male; uno piccolo lo compila
bene. Per questo l'interpretazione che il modello propone non ha campi
liberi: ha esattamente quattro caselle, e il vocabolario di ognuna viene da
qualcosa che esiste gia', non da un elenco inventato qui:

- **a chi si riferisce** (`ancore`): area, entita', dispositivo. Il
  vocabolario e' l'ANAGRAFE -- `Indice.verifica()` (riconoscitore.py). Un
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

`VOCABOLARIO` e' l'unico posto in cui questo si legge -- non sparso nel
codice -- e `test_il_vocabolario_e_chiuso` lo tiene esattamente a queste
tre caselle e questi valori: se domani ne serve una quinta, quel test cade
apposta, perche' aggiungerne una in silenzio e' la stessa deriva che ha
reso ingestibili i campi liberi della 1.x.

**Il principio di validazione** (docs/design/2026-08-05, gia' pagato dodici
volte su questo ramo): un silenzio non dichiarato e' indistinguibile da
un'assenza di problemi. Quindi `valida()` non inventa, non lascia passare
in silenzio e non butta via senza dirlo: cio' che non riconosce lo SCARTA e
lo DICHIARA in un problema leggibile da una persona.

**L'unita' si deduce, non si chiede al modello.** Se l'ancora e' un'entita'
con una `unita`, e' quella. Se e' un'area, si guarda l'entita' di
quell'area la cui `classe` combacia con la `grandezza` proposta. Se non si
riesce a dedurla, resta `None`: inventarla sarebbe peggio di non averla.
"""
from __future__ import annotations

# Le quattro... anzi tre caselle con un vocabolario chiuso: "a chi si
# riferisce" e "che forza ha" restano qui elencate per intero; "cosa
# chiede" non ha voce perche' il suo vocabolario e' quello di Home
# Assistant (device_class), non uno nostro -- vedi la docstring del
# modulo. "quando vale" aggiunge "stagione" alle condizioni che HA gia'
# conosce.
VOCABOLARIO: dict[str, frozenset[str]] = {
    "forza": frozenset({"preferenza", "divieto", "fatto", "regola"}),
    "condizioni": frozenset({"ora", "giorno", "presenza", "sole", "meteo", "stagione"}),
    "ancore": frozenset({"area", "entita", "dispositivo"}),
}


def valida(interpretazione: dict, indice) -> tuple[dict, list[str]]:
    """Ripulisce un'interpretazione proposta dal modello, contro il
    vocabolario chiuso e l'anagrafe di `indice`.

    Restituisce `(interpretazione_ripulita, problemi)`. La ripulita ha
    sempre tutte le chiavi (`forza`, `grandezza`, `minimo`, `massimo`,
    `unita`, `ancore`, `condizioni`), anche quando l'input era vuoto o
    parziale: un'interpretazione a meta' e' legittima (Regola 3 -- "mi
    piace il caffe'" non ha ne' ancore ne' condizioni, e non e' un errore).
    `problemi` e' vuota solo se davvero non c'era nulla da scartare.
    """
    problemi: list[str] = []

    forza = _valida_forza(interpretazione.get("forza"), problemi)
    grandezza = interpretazione.get("grandezza")
    minimo, massimo = _valida_intervallo(
        interpretazione.get("minimo"), interpretazione.get("massimo"), problemi)
    ancore = _valida_ancore(interpretazione.get("ancore") or [], indice, problemi)
    condizioni = _valida_condizioni(interpretazione.get("condizioni") or [], problemi)
    unita = _deduci_unita(ancore, grandezza, indice)

    pulita = {
        "forza": forza,
        "grandezza": grandezza,
        "minimo": minimo,
        "massimo": massimo,
        "unita": unita,
        "ancore": ancore,
        "condizioni": condizioni,
    }
    return pulita, problemi


def _valida_forza(forza, problemi: list[str]):
    """`forza` e' opzionale: non fornita non e' un problema, fornita ma
    fuori vocabolario si' -- e si dichiara con la parola che il modello
    aveva scritto, cosi' chi legge il problema capisce cosa e' stato
    scartato."""
    if forza is None:
        return None
    if forza not in VOCABOLARIO["forza"]:
        problemi.append(
            f"forza «{forza}» non e' nel vocabolario "
            f"({', '.join(sorted(VOCABOLARIO['forza']))}) -- scartata")
        return None
    return forza


def _valida_intervallo(minimo, massimo, problemi: list[str]) -> tuple[float | None, float | None]:
    """Un valore o un intervallo, mai un testo: qui si converte a numero e
    si raddrizza un intervallo scritto al contrario, che e' un errore di
    battitura del modello, non un'intenzione -- si corregge, ma si
    dichiara comunque, perche' un raddrizzamento silenzioso e' comunque
    un silenzio non dichiarato."""
    try:
        minimo = None if minimo is None else float(minimo)
        massimo = None if massimo is None else float(massimo)
    except (TypeError, ValueError):
        problemi.append(
            f"intervallo non numerico (minimo={minimo!r}, massimo={massimo!r}) -- scartato")
        return None, None

    if minimo is not None and massimo is not None and minimo > massimo:
        problemi.append(
            f"minimo ({minimo}) maggiore di massimo ({massimo}): intervallo invertito -- raddrizzato")
        minimo, massimo = massimo, minimo
    return minimo, massimo


def _valida_ancore(ancore, indice, problemi: list[str]) -> list[dict]:
    """Ogni ancora deve avere un tipo del vocabolario ED esistere
    nell'anagrafe -- le due condizioni sono indipendenti e vengono
    dichiarate separatamente, cosi' il problema dice davvero cosa non ha
    funzionato invece di un generico "ancora non valida"."""
    pulite: list[dict] = []
    for ancora in ancore:
        tipo = ancora.get("tipo")
        riferimento = ancora.get("riferimento")
        etichetta = ancora.get("nome_visto") or riferimento or "?"

        if tipo not in VOCABOLARIO["ancore"]:
            problemi.append(
                f"ancora «{etichetta}» ha un tipo («{tipo}») fuori dal vocabolario "
                f"({', '.join(sorted(VOCABOLARIO['ancore']))}) -- scartata")
            continue
        if riferimento is None or indice.verifica(tipo, riferimento) is None:
            problemi.append(
                f"ancora {tipo} «{etichetta}» non esiste nell'anagrafe -- scartata "
                f"(un'ancora senza riscontro non si scrive)")
            continue
        pulite.append({"tipo": tipo, "riferimento": riferimento,
                        "nome_visto": ancora.get("nome_visto")})
    return pulite


def _valida_condizioni(condizioni, problemi: list[str]) -> list[dict]:
    """`valore` non ha un vocabolario chiuso qui: e' il modello che lo
    riempie con cio' che Home Assistant intende per quella condizione
    (es. `sole: tramontato`), e la traduzione in automazione verifica il
    resto. Qui si restringe solo il `tipo` della condizione."""
    pulite: list[dict] = []
    for condizione in condizioni:
        tipo = condizione.get("tipo")
        if tipo not in VOCABOLARIO["condizioni"]:
            problemi.append(
                f"condizione «{tipo}» non e' nel vocabolario "
                f"({', '.join(sorted(VOCABOLARIO['condizioni']))}) -- scartata")
            continue
        pulite.append({"tipo": tipo, "valore": condizione.get("valore")})
    return pulite


def _deduci_unita(ancore: list[dict], grandezza, indice) -> str | None:
    """L'unita' non si chiede al modello, si deduce da cio' che l'anagrafe
    gia' sa:

    - un'ancora `entita` porta gia' la sua `unita`: e' quella, senza
      bisogno che `grandezza` la confermi (l'entita' e' gia' la fonte piu'
      precisa che esista).
    - un'ancora `area` non ha un'unita' propria: si cerca, fra le entita'
      di quell'area, quella la cui `classe` (il `device_class` di HA)
      combacia con la `grandezza` proposta, e si prende la sua unita'.

    Si usa `indice._per_tipo` (interno a `Indice`) perche' l'anagrafe non
    espone un modo pubblico per elencare "le entita' di un'area" -- e
    Task 3 non tocca `riconoscitore.py`. Se in futuro serve altrove, vale
    la pena promuovere questa ricerca a un metodo pubblico di `Indice`.

    Se non si trova nulla, resta `None`: **non si inventa**.
    """
    entita_per_riferimento: dict[str, dict] = indice._per_tipo.get("entita", {})

    for ancora in ancore:
        if ancora["tipo"] == "entita":
            entita = entita_per_riferimento.get(ancora["riferimento"])
            if entita and entita.get("unita") is not None:
                return entita["unita"]
        elif ancora["tipo"] == "area" and grandezza is not None:
            area_id = ancora["riferimento"]
            for entita in entita_per_riferimento.values():
                if entita.get("area_id") == area_id and entita.get("classe") == grandezza \
                        and entita.get("unita") is not None:
                    return entita["unita"]
    return None
