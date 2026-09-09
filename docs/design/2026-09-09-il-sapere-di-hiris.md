# Il sapere di HIRIS — punto di partenza per la sessione che verrà

`consegna · 09/09/2026 · HIRIS 3.23.2 rilasciata, due commit verso la 3.23.4`

**Questo documento esiste perché il lavoro riparte da una sessione pulita.** Chi lo legge non ha
la memoria della conversazione da cui nasce: qui c'è tutto ciò che serve per ricominciare senza
rifare le misure e senza ripetere gli errori.

**Il proprietario ha dichiarato che questa parte è fondamentale, che deve essere fatta così, e
che se serve DISTRUGGERE E RICOSTRUIRE si fa.** Non è un invito alla leggerezza: è il permesso di
non piegare il disegno per rispettare ciò che esiste già.

---

## §0 · Il vincolo nuovo, che cambia tutti gli altri

> **HIRIS verrà distribuito ad altri utenti.**

Fino a oggi non è mai stato un vincolo di disegno, e si vede. Da adesso ogni scelta si giudica
anche così: *«cosa succede a chi installa HIRIS su una casa che non abbiamo mai visto?»*

---

## §1 · I tre attori, dettati dal proprietario

| chi | risponde a | provenienza |
|---|---|---|
| **il catalogatore** | *cos'è questa cosa?* | **dedotta** dal modello, **verificata** sulla documentazione di HA |
| **l'analista** | *mi serve per rispondere alla domanda dell'obiettivo?* | giudizio, guidato dall'obiettivo |
| **l'osservatore** | raccoglie ciò che gli è stato detto di raccogliere | esecuzione — **esiste già e gira** |

**Le sue parole, e vanno rilette perché sono la specifica:**

> *«HIRIS non riconosce un dispositivo e non sa catalogarlo. Dovrebbe chiedere al modello di AI
> cosa si tratta, verificare con la documentazione HA cosa gestisce e cos'è, ottenere le risposte
> e aggiungerlo alla sua memoria come catalogazione, e quindi da lì in poi strutturarlo nei vari
> sistemi.»*

> *«L'osservatore che deve osservare i dati energetici — perché il suo obiettivo è il benessere
> energetico di casa — li trova classificati correttamente e da lì li inserisce nelle sue
> osservazioni. Oppure l'analista dovrebbe accorgersi che ci sono nuove entità che permettono di
> capire meglio come la casa risponde a questa domanda, e dare compito all'osservatore di
> raccogliere dati da lì in avanti.»*

**Le due strade non sono alternative: sono lo stesso anello in due momenti.** A regime
l'osservatore trova le cose catalogate. Quando arriva qualcosa di nuovo, è l'analista ad
accorgersene e a estendere ciò che si osserva.

**Oggi quell'anello è aperto**: la gamba è un giudizio scritto a mano una volta, e nessuno la
rivede mai. È il motivo per cui esistono 109 classi che nessuno ha mai guardato.

### Il primo avvio, secondo il proprietario

> *«Installo HIRIS: al primo avvio classifica il classificabile. L'osservatore avrà un obiettivo
> (lo faremo ad attivazione) e comincia a osservare tutta la casa, e ne raccoglie i dati
> fondamentali per rispondere al prompt di obiettivo — che ricordo può variare. Quindi i dati
> grezzi stessi possono dinamicamente variare. Il punto focale invece è il resoconto giornaliero:
> quello resta completamente in memoria, per poi creare i trend e su quello operare.»*

**Due conseguenze che il disegno deve reggere:**
1. **L'obiettivo è un prompt e può cambiare.** Ciò che si raccoglie dipende da esso: il pavimento
   non è una costante del prodotto, è una funzione dell'obiettivo di quella casa.
2. **Il resoconto giornaliero è il perno**, e oggi **non esiste**. L'osservatore scrive episodi
   (`oggetti`), non sintesi.

### E una cosa che il proprietario ha escluso esplicitamente

> *«Non voglio raccogliere largo, voglio fare qualcosa di intelligente.»*

La via «nel dubbio registra tutto e filtra dopo» **è stata scartata**. Resta però il suo costo,
che va dichiarato nel disegno: **«da lì in avanti» è una condanna** — il giorno in cui l'analista
scopre che gli servirebbe un dato, di quel dato non ha storia, e la prima risposta utile arriva
settimane dopo. Il disegno deve dire come si convive con questo.

---

## §2 · Le due domande del proprietario, e le risposte misurate il 09/09

### «La base di conoscenza come l'abbiamo creata è sostenibile e funzionale?»

**Per questa casa sì. Per un utente nuovo no**, e il difetto è strutturale:

> **Il vocabolario dei tipi è un file Python dentro il repository.** È conoscenza *nostra*, uguale
> per tutti, congelata al rilascio. **Non esiste nessun posto dove una singola casa possa scrivere
> ciò che HIRIS ha imparato lì dentro.**

Un utente nuovo ha domini che non abbiamo classificato e integrazioni che qui non esistono. Il
censore glielo direbbe — e **nessuno lo ascolterebbe**, perché il censore fa fallire una *prova*,
che gira da noi, non da lui.

Le **109 classi ancora aperte** sono la dimostrazione: dopo tre giorni di lavoro, il modello di
riempimento è ancora *«il proprietario risponde»*. **Quello non si distribuisce.**

La **forma** regge (una casa per tipo, provenienza per campo, un censore che si accorge). Il
**modo di riempirla** no.

### «HIRIS sa apprendere e costruirsi la sua documentazione? La base dati è coerente e strutturata?»

**Coerente sì**: ogni archivio ha un padrone solo, nessuno scrive nel database di un altro.
**Strutturata per quello che le si sta per chiedere, no.** È fatta per **registrare**, non per
**sapere**. Tre mancanze precise:

1. **Manca la casa per ciò che HIRIS deduce.** `memoria.db` conserva *ciò che l'utente ha detto*
   (ricordi, ancore, condizioni). Non c'è nessuna tabella per *ciò che HIRIS ha capito da solo*:
   la quarta provenienza non ha un tetto.
2. **Manca il resoconto giornaliero.** `cambi` (22 giorni) + `oggetti` (per sempre) sono episodi.
   La sintesi da cui nascono le tendenze non esiste.
3. **Non sa prendere porzioni.** Il modello riceve **un testo fisso di 6.800 caratteri**, uguale a
   ogni messaggio, tagliato da una scaletta decisa una volta. Nessun meccanismo sceglie *cosa
   serve per questa domanda*. E il problema non è il nucleo: **è che non esiste niente sotto di lui
   da cui pescare.**

---

## §3 · La quarta provenienza

Il vocabolario oggi ha tre provenienze (spec `2026-09-07-l-anagrafe-dei-tipi.md` §3): `chiesto`,
`importato`, `nostro`. Ne serve una quarta: **`dedotto`**.

> **REGOLA CHE NON SI NEGOZIA: una deduzione non diventa mai un fatto.**

Senza di essa questa idea è la legge più importante del prodotto violata **su scala industriale**:
tre giorni a togliere affermazioni non verificate, e un catalogo che scrive «autoconsumata =
energia consumata dal proprio impianto» **senza dire che l'ha dedotto** ricrea lo stesso difetto,
automatico e a centinaia di voci.

Ogni voce dedotta porta **chi**, **quando**, **su quali prove**, e **se la documentazione l'ha
confermata**. Ed è correggibile, come già lo sono i ricordi.

**Tre esiti distinti, da tenere distinti:**
- **confermato dalla documentazione** — `device_class`, `state_class`, gli stati di un dominio: HA
  li pubblica, e la deduzione diventa una lettura;
- **dedotto e non confermabile** — «Potenza autoconsumata» è un nome che *l'integrazione si è
  inventata*: la documentazione di HA non ne parla e non ne parlerà mai;
- **non capito** — e va detto, non riempito.

### Il modo di chiedere, che decide la qualità della risposta

**Non chiedere una cosa alla volta.** «Cos'è `sensor.solare_potenza_autoconsumata`?» è la domanda
debole. Questa è quella forte:

> *«Questo dispositivo si chiama SOLARE, viene dall'integrazione X, e porta queste otto entità:
> prodotta, consumata, autoconsumata, carica, scarica, importata, esportata, e un totale. Tutte in
> watt. Che cos'è, e che ruolo gioca ciascuna?»*

**Viste insieme quelle otto si spiegano da sole; viste una alla volta sono otto indovinelli.** E la
risposta non è «cos'è questa entità», è **«questo è un impianto fotovoltaico con accumulo, e queste
sono le sue sette misure»**.

### Cosa il catalogatore NON può fare

Il modello può dire **cos'è**. Non può dire **se interessa**. La gamba resta il giudizio del
proprietario; al massimo il modello **propone** e lui conferma.

---

## §4 · Il caso che ha fatto emergere tutto: l'impianto solare

Misurato sulla casa vera il 09/09. Otto entità, **otto ruoli diversi, un solo `device_class`**:

```
SOLARE Potenza prodotta        160 W    device_class = power
SOLARE Potenza consumata       340 W    device_class = power
SOLARE Potenza autoconsumata   0.14 kW  device_class = power
SOLARE Potenza carica            0 W    device_class = power
SOLARE Potenza scarica         200 W    device_class = power
SOLARE Potenza importata         0 W    device_class = power
SOLARE Potenza esportata        20 W    device_class = power
Fuoco e tv Potenza          29.353 W    device_class = power   <- una presa in soggiorno
```

Per il vocabolario di oggi sono **la stessa identica cosa**: `power` → gamba «energia».

E quei numeri raccontano una storia che HIRIS **non sa leggere**: produce 160 W, ne consuma 340,
la batteria scarica 200 W, dalla rete prende zero e ne esporta 20 — *sta vivendo di sole e
batteria, e sta persino vendendo*.

**Parole del proprietario:**

> *«HIRIS deve conoscere ogni tipologia per poterla assegnare correttamente nei termini e
> definizioni corrette. La sezione del solare deve capire cosa sta consumando, cosa sta
> producendo, cosa abbiamo storato nella batteria, da dove ho prelevato: rete, batteria, impianto
> solare. Mentre a presa consumo/voltage è un riferimento diverso, un consumo di dettaglio di
> quell'apparecchio. `energy_distance` mi dice per un'auto elettrica cosa ha consumato per quei km,
> ma è associata a un dispositivo riconoscibile: automobile. Quindi qui il riconoscimento e la
> gestione devono essere fini.»*

**Due assi, non uno:**
1. **Il ruolo dentro la gamba** — prodotto, consumato, immagazzinato, prelevato, immesso,
   autoconsumato. La gamba dice *a quale domanda l'entità aiuta a rispondere*; **non dice che ruolo
   ci gioca**, e senza il ruolo «hai consumato 6,8 kWh» e «ne hai prodotti 2,31» sono lo stesso
   fatto detto due volte.
2. **Il soggetto a cui appartiene** — il consumo di una presa è dettaglio di quell'apparecchio, il
   consumo dell'impianto è il bilancio di casa. **Questo dato HIRIS ce l'ha già**: l'anagrafe
   conosce dispositivi e integrazioni. Semplicemente non lo usa per interpretare i numeri.

**Da misurare prima di disegnare**: da dove si legge davvero il ruolo? Dal nome dell'entità (e
allora è fragile), o da qualcosa di dichiarato — `unique_id`, l'integrazione, o **la configurazione
del pannello Energia di Home Assistant**, che quella distinzione la conosce già perché gliel'ha
insegnata l'utente.

---

## §5 · Lo stato dei fatti, misurato

| | |
|---|---|
| entità della casa | **841** (839 con stato) |
| entità che entrano nel pavimento dell'osservatore | **88** — *non ~800: è un errore che ho fatto e che è stato corretto* |
| archivi vivi | 7 — `casa.db`, `osservazioni.db`, `memoria.db`, `promesse.db`, `costruzioni.db`, `consumi.db`, `chat_history.db` (+ `azioni.db`, `reasoning.db`) |
| archivi **morti** ma dichiarati nel log | 7 — `knowledge.db`, `advisory.db`, `portrait.db`, `sentinel.db`, `vault.db`, `hiris_memory.db`, `history.db` |
| classi che il censore tiene aperte | **115** (109 + `lock=jammed` + 5) |
| in quante decisioni si riducono | **17 gruppi, di cui 8 vere scelte** |
| entità vive in gioco su quelle 109 | **zero** (7 spente) |
| nucleo | **6.456 su 6.800**, sette sezioni |

### Il difetto del censore, che è una fetta e non una decisione

`claimed_device_classes()` considera «classificata» una coppia che sta soltanto in
`DEVICE_CLASS_MEANING` — una tabella che risponde a *«che valore rappresenta»*, **non** a *«a quale
gamba serve»*.

> **La domanda sulla gamba non è mai stata posta per 43 delle 62 classi di `sensor`**, e il censore
> ne nomina 31. Le 12 invisibili, più 9 coppie di altri domini, valgono **119 entità vive**
> (`sensor.timestamp` 19, `switch.outlet` 10, `sensor.illuminance` 4, `valve.water` 4, …).

È lo stesso difetto che la fetta 5 ha tolto agli stati: **una parola che copre due domande**, e il
controllo che tace perché guarda quella sbagliata. **Va riparato prima di rispondere alle otto
domande**, o si risponderebbe a 31 sapendo che ne mancano 12.

---

## §6 · Le decisioni già prese, che non si rifanno

| decisione | presa |
|---|---|
| **`number` eredita la gamba del suo sensore gemello** | 09/09 — chiude **57 classi**. Provato dal fornitore: `number/const.py:112` dice *«NumberDeviceClass should be aligned with SensorDeviceClass»*; `NumberDeviceClass` (58) ⊂ `SensorDeviceClass` (62); `number/strings.json` prende **58 nomi su 58** per riferimento da `sensor` |
| **`sensor.signal_strength` → «buono stato»** | 09/09 — con la regola qui sotto |
| **La gamba dice «potrebbe servire», l'analista dice «serve»** | 09/09, parole del proprietario: *«l'oscillazione va interpretata per capire cosa significa»*. **Non si inventa una soglia**: si archivia e si interpreta. Non si può analizzare ciò che non si è registrato |
| **Gli undici stati di mezzo: si annuncia solo ciò che significa qualcosa** | 08/09 — `lock` che si muove **sì** (qualcuno è alla porta), `vacuum` in pausa **sì** (di solito è bloccato); tapparella in movimento, film in pausa, `buffering` **no**. Criterio: *si annuncia ciò che farebbe alzare dalla sedia* |
| **`lock=jammed` è un guasto** | 08/09 — richiede la fetta «il genere che dipende dallo stato»: oggi il genere si decide **per soggetto**, e una serratura non può cambiarlo a metà giornata |

### Le sei domande in pausa, da riporre DOPO il nuovo modello

3. l'energia **ferma** in una batteria · 4. `sensor.radon` · 5. `event.motion` · 6. il dominio
`humidifier` · 7. pioggia, vento, irraggiamento · 8. `valve.gas` (**per classe, non per dominio**:
trascinerebbe `valve.water`, che qui è l'irrigazione)

**Sono in pausa perché poste male**: con il ruolo e il soggetto, la domanda 3 non è più «l'accumulo
entra nella gamba energia» ma «che ruolo gioca nel bilancio».

---

## §7 · Cosa resta in sospeso, indipendentemente da questo sprint

- **La 3.23.4 non è rilasciata.** Due commit su `master`: `decae7f9` (i membri di un gruppo escono
  dalle capacità) e `6c9d07fd` (CLI del ponte a **2.1.266**). Il proprietario ha deciso di
  rilasciarli con lo sprint successivo.
- **La CLI 2.1.263 non è MAI stata vista girare nel container.** `GET /api/health` risponde
  `ponte: null` — «non ancora visto», che non è «assente»: nessun turno di chat dal riavvio.
  Il ripiego dichiarato nel Dockerfile resta la **2.1.260**, l'unica letta davvero. **Basta un turno
  di chat qualunque e poi rileggere `ponte.cli`.**
- **`membri` esce solo dal dettaglio di una entità**: chi comanda senza guardare prima non legge
  l'avviso sul gruppo misto. Portarlo nell'esito dell'azione è una fetta sua.
- **Lo specchio non si risincronizza dopo un distacco WS** (riguarda ogni evento perso, non solo le
  rimozioni). E **`PRICING` non ha tariffe di cache per i `gpt-*`**: l'input cachato resta
  fatturato a prezzo pieno.
- **`chat_stream`** non è collegato e non è cancellato, con la ragione scritta nel codice.

---

## §8 · Le regole, che valgono anche quando si distrugge e si ricostruisce

`CLAUDE.md`, «Le tre leggi» e «Le quattro fondamenta» — **atomicità, nessun doppione, consistenza,
autonomia funzionale**. Il proprietario le ha imposte come fondamenta indiscusse e ha chiesto che
**ogni revisione le verifichi**. Una violazione non è un'opinione di stile.

E le forme di difetto che questo progetto ha già pagato, tutte trovate fra il 05 e il 09/09 —
**cercarle è più utile che cercare bug**:

| forma | dove ha morso |
|---|---|
| **due cose diverse dette con una parola sola**, curate a valle invece che alla fonte | sei volte, ogni volta un livello più in fondo |
| **la motivazione falsa**: una ragione scritta accanto al codice, smentita dal file che cita | **nove volte in due giorni**, due delle quali scritte da chi sorvegliava |
| **una prova che non può fallire**: finte costruite nella forma che il codice si aspetta, non del fornitore | dieci, fra cui la cancellazione provata su una cache vuota |
| **un numero non misurato** scritto come misurato | «31 eccezioni» (71), «167 voci» (181), «14 file» (12), «2.349 su 6.000» (lo spazio libero era 324) |
| **stato condiviso caricato pigramente** | il registro dei servizi era vuoto finché nessuno agiva: nelle prove la finta lo popolava sempre |
| **verde in locale non è verde** | `EXE001` due volte: su Windows il bit di esecuzione non esiste |

**E la difesa che ha funzionato meglio di tutte**: chiedere esplicitamente al revisore che
**nessuna ragione sia smentita dal codice che cita**. Ne ha verificate 64 e ne ha bocciate 7.
