# I menu esecutivi — Impegni e Proposte

*Fetta di disegno · 03/09/2026*

> **Stato**: specifica da rileggere. Nessuna riga di codice si tocca prima
> che il proprietario l'abbia approvata.

---

## §1 · Il difetto

Due delle dieci voci del secondo guscio non sono configurazione.

«Promesse» elenca cose che HIRIS **farà**, con un'ora. «Costruzioni» elenca
cose che HIRIS **ha già scritto** e per cui aspetta un sì o un no. Non si
configura niente né sull'una né sull'altra: si guarda cosa sta per succedere,
e si dice sì o no. Sono **menu esecutivi**, e stanno sotto l'etichetta
«Configurazione».

Il difetto ha una faccia misurata, riferita dal proprietario:

> «Sto chiedendo la modifica ad un'automazione, la chat mi risponde che ha
> costruito la nuova versione ed è in attesa di conferma. Questo all'utente
> può creare qualche difficoltà perché la chat chiede di confermare ma tu non
> sai dove.»

La chat apre un'attesa e non dice dove si chiude. Chi legge quella frase
resta fermo, oppure va a cercare in Home Assistant una cosa che in Home
Assistant non c'è ancora. La proposta scade dopo il suo tempo
(`ConstructionStore.scadi`) senza che nessuno l'abbia vista.

E non c'è nessun posto, in nessuno dei due gusci, che dica **che c'è
qualcosa da guardare**. Bisogna aprire la pagina per scoprire se valeva la
pena aprirla.

---

## §2 · I nomi

### 2.1 «Promesse» → **Impegni**

Il nome è passato per due prove del lettore nuovo (un agente a cui è vietato
leggere il codice: giudica la parola, non l'implementazione).

La prima ha bocciato **«Schedulazioni»**, che era il nome proposto in
partenza, su quattro punti: nomina l'orologio e non la commissione; non ha
soggetto («le cose *sono schedulate*, da nessuno»); non regge lo storico
(«schedulazioni concluse» è un errore di categoria); promette ricorrenza,
mentre metà dei casi sono una-tantum («fra due ore»). E in Home Assistant
*schedule* è già preso.

La seconda ha messo a confronto **Programmi · Programmazione · Impegni ·
Incarichi**, con quattro criteri: (a) c'è un soggetto che si impegna, (b)
regge lo storico, (c) non promette ricorrenza a sproposito, (d) non si
confonde col vocabolario delle automazioni.

| | (a) soggetto | (b) storico | (c) ricorrenza | (d) automazioni |
|---|---|---|---|---|
| **Programmi** | no | no | sì, a sproposito | **sì, collide** |
| **Impegni** | sì | sì | no | no |
| **Incarichi** | sì, ma girato | sì | no | quasi no |

«Programmi» fallisce tutti e quattro, e in un modo peggiore di
«Schedulazioni»: non è *vuota*, è **occupata**. In domotica un'automazione
*è* un programma. Il lettore costruisce un modello a due caselle — «Proposte»
= le modifiche in attesa del mio sì, «Programmi» = dove finiscono una volta
approvate — che è coerente, plausibile e falso. *Un nome che genera
un'ipotesi sbagliata e verosimile è più dannoso di un nome opaco: l'utente
non si accorge di aver sbagliato pagina, si accorge che il prodotto non fa
quello che credeva.*

«Programmazione» non è stata sottoposta alla prova (è arrivata a giudizio
concluso). Gli argomenti contro «Programmi» valgono su di lei più forti:
stessa collisione, più il fatto che in italiano «programmazione» è anche
*scrivere codice*, più un singolare astratto che una lista mezza storica non
regge.

Fra Impegni e Incarichi li separa **una cosa sola, e decide**: la sostanza di
questa pagina è il momento — «fra due ore», «quanto manca». *Impegno* porta
con sé il soggetto **e** l'ora («ho un impegno alle 23» si capisce da sé).
*Incarico* porta solo il soggetto: l'ora andrebbe riattaccata, e riattaccare
l'orologio è esattamente l'errore per cui è caduta «Schedulazioni».

**La prova che conta**: HIRIS in chat dice «te lo prometto». Quale voce
clicchi per ritrovarla? In italiano *prendere un impegno* e *fare una
promessa* sono la stessa mossa detta in due registri: la giuntura è
invisibile, non c'è niente da tradurre.

Scartata anche **«Promesse»** (il nome di oggi): una pagina intitolata alle
promesse non mantenute lavora contro il prodotto, e al plurale la parola ha
l'alone delle promesse da marinaio.

**Rischio residuo, dichiarato e accettato**: al primo colpo qualcuno può
leggere «Impegni» come «la mia agenda». È un errore che atterra nella stanza
accanto — apre la pagina, vede impegni presi da HIRIS con un conto alla
rovescia, e il modello si corregge da solo in un secondo.

### 2.2 «Costruzioni» → **Proposte**

Il nome dice cosa ti si sta chiedendo, non cosa la macchina ha fabbricato. È
anche la parola che la chat userà per mandarti lì (§6), e la parola che i
bottoni della pagina già usano («Approva» / «Rifiuta»).

La riga che separa le due voci si dice in una frase, ed è la prova che non si
sovrappongono:

> **Le Proposte aspettano te. Gli Impegni aspettano l'ora.**

### 2.3 Cosa NON si rinomina

- **Gli indirizzi**: `#/agenda` e `#/constructions` restano. Sono
  identificatori, e la fetta «la rinomina» (02/09) li ha già portati
  all'inglese; finiscono nei segnalibri, e la tabella `HASH_DI_PRIMA` in
  `config/router.js` esiste apposta per non rompere quelli vecchi. Cambiarli
  di nuovo, sette giorni dopo, aggiungerebbe due righe a quella tabella e due
  bersagli a `tests/js/router-alias.test.mjs` in cambio di niente: **l'utente
  non legge l'hash, legge l'etichetta.**
- **Il codice**: `constructions`, `ConstructionStore`, `/api/constructions`,
  la tabella `costruzioni`. Il codice nomina *la cosa che l'archivio tiene*
  (una revisione da costruire); l'interfaccia nomina *cosa si chiede a te* (di
  approvarla). Sono due fatti diversi, non una traduzione — la legge del
  glossario dice «si rinomina per funzione», e qui le due funzioni divergono
  davvero. La parola del database resta comunque **dentro la fetta rimandata**
  «il vocabolario del dato», insieme ai valori di dominio.
- **La chat**: continua a dire «promessa». Vedi §6.

---

## §3 · Dove vanno le pagine

### 3.1 Lo stato di oggi

Ci sono due gusci, non uno:

| URL | file | cos'è |
|---|---|---|
| `/` | `static/index.html` | la chat. Nessun router, la conversazione occupa tutto |
| `/config` | `static/config.html` | SPA con hash router, dieci voci di `side-nav` |

Nel secondo, **una sola etichetta di sezione** — «Configurazione» — sta sopra
**nove** voci, di cui configurazione vera ne sono due: Impostazioni chat e
Modelli. «Cosa HIRIS sa», «Albero della casa», «Memoria», «L'osservatore»,
«Consumi», «Promesse», «Costruzioni» non configurano niente — si guardano. Il
difetto del §1 è un caso particolare di questo.

### 3.2 La decisione

**Le pagine restano dove sono scritte; cambia dove si arriva e come sono
raggruppate.** In concreto, tre mosse:

1. **Nella barra laterale della chat** (`index.html`) nascono due voci —
   Impegni e Proposte — sopra «Configurazione», col pallino di §4. Da dove
   l'utente sta davvero, la pagina è a un click.
2. **Nella `side-nav` del secondo guscio** le due voci escono da sotto
   «Configurazione» e salgono in un gruppo proprio, subito sotto «Chat». Le
   nove voci si ridividono in tre gruppi:

   | gruppo | voci |
   |---|---|
   | **Da fare** | Impegni · Proposte |
   | **La casa** | Cosa HIRIS sa · Albero della casa · Memoria · L'osservatore |
   | **Configurazione** | Impostazioni chat · Modelli · Consumi |

   «Da fare» in cima perché è l'unico gruppo che chiede qualcosa. «Memoria»
   sta con la casa e non con la configurazione: è ciò che HIRIS ricorda, non
   un parametro. **«Consumi» è l'unico compromesso dichiarato**: è un
   rendiconto, non una configurazione, e sta lì perché è accanto a «Modelli»
   che si agisce su ciò che dice. Un quarto gruppo per una voce sola
   costerebbe più di quanto renda.
3. Niente altro si muove.

### 3.3 Perché non si portano dentro la chat

L'alternativa era far vivere le due pagine dentro `index.html`. Costa: la chat
non ha router, non ha `route-outlet`, e la conversazione occupa tutta l'area
principale — per ospitare due route bisognerebbe rendere la chat stessa una
route. È una riscrittura del guscio più usato del prodotto, per spostare due
pagine che funzionano e che tre file di test già bloccano
(`agenda-route.test.mjs`, `agenda-route-vocabulary.test.mjs`,
`constructions-route.test.mjs`).

**Il costo che questa scelta lascia sul tavolo, dichiarato**: la barra degli
indirizzi continuerà a dire `/config#/agenda` per una pagina che non è
configurazione. Non si paga oggi: un secondo URL per la stessa pagina
spaccherebbe i segnalibri in due, e l'utente l'indirizzo non lo legge — ci
arriva dal menu. **Condizione d'uscita**: il giorno in cui il secondo guscio
smette di essere «la configurazione» anche di nome, `/config` diventa un alias
di un percorso onesto, e quel giorno si toglie in un pezzo solo.

---

## §4 · Il pallino

### 4.1 Cosa conta

- **Impegni** — le promesse in `STATES_SOSPESO` (`keeper/promise.py`:
  `in_attesa`, `in_corso`).
- **Proposte** — le costruzioni in `STATES_SOSPESO`
  (`action/construction/revisions.py`: gli stessi due).

Il numero è nudo; le parole stanno nel `title` e nell'`aria-label`: **«N in
attesa»**. Sotto i 1024 px la `side-nav` si stringe a 64 px e le etichette
spariscono: un numero senza nome, lì, non si capirebbe né col mouse né con
uno screen reader.

### 4.2 La regola che il pallino precedente ha infranto

In `hiris-config.css:871` c'è la lapide del badge di prima:

> *«qui vivevano le quattro regole di `.nav-badge`… la voce di nav è uscita
> col badge»*

Quel pallino contava le segnalazioni del Brain leggendo una rotta uscita con
la fetta E3, e **mostrava `0` quando la rotta rispondeva 404**. Non era
inutile: era peggio — diceva «non c'è niente da guardare» quando la verità era
«non lo so».

**Regola, e si prova**: se la richiesta fallisce — rete, 4xx, 5xx, archivio non
disponibile (503) — **il pallino non compare**. Mai `0` per ignoranza. Uno
zero vero (l'archivio risponde, non c'è niente in sospeso) nasconde il pallino
allo stesso modo: zero non è una notizia.

### 4.3 Da dove arriva il numero

Le rotte di oggi esistono ma sono grasse per un pallino: `GET /api/agenda`
serve fino a 200 promesse serializzate, `GET /api/constructions` fa altrettanto
e prima scrive (`store.scadi`). Chiamarle per leggere due interi, a ogni
apertura, su un Raspberry, no.

**Nasce `GET /api/pending`**, che risponde:

```json
{"agenda": 3, "constructions": 1}
```

Due `SELECT COUNT(*) … WHERE stato IN (…)`. Le chiavi ripetono i nomi delle
rotte che le due pagine già usano: chi legge il JSON sa subito dove andare. Su
archivio non disponibile risponde **503** — e §4.2 fa il resto.

Due metodi nuovi, `count_pending()`, uno per archivio. Sono codice nuovo,
quindi in inglese come vuole la legge; convivranno con `solo_in_sospeso=` di
`keeper/store.py::list`, che è italiano ed è **debito già dichiarato** della
fetta rimandata sul dato. Non si sana qui: sanarlo qui significherebbe toccare
l'SQL di un archivio vivo dentro una fetta di interfaccia.

### 4.4 Quando si aggiorna

Non c'è nessun timer. Il numero cambia in momenti che si vedono tutti:

1. all'apertura di ogni guscio;
2. **dopo ogni risposta della chat** — è lì che nasce una promessa o una
   proposta, ed è l'istante esatto in cui il pallino deve accendersi mentre
   l'utente sta ancora leggendo la frase che lo manda a guardarlo;
3. dopo ogni azione sulle due pagine (Disdici, Approva, Rifiuta);
4. al ritorno del fuoco sulla finestra (`focus`) — copre il solo caso che i tre
   sopra non vedono: lo schedulatore ha mantenuto una promessa mentre la scheda
   era in secondo piano.

Un poll ogni N secondi costerebbe una richiesta al minuto, per sempre, per un
numero che cambia qualche volta al giorno.

### 4.5 Dove vive il codice

Un file nuovo, `static/pending-badge.js`, caricato **da tutti e due i gusci**
— che già condividono `hiris-theme.css` e `build-check.js`, quindi il modo è
stabilito. Le regole `.nav-badge` tornano in **`hiris-theme.css`**, non nei
due fogli di guscio: entrambi lo caricano, e un fatto ha una sola casa.

---

## §5 · Lo storico compresso

Le due pagine hanno **già** due sezioni ciascuna — «In sospeso» / «Storico»
per gli Impegni, «In attesa» / «Storico» per le Proposte. Non serve costruire
niente: serve chiuderle.

> «Mi basta archiviarle in una sezione che è compressa e non visibile.»

- La sezione «Storico» nasce **chiusa**, con il conteggio nell'intestazione:
  «Storico (14)».
- Si apre con un click sull'intestazione, che è un `<button>` con
  `aria-expanded` — stessa disciplina di `detailsDisclosure()` in
  `constructions-route.js:317`, che già fa esattamente questo per i dettagli
  tecnici. Nessun sistema nuovo.
- Lo stato aperto/chiuso **non si ricorda** fra una visita e l'altra: la
  domanda con cui si apre questa pagina è «cosa c'è in sospeso», e deve avere
  la stessa risposta tutte le volte.

**Non si aggiunge nessuna cancellazione.** Era la richiesta di partenza, ed è
stata ritirata in favore dell'archiviazione. È anche la scelta giusta per una
ragione che `agenda-route.js` già dichiara nel proprio commento: disdire non
distrugge niente, la riga resta leggibile per sempre — a differenza della
cancellazione di un ricordo, che è per sempre. Le righe vecchie se ne vanno da
sole: 90 giorni (`promise.py::CONSERVAZIONE_S`).

---

## §6 · La chat dice dove

Questo chiude il difetto del §1.

### 6.1 Le proposte

`PROPOSE_TOOL_DEF` (`home_space/tools.py:695`) oggi istruisce il modello a
mostrare l'anteprima e aspettare, e **non nomina il posto**. Alla sua
descrizione si aggiunge, in coda alla frase che parla dell'attesa: che la
proposta resta in attesa nella pagina **«Proposte»**, e che va detto
all'utente insieme all'anteprima.

### 6.2 Gli impegni

`PROMISE_TOOL_DEF` (`tools.py:593`) ha il difetto in forma più lieve — non
chiede niente, la promessa parte da sola — ma la stessa cura costa una frase:
quando prende un impegno, dice che si ritrova nella pagina **«Impegni»**.

La chat **continua a dire «promessa»**, che è la parola giusta in una
conversazione. È «Impegni» che è stata scelta perché la giuntura regge senza
traduzione (§2.1).

### 6.3 Il cancello che tiene insieme le due parole

Una descrizione di strumento che nomina una pagina è una **sponda**: due file
che devono dire la stessa parola senza che nessuno dei due importi l'altro —
l'undicesima specie trovata durante «la rinomina», la coerenza fra file di un
nome che non attraversa.

Un test lega la parola nella descrizione dello strumento all'etichetta nel menu
(`config.html` e `index.html`). Chi rinomina la pagina domani e non tocca il
prompt trova rosso. Senza questo test la cura del §6 è vera **il giorno in cui
si scrive**, e falsa dal primo rename in poi.

Vive in **`pytest`**, non in `npm test`: un lato della sponda è Python
(`tools.py`), e una prova sta dove sta il lato che non si può leggere
dall'altra parte. Legge i due HTML come testo — non serve un DOM per
verificare che una parola ci sia.

### 6.4 Cosa è rimandato allo sprint successivo

La scheda della proposta **dentro la chat** — l'anteprima con Approva e Rifiuta
lì dove la frase la annuncia, senza cambiare pagina. Il proprietario l'ha
voluta segnalata, non fatta ora: costa **rimettere `tools_called` nella
risposta della chat**, tolto il 17/08. È una fetta sua.

---

## §7 · Cosa questa fetta non tocca

| Cosa | Perché |
|---|---|
| L'osservatore | Il proprietario l'ha rimandato esplicitamente a una fase a parte |
| Il database, i valori di dominio, le chiavi fra motore e pagina | Rimandati insieme, in una fetta sola: «il vocabolario del dato» |
| `#/agenda`, `#/constructions`, `constructions` nel codice | §2.3 |
| Qualunque cancellazione | §5 |
| Il badge «esiti non letti» sugli Impegni | Vedi sotto |

**Sul badge degli esiti non letti**: la prima prova del lettore ha osservato
che su quella pagina ciò che *ti* aspetta non sono gli impegni in sospeso —
quelli aspettano l'ora, non te — ma **gli esiti che non hai ancora letto**. È
un'osservazione giusta e non si può implementare oggi: «non letto» vuol dire un
segno di lettura, cioè una colonna nuova nell'archivio delle promesse, che è
dentro la fetta rimandata sul dato. Il pallino conta gli in-sospeso, che è un
fatto vero, misurabile oggi, e già utile. **Quando la fetta sul dato passa,
questa scelta si riapre.**

---

## §8 · Le prove

Ogni prova qui sotto deve poter **fallire**: la finta deve saper produrre il
difetto che la prova cerca.

1. **Il pallino non mente** — con la rotta che risponde 503, e con la rotta che
   va in errore di rete, il pallino **non è nel DOM**. La prova per mutazione:
   un'implementazione che scrive `0` in caso d'errore la fa diventare rossa. È
   la prova che il badge morto non aveva.
2. **Il pallino conta i sospesi** — con una lista finta di tre `in_attesa` + un
   `in_corso` + due concluse, il numero è 4, non 6 e non 3 (`in_corso` conta:
   sta nella sezione azionabile della pagina).
3. **Zero non compare** — archivio che risponde `{"agenda": 0}`: nessun
   pallino.
4. **Le parole della sponda** (§6.3) — l'etichetta del menu nei due gusci e la
   parola nelle descrizioni di `promise` e `propose` coincidono. Mutazione:
   cambiare l'etichetta in un solo posto → rosso.
5. **Lo storico nasce chiuso** — al primo render `aria-expanded="false"` e il
   corpo è `hidden`; il conteggio nell'intestazione è quello delle righe
   concluse.
6. **`GET /api/pending`** — conta giusto su un archivio vero (SQLite in
   memoria), e risponde 503 senza archivio.
7. **Il raggruppamento della nav** — le voci Impegni e Proposte non stanno
   sotto l'etichetta «Configurazione».

E una prova che **non** si scrive: che l'utente capisca. Quella la fa il
proprietario, dal vivo, sulla casa vera — come ogni rilascio.

---

## §9 · I cancelli

Nessuna riga entra senza tutti e cinque verdi:

```
ruff check .
pytest -q                       # in PRIMO PIANO, mai in background
npm test
npx oxlint --deny-warnings hiris/app/static
python scripts/sponde_js.py
```

Più il cancello delle classi CSS uscito con la 3.20.0, e il bump di versione —
senza il quale i client non si aggiornano.

---

## §10 · I rischi

| Rischio | Come lo si vede |
|---|---|
| Il pallino diventa il nuovo badge morto | §8.1 e §8.2, scritte per mutazione |
| Le due parole divergono (menu vs chat) | §8.4, la sponda |
| Il raggruppamento della nav rompe il cassetto mobile | `main.js:39` chiude il cassetto su `.nav-item`: le etichette di sezione non lo sono. Verifica dal vivo su iPad |
| `GET /api/pending` a ogni risposta della chat pesa | Due `COUNT(*)` su SQLite locale. Se pesasse, si vedrebbe nei consumi |
| L'utente legge «Impegni» come la propria agenda | §2.1, dichiarato e accettato: si corregge da solo aprendo la pagina |

---

## §11 · L'ordine

1. `count_pending()` sui due archivi + `GET /api/pending` + le sue prove.
2. `pending-badge.js` + `.nav-badge` in `hiris-theme.css` + le prove del
   pallino.
3. Il raggruppamento della `side-nav` e le due voci nella barra della chat.
4. Le etichette: Impegni, Proposte — menu, titoli di pagina, briciola.
5. Lo storico compresso, sulle due pagine.
6. Le descrizioni degli strumenti + il cancello della sponda.
7. Verifica dal vivo sulla casa, poi rilascio.
