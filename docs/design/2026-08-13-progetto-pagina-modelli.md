# La pagina Modelli — progetto

Ramo `2.0`, HEAD `a3f9f7e`, versione `2.4.1`. Soggetto: la rotta `#/models` della SPA di
configurazione (`hiris/app/static/config/models-route.js`), e il confine fra questa pagina e la
scheda Configurazione dell'add-on nel Supervisor.

Questo è un **progetto**, non una modifica: nessun file di prodotto è stato toccato. Tutto ciò che
segue è verificato leggendo il codice; dove non l'ho potuto verificare lo dico.

---

## 0. Le sei cose che ho verificato, e che cambiano il progetto

Prima di progettare qualcosa ho letto cosa succede davvero. Sei fatti, tutti con la riga che li
prova, e ognuno sposta una decisione di disegno.

**(1) La catena di ripiego funziona davvero — sul percorso che il prodotto usa.**
`llm_router.chat` (`llm_router.py:162-179`) cicla la catena solo quando il modello richiesto è
`"auto"`; `chat_stream` (`:181-193`) non ha nessun ciclo di ripiego, prende il primo e basta. Ma la
chat di HIRIS **non fa streaming**: `static/chat/send.js:143-147` fa `POST api/chat` con
`Content-Type: application/json` e legge `r.json()` — nessun `Accept: text/event-stream`, nessun
`stream: true`, quindi `wants_stream` (`handlers_chat.py:538-541`) è falso in produzione. Il ramo
SSE esiste ed è raggiungibile solo da un client API esterno. **Conclusione: la parola «catena» è
onesta, e il progetto può disegnarla.** Ma è un'onestà che regge su un dettaglio del frontend: se
un giorno la chat inizierà a fare streaming, questa pagina comincerà a mentire senza che nessuno
tocchi questa pagina. Va pinnato (§13).

**(2) La catena esiste solo quando il modello della chat è `"auto"`.**
`handlers_chat.py:498` legge `impostazioni.model` e lo passa dritto a `runner.chat(model=...)`;
`llm_router.chat:164-168` se non è `"auto"` chiama `self._route(model)` e **una sola volta**. Quindi
un modello fissato nella pagina *Impostazioni chat* **scavalca l'intera pagina Modelli**: sceglie il
provider, salta la catena, annulla il ripiego. Oggi la pagina Modelli non lo nomina mai. È il primo
buco da chiudere, ed è più grave di tutti quelli che il brief elencava.

**(3) L'abbonamento non è un anello: è un bivio a monte.**
`handlers_chat.py:408`: `if request.app.get("ponte_attivo") and _bridge_on(request.app):` — è
*prima* della riga che prende il router (`:430`). Se il ponte è acceso, **ogni** turno va in coda e
**la catena non viene consultata mai**. E il ritorno non esiste: un job scaduto resta `expired`
(`server.py:1414-1421`), il tetto giornaliero risponde 429 e il messaggio non parte
(`handlers_chat.py:421-427`; `docs/prova-la-2.0.md:102-104` lo dichiara: «non c'è ripiego automatico
su un altro provider»). **Quindi la frase che il proprietario vuole — «usa il piano Claude Max, e se
non è disponibile passa a OpenRouter» — oggi non è solo inesprimibile nella pagina: è inesistente
nel prodotto.** Il progetto deve dire cosa la pagina disegna prima che quel ripiego esista, e cosa
serve al backend perché esista (§11).

**(4) Il modello dell'abbonamento è un effetto collaterale del modello di Claude API.**
`handlers_chat.py:282-285` compone `modello_cli(resolve_model(impostazioni.model, "chat",
provider_models["claude"]))`. Quando il modello della chat è `"auto"`, il valore che entra è il
default **di Claude API**, e `modello_cli` (`agent/runner.py:537-567`) lo riduce per sottostringa a
`opus`/`haiku`/`sonnet`, con ripiego su `sonnet` e un `log.warning` per tutto il resto. Due
conseguenze che il progetto deve rendere visibili: cambiare il modello di Claude API cambia il
modello che gira sul piano, e `claude-opus-4-7` e `claude-opus-4-1` producono **lo stesso identico**
comportamento sul ponte. La granularità del selettore è vera per l'API e finta per l'abbonamento.

**(5) Il salvataggio non è a caldo — ma solo per tre dei cinque.**
`server.py:1461` legge `provider_models` una volta e lo passa come argomento di costruzione ai tre
runner (`:1468`, `:1480`, `:1523`), che poi leggono solo `self._default_model`. Invece
`handlers_chat.py:282` rilegge `request.app["models_config"]` **a ogni turno**, e
`handlers_models.py:205` aggiorna quel dizionario a ogni PUT. Risultato: cambiare il modello di
Claude API dalla pagina **non ha effetto sull'API fino al riavvio, e ha effetto immediato sul
ponte**. La didascalia `riapplicato al riavvio dell'add-on` (`models-route.js:314`) è quindi giusta
per metà e sbagliata per l'altra metà, sullo stesso valore. Questo è il difetto peggiore che ho
trovato, perché è la pagina che dice una cosa falsa su se stessa.

**(6) `provider_models["ollama"]` è un fantasma, non un doppione.**
`_clean_provider_models` (`handlers_models.py:28-34`) itera solo `_PROVIDER_MODEL_KEYS =
("claude","openai","openrouter")`, sia in lettura (`:72`) sia in scrittura (`:84`): una chiave
`ollama` inviata da un client viene scartata prima di toccare il disco. `"ollama"` sta in
`_VALID_BACKENDS` solo per essere ammesso in `chain_order`, che è un altro campo. Il modello di
Ollama ha **una sola casa**, `local_model.model` → `LOCAL_MODEL_NAME` → `fixed_model`
(`server.py:1488`), e `_resolve_model` lo restituisce **prima** di ogni altro ramo
(`openai_compat_runner.py:403-404`) — quindi vince persino su un modello fissato esplicitamente.
Nessun difetto da riparare: c'è solo da spostarlo dove si decide.

**Cosa non ho verificato.** Non ho eseguito la pagina né chiamato le API. Non ho verificato che
`POST /addons/self/restart` funzioni da dentro l'add-on: `hassio_api: true` c'è (`config.yaml:28`),
`SUPERVISOR_TOKEN` è disponibile (`server.py:700`), ma **nessun chiamante esiste oggi nel
codice** — è un'assunzione, e la marco come tale in §11.

---

## 1. La diagnosi: la pagina descrive una configurazione, e serve una decisione

Oggi `#/models` risponde alla domanda «com'è configurato?». Ogni riga è vera. Il difetto è che
nessuna riga è in relazione con le altre, e la domanda che l'utente ha davvero — **«chi risponderà
al mio prossimo messaggio, e quanto mi costa?»** — non ha nessun posto dove essere risposta.

Percorriamo l'impianto vero del proprietario, così com'è, riga per riga, come la pagina lo mostra
adesso:

| Cosa la pagina mostra | Cosa succede davvero |
|---|---|
| Claude API — pallino verde, badge «Attivo» | È il primo della catena `balanced`. Ogni messaggio ci passa, l'API risponde `400 credit balance too low`, `claude_runner.py:830-834` lo trasforma in `RunnerBackendError`, `llm_router.py:175` logga «Backend ... failed, trying next». **Ogni singolo messaggio paga una chiamata fallita di latenza, per sempre.** |
| Abbonamento — badge «Disattivato» | Il token c'è, il piano è pagato, il ponte è spento. La cosa migliore che ha è l'unica che non usa. |
| OpenRouter — pallino verde, badge «Attivo» | È lui che risponde. A consumo. |
| «Catena automatica»: 1. Claude API · 2. OpenRouter | Vero. E illeggibile: dice l'ordine, non dice che il primo non risponde mai. |

Tutte le informazioni per dirgli «stai pagando due volte» sono già a schermo. **La pagina è vera
riga per riga e falsa nel complesso.** Non le manca un dato: le manca una frase.

E c'è una parola che fa danno più di tutte. **«Attivo» non è un fatto che il sistema possa
sostenere.** Vuol dire «l'interruttore è acceso e la credenziale c'è» — cioè una proprietà della
configurazione — ma chi la legge capisce «funziona», che è una proprietà della capacità. Claude API
a credito zero è «Attivo» e non può rispondere. Questa parola è la bugia strutturale della pagina, e
il progetto la ritira (§4).

---

## 2. Il principio: la pagina è una frase, e tutto il resto la giustifica

Una sola regola di composizione, da cui discende tutto il resto:

> **In cima alla pagina c'è una frase sola: chi risponde al prossimo messaggio. Tutto ciò che sta
> sotto è la ragione per cui è quella, o il modo di cambiarla.**

Per l'impianto del proprietario quella frase è:

> **Il prossimo messaggio va a OpenRouter,** con `anthropic/claude-sonnet-4-6`, a consumo.
> Claude API è primo in catena e ha rifiutato le ultime 40 richieste: credito esaurito.
> Il Piano Claude Max ha il token, lo paghi, ed è fuori dalla catena.

È la frase che la pagina non gli ha mai detto. Deve essere la prima cosa della pagina e il testo più
grande della pagina.

Tre corollari, che sono il metro di ogni scelta più sotto:

**(a) La pagina non mostra mai una configurazione, mostra un esito.** Non «l'interruttore di Claude
API è acceso», ma «Claude API è il primo che HIRIS prova». Se un giorno tornasse una regola di
compatibilità come `model_activation.py:22`, una pagina che mostra gli esiti la renderebbe visibile
da sola, senza che nessuno la insegni alla pagina. È la risposta strutturale al difetto 3 del brief,
e la sviluppo in §11.

**(b) Ogni affermazione dichiara la propria fonte e la propria età.** «Ha rifiutato» non è mai da
solo: è «ha rifiutato, 4 minuti fa». HIRIS non indovina la salute di un provider, **riferisce cosa ha
osservato e quando**. È l'etica del prodotto applicata qui: il contrario di «Attivo», che è una
predizione travestita da stato.

**(c) Un concetto ha una parola sola.** Applico lo stesso principio del riordino della pagina add-on:
«in catena» è dove sei, «ha risposto / ha rifiutato / mai provato» è cosa hai fatto, «a consumo /
nel piano / gratuito / in casa» è cosa costi. Tre famiglie, nessuna sovrapposizione, e «Attivo»
sparisce perché confondeva la prima con la seconda.

---

## 3. La struttura della pagina

Cinque blocchi, in quest'ordine. L'ordine è quello di chi apre la pagina la prima volta e non sa
niente: prima **cosa succede**, poi **perché**, poi **cosa non stai usando**, poi **cosa ti manca**,
e in fondo la sola cosa che non è una decisione.

```
  Modelli
  Chi risponde alle tue domande, e in che ordine.

  +----------------------------------------------------------------+
  |  ADESSO                                                        |   <- non numerata:
  |  la frase, piu' al massimo due righe di diagnosi,              |      non e' una sezione,
  |  piu' al massimo un bottone di correzione                      |      e' la risposta
  +----------------------------------------------------------------+

  01  LA CATENA
      Le righe-provider in uso, in ordine. E' l'unica verita':
      un provider e' usato se e solo se sta qui.

  02  FUORI DALLA CATENA
      Chi potrebbe entrare (un gesto) e chi non puo' (manca la chiave).

  03  QUANDO NON DECIDE LA CATENA        <- CANCELLATO, vedi la nota qui sotto
      Il modello fissato nelle Impostazioni chat, se c'e'.
      Compare SOLO quando c'e'. (motivazione sotto)

      ----------------------------------------------------------------
      Embedding: nessun testo viene vettorizzato. [riga sola, in fondo]
```

> **Il blocco 03 è cancellato — i blocchi sono QUATTRO.** Il §13 di questo
> documento proponeva due strade per il modello della chat e raccomandava la
> **(a)**: il selettore esce da `#/impostazioni`. Il proprietario ha scelto la
> (a) il 13 agosto («la catena è l'unica verità»), e la fetta *modelli e
> catena* l'ha eseguita al **Task 4**: il campo `ImpostazioniChat.model` non
> esiste più, `handlers_chat` chiede sempre `"auto"`, e `PUT
> /api/impostazioni-chat` rifiuta la chiave con un 400 parlante. Il blocco 03
> esisteva **solo** per dichiarare che un modello fissato altrove scavalcava
> la catena: senza quel campo non c'è più niente da dichiarare, e disegnarlo
> significherebbe disegnare un avviso per uno stato irraggiungibile — cioè
> l'esatto contrario del principio di questa pagina. **Chi implementa i
> blocchi (Task 8-9) non lo disegna.** Tutto ciò che nel resto del documento è
> scritto al presente sul campo della chat (§0 punto 2, §0 punto 4, §5.1, §13)
> descrive il prodotto *prima* del Task 4 e va letto come diagnosi storica,
> non come stato di oggi.

**Perché quest'ordine.** Chi apre la pagina la prima volta ha una domanda sola e la pagina gliela
risponde prima di chiedergli di capire qualcosa. La catena viene subito dopo perché è la
giustificazione della frase — si legge dall'alto e si arriva al provider nominato nella frase. «Fuori
dalla catena» è terzo perché è il posto dove si guarda solo dopo aver capito cos'è dentro. Gli
embedding sono in fondo e non sono una sezione, perché non sono una decisione (§8).

**Perché non c'è più una sezione «Provider attivi» separata dalla catena.** Erano due
rappresentazioni della stessa cosa, e due rappresentazioni della stessa cosa possono divergere: è
esattamente il modo in cui la pagina ha mentito finora. Fuse in una, la divergenza è impossibile per
costruzione.

**Sul blocco 03 e la regola del brief** («un campo che compare solo in certi stati è comodo per il
caso normale e crudele per chi non capisce perché è sparito»). Qui il campo condizionale è
giustificato e vale la pena dire perché, perché è l'unico della pagina: **non è un controllo che
sparisce, è un avviso che compare**. Quando il modello della chat è `"auto"` — il caso normale — non
c'è niente da dire e non c'è niente da cercare; nessuno può chiedersi «dov'è finito» qualcosa che
non ha mai visto. Quando invece è fissato, il blocco compare per dichiarare che **la catena qui
sopra non viene consultata**, cioè per smentire il resto della pagina. Un avviso che compare quando
c'è qualcosa di cui avvisare non è progressive disclosure: è la pagina che smette di mentire. Se
invece il blocco fosse un *controllo* (una tendina di modelli che appare e sparisce), la regola del
brief varrebbe in pieno e sarebbe sbagliato: perciò nel blocco 03 c'è un solo collegamento a
`#/impostazioni` e nessun controllo.

---

## 4. L'anatomia di una riga-provider

Una riga è una frase su quattro colonne, e ogni colonna risponde a una domanda diversa:

```
  N  o  NOME                   MODELLO           natura      [azioni]
        stato osservato, con quando
```

```
  1  o  Claude API             claude-opus-4-7 v   a consumo   ^ v  (x)
        x ha rifiutato le ultime 40 richieste - credito esaurito (400), 3 min fa
 - - - - se non risponde (circa 1 s) - - - - - - - - - - - - - - - - - - - - - -
  2  o  OpenRouter    anthropic/claude-sonnet-4-6 v  a consumo  ^ v  (x)
        v ha risposto 3 min fa
 - - - - ultimo della catena: se non risponde, la chat da' errore - - - - - - - -
```

### 4.1 Cosa mostra

| Colonna | Contenuto | Perché |
|---|---|---|
| **Posizione** | `1`, `2`, `3`… in `--font-mono` | È il dato della riga, non un ornamento: la posizione *è* la decisione. `.chain-num` esiste già. |
| **Pallino** | verde / ambra / grigio / vuoto | Mai unico segnale: sempre accompagnato dal testo di stato sotto (WCAG 1.4.1, regola già adottata nel contratto precedente). |
| **Nome** | «Claude API», «OpenRouter», «Piano Claude Max», «Ollama (in casa)» | Un nome per provider, mai due (oggi coesistono «Abbonamento (Claude Max)», «Abbonamento Claude (subscription)», «Piano Claude Max»: tre nomi per una cosa, uno per ogni file). |
| **Modello** | l'identificatore in uso, cliccabile | §6. In `--font-mono` se è un identificatore, in tondo se è un alias. |
| **Natura** | `a consumo` / `nel piano` / `gratuito` / `in casa` | Quattro categorie, non un prezzo (§12). È l'unica cosa che serve per decidere l'ordine. |
| **Azioni** | `^` `v` per l'ordine, `(x)` per uscire dalla catena | Un gesto per uscire, un gesto per rientrare (§4.4). |
| **Riga di stato** | l'ultimo esito osservato + quando | §4.3. |
| **Connettore** | «se non risponde (circa 1 s)» fra una riga e la successiva | §5. |

### 4.2 Cosa si può toccare

Tutto ciò che è una decisione: la posizione, il modello, l'appartenenza alla catena. **Non** la
credenziale — quella sta nella pagina dell'add-on e la riga non finge di poterla cambiare: quando
manca, la riga non è nemmeno qui (è in «Fuori dalla catena», §2 del layout, con il collegamento).

### 4.3 Come si vede che non può rispondere

Questa è la parte che chiude il caso del proprietario, e richiede al backend un dato che oggi non
esiste (§11.2). Quattro stati, ognuno un fatto osservato, mai una previsione:

| Stato | Testo | Quando |
|---|---|---|
| ha risposto | `v ha risposto 3 min fa` | ultimo esito = successo |
| ha rifiutato | `x ha rifiutato le ultime 40 richieste - credito esaurito (400), 3 min fa` | ultimo esito = errore, con la causa in parole e il codice fra parentesi |
| irraggiungibile | `x non risponde all'indirizzo - ultimo tentativo 2 h fa`<br>`x circuito aperto, riprova fra 42 s` | errore di connessione (Ollama spento, host sbagliato); il secondo quando l'interruttore di protezione è scattato |
| non puo' rispondere | `x il ponte e' acceso ma manca il token: ogni messaggio scadra' dopo 5 min` | vedi sotto |
| mai provato | posizione 1: `- non l'hai ancora usato`<br>posizione 2+: `- non e' mai servito ripiegare qui` | nessuna osservazione |

**Il quarto stato non è ipotetico ed è già rilevabile con i dati di oggi.**
`_ponte_attivo` (`server.py:66-91`) è `BRIDGE_ENABLED or _sub_first_class`, ma il worker che risponde
parte solo se `(PROVIDER_SUBSCRIPTION or BRIDGE_ENABLED) and token` (`server.py:443-459`). Quindi
**ponte acceso senza token è uno stato raggiungibile in cui ogni messaggio viene accodato e scade
dopo cinque minuti**, e l'unica traccia è un `bashio::log.warning` all'avvio (`run.sh:147`) che
nessuno legge. La pagina ha già tutto il necessario per dirlo: `ponte_attivo` e `has_credential` sono
entrambi nel payload di oggi. È il rilievo con il miglior rapporto fra costo e danno evitato di
tutto il progetto.

**Uno stato di guasto esiste già, per tre provider su cinque, e nessuno lo espone.**
`OpenAICompatRunner` tiene `_conn_fail_count` e `_circuit_open_until`
(`backends/openai_compat_runner.py:259-260`, soglia 3, raffreddamento 60 s a `:28-29`): dopo tre
errori di connessione consecutivi il provider viene saltato senza nemmeno provarci, per un minuto.
Vale per OpenAI, OpenRouter e Ollama — non per Claude, che non ha nessuna protezione e viene
ritentato da zero a ogni turno. È in memoria, per istanza, **e nessuna rotta lo restituisce**: la
pagina non può dire «lo sto saltando» di un provider che il prodotto sta effettivamente saltando.
Esporlo è la metà meno costosa di §11.2.

Due dettagli che valgono quanto la tabella.

**Il conteggio, non solo l'ultima volta.** «Ha rifiutato **le ultime 40 richieste**» dice una cosa
che «ha rifiutato 3 minuti fa» non dice: che non è un incidente, è lo stato. Nel caso del
proprietario è la differenza fra «ah, un errore» e «ah, sto buttando via una chiamata a messaggio da
settimane».

**«Mai provato» cambia significato con la posizione, e la copia lo segue.** In prima posizione è
allarmante; in seconda è la notizia buona (il ripiego non è mai servito). Stesso fatto, due frasi,
una regola sola.

**Cosa succede visivamente.** Non una riga rossa: **il pallino diventa grigio-ambra e il nome
perde peso** (`--text-2` invece di `--text`), così una riga che non risponde *smette di sembrare
attiva* — è la traduzione grafica del ritiro della parola «Attivo». Il testo di stato è in
`--err-ink` / `--warn-ink`, **mai** in `--err` / `--warn`: la regola d'uso è scritta in
`hiris-theme.css:76-79` e la pagina Modelli è, secondo l'audit pre-UAT, l'unica superficie i cui
punti d'uso non sono stati riportati sui token `*-ink`. Va fatto qui.

### 4.4 Il gesto che accende, e quello che spegne

Il difetto 1 del brief («accendere costa due gesti, spegnere uno; l'interruttore fa due mestieri
opposti») si chiude togliendo l'interruttore.

**Un provider è usato se e solo se sta nella catena.** Entrare: un gesto (`Usa`, dalla lista «Fuori
dalla catena»). Uscire: un gesto (`(x)`). Simmetrico, e soprattutto **c'è una sola
rappresentazione dello stato**, quindi non esiste più uno stato in cui l'interruttore dice una cosa
e la catena un'altra.

Questo chiude anche il difetto 3, e lo chiude per costruzione invece che per disciplina. Oggi
`model_activation.py:22` esiste perché *«tutti gli interruttori spenti»* è uno stato ambiguo — vuol
dire sia «non ho ancora deciso» sia «non voglio nessuno» — e qualcuno ha dovuto scegliere cosa
significasse. Con la catena come unica verità l'ambiguità non c'è: **catena vuota significa una cosa
sola, «HIRIS non può rispondere», e la pagina lo dice** invece di riaccendere di nascosto tutto
quello che ha una credenziale.

**La proprietà buona di `reconcile_chain` va conservata, e cambia forma.** Oggi un ordine salvato
quando erano attivi meno provider non deve nascondere quelli diventati attivi dopo, e la funzione li
accoda (`model_activation.py:70-73`). Con questo progetto la regola diventa: **un provider che
diventa credenziato non entra in catena da solo, e non sparisce: compare in «Fuori dalla catena»,
visibile, a un gesto di distanza.** Non si perde niente (nessuno resta escluso dal ripiego senza
saperlo, che era il rischio che la funzione copriva) e si guadagna che **niente entra nella catena
senza che qualcuno l'abbia messo** — che era l'altro difetto, quello che `reconcile_chain` creava
mentre ne risolveva uno.

---

## 5. Come si esprime la catena, e come ci entra l'abbonamento

### 5.1 La catena si legge come una frase perché il costo del passaggio sta fra le righe

Un elenco numerato dice l'ordine. Non dice la cosa che serve davvero per scegliere l'ordine:
**quanto costa passare oltre**. E i costi qui non sono paragonabili — differiscono di due ordini di
grandezza:

```
  1  o  Claude API              claude-opus-4-7 v      a consumo   ^ v (x)
        x credito esaurito (400) - ultime 40 richieste, da 3 min fa
 - - - - se non risponde (circa 1 s) - - - - - - - - - - - - - - - - - - - -
  2  o  Piano Claude Max        sonnet v               nel piano   ^ v (x)
        v ha risposto 12 min fa - 7 di 50 messaggi oggi
 - - - - se non risponde entro 5 min [cambia] - - - - - - - - - - - - - - - -
  3  o  Ollama (in casa)        llama3.1:8b            in casa     ^ v (x)
        - non e' mai servito ripiegare qui
 - - - - ultimo della catena: se non risponde, la chat da' errore - - - - - -
```

Il connettore è la frase. `1 -> se non risponde (circa 1 s) -> 2 -> se non risponde entro 5 min -> 3`
si legge di seguito e **dice che mettere il ponte al primo posto costa cinque minuti di attesa
prima di ogni ripiego**, che è l'informazione che decide l'ordine e che nessun elenco numerato
poteva dare.

Costa due righe di altezza in più su cinque provider. Le vale: sono le uniche due righe della pagina
che spiegano *perché* un ordine è meglio di un altro.

**Ma il numero dev'essere onesto, e non tutti lo sono allo stesso modo.** Tre casi diversi, e il
connettore deve dire cosa sa e non di più:

- **Un tempo configurato** (ponte 5 min, Ollama 120 s): è un numero vero, cliccabile, ed è una
  decisione. Il connettore lo mostra.
- **Un rifiuto immediato** (400 credito, 401 chiave): il ripiego è nell'ordine del secondo. Il
  connettore dice `se rifiuta, subito` e non promette una cifra.
- **Un tempo che non si può configurare e non è breve**: su Claude un 429 viene ritentato tre volte
  con pause di 5, 15 e 45 secondi (`claude_runner.py:318-319, 997-1008`) **prima** di cedere alla
  catena. Sono più di sessanta secondi che nessuno ha chiesto e che nessuna pagina dice. Il
  connettore non può inventarli, ma la riga di stato sì, quando succede: `x troppe richieste - ha
  ceduto dopo 65 s`. Serve che l'esito registrato (§11.2) porti anche quanto è durato il fallimento,
  non solo che c'è stato.

La regola generale: **il connettore mostra un numero solo quando quel numero è una decisione di
qualcuno.** Negli altri casi dice cosa succede a parole, e il tempo reale lo racconta la riga di
stato dopo che è successo.

### 5.2 L'abbonamento: cosa la pagina disegna oggi, e cosa disegna quando il backend saprà farlo

Qui il progetto deve essere spietato, perché è il punto in cui una pagina bella diventa una bugia.

**Oggi il ponte non è un anello: è un bivio, e disegnarlo come anello sarebbe il difetto 3 che
riapre.** Quando il ponte è acceso, `handlers_chat.py:408` dirotta *tutto* e la catena non viene
consultata mai; se il job scade o il tetto è pieno, non c'è ripiego, la chat dà errore. Quindi
finché il backend è questo, la pagina disegna **un bivio**, e lo disegna in modo che si capisca al
primo sguardo che la catena è spenta:

```
  01  LA CATENA

      +--------------------------------------------------------------+
      | o  Piano Claude Max      sonnet v          nel piano  [ Spegni ] |
      |    v ha risposto 12 min fa - 7 di 50 messaggi oggi              |
      |    scade dopo 5 min [cambia] - poi il messaggio va perso        |
      +--------------------------------------------------------------+
             |
             |  il ponte e' acceso: tutto passa di qui,
             |  e quello che segue non viene consultato.
             v
      . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
      . 1  Claude API      claude-opus-4-7    a consumo   ^ v (x)     .   <- tutta la
      . 2  OpenRouter      claude-sonnet-4-6  a consumo   ^ v (x)     .      catena in
      . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      --text-3,
                                                                              non tolta
```

La catena resta **visibile e riordinabile** anche mentre è scavalcata (nascondere ciò che conta è
proibito dal brief, e serve poterla preparare per quando il ponte si spegne), ma è disegnata come
ciò che è: inerte, adesso.

Questo disegno, da solo, **chiude una domanda aperta del prodotto**:
`docs/design/2026-08-10-parita-ponte-chat.md` §7 e domanda aperta 6 dicono che
`provider_subscription` implica il ponte senza dirlo, che è «un difetto vero» da chiudere
«rendendolo visibile all'utente, che è un lavoro di configurazione e di interfaccia». Questo è quel
lavoro. Oggi la risposta a «quale strada sto usando» sta sulla pagina Consumi e in una frase
dell'indicatore d'attesa dopo due minuti (`docs/prova-la-2.0.md:123-133`) — cioè ovunque tranne che
nella pagina che si chiama Modelli.

**Quando il backend saprà ripiegare, il bivio diventa un anello, e la pagina non cambia forma: cambia
dato.** Questo è il punto (§11.1): la topologia non è scritta nella pagina, è chiesta al backend. Il
giorno in cui il ponte ripiega, il backend risponde «il ponte è la posizione 1 di una catena di 3» e
la pagina disegna tre righe con un connettore da cinque minuti fra la prima e la seconda. Nessuna
riga di frontend da cambiare, e — più importante — **nessun momento in cui la pagina disegna un
ripiego che non c'è.**

### 5.3 Perché `llm_strategy` esce dalla pagina come modo, e resta come scorciatoia

Il brief la mette fra le cose da spostare. Sposterei invece la *funzione*, non il *controllo*.

`llm_strategy` e `chain_order` sono **due controlli per un solo esito**, e il prodotto ha già dovuto
scrivere un arbitro (`reconcile_chain`) e poi spiegare chi vince nelle descrizioni delle opzioni. La
sovrapposizione è già stata nominata e rinviata: `config-addon-report.md` §7.6 la chiama «una
sovrapposizione di responsabilità fra le due superfici» e dice «riprogettarla sarebbe una fetta a
sé». Questa è quella fetta.

**Proposta: le tre strategie restano, come tre modi di *rifare* la catena, non come uno stato.**

```
      Rifai la catena:  [ Bilanciato ]  [ Risparmio ]  [ Qualita' massima ]
```

I tre ordini, per esteso (`llm_router.py:44-55`), perché nella pagina non entrano e chi implementa
deve averli sotto mano: **Bilanciato** = claude, openrouter, openai, ollama; **Risparmio** = ollama,
openrouter, openai, claude; **Qualità massima** = claude, openai, openrouter, ollama. Nessuno dei tre
nomina l'abbonamento, ed è coerente con §5.2: oggi non è un anello.

Un gesto, effetto immediato e visibile (le righe si riordinano), e da quel momento **la verità è di
nuovo una sola: la catena**. Nessun «preset corrente» da mostrare, nessuna regola di precedenza da
spiegare, nessun arbitro da mantenere. Chi vuole l'ordine consigliato lo ottiene con un click; chi
lo vuole suo lo trascina e nessuno glielo riscrive all'avvio.

Ricaduta: `llm_strategy` come opzione persistente può uscire, e `reconcile_chain` si riduce a
«filtra ai provider ancora credenziati». Va detto nella fetta, non qui, ma il progetto lo assume.

---

## 6. Il modello di ogni provider

### 6.1 La riga porta il modello, per tutti e cinque

È il buco che l'aggiunta del proprietario ha aperto, ed è giusto: una riga che dice «OpenRouter,
primo in catena» non risponde a «con che cosa». Il modello sta nella riga, sempre visibile, mai
dentro un pannello da aprire per sapere cosa c'è.

Il modello è **cliccabile**, e apre un pannello. Non è una `<select>` inline: §6.3.

### 6.2 Alias e identificatori sono cose diverse, e lo dice la tipografia

Il proprietario chiede che la differenza di natura si capisca «senza spiegoni». La porta il carattere:

```
  1  o  Claude API          claude-opus-4-7           <- --font-mono: e' un identificatore,
                                                          punta a una cosa fissa
  2  o  Piano Claude Max    opus                      <- tondo, minuscolo: e' un alias,
                                                          segue il modello corrente del piano
```

Un identificatore ha l'aspetto di un identificatore (mono, trattini, numeri di versione); un alias ha
l'aspetto di una parola. La distinzione si legge prima di essere spiegata, e la spiegazione — una
riga sola — vive nel pannello, non nella riga.

E l'onestà richiede una cosa in più, che oggi non c'è da nessuna parte: **il pannello
dell'abbonamento offre tre voci e non di più**, perché `modello_cli` (`agent/runner.py:554-560`)
riduce tutto a `opus`/`haiku`/`sonnet` per sottostringa. Offrire `claude-opus-4-7` sull'abbonamento
sarebbe una precisione finta.

### 6.3 Il problema dei duecento: il pannello non è un catalogo, è un filtro

Il vincolo: OpenRouter espone 200+ modelli, e `_fetch_openrouter_models`
(`handlers_models.py:~330`) ne restituisce già una lista filtrata alla capacità *tools*. Una tendina
con duecento voci dentro una riga distruggerebbe la leggibilità che tutto il resto costruisce.

La forma che propongo — e la ragione per cui non è né un catalogo né una procedura guidata:

```
  +-- Modello di OpenRouter --------------------------------------- (x) --+
  |                                                                        |
  |  [ filtra, o incolla un identificatore...                            ] |
  |                                                                        |
  |  IN USO                                                                |
  |   (*) anthropic/claude-sonnet-4-6                                      |
  |                                                                        |
  |  SCELTI DA NOI                                                         |
  |   ( ) anthropic/claude-opus-4-7                                        |
  |   ( ) openai/gpt-4.1                                                   |
  |   ( ) google/gemini-2.5-flash                                          |
  |   ( ) mistralai/mistral-large                                          |
  |   -- gratuiti ------------------------------------------------------   |
  |   ( ) meta-llama/llama-3.3-70b-instruct:free                           |
  |   ( ) google/gemma-3-27b-it:free                                       |
  |   ( ) deepseek/deepseek-chat:free                                      |
  |                                                                        |
  |  [ ] nascondi i gratuiti              Mostra tutti (183) v             |
  |                                                                        |
  |  Solo modelli che sanno usare gli strumenti: HIRIS manda sempre il     |
  |  catalogo, e gli altri rifiuterebbero ogni richiesta.                  |
  +------------------------------------------------------------------------+
```

Quattro decisioni, ognuna con la sua ragione:

1. **La curatela esiste già.** `_OPENROUTER_PRESETS` (`handlers_models.py:~300`) sono undici voci
   scelte a mano, con i gratuiti separati dai paganti. Non serve inventare una curatela: serve
   *mostrarla* invece di annegarla in un elenco piatto. Le undici sono lo stato d'apertura.
2. **Il campo in cima è un filtro E un campo di testo.** Digitando si filtra la lista vera;
   incollando un identificatore che la lista non contiene, lo si salva comunque — il backend accetta
   qualunque stringa `openrouter:vendor/modello`, e `impostazioni-route.js:112-127` usa già questo
   stesso ripiego con la stessa motivazione dichiarata. Nessuna capacità persa, nessun catalogo
   aperto per difetto.
3. **`hide_free_models` vive qui, come casella sulla lista che filtra.** Smette di essere
   un'impostazione globale e diventa un controllo sull'unica cosa su cui agisce. Si auto-documenta:
   non serve una descrizione per capire cosa fa una casella che sta sotto l'elenco che modifica.
4. **«Mostra tutti (183)» dichiara il numero prima di aprirlo.** Chi vuole il catalogo lo ha; chi non
   lo vuole non lo incontra mai; e nessuno ci finisce dentro per sbaglio, perché il numero è la
   deterrenza.

Per gli altri provider lo stesso pannello, senza le parti che non servono: Claude ha quattro voci
(`_CLAUDE_MODELS`), OpenAI una ventina, l'abbonamento tre e nessun campo di filtro.

**Un quinto punto, che non avevo previsto e che il codice mi ha imposto: l'elenco deve dichiarare da
dove viene.** `_fetch_openai_models` e `_fetch_openrouter_models` (`handlers_models.py:235-253`,
`:322-377`) hanno cinque secondi di pazienza e, se falliscono, restituiscono **una lista scritta a
mano nel sorgente** con un `logger.warning` e niente altro. Peggio: un provider con una chiave
sbagliata compare lo stesso nell'elenco dei provider, perché la condizione è la *presenza* della
chiave, non la sua validità (`:421`, `:430`, `:440`, `:451`). Quindi oggi si può stare davanti a un
elenco di modelli che sembra vero, che viene da una costante di due anni fa, per un provider che non
risponderebbe comunque. Il pannello deve portare una riga di provenienza, sempre, come già previsto
per Ollama in §10.2:

```
   Letti da openrouter.ai adesso                      <- lista viva
   Elenco di riserva: non ho potuto leggere openrouter.ai
   (chiave rifiutata? rete?). Quello che vedi qui potrebbe non esistere piu'.
```

E `hide_free_models` ha un difetto gemello da dichiarare nello stesso posto: quando la lettura
fallisce, il ripiego restituisce i preset **non filtrati** (`handlers_models.py:375-377`), quindi i
gratuiti ricompaiono anche con la casella spuntata. Con la riga di provenienza a schermo, questo
smette di essere un mistero e diventa una conseguenza leggibile.

### 6.4 Dove finisce la scelta quando il provider è fuori dalla catena

La domanda del brief («sparisce, resta grigia, resta modificabile?»). **Resta visibile e resta
modificabile.**

```
  02  FUORI DALLA CATENA

   o  Piano Claude Max      opus v            token presente     [ Usa ]
      Lo paghi e non lo stai usando.
   o  OpenAI                gpt-4.1 v         manca la chiave    [ Configurazione add-on -> ]
   o  Ollama (in casa)      -                 manca l'indirizzo  [ Configurazione add-on -> ]
```

Tre ragioni per non renderla grigia né farla sparire. **(a)** Il valore è salvato comunque: renderlo
non modificabile significherebbe che l'unico modo di cambiarlo è mettere il provider in catena,
cioè costringere a un cambiamento reale per fare una preparazione. **(b)** Preparare un provider
prima di usarlo è un uso legittimo e frequente — scegliere il modello e *poi* metterlo primo è un
ordine di gesti sensato. **(c)** La regola del brief: un valore che sparisce è crudele. Un valore
che resta e non ha effetto **adesso** è onesto, purché la riga dica che non ce l'ha — e lo dice, per
il solo fatto di stare sotto l'intestazione «Fuori dalla catena».

L'unica eccezione è il provider senza credenziale: lì il selettore mostra il valore salvato ma non
si può aprire, perché la lista dei modelli viene dal provider stesso e senza chiave non c'è lista.
La riga lo dice in tre parole («manca la chiave»), che sono anche il collegamento.

### 6.5 Quando il modello scelto non è più disponibile

Il brief chiede di guardarlo e di dire com'è. **È peggio di quanto immaginavo, e non lo può
riparare questa pagina.** Ecco cosa succede oggi, verificato:

- Un modello ritirato produce un 404 dal provider. `claude_runner.py:830-834` e
  `openai_compat_runner.py:657-662` lo catturano **insieme a tutto il resto** e sollevano
  `RunnerBackendError("Errore temporaneo del servizio AI. Riprova tra poco.")`. Il nome del modello
  non compare, la causa nemmeno.
- `_is_conn_error` (`openai_compat_runner.py:35-44`) restituisce falso per un 404, quindi
  **l'interruttore di protezione non scatta**: il modello morto viene richiesto a ogni turno, per
  sempre, e l'unica traccia è una riga di `logger.error`.
- Con il modello della chat a `"auto"`, `llm_router.py:175` passa al provider successivo e
  **l'utente non vede niente**: un altro provider risponde al posto suo, in silenzio.
- Con un modello fissato, nessun ripiego: l'utente legge «Errore temporaneo del servizio AI», che
  non nomina né il modello né la causa — **e quella frase finisce in cronologia**, perché non è fra
  i `_TOXIC_ASSISTANT_PREFIXES` (`chat_store.py:56-64`), quindi il turno successivo la rilegge come
  contesto.

**Non è materiale per questo progetto: è materiale per la fetta, e lo segnalo come tale.** La pagina
può però fare la sua parte, e la fa con lo stesso meccanismo di §4.3: se l'ultimo esito osservato di
un provider è un 404 su un modello, la riga lo dice con le parole giuste — `x il modello
anthropic/qualcosa non esiste piu' (404), 3 min fa` — invece di un «errore temporaneo» che
temporaneo non è. Serve che il backend distingua i 404-di-modello dagli altri errori quando registra
l'esito (§11.2).

---

## 7. Dove finiscono le impostazioni di dettaglio

Regola: **un'impostazione appartiene al provider che governa, e vive nella sua riga — espansa, non
nascosta.** Niente sezione «Avanzate» a fondo pagina: sarebbe un secondo posto dove cercare la stessa
cosa.

| Impostazione | Dove va | Forma |
|---|---|---|
| `ponte.bridge_deadline_min` | connettore sotto la riga del Piano Claude Max | «se non risponde entro **5 min**» — il numero *è* il testo del connettore, cliccabile |
| `local_model.request_timeout` | connettore sotto la riga di Ollama | «se non risponde entro **120 s**» — stesso slot, stessa forma |
| `ponte.chat_daily_cap` | riga di stato del Piano Claude Max | «7 di **50** messaggi oggi» — un tetto senza il suo contatore è un numero su cui non si può ragionare, e HIRIS il contatore ce l'ha (`reasoning_queue.count_chat_today()`) |
| `hide_free_models` | pannello modello di OpenRouter | casella sotto l'elenco che filtra (§6.3) |
| `local_model.model` | pannello modello di Ollama | smette di essere un campo di testo nella pagina add-on e diventa una scelta fra i modelli davvero scaricati (`/api/tags` è già interrogato, `handlers_models.py:_fetch_ollama_models`) |
| `llm_strategy` | tre bottoni sopra la catena | §5.3: scorciatoia, non modo |
| `provider_*` (i cinque) | **nessuna**: sono la catena | §4.4 |

Due simmetrie che il progetto guadagna gratis, e che sono la ragione per cui le prime due righe
della tabella finiscono nello stesso posto:

- **Ogni passo della catena dichiara quanto ci mette a rinunciare**, e per due provider su cinque
  quel tempo è una decisione. Ha smesso di essere «un'impostazione avanzata del ponte» ed è diventata
  «quanto aspetti prima di passare oltre» — che è la stessa cosa detta dove serve.
- **Il numero è il testo.** Non c'è un'etichetta «Scadenza (minuti)» con accanto un campo: c'è una
  frase in cui il numero è cliccabile. Densità alta, zero paternalismo, e il senso non si può perdere
  perché il senso è la frase intorno.

**Due conseguenze da non dimenticare in fase di fetta.**

`_prov_creds["ollama"] = bool(local_model_url and local_model_name)` (`server.py:1006`): oggi il
*nome del modello* fa parte del test di credenziale. Spostando il modello in questa pagina, la
credenziale di Ollama diventa il solo indirizzo — che è anche più corretto (l'indirizzo è ciò che si
custodisce, il modello è ciò che si decide), ma cambia il comportamento di un install esistente con
URL presente e modello vuoto.

**La scadenza del ponte ha un tetto che nessuno ha messo lì apposta.** Lo schema ammette
`int(1,120)` minuti (`config.yaml:292`), ma il frontend della chat smette di aspettare a
`CHAT_POLL_MAX_MS = 5 * 60 * 1000` (`static/chat/send.js:27`) — una costante indipendente e non
collegata. Impostare 10 minuti produce uno stato in cui il browser dichiara scaduta un'attesa che
sul server è ancora viva (la risposta poi arriva e finisce in cronologia, e `send.js:76-82` lo
gestisce con garbo, ma non è quello che l'utente ha chiesto). Quindi: o il campo del connettore si
ferma a 5, o i due numeri diventano uno. Non va lasciato com'è, perché questa pagina, mettendo quel
numero davanti a tutti, lo trasformerebbe da opzione dimenticata a cosa che la gente tocca.

---

## 8. Gli embedding inerti: dichiararli, non arredarli

Il brief li mette fra le cose da spostare. **Sposterei la dichiarazione e non i controlli**, e
argomento, perché è una delle due deviazioni dalla lista.

Tre opzioni possibili:

- **Mostrarli come sezione con i due campi.** Dà a un binario dichiaratamente morto lo stesso peso
  visivo dell'unica cosa per cui la pagina esiste, e invita a modificare due valori che non fanno
  niente. È quello che la pagina fa oggi, con una `section-card` numerata `03`.
- **Nasconderli.** Contro l'etica dichiarata del prodotto e contro la regola del brief.
- **Dichiararli e basta.** Una riga, in fondo, sotto un filetto, in `--text-3`:

  > Embedding: nessun testo viene vettorizzato, e i due campi in Configurazione add-on non hanno
  > effetto. La ricerca per somiglianza è rimandata, non annullata.

Scelgo la terza, e il motivo che la rende non solo più pulita ma **meno rischiosa** è tecnico:
spostare i due campi qui significherebbe toglierli da `config.yaml`, e il Supervisor scarta in
silenzio le chiavi fuori schema — chi aggiorna **perde il valore salvato**, senza migrazione
possibile. Pagare una perdita di dato per un campo che non fa niente è il peggior rapporto
costo/beneficio della lista. I due campi restano dove sono, a costo zero; la pagina Modelli dice che
sono inerti, che è la sola cosa che qualcuno debba sapere.

Nota di coerenza: la riga non è dentro nessuna sezione numerata proprio perché **non è una
decisione**, e la numerazione in questa pagina significa «qui si decide qualcosa».

---

## 9. I tre stati che contano

### 9.1 Nessun provider configurato

```
  Modelli
  Chi risponde alle tue domande, e in che ordine.

  +--------------------------------------------------------------------+
  |                                                                    |
  |   HIRIS non puo' ancora rispondere.                                |
  |                                                                    |
  |   Non c'e' nessuna credenziale: non c'e' niente da mettere in       |
  |   catena. Le chiavi stanno in Configurazione add-on perche' e'      |
  |   l'unico posto che sa custodirle; tutto il resto si decide qui.    |
  |                                                                    |
  |   [ Apri Configurazione add-on -> ]                                |
  |                                                                    |
  +--------------------------------------------------------------------+

  01  LA CATENA
      Vuota.

  02  FUORI DALLA CATENA
   o  Piano Claude Max     -    manca il token      [ Configurazione add-on -> ]
   o  Claude API           -    manca la chiave     [ Configurazione add-on -> ]
   o  OpenRouter           -    manca la chiave     [ Configurazione add-on -> ]
   o  OpenAI               -    manca la chiave     [ Configurazione add-on -> ]
   o  Ollama (in casa)     -    manca l'indirizzo   [ Configurazione add-on -> ]
```

La catena vuota **si mostra vuota**, non si nasconde: chi arriva qui capisce in due righe che la
catena è la cosa che conta e che è vuota. E la frase spiega il confine fra le due pagine una volta
sola, dove serve — non in un riquadro informativo permanente come oggi (`models-route.js:337-344`).

### 9.2 Tutto a posto

```
  +--------------------------------------------------------------------+
  |   Il prossimo messaggio va al Piano Claude Max, con opus.           |
  |   Nel piano: nessun costo a consumo, fino a 50 messaggi al giorno.   |
  +--------------------------------------------------------------------+

  01  LA CATENA               Rifai: [Bilanciato] [Risparmio] [Qualita' massima]

   1  o  Piano Claude Max      opus v              nel piano    ^ v (x)
         v ha risposto 4 min fa - 7 di 50 messaggi oggi
  - - - - se non risponde entro 5 min - - - - - - - - - - - - - - - - - - - -
   2  o  OpenRouter    anthropic/claude-sonnet-4-6 v  a consumo  ^ v (x)
         - non e' mai servito ripiegare qui
  - - - - ultimo della catena: se non risponde, la chat da' errore - - - - - -

  02  FUORI DALLA CATENA
   o  Claude API     claude-opus-4-7 v   chiave presente   [ Usa ]
   o  OpenAI         -                   manca la chiave   [ Configurazione add-on -> ]
   o  Ollama         -                   manca l'indirizzo [ Configurazione add-on -> ]

  ------------------------------------------------------------------------
  Embedding: nessun testo viene vettorizzato.
```

Nota: **niente verde trionfale, nessun «tutto ok».** Lo stato buono è quello in cui la pagina è
noiosa. L'unica cosa che la distingue è che il riquadro in cima non ha righe di diagnosi sotto la
frase.

### 9.3 Un provider che era attivo e ha smesso di funzionare — il caso vero

```
  +--------------------------------------------------------------------+
  |                                                                    |
  |   Il prossimo messaggio va a OpenRouter,                           |
  |   con anthropic/claude-sonnet-4-6, a consumo.                       |
  |                                                                    |
  |   x  Claude API e' primo in catena e ha rifiutato le ultime 40      |
  |      richieste: credito esaurito. Ogni messaggio ci prova prima.    |
  |                                                                    |
  |   !  Il Piano Claude Max ha il token, lo paghi, ed e' fuori         |
  |      dalla catena.                             [ Mettilo primo ]   |
  |                                                                    |
  +--------------------------------------------------------------------+

  01  LA CATENA               Rifai: [Bilanciato] [Risparmio] [Qualita' massima]

   1  o  Claude API           claude-opus-4-7 v      a consumo   ^ v (x)
         x credito esaurito (400) - ultime 40 richieste, l'ultima 3 min fa
  - - - - se non risponde (circa 1 s) - - - - - - - - - - - - - - - - - - - -
   2  o  OpenRouter   anthropic/claude-sonnet-4-6 v  a consumo   ^ v (x)
         v ha risposto 3 min fa
  - - - - ultimo della catena: se non risponde, la chat da' errore - - - - - -

  02  FUORI DALLA CATENA
   o  Piano Claude Max   opus v      token presente      [ Usa ]
      Lo paghi e non lo stai usando.
   o  OpenAI             -           manca la chiave     [ Configurazione add-on -> ]
   o  Ollama (in casa)   -           manca l'indirizzo   [ Configurazione add-on -> ]
```

**Il metro del brief, verificato.** «Leggibile a colpo d'occhio»: le prime tre righe della pagina lo
dicono, senza che si debba mettere in relazione niente. «Correggibile in pochi gesti»: due — `Mettilo
primo` sul piano, `(x)` su Claude API. Zero conferme, zero procedure guidate.

**Perché il bottone sta sul piano e non su Claude API.** Le due diagnosi sono ordinate per **quanto
costano**, non per gravità tecnica: un abbonamento pagato e non usato costa soldi ogni mese, un
provider che fallisce costa un secondo di latenza a messaggio. Il bottone sta sulla prima. Regola
generale: **una sola azione consigliata, sulla riga che costa di più**; l'altra resta a portata,
nella catena.

---

## 10. Mockup: i pannelli

### 10.1 Pannello modello dell'abbonamento

```
  +-- Modello del Piano Claude Max ------------------------------- (x) --+
  |                                                                      |
  |   ( ) haiku      il piu' rapido                                      |
  |   (*) sonnet     l'equilibrato                                       |
  |   ( ) opus       il piu' capace                                      |
  |                                                                      |
  |   Sono alias, non nomi di modello: seguono il modello corrente del    |
  |   piano invece di puntare a una versione fissa. Non c'e' un           |
  |   identificatore da scegliere, e non ce ne saranno di piu' di tre.    |
  |                                                                      |
  +----------------------------------------------------------------------+
```

Tre voci, nessun campo di filtro, nessun carattere monospaziato: **la forma del pannello è già la
spiegazione**, e la frase sotto serve solo a chi si chiede perché sia così povero.

### 10.2 Pannello modello di Ollama

```
  +-- Modello di Ollama ------------------------------------------ (x) --+
  |                                                                      |
  |   Scaricati su 192.168.1.42:11434 -- letti adesso                    |
  |   (*) llama3.1:8b                                                    |
  |   ( ) qwen2.5:14b                                                    |
  |   ( ) mistral-nemo:12b                                               |
  |                                                                      |
  |   Se non risponde entro [ 120 ] secondi, HIRIS passa al prossimo      |
  |   della catena.                                                       |
  |                                                                      |
  +----------------------------------------------------------------------+
```

La lista viene da `/api/tags`, che il prodotto già interroga. «letti adesso» è la data della fonte:
la stessa disciplina di §4.3 applicata a un elenco invece che a uno stato.

### 10.3 Il connettore quando si cambia il tempo

```
  - - - - se non risponde entro [ 5 ] min - - - - - - - - - - - - - - - -
```

Il numero diventa un campo al click, si conferma con Invio o uscendo dal campo. Nessun bottone
Salva, nessun dialogo: coerente con la disciplina di scrittura ottimistica già adottata da questa
pagina.

---

## 11. Cosa il backend deve dare, e che oggi non dà

Il progetto non è realizzabile con le API di oggi. Tre cose, in ordine di quanto sono
indispensabili.

### 11.1 La topologia effettiva, calcolata dal runtime — non i suoi ingredienti

**È l'idea portante del progetto, e la risposta strutturale al difetto 3.**

Oggi la pagina riceve gli *ingredienti* (`providers[]` con `active`/`has_credential`/`toggle`,
`llm_strategy`, `chain_order`) e ricostruisce da sola l'esito, con `buildDisplayChain`
(`models-route.js:378-382`) che riproduce a mano la logica di `reconcile_chain`
(`model_activation.py:66-77`). **Due implementazioni della stessa regola, in due linguaggi.** Il
commento di `reconcile_chain` lo dice a voce alta: «This mirrors the frontend's `buildDisplayChain`».
Finché è così, «ciò che la pagina mostra dev'essere ciò che succede» è una promessa che qualcuno deve
ricordarsi di mantenere a ogni modifica — cioè esattamente la condizione che ha prodotto il difetto
3.

**Proposta: un solo `GET` che restituisce la decisione già presa, nella forma in cui il runtime
l'ha presa.** Non «i cinque interruttori», ma «l'ordine effettivo, chi lo scavalca, e perché». La
pagina disegna quello che le viene detto e non calcola niente.

Il guadagno concreto è che il disegno del bivio di §5.2 e quello dell'anello diventano **lo stesso
codice di frontend con dati diversi**: il giorno in cui il ponte imparerà a ripiegare, la pagina lo
disegnerà come anello senza che nessuno la modifichi — e, cosa che conta di più, **non esiste
nessun momento in cui la pagina possa disegnare un ripiego che il backend non fa.** Allo stesso
modo, se una regola di compatibilità come `model_activation.py:22` tornasse per qualunque ragione,
la pagina ne mostrerebbe l'effetto da sola, perché mostra il risultato e non gli ingredienti.

### 11.2 Cosa è successo davvero, per provider

Serve per §4.3, ed è la sola cosa che permetta alla pagina di dire «credito esaurito» invece di
«Attivo». Oggi HIRIS **butta via** questa informazione: `llm_router.py:175` logga «Backend ... failed,
trying next» e va avanti; i runner collassano ogni errore in `RunnerBackendError("Errore temporaneo
del servizio AI")` perdendo codice e causa.

Il minimo che serve, per provider: **l'ultimo esito, quando è successo, quanto è durato il
fallimento, e da quante richieste dura.** Non serve persistenza su disco: un dizionario in memoria
alimentato dal ciclo di ripiego basta, e «da quando l'add-on è partito» è un'età dichiarabile.

**Metà del lavoro è già fatta e va solo esposta.** `_conn_fail_count` / `_circuit_open_until`
(`backends/openai_compat_runner.py:259-260`) sono già uno stato di guasto per provider, per tre
provider su cinque, aggiornato dal traffico vero. Manca la rotta che lo restituisca, e mancano i due
provider che non ce l'hanno: **Claude non ha nessuna protezione** e viene ritentato integralmente a
ogni turno — che è esattamente perché il proprietario paga una chiamata fallita a messaggio da
settimane senza che niente ceda mai.

Due discipline da mettere nel contratto, perché altrimenti questa informazione nasce già bugiarda:

- **Distinguere le famiglie di errore**, almeno tre: credenziale/credito (400/401/402/403), modello
  inesistente (404), irraggiungibile (errore di connessione). Sono tre frasi diverse e tre azioni
  diverse per l'utente. Collassarle in «errore temporaneo» è ciò che fa il codice oggi, ed è la
  ragione per cui il proprietario non ha mai saputo del credito.
- **Nessuna sonda automatica all'apertura della pagina.** Sondare cinque provider a ogni apertura
  costa denaro e quota per un'informazione che scade subito, e trasformerebbe questa pagina in una
  cosa che conviene non aprire. La pagina riferisce le osservazioni che il traffico vero ha già
  prodotto. Una sonda **su richiesta** (`Prova adesso`, per riga) è legittima e la prevedo — purché
  il suo esito venga scritto con la stessa data e la stessa forma di tutti gli altri, così che
  «provato a mano» e «provato dalla chat» non diventino due stati diversi.

### 11.3 La scrittura, e il riavvio

Le decisioni escono da `config.yaml` e vanno in `models_config.json`, scritto da questa pagina — che
è già il meccanismo esistente per `chain_order` e `provider_models`, esteso. Nessun giro dal
Supervisor, nessuna perdita di valore all'aggiornamento (le chiavi che restano in `config.yaml` non
si toccano).

Resta il problema di §0.5: **oggi metà di questi valori si applicano solo al riavvio, e la pagina
dichiara la cosa sbagliata sul valore sbagliato.** Due strade, in ordine di preferenza:

- **(a) Togliere il problema.** I runner leggono `app["models_config"]` al momento dell'uso invece
  che alla costruzione, e i provider attivi si ricalcolano quando la catena cambia. Allora nessun
  controllo di questa pagina ha bisogno di una didascalia, e **l'assenza di didascalie è la cosa più
  onesta che la pagina possa dire di sé**. È il contrario del rimedio del contratto precedente
  (`riapplicato al riavvio dell'add-on` su ogni controllo interessato), che era giusto quando la
  pagina non poteva cambiare niente e diventa una confessione ripetuta quando la pagina è il posto
  dove si decide.
- **(b) Se (a) non entra nella fetta**, allora **una sola barra a livello di pagina** — «3 modifiche
  aspettano il riavvio» + `[ Riavvia l'add-on ]` — e non venti didascalie. Una confessione sola è
  informazione; venti sono rumore che si smette di leggere. Il bottone richiede `POST
  /addons/self/restart`: `hassio_api: true` c'è, `SUPERVISOR_TOKEN` c'è, **ma nessun chiamante
  esiste oggi e non l'ho verificato** — e va progettato il momento in cui l'add-on si riavvia sotto
  la pagina che lo ha chiesto (stato «riavvio in corso», riconnessione automatica). Se la verifica
  fallisse, la barra resta e il bottone diventa un'istruzione.

Nota bene, per chi scriverà la fetta: la didascalia di oggi è **sbagliata** sul modello di Claude
API, non solo imprecisa. Cambiarlo ha effetto **immediato** sul ponte (§0.4) e **solo al riavvio**
sull'API. Qualunque strada si scelga, quel singolo valore va sistemato per primo.

---

## 12. Cosa NON ho messo, e perché

1. **Il prezzo per milione di token.** Sarebbe la cosa più richiesta e la più dannosa: HIRIS non ha
   una fonte di prezzi, i listini cambiano più spesso dei rilasci, e un prezzo vecchio è peggio di
   nessun prezzo — è una bugia che sembra un servizio. Le quattro nature (`a consumo` / `nel piano` /
   `gratuito` / `in casa`) portano tutto ciò che serve per ordinare una catena.
2. **Un pulsante «Prova tutti» automatico all'apertura.** §11.2: costa soldi e quota a ogni apertura
   per un'informazione che scade in un minuto.
3. **Regole condizionali** («usa Ollama per le domande brevi»). È una seconda catena, invisibile,
   che contraddirebbe quella disegnata. Se un giorno servirà, il posto è questo — ma allora la
   pagina ha una sola catena in più, non un motore di regole.
4. **Un secondo modello di ripiego dentro lo stesso provider.** Raddoppia il concetto di modello per
   un guadagno che la catena già copre.
5. **Il trascinamento come unico modo di riordinare.** Le frecce restano; il trascinamento è
   un'aggiunta, mai il solo meccanismo — tastiera e touch.
6. **La conferma prima di togliere un provider dalla catena.** Il gesto è reversibile con un gesto,
   e la riga riappare due centimetri sotto. Confermare sarebbe paternalismo.
7. **Un grafico dei consumi.** C'è la pagina Consumi. Qui sta solo il contatore del tetto
   giornaliero del ponte, e sta qui perché senza di lui il tetto è un numero su cui non si può
   ragionare.
8. **`llm_strategy` come modo persistente** (§5.3): resta come tre scorciatoie, esce come stato.
9. **Un ordine di visualizzazione fisso per i provider.** Il contratto del 2026-07-27 ne prescriveva
   uno (Abbonamento, Claude API, OpenAI, OpenRouter, Ollama) e la pagina add-on riordinata ne usa un
   altro (l'ordine di ripiego di `balanced`): due liste, due ordini, già incoerenti fra loro. Qui la
   lista è una sola e l'ordine è quello dell'utente; l'ordine fisso sopravvive solo in «Fuori dalla
   catena», dove non significa niente e quindi non può contraddire niente.
10. **Un riquadro informativo permanente sul confine fra le due pagine.** Oggi ce n'è uno
    (`models-route.js:337-344`) e spiega una regola di compatibilità che con questo progetto smette
    di esistere. La spiegazione del confine compare una volta, nello stato vuoto (§9.1), dove è
    l'unica cosa che serve sapere.
11. **Una procedura guidata di primo avvio.** Lo stato vuoto (§9.1) dice cosa manca in due righe e
    dove andare. Chi legge questa pagina non ha bisogno di essere accompagnato.

---

## 13. Cosa non appartiene a questa pagina, e cosa appartiene e non era in lista

Il brief invitava a dirlo.

**Non appartiene: i due campi degli embedding** (§8). Va la dichiarazione, non i controlli — e la
ragione decisiva è che spostarli costa una perdita di valore silenziosa in cambio di niente.

**Non appartiene: `llm_strategy` come impostazione** (§5.3). Appartiene la sua funzione, come
scorciatoia.

**Appartiene e non era in lista: `local_model.model`.** Il brief lascia in Configurazione add-on
«l'indirizzo di Ollama» e non nomina il modello. Ma il modello di Ollama è la stessa decisione che
per gli altri quattro provider si prende qui, e per di più oggi è l'unica riga della pagina che
mostra un valore dichiarandolo immodificabile («*fisso, da config add-on*»,
`models-route.js:274`). Con questo progetto diventa una scelta fra i modelli davvero scaricati, letti
da `/api/tags` — che è più di quanto un campo di testo nel Supervisor possa dare. Va spostato.

**Appartiene e non era in lista, ed è il buco più grosso: il modello della chat**
(`impostazioni_chat.model`, pagina `#/impostazioni`). Oggi quel campo **scavalca tutto questo
lavoro**: se non è `"auto"`, sceglie il provider da solo (`llm_router.py:149-156`), salta la catena
e annulla il ripiego, e questa pagina non lo nomina mai. Peggio: `_route` finisce con `return
self._ollama` come ultimo ramo, quindi un identificatore che non assomiglia a nessun formato noto
viene mandato a Ollama e **lì riscritto** in `LOCAL_MODEL_NAME` (`openai_compat_runner.py:403-404`),
scartando la scelta dell'utente senza nemmeno una riga di log. È l'unica sostituzione di modello
davvero silenziosa del prodotto.

Due strade, e raccomando la prima:

- **(a) Il selettore di modello esce da `#/impostazioni`.** «Un concetto per posto» applicato fino
  in fondo: il modello si sceglie per provider, qui, e la chat usa sempre la catena. Non si perde
  niente di esprimibile — «voglio Opus» si ottiene mettendo Claude primo con Opus — e si guadagna che
  esiste **un solo posto** dove si decide chi risponde, che è il titolo di questo lavoro.
- **(b) Se resta, va riformulato come «forza un modello, ignorando la catena»** e va rispecchiato
  qui, nel blocco 03 (§3), perché una pagina che disegna una catena mentre un'altra pagina la
  disattiva è il difetto 3 sotto un altro nome.

---

## 14. Invarianti da pinnare, e rischi

Cose che questo disegno rende vere e che possono tornare false senza che nessuno tocchi questa
pagina. Vanno pinnate con dei test, perché nessuna di loro lascia traccia altrove.

1. **La chat non fa streaming.** Tutto il disegno della catena regge su questo (§0.1). Il giorno in
   cui `static/chat/send.js` chiedesse SSE, il ripiego sparirebbe (`llm_router.py:181-193` non ne
   ha) e questa pagina inizierebbe a mentire. Un test che verifichi che il ramo di produzione passa
   da `llm_router.chat` e non da `chat_stream`, oppure — meglio — dare a `chat_stream` lo stesso
   ciclo di ripiego.
2. **La topologia disegnata è quella calcolata.** Se resta una seconda implementazione lato client
   della regola della catena, l'invariante è una disciplina; con §11.1 diventa una struttura. Se la
   fetta non fa §11.1, allora serve un test che confronti l'esito di `buildDisplayChain` e di
   `reconcile_chain` sugli stessi ingredienti.
3. **Nessuna parola dichiara una capacità che il sistema non può verificare.** Un test sul
   vocabolario della pagina, nella famiglia di `tests/test_prompt_azione.py`: «Attivo», «Disponibile»,
   «Funzionante» e simili non devono comparire come stato di un provider.
4. **Un provider è in catena se e solo se è usato.** Nessun percorso può usare un provider fuori
   catena, nessun percorso può saltarne uno dentro (a parte il bivio del ponte, che è disegnato come
   tale). **C'è un punto dove sarebbe già falso, e per fortuna è morto**: `llm_router.simple_chat`
   (`llm_router.py:210`) sceglie con un `self._claude or self._openai or self._ollama` scritto a
   mano — OpenRouter escluso, nessun ripiego, catena ignorata. Ho verificato col grep: **nessun
   chiamante di produzione** (le sole occorrenze fuori dal router sono le implementazioni dei
   backend). Va tolto insieme a questa fetta, prima che qualcuno lo richiami: è una seconda regola
   di instradamento che aspetta solo di contraddire la pagina.
5. **I token semantici del testo sono gli `*-ink`.** `hiris-theme.css:76-79` scrive la regola;
   secondo l'audit pre-UAT `models-route.js` è l'unico punto d'uso rimasto indietro. Con la
   riscrittura va allineato, e vale un test che vieti `var(--warn)`/`var(--ok)`/`var(--err)` come
   colore di testo.

**Rischi noti del disegno.**

- **Il connettore aggiunge altezza.** Cinque provider in catena fanno quindici righe invece di
  cinque. Accettato: sono le righe che spiegano perché un ordine è meglio di un altro, e cinque
  provider in catena contemporaneamente è un caso raro.
- **Il pannello del modello è una superficie nuova.** Non esiste nella SPA di oggi (non c'è un
  vocabolario di popover in `hiris-config.css` oltre a `.popover-presets`, che è del vecchio editor).
  Va disegnato dentro il linguaggio esistente: `.section-card` come base, `--shadow-lg`, `--r-md`.
- **`Prova adesso` spende.** Su Claude e OpenAI una sonda costa una chiamata vera. Va tenuta a un
  token e va detto che costa, oppure ridotta a un `GET /models` dove esiste (OpenAI, OpenRouter,
  Ollama) — e su Anthropic, che non ha un elenco pubblico, dichiarare che la sola prova possibile è
  una richiesta vera.
- **La rimozione di `llm_strategy` come stato** è una modifica di comportamento per chi aveva
  salvato `cost_first`. La finestra conta più dell'argomento: se la fetta esce insieme allo
  spostamento dei cinque interruttori — che comunque azzera e ricostruisce quello stato — il salto
  non sorprende nessuno.

---

## 15. Se la fetta dovesse entrare a pezzi, questo è l'ordine

Non è un piano — è la scala di quanto ogni pezzo vale da solo, se il resto non arrivasse mai.

1. **La frase in cima, con i dati di oggi.** Anche senza §11.2, con il solo payload attuale la
   pagina può già dire chi è primo in catena, che il ponte scavalca tutto, e che c'è un token pagato
   fuori dalla catena. Nel caso del proprietario due delle tre righe di §9.3 sono già scrivibili
   adesso. È il pezzo con più valore per riga di codice di tutto il progetto.
2. **Il ponte acceso senza token** (§4.3). Un `if` su due booleani già nel payload, e chiude uno
   stato in cui ogni messaggio si perde in silenzio.
3. **La catena come unica verità** (§4.4) e la riga-provider con il suo modello (§6). È il grosso, ed
   è ciò che chiude i difetti 1 e 3 del brief.
4. **La scrittura a caldo** (§11.3a). Senza, la pagina resta una che confessa; e il valore su cui
   confessa sbagliato — il modello di Claude API — va sistemato comunque, anche in una fetta di sole
   didascalie.
5. **Gli esiti osservati** (§11.2). È quello che chiude il caso del proprietario per intero: senza,
   la pagina sa dire «Claude è primo» ma non «e sta rifiutando da quaranta richieste».
6. **La topologia calcolata dal runtime** (§11.1). È il pezzo che rende gli altri cinque
   irreversibili: finché non c'è, «la pagina non mente» è una promessa che qualcuno deve ricordarsi
   di mantenere.
7. **Il ripiego dal ponte alla catena.** Il più grosso, ed è l'unico che rende vera la frase che il
   proprietario ha chiesto — «usa il piano Claude Max, e se non è disponibile passa a OpenRouter».
   Fino ad allora la pagina disegna un bivio, e lo disegna onestamente.
