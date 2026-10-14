"""Il vocabolario condannato di `CLAUDE.md` non torna nel prodotto (T-11).

`CLAUDE.md`, tabella «Cosa è condannato dal refactor»: il **vocabolario**
«Sentinella», «Agentbot», «Persona», «Lente» -- tre nomi per una cosa sola,
che «resta **agente**». Questa prova e' il cancello di quella riga.

**L'elenco si chiede a `CLAUDE.md`, non si ricopia** (I-0): le parole sono
quelle fra «» nella riga della tabella che nomina il vocabolario. Se il
proprietario ne aggiunge una, entra qui senza toccare la prova.

Fino al 14/10/2026 questo file era `test_fe_rename_regression.py`, la guardia
della rinomina SP-4 (`api/agents`, `#/sentinel`, `HirisAgentsList`...): nomi di
rotte di un prodotto che non esiste piu', e una guardia che avrebbe vietato
proprio le rotte degli agenti che l'impianto prevede (③ Agenti). Decisione di
Paolo del 13/10/2026: diventa il cancello del vocabolario.

**Dove guarda.** Cio' che il prodotto dice a chi lo usa e al modello: i
letterali di stringa del Python di `hiris/app` (con le docstring), il codice
del frontend (`.js`, `.html`, `.css`) senza i commenti, e i valori dei file
YAML che entrano nell'immagine (`config.yaml`, `translations/`) senza i
commenti. **I commenti no**: raccontano la storia del codice, e la storia
nomina la Sentinella che e' uscita -- e' un fatto, non un ritorno.

**Cosa non vede, dichiarato.** Le parole si cercano intere e con le maiuscole
di `CLAUDE.md`: il nome condannato e' il nome proprio del concetto. Una
«persona» minuscola e' una parola italiana comune, e «sentinella» minuscola e'
il valore sentinella della programmazione -- tutte e due legittime. Una frase
che comincia con «Persona» verrebbe segnalata: oggi non ce n'e' nessuna.
"""
import io
import pathlib
import re
import tokenize

RADICE = pathlib.Path(__file__).resolve().parents[1]
CLAUDE_MD = RADICE / "CLAUDE.md"
APP = RADICE / "hiris" / "app"
YAML = [RADICE / "hiris" / "config.yaml",
        *sorted((RADICE / "hiris" / "translations").glob("*.yaml"))]

_COMMENTO_JS = re.compile(r"/\*.*?\*/|<!--.*?-->|(?<![:\\])//[^\n]*", re.DOTALL)


def parole_condannate(testo: str) -> list[str]:
    """Le parole fra «» della riga della tabella che nomina il vocabolario."""
    for riga in testo.splitlines():
        celle = [c.strip() for c in riga.strip().strip("|").split("|")]
        if riga.lstrip().startswith("|") and "**vocabolario**" in celle[0]:
            return re.findall(r"«([^»]+)»", celle[0])
    return []


def _stringhe_python(sorgente: str):
    for tok in tokenize.generate_tokens(io.StringIO(sorgente).readline):
        if tok.type == tokenize.STRING or tok.type == getattr(
                tokenize, "FSTRING_MIDDLE", -1):
            yield tok.start[0], tok.string


def _testi():
    """`(percorso, riga, testo)` di tutto cio' che il prodotto dice."""
    for percorso in sorted(APP.rglob("*.py")):
        for riga, testo in _stringhe_python(percorso.read_text(encoding="utf-8")):
            yield percorso, riga, testo
    for estensione in ("*.js", "*.html", "*.css"):
        for percorso in sorted(APP.rglob(estensione)):
            sorgente = percorso.read_text(encoding="utf-8")
            # I commenti diventano spazi lunghi uguali: le righe restano vere.
            pulito = _COMMENTO_JS.sub(
                lambda m: re.sub(r"[^\n]", " ", m.group(0)), sorgente)
            for riga, testo in enumerate(pulito.splitlines(), start=1):
                yield percorso, riga, testo
    for percorso in YAML:
        for riga, testo in enumerate(
                percorso.read_text(encoding="utf-8").splitlines(), start=1):
            yield percorso, riga, testo.split(" #")[0] if not testo.lstrip().startswith("#") else ""


def test_l_elenco_si_legge_davvero_da_claude_md():
    """Una derivazione rotta svuota l'elenco, e un cancello senza parole passa
    sempre. Mutazione ESEGUITA (14/10/2026): tolto «**vocabolario**» dalla
    riga di `CLAUDE.md` -- rossa qui (elenco vuoto)."""
    parole = parole_condannate(CLAUDE_MD.read_text(encoding="utf-8"))

    assert len(parole) >= 1, "nessuna parola condannata letta da CLAUDE.md"
    assert all(p and " " not in p for p in parole), parole


def test_una_parola_aggiunta_a_claude_md_entra_nel_cancello():
    """La mutazione della fonte, sulla funzione che la legge: una parola nuova
    nella riga entra senza toccare la prova."""
    riga = "| **vocabolario** «Sentinella», «Agentbot», «Nuova» | resta **agente** |"

    assert parole_condannate(riga) == ["Sentinella", "Agentbot", "Nuova"]


def test_il_prodotto_non_usa_il_vocabolario_condannato():
    """Mutazioni ESEGUITE (14/10/2026), rosse con il file e la riga: «Lente»
    in una stringa di `agent/prompts.py`; «Sentinella» in un testo di
    `static/config/settings-route.js`. Verde con la stessa parola dentro un
    commento dei due file."""
    parole = parole_condannate(CLAUDE_MD.read_text(encoding="utf-8"))
    cerca = re.compile(r"\b(" + "|".join(map(re.escape, parole)) + r")\b")

    trovate = [f"{p.relative_to(RADICE)}:{riga}: {m.group(1)}"
               for p, riga, testo in _testi()
               for m in cerca.finditer(testo)]

    assert trovate == [], (
        "vocabolario condannato da CLAUDE.md (resta «agente»):\n"
        + "\n".join(trovate))
