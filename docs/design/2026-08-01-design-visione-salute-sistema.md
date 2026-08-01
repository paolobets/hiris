# HIRIS — Visione e salute del sistema (Filone 2)

Data: 2026-08-01 · Stato: design da approvare

## Problema

Un utente chiede a HIRIS «ci sono problemi in casa?» e HIRIS non sa rispondere,
pur avendo già in casa metà della risposta.

Due carenze distinte, che vanno affrontate insieme perché la seconda senza la
prima produrrebbe altra duplicazione:

**1. Un ponte mancante all'interno di HIRIS.** Il Brain esegue ogni 30 minuti
cinque controlli di salute (`brain/health_checks.py`) — batterie scariche,
entità non disponibili da giorni, automazioni rotte, domini pericolosi lasciati
in verde, entità senza area — e li scrive in `AdvisoryStore`. Ma **nessuno
strumento li espone all'LLM**: vivono solo nella dashboard della
configurazione. In chat sono invisibili.

Peggio: la logica delle batterie è **già scritta due volte**, con soglie
diverse — in `brain/health_checks.py:46` (`check_low_battery`, soglia 15%) e in
`brain/briefing.py:93-138` (soglia da `policy.detectors.battery.min_pct`). Una
terza lettura indipendente sarebbe il modo sbagliato di rispondere alla
richiesta.

**2. Fonti che HIRIS non legge affatto.** Non esiste alcun accesso a: logbook
(la cronologia degli eventi, cioè il *perché* è successo qualcosa), il
`system_health` nativo di Home Assistant, il Supervisor (stato degli add-on,
spazio disco, aggiornamenti di core/OS/Supervisor/add-on), e la valutazione di
template. Gli aggiornamenti che HIRIS vede oggi sono solo quelli esposti come
entità `update.*`: non sa nulla di add-on e sistema operativo.

## Decisioni prese con l'utente

1. **Sprint completo**: ponte interno e fonti nuove in un unico lavoro.
2. **Segnala e notifica**: i dati sono disponibili in chat su richiesta, il
   Brain apre una segnalazione per le condizioni gravi, e per quelle gravi
   parte anche una notifica push.
3. **Aggiornamenti: lettura completa** (core, OS, Supervisor, add-on) —
   **senza alcuna capacità di applicarli**, nemmeno tramite proposta.

## Linea rossa

Tutto ciò che questo lavoro aggiunge è **in sola lettura**. Nessun tool nuovo
può fermare, avviare, riavviare o aggiornare alcunché: né add-on, né Supervisor,
né sistema operativo. Aggiornare il Supervisor o l'OS è l'azione più delicata
dell'intero sistema, e resta fuori dalla portata di HIRIS.

## Vincoli accertati nel codice

- `get_ha_health` è **sincrona e non tocca mai Home Assistant**: legge lo
  snapshot che `HealthMonitor` aggiorna con un job ogni 30 minuti. È il pattern
  da riusare per ogni dato periodico costoso: un tool che colpisse HA a ogni
  domanda dell'LLM sarebbe un errore di costo.
- Lo snapshot di salute **non ha alcun limite di dimensione** sulle entità non
  disponibili: con molti problemi, l'intera lista finisce nel prompt.
- Il Supervisor **non è raggiungibile dall'LLM** via `http_request`: gli
  hostname `supervisor`/`homeassistant`/`localhost` sono in deny-list
  (`tools/http_tools.py:13`) e gli header del token sono bloccati. È
  intenzionale: serve un tool dedicato server-side.
- `hassio_api: true` è già in `hiris/config.yaml:21` e `SUPERVISOR_TOKEN` è già
  disponibile. Oggi il Supervisor è interrogato solo con due chiamate una
  tantum in `server.py` (slug e URL di ingress): non esiste un client
  riutilizzabile.
- `AdvisoryStore.reconcile` distingue già inserimento, aggiornamento e
  riapertura di una segnalazione: è l'aggancio corretto per notificare **solo
  ciò che è nuovo**, evitando di ri-notificare a ogni ciclo di scansione.
- API verificate sulla documentazione ufficiale: `GET /api/logbook/<timestamp>`
  (parametri `entity`, `end_time`), `POST /api/template`, WebSocket
  `system_health/info`, e sul Supervisor `GET /info`, `/host/info`, `/addons`,
  `/available_updates`, `/core/info`.

## Architettura

### A. Il ponte: gli advisory diventano visibili in chat

Nuovo `tools/advisory_tools.py` con un tool di sola lettura che espone le
segnalazioni aperte del Brain (`AdvisoryStore.list(status="open")`), iniettando
lo store nel dispatcher come già avviene per gli altri store.

**Chiude anche la duplicazione:** il briefing giornaliero smette di ricalcolare
le batterie per conto proprio e legge le segnalazioni del Brain. Una sola
soglia, un solo posto in cui cambiarla.

### B. Stato periodico: nuove sezioni dello snapshot

Nessun tool nuovo. `HealthMonitor` acquisisce due sezioni, e `get_ha_health`
le espone attraverso l'enum che ha già:

- **`system_health`** — dal WebSocket `system_health/info`: salute per-integrazione
  nativa di HA (database, cloud, ecc.).
- **`supervisor`** — stato degli add-on (quali sono fermi o in errore), spazio
  disco dell'host, e **aggiornamenti disponibili per core, OS, Supervisor e
  add-on**.

Il Supervisor richiede un client nuovo, `proxy/supervisor_client.py`, modellato
su `ha_client.py`: sessione in `start()`/`stop()`, header
`Authorization: Bearer $SUPERVISOR_TOKEN`, base `http://supervisor`. Ogni
chiamata degrada a un valore vuoto se fallisce: HIRIS deve continuare a
funzionare su installazioni senza Supervisor (container standalone).

**Cap obbligatori.** Ogni sezione dello snapshot riceve un limite esplicito
dichiarato come costante, e lo snapshot dichiara quando ha troncato (per
esempio «12 entità non disponibili, ne mostro 10»). Include la sezione
`unavailable` che oggi è senza limite: è un difetto preesistente che questo
lavoro chiude, perché aggiungere sezioni senza cap peggiorerebbe il problema.

### C. Query su richiesta: due tool nuovi

Questi non sono fotografie periodiche: hanno senso solo con parametri, quindi
sono tool a sé e non sezioni dello snapshot.

- **`get_logbook(entity_id?, hours)`** — cronologia degli eventi, con o senza
  filtro per entità. Risponde a «cosa è successo ieri sera in salotto?» e «chi
  ha acceso il riscaldamento?». Numero di voci limitato e finestra massima
  dichiarata.
- **`render_template(template)`** — valuta un template Jinja tramite HA.
  Serve alla diagnosi («questa condizione è vera adesso?»). **Chat-only**: non
  entra fra i tool degli agenti autonomi, perché un template può leggere
  qualunque stato e un agente reattivo è esposto al prompt injection
  proveniente dallo stato di Home Assistant. Lunghezza del template e della
  risposta limitate.

### D. Il Brain guarda anche il sistema

Tre controlli nuovi in `brain/health_checks.py`, che seguono la forma dei
cinque esistenti (funzioni pure, nessun I/O, `source_ref` per la deduplica):

| Controllo | Severità | Condizione |
|---|---|---|
| add-on non in esecuzione | alta | un add-on installato e abilitato risulta fermo o in errore |
| spazio disco | alta sotto il 10% libero, avviso sotto il 20% | dal Supervisor |
| aggiornamenti disponibili | informativa | core, OS, Supervisor o add-on aggiornabili |

Le soglie sono costanti dichiarate, non numeri sparsi nel codice.

Nota: gli aggiornamenti restano **informativi** e non generano notifica push —
sono una condizione permanente, non un evento; notificarli produrrebbe rumore
quotidiano.

### E. Notifica per le sole segnalazioni gravi e nuove

Aggancio in `brain/health_scan.py`, sull'esito di `reconcile`: quando una
segnalazione di severità alta viene **aperta o riaperta** — mai su un
aggiornamento di una già aperta — parte una notifica push agli utenti
configurati, riusando `send_notification` e `build_push_data` già esistenti,
con il deep-link a HIRIS già in uso per le altre notifiche.

Il vincolo di non ri-notificare non è una gentilezza: senza, ogni scansione
(48 al giorno) rimanderebbe la stessa notifica, e l'utente disattiverebbe le
notifiche perdendo anche quelle utili.

Deve essere disattivabile da un'opzione dell'add-on, per chi non le vuole.

### F. Il catalogo degli strumenti della UI

`static/config/templates.js` elenca uno strumento che **non esiste**
(`search_entities`) e ne omette molti reali, senza alcun test che tenga
allineate le due liste. Un Chatbot configurato con una whitelist esplicita non
può quindi selezionare gli strumenti nuovi. Il catalogo va allineato e coperto
da un test che fallisce se qualcuno aggiunge un tool senza registrarlo lì.

## Test

- Ogni nuovo tool: definizione valida, pass-through degli argomenti, percorso
  d'errore con dipendenza assente, e cap rispettati.
- `SupervisorClient`: ogni metodo colpisce l'endpoint atteso; un Supervisor
  irraggiungibile degrada a vuoto senza sollevare.
- `HealthMonitor`: le nuove sezioni entrano nello snapshot; un fallimento di
  una fonte non azzera le altre; i cap troncano e lo dichiarano.
- Controlli nuovi del Brain: tabelle di stati in ingresso, come i cinque
  esistenti.
- Notifica: parte per una segnalazione grave **nuova**; **non** parte per una
  già aperta a una scansione successiva; non parte se disattivata.
- Briefing: usa le segnalazioni del Brain e non ricalcola le batterie.
- Catalogo UI allineato a `ALL_TOOL_DEFS`.

## Rischi

| Rischio | Mitigazione |
|---|---|
| Costo in token dello snapshot che cresce | cap per sezione, dichiarati e testati |
| Notifiche ripetute che portano l'utente a disattivarle | notifica solo su apertura/riapertura, e solo severità alta |
| Installazioni senza Supervisor | ogni chiamata degrada a vuoto; la sezione semplicemente non compare |
| Formato di `system_health/info` non documentato in dettaglio | lettura difensiva: si espone ciò che si riconosce, il resto viene ignorato |
| Template come vettore di prompt injection | `render_template` è chat-only, escluso dagli agenti autonomi |

## Fuori scope, dichiarato

- Qualunque **azione** su add-on, Supervisor o sistema operativo, aggiornamenti
  inclusi.
- Script e scene restano ad azione diretta dalla chat (asimmetria ereditata dal
  Filone 1, da chiudere separatamente).
- Nessuna modifica al semaforo o ai tier.
