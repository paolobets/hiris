# HIRIS per chi non amministra — un'opzione, un cancello al confine

`spec · 27/09/2026 · decisioni del proprietario prese in chat il 27/09/2026, disegno approvato a sezioni`

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

---

## §5 · Come si prova

- Opzione: all'avvio con l'opzione accesa/spenta viene chiamato `frontend/update_panel` col valore
  giusto (e `null` per spenta); comando sconosciuto → registro chiaro, avvio che prosegue.
- Cancello: ogni voce della lista esiste nel router; per **ogni** rotta del router non in lista una
  persona non amministratrice riceve 403 (elenco ricavato dal router); opzione spenta → 403 anche
  sulle voci in lista; amministratore → passa ovunque; ruolo non leggibile → come non amministratore;
  una rotta aggiunta nasce chiusa (mutazione eseguita); servizi firmati e ponte invariati.
- Memorie: Marta vede solo le sue; `PATCH`/`DELETE` → 403; l'amministratore vede tutto.
- Pagine: con `can_configure` falso i link e i pulsanti spariscono; il rifiuto per indirizzo è testo.
- **Dal vivo**: opzione accesa → la voce HIRIS compare a Marta; Marta chatta, vede i suoi Impegni e le
  sue memorie, non vede Modelli/Servizi/consumi, `/config/#/models` per indirizzo → rifiuto; opzione
  spenta → Marta rifiutata anche forzando la sessione.
