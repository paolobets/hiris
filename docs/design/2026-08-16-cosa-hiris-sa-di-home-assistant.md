# Cosa HIRIS sa di Home Assistant — rapporto di scostamento

**Data:** 2026-08-16 · **Ramo:** `2.0` · **Commit di riferimento:** `15ae32e` (v3.3.0)
**Metodo:** lettura del codice + verifica su `developers.home-assistant.io` e `home-assistant.io`.
Ogni affermazione porta o un `file:riga` o un URL. Dove non ho potuto verificare, è scritto.

**Avvertenza sul momento della lettura.** `hiris/app/casa/nucleo.py` era **modificato e non
committato** mentre scrivevo (la fetta «il vocabolario delle tipologie», `docs/design/
2026-08-16-il-vocabolario-delle-tipologie.md`, più `tests/test_vocabolario_tipologie.py` non
tracciato). Il file è cambiato *durante* la mia lettura: da 864 a 966 righe. I riferimenti a
`nucleo.py` qui sotto sono all'**albero di lavoro** al momento della seconda lettura, non a
`15ae32e`. Tutti gli altri file sono puliti.

**Annotazione del 02/09/2026 — i nomi citati qui sono quelli del 16 agosto.**
Questo e' un rapporto di MISURA: ogni riga porta un `file:riga` letto quel giorno, e riscrivere
i nomi lo trasformerebbe in un documento che non e' piu' il verbale di niente. La fetta «la
rinomina» ha da allora portato il codice all'inglese, quindi le 25 citazioni di questo file
vanno lette con la tabella del `docs/GLOSSARIO.md`: fra le altre, `_NOMI_DOMINIO` e'
`_DOMAIN_NAMES`, `_SIGNIFICATO_CLASSE` e' `_CLASS_MEANING`, `_CLASSI_EVENTO` e'
`_EVENT_CLASSES`, `_DOMINI_EVENTO` e' `_EVENT_DOMAINS`, `_STATI_ATTIVI` e' `_ACTIVE_STATES`,
`gerarchia()` e' `hierarchy()`, `_guarda_area` e' `_view_area`, `RegistroServizi` e'
`ServiceRegistry`, `memoria/riconoscitore.py` e' `memoria/resolver.py`. **Cio' che il rapporto
dice resta vero; sono cambiati i nomi, non i buchi.**

---

## 1. In una frase

HIRIS conosce bene la **struttura** dichiarata della casa — sei registri su sei, piani compresi,
con la distinzione fra «non c'è» e «non l'ho letto» curata meglio della media dei progetti che
parlano a Home Assistant — e conosce male **cosa tratta**: dei 44 tipi di entità documentati ne
nomina 17, delle ~160 `device_class` documentate ne interpreta 27 (tutte di `binary_sensor`) e
**non legge mai `/api/config`**, cioè non sa né in che unità misura questa casa, né dov'è, né in
che fuso orario — il buco più grande, perché non è una lacuna di dettaglio ma la mancanza del
sistema di riferimento in cui ogni numero che HIRIS pronuncia andrebbe letto. Sopra a tutti, però,
c'è un difetto puntuale nel codice non ancora committato: la classe del **rilevatore di
monossido** è scritta `co` invece di `carbon_monoxide` (§3.0).

---

## 2. Tabella di scostamento

| Area | Cosa dice Home Assistant | Cosa sa HIRIS | Conseguenza pratica |
|---|---|---|---|
| **Tipi di entità (domini)** | 44 tipi con pagina propria sotto `/docs/core/entity/`; la pagina utente «Entities and domains» ne elenca 46 (aggiunge `image_processing` e `tag`). Oltre a questi esistono domini non-entity-platform di uso quotidiano: `sun`, `zone`, `timer`, `counter`, `group`, `person`, `input_*` | `_NOMI_DOMINIO` ne nomina **17** (`nucleo.py:55`). Un dominio ignoto **non sparisce**: si stampa col nome tecnico (`nucleo.py:_nome_dominio`) | Il digesto scrive «Cucina: 3 `todo`» invece di «3 liste della spesa». Non è una perdita di dati, è una perdita di leggibilità — e per una persona che legge il nucleo, di senso |
| **`device_class` — `sensor`** | **62** valori documentati (+ `None`) | **Nessuna**. `archivio.py:136` salva la classe in colonna, `nucleo.py:_traduci_stato` la usa solo per `binary_sensor`/`cover` | HIRIS non sa distinguere `sensor.x` energia da `sensor.x` pressione da `sensor.x` glicemia. Tutti «sensore» |
| **`device_class` — `binary_sensor`** | **28** valori, ciascuno con semantica `on`/`off` dichiarata | **29 voci** in `_SIGNIFICATO_CLASSE` (`nucleo.py:152`): 27 delle 28 corrette, **`carbon_monoxide` scritta `co`** (vedi §3.0), più `damper` che è di `cover`. A `15ae32e` erano 5 | Quasi chiuso dalla fetta in corso: un allagamento passa da «1 sensore binario (acceso)» a «bagnato». **Il monossido no** |
| **`device_class` — `cover`** | **10** valori (`awning`, `blind`, `curtain`, `damper`, `door`, `garage`, `gate`, `shade`, `shutter`, `window`) + `None` | **0 delle 10**. `_SIGNIFICATO_CLASSE` contiene `door`/`window`/`garage_door`/`opening`/`damper`, ma `garage_door`/`opening` sono di `binary_sensor`, non di `cover`: le classi vere di `cover` sono `garage` e `gate`, e non ci sono | Una tapparella si chiama «tapparella» anche se è un cancello o una tenda da sole. `cover.cancello` aperto si legge «tapparella (aperta)» |
| **`device_class` — `switch`** | 2 valori (`outlet`, `switch`) + `None` | Nessuno | Una presa e un interruttore sono la stessa cosa per HIRIS |
| **`device_class` — `number`** | **59** valori | Nessuno; `number` è per giunta fuori dai domini-evento (`nucleo.py:108`) e fuori da `_NOMI_DOMINIO` | Un `number` di setpoint non si distingue da un `number` di calibrazione |
| **`state_class` (`sensor`)** | 4 valori: `measurement`, `measurement_angle`, `total`, `total_increasing`. È il campo che abilita le statistiche a lungo termine e la dashboard energia | **Non letto in nessun punto del prodotto.** `grep state_class` su `hiris/app/` → zero occorrenze | HIRIS non sa distinguere «21.5 °C adesso» da «un contatore che sale». `get_statistics` esiste (`ha_client.py:650`) ma **non ha chiamanti di produzione** — e senza `state_class` non saprebbe nemmeno a quali entità applicarla |
| **`entity_category`** | `config` / `diagnostic`. Le entità così marcate sono escluse dalle chiamate su device/area, non esposte di default ad Alexa/Google, e fuori dalle dashboard auto-generate | **Salvato** in colonna `categoria` (`archivio.py:135`) e **mai letto** in `15ae32e` (`grep` su tutto `app/`: solo scritture). La fetta in corso lo introduce come precondizione del digesto | Misurato sull'impianto vero: 179 entità su 300 «notevoli» erano `config` o `diagnostic`. Erano il rumore che ha fatto scattare il raggruppamento e nascosto le due luci accese |
| **`hidden_by`** | Scelta esplicita dell'utente nel registro | **Salvato** (`archivio.py:139`, colonna `nascosta`) e **mai letto** in `15ae32e` | Idem: 10 entità nascoste dall'utente rientravano dalla finestra |
| **`disabled_by`** | Tre disabilitatori documentati (`USER`, `INTEGRATION`, `CONFIG_ENTRY`) | Salvato come **booleano** (`archivio.py:138`) e usato davvero: fuori dai conteggi, dentro il dettaglio marcata (`anagrafe.py`, `domande.py:_guarda_area`) | Ben gestito. Si perde solo *chi* l'ha disabilitata — irrilevante per l'utente |
| **`labels`** | Assegnabili a aree, dispositivi, entità, automazioni, scene, script, helper | **Lette e salvate** (aree, dispositivi, entità: `archivio.py:114,122,140`); arrivano fino all'albero delle aree (`anagrafe.py:176`) e **non compaiono in nessun output**: né nel nucleo, né in `guarda`, né in `cerca` | «Fammi vedere tutto ciò che ho etichettato "vacanza"» → HIRIS non sa cosa siano le etichette, pur avendole in tabella |
| **`aliases`** | Nomi alternativi delle entità/aree | **Lette, salvate e USATE**: sono la spina dorsale di `memoria/riconoscitore.py:306` e di `cerca` | Nessuno scostamento. È la parte fatta meglio |
| **`categories`** | Tassonomia per tabella (automazioni, script, scene, helper) | Il **registro** delle categorie è letto per tutti e 4 gli ambiti (`ha_client.py:678`) e salvato (`archivio.py:151`), ma **nessuno lo legge** dopo. E l'**assegnazione** per-entità (campo `categories` di una voce di registro) non è letta affatto | Quattro comandi WS per riga in un DB che nessuno interroga |
| **Registri** | Gerarchia documentata: entità → dispositivo → area → piano; labels e categories trasversali | **Sei su sei**: piani, aree, dispositivi, entità, etichette, `config_entries` (`ha_client.py:687`). Il **registro piani esiste ed è usato davvero** — `gerarchia()` costruisce piano→area→entità e distingue «senza piano» da «piani non letti» (`anagrafe.py`) | Nessuno scostamento strutturale. È la parte forte del prodotto |
| **Integrazioni (`config_entries`)** | Elenco delle integrazioni configurate con il loro stato | Lette e salvate (`archivio.py:156`), **mai lette dopo** | «Quale integrazione gestisce questa luce?» — il dato c'è in tabella, non arriva mai al modello. `piattaforma` (la `platform` dell'entità) è nella stessa condizione (`archivio.py:134`, zero lettori) |
| **Servizi / azioni** | `GET /api/services`; ogni servizio ha `fields` (con sezioni collassabili), `selector`, `filter`, `target` e un `supports_response` | `RegistroServizi` specchia `/api/services` e **normalizza `fields`** appiattendo le sezioni (`azione/registro.py:39`). Verifica dominio, esistenza del servizio, esistenza dell'entità e **nomi dei parametri** (`azione/verifica.py:275`). **Non** legge `target`, **non** legge i `selector`, **non** valida i valori | Un servizio si può chiamare solo con bersaglio `entity` (`verifica.py:217`): area, dispositivo, piano ed etichetta sono rifiutati. E `homeassistant.restart` passa il controllo di dominio (`verifica.py:252`, dichiarato) |
| **Eventi** | 16 eventi core documentati + 4 delle integrazioni di default | Sottoscritti **7**: `state_changed`, i 6 `*_registry_updated` (`ha_client.py:25,810-821`) e `lovelace_updated` (`ha_client.py:39`). Nessun evento core documentato oltre `state_changed` | Vedi §3: HIRIS non sa quando HA riparte, non sa quando un'automazione scatta, non sa quando cambia la configurazione |
| **Unità e sistema di unità** | `/api/config` porta `unit_system` (`length`, `mass`, `temperature`, `volume`), `latitude`, `longitude`, `elevation`, `time_zone`, `location_name`, `version`, `components`. Il sistema è «Metric» o «US customary» | **Mai chiamato.** `grep` su `hiris/app/`: zero occorrenze di `config/core`, `get_config`, `unit_system`, `latitude`, `time_zone`. L'unità della singola entità è letta due volte (`entity_cache.py:88`, `archivio.py:137`) e **non arriva mai al modello**: `_specchio()` (`strumenti.py:599`) estrae solo `stato` e `nome`, e `_guarda_area` non include `unita` (`domande.py:181`) | HIRIS legge un numero e non sa in che unità è. Vedi §3.1 |
| **Storico** | `GET /api/history/period`, `GET /api/logbook`, `recorder/statistics_during_period` | `get_logbook`, `get_statistics`, `render_template`, `get_error_log`, `get_system_health` esistono nel client e **hanno zero chiamanti di produzione** (verificato: solo `tests/`) | «Da quanto è accesa?» «Quanto ho consumato ieri?» «Chi ha acceso la luce?» — nessuna è rispondibile. `_to_minimal` butta via anche `last_changed` (`entity_cache.py:80`) |
| **Plance (Lovelace)** | `lovelace/dashboards/list` + `lovelace/config` | Lette tutte, **predefinita compresa** (che non compare nell'elenco), con gli entity_id estratti ricorsivamente (`comportamento.py:305`) | Nessuno scostamento. Copertura migliore della media |
| **Comportamento (automazioni/script)** | Automazioni e script vivono in `automations.yaml`/`scripts.yaml` **o** in packages, `!include`, cartelle, o nella UI | Legge **solo i due file** (`comportamento.py:23-24`) e incrocia con lo stato, marcando `solo_stato` chi ha nome ma non corpo | Corretto e dichiarato. Ma **scene** (dominio nominato in `_NOMI_DOMINIO`), **helper** e **template** non hanno corpo per nessuna via: `guarda` accetta `automazione` e `script`, non `scena` |

> **Chiuso a metà il 24/08/2026**, fetta «HIRIS e il tempo»: `get_logbook` e
> `get_statistics` sono diventati `diario` e `statistiche`, e hanno un
> chiamante vero (`casa/tempo.py`). `render_template` resta orfano, per motivi
> suoi.

> **`get_error_log` non esiste piu', dal 01/09/2026** (fetta «la rinomina»,
> commit `c6d0591`). La riga sopra dice che «esiste nel client», ed era vero
> quel giorno: oggi il metodo e' cancellato, insieme al suo test e alla sua
> voce nella guardia di `scripts/rinomina.py`. La ragione non e' che fosse
> orfano -- lo erano anche altri -- ma che **mentiva**: l'endpoint
> `GET /api/error_log` risponde 404 su Home Assistant 2026.8.3, e il metodo
> inghiottiva il 404 restituendo `{"errors": 0, "warnings": 0}`, cioe' «nessun
> errore» invece di «non lo so». E' lo zero che AFFERMA, la stessa famiglia del
> «0%/Attenzione» di altri prodotti. Chi riprendera' le tracce e i log parte
> quindi da zero metodi, non da uno da collegare -- ed e' un'informazione che
> cambia il piano, non un dettaglio di manutenzione.

---

## 3. I buchi in ordine di danno

L'ordine è di **danno**, non di dimensione: un buco piccolo che fa dire una frase falsa con
sicurezza sta sopra un buco grande che fa dire «non lo so».

### 3.0 — Il rilevatore di monossido non si chiama `co`, e la fetta in corso lo chiama così

**Sta nel codice non committato**, quindi non è ancora un difetto in produzione — ma sta per
diventarlo, ed è il motivo per cui apre questo elenco.

`nucleo.py:121` (`_CLASSI_EVENTO`) e `nucleo.py:157` (`_SIGNIFICATO_CLASSE`) usano la stringa
**`"co"`**. Home Assistant documenta quella `device_class` come **`carbon_monoxide`**, verbatim:
*«`carbon_monoxide`: `on` means carbon monoxide detected, `off` no carbon monoxide (clear)»*. La
sigla `CO` è il nome della **costante Python**, non il valore della stringa. Lo stesso errore è
nella tabella del progetto (`docs/design/2026-08-16-il-vocabolario-delle-tipologie.md`, §2.1).

**Conseguenza.** Un rilevatore di monossido che scatta **non entra nel digesto** (la classe non è
in `_CLASSI_EVENTO`) e **non viene tradotto** (`_traduci_stato` non trova la voce): resta
`binary_sensor` con stato `on`, cioè fuori da «Notevole adesso» insieme ai sensori di movimento.
Il caso peggiore che questa fetta esiste per chiudere — un allarme di sicurezza indistinguibile
dal rumore — resta aperto proprio per il gas che uccide.

**Nessun test lo copre.** `tests/test_vocabolario_tipologie.py` prova `moisture`; non nomina né
`co` né `carbon_monoxide`. La suite resterà verde.

**Correzione:** `"co"` → `"carbon_monoxide"` nei due punti, e una prova gemella di quella su
`moisture`. Ho controllato le altre 27: `gas`, `smoke`, `moisture`, `safety`, `tamper`, `problem`,
`heat`, `cold`, `door`, `window`, `garage_door`, `opening` sono scritte esatte.

*(Minore, stesso blocco: `damper` è una `device_class` di **`cover`**, non di `binary_sensor`, e
gli stati di `cover` sono `open`/`closed`, non `on`/`off`. La riga `nucleo.py:168` è quindi
inerte — non fa danno, ma afferma di coprire un caso che non copre. Le classi di `cover` vere e
non coperte sono `garage` e `gate`.)*

### 3.1 — HIRIS non legge `/api/config`: non sa in che unità, dove e quando vive

**Cosa non può fare.** Non conosce il sistema di unità della casa, la posizione, il fuso orario,
la versione di Home Assistant, né quali componenti siano caricati. Peggio: **l'unità della singola
entità, che pure legge due volte, non arriva mai al modello.** `_to_minimal` la mette in `unit`
(`entity_cache.py:88`) e nessuno la rilegge (`grep '"unit"'`, `grep '.get("unit")'`: un solo
punto di scrittura, zero letture). `_guarda_area` restituisce `{id, nome, classe, stato,
disabilitata}` (`domande.py:181`) — nessuna unità. `_guarda_entita` ha `unita`
(`domande.py:226`) ma la prende dal **registro**, non dallo stato: vedi §3.2 sul perché quel
campo potrebbe essere sempre nullo.

**La domanda che sbaglia.** *«Fa caldo in soggiorno?»* → HIRIS legge `sensor.soggiorno_temp` e
trova `72`. Con `guarda` su un'area non ha l'unità; se la casa è in US customary sono 72 °F
(22 °C, tiepido) e HIRIS può concludere «fa molto caldo, 72 gradi». Se il sensore fosse in %
di umidità mal classificato, stesso numero, altro pianeta. **HIRIS non ha modo di accorgersene.**

**Nota di onestà.** La documentazione ufficiale dichiara che la conversione automatica avviene
*«only the first time the sensor is added»*: cambiare sistema di unità dopo **non** riconverte i
sensori già presenti. Quindi nemmeno leggere `unit_system` basterebbe da solo — serve l'unità
per entità, che è quella che HIRIS getta via.

### 3.2 — La forma delle risposte di HA su cui poggia l'anagrafe non è documentata, e i test non possono accorgersene

**Cosa ho verificato.** La pagina WS API documenta **un solo** comando di registro:
`config/entity_registry/list_for_display`. `config/area_registry/list`,
`config/device_registry/list` e `config/entity_registry/list` compaiono solo dentro un esempio
di codice in `docs/frontend/custom-ui/custom-strategy`. `config/floor_registry/list`,
`config/label_registry/list`, `config/category_registry/list` e `config_entries/get` **non
compaiono in nessuna pagina ufficiale**. E la pagina `entity_registry_index` **non elenca i campi
di una voce di registro**: rimanda al sorgente.

**Cosa ne segue per HIRIS.** `archivio.py:124-140` legge da `config/entity_registry/list` questi
campi: `name`, `original_name`, `area_id`, `device_id`, `platform`, `entity_category`,
`device_class`, `original_device_class`, `unit_of_measurement`, `disabled_by`, `hidden_by`,
`aliases`, `labels`. Dalla tabella `list_for_display` ho potuto **confermare**: `entity_id`,
`platform`, `area_id`, `device_id`, `labels`, `icon`, `translation_key`, `entity_category`,
`hidden_by`, `has_entity_name`, `name`/`original_name`, `options`, `disabled_by`. **Non ho
potuto verificare su documentazione ufficiale**: `device_class`, `original_device_class`,
`unit_of_measurement`, `aliases`, `categories`, `capabilities`, `supported_features`,
`config_entry_id`, `original_icon`. Non affermo che non ci siano — affermo che la doc non li
dichiara.

**Perché è un danno e non un cavillo.** Tre colonne dell'anagrafe (`classe`, `unita`, `alias`)
dipendono da campi non confermati, e l'unico test che le copre
(`tests/test_casa_archivio.py:5-20`) usa un **fixture scritto a mano** che li contiene per
costruzione. Se `config/entity_registry/list` non li restituisse, il test resterebbe verde e in
produzione `classe` e `unita` sarebbero **NULL su tutta la casa** — silenziosamente. È
esattamente la classe di difetto già pagata due volte su questo ramo (`fields` di
`/api/services`, e la lista dei cambiati di `call_service`, entrambe misurate solo dal vivo).

**Aggravante misurabile.** La doc REST di `GET /api/services` mostra `services` come **lista di
nomi** (`{"domain": "browser", "services": ["browse_url"]}`), mentre `azione/registro.py:114-124`
si aspetta una **mappa** nome→dettaglio. Il modulo lo dichiara già («la forma **attesa**, non
ancora misurata», `registro.py:17-21`) e ha una diagnosi apposita (`registro.py:134`). L'esempio
della doc è però datato (`version 0.56.2` altrove nella stessa pagina): non ho potuto stabilire
quale delle due forme mandi HA oggi. **Non verificato.**

**La domanda che sbaglia.** *«Che classe è questo sensore?»* → «non lo so» su ogni entità della
casa, senza che nessun test, nessun log e nessun avviso lo dica.

### 3.3 — HIRIS non sa quando Home Assistant riparte, né quando un'automazione scatta

**Cosa non può fare.** Sottoscrive 7 eventi (`ha_client.py:810-825`). Non sottoscrive:
`homeassistant_start` / `homeassistant_started` / `homeassistant_stop` (HA riparte),
`core_config_updated` (cambia posizione/unità/fuso), `service_registered` / `service_removed`
(compare o sparisce un servizio), `automation_triggered` / `script_started` (qualcosa è scattato),
`call_service` (qualcuno ha chiesto qualcosa), `logbook_entry`.

**Le conseguenze, in ordine.**
1. Al riavvio di HA le entità passano tutte per `unknown` e poi tornano: `state_changed` copre il
   caso, ma `_stato_inaffidabile` (`nucleo.py`) deduce il riavvio dal fatto che *nessuna* entità
   abbia stato leggibile. Con un riavvio parziale la deduzione non scatta.
2. `RegistroServizi` si rinfresca a scadenza (300 s, `registro.py:100`) invece che su evento:
   per cinque minuti dopo aver installato un'integrazione HIRIS rifiuta i suoi servizi dicendo
   «non esiste in questa casa» — una frase falsa, detta con sicurezza.
3. **Il danno vero:** *«perché si è accesa la luce del corridoio?»* HIRIS non ha modo di
   rispondere. Non ha `automation_triggered`, non ha `call_service`, non ha il logbook cablato
   (`get_logbook` è orfano). Può solo elencare le automazioni che *potrebbero* averlo fatto,
   leggendo i corpi dei due file YAML.

### 3.4 — `esegui` sa colpire solo entità, quando HA ha cinque dimensioni di bersaglio

**Cosa non può fare.** `verifica()` rifiuta qualunque bersaglio che non sia `bersaglio.entita`
(`verifica.py:295-307`), e lo dichiara apposta (`verifica.py:217`). Ma HA documenta `target` con
`entity_id`, `device_id`, `area_id` — e la pagina WS mostra `label_id` e le risposte
`missing_floors`/`missing_labels`.

**Cosa esiste in HA e HIRIS non usa.** La stessa pagina WS documenta `extract_from_target`, che
risolve un target in entità, e `get_services_for_target`, che dice quali azioni si applicano a un
bersaglio. Sono esattamente i due comandi che chiuderebbero questo buco senza indovinare nulla.
**Non ho verificato** se siano disponibili nella versione di HA del proprietario.

**La domanda che sbaglia.** *«Spegni tutto in cucina.»* → il modello deve prima chiamare `cerca`,
prendere gli id uno per uno e passarli tutti a `esegui`. Se `cerca` ne perde uno — o se il tetto
di 10 giri di strumenti scatta prima — HIRIS spegne *quasi* tutto e dichiara di aver spento tutto.
Con `area_id` sarebbe una chiamata sola e nessuna lista da ricostruire.

**Aggravante sulla larghezza.** `_DOMINI_UNIVERSALI = {"homeassistant"}` (`verifica.py:252`)
esenta l'**intero** dominio dal controllo, non i soli servizi che agiscono sull'entità:
`homeassistant.restart` con `light.cucina` nel bersaglio passa. È dichiarato nel codice, con la
ragione (`target` non ancora misurato). Verificato: la doc `dev_101_services` conferma che
`target` esiste ed è opzionale per definizione, quindi il criterio proposto è sano — ma resta
non misurato.

### 3.5 — 27 tipi di entità comuni in una casa non hanno né nome né significato

`_NOMI_DOMINIO` ha 17 voci sui 44 documentati. Restano fuori, fra quelli che una casa vera ha
davvero (27, contati sotto):
`weather`, `sun`, `zone`, `device_tracker`, `todo`, `calendar`, `number`, `select`, `update`,
`button`, `humidifier`, `water_heater`, `valve`, `siren`, `remote`, `text`, `event`, `timer`,
`counter`, `group`, `date`, `time`, `schedule`, `input_number`, `input_select`, `input_text`,
`input_datetime`.

Due sono **incoerenze interne**, non solo lacune:
- `water_heater` e `valve` hanno attributi curati in `_DOMAIN_ATTRS` (`entity_cache.py:68`) e
  `valve` è nei domini-evento (`nucleo.py:108`), ma **nessuno dei due ha un nome italiano**:
  il digesto scrive «1 `water_heater`».
- `scene` ha un nome italiano (`nucleo.py:69`) ma **nessun corpo leggibile**: `comportamento.py`
  legge solo `automations.yaml` e `scripts.yaml`, e `guarda` non accetta il tipo `scena`.

**La domanda che sbaglia.** *«Cosa devo comprare?»* → HIRIS ha `todo.lista_spesa` in anagrafe, lo
conta come «1 todo», non sa che sia una lista, non ha modo di leggerne le voci (nessuno strumento
tocca il dominio `todo`) e non lo dice. Idem *«che tempo farà?»* con `weather.casa` a portata di
`guarda`: ne leggerebbe lo stato (`sunny`) e nient'altro, perché gli attributi di `weather` non
sono in `_DOMAIN_ATTRS` — previsioni, temperatura e vento non arrivano.

### 3.6 — `state_class` e le statistiche: la capacità c'è, il ponte no

`get_statistics` (`ha_client.py:650`) è scritto, testato
(`tests/test_ha_client_statistics.py`) e **senza chiamanti**. Senza `state_class` HIRIS non
saprebbe comunque a quali entità applicarlo: la doc dice che HA compila statistiche a lungo
termine **solo** per i sensori che dichiarano `measurement`, `total` o `total_increasing`, e che
quelle statistiche non vengono mai purgate.

**La domanda che sbaglia.** *«Ho consumato più corrente questo mese o il mese scorso?»* → HIRIS
può leggere il valore istantaneo del contatore e nient'altro. La risposta esiste nel database di
Home Assistant, a un comando WS di distanza.

---

## 4. Cosa NON è un buco

Elencato perché non venga «corretto» per errore.

1. **Il nucleo conta e non elenca.** Con 845 entità, elencarle sfonderebbe il contesto a ogni
   messaggio. È dichiarato nel docstring del modulo (`nucleo.py:1-43`) ed è la scelta giusta.
   Aggiungere domini a `_NOMI_DOMINIO` non contraddice questo: si tratta di come si chiama una
   riga di conteggio, non di quante righe ci sono.

2. **`_STATI_ATTIVI` non copre gli stati «armed_*» dell'allarme.** Verificato che quegli stati
   esistono; sono deliberatamente esclusi perché armare e disarmare è la routine quotidiana, non
   un'eccezione. Solo `triggered` è un evento. La ragione è scritta accanto (`nucleo.py:74-88`).

3. **`_DOMINI_EVENTO` esclude `sensor`, `device_tracker`, `person`, `automation`.** Non è cecità:
   è la distinzione fra un evento e una condizione, misurata (179 su 300 «notevoli» erano rumore).
   `guarda` e `cerca` li riportano quando li si chiede — è la differenza fra un vocabolario e un
   filtro, e c'è una prova che la pinna.

4. **`verifica()` non valida i valori dei parametri.** Dichiarato (`verifica.py:206-212`): una
   validazione approssimativa rifiuterebbe chiamate legittime, mentre l'errore di HA è chiaro e il
   modello ci si corregge. Il ragionamento è corretto e va lasciato stare.

5. **`verifica()` non guarda `supported_features`.** Dichiarato (`verifica.py:213-216`). Richiede
   interpretare bitmask dominio per dominio; il controllo sul dominio copre il caso grosso.

6. **`call_service` non è la fonte dell'esito.** Misurato sull'impianto vero: risposta `list`,
   0 voci utilizzabili, a comando riuscito (`ha_client.py:139-146`). La scelta di aspettare
   `state_changed` con una scadenza (`porta.py:22-70`) è **corroborata dalla doc ufficiale**, che
   per `call_service` via WebSocket dice: *«Right now there is no return value. The client can
   listen to `state_changed` events if it is interested in changed entities as a result of a
   call.»* Non toccare.

7. **HIRIS non chiede `?return_response`.** La doc avverte che usarlo su un servizio che non
   restituisce dati produce un **400**, e non usarlo su uno che *deve* restituirli produce
   anch'esso un 400. Senza sapere quali servizi lo supportano — informazione che
   `GET /api/services` non espone nella forma documentata — non chiederlo è la scelta sicura.

8. **La replica si sostituisce, non si rattoppa** (`archivio.py:1-10`, `sostituisci()`).
   È il motivo per cui una casa monca non può esistere. Non è inefficienza.

9. **Sei registri letti su una connessione sola** (`ha_client.py:_ws_batch`) con
   `non_disponibili` conservato accanto ai dati. Il fatto che una casa senza piani e un registro
   piani caduto siano distinguibili anche a ore di distanza è raro e va difeso.

10. **Gli eventi di registro che HIRIS sottoscrive non sono documentati da HA.**
    `area_registry_updated`, `entity_registry_updated`, `device_registry_updated` **non compaiono**
    nella pagina ufficiale degli eventi; `floor_`/`label_`/`category_registry_updated` nemmeno.
    Funzionano, ma sono superficie non contrattuale: se un giorno smettessero, HIRIS ha già la
    rete di sicurezza giusta — ogni riconnessione WS rifà l'anagrafe (`ha_client.py:826-846`).
    Non è un buco; è un rischio già coperto.

---

## 5. Fonti

Tutte consultate il 2026-08-16.

| URL | Cosa ho verificato lì |
|---|---|
| `https://developers.home-assistant.io/sitemap.xml` | L'elenco dei **44** tipi di entità con pagina propria sotto `/docs/core/entity/`. La pagina `/docs/core/entity/` **non** contiene l'elenco nel corpo: sta solo nella sidebar |
| `https://www.home-assistant.io/docs/configuration/entities_domains/` | Elenco utente delle «building block integrations»: **46** voci, che aggiungono `image_processing` e `tag` rispetto alla sitemap |
| `https://developers.home-assistant.io/docs/core/entity/sensor/` | Le **62** `device_class` di `sensor`; i **4** valori di `state_class` (`measurement`, `measurement_angle`, `total`, `total_increasing`) e il loro legame con le statistiche a lungo termine; `native_unit_of_measurement` e `suggested_unit_of_measurement` |
| `https://www.home-assistant.io/integrations/binary_sensor/#device-class` | Le **28** `device_class` di `binary_sensor` con la semantica `on`/`off` di ciascuna; le quattro di apertura sono `door`, `garage_door`, `opening`, `window` |
| `https://www.home-assistant.io/integrations/cover/#device-class` | Le **10** `device_class` di `cover`: `awning`, `blind`, `curtain`, `damper`, `door`, `garage`, `gate`, `shade`, `shutter`, `window` |
| `https://www.home-assistant.io/integrations/switch/` | Le sole 2 `device_class` di `switch`: `outlet`, `switch` |
| `https://developers.home-assistant.io/docs/core/entity/number/` | Le **59** `NumberDeviceClass` |
| `https://developers.home-assistant.io/docs/core/entity/` | `entity_category`: i due valori `CONFIG` e `DIAGNOSTIC` con le definizioni; `unit_of_measurement` come proprietà dell'entità base |
| `https://developers.home-assistant.io/blog/2021/10/26/config-entity/` | Le quattro conseguenze di `entity_category`: escluse dalle chiamate su device/area, non esposte di default a Google/Alexa, card separata, fuori dalle dashboard auto-generate |
| `https://www.home-assistant.io/docs/configuration/basic/` | Il sistema di unità è «Metric» o «US customary», scelto in onboarding per geolocalizzazione. La pagina **non** spiega quali unità concrete implichi ciascuno |
| `https://developers.home-assistant.io/blog/2022/12/07/unit_system_changes/` | La conversione automatica avviene *solo alla prima aggiunta del sensore*; cambiare sistema dopo non riconverte. `IMPERIAL_SYSTEM` deprecato in favore di `US_CUSTOMARY_SYSTEM` |
| `https://developers.home-assistant.io/docs/api/websocket/` | I comandi WS documentati (`get_states`, `get_config`, `get_services`, `get_panels`, `subscribe_events`, `subscribe_trigger`, `call_service`, `fire_event`, `validate_config`, `extract_from_target`, `get_triggers_for_target`, `get_conditions_for_target`, `get_services_for_target`, `homeassistant/expose_entity/list`). **Nessun comando di registro tranne `config/entity_registry/list_for_display`.** La tabella di quel comando è l'unica fonte ufficiale sui campi di una voce di registro. `extract_from_target` accetta `label_id` e risponde `missing_floors`/`missing_labels`. `call_service` via WS: *«Right now there is no return value»* |
| `https://developers.home-assistant.io/docs/frontend/custom-ui/custom-strategy` | L'unico punto ufficiale in cui compaiono `config/area_registry/list`, `config/device_registry/list`, `config/entity_registry/list` — dentro un esempio di codice, non una specifica |
| `https://developers.home-assistant.io/docs/entity_registry_index/` | **Non** elenca i campi di una voce di registro: solo il concetto e la regola dello `unique_id` |
| `https://developers.home-assistant.io/docs/entity_registry_disabled_by` | I tre valori di `disabled_by`: `USER`, `INTEGRATION`, `CONFIG_ENTRY` |
| `https://developers.home-assistant.io/docs/api/rest/` | L'elenco degli endpoint REST; i campi di `GET /api/config` (`unit_system`, `latitude`, `longitude`, `elevation`, `time_zone`, `location_name`, `version`, `components`, `config_dir`); `POST /api/services` *«Returns a list of states that have changed while the service was being executed»* e il comportamento di `?return_response` (400 nei due versi); `GET /api/history/period` con `filter_entity_id` obbligatorio; `GET /api/logbook`; `GET /api/calendars`. **`GET /api/services` mostra `services` come lista di nomi**, non come mappa con `fields` |
| `https://www.home-assistant.io/docs/configuration/events/` | I 16 eventi core + 4 delle integrazioni di default. **`*_registry_updated` non compaiono** |
| `https://developers.home-assistant.io/docs/dev_101_services/` | La struttura di `services.yaml`: `target` (entity/device/area), `fields` con **sezioni collassabili** — che è ciò che `azione/registro.py:_campi` appiattisce — `selector`, `filter`, `supports_response` (`OPTIONAL`/`ONLY`). `target` con `floor_id`/`label_id` **non è documentato qui** |
| `https://www.home-assistant.io/docs/organizing/` + `/areas/` + `/floors/` + `/labels/` + `/categories/` | La gerarchia entità→dispositivo→area→piano; *«Devices and entities cannot be assigned to floors directly but to areas»*; le labels su aree/dispositivi/entità/automazioni/scene/script/helper; le categories uniche per tabella |
| `https://www.home-assistant.io/integrations/sun/`, `/zone/`, `/timer/`, `/group/` | Esistenza e stati di `sun` (`above_horizon`/`below_horizon`), `zone` (numero di persone dentro), `timer` (`idle`/`active`/`paused`), `group` |

### Cose che non ho potuto verificare

- Se `config/entity_registry/list` restituisca `device_class`, `original_device_class`,
  `unit_of_measurement`, `aliases`, `categories`, `capabilities`, `supported_features`,
  `config_entry_id`. La documentazione ufficiale non descrive la risposta di quel comando.
- Se `capabilities` di una voce di registro contenga `state_class`: nessuna riga della
  documentazione ufficiale lo dice.
- Quale forma abbia oggi `services` in `GET /api/services` (lista di nomi come nell'esempio della
  doc, o mappa con `fields` come assume `azione/registro.py`). L'esempio ufficiale è datato.
- Se `extract_from_target` e `get_services_for_target` siano disponibili nella versione di HA
  dell'impianto del proprietario.
- Gli stati documentati delle entità `automation` e `script`: la doc ufficiale non li dichiara.
- Se `entity_category` implichi la non-esposizione automatica ad **Assist**: il testo ufficiale
  cita solo Google Assistant e Alexa.
