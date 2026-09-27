# HIRIS per chi non amministra — un'opzione, un cancello al confine

`spec · 27/09/2026 · decisioni del proprietario prese in chat il 27/09/2026, disegno approvato a sezioni · allineata il 27/09/2026 a ciò che è stato costruito (Task 5)`

> **Come si legge dopo la costruzione.** Il disegno approvato resta com'era; dove il codice ha
> preso un'altra strada lo dice un paragrafo **«Cambiato durante la costruzione: …»** accanto alla
> sezione che cambia, con la ragione. I fatti di Home Assistant misurati durante i task stanno in
> §1, datati. Ciò che la fetta lascia fuori sta in §6 e, voce per voce, in `docs/BACKLOG.md`.

Chi installa HIRIS deve poterlo **distribuire in casa anche agli utenti non amministratori** di Home
Assistant, con una configurazione e senza toccare codice. Chiude la voce del BACKLOG «HIRIS per gli
utenti non-admin di Home Assistant» (05/09/2026): il blocco di allora («come sa HIRIS chi è
amministratore») è sciolto dal soffitto (`api/soffitto.py`), e dalle fette «le chat divise» (v3.68.0)
ogni persona ha il suo filo.

Nomi: identificatori in inglese, prosa e valori di dominio in italiano; `storage.init_schema` esegue
lo schema prima delle migrazioni (qui non servono tabelle nuove).

---

## §0 · Le decisioni del proprietario (27/09/2026)

| # | Domanda | Decisione |
|---|---|---|
| 1 | Come si rende HIRIS disponibile ai non amministratori | **Con un'opzione di configurazione** dell'add-on; HIRIS applica la visibilità della voce di menu da sé |
| 2 | Dove sta l'interruttore | **Nelle opzioni dell'add-on** (HA → Add-on → HIRIS → Configurazione), letto all'avvio |
| 3 | Cosa vede un non amministratore | **La chat, i suoi Impegni e le sue memorie.** Il resto di `/config` è chiuso |
| 4 | Le sue memorie | **In sola lettura** — correggere e cancellare la memoria della casa resta agli amministratori |
| 5 | Con l'opzione spenta, chi entra dalla porta laterale | **HIRIS lo rifiuta**: l'opzione è il cancello, non solo il menu |
| 6 | Come si costruisce il cancello | **Una lista di ammissione al confine**: tutto è riservato agli amministratori per difetto, per una persona non amministratrice passa solo ciò che la lista ammette |

Il principio che governa tutto è quello già scritto in `api/soffitto.py`: **HIRIS non concede mai più
di quanto il chiamante può già in Home Assistant.** In HA un non amministratore usa le dashboard e
comanda le entità, non entra in Impostazioni: in HIRIS chatta e comanda, non configura.

---

## §1 · I fatti (verificati il 27/09/2026 su Core 2026.9.3, Supervisor 2026.09.2)

- **`panel_admin` è solo del manifest** (`supervisor/apps/model.py::panel_admin`, default `True` in
  `apps/validate.py`) e **governa solo la voce di menu**: Core registra il pannello con
  `require_admin=data.admin` (`hassio/addon_panel.py::_register_panel`) e `get_panels` lo toglie ai
  non amministratori (`frontend/__init__.py::websocket_get_panels`). L'installatore non può
  cambiarlo dall'interfaccia.
- **Non è un controllo d'accesso.** Core permette ai non amministratori `supervisor/api
  /ingress/session` e `/addons/<slug>/info` via WebSocket (`hassio/websocket_api.py`,
  `WS_NO_ADMIN_ENDPOINTS`, dalla 2021.12, PR #60120); il proxy ingress del Supervisor non controlla
  ruoli (`supervisor/api/ingress.py::handler`) e una sessione vale per ogni add-on. **Un non
  amministratore loggato può già oggi aprire HIRIS, `/config` compresa, con due chiamate WebSocket.**
  La pagina di sicurezza di HA: «assume che ogni utente sia fidato».
- **L'identità arriva e non si falsifica**: Core scrive `user_id` dalla connessione, il Supervisor
  aggiunge `X-Remote-User-Id/-Name/-Display-Name` e toglie quelli mandati dal client. **Il ruolo non
  arriva**: HIRIS lo legge da `config/auth/list` (il soffitto lo fa già; Marta → `system-users` →
  `utente`).
- **`frontend/update_panel`** (dalla 2026.3, PR #162742; `@websocket_api.require_admin`) scrive un
  override di `require_admin`/`show_in_sidebar`/`title`/`icon` per un pannello in un archivio di HA
  (`frontend_panels` in `.storage`), **separato dalla registrazione del pannello**: resiste a riavvii
  e aggiornamenti dell'add-on; `get_panels` lo applica per ogni utente; un valore `null` toglie
  l'override. Nessuna schermata di HA lo espone per i pannelli degli add-on.
- **Sulla casa**: il pannello si chiama `6354e165_hiris`, oggi `require_admin: True`,
  `show_in_sidebar: True`. HIRIS parla con HA con diritti di amministratore (legge `config/auth/list`).
- **Il buco di oggi, nel codice**: `PUT /api/models/config`, `PUT /api/chat-settings`,
  `POST /api/mind/objective`, `POST /api/usage/reset`, `PATCH` e `DELETE /api/memories/{id}` non
  chiedono il ruolo; `tests/test_soffitto_cancello.py` le classifica «esenti» sul presupposto — falso —
  che a `/config` arrivino solo amministratori.

**Misurati durante la costruzione** (27/09/2026, sorgente di Core 2026.9.3 e del Supervisor
2026.09.2; il commento datato sta accanto al codice che ne dipende):

- **Chi è amministratore** (`auth/models.py::User.is_admin`): `is_owner` **oppure** (`is_active` e
  gruppo `system-admin`). `config/auth/list` non restituisce `is_admin`: HIRIS lo ricava con la
  stessa regola (`proxy/ha_client.py::HAClient._user_row`). Prima contava solo il gruppo.
- **Sola lettura**: il gruppo `system-read-only` (`auth/const.py`) **senza** `system-users` — Core
  unisce le politiche dei gruppi (`auth/permissions/merge.py`), e chi è in entrambi comanda.
- **Senza gruppi**: un utente che non è il proprietario e non ha gruppi ha `merge_policies([])`,
  nessun permesso su nessuna entità.
- **Letture riservate** (`@websocket_api.require_admin`): `system_log/list`, `trace/list`,
  `trace/get`, `automation/config`, e `/api/config/<dominio>/config/<chiave>`
  (`components/config/view.py`). **Non** riservate: `script/config` e `repairs/list_issues`.
- **Servizi riservati del dominio `homeassistant`** (`components/homeassistant/__init__.py`):
  `stop`, `restart`, `check_config`, `reload_core_config`, `set_location`,
  `reload_custom_templates`, `reload_config_entry`, `reload_all` si registrano con
  `async_register_admin_service`; `turn_on`, `turn_off`, `toggle`, `update_entity` e
  `save_persistent_states` con `async_register`.
- **Lo slug dell'add-on**: `GET /addons/self/info` del Supervisor risolve l'add-on che chiama
  (`api/apps.py::get_app_for_request`); la risposta porta anche le opzioni dell'add-on, chiavi API
  comprese — il corpo non si scrive mai nel registro.

---

## §2 · L'opzione e la voce di menu

- **Opzione dell'add-on** `non_admin_access` (booleana, **spenta per difetto**), etichetta italiana
  «Consenti HIRIS agli utenti non amministratori», con descrizione. È l'**unica fonte** della scelta.
- **All'avvio** HIRIS: (1) chiede al Supervisor il proprio slug (mai scritto a mano); (2) chiama
  `frontend/update_panel` sul proprio pannello — opzione accesa `require_admin: false`, opzione spenta
  `require_admin: null` (toglie l'override: torna il predefinito di HA senza tracce); (3) rilegge
  `get_panels` e scrive nel registro lo stato vero della voce.
- **HA più vecchio della 2026.3** (comando sconosciuto): lo dice nel registro — la voce resta ai soli
  amministratori, l'accesso lo governa comunque HIRIS (§3). **Altri errori**: il motivo nel registro,
  nessun ritentare in loop. La sicurezza non dipende mai dal menu.

**Cambiato durante la costruzione** (Task 1, `hiris/app/panel_visibility.py`):

- **Il comando parte dopo che Home Assistant risponde**, non all'avvio nudo: il Supervisor avvia
  l'add-on prima del nucleo (`startup: services`), e un comando mandato allora fallirebbe a ogni
  riavvio della macchina. La sincronia gira in un compito a parte, aspetta che il WebSocket di
  HIRIS si autentichi (`HAClient.ws_ready`), manda **una** chiamata e rilegge lo stato; tutto sotto
  un tetto di `SYNC_CEILING_S = 600` secondi — scelto, non misurato — oltre il quale la voce resta
  com'era e lo si dice. Un Home Assistant che non risponde non tiene chiuso HIRIS.
- **Lo slug si valida** con `SLUG_SHAPE` (`[a-z0-9_]+`, con `fullmatch`: `$` accetterebbe un
  a-capo finale); uno slug di forma inattesa ferma il comando invece di viaggiare fino a HA.
- **L'opzione si legge stretta**: solo `true` apre (`parse_access_flag`); ogni forma inattesa resta
  chiusa. Si legge **una volta**, in `create_app`, in `app["non_admin_access"]`: cambiare
  l'ambiente a processo avviato non apre niente.
- **L'override vive in Home Assistant, non in HIRIS** (`.storage/frontend_panels`): resiste agli
  aggiornamenti e ai riavvii dell'add-on, e anche alla sua disinstallazione. Chi toglie HIRIS dopo
  averla accesa, la spegne e riavvia l'add-on prima, così l'override se ne va con `null`.

---

## §3 · Il cancello al confine

- **Dove**: nel middleware che stabilisce il soggetto (`api/middleware_internal_auth.py`), subito dopo
  aver riconosciuto una **persona arrivata dall'ingress**. Il ruolo si legge con la funzione del
  soffitto (una casa sola, cache 60 s).
- **Regola**: amministratore → passa. Non amministratore **o ruolo non leggibile** (nel dubbio si
  chiude) → con l'opzione spenta **rifiuto su tutto**; con l'opzione accesa passa **solo** ciò che è
  nella **lista di ammissione**, il resto è rifiutato.
- **La lista di ammissione** vive in un posto solo, scritta a mano perché *è* la decisione, ogni voce
  con la sua ragione: metodo + schema della rotta del router (niente prefissi larghi). Contiene ciò
  che servono la chat, le conversazioni, gli Impegni, la Memoria in lettura e i pallini, più i due
  gusci e gli asset della pagina. L'elenco esatto si ricava **leggendo cosa chiamano davvero** le pagine
  della chat, degli Impegni e della Memoria.
- **Il rifiuto**: rotte `/api` → JSON 403 con testo; gusci → una pagina semplice con il perché. Nel
  registro (livello info) lo schema della rotta e la chiave del soggetto, mai il nome.
- **Cosa non cambia**: servizi firmati (porta 8099, Retro Panel), ponte, sviluppo — le loro regole.
- **I cancelli esistenti restano** (`require_builder`, il soffitto su `confirm` e sulle `fai`, i fili):
  la lista dice **dove** si entra, i cancelli **cosa** si fa lì dentro.
- **Le sei rotte di §1** diventano riservate per costruzione (non sono in lista); il loro stato
  «esente» in `tests/test_soffitto_cancello.py` si riscrive con la ragione vera.

### §3.1 · La lista com'è stata costruita

La fonte unica è `hiris/app/api/admission.py::ADMISSION`: metodo, modello della rotta del router
(`resource.canonical`), ragione. Ogni voce viene da una chiamata vera delle pagine, lette il
27/09/2026 (`index.html` e `static/chat/*.js`, `pending-badge.js`, `build-check.js`,
`config/api.js`, e nel guscio `/config` `agenda-route.js` e `memory-route.js`). In sintesi:

| Metodo | Rotta | Perché |
|---|---|---|
| GET | `/`, `/config` | i due gusci |
| GET | `/static` | gli asset dei gusci, ammessi come **risorsa statica** (`StaticResource`), non come nome |
| GET | `/api/config` | il tema della pagina, chiesto da entrambi i gusci |
| GET | `/api/health` | connesso o no, e l'impronta del guscio per `build-check.js` — ridotta, vedi sotto |
| GET | `/api/pending` | i pallini, `can_build`, `can_configure` |
| GET | `/api/chat-settings` | nome dell'assistente e tetto dei turni — ridotta, vedi sotto |
| POST | `/api/chat` | il turno di chat; cosa si fa dentro lo decide il soffitto |
| GET | `/api/chat/reply/{job_id}` | la risposta di un turno servito dal ponte, nel suo filo |
| GET | `/api/chat/history` | la cronologia del suo filo |
| GET · POST | `/api/chat/conversations` | l'elenco delle sue conversazioni, una nuova |
| POST | `/api/chat/conversations/{id}/resume` | riprende una sua conversazione |
| DELETE | `/api/chat/conversations/{id}` | cancella una sua conversazione |
| GET | `/api/agenda` | i suoi Impegni |
| DELETE | `/api/agenda/{id}` | disdire una sua promessa |
| POST | `/api/agenda/read` | segnare letti gli esiti dei suoi Impegni |
| GET | `/api/executions/{id}` | l'esito di una sua promessa, o di un suo comando |
| GET | `/api/memories` | la pagina Memoria, in sola lettura |

`HEAD` passa solo dove passa `GET`. Il confronto è su metodo e modello della rotta **già risolta**
da aiohttp: mai il percorso, un prefisso o una regex. Una rotta che non esiste e una vietata
rispondono uguale.

**Cambiato durante la costruzione:**

- **Quattro testi di rifiuto, non due** (`admission.py`). Oltre ai due di §4: ruoli illeggibili —
  «Non ho potuto leggere i ruoli da Home Assistant: riprova tra poco.» (la sua pagina si ricarica
  da sé ogni sei secondi); persona che Home Assistant non riconosce, anonimi compresi — «Home
  Assistant non mi ha detto chi sei: HIRIS risponde solo agli utenti di Home Assistant che
  riconosce. Se sei appena stato aggiunto, riprova tra un minuto.». Nessun testo nomina la rotta,
  il ruolo o il soggetto.
- **Ruoli illeggibili chiudono tutti, amministratori compresi**, col loro testo: nel dubbio si
  chiude, e si dice perché. Un guasto appena visto vale per `GATE_FAILURE_HOLD_S = 5` secondi
  (dichiarato, non misurato) senza richiamare Home Assistant: altrimenti ogni asset della pagina
  sarebbe un `config/auth/list`. Alla richiesta dopo si riprova. Un ruolo letto vale 60 secondi
  (`RUOLI_VALIDI_S`): un utente promosso o degradato lo vede entro un minuto.
- **Un utente senza gruppi è rifiutato**, anche con l'opzione accesa: per Home Assistant non può
  niente (§1). Riceve il testo della pagina non concessa.
- **Il gruppo di sola lettura è `lettore`**: legge, non comanda, non costruisce. Un ruolo che non
  si è potuto leggere, per un turno servito dal ponte che arriva allo strumento, vale `lettore` e
  non più `utente`.
- **Il ruolo si legge una volta per richiesta**: il cancello lo lascia su `request["ruolo"]`, e chi
  viene dopo (salute, memorie, impostazioni, pallini, turno di chat) lo prende da lì
  (`soffitto.request_role`, `request_ceiling`, `restricted_person`) — nessuna seconda domanda a
  Home Assistant.
- **Il registro del rifiuto** (livello info) non scrive una riga per ogni asset di un guscio
  rifiutato: la prima dice già tutto.

### §3.2 · Dentro le porte ammesse

La lista dice dove si entra; il principio di `soffitto.py` vale anche lì dentro. **Cambiato durante
la costruzione** — la spec approvata non lo prevedeva, la review di sicurezza del Task 2 l'ha
trovato:

- **Un quarto gesto, `amministrare`** (`soffitto.GESTI`, `canali.PUO`): toccare ciò che Home
  Assistant riserva ai soli amministratori (§1). Solo `amministratore` lo ha.
- **Gli strumenti della chat seguono i diritti di Home Assistant**: `system_log` e
  `automation_trace` rifiutano per chi non amministra (`ADMIN_READS_REFUSAL`); `view` non mostra
  il corpo di un'automazione (si sa che c'è e come si chiama); l'anteprima di `propose` non
  descrive com'è adesso un'automazione o una scena («com'è adesso lo vedono solo gli
  amministratori»), gli script sì; `execute` del dominio `homeassistant` concede a chi non
  amministra solo `turn_on`, `turn_off`, `toggle`, `update_entity` (`ADMIN_SERVICES_REFUSAL`
  per il resto; `save_persistent_states` resta fuori per decisione).
- **I turni delle promesse portano il soffitto di chi le ha chieste**, riletto al risveglio
  (`keeper/exchange.py::promise_ceiling`), sulla strada sincrona e su quella del ponte: senza,
  l'orologio avrebbe letto per lei ciò che la chat le nega.
- **`GET /api/health`** a chi non amministra: solo `status`, `version`, `build`. **`GET
  /api/chat-settings`**: solo `name` e `max_chat_turns` (`handlers_settings.CHAT_PAGE_FIELDS`).
- **`GET /api/executions/{id}`**: un'esecuzione che nessuna promessa ha prodotto (un comando dato
  in chat) si mostra solo a chi l'ha fatta; per gli altri è un 404 come un id che non c'è.
- **Lo sviluppo** (`HIRIS_ALLOW_NO_TOKEN=1`, autenticazione spenta) non si restringe per ruolo:
  decide l'interruttore insieme alla specie `sviluppo`, non la specie da sola — una promessa nata in
  sviluppo che si sveglia in produzione non legge ciò che è riservato.

---

## §4 · Cosa vede chi non amministra

- **Memorie**: `GET /api/memories` (e la lettura di un singolo ricordo, se la pagina la usa) per una
  persona non amministratrice restituisce **solo i ricordi con `said_by` uguale alla sua chiave**;
  quelli senza autore non sono suoi. Correggere e cancellare non sono in lista. Per un amministratore
  niente cambia. La memoria usata in chat resta condivisa (decisione delle chat divise).
- **Pagine**: `GET /api/pending` porta, accanto a `can_build`, **`can_configure`** (vero solo per gli
  amministratori), con la stessa memoria locale del menu «Proposte» (il server resta il giudice). Con
  `can_configure` falso: nella chat spariscono il widget dei consumi e il link «Configurazione»; nel
  guscio `/config` il menu mostra solo **Impegni** e **Memoria** (senza pulsanti di correzione e
  cancellazione); una pagina aperta per indirizzo mostra il testo del rifiuto del server via
  `textContent`.
- **Testi** (da rivedere con l'ux-ui-specialist): opzione spenta — «HIRIS in questa casa è riservato
  agli amministratori: chiedi a chi lo gestisce di attivarlo per tutti.»; pagina non concessa —
  «Questa parte di HIRIS è riservata agli amministratori.»

**Cambiato durante la costruzione** (Task 3 e 4):

- **Il filtro delle memorie sta nell'archivio**, prima del taglio: `MemoryStore.fetch`/`count`
  con `said_by` nel `WHERE` (filtrati dopo, i suoi ricordi sparirebbero sotto quelli degli altri),
  e il `total` è il suo. La chiave è `subject_key_for`, la stessa che scrive `remember`. Una
  persona senza id non ha ricordi. La lettura di un singolo ricordo non serviva alla pagina e non
  è stata aggiunta.
- **`can_configure`** è vero dove il soffitto non nega `amministrare` (`soffitto.denies`): un
  amministratore, e lo sviluppo. In sviluppo quindi `can_configure` è vero mentre `can_build` è
  falso — incoerenza dichiarata (BACKLOG).
- **Il testo del rifiuto viaggia con `/api/pending`**: `configure_refusal`, presente solo quando
  `can_configure` è falso, porta la costante del cancello (`admission.NOT_ADMITTED`). La prima
  stesura lo chiedeva a una rotta negata, e lasciava nel registro del cancello una riga falsa.
- **Nel dubbio la pagina si chiude**: si configura solo col `true` detto dal server o ricordato
  dal browser (`localStorage["hiris.can_configure"]`, comodità e non permesso). La pagina
  d'atterraggio di chi non configura, e di chi non si sa, è **Impegni** (la home legge rotte a lui
  chiuse). Senza ricordo il guscio aspetta la prima risposta fino a 3 secondi (`ROUTER_WAIT_MS`)
  prima di scegliere; le voci di configurazione nascono nascoste e compaiono quando il server dice
  `true`. Una pagina di configurazione aperta per indirizzo non si monta e non chiede i suoi dati:
  mostra titolo, testo del server e un link agli Impegni.
- **Nella chat** il giro dei consumi parte solo quando `can_configure` diventa vero, e si ferma se
  torna falso: chi non configura non chiede mai `api/usage`.
- **I testi dei rifiuti** sono quelli del server, rivisti dal coordinatore; l'ux-ui-specialist ha
  rivisto le pagine dopo la costruzione e ha proposto per la pagina non concessa «…riservata a chi
  gestisce la casa in Home Assistant.» — decisione del proprietario, in BACKLOG.

---

## §5 · Come si prova

- Opzione: all'avvio con l'opzione accesa/spenta viene chiamato `frontend/update_panel` col valore
  giusto (e `null` per spenta); comando sconosciuto → registro chiaro, avvio che prosegue.
- Cancello: ogni voce della lista esiste nel router; per **ogni** rotta del router non in lista una
  persona non amministratrice riceve 403 (elenco ricavato dal router); opzione spenta → 403 anche
  sulle voci in lista; amministratore → passa ovunque; ruolo non leggibile → come non amministratore;
  una rotta aggiunta nasce chiusa (mutazione eseguita); servizi firmati e ponte invariati.
- Memorie: una persona non amministratrice vede solo le sue; `PATCH`/`DELETE` → 403; l'amministratore vede tutto.
- Pagine: con `can_configure` falso i link e i pulsanti spariscono; il rifiuto per indirizzo è testo.
- **Dal vivo**: opzione accesa → la voce HIRIS compare a una persona non amministratrice; lei
  chatta, vede i suoi Impegni e le sue memorie, non vede Modelli/Servizi/consumi, `/config/#/models`
  per indirizzo → rifiuto; opzione spenta → rifiutata anche forzando la sessione. **Non ancora
  fatta al 27/09/2026**: si fa sulla casa col rilascio.

**Come è stato provato** (Task 1-4): la lista si confronta col router **vivo**
(`create_app().router.routes()`), non con un elenco ricopiato — ogni voce esiste, ogni rotta fuori
lista dà 403 a una persona non amministratrice, e una rotta aggiunta nasce chiusa (mutazione
eseguita); l'amministratore passa su ogni rotta (confrontato con gli stati pinnati sul codice di
partenza); le sei rotte di §1 rispondono 403 con corpo e CSRF validi e l'archivio resta com'era;
servizi firmati, ponte, accoppiamento e sviluppo non chiedono mai i ruoli a Home Assistant.

---

## §6 · Cosa resta fuori

Ogni punto è una voce di `docs/BACKLOG.md` (sezione «In attesa»), con il fatto, perché resta fuori
e cosa lo chiuderebbe:

- la memoria in chat resta condivisa: chi non amministra può farsi dire ciò che altri hanno detto
  a HIRIS (rischio accettato dal proprietario);
- nessun tetto di spesa per persona;
- i servizi firmati: con ruolo `utente` scrivono ancora sulle rotte di configurazione, e con
  `utente` o `lettore` leggono tutte le memorie e tutte le impostazioni della chat (la lista e i
  filtri valgono solo per le persone dall'ingress);
- i servizi riservati agli amministratori di domini diversi da `homeassistant` con un bersaglio;
- in sviluppo `can_configure` vero e `can_build` falso;
- «ogni utente è fidato»: il cancello di HIRIS è l'unica protezione, e le porte degli altri
  add-on restano aperte;
- il ricordo di `can_configure` sullo stesso profilo del browser, fra un amministratore e chi viene
  dopo;
- la Memoria raggiungibile dalla chat solo passando dagli Impegni;
- il testo della pagina non concessa, da decidere;
- una risposta tardiva di `can_configure` dopo i 3 secondi rimonta la pagina aperta.
