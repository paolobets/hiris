"""L'apostrofo dritto non torna nell'elisione che il proprietario legge.

Il collaudo del 07/09/2026 (U7) aveva ragione sul fatto ma sbagliava il
rimedio: «viene dal server, si corregge in un posto solo» e' falso. L'analisi
per la fetta 9 ha misurato **541 occorrenze di elisione con l'apostrofo
dritto** (`l'`, `un'`, `dell'`...) in 44 file di `hiris/app/**/*.py`, fuori
dai docstring. La maggioranza -- `home_space/tools.py`, `agent/prompts.py`,
`claude_runner.py`, la gran parte di `server.py`, tutto `home_space/
ha_vocabulary.py` e `home_space/historian.py` -- e' testo che legge SOLO il
modello (descrizioni di strumenti, prompt di sistema, righe di log): cambiarlo
e' rumore, non un miglioramento, e rischia di far divergere una prova che
confronta stringhe con il modello.

**Il confine vero non e' il file, e' la singola stringa.** Anche dentro un
modulo "del proprietario" convivono log (`logger.warning(...)`, mai a
schermo) e testo che arriva davvero su una pagina o in una risposta di chat.
Anche dentro un modulo "del modello" (`action/construction/workshop.py`,
`action/construction/advisor.py`) una funzione sola puo' avere un ramo che
finisce in un tool-result e un altro che finisce, verbatim, nell'anteprima
della pagina Costruzioni o nel `motivo` della pagina Promesse. Questa e' la
ragione per cui la guardia sotto non scansiona semplicemente "questi file":
scansiona gli INTERVALLI DI RIGHE gia' verificati, uno per uno, guardando
davvero chi chiama quella funzione (grep dei chiamanti, lettura degli
handler, lettura del frontend che la mostra) prima di dichiararli.

**Cosa sorveglia, e cosa no -- dichiarato, non promesso.**

- File interi, perche' non hanno un secondo canale verso il modello:
  `home_space/briefing.py` (il nucleo esce anche crudo da `/api/briefing`,
  letto dal proprietario per verificare che HIRIS guardi la casa giusta),
  `model_resolution.py` (pagina Modelli + nota di ripiego in chat),
  `usage/vocabulary.py` e le rotte HTTP di sola pagina
  `api/handlers_settings.py`, `api/handlers_usage.py`,
  `api/handlers_memory.py`, `api/handlers_agenda.py`,
  `api/handlers_constructions.py`, e `keeper/sweeper.py` (le note del
  ripiego/della mancata notifica finiscono nel `motivo` della pagina
  Promesse, mai in un prompt).
- Funzioni o blocchi precisi dentro file misti, dove il resto del file resta
  FUORI dalla sorveglianza apposta: `action/construction/workshop.py`
  (`ARTICOLO_INDETERMINATIVO`/`ARTICOLO_DETERMINATIVO`, `_preview`, `apply`,
  `restore`, `_translate_rejection` -- **non** `propose`, i cui rifiuti
  precoci non toccano mai l'archivio e restano un tool-result),
  `action/construction/advisor.py` (`consiglia`, **solo dalla riga 43 in poi**
  -- il ramo "non ho capito cosa dovrebbe fare" alla riga 39 ritorna PRIMA che
  `propose()` arrivi a salvare l'anteprima, quindi resta un tool-result e non
  e' sorvegliato), `action/construction/revisions.py` (`risana`),
  `keeper/store.py` (`cancel`, `risana` -- **non** `create`, dove l'errore di
  validazione lo legge solo il modello), `keeper/promise.py`
  (`delay_reason` -- **non** `validate`, il cui stesso docstring dichiara
  «chi la riceve e' uno strumento che parla a un modello»), `keeper/
  exchange.py` (`interpreta_promise`, `_downgrade_note` -- **non**
  `_system_prompt`, `_domanda`, `CONCLUDI_TOOL_DEF`, che sono prompt),
  `home_space/topology.py` (`_compare_area`, il cui `errore` esce grezzo da
  `/api/home-space`), `agent/runner.py` (solo le 5 righe della frase «flusso
  incompleto» che finiscono nella reply -- il resto della funzione che le
  contiene, `_reason_chat`, e' quasi tutto log), `backends/
  openai_compat_runner.py` (`TOOL_LEAK_USER_MSG` e i due messaggi di
  `RunnerBackendError`/`err` per i 402 di OpenRouter, che diventano la
  risposta di chat quando il backend fallisce -- non il resto del file, che e'
  runner per il modello), `api/handlers_chat.py` (i tre `web.json_response`
  con un `error`/`message` letterale -- non il `logger.warning` alla riga 423,
  che e' un log), `action/actuator.py` (`_BLIND_MIRROR`, `_NO_TARGET_
  RESOLVER`, `_not_seen`, `_CHANGED_NOT_SHOWABLE`, `_NO_STATE_TO_REREAD`, e
  il log di `_open_listen` -- **non** il resto del file: `_states`,
  `_preview`, `_record`, `_no_change`, l'esecuzione vera e propria, che sono
  log o campi della cronaca che la pagina non rende).

**Rilievo R2 della revisione indipendente (07/09), chiuso.** Il confine
dichiarava `action/actuator.py` fuori sorveglianza per intero, e sei
stringhe della sua cronaca (`errore`/`avviso`) uscivano verbatim su Impegni
(«Cosa e' cambiato», `agenda-route.js:228,238`) e come `motivo` di un `fai`
fallito (`agenda-route.js:259`). Corrette le sei elisioni, e allargato
`SORVEGLIATO` alle funzioni che le portano davvero -- **non** a tutto il
file: `_states`/`_preview`/`_record`/`_no_change`/l'esecuzione restano
fuori, log e campi che la pagina non rende. Riscansionate le 189 stringhe
fuori registro degli altri 31 file (stessa regex, fuori da `SORVEGLIATO`):
sono log con segnaposto (`%s`/`%r`/`%d`), prompt di sistema, o `{"errore":
...}` che torna al modello attraverso `ToolDispatcher` -- **nessun'altra**
raggiunge uno schermo. `mind/baseline.py` (`"chi c'e'"`, quattro occorrenze)
resta fuori per la stessa ragione gia' scritta sopra: la pagina lo rende con
`ASPECT_LABEL` (`watcher-route.js:136`, «Chi c'è»), mai verbatim.

**Il limite dichiarato.** Questa lista e' stata costruita leggendo il
codice l'8/09/2026, non derivata da un criterio che il codice esponga: non
esiste, oggi, un modo automatico di sapere se una stringa python arriva su
uno schermo. Una funzione NUOVA in uno di questi file, o un ramo nuovo dentro
una funzione gia' sorvegliata ma FUORI dall'intervallo dichiarato, non e'
vista da questa prova. E il resto dei 44 file (quasi 400 occorrenze, la
grande maggioranza in `home_space/tools.py`) resta fuori per scelta, non per
dimenticanza: cambiarle sarebbe correggere testo che nessuna persona legge.
Chi tocca uno di questi file e aggiunge testo per il proprietario deve
allargare `SORVEGLIATO` sotto, dichiarando perche'.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"

# Un'elisione dritta: una lettera, l'apostrofo ASCII, un'altra lettera subito
# dopo -- "l'utente", non "utente'" (l'apostrofo di chiusura di un
# identificatore citato, quello si lascia stare: dopo di lui non c'e' mai una
# lettera) e non "e'"/"gia'"/"perche'" (l'accento sostituito con l'apostrofo
# a fine parola: un'altra convenzione di questo codice, gia' sorvegliata da
# `tests/js/watcher-route.test.mjs` per il frontend, FUORI dal perimetro di
# questa prova).
ELISIONE_DRITTA_RE = re.compile(r"[A-Za-zÀ-ÿ]+'(?=[A-Za-zÀ-ÿ])")

WHOLE_FILE: tuple[tuple[int, int], ...] | None = None

# file (relativo a hiris/app) -> None (tutto il file) oppure lista di
# intervalli di riga INCLUSIVI gia' verificati come testo per il proprietario.
SORVEGLIATO: dict[str, tuple[tuple[int, int], ...] | None] = {
    "home_space/briefing.py": WHOLE_FILE,
    "model_resolution.py": WHOLE_FILE,
    "usage/vocabulary.py": WHOLE_FILE,
    "proxy/entity_cache.py": WHOLE_FILE,
    "proxy/state_translations.py": WHOLE_FILE,
    "api/handlers_settings.py": WHOLE_FILE,
    "api/handlers_usage.py": WHOLE_FILE,
    "api/handlers_memory.py": WHOLE_FILE,
    "api/handlers_agenda.py": WHOLE_FILE,
    "api/handlers_constructions.py": WHOLE_FILE,
    "keeper/sweeper.py": WHOLE_FILE,
    "keeper/store.py": ((209, 234), (261, 268)),  # cancel, risana (solo REASON_FAI/CHIEDI)
    "keeper/promise.py": ((206, 215),),                    # delay_reason
    "keeper/exchange.py": ((147, 211), (244, 263)),        # interpreta_promise, _downgrade_note
    "home_space/topology.py": ((1332, 1371),),             # _compare_area
    "action/construction/advisor.py": ((73, 123),),        # consiglia, dopo il primo ritorno
    # Intervalli rinumerati l'09/09/2026 (rilievo 9 dell'audit delle
    # fondamenta: `apply` cresce di 13 righe e `_helper_entities` ne aggiunge
    # 77 sopra `_label`). ANCORE ritrovate per contenuto e verificate una per
    # una con un'elisione dritta iniettata dentro ciascun intervallo nuovo --
    # il cancello arrossisce in 5 casi su 5. `_helper_entities` resta FUORI:
    # le sue uniche stringhe sono `logger.warning` con segnaposto, e la frase
    # che il proprietario legge la compone `apply`, dentro il suo intervallo.
    "action/construction/workshop.py": (
        (64, 70),      # ARTICOLO_INDETERMINATIVO / ARTICOLO_DETERMINATIVO
        (288, 324),    # _preview
        (328, 448),    # apply
        (723, 773),    # restore
        (856, 872),    # _translate_rejection
    ),
    "action/construction/revisions.py": ((254, 255),),     # risana (solo `reason`)
    "agent/runner.py": ((1612, 1618),),  # la frase "flusso incompleto" nella reply
    # Intervalli rinumerati l'09/09/2026 (rilievo 8 dell'audit delle
    # fondamenta: `_cache_counts` entra a livello di modulo, sopra la classe,
    # e sposta di 40 righe tutto cio' che sta sotto). Sono ANCORE, non offset:
    # ritrovate per contenuto e verificate una per una iniettando un'elisione
    # dritta all'inizio di ciascun intervallo nuovo -- il cancello arrossisce
    # in 3 casi su 3. Un intervallo rimasto indietro non fa rumore: perde la
    # copertura in silenzio, ed e' il danno peggiore.
    "backends/openai_compat_runner.py": (
        (157, 162),    # TOOL_LEAK_USER_MSG
        (785, 788),    # RunnerBackendError, 402 OpenRouter (non-stream)
        (1056, 1059),  # err, 402 OpenRouter (stream)
    ),
    "api/handlers_chat.py": (
        (498, 502),    # nessun altro provider dopo la scadenza del ponte
        (753, 756),    # 409, risposta gia' in arrivo
        (808, 817),    # nessun provider AI configurato
    ),
    # Rilievo R2 della revisione indipendente sul tratto `v3.22.2..HEAD`:
    # il confine dichiarava questo file fuori sorveglianza per intero, ma sei
    # stringhe della cronaca (`errore`/`avviso`) escono verbatim su Impegni
    # («Cosa e' cambiato», `agenda-route.js:228,238`) e come `motivo` di un
    # `fai` fallito (`agenda-route.js:259`, che legge `esito.errore`). Le
    # altre funzioni del file (`_states`, `_preview`, `_record`, l'esecuzione
    # vera e propria) restano fuori: sono log, o campi che la cronaca porta
    # ma la pagina non rende (`entity_before`/`entity_after`).
    # Intervalli rinumerati il 07/09/2026 (fetta dell'eredita' degli
    # attributi): `_fingerprint` e i suoi import si sono allungati e ogni
    # ancora si e' spostata piu' in basso. Sono ANCORE, non offset: ognuna e'
    # stata ritrovata per contenuto, non traslata a occhio -- e la prova qui
    # sotto (`..._la_guardia_vede_davvero_dentro_actuator_appena_allargata`)
    # e' esattamente cio' che scopre un intervallo rimasto indietro.
    "action/actuator.py": (
        (137, 139),    # _BLIND_MIRROR
        (150, 153),    # _NO_TARGET_RESOLVER
        (184, 189),    # _not_seen
        (202, 206),    # _CHANGED_NOT_SHOWABLE
        (217, 219),    # _NO_STATE_TO_REREAD
        (532, 534),    # _open_listen: l'annuncio di ascolto assente
    ),
}


def _docstring_linenos(tree: ast.AST) -> set[int]:
    """Le righe di ogni docstring del modulo -- mai testo per il proprietario,
    sempre per chi legge il sorgente."""
    righe: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            corpo = node.body
            if (corpo and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)):
                costante = corpo[0].value
                righe.update(range(costante.lineno, costante.end_lineno + 1))
    return righe


def _elisioni_dritte(sorgente: str, nome: str,
                     intervalli: tuple[tuple[int, int], ...] | None) -> list[str]:
    """Le stringhe (non docstring) nell'intervallo dichiarato che portano
    un'elisione con l'apostrofo dritto. Una lista vuota e' il verde.

    Pura: prende il TESTO del modulo, non il file. La prova della mutazione
    (sotto) costruisce una versione alterata solo in memoria -- mai un
    guasto sul disco vero, nemmeno se il test si interrompe a meta'."""
    albero = ast.parse(sorgente, filename=nome)
    docstring_righe = _docstring_linenos(albero)
    trovate = []
    for node in ast.walk(albero):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if node.lineno in docstring_righe:
            continue
        if intervalli is not None and not any(
                inizio <= node.lineno <= fine for inizio, fine in intervalli):
            continue
        if ELISIONE_DRITTA_RE.search(node.value):
            trovate.append(f"{nome}:{node.lineno}: {node.value[:90]!r}")
    return trovate


def _elisioni_dritte_in(path: Path, intervalli: tuple[tuple[int, int], ...] | None) -> list[str]:
    return _elisioni_dritte(path.read_text(encoding="utf-8"), path.name, intervalli)


def test_nessuna_elisione_dritta_nel_testo_sorvegliato_del_proprietario():
    """La prova che regge nel tempo: cambia una `’` in `'` in una delle righe
    sorvegliate e questa prova arrossisce -- senza dover rileggere il capitolo
    apposta."""
    difetti: list[str] = []
    for relativo, intervalli in SORVEGLIATO.items():
        difetti.extend(_elisioni_dritte_in(APP / relativo, intervalli))
    assert difetti == [], (
        "elisione con l'apostrofo dritto trovata nel testo per il proprietario:\n"
        + "\n".join(difetti)
    )


def test_la_guardia_arrossisce_davvero_su_un_elisione_dritta_iniettata():
    """La mutazione dichiarata dal capitolato: senza questo test, il test
    sopra potrebbe essere verde perche' non guarda mai dentro le stringhe
    giuste (un `SORVEGLIATO` vuoto per errore, un regex che non compila
    davvero, un controllo saltato). Qui si inietta l'errore vero -- lo stesso
    che la fetta 9 ha corretto -- in una STRINGA, mai nel file su disco, e si
    chiede alla stessa funzione di trovarlo."""
    intatto = (APP / "model_resolution.py").read_text(encoding="utf-8")
    assert "l’ultima richiesta" in intatto, (
        "questo test presuppone che model_resolution.py sia gia' corretto: "
        "se questa asserzione fallisce, la fetta 9 e' stata disfatta altrove"
    )
    mutato = intatto.replace("l’ultima richiesta", "l'ultima richiesta", 1)
    assert mutato != intatto

    difetti = _elisioni_dritte(mutato, "model_resolution.py",
                               SORVEGLIATO["model_resolution.py"])

    assert any("ultima richiesta" in d for d in difetti), (
        "la guardia non ha visto l'elisione iniettata: e' cieca, non verde per merito"
    )


def test_la_guardia_vede_davvero_dentro_actuator_appena_allargata():
    """Rilievo R2 della revisione indipendente sul tratto `v3.22.2..HEAD`:
    non basta che `action/actuator.py` compaia in `SORVEGLIATO` -- se gli
    intervalli fossero sbagliati (spostati, invertiti, o puntati su righe di
    commento) la prova sopra resterebbe verde senza guardare davvero le
    frasi che finiscono su Impegni. Stessa disciplina della mutazione su
    `model_resolution.py`: si inietta l'errore vero -- lo stesso che questa
    correzione ha tolto da `_BLIND_MIRROR` -- in una stringa mai scritta su
    disco, dentro l'intervallo dichiarato per la funzione."""
    intatto = (APP / "action" / "actuator.py").read_text(encoding="utf-8")
    assert "l’inventario delle entita'" in intatto, (
        "questo test presuppone che _BLIND_MIRROR sia gia' corretto: se "
        "questa asserzione fallisce, la correzione R2 e' stata disfatta altrove"
    )
    mutato = intatto.replace("l’inventario delle entita'", "l'inventario delle entita'", 1)
    assert mutato != intatto

    difetti = _elisioni_dritte(mutato, "actuator.py", SORVEGLIATO["action/actuator.py"])

    assert any("inventario" in d for d in difetti), (
        "la guardia non ha visto l'elisione iniettata dentro l'intervallo di "
        "_BLIND_MIRROR: gli estremi dichiarati in SORVEGLIATO non coprono la "
        "riga vera, o non la coprivano mai"
    )
