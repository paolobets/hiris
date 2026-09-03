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

### 4.1 Cosa conta — e non è la stessa cosa nelle due voci

Il pallino risponde a una domanda sola: **c'è qualcosa che aspetta me?** Le
due pagine rispondono in due modi diversi, ed è la ragione per cui sono due
pagine.

- **Proposte** → le costruzioni in `STATES_SOSPESO`
  (`action/construction/revisions.py`: `in_attesa`, `in_corso`). Una proposta
  in attesa aspetta letteralmente te: senza il tuo sì non succede niente.
- **Impegni** → **gli esiti conclusi che non hai ancora letto**. Non gli
  impegni in sospeso.

La seconda riga è la correzione che la prima prova del lettore ha fatto al
disegno di partenza, ed è giusta: *un impegno in sospeso non aspetta te,
aspetta l'ora*. Se il pallino contasse quelli, resterebbe acceso tutte le
volte che HIRIS ha qualcosa in programma per domani — cioè quasi sempre — e
un pallino sempre acceso **smette di essere letto**. Sarebbe il badge morto
di §4.2 in una forma nuova: non più un numero falso, ma un numero vero che
non è una notizia.

Ciò che è una notizia è l'esito: la promessa è stata mantenuta, o è fallita,
o è stata saltata, e tu non lo sai ancora. Quello aspetta te, e si spegne da
solo quando l'hai guardato.

Il conteggio degli impegni **in sospeso** non sparisce: sta
nell'intestazione della sezione, dentro la pagina, dove è un'informazione e
non un allarme.

> **Le Proposte aspettano te. Gli Impegni aspettano l'ora — tranne i loro
> esiti, che aspettano te.**

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
{"agenda_unread": 3, "constructions_pending": 1}
```

**Le chiavi dicono cosa contano, non dove stanno.** Se si fossero chiamate
`agenda` e `constructions` — simmetriche, come le rotte — avrebbero
nascosto che i due numeri contano due cose diverse (§4.1), e il primo che
avesse letto il JSON avrebbe creduto di vedere due volte lo stesso fatto.
Una chiave che mente è un commento che mente con l'aggravante di essere
eseguibile.

Su archivio non disponibile risponde **503** — e §4.2 fa il resto.

Due metodi nuovi, uno per archivio: `count_unread()` sulle promesse,
`count_pending()` sulle costruzioni. Sono codice nuovo, quindi in inglese
come vuole la legge; convivranno con `solo_in_sospeso=` di
`keeper/store.py::list`, che è italiano ed è **debito già dichiarato** della
fetta rimandata sul dato.

### 4.4 Quando si aggiorna

Non c'è nessun timer. Il numero cambia in momenti che si vedono tutti:

1. all'apertura di ogni guscio;
2. **dopo ogni risposta della chat** — è lì che nasce una promessa o una
   proposta, ed è l'istante esatto in cui il pallino deve accendersi mentre
   l'utente sta ancora leggendo la frase che lo manda a guardarlo;
3. dopo ogni azione sulle due pagine (Disdici, Approva, Rifiuta) e **dopo il
   segno di lettura** (§4.6) — è il momento in cui il pallino degli Impegni
   deve spegnersi, mentre l'utente è ancora lì che guarda;
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

### 4.6 Il segno di lettura — la colonna nuova

«Non letto» è un fatto che oggi non esiste da nessuna parte: va scritto.

**La colonna**: `esito_letto_ts REAL` sulla tabella `promesse`, `NULL` =
non letto. Il nome è **italiano** perché la tabella è italiana
(`quando_ts`, `nata_ts`, `risvegliata_ts`): una colonna inglese in mezzo a
quelle sarebbe peggio del debito che pretende di sanare, e la lingua del
database è dentro la fetta rimandata «il vocabolario del dato», che la
cambierà tutta insieme o non la cambierà.

**La migrazione**: `promesse` è oggi allo schema `version=1`. Va a `2` con
lo stesso meccanismo che `action/journal.py::_migration_2` usa già —
`PRAGMA table_info` per l'idempotenza, `ALTER TABLE … ADD COLUMN`, nessuna
tabella ricostruita. La colonna si aggiunge **anche a `_SCHEMA`**, o un
archivio nuovo (che `init_schema` timbra a `version` senza far girare le
migrazioni, `storage.py:55`) nascerebbe senza.

**Il travaso, e perché non è neutro**: dopo l'`ALTER TABLE` ogni riga ha
`NULL`, cioè *tutte* le promesse già concluse della casa vera risultano non
lette. Al primo avvio il pallino si accenderebbe con il numero di tutto lo
storico degli ultimi 90 giorni — un allarme per fatti vecchi di settimane.
Quindi la migrazione **segna come lette tutte le concluse esistenti**. Non è
vero che le hai lette: è una decisione, e si scrive nel commento della
migrazione. **Il segno di lettura comincia a contare dal giorno in cui
esiste**; ciò che è successo prima è storia, non notizia.

**Chi lo scrive**: `POST /api/agenda/read`, corpo `{"ids": [...]}`, chiamata
dalla pagina Impegni **dopo aver disegnato** la sezione «Esiti da leggere»
(§5.1), con gli identificatori che ha effettivamente messo sullo schermo —
non «tutti i non letti», che segnerebbe letto anche ciò che non è stato
disegnato. È un metodo non-safe: passa dal `csrf_middleware` come ogni POST
di questa interfaccia (stessa disciplina di `POST
/api/constructions/{id}/confirm`, che la pagina Proposte già usa).

Se la chiamata fallisce, le righe restano non lette e ricompaiono alla
visita dopo. È il guasto giusto da avere: **il segno di lettura sbaglia
sempre per eccesso di notizia, mai per difetto.**

**`serializza()`** (`keeper/promise.py::_CHIAVI`) porta il campo nuovo: la
pagina deve poter dire quali righe sono nella sezione di sopra, e la forma
di una promessa è UNA — quella. Il contratto JSON cambia di un campo, e i
test che lo bloccano diventeranno rossi: è il modo in cui si vede che è
cambiato.

---

## §5 · Le sezioni

### 5.1 «Esiti da leggere», in cima agli Impegni

Il pallino manda l'utente su quella pagina per una ragione precisa (§4.1).
Se ciò che lo ha chiamato finisse sepolto dentro uno «Storico» chiuso a
chiave, il pallino avrebbe mentito una seconda volta — stavolta sulla strada.

La pagina Impegni prende quindi **tre** sezioni:

| # | sezione | contenuto | stato iniziale |
|---|---|---|---|
| 01 | **Esiti da leggere** | concluse con `esito_letto_ts IS NULL` | aperta; **non compare se è vuota** |
| 02 | **In sospeso** | `in_attesa` + `in_corso`, col conteggio | aperta |
| 03 | **Storico** | tutte le concluse, col conteggio | **chiusa** |

Una riga appena conclusa sta in **due** sezioni: la 01 e la 03. È voluto, e
si dichiara: la 01 non è un archivio diverso, è una **finestra sul terzo** —
la parte che non hai ancora guardato. Con la 03 chiusa non si vedono mai
insieme, e alla visita successiva la 01 è sparita da sola.

La sezione 01 **non compare quando è vuota**, che è il caso normale: una
sezione vuota permanente insegna a non guardare quella zona dello schermo, e
il giorno in cui ha qualcosa dentro non la si vede più.

La pagina Proposte resta a **due** sezioni: lì non serve una terza, perché
ciò che aspetta l'utente è già la prima («In attesa»).

### 5.2 Lo storico compresso

Le due pagine hanno **già** la sezione «Storico». Non serve costruirla:
serve chiuderla.

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
| La **lingua** del database, i valori di dominio, le chiavi fra motore e pagina | Rimandati insieme, in una fetta sola: «il vocabolario del dato» |
| `#/agenda`, `#/constructions`, `constructions` nel codice | §2.3 |
| Qualunque cancellazione | §5.2 |

**Una colonna sì, la lingua no.** Il proprietario ha aggiunto la colonna a
questa fetta (03/09) dopo aver letto §4.1: senza il segno di lettura il
pallino degli Impegni non può esistere nella forma giusta, e sarebbe nato
già sbagliato per poi essere rifatto. Quindi `esito_letto_ts` **si scrive
adesso** (§4.6).

Questo **non** riapre la fetta sul vocabolario del dato. Si aggiunge una
colonna alla tabella `promesse`, nella lingua che quella tabella già parla;
non si rinomina nessuna colonna esistente, non si tocca `solo_in_sospeso=`,
non si toccano i valori di dominio. La distinzione è netta e va tenuta:
**aggiungere un fatto che manca è un'altra cosa dal rinominare i fatti che
ci sono.** La prima costa una migrazione additiva e reversibile; la seconda
costa la riscrittura di ogni query che li nomina.

---

## §8 · Le prove

Ogni prova qui sotto deve poter **fallire**: la finta deve saper produrre il
difetto che la prova cerca.

1. **Il pallino non mente** — con la rotta che risponde 503, e con la rotta che
   va in errore di rete, il pallino **non è nel DOM**. La prova per mutazione:
   un'implementazione che scrive `0` in caso d'errore la fa diventare rossa. È
   la prova che il badge morto non aveva.
2. **I due pallini contano due cose diverse** (§4.1) — su un archivio con
   tre proposte `in_attesa` + una `in_corso`, e con due promesse concluse non
   lette **più cinque promesse in sospeso**, i numeri sono **4** e **2**. La
   mutazione che questa prova deve uccidere è quella che verrebbe scritta per
   simmetria: contare i sospesi anche sugli Impegni darebbe 4 e 5.
3. **Zero non compare** — archivio che risponde `{"agenda_unread": 0}`:
   nessun pallino.
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
8. **La migrazione non inventa notizie** (§4.6) — si costruisce un archivio
   `version=1` con lo schema VECCHIO, ci si scrivono dentro promesse
   concluse, lo si apre con il codice nuovo: la colonna c'è, e
   `count_unread()` risponde **0**. La mutazione da uccidere è la migrazione
   che aggiunge la colonna e si ferma lì: quella risponderebbe col numero di
   tutto lo storico. Questa prova è l'unica che tocca il difetto vero, cioè
   ciò che succede **sulla casa del proprietario** al primo avvio dopo
   l'aggiornamento — non su un archivio nato oggi.
9. **La migrazione è idempotente** — girarla due volte non solleva e non
   cambia i conti (`PRAGMA table_info`, come `_migration_2`).
10. **Un archivio nuovo nasce già a posto** — nessuna migrazione girata
    (`storage.py:55`), e la colonna c'è lo stesso: è la prova che
    `_SCHEMA` è stato aggiornato insieme alla migrazione, e non solo lei.
11. **Il segno di lettura segna ciò che è stato mostrato** — `POST
    /api/agenda/read` con due id su tre non lette: dopo, `count_unread()`
    risponde 1. E marcare una promessa **in sospeso** non la fa sparire da
    nessuna parte: il segno vale sugli esiti, non sugli impegni.
12. **La sezione «Esiti da leggere» sparisce quando è vuota** (§5.1) — non
    è nel DOM, non è una sezione vuota con dentro «nessun esito».

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
| **La migrazione gira sull'archivio vero e sbaglia** | È l'unico passo irreversibile della fetta. Prove 8-10, più una passata su una **copia del `.db` della casa** prima del rilascio (§11) |
| Il pallino degli Impegni resta acceso perché il segno di lettura non parte | Prova 11. E il guasto è per eccesso: si rivede la notizia, non la si perde (§4.6) |

---

## §11 · L'ordine

1. **La colonna** (§4.6): `esito_letto_ts` in `_SCHEMA` + migrazione a
   `version=2` col travaso + `serializza()` + le prove 8, 9, 10. È il primo
   passo perché è l'unico irreversibile su una casa vera, e perché tutto il
   resto dipende da cosa c'è dentro.
2. `count_unread()` / `count_pending()` + `GET /api/pending` + `POST
   /api/agenda/read` + le prove 6 e 11.
3. `pending-badge.js` + `.nav-badge` in `hiris-theme.css` + le prove 1, 2, 3.
4. Il raggruppamento della `side-nav` e le due voci nella barra della chat
   (prova 7).
5. Le etichette: Impegni, Proposte — menu, titoli di pagina, briciola.
6. Le tre sezioni della pagina Impegni + lo storico chiuso su entrambe
   (prove 5 e 12).
7. Le descrizioni degli strumenti + il cancello della sponda (prova 4).
8. Verifica dal vivo sulla casa, poi rilascio.

**Sul passo 1 e la casa vera**: la migrazione gira all'avvio dell'add-on,
sull'archivio del proprietario, senza chiedere permesso. Prima del rilascio
si prova su **una copia del `.db` vero**, non solo su SQLite in memoria: la
prova 8 dice che il codice fa la cosa giusta, una copia del vero dice che la
fa su quei dati.
