# Ciò che il modello non sa di poter chiedere — specifica

*14 agosto 2026. Nasce da quattro segnalazioni del proprietario che usa il prodotto. Due sono lo
stesso difetto; le altre due sono piccole e stanno nello stesso giro.*

## 0. Il criterio non è nuovo: è già scritto, e va applicato

Il nucleo — il testo che il modello ha **sempre** davanti — dichiara nel proprio modulo cosa merita
di starci dentro (`hiris/app/casa/nucleo.py`, docstring):

> **il nucleo CONTA, non elenca.**
> La priorità vera è **«cosa il modello perde la possibilità di SAPERE che esiste»**, perché il
> nucleo è l'unico posto da cui può scoprirlo.

Questa fetta **non introduce un criterio**: applica quello che c'è a due punti in cui non è mai stato
applicato. Ed è il motivo per cui i primi due punti sono **un difetto solo**, non due.

## 1. Il caso che l'ha fatta nascere

Il proprietario ha chiesto se l'irrigazione fosse partita quella mattina e quanto. HIRIS ha elencato
**valvole scollegate**, senza raggrupparle.

La macchina per raggruppare **esiste e funziona**: `guarda(tipo="dispositivo")` restituisce un
dispositivo con le sue entità, e i dispositivi sono nell'indice di `cerca`
(`memoria/riconoscitore.py::_ARCHIVI`). Il problema è che **il modello non sa che quel dispositivo
c'è**: il nucleo è organizzato piano → area → conteggi per dominio, e **nessun dispositivo compare in
nessuna riga**. Duecentoquaranta dispositivi conosciuti, zero mostrati.

Quindi per raggruppare avrebbe dovuto **indovinare** di cercare un dispositivo il cui nome non
conosce. È esattamente la condizione che il criterio del nucleo condanna.

## 2. Il punto esatto in cui l'informazione si perde

> La riga **«Esterno: 4 valve»** è vera, e distrugge una cosa: **non dice se sono quattro dispositivi
> o uno.**

Quando sono quattro cose separate va bene così — il conteggio è tutto ciò che serve. Quando sono
**un irrigatore solo**, la riga ha cancellato l'unica informazione che contava.

**La regola, e si spegne da sola:**

> **Una riga di conteggio va annotata quando le entità che conta appartengono a MENO dispositivi di
> quante sono.**

Nel caso vero: `Esterno: … 4 valve (Irrigazione giardino) …`.

- Un dispositivo con **una sola** entità non produce nessuna annotazione: le lampadine singole non
  costano niente.
- Il costo è **limitato per costruzione**: si paga solo dove il raggruppamento *è* l'informazione.
- Non è «mettere i dispositivi nel nucleo» — 240 righe sfonderebbero il budget e violerebbero
  «conta, non elenca». È **annotare i conteggi che mentono per omissione**.

Il dato è già lì e costa niente: `entita.dispositivo_id` esiste in `casa/archivio.py` **con il suo
indice** (`idx_entita_dispositivo`), e la tabella `dispositivi` porta i nomi.

**Vincolo:** il nucleo ha un **budget con taglio dichiarato** (`_avviso_taglio`,
`_RISERVA_MINIMA_RIGHE_CASA`, la sezione «ciò che HIRIS ignora»). Le annotazioni entrano **dentro
quel budget e dentro quella disciplina**: se il taglio le tocca, il taglio si dichiara come già fa
per tutto il resto. `componi()` **resta pura** — nessun archivio aperto, nessuna rete.

## 3. Lo stesso dovere, applicato alla ricerca

Un'entità **senza nome** oggi **non esiste nello spazio in cui si cerca**: `casa/archivio.py:133`
prende il nome da `name or original_name` del registro — su questa casa **entrambi vuoti** — e
`memoria/riconoscitore.py` costruisce i termini solo da `nome` + `alias`. Nessun nome ⇒ nessun
termine ⇒ **invisibile**.

È **lo stesso criterio del nucleo**: il modello perde la possibilità di sapere che quella cosa
esiste. Ha già bruciato quattro giri di `cerca` sulle abat-jour prima di trovarle per un'altra
strada.

**Cosa deve diventare vero:**

- **Il ripiego è il `friendly_name`**, non l'`entity_id`: è ciò che Home Assistant mostra all'utente
  ed è la parola che una persona userebbe parlando. Lo specchio dello stato lo conserva già.
  Un id tecnico va semmai marcato come **dedotto**, mai spacciato per un nome dichiarato.
- **`{"trovati": []}` smette di essere ambiguo.** Oggi «non c'è nessuna cosa con quel nome» e «non ho
  potuto guardare» hanno la stessa faccia, e la seconda è ciò che ha bruciato quei quattro giri. Chi
  legge deve poterle distinguere.
- **Da guardare, non necessariamente da chiudere:** `cerca("luci")` restituisce `sensor.lights` — un
  contatore, non delle luci. È cecità al dominio; se la correzione è piccola si prende, altrimenti si
  dichiara.

## 4. Le due piccole, nello stesso giro

**a) Le targhette degli strumenti escono dalla chat, la traccia entra nel log.**
Sotto ogni risposta compaiono targhette cliccabili col nome dello strumento chiamato
(`static/chat/messages.js::appendDebug`, alimentate da `payload["debug"]["tools_called"]`, disegnate
in **due** punti di `send.js`). Il proprietario non le vuole.

**Attenzione, e va detto perché ribalta l'intervento:** al livello `debug` quelle chiamate **non
vengono tracciate affatto** — l'unica riga che parla di strumenti si scrive **quando uno fallisce**.
Togliere le targhette e basta **non sposta l'informazione: la cancella**. Ed è l'informazione che ha
fatto capire il caso delle abat-jour.

Quindi: **targhette fuori + traccia nel log a `debug`**. E se dopo la rimozione il campo `debug` non
ha più lettori, **esce anche dalla risposta** invece di viaggiare per niente.
*(Il rumore che rendeva il log illeggibile è già chiuso: dalla 3.0.0 il lavoratore del ponte si ferma
quando non serve.)*

**b) `fable` fra gli alias del piano, e l'elenco di Claude si chiede al servizio.**
`decisione_modelli.ALIAS_DEL_PIANO` offre `haiku`/`sonnet`/`opus`; `agent/runner.modello_cli` produce
gli stessi tre, e un test li tiene legati. **Sono allineati e tutti e due indietro:** manca `fable`, e
il traduttore davanti a un nome che non riconosce **ricade su `sonnet`** con un avviso.

E **Claude è l'unico dei quattro provider con l'elenco scritto a mano** (`_CLAUDE_FALLBACK`): OpenAI,
Ollama e OpenRouter lo **chiedono** ai rispettivi servizi. Anthropic ha un endpoint: si può chiedere,
con l'elenco a mano che resta solo come riserva.

**E il rimedio strutturale, che vale più dei due:** la CLI dichiara nell'evento `init` **quale modello
sta usando davvero**, e `agent/runner.verifica_init` quella riga **la legge già** per un altro motivo.
Confrontare il modello chiesto con quello dichiarato trasforma una sostituzione silenziosa in un
fatto detto. È «verificare invece di insegnare» — lo stesso principio dell'azione, applicato ai
modelli.

## 5. Cosa NON fa questa fetta

- **Il flag «limitati agli argomenti di casa» resta fuori.** Il proprietario vuole ripensarlo insieme
  alla possibilità che HIRIS **cerchi nel web**. Fatto verificato che serve a quella decisione: quel
  flag **non impedisce di cercare in rete** — impedisce di *rispondere fuori tema*
  (`claude_runner.RESTRICT_PROMPT`). Sono **due assi diversi** — *di cosa parli* e *dove prendi i
  fatti* — che oggi si confondono solo perché HIRIS non ha nessun modo di uscire di casa.
- **Non si mettono i dispositivi nel nucleo come sezione**: violerebbe «conta, non elenca».
- **Non si tocca il budget del nucleo**: le annotazioni stanno dentro quello che c'è.
- **Non si costruisce la ricerca nel web**: è una fetta sua, e dipende dalla decisione sul flag.

## 6. Gli invarianti

1. **Ciò che il modello non può scoprire altrove sta nel nucleo; il resto si va a prendere.** È il
   criterio già scritto: questa fetta lo applica, non lo cambia.
2. **`componi()` resta pura** e il taglio resta dichiarato.
3. **Nessuna informazione sparisce spostandosi**: ciò che esce dalla chat entra nel log, e si prova
   che ci sia arrivato.
4. **Un'assenza dichiarata non somiglia a un'assenza taciuta**: «non c'è» e «non ho potuto guardare»
   restano distinguibili ovunque.
5. **Nessun elenco scritto a mano che il servizio possa dichiarare** — e dove un elenco resta
   inevitabile, si confronta con ciò che il sistema dice di aver usato.

## 7. Le verifiche che solo la casa vera può dare

- **L'irrigazione**: la stessa domanda del 14 agosto — *«è andata stamattina, e quanto?»* — deve
  ottenere una risposta raggruppata. **È il metro della fetta**, non un esempio.
- **Le abat-jour**: `cerca` deve trovarle senza quattro giri.
- **Il nucleo su una casa da 1.225 entità e 240 dispositivi**: quante annotazioni compaiono davvero,
  e se il taglio le tocca. Il banco non può dirlo — nessuna finta ha quella forma.
- **Le targhette**: che siano sparite dalla chat **e** che la traccia si trovi nel log.
