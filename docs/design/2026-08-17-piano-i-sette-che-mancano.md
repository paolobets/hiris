# I sette che mancano — e l'albero che diventa verificabile

> Piano per i reperti **29, 30, 33, 35, 36, 37, 38** della review del
> 2026-08-17, più le tre decisioni di prodotto rimaste (24, 25, 26).
> Nessuno di questi è un difetto: HIRIS non sbaglia e non tace su qualcosa che
> sa. Non sa ancora, e per saperlo serve una fetta.

## L'idea che li tiene insieme

Oggi `gerarchia()` è **un'affermazione** che HIRIS fa sulla casa: la costruisce
dai registri e ci ragiona sopra, e **niente la verifica**. Se un'entità prende
la stanza da un dispositivo che HIRIS ha letto male, o se un'area contiene cose
che HIRIS non le attribuisce, non c'è nessun modo di accorgersene — se non
sbagliando una risposta davanti all'utente.

Tre dei sette cambiano proprio questo. Non aggiungono conoscenza: aggiungono un
**secondo parere**, quello di Home Assistant su se stesso.

| | HIRIS oggi | Home Assistant, se glielo si chiede |
|---|---|---|
| «cosa c'è in cucina» | lo deduce dai registri | `extract_from_target` **lo risolve** |
| «chi tocca questa luce» | legge due file YAML | `search/related` **lo calcola su tutto** |
| «cosa non funziona» | conta le entità non disponibili | `repairs` **lo ha già diagnosticato** |

L'albero smette di essere una replica da credere e diventa **una risposta
confrontabile**. Ed è per questo che l'ordine di questo piano non è per valore
percepito: prima ciò che rende l'albero verificabile, poi ciò che lo estende.

---

## Fetta 1 — I bersagli: HIRIS smette di spegnere «quasi tutto» ✅ FATTA

> Reperto 33. È il più urgente, e non perché manchi una funzione.

**Il difetto vero.** «Spegni tutto in cucina» obbliga il modello a chiamare
`cerca`, raccogliere gli id a mano e passarli tutti a `esegui`. Se ne perde uno
— e su una cucina con quindici entità ne perde uno — HIRIS spegne quattordici
cose e **dichiara di aver spento tutto**. È una risposta sbagliata detta con
sicurezza: la classe A1, in un prodotto che agisce.

**Cosa si aggiunge.** `azione/verifica.py` accetta oggi solo
`bersaglio.entita`. Home Assistant risolve i bersagli da sé:

    extract_from_target  {target: {area_id: "cucina"}}
      → referenced_entities, referenced_devices, referenced_areas
      → missing_devices, missing_areas, missing_floors, missing_labels

Le due metà contano entrambe. `referenced_*` dice **cosa si toccherà**;
`missing_*` dice **cosa il bersaglio nominava e non esiste** — cioè la
differenza fra «l'area è vuota» e «quell'area non c'è», che è la stessa
distinzione che l'anagrafe fa già ovunque e che qui arriva gratis.

**Perché è anche la primitiva di verifica.** Chiedere a HA cosa contiene
`area_id: cucina` e confrontarlo con ciò che `gerarchia()` mette in quell'area
è il primo confronto possibile fra la replica e l'originale. La fetta 4 lo usa.

**Fatta quando**: `esegui` accetta un bersaglio per area, piano, etichetta o
dispositivo; l'anteprima elenca cosa toccherà **prima** di toccarlo; un
bersaglio che nomina qualcosa di inesistente lo dichiara invece di ridurlo in
silenzio.

---

## Fetta 2 — `search/related`: chi tocca questa cosa ✅ FATTA

> Reperto 30.

**Il buco.** `casa/comportamento.py` legge `automations.yaml` e `scripts.yaml`.
Non vede i pacchetti, gli `!include`, le cartelle, le scene né i gruppi — cioè
tutto ciò che una casa cresciuta usa davvero. HIRIS crede di conoscere il
comportamento della casa e ne conosce la parte scritta in due file.

**Cosa si aggiunge.** `search/related` è calcolato **da Home Assistant su tutto
ciò che ha caricato**, ovunque sia scritto. Accetta `area, automation, device,
entity, floor, group, integration, label, person, scene, script` e risponde con
ciò che è collegato. È dipendenza di `frontend`: c'è in ogni HA che ospita
HIRIS.

**Le due domande che sblocca**, entrambe reali:
- *«Perché si è accesa la luce del corridoio?»*
- *«Se cancello questa entità, cosa smette di funzionare?»* — che è la domanda
  che un assistente deve saper fare **prima** di proporre una modifica.

**Attenzione a non rifare il difetto.** `search/related` non sostituisce la
lettura dei file: quella porta il **corpo** (cosa fa l'automazione), questa
porta i **legami** (chi tocca cosa). Sono due fatti diversi sullo stesso
oggetto, e vanno tenuti distinti — o si ricrea la confusione fra «dichiarato» e
«dedotto» che il progetto paga da sempre.

---

## Fetta 3 — `repairs`: ciò che HA sa già essere rotto ✅ FATTA

> Reperto 29.

Oggi alla domanda «c'è qualcosa che non va in casa?» HIRIS sa contare le entità
non disponibili. Home Assistant tiene un **registro dei problemi** con
severità, se è riparabile, e in quale versione qualcosa si romperà.

Si affianca al motivo delle integrazioni già chiuso ieri: quello dice *perché
un'integrazione non è partita*, questo dice *cosa HA ha diagnosticato in
generale*. Vanno nella stessa sezione del nucleo, che già esiste — «ciò che
HIRIS ignora» — e per la stessa ragione: sono condizioni, non eventi.

**Il rischio da evitare**: un elenco che dice sempre qualcosa. Molte case hanno
sempre due o tre `repairs` aperti e innocui. Va filtrato per severità, e va
dichiarato quanti se ne sono taciuti — mai un filtro silenzioso.

---

## Fetta 4 — L'albero verificabile · IN CORSO

> **Non è un reperto della review: è la fetta che le prime tre rendono
> possibile.**

Con la fetta 1 HIRIS può chiedere a Home Assistant cosa contiene un'area. Con
la 2, chi tocca cosa. A quel punto la domanda diventa: *la casa che HIRIS
racconta è la casa che c'è?*

**Cosa fa.** Un confronto, a ogni ricostruzione dell'anagrafe, fra l'albero che
`gerarchia()` costruisce e ciò che HA risponde su un campione di aree. Le
divergenze non sono un errore da correggere in silenzio: sono **conoscenza**, e
vanno dichiarate dove il modello le legge.

Tre esiti, tre diciture diverse — la stessa disciplina con cui l'anagrafe
distingue oggi «senza area», «area sconosciuta» e «aree non lette»:

- **combaciano** — non si dice niente, che è la cosa giusta da dire;
- **HIRIS ne ha di meno** — la replica è vecchia, o un registro è caduto: si
  dichiara, come si dichiara già `non_disponibili`;
- **HIRIS ne ha di più** — la replica afferma qualcosa che HA non conferma, ed è
  il caso peggiore perché è quello che produce risposte sbagliate dette con
  sicurezza.

**Perché conta più delle altre.** Tutte le fette di conoscenza fatte finora
hanno reso l'albero **più ricco**. Nessuna l'ha reso **controllabile**. È la
differenza fra «HIRIS sa di più» e «HIRIS sa di sapere», e da qui in avanti è
la seconda che vale.

**Il costo, dichiarato**: un comando WS per area confrontata. Non si confronta
tutta la casa a ogni ricostruzione — si campiona, e si dice quante se ne sono
guardate. Un controllo che costa quanto la cosa che controlla non si esegue mai.

---

## Fette 5-8 — Ciò che estende, in ordine di valore

Nessuna di queste rende l'albero più solido: lo allargano. Vanno dopo.

### 5 · Il corpo delle scene (reperto 38)

`GET /api/config/scene/config/{id}`, e il file è `scenes.yaml` — la stessa
strada con cui `comportamento.py` già legge gli altri due. È la più corta del
gruppo, ed è già mezza costruita.

### 6 · La topologia dei dispositivi (reperto 37)

`via_device_id` è **la sola cosa che spiega un guasto di gruppo**: dieci
lampadine Zigbee non rispondono insieme perché il loro gateway è giù. Con
`sw_version`, `entry_type` (una voce di servizio non è un oggetto fisico) e il
numero di serie. Arriva già dentro `config/device_registry/list`: costa zero
chiamate, come le entità di riferimento dell'area.

### 7 · Il calendario (reperto 35)

`calendar/event/subscribe`. «Giovedì sera sono a casa?» non è curiosità: è la
condizione che serve per decidere il riscaldamento, cioè il primo caso in cui
HIRIS potrebbe **proporre** invece di rispondere.

### 8 · Le liste (reperto 36)

`todo/item/list`. HIRIS nomina il dominio in italiano, lo conta, e non ne legge
una riga.

---

## Le tre decisioni, prese ✅ (categorie e albero FATTE)

**24 · Le categorie — ENTRANO.** Sono una tassonomia che l'utente scrive a
mano, come le etichette: vanno trattate come quelle. Escono da `guarda`,
entrano nell'indice di `cerca`, e l'assegnazione per-entita' -- che arriva
**gratis** dentro la risposta che HIRIS gia' riceve e oggi si butta -- si
salva. Il registro delle categorie e' partizionato per ambito
(`automation`, `script`, `scene`, `helpers`): quell'ambito fa parte del nome,
o due categorie omonime in ambiti diversi diventano indistinguibili.

**26 · L'albero in pagina — ENTRA.** Il payload piu' ricco che HIRIS produce
usciva verso una pagina che ne leggeva solo i conteggi. Diventa anche il posto
dove la fetta 4 mostrera' le divergenze fra la replica e la casa vera.

**25 · Le plance — PARCHEGGIATE, e non per costo.** Sono l'unica delle tre che
non e' conoscenza da leggere: e' materiale su cui AGIRE. «Questa luce compare
in qualche mia dashboard?» ha senso solo quando HIRIS sa anche **creare** e
modificare una plancia -- e quella e' un'altra fetta, con un'altra spec e altre
protezioni. Leggerle adesso vorrebbe dire aggiungere un tipo di `guarda` che
risponde e non porta a niente: la fondamenta 4 al contrario, esattamente il
difetto che questa review e' servita a chiudere. Restano dove sono, e tornano
con «crea».

## L'ordine, in una riga

**1 bersagli → 2 legami → 3 guasti → 4 verifica dell'albero**, e solo dopo
scene, topologia, calendario, liste — piu' le categorie e l'albero in pagina,
che non dipendono da nessuna delle quattro e possono correre a fianco.

Le prime tre non sono tre funzioni: sono i tre modi in cui Home Assistant può
smentire HIRIS. La quarta è dove quella smentita smette di essere un rischio e
diventa una riga che il modello legge.
