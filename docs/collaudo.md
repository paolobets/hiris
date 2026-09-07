# Il collaudo di HIRIS

*Foglio unico, scritto il **7 settembre 2026** per la **3.22.1**. Sostituisce
`prova-la-2.0.md`, `prova-azione.md` e `prova-modelli-e-catena.md`, che descrivevano al presente
le versioni 2.0, 2.2 e 2.5 e sono rimasti indietro di venti versioni.*

> **Si aggiorna quando il prodotto cambia, o non serve a niente.** Un foglio di collaudo che
> descrive una versione vecchia produce decine di scostamenti che **non sono difetti**, e quelli
> veri ci si perdono in mezzo. Se esegui questo foglio e una prova non corrisponde più al
> prodotto, la prova è da riscrivere: dillo, non ignorarla.

---

## Come si esegue

Serve **una casa vera** con Home Assistant e HIRIS installato. Due vie d'accesso:

- **l'interfaccia**, dal pannello dell'add-on in Home Assistant;
- **l'API interna** su `:8099`, che risponde solo con l'intestazione `X-HIRIS-Internal-Token`
  (il token sta in `~/.hiris-debug-token`, e **non si scrive mai** in un messaggio, un log o un
  documento).

**La porta 8099 non è dichiarata nel manifesto**: è un'impostazione dell'utente nella sezione
Rete di Home Assistant, e **ogni aggiornamento la riporta a «non esposta»**. Se rifiuta la
connessione, il primo sospetto è quello — o che l'add-on non stia girando affatto.

Per guidare l'interfaccia da un browser automatico serve che il token arrivi a ogni richiesta:
la via pulita è un **proxy locale** che inietta l'intestazione, così il token non lascia la
macchina.

**Ogni prova ha tre righe**: cosa si fa, cosa deve succedere, e **cosa sarebbe un fallimento**.
La terza è la più importante: senza, si finisce a guardare un risultato e a convincersi che vada
bene.

---

## A · L'avvio

### A1 — L'add-on parte e dichiara la propria versione

**Si fa**: si apre il pannello. **Deve**: caricare, e mostrare in basso a sinistra `vX.Y.Z` uguale
alla versione installata (`update.hiris_update` in Home Assistant lo conferma).
**Fallimento**: pagina bianca, `401`, o una versione diversa da quella installata — significa che
il browser sta guardando una copia in cache.

### A2 — Nessun errore di console, su nessuna pagina

**Si fa**: si percorrono tutte e nove le rotte del pannello raccogliendo gli errori di console e
le risposte HTTP ≥ 400. **Deve**: zero errori, zero risposte fallite.
**Fallimento**: qualunque `PAGEERROR`, o un `404` su una risorsa dell'app (non su una rotta
inventata da chi prova).

### A3 — Le nove rotte esistono e sono quelle documentate

**Si fa**: si leggono gli `href` veri del menu e si confrontano col README.
**Deve**: coincidere. **Fallimento**: una rotta documentata che non esiste — è successo, ed è la
ragione per cui questa prova c'è.

### A4 — I campi di ogni pagina sono quelli documentati

**Si fa**: si apre `#/settings` e si contano i campi veri mostrati a schermo; si confrontano col
numero e coi nomi che il README dichiara per quella rotta.
**Deve**: coincidere — oggi sono sette (nome, prompt di sistema, forma della risposta, budget di
ragionamento, tetto di turni, giorni di conservazione, restrizione casa).
**Fallimento**: un campo mostrato a schermo che il README non nomina, o viceversa — è la stessa
famiglia di scostamento di A3 (il codice cambia, il documento resta indietro), ma su un contenuto
che un cancello di **conta** non basta a vedere: A3 conta le rotte E ne confronta l'identità;
qui il numero solo («sette») avrebbe già mascherato una volta la stessa divergenza («sei» campi
elencati mentre il codice ne montava sette) — servono i **nomi**, non il conteggio.

---

## B · Le fonti che HIRIS legge

### B1 — Il registro di sistema

**Si fa**: `tools/call` su `system_log`. **Deve**: tornare `voci` con le righe **come Home
Assistant le manda** — `name`, `message`, `level`, `source`, `count`, `first_occurred` — e i
livelli devono comprendere `WARNING`, non solo `ERROR`.
**Fallimento**: un elenco vuoto quando Home Assistant ha voci nel registro; oppure `voci: []`
al posto di un `errore` quando la lettura fallisce — **un elenco vuoto non deve mai poter dire
«non c'è niente che non va»**.

### B2 — Le tracce di un'automazione

**Si fa**: si sceglie un'automazione **scattata di recente** (l'attributo `last_triggered` in
Home Assistant lo dice) e si chiama `automation_trace` con il suo `entity_id`.
**Deve**: tornare fino a **cinque** tracce con `timestamp.start` e `script_execution`.
**Fallimento**: un elenco **vuoto** su un'automazione che è appena girata. Sarebbe il ritorno del
difetto peggiore di questa fetta: HIRIS archivia le tracce sotto l'**id di configurazione**
(`1758128590523`), non sotto l'`object_id` — e con la chiave sbagliata la risposta è vuota
**sempre**, dicendo «questa automazione non ha mai girato».

### B3 — I calendari

**Si fa**: `tools/call` su `calendar`. **Deve**: tornare `calendari_guardati` con **tutti** i
calendari della casa, gli `impegni` ordinati per data e **etichettati col calendario di
provenienza**, e la chiave `non_letti` **solo** se qualcuno non ha risposto.
**Fallimento**: un calendario che sparisce senza comparire fra i non letti; `non_letti` presente
quando sono stati letti tutti; o un impegno senza il proprio calendario.

### B4 — La fine esclusiva dei giornalieri

**Si fa**: si cerca un impegno **giornaliero** fra quelli restituiti (`giornaliero: true`).
**Deve**: per un evento di un giorno solo, `inizio` e `fine` devono essere **lo stesso giorno**.
**Fallimento**: la fine è il giorno **dopo**. Home Assistant manda la fine **esclusiva** — un
evento del 14 arriva come `end: 2026-09-15` — e sbagliarlo sposta ogni evento giornaliero di un
giorno: «siamo in ferie fino al 31» invece che «fino al 30».

---

## C · Rifiutare invece di indovinare

### C1 — La ricerca dice quando non ha capito

**Si fa**: `search` con un testo che in casa non esiste (`"xyzzy qwerty non esiste"`).
**Deve**: tornare `nulla_riconosciuto: true` e un `suggerimento` che dice che **non è detto che
la cosa non esista** — la ricerca ha guardato **i nomi**, non l'inventario.
**Fallimento**: un elenco vuoto e basta. Il modello lo leggerebbe come «questa cosa non c'è in
casa», che è un'affermazione diversa e non verificata.

### C2 — Un argomento obbligatorio mancante nomina il campo

**Si fa**: `trend` senza `ore`. **Deve**: un errore che **nomina «ore»**.
**Fallimento**: la chiamata arriva al gestore e risponde qualcosa, oppure un «argomenti non
validi» che non dice quale campo manca — il modello non ha modo di correggersi.

### C3 — Un nome d'argomento sconosciuto è un errore, non un silenzio

**Si fa**: `trend` con `orario` al posto di `ore`. **Deve**: un errore che **nomina «orario»**;
e se mancano **entrambe** le cose, la risposta le dice **tutte e due**.
**Fallimento**: l'argomento ignoto viene ignorato in silenzio, e chi ha sbagliato il nome riceve
una risposta come se avesse chiesto un'altra cosa.

### C4 — La chat non inventa l'ora di un messaggio ripristinato

**Si fa**: si manda un messaggio, si annota l'ora vera che compare sulla bolla, si ricarica la
pagina **più tardi** (almeno un minuto dopo) e si guarda di nuovo la bolla dello stesso messaggio
— compresa la primissima domanda della sessione.
**Deve**: l'ora resti quella di prima, presa dal `timestamp` che `GET api/chat/history` porta per
ogni messaggio — **non** l'ora del ricaricamento.
**Fallimento**: tutte le bolle mostrano la stessa ora, quella di **adesso** — il sintomo misurato
il 07/09/2026: alle 08:28 ogni bolla diceva «08:28», ricaricando alle 08:33 tutte dicevano «08:33»,
compresa la domanda con cui la conversazione era iniziata molto prima.

### C5 — Il costo non misurabile si dichiara, non si azzera

**Si fa**: si guarda «Utilizzo» nella barra laterale della chat e la tessera «Costo» in `#/usage`
in una casa dove l'unico uso registrato è l'abbonamento — nessun'altra sezione con un costo noto
in `sections` (`GET api/usage`).
**Deve**: comparire una dichiarazione esplicita («in abbonamento» o equivalente) al posto del
numero — mai «€ 0,00». La stessa regola che una sezione già rispetta scrivendo «Compreso» invece
di 0,00 per il singolo modello.
**Fallimento**: «€ 0,00» senza nessuna spiegazione accanto — il sintomo misurato: *«Richieste 99 ·
Token input 7.20M · Costo € 0,00»*. Si legge o come «gratis» o come «rotto», la stessa confusione
a tre stati (misurato / zero vero / non misurabile) che l'archivio della casa combatte ovunque.

---

## D · Le specifiche di Home Assistant

### D1 — Il vocabolario tace quando è aggiornato

**Si fa**: si legge il nucleo (`/api/briefing`) e si cerca la riga sulla freschezza del
vocabolario. **Deve**: **non esserci**, se la casa è alla stessa versione di Home Assistant su cui
il vocabolario è stato verificato.
**Fallimento**: la riga compare comunque. Direbbe al modello, a **ogni turno**, che c'è qualcosa
da riverificare quando non c'è.

### D2 — Il vocabolario parla quando è invecchiato

**Si fa**: quando la casa passa a una versione di Home Assistant **successiva** a quella del
vocabolario. **Deve**: comparire **una** riga sotto «Riferimento:», che invita a rileggere la
documentazione e **dichiara che non è un errore**.
**Fallimento**: silenzio (il vocabolario invecchia senza che nessuno lo sappia), oppure un
allarme fra le cose che non vanno in casa.

### D3 — Le capacità di un'entità sono lette, non dedotte

**Si fa**: `view` su una luce che dichiara `supported_features` con dei bit accesi.
**Deve**: comparire `capacita` con **parole** (`transizione`, `effetti`), e **non** deve comparire
il numero grezzo `supported_features` accanto.
**Fallimento**: il numero nudo a schermo — è l'invito a indovinare che questa fetta esiste per
togliere. Oppure `capacita: []` su un'entità che non dichiara niente: le chiavi che non hanno
niente da dire **non escono**.

---

## E · L'osservatore

### E1 — Guarda anche le condizioni di sistema

**Si fa**: `/api/mind/watching`. **Deve**: comprendere, oltre alle entità del pavimento, i
soggetti `log:` (le voci di errore del registro di Home Assistant) e, quando ce ne sono, i
`problema:`, `integrazione:` e `automazione:`.
**Fallimento**: solo entità. Vorrebbe dire che le condizioni di sistema non sono sorvegliate, o
che `watching()` non le elenca.

### E2 — A schermo non resta un prefisso tecnico

**Si fa**: si apre la pagina dell'osservatore e si **espandono tutti i gruppi** di «Cosa sto
guardando» (sono `<details>`, e chiusi non mostrano le voci).
**Deve**: ogni voce leggibile da una persona.
**Fallimento**: righe come `log:aioamazondevices@components/alexa_devices/coordinator.py:192` o
`integrazione:01K2CK...`. **Questa prova oggi FALLISCE** — è il difetto registrato il 07/09.

### E3 — Un episodio dice di che cosa parla

**Si fa**: si guarda la sezione «Cosa è successo». **Deve**: ogni episodio nominare il proprio
protagonista in modo leggibile.
**Nota**: un episodio **nato prima** della versione che registra dominio e titolo non può
mostrarli — la correzione vale **in avanti**, non all'indietro. Un identificatore opaco su un
episodio vecchio **non è** un fallimento; su uno nato dopo l'aggiornamento sì.

---

## F · Ciò che costa, e si prova solo con l'assenso di chi paga

### F1 — La chat risponde

**Si fa**: si manda **un** messaggio dalla chat. **Costa**: una chiamata vera al modello.
**Deve**: rispondere, e i «Consumi» devono aumentare di conseguenza.
**Fallimento**: nessuna risposta, o consumi che non si muovono.

### F2 — Un'azione tocca la casa

**Si fa**: si chiede a HIRIS di accendere qualcosa di innocuo. **Tocca la casa vera.**
**Deve**: la cosa cambia stato, e HIRIS lo **rilegge** invece di dichiararlo per fede.
**Fallimento**: HIRIS dice di aver fatto e la casa non è cambiata.

> **Queste due non si eseguono senza chiederlo.** Costano denaro e toccano l'impianto: chi
> esegue il foglio le salta e lo **dichiara**, invece di farle di nascosto o di fingere di
> averle fatte.

---

## Come si riporta l'esito

Per ogni prova: **passata**, **fallita** o **saltata**, e per le fallite **cosa si è visto**, non
«non funziona». Una riga di log o una risposta copiata vale più di tre righe di descrizione — su
questo prodotto un difetto è stato trovato perché un foglio chiedeva di **copiare** una riga che
nessuno guardava.

E la regola che vale più di tutte: **se una prova passa ma per la ragione sbagliata, è fallita.**
