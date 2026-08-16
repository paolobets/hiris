# Il vocabolario delle tipologie

**Data:** 2026-08-16 · **Ramo:** `2.0` · **Versione di partenza:** 3.3.0 (`15ae32e`)
**Nasce da:** una risposta sbagliata di HIRIS sull'impianto del proprietario, e da tre correzioni
di rotta che il proprietario ha imposto durante l'analisi.

---

## 0. Il fatto

Alla domanda *«lo stato della casa in generale, luci accese, temperature»* HIRIS ha risposto
elencando nove aree su sedici, dichiarando di aver **esaurito il limite di chiamate per il turno**,
e concludendo che **nessuna luce era accesa**. Erano accese due luci, entrambe nelle aree che il
limite ha lasciato fuori.

La risposta era **onesta e sbagliata**: HIRIS ha detto cosa non aveva guardato, e ciò che non aveva
guardato conteneva la risposta.

**E l'informazione era già nel suo prompt.** La sezione «Notevole adesso» del nucleo diceva, in
quel turno: `Senza area: 2 luci (acceso)`. HIRIS sapeva **che** due luci erano accese. Non sapeva
**quali** — perché la sezione era raggruppata, e lo era perché conteneva **300 elementi**.

## 0.1 Perché 300

`_STATI_NOTEVOLI` (`casa/nucleo.py:89`) è **un insieme di stringhe di stato, cieco alla tipologia**:
se lo stato è in quell'insieme, l'entità è notevole. Non guarda mai il dominio, né la classe.

Misurato sull'impianto vero (845 entità):

| cosa finisce in «notevole» | quante |
|---|---:|
| `sensor` / `switch` / … **`unavailable`** | 119 |
| `device_tracker` / `person` **`home`** | 49 |
| `automation` **`on`** (cioè *abilitata*) | 18 |
| `switch` **`on`** | 99 |
| **luci accese** | **2** |

E la scoperta che decide il disegno: **179 di quei 300 sono entità che Home Assistant stesso
dichiara non primarie** — 113 `entity_category: config`, 66 `diagnostic` — più 10 nascoste
dall'utente. HIRIS **legge già** quei campi (`casa/archivio.py:135`: `categoria`, `nascosta`,
`classe`, `disabilitata`) e il digesto ne guarda **uno solo**, `disabilitata`.

Fra i 99 `switch` accesi, **90 erano `config` o `diagnostic`**: interruttori di configurazione
delle integrazioni, non cose accese in casa.

---

## 1. Il principio

**Un vocabolario, non un filtro.**

Un filtro toglie una volta per tutte e perde una capacità: escludere `device_tracker` dal digesto
significherebbe anche non saper più rispondere a «chi è in casa?». Un vocabolario dice **cosa una
cosa è e cosa significano i suoi valori**, e lascia che sia **chi legge** a decidere se interessa —
il digesto in un modo, uno strumento interrogato in un altro, il Brain domani in un terzo.

Tre strati, nelle parole del proprietario: *«sapere di cosa si tratta, sapere cosa significano i
dati e le espressioni mostrate, e sulla base di quello fornire cosa è di interesse in base al
contesto»*.

## 1.1 Non è un oggetto nuovo: due dei tre strati esistono già

Verificato prima di progettare, ed è la ragione per cui questa fetta è piccola. In
`casa/nucleo.py`, nell'arco di sessanta righe:

| strato | cosa c'è già | stato |
|---|---|---|
| **cos'è** | `_NOMI_DOMINIO` (`:55`) — 17 domini con nome italiano | ✅ completo per l'uso attuale |
| **cosa significano i dati** | `_traduci_stato()` (`:251`) + `_CLASSI_APERTURA` (`:112`) | ⚠️ **1 famiglia su 28** |
| **cosa interessa** | `_STATI_NOTEVOLI` (`:89`) | ⚠️ **cieco alla tipologia** |

`_traduci_stato` **prende già `classe` come parametro** e la usa per porte e finestre, col
principio scritto accanto:

> *«"on"/"off" non bastano per una porta o una finestra: "acceso"/"spento" affermerebbe
> un'alimentazione che l'oggetto non ha. Per queste classi — **dichiarate da Home Assistant, non
> indovinate dal nome** — si traduce come apertura.»*

**Il vocabolario è già nato e si è fermato a cinque classi.** Questa fetta lo finisce. Nessun
modulo nuovo, nessuna tabella accanto a quelle che ci sono, nessun secondo posto da tenere
allineato.

---

## 2. Il vocabolario, derivato dalla documentazione di Home Assistant

**Nessun significato è inventato.** Le 28 classi di `binary_sensor` e il loro `on`/`off` sono
quelli documentati su `developers.home-assistant.io/docs/core/entity/binary-sensor/`, verificati il
16/08/2026.

### 2.1 Cosa significano i valori (`_SIGNIFICATO_CLASSE`)

`_CLASSI_APERTURA` — cinque classi, un solo significato — diventa una mappa
`classe -> (testo per "on", testo per "off")`:

| classe | `on` | `off` |
|---|---|---|
| `moisture` | bagnato | asciutto |
| `smoke` / `gas` / `carbon_monoxide` | fumo / gas / monossido rilevato | nessuno |
| `safety` | non sicuro | sicuro |
| `tamper` | manomissione rilevata | nessuna manomissione |
| `problem` | problema rilevato | nessun problema |
| `heat` / `cold` | caldo / freddo | normale |
| `door` / `window` / `garage_door` / `opening` | aperto | chiuso |
| `lock` | sbloccato | bloccato |
| `motion` / `occupancy` / `presence` | movimento rilevato / occupato / a casa | nessuno / libero / fuori |
| `battery` | carica bassa | normale |
| `connectivity` | connesso | disconnesso |
| `running` / `moving` | in funzione / in movimento | fermo |
| `plug` / `power` | collegato / alimentato | scollegato / non alimentato |
| `update` | aggiornamento disponibile | aggiornato |
| `light` / `sound` / `vibration` | luce / suono / vibrazione rilevata | nessuna |
| `battery_charging` | in carica | non in carica |

`_CLASSI_APERTURA` **sparisce**: le sue cinque voci sono cinque righe di questa mappa, e la logica
di `_traduci_stato` diventa una lettura invece di un caso particolare.

### 2.2 Cosa interessa nel digesto (`_NOTEVOLE_PER_TIPOLOGIA`)

`_STATI_NOTEVOLI` — un insieme piatto — guadagna la dimensione che `_traduci_stato` ha già.

**Un'entità entra nel digesto solo se è un EVENTO**: qualcosa che *sta succedendo*, non una
condizione stabile né una misura.

**Sono eventi:**

- i domini in cui l'attivo è un'eccezione rispetto al riposo: `light`, `switch`, `cover`, `lock`,
  `fan`, `media_player`, `valve`, `remote`, `siren`, `vacuum` — attivi;
- `alarm_control_panel` **solo** `triggered` (regola già presente e corretta, si conserva);
- `binary_sensor` **solo** per le classi di **allarme** (`moisture`, `smoke`, `gas`,
  `carbon_monoxide`, `safety`, `tamper`, `problem`, `heat`, `cold`) e di **apertura** (`door`,
  `window`, `garage_door`, `opening`).

> **La trappola del monossido.** La documentazione elenca le classi coi **nomi delle costanti
> Python**, e ventisette su ventotto coincidono col valore-stringa in minuscolo. Una no:
> `BinarySensorDeviceClass.CO = "carbon_monoxide"`. Scritto `co`, **un allarme monossido non entra
> nel digesto e non viene tradotto** — la classe più critica dell'elenco, muta. Verificato sulla
> sorgente (`homeassistant/components/binary_sensor/__init__.py`), non sulla pagina di
> documentazione che non riporta i valori.

**Non sono eventi, e restano fuori dal digesto** — ma *non* dal prodotto: `guarda` e `cerca` li
riportano quando li chiedi.

| famiglia | perché |
|---|---|
| `device_tracker`, `person` (`home`) | è una **condizione**: un telefono a casa è il riposo |
| `automation`, `script`, `input_boolean` (`on`) | `on` significa **abilitata**, non accesa |
| `sensor`, `number`, `weather`, `sun`, `todo` | **misure**: un numero non è un evento |
| `button`, `event`, `tag`, `notify`, `image` | **nessuno stato utile** — 57 dei 72 `button` sono `unknown` per costruzione |
| `binary_sensor` transitori (`motion`, `occupancy`, `presence`, `sound`, `vibration`, `light`, `running`, `moving`, `power`, `plug`, `connectivity`, `battery`, `battery_charging`, `update`) | veri per trenta secondi, o manutenzione |

### 2.3 I due campi che HA dichiara e che il digesto ignora

Entrano come **precondizione**, prima di ogni altra regola:

- **`categoria`** (`config` / `diagnostic`): fuori dal digesto. È Home Assistant a dire che non sono
  primarie, e la sua stessa documentazione dice che *«diagnostic and config entities are typically
  hidden from primary UI displays»*.
- **`nascosta`**: fuori. È una scelta esplicita dell'utente dentro Home Assistant, e ignorarla
  significherebbe rimetterle davanti da un'altra porta.

---

## 3. `unavailable` esce dall'«adesso», e diventa una riga

Sono 119, e oggi occupano **76 righe** del digesto. Non sono «cosa sta facendo la casa»: sono
**salute** — la fetta già progettata e non ancora scritta.

Togliere il fatto sarebbe una perdita. Ripeterlo settantasei volte è il rumore. Quindi:

> `119 entità non rispondono.`

Una riga, sempre, quando ce ne sono. Il dettaglio (quali, da quando, raggruppate per causa) è della
fetta «salute di HA», che questa non anticipa.

---

## 4. Cosa NON si tocca

- **`guarda` e `cerca`** — nessun filtro. Se chiedi una stanza vedi tutto, entità diagnostiche
  comprese. Filtrare una risposta esplicita sarebbe **nascondere**; filtrare un riepilogo è
  **scegliere cosa vale la pena dire senza che tu abbia chiesto**. Sono due mestieri diversi.
- **`_SOGLIA_NOTEVOLE_INDIVIDUALE = 15`** — resta. È una guardia corretta: se dài una festa e hai
  trenta luci accese, raggruppare è giusto. Non si tara e non si toglie: **le si toglie il motivo
  per cui scattava sempre**.
- **`_NOMI_DOMINIO`** — già completo.
- **`proxy/entity_cache._DOMAIN_ATTRS`** — conserva già `current_temperature`; nessuna estensione.
- **`exposed`** — la scheda «Expose» di Home Assistant. Vedi §6.

---

## 5. Le prove

Ogni prova deve poter **produrre** il difetto che dice di impedire, e si convalida per mutazione.

1. **Un `binary_sensor` `moisture` acceso entra nel digesto e si legge «bagnato».** *Mutazione:*
   togliere la classe dalla mappa → torna «acceso», e un allagamento diventa indistinguibile da una
   lampadina.
2. **Un `binary_sensor` `motion` acceso NON entra nel digesto** — ed è la prova gemella della
   precedente, sullo stesso dominio: senza, «filtrare per dominio» passerebbe entrambe.
3. **Un'entità `entity_category: diagnostic` non entra**, qualunque sia il suo stato. È il caso da
   179 unità.
4. **Un'entità nascosta non entra.**
5. **`automation` `on` non entra.** Caso da 18 unità.
6. **`device_tracker` `home` non entra nel digesto MA `guarda` lo riporta.** Due asserzioni nella
   stessa prova: è la differenza fra vocabolario e filtro, e senza la seconda metà avremmo
   costruito il filtro.
7. **`unavailable` produce UNA riga di conteggio, non una riga per entità.** *Mutazione:* lasciarlo
   in `_STATI_NOTEVOLI` → 76 righe.
8. **Sull'anagrafe vera dell'impianto il digesto scende sotto la soglia dei 15**, quindi il
   dettaglio individuale torna e le due luci di «Senza area» compaiono **per nome**.
9. **La soglia resta viva:** con trenta luci accese si raggruppa ancora. *Mutazione:* togliere la
   soglia → questa prova cade.
10. **`_CLASSI_APERTURA` non esiste più e porte/finestre si leggono ancora «aperto»/«chiuso».** La
    prova che l'estensione ha assorbito il caso particolare invece di affiancarlo.

**Cancelli:** suite py e js verdi in foreground, censimento a 0 opzioni non lette.

---

## 6. Cosa NON entra, e perché

1. **La lettura di `exposed`** (`homeassistant/expose_entity/list`). Verificato che il comando
   esiste, **e che restituisce solo le entità esplicitamente esposte o non-esposte**: su un
   impianto dove nessuno ha aperto quella scheda la risposta è vuota o parziale, e un filtro
   costruito su di essa direbbe a HIRIS di non guardare quasi niente. Non può essere il filtro
   primario. Entra dopo, come **informazione in più**.
2. **L'opzione utente** «guarda tutto / filtra tu / solo ciò che ho esposto». Decisa la forma,
   rimandata: prima HIRIS deve saper filtrare bene da solo, altrimenti l'opzione offrirebbe una
   scelta fra due comportamenti di cui uno solo funziona.
3. **Il significato attaccato alle risposte di `guarda`.** Un buon modello sa già che
   `moisture: on` è una perdita; è il **codice** a non saperlo, ed è il codice a comporre il
   digesto. Se un giorno servirà, la mappa è già lì.
4. **La salute di Home Assistant.** Riparazioni, integrazioni cadute, il dettaglio delle
   irraggiungibili: fetta sua, già brainstormata.
5. **`get_history` e «da quanto è accesa».** Emersi confrontando i progetti IA per HA (Power LLM
   implementa esattamente questo, e `proxy/entity_cache._to_minimal` **butta via `last_changed`**).
   È una capacità mancante e va aperta come fetta propria.

---

## 7. Il metro della fetta — corretto da una misura

La prima stesura diceva: *«deve nominare le due luci accese in Senza area»*. **È sbagliato**, e
scoprirlo ha richiesto di guardare i metadati invece del solo stato: quelle due luci hanno
**`nascosta: 1`** — il proprietario le ha nascoste dentro Home Assistant.

Quindi il digesto **deve** tacerle, e da questa fetta lo fa **per la ragione giusta**: rispetta una
scelta esplicita dell'utente. Prima taceva per la ragione sbagliata — aveva esaurito i giri di
strumento. Due cause diverse che producevano la stessa frase, ed è esattamente il tipo di
coincidenza che nasconde un difetto.

Il metro vero, misurato sull'anagrafe dell'impianto (842 entità, 16 aree) facendo girare
`componi()` sui dati veri:

| | prima | dopo |
|---|---:|---:|
| elementi nel digesto | **300** | **12** |
| caratteri della sezione | ~2.900 | **549** |
| dettaglio individuale | no, raggruppato | **sì, per nome** |
| irraggiungibili | 76 righe | **1 riga** |

E le voci che restano sono cose vere: la lavatrice e l'asciugatrice accese in lavanderia, il forno
e la lavastoviglie in cucina, il televisore in soggiorno.

**Dopo il rilascio**, sull'impianto: la domanda del §0 deve ottenere una risposta **senza che HIRIS
chiami un solo strumento** e **senza dichiarare di aver esaurito i giri**. Se poi si chiede
esplicitamente delle luci nascoste, `cerca` e `guarda` le trovano — perché non filtrano, ed è la
metà del disegno che rende questo un vocabolario e non un filtro.
