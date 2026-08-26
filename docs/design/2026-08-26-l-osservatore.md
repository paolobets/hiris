# L'osservatore

**Data:** 26 agosto 2026 · **Ramo:** `2.0` · **Stato:** spec da approvare
**Nasce da:** `docs/design/2026-08-25-il-cervello-da-capo.md` (il brainstorming, che resta la fonte
delle decisioni del proprietario e va letto prima di questa spec)

La prima fetta del cervello nuovo. **Guarda la casa, e ne ricava oggetti.** Non conclude, non parla,
non tocca niente.

---

## 0. Il fatto da cui si parte, misurato

> **`person.paolo_bettinelli` ha tre giorni di storico in Home Assistant, e nessuna statistica.**

Misurato sulla casa vera il 25 agosto: 3 punti negli ultimi 3 giorni, zero oltre, e `person.*` non ha
`state_class` — quindi le statistiche a lungo termine per lei non esistono affatto.

Nella finestra che Home Assistant conserva **non c'è nemmeno un mercoledì completo**. L'esempio
fondativo del cervello — *«il mercoledì rientri alle 17:30, il riscaldamento scalda a vuoto»* — **non
è ricostruibile** dai dati di HA, oggi, in nessun modo.

Da cui l'unica ragione per cui questa fetta esiste: **senza una memoria propria, il cervello che il
proprietario ha in mente non può esistere.** Non è un'ottimizzazione, è il presupposto.

## 1. Il prodotto dell'osservatore sono OGGETTI

> **Decisione del proprietario, e correzione di una prima stesura di questa spec:** *«l'osservatore
> aggrega i grezzi in oggetti; l'analista si basa su quegli oggetti per identificare tendenze,
> problemi, o comunque analizzare i fatti.»*

Una prima versione faceva consolidare la giornata **per entità** — una riga per il termostato, una
per la temperatura, una per la presenza. Era sbagliata per due ragioni, e il proprietario le ha
nominate entrambe: l'analista si sarebbe trovato tabelle da correlare invece di cose su cui
ragionare, e **questa fetta non avrebbe prodotto niente di guardabile** per verificare che
funzionasse.

**Un oggetto è una cosa compiuta della casa.** Qualcosa che è cominciato, è durato, è finito — con
dentro chi lo ha fatto, e cosa c'era attorno mentre durava:

> *Riscaldamento camera: acceso 15:30 → 17:05. Temperatura da 18,2 a 21,0. Finestra chiusa. Nessuno
> in casa. Fuori 6 gradi.*

Un oggetto solo, leggibile da una persona, e sufficiente per ragionarci sopra senza andare a
ripescare altro.

**Perché è anche la prova che la fetta funziona:** gli oggetti si leggono e si giudica se hanno
senso. Un registro per entità no.

## 2. Cosa NON fa

- **Non conclude niente.** «Il mercoledì rientri alle 17:30» è una conclusione tratta da **molti**
  oggetti: la trarrà l'analista. L'osservatore costruisce gli oggetti, uno per volta.
- **Non riempie la pagina della memoria.** Lì andranno i **fatti** del cervello, che sono
  conclusioni. Da questa fetta l'utente vede **gli oggetti** e la pagina che dice cosa si osserva.
- **Non parla, non propone, non notifica.**
- **Non tocca la casa.** Nessuna scrittura, in nessuna forma.
- **Non legge i fatti** (§5): non esistono ancora, e non si costruisce un ingresso per loro.
- **Non invoca nessun modello.** Il pavimento è deterministico e l'aggregazione è codice: questa
  fetta costa **zero token al giorno**, per sempre.

## 3. I tre strati

| | Cosa | Quanto vive |
|---|---|---|
| **il grezzo** | i cambi, così come arrivano | **21 giorni** |
| **gli oggetti** | le cose compiute, aggregate dal grezzo | restano |
| **i fatti** | le conclusioni | **non esistono ancora**: sono dell'analista |

### Perché il grezzo resta 21 giorni e non una notte

La prima stesura lo buttava dopo il consolidamento serale, per una proprietà che vale ancora:
**sbagliare l'aggregazione costa un giorno, non tutto** — finché il grezzo c'è, gli oggetti si
rifanno.

Ma il modo di costruire gli oggetti **cambierà**, e non per caso: le prime settimane sono quelle in
cui si sta ancora imparando a costruirli, e ogni correzione dell'aggregazione arriva **dopo** aver
visto gli oggetti veri. Con una notte sola, ogni miglioramento varrebbe **solo da domani**, e tutto
il passato resterebbe com'è stato capito la prima volta.

È anche la sola difesa contro il rischio dichiarato al §5: quando gli altri attori arriveranno e
vorranno un'aggregazione diversa, tre settimane di oggetti **si rifanno davvero**.

**Ventuno giorni sono tre mercoledì**, cioè l'unità dell'esempio da cui nasce tutto il cervello. È il
periodo in cui rifare i conti serve di più, e costa poco disco.

**Ma la ritenzione vera è ventidue giorni, e il ventiduesimo è una guardia.** La review dell'archivio
il 26 agosto ha misurato che una soglia di 21×86400 secondi *non* contiene tre mercoledì interi: se la
potatura gira alle 03:00, del giorno a −21 sopravvive solo ciò che è successo dopo le 03:00, e nel
weekend di ottobre in cui l'ora torna indietro — un giorno da 25 ore — è **l'evento fondativo stesso**,
il mercoledì alle 17:30, a cadere oltre la soglia. La promessa e la sua aritmetica si contraddicevano.
Il giorno di guardia le riconcilia: la soglia resta in secondi assoluti, senza far entrare il fuso
orario nell'archivio, e i ventuno giorni promessi ci sono **per intero** anche al bordo e anche quando
l'ora cambia. Costa il 5% di disco su decine di megabyte.

### La condizione che regge tutto

> **Nel grezzo non c'è nessun giudizio.** Il cambio si scrive così com'è: quale cosa, quando, da che
> valore a che valore.

Tutto il giudizio sta nell'aggregazione, che è **rifacibile per 21 giorni**. È il criterio con cui
vanno giudicate tutte le scelte di questa fetta: **una decisione presa in scrittura non si corregge
più**, una presa in aggregazione sì.

Per la stessa ragione il grezzo **non porta il contesto attorno**: duplicherebbe lo stesso valore in
ogni riga che lo nomina, e deciderebbe oggi cosa sarà rilevante domani. Il contesto entra
nell'oggetto, dove si può rifare.

## 4. Cosa si osserva: il pavimento, e il prompt che allarga

> **Punto dichiarato fondamentale dal proprietario:** se il prompt dell'obiettivo decide cosa entra
> nelle osservazioni, **il prompt è un punto singolo che può accecare l'osservatore** — e ciò che non
> è stato osservato **non esiste più**. Riscriverlo fra tre mesi non fa ricomparire i tre mesi
> mancanti, e il danno si scopre il giorno in cui serve quel dato.

**Il pavimento si osserva comunque**, qualunque cosa dica l'obiettivo, e non è una lista scritta a
mano: si deriva da ciò che Home Assistant **dichiara già** su ogni entità.

| Gamba dell'obiettivo | Cosa entra nel pavimento |
|---|---|
| chi c'è | `person`, i `device_tracker` **con `source_type: gps`**, e i sensori binari di presenza, occupazione, movimento |
| comfort | i sensori di temperatura e umidità, e i termostati |
| dispersione | i sensori binari di porta, finestra e apertura, e le tapparelle |
| consumo | i sensori di energia, potenza, gas e acqua, e i contatori che salgono |
| buono stato | le condizioni di sistema (§6) e i sensori di batteria |
| sicurezza | **serrature, pannello dell'allarme, sirene, e i sensori di fumo, gas, monossido, allagamento, manomissione, guasto, calore e gelo** |

**Il prompt allarga e dà priorità sopra il pavimento; non restringe mai sotto.**

### La sesta gamba, aggiunta il 26 agosto dalla review del primo task

La prima stesura di questa spec **non conteneva gli allarmi**: né fumo, né gas, né monossido, né
allagamento; né le serrature, né il pannello dell'allarme. Era una dimenticanza, non una scelta, e
la review l'ha trovata guardando l'elenco vero delle classi di Home Assistant invece del mio.

**Perché è il buco peggiore possibile in questa spec.** Un allarme che scatta e rientra mentre
nessuno è in casa — una falsa partenza, un episodio risolto — dopo tre giorni non esiste più in
Home Assistant, e dopo ventuno non esisterebbe più nemmeno qui. È esattamente lo scenario
irreversibile che il pavimento esiste per impedire, sulla categoria di dati che conta più di tutte.

**E il prodotto quel vocabolario ce l'aveva già**, verificato sulla documentazione di HA il 16
agosto e con la trappola documentata (`carbon_monoxide`, **non** `co`):
`casa/nucleo.py::_CLASSI_EVENTO` e `_DOMINI_EVENTO`. Sono due domande diverse — «cosa è notevole
adesso» contro «cosa si osserva sempre» — ma **sugli allarmi le due risposte devono coincidere**, e
non coincidevano.

**Le sirene sono entrate il 26 agosto**, dalla re-review dello stesso task: `siren` stava nel
vocabolario gemello di `nucleo.py` e non in questa gamba. Una sirena che suona e rientra mentre in
casa non c'è nessuno è **letteralmente** lo scenario che il paragrafo qui sopra descrive: se la
sesta gamba esiste per quello, non può escludere la cosa che fa rumore quando succede.

**Le classi di qualità dell'aria** (`carbon_dioxide`, `pm25`, `pm10`, i composti organici volatili)
entrano in **comfort**: il docstring prometteva «che aria si respira» e la spec copriva solo
temperatura e umidità. Anche questa era una dimenticanza.

### Tre decisioni sul perimetro, con la loro ragione

**Le entità nascoste SI osservano.** Nascondere in Home Assistant significa «toglila dalle mie
viste», non «non esiste» — e l'interruttore del gruppo LIFX, che è nascosto, è il pezzo che spiega il
comportamento di tre lampade. È il **verso opposto** a quanto deciso per la chat, dove le nascoste
escono dagli elenchi, ed è coerente: lì la domanda è *«cosa ti mostro»*, qui è *«cosa succede»*.

**Le entità disabilitate NON si osservano.** Non hanno stato: non c'è niente da osservare.

**I `device_tracker` del router restano fuori.** Misurato: 65 dei 73 di questa casa hanno
`source_type: router` — l'NVR, Alexa, un Echo, una TV, una lampada. Dicono «questo apparecchio è
connesso al wifi», non «c'è qualcuno in casa». I 4 `gps` sono i telefoni, e sono le fonti che stanno
dietro alle due `person`. **Non è una questione di volume** (i 65 producono 114 cambi al giorno, lo
zero per cento): è che non significano niente per l'obiettivo.

**Le entità di servizio si osservano solo se sono nel pavimento.** `config` e `diagnostic` sono 604
su 1226 in questa casa e per lo più sono rumore — ma i sensori di **batteria** sono `diagnostic` e
sono precisamente «buono stato». Il filtro è per **classe del dispositivo**, non per categoria.

## 5. Il dialogo fra gli attori: idea registrata, NON costruita

Il proprietario ha descritto il sistema a regime: *«osservatore e analista si parleranno come due
agenti specializzati, si confronteranno e miglioreranno il set informativo, tutto con
l'orchestrazione del verificatore»* — e i **fatti mutano** man mano che le prove crescono.

**Decisione: in questa fetta non si costruisce niente di tutto questo.** *«Quella è un'idea, ora
osservatore e basta, poi vedremo.»*

Concretamente, e va scritto perche' e' la differenza fra una fetta onesta e un archivio senza lettori:

- **l'osservatore NON legge i fatti** — non esistono, e un ingresso che nessuno alimenta e' codice
  morto travestito da previsione;
- **non c'e' nessun canale per ricevere richieste** da un analista che non c'e';
- **non c'e' nessun orchestratore**: l'osservatore gira per conto suo, a orario.

**Il rischio di questa scelta, dichiarato:** progettare un oggetto senza i suoi ingressi e' un modo
noto di ottenere un'architettura storta, e l'osservatore andra' riaperto quando l'analista arrivera'.

**Cosa lo rende accettabile, ed e' l'unica difesa che serve:** il grezzo resta 21 giorni (§3).
Quando il dialogo arrivera' e chiedera' di aggregare diversamente, **gli oggetti di tre settimane si
rifanno davvero**. La possibilita' di cambiare idea non e' affidata a un'interfaccia indovinata
adesso: e' affidata al fatto che il materiale grezzo c'e' ancora.

## 6. Come si costruisce un oggetto

**L'obiettivo sceglie QUALI entità; la natura dell'entità decide CHE TIPO di oggetto ne esce.**
Nessuna delle due è una lista scritta a mano: la natura la dichiara Home Assistant.

| Natura del protagonista | L'oggetto che ne esce |
|---|---|
| termostato, interruttore, luce, tapparella | **un funzionamento**: acceso/aperto da → a, e cosa ha fatto la grandezza collegata mentre durava |
| presenza | **una presenza o un'assenza**: dentro/fuori da → a |
| temperatura, umidità | non generano oggetti da sole: sono il **contesto** di altri oggetti, più gli attraversamenti di soglia |
| contatore | **un consumo**: quanto, in che periodo, come distribuito |
| condizione di sistema | **un guasto**: nato quando, durato quanto, ancora aperto o chiuso |

### Chi sta insieme a chi

Un oggetto raccoglie **più entità**, e sapere quali stanno insieme non è un'invenzione: **`legami`
lo dice già**. È il caso misurato del lampadario — tre lampade LIFX, il loro gruppo, e l'interruttore
fisico che le comanda sono **un sistema solo**, e `legami` restituisce l'automazione che li unisce.

**Un oggetto ha un protagonista e i suoi comprimari**, e i comprimari si trovano chiedendo, non
indovinando dal nome. È anche la ragione per cui il grezzo resta nudo: **quel legame si scopre dopo**,
e con l'episodio scritto per entità si sarebbe già deciso che sono quattro cose separate.

### La salute di Home Assistant entra nella stessa forma

*«Per dire che la casa è efficiente, confortevole e in buono stato l'osservatore deve osservare anche
HA»* — è la terza gamba dell'obiettivo.

Un'integrazione rotta non è un cambio di stato di un'entità, **ma il suo comparire e il suo sparire
lo sono**. L'osservatore interroga periodicamente le superfici di salute che il client già espone e
scrive un cambio quando una condizione **nasce** o **finisce**. Così la riga del grezzo resta una
sola, con un campo che dice se viene da un'entità o dal sistema — e l'oggetto che ne esce è un
guasto con la sua durata.

> **Il modello sceglie, il codice fa i conti.** In questa fetta il modello non entra affatto: il
> pavimento è deterministico e l'aggregazione è codice. Al modello resterà la domanda «cosa è
> rilevante», quando servirà allargare oltre il pavimento.

## 7. Cosa vede l'utente

**Una pagina nuova, e non è un pannello di configurazione.** Il proprietario ha scelto *trasparenza
al posto del permesso*: l'osservatore non chiede, ma si deve poter vedere in qualunque momento
**cosa sta guardando e perché** — e togliergli qualcosa.

Per ogni cosa osservata deve dire **da dove viene**: dal **pavimento** (e allora non si toglie) o
dall'**obiettivo** (e allora sì). Un elenco che non distingue le due non si può usare per decidere.

*La terza provenienza — «me l'ha chiesto l'analista» — arriverà con lui. Il campo si prevede nella
forma del dato, perché aggiungerlo dopo significherebbe riscrivere ogni riga già salvata; ma nessuna
riga lo porta ancora.*

**E si vedono gli oggetti**, perché sono l'unico modo di capire se il cervello sta guardando bene
prima ancora che qualcuno concluda qualcosa.

**Rifinitura non ancora decisa:** la prima volta che l'osservatore si allarga su qualcosa che
riguarda **le persone**, lo dice. Non un permesso: un avviso.

## 8. Dove vivono le cose, e perché non è il ritorno di `history.db`

Il prodotto ha già avuto un archivio storico ed è uscito: **scriveva e nessuno leggeva**. L'avvio lo
tratta ancora oggi come un residuo da rimuovere, e questa spec **non lo resuscita**.

La differenza non è di forma, è di destino: **quello nasceva senza lettore, questo nasce col
lettore** — l'analista è la fetta immediatamente successiva, e senza gli oggetti non può esistere.

> **Se l'analista non venisse costruito, questo archivio va cancellato**, non lasciato a scrivere. È
> la stessa regola che ha condannato il primo, e vale anche per questo.

L'archivio è **separato dalla memoria**: i ricordi sono dell'utente, i fatti saranno del cervello, gli
oggetti sono **materiale**, non conoscenza.

**Gli oggetti restano finché l'utente non li cancella.** Nessuna compattazione in questa fetta:
sarebbe una difesa contro un problema che nessuno ha misurato, e questo progetto ha già pagato
l'abitudine di ottimizzare prima di misurare.

## 9. Le misure, prese prima di scrivere una riga

Le prime tre verifiche di questa spec sono state **eseguite sulla casa vera il 26 agosto**, e hanno
corretto la spec tre volte su tre. Restano qui perché sono i numeri su cui il codice si appoggia.

### ① Il pavimento cattura 153 entità — ma 65 sono da buttare

Su 852 entità con stato (escluse le disabilitate), il pavimento ne prende **153**: 95 «chi c'è», 29
consumo, 23 comfort, 6 «buono stato». Una sola è nascosta.

**Ma 65 delle 95 sono `device_tracker` del router**, e non significano niente (§4). Tolte quelle, il
pavimento vero è di **circa 88 entità** — la dimensione giusta: abbastanza da vedere la casa, poche
abbastanza da restare leggibili in una pagina.

### ② Il volume vero è 14.597 cambi al giorno, non «un migliaio o due»

Misurato su 24 ore reali. La stima della prima stesura era sbagliata **di dieci volte**.

| | cambi in 24h | |
|---|---|---|
| comfort | 10.421 | **71%** |
| chi c'è | 2.090 | 14% |
| consumo | 1.799 | 12% |
| buono stato | 149 | 1% |
| tracker del router | 114 | 0% |

**Su 21 giorni: circa 306.000 righe.** Per SQLite sono decine di megabyte — sostenibile, e va detto
che è sostenibile invece di scoprirlo dopo.

**Il 71% è comfort**, e una sola entità (`binary_sensor.reolink_trackmix_poe_1_movimento`) fa 1.545
cambi al giorno da sola. Un sensore di temperatura ne fa 935. **Se un giorno servirà ridurre, è lì
che si guadagna** — ma non si ottimizza adesso: il numero è sostenibile e ridurre significherebbe
decidere in scrittura, che è la cosa che questa fetta non fa.

### ③ Le statistiche di HA NON sostituiscono questa memoria

Sembrava una scorciatoia: le entità con `state_class` hanno statistiche orarie, quindi l'osservatore
potrebbe non conservarle. **Misurato: le statistiche di questa casa partono dal 13 agosto** — tredici
giorni, non mesi. Il database del recorder è evidentemente nato allora.

E l'argomento che vale più della misura: **se è già successo una volta che quel database ripartisse
da zero, può succedere ancora.** La copia dell'osservatore non duplica le statistiche — è l'unica che
non dipende da quel file.

### ④ Le superfici di salute: due funzionano, una no

Misurate una per una, perché nelle due fette precedenti la forma immaginata era sbagliata **tutte e
due le volte**.

| Superficie | Esito |
|---|---|
| `config_entries/get` | **funziona**: 53 integrazioni, di cui **9 non caricate** (una in `setup_retry`, le altre `not_loaded`), con `state` e `reason` |
| `repairs/list_issues` | **funziona**: 4 problemi aperti, con `domain`, `issue_id`, `severity`, `is_fixable` |
| `system_health/info` | **non serve**: la chiamata riesce ma torna vuota. Non ci si appoggia |

**Cosa ha trovato, di vero, su questa casa:** tre dei quattro problemi aperti sono automazioni che
**riferiscono entità, servizi o dispositivi che non esistono** — e il quarto è Sonos con le
sottoscrizioni fallite, di gravità `error`. È esattamente il materiale di «la casa in buono stato»,
ed esisteva già senza che nessuno lo guardasse.

### Le verifiche che restano, dopo l'implementazione

1. **Gli oggetti di una giornata vera, riletti a mano.** È la prova che conta: si guarda cosa è
   rimasto di ieri e ci si chiede se ci si potrebbe ragionare sopra. Se la risposta è no, l'analista
   non funzionerà mai, e si scopre adesso invece che fra un mese.
2. **Il caso del lampadario**: le tre lampade, il gruppo e l'interruttore devono finire in **un
   oggetto solo**, non in quattro.
3. **Il peso reale su disco** dopo la prima settimana, contro i 306.000 previsti.

## 10. Fuori scope, dichiarato

- **Nessuna conclusione, nessun fatto, nessuna tendenza**: è l'analista.
- **Nessun turno di modello.**
- **Nessuna scrittura sulla casa.**
- **Nessuna compattazione** dell'archivio.
- **Nessun multiutente**: i fatti di Paolo e quelli di Marta sono un problema dei fatti, e i fatti
  non esistono ancora.
- **Il canale dell'analista, la lettura dei fatti e l'orchestrazione** (§5): idea registrata, non
  costruita. Niente ingressi che nessuno alimenta.
