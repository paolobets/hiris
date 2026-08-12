# La mappa — cosa c'è dentro HIRIS, e cosa ne resta

**Data:** 5 agosto 2026 · versione analizzata `1.1.0-beta.18`
**Perché esiste:** *«è stato inserito troppo in questa app che doveva essere semplice, mattoncino su
mattoncino abbiamo perso la coerenza»*.
**Metodo:** sei letture indipendenti del codice, una per area, ciascuna con l'ordine di produrre
**verdetti** e non descrizioni. Il metro è `2026-08-04-scope-hiris.md`.

**Come si legge:** la Parte 1 è l'elefante — leggila. La Parte 2 dice quanto del prodotto è
effettivamente acceso. La Parte 3 è la mappa completa, riga per riga, su cui mettere una crocetta.

> ## 🗄 Annotazione — 12 agosto 2026: il verdetto sui documenti è stato superato
>
> **Questa mappa resta il verbale del 5 agosto e non viene riscritta — un verbale non si riscrive,
> si annota (stessa disciplina di `PRODUCT.md`). Questo blocco è l'annotazione.**
>
> Il 12 agosto 2026 il proprietario ha deciso: *«Al momento l'integrazione documentale può essere
> tolta, la rivedremo poi, non serve.»* Con la 2.1.0 (`refactor!: esce l'integrazione documentale`)
> sono usciti dal prodotto Mayan EDMS, l'archivio di conoscenza (`KnowledgeStore`, `knowledge.db`),
> la cattura dello storico (`HistoryStore`, `history.db`), la pagina Storicizzazione, il digest
> delle 04:00 e la pseudonimizzazione (`brain/privacy.py`).
>
> **Le righe di questa mappa che quella decisione ha superato:**
>
> - § 3.4, `| Documenti | Spenti; unico consumatore legittimo degli embedding | **TIENE** |` — il
>   verdetto è oggi **ESCE**. È la riga su cui la fetta aveva appoggiato il proprio confine, ed è
>   quella che la decisione ha ribaltato.
> - § 3.4, `| Storico | … | **SEMPLIFICA** |` — non è stato semplificato: è **uscito** per intero,
>   con la sua pagina e le sue rotte. La cronaca della casa la tiene Home Assistant.
> - Parte 4, l'elenco di *«ciò che sopravvive intero»*: la voce **«i documenti, unico consumatore
>   legittimo degli embedding»** non sopravvive.
>
> **Cosa resta valido.** Tutto il resto della mappa, compresa la riga
> `| Embedding e ricerca vettoriale | Inerte di fabbrica, e l'utente non lo sa | **TIENE** ma va
> dichiarato in UI |`: le due opzioni `memory.embedding_provider`/`memory.embedding_model` sono
> rimaste, e la 2.1.0 ha fatto esattamente ciò che la riga chiedeva — dichiarare l'inerzia in
> configurazione, nelle traduzioni e nella pagina Modelli. Il consumatore che la riga dava per
> legittimo però non c'è più: quando i vettori si accenderanno, sarà sopra un archivio nuovo.
>
> **Per cosa il prodotto fa davvero oggi:** il `README.md` e il `CHANGELOG.md`.

---

# Parte 1 — L'elefante

Non ci sono novanta problemi. **Ce ne sono nove, ripetuti novanta volte.**

### 1. La casa esiste in cinque copie, e nessuno le vede tutte

`entity_cache` (stato) · `semantic_context_map` (30 tipi, per la chat) · `semantic_map` (12 ruoli,
per due tool, con classificazione LLM **a pagamento**) · `knowledge_db.entity_classifications`
(persistenza di una delle due) · `portrait` (aree/acceso/aperto/allerta, per il Brain). Più lo
`snapshot` della ronda e il `health_monitor`.

**La chat riceve la mappa e non il ritratto. Il Brain riceve il ritratto e non la mappa.** Due
intelligenze nella stessa casa, che vedono due case diverse.

### 2. Sei strade per dire una cosa a una persona

`notify_tools` (4 canali) più il resoconto, i solleciti, la scansione di salute, i task e
l'esecutore, che lo scavalcano. **Quattro logiche di deduplica diverse.** E la destinazione del push
non è configurabile da nessuna interfaccia: `HA_NOTIFY_SERVICE` è letta dal codice e mai esportata,
quindi ogni notifica va a `notify.notify`.

### 3. Cinque percorsi di conferma per un'azione rischiosa

Tap sulla notifica (nessuna verifica umana, funziona a telefono bloccato) · pagina in HIRIS (l'unica
che verifica davvero) · OTP in chat · step-up dei task · una frase nel prompt che chiede al modello
di autocontrollarsi.

**Gli ultimi due sono morti per costruzione**: dipendono da una mappa utente→canale che **nessuna
interfaccia scrive**. Il modello dice «guarda il telefono» e sul telefono non arriva niente.

### 4. Quattro strade perché una modifica arrivi a Home Assistant

Azione diretta (semaforo) · proposta (approvazione… ma l'apply accetta il solo token, quindi chi
crea la proposta può approvarsela) · `create_ha_config` dalla chat, che **scrive script e scene
subito, senza proposta né semaforo** · task differito.

Lo stesso `create_ha_config` è **una proposta** se arriva dall'execute API e **una scrittura
immediata** se arriva dalla chat. Stesso nome, due comportamenti opposti.

### 5. Il catalogo degli strumenti esiste in tre copie divergenti

34 definizioni per la chat · 16 nomi per l'execute API · 15 tool MCP. Con nomi citati nelle
descrizioni che non sono raggiungibili (chi li chiama prende 403).

### 6. «Batteria scarica» ha tre implementazioni. «Porta aperta» anche

Sempre-attivo con soglia fissa · opt-in con soglia regolabile · e il resoconto che rilegge il primo.
Un commento nel codice difende la duplicazione per diciassette righe: è il sintomo, non la
spiegazione.

### 7. Tre freni che non si parlano

Cooldown e tetto giornaliero **globali** da variabili d'ambiente · cap per-agente · tetto giornaliero
della chat. Tre semantiche, tre configurazioni, nessuna comunicazione.

### 8. Chatbot e Agentbot sono la stessa macchina con due file di configurazione

Stesso runner, stesso `reason()`, stesso esecutore, stesso semaforo, stessa contabilità: l'Agentbot
finisce **letteralmente dentro** `get_chatbot_usage()`. La differenza vive nel vocabolario e in due
editor da 90 KB di JavaScript. Ciò che davvero li distingue — avere un innesco proprio — **è un
campo, non un'entità.**

### 9. Cinque strade per creare un bot, e nessuna è quella prevista

Wizard che indovina il tipo **contando parole con espressioni regolari, senza mai chiamare un
modello** · due editor vuoti · onboarding della chat · proposta del Brain. **Tutte e cinque creano
l'entità già attiva**, cioè il contrario di quanto lo scope prescrive. La strada del contratto — *lo
dici in chat, il sistema chiede ciò che manca, poi chiede «attivo?»* — è **l'unica che non esiste**.

---

# Parte 2 — Quanto di HIRIS è davvero acceso

Su un'installazione appena fatta, **si muovono da sole quattro cose**. Due delle quattro sono mute,
perché parlano di dati che di fabbrica non esistono.

| Spento di fabbrica | Conseguenza |
|---|---|
| Il **semaforo** (nessun tier configurato) | **Ogni azione viene negata in silenzio.** La chat risponde «bloccata dal semaforo (off)» e non dice dove si sblocca |
| I **4 rilevatori**, le **2 situazioni**, l'**arrivo serale** | La sorveglianza gira a vuoto: fa una fotografia ogni 15 minuti e la butta |
| La **revisione olistica** | È l'unico Brain proattivo esistente. Spento ⇒ la zona più visibile della Dashboard **non riceverà mai una riga** |
| La **cattura storica** | Il digest delle 04:00 gira e non scrive nulla. La taratura automatica non può partire |
| L'**embedder** | Nessuna ricerca per significato. Tutto degrada ai più recenti |
| Il **documentale** | Nessuna scadenza esiste ⇒ i solleciti ogni 6 ore sono muti |
| Il **ponte abbonamento** e l'**execute API** (`internal_token` vuoto ⇒ 401) | Anche la chat via abbonamento non può chiamare nessuno strumento |

E l'interruttore che accende il Brain **si chiama «Riepilogo giornaliero»**: non è un riepilogo, è
l'unico comando di quattro funzioni diverse, e il nome collide con il vero resoconto delle 08:00 che
sta altrove. **Nessuno lo accenderebbe mai per la ragione giusta.**

### Cose morte, non spente

| Cosa | Prova |
|---|---|
| **Test Run del Chatbot** | Passa un parametro che nessun runner accetta: `TypeError` alla prima chiamata reale. Nessuno può averlo usato con successo |
| **Taratura automatica delle soglie** | ~400 righe dietro tre interruttori in serie. Mai partita su nessuna installazione |
| **Coda di approvazione della conoscenza** | Nessuno scrive più `pending`. La pagina interroga la coda **ogni 30 secondi, per sempre** |
| **Kill-switch e audit MCP** | Nessun endpoint, nessun chiamante |
| **Notifiche Retropanel** | URL mai esportata: irraggiungibile per chiunque |
| **MQTT** | Sette sensori per chatbot, **nessun consumatore**; `budget_remaining_eur` è la costante `"unlimited"` |
| **Annotazioni entità, correlazioni, pattern di query** | Tre tabelle create e mai scritte |
| **Costo OpenRouter** | Non è nel listino: ogni chiamata è contabilizzata **0,00 €**. Un freno di spesa costruito su questo numero non frena |
| **~24 variabili d'ambiente** | Lette dal codice, mai esportate: costanti travestite da configurazione |
| **6 rotte HTTP** | Nessun frontend le chiama |

---

# Parte 3 — La mappa completa

Verdetti: **TIENE** · **SEMPLIFICA** · **UNIFICA con X** · **ESCE**.

## 3.1 La conversazione

| Funzionalità | Cosa fa davvero | Verdetto |
|---|---|---|
| Pagina chat | La porta. Funziona, senza streaming | **TIENE** |
| Card Lovelace | Cronologia in `localStorage`, **divergente** da quella del server che alimenta il prompt | **UNIFICA** con la pagina chat |
| Più Chatbot | Ogni persona ha prompt, tool, memoria e limiti propri | **ESCE** — è il workbench, non la porta |
| Mappa semantica nel prompt | Piena di fabbrica, ma **solo** la chat la riceve | **UNIFICA** — darla anche al Brain |
| Memoria richiamata | Inerte: degrada sempre ai più recenti | **SEMPLIFICA** |
| Fatti dichiarati | Entrano sempre, con filtri corretti | **TIENE** |
| Sessioni precedenti | «Nuova conv.» cancella **tutte** le sessioni e i riassunti | **SEMPLIFICA** |
| Chat via abbonamento | Turno **cieco**: niente mappa, memoria, dichiarati, **niente tool** | **UNIFICA** col percorso sincrono |
| Streaming | Implementato due volte, lo vede solo la card | **SEMPLIFICA** |
| Pannello Proposte | Funziona; nessun perimetro visibile prima del sì | **UNIFICA** con la pagina Proposte |
| Pannello Task | Innesco→azione senza giudizio | **ESCE** — Legge III |
| Pannello Memoria | **Morto** | **ESCE** |
| Conferma OTP in chat | **Inattivabile** | **ESCE** |
| Freni e conti della chat | Barra budget **morta** | **SEMPLIFICA** |

## 3.2 I bot e la loro creazione

| Funzionalità | Cosa fa davvero | Verdetto |
|---|---|---|
| Chatbot | Una sola persona esiste, seminata dal codice | **SEMPLIFICA** → impostazioni della chat |
| Test Run | `TypeError` alla prima chiamata | **ESCE** — morto |
| Template preconfigurati | Riempiono due textarea | **ESCE** — sono automazioni HA |
| Permessi del Chatbot | `[]` = tutto per il Chatbot, `[]` = niente per l'agente: **convenzione opposta** | **UNIFICA** nel perimetro |
| Agentbot modalità regola | Innesco→azione senza giudizio | **ESCE** — condannata dallo scope |
| Agentbot modalità obiettivo | Coerente; ma solo su pianificazione, e `max_tier` **non è onorato da nessun runtime** | **TIENE** → si chiama **agente** |
| Freni | Globali da env, non per-agente; il budget si verifica **a spesa avvenuta** | **UNIFICA** nel perimetro |
| Wizard goal-first | Indovina il tipo con espressioni regolari; l'entità nasce **già attiva** | **ESCE** |
| I due editor | 90 KB di JS per la stessa entità | **SEMPLIFICA** → un editor di perimetro |
| Agente da proposta | Funziona; nasce **abilitato** | **TIENE** con «nasce disattivato» |
| Task pianificate | Solo un modello può crearne | **SEMPLIFICA** → mano dell'agente |
| Rilevatori sulla pagina «Agentbot» | La pagina degli Agentbot **è** il pannello dei rilevatori | **ESCE** |
| Consumi | Promette un budget per Chatbot **che non esiste più** | **SEMPLIFICA** |
| Pagina Modelli | Il modello si sceglie in **quattro** posti | **SEMPLIFICA** |

## 3.3 Il Brain e la sorveglianza

| Funzionalità | Cosa fa davvero | Verdetto |
|---|---|---|
| Scansione di salute | 8 controlli, sempre attiva, senza interruttore | **SEMPLIFICA** — metà la fa HA |
| Push delle segnalazioni gravi | Accesa di fabbrica | **UNIFICA** col resoconto |
| Revisione olistica | Unico Brain proattivo. **Spenta** | **SEMPLIFICA** — deve proporre oggetti HA |
| Auto-applicazione dei rilevatori | Scrive sorveglianza **senza chiedere** | **ESCE** |
| Proposte di automazione dal Brain | **L'unica riga pienamente in scope.** Inerte | **TIENE** — va accesa |
| Taratura automatica | Mai partita | **ESCE** |
| Resoconto 08:00 | Sempre attivo, invia anche a riepilogo vuoto | **SEMPLIFICA** |
| Solleciti scadenze | Muti (documentale spento) | **UNIFICA** col resoconto |
| Digest storico | Non scrive nulla | **UNIFICA** col ritratto, o esce |
| Cronologia ragionamenti | **Vuota per sempre** di fabbrica | **SEMPLIFICA** — 4 cronologie diverse |
| 4 rilevatori integrati | Spenti | **ESCE** — lo scope li nomina |
| Situazioni della ronda | Due regole cablate, mai accese | **ESCE** |
| Arrivo serale | Spento | **ESCE** |
| Esecutore + semaforo + proposta-script | Auto-esecuzione spenta; semaforo off ⇒ tutto negato | **UNIFICA** nel perimetro |
| Freni | **Lo scope li salva**: unica capacità che HA non ha | **TIENE, ma sposta** nell'agente |
| Ponte runner esterno | Spento | **SEMPLIFICA** — è trasporto |

## 3.4 Memoria, conoscenza, ritratto

| Funzionalità | Cosa fa davvero | Verdetto |
|---|---|---|
| Archivio unico | Coerente col contratto | **TIENE** |
| Salvataggio ricordi | Sempre approvato, mai scadenza | **TIENE** |
| Richiamo ricordi | Tre chiamanti ricostruiscono lo stesso richiamo | **SEMPLIFICA** |
| Fatti dichiarati | È ciò che salva il prodotto senza embedder | **TIENE** |
| Coda di approvazione | **Inerte**, e la pagina la interroga ogni 30s | **ESCE** |
| Aggiunta manuale | Stessa scrittura di `save_memory` | **UNIFICA** |
| Embedding e ricerca vettoriale | Inerte di fabbrica, e l'utente non lo sa | **TIENE** ma va dichiarato in UI |
| Ritratto | Rende **due** dei quattro contenuti promessi | **UNIFICA** con la mappa semantica |
| Osservazione periodica | Funziona | **TIENE** |
| Chi riceve il ritratto | **La chat non lo vede mai** | **SEMPLIFICA** |
| Mappa semantica (chat) | Piena, letta solo dalla chat | **UNIFICA** col ritratto |
| Mappa semantica per ruoli | Classificazione LLM **a pagamento** per due soli tool | **ESCE** |
| Classificazioni e annotazioni | Tre tabelle su quattro morte | **SEMPLIFICA** |
| Documenti | Spenti; unico consumatore legittimo degli embedding | **TIENE** |
| Storico | Inerte; è il recorder di HA riscritto | **SEMPLIFICA** |
| Digest degli insight | **Dannoso**: alle 04:00 occupa tutti gli slot del ragionatore e sfratta i ricordi veri | **ESCE** dall'archivio |
| Scadenze e spese | Corrette, ma il Brain non le vede mai | **SEMPLIFICA** — dentro il ritratto |

## 3.5 Azioni e sicurezza

| Funzionalità | Cosa fa davvero | Verdetto |
|---|---|---|
| Semaforo per-azione | Inerte ⇒ tutto negato in silenzio | **ESCE** |
| Denylist domini pericolosi | Batte tutto, tranne una conferma umana | **SEMPLIFICA** → «azione irreversibile» |
| Pagina Accessi Gateway | Accende il semaforo di **tutto** il sistema, chiamandosi «gateway» | **ESCE** col semaforo |
| Conferma tap notifica | Nessuna verifica umana; funziona a telefono bloccato | **UNIFICA** |
| Conferma inbox in HIRIS | **L'unica che verifica davvero l'umano** | **TIENE come modello** |
| Conferma OTP in chat | Morta | **ESCE** |
| Conferma step-up dei task | Morta per la stessa ragione | **ESCE** |
| «Chiedi conferma» nel prompt | Nessun controllo: il modello che la ignora attua | **ESCE** |
| Dispatcher | Punto unico di esecuzione | **TIENE, SEMPLIFICA** |
| Execute API | `internal_token` vuoto ⇒ 401 su tutto | **SEMPLIFICA** — token all'avvio |
| Server MCP interno | Espone un **terzo** catalogo | **UNIFICA** |
| Gateway MCP esterno | **Non esiste in questo repo** — ma metà delle protezioni esistono per lui | **ESCE** — o si dichiara vivo |
| Kill-switch e audit MCP | Morto | **ESCE** |
| Denylist di lettura | Ben fatta; protegge una superficie irraggiungibile | **TIENE** — segue il gateway |
| Proposte | **Il cuore dello scope.** Ma l'apply non richiede l'umano | **TIENE** con verifica umana |
| Scrittura diretta fuori dalle proposte | Due strade parallele verso HA | **UNIFICA** con Proposte |

## 3.6 Integrazione HA, modelli, superfici

| Funzionalità | Cosa fa davvero | Verdetto |
|---|---|---|
| Conoscenza HA | Fondazione; il Brain non la riceve | **TIENE** — darla a tutti |
| Monitor di salute HA | **Nessun frontend lo legge** | **UNIFICA** con le segnalazioni |
| MQTT | Nessun consumatore; costanti come telemetria | **ESCE** |
| Notifiche | **Sei strade**; destinazione non configurabile | **UNIFICA** |
| Apprise + Retropanel | Retropanel irraggiungibile | **ESCE** |
| Attivazione provider | La pagina li mostra e **non li può cambiare** | **SEMPLIFICA** |
| Catena di ripiego | Due policy nello schema, **sempre sovrascritte** | **SEMPLIFICA** |
| Modello per-entità | Si sceglie in quattro posti | **SEMPLIFICA** |
| Abbonamento Claude | Un quinto provider travestito da architettura | **SEMPLIFICA** |
| Consumi | OpenRouter sempre 0,00 € | **TIENE** come freno, **ESCE** come pagina |
| Storico HIRIS | Pagina che configura un motore spento | **ESCE** |
| Superficie HTTP | 64 rotte, 6 senza chiamanti | **SEMPLIFICA** |
| Opzioni e pagine | **51 opzioni, 9 pagine**; dopo il primo giorno se ne usano due | **SEMPLIFICA** |

---

# Parte 4 — Cosa resta

Contando i verdetti: **~90 funzionalità mappate**. Circa **un terzo esce**, un terzo si unifica o
semplifica, e **meno di venti tengono così come sono.**

Ciò che sopravvive intero è poco e coerente:

- **la chat** come unica porta;
- **la conoscenza della casa**: archivio, ricordi, dichiarati, ritratto, osservazione;
- **le proposte** — l'unico meccanismo che fa già ciò che il contratto chiede;
- **l'agente in modalità obiettivo**, che è l'unica cosa in quell'area che lo scope riconosce;
- **i freni**, l'unica capacità che Home Assistant non ha;
- **i documenti**, unico consumatore legittimo degli embedding.

Il resto è o un doppione, o un'automazione di Home Assistant scritta in Python, o una funzione che
non si è mai accesa.

**Non serve decidere novanta righe.** Le nove sovrapposizioni della Parte 1 le portano quasi tutte
con sé: sciolta la sovrapposizione, i verdetti delle righe che vi appartengono seguono.
