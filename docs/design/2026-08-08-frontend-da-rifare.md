# Frontend da rifare — l'elenco per la fetta E5

Prodotto dal Task 15 della fetta E3 («Esce la casa vecchia»), che **non tocca `static/`**: qui si
elenca e si verifica, non si ripara e non si nasconde (vincolo esplicito del brief).

## Metodo

Ogni `fetch(...)`/`api(...)` che compare in `hiris/app/static/` è stato estratto con un grep mirato
e confrontato con la tabella di routing viva, cioè l'elenco reale delle `app.router.add_*` in
`hiris/app/server.py` **a HEAD di questa fetta** (35 rotte):

```
/  /config  /api/health  /api/status  /api/config  /api/usage  /api/usage/reset
/api/chat  /api/chat/reply/{job_id}
/api/chatbots  /api/chatbots/{agent_id}[/run|/usage|/usage/reset|/chat-history]
/api/entities
/api/models  /api/models/config
/api/knowledge/pending  /api/knowledge/{id}/approve  /api/knowledge/{id}/reject  /api/knowledge
/api/history/policy
/api/reasoning/claim  /api/reasoning/submit
/api/casa  /api/memoria  /api/memoria/{id}  /api/nucleo
```

Ogni endpoint chiamato dal frontend che **non** compare in questa lista risponde 404. Nessuna delle
pagine sotto mostra un errore visibile per questo: sono tutte scritte per degradare in silenzio
(`.catch(() => [])`, `r.ok ? r.json() : []`, badge che restano a `—`), che è esattamente la causa
per cui il censimento del prodotto non le vede da solo — **il frontend non viene analizzato**
(limite dichiarato dello strumento).

Verificato anche il rovescio: gli endpoint frontend **ancora vivi** (`/api/chatbots*`,
`/api/entities`, `/api/models*`, `/api/usage*`, `/api/knowledge*`, `/api/history/policy`,
`/api/casa`, `/api/config`, `/api/health`, `/api/chat*`) hanno tutti almeno un chiamante nello
`static/` — nessuna rotta viva orfana dal lato frontend.

## Tabella

| # | Pagina / pezzo | File JS | Endpoint morti chiamati | Uscito con | Come si rompe |
|---|---|---|---|---|---|
| 1 | Dashboard `#/` — zona 3 "Azioni" (ragionamenti, segnalazioni, proposte) | `config/dashboard.js` (righe 180, 206, 259, 294), `config/main.js` (righe 107, 116, 127) | `/api/brain/feed`, `/api/brain/advisories*`, `/api/proposals*`, `/api/tasks*` | Task 5 (brain/feed), Task 6 (brain/advisories), Task 9 (tasks), Task 10 (proposals) | I tre pannelli e i tre badge di navigazione (`nav-adv-count`, `nav-proposals-count`, `nav-tasks-count`, e i badge inline di `main.js:107,116,127`) restano vuoti/a `—`: ogni `fetch` fallisce ma il codice degrada su array/oggetto vuoto, nessun `alert`/errore mostrato. |
| 2 | `#/tasks` (pagina intera) | `config/tasks-route.js` (righe 29, 33, 92) | `/api/tasks*` | Task 9 | La lista task è sempre vuota (`.catch(() => [])`); il pulsante di cancellazione (riga 33) fallisce silenziosamente allo stesso modo. |
| 2b | Pannello Task della chat + voce nav | `chat/tasks.js` (righe 30, 54), voce `#nav-tasks` in `index.html:76` | `/api/tasks*` | Task 9 | Stesso pannello che in `1.x` mostrava i task pendenti: oggi il fetch iniziale (riga 30) fallisce, il pannello resta vuoto senza errore. |
| 3 | `#/proposals` (pagina intera, tab In attesa/Archivio) | `config/proposals-route.js` (righe 19, 20), `config/proposals-core.js` (righe 71, 78, 84, 96, 106), `config/proposals.js` (workflow legacy, non più montato da nessuna route ma ancora `<script src>` in `config.html:205`) | `/api/proposals*`, `/api/dashboards/*` | Task 10 | Entrambi i tab restano vuoti (`{proposals:[]}` di fallback); Applica/Rifiuta e il ripristino plance da `dashboard_backups.json` (`api/dashboards/backups`, `api/dashboards/{path}/restore`) rispondono 404 mostrato come "Errore" solo se l'utente clicca un'azione — l'elenco iniziale non segnala nulla. |
| 3b | Pannello Proposte della chat + voce nav | `chat/proposals.js` (usa `HirisProposalsCore`, quindi transitivamente `/api/proposals*`), voce `#nav-proposals` in `index.html:83` | `/api/proposals*` | Task 10 | Stesso fallback silenzioso di 3, lato chat. |
| 4 | `#/agentbots` (lista) + editor Agentbot | `config/agentbot-route.js` (righe 121, 173, 348, 409, 427, 459, 491), `config/agentbot-editor.js` (righe 183, 500, 803, 827) | `/api/agentbots*`, `/api/sentinel/policy`, `/api/sentinel/timeline`, `/api/suggestions*` | Task 3 (agentbots), Task 7 (sentinel/policy, sentinel/timeline — il semaforo), Task 5 (suggestions) | La pagina non ha più nessuna via di ingresso dalla sidebar (vedi sotto), ma resta raggiungibile via URL diretto: lista sempre vuota, editor non salva/carica, timeline e suggerimenti muti. `api('api/entities?...')` (riga 173) resta vivo — solo il resto della pagina è morto. |
| 4b | Voce di navigazione Agentbots | `config.html:106` (`<a class="nav-item" href="#/agentbots" data-route="agentbots">`) | — | Task 3 | **Non elencata nel brief**, trovata durante la verifica: la sidebar del Designer ha ancora una voce "Agentbots" che porta a una pagina i cui dati sono tutti morti (vedi riga 4). |
| 5 | `#/gateway` (pagina intera) | `config/gateway-route.js` (righe 67, 192, 214, 337, 357 — tutte passano dal wrapper `api()` a riga 61, che prependa `api/gateway`) | `/api/gateway/pending`, `/api/gateway/pending/{id}/{verb}`, `/api/gateway/policy` | Task 7 | L'intera pagina "Accessi Gateway" (coda approvazioni + policy) è vuota/non salvabile. Nota: `gateway-route.js:5` nomina ancora `HA_NOTIFY_SERVICE`, opzione uscita al Task 13 — commento morto oltre a rotta morta. |
| 6a | Editor Chatbot — riquadro «Autonomia» | `config/chatbot-editor.js:382` | `/api/gateway/autonomy-summary` | Task 7 | Il riquadro non mostra mai un riepilogo di autonomia (era il residuo diretto del semaforo). |
| 6b | Editor Chatbot — riquadro «Context preview» | `config/logs.js:48` (montato da `chatbot-editor.js`) | `/api/chatbots/{id}/context-preview` | Task 2 (fetta E3) | 404 muto, dichiarato già dal report del Task 2: "il pannello ora riceve 404 e la pagina lo mostra vuoto senza errore visibile". |
| 7 | Wizard di creazione — ramo Agentbot | `config/create-wizard.js:730` (`POST api/agentbots` quando `state.type === 'agentbot'`) | `/api/agentbots` | Task 3 | Il quarto step del wizard, se l'utente sceglie "Agentbot" invece di "Chatbot", fallisce alla creazione: `errorEl` mostra l'errore HTTP (unico caso della lista con un errore visibile, perché qui il codice testa esplicitamente `r.ok`). |
| 8 | Catalogo a checkbox del Designer (creazione/editor Chatbot) | `config/templates.js` (righe 71 `send_notification`, 88 `create_automation_proposal`, e le altre voci dei 34 strumenti ex-catalogo) | — (non è un `fetch`, è una lista statica di nomi-tool offerti come checkbox) | Task 8 della fetta **E2** ("escono i trentaquattro") | Le checkbox restano nell'editor Chatbot e sono persistibili (`Chatbot.allowed_tools`), ma **nessun runner filtra più per nome** (rimosso Task 9 di questa fetta): selezionarle o no non ha alcun effetto sul comportamento in chat. Non è una rotta 404, è una configurazione inerte — stessa famiglia di difetto, forma diversa. |

## Non rotte (verificato, non toccare in E5)

- **Chat** (`index.html` + `chat/*.js` tranne `chat/tasks.js` e `chat/proposals.js` sopra): `/api/chat`,
  `/api/chat/reply/{job_id}`, `/api/chatbots*`, `/api/knowledge*` — tutte vive.
- **`#/models`**, **`#/usage`**, **`#/history`**: `/api/models*`, `/api/usage*`, `/api/history/policy`
  — tutte vive.
- **`#/chatbots`** (lista + editor), meno i due riquadri della riga 6: `/api/chatbots*` vivo.
- **Pannello Conoscenza** (`chat/knowledge.js`, `chat/knowledge-core.js`): `/api/knowledge*` resta
  (Decisione 2 del brief — `knowledge_store` non esce con questa fetta).
- **Entity-picker** (`config/entity-picker.js`): `/api/entities` resta.

## Riepilogo per chi pianificherà la E5

Sette pagine/pannelli rotti dal brief (voci 1-7), più due trovati durante la verifica di questo
task (4b: la voce di sidebar Agentbots resta linkata a una pagina morta; 8: il catalogo a checkbox
di `templates.js` non è una rotta rotta ma una configurazione senza più effetto). In totale, 14 file
JS coinvolti: `dashboard.js`, `main.js`, `tasks-route.js`, `chat/tasks.js`, `proposals-route.js`,
`proposals-core.js`, `proposals.js`, `chat/proposals.js`, `agentbot-route.js`, `agentbot-editor.js`,
`gateway-route.js`, `chatbot-editor.js`, `logs.js`, `create-wizard.js`, più le due voci di sidebar
(`config.html:106` per Agentbots, le voci nav di `index.html:76,83` per Task/Proposte) e il catalogo
di `templates.js`. Nessuno di questi file è stato toccato da questo task.
