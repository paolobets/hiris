# Il cervello, da capo

**Data:** 25 agosto 2026 · **Stato:** brainstorming aperto, nessuna decisione implementativa presa
**Supera e annulla:** ogni documento sul Brain precedente al refactor 2.0, e la sezione ② dello
scope 2.0 (`2026-08-04-scope-hiris.md`) per la parte che riguarda il cervello.

> **Decisione del proprietario, 25 agosto:** il cervello va **rifatto da capo**. Anche le due
> «regole dure» dello scope 2.0 — *non tocca senza un sì*, *impara liberamente* — non si danno per
> acquisite: si riparte dalla domanda più a monte.

Questo documento non decide come si costruisce. Fissa **cosa abbiamo capito** in un brainstorming
che è ancora aperto, perché riconquistarlo costerebbe più che scriverlo.

---

## 1. L'esempio fondativo

Il proprietario lo ha portato per spiegare a cosa serve il cervello, e contiene il prodotto intero:

> *Il riscaldamento si accende sempre alle 15:30 e la casa è calda alle 16:30. Ma il mercoledì
> rientri alle 17:30 — sarebbe meglio posticipare di un'ora.*

Per **dire** quella frase servono quattro cose, e nessuna è una notifica:

| | |
|---|---|
| Cosa fa la casa | il riscaldamento parte alle 15:30 |
| Che effetto ha | la temperatura arriva a destinazione alle 16:30 |
| Cosa fa la persona | il mercoledì rientra più tardi, e **non per caso** |
| Lo scarto fra i tre | un'ora di casa calda a vuoto |

**Il cervello che serve non è un osservatore che segnala: è uno che tara.** Il suo prodotto non è un
avviso, è *«questa cosa andrebbe spostata di un'ora il mercoledì»*.

Le tre direzioni proposte all'inizio — accorgersi di ciò che **non va**, di ciò che si **spreca**, di
ciò che si **ripete** — il proprietario le ha volute **unificate**, e questo esempio è la prova che
sono la stessa cosa vista da tre lati.

## 2. La correzione che cambia il problema

> **«Possono anche non esserci automazioni.»** Il riscaldamento può essere governato dalla
> programmazione interna del termostato. In Home Assistant **la regola non esiste**: esiste solo il
> suo effetto.

Tre conseguenze, in ordine di gravità.

**Il cervello deve dedurre le regole che la casa già segue, senza poterle leggere.** «Parte alle
15:30» non è un dato: è una **conclusione** tratta da settimane di osservazione. È un mestiere
diverso dal leggere un'automazione — e nessuna delle capacità costruite finora lo copre.

**Non può conoscere la causa.** Il termostato attivo alle 15:30 può essere la sua programmazione, o
una mano, o una caldaia con un proprio orologio. Un cervello onesto deve poter dire *«succede sempre
alle 15:30, e non so cosa lo decida»*. Qui la disciplina del prodotto — dichiarare l'incertezza
invece di affermare una causa — non è una rifinitura: è la sostanza.

**Il rimedio non è uno solo.** Decisione del proprietario: **la risposta si adatta a ciò che HIRIS
può davvero raggiungere.**

- Se **non** può intervenire: lo capisce e lo **segnala**. La modifica la fa la persona, fuori dal
  sistema o dentro Home Assistant.
- Se **può**: propone la correzione sugli oggetti veri di Home Assistant. E ne propone di **nuovi**.

Il proprietario lo immagina **interattivo**: «un vero e proprio assistente domestico proattivo,
osservatore».

## 3. Il cervello non guadagna un canale di scrittura

Osservazione emersa dal disegno, e vale come vincolo: quando il cervello propone una modifica e la
persona dice sì, **la modifica non la scrive il cervello**. La scrive `costruisci`, con il cancello
di consenso, l'anteprima validata da Home Assistant, l'archivio delle versioni e il ripristino —
tutto già esistente dalla fetta «costruire».

> **Il cervello non guadagna nessuna superficie di scrittura sua.**

Il che rovescia la domanda di sicurezza: non «che permessi gli diamo», ma **«quali porte esistenti
gli lasciamo usare»** — un elenco corto di nomi, nella forma che `SOLA_LETTURA` usa già per i turni
delle promesse. Non una scala di autonomia da configurare.

Vincolo esplicito del proprietario: **non deve diventare un prodotto con mille configurazioni.** La
granularità la mette il prodotto col suo giudizio, non l'utente con un pannello.

## 4. Che forma ha la conoscenza

Il proprietario, sulla memoria:

> *Il cervello deve costruire una sua memoria, con le informazioni più adatte ai suoi ragionamenti —
> questa è anche la base per il suo autoapprendimento. Deve poter accedere anche alla memoria data
> dai vari utenti che usano l'applicazione. Il concetto è che crei una vera e propria memoria come
> rete neurale, con informazioni che si collegano l'una all'altra creando una vera e propria
> conoscenza, che possa usare lui ma anche essere passata alla chat, perché la chat sia sempre più
> evoluta nelle risposte.*

E, sul problema più difficile:

> *Diverse informazioni — qualcuno le deve **interpretare, leggere, gestire e ponderare**.*

### Due cose già vere, che non vanno reinventate

- **La struttura associativa esiste in piccolo.** I ricordi hanno le **ancore**: sono agganciati a
  entità, aree, dispositivi. Non è una rete — è una stella: tutto punta alle cose della casa, niente
  punta a niente altro. Ma il primo anello c'è.
- **La chat già legge quella memoria.** I ricordi entrano nel nucleo a ogni turno e si interrogano
  con `richiama`. «Passata alla chat» è per metà già vero. **Ciò che manca è che oggi solo la
  persona scrive: il cervello non ci mette niente.**

### La trappola, misurata e non opinata

Il documento 2.0 sul Brain porta una misura: il RAG vettoriale del prodotto vecchio era *«un
pedaggio pagato in scrittura su dati che si leggono con una `WHERE` su una data»*. Da lì la regola:

> **La memoria prende la forma del dato che contiene.**

È il motivo per cui **non si sceglie la tecnologia prima di sapere cosa ci va dentro**. «Rete
neurale» descrive bene la proprietà voluta — informazioni che si richiamano — ma scegliere lo
strumento adesso significa rifare il RAG con un altro nome.

### Quattro nature diverse, riconosciute e non ancora sistemate

| Esempio | Natura |
|---|---|
| «il termostato sta in camera» | relazione stabile |
| «il mercoledì rientri alle 17:30» | regolarità temporale, con una confidenza |
| «sotto i 20 gradi Paolo ha freddo» | preferenza **di una persona** |
| «il riscaldamento ci mette un'ora» | legge fisica **di questa casa** |

Alcune si contraddicono nel tempo, altre no. Alcune valgono per tutti, altre per una persona sola.

### Il multiutente

> **Se Paolo ha freddo a 20 gradi e Marta ha caldo, non è un conflitto da risolvere: sono due fatti
> veri.** Una memoria che li fonde perde l'informazione; una che li tiene separati deve sapere *a
> chi* appartiene ogni cosa che sa.

## 5. Le due misure che vincolano tutto

Prese sulla casa vera il 25 agosto 2026, e più decisive di qualunque argomento.

**La presenza arriva indietro tre giorni.** `person.paolo_bettinelli`, storico dettagliato: 3 punti
negli ultimi 3 giorni, **zero** oltre. E `person.*` non ha `state_class`, quindi **non esiste**
nessuna statistica a lungo termine.

> **Nella finestra che Home Assistant conserva non c'è nemmeno un mercoledì completo.** L'esempio
> fondativo **non è ricostruibile** dai dati di HA, oggi, in nessun modo.

Da cui: la domanda non è *se* il cervello debba avere una memoria propria — **senza, il cervello che
il proprietario ha in mente non può esistere.**

**Le fondamenta invece ci sono.** `andamento` misura a che ora la casa si scalda davvero, `accaduto`
dice cosa è successo e per mano di chi, `costruisci` sa scrivere una modifica in Home Assistant. Il
cervello non è un sottosistema nuovo: **è la cosa che usa quello che c'è.**

## 6. Cosa NON è deciso

- **Chi pondera.** Se una regolarità vista 8 volte su 9 valga più o meno di una cosa detta una volta
  dalla persona. Se una preferenza di Paolo valga in salotto quando in salotto c'è Marta. Se una
  legge fisica misurata a marzo valga ad agosto. È **il problema difficile**, ed è aperto.
- **Che forma ha la memoria** — e in particolare se conservi solo conclusioni, o anche le prove che
  le sostengono, o una traccia regolare di ciò che osserva.
- **Quando il cervello parla**, e come non diventa una macchina da notifiche.
- **Come si separano le persone** dentro la conoscenza.
- Se le due regole dure dello scope 2.0 tornino, in qualche forma, alla fine.

## 7. Da dove si comincia

Un fatto blocca ogni strada: **oggi i dati per verificare l'esempio fondativo non esistono.**
Qualunque cosa si progetti, la prima settimana in cui gira non avrà niente su cui ragionare.

Da cui la prima fetta, che si scrive da sola: **l'osservatore che ricorda e basta.** Non ragiona, non
parla, non tocca niente. Guarda le poche cose che servono all'esempio — presenza, termostato,
temperatura — e le annota **prima che Home Assistant le butti**.

Fra tre settimane ci saranno dati veri, e le domande difficili del §6 si risponderanno **guardando
invece che immaginando** — che è il metodo con cui questo progetto ha deciso le sue ultime due
fette, e le due volte le misure hanno smentito il ragionamento.

---

# L'osservatore — dove è arrivato il brainstorming

*(Aggiunto in coda alla sessione del 25 agosto. Confermato dal proprietario: «mi sembra prendere
forma correttamente». Nessuna decisione implementativa: è la forma, non il progetto.)*

## Il cervello è fatto di più attori

Parole del proprietario. **L'osservatore è il primo**, e questa sezione riguarda solo lui. Gli altri
non sono ancora stati nominati — è la prima cosa da riprendere.

## L'obiettivo è un prompt, ed è l'unica manopola

> **«Ottimizzare la casa e renderla confortevole»** — obiettivo dell'intero cervello, **gestibile da
> un prompt personalizzabile.**

Non una scala di autonomia, non un selettore d'ambito, non un pannello di permessi: **una frase**,
nella lingua in cui il proprietario pensa. La si cambia e cambia tutto a valle — cosa si osserva,
cosa si riassume, cosa vale la pena dire. È la risposta al vincolo «non deve diventare un prodotto
con mille configurazioni»: la manopola è **una**.

## La rilevanza si deduce, non si configura

Dall'obiettivo l'osservatore capisce **quali entità** contano. Il problema d'avvio — per giudicare la
rilevanza serve esperienza, il primo giorno non c'è — si scioglie perché **l'obiettivo è già un
criterio prima di qualunque esperienza**, e Home Assistant dichiara già la natura di ogni entità:
`device_class`, unità di misura, dominio, area. Cosa **consuma**, cosa **produce comfort**, cosa dice
**chi c'è**, cosa **disperde**.

Nessuna lista scritta a mano, nessun pannello. Poi l'osservatore **si allarga da solo**, mano a mano
che capisce.

**Il calendario è una fonte prevista.** «Il mercoledì rientri alle 17:30» dedotto dall'osservazione è
una statistica; **letto dal calendario è un fatto**, e disponibile dal primo giorno invece che dalla
nona settimana.

## Trasparenza al posto del permesso

**Decisione del proprietario.** L'osservatore si allarga senza chiedere, ma **esiste una pagina dove
in qualunque momento si vede cosa sta guardando e perché**, e da cui si può togliergli qualcosa.

Ragione: il permesso si logora — chi clicca «sì» quindici volte smette di leggere — la trasparenza no.

**Rifinitura proposta e non ancora decisa:** la prima volta che si allarga su qualcosa che riguarda
**le persone** (presenza, calendario), lo **dice**. Non un permesso da concedere: un avviso, una riga.
Non dipende dal fatto che qualcuno vada a guardare una pagina di propria iniziativa.

## Due strati, e il consolidamento di fine giornata

Parole del proprietario: *«durante il giorno traccio e poi alla fine giornata consolido l'intero
giorno con un set informativo di resoconto»*.

| | |
|---|---|
| **Il giorno corrente** | i cambi grezzi delle entità che l'obiettivo indica |
| **A fine giornata** | il **consolidamento**: per ogni entità, il riassunto che serve all'obiettivo |
| **Poi** | il grezzo del giorno si butta |

È la stessa forma che il recorder di Home Assistant usa per sé — dettaglio breve, riassunto lungo — e
porta con sé una **proprietà di sicurezza gratuita**: finché il grezzo di oggi esiste, un
consolidamento sbagliato si può rifare. **Sbagliare costa un giorno, non tutto.**

## La forma del riassunto discende dalla natura dell'entità

Non si decide entità per entità — sarebbero 848 decisioni, sbagliate almeno cento volte. La natura la
dichiara Home Assistant, e da lì:

| Natura | Cosa si conserva |
|---|---|
| temperatura | minimi, massimi, medie per fascia, attraversamenti di soglia |
| presenza | episodi dentro/fuori, con le durate |
| termostato | episodi acceso/spento, **e cosa ha fatto la temperatura mentre era acceso** |
| contatore | consumo del giorno e come si distribuisce |
| porta / finestra | aperture, durate, **e se qualcosa scaldava mentre era aperta** |

> **L'obiettivo sceglie QUALI entità, la natura decide COME riassumerle.** Nessuna delle due è una
> lista scritta a mano.

## Il modello sceglie, il codice fa i conti

Un consolidamento scritto da un modello ogni sera costa token tutti i giorni e sbaglia l'aritmetica.
Guidato dalla natura dell'entità, il codice lo fa gratis e non sbaglia.

È la regola della fetta del tempo — *sceglie il codice, non il modello* — applicata al posto giusto:
al modello la domanda «cosa è rilevante», al codice «quanto fa la media».

## Allargare è reversibile, restringere no

L'osservatore può cominciare a guardare cose nuove quando vuole. Ma **smettere** di conservare
qualcosa significa che fra sei mesi quel passato non esiste: può smettere di **consolidare**, mai
buttare ciò che ha già consolidato.

## Cosa resta aperto, dopo questa sessione

1. **Gli altri attori del cervello** — quali sono, oltre all'osservatore.
2. **Chi pondera** (§6): resta il problema difficile, intatto.
3. Se l'avviso sulla prima osservazione delle persone entra o no.
4. Dove vive materialmente questa memoria, e come si lega ai **ricordi** che già esistono con le loro
   ancore — perché la destinazione dichiarata dal proprietario è **una conoscenza collegata**,
   condivisa fra cervello e chat, e i ricordi ne sono già il primo anello.

---

# I quattro attori

*(Parole del proprietario, 25 agosto. Nomi e ruoli; non ancora un disegno.)*

| Attore | Cosa fa |
|---|---|
| **Osservatore** | guarda e ricorda. Tutta la sezione precedente riguarda lui |
| **Analista** | analizza le informazioni e **definisce cosa si potrebbe fare o meno** |
| **Attuatore** | **crea le soluzioni** indicate dall'analista |
| **Verificatore** | **verifica e monitora gli altri attori** |

Tre osservazioni che nascono dalla sola lettura dei quattro nomi, e che vanno tenute quando si
passerà al disegno.

**La catena separa il vedere dal giudicare dal fare.** Sono tre mestieri diversi con tre modi diversi
di sbagliare: l'osservatore sbaglia raccogliendo la cosa sbagliata, l'analista sbaglia concludendo,
l'attuatore sbaglia scrivendo. Tenerli distinti significa che un errore si può attribuire — ed è la
condizione perché il quarto possa esistere.

**L'attuatore non guadagna un canale di scrittura suo** (§3). «Crea le soluzioni» significa che passa
da `costruisci`, con il cancello di consenso che esiste già. È lui il punto in cui il cervello tocca
la casa, ed è l'unico: la sicurezza del cervello si concentra su un attore solo invece di essere
spalmata su tutti e quattro.

**Il verificatore è la parte inusuale, ed è la più interessante.** Un attore il cui oggetto non è la
casa ma **gli altri attori**. È esattamente la disciplina che questo progetto applica a sé stesso —
ogni implementatore ha una review indipendente, e in questa fetta le review hanno trovato un difetto
dopo *ogni* correzione. Se quella pratica funziona sugli agenti che scrivono il codice, ha senso che
il prodotto la applichi ai propri attori.

Da chiarire quando si arriverà a disegnarlo: **cosa fa il verificatore quando trova qualcosa.** Ferma
l'attuatore? Segnala alla persona? Abbassa la confidenza dell'analista? Sono tre poteri molto diversi,
e il quarto attore è quello che ha più bisogno di limiti scritti — perché è l'unico che ha autorità
sugli altri.

## Cosa resta aperto, aggiornato

1. ~~Gli altri attori del cervello~~ — **nominati**: analista, attuatore, verificatore. Da disegnare.
2. **Chi pondera** — probabilmente l'analista, ma va detto e non dato per scontato.
3. Se l'avviso sulla prima osservazione delle persone entra o no.
4. Come la memoria si lega ai **ricordi** che già esistono con le loro ancore.
5. **Che poteri ha il verificatore** quando trova che un altro attore ha sbagliato.

---

# L'osservatore — la forma decisa (26 agosto)

## Cos'e' una riga: il cambio nudo

Durante la giornata l'osservatore annota **il cambio cosi' com'e'**: entita', istante, valore.
Nessun giudizio in scrittura.

**La ragione e' una sola, e regge tutto il disegno.** La proprieta' che rende buono lo schema a due
strati e' che *sbagliare il consolidamento costa un giorno, non tutto* — domani si rifa' con una
logica migliore, perche' il grezzo e' ancora li'. **Quella proprieta' regge a una condizione: che nel
grezzo non ci sia nessun giudizio.**

Le due alternative sono state scartate per questo:

- **L'episodio gia' chiuso** («termostato acceso 15:30→17:05») e' meta' delle righe e assomiglia al
  ragionamento, ma decidere *quando finisce* e' un giudizio fatto **in scrittura**: se sbaglia,
  sbaglia per sempre, e la rete di sicurezza sparisce. Ed e' esattamente cio' che il consolidamento
  deve produrre: anticiparlo non aggiunge, toglie la possibilita' di rifarlo.
- **Il cambio piu' il contesto attorno** decide **oggi** cosa sara' rilevante domani, e duplica lo
  stesso valore in ogni riga che lo nomina.

**E c'e' un argomento che viene dalla casa vera.** Le quattro luci nascoste della sala da pranzo sono
**un sistema solo**: tre lampade LIFX, il loro gruppo, e l'interruttore fisico che le comanda
(`legami` lo dice — quell'interruttore e' l'innesco di `automation.interruttore_gruppo_lifx`). Col
cambio nudo quel legame si scopre **dopo** e si applica al consolidamento; con l'episodio scritto
per entita' si sarebbe gia' deciso che sono quattro cose, e nessun consolidamento potrebbe piu'
rimetterle insieme.

*Volume misurato: ~6.000 cambi al giorno su tutta la casa; ristretto a cio' che serve, un migliaio o
due. Su SQLite non e' un criterio — la scelta si e' giocata tutta sul giudizio, non sul peso.*

## Si osserva anche Home Assistant

Parole del proprietario: *«per dire che la casa e' efficiente, confortevole e in buono stato
l'osservatore deve osservare anche HA»*. **«In buono stato» e' la terza gamba dell'obiettivo**, e le
superfici esistono gia' nel client (problemi delle integrazioni, salute del sistema, registro
errori).

**Aperto:** «l'integrazione Reolink e' rotta da due giorni» **non e' un cambio di stato di
un'entita'** — e' una condizione del sistema. La sua riga non ha la stessa forma, e va decisa.

## Il pavimento: il prompt allarga, non restringe

> **Punto dichiarato fondamentale dal proprietario:** *«attenzione a cosa entra nelle osservazioni,
> che sono decise dal prompt dell'obiettivo dell'intero brain»*.

Il pericolo, reso esplicito: **se il prompt decide cosa entra, il prompt e' un punto singolo che puo'
accecare l'osservatore senza che nessuno se ne accorga** — e cio' che non e' stato osservato **non
esiste piu'**. Riscrivere il prompt fra tre mesi non fa ricomparire i tre mesi mancanti. Il danno si
scopre il giorno in cui serve quel dato, cioe' troppo tardi.

**Decisione: un pavimento fisso che il prompt non puo' togliere.** Presenza, temperature, aperture,
consumi, salute di Home Assistant si osservano **comunque**, qualunque cosa dica l'obiettivo. Il
prompt **allarga** e da' priorita'; non restringe mai sotto il pavimento.

Costa poche decine di entita' e rende **impossibile** il danno irreversibile. Il contenuto esatto del
pavimento resta da fissare.

## Cosa resta aperto per l'osservatore

1. **Dove vive la memoria** — un archivio nuovo, e questo prodotto ne ha gia' seppellito uno
   (`history.db`, uscito perche' scriveva e nessuno leggeva). Va deciso **esplicitamente**, non di
   straforo, e va detto perche' questa volta e' diverso.
2. **La forma della riga per la salute di HA**, che non e' un cambio di stato.
3. **Per quanto vivono i consolidati** — per sempre? anni? E cosa succede quando il prompt cambia.
4. Il contenuto esatto del pavimento.

## Una memoria sola, due nature, la provenienza scritta

Parole del proprietario: *«mi piacerebbe che fosse tutto nella pagina memoria, con l'evidenza di
cosa si e' salvato in autonomia — i fatti — e cosa gli e' stato detto: le istruzioni date dagli
utenti. Il grezzo puo' stare in un oggetto transitorio giornaliero. Cosi' la memoria di HIRIS
diventa una sola, su cui sia chat che brain lavorano, e su cui io posso avere il controllo e in caso
applicare modifiche.»*

**La conseguenza che rende sicura la scelta: la provenienza e' un campo di prima classe.** Ogni cosa
che HIRIS sa porta scritto chi ce l'ha messa — la persona, oppure il cervello, e in quel caso con
quali prove e quanta fiducia. Senza, una deduzione sbagliata finirebbe per sembrare una cosa che
l'utente ha detto.

**Risolve per meta' il problema del ponderare** (§6): chi pondera ha almeno un criterio solido da cui
partire.

**E la correzione umana e' essa stessa un'informazione.** Quando il proprietario corregge un fatto
dedotto, quello non e' solo un dato aggiustato: e' il segnale piu' forte che il cervello possa
ricevere su come sta sbagliando a ragionare.

**Due nature, una pagina.** Un ricordo dell'utente (*«queste due luci sono di servizio, devono
restare accese»*) e un fatto osservato (*«il mercoledi' rientri fra le 17:15 e le 17:45, 8 settimane
su 9»*) **non hanno la stessa forma**: il secondo porta confidenza, prove, un periodo, e cambia nel
tempo; il primo vale finche' non lo cambi. Restano **due cose distinte** — la memoria prende la forma
del dato che contiene — ma la pagina le mostra **insieme**, filtrabili, e **chat e cervello leggono
entrambe**. Nessuna delle due si deforma per stare nel formato dell'altra.

**Il grezzo resta fuori dalla memoria**: oggetto transitorio giornaliero, nasce e muore. Non compare
nella pagina, non e' conoscenza — e' materiale di lavoro.
