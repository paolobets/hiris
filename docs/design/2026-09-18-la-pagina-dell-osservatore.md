# La pagina dell'osservatore — quattro schede, e chi giudica cosa

`spec · 18/09/2026 · riprogetta hiris/app/static/config/watcher-route.js`

Nasce da una richiesta del proprietario: *«è troppo lunga, densa di informazioni non strutturate, e
riporta anche elementi con errori»*. Ogni decisione qui sotto è sua, presa il 18/09/2026 una domanda
alla volta; ogni numero è misurato quel giorno sulla casa vera alla `3.49.0`. Dove un numero non è
misurato, lo si dice.

---

## §0 · Le decisioni, e chi le ha prese

| # | Domanda | Decisione del proprietario |
|---|---|---|
| 1 | A cosa serve la pagina | **Tre mestieri diversi**, oggi a forza in una pagina sola: come sta la casa · cosa ha capito · come sta lavorando |
| 2 | Dove stanno | **Una voce di menu, schede** — non tre voci, non una pagina che riassume |
| 3 | I soggetti tecnici (log, integrazioni) | **Restano, raggruppati per integrazione e in italiano**, col percorso del sorgente solo nel dettaglio |
| 4 | Cosa sta in cima alla scheda del giorno | **Solo ciò che esce dal solito**; la cronaca intera sotto, chiusa |
| 5 | I guasti | Mostrano **la frase vera**, non il livello |
| 6 | Gli elenchi lunghi | **Riassunto coi numeri e i pochi che contano**, elenco intero dietro «vedi tutti» |
| 7 | Il carico | **Ogni scheda legge i suoi dati quando la apri** |
| 8 | Il nome della prima scheda | **«Il giorno»**, e dice sempre quale — non «Oggi», che mostrerebbe ieri |
| 9 | Chi decide cosa è notevole | **Il server, in un posto solo.** La pagina disegna e basta |
| 10 | Le osservazioni dell'analista | **Una scheda propria, «Cosa fare»** — è l'unica cosa che chiede un'azione |
| 11 | L'attuatore | **Non si costruisce adesso**: la pagina apre un ponte verso la chat, e la proposta nasce dove nasce già |

---

## §1 · Le misure (18/09/2026, casa vera, 3.49.0)

1. **La pagina scarica oltre 110 KB e disegna più di 500 righe** in una colonna sola:
   `/api/mind/watching` 86 KB, `/api/mind/knowledge` 27 KB, il resoconto del giorno, le analisi.
2. **Cosa sto guardando: 153 soggetti** — 49 `sensor`, 35 `light`, 9 `switch`, 8 `climate`, 5
   `button`, 3 `binary_sensor`, 2 `person`, 2 `automation`, 1 `weather`, e **39 soggetti tecnici**
   (`log:…` e un `integrazione:…`), che vengono da **30 logger distinti** — 23 integrazioni una
   volta raggruppati. (La prima stesura di questa spec diceva «6 integrazioni»: numero mai
   misurato, corretto il 18/09 contandoli.)
3. **Lasciato fuori: 280 soggetti**, con **128 motivi distinti** scritti in prosa dal modello
   («Comando PTZ di una telecamera, non riguarda energia o comfort»). **Non si raggruppano per
   motivo**: si raggruppano per tipo di cosa — i primi otto tipi coprono 226 dei 280
   (106 `sensor`, 31 `binary_sensor`, 25 `button`, 17 `switch`, 16 `automation`, 11
   `input_boolean`, 11 `notify`, 9 `camera`), i restanti 54 stanno su tipi con pochi soggetti
   ciascuno.
4. **I 39 soggetti tecnici non hanno autore** (`autore: null`): le cose della casa le ha scelte
   l'osservatore, i log nascono dai guasti. Oggi la pagina lascia il vuoto sotto «deciso da».
5. **La cronaca di ieri (17/09): 75 voci** — 65 `funzionamento`, 6 `guasto`, 3 `presenza`, 1
   `sicurezza`. **7 voci su 75 non hanno `nome`**, e sono esattamente i 6 guasti e l'allarme: la
   pagina mostra al loro posto l'identificativo grezzo
   (`log:homeassistant.components.hassio.handler@components/hassio/handler.py:108`).
6. **La frase del guasto c'è già nel dato.** La stessa voce porta `titolo` («Timeout fetching
   hydrawise data») e `dominio` (`homeassistant.components.hydrawise`), scritti dall'osservatore
   (`mind/watcher.py`, `title = message[0]`) e conservati da `mind/facts.py:710`. La pagina li
   ignora e disegna il livello (`ERROR`).
7. **Le analisi portano già «cosa cambierebbe»** — *«spostare i consumi più flessibili nelle ore di
   produzione solare»* — e quel campo ha **un solo lettore in tutta l'applicazione**:
   `watcher-route.js:1338`, che lo stampa come riga di testo.
8. **Nelle analisi il soggetto è un identificativo di dispositivo**
   (`eb941883a1f4429373452e0cda48ef77`) col nome accanto («Alexa»).
9. **La base di un'osservazione varia di sei volte**: una vive su 3 giorni di storia, un'altra su 19
   (campo `base`). La spec dei tre attori impone di dichiarare quando la base è sottile; la pagina
   oggi non mostra il campo.
10. **Non esiste una rotta per creare una proposta**: `/api/constructions` espone solo lettura,
    conferma, rifiuto e ripristino. Una proposta nasce **solo** dal turno di chat che chiama
    `costruisci`.
11. **La chat non sa ricevere un testo già scritto**: nessun parametro di bozza in
    `hiris/app/static/chat/`.
12. **Il resoconto nasce su ieri**, all'aggregazione delle 00:20.

---

## §2 · La cornice

**Una voce di menu, una registrazione nel router, quattro schede.**

- Indirizzi: `#/watcher/giorno`, `#/watcher/cosa-fare`, `#/watcher/sapere`, `#/watcher/lavoro`.
  `#/watcher` nudo viene riscritto su `giorno` **senza aggiungere una voce di cronologia** (lo
  stesso meccanismo che la pagina usa già per correggere l'indirizzo).
- Il clic su una scheda **lascia** una voce di cronologia: «indietro» torna alla scheda precedente, e
  un segnalibro riapre la scheda giusta.
- I quattro pannelli vivono nel DOM insieme; cambiare scheda toglie `hidden` a uno e lo dà agli
  altri. **Lo stato sopravvive**: elenchi aperti, giorno scelto, posizione.
- **Ogni scheda legge i suoi dati alla prima apertura**, mai prima. Aprire «Il giorno» non deve
  scaricare gli 86 KB dell'osservatore.
- In testa a ogni pannello, a dati arrivati: «Letto alle 14:32 · Aggiorna». È l'unico modo per
  rileggere, e dice quanto è fresco ciò che si guarda.
- **L'errore resta dentro la sua scheda**: se il resoconto non si legge, «Cosa ho capito» continua a
  funzionare. Due frasi per due cause diverse (archivio che non risponde, connessione assente), con
  la convenzione già in uso nella pagina e il bottone «Riprova».
- Semantica `tablist`/`tab`/`tabpanel`, frecce destra-sinistra fra le schede, bersagli 44 px.
  **Etichette nude, senza contatori**: un contatore obbligherebbe a caricare tutte le schede
  all'avvio, contro la decisione 7.
- La riga di caricamento di un pannello nascosto **non** ha `aria-live`: sarebbe letta da uno screen
  reader per una scheda che nessuno sta guardando.

---

## §3 · Il lato server: un modulo di lettura, non un campo salvato

Il resoconto **scritto non si tocca**. Nome risolto, marchio «fuori dal solito» e raggruppamenti
nascono **quando la pagina legge**.

**La ragione è una regola della fetta dei giudizi**: la cronaca salvata si rifà solo quando cambia il
giudizio, e l'impronta dice quali giorni rifare. Se «notevole» finisse nella cronaca salvata, il
giorno in cui cambiamo idea su cosa merita la banda — e cambieremo idea — servirebbe rifare 22
giorni per una decisione che col sapere non c'entra. In lettura, cambiarla costa una riga e zero
ricostruzioni.

Il modulo, su un giorno, aggiunge alle voci di cronaca:

- **`nome`, sempre.** Per un soggetto `log:` si ricava dal `dominio` che la voce già porta
  (`homeassistant.components.hydrawise` → «Hydrawise»); per un'entità, il nome vivo. **Nessuna
  pagina inventa un nome.**
- **`notevole_in_banda`** — il marchio, con **`specie_notevole`** (la famiglia: `guasto`, `avviso`,
  `da_sapere_subito`) e **`perche_notevole`** (la ragione scritta nel giudizio, oppure niente). Due
  campi e non uno: se la stessa chiave portasse ora una parola chiusa e ora una frase libera, la
  pagina dovrebbe **riconoscere** quale delle due ha in mano, cioè tornare a decidere.

  **Il criterio lo dice il sapere, con un giudizio suo** (decisione del proprietario, 18/09/2026,
  dopo che la misura ha smentito due stesure di questa spec): il campo si chiama
  **`da_sapere_subito`**, nasce nella fetta `2026-09-18-da-sapere-subito.md` e vale su 16 tipi. La
  regola completa, con il caso dell'allarme `disarmed` che ha fatto scartare la stesura precedente,
  sta nel §3 di quella spec. Qui basta sapere che **questa pagina non contiene nessun criterio**: lo
  legge.

  Misurato su otto giorni (10-17/09): da **0 a 10 righe** al giorno, due giorni con «niente da
  dire». Con la stesura precedente di questa spec sarebbero state 71 righe su 75 il solo 17/09.

Il vantaggio non è solo l'onestà: **il criterio vive nei giudizi, quindi il proprietario può
  correggerlo** dalla scheda «Cosa ho capito», senza toccare il codice. La banda non è un elenco di
  generi cablato nel JavaScript, e nemmeno nel Python.
- **il raggruppamento dei soggetti tecnici** per integrazione, con `volte` e **la finestra** a cui
  quel numero si riferisce: un numero di volte senza finestra non significa niente.

Il contratto cresce di campi e non ne perde nessuno: chi legge già quella rotta continua a
funzionare.

---

## §4 · Le quattro schede

### A · «Il giorno» (`#/watcher/giorno`)

*Com'è andata la casa?*

1. Titolo, e **quale giorno**, in chiaro: «Ieri, mercoledì 17 settembre», col selettore per
   cambiarlo (etichetta legata al campo). **Non** si scrive «resoconto scritto alle 00:20»: il
   contratto del resoconto **non porta nessun istante di scrittura** (misurato il 18/09; la prima
   stesura lo prometteva). Se lo si vorrà dire, prima serve il campo.
2. **«Fuori dal solito»**, sempre visibile. Ordine: sicurezza e presenza, poi guasti, poi avvisi.
   Al massimo cinque righe, il resto dietro «Vedi tutti (N)».
   - **riga di guasto**: `Hydrawise — Timeout fetching hydrawise data` e sotto, in grigio, `Guasto ·
     6 volte · l'ultima alle 14:32`. Il `titolo` è una **citazione**: resta nella lingua in cui Home
     Assistant l'ha scritto, non si traduce. Aprendo la riga: dominio intero, primo istante,
     identificativo grezzo.
   - **riga di un episodio notevole**: il soggetto è **sempre il nome**, e lo stato si **cita**, non
     si interpreta: `Allarme piano terra — triggered · dalle 03:12 alle 03:19`. Scrivere «è
     scattato» sarebbe una traduzione che oggi nessuno fa: rendere gli stati nella lingua della casa
     è una fetta sua, e finché non c'è si cita.
   - **niente da dire** (il caso più frequente): una riga sola, neutra — «Nessun guasto e nessun
     allarme nelle 75 voci di ieri.» Il numero è la prova che ha guardato. **Non** si scrive «tutto
     a posto»: la pagina custodisce, non giudica.
   - **non si può sapere** (resoconto assente, archivio scollegato): «Il resoconto di ieri non è
     stato scritto: non si può sapere cosa è uscito dal solito.»
3. **«Cosa non si sa»**, che compare solo se ha qualcosa da dire.
4. **«Le misure» (67)**: riassunto con un criterio **dichiarato in didascalia**. Misurato il 18/09:
   **47 misure hanno copertura piena e 20 non sono calcolabili**, e nessuna porta una freschezza —
   quindi «le 3 non aggiornate» della prima stesura **non esiste nei dati**. Il criterio è «le 5 con
   la copertura più bassa»; quando sono tutte piene lo si dice, invece di mostrare un elenco vuoto.
   Le 20 non calcolabili vivono in «Cosa non si sa» e **non** si ripetono qui.
5. **«Le forme» (8)**: chiuse.
6. **«La cronaca» (75)**: in fondo, chiusa. Aperta: ordine cronologico con intestazioni d'ora, e le
   voci notevoli con lo stesso aspetto che hanno nella banda.

### B · «Cosa fare» (`#/watcher/cosa-fare`)

*Dove intervenire, e cosa cambierebbe.* Sono le osservazioni dell'analista, oggi sepolte in fondo.

Ogni osservazione dice, in quest'ordine: **cosa ha visto** (in prosa, col valore, la mediana e la
**base di giorni** su cui si regge) · **perché lo dice** (l'innesco, in italiano: «qualcosa è
cambiato», «qualcosa è stabile e costa», «qualcosa non c'è più») · **se è spiegato** · **cosa
cambierebbe** rispetto all'obiettivo · il comando **«Fanne una proposta»**.

- **la base si dichiara sempre**: «su 19 giorni di storia», «su 3 giorni — base sottile».
- **il nome, mai l'identificativo**: `eb941883a1f4429373452e0cda48ef77` sta nel dettaglio.
- **il silenzio è un esito legittimo**: «Nessuna osservazione per il 17 settembre. L'analista tace
  quando ciò che vede è già spiegato.»

### C · «Cosa ho capito» (`#/watcher/sapere`)

*Cosa pensa della casa, e dove sbaglia?* È la sezione 04 di oggi, riordinata.

Riga di peso in testa («99 giudizi · 6 domande aperte · 362 righe di sapere · N corrette da te»),
poi **le 6 domande aperte per intero** — sono l'unica cosa che chiede qualcosa al proprietario, e
non stanno dietro un clic. Poi i giudizi raggruppati per tipo (gruppi chiusi), le correzioni del
proprietario per intero in fondo, il sapere a blocchi. **«Non capito» non compare quando è zero.**

### D · «L'osservatore» (`#/watcher/lavoro`)

*Sta lavorando bene?* È la sezione 01 di oggi, riordinata.

L'obiettivo per primo (è la voce del proprietario), poi tre numeri — guardati, lasciati fuori, righe
al giorno — e la riconsiderazione. Poi:

- **«Cosa guardo» (153)**: «Le cose della casa (114)», raggruppate per chi le ha decise, e
  «Integrazioni e log (39, in 6 integrazioni)», una riga per integrazione con le volte e la
  finestra; il percorso del sorgente solo nel dettaglio. I soggetti tecnici **dichiarano di non
  avere autore**: «nate dai guasti, non scelte».
- **«Lasciato fuori» (280)**: raggruppato **per tipo di cosa**, non per motivo (i motivi sono 128
  frasi diverse). Il motivo scritto dal modello si legge sulla riga, aperto il gruppo: è lì che ci
  si accorge se ha scartato qualcosa che contava.
- **«I tentativi» (10)** e **«Quanto scrive»**: chiusi.

---

## §5 · Il ponte verso l'azione

«Fanne una proposta» **apre la chat con la frase già scritta** — l'osservazione, il suo numero, cosa
cambierebbe — e da lì la strada è quella che esiste: il modello prepara, `costruisci` scrive la
proposta, e l'approvazione resta nella pagina **Proposte**.

Due regole del progetto lo impongono in questa forma: **nessun secondo posto dove si approvano le
cose** (fondamenta: nessun doppione) e **l'attuatore non guadagna un canale di scrittura suo**
(decisione del proprietario, 25/08/2026).

Costo dichiarato: la chat impara **una** cosa, accettare una bozza dall'indirizzo.

**Non è l'attuatore.** L'attuatore sceglie da sé dove intervenire; qui è il proprietario a
decidere quale osservazione diventa una proposta. Chi lo costruirà troverà il posto già pronto: la
scheda «Cosa fare».

---

## §6 · La forma condivisa degli elenchi lunghi

Una forma sola per misure, forme, cronaca, giudizi, sapere, soggetti guardati, lasciati fuori:

```
«Le misure»                                   [h3]
67 misure lette · 3 non aggiornate da più di un giorno   [riassunto]
· Temperatura corridoio — ferma da 2 giorni              [i pochi che contano, max 5]
· Umidità bagno — ferma da 1 giorno
[ Vedi tutte (67) ]                           [bottone 44 px, aria-expanded]
```

- **Al massimo tre numeri** nel riassunto: il totale, la fetta che chiede attenzione, chi l'ha
  decisa se cambia qualcosa. Mai percentuali, mai «+12% rispetto a ieri»: sarebbe una lettura, e la
  pagina custodisce.
- **I pochi che contano** hanno un criterio dichiarato in didascalia («le 3 più vecchie»), mai
  l'ordine di arrivo.
- **Bottone, non `<summary>`**: i `summary` di oggi sono alti 21-23 px, sotto la soglia del tocco.
- L'elenco **si costruisce al clic**, non prima. Il fuoco va sul titolo dell'elenco (`tabindex=-1`);
  alla chiusura torna al bottone.
- Oltre 100 righe: blocchi di 50, col fuoco sulla prima riga nuova.
- Su telefono **nessuno scroll dentro lo scroll**: l'elenco aperto non ha altezza fissa.

---

## §7 · Le prove, e i due cancelli di questa fetta

La parte che **decide** — cosa è notevole, che nome ha una voce di log, come si raggruppa — è codice
puro nel server: si prova in Python sui dati veri, senza browser. Le schede si provano con
`node:test` e jsdom, come il resto del frontend. **Ogni prova nuova si vede rossa prima del codice.**

Due cancelli specifici, perché sono le cose che si rompono in silenzio:

1. una prova che **fallisce se la pagina torna a decidere da sola cosa è notevole** — cioè se in
   JavaScript ricompare un elenco di generi;
2. una prova che **misura il peso di ciascuna scheda**: aprire «Il giorno» non scarica i dati
   dell'osservatore.

E le prove che il progetto già pretende: nessun testo del server scritto come HTML, etichette legate
ai campi, fuoco governato all'apertura e alla chiusura, nessuna emoji.

---

## §8 · Fuori perimetro, dichiarato

- **L'attuatore** che sceglie da sé dove intervenire, e **il verificatore** che misura se l'obiettivo
  si è mosso: sono il terzo e il quarto attore del cervello (25/08/2026), e sono fette loro.
- **I «consumi fuori norma»** nella banda: servirebbe il confronto fra giorni, che è lavoro del
  cervello e non della pagina.
- **Il multiutente** (§11 dei tre attori).
- **Tradurre il `titolo` di un guasto**: è una citazione di Home Assistant, non un nostro testo.

---

## §9 · L'ordine

1. Il modulo di lettura nel server (nome, notevole, raggruppamenti) con le sue prove.
2. La cornice: rotta con la scheda, quattro pannelli, carico pigro, errori isolati.
3. La forma condivisa degli elenchi lunghi.
4. «Il giorno» e la banda.
5. «Cosa fare» e il ponte (compresa la bozza nella chat).
6. «Cosa ho capito» e «L'osservatore».
7. Cancelli, e la verifica dal vivo sulla casa.
