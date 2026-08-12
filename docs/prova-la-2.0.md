# Prova la 2.0

*Foglio della prova aperta l'11 agosto 2026, **aggiornato il 12 agosto** per la build
che riporta l'azione (§4, §5). Accompagna la build che ti è stata
consegnata: si legge in dieci minuti, dice come si parte, cosa aspettarsi, cosa
**non** aspettarsi e cosa segnalare. Non è la documentazione del prodotto — quella
verrà riscritta quando le funzionalità saranno rifatte. Non è un verbale: descrive
al presente la build che hai in mano, quindi si aggiorna quando la build cambia,
invece di restare indietro.*

---

## In una riga

**HIRIS conosce la tua casa, e la tocca quando glielo chiedi tu.** Legge da Home
Assistant piani, aree, dispositivi, entità, automazioni e script; ricorda ciò che gli
dici; e c'è una chat per interrogarlo e per comandarlo. Accende, spegne, imposta —
chiamando i servizi di Home Assistant, **solo** quando glielo chiedi in chat e mai
di sua iniziativa. Non manda notifiche e non scrive automazioni.

**Non ti viene chiesta nessuna conferma prima di un'azione, ed è voluto.** Prima la
capacità, poi le sicurezze, in una fase pensata apposta: quello che c'è al posto
della conferma è una **verifica** — prima di chiamare un servizio HIRIS controlla
sulla *tua* installazione che quel servizio esista, che l'entità esista e che i
parametri siano suoi; e dopo aver chiamato **rilegge lo stato**, così ti racconta
cos'è successo davvero invece di cos'era stato chiesto. Se non è cambiato niente,
te lo dice.

Il tratto che stiamo mettendo alla prova è un altro, ed è quello che ti chiediamo di
guardare per primo: **HIRIS deve dichiarare ciò che non sa invece di fingerlo.** Una
tessera che dice «non letto» al posto di uno zero è la funzione, non il guasto.
Quando lo vedi mentire — uno zero al posto di un «non lo so», una risposta sicura su
una cosa che non ha letto — quella è la segnalazione che vale di più.

---

## 1. Installare

**Serve**: Home Assistant **2024.7.0** o successivo, su architettura **amd64** o
**aarch64**. Su altre architetture non è installabile: non è un guasto
dell'installazione, non è compilato per quelle.

**Dallo store degli add-on**

1. Impostazioni → Add-on → Add-on Store → menù ⋮ → **Repository**
2. Aggiungi `https://github.com/paolobets/hiris`
3. Cerca **HIRIS** → Installa

**Da HACS**, in alternativa: ⋮ → Repository personalizzati → stesso URL, categoria
**Add-ons**, poi installa dalla sezione Add-ons.

**Dopo l'installazione**, prima di avviare: apri la scheda **Configurazione** e
scegli una delle strade del punto 2. Senza, l'add-on parte lo stesso ma la chat non
ha nessuno a cui chiedere.

HIRIS si apre **dentro Home Assistant** (ingress): dalla pagina dell'add-on con
«Apri interfaccia web», e dalla barra laterale se lasci attivo «Mostra nella barra
laterale». Non devi aprire nessuna porta. Nella sezione **Rete** della pagina
dell'add-on (visibile solo con la Modalità avanzata di HA) compare una porta
`8099/tcp`: **lasciala vuota** — serve a sessioni di diagnostica, e senza HTTPS
espone l'API a chiunque sia sulla tua rete.

---

## 2. Le opzioni, e le strade per far rispondere la chat

**Nessuna opzione è obbligatoria per far partire l'add-on.** HIRIS parte, legge la
casa e ti mostra cosa sa anche senza una sola credenziale. Quello che manca, senza
credenziali, è la risposta: al primo messaggio la chat risponde con un errore che
nomina i campi da compilare per le due strade principali — l'abbonamento e la
chiave API Claude.

Vale una regola sola, ovunque: **un provider è usato solo se è attivo *e* ha la sua
credenziale.** Attivare il toggle senza incollare la chiave non serve a niente, e
incollare la chiave senza attivare il toggle nemmeno.

> Una nota per chi aggiorna da una versione precedente: se lasci **tutti** i toggle
> `provider_*` spenti, HIRIS continua a derivare i provider attivi dalle credenziali
> che trova (retro-compatibilità). Appena ne accendi **uno qualsiasi**, valgono solo
> i toggle accesi: riattiva a mano ogni provider che vuoi tenere.

### Strada A — abbonamento Claude Max

Due campi:

- **Attiva provider: Abbonamento (Claude Max)** → acceso
- **Token OAuth Claude Code (abbonamento)** → il token. Lo ottieni su una macchina
  dove Claude Code è già installato e autenticato, con `claude setup-token`, e
  incolli qui la stringa che stampa.

Con questi due presenti, la chat viene instradata sull'abbonamento **anche se
lasci spente** «Ponte abbonamento — attiva» e «Chat via abbonamento — attiva». Non
è un difetto da segnalare: è scritto nel codice ed è dichiarato nelle descrizioni
delle opzioni. Su questo percorso valgono anche:

- **Ponte abbonamento — scadenza (minuti)**: 5 di default, entro cui la risposta
  deve arrivare;
- **Chat via abbonamento — cap messaggi/giorno**: 50 di default. Superato il tetto
  la chat risponde con un errore e il messaggio **non parte**: non c'è ripiego
  automatico su un altro provider;
- **i consumi non si misurano.** L'abbonamento non espone né i token né il costo
  della singola risposta, e la pagina Consumi lo dichiara invece di mostrare zeri.

### Strada B — chiave API a consumo

- **Attiva provider: API Claude** → acceso, più **Chiave API Claude**.
- Stessa forma per OpenAI e OpenRouter, ciascuno col suo toggle e la sua chiave.

Qui i consumi si misurano: richieste, token, costo, sulla pagina Consumi e nel
riquadro «Utilizzo» della chat.

### Strada C — Ollama, tutto in casa

**Attiva provider: Ollama (locale)** più **URL Ollama** e **Nome Modello Ollama**
(e, se l'hardware è lento, alza il **Timeout richiesta Ollama**, default 120 s).
Con questa strada HIRIS funziona senza nessuna chiave verso l'esterno.

### Quale strada sto usando davvero?

Due modi per accorgersene, senza aprire i log:

- **la pagina Consumi**: se sei sull'abbonamento, dice a parole che su quel percorso
  i consumi non si misurano; se non hai nessun provider, dice che non c'è niente da
  misurare; altrimenti mostra i contatori;
- **cosa dice l'attesa dopo due minuti**: sul percorso diretto compare *«Tieni
  aperta questa pagina: se la chiudi, questa risposta si perde»*; sul percorso ad
  abbonamento *«Puoi anche chiudere: se arriva, la risposta finisce nella
  cronologia»*. Le due frasi sono diverse perché il fatto è diverso.

### Le altre opzioni che ti riguardano

| Opzione | A cosa serve nella prova |
|---|---|
| **Tema** | `light`, `dark`, `auto`. Attenzione: vedi il limite n. 7 più sotto |
| **Livello Log** | metti `debug` prima di riprodurre un problema che vuoi segnalare |
| **Conservazione Cronologia (giorni)** | 90 di default; i messaggi più vecchi vengono cancellati alle 03:00 |
| **Token Interno** | **lascialo vuoto.** HIRIS ne genera uno al primo avvio e lo conserva: resta lo stesso a ogni riavvio e non devi farci niente |
| **CIDR ingress Supervisor fidata** | non toccarla se non sai di doverla toccare |
| **Debug — warning esposizione porta** | da solo non apre nessuna porta: logga un promemoria. Lascialo spento |

**Resta dalla 1.x e non serve a questa prova**: `Embedding (oggi inattivi)` —
provider e modello. Le due opzioni si leggono ancora e la pagina Modelli le
mostra, **ma oggi non hanno alcun effetto**: nessuna parte di HIRIS calcola
embedding. Lasciale vuote. Le opzioni `Mayan EDMS` non esistono più: dalla
2.1.0 l'integrazione documentale è uscita.

### Quando serve riavviare

Le opzioni dell'add-on si leggono **all'avvio**: dopo averle cambiate, riavvia
l'add-on o non cambia niente. L'unica eccezione è la pagina **Impostazioni chat**
dentro HIRIS (nome, prompt di sistema, modello, forma della risposta, budget di
ragionamento, tetto di turni, «rispondi solo su argomenti di casa»): lì il
salvataggio vale **dal messaggio successivo**, senza riavviare.

---

## 3. Cosa aspettarsi la prima volta

**All'avvio** HIRIS legge i registri di Home Assistant e costruisce l'anagrafe della
casa, poi legge `automations.yaml` e `scripts.yaml` e le plance Lovelace. Se Home
Assistant non è ancora pronto, **la costruzione fallisce senza impedire l'avvio**:
l'anagrafe resta vuota, il log lo dice, e si rifà da sola al primo evento di
registro (con tre secondi di attesa, per non rileggere dieci volte se stai
spostando dieci entità). Se resta vuota e non si riempie, riavvia l'add-on.

**Quanto ci mette**: non lo sappiamo. Nessuno ha ancora misurato la prima lettura su
una casa vera. È una delle cose che ci servono da te.

**Poi, mentre gira**: l'inventario delle entità si ricarica ogni 2 minuti, e una
sentinella controlla ogni 5 minuti se i file di automazioni e script sono cambiati
(per gli script è l'unico segnale che esista: Home Assistant non emette un evento
di ricarica). La cronologia vecchia si cancella alle 03:00.

**La chat** è la prima cosa che vedi. In alto compaiono la versione con l'impronta
dell'interfaccia (`v2.0.0 · qualcosa`) e un pallino *connesso/offline*: la prima
serve nelle segnalazioni, il secondo dice se la pagina sta parlando con l'add-on.

**«Cosa HIRIS sa»** è la pagina da aprire subito dopo: dalla chat, «Configurazione»
in fondo alla colonna di sinistra — è la prima pagina che si apre. Contiene:

- **L'anagrafe della casa**: quando è stata letta e quante voci per registro (piani,
  aree, dispositivi, entità, etichette, categorie, integrazioni);
- **Ciò che la casa sa fare da sola**: automazioni e script, e — numero importante —
  **di quante voci HIRIS conosce solo il nome e non il corpo**;
- **Le plance di Home Assistant** che è riuscito a leggere;
- **Il nucleo, come lo vede il modello**: il testo **esatto** che finisce nel
  contesto a ogni turno di chat, parola per parola, non una sua descrizione. Sopra
  al testo trovi «Ciò che HIRIS ignora», i caratteri, se il testo è stato troncato e
  quanti ricordi sono rimasti fuori.

### «Non letto» è una funzione, non un guasto

Questa pagina distingue **tre** stati, non due, e li rende in tre modi diversi:

- **un numero** — ho guardato, ce n'è questa quantità;
- **zero** — ho guardato, non c'è niente;
- **«non letto»**, colorato diversamente, con accanto la ragione — **non ho
  guardato**, oppure quel registro non ha risposto.

Se una tessera dice «non letto», HIRIS ti sta dicendo che quel dato non ce l'ha. È
la cosa giusta. Il difetto sarebbe l'opposto: uno zero, o un «tutto a posto», dove
la lettura non è avvenuta. **Se vedi uno zero che sospetti sia un «non lo so»
travestito, segnalalo**: è il difetto storico di questo prodotto ed è esattamente
ciò che questa build vuole aver chiuso.

Lo stesso vale nella chat: con Home Assistant irraggiungibile il nucleo non scrive
«niente di notevole», scrive che lo stato non è stato letto — e che non è la stessa
cosa.

---

## 4. Cosa chiedere alla chat

Il modello riceve il nucleo (la casa condensata) più **cinque strumenti**. Quattro
leggono e ricordano: `cerca` (trova per nome o alias), `guarda` (il dettaglio di una
cosa sola), `ricorda` (salva ciò che hai detto), `richiama` (i ricordi legati a una
parte della casa). Il quinto, `esegui`, è l'unico che tocca Home Assistant: chiama un
servizio — verificato prima, con lo stato riletto dopo.

Sette richieste che li esercitano davvero:

1. **«Quante luci ci sono al piano di sopra?»** — risponde dal nucleo, che **conta
   invece di elencare**: le entità di una casa non entrerebbero tutte nel contesto,
   quindi HIRIS porta i numeri e va a guardare il dettaglio solo quando serve.
2. **«Cosa c'è di acceso o aperto adesso?»** — la sezione «Notevole adesso» del
   nucleo. Se lo stato non è stato letto, deve dirlo invece di rispondere
   «niente».
3. **«Trova il termostato del salotto»** — `cerca`. Se in casa hai due cose che si
   chiamano allo stesso modo (due «Bagno» su piani diversi, un alias che collide),
   lo strumento restituisce **tutti** i candidati e marca il risultato come ambiguo,
   con l'istruzione esplicita di non prendere il primo: HIRIS dovrebbe chiederti
   quale intendi. Se hai nomi duplicati, provalo — è uno dei comportamenti che
   vogliamo vedere sbagliare.
4. **«Cosa fa esattamente l'automazione "Buonanotte"?»** — `guarda`, che restituisce
   anche **il corpo** dell'automazione. Se quell'automazione è scritta a mano fuori
   dai file che HIRIS legge, deve dirti che ne conosce il nome e non il corpo, non
   inventarne il contenuto.
5. **«D'inverno il soggiorno sta bene a 19.5»** — `ricorda`. La frase si salva per
   intero, così come l'hai detta, agganciata al soggiorno. Riaprila al turno dopo:
   deve ricomparire nel nucleo, sotto «Ciò che le persone hanno detto». Se HIRIS
   prova ad agganciarla a qualcosa che in casa tua non esiste, **quell'aggancio non
   viene scritto** e lo scarto viene dichiarato: la frase però resta salvata tutta.
6. **«Cosa ti ho già detto sulla cucina?»** — `richiama`. Nessun ricordo non
   significa «la casa non ha ricordi»: significa che nessuno di quelli salvati
   nomina proprio la cucina.
7. **«Spegni la luce della cucina»** — `esegui`. È la novità di questa build, ed è
   quella su cui ti chiediamo di essere più severo. Guarda tre cose, in quest'ordine:
   che **spenga quella giusta** (se in casa hai due «cucina», deve chiedertelo invece
   di tirare a indovinare — è lo stesso comportamento del punto 3, applicato a
   qualcosa che poi succede per davvero); che ti racconti **cos'è cambiato**, non
   cos'ha chiesto; e che quando **non cambia niente** — la luce era già spenta,
   oppure il servizio è andato ma lo stato è rimasto uguale — te lo dica, invece di
   dichiarare un successo. Prova anche a chiedergli qualcosa di impossibile
   («imposta il colore del termostato»): deve dirti **cosa** non esiste, non «non
   posso».

**Se hai mezz'ora e un impianto vero**, `prova-azione.md` (in questa stessa cartella)
è il foglio delle nove prove che mettono alla prova solo `esegui` — cosa deve succedere
e come si riconosce il fallimento, riga di log per riga di log. La prima di quelle prove
va fatta prima di tutte le altre.

**Sotto la risposta**, quando il modello ha usato uno strumento, compaiono delle
targhette con il nome dello strumento: cliccale per vedere con quali argomenti è
stato chiamato. Servono a te per capire se ha davvero guardato o ha risposto a
memoria, ed è il modo più immediato di accorgersi che un `ricorda` ha scritto
qualcosa: la verifica definitiva resta la pagina Memoria.

**I ricordi si guardano e si correggono** nella pagina **Memoria** della
configurazione: lì puoi rivedere l'interpretazione che HIRIS ha dato a una frase
(forza, valore, chi l'ha detta) e cancellare un ricordo. La cancellazione è
definitiva e la conferma ti mostra la frase esatta prima di procedere.

---

## 5. Cosa NON fa

Nessuna di queste è un difetto da segnalare. Sono scelte, e sono la ragione per cui
questa versione esiste.

- **Non costruisce.** Non crea né modifica automazioni, script, scene o dashboard.
  Chiamare un servizio sì (`esegui`, §4): scrivere oggetti dentro Home Assistant no.
  Questo è ciò che tornerà rifatto quando HIRIS saprà **costruire**, ed è un progetto
  a sé.
- **Non ti scrive mai per primo.** Niente notifiche, niente Telegram, niente
  messaggi push, niente promemoria. Parla solo quando gli parli tu.
- **Non ragiona da solo, e non agisce da solo.** Niente agenti, niente sentinella,
  niente ronde, niente proposte da approvare, niente segnalazioni. Ogni azione nasce
  da una frase che hai scritto tu in chat: non esiste nessun percorso — orario,
  evento, regola — che possa farne partire una senza di te.
- **Non ha un semaforo dei permessi.** Non esistono livelli, liste di divieti,
  conferme rinforzate. Adesso che HIRIS agisce questa è una scelta, non una
  conseguenza: prima la capacità, poi le sicurezze, disegnate sui rischi veri di
  questa struttura e non ereditate dalla 1.x. Se ti pare che manchi un freno,
  **segnalalo lo stesso** — è esattamente il materiale che serve alla fase dopo.
- **Niente MQTT, niente gateway, niente Test Run.**
- **Non c'è la card per le dashboard.** Se avevi la card della 1.x, quel riquadro
  smette di funzionare: al primo avvio HIRIS **disinstalla da solo** ciò che aveva
  installato (i file e la risorsa Lovelace che aveva registrato lui, nient'altro).
  A te resta da togliere il riquadro vuoto dalla dashboard.
- **Non ci sono più assistenti da creare e configurare.** C'è una conversazione
  sola, e si imposta dalla pagina «Impostazioni chat».
- **Le risposte non arrivano parola per parola.** L'interfaccia web aspetta e poi
  mostra la risposta intera: se sembra ferma, sta aspettando. L'indicatore d'attesa
  ti dice a che punto è (punto 4 della sezione successiva).
- **L'interfaccia web parla solo italiano**, anche se le opzioni dell'add-on nel
  Supervisor sono tradotte in due lingue.

---

## 6. I limiti di questa build, dichiarati

**È la sezione più utile di questo foglio.** Qui sotto c'è l'elenco delle cose che
**nessuno ha potuto verificare** prima di consegnarti la build: le abbiamo
controllate leggendo il codice, o rendendo le pagine in un browser fuori da Home
Assistant, con dati inventati. Tu hai le tre cose che a noi mancavano: Home
Assistant vero, un dispositivo vero in mano, e una casa vera dentro. Ognuno dei
punti qui sotto è un posto in cui non siamo arrivati: leggilo come un compito, non
come una scusa.

**1. La cornice vera di Home Assistant.** Le pagine sono state guardate aperte da
sole in un browser, non dentro l'iframe di HA: mancavano la barra laterale, il tema
e il percorso di ingress veri. Non sappiamo come si comporta la **doppia barra di
scorrimento** (quella di HA più quella della pagina), se la larghezza reale
dell'iframe cade nella fascia in cui la barra di navigazione della configurazione si
stringe, se i link relativi reggono con e senza `/` finale, e se qualche stile di
Home Assistant filtra dentro. Guarda proprio qui, e su più larghezze di finestra.

**2. Un dispositivo touch vero.** Le aree toccabili sono state misurate in
geometria, non col dito. In particolare, tre cose sono **dedotte dal codice e mai
osservate**: che la tastiera di sistema non faccia più "saltare" la pagina quando
mandi un messaggio; che il campo di testo si comporti bene su iOS mentre HIRIS
elabora; e che **Maiusc+Invio vada a capo senza inviare** anche con la tastiera di
un tablet (la regola che lo governa riconosce un solo modo di produrre l'a capo:
una tastiera che ne usasse un altro potrebbe non andare a capo affatto). Provale con
un dito vero, su un tablet vero.

**3. Una casa vera, con dentro dei dati veri.** Le prove sono state fatte su dati
inventati. Non sappiamo cosa succede con **40 aree e 2.000 entità** (su quante righe
si dispongono le tessere?), con un **nucleo da 60.000 caratteri** dentro il suo
riquadro, con **200 ricordi** nella pagina Memoria, o con una risposta lunga
3.000 caratteri piena di tabelle. Se la tua casa è grande, sei tu la prova.

**4. Il tempo.** L'attesa cambia aspetto a **10 secondi** (compare il cronometro),
a **30 secondi** (ammette che ci sta mettendo troppo) e a **2 minuti** (dice che
fine fa il turno se chiudi la pagina). Quelle tre soglie sono state calibrate sulla
letteratura, **non su tempi misurati su questo prodotto: nessuno li ha ancora
raccolti.** Annota quanto ci mette davvero a risponderti, sui due percorsi: se il
percorso diretto sta quasi sempre sotto i 6 secondi la soglia dei 10 è giusta, se
sta spesso a 15 va alzata. Sul percorso ad abbonamento l'attesa si arrende dopo
**5 minuti** e te lo dice; la risposta, se arriva dopo, la ritrovi ricaricando.

**5. I caratteri.** Tutt'e due le pagine (chat e configurazione) chiedono i loro
font a Google. Nelle prove non erano
raggiungibili, quindi sono state viste con i caratteri di ripiego: interlinee,
larghezze e troncature saranno leggermente diverse da come le vedi tu. E se il
tablet non arriva a Internet — o non arriva a Google — **vedrai anche tu i caratteri
di ripiego**: dicci quale dei due casi ti è capitato.

**6. Uno screen reader vero.** Ruoli, nomi ed etichette sono stati controllati
leggendo il codice della pagina. **NVDA e VoiceOver non sono mai stati accesi**:
l'ordine reale degli annunci durante un'attesa lunga va sentito, non dedotto.

**7. Il tema si congela nel browser.** Alla prima apertura della pagina di
configurazione, il tema in uso viene scritto nella memoria del browser. Da quel
momento **l'opzione «Tema» dell'add-on non ha più effetto su quel browser**: vince
la scelta memorizzata, e il pulsante sole/luna dentro HIRIS è l'unico modo di
cambiarla. È verificato nel codice e osservato; è un difetto noto, non serve
segnalarlo di nuovo — ma sappilo, prima di concludere che l'opzione è rotta.

**8. Il ponte dell'abbonamento: gli strumenti ci sono, ma non sempre.**
Su quel percorso la chat non riceve solo la conoscenza della casa: riceve anche gli
strumenti, `esegui` compreso. Prima di ogni turno HIRIS verifica che ci siano davvero,
e se non ci sono **te lo dice in una riga premessa alla risposta**
(*«In questo turno non ho potuto usare gli strumenti per guardare la casa…»*)
invece di rispondere come se niente fosse — e in quel caso non può nemmeno agire.
Guarda quale dei due stati capita sul tuo impianto: te lo dicono le targhette degli
strumenti sotto la risposta, e quella riga premessa quando mancano. *(Fino alla
build precedente la descrizione dell'opzione nel Supervisor era rimasta indietro e
negava gli strumenti; adesso è allineata al codice.)*

**9. Le risposte in elenco si vedono grezze.** Il testo della chat riconosce solo il
**grassetto**, il `codice` e l'a capo. Se il modello risponde con un elenco
puntato o con dei titoletti, li vedi scritti alla lettera (`- `, `## `). È noto e non
ancora corretto: non serve segnalarlo, ma tienine conto quando giudichi la qualità
di una risposta — quella brutta potrebbe essere la forma, non il contenuto.

**10. «Nuova conversazione» cancella più di quel che sembra.** Il pulsante svuota i
messaggi che vedi **e i riassunti delle conversazioni precedenti** che HIRIS si tiene
da parte per il turno dopo. Non si può annullare, e la conferma te lo dice. I
ricordi salvati con `ricorda` **non** vengono toccati: quelli vivono nella pagina
Memoria e si cancellano solo da lì. È una decisione di prodotto ancora aperta —
se ti sembra sbagliata, dillo: è il momento giusto.

---

## 7. Come si segnala un problema

Una segnalazione utile costa due minuti in più e ne fa risparmiare un'ora.

**Cosa scrivere sempre**

1. **Cosa ti aspettavi, cosa hai visto.** Nell'ordine, e separate.
2. **Come si rifà.** I passi, anche banali.
3. **Quale strada stavi usando**: abbonamento Claude Max, chiave API (quale
   provider), o Ollama. Cambia il percorso interno, e cambiano i sintomi.
4. **Versione e impronta**: leggile in cima alla chat (`v2.0.0 · …`). Il numero di
   versione da solo non distingue due build consegnate a poca distanza — resta
   `2.0.0` per entrambe. L'impronta accanto è calcolata sui file dell'interfaccia:
   **cambia se è cambiato il frontend**, e serve a capire se stai guardando la build
   nuova o una pagina rimasta in cache. Se fra le due build è cambiato solo il
   codice Python, l'impronta è la stessa: in quel caso dicci **quando** l'hai
   installata.
5. **Dove stavi guardando**: browser e versione, se era un telefono/tablet o un
   computer, e **quanto era largo lo schermo o la finestra** — diversi dei difetti
   già trovati compaiono solo in certe fasce di larghezza. E se eri dentro Home
   Assistant o avevi aperto HIRIS in una scheda a parte.

**I log dell'add-on** stanno nella pagina dell'add-on dentro Home Assistant, nella
scheda **Log**. Prima di riprodurre il problema, metti **Livello Log** su `debug` e
riavvia: la riga che serve spesso non c'è al livello `info`. Copia il pezzo di log
che circonda l'orario del problema, non l'intero registro.

**Se il problema è nella pagina** (qualcosa che non compare, un pulsante che non
risponde, un errore), apri la console del browser e allega quello che ci trovi
dentro: alcune pagine scrivono lì il dettaglio tecnico invece di sporcare
l'interfaccia.

**Un'attenzione, prima di incollare**: il nucleo e i log possono contenere i nomi
delle tue stanze, delle tue entità e le frasi che hai detto alla chat. Guarda cosa
stai allegando.

**Cosa è più prezioso di un bug**: una frase in cui HIRIS **ha dichiarato con
sicurezza qualcosa che non sapeva**. Uno zero al posto di un «non lo so», un'automazione
di cui inventa il contenuto, un ricordo che dice di aver salvato e non trovi nella
pagina Memoria. Quella classe di errore è il motivo per cui questa versione esiste,
ed è quella che vogliamo sapere per prima.
