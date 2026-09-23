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
restava fuori perche' la pagina dell'osservatore lo rendeva con
`ASPECT_LABEL` («Chi c'è»), mai verbatim.

**Aggiornato l'11/09/2026, e la ragione e' cambiata due volte in un giorno.**
`mind/baseline.py` e' stato cancellato col pavimento, e le quattro occorrenze
di `"chi c'e'"` vivono adesso in `home_space/type_vocabulary.py`. E
`ASPECT_LABEL` **non esiste piu'**: la pagina non raggruppa piu' per gamba --
mostra cosa si guarda, perche' e chi l'ha deciso (`watcher-route.js`, sezione
01). Quelle stringhe **non sono mai arrivate su nessuno schermo dopo
l'11/09/2026**, ed erano il valore interno di una metrica del vocabolario dei
tipi che nessun lettore di produzione interrogava piu' dal 17/09/2026
(`facts.genre_for` chiede il genere all'istantanea dei giudizi, spec
2026-09-16 §5). **Sono uscite del tutto il 17/09/2026**, con la gamba intera
(spec §11): questo paragrafo resta come nota storica, non come eccezione
attiva -- `home_space/type_vocabulary.py` non porta piu' nessuna occorrenza di
`"chi c'e'"` fuori da questa stessa prosa di changelog.

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
def corpo(relativo: str, nome: str) -> tuple[tuple[int, int], ...]:
    """L'intervallo di una funzione, **letto dal suo albero sintattico**.

    `ancora()` qui sotto fissa l'INIZIO al contenuto e poi conta le righe: e'
    mezza cura, e il 23/09/2026 si e' visto quanto mezza. `apply` e' cresciuta
    di quindici righe di docstring, l'ancora ne contava ancora 121, e **le
    ultime quindici righe della funzione hanno smesso di essere sorvegliate**
    senza che niente arrossisse — un cancello cieco proprio sulla coda, dove
    una funzione mette le frasi che l'utente legge.

    Un intervallo che si ricalcola all'inizio ma non alla fine invecchia
    esattamente come uno scritto a mano: piu' lentamente, e in silenzio.

    Se la funzione non si trova **si solleva**, per la stessa ragione per cui
    si solleva `ancora`.
    """
    import ast

    albero = ast.parse((APP / relativo).read_text(encoding="utf-8"))
    for nodo in ast.walk(albero):
        if (isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                and nodo.name == nome):
            return ((nodo.lineno, nodo.end_lineno),)
    raise AssertionError(
        f"la funzione «{nome}» non esiste piu' in {relativo}: se e' stata "
        "rinominata, aggiorna questa riga — non lasciare il cancello cieco")


def ancora(relativo: str, testo: str, *, quante: int) -> tuple[tuple[int, int], ...]:
    """L'intervallo che comincia alla riga che CONTIENE `testo`.

    Un numero di riga scritto a mano invecchia alla prima riga aggiunta sopra,
    e il cancello si mette a sorvegliare un'altra frase senza dirlo. Qui
    l'intervallo si ricalcola a ogni corsa.

    Se l'ancora non si trova **si solleva**: un intervallo vuoto renderebbe
    questo cancello cieco proprio sul file che aveva piu' bisogno di lui.
    """
    righe = (APP / relativo).read_text(encoding="utf-8").splitlines()
    for numero, riga in enumerate(righe, start=1):
        if testo in riga:
            return ((numero, numero + quante - 1),)
    raise AssertionError(
        f"ancora «{testo}» non trovata in {relativo}: se quel codice e' "
        "cambiato, scegli una nuova ancora — non lasciare il cancello cieco")


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
    # una con un'elisione dritta iniettata DENTRO UNA STRINGA di ciascuno dei
    # cinque intervalli -- anche i due non spostati, perche' «non l'ho
    # toccato» e' un'ipotesi come le altre: il cancello arrossisce in 5 casi
    # su 5. La mutazione va messa in una stringa e mai in un commento: li' e'
    # inerte, e la verifica direbbe «coperto» senza aver verificato niente.
    # `_helper_entities` resta FUORI:
    # le sue uniche stringhe sono `logger.warning` con segnaposto, e la frase
    # che il proprietario legge la compone `apply`, dentro il suo intervallo.
    # **Erano cinque intervalli a NUMERI, e sono scivolati una terza volta**
    # (23/09/2026, fetta 8): cinquantuno righe aggiunte in cima al file --
    # `FRASE_MAX` e `_aggiungi_frase` per il reperto B-5 -- hanno spostato
    # tutto piu' giu', e il cancello ha cominciato a sorvegliare due frasi che
    # nessuno aveva toccato (`logger.warning` dell'etichetta, e il rifiuto di
    # `richiesto`). Esattamente cio' che il commento qui sotto racconta essere
    # successo due volte il 22/09 su `agent/runner.py` -- e la cui cura era
    # gia' scritta, in questo stesso file, quindici righe piu' giu'.
    #
    # Una cura scritta e non applicata dove serviva e' una cura che non c'e'.
    # Adesso tutti e cinque gli intervalli si ANCORANO al loro contenuto.
    "action/construction/workshop.py": (
        # ARTICOLO_INDETERMINATIVO / ARTICOLO_DETERMINATIVO
        *ancora("action/construction/workshop.py",
                "ARTICOLO_INDETERMINATIVO", quante=7),
        # Le quattro funzioni si leggono dall'ALBERO, non si contano: vedi
        # `corpo()` per cosa e' costato contarle.
        *corpo("action/construction/workshop.py", "_preview"),
        *corpo("action/construction/workshop.py", "apply"),
        *corpo("action/construction/workshop.py", "restore"),
        *corpo("action/construction/workshop.py", "_translate_rejection"),
    ),
    "action/construction/revisions.py": ((254, 255),),     # risana (solo `reason`)
    # **Si ANCORA, non si conta** (22/09/2026, seconda volta in un giorno).
    #
    # Qui c'erano due numeri di riga, e due volte nello stesso giorno sono
    # scivolati su una frase che non dovevano sorvegliare -- perche' qualcuno
    # aveva aggiunto righe piu' in alto in `agent/runner.py`. Il cancello
    # arrossiva su un testo che nessuno aveva toccato: rumore, non difesa, e
    # rumore che insegna a non guardarlo.
    #
    # `ancora()` trova la riga dal suo CONTENUTO e sorveglia quella piu' le
    # sei che seguono -- il ramo `rc != 0`, dove il `detail` finisce nella
    # reply. Cio' che si sposta resta sorvegliato da solo.
    # L'ancora e' la riga del `log.warning` del ramo `rc != 0`: da li' in giu'
    # si compone il `detail` che finisce nella REPLY. La riga sopra
    # (`log_tail`) resta fuori apposta: e' coda di un log, non testo che
    # l'utente legge -- ed era fuori anche prima, con i numeri.
    "agent/runner.py": ancora("agent/runner.py", 'log.warning("claude rc=',
                              quante=7),
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
        # 1062-1065, non piu' 1056-1059: rinumerato il 09/09/2026 quando il
        # docstring di `chat_stream` (audit delle fondamenta, rilievo 8) e'
        # cresciuto di 6 righe sopra questo punto. Ancora per contenuto
        # (`err = (` prima della f-string), non offset.
        (1062, 1065),  # err, 402 OpenRouter (stream)
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
    # Intervalli rinumerati il 09/09/2026 (rilievo 7 sotto soglia dell'audit
    # delle fondamenta: `_not_seen`/`_no_change` guadagnano un ramo
    # `listened=False`, +25 righe). ANCORE, non offset: ritrovate per
    # contenuto (`grep` sulle costanti/funzioni nominate) e verificate
    # iniettando un'elisione dritta DENTRO UNA STRINGA di ciascuno dei
    # cinque intervalli, compreso `_not_seen` con ENTRAMBI i suoi rami --
    # il cancello arrossisce in 5 casi su 5.
    "action/actuator.py": (
        (137, 139),    # _BLIND_MIRROR
        (150, 153),    # _NO_TARGET_RESOLVER
        (193, 205),    # _not_seen -- entrambi i rami, listened=False e =True
        (227, 231),    # _CHANGED_NOT_SHOWABLE
        (242, 244),    # _NO_STATE_TO_REREAD
        (557, 559),    # _open_listen: l'annuncio di ascolto assente
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


def test_l_intervallo_di_runner_si_DERIVA_e_non_si_scrive():
    """**La proprieta' che una prova di comportamento non puo' vedere.**

    Rimettendo due numeri di riga al posto dell'ancora, il cancello sorveglia
    altre righe -- magari innocue -- e resta verde: ha guardato qualcosa, solo
    non quello che doveva. E' successo due volte in un giorno con i numeri
    scritti a mano, ed e' il motivo per cui l'ancora esiste.

    Si guarda la FORMA, come per le porte di scrittura dell'attuatore.

    Mutazione ESEGUITA: `((1, 7),)` al posto dell'ancora -- rossa (prima era
    verde: il cancello sorvegliava il docstring del modulo e taceva)."""
    import pathlib as _p

    sorgente = _p.Path(__file__).read_text(encoding="utf-8")
    # La riga della TABELLA, non quella di questa prova: il criterio e' che
    # porti un valore (`: ancora(...)` oppure `: ((...`), perche' la riga qui
    # sotto nomina la stessa chiave per cercarla.
    riga = [r for r in sorgente.splitlines()
            if r.lstrip().startswith('"agent/runner.py": ')]

    assert len(riga) == 1, f"la voce di runner.py non e' piu' una sola: {riga}"
    assert "ancora(" in riga[0], (
        "l'intervallo di `agent/runner.py` e' tornato a essere scritto a mano: "
        "scivolera' alla prima riga aggiunta sopra, e il cancello sorveglierA' "
        "una frase che non doveva -- e' gia' successo due volte")


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
