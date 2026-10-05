"""Le specie di turno si scrivono in un posto solo: `steering` (C-28; A21).

Il letterale si cerca nell'albero sintattico di ogni modulo del prodotto (le
stringhe, non i commenti: un commento che nomina l'attuatore non e' un
doppione). I valori da cercare si CHIEDONO a `steering.SPECIE`, i file alla
cartella: nessun elenco ricopiato (CLAUDE.md, I-0).

**Tutte le specie tranne `chat`** (A21, approvata da Paolo il 05/10/2026):
`chat` e' anche un `agent_type`, il nome di un `kind` della coda e la
chiave di molte strutture, e un cancello sul suo letterale non
distinguerebbe niente. Fino al 05/10/2026 il cancello guardava solo
l'attuatore (C-28, Tappa 4, T6), e «analista», «osservatore», «ricette»,
«promessa» restavano letterali in `server.py`, `agent/runner.py`,
`mind/observer.py`, `mind/recipe_turn.py` e `keeper/exchange.py`.

`promessa` ha anche altri sensi -- il `kind` del job della coda, la chiave
`agent_type` del modello, il campo che porta la riga di una promessa -- e
quelli restano letterali: stanno in `_OTHER_SENSES`, una lista d'AMMISSIONE
con la ragione, per modulo e per conto.

Mutazione ESEGUITA (05/10/2026): rimesso `specie="attuatore"` nella misura del
turno in `server.py` -- rossa, col file e la riga. Mutazione ESEGUITA
(05/10/2026, A21): rimesso `agent="ricette"` in `declare_downgrade` di
`server.py` -- rossa, col file e la riga.
"""
import ast
from collections import Counter
from pathlib import Path

from hiris.app import steering

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"

#: Le specie sorvegliate: tutte, tranne quella che e' anche altre cose.
GUARDED = steering.SPECIE - {"chat"}

#: Lista d'AMMISSIONE: dove il letterale di una specie e' un'ALTRA parola con
#: la stessa grafia. Chiude per difetto: un posto nuovo e' rosso finche'
#: qualcuno non lo ammette qui, con la ragione.
_OTHER_SENSES = {
    ("agent/runner.py", "promessa"): (
        2, "il `kind` del job della coda (chiave di JOB_SPECIES, RAGIONABILI)"),
    ("api/handlers_reasoning.py", "promessa"): (
        1, "il `kind` del job della coda"),
    ("server.py", "promessa"): (1, "il `kind` del job della coda"),
    ("keeper/exchange.py", "promessa"): (
        2, "il `kind` con cui la promessa si accoda, e il suo `agent_type`"),
    ("claude_runner.py", "promessa"): (
        1, "la chiave `agent_type` di AUTO_MODEL_MAP"),
    ("keeper/store.py", "promessa"): (
        2, "il campo che porta la riga di una promessa"),
    ("home_space/tools.py", "promessa"): (
        5, "il campo che porta la riga di una promessa"),
    ("api/handlers_agenda.py", "promessa"): (
        2, "il campo che porta la riga di una promessa"),
}


def _modules() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if p.name != "steering.py"
                  or p.parent != APP)


def _literals(values) -> Counter:
    found = Counter()
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in values:
                found[(str(path.relative_to(APP)), node.value)] += 1
    return found


def test_specie_attuatore_appartiene_specie():
    assert steering.ACTUATOR_SPECIES in steering.SPECIE


def test_ogni_specie_sorvegliata_ha_un_nome_in_steering():
    """Una costante per specie: chi la scrive la importa, e un refuso e' un
    `NameError` invece di una misura rifiutata."""
    named = {value for name, value in vars(steering).items()
             if name.endswith("_SPECIES") and isinstance(value, str)}
    assert GUARDED <= named, sorted(GUARDED - named)


def test_specie_non_si_ricopia_fuori_steering():
    copie = {key: n for key, n in _literals(GUARDED).items()
             if (key, n) != (key, _OTHER_SENSES.get(key, (None,))[0])}
    assert copie == {}, (
        "una specie scritta come letterale invece della sua costante in "
        f"`steering` (o un altro senso non ammesso in _OTHER_SENSES): {copie}")


def test_derivazione_guarda_prodotto():
    """La prova della derivazione: i moduli ci sono, le specie sorvegliate
    sono quelle di oggi o di piu', e il letterale si trova dove c'e' (in
    `steering` stesso, escluso dalla ricerca qui sopra)."""
    assert len(_modules()) > 100
    assert len(GUARDED) >= 5, GUARDED
    in_steering = {n.value for n in ast.walk(ast.parse(
        (APP / "steering.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.Constant)}
    assert GUARDED <= in_steering
