# I comandi verso Home Assistant — cosa HIRIS non sa ancora fare

*Studio · 04/09/2026 · arretrato dello sprint prossimo*

> **Stato**: studio, non specifica. Dice **cosa** manca e **con quale chiamata**
> si colma; non dice come si presenta all'utente né in che ordine si fa. La
> specifica della fetta si scrive dopo, quando il proprietario avrà scelto il
> perimetro.

---

## §0 · Da dove viene

Dall'analisi di **[ha-mcp](https://github.com/homeassistant-ai/ha-mcp)** (MIT,
compatibile con HIRIS proprietario), un server MCP che espone Home Assistant a
un modello. Non è un concorrente — è un **attrezzo, non un agente**: nessuna
memoria, nessuno schedulatore, nessun osservatore, tutta l'intelligenza sta nel
client. Ma copre una superficie di scrittura verso HA molto più larga della
nostra, ed è da lì che viene questo elenco.

**Su un punto siamo avanti noi, e va detto prima di copiare qualunque cosa**:
`ha-mcp` non chiama **mai** `validate_config` — verificato per grep, quella
stringa non esiste nel suo sorgente. La prova a vuoto che HIRIS fa prima di ogni
proposta (`proxy/ha_client.py::validate_config`, comando WS con `triggers`/
`conditions`/`actions` separati) lì non c'è. Non è un dettaglio: è la differenza
fra un'anteprima verificata e un'anteprima sperata.

Siamo avanti anche su: l'anagrafe persistente (loro ricostruiscono dai registri
a ogni chiamata), comportamento/unità/classe come dimensioni di prima classe, i
piani dentro la topologia, e il fatto che **noi misuriamo i token e loro no, in
nessun punto**.

---

## §1 · Cosa HIRIS sa scrivere oggi

Misurato su `hiris/app/proxy/ha_client.py`:

| superficie | come | dove |
|---|---|---|
| automazioni, script, scene | `POST /api/config/{dominio}/config/{chiave}` | `save_configuration` |
| comandi | `POST /api/services/{dominio}/{servizio}` | `call_service` |
| validazione a vuoto | WS `validate_config` | `validate_config` |
| helper (8 tipi) | WS `{dominio}/create` · `/delete` | `create_helper` |
| etichette | WS `config/label_registry/list` · `create` | `list_labels`, `create_label` |
| registro entità | WS `config/entity_registry/update` | `add_label_to` |
| plance | **solo lettura** (`lovelace/dashboards/list`, `lovelace/config`) | `read_dashboards` |

La regola di fondo di `save_configuration` resta e non si tocca: **il file lo
scrive Home Assistant**, trovando la voce per `id` e sostituendola. HIRIS non
serializza YAML, e non deve iniziare — la ragione è misurata (una voce accodata
quattro volte in `automations.yaml`, nascosta dalle ancore YAML).

---

## §2 · L'arretrato, per costo crescente

Ogni voce porta la chiamata esatta. Sono state lette nel sorgente di ha-mcp, non
dedotte dalla documentazione di HA.

### 2.1 Le plance — il buco più grosso

Leggiamo le plance e non le scriviamo. Nel codice c'è perfino la lapide di un
`save_dashboard_config` scritto e poi tolto perché senza chiamanti.

- **Scrivere**: WS `lovelace/config/save` con `{url_path, config}` (`url_path`
  omesso per la predefinita).
- **Creare**: WS `lovelace/dashboards/create` con `{url_path, title,
  require_admin, show_in_sidebar, icon}`. L'id lo decide HA (`result.id`). Il
  percorso nuovo **deve contenere un trattino** — vincolo di HA.
- **Metadati**: WS `lovelace/dashboards/update` con `dashboard_id` e i soli
  campi cambiati. La predefinita `lovelace` **non ha id di storage** su
  installazioni fresche e non accetta l'update: caso a parte.
- **Cancellare**: WS `lovelace/dashboards/delete` con `dashboard_id`.

**Tre vincoli che non sono opzionali**, e vengono dai loro errori, non dalla
loro eleganza:

1. `config/save` è una **sostituzione totale**. Non esiste «aggiungi una card».
   Quindi: leggere (`lovelace/config` con `force: true`), calcolare un hash del
   JSON canonico (`sort_keys=True, separators=(",",":")`), riscrivere solo se
   l'hash regge. Senza lock ottimistico, due scritture vicine si mangiano a
   vicenda in silenzio.
2. **Le plance *strategy* non si convertono.** Se il corpo letto ha la chiave
   `strategy` e quello nuovo no, **rifiutare**: la conversione si fa dalla UI
   con «Take Control», e farla da qui distrugge una plancia generata.
3. **Il corpo si legge SOLO se `mode == "storage"`**, fail-closed anche sulle
   righe non taggate. Il corpo di una plancia YAML può contenere valori
   `!secret` **già risolti in chiaro**. Questo è un requisito di sicurezza, non
   un'ottimizzazione, e vale anche solo per leggere.

**Il problema aperto**: far riscrivere al modello 40 KB di plancia per
aggiungere una card è assurdo. La loro soluzione è far mandare al modello
un'**espressione Python** che muta il dict letto, eseguita in sandbox. Per noi
quella strada apre un fronte di sicurezza che non vogliamo aprire adesso
(vedi [la fetta sicurezza](#4--cosa-non-entra-in-questa-fetta)); l'alternativa
è comporre la mutazione dai **parametri**, come già facciamo per le
automazioni. Va progettata, non copiata.

### 2.2 Le categorie — organizzare ciò che HIRIS scrive

Oggi HIRIS crea automazioni e non ha modo di ordinarle. Le categorie sono
**per dominio** (a differenza delle etichette, trasversali).

- WS `config/category_registry/create` con `{scope: "automation", name, icon}`.
- Assegnazione: WS `config/entity_registry/update` con
  `{entity_id, categories: {scope: category_id}}`.
- **La guardia**: ri-verificare che la categoria esista **immediatamente prima**
  della scrittura. HA non la valida, e una categoria cancellata nel frattempo
  resta appesa.

### 2.3 Etichette: aggiornare e cancellare

Oggi solo `list` e `create`.

- WS `config/label_registry/update` con `{label_id, name, color, icon, description}`.
- WS `config/label_registry/delete` con `{label_id}`.
- **La guardia**: verificare l'esistenza prima. Un update con id ignoto torna un
  opaco «Unknown error» che non dice niente a nessuno.

### 2.4 Aree e piani in scrittura

Oggi li leggiamo soltanto.

- WS `config/area_registry/create` · `/update` con `{name, floor_id, icon, aliases, picture}`.
- WS `config/floor_registry/create` · `/update` con `{name, level, icon, aliases}`.

### 2.5 Zone

- WS `zone/create` con `{name, latitude, longitude, radius, passive, icon}`
  (`radius` default 100).
- WS `zone/update` con `zone_id` · `zone/delete`.
- **La trappola**: `zone/list` serve **solo** la collezione di storage, quindi
  le zone YAML — `home` compresa, che HA sintetizza da sola — sono
  strutturalmente assenti. Il discriminante affidabile è `editable: False` nel
  corpo da attributi di stato.

### 2.6 Calendari, incluse le ricorrenze

Due cose che **non si fanno con un servizio**, e vanno sapute:

- il servizio `calendar.create_event` **non ha `rrule`**: un evento ricorrente
  si crea con WS `calendar/event/create` e
  `{entity_id, event: {summary, dtstart, dtend, rrule, description, location}}`;
- **`calendar.delete_event` non esiste**: si cancella con WS
  `calendar/event/delete` e `{entity_id, uid, recurrence_id, recurrence_range}`.

### 2.7 Gruppi e liste

- Gruppi: **non** è WS né config — è un servizio.
  `POST /api/services/group/set` con
  `{object_id, entities | add_entities | remove_entities, name, icon, all}`;
  `group.remove` per cancellare.
- Todo: servizi `todo.add_item` / `update_item` / `remove_item`; la lettura è
  WS `todo/item/list`.

### 2.8 Gli helper a config-flow — il secondo buco per dimensione

I nostri 8 `HELPER_DOMAINS` sono le *storage collection*. I 17 tipi che valgono
davvero — `template`, `group`, `utility_meter`, `derivative`, `min_max`,
`threshold`, `integration`, `statistics`, `trend`, `filter`, `tod`,
`history_stats`, `switch_as_x`, `generic_thermostat`, `generic_hygrostat`,
`random`, `mold_indicator` — **non si creano con una POST**. Si creano
camminando un config flow:

1. `POST /api/config/config_entries/flow` con `{"handler": "template"}`;
2. `POST /api/config/config_entries/flow/{flow_id}` con lo `user_input` di ogni
   passo (i menu vanno scelti);
3. `DELETE /api/config/config_entries/flow/{flow_id}` per abortire su errore.

**La regola da copiare parola per parola**: il POST di un passo **non si ritenta
mai**. HA consuma il `flow_id` al successo, e un replay torna un 404 che
nasconde una prima esecuzione già andata a buon fine.

Un `template` sensor creato così è la cosa che oggi manca di più a un assistente
che ragiona sulla casa: è il modo di far *nascere* una grandezza che non esiste.

### 2.9 Blueprint

- WS `blueprint/import` con `{url}` per scaricare.
- WS `blueprint/save` con `{domain, path, yaml, source_url}` (+ `allow_override`
  solo per sovrascrivere: lo schema rifiuta le chiavi ignote).

Permetterebbe di **proporre un blueprint** invece di generare la ventesima
automazione a mano.

### 2.10 Cose piccole che chiudono asimmetrie

- **Servizi che rispondono**: `POST /api/services/{d}/{s}?return_response=true`.
  La risposta va restituita **una sola volta**, come chiave di primo livello,
  mai annidata nel risultato.
- **Reload mirato** invece del riavvio: `POST /api/services/{dominio}/reload`
  per `automation`, `script`, `scene`, `group`, `template`, `person`, `zone`,
  ogni `input_*`, `timer`; `homeassistant.reload_core_config` per il core.
- **Esposizione alla voce**: WS `homeassistant/expose_entity` con
  `{assistants, entity_ids, should_expose}`.

---

## §3 · Tre modi di fare, non tre chiamate

Sono la parte che vale più delle chiamate.

### 3.1 L'errore di HA resta intero, e sopra ci si appoggia

Loro non riscrivono mai il messaggio di Home Assistant: lo passano **verbatim** e
gli **anteponogono** un suggerimento mirato, scelto per pattern sul testo.
`'service' ... not allowed` → «usa `action:` non `service:`, rinominato in HA
2024.8». `unexpected keyword argument` → «un passo d'azione contiene un campo che
appartiene alla radice».

HIRIS già lascia passare il testo di HA (`save_configuration` non solleva sul
rifiuto apposta, perché quella frase è il validatore vero che parla al modello).
Manca lo strato sopra: la traduzione che si **aggiunge** senza sostituire.

### 3.2 Fallire chiuso quando due bersagli si sovrappongono

Il loro `bulk_control` **non dispaccia niente** se un lotto mira a un gruppo *e*
a un suo membro. La ragione è sostanziale: HA applica l'azione a **tutti** i
membri quando il gruppo è mirato, quindi una riga «membro» non può escludere
quel membro. È una trappola che N chiamate indipendenti non vedono mai.

Il nostro `execute` risolve già aree, piani, etichette e dispositivi lasciando
fare a HA — quindi lo stesso scontro è possibile e oggi non è controllato.

### 3.3 Registrare l'attesa PRIMA di spedire

Il loro registro delle operazioni asincrone scrive l'operazione **prima** della
chiamata di servizio, perché un'entità veloce farebbe altrimenti arrivare
`state_changed` nella finestra fra il ritorno della chiamata e la registrazione.
È lo stesso genere di ordine che il nostro `actuator` già cura leggendo
*prima*; vale rileggerlo con quest'occhio.

---

## §4 · Cosa NON entra in questa fetta

**La sicurezza.** È stata dichiarata sprint a sé, e viene **dopo** questo
(decisione del proprietario, 04/09). Qui si aggiungono comandi; là si decide chi
può darli e con quali difese.

Il reperto che quello sprint eredita, trovato leggendo il nostro codice mentre si
scriveva questo studio: **HIRIS non ha nessuna lista di servizi vietati.** Ciò
che oggi rende irraggiungibili `homeassistant.restart`, `hassio.host_reboot`,
`recorder.purge`, `shell_command.*` è un **accidente di forma** — quei servizi
non dichiarano un `target`, e un bersaglio vuoto è sempre stato un rifiuto.
`action/verification.py` lo dichiara per intero, dentro un commento che
**contempla di allargare quella regola** appena ci sarà la misura:

> «servizi di sistema oggi DI FATTO irraggiungibili, perche' un bersaglio vuoto
> era sempre un rifiuto e **non esiste nessuna lista nera che li fermi
> altrimenti**»

La difesa non è progettata: è incidentale, e cade tutta insieme il giorno in cui
quella condizione si allarga. **Ogni comando aggiunto da questo studio allarga la
superficie prima che quella decisione sia stata presa** — ed è la ragione per cui
l'ordine dei due sprint va rispettato, o si arriva alla sicurezza con più
superficie da difendere di quanta se ne avesse cominciando.

Non entrano nemmeno, e per la stessa ragione: la **sandbox Python** per mutare le
plance, e qualunque via di fuga che permetta al modello di mandare un comando WS
arbitrario.
