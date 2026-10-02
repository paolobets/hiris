# Una fonte sola di verità — esito dell'analisi e requisiti dello sprint

`requisiti · 01/10/2026 · sprint partito il 01/10/2026; le sedici decisioni del §7 restano al proprietario · v3.72.2`

Nasce da una pausa. Il 01/10/2026 un audit degli attori automatici sulla casa vera ha mostrato che
non inventano quasi niente: lavorano su dati rotti. Stavo proponendo un modulo nuovo che dicesse
«in che stato è una fonte», e la verifica sul codice ha trovato che la regola accanto — «questa
entità è disabilitata, nascosta o di servizio, quindi è fuori» — era già scritta undici volte: il
modulo sarebbe stato la dodicesima copia. Il proprietario ha fermato tutto:

> *«L'anagrafe e gli 11 posti hanno ancora senso di esistere? Vorrei capire cosa abbiamo creato nel
> tempo come doppione e creare un'unica fonte di verità per tutta l'app … senza rompere nulla.»*
>
> *«Questo lavoro è la quinta volta che lo chiedo di fare, deve essere l'ultima.»*

Questo documento dice cosa ha trovato l'analisi, cosa deve essere vero alla fine, e in che ordine ci
si arriva. Ogni numero viene da un rapporto nominato; dove un numero non è misurato, lo si dice.
**Nessuna riga di codice è stata cambiata per questa analisi.**

---

## §0 · Le decisioni, e chi le ha prese

| # | Domanda | Decisione del proprietario (01/10/2026) |
|---|---|---|
| 1 | Si continua a riparare gli attori? | **No, si mette in pausa.** Prima la fonte unica; gli attori ripartono sopra |
| 2 | Come ci si arriva | **Una domanda alla volta**, con una sonda che confronta le copie sui dati veri della casa |
| 3 | Dove si arriva | **Al modello unico**: un solo insieme di metodi da cui tutta l'app legge. «Dobbiamo essere consistenti» |
| 4 | I dati verso l'esterno | **Si possono modificare** |
| 5 | L'MCP di integrazione esterno | **Esce tutto**: il gateway su .31 è eliminato e abbandonato. **Il ponte interno DEVE rimanere** |
| 6 | Quanto deve essere larga la verifica | **Tutta l'app, tutte le funzioni sviluppate**: anche gli strumenti di oggi, come la chat usa tutto, come chat e attori passano i dati ai modelli |
| 7 | L'obiettivo | Scritto al §2, con le sue parole |
| 8 | Cosa esce dall'analisi | **Un documento col risultato e il piano di intervento, come requisiti del prossimo sprint** — questo |
| 9 | Il ponte spento | **È voluto**, per provare gli attori con altri modelli. I difetti che escono sulla catena vanno capiti e instradati, non chiusi riaccendendolo |
| 10 | L'attuatore | **In pausa** dalla 3.72.2 finché non avrà gli strumenti |
| 11 | La pagina dell'osservatore | **Dopo** le correzioni sugli attori |

---

## §1 · L'esito dell'analisi

### 1.0 Il verdetto: quanto è lontano il codice dall'obiettivo

**Il codice di oggi non è conforme all'obiettivo, e la distanza è grande.** Non si parte da zero —
l'ossatura giusta esiste — ma è usata da metà dell'app; l'altra metà l'ha riscritta per conto suo.

Il metro è il registro: su 288 voci di doppione, **128 danno già oggi risposte diverse** alla stessa
domanda, e **164 non si chiudono con una sostituzione**: 115 cambiano un comportamento, 49 chiedono
una decisione. Le pure sostituzioni sono 120.

| Proprietà dell'obiettivo | Distanza | Perché |
|---|---|---|
| Una risposta sola | **lontano** | 13 domande sulla casa ripetute, 18 fatti con più di una casa, l'entità in 10 forme, 15 ingressi verso i modelli |
| Completa | **lontano** | numeri senza unità oltre le dieci righe, id senza nome agli attori, stato in parole da una porta sola; resoconti e analisi non chiedibili dalla chat |
| Coerente con la casa | **a metà** | lo specchio degli stati è allineato (0 differenze dopo un riavvio); ma 26 soggetti guardati su 95 sono morti, e nessuno sa lo stato di una fonte |
| Atomica e strutturata | **lontano** | le letture degli strumenti sono metodi privati di un oggetto per-turno: nessun attore può chiamarle, e infatti le ha riscritte |
| Economica | **lontano, e mai misurata** | 40.000 caratteri fissi per turno di chat; la casa letta 3–4 volte all'avvio; nessuna misura in token |

| Area | Distanza | Cosa c'è già di giusto | Cosa manca |
|---|---|---|---|
| Leggere da Home Assistant | a metà | un client solo; lo specchio tenuto vivo dagli eventi | 5 chiamanti che lo aggirano; una connessione nuova per lettura; 7 forme di ritorno |
| La casa e le sue regole — **lato chat** | **vicino** | `search` e `history` condividono la selezione; anagrafe e specchio sono il disegno giusto | l'oggetto non porta causa dell'esclusione, area ereditata, stato della fonte |
| La casa e le sue regole — **lato attori** | **lontano** | niente: osservatore e ricette rifanno elenco, nome, tipo e posizione | tutto da ricondurre ai metodi della chat |
| La resa e i nomi dei campi | **lontano** | lo stato in parole ha un solo produttore | 12 renditori, 6 nomi per l'id, due chiavi d'errore, il frontend che ricalcola |
| Gli strumenti | a metà | 12 strumenti, catalogo sano, un solo dispatcher | logica propria dentro ciascuno, tre tabelle a mano, promesse non mantenute dalle descrizioni |
| Un turno verso un modello | **lontano** | una sola decisione su chi risponde | 4 compositori, 5 lettori, 4 registri; catena e ponte si comportano diversamente |
| Scrivere su Home Assistant | **vicino** | 43 metodi del client: una sola scrittura fuori dalle due porte | la forma del rifiuto (4), rileggere prima di scrivere |
| Permessi e modelli | a metà | una regola dei permessi e una fonte vera dei modelli (`models_config.json`) esistono | «chi sei» posto in 13 punti; «quali modelli» in 37, con 9 tabelle parallele |
| Gli archivi | a metà | schema pulito: 21 colonne mai lette su 228, nessuna tabella orfana | nessuna riconciliazione con la casa |
| Le prove | a metà | 4.854 test, otto cancelli buoni | 37 file fissano il testo di `server.py`: vanno convertiti prima di spostare codice |

**Cosa vuol dire in pratica.** L'intervento tocca quasi tutti i moduli: `home_space/` (16.000
righe), `mind/` (10.000), `server.py` (6.000, di cui ~1.830 sono giri del cervello fuori posto), i
runner (5.000), le rotte e il frontend. Non è una pulizia: è una riorganizzazione. Le tre tappe
pesanti sono la casa come oggetto unico con gli attori ricondotti (3), la resa col vocabolario dei
campi (4) e il turno unico verso i modelli (6); le altre sono più corte. La parte facile — codice
morto, documenti falsi, MCP esterno: 152 voci — è grande come numero e piccola come rischio.

### 1.1 Cosa è stato letto

| | |
|---|---|
| Python di `hiris/app/` letto per intero, riga per riga | **62.703 righe su 62.703** |
| JavaScript del frontend letto per intero | 10.824 righe, 30 file |
| Suite di test | misurata come insieme (304 file, 4.854 test Python, 584 JavaScript); 42 file letti a fondo |
| Sonda di parità sulla casa vera | le copie vere di 9 regole fatte girare su 1.525 entità, 333 dispositivi, 15 aree |
| **Non letto** | i 5 fogli di stile (3.852 righe), i test JavaScript; il resto della suite Python solo a campione |

Il lavoro ha avuto due tempi. Otto assi hanno cercato i doppioni leggendo «dove serviva»; poi nove
revisori hanno riletto tutto il Python riga per riga. **Il secondo passaggio era necessario**: ha
aggiunto 223 voci, ne ha corrette 88 su 216, e ha trovato 19 difetti veri. Un censimento fatto a
pezzi vedeva meno della metà.

### 1.2 Il registro

**464 voci**, una riga ciascuna, in `2026-10-01-registro-dei-doppioni.md` (accanto a questo file).

| Capitolo | Voci |
|---|---|
| A · Leggere da Home Assistant | 39 |
| B · L'oggetto «casa» e le sue regole | 54 |
| C · La resa in uscita e i nomi dei campi | 56 |
| D · Un turno verso un modello | 66 |
| E · Scrivere su Home Assistant | 13 |
| F · Chi sei, cosa puoi, quali modelli | 21 |
| G · Gli archivi che seguono la casa | 23 |
| T · La suite di test | 16 |
| M · Codice morto e residui | 79 |
| X · Documenti e commenti che dicono il falso | 77 |
| S · Difetti veri che non sono doppioni | 20 |

Delle 288 voci di doppione (A–G e T): **111 copie equivalenti, 128 divergenti, 46 non verificate**
(più 3 su cui due rapporti danno verdetti diversi).
Unirle è **pura sostituzione in 120 casi, cambia un comportamento in 115, chiede una decisione del
proprietario in 49** (più 2 con due verdetti e 2 senza verdetto dichiarato). I conti di questa sezione si chiedono al registro, non si ricopiano:
`python scripts/registro.py conta` (ricontati così il 01/10/2026, a Tappa 0 cominciata).

### 1.3 Cosa diverge già oggi, sulla casa vera

La sonda ha fatto girare le funzioni vere del repo sui dati veri. Delle divergenze lette sul codice,
alcune pesano e altre oggi valgono zero casi.

| Domanda | Sulla casa | |
|---|---|---|
| In che area sta | **194 entità guardabili su 324** arrivano all'osservatore senza area: la ereditano dal dispositivo e lui legge solo quella propria | pesa |
| È fuori? (nelle ricette) | Il modello che scrive le ricette vede **1.138 entità** che l'osservatore esclude (548 disabilitate, 575 di servizio, 15 nascoste) | pesa |
| Come si chiama | **944 entità su 1.525** hanno un nome diverso fra le due porte della chat; è sempre e solo il prefisso del dispositivo | pesa |
| Il consumato | Su 7 giorni **28 conti su 272** danno risultati diversi (es. 174,5 kWh contro 24,2; quello giusto secondo HA è 174,5) | regola divergente, oggi non raggiunta da un numero in pagina |
| Cerca per integrazione | `search` accetta solo il dominio esatto in minuscolo: con una maiuscola fallisce su tutte le 39 | pesa |
| «Oggi» nelle sessioni di chat | etichetta sbagliata fra mezzanotte e le 02:00 | pesa poco |
| È un valore? | 328 entità su 974 sono `unavailable` e una copia le legge come valori | oggi stesso verdetto, per caso |
| Ha statistiche? · Unità e classe · Accenti nei nomi | **0 casi** | divergenza solo potenziale |

### 1.4 I costi fissi e ripetuti

Nessun rapporto ha misurato i token: le cifre in token sono conversioni dai caratteri.

**Cosa entra in ogni turno, prima di nucleo e cronaca:**

| Turno | Fisso | Nota |
|---|---|---|
| Chat su catena | **40.043 caratteri** (~12.000 token) | il catalogo dei 12 strumenti, 33.069 caratteri, rispedito **a ogni giro** |
| Chat su ponte | ~29.000 token fissi per giro | di cui ~12.000 il contorno della CLI (dal BACKLOG, non rimisurato) |
| Analista | 136.822 caratteri di domanda, una volta all'ora finché non riesce | tetto d'uscita **4.096 non dichiarato**: 7 turni su 8 troncati il 01/10 |
| Osservatore, ricette, analista, attuatore, «Rifalla» su catena | 6.044 caratteri di regole sugli strumenti | che non hanno: gli si dice «usa sempre gli strumenti» |

Testo ripetuto dentro lo stesso turno: ~3.600 caratteri delle regole di base e ~3.100 della guida
del ponte ripetono ciò che le descrizioni degli strumenti dicono già; undici parametri descritti due
volte fra `search` e `history`; `calendar` spende 3.050 caratteri di descrizione per due parametri.
Nessuna risposta di strumento ha un tetto in caratteri: solo in righe, e due non ne hanno affatto.

**Letture verso Home Assistant ripetute:** ogni lettura via WebSocket apre sessione, connessione e
autenticazione nuove. `GET /api/states` di tutta la casa da 5 chiamanti (3 vogliono poche righe che
lo specchio ha già), 288 volte al giorno dal solo comportamento. I registri interi (2 connessioni,
11 comandi) da 4 chiamanti, 144 volte al giorno per usarne uno. Le segnalazioni di HA lette da due
lavori: 432 connessioni al giorno invece di 288. Le tracce lette un'automazione alla volta ogni 2
minuti. All'avvio: circa 17 connessioni più 4 letture intere degli stati nei primi secondi.

**Ricalcoli in memoria:** la gerarchia della casa si rifà da capo 1 volta per turno di chat e da 1 a
4 per ogni `search`; lo specchio costruisce 6 mappe per usarne 1 o 2; i ricordi si rileggono con
1 + 2N letture a ogni turno; sul ponte permessi e dispatcher si rifanno a ogni chiamata di
strumento, fino a 50 volte per turno; la tabella dello scope è riletta ~102 volte per lotto.

**Dove si perde tempo** (dichiarato dal revisore dei runner, in ordine): il ponte aggiunge ~3,3 s
per risposta ed è una corsia sola; nessuno streaming sulla catena; gli strumenti chiesti insieme
partono in fila; il giro in più di `ToolSearch` sul ponte (67 turni su 83). Misurato sulla casa: un
turno di chat dura in media 22,8 s sulla catena e 13,9 s sul ponte.

### 1.5 Perché nessuno se n'era accorto

Gli strumenti del progetto non vedono questo genere di doppione. `scripts/censimento.py` trova
codice morto e tabelle orfane; `scripts/doppioni.py` trova vocabolari gemelli. **Nessuno dei due
vede due funzioni che rispondono alla stessa domanda con codice diverso**, né le copie fra
JavaScript e Python, né le colonne mai lette. E nessuno dei due gira nel pre-push o nella CI, benché
abbiano una modalità cancello. Le quattro volte precedenti si è curato un doppione alla volta, senza
una destinazione scritta e senza un cancello che fermasse il successivo.

### 1.6 I difetti veri che l'analisi ha trovato per strada

Sono 20 (capitolo S del registro). Quelli che esistono oggi in produzione e toccano dati o permessi,
tutti letti sul codice e non provati dal vivo:

| | Difetto |
|---|---|
| S-17 | Una proposta confermata (anche 7 giorni dopo) scrive il corpo calcolato allora senza rileggere la casa: una modifica fatta a mano in HA nel frattempo è persa |
| — | `GET /api/home-space` consegna il corpo delle automazioni a un servizio firmato «lettore», mentre lo strumento della chat lo nega a chi non amministra |
| S-16 | L'identità di un servizio firmato è il suo nome, non la chiave: due servizi omonimi condividono chat, ricordi e promesse |
| S-15 | L'elenco vuoto delle reti fidate fa fidare l'add-on dell'intera rete Docker (caso raro) |
| S-19 | Un file di impostazioni della chat rovinato ferma l'add-on all'avvio (eseguito) |
| S-08 | Sul ponte la domanda dell'analista supera il limite di un argomento della CLI (dedotto) |
| S-04 | Un'autenticazione WebSocket fallita ferma il ciclo degli eventi fino al riavvio |

---

## §2 · L'obiettivo

Con le parole del proprietario:

> In tutta l'app ogni domanda ha una risposta sola, scritta in un posto solo, **che possa restituire
> le informazioni necessarie**. Tutto è costruito in modo **consistente e coerente con la casa**. Gli
> strumenti sono fatti **in modo completo, senza doppioni**, tutto unificato dove possibile in
> **metodi atomici e strutturati**, con **il livello necessario a rispondere a tutte le funzionalità
> dell'app**. Gli strumenti restituiscono ai modelli **il set informativo necessario, ottimizzando il
> consumo di token e la latenza** nelle risposte e nel recupero.

Cinque proprietà, tutte necessarie:

1. **Una risposta sola.** Ogni domanda è scritta in un posto solo.
2. **Completa.** Quel posto restituisce tutto ciò che serve per usarla: il valore con l'unità, il
   nome, dove sta, da quando, quanto è affidabile.
3. **Coerente con la casa.** Coincide con ciò che Home Assistant sa, e cambia quando lui cambia.
4. **Atomica e strutturata, al livello necessario.** Un metodo, una domanda, una forma fissa, la
   profondità che serve. Strumenti, attori, rotte e pagine **compongono** quei metodi: non li
   riscrivono.
5. **Economica.** Dà al modello ciò che serve e niente di più, col minimo di token, di giri e di
   attesa.

E una condizione di sufficienza: **l'insieme deve bastare a tutte le funzionalità dell'app.** Se una
funzionalità ha bisogno di qualcosa che nessun metodo dà, manca un metodo — e va aggiunto lì.

---

## §3 · I requisiti

Ogni requisito dice cosa deve essere vero alla fine e come lo si controlla.

### Una risposta sola

- **R1.** Ogni comando verso Home Assistant ha **un solo chiamante**. *Controllo:* una prova che
  legge l'albero del codice e fallisce se un metodo di lettura del client è chiamato fuori dal
  modulo che lo possiede.
- **R2.** Ogni domanda sulla casa (le trenta della matrice, §4) ha **un solo metodo** che risponde.
  *Controllo:* il registro non ha più voci aperte nei capitoli A e B; la sonda di parità dà zero
  disaccordi.
- **R3.** Un oggetto esce con **la stessa forma da tutte le porte**: stessi campi, stessi nomi,
  stessa lingua. *Controllo:* una funzione di resa per oggetto; una prova che fallisce se una rotta,
  uno strumento o un testo per un modello compone un'entità senza passare di lì.
- **R4.** Esiste **un solo modo di fare un turno** verso un modello, uguale su catena e ponte: un
  compositore del prompt, un lettore della risposta, un registro degli esiti, un tetto dichiarato.
  *Controllo:* nessuna chiamata diretta al runner fuori dal modulo dei turni.
- **R5.** Le scritture verso Home Assistant passano **solo dalle porte dichiarate**; il rifiuto ha
  una forma sola. *Controllo:* la prova esistente sulle porte, estesa alle scritture via WebSocket
  che oggi non vede.
- **R6.** «Chi sei e cosa puoi» ha **un solo cancello**, usato da strumenti e da rotte; l'elenco dei
  provider, i loro nomi e le loro credenziali hanno **una tabella sola**. *Controllo:* prova di
  cablaggio sul cancello; nessun elenco di provider scritto a mano fuori dalla tabella.

### Completa

- **R7.** Nessun oggetto esce senza ciò che serve a interpretarlo: nessun numero senza unità, nessun
  id senza nome, nessun istante senza fuso dichiarato. *Controllo:* prove sulla resa, a ogni
  profondità.
- **R8.** Ciò che HIRIS sa è chiedibile: **i resoconti, le analisi, lo scope e l'obiettivo sono
  raggiungibili dalla chat**, non solo dalla pagina. *Controllo:* la matrice non ha celle «il dato
  c'è e nessuno può chiederlo».
- **R9.** Gli strumenti fanno ciò che dichiarano: `search` elenca davvero ogni genere che la sua
  descrizione nomina; ogni chiave citata in una descrizione esiste nella risposta. *Controllo:* una
  prova che confronta le descrizioni col catalogo dei campi resi.

### Coerente con la casa

- **R10.** Ogni fatto della casa tenuto in un archivio di HIRIS (scope, ricette, ancore dei ricordi,
  proposte) **si riallinea al registro di HA**: ciò che esce da HA esce anche di lì, o è marcato.
  *Controllo:* zero soggetti morti fra i guardati (oggi 26 su 95).
- **R11.** Lo stato di una fonte è un fatto dell'oggetto: viva, spenta dal proprietario, mai
  attivata, non disponibile, sparita, senza statistiche. *Controllo:* il censimento del 01/10 (59
  vive, 52 disabilitate, 21 non disponibili, 4 ricreate, 4 senza statistiche su 140) riprodotto dal
  metodo.
- **R12.** Nessuna copia invecchia in silenzio: lo stato delle integrazioni, la classe e l'unità
  non si congelano alla ricostruzione. *Controllo:* dopo un riavvio di HA, zero differenze fra
  HIRIS e HA (già misurato a zero per gli stati il 30/09; va esteso).

### Atomica e strutturata

- **R13.** I metodi sono **richiamabili da chiunque**: oggi le letture degli strumenti sono metodi
  privati di un oggetto che nasce a ogni turno coi permessi di una persona, e nessun attore può
  chiamarle. *Controllo:* osservatore, ricette, analista e attuatore non contengono più codice che
  elenca, nomina o colloca un'entità.
- **R14.** Gli strumenti della chat **non hanno logica propria**: ognuno è una tabella di una riga
  (definizione, metodi che compone, permesso richiesto, sigillo) e una resa. Uno strumento che è
  sottoinsieme di un altro esce. *Controllo:* le tre tabelle a mano per nome di strumento diventano
  una.
- **R15.** Il frontend **disegna e non ricalcola**: le regole che oggi vivono solo nel JavaScript
  passano al server; le utilità ricopiate fra file diventano un modulo. *Controllo:* le prove che
  legano ogni vocabolario JavaScript alla sua fonte; nessuna utilità definita in più di un file.

### Economica

- **R16.** Ogni metodo dichiara **il suo costo**: letture verso HA, caratteri in uscita per
  profondità, memoria o rete. Ogni risposta di strumento ha un tetto **in caratteri**.
- **R17.** **Unificare non costa di più.** La batteria della chat (token e tempi per domanda) e
  quella degli attori si rilanciano prima e dopo ogni tappa: se un numero peggiora, la tappa non è
  chiusa.
- **R18.** I costi fissi scendono. Obiettivi misurabili, da fissare come numeri alla tappa 0 sulla
  prima misura: nessun turno senza strumenti riceve regole sugli strumenti; il testo ripetuto fra
  regole di base, guida del ponte e descrizioni sparisce; la casa si legge una volta all'avvio; la
  gerarchia e lo specchio si calcolano una volta per turno.

### Che resti così

- **R19.** Un **cancello nel pre-push e nella CI** rifiuta un doppione nuovo: fuori dal modulo della
  casa nessuno legge i campi grezzi del registro, scrive i letterali `unavailable`/`unknown`, o
  chiama le letture del client. L'elenco lo chiede al modulo, non lo ricopia.
- **R20.** Il **registro dei doppioni è in git** e si chiude voce per voce: una voce è chiusa solo
  quando la copia è cancellata. Il lavoro è finito quando è vuoto.
- **R21.** I documenti dicono il vero: `CLAUDE.md`, `README.md` e i commenti di testa dei moduli
  descrivono ciò che esiste.

---

## §4 · La destinazione: i metodi

I nomi sono provvisori: passano dal glossario prima di entrare nel codice. Per ogni domanda la
tabella dice quante risposte esistono oggi e da quale funzione si parte — quella che i revisori
hanno indicato come la più vicina a un metodo unico.

### 4.1 La casa — un solo punto dove registri e stati si incontrano

L'anagrafe **resta**: i registri e gli stati sono due cose diverse in Home Assistant, e nessuna
delle due basta da sola. Quello che cambia è che smette di copiare e congelare ciò che è dello
specchio, e che tutti leggono da un solo punto di giunzione.

| Domanda | Oggi | Si parte da | Cosa deve restituire |
|---|---|---|---|
| **ELENCO** — quali cose, con che filtri | 6 risposte, 4 insiemi diversi (324 / 954 / 974 / tutto) | `house_query.select_subjects` | la selezione con le escluse contate; estesa ad aree, dispositivi, integrazioni, ricordi |
| **IDENTITÀ** — come si chiama | 5 regole per l'entità, 6 per il dispositivo, 2 per l'integrazione | `queries._enrich_entity` | una regola del nome per genere; il nome sempre accanto all'id |
| **DOVE** — area, piano, dispositivo, integrazione | 3 risposte, più una porta che non risponde | `topology.actual_area` | `{area, piano, dispositivo, integrazione}` con l'area ereditata |
| **TIPO** — dominio, classe, unità, statistiche | 3 formule per le statistiche, 9 copie del dominio | lo specchio, con la lettura per id | classe e unità vive; «ha statistiche» da una regola |
| **STATO** — adesso, in parole, da quando | 12 renditori su 4 proiezioni dello specchio | `EntityCache.all_states` + `rendered_state` | stato grezzo e in parole, da quando, con l'unità; lettura per id |
| **VISIBILITÀ** — è fuori? | 8 copie della regola | `digest_visible_entity_ids` | una classe per entità (**visibile · di servizio · nascosta · disabilitata**) **con la causa** e chi l'ha disabilitata |
| **SALUTE** — fonte viva? integrazione sana? | 3 risposte per l'integrazione, 2 per gli errori | `HAClient.problems`, `system_log` | lo stato della fonte (R11); le integrazioni con `disabled_by`; una lettura sola per giro |
| **STORIA** — stati, valori, esecuzioni, errori | 3 storie, 2 case dei conti | `tools._read_history`, `HAClient.traces` | uno storico richiamabile da chiunque; **i conti in una casa sola** |
| **COMPORTAMENTO** — automazioni, script, scene | 3 risposte per «attiva / ultima esecuzione» | `HAClient.behavior_configs` | corpo, stato, ultima esecuzione nella stessa risposta |
| **SERVIZI** — cosa si può comandare | 2 registri, 2 controlli prima del volo | `queries.commands_for` | i comandi, e **«verifica senza eseguire»** come metodo della porta |
| **RIFERIMENTO** — da un testo a un oggetto | 3 motori | `Lookup.verify`, `name_matches` | un motore solo, che normalizza maiuscole, accenti e articoli |
| **TEMPO** — fuso, oggi, confini del giorno | 3 politiche (casa, browser, UTC), 9 punti | `historian.day_boundaries` | un «giorno della casa»; **un solo formato dell'istante** in uscita |

In più, tenuti unici già oggi o quasi: **CALENDARIO**, **PLANCE**, **LEGAMI** (a cui mancano i nomi).

### 4.2 La resa

Una funzione per genere di oggetto, a tre profondità — corta, media, completa — ciascuna col suo
tetto in caratteri. La usano gli strumenti, le rotte e i testi per i modelli. Oggi l'entità esce in
10 forme da 12 funzioni; lo stato in parole esce da una porta sola; oltre le dieci righe `search`
toglie unità e classe.

**Un vocabolario dei campi**, deciso una volta e scritto nel glossario: un nome per
l'identificatore (oggi sei), uno per lo stato (quattro), uno per l'istante (cinque); `tipo`,
`genere` e `dominio` con un significato solo; una chiave d'errore.

### 4.3 Un turno verso un modello

| Mestiere | Oggi | Alla fine |
|---|---|---|
| Comporre il prompt di sistema | 4 compositori | uno; le regole sugli strumenti solo a chi li ha |
| Dire cosa c'è della casa | 3 forme dello stesso dispositivo | la resa del §4.2 |
| Leggere la risposta | 5 lettori JSON, 3 strategie | uno, che riconosce anche la troncatura |
| Validare e registrare | 4 registri, 3 freni, uno assente | un registro degli esiti con un freno, che non può far cadere il turno |
| Tetti | `max_tokens` in 5 posti, uno non dichiarato | dichiarato per mestiere |
| Accodare e raccogliere sul ponte | 6 e 4 copie, scadenza riletta in 8 punti | un accodamento, con priorità alla chat |
| Chi risponde | 1 decisione, 7 chiamanti, 4 «dopo» diversi | la decisione restituisce anche il runner e il seguito |

### 4.4 Scrivere, permessi, modelli, archivi

- **Scrivere su Home Assistant:** le due porte dichiarate, più la visibilità del pannello e la
  rimozione della vecchia card ricondotte a una di esse o dichiarate come terza. Una forma del
  rifiuto (oggi quattro), e il motivo di HA sempre conservato. **Si rilegge prima di scrivere.**
- **Permessi:** un cancello solo — oggi la domanda è posta in almeno 13 punti, e una regola vale
  negli strumenti e non nelle rotte.
- **Modelli:** una tabella dei provider con ordine, nome, credenziale, modello e prezzo. Oggi la
  domanda è posta in **37 punti**: una sola fonte vera (`models_config.json`), 9 tabelle parallele
  dei cinque id, 5 ordini scritti a mano, 6 definizioni di «ha una credenziale», 2 vocabolari del
  prezzo, 2 nomi per lo stesso provider. Per «quali provider esistono, come si chiamano, di che
  natura sono» non esiste nessun metodo da cui partire: va scritto.
- **Comandare:** `verification()` è già atomica, ma «verificare senza eseguire» non ha una porta
  pubblica; chi ne ha bisogno (le promesse) ricompone il controllo a mano. Costo di un comando oggi:
  nessuna lettura e una scrittura se il registro dei servizi è caldo e il bersaglio è di sole
  entità; una lettura intera dei servizi in più se è scaduto; un comando in più per area, piano,
  etichetta o dispositivo; fino a 2 secondi di attesa dell'esito.
- **Conversazione:** per ogni turno «qual è la sessione attiva» è chiesta 4 volte, e la cronologia
  è letta intera e poi tagliata da quattro tetti in due moduli. Si parte da un solo
  `ChatStore.load_context`.
- **Le operazioni delle ricette:** sono 18; 8 sono offribili al modello, le altre 10 (con `Period`,
  ~530 righe) vivono solo nelle prove ed escono alla tappa 0. Quali operazioni usino le ricette
  archiviate sulla casa non si legge dal codice: va misurato.
- **Archivi:** una riconciliazione col registro di HA; un vocabolario unico per gli stati di
  promesse, costruzioni e proposte (oggi `attesa` contro `in_attesa`, e `rifiutata` con due
  significati).

---

## §5 · Le garanzie — perché questa è l'ultima volta

1. **Il registro in git**, chiuso voce per voce (R20).
2. **Il cancello** nel pre-push e nella CI (R19). All'inizio elenca le eccezioni note — che sono le
   voci del registro — e l'elenco può solo accorciarsi.
3. **La sonda di parità** entra nel repo (`scripts/sonda_parita.py`) e si rilancia sulla casa vera a
   ogni rilascio di questo lavoro. L'attesa è zero disaccordi.
4. **La fotografia delle porte.** Prima di toccare una regola si salva ciò che esce oggi da ogni
   porta sui dati veri (nucleo, risposte degli strumenti, righe per gli attori, rotte). Dopo, o è
   identica o la differenza è quella dichiarata.
5. **Ogni voce è classificata prima.** «Pura sostituzione»: la fotografia non cambia. «Cambia
   comportamento»: decide il proprietario, sui casi veri della sua casa.
6. **Le batterie.** Quella della chat (28 domande, token e tempi) e quella degli attori — l'audit
   del 01/10 reso ripetibile — prima e dopo ogni tappa (R17).

---

## §6 · Il piano di intervento

Una tappa, uno o più rilasci piccoli, ognuno verificato dal vivo. Il piano di dettaglio di ogni
tappa — task per task, con le prove da scrivere prima — si scrive quando la tappa comincia: dipende
da cosa lasciano le precedenti.

| Tappa | Cosa | Voci | Natura |
|---|---|---|---|
| **0** | Si toglie e si prepara | M 79 · X 77 · i difetti urgenti di S | cancellazioni; nessun cambio di comportamento voluto |
| **1** | Le prove smettono di leggere il testo | T 16 | solo test |
| **2** | Un solo lettore di Home Assistant | A 39 | quasi tutta sostituzione |
| **3** | La casa: un oggetto, una risposta | B 54 | qui stanno le decisioni del proprietario |
| **4** | Una resa, un vocabolario | C 56 | cambia forme: server e pagine insieme |
| **5** | Gli strumenti | parte di C e D | catalogo, completezza, tetti |
| **6** | Un turno verso un modello | D 66 | catena e ponte uguali |
| **7** | Scrivere, permessi, modelli | E 13 · F 21 | sicurezza e coerenza |
| **8** | Gli archivi seguono la casa | G 23 | migrazioni |
| **poi** | Riparte la riparazione degli attori, poi la pagina | — | voce del BACKLOG «Gli attori si riparano dal basso» |

### Tappa 0 — Si toglie e si prepara

- **Esce** l'MCP esterno (`GET /api/entities`, `api/handlers_entities.py`, le sue prove); il codice
  senza chiamanti (`simple_chat`, `chat_stream`, `backends/embeddings.py`, `OllamaBackend`,
  `Lookup.find`, lo strumento di prova dentro `type_census.py`, le funzioni del registro dei
  servizi usate solo da uno script); le sette variabili d'ambiente lette e mai impostate; gli undici
  messaggi di avvio che dicono «il file resta» una riga prima di cancellarlo; i commenti che citano
  moduli inesistenti; le righe morte del sapere (`notevole`, `direzione`), con la loro migrazione.
- **Si correggono** i documenti che dicono il falso (`CLAUDE.md`, `README.md`).
- **Nascono**: il registro in git; la sonda nel repo; la fotografia delle porte; le due batterie con
  la prima misura; il cancello, con `censimento.py` e `doppioni.py` finalmente collegati al pre-push
  e alla CI e con l'elenco delle eccezioni note.
- **Difetti di S**: quelli che il proprietario decide di anticipare (§7, decisione 1).
- *Misura:* la fotografia delle porte prima e dopo è identica; suite verde; i numeri di partenza
  delle batterie sono scritti.

### Tappa 1 — Le prove smettono di leggere il testo

37 file di test leggono il testo di `server.py`: 13 prove ne fissano l'ordine, 16 la presenza di una
stringa. Spostare codice le rompe senza che il comportamento cambi, quindi **vanno convertite prima
di spostare qualunque cosa**. Si tengono gli otto cancelli buoni (confine degli import, contratto
del client, soffitto, classi CSS…). Le finte di Home Assistant — 68 classi in 41 file, tutte e 17
le finte di `get_states` che ignorano il filtro vero — convergono su quelle condivise, che
rispondono nella forma del vero. *Misura:* nessuna prova di ordine o di letterale su `server.py`;
suite verde.

### Tappa 2 — Un solo lettore di Home Assistant

Un solo invio WebSocket con una sola forma di ritorno (oggi sette modi di dire «è andata?»); i
registri leggibili uno per uno; lo stato per id dallo specchio, che toglie tre letture intere su
cinque; le segnalazioni e il registro degli errori letti una volta per giro e riusati; le tracce a
raffica; lo stato delle integrazioni tenuto vivo; la casa letta una volta all'avvio; il motivo di un
rifiuto di HA conservato. *Misura:* connessioni al giorno e all'avvio, prima e dopo; sonda a zero.

### Tappa 3 — La casa: un oggetto, una risposta

I metodi del §4.1. Osservatore e ricette smettono di elencare, nominare e collocare le entità con
codice loro. **Lo stato della fonte nasce qui**, come campo dell'oggetto — è lo «strato 1a» degli
attori, che a quel punto è quasi tutto fatto. *Decisioni del proprietario:* §7, da 2 a 6. *Misura:*
sonda a zero su tutte le domande; batteria degli attori.

### Tappa 4 — Una resa, un vocabolario

Le funzioni di resa del §4.2; i nomi dei campi; la chiave d'errore; il formato dell'istante. Le
regole che vivono solo nel JavaScript passano al server; le utilità ricopiate diventano un modulo;
le pagine ricevono ciò che disegnano. Ogni descrizione di strumento che nomina un campo si riscrive
nello stesso rilascio. *Decisioni:* §7, da 7 a 9. *Misura:* una funzione di resa per oggetto;
caratteri per risposta, prima e dopo.

### Tappa 5 — Gli strumenti

Una tabella per strumento al posto di tre; gli strumenti come composizioni (R14); `search` che
elenca ciò che dichiara (R9); un tetto in caratteri per ogni risposta; le descrizioni senza
ripetizioni. **I resoconti, le analisi, lo scope e l'obiettivo diventano chiedibili dalla chat**
(R8). *Decisioni:* §7, 10. *Misura:* peso del catalogo; batteria della chat, giuste e token.

### Tappa 6 — Un turno verso un modello

Il §4.3. Gli attori ricevono solo il loro mestiere; l'analista dichiara il suo tetto; un lettore
solo, che accetta ciò che osservatore e ricette già accettano; il registro degli esiti. Sul ponte:
priorità alla chat, la scadenza che viaggia col turno, la domanda lunga non più come argomento.
*Decisioni:* §7, 11 e 12. *Misura:* turni troncati (oggi 7 su 8 dell'analista); caratteri fissi per
turno; batteria degli attori su catena.

### Tappa 7 — Scrivere, permessi, modelli

Le porte di scrittura; **rileggere prima di scrivere** (S-17); una forma del rifiuto; il cancello
unico dei permessi, che vale anche sulle rotte; l'identità dei servizi firmati sulla chiave; la
tabella unica dei provider. *Decisioni:* §7, 13 e 14.

### Tappa 8 — Gli archivi seguono la casa

La riconciliazione di scope e ricette col registro di HA; il vocabolario unico degli stati; le
colonne scritte e mai lette; la potatura della coda del ponte anche a ponte spento; i file residui.
*Decisioni:* §7, 15 e 16.

### Chiusura

Registro vuoto; cancello senza eccezioni; sonda a zero; le batterie non peggiorate; `CLAUDE.md` e
`README.md` riscritti sul codice che c'è.

---

## §7 · Le decisioni che restano al proprietario

| # | Decisione | I casi veri | La mia proposta |
|---|---|---|---|
| 1 | Quali difetti di S si correggono subito, in un rilascio a sé | S-17 può perdere un lavoro tuo; il corpo delle automazioni è aperto a un «lettore» | Anticipare questi due; gli altri nella loro tappa |
| 2 | Il nome: con o senza il prefisso del dispositivo | 944 entità su 1.525 | Il nome vivo, che è quello che vedi in HA; uguale ovunque |
| 3 | Le ricette vedono solo ciò che l'osservatore guarda | 1.138 entità in meno nel loro prompt | Sì |
| 4 | L'area ereditata arriva all'osservatore | 194 entità su 324 | Sì |
| 5 | Il consumato segue la regola di Home Assistant | 28 conti su 272 su 7 giorni | Sì |
| 6 | La ricerca per nome ignora maiuscole, accenti, articoli | 39 integrazioni su 39 falliscono con una maiuscola | Sì |
| 7 | I nomi dei campi: quale tengo per id, stato, istante | 6, 4 e 5 nomi oggi | Da scegliere insieme, sul glossario |
| 8 | La chiave d'errore | `error` in 12 file, `errore` in 11 | `errore`: il dominio è in italiano |
| 9 | L'istante verso il modello | 4 forme oggi | Fuso della casa, una forma |
| 10 | `fetch`: esce, o resta come alias di `search` | 11 chiamate contro 194 | Esce |
| 11 | Sul ponte gli attori usano il modello che scegli tu | oggi «sonnet» fisso | Sì |
| 12 | Nomi di persone e tracker nel prompt dell'osservatore | partono senza maschera | Restano fuori, salvo che l'obiettivo li chieda |
| 13 | Un attore non è una persona: cosa può leggere | oggi il cancello non gli nega niente | Sola lettura dichiarata, scritta nella spec |
| 14 | Servizi firmati: cosa legge un «lettore» | oggi anche i corpi delle automazioni | Come una persona che non amministra |
| 15 | Le 7 proposte in attesa nate su dati rotti | bloccherebbero l'attuatore al riavvio | Si chiudono |
| 16 | `chatbots.json`, `agents.json`, i vecchi `usage*.json` | residui senza lettore | Si cancellano |

Le altre fra le 49 voci marcate «decisione del proprietario» nel registro sono più piccole: arrivano
una per una, coi loro casi, quando la tappa le tocca.

---

## §8 · I criteri di accettazione dello sprint

1. Il registro dei doppioni è vuoto: ogni voce chiusa cancellando la copia.
2. La sonda di parità sulla casa vera dà zero disaccordi su tutte le domande.
3. Il cancello è attivo nel pre-push e nella CI, senza eccezioni.
4. La batteria della chat non è peggiorata né in risposte giuste, né in token, né in tempi; i costi
   fissi del §1.4 sono scesi dei valori fissati alla tappa 0.
5. La batteria degli attori dà almeno i risultati di partenza, senza turni troncati.
6. Osservatore, ricette, analista e attuatore non contengono codice che elenca, nomina o colloca
   un'entità.
7. Ogni rilascio è stato verificato dal vivo.
8. `CLAUDE.md` e `README.md` descrivono ciò che esiste.

---

## §9 · Fuori perimetro, dichiarato

- **La riparazione degli attori** (misure dell'obiettivo, analista, attuatore con gli strumenti):
  riparte dopo, dalla voce del BACKLOG. Di quella fa parte qui solo lo stato della fonte, perché è
  un campo dell'oggetto.
- **Il dato congelato** — una fonte che Home Assistant dà per viva e che tace: regole per tipo di
  cosa, nel sapere. È lo «strato 1b», dopo.
- **La pagina dell'osservatore** e il suo nome.
- **La rinomina delle colonne italiane** del database: debito di una fetta sua.
- **Accendere il ponte**, e la leva `ToolSearch`.

---

## §10 · Cosa l'analisi non ha stabilito

- **I token non sono mai stati misurati**: ogni cifra in token è una conversione dai caratteri. La
  prima misura vera è nella tappa 0.
- **I tempi** di gerarchia, specchio, nucleo e indice dei nomi: si conoscono le chiamate, non i
  millisecondi.
- **46 voci «non verificate»**: dedotte dal codice e non eseguite. Si verificano quando la tappa le
  tocca.
- **Le voci nuove non hanno numeri della casa**: la copertura era sola lettura. I numeri misurati
  sono quelli della sonda, su nove domande.
- **Otto contraddizioni aperte** fra rapporti, quasi tutte conteggi: elencate in coda al registro.
  Il complemento della matrice ne ha sciolte quattro (i punti dei provider sono 37; il conto
  sbagliato del consumato non è raggiungibile dalla produzione; due sulla matrice).
- **Tre difetti letti e non provati dal vivo** perché la casa non ne ha il caso: l'avviso «il
  bersaglio è cambiato» di una promessa non può mai partire (S-20; in casa ci sono 2 promesse e
  nessuna del tipo «fai»); la copertura delle misure è calcolata sul campione e il rifiuto sotto il
  75% non scatta; il difetto dormiente dell'attuatore (S-01).
- **L'uso reale degli strumenti** viene per 158 turni su 180 dal canale di sviluppo: misura prove,
  non persone. `history` non è mai stato chiamato dal vivo.
- **Retro Panel**: non si sa cosa legga delle nostre risposte; il suo codice è in un altro repo.
- **Non letti:** i fogli di stile, i test JavaScript.

---

## §11 · Dove sono le prove

In `docs/superpowers/audit-2026-10-01/` — cartella fuori da git, archivio dell'analisi:

- `REGISTRO-DEI-DOPPIONI.md` — il registro v1, con il dettaglio di 155 voci.
- `INDICE-DEL-REGISTRO-v2.md` — le 458 voci; copia tracciata: `2026-10-01-registro-dei-doppioni.md`.
- `MATRICE-FUNZIONALITA-DOMANDE.md` — 59 funzionalità per 30 domande, una scheda per domanda, il
  catalogo di 456 funzioni, i costi; `MATRICE-COMPLEMENTO-44-FILE.md` per comandare, modelli,
  conversazione e le rotte delle pagine.
- `doppioni-1…8`, `copertura-1…9`, `database.md`, `mcp-esterno.md`, `strumenti-per-attori.md` — i
  rapporti.
- `sonda-parita.md`, `sonda_parita.py` — la sonda e i suoi numeri.
- `analista.md`, `attuatore.md`, `osservatore.md`, `strato1-fonte.md`, `pagina.md` — l'audit degli
  attori e della pagina, da cui tutto è partito.

---

## §12 · STATO

- **01/10/2026** — analisi chiusa; documento in bozza. Rilasciata la 3.72.2 (attuatore in pausa).
  **In attesa:** il sì del proprietario a questo documento e alle decisioni del §7; poi il piano di
  dettaglio della tappa 0.
- **01/10/2026, sera** — il proprietario fa partire lo sprint e risponde «procediamo» all'elenco delle
  domande aperte (piano, dichiarazioni D1–D13, decisione 1). Decisione 1 del §7: i due difetti su
  dati e permessi (S-17 e `GET /api/home-space` a un «lettore») si correggono in un rilascio a sé,
  subito dopo la Tappa 0. Piano della Tappa 0 approvato:
  `docs/superpowers/plans/2026-10-01-tappa-0-si-toglie-e-si-prepara.md` (cartella fuori da git).
  Le misure della tappa: `docs/misure/2026-10-tappa-0.md`.
  L'ordine dopo la Tappa 3 (domanda (b)): **a scaglioni** -- tappe 0-3, strati 1 e 2 degli attori,
  tappe 4-6, strati 3 e 4, tappe 7-8. Ogni strato nasce sul pezzo gia' unificato.
