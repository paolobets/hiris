# La conoscenza di HIRIS

**Data:** 5 agosto 2026 · **Stato:** approvato nelle decisioni di fondo
**Dipende da:** `2026-08-04-scope-hiris.md` (il contratto) · `2026-08-05-mappa-funzionalita.md` (la mappa)
**Supera:** `2026-08-04-cosa-sa-il-brain.md` (oggi in `docs/out-of-scope/`) per la parte sul
ritratto e sulla mappa semantica.

---

## 0. Da dove viene

È la sovrapposizione **n.1** della mappa: *«la casa esiste in cinque copie, e nessuno le vede tutte»*.

`entity_cache` · `semantic_context_map` · `semantic_map` · `entity_classifications` · `portrait` ·
`snapshot`. Tre di queste sono **rappresentazioni della stessa casa** con tre vocabolari incompatibili
— trenta tipi, dodici ruoli, quattro secchi. La chat riceve la mappa e non il ritratto; il Brain
riceve il ritratto e non la mappa. **Due intelligenze nella stessa casa che vedono due case diverse.**

E la parola dell'utente che ha aperto il progetto: *«la context map era un'evoluzione per risparmiare
token; questa deve essere la conoscenza completa di HIRIS, riprogettata e ottimizzata, la base dati
su cui tutto si fonda»*.

> Non stiamo comprimendo meglio. Stiamo smettendo di comprimere e cominciando a **sapere**.

---

## 1. Il principio

> **Una conoscenza. Due archivi. Quattro cadenze.**

**Una conoscenza** perché chi interroga ne vede una sola: stessa ricerca, stessa risposta, la casa e i
ricordi mescolati.

**Due archivi** perché sotto sono cose di natura opposta. La casa è una **replica**: si cancella e si
ricostruisce da Home Assistant in pochi secondi. La memoria è **insostituibile**: esiste solo lì. Non
si mette una cosa usa-e-getta e una irripetibile nello stesso file, o ogni migrazione della prima
passa accanto alla seconda.

**Quattro cadenze** perché ciò che HIRIS deve sapere non cambia alla stessa velocità, e trattarlo allo
stesso modo è l'errore di fondo di oggi.

| | Cosa | Cambia ogni | Dove sta | Come se ne accorge |
|---|---|---|---|---|
| **Anagrafe** | piani → aree → dispositivi → entità, registro completo, etichette, categorie, alias, integrazioni, persone, zone, mappa energia | **mesi** | su disco | eventi di registro: portano l'id, si rilegge **solo quello** |
| **Comportamento** | corpo di automazioni, script, scene; plance; definizione degli helper | **giorni** | su disco | **`mtime` dei file** + sottoscrizioni che spingono l'oggetto intero |
| **Stato** | il valore di adesso | **secondi** | in memoria | push, come già oggi |
| **Cronaca** | storico, logbook, statistiche | append | **mai tenuta** | interrogata a finestra, quando serve |

L'archivio due — **la memoria** — ha una quinta cadenza: cambia **quando parli**.

---

### Come si costruisce: accanto, non dentro

Questa conoscenza **non si ottiene modificando le cinque rappresentazioni esistenti**. Nasce nuova, in
un modulo suo, con tabelle sue e test suoi, senza toccare nulla di ciò che gira. Quando il nucleo
nuovo alimenta la chat, il Brain e gli agenti, **le cinque vecchie si cancellano in un colpo solo** —
e i 2.769 test esistenti dicono all'istante che cosa reggeva ancora su di esse.

Il lavoro vive sul ramo **`2.0`** dello stesso repository. Non un repository nuovo: la mappa ha
chiesto di **cancellare**, non di riscrivere, e cancellare si verifica mentre ricostruire no. I test —
45.500 righe, più grandi dell'applicazione — sono la forma scritta di tutto ciò che è stato imparato
in 1.164 commit, e sono lo strumento con cui la demolizione resta sicura.

## 2. L'anagrafe

### Cosa contiene

Quattro livelli di gerarchia, dove oggi ne conosciamo **uno**:

```
piano → area → dispositivo → entità
```

più, per ciascun livello, ciò che l'utente ha già dichiarato in Home Assistant: **etichette**,
**categorie**, **alias**, **icone**, e per le entità l'intero registro — `device_id`, `platform`,
`entity_category`, `device_class`, `unit`, `disabled_by`, `hidden_by`, `capabilities`.

Accanto: **integrazioni installate**, **persone** e **zone**, la **mappa energetica** dichiarata in HA,
e il **grafo delle dipendenze** (quali automazioni usano questa entità, quali scene la contengono, in
quali plance compare).

### Da dove viene, e cosa oggi buttiamo

| Fonte | Oggi |
|---|---|
| registro **aree** | letto, e si tiene **solo il nome**: `floor_id`, `aliases`, `icon`, `labels` finiscono nel cestino |
| registro **entità** | letto, e si usa **un campo su quindici**: solo `area_id` |
| registro **dispositivi** | **mai letto** |
| registro **piani** | **mai letto** |
| registro **etichette** e **categorie** | **mai letti** |
| `/api/config` | letto, e si buttano le **integrazioni caricate**, che sono lì dentro |
| grafo delle dipendenze | **mai chiamato** |
| mappa energetica | **mai letta** |
| catalogo dei **servizi** e loro parametri | **mai letto**: il modello li inventa |

**Nessuna di queste è una chiamata nuova costosa.** Sono decine di voci, pochi KB, e cambiano quando
riorganizzi casa: mesi.

### Come si aggiorna

Home Assistant emette un evento per ogni registro. L'evento porta **l'id** di ciò che è cambiato — e
per entità e dispositivi anche l'elenco dei campi toccati — ma **non l'oggetto**: serve sempre una
rilettura mirata di quella singola voce.

Oggi HIRIS ascolta **un evento su dieci**, e **solo alla creazione**: rinomini, cambi d'area,
disabilitazioni e cancellazioni passano inosservati. La casa che HIRIS crede di conoscere si allontana
da quella vera, e nessuno se ne accorge.

**Rete di sicurezza:** una rilettura completa all'avvio. Gli eventi persi durante una disconnessione
non si recuperano, e senza rilettura la deriva sarebbe permanente e silenziosa.

**Sottoscrizioni che risolvono interi pezzi senza rilettura** — spingono l'**oggetto completo**:

| Comando | Copre |
|---|---|
| `config_entries/subscribe` | integrazioni (snapshot iniziale + delta) |
| `lovelace/dashboards/subscribe` · `lovelace/resources/subscribe` | plance e risorse |
| `{input_*,counter,timer,schedule,zone,person,tag}/subscribe` | **tutti gli helper**, con la loro definizione |

---

## 3. Il comportamento

### Il file, non l'API

Home Assistant scrive automazioni, script e scene in tre file dentro la propria cartella di
configurazione. **Quella cartella è già montata dentro HIRIS**: `hiris/config.yaml` dichiara
`map: - config:rw`, e il codice la cerca già (`hiris/app/server.py:144`) — la usiamo per depositarci
il JavaScript della card Lovelace.

L'API di configurazione di HA **legge quello stesso file**. E lo legge male: ogni richiesta di una
singola automazione **apre e parsa `automations.yaml` per intero**, poi ne estrae una riga. Trenta
automazioni sono trenta letture da disco e trenta parse completi dello stesso file.

> Non è N+1. È **N²**. Leggere il file costa **una lettura** e dà **esattamente lo stesso dato**.

Non esiste alcun endpoint che restituisca tutte le automazioni in una chiamata, e non esiste alcun
campo di versione o data di modifica su una automazione. La lettura del file non è una scorciatoia: è
l'unica via economica che esista.

### Come si sa che è cambiato

| | Segnale | Granularità |
|---|---|---|
| **Automazioni · script · scene** | **`mtime` del file** | il file è cambiato o no. Costa un `stat()` |
| **Automazioni** (in più) | l'evento di chiamata del servizio di ricarica porta **l'id** | *quale* |
| **Script** | **nessun evento esiste in Home Assistant** — il servizio di ricarica non emette nulla e non accetta un id | il `mtime` è l'unico appiglio, **e basta** |
| **Scene** | evento di ricarica generico, senza id | il file è cambiato |
| **Plance** | evento con il percorso, o la sottoscrizione che spinge l'oggetto | *quale* |

Un evento di ricarica delle automazioni parte **anche quando non è cambiato nulla**: non è una prova
che serva risincronizzare. Il `mtime` sì.

### I due limiti, dichiarati

**Le automazioni scritte a mano non stanno in quel file.** Possono vivere in cartelle incluse o nei
pacchetti. Ma l'elenco completo di quelle **vive** si ha gratis dallo stato: ogni entità automazione
espone il proprio id. Quindi HIRIS **sa sempre quali esistono**; di alcune avrà il nome e non il
corpo, e **lo sa e lo dice**, invece di credere che non esistano.

**Non si legge la cartella di stato interna di Home Assistant.** Non ha contratto pubblico ed è
versionata con migrazioni: parsarla funziona finché non smette. Per le plance si usano i comandi
WebSocket, che sono supportati.

---

## 4. Lo stato e la cronaca

**Lo stato** resta uno specchio in memoria, alimentato in push — come già oggi. Cambia solo il nome e
il ruolo: `entity_cache` **smette di far finta di essere la casa**. È il riflesso del valore di
adesso, e si chiamerà così.

Un difetto da chiudere qui: lo stato completo viene scaricato **da cinque punti diversi del codice**,
e due di quelle chiamate scaricano l'intera casa per filtrarne un dominio.

**La cronaca** non si tiene mai. Storico, logbook e statistiche si interrogano a finestra quando
servono. Tenerli sarebbe riscrivere il registratore di Home Assistant, che già esiste — Legge I.

Un difetto da chiudere: **ogni lettura WebSocket apre oggi una connessione nuova**, con handshake e
autenticazione completi, e la chiude — separata dalla connessione persistente che già esiste. Con un
timeout fisso, N letture in serie possono costare N volte quel timeout.

---

## 5. Il significato è dichiarato, non dedotto

**Decisione.** La spina dorsale del «ragionare per significato» è **la casa che l'utente ha già
dichiarato in Home Assistant**.

| Dichiarazione | Cosa dà |
|---|---|
| **piano → area → dispositivo → entità** | la gerarchia vera |
| **etichette e categorie** | la tassonomia scelta dall'utente |
| **alias** | i sinonimi già scritti per l'assistente vocale: «caldaia» per lo scaldabagno |
| **`device_class`, unità, `entity_category`** | cos'è la cosa, secondo HA |
| **marca, modello, integrazione** | che oggetto fisico è |
| **grafo delle dipendenze** | cosa dipende da cosa |

**Cosa questo elimina:** la classificazione LLM **a pagamento** della seconda mappa, e le espressioni
regolari che indovinano il ruolo da una parola nel nome.

**Il limite, dichiarato:** vale quanto vale la configurazione. Se non ci sono etichette, quel
significato non c'è. Ma allora **HIRIS lo sa, e lo dice** — e può proporre di aggiungerla. Che è un
oggetto di Home Assistant: **Legge I applicata alla conoscenza stessa.**

---

## 6. La memoria, ancorata alla casa

### La frase che ha fatto nascere questa sezione

> *«D'inverno preferisco la sala da pranzo fra 19 e 20 gradi quando sono a casa.»*

Finisce **nell'archivio due**, la memoria — non nell'anagrafe: in Home Assistant non esiste, e
sparirebbe alla prima ricostruzione della replica.

Oggi ci finirebbe come **una riga di testo**. I campi strutturati che esistono — data, importo,
categoria, titolo — sono nati per le scadenze e le spese. Nessuno serve qui.

Quel testo entra sempre in contesto, quindi in chat HIRIS lo onora. **Fin qui funziona.** Ciò che non
funziona si vede solo guardando cosa la frase contiene:

| | | |
|---|---|---|
| «la sala da pranzo» | **un'area** | che esiste nell'anagrafe, ma per la memoria è una parola |
| «fra 19 e 20 gradi» | **un intervallo** con un'unità | non un numero, non un testo |
| «d'inverno» · «quando sono a casa» | **due condizioni** | una stagionale, una di presenza |
| «preferisco» | **una preferenza** | si può violare senza che nessuno abbia sbagliato |

Tre conseguenze: **rinomini l'area** e il legame si spezza in silenzio; **nessuno può controllarla**,
perché il Brain non sa che parla di quell'area e di quella grandezza; e soprattutto quella frase è
**quasi un'automazione** — ha un innesco, una condizione, un obiettivo — ma la Legge I è inapplicabile
se HIRIS non sa a quale area e a quale termostato si riferisce.

### Le tre regole di sicurezza

La struttura è la parte più potente del progetto e **la più fragile**: è un linguaggio che il modello
deve compilare bene ogni volta, e quando sbaglia HIRIS crede una cosa diversa da quella che gli è
stata detta. Queste tre regole sono ciò che rende la scelta sicura, e non sono negoziabili.

**① Il testo è la verità. La struttura sta accanto, mai al posto.**
Se divergono, vince la frase.

**② La pagina della memoria mostra tutte e due.** La frase, e sotto, in chiaro, **cosa HIRIS ha
capito**: quale area, quale grandezza, quale intervallo, quali condizioni — correggibile lasciando la
frase intatta. Senza questo, un'interpretazione sbagliata è invisibile e diventa permanente.

**③ La struttura è parziale e opzionale.** Riconosce l'area ma non le condizioni? Registra l'area.
Non riconosce niente? Resta testo e funziona come oggi. **Mai tutto-o-niente.**

### Il vocabolario — piccolo e chiuso

Un linguaggio aperto il modello lo compila male. Uno piccolo lo compila bene. **Quattro caselle.**

| | Valori | Da dove viene il vocabolario |
|---|---|---|
| **A chi si riferisce** | area · entità · dispositivo · persona | **l'anagrafe**. Un'ancora senza riscontro **non si scrive** |
| **Cosa chiede** | una grandezza e un valore o intervallo | **`device_class` e unità di Home Assistant**, non un elenco nostro |
| **Quando vale** | ora · giorno · presenza · sole · meteo · **stagione** | il **vocabolario delle condizioni di Home Assistant**, più la stagione che HA non ha e che si traduce in mesi |
| **Che forza ha** | preferenza · divieto · fatto · regola operativa | quattro parole, chiuse |

La terza casella non è una scelta estetica: **è quella che rende la Legge I automatica.** Se le
condizioni parlano già la lingua di Home Assistant, la frase si traduce in un'automazione **senza che
nessuno debba reinterpretarla** — e HIRIS può proportela, col tuo sì, invece di limitarsi a ricordarla.

E la quarta dà la differenza di tono: una **preferenza** violata è un'osservazione (*«in sala da pranzo
ci sono 17 gradi»*); un **divieto** violato è una segnalazione.

---

## 7. Come si guarda: due modi, e sono tutta la superficie

**Il nucleo** — sempre in contesto, **identico per la chat, per il Brain e per gli agenti**. Piani e
aree, cosa c'è in ciascuna per tipo, cosa è notevole adesso, cosa è cambiato, i nomi di ciò che la
casa fa già da sola, e ciò che le persone hanno dichiarato. Poche migliaia di token.

**Le domande** — **uno** strumento che interroga la base: per struttura (*«cosa c'è in cucina»*,
*«quali automazioni toccano questa luce»*) e per significato (*«cosa succede quando esco»*).

> È qui che muore la sovrapposizione n.1: **la stessa casa per tutti.**

Il principio dietro la divisione è la parola dell'utente — *«tutti devono **poter** vedere»*.
Raggiungibile, non residente. **La base tiene tutto; il prompt è una resa.** Oggi invece ciò che non è
in contesto **non esiste**, perché non è memorizzato da nessuna parte.

---

## 8. Cosa sparisce

| Esce | Perché |
|---|---|
| `semantic_context_map` (30 tipi) | assorbita nell'anagrafe |
| `semantic_map` (12 ruoli) **e la sua classificazione LLM a pagamento** | il significato non si compra: è dichiarato |
| `entity_classifications` **+ le tre tabelle mai scritte** | cache di una classificazione che non facciamo più |
| `snapshot` come oggetto a sé | i suoi campi diventano campi del nucleo |
| `portrait` come rappresentazione separata | è **una resa** dell'anagrafe, non un secondo archivio |
| le letture di configurazione una-alla-volta | il file costa una lettura invece di N² |
| i cinque scaricamenti completi dello stato | uno specchio, un consumatore |
| la connessione WebSocket nuova a ogni lettura | si riusa quella persistente che già esiste |

`entity_cache` **resta**, con nome e ruolo espliciti: lo specchio dello stato.

---

## 9. Cosa costa

**La prima costruzione:** una raffica di letture, **una volta**. Poi mai più per intero.
**Il regime:** un `stat()` su tre file, e gli eventi che Home Assistant manda da solo.

Oggi paghiamo **di più** — una classificazione LLM a pagamento, cinque scaricamenti completi dello
stato da punti diversi del codice, e una connessione WebSocket con autenticazione completa a ogni
singola lettura — **per sapere molto meno.**

Ordini di grandezza, per calibrare cosa può stare dove:

| | Peso | Cadenza |
|---|---|---|
| Struttura completa | 100–200 KB (~30–50k token) | mesi |
| Comportamento (corpi) | 50–150 KB | giorni |
| Stato compresso | ~50 KB | secondi |
| *Stato grezzo · catalogo servizi* | *150–800 KB* | *non stanno in un prompt: si interrogano* |

---

## 10. Il vincolo di versione — deciso

`hiris/config.yaml` dichiarava `homeassistant: "2023.1.0"`. Alcune sottoscrizioni su cui questo
progetto si appoggia — quelle delle plance e delle risorse — **non esistono prima di 2024.7**.

**Decisione: si alza la soglia.** `homeassistant: "2024.7.0"` — **eseguita** (Task 6). Niente
ripiego, niente doppia strada: un ripiego per una versione che nessuno usa più è codice morto il
giorno in cui nasce, ed è esattamente il modo in cui questa applicazione è arrivata a novanta
funzionalità.

Va scritto nelle note di rilascio: chi ha un Home Assistant più vecchio resta sulla `1.x`.

---

## 11. Cosa questo documento non decide

- **La forma esatta del nucleo** — quali campi, in che ordine, con quale resa testuale.
- **Il nome delle cose nel codice** e la loro suddivisione in file.
- **Se e quando accendere i vettori.** La spina dorsale è dichiarata; una ricerca per somiglianza
  resta possibile sopra, ma richiede un embedder acceso — oggi spento, con la ricerca che degrada ai
  più recenti. È una decisione successiva, non un prerequisito.
- **Il destino della cartella montata in scrittura.** `config:rw` esiste perché HIRIS deposita il
  JavaScript della card. Ridurre quel permesso richiede un'altra strada per la card: è un lavoro a sé.
- **Come si migra ciò che c'è.** Le classificazioni esistenti sono una cache: si buttano. Ma il piano
  deve dirlo esplicitamente.

---

## 12. Le prove

Ogni affermazione forte di questo documento è stata verificata prima di essere scritta, sul codice di
HIRIS o sul sorgente di Home Assistant.

| Affermazione | Verificata |
|---|---|
| La cartella di configurazione di HA è già montata in HIRIS | `hiris/config.yaml` (`map: - config:rw`) · `hiris/app/server.py:144` |
| L'API di configurazione riparsa il file intero a ogni richiesta | sorgente `home-assistant/core`, vista di configurazione |
| Non esiste alcun endpoint bulk né alcun campo di versione | idem — la chiave è obbligatoria nel percorso |
| **Per gli script non esiste alcun evento di ricarica** | il gestore non emette nulla; lo schema del servizio è vuoto |
| L'evento di ricarica delle automazioni porta l'id | il *post-write hook* chiama il servizio con `id` |
| Gli eventi di registro portano l'id, non l'oggetto | helper dei registri, sorgente HA |
| Le sottoscrizioni di plance/integrazioni/helper spingono l'oggetto intero | helper delle collezioni, sorgente HA |
| La cartella di stato interna non ha contratto pubblico | nessuna documentazione; formato versionato con migrazioni |
| L'inventario completo delle automazioni si ha dallo stato | l'entità espone il proprio id fra le capacità |
| HIRIS ascolta un evento di registro su dieci, e solo alla creazione | `hiris/app/proxy/ha_client.py` |
| Ogni lettura WebSocket apre una connessione nuova | idem |

Dove la documentazione ufficiale di Home Assistant non copre il punto, la verifica è sul sorgente.
Due punti restano **non documentati** e vanno trattati come tali: la stabilità della cartella di stato
interna, e l'assenza di qualunque raccomandazione ufficiale su come un add-on debba restare
sincronizzato con la configurazione.
