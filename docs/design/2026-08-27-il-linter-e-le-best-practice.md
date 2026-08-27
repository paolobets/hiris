# Il linter e le best practice

**Data:** 27 agosto 2026
**Stato:** spec approvata, piano da scrivere
**Ramo:** `2.0`
**Precede:** la rinomina in inglese degli identificatori, che senza questo non si puo' fare.

---

## 1. Il mandato

> **Le best practice sono un cancello, non un'aspirazione.** «Seguire le buone pratiche» senza uno
> strumento che le verifichi non e' una regola, e' un auspicio. Valgono solo quelle controllate
> automaticamente, e cio' che non e' controllato non si pretende.

Deciso il 26 agosto 2026 come **lo sprint successivo a «l'osservatore»**, da avviare a fetta chiusa
e non durante. La fetta e' chiusa: 3.14.0 «il bilancio dell'energia» e' in produzione.

Il rovescio della stessa regola, deciso il 27 agosto: **una regola esclusa non e' silenzio, e' una
decisione scritta.** Ogni esclusione in `pyproject.toml` porta accanto il suo perche' e il numero
che l'ha motivata.

---

## 2. Il punto zero, misurato il 27/08/2026

Nessun numero in questo documento e' stimato. Sono stati contati con `ruff 0.16.4` e `oxlint` su un
ambiente usa-e-getta, sul codice del commit `28b0874`.

| Misura | Valore |
|---|---|
| Python | **89.453 righe**, 264 file — `hiris/app` 33.812 · `tests` 53.744 · `scripts` 1.887 |
| Frontend JS (escluso `node_modules`) | **6.940 righe**, 22 file |
| Configurazione di lint esistente | **nessuna**: ne' `pyproject.toml`, ne' pre-commit, ne' lint nel CI |
| Violazioni, set di default di `ruff` | **836** — `hiris` 286 · `scripts` 34 · `tests` 516 |
| Violazioni JS, set di correttezza di `oxlint` | **27**, di cui **14 in produzione** |
| Lunghezza delle righe gia' scritte | p90=78 · p95=80 · **p99=91** · max 272 |
| `E501` a soglia 88 / 100 / 110 / 120 | 1298 / **128** / 33 / 14 |
| `ruff format` se adottato | 243 file su 265, **33.606 righe di diff** |
| Tempo di `ruff` su tutto il repo | **0,594 s** |
| Suite | 2.836 test; verde su Python 3.14.3 in 3m38s (2835 passati, 1 saltato) |

### I reperti che valgono piu' del conteggio

- **`F811` e' 56, ma 55 sono falsi positivi**: parametri-fixture di pytest che ombreggiano il nome
  della fixture. **Uno solo e' vero** — `test_resolve_model_auto_agent_returns_haiku` e' definito
  **due volte identico** in `tests/test_claude_runner.py` (righe 198 e 323): il primo non viene mai
  eseguito. Un doppione ai sensi delle fondamenta, trovato in trenta secondi.
- **`B017` x 5** — `pytest.raises(Exception)`: un test che passa qualunque cosa esploda, compreso un
  `AttributeError` da refuso. E' letteralmente la classe di difetto n.1 di questo progetto, trovata
  da uno strumento invece che da una review.
- **`DTZ006` x 2** — `datetime.fromtimestamp()` senza fuso (`officina.py:733`, `queue.py:298`):
  parente diretto del difetto del fuso gia' annotato sulla pagina dell'osservatore.
- **Codice morto nel frontend** — `hiris/app/static/config/api.js` dichiara quattro funzioni che
  nessuno chiama: `esc`, `escHtml`, `applyTheme`, `loadUsage`.
- **Il CI non gira sul ramo dove si lavora**: `tests.yml` si attiva su `push`/`pull_request` verso
  **`master`**, ma la 2.0 vive sul ramo `2.0`. Un linter messo li' dentro nascerebbe addormentato.
- **L'add-on gira su Python 3.13** (`build.yaml`: `base-python:3.13-alpine3.21`), **il CI prova 3.11
  e 3.12**: la versione che sta in casa non e' provata da niente. E' la stessa affermazione-non-
  verificata contro cui `requirements.txt` mette in guardia nel proprio commento.
- **I rilievi si concentrano dove il codice e' piu' grosso**: `hiris/app/server.py` e' 3.818 righe e
  da solo porta 26 dei 103 `BLE001` e 14 dei 15 `ASYNC`. Annotato, **fuori da questa fetta**.

---

## 3. Le decisioni

### 3.1 Il formatter non entra adesso

`ruff format` riformatterebbe **243 file su 265** con **33.606 righe di diff**. Ordine deciso:

> **linter ora → rinomina in inglese → formatter alla fine.**

Cosi' i due diff di massa non si incrociano mai, e resta vera la condizione gia' posta sulla
rinomina: *un commit di sola rinomina; se il diff contiene una riga di logica, non e' una rinomina*.

Conseguenza operativa: **`line-length` si sceglie adesso col valore che il formatter erediterà**,
altrimenti fra sei mesi `E501` e `ruff format` litigano.

### 3.2 Il cancello nasce verde

Nessuna baseline congelata, nessuna lista di peccati ereditati, nessun `noqa` di comodo. Il set di
regole e' scelto perche' cio' che resta **si sani dentro questa fetta**. Una regola che non si
riesce a sanare non entra ancora.

### 3.3 Il perimetro e' Python **e** JavaScript

Un cancello solo, su tutto cio' che il prodotto spedisce. Il frontend costa 27 rilievi ed e' l'unica
parte del prodotto che oggi nessuno strumento guarda.

### 3.4 Il cancello blocca in due punti

- **Locale**: `.githooks/pre-push`, **su ogni push** (0,6 s Python + ~0,1 s JS). L'obiezione che ha
  fatto dormire il cancello attuale — *un cancello che blocca sempre e' un cancello che verra'
  disattivato* — non si applica a mezzo secondo.
- **Remoto**: job `lint` in `tests.yml`, **con `branches: [master, "2.0"]`** su `push` e
  `pull_request`, cosi' suite e linter smettono di dormire sul ramo dove si lavora.

`scripts/verifica_componenti.py` **non** viene toccato: il pre-push su ogni push copre gia' il push
di rilascio, e metterlo anche li' sarebbe la stessa regola in due posti.

### 3.5 Python 3.13 entra nella matrice del CI

`"3.13"` si aggiunge alla matrice pytest: la versione che sta davvero in casa smette di essere non
provata. Rischio misurato e assente: la suite e' **verde su 3.14.3**, quindi su 3.13 lo e'.

---

## 4. L'architettura del cancello

**Un file di configurazione, due strumenti, due strati.**

- **`pyproject.toml` alla radice** — l'unica casa della configurazione. Contiene `[tool.ruff]` e
  nient'altro: non diventa un file di packaging, HIRIS non e' un pacchetto.
- **`ruff` appuntato** in `hiris/requirements.txt` (`ruff>=0.16.4,<0.17.0`), con lo stesso
  ragionamento dei «pavimenti» gia' scritto in quel file: un linter che cambia da solo trasforma un
  CI verde in rosso senza che nessuno abbia toccato una riga.
- **`oxlint` appuntato** in `package.json` come `devDependency` (`~1.80.0`), invocato da
  `npm run lint`. Nessun `eslint` con la sua catena di plugin: qui ci sono 22 file JS, non un
  ecosistema.
- **`oxlint` va invocato con `--deny-warnings`.** Misurato il 27/08: senza quel flag **esce con
  codice 0 pur avendo segnalato 27 rilievi**. Segnalerebbe e lascerebbe passare — la meta' JS del
  cancello sarebbe decorativa, e nessuno se ne accorgerebbe perche' l'output sembra giusto. `ruff`
  esce 1 correttamente e non ha bisogno di niente.
- **`target-version = "py311"`** — il piu' basso che il CI dichiara di supportare.

---

## 5. Il set di regole, e le quattro esclusioni scritte

Base: **il set di default di `ruff` 0.16** (pyflakes, bugbear, security, async, datetime, pyupgrade,
simplify, perflint, ruff, isort). Sopra, quattro decisioni **misurate il 27/08/2026**:

| Decisione | Misura | Il perche', che va scritto in `pyproject.toml` |
|---|---|---|
| **`BLE001` esce** | 103 casi, 99 in produzione | In questo prodotto `except Exception` e' una **difesa deliberata**, e la maggioranza dei blocchi ha gia' il perche' scritto nel commento accanto (*«una difesa che solleva non e' una difesa»*). Il difetto che `BLE001` vuole prendere e' la difesa **muta**, e quella la prende **`S110`**, che resta accesa coi suoi 7 casi. Non si perde copertura: si sposta su una regola che dice la cosa giusta. |
| **`F811` esce nei soli test** | 56 casi, **55 falsi positivi** | Sono i parametri-fixture di pytest. Il caso vero si sana **prima** di spegnerla. |
| **`S101`, `S102`, `S105`, `S106`, `S108` escono nei soli test** | 5.884 `assert`, 21 `exec` | `assert` e' il modo in cui un test asserisce; i segreti e i percorsi temporanei nei test sono finti per costruzione. **`S107` resta accesa ovunque**: nella misura non e' servito spegnerla. |
| **`E501` entra, `line-length = 100`** | costo **128 righe** | Il codice e' gia' scritto a ~90 colonne (p95=80, p99=91). 100 e' il numero tondo appena sopra la realta' misurata; 88 (il default) ne costerebbe 1.298 e sarebbe uno stile importato invece che il proprio. |

### Il residuo, misurato applicando davvero i fix in una copia

Non stimato: i fix sono stati applicati su una copia usa-e-getta del codice e il resto contato.

Il perimetro esatto e' `hiris scripts tests conftest.py .smoke-test` — cinque bersagli **nominati**,
mai `.`: le cartelle non tracciate (`Testbook`, `Nuova grafica`, `.mockups`) esistono in locale e non
sul CI, e un cancello che guarda cose diverse nei due posti non e' un cancello. `.smoke-test` sono
due file tracciati (377 righe, 6 rilievi) e quindi entra.

Con la configurazione definitiva il conto e' **798** (comprende i 137 `E501` che nascono con
`line-length = 100`). Poi:

- **798 → 564** applicando i **fix sicuri**
- **564 → 241** applicando i **fix «unsafe»** (323 correzioni, quasi tutte i **178 `RUF059`** dei
  test: prefisso `_` su variabili spacchettate e mai usate, **zero in produzione**), con 2.836 test
  a fare da prova
- **241 = 157 righe lunghe + 84 rilievi a mano**

**`E501` sale da 137 a 157 durante il sanamento**, e non e' un errore di conto: accorpare import e
convertire in f-string **allunga le righe**. E' la prova misurata che la tipografia va **per ultima**.

Gli 84, per famiglia: `SIM117` 21 · `UP031` 20 · `RUF012` 7 · `S110` 7 · `TRY401` 7 · `B017` 5 ·
`PLW1510` 5 · `SIM115` 5 · `ASYNC230` 3 · `DTZ006` 2 · `PLR0124` 1 · `SIM102` 1.

**Due precisazioni fatte guardando il codice, non il conteggio:**

- **`ASYNC230` x 2 non sono difetti.** Uno e' in un test; l'altro (`server.py:1690`) legge i due file
  statici **una volta all'avvio**, prima che l'app serva alcunche'. Si sanano come igiene.
- **`PLR0124` e' un falso positivo che vale comunque la correzione.** `hiris/app/casa/tempo.py:72`
  usa `numero != numero` come idioma per il NaN — deliberato e commentato. `math.isnan()` dice la
  stessa cosa senza farsi scambiare per un difetto.

---

## 6. L'ordine del sanamento

**Il cancello si chiude per ultimo.** Un cancello che nasce rosso e' un cancello che verra' aggirato
il primo giorno. La suite dev'essere verde a ogni passo.

| # | Commit | Cosa | Perche' a se' |
|---|---|---|---|
| **0** | `test` + `fix(tests)` | **Il doppione vero**, per primo: via la ridefinizione a `tests/test_claude_runner.py:323`. | **Prima della configurazione, non dopo.** `per-file-ignores` su `tests/**` spegnera' `F811`, e quel caso vero verrebbe silenziato insieme ai 55 falsi positivi che lo giustificano. Chi lo sana dopo non lo trova piu'. |
| 1 | `chore(lint)` | `pyproject.toml`, `ruff` appuntato, `oxlint` + `npm run lint`. **Nessuno sbarramento ancora.** | La configurazione e' il documento: nasce leggibile e da sola. |
| 2 | `chore(lint)` | **I fix sicuri** (798 → 564), sola macchina. Suite verde. | Rischio nullo, diff grande: dev'essere leggibile senza nient'altro dentro. |
| 3 | `chore(lint)` | **I 323 fix «unsafe»** (564 → 241), quasi tutti `RUF059` nei test. Suite verde. | Classe di rischio diversa dal #2: un `git revert` deve poter tornare indietro **solo** su questi. |
| 4..n | uno **per famiglia** | Gli **84 a mano**: `SIM117`, `UP031`, `RUF012`, `S110`, `TRY401`, `PLW1510`, `SIM115`, `SIM102`, `PLR0124`, `ASYNC230`. | Una famiglia = una decisione = un commit leggibile nel log fra sei mesi. Non per file. |
| — | `test` + `fix` **rosso → verde** | **I difetti veri**: `B017` x 5, `DTZ006` x 2. Il test che li dimostra viene **prima** della correzione. | Sono cambi di comportamento, non igiene. La finta deve saper **produrre** il difetto. |
| — | `chore(lint)` | **Le 157 righe** oltre 100 colonne. Sola tipografia, **per ultima**. | Se il diff contiene una riga di logica, non e' questo commit. E vanno per ultime perche' i fix automatici ne creano venti di nuove. |
| — | `chore(lint)` + `fix(frontend)` | **I 27 rilievi JS**, dentro cui il **codice morto** di `config/api.js`. | Ogni fetta e' anche pulizia: cancellare cio' che il linter ha trovato morto e' parte della fetta, non un extra. |
| **ultimo** | `chore(ci)` | **Il cancello si chiude**: job `lint`, `branches: [master, "2.0"]`, `"3.13"` in matrice, `pre-push` su ogni push, commento dell'hook riscritto. | Si chiude solo su verde, mai prima. |

Il commento in testa a `.githooks/pre-push` oggi dichiara «sui push ordinari dorme»: con questa
fetta smette di essere vero e va riscritto. Un commento che mente e' un difetto.

---

## 7. Come si prova che il cancello blocca davvero

E' il punto in cui questa fetta puo' fallire in silenzio, ed e' la trappola che il progetto ha gia'
pagato: **uno strumento che gira, dichiara «ok», e non avrebbe potuto dire altro.** Un linter
configurato male passa sempre — indistinguibile da un linter che funziona su codice pulito.

Il cancello si prova **per mutazione**, e la prova va registrata qui sotto col suo output:

1. Si introduce di proposito una violazione di ciascuna classe: un import non usato in `hiris/app/`,
   una riga a 130 colonne, una variabile mai usata in un `.js`.
2. **Il pre-push deve rifiutare il push**, con un messaggio leggibile e non un traceback.
3. **Il job CI deve diventare rosso** — provato una volta su un ramo usa-e-getta, poi buttato.
4. Si toglie la mutazione e **tutti e tre devono tornare verdi**: un cancello che blocca anche il
   codice pulito verra' disattivato entro la settimana, e allora non protegge piu' niente.

**Due limiti, dichiarati invece che nascosti:**

- `git push --no-verify` salta l'hook, e `core.hooksPath` va impostato una volta per clone. Lo strato
  locale e' una comodita' veloce; **il cancello vero e' il CI**, che nessuno puo' saltare.
- **Non** si aggiunge un test pytest che invoca `ruff`: sarebbe un **terzo** innesco per una regola
  che ha gia' una casa sola (`pyproject.toml`) e due inneschi. Un doppione ai sensi delle fondamenta.

---

## 8. Cosa resta fuori, dichiarato

- **`ruff format`** — dopo la rinomina in inglese (§3.1).
- **La rinomina in inglese** degli identificatori — e' cio' per cui questa fetta esiste.
- **Lo spacchettamento di `server.py`** (3.818 righe, dove i rilievi si concentrano).
- **`mypy` e le annotazioni di tipo** — non misurato, non deciso, non promesso.

### Reperti adiacenti, misurati e non toccati qui

- `tests/test_schedulatore_orologio.py:357` — un test marcato `@pytest.mark.asyncio` che **non e'
  async**. Non fallisce; il marcatore e' rumore, e vale la pena capire se il test fa cio' che crede.
- **27 `DeprecationWarning` di aiohttp** in `tests/test_security.py`: *«Bare functions are
  deprecated, use async ones»*. Oggi warning, un domani errori.
- La famiglia `PT` (`flake8-pytest-style`) non e' nel set di default e non e' stata misurata: e' il
  candidato naturale per il gradino successivo del set, quando questo sara' a zero.
