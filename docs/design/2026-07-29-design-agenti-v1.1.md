# Agenti 2.0 — Brain che orchestra, Agenti che fanno, Task come atto

**Data:** 2026-07-29 · Repo: `hiris` · Base: **v1.0.0** (`3b75dfd`)
**Stato:** design **completo** — tutti i punti aperti chiusi il 2026-07-29. Target: **v1.1**.
**Origine:** conversazione di design con l'utente, 2026-07-29, dopo il rilascio della 1.0.
**Prossimo passo:** piano d'implementazione (skill `writing-plans`), su conferma.

## Il problema

La 1.0 ha due forme che fanno qualcosa:

- **Chatbot** — conversa. Sei presente tu, turno per turno. Se chiudi, finisce.
- **Agentbot** — vigila. Trigger → azione **dichiarata**. Non sceglie mai cosa fare.

Manca la forma per: *"ti ho dato un obiettivo, lavoraci, e dimmi com'è andata."* Nessuna delle due regge un compito come **«scopri perché il consumo è salito del 30% e dimmi cosa fare»**: il Chatbot non sopravvive alla chiusura della UI, l'Agentbot deve sapere in anticipo cosa farà — ma qui il punto è che *non lo sappiamo ancora*.

## L'idea

Una sola entità che fa: l'**Agente**. Il **Task** è la sua unità di azione, non un'entità sorella. Il **Brain** ragiona e orchestra, ma non esegue mai.

### I due pilastri

Tutto poggia su due invarianti. Se cadono, cade il design.

1. **Un task è sempre una dichiarazione**, mai una chiamata composta al volo: *«questo servizio, su questa entità, con questi parametri»*. L'intelligenza dell'agente sta nel decidere **quali** task creare; l'esecuzione resta deterministica e passa dal semaforo. **L'LLM non causa mai direttamente un'azione: emette intenzioni.**
2. **Il Brain non esegue mai.** Analizza, ragiona, crea/invoca/schedula agenti. L'output di un modello non può causare un'azione se non attraverso un'entità autorizzata.

Il pilastro 1 generalizza il contratto che l'Agentbot ha già oggi (verdetto-JSON senza tool che attuano: legge liberamente, non attua mai direttamente): invece di un verdetto, emette task.

## Le entità

### Agente — l'unica cosa che fa

Una sola entità, **due modalità** sullo stesso substrato:

| | **modalità REGOLA** *(= Agentbot 1.0)* | **modalità OBIETTIVO** *(nuova)* |
|---|---|---|
| Cosa dichiari | trigger → task | obiettivo in linguaggio naturale |
| Chi decide i task | l'utente, alla creazione | l'agente, ragionando |
| LLM | **opzionale — zero se spento** | necessario |
| Esempio | *«finestra aperta 10 min → avvisa»* | *«valuta e ottimizza i consumi»* |

La modalità REGOLA **non si perde ed è preziosa**: è deterministica, ispezionabile e costa zero. Non va forzata dentro un ragionamento.

Un agente in modalità obiettivo: **legge → valuta → emette task → osserva l'esito → decide se continuare**. Può anche emettere **proposte** (automazioni HA, nuovi agenti) invece di agire.

### Task — l'unità di azione

Dichiarativo, ispezionabile, eseguito deterministicamente, **sempre attraverso il semaforo**. Appartiene a un agente. Un task può generarne altri.

### Brain — orchestratore che non esegue

Analizza, ragiona, **non attua**. Crea, invoca e schedula agenti. Quando i suoi controlli diventano ripetitivi, **propone un agente specializzato**.

### Chatbot — invariato

Resta a parte: è l'altro modo, quello in cui sei presente tu.

## Il contratto di autorizzazione

Autorizzi **una volta**, come un'automazione HA. Ma ciò che approvi è il **perimetro**, non la lista dei task (che per definizione cambierà):

```
  Obiettivo      "Valuta e ottimizza i consumi"
  Può agire su   AREA Lavanderia + AREA Cucina
  Fino a         semaforo VERDE
  Budget         50k token/giorno · scadenza 30 min
  Letture        tutto (limitato di fatto dal gate sui dati sensibili)
```

### Fiducia progressiva

La prima volta che l'agente vuole compiere un'azione mai fatta su una certa entità, **chiede** (tap + OTP, il meccanismo esistente): *Solo stavolta* / *Sempre* / *No*.

**Granularità del "Sempre": verbo + entità specifica.** Sbloccare `switch.turn_off` su `switch.boiler_lavanderia` **non** sblocca lo stesso verbo su `switch.boiler_bagno`, né `switch.turn_on` sulla stessa entità. Conservativo per scelta: su una casa, meglio un'interruzione in più che una sorpresa.

*Mitigazione prevista:* al primo giro, richiesta cumulativa (*«vuole fare X su queste 6 entità — sempre per tutte?»*) per evitare raffiche di richieste.

### Domini pericolosi

Per `lock`, `alarm_control_panel`, `cover`, `siren`, `garage_door` la fiducia progressiva **può** essere concessa — l'agente è autorizzato a eseguire quell'azione — ma **la richiesta di conferma parte comunque**. Concedere il "Sempre" autorizza l'agente a *tentare* l'azione; non sopprime l'OTP.

In pratica, su un dominio pericoloso la sequenza è sempre:

```
  agente emette il task  →  il semaforo lo riconosce pericoloso
                         →  parte la richiesta OTP (digitato, non tap)
                         →  se confermi: eseguito
                         →  se non confermi / scade: non eseguito
```

> **Proprietà preservata (invariata rispetto alla 1.0):** niente di pericoloso si esegue senza che un umano confermi *quella specifica azione*. La fiducia progressiva riduce le interruzioni sui domini ordinari; sui pericolosi riduce l'attrito di autorizzazione, **mai** quello di conferma.

### Ambito di lettura

Un agente **legge tutto** (stati, storico, consumi, documenti, memoria); solo le **azioni** sono confinate al perimetro. Zero configurazione sulle letture.

Questo è sicuro **perché il gate esiste già**: `automatic_allows_sensitive` consente al contenuto marcato sensibile di raggiungere un modello **solo se l'intera catena disponibile è locale** (Ollama); con una catena cloud resta fuori, fail-closed. Nella pratica *«legge tutto»* significa *«legge tutto ciò che è già consentito mandare al modello in uso»*.

Il costo reale non è la privacy ma la **spesa**: più contesto = più token.

> **Rettifica (Fase 2, Task 3).** Come implementata, la Fase 2 **non** rispetta questo paragrafo: `perimeter.allowed_entities` è **una sola lista che governa sia la lettura sia l'azione**. `tools/dispatcher.py` la usa per filtrare `get_entity_states`, `get_history`, `get_home_status`, `get_entities_on`, `get_entities_by_domain` e `get_area_entities` *oltre* che per rifiutare le attuazioni. Un agente con `allowed_entities: ["light.cucina"]` **non vede** `sensor.consumo_cucina`. Vedi `Debito noto — Fase 2`, voce 1.

## Ciclo di vita e fine corsa

Budget (token/giorno) e scadenza per esecuzione sono parte del contratto, non opzionali.

All'**80% del budget** l'agente chiede fuori banda se proseguire (*Continua* / *Fermalo*). Se non rispondi entro la scadenza, **si ferma e lascia un resoconto strutturato**:

```
AGENTE "Consumi"  — IN PAUSA
  Budget esaurito dopo 3 dei 5 passi
  Ho capito:      il picco viene dalla pompa di calore (6h/g contro 2h di marzo)
  Ho già fatto:   letto storico 90gg · isolate 3 entità sospette
  Mi restava:     correlazione col meteo · proporre una fascia oraria
  [ Dagli altro budget ]  [ Chiudi ]
```

Il lavoro parziale non si perde: un rilancio riparte da ciò che aveva capito.

## Il ciclo di miglioramento

```
Brain osserva → nota una ripetizione → propone un agente specializzato
                                          ↓ autorizzi una volta
                                      l'agente lavora nel suo perimetro
                                          ↓ si ripete con successo
                                      propone di diventare una REGOLA
                                          (deterministica, costo zero)
```

**La libertà diminuisce man mano che l'autonomia aumenta.** Un agente che ha imparato il suo mestiere si condensa in una regola che non ha più bisogno di pensare. È anche la versione onesta di *«il Brain crea agenti per migliorarsi»*: la promozione atterra nell'entità **vincolata** e passa dall'assenso umano.

## Impatto sul codice esistente

### Si riusa così com'è

| Pezzo | Ruolo |
|---|---|
| `Task` + `task_engine` | Ha già `trigger`, `actions[]`, `condition`, `status`, `result`/`error`, **`parent_task_id`**, ambito. È l'unità di azione, già pronta. |
| `reasoning/queue.py` | Coda job durevole (claim/submit), nata per la chat via abbonamento. Substrato d'esecuzione per agenti che lavorano nel tempo. |
| Step-up (tap + OTP) | Canale fuori banda per fiducia progressiva e domanda di budget. |
| `security/semaphore.py` | **Invariato.** Gate di ogni task. |
| `agentbots.json` + `validate_agentbot` | È già la modalità REGOLA. |
| Usage per-entità + backoff rate-limit | Substrato del budget. |
| Proposte + ponte approva→crea | Diventa "approva → crea l'Agente". |

### Si smonta / evolve

- **"Test Run" del Chatbot** — esecuzione sincrona con timeout 10 min nel FE + `execution_log`. È un'esecuzione d'agente con una brutta interfaccia → sostituita da *«esegui come agente»*, asincrona e rendicontata.
- **`Task.chatbot_id` → `agent_id`** — rinomina meccanica.
- **Editor** — `chatbot-editor.js` e `agentbot-editor.js` sono già sullo **stesso kit condiviso** (1.0): REGOLA/OBIETTIVO diventa un ramo dentro l'editor agente. Incrementale, non un rifacimento.

### La riga più delicata

```python
allowed_tools=[]   # oggi hardcodato nel ragionamento dell'Agentbot
```

Diventa **una lista chiusa di tool di sola lettura**, imposta nel codice — mai configurabile, mai estendibile da configurazione umana o generata. È l'unico invariante di sicurezza della 1.0 che questo design modifica, e va trattato come tale: nessun tool che attua può entrare in quella lista.

## Riordino delle fasi (2026-07-29, dopo la Fase 1)

La mappa originale metteva perimetro e concessioni **prima** della modalità obiettivo. La Fase 1 ha mostrato che non regge: **la fiducia progressiva ha senso solo quando l'agente sceglie le azioni**, e in modalità regola l'azione è dichiarata e approvata alla creazione. Perimetro e concessioni sarebbero rimasti **inerti** finché la modalità obiettivo non esiste — due fasi consecutive non verificabili sul campo, ed è esattamente nei percorsi non esercitati che si annidano i difetti (il Critical della Fase 1 stava in un percorso che nessun test attraversava).

**Nuovo ordine — a fette verticali:**

| Fase | Contenuto | Verificabile? |
|---|---|---|
| ~~1~~ | ✅ fondazione dello schema (fatta, merge `34789c7`) | invisibile per costruzione |
| **2** | **modalità OBIETTIVO reale + perimetro minimo** (ambito azione, tetto tier, budget, scadenza). **Nessuna fiducia progressiva**: ogni azione chiede conferma, sempre | **sì, end-to-end** |
| **3** | fiducia progressiva: store delle concessioni, "Sempre", revoca, richiesta cumulativa — **progettata su come la Fase 2 viene usata davvero** | sì |
| **4** | ciclo di miglioramento (Brain propone agenti; regola invoca obiettivo; agente ripetuto → regola) + **tag v1.1** | sì |

Un agente-obiettivo senza fiducia progressiva è **sicuro e usabile**, solo più chiacchierone: chiede conferma ogni volta. La fiducia progressiva è un'ottimizzazione di UX sopra un sistema già corretto — e va progettata sull'attrito reale, non immaginato.

## Decisioni (punti chiusi il 2026-07-29)

**1. Chi autorizza — owner configurato.** Nelle opzioni dell'addon si indicano uno o più utenti HA come **proprietari**. Solo loro autorizzano agenti e concedono i "Sempre"; gli altri usano la chat e vedono cosa succede, ma non possono ampliare i poteri di un agente.
*Vincolo tecnico:* l'Ingress passa l'identità (`X-Remote-User-Id`, nome) ma **non** dice se l'utente è amministratore di HA — quindi la proprietà va dichiarata in configurazione, non dedotta.

**2. Inneschi della modalità obiettivo — manuale, pianificato, invocazione del Brain.** Gli **eventi restano dominio della modalità regola**, che costa zero. Se una regola rileva qualcosa che merita ragionamento, **invoca lei** l'agente-obiettivo:

```
REGOLA (deterministica, gratis)
  "consumo orario > 3kW per 30 min"
        └── invoca ──▶ AGENTE OBIETTIVO
                       "scopri cosa lo causa e proponi un rimedio"
```

Così il pensiero costoso parte solo quando c'è davvero qualcosa da pensare — e non a ogni ricorrenza di un evento rumoroso.

**3. Dove vivono i resoconti — in entrambi i posti, con ruoli diversi.** Una riga di sintesi nel **feed della home del Brain** (che già aggrega ragionamenti, segnalazioni e proposte: risponde a *«è successo qualcosa?»*), e il dettaglio completo nella **pagina dell'agente** insieme al suo storico di esecuzioni (risponde a *«cosa ha fatto esattamente e perché»*).

**4. Richiesta cumulativa.** Quando in un singolo giro un agente deve chiedere più azioni della stessa forma, parte **una sola richiesta raggruppata** — *«vuole spegnere 6 interruttori in Lavanderia: sempre per tutti / solo stavolta / scegli quali»* — **con l'elenco visibile**. Un "sempre per tutti" senza vedere la lista sarebbe l'assegno in bianco che questo design evita.

**5. Persistenza e revoca della fiducia — nella pagina dell'agente.** Ogni agente ha una sezione **«Cosa gli hai permesso»**: l'elenco delle coppie *verbo + entità* concesse, con la data, una revoca puntuale per ciascuna e un **«Revoca tutto»** che riporta l'agente allo stato di appena autorizzato.

> La fiducia progressiva **accumula potere nel tempo**. Tenerla visibile dove l'agente vive — e non in una pagina che nessuno apre — è ciò che impedisce che dopo tre mesi tu non sappia più cosa possono fare i tuoi agenti.

## Debito noto — Fase 2

Scelte prese **consapevolmente** durante la Fase 2 e non ancora chiuse. Sono qui perché siano **tracciate**, non perché siano sviste: la regola di questa fase è che il vincolo di **non-regressione** vince sulla completezza, quindi tutto ciò che avrebbe richiesto di toccare il comportamento esistente è stato rimandato invece che forzato.

**1. Una sola lista governa vista e tatto (Task 3).**
`perimeter.allowed_entities` confina **sia ciò che l'agente può vedere sia ciò che può toccare**: un'entità non elencata non è soltanto non attuabile, non è nemmeno **leggibile**. Contraddice il paragrafo *Ambito di lettura* (rettificato sopra). Accettato per questa fase: separare i due assi vorrebbe dire introdurre un secondo campo (`readable_entities`) e un secondo punto di controllo, cioè esattamente le due cose che questa fase evita. **Conseguenza pratica da documentare all'utente:** se un agente deve *guardare* qualcosa per decidere, quel qualcosa va **elencato nel perimetro**, non solo ciò su cui deve agire.

**2. Un Agentbot `mode="rule"` con `reasoning.enabled` ragiona ancora senza confini (Task 3).**
La modalità regola **non ha** (e non può avere) un blocco `perimeter`: `validate_agentbot` lo vieta. Ma se ha `reasoning.enabled`, il suo ragionatore riceve comunque l'intero set `EVALUATION_ONLY_TOOLS`, **`create_task` incluso**, e i Task che ne nascono hanno `agent_id="hiris-default"` e `allowed_entities`/`allowed_services` a `None` — cioè **nessun confine oltre al semaforo**.

È il comportamento che le regole hanno **sempre** avuto, e il vincolo di non-regressione di questa fase è esplicito: *un Agentbot `mode="rule"` esistente non deve cambiare di una virgola*. Dargli un perimetro adesso significherebbe restringere in silenzio configurazioni utente già funzionanti. **Resta quindi vero che la modalità regola + ragionamento è il percorso meno confinato del sistema**, e va chiuso quando ci sarà una migrazione esplicita (fase 3 o 4), non di soppiatto. Il confine che regge oggi su quel percorso è il **semaforo** (denylist + tier + conferma), non il perimetro.

**3. Asimmetria di `create_task` (Task 3, review minor #7).**
Il ramo `create_task` del dispatcher rifiuta alla **creazione** un *servizio* fuori perimetro, ma lascia passare un'*entità* fuori perimetro, che viene rifiutata solo all'**esecuzione** da `task_engine._run_action`. L'LLM può quindi ricevere «task creato» per un task che non farà nulla. Voluto: `allowed_entities` ha **un solo punto di enforcement**, e aggiungerne un secondo lo farebbe divergere nel tempo. Il costo è un messaggio d'errore peggiore, non un confine più debole.

## Versione: 1.1, non 2.0

**Condizione che rende onesto il numero: nessuna rottura per le configurazioni esistenti.**

Il design regge questa promessa **sui dati persistiti**: gli Agentbot di oggi diventano *modalità regola* con migrazione a fiuto sul contenuto (`mode` assente ⇒ `"rule"`), e `tasks.json` ha già uno shim di lettura per-campo che copre tutte e tre le generazioni di nome.

**Correzione (grounding 2026-07-29): non regge su due contratti wire, che vanno sanati esplicitamente nel piano.**

| Contratto | Dove | Perché rompe |
|---|---|---|
| Corpo di risposta di `GET /api/tasks` e `/api/tasks/{id}` | `handlers_tasks.py:15,25` → `asdict(Task)` | Emette `chatbot_id` verbatim, **senza alias e senza test che lo copra**. Un consumatore esterno (card, script, template HA) leggerebbe `undefined`. |
| Schema del tool MCP `list_tasks` | `task_tools.py:62`, letto in `dispatcher.py:387` | La proprietà `chatbot_id` è letta **senza fallback**: un client MCP esterno che ha imparato la vecchia chiave riceve silenziosamente la lista **non filtrata**. |

Entrambi si chiudono emettendo/accettando **entrambe le chiavi**. Con quelle due righe la promessa 1.1 regge; senza, non regge.

*(Il query param `?chatbot_id=` è già al sicuro: `handlers_tasks.py:12` accetta già `?agent_id=` come fallback.)*

Il Chatbot non si tocca, il semaforo non si tocca.

Se durante lo sviluppo emergesse qualcosa che rompe una configurazione utente, **quello è il segnale che è diventata una 2.0** — e va detto, non aggirato.

## Non-goal

- Non si tocca il semaforo.
- Non si introducono tool che attuano nel ragionamento.
- Non si rimuove la modalità REGOLA deterministica a costo zero.
- Il Chatbot resta com'è.

## Valutazione

Il design è **più coerente e più difendibile del modello 1.0** su due fronti: sposta la sicurezza dalla verifica a runtime alla **struttura** (il Brain non può eseguire; l'LLM emette solo dichiarazioni), e riduce le entità invece di aggiungerne (Task diventa unità, non fratello).

Il costo è reale: tocca `task_engine`, il ragionamento dell'Agentbot e il modello di autorizzazione. Ma è **additivo per l'utente** — chi ha configurato Agentbot oggi non deve rifare nulla — quindi **v1.1**.

**Raccomandazione:** far girare la 1.0 sul campo in parallelo allo sviluppo. Molti dei difetti peggiori trovati costruendo la 1.0 erano invisibili finché non sono stati cercati davvero; il modello dell'agente guadagna dagli attriti reali, non solo dal ragionamento a tavolino.
