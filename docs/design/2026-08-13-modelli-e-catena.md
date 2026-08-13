# La catena diventa l'unica verità — specifica

*13 agosto 2026. Nasce da tre difetti trovati dal proprietario usando il prodotto, e da due decisioni
che ha preso lo stesso giorno.*

**Il progetto della pagina, con i mockup e l'anatomia di ogni elemento, sta in
`docs/design/2026-08-13-progetto-pagina-modelli.md`.** Questa specifica fissa **cosa cambia nel
prodotto**, i confini e l'ordine; quel documento fissa **che forma prende**.

## 0. La frase che riassume tutto

> La pagina Modelli e' **vera riga per riga e falsa nel complesso**: dice «Claude API: Attivo»,
> «Abbonamento: Disattivato», «OpenRouter: Attivo» — tutte e tre corrette — e non mette mai in
> relazione le tre cose. **Non le manca un dato: le manca una frase.**

E la parola che regge quell'inganno esce dal prodotto: **«Attivo» non e' un fatto che il sistema
possa sostenere.** Significa «interruttore acceso **e** credenziale presente» e si legge «funziona».
Una chiave a credito esaurito e' «Attivo».

## 1. I tre difetti che la fetta chiude

1. **Accendere un provider costa due gesti** (metti la chiave *e* accendi l'interruttore), spegnerlo
   senza cancellare la chiave ne costa uno. L'interruttore fa **due mestieri opposti**, e sta in una
   pagina — quella dell'add-on — che non puo' nemmeno mostrarlo bene: il Supervisor rende un modulo
   **statico**, senza campi condizionali.
2. **L'abbonamento non entra in catena.** `models-route.js:183` lo dichiara: *«subscription non entra
   mai qui»*. Verificato sul codice: **il ponte non e' un anello, e' un bivio che sta PRIMA del
   router** (`handlers_chat.py:408`) **e non ha ritorno**. Quindi «usa il piano Claude Max, e se non
   e' disponibile passa a OpenRouter» **non e' inesprimibile nella pagina: non esiste nel prodotto**.
3. **Una regola di compatibilita' rende gli interruttori decorativi.** `model_activation.py:22`:
   `legacy = not any(toggles.values())` — se sono spenti **tutti**, e' attivo ogni provider **con
   credenziale**. E' lo stato dell'unica installazione esistente: due provider lavoravano mentre la
   pagina li mostrava spenti. *Trappola aggiuntiva*: accendendo **un** interruttore qualsiasi la
   compatibilita' cade e valgono solo quelli accesi — accendere il piano avrebbe spento Claude API e
   OpenRouter senza toccarli.

**E un quarto, piu' grosso di tutti, trovato progettando:** il modello scelto in `#/impostazioni`
**scavalca l'intera pagina Modelli** — se non e' `"auto"` sceglie il provider da se', salta la catena
e annulla ogni ripiego. Una pagina decide le priorita' e un'altra le ignora senza dirlo.

## 2. Le due decisioni del proprietario (13 agosto)

1. **Il ripiego si costruisce.** Il ponte smette di essere un bivio e diventa **il primo anello della
   catena**: se il piano non risponde, si passa al successivo. E' la frase che ha chiesto.
2. **La catena e' l'unica verita'.** Lo scavalco del modello in `#/impostazioni` **esce**: il modello
   si sceglie nella pagina Modelli, per provider.

E una terza, presa il giorno prima e che questa fetta esegue: **un concetto per posto — le
credenziali dove si custodiscono, le decisioni dove si prendono.**

## 3. L'idea portante, ed e' architetturale prima che grafica

Oggi la pagina riceve **gli ingredienti** (`providers[]`, `llm_strategy`, `chain_order`) e
**ricostruisce da sola l'esito**: `buildDisplayChain` (`models-route.js:378-382`) riproduce a mano
`reconcile_chain` (`model_activation.py:66-77`). Il commento di quest'ultima lo dice a voce alta:
*«This mirrors the frontend's buildDisplayChain»*.

**Due implementazioni della stessa regola, in due linguaggi. E' quello il meccanismo con cui la
pagina ha potuto mentire** — non una svista, una struttura.

> **Il backend restituisce la DECISIONE GIA' PRESA, non gli ingredienti.** Non «i cinque
> interruttori», ma «l'ordine effettivo, chi lo scavalca, e perche'». La pagina disegna cio' che le
> viene detto e **non calcola niente**.

Due conseguenze che valgono la fetta:
- il bivio e l'anello diventano **lo stesso codice di frontend con dati diversi**: il giorno in cui
  il ponte ripiega, la pagina lo disegna senza che nessuno la modifichi — e **non esiste nessun
  momento in cui la pagina possa disegnare un ripiego che il backend non fa**;
- se una regola di compatibilita' come quella del difetto 3 tornasse, **la pagina ne mostrerebbe
  l'effetto da sola**, perche' mostra il risultato.

## 4. Cosa si sposta, e dove

**Restano nella pagina dell'add-on** — cio' che si mette una volta: le quattro **chiavi** (Claude
API, token del piano, OpenRouter, OpenAI), l'**indirizzo di Ollama** (un endpoint, non una scelta),
**aspetto**, **livello di log**, **token interno**, **CIDR di rete**.

**Si spostano nella pagina Modelli** — le decisioni: i **cinque interruttori**, la **strategia**,
**nascondi i modelli gratuiti**, **quale modello Ollama** e il suo **timeout**, i tre del **ponte**
(attivo, scadenza, tetto giornaliero), i due dell'**embedding** (inerti, gia' mostrati li').

**Si sposta nelle impostazioni della chat**: `history_retention_days`. E li' si dichiara finalmente
cio' che nessuno aveva scritto — governa **anche** quanto HIRIS rilegge della conversazione in corso,
e `0` non cancella mai niente.

**Escono dal prodotto:**
- **`debug_expose_port`** — zero lettori nel codice; il suo unico effetto e' stampare sette righe che
  spiegano come aprire la porta **a mano** in un'altra sezione di Home Assistant. Un promemoria
  travestito da comando.
- **La regola di compatibilita'** di `model_activation.py:22`. Esisteva per gli aggiornamenti da
  pre-SP-2: **al mondo c'e' un'installazione sola ed e' quella del proprietario**, che e' qui.
- **`provider_models["ollama"]`** — verificato: e' un **fantasma, non un doppione**.
  `_clean_provider_models` lo scarta in lettura **e** in scrittura, e `local_model.model` vince
  persino su un modello fissato esplicitamente.

## 5. La migrazione, in due versioni

Togliere un'opzione dallo schema significa che **il Supervisor la scarta**: `AddonOptions.__call__`
elimina ogni chiave fuori schema, e **nessuna migrazione lato add-on e' possibile** (verificato sul
sorgente del Supervisor). `llm_strategy`, il ponte e il modello di Ollama hanno valori dell'utente
che sparirebbero **in silenzio**, riportandolo ai default senza che se ne accorga.

- **Versione A** — HIRIS legge dal **proprio archivio** e, se e' vuoto, **copia il valore
  dall'opzione dell'add-on**, dichiarandolo nel log. Le opzioni restano nello schema. Un avvio, e i
  valori sono al sicuro.
- **Versione B** — le opzioni escono dallo schema. A quel punto non serve piu' niente.

**Non accorpare A e B.** E' l'unico modo per non perdere valori, ed e' gia' costato una lezione su
questo ramo.

## 6. Cosa NON fa questa fetta

- **Non tocca le chiavi**: restano dove sono, per la ragione detta.
- **Non annida altre opzioni** nella pagina dell'add-on: annidare azzera il valore salvato, e per i
  provider costerebbe **denaro** (riaccendere un provider spento apposta), per il blocco avanzate
  **sicurezza** (un CIDR azzerato torna a un default piu' largo).
- **Non progetta un catalogo di modelli**: OpenRouter ne offre piu' di duecento, e un elenco cosi'
  distruggerebbe la leggibilita' che la pagina costruisce. Il progetto propone preset curati, un
  campo che e' insieme filtro e inserimento libero, e il numero totale come deterrenza.
- **Non risolve il modello ritirato**: oggi un `404` non fa scattare la protezione, viene richiesto a
  ogni turno per sempre, e «Errore temporaneo del servizio AI» **finisce in cronologia**. E' un
  difetto vero, dichiarato, e non di questa fetta.

## 7. Gli invarianti che questa fetta deve rendere impossibili da violare

1. **Un provider e' usato se e solo se sta in catena.** Nessuna seconda rappresentazione dello stato:
   e' la seconda rappresentazione che permetteva alla pagina di mentire.
2. **La pagina non calcola la topologia.** Se un test trova logica di ordinamento nel frontend, il
   difetto 3 e' tornato per un'altra porta.
3. **Nessuna parola che affermi piu' di cio' che il sistema sa.** «Attivo» e' vietata; cio' che si
   afferma dev'essere cio' che si e' misurato.
4. **Un valore si applica in un modo solo.** Oggi il modello di Claude API ha effetto **immediato**
   sul ponte e **solo al riavvio** sull'API, e la didascalia dice una cosa sola: **e' sbagliata**, non
   imprecisa.
5. **Ponte acceso senza token e' uno stato che non deve poter passare in silenzio**: oggi si
   raggiunge, e ogni messaggio scade dopo cinque minuti con un solo warning in `run.sh`.

## 8. L'ordine, se dovesse entrare a pezzi

Dal progetto, §15 — e' la scala di quanto ogni pezzo vale **da solo**:

1. **la frase in cima**, con i dati di oggi (piu' valore per riga di codice di tutto il resto);
2. **ponte acceso senza token** (un `if` su due booleani gia' nel payload);
3. **la catena come unica verita'** + la riga-provider col suo modello (chiude i difetti 1 e 3);
4. **la scrittura a caldo** (senza, la pagina resta una che confessa);
5. **gli esiti osservati** per provider (chiude il caso del proprietario: «Claude e' primo **e sta
   rifiutando da quaranta richieste**»);
6. **la topologia calcolata dal runtime** (rende irreversibili i cinque sopra);
7. **il ripiego dal ponte alla catena** (il piu' grosso, e l'unico che rende vera la frase chiesta).

## 9. Le verifiche che solo la casa vera puo' dare

Questa fetta tocca **come HIRIS sceglie a chi chiedere**, e l'unica installazione al mondo e' quella
del proprietario. Vanno provate li':
- il **ripiego vero**: il piano non risponde → il turno passa al successivo **e la pagina lo mostra**;
- la **migrazione della versione A**: dopo l'aggiornamento i valori sono ancora quelli, e il log lo
  dice;
- il caso concreto di oggi — **chiave Claude a credito zero, piano pagato e fermo, OpenRouter che
  paga a consumo**: la pagina deve renderlo leggibile a colpo d'occhio e correggibile in pochi gesti.
  **E' il metro di questa fetta**, non un esempio.
