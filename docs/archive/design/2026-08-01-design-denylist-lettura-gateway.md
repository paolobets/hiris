# HIRIS — Denylist di lettura per il gateway MCP

Data: 2026-08-01 · Stato: design approvato dall'utente

## Problema

Il gateway MCP espone HIRIS a un client remoto (Claude Code) attraverso un
tunnel. Gli strumenti di **azione** che passano di lì sono vincolati da una
whitelist derivata dai domini che l'utente ha marcato verdi nel semaforo. Gli
strumenti di **lettura** no: partono deliberatamente con nessun perimetro.

La ragione, scritta nel codice (`api/handlers_execute.py`, ramo `is_read`), è
legittima: quella whitelist è derivata dai domini **azionabili**, quindi
applicarla alle letture nasconderebbe ogni entità fuori da essi — configurato
il gateway per comandare le luci, non si potrebbe più chiedere la temperatura.

Il risultato però è che **ogni lettura vede tutta la casa**: `get_history` può
restituire lo storico della serratura, `get_entity_states` lo stato
dell'allarme. Non è una falla introdotta di recente: è la condizione attuale.
È emersa lavorando su `get_logbook`, che l'avrebbe resa evidente passando
dall'interrogazione mirata («com'è la serratura?») all'enumerazione («dammi
tutto quello che è successo ieri»).

## Decisione presa con l'utente

Una **denylist di lettura**: un elenco di entità o domini che non escono mai
dal gateway, valido per **tutte** le letture. Si elencano le poche cose
sensibili invece di enumerare tutta la casa, e non ha il difetto della
whitelist d'azione (non nasconde i sensori).

Chiuso questo, `get_logbook` torna disponibile sul gateway: non può più
enumerare ciò che conta.

## Il punto architetturale

**Filtrare gli argomenti in ingresso non basta.** Alcune letture non prendono
affatto un'entità:

| Strumento | Come sfugge a un filtro sui soli argomenti |
|---|---|
| `get_home_status` | restituisce l'intera casa, nessun argomento |
| `get_logbook` | senza `entity_id` elenca tutti gli eventi |
| `get_advisories` | le evidenze contengono identificativi |
| `get_area_entities` | elenca per area |

Se si filtrasse solo l'ingresso, basterebbe **omettere il parametro** per
aggirare il perimetro — lo stesso difetto già trovato e chiuso su `get_logbook`
lato chat. La denylist deve quindi agire su **due lati**: rifiutare una
richiesta che nomina esplicitamente un'entità vietata, e **potare le risposte**
di ciò che non doveva uscire.

## Limite dichiarato

`recall_knowledge` restituisce testo libero della memoria, non entità. Se un
appunto contiene un dato sensibile scritto a mano, nessuna denylist per entità
può intercettarlo. Questo lavoro **non** copre quel caso, e non deve dare
l'impressione di farlo.

## Architettura

### Configurazione

Nuova opzione dell'add-on, accanto a quelle già esistenti per il gateway
(`execute_api_tools`, `execute_api_entities`, `execute_api_services`):
un elenco CSV di glob su `entity_id` — per esempio `lock.*, alarm_control_panel.*`.

**Valore predefinito protettivo.** Il repo segue il principio fail-closed, e la
protezione che l'utente ha scelto non deve dipendere dal ricordarsi di
configurarla. Il valore iniziale copre i domini sensibili **in lettura**:
serrature, pannelli d'allarme, telecamere, e le entità di presenza (`person`,
`device_tracker`), che rivelano quando la casa è vuota.

Nota: non coincide con i domini pericolosi del semaforo, che riguardano
l'**azione**. Una tapparella è pericolosa da muovere ma innocua da leggere;
una telecamera è l'opposto.

È un cambiamento di comportamento per chi già usa il gateway: va dichiarato
nelle note di rilascio, e l'elenco è svuotabile per tornare al comportamento
precedente.

### Applicazione

Nel percorso `/api/execute`, per i soli strumenti di lettura:

1. **In ingresso** — se la richiesta nomina un'entità coperta dalla denylist,
   viene rifiutata con un messaggio chiaro. Rifiutare, non ignorare in
   silenzio: un errore esplicito è diagnosticabile, un risultato vuoto no.
2. **In uscita** — la risposta viene potata delle entità coperte, con la stessa
   convenzione di dichiarazione del troncamento già usata altrove
   (`filtered: {shown, total}`), così il modello remoto sa che sta vedendo una
   parte e può dirlo.

La potatura deve conoscere la forma delle risposte degli strumenti di lettura
esposti: è la parte che richiede attenzione, perché ciascuno ha una struttura
diversa. Una forma non riconosciuta va trattata **fail-closed** — se non so
potarla, non la lascio passare — e registrata nei log.

### Riabilitazione di `get_logbook`

Chiusa la denylist, `get_logbook` torna nell'elenco degli strumenti di lettura
del gateway e nel registro MCP, con il commento aggiornato: non è più
«contenimento della superficie remota» ma «coperto dalla denylist di lettura».

## Test

- La denylist rifiuta una richiesta che nomina un'entità vietata, senza
  raggiungere Home Assistant.
- La denylist pota le risposte: `get_home_status`, `get_logbook` senza entità,
  `get_advisories` non restituiscono entità vietate.
- **Il caso dell'omissione**: uno strumento invocato senza il parametro
  facoltativo non deve restituire entità vietate — è il modo con cui il
  perimetro verrebbe aggirato.
- Una forma di risposta non riconosciuta è bloccata, non lasciata passare.
- La denylist vuota ripristina il comportamento precedente.
- I glob funzionano sia per dominio (`lock.*`) sia per entità singola.
- La denylist **non** si applica alle letture in chat: lì vale il perimetro del
  Chatbot, che è un meccanismo diverso e già verificato.

## Rischi

| Rischio | Mitigazione |
|---|---|
| Il gateway diventa cieco su dati che servono davvero | elenco svuotabile; il default copre solo domini sensibili in lettura |
| Una risposta di forma nuova sfugge alla potatura | fail-closed sulle forme non riconosciute, con log |
| Falso senso di sicurezza sui dati testuali | limite dichiarato: `recall_knowledge` non è coperto |

## Fuori scope

- L'opt-in per singolo strumento di lettura (valutato e scartato per ora).
- Il perimetro delle letture in chat, che ha già il suo meccanismo.
- Qualunque modifica alla whitelist d'azione.
