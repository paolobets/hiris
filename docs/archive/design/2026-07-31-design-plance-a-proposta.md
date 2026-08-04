# HIRIS — Plance (dashboard Lovelace) a proposta

Data: 2026-07-31 · Stato: design approvato dall'utente · Filone 1

## Problema

Un utente chiede in chat di modificare le dashboard e HIRIS risponde di non
poterlo fare. L'audit del codice smentisce il sintomo: HIRIS **sa** creare e
modificare plance (tool `create_ha_config` kind `dashboard` e
`add_dashboard_view`, metodi WebSocket Lovelace in `proxy/ha_client.py`), e il
prompt di sistema non lo vieta.

Il problema vero è un'**asimmetria di flusso**:

| Oggetto | Percorso dalla chat |
|---|---|
| Automazioni | tool `create_automation_proposal` → **proposta** riesaminabile → apply |
| Dashboard / script / scene | tool → **scrittura immediata su HA**, senza proposta e **senza semaforo** (`tools/dispatcher.py:551-560`) |

Il tipo di proposta `ha_dashboard` **esiste già ed è reale all'apply**
(`api/handlers_proposals.py:60-72` → `apply_ha_config` →
`ha_client.create_dashboard`), ma è raggiungibile **solo dal gateway MCP**
(`handlers_execute.py:206-217`). Nessun tool permette all'LLM in chat di
*proporre* una plancia: `create_automation_proposal` espone l'enum
`["ha_automation", "hiris_agent"]` (`tools/proposal_tools.py:26`).

Di conseguenza il Chatbot ha solo due comportamenti possibili: scrivere subito
senza review, oppure — se il suo `allowed_tools` non include quei tool — non
fare nulla e dichiararsi incapace.

## Obiettivo

Portare le plance sullo stesso modello delle automazioni: **l'LLM propone,
l'umano approva, l'apply scrive**. Eliminare la scrittura diretta delle
dashboard dalla chat e la sua elusione del semaforo.

## Decisioni prese (con l'utente)

1. **Sostituire** l'azione diretta col flusso a proposta (non affiancarla).
2. Ambito modifica: **sostituzione completa** della config di una plancia (non
   solo additivo).
3. Sicurezza dell'apply: **review + snapshot/undo**, senza OTP.

La 2 e la 3 sono legate: la sostituzione completa è potente e potenzialmente
distruttiva, quindi la sicurezza non sta nell'attrito (OTP) ma nella
**reversibilità**.

## Vincoli accertati

- Le plance dell'utente sono in **storage mode** → scrivibili via WebSocket.
  Le dashboard in YAML mode non sono scrivibili (`ha_client.py:255`); il caso
  va gestito come errore chiaro, non come fallimento silenzioso.
- Lovelace **non è esposto via REST** in Home Assistant: ogni operazione passa
  dal WebSocket.
- `url_path` di una dashboard deve contenere un trattino (`config_tools.py:15`).

## Architettura

### A. Superficie tool (solo Chatbot)

Per proporre una sostituzione sensata l'LLM deve prima **leggere** la plancia.
Tre tool, due dei quali di sola lettura:

| Tool | Natura | Descrizione |
|---|---|---|
| `list_dashboards` | lettura, nessun gate | Elenca le plance (`url_path`, titolo, mode). Richiede il nuovo `ha_client.list_dashboards` (WS `lovelace/dashboards/list`). |
| `get_dashboard_config(url_path)` | lettura, nessun gate | Config attuale di una plancia. Usa `ha_client.get_lovelace_config` (esistente). |
| `propose_dashboard(mode, url_path, title?, config, reason)` | **crea proposta** | Scrive una proposta di tipo `ha_dashboard` nel ProposalStore. Non tocca HA. |

`propose_dashboard` è il gemello di `create_automation_proposal`: stessa forma,
stesso store, stessa UI di review.

**Rimozione dell'azione diretta:** `create_ha_config` perde il `kind:
dashboard`; `add_dashboard_view` viene rimosso dai tool esposti. Entrambi i
percorsi in `dispatcher.py:551-560` cessano di scrivere dashboard.

**Fuori scope dichiarato:** `create_ha_config` continua a creare **script e
scene** in modo diretto. La stessa asimmetria resta aperta per loro; è un
follow-up esplicito, non una svista.

### B. Proposta `ha_dashboard`

Riusa il tipo esistente (già validato in `_VALID_PROPOSAL_TYPES`, già reale
all'apply). Il `config` della proposta contiene:

| Campo | Obbligatorio | Note |
|---|---|---|
| `mode` | sì | `create` (nuova plancia) o `replace` (sostituisce una esistente) |
| `url_path` | sì | destinazione; per `create` deve contenere un trattino |
| `title` | solo `create` | titolo mostrato in sidebar |
| `ha_config` | sì | config Lovelace completa (dict con `views`) |

Validazione alla creazione della proposta (fail-closed, come
`validate_agentbot`): `mode` fra i due ammessi, `url_path` presente e valido,
`ha_config` dict contenente `views`. Una proposta non valida viene **rifiutata,
non salvata** — la lezione del bug #2 era che i tipi non canonici finivano nel
ramo status-only e sembravano applicati.

**UI di review:** la card della proposta mostra un'intestazione esplicita —
«Crea nuova plancia "X"» oppure «**Sostituisce interamente** la plancia "X"» —
oltre all'anteprima JSON già presente per `ha_dashboard`. L'utente deve capire
cosa sta approvando senza leggere il JSON.

### C. Apply, snapshot e undo

Estensione del ramo `ha_dashboard` di `apply_ha_config`:

- `mode: create` → `ha_client.create_dashboard` (esistente).
- `mode: replace` →
  1. legge la config attuale (`get_lovelace_config`);
  2. la salva in `DashboardBackupStore` (`dashboard_backups.json`, ultimi
     **3** snapshot per `url_path`, i più vecchi vengono scartati);
  3. scrive la nuova config con il nuovo `ha_client.save_dashboard_config`
     (WS `lovelace/config/save`).

Se la lettura della config attuale fallisce (es. plancia in YAML mode, o
url_path inesistente), l'apply **si ferma e riporta l'errore**: non si
sovrascrive mai senza aver prima messo al sicuro lo stato precedente.

**Undo.** Dopo un `replace` riuscito, la card nella sezione Proposte mostra
«✓ Attivata — Annulla». L'azione chiama `POST
/api/dashboards/{url_path}/restore`, che ri-applica l'ultimo snapshot tramite
lo stesso `save_dashboard_config`. Un overwrite sbagliato si annulla con un
click.

Un restore **riuscito consuma** lo snapshot riapplicato: da quel momento è lo
stato corrente della plancia, quindi `GET /api/dashboards/backups` non lo
elenca più e l'affordance di ripristino sparisce senza che l'interfaccia debba
ricordarsi nulla (sopravvive quindi anche a un refresh). Le versioni più
vecchie restano ripristinabili; se HA rifiuta la scrittura lo snapshot **non**
viene consumato, perché il ripristino non è avvenuto e va poter riprovare.

Il consumo è **per identità, non per posizione**: fra la lettura dello snapshot
e la sua rimozione c'è la scrittura verso HA (un `await`), e in quella finestra
un apply `replace` concorrente (secondo tab, gateway MCP) può appendere un nuovo
snapshot per la stessa plancia. `discard_latest_backup` riceve la config
riapplicata e rimuove l'ultima entry **solo se coincide**; altrimenti non tocca
nulla e ritorna `False` — meglio una voce di troppo nell'elenco che cancellare
la via di ritorno di quella sostituzione. Il restore resta comunque un 200: la
plancia è stata ripristinata davvero.

Il `count` esposto da `GET /api/dashboards/backups` conta solo le versioni
**ripristinabili** (stesso criterio di `latest_backup`), e serve al frontend per
dire la verità nella striscia: con più di uno snapshot la plancia non è
«sostituita» — può essere appena stata ripristinata — e il pulsante porta a una
versione ancora precedente. Dopo un restore riuscito la pagina toglie quella
voce dalla propria cache prima di richiedere l'elenco: non è memoria locale di
«cosa ho già annullato» (l'elenco del server resta l'unica verità), è recepire
ciò che il server ha appena confermato, così un aggiornamento fallito non lascia
a schermo un pulsante che al secondo click scenderebbe di un'altra versione.

### D. Gating e visibilità

- **Chi può usarli:** solo il Chatbot (chat). Brain e Agentbot restano esclusi:
  i nuovi tool **non** vengono aggiunti a `EVALUATION_ONLY_TOOLS`
  (`claude_runner.py:210`), coerente con la protezione anti prompt-injection
  già in essere.
- **Gate:** nessun semaforo, nessun OTP. Il gate umano è la review della
  proposta, come per le automazioni; la rete di sicurezza è lo snapshot/undo.
  Con la rimozione dei tool diretti, sparisce anche l'attuale scrittura di
  dashboard che elude del tutto il semaforo.
- **Scope per-Chatbot:** i nuovi tool rispettano `allowed_tools` come ogni
  altro tool (`claude_runner.py:651`). Un Chatbot con whitelist ristretta
  continuerà a non vederli — comportamento voluto e ora diagnosticabile.

### E. Nuovi metodi in `ha_client.py`

| Metodo | Comando WS | Uso |
|---|---|---|
| `list_dashboards` | `lovelace/dashboards/list` | tool `list_dashboards` |
| `save_dashboard_config` | `lovelace/config/save` (con `url_path`) | apply `replace` + restore |

I nomi esatti dei comandi e la forma del payload vanno **verificati contro la
documentazione/API reale di Home Assistant** in fase di piano, prima
dell'implementazione.

## Test

**Backend (pytest)**
- `propose_dashboard` valida `mode`, `url_path`, `ha_config`; input invalido →
  nessuna proposta salvata.
- Apply `mode: create` → chiama `create_dashboard`.
- Apply `mode: replace` → **lo snapshot è salvato prima** della scrittura
  (ordine verificato, non solo presenza).
- Apply `replace` con lettura config fallita → nessuna scrittura, errore
  riportato.
- Restore → ri-applica l'ultimo snapshot e, **solo se la scrittura riesce**, lo
  consuma: l'elenco non lo propone più; un restore fallito lo lascia dov'è.
- Restore con salvataggio concorrente durante la scrittura verso HA → il
  consumo per identità non tocca lo snapshot nuovo; esito 200 per l'utente.
- `count` conta solo le versioni ripristinabili, non le entry malformate.
- Lo store tiene al massimo 3 snapshot per `url_path`.
- Una proposta `ha_dashboard` non finisce mai nel ramo status-only.

**Frontend (node --test + jsdom)**
- La card `ha_dashboard` mostra l'intestazione giusta per `create` e per
  `replace`.
- Dopo un `replace` applicato compare l'azione «Annulla», che chiama
  l'endpoint di restore.
- Con più di una versione ripristinabile la striscia non dichiara la plancia
  «sostituita» e offre esplicitamente la versione ancora precedente.
- Restore riuscito seguito da un aggiornamento dell'elenco fallito → la voce
  non ricompare (e non si può partire un secondo restore).
- Se invece il server continua a elencare quella voce, l'affordance torna:
  la verità resta la sua, la pagina non se lo ricorda per conto proprio.

## Rischi

| Rischio | Mitigazione |
|---|---|
| L'LLM genera una config Lovelace malformata e l'utente la approva distrattamente | Intestazione esplicita di sostituzione + snapshot/undo |
| Comandi WS Lovelace diversi da quelli ipotizzati | Verifica sulla doc HA in fase di piano, prima di implementare |
| Plancia in YAML mode | L'apply fallisce con errore chiaro; nessuna scrittura parziale |
| Perdita della capacità "aggiungi vista" oggi esistente | Coperta: l'LLM legge la config e propone la stessa config più la vista |

## Follow-up (non in questo lavoro)

- Script e scene restano ad azione diretta: stessa asimmetria da chiudere.
- Filone 2 — visione/salute sistema: logbook, `system_health`,
  Supervisor/add-on, template; batterie nel report salute esposto all'LLM.
