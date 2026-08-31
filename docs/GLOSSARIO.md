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

## Il limite della qualificazione per ambito

**Aggiunto durante la re-review di Task 5 (fix round 2): un limite del meccanismo, incontrato due
volte, va scritto qui invece di essere riscoperto una terza.** La qualificazione per ambito
(`parola (ambito)`, nelle tabelle sotto) risolve l'omonimia fra sottosistemi diversi -- la stessa
parola italiana, un significato per sottosistema. Ma presuppone esattamente questo: **un senso per
ambito**. `Glossario.per(parola, ambito)` restituisce un solo inglese per quella coppia, non uno
per occorrenza -- non sa esprimere due sensi DENTRO lo stesso ambito.

Incontrato due volte, in due forme diverse:

- **`spazio` dentro `memoria/`** (Task 5, prima review): `spazio (memoria)` → `slot` e' il concetto
  di cache (`cache_indice.py`, «a quale chiamante appartiene una voce»). Ma `spazio_precedente`,
  una variabile locale di `resolver.py::_normalize_con_mappa`, non parla affatto di quel concetto:
  e' il carattere di spaziatura che precede un token durante una normalizzazione di stringa. Stessa
  parola, stesso ambito, due significati senza nulla in comune. Risolto senza una seconda riga
  ambito-qualificata (qui non avrebbe nemmeno senso: non c'e' un secondo ambito da nominare, e' la
  stessa funzione) -- deciso a mano, il singolo residuo, guardando il codice invece di applicare
  `slot` alla cieca.
- **`riferimento` dentro `casa/`** (questo fix round, vedi la riga in «I concetti», sotto): il senso
  *frame* (`sistema_di_riferimento` e i suoi due composti imparentati) e il senso *reference* (l'id
  a cui punta un'ancora -- lo stesso di `riferimento (memoria)`) convivono nello stesso ambito, a
  volte nello stesso file. Qui va meglio che con `spazio` **solo perche' i due sensi hanno forme
  lessicali diverse**: uno vive *sempre* dentro un composto (mai nudo da solo), l'altro vive
  *sempre* nudo (mai come pezzo di un composto piu' lungo). Lo strumento propone sempre i composti
  invece di applicarli da solo, quindi il senso sbagliato non passa mai dall'automatismo su quella
  forma -- ma e' una fortuna della forma di questo caso, non una capacita' del meccanismo: se le due
  forme coincidessero (due sensi entrambi nudi, o entrambi dentro lo stesso composto), la
  qualificazione per ambito non li distinguerebbe, e servirebbe di nuovo una decisione a mano riga
  per riga.

**Il segnale a cui guardare, per chi convertira' `azione/` o il resto di `casa/`:** una parola gia'
qualificata per ambito che, dentro QUEL sottosistema, compare sia nuda sia dentro composti con
significati diversi. Non basta chiedersi «che ambito e'»: bisogna chiedersi anche «che forma ha,
qui, in questa occorrenza» prima di fidarsi del valore della riga.

**Terzo caso, e stavolta il peggiore dei tre: `fuori` dentro `casa/`** (rilievo della review
indipendente sul lotto 5). `fuori (casa)` → `outside` e' stato deciso guardando le forme composte
di `anagrafe.py` (`fuori_dalle_aree` → `outside_areas`, `_ID_FUORI_DALLE_AREE`,
`_fuori_dal_confronto` → `_excluded_from_comparison`): tutte portano il senso "escluso/al di fuori
di un confine". Ma la stessa parola, **nuda**, compare una volta sola nello stesso file
(`categorie_con_nome`, oggi `categories_with_name`) con un senso completamente diverso: non
"escluso", ma "il dizionario che la funzione produce in uscita" -- lo stesso idioma di
`schedulatore/promise.py::serializza` (`fuori = {...}; return fuori`) e di
`consumi/store.py`, gli stessi due file che avevano gia' motivato la qualificazione `(casa)` invece
di lasciare `fuori` nudo per l'intero repository. **Qui l'asimmetria gira dalla parte sbagliata**:
non e' la forma composta a portare il senso minoritario (come per `riferimento`, sopra) -- e'
proprio la forma NUDA, quella che lo strumento applica da solo senza chiedere conferma, a portare
il senso sbagliato in un caso. Applicato una prima volta alla cieca (`fuori` → `outside` sul
dizionario delle categorie risolte: un nome che mente, "outside" su un dato che non ha niente di
"fuori" o "escluso"), corretto durante la review indipendente in `resolved` -- deciso a mano, il
singolo residuo, esattamente come gia' fatto per `spazio_precedente` sopra. La riga `fuori (casa)`
resta corretta per tutti gli altri usi del file (composti, mai applicati da soli): il residuo era
uno solo, ed era nella forma che il meccanismo si fida di piu'.

**Quarto caso, di meccanismo non di significato: una riga ambito-qualificata spegne la riga nuda
per OGNI ALTRO ambito, non solo per il proprio.** Trovato convertendo `api/handlers_promesse.py`
(Task 9 di questa fetta): `Glossario.per()` cerca prima in `omonimi`, e `leggi_glossario()` toglie
la parola da `mappa` (la riga nuda) nel momento stesso in cui legge la PRIMA riga qualificata per
quella parola, qualunque sia l'ambito -- verificato chiamando `Glossario.per("riga", ...)` da
codice: `per("riga", "casa")` e perfino `per("riga", "api")` → `None`, nonostante la riga nuda
`riga | row` sia ancora scritta nella tabella due righe sopra. La riga nuda non e' quindi un
ripiego che "resta valido per tutti gli altri ambiti" quando ne esiste una qualificata da qualche
parte -- e' spenta ovunque, e ogni ambito che vuole quel senso deve avere la propria riga
qualificata esplicita, anche se il senso e' identico a quello che la riga nuda intendeva dare di
default. E' per questo che esiste, qui sotto, `riga (api) | row`: non un secondo senso di `riga`
scoperto in `api/`, ma la stessa riga nuda `riga | row` resa di nuovo raggiungibile per questo
ambito. **Chi trova `per(parola, ambito)` che torna `None` per una parola che il glossario sembra
gia' dare per scontata non deve fidarsi della riga nuda**: va verificato con `Glossario.per()` da
codice se quella parola ha gia' una riga qualificata altrove per un ambito diverso -- se si', la
riga nuda e' gia' spenta anche per il proprio ambito, silenziosamente.

**Correzione allo stesso paragrafo (Task 9, verifica del coordinatore): l'esempio originale
citava `per("riga", "nucleo") -> "line"` come caso funzionante -- era falso.** `nucleo` non e' mai
stato un ambito valido: gli ambiti sono i nomi delle CARTELLE con cui si invoca `rinomina.py
--ambito <...>` (`casa`, `memoria`, `api`, ...), e `nucleo.py` e' un FILE dentro `casa/`. La riga
era scritta `riga (nucleo)`, non `riga (casa)`: nessuna invocazione reale dello strumento passa
mai `--ambito nucleo`, quindi quella riga non ha mai risolto nulla per nessuno, dal lotto di
`strumenti.py` fino a qui -- il codice di `nucleo.py` e' comunque giusto solo perche' la famiglia
`line` fu applicata A MANO. Corretto in tabella (`riga (casa) | line`, sopra) e verificato
eseguendo: `Glossario.per("riga", "casa")` torna ora `line`, senza conflitti nel resto di `casa/`
(scansione `tokenize`, zero identificatori `riga`/`righe` residui fuori da `nucleo.py`).

**La conseguenza operativa generale, per chi qualifica una parola d'ora in poi: qualificarla per
UN ambito la rende cieca in TUTTI GLI ALTRI, non solo silenziosa in quello nuovo.** Non e' un
difetto da correggere in blocco -- e' il comportamento sicuro (`None` invece di indovinare) --
ma va saputo, perche' il criterio di fine di questa fetta conta i COMPOSTI, e una parola nuda gia'
qualificata altrove che ricompare nuda in un ambito nuovo non e' un composto: e' invisibile allo
stesso identico modo, silenziosamente italiana per sempre finche' nessuno aggiunge la riga
`parola (nuovo_ambito)` esplicita. Tredici parole sono gia' qualificate in questo glossario, e
ciascuna e' cieca in ogni ambito che non compare fra parentesi: `ancora` (vede in `consumi`,
`memoria`), `guarda` (`casa`, `cervello`), `verifica` (`azione`, `memoria`), `lettura` (`casa`,
`consumi`), `riferimento` (`casa`, `memoria`), `riga` (`casa`), `dopo`/`fuori`/`loro`/`nostro`/
`senza`/`note` (solo `casa`) -- misurato chiamando `Glossario.omonimi` da codice. Nei quattro
ambiti non ancora aperti da questa fetta (`api`, `agent`, `proxy`, `backends`) tutte e tredici
restano italiane senza che nessun dry-run lo segnali, se compaiono nude. **La disciplina, non
un'automazione**: quando una di queste parole compare nuda in un file che si sta convertendo,
verificare con `Glossario.per(parola, ambito)` da codice invece di fidarsi del dry-run, decidere
guardando il codice se il senso e' lo stesso di un ambito gia' qualificato o un altro ancora, e
aggiungere la riga `parola (proprio_ambito)` di conseguenza -- esattamente il passo gia' fatto per
`riga (api)` sopra.

## Verbo e sostantivo possono condividere lo stesso inglese: e' una classe ACCETTATA

**Scritta durante il Task 9 (lotto 12) su richiesta del coordinatore, dopo che era gia' successa
cinque volte senza che nessuna riga la dichiarasse.** L'italiano distingue il verbo dal sostantivo
dell'atto (`scrivi`/`scrittura`, `elenca`/`elenco`); l'inglese spesso no. Quando due parole
italiane sono il verbo e il nome dello STESSO atto, la colonna «inglese» puo' contenere la stessa
parola per entrambe, e **non e' l'omonimia che «Il limite della qualificazione per ambito»
descrive**: li' una parola italiana porta due sensi diversi e va disambiguata; qui due parole
italiane portano lo stesso senso, e il collasso e' una proprieta' della lingua di arrivo, non un
difetto da contenere.

Le sei coppie oggi in tabella -- **l'elenco e' il punto, non l'esempio**: cinque erano nate una
per volta, ciascuna senza sapere delle altre, e la sesta stava per essere ridecisa da capo perche'
nessuna riga diceva che la classe era ammessa.

| verbo | sostantivo | inglese |
|---|---|---|
| `scrivi` | `scrittura` | `write` |
| `elenca` | `elenco` | `list` |
| `raggruppa` | `gruppo` | `group` |
| `taglia` (come `tagliato`) | `taglio` | `cut` |
| `leggi` | `lettura (consumi)` | `read` |
| `chiama` | `chiamata` | `call` |
| `ripiega` | `ripiego` | `downgrade` |

**Il confine, perche' la classe non diventi un permesso generico:** vale solo quando il verbo e il
sostantivo nominano lo stesso atto. Due parole italiane con sensi DIVERSI che finiscono sullo
stesso inglese restano un difetto, e la guardia `Collisione` di `scripts/rinomina.py` le ferma
quando si incontrano nello stesso file -- non perche' l'inglese coincida, ma perche' fondere due
identita' diverse e' peggio che non rinominare. Le coppie qui sopra non la fanno mai scattare per
un motivo strutturale, non per fortuna: verbo e sostantivo dello stesso atto non compaiono quasi
mai come due identificatori distinti nella stessa funzione, e se accadesse la guardia direbbe di
guardarli, che e' la risposta giusta.

## Le citazioni fra backtick seguono il codice

**La prosa italiana non si traduce -- ma un identificatore citato fra backtick in un commento o in
una docstring non e' prosa: e' un riferimento, e un riferimento a un nome che non esiste piu' e'
semplicemente falso.** Regola in vigore dal lotto 9 di Task 9, corretta subito dopo (review del
lotto 9) perche' la prima formulazione lasciava passare esattamente il caso che conta.

**Il confine e' «rese false da me», ovunque siano -- non «nel file che sto toccando».** La prima
stesura diceva «aggiorna quelle che tu stesso rendi false» e, subito dopo, «non andare a caccia di
quelle vecchie»: chi la leggeva capiva ragionevolmente «nel file che sto editando», e con quel
confine rinominare una funzione PUBBLICA lascia false per sempre tutte le citazioni che la nominano
altrove -- cinque, misurate dopo il lotto 9, in `casa/strumenti.py` e in
`static/config/memoria-route.js`, cioe' in un ambito gia' chiuso e nel frontend. Restano fuori solo
le citazioni gia' false PRIMA del proprio lotto: quelle vanno in un giro unico di fine fetta, e non
si vanno a cercare mentre si converte.

**Il criterio meccanico e' «ogni parola dentro ogni coppia di backtick», mai il contenuto intero.**
Confrontare l'intero contenuto dei backtick con l'elenco dei nomi rinominati non vede una citazione
che sia un'ESPRESSIONE: `` `indice is None` `` non combacia con `indice`, `` `turno=id_turno` `` non
combacia con `id_turno`, `` `_LIMITE_RICORDI_MOSTRATI = 200` `` non combacia con la costante.
Misurato dal vivo due volte: il lotto 9 aveva dichiarato di aver verificato tutte le citazioni del
proprio file e ne aveva mancata una **nello stesso file** (`handlers_memoria.py:118`); il lotto 10
ne ha lasciata una in un test (`tests/test_rotta_mcp.py:652`), trovata solo dal lotto 11 col
criterio corretto. Non e' distrazione: e' il criterio sbagliato.

**Il frontend conta, e il confine che ha fatto sfuggire la prima citazione non e' la cartella:
e' l'ESTENSIONE.** Le citazioni vivono anche nei commenti JavaScript, e questa riga diceva gia'
«la ricerca si fa su `hiris/` e `tests/` interi, non sui soli `.py`». Non e' bastato: il lotto 11
ha corretto `hiris/app/static/config/albero-route.js:147` e mancato il suo gemello in
`tests/js/dashboard-conoscenza.test.mjs:44`, perche' la scansione elencava le estensioni a mano
(`.py`, `.js`, `.css`, `.html`) e **`.mjs` non era nell'elenco** -- e i 24 file di `tests/js/` sono
tutti `.mjs`. Una regola giusta si e' fermata al primo confine di estensione, non al primo caso
difficile.

**La forma che regge:** si elencano le estensioni da ESCLUDERE (binari e immagini), non quelle da
includere -- misurato oggi, il progetto porta `py`, `mjs`, `js`, `yaml`, `css`, `html`, `md`,
`txt`, `sh`, e ogni elenco per inclusione ne dimentichera' una la prossima volta che ne nasce
un'altra.

**La protezione e' per la PROSA italiana, non per un identificatore nudo.** Un nome di funzione
scritto senza backtick in un commento -- `# vedi handle_get_memoria` -- e' formalmente esente da
questa regola e sostanzialmente falso allo stesso modo: si corregge. La regola dei backtick decide
cosa e' certamente un riferimento, non cosa e' lecito lasciare falso.

### Quali documenti si correggono, e quali sono verbali che non si toccano

**Aggiunto durante il Task 9 (lotto 12) su richiesta del coordinatore, dopo che la review aveva
trovato citazioni stantie anche sotto `docs/design/` e nessuna riga diceva cosa farne.** La regola
sopra («un identificatore fra backtick segue il codice») vale per i documenti VIVI, non per i
verbali.

- **Si correggono sempre, perche' descrivono cio' che il codice E' oggi**: `docs/GLOSSARIO.md`
  (questo documento -- «non e' storia: e' la regola», in testa), la specifica della fetta IN CORSO
  (`docs/design/<data>-<fetta>.md` finche' la fetta e' aperta), e `CLAUDE.md`.
- **Non si correggono mai, perche' sono il verbale di cio' che si e' deciso QUEL giorno**: ogni
  altro documento sotto `docs/design/`. Portano una data nel nome, ed e' quella la loro natura:
  `docs/design/2026-08-15-come-sta-la-casa.md` racconta la fetta del 15 agosto coi nomi del 15
  agosto. Correggerlo riscriverebbe la storia -- e la storia serve esattamente a spiegare perche'
  oggi il codice e' com'e'. Un verbale aggiornato non e' piu' un verbale.

Lo stesso vale per i rapporti sotto `.superpowers/`: si scrivono in coda, non si riscrivono a
monte -- salvo per correggere un dato MISURATO che si e' rivelato falso (un conteggio, un esito),
mai per allineare un nome.

## «Ambito chiuso» significa chiuso rispetto al glossario di QUEL giorno

**Aggiunto dopo la review del lotto 9, e non descrive un difetto da correggere: descrive come il
meccanismo e' fatto.** Un sottosistema «chiuso» non e' congelato. Non e' lo strumento ad
attraversare il confine -- `applica()` e' limitato dal `--percorso` che riceve -- **e' il glossario
a essere globale**: `Glossario.per(parola, ambito)` ignora del tutto l'ambito per una riga NUDA, e
le righe nude sono oltre 340 contro 13 qualificate.

**Conseguenza operativa, diretta e non teorica: ogni riga nuda nuova riapre tutti e sei gli ambiti
chiusi insieme.** E' gia' successo tre volte -- `carattere` (lotto 8) su `memoria/resolver.py`,
`richiesto` (lotto 9) su `azione/costruzione/mestiere.py`, `definizione` (lotto 10) su
`azione/verifica.py` -- e ogni volta l'unico contenimento e' stato
`tests/test_rinomina_applica.py::test_gli_ambiti_chiusi_restano_idempotenti`, che ha fatto il suo
lavoro. Ma un fatto che vive solo dentro un test lo conosce soltanto chi lo fa fallire: e' scritto
qui perche' lo si sappia PRIMA.

**Cosa si misura, prima di committare una parola nuova**: non il numero delle proposte, che cambia
a ogni lotto per ragioni innocue, ma **l'insieme dei FILE che lo strumento riscriverebbe** in
ciascuno dei sei ambiti chiusi, che deve restare identico a quello noto (oggi:
`memoria/resolver.py`, `azione/costruzione/composer.py`, `casa/strumenti.py`). Un file nuovo in
quell'insieme e' una parola che ha attraversato un confine: o la si corregge a mano nel file
toccato -- come e' stato fatto tutte e tre le volte -- o la parola non entra.

## Due difetti di composizione, e solo uno si puo' meccanizzare

**Aggiunto dopo la misura ordine-e-preposizioni del 31/08.** Quella misura ha letto uno per uno i
676 composti interamente inglesi di `hiris/app/` e ne ha trovati 25 difettosi (3,0% su 844
composti vivi). **Nessuno dei 25 sarebbe uscito rilanciando `scripts/rinomina.py`**: sono fatti di
parole gia' inglesi, e lo strumento non ha niente da tradurre. Ma i 25 non sono una cosa sola: sono
due difetti diversi, e si difendono in due modi diversi.

**① La giuntura italiana -- MECCANIZZABILE, e ora c'e' un cancello.** `_prompt_di_system`,
`area_del_device`, `behavior_loaded_il`, `state_e_cost`, `da_anchor`, `da_iso`/`a_iso`,
`da_ts`/`a_ts`: una preposizione (o un articolo, o una congiunzione) italiana che tiene insieme
parole inglesi. E' un fatto di FORMA -- la parola c'e' o non c'e' -- quindi un test la puo' vietare
per sempre, comprese le 11.266 righe dei sottosistemi che nessuno ha ancora aperto. Il cancello e'
`tests/test_preposizioni_italiane.py`, e porta scritte dentro le tre regole (forme piane, elisioni
solo davanti a vocale, `a` solo se non e' l'ultimo pezzo), le due forme escluse con la misura degli
usi inglesi veri (`in`, `per`), e cio' che non copre (i nomi `test_*`, il camelCase,
`hiris/app/static/` che e' JavaScript).

**② L'ordine invertito -- NON meccanizzabile, e il suo unico controllo e' la lettura.**
`bands_all` invece di `all_bands`, `reason_downgrade` invece di `downgrade_reason`, `lines_pool`
invece di `pool_lines`, `STATE_READABLE` invece di `READABLE_STATE`, `RETENTION_EXECUTIONS_S`
invece di `EXECUTIONS_RETENTION_S`, `target_ha` invece di `ha_target`.

**Perche' nessuna macchina lo puo' vedere**: gli stessi due pezzi inglesi sono corretti in
ENTRAMBI gli ordini, e quale sia quello giusto dipende da quale pezzo e' la **testa** del nome --
cioe' dal significato, non dalla forma. `state_class` e `class_state` sono due nomi diversi ed
entrambi grammaticali; `promise_tools` sono gli strumenti di una promessa e `tools_promise`
sarebbe la promessa di uno strumento. Riconoscere la testa vuol dire sapere di che cosa parla il
nome, ed e' esattamente cio' che questo strumento dichiara di non saper fare («**Non indovina**»,
docstring di `scripts/rinomina.py`).

**Che non si possa automatizzare non la rende meno vincolante**: la rende una regola che nessuna
macchina difende, e va detto. Il controllo e' la lettura, in due momenti: chi converte un file
rilegge OGNI suo identificatore composto con una sola domanda -- «qual e' la testa?» -- e la review
la rifa. La misura del 31/08 e' ripetibile ed e' il modo di rifarla su scala: si enumerano i
composti con `spezza()`, si separano quelli interamente inglesi, e si leggono tutti.

**Perche' la lettura distratta non basta**, misurato: `casa/nucleo.py:1572` dichiarava
`_pop(pool_name, lines_pool, pool_weights, reserve)` -- **due parametri su tre in ordine inglese e
uno in ordine italiano, nella stessa riga**. Nessuna delle review precedenti si e' fermata li',
perche' un solo nome fuori posto in mezzo a due giusti non stona abbastanza. La domanda va fatta a
ogni nome, non aspettata dall'occhio.

## Parole scartate durante l'estrazione

Una regola esclusa non e' silenzio, e' una decisione scritta. Lo script di estrazione (Step 1 del
piano) ha fatto uscire tre parole che **non richiedono nessuna decisione di rinomina**, perche' sono
gia' nella lingua di destinazione o sono una sigla, e sono state tolte a mano dall'elenco:

| parola uscita dallo script | perche' e' stata scartata |
|---|---|
| `backend` | e' gia' inglese -- corretto durante la review finale del ramo, la ragione precedente citava un file che non esiste (nessun file si chiama `backend*.py`, solo la cartella `backends/`): il singolare vive come identificatore vero, per esempio `nome_backend` (`llm_router.py:218,228,231,242,245,249`; era anche in `api/handlers_chat.py:302,303,305`, dove il Task 9 lotto 12 l'ha portato a `backend_name` -- il pezzo `backend` resta invariato, che e' il punto di questa riga), oltre che in prosa ovunque nel sottosistema |
| `sanitize` | e' gia' inglese, usata cosi' com'e' nel codice |
| `yaml` | e' una sigla di formato, non si traduce |
| `ha` | **e' la sigla di Home Assistant in dieci nomi su dodici, e il VERBO negli altri due -- quindi non si traduce mai, e si legge sempre.** I dieci: `ha_client` (109 siti), `ha_base_url`, `ha_config_dir`, `sanitize_ha_value`, `_ha_channel`, `_fingerprint_from_ha_state`, `ha_target`, `ha_fingerprints`, `HA_LINK_TYPE`, `_find_ha_config_dir` -- li' `ha` resta `ha`. I due: `ha_credenziale` (`decisione_modelli.py:653,717,736,755`, `ha_credenziale = bool(credenziali.get(pid))`) e `piano_ha_il_token`, dove `ha` e' il verbo «avere» e il gemello gia' inglese si chiama `_config_has_credential` (`api/handlers_models.py:369`) -- **non** `ha_credential`. Scritta qui il 31/08 dopo che la misura ordine-e-preposizioni ha trovato la trappola ARMATA in due documenti che avvertivano di non innescarla (la specifica della fetta e il docstring di `scripts/rinomina.py`, che portavano entrambi `ha_credenziale` come esempio del caso *Home Assistant*): stare qui significa che lo strumento non traduce MAI `ha` da solo, invece di non tradurlo solo perche' nessuno l'ha deciso. **Non significa che sia protetto il COMPOSTO**: `classifica('ha_credenziale')` restituisce ancora `Proposta(suggerito='ha_credential')`, cioe' esattamente il nome sbagliato -- perche' un composto si compone dai pezzi tradotti E da quelli non tradotti. La rete vera e' un'altra, ed e' sufficiente: **lo strumento propone e si ferma**, non applica mai un composto, e questa riga dice a chi guarda la proposta cosa scrivere. Distinguere le due cose e' la differenza fra una protezione e una speranza. Chi convertira' `decisione_modelli.py` deve scrivere `has_credential`, e la chiave JSON `"ha_credenziale"` (letta da `static/config/models-route.js`, sei siti) resta com'e' finche' non si convertono i campi |
| `grandezza` | **contratto col modello, come i 13 nomi degli strumenti: e' una CHIAVE dello schema di `REMEMBER_TOOL_DEF`** (`casa/strumenti.py:397`, dentro `input_schema.properties`), riletta col suo nome esatto quando l'argomento torna indietro (`casa/strumenti.py:1430`, `arguments.get("grandezza")`), e ripetuta nella descrizione che il modello legge. Le stringhe che il modello legge non si toccano mai -- e questa e' una di quelle, non un identificatore Python. **Sta QUI e non fra le parole non ancora decise perche' «non decisa» significa invisibile, non protetta**: `classifica('grandezza')` tornava `None` solo perche' nessuno l'aveva scritta, e il giorno in cui qualcuno la decidesse per un'altra ragione (e' un parametro keyword-only vero di `MemoryStore.remember` e di `memoria/interpretazione.py::deduci_unit`/`validate`) niente lo fermerebbe. Scritta qui, lo strumento la salta per costruzione e ignora anche un'eventuale riga futura. Rilievo della review del lotto 9: la ragione registrata allora era l'asimmetria fra `def` e chiamata dentro `memoria/` -- vera, ma **evapora** il giorno in cui si riaprisse `casa/`; questa no |

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
| `lette` | `letto` |
| `sconosciuta` | `sconosciuto` |
| `effettiva` | `effettivo` |
| `identificativo` | `identificatore` |
| `disabilitate` | `disabilitato` |
| `disabilitata` | `disabilitato` |
| `nascoste` | `nascosto` |
| `nascosta` | `nascosto` |
| `assegnate` | `assegnato` |
| `dichiarata` | `dichiarato` |
| `propria` | `proprio` |
| `viva` | `vivo` |
| `candidata` | `candidato` |
| `nostre` | `nostro` |
| `vivi` | `vive` |
| `citate` | `citato` |
| `sconosciute` | `sconosciuto` |
| `campi` | `campo` |
| `modi` | `modo` |
| `nuove` | `nuovo` |
| `problemi` | `problema` |
| `pulita` | `pulito` |
| `correggibili` | `correggibile` |
| `aggiornamenti` | `aggiornamento` |
| `correzioni` | `correzione` |
| `ignorati` | `ignorato` |
| `letta` | `letto` |
| `disponibili` | `disponibile` |
| `verificabili` | `verificabile` |
| `nostri` | `nostro` |
| `strumento` | `strumenti` |

Le righe sopra (dopo le tre della spec) sono **variazioni di genere**, non singolare/plurale: lo
script segnala la forma flessa come composto/proposta invece di applicarla da sola (la stessa
`Proposta` di un plurale non aliasato), e senza una riga qui resterebbero invisibili per sempre --
non un composto (`_radici_plurali` non copre il genere), non una parola gia' decisa. Scoperte in
`casa/anagrafe.py` (Task 8, lotto 4) con la scansione dedicata sull'AST che il criterio di fine
richiede -- la stessa enumerazione gia' raccomandata dal Task 8 per non fidarsi del solo dry-run.

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
| ancora (api) | la stessa `ancora (memoria)` qui sopra, letta dal confine `api/`: `handlers_memoria.py::_resolve_tether` riceve lo stesso dizionario `{"tipo": ..., "riferimento": ...}` che `memoria/interpretazione.py` costruisce -- la stessa riga che `riga (api)` (Task 9, lotto 2) rende raggiungibile anche da questo ambito. **Attenzione, e la prima stesura lo taceva: `api` porta ENTRAMBI i sensi di `ancora`, non uno solo.** `api/handlers_usage.py:119,120,121,153,218` usa l'ancora dei CONSUMI (`ancora (consumi) -> anchor`), non questa. Questa riga non sbaglia oggi solo perche' `consumi/` e' stato convertito PRIMA, e quelle cinque occorrenze si scrivono gia' `anchor`: con un altro ordine dei lotti sarebbe una regola che sbaglia in silenzio, ed e' esattamente il caso che «Il limite della qualificazione per ambito» descrive (due sensi DENTRO lo stesso ambito, che una riga per ambito non sa distinguere). Chi incontra `ancora` nuda in un file di `api/` guarda il file prima di fidarsi di questa riga: se e' `handlers_usage.py` o un suo parente, e' `anchor` | tether | ~ parziale |
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
| guarda (cervello) | il verbo con cui l'osservatore si aggancia al rubinetto dei cambi di stato e delle condizioni di sistema e li annota cosi' come sono, senza interpretare nulla -- il meccanismo centrale della classe che lo fa (`Watcher`, ex `Osservatore`) | watch | ✓ arriva |
| impostazioni | i valori che governano il comportamento della chat -- il prompt di sistema, i giorni di conservazione della cronologia -- caricati da un file proprio e gia' completi al momento della costruzione, cosicche' un valore mancante non sia mai un caso da gestire a valle | settings | ✓ arriva |
| indice | la struttura, costruita una sola volta dai nomi e dagli alias dichiarati nell'anagrafe, che trova i riferimenti che un testo libero puo' significare -- dichiarando l'ambiguita' quando piu' di uno corrisponde -- e conferma se un identificatore proposto esiste davvero | lookup | ✓ arriva |
| instradamento | la decisione, presa in un punto solo per ogni turno, se a rispondere sia il canale a forfait o quello a consumo -- e, se serve scendere al secondo, se e' una configurazione scelta dall'utente (silenziosa) o un ripiego vero da annunciare sempre | steering | ✓ arriva |
| intento | la struttura con cui una richiesta di nuova costruzione descrive se stessa -- che cosa la fa scattare, quali passi compie, quali stati verifica, quali parametri porta, se va riusata o si ripete, se e' stata chiesta esplicitamente -- da cui si decide quale oggetto serve davvero | intent | ✓ arriva |
| interpretazione | il linguaggio chiuso a quattro caselle -- a chi si riferisce, cosa chiede, quando vale, che forza ha -- con cui il modello propone una lettura strutturata di una frase ricordata, scartando cio' che non riconosce invece di inventarlo | interpretation | ~ parziale |
| invocazione | il risultato completo di un singolo lancio del processo che parla col modello -- il codice di uscita, l'output gia' ripulito dai segreti, il flusso gia' interpretato -- pensato perche' lo stesso lancio puo' avvenire due volte nello stesso turno senza che i due tentativi vengano letti in due modi diversi | invocation | ~ parziale |
| legame | la relazione fra una cosa della casa e le altre che la nominano o dove sta, nel vocabolario dei quattordici tipi che Home Assistant riconosce per l'API di ricerca -- il tipo di legame, non il legame stesso: `legami()` ("I nomi degli strumenti") ne restituisce l'elenco, questa e' la parola con cui una singola voce di quell'elenco si nomina | link | ~ parziale |
| letto | il participio passato di `leggi`: non l'atto di leggere ma il RISULTATO, cio' che e' stato letto e tenuto -- `sistema_letto`, `specchio_letto`, `comportamento_letto_il`. Il glossario aveva risolto sia `leggi` sia `letto` con lo stesso inglese (`read`): la guardia sulle collisioni dello strumento di rinomina (Task 4bis) l'ha trovato prima che potesse fondere l'atto e il risultato in un nome solo, su `casa/strumenti.py` e `azione/costruzione/officina.py`, dove le due forme convivono. `leggi` resta `read`: e' il verbo, il nome giusto per un metodo (`casa.leggi()`). `letto` e' il participio, quindi diventa un aggettivo in inglese: `loaded` | loaded | ✓ arriva |
| lettura (casa) | trasforma il testo di un file di configurazione di Home Assistant nella struttura che rappresenta, sollevando quando il testo e' davvero malformato invece di restituire un risultato vuoto indistinguibile da un file senza contenuto | parse | ✓ arriva |
| lettura (consumi) | i token che una chiamata ha RICEVUTO dalla cache del provider invece di generarli da capo -- un significato distinto da «trasformare il testo di un file di configurazione» (la riga sopra): scoperto rinominando `consumi/` (Task 4), dove applicare alla cieca `parse` avrebbe prodotto un nome semanticamente falso per `cache_lettura`. La stessa codebase aveva gia' scelto `cache_read`/`cache_write` altrove (`backends/pricing.py`) prima che questo glossario lo dicesse | read | ✓ arriva |
| memoria | il sottosistema che conserva per sempre le frasi esatte che una persona ha detto sulla sua casa insieme a come HIRIS le ha interpretate, correggibile senza toccare le parole originali, senza anonimizzazione e senza scadenza | memory | ~ parziale |
| mestiere | la funzione pura che, davanti a una richiesta, decide se serve un'automazione, uno script, una scena o una combinazione delle tre, e dice anche perche' -- consigliando senza mai bloccare chi insiste per un'altra scelta | advisor | ✓ arriva |
| migrazione | la copia, fatta una volta sola e segnata perche' non si ripeta, di un valore che viveva nello schema delle opzioni dell'add-on verso l'archivio proprio di HIRIS, cosi' che togliere l'opzione dallo schema in un rilascio successivo non ne faccia sparire il valore in silenzio | migration | ~ parziale |
| note (casa) | l'aggettivo "conosciuto/e", non il sostantivo inglese "notes": `{entity_id: entita}` costruito dai registri grezzi dell'anagrafe, usato per guardare se un id che Home Assistant riporta corrisponde a un'entita' GIA' CONOSCIUTA da noi, dentro il confronto (`casa/anagrafe.py::compare_with_home_assistant`/`_compare_area`). **Qualificato per collisione fra ambiti, non dentro `casa/`**: `azione/costruzione/officina.py:357,381,394` ha gia' un identificatore bare `note` con l'ALTRO senso -- il sostantivo inglese "note" (un messaggio d'errore accodato da `_disfa()`), gia' valido inglese per coincidenza. Decisa a mano durante la conversione di `anagrafe.py` (lotto 5), applicata subito col nome giusto (`known`) senza mai passare da una riga di glossario -- scritta ora, a conversione fatta, perche' un lotto futuro che aggiungesse `note -> known` nuda romperebbe silenziosamente `officina.py` | known | ✓ arriva |
| notevole | un'etichetta calcolata al momento della composizione, non conservata, che segnala le cose il cui stato attuale si scosta dalla normalita' -- acceso, aperto, in allarme -- perche' compaiano subito nel riepilogo | highlight | ✓ arriva |
| nucleo | il testo unico e sempre presente che chi ragiona riceve a ogni messaggio, ottenuto comprimendo sotto un tetto di caratteri la casa, cio' che fa da sola e i ricordi, uguale per chiunque lo consulti | briefing | ✓ arriva |
| officina | il modulo gemello di quello dei servizi ma per l'altro canale: compone e scrive su Home Assistant automazioni, script, scene e helper in due tempi -- una proposta archiviata, poi una scrittura che avviene solo con l'approvazione di un umano -- e disfa quanto ha appena creato se il passo finale viene rifiutato | workshop | ~ parziale |
| oggetti | il fatto interpretato che l'aggregazione ricava da un periodo di grezzo, nella forma che il suo genere impone -- un intervallo con inizio e fine per la maggioranza, una condizione che puo' restare aperta per un guasto, una quantita' che riassume l'intera giornata per il bilancio -- mai il dato grezzo stesso | fact | ✓ arriva |
| origine | classifica chi ha richiesto un'operazione di costruzione -- un umano che ha appena cliccato sulla pagina, oppure il modello durante un turno -- e decide se un controllo pensato per trattenere il modello si applica o si scavalca | actor | ~ parziale |
| orologio | il battito che, ricevuto un istante dall'esterno, scorre le promesse scadute e porta ciascuna a termine senza mai fermarsi per il guasto di una singola, cosi' che le altre dello stesso giro vengano comunque servite -- **corretto in fix round 1:** `clock` era stato dichiarato pulito per errore (il report diceva "una sola occorrenza, in prosa"; sono due, e la seconda -- `request.app.get("_clock")` in `api/handlers_reasoning.py:12` -- e' una chiave di dizionario, contesto non-prosa che la regola meccanica blocca. Non ho fatto eccezione: e' lo stesso standard gia' applicato a `turn`/`wake` in questo stesso lotto, bloccati per identificatori altrettanto estranei al sottosistema che stavo nominando. Nuovo inglese: `heartbeat`, pulito (`hiris/` ne ha una sola occorrenza, dentro un commento non correlato su un keep-alive SSE, tollerata) | sweeper | arbitrato del proprietario |
| osservatore | il modulo che si aggancia al flusso dei cambiamenti di stato e li annota cosi' come sono, applicando solo il filtro fisso dei confini, senza interpretare nulla | watcher | ✓ arriva |
| osservazioni | il deposito unico dove finiscono sia i cambiamenti annotati cosi' come sono sia i fatti compiuti che se ne ricavano, la fonte a cui un domani attingera' chi analizza | observations | ✓ arriva |
| pavimento | l'insieme fisso di classi che entra comunque, qualunque cosa dica l'obiettivo del momento: quest'ultimo puo' solo allargarlo, mai restringerlo sotto quella soglia | baseline | ~ parziale |
| piano (abbonamento) | il canale a forfait alimentato dall'abbonamento Claude Max, riconosciuto dalla sola presenza di una credenziale dedicata -- mai dal suo valore, cosi' che nessun chiamante possa stamparla per sbaglio in un log -- **`(abbonamento)` NON e' un ambito reale (nessuna cartella `hiris/app/abbonamento/` esiste, e non e' un refuso da correggere in un nome di cartella vero come `riga (nucleo) -> riga (casa)` qui sopra): il senso *subscription* di `piano` non vive in un sottosistema unico, e' sparso fra file di radice e `api/` (`api/handlers_chat.py`, `api/handlers_models.py::_clean_subscription_model`, `migrazione_opzioni.py`, `agent/runner.py`, `instradamento.py`). Questa riga resta di proposito irraggiungibile da `Glossario.per("piano", ambito)` per qualunque `--ambito` reale: e' una documentazione del significato deciso, da applicare A MANO ovunque questo senso di `piano` compaia (sempre dentro un composto finora, mai nudo -- verificato con `tokenize` su `hiris/app`), non un'automazione da riattivare qualificandola** | subscription | ✓ arriva |
| piano (casa) | il livello piu' alto della gerarchia della casa, letto dal registro che Home Assistant stesso tiene per i livelli verticali di un edificio, sopra le aree e i dispositivi | floor | ~ parziale |
| plance | le pagine visive che Home Assistant lascia comporre all'utente stesso, con percorso, titolo, modalita' e viste proprie, lette dallo stesso catalogo con cui l'installazione le elenca | dashboards | ✓ arriva |
| ponte | il percorso che risponde a un turno usando l'abbonamento a forfait del modello invece della chiave a consumo, mettendo in coda il lavoro per un processo separato che lo prende in carico e lo restituisce quando e' pronto | bridge | ~ parziale |
| porta | il modulo che e' l'unico punto del prodotto da cui parte, verso Home Assistant, una chiamata di servizio, e che ne osserva l'esito aspettando l'annuncio del cambiamento di stato prima di dichiarare cosa e' successo davvero | actuator | ~ parziale |
| promessa | l'impegno per un momento futuro che l'utente ha chiesto -- fare qualcosa, oppure controllare qualcosa e riferire -- con la sua scadenza, la sua tolleranza al ritardo, e lo stato con cui si conclude | promise | ✓ arriva |
| provenienza | se un valore osservato viene da una regola fissa del prodotto (il pavimento, mai tolto) o da una scelta dell'obiettivo del momento (aggiunto, puo' essere tolto) -- lo stesso principio classifica anche una direzione dell'energia (dichiarata dalla dashboard dell'utente, o dedotta dall'integrazione quando la dichiarata tace) -- aggiunta dal Task 6, non ancora passata dalla prova del lettore nuovo | provenance | ~ non provato |
| registro | lo specchio aggiornato di cosa Home Assistant sa fare in questa casa, servizio per servizio e con i relativi parametri -- non un catalogo scritto da HIRIS, ma la copia di cio' che Home Assistant stesso dichiara di poter eseguire | registry | ~ parziale |
| riconoscitore | il modulo che decide a quale parte della casa si riferisce una frase scritta, confrontandola con nomi e alias dichiarati e restringendo poi cio' che il modello propone a cio' che esiste davvero nell'anagrafe | resolver | ✓ arriva |
| ricordi | le frasi esatte, cosi' come sono state dette, che una persona ha affidato a HIRIS -- la verita' che non si tocca mai, nemmeno quando la sua lettura viene corretta | memories | ~ parziale |
| riferimento (casa) | l'insieme dei dati con cui si interpreta ogni altra misura della casa -- unita', ora locale, valuta, lingua, paese, versione dell'installazione -- distillato una volta e mai cancellato da una lettura vuota, perche' quello di ieri resta quello giusto finche' non arriva un valore nuovo (`casa/anagrafe.py::sistema_di_riferimento`) -- **corretto in fix round 2 (rilievo del reviewer): l'inglese era `frame`, sbagliato.** Misurato con token reali (`tokenize.NAME`, non un grep sul file intero: prosa e stringhe escluse) su ogni file di `casa/`: il senso *frame* qui descritto vive **solo dentro composti** -- `sistema_di_riferimento` (10 occorrenze, in `anagrafe.py`/`archivio.py`/`nucleo.py`/`strumenti.py`) e `_CAMPI_RIFERIMENTO`/`_migrazione_3_entita_di_riferimento_dell_area` (4, in `anagrafe.py`/`archivio.py`) -- mentre `riferimento` **nudo** (53: 39 in `domande.py`, 14 in `strumenti.py`) porta il senso opposto, quello di `riferimento (memoria)` sotto (l'id a cui punta un'ancora). Lo strumento propone sempre i composti invece di applicarli da solo, quindi il senso sbagliato non passa mai dall'automatismo su quella forma -- ma la parola nuda si', e vince per numero (53 contro 14): l'inglese di questa riga e' quello del senso nudo, `reference`, non `frame`. **Chi convertira' `casa/` non trovera' un suggerimento pronto per i tre composti**: lo strumento comporra' `sistema_di_reference` pezzo per pezzo, che e' sbagliato -- serve una decisione umana esplicita (`system_frame` o simile), proprio perche' quei tre nomi portano l'altro senso. Vedi «Il limite della qualificazione per ambito» per il limite di fondo che questo caso rivela | reference | ✓ arriva |
| riferimento (memoria) | l'identificatore a cui punta un'ancora -- un'area, un'entita', un dispositivo -- un significato generico, distinto dal "sistema di riferimento" per interpretare le misure (riga sopra). Scoperto rinominando `memoria/` (Task 5, review): applicare alla cieca `frame` -- l'inglese di `riferimento (casa)` al momento di questa scoperta -- avrebbe prodotto `lookup.verify(tipo, frame)`, un nome che allude a un sistema di unita'/locale per qualcosa che e' solo l'id referenziato. La stessa parola, con lo stesso significato di memoria, vive gia' anche in `casa/domande.py` (non ancora convertito): misurata con token reali in fix round 2, sono 39 occorrenze nude (piu' 14 in `casa/strumenti.py`, vedi la misura completa in `riferimento (casa)`, sopra) -- non piu' "almeno 8 punti" come stimato qui in origine. **Corretto in fix round 2: `riferimento (casa)` e' stato a sua volta corretto in `reference`** (lo stesso di questa riga), proprio perche' il senso nudo -- quello di questa riga -- domina numericamente in `casa/`; quando quell'ambito verra' convertito, il senso nudo non avra' quindi bisogno di una qualificazione diversa da questa, ma i tre composti che portano ancora il senso *frame* (`sistema_di_riferimento` e affini) sì -- vedi «Il limite della qualificazione per ambito» | reference | ✓ arriva |
| rifiuto | una risposta negativa che porta sempre, insieme al no, il motivo per cui non si procede -- mai un diniego silenzioso -- usata sia per bloccare la scrittura di un campo non valido prima che tocchi il disco, sia per fermare un comando o una costruzione prima che tocchino Home Assistant | rejection | ✓ arriva |

> **Decisione umana per i tre composti che portano il senso *frame* di `riferimento (casa)`**
> (annunciata come dovuta sopra, presa nel Task 8 lotto 4 convertendo `anagrafe.py`): il nome
> **non** e' `system_frame` (l'esempio provvisorio della nota) ma **`reference_frame`**, perche'
> `HomeSpaceStore.replace`/`.reference_frame` (`casa/archivio.py`, gia' convertito nel Task 8 lotto
> 2) usava gia' quel nome per lo stesso identico concetto -- la funzione che lo PRODUCE
> (`anagrafe.py`) doveva chiamarsi come il posto che lo CONSERVA, non inventare un secondo nome per
> lo stesso fatto (fondamenta: una sola casa). Applicato: `sistema_di_riferimento` (funzione) ->
> `reference_frame`, `_CAMPI_RIFERIMENTO` -> `_REFERENCE_FRAME_FIELDS`. Il terzo composto citato,
> `_migrazione_3_entita_di_riferimento_dell_area`, non e' ancora stato incontrato nel Task 8 (vive
> in un file non ancora convertito): stessa direzione quando arrivera' il suo turno.
| ripiego | il passaggio, dichiarato sempre e mai silenzioso, con cui un turno che non ha potuto essere servito dal canale a forfait viene rifatto da capo su quello a consumo -- uno stato non definitivo di un lavoro in coda, distinto da uno riuscito, scaduto o fallito, perche' resta da chiudere finche' non arriva una risposta | downgrade | ✓ arriva |
| schedulatore | il sottosistema che tiene le promesse fatte per un momento futuro: le risveglia quando arriva l'ora, ne porta a termine il compito o la domanda, e registra sempre come e' andata | keeper | ~ parziale |
| scrittura | i token che una chiamata ha fatto CREARE nella cache del provider, il lato opposto di `lettura (consumi)` -- mai aggiunta finche' non serviva: la sua assenza teneva `cache_scrittura` in italiano nella firma pubblica di `consumi/`, accanto a `cache_read` gia' inglese, i due lati della stessa coppia in due lingue | write | ✓ arriva |
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
| turno | il singolo scambio col modello che si apre quando una promessa che deve solo controllare si risveglia: puo' usare solo strumenti di lettura e finisce esclusivamente quando chiama lo strumento di chiusura obbligatorio -- oppure, se le risposte passano dalla catena esterna, si affida alla coda persistente invece di aspettare (vedi la nota su `ReasoningQueue`, sotto la tabella) -- **`turni` in `api/handlers_impostazioni.py::validate` (Task 9, lotto 8) NON e' questo concetto**: e' il conteggio di `max_chat_turns` (gia' inglese con la parola "turns"), non lo scambio col modello del reasoning delle promesse. Deciso a mano `turni -> turns`, MAI applicato alla cieca il suggerimento meccanico (`exchange`, questa riga). **Non qualificare `turno (api)`**: la collisione e' di SENSO, non di ambito -- `api/handlers_chat.py` usera' `turno` nel senso VERO di questa riga, nello stesso ambito `api` di `handlers_impostazioni.py` -- una riga per ambito qui risolverebbe meta' dei casi e sbaglierebbe l'altra meta'. `classifica('turni','api')` resta `Proposta(suggerito='exchange')` di proposito: e' la forma corretta, decidere ogni occorrenza guardando il codice, non un'automazione da attivare | exchange | ~ parziale |
| verdetto | l'oggetto che la funzione di controllo restituisce: un booleano che dice se il comando puo' procedere, il motivo quando non puo', e -- quando puo' -- dominio, servizio ed entita' toccate, comprese quelle esplicitamente escluse | verdict | ✓ arriva |
| verifica (azione) | la funzione pura che esamina un comando proposto contro cio' che Home Assistant sa fare e contro lo stato vivo della casa, e decide se puo' procedere -- mai i valori dei parametri, mai le capacita' fini di un dispositivo, solo dominio, servizio e bersaglio (`azione/verifica.py`) | verification | ✓ arriva |
| verifica (memoria) | il metodo di `Indice`/`Lookup` che controlla se l'identificatore che il modello ha proposto esiste davvero nell'anagrafe, con quel tipo (`Indice.verifica`, ora `Lookup.verify`) -- un VERBO (un'azione: "verifica che..."), non il sostantivo che descrive il modulo della riga sopra. Scoperto rinominando `memoria/` (Task 5, review): applicare alla cieca `verification` avrebbe prodotto `lookup.verification(tipo, riferimento)`, grammaticalmente sbagliato per un metodo che si chiama come un imperativo | verify | ✓ arriva |
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
> Stesso ragionamento, dedotto con lo stesso criterio, per `segno` (da `_MIGRATION_FLAGS`): i
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
> (`api/handlers_models.py:37`), `def _clean_bridge(raw)` (`api/handlers_models.py:139`), piu'
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
> `_STATI_ATTIVI` (`casa/nucleo.py:182`) e `_STATI_INTEGRAZIONE_ROTTA`
> (`casa/nucleo.py:821`) / `_TRANSIENT_INTEGRATION_STATES` (ex `_STATI_INTEGRAZIONE_TRANSITORI`, rinominata dal Task 6, `cervello/osservatore.py:31`), tutte
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
| affidabile | reliable |
| aggiorna | refresh |
| aggiornamento | update |
| aggiornato | updated |
| aggiungi | add |
| agisci | act |
| albero | tree |
| altro | other |
| ambiente | environment |
| ambito | scope |
| annota | record |
| annotazione | annotation |
| anteprima | preview |
| aperto | open |
| applica | apply |
| area | area |
| argomento | argument |
| assegnato | assigned |
| assembla | assemble |
| assicura | ensure |
| attesa | pending |
| attivo | active |
| attributo | attribute |
| automazione | automation |
| avviso | notice |
| blocco | block |
| cambiato | changed |
| cambio | change |
| campione | sample |
| campo | field |
| candidato | candidate |
| carattere | character |
| carica | load |
| cartella | folder |
| catalogo | catalog |
| categoria | category |
| chiama | call |
| chiamata | call |
| chiave | key |
| chiudi | close |
| citato | cited |
| classe | class |
| coda | tail | **due sensi vivi, e quello che lo strumento applica da solo e' il minoritario -- quarto caso della famiglia gia' descritta in «Il limite della qualificazione per ambito» (Task 9, lotto 12).** `tail` e' giusto per `agent/runner.py:1559` (`coda = stdout.strip()[-200:]`, l'ultimo pezzo del flusso letto) e per i due `_coda` di `tests/test_strumenti_al_ponte.py` e `tests/test_token_interno.py`. Ma in `api/handlers_chat.py::_downgrade_to_chain` e nei quattro file di test che la nominano (`test_reasoning_queue.py`, `test_instradamento.py::_CodaFinta`, `test_promessa_dal_ponte.py`, `test_schedulatore_turno.py`) `coda` e' la CODA DI LAVORO, cioe' `ReasoningQueue`: `tail = request.app["reasoning_queue"]` sarebbe un nome che mente. Qualificare per ambito non aiuta -- i due sensi convivono dentro `agent/` come dentro `tests/` -- e nemmeno la forma li separa: sono entrambi NUDI, che e' esattamente il caso peggiore descritto per `fuori (casa)`. Si decide occorrenza per occorrenza guardando il codice: `queue` quando e' `ReasoningQueue` (il nome che l'app usa gia' nella chiave `reasoning_queue` e nella classe), `tail` quando e' la coda di una stringa |
| codice | code |
| colonna | column |
| configurazione | configuration |
| confronta | compare |
| confronto | comparison |
| conoscenza | knowledge |
| conosciuto | known |
| conservazione | retention |
| consumi | usage |
| conta | count |
| conteggio | counts |
| contenuto | content |
| coppia | pair |
| corpo | body |
| correggibile | correctable |
| corrente | current |
| correzione | correction |
| costo | cost |
| crea | create |
| credenziale | credential |
| dati | data |
| dedotto | deduced |
| denominatore | denominator |
| definizione | definition |
| dettaglio | detail |
| diagnosi | diagnosis |
| dichiara | declare |
| dichiarato | declared |
| differenza | difference |
| dimensione | dimension |
| disabilitato | disabled |
| disponibile | available |
| dispositivo | device |
| divergenza | divergence |
| dominio | domain |
| dopo (casa) | after |
| dove | where |
| effettivo | actual |
| elenca | list |
| elencato | listed |
| elenco | list |
| entita | entity |
| episodio | episode |
| errore | error |
| escluso | excluded |
| esecuzione | execution |
| eseguito | executed |
| esistente | existing |
| eta | age |
| etichetta | label |
| evento | event |
| fallito | failed |
| fascia | band |
| finale | final |
| finestra | window |
| fonte | source |
| forma | form |
| frase | phrase |
| fresco | fresh |
| fuori (casa) | outside |
| gerarchia | hierarchy |
| giorno | day |
| giro | round |
| grana | granularity |
| gratuito | free | **`free` e' preso da QUESTO senso -- «senza costo» -- e non e' disponibile per `libero`, «non vincolato».** Misurato nel lotto 14 (`proxy/_sanitize.py`): `MAX_TESTO_LIBERO` andava all'inglese e il suggerimento meccanico era `max_text_libero`, meta' nome. Scrivere `libero -> free` avrebbe messo due parole italiane di senso diverso sullo stesso inglese in modo PERMANENTE -- la collisione che `Collisione` ferma dentro un file, resa regola. Risolto riusando il nome dell'interfaccia che la costante alimenta (`sanitize_ha_free_text` -> `MAX_FREE_TEXT`), e `libero` resta undecided: chi la incontra decide guardando il codice, non traducendo |
| guasto | fault |
| identificatore | identifier |
| identita | identity |
| ignorato | ignored |
| illeggibile | unreadable |
| impronta | fingerprint |
| inaffidabile | unreliable |
| incompleto | incomplete |
| individuale | individual |
| ingresso | input |
| iniziale | initial |
| inizio | start |
| innesca | trigger |
| integrazione | integration |
| interno | internal |
| intero | integer |
| invalida | invalidate |
| inventario | inventory |
| irraggiungibile | unreachable |
| istante | instant |
| lacuna | gap |
| leggi | read |
| leggibile | readable |
| lettore | reader |
| limite | limit |
| locale | local |
| loro (casa) | their |
| lunghezza | length |
| mancante | missing |
| mantieni | keep |
| massimo | maximum |
| messaggio | message |
| metodo | method |
| minimo | minimum |
| misura | measurement |
| modelli | models |
| modello | model |
| modo | mode |
| momento | moment |
| motivo | reason |
| nascosto | hidden |
| negativo | negative |
| nodo | node |
| nome | name |
| normalizza | normalize |
| nostro (casa) | our |
| nota | note |
| notifica | notification |
| numeratore | numerator |
| nuovo | new |
| oggetto | object |
| oggi | today |
| ogni | every |
| opzioni | options |
| ora | hour |
| ordine | order |
| ordinato | sorted |
| ottieni | get |
| parte | part |
| percorso | path |
| peso | weight |
| piattaforma | platform |
| picco | peak |
| plurale | plural |
| portatore | carrier |
| posizione | position |
| pota | prune |
| prefisso | prefix |
| predefinito | default |
| principale | main |
| problema | problem |
| programma | schedule |
| proponi | propose |
| proposta | proposal |
| proprio | own |
| protagonista | protagonist |
| protocollo | protocol |
| pulisci | clean |
| pulito | cleaned |
| punto | point |
| quale | which |
| quando | when |
| quante | count |
| raggruppa | group |
| gruppo | group |
| raggruppato | grouped |
| rango | rank |
| registra | log |
| resto | rest |
| restrizione | restriction |
| richiesta | request |
| richiesto | requested |
| ricordo | memory |
| ricostruisci | rebuild |
| riepilogo | summary |
| rifiuta | reject |
| ripiega | downgrade |
| riga | row |
| riga (api) | row |
| riga (casa) | line |
| rileggi | reread |
| ripara | repair |
| ripristina | restore |
| riserva | reserve |
| risolto | resolved |
| risolvi | resolve |
| risposta | answer | **`answer` e `response` non sono un doppione: sono due cose, e a separarle e' la legge del confine.** `answer` e' il testo che il modello produce -- DOMINIO, e il dominio prende il nome che il glossario decide (cosi' lo chiamano gia' `schedulatore/turno.py` e `schedulatore/sweeper.py`). `response` e' il `web.Response` di aiohttp -- CONFINE, e il confine prende il nome del sistema esterno, come `entity`, `state`, `unit`, `domain`. Convivono nello stesso file (`api/handlers_chat.py`: `answer` in `_downgrade_to_chain`, `response` in `handle_chat_reply_poll` e nel ramo sincrono di `handle_chat`) ed e' corretto cosi'. La distinzione non era scritta da nessuna parte, e senza di lei il primo lettore la scambia per due nomi della stessa cosa |
| risultato | result |
| ritardo | delay |
| rivendica | claim |
| rotta (proxy) | route | **La riga che sarebbe costata piu' cara di tutta la fetta, e non perche' lo strumento sbagli: perche' `rotta` e' un OMOGRAFO vero dell'italiano** -- participio di «rompere» e sostantivo «percorso». Su `proxy/ha_client.py:423` lo strumento propone `_rotta_config -> broken_config`, e quel nome **direbbe l'opposto del vero**: quella funzione compone l'URL della rotta di configurazione, e lo dice il suo stesso docstring («L'URL della rotta di configurazione, oppure il motivo del rifiuto»). Non e' un suggerimento storpiato che salta all'occhio come `metti_da_part_l_store_unreadable`: e' **plausibile**, e sarebbe passato in review. **Misurato su tutti gli identificatori del repo che contengono il pezzo `rotta`**: uno in `hiris/app` (`_rotta_config`, senso PERCORSO) e circa 130 nei test (`ROTTA`, `rotta`, `rotta_senza_archivi`, `_Rotta`, tutti senso PERCORSO) contro **UNO** nel senso participio (`porta_rotta`, `tests/test_azione_porta.py:986`). La riga nuda `broken` descrive quindi il senso MINORITARIO, ed e' il verso in cui un'applicazione cieca fa piu' danno. Qualificando `(proxy)`, la riga nuda si spegne per ogni altro ambito (vedi «Il limite della qualificazione per ambito»): e' voluto -- meglio non rinominare che rinominare col senso sbagliato -- e il giorno in cui si convertira' `tests/` va qualificata anche li', guardando ogni occorrenza |
| rotta (participio) | broken | **Annotazione, non una riga raggiungibile**: `(participio)` non e' un ambito reale e nessun `--ambito` la trovera' mai, esattamente come `piano (abbonamento)`. Serve a tenere scritto il senso -- `porta_rotta` e' una porta GUASTA -- accanto a quello che gli somiglia, perche' chi legge solo la riga giusta non capisce perche' esiste. Si applica a mano, se mai servira' |
| sanificato | sanitized |
| scadenza | deadline |
| scegli | choose |
| scelto | chosen |
| scena | scene |
| sconosciuto | unknown |
| scritto | written |
| scrivi | write |
| secondo | second |
| segna | mark |
| semina | seed |
| senza (casa) | without |
| serie | series |
| servizio | service |
| severita | severity |
| sezione | section |
| sicurezza | safety |
| significato | meaning |
| singolare | singular |
| sistema | system |
| soggetto | subject |
| soglia | threshold |
| sostituisci | replace |
| stampa | print |
| statistiche | statistics |
| stato | state |
| successivo | next |
| suffisso | suffix |
| suggerimento | suggestion |
| taciuto | silenced |
| tagliato | cut |
| taglio | cut |
| termine | term |
| testo | text |
| tipo | type |
| titolo | title |
| totale | total |
| tracciato | tracked |
| tradotto | translated |
| traduci | translate |
| traduzione | translation |
| troncato | truncated |
| trova | find |
| trovato | found |
| tutte | all |
| unita | unit |
| valida | validate |
| via | route | **decisa nel Task 9, lotto 12, dopo che era stata scelta a mano senza riga** (`_via -> _route` in `api/handlers_chat.py`): e' il canale che servira' il turno, e i due valori che porta -- `"ponte"` e `"catena"` -- sono VALORI DI DOMINIO, la sezione che il glossario ha rinviato di proposito con la ragione scritta. Il nome dice cosa la variabile sceglie, non traduce la parola. Vive anche in `schedulatore/turno.py:139` (stesso idioma, `via, ... = chi_risponde(app)`) e in `decisione_modelli.py`, dove `"via"` e' anche una CHIAVE del dizionario che la pagina Modelli legge: la chiave resta italiana come ogni altra, si rinomina la variabile |
| valore | value |
| verbo | verb |
| verificabile | verifiable |
| visibile | visible |
| visualizzato | displayed |
| vivo | live |
| voce | entry |
| vuoto | empty |
| zona | zone |

> **`guarda` non e' piu' in questa tabella -- corretto durante la review del Task 6.** Viveva qui
> come parola ordinaria (`look`) ED era gia' un nome dei tredici strumenti (`view`, sotto): due
> righe nude con inglesi diversi, senza che nessuna lo dichiarasse un omonimo. Vedi la nota alla
> fine di «I nomi degli strumenti» per la correzione completa (`guarda (casa) -> view`, `guarda
> (cervello) -> watch`).

> **`aperto -> open` e' protetto dalla guardia sulle keyword/builtin di `scripts/rinomina.py`
> (Task 6): non si applica mai da solo su un identificatore nudo, perche' `open` e' un builtin
> Python (il costruttore dei file) -- esce sempre come proposta, e chi la chiude decide un nome che
> non lo ombreggi (`cervello/oggetti.py::aperti`, il caso vero, e' diventato `open_episodes`, non
> `open`).**

> **`spento` e `funziona`/`_FUNZIONANO` (`cervello/oggetti.py`) NON sono in questa tabella, di
> proposito.** Non sono traduzioni dirette del verbo italiano: `_SPENTO` (rinominata `_RESTING`)
> raggruppa stati di riposo molto piu' larghi di "spento" alla lettera (`locked`, `docked`,
> `idle`...), e `_FUNZIONANO` (rinominata `_OPERABLE`) descrive domini Home Assistant che si
> accendono/spengono come un interruttore, non "che funzionano" in senso generico. Applicare
> `off`/`function` alla cieca avrebbe detto una bugia sul contenuto delle due costanti -- decisioni
> di giudizio locali a `cervello/`, non parole ordinarie da riusare altrove senza rileggerle.

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

> **`riga`: omonimo per ambito, il sesto di questa fetta -- `riga (casa) -> line` in tabella,
> sopra.** Negli archivi SQLite (`cervello/archivio.py`, `memoria/archivio.py`, `casa/archivio.py`,
> `azione/cronaca.py`, `schedulatore/promessa.py`, `decisione_modelli.py`) `riga`/`righe` e' una
> riga di tabella: `row` e' corretto e non perde niente -- ed e' il senso DOMINANTE, misurato
> (`cervello/archivio.py`: 53 occorrenze; `chat_store.py`: 17; piu' `azione/cronaca.py` e i
> costruttori `_fact_row`/`_reading_row`), motivo per cui la riga nuda `riga -> row` resta cosi'
> com'e'. Ma `casa/nucleo.py` costruisce il testo che il modello legge -- non una tabella -- e li'
> `riga` e' sempre una riga di **testo**: la parola giusta e' `line`. **Applicato per intero nel
> lotto di `strumenti.py` (arbitrato del proprietario, dopo la misura sopra)**: tutta la famiglia
> (`_home_space_rows` -> `_home_space_lines`, `_behavior_rows` -> `_behavior_lines`, `_gap_rows`
> -> `_gap_lines`, `_highlight_rows` -> `_highlight_lines`, `_memory_rows` -> `_memory_lines`,
> `_reference_frame_rows` -> `_reference_frame_lines`, `_now_row` -> `_now_line`,
> `unreachable_row` -> `unreachable_line`, `rows_pool` -> `pool_lines`, il bare `row`/`rows` ->
> `line`/`lines` -- 99 occorrenze in tutto, non le "~30" stimate prima di contarle davvero) --
> non solo la variabile locale mostrata come esempio: lasciare meta' famiglia `row` e meta' `line`
> nello stesso file sarebbe stata l'incoerenza che questa correzione esiste per togliere.
>
> **Corretto (Task 9, `api/`): la riga era scritta `riga (nucleo)`, e per un anno intero -- dal
> lotto di `strumenti.py` fino a qui -- non ha mai fatto nulla.** `Glossario.per(parola, ambito)`
> riceve l'ambito con cui si invoca `rinomina.py --ambito <...>`, e quell'argomento e' sempre il
> nome di una CARTELLA (`casa`, `memoria`, `api`, ...): `nucleo` non e' mai stato un ambito valido,
> e' il nome del FILE dentro `casa/` dove vive il senso *line*. `per("riga", "nucleo")` non e' mai
> stato chiamato da nessuna invocazione reale dello strumento (si invoca sempre `--ambito casa`,
> mai `--ambito nucleo`): la riga era una decisione scritta senza effetto, e il codice di
> `nucleo.py` e' comunque giusto solo perche' la famiglia `line` e' stata applicata A MANO, non
> dal join meccanico che questa riga avrebbe dovuto guidare. **Verificato eseguendo**, prima e
> dopo la correzione: `Glossario.per("riga", "casa")` tornava `None` (nonostante `casa/nucleo.py`
> usi gia' `line` ovunque) e ora torna `line`; l'assenza di conflitto con gli altri sette file di
> `casa/` e' verificata con una scansione `tokenize` su tutta la cartella, zero identificatori
> `riga`/`righe` residui fuori da `nucleo.py` (sono gia' tutti diventati `row`/`rows` a mano,
> prima che questa riga esistesse) -- qualificare per `casa` non ha quindi nulla da correggere
> retroattivamente, protegge solo un'eventuale riapplicazione futura. Vedi «Il limite della
> qualificazione per ambito» per la conseguenza operativa generale che questo errore rivela: una
> parola si qualifica col nome della CARTELLA con cui lo strumento si invoca, mai col nome di un
> file al suo interno.

> **`stato`: tre significati, non uno.** La tabella sopra lo marca confine → `state`: e' giusto
> per il senso principale, lo stato di un'entita' di Home Assistant (`casa/domande.py`,
> `casa/nucleo.py`, e la colonna `stato` di `costruzioni`/`promesse` che tiene i valori di
> `STATI_SOSPESO`/`STATI_CONCLUSI` — quello e' ancora «lo stato di qualcosa», `state` non mente).
> Ma **non e' l'unico senso**: in `api/handlers_mcp.py:207` (oggi `def _error(..., *, status:
> int = 200)`, passato a `web.json_response(..., status=status)`, e usato con `status=400` alle
> righe 540, 548, 568) `stato` e' uno **status HTTP**, un intero, non lo stato di un'entita' —
> `state: int = 200` sarebbe un nome che mente. **Fatto nel lotto 10 (Task 9), esattamente come
> quest'istruzione lo prescriveva, e con l'inciampo che prevedeva:** lo strumento aveva applicato
> `stato -> state` alla `def` e lasciato intatti i tre `stato=400` (parole chiave in una chiamata,
> mai applicate da sole) -- una divergenza fra firma e chiamanti che nessun cancello avrebbe
> visto, chiusa a mano su entrambe le sponde con `status`. E in `costo_stato` (`agent/runner.py:1123`,
> `backends/openai_compat_runner.py:394,408`, `claude_runner.py:741,755`,
> `consumi/archivio.py` — colonna e funzioni, alimentato da `consumi/vocabolario.py:
> stato_e_costo()`) `stato` e' una **classificazione del costo di una chiamata** (`compreso`,
> `gratuito`, `reale`, `misurato`, `non_noto`), non uno stato nel senso HA ne' un codice HTTP.
> La tabella sopra fissa `state` come equivalente di default per il caso principale;
> `api/handlers_mcp.py:207` e i dintorni di `status=400/540/548/568` usano `status` (il nome che
> HTTP e aiohttp usano gia') dal lotto 10, e chi rinomina `costo_stato` deve usare qualcosa come
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
> di uno scambio diretto. **Deciso (Task 7, «I valori di dominio», sotto): `STATES_SOSPESO` e
> `STATES_CONCLUSI`**, cioe' `STATES_...` e non `..._STATES` -- proprio la forma che questa nota
> chiedeva di preferire: il qualificatore (`SOSPESO`/`CONCLUSI`) resta subito accanto al nome della
> costante invece di finire in coda dopo `STATES`, cosi' nessuna delle due si legge come l'elenco
> vivo delle entita' di Home Assistant.

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

**Una firma pubblica non puo' avere alcuni parametri tradotti e altri no per il solo motivo che
il glossario non li aveva ancora decisi -- aggiunta durante la review indipendente del Task 7
(`azione/`).** `Journal.log`/`Journal.log_construction` (`azione/cronaca.py`) traducevano gia'
`origine→actor`, `servizio→service`, `entita→entity`, `errore→error`, `avviso→notice`, ma
lasciavano `eseguito`/`cambiato` in italiano — non perche' rispecchiassero le colonne del
database (`eseguito`/`cambiato_json`: quella e' la ragione giusta per le COLONNE, che restano
italiane per costruzione, non per i PARAMETRI Python della funzione che le scrive), ma solo
perche' `eseguito`/`cambiato` non erano ancora righe di questo glossario. Il criterio per un
parametro di funzione e' lo stesso di ogni altro identificatore: si traduce se il glossario ha
deciso la parola, resta italiano se non l'ha ancora decisa — **mai** "resta italiano perche'
rispecchia una colonna", che confonderebbe il livello Python con quello SQL. Decise qui
`eseguito → executed` e `cambiato → changed` (righe sopra, «Le parole ordinarie») e applicate a
entrambi i metodi: la firma di `Journal.log` ora traduce OGNI suo parametro, le colonne del
database (`eseguito`, `cambiato_json`) restano quelle di sempre.

**La collisione `conteggio`/`quante`, decisa nel lotto di `casa/nucleo.py`.** Segnalata dalla
guardia sulle collisioni fin dal lotto 4 (`anagrafe.py`), rimandata perche' viveva in un file non
ancora suo: entrambe decise `-> count` (righe sopra), ma nello stesso file (`nucleo.py`) nominano
cose diverse -- `quante` e' quasi sempre uno SCALARE (un numero: quante entita' porta una riga,
`_annotazione_dispositivo`), `conteggio` e' sempre un DIZIONARIO (dominio -> quante, in quattro
funzioni diverse: `_count_per_domain`, `_home_space_lines`, `_group_highlights`,
`_integrations_notice`). Deciso qui, guardando il codice invece di applicare la riga alla cieca:
`conteggio` (il dizionario) -> **`counts`** (plurale: e' una mappa di piu' conteggi, coerente con
`conteggi -> counts` gia' deciso per il ritorno di `anagrafe.rebuild`); `quante` (lo scalare) resta
**`count`** (singolare), la riga com'e' scritta sopra. Due occorrenze di `quante` in
`_integrations_notice`/`_comparison_notice` non sono ne' l'uno ne' l'altro: portano gia' una FRASE
formattata ("3 aree", "un'area"), non un numero -- rinominate a mano `count_phrase`, per non
promettere uno scalare dove il valore e' un testo.

**Altre decisioni a mano prese nel lotto di `casa/nucleo.py`, invisibili al criterio dei composti
perche' parole singole (come `righe`/`identita`, corrette sopra).** Trovate rileggendo il file
identificatore per identificatore dopo il giro dello strumento, non dal dry-run: nessuna era un
composto, quindi nessuna era comparsa nell'elenco da decidere.

- `ripetuta` (`_integrations_notice`, il suffisso " x2" di un'integrazione ripetuta) ->
  **`repeat_suffix`**: non una parola del vocabolario generale, un nome che dice cosa la variabile
  CONTIENE.
- `chiusura` (`_problems_notice`, la clausola finale gia' concordata al singolare/plurale: "non e'
  elencato qui, si legge" / "non sono elencati qui, si leggono") -> **`closing_phrase`**, stessa
  famiglia di `count_phrase`: non e' un conteggio ne' un verbo, e' una frase gia' fatta.
- `da_dire` (`_problems_notice`, i problemi non silenziati, quelli che il testo restituito
  effettivamente elenca) -> **`to_report`**.
- `guardate` (`_comparison_notice`, le aree per cui il confronto e' stato fatto) -> **`checked`**,
  la stessa parola gia' scelta in `anagrafe.confronta_con_home_assistant` per il campo dati
  OMONIMO. La chiave stringa del dizionario che quella funzione restituisce (`"guardate"`) resta
  cosi' -- e' dato, non un identificatore -- il nome cambia solo sulla variabile locale che lo
  legge qui.
- `piu`/`meno` (stessa funzione, i due casi -- l'albero ne ha DI PIU' di quel che HA conferma /
  Home Assistant ne riporta MENO di quel che l'albero conosce) -> **`extra`**/**`missing`**:
  tradurre alla lettera ("more"/"less") non direbbe la stessa cosa in inglese, `missing` in piu'
  e' coerente con la chiave dati `mancanti` che quella lista filtra.
- `mappa` (`_area_per_entity`, un semplice `entity_id -> nome area`) -> **`area_lookup`**, non
  `map`: applicarla nuda avrebbe ombreggiato il builtin (stessa guardia di `_pericoloso`, vedi
  `scripts/rinomina.py`). Non e' la stessa cosa del concetto `indice -> lookup` di `memoria/`: qui
  e' descrittiva di una variabile locale, non il nome di una struttura del prodotto.
- `_assembla` -> **`_assemble`** (e le sue variabili locali `blocchi`/`blocco` -> `blocks`/`block`),
  `rango` (`_severity_rank`) -> **`rank`**, `righe_pool` -> **`pool_lines`** (corretto dopo il
  lotto di `riga (nucleo) -> line`: era `rows_pool` quando questa riga fu scritta, prima che
  l'omonimia per ambito fosse arbitrata -- vedi la nota su `riga` sopra), `tagliato` (il
  flag per-iterazione del taglio, distinto da `troncato` -- il flag dell'intero giro) -> **`cut`**:
  letture dirette del glossario (`taglio -> cut`, `raggruppa -> group`, ecc.), non nuove decisioni,
  ma invisibili allo strumento perche' nessuna e' un composto.
- `problemi`, il parametro pubblico di `compose()` e di `_problems_notice()` -> **`problems`**:
  MAI lo stesso nome del metodo di `HAClient.problemi()` che lo alimenta (protetto a parte in
  `_METODI_HA_CLIENT`) -- qui non c'e' un punto davanti, e' un parametro, non un attributo.
- `detto_da` (`_memory_lines`, letta da un ricordo) -> **`said_by`**: la chiave dati resta
  `"detto_da"`, la stessa colonna di `memoria/archivio.py` -- resta italiana PER SEMPRE, come ogni
  colonna di database di questa fetta (regola permanente, non legata allo stato di conversione di
  `memoria/`: cambierebbe solo se la colonna stessa venisse migrata, una decisione a parte).
  Cambia solo la variabile locale che la legge qui. La FRASE italiana che finisce nel testo
  ("detto da ...") resta italiana: e' cio' che il modello legge, non un identificatore.
- Forme plurali non incatenate dallo strumento perche' l'alias esistente traduce il singolare
  (`identificativo -> identificatore`, `dettaglio -> detail`) ma non la forma con la "i" finale:
  `identificativi` -> `identifiers`, `dettagli` -> `details`, `gruppi` -> `groups` (`gruppo ->
  group` e' nuovo in questo lotto, sotto).

**Decisioni del lotto di `casa/strumenti.py`, il dispatcher dei tredici strumenti.**

- **`_ARCHIVIO_PER_STRUMENTO`/`_archivio_mancante` -> `_RESOURCE_PER_TOOL`/`_missing_resource`,
  non `_store_*`.** Il nome originale usa "archivio" in senso largo: la mappa elenca anche `"ha"`
  (il canale verso Home Assistant) e `"porta"`/`"officina"` (due servizi, non due archivi).
  Applicare `archivio -> store` alla lettera avrebbe promesso "manca lo STORE" quando il messaggio
  vero e' "manca il collegamento vivo con Home Assistant" -- deciso guardando i quattro rami di
  `_missing_resource`, non la singola parola.
- **`_cecita` -> `_blind_spots`**: non e' nel vocabolario generale, e' il nome di UN metodo che
  spiega perche' `cerca` puo' non vedere qualcosa che esiste (registri caduti, entita' senza nome).
  `cecita` stessa non e' mai stata una parola da tradurre in astratto.
- **`tipo` (bare, locale) -> `kind`, mai `type`**: stessa decisione di `domande.py` (lotto 6) per
  lo stesso motivo -- ombreggerebbe il builtin. `casa/strumenti.py` chiama `domande.view` e
  `domande.related` passando questo stesso valore per posizione ai loro parametri, gia' `kind`:
  riusare la parola invece di deciderla di nuovo e' la fondamenta "nessun doppione" applicata a un
  nome, non solo a un concetto.
- **`caduti` -> `fallen_stores`**, non `unavailable`: il concetto e' lo stesso di `registro_caduto
  -> unavailable` (lotto 5), ma nello stesso file esiste gia' un parametro `non_disponibili ->
  unavailable` con un significato diverso (i registri passati a `guarda`) -- due variabili
  `unavailable` nello stesso modulo, anche se in funzioni diverse, sarebbero state una lettura
  ambigua per chi rivede il codice senza il contesto di questa nota.
- **`letto`/`specchio_letto` -> `loaded`/`mirror_loaded`, mai `read`**: gia' deciso e scritto in
  questo glossario (vedi la riga `letto` sopra, in "Le parole ordinarie") proprio guardando
  `casa/strumenti.py` come uno dei due file dove `leggi` (il verbo, `read`) e `letto` (il
  participio, `loaded`) convivono -- applicato qui per la prima volta.
- **Il parametro `verifica` di `_verifica_ora` -> `verify`**: riceve la funzione
  `azione.verifica.verification` (mai rinominata: e' un ambito chiuso ma non mio da toccare in
  questo lotto) come valore -- il nome del PARAMETRO e' mio, il nome della funzione importata no.
- Composti auto-suggeriti dallo strumento e ACCETTATI cosi' come sono (ordine gia' naturale in
  inglese, nessuna correzione semantica necessaria): `_TIPI_ANCORA -> _TETHER_TYPES` (il
  vocabolario delle ancore e' di `memoria/`, che ha gia' deciso `ancora -> tether`),
  `_TIPI_LEGAME_NOSTRI -> _OUR_LINK_TYPES`, `STRUMENTI_CONOSCENZA -> KNOWLEDGE_TOOLS`,
  `_NOMI_STRUMENTI -> _TOOL_NAMES`, `DispatcherStrumenti -> ToolDispatcher`, e le tredici costanti
  `*_TOOL_DEF` (`CERCA_TOOL_DEF -> SEARCH_TOOL_DEF`, ecc.): ognuna e' il nome della costante Python,
  mai la stringa `"name"` che il modello legge dentro -- quella resta italiana, e' il contratto.
- **`entita` (bare, locale)**: tradotta `entity` dove il valore e' UNA cosa sola (`_andamento`,
  `_accaduto`), `entities` dove e' una lista (`_verifica_da_confrontare`, `_istantanea`) --
  l'italiano non flette la parola fra singolare e plurale, l'inglese si', e la forma del
  parametro (`list` contro stringa) dice quale delle due serve.

**Decisioni del Task 9 (`api/`), non parole del vocabolario generale.**

- `handle_get_promesse`/`handle_get_costruzioni` (le due rotte che tornano una LISTA) ->
  `handle_get_agenda`/`handle_get_constructions`: `promesse` (plurale) e' un concetto collettivo
  gia' deciso a se' (`promesse -> agenda`, distinto da `promessa -> promise`), mentre
  `costruzioni` non ha una riga propria -- e' il semplice plurale di `costruzione -> construction`
  gia' deciso, senza bisogno di un sostantivo collettivo diverso come per `promesse`.
- `tutte` (`handlers_promesse.py`, il flag booleano `?tutte=1`) -> parola ordinaria decisa
  `tutte -> all`, ma applicata a mano come **`show_all`**, non `all` nudo: `all` e' un builtin
  Python, la stessa guardia di `classe`/`class` che lo strumento applica gia' alle parole che
  decide da solo.
- `esito` (`handlers_promesse.py`/`handlers_costruzioni.py`, il dict `{"errore": ...}`/`{...}`
  che un tentativo di operazione restituisce) -> **`occurrence`**, la riga gia' decisa: verificato
  contro il codice prima di applicarla (non per fiducia nel suggerimento), perche' la descrizione
  della riga parla di "un tentativo" in un senso che in `azione/porta.py` e
  `azione/costruzione/officina.py` (gia' chiusi) e' esattamente questo stesso idioma -- non una
  collisione di senso come `grezzo`/`reading`.
- `_NON_TROVATA` (`handlers_costruzioni.py`, il testo del 404 condiviso da lettura e azione) ->
  **`_NOT_FOUND`**: composto ad hoc, non una parola del vocabolario generale -- `non` e' un
  prefisso di negazione che in altri composti gia' decisi (`non_disponibili -> unavailable`) non
  si traduce affatto con "not_", quindi non e' stata scritta una riga generale per `non`; `trovata`
  e' la forma femminile di `trovato -> found`, mai aliasata perche' non ricorre altrove.
- `solo_aperte` (`handlers_costruzioni.py`, il flag booleano `?in_attesa=1`) -> non tradotta parola
  per parola (`solo`/`aperte` non sono mai state decise): rinominata **`pending_only`**, lo stesso
  nome del parametro keyword-only VERO di `ConstructionStore.list` che riceve (gia' inglese) --
  stesso principio di `metodo`/`method` sotto, riusare il nome dell'interfaccia che si sta gia'
  chiamando invece di inventarne uno diverso per lo stesso fatto.
- `agisci`/`verbo`/`metodo` (`handlers_costruzioni.py::_agisci`, il dispatcher privato che sceglie
  fra `officina.apply`/`.restore` con `getattr`) -> **`_act`/`verb`/`method`**, tre parole
  ordinarie nuove (sotto, in "Le parole ordinarie"): nessuna collisione nel resto di `hiris/app`
  (scansione `tokenize`, `metodo` ricorre anche in `api/handlers_mcp.py` col senso di "nome del
  metodo JSON-RPC richiesto" -- stesso concetto generale, non un secondo senso).
- `store.scadi(...)` (`handlers_costruzioni.py`, verso `ConstructionStore.scadi`,
  `azione/costruzione/versioni.py:295`) **lasciato intatto di proposito**: `scadi` e' un metodo
  PUBBLICO ancora italiano in un ambito gia' chiuso (`azione/`), mai deciso nel glossario --
  invisibile allo strumento per costruzione (nessun pezzo di `scadi` e' mai stato tradotto), la
  stessa classe di residuo gia' tracciata per `AgendaStore.list::solo_in_sospeso`
  (`schedulatore/`, vedi `tests/test_rinomina_applica.py`). Non tracciato li' perche' fuori dal
  perimetro-file di questo lotto: segnalato qui perche' chi apre `azione/costruzione/versioni.py`
  lo sappia prima di scoprirlo per caso.

- `store.concludi(...)`/`_senza_conclusione` (`handlers_reasoning.py`, verso
  `AgendaStore.concludi` e `schedulatore/turno.py::_senza_conclusione`) **lasciati intatti di
  proposito**: stessa classe di residuo di `store.scadi`, sopra -- metodi/funzioni ancora italiani
  in un ambito gia' chiuso (`schedulatore/`), mai decisi. Entrambi nell'elenco unico del debito nel
  report di Task 9, non ripetuti qui parola per parola.
- **`ingresso -> input_tokens`, non `input` nudo**: `input` e' un builtin Python (`_pericoloso`),
  la stessa guardia di `classe`/`class` -- lo strumento lo segnala come proposta invece di
  applicarlo, e la scelta a mano riusa il nome del campo JSON che la variabile alimenta
  (`"input_tokens"`), la stessa disciplina gia' vista per `pending_only`.
- **`sezioni`/`totali` (`handlers_usage.py`, verso `UsageStore.sezioni`/`.totali`), `storia`
  (verso `UsageStore.storia`) e `sposta_anchor` (verso `UsageStore.sposta_anchor`,
  `handlers_usage.py:218`, `handle_reset_usage`) NON decise come parole generali**, a differenza
  di `ingresso`: sono QUATTRO metodi PUBBLICI di un ambito gia' chiuso (`consumi/`) mai tradotti
  -- terzo/quarto/quinto/sesto caso della stessa famiglia di `scadi`/`solo_in_sospeso`/`concludi`
  (`sposta_anchor` mancava dal primo giro di questa nota: lo stesso lotto lo chiama, e non era
  stato scritto qui -- corretto dopo il rilievo del coordinatore, Round 4). Qui pero' la scoperta
  e' arrivata PRIMA di romperli (dry-run su questo stesso file, che chiama tutti e quattro): la
  guardia di `scripts/rinomina.py` e' stata estesa con `_METODI_USAGE_STORE` (che include gia'
  `sposta_anchor` fra le sue voci), sullo stesso modello di `_METODI_HA_CLIENT`, cosi' un domani
  in cui `sezione -> section` venisse decisa per un'altra ragione non romperebbe silenziosamente
  queste quattro chiamate. Le variabili LOCALI che ricevono i risultati sono comunque tradotte a
  mano (`sections`, `totals`) senza toccare le chiamate protette -- la funzione
  `handle_storia_usage -> handle_usage_history` (il nome della rotta, mio) e' tradotta lo stesso,
  senza mai scrivere una riga generale `storia -> history` che romperebbe la guardia appena
  descritta se applicata a un `def storia(` non protetto. **Gli stessi metodi portano anche
  keyword-only ancora italiani nella FIRMA**, mai decisi ne' tradotti: `da`/`a` di
  `UsageStore.storia` -- gia' protetti dalla guardia
  generale sulle parole chiave in una chiamata (mai applicate da sole), qui elencati per
  completezza dell'inventario, non perche' rischino qualcosa in piu' della protezione gia' in
  vigore. **`da_anchor` di `.sezioni`/`.totali` era il terzo di questo elenco e non c'e' piu'**:
  la misura ordine e preposizioni (31/08) l'ha corretto in `from_anchor`, insieme ai suoi
  chiamanti per parola chiave -- una preposizione italiana innestata su una testa inglese non
  e' un residuo coerente, e' il difetto che il cancello sulle preposizioni vieta.
- `_MSG_NESSUN_PROVIDER -> _NO_PROVIDER_MSG`, `_GIORNI_STORIA -> _HISTORY_DAYS` (composto ad hoc,
  non una parola generale: vedi sopra il perche' di `storia`), `_puo_rispondere -> _can_respond`,
  `_non_misurata -> _unmeasured`, `_modello_fuori -> _model_out` (`fuori` qui e' il senso
  "dato in uscita", NON il senso `fuori (casa) -> outside`: lo stesso idioma di
  `schedulatore/promise.py::serializza` gia' documentato in «Il limite della qualificazione per
  ambito», applicato a mano senza toccare la riga `fuori (casa)`). Tutte private, nessun
  chiamante esterno.
- **`nome`/`giorni_conservazione` (`handlers_impostazioni.py`, verso `ImpostazioniChat`) --
  terza voce della guardia meccanica**: `ImpostazioniChat` (`impostazioni_chat.py`, un file di
  RADICE, ne' ambito chiuso ne' aperto) e' un dataclass con due campi ancora italiani. Misurato
  PRIMA di romperlo (`rinomina.riscrivi()` su uno snippet isolato): `corrente.nome` diventava
  `corrente.name` senza guardia. Estesa `scripts/rinomina.py` con
  `_METODI_IMPOSTAZIONI_CHAT` (i sette campi piu' i due metodi pubblici, `carica`/`salva`),
  unita a `_METODI_ESTERNI_PROTETTI`. Due test nuovi, entrambi provati per mutazione. `nome`
  come parola ordinaria si applica comunque alle VARIABILI LOCALI non protette (`nome -> name`),
  `giorni_conservazione` resta intatto ovunque (mai deciso come parola generale, stessa
  ragione di `handlers_chat_history.py`, lotto 1: la parola vive gia', invariata, in tutti i sei
  ambiti chiusi).
- `Rifiuto -> Rejection` (classe, campi `.campo`/`.motivo -> .field`/`.reason`, MIA -- non
  un'interfaccia esterna, sicura da rinominare per intero), `_tipo -> _type`, `_testo -> _text`,
  `valida -> validate`, `CAMPI -> FIELDS` (non `field` singolare, il suggerimento meccanico
  letterale: e' una tupla di piu' nomi), `MODI_RISPOSTA -> RESPONSE_MODES`,
  `MAX_CARATTERI_PROMPT -> MAX_PROMPT_CHARS` (invisibile al dry-run: nessuno dei tre pezzi era
  mai stato deciso), `_intero_non_negativo -> _non_negative_integer` (aggettivo prima del nome),
  `sconosciute -> unknown_fields`, `nuove -> updated` (non l'alias letterale "new": e' un'istanza
  singola gia' validata, non un aggettivo su un plurale), `turni -> turns` (**non** `exchange`,
  il suggerimento del concetto generale `turno -> exchange`: qui il senso e' il conteggio di
  `max_chat_turns`, gia' inglese con la parola "turns", non lo scambio col modello del
  reasoning -- collisione catturata leggendo il codice, non applicata alla cieca).
- Tre parole nuove nel glossario, verificate senza collisioni di senso su tutto `hiris/app`:
  `intero -> integer`, `negativo -> negative`, `restrizione -> restriction`. Quattro alias di
  forma flessa aggiunti: `campi -> campo`, `modi -> modo`, `nuove -> nuovo`,
  `sconosciute -> sconosciuto`. Una quinta parola, `carattere -> character`, ha causato un
  effetto collaterale reale in un ambito gia' idempotente: vedi sotto.
- **Effetto collaterale reale, chiuso subito**: `carattere -> character` (decisa qui, per
  `MAX_CARATTERI_PROMPT`) si applica anche a `memoria/resolver.py` (2 occorrenze, un parametro e
  una variabile di loop, entrambi privati e senza chiamanti per keyword -- verificato con grep).
  Trovato dalla guardia di idempotenza (`test_il_residuo_di_memoria_resolver_e_solo_inizio_start`,
  andata rossa: "diverge su {('carattere', 'character'), ('inizio', 'start')}"), non da
  un'ispezione volontaria. Corretto A MANO nel file (non rilanciando l'intero strumento, che
  avrebbe reintrodotto anche `inizio -> start`, il residuo deliberatamente lasciato italiano
  dal fix I2 del Task 8): rinominate le due occorrenze private di `carattere`, la guardia torna
  verde. Nessun altro pezzo di `memoria/resolver.py` toccato.

**Decisioni del lotto 10 (`api/handlers_mcp.py`), non parole del vocabolario generale.**

- **`stato` -> `status`, non `state`**: la decisione era gia' scritta accanto alla riga `stato`
  (vedi la nota «`stato`: tre significati, non uno», sopra) e questo lotto l'ha solo eseguita.
  Vale la pena registrare COME il difetto si presenta a chi arriva: lo strumento applica
  `stato -> state` alla `def _error(..., *, stato: int = 200)` ma NON ai tre `stato=400` dei
  chiamanti (parole chiave in una chiamata, protette per costruzione) -- il risultato intermedio
  e' una firma e tre chiamate che non si parlano piu', e la suite non lo vede perche' entrambe le
  sponde vivono nello stesso file mio. Si chiude a mano su entrambe le sponde, mai su una sola.
- **`turno` -> `exchange` qui SI'** (a differenza di `turni -> turns` del lotto 8): l'identita' di
  `X-HIRIS-Turno` che questa rotta legge e' esattamente lo scambio applicativo della riga
  `turno`, ed e' lo STESSO valore che `azione/costruzione/officina.py` e `casa/strumenti.py`
  (ambiti gia' chiusi) chiamano gia' `exchange`. Verificato leggendo quei due file, non dedotto
  dal suggerimento meccanico. Il keyword `turno=` della chiamata a
  `costruisci_dispatcher_strumenti` (`api/handlers_chat.py`, NON convertito) resta italiano: e'
  il nome del parametro altrui.
- **`id_turno`/`id_richiesta`/`id_promessa` -> `exchange_id`/`request_id`/`promise_id`**:
  l'inglese mette l'`id` in coda, ed e' gia' la convenzione misurata nel codice convertito
  (`execution_id` 32, `promise_id` 10, `entity_id` 94, `proposal_id` 9 -- contro zero
  identificatori nella forma `id_<cosa>` fuori dai file ancora italiani).
- **`prepara_contatori` -> `create_rounds_per_exchange`, e ne' `prepare` ne' `counter` sono
  entrati nel glossario.** Due blocchi veri della regola di collisione, non una preferenza:
  `prepare` cade su un identificatore non-prosa (`stream_resp.prepare(request)`,
  `api/handlers_chat.py:933`) e `counter` e' un **dominio di Home Assistant** (`casa/nucleo.py:138`
  lo mappa proprio su `("contatore", "contatori")`, e `proxy/ha_client.py:576` lo elenca fra i
  domini) -- chiamare `counter` un dizionario di conteggi in un prodotto che parla con HA sarebbe
  la peggiore collisione possibile. Il nome scelto dice cosa la funzione CREA (`crea -> create`,
  riga gia' decisa) e combacia con la costante che nomina la stessa struttura,
  `ROUNDS_PER_EXCHANGE_KEY`. `prepara` resta undecided: ricorre ancora in `prepara_token_interno`
  (`server.py`, `token_interno.py`), fuori dal perimetro di questo lotto.
- **`_rifiuto_tetto_raggiunto` -> `_ceiling_rejection`**: `rifiuto -> rejection` e `tetto ->
  ceiling` sono gia' decise, `raggiunto` NO e non e' stata decisa -- `reached` cade su un
  identificatore non-prosa (`var reached = current >= max`, `static/chat/agents.js:44`), quindi
  la regola blocca. Il participio sparisce nel nome, come le preposizioni di `nomi_di_ripiego`:
  cio' che il rifiuto sia «del tetto raggiunto» lo dice il docstring, non serve nel nome.
- **`parametri` -> `params`, non `parameters`**: e' il membro `params` di JSON-RPC 2.0 che la
  funzione riceve, riusato invece che tradotto -- stessa disciplina di `pending_only`
  (lotto 5), `input_tokens` (lotto 7) e `turns` (lotto 8). `parametro` resta undecided.
- **`giri_gia_fatti` -> `rounds_so_far`**: composto ad hoc (`gia`/`fatti` mai decise), il nome di
  cio' che il valore E' -- quanti giri erano gia' passati PRIMA dell'incremento, cioe' il valore
  che `_count_round` restituisce.
- **`promessa` (la variabile locale) -> `store`, non `promise`**: il valore e'
  `request.app.get("promesse")`, cioe' l'`AgendaStore`, non una promessa -- lo strumento
  applicava `promise` da solo (parola singola gia' decisa) e il nome avrebbe mentito, la stessa
  famiglia di `fuori -> outside` sul dizionario delle categorie (vedi «Il limite della
  qualificazione per ambito»). Corretto a mano in `store`, lo stesso nome che la funzione gemella
  `_exchange_promise_id` usa gia' per lo stesso oggetto.
- **`_promessa_del_turno` -> `_exchange_promise_id`**: la preposizione sparisce e l'`id` compare,
  perche' la funzione restituisce un id (una stringa), non una promessa -- il nome originale non
  lo diceva e il docstring si'.
- **Nomi composti accettati senza correzione semantica**: `MCP_SERVER_NAME`, `DEFAULT_PROTOCOL`,
  `METHODS`, `MAX_TOOL_ROUNDS` (l'ordine e' quello di `MAX_TOOL_ITERATIONS`, il tetto gemello del
  ramo sincrono in `claude_runner.py`: due tetti con lo stesso mestiere portano ora la stessa
  forma di nome), `_MAX_TRACKED_EXCHANGES`, `ROUNDS_PER_EXCHANGE_KEY`, `mcp_catalog`,
  `_count_round`, `_call_tool`, `is_notification`, `arguments`, `entries`, `definitions`,
  `rounds`, `rounds_per_exchange`, `content`.
- **Il valore della chiave d'applicazione NON cambia**: `ROUNDS_PER_EXCHANGE_KEY` vale ancora
  `"mcp_giri_per_turno"`, ed e' letto per stringa da `tests/test_rotta_mcp.py`
  (`client.app["mcp_giri_per_turno"]`). E' un accesso dinamico -- il §5 della spec: la costante e'
  un identificatore e si rinomina, la stringa e' un contratto interno fra `server.create_app()` e
  questa rotta e si tocca solo in una fetta che tocchi entrambe le sponde.
- **Sette parole nuove nel glossario** (`catalogo -> catalog`, `chiama -> call`,
  `contenuto -> content`, `definizione -> definition`, `notifica -> notification`,
  `protocollo -> protocol`, `tracciato -> tracked`) e **un alias di forma**
  (`strumento -> strumenti`, il lemma e' il plurale perche' il concetto e' «l'insieme dei nomi»).
  `chiama` e `chiamata` puntano entrambe a `call`: non e' un difetto ma la stessa coppia
  verbo/sostantivo gia' presente in `scrivi`/`scrittura`, `elenca`/`elenco`, `raggruppa`/`gruppo`.
  Una sola ha avuto un effetto fuori dal file: vedi sotto.
- **Effetto collaterale reale, chiuso subito**: `definizione -> definition` si applica anche a
  `azione/verifica.py` (6 occorrenze: i parametri di `_declare_target`/`_allows_empty_target` e
  una locale di `verification`, tutti privati, nessun chiamante per keyword -- verificato con
  grep). Misurato PRIMA di applicare il file, rieseguendo la guardia di idempotenza sui sei ambiti
  chiusi: `azione` compariva fra i cambiati insieme al residuo noto `costruzione/composer.py`.
  Corretto lasciando che lo strumento lo applicasse a quel solo file (il risultato coincide con la
  correzione a mano: `_sostituzioni_di_identificatori` mostra la sola coppia
  `('definizione', 'definition')`), piu' l'unica citazione fra backtick che diventava falsa nello
  stesso file. Stessa famiglia di `carattere` (lotto 8) e `richiesto` (lotto 9).

**Decisioni del lotto 11 (`api/handlers_casa.py`), non parole del vocabolario generale.**

- **`costruisci_nucleo` e `handle_get_nucleo` LASCIATE italiane, di proposito.** Non sono
  invisibili allo strumento (le propone entrambe) e non sono difficili: escono insieme a
  `api/handlers_chat.py`, che le tiene per un'importazione vera (`from .handlers_casa import
  costruisci_nucleo`, riga 28) e per una citazione fra backtick (riga 220). `costruisci_nucleo` e'
  importata per nome anche da `schedulatore/turno.py` (ambito chiuso, righe 128 e 259) e citata fra
  backtick in una ventina di punti fra `casa/nucleo.py`, `casa/strumenti.py`,
  `impostazioni_chat.py`, `proxy/entity_cache.py`, `server.py` e otto file di test: rinominarla e'
  un giro suo, e il suo commit naturale e' quello di `handlers_chat.py`. Il suggerimento meccanico
  sarebbe per giunta SBAGLIATO: `propose_briefing` (`costruisci -> propose`, il verbo dello
  strumento che propone una costruzione) mentirebbe -- questa funzione non propone niente, compone
  (`casa/nucleo.compose`). `build_briefing` e' escluso a sua volta: `build` e' gia' bloccato dalla
  regola di collisione (vedi `build` per `costruzione`, sopra).
- **`_mappa_categorie` -> `_categories_by_scope`, e `mappa` resta undecided**: il nome dice cosa la
  funzione RESTITUISCE (le categorie indicizzate per ambito), non come e' fatta dentro. `mappa` non
  e' stata decisa perche' non serviva: la variabile locale che la teneva e' diventata `categories`,
  il nome del suo contenuto.
- **Riuso del nome del parametro che si sta gia' alimentando**, la disciplina di `pending_only`
  (lotto 5) applicata cinque volte in un colpo: le locali di `costruisci_nucleo` che finiscono
  dritte nei keyword di `casa/nucleo.compose` prendono il nome del keyword --
  `non_disponibili -> unavailable`, `stato_affidabile -> reliable_state`,
  `file_non_letti_comportamento -> unloaded_behavior_files`,
  `sistema_di_riferimento -> reference_frame`, `classi_vive -> reported_classes`. Nessuna e' una
  traduzione parola per parola (`classi_vive` letterale sarebbe `class_reported`, l'ordine
  italiano), e nessuna richiede una riga nuova.
- **`stato -> state` qui SI'** (a differenza di `api/handlers_mcp.py`, dove e' `status`): la
  variabile e' lo specchio degli stati vivi delle entita' di Home Assistant, cioe' il senso
  principale della riga `stato`. Le due decisioni opposte nello stesso ambito `api` sono la prova
  che la nota «`stato`: tre significati, non uno» va letta ogni volta, non applicata una volta
  sola.
- **`stato, _nomi, _unita, classi_vive, _da_quando, _attributi` -> `state, _names, _units,
  reported_classes, _since_when, _attributes`**: gli stessi nomi che `casa/strumenti.py:1349`
  (ambito gia' chiuso) usa gia' per lo stesso identico spacchettamento di
  `anagrafe.live_mirror()`. Lo strumento aveva applicato `_unita -> _unit` (singolare: `unita` e'
  invariante in italiano, l'inglese no) -- corretto a mano in `_units` guardando il chiamante
  gemello, non il suggerimento.
- **`archivio_casa`/`archivio_memoria` -> `home_space_store`/`memory_store`**: le VARIABILI, non le
  chiavi d'applicazione `app["archivio_casa"]`/`app["archivio_memoria"]` che restano identiche --
  sono l'accesso dinamico del §5 della spec (41 occorrenze per la sola prima), e la loro rinomina
  e' una fetta a se'. `home_space_store` e' lo stesso nome gia' scelto dal lotto 9 per lo stesso
  oggetto (`handlers_memoria.py`).
- **`inventario_leggibile` lasciata intatta**: e' importata da `proxy/entity_cache.py`, ambito che
  questa fetta non converte -- stessa trappola di `inventario_non_leggibile` (lotto 3), protetta
  per costruzione (composto, mai applicato da solo). **CHIUSA dal lotto 15**, che ha convertito
  `proxy/entity_cache.py`: le due funzioni sono ora `inventory_is_readable` e
  `unreadable_inventory_error`, e i quattro importatori -- `api/handlers_casa.py`,
  `api/handlers_entities.py`, `azione/porta.py`, `casa/strumenti.py` -- sono stati aggiornati
  nello STESSO commit. Il nome importato non e' protetto dalla guardia dei percorsi di import
  (arriva dopo `import`, vedi la nota in `_righe_di_percorso_e_parola_chiave`) ne' dal controllo
  di chiusura, che guarda le parole chiave e non i nomi importati: e' l'unica sponda che nessun
  meccanismo copre, e va chiusa a mano guardando i chiamanti.
- Nessuna parola nuova nel glossario per questo lotto: l'insieme dei file che lo strumento
  riscriverebbe nei sei ambiti chiusi e' rimasto identico (`resolver.py`, `composer.py`,
  `strumenti.py`), misurato prima del commit come prescritto sotto.

**Decisioni del lotto 12 (`api/handlers_chat.py` + la coppia `nucleo` di `api/handlers_casa.py`).**

- **`esito` -> la QUARTA voce della guardia meccanica, e la sola delle quattro che ferma un
  difetto ATTIVO invece che futuro.** `handlers_chat.py:303` scrive
  `registro.esito(nome_backend)` su un `RegistroEsiti` (`esiti_provider.py`, file di RADICE mai
  convertito), ed `esito -> occurrence` e' deciso da sempre: senza guardia il join produceva
  `registry.occurrence(...)`, cioe' un `AttributeError` alla prima chat che ripiega dal piano alla
  catena. Misurato con `rinomina.riscrivi()` sul file vero PRIMA di scriverlo, e provato per
  mutazione (tolta la voce dall'unione, la sostituzione ricompare). E' l'unico attributo di tutto
  `api/` in questa condizione.
- **`coda` -> `queue`, mai `tail`** (vedi l'annotazione accanto alla riga `coda` in «Le parole
  ordinarie»): `coda = request.app["reasoning_queue"]` e' la coda di lavoro, non la coda di una
  stringa. Il senso `tail` esiste ed e' vivo (`agent/runner.py:1559`), quindi la riga NON e'
  sbagliata -- e' il quarto caso di «due sensi dentro lo stesso ambito», e per giunta il peggiore:
  entrambi vivono nella forma NUDA, quella che lo strumento applica da solo senza chiedere.
- **`registro` -> `occurrence_registry`, non `registry`.** La riga `registro` di «I concetti» e'
  il registro dei SERVIZI di Home Assistant, e nello stesso file, 130 righe piu' su,
  `create_tool_dispatcher` passa gia' `registry=app.get("registro_servizi")` proprio con quel
  senso. Applicare `registry` al `RegistroEsiti` avrebbe messo due cose diverse sotto lo stesso
  nome nello stesso modulo -- la stessa ragione per cui `caduti` divento' `fallen_stores` e non
  `unavailable` in `casa/strumenti.py`.
- **`motivo` e `turno`: la trappola di `stato` (lotto 10), altre due volte, e la seconda ATTRAVERSA
  UN FILE.** Lo strumento rinomina il parametro nella `def` e lascia intatte le parole chiave nelle
  CHIAMATE. Per `_who_answered_note(*, motivo)` le due chiamate erano nello stesso file; per
  `create_tool_dispatcher(app, turno=...)` una delle tre era in `api/handlers_mcp.py:438`, cioe' in
  un altro file gia' convertito, dove nessun cancello di questo lotto guardava. Chiuse a mano su
  tutte le sponde. **Cio' che NON si tocca, e sta a un carattere di distanza:**
  `nota_ripiego(motivo=..., chi_ha_risposto=...)` (`decisione_modelli.py`, file di RADICE) e
  `runner.chat(strumenti=..., dispatcher=...)` -- parole chiave di firme altrui, che restano
  italiane finche' quei file non si convertono.
- **`risposta` -> `answer` in `_downgrade_to_chain`, ma `response` in `handle_chat_reply_poll`**:
  nel primo caso la variabile tiene il testo che il modello ha prodotto (lo stesso senso che
  `schedulatore/turno.py` chiama gia' `answer`), nel secondo tiene un `web.Response`. Lo strumento
  applicava `answer` a entrambe. **Debito onesto che ne resta**: nel ramo sincrono di `handle_chat`
  la stessa cosa del primo caso si chiama gia' `response` da prima di questa fetta -- due nomi
  inglesi per un concetto solo nello stesso file. Non l'ho unificato: `response` non e' un
  identificatore italiano e non ricade nel mandato di questa fetta.
- **`costruisci_dispatcher_strumenti -> create_tool_dispatcher` e `costruisci_nucleo ->
  compose_briefing`: il suggerimento meccanico (`propose_*`) mentiva su entrambe.** `costruisci`
  e' il verbo dello strumento che PROPONE una costruzione (`costruisci -> propose`), e nessuna
  delle due funzioni propone niente: una costruisce un oggetto, l'altra compone un testo chiamando
  `casa/nucleo.compose`. `build_*` e' escluso a sua volta perche' `build` e' bloccato dalla regola
  di collisione (vedi la riga `costruzione`). Scelti `create` (riga gia' decisa, gia' usata per
  `create_rounds_per_exchange` nel lotto 10) e `compose` (riga gia' decisa) sul nome di cio' che le
  due funzioni FANNO.
- **La coppia `nucleo` esce intera, mai a meta'**: `compose_briefing` e `handle_get_briefing`
  (`api/handlers_casa.py`) si convertono in QUESTO lotto e non nel loro, perche' la prima e'
  importata per nome da `api/handlers_chat.py:28` e da `schedulatore/turno.py:128,259`.
  Rinominarne una sola avrebbe lasciato mezza coppia sulla stessa parola -- lo stesso difetto di
  `_risolvi_ancora`/`ancora` corretto poche ore prima.
- **Composti ad hoc, tutti privati e senza chiamanti esterni**: `_ripiega_sulla_catena ->
  _downgrade_to_chain` (con la parola nuova `ripiega -> downgrade`, verbo del gia' deciso `ripiego
  -> downgrade`: vedi «Verbo e sostantivo possono condividere lo stesso inglese»),
  `_nota_di_chi_ha_risposto -> _who_answered_note`, `_motivo_ripiego -> _downgrade_reason`
  (l'aggettivo prima del nome, non l'ordine italiano `reason_downgrade` del suggerimento -- il
  gemello di `schedulatore/turno.py`, che quell'ordine l'aveva accettato, e' stato allineato a
  `downgrade_reason` dalla misura ordine e preposizioni),
  `_motivo_del_piano -> _subscription_reason` (`piano (abbonamento)`, la riga annotata come
  irraggiungibile e applicata a mano), `_scadenza_min -> _deadline_min`,
  `nome_backend -> backend_name`, `dispatcher_strumenti -> tool_dispatcher`,
  `nucleo_testo`/`_nucleo_riepilogo -> briefing_text`/`_briefing_summary`, `id_turno ->
  exchange_id`, `_via -> _route` (`via` mai decisa: il nome dice cosa il valore SCEGLIE -- il
  canale che servira' il turno -- non traduce la parola).
- **Residui dichiarati, con la loro ragione**: `_STORE_DEFAULTS` (importato da
  `api/handlers_models.py`, l'ultimo file riservato di `api/`); `nota_ripiego` e le sue due parole
  chiave (`decisione_modelli.py`, radice); `risolvi_ripiego`/`reclama_scaduto`/`has_pending_chat`
  (`reasoning/queue.py`, mai convertito); `giorni`/`giorni_conservazione` (la decisione del lotto
  1, invariata); i nomi delle funzioni `test_*` che contengono un identificatore rinominato
  (`tests/test_schedulatore_wiring.py:315`) -- i nomi dei test sono prosa italiana in tutti e 172
  i file, e rinominarne uno perche' contiene un nome convertito sarebbe arbitrario finche' non si
  converte `tests/` per intero.

**Decisioni del lotto 13 (`api/handlers_models.py`), l'ultimo di `api/`.**

- **Tre nomi che il join meccanico avrebbe fatto mentire, tutti da parole SINGOLE gia' decise,
  quindi applicate senza nessuna proposta**: `guasto -> fault` su `guasto = path + ".corrotto"`
  (e' il PERCORSO del file messo da parte, non un guasto: deciso `corrupted_path`);
  `grezzo -> reading` su `grezzo = json.load(fh)` (la riga `grezzo` descrive «un cambiamento di
  stato registrato come Home Assistant lo riporta» -- qui e' il JSON non validato di un file di
  configurazione: deciso `raw`, la parola che questo stesso file usa gia' per l'ingresso non
  validato in `_clean_bridge(raw)` e `_store_keys(raw)`); e `archivio -> store` su
  `archivio = load_models_config(...)`, che invece **e' stato TENUTO**: li' «archivio» e' davvero
  il magazzino su disco di questa pagina, lo stesso concetto delle altre quattro voci del file
  (`_STORE_DEFAULTS`, `_store_keys`, `_read_raw_store`, `_set_aside_unreadable_store`), e la
  coerenza dentro il file batte un micro-miglioramento su una riga.
- **`_metti_da_parte_l_archivio_illeggibile -> _set_aside_unreadable_store`**: il suggerimento
  meccanico (`metti_da_part_l_store_unreadable`) e' il caso limite di cio' che lo strumento non
  sa fare, e serve come esempio. Il nome scelto non traduce le sei parole: usa il verbo che il
  docstring usa gia' («messo da parte»), che e' anche l'inglese naturale.
- **`_PREDEFINITI_ARCHIVIO`/`_PREDEFINITI_SEMINA -> _STORE_DEFAULTS`/`_SEED_DEFAULTS`**: due
  costanti che il suggerimento appiattiva entrambe su `default_*`. La distinzione e' quella che il
  commento gia' spiega -- i predefiniti DELL'ARCHIVIO contro quelli della SEMINA
  (`migrazione_opzioni._PREDEFINITI`, importato con `as`) -- e in inglese la porta il sostantivo
  che li qualifica. `_PREDEFINITI`, il nome VERO dentro `migrazione_opzioni.py` (file di radice
  mai convertito), resta italiano: si rinomina l'alias, mai l'importato.
- **`_CHIAVI_NOSTRE -> _OUR_KEYS`, e `nostro (api)` NON e' stata aggiunta al glossario**: `nostro`
  e' qualificato `(casa)`, quindi cieco in `api` (vedi «Il limite della qualificazione per
  ambito»). Qui il senso e' identico a quello di `casa` -- «cio' che appartiene a noi, non a Home
  Assistant» -- ma la costante e' UNA, privata, senza chiamanti, e qualificare una parola per un
  ambito intero per un solo composto privato allarga il raggio d'azione piu' di quanto serva:
  deciso a mano, riusando lo stesso inglese della riga esistente.
- **`segni -> flags`, e i suoi NOVE chiamanti**: `save_models_config(..., *, segni=False)` e' una
  parola chiave usata da `server.py` (3 volte) e da quattro file di test (6 volte). **Trovati tutti
  e nove dal controllo di chiusura**, non a mano: e' il primo file convertito con quella rete
  attiva. Otto erano marcati «certi» e uno («ambiguo») era il falso positivo previsto.
- **`nascondi_gratuiti`: il caso in cui la stessa parola e' insieme mia e altrui.** E' la parola
  chiave del MIO `_fetch_openrouter_models` (rinominata `hide_free_models`, 7 chiamanti nei test
  aggiornati), **e** la parola chiave di `decisione_modelli.componi_pannello` (file di radice, 6
  chiamanti che restano italiani), **e** una chiave dell'archivio JSON (`models_config[
  "nascondi_gratuiti"]`, invariata ovunque, frontend compreso). Tre cose con lo stesso nome, due
  che non si toccano: il controllo di chiusura le ha elencate tutte e dodici lasciando a chi legge
  la separazione, che e' esattamente cio' che dichiara di fare. Il parametro NON e' diventato
  `hide_free` perche' quel nome e' gia' la locale a due righe di distanza (`hide_free =
  bool(...)`, la coercizione): due nomi per l'ingresso grezzo e per il valore validato sono la
  stessa disciplina di `raw` e delle sue versioni pulite in questo file, un solo nome sarebbe
  stato `hide_free = bool(hide_free)`.
- Composti ad hoc, tutti privati e senza chiamanti esterni: `_pulisci_ponte -> _clean_bridge`,
  `_pulisci_ollama -> _clean_ollama`, `_pulisci_modello_del_piano -> _clean_subscription_model`
  (`piano (abbonamento)`, applicata a mano come nel lotto 12), `_chiavi_archivio -> _store_keys`,
  `_leggi_archivio_grezzo -> _read_raw_store`, `_credenziali_dei_cinque ->
  _credentials_of_the_five`, `_modelli_in_uso -> _models_in_use`, `_SEGNI_MIGRAZIONE ->
  _MIGRATION_FLAGS`, `_ponte_acceso -> _bridge_on`, `_scadenza_ponte -> _bridge_deadline`,
  `_timeout_ollama -> _ollama_timeout`, `modello_ollama`/`modello_piano`/`modello_scelto ->
  `ollama_model`/`subscription_model`/`chosen_model`, `voluto -> requested` (riusando la riga
  `richiesto`, gia' decisa: e' il provider chiesto esplicitamente nella query),
  `in_uso -> in_use`, `nascondi -> hide_free`, `ricalcola -> recompute`,
  `strategia -> strategy`, `scrivibili -> writable`.
- **L'ordine delle parole, applicato a ogni nome di questo lotto dopo un rilievo della misura
  dedicata.** L'inglese mette il modificatore PRIMA della testa; l'italiano dopo. E' il difetto n.1
  del par. 2 della specifica -- previsto per iscritto il 29/08 e mai verificato da nessuno, perche'
  **un nome fatto di parole inglesi in ordine italiano non stona mai abbastanza da fermare chi
  legge**. Due casi trovati proprio qui, e corretti insieme perche' sono lo stesso concetto con e
  senza suffisso di unita': `_timeout_ollama -> _ollama_timeout` (locale, `handlers_models.py:526`)
  e `timeout_ollama_s -> ollama_timeout_s`, che e' un parametro di
  `decisione_modelli.componi_topologia` -- quindi corretto su tutte e tre le sponde (la `def`, la
  chiamata qui, e `tests/test_decisione_modelli.py:452`), col controllo di chiusura a confermare
  zero chiamanti rimasti indietro. **Il secondo e' il caso istruttivo**: `ollama_timeout_s` e' fatto
  di parole gia' inglesi, quindi nessun dry-run lo avrebbe mai segnalato -- solo una misura
  sull'ORDINE poteva trovarlo. Nella stessa firma resta `scadenza_ponte_min`, che invece e' italiano
  di parole E di ordine e uscira' quando si convertira' quel modulo di radice: due difetti diversi
  nella stessa riga, e solo uno visibile allo strumento.
- **Cio' che resta italiano, e non e' un residuo**: ogni parola chiave verso
  `decisione_modelli.componi_adesso`/`componi_topologia`/`componi_pannello` (`catena`,
  `credenziali`, `modelli`, `ponte_attivo`, `scadenza_ponte_min`, `esiti`, `adesso`, `valori`,
  `fonte`, `scelto`, `auto_risolto`, `indirizzo`, `nascondi_gratuiti`) e i
  nomi importati da li' (`FINE_CATENA`, `modello_cli`, `piano_ha_il_token`): sono firme di un
  modulo di RADICE che questa fetta non converte. `registro_esiti.tutti()` e' protetto due volte
  -- e' un plurale, quindi mai applicato da solo, ed e' nella guardia `_METODI_REGISTRO_ESITI`
  aggiunta dal lotto 12.

**Decisioni del lotto 14 (`proxy/_sanitize.py`), il primo di `proxy/`.**

- **`_TRONCATO -> _TRUNCATED`**, auto-applicato dal join (`troncato -> truncated` era gia' deciso).
  **Il VALORE della costante, `" [troncato]"`, non si tocca**: e' la stringa che compare nel testo
  che il modello e la persona leggono, e le stringhe sono fuori dal perimetro della fetta. La
  costante e' privata e senza importatori esterni (verificato con un grep su `hiris/`, `tests/`,
  `scripts/` e `docs/`): le uniche altre occorrenze erano tre citazioni fra backtick nello stesso
  file, aggiornate.
- **`MAX_TESTO_LIBERO -> MAX_FREE_TEXT`, e NON aggiungendo `libero -> free` al glossario.** Il
  suggerimento meccanico era `max_text_libero`, cioe' meta' nome. Ma `free` **e' gia' preso**:
  `gratuito -> free`, fra le parole ordinarie, e i due sensi sono davvero diversi -- «senza costo»
  contro «non vincolato». Scrivere `libero -> free` avrebbe messo due parole italiane di senso
  diverso sullo stesso inglese, che e' esattamente cio' che la guardia `Collisione` esiste per
  fermare, e lo avrebbe reso **permanente** invece che locale. Il nome viene percio' dall'interfaccia
  che quella costante gia' alimenta -- `sanitize_ha_free_text`, «HA free text», inglese gia' scritto
  in quel file da prima della fetta -- come `pending_only`, `turni -> turns` e `da_anchor`.
  **`libero` resta undecided e NON protetta**: chi la incontra altrove deve rileggere questa riga e
  la nota accanto a `gratuito`, non decidere di sfuggita.
- Nessun'altra rinomina: il resto del file era gia' inglese, docstring compresi (e' un modulo che
  nasce con la prosa in inglese, unico in `hiris/app/` -- non si traduce all'italiano, come non si
  traduce niente: il perimetro e' il codice).


**Decisioni del lotto 15 (`proxy/entity_cache.py`).**

- **`inventario_leggibile -> inventory_is_readable`, NON `inventory_readable`** (il suggerimento
  meccanico). `leggibile -> readable` e' deciso e la traduzione pezzo per pezzo e' corretta: e'
  l'ORDINE a essere sbagliato, ed e' lo stesso difetto della misura del 31/08 (`STATE_READABLE ->
  READABLE_STATE`). Ma qui la correzione dell'ordine non basta: `readable_inventory` nominerebbe
  una COSA (un inventario leggibile) mentre questa funzione dichiara un FATTO (che l'inventario si
  puo' leggere) e torna un booleano. **Un predicato non e' un sintagma nominale**: si scrive come
  una frase -- `inventory_is_readable(cache)` -- e ogni sito di chiamata lo legge come tale
  (`if not inventory_is_readable(self._cache):`). Precedenti nel prodotto: `_can_respond`,
  `_allows_empty_target`, `in_baseline`.
- **`inventario_non_leggibile -> unreadable_inventory_error`, e la coppia SMETTE di essere una
  coppia morfologica.** In italiano i due nomi erano `X` e `non_X`; in inglese non possono esserlo,
  perche' non fanno la stessa cosa: il primo torna un booleano, il secondo torna **il dizionario
  d'errore da restituire subito al chiamante**, oppure `None`. Il nome dice cosa la funzione
  RESTITUISCE. E' la stessa regola gia' scritta per `non`: sparisce nella traduzione
  (`non_disponibili -> unavailable`, `_NON_TROVATA -> _NOT_FOUND`), non diventa `non_readable`.
- **`ERRORE_INVENTARIO_ASSENTE -> NO_INVENTORY_ERROR`, senza decidere `assente`.** `assente` non e'
  mai stata decisa, e il candidato ovvio (`missing`) e' gia' preso da `mancante -> missing`: sarebbe
  la stessa collisione permanente evitata per `libero`/`free` nel lotto 14. Il nome usa invece la
  forma gia' in uso nel prodotto per esattamente questo caso, `_MSG_NESSUN_PROVIDER ->
  _NO_PROVIDER_MSG` (lotto 7).
- **`ERRORE_INVENTARIO_NON_PRONTO -> INVENTORY_NOT_READY_ERROR`, senza decidere `pronto`.**
  `not_ready` e' gia' l'inglese che il prodotto usa per questa identica forma
  (`casa/strumenti.py::_registry_not_ready`): riuso, non traduzione. Aggiungere una riga nuda
  `pronto -> ready` avrebbe riaperto tutti e sei gli ambiti chiusi insieme (vedi «Ambito chiuso»)
  per un guadagno che il riuso dava gratis. `assente` e `pronto` restano **undecided e non
  protette**.
- **`_ATTRIBUTI_TESTO_LIBERO -> _FREE_TEXT_ATTRIBUTES`**: `free_text` e' lo stesso inglese gia'
  scelto nel lotto 14 per `MAX_FREE_TEXT`, nel modulo che questa costante alimenta
  (`sanitize_ha_value` sugli attributi liberi del `media_player`) -- due lotti, un solo nome per un
  solo concetto.
- `chiave -> key` auto-applicato (parola singola gia' decisa).
- **Il nome di un test NON si rinomina**:
  `tests/test_strumenti_conoscenza.py:408::test_senza_inventario_leggibile_lo_stato_si_dichiara_non_letto`
  contiene le tre parole ma e' prosa italiana, come i nomi di test in tutti e 172 i file. Le
  CITAZIONI dentro i docstring degli stessi file sono state aggiornate: sono riferimenti, non prosa.


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
| guarda (casa) | Il dettaglio completo di UNA cosa sola della casa -- area, entita', dispositivo, automazione, script o ricordo -- dato il suo identificatore ESATTO, mai un nome libero | view | ✓ arriva |
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
> **Dubbio chiuso durante la review indipendente del Task 7 (`azione/`): il metodo interno dietro
> `conferma` diventa `apply`, non piu' `applica`.** Il dubbio era se questo confondesse `apply` col
> nome dello STRUMENTO (`confirm`) -- non lo confonde, perche' sono due livelli diversi: `confirm`
> resta il nome che il modello invoca (il consenso esplicito, la ragione scritta sopra per cui
> resta `confirm` e non `apply`), `apply` e' solo l'implementazione Python dietro quel nome, mai
> esposta al modello. Aggiunta la riga ordinaria `applica -> apply` (sopra, «Le parole ordinarie»);
> `Workshop.applica` (`azione/costruzione/officina.py:328`) e' ora `Workshop.apply`. Stessa
> famiglia, stesso giro: `Workshop.proponi`/`ConstructionStore.proponi` -> `propose` (riga
> ordinaria `proponi -> propose`, coerente con la nota qui sopra su `costruisci -> propose`, che
> gia' citava questo stesso metodo come indizio), `Workshop.ripristina` -> `restore` (riga
> ordinaria `ripristina -> restore`, sotto), `ConstructionStore.rivendica` -> `claim` (riga
> ordinaria `rivendica -> claim`, sopra) — le interfacce pubbliche di `ConstructionStore`/`Workshop`
> non avevano piu' nessuna ragione per restare a meta' tradotte, con alcuni verbi in inglese
> (`read`, `list`) e altri no.
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

> **`guarda`: un difetto latente del lettore, trovato dalla review del Task 6 -- corretto qui,
> non solo nello strumento.** Questa riga (sopra: «Il dettaglio completo di UNA cosa sola della
> casa...», -> `view`) e la riga `guarda` di «Le parole ordinarie» (-> `look`) erano ENTRAMBE nude
> (nessuna parentesi ambito), nella stessa mappa piatta: `leggi_glossario()` processa le tabelle in
> ordine e l'ULTIMA scritta vince in silenzio -- qui `view`, senza che nessuna riga lo dichiarasse.
> Il caso vero (Task 6, `cervello/osservatore.py`) ha aggiunto una TERZA lettura, `watch`
> (`guarda_cambio`/`guarda_sistema`, il verbo del `Watcher`), rendendo `guarda` un omonimo a tre vie
> mai dichiarato come tale. Corretto cosi': la riga qui sopra e' ora `guarda (casa)` (il vero
> identificatore che descrive, `casa/domande.py::guarda`); `guarda (cervello) -> watch` e' una riga
> a se' in «I concetti»; la riga `guarda -> look` di «Le parole ordinarie» e' stata tolta -- non
> risultava applicata a nessun identificatore vero in nessun sottosistema gia' convertito (verificato
> `grep` sui tre gia' fatti), era un default generico che nascondeva la collisione invece di
> risolverla. `leggi_glossario()` ora solleva se due righe nude finissero di nuovo sullo stesso nome
> con inglesi diversi (vedi `scripts/rinomina.py`): questa correzione lo rende silenzioso di nuovo
> per il caso vero, ma la guardia resta per il prossimo.

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
| `GENRES` (ex `GENERI`, rinominata dal Task 6 -- solo il nome della costante, non i valori) | funzionamento · presenza · energia · guasto · sicurezza · bilancio | `cervello/oggetti.py:44`; colonna `genere` in `cervello/archivio.py:91` e `azione/cronaca.py:65` |  |
| `ASPECTS` (ex `GAMBE`, rinominata dal Task 6 -- solo il nome della costante, non i valori) | chi c'e' · comfort · dispersione · energia · buono stato · sicurezza | `cervello/pavimento.py:21` — i nomi delle sei gambe del pavimento dell'osservatore |  |
| `SPECIE` | fai · chiedi | `schedulatore/promessa.py:21`; colonna `specie` in `schedulatore/archivio.py:34` |  |
| `STATES_CONCLUSI` (ex `STATI_CONCLUSI`, rinominata durante la conversione di `schedulatore/` -- solo il nome della costante, non i valori; non composta in `..._STATES` per il rischio di confusione con l'elenco vivo delle entita' di Home Assistant, vedi la nota sopra) | mantenuta · saltata · disdetta · fallita | `schedulatore/promise.py:22` — stato concluso delle promesse |  |
| `STATES_SOSPESO` (ex `STATI_SOSPESO`, rinominata dal Task 7 (`azione/`), gia' applicata a `schedulatore/promise.py` durante la sua conversione -- solo il nome della costante, non i valori; stessa cautela sulla composizione della riga sopra) | in_attesa · in_corso | `azione/costruzione/versioni.py:36` e `schedulatore/promise.py:34` — definita due volte, stesso valore |  |
| `BALANCE_DIRECTIONS` (ex `DIREZIONI_BILANCIO`, rinominata dal Task 6 -- solo il nome della costante, non i valori) | produzione · autoconsumo · immissione · prelievo · carica · scarica · consumo | `cervello/oggetti.py:71` — le direzioni del bilancio energia dell'osservatore |  |
| `FAMIGLIE` | credenziale · modello · irraggiungibile · scaduto · altro | `esiti_provider.py:63` — famiglie di esito dei provider LLM |  |
| `OPERATIONS` (ex `_GESTI`, rinominata dal Task 7 -- solo il nome della costante, non i valori; invisibile agli Step 1/2 perche' plurale, trovata solo eseguendo lo strumento sull'ambito `azione`) | crea · modifica · cancella | `azione/costruzione/officina.py:56` — i gesti sulle costruzioni |  |
| `_TIPI_COMPORTAMENTO` | automazione · script | `casa/domande.py:68` — i tipi di comportamento della casa |  |
| `HUMAN_ACTORS` (ex `ORIGINI_UMANE`, rinominata dal Task 7 -- solo il nome della costante, non i valori; stessa invisibilita' di `OPERATIONS` sopra, stessa riga) | pagina | `azione/costruzione/officina.py:54` — l'origine di un'azione quando e' un umano a farla |  |
| `_MIGRATION_FLAGS` | seminato · catena_seminata · piano_seminato | `api/handlers_models.py:94` — i segni lasciati da una migrazione gia' avvenuta |  |
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

**Corretto durante la review del Task 6: il conteggio diceva "cinque casi", eseguito davvero ne
restituisce sette -- gli altri due erano gia' spiegati altrove nel documento, solo non contati
qui.** `reading` (`cambi`/`grezzo`): non cambia con la rinomina del rilievo A2 (ne' col candidato
intermedio bocciato, `sample` -- vedi la nota sotto la tabella «I concetti»), e' lo stesso caso
che prima si chiamava `raw` con la stessa identica giustificazione — un solo concetto, due nomi
italiani. `count` (`conta`/`quante`),
`list` (`elenco`/`elenca`) e `read` (`letto`/`leggi`) sono forme flesse della stessa parola
ordinaria -- `write` (`scrittura`/`scrivi`) e' la stessa famiglia, il lato opposto della stessa
coppia gia' vista per `read`. `promise` compare sia come concetto (`promessa`) sia come nome di
strumento (`prometti`): **non e' una svista**, e' lo stesso concetto visto dai due lati che questa
fetta separa ovunque -- il dato e lo strumento che lo scrive -- documentato per esteso nella nota
sotto la tabella dei 13 nomi degli strumenti. `reference` (`riferimento (casa)`/`riferimento
(memoria)`) e' un omonimo per ambito, non una forma flessa -- documentato per esteso nella nota
«Il limite della qualificazione per ambito».

**Rimisurato il 31/08, ed e' il caso in cui il documento sul controllo era piu' vecchio del
controllo: il comando restituisce OGGI 18 casi, non otto.** La frase qui sotto («se questo
comando restituisse un NONO caso non elencato qui, sarebbe quello a essere una collisione vera»)
era vera quando fu scritta e ha smesso di esserlo senza che nessuno la rileggesse -- il glossario
e' cresciuto di dieci righe qualificate e di parecchie coppie verbo/sostantivo, e ognuna aggiunge
un caso. **I dieci arrivati dopo appartengono tutti a famiglie gia' documentate qui sotto**, e si
leggono cosi':

- **omonimi per ambito** (stessa parola italiana, due ambiti): `tether` (`ancora (api)`/
  `ancora (memoria)`), `row` (`riga`/`riga (api)`) -- la stessa famiglia di `reference`;
- **verbo e sostantivo dello stesso atto**, la classe ACCETTATA descritta piu' su: `downgrade`
  (`ripiega`/`ripiego`), `cut` (`tagliato`/`taglio`);
- **un concetto solo con due nomi italiani**, la stessa famiglia di `reading` (`cambi`/`grezzo`):
  `memory` (`memoria`/`ricordo`), `known` (`conosciuto`/`note (casa)`), `verb` (`specie`/`verbo`),
  e **`route` (`via`/`rotta (proxy)`, aggiunto il 31/08)** -- `via` e' il canale che servira' il
  turno, `rotta` e' il percorso HTTP: due parole italiane per la stessa idea di «strada», che in
  inglese e' una parola sola. Lo dichiaro qui invece di inventare un secondo inglese per non
  farlo comparire: un `endpoint` scritto solo per far tacere questo controllo sarebbe un nome
  scelto dal controllo, non dal significato.

**La conseguenza operativa, che ha smesso di essere «il nono caso»**: il numero cresce da solo, e
contarlo non e' piu' il controllo. Il controllo e' che **ogni caso che il comando restituisce sia
riconducibile a una delle tre famiglie qui sopra**; un caso che non lo e' -- due parole italiane
di senso diverso finite sullo stesso inglese senza essere ne' omonimi per ambito, ne' verbo e
sostantivo, ne' due nomi dello stesso concetto -- e' la collisione vera da correggere. E' la stessa
ragione per cui `libero -> free` non e' stato scritto (lotto 14) e `assente -> missing` non e'
stato scritto (lotto 15): li' le due parole dicevano cose diverse davvero.

**Aggiornato durante la review indipendente del Task 7 (`azione/`): l'ottavo caso e' arrivato, ed
e' spiegato, non una collisione vera.** `propose` (`proponi`/`costruisci`) e' la STESSA coppia
concetto/nome-di-strumento gia' vista per `promise` sopra -- `proponi` e' il metodo Python che
implementa l'azione, `costruisci` e' il nome che il modello invoca per chiamarla -- documentato per
esteso nella nota su `costruisci -> propose`, sotto la tabella dei 13 nomi degli strumenti. Se
questo comando restituisse un NONO caso non elencato qui, sarebbe quello a essere una collisione
vera da correggere, non da spiegare.

**3. Nessun file di codice toccato, e il linter resta verde:**

```bash
git status --porcelain   # deve mostrare solo docs/GLOSSARIO.md
python -m ruff check     # deve dire "All checks passed!"
```
