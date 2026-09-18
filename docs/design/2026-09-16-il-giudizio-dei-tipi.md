# Il giudizio dei tipi — dal letterale al sapere, e il genere con lui

`spec · 16/09/2026 · chiude §8 e §13 di docs/design/2026-09-10-i-tre-attori.md`

Questa spec e' la **meta' 1** dello sprint dichiarato il 16/09/2026 (commit `0ad64b8d`): il
vocabolario dei tipi come **seme** del sapere e il **genere dal sapere** invece che dalla gamba.
Ogni decisione qui sotto e' stata presa dal proprietario il 16/09/2026, una domanda alla volta, e
ogni numero e' stato misurato quel giorno sul repository alla `3.48.1` o sulla casa vera. Dove un
numero **non** e' misurato, lo si dice.

---

## §0 · Le decisioni, e chi le ha prese

| # | Domanda | Decisione del proprietario |
|---|---|---|
| 1 | Dove passa il confine fra il codice che chiede e l'archivio che risponde | **Istantanea immutabile** costruita dal sapere; i lettori la ricevono (disegno «C») |
| 2 | Quando vale una correzione della casa | **Subito**: la porta di scrittura ricostruisce l'istantanea |
| 3 | Cosa diventa sapere | **Solo i giudizi nostri**; i fatti copiati dal sorgente di HA restano codice |
| 4 | Una correzione rifa' i giorni passati? | **Impronta nel resoconto** + **solo la cronaca** rifatta, dentro i 22 giorni di grezzo |
| 5 | Genere per tipo o per entita' | **Per entita', coppia e dominio**; in questa fetta scrive **solo il proprietario** |
| 6 | Genere per stato (`lock=jammed`) | **Non si costruisce**; resta aggiungibile come campo separato |
| 7 | Da dove si scrive | **Rotta + sezione 04 della pagina dell'osservatore** |
| 8 | Il genere `presenza` di un sensore | **Una regola sola**: l'episodio e' il soggetto fuori dal suo riposo, e il riposo e' del tipo |
| D1 | `attributi_assumibili` (intrecciato con la metrica importata `capability_attributes`) | **Resta codice**, come `capability_attributes_dropped`: niente ricarica della `EntityCache`; `entity_cache` e `actuator` non ricevono l'istantanea |
| D2 | Il genere `energia` (e `bilancio`) | Il seme scrive **solo i generi con una forma** — `presenza`, `funzionamento`, `sicurezza`: **26 righe**. `energia` e `bilancio` **non sono sceglibili** finche' non hanno una forma (§5) |
| D3 | Come arriva l'istantanea ai lettori profondi | **Keyword `judgments=` con predefinito del solo seme** (`REPO_JUDGMENTS`) + **prova strutturale** su `hiris/app` che boccia ogni chiamata di produzione senza `judgments=` (mutazione eseguita) |
| D4 | La tabella dei lettori | **Corretta** (§3): `action/verification` e `home_space/topology` usano solo fatti di HA e non ricevono l'istantanea |

Le decisioni D1–D4 sono del 16/09/2026, prese dopo la scrittura del piano, che le aveva trovate
leggendo il codice.

I due disegni che la voce di backlog proponeva sono stati confrontati e scartati per ragioni
misurate: «spostare i lettori» sull'archivio mette letture SQLite nel percorso caldo; «il modulo
come confine» rompe il contratto scritto del modulo (*«un vocabolario che leggesse la rete
congelerebbe all'import un dato che e' di adesso»*) e riapre lo stato condiviso caricato
pigramente, che qui esiste gia' nell'ordine d'avvio (§1, misura 5).

---

## §1 · Le misure

1. **Le 76 righe sono 186 celle su 12 campi** (eseguito sul vocabolario): `aspect` 42, `state_attributes`
   30, `notable` 23, `capability_names` 22, `capability_attributes` 16, `resting_states` 16,
   `operable` 13, `parameter_limits` 10, `working_states` 9, `assumable_attributes` 2,
   `capability_attributes_dropped` 2, `aspect_guard` 1. **68 celle sono `importato`**, 118 `nostro`.
2. **I lettori veri sono 7 moduli e usano 17 porte**: `action/verification`, `home_space/briefing`,
   `home_space/queries`, `home_space/topology`, `home_space/type_census`, `mind/facts`,
   `proxy/entity_cache`. La voce di backlog ne elencava 7 diversi (con `action/registry`, che cita
   soltanto, e senza `proxy/entity_cache`) e 11 porte.
3. **Il genere e' una tabella per tipo** (eseguito `genre_for` su tutte le 76 righe): presenza 2
   (`person`, `device_tracker`), funzionamento 12, sicurezza 12 (compresa `siren`), energia 4,
   nessuno 46. Delle 43 celle di gamba e guardia **26 non influiscono su niente**. La guardia del
   `device_tracker` non cambia il genere: un tracker `router` e' `presenza` come uno `gps`.
4. **L'osservatore sceglie soggetti che la cronaca ignora.** Dei 151 soggetti guardati: 3 sensori
   di presenza, 4 `binary_sensor` dell'irrigazione, 10 `input_boolean`, 6 `button`, 3
   `automation`, `weather` non hanno genere. Il 15/09, dopo le 12:13 (inizio della guardia), la
   storia di HA porta 32 righe su `fp300` e 50 su `fp2`; la cronaca del giorno (46 episodi) ne
   porta **zero**.
5. **L'ordine d'avvio**: `EntityCache` si carica a `server.py:2862` e usa 4 porte del vocabolario;
   il sapere nasce a `server.py:2922`.
6. **Oggi sui tipi scrive solo il seme**: 241 righe di sapere in casa; sui tipi 177 `significato`
   `importato` e 3 `attributi`. Chi scrive di suo (il turno delle ricette) scrive sui dispositivi.
7. **Riposo del tipo contro riposo unito** (`_is_on` usa l'unione): ripassate 52.123 righe di
   storia di HA su 304 entita' dei tipi con genere, 09/09–16/09: **0 righe cambiano**.
8. **`none` non e' un riposo**: nella stessa settimana 200 righe `none` da **6 apparati di rete**
   (`device_tracker.switch_2` e `switch.switch_accesso_a_internet_2` 82 ciascuno, i `skyq` il
   resto), quasi tutte intorno alle 23.
   **Corretta il 17/09/2026 dalla revisione a 360 gradi: «quasi tutte intorno alle 23» e' falso.**
   Rimisurato sul recorder (`/api/history/period`, 6 apparati, 10/09-17/09, finestra ridotta dalla
   potatura): **186 righe**, di cui **28 (15%)** alle 23 UTC -- l'una di notte locale -- e le altre
   sparse fra le 9 e le 19 locali. Cambiano anche i totali per apparato (79 e 79 invece di 82 e 82,
   7 per ciascuno dei quattro `skyq`): la finestra di allora non e' piu' riproducibile, quindi le
   due misure non si sovrappongono. **Cio' che la misura doveva dimostrare resta vero**: `none`
   arriva a centinaia in una settimana da apparati di rete, e oggi apre e chiude episodi.
   Oggi su un `device_tracker` `none` **apre un'assenza**
   (non e' `home`); su uno `switch` **chiude** un episodio (e' nell'unione dei riposi).
9. **Il genere `presenza` oggi e' l'ASSENZA di una persona**: i 5 episodi del 15/09 sono tutti
   `not_home`; `home` e' scritto a mano in `mind/facts.py` (ramo della presenza) e **non** e' nel
   vocabolario (`resting_states_of("person")` vale `['', 'none']`).
10. **La cronaca e le misure si separano gia'**: in `aggregate_day` gli episodi nascono solo da
    `store.readings` e `store.last_before`; le misure arrivano dal chiamante (`recipes`, `series`,
    `names`) e si incontrano in `build_report`, che e' pura.
11. **Il ritmo del recupero**: `_recupero_resoconti` gira ogni **5 minuti** (`server.py`, job con
    `minutes=5`), un giorno per giro, dal piu' vecchio.
12. **Quanto dura un giorno** — **misura sintetica, non della casa**: `aggregate_day` senza misure
    su un archivio locale con 17.519 righe (il volume del 15/09) e 1.755 episodi: **0,68–0,74 s** su
    un PC di sviluppo, cinque ripetizioni. L'host di HA non e' misurato; la fetta scrive la durata
    vera nel log di ogni giorno rifatto (§6).
    **Stato al 17/09/2026 (Task 10):** la riga di log **esiste** ed e' implementata
    (`server.py::_recupero_resoconti`, «ogni giorno rifatto logga una riga con la durata»); la
    **durata vera della casa non e' ancora scrivibile qui**, perche' nasce solo dopo il rilascio,
    quando il recupero rifa' i giorni sull'host di HA. Si scrive al Task 12, con la verifica dal
    vivo: **questa misura resta sintetica finche' quel numero non c'e'.**
13. **Le domande aperte del censore**: `type_census.OPEN_QUESTIONS` ne ha **6**, che coprono
    **115 voci** (1 + 4 + 1 + 31 + 57 + 21). La docstring di `type_vocabulary.py` dice «110».
14. **La casa**: 0 `lock`, 1 `alarm_control_panel` (`disarmed`), 53 `update` (nessuno `on`), HA
    `2026.9.2`.

---

## §2 · Il perimetro: cosa diventa sapere

**Diventano sapere i giudizi nostri che un lettore usa a runtime**, e il genere nuovo:

| campo del sapere | da | celle |
|---|---|---|
| `genere` | nuovo (§5) — solo generi con una forma (D2) | 26 |
| `notevole` | `notable` | 23 |
| `riposo` | `resting_states` | 16 + 2 nuove (`home` su `person` e `device_tracker`, §5) |
| `accendibile` | `operable` | 13 |
| `limiti_parametri` | `parameter_limits` | 10 |
| `lavoro` | `working_states` | 9 |
| **totale** | | **99** |

**Conteggio eseguito il 16/09/2026** sul letterale alla `3.48.1` (non a mano): `notable` 23,
`resting_states` 16, `operable` 13, `parameter_limits` 10, `working_states` 9, tutte `nostro`;
`genre_for` eseguito su tutte le 76 righe da' 2 `presenza` + 12 `funzionamento` + 12 `sicurezza` =
26; `person` e `device_tracker` oggi **non** hanno una riga `resting_states`, quindi le due `home`
sono celle nuove. Totale **99**.

**Restano codice**, in `type_vocabulary.py`, con le loro porte e le 12 prove ancorate al sorgente
(`test_feature_tables_pinned_to_source.py`, 3; `test_attribute_tables_pinned_to_source.py`, 9):
`capability_names`, `capability_attributes`, `state_attributes` (68 celle `importato`),
`capability_attributes_dropped` (2 celle) e **`assumable_attributes` (2 celle, D1)**. Questi due
ultimi sono giudizi nostri, ma **correggono una tabella importata**: `capability_attributes(domain)`
sottrae entrambi dalla trascrizione di HA, quindi vivono accanto alla loro fonte. Restano costanti
del modulo `ABSENT_STATE_FORMS`, `UNKNOWN_STATES`, `GROUP_MEMBERSHIP_ATTRIBUTES`.

**Perche' i fatti di HA non entrano.** Nessuno ha titolo per correggerli (il bit 32 di `climate`
lo dice il sorgente); una riga di casa che li sovrascrivesse lascerebbe **verdi** le prove
ancorate al sorgente mentre il prodotto legge altro; e `importato` finirebbe per dire due cose —
«copiato dal sorgente con la versione» e «letto dall'installazione» (le 177 righe `significato`).

**I nomi dei campi sono italiani**, come quelli gia' nel sapere (`significato`, `attributi`,
`ricetta`): sono chiavi di dominio in un archivio nostro, non valori che attraversano un confine.
La traduzione fra i nomi dei campi del modulo (inglesi) e quelli del sapere vive **in un posto
solo**, accanto al seme.

**Forma dei valori**, letta sul letterale (non dedotta): `genere` e' testo nudo; `riposo` e' una
lista JSON ordinata; **`lavoro` e' un oggetto JSON `{stato: ragione}`** — nel letterale
`working_states` e' una mappa con la ragione scritta di ogni stato (`declared_working_states`,
«per la prova che boccia un giudizio senza ragione scritta»), e la ragione non si perde passando al
sapere; `notevole` e `accendibile` sono `"si"`/`"no"`; `limiti_parametri` e' un oggetto JSON
`{parametro: {"min": attributo, "max": attributo} | {"options": attributo}}`.

---

## §3 · L'istantanea

**`TypeJudgments`** (nuovo, `home_space/type_judgments.py`): un oggetto **immutabile** costruito
da un elenco di righe del sapere. Non apre archivi, non legge la rete, non ha stato globale.

- **Risponde per soggetto, dal piu' specifico**: entita' → coppia dominio/classe → dominio. La
  prima riga trovata vince; un valore esplicito `nessuno` (per `genere`) **nega** il livello
  sopra, ed e' diverso dall'assenza della riga.
- Espone le domande che i lettori fanno oggi: il genere di un soggetto, il riposo e il lavoro di
  un tipo, se e' notevole, i domini accendibili, i limiti di un parametro, e
  l'**impronta della cronaca** (§6).
  **Corretto il 17/09/2026**: questa riga elencava anche «se e' accendibile». Quella porta
  (`TypeJudgments.is_operable`) e' stata **cancellata** al Task 8, perche' nessun lettore di
  produzione la chiamava e la sua prova e' passata su `operable_domains()`: chi chiede
  dell'accendibile chiede i domini.
- **Un valore che non si interpreta** (JSON rotto, genere fuori elenco) **ferma la costruzione**
  con l'elenco delle righe storte: si vede all'avvio o alla scrittura, non giorni dopo dentro un
  lettore.

**Il seme** (`mind/seed.judgment_seed`): le 99 celle del §2, ricavate **dal letterale** di
`type_vocabulary.py`, con provenienza `nostro`, autore `SEED_AUTHOR`, precedenza `REPO_PRIORITY`,
caricate all'avvio insieme a `direction_seed`, `meaning_seed`, `attribute_seed`. Il letterale resta
nel repo **solo come seme**: nessun lettore di produzione lo interroga piu' per questi campi.

**Chi la riceve.** L'app ne tiene **un riferimento**, `app["type_judgments"]`, e i lettori la
ricevono come parametro, come oggi ricevono il sapere `attributes_wanted_for(store, ...)` e
`directions_by_translation_key(store)`. Il riferimento si sostituisce in un colpo solo (§4): un
lettore che l'ha gia' preso finisce il suo lavoro sulla versione che aveva, e non vede mai
un'istantanea a meta'.

**Il parametro (D3).** I lettori profondi stanno in fondo a catene lunghe — `briefing.compose` →
`_highlight_lines` → `_is_event`; `ToolDispatcher._view` → `queries.view` → `_view_entity` →
`commands_for` → `_command_parameters` → `_limits_of_entity`; `aggregate_day` — con, nelle prove,
113 chiamate a `compose(`, 170 a `view(`, 55 ad `aggregate_day(` (contate il 16/09/2026). Il
parametro e' un **keyword `judgments=` con predefinito `REPO_JUDGMENTS`**: l'istantanea **del solo
seme**, costruita all'import **dal letterale** — pura e deterministica, non uno stato caricato
pigramente. Il predefinito serve alle prove e al censore; **in produzione ogni chiamata passa
l'istantanea viva**, e lo garantisce una **prova strutturale** su tutto `hiris/app` che boccia ogni
chiamata di produzione a queste funzioni senza `judgments=`, con la sua mutazione eseguita. Senza
quella prova il predefinito sarebbe esattamente la ricaduta silenziosa che §8 vieta.

**I lettori dei giudizi** (corretti il 16/09/2026, D4 — la prima stesura elencava anche
`action/verification`, `home_space/topology` e `proxy/entity_cache`, che leggono solo fatti di HA o
`attributi_assumibili`, rimasti codice):

| lettore | quale giudizio | quando chiede | cosa riceve |
|---|---|---|---|
| `home_space/briefing` (`_is_event`) | `notevole`, `lavoro` | a ogni turno di chat | l'istantanea corrente |
| `home_space/queries` (`_limits_of_entity`) | `limiti_parametri` | a ogni strumento | l'istantanea corrente |
| `home_space/type_census` | `riposo`, `lavoro`, `accendibile` | solo `scripts/istantaneo_pubblicato.py` | l'istantanea **del solo seme**: chiede cosa il REPO rivendica |
| `mind/facts` | `genere`, `riposo` | aggregazione notturna, riparazione, recupero | l'istantanea corrente, **una per giorno aggregato** |

**Non la ricevono**: `action/verification` e `home_space/topology` (solo `capability_names`),
`proxy/entity_cache` e `action/actuator` (fatti di HA e `assumable_attributes`, codice per D1).

---

## §4 · La porta di scrittura

**Una funzione sola** scrive un giudizio (`mind/judgments.write_judgment`): soggetto (genere del
soggetto `tipo` o `entita`, soggetto), campo, valore.

1. **Rifiuta** un campo fuori dal §2 — compresi i fatti di HA — e un valore che l'istantanea non
   sa interpretare, con un rifiuto motivato nella forma delle altre rotte.
2. Scrive la riga (`KnowledgeStore.write`), provenienza `nostro`, autore `proprietario`.
3. **Ricostruisce** l'istantanea dall'archivio e **sostituisce** il riferimento.
4. Risponde con la riga scritta e l'impronta nuova.

**Nessuna copia a valle da ricaricare.** Nessun giudizio del §2 e' tenuto gia' calcolato da una
cache: la `EntityCache` conserva ceste calcolate da fatti di HA e da `assumable_attributes`, che
restano codice (D1). La sola copia a valle dei giudizi sono i resoconti, e li governa §6.

**Tornare al seme** e' la stessa porta: scrivere il valore del seme. La regola del seme esistente
(«nessuno l'ha toccata si legge dal VALORE», `seeded_value`) le restituisce la riga.

**La rotta**: `POST /api/mind/judgment`, dietro la stessa autenticazione delle altre rotte
`/api/mind/*`. **Nessuna seconda porta**: una scrittura dei giudizi fuori da questa funzione e' un
difetto, con una prova che cerca le scritture su questi campi in tutto `hiris/app`.

---

## §5 · Il genere e il riposo

**Il genere nasce dal sapere.** `mind/facts` chiede all'istantanea il genere del soggetto (entita',
poi coppia dal `device_class` della riga di grezzo, poi dominio). **Restano codice**:

- i prefissi `problema:`, `integrazione:`, `log:`, `automazione:` → `guasto` (non sono entita');
- la **forma** di ogni genere (come apre, come chiude, cosa porta); i generi restano un **elenco
  chiuso** — la casa sceglie quale dare, non ne inventa;
- l'eccezione del `sensor` di sicurezza (il monossido misurato): nel seme **non ha riga** `genere`,
  e il dominio `sensor` non ne ha nessuna — la stessa uscita di oggi, ora scritta come dato.

**Il seme scrive solo i generi che hanno una forma (D2): 26 righe** — `presenza` 2, `funzionamento`
12, `sicurezza` 12. I sensori di presenza **non** vi entrano: li aggiunge il proprietario dalla
pagina, ed e' la verifica dal vivo (§9).

**`energia` e `bilancio` sono generi morti, misurato il 16/09/2026.** `mind/facts.py:69` li elenca
in `GENRES`, ma:

- **`energia`** — `genre_for` lo restituisce oggi per `sensor.energy`, `sensor.power`, `sensor.gas`,
  `sensor.water`, e dentro `aggregate_day` **nessun ramo lo tratta**: esistono solo `guasto`,
  `sicurezza`, `presenza`, `funzionamento`, e una riga `energia` cade oltre tutti senza produrre
  niente. Il commento in coda al ciclo lo dice: *«Un contatore non apre niente. Fino al 15/09/2026
  qui si annotava che il soggetto era un contatore, per costruirgli dopo un episodio di energia;
  quell'episodio e' uscito»*.
- **`bilancio`** — nessun codice lo produce: in `hiris/app` la stringa compare solo in `GENRES` e
  nella docstring di `aggregate_day` (`facts.py:677-690`), che descrive un parametro `balances` e
  «un oggetto di genere `"bilancio"`» che **non esistono piu'** (il commento dentro la funzione:
  *«I bilanci non entrano piu' qui (15/09/2026)»*). Il bilancio vive fra le **misure**, per la sua
  ricetta. Quella docstring e' una ragione smentita dal file stesso, e si corregge (§11).
- **Dal vivo**: nessuna voce di cronaca porta `genere` `energia` o `bilancio`. Il 15/09, il primo
  giorno col genere nella cronaca: `funzionamento` 36, `presenza` 5, `guasto` 4, `sicurezza` 1. I
  resoconti fino al 14/09 sono nella forma precedente, **senza** `genere` (788 voci su 834), e fino
  all'11/09 contenevano episodi di energia, usciti di proposito il 15/09 (§6).

Quindi **`GENRES` scende ai quattro con una forma** (`funzionamento`, `presenza`, `guasto`,
`sicurezza`) e la porta di scrittura **rifiuta** `energia` e `bilancio`. **E rifiuta anche
`guasto`** (aggiunto il 17/09/2026, dalla revisione: era nel codice e non in questa spec):
`guasto` e' il genere delle **condizioni di sistema**, non di un tipo o di un'entita' della casa
(`mind/judgments._SYSTEM_ONLY_GENRE`), e la pagina non lo offre fra le scelte. Tornano sceglibili il giorno
in cui un genere avra' una forma scritta in `facts.py`, non prima. Cambio di comportamento: **nessuno**
— oggi quelle righe non producono niente, e continuano a non produrre niente.

**Una regola sola per l'apertura**: un episodio di `funzionamento`, `sicurezza` o `presenza` e'
**aperto quando lo stato non e' a riposo per il suo soggetto**, letto dall'istantanea.

- `home` diventa una riga `riposo` su `person` e `device_tracker`; il ramo della presenza con
  `"home"` scritto a mano sparisce. L'episodio di una persona resta l'assenza, quello di un sensore
  di presenza diventa «rilevata presenza»: lo dicono `cosa` e `classe`, che l'episodio porta gia'.
- **`none` e il vuoto non aprono e non chiudono niente**, in nessun genere: sono un dato che manca,
  come `unavailable`/`unknown`. **Cambio di comportamento dichiarato** (§1, misura 8): i 6 apparati
  di rete smettono di aprire assenze false e di chiudere episodi con `none`, e quelle righe non portano
  piu' alla cronaca ne' il loro `friendly_name` ne' i cambi di solo attributo (come gia' per
  `unavailable`/`unknown`). Tutto il resto: 0 righe
  cambiano su 52.123.
- Il riposo e' **del soggetto**, non piu' l'unione di tutti i tipi: misurato senza effetti (§1,
  misura 7); la frase di `facts.py` che lo chiamava «un cambio di comportamento» si corregge con la
  misura.

---

## §6 · L'impronta e la cronaca rifatta

**L'impronta della cronaca**: un hash stabile delle righe `genere` e `riposo` dell'istantanea
(entita' comprese), ordinate. **Solo quei due campi**: correggere un limite o cio' che e' notevole
non invecchia nessun giorno.

**Il resoconto la porta**: `{"giudizio": {"impronta": "…"}}`, accanto a `obiettivo`. La scrive
chiunque scriva la cronaca — l'aggregazione notturna, la riparazione d'avvio, il recupero.

**Gli episodi escono da `aggregate_day`** in una funzione sola (`mind/facts.build_episodes`),
chiamata da `aggregate_day` e dal ricalcolo: **una** costruzione degli episodi, non due.

**Il ricalcolo** (`mind/facts.rebuild_chronicle`): per un giorno, ricostruisce gli episodi dal
grezzo con l'istantanea corrente e **sostituisce solo `cronaca` e `giudizio`** nel resoconto
salvato. `misure`, `forme`, `obiettivo` restano identici. Nessuna lettura di HA, nessuna ricetta.

**Quando**: il giro di recupero esistente (ogni 5 minuti, un giorno per giro, dal piu' vecchio,
mai oltre il grezzo) allarga la sua condizione da «il resoconto manca» a «**manca, oppure la sua
impronta e' diversa**». Un giorno mancante si fa intero come oggi; un giorno con impronta diversa
rifa' solo la cronaca. Ogni giorno rifatto logga **una riga con la durata** — e' la misura vera
che il §1 (misura 12) non ha. Un giro che non ha niente da fare non logga.

**Cosa non si rifa', e si dichiara**:

- i giorni **oltre il grezzo** tengono la loro impronta; il documento dell'analista (sezione «La
  cronaca») dice quando un giorno e' raccontato con un giudizio diverso da quello attuale;
- le **analisi gia' scritte** non si riscrivono: sono letture di un momento;
- una correzione su un'entita' che in un giorno non compare cambia comunque l'impronta, e quel
  giorno si rifa' con lo stesso risultato. E' accettato: il costo e' un giorno per giro.

**Due regole in piu', nate durante l'esecuzione e scritte qui il 17/09/2026** (decisioni del
proprietario al Task 6, trovate fuori dalla spec dalla revisione a 360 gradi):

- **il giorno a cavallo della potatura non rifa' la cronaca.** La potatura taglia il grezzo a un
  istante, non a mezzanotte: il primo giorno raggiungibile comincia quasi sempre prima della riga
  piu' vecchia, e le sue voci nate prima del taglio non si possono ricostruire. Rifarlo le
  cancellerebbe, quindi quel giorno **tiene** la cronaca e l'impronta che ha, e il documento dice
  che e' raccontato con un altro giudizio. Un giorno **mancante** a cavallo si scrive ancora, per la
  sola cronaca;
- **le voci ereditate da una riga d'origine gia' potata si conservano.** Una voce di cronaca che
  viene da prima della finestra non ha piu' il suo grezzo: `rebuild_chronicle` la tiene com'e'
  invece di perderla, sotto qualunque impronta.

**La prima volta**: i resoconti esistenti non hanno impronta, quindi al primo avvio tutti i giorni
dentro il grezzo rifanno la cronaca (in meno di due ore). E' la **prova sui giorni veri** (§9).

**Cosa cambia nei giorni vecchi, misurato il 16/09/2026** (21 resoconti, 26/08–15/09, 834 voci di
cronaca, eseguito sull'add-on). La cronaca rifatta non differisce da quella salvata solo per i `none`:
i resoconti fino al 14/09 sono stati scritti **prima** del commit `b2b2b55e` («gli oggetti escono»,
15/09/2026), che ha fatto entrare il genere nella cronaca. Quindi, oltre ai giudizi, il ricalcolo
porta i giorni vecchi **nel formato di oggi**. Tre classi di differenza, tutte dichiarate:

1. **i `none` degli apparati di rete** (§5, §1 misura 8) — episodi aperti o chiusi da `none` che
   spariscono o cambiano `fine_ts`;
2. **chiavi di formato aggiunte** — **788 voci su 834 non hanno `genere`** (solo le 46 del 15/09 lo
   portano); allo stesso modo le chiavi d'ancora `dominio`, `titolo`, `comparso_ts` (oggi 4 voci)
   entrate con lo stesso commit. Dopo il ricalcolo ogni voce le porta dove la forma di oggi le
   scrive. E' il formato, non un fatto nuovo sulla casa;
3. **episodi di energia tolti** — fino all'11/09 la cronaca portava ~17 episodi di energia al giorno
   (misura del piano dei tre attori, 05→09/09); sono **usciti di proposito** il 15/09 con lo stesso
   commit, sostituiti dalle ricette fra le misure. Il ricalcolo li toglie anche dai giorni vecchi:
   **non e' una regressione**, e' la decisione del 15/09 applicata ai giorni che ancora non la
   rispecchiavano, e il confronto la dichiara.

**Qualunque differenza fuori da queste tre classi e' un difetto e ferma la fetta.**

---

## §7 · La pagina

La sezione **04 «Cosa ho capito della casa»** della pagina dell'osservatore prende i giudizi:

- ogni giudizio mostra **il valore e da dove viene** (seme del repo, oppure corretto dal
  proprietario il giorno X);
- il genere di un tipo o di un'entita' si corregge sul posto, con «torna al seme»;
- le **6 domande aperte del censore** compaiono come domande a cui rispondere, ciascuna col suo
  campo di destinazione.
  **Consegnato in sola lettura, e la deviazione si scrive qui** (17/09/2026, forma approvata dal
  proprietario e revisione a 360 gradi): le sei domande **si vedono** con la loro domanda e le
  chiavi che coprono, ma **non si rispondono da questa porta**. Il contratto di
  `/api/mind/knowledge` non porta il campo di destinazione, e quattro delle sei non chiedono un
  `genere`: risponderle vorrebbe dire una porta per campo. E' una fetta sua, e finche' non c'e'
  questa riga della spec vale come «v1: le domande si leggono».

**La forma visiva non e' in questa spec**: prima di scriverla si consulta lo specialista UX/UI
(regola del progetto) e la proposta torna al proprietario. Vincoli gia' decisi: nessuna emoji;
titoli e bersagli secondo la voce di backlog sull'accessibilita' (titolo di rotta, 44 px).

---

## §8 · L'avvio e la salute

- Il sapere, il suo seme e l'istantanea nascono **prima** della `EntityCache`.
- Se il sapere non si apre, l'istantanea si costruisce **dal solo seme** e `GET /api/health` lo
  dichiara: `giudizi: {"da": "sapere" | "solo seme", "perche": …, "impronta": …}`. Nessuna ricaduta
  silenziosa.
- Se un valore del sapere non si interpreta, l'avvio **non** cade: l'istantanea si costruisce dal
  solo seme e `giudizi.perche` elenca le righe storte.

---

## §9 · Le prove e la verifica dal vivo

**Test prima del codice; mutazioni ESEGUITE e ripristinate con l'editor.** Una mutazione che resta
verde e' un test che non puo' fallire: si riscrive e lo si annota.

1. **Equivalenza del seme** — su tutte le 76 righe, genere e riposo dall'istantanea sono uguali
   alla regola vecchia **salvo le 4 righe `energia`** (vecchia: `energia`, nuova: nessun genere —
   la stessa uscita, perche' `energia` non produce niente, §5), **prima** che la vecchia si cancelli (poi la prova resta, contro valori
   attesi scritti a mano, non derivati dal vocabolario).
2. **Ordine di ricerca** — entita' > coppia > dominio; `nessuno` nega; l'assenza eredita.
3. **La porta** — scrivere e rileggere **dal lettore** (`facts`, `briefing`); mutazione: togliere
   la ricostruzione deve arrossire. Rifiuti: campo di HA, genere fuori elenco.
4. **Una porta sola** — nessuna scrittura dei campi del §2 fuori da `write_judgment`.
5. **L'avvio** — il sapere prima della cache; sapere rotto → `giudizi.da = "solo seme"`.
6. **La cronaca rifatta** — `misure`, `forme`, `obiettivo` identici byte per byte; cambiano solo
   `cronaca` e `giudizio`.
7. **I cambi dichiarati** — `none` su `device_tracker` e su `switch` non apre e non chiude.
9. **Una sola strada per il parametro** (D3) — una prova strutturale su `hiris/app` boccia ogni
   chiamata di produzione alle funzioni che leggono i giudizi senza `judgments=`; mutazione
   eseguita: togliere `judgments=` da una chiamata di produzione deve arrossire, con file e riga.
10. **I generi senza forma** (D2) — la porta rifiuta `energia` e `bilancio`; `GENRES` ha quattro
    voci.
8. **La presenza** — `person` a `not_home` apre, a `home` chiude (come oggi); un `binary_sensor`
   di classe `occupancy` con `genere=presenza` apre a `on` e chiude a `off`.

**Cancelli**: `pytest`, `npm test`, `npm run lint`, `ruff`, `censimento --cancello`,
`verifica_componenti`.

**Verifica dal vivo, sulla casa**:

1. **Prima del rilascio** si salva la cronaca di ogni giorno dentro il grezzo
   (`GET /api/mind/report?day=`).
2. **Dopo il rilascio**, a recupero finito, si rileggono e si confrontano. `misure`, `forme` e
   `obiettivo` **identici**. Ogni differenza nella cronaca si **classifica** in una delle tre classi
   del §6: (1) `none` degli apparati di rete; (2) chiavi di formato aggiunte (`genere`, `dominio`,
   `titolo`, `comparso_ts`) su una voce che per il resto e' la stessa (stessi `chi`, `quando_ts`,
   `fine_ts`, `cosa`); (3) episodi di energia tolti come deciso il 15/09. Il confronto stampa il
   conteggio per classe e giorno. **Qualunque differenza non classificata ferma la fetta.**
3. Dalla pagina il proprietario scrive `presenza` sul tipo dei sensori di presenza; la risposta
   porta un'impronta nuova; `GET /api/health` la mostra.
4. Nei giri successivi i giorni passati rifanno la cronaca, e il log dice quanto dura ciascuno
   sull'host vero.
5. La cronaca della notte successiva contiene gli episodi dei sensori di presenza.

---

## §10 · La revisione

A fine fetta, **tre revisori indipendenti su Fable 5.1**, con il divieto esplicito di `git stash`,
`git checkout`, `git restore` nel prompt. **La revisione guarda l'implementazione e tutta l'app a
360 gradi** (istruzione del proprietario, 16/09/2026): ogni lettore toccato, ogni porta, la pagina,
l'avvio, i resoconti, la casa viva — e risponde a «e' tutto funzionale e completo?», non solo «il
diff e' corretto?».

- **correttezza e completezza funzionale** su tutta l'app;
- **prove**: le mutazioni, eseguite;
- **coerenza** spec ↔ codice ↔ casa, comprese le ragioni scritte accanto al codice.

---

## §11 · Cosa si cancella e cosa si corregge

**Si cancella**: `ASPECTS`, `aspect_of`, i campi `aspect` e `aspect_guard` (43 celle), le righe di
genere `energia` di oggi (in `genre_for`),
`_reading_aspect`, il parametro della gamba di `genre_for`, il ramo `"home"` di `facts.py`,
l'uso dell'unione dei riposi in `_is_on`; le prove che difendevano le gambe
(`tests/test_home_space_gamba.py` e le parti relative di `test_home_space_type_vocabulary.py` e
`test_mind_facts.py`), smontate insieme a cio' che provavano.

**Si corregge** (ragioni smentite dal codice o dalla misura):

- `type_vocabulary.py`, docstring: «tutto `nostro`» (68 celle sono `importato`); «110 voci» (sono
  115); la parte «il vocabolario come casa» diventa «il vocabolario come seme».
- `type_vocabulary.py:505-518`: «perche' esiste un pavimento» (cancellato con la 3.26.0) esce con le
  gambe.
- la guardia del `device_tracker` e il suo commento escono con le gambe.
- `mind/facts.py`: la docstring di `genre_for` (il pavimento) e la frase sul riposo per tipo come
  «cambio di comportamento»; la docstring di `aggregate_day` (`:677-690`) che descrive il parametro
  `balances` e il genere `"bilancio"`, usciti il 15/09; `GENRES` (`:69`) scende ai quattro generi con
  una forma (§5, D2).
- **codice morto**: in `aggregate_day` il dizionario `measurements` (`facts.py:739`, `:766`) si
  scrive e non si legge mai — si cancella.
- **`mind/report.as_document`** e' puro e non conosce l'impronta di adesso: per dire «questa cronaca e'
  raccontata con un giudizio diverso» (§6) riceve un parametro nuovo con l'impronta corrente, e il
  suo chiamante `api/handlers_mind.py:215` lo passa.
- **`GET /api/mind/knowledge`** (`api/handlers_mind.py::handle_knowledge`) si estende per la pagina
  (§7): `giudizi` (le righe dei giudizi, ciascuna con `da`: seme o proprietario, e quando) e
  `domande_aperte` (le 6 di `type_census.OPEN_QUESTIONS`). Nessuna seconda rotta di lettura.
- `docs/BACKLOG.md`: la voce «Il vocabolario dei tipi non e' ancora un seme» (lettori, porte) e la
  gemella del genere si chiudono; «I tre attributi fissi del grezzo» si aggiorna: `source_type`
  perde il suo ultimo lettore.
- `docs/design/2026-09-10-i-tre-attori.md`: §8 («le 76 righe» → i giudizi, col perche' dei fatti di
  HA) e §13 (gambe e generi **fatti**).

---

## §12 · Fuori perimetro, dichiarato

- **L'osservatore che propone un genere per entita'** — una sua scelta sarebbe `dedotto`, e porta
  la regola «una deduzione non diventa mai un fatto». Fetta successiva.
- **Lo strumento della chat per correggere un giudizio** — chi scrive sarebbe il modello che
  interpreta le parole del proprietario. Fetta successiva.
- **Il genere per stato** (`lock=jammed`) — nessun caso in casa (0 serrature). Sara' un campo
  separato, non un formato dentro `genere`.
- **L'uscita di `source_type` dal grezzo** — resta nella sua voce di backlog.
- **I 6 apparati di rete come `presenza`** — un `nessuno` sulle loro entita' li toglie; nessuno e'
  guardato oggi.

---

## §13 · L'ordine

0. **Le due misure della 3.48.0** (volume a giorno pieno, resoconto del 16/09). Se il volume non e'
   crollato si ripara quello prima. **Nessuna riga di codice di questa fetta prima di allora.**
1. L'istantanea e il seme, con l'equivalenza (§9.1–2).
2. Il genere e il riposo in `facts` e negli altri lettori; cancellazione delle gambe (§5, §11).
3. L'impronta, `build_episodes`, il ricalcolo e il recupero allargato (§6).
4. La porta e la rotta; l'avvio e la salute (§4, §8).
5. La pagina, dopo lo specialista UX/UI (§7).
6. Le correzioni dei documenti (§11).
7. La revisione a 360 gradi su Fable 5.1 (§10).
8. Il rilascio — **commit, push e tag solo con la conferma esplicita del proprietario** — e la
   verifica dal vivo (§9).
