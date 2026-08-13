# HIRIS — Changelog

## [2.2.1] — «Le ho spente» invece di «non è cambiato niente» (2026-08-13)

**Correzione del primo difetto trovato usando davvero la 2.2.0 in una casa.**

**Cosa si vedeva.** Chiedevi di spegnere due abat-jour. Si spegnevano. E HIRIS ti
rispondeva che erano ancora accese:

> «Il comando è partito correttamente ma non ha avuto effetto — probabile problema di
> comunicazione col dispositivo. Vuoi che riprovi?»

Non capitava ogni tanto: capitava **quasi sempre**, su qualsiasi comando riuscito.
Chiedendo di portare il termostato a 19.5° ci andava davvero, e HIRIS ti diceva che era
rimasto a 17.5°.

**Cosa si vede adesso.** «Le ho spente.» «Era a 17.5°, adesso è a 19.5°.» Quando qualcosa
succede, HIRIS lo racconta come successo.

**Perché sbagliava.** Guardava nel posto sbagliato. Dopo aver dato il comando rileggeva lo
stato dalla sua copia interna della casa, che si aggiorna qualche istante più tardi: ci
trovava sempre la situazione di prima. Adesso il «dopo» glielo dice **Home Assistant**,
che gli riporta cosa è cambiato mentre eseguiva il comando — la sola misura presa nel
momento giusto.

**E soprattutto: HIRIS non inventa più una causa.** Quella frase sul «problema di
comunicazione col dispositivo» era una diagnosi che HIRIS non aveva alcun modo di fare, e
mandava a cercare un guasto che non esisteva. Quando davvero non risulta cambiato niente,
adesso te lo dice per quello che è — *Home Assistant non ha riportato nessun cambiamento*
— senza dare la colpa a un dispositivo che sta benissimo.

**Una tapparella lenta resta un caso a parte, ed è giusto così.** Se ci mette venti
secondi, nell'istante del comando non è ancora cambiato niente e HIRIS te lo dice; ma è
un'osservazione, non un allarme, e la differenza fra «non è ancora cambiato» e «è rotto»
adesso c'è.

**Un dettaglio in più nel registro (`Log`).** Ogni azione porta ora anche quanti
cambiamenti Home Assistant ha riportato, e al primo comando dopo ogni avvio compare una
riga che descrive la forma esatta della risposta ricevuta. Serve a chi segnala un
problema: è il dato che permette di capire cosa è successo senza tirare a indovinare.

### E il benvenuto della chat non si smentisce più

Aprendo HIRIS, la prima cosa che si leggeva era: *«Non agisco: non accendo, non spengo e
non modifico niente»*. Da tre giorni non era più vero. Adesso dice cosa HIRIS fa davvero
— accende, spegne, imposta se glielo chiedi — e cosa continua a non fare: non scrive
automazioni né script, non programma niente per dopo, e **non parte mai da sola**.

## [2.2.0] — Adesso puoi chiedergli di fare (2026-08-12)

**Fino a ieri HIRIS sapeva e basta. Da questa versione, se glielo chiedi, fa.**
«Spegni la luce della cucina» non è più una domanda a cui rispondere: è una cosa
che succede. HIRIS chiama i servizi di Home Assistant — accende, spegne, imposta —
sulle entità che gli indichi, e poi ti racconta com'è andata.

Il resto di questa nota dice tre cose: cosa vedi succedere, cosa succede prima che
qualcosa si muova, e cosa questa versione **non** fa ancora.

### Cosa vedi succedere

Scrivi in chat quello che vuoi. Sotto la risposta compare la targhetta di uno
strumento nuovo, **`esegui`**: è l'unico punto in cui HIRIS tocca la tua casa, e
cliccandola vedi con quali argomenti è stato chiamato — quale servizio, su quale
entità. Gli altri quattro strumenti (`cerca`, `guarda`, `ricorda`, `richiama`)
continuano a fare quello che facevano: leggere e ricordare.

Se gli dai un nome invece di un'entità («la luce della cucina»), HIRIS cerca prima
e agisce dopo: gli id delle entità li prende dalla tua casa, non se li inventa.

### Prima di toccare qualcosa, controlla che si possa

Non c'è nessuna conferma da confermare — e non è una dimenticanza, è una scelta:
prima la capacità, poi le sicurezze, in una fase pensata apposta. Al posto della
conferma c'è una **verifica**, fatta sulla *tua* installazione e non su un elenco
scritto da noi:

- **quel servizio esiste in questa casa?** HIRIS chiede a Home Assistant cosa sa
  fare, e lo richiede da sé man mano che passa il tempo: un'integrazione che
  installi oggi entra nel giro senza che HIRIS venga aggiornato;
- **quell'entità esiste?**
- **quel servizio si applica a quell'entità?** `light.turn_off` su una presa viene
  fermato prima di partire;
- **quel parametro è un parametro di quel servizio?**

E quando dice di no, **dice cosa esiste davvero**: non «non posso», ma «"quello" non
esiste, i servizi di questo dominio sono questi». È scritto per il modello, che se
ne serve per correggersi da solo, ma lo leggi anche tu nel log dell'add-on.

### Dopo, ti dice cosa è successo — non cosa avevi chiesto

Chiamato il servizio, HIRIS **rilegge lo stato** delle entità che ha toccato e
confronta prima e dopo. «L'ho spenta» te lo dice solo se è spenta.

Il confronto guarda lo stato **e i valori**: la temperatura di un termostato, la
luminosità di una luce, la posizione di una tapparella, il volume. Serve perché
«metti il termostato a 21» non cambia lo stato — il clima resta `heat`, cambia
il numero — e guardando il solo stato HIRIS ti avrebbe risposto che non è
cambiato niente di un comando che aveva funzionato. Se il valore che cambia è
uno che HIRIS non tiene in memoria (il colore di una luce, per esempio), vedrai
l'avviso del punto qui sotto: dice il vero su ciò che ha potuto guardare.

Due casi che vedrai, e che sono la parte onesta di questa versione:

- **«la chiamata è andata a buon fine ma nessuno stato è cambiato».** Succede
  quando la luce era già spenta, quando il servizio non cambia nessuno stato, e
  anche quando la cosa **si sta ancora muovendo**: una tapparella impiega venti
  secondi e HIRIS rilegge dopo pochi millisecondi. Non aspetta apposta: preferisce
  dirti un fatto («in questo momento non è cambiato niente») invece di indovinare.
- **«non sono riuscito a rileggere lo stato: non so dire cosa sia cambiato».** La
  chiamata è partita, la lettura dopo no. Dichiara di non sapere invece di
  dedurre che sia cambiato tutto.

E se HIRIS non riesce a leggere cosa Home Assistant sa fare, o non vede lo stato
della casa, **si ferma e lo dice** — «non ho potuto controllare» — invece di
spacciare la propria cecità per un «non esiste».

### Quando la tua frase ammette più letture

«Accendi il bagno», e in bagno hai due luci, uno scaldasalviette e un aspiratore.
HIRIS **agisce sulla lettura più naturale e ti dice cosa ha fatto**, invece di
fermarsi a chiedere: quello che fa si annulla dicendo il contrario, quindi
sbagliare costa una frase mentre domandare costerebbe qualcosa a ogni richiesta.
Chiede solo quando una lettura naturale non c'è.

Se lo correggi, ti proporrà di ricordare la tua **preferenza generale** — «quando
dico di accendere una stanza, di solito intendo le luci» — e non una sostituzione
della tua frase con delle entità. È voluto: una sostituzione ti toglierebbe la
possibilità di intendere il riscaldamento con le stesse parole, e non varrebbe per
nessun'altra stanza.

### Cosa NON fa ancora

Nessuna di queste è un difetto da segnalare.

- **Non costruisce niente.** Non crea e non modifica automazioni, script, scene o
  dashboard: non scrive oggetti dentro Home Assistant. **Ma le tue automazioni
  non sono fuori portata**, e questo va letto alla lettera: *accendere e
  spegnere* un'automazione è una chiamata a un servizio come tutte le altre
  (`automation.turn_off`), e HIRIS la fa se gliela chiedi. È l'unica azione di
  questa versione che **non si vede guardando la casa** e che resta finché
  qualcuno non la riattiva — il riscaldamento che non parte più, e nessuno che
  sappia perché. Se succede, HIRIS te lo dice; ma se il riavvio dell'add-on
  cancellasse quella conversazione, il log dell'add-on resterebbe l'unico posto
  in cui l'informazione esiste.
- **Non ha un modo suo di raggiungerti.** Nessuna notifica, nessun push,
  nessun canale: quando non sei nella chat, HIRIS non ti parla. Questa però è
  una frase su HIRIS, **non una garanzia sulla tua casa**: se la tua
  installazione ha entità `notify.*` (dalla 2024.6 di Home Assistant è una
  configurazione ordinaria), `notify.send_message` passa gli stessi controlli
  di qualunque altro servizio. Non c'è niente nel codice che tenga fuori una
  categoria di servizi, e dire il contrario sarebbe promettere un freno che
  non esiste.
- **Non fa niente da solo.** Non esiste nessun percorso — un orario, un evento, una
  regola, una ronda — che possa far partire un'azione senza di te. **Ogni azione
  nasce da una tua frase in questa conversazione.**
- **Non sa rimandare a più tardi.** «Spegni le luci fra un'ora» non è una cosa che
  può prendere in carico: non c'è nessun promemoria e nessuna coda. O adesso, o mai.
- **Non ti chiede conferma e non ha livelli di permesso.** Vedi sopra: è una scelta
  di questa fase. Se ti pare che manchi un freno, **segnalalo lo stesso**.
- **Agisce sulle entità**, non su un'area o su un dispositivo come bersaglio: se
  chiedi una stanza, HIRIS ne ricava le entità e agisce su quelle.

### Prima di fidartene su una casa vera

Questa versione fa cose che nessuna suite di test può provare da sola: che i
servizi che HIRIS legge siano davvero quelli della *tua* installazione, si vede
solo sulla tua installazione. **`docs/prova-azione.md`** è il foglio delle nove
prove da fare, in mezz'ora, con cosa deve succedere e come si riconosce il
fallimento. La prima di quelle prove va fatta prima delle altre.

---

## [2.1.0] — Esce l'integrazione documentale (2026-08-12)

**HIRIS non legge più i tuoi documenti, e smette di registrare la tua casa per
conto suo.** L'integrazione con Mayan EDMS esce da questa versione. È una scelta
deliberata, non un guasto: sarà rivista più avanti, con un progetto.

### Cosa non c'è più

- **Mayan EDMS.** Le cinque opzioni `mayan.*` (URL, token, ID del tag,
  sensibilità, intervallo di interrogazione) non compaiono più nella
  configurazione dell'add-on, e HIRIS non interroga più Mayan.
- **L'archivio dei documenti e dei ricordi «in coda»** — quello che HIRIS
  riempiva con i documenti ingeriti e con i riepiloghi notturni.
- **La pagina «Storicizzazione»** e la registrazione dello storico. HIRIS non
  tiene più una cronaca propria della casa: la cronaca la tiene Home Assistant,
  che lo fa già e lo fa meglio.
- **Il riepilogo notturno delle 04:00** e la compattazione delle 03:30.

### Se avevi configurato Mayan

**Non devi fare niente, e non perdi nessun file.** Alla prima partenza HIRIS
trova le tue vecchie opzioni `mayan.*` e semplicemente non le legge più: non
sono più nello schema dell'add-on, quindi spariscono dalla pagina di
configurazione. Home Assistant potrebbe segnalarle nel proprio log come opzioni
sconosciute finché restano salvate: se succede, apri la Configurazione
dell'add-on e salva una volta: le righe vecchie se ne vanno con quel salvataggio.
**Nessun file viene cancellato**, né dentro HIRIS né sul tuo Mayan: i documenti
restano dov'erano, in Mayan, e gli archivi che HIRIS si era creato
(`knowledge.db`, `hiris_memory.db`, `history.db`, `vault.db`,
`history_policy.json`) restano intatti nella cartella dati dell'add-on. Se ci
sono, HIRIS lo scrive nel log all'avvio, una riga per file, invece di
incontrarli in silenzio.

Restano intatti, ma **da questa versione nessun codice li riapre più**: quello
che c'era dentro — i ricordi migrati dalla 1.x, ciò che era entrato da
`POST /api/knowledge`, i documenti indicizzati — non è più raggiungibile da
nessuna pagina e da nessuna chat. I file sono tuoi e restano tuoi; sono però
archivio, non più memoria viva del prodotto.

**Quello che ti sembrava di avere, però, non l'avevi.** Chi configurava Mayan
credeva di alimentare la chat: non la alimentava. La chat 2.0 costruisce il suo
contesto dal *nucleo* — l'anagrafe della casa, cosa è notevole adesso, cosa la
casa fa da sola, e ciò che le hai detto tu — e quell'archivio non lo apriva mai.
Nessuna pagina lo mostrava. E se avevi configurato un provider di embedding,
HIRIS spendeva ogni notte chiamate a quel servizio per riempire un cassetto che
nessuno riapriva.

### Una promessa che ritiriamo perché non era vera

L'opzione `mayan.sensitivity` diceva, testualmente, che il valore `sensitive`
**«nasconde il contenuto all'AI cloud»**. **Non era vero.**

Va detto con precisione cosa significa e cosa non significa, perché sono tre
cose diverse e vanno separate.

**1. Il modello con cui parli non ha mai letto i tuoi documenti.** Non è una
sfumatura: l'archivio in cui finivano non veniva riaperto da nessuna pagina e da
nessuna chat, e nei prompt di sistema non compare. Su questo la rassicurazione
regge intera.

**2. Il testo dei documenti veniva però mandato al servizio che calcola gli
embedding, per indicizzarlo.** Integrale, così come l'OCR lo aveva letto, senza
alcun mascheramento e **senza guardare il valore di `sensitivity`**: la
sensibilità veniva scritta nella riga dell'archivio, non usata per decidere cosa
uscisse. Dove finiva quel testo dipende da una sola opzione,
`memory.embedding_provider`:

- **vuoto** — è il valore **di fabbrica**, e chi non l'ha mai toccato ce l'ha
  ancora: HIRIS non calcolava nessun embedding e **non faceva nessuna chiamata di
  rete**. Il testo non usciva dall'add-on.
- **`model2vec`** — calcolo locale, dentro l'add-on: il testo non usciva di casa.
- **`ollama`** — con l'URL del tuo server impostato, il testo andava a quel
  server, sulla tua rete: non usciva di casa. (Senza URL, come senza chiave nel
  caso qui sotto, HIRIS ricadeva sul comportamento del valore vuoto: niente.)
- **`openai`** — con la chiave API impostata, **il testo dei documenti usciva in
  chiaro verso i server di OpenAI** (`api.openai.com`), esattamente come sarebbe
  uscito con `sensitivity: normal`. Lo stesso vale per i riepiloghi notturni
  delle 04:00 sullo stato della casa.

**Se vuoi sapere se questo ti riguarda, guarda `memory.embedding_provider` nella
Configurazione dell'add-on:** se è vuoto — il default — non ti riguarda. Se hai
scelto `openai`, il testo dei documenti che hai ingerito è passato di là.

**3. La difesa che l'etichetta prometteva non è mai esistita.** Il meccanismo che
avrebbe dovuto sostituire i dati personali con dei segnaposto esisteva nel codice
ma non veniva più invocato da nessuna parte, in nessuno dei due versi: nessun
testo veniva mai mascherato, e quindi non c'era neanche nulla di mascherato che
potesse essere smascherato per errore. `sensitive` e `normal` producevano lo
stesso identico comportamento.

Preferiamo dirlo che nasconderlo. La frase esce insieme all'opzione, e il codice
che la sosteneva a metà esce con lei: quando le difese torneranno, saranno
progettate sui rischi veri di questo prodotto, non ereditate da quello di prima.

### Embedding: le due opzioni restano, ma oggi non fanno niente

`memory.embedding_provider` e `memory.embedding_model` si leggono ancora e la
pagina **Modelli** le mostra, ma **da questa versione nessuna parte di HIRIS
calcola più embedding**: gli ultimi tre pezzi che li usavano escono tutti qui.
Le etichette nella configurazione lo dicono adesso a chiare lettere invece di
lasciartelo scoprire. Restano perché la ricerca per somiglianza è una decisione
**rimandata, non annullata**; quando verrà accesa, si configurerà da lì.

Esce invece `memory.rag_k`: era il numero di risultati di quella ricerca, e la
ricerca non c'è più.

---

## [2.0.1] — La CLI dentro l'immagine adesso ha un numero (2026-08-12)

**Due installazioni della stessa versione di HIRIS contengono adesso lo stesso
programma.** Prima non era garantito. L'immagine chiedeva «l'ultima 2.x» della
CLI di Claude — il programma che alimenta la chat quando usi l'abbonamento — e
quale fosse dipendeva dal giorno in cui l'immagine veniva costruita. Due
persone che installavano la stessa 2.0.0 a una settimana di distanza potevano
ritrovarsi con due programmi diversi sotto il cofano: se una delle due vedeva
un comportamento strano e l'altra no, non c'era modo di dire se la differenza
stesse lì.

Adesso la versione è scritta per intero: **2.1.228**. Cambia soltanto quando
qualcuno la cambia a mano, e allora esce con una versione nuova di HIRIS e con
una riga qui dentro che lo dice.

**Cosa cambia per te nell'uso di tutti i giorni: niente.** Cambia però da dove
arrivano gli aggiornamenti di quel programma: non più in silenzio a ogni
reinstallazione, ma dichiarati, insieme a un aggiornamento di HIRIS. E se ti
serve sapere quale CLI sta girando davvero — non quale dovrebbe — è scritta nel
log dell'add-on, nella riga `init del ponte`, subito dopo `cli=`.

**Il commento nel file di costruzione dell'immagine diceva una cosa falsa**:
che vincolare la CLI alla sola versione maggiore rendesse le build
riproducibili. Non le rendeva riproducibili — è esattamente il difetto che
questo rilascio chiude. Adesso quel commento dice cosa il vincolo fa davvero,
cosa costa tenerlo e come si aggiorna.


## [2.0.0] — HIRIS conosce e non agisce (2026-08-11)

**HIRIS conosce la tua casa, e c'è una chat per interrogarla.** È questa la
versione: non un assistente che promette di fare, ma uno che *sa* — e che dice
anche cosa non sa. Sotto, in due metà: prima ciò che HIRIS oggi sa e prima non
sapeva, poi ciò che non fa più.

### Quello che HIRIS adesso sa

**Conosce la casa come l'hai dichiarata tu.** All'avvio, e ogni volta che Home
Assistant segnala un cambiamento, HIRIS rilegge i registri della tua casa:
piani, aree, dispositivi, entità, etichette, categorie, integrazioni. Prima ne
conosceva un livello solo — un elenco piatto di entità con accanto il nome
dell'area; adesso sa che il termostato appartiene a un dispositivo, che quel
dispositivo sta in una stanza e che quella stanza sta su un piano. Il
significato non lo indovina e non lo compra da un modello: è quello che tu hai
già scritto in Home Assistant — i nomi, gli alias, le etichette, le categorie.

**Se un registro non risponde, non lo scambia per una casa vuota.** Un piano
che non c'è e un registro dei piani caduto producono la stessa lista vuota:
HIRIS le tiene distinte, conserva la casa di ieri invece di sostituirla con
dieci liste vuote, e scrive quali registri non hanno risposto.

**Sa anche cosa la casa fa già da sola.** Legge il corpo delle automazioni e
degli script direttamente dai file di configurazione di Home Assistant, e si
accorge che sono cambiati guardando la data di modifica dei file — l'unico
segnale che esista per gli script, per i quali Home Assistant non emette alcun
evento. Delle automazioni scritte a mano fuori da quei file conosce il nome ma
non il corpo: **lo sa e lo dice**, invece di credere che non esistano.

**Il nucleo: la stessa casa, sempre davanti.** Ogni turno di chat comincia da
un testo solo, ricomposto ogni volta: *La casa* (piani, aree, cosa c'è in
ciascuna), *Notevole adesso* (cosa è acceso, aperto, in allarme in questo
momento), *Ciò che la casa fa già da sola*, *Ciò che le persone hanno detto*.
Prima la stessa casa esisteva in cinque rappresentazioni diverse e nessuno le
vedeva tutte: la chat ne riceveva una, il resto del sistema un'altra. Adesso è
una sola. Il testo esatto che il modello riceve si può leggere anche da fuori,
sull'API dell'add-on: quello che vedi tu è quello che vede lui.

**E dichiara ciò che ignora.** Il nucleo ha una sezione sua — *Ciò che HIRIS
ignora* — dove finisce quello che non ha potuto leggere. Con Home Assistant
irraggiungibile non scrive «niente di notevole»: scrive che lo stato non è
stato letto, e che **non è la stessa cosa**. Se il nucleo supera la propria
dimensione massima, dice dentro sé stesso quanti elementi ha lasciato fuori,
invece di troncare in silenzio.

**Quattro strumenti in chat, e nessuno tocca la casa.** `cerca` (trova un'area,
un'entità o un dispositivo a partire da come lo chiami tu, e quando un nome è
ambiguo lo dichiara invece di scegliere il primo), `guarda` (il dettaglio di
una cosa sola — un'area, un'entità col suo **stato di adesso**, un'automazione
col suo corpo, un ricordo), `ricorda`, `richiama`. Sono quattro al posto dei
trentaquattro di prima, e **leggono soltanto**. Se HIRIS non riesce a guardare
lo stato vivo non restituisce un vuoto: marca il risultato come non letto.

**E adesso ricorda davvero.** Dirgli «d'inverno il soggiorno sta bene a 19.5»
lo fa salvare sul serio, e quel ricordo **ricompare nel nucleo del turno
successivo**, sotto *Ciò che le persone hanno detto*, con il nome di chi l'ha
detto. È la riparazione del difetto fondativo di HIRIS: la versione precedente
rispondeva «preso nota» e non salvava niente (vedi la voce `[1.1.0-beta.18]`
qui sotto), perché nessuno chiamava mai l'archivio.

**Il ricordo può essere agganciato alla casa.** Oltre alla frase — che si salva
sempre per intero, non riassunta — HIRIS può registrare a quale area o entità
si riferisce, che forza ha (preferenza, divieto, fatto, regola), un valore o un
intervallo e quando vale. Se aggancia il ricordo a qualcosa che nella tua casa
non esiste, **quell'aggancio non viene scritto** — ma la frase sì, per intero, e
lo scarto viene dichiarato: mai un ricordo mezzo inventato spacciato per buono.

**La prima pagina della configurazione adesso mostra cosa HIRIS sa.** Si
chiama *Cosa HIRIS sa* e ha preso il posto della vecchia Dashboard: quanti
piani, aree, dispositivi ed entità ha letto della tua casa, cosa la casa fa già
da sola (automazioni e script), quali plance ha visto, e — per intero, parola
per parola — **il testo del nucleo che il modello riceve a ogni turno**. Quello
che leggi tu è quello che legge lui.

**E quando non ha letto, lo dice.** Se un registro della casa non ha risposto,
o se HIRIS non ha ancora fatto la prima lettura, quella tessera non mostra uno
zero e non dice «tutto a posto»: dice **che non ha guardato**. Un numero mai
misurato e un numero misurato a zero non sono la stessa cosa, e ora sullo
schermo non si somigliano più.

**La Memoria si guarda e si corregge.** Configurazione → *Memoria*
(`#/memoria`) elenca tutto ciò che HIRIS ha imparato da te: la frase per
intero, chi l'ha detta, quando, a cosa è agganciata. Ogni voce si può
**correggere** o **cancellare**, con una conferma che ti rimette davanti la
frase esatta prima di toglierla. È la pagina promessa nella versione
`[1.1.0-beta.18]` («arriva nella prossima versione»): eccola. Gli agganci alla
casa e le condizioni si vedono ma non si modificano da qui.

### Quello che si tocca con le dita

**La chat non manda più messaggi che non hai scritto.** Premere **Maiusc+Invio**
per andare a capo faceva partire il messaggio; incollare due righe prese dal log
di Home Assistant lo faceva partire **e** saldava le due righe senza spazio
(«riga uno» e «riga due» diventavano «riga unoriga due»). Era l'unico gesto di
composizione che esiste in una chat, e faceva l'opposto di se stesso — su un
messaggio che non si può annullare e che consuma un turno del tetto di
sessione. Adesso Maiusc+Invio va a capo, l'incolla resta nel campo, e il
messaggio parte quando lo chiedi tu. Continua a funzionare il caso per cui
quella scorciatoia era nata: le tastiere dei telefoni che, invece di premere
Invio, infilano un a capo nel testo.

**Il bottone in alto a destra adesso dice cosa fa.** Si chiamava «Nuova conv.» e
non apriva niente di nuovo: cancellava. Adesso si chiama **Cancella la chat**, ha
l'icona di un cestino, e la conferma ti dice **quanto** stai per perdere — i
messaggi che vedi **e** i riassunti delle conversazioni passate, che HIRIS si
tiene da parte e usa nei turni successivi. È sempre stato così: non era mai
stato scritto. In più il bottone è **spento mentre HIRIS elabora**: premuto in
quel momento svuotava la conversazione, e la risposta in arrivo — già pagata in
token — finiva in un punto che nessuno vedeva. Spariva, e nessuno lo diceva.

**Mentre HIRIS elabora si vede una cosa sola.** Ce n'erano due, e quale vedessi
dipendeva da come il server aveva smaltito la domanda: una differenza che non
scegli, non capisci e non ti serve. Adesso è sempre il logo che pulsa con la
scritta che scorre nei colori del marchio. Il **cronometro non parte subito**:
compare dopo dieci secondi, così una risposta da tre secondi non viene
cronometrata. A trenta secondi l'attesa ammette di essere lunga. **A due minuti
ti dice se puoi chiudere la pagina** — e lo dice guardando che fine fa davvero la
tua domanda: se è stata affidata all'abbonamento la risposta arriva comunque in
cronologia e la ritrovi riaprendo; se sta rispondendo un provider a consumo,
chiudere la perde. Sono due frasi diverse perché sono due fatti diversi. E dove
HIRIS ha un tempo massimo lo annuncia prima di arrendersi; dove non ce l'ha, **lo
dice invece di promettere una fine che non arriverebbe**.

**Chi usa uno screen reader adesso viene avvisato.** Prima si mandava il
messaggio e non si sentiva più niente: nessun annuncio della presa in carico,
nessun annuncio della risposta, silenzio per minuti. Adesso la riga dell'attesa
è una regione annunciata, ed è la stessa in cui viene scritta la risposta:
arrivano tutte e due. Il cronometro invece resta muto di proposito — un
contatore dentro una regione annunciata verrebbe letto ogni secondo.

**Su tablet la pagina non salta più sotto il dito.** A ogni invio il campo di
scrittura si spegneva, quindi perdeva il fuoco, quindi la tastiera si chiudeva e
la pagina si allungava di colpo; alla risposta tutto risaliva. Adesso il campo
resta dov'è, in sola lettura, e **dice perché** non si può scrivere invece di
restare muto e inerte. Nella stessa fascia di larghezze l'intestazione della
chat non si spezza più in due righe, e le due schermate — chat e configurazione
— cambiano forma alla stessa larghezza invece che a due diverse.

**Adesso «non l'ho letto» si legge.** La frase con cui HIRIS dichiara di non
sapere una cosa era servita, sul tema chiaro, dal colore meno leggibile
dell'intera tavolozza: arancione pallido su bianco, sotto ogni soglia di
accessibilità. Cioè la frase per cui questo prodotto esiste era quella che si
faceva più fatica a leggere. Adesso è leggibile, e con lei gli errori, i badge
di stato, i sottotitoli, gli orari, i numeri di sezione e la scritta d'attesa —
in tutti e due i temi, non solo nel chiaro. Sotto i 1024 px — la larghezza che
l'add-on ha su un portatile con la barra di Home Assistant aperta — la colonna
del menu della configurazione non taglia più la propria intestazione a metà, e
le sue icone hanno un nome: prima erano sei disegni identici per dimensione,
senza etichetta, senza suggerimento al passaggio del mouse e senza nome per uno
screen reader.

**Dettagli che si notano solo se ci lavori dentro.** Le azioni di recupero
(«Riprova», «Correggi») hanno di nuovo l'aspetto di comandi invece che di
etichette, e «Dimentica» non è più l'elemento più pesante della riga: la cosa
distruttiva non deve essere la più invitante. Un bottone appeso al corpo di una
sezione non si stira più per tutta la larghezza facendosi scambiare per un campo
di testo. E lo stesso numero è scritto allo stesso modo nelle due schermate: il
riquadro «Utilizzo» della chat diceva `1.28M` e `€3.2149` dove la pagina
*Consumi* diceva `1.3M` e `€ 3.21` — sugli stessi identici dati, il che dava
ragione a chi sospettava che uno dei due stesse sbagliando. E le date si
scrivono dappertutto come nel resto del prodotto, `01/08/2026`, non come un ISO
tagliato a metà.

**La descrizione dell'opzione «Chat via abbonamento» negava una cosa che HIRIS
sa fare.** Diceva che su quel percorso la chat riceve la conoscenza della casa
«ma NON i suoi strumenti». Era vero fino a poco fa; poi gli strumenti sono stati
riattaccati anche a quel percorso, e il testo è rimasto indietro — nel pannello
di configurazione dell'add-on, in italiano e in inglese, e nel README. È lo
stesso difetto che questa versione ha passato la settimana a chiudere, girato al
contrario: di solito il testo promette ciò che il codice non fa, qui negava ciò
che il codice fa. Chi leggeva non avrebbe mai provato a chiedere alla chat in
abbonamento di cercare qualcosa. Adesso il testo dice come stanno le cose, in
tutti e due i casi: quando il collegamento riesce il modello ha i quattro
strumenti e guarda lo stato di adesso; quando non riesce risponde lo stesso con
ciò che sa, e **te lo dice in cima alla risposta** invece di far finta di aver
guardato. Le targhette sotto la risposta ti mostrano quali strumenti ha usato
davvero.

### Quello che HIRIS non fa più

**HIRIS non tocca più niente in casa tua.** Non accende, non spegne, non crea
automazioni né plance, non modifica scene, non chiede conferme — perché non c'è
più nessuna azione da confermare. Non è un guasto: è la scelta che dà il nome a
questa versione. HIRIS aveva trentaquattro strumenti per agire sulla casa e un
impianto di conferme perché non lo facesse di nascosto, e la promessa che non ha
mai mantenuto era proprio quella — diceva «fatto» quando non aveva fatto niente.
Meglio un assistente che sa e te lo dice, che uno che dice di aver fatto.

Ciò che è uscito **non c'è più nel prodotto**, e non è nascosto dietro
un'impostazione da riaccendere: è assenza di codice. La storia di Git lo
conserva per intero.

**E non ti parla più, se non gli parli tu.** Sono spariti il resoconto delle
08:00, i solleciti, la scansione di salute notturna, la sorveglianza continua
della casa, il saluto all'arrivo la sera, i suggerimenti che comparivano da soli
e le proposte da approvare. Da questa versione HIRIS ha **una bocca sola** — la
chat — e la apre solo se sei tu a cominciare. Se ti eri abituato a quelle voci,
il silenzio che senti non è un malfunzionamento: non c'è più niente che parli.

**Anche le notifiche sono uscite.** Nessun messaggio su Home Assistant, nessun
canale esterno. L'impostazione che li configurava non c'è più: se l'avevi
riempita, la trovi svanita dalla pagina di configurazione dell'add-on.

**I sensori di HIRIS in Home Assistant restano «non disponibile».** HIRIS
pubblicava via MQTT sette sensori per ogni assistente (consumi, budget, stato).
Non li pubblica più, ma Home Assistant conserva le entità già scoperte: le
vedrai `unavailable` per sempre finché non le togli tu, da *Impostazioni →
Dispositivi e servizi → MQTT*. È l'unica cosa di questo aggiornamento che
richiede un tuo gesto.

**La cronologia della chat riparte da zero.** Al primo avvio dopo
l'aggiornamento le conversazioni precedenti non ci sono più. È una decisione
esplicita, non una perdita accidentale: la conversazione ha cambiato forma sotto
i piedi (non è più legata a un assistente con un nome e un id) e trascinarsi
dietro il vecchio formato avrebbe significato rispondere con metà contesto senza
dirlo. Se HIRIS trova sul disco una cronologia della versione 1.x, lo **scrive
nel log** invece di farla sparire in silenzio. Ciò che gli avevi *detto di
ricordare* non è nella cronologia e **non si perde**.

**C'è un solo assistente, e la chat è quell'assistente.** Niente più selezione
del bot, niente più assistenti con un nome proprio e permessi diversi: si apre
la chat e si parla con HIRIS. Le impostazioni della conversazione (nome,
modello, prompt di sistema, forma della risposta, budget di ragionamento,
tetto di turni, restrizione alla casa) si cambiano dalla pagina
*Configurazione → Impostazioni chat* (`#/impostazioni`, GET/PUT
`api/impostazioni-chat`).

**Sono uscite sei pagine della configurazione.** *Chatbot* (lista ed
editor), *Agentbot*, *Nuovo* (la procedura guidata di creazione), *Task*,
*Proposte* e *Accessi Gateway* non esistono più, e con loro i pannelli Task,
Proposte e Conoscenza dentro la chat e le voci di menu che ci portavano.
Erano le pagine di un prodotto che agiva sulla casa: senza le azioni, le
approvazioni e gli assistenti multipli, non governavano più niente — e da mesi
si limitavano a mostrare liste vuote senza dire che erano vuote perché il
motore sotto non c'era più. Quello che resta è quello che funziona: *Cosa HIRIS
sa*, *Memoria*, *Modelli*, *Consumi*, *Storicizzazione*, *Impostazioni chat*.

**La schermata «Benvenuto in HIRIS» al primo avvio non c'è più.** Chiedeva di
creare un secondo assistente in un prodotto che ne ha uno solo: su
un'installazione nuova non trovava mai niente da offrire, e il pulsante «Crea»
falliva sempre con un errore — era la primissima cosa che un'installazione
nuova mostrava, ed era rotta. Ora si apre direttamente sulla chat, già pronta,
con l'assistente predefinito attivo. Il dare un nome e delle istruzioni proprie
a quell'assistente ha ora una pagina sua (*Configurazione → Impostazioni
chat*). Se il tuo browser aveva già visto la schermata, resta nel
suo `localStorage` una chiave inerte (`hiris_onboarding_v1`) che non serve più
a nulla: non viene ripulita, perché non c'è più codice che la legga.

**La card di HIRIS nelle tue dashboard non c'è più.** Se avevi messo la chat
di HIRIS dentro una dashboard di Home Assistant (la tessera
`custom:hiris-chat-card`), quella tessera **smette di funzionare**: la card è
uscita dal prodotto. Non è un guasto ed è una decisione, presa per una ragione
sola: la card verrà **rifatta da zero** come ultimo passo, quando il resto di
HIRIS sarà finito, invece di essere rattoppata a ogni cambiamento nel
frattempo. Fino ad allora si parla con HIRIS in un posto solo: aprendo
l'add-on. La tessera vuota rimasta nella dashboard va tolta da te — è l'unico
gesto che ti resta.

Di suo, HIRIS **disinstalla ciò che aveva installato**: al primo avvio dopo
l'aggiornamento toglie da Home Assistant la copia della card
(`<configurazione>/www/hiris/`) e la risorsa Lovelace che aveva registrato, e
scrive nel log che l'ha fatto. Toglie **soltanto** quelle: qualunque altra
risorsa nella tua dashboard — di un altro add-on, o messa da te — non viene
toccata, e se in quella cartella avevi file tuoi restano dove sono. Se Home
Assistant non risponde in quel momento, HIRIS non insiste e non fallisce
l'avvio: scrive nel log **quale** risorsa è rimasta e dove toglierla a mano
(*Impostazioni → Dashboard → Risorse*). Senza questa pulizia ti resterebbe in
dashboard una risorsa che punta a un file che non esiste più — un errore che
avresti scoperto tu.

Una traccia resta, ed è nel tuo browser: la card teneva la propria cronologia
in `localStorage` (chiavi `hiris.chat.<slug>.<id>`), separata da quella che il
server già salva. Quelle chiavi restano dove sono e diventano inerti — non c'è
più codice che le legga, e nessuna conversazione va persa: la cronologia della
chat dell'add-on è quella del server, e non è mai stata la stessa.

**Gli assistenti in più che avevi creato non vengono più caricati.** Il file che
li conteneva **resta intatto sul disco** — non è stato cancellato — e HIRIS ne
dichiara la presenza nel log all'avvio. Attenzione a una cosa: un prompt
personalizzato salvato sull'assistente predefinito **non viene trasferito** alla
chat nuova. Se ne avevi uno e ci tieni, riprendilo dal file prima di riscriverlo.

**La documentazione del prodotto vecchio non c'è più.** In `docs/` c'erano
quattordici guide — architettura, come funziona, casi d'uso, configurazione,
sicurezza, MQTT, modalità completamente locale, in italiano e in inglese — che
raccontavano **al presente** un HIRIS che agisce sulla casa: gli Agentbot, il
semaforo delle conferme, le notifiche, i sensori MQTT. Niente di tutto questo
esiste più: chi le apriva leggeva le istruzioni di un prodotto diverso da quello
che aveva installato. Sono state **cancellate**, non aggiornate e non marcate
come storiche — dopo questa pubblicazione le funzionalità principali verranno
**reinventate**, quindi quei testi non sarebbero un riferimento nemmeno per ciò
che arriva dopo, e un avviso in cima a una pagina sbagliata lascia comunque una
pagina sbagliata. La storia di Git le conserva per intero. Quello che resta da
leggere è questo CHANGELOG, il foglio `docs/prova-la-2.0.md` per chi prova
questa build, e i documenti di progetto in `docs/design/`, che portano una data
e si presentano per quello che sono.

### Meno cose, non solo più cose

- **Il «Test Run» non esiste più.** Non ha mai funzionato: ogni esecuzione vera
  falliva, ed era protetto da un controllo automatico che verificava una firma
  diversa da quella reale — cioè non lo provava affatto.
- **La pagina Consumi perde per intero la sezione per assistente.** Non mostra
  una riga a zero: la tabella è stata rimossa, perché HIRIS ha una chat sola e
  non c'è più nessun id per cui contare. Resta il **contatore complessivo** —
  richieste, token, costo — che però è vero **solo se stai usando una chiave
  API a consumo** (Claude, OpenAI, OpenRouter) o Ollama. Se usi
  l'**abbonamento** Claude, quei numeri non esistono: l'abbonamento non espone
  né i token né il costo della singola risposta. In quel caso la pagina te lo
  **dice** — «i consumi non si misurano sul percorso abbonamento» — invece di
  mostrare zeri o un errore. **Non è un consumo azzerato, è un consumo che non
  viene misurato.**
- Il tetto giornaliero dei messaggi di chat instradati sull'abbonamento resta,
  ed è l'unico freno rimasto.
- Dettaglio per chi ha scritto qualcosa sopra le API di HIRIS: l'evento `done`
  del flusso della chat non porta più il campo `agent_id`.

## [1.1.0-beta.18] — Adesso ricorda davvero (2026-08-05)

**Se gli dicevi una cosa, HIRIS non la teneva.** Rispondeva «preso nota» — e non
salvava niente. Non era un guasto: nel testo che lo governa non c'era **nessuna
riga** che gli dicesse quando ricordare. Aveva lo strumento e nessuna istruzione
per usarlo. In quattro mesi ha imparato da te **tre volte**, tutte e tre lo stesso
giorno, e solo perché gliel'avevi chiesto in modo esplicito.

Adesso basta dirglielo normalmente. *«D'inverno il soggiorno sta bene a 19.5»* è
un'affermazione, non un comando, e tanto basta.

**E quelle tre cose che sapeva erano già sparite.** Chi sei, come capire chi c'è
in casa, e che il sensore meteo esterno è guasto: erano state salvate a luglio con
una scadenza automatica di novanta giorni, ed erano già scadute — invisibili, senza
che nulla lo dicesse. **Questa versione le riporta indietro**, e toglie la scadenza:
ciò che HIRIS sa della tua casa non svanisce più perché è passato un trimestre.

**Ora se ne ricorda da solo.** Prima, anche i ricordi salvati riemergevano solo se
HIRIS decideva di andarseli a cercare. Adesso ciò che gli hai detto entra da sé
nelle conversazioni nuove e nei suoi ragionamenti — e resta distinto da ciò che ha
dedotto per conto suo, così duecento medie settimanali non seppelliscono le tre cose
che contano.

**E quello che dici lo sa HIRIS, non il singolo assistente.** Le tre cose di sopra
erano legate al chatbot con cui parlavi: un secondo assistente non avrebbe saputo del
sensore guasto, e avrebbe ricominciato a proporti soluzioni basate su sensori che non
esistono. Ora valgono ovunque, e ognuna porta il nome di chi l'ha detta. Ciò che è
marcato come riservato resta di chi l'ha scritto.

### Meno cose, non solo più cose

- **Un solo modo di ricordare.** C'erano due strumenti che facevano la stessa cosa
  scrivendo nella stessa tabella, con regole diverse e senza motivo: uno salvava
  subito ma legato a un assistente e con scadenza, l'altro chiedeva il permesso ma
  valeva per tutta la casa e non scadeva mai. Adesso è uno.
- **Via la coda di approvazione per i ricordi**: si salva e basta. La pagina che
  mostra ciò che HIRIS sa — con la possibilità di correggere e cancellare — arriva
  nella prossima versione.
- Via anche l'impostazione di conservazione, la pulizia periodica che non serviva più
  e alcune scritte che promettevano comportamenti non più veri.

### Corretto anche

- **Cancellare un assistente non cancella più ciò che sapeva la casa.** Prima
  spariva insieme a lui.
- Un assistente con permessi ristretti poteva salvare un ricordo e non ritrovarlo
  mai più.
- Un fatto lungo più di due righe veniva **tagliato a metà in silenzio** prima di
  arrivare al modello.
- Le scritte che dicevano «dichiarato da una persona di casa» ora dicono la verità:
  «salvato in conversazione».

## [1.1.0-beta.17] — HIRIS ricorda, e si ricorda da solo (2026-08-04)

**Se non hai mai configurato un fornitore di embedding — cioè, quasi certamente,
se non sai cosa sia — fino a ieri HIRIS non ricordava assolutamente nulla.**
Non «ricordava male»: rifiutava di scrivere. Ogni «ricordati che…» finiva contro
un requisito tecnico invisibile, e non lo diceva a nessuno.

Il caso peggiore era il resoconto delle 08:00. Le scadenze si leggono per data —
una semplice interrogazione sul calendario — e infatti il codice che le legge
**butta via** il dato tecnico che pretendeva in scrittura. Risultato: non si
scrivevano mai, e quel resoconto era **vuoto per sempre** su ogni installazione
appena fatta. E nella pagina **Memoria** si vedeva la cosa che HIRIS aveva
imparato, con accanto un pulsante «Approva» che rispondeva con un errore: la
vedevi, e non potevi tenerla.

**Ora ricorda.** Salvi una scadenza parlando in chat, la approvi, e alle 08:00
la ritrovi nel resoconto. Senza configurare niente.

**E soprattutto: si ricorda da solo.** Prima, anche i ricordi salvati riaffioravano
solo se HIRIS decideva di andarseli a cercare. Adesso ciò che gli hai detto in
passato entra da sé nelle conversazioni nuove e nei suoi ragionamenti: gli dici
una volta che preferisci 21 gradi in salotto, e non serve ripeterglielo.

**Con una regola che vale la pena conoscere, perché riguarda la fiducia.** Quando
HIRIS può confrontare i significati lo fa; quando non può, ti dà le cose più
recenti — e **lo dichiara**. Non ti presenterà mai «gli ultimi cinque ricordi»
spacciandoli per «i cinque più pertinenti». Se configuri un fornitore di embedding
la ricerca per significato torna a funzionare esattamente come prima, e le
etichette cambiano di conseguenza.

### Meno cose, non solo più cose

Questa versione **toglie** anche.

- **I collegamenti fra ricordi non esistono più.** HIRIS poteva collegare fra loro
  le cose che sapeva — e nessuna parte del programma leggeva più quei collegamenti.
  Erano lavoro (e spesa) per un archivio che nessuno apriva. Via la funzione, via la
  tabella.
- Insieme se ne vanno due letture che nessuno chiamava, un ramo di codice diventato
  irraggiungibile e alcuni commenti che spiegavano cose non più vere.

### Corretto anche

- **Un guasto dell'archivio non ti costa più l'annullamento.** Quando il Brain
  regola qualcosa da solo, lascia una traccia che ti permette di annullare. Se il
  servizio di embedding era configurato ma irraggiungibile, quella traccia non
  veniva scritta: la modifica restava applicata e **non era più annullabile**, senza
  che nulla lo dicesse.
- **La revisione quotidiana della casa non si interrompe più in silenzio** per un
  errore interno introdotto durante questi lavori.
- **La chat non dimentica più tutto** quando il servizio di embedding è configurato
  ma non risponde: prima, in quel caso, gli altri percorsi ricordavano e solo la
  chat perdeva la memoria.

## [1.1.0-beta.16] — HIRIS guarda la casa, e si accorge di cosa è cambiato (2026-08-04)

**Fino a ieri, quando HIRIS ragionava su qualcosa che era successo in casa, vedeva
una cosa sola: l'entità che si era mossa.** Una porta, una batteria, un consumo —
e nient'altro. Non sapeva quali stanze esistono, cosa c'è acceso altrove, se
quella porta è aperta da dieci minuti o da tre ore. Soprattutto: non ricordava
nulla di mezz'ora prima. Ogni volta ricominciava da capo.

**Ora HIRIS tiene un ritratto della casa e se lo porta dietro quando ragiona.**
Le stanze e cosa contengono, cosa è acceso e cosa è aperto in questo momento, e —
la parte che conta di più — **cosa è cambiato dall'ultima volta che ha guardato**.
Una casa che gli dice «sono queste sette cose a essere diverse da stamattina» è
una casa su cui può accorgersi di qualcosa, non solo rispondere.

**I rilevatori che scattano hanno una sezione tutta loro, ed è la prima.** Fumo,
gas, allagamento, guasto, manomissione: non finiscono più mescolati alle finestre
aperte. Un rilevatore che è scattato è la cosa più importante che una casa possa
dire, e adesso viene detta per prima.

Il ritratto si aggiorna da solo ogni quindici minuti e non chiama mai Home
Assistant per essere letto, quindi non aggiunge attesa a niente. Registra solo
stati che cambiano di rado — porte, luci, serrature, allarmi — e volutamente **non**
temperature, consumi, umidità: sono numeri che si muovono in continuazione, e
metterli lì dentro vorrebbe dire dire «è cambiato tutto» ogni volta, cioè niente.

### E prima di tutto questo: HIRIS ha smesso di dire cose che non erano vere

Un giro di correzioni su una sola cosa — **la distanza fra quello che HIRIS
dichiarava e quello che faceva davvero.**

- **Una serratura poteva essere aperta da una notifica.** Un dominio pericoloso
  classificato «giallo» produceva una notifica con il pulsante di approvazione, e
  quel tocco eseguiva l'azione **saltando il controllo di sicurezza** — a telefono
  bloccato, senza autenticazione. Ora i domini pericolosi sono forzati al livello
  che richiede sempre un codice.
- **Salvataggi, strumenti e guasti restavano muti.** Cose che non erano andate a
  buon fine venivano riferite come riuscite, o non venivano riferite affatto.
- **Reti di sicurezza promesse e inesistenti.** Alcuni messaggi dichiaravano
  protezioni che nessuna riga di codice applicava, sulla conferma e sul gateway.
- **Un identificativo sbagliato scavalcava il controllo** che invece scattava
  quando l'identificativo mancava del tutto.
- **L'inventario delle entità non si ricaricava** dopo un avvio fallito, e schede
  gemelle raccontavano la stessa cosa in modi diversi.
- **Il chip «eseguiti» contava zero** perché due punti del codice usavano
  vocabolari diversi per le stesse etichette di stato.

## [1.1.0-beta.15] — La memoria funziona davvero, e le notifiche si aprono (2026-08-02)

**Quando chiedevi a HIRIS di ricordare qualcosa, non lo ricordava.** «Ricordati
che la caldaia va revisionata a ottobre» → «salvato» → e quel dato non sarebbe
mai tornato indietro. Non era un errore occasionale: ciò che HIRIS impara nasce
in attesa di approvazione, la ricerca legge solo ciò che è approvato, e il modo
di approvare **non esisteva**. Nessun errore, nessun avviso: solo un ricordo che
non torna.

Ora nella chat, accanto a **Proposte** e **Task**, c'è la voce **Memoria** con il
numero di elementi in attesa: vedi cosa HIRIS ha imparato — il contenuto, quando,
da quale conversazione — e decidi se tenerlo o scartarlo. Approvato significa
richiamabile da quel momento in poi. Ciò che è marcato come **sensibile** resta
coperto finché non sei tu a chiedere di vederlo.

**Se hai usato «ricordati che…» in passato, quei dati sono ancora lì.** Non sono
andati persi: erano solo in attesa di un'approvazione che non potevi dare. Apri
la Memoria e li trovi ad aspettarti. Alcuni di quei ricordi erano stati salvati
senza l'indice che serve a ritrovarli: approvarli ora lo calcola, così
«approvato» significa davvero «richiamabile». Se in quel momento l'indice non si
può calcolare, l'approvazione **te lo dice e non avviene**, invece di lasciarti
un elemento approvato e muto: riprova quando il servizio è di nuovo disponibile.

Un caso restava scoperto anche con la coda: se HIRIS non ha un modo per indicizzare
il testo (nessun servizio di embedding configurato, o momentaneamente fuori uso),
salvare produceva comunque un elemento non richiamabile. Ora in quel caso il
salvataggio **fallisce e te lo dice**, invece di riuscire a vuoto.

**Le notifiche si aprono.** Su iPhone, toccare una notifica di HIRIS non apriva
HIRIS: compariva il selettore di sistema che propone di salvare il sito, e dietro
una pagina vuota. Ora il tocco apre HIRIS **dentro l'app di Home Assistant**,
senza passare dal browser e senza dipendere da come hai esposto Home Assistant
all'esterno. Vale anche per il pulsante **«Apri HIRIS»** delle richieste di
conferma — quello con cui si approva un'azione a rischio — che era rotto allo
stesso modo: la notifica che conta di più era proprio quella che non si apriva.

**Le proposte della Sentinella dicono il vero.** Quando la sorveglianza rileva
qualcosa e propone un rimedio, approvando si ottiene uno **script pronto
all'uso**, da lanciare quando vuoi. La descrizione però raccontava il rimedio
come se venisse eseguito subito. Ora dice cosa ottieni davvero approvando,
mantenendo la descrizione di ciò che è stato rilevato. E se la proposta non
riesce a essere salvata, ricevi comunque la notifica del problema invece di
restare senza l'una e senza l'altra.

**Una sola verità su cosa non funziona in casa.** «Entità non disponibile» veniva
calcolata in due modi diversi, e le due letture potevano contraddirsi: un
dispositivo già spento **prima** che HIRIS partisse poteva non comparire fra le
entità non disponibili, e uno tornato a funzionare mentre HIRIS era fermo poteva
restare segnalato per sempre. Ora il conteggio è uno solo, riletto dagli stati
reali di Home Assistant, e «da quanto tempo» è il tempo vero del dispositivo, non
quello da cui HIRIS se n'è accorto.

**I modelli preconfigurati** dei Chatbot (Energia, Sicurezza, Presenza, Clima,
Irrigazione) istruivano il modello a usare uno strumento che non esiste più: ogni
bot creato da un modello sprecava un tentativo a vuoto. Ora citano solo strumenti
reali, e reali su **entrambi** i modi di chattare — con la tua chiave e con
l'abbonamento — che non hanno gli stessi strumenti a disposizione. Dove uno
strumento esiste solo da una parte (le previsioni meteo), il testo dice cosa fare
quando non c'è.

Sotto il cofano, infine, la **Sentinella non si interrompe più** su una risposta
del modello di forma inattesa: ricade sul comportamento prudente previsto invece
di fermare il giro di sorveglianza, e nemmeno quando il modello scrive come testo
il numero di minuti dopo cui rispegnere un dispositivo — prima quel dettaglio
costava la proposta e la notifica insieme.

## [1.1.0-beta.14] — Le letture dal gateway remoto hanno un perimetro (2026-08-01)

Quando colleghi Claude a HIRIS tramite il gateway MCP, le **azioni** erano già
vincolate dal semaforo: Claude può comandare solo ciò che hai marcato verde. Le
**letture** no. Chiedere lo stato o lo storico di casa non è distruttivo, quindi
partivano senza alcun perimetro — e questo significava che ogni lettura vedeva
tutta la casa, serrature e allarme compresi. Non era una novità introdotta di
recente: era la condizione in cui il gateway ha sempre funzionato.

Ora c'è una **denylist di lettura**: un elenco di entità o domini che non escono
mai dal gateway. Di serie copre le cose che è ragionevole tenersi in casa —
**serrature, pannello d'allarme, telecamere e presenza** (`person`,
`device_tracker`, che rivelano quando la casa è vuota). Non è l'elenco dei domini
pericolosi del semaforo, che riguarda l'azione: una tapparella è rischiosa da
muovere ma innocua da leggere, una telecamera è l'opposto.

Il perimetro vale per **tutte** le letture, non solo per quelle nuove. Non basta
infatti controllare che cosa viene chiesto: parecchie letture non nominano
affatto un'entità (lo stato dell'intera casa, la cronologia degli eventi, le
segnalazioni di salute, l'elenco per stanza), quindi sarebbe bastato **omettere
un parametro** per aggirare il controllo. HIRIS filtra perciò anche le
**risposte**, dichiarando quando ha tolto qualcosa, così il modello sa che sta
vedendo una parte e può dirtelo. Lo stesso filtro copre l'elenco dei **task
pianificati**, che altrimenti avrebbe mostrato al gateway un promemoria come
«arma l'allarme alle 23» con l'entità e l'orario.

**Cambiamento di comportamento se già usi il gateway.** Se una lettura che prima
funzionava ora non restituisce certe entità, o se una richiesta che le nomina
viene rifiutata con un messaggio esplicito, è voluto. L'elenco è configurabile
dall'opzione **`execute_api_read_denylist`** nella configurazione dell'add-on:
puoi restringerlo, allargarlo, o **svuotarlo** del tutto per tornare al
comportamento precedente. Nulla di tutto questo tocca la chat dentro l'add-on,
che ha il suo perimetro e resta com'era.

Chiuso il perimetro, la **cronologia degli eventi** (`get_logbook`) torna
disponibile anche dal gateway: era rimasta fuori proprio perché avrebbe reso
enumerabile in blocco tutto ciò che è successo in casa, e ora non può più.

**Limite dichiarato.** La denylist filtra per entità. La **memoria testuale** di
HIRIS contiene testo libero, non identificativi: se un appunto salvato a mano
contiene un dato sensibile, nessuna denylist per entità può intercettarlo. Quel
caso non è coperto, e non vogliamo dare l'impressione che lo sia.

## [1.1.0-beta.13] — HIRIS vede lo stato di casa e del sistema, e te lo dice (2026-08-01)

Finora HIRIS teneva d'occhio la salute della casa, ma il risultato viveva solo
nella dashboard della configurazione: chiedere in chat «ci sono problemi?» non
serviva a niente. Ora le **segnalazioni del Brain** — batterie scariche, entità
non disponibili da giorni, automazioni rotte, domini pericolosi lasciati aperti,
entità senza area — sono leggibili nella conversazione, con gravità, evidenza e
rimedio suggerito.

HIRIS vede anche lo **stato del sistema**: add-on fermi o in errore, spazio
libero sul disco, salute delle singole integrazioni e **aggiornamenti
disponibili** per core, sistema operativo, Supervisor e add-on. Su
un'installazione senza Supervisor la parte relativa semplicemente non compare,
senza errori.

Sa inoltre raccontare **cosa è successo** — «cosa è successo ieri sera in
salotto?», «chi ha acceso il riscaldamento?» — leggendo il registro eventi di
Home Assistant, e sa **valutare una condizione al volo** con un template, utile
quando serve verificare qualcosa che gli altri strumenti non espongono.

**Tutto questo è in sola lettura, per scelta e non in attesa di un seguito.**
HIRIS vede che ci sono aggiornamenti e te li segnala, ma non li applica: non può
aggiornare, avviare, fermare o riavviare nulla, né direttamente né proponendotelo
per approvazione. Aggiornare il sistema resta una cosa che fai tu, dove la fai
oggi.

**Notifica per i problemi gravi.** Quando la scansione di salute — che gira ogni
30 minuti — rileva un problema **grave**, arriva una notifica push. Una sola:
finché quel problema resta lì, non torna a suonare. Torna a suonare solo se il
problema si era chiuso e si ripresenta, o se una segnalazione già aperta
**peggiora** fino a diventare grave (l'add-on che avevi spento e che poi si
guasta davvero). C'è un periodo di silenzio di 12 ore per assorbire i valori che
oscillano attorno a una soglia, e se un guasto solo apre molte segnalazioni in
un colpo arriva un unico messaggio di riepilogo invece di una raffica. Si
disattiva dall'opzione **"Salute del sistema — notifica i problemi gravi"**
(`brain_notify_high`) nella configurazione dell'add-on; le segnalazioni restano
comunque visibili.

**Azione richiesta se hai Chatbot con permessi personalizzati.** L'elenco degli
strumenti mostrato nella configurazione dei Chatbot era rimasto indietro rispetto
agli strumenti realmente disponibili: ne mostrava uno che non esiste più e ne
ometteva parecchi reali. Ora è allineato. I Chatbot **già salvati con una lista
esplicita di strumenti** però non ereditano le voci nuove: la loro lista è quella
che hai scelto tu, e resta tale. Se hai Chatbot di questo tipo, **riaprili e
risalvali** dalla pagina di configurazione, così raccolgono anche gli strumenti
nuovi. Vale in particolare per lo strumento di conferma delle azioni a rischio
(`confirm_pending`): su un Chatbot con **conferma richiesta** attiva e una lista
esplicita che non lo comprende, digitare il codice OTP non completa l'azione,
perché il modello non ha lo strumento per confermarla. Fallisce dalla parte
sicura — l'azione resta bloccata e non viene eseguita — ma è comunque un
malfunzionamento visibile. I Chatbot senza lista esplicita (tutti gli strumenti)
non sono interessati.

**Batterie: la soglia ora è unica al 15%.** Il resoconto giornaliero calcolava le
batterie scariche per conto suo, con una soglia configurabile che valeva **20%**
per impostazione predefinita, mentre la dashboard di salute usava **15%**: la
stessa casa, due risposte diverse a seconda di dove guardavi. Ora c'è una sola
fonte e una sola soglia, **15%**, uguale in chat, nella dashboard e nel resoconto.
Conseguenza pratica: le batterie fra il 15% e il 20% non compaiono più nel
resoconto giornaliero — non sono sparite, semplicemente non erano ancora da
sostituire secondo il criterio che HIRIS usa ovunque. Le batterie riflettono
l'ultima scansione del Brain, quindi con un ritardo massimo di 30 minuti.

## [1.1.0-beta.12] — Il ripristino di una plancia non dipende più dalla pagina aperta (2026-08-01)

Il pulsante per tornare indietro dopo una sostituzione di plancia viveva nella
memoria della pagina chat: se approvavi la proposta da un'altra schermata non
compariva mai, e bastava un aggiornamento del browser per perderlo. Lo snapshot
restava al sicuro sul disco, ma non avevi più un modo per raggiungerlo.

Ora l'elenco delle versioni ripristinabili arriva dal server, quindi vale
ovunque tu abbia approvato e sopravvive a qualsiasi ricaricamento. Le
sostituzioni delle **ultime 24 ore** restano in evidenza come un annullamento
immediato; quelle più vecchie compaiono in un elenco discreto con la data, da
cui puoi comunque ripristinare. Una versione ripristinata sparisce dall'elenco:
è tornata a essere la configurazione attuale della plancia.

## [1.1.0-beta.11] — Le plance si creano e si modificano per proposta (2026-08-01)

HIRIS puo' ora **creare una nuova plancia** (dashboard Lovelace) e **modificare
quelle esistenti**, ma non le scrive piu' di sua iniziativa: propone, e tu
approvi dalla sezione Proposte — esattamente come per le automazioni. Prima le
dashboard erano l'unico caso in cui la chat scriveva su Home Assistant senza
passare da una revisione.

Nuovi strumenti: `list_dashboards` ed `get_dashboard_config` per leggere le
plance esistenti, `propose_dashboard` per proporre una creazione o una
sostituzione. Le proposte di sostituzione lo dicono a chiare lettere, e prima
di sovrascrivere HIRIS salva uno **snapshot** della configurazione precedente:
se il risultato non convince, "Annulla" la ripristina con un click (ultimi 3
snapshot per plancia).

Rimossi gli strumenti di scrittura diretta delle dashboard
(`add_dashboard_view`, e il tipo `dashboard` da `create_ha_config`); script e
scene restano invariati.

## [1.1.0-beta.10] — Proposte nella chat + fix "Errore di rete" dalla Dashboard (2026-07-31)

**Bug.** Attivare una proposta dalla **Dashboard** dava "Errore di rete", mentre
dalla pagina Proposte funzionava. In realtà l'automazione **veniva attivata**:
la Dashboard riusava `applyProposal()` di `proposals.js`, cablato sul DOM della
pagina Proposte (`#pr-<id>`, `#proposals-list`). Dopo l'apply riuscito, sul DOM
della dashboard quegli elementi non esistono → `checkEmptyList()` cadeva su
`null.querySelector` → un falso `alert('Errore di rete')`. Risolto alla radice
con un **core condiviso solo-fetch** (`proposals-core.js`): ogni vista aggiorna
il proprio DOM, nessuna eredita quello di un'altra. Il peek della Dashboard ora
usa il core e si ricarica; aggiunta anche una guardia difensiva su
`checkEmptyList()`.

**Feature.** Le **Proposte** sono ora accessibili dalla **pagina chat**, con una
**voce di navigazione dedicata** accanto a "Task pianificati" (con badge del
numero in attesa) e un pannello Attiva/Rifiuta. Le proposte sono un'inbox di
azioni come i Task, e vivono dove operi ogni giorno. La pagina Proposte del
config resta disponibile; tutte le viste (chat, Dashboard, config) passano ora
dallo stesso core, quindi quella classe di bug non può ripresentarsi.

## [1.1.0-beta.9] — Chat: "in elaborazione" col logo HIRIS che pulsa + timer (2026-07-31)

La risposta via abbonamento mostrava il testo statico "HIRIS sta pensando…
(risposta in arrivo)". Ora al suo posto: il **logo HIRIS che pulsa**, la scritta
"HIRIS sta elaborando" che scorre **nei colori del logo**, e sotto un **timer che
conta i secondi** — così si vede a colpo d'occhio che sta lavorando e non è
bloccato. Alla risposta il timer si ferma e la bolla mostra il testo. Rispetta
`prefers-reduced-motion`.

## [1.1.0-beta.8] — Build stamp: sapere QUALE build gira (diagnosi cache) (2026-07-31)

Primo passo per chiudere i problemi di cache della live-verify: un **build stamp**
(hash del contenuto del frontend) esposto in `/api/health` e mostrato nell'header
della chat accanto alla versione (`v1.1.0-beta.8 · <stamp>`). Cambia a ogni
modifica del frontend, quindi permette di verificare **con certezza** cosa gira:
se lo stamp non cambia dopo un update → non è arrivato il codice nuovo (cache del
browser/CDN o container non ricostruito), non un bug di logica. HIRIS già serve la
shell `no-store` e gli asset fingerprintati; questo aggiunge l'osservabilità che
mancava per puntare il fix giusto.

## [1.1.0-beta.7] — Modifica automazioni: overwrite anche senza id (per alias) (2026-07-31)

La beta.5 fa scrivere le proposte in HA, ma se il config non riporta l'`id`
(l'LLM spesso lo omette "modificando") si creava un **doppione** invece di
sovrascrivere. Ora `create_automation`, quando manca l'id, **risolve per alias**:
se esiste UNA sola automazione con quel `friendly_name`, modifica quella (riusa
il suo id); solo se non c'è match (o è ambiguo) conia un id nuovo. Fail-safe: in
caso di errore nel lookup, comportamento invariato (nuova).

## [1.1.0-beta.6] — Chat: la conversazione resta + "sta elaborando" (2026-07-31)

- **La chat non sparisce più.** Tornando alla pagina chat dalla configurazione
  (reload pieno) la conversazione dell'agente attivo veniva persa: la history
  era salvata lato server (per Chatbot) ma non veniva mai ricaricata al boot.
  Ora l'agente attivo è ricordato (localStorage) e la sua history ricaricata.
- **Mentre HIRIS elabora:** un indicatore **stile code** (prompt col caret +
  barrette monospace animate) e l'**input bloccato** per tutta l'elaborazione —
  incluso il poll della risposta via abbonamento (prima l'input si riapriva
  troppo presto e si poteva inviare un secondo messaggio mentre HIRIS pensava).

## [1.1.0-beta.5] — Fix bug #2: le proposte di modifica automazioni ora scrivono in HA (2026-07-31)

Root cause (dai log diagnostici beta.3/4): il Chatbot proponeva l'automazione con
`type='automation'` invece di `'ha_automation'`; l'apply non riconosceva l'alias e
cadeva nel ramo "status-only" che marca la proposta applicata **senza scrivere in
HA** — "sembrava applicata" ma l'automazione non cambiava (né errore né duplicato).

- **Normalizzazione del tipo + fail-loud.** `automation`→`ha_automation` (e
  `agent`→`hiris_agent`) alla creazione; un tipo davvero sconosciuto ora viene
  **rifiutato con un errore** invece di essere salvato e perso nel no-op. Il ramo
  status-only logga un warning permanente se mai un tipo non gestito lo raggiunge.
- **Modifica che sovrascrive davvero.** L'`id` presente nel config (che l'LLM
  copia leggendo l'automazione) viene **preservato**, così approvare una modifica
  **sovrascrive** l'automazione esistente invece di duplicarla. Per creare una
  automazione NUOVA l'LLM omette l'`id`. Descrizione del tool aggiornata.
- Rimossi i log diagnostici temporanei `[DIAG]` di beta.3/beta.4.

## [1.1.0-beta.4] — Diagnostica bug #2, giro 2: tipo proposta (2026-07-31)

La beta.3 loggava solo dentro il ramo `ha_automation`, ma l'apply osservato NON
lo attraversava (proposta di altro tipo → ramo "status-only" che non scrive in
HA). Ora si logga il **tipo della proposta prima del branching** e il passaggio
nel ramo status-only. Sempre solo `[DIAG]` temporanei, nessun cambio di comportamento.

## [1.1.0-beta.3] — Build diagnostica (bug #2: overwrite automazioni) (2026-07-31)

Solo **logging diagnostico** temporaneo sul giro di applicazione di una proposta
`ha_automation` (cosa arriva a `create_automation`, se il config ha `id`/`trigger`/
`action`, e lo stato della risposta HA). Serve a individuare perché l'approvazione
non sovrascrive l'automazione esistente. Nessun cambiamento di comportamento; i
`[DIAG …]` verranno rimossi nel commit di fix.

## [1.1.0-beta.2] — Notifiche: apri HIRIS al tap + leggibilità (2026-07-31)

Dalla live-verify: le notifiche della Companion aprivano la Dashboard home ed
erano poco leggibili. Ora:

- **Il tap apre HIRIS.** Ogni push HIRIS porta un `clickAction`/`url` alla UI
  ingress dell'add-on (`/hassio/ingress/<slug>`, ricavato dal Supervisor); il
  pulsante "Apri HIRIS" del pending punta allo stesso path (prima era rotto).
  Se lo slug non è disponibile, il deep-link viene omesso (nessuna regressione).
  I pending rossi restano **solo-OTP**: il deep-link è navigazione, non approva.
- **Più leggibili.** Canale dedicato "HIRIS" e, per il testo lungo, un `subject`.
- **"Nuovo dall'ultima visita".** All'apertura, la Dashboard del Brain evidenzia
  (e scrolla su) gli elementi del feed più recenti della tua ultima apertura —
  così, qualunque notifica tu tocchi, vedi subito cosa è nuovo. Stato locale
  per-dispositivo; rispetta `prefers-reduced-motion`.

## [1.1.0-beta.1] — Agenti v1.1 Fase 2 + 2.5 (2026-07-31, build di verifica)

Build **dev/beta** per la live-verify sul campo — non è la release 1.1.0 (che
arriva a fine Fase 4, con tag). Introduce la **modalità obiettivo** reale e il
primo strato di conferma out-of-band per gli agenti autonomi.

- **Modalità obiettivo (Agente v1.1).** Un agente può lavorare per un
  **obiettivo** in linguaggio naturale: ragiona ed emette **Task dichiarativi**
  (mai chiamate composte al volo), dentro un **perimetro** — entità e servizi
  consentiti, tetto tier, budget token e scadenza per esecuzione. I Task emessi
  ereditano identità e perimetro dell'agente; l'esecuzione li fa rispettare. La
  modalità obiettivo gira su **pianificazione** (gli eventi restano alle regole).
- **Step-up per i Task autonomi.** Un'azione emessa **oltre il verde** non viene
  più saltata in silenzio: **chiede conferma** (tap/OTP) all'**owner**
  configurato (opzione `agent_owner` + canale privato in `notify_users`), e viene
  eseguita solo all'approvazione. Senza owner/canale privato fallisce-chiuso
  (saltata, loggata). I domini pericolosi e i tier "off" non sono confermabili.
- **Perimetro applicato a ogni verdetto.** Un'azione fuori dal perimetro viene
  saltata a qualsiasi tier (non solo sul verde).
- **`max_tier` onorato fino al verde** (nessuna fiducia progressiva in questa
  fase: la fiducia progressiva è la Fase 3).
- **Tetto token robusto.** Il budget per esecuzione morde anche sui backend che
  non dichiarano `usage` (stima conservativa dai caratteri); `deadline_min` resta
  il bound di durata.

## [1.0.0] — Prima versione definitiva (2026-07-29)

Chiude l'arco SP-1→SP-4: HIRIS non è più uno stage sperimentale, è un
add-on con un modello mentale stabile e una cornice front-end coerente.
Nessuna capacità nuova rispetto alla 0.102.x — questa release **consolida**
ciò che le release 0.99.x→0.102.x hanno già introdotto e chiude il rebuild
dell'editor che le sosteneva.

- **Tre entità AI con nomi definitivi.** **Chatbot** — conversazionale, a
  interrogazione: prompt libero, legge HA liberamente, le azioni passano dal
  semaforo. **Agentbot** — autonomo: agisce o segnala **da solo** su un
  proprio trigger (cron/interval/evento), contratto a **verdetto JSON**,
  azione **dichiarata in configurazione**, mai scelta dall'AI. **Brain** —
  il fulcro: ragiona, traccia le abitudini della casa e propone (nuovi
  Agentbot, automazioni HA, evoluzioni), preferendo segnalare-e-chiedere
  piuttosto che agire di testa propria.
- **Home del Brain (`#/`).** Stream dei ragionamenti (rationale del giro
  olistico, nessuna nuova chiamata LLM), segnalazioni da un health-scan a
  **5 controlli read-only** (entità non disponibili, batterie scariche,
  automazioni rotte, domini pericolosi in verde, entità senza area — si
  auto-risolvono quando il problema sparisce), e proposte in attesa di
  revisione, tutto in un unico stream.
- **Layer Modelli (`#/models`).** Attivazione provider esplicita (un
  provider è usato solo se attivo *e* credenziato), **Abbonamento Claude
  Max first-class** (sostituisce la vecchia accoppiata
  `chat_via_subscription`+`bridge_enabled`), catena di fallback unica
  riordinabile, e **modello per-entità**: ogni Chatbot e ogni Agentbot
  sceglie il proprio modello, il Brain il suo (`brain_model`).
- **Cornice unificata.** Un solo editor per Chatbot e Agentbot (stesso kit
  condiviso: dirty-tracking reale, guard di navigazione, selettore entità
  istanziabile — i puntelli legacy che tenevano insieme l'editor precedente
  sono stati smontati). Creazione **goal-first** (`#/nuovo`): l'utente
  scrive l'obiettivo in linguaggio naturale, HIRIS deriva il tipo giusto
  (Chatbot o Agentbot, euristica deterministica — nessuna chiamata LLM, e
  la scelta resta sempre modificabile), poi passa all'editor avanzato per
  rifinire. `#/chatbots/new` resta la via diretta per chi preferisce
  partire dall'editor vuoto. `knowledge_access` (scope memoria) è ora
  **configurabile dalla UI** invece che solo da API.
- **Sicurezza invariata.** Il **semaforo** resta l'unico gate delle azioni
  (tier + denylist domini pericolosi); l'Agentbot ragiona **senza tool
  liberi** (single-shot, ristretto a tool di sola lettura) e la sua azione
  è sempre dichiarata in configurazione, mai scelta dall'AI — la linea
  rossa fra prompt libero (Chatbot) e verdetto-JSON (Agentbot) è tenuta
  strutturalmente (due builder disgiunti su due endpoint disgiunti).
- **Qualità.** Alla suite Python si aggiunge una nuova suite di **test
  comportamentali front-end** (`node --test` + jsdom, DOM vero e
  interazione, non solo asserzioni di testo) eseguita in CI insieme a
  pytest.

**Nota operativa per chi aggiorna:**

- Chi arriva da una versione **≤ 0.101.x** ha già eseguito le migrazioni
  dati (rename `agent→chatbot`/`lente→agentbot`, `knowledge.db`,
  `chat_history.db`, MQTT) al passaggio per la 0.102.0 — vedi le note
  operative di quella release. Non c'è nessuna migrazione dati aggiuntiva
  per la 1.0.0: solo il front-end è stato ricostruito.
- **Aggiornare HIRIS e Retro Panel insieme**: Retro Panel **≥ 2.24.0**
  richiede HIRIS **≥ 0.102.0** (il proxy chiama `/api/chatbots`, non
  `/api/agents`).
## [0.102.1] — Fix: le proposte non falliscono più con un errore indefinito (2026-07-28)

### Corretto
- **Proposte di automazione**: quando il modello ometteva un campo obbligatorio nella
  chiamata allo strumento, l'errore risultante era un `KeyError` intercettato dal
  gestore generico — l'utente vedeva solo *"Strumento non riuscito. Riprova più tardi"*
  e la proposta non veniva mai creata. Ora il messaggio nomina il campo mancante
  (es. *"Campi obbligatori mancanti: routing_reason"*), così il modello può correggersi
  e riprovare.
- Stesso difetto chiuso **come classe**: ogni strumento a cui manchi un campo
  obbligatorio (`send_notification`, `call_ha_service`, `create_task`, …) ora riporta
  quale campo manca invece di un errore indistinto.
- Rimossa una fuga di dettagli interni (`str(exc)` grezzo) nel percorso di salvataggio
  delle proposte.

## [0.102.0] — SP-4 Fase A: rename profondo Chatbot/Agentbot (2026-07-28)

Rinominato in modo esteso `agente→Chatbot` e `lente→Agentbot` in tutto HIRIS
(entità, API, route, DB, storage, frontend, wire MQTT, plumbing interno) e
aggiornato Retro Panel in lockstep. **Comportamento invariato** — solo nomi:
stesso semaforo, stessi contratti Agentbot (verdetto-JSON senza tool) e
Chatbot (tool liberi senza trigger), stesso runner, stessa memoria, stesso
scheduling.

- **API/route:** `/api/agents`→`/api/chatbots`, `/api/lenses`→`/api/agentbots`,
  `#/agents`→`#/chatbots`, `#/sentinel` (lenti)→`#/agentbots`. Le route
  `/api/chat`, `/api/entities`, `/api/suggestions*`, `/api/sentinel/policy`,
  `/api/sentinel/timeline` (config/timeline Sentinella, non le lenti
  user-defined) restano invariate.
- **DB/storage:** colonna `knowledge_items.lens`→`chatbot_id`; colonne e indici
  `chat_store` (`agent_id`→`chatbot_id`, `idx_msg_agent/idx_sess_agent`→
  `idx_msg_chatbot/idx_sess_chatbot`); `agents.json`→`chatbots.json`,
  `sentinel_lenses.json`→`agentbots.json`. Migrazioni automatiche, idempotenti
  e non-fatali al boot: nessuna perdita dati, nessun intervento manuale
  richiesto.
- **Wire MQTT:** topic `hiris/agents`→`hiris/chatbots`, nuovo schema id
  discovery. **Le entità Home Assistant scoperte col vecchio schema vengono
  ripulite automaticamente e ricreate col nuovo** al primo avvio — un
  eventuale riordino delle entità HIRIS in Home Assistant dopo l'aggiornamento
  è atteso.
- **Chat-wire coerente:** il body di `/api/chat` accetta ora `chatbot_id` come
  chiave primaria, con `agent_id` mantenuto come fallback retro-compat — le
  dashboard Lovelace esistenti continuano a funzionare senza modifiche;
  la card `hiris-chat-card.js` scrive `chatbot_id` nelle nuove configurazioni.
- **Retro Panel aggiornato in lockstep** (v2.24.0): il proxy HIRIS chiama ora
  `/api/chatbots` invece di `/api/agents`.
- **Non rinominato (per design):** l'etichetta di origine richiesta
  `agent_id="mcp-gateway"/"unknown"` in `handlers_execute.py` /
  `handlers_gateway_pending.py` / `http_tools.py` (è un'origine, non un id di
  Chatbot); il subsystem `hiris/app/agent/runner.py` (poller della coda di
  ragionamento, non l'entità Chatbot); il prefisso discovery HA
  `"homeassistant"`; l'aggettivo "agentic" nei runner.

**⚠️ Note operative per l'aggiornamento:**

- **Aggiornare HIRIS e Retro Panel insieme.** L'API è cambiata: Retro Panel
  ≥ 2.24.0 richiede HIRIS ≥ 0.102.0 (il proxy RP chiama `/api/chatbots`, che
  non esiste sulle versioni HIRIS precedenti).
- **Aggiornamento non reversibile.** Le migrazioni automatiche riscrivono
  `knowledge.db` (schema v3) e `chat_history.db`, e rinominano
  `sentinel_lenses.json`→`agentbots.json` sul disco. Un downgrade a una
  0.101.x precedente **non è supportato** dopo l'aggiornamento — fare uno
  snapshot dell'add-on/HA prima di aggiornare.
- **Reset una-tantum atteso (non è un bug).** Al primo avvio dopo
  l'aggiornamento: il cooldown e il cap giornaliero degli Agentbot, e i
  timer di durata (`duration_min`) delle condizioni in corso, ripartono da
  zero (cambio di chiave interna `lens:*`→`agentbot:*`); le entità MQTT
  scoperte col vecchio schema (`hiris_<id>_*`) vengono ritirate e
  ripubblicate col nuovo schema (`chatbot_<id>_*`) — un eventuale riordino
  delle entità HIRIS in Home Assistant è quindi atteso.

## [0.101.0] — Brain come fulcro: home, stream ragionamenti, health-scan advisory (SP-3 v1) (2026-07-28)

**Home del Brain su `#/`:** supervisione casa + stream ragionamenti (cattura rationale del giro olistico, nessuna nuova chiamata LLM) + segnalazioni (health-scan a 5 check read-only: entità non disponibili, batterie scariche, automazioni rotte, domini pericolosi in verde, entità senza area).

- **Nuovi endpoint `/api/brain/feed|reasoning|advisories`:** aggregatore unificato, endpoint advisory con ack/dismiss.
- **Advisory sola-lettura:** non attuano mai; i fix passano dal percorso proposte→semaforo.
- **Feed unificato:** 4 sorgenti tipizzate + timestamp: rationale + health-scan + proposte + sentinel tracce.
- **Cattura rationale:** sanitizzato, retention-capped, no nuovo egress LLM.

---

## [0.100.0] — Layer Modelli: attivazione provider, una catena, modello per-entità e per-provider (SP-2) (2026-07-27)

Ridisegno della gestione dei modelli AI (retro-compatibile: nessun install
esistente cambia comportamento).

- **Attivazione provider esplicita:** toggle `provider_subscription/claude/openai/
  openrouter/ollama` nella config dell'addon. Un provider è usato solo se attivo
  E con credenziale. Su un install esistente (toggle a false) i provider attivi
  sono derivati dalle credenziali già presenti — comportamento invariato.
- **Abbonamento first-class:** il toggle `provider_subscription` sostituisce la
  vecchia accoppiata `chat_via_subscription`+`bridge_enabled` (che restano letti
  per retro-compat). Attivarlo abilita chat, Brain e Agentbot in `auto`
  sull'abbonamento. Il fail-safe della coda di ragionamento è preservato.
- **Una catena modello globale** con failover, al posto della doppia
  `chat_policy`/`automatic_policy`. Riordinabile; ricalcolata al boot includendo
  sempre tutti i provider attivi.
- **Modello per-entità:** ogni **Chatbot** e ogni **Agentbot** sceglie il proprio
  modello (nuovo campo per-Agentbot); il **Brain** ha il suo (`brain_model`).
- **Modello di default per-provider:** per Claude/OpenAI/OpenRouter scegli quale
  modello usare quando l'entità è in `auto` (Ollama usa il suo modello fisso).
- **Nuova sezione "Modelli"** (`#/models`): provider attivi + stato credenziale,
  catena, assegnazione per-entità, embeddings (dichiarati separati —
  l'Abbonamento non fa embeddings), con distinzione tra impostazioni applicate
  al riavvio e quelle live.
- **Sicurezza invariata:** semaforo, contratto Agentbot verdetto-JSON-senza-tool,
  gate egress memoria sensibile (che continua a fallire in sicurezza), loopback
  MCP e token OAuth. Nessun segreto esposto dalle API.


## [0.99.5] — Rinomina AI: Chatbot / Agentbot / Brain (SP-1a) (2026-07-27)

Fondazione dei nomi (SP-1 della north-star). Rinominato **solo il testo
visibile** delle entità AI, senza toccare codice interno, API, route o DB:

- **Chatbot** = assistente conversazionale, a interrogazione (chiedi → risponde).
- **Agentbot** = entità autonoma/proattiva, agisce o segnala da sola su trigger.
- **Brain** = il core che ragiona, traccia le abitudini e propone nuovi Agentbot,
  automazioni HA ed evoluzioni.

Aggiornati: navigazione/breadcrumb, editor e lista Chatbot, viste proattive,
pagina chat + card Lovelace, dropdown modelli, pagine consumi/task, e
`PRODUCT.md`. Identificatori, endpoint `api/agents`, route `#/agents`/`#/sentinel`
e la colonna DB restano invariati: **nessuna rottura**, i dati esistenti non
sono toccati. Il wizard di onboarding usa il termine neutro "assistente" perché
copre più tipi.


## [0.99.4] — Diagnostica errori chat abbonamento (2026-07-27)

- Il runner chat via abbonamento ora, se `claude -p` fallisce, logga stdout+stderr
  e restituisce il dettaglio dell'errore (auth/quota/ecc.) invece del muto
  "[errore runner]" — sia nel log sia nella risposta, per diagnosi.


## [0.99.3] — Chat via abbonamento self-contained (MCP interno + runner in-addon) (2026-07-27)

Passo verso un'app unica: la chat via abbonamento può ora girare **interamente
dentro l'addon**, senza il gateway esterno. **Opt-in, spenta di default** — chi
usa la chat con API key non è toccato.

- **MCP interno:** l'addon espone i propri tool via un server MCP su `127.0.0.1`
  (solo loopback), che inoltra alla execute-API interna — allowlist e **semaforo
  invariati**.
- **Runner in-addon:** l'immagine include node + Claude CLI; un worker interno
  consuma la coda di ragionamento e lancia `claude -p` (autenticato via il nuovo
  campo secret **`claude_code_oauth_token`**, da `claude setup-token`) contro
  l'MCP interno. Si attiva solo con `chat_via_subscription: true` + token.
- **Kill-switch/audit** in-memory sul percorso MCP.
- Nessuna esposizione pubblica, nessun OAuth: tutto su loopback. Il gateway
  esterno non è più necessario per questo percorso (dismissione separata).

## [0.99.2] — Fix modifica automazioni via proposta (2026-07-26)

- **Approvare una proposta di *modifica* automazione ora sovrascrive davvero
  l'automazione esistente in Home Assistant**, invece di crearne una duplicata
  lasciando l'originale invariata. Prima l'apply coniava sempre un id nuovo;
  ora riusa l'id dell'automazione da modificare (dal parametro esplicito o dalla
  config). Una proposta di automazione *nuova* nata copiando una esistente non
  può più sovrascrivere per errore l'originale (l'id viene rimosso se non stai
  esplicitamente modificando). Rilevante per la chat con tool HA reali.

## [0.99.1] — Residui di robustezza/privacy pre-1.0 (2026-07-26)

Patch sulla RC 0.99: chiusi i tre residui low-impact rimasti dalla review, con
revisione indipendente (Fable) = *ready to merge*.

- **Privacy step-up:** l'OTP di conferma viene inviato solo a un dispositivo
  privato per-utente; un servizio `notify` condiviso/globale (o
  `persistent_notification`) non riceve più il codice — in quel caso l'azione
  ricade sul flusso "richiede conferma" senza mai esporre il segreto.
- **Mayan:** un errore di scrittura dei chunk dopo la creazione del documento
  esegue il rollback dell'item (che ora ripulisce anche i chunk orfani), così
  il documento viene ritentato intero al giro successivo invece di restare un
  gap parziale permanente; un doppio errore viene loggato senza interrompere il
  resto del batch.
- **Messaggi:** l'avviso di circuito aperto distingue backend cloud
  ("Il servizio AI") da locale ("Il backend locale"); errore generico di
  dispatch tutto in italiano.

_Nota infra (non tocca l'addon): il runner del gateway MCP chat-via-abbonamento
su .31 girava una build precedente al ramo chat — redeployato; la chat via
abbonamento ora risponde correttamente._

## [0.99.0] — Chiusura finding medium/low pre-1.0 (2026-07-26)

Release candidate verso la 1.0: chiusi **tutti i finding medium e low** della
review multi-agente dell'intera codebase (i critical/high erano già stati
chiusi nella 0.90.0). Review finale whole-branch indipendente (Fable): nessun
finding critical o important, esito **pronto al merge**.

- **Robustezza task/lenti:** finestra oraria che scavalca la mezzanotte gestita
  correttamente (le finestre notturne non scadono più per errore); una finestra
  degenere `from==to` ora scade invece di restare attiva per sempre; le lenti
  memorizzate ma non più valide vengono loggate quando scartate (niente sparizioni
  silenziose); cron con valori fuori range rifiutato alla creazione.
- **Sicurezza difesa-in-profondità:** sanitizer anti-injection ampliato (marcatori
  strutturati, forme flesse di override/bypass); filtro storico HA con quoting;
  `limit` negativo sui log del sentinella limitato all'intervallo `[1,200]`;
  errori di dispatch generici verso il chiamante (dettaglio solo nei log server).
- **Concorrenza:** cleanup dei task su snapshot sotto lock; riferimenti forti ai
  task immediati; circuit-breaker e avviso di troncamento sui percorsi di chat.
- **Frontend:** id nei pulsanti passati via data-attribute (niente interpolazione
  di stringa JS); escaping quote-safe condiviso.
- **Infra/deps:** dipendenze principali con cap di versione; `run.sh` con guardie
  su jq, formato CIDR e pre-flight dei provider LLM (avvisi chiari all'avvio).
- **Mayan:** un fallimento transitorio dell'embedder non marca più il documento
  come ingerito (verrà ritentato al prossimo giro).

## [0.90.0] — Hardening di sicurezza pre-1.0 (2026-07-25)

Release intermedia verso la 1.0: dopo una **review completa multi-agente
dell'intera codebase**, sono state chiuse **tutte le vulnerabilità critiche e
alte** individuate, ciascuna con fix + revisione indipendente.

- **Semaforo rafforzato:** anche l'attivazione di automazioni e degli helper
  (input_boolean/number/text/select) passa ora dal controllo tier; le azioni
  vengono eseguite esattamente sulle entità autorizzate (niente più diffusione
  a tutto il dominio quando l'ambito è una singola entità).
- **Approvazione step-up più sicura:** l'approvazione delle azioni sensibili
  richiede l'interfaccia HIRIS (un umano), non il token di servizio usato dal
  gateway — così un componente automatico non può auto-approvarsi.
- **Isolamento dei dati:** niente accesso incrociato tra utenti agli elementi
  privati del second-brain; nessuna fuga di dati personali tra conversazioni;
  gli strumenti di lettura rispettano gli ambiti configurati; corretto un caso
  di SSRF/percorso e uno di possibile mescolamento di dati tra richieste.
- **Validazione e robustezza:** soglie dei rilevatori e configurazione
  validate prima di essere applicate; failover automatico tra modelli LLM se
  un backend è irraggiungibile; i task pianificati non restano più bloccati.
- **Chat via abbonamento più reattiva** (lato infrastruttura).

## [0.38.0] — UI/UX hardening pre-1.0 (2026-07-25)

- **Configurazione più chiara:** rimosso un campo inutilizzato (Primary Model),
  descrizioni corrette (incluso il toggle Debug, che da solo non apre la porta —
  la porta si mappa nella sezione Rete), strategie LLM distinte, e valori
  numerici ora validati.
- **App più robusta:** le pagine sconosciute mostrano un fallback invece di
  restare bloccate; se una sezione non carica, ora lo dice invece di mostrare
  trattini vuoti o una falsa schermata di primo avvio.
- **Pulizia e privacy:** rimossi residui di sviluppo e sostituito il servizio di
  notifica di esempio personale con uno neutro predefinito.
- **Accessibilità:** filtri e campi dei form ora usabili da tastiera e con
  etichette associate; menu laterale con stato annunciato agli screen reader.

## [0.37.0] — Maggiordomo: briefing e scadenze (Slice 7 verso 1.0) (2026-07-25)

- **Il maggiordomo:** ogni mattina un unico riepilogo in linguaggio naturale
  delle scadenze imminenti (dai tuoi documenti) e dello stato notevole della
  casa (porte/finestre aperte, batterie scariche) — al posto delle vecchie
  notifiche ripetute una per scadenza.
- **Promemoria urgenti, non ripetuti:** le scadenze di oggi/domani/scadute
  ricevono un avviso puntuale, una sola volta per soglia.
- **A richiesta in chat:** puoi chiedere "cosa devo fare oggi?" e ottenere lo
  stesso riepilogo.
- Privacy: le scadenze sensibili entrano nel riepilogo solo quando
  l'elaborazione resta locale — sia nel briefing del giorno sia nella richiesta
  in chat (che rispetta anche la configurazione di accesso ai dati sensibili
  dell'agente). Il riepilogo segnala quante scadenze riservate ha nascosto.

## [0.36.1] — Hardening anti-injection italiano (2026-07-25)

- Il filtro anti-manipolazione che protegge il cervello dalle istruzioni
  nascoste nei dati ora riconosce anche le formule italiane ("ignora le
  istruzioni", "dimentica tutto", "agisci come…"), non solo quelle inglesi —
  senza intaccare i testi legittimi (es. "il sistema ha ignorato l'evento").

## [0.36.0] — Ragionamento consapevole (Slice 6b verso 1.0) (2026-07-24)

- **Il cervello ora ragiona con memoria:** quando la sentinella valuta un
  evento (o durante il controllo giornaliero "va tutto bene?"), tiene conto
  degli insight e delle preferenze rilevanti che ha imparato sulla tua casa,
  non solo del dato grezzo del momento.
- **Privacy per progettazione:** le informazioni marcate come sensibili
  entrano nel ragionamento solo quando l'elaborazione resta locale; con un
  modello cloud il cervello usa solo informazioni non sensibili.

## [0.35.1] — Fast-follow ciclo cognitivo (2026-07-24)

- Il cervello ora mantiene una sola riga di taratura annullabile per rilevatore
  (le tarature ripetute superano le precedenti, niente più righe "Annulla"
  bloccate).

## [0.35.0] — Ciclo cognitivo: soglie auto-apprese (Slice 6 verso 1.0) (2026-07-24)

- **Soglie auto-apprese:** il cervello tara le soglie di rilevamento (v1: consumo)
  sulla base dei dati reali della tua casa invece che su valori fissi — solo per i
  rilevatori già attivi, con limiti di sicurezza, e con un annullamento.
- **Spiegabilità:** ogni configurazione/taratura automatica del cervello lascia una
  traccia in memoria, così puoi chiedere in chat "perché hai cambiato X?" e ottenere
  la spiegazione.
- Il ragionamento consapevole (il cervello che consulta insight e preferenze durante
  la valutazione) arriva in una versione successiva.

## [0.34.0] — Lenti definite dall'utente (Slice 5b verso 1.0) (2026-07-24)

- **Crea le tue lenti:** oltre ai detector predefiniti, ora puoi definire lenti
  custom dalla pagina Sentinella — scatto su **evento** (quando un'entità supera
  una soglia, con durata opzionale) o a **tempo** (cron/interval), con
  ragionamento AI opzionale (un tuo prompt) e un'azione (notifica o un servizio).
  Le azioni passano sempre dal semaforo (target deterministico dalla tua config;
  l'AI decide solo se/come avvisare, mai cosa attuare).

## [0.33.0] — Lenti e Personas (Slice 5 verso 1.0) (2026-07-24)

- **Modello unificato:** niente più due paradigmi. Il livello proattivo è la
  Sentinella (detector/situazioni "lenti", tarabili); la chat è configurata con
  **Personas** (prompt, tool, memoria, politica chat). Ritirata la vecchia macchina
  di azioni/regole/stati degli agenti autonomi (sostituita dalla pipeline sicura
  della Sentinella con il semaforo).
- Le lenti definite dall'utente (trigger e prompt personalizzati) arrivano in una
  versione successiva.
- Le installazioni pre-esistenti con agenti autonomi legacy mantengono solo i campi
  persona (chat): i vecchi comportamenti autonomi sono sostituiti dalla Sentinella,
  senza migrazione automatica dei comportamenti custom.

## [0.32.0] — Chat via abbonamento (Slice 4b verso 1.0) (2026-07-24)

- **La chat può girare sull'abbonamento Claude** (opzione `chat_via_subscription`,
  default off): quando attiva, i messaggi sono elaborati in modo asincrono da un
  runner esterno via `claude -p` (a costo zero di token metered), con la chat che
  mostra "risposta in arrivo" e la recupera al termine. Cap chat giornaliero
  separato e una sola risposta in volo per conversazione.
- Con l'opzione off la chat resta sincrona come prima (nessun cambiamento).

## [0.31.0] — Due politiche di routing LLM (Slice 4 verso 1.0) (2026-07-24)

- **Due politiche separate** per la scelta del provider AI: una per il ragionamento
  **automatico** (sentinella, agenti proattivi/schedulati) e una per la **chat**
  interattiva — configurabili come ordine di backend (es. `claude,ollama`) dalle
  opzioni dell'add-on (`automatic_policy` / `chat_policy`). Vuote = usano la
  strategia esistente (nessun cambiamento per chi non le imposta).
- Il modello per-agente resta come override esplicito quando serve.

## [0.30.0] — Memoria unificata (Slice 3 verso 1.0) (2026-07-23)

- **Un unico substrato di memoria:** la memoria di lavoro per-agente confluisce nel
  second brain (KnowledgeStore) con scoping unificato — personale (owner), condivisa
  (home) e di lavoro dell'agente (lens). `save_memory`/`recall_memory` restano come
  alias. Migrazione automatica una-tantum della memoria esistente (nessuna perdita).
- La conoscenza personale è ora correttamente **per-utente** (non più tutta "home").
- Il filtro `kinds` di `knowledge_access` è finalmente attivo.
- Rinominato il DB delle classificazioni entità in `home_map.db` (toglie l'ambiguità
  con il knowledge store).

## [0.29.0] — Step-up di conferma dalla chat (Slice 2 verso 1.0) (2026-07-23)

- **Conferma out-of-band per le azioni a rischio richieste in chat:** un'azione
  gialla/rossa o su un dominio pericoloso richiesta a un assistente viene congelata
  e confermata dal telefono dell'utente — **tap** sulla notifica (primario) o
  **codice OTP** digitato in chat (fallback, tool `confirm_pending`). L'azione
  eseguita è quella congelata: l'assistente non può alterarla, solo sbloccarla.
- **Notifiche per-utente:** mappa persona HA → servizio notify (con fallback globale),
  così la conferma arriva al telefono di chi sta chattando.
- **Inbox unica** "Da approvare": i pending di chat e gateway nello stesso elenco.
- **Sicurezza:** azioni con target per area/dispositivo/label sui percorsi non
  confermati sono ora bloccate (fail-closed), per non aggirare gli override per-entità.

## [0.28.0] — Semaforo universale (Slice 1 verso 1.0) (2026-07-23)

- **Semaforo universale (Slice 1 verso 1.0):** il semaforo (tiers/entity_tiers)
  e la denylist domini pericolosi sono ora il gate UNICO su ogni `call_ha_service`
  — chat, agenti, gateway, sentinella e task differiti passano tutti dallo stesso
  controllo (`hiris/app/security/semaphore.py`).
- **Fail-closed:** un dominio non configurato nel semaforo (`off`) blocca l'azione
  anche da chat. Configura le categorie dalla pagina gateway perché le azioni siano
  eseguibili. Le letture non sono mai gated.
- Le azioni yellow/red richieste in modo **non confermato** (chat/agente diretti) sono
  per ora bloccate; il flusso di **conferma umana esistente del gateway** ("Approva" dalla
  notifica) continua a eseguirle, inclusi i domini pericolosi quando approvati out-of-band
  (`tier_confirmed`). Lo step-up di conferma dalla chat arriva nella Slice 2.

## [0.27.0] — Cervello auto-proponente + selettore entità (2026-07-23)
- **Selettore di entità** nella pagina Sentinella: scegli le entità dalla lista filtrata
  per tipo (niente più entity id scritti a mano). Nuova API `/api/entities`.
- **Cervello auto-proponente**: la scansione olistica confronta l'inventario della casa con
  la configurazione attuale, trova buchi di copertura e **auto-configura** nuovi detector
  (marcati "brain", con undo dalla pagina "Suggerimenti"). Le opportunità di gestione
  diventano proposte di automazione (approvazione umana — le automazioni HA girano fuori
  dal semaforo). Grounding + cap anti-runaway; il cervello non tocca mai la config utente.

## [0.26.0] — Ponte push→abbonamento: coda di ragionamento (scheletro olistica) (2026-07-22)

- **Nuova fondazione: coda di ragionamento (`ReasoningQueue`)** + API
  `/api/reasoning/claim` e `/api/reasoning/submit` (nonce monouso). Con
  `bridge_enabled`, la scansione olistica non ragiona più inline: accoda un job
  che un runner esterno (abbonamento Claude) drena e a cui restituisce la
  Decisione — eseguita da HIRIS con il semaforo (il runner non bypassa la
  sicurezza).
- **Fallback**: i job non serviti entro la scadenza vengono ragionati dal
  provider metered/locale (con cap), così il cervello resta vivo se il runner è
  giù. Opzioni addon `bridge_enabled`/`bridge_deadline_min`/`bridge_fallback`.
- Solo la scansione olistica passa dal ponte in questa versione; i tool gateway
  e il container runner arrivano nei rilasci successivi.

## [0.25.0] — Cervello proattivo: preparazione contestuale (fetta 3) (2026-07-22)

- **Nuova capacità: preparazione al rientro serale.** Quando la presenza passa
  fuori→casa ed è sera (sole sotto l'orizzonte o dopo un'ora configurata), HIRIS
  attiva una scena configurata (luci esterne/ingresso + clima) — con autonomia
  graduata sul semaforo (verde+opt-in per farlo da solo, altrimenti propone).
- Trigger a evento in tempo reale (transizione di presenza), distinto dal
  guardiano anomalie e dalla ronda situazioni; cooldown anti-flapping.
- Sicurezza: unico attuatore gated da semaforo + denylist; target deterministico
  dalla config (una scena HA); default prudente (agisci-auto spento).
- Config: sezione "Preparazione" nella pagina Sentinella. La prossimità
  (anticipazione prima dell'arrivo) è un'estensione futura opzionale.

## [0.24.0] — Cervello proattivo: valutatore di situazioni (fetta 2) (2026-07-21)

- **Nuova capacità: valutazione olistica e periodica delle situazioni di casa.** Una
  ronda deterministica (zero-AI) costruisce una foto della casa (presenza, meteo,
  temperatura esterna, allarme, salute HA) e sveglia il cervello solo quando una
  situazione scatta.
- **3 situazioni iniziali**: caldo forte + nessuno in casa → avvia irrigazione per
  N minuti (prima azione autonoma "verde", opt-in, con spegnimento programmato);
  tutti fuori + allarme disinserito → allerta (l'allarme non si arma mai in
  autonomia — denylist); scansione olistica AI (rate-capata) per gli imprevisti.
- **Sicurezza**: unico attuatore (l'esecutore) gated da semaforo + denylist; azione a
  target deterministico dalla config; default prudente (agisci-auto spento).
- **Config**: sezione "Situazioni" nella pagina Sentinella; intervallo ronda addon.

## [0.23.0] — Cervello proattivo: Sentinella anomalie (fetta 1) (2026-07-20)

- **Nuova capacità: livello cognitivo proattivo.** Un guardiano deterministico
  (zero-AI) sorveglia lo stato della casa in tempo reale e sveglia un ragionamento
  AI solo quando un segnale supera soglia/durata, con debounce, cooldown e cap
  giornaliero rigido.
- **4 detector**: aperture prolungate, catena del freddo (frigo/freezer),
  consumo anomalo, batterie scariche. Configurabili dalla nuova pagina "Sentinella".
- **Autonomia graduata sul semaforo**: verde → agisci-e-notifica (opt-in, spento
  di default); giallo → proponi; rosso/off → solo allerta. Ogni azione è
  rivalidata dal semaforo lato server (anti prompt-injection).
- **Osservabilità**: timeline eventi (segnale → esito) nella pagina Sentinella.
- **Opzioni addon**: cap risvegli/giorno, pausa tra risvegli, azioni automatiche
  su domini verdi.

## [0.22.1] — Fix creazione dashboard da chat: tetto token e costruzione incrementale (2026-07-17)

- **Fix: la creazione di dashboard/script da chat sembrava riuscire ma non
  produceva nulla.** La chiamata con l'intero config Lovelace superava il limite
  di output (max_tokens 4096): la generazione si troncava a metà e il runner
  restituiva solo il testo del preambolo senza eseguire la creazione. Ora la chat
  ha un tetto di output più alto (16000 token — è un tetto, non aumenta il costo
  delle risposte normali), i troncamenti vengono segnalati con un messaggio chiaro
  invece del falso "creata", e le dashboard grandi si costruiscono in modo incrementale.
- **Nuovo strumento chat `add_dashboard_view`**: aggiunge una vista/stanza alla
  volta a una dashboard esistente, così case con molte stanze non superano mai il
  limite di token in una singola risposta.
- **`create_ha_config`** guida il modello a creare prima la dashboard con poche
  viste e poi aggiungere le stanze una alla volta.
- **Modelli locali (OpenRouter/Ollama)**: stessa gestione del troncamento
  (`finish_reason=length`) del percorso Claude.
- **Fix: rollback dashboard orfana.** Se `lovelace/config/save` fallisce dopo la
  creazione, la dashboard vuota appena creata viene eliminata, evitando che i
  tentativi successivi falliscano per sempre su un url_path ormai esistente.
- **Cap `max_tokens` per tipo di agente**: chat fino a 16000, agenti
  proattivi/reattivi restano a 8192 (costo, latenza, sicurezza prompt-injection).

## [0.22.0] — Generazione config HA da chat e MCP (dashboard, script, scene) (2026-07-17)

- **Nuova capacità: HIRIS crea dashboard Lovelace, script e scene su Home Assistant.**
  Nuovo tool `create_ha_config` (chat-only). Da chat HIRIS l'artefatto viene scritto
  subito su HA; dal gateway MCP viene salvato come **proposta pending** che l'operatore
  approva dalla pagina Proposte (con anteprima del config), rispecchiando il semaforo di
  sicurezza già esistente per `call_ha_service`.
- **Write layer HA**: `create_script`/`create_scene` via REST config API (+ reload);
  `create_dashboard` via WebSocket Lovelace (`lovelace/dashboards/create` + `config/save`).
  Dashboard sempre additive (nuova voce in sidebar, non tocca quelle esistenti).
- **Validazione condivisa** in `config_tools.py`: slug/id, config non vuoto, cap dimensione,
  presenza di `views` per le dashboard. Identica per il percorso chat (scrittura diretta)
  e MCP (proposta).
- **Sicurezza**: da MCP il tool non viene mai eseguito direttamente (intercettato prima del
  dispatch → proposta); non disponibile agli agent non-chat (proattivi/reattivi restano
  read-only); output non fidato nella UI review escapato (stored-XSS chiuso).
- **Perché**: generare plance, scene e script in linguaggio naturale, mantenendo il
  controllo umano quando la richiesta arriva da un canale esterno (MCP).

## [0.21.2] — Notifiche persistenti Home Assistant (send_notification) (2026-07-01)

- **Nuova capacità: notifiche persistenti nel dashboard HA.** `send_notification`
  ora supporta il canale **`ha_persistent`** (→ `persistent_notification.create`,
  con `title` e `notification_id`; rimozione via `dismiss` passando `notification_id`
  e `message` vuoto). Anche il canale `ha_push` ora invia il `title`.
- **Perché**: un task creato via MCP gateway per creare una notifica persistente non
  veniva eseguito — `persistent_notification` non è tra le categorie del semaforo
  (tier `off`), i task rifiutano le `call_ha_service` senza `entity_id`, e non
  esisteva alcun percorso per emettere `persistent_notification`. Le notifiche sono
  informative e non azionano dispositivi: ora hanno un canale dedicato, fuori dai
  cancelli di attuazione ("sempre permesse").
- **Execute-API**: `send_notification` è sempre esposto (indipendente da
  `EXECUTE_API_TOOLS`), così il gateway può sempre raggiungere l'utente.
- **Osservabilità**: i risultati di rifiuto dell'execute-API ora includono
  `"ok": false` (non più scambiabili per successo dal chiamante MCP).
- Guida `create_task` aggiornata: usare `send_notification` per le notifiche, mai
  `call_ha_service` su `persistent_notification`/`notify`.
- Nuovi test `tests/test_notifications.py` + copertura execute-API. 764 test.
- **Nota**: richiede anche il redeploy del MCP gateway per esporre a Claude il nuovo
  tool `send_notification` e la descrizione aggiornata.

## [0.21.1] — Fix cache-busting asset: menu /config Storicizzazione + Accessi Gateway (2026-07-01)

- **Bugfix**: nella pagina /config i menu del drawer *Storicizzazione* (`#/history`)
  e *Accessi Gateway* (`#/gateway`) non entravano — un `main.js` cachato dal browser
  (privo delle registrazioni delle route) veniva servito ancora dopo l'upgrade.
- **Causa**: il cache-busting iniettava un unico `?v=VERSION` globale su tutti gli
  asset; cambiava solo al bump di versione, quindi ogni modifica JS/CSS senza bump
  riusava lo stesso URL e browser/HA-Ingress servivano il file stale.
- **Fix**: `_inject_version()` ora inietta un fingerprint **per singolo file**
  (`?v=<hash-contenuto>`, cache invalidata per mtime) — qualunque modifica al file
  cambia l'URL e forza il refetch, senza dipendere dal bump di versione. Aggiunto
  anche `Cache-Control: no-cache` sugli asset `/static/` (revalidation, difesa in
  profondità contro il proxy HA Ingress).
- Nuovo test `tests/test_cache_busting.py`. 754 test.

## [0.21.0] — Semaforo per-entità + pip-audit (Road to 1.0, Blocker 3) (2026-06-29)

- **Granularità per-entità del semaforo**: oltre al livello per-dominio, ora puoi
  impostare override per singola entità (off/green/yellow/red) — l'entità batte il
  dominio. Es. dominio Interruttori verde ma `switch.cancello off`, oppure dominio
  off con `switch.lampada green`. UI: riquadro "Override per entità" in *Accessi
  Gateway*. Chiude il residuo "sharp" dell'audit (domini eterogenei).
- **Enforcement a tenuta** (audit adversariale + fix): un'entità `off` dentro un
  dominio verde è bloccata sia per azione diretta sia (bypass chiuso) per azione
  **schedulata in un task** — i task possono contenere solo azioni verdi. La
  risoluzione del tier è entity-aware sul confine execute-API.
- **Sicurezza dipendenze**: `pip-audit` sulle dipendenze dirette pulito; floor di
  `aiohttp` alzato a `>=3.14.1` (CVE-2026-54274). Audit transitivo definitivo →
  in CI sull'immagine (Blocker 4).
- 749 test.

## [0.20.0] — Data layer robusto: WAL + migrazioni schema (Road to 1.0, Blocker 2) (2026-06-29)

Fondazione per la sicurezza dei dati negli aggiornamenti dell'addon. Nessun
cambiamento funzionale visibile; cambia come i DB SQLite vengono aperti e versionati.

- Nuovo helper condiviso `storage.connect()` / `storage.init_schema()`. Tutti i 7
  store (`chat`, `history`, `knowledge`, `vault`, `knowledge_db`, `proposals`,
  `memory`) ora aprono con: **WAL** (resilienza a crash/black-out + letture
  concorrenti mentre cattura/scheduler scrivono), **busy_timeout=5000** (niente
  "database is locked"), `synchronous=NORMAL`, `foreign_keys=ON`.
- **Versioning schema** via `PRAGMA user_version` + runner di migrazioni
  idempotente, con baseline degli store esistenti (nessuna perdita dati). Oggi
  tutti a versione 1; i prossimi cambi di schema avranno migrazioni sicure.
- 736 test (incl. WAL/migrazioni). Nessun vincolo FK negli schemi → `foreign_keys`
  è no-op oggi, pronto per il futuro.

## [0.19.0] — Apply reale proposte + hardening sicurezza semaforo (2026-06-29)

A valle di un audit di sicurezza adversariale sul semaforo (nessun bypass verso
domini giallo/rosso/off; l'enforcement server-side regge come backstop alla
prompt-injection):

- **Apply reale delle proposte**: attivare una proposta `ha_automation` ora **crea
  davvero** l'automazione in Home Assistant (config API + reload), prima il click
  "Attiva" marcava solo lo stato senza scrivere su HA. Resta **human-gated**
  (route `/api/proposals/.../apply` dietro auth UI, irraggiungibile da MCP) e
  scrive solo se HA accetta la config (altrimenti resta pending, ritentabile).
- **Hardening execute-API**:
  - `create_task`: **deny-by-default** sui tipi di action (solo
    call_ha_service/send_notification/create_task; tipi sconosciuti rifiutati alla
    creazione).
  - `call_ha_service`: **fail-closed** sui broadcast — con whitelist attiva una
    call senza entity target è bloccata (niente azioni a tappeto).
  - **Tetto hard server-side** dei tool execute-API: nessun tool fuori
    dall'allowlist (READ/PROPOSE/call_ha_service/create_task) è dispatchabile,
    anche se l'env `EXECUTE_API_TOOLS` lo elencasse.
- **Gateway**: `cancel_task` richiede **sempre** conferma umana, indipendente da
  `CONFIRM_ACTIONS` (evita la disattivazione silenziosa di task di sicurezza);
  `create_task` resta attivo come da scelta utente.
- 731 test HIRIS / 88 gateway. Richiede update addon HA a 0.19.0 + redeploy gateway.

## [0.18.0] — Lettura config automazioni + fix proposte/task via MCP (2026-06-29)

- Nuovo tool **get_automation_config**: legge la configurazione (YAML-equivalente)
  di un'automazione creata da UI in HA, così Claude/HIRIS può mostrarla e
  spiegarla. (Le automazioni scritte a mano in YAML non passano dall'API HA → errore chiaro.)
- **Fix via MCP**: i tool di proposta/pianificazione (create_automation_proposal,
  save_knowledge, list_tasks, create_task, cancel_task) erano nel catalogo del
  gateway ma non nell'allowlist execute-API di HIRIS → venivano respinti ("tool
  not exposed by policy"). Ora derive_execute_policy li espone (create_task/
  cancel_task restano gated dal semaforo del gateway).

## [0.17.1] — Fix: layout chat immune alla cache CSS stantia (2026-06-28)

- **Bugfix layout chat su desktop**: con una `hiris-chat.css` vecchia in cache del
  browser (precedente al drawer, v0.14.5) il div `#sidebar-overlay` — non più
  nascosto da quella CSS — occupava una cella della griglia `#app`, spingendo la
  sidebar nella colonna larga e la chat in una colonna stretta da 280px (sidebar
  in alto a tutta larghezza, chat compressa a sinistra).
- **Fix**: `style="display:none"` inline sugli overlay drawer (`#sidebar-overlay`
  in chat, `#sidenav-overlay` in config) → l'overlay non ruba mai una cella della
  griglia, **anche con CSS in cache vecchia**. Il JS lo imposta a `block`
  all'apertura del drawer, quindi il comportamento mobile è invariato.
- Diagnosi e fix verificati a video (riproduzione con CSS pre-drawer + immunità
  confermata a 1920px; drawer mobile 390px funzionante). NB: un hard-refresh
  (Ctrl+Shift+R) risolve comunque la vista corrente, essendo cache.

## [0.17.0] — Storico → second brain: digest notturno di insight (2026-06-28)

- Nuovo job notturno (04:00) che distilla lo storico (HistoryStore) in **insight
  testuali** salvati nel second brain (KnowledgeStore), ricercabili via
  recall_knowledge. Un riepilogo settimanale per entità storicizzata
  (media/ore attive + Δ% settimana-su-settimana), aggiornato (superseded) ogni notte.
- **Regole deterministiche, zero token** (nessuna chiamata LLM). Dati di
  presenza/sicurezza marcati sensitive (rispettano l'egress privacy del brain).
- Completa la Fase 3 dello storico (2a/2b/2c già in v0.16.0).

## [0.16.0] — Storico proprietario HIRIS: cattura + Storicizzazione + analisi a lungo termine (2026-06-27)

Completa lo **storico ibrido** (Fasi 2a/2b/2c): oltre a recorder+statistics di HA
(v0.15.0), HIRIS ora **conserva in proprio** lo storico delle entità che scegli,
anche oltre la retention di HA — base per analisi a lungo periodo via `get_history`.

- **`HistoryStore`** (SQLite locale): cattura eventi di stato, li compatta in
  **riepiloghi giornalieri permanenti** (numerici: min/max/media; on/off: durate e
  transizioni) e pota i grezzi oltre la retention. Timestamp normalizzati UTC,
  cattura crash-proof, chiusura pulita allo shutdown.
- **Cattura opt-in**: nuova pagina config **"Storicizzazione"** per scegliere cosa
  registrare (per categoria + entità extra/escluse + retention). **Default: nulla**
  viene storicizzato finché non abiliti tu — zero impatto su chi non la usa.
- **`get_history`** legge automaticamente lo store per le entità storicizzate
  (recorder/statistics per il resto), così Claude analizza trend di presenza,
  irrigazione, clima ecc. anche su mesi.
- **Compattazione notturna** schedulata (03:30) con retention dalla policy.
- API `/api/history/policy` protetta dai middleware auth/CSRF come il resto.
- Verificato a video (desktop 1440 + iPhone 390) prima del rilascio; 704 test verdi.

## [0.15.0] — Storico via MCP: get_history (recorder + statistics) (2026-06-27)

Nuova capability: **dati storici accessibili via MCP** e nella chat HIRIS.
Fase 1 dello storico ibrido (Fase 2 = HistoryStore proprietario + cattura + config
"Storicizzazione"; Fase 3 = digest verso il second brain).

- Nuovo tool **`get_history(entity_ids, days, resolution)`**: trend storici
  **compressi** (min/max/media) leggendo il **recorder HA** (recente) e le
  **Long-Term Statistics HA** (mesi, via WebSocket `recorder/statistics_during_period`),
  senza nuovo storage. Entità numeriche → `buckets` aggregati; entità on/off →
  `samples` downsamplati. Output uniforme `{id, source, resolution, unit, buckets|samples}`.
- Tier **READ** → fuori dal semaforo; con il fix v0.14.9 vede tutte le entità.
  Esposto sia a Claude/MCP (catalogo gateway) sia ai runner LLM della chat HIRIS.
- **Token-safe**: output sempre limitato (cap a 500 punti/bucket per entità con
  downsampling, aggregazione per giorno/ora). Cap input: ≤20 entità, ≤365 giorni.
- **Hardening**: validazione formato `entity_id` (`domain.object_id`) per evitare
  injection nei query param della history API; rifiuto di `days` booleano.
- Routing automatico: recente/raw → recorder; range lungo numerico → statistics;
  se le statistics mancano → fallback recorder con flag `partial` (mai troncamento
  silenzioso).

## [0.14.9] — Gateway: le letture non sono più filtrate dal semaforo azioni (2026-06-27)

**Bugfix.** Da Claude/MCP, chiedere stati di entità non controllabili (es. *"dammi
le temperature delle stanze"*) tornava **vuoto** appena una categoria del semaforo
era impostata a verde.

- **Causa**: `derive_execute_policy` deriva `allowed_entities` dai soli **domini
  azione verdi** (`light.*`, `climate.*`, …). Il dispatcher applicava quel
  whitelist **anche alle read tool** (`get_home_status`, `get_entity_states`),
  filtrando via tutto ciò che non era un dominio-azione verde — inclusi tutti i
  `sensor.*` (temperature). Con semaforo non configurato `allowed_entities` era
  `None` → nessun filtro, e le letture funzionavano.
- **Fix** (`handlers_execute.py`): le read tool del gateway ignorano
  `allowed_entities`/`allowed_services`; solo i tool che mutano stato portano il
  whitelist. Principio: **le azioni sono sotto semaforo, le entità si leggono
  sempre.** Letture non distruttive → nessun indebolimento della safety azioni.
- Test: nuovo `test_execute_read_bypasses_action_whitelist` +
  `test_execute_action_passes_whitelists` (era codificato il comportamento
  errato). 99 test gateway/security/tools verdi.

## [0.14.8] — Mobile config: editor agente senza overflow orizzontale (2026-06-27)

Verificato a video (render headless a viewport iPhone 390×844) **prima** della
pubblicazione: `scrollWidth` da 452 → 389 ≤ 390, `main` da 451 → 382, nessuno
scroll orizzontale.

- **Editor agente: fix overflow orizzontale** (≤768px). La colonna `1fr` del
  grid `.app-shell` cresceva al min-content del contenuto (`min-width:auto`)
  spingendo la larghezza a 452px. Aggiunto `min-width:0` su
  `main / .page-main / .editor-grid / .editor-content` per consentire lo shrink,
  più `.log-list { overflow-x:auto }` per i blocchi log lunghi.
- **Anchor-nav nascosta** su mobile (la barra àncore laterale non serve nel
  layout a colonna singola e contribuiva all'overflow).
- **Barra azioni sticky a tutta larghezza** (`left:0`) — prima era ancorata alla
  griglia desktop e finiva fuori viewport.

## [0.14.7] — Mobile config: sidebar a drawer + dashboard senza overflow (2026-06-27)

Verificato a video (render headless a viewport iPhone) **prima** della pubblicazione.

- **Config: sidebar → drawer a scomparsa** (≤768px). Il rail da 64px mangiava
  spazio; ora un hamburger nel chrome apre la sidebar come drawer (con overlay e
  label visibili), e il contenuto usa **tutta la larghezza**. Si chiude su tap
  voce/overlay. (Fix specificità: regole `!important` perché la media query
  precedeva la definizione base `.side-nav`.)
- **Dashboard: card template responsive** — erano forzate a `repeat(3,1fr)`
  inline → overflow orizzontale e sottotitolo tagliato su iPhone. Ora
  `auto-fit/minmax(150px)` → wrappano, niente scroll orizzontale.

## [0.14.6] — Mobile: header chat riprogettato (no sovrapposizioni) (2026-06-27)

- L'header della chat su mobile (≤720px) era affollato (logo + versione +
  sottotitolo + Nuova conv. + pill agente + Task + tema) → elementi
  sovrapposti. **Riprogettato minimale**: restano solo **☰ menu · HIRIS ·
  nuova conversazione (icona) · tema**. Logo/versione/sottotitolo/pill
  agente/Task **nascosti** (agenti, Configurazione e Task sono nel drawer).
  Padding con safe-area iOS.

## [0.14.5] — Mobile: menu a scomparsa + fix overflow Accessi Gateway (2026-06-27)

### Chat (mobile)

- **Hamburger ☰** nell'header HIRIS che apre la sidebar come **drawer a
  scomparsa** (con overlay): da iPhone in verticale ora si raggiungono la lista
  agenti e **Configurazione** (prima la sidebar era `display:none` e la config
  era irraggiungibile). Chiusura su tap agente/voce o overlay. Safe-area iOS.

### Accessi Gateway (mobile)

- Righe responsive: `flex-wrap` + controlli flessibili (niente più larghezze
  fisse 220/240px) → niente **scroll orizzontale** su iPhone. `select`/input a
  **44px** (target touch), label a 15px.

Solo front-end (HTML/CSS/JS), nessun cambiamento backend.

## [0.14.4] — Semaforo operativo: flusso Giallo/Rosso (notifica + approvazione) (2026-06-27)

Il comportamento dei livelli del semaforo, **solo sul percorso del gateway**
(Claude); chat HIRIS e agenti restano diretti.

### Flusso approvazione

- L'execute-API instrada `call_ha_service` per **tier**: 🟢 esegue subito ·
  🟡 trattiene + **notifica azionabile** (Approva/Nega) sull'iPhone ·
  🔴 trattiene + notifica informativa (conferma solo in HIRIS).
- Store comandi-in-sospeso (`gateway_pending.json`): **nonce monouso + scadenza
  5 min**, esecuzione vincolata al singolo comando approvato (whitelist scoped).
- `ha_client`: sottoscrive `mobile_app_notification_action` → il bottone
  "Approva" sull'iPhone esegue il comando (mappa azione→nonce).
- Endpoint `/api/gateway/pending` (list/approve/reject) + sezione
  **"Approvazioni in attesa"** nella pagina Accessi Gateway.
- **Servizio notifica configurabile** (default `notify.iphone_bet`) dalla pagina.

### Test

- `tests/test_gateway_pending.py` (nonce monouso, scadenza, approva/rifiuta,
  evento iPhone) + routing tier in `test_execute_api.py`. Suite: 647 passati.

## [0.14.3] — Semaforo categorie + conteggi + provenienza (2026-06-27)

### Accessi Gateway

- **Semaforo a 4 livelli** per categoria: Off / 🟢 Verde / 🟡 Giallo / 🔴 Rosso
  (Giallo/Rosso configurabili; il flusso notifica si attiva nel prossimo update).
- **Categorie complete** (22: luci, scene, script, clima, tapparelle, media,
  interruttori, ventilazione, aspirapolvere, umidificatori, scaldabagno, valvole,
  sirene, tagliaerba, selettori, numeri, pulsanti, interruttori virtuali,
  automazioni, telecomandi, serrature, allarme).
- **Conteggio dispositivi** per categoria dalla cache entità (`EntityCache.
  domain_counts()`); le categorie senza dispositivi sono attenuate.
- Dicitura chat "Configura agenti" → **"Configurazione"**.

### Provenienza

- L'execute-API registra l'**origine** (`origin` → `agent_id`, validato) di ogni
  chiamata: gateway/Claude vs chat HIRIS vs agente schedulato.

### Test

- `tests/test_gateway_policy.py`, `tests/test_execute_api.py`. Suite verde.

## [0.14.2] — Pagina "Accessi Gateway" (permessi a categorie) (2026-06-26)

Nuova sezione nell'interfaccia `/config` per scegliere **a click** cosa il
gateway MCP (Claude) puo' comandare, per **categoria** (Luci, Climatizzazione,
Scene…), al posto del CSV nelle opzioni dell'add-on.

### UI

- Voce di menu **"Accessi Gateway"** + rotta `#/gateway` + pagina dedicata:
  ogni categoria con scelta **🟢 Verde / Off**, salvataggio, nomi leggibili.
- Branding `Agent Designer` → **Configurazione**; larghezza contenuto
  `/config` 1140 → 1440px.

### Backend

- `GET/POST /api/gateway/policy` + persistenza `/data/gateway_policy.json`.
- La policy UI deriva l'`execute_policy` (categoria Verde → `dominio.*`
  eseguibile) e **sovrascrive il CSV** delle opzioni; caricata all'avvio e
  aggiornata al salvataggio (mutazione in place, no deprecation aiohttp).
- v1: livelli Verde/Off; 🟡 Giallo / 🔴 Rosso (notifica/conferma) in arrivo.

### Test

- `tests/test_gateway_policy.py` (derivazione, persistenza, endpoint). Suite: 635 passati.

## [0.14.1] — Hardening auth per esposizione a tunnel (CR-1 + CSRF) (2026-06-26)

Preparazione sicura all'accesso dell'execute-API da un secondo host (gateway MCP
su .31) via tunnel cifrato, senza esporre la porta sulla LAN e senza rompere i
consumer esistenti (card custom + proxy Retro Panel).

### Sicurezza

- **CR-1 (X-Ingress-Path spoofing) chiuso.** `internal_auth_middleware` ora
  concede il bypass-ingress solo se `X-Ingress-Path` è presente **E** l'IP
  sorgente è in una CIDR Supervisor fidata (nuova opzione
  `supervisor_ingress_cidr`, default `172.30.32.0/23`). Prima bastava il
  formato dell'header: chiunque raggiungesse la porta poteva falsificarlo e
  bypassare `internal_token` su tutta la API. Stesso pattern già in produzione
  in Retro Panel.
- **Esenzione CSRF per client server-to-server.** `csrf_middleware` ora esenta
  le richieste con un `X-HIRIS-Internal-Token` valido (non sono un vettore CSRF
  browser). Sblocca i `POST/PUT` autenticati col token del gateway MCP e del
  proxy Retro Panel senza `X-Requested-With`.
- **Execute-API coerente.** `/api/execute` valida `X-HIRIS-Internal-Token`
  (header HIRIS-nativo) invece di `Authorization: Bearer`, mantenendo il check
  indipendente come difesa-in-profondità (resta sicuro anche se l'ingress fosse
  falsificato).

### Test

- Nuovi test CR-1 (ingress da IP non fidato non bypassa; token sempre valido),
  esenzione CSRF (token valido/non valido), header execute-API. Suite: 627 passati.

## [0.14.0] — Execute-API per il gateway MCP (2026-06-26)

Aggiunta una piccola **execute-API non-LLM** che permette al gateway MCP
(app separata su .31) di pilotare tool HIRIS curati a IA = zero. HIRIS resta
l'unico punto di enforcement: rivalida ogni chiamata, il gateway non può
ampliare i privilegi.

### Nuovo endpoint

- `POST /api/execute` — gated da `internal_token` (confronto timing-safe
  `hmac.compare_digest`, fail-closed se il token non è impostato). Applica una
  **allowlist server-side** dei tool eseguibili (vuota = nessuno) e le whitelist
  `allowed_entities` / `allowed_services`, poi chiama `ToolDispatcher.dispatch`
  (`cloud=True`). Valida il body JSON e la forma di `tool`/`input`.
- `app["execute_policy"]` e `app["tool_dispatcher"]` esposti su `create_app`.

### Configurazione addon

- Nuove opzioni `execute_api_tools` / `execute_api_entities` /
  `execute_api_services` (CSV) + schema + export in `run.sh` + label IT/EN.
- Versione `0.13.0` → `0.14.0`.

### Test

- `tests/test_execute_api.py`: 9 casi (auth, allowlist 403, pass-through
  whitelist, fail-closed, JSON/input non validi). Suite completa: 623 passati.

## [0.10.15] — Fix HTTP 401 nella Lovelace card (ingress session) (2026-05-08)

User: "Errore: HTTP 401" sulla custom card dopo l'aggiornamento. Diagnosi:
le rotte `/api/hassio_ingress/<token>/...` non sono autenticate dal Bearer
token utente — richiedono il cookie `ingress_session` creato da
`POST /api/hassio/ingress/session`. Il riavvio del container al deploy di
v0.10.14 ha invalidato la sessione esistente nel browser → 401 finché l'utente
non riapriva il pannello sidebar dell'addon.

### Card fix

- `_ensureIngressSession(hass)`: helper module-level che chiama
  `hass.callApi('POST', 'hassio/ingress/session')` con cache 4 minuti
  (stesso intervallo del refresh che fa HA frontend). Coalesce su singolo
  in-flight per evitare race su mount multiplo.
- `_hirisFetch(hass, url, opts)`: wrapper attorno a `fetch()` che chiama
  `_ensureIngressSession()` prima della call e, su 401, force-refresh della
  sessione + retry una volta. `credentials: 'same-origin'` esplicito così il
  browser invia sempre il cookie ingress.
- Sostituite le 4 fetch ingress (`_fetchStatus`, `_sendMessage`,
  `_toggleAgent`, editor `_loadAgents`) col wrapper.
- `connectedCallback` + primo `set hass()` triggerano subito la creazione
  sessione, così la prima POST/GET dopo un restart parte autenticata.
- Visibility change da hidden→visible → force-refresh sessione (cookie può
  scadere mentre la tab è in background).

### Default attivo dopo restart

- `set hass()`: lo switch HA viene letto solo se in stato definito
  (`'on'`/`'off'`). `'unavailable'`/`'unknown'`/missing → `_enabled = true`
  ottimistico, così l'utente non deve mai abilitare manualmente l'agente
  dopo un restart dell'addon. Backend già parte con `enabled=True` di
  default, ora la UI riflette quell'intento esplicitamente.

## [0.10.14] — Lovelace card overhaul: persistence, markdown, switch (2026-05-08)

User: "prendiamo la card Lovelace, fai un'analisi front end UI UX se è
migliorabile" → audit con 19 punti → "fai la 10.14 fixando tutto".

`hiris-chat-card.js` riscrittura sostanziale (custom element + editor):

### High

- **Storia chat persistente** (H1): conversazione salvata in `localStorage`
  per `(slug, agent_id)`, retention max 60 messaggi. Sopravvive a refresh
  dashboard / mount/unmount card. Nuovo bottone "↺ pulisci conversazione".
- **Polling visibility-aware** (H2): listener `visibilitychange` sospende
  il polling 30s quando la tab è hidden, riprende su visible con refresh
  immediato. Risparmia quote API (specie OpenRouter `:free`).
- **Toggle come switch HA-style** (H3): track + thumb, `role="switch"` +
  `aria-checked`. Sostituisce le emoji 🟢/⚪ poco discoverable.
- **Budget bar threshold colors** (H4): verde fino 50%, accent fino 80%,
  ambra 80-94%, rosso ≥95%. Percentuale numerica leggibile.
- **Markdown rendering safe** (H5): `**bold**`, `*italic*`, `` `code` ``,
  newlines preservati. Parser su testo già escapato → nessuna XSS surface.
- **Accessibility** (H6): `role="log" aria-live="polite"` su area messaggi,
  `aria-label` su bottoni icon-only (toggle, send, copy, regen, clear),
  `role="meter"` con `aria-valuemin/max/now` su budget, `aria-hidden` su
  SVG decorative, `aria-label` su tutti i field dell'editor.

### Medium

- **Composer textarea auto-grow** (M1): da `<input>` a `<textarea>` che
  cresce 1→6 righe. Enter invia, Shift+Enter (o Cmd/Ctrl/Alt) nuova riga.
- **Avatar grouping** (M2): l'icona HIRIS appare solo sul primo bubble
  della raffica assistant — riduce visual noise nelle risposte multi-blocco.
- **Messages height responsive** (M3): da `220px` fisso a `max-height: 60vh`
  con `min-height: 180px`. Override via config `height: <css>`.
- **Quick replies onboarding** (M4): nuovo campo `suggestions: [...]`
  configurabile (max 6) → chip cliccabili nello stato vuoto. Stub
  predefinito con 3 prompt italiani.
- **Toggle undo snackbar** (M5): optimistic UI + snackbar 5s con "Annulla"
  per ripristinare lo stato precedente. Niente più click accidentali
  irrecuperabili.
- **Copy / Regenerate** (M6): hover su bubble assistant mostra "📋 copia"
  e "🔄 rigenera" che ri-invia il prompt utente corrispondente.
- **Stato di errore visibile sui bubble** (M6 bonus): assistant bubble con
  testo errore ottiene background rosso tinted + border, vs prima testo
  generico nello stesso stile dei messaggi normali.

### Low / Cosmetic

- **Font Google caricato 1 volta** (L1): module-level injection su
  `document.head`, deduplicato via `data-hiris-font` flag. Era replicato
  in HirisCard + Editor.
- **Stylesheet montato 1 volta** (L2): `<style>` mosso da `_render()` a
  `connectedCallback()` — niente più re-parse del CSS ad ogni token SSE.
- **Unconfigured copy** (L3): "Apri il menu della card (… in alto a destra)
  e seleziona Modifica" invece di "Clicca ✏️" (non sempre visibile mobile).
- **Mobile portrait <360px** (L4): nasconde title nel header, padding
  ridotto su composer + header.
- **Status pill labels italiano** (L5): `idle → pronto`, `running → in
  esecuzione`, `error → errore`, `unavailable → offline` (era misto IT/EN).
- **SVG send con `aria-hidden`** (L6): decorative, non viene letto da SR.
- **Editor: nuovi field "Suggerimenti iniziali" + "Altezza area chat"**.

### Tooling

- `.smoke-test/card-mockup.html`: pagina HTML standalone con 4 stati
  della card (light/dark × empty/populated/disabled/error) per validazione
  visiva senza HA. Utile per regression test rapidi senza rebuild addon.

### Files toccati

- `hiris/config.yaml`: bump `0.10.14`
- `hiris/app/static/hiris-chat-card.js`: refactor completo (~1100 LOC)
- `hiris/app/static/config/agent-editor.js`: V6_CACHE_BUST `0.10.14`
- `.smoke-test/card-mockup.html`: dev tool

---

## [0.10.13] — Audit UX: status visibility, label/typo cleanup (2026-05-08)

User: "Se apri la tab agenti capisci subito quali sono attivi?" → audit
completo grafico app reale + "Chiudi tutti i bug segnalati".

### Critical / High

- **Log status mismatch** (`agent_engine.py:925`): agente che riceve
  "Errore temporaneo del servizio AI…" (string return su `APIError`) veniva
  loggato con `success=True`. Aggiunto check upstream-error che marca il
  record come fail (✗ rosso invece di ✓ verde nei log dashboard + editor).
- **Sidebar badge "0"**: `nav-tasks-count` / `nav-proposals-count` ora si
  nascondono quando count=0 (classe `.is-empty` in `hiris-config.css`,
  toggle in `main.js` + `tasks-route.js`). Niente più "Task 0" che fa
  pensare a tab vuota.
- **Lista agenti** (già v0.10.12): badge `● Attivo / ○ Disabilitato /
  ⏸ in pausa`, opacity 0.55 sui disabled, sort attivi-prima, summary chips.
- **Consumi per agente**: `/api/agents` ora include `usage` per-agent
  (`requests / input_tokens / output_tokens / cost_eur / last_run`) letto
  dal runner — fixa "0 run · 0 tok" su tutti gli agenti.
- **Dashboard typo**: `disabilitatoi` → `disabilitati` (plurale italiano).
- **"Vai alla chat" unstyled**: `btn-ghost` → `btn` (ora ha border
  visibile come secondary action accanto al primary "+ Nuovo agente").
- **"P2" label** in tile "Prossimi trigger" → "presto" + descrizione
  user-friendly invece di reference roadmap interna.

### Medium

- **Consumi page**: stesso pattern badge della lista agenti (Attivo /
  Disabilitato / pausa) applicato anche al breakdown per-agente, con sort.
- **Btn-danger sul reset contatori globali** (era neutro).
- **Proposals tab**: count inline "In attesa N / Archivio N" visibile.
- **Tasks row dedupe**: `agentName · label` mostra label solo se diversa
  dal nome agente (era "Monitor energia · Monitor energia").
- **Drawer Notifica**: aggiunto campo `Destinatario` (es. notify.mobile_app_*
  per HA push, vuoto = URLs Apprise globali) — prima la action `notify`
  non aveva modo di specificare target nel drawer UI.

### Files toccati

- `hiris/config.yaml`: bump `0.10.13`
- `hiris/app/agent_engine.py`: success-flag fix per upstream-error string
- `hiris/app/api/handlers_agents.py`: include `usage` payload nel response
- `hiris/app/static/config/agent-editor.js`: V6_CACHE_BUST `0.10.13`
- `hiris/app/static/config/dashboard.js`: typo, btn-ghost→btn, P2→presto
- `hiris/app/static/config/main.js`: nav badge `.is-empty` toggle
- `hiris/app/static/config/usage-route.js`: badge stato + btn-danger + sort
- `hiris/app/static/config/proposals-route.js`: count nei tab
- `hiris/app/static/config/tasks-route.js`: dedupe label + nav-badge empty
- `hiris/app/static/config/script-action.js`: campo Destinatario su notify
- `hiris/app/static/hiris-config.css`: `.nav-badge.is-empty`

---

## [0.10.12] — Lista agenti: badge stato esplicito (2026-05-08)

User: "Se apri la tab agenti capisci subito quali sono attivi?" → no.
Dot 8x8px quasi invisibile, nessun badge testuale, no row dimming, no toggle.

- `agents-list.js`: badge esplicito `● Attivo / ○ Disabilitato / ⏸ in pausa`,
  opacity 0.55 sui disabled, sort attivi-prima, summary chips count.
- `hiris-config.css`: stili `.agent-badge`, `.agents-summary .chip`, grid
  4-column su `.dl-row.agent-row`.

---

## [0.10.11] — Debug expose port toggle (per testing esterno) (2026-05-07)

User: "Possiamo inserire una modalità DEBUG attivabile dal config che
espone la porta? Se la disattivo la porta viene chiusa".

Aggiunto toggle UI per esporre temporaneamente la porta 8099 sulla LAN per
sessioni di sviluppo / diagnostica esterna (es. Playwright headless da host
esterno, curl da workstation, debug da remoto).

### Implementazione

- `config.yaml`:
  - `ports: {"8099/tcp": null}` — port mappable da HA UI (default null = non
    esposta). User imposta `8099` come host port nella sezione Network di
    HA Settings → Add-ons → HIRIS → Configuration.
  - `ports_description`: spiegazione inline visibile in HA UI sezione Network.
  - Nuova opzione `debug_expose_port: false` (toggle) + schema `bool`.
- `run.sh`: legge `debug_expose_port`, se `true` logga warning multilinea ad
  ogni avvio addon con istruzioni complete (set port mapping + risk note).
- `translations/{it,en}.yaml`: nome opzione `🛠 Debug — esposizione porta
  (DEV ONLY)` + descrizione completa con warning sicurezza.

### UX flow

**Per attivare debug** (utente):
1. Settings → Add-ons → HIRIS → Configuration
2. Scroll a `🛠 Debug — esposizione porta` → toggle ON
3. Sezione **Network** sotto → imposta `8099/tcp` = `8099`
4. Save → Restart addon
5. Verifica: `curl http://<ha-host-ip>:8099/config.html` ritorna 200

**Per disattivare** (post-debug):
1. Toggle OFF
2. Sezione Network → svuota campo `8099/tcp`
3. Save → Restart

### Sicurezza

Esponendo la porta in HTTP plain (no HTTPS), chiunque sulla LAN può chiamare
`/api/*`. L'unica barriera è `internal_token` se settato. Default off + log
warning chiaro + descrizione UI esplicita evitano misuse.

### Test

- pytest 562/562 passed
- Schema yaml validato (HA Hass.io schema validator)

## [0.10.10] — Trigger UI fixes (2026-05-07)

User report 4 bug nella sezione Trigger:
1. **Periodico**: input number con arrows native non in linea col design
2. **Cambio stato entità**: campo stringa free-text — utente vuole autocomplete
3. **Cron**: chip "Ogni giorno alle 06:00" appare ma non cliccabile/modificabile
4. **Manuale**: option mai implementata, da rimuovere

### Fix

1. **Periodico CSS** (`hiris-config.css`): `.nt-num-input` rimuove arrows
   native via `appearance: textfield` + `::-webkit-inner/outer-spin-button`.
   Width 80px center-aligned. Range `min=1 max=1440` (24h).
2. **Cambio stato entità autocomplete** (`agent-editor.js populateIdentita`
   + `rewireLegacyAfterMount`): input ora ha dropdown suggestions sotto.
   Pattern stesso di permessi.js entity-search ma scope locale.
   Fetch `api/entities?q=` con debounce 250ms, max 30 risultati.
   Click suggestion fill input. Outside-click + ESC chiudono.
   CSS `.nt-entity-suggestions` con max-height + scroll.
3. **Cron chip diagnostic** (`cron-popover.js`): aggiunto console.log su
   click + try/catch + alert se `HirisPopover` undefined o errore.
   Future debug istantaneo. Se persiste in v0.10.10 → user vede output
   console + alert con causa.
4. **Manuale rimosso**: `<option value="manual">` eliminato dal select
   `#new-trigger-type`. Triggers esistenti con `type='manual'` non
   vengono toccati lato backend.

### Test

- pytest 562/562 passed
- node -c syntax OK

Bump 0.10.9 → 0.10.10 + V6_CACHE_BUST sync.

## [0.10.9] — Frontend runAgent timeout 90s → 600s (2026-05-07)

User console v0.10.8: `[v6] runAgent error: AbortError: signal is aborted
without reason at agent-editor.js:692:46`. Test Run su agente IRRIGAZIONE
con modello locale gemma4:e4b abortiva al frontend dopo 90s.

### Root cause

`window.runAgent` aveva hardcoded `setTimeout(ctrl.abort, 90000)` (90s)
ma backend è configurato per timeout molto più lunghi:
- `_AGENT_RUN_TIMEOUT` fallback su `OLLAMA_REQUEST_TIMEOUT * 1.2` (v0.10.4)
- User `local_model.request_timeout=600` o `800` → backend permette 720-960s
- Frontend cuttava a 90s anche se backend lavorava → AbortError visibile

### Fix

- `FRONTEND_RUN_TIMEOUT_MS = 600000` (10 min) — allineato al backend.
- Banner "attendere fino a 10 minuti" (era 90s).
- Timeout error message aggiornato con suggerimento debug (Ollama logs).

### Test

- pytest 562/562 passed
- node -c syntax OK

Bump 0.10.8 → 0.10.9 + V6_CACHE_BUST sync.

## [0.10.8] — Test Run feedback visivo + sidebar/sticky-bar redesign (2026-05-07)

Due richieste user combinate in unica release:

1. Test Run "logga in console l'avvio ma 1) nessuna evidenza del test in
   corso 2) la sezione test non si compila 3) posso premere N volte il
   pulsante 4) non sono certo il test venga lanciato".

2. Sidebar footer "non esteticamente corretto": rimuovi voce duplicata
   "Vai alla chat" + icona luna sbagliata. Sposta link Chat in cima
   (sotto HIRIS, sopra Configurazione). Stringi sticky bar simmetrica
   alla parte centrale del page-main: Annulla a sinistra, TestRun/
   Elimina/Salva a destra.

### Root cause (systematic debugging Phase 1)

CSS spinner usava selector legacy `#run-btn`:
```css
#run-btn.running .spinner { display: inline-block; }
```
Ma in v6 il bottone è `#btn-test-run`. Lo spinner non veniva MAI mostrato →
zero feedback visivo. User vedeva solo log console + nessuna animazione →
impressione di "non funziona" → click multipli.

Inoltre `runAgent` non scrollava alla sezione Test Run, quindi l'output
appariva sotto il viewport user (sezione 08, dopo Log esecuzioni in 07).

### Fix

1. **CSS spinner**: regole estese a `#btn-test-run` (oltre `#run-btn` legacy):
   - `.running` → opacity ridotta + cursor not-allowed + **pointer-events:none**
     (impedisce nativamente click multipli)
   - `.spinner` visibile via `inline-block` quando `.running` aggiunto
   - Border-color usa `currentColor` (funziona su qualsiasi tema/colore bottone)

2. **Banner "Test Run in corso"**: nuovo atom CSS `.run-running-banner`
   con icon spinner + testo "Test Run in corso… l'agente sta elaborando,
   attendere fino a 90s." Inserito in cima a `sc-body-run` quando user clicca.
   Il banner viene rimosso a fine esecuzione (success/error/timeout).

3. **JS `window.runAgent`**:
   - Flag `_runInFlight` globale → previene esecuzione doppia anche se click
     handler logga prima del check (race condition).
   - Bottone label cambia in `⏱ In esecuzione…` (visivamente diverso dal
     `▶ Test Run` di base).
   - `requestAnimationFrame` + `scrollIntoView({behavior:'smooth',block:'start'})`
     IMMEDIATO → user vede subito il banner + section Test Run.
   - Console.log esteso (`fetch starting`, `response status=N`, `done`/`error`)
     per debug futuro.
   - Gestione errori: response con `data.error` colorata `run-error-text`,
     prefisso `✗`. Success colorato `✓ ESEGUITO` in verde.
   - `cleanupRunning()` reset stato bottone in TUTTI i path
     (success/error/timeout) — niente più bottone bloccato in stato running.
   - Pre/post output: `<pre>` ora ha sfondo + padding + min-height 60px →
     visibile anche con output vuoto/errore.

### Sidebar redesign

- **Chat link in cima**: voce nav `<a href="./">` con icona speech-bubble,
  inserita SOTTO il brand HIRIS, SOPRA il label "Configurazione".
- **Rimossa voce duplicata in fondo**: vecchia "Vai alla chat" con icona luna
  (sbagliata, era theme toggle icon) eliminata. Niente più nav-spacer.
- **Niente più sezione "Sistema"** vuota (la voce Settings era stata già
  rimossa in v0.10.5).

### Sticky bar redesign — wrap pattern + simmetria

- **Outer `.sticky-actions-wrap`**: position fixed bottom, full-width da
  sidebar a viewport-right. Background blur + border-top → la "barra"
  visiva continua per tutta la larghezza.
- **Inner `.sticky-actions`**: `max-width: var(--shell-content-max)` (1140px)
  + `margin: 0 auto` → contenuto centrato simmetricamente alla `.editor-content`.
- **Layout interno**:
  ```
  [Annulla]  ........spacer.........  [▶ Test Run] [Elimina] [Salva]
  ```
- **Rimosso "Salvato ✓" / "Modifiche non salvate" status text** dalla bar.
  Lo stato dirty/saved è ora indicato dal solo pulsante Salva (`disabled` =
  saved, enabled = pending). Pattern Stripe/Linear: visivamente più pulito,
  meno rumore. `setupStickyActions` aggiornato (`var status` rimosso, guard
  `if (btnSave)` aggiunto).

### Test

- pytest 562/562 passed
- node -c syntax OK

Bump 0.10.7 → 0.10.8 + V6_CACHE_BUST sync.

## [0.10.7] — Route #/tasks per Task pianificati (2026-05-07)

User feedback: "in tutto questo aggiornamento/restyle dove sono finiti i task?"

Gap del v6 redesign: i Task pianificati esistono in chat (`index.html`
sidebar "Task pianificati") + backend (`handlers_tasks.py` + `task_engine.py`)
ma il designer v6 (`config.html`) **non aveva alcuna route** per loro.
Mea culpa nel design doc originale.

### Implementato

- **Voce side-nav "Task"** con icon clock + badge `nav-tasks-count` (count
  task pending), inserita sotto "Consumi" prima del nav-spacer.
- **Route `#/tasks`** mount via `HirisTasksRoute.mount()`:
  - 5 filter chip: tutti / ⏱ in attesa / ✓ eseguiti / ✗ falliti / ⊘ cancellati
    con counter dinamici aggiornati ad ogni render.
  - Lista task: time created / status / agent name / label / trigger summary.
  - Click row → expand inline (pattern log-row v6, accordion).
  - Detail mostra: meta-chip trigger/actions/executed-at/error/parent-task,
    block result (preformattato) se presente, bottone "⊘ Cancella" SOLO per
    task pending, bottone "{} copia raw JSON" sempre.
  - Refresh on demand (↻ aggiorna).
  - Sort: pending+failed prima, poi by created_at desc.
- **Side-nav badge sync**: `nav-tasks-count` aggiornato anche dopo cancel
  (no full reload necessario).

### Backend

- **Zero modifiche**. Endpoints esistenti (`api/tasks` GET con filtri,
  `api/tasks/:id` GET single, `api/tasks/:id` DELETE cancel) usati as-is.

### File

- **Nuovo**: `hiris/app/static/config/tasks-route.js` (~210 LOC)
- **Modificati**: `config.html` (nav voice + script include), `main.js`
  (route handler + nav active 'tasks' + badge fetch), `agent-editor.js`
  (V6_CACHE_BUST 0.10.6 → 0.10.7), `config.yaml` (version bump)

### Test

- pytest 562/562 passed
- node -c syntax OK

## [0.10.6] — Hotfix regressione cleanup v0.10.5 (2026-05-07)

User report v0.10.5 console: due regressioni introdotte dal cleanup.

### Bug 1: `ReferenceError: renderList is not defined`

`agent-form.js openAgent()` linea 142 chiamava ancora `renderList()` ma la
funzione era stata rimossa dal cleanup v0.10.5 (target #agent-list shim
invisibile). Il banner errore "Step openAgent failed" appariva all'apertura
di ogni agente.

**Fix:** rimossa anche la call `renderList()` da openAgent. Commento aggiunto
per spiegare che la lista agenti è ora gestita da agents-list.js sulla
route #/agents.

### Bug 2: `TypeError: Cannot set properties of null (setting 'value')` in `_setModelValue`

`api.js _setModelValue()` (linea 48) faceva `sel.value = val` senza null
guard. Quando `loadModels()` fetch async era in flight e l'utente cambiava
route, `#f-model` veniva rimosso dal DOM e `sel` diventava null al callback.

**Fix:** added `if (!sel) return` guards in `_setModelValue` e all'inizio
di `loadModels`. La function diventa no-op se l'editor non è montato.

### Test

- pytest 562/562 passed
- node -c syntax OK

Bump 0.10.5 → 0.10.6 + V6_CACHE_BUST sync.

## [0.10.5] — Drawer/popover loading + anchor nav + sidebar count + settings + sticky align (2026-05-07)

User feedback su v0.10.4 + console output. Audit systematic-debugging ha
trovato **bug critico mai notato**: drawer.js e popover.js NON ERANO MAI
CARICATI dalla v0.10.0 in poi. Spiegava perché +Aggiungi azione e cron chip
popover non funzionavano.

### Bug critici fixati

1. **`drawer.js` + `popover.js` mai caricati** (CRITICAL, presente fin da v0.10.0)
   - `config.html` non aveva i `<script>` static per questi atom
   - `agent-editor.js LEGACY_SCRIPTS` aveva solo `cron-popover.js`, NON
     i base atom `popover.js` né `drawer.js`
   - Conseguenza: `HirisDrawer` e `HirisPopover` erano `undefined`
   - **+Aggiungi azione** non apriva nulla (script-action.js HirisActionDrawer.open fallisce silently)
   - **Cron chip click** non apriva il popover preset (cron-popover.js HirisPopover.open fallisce)
   - Bug mai catturato perché test browser-based di Phase 3 testavano i moduli isolati ma nessun test integration end-to-end ne ha verificato il caricamento globale
   - **Fix**: aggiunti `<script src="static/config/drawer.js">` e
     `<script src="static/config/popover.js">` in config.html PRIMA di
     agent-editor.js

2. **Anchor nav causa router warnings + service worker errors + remount loop**
   - Click `<a class="anchor-link" href="#sec-X">` cambiava URL hash
   - Browser fires `hashchange` → router.resolveRoute → no route match per `#sec-X` → console.warn
   - HA Ingress service worker prova a fetch `config#sec-X` → 404 → "Uncaught (in promise) Object"
   - Quando user navigava back → remount agent-editor → invalidava reference a `#run-output` → output Test Run non appariva
   - **Fix**: `setupAnchorNav` ora intercetta click anchor con `e.preventDefault()` + `scrollIntoView({behavior:'smooth'})`. Hash invariato, nessun service worker hit, no remount.

3. **Sidebar "Agenti" badge "—" invece del count**
   - main.js mountChrome usava `loadAgents()` (in agent-form.js, legacy)
   - Legacy modules sono caricati solo quando user apre l'editor → al boot `loadAgents` undefined → typeof check skip → badge resta "—"
   - **Fix**: fetch diretto `api/agents` in mountChrome, popola badge + HirisState + window.agents global

4. **Settings menu placeholder "Implementata in Phase 11" confondeva**
   - **Fix**: rimosso voce nav "Impostazioni" da config.html. Re-aggiungeremo quando avrà contenuto reale.

5. **Sticky-actions bar misaligned**
   - v0.10.4 fix usava `left: var(--shell-sidebar-w); right: 0` che spannava la bar da sidebar-edge a viewport-right-edge ignorando il max-width centrato del page-main (1140px)
   - **Fix**: padding-left/right calcolato dinamicamente per allineare il contenuto della bar al page-main centrato.

### Test Run output

Bug Test Run "non si popola" è probabilmente effetto collaterale del **remount loop** causato dall'anchor nav (#3 sopra). Risolto il remount, `out` reference resta valida durante l'intera vita del fetch → output appare.

Se persiste in v0.10.5, il diagnostic logging in console.log `[v6] TestRun clicked, ...` mostra runAgent=function — andremo a debug interno della funzione.

### Dead code cleanup (eseguito in v0.10.5)

- **`tabs.js` ELIMINATO** (~50 LOC): file mai più caricato dopo Phase 4 v6 long-form. Conteneva `switchTab`, `resetToFirstTab`, theme toggle duplicato, version footer fetcher.
- **`agent-form.js` ridotto 333 → 211 LOC** (-122): rimossi handler IIFE `#new-btn`/`#save-btn`/`#delete-btn`/`#run-btn` (erano shimmati a div invisibili, sostituiti da `window.saveAgent`/`runAgent`/`deleteAgent` in agent-editor.js + `initNewAgent` path), rimossa funzione `renderList` (target `#agent-list` shim), rimossa querySelector `#agent-tabs .tab-btn` (markup tab orizzontale rimosso in v6). `loadAgents` resta ma non chiama più `renderList`. `showAgentMode` ora target `#sec-azioni` v6 invece del `#tab-azioni` legacy.
- **`logs.js` ridotto 87 → 60 LOC** (-27): rimossi `toggleLogRow` e click delegate su `#log-body` per `.log-expand-btn`/`.log-thinking-btn` (classi non esistono in v6 — `HirisLogRow.render` produce markup `.log-row`/`.lr-collapsed`/`.lr-detail` con click handler proprio). Rimossi IIFE listener `input` su `#f-strategic`/`#f-prompt` (gestiti ora da `rewireLegacyAfterMount`). Funzioni `updateTokenCounter` e `loadContextPreview` ora null-safe.
- **`addLegacyShims` ridotto da 11 a 5 ID stub** (`no-selection`, `form`, `form-title`, `delete-btn`, `usage-reset-btn`). Rimossi `new-btn`/`save-btn`/`run-btn`/`agent-list`/`agent-tabs`/`tab-azioni` perché i loro consumatori legacy sono stati eliminati.
- **Visibility `btn-delete` per default agents**: aggiornato `agent-editor.js mount()` post-resolveAgent per nascondere il pulsante Elimina su agenti default (es. HIRIS, `is_default=true`).

### Pending v0.10.6+ (se servono)

- `api/scripts` endpoint backend (script picker oggi vuoto, fallback input text)
- Field UI per `fallback_action` e `allowed_endpoints` (orphan in dataclass) — o rimozione dal backend

### Test

- pytest 562/562 passed
- node -c syntax OK su tutti i file modificati

## [0.10.4] — 300s timeout + sticky bar + theme toggle + chat redundant badge (2026-05-07)

User segnala 5 categorie bug. Audit deep ha individuato root cause per ognuno
+ extra dead code. Fix mirati:

### 1. **Bug critico — 300s timeout sui modelli locali ignorato** (HIGH)

User imposta `local_model.request_timeout` a 600 → 800s in HA addon ma riceve
sempre "Timeout dopo 300s — il modello non ha risposto in tempo".

**Root cause** (`hiris/app/agent_engine.py:20`):
```python
_AGENT_RUN_TIMEOUT = int(os.environ.get("AGENT_RUN_TIMEOUT", "300"))
```
La env var `AGENT_RUN_TIMEOUT` è **mai esportata in `run.sh`** → cade sempre
sul default 300. La user setting `local_model.request_timeout` viene
correttamente esportata come `OLLAMA_REQUEST_TIMEOUT` (usata dall'OpenAI SDK
client) ma **non viene letta dal wrapper outer `asyncio.wait_for`**, che cuttava
sempre a 300s anche se il modello locale completava in 500s.

**Fix:** `_AGENT_RUN_TIMEOUT` ora cade su `OLLAMA_REQUEST_TIMEOUT × 1.2` (con
floor 300s) quando `AGENT_RUN_TIMEOUT` non è esplicitamente settata. User che
imposta `local_model.request_timeout=800` ora ha `_AGENT_RUN_TIMEOUT=960`
(800 × 1.2). Margin 20% garantisce che il client SDK timeout scatti per
primo (errore localizzato) invece dell'asyncio wrapper outer (errore generico).

### 2. **Sticky-actions bar layout broken**

CSS bug: `.sticky-actions { position: sticky; bottom: 0; margin: ... -X -X -X }`
dentro `.editor-content` con `align-items:start` causava posizionamento
sbagliato + flicker.

**Fix:** `position: fixed` con `left: var(--shell-sidebar-w)` allinea la bar
alla sidebar v6 (responsive a viewport). `padding-bottom: 80px` su
`.editor-content` previene che la bar copra l'ultima section-card.

### 3. **Log row ANCORA esploso** (defense-in-depth)

Audit conferma codice CSS corretto v0.10.3 — il problema era cache stale.
Ora belt-and-suspenders triplo:
- `.lr-detail { display: none !important }` (CSS)
- `.log-row.expanded .lr-detail { display: flex !important }` (CSS specifico)
- `<div class="lr-detail" style="display:none">` inline (log-row.js)

Anche con cache stale di v0.10.2, il pattern `display:none` inline sul
container resta. La nuova regola `!important + .expanded .lr-detail` sblocca
solo quando expanded.

### 4. **Theme toggle "quadrato" + FOUC** (designer + chat)

- **Designer**: nuovo atom `.btn-icon-only` (36px circolare, transparent,
  hover background). Template `tpl-page-chrome` ora usa questo invece di
  `.btn .btn-ghost`. Icone partono `style="visibility:hidden"` invece di
  `display:none` — `paint()` setta `visibility: visible/hidden` per la icona
  giusta, eliminando FOUC.
- **Chat**: `#theme-toggle` da `border-radius: var(--r-sm)` (quadrato) a
  `border-radius: 50%` (circolare), no border default, hover state coerente
  con designer.

### 5. **Chat — badge "connesso" ridondante**

`#agent-pill` mostrava già il pallino verde "live" indicando connessione.
Il `#conn-dot` con testo "connesso" duplicava info → rumore visivo.

**Fix:** `#conn-dot { display: none }` di default. La classe `.offline` lo
rivela come error chip. Quindi il badge appare SOLO quando offline, mentre
in stato normale (happy path) la connessione è indicata implicitamente
dall'avatar verde dell'agent-pill.

### 6. **Breadcrumb mostra ID invece di nome agente** (cosmetico)

`agent-editor.js mount()` aggiorna ora `chrome-here` con `'Agenti / ' + agent.name`
dopo che `resolveAgent` carica l'oggetto. Il bare ID rimane fallback solo
durante il caricamento iniziale di pochi ms.

### 7. **Audit dead code (info, fix in v0.10.5+)**

Identificato:
- `tabs.js` mai più caricato — pronto per cancellazione
- `agent-form.js` IIFE handlers `#save-btn`/`#delete-btn`/`#run-btn`/`#new-btn` —
  shimmati ma puntano a div invisibili → dead. setupStickyActions chiama
  saveAgent/runAgent/deleteAgent globali che è il path live.
- `agent-form.js` `renderList` — `#agent-list` è shim → dead path.
- `logs.js` `toggleLogRow` + click delegate su `.log-expand-btn` — quelle
  classi non esistono in v6, dead.
- `api/scripts` endpoint **non implementato backend** — `script-action.js`
  fa fetch e fallisce silenziosamente. Picker script vuoto.
- 2 campi Agent dataclass orphan: `fallback_action`, `allowed_endpoints` —
  esistono backend, no UI.

Cleanup pianificato per v0.10.5+ insieme a `api/scripts` decision.

### Test

- pytest 562/562 passed
- node -c syntax OK su tutti i file modificati
- Backend agent_engine.py modifica: prima volta che tocchiamo backend in v6
  redesign. Solo 1 cambio (calcolo default `_AGENT_RUN_TIMEOUT`),
  retro-compat completa (env var override prevale).

### User action

Hard reload browser (Ctrl+Shift+R) post-update per forzare fetch CSS/JS
freschi. Da v0.10.4 il client-side cache-bust più aggressivo previene la
ricomparsa.

## [0.10.3] — Log row collapse di default + diagnostic buttons (2026-05-07)

Due bug user reportati:
1. Sezione log dell'editor appariva ESPLOSA con tutti i dettagli visibili
   invece di compatta + apribile su click.
2. Pulsanti Test Run, Salva, Elimina sembravano non funzionare.

### Fix bug 1 — Log row collapse default

CSS bug in hiris-config.css: `.lr-detail` era `display: flex` di default
invece di `display: none`. La classe `.log-row.expanded` aggiungeva solo
gli stili visivi accent ma il dettaglio era sempre visibile.

### Causa root

Il CSS atom `.lr-detail` (in `hiris-config.css` riga 1593) era `display: flex`
di default invece di `display: none`. La classe `.log-row.expanded` aggiungeva
solo gli stili visivi accent (border + box-shadow) ma il dettaglio era già
visibile, quindi tutti i log apparivano espansi all'apertura.

### Fix

```css
.lr-detail {
  display: none;             /* nascosto di default */
}
.log-row.expanded .lr-detail {
  display: flex;             /* visibile solo quando il row è espanso */
  margin-top, padding-top, border-top, animation… (immutati)
}
```

Click sulla riga aggiunge `.expanded` (logica già in log-row.js) → detail
diventa visibile con animazione slideIn. Click su altra riga collapse la
prima e espande la seconda (accordion). ESC chiude.

### Fix bug 2 — Diagnostic logging pulsanti sticky-actions

Code review statico ha confermato che `window.saveAgent`/`runAgent`/
`deleteAgent` sono correttamente definiti dentro l'IIFE di `agent-editor.js`
(prima della chiusura). I click handler in `setupStickyActions` chiamano
`if (typeof saveAgent === 'function') saveAgent()` che dovrebbe risolvere via
window. Tuttavia user reports che i pulsanti "non funzionano" — diagnosi
necessaria run-time.

Aggiunto **diagnostic console.log** in OGNI click handler:
- Save: logga agentId, typeof saveAgent, typeof buildPayload, return value, promise resolve/reject
- Test Run: logga typeof runAgent, currentId, errori try/catch
- Delete: logga typeof deleteAgent, errori try/catch

Se la funzione globale non è definita, alert + console.warn istruisce su
hard reload (cache stale). Se la funzione throw, alert con messaggio.

Aprendo DevTools console (F12) e cliccando un pulsante, l'output dirà
ESATTAMENTE cosa fallisce: typeof check, throw nella funzione, fetch failure,
ecc. Future debug saranno immediati.

Bump version 0.10.2 → 0.10.3 + V6_CACHE_BUST sync.

## [0.10.2] — Defensive guards + cache-bust + chat link fix (2026-05-07)

User segnala che v0.10.1 aveva ancora il banner "Errore caricamento editor:
Cannot read properties of null (reading 'style')" e un nuovo bug: il bottone
"Vai alla chat" usciva dall'iframe Ingress di Home Assistant.

### Diagnosi

Audit statico ha confermato che il codice v0.10.1 è clean: tutti gli `.style`
access nei moduli legacy puntano a ID coperti dallo shim oppure creati dai
populate*() di agent-editor.js. Il TypeError persistente è quasi certamente
**browser cache stale**: il tablet HA serviva ancora `agent-editor.js` v0.10.0
(senza `addLegacyShims`) anche dopo l'update dell'addon a v0.10.1.

Causa root: la cache-bust HIRIS (`_inject_version` che appende `?v=VERSION`)
agisce solo sui `<script>` del HTML response. Gli script caricati DINAMICAMENTE
da `agent-editor.js loadScript()` (templates, cron, triggers, agent-form, ecc)
NON ricevevano il cache-bust → browser caching aggressivo li manteneva alla
versione precedente.

### Fix

- **Cache-bust client-side** in `agent-editor.js loadScript()`: appende
  `?v=V6_CACHE_BUST` a OGNI dynamic-loaded script. La costante è hardcoded
  in `agent-editor.js` (top) e va bumpata ad ogni release. Forza re-fetch
  sicuro anche con caching aggressivo.
- **Diagnostic logging step-by-step** in `mount()`: ogni passo (clear outlet,
  clone template, populate*, addLegacyShims, ensureLegacy, populateTemplateSelector,
  loadModels, rewireLegacyAfterMount, setupStickyActions, openAgent) è wrapped
  in `step(name, fn)` che logga su console.error il nome dello step se throw,
  e il banner errore mostra "Step: <stepName> · v0.10.2" + suggerimento hard
  reload. Future debug saranno immediati.
- **Null guards difensivi** in `agent-form.js` openAgent + new-btn handler +
  save-btn/delete-btn/run-btn IIFE binding: TUTTI i `getElementById(...).style`
  e `.addEventListener` ora protetti con `var x = getElementById(...); if (x)`.
  Belt-and-suspenders: anche con cache stale, l'app degrada gracefully invece
  di throware.
- **Chat link `target="_top"` rimosso** da side-nav (config.html) e dashboard
  (dashboard.js): il link "Vai alla chat" navigava la TOP frame causando
  uscita dall'iframe Ingress di HA. Senza target, naviga nell'iframe → resta
  in HA.

### Test

- pytest 562/562 passed
- node -c syntax OK su agent-editor.js, agent-form.js, dashboard.js

### User action

Per chi era su v0.10.1 con cache stale: dopo update a v0.10.2 fare hard reload
del browser (Ctrl+Shift+R su PC, clear cache via Settings su tablet) per
forzare fetch del nuovo agent-editor.js. Da v0.10.2 in poi, il cache-bust
client-side previene la ricomparsa del problema.

## [0.10.1] — Hotfix wiring legacy↔v6 (2026-05-07)

Fix comprehensive di **9 bug** di disconnessione tra il long-form v6 e i moduli
legacy (templates, triggers, permessi, action-editor, logs, usage, agent-form):

### Bug fixed

1. **Crash apertura agente** (Cannot read properties of null reading 'style'):
   `agent-form.js openAgent()` accedeva a ID legacy non più presenti
   (`#no-selection`, `#form`, `#form-title`, `#delete-btn`, `#agent-list`,
   `#agent-tabs`, `#tab-azioni`). + `agent-editor.js` passava string id
   invece di agent object.
2. **Templates dropdown vuota**: `populateTemplateSelector()` non veniva
   mai chiamato dal v6 boot (era nel vecchio `main.js` rimosso).
3. **Trigger type switch non funziona**: listener `change` su
   `#new-trigger-type` bound IIFE-time alla prima istanza del nodo, stale
   ad ogni successivo mount perché populate ricrea l'innerHTML del sc-body.
4. **Form si congela al 2° open editor**: stesso pattern del bug 3 affetta
   tutti i 23 listener IIFE-time (triggers, permessi domain pills, entity
   search, f-type/f-action-mode/f-model/f-states change, token counter,
   usage budget buttons).
5. **Save/TestRun/Delete sticky-actions inerti**: `agent-form.js:245` faceva
   `getElementById('save-btn').addEventListener` ma v6 usa `#btn-save`
   → TypeError → IIFE crashava prima di registrare anche `run-btn` /
   `delete-btn`. setupStickyActions cercava `saveAgent`/`runAgent`/
   `deleteAgent` come globali che non venivano definite.
6. **Crash IIFE su `#usage-reset-btn`**: `usage.js:74` setava `.onclick`
   su id legacy global rimosso in v6 → TypeError.
7. **Crash IIFE su `#run-btn`**: stesso pattern, v6 usa `#btn-test-run`.
8. **Path "Nuovo agente" form vuoto**: la sequenza di reset (clear fields,
   `_triggersLoad([])`, `_entitySelectorLoad([])`, `_actionsLoad([])`,
   `buildToolChecks([])`, `buildActionChecks([])`, `_buildTriggerOnChecks`,
   `showAgentMode('agent')`, ecc) era nel `#new-btn` IIFE handler, mai
   chiamato in v6.
9. **Model dropdown vuota**: `loadModels()` non veniva mai chiamato.

### Fix (tutti in `agent-editor.js`)

- **`addLegacyShims` esteso** con `save-btn`, `run-btn`, `usage-reset-btn`
  per evitare TypeError IIFE.
- **`rewireLegacyAfterMount()`**: rebinda via `.onchange/.onclick/.oninput`
  i 23 listener IIFE-time sui nodi v6 attuali ad ogni mount.
- **`populateTemplateSelector()` + `loadModels()`** chiamati dopo
  `ensureLegacy()` (idempotenti, OK al re-mount).
- **`initNewAgent()`** replica la sequenza di reset del vecchio `#new-btn`
  IIFE handler quando `mount(null)`.
- **Globali `window.saveAgent` / `runAgent` / `deleteAgent`** definite in
  agent-editor.js (riusano `buildPayload()` da agent-form.js) — sticky-actions
  callback ora collegate a logica reale.
- **`resolveAgent(agentId)`**: id → agent object via HirisState cache o
  fetch `api/agents`, popola anche `window.agents` per renderList() legacy.

### Test

- pytest 562/562 passed (zero regressioni backend)
- node -c syntax OK su agent-editor.js (733 LOC, +400 vs v0.10.0)

## [0.10.0] — Agent Designer v6 redesign (2026-05-07)

Refactor completo della pagina `config.html` (Agent Designer) come applicazione
multi-route con long-form editor.

### Highlights

- **Multi-route hash router** (`#/`, `#/agents`, `#/agents/:id`, `#/proposals`,
  `#/usage`, `#/settings`) — deep-link supportato, navigazione naturale.
- **Long-form editor** — i 6 tab orizzontali sostituiti da 9 section-card
  scrollabili con anchor nav a destra (IntersectionObserver active state) e
  sticky save bar in fondo.
- **Log row v6** — click ovunque sulla riga espande inline (accordion, una sola
  aperta), mid-truncation per testo lungo, filter chips
  (tutti / ok / err / thinking), copia summary + copia raw JSON, ESC chiude.
- **Action editor in drawer** — il builder azioni esce dall'inline e si apre
  come drawer da destra full-height.
- **Nuovo tipo azione "▶ Esegui script HA"** — wrapper friendly su
  `call_service domain=script` con script picker + variables JSON.
- **Cron chip + popover** — i 5 select inline diventano un chip
  `Ogni giorno alle 06:00` che apre un popover con 6 preset
  (orario/mattino/sera/lunedì/weekend/custom).
- **Dashboard adaptive** — stato vuoto = onboarding + template gallery, stato
  popolato = 4 stat tile + log cross-agent + proposte peek + prossimi trigger.
- **Proposte automazione** — terminologia allineata: badge `→ automazione HA`,
  buttons `Attiva` / `Rifiuta`, una proposta attivata genera una automation HA
  nativa (semantica esistente, ora chiara nella UI).

### Internal

- 13 nuovi moduli JS in `hiris/app/static/config/`: `state.js`, `router.js`,
  `dashboard.js`, `agent-editor.js`, `agents-list.js`, `log-row.js`,
  `drawer.js`, `popover.js`, `script-action.js`, `cron-popover.js`,
  `proposals-route.js`, `usage-route.js`.
- Token v6 additivi in `hiris-theme.css` (spacing scale 4-base, typography
  ramp, layout dims, elevations). Zero rinomine v5.
- Atom CSS v6 in `hiris-config.css`: `.app-shell`, `.section-card`,
  `.anchor-nav`, `.sticky-actions`, `.drawer`, `.popover`, `.log-row`, ecc.
- Translations IT+EN: ~50 nuove chiavi sotto namespace `designer.*`.
- Test browser-based in `tests/static/test_*.html` per moduli JS chiave
  (state, router, drawer, popover, log-row).
- Backend Python: zero modifiche. Suite 562/562 passed invariata.
- Chat surface (`index.html`, `hiris-chat-card.js`): zero impatto.

### Migration

- Nessuna migration richiesta. Schema agent invariato.
- URL `config.html` → ridireziona a `#/`. Bookmark `#/proposals` etc. valido.
- Action `script` salvata come `call_service domain=script`, retro-compat completa.

### Removed

- File backup `config.legacy.html` (era temporaneo per consultazione).
- Regole CSS legacy obsolete (`.tab-btn`, `.agent-tabs`).

### Reference

- Design doc: `docs/superpowers/specs/2026-05-07-hiris-agent-designer-v6-design.md`
- Implementation plan: `docs/superpowers/plans/2026-05-07-hiris-agent-designer-v6.md`

## [0.9.10] — 2026-05-05

### Added — Gestione consapevole modelli OpenRouter `:free`

OpenRouter è il provider HIRIS dedicato all'uso gratuito. I modelli `:free`
hanno però quote giornaliere basse (specialmente con account a $0 di
credito) e vengono routinariamente rate-limited dai provider upstream
(Venice, Together, ecc.). v0.9.10 introduce tre meccanismi per non
bruciare quota e per dare visibilità all'utente:

- **Badge `• free` nel dropdown modelli** (`static/config/api.js`): ogni
  modello con suffisso `:free` viene mostrato con marker visibile + tooltip
  *"quota giornaliera bassa e rate-limit upstream frequenti, sconsigliato
  per agenti schedulati"*.
- **Warning bloccante al save di agente autonomo su `:free`**
  (`handlers_agents._validate_free_model_for_agent_type`): `POST/PUT
  /api/agents` rifiuta con HTTP 400 se `agent.type == "agent"` e
  `agent.model.endswith(":free")`. L'utente può accettare il rischio
  ripetendo il save con `confirm_free_for_agent: true` nel payload. Chat
  agent su `:free` restano consentiti senza attriti (uso a basso volume).
- **Backoff automatico per agente su rate-limit ripetuti**
  (`agent_engine`): nuovo `_record_rate_limit_failure()` /
  `_is_in_rate_limit_pause()`. Quando un agente schedulato riceve
  `AGENT_RATE_LIMIT_THRESHOLD=3` risposte rate-limited entro
  `AGENT_RATE_LIMIT_WINDOW_SEC=600s`, viene messo in **cooldown** per
  `AGENT_RATE_LIMIT_COOLDOWN_SEC=3600s`. Le esecuzioni schedulate durante
  il cooldown vengono saltate (no chiamata al runner) e logged.
- **Toggle "Nascondi modelli :free di OpenRouter"** in *Settings →
  Add-ons → HIRIS → Configurazione*, posizionato subito sotto la chiave
  OpenRouter. Quando attivo, i `:free` non compaiono affatto nel dropdown
  modelli. Implementato come `hide_free_models: bool` in `config.yaml`,
  esportato come `HIRIS_HIDE_FREE_MODELS` da `run.sh`. Stessa env var
  resta disponibile per chi preferisce gestirla via shell.
- **UI checkbox "accetto rischi free-tier"** nel Designer agente
  (`config.html` + `agent-form.js`): nel tab Modello compare un checkbox
  visibile solo quando `type=agent` E `model` termina con `:free`. Quando
  spuntato il save include `confirm_free_for_agent: true` bypassando il
  warning server-side. Caricamento di agente esistente con `:free` →
  pre-checkato (perché il save passato è andato a buon fine).

### Added — Configurazione timeout Ollama da addon UI
- Nuovo campo `local_model.request_timeout` (int, default 120, range
  10–1800) in `config.yaml` schema/options. `run.sh` lo esporta come
  `OLLAMA_REQUEST_TIMEOUT` letto da `OpenAICompatRunner`. Compare
  automaticamente in *Settings → Add-ons → HIRIS → Configurazione*. Utile
  per hardware lento (Pi 5 con `gemma2:9b` in genere richiede 240–300s
  contro il default 120). Translations IT/EN aggiornate.

### Test
- Suite: 543 + 19 nuovi = 562 test, tutti pass.
- Fix #11 e #12 sono modifiche solo a UI/config addon (no logica Python
  nuova) → nessun test aggiunto, copertura esistente sufficiente.

## [0.9.9] — 2026-05-05

### Fixed — Tre buchi residui dopo v0.9.8 (validazione, history, UX errori)

v0.9.8 ha fermato la creazione di nuovi turni "tossici" ma:
- la **chat history già salvata** prima dell'upgrade continuava a essere
  rispedita al modello ad ogni turno → degradazione persistente,
- gli **agenti già configurati** con `nousresearch/hermes-3-llama-3.1-405b:free`
  continuavano a fallire con HTTP 404 finché l'utente non cambiava modello,
- gli errori `429 rate-limited upstream` dei modelli OpenRouter `:free` si
  presentavano come opaco "Errore temporaneo del servizio AI" senza
  istruzioni utili.

#### Fix
- **`chat_store.load_history()`**: filtra automaticamente i messaggi assistant
  tossici (tool-call leakate via pattern `<id><non-ASCII>`, errori sintetici
  noti, prefissi credit-exhausted / tool-leak). Quando un assistant è
  scartato anche il suo user immediatamente precedente viene rimosso, per
  non lasciare turni orfani senza risposta. **Nessuna azione richiesta agli
  utenti**: chat esistenti si auto-puliscono al prossimo caricamento.
- **`PUT/POST /api/agents`**: nuovo `is_openrouter_model_tool_capable()` in
  `handlers_models.py` consulta il campo `supported_parameters` di
  OpenRouter. Se il modello non supporta i tool, il save viene rifiutato
  con HTTP 400 e un messaggio che spiega perché e suggerisce alternative.
  Modelli non-OpenRouter (Claude/OpenAI/Ollama) non triggherano nessuna
  chiamata di rete extra.
- **`handlers_chat.py`**: dopo `runner.chat()` / streaming, se la response
  matcha il filtro tossico, NON viene persistita in chat_store (né user
  né assistant). Future turni non ereditano più storia degradata.
- **`OpenAICompatRunner`**: nuovo `parse_upstream_rate_limit()` traduce
  `qwen/...:free is temporarily rate-limited upstream` in messaggio
  italiano azionabile (suggerisce retry, modello a pagamento, o aggiunta
  API key del provider su openrouter.ai).

### Test
- Suite: 521 + 22 nuovi = 543 test, tutti pass.

## [0.9.8] — 2026-05-05

### Fixed — OpenRouter quality regressions (multi-causa)
Quattro bug indipendenti emersi insieme su agenti chat con OpenRouter
(`mistralai/mistral-large` e modelli `:free`) causavano risposte degradate
o incoerenti turno dopo turno. Tutti corretti in un singolo release.

- **Tool-call leakati come testo** (CRITICO): alcuni provider routati da
  OpenRouter (Mistral, Hermes) non traducono i token speciali nativi del
  modello (es. `[TOOL_CALLS]`) nello schema OpenAI `tool_calls`. La risposta
  arrivava come `content` testuale del tipo `get_ha_healthיׂ{"sections":["all"]}`
  e veniva persistita pari pari in chat history, inquinando il prompt dei
  turni successivi (il modello vedeva la propria robaccia e degradava
  ulteriormente). Fix: nuovo helper `detect_leaked_tool_call()` in
  `OpenAICompatRunner` rileva il pattern `<tool_name><non-ASCII>` e — se il
  nome combacia con un tool effettivamente disponibile — sostituisce la
  risposta con un messaggio chiaro all'utente (cambia modello / disattiva
  tool). Stesso check anche in `chat_stream` con evento SSE
  `discard_collected` per pulire i token già renderizzati nella Lovelace
  card. 8 test regressivi.
- **Mojibake nel context casa**: `proxy/semantic_context_map.py` conteneva
  letterali doppio-encodati (UTF-8 bytes letti come CP1252 e ri-encodati
  come UTF-8): `Umidità` → `UmiditÃ\xa0`, `·` → `Â·`, `°` → `Â°`,
  `→` → `â†→`, `—` → `â€—`, `₂` → `â‚‚`, `×` → `Ã—`. 22 sostituzioni
  applicate. Il context era visibile direttamente nel system prompt di
  ogni turno e degradava le risposte. 3 test di regressione che vietano
  marker mojibake nelle label `ENTITY_TYPE_SCHEMA`, nei concept
  `CONCEPT_TO_TYPES` e nell'output di `get_context()`.
- **Modelli OpenRouter senza tool support nei suggeriti**: il preset
  includeva `nousresearch/hermes-3-llama-3.1-405b:free` che fallisce con
  HTTP 404 `"No endpoints found that support tool use"` su ogni chiamata.
  Fix: `_fetch_openrouter_models` ora filtra usando il campo
  `supported_parameters` di OpenRouter (`tools` o `function_calling`).
  Il preset hermes-3 è stato rimosso. Nuovo file
  `tests/test_handlers_models_openrouter.py` con 8 test.
- **`max_tokens=4096` rigido vs credito OpenRouter limitato**:
  l'errore HTTP 402 `"can only afford 3907"` si propagava come
  `"Errore temporaneo del servizio AI"` opaco. Fix: nuovo
  `parse_afford_limit()` estrae il limite affrontabile dal messaggio,
  e `chat()` / `chat_stream()` riprovano una volta con `max_tokens`
  clampato (-5% safety). Se anche il retry fallisce, errore esplicito
  che indica all'utente di abbassare `max_tokens` dell'agente o
  aggiungere credito.

### Test
- Suite: 496 + 25 nuovi = 521 test, tutti pass.

## [0.9.7] — 2026-05-05

### Fixed (regression hotfix)
- **TypeError su agent non-Claude**: agent autonomi configurati su modelli
  Ollama / OpenAI / OpenRouter crashavano con `TypeError:
  OpenAICompatRunner.chat() got an unexpected keyword argument
  'thinking_budget'` al primo trigger. Regressione introdotta in v0.9.5
  quando il parametro `thinking_budget` è stato aggiunto a `ClaudeRunner`
  per Anthropic Extended Thinking; `LLMRouter` forward `**kwargs` a tutti i
  runner ma `OpenAICompatRunner` non aveva il parametro nella firma.
  Fix: `OpenAICompatRunner.chat`/`chat_stream`/`run_with_actions` ora
  accettano `thinking_budget: int = 0` come parametro silentemente
  ignorato (non esiste un equivalente nell'API OpenAI-compatible).
  `OpenRouterRunner` eredita da `OpenAICompatRunner` → fix automatica.
- 3 test regressivi aggiunti in `test_openai_compat_runner.py`.

## [0.9.6] — 2026-05-05

### Added — OpenRouter provider
- Nuovo backend **OpenRouter** (`hiris/app/backends/openrouter_runner.py`)
  come quarto provider HIRIS, accanto a Claude / OpenAI / Ollama.
  OpenRouter ([openrouter.ai](https://openrouter.ai/)) è un proxy unificato
  che dà accesso a 200+ modelli con una sola API key, inclusi modelli
  gratuiti marcati `:free` (Llama 3.3 70B, Gemma 3 27B, Qwen 2.5 72B,
  DeepSeek Chat, Mistral Nemo, Hermes 3 405B).
- Configurazione: nuovo campo `openrouter_api_key` nelle opzioni dell'addon
  (`config.yaml` + `run.sh` + `translations/{en,it}.yaml`).
- Routing: il prefix `openrouter:` o `openrouter/` davanti al model name
  (es. `openrouter:meta-llama/llama-3.3-70b-instruct:free`) instrada a
  OpenRouter via `LLMRouter`. Strategy chain aggiornata a
  `claude > openai > openrouter > ollama` (balanced/quality_first) e
  `ollama > openrouter > openai > claude` (cost_first).
- `/api/models` espone la lista live dei modelli OpenRouter disponibili
  con preset curati (12 modelli più richiesti) + tutti i `:free` aggiuntivi.

### Fixed — Ollama hang con modelli reasoning (Gemma 4, Qwen QwQ, DeepSeek R1...)
- Bug: agent autonomi configurati su modelli Ollama con thinking-by-default
  timeoutavano dopo 300s con 0/0 token e nessun log diagnostico — il modello
  restava bloccato emettendo solo blocchi `thinking` mentre `content` restava
  vuoto, fino a quando httpx 120s + 2 retry SDK (~360s) superavano il wrapper
  `agent_engine` 300s.
- Fix: tre interventi in `OpenAICompatRunner` quando `fixed_model` (Ollama):
  1. `extra_body={"think": False}` passato via OpenAI SDK a tutte le chiamate
     (`chat`, `chat_stream`, `simple_chat`). I modelli senza thinking lo
     ignorano, quelli con thinking lo disattivano.
  2. `max_retries=0` sul AsyncOpenAI client per Ollama (default SDK = 2).
     Il primo errore/timeout viene loggato e ritornato invece di hang × 2.
     Cloud OpenAI mantiene il retry default (rete cloud più affidabile).
  3. Logging info pre/post chiamata Ollama (model, iter, agent, tools,
     msg_chars, finish_reason, content_len, tool_calls). Per future indagini.

### Added — Documentazione privacy
- Nuova sezione **"Provider AI e privacy"** in `docs/guida-configurazione.md`
  e `docs/configuration-guide.md`, con:
  - Tabella decisione "quale provider scegliere" per use case
  - Tabella privacy per provider (cosa esce di casa, giurisdizione, costo,
    link policy) per Claude / OpenAI / OpenRouter / Ollama
  - Definizione di "cosa intende HIRIS per messages" per chat vs agent autonomi
  - Lista esplicita di "cosa NON esce mai" per nessun provider
- Disclaimer privacy aggiunto alle descrizioni dei campi cloud nelle
  translations IT/EN: l'utente vede in UI HA addon il dettaglio "i dati
  passano da X (giurisdizione Y) — vedi policy Z".

### Tests
- 4 nuovi test in `test_openai_compat_runner.py` (max_retries 0/2,
  extra_body presence/absence per Ollama vs OpenAI cloud)
- 6 nuovi test in `test_llm_router.py` (routing prefix colon/slash,
  Claude precedence, strategy chain, prefix strip helper, runner init)
- Suite ora 493/493 pass

## [0.9.5] — 2026-05-05

### Added
- **Extended Thinking** support per agente. Nuovo campo `thinking_budget`
  sull'Agent (default 0 = disabilitato). Quando >0 e il modello e'
  thinking-capable (sonnet-4.5+/opus-4+) il runner passa
  `thinking={"type":"enabled","budget_tokens":N}` a `messages.create`.
  - I thinking blocks vengono catturati dal runner e salvati in
    `execution_log[].thinking_blocks` (troncati a 2000 char/block).
  - Designer UI: nuovo `<select>` Extended Thinking budget con preset
    0 / 2048 / 4096 / 8192 / 16384.
  - Execution log UI: chip pill `💭 thinking` accanto a ogni row con
    blocchi presenti; click apre un pannello mono con il chain-of-thought
    numerato per step.
  - Validation difensiva (handlers + runner): blocca budget < 1024 o
    >= max_tokens, ignora silenziosamente su modelli non capable invece
    di fallire con un 400 Anthropic.
  - Chat handler include `debug.thinking_blocks[]` nella response JSON
    quando thinking e' attivo (consumabile dal client per debug).

### Changed (perf)
- **Prompt cache reorder** in `claude_runner.chat()`: i prompt di
  comportamento (`RESTRICT_PROMPT`, `REQUIRE_CONFIRMATION_PROMPT`,
  `response_mode` prompts) ora precedono il `context_str` query-dependent.
  Anthropic richiede cache contigue dall'inizio: prima questi blocchi
  cadevano *dopo* il context_str non-cached e venivano riemessi fresh.
  Ora il cache breakpoint si estende a includerli (cumulativo). Risparmio
  tipico: ~250 input token aggiuntivi cached per richiesta su agenti con
  `restrict_to_home` + `response_mode='compact'`.

### Tests
- 14 nuovi test (4 dataclass `thinking_budget`, 10 runner
  `_build_thinking_param` + integration). Suite ora 483 pass.

## [0.9.4] — 2026-05-05

### Fixed (security)
- **CVE-2026-34450** + **CVE-2026-34452**: bump floor `anthropic` da
  `>=0.55.0` a `>=0.87.0`. I due CVE affettano il "Local Filesystem
  Memory Tool" della SDK anthropic nelle versioni 0.55-0.86:
  - CVE-2026-34450 (file permissions 0o666 → leak state agente)
  - CVE-2026-34452 (path validation race → sandbox escape via symlink)

  HIRIS non usa `client.beta.memory.*` (il nostro `memory_tool` è un
  MemoryStore SQLite custom indipendente dall'SDK), quindi non eravamo
  direttamente vulnerabili. Tuttavia il range `>=0.55,<1.0` permetteva
  l'installazione di SDK con la feature vulnerabile presente. Floor
  alzato per igiene security.

## [0.9.3] — 2026-05-04

### Fixed (security)
- **CVE-2026-22815, 34513-34520, 34525**: bump `aiohttp` da `>=3.10.11` a
  `>=3.13.4`. Chiude 10 CVE pubblicati il 2026-04-01: trailer DoS,
  DNS cache DoS, CRLF injection multipart, Windows UNC SSRF/NTLMv2 leak,
  multipart bypass DoS, multipart memory DoS, cookie/proxy-auth leak su
  cross-origin redirect, response splitting, null byte/control char in
  response headers, duplicate Host headers.
- **CVE-2026-28684**: bump `python-dotenv` da `==1.0.1` a `>=1.1.0`.
  Chiude vulnerabilità Link Following.

### Changed (deps refresh)
- `anthropic` da `==0.40.0` (pinned, 57 release indietro) a
  `>=0.55.0,<1.0.0`. Le API in uso (`AsyncAnthropic`, `messages.create`,
  `APIStatusError`) sono stabili da 0.30+, no breaking attesi.
- `apscheduler` da `==3.10.4` a `>=3.11.0,<4.0.0` (3.x stable, 4.x ancora alpha).
- `pytest` da `==8.3.2` a `>=9.0.0,<10.0.0`.
- `pytest-asyncio` da `==0.23.8` a `>=1.0.0,<2.0.0`. La suite usa già
  `@pytest.mark.asyncio` esplicito su ogni test → strict mode 1.x compat.
- `pytest-aiohttp` da `==1.0.5` a `>=1.1.0,<2.0.0`.
- `openai` da `>=1.0.0` (range troppo ampio) a `>=2.0.0,<3.0.0`. API in
  uso (`AsyncOpenAI` con api_key/base_url/timeout) invariata tra 1.x e 2.x.
- `httpx` da `>=0.27.0` a `>=0.28.0,<1.0.0`.

### Removed (dead deps)
- `aiohttp-cors` rimosso dai requirements: era pinned a `==0.7.0` ma mai
  importato dal codice (zero match grep su `aiohttp_cors` / `aiohttp.cors`
  in `hiris/app/`).

### Improved
- `Dockerfile` cache buster aggiornato da `"HIRIS v0.6.12"` (stantio dalle
  release 0.7→0.9.2) a `"HIRIS v0.9.3 — full deps refresh"`. Forza il
  rebuild del layer pip install nel container HA Supervisor in modo che
  le nuove versioni vengano effettivamente installate.

### Verified
- Suite di test 469/469 pass su environment locale che gira già le
  versioni target (aiohttp 3.13.3, openai 2.33.0, httpx 0.28.1,
  pytest 9.0.2, pytest-asyncio 1.3.0).

## [0.9.2] — 2026-05-04

### Fixed (security)
- **SEC-022** `trigger_automation` / `toggle_automation` ora rispettano
  `allowed_services` e `allowed_entities` per agente. Prima un agente con
  whitelist limitata (es. `light.*`) poteva firare qualsiasi automation HA.
- **SEC-022b** `automation_id` validato contro injection: regex `^[a-z0-9_]+$`
  prima di costruire `entity_id` per call_service.
- **SEC-023** Middleware auth interno non si fida più della sola presenza
  dell'header `X-Ingress-Path`: ora valida il pattern reale di HA Supervisor
  (`/api/hassio_ingress/<token>/...`).
- **SEC-024** `SemanticContextMap` ora sanitizza `friendly_name`, `state`,
  `hvac_mode`, `media_title`, area name, e knowledge_db annotations da HA
  prima di iniettarle nel system prompt della chat (prima il filtro era
  applicato solo agli agent autonomi → vector di prompt-injection persistente).
- **SEC-025** Nuovo CSRF middleware globale: richiede `X-Requested-With` su
  POST/PUT/DELETE `/api/*`. Tutti i fetch client lato HIRIS lo inviano.
- `tools/http_tools.py` non logga più la query string dell'URL (token leak).

### Fixed (bug)
- **F-CRIT-1** Task DELETE usa path relativo `api/tasks/...` invece di assoluto
  `/api/tasks/...` (sotto HA Ingress il path assoluto faceva 404).
- **F-CRIT-2** Onboarding: tipi agent allineati a backend (`chat`/`agent`),
  payload `triggers` (plurale) corretto invece di `trigger`. Prima i Monitor
  preset venivano creati senza alcun trigger schedulato.
- **F-ALTO-1** Race condition in `setActiveAgent`: switching rapido tra agenti
  prima del completamento della fetch history non popola più la chat sbagliata.
- `agent_engine.delete_agent` ora pulisce `memory_store` e chat history
  associati (no più dati orfani in `/data/hiris_memory.db` e `/data/chat_history.db`).
- Locking thread-safe per `_save()` JSON in `agent_engine`, `task_engine`,
  `health_monitor`, `semantic_context_map`: due chiamate concorrenti non
  corrompono più il file `.tmp` durante `os.replace`.

### Changed (perf)
- HTML statici (`index.html`, `config.html`) cached a startup invece di
  `open().read()` sync per request — non blocca più l'event loop.

### Removed (dead code)
- `hiris/app/backends/claude.py` (`ClaudeBackend` mai importato in produzione).
- `hiris/app/proxy/home_profile.py` (sostituito da `SemanticContextMap`).
- `KnowledgeDB.record_correlation` / `record_query_hit` mai chiamati.
- `SemanticContextMap.add_entity` / `remove_entity` mai chiamati.
- Selettori CSS `.badge.{chat,monitor,reactive,preventive,cron}` mai emessi.
- Token CSS `--p-indigo` / `--p-blue` / `--p-cyan` / `--p-teal` mai referenziati.

### Improved (a11y)
- Tap target ≥44px (WCAG 2.5.5) su touch device per `#theme-toggle`,
  `.task-cancel-btn`, `.entity-chip .chip-remove`, `.action-item .ai-remove`.
- Lovelace card rispetta `prefers-reduced-motion` (animazione `iris-breathe`,
  `bounce`, `spin` disattivate via media query nel template Shadow DOM).

### Improved (qualità)
- `addEventListener` al posto di `.onclick` / `.onchange` in `agent-form.js`
  (no overwrite silenzioso se più handler vengono attaccati).
- Save / delete agent nel designer mostra ora un messaggio di errore se la
  fetch fallisce (prima falliva in silenzio).
- 7 punti `except Exception: pass` ora loggano almeno a debug/warning.
- Funzione `escapeHtml()` deduplicata in `index.html` (rimasta solo `esc()`).
- Cleanup git: rimossi 4 worktree e 4 branch locali integrati + 4 branch
  remoti orfani (`origin/claude/*`); repo ora ha solo `master`.

### Tests
- Nuovo `tests/test_handlers_smoke.py` (14 test) per handler API senza
  copertura: `status`, `config`, `tasks`, `health`, `run_agent`.
- Nuovi test in `tests/test_security.py` per SEC-022, SEC-022b, SEC-025.
- Nuovi test in `tests/test_internal_auth_middleware.py` per SEC-023.
- Nuovi test in `tests/test_semantic_context_map.py` per SEC-024.
- Suite passata da 446 a 469 test (+23 net; +25 added, –2 obsoleti).

## [0.9.1] — 2026-05-03

### Changed — chat surface aligned to v5 mockup
- **Greeting time-of-day**: l'header del welcome ora dice
  "Buongiorno / Buon pomeriggio / Buonasera / Buonanotte" in base all'ora,
  invece del generico "Ciao". Si aggiorna ogni ora.
- **Agent picker pill** in alto a destra: pillola con avatar gradient
  (violet → fuchsia, prima lettera del nome agente), nome agente troncato
  a 140px, dot live verde. Sostituisce il vecchio "header-title plain".
  Si aggiorna automaticamente quando si seleziona un agente.
- **Quick chips con icona emoji** sul welcome: ⚡ Stato casa, 🌡 Temperatura
  camere, 💡 Consumi energia, ☀️ Briefing del mattino. Più riconoscibili
  a colpo d'occhio.
- **Tool calls come chip pill mono inline** invece del vecchio `<details>` con
  freccia espandi. Click sul chip apre/chiude un pannello arg sotto.
  Allineato al mockup v5.

### Fixed
- Cache-busting confermato funzionante: tutti gli asset (`hiris-chat.css?v=`,
  `static/config/*.js?v=`) ricevono il `?v=VERSION` via `_inject_version()`,
  garantendo refresh dopo upgrade dell'addon.

## [0.9.0] — 2026-05-03

### Changed — Design system v5 (UI overhaul)
- **Tipografia**: stack passato da Inter Tight a **Geist** (sans + Geist Mono),
  con fallback graceful su Inter Tight / system. Mono usato solo nei blocchi
  codice (system prompt, valori tecnici, log).
- **Palette**: tokens iris OKLCH (`hiris-theme.css`) raffinati; nuovo accent
  `--iris-glow` per ombre-luce, atom `.toggle` riusabile in stile iOS,
  petali iris (`--p-violet`/`--p-fuchsia`/…) per gradient send-button.
- **Top chrome moderno** in `index.html` e `config.html`: logo iris animato
  (breathing 6s), brand + version + breadcrumb, theme toggle persistente in
  localStorage (cascade: localStorage > server config > system).
- **Chat (`index.html`)**: greeting con gradient iris→fucsia su "come posso
  aiutarti?", suggerimenti come pill rotonde, input bar ovale con send button
  gradient, bubble user in iris-tint (non più solid accent), theme toggle.
- **Designer (`config.html`)**: spec sheet con tabs moderne (sliding underline
  iris), system prompt come blocco code-styled, contesto come chip filled/outlined,
  azioni primarie con `box-shadow` iris glow, runs timeline.
- **Lovelace card (`hiris-chat-card.js`)**: Shadow DOM aggiornato — header con
  iris breath + glow ambient, send button gradient, user bubble in iris-tint,
  font Geist con fallback.

### Added — Modular split (frontend)
- **CSS estratto** dagli inline `<style>` in file dedicati:
  - `static/hiris-chat.css` (549 righe)
  - `static/hiris-config.css` (1 095 righe — sezione legacy + sezione v5)
- **JS modulare** del Designer suddiviso in `static/config/`:
  - `api.js` — fetch + helpers (esc, fmtNum, fmtTok, applyTheme, loadModels, loadUsage)
  - `templates.js` — TEMPLATES + TOOLS + ACTIONS + populateTemplateSelector
  - `cron.js` — preset, builder, _cronDesc/Apply/InitUI
  - `triggers.js` — _agentTriggers + render/load/value
  - `permessi.js` — buildToolChecks, buildActionChecks, entity selector + domain pills
  - `action-editor.js` — _agentActions + ae-* editor handlers
  - `logs.js` — renderExecutionLog, toggleLogRow, token counter, context preview
  - `usage.js` — loadAgentUsage + budget/toggle/reset handlers
  - `proposals.js` — pending/archived workflow
  - `agent-form.js` — CRUD orchestration: openAgent, save/delete/run, buildPayload
  - `tabs.js` — switchTab, theme toggle, version footer
  - `main.js` — bootstrap
- **Risultato**: `config.html` da 2 779 → 473 righe (−83%); logica invariata,
  solo riorganizzazione di delivery (classic scripts, no bundler, scope globale).
- **Strategic doc** `PRODUCT.md` aggiunto al root (impeccable design context).

### Fixed
- `applyTheme()` ora rispetta `localStorage` come prima sorgente, evitando
  che il config server-side sovrascriva la preferenza utente al refresh.

## [0.8.9] — 2026-05-03

### Fixed
- **Startup crash con OpenAI/Ollama configurato**: `OpenAICompatRunner.__init__`
  passava `total=` a `httpx.Timeout`, che non accetta quel kwarg
  (`TypeError: Timeout.__init__() got an unexpected keyword argument 'total'`).
  Sostituito con argomento posizionale (`httpx.Timeout(timeout, connect=5.0)`),
  comportamento equivalente all'intent originale. Regressione introdotta in 0.8.7.

## [0.8.8] — 2026-05-02

### Fixed
- **Ollama streaming**: `chat_stream` riscritta con `stream=True` e assemblea fragmenti
  tool-call da chunk SSE — i token ora arrivano in tempo reale invece di buffered
- **JSON argomenti malformati**: quando un modello locale invia argomenti JSON non validi,
  viene restituito un errore esplicito al modello invece di passare `{}` al tool
- **Disambiguazione eval_instruction**: etichetta "Comandi AZIONI" ora include
  "(vanno scritti in testo nel blocco AZIONI:, NON come tool calls)" — riduce le
  chiamate spurie come tool OpenAI da parte di Ollama
- **`misfire_grace_time=60`** sui job interval (era già presente su cron) — evita
  skip silenzioso se l'agente parte con ritardo
- **Ollama health check all'avvio**: `server.py` verifica `/api/tags` e logga un warning
  se Ollama non è raggiungibile o il modello non è scaricato, senza bloccare lo startup
- **`MAX_TOOL_ITERATIONS`** e **`OLLAMA_MAX_TOOL_ITERATIONS`** configurabili via env
  (default 10/5)
- **Usage tracking**: log debug quando un modello locale non ritorna informazioni sui token

## [0.8.7] — 2026-05-02

### Fixed
- **Ollama/modelli locali**: `AsyncOpenAI` ora usa `httpx.Timeout(120s)` per Ollama
  (configurabile via `OLLAMA_REQUEST_TIMEOUT`), eliminando i hang fino a 600s su hardware lento
- **Agent engine**: `asyncio.wait_for(300s)` su ogni run di agente (configurabile via
  `AGENT_RUN_TIMEOUT`) come ceiling assoluto; risolve la cascata di
  `max instances reached` che bloccava APScheduler per ore
- **Tool dispatcher**: messaggio di errore direttivo per tool sconosciuti (es. `search_entities`)
  con istruzione esplicita a non inventare nomi; riduce loop di allucinazione sui modelli locali
- **Ollama tool injection**: lista esplicita dei tool disponibili iniettata nel system prompt
  per i modelli locali, prevenendo chiamate a tool inesistenti

## [0.8.6] — 2026-05-01

### Added
- Cron builder ibrido nell'editor agenti: 13 preset comuni, builder visuale
  a 5 campi (min/ora/giorno/mese/sett.) e preview live in italiano;
  i chip nel trigger list mostrano la descrizione leggibile
- Supporto dominio `valve` (HA 2023.9+): classificazione in SemanticContextMap,
  attributi `current_position`/`reports_position` in EntityCache, pill "valvole"
  nel tab Permessi, azione `valve.*` nella whitelist; template irrigazione
  aggiornato con `open_valve`/`close_valve`

### Fixed
- MQTT: errori di autenticazione (code 135/134/5/4) ora loggati con livello
  ERROR e backoff massimo; errori di rete mantengono il backoff esponenziale
- CSS cache-busting: `?v=VERSION` iniettato nei path CSS/JS al serve time,
  forza invalidazione cache browser ad ogni release

## [0.8.5] — 2026-05-01

### Added
- Navigazione a schede nel pannello editor agenti: Identità · Istruzioni · Modello · Permessi · Azioni · Stato. Il tab Azioni si nasconde automaticamente per agenti di tipo "chat".

### Fixed
- Ripristinata palette Iris (OKLch) nella pagina Agent Designer: i blocchi `:root` hex legacy nell'inline `<style>` di `config.html` sovrascrivevano `hiris-theme.css`, rendendo inefficace il restyling grafico.

## [0.8.4] — 2026-04-30

### Changed
- Prompt engineering: `BASE_SYSTEM_PROMPT` ridotto a 5 righe eliminando la lista tool ridondante (già presente negli schemi JSON del parametro `tools`)
- Tool definitions ora cachate via `cache_control` sull'ultimo tool — risparmio su ogni chiamata con configurazione agente stabile
- Tool results vecchi nell'agentic loop compressi a 300 char (si mantengono completi solo gli ultimi 2 set) — riduce il context bloat su catene lunghe di tool calls
- Session summary riscritta come digest conversazionale (ultimi 3 scambi U→A, 120 char ciascuno) invece di troncamento dell'ultima risposta
- `context_str` strutturato con header espliciti (`## Memoria rilevante`, `## Sessioni precedenti`, `## Contesto casa`) per disambiguare la provenienza dei dati
- History truncation basata su token stimati (~6000) invece di conteggio fisso a 30 messaggi — evita esplosioni di contesto con risposte lunghe

## [0.8.3] — 2026-04-30

### Fixed
- `HealthMonitor`: ogni sezione del refresh (error_log, config_entries, system_info, updates) ora è isolata in un proprio try/except — un endpoint non disponibile non blocca più le altre sezioni
- `get_error_log()`: gestisce 403/404 gracefully invece di propagare l'eccezione
- MQTT: strip whitespace dalle credenziali lette da bashio (causa principale del codice 135 "Not Authorized"); client ID fisso `"hiris"` invece di UUID casuale; log di debug con host/user/password_len ad ogni tentativo di connessione

## [0.8.2] — 2026-04-30

### Changed
- `hiris-chat-card`: applicato Iris design system alla Shadow DOM (token `--i-*`, font Inter Tight + JetBrains Mono, bubble chat allineate a `index.html`, composer con focus ring, status pill)
- `hiris-chat-card`: dropdown agenti filtrato solo su `type === 'chat'` con hint "Solo agenti di tipo Chat"

## [0.8.1] — 2026-04-30

### Changed
- Iris design system: nuovo `hiris-theme.css` con palette oklch a 6 petali, tipografia Inter Tight + JetBrains Mono, light/dark automatico
- `index.html` completamente riscritto con il nuovo layout Iris (sidebar 280px, bubble chat, welcome screen con gradient, onboarding con radial glow)
- `config.html` aggiornato tramite `hiris-config-override.css` — zero modifiche alla logica JS esistente
- CSP aggiornata per consentire Google Fonts CDN (`fonts.googleapis.com`, `fonts.gstatic.com`)

## [0.8.0] — 2026-04-30

### Added
- **HealthMonitor**: hybrid health snapshot for HA — real-time unavailability tracking via WebSocket `state_changed` + full refresh every 30 minutes via APScheduler; persists to `/data/ha_health.json` across restarts
- **ProposalStore**: async SQLite store for automation proposals with 7-day archive / 30-day delete lifecycle; states: `pending → applied|rejected` (permanent) or `archived` (after 7d) → deleted (after 30d)
- **Tool `get_ha_health(sections)`**: reads the HealthMonitor snapshot — unavailable entities, integration errors, error log summary, pending HA updates, system info; available to all agent types (in `EVALUATION_ONLY_TOOLS`)
- **Tool `create_automation_proposal(...)`**: agents can propose new HA automations or HIRIS agents for human review instead of executing changes directly; chat agents only
- **REST API**: `GET /api/health/ha`, `POST /api/health/ha/refresh`, `GET /api/proposals`, `GET /api/proposals/{id}`, `POST /api/proposals/{id}/apply`, `POST /api/proposals/{id}/reject`
- **Agent Designer UI**: "Proposte automazione" section with pending/archived tabs; apply (with confirmation dialog) and reject actions; animated row feedback before removal

### Fixed
- **Security — XSS**: `renderProposals` replaced inline `onclick` handlers with `data-pid` attributes and `addEventListener`; `p.id` now escaped via `escHtml()` in HTML attribute context
- **Security — CSRF**: `apply` and `reject` POST endpoints require `X-Requested-With: XMLHttpRequest` header (403 otherwise); frontend fetch calls include the header
- **Validation**: `GET /api/proposals?status=` returns 400 for values outside `pending|applied|rejected|archived`
- **Code quality**: `HealthMonitor.start()` simplified — removed redundant `scheduler` parameter, always uses `self._scheduler`; `except Exception as exc:` cleaned to `except Exception:`
- **UX**: "Attiva" button shows confirmation dialog; `checkEmptyList()` uses active tab label; apply/reject show animated feedback before removing row
- **UI**: `proposal-desc` upgraded from single-line `white-space: nowrap` to 2-line `-webkit-line-clamp: 2`; load errors shown in red distinct from empty state; routing_reason labeled "Motivo:"

### Changed
- `docs/ROADMAP.md` removed from git tracking (added to `.gitignore`); Roadmap section removed from README
- All documentation updated: new tools, new components, new data stores, version headers to 0.8.0

## [0.7.0] — 2026-04-29

### Changed
- Refactored agent model to two types: **chat** (conversational NL) and **agent** (autonomous agentic loop with structured output)
- Post-review fixes to two-agent-type migration (naming, validation, UI consistency)

### Fixed
- Entity ACL bypass: agents can no longer access entities outside their allowed areas
- Prompt injection protection added to user-supplied fields
- CSP headers hardened on all aiohttp responses
- Dead code removed from agent runner and tool dispatcher

## [0.6.16] — 2026-04-29

### Added
- **Custom agent states** (`states` field): each non-chat agent can now declare its own VALUTAZIONE vocabulary instead of the fixed `OK|ATTENZIONE|ANOMALIA`; defaults unchanged for existing agents — fully backward compatible
- **`response_mode` per agent** (`auto` / `compact` / `minimal`): controls verbosity of agent responses; `minimal` uses key:value output for chat and a single-line motivation for non-chat agents
- **Irrigation agent template** ("Irrigazione Giardino"): preventive agent (`0 5 * * *`) that reads precipitation history + soil moisture + 48h forecast and schedules valve on/off via `create_task()`; uses `SKIP|LEGGERA|PIENA` states
- **SemanticContextMap**: added `precipitation`, `soil_moisture`, `weather` entity types; added concepts `irrigazione`, `irrigare`, `sprinkler`, `pioggia`, `piovuto`, `precipitazione`, `umidità suolo`, `giardino`, `meteo`, `previsioni`
- **Docs**: irrigation use case added to `docs/use-cases.md` and `docs/casi-duso.md`; tips sections updated to document custom states

### Changed
- **config.html**: trigger-on checkboxes are now dynamically generated from the agent's `states` field; "Modalità risposta" dropdown added; template selector now applies `type`, `cron`, `states`, `trigger_on` when a template is chosen; `f-states` blur listener rebuilds checkboxes preserving current selections

## [0.6.15] — 2026-04-29

### Changed
- **`config.yaml`**: sidebar icon changed from `mdi:robot` to `mdi:home-automation`

## [0.6.14] — 2026-04-29

### Added
- **`scripts/doc_check.py`**: documentation consistency checker run automatically before every release as step 3c; detects stale config key names (auto-fixes with `--fix`), broken cross-links, missing version headers, untracked docs, and README documentation table gaps; bypass with `--skip-doc-check` for emergencies
- **`scripts/release.py`**: `--skip-doc-check` flag added; step 3c calls `doc_check.py --fix` before the git-clean check so any auto-fixable stale keys are repaired and committed in the same release commit

### Fixed
- **`scripts/release.py`**: `_VERSIONED_DOCS` entry `ROADMAP.md` corrected to lowercase `roadmap.md` to match the actual filename (was working on Windows due to case-insensitive FS but would fail on Linux)

## [0.6.13] — 2026-04-29

### Added
- **`docs/full-local-mode.md`** / **`docs/full-local-mode-it.md`**: new guide for running HIRIS with zero cloud dependencies — Ollama model recommendations (Qwen2.5:27b, Mistral Small 3.1), full configuration example, performance comparison vs Claude, known limitations
- **`docs/mqtt-integration.md`**: new guide for MQTT auto-discovery — all published entities (`status`, `budget_remaining_eur`, `tokens_used_today`, `enabled`, `last_result`, `run_now`), control via MQTT topics, dashboard example, budget-warning automation example

### Fixed
- **README.md**: configuration table now uses correct nested key names (`local_model.url`, `local_model.model`, `mqtt.host`) — flat underscore names were stale since v0.6.6
- **README.md**: local-only mode note corrected — when `local_model.url` + `local_model.model` are set, HIRIS runs fully offline with Ollama (full agentic loop, all agent types); the old note said AI calls were always disabled when `claude_api_key` was empty
- **README.md**: Multi-provider LLM section clarified — automatic model selection (Sonnet for chat, Haiku for monitors) applies only when Claude is the provider; Ollama model is configured per-agent in the designer UI

## [0.6.12] — 2026-04-29

### Added
- **`model2vec` embedding provider**: fully local, no server, no API key required — the only embedding option compatible with Alpine Linux (HA add-ons); models are downloaded from HuggingFace Hub on first startup and cached in `/config/hiris/models/huggingface/`; recommended model is `minishlab/potion-base-8M` (~30 MB)
- **`run.sh`**: `HF_HOME` environment variable set to `/config/hiris/models/huggingface` so HuggingFace models persist across add-on restarts
- **Docs**: `docs/configuration-guide.md` and `docs/guida-configurazione.md` updated — Option C section replaced with model2vec (was fastembed); model2vec marked as recommended local option for HA add-ons

### Changed
- **`requirements.txt`**: replaced `fastembed>=0.3.0` with `model2vec>=0.8.0`
- **`Dockerfile`**: removed best-effort fastembed install step (model2vec installs cleanly on Alpine via musllinux wheels)
- **Translations** (`en.yaml`, `it.yaml`): embedding provider and model descriptions updated to mention model2vec

## [0.6.11] — 2026-04-29

### Fixed
- **Docker build failure**: `fastembed` depends on `onnxruntime` which has no pre-built wheels for Alpine Linux (musl libc) — the add-on image failed to build on all platforms; removed `fastembed` from `requirements.txt` and moved it to a best-effort `pip install || true` step in `Dockerfile` so the build never fails
- **`embeddings.py`**: `build_embedding_provider("fastembed")` now checks if fastembed is importable at startup and falls back to `NullEmbedder` with a log warning if not installed, instead of crashing on first use

## [0.6.10] — 2026-04-28

### Fixed
- **`run.sh`**: `bashio::config --raw` is not a valid bashio flag and caused 12 jq compile errors on every startup; replaced with `jq -c '.apprise_urls // []' /data/options.json` which reads the array directly from the HA options file — Apprise URLs were being silently ignored before this fix

## [0.6.9] — 2026-04-28

### Fixed
- **Chat input (`index.html`)**: textarea now grows dynamically as you type without ever showing a scrollbar (`overflow-y: hidden`); height cap raised to 40% of viewport height instead of the fixed 8rem/128px limit

## [0.6.8] — 2026-04-28

### Added
- **fastembed embedding provider**: fully local RAG with no external server or API key required; uses ONNX Runtime (ARM64/amd64 compatible); models cached in `/config/hiris/models/`; default model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` supports 50+ languages including Italian
- `fastembed>=0.3.0` added to `requirements.txt`
- Configuration guide updated with Option C (fastembed) section; translations updated with fastembed in provider description

## [0.6.7] — 2026-04-28

### Added
- **Configuration guide** (`docs/configuration-guide.md` / `docs/guida-configurazione.md`): step-by-step setup for Apprise notifications (Telegram, ntfy, Gotify, email, Discord, WhatsApp) and Memory/RAG (OpenAI embeddings, Ollama local embeddings, tuning parameters)
- README: links to new configuration guide docs

## [0.6.6] — 2026-04-28

### Changed
- **Config restructure**: options now grouped into logical nested sections (`local_model`, `mqtt`, `memory`) instead of flat underscore-prefixed keys; HA UI renders each group as a collapsible section
- **`run.sh`**: updated all `bashio::config` calls to dotted path notation (`mqtt.host`, `local_model.model`, etc.); added missing `LLM_STRATEGY` export (was always defaulting to `balanced` regardless of config UI)
- **Translations**: added `hiris/translations/en.yaml` and `hiris/translations/it.yaml` with human-readable labels and descriptions for all 18 configuration options in both English and Italian

## [0.6.5] — 2026-04-28

### Fixed
- **Chat UI (`index.html`)**: added `_isLoading` flag — Enter key can no longer trigger a second request while a response is in progress; send button shows a CSS spinner during generation
- **Lovelace card**: text typed in the input field is now preserved across streaming re-renders (previously lost on every token); send button shows a spinner and `title="Elaborazione…"` while loading; input placeholder changes to "Elaborazione…" during generation

## [0.6.4] — 2026-04-28

### Fixed
- `ClaudeRunner.__init__()` crashed on startup due to spurious `entity_cache` and `semantic_map` kwargs passed from `server.py` (introduced in v0.6.3)

## [0.6.3] — 2026-04-28

### Added
- **LLMRouter strategy**: `strategy` param (`balanced` / `quality_first` / `cost_first`) controls backend preference order; wired via `LLM_STRATEGY` env var and `llm_strategy` config option
- **LLMRouter fallback**: when `model="auto"`, if the primary backend raises an exception the next backend in the strategy chain is tried automatically
- `backends/pricing.py`: centralized USD/MTok pricing table for all supported models (Claude 4.x, GPT-4o/4.1/o-series, Ollama free); replaces duplicate `_PRICING` dicts in `ClaudeRunner` and `OpenAICompatRunner`

## [0.6.2] — 2026-04-28

### Fixed
- **SSRF**: `http_tools` now blocks IPv4-mapped IPv6 addresses (`::ffff:127.x`) and always disables redirects (redirects bypassed `_PinnedResolver`)
- **Entity leakage**: `allowed_entities` filter now applied to `get_home_status`, `get_entities_on`, `get_entities_by_domain` (was only enforced on `get_entity_states`)
- **Prompt injection**: RAG memories marked as untrusted data in system context; `debug.tools_called` response redacted to tool names only
- **Path traversal**: `agent_id` validated with regex in chat history handler
- **Auth bypass**: middleware now denies non-ingress requests by default when no `internal_token` is configured
- `ClaudeRunner.run_with_actions` now includes action instructions in augmented prompt (was inconsistent with `OpenAICompatRunner`)
- `openai_compat_runner`: imports hoisted to module top (were dynamic per-call)
- `handlers_agents`: `_validate_agent_payload()` validates type/name/trigger/budget on create and update

### Removed
- Dead `entity_cache`/`semantic_map` params from `ClaudeRunner` (unreachable branch in production)
- Dead `set_notify_config()` / `_notify_config` from `AgentEngine` (written, never read)

## [0.6.1] — 2026-04-28

### Added
- **Sprint D — Multi-provider LLM**: supporto OpenAI e Ollama per-agente; `OpenAICompatRunner`
  con loop agentico completo (tool use, `run_with_actions`); `ToolDispatcher` condiviso tra tutti
  i runner; `LLMRouter` ridisegnato come router reale; endpoint `/api/models` con lista dinamica
  (fetch live da OpenAI, `/api/tags` per Ollama); dropdown modello con `<optgroup>` per provider;
  `_PRICING_OAI` per tracking costi OpenAI/Ollama
- **Sprint C — Memory-RAG**: tabella `agent_memories` in SQLite; tool `recall_memory` / `save_memory`;
  RAG pre-injection nelle chat; `EmbeddingProvider` Protocol + `OpenAIEmbedder` + `OllamaEmbedder`
  + `NullEmbedder`; job APScheduler retention 03:00 UTC; config: `memory_embedding_provider`,
  `memory_embedding_model`, `memory_rag_k`, `memory_retention_days`, `history_retention_days`
- **Sprint B — Tool Expansion**: tool `create_calendar_event`; layer Apprise (80+ canali via
  `apprise_urls`); `EVALUATION_ONLY_TOOLS` frozenset; `Agent.trigger_on` + `AgentEngine._execute_agent_actions`;
  `on_fail: continue|stop` per azione; `TaskEngine` trigger `immediate`; UI: trigger_on checkboxes,
  on_fail dropdown, editor azioni child (wait/verify)
- **Sprint A — HA-Bridge**: MQTT 2-way subscribe (`hiris/agents/+/{enabled,run_now}/set`);
  nuove entità MQTT `last_result`, `budget_remaining_eur`, `tokens_used_today`, `run_now`;
  tool `http_request` con security strutturata (AllowedEndpoint, DNS pinning, RFC1918 DENY_NETS);
  `Agent.allowed_endpoints`

### Fixed
- **Sprint 0 — Bugfixes critici**: `handlers_agents.py` / `handlers_usage.py` usa
  `get("llm_router") or get("claude_runner")`; stub `app/ha_client.py` rimosso; `SemanticContextMap`
  persist/load JSON su restart; `EUR_RATE` centralizzato in `config`; MQTT pubblica stato su
  cambio `enabled`
- I/O file non bloccante: `_save()`, `_save_usage()`, `SemanticContextMap.save()` via
  `run_in_executor`

## [0.5.16] — 2026-04-27

### Fixed
- Lovelace card: server writes `hiris-ingress.json` to `/local/hiris/` at startup so the card discovers the real Supervisor ingress URL — resolves all card 503 errors
- Lovelace card: chat streaming hang fixed — timeout now covers the entire stream lifecycle; `streaming` flag cleared when stream closes even without SSE `done` event
- Lovelace card: replaced blinking cursor with animated typing indicator (HIRIS icon + three bouncing dots) matching the add-on's direct chat UI
- Lovelace card: removed duplicate status indicator from header — only the enable/disable toggle button remains in the top-right
- Lovelace card: switched all API calls from `hass.callApi()` to `fetch()` with explicit Authorization header
- Lovelace card: SyntaxError and constructor render crash blocking the HA card picker
- Docker: `config.yaml` now copied into the container so `read_version()` returns the correct version string instead of "unknown"

## [0.5.15] — 2026-04-27

### Fixed
- La card Lovelace restituiva HTTP 503 per tutte le chiamate API anche con il add-on attivo: il Supervisor HA assegna ad ogni add-on un token casuale come percorso ingress (`/api/hassio_ingress/{token}/`) invece dello slug, quindi il vecchio URL hardcoded `/api/hassio_ingress/hiris/` non veniva riconosciuto da HA
- All'avvio HIRIS interroga il Supervisor (`/addons/self/info`) per ottenere il proprio `ingress_url` reale e lo scrive in `/homeassistant/www/hiris/hiris-ingress.json` (file statico pubblico, nessuna auth richiesta)
- La card legge questo file una volta prima della prima chiamata API e usa l'URL corretto per tutte le operazioni; se il file non è disponibile usa l'URL basato sullo slug come fallback
- `HirisChatCardEditor._loadAgents()` migrato da `hass.callApi()` a `fetch()` con auth esplicita (stesso motivo)

## [0.5.14] — 2026-04-27

### Fixed
- `_fetchStatus()` e `_toggleAgent()` ora usano `fetch()` con auth esplicita invece di `hass.callApi()`: quest'ultimo fallisce su alcuni HA/Supervisor con percorsi di ingress, mostrando "HIRIS non disponibile" anche quando il backend è raggiungibile
- Il messaggio di errore nel chat ora mostra la causa reale dal body JSON del backend (es. "Claude runner not configured — set CLAUDE_API_KEY") invece del generico "HTTP 503"
- Estratti i metodi helper `_hirisUrl(path)` e `_authToken()` per eliminare la duplicazione della logica di autenticazione

## [0.5.13] — 2026-04-27

### Fixed
- `config.yaml` ora viene copiato nel container Docker (`COPY config.yaml /usr/lib/hiris/config.yaml`): `read_version()` restituiva sempre `"unknown"` in produzione perché il file non era presente, rendendo l'URL della risorsa Lovelace sempre `/local/hiris/hiris-chat-card.js?v=unknown` e vanificando il cache-busting introdotto in v0.5.12

## [0.5.12] — 2026-04-27

### Fixed
- La risorsa Lovelace ora viene registrata come `/local/hiris/hiris-chat-card.js?v=VERSION` invece dell'URL senza versione: ad ogni aggiornamento dell'add-on il vecchio URL viene rimosso e quello nuovo creato, forzando il browser a ricaricare il JS aggiornato (cache-busting)
- Migrazione automatica da tre tipi di URL obsoleti: vecchio ingress URL, vecchio URL senza versione, vecchio URL con versione diversa

## [0.5.11] — 2026-04-27

### Fixed
- `set hass()` in `HirisCard` non guardava contro `hass` null/undefined — il card picker di HA istanzia gli elementi e chiama il setter prima di `setConfig`, causando `TypeError` che HA interpreta come "card rotta" e rimuove silenziosamente dal picker
- `set hass()` in `HirisChatCardEditor` idem — impediva il caricamento dell'editor di configurazione
- `_loadAgents()` ora verifica `this._hass` prima di chiamare `callApi`
- `_sendMessage()` ora esce anticipatamente se `this._hass` non è disponibile
- `parseFloat` sul budget ora usa `Number.isFinite` per evitare `NaN.toFixed(2)` in template
- `customElements.define()` ora guarda con `customElements.get()` prima di registrare: se il file viene caricato due volte (hot reload HA) la `define()` non lancia più `NotSupportedError` che bloccava la `window.customCards.push()` sottostante
- `window.customCards.push()` ora deduplica con `.find()`: nessuna doppia registrazione nel picker
- `titleInput.oninput` → `onchange` nell'editor: HA chiama `setConfig` → `_render()` → `innerHTML` ricreato ad ogni tasto, causando perdita del focus; con `onchange` il focus si perde solo al blur
- `getCardSize()` ora restituisce 2 in stato non configurato (era 6: riservava troppo spazio verticale)

## [0.5.10] — 2026-04-27

### Fixed
- `SyntaxError: Identifier 'msgs' has already been declared` in `hiris-chat-card.js`: variabile `msgs` dichiarata due volte nella stessa funzione `_render()`, impediva il parsing del file e rendeva la card completamente invisibile in HA
- Rimosso `this._render()` dai costruttori di `HirisCard` e `HirisChatCardEditor`: il card picker di HA istanzia gli elementi custom prima di connetterli al DOM, causando ricorsione Shadow DOM tramite i mutation observer di Lit (`Maximum call stack size exceeded`)
- Aggiunto `connectedCallback` a `HirisChatCardEditor` in modo che il primo render avvenga nel momento corretto del lifecycle

## [0.5.9] — 2026-04-27

### Fixed
- `get_area_registry()` e `get_entity_registry()` migrati da REST
  (`/api/config/*/list`, restituiva 404 via Supervisor) a WebSocket
  (`config/area_registry/list`, `config/entity_registry/list`);
  il tool Claude `get_area_entities` ora funziona e le aree/stanze
  sono disponibili come contesto per gli agenti

## [0.5.8] — 2026-04-27

### Added
- **Lovelace card picker** — `window.customCards` registration, visual editor
  (`hiris-chat-card-editor`), `getStubConfig` returning `hiris-default`; card
  now appears in the HA "Add Card" picker without manual YAML

### Fixed
- **Lovelace resource registration** — switched from REST API
  (`/api/lovelace/resources`, returned 404 in many HA setups) to WebSocket API
  (`lovelace/resources/create/delete`); works in all storage-mode configurations
- **Card JS deployment** — add-on copies `hiris-chat-card.js` to
  `<ha-config>/www/{slug}/` on startup so `/local/{slug}/hiris-chat-card.js`
  resolves without authentication; probes `/config` then `/homeassistant`
- **Stale ingress URL migration** — removes old `/api/hassio_ingress/` resource
  automatically and registers the new `/local/` URL in its place
- `config:rw` added to add-on map (`config.yaml`) — required for www deployment
- `getCardSize()` implemented; `preview: false` set to prevent HA from
  attempting live renders in the picker

## [0.5.7] — 2026-04-27

### Fixed
- `_deploy_card_to_www()` ora prova sia `/config` che `/homeassistant` per trovare la directory di configurazione HA (il Supervisor monta il volume `config:rw` su `/config` nelle versioni correnti, non su `/homeassistant`); la funzione usa il percorso che contiene effettivamente `configuration.yaml` o `.storage`
- Aggiunta funzione `_find_ha_config_dir()` che individua il percorso corretto in modo robusto tra le versioni di Supervisor

## [0.5.6] — 2026-04-26

### Fixed
- `map: homeassistant:rw` replaced with `map: config:rw` — `homeassistant` is not a recognized HA Supervisor volume key and was silently ignored, leaving `/homeassistant` unmounted inside the container; the card copy appeared to succeed but wrote to the ephemeral container filesystem instead of the HA host, so `/local/hiris/hiris-chat-card.js` always returned 404
- `_deploy_card_to_www()` now verifies the HA config volume is actually mounted (checks for `configuration.yaml` or `.storage` at `/homeassistant`) before copying; logs a clear ERROR with actionable instructions if not, instead of silently "succeeding" with no visible failure

## [0.5.5] — 2026-04-26

### Fixed
- `setConfig` lancia eccezione su config null (contratto HA), resetta messaggi/polling al cambio agente
- Token SSE in `_sendMessage` usa `auth.accessToken` (HA 2024+) con fallback a `data.access_token`
- Rimossa costante `EUR_RATE` inutilizzata

## [0.5.4] — 2026-04-26

### Fixed
- Aggiunto `getCardSize()` → HA alloca la griglia correttamente senza mostrare shimmer di caricamento permanente
- `preview: false` nel registro `window.customCards` → il picker non tenta un render live (che richiede HIRIS attivo)
- `_fetchStatus()` usa `_patchStatus()` invece di `_render()` quando il DOM è già inizializzato → preserva il testo digitato nella chat
- `set hass()` usa `_patchStatus()` per aggiornamenti MQTT → nessuna sostituzione DOM su ogni cambio entity

## [0.5.3] — 2026-04-26

### Fixed
- Lovelace card JS ora servita via `/local/hiris/hiris-chat-card.js` invece dell'URL ingress (che richiedeva auth e restituiva 401 al browser)
- Aggiunto `map: homeassistant:rw` in `config.yaml` per consentire la copia del JS in `/homeassistant/www/hiris/` all'avvio
- Migrazione automatica: l'URL ingress stale viene eliminata da Lovelace resources e sostituita con quella `/local/`

## [0.5.2] — 2026-04-26

### Added
- Lovelace card picker: registrazione custom card, visual editor e stato "unconfigured"
- Lovelace card picker integration completa (v0.6.0 feature set)

### Fixed
- Code review findings post-picker integration

## [0.5.1] — 2026-04-25

### Added
- **Lovelace card auto-registration** — on startup HIRIS calls `POST /api/lovelace/resources` (via Supervisor token) to register `hiris-chat-card.js` as a UI module; idempotent, graceful in YAML-mode HA
- **Single-source versioning** — version read dynamically from `config.yaml` at runtime; `server.py` and `handlers_status.py` no longer hardcode it
- **Release script** — `scripts/release.py`: 10-step mechanical release executor (semver validation → changelog check → tests → git tag → GitHub Release); supports `--dry-run` and `--skip-tests`

## [0.5.0] — 2026-04-25

### Added
- **X-HIRIS-Internal-Token middleware** — HMAC-validated auth for inter-add-on requests (non-Ingress)
- **Enriched `/api/agents` response** — includes `status`, `budget_eur`, `budget_limit_eur` for Lovelace dashboard
- **SSE streaming for `/api/chat`** — Server-Sent Events path when `stream: true` or `Accept: text/event-stream`; Phase 1 pseudo-streaming (full response sliced into 80-char tokens)
- **`hiris-chat-card.js`** — vanilla JS Lovelace custom card (shadow DOM, 30s polling, SSE streaming, budget bar, toggle enable/disable)
- **MQTT Discovery publisher** — publishes `sensor.hiris_*_status/budget_eur/last_run` and `switch.hiris_*_enabled` via aiomqtt; exponential backoff reconnect; discovery messages queue during initial backoff

### Changed
- `config.yaml`: added `internal_token`, `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password` options
- `AgentEngine`: tracks running/error agent status; publishes MQTT state on each run

## [0.4.2] — 2026-04-24

### Fixed
- `internal_token` option uses `password` schema in `config.yaml` (masked in HA UI)
- HMAC comparison uses `hmac.compare_digest` (constant-time, prevents timing attacks)

## [0.4.0] — 2026-04-23

### Added
- **SemanticContextMap** — replaces EmbeddingIndex; organizes entities by area using `device_class` + domain classification; ~60% token reduction vs previous RAG
- **KnowledgeDB** — SQLite persistence for entity classifications, agent annotations, entity correlations
- **TaskEngine** — shared deferred-task system; 4 trigger types (`delay`, `at_time`, `at_datetime`, `time_window`); 3 action types; task persistence in `/data/tasks.json`
- **LLM Router** — routes standard inference to Claude, offloads `classify_entities()` to local Ollama when `LOCAL_MODEL_URL` configured
- **Task UI** — "Task" tab with pending-count badge; active + recent task list; cancel button; auto-refresh every 30s

### Removed
- `EmbeddingIndex` — replaced by `SemanticContextMap`
- `search_entities` Claude tool — removed with EmbeddingIndex dependency

## [0.3.0] — 2026-04-23

### Added
- **SemanticContextMap** — replaces EmbeddingIndex RAG and SemanticMap snippet; organizes all HA entities by area using native `device_class` + domain classification
- **ENTITY_TYPE_SCHEMA** — maps (domain, device_class) → (entity_type, label_it) for 30+ entity types, based on HA documentation
- **ContextSelector** — keyword-based query: extracts area + concept→type matches from user message, injects only relevant sections
- **Two-tier prompt injection** — compact home overview always present (~80 token); area/type detail expanded on match (~150 token); ~60% token reduction vs previous RAG
- **KnowledgeDB** — SQLite persistence for entity classifications, agent annotations, entity correlations, query patterns
- **Unified permission boundary** — `visible_entity_ids` from `SemanticContextMap.get_context()` used to validate all entity tool calls; consistent `allowed_entities` enforcement
- **EntityCache enriched** — `domain`, `device_class`, and typed attributes (hvac_mode, brightness, current_position, etc.) stored per entity for all domains

### Removed
- `EmbeddingIndex` — replaced by `SemanticContextMap` + `ContextSelector`
- `SemanticMap.get_prompt_snippet()` — replaced by `SemanticContextMap._format_overview()` + `_format_detail()`
- `search_entities` Claude tool — removed with EmbeddingIndex dependency

## [0.2.3] — 2026-04-22

### Added
- **TaskEngine** — shared deferred-task system available to all agent types (chat, monitor, reactive, preventive)
- **4 trigger types** — `delay` (minutes from now), `at_time` (wall-clock HH:MM local time), `at_datetime` (ISO datetime), `time_window` (poll every N min within a HH:MM–HH:MM window)
- **Optional condition** — entity state check at trigger time with operators `<`, `<=`, `>`, `>=`, `=`, `!=`; task skipped (not failed) if condition unmet
- **3 action types** — `call_ha_service`, `send_notification`, `create_task` (chaining: child task inherits `agent_id`, sets `parent_task_id`)
- **Task persistence** — tasks saved to `/data/tasks.json` with atomic write; pending tasks rescheduled on restart
- **Automatic cleanup** — terminal tasks (done/skipped/failed/expired/cancelled) deleted after 24h via hourly APScheduler job
- **3 Claude tools** — `create_task`, `list_tasks`, `cancel_task` available in `allowed_tools` per agent
- **REST API** — `GET /api/tasks`, `GET /api/tasks/{id}`, `DELETE /api/tasks/{id}`
- **Task UI** — "Task" tab in sidebar with pending-count badge; active task list + recent (24h) list; Annulla button for pending tasks; auto-refresh every 30s
- **Python 3.13** — upgraded base image from `3.11-alpine3.18` to `3.13-alpine3.21`

### Fixed
- `at_datetime` trigger called removed `_run_task_async` method — changed to `_execute_task`
- `_check_time_window` stored naive local timestamp in `executed_at` — now UTC-aware
- `create_task` tool dispatch now enforces agent's `allowed_services` whitelist on all `call_ha_service` actions before scheduling (previously bypassable via deferred tasks)
- Task UI: `label`, `result`, `error`, `status`, and `id` fields now HTML-escaped before injection into innerHTML (XSS prevention)
- `EntityCache`: added `get_state(entity_id)` method required by `TaskEngine` condition evaluation

## [0.2.2] — 2026-04-22

### Fixed
- `get_weather_forecast`: cast `hours` parameter to `int` to handle Claude passing it as string
- `get_energy_history`: cast `days` parameter to `int` for the same reason

## [0.2.1] — 2026-04-22

### Fixed
- `EntityCache.get_state()` method missing — caused `AttributeError` in `SemanticMap.get_prompt_snippet()` on production

## [0.2.0] — 2026-04-22

### Added
- **Semantic Home Map** — automatic rule-based + LLM-assisted classification of all HA entities into semantic roles (energy_meter, solar_production, climate_sensor, lighting, appliance, presence, door_window, etc.)
- **LLM Router** — thin routing layer that forwards standard inference to Claude and offloads `classify_entities()` to a local Ollama model when `LOCAL_MODEL_URL` is configured
- **LLM Backend abstraction** — `LLMBackend` ABC with `ClaudeBackend` and `OllamaBackend` implementations
- **Semantic prompt snippet** — structured home context injected into every Claude call (energy, climate, lights summary with live state)
- **SemanticMap persistence** — classification saved to disk and reloaded on startup; LLM re-classifies only unknown entities
- **HAClient entity registry listener** — SemanticMap updates automatically when new entities are added to HA
- **`get_home_status` enriched** — returns semantic labels from SemanticMap instead of raw entity IDs
- **Energy tools read SemanticMap** — `get_energy_history` resolves entity IDs from SemanticMap; no manual configuration needed
- **Config options** — `primary_model`, `local_model_url`, `local_model_name` in `config.yaml`
- **SSRF protection** — `OllamaBackend` validates URL and blocks cloud metadata endpoints (169.254.169.254, etc.)

### Security
- **CVE-2024-52304** — upgraded `aiohttp` to `>=3.10.11` (HTTP request smuggling)
- **CVE-2024-42367** — same upgrade covers path traversal via static routes
- **Prompt injection sanitization** — control characters stripped from entity names, states, units, and action fields before injection into system prompt (`handlers_chat.py`, `semantic_map.py`)
- **asyncio race condition** — `SemanticMap._classify_unknown_batch()` protected with `asyncio.Lock`
- **JSON schema validation** — `LLMRouter._parse_classify_response()` validates role against allowlist, clamps confidence, truncates fields; truncates raw response to 100 KB before parse
- **WebSocket reconnect** — `HAClient._ws_loop` now reconnects automatically after any disconnect (10 s backoff); listener callback exceptions are isolated

---

## [0.1.9] — 2026-04-22

### Added
- **RAG pre-fetch** — before each Claude call, HIRIS tokenizes the user message, finds semantically related entities via `EmbeddingIndex` (keyword overlap), fetches their live states from `EntityCache`, and injects them into the system prompt under "Entità rilevanti"
- `EmbeddingIndex` — in-memory keyword index built from entity names and IDs; no ML dependency
- `EntityCache` — in-memory entity state cache updated in real time from HA WebSocket events

### Fixed
- Include climate entity temperatures in EntityCache
- Default agent system prompt updated with correct tool signatures

---

## [0.1.8] — 2026-04-22

### Fixed
- Mobile UI: `100dvh` viewport height, `font-size: 16px` (prevents iOS auto-zoom), 44px send button, `enterkeyhint: send` on message input, safe-area insets for notch/home-bar

---

## [0.1.7] — 2026-04-22

### Added
- **Per-agent usage tracking** — token counts (input/output) and estimated cost in USD tracked per agent and model; reset endpoint available
- **Budget auto-disable** — agent auto-disables when cumulative cost (USD × 0.92) reaches `budget_eur_limit`; logs reason
- **Global usage endpoint** — `GET /api/usage` returns total tokens and cost across all agents
- **Agent usage endpoints** — `GET /api/agents/{id}/usage`, `POST /api/agents/{id}/usage/reset`

### Fixed
- Count global request tokens once per `chat()` call, not once per tool iteration
- Truncate conversation history to last 30 messages sent to Claude API

---

## [0.1.6] — 2026-04-21

### Added
- **Chat persistence** — server-side conversation history stored per agent in `/data/chat_history_<agent_id>.json`
- **Max chat turns** — `max_chat_turns` field on agent; chat returns `{error: "max_turns_reached"}` when limit is hit
- **Chat history endpoints** — `GET /api/agents/{id}/chat-history`, `DELETE /api/agents/{id}/chat-history`
- **New conversation button** — UI clears client-side history and calls delete endpoint
- **Turn counter** — displayed in chat UI header
- **`icon.png`** — add-on icon for HA Supervisor store
- `script.*` added to allowed action domains in agent designer

### Fixed
- Notify channel value corrected from `ha` to `ha_push` in Action Builder
- `agent_id` sanitized in chat store path to prevent path traversal

---

## [0.1.5] — 2026-04-21

### Added
- **Action Builder** — visual step editor for agent actions in the Config UI; supports `call_ha_service`, `send_notification`, and `trigger_automation` actions
- **Per-agent entity chips** — quick entity selector in agent designer; entities filtered by `allowed_entities` patterns
- **`strategic_context`** field on agents — house/family context prepended to every Claude system prompt

### Fixed
- Agent designer improvements merged from feature branch
- Four issues from final branch review

---

## [0.1.4] — 2026-04-20

### Added
- **Chat NL UI** — full conversation interface at `/` with real-time assistant responses, sidebar for agent selection, message history display
- **Agents CRUD API** — `GET/POST /api/agents`, `GET/PUT/DELETE /api/agents/{id}`, `POST /api/agents/{id}/run`
- **Agent Designer UI** — step-based editor at `/config` for creating and editing agents
- **`require_confirmation` mode** — Claude must ask user before executing `call_ha_service`
- **`restrict_to_home` mode** — agent refuses off-topic questions
- **`allowed_entities` filter** — glob-pattern entity whitelist per agent
- **`allowed_services` filter** — glob-pattern service whitelist per agent
- **Default agent seed** — `hiris-default` chat agent created automatically on first startup
- **Execution log** — last 20 runs logged per agent with tokens, tool calls, result summary, `eval_status`, `action_taken`

---

## [0.1.3] — 2026-04-20

### Added
- **Claude agentic loop** — multi-turn tool use loop (max 10 iterations) with retry logic (429/529: 5s → 15s → 45s → error)
- **8 built-in tools**: `get_entity_states`, `get_area_entities`, `get_home_status`, `get_energy_history`, `get_weather_forecast`, `call_ha_service`, `send_notification`, `get_ha_automations`, `trigger_automation`, `toggle_automation`
- **Notify tools** — HA push, Telegram, Retro Panel toast
- **Automation tools** — list, trigger, toggle HA automations
- **Weather tools** — Open-Meteo forecast (no API key needed)
- **Energy tools** — HA History API integration
- **HA tools** — entity states and area grouping

### Fixed
- `AsyncAnthropic` client initialization
- Error handling in chat dispatch and tool calls
- Weather tools zip safety, unused imports

---

## [0.1.2] — 2026-04-19

### Added
- **AgentEngine** — APScheduler-based scheduler for `monitor` and `preventive` agents, WebSocket listener for `reactive` agents, CRUD persistence to `/data/agents.json`
- **Structured response parsing** — `VALUTAZIONE: [OK|ATTENZIONE|ANOMALIA]` and `AZIONE:` fields stripped from agent output and saved to execution log
- REST API handlers for chat, agent CRUD, and status endpoints
- Comprehensive API test coverage

### Fixed
- Cron expression parsing, `last_run` tracking, WebSocket startup, task error callbacks

---

## [0.1.1] — 2026-04-19

### Added
- **HA Client** — REST client for `/api/states`, `/api/services`, History API; WebSocket client for `state_changed` events with auto-reconnect
- Module restructure: `proxy/`, `tools/`, `api/` sub-packages

### Fixed
- HA client error logging, automations endpoint, async WebSocket startup

---

## [0.0.2] — 2026-04-18

### Added
- Restructured app into `proxy/tools/api` module layout
- Static file serving with 503 guard when UI not yet built

---

## [0.0.1] — 2026-04-18

### Added
- Phase 0 scaffold: HA add-on structure with `config.yaml` (ingress, `stage: experimental`)
- `Dockerfile` based on Python 3.11 HA base image
- `build.yaml`: HA Supervisor base-image declarations for `aarch64` and `amd64`
- `run.sh` entrypoint using bashio for configuration reading
- `aiohttp` server on port 8099
- `GET /` placeholder UI, `GET /api/health` → `{"status": "ok"}`
- `hacs.json`: HACS custom repository metadata
- MIT licence
