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
| anagrafe | il modulo che legge i quattro registri grezzi di Home Assistant -- piani, aree, dispositivi, entita' -- e li assembla in un'unica gerarchia coerente | directory |  |
| archivio |  |  |  |
| ascolto |  |  |  |
| azione | il sottosistema che sa cosa questa casa puo' fare secondo Home Assistant e lo fa succedere davvero -- chiamando i suoi servizi, scrivendo la sua configurazione -- sempre passando per un solo punto per ciascun canale | action |  |
| caricatore |  |  |  |
| casa | la rappresentazione strutturata a quattro livelli (piano, area, dispositivo, entita') degli spazi fisici su cui HIRIS ragiona, costruita a partire dai registri di Home Assistant | home |  |
| catena | l'ordine di ripiego fra i provider del modello: se il primo non risponde si passa al successivo, ed e' la sola fonte di verita' sulla priorita' -- non un ingrediente che ogni pagina ricostruisce a modo suo | chain |  |
| cervello | il sottosistema che osserva nel tempo cio' che succede e ne impara i pattern per dedurre correzioni utili, con una memoria e un obiettivo propri, distinto dal resto del prodotto | mind |  |
| comportamento | l'elenco di automazioni e script gia' in esecuzione da soli, ottenuto incrociando cio' che i file dichiarano con cio' che lo stato conferma esistere davvero, cosicche' HIRIS non riproponga qualcosa gia' fatto | behavior |  |
| comprimari |  |  |  |
| costruzione | il sottosistema che compone e scrive su Home Assistant nuovi oggetti di configurazione -- automazioni, script, scene, helper -- attraverso un ciclo di proposta, approvazione umana e scrittura, con la possibilita' di disfare cio' che ha appena creato e di tornare indietro | construction |  |
| cronaca | il registro unico e leggibile di ogni tentativo che ha gia' superato i controlli -- un comando o una scrittura di configurazione, riuscito o fallito -- con chi l'ha chiesto, cosa e' successo e quando, interrogabile a prescindere da chi ha agito | journal |  |
| decisione |  |  |  |
| direzione |  |  |  |
| dispatcher |  |  |  |
| domande | le tre funzioni che, su richiesta esplicita, restituiscono il dettaglio di una cosa sola -- cercarla per nome, vederne il corpo, sapere chi la tocca -- quando il riepilogo sempre presente non basta | queries |  |
| esito | il fatto osservabile su cio' che e' davvero successo in un tentativo -- un provider che ha rifiutato, un comando riuscito o fallito, un tempo di attesa misurato -- mai un'ipotesi sul perche' | disposition |  |
| famiglia |  |  |  |
| flusso |  |  |  |
| forme | il modulo puro che, a partire dai parametri portati dal modello, compone la struttura pronta da scrivere per ciascun tipo di oggetto -- automazione, script, scena -- generando anche un identificatore che in questa casa non esiste ancora | shapes |  |
| gamba | una delle sei dimensioni lungo cui l'osservatore guarda la casa: chi c'e', comfort, dispersione, energia, buono stato, sicurezza | aspect |  |
| genere |  |  |  |
| gesto |  |  |  |
| grezzo | un cambiamento di stato registrato esattamente come Home Assistant lo riporta, con le classi che lo accompagnano, prima che qualunque giudizio lo trasformi in un fatto interpretato | raw |  |
| impostazioni |  |  |  |
| indice | la struttura, costruita una sola volta dai nomi e dagli alias dichiarati nell'anagrafe, che trova i riferimenti che un testo libero puo' significare -- dichiarando l'ambiguita' quando piu' di uno corrisponde -- e conferma se un identificatore proposto esiste davvero | lookup |  |
| instradamento |  |  |  |
| interpretazione | il linguaggio chiuso a quattro caselle -- a chi si riferisce, cosa chiede, quando vale, che forza ha -- con cui il modello propone una lettura strutturata di una frase ricordata, scartando cio' che non riconosce invece di inventarlo | interpretation |  |
| invocazione | il risultato completo di un singolo lancio del processo che parla col modello -- il codice di uscita, l'output gia' ripulito dai segreti, il flusso gia' interpretato -- pensato perche' lo stesso lancio puo' avvenire due volte nello stesso turno senza che i due tentativi vengano letti in due modi diversi | invocation |  |
| lettura |  |  |  |
| memoria | il sottosistema che conserva per sempre le frasi esatte che una persona ha detto sulla sua casa insieme a come HIRIS le ha interpretate, correggibile senza toccare le parole originali, senza anonimizzazione e senza scadenza | memory |  |
| mestiere | la funzione pura che, davanti a una richiesta, decide se serve un'automazione, uno script, una scena o una combinazione delle tre, e dice anche perche' -- consigliando senza mai bloccare chi insiste per un'altra scelta | advisor |  |
| migrazione |  |  |  |
| notevole | un'etichetta calcolata al momento della composizione, non conservata, che segnala le cose il cui stato attuale si scosta dalla normalita' -- acceso, aperto, in allarme -- perche' compaiano subito nel riepilogo | highlight |  |
| nucleo | il testo unico e sempre presente che chi ragiona riceve a ogni messaggio, ottenuto comprimendo sotto un tetto di caratteri la casa, cio' che fa da sola e i ricordi, uguale per chiunque lo consulti | briefing |  |
| officina | il modulo gemello di quello dei servizi ma per l'altro canale: compone e scrive su Home Assistant automazioni, script, scene e helper in due tempi -- una proposta archiviata, poi una scrittura che avviene solo con l'approvazione di un umano -- e disfa quanto ha appena creato se il passo finale viene rifiutato | workshop |  |
| oggetti | il fatto interpretato che l'aggregazione ricava da un periodo di grezzo, nella forma che il suo genere impone -- un intervallo con inizio e fine per la maggioranza, una condizione che puo' restare aperta per un guasto, una quantita' che riassume l'intera giornata per il bilancio -- mai il dato grezzo stesso | fact |  |
| origine |  |  |  |
| orologio | il battito che, ricevuto un istante dall'esterno, scorre le promesse scadute e porta ciascuna a termine senza mai fermarsi per il guasto di una singola, cosi' che le altre dello stesso giro vengano comunque servite | clock |  |
| osservatore | il modulo che si aggancia al flusso dei cambiamenti di stato e li annota cosi' come sono, applicando solo il filtro fisso dei confini, senza interpretare nulla | watcher |  |
| osservazioni | il deposito unico dove finiscono sia i cambiamenti annotati cosi' come sono sia i fatti compiuti che se ne ricavano, la fonte a cui un domani attingera' chi analizza | observations |  |
| pavimento | l'insieme fisso di classi che entra comunque, qualunque cosa dica l'obiettivo del momento: quest'ultimo puo' solo allargarlo, mai restringerlo sotto quella soglia | baseline |  |
| ponte |  |  |  |
| porta | il modulo che e' l'unico punto del prodotto da cui parte, verso Home Assistant, una chiamata di servizio, e che ne osserva l'esito aspettando l'annuncio del cambiamento di stato prima di dichiarare cosa e' successo davvero | actuator |  |
| promessa | l'impegno per un momento futuro che l'utente ha chiesto -- fare qualcosa, oppure controllare qualcosa e riferire -- con la sua scadenza, la sua tolleranza al ritardo, e lo stato con cui si conclude | promise |  |
| registro | lo specchio aggiornato di cosa Home Assistant sa fare in questa casa, servizio per servizio e con i relativi parametri -- non un catalogo scritto da HIRIS, ma la copia di cio' che Home Assistant stesso dichiara di poter eseguire | registry |  |
| riconoscitore | il modulo che decide a quale parte della casa si riferisce una frase scritta, confrontandola con nomi e alias dichiarati e restringendo poi cio' che il modello propone a cio' che esiste davvero nell'anagrafe | resolver |  |
| ricordi | le frasi esatte, cosi' come sono state dette, che una persona ha affidato a HIRIS -- la verita' che non si tocca mai, nemmeno quando la sua lettura viene corretta | memories |  |
| rifiuto | una risposta negativa che porta sempre, insieme al no, il motivo per cui non si procede -- mai un diniego silenzioso -- usata sia per bloccare la scrittura di un campo non valido prima che tocchi il disco, sia per fermare un comando o una costruzione prima che tocchino Home Assistant | rejection |  |
| ripiego |  |  |  |
| schedulatore | il sottosistema che tiene le promesse fatte per un momento futuro: le risveglia quando arriva l'ora, ne porta a termine il compito o la domanda, e registra sempre come e' andata | keeper |  |
| segno |  |  |  |
| semaforo |  |  |  |
| servizi |  |  |  |
| spazio | l'etichetta che distingue, dentro la cache in memoria dell'indice, a quale chiamante appartiene una voce, cosi' che due strumenti sulla stessa casa non si sovrascrivano il risultato a vicenda -- **nota per la migrazione:** questo stesso nome vive gia' come valore di una colonna persistita (`memoria/cache_indice.py:27`); rinominare il concetto qui non rinomina da solo quella colonna, sono due decisioni distinte | slot |  |
| specie |  |  |  |
| stati |  |  |  |
| strumenti |  |  |  |
| tempo | il modulo che decide, per una domanda su un periodo passato, quale superficie viva di Home Assistant interrogare e con quale grana, e compone come dire cio' che si e' letto -- senza conservare nulla in proprio | span |  |
| turno | il singolo scambio col modello che si apre quando una promessa che deve solo controllare si risveglia: puo' usare solo strumenti di lettura e finisce esclusivamente quando chiama lo strumento di chiusura obbligatorio -- oppure, se le risposte passano dalla catena esterna, si affida alla coda persistente invece di aspettare (vedi la nota su `ReasoningQueue`, sotto la tabella) | exchange |  |
| verdetto | l'oggetto che la funzione di controllo restituisce: un booleano che dice se il comando puo' procedere, il motivo quando non puo', e -- quando puo' -- dominio, servizio ed entita' toccate, comprese quelle esplicitamente escluse | verdict |  |
| verifica | la funzione pura che esamina un comando proposto contro cio' che Home Assistant sa fare e contro lo stato vivo della casa, e decide se puo' procedere -- mai i valori dei parametri, mai le capacita' fini di un dispositivo, solo dominio, servizio e bersaglio | verification |  |
| versioni | l'archivio che tiene lo stato di ogni proposta di scrittura -- in attesa, in corso, applicata, rifiutata, scaduta -- insieme al corpo di prima e a quello di dopo, e conserva per sempre l'ultima copia precedente di ogni oggetto scritto perche' e' l'unica esistente al mondo e permette di tornare indietro | revisions |  |
| vive |  |  |  |
| vocabolario |  |  |  |

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
