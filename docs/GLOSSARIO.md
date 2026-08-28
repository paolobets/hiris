# GLOSSARIO — come si chiamano le cose in HIRIS

Spec: `docs/design/2026-08-28-il-glossario.md`.

Questo documento non e' storia: e' la **regola**. Si consulta ogni volta che nasce un nome, e si
aggiorna quando nasce un concetto. Non porta una data di redazione perche' non e' la fotografia di
un giorno: e' vivo, e cambia quando cambia il codice.

**Stato di questo documento: l'elenco e' completo, nessuna colonna e' decisa.** Le colonne «che
cosa fa», «inglese» e «prova del lettore nuovo» sono lasciate vuote di proposito — le riempiono i
task successivi della stessa fetta. Una riga con la colonna vuota significa «non ancora deciso», non
«dimenticato».

**Aggiornato il 28/08 durante l'esecuzione, dopo una review:** la prima stesura aveva tre insiemi.
La review ha trovato un quarto insieme che la spec non aveva visto (`genere` e altre parole che
vivono come **valori** dentro costanti, non come nomi di modulo o classe) — vedi «I valori di
dominio» in fondo, e §4④ di `docs/design/2026-08-28-il-glossario.md`.

## Come si legge

Il nome inglese non e' la traduzione della parola italiana: e' il nome di **cio' che la cosa fa**.
La colonna «che cosa fa» si scrivera', quando verra' riempita, **senza usare la parola italiana**,
perche' e' cosi' che si arrivera' al nome — non traducendo, rinominando.

Il criterio che separa gli insiemi qui sotto e' **la natura della parola, non quanto e' usata**: un
concetto raro (`comprimari`) richiede tutto il giudizio che una parola frequente (`giorno`) non
richiede affatto.

## Il controllo di collisione si fa sul codice, non solo sul glossario

**Corretto durante la review del Task 4, dopo che due nomi ci sono passati sotto: un grep sul solo
`docs/GLOSSARIO.md` non basta.** Il documento non e' l'unico posto dove l'inglese gia' esiste:
`hiris/` ne e' pieno, in sottosistemi in inglese (`reasoning/`, `backends/`, `proxy/`) e in commenti
e identificatori sparsi ovunque. Un nome scelto guardando solo le righe gia' decise qui puo' ancora
collidere con una parola che il codice usa gia' per dire un'altra cosa — ed e' lo stesso identico
difetto per cui questa fetta esiste, spostato dal glossario al codice.

**Prima di fissare un candidato in tabella:**

1. cercalo nel glossario (come gia' si faceva) — collide con un'altra voce decisa, con un nome di
   strumento, con un valore di dominio?
2. cercalo anche **in `hiris/`** con un grep sul sorgente vero — collide con un identificatore, un
   commento, un valore di stringa gia' scritto dal codice?
3. **confrontalo anche con le parole italiane ancora senza inglese** — le righe di «I concetti»
   con la colonna «inglese» vuota, punto: nessun altro posto. Se il candidato e' il nome ovvio per
   una di quelle, si lascia a lei: non vince chi lo sceglie prima.

```bash
python - <<'PY'
import pathlib,sys
t=pathlib.Path('docs/GLOSSARIO.md').read_text(encoding='utf-8').split(chr(10))
sez=None
for r in t:
    if r.startswith('## '): sez=r[3:].strip()
    elif sez=='I concetti' and r.startswith('| '):
        c=[x.strip() for x in r.split('|')]
        if len(c)>4 and c[1] and c[1]!='italiano' and not set(c[1])<=set('- ') and not c[3]:
            sys.stdout.write(c[1]+chr(10))
PY
```

**Corretto in fix round 1 del Task 6 (rilievo del reviewer): il controllo, cosi' come scritto nei
passi 1 e 2, guardava il glossario gia' deciso e il codice, ma non le parole ancora da decidere.**
La conseguenza e' un difetto di processo della fetta, non di chi esegue un singolo task: l'ordine
dei lotti diventa un arbitro silenzioso. Chi decide un lotto prima si prende l'inglese piu' ovvio
per una parola qualunque, e l'ultimo lotto — che per costruzione contiene le parole rimaste, cioe'
quelle su cui nessuno si e' ancora dovuto misurare — eredita un vocabolario gia' eroso dai lotti
precedenti, anche quando il nome ovvio per una parola non ancora arrivata era proprio quello. Il
caso vero, dal Task 6: `specie` (`SPECIE`, `fai`/`chiedi`) stava per diventare `intent`, il nome
piu' naturale in inglese per «scopo, intenzione» — ma `intent` e' anche il nome ovvio di `intento`
(`azione/costruzione/mestiere.py:20-32`, la struttura con `innesco`/`passi`/`stati`/`parametri`
che descrive lo scopo di una costruzione). Corretto scegliendo `verb` per `specie` (vedi la nota
dedicata, sotto la tabella «I concetti») e aggiungendo questo passo 3, perche' il passo 2 da solo
— cercare `intent` nel codice — non lo avrebbe MAI trovato: `intento` non e' scritto in inglese da
nessuna parte, ne' nel glossario ne' nel codice.

**Corretto una seconda volta (fix round 2, rilievo del reviewer): la prima stesura di questo passo
diceva di confrontare anche con "le parole dei lotti futuri elencate nella spec" — riferimento
falso, perche' `docs/design/2026-08-28-il-glossario.md` non elenca quelle parole per nome
(anzi dichiara che l'elenco si chiude nel primo passo del piano); l'unico posto dove le 12 parole
ancora assenti sono elencate e' un file di processo destinato a sparire, che il glossario non
cita.** Corretto: l'unico posto valido e' la tabella stessa, colonna «inglese» vuota. **Nota
onesta, perche' questo passo non sia ovvio da saltare:** quando e' stato scritto (fix round 1),
`intento` era una delle parole senza riga -- il passo, cosi' com'e' oggi, non l'avrebbe ancora
potuto trovare da solo: la scoperta e' venuta da una lettura manuale durante la review, non
dall'eseguire questo comando. Il passo diventa meccanicamente sufficiente solo dal momento in cui
un dispaccio successivo aggiunge le 12 righe mancanti (vuote) a «I concetti»: da li' in poi, e non
prima, il documento e' l'unica casa delle parole non ancora decise e la colonna vuota le copre
tutte.

**Non ogni collisione col codice conta allo stesso modo — e si decide guardando DOVE cade il
match, non giudicando quanto la parola «conti» come nome.** Corretto una seconda volta dopo la
review del fix round 1: la prima formulazione («un concetto che qualcuno ha deciso di chiamare
cosi'») era un giudizio, non un test, e due persone diverse l'avrebbero applicata in modo opposto
sullo stesso caso — proprio il rischio che questa regola esiste per chiudere, per i lotti 5 e 6 che
la useranno senza che nessuno gliela rispieghi. La regola e' un test meccanico:

- **Blocca** se la parola compare in `hiris/` in un **contesto sintattico non-prosa**: un
  identificatore (nome di funzione, classe, variabile, costante), una chiave di dizionario o di
  JSON, un segmento di rotta, un nome di file o di modulo.
- **Tollera** se compare **soltanto dentro frasi in linguaggio naturale** — commenti, docstring,
  messaggi di log o di errore — **anche se ripetuta molte volte**.

Un grep piu' un'occhiata a dove cade ogni riga trovata: non serve altro.

Due casi veri, trovati nella review del Task 4:

- **`gateway` per `porta`** (poi corretto in `actuator`): 16 occorrenze in `hiris/app`. Cade su un
  **nome di file** (`api/handlers_gateway_policy.py`) e su un **segmento di rotta**
  (`/api/gateway/policy`, `server.py:3598`) — entrambi contesti non-prosa: blocca. (Compare anche in
  prosa, `agent/runner.py:3`: *«Porta in-addon del runner del gateway esterno»* — ma basta un solo
  match non-prosa per bloccare.)
- **`build` per `costruzione`** (poi corretto in `construction`): 44 occorrenze. Cade su
  **identificatori** — `app["build_stamp"]` (chiave di dizionario) e `_compute_build_stamp` (nome
  di funzione), entrambi in `server.py` — contesto non-prosa: blocca.
- **Per contrasto, il caso tollerato:** `construction` compare 3 volte in `hiris/`, e cade **solo**
  dentro frasi in linguaggio naturale — commenti come «dead by construction», «at store
  construction», «numeric by construction» — mai come identificatore, chiave o nome di file:
  tollera.

## Parole scartate durante l'estrazione

Una regola esclusa non e' silenzio, e' una decisione scritta. Lo script di estrazione (Step 1 del
piano) ha fatto uscire tre parole che **non richiedono nessuna decisione di rinomina**, perche' sono
gia' nella lingua di destinazione o sono una sigla, e sono state tolte a mano dall'elenco:

| parola uscita dallo script | perche' e' stata scartata |
|---|---|
| `backend` | e' gia' inglese — frammento del nome di un file dentro `backends/` (il modulo plurale e' gia' filtrato, il singolare sfugge come pezzo di un altro nome di file) |
| `sanitize` | e' gia' inglese, usata cosi' com'e' nel codice |
| `yaml` | e' una sigla di formato, non si traduce |

Lo script ha anche fatto uscire tre coppie singolare/plurale della stessa parola. Nel glossario
resta **un solo lemma per coppia** — la forma scelta e' quella data dalla spec come esempio certo
in §4①:

| forma uscita dallo script | lemma nel glossario |
|---|---|
| `costruzioni` | `costruzione` |
| `esiti` | `esito` |
| `gambe` | `gamba` |

## I concetti

Parole che il progetto ha **inventato**, o a cui ha dato un significato suo. Per spiegarle a
qualcuno bisogna raccontare come funziona HIRIS.

Sette di queste righe (`genere`, `specie`, `famiglia`, `gesto`, `direzione`, `segno`, `origine`)
non vengono dallo script di Step 1: sono le **etichette** delle costanti di dominio scoperte dalla
review (vedi «I valori di dominio», in fondo). Sono due decisioni distinte sulla stessa riga di
codice: il **valore** (`'funzionamento'`) e' un dato che vive in «I valori di dominio»; la **parola**
che lo classifica (`genere`) e' un concetto e vive qui.

| italiano | che cosa fa | inglese | prova del lettore nuovo |
|---|---|---|---|
| anagrafe | il modulo che legge i quattro registri grezzi di Home Assistant -- piani, aree, dispositivi, entita' -- e li assembla in un'unica gerarchia coerente | topology | ~ parziale |
| ancora (consumi) | il punto nel tempo da cui l'archivio dei consumi conta il progresso corrente: spostarlo in avanti congela, in una riga a parte, i totali per provider e modello registrati fino a quell'istante, cosi' un contatore riportato a zero non perde la storia che lo precede | anchor | ~ parziale |
| ancora (memoria) | il legame -- di un tipo dichiarato fra area, dispositivo ed entita' -- fra un ricordo e la parte della casa a cui si riferisce, con il nome visto nel momento in cui il legame e' stato scritto | tether | ~ parziale |
| archivio | una classe che apre la propria connessione SQLite, applica lo schema e le eventuali migrazioni al costruttore, e offre ai chiamanti metodi tipizzati per scrivere e rileggere lo stato persistito di UN sottosistema -- mai una connessione condivisa fra sottosistemi diversi | store | ✓ arriva |
| ascolto | la finestra temporanea, aperta prima di eseguire un comando su Home Assistant e richiusa subito dopo, durante la quale ci si aggancia agli annunci di cambiamento di stato delle sole entita' bersaglio per confermare che l'effetto e' davvero arrivato, invece di fidarsi del silenzio | listen | ~ parziale |
| azione | il sottosistema che sa cosa questa casa puo' fare secondo Home Assistant e lo fa succedere davvero -- chiamando i suoi servizi, scrivendo la sua configurazione -- sempre passando per un solo punto per ciascun canale | action | ✓ arriva |
| bersaglio | cio' che un comando proposto dichiara di voler toccare, nello stesso vocabolario con cui Home Assistant accetta le sue chiamate di servizio -- identificatori precisi, oppure aree, piani ed etichette ancora da risolvere -- confrontato con lo stato vivo della casa prima di lasciarlo procedere, e legittimamente assente solo per i servizi che non si rivolgono a nessuna entita' | target | ✓ arriva |
| cambi | la tabella che tiene per 22 giorni le singole registrazioni descritte alla voce `grezzo` -- non un concetto a se', ma la sua forma persistita: la finestra di 22 giorni e' cio' che permette di rifare un giudizio sbagliato senza aver perso il materiale di partenza | raw | ✓ arriva |
| caricatore | la sottoclasse del parser YAML che tollera i tag propri di Home Assistant (`!secret`, `!include`, `!input`) trasformando ognuno in un segnaposto leggibile invece di sollevare un'eccezione, restando pero' un parser sicuro che rifiuta i tag pericolosi del linguaggio stesso | loader | ~ parziale |
| casa | la rappresentazione strutturata a quattro livelli (piano, area, dispositivo, entita') degli spazi fisici su cui HIRIS ragiona, costruita a partire dai registri di Home Assistant |  | ✗ non arriva — arbitrato del proprietario |
| catena | l'ordine di ripiego fra i provider del modello: se il primo non risponde si passa al successivo, ed e' la sola fonte di verita' sulla priorita' -- non un ingrediente che ogni pagina ricostruisce a modo suo | chain | ~ parziale |
| cervello | il sottosistema che osserva nel tempo cio' che succede e ne impara i pattern per dedurre correzioni utili, con una memoria e un obiettivo propri, distinto dal resto del prodotto | mind | ~ parziale |
| componi | assembla, a partire dai pezzi gia' pronti che riceve, la struttura finale che serve a un chiamante -- il corpo di un'automazione, il testo dato al modello a inizio turno, il pannello di una decisione -- sempre nello stesso punto per ogni caso, cosicche' nessun chiamante ricalchi da solo la stessa regola di assemblaggio | compose | ✓ arriva |
| comportamento | l'elenco di automazioni e script gia' in esecuzione da soli, ottenuto incrociando cio' che i file dichiarano con cio' che lo stato conferma esistere davvero, cosicche' HIRIS non riproponga qualcosa gia' fatto | behavior | ~ parziale |
| comprimari | per un soggetto osservato, le altre cose della casa -- entita', automazioni, scene, script -- che agiscono su di lui o lo misurano, lette una sola volta per l'intera giornata e riusate per ogni fatto compiuto che ne nasce | companions | ~ parziale |
| condizioni | quando una lettura ricordata o un'automazione vale, nello stesso vocabolario che Home Assistant gia' usa per i propri inneschi e le proprie regole -- ora, giorno, presenza, sole, meteo -- con una sola voce aggiunta da HIRIS perche' Home Assistant non ce l'ha | conditions | ✓ arriva |
| costruzione | il sottosistema che compone e scrive su Home Assistant nuovi oggetti di configurazione -- automazioni, script, scene, helper -- attraverso un ciclo di proposta, approvazione umana e scrittura, con la possibilita' di disfare cio' che ha appena creato e di tornare indietro | construction | ~ parziale |
| cronaca | il registro unico e leggibile di ogni tentativo che ha gia' superato i controlli -- un comando o una scrittura di configurazione, riuscito o fallito -- con chi l'ha chiesto, cosa e' successo e quando, interrogabile a prescindere da chi ha agito | journal | ✓ arriva |
| decisione | il risultato gia' calcolato di chi rispondera' al prossimo messaggio e perche', composto da fatti gia' misurati -- non dagli ingredienti grezzi di configurazione -- cosicche' la pagina che lo mostra si limiti a disegnarlo invece di ricalcolare la stessa regola per conto suo | resolution | ~ parziale |
| direzione | classifica in quale verso si muove un valore fisico del bilancio energetico osservato -- prodotto, autoconsumato, immesso, prelevato, caricato, scaricato, consumato | direction | ✓ arriva |
| dispatcher | collega ciascuno dei tredici nomi che il modello puo' invocare alla sua implementazione concreta -- gli archivi, l'attuatore, l'officina, il canale verso Home Assistant -- attraverso un solo punto d'ingresso che non solleva mai: un nome sconosciuto, argomenti mancanti o un guasto imprevisto diventano tutti un dizionario leggibile con la chiave dell'errore, mai un'eccezione che interrompe il turno | dispatcher | ✓ arriva |
| domande | le tre funzioni che, su richiesta esplicita, restituiscono il dettaglio di una cosa sola -- cercarla per nome, vederne il corpo, sapere chi la tocca -- quando il riepilogo sempre presente non basta | queries | ~ parziale |
| esito | il fatto osservabile su cio' che e' davvero successo in un tentativo -- un provider che ha rifiutato, un comando riuscito o fallito, un tempo di attesa misurato -- mai un'ipotesi sul perche' | occurrence | ✓ arriva |
| famiglia | raggruppa il fallimento di un provider del modello in una delle cinque cause riconosciute -- credenziale, modello, irraggiungibile, scaduto, altro -- cosi' che due rifiuti della stessa causa vengano trattati come lo stesso evento invece che come due guasti diversi | family | ✓ arriva |
| flusso | la sequenza di righe NDJSON che il processo del CLI del modello scrive in uscita mentre lavora, letta una volta sola e ridotta a un esito unico -- riuscito, troncato, senza risultato -- mai riletta una seconda volta con una logica diversa | stream | ✓ arriva |
| forme | il modulo puro che, a partire dai parametri portati dal modello, compone la struttura pronta da scrivere per ciascun tipo di oggetto -- automazione, script, scena -- generando anche un identificatore che in questa casa non esiste ancora | shapes | ~ parziale |
| forza | quale delle quattro nature chiuse porta una lettura ricordata -- preferenza, divieto, fatto o regola -- mai un numero su una scala libera | modality | ~ parziale |
| fuso | l'informazione con cui si interpreta correttamente ogni istante letto o scritto nella casa -- senza di essa "le 8" o "ieri" non hanno un significato univoco -- letta dallo stesso campo che Home Assistant espone per la propria installazione | timezone | ✓ arriva |
| gamba | una delle sei dimensioni lungo cui l'osservatore guarda la casa: chi c'e', comfort, dispersione, energia, buono stato, sicurezza | aspect | ✓ arriva |
| genere | classifica a quale dei sei ambiti appartiene un fatto compiuto della casa -- funzionamento, presenza, energia, guasto, sicurezza, bilancio -- e insieme all'obiettivo che sceglie quali entita' guardare decide che forma prendera' il fatto quando viene scritto | genre | ~ parziale |
| gesto | il verbo con cui una proposta di costruzione viene toccata -- crearla, modificarla, cancellarla -- usato anche per scegliere la forma grammaticale del testo che la descrive all'utente | operation | ~ parziale |
| grezzo | un cambiamento di stato registrato esattamente come Home Assistant lo riporta, con le classi che lo accompagnano, prima che qualunque giudizio lo trasformi in un fatto interpretato | raw | ✓ arriva |
| impostazioni | i valori che governano il comportamento della chat -- il prompt di sistema, i giorni di conservazione della cronologia -- caricati da un file proprio e gia' completi al momento della costruzione, cosicche' un valore mancante non sia mai un caso da gestire a valle | settings | ✓ arriva |
| indice | la struttura, costruita una sola volta dai nomi e dagli alias dichiarati nell'anagrafe, che trova i riferimenti che un testo libero puo' significare -- dichiarando l'ambiguita' quando piu' di uno corrisponde -- e conferma se un identificatore proposto esiste davvero | lookup | ✓ arriva |
| instradamento | la decisione, presa in un punto solo per ogni turno, se a rispondere sia il canale a forfait o quello a consumo -- e, se serve scendere al secondo, se e' una configurazione scelta dall'utente (silenziosa) o un ripiego vero da annunciare sempre | steering | ✓ arriva |
| intento | la struttura con cui una richiesta di nuova costruzione descrive se stessa -- che cosa la fa scattare, quali passi compie, quali stati verifica, quali parametri porta, se va riusata o si ripete, se e' stata chiesta esplicitamente -- da cui si decide quale oggetto serve davvero | intent | ✓ arriva |
| interpretazione | il linguaggio chiuso a quattro caselle -- a chi si riferisce, cosa chiede, quando vale, che forza ha -- con cui il modello propone una lettura strutturata di una frase ricordata, scartando cio' che non riconosce invece di inventarlo | interpretation | ~ parziale |
| invocazione | il risultato completo di un singolo lancio del processo che parla col modello -- il codice di uscita, l'output gia' ripulito dai segreti, il flusso gia' interpretato -- pensato perche' lo stesso lancio puo' avvenire due volte nello stesso turno senza che i due tentativi vengano letti in due modi diversi | invocation | ~ parziale |
| lettura | trasforma il testo di un file di configurazione di Home Assistant nella struttura che rappresenta, sollevando quando il testo e' davvero malformato invece di restituire un risultato vuoto indistinguibile da un file senza contenuto | parse | ✓ arriva |
| memoria | il sottosistema che conserva per sempre le frasi esatte che una persona ha detto sulla sua casa insieme a come HIRIS le ha interpretate, correggibile senza toccare le parole originali, senza anonimizzazione e senza scadenza | memory | ~ parziale |
| mestiere | la funzione pura che, davanti a una richiesta, decide se serve un'automazione, uno script, una scena o una combinazione delle tre, e dice anche perche' -- consigliando senza mai bloccare chi insiste per un'altra scelta | advisor | ✓ arriva |
| migrazione | la copia, fatta una volta sola e segnata perche' non si ripeta, di un valore che viveva nello schema delle opzioni dell'add-on verso l'archivio proprio di HIRIS, cosi' che togliere l'opzione dallo schema in un rilascio successivo non ne faccia sparire il valore in silenzio | migration | ~ parziale |
| notevole | un'etichetta calcolata al momento della composizione, non conservata, che segnala le cose il cui stato attuale si scosta dalla normalita' -- acceso, aperto, in allarme -- perche' compaiano subito nel riepilogo | highlight | ✓ arriva |
| nucleo | il testo unico e sempre presente che chi ragiona riceve a ogni messaggio, ottenuto comprimendo sotto un tetto di caratteri la casa, cio' che fa da sola e i ricordi, uguale per chiunque lo consulti | briefing | ✓ arriva |
| officina | il modulo gemello di quello dei servizi ma per l'altro canale: compone e scrive su Home Assistant automazioni, script, scene e helper in due tempi -- una proposta archiviata, poi una scrittura che avviene solo con l'approvazione di un umano -- e disfa quanto ha appena creato se il passo finale viene rifiutato | workshop | ~ parziale |
| oggetti | il fatto interpretato che l'aggregazione ricava da un periodo di grezzo, nella forma che il suo genere impone -- un intervallo con inizio e fine per la maggioranza, una condizione che puo' restare aperta per un guasto, una quantita' che riassume l'intera giornata per il bilancio -- mai il dato grezzo stesso | fact | ✓ arriva |
| origine | classifica chi ha richiesto un'operazione di costruzione -- un umano che ha appena cliccato sulla pagina, oppure il modello durante un turno -- e decide se un controllo pensato per trattenere il modello si applica o si scavalca | actor | ~ parziale |
| orologio | il battito che, ricevuto un istante dall'esterno, scorre le promesse scadute e porta ciascuna a termine senza mai fermarsi per il guasto di una singola, cosi' che le altre dello stesso giro vengano comunque servite -- **corretto in fix round 1:** `clock` era stato dichiarato pulito per errore (il report diceva "una sola occorrenza, in prosa"; sono due, e la seconda -- `request.app.get("_clock")` in `api/handlers_reasoning.py:12` -- e' una chiave di dizionario, contesto non-prosa che la regola meccanica blocca. Non ho fatto eccezione: e' lo stesso standard gia' applicato a `turn`/`wake` in questo stesso lotto, bloccati per identificatori altrettanto estranei al sottosistema che stavo nominando. Nuovo inglese: `heartbeat`, pulito (`hiris/` ne ha una sola occorrenza, dentro un commento non correlato su un keep-alive SSE, tollerata) |  | ✗ non arriva — arbitrato del proprietario |
| osservatore | il modulo che si aggancia al flusso dei cambiamenti di stato e li annota cosi' come sono, applicando solo il filtro fisso dei confini, senza interpretare nulla | watcher | ✓ arriva |
| osservazioni | il deposito unico dove finiscono sia i cambiamenti annotati cosi' come sono sia i fatti compiuti che se ne ricavano, la fonte a cui un domani attingera' chi analizza | observations | ✓ arriva |
| pavimento | l'insieme fisso di classi che entra comunque, qualunque cosa dica l'obiettivo del momento: quest'ultimo puo' solo allargarlo, mai restringerlo sotto quella soglia | baseline | ~ parziale |
| piano (abbonamento) | il canale a forfait alimentato dall'abbonamento Claude Max, riconosciuto dalla sola presenza di una credenziale dedicata -- mai dal suo valore, cosi' che nessun chiamante possa stamparla per sbaglio in un log | subscription | ✓ arriva |
| piano (casa) | il livello piu' alto della gerarchia della casa, letto dal registro che Home Assistant stesso tiene per i piani di un edificio, sopra le aree e i dispositivi | floor | ~ parziale |
| plance | le pagine visive che Home Assistant lascia comporre all'utente stesso, con percorso, titolo, modalita' e viste proprie, lette dallo stesso catalogo con cui l'installazione le elenca | dashboards | ✓ arriva |
| ponte | il percorso che risponde a un turno usando l'abbonamento a forfait del modello invece della chiave a consumo, mettendo in coda il lavoro per un processo separato che lo prende in carico e lo restituisce quando e' pronto | bridge | ~ parziale |
| porta | il modulo che e' l'unico punto del prodotto da cui parte, verso Home Assistant, una chiamata di servizio, e che ne osserva l'esito aspettando l'annuncio del cambiamento di stato prima di dichiarare cosa e' successo davvero | actuator | ~ parziale |
| promessa | l'impegno per un momento futuro che l'utente ha chiesto -- fare qualcosa, oppure controllare qualcosa e riferire -- con la sua scadenza, la sua tolleranza al ritardo, e lo stato con cui si conclude | promise | ✓ arriva |
| registro | lo specchio aggiornato di cosa Home Assistant sa fare in questa casa, servizio per servizio e con i relativi parametri -- non un catalogo scritto da HIRIS, ma la copia di cio' che Home Assistant stesso dichiara di poter eseguire | registry | ~ parziale |
| riconoscitore | il modulo che decide a quale parte della casa si riferisce una frase scritta, confrontandola con nomi e alias dichiarati e restringendo poi cio' che il modello propone a cio' che esiste davvero nell'anagrafe | resolver | ✓ arriva |
| ricordi | le frasi esatte, cosi' come sono state dette, che una persona ha affidato a HIRIS -- la verita' che non si tocca mai, nemmeno quando la sua lettura viene corretta | memories | ~ parziale |
| riferimento | l'insieme dei dati con cui si interpreta ogni altra misura della casa -- unita', ora locale, valuta, lingua, paese, versione dell'installazione -- distillato una volta e mai cancellato da una lettura vuota, perche' quello di ieri resta quello giusto finche' non arriva un valore nuovo | frame | ~ parziale |
| rifiuto | una risposta negativa che porta sempre, insieme al no, il motivo per cui non si procede -- mai un diniego silenzioso -- usata sia per bloccare la scrittura di un campo non valido prima che tocchi il disco, sia per fermare un comando o una costruzione prima che tocchino Home Assistant | rejection | ✓ arriva |
| ripiego | il passaggio, dichiarato sempre e mai silenzioso, con cui un turno che non ha potuto essere servito dal canale a forfait viene rifatto da capo su quello a consumo -- uno stato non definitivo di un lavoro in coda, distinto da uno riuscito, scaduto o fallito, perche' resta da chiudere finche' non arriva una risposta | downgrade | ✓ arriva |
| schedulatore | il sottosistema che tiene le promesse fatte per un momento futuro: le risveglia quando arriva l'ora, ne porta a termine il compito o la domanda, e registra sempre come e' andata | keeper | ~ parziale |
| segno | il valore persistito che ricorda se un passo di migrazione e' gia' avvenuto, scritto anche quando non c'era nulla da copiare, cosi' che un'installazione nuova non lo cerchi piu' una volta che quel passo e' definitivamente chiuso | flag | ✓ arriva |
| semaforo | la classificazione a tre livelli, per singola azione, che decideva se procedere senza chiedere nulla, se serviva una conferma umana, oppure se l'azione era negata a prescindere -- uscita dal prodotto insieme ai suoi ultimi lettori, ma ancora nominata nei commenti che raccontano perche' non c'e' piu' | clearance | ✓ arriva |
| servizi | un'operazione che un dominio di Home Assistant dichiara di saper eseguire, identificata da un nome e dai propri parametri -- non un catalogo scritto da HIRIS, ma cio' che l'installazione stessa dichiara di poter fare | services | ✓ arriva |
| spazio | l'etichetta che distingue, dentro una cache **puramente in memoria di processo** (nessuna tabella, nessun SQL -- `CacheIndice` muore col riavvio), a quale chiamante appartiene una voce, cosi' che due strumenti sulla stessa casa non si sovrascrivano il risultato a vicenda -- **nota corretta in fix round 1:** non e' una colonna persistita (il brief originale lo affermava per errore, propagato dalla spec); e' una chiave di dizionario in `memoria/cache_indice.py:27,65,175,179` (`self._voci[spazio] = ...`), con valori che sono nomi di strumento (`"cerca"`, `"ricorda"`). Chi rinomina non trovera' nessuna tabella da migrare per questo -- solo il parametro e le due stringhe | slot | ~ parziale |
| specchio | la proiezione, calcolata una volta sola per ogni chiamante a partire dalle righe della cache di stato, in sei dizionari pronti all'uso -- valore corrente, nome, unita', classe, istante dell'ultimo cambiamento, attributi -- tenuta distinta da cio' che i quattro registri di Home Assistant dichiarano in modo statico, cosi' che le due fonti possano essere confrontate quando non coincidono | mirror | ✓ arriva |
| specie | classifica se un impegno per il futuro e' un fare qualcosa o un chiedere qualcosa da riferire -- le due sole forme ammesse, ciascuna gia' scritta come un verbo all'imperativo, con un valore fuori da queste due rifiutato subito | verb | ~ parziale |
| stati | un insieme chiuso di valori specifici che condividono una proprieta' -- quali contano come conclusi e quali come ancora in sospeso per un impegno o una proposta di costruzione, quali come attivi per un'entita', quali come guasti o transitori per un'integrazione -- usato per verificare se un valore singolo vi appartiene, mai un valore da solo | states | ~ parziale |
| strumenti | l'insieme dei nomi che il modello puo' invocare durante un turno, ciascuno con la propria definizione di argomenti, dichiarato in un unico catalogo che sia il canale sincrono sia quello del ponte leggono senza tenerne una copia propria | tools | ~ parziale |
| tempo | il modulo che decide, per una domanda su un periodo passato, quale superficie viva di Home Assistant interrogare e con quale grana, e compone come dire cio' che si e' letto -- senza conservare nulla in proprio |  | ✗ non arriva — arbitrato del proprietario |
| tetto | il limite massimo -- di caratteri in un testo, o altrove di turni in un giorno -- oltre il quale si deve tagliare o rifiutare, mai superato in silenzio: quando si taglia, il taglio stesso si dichiara dentro cio' che resta | ceiling | ✓ arriva |
| turno | il singolo scambio col modello che si apre quando una promessa che deve solo controllare si risveglia: puo' usare solo strumenti di lettura e finisce esclusivamente quando chiama lo strumento di chiusura obbligatorio -- oppure, se le risposte passano dalla catena esterna, si affida alla coda persistente invece di aspettare (vedi la nota su `ReasoningQueue`, sotto la tabella) | exchange | ~ parziale |
| verdetto | l'oggetto che la funzione di controllo restituisce: un booleano che dice se il comando puo' procedere, il motivo quando non puo', e -- quando puo' -- dominio, servizio ed entita' toccate, comprese quelle esplicitamente escluse | verdict | ✓ arriva |
| verifica | la funzione pura che esamina un comando proposto contro cio' che Home Assistant sa fare e contro lo stato vivo della casa, e decide se puo' procedere -- mai i valori dei parametri, mai le capacita' fini di un dispositivo, solo dominio, servizio e bersaglio | verification | ✓ arriva |
| versioni | l'archivio che tiene lo stato di ogni proposta di scrittura -- in attesa, in corso, applicata, rifiutata, scaduta -- insieme al corpo di prima e a quello di dopo, e conserva per sempre l'ultima copia precedente di ogni oggetto scritto perche' e' l'unica esistente al mondo e permette di tornare indietro | revisions | ✓ arriva |
| vive | il valore che Home Assistant sta dichiarando in questo momento per un'entita' -- la sua unita', la sua classe, l'istante dell'ultimo cambiamento -- letto dallo specchio dello stato invece che dal registro statico, per i casi in cui i due possono non coincidere | reported | ✓ arriva |
| vocabolario | il modulo che tiene in un posto solo le parole con cui i consumi vengono raccontati -- i cinque livelli di affidabilita' di un costo dal piu' debole al piu' forte, e le etichette con cui ogni provider viene mostrato -- cosi' che nessun'altra pagina le reinventi a modo suo | vocabulary | ✓ arriva |

> **`promessa`** (qui) e **`promesse`** (nei «Nomi degli strumenti», sotto) sono **due cose
> diverse**: la prima e' il concetto/modulo Python (il significato di «una promessa nel ponte»), la
> seconda e' la stringa che il modello legge come nome di uno strumento. Il brief che ha guidato
> questo task usa «guarda e promesse compaiono due volte» come scorciatoia per descrivere questa
> coppia insieme al caso di `guarda` — ma a differenza di `guarda` (stessa identica grafia in due
> sezioni), qui **le grafie sono diverse**: singolare (`promessa`) per il concetto, plurale
> (`promesse`) perche' cosi' e' scritta la stringa nel codice (`schedulatore/turno.py:38`, la lista
> bianca di sicurezza). Non e' un doppione mancato ne' un dedup fatto a meta': sono deliberatamente
> due voci, con due grafie diverse perche' cosi' sono nel codice.

> **`origine` e `segno`: perche' sono qui e non fra le parole ordinarie, e perche' il glossario
> vince sulla spec.** Il §4② di `docs/design/2026-08-28-il-glossario.md` elenca `origine` come
> esempio di parola ordinaria ("non entra"). Quella `origine` non e' questa: l'esempio della spec
> era un elenco a campione scritto prima di guardare il codice, mentre la voce qui viene
> dall'estrazione vera di `ORIGINI_UMANE` (vedi «I valori di dominio», in fondo) — non e' il
> sostantivo generico "origine di qualcosa", e' la parola che classifica un valore persistito (se
> un'azione l'ha fatta un umano), e per questo porta un significato costruito da HIRIS, non un
> equivalente diretto. Una regola ribaltata e' comunque una decisione scritta: questa nota lo e'.
> Stesso ragionamento, dedotto con lo stesso criterio, per `segno` (da `_SEGNI_MIGRAZIONE`): i
> valori che classifica (`seminato`, `catena_seminata`, `piano_seminato`) sono marcatori specifici
> del progetto, non un sostantivo generico.

> **`ricordi` non c'era: la riga e' stata aggiunta da questo task, non solo riempita.** Ne'
> l'estrazione di Task 1 (moduli e classi) ne' quella allargata di Task 2 (funzioni e parametri)
> lo avevano fatto uscire, pur essendo un parametro ricorrente (`casa/nucleo.py::_righe_ricordi`,
> `componi`) e una tabella vera (`CREATE TABLE ricordi`, `memoria/archivio.py`). E' un concetto,
> non un rumore: per spiegarlo serve raccontare come funziona la memoria di HIRIS. Stesso principio
> gia' applicato a `origine`/`segno` sopra -- il glossario vince sull'estrazione automatica quando
> il codice mostra un buco che lo script non poteva vedere.

> **Verdetto su `turno` (`schedulatore/turno.py`) contro `ReasoningQueue`
> (`reasoning/queue.py`): NON sono la stessa cosa, e la differenza e' voluta.** `turno` e' lo
> scambio applicativo -- una chiamata al modello con un catalogo di strumenti ristretto ai soli
> lettori, che deve chiudersi chiamando `concludi` o e' un errore dichiarato. `ReasoningQueue` e'
> l'infrastruttura di persistenza -- una coda SQLite generica con `claim`/`submit`/`sweep_expired`/
> `reclama_scaduto`, usata **sia** dai turni di chat **sia** dalle promesse instradate sul ponte,
> quando la risposta deve attraversare un confine di processo e non si puo' aspettare in linea.
> `turno._accoda_al_ponte()` e' l'unico punto in cui i due si toccano: quando la promessa va al
> ponte, il turno smette di essere uno scambio sincrono e diventa un job accodato in
> `ReasoningQueue`, chiuso altrove (`api/handlers_mcp`) o mai chiuso (`sweep_expired`). Due
> concetti a livelli diversi -- un episodio di conversazione, e il magazzino che lo fa
> sopravvivere a un riavvio del chiamante -- non la stessa cosa con due nomi: se lo fossero
> davvero, l'inglese di `turno` sarebbe stato `queue`, e non lo e'.

> **`promessa` → `promise`: un rischio per chi rinominera' il lato JavaScript, non per il modulo
> Python.** Il confronto sul codice trova `Promise` (maiuscolo) come identificatore non-prosa in
> piu' file di `hiris/app/static/` (`new Promise(...)`, `Promise.all(...)`, `Promise.resolve(...)`
> -- `chat/send.js:30`, `config/dashboard.js:410`, `config/models-route.js:165`, altri): e' il
> costruttore nativo di JavaScript per il controllo asincrono, non un nome che HIRIS ha scelto.
> Non blocca `promise` per il modulo Python (`schedulatore/promessa.py` non vede quel costruttore),
> ma chi rinominera' il concetto anche lato JavaScript dovra' scegliere una variabile locale che
> non si chiami `promise` a cuor leggero nello stesso file in cui gira gia' `new Promise(...)`:
> l'ombra sarebbe legale in JS (scoping locale) ma illeggibile.

> **`cambi` → `raw`: non e' un secondo inglese per lo stesso lemma, e' lo stesso concetto di
> `grezzo` sotto un altro sostantivo italiano.** Aggiunta in fix round 1 (rilievo del
> coordinatore): la tabella `CREATE TABLE cambi` (`cervello/archivio.py`) e' esattamente cio' che
> la riga `grezzo` descrive -- *«un cambiamento di stato registrato esattamente come Home
> Assistant lo riporta ... prima che qualunque giudizio lo trasformi in un fatto interpretato»* --
> e i commenti del sottosistema lo confermano chiamandolo "il grezzo" anche quando parlano della
> tabella nel suo insieme (`cervello/oggetti.py`: *«finche' il grezzo esiste (22 giorni)»*).
> Riusare `raw` per `cambi` non viola "nessun inglese due volte per due concetti diversi" --
> non sono due concetti diversi, sono lo stesso, con due nomi italiani. Il rischio che questa nota
> chiude: applicare alla cieca `cambio → change` (parola ordinaria gia' in tabella) avrebbe
> prodotto `changes`, un secondo nome inglese per una cosa che ogni commento del sottosistema gia'
> chiama `raw` -- la stessa incoerenza che questa fetta esiste per chiudere, ricreata al contrario.

> **`ancora` e' un OMONIMO fra due sottosistemi, non ancora deciso -- nota per il Task 6, non una
> decisione presa qui.** Aggiunta in fix round 1 (rilievo del coordinatore). Il Task 2 aveva messo
> `ancora`/`ancore` in coda al Task 6 citando solo `memoria/archivio.py` (il meccanismo con cui un
> ricordo si lega a un'entita', un'area o un dispositivo: `CREATE TABLE ancore`, colonne `tipo`,
> `riferimento`, `nome_visto`). **Esiste una seconda `ancora`, completamente diversa, in
> `consumi/archivio.py`**: una riga singleton (`CREATE TABLE ancora (id, da_ts, da_giorno)`) che
> e' il punto di riferimento temporale da cui si contano i consumi correnti, con `ancora_saldo`
> (il saldo per provider/modello congelato in quell'istante, `sposta_ancora()`) -- nessuna
> estrazione automatica aveva visto questa seconda voce. Le due `ancora` non sono la stessa cosa
> (una lega un ricordo a un pezzo di casa, l'altra e' uno zero mobile per un contatore) e per la
> fondamenta n.3 **richiedono due inglesi diversi**, non uno scelto guardando solo la memoria e
> applicato per abitudine anche ai consumi. Il Task 6 decidera' quali; questa nota esiste perche'
> chi ci arriva lo trovi scritto invece di scoprirlo a meta' rinomina.

> **`ancora` NON e' stato deciso da questo task, nonostante la nota qui sopra lo assegnasse al
> Task 6.** Verificato all'inizio di questo task: `ancora` non e' una riga di «I concetti» -- non
> compariva ne' vuota ne' piena -- ed e' invece uno dei 12 concetti che il brief dichiara ancora
> assenti dal documento, la cui aggiunta e decisione spetta a un dispaccio successivo. La nota di
> fix round 1 aveva scritto un'assegnazione che la struttura del documento non rispecchiava: il
> vincolo di questo task ("nessuna riga nuova") impedisce di correggere l'incongruenza aggiungendo
> la riga qui. Chi apre il prossimo dispaccio deve sapere che l'omonimia fra le due `ancora`
> (memoria e consumi) resta da decidere per intero, comprese le due inglesi.

> **Deciso dal Task 6bis: le due righe `ancora (memoria)` e `ancora (consumi)` sono ora in «I
> concetti».** L'ancora della memoria (il legame ricordo -- area/dispositivo/entita') e' diventata
> `tether`; l'ancora dei consumi (il punto temporale da cui si conta, spostato da
> `sposta_ancora()`) e' diventata `anchor`, non `baseline` -- vedi la nota successiva, che avvertiva
> proprio di questo rischio, per il motivo dello scarto.

> **`piano` e' un secondo OMONIMO fra due sottosistemi, trovato dalla review di questo task --
> stessa natura di `ancora` sopra, non deciso qui.** `piano` non e' una riga di «I concetti»: e'
> un altro dei 12 concetti ancora assenti dal documento. Ma il codice gia' lo usa per DUE cose
> senza relazione, e chi lo decidera' deve saperlo prima di scegliere un solo inglese per abitudine:
> 1. **il livello della casa** -- la gerarchia piani → aree → dispositivi → entita' letta dal
>    `floor_registry` di Home Assistant (`casa/archivio.py:22`, tabella `piani`, colonna
>    `livello`; `casa/anagrafe.py`, che la assembla dai quattro registri grezzi);
> 2. **il Piano dell'abbonamento Claude** -- l'abbonamento a forfait che alimenta il ponte
>    (`decisione_modelli.py`: `VARIABILE_TOKEN_DEL_PIANO`, `piano_ha_il_token()`; anche
>    `instradamento.py:70-77`, `ponte.tetto_giornaliero` letto per "il piano").
>
> Per la fondamenta n.3 servono **due inglesi diversi**, mai uno scelto guardando un sottosistema
> e applicato per abitudine anche all'altro -- lo stesso principio gia' scritto per `ancora`. Il
> dispaccio che decidera' `piano` deve anche sapere questo, prima di scegliere l'inglese del senso
> 2 -- rilievo della review di questo task: l'`ancora` dei consumi (sopra, "il punto temporale da
> cui si contano i consumi correnti") e' semanticamente vicinissima a **`baseline`**, gia' presa da
> `pavimento` ("l'insieme fisso di classi che entra comunque", riga «I concetti»). Non e' una
> collisione meccanica sul codice (nessun identificatore condiviso), ma una vicinanza di
> SIGNIFICATO che un lettore nuovo potrebbe confondere se le due finissero per suonare uguali:
> chi decide l'`ancora` dei consumi deve verificarlo prima di fissare il candidato, non scoprirlo
> dopo aver gia' scritto la riga.

> **Deciso dal Task 6bis: le due righe `piano (casa)` e `piano (abbonamento)` sono ora in «I
> concetti».** Il livello della casa e' diventato `floor` -- il confine vince: e' il nome che lo
> stesso `floor_registry` di Home Assistant usa gia' (`casa/domande.py:98`, `"floor": "piano"`;
> `proxy/ha_client.py:1374`). Il Piano dell'abbonamento Claude e' diventato `subscription` -- non
> una scelta nuova ma il nome che il codice usa gia' per lui: `_credenziali["subscription"]` e
> `NOMI["subscription"] = "Piano Claude Max"` in `decisione_modelli.py`,
> `_CONFIG_PROVIDER_IDS = ("subscription", ...)` in `api/handlers_models.py`. Il rischio segnalato
> sopra (`ancora` dei consumi vicina a `baseline`) e' stato evitato: l'ancora dei consumi e'
> `anchor`, non `baseline` -- `baseline` resta solo di `pavimento`.

> **Verdetto su `archivio` (`ArchivioCasa`, `ArchivioMemoria`, `ArchivioConsumi`,
> `ArchivioCostruzioni`, `ArchivioOsservazioni`, `ArchivioPromesse`) contro `ChatStore`
> (`chat_store.py`): fanno la stessa cosa, e il nome e' uno solo.** Lette per intero
> `memoria/archivio.py` e `casa/archivio.py`, e per intero `chat_store.py`: tutti e sette seguono
> la stessa forma, byte per byte nella struttura anche se non nel contenuto -- una classe che apre
> la propria connessione SQLite nel costruttore (`connect()`), applica uno schema con eventuali
> migrazioni versionate (`init_schema(..., version=N, migrations={...})`), e offre metodi propri
> per scrivere e rileggere lo stato di UN sottosistema, mai condivisi con un altro. `ChatStore`
> aggiunge una gestione di sessioni (finestre di conversazione) che nessun `Archivio*` ha, ma e'
> un dettaglio del SUO sottosistema (la chat ha sessioni, la memoria no), non una differenza di
> ruolo: e' la stessa distinzione per cui `ArchivioCasa` e `ArchivioPromesse` hanno metodi diversi
> fra loro pur essendo entrambi `Archivio*`. La riprova che il nome giusto era gia' nel codice:
> `hiris/app/storage.py` (`connect()`/`init_schema()`, importato da OGNI classe qui sopra E da
> `ChatStore`) dice nel proprio docstring *"Every HIRIS **store** should open its connection via
> connect()"* -- l'infrastruttura condivisa da tutti e sette gia' li chiama cosi'. Per questo
> l'inglese scelto per `archivio` e' `store`, non `archive`: un archivio in inglese implica
> permanenza, e `casa/archivio.py` dichiara nel proprio docstring di essere l'opposto -- "Non
> contiene niente di irripetibile: si cancella e si ricostruisce da HA in pochi secondi" --
> mentre `memoria/archivio.py` e' l'esatto contrario ("l'unica cosa di HIRIS che non si
> ricostruisce"). Un solo inglese per sette classi con politiche di persistenza opposte e' corretto
> solo se descrive il RUOLO (una classe-store per-sottosistema) e non la durata dei suoi dati --
> motivo per cui la colonna «che cosa fa» di `archivio`, sopra, non menziona quanto a lungo i dati
> restano.

> **`genere`, `specie`, `famiglia`: tre inglesi deliberatamente non imparentati, nonostante in
> italiano formino la stessa terna tassonomica (genere/specie/famiglia, come in biologia).** Il
> mandato di questo task avverte che tre nomi che si somigliano impedirebbero a chi legge di capire
> quale e' quale. `genere` (`GENERI`, sei ambiti di un fatto compiuto della casa) e' diventato
> `genre`; `specie` (`SPECIE`, fai/chiedi di un impegno) e' diventato `verb`; `famiglia`
> (`FAMIGLIE`, le cinque cause di un fallimento del provider) e' diventato `family`. Una traduzione
> letterale in terna biologica (genus/species/family) avrebbe ricreato in inglese la stessa
> somiglianza superficiale che le tre parole hanno gia' in italiano, nonostante classifichino tre
> cose senza relazione (un fatto osservato, un impegno futuro, un errore di rete): scartata di
> proposito. Scartati anche, durante la ricerca, candidati che collidevano con codice gia'
> scritto per un concetto DIVERSO: `kind` (blocca -- e' gia' la chiave `job.get("kind")` che
> distingue `"chat"`/`"promessa"`/`"holistic"` in `agent/runner.py:1575` e dintorni, un job della
> coda di ragionamento, non un genere di fatto), `type`/`class`/`category`/`nature` (bloccano --
> gia' assegnati rispettivamente a `tipo` [parola ordinaria], usati come parola chiave del
> linguaggio, assegnati a `categoria` [parola ordinaria], e gia' identificatore `NATURE` in
> `decisione_modelli.py:85`), `mode` (blocca per `specie` -- e' gia' il parametro `mode: str` che
> distingue l'esecuzione `"live"` da quella `"mock"` in `agent/runner.py:1151` e dintorni, un'altra
> cosa).

> **Correzione (fix round 1, rilievo del reviewer): `specie` NON e' diventato `intent`.**
> La prima stesura di questa nota assegnava `intent` a `specie`, ma `intent` e' il nome ovvio di
> `intento` (`azione/costruzione/mestiere.py:20-32`, il dizionario con `innesco`/`passi`/`stati`/
> `parametri` che descrive lo SCOPO di una costruzione richiesta) -- una delle 12 parole ancora
> senza riga in questo documento, non ancora decisa da nessun task. `specie` e `intento` sono due
> concetti diversi: `SPECIE` e' una classificazione binaria (`fai`/`chiedi`), `intento` e' una
> struttura a piu' campi. Assegnare `intent` a `specie` per primo avrebbe tolto a `intento` il suo
> nome piu' naturale quando arrivera' il dispaccio che lo decide -- vedi il terzo passo aggiunto
> alla sezione «Il controllo di collisione», sotto, che esiste apposta per questo caso. L'inglese
> corretto di `specie` e' **`verb`**: `fai` e `chiedi` sono gia' scritti come due verbi
> all'imperativo, non due categorie astratte. Zero occorrenze di `verb` in `hiris/` come
> identificatore (le uniche tre righe trovate sono prosa non correlata in `proxy/_sanitize.py:124-
> 157`, su una grammatica inglese generica). Scartato anche `mood`: `fai` e `chiedi` sono lo stesso
> modo grammaticale (l'imperativo), non due modi diversi -- "mood" avrebbe descritto una
> distinzione che qui non esiste.

> **`servizi` e `registro` vengono dalla stessa classe (`RegistroServizi`,
> `azione/registro.py:110`), ma restano due voci distinte apposta.** L'estrazione ha spezzato il
> nome composto in due parole: `registro` (gia' deciso, `registry`) e' lo specchio -- la struttura
> che HIRIS tiene aggiornata e interroga; `servizi` (`services`, qui) e' cio' che lo specchio
> contiene -- la singola operazione che un dominio di Home Assistant dichiara di saper eseguire
> (`RegistroServizi.servizio(dominio, nome)`, `.servizi_di(dominio)`), un fatto che l'installazione
> stessa dichiara e non un'invenzione di HIRIS. Non e' un doppione mancato: sono il contenitore e
> il contenuto, stessa distinzione gia' in uso fra `memoria`/`ricordi` e fra `schedulatore`/
> `promessa`.

> **`stati` riusa lo stesso lemma inglese di `stato` (`state`/`states`), e non e' una violazione
> della regola "un solo inglese per concetto" -- e' la stessa relazione grana-diversa gia' scritta
> qui sopra per `servizi`/`registro`, applicata alla coppia `stato`/`stati`.** `stato` (gia' deciso,
> `state`, con le tre accezioni gia' documentate nella nota sulle parole ordinarie) e' il singolo
> valore che una entita', una promessa o una proposta di costruzione porta in un dato momento;
> `stati` (`states`, qui) e' il PATTERN con cui il codice nomina un insieme chiuso di quei valori
> che condividono una proprieta' -- `STATI_CONCLUSI`/`STATI_SOSPESO`
> (`schedulatore/promessa.py:22,34`, `azione/costruzione/versioni.py:36`), ma anche
> `_STATI_ATTIVI` (`casa/nucleo.py:182`) e `_STATI_INTEGRAZIONE_ROTTA`/
> `_STATI_INTEGRAZIONE_TRANSITORI` (`casa/nucleo.py:821`, `cervello/osservatore.py:31`), tutte
> dello stesso schema `STATI_X = (valore, valore, ...)` usato per testare appartenenza, mai per
> leggere un valore da solo. Non e' un secondo significato di `stato` (le tre accezioni gia' viste
> restano tre), e' lo stesso concetto raccolto in insiemi con nome -- coerente con come il
> documento tratta gia' `registri`/`registro` come forme flesse dello stesso concetto nella nota
> sulle parole ordinarie.

> **`ripiego` e' anche un valore persistito, non solo un concetto -- fuori dallo scopo di questo
> task, segnalato per chi verra' dopo.** `reasoning/queue.py:161` scrive `status='ripiego'` come
> quinto stato letterale della coda (accanto a `pending`/`claimed`/`decided`/`expired`/`failed`),
> non attraverso una costante nominata come `GENERI` o `SPECIE`: e' una stringa scritta a mano
> nell'SQL. Questo task decide la parola-concetto (`ripiego` → `downgrade`) come tutte le altre 25
> righe, ma non aggiunge una riga a «I valori di dominio» per quello stato -- il divieto di questo
> task e' non aggiungere righe, e la colonna `status` in `reasoning_jobs` non ha un nome di
> costante Python da cui questo task possa citare la posizione nello stesso formato delle altre
> undici righe di quella tabella. Chi migrera' i valori di `status` deve scrivere `downgrade` al
> posto di `'ripiego'`, con lo stesso significato deciso qui.

> **La prova del lettore nuovo (Task 7): due righe cambiano inglese dopo il primo giro, tre
> restano aperte e vanno all'arbitrato del proprietario.** Metodo: il solo nome nudo dato a un
> agente senza contesto del progetto (nessuno strumento, nessun accesso al repository), che scrive
> in una frase che cosa si aspetta che quella cosa faccia. Esito confrontato con la colonna «che
> cosa fa»: `✓ arriva` (la funzione principale si vede, anche con parole diverse), `~ parziale`
> (campo giusto ma generico o incompleto), `✗ non arriva` (un'altra cosa, o «non mi dice niente»).
> Conteggio sulle 80 righe dopo il primo giro: 41 `✓`, 34 `~`, 5 `✗`. Dei 5 `✗`, il secondo giro ne
> ha risolti 2 (un nuovo inglese ciascuno) e ne ha lasciati 3 bocciati due volte su due. Conteggio
> finale: **42 `✓`, 35 `~`, 3 `✗` in arbitrato** (`casa`, `orologio`, `tempo`).
>
> **`anagrafe`: `directory` bocciato, sostituito da `topology`.** Il lettore nuovo ha letto
> `directory` come cartella di filesystem — *«un catalogo organizzato di elementi, in informatica
> una cartella con contenuti»* — non come il modulo che assembla quattro registri in una
> gerarchia. Al secondo giro, due lettori indipendenti su `topology` hanno risposto in modo
> sovrapponibile citando esplicitamente «dispositivi» e «nodi collegati/disposti» — vicino alla
> funzione reale ma ancora generico (potrebbe descrivere una rete o un grafo qualunque, non
> specificamente l'assemblaggio di piani/aree/dispositivi/entita' in un'unica gerarchia): `~
> parziale`, non `✓`, ma non piu' un `✗` — resta deciso qui, non va all'arbitrato.
>
> **`esito`: `disposition` bocciato, sostituito da `occurrence`.** Il lettore nuovo ha risposto
> *«Non mi dice niente di preciso nel contesto di programmazione»* — bocciatura netta, gia'
> segnalata come rischio nel report del Task 5 (*"e' un inglese piu' colto/amministrativo del
> semplice outcome che la lettura del codice avrebbe suggerito"*). Al secondo giro, `occurrence`
> ha ricevuto da due lettori indipendenti risposte convergenti sul nucleo della frase — *«un'istanza
> singola di un evento... in un momento specifico»* / *«una singola istanza/verificarsi di un
> evento, spesso con timestamp»* — che nominano "il fatto di cio' che e' davvero successo": `✓
> arriva`.
>
> **`casa`, `orologio`, `tempo`: due candidati bocciati su due, vanno all'arbitrato del
> proprietario — non un terzo giro, per il vincolo "massimo due giri per parola".** Per ciascuno,
> la frase «che cosa fa» (gia' in tabella sopra), i due inglesi provati e la risposta testuale del
> lettore che li ha bocciati:
>
> - **`casa`** — *"la rappresentazione strutturata a quattro livelli (piano, area, dispositivo,
>   entita') degli spazi fisici su cui HIRIS ragiona, costruita a partire dai registri di Home
>   Assistant."* Primo giro, `home`: *«il punto di partenza principale di un'applicazione, la
>   schermata iniziale»* — ha letto *homepage*, non "la casa". Secondo giro, `house`, dato a due
>   lettori indipendenti: sono **divergenti** — uno risponde *«un contenitore/raggruppamento
>   principale di organizzazione (come una categoria padre o un'area logica)»*, l'altro *«non mi
>   dice niente di preciso — potrebbe essere quasi qualunque cosa (contenitore, entita' di
>   dominio, edificio in un gioco)»*. Due letture cosi' distanti sullo stesso nome sono gia' un
>   esito: il nome non porta il concetto in modo affidabile.
> - **`orologio`** — *"il battito che, ricevuto un istante dall'esterno, scorre le promesse
>   scadute e porta ciascuna a termine senza mai fermarsi per il guasto di una singola."* Primo
>   giro, `heartbeat`: *«un segnale periodico che attesta il funzionamento e lo stato vitale di
>   qualcosa»* — legge un ping di liveness/health-check, non un lavoratore attivo che processa le
>   promesse scadute. Secondo giro, `pulse`, due lettori indipendenti concordi ma sulla stessa
>   lettura sbagliata: *«un segnale periodico che batte/ripete a intervalli regolari, o lo stato
>   di vitalita' di un sistema»* e — piu' netto — *«qualcosa legato a un segnale periodico o
>   **heartbeat** — un check di attivita'/salute del sistema»*: il secondo lettore usa
>   letteralmente la parola gia' bocciata. Non e' un nome nuovo, e' lo stesso equivoco con
>   un'altra grafia.
> - **`tempo`** — *"il modulo che decide, per una domanda su un periodo passato, quale superficie
>   viva di Home Assistant interrogare e con quale grana, e compone come dire cio' che si e'
>   letto — senza conservare nulla in proprio."* Primo giro, `span`: *«un intervallo o
>   un'estensione delimitata (di tempo, di dati, di contesto)»* — un intervallo passivo, vicino al
>   senso di `period` in Home Assistant, non il modulo attivo che decide e compone. Secondo giro,
>   `timeframe`, due lettori indipendenti convergenti sullo stesso equivoco: *«una finestra di
>   tempo definita entro cui qualcosa accade o e' valido»* e *«un intervallo temporale (data/ora
>   di inizio e fine) usato per **filtrare o delimitare** dei dati»* — di nuovo un valore/parametro
>   di tempo, non il modulo che decide la fonte e la grana e compone la risposta.
>
> Le tre righe restano con la colonna «inglese» vuota (non ancora deciso, non dimenticato) finche'
> il proprietario non arbitra. Dettaglio completo del dispaccio e delle due letture indipendenti in
> `.superpowers/sdd/2026-08-28-il-glossario/task-7-risposte.md` e `task-7-report.md` (non
> tracciati, cartella di processo).

## Le parole ordinarie

Equivalenti diretti, che non perdono niente nella conversione. Nessun giudizio da fare, nessuna
prova del lettore nuovo: vanno in una tabella di conversione decisa una volta e applicata
meccanicamente.

**Aggiornato durante l'esecuzione del Task 2: l'estrazione e' stata allargata.** Il Task 1
estraeva da nomi di modulo e di classe, e le parole ordinarie non vivono li': vivono nei nomi di
**funzione e parametro**. Un secondo giro di estrazione su `hiris/app/**/*.py` (funzioni e
parametri, non piu' moduli e classi) ha fatto uscire 206 parole candidate usate 3 o piu' volte
(209 nella misura del coordinatore, presa qualche riga prima di quest'ultima; la differenza sono
poche parole gia' fissate nel frattempo da questo stesso task, quindi tolte a monte dal filtro).
Di queste, **112 sono ordinarie** e sono nella tabella qui sotto (piu' le 6 che c'erano gia').
Il resto e' rumore da tre famiglie (vedi il report del Task 2) o un concetto travestito, dichiarato
al Task 6 invece che deciso qui.

| italiano | inglese |
|---|---|
| adesso | now |
| aggiornato | updated |
| aggiungi | add |
| albero | tree |
| ambiente | environment |
| anteprima | preview |
| area | area |
| argomento | argument |
| attesa | pending |
| attivo | active |
| attributo | attribute |
| avviso | notice |
| cambio | change |
| campo | field |
| carica | load |
| cartella | folder |
| categoria | category |
| chiamata | call |
| chiave | key |
| chiudi | close |
| classe | class |
| codice | code |
| configurazione | configuration |
| confronto | comparison |
| consumi | usage |
| conta | count |
| corpo | body |
| corrente | current |
| costo | cost |
| crea | create |
| credenziale | credential |
| dati | data |
| dettaglio | detail |
| dimensione | dimension |
| disponibile | available |
| dispositivo | device |
| dominio | domain |
| effettivo | actual |
| elenca | list |
| elenco | list |
| entita | entity |
| errore | error |
| esecuzione | execution |
| eta | age |
| etichetta | label |
| evento | event |
| fonte | source |
| frase | phrase |
| giorno | day |
| giro | round |
| gratuito | free |
| guarda | look |
| identificatore | identifier |
| impronta | fingerprint |
| innesca | trigger |
| integrazione | integration |
| interno | internal |
| inventario | inventory |
| leggi | read |
| leggibile | readable |
| letto | read |
| limite | limit |
| locale | local |
| mantieni | keep |
| massimo | maximum |
| minimo | minimum |
| modelli | models |
| modello | model |
| motivo | reason |
| nome | name |
| normalizza | normalize |
| nota | note |
| oggi | today |
| opzioni | options |
| ora | hour |
| ottieni | get |
| percorso | path |
| posizione | position |
| pota | prune |
| predefinito | default |
| problema | problem |
| programma | schedule |
| proposta | proposal |
| pulisci | clean |
| punto | point |
| quante | count |
| registra | log |
| richiesta | request |
| riga | row |
| rileggi | reread |
| risolto | resolved |
| risolvi | resolve |
| risposta | answer |
| ritardo | delay |
| scadenza | deadline |
| scelto | chosen |
| scrivi | write |
| secondo | second |
| segna | mark |
| semina | seed |
| servizio | service |
| sezione | section |
| sistema | system |
| soggetto | subject |
| sostituisci | replace |
| statistiche | statistics |
| stato | state |
| termine | term |
| testo | text |
| tipo | type |
| traduci | translate |
| trova | find |
| unita | unit |
| valida | validate |
| valore | value |
| verificabile | verifiable |
| voce | entry |
| vuoto | empty |

> **`guarda`** compare **anche** fra i «Nomi degli strumenti» (sotto). Qui e' una parola ordinaria
> (o un nome di funzione qualunque); li' e' il nome di uno strumento esposto al modello — la stessa
> grafia, per due ragioni diverse, nella stessa lingua di partenza. Non e' un errore di copia:
> sono due voci a se', e ciascuna avra' la propria decisione.

> **`riga`: la stessa parola, due significati.** Negli archivi SQLite (`cervello/archivio.py`,
> `memoria/archivio.py`, `casa/archivio.py`, `azione/cronaca.py`, `schedulatore/promessa.py`,
> `decisione_modelli.py`) `riga`/`righe` e' una riga di tabella: `row` e' corretto e non perde
> niente. Ma in `casa/nucleo.py` (`_riga_adesso`, `_righe_sistema`, `_righe_casa`,
> `_righe_notevole`, `_righe_comportamento`, `_righe_ricordi`, `_righe_lacune`, `righe_pool` —
> i costruttori del prompt di sistema) `riga` e' una riga di **testo**, non di tabella: la' la
> parola giusta e' `line`, non `row`. La tabella sopra fissa l'equivalente di default (`row`,
> il senso maggioritario e quello dato per obbligato dal brief); chi rinomina in `casa/nucleo.py`
> deve leggere il contesto e usare `line`, non applicare `row` alla cieca.

> **`stato`: tre significati, non uno.** La tabella sopra lo marca confine → `state`: e' giusto
> per il senso principale, lo stato di un'entita' di Home Assistant (`casa/domande.py`,
> `casa/nucleo.py`, e la colonna `stato` di `costruzioni`/`promesse` che tiene i valori di
> `STATI_SOSPESO`/`STATI_CONCLUSI` — quello e' ancora «lo stato di qualcosa», `state` non mente).
> Ma **non e' l'unico senso**: in `api/handlers_mcp.py:207` (`def _errore(..., *, stato: int =
> 200)`, passato a `web.json_response(..., status=stato)`, e usato con `stato=400` alle righe 540,
> 548, 568) `stato` e' uno **status HTTP**, un intero, non lo stato di un'entita' — `state: int =
> 200` sarebbe un nome che mente. E in `costo_stato` (`agent/runner.py:1123`,
> `backends/openai_compat_runner.py:394,408`, `claude_runner.py:741,755`,
> `consumi/archivio.py` — colonna e funzioni, alimentato da `consumi/vocabolario.py:
> stato_e_costo()`) `stato` e' una **classificazione del costo di una chiamata** (`compreso`,
> `gratuito`, `reale`, `misurato`, `non_noto`), non uno stato nel senso HA ne' un codice HTTP.
> La tabella sopra fissa `state` come equivalente di default per il caso principale; chi rinomina
> `api/handlers_mcp.py:207` e i dintorni di `stato=400/540/548/568` deve usare `status` (il nome
> che HTTP e aiohttp usano gia'), e chi rinomina `costo_stato` deve usare qualcosa come
> `cost_status`/`cost_state` **deciso insieme al resto del vocabolario dei costi**, non `state`
> applicato alla cieca.
>
> **Il metodo con cui e' stata cercata la terza famiglia di errori (parole generiche con piu' di
> un senso):** oltre a `stato`, sono state riesaminate le altre parole generiche e frequenti della
> tabella — `valore`, `voce`, `tipo`, `campo`, `chiave`, `nome`, `motivo`, `testo` (`origine` no:
> e' gia' un concetto, non e' in questa tabella) — guardando per ciascuna in quali sottosistemi
> compare e con che tipo di parametro. Nessuna delle otto ha mostrato la stessa spaccatura di
> `stato`: `tipo` ha un caso vicino (classificatore di dominio in `proxy/ha_client.py: legami` vs.
> nome di tipo dato in `api/handlers_impostazioni.py: _tipo`), ma in entrambi i casi l'inglese
> «type» resta corretto senza perdere informazione — a differenza di «state» per uno status HTTP.
> Le altre sette (`valore`, `voce`, `campo`, `chiave`, `nome`, `motivo`, `testo`) sono risultate
> genuinamente uniformi in ogni sottosistema in cui compaiono.

> **Quattro forme flesse non compaiono ne' qui ne' in «I concetti», di proposito.**
> L'estrazione allargata ha fatto uscire `vivi` (masch. plur. — `casa/domande.py:209,437,464,543,
> 603,764` `attributi_vivi`, `casa/strumenti.py:1158` `nomi_vivi`), `direzioni` (plur. —
> `server.py:917`, `cervello/oggetti.py:570`, `proxy/ha_client.py:1482` `direzioni_energia`),
> `registri` (plur. — `casa/archivio.py:245`, `proxy/ha_client.py:1620,1678`) e `interpreta`
> (verbo — `server.py:2773` `_interpreta`, `schedulatore/orologio.py:27`,
> `schedulatore/turno.py:121` `interpreta_promessa`): la stessa radice di quattro voci gia' in
> «I concetti» (`vive`, `direzione`, `registro`, `interpretazione`). Non le ho aggiunte qui come
> ordinarie ne' come nuove voci in «I concetti»: dare un secondo inglese alla stessa radice
> violerebbe la fondamenta n.3 (stessa cosa, stessa forma) — ed e' esattamente il difetto che
> questa fetta esiste per chiudere. **Chi decidera' l'inglese di `vive`, `direzione`, `registro`
> e `interpretazione` in «I concetti» deve usare lo stesso identico inglese anche per queste
> quattro forme flesse**, nei file e alle righe elencati sopra: non e' una seconda decisione, e'
> la stessa applicata a un'altra forma grammaticale.

**La coda lunga (le parole usate una o due volte) non si decide riga per riga: si applica una
regola sola.** Al momento della rinomina si usa l'equivalente inglese piu' ovvio della parola
italiana, verificando solo che non collida con un nome inglese gia' assegnato altrove nello stesso
modulo — senza aprire una voce di glossario per ciascuna. Se durante la rinomina una di queste
parole si rivela un concetto travestito (la stessa identica domanda del Task 6: per spiegarla
serve raccontare come funziona HIRIS), si sposta fra i concetti anche se e' stata usata una sola
volta — la soglia dei 3 usi separa cio' che vale la pena estrarre in automatico da cio' che si
guarda a mano, non cio' che e' ordinario da cio' che e' un concetto.

## I nomi degli strumenti

**Non sono identificatori: sono dati.** Vivono come stringhe nella lista bianca di sicurezza
(`schedulatore/turno.py:38`), nell'etichetta `spazio` persistita nell'indice della memoria
(`memoria/cache_indice.py:27`) e nel testo del prompt (`casa/domande.py:386`,
`memoria/interpretazione.py:198`). Il nome si decide qui; **si applica in una fetta a se'**, con la
migrazione dei dati.

| italiano | che cosa fa | inglese |
|---|---|---|
| cerca |  |  |
| guarda |  |  |
| legami |  |  |
| ricorda |  |  |
| richiama |  |  |
| esegui |  |  |
| prometti |  |  |
| promesse |  |  |
| disdici |  |  |
| costruisci |  |  |
| conferma |  |  |
| andamento |  |  |
| accaduto |  |  |

## I valori di dominio

**Aggiunto il 28/08 durante l'esecuzione: la spec non li aveva visti.** Emersi dalla review del
Task 1, che ha trovato `genere` — un concetto vero, assente dalla prima stesura perche' non e' mai
nome di modulo ne' di classe.

Esiste uno strato di vocabolario che vive **come valore**, non come identificatore: tassonomie di
dominio dichiarate come costanti Python e **persistite nei database** (`genere TEXT NOT NULL` in
`cervello/archivio.py:91` e `azione/cronaca.py:65`, `specie TEXT NOT NULL` in
`schedulatore/archivio.py:34`). **Sono dati, esattamente come i 13 nomi degli strumenti** qui sopra:
il nome si decide qui, si applica in una fetta che sa gestire la migrazione di cio' che e' gia'
scritto — non con la rinomina degli identificatori.

La parola che classifica ciascuna costante (`genere`, `specie`, `famiglia`, `gesto`, `direzione`,
`segno`, `origine`) e' un'altra cosa — un **identificatore**, quindi un concetto: e' gia' in «I
concetti», sopra.

| costante | valori | dove vive | valori — inglese |
|---|---|---|---|
| `GENERI` | funzionamento · presenza · energia · guasto · sicurezza · bilancio | `cervello/oggetti.py:44`; colonna `genere` in `cervello/archivio.py:91` e `azione/cronaca.py:65` |  |
| `GAMBE` | chi c'e' · comfort · dispersione · energia · buono stato · sicurezza | `cervello/pavimento.py:21` — i nomi delle sei gambe del pavimento dell'osservatore |  |
| `SPECIE` | fai · chiedi | `schedulatore/promessa.py:21`; colonna `specie` in `schedulatore/archivio.py:34` |  |
| `STATI_CONCLUSI` | mantenuta · saltata · disdetta · fallita | `schedulatore/promessa.py:22` — stato concluso delle promesse |  |
| `STATI_SOSPESO` | in_attesa · in_corso | `azione/costruzione/versioni.py:36` e `schedulatore/promessa.py:34` — definita due volte, stesso valore |  |
| `DIREZIONI_BILANCIO` | produzione · autoconsumo · immissione · prelievo · carica · scarica · consumo | `cervello/oggetti.py:71` — le direzioni del bilancio energia dell'osservatore |  |
| `FAMIGLIE` | credenziale · modello · irraggiungibile · scaduto · altro | `esiti_provider.py:63` — famiglie di esito dei provider LLM |  |
| `_GESTI` | crea · modifica · cancella | `azione/costruzione/officina.py:56` — i gesti sulle costruzioni |  |
| `_TIPI_COMPORTAMENTO` | automazione · script | `casa/domande.py:68` — i tipi di comportamento della casa |  |
| `ORIGINI_UMANE` | pagina | `azione/costruzione/officina.py:54` — l'origine di un'azione quando e' un umano a farla |  |
| `_SEGNI_MIGRAZIONE` | seminato · catena_seminata · piano_seminato | `api/handlers_models.py:94` — i segni lasciati da una migrazione gia' avvenuta |  |
| `_LEGAMI_COMPRIMARI` | entita · automazione · scena · script | `server.py:807` — i tipi di comprimari a cui una promessa puo' legarsi |  |

> Perche' `tipo` non compare come riga nuova per `_TIPI_COMPORTAMENTO`: non e' mai uscito
> dall'estrazione (Step 1/2), e col criterio del §4② sarebbe comunque una **parola ordinaria** — un
> sostantivo generico ("type"), cosi' come negli esempi certi del brief — non un concetto da
> aggiungere. Perche' `legame`/`comprimari` non generano una nuova voce per `_LEGAMI_COMPRIMARI`: la
> costante enumera **tipi di comprimari**, e sia `legami` (nomi degli strumenti) sia `comprimari`
> (concetti) sono gia' voci a se' — non serve una terza parola.
