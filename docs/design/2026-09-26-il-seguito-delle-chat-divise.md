# Il seguito delle chat divise — promesse, chi costruisce, conversazioni

`spec · 26/09/2026 · decisioni del proprietario prese in chat il 25-26/09/2026, disegno approvato a sezioni`

Chiude quattro voci che la fetta «le chat divise» (`docs/design/2026-09-25-le-chat-divise.md`) aveva
dichiarato fuori: chi ha chiesto una promessa · il cancello delle costruzioni · i testi che assumono
un proprietario unico (con l'autore del giudizio) · più conversazioni per filo. Restano fuori, apposta:
la cache di «Chi ti sta parlando» (si misura prima) e il filo condiviso dagli anonimi (Home Assistant
non dà l'identità: si può solo dichiarare, ed è dichiarato).

Nomi: identificatori in inglese (cancello `tests/test_preposizioni_italiane.py`), prosa e valori di
dominio in italiano; colonne nuove in inglese, gli stessi nomi del filo ovunque (`subject_key`,
`entry_point`). Il filo è `hiris/app/chat_thread.py::ChatThread`.

---

## §0 · Le decisioni del proprietario

| # | Domanda | Decisione |
|---|---|---|
| 1 | Di chi è una promessa | **Di chi l'ha chiesta**, come la chat: `agenda`, `cancel`, la pagina Impegni e il badge vedono e toccano solo il proprio filo |
| 2 | Dove torna l'esito | **Nel filo di chi l'ha chiesta**, come messaggio di HIRIS, **più una push al suo recapito** — mai più scelto dal modello |
| 3 | Chi non ha una strada per essere avvisato | **Ogni soggetto ha la sua strada** (persona → i suoi dispositivi; Retro Panel → il suo gestore di notifiche, quando si accoppierà). **Se non c'è, il sistema lo segnala** |
| 4 | Quali dispositivi di una persona | **Quelli della sua `person` in HA** (dato ufficiale). Chi vuole meno push toglie un dispositivo dalla persona in HA |
| 5 | La pagina Costruzioni | **È di chi costruisce**: gli amministratori vedono tutte le proposte con chi le ha chieste; gli altri non la vedono |
| 6 | I giudizi (correzioni al sapere) | **Di chi amministra**, con l'autore vero |
| 7 | Quando nasce una conversazione | **Da sola dopo 2 ore di silenzio, e col pulsante «Nuova conversazione»** |
| 8 | Una conversazione vecchia | **Si riprende**: torna quella attiva |
| 9 | Il cestino | **Cancella la conversazione aperta**; niente «cancella tutte» |

---

## §1 · I fatti (misurati il 25/09/2026)

**Sul codice** (ramo `master` locale, `c3225aa5`):
- `promesse` (`keeper/store.py:33-56`) non ha colonna per chi ha chiesto. `promise` (`home_space/tools.py:838-901`, gestore `_promise` :2504-2575) riceve `recapito` dal **modello** («es. notify.mobile_app_x», da trovare con `search`) e non passa soggetto né filo, pur avendoli nel dispatcher.
- `agenda`/`cancel` (tools.py:2604-2619) e le rotte `GET/DELETE /api/agenda`, `POST /api/agenda/read` (`api/handlers_agenda.py`) non filtrano: **chiunque vede e disdice le promesse di chiunque**. Il badge `agenda_unread` (`api/handlers_pending.py`) è della casa. Il limite di 50 pendenti è della casa (store.py:159-167).
- L'esito di un `chiedi` parte come push su `recapito` (`keeper/sweeper.py:107-156`, `promise.delivery_call`); nella chat non entra niente. Il job del ponte (`keeper/exchange.py::_enqueue_to_bridge`) si accoda **senza** `thread=`.
- `GET /api/constructions[/{id}]`, `reject`, `/api/proposals/{id}/reject|done|redo` e `POST /api/mind/judgment` **non hanno cancello**; solo `_act` (conferma/ripristino) chiede `costruire`. `GET /api/pending` conta le proposte per tutti.
- `JUDGMENT_AUTHOR = "proprietario"` (`mind/judgments.py:50`) è l'unico autore di `write_judgment`; la pagina lo mostra come «Le tue correzioni» (`static/config/watcher-sapere.js`).
- Testi che assumono un proprietario/utente unico: `agent/prompts.py:412` (`DICHIARAZIONE_CASA`, «RIFERISCILA al proprietario»), `:470`; `claude_runner.py` `BASE_IDENTITY`/`BASE_TOOL_RULES` («l'utente», :240, :297, :327, :333, :343); descrizioni degli strumenti in `home_space/tools.py` («l'utente»); `home_space/briefing.py:1977`; `action/construction/workshop.py:1027`; `mind/observer.py:67`, `mind/actuator_turn.py:64`, `api/handlers_proposals.py:42-43,148,153` («il proprietario»); `action/construction/revisions.py:362` `motivo="rifiutata dal proprietario"`, confrontato alla lettera da `static/config/constructions-route.js:109,609`.
- Conversazioni: `chat_sessions` ha già id, date, riassunto e filo; la sessione attiva è la più recente aperta del filo, chiusa dopo `SESSION_GAP_HOURS=2`; nessuna rotta sceglie una sessione. `#session-ended-msg` («Sessione completata — avvia una nuova conversazione») non ha nessuna azione dietro.

**Su Home Assistant vero** (192.168.1.95, 25/09/2026):
- `person.paolo_bettinelli`: `user_id` presente; `device_trackers` = `iphone_bet`, `ipad_mini`, `iphone_bet_apple_watch`, tutti piattaforma `mobile_app`, ciascuno con un dispositivo nel registro.
- `person.marta`: **`user_id` vuoto** (l'utente «Marta consoli» esiste ma la persona non è collegata); tracker `iphone_di_marta`.
- Servizi notify: `mobile_app_iphone_bet`, `mobile_app_ipad_mini`, `mobile_app_iphone_di_marta`, `mobile_app_nbbet_001` — il nome segue il nome del dispositivo; il Watch non ne ha uno.
- Quale utente ha registrato un dispositivo dell'app **non** è esposto da REST né da WebSocket (`config_entries/get` dà solo il titolo): sta nei file interni `.storage`. Non si usa (decisione 4).
- **Da verificare in implementazione, sulla documentazione ufficiale di HA** prima di scriverlo nel codice: come si forma il nome `notify.mobile_app_<dispositivo>` (slug del nome del dispositivo) e se esiste una via ufficiale dal dispositivo al servizio notify.

---

## §2 · Le promesse sono di chi le chiede

- **Dato.** `promesse` guadagna `subject_key`, `entry_point` (migrazione con `ALTER TABLE` protetto da `PRAGMA table_info`; nessun indice nello script di schema, che `storage.init_schema` esegue prima delle migrazioni). `serializza`/`_CHIAVI` (`keeper/promise.py`) portano `thread` come `ChatThread | None`, **la stessa forma** della coda e delle costruzioni; le risposte HTTP non lo espongono.
- **Nascita.** `_promise` scrive il filo del dispatcher. Il parametro `recapito` **esce** dallo schema dello strumento (un comportamento solo; un `recapito` mandato comunque viene rifiutato da `_bad_arguments`, come `detto_da`). Se il soggetto non ha una strada (§2.3), il risultato di `promise` lo dice con un testo leggibile che il modello riferisce («te lo dico qui in chat: non so qual è il tuo telefono; collega la tua persona al tuo utente in Home Assistant»).
- **Chi vede e chi tocca.** `agenda`, `cancel`, `GET/DELETE /api/agenda`, `POST /api/agenda/read`, `GET /api/executions/{id}` (se legato a una promessa) e il conteggio `agenda_unread` lavorano **solo sul filo di chi chiede**; un id di un altro filo risponde come uno inesistente. Il tetto delle 50 pendenti è per filo.
- **Orfane.** Le promesse senza filo (nate prima) si adottano col proprietario, **nello stesso momento e con la stessa regola** della cronologia (`chat_thread.adopt_if_owner`: persona proprietaria, ingresso `pannello`, una volta).

### §2.3 · Il recapito del soggetto

Un punto solo, `hiris/app/keeper/recipient.py::recipients_for(subject, ha) -> Recipients`, che risponde **per genere**:
- **persona**: utente HA (`subject["id"]`) → la `person` con quel `user_id` (dagli stati) → i suoi `device_trackers` con piattaforma `mobile_app` (registro entità) → il dispositivo (registro dispositivi) → il servizio `notify.mobile_app_<…>` di quel dispositivo, **solo se esiste davvero** fra i servizi notify. Il Watch cade da sé.
- **luogo / integrazione** (servizi firmati, Retro Panel): nessuna strada **oggi** — «il servizio non ha ancora dichiarato come si avvisa»; la strada arriverà con l'accoppiamento di Retro Panel (BACKLOG).
- **nessuno / anonimo**: nessuna strada.
Il risultato porta i servizi trovati **e il motivo** quando sono zero (fondamenta 1: si interpreta da solo).

### §2.4 · L'esito

- Il recapito si risolve **al risveglio**, non alla nascita: se nel frattempo la persona è stata collegata, funziona già.
- L'esito di un `chiedi` (e il racconto di un `fai` concluso) diventa **un messaggio `assistant` nel filo di chi ha chiesto** (`chat_store.append_messages(..., thread=)`), nella conversazione attiva di quel filo, preceduto da una riga che dice che è l'esito di una promessa (la frase originale).
- La push va a ogni servizio del recapito; se sono zero si registra il motivo (come oggi `_SENZA_RECAPITO`).
- Il job del ponte si accoda col filo (`reasoning_queue.enqueue("promessa", …, thread=)`); il turno resta in sola lettura (`SOLA_LETTURA`) e la cronaca lo attribuisce a chi l'ha chiesta.

---

## §3 · Chi costruisce, chi corregge, e i testi

- **Un cancello solo**: in `api/soffitto.py`, una funzione che risponde `403` con il motivo del soffitto quando manca `costruire`. La usano `GET /api/constructions`, `GET /api/constructions/{id}`, `POST …/reject`, `/api/proposals/{id}/reject|done|redo`, `POST /api/mind/judgment`, e `_act` passa alla stessa funzione (una regola, non due).
- **La pagina Costruzioni**, per chi costruisce: ogni proposta mostra **chi l'ha chiesta** (nome leggibile, non la chiave). Per chi non costruisce: la voce «Proposte» sparisce dal menu (lo decide la risposta del server, non un ruolo indovinato dal browser) e `GET /api/pending` conta zero proposte.
- **I giudizi**: `write_judgment(…, subject)` registra autore (nome) e `said_by` (chiave), come i ricordi. `JUDGMENT_AUTHOR` esce. I giudizi già scritti restano «proprietario» (per loro è vero). La pagina: «Le tue correzioni» → «Correzioni», con chi.
- **I testi**: «l'utente» → «chi ti sta parlando» nei prompt e nelle descrizioni degli strumenti; `DICHIARAZIONE_CASA`: la segnalazione va a chi ti sta parlando, le decisioni restano a chi amministra la casa; osservatore/attuatore/«Rifalla»: «il proprietario» → «chi amministra la casa»; `motivo` di rifiuto → una costante sola «rifiutata dalla pagina», letta anche dalla pagina. Il prefisso statico in cache resta statico (si cambia testo, non si aggiunge niente per turno).

---

## §4 · Più conversazioni nel filo

- **Dato**: nessuna tabella nuova. Una conversazione è una sessione di `chat_sessions`. Il **titolo non si salva**: è la prima frase dell'utente nella sessione, letta quando serve. Una sessione nasce solo quando si scrive.
- **Archivio** (`chat_store`), tutto limitato al filo (un id altrui = inesistente):
  `list_conversations(thread)` → id, titolo, `last_msg_at`, attiva sì/no ·
  `new_conversation(thread)` → chiude quella aperta col riassunto ·
  `resume(thread, session_id)` → chiude quella aperta, riapre questa (il riassunto si azzera: si rifarà alla chiusura), `last_msg_at` = adesso ·
  `delete_conversation(thread, session_id)`.
  La chiusura dopo 2 ore di silenzio resta com'è.
- **Rotte**: `GET /api/chat/conversations` · `POST /api/chat/conversations` · `POST /api/chat/conversations/{id}/resume` · `DELETE /api/chat/conversations/{id}`. `GET /api/chat/history` resta (la conversazione attiva). `DELETE /api/chat/history` **esce**. Tutte rispondono `409` se nel filo c'è una risposta in arrivo (`has_pending_chat(thread)`).
- **Contesto del modello**: invariato — la conversazione attiva più i riassunti delle ultime tre chiuse del filo.
- **Pagina** (con `ux-ui-specialist`, 25/09/2026):
  - nella barra laterale, dopo Impegni/Proposte: **«Nuova conversazione»**, poi l'**elenco** (titolo con ellissi in CSS, data relativa oggi/ieri/gg-mm in `--text-3`; voce attiva con `.active` **e** `aria-current="true"`; voci come `<button>`; contenitore con scroll proprio `overflow-y:auto; min-height:0` fra `#sidebar-nav` e `#sidebar-footer`; riuso di `.sb-nav-item`, `hiris-chat.css:69-81`);
  - su telefono la barra è già un cassetto: il tocco su una voce lo chiude (`sidebar.js`) e il fuoco va a `#input`;
  - elenco vuoto: «Le tue conversazioni con HIRIS compariranno qui.»;
  - il cestino dell'header cancella la conversazione aperta; conferma: «Perdi i messaggi di questa conversazione e il suo riassunto. Le tue altre conversazioni restano, in elenco qui a fianco.\nI ricordi non si toccano: restano finché non li cancelli tu, uno per uno, dalla pagina Memoria.\nNon si può annullare.\n\nCancellare questa conversazione?»;
  - `#session-ended-msg` e il testo gemello in `send.js`: «Hai raggiunto il limite di messaggi per questa conversazione. Avviane una nuova dalla barra laterale.»

---

## §5 · Come si prova

- Promesse: Paolo non vede né disdice quelle di Marta (strumenti e rotte); il badge conta solo le proprie; un `recapito` dal modello è rifiutato; il recapito di una persona collegata sono i suoi `notify.mobile_app_*` esistenti (Watch escluso); una persona non collegata → zero servizi con motivo, e il risultato di `promise` lo dice; l'esito entra nel filo di chi ha chiesto e non in altri; le orfane passano al proprietario.
- Cancello: un non amministratore riceve 403 su tutte le rotte di §3 e zero proposte da `/api/pending`; un amministratore vede chi ha chiesto; `POST /api/mind/judgment` registra l'autore vero.
- Testi: nessun «proprietario»/«l'utente» residuo nei prompt elencati in §1 (grep pinnato da un test); il prefisso in cache non cambia fra due turni.
- Conversazioni: nuova/riprendi/cancella per id limitati al filo; 409 con risposta in arrivo; il contesto dopo una ripresa contiene i messaggi della ripresa.
- Dal vivo (casa vera, porta 8099): una promessa di Paolo arriva come push sull'iPhone e come messaggio nella sua chat; una di Marta (persona non collegata) lo dichiara; un non admin non vede Proposte; l'elenco delle conversazioni sul telefono.
