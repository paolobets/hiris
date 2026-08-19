# Lo Schedulatore — specifica

> **Fetta 3 dell'azione**: comandare → costruire → **schedulare**.
> Il fondamento, l'ordine e i confini stanno in `docs/design/2026-08-12-azione-design.md` §5;
> questo documento decide la forma dell'oggetto.
> Misurato con le **quattro fondamenta** e le **tre leggi** di `CLAUDE.md`.

## 0. Da dove nasce, e cosa lo fa nascere adesso

Lo schedulatore era già scritto nel contratto dell'azione, ed era già nominato nel codice: la
docstring di `azione/porta.py` dice, dalla fetta «comandare», *«Lo schedulatore (fetta 3) e il brain
faranno lo stesso»*. È la ragione per cui `esegui()` prende un'`origine` e non sa nulla di chi la
chiama. **La porta non va toccata**: questa fetta la usa com'è, ed è la prova che l'invariante «una
porta sola» funzionava davvero.

Lo fanno nascere adesso tre frasi del proprietario, che sono anche i tre casi di prova di questa
fetta:

1. «Alle 17 accendi lo studio.»
2. «Fra un'ora verifica la temperatura della camera da letto, se è aumentata notificamelo.»
3. «Fra due ore dimmi se è possibile aprire le finestre per rinfrescare la casa.»

Non sono la stessa cosa, e trattarle come se lo fossero sarebbe il difetto: la prima è una chiamata
di servizio, la seconda è un confronto con **un valore di adesso**, la terza è giudizio che nessuna
regola scrive.

## 1. Cos'è, in una frase

> **Un magazzino con un orologio.** Tiene *cosa* e *quando*. Non decide, non interpreta, non sa chi
> gli ha scritto: al momento giusto passa dalla porta di tutti.

## 2. Perché non è un'automazione di Home Assistant

La Legge I pretende una risposta, e questa fetta ne ha due.

**Per le promesse una-tantum:** fare «accendi fra un'ora» creando un'automazione vera riempie la
configurazione dell'utente di automazioni usa-e-getta che nessuno cancella. Una promessa che scade
quando è mantenuta non è un oggetto che Home Assistant sappia tenere.

**Per il confronto con «adesso»:** «se è aumentata» rispetto al valore delle 16:03 richiede che quel
valore sia stato messo da parte alle 16:03. In Home Assistant servirebbe un `input_number` creato ad
hoc — cioè di nuovo configurazione usa-e-getta.

**Le ricorrenze invece restano di Home Assistant.** «Ogni sera alle 22 spegni tutto» è
un'automazione, e HIRIS lo dice e la propone (fetta «costruire»). Lo Schedulatore non ha calendari,
non ha regole di ricorrenza, non ha ora legale da gestire: solo istanti. Vedi §11.

## 3. Perché non è autonomia

La spec dell'azione tiene fuori il brain perché *«HIRIS non decide quando agire»* (§6). Qui **il
quando lo decide l'utente**: una promessa che pensa non è autonomia, è una domanda differita.

Ciò che va vietato — e che questa spec vieta strutturalmente, non a parole — è che un turno di
modello che gira **senza nessuno davanti** possa toccare la casa. Vedi §6.2.

Resta perciò vera la frase che `hiris/config.yaml` dichiara al mondo: *«It never acts on its own:
every action starts from a sentence you type»*. Differita, ma tua.

---

## 4. L'oggetto e i suoi confini

`hiris/app/schedulatore/`, tre file:

| File | Cosa tiene |
|---|---|
| `archivio.py` | SQLite (`/data/promesse.db`) — **l'unica casa** di «cosa e quando» |
| `promessa.py` | la forma di una promessa: validazione, e **una sola** serializzazione |
| `orologio.py` | il battito: chi è scaduto, chi si è perso, chi si sveglia |

**Non importa né la chat, né il modello, né Home Assistant.** Al montaggio riceve da `server.py` due
funzioni:

- `esegui(chiamata, origine)` — è `azione/porta.py`, invariata;
- `interpreta(domanda, istantanea)` — un turno di modello, con il catalogo ristretto di §6.2.

È la stessa disciplina che ha reso riusabile la porta: chi la chiama non le appartiene. Conseguenza
pratica: lo Schedulatore si prova **per intero** con due finte, senza Home Assistant e senza LLM.

**Non ha un timer per promessa.** Un timer in memoria muore al riavvio e diventa un secondo posto che
sa *quando*: la verità è sempre e solo la tabella. L'orologio è un **battito fisso ogni 15 s** che
chiede all'archivio chi è scaduto — **un solo job** registrato sull'`AsyncIOScheduler` già presente
in `server.py`, non un secondo meccanismo di tempo. Un battito fisso, per giunta, non si perde se
l'ora di sistema salta (NTP, ora legale).

## 5. L'anatomia di una promessa

Fondamenta n.1: deve potersi leggere **da sola**, anche fra sei mesi, anche se la chat che l'ha
generata non esiste più.

| Campo | Cosa porta |
|---|---|
| `id` | l'identificatore |
| `specie` | `fai` oppure `chiedi` |
| `frase` | **la frase dell'utente, verbatim** — non riassunta, non riscritta. Come `testo` in `ricorda` |
| `quando_ts` | l'istante assoluto (epoch UTC) |
| `quando_detto` | come l'utente l'ha espresso: «fra un'ora», «alle 17» |
| `fuso` | il fuso della casa **usato per risolvere** `quando_detto` in `quando_ts` |
| `chiamata` | *(solo `fai`)* `servizio` + `bersaglio` + `dati` — la stessa identica forma di `esegui` |
| `domanda` | *(solo `chiedi`)* cosa deve guardare e a cosa deve rispondere |
| `istantanea` | *(solo `chiedi`, facoltativa)* i valori di partenza: entità, valore, **unità**, istante della misura |
| `recapito` | il servizio `notify.*` scelto e **verificato alla nascita**, oppure nulla |
| `stato` | `in_attesa` · `in_corso` · `mantenuta` · `saltata` · `disdetta` · `fallita` |
| `motivo` | perché non è andata — **solo** per `saltata` e `fallita` |
| `esecuzione_id` | il collegamento alla riga di cronaca (§8), quando un'esecuzione c'è stata |
| `testo` · `avvisare` | *(solo `chiedi`)* il testo concluso dal turno, e se c'era qualcosa da dire — gli stessi due nomi che porta `concludi` (§6.2) |
| `nata_ts` · `risvegliata_ts` | quando è nata, quando l'orologio l'ha vista |
| `origine` | traccia della nascita: `chat` + id di sessione, **riferimento che può restare orfano** |

Tre note che sono le fondamenta applicate, non decorazione.

**`istantanea` è il caso 2 reso atomico.** «È aumentata» rispetto a **21,4 °C misurati alle 16:03**,
scritto dentro la promessa. Senza quel campo la promessa è il `72` senza unità: un numero che chi lo
riceve non può interpretare.

**`fuso` non è un doppione del fuso della casa.** Il fuso vivo ha una casa sola — `casa/nucleo.py`,
letto da `get_config`. Qui si registra **quale fuso è stato usato in quel momento** per risolvere
«alle 17»: è una misura fatta a un istante, non la copia di un fatto vivo. Se domani la casa cambia
fuso, `quando_ts` resta ciò che è stato promesso, e la promessa continua a spiegarsi da sola.

**`origine` è una traccia, non una casa.** Cancellare una conversazione non deve poter cancellare una
promessa né renderla illeggibile: per questo `frase` sta qui, verbatim, e non è un puntatore.

## 6. Le due specie

### 6.1 `fai` — la promessa che agisce

«Alle 17 accendi lo studio.» Arriva l'ora, l'orologio chiama `porta.esegui(chiamata,
origine="schedulatore")`. **Nessun modello, costo zero in token, esito deterministico**: la porta
verifica contro questa installazione, esegue, rilegge lo stato — cioè dice cosa è successo, non cosa
è stato chiesto. L'esito finisce in cronaca (§8) e la promessa vi si collega.

### 6.2 `chiedi` — la promessa che guarda e risponde

«Verifica la temperatura, se è aumentata notificamelo.» · «Posso aprire le finestre?»

Arriva l'ora e parte **un turno di HIRIS con i soli strumenti di lettura**:

| Ha | Non ha |
|---|---|
| `cerca` · `guarda` · `legami` · `richiama` · `concludi` | `esegui` · `ricorda` · `prometti` · `promesse` · `disdici` |

`concludi` **esiste solo in questo catalogo**: dalla chat non si vede, perché in chat a concludere è
la risposta all'utente.

Le tre esclusioni oltre a `esegui` non sono zelo: un modello che gira senza nessuno davanti **non
tocca la casa** (`esegui`), **non scrive nella memoria** — che entra verbatim nel prompt di sistema, e
la cui sanificazione oggi è irraggiungibile — e **non si dà appuntamenti da solo** (`prometti`), che
sarebbe autonomia costruita per sbaglio.

**Quel turno finisce in un modo solo: chiamando `concludi(avvisare, testo)`.** Così il silenzio è un
**fatto dichiarato** — «condizione non verificata, non ti ho disturbato» è un esito **riuscito**, e
finisce nel registro — invece di essere indovinato da una risposta vuota. Un turno che finisce senza
concludere lascia la promessa `fallita` col motivo *«il turno non ha concluso»*: mai un «forse è
andata bene».

La notifica non la manda il modello. La manda **lo Schedulatore**, attraverso la porta, sul canale
approvato alla nascita, e solo se `avvisare` è vero.

Se `avvisare` è vero ma alla nascita non era stato scelto nessun recapito, **non si inventa un
canale**: il testo resta nella promessa e si legge dalla pagina. La promessa è `mantenuta`, e lo
dichiara — «avevo qualcosa da dirti e nessun modo per venire a cercarti» — invece di far passare per
riuscita una consegna che non c'è stata.

## 7. L'orologio, e la regola del mai-in-ritardo

**Una tolleranza sola, dichiarata: 120 secondi.** Non configurabile per promessa — un ramo in meno, e
un numero che si scrive nella spec invece di indovinarlo. Copre il caso vero per cui esiste: un
aggiornamento dell'add-on che cade sopra l'orario.

Oltre quella soglia la promessa diventa **`saltata`** e **non viene mai eseguita in ritardo**: una
luce che si accende alle 19 perché doveva accendersi alle 14 è peggio di una luce spenta.

Il motivo dice ciò che è stato **misurato**, non una causa inventata:

> «scaduta da 41 minuti quando l'orologio l'ha vista — non eseguita»

HIRIS non sa *perché* era ferma; sa di quanto è in ritardo, e dice solo quello.

**Mai due volte.** Prima di mantenerla, la riga passa a `in_corso`. Se l'add-on muore lì in mezzo, al
riavvio quella riga diventa `fallita` col motivo *«l'add-on si è fermato mentre la manteneva»* — e non
riparte. Una luce accesa due volte è innocua; una serranda no, e la regola dev'essere una sola.

## 8. Il registro delle esecuzioni

La fetta «comandare» prevedeva *«il registro di ciò che è stato fatto: una riga leggibile per
esecuzione»*. **Non è mai stato costruito**: `porta.py` scrive una riga di `logger.info` e basta. Per
la fondamenta n.4 quel registro non esiste — nessuno può chiederlo.

Questa fetta lo costruisce, **una volta sola, accanto alla porta**: `hiris/app/azione/cronaca.py`.

- Ogni esecuzione che passa da `porta.esegui` scrive una riga: cosa, su cosa, esito, e l'**origine**
  (`chat` o `schedulatore`). È esattamente ciò per cui `origine` era stato messo nella porta.
- **Il nome non è `registro.py`**: in `azione/` quel nome è già il registro *dei servizi* (cosa Home
  Assistant sa fare). Due cose diverse non possono chiamarsi allo stesso modo in due file vicini.
- **La promessa non ricopia l'esito.** Tiene ciò che è solo suo (`stato`, `motivo`, e per un `chiedi`
  `detto` e `avvisare`, che non hanno altra casa) e si collega per `esecuzione_id`. Da un `fai` si
  guarda cosa è cambiato **leggendo la riga**, non una copia che prima o poi mentirà.
- Anche la notifica spedita per conto di un `chiedi` è un'esecuzione: passa dalla porta e finisce in
  cronaca con `origine="schedulatore"`. Uniforme.

Senza questa scelta lo stesso fatto — un'azione eseguita — avrebbe due trattamenti a seconda di chi
l'ha chiesta: una violazione della fondamenta n.3, e un doppione costruito sapendo che è un doppione.

### 8.1 Quanto si conserva

**Novanta giorni**, per le promesse concluse e per le righe di cronaca. Un registro che cresce per
sempre su una scheda SD è un guasto rimandato, e «lo poterà qualcuno» non è una decisione.

La potatura avviene **alla scrittura** — chi inserisce una riga cancella quelle più vecchie della
soglia — e non con un lavoro periodico: un lavoro in più sarebbe un secondo posto che sa *quando*,
cioè precisamente ciò che §12 si è impegnata a togliere. Le promesse **in sospeso non si potano
mai**, qualunque età abbiano: il tetto dei 30 giorni di §9.1 le tiene già entro un limite.

## 9. Come nasce, come si disdice

Tre strumenti nuovi, coerenti con la coppia `ricorda`/`richiama`:

| Strumento | Cosa fa |
|---|---|
| `prometti` | crea una promessa dalla frase dell'utente |
| `promesse` | elenca ciò che è in sospeso e com'è andata |
| `disdici` | annulla una promessa in attesa |

`promesse` esiste per la fondamenta n.4: se non si può chiedere «cosa mi hai promesso?», le promesse
non esistono.

### 9.1 Il modello propone, il codice restringe

Alla nascita **tutto viene verificato adesso, non fra due ore**:

1. la `chiamata` di un `fai` passa da `azione/verifica.py` contro **questa** installazione. «Alle 17
   accendi lo studio» viene rifiutato **ora**, col motivo vero, se `light.studio` non esiste — invece
   di fallire in silenzio alle 17;
2. il `notify.*` del recapito deve esistere nel registro dei servizi;
3. l'`istantanea` di un `chiedi` viene presa **adesso** dallo specchio dello stato, con l'unità;
4. `quando` diventa un istante assoluto risolto col fuso della casa. **A risolvere l'espressione è il
   modello** — «fra un'ora», «alle 17» — e a rifiutare è il codice: un istante passato non si
   corregge da soli tirando a indovinare il giorno. Il rifiuto lo dice con la domanda dentro: *«le 17
   di oggi sono passate: intendevi domani?»*;
5. **due tetti dichiarati**: non si promette oltre **30 giorni**, e non stanno in sospeso più di **50**
   promesse insieme. Servono perché un modello che va in circolo non deve poter riempire il disco. Il
   rifiuto dice quale tetto è stato toccato.

Il rifiuto porta sempre il motivo (§2.5 della spec dell'azione): mai un fallimento che sembra un
guasto.

### 9.2 Disdire

`disdici` dalla chat e il bottone della pagina chiamano **la stessa funzione**. Una promessa già
mantenuta o già saltata non si disdice: si legge.

## 10. La faccia

Voce nuova nella pagina di configurazione: **Promesse**, accanto ad Albero, Memoria, Modelli, Uso.

- **In sospeso**, in alto: quando, cosa, la frase dell'utente, un bottone per disdire.
- **Storico**, sotto: quando doveva, cosa è successo, lo stato, e **il motivo quando è andata male**.

`GET /api/promesse` · `DELETE /api/promesse/{id}`.

**Una sola funzione di serializzazione**, in `promessa.py`, usata sia dallo strumento del modello sia
dalla rotta HTTP — con un test che le confronta campo per campo. Una promessa vista dalla chat e vista
dalla pagina è la stessa promessa, con gli stessi campi e gli stessi nomi (fondamenta n.3).

La pagina si disegna dopo aver interpellato `ux-ui-specialist`, com'è regola qui.

## 11. Cosa non entra, e perché

| Fuori | Perché |
|---|---|
| **Le ricorrenze** | «ogni sera alle 22» è un'automazione HA. HIRIS lo dice e la propone (fetta «costruire»). Niente calendari, niente regole di ricorrenza, niente ora legale |
| **Una promessa che tocchi la casa senza l'utente** | non esiste: il *quando* lo decide l'utente, e il turno di `chiedi` non ha `esegui` |
| **I sei lavori interni di sistema** | inventario, comportamento, retention, spazzata della coda restano su APScheduler. La loro migrazione è la **fetta successiva**, §12 |
| **Le sicurezze** | prima le strutture, poi le difese, derivate dai rischi veri della struttura nuova |
| **La plancia** | fetta propria, per la ragione di §4.3 della spec dell'azione |

## 12. La fetta successiva, dichiarata

Oggi in HIRIS ci sono **due cose che sanno quando**: l'`AsyncIOScheduler` di `server.py`, con i sei
lavori di sistema, e lo Schedulatore. È una tensione con la fondamenta n.2, e si accetta **per una
fetta sola**, per non mettere a rischio ricarica dell'inventario e retention dentro una fetta che deve
aggiungere una capacità nuova.

La fetta successiva porta i sei lavori sotto lo Schedulatore e toglie APScheduler dal prodotto e da
`requirements.txt`. Per questo l'archivio e l'orologio si disegnano **già capaci** di reggere un
lavoro che si ripete e non appartiene a nessun utente: la specie è un campo, non un `if`.

**Non è in contraddizione con §11.** Ciò che resta fuori sono le *ricorrenze dell'utente* — «ogni sera
alle 22», che è un'automazione di Home Assistant per la Legge I. Un lavoro di sistema che si ripete
non è una promessa di nessuno: Home Assistant non lo conosce, non lo può fare, e la Legge I non ha
nulla da obiettare.

## 13. Come si prova

La regola di questo progetto: **la finta deve saper produrre il difetto**, altrimenti il test non può
fallire. Per ogni prova, la mutazione che deve farla diventare rossa.

| Prova | Mutazione che deve farla fallire |
|---|---|
| Una promessa scaduta durante uno spegnimento non viene eseguita | togliere il controllo della tolleranza |
| Una promessa sopravvive al riavvio | tenerla in memoria invece che in tabella |
| Una promessa non viene mantenuta due volte | non scrivere `in_corso` prima di chiamare la porta |
| Il turno di `chiedi` non ha `esegui` | la finta del runner **prova** a chiamarlo: se il catalogo glielo passasse, il test lo vedrebbe |
| Silenzio dichiarato | `concludi(avvisare=false)` → nessuna chiamata alla porta, **ma una riga nel registro** |
| Rifiuto alla nascita | servizio inesistente → il rifiuto deve arrivare ora, col motivo vero |
| I due tetti | la 51ª promessa e quella a 31 giorni vengono rifiutate, dicendo quale tetto |
| Stessa forma dalle due porte | lo strumento e la rotta HTTP confrontati campo per campo |
| La cronaca registra anche la chat | un'esecuzione con `origine="chat"` scrive la sua riga |

### 13.1 La verifica che nessun banco può dare

La spec dell'azione la pretende per questa fetta, ed è la condizione di pubblicazione:

1. **un riavvio dell'add-on con qualcosa in sospeso** — la promessa deve essere ancora lì;
2. un riavvio **che scavalca l'orario** — la promessa deve risultare `saltata`, col ritardo misurato;
3. un `fai` che accende **una luce vera**;
4. un `chiedi` che **tace davvero** quando non c'è niente da dire, e che notifica quando c'è.

## 14. Rilascio

È `feat` → minor: **3.7.3 → 3.8.0**, col cancello pre-push da passare
(`python scripts/verifica_componenti.py`).

Chiusura della fetta con la **review totale** dell'intero ramo (`python scripts/censimento.py`), non
del solo diff: si cerca ciò che è rimasto orfano, non solo ciò che è stato aggiunto.
