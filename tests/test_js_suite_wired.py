import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Review finale pre-1.0, finding m10: questo file verificava solo che
# "npm test" comparisse DA QUALCHE PARTE nel testo del workflow CI e che
# la cartella tests/js contenesse ALMENO UN file .test.mjs -- un cieco
# angolo morto. `npm test` esce con codice 0 anche se lo script `test` di
# package.json punta a un glob che non combacia con NULLA (node --test su
# zero file non fallisce), quindi: 1) uno script "test" neutralizzato
# (es. sostituito con un no-op silenzioso) o 2) una cancellazione di massa
# dei file *.test.mjs (fuori dalla singola glob-non-vuota già controllata)
# passerebbero comunque questo controllo E farebbero girare CI verde senza
# eseguire alcun test JS comportamentale reale. Fix: legge lo script
# "test" EFFETTIVO da package.json (non solo cerca "npm test" come
# sottostringa nel workflow) e verifica un numero minimo di file
# *.test.mjs, non solo "almeno uno".
#
# fetta E5 Task 8: la soglia era 10 ed e' stata RIANCORATA a 8, non abbassata
# per far passare la suite. Il fatto che questa guardia sia scattata e' il suo
# lavoro: va spiegato, non aggiustato in silenzio.
#   - la soglia fu scritta quando `static/` conteneva il workbench intero
#     (Chatbot, Agentbot, wizard, Task, Proposte, Gateway, Designer);
#   - la fetta E5 lo fa uscire per intero, e con esso i test che avevano quei
#     file come soggetto. A HEAD del Task 6 i file erano esattamente 10 --
#     la soglia era gia' al pelo;
#   - il Task 8 ne toglie 3 (`dashboard-feed-new`, `dashboard-proposals-apply`,
#     `labels-dict`), ciascuno visto fallire per costruzione prima della
#     cancellazione, e ne aggiunge 1 (`dashboard-conoscenza`): 8.
# La soglia resta ANCORATA AL CONTEGGIO REALE, cioe' massimamente stretta:
# cosi' continua a fare cio' per cui e' nata (rompersi su una cancellazione di
# massa) invece di diventare un margine dentro cui si puo' erodere la suite
# senza che nessuno se ne accorga. Chi la riabbassa deve scrivere qui perche',
# come e' stato fatto ora.
#
# fetta «l'accoppiamento» (22/09/2026): la soglia era rimasta a 12 mentre i file
# erano diventati 36 -- un margine di ventiquattro file cancellabili in silenzio,
# cioe' la guardia spenta per erosione invece che per decisione, esattamente cio'
# che il paragrafo qui sotto vieta. Piu' `services-route.test.mjs`, che questa
# fetta aggiunge: 36 + 1 = 37, CONTATO (`ls tests/js/*.test.mjs | wc -l`), non
# incrementato a mano. Chi aggiunge o toglie un file conta di nuovo.
#
# fetta «la catena diventa l'unica verita'» Task 2: la soglia era rimasta a 8
# mentre i file erano diventati 11 -- tre file aggiunti dopo la riancora
# (`chat-page`, `chat-usage-widget`, `chat-usage-non-measured`) senza rialzarla,
# cioe' un margine di 3 file cancellabili in silenzio: esattamente cio' che il
# paragrafo qui sopra vieta. Piu' `models-route.test.mjs`, che questo task
# aggiunge (la pagina #/models non aveva alcun test comportamentale, ed e' la
# pagina che questa fetta riscrive): 11 + 1 = 12. Il numero e' CONTATO, non
# incrementato a mano -- chi aggiunge o toglie un file conta di nuovo.
#
# Il conteggio instabile di `npm test` (07/10/2026): la soglia era rimasta a 37
# mentre i file erano 42 -- cinque cancellabili in silenzio. Piu'
# `conteggio-prove.test.mjs`, che questa fetta aggiunge: 43, CONTATO
# (`ls tests/js/*.test.mjs | wc -l`).
_MIN_JS_TEST_FILES = 43


def _js_test_files():
    return list((ROOT / "tests" / "js").glob("*.test.mjs"))


def test_js_test_suite_exists_and_is_ci_wired():
    assert (ROOT / "package.json").exists()
    assert _js_test_files(), "nessun test JS comportamentale"
    ci = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "npm test" in ci, "i test JS devono girare in CI"


def test_npm_test_script_actually_targets_the_js_test_suite():
    """`npm test` esce 0 anche se il glob non combacia con nessun file
    (node --test su zero file è un successo vuoto) -- uno script "test"
    svuotato/neutralizzato (es. "echo skip" o "exit 0") farebbe comunque
    passare test_js_test_suite_exists_and_is_ci_wired sopra (che guarda
    solo il testo del workflow, non lo script reale) e la CI resterebbe
    verde senza eseguire un solo test JS. Verifica lo script effettivo."""
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    script = pkg.get("scripts", {}).get("test", "")
    # `node` con `--test` fra le opzioni, non la sottostringa "node --test":
    # dal 07/10/2026 fra i due sta `--import` (vedi la prova qui sotto).
    argomenti = script.split()
    assert argomenti[:1] == ["node"] and "--test" in argomenti, (
        f'package.json scripts.test deve invocare "node --test", trovato: {script!r}'
    )
    assert "tests/js" in script and ".test.mjs" in script, (
        f'package.json scripts.test deve puntare al glob tests/js/*.test.mjs, trovato: {script!r}'
    )


def test_npm_test_non_perde_le_prove_e_confronta_il_conteggio():
    """Il conteggio instabile di `npm test` (BACKLOG, 05/10/2026; causa
    trovata il 07/10/2026). Con `--test-force-exit` ogni figlio esce appena
    l'ultima prova finisce, e sulle pipe POSIX le sue scritture sono
    asincrone: gli esiti di coda si perdevano senza nessuna rossa (misurato:
    553, 551 e 552 su 638 col padre rallentato). `uscita-intera.mjs` rende
    bloccante l'uscita, in ogni processo; il reporter `conteggio-prove.mjs`
    confronta le prove raccolte col giro prima, e deve stare su una
    destinazione sua (stderr), o la sua riga si perde con `--test-force-exit`."""
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    argomenti = pkg["scripts"]["test"].split()
    assert "--import" in argomenti
    assert argomenti[argomenti.index("--import") + 1] == "./tests/js/helpers/uscita-intera.mjs"
    # `--import` va prima di `--test`: dopo, node lo passerebbe come file da
    # provare, e i figli non lo riceverebbero fra i propri `execArgv`.
    assert argomenti.index("--import") < argomenti.index("--test")
    def valori(opzione):
        return [a.split("=", 1)[1] for a in argomenti if a.startswith(opzione + "=")]

    dove = dict(zip(valori("--test-reporter"), valori("--test-reporter-destination"), strict=True))
    conteggio = dove.pop("./tests/js/helpers/conteggio-prove.mjs", None)
    assert conteggio is not None, dove
    assert conteggio not in dove.values(), dove


def test_js_test_suite_has_a_minimum_number_of_behavioural_test_files():
    """Non solo "almeno un file esiste" (un mass-delete che ne lascia UNO
    residuo passerebbe comunque quel controllo) -- una soglia minima che
    una cancellazione di massa dei test JS comportamentali deve rompere."""
    files = _js_test_files()
    assert len(files) >= _MIN_JS_TEST_FILES, (
        f"attesi almeno {_MIN_JS_TEST_FILES} file *.test.mjs in tests/js, trovati {len(files)} "
        f"({sorted(f.name for f in files)}) -- possibile cancellazione di massa dei test JS"
    )


def test_js_deps_are_not_shipped_in_the_image():
    df = (ROOT / "hiris" / "Dockerfile").read_text(encoding="utf-8")
    assert "package.json" not in df and "node_modules" not in df
