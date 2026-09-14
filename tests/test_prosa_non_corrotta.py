"""Il cancello sulla prosa: nessun identificatore nudo dentro una frase italiana.

**Perche' esiste.** Tre volte in due giorni una rinomina di identificatori
fatta con un'espressione regolare ha toccato la PROSA dei commenti, non solo il
codice: «la temperatura e' salita» e' diventata «la temperatura e' rise», «il
settimo totale» e' diventato «il settimo total», «i 22 giorni di grezzo» sono
diventati «i 22 giorni di raw_attributes». Tutte e tre le volte l'ha trovata
una rilettura a mano o una revisione indipendente -- cioe' per fortuna.

Non e' un difetto estetico. Le motivazioni scritte accanto al codice sono il
modo in cui questo progetto tiene la sua memoria, e una frase resa illeggibile
e' una motivazione persa: la regola del mandato dice che *«nessuna ragione
scritta accanto al codice deve essere smentita dal file che cita»*, e una
ragione che non si legge piu' non si puo' nemmeno verificare.

## Come funziona, e perche' e' preciso invece che prudente

Lo stile del progetto e' costante: **il codice citato nella prosa sta fra
backtick** (`aggregate_day`, `mind/store.py`, `_wanted_attributes`). Quindi un
identificatore che compare **nudo** dentro una frase italiana e' quasi sempre
il residuo di una sostituzione meccanica, non una scelta di chi scriveva.

Il cancello quindi:

1. raccoglie gli identificatori DEFINITI in ogni file (funzioni, classi,
   variabili, parametri) -- non un elenco a mano;
2. guarda solo le righe di commento e di docstring;
3. tiene solo le righe che sono ITALIANE, cioe' che portano almeno due parole
   funzionali italiane (`che`, `non`, `il`, `la`, `di`, `per`, `una`, ...);
4. toglie tutto cio' che sta fra backtick, fra virgolette, e dopo un `:` di
   una riga di campo;
5. e segnala cio' che resta.

La forma e' quella dell'istantanea gia' usata da
`test_preposizioni_italiane.py`: **uguaglianza esatta nelle due direzioni**.
Un residuo nuovo grida; un residuo corretto e non tolto da qui grida pure.
"""
from __future__ import annotations

import ast
import pathlib
import re

#: La radice del repo. `scripts/_comune.ROOT` esiste, ma vive fra gli script e
#: si importa solo dopo averli messi in `sys.path`: qui basta risalire.
ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Le parole funzionali che dicono «questa riga e' italiana». Due bastano: una
#: sola comparirebbe per caso in una frase inglese (`the`, `in`, `a`).
_PAROLE_FUNZIONALI = frozenset([
    "che", "non", "il", "la", "lo", "le", "gli", "un", "una", "uno", "di",
    "del", "della", "dei", "delle", "da", "dal", "per", "con", "su", "nel",
    "nella", "sul", "sulla", "e'", "quando", "perche'", "come", "questo",
    "questa", "quello", "quella", "si", "sono", "era", "erano", "piu'",
    "meno", "anche", "invece", "quindi", "senza", "dentro", "fuori", "ogni",
])

#: Gli identificatori troppo corti o troppo comuni per dire qualcosa: cercarli
#: nella prosa produrrebbe solo rumore.
_TROPPO_CORTI = 4

#: Parole che sono insieme identificatori e italiano vero. Cercarle segnalerebbe
#: la prosa giusta: `zone` («le zone insieme»), `state` («sono state»),
#: `serie` («una serie di punti»), `periodo`, `misure`.
_PAROLE_DOMINIO = frozenset({
    "zone", "state", "serie", "periodo", "misure", "misura", "valore",
    "valori", "istante", "totale", "nome", "citazione", "grezzo", "prima",
    "seconda", "presenti", "punti", "noti", "ore", "chiave", "entita",
    "direzione", "operazione", "risultato", "copertura", "unita", "finestre",
    "attributi", "letture", "gruppi", "coppie", "pendenza", "verso",
    "differenza", "variazione", "numero", "parte", "parti", "forma", "genere",
    "corpo", "giorno", "giorni", "riga", "righe", "casa", "campo", "campi",
    "fonte", "prove", "seme", "ricetta", "passo", "passi", "sapere", "dato",
    "dati", "conto", "conti", "cosa", "cose", "modo", "posto", "volta",
    "volte", "caso", "casi", "regola", "regole", "classe", "classi", "tipo",
    "tipi", "stato", "stati", "quando", "quanto", "solo", "sola", "tutte",
    "tutti", "tutto", "altro", "altra", "altre", "altri", "nomi", "scope",
    "problemi", "problema", "risposta", "domanda", "data",
    "cronaca", "fuori", "resto", "sezione", "documento",
})

#: I file guardati: l'ambito dove le rinomine meccaniche sono avvenute.
_PERIMETRO = ("hiris/app/mind",)

#: L'istantanea dei residui NOTI. Vuota, e deve restarlo: a differenza delle
#: preposizioni qui non c'e' debito storico da tracciare -- il difetto e' nato
#: con le rinomine di questa settimana, ed e' stato corretto tutto.
_RESIDUI_NOTI: frozenset[str] = frozenset({
    # Inglese tecnico dentro una frase italiana, scritto apposta: e' la lingua
    # con cui questo prodotto parla di Home Assistant, e mettere «registratore»
    # al posto di `logger` renderebbe la frase piu' difficile, non piu' pulita.
    "entity_id",   # `mind/watcher.py`: «l'entity_id e' ...»
    "logger",      # `mind/watcher.py`: la chiave con cui HA deduplica
    "runner",      # `mind/observer.py`: «il runner vero»
    # Citazioni di codice che il ripulitore non vede perche' i backtick si
    # aprono su una riga e si chiudono sulla successiva. E' un limite
    # dichiarato: chiudere anche quelle vorrebbe dire ricostruire il testo del
    # docstring intero, e il guadagno non vale la macchina.
    "log_entries",
    "self",
})


def _identificatori(albero: ast.Module) -> set[str]:
    """Ogni nome DEFINITO nel file: funzioni, classi, assegnazioni, parametri."""
    nomi: set[str] = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomi.add(nodo.name)
            args = getattr(nodo, "args", None)
            if args is not None:
                for a in (list(args.args) + list(args.kwonlyargs)
                          + list(args.posonlyargs)):
                    nomi.add(a.arg)
        elif isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Store):
            nomi.add(nodo.id)
    return nomi


def _righe_prosa(testo: str) -> list[tuple[int, str]]:
    """Le righe di commento e di docstring, col loro numero."""
    righe = testo.split("\n")
    fuori: list[tuple[int, str]] = []
    in_docstring = False
    for numero, riga in enumerate(righe, start=1):
        spoglia = riga.strip()
        aperta_chiusa = spoglia.count('"""') >= 2
        if in_docstring or spoglia.startswith("#") or aperta_chiusa:
            fuori.append((numero, riga))
        if spoglia.count('"""') == 1:
            in_docstring = not in_docstring
            if in_docstring:
                fuori.append((numero, riga))
    return fuori


def _prosa_spogliata(riga: str) -> str:
    """La riga senza cio' che e' citato: backtick, virgolette, percorsi."""
    riga = re.sub(r"`[^`]*`", " ", riga)
    riga = re.sub(r"«[^»]*»", " ", riga)
    riga = re.sub(r'"[^"]*"', " ", riga)
    riga = re.sub(r"\b[\w./]+\.(py|js|md|db|yaml)\b", " ", riga)
    return riga


def _sembra_italiana(riga: str) -> bool:
    parole = {p.strip(".,;:()[]").lower() for p in riga.split()}
    return len(parole & _PAROLE_FUNZIONALI) >= 2


def _residui() -> dict[str, str]:
    """`{identificatore: "file:riga"}` per ogni residuo trovato."""
    trovati: dict[str, str] = {}
    for cartella in _PERIMETRO:
        for percorso in sorted((ROOT / cartella).glob("*.py")):
            testo = percorso.read_text(encoding="utf-8")
            try:
                albero = ast.parse(testo)
            except SyntaxError:  # pragma: no cover - il file non compila
                continue
            nomi = {n for n in _identificatori(albero)
                    if len(n) >= _TROPPO_CORTI and n.lower() not in _PAROLE_DOMINIO
                    and not n.isupper()}
            if not nomi:
                continue
            cercati = re.compile(r"(?<![\w`])(" + "|".join(
                sorted(map(re.escape, nomi), key=len, reverse=True)) + r")(?![\w`])")
            for numero, riga in _righe_prosa(testo):
                nuda = _prosa_spogliata(riga)
                if not _sembra_italiana(nuda):
                    continue
                for trovato in cercati.findall(nuda):
                    chiave = f"{trovato}"
                    trovati.setdefault(
                        chiave,
                        f"{percorso.relative_to(ROOT).as_posix()}:{numero}")
    return trovati


def test_nessun_identificatore_NUDO_dentro_una_frase_italiana():
    """Il cancello. Uguaglianza esatta nelle due direzioni.

    Provato per mutazione: rimesso «i 22 giorni di raw_attributes» al posto di
    «i 22 giorni di grezzo» in `mind/facts.py` -- questa prova va rossa col
    nome nell'elenco; ripristinato, torna verde.
    """
    trovati = _residui()
    nuovi = sorted(set(trovati) - _RESIDUI_NOTI)
    spariti = sorted(_RESIDUI_NOTI - set(trovati))

    assert not nuovi, (
        "identificatori nudi dentro una frase italiana: "
        + ", ".join(f"{n} ({trovati[n]})" for n in nuovi)
        + " -- quasi sempre e' il residuo di una rinomina fatta con una "
          "espressione regolare che ha toccato la prosa invece del solo "
          "codice. Se la parola e' citata apposta, mettila fra backtick come "
          "fa il resto del progetto; se e' un residuo, ripristina la parola "
          "italiana.")
    assert not spariti, (
        f"residui dichiarati e non piu' presenti: {spariti} -- sono stati "
        "corretti (bene): toglili da `_RESIDUI_NOTI`.")
