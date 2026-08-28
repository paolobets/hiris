# GLOSSARIO — come si chiamano le cose in HIRIS

Spec: `docs/design/2026-08-28-il-glossario.md`.

Questo documento non e' storia: e' la **regola**. Si consulta ogni volta che nasce un nome, e si
aggiorna quando nasce un concetto. Non porta una data di redazione perche' non e' la fotografia di
un giorno: e' vivo, e cambia quando cambia il codice.

**Stato di questo documento (corretto durante la review finale del ramo: la frase precedente
diceva il contrario e nessuno l'aveva piu' aggiornata dopo il Task 9): l'elenco e' completo E le
colonne sono decise.** «I concetti», «Le parole ordinarie» e «I nomi degli strumenti» hanno tutte
e tre le colonne piene su ogni riga -- nessuna vuota per dimenticanza, nessuna in sospeso. Fa
eccezione, dichiarata e non silenziosa, «I valori di dominio»: vedi la nota di rinvio in quella
sezione, in fondo al documento. Una riga di una qualunque tabella con una cella vuota, se mai ne
ricomparira' una in futuro, significa «non ancora deciso», non «dimenticato» -- ma oggi, salvo
quella sezione, non ce n'e' nessuna.

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

**Istruzione mancante, aggiunta durante la re-review mirata: quando nasce un concetto, la riga
entra con l'inglese vuoto, e l'inglese si decide in un passaggio successivo -- mai nello stesso
passaggio.** Il passo 3 del controllo, sotto, scatta solo se questo gesto avviene per primo:
qualcuno scrive la riga italiana con la colonna «inglese» vuota, e SOLO DOPO qualcun altro (o lo
stesso, in un secondo momento) sceglie un candidato. Nessuna riga di questo documento, prima
d'ora, lo prescriveva: il comportamento naturale — scrivere la riga e il suo inglese nello stesso
istante, perche' e' cosi' che viene da lavorare — salterebbe il presupposto senza che nessuno se ne
accorga, e il passo 3 non scatterebbe mai per il concetto appena nato. Non e' un dettaglio di
stile: e' la differenza fra un controllo che protegge le parole non ancora decise (il suo scopo
dichiarato, vedi il caso `intent`/`intento` sotto) e un controllo che non ha mai l'occasione di
proteggere nessuno perche' il momento in cui servirebbe non viene mai creato.

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

**Corretto durante la review finale del ramo: il comando qui sopra restituisce zero righe --
verificato eseguendolo davvero, non leggendo la tabella a occhio.** Non e' un test che non puo'
fallire per un difetto di scrittura: e' che oggi non c'e' piu' nessuna parola italiana di «I
concetti» con la colonna «inglese» vuota, punto -- verificato anche in modo indipendente per
l'intero documento, non solo per questa sezione (vedi i controlli di completezza del Task 9). Le
dodici parole che il Task 2 aveva segnalato come concetti senza riga (`riferimento`, `bersaglio`,
`fuso`, `componi`, `condizioni`, `piano`, `ancora`, `specchio`, `intento`, `forza`, `tetto`,
`plance`) sono **tutte e dodici** righe decise oggi: il Task 6 ne ha decise la maggior parte (fra
cui `intento`, l'esempio citato sopra), il Task 6bis ha chiuso le ultime due, `ancora` e `piano`,
sdoppiate in quattro righe per l'omonimia gia' raccontata sopra. Nessuna delle dodici e' rimasta
indietro, nonostante nessun singolo task si fosse mai preso esplicitamente il compito di
"aggiungere le righe vuote residue" per tutte insieme.
**Il passo non e' morto, e' inerte per il motivo giusto**: protegge le parole italiane non ancora
decise da un candidato che le collida per primo, e oggi non ce ne sono perche' il vocabolario
di questo giro e' chiuso -- non perche' la difesa non sappia scattare. Resta scritto, non
cancellato, perche' il documento e' dichiaratamente vivo («si aggiorna quando nasce un concetto»,
in testa): il giorno in cui un nuovo concetto italiano entrera' in «I concetti» ancora senza
inglese (anche solo come riga vuota), questo stesso comando tornera' a trovarlo e a farlo valere
prima che un candidato successivo lo scavalchi. Cancellarlo ora, per il solo fatto che restituisce
zero oggi, toglierebbe la protezione proprio nel momento in cui tornera' a servire.

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

**Eccezione, e va scritta qui perche' la regola sopra non la contiene: il confine batte la
collisione.** Corretto durante la review finale del ramo — il documento gia' applicava questa
eccezione in almeno tre punti (`target` per `bersaglio`, sotto; `related` per `legami` e
`logbook` per `accaduto`, «I nomi degli strumenti») ma non l'aveva mai scritta nella sezione della
regola, cosi' come scritta oggi: un lotto futuro che applicasse la regola alla lettera bloccherebbe
`target` (identificatore per un altro concetto, `storage.py:56`, `for target in range(...)`) e
sceglierebbe un sinonimo inventato al posto del nome che Home Assistant o un provider LLM usano
gia' per la stessa cosa — esattamente la traduzione-travestita-da-rinomina che questa fetta esiste
per impedire. **Ordine di applicazione: prima si controlla se il candidato e' un nome di confine
(HA o un provider lo usano gia' per QUESTA identica cosa); se lo e', vince e la collisione con un
significato diverso altrove nel codice non lo scarta. Solo se non e' un nome di confine, la
collisione blocca come sopra.**

Due casi veri, trovati nella review del Task 4:

- **`history` per `accaduto`** (poi corretto in `logbook`, «I nomi degli strumenti», sotto --
  corretto qui il 28/08 durante la review finale del ramo: l'esempio precedente, `gateway` per
  `porta`, citava un file cancellato, sotto). 50 occorrenze in `hiris/app`. Cade su **chiavi di
  dizionario e parametri di funzione** non-prosa usati per la cronologia dei messaggi di chat --
  `agent/prompts.py:365` (`build_chat_messages(system_prompt, history, ...)`),
  `agent/runner.py:1172` (`history = context.get("history")`), `api/handlers_chat.py:354`
  (`"history": sanitized_history`) -- un significato completamente diverso da «cosa e' successo in
  casa»: blocca.
- **`build` per `costruzione`** (poi corretto in `construction`): 44 occorrenze. Cade su
  **identificatori** — `app["build_stamp"]` (chiave di dizionario, `server.py:3502`) e
  `_compute_build_stamp` (nome di funzione, `server.py:3777`), piu' il file
  `static/build-check.js` — contesto non-prosa: blocca.
- **Per contrasto, il caso tollerato:** `construction` compare 3 volte in `hiris/`, e cade **solo**
  dentro frasi in linguaggio naturale — commenti come «dead by construction», «at store
  construction», «numeric by construction» — mai come identificatore, chiave o nome di file:
  tollera.

**Corretto durante la review finale del ramo: l'esempio con cui questa regola viene INSEGNATA era
falso, e non e' un refuso -- e' l'esempio da cui i lotti futuri imparano la regola, quindi l'errore
si sarebbe propagato.** L'esempio citava `gateway` per `porta`: *«Cade su un nome di file
(`api/handlers_gateway_policy.py`) e su un segmento di rotta (`/api/gateway/policy`,
`server.py:3598`)»*. **Verificato: `api/handlers_gateway_policy.py` non esiste piu'** — cancellato
per intero nella fetta E3 Task 7, e sopravvive solo dentro commenti che ne annunciano la
cancellazione (`server.py:1749,2897,2994,3598-3604`, tutti in prosa). `server.py:3598` non e' una
rotta viva, e' una riga di commento. Applicando la regola COSI' COME SCRITTA sopra — non-prosa
contro prosa — ogni occorrenza rimasta di `gateway` in `hiris/app` cade oggi in prosa (commenti, un
docstring): la regola vera **tollera** `gateway`, non lo blocca. Il paragrafo chiudeva con *«Un
grep piu' un'occhiata a dove cade ogni riga trovata: non serve altro»* — l'occhiata, per questo
esempio, non era mai stata rifatta dopo che il codice era cambiato. Sostituito con `history`
(sopra), un caso verificato di persona su questo stesso codice, oggi.

## Parole scartate durante l'estrazione

Una regola esclusa non e' silenzio, e' una decisione scritta. Lo script di estrazione (Step 1 del
piano) ha fatto uscire tre parole che **non richiedono nessuna decisione di rinomina**, perche' sono
gia' nella lingua di destinazione o sono una sigla, e sono state tolte a mano dall'elenco:

| parola uscita dallo script | perche' e' stata scartata |
|---|---|
| `backend` | e' gia' inglese -- corretto durante la review finale del ramo, la ragione precedente citava un file che non esiste (nessun file si chiama `backend*.py`, solo la cartella `backends/`): il singolare vive come identificatore vero, per esempio `nome_backend` (`api/handlers_chat.py:302,303,305`), oltre che in prosa ovunque nel sottosistema |
| `sanitize` | e' gia' inglese, usata cosi' com'e' nel codice |
| `yaml` | e' una sigla di formato, non si traduce |

**`dispatcher` NON e' in questa lista, e va scritto perche' fa eccezione -- corretto durante la
review finale del ramo, che ha trovato una riga completa in «I concetti» per una parola gia'
inglese, lo stesso criterio con cui `backend`/`sanitize`/`yaml` sono stati tolti sopra, applicato
al contrario.** La differenza: `backend`, `sanitize` e `yaml` sono parole di dizionario, prive di
un significato che HIRIS abbia inventato — non c'e' niente da spiegare oltre al loro senso
ordinario. `dispatcher` invece porta un **contratto comportamentale specifico di HIRIS**, non
ovvio dal nome da solo: la riga in «I concetti» (sotto) descrive che `DispatcherStrumenti` non
solleva MAI, e trasforma un nome sconosciuto, argomenti mancanti o un guasto imprevisto in un
dizionario leggibile invece che in un'eccezione che interrompe il turno — un impegno che il
progetto rispetta ovunque, non deducibile dalla sola parola inglese. E' la stessa ragione per cui
`archivio` ha una riga (→ `store`, gia' un inglese comune) pur non inventando la parola: il
glossario cataloga il **contratto**, non solo il vocabolario che manca.

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
| cambi | la tabella che tiene per 22 giorni le singole registrazioni descritte alla voce `grezzo` -- non un concetto a se', ma la sua forma persistita: la finestra di 22 giorni e' cio' che permette di rifare un giudizio sbagliato senza aver perso il materiale di partenza | reading | ~ parziale |
| caricatore | la sottoclasse del parser YAML che tollera i tag propri di Home Assistant (`!secret`, `!include`, `!input`) trasformando ognuno in un segnaposto leggibile invece di sollevare un'eccezione, restando pero' un parser sicuro che rifiuta i tag pericolosi del linguaggio stesso | loader | ~ parziale |
| casa | la rappresentazione strutturata a quattro livelli (piano, area, dispositivo, entita') degli spazi fisici su cui HIRIS ragiona, costruita a partire dai registri di Home Assistant | home_space | ~ parziale |
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
| famiglia | raggruppa il fallimento di un provider del modello in una delle cinque cause riconosciute -- credenziale, modello, irraggiungibile, scaduto, altro -- cosi' che due rifiuti della stessa causa vengano trattati come lo stesso evento invece che come due guasti diversi | family | ~ parziale |
| flusso | la sequenza di righe NDJSON che il processo del CLI del modello scrive in uscita mentre lavora, letta una volta sola e ridotta a un esito unico -- riuscito, troncato, senza risultato -- mai riletta una seconda volta con una logica diversa | stream | ✓ arriva |
| forme | il modulo puro che, a partire dai parametri portati dal modello, compone la struttura pronta da scrivere per ciascun tipo di oggetto -- automazione, script, scena -- generando anche un identificatore che in questa casa non esiste ancora | composer | ✓ arriva |
| forza | quale delle quattro nature chiuse porta una lettura ricordata -- preferenza, divieto, fatto o regola -- mai un numero su una scala libera | modality | ~ parziale |
| fuso | l'informazione con cui si interpreta correttamente ogni istante letto o scritto nella casa -- senza di essa "le 8" o "ieri" non hanno un significato univoco -- letta dallo stesso campo che Home Assistant espone per la propria installazione | timezone | ✓ arriva |
| gamba | una delle sei dimensioni lungo cui l'osservatore guarda la casa: chi c'e', comfort, dispersione, energia, buono stato, sicurezza | aspect | ✓ arriva |
| genere | classifica a quale dei sei ambiti appartiene un fatto compiuto della casa -- funzionamento, presenza, energia, guasto, sicurezza, bilancio -- e insieme all'obiettivo che sceglie quali entita' guardare decide che forma prendera' il fatto quando viene scritto | genre | ~ parziale |
| gesto | il verbo con cui una proposta di costruzione viene toccata -- crearla, modificarla, cancellarla -- usato anche per scegliere la forma grammaticale del testo che la descrive all'utente | operation | ~ parziale |
| grezzo | un cambiamento di stato registrato esattamente come Home Assistant lo riporta, con le classi che lo accompagnano, prima che qualunque giudizio lo trasformi in un fatto interpretato | reading | ~ parziale |
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
| orologio | il battito che, ricevuto un istante dall'esterno, scorre le promesse scadute e porta ciascuna a termine senza mai fermarsi per il guasto di una singola, cosi' che le altre dello stesso giro vengano comunque servite -- **corretto in fix round 1:** `clock` era stato dichiarato pulito per errore (il report diceva "una sola occorrenza, in prosa"; sono due, e la seconda -- `request.app.get("_clock")` in `api/handlers_reasoning.py:12` -- e' una chiave di dizionario, contesto non-prosa che la regola meccanica blocca. Non ho fatto eccezione: e' lo stesso standard gia' applicato a `turn`/`wake` in questo stesso lotto, bloccati per identificatori altrettanto estranei al sottosistema che stavo nominando. Nuovo inglese: `heartbeat`, pulito (`hiris/` ne ha una sola occorrenza, dentro un commento non correlato su un keep-alive SSE, tollerata) | sweeper | arbitrato del proprietario |
| osservatore | il modulo che si aggancia al flusso dei cambiamenti di stato e li annota cosi' come sono, applicando solo il filtro fisso dei confini, senza interpretare nulla | watcher | ✓ arriva |
| osservazioni | il deposito unico dove finiscono sia i cambiamenti annotati cosi' come sono sia i fatti compiuti che se ne ricavano, la fonte a cui un domani attingera' chi analizza | observations | ✓ arriva |
| pavimento | l'insieme fisso di classi che entra comunque, qualunque cosa dica l'obiettivo del momento: quest'ultimo puo' solo allargarlo, mai restringerlo sotto quella soglia | baseline | ~ parziale |
| piano (abbonamento) | il canale a forfait alimentato dall'abbonamento Claude Max, riconosciuto dalla sola presenza di una credenziale dedicata -- mai dal suo valore, cosi' che nessun chiamante possa stamparla per sbaglio in un log | subscription | ✓ arriva |
| piano (casa) | il livello piu' alto della gerarchia della casa, letto dal registro che Home Assistant stesso tiene per i livelli verticali di un edificio, sopra le aree e i dispositivi | floor | ~ parziale |
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
| servizi | un'operazione che un dominio di Home Assistant dichiara di saper eseguire, identificata da un nome e dai propri parametri -- non un catalogo scritto da HIRIS, ma cio' che l'installazione stessa dichiara di poter fare | services | ~ parziale |
| spazio | l'etichetta che distingue, dentro una cache **puramente in memoria di processo** (nessuna tabella, nessun SQL -- `CacheIndice` muore col riavvio), a quale chiamante appartiene una voce, cosi' che due strumenti sulla stessa casa non si sovrascrivano il risultato a vicenda -- **nota corretta in fix round 1:** non e' una colonna persistita (il brief originale lo affermava per errore, propagato dalla spec); e' una chiave di dizionario in `memoria/cache_indice.py:27,65,175,179` (`self._voci[spazio] = ...`), con valori che sono nomi di strumento (`"cerca"`, `"ricorda"`). Chi rinomina non trovera' nessuna tabella da migrare per questo -- solo il parametro e le due stringhe | slot | ~ parziale |
| specchio | la proiezione, calcolata una volta sola per ogni chiamante a partire dalle righe della cache di stato, in sei dizionari pronti all'uso -- valore corrente, nome, unita', classe, istante dell'ultimo cambiamento, attributi -- tenuta distinta da cio' che i quattro registri di Home Assistant dichiarano in modo statico, cosi' che le due fonti possano essere confrontate quando non coincidono | mirror | ✓ arriva |
| specie | classifica se un impegno per il futuro e' un fare qualcosa o un chiedere qualcosa da riferire -- le due sole forme ammesse, ciascuna gia' scritta come un verbo all'imperativo, con un valore fuori da queste due rifiutato subito | verb | ~ parziale |
| stati | un insieme chiuso di valori specifici che condividono una proprieta' -- quali contano come conclusi e quali come ancora in sospeso per un impegno o una proposta di costruzione, quali come attivi per un'entita', quali come guasti o transitori per un'integrazione -- usato per verificare se un valore singolo vi appartiene, mai un valore da solo | states | ~ parziale |
| strumenti | l'insieme dei nomi che il modello puo' invocare durante un turno, ciascuno con la propria definizione di argomenti, dichiarato in un unico catalogo che sia il canale sincrono sia quello del ponte leggono senza tenerne una copia propria | tools | ~ parziale |
| tempo | il modulo che decide, per una domanda su un periodo passato, quale superficie viva di Home Assistant interrogare e con quale grana, e compone come dire cio' che si e' letto -- senza conservare nulla in proprio | historian | arbitrato del proprietario |
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

> **`cambi` e `grezzo` sono un solo concetto, non due: stesso inglese per entrambi, e non e' un
> doppione.** Aggiunta in fix round 1 (rilievo del coordinatore): `cervello/archivio.py:74`
> (`CREATE TABLE IF NOT EXISTS cambi`) e' esattamente cio' che la riga `grezzo` descrive -- *«un
> cambiamento di stato registrato esattamente come Home Assistant lo riporta ... prima che
> qualunque giudizio lo trasformi in un fatto interpretato»*. **Prova migliore, trovata dalla
> review finale, sostituita a quella precedente:** il codice stesso usa le due parole attaccate,
> `cervello/archivio.py:3`, *«I **cambi grezzi** vivono 22 giorni»* -- dimostra la fusione meglio
> di una citazione di schema, perche' non e' un'inferenza di chi scrive il glossario, e' il
> sottosistema che chiama la sua stessa tabella cosi'. Dare un secondo inglese a `cambi` (per
> esempio applicando alla cieca `cambio → change`, parola ordinaria gia' in tabella) produrrebbe
> `changes`, un secondo nome per una cosa che il codice chiama gia' con la stessa coppia di parole
> italiane -- la stessa incoerenza che questa fetta esiste per chiudere, ricreata al contrario.
>
> **Corretto durante la review finale del ramo: l'inglese era `raw`, e collideva -- la collisione
> non era mai stata cercata.** `raw` e' gia' un identificatore vivo in `hiris/app` per un concetto
> **diverso**, "il valore non ancora decodificato di un input": `raw = getattr(runner,
> "last_tool_calls", None)` (`api/handlers_chat.py:1045`), `def _clean_provider_models(raw)`
> (`api/handlers_models.py:37`), `def _pulisci_ponte(raw)` (`api/handlers_models.py:139`), piu'
> occorrenze non-prosa in `env_util.py`, `impostazioni_chat.py`, `claude_runner.py` -- **circa 24
> righe non-prosa su 6 file**. Per la regola meccanica del documento (sopra, «Il controllo di
> collisione...») questo blocca **esattamente come ha bloccato `build`** (44 occorrenze, scartato
> per `costruzione`) e **come ha fatto cambiare `clock`** (una sola chiave di dizionario,
> `request.app.get("_clock")`, nessuna eccezione concessa nonostante fosse un solo match). Non ho
> scritto un'eccezione per `raw`: sarebbe stato lo stesso difetto che questa nota gia' cita come
> esempio da non ripetere, applicato al contrario -- due pesi per la stessa regola, uno strumento
> con 44 occorrenze e uno con una sola bloccati, uno con ~24 no, senza un motivo di confine a
> giustificarlo (a differenza di `target` o `related`: nessun sistema esterno chiama "raw" questo
> preciso concetto).
>
> **Primo candidato, `sample`, bocciato dalla prova -- e la lezione vale oltre questa riga:
> correggere un difetto non garantisce di non introdurne un altro.** `sample` era stato dichiarato
> pulito sulla collisione ("zero occorrenze in `hiris/`, zero nel glossario"), ma non era mai
> stato **provato** come tutti gli altri candidati di questo documento, ed e' stato marcato
> onestamente `~ non ri-provato` invece di `✓`. **Corretto durante la re-review mirata: la
> dichiarazione "zero occorrenze" era falsa.** Ce ne sono **tre**, tutte in log:
> `backends/openai_compat_runner.py:780,860,1080`, tutte `"Sample: %r"`. Il grep di verifica era
> **case-sensitive** e ha cercato solo la forma minuscola, non anche quella con la maiuscola, quindi
> le ha mancate. **La conclusione regge lo stesso** (sono stringhe di formato dentro un log, prosa
> pura -- non un identificatore, una chiave o un nome di file: la regola non blocca), ma la frase
> era imprecisa e va corretta, non solo la conclusione. **La trappola da scrivere, perche' e' la
> terza volta che questa fetta la incontra:** il controllo di collisione va fatto
> **case-insensitive**. `Sample`, `RAW`, `View` sono lo stesso nome per un lettore umano (e per il
> modello che sceglie uno strumento dal suo nome) quanto `sample`, `raw`, `view` — un grep
> case-sensitive puo' dichiarare pulito un candidato che in realta' collide, semplicemente perche'
> la maiuscola iniziale di un log o di un nome di classe lo nasconde a un pattern che cerca solo la forma minuscola.
> Ri-provato dal coordinatore, due lettori indipendenti, nome nudo: entrambi lontani. A: *«un esempio, un campione, un pezzo rappresentativo... insomma una
> dimostrazione di come funziona il resto»*. B: *«un campione: un piccolo sottoinsieme di dati
> estratto da un insieme piu' grande, usato per test, anteprima o rappresentazione statistica»*. La
> riga dice *«un cambiamento di stato registrato esattamente come HA lo riporta, prima che
> qualunque giudizio lo trasformi in un fatto interpretato»* -- niente a che vedere con
> un'anteprima, una demo o un sottoinsieme a scopo statistico. **`✗ non arriva`, e aggravato**: in
> software `sample` significa convenzionalmente *esempio/demo* (sample app, sample data) -- il
> nome non e' muto, **svia** verso un senso concreto e sbagliato. Risolvere la collisione di `raw`
> aveva solo spostato il problema da "collide" a "non dice niente, anzi dice la cosa sbagliata": un
> nome scelto per uscire da una collisione resta un candidato come tutti gli altri, e va provato
> come tutti gli altri, non solo controllato sul codice.
>
> **Secondo candidato, `readout`, bocciato.** A: *«il risultato visibile o esportato di una
> lettura... cio' che il software legge e restituisce all'utente»*. B, piu' netto: *«un riepilogo o
> resoconto... un rapporto sintetico presentato a fine processo, piuttosto che un dato grezzo
> continuo»* -- il lettore esclude esplicitamente proprio il senso che serve: un dato grezzo
> continuo e' esattamente cio' che questa riga e' comunque, e `readout` lo dice, comunque, per
> escluderlo.
>
> **Terzo candidato, `reading`, confermato -- i due lettori convergono su tre punti che contano.**
> A: *«un valore o una misura catturata da una fonte (sensore, database, configurazione) in un
> determinato momento»*. B: *«una singola lettura/misurazione acquisita in un dato istante -- il
> valore letto da un sensore, uno strumento o una fonte esterna (es. temperatura, consumo,
> timestamp incluso), spesso come elemento di una serie storica»*. Combacia su: valore singolo
> preso da una fonte; in un istante preciso; come elemento di una serie -- letteralmente la
> finestra di 22 giorni di `cambi`. B nomina "temperatura" e "consumo", cio' che l'osservatore
> registra davvero. Controllo di collisione a tre passi: `reading` ha **zero occorrenze non-prosa**
> in `hiris/app` (`.py` e `.js` — l'unica occorrenza e' un gerundio inglese in un commento,
> `claude_runner.py:575`, *«handlers_chat.py reading `runner.last_tool_calls`»*, prosa pura), zero
> nel glossario, non e' il nome ovvio di nessuna parola italiana ancora senza inglese (non ce ne
> sono, vedi A3). **Nuovo inglese: `reading`, per entrambe le righe** (stessa ragione di `sample`:
> non e' un secondo lemma, e' la stessa cosa con due nomi italiani).
>
> **Esito: `~ parziale`, non `✓` -- la tensione fra "cambiamento" e "misura" e' reale e non si
> chiude fingendo che non ci sia.** `grezzo` e' un **cambiamento** di stato: HA lo registra perche'
> qualcosa e' diventato diverso da prima (un evento, innescato da una transizione), non perche' un
> orologio ha chiesto "quanto vale adesso" a intervalli fissi. Entrambi i lettori descrivono invece
> una **misura/lettura catturata in un istante** -- un valore letto, non un cambiamento accertato:
> nessuno dei due nomina una transizione, un "prima" e un "dopo", o il fatto che la riga esiste
> SOLO quando qualcosa e' cambiato, non a ogni tick. E' esattamente il criterio scritto sopra per
> `~`: i lettori atterrano nella famiglia giusta (un dato puntuale, con istante, elemento di una
> serie storica di un sensore -- "temperatura", "consumo") ma sulla forma sbagliata (un valore
> campionato, non un evento di cambiamento). Non e' un `✓`: la natura evento-driven di `grezzo`, la
> ragione per cui questa riga e' un concetto a se' e non un sinonimo di "misura periodica", non e'
> arrivata a nessuno dei due lettori.
>
> **`reading` sta accanto a un `read` gia' assegnato -- stessa famiglia di rischio di
> `promise`/`promises` e `stati`/`states`, nota aggiunta durante la re-review mirata.** «Le parole
> ordinarie» da' gia' `read` sia a `leggi` sia a `letto` (sopra): `reading` e' la forma in *-ing*
> di quello stesso `read`, ma per un concetto diverso -- non "l'atto di leggere un file o un
> campo", il dato stesso, una misura di un sensore con il suo istante. Lo script di controllo
> duplicati (sotto, «Controlli di completezza») confronta token esatti e non lo vede: `reading` e
> `read` non sono la stessa stringa, quindi non compaiono insieme nel suo output, anche se dopo la
> rinomina degli identificatori si otterrebbero funzioni/variabili `read_*` (da `leggi`/`letto`) e
> una tabella o classe `Reading`/`reading` nello stesso sottosistema (`cervello/`) -- lo stesso
> tipo di vicinanza visiva e concettuale che ha fatto scartare `raw` (radice condivisa con
> "read" solo per assonanza, non e' questo il punto) e che rende `promise`/`promises` un rischio
> anche quando la radice e' voluta. Non e' un'istruzione a cambiare nome: `reading` resta, la nota
> serve a chi rinomina davvero il codice, perche' verifichi che un `read_qualcosa` (da `leggi`) e
> una `Reading` (da `grezzo`/`cambi`) nello stesso file o modulo restino leggibili come cose
> diverse, non due varianti della stessa radice lette distrattamente come sinonimi.


> **`ancora` era un OMONIMO fra due sottosistemi, oggi risolto -- fusa qui in una nota sola**
> (la review finale ha trovato tre note in sequenza a raccontare la stessa vicenda in tre stadi --
> bozza, correzione, decisione -- la seconda stantia non appena la terza e' arrivata: un fatto ha
> una sola casa). `memoria/archivio.py` usa `ancora` per il legame, di tipo dichiarato, fra un
> ricordo e l'area/dispositivo/entita' a cui si riferisce (`CREATE TABLE ancore`, colonne `tipo`,
> `riferimento`, `nome_visto`). `consumi/archivio.py` usa lo stesso nome per una riga singleton
> completamente diversa (`CREATE TABLE ancora (id, da_ts, da_giorno)`): il punto di riferimento
> temporale da cui si contano i consumi correnti, con `ancora_saldo` (il saldo per provider/modello
> congelato in quell'istante, `sposta_ancora()`). Non sono la stessa cosa -- una lega un ricordo a
> un pezzo di casa, l'altra e' uno zero mobile per un contatore -- e per la fondamenta n.3
> servivano due inglesi diversi. **Deciso dal Task 6bis, ora in «I concetti»:** l'ancora della
> memoria e' `tether`, l'ancora dei consumi e' `anchor` -- non `baseline`, nonostante la vicinanza
> di significato segnalata come rischio da verificare (gia' presa da `pavimento`, «l'insieme fisso
> di classi che entra comunque»): il rischio e' stato evitato, `baseline` resta solo di `pavimento`.

> **`piano` era un secondo OMONIMO fra due sottosistemi, oggi risolto -- fusa qui in una nota sola
> per lo stesso motivo di `ancora` sopra.** Il codice lo usava per due cose senza relazione:
> 1. **il livello della casa** -- la gerarchia piani -> aree -> dispositivi -> entita' letta dal
>    `floor_registry` di Home Assistant (`casa/archivio.py:22`, tabella `piani`, colonna
>    `livello`; `casa/anagrafe.py`, che la assembla dai quattro registri grezzi);
> 2. **il Piano dell'abbonamento Claude** -- l'abbonamento a forfait che alimenta il ponte
>    (`decisione_modelli.py`: `VARIABILE_TOKEN_DEL_PIANO`, `piano_ha_il_token()`; anche
>    `instradamento.py:70-77`, `ponte.tetto_giornaliero` letto per "il piano").
>
> Per la fondamenta n.3 servivano due inglesi diversi. **Deciso dal Task 6bis, ora in «I
> concetti»:** il livello della casa e' `floor` -- il confine vince, e' il nome che lo stesso
> `floor_registry` di Home Assistant usa gia' (`casa/domande.py:98`, `"floor": "piano"`;
> `proxy/ha_client.py:1374`); il Piano dell'abbonamento e' `subscription` -- non una scelta nuova
> ma il nome che il codice usa gia' per lui: `_credenziali["subscription"]` e
> `NOMI["subscription"] = "Piano Claude Max"` in `decisione_modelli.py`,
> `_CONFIG_PROVIDER_IDS = ("subscription", ...)` in `api/handlers_models.py`.

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
> restano tre), e' lo stesso concetto raccolto in insiemi con nome -- lo stesso schema gia' visto
> in «I valori di dominio», sotto, dove il singolare classifica (`genere`, `specie`, `famiglia`) e
> il plurale maiuscolo nomina l'insieme dei valori ammessi (`GENERI`, `SPECIE`, `FAMIGLIE`).
> **Corretto durante la review finale del ramo: questa nota citava `registri`/`registro` come
> esempio dello stesso fenomeno -- e' sbagliato, sono un OMONIMO fra due sottosistemi diversi, non
> lo stesso concetto a grana diversa (vedi la nota su `registri`/`interpreta`, sotto «Le parole
> ordinarie»); rimosso da qui, non era l'esempio giusto.**

> **`ripiego` e' anche un valore persistito, non solo un concetto -- fuori dallo scopo di questo
> task, segnalato per chi verra' dopo.** **Citazione corretta durante la review finale del ramo:
> `reasoning/queue.py:161` e' un commento** (*«Lo stato nuovo si chiama 'ripiego'...»*), non la
> SQL vera -- che e' a `reasoning/queue.py:200` (`"UPDATE reasoning_jobs SET status='ripiego', ...`).
> La sostanza restava vera, il puntatore no. `status='ripiego'` e' il quinto stato letterale della
> coda (accanto a `pending`/`claimed`/`decided`/`expired`/`failed`), non attraverso una costante
> nominata come `GENERI` o `SPECIE`: e' una stringa scritta a mano nell'SQL.
> Questo task decide la parola-concetto (`ripiego` → `downgrade`) come tutte le altre 25
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
> ha risolti 2 (un nuovo inglese ciascuno) e ne ha lasciati 3 bocciati due volte su due, andati
> all'arbitrato del proprietario (`casa`, `orologio`, `tempo`).
>
> **Il conteggio "finale" scritto qui era stantio -- corretto durante la review finale del ramo,
> perche' anteriore a due ricalibrature che il documento stesso racconta pochi paragrafi sotto
> (Task 8bis e Task 9), non solo al secondo giro appena citato.** Il numero giusto **oggi** si
> ricava rieseguendo lo stesso conteggio sulla tabella corrente, non fidandosi di una cifra scritta
> in un giorno che non c'e' piu':
>
> ```bash
> python - <<'PY'
> import pathlib
> from collections import Counter
> t = pathlib.Path('docs/GLOSSARIO.md').read_text(encoding='utf-8').split(chr(10))
> sez, c = None, Counter()
> for r in t:
>     if r.startswith('## '): sez = r[3:].strip(); continue
>     if sez == 'I concetti' and r.startswith('| '):
>         cols = [x.strip() for x in r.strip('|').split('|')]
>         if cols[0] == 'italiano' or set(cols[0]) <= set('- '): continue
>         esito = cols[3]
>         if 'arbitrato' in esito: chiave = 'arbitrato'
>         elif esito.startswith('~'): chiave = 'tilde'
>         else: chiave = 'check'
>         c[chiave] += 1
> print(dict(c), sum(c.values()))
> PY
> ```
>
> (Nota per chi lo rilancia su un terminale Windows in code page non-UTF8: se il glifo `✓` nel
> file dovesse mai far fallire la stampa con `UnicodeEncodeError`, e' un limite del terminale, non
> dello script -- rilancia con `PYTHONIOENCODING=utf-8` davanti al comando.)
>
> **Eseguito oggi: 39 `✓`, 39 `~`, 2 arbitrato (senza misura, `orologio`/`tempo`) su 80 righe.**
>
> **Corretto durante la re-review mirata: la riconciliazione precedente non tornava a conti fatti,
> e una sua frase era falsa.** L'aritmetica giusta, verificata sui commit veri (`git show
> <hash>:docs/GLOSSARIO.md`, non a memoria):
>
> - **`a5735c1` = 42 `✓` / 35 `~` / 3 arbitrato.** Il "conteggio finale" del primo giro, sopra.
> - **`fc1adfd` = 42 `✓` / 36 `~` / 2 arbitrato.** Quattro righe si sono mosse fra i due commit, non
>   una sola: `famiglia` (`✓`→`~`), `servizi` (`✓`→`~`), `forme` (`~`→`✓`, `shapes` sostituito da
>   `composer`), `casa` (arbitrato→`✓` **direttamente**, non passando da `~` -- il Task 9 l'ha
>   decisa e misurata subito a `✓`, prima che il rilievo B1 la correggesse). Netto: `✓` invariato
>   (42, due escono e due entrano), `~` +1 (35→36), arbitrato -1 (3→2, `casa` decisa) — torna.
> - **Oggi = 39 `✓` / 39 `~` / 2 arbitrato.** Da `fc1adfd`, altre tre righe scendono da `✓` a `~`,
>   nessuna in altra direzione: `casa` (`✓`→`~`, rilievo B1 -- il criterio per un lettore che
>   nomina prima la homepage e' `~`, non `✓`), `grezzo` e `cambi` (`✓`→`~`, rilievo A2 -- la
>   collisione di `raw` ha imposto un cambio di candidato, prima `sample` poi `reading`, e il
>   nuovo esito misurato e' `~`, non `✓`). Netto: `✓` -3 (42→39), `~` +3 (36→39), arbitrato
>   invariato — torna.
>
> **Una frase della riconciliazione precedente era falsa, e non per un typo:** diceva *«nessuna
> delle due cifre precedenti (42/35/3 ne' 41/37/2) era falsa quando scritta: erano entrambe esatte
> al proprio commit»*. **`41/37/2` non e' mai stato lo stato di nessun commit.** Era una proiezione
> aritmetica scritta in un brief del coordinatore (il calcolo di "cosa dovrebbe dare B1 da solo"),
> presa per un fatto storico invece che per l'ipotesi che era. Corretto qui: le uniche due cifre
> che sono davvero esistite come stato di un commit sono `42/35/3` (`a5735c1`) e `42/36/2`
> (`fc1adfd`), sopra -- entrambe verificate ora, non solo scritte a un certo punto e mai piu'
> ricontrollate.
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
> **Perche' `outcome`, citato qui sopra come il piu' ovvio, non e' mai stato provato come
> candidato -- decisione mancante, scritta durante la review finale del ramo.** `outcome` e' gia'
> un identificatore vivo in `hiris/app`, non-prosa: variabile locale in `agent/runner.py:1645,
> 1647-1648,1669-1671` (`outcome = ...`, confrontato con `"idle"`) e in
> `api/handlers_reasoning.py:34,60,65` (`outcome = "recorded"`, `"promessa_sconosciuta"`,
> `"promessa_gia_conclusa"`) -- in entrambi i casi una classificazione locale del risultato di UNA
> chiamata o iterazione specifica, non il concetto generale che `esito` descrive (*«il fatto
> osservabile su cio' che e' davvero successo in un tentativo... mai un'ipotesi sul perche'»*).
> Vicino ma non lo stesso: usarlo per `esito` avrebbe messo lo stesso inglese su un concetto
> generale del glossario e su una variabile locale che gia' significa qualcosa di piu' stretto in
> due punti del codice — la stessa classe di rischio per cui `raw` e' stato scartato sopra, solo
> con un peso minore (2 file, non 6). Non blocca con la stessa forza di `raw`/`history`, ma basta a
> spiegare perche' il secondo giro sia partito da `occurrence` invece che dalla parola piu' ovvia.
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
> Dettaglio completo del dispaccio e delle due letture indipendenti in
> `.superpowers/sdd/2026-08-28-il-glossario/task-7-risposte.md` e `task-7-report.md` (non
> tracciati, cartella di processo).

> **Task 9 -- il proprietario ha arbitrato le tre parole.** `casa` -> **`home_space`**,
> `orologio` -> **`sweeper`**, `tempo` -> **`historian`**. Le tre proposte vengono dal proprietario,
> non da un terzo giro dell'implementer (vietato dal limite "massimo due giri per parola" appena
> sopra): sono un arbitrato, non una misura. Cio' non le esenta dal controllo di collisione a tre
> passi, che e' stato rifatto su tutte e tre (glossario, `grep -rn` su `hiris/app`, parole ancora
> indecise): **zero occorrenze in `hiris/` per `home_space`, `sweeper` e `historian`**, nessuna
> riga del glossario le usa gia', nessuna e' il nome ovvio di una parola italiana ancora senza
> inglese.
>
> - **`home_space`** e' stato comunque **misurato**, non solo arbitrato: due lettori indipendenti,
>   nudo, come per ogni altra riga. Lettore A: *«gestisce gli spazi o le zone fisiche della casa
>   (stanze, ambienti, aree)»* -- centro pieno. Lettore B: *«un componente che rappresenta lo
>   spazio di un'abitazione... il concetto di ambiente domestico (una casa, con le sue
>   stanze/dispositivi) in un sistema di domotica»* -- nomina prima la homepage, poi atterra sul
>   concetto giusto.
>
>   **Corretto durante la review finale del ramo: l'esito era stato scritto `✓ arriva` prendendo la
>   lettura migliore (A), quando il criterio del documento stesso dice `~` quando "il lettore
>   atterra nella famiglia giusta ma sulla forma sbagliata" -- ed e' esattamente cio' che fa B.**
>   Per `house` (sopra, bocciato) la divergenza fra due lettori era stata di per se' l'esito
>   (*«due letture cosi' distanti sullo stesso nome sono gia' un esito»*); qui la stessa divergenza
>   era stata invece risolta scegliendo la lettura migliore, e succedeva sull'unica riga il cui
>   candidato viene dal proprietario. Non era un arbitrato spacciato per misura -- peggio: era una
>   prova che, solo su quella riga, non poteva fallire. **Il metro non cambia in base a chi propone
>   il nome.** Esito corretto: **`~ parziale`** (A pieno, B parziale -- nomina prima la homepage).
>   Il **nome resta**: `home_space` **cura comunque il difetto di `home`** (letto SOLO come
>   homepage, bocciato al primo giro) **senza cadere in quello di `house`** (che a un lettore non
>   diceva niente) -- la coppia `home`+`space` porta entrambi i lettori sul concetto a quattro
>   livelli (piano, area, dispositivo, entita') invece che su un contenitore generico o una pagina
>   web, e resta la lettura migliore misurata su questa riga finora. **Fatto onesto da scrivere:**
>   il candidato del proprietario ha misurato meglio dei candidati che questa fetta aveva gia'
>   tentato e bocciato per questa stessa riga (`home`, `house`, sopra) -- due giri, due bocciature,
>   e la proposta arbitrata supera entrambe, anche con l'esito corretto a `~`.
> - **`sweeper`** non e' stato ri-provato (istruzione esplicita: e' un arbitrato, non una misura, e
>   va segnato come tale in colonna prova -- `arbitrato del proprietario`, non `✓ arriva`).
>   Ragionamento del proprietario, registrato qui: `heartbeat` e `pulse` erano stati bocciati
>   entrambi per la stessa lettura -- un segnale di liveness/salute, passivo -- mentre `orologio`
>   **lavora**: scorre le promesse scadute e le porta a termine una per una, senza fermarsi per il
>   guasto di una singola. `sweeper` nomina l'azione (ripulire cio' che e' scaduto) che ne'
>   `heartbeat` ne' `pulse` nominavano, entrambi fermi al segnale che precede l'azione.
> - **`historian`** stessa cura: non ri-provato, segnato `arbitrato del proprietario`. `span` e
>   `timeframe` erano stati bocciati entrambi per la stessa lettura -- un valore passivo (un
>   intervallo, una finestra) -- mentre `tempo` e' un **modulo che decide**: quale superficie di
>   Home Assistant interrogare, con quale grana, e come dire cio' che ha letto. `historian` e' un
>   nome di mestiere (chi fa qualcosa con la storia), non di misura (un pezzo di storia): cura lo
>   stesso difetto comune ai due bocciati. Non collide con `history` (gia' bloccato altrove in
>   questo documento, sopra, per la cronologia dei messaggi di chat): sono due token diversi,
>   nessun grep su `history` puo' far scattare per errore su `historian` o viceversa.

> **Ricalibratura del confronto (Task 7): il primo criterio di misura convergeva a zero, ed e'
> stato sostituito.** Una prima verifica indipendente aveva confrontato ogni risposta con
> "varrebbe identica per qualunque altro software esistente?" -- un insieme infinito, contro cui
> nessun nome tecnico puo' differenziarsi: applicato fino in fondo, quel criterio non ammette
> **nessun** `✓` (`watcher` e' la definizione da manuale dell'Observer, `parse` e' la definizione
> di parsing, `revisions` e' git -- eppure erano risposte corrette). Due passate con quel criterio
> avevano declassato 32 righe da `✓` a `~` (e una, `forme`, da `~` a `✗`); una review indipendente
> ha giudicato che la seconda passata aveva sovracorretto, e le 32 righe sono state riesaminate da
> capo con un criterio diverso.
>
> **Il criterio corretto confronta ogni risposta con le altre 79 righe di QUESTO glossario, non
> con l'universo del software:**
>
> - **`✗` non arriva** -- il lettore atterra su un'altra cosa o su niente: nomina un dominio o un
>   meccanismo che la riga non e' (`home`->homepage, `directory`->cartella, `heartbeat`->ping di
>   liveness), dice "non mi dice niente", o due lettori indipendenti divergono senza condividere
>   il senso corretto.
> - **`~` parziale** -- il lettore atterra nella famiglia giusta ma sulla forma sbagliata (nomina
>   l'input al posto del processore, il dato al posto del modulo, un numero al posto di un
>   insieme), oppure la stessa risposta descriverebbe altrettanto bene un'ALTRA riga di questa
>   stessa tabella.
> - **`✓` arriva** -- la risposta, sovrapposta alla riga, nomina la stessa cosa con parole diverse.
>   **Gli invarianti non bloccano il `✓`**: ogni *sempre/mai/solo/unico*, ogni elenco di campi,
>   ogni scelta di persistenza o caching, ogni percorso di file sono dettagli d'implementazione --
>   vanno nel docstring quando si scrivera' il codice, non nel nome.
>
> **La prova che il criterio nuovo discrimina davvero, non solo che e' piu' permissivo:** il
> gruppo `store`/`registry`/`journal`/`revisions` era stato co-lottizzato apposta per vedere se
> collassavano sulla stessa risposta -- e il lettore li ha separati tutti e quattro, ciascuno con
> un pattern specifico e diverso (archivio persistente generico / mappa chiave-valore / log di
> audit / cronologia con ripristino). Quell'esperimento e' la misura vera di questo gruppo: le due
> passate precedenti lo avevano ignorato, declassando `store` (e in un giro `journal`) sulla sola
> base del confronto con "qualunque altro software".
>
> **Riapplicato il criterio a tutte e 32 le righe declassate (nessun'altra riga toccata): 30
> tornano `✓`, 2 restano `~` per una ragione specifica e diversa dalla precedente:**
>
> - **`famiglia` (family)** -- *"una collezione o categoria di entita' che condividono proprieta'
>   comuni"* descriverebbe altrettanto bene la riga `stati` (*"un insieme chiuso di valori che
>   condividono una proprieta'... usato per verificare l'appartenenza"*): stessa forma testuale,
>   due righe diverse. Non e' un'invenzione di questa nota: il glossario stesso avverte, nella nota
>   su `genere`/`specie`/`famiglia` sotto la tabella, che questi tre nomi rischiano proprio questo.
> - **`servizi` (services)** -- *"interfaccia o raccolta di operazioni disponibili che il sistema
>   mette a disposizione"* nomina il CONTENITORE (il catalogo), non il singolo elemento che la riga
>   descrive (*"un'operazione che un dominio... dichiara di saper eseguire"*) -- la stessa
>   confusione grana-diversa gia' documentata per la coppia `registro`/`servizi` nella nota sotto
>   la tabella, ma qui e' la RISPOSTA a cadere dal lato sbagliato della distinzione, non il nome.
>
> Nessuna delle 32 e' scesa a `✗`.
>
> **`forme`: `shapes` scartato dalla prova, sostituito da `composer` -- chiuso.** `shapes` e'
> caduto per un motivo indipendente dalla sovracorrezione, e l'argomento regge tal quale: non e'
> un caso di "manca un dettaglio" (il difetto delle 32 corrette sopra), e' che **entrambi** i
> lettori indipendenti, al primo giro e alla ri-prova, hanno incluso un senso "visivo/geometrico"
> (*"forme geometriche"*, *"qualcosa di visuale"*) per un modulo che compone corpi JSON di
> automazioni/script/scene e non genera nulla di visivo -- "atterra anche su un dominio che la
> riga non e'", la definizione stessa di `✗`. Secondo candidato -- gia' segnalato nel report del
> Task 4 come riserva pulita -- **`composer`**, provato in un lotto mescolato con altri sette nomi
> gia' testati e lontani, senza contesto: *"Una cosa che assembla, orchestra, mette insieme parti
> in un tutto coeso"* -- nessuna traccia del senso visivo/geometrico che aveva affossato `shapes`
> in entrambe le letture, ed e' esattamente cio' che `forme` fa (compone corpi pronti da scrivere
> per ciascun tipo di oggetto). `✓ arriva`. Chiuso in due giri, come da vincolo.
>
> **Due limiti della prova, perche' la prossima taratura non ricaschi negli stessi errori:**
>
> 1. **Il nome nudo sottostima ogni nome, in modo sistematico.** Chi incontra `vocabulary` nel
>    codice lo incontra come `consumi/vocabolario.py`; chi incontra `flag` lo incontra come
>    `migrazione/segno.py`. La prova toglie apposta il percorso -- cioe' toglie il dominio -- per
>    non regalare un indizio; ma questo significa che una riga puo' sembrare debole nella prova
>    per una ragione che sparisce nel momento in cui il nome vive nel file giusto. E' un limite
>    della prova, non un difetto automatico dei nomi.
> 2. **Il metro e' questo glossario, non l'universo del software.** Un nome tecnico il cui
>    significato standard coincide con la funzione della riga (`dispatcher`, `parse`, `resolver`)
>    non e' un fallimento della prova: e' esattamente il risultato che una buona scelta di nome
>    dovrebbe produrre. Il confronto giusto e' "si confonde con un'altra riga di questa tabella?",
>    non "esiste gia' altrove con questo significato?" -- la seconda domanda, applicata sul serio,
>    boccia ogni nome tecnico riuscito.
>
> **Cosa comporta ciascun esito -- l'azione che ne segue, perche' un `~` che non decide niente non
> e' una misura:**
>
> - **`✗`** -> si prepara un secondo candidato (se non ancora tentato) o si passa all'arbitrato del
>   proprietario (se gia' al secondo giro). Cosi' come per `casa`, `orologio`, `tempo`, `forme`.
> - **`~` per forma sbagliata o collisione con un'altra riga** (es. `famiglia`, `servizi`, sopra)
>   -> il nome resta quello scritto in tabella, ma la riga porta l'annotazione del rischio
>   specifico, cosi' che chi rinomina sappia perche' verificare due volte prima di usarlo alla
>   cieca.
> - **`~` per sola genericita' o dettagli mancanti** (la maggioranza delle righe `~` di questo
>   documento) -> nessuna azione: il nome va bene, descrive la riga giusta, semplicemente un
>   lettore nudo senza il codice davanti non recupera ogni sfumatura -- cosa vera per quasi
>   qualunque nome di una riga con una frase "che cosa fa" lunga.
> - **`✓`** -> nessuna azione, il nome regge senza riserve.

> **Dubbio residuo sul Lotto 7 (primo giro), chiuso con una misura: `watcher` + `observations` +
> `baseline` reggono anche lontane dal loro cluster.** Erano finite insieme nel lotto finale del
> primo giro, tutte e tre dal sottosistema `cervello` (`osservatore.py`, `osservazioni`,
> `pavimento.py`) e semanticamente affini (vocabolario di monitoraggio) -- il dubbio era che le tre
> risposte si fossero rinforzate a vicenda invece di reggere ciascuna sul proprio nome nudo.
> Ri-provate mescolate a 7 nomi gia' testati e lontani (`chain`, `vocabulary`, `memory`, `promise`,
> `target`, `shapes`, `settings` -- nessuno da `cervello`/`casa`): le tre risposte sono coerenti con
> quelle del primo giro (`watcher`: *"un osservatore che monitora cambiamenti e reagisce quando
> accadono"*; `observations`: *"dati raccolti o fatti registrati durante l'esecuzione del
> sistema"*; `baseline`: *"un valore di riferimento iniziale o di comparazione, per misurare
> scostamenti"*) -- nessun cambio di esito (`watcher` e `observations` restano `✓`, `baseline`
> resta `~`, coerente con la lettura gia' registrata: coglie "riferimento per confronto" ma non
> "soglia fissa che si allarga e mai si restringe"). Il dubbio e' chiuso da una misura, non da
> un'opinione. (E' in questo stesso lotto di ri-prova che e' emerso il reperto su `shapes`,
> discusso sopra.)

> **Quattro coppie che la frase «che cosa fa» non distingueva bene, segnalate dalla review finale
> del ramo: rilievo giusto, rimedio no.** Il revisore proponeva di declassare quattro `✓` a `~`
> (`costruzione`/`officina`, `casa`/`anagrafe`, `schedulatore`/`orologio`, `indice`/
> `riconoscitore`). Il metro `✓`/`~` e' gia' stato riscritto tre volte su queste stesse 80 righe
> (12 righe declassate, poi altre 20, poi 30 restituite, sopra: la ricalibratura del confronto e
> le due passate sul criterio nuovo) senza mai cambiare un solo nome inglese: una quarta
> ricalibratura ripeterebbe lo stesso errore invece di correggerlo. Cio' che il criterio chiede
> davvero — e che le altre coppie vicine hanno gia' avuto (`registro`/`servizi`, `memoria`/
> `ricordi`, `turno`/`ReasoningQueue`, `promessa`/`promesse`) — e' la **nota di distinzione**: una
> riga che dice cosa fa l'una che l'altra non fa. Scritta qui per tutte e quattro; se la frase
> distingue dopo la nota, l'esito `✓` regge e non si tocca:
>
> - **`costruzione` / `officina`**: `costruzione` e' il **sottosistema** — la capacita' generale
>   di comporre e scrivere nuova configurazione con un ciclo proposta/approvazione/scrittura e
>   annullamento; `officina` e' il **modulo concreto** che quella capacita' la implementa per
>   automazioni/script/scene, gemello di `azione`/`porta` per i servizi. Uno nomina il dominio,
>   l'altro nomina il file che lo fa succedere.
> - **`casa` / `anagrafe`**: `casa` e' la **struttura dati risultante** — la gerarchia a quattro
>   livelli su cui HIRIS ragiona; `anagrafe` e' il **modulo che la produce**, leggendo e
>   assemblando i quattro registri grezzi di Home Assistant. Uno e' il dato, l'altro e' il
>   processo che lo costruisce.
> - **`schedulatore` / `orologio`**: `schedulatore` e' il **sottosistema che tiene le promesse**
>   per l'intero ciclo di vita — le risveglia, ne porta a termine il compito, **registra come e'
>   andata**; `orologio` e' il **meccanismo di battito** che, ricevuto un tick esterno, scorre le
>   sole promesse scadute in QUEL giro e non si ferma se una fallisce, cosi' che le altre dello
>   stesso giro vengano comunque servite. Uno tiene lo stato e la memoria dell'esito, l'altro e' la
>   resilienza di un singolo passaggio.
> - **`indice` / `riconoscitore`**: `indice` e' la **struttura di lookup** — costruita una sola
>   volta, interrogata da altri chiamanti per trovare candidati o confermare un identificatore;
>   `riconoscitore` e' il **modulo che la costruisce e la usa** per un compito piu' specifico,
>   decidere a quale parte della casa si riferisce una FRASE scritta dal modello, restringendo le
>   proposte a cio' che esiste davvero. Uno e' il dato interrogabile, l'altro e' il processo che lo
>   fabbrica e lo applica a un testo libero.

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

> **`carica → load` e' sbagliato in un senso su due -- nota di scissione aggiunta durante la
> review finale del ramo, con lo stesso metodo gia' usato per `stato` e `riga`, sotto.** Il senso
> maggioritario e' generico e `load` e' corretto: `casa/lettura_yaml.py:49,59`
> (`def carica_yaml(...)`, `def carica_file(...)`) e `impostazioni_chat.py:280`
> (`ImpostazioniChat.carica()`, chiamato da `server.py:2085`) caricano un file o una
> configurazione, esattamente "load". Ma `carica`/`scarica` sono anche **due dei sette valori di
> `DIREZIONI_BILANCIO`** («I valori di dominio», in fondo): li' significano carica **di batteria**,
> non caricamento di un file -- `casa/anagrafe.py:469` (`"battery_charging": ("in carica", "non in
> carica")`) e `cervello/oggetti.py:439` (`attive_scarica`, `fine_scarica_batteria`). In quel
> contesto `load` mentirebbe: l'inglese giusto e' `charge`/`discharge`, non una forma di `load`.
> La tabella sopra fissa `load` come equivalente di default (il senso maggioritario); chi traduce
> i valori di `DIREZIONI_BILANCIO` deve usare `charge`/`discharge`, non applicare `load` alla
> cieca. **Aggravante da scrivere:** la caccia alla terza famiglia di errori (parole generiche con
> piu' di un senso, sotto) ha esaminato otto parole frequenti e concluso che nessuna mostrava la
> spaccatura di `stato` -- vero per quelle otto, ma la parola davvero spaccata (`carica`) non era
> fra le otto esaminate: era gia' elencata da questo stesso documento due sezioni piu' sotto, come
> valore di `DIREZIONI_BILANCIO`, un posto che quella caccia non ha guardato.

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

> **`stati` → `states`: nota di rischio, aggiunta durante la review finale del ramo -- secondo
> caso di confine preso con un significato diverso, questa volta senza cambiare il nome.** Home
> Assistant chiama gia' `/api/states` l'elenco degli stati vivi di tutte le entita', e il codice
> lo rispecchia: `api/handlers_entities.py:13` (`def filter_entities(states: list[dict], ...)`),
> `proxy/ha_client.py:332` (`f"{self._base_url}/api/states"`). La riga `stati` (sopra) e' una cosa
> diversa: *«un insieme chiuso di valori... usato per verificare se un valore singolo vi
> appartiene»* -- `STATI_SOSPESO`, `STATI_CONCLUSI` e simili, non l'elenco delle entita' vive.
> `state` per `stato` (nota sopra) resta corretto perche' li' i due sensi COINCIDONO (lo stato di
> un'entita' e' ancora "lo stato di qualcosa"); qui invece il plurale del confine (`states`, "gli
> stati vivi delle entita'") e il plurale del concetto (`states`, "l'insieme chiuso di valori
> ammessi") sono **due cose diverse che suonerebbero uguali**. Non ho cambiato il nome -- le due
> occorrenze del confine sono poche (un parametro, un URL) rispetto ai casi che questa review ha
> fatto cambiare (`raw`, sopra: ~24 righe su 6 file; `history`: 50 occorrenze), e `stati` vive quasi
> sempre in composizione (`STATI_SOSPESO`, `STATI_CONCLUSI`), mai da solo, il che riduce il rischio
> di uno scambio diretto. **Chi decidera' l'inglese delle costanti `STATI_SOSPESO`/`STATI_CONCLUSI`
> in «I valori di dominio» (sotto, oggi senza inglese -- vedi C7) deve verificare questo rischio
> prima di comporre `..._STATES` alla cieca**: se il contesto in cui la costante compare puo'
> confondersi con l'elenco vivo delle entita' di Home Assistant, la forma composta va preferita a
> `states` nudo, o va usato un suffisso diverso (`*_VALUES`, `*_SET`).

> **`spazio` → `slot`: un disallineamento apparente, verificato durante la review finale del ramo
> e non azionato -- decisione scritta, non un silenzio.** La frase «che cosa fa» descrive
> un'**etichetta che identifica il chiamante** (*«a quale chiamante appartiene una voce»*), che
> suonerebbe piu' vicina a "namespace" che a "slot" (una posizione). Verificato pero' cosa fa
> davvero il codice: `memoria/cache_indice.py:122` (`self._voci: dict[str, tuple[tuple, Indice]]
> = {}`) tiene **un dizionario con una voce per spazio**, e `spazio` e' la chiave con cui si scrive
> e si legge quella voce (`self._voci[spazio] = ...`). In questo senso `slot` non nomina "una
> posizione" in astratto: nomina **il comparto della cache identificato da quella chiave** -- lo
> stesso uso comune di "slot" in un dizionario/cache con chiave (una cache a `hash slot`, un
> comparto per chiave). Non ho rinominato: due alternative piu' letterali collidono col confine
> peggio del disallineamento che risolverebbero -- `namespace` e' generico ma `scope` e' gia' un
> parametro non-prosa di Home Assistant per un concetto diverso (`{"scope": ambito}` in
> `proxy/ha_client.py:1616,1644,1671`, l'ambito area/dispositivo/entita' del registro delle
> categorie/etichette) -- e sostituire un disallineamento lieve con una collisione di confine vera
> sarebbe un peggioramento, non una correzione. Resta `slot`, con questa nota a spiegare perche'
> regge nonostante la lettura letterale della frase.

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
>
> **Corretto durante la review finale del ramo: questa caccia era vera ma incompleta -- ha guardato
> solo dentro «Le parole ordinarie», non nelle altre tabelle del documento.** `carica` (nota sopra)
> ha la stessa spaccatura di `stato` -- un senso maggioritario e uno di dominio che lo smentisce --
> ma non era fra le otto parole riesaminate qui: viveva gia' come valore di `DIREZIONI_BILANCIO`,
> in «I valori di dominio», una tabella che questo metodo non ha guardato. La caccia era limitata
> al posto sbagliato, non alle parole sbagliate.

> **Due forme flesse vere, `vivi` e `direzioni` — non compaiono ne' qui ne' in «I concetti», di
> proposito.** L'estrazione allargata ha fatto uscire `vivi` (masch. plur. — `casa/domande.py:209,
> 437,464,543,603,764` `attributi_vivi`, `casa/strumenti.py:1158` `nomi_vivi`) e `direzioni`
> (plur. — `server.py:917`, `cervello/oggetti.py:570`, `proxy/ha_client.py:1482`
> `direzioni_energia`): la stessa radice, la stessa cosa, di due voci gia' in «I concetti» (`vive`,
> `direzione`). Non le ho aggiunte qui come ordinarie ne' come nuove voci in «I concetti»: dare un
> secondo inglese alla stessa radice violerebbe la fondamenta n.3 (stessa cosa, stessa forma) — ed
> e' esattamente il difetto che questa fetta esiste per chiudere. **Chi decidera' l'inglese di
> `vive` e `direzione` in «I concetti» deve usare lo stesso identico inglese anche per queste due
> forme flesse**, nei file e alle righe elencati sopra: non e' una seconda decisione, e' la stessa
> applicata a un'altra forma grammaticale.
>
> **`registri` e `interpreta` NON sono forme flesse: sono OMONIMI, tolti da questa nota durante
> la review finale del ramo dopo che una prima stesura li aveva fusi per errore con `registro` e
> `interpretazione` -- lo stesso fenomeno gia' trattato per `ancora` e `piano`, sopra.**
> `registri` (plur. — `casa/archivio.py:245` `sostituisci(self, registri: dict[...], ...)`,
> `proxy/ha_client.py:1618-1622` `leggi_registri()`, *«Tutti i registri della casa»*,
> `proxy/ha_client.py:1676-1680` `config/entity_registry/list`) sono **i quattro registri di
> Home Assistant** -- piani, aree, dispositivi, entita' -- esattamente cio' che la riga `anagrafe`
> (sopra, `topology`) descrive: *«il modulo che legge i quattro registri grezzi di Home Assistant
> ... e li assembla in un'unica gerarchia coerente»*. La riga `registro` (sotto, `registry`) e'
> invece un concetto diverso, `azione/registro.py`: *«lo specchio aggiornato di cosa Home Assistant
> sa fare in questa casa»*, il riflesso di `/api/services`. Applicare l'istruzione "stesso inglese
> della radice" a `registri` avrebbe prodotto **un solo inglese per due concetti diversi** -- il
> difetto che questa fetta esiste per chiudere, nel modo peggiore: `registry` e' anche la parola
> con cui Home Assistant stesso chiama i SUOI registri (`floor_registry`, `entity_registry`,
> `device_registry` — gia' citati sopra, nota su `piano (casa)`), quindi finirebbe naturalmente
> addosso al senso di `anagrafe`/`registri`, non a quello di `registro` che l'ha gia' presa: un
> conflitto di confine, non solo interno al glossario. **Chi decidera' l'inglese di `registri` deve
> scegliere guardando `anagrafe`, non `registro`, e verificare la collisione con `registry` prima
> di riusarla.**
> `interpreta` (verbo — `schedulatore/orologio.py:27` `Orologio.__init__(self, archivio, *,
> esegui, interpreta, ...)`, `schedulatore/turno.py:121` `async def interpreta_promessa(app,
> promessa)`) e' il callback che risveglia il modello per una promessa "chiedi" e ne interpreta la
> risposta -- un concetto del sottosistema `schedulatore`, non di `memoria`. La riga
> `interpretazione` (sotto, `interpretation`) e' invece `memoria/interpretazione.py`: *«il
> linguaggio chiuso a quattro caselle ... con cui il modello propone una lettura strutturata di
> una frase ricordata»*. Due funzioni diverse che condividono un verbo italiano generico
> ("interpretare"), non la stessa cosa vista da un'altra forma grammaticale: over-merge dello
> stesso tipo di `registri`, corretto per lo stesso motivo.

**La coda lunga (le parole usate una o due volte) non si decide riga per riga: si applica una
regola sola.** Al momento della rinomina si usa l'equivalente inglese piu' ovvio della parola
italiana, verificando solo che non collida con un nome inglese gia' assegnato altrove nello stesso
modulo — senza aprire una voce di glossario per ciascuna. Se durante la rinomina una di queste
parole si rivela un concetto travestito (la stessa identica domanda del Task 6: per spiegarla
serve raccontare come funziona HIRIS), si sposta fra i concetti anche se e' stata usata una sola
volta — la soglia dei 3 usi separa cio' che vale la pena estrarre in automatico da cio' che si
guarda a mano, non cio' che e' ordinario da cio' che e' un concetto.

## I nomi degli strumenti

**Non sono identificatori qualunque: sono la parte di codice che un modello linguistico legge per
decidere cosa chiamare.** Per questo il criterio qui e' piu' stretto che altrove: non basta che il
nome si capisca, deve anche **non confondersi con un altro dei tredici**. Il prodotto ha gia' due
coppie a rischio in italiano -- `cerca`/`richiama` e `ricorda`/`richiama` -- e il compito di questo
lotto e' non farle restare vicine in inglese.

**Lo standard che regge questa sezione, prima ancora del controllo di collisione sul codice: se un
lettore che non conosce il progetto confonde due strumenti, li confondera' anche il modello.** Il
modello sceglie lo strumento dal nome che vede nel catalogo -- e' esattamente la posizione del
lettore nuovo, senza contesto, senza descrizione del programma. Per questo la prova del lettore
nuovo non e' opzionale su questo lotto: e' la stessa identica misura richiesta per gli altri 80
concetti, applicata alla parte del glossario dove sbagliare costa di piu'.

**La prova e' stata eseguita** (`.superpowers/sdd/2026-08-28-il-glossario/task-8-risposte.md`): due
lettori indipendenti, su **modelli diversi**, lotto unico dei tredici nomi (corretto tenerli
insieme: un modello li vede sempre tutti nello stesso catalogo, separarli avrebbe falsato la prova
al ribasso), nessun contesto di dominio, `tool_uses: 0` per entrambi. Sulla prima domanda («cosa fa
ciascuno») le due letture sono quasi sovrapponibili e i nomi reggono. E' la seconda domanda («quali
confonderesti») ad aver prodotto il reperto che segue.

**Corretto durante il Task 8: due delle tre ragioni con cui questa nota giustificava
l'applicazione differita erano imprecise; una era proprio falsa.** Le ragioni vere, verificate sul
codice:

- **Sono una lista bianca di sicurezza, indicizzata per nome.** `schedulatore/turno.py:38`:
  `SOLA_LETTURA = ("cerca", "guarda", "legami", "richiama", "andamento", "accaduto")` -- i sei nomi
  che un turno risvegliato da una promessa "chiedi" puo' invocare, e nient'altro. E' controllata a
  `schedulatore/turno.py:81-82` (il catalogo esposto al turno e' filtrato su questa tupla) e
  `schedulatore/turno.py:113` (`if nome not in SOLA_LETTURA`, il rifiuto quando il modello prova a
  chiamare uno strumento di scrittura). Rinominare uno dei tredici senza toccare in sincrono questa
  tupla apre o chiude la lista bianca per errore -- un difetto di sicurezza, non solo di lettura.
- **Il testo del prompt nomina gli strumenti al modello, in chiaro.** `casa/domande.py:393-394`
  istruisce il modello a chiamare *"«cerca» per trovare il nome giusto... poi ripeti «guarda»"* --
  il messaggio che risponde quando un riferimento sembra un nome anziche' un id.
  `memoria/interpretazione.py:203-204` fa lo stesso per la coppia *"chiama «cerca»... e ripeti
  «ricorda»"*. Sono frasi generate a runtime che nominano lo strumento **per iscritto**, non un
  identificatore che un editor possa rinominare ovunque in un colpo solo.
- **La ragione piu' forte: questi nomi li legge il modello per scegliere, quindi cambiarli e' un
  cambio di comportamento, non solo di testo.** Un `grep`+`sed` su un identificatore Python non
  puo' dire se il modello, davanti al nuovo nome, continuera' a chiamare lo strumento giusto nello
  stesso punto della conversazione: questo si prova eseguendo dei turni veri, non leggendo un diff.
  E' la ragione per cui il Task 8 decide il nome ma non lo applica: l'applicazione e' una fetta con
  la sua verifica dal vivo, non un'estensione meccanica di questa.

**Le due ragioni corrette (non erano vere come scritte prima di questo task):**

- ~~`spazio` persistita nell'indice della memoria~~ -- **falso: non c'e' nessuna colonna
  persistita.** `CacheIndice` (`memoria/cache_indice.py:112`, `self._voci: dict[str, tuple[tuple,
  Indice]] = {}` a riga 122) e' una cache **puramente in memoria di processo**: nessuna tabella,
  nessun SQL, muore al riavvio (gia' corretto nella riga `spazio` di «I concetti», sopra, ma non
  ancora in questa nota). `spazio` e' solo la chiave di quel dizionario in memoria
  (`memoria/cache_indice.py:27,65,175,179`), e i suoi VALORI capitano a essere due dei tredici nomi
  (`"cerca"`, `"ricorda"`) -- ma non c'e' niente da migrare in un database perche' non c'e' un
  database.
- ~~i nomi vivono in un database, nel `chiamata_json` delle promesse~~ -- **falso: quel campo non
  contiene un nome di strumento.** `schedulatore/archivio.py:39` (`chiamata_json TEXT`) persiste
  cio' che `schedulatore/promessa.py:124` rilegge come `chiamata`: una **chiamata di servizio di
  Home Assistant** (`dominio.servizio` + bersaglio), la stessa forma richiesta da `esegui`, passata
  a `azione/porta.py:607` (`async def esegui(self, chiamata: dict, *, origine: str)`) e verificata
  contro il registro dei servizi a `azione/porta.py:634` (`verifica(chiamata, self._registro,
  stati_prima)`). E' il bersaglio DI un'esecuzione, non il nome DELLO strumento che l'ha proposta:
  in nessun archivio persistito compare uno dei tredici nomi come dato scritto.

| italiano | che cosa fa | inglese | prova del lettore nuovo |
|---|---|---|---|
| cerca | Trova nella casa aree, entita', dispositivi, piani, automazioni, script o etichette a partire da un nome o alias in linguaggio naturale, restituendo la lista COMPLETA dei candidati quando piu' di uno corrisponde allo stesso nome | search | ~ parziale |
| guarda | Il dettaglio completo di UNA cosa sola della casa -- area, entita', dispositivo, automazione, script o ricordo -- dato il suo identificatore ESATTO, mai un nome libero | view | ✓ arriva |
| legami | Chi tocca una cosa della casa secondo Home Assistant -- quali automazioni, script, scene, gruppi o persone la nominano, e dove sta -- calcolato da Home Assistant su tutto cio' che ha caricato, non solo sui file che HIRIS legge da solo | related | ~ parziale |
| ricorda | Salva per sempre qualcosa che una persona ha detto sulla casa -- una preferenza, un divieto, un fatto, una regola -- col testo esatto sempre conservato e un'interpretazione strutturata facoltativa | remember | ✓ arriva |
| richiama | I ricordi gia' salvati che riguardano una parte della casa, dato il suo identificatore ESATTO, senza dover rileggere ogni ricordo uno per uno | fetch | ~ parziale |
| esegui | Chiama un servizio di Home Assistant per far succedere qualcosa nella casa -- accendere, spegnere, impostare -- su un bersaglio di entita' esatte oppure aree, piani, etichette o dispositivi | execute | ✓ arriva |
| prometti | Mette da parte un'azione o una domanda da eseguire piu' tardi -- un'azione viene verificata subito contro l'installazione, una domanda viene guardata all'ora detta | promise | ✓ arriva |
| promesse | Gli impegni futuri che HIRIS tiene in carico -- cio' che e' ancora in sospeso e, su richiesta, come sono andate a finire quelli gia' conclusi | agenda | ✓ arriva |
| disdici | Annulla una promessa non ancora mantenuta, dato il suo identificatore | cancel | ~ parziale |
| costruisci | Propone di creare, modificare o cancellare un'automazione, uno script o una scena -- valida la configurazione contro questa casa e restituisce un'anteprima, senza scrivere nulla | propose | ~ parziale |
| conferma | Applica una proposta creata da `costruisci`, rendendola reale in Home Assistant -- solo dopo che l'utente ha detto esplicitamente di procedere, in un turno successivo a quello dell'anteprima | confirm | ~ parziale |
| andamento | Come e' cambiato nel tempo il valore di UNA entita' -- temperatura, apertura, consumo -- in una finestra di ore all'indietro da adesso, con la grana scelta da HIRIS e dichiarata nella risposta | trend | ~ parziale |
| accaduto | Cosa e' successo in casa in una finestra di tempo, e per mano di chi -- riconoscendo i propri atti confrontando il diario di Home Assistant con la propria cronaca | logbook | ~ parziale |

> **Gli esiti della tabella seguono la stessa tabella azione-per-esito gia' scritta sopra (sezione
> «I concetti», sotto «Cosa comporta ciascun esito»):** `✓` non richiede nessuna azione; `~` per
> collisione con un'altra riga lascia il nome ma porta l'annotazione del rischio specifico, cosi'
> che chi rinomina sappia cosa verificare due volte.

> **Secondo giro di prova (dopo il commit 857eb6e): `view`, `defer`, `agenda` erano marcati
> `~ non ri-provato`** -- cambiati dopo la prima prova, verificati solo sulla collisione col
> codice. La legge della fetta -- *«una riga senza l'esito della prova non e' decisa: e'
> un'opinione»* -- vieta di lasciarli cosi'. **Disegno della ri-prova**
> (`.superpowers/sdd/2026-08-28-il-glossario/task-8bis-risposte.md`): due cataloghi da 13 nomi,
> identici tranne una parola (`defer` contro `promise` al posto di `prometti`), quattro lettori --
> due per catalogo, su modelli diversi -- nessuno a conoscenza dell'altro catalogo, tutti
> `tool_uses: 0`. Il catalogo resta unico e non mescolato con esche di altri sottosistemi, per lo
> stesso motivo del primo giro: e' cosi' che un modello li vede davvero. Risultato per riga, sotto.

> **`view` confermato, `✓ arriva`.** Tutti e quattro i lettori, con parole quasi identiche:
> *«il dettaglio completo di un elemento gia' identificato, per id»*, *«dato un id, ne recupera il
> contenuto/stato completo»* -- combacia con la riga del glossario senza bisogno di interpretarla.
> `view`/`fetch`, la coppia che aveva bocciato `show`, scende a coppia debole e ultima per chi la
> nomina ancora (*«confusione minore, il contesto disambigua da solo»*): lo scarto di `inspect` per
> la collisione con `import inspect` (`casa/strumenti.py:126,1096`, lo stesso file che definisce i
> 13 strumenti) resta la scelta giusta, confermata dalla prova.
>
> **Il sospetto sul confine era stato chiuso su un'evidenza sbagliata -- corretto durante la review
> finale del ramo, e riaperto onestamente.** Prima di chiudere `view`, era stato controllato se
> fosse un secondo caso di confine mancato -- in Home Assistant una *view* e' anche una scheda di
> plancia (dashboard). La chiusura precedente citava `proxy/ha_client.py:411,499`
> (`components/config/view.py`, il modulo di rotta con cui Home Assistant serve `/api/config/...`)
> come prova che il sospetto non reggeva -- **era il file sbagliato: quell'evidenza non c'entra ne'
> in un senso ne' nell'altro.**
>
> **L'evidenza vera va nel senso opposto, e il documento la contiene gia'.** La riga `plance`
> (sopra, `dashboards`) dice che le dashboard hanno *«percorso, titolo, modalita' e **viste**
> proprie»*, e il codice usa "viste" nel senso di Home Assistant, non a caso: `casa/anagrafe.py:
> 730-732` (*«Le entita' NASCOSTE (`hidden_by` non nullo: l'utente le ha tolte dalle **proprie
> viste** in Home Assistant)»*) e `:979-981` (*«sono entita' vere, che l'utente ha solo tolto dalle
> **proprie viste**»*) -- entrambi parlano delle schede di una dashboard, non di "guardare il
> dettaglio di una cosa". La frase precedente, *«il sospetto non ha trovato riscontro ne' nel
> codice ne' nella prova»*, e' **falsa sul codice**: un riscontro c'e', ed e' proprio nella parte
> del prodotto (le dashboard) che questa fetta gia' rinomina altrove.
>
> **Riaperto e richiuso di nuovo, questa volta sull'evidenza giusta: il rischio si accetta,
> dichiarato per iscritto, non si scarta per mancanza di prove.** Due fatti restano veri insieme:
> (1) Home Assistant chiama "view" le schede di una dashboard, un senso reale e diverso da quello
> di questo strumento; (2) **nessuno dei quattro lettori della ri-prova a due cataloghi (Task 8,
> `view` testato nudo dentro un catalogo di 13 nomi di strumenti) ha letto "plancia", "scheda" o
> "dashboard"** -- tutti e quattro hanno letto *«il dettaglio completo di un elemento gia'
> identificato, per id»*. La prova che conta per una decisione di naming e' quella che riproduce la
> condizione vera in cui il modello incontra il nome (dentro un catalogo di 13 strumenti, non contro
> l'intero vocabolario di Home Assistant preso da solo), e su quella prova specifica il rischio non
> si e' materializzato. Tenuto `view`: il rischio di confine con le dashboard di HA e' reale e
> resta scritto qui, non silenziato -- ma non ha superato la soglia per cambiare un nome gia'
> confermato da quattro letture indipendenti su un compito piu' pertinente.
>
> **`fetch` resta cosi' com'e' -- decisione scritta ora, mancava, durante la review finale del
> ramo.** `fetch(...)` e' la funzione globale del browser per le chiamate HTTP dalla pagina.
> **Corretto durante la re-review mirata: la cifra "oltre 50 volte" contava il TOKEN `fetch`, non
> le chiamate** -- il brief da cui veniva ereditava un numero senza dire quale delle due cose
> stesse contando, e non l'ho ri-misurato. Le chiamate vere, `fetch(`, sono **26** in
> `hiris/app/static/**/*.js` (`chat/agents.js:79,140,157`, `chat/main.js:18`, `chat/send.js:43`, e
> nel resto del frontend); il token nudo `fetch` arriva a 57 perche' conta anche occorrenze non di
> chiamata, come la stringa `'X-Requested-With': 'fetch'` (`chat/agents.js:79`). Il numero che
> conta per il ragionamento sotto e' 26 (le chiamate reali): non un'invenzione di HIRIS, la stessa
> API che ogni pagina web userebbe per parlare col proprio backend. Stesso ragionamento gia'
> scritto per `search`/`execute`/`cancel` contro `re.search()`/`sqlite3.execute()`/
> `asyncio.Task.cancel()` (sopra, «I nomi degli strumenti»): il match non cade su un identificatore
> che QUESTO progetto ha scelto per nominare un proprio concetto diverso, cade su un'API di
> piattaforma che qualunque pagina JavaScript chiamerebbe comunque cosi'. `richiama` (lo strumento
> che usa `fetch`) e il `fetch()` del browser vivono in due mondi separati -- Python lato server,
> JavaScript lato client -- e non c'e' un file dove un lettore vedrebbe le due cose fianco a fianco
> confondendole, a differenza del rischio reale gia' scritto per `promise` contro `new
> Promise(...)` (sopra), dove invece un rename lato JavaScript potrebbe far collidere le due cose
> nello stesso file.

> **`promise`/`promises` -- il reperto principale della prima prova, sanato con una parola sola,
> non con due nuove.** Nel catalogo con `promise`/`promises` la coppia era il rischio numero uno
> per entrambi i lettori, per la quasi-omografia (*«differiscono solo per una "s"»*,
> *«facilissimo scambiarli»*) prima ancora che per sovrapposizione di significato. **Non e' un
> difetto introdotto da questa scelta di inglese: esiste gia' in italiano** -- `prometti`/
> `promesse` sono la stessa identica coppia, con la stessa identica differenza di una lettera. La
> prima traduzione l'aveva ereditato invece di risolverlo, aggiungendo una "s" per il plurale
> esattamente come l'italiano.
>
> **Primo tentativo di cura, `defer`, bocciato dalla ri-prova -- non per confondibilita', per la
> domanda che decide (la prima: "che cosa fa").** Entrambi i lettori del catalogo `defer` lo
> leggono come *«rimanda/posticipa un'azione a dopo... senza eliminarla»*: presumono una cosa che
> **esiste gia'** e viene spostata. Lo strumento invece la **crea** (un impegno nuovo, non uno
> spostato). E' un errore di funzione, non di stile, e genera un difetto nuovo che prima non
> c'era: la coppia `defer`/`cancel` (*«il rischio e' scegliere `cancel` quando si intendeva solo
> posticipare -- perdita di un'azione»*), che nasce esattamente da quella lettura sbagliata
> (`defer` suona come "sposta una cosa che c'e' gia'", quindi si avvicina a `cancel`, che su una
> cosa che c'e' gia' opera davvero).
>
> **Scelto `promise` al posto di `defer`, per tre ragioni convergenti:**
>
> 1. **La prova.** Nel catalogo con `promise`, entrambi i lettori lo leggono su domanda 1 come
>    *«crea/registra un impegno futuro a fare qualcosa»* -- combacia con la riga del glossario, non
>    la deforma.
> 2. **La fondamenta n.3 ("la stessa cosa ha la stessa forma da tutte le porte").** La riga
>    `promessa` di «I concetti» (sopra) e' gia' `promise`, `✓ arriva`: lo strumento che CONIA una
>    promessa deve portare il nome di cio' che conia, o il catalogo (cosa dice il modello) e il
>    dominio (cosa e' la cosa) divergono sulla stessa entita'.
> 3. **Il difetto misurato era la coppia, non una delle due meta'.** Cambiare `prometti` in un
>    terzo termine indipendente da `promesse`/`agenda` avrebbe rotto l'ortografia comune, ma senza
>    ancorare `prometti` al concetto che produce -- una cura piu' debole di quella che riallinea lo
>    strumento al dominio.
>
> **Quindi: `prometti` -> `promise`, `promesse` -> `agenda`.** Il difetto ortografico e' morto lo
> stesso: nel catalogo finale nessuna delle coppie residue e' ortografica (differenza di una
> lettera o quasi-omografia), sono **tutte semantiche** (sovrapposizione di significato o di
> funzione). **Ed e' proprio questo che rende la sanatoria definitiva: una confusione semantica la
> cura la descrizione dello strumento (si legge la frase intera, non solo il nome); una
> confusione ortografica no (il nome nudo e' l'unica cosa che il modello confronta quando deve
> scegliere in fretta, e "cerca"/"c" di differenza non lascia nulla da leggere).** E' il motivo per
> cui questa sanatoria chiude il problema mentre le note sotto (`search`/`related`,
> `remember`/`logbook`, il trio `propose`/`confirm`/`execute`) restano aperte come rischio
> annotato invece che come difetto da correggere con un nome: sono tutte semantiche, quindi la
> cura e' nella description, non in un quarto giro di sinonimi.
>
> Questo NON tocca la riga `promessa` di «I concetti» (sopra, gia' `promise`, `✓ arriva`): quella e'
> il concetto/dato Python (`schedulatore/promessa.py`), questa e' la stringa che il modello legge
> come nome di strumento -- **due decisioni distinte**, gia' documentato nella nota sotto la tabella
> «I concetti». Che oggi coincidano (`promise` per entrambe) non e' una svista ne' un doppione: e'
> lo stesso concetto visto dalle due facce che questa fetta separa ovunque -- il dato e lo
> strumento che lo scrive -- ed e' esattamente il caso in cui coincidere e' corretto (ragione 2,
> sopra). Il controllo "nessun inglese usato due volte per due concetti diversi" (vedi i controlli
> di completezza, in fondo al documento) non si applica qui perche' non sono due concetti diversi.

> **`search`/`related`: entrambi i lettori li hanno accoppiati** (*"entrambi restituiscono
> liste"*), ma qui il nome non si tocca, perche' `related` e' un nome di confine (`legami` chiama
> letteralmente `search/related` di Home Assistant, vedi sotto) e il confine vince sempre su un
> sinonimo inventato -- anche quando la prova segnala un rischio vero. **L'azione qui non e'
> rinominare: e' scrivere che la disambiguazione deve stare nella description dello strumento, non
> nel nome**, cosa che le description italiane gia' fanno oggi e che chi tradurra' NON deve perdere:
> `cerca` parte da un **testo libero e ambiguo** (un nome o alias scritto dall'utente) e puo'
> restituire piu' di un candidato quando non sa quale sia quello giusto (`casa/strumenti.py:169-180`,
> `«ambiguo»` a riga 179); `legami` parte invece da un **identificatore gia' risolto** (`riferimento`,
> l'id esatto -- `casa/strumenti.py:313-314`, `"usa cerca se hai solo un nome"`) e restituisce chi
> lo tocca, non candidati su cosa potrebbe essere. La differenza da rendere esplicita, per chi
> scrivera' la description in inglese: **testo ambiguo -> candidati** (`search`) contro
> **id esatto -> collegamenti** (`related`). Se una futura traduzione della description perde questo
> contrasto, il nome da solo non basta a recuperarlo -- la prova lo dimostra.

> **`remember`/`logbook`: tre lettori su quattro nella ri-prova, coppia non affrontata nel primo
> giro.** *«Entrambi conservano informazioni, ma uno e' una memoria dichiarata e intenzionale,
> l'altro un registro automatico»*; piu' netto: *«si potrebbe usare `remember` per loggare un
> evento, o cercare in `logbook` qualcosa che era stato salvato con `remember`»*. Stessa cura di
> `search`/`related`, per lo stesso motivo: `logbook` e' un nome di confine (`accaduto` chiama
> letteralmente `/api/logbook` di Home Assistant, sotto) e non si tocca, anche con un rischio
> confermato da tre lettori su quattro. **L'azione e' di nuovo nella description, non nel nome**:
> `ricorda` scrive una frase che una PERSONA ha detto, con la sua interpretazione facoltativa
> (`casa/strumenti.py:357-364`) -- una memoria **dichiarata**, mai generata da sola; `accaduto`
> legge il diario che Home Assistant tiene **da solo**, per ogni cambiamento di stato, senza che
> nessuno lo dichiari (`casa/strumenti.py:833-855`, `ha_client.diario()`). La differenza da rendere
> esplicita in inglese: **dichiarata da una persona** (`remember`) contro **registrata in
> automatico dal sistema** (`logbook`). E' salita da un rischio isolato (un lettore su due, primo
> giro) a un rischio maggioritario (tre su quattro, secondo giro): la ri-prova non l'ha solo
> confermata, l'ha aggravata, e la nota va aggiornata di conseguenza -- non e' piu' un'annotazione
> marginale.

> **Perche' `legami` -> `related` e non un sinonimo inventato (`links`, `relations`):** e' il
> confine, non un'invenzione. `legami` chiama, sotto, il comando nativo di Home Assistant
> `search/related` (`proxy/ha_client.py:1406`, `TIPI_LEGAME` a riga 1371-1373 coi VALORI di
> `ItemType` di `homeassistant/components/search/__init__.py`) -- HA ha gia' un nome per "chi tocca
> questa cosa", ed e' quello, non un sinonimo che questa fetta esiste per non inventare.
>
> **Perche' `accaduto` -> `logbook` e non `history`:** stessa logica, ma con un secondo passo che
> vale la pena raccontare perche' e' il controllo di collisione a fare il lavoro. `accaduto` legge
> `ha_client.diario()` (`proxy/ha_client.py:1060`, `GET /api/logbook/<ISO start>` a riga 1094) --
> il nome nativo di Home Assistant per questa funzione e' `logbook`, non `history`. `history` era
> il primo candidato (e' anche il nome dell'API usata da `andamento`, sotto), ma **collide nel
> codice**: `history` e' gia' una chiave/parametro non-prosa usata ovunque per la cronologia dei
> MESSAGGI di chat (`agent/prompts.py:365` `build_chat_messages(system_prompt, history, ...)`,
> `agent/runner.py:1172` `history = context.get("history")`, `api/handlers_chat.py:354`
> `"history": sanitized_history`, oltre al vecchio `history.db` uscito dal prodotto) -- un
> significato completamente diverso (i turni della conversazione, non il diario della casa). Il
> passo 2 del controllo di collisione (grep su `hiris/`, non solo sul glossario) blocca `history`
> qui esattamente come ha bloccato `gateway` e `build` nella review del Task 4.
>
> **Perche' `andamento` -> `trend` e non `history`, nonostante `andamento` usi davvero le API
> `/api/history/period` e `recorder/statistics_during_period` di Home Assistant
> (`proxy/ha_client.py:965,1274,1292`):** il nome di confine sarebbe `history`, ma e' lo stesso
> nome gia' bloccato sopra per `accaduto` -- e usarlo qui aggraverebbe esattamente la collisione con
> la cronologia di chat appena descritta, oltre a rendere `andamento` e `accaduto` indistinguibili
> fra loro (il rischio che questo lotto esiste per evitare). Scelto un nome funzionale che descrive
> UNA serie numerica nel tempo invece del registro di eventi -- pulito su `hiris/` (nessuna
> occorrenza come identificatore).
>
> **`trend`/`logbook`: rischio previsto dall'implementer e confermato da un lettore su due**
> (*«entrambi guardano al passato; per "fammi vedere cosa e' successo" potrei esitare»*). Non c'e'
> un terzo nome piu' pulito disponibile: `history`, il candidato di confine per entrambi, e' bloccato
> per collisione col codice (sopra) per tutti e due, quindi sostituirne uno solo con `history`
> aggraverebbe la collisione invece di scioglierla. Resta un rischio annotato (`~ parziale`), non
> chiuso: la differenza reale -- una serie numerica di UNA entita' contro un registro di eventi
> discreti dell'intera casa -- va portata nella description quando questi nomi si applicano, con lo
> stesso principio appena scritto per `search`/`related`.

> **Verificato ma NON trattato come collisione bloccante:** `search` (`cerca`), `execute` (`esegui`)
> e `cancel` (`disdici`) compaiono in `hiris/app` solo come chiamate a metodi di libreria standard
> gia' esistenti -- `re.search()`, `sqlite3.Connection.execute()`, `asyncio.Task.cancel()` -- mai
> come un identificatore che QUESTO progetto ha scelto per nominare un proprio concetto diverso. E'
> lo stesso principio che tollera `construction` nei commenti (sopra): il match non cade su una
> parola che il progetto usa per dire un'altra cosa, cade su un'API esterna che userebbe la stessa
> parola comunque, in qualunque progetto Python. Segnalato qui perche' due persone potrebbero
> leggere la regola meccanica in modo diverso su questo caso, e non deve restare implicito quale
> lettura ho applicato.

> **`costruisci` -> `propose` e' coerente con `proposta` (concetto, gia' `proposal`) e col metodo
> Python che gia' implementa l'azione**, `azione/costruzione/officina.py:132`
> (`async def proponi(...)`) -- due indizi indipendenti che convergono sullo stesso inglese.
>
> **`propose`/`confirm`: la vicinanza dei NOMI e' voluta, non un difetto -- ma il rischio vero,
> trovato dalla ri-prova, non e' di naming.** Nel primo giro il lettore B aveva accoppiato
> `propose`/`confirm` come un accoppiamento debole, e la lettura restava giusta: sono **i due poli
> dello stesso flusso** (proponi, poi conferma solo in un turno successivo e solo dopo il si'
> esplicito dell'utente), non due sinonimi. **La ri-prova a quattro lettori pero' ha trovato
> qualcosa di piu' serio, sullo stesso terzetto piu' `execute`:** un lettore lo mette **al primo
> posto per rischio in tutte e due le varianti del catalogo**, e la ragione dichiarata non e'
> l'esitazione fra due nomi:
>
> > *«non e' solo semantica ma tocca il flusso di autorizzazione: se voglio "far succedere una
> > cosa", non e' chiaro se devo chiamare `execute` direttamente o passare per `propose` e poi
> > `confirm`. Sbagliare qui significa potenzialmente **bypassare un gate di approvazione**
> > (eseguire senza che nessuno abbia confermato).»*
>
> E, nella nota d'insieme dello stesso lettore: *«il gruppo piu' rischioso e' quello del ciclo di
> vita di un'azione differita -- `promise`, `agenda`, `propose`, `confirm`, `cancel`, `execute` --
> sei verbi che sembrano coprire fasi diverse dello stesso processo, e senza documentazione e'
> facile sovrapporli o invocarli nell'ordine sbagliato.»*
>
> **Non si cura rinominando** (i nomi presi singolarmente restano corretti, vedi la nota su
> `costruisci` -> `propose` appena sopra). **Si cura nella description**, e la richiesta e' piu'
> precisa di "spiega cosa fa ciascuno": la description
> di `execute` deve dire esplicitamente quando si puo' chiamare diretto (un servizio che tocca la
> casa adesso, senza bisogno di anteprima) e quando invece il gate `propose`+`confirm` e'
> obbligatorio (creare, modificare o cancellare configurazione), e le description di `propose`/
> `confirm` devono nominarsi a vicenda come le due meta' di un unico gate, non come strumenti
> indipendenti. Lo stesso principio richiesto sopra per `search`/`related` e `remember`/`logbook`,
> qui applicato a un rischio piu' grave perche' non e' "che cosa restituisce" ma "chi ha autorizzato
> questo cambiamento" -- il tipo di errore che questa fetta intera esiste per prevenire.
>
> Il lettore ha anche accoppiato debolmente `cancel`/`propose` (stessa soglia di `fetch`/`search`,
> annotato, nessuna azione oltre a quanto gia' coperto dalla nota sul ciclo di sei verbi sopra).
>
> **Dubbio aperto, non richiuso qui:** il metodo interno dietro `conferma` si chiama `applica`
> (`azione/costruzione/officina.py:328`, `async def applica(...)`), che suggererebbe `apply` invece
> di `confirm`. Ho tenuto `confirm` perche' la descrizione dello strumento insiste sul cancello
> **"solo dopo che l'utente ha detto di procedere, in un turno successivo"** -- e' quel consenso
> esplicito, non il meccanismo di scrittura, la ragione per cui questo strumento esiste separato da
> `costruisci`; `apply` lo dice meno di `confirm`. Ma e' un giudizio, non una misura: se una prova
> futura mostra che `confirm` si confonde con qualcos'altro, `apply` resta il secondo candidato
> pronto.
>
> **`execute`: non piu' "chiaramente distinto" dopo la ri-prova.** Il primo giro l'aveva dichiarato,
> insieme a `remember`, l'unico strumento che nessun lettore confondeva. La ri-prova lo smentisce:
> `execute` e' proprio il terzo vertice del rischio "gate di autorizzazione" appena descritto. La
> nota va corretta di conseguenza -- non e' un naming pulito che basta a se stesso, e' un naming
> pulito che da solo non comunica un vincolo di sequenza, e quel vincolo va scritto altrove
> (description, non nome).
>
> **`remember` resta il piu' solido dei tredici**, ma non per la ragione scritta nel primo giro
> (che l'accoppiava anche a `execute`): nella ri-prova nessuno dei quattro lettori ha accoppiato
> `remember` con `fetch` (confermando che la separazione lessicale scelta per la coppia a rischio
> originale, `ricorda`/`richiama` -> `remember`/`fetch` e non `remember`/`recall`, ha tenuto), ma
> tre lettori su quattro l'hanno accoppiato con `logbook` -- vedi la nota dedicata sopra, che
> sostituisce la vecchia annotazione "isolata e generica" con l'azione richiesta sulla description.

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

**Il rinvio dei ~40 valori (12 costanti) e' una decisione scritta, non un silenzio -- corretto
durante la review finale del ramo, che ha trovato la colonna «valori — inglese» vuota su ogni
riga senza che nessuna nota lo dichiarasse.** La spec dice *«il glossario decide TUTTO»*, e la
testata del documento (in cima) oggi dichiara giustamente che l'elenco e' completo: questa e'
l'unica eccezione, ed e' dichiarata qui, non lasciata a un lettore che deve accorgersene da solo
guardando una tabella con una colonna intera bianca. **Nota per la cronaca: nel dispaccio al
proprietario si era riferito "zero righe senza nome" -- era falso proprio per questa tabella, e la
correzione e' qui.**
**Corretto durante la re-review mirata: la prima ragione scritta qui era una scelta di parole
sbagliata, e citava un precedente che dimostra il contrario di cio' per cui veniva invocato.** La
prima stesura diceva "questi sono dati persistiti, non identificatori: tradurli richiede una
migrazione, quindi il NOME si rinvia" -- ma il paragrafo appena sopra, per i 13 nomi degli
strumenti, dice esattamente l'opposto: *«Sono dati... il nome si decide qui, si applica in una
fetta che sa gestire la migrazione»*. Per quei 13 l'essere dati persistiti e' la ragione per cui
si rinvia l'APPLICAZIONE, non la ragione per rinviare la decisione -- la colonna «inglese» dei 13
strumenti infatti e' piena. Essere un dato persistito, da solo, non giustifica un rinvio della
decisione qui: il nome **si potrebbe** decidere anche per questi ~40 valori, cosi' come e' stato
deciso per i 13 strumenti.
La ragione vera, e basta da sola: tradurre ~40 valori enum-like col rigore che le altre ~80 righe
di questo documento hanno gia' ricevuto (controllo di collisione a tre passi PIU' la prova del
lettore nuovo dove serve) e' un lavoro della stessa taglia di un intero task di questa fetta, non
una riga da riempire di corsa dentro un giro di correzioni; farlo senza quel rigore produrrebbe 40
opinioni etichettate come misure — esattamente il difetto che questo documento esiste per non
fare. **Decisione: rinviato a un dispaccio dedicato**, con lo stesso metodo gia' usato per gli
altri lotti di questa fetta — non deciso qui, non dimenticato. (La migrazione dei dati gia'
scritti, quando i valori saranno decisi, restera' comunque un passo a se', come per i 13 nomi
degli strumenti — quella parte della ragione originale non era falsa, era solo il posto sbagliato
per usarla.)

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

## Controlli di completezza

**Aggiunta durante la review finale del ramo: due note del documento rimandavano qui prima che
questa sezione esistesse (righe ~99 e ~1256) -- corretto scrivendola, non togliendo il rimando,
perche' i controlli sono reali e vale la pena poterli rifare invece di fidarsi.** Tre controlli
meccanici, eseguibili da chiunque:

**1. Nessuna cella vuota, in nessuna tabella del documento** (salvo l'eccezione dichiarata in
«I valori di dominio», sopra):

```bash
python - <<'PY'
import pathlib
t = pathlib.Path('docs/GLOSSARIO.md').read_text(encoding='utf-8').split(chr(10))
header, vuote = None, []
for r in t:
    if r.startswith('## '): header = None; continue
    if r.startswith('| ') and '---' not in r:
        cols = [c.strip() for c in r.strip('|').split('|')]
        if cols[0] in ('italiano', 'costante', 'parola uscita dallo script',
                       'forma uscita dallo script'):
            header = cols; continue
        if header is None: continue
        for i, val in enumerate(cols):
            if not val:
                vuote.append((cols[0], header[i]))
print(vuote or "nessuna riga vuota")
PY
```

Eseguito ora: 12 righe vuote, tutte in «I valori di dominio», colonna «valori — inglese» -- **e
non un'altra**. E' esattamente l'eccezione dichiarata in cima a quella sezione: se questo comando
restituisse anche una sola riga vuota FUORI da quella tabella, sarebbe una riga dimenticata da
decidere, non l'eccezione nota.

**2. Nessun inglese usato due volte per due concetti diversi.** Confronta ogni parola inglese
decisa contro l'italiano di provenienza, su tutte le tabelle:

```bash
python - <<'PY'
import re, pathlib
from collections import defaultdict
t = pathlib.Path('docs/GLOSSARIO.md').read_text(encoding='utf-8').split(chr(10))
header, sez, byword = None, None, defaultdict(set)
for r in t:
    if r.startswith('## '): sez = r[3:].strip(); header = None; continue
    if r.startswith('| ') and '---' not in r:
        cols = [c.strip() for c in r.strip('|').split('|')]
        if cols[0] in ('italiano', 'costante'):
            header = cols; continue
        if header is None: continue
        try: idx = header.index('inglese')
        except ValueError: continue
        for w in re.findall(r'`([a-zA-Z_]+)`', cols[idx]) or ([cols[idx]] if cols[idx] else []):
            byword[w].add((sez, cols[0]))
for w, s in byword.items():
    itas = set(x[1] for x in s)
    if len(itas) > 1:
        print(w, '->', s)
PY
```

**Risultato atteso, eseguito ora: cinque casi, tutti gia' documentati altrove nel documento.**
`reading` (`cambi`/`grezzo`): non cambia con la rinomina del rilievo A2 (ne' col candidato
intermedio bocciato, `sample` -- vedi la nota sotto la tabella «I concetti»), e' lo stesso caso
che prima si chiamava `raw` con la stessa identica giustificazione — un solo concetto, due nomi
italiani. `count` (`conta`/`quante`),
`list` (`elenco`/`elenca`) e `read` (`letto`/`leggi`) sono forme flesse della stessa parola
ordinaria. `promise` compare sia come concetto (`promessa`) sia come nome di strumento
(`prometti`): **non e' una svista**, e' lo stesso concetto visto dai due lati che questa fetta
separa ovunque -- il dato e lo strumento che lo scrive -- documentato per esteso nella nota sotto
la tabella dei 13 nomi degli strumenti. Se questo comando restituisse un sesto caso non elencato
qui, sarebbe una collisione vera da correggere, non da spiegare.

**3. Nessun file di codice toccato, e il linter resta verde:**

```bash
git status --porcelain   # deve mostrare solo docs/GLOSSARIO.md
python -m ruff check     # deve dire "All checks passed!"
```
