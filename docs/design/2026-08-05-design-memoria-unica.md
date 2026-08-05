# Una memoria sola

**Data:** 5 agosto 2026
**Stato:** approvato nelle decisioni di fondo — nasce da un bug trovato nella verifica live di
`1.1.0-beta.17`.
**Dipende da:** `2026-08-04-scope-hiris.md` · `2026-08-04-cosa-sa-il-brain.md`

---

## 0. Da dove viene

L'utente ha scritto in chat che d'inverno la temperatura ideale del soggiorno è 19.5. HIRIS ha
risposto **«preso nota»**. Nella sezione Memoria non c'era niente.

Indagando sono venuti fuori **tre difetti distinti**, e nessuno dei tre è quello che sembrava.

**① Nessuno dice a HIRIS di ricordare.** Il prompt di sistema nomina la memoria una volta sola, per
dire che lo strumento esiste. Le sue quattro «regole fondamentali» riguardano tutte il *non
inventare* e il *non dichiarare azioni mai eseguite*. **Nessuna dice quando salvare.** Il modello ha
lo strumento e nessuna istruzione per usarlo: a un'affermazione risponde con cortesia, non con
persistenza. *«Preso nota»* è precisamente ciò che dice un modello che non ha salvato niente — ed è
anche, ironicamente, la dichiarazione di un'azione mai eseguita che quel prompt vieta.

**② Ciò che HIRIS sa non è visibile da nessuna parte.** La sezione si chiama «Memoria» ma chiama solo
`api/knowledge/pending`. In tutto il codice c'è **una sola** chiamata a `list_items`, ed è
`status="pending"`. Quindi la pagina mostra la **coda di approvazione**, non la memoria — e ciò che
approvi **sparisce** dall'unico posto in cui potevi vederlo.

**③ Due gestioni per una cosa sola.** È il difetto che li tiene insieme.

---

## 1. Il difetto strutturale: una fusione fatta a metà

`save_memory` e `save_knowledge` chiamano **la stessa funzione sulla stessa tabella**. Cambia solo
cosa le passano:

| | `save_memory` | `save_knowledge` |
|---|---|---|
| `kind` | `"memory"` fisso | scelto dal modello: fatto, preferenza, scadenza, spesa, nota |
| **approvazione** | `approved` — nessun gate | `pending` — richiede un sì |
| **ambito** | legato **a un chatbot** | vale per tutta la casa |
| **scadenza** | sì, da `retention_days` | nessuna |
| campi strutturati | nessuno | titolo, importo, data, categoria |
| riservatezza | sempre `normal` | scelta dal modello |

Dal punto di vista di chi usa il prodotto:

> *«preferisco 21 gradi»* → salvata **subito, senza chiedere**, ma **legata a un solo chatbot** e con
> **scadenza a 90 giorni**.
> *«la TARI scade il 15»* → **chiede il permesso**, ma vale per tutta la casa e **non scade mai**.

Perché una preferenza non richiede approvazione e una scadenza sì? Perché la preferenza scade e la
scadenza no? Perché ciò che dici a un chatbot è invisibile all'altro? **Nessuna di queste domande ha
una risposta.** Sono il residuo di due funzioni costruite in momenti diversi — la memoria RAG ad
aprile, il second brain a giugno — fuse a luglio **a livello di archivio** e mai a livello di
superficie.

> **Lo store è già uno. Sono rimaste due gestioni sopra.**

### La distinzione che sopravvive

Non «memoria contro conoscenza», ma: **questa cosa ha una struttura?** Una scadenza ha una data, una
spesa ha un importo, una preferenza no. È una **proprietà dell'elemento** — un campo che c'è o non
c'è — non una ragione per due strumenti, due politiche, due ambiti e due scadenze.

---

## 2. Le decisioni

### ① HIRIS ricorda subito, tu correggi dopo

Ciò che gli dici entra **immediatamente** nella memoria. Niente coda di approvazione.

**Perché:** dire tre cose in una conversazione non deve produrre tre approvazioni da smaltire, e
soprattutto non deve produrre un HIRIS che *non se le ricorda finché non le confermi*. Il controllo
si esercita **dopo**, guardando ciò che sa e correggendolo — che è anche l'unico momento in cui hai
davvero il contesto per giudicare.

Metà del sistema si comporta già così: `save_memory` scrive già-approvato. Questa decisione estende
il comportamento esistente, non ne inventa uno.

### ② La memoria è di HIRIS, e porta il nome di chi l'ha detta

Ciò che dici lo sa **HIRIS**, non il chatbot con cui capitava di parlare. Dici una volta che d'inverno
il soggiorno sta bene a 19.5, e vale ovunque: chat, ragionatore proattivo, resoconto.

**Ogni elemento registra chi l'ha detto**, e l'interfaccia lo mostra. Sapere *da dove viene* una cosa
è metà del poterla giudicare.

**Con una eccezione deliberata:** oggi il campo che registra l'autore serve anche a **nascondere** le
cose agli altri abitanti. Rendere tutto visibile a tutti degraderebbe una protezione esistente. Quindi:

> **Ciò che riguarda la casa è di tutti e porta il nome di chi l'ha detto. Ciò che è marcato sensibile
> resta di chi l'ha detto.**

Riducibile a una impostazione per le case a un solo abitante.

### ③ La memoria non evapora

Niente scadenza a 90 giorni. Ciò che HIRIS sa della tua casa non deve svanire perché è passato un
trimestre. La conservazione diventa un'impostazione, spenta di default.

### ④ Un solo strumento, e il prompt dice quando usarlo

Uno strumento di salvataggio e uno di richiamo. I campi strutturati — data, importo, categoria —
restano **opzionali sull'elemento**: si valorizzano quando ci sono, e sono ciò che permette di
chiedere «quali scadenze questo mese» invece di cercare a tentoni.

E il prompt di sistema acquisisce la regola che oggi non c'è: **quando l'utente dice qualcosa che vale
la pena tenere, si salva.** Senza quella, l'unificazione non basta: il modello continuerebbe a
rispondere «preso nota».

### ⑤ La sezione «Memoria» diventa ciò che HIRIS sa

Non più la coda di approvazione. L'elenco di ciò che HIRIS sa, con — per ogni elemento — **chi l'ha
detto**, **quando**, e i pulsanti per **correggere** e **cancellare**.

È la superficie che rende vera la decisione ①: si può ricordare subito solo se poi si può guardare e
correggere.

---

## 3. Cosa questo elimina

Il Refactor 2.0 non aggiunge soltanto (`CLAUDE.md`, «Ogni fetta è anche pulizia»).

| Esce | Perché |
|---|---|
| uno dei due strumenti di salvataggio, e uno dei due di richiamo | erano la stessa funzione con due nomi |
| la coda di approvazione (`status='pending'` e le sue rotte) | non c'è più niente da approvare |
| il legame `chatbot_id` sugli elementi di memoria | la memoria è di HIRIS, non del chatbot |
| la scadenza automatica a 90 giorni | ciò che HIRIS sa non evapora |

**Migrazione:** le righe oggi ferme in `pending` vengono **approvate**. Sono lì solo perché il
pulsante rispondeva `503` — non perché qualcuno abbia deciso di non approvarle.

---

## 4. Cosa questo documento non decide

- **La forma esatta della pagina** — quali colonne, come si corregge un elemento, se si raggruppa per
  tipo o per data.
- **Il criterio con cui il modello decide che una cosa vale la pena tenere.** Il prompt gli dirà di
  salvare; *cosa* meriti memoria è materia di prompt, e va tarato sull'uso reale.
- **Se il ritratto della casa debba includere ciò che HIRIS ha imparato** — era la fetta 2c, e questa
  decisione la rende più semplice.
- **Il destino di `sensitivity` a lungo termine**: qui resta com'è perché è l'unica protezione fra
  abitanti, ma nasce da un'epoca in cui la memoria era per-chatbot.

## 5. La prova, dal sistema vivo

Interrogato il database dell'add-on in produzione (5 agosto 2026, `1.1.0-beta.17`):

| tipo | stato | righe |
|---|---|---|
| `insight` | approved | **199** |
| `memory` | approved | **3** |
| `note` | approved | 1 |
| **qualunque tipo** | **`pending`** | **0** |

Nessuna riga contiene il dato che l'utente aveva dichiarato in chat. Le uniche corrispondenze
testuali su «soggiorno» e «19» sono insight del digest notturno, per coincidenza.

**Difetto ① CONFERMATO.** Il modello ha risposto «preso nota» senza chiamare alcuno strumento.

E due fatti che l'indagine non cercava:

**Zero righe `pending`, da sempre.** La sezione «Memoria» interroga **solo** i pending. Su questa
installazione quella pagina **non ha mai avuto nulla da mostrare, in tutta la vita dell'add-on** —
ed è nella navigazione, con un contatore e un badge. Non è che manchi un elemento: la pagina è vuota
per costruzione.

**Tre ricordi in quattro mesi, contro 199 insight.** Il 98% di ciò che HIRIS ha in memoria è rumore
che ha prodotto su sé stesso. Gli id arrivano a 4344 su 203 righe vive, quindi la **potatura
funziona** — il problema non è la crescita, è il rapporto. Quando finalmente ricorderà qualcosa
detto da una persona, quella riga sarà una su duecento.

### Cosa questo cambia nel piano

La **regola nel prompt** (decisione ④) non è un dettaglio dell'unificazione: **è il pezzo che conta
di più.** Senza, il resto della fetta costruisce una pagina più bella su una memoria che resta vuota.

E ne discende un requisito che il resto del documento non aveva: **ciò che l'utente ha detto e ciò
che HIRIS ha dedotto da solo non possono avere lo stesso peso.** La pagina della memoria deve
distinguerli, e il richiamo deve preferire i primi — altrimenti 199 medie settimanali sommergono le
tre cose che contano davvero.
