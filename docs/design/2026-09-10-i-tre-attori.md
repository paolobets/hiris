# La conoscenza di HIRIS — il lettore, l'osservatore, l'analista

`spec · 10/09/2026 · sostituisce l'impianto proposto in docs/design/2026-09-09-il-sapere-di-hiris.md`

Questa spec nasce dalla consegna del 09/09 e **la corregge in sei punti**. Ogni correzione viene da
una misura fatta sul repository alla `3.23.2` o sulla casa vera fra il 09 e il 10/09/2026 — nessuna
viene da un'opinione di disegno, e ogni numero qui dentro è stato contato, non stimato.

Il vincolo che governa tutto resta il §0 della consegna: **HIRIS verrà distribuito ad altri
utenti**, e ogni scelta si giudica anche così — *«cosa succede a chi installa HIRIS su una casa che
non abbiamo mai visto?»*

---

## §0 · Le sei correzioni alla consegna

**1. Il problema non è il riconoscimento. Home Assistant riconosce già, e meglio di noi.**
Le sette entità del solare — il caso che ha fatto nascere lo sprint — portano ciascuna un
`translation_key` parlante (`power_charging`, `energy_generating_today`, …). Su 833 entità vive:
**100% ha un `unique_id`**, **89% un `original_name`**, **64% un `translation_key`**, e **nessuna è
priva di tutti e tre**. I 241 dispositivi dichiarano il produttore nel **99%** dei casi e il modello
nel **96%**. Le **70 entità (8%)** che non hanno né classe né `translation_key` né un nome che
aggiunga qualcosa al nome del dispositivo sono, all'esame, **l'unica entità del loro dispositivo** —
`light.lampadario`, `camera.ingresso_cancellino` — dove il dominio dice già tutto.

**2. Il difetto è che HIRIS guarda una copia impoverita.**
`casa.db` copia il registro di Home Assistant e **butta via** `translation_key`, `unique_id`,
`original_name`, e non espone il **dispositivo** come oggetto: nell'albero che HIRIS pubblica,
`dispositivo_id` compare 1.227 volte come stringa opaca e **non c'è un solo oggetto dispositivo**.
La prova definitiva è che l'unico pezzo che riconosce i ruoli — `ha_client.energy_directions()` —
funziona perché **scavalca `casa.db` e legge il registro dal vivo**.

**3. Il ruolo dell'energia non va inventato: esiste già, ed è prigioniero.**
`mind/facts.py:88` porta i sette ruoli (`produzione`, `autoconsumo`, `immissione`, `prelievo`,
`carica`, `scarica`, `consumo`) e `ha_client.py:1926` li assegna a tutte e 14 le entità
dell'inverter, con la provenienza scritta accanto a ciascuna. Ha **due soli chiamanti**, entrambi
nel giro notturno: il ruolo finisce nel corpo di un oggetto e **non esce da nessuna porta**.
Quarta fondamenta violata alla lettera.

**4. Le gambe e il pavimento vanno via.**
Il pavimento seleziona per **grandezza fisica**; l'obiettivo chiede per **fenomeno**. Da qui: cinque
prese di luci natalizie dentro (misurano kWh), forno, lavatrice, lavastoviglie e asciugatrice fuori
(sono interruttori), 50 luci fuori, il termostato dentro **due volte** (come `climate` e come
`sensor.temperature`), e la gamba `dispersione` **vuota — zero entità** — perché è definita sulle
finestre invece che sul fenomeno.

**5. La ragione che giustificava il pavimento è caduta, ed è misurabile.**
`baseline.py` lo giustifica così: *«ciò che non si è osservato non esiste più»*. Misurato: Home
Assistant tiene **7 giorni** di grezzo per tutto, e **statistiche che non scadono** per le 130
entità (16%) con `state_class`. La frase è **falsa per sempre sul 16%** e **falsa per una settimana
sull'84%**.

**6. Lo scope è dell'osservatore.**
Decisione del proprietario, 09/09, che conferma quella del 25/08 (*«trasparenza al posto del
permesso»*). La terza legge la impone: un osservatore che non può scegliere cosa guardare non
ragiona — è un'automazione, e la prima legge direbbe di farla in Home Assistant.

---

## §1 · Le misure

Tutte fatte fra il 09 e il 10/09/2026, su `192.168.1.95` (HA `2026.9.1`) e sul repository alla
`3.23.2`.

### La casa

| | |
|---|---|
| entità con stato · nel registro · non disabilitate | **837** · 1.225 · **833** |
| dispositivi · con entità vive | **241** · 221 |
| piattaforme (integrazioni) | **38** |
| con `unique_id` · `original_name` · `translation_key` | **833 (100%)** · 740 (89%) · **536 (64%)** |
| prive di tutti e tre | **zero** |
| dispositivi con produttore · con modello · rinominati dall'utente | 239 (99%) · 231 (96%) · 13 |
| integrazioni con documentazione pubblica su `home-assistant.io` | **32 su 38** |
| le sei senza | `zcsazzurro` · `ave_domina` · `spook` · `hacs` · `lepro_led` · `alarmo` — **171 entità (21%)** |
| entità con `state_class` (statistiche che non scadono) | **130 (16%)** |
| entità che sono **contatori** (`energy`/`power`/`gas`/`water`) | **30 (3,6%)** |
| dispositivi con **due o più** contatori — cioè con un bilancio | **3** |

### Le letture da Home Assistant

```
config/area_registry/list        5 ms      4 KB      15 aree
config/device_registry/list     21 ms    175 KB     241 dispositivi
config/entity_registry/list     56 ms    732 KB   1.225 entità
get_states                      35 ms    367 KB     837 stati
─────────────────────────────────────────────────────────────
sette comandi                  130 ms   1,28 MB
```

Tutta la casa, resa in una riga per entità (nome, dispositivo, area, classe, unità, `state_class`,
`translation_key`, produttore): **97,5 KB ≈ 25.000 token**. Ci sta in una chiamata sola.

Memoria di Home Assistant: **7 giorni** di grezzo (verificato su tre entità: tutte partono dallo
stesso giorno), statistiche orarie **28 giorni** su questa casa (dal 13-14/08, cioè da quando
esistono) e **senza scadenza** per il 16% delle entità. `person.*`: statistiche **vuote**.

### Cosa scrive l'osservatore oggi

```
pavimento                                                 88 entita (11%)
per gamba   chi c'e' 26 · energia 26 · comfort 25 · buono stato 6 · sicurezza 5 · dispersione 0

eventi state_changed in 24 ore                        29.227 righe/giorno
  – cio' che HA riassume gia' (state_class, 45 entita)  −17.773
  – i doppioni da attributo (da == a, oggi NON filtrati) − 6.503
  ─────────────────────────────────────────────────────────────
  RESTA                                                  4.951 righe/giorno   (−83%)

a 22 giorni:   642.994 righe / 74 MB   ->   108.922 righe / 12,5 MB
```

Gli **otto termostati** producono **6.446 righe al giorno, di cui 8 vere** — un solo cambio di stato
ciascuno in 24 ore — e **non producono nessun oggetto**.

### Cosa produce l'osservatore oggi

Cinque giorni misurati (`GET /api/mind/facts?day=…`):

```
03/09  25 oggetti   guasto 4   energia 17   presenza 4
05/09  31 oggetti   guasto 3   energia 17   presenza 10   sicurezza 1
07/09  45 oggetti   guasto 22  energia 17   presenza 6
08/09  29 oggetti   guasto 4   energia 17   presenza 8
09/09  29 oggetti   guasto 6   energia 17   presenza 6
```

`energia` è **sempre esattamente 17** — un frammento per ciascuna entità dell'inverter, ogni
giorno, per sempre. **`bilancio`: zero in tutti e cinque i giorni.** **`funzionamento`: zero.**

### Il sapere del prodotto, dov'è

| dove | quanto | cosa |
|---|---|---|
| `type_vocabulary.py` | **76 righe** (41 domini, 35 coppie) | il giudizio: a quale gamba serve un tipo |
| `ha_vocabulary.py` | **27 voci** di `DEVICE_CLASS_MEANING` | copiate a mano da HA |
| `ha_client._DIRECTION_BY_TRANSLATION_KEY` | **14 righe**, **una** integrazione | i sette ruoli dell'energia |
| **archivi** | **zero** | i tre moduli non contengono nessun `sqlite3` né `CREATE TABLE` |

Contro le 27 voci copiate a mano, Home Assistant spedisce **87 chiavi** per `binary_sensor` e **72**
per `sensor` — nella lingua dell'utente, alla versione installata — più **1.730 chiavi** di
traduzioni delle integrazioni, di cui **37 di `zcsazzurro`**.

### Gli archivi

Nove vivi (`casa`, `osservazioni`, `memoria`, `promesse`, `costruzioni`, `azioni`, `consumi`,
`chat_history`, `reasoning`) più otto nomi morti che il codice **nomina solo per scriverlo nel log**
e non apre mai. `ATTACH` **non compare mai**: i nove non si possono unire in una query, e ogni
collegamento è scritto a mano in Python. `storage.py::connect()` accende già
`PRAGMA foreign_keys=ON` su tutti e nove — chiavi esterne **accese e inutilizzabili**, perché fra
file diversi non si dichiarano.

### Il modello

**126 richieste in 18 giorni** (22/08 → 09/09), 8,9 M token, quasi tutti di cache. Circa **sette
richieste al giorno**.

---

## §2 · Le tre sostituzioni — smettere di copiare

Lo stesso difetto a tre livelli: **una copia a mano di qualcosa che l'installazione già possiede.**

| superficie | padrone vero | come si sostituisce |
|---|---|---|
| **`casa.db`** | Home Assistant | si legge dal vivo (80 ms) **senza buttare niente**, col dispositivo come oggetto |
| **`ha_vocabulary.DEVICE_CLASS_MEANING`** | Home Assistant | `frontend/get_translations`, che HIRIS **chiama già** |
| **`_DIRECTION_BY_TRANSLATION_KEY`** | l'integrazione | il `translation_key` del registro, letto e interpretato una volta |

**Effetto collaterale che chiude un difetto della consegna (§5).** Il censore considera
«classificata» una coppia che sta in `DEVICE_CLASS_MEANING` — **27 voci copiate a mano** — ed è per
questo che **43 delle 62 classi di `sensor` non sono mai state chieste**. Cambiata la fonte, il
difetto si chiude da sé.

**Cosa NON si sostituisce, e adesso con un numero:**

- **`osservazioni.db`** — HA tiene 7 giorni, HIRIS 22; e per l'**84%** delle entità oltre una
  settimana **in HA non esiste niente**.
- **`memoria.db`** — ciò che l'utente ha detto non è in nessuna API.
- **`type_vocabulary.py`** — nessuna API di HA sa dire a cosa serve un tipo. È l'unica cosa
  davvero nostra, ed è di 76 righe.

---

## §3 · L'impianto

```
Home Assistant
     │  letto per intero, 80 ms, senza buttare niente
     ▼
IL LETTORE ─────────────────────────────────────────────▶ la casa, come HA la conosce
                                                                    │
                              L'OSSERVATORE la guarda tutta contro l'obiettivo
                              e decide cosa pesa — nessuna gamba, nessun pavimento
                                                                    │
                              registra SOLO cio' che HA non riassume        (−83%)
                              esegue le RICETTE, che usano le OPERAZIONI
                                                                    │
                                                    RESOCONTO GIORNALIERO
                                              misure (piccole) + cronaca (grande)
                                                                    │
                              L'ANALISTA lo legge, riconosce i tre INNESCHI,
                              e solo allora scava — in HA o nelle osservazioni
```

**Due attori e una lettura.** Il catalogatore della consegna **non sopravvive come attore**: ciò che
doveva riconoscere, Home Assistant lo dichiara già. Resta una domanda al modello dove c'è un
bilancio da interpretare — **tre dispositivi, in questa casa** — e quella domanda la pone
l'osservatore.

---

## §4 · Il lettore

Sostituisce `casa.db`. Legge i registri dal vivo e costruisce il dizionario `home_space` che il
resto del prodotto già usa.

**Non cambia nessuno dei suoi lettori.** `queries.py` — `search`, `view`, `hierarchy`,
`_view_entity`, `_view_device` — contiene **zero SQL**: sono funzioni pure sopra un dizionario. Anche
`briefing.compose()` è pura. `store.read()` ha **16 chiamanti**, `store.replace()` **uno**. Non è un
refactor: **è cambiare il fornitore di un dizionario.**

**Cosa il lettore porta in più di oggi:**

- `translation_key`, `unique_id`, `original_name` su ogni entità;
- **il dispositivo come oggetto** — con produttore, modello, nome dato dall'utente, area, e le sue
  entità sotto di sé;
- **gli attributi che le ricette chiedono** — vedi §5.

**Cosa si perde, ed è dichiarato:** con Home Assistant irraggiungibile HIRIS oggi risponde ancora
sulla struttura, leggendo l'ultima copia buona. Senza copia, non risponde. Vale poco (con HA giù non
può né guardare né agire) ma **è una scelta, non una scoperta**.

**Un residuo che resta nostro: l'impronta.** *«È comparsa un'entità nuova»* non è una domanda che HA
sappia rispondere: lo si sa solo confrontando con com'era. Serve **un'impronta di com'era la casa**,
non una copia dell'anagrafe — ed è l'innesco dell'anello. Il `confronto` di oggi **non è** questo
(`topology.py:1195` è una funzione pura che confronta le aree adesso).

---

## §5 · L'osservatore

**Esiste, gira, e non si rifà: si collega.** Ma smette di essere un filtro.

### 5.1 Si dà lo scope da sé

Guarda **tutta la casa** — 25.000 token, una chiamata — con l'obiettivo davanti, e decide cosa pesa.
Nessuna gamba, nessun pavimento, nessuna lista.

**Decide, e lo dice.** Esiste una pagina che dichiara **cosa guarda, da quando e perché**, e da cui
gli si può togliere qualcosa. Quella pagina è anche la prova che l'obiettivo è stato capito
(§11): **non sono due cose**.

**Quando gira:** al primo avvio, quando cambia l'obiettivo, quando compare qualcosa di nuovo, e a
una **cadenza di riconsiderazione**.

### 5.2 La cadenza sostituisce il pavimento

> **L'osservatore riconsidera l'intera casa più spesso di quanto duri la memoria di Home Assistant.**

Se ripensa il suo campo entro quella finestra, tutto ciò che aveva scartato è ancora recuperabile.
E la finestra **non si assume: si misura** — si chiede a HA quanto indietro arriva la sua storia
(**7 giorni** su questa casa) e la cadenza si adegua. **Nessuna costante nel codice.**

### 5.3 Le due regole di scrittura

1. **Ciò che Home Assistant riassume già (`state_class`) non si registra a campione: si legge dalle
   statistiche.** Sono più corrette (gestiscono gli azzeramenti) e durano più a lungo dei nostri
   22 giorni. È già la scelta di `build_balances`, con la motivazione scritta accanto: si smette di
   applicarla ai soli bilanci. **−17.773 righe/giorno.**
2. **Non si scrive una riga dove `da == a`.** Home Assistant emette `state_changed` anche per un
   attributo, e oggi non c'è nessun filtro: gli otto termostati scrivono 6.446 righe al giorno per
   8 cambi veri. **−6.503 righe/giorno.**

**Insieme: da 29.227 a 4.951 righe al giorno (−83%), e da 74 a 12,5 MB sui 22 giorni.**

### 5.4 Gli attributi

**Il fatto vive spesso in un attributo, non nello stato.** Lo stato di un termostato è `heat` e resta
`heat`; `hvac_action` dice `idle`/`heating`, `temperature` dice l'obiettivo, `current_temperature`
dice dove si è. **È per questo che l'esempio fondativo del documento del cervello — «il
riscaldamento parte alle 15:30, la casa è calda alle 16:30» — oggi non è rispondibile.**

Oggi il grezzo conserva **tre attributi fissi** scelti a mano (`device_class`, `state_class`,
`source_type`). **Quali attributi valgono la pena dipende dal dispositivo**: lo dice la **ricetta**,
non una lista nel codice. E costa meno di oggi — i termostati passerebbero da 6.446 righe inutili a
poche decine utili.

### 5.5 Cosa NON fa

Non dice cosa **significa** ciò che ha visto, né cosa **fare**. Il giudizio sta nell'aggregazione,
rifacibile finché il grezzo c'è.

---

## §6 · Le operazioni

Un **registro** — `operations` — di ciò che il sistema sa calcolare. Chiuso e versionato. Ogni
operazione dichiara, e non si può costruire senza:

```
nome           somma_periodo
ingressi       entita (una o piu', stessa unita') · periodo
restituisce    un numero · la sua UNITA' · la COPERTURA (quanta parte del periodo aveva dati)
rifiuta se     l'entita' non ha statistiche · il periodo e' fuori dalla memoria disponibile
```

**La copertura rende il set onesto.** Sotto una soglia di copertura il risultato diventa **«non
calcolabile, e perché»** — mai un numero plausibile. Il precedente è già stato pagato: `_difference`
con un punto solo restituiva `0.0`, cioè *«non è cambiato niente»* travestito da dato, corretto in
`None`.

**Il set non si dimensiona a preventivo: si chiude con un test.** *È abbastanza ricco quando le
quattro domande vere del proprietario e il resoconto giornaliero si esprimono tutti senza
aggiungerne una.* Provato su quelle domande, sono **quindici**:

| | operazione | serve a | oggi |
|---|---|---|---|
| 1 | `episodio` | «acceso 15:30-17:05» | c'è |
| 2 | `tempo_in_stato` | quanto in totale | parziale |
| 3 | `quante_volte` | quante accensioni | no |
| 4 | `quando_succede` | a che ore capita | no |
| 5 | `somma_periodo` | i sette totali dell'energia | c'è |
| 6 | `media_min_max` | la temperatura tipica | parziale |
| 7 | `primo_ultimo_differenza` | i contatori grezzi | c'è |
| 8 | `per_ora` | il profilo delle 24 ore | c'è |
| 9 | `misure_durante` | «mentre scaldava, da 18 a 21» | **c'è — la più potente** |
| 10 | `correlazione` | batteria ↔ produzione ↔ meteo | **no** |
| 11 | `quota` | l'autosufficienza | c'è |
| 12 | `differenza_fra` | consumo − prelievo | c'è |
| 13 | `confronto_periodi` | oggi contro ieri | no |
| 14 | `tendenza` | dove sta andando | no |
| 15 | `somma_entita` · `raggruppa_per` | tutte le luci di un'area | no |

**Nove su quindici esistono già**, implicite dentro `mind/facts.py`. Le sei nuove nascono ciascuna
da una domanda posta davvero, non da un preventivo.

---

## §7 · Le ricette

Una **ricetta** è *come si calcola una cosa* per un dispositivo. **Non è codice: è un dato**, e il
codice sa eseguirlo.

```
RICETTA   inverter con accumulo — zcsazzurro
perche'   pesa su «risparmio energetico»: e' la fonte e l'accumulo di casa
passi:
  1  prodotta        = somma_periodo(…energia_prodotta_oggi,   giorno)   ->  23,71 kWh
  2  consumata       = somma_periodo(…energia_consumata_oggi,  giorno)   ->  14,01 kWh
  3  prelevata       = somma_periodo(…energia_importata_oggi,  giorno)   ->   0,11 kWh
  …
  7  autosufficienza = quota(differenza_fra(consumata, prelevata), consumata)  ->  0,99
  8  quando_produce  = per_ora(…potenza_prodotta, media, 7 giorni)
```

**È una sequenza di passi con nomi**, non un linguaggio: un passo può leggere il risultato dei passi
precedenti, e nient'altro. **Niente cicli, niente condizioni, niente funzioni nuove.** Una ricetta si
può leggere tutta, provare, e **rifiutare prima di eseguirla**.

**Chi la scrive.** L'osservatore, quando decide che un dispositivo pesa e non ha una ricetta per lui,
chiede al modello — **una volta, non ogni giorno** — mostrandogli il dispositivo con **tutte le sue
entità insieme** e l'obiettivo. Viste insieme, le sette misure di un inverter si spiegano da sole;
viste una alla volta sono sette indovinelli.

**Come si valida.** Il codice la verifica e, se non è valida, **la rifiuta — non la corregge**. Ogni
passo deve nominare un'operazione che esiste, entità che esistono, un periodo ben formato. Il
precedente della disciplina è `type_vocabulary.Field`, che non si può costruire senza provenienza:
*«una prova dice che oggi nessuno l'ha fatto, il costruttore dice che non si può fare»*.

**Dove vive: nel sapere** (§8), con provenienza e prove.
- *«Un inverter `zcsazzurro` si misura così»* → soggetto **integrazione**, **universale**, si esporta.
- *«In questa casa il contatore generale è `sensor.gestione_carichi_power`»* → soggetto **entità**,
  **locale**, non esce.

**Cosa una ricetta NON fa:** non decide se una cosa conta (è il giudizio dell'osservatore contro
l'obiettivo), non inventa numeri, non scrive in Home Assistant, non fa fare i conti al modello.

**Perché conta, con una prova storica.** Il 27/08 è stata corretta la quota di autosufficienza:
`autoconsumo/(autoconsumo+prelievo)` era sbagliata perché su *quella* integrazione «autoconsumata»
esclude la batteria — misurato **0,964 invece di 0,985**, e con più ciclo **0,167 invece di 0,41**.
Era **una ricetta specifica di un'integrazione, scritta dentro il motore di aggregazione.** Come
dato sarebbe stata correggibile senza un rilascio, visibile a chi legge il sapere, ed esportabile
corretta a chiunque abbia quell'inverter.

---

## §8 · Il sapere

Una casa sola per ciò che HIRIS ha capito, con **il soggetto come colonna**:

```
soggetto_genere  'tipo' | 'integrazione' | 'entita'
soggetto         'sensor' · 'sensor.power' · 'zcsazzurro' · 'sensor.ze1…_potenza_carica'
campo            'ruolo' · 'ricetta' · 'gamba' · 'riposo' · 'significato' · 'come_si_comanda'
valore
provenienza      'chiesto' | 'importato' | 'nostro' | 'dedotto' | 'ereditato'
verifica         'confermata' | 'non_confermabile' | 'non_capito' | NULL
prove            cosa e' stato letto per dedurlo
fonte            la citazione, con la versione, quando la verifica ha confermato
chi, quando_ts   quale modello, e quando
PRIMARY KEY (soggetto_genere, soggetto, campo)
```

**I due assi restano due.** `provenienza` dice **da dove viene**, `verifica` dice **cosa ha detto il
controllo**. Un campo `nostro` non è né confermato né dedotto: è un giudizio che HA non può darci, e
`verifica` per lui è `NULL`. Fonderle in una parola sola sarebbe il difetto che questo progetto ha
già pagato sei volte.

**`ambito` NON è una colonna**: sarebbe un doppione. `tipo` e `integrazione` sono universali per
natura, `entita` è di questa casa.

**La regola che non si negozia:** *una deduzione non diventa mai un fatto.* Tre esiti distinti —
**confermata** (l'installazione o la documentazione lo dicono) · **non confermabile** («autoconsumata»
è un'invenzione dell'integrazione e non esisterà mai in HA) · **non capito**, che **si scrive**.

**Le tre fonti della verifica, e nessuna siamo noi:**

1. **ciò che l'integrazione dichiara di sé, dentro l'installazione** — `frontend/get_translations`
   (già usata), `translation_key`, `original_name`, `device_class`, il registro dei servizi, il
   manifest. **Copre tutte, custom comprese.** È la fonte che porta il carico.
2. **la documentazione pubblica di Home Assistant**, letta **da casa dell'utente** — copre **32
   integrazioni su 38**.
3. **il modello**, dove le prime due tacciono. Sempre `dedotto`, mai promosso a fatto.

`ha_vocabulary.py` **retrocede**: resta il seme di ciò che HA documenta sui tipi, e smette di essere
un verificatore.

**Il repo diventa il seme.** Le **76 righe** del vocabolario dei tipi e le **14** delle direzioni si
caricano all'avvio con la loro provenienza: restano scritte, riviste, linterate e in git — e la casa
scrive sopra.

---

## §9 · Il resoconto giornaliero

**Due strati, non tre.**

```
grezzo del giorno   ->  scade      (finestra misurata sulla memoria di HA)
resoconto giornaliero -> resta
```

Gli `oggetti` **spariscono come strato separato**: gli episodi vivono dentro il resoconto del giorno.
Non è una perdita — è una constatazione: `genre_for(subject, aspect_)` **prende la gamba in
ingresso**, quindi tolte le gambe quello strato non ha più sorgente; e misurato su cinque giorni
produce 25-45 oggetti di cui **17 sempre uguali**, con `bilancio` e `funzionamento` **a zero**.

**Rifare un giorno** = rieseguire le ricette sul grezzo. Sbagliare costa **un giorno**, non tutto —
esattamente la promessa del documento del cervello.

**Il resoconto ha due parti, e la separazione è funzionale:**

| parte | contiene | dimensione | come si legge |
|---|---|---|---|
| **le misure** | i numeri delle ricette, ciascuno con operazione, unità, periodo, **copertura**, e **ciò che non si è potuto calcolare, e perché** | decine di numeri | **in serie**, molti giorni insieme |
| **la cronaca** | gli episodi del giorno | grande | **un giorno alla volta**, a richiesta |

Trenta giorni di **misure** stanno in un prompt; trenta giorni di cronaca no. È questa separazione
che rende possibile all'analista *«vedere la variazione e poi scavare»*, ed è la ragione per cui
**«le porzioni» smettono di essere un problema da risolvere**: il resoconto *è* la porzione.

---

## §10 · L'analista

Legge i resoconti e dice **cosa si potrebbe fare**. Non osserva e non cataloga.

### I tre inneschi

**1 · Qualcosa è cambiato**, e **non è spiegato da ciò che già sappiamo.**
L'autosufficienza è passata da 99,2% a 61,3% il 09/09 — ma è **spiegata dal meteo**: è una conferma,
non una scoperta. Lo stesso crollo in una giornata di sole sarebbe una notizia. È a questo che serve
l'operazione `correlazione`.

**2 · Qualcosa è stabile e costa.**
Misurato: la batteria satura al **90% alle 13-16** mentre l'impianto produce ancora 2.600-3.100 W, e
si esportano **~10 kWh al giorno** mentre di notte se ne riprendono **4** dalla batteria. **Nessuna
variazione, e il valore più alto di tutta la prova.** Un analista che guardasse solo ciò che cambia
non lo troverebbe mai.

**3 · Qualcosa non c'è più.**
La copertura di una misura crolla, o una misura smette di essere calcolabile. Il caso vero:
**`bilancio` a zero da cinque giorni su cinque, e nessuno se n'è accorto.**

### I vincoli

- ***«Non si inventa una soglia: si archivia e si interpreta»*** (09/09). Lo scostamento si misura
  contro la storia di quel dato, non contro un numero scelto da noi — e con 28 giorni di storia
  **va detto che la base è sottile**.
- **Se una cosa funziona non va segnalata.** Otto giorni al 99% non sono una notizia.
- **Il codice calcola, il modello sceglie.** Il codice produce valore, storia, scostamento,
  copertura e le serie correlate disponibili; il modello dice **cosa merita di essere detto e
  perché**. Stesso schema delle ricette: **un meccanismo solo per due problemi**.

### Cosa produce

Poche cose dette bene, ciascuna con: **cosa** ha visto (col numero e la sua copertura) · **perché**
lo dice (quale innesco) · **se è spiegato** · **cosa cambierebbe** rispetto all'obiettivo.
**Il silenzio è un esito legittimo.**

### Il costo di «da lì in avanti», e la sua mitigazione

Il §1 della consegna lo chiama una condanna. Misurato, è una condanna **parziale**: per il 16% delle
entità le statistiche di HA non scadono, e per tutte le altre ci sono 7 giorni. L'analista deve
**dire quale dei due casi è** — *«da oggi in avanti»* oppure *«ho recuperato N giorni da HA»* — e mai
lasciarlo implicito.

---

## §11 · L'obiettivo

**Testo libero, più una pagina che dice cosa HIRIS ha capito.**

È **l'unica manopola** (25/08), e il vincolo è esplicito: *«non deve diventare un prodotto con mille
configurazioni»*. Quindi niente pesi, niente priorità, niente caselle. **L'unica configurazione che
resta è togliere**: dalla pagina si può levare qualcosa a ciò che l'osservatore ha scelto.

**La difesa contro il testo vago non è vincolare il testo: è rendere visibile la comprensione.**
Scrivi l'obiettivo, HIRIS risponde con **cosa guarderà e perché**, dispositivo per dispositivo. Se ha
capito male si vede subito. **Quella pagina è la stessa della trasparenza (§5.1)**: la prova che
l'obiettivo è stato capito *è* l'elenco di ciò che viene osservato.

E costa poco: la casa intera in un prompt è **25.000 token**, quindi al primo avvio, su una casa
sconosciuta, HIRIS dice *«ecco cosa guarderò»* **subito** — senza questionario. È l'argomento con cui
si giustifica l'autonomia dell'osservatore.

**Quattro conseguenze:**

1. **È datato, e la sua storia conta.** Se cambia, i resoconti precedenti rispondono a un'altra
   domanda: chi legge trenta giorni di misure deve **sapere** che al giorno 20 l'obiettivo è
   cambiato, o legge una tendenza dove c'è un cambio di domanda.
2. **Cambiarlo non butta via nessuna ricetta.** Una ricetta dice *come si misura*, non *se conta*.
3. **Non riparte da zero**: l'osservatore recupera all'indietro ciò che HA ha, e dichiara quanto.
4. **Il default esiste già**: *«ottimizzare la casa e renderla confortevole»* (25/08).

**Fuori da questo sprint, ma nominato: il multiutente.** *«Paolo ha freddo a 20°, Marta ha caldo:
due fatti veri, non un conflitto»* — e questa casa ha davvero `person.paolo_bettinelli` e
`person.marta`. L'obiettivo come testo libero **può già portare il fatto**; **risolverlo** è materia
dell'attuatore, che non esiste.

---

## §12 · La distribuzione

**Il sapere resta locale ed è esportabile a mano.** Nessun canale automatico, nessun dato che parte
senza un gesto esplicito. Un catalogo comune fra le case resta possibile **dopo**, come trasporto che
si aggiunge — non come casa da rifare.

**L'export è `WHERE soggetto_genere IN ('tipo','integrazione')`** — non una funzione di ripulitura da
tenere aggiornata: non può dimenticarsi un campo nuovo, e la casa universale **non ha mai contenuto
niente di locale**.

**`ereditato` è la quinta provenienza**: *dedotto qui* e *dedotto altrove e importato* non sono la
stessa cosa.

---

## §13 · Cosa si distrugge

| esce | dove va |
|---|---|
| `casa.db` | **cancellato** — l'anagrafe si legge dal vivo, e più ricca |
| le **gambe** (`ASPECTS`, `aspect_of`, le 42 righe che le assegnano) | il giudizio di rilevanza passa all'osservatore, contro l'obiettivo |
| il **pavimento** (`baseline.in_baseline`, `baseline.aspect`) | sostituito dalla **cadenza di riconsiderazione** |
| gli **`oggetti`** come strato separato | episodi dentro il resoconto giornaliero |
| `genre_for` e i sei **generi** | il resoconto nasce dalle ricette, non da un elenco fisso |
| `_DIRECTION_BY_TRANSLATION_KEY` (`ha_client.py:1916`) | 14 righe di sapere, soggetto `integrazione` |
| `DEVICE_CLASS_MEANING` (27 voci) | letto da `frontend/get_translations` |
| `type_vocabulary.py` come **casa** | resta come **seme**: 76 righe caricate all'avvio |
| `home_space/store.py::replace()` che cancella tutto | non serve più |
| l'assenza del filtro `da != a` | filtro aggiunto (**−22%** da solo) |

**E i test si smontano insieme a ciò che testavano** — è la regola della review totale, e qui vale
in pieno: le asserzioni che difendono gambe, pavimento e generi difenderebbero ciò che abbiamo
deciso di togliere.

---

## §14 · Sostenibilità

| faccia | esito |
|---|---|
| **volume di scrittura** | **−83%**: da 29.227 a 4.951 righe/giorno; da 74 a 12,5 MB sui 22 giorni. E l'osservatore può allargarsi molto senza esplodere: ciò che è numerico con `state_class` costa **zero righe**, e **439 entità su 837 non cambiano mai in 24 ore** |
| **costo del modello** | oggi **7 richieste/giorno**, 8,9 M token in 18 giorni (quasi tutti di cache). La casa intera in un prompt è 25.000 token, e succede di rado — vedi sotto |
| **carico su HA** | 80 ms per i registri completi, su connessione già aperta. I job girano ogni 2-15 minuti. Rumore di fondo |
| **crescita nel tempo** | i resoconti crescono, il grezzo no (finestra). Da decidere in implementazione: se anche i resoconti abbiano una finestra, e quale |

### Il costo del modello non è un vincolo di piattaforma: è una misura da fare

**I canali esistono già tutti e cinque** — `handlers_models.py:372` dichiara `subscription`,
`claude`, `openai`, `openrouter`, `ollama` — quindi chi installa HIRIS **sceglie**: abbonamento se
ce l'ha, API a token se preferisce, e OpenRouter o un modello locale se vuole spendere meno. Non
c'è nessuna decisione di piattaforma da prendere in questo sprint.

**Quello che va fatto è misurare, per fetta, quanto consuma davvero ciascun momento del sistema** —
lo scope dell'osservatore (la casa intera in un prompt), la scrittura di una ricetta, il resoconto
giornaliero, il giro dell'analista — **separando input, output e cache**, che hanno prezzi molto
diversi e su questa casa sono già oggi 8,9 M di token di cui **6,45 M letti da cache**.

Da quella misura si vede **dove si può ottimizzare**, e le leve sono note: la cache (il prompt della
casa è quasi identico fra un giro e l'altro, quindi è materiale da cache), la **cadenza** (lo scope
si ripensa a intervalli, non di continuo), e il **modello giusto per il momento giusto** — la catena
esiste già e oggi manda 118 richieste su 126 a un modello piccolo.

**Il tetto va dichiarato in prodotto**, non stimato qui: l'utente deve poter vedere quanto consuma e
poterlo limitare. `consumi.db` e la pagina dei consumi esistono già; manca il limite.

---

## §15 · Cosa resta aperto

**Da verificare prima di costruirci sopra:**

- **`bilancio` è a zero in cinque giorni su cinque.** La fetta del 27/08 esiste per unire i 17
  frammenti in un oggetto e in produzione non ne produce nessuno. Va capito **perché**, prima che il
  resoconto ci si appoggi.

**Da decidere in implementazione:**

- la forma esatta delle sei operazioni nuove e la soglia di **copertura** sotto la quale un
  risultato diventa «non calcolabile»;
- **quanto dura il grezzo.** Oggi 22 giorni. Deve essere **almeno** la cadenza di riconsiderazione
  (§5.2), perché un giorno si rifà solo finché il suo grezzo esiste; con le due regole di scrittura
  costa 12,5 MB a 22 giorni, quindi allungarlo è economico. Il numero va scelto, non ereditato;
- la **migrazione**: cosa succede ai 22 giorni di `cambi` e agli `oggetti` storici;
- il **formato dell'export** del sapere universale;
- il **consumo per fetta** (input / output / cache separati) e il **limite di spesa** che l'utente
  deve poter vedere e imporre — §14;
- il **cancello**: chi difende che il registro delle operazioni resti chiuso e che un modulo scriva
  solo le sue tabelle. A occhio su 43.000 righe non è eseguibile — `scripts/censimento.py` esiste
  per questo.

**Fuori da questo sprint, nominati:**

- **le sicurezze** — per regola del proprietario (7/08) si derivano **dopo** le strutture, dai rischi
  che la struttura nuova ha davvero;
- **il multiutente** (§11);
- **il debito della «fetta 6»**: `DEVICE_CLASS_MEANING` è indicizzato per `(dominio, classe)` — la
  stessa chiave del tipo — e `type_vocabulary.py:52` dichiara già che il suo posto è un campo di
  quelle righe;
- **`azioni.db`** come caso di frontiera del sapere: *«cosa ho fatto a questa entità»* somiglia a
  conoscenza, ma nessuno dei due attori la legge insieme alle altre.

---

## §16 · Le regole, verificate

**Le tre leggi.** *Sussidiarietà*: osservare scegliendo cosa guardare e dire cosa si potrebbe fare
sono giudizio, non automazioni di HA. *Autoconsistenza*: l'agente ha i propri sensi, e il sapere è
dove li tiene. *Ogni agente ragiona*: è la legge che ha deciso il §5.1 — un osservatore senza scope
sarebbe un'automazione, e la prima legge direbbe di farlo in Home Assistant.

**Le quattro fondamenta.** *Atomicità*: ogni riga di sapere porta valore, provenienza, verifica,
prove e fonte; ogni risultato di un'operazione porta unità e copertura. *Nessun doppione*: `casa.db`
esce perché è la copia di un fatto che HA possiede; `ambito` non è una colonna perché vive già nel
genere del soggetto. *Consistenza*: il ruolo esce dalla stessa forma da `view`, da `search` e dal
resoconto — oggi non esce da nessuna. *Autonomia funzionale*: è la fondamenta che questa spec esiste
per riparare.

**Le forme di difetto cercate apposta.** *Due cose dette con una parola sola*: separati
`provenienza` e `verifica`, separati «un archivio solo» e «elementi collegati», separati «come si
misura» e «se conta». *La motivazione falsa*: ogni affermazione qui dentro porta il file e la riga da
cui viene. *Un numero non misurato scritto come misurato*: ogni numero di questa spec è stato
contato sulla casa vera o sul repository, e dove la base è sottile (28 giorni di statistiche) è
scritto che è sottile.

---

## §17 · Le tre metriche sbagliate, e perché stanno qui

Durante il disegno sono state proposte e **scartate** tre misure del «lavoro di riconoscimento», e
restano scritte perché la prossima persona non le riproponga:

1. **«49 forme strutturali»** — utile per stimare un costo, inutile come misura del problema: la
   forma di un dispositivo non dice se è ambiguo.
2. **«21% di entità in integrazioni senza documentazione»** — `ave_domina` ha 0% di
   `translation_key` ed è il caso **più facile** della casa: 39 luci che si chiamano «Abat-jour
   sinistra». La percentuale di traduzioni misura se l'autore ha scritto delle parole, non se
   serviamo noi.
3. **«30 dispositivi ambigui, 44% delle entità»** — «stesso `(dominio, device_class)`» non è
   ambiguità: gli 11 switch di una Reolink hanno undici `translation_key` diversi e parlanti.

La misura giusta è risultata essere **dove le entità si sommano**, cioè dove esiste un bilancio:
**30 contatori su 833, e 3 dispositivi**. Tutto il resto, Home Assistant lo dichiara già.
