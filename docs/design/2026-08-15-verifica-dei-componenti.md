# La verifica dei componenti al rilascio

**Data:** 2026-08-15 · **Ramo:** `2.0` · **Versione di partenza:** 3.2.0 (`cd4d083`)
**Nasce da:** una domanda del proprietario — *«possiamo fare in modo che quando pubblichiamo ci
sia una verifica dei componenti e in caso un aggiornamento?»*

---

## 0. Il fatto che fa esistere questa fetta

**Una disciplina scritta non è una disciplina eseguita.**

`hiris/Dockerfile:20-31` porta, per esteso, il prezzo del pin della CLI e la procedura per pagarlo:

> *«Le patch della CLI non arrivano più da sole. Si resta su questa riga finché qualcuno non la
> cambia a mano, comprese le correzioni di sicurezza. […] è la ragione per cui la riga va guardata
> a ogni giro di rilascio.»*

Sono uscite la **3.0.0**, la **3.1.0** e la **3.2.0**. La riga non è stata guardata nessuna delle
tre volte. Misurato il 15 agosto 2026: pin `2.1.228`, ultima pubblicata **`2.1.233`**.

Lo stesso vale per il resto:

- **8 PR dependabot aperte**, la più vecchia dal 18 maggio, saltate da tre release.
- **`actions/setup-node@v4`** gira su Node 20, deprecato: l'annotazione compare **già** nei run di
  CI, compreso quello della 3.2.0.
- L'ambiente di sviluppo locale girava **sotto i pavimenti dichiarati** (`anthropic` 0.40 contro
  `>=0.87`, `openai` 2.33 contro `>=2.36`): la suite locale provava una cosa diversa da CI e
  dall'immagine, e nessuno se n'era accorto.

**Il difetto non è che manchi un controllo: è che il controllo esiste come NOTA.** Una nota si
legge solo se qualcuno va a cercarla, e al momento del rilascio nessuno ci va. Serve qualcosa che
**si faccia trovare**, e che al momento giusto **non si lasci saltare**.

---

## 1. Il principio

**La verifica dice, l'aggiornamento lo chiedi, la suite decide.**

Tre atti distinti, e nessuno dei tre ne fa un altro per conto suo. In particolare: il rilascio non
aggiorna niente. Sul ponte, cambiare la CLI sotto un rilascio è **precisamente ciò che il pin
esiste per impedire**.

---

## 2. Che cosa guarda

Tre registri, letti con `urllib` della libreria standard: **nessuna dipendenza nuova, nessuna
autenticazione**. Verificato eseguendo il 15/08/2026, non dedotto:

| Componente | Dove è scritto | Registro | Risposta di prova |
|---|---|---|---|
| CLI del ponte | `hiris/Dockerfile`, `claude-code@X.Y.Z` | `registry.npmjs.org/@anthropic-ai/claude-code/latest` → `.version` | `2.1.233` |
| Dipendenze Python | `hiris/requirements.txt`, i **tetti** `<N.0.0` | `pypi.org/pypi/<nome>/json` → `.info.version` | `anthropic` → `0.122.0` |
| Azioni CI | `.github/workflows/tests.yml`, `uses: <owner>/<repo>@vN` | `api.github.com/repos/<owner>/<repo>/releases/latest` → `.tag_name` | `setup-node` → `v7.0.0` |

Il confronto è **«più vecchio di»**, non «diverso da»: un registro che regredisce (un rilascio
ritirato) non deve produrre uno scarto.

Per le azioni si confronta **solo il major**, perché è la forma con cui il workflow le riferisce
(`@v6`). Confrontare la patch chiederebbe di riscrivere il workflow in una forma che non usa.

### 2.1 Per le dipendenze Python NON si guardano i pavimenti — e la ragione conta

La prima stesura di questa spec confrontava il pavimento (`>=0.87.0`) con l'ultima uscita su PyPI.
**È sbagliato, e in modo istruttivo:** un pavimento sta *per definizione* sotto l'ultima versione.
`pytest>=9.0.3` contro `9.1.1`, `anthropic>=0.87.0` contro `0.122.0` — tutte e undici le righe
sarebbero uno scarto, a ogni rilascio, per sempre. Cioè **un elenco che dice sempre qualcosa**: il
difetto che §3 dichiara inaccettabile, reintrodotto una sezione dopo averlo dichiarato.

I tetti sono aperti (`<1.0.0`, `<3.0.0`) e CI installa da zero: **CI sta già provando le versioni
più recenti.** Il pavimento non decide che cosa gira; è documentazione. Le domande utili sono
quindi due, ed entrambe sono **rare** — cioè producono un elenco che vale la pena leggere:

**(a) Esiste un major sopra il tetto?** `anthropic<1.0.0` mentre PyPI passa a `1.x` significa che
il tetto sta **congelando la dipendenza in silenzio**: CI resta verde, l'immagine si costruisce, e
nessuno vede che una linea intera è stata esclusa. È il solo caso in cui un numero su PyPI cambia
ciò che gira davvero.

**(b) Ciò che è INSTALLATO rispetta i pavimenti dichiarati?** Nessuna rete: si confronta
`requirements.txt` con `importlib.metadata` dell'interprete che esegue il controllo.

La (b) non è teorica. Misurata il 15/08/2026 sull'ambiente di sviluppo: `anthropic` **0.40.0**
contro un pavimento `>=0.87.0`, `openai` **2.33.0** contro `>=2.36.0`, `aiohttp` **3.13.5** contro
`>=3.14.1`. **La suite locale provava qualcosa di diverso da CI e dall'immagine**, e il verde che
ne usciva valeva meno di quanto sembrava. Nessun controllo lo diceva, e la nota nel `Dockerfile`
non parlava di questo.

## 3. Che cosa risponde

**Una lista di scarti, non un booleano.** Ogni voce nomina il componente, ciò che è scritto e ciò
che il registro dice:

```
CLI del ponte indietro          2.1.228 → 2.1.233   hiris/Dockerfile
actions/setup-node indietro     v4      → v7        .github/workflows/tests.yml
anthropic: esiste il major 1, il tetto <1.0.0 lo esclude
                                                    hiris/requirements.txt
anthropic installato 0.40.0, il pavimento dice >=0.87.0
                                                    ambiente di questo interprete
```

**Un componente allineato NON compare.** Un elenco che dice sempre qualcosa è un elenco che si
smette di leggere — è il difetto che questa fetta chiude, non uno da reintrodurre in scala minore.

### 3.1 Il registro che non risponde

**Non è un via libera.** Se npm, PyPI o GitHub non rispondono entro il timeout, il componente esce
come *«non ho potuto controllare X: `<motivo>`»* e **conta come scarto**.

È la stessa regola che il prodotto ha appena adottato nella pagina Modelli: «non c'è» e «non ho
potuto guardare» sono due risposte diverse, e **nessuna delle due è "tutto a posto"**. Un controllo
che passa in silenzio quando la rete cade è un controllo che si può disattivare staccando il cavo.

---

## 4. Dove vive, e come blocca

`.githooks/pre-push`, attivato con `git config core.hooksPath .githooks`, così **vive nel repo** e
non in una cartella locale che sparisce al clone.

**Si sveglia solo sui rilasci**, e li riconosce dal contenuto: il push contiene un commit che
cambia il campo `version` di `hiris/config.yaml`. Non dalle intenzioni, non da un flag, non dal
nome del ramo — dal fatto. Sui push ordinari (correzioni, documenti, test) l'hook dorme.

### 4.1 L'hook NON fa domande

Durante `pre-push` git usa lo **stdin** dell'hook per passargli i ref: non è un canale su cui si
può leggere una risposta. E i push di questo progetto partono anche da una sessione **senza
terminale** — un prompt resterebbe appeso per sempre, e il primo rilascio si sarebbe piantato.

Quindi l'hook **si ferma, stampa il quadro, e dice come si risponde**:

```
Il rilascio si è fermato: 3 componenti da guardare.
[…la lista…]

Se hai deciso di rilasciare così com'è:
    HIRIS_COMPONENTI_OK=1 git push …
Se vuoi aggiornare le azioni CI:
    python scripts/verifica_componenti.py --aggiorna   (poi rilancia la suite)
```

**La risposta è un atto, non un tasto.** Compare nel comando, resta nella cronologia della shell,
non si può dare per sbaglio, e vale **solo per quel push**. Il valore accettato è esattamente `1`:
qualunque altro valore non sblocca, perché una variabile che accetta qualsiasi cosa si finisce per
lasciarla esportata nel profilo.

---

## 5. L'aggiornamento

`python scripts/verifica_componenti.py --aggiorna` applica **la sola cosa che sa applicare da
sola**: porta le azioni in `.github/workflows/tests.yml` all'ultimo major.

Non tocca né `requirements.txt` né il `Dockerfile`, e le due ragioni sono diverse.

**`requirements.txt`**: gli scarti Python di §2.1 non si correggono cambiando un numero. Un major
sopra il tetto è una **decisione** (si alza il tetto e si prova, o si resta), e un pacchetto
installato sotto il pavimento non si ripara scrivendo nel file — si ripara nell'**ambiente**, con
`pip install -r hiris/requirements.txt --upgrade`, che lo script suggerisce e non esegue.

**Il `Dockerfile`** richiede `--aggiorna --cli`, cioè una richiesta a parte. Non è prudenza
generica: un confronto di numeri **non può vedere** la cosa che conta, cioè se la CLI nuova smette
di emettere `mcp_servers` nell'`init` — nel qual caso HIRIS non si rompe, **diventa cieco**. Quel
controllo lo fa `sonda_strumenti` a runtime, sull'impianto, dopo il deploy; il numero non lo sa.

La CLI del ponte richiede `--aggiorna --cli`, cioè una richiesta a parte. Non è prudenza generica:
un confronto di numeri **non può vedere** la cosa che conta, cioè se la CLI nuova smette di
emettere `mcp_servers` nell'`init` — nel qual caso HIRIS non si rompe, **diventa cieco**. Quel
controllo lo fa `sonda_strumenti` a runtime, sull'impianto, dopo il deploy; il numero non lo sa.

Dopo aver scritto, lo script **si ferma e dice che tocca alla suite**. Non la lancia: lanciarla
renderebbe l'aggiornamento un'operazione unica che «è andata bene», invece di due fatti separati
di cui il secondo può fallire.

---

## 6. La forma del codice

Il cuore è **una funzione pura**:

```
componi_scarti(letti: dict, registri: dict) -> list[Scarto]
```

`letti` è ciò che c'è nei file; `registri` è ciò che i registri hanno risposto (o il motivo per cui
non hanno risposto). **Nessuna rete, nessun git, nessun orologio, nessun filesystem.** Le tre
letture di registro e la lettura/scrittura dei file stanno fuori e sono sottili.

È la stessa divisione di `decisione_modelli`, ed è ciò che rende le prove capaci di **produrre** il
difetto invece di descriverlo: uno scarto si fabbrica passando due dizionari.

`.githooks/pre-push` resta di poche righe: decide se il push è un rilascio, chiama lo script,
guarda l'uscita e la variabile. Nessuna logica di confronto in shell.

---

## 7. Le prove

Ogni prova deve poter **produrre** il difetto che dice di impedire, e si convalida per mutazione.

1. **Un componente indietro viene nominato**, con i due numeri. *Mutazione:* confronto `!=` invece
   di «più vecchio» → un registro che regredisce produce uno scarto falso.
2. **Un componente allineato non compare.** *Mutazione:* elencare tutto.
3. **Il registro che non risponde è uno scarto.** *Mutazione:* trattarlo come allineato — la prova
   deve cadere.
4. **L'hook dorme sui push ordinari** e **si sveglia sul bump di versione**. Due prove opposte:
   senza la prima, un hook che blocca sempre passerebbe la seconda.
5. **`HIRIS_COMPONENTI_OK=1` sblocca, e solo quel valore.** *Mutazione:* accettare qualunque
   stringa non vuota.
6. **`--aggiorna` scrive il workflow e NON tocca `requirements.txt` né il `Dockerfile`.**
   *Mutazione:* fargli scrivere anche la CLI, oppure i pavimenti.
7. **Le versioni si confrontano da versioni, non da stringhe:** `2.1.9` è più vecchio di `2.1.10`.
   *Mutazione:* confronto lessicografico — cade su questo caso e su nessun altro.
8. **Un major sopra il tetto è uno scarto; un minor o una patch sopra il pavimento NON lo sono.**
   È la prova che difende §2.1: senza, l'elenco torna a dire sempre qualcosa. *Mutazione:*
   confrontare il pavimento con l'ultima uscita — undici scarti su undici dipendenze.
9. **Un pacchetto installato sotto il pavimento è uno scarto**, e nominato con i due numeri.
   *Mutazione:* leggere il pavimento invece della versione installata — i due coincidono nel caso
   sano e divergono solo nel caso che questa prova esiste per cogliere.

---

## 8. Cosa NON entra, e perché

1. **L'elenco delle PR dependabot aperte**, e più in generale **l'inseguimento dei pavimenti.**
   Cinque delle otto PR aperte oggi alzano un pavimento Python (`openai` ≥2.36→≥2.37 e simili):
   non cambiano ciò che gira, perché i tetti sono aperti e CI installa già l'ultima versione. Sono
   contabilità, e questa verifica non le nominerà — per la ragione di §2.1: un controllo che
   segnala ciò che non cambia niente diventa un controllo che si smette di leggere. Restano una
   faccenda da sbrigare a mano quando fa comodo. In più, l'elenco delle PR chiederebbe all'hook
   un'autenticazione `gh` che non deve pretendere.
2. **L'auto-merge delle PR.**
3. **`node-version: '22'` nel workflow.** È sano: l'avviso di deprecazione riguarda **l'azione**
   `setup-node@v4`, ed è già coperto dal controllo delle azioni.
4. **Un controllo delle CVE.** È un'altra domanda, con un'altra fonte e un altro modo di sbagliare
   («nessuna CVE nota» letto come «sicuro»). Se servirà, sarà una fetta sua.
5. **L'attivazione automatica di `core.hooksPath`.** Un repo che si riconfigura il git al primo
   comando è una sorpresa. Si attiva a mano, una volta per clone, e una prova verifica che il file
   dell'hook esista ed sia eseguibile — così l'assenza si vede.

---

## 9. Il metro della fetta

1. Un push **senza** bump di versione passa senza dire niente.
2. Un push **con** il bump si ferma ed elenca. Misurato al primo giro vero, il 15/08/2026:
   **cinque** voci — la CLI (`2.1.228 → 2.1.233`), le tre azioni (`checkout` e `setup-python`
   `v6 → v7`, `setup-node` `v4 → v7`) e **una** dipendenza Python: `openai`, il cui tetto
   `<3.0.0` esclude il major **3.1.0** che esiste già.

   Quest'ultima è la conferma di §2.1 sul campo: **una sola riga Python su undici**, e non è
   rumore — è un congelamento silenzioso che nessuno aveva visto, con CI verde e immagine che si
   costruisce. Se un giorno compaiono tutte e undici, §2.1 è stata violata e l'elenco è già
   diventato illeggibile.
3. `HIRIS_COMPONENTI_OK=1 git push` passa. `HIRIS_COMPONENTI_OK=si` no.
4. `--aggiorna` cambia il workflow, lascia `requirements.txt` e `Dockerfile` intatti, e la suite
   resta verde.
5. Staccando la rete, il controllo **si ferma lo stesso** e dice che non ha potuto guardare.
6. Con un `anthropic` vecchio installato a mano, il controllo lo nomina — ed è la prova che
   riproduce il difetto misurato oggi.
