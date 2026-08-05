# Una memoria sola — Fetta 3a: HIRIS ricorda

> **Per chi esegue:** SOTTO-SKILL RICHIESTA — usa `superpowers:subagent-driven-development`.
> I passi usano caselle (`- [ ]`).

**Goal:** far sì che HIRIS ricordi ciò che gli dici, di sua iniziativa, e che ciò che gli hai detto
sia sempre presente quando ragiona — invece di rispondere «preso nota» e non salvare niente.

**Architettura:** una regola nel prompt di sistema che oggi non c'è; un solo strumento di
salvataggio al posto di due; la memoria slegata dal singolo chatbot; e ciò che una persona ha
dichiarato iniettato **sempre** nel contesto invece di essere richiamato per somiglianza.

**Tech stack:** Python 3.11+, pytest + pytest-asyncio (strict).

## Il fatto da cui si parte — misurato, non supposto

Database dell'add-on in produzione, 5 agosto 2026:

| tipo | stato | righe |
|---|---|---|
| `insight` (dedotti da HIRIS) | approved | **199** |
| `memory` (detti da una persona) | approved | **3** |
| `note` | approved | 1 |
| qualunque tipo | **`pending`** | **0** |

I tre ricordi hanno **lo stesso identico timestamp**: salvati in un unico momento il 24 luglio,
quasi certamente su richiesta esplicita. **Da allora, dodici giorni, nessuno.**

L'utente ha scritto in chat che d'inverno il soggiorno sta bene a 19.5. HIRIS ha risposto **«preso
nota»** e non ha chiamato alcuno strumento.

> **Lo strumento funziona. Il modello sa usarlo. Non è rotto: è muto.**

Dettaglio completo e decisioni: `2026-08-05-design-memoria-unica.md`.

## Vincoli globali

- **Nessuna nuova dipendenza.**
- **Nessuna regressione per i tre ricordi esistenti**: devono restare leggibili e richiamabili dopo
  ogni migrazione. Sono quattro mesi di conoscenza reale di una casa vera.
- **La distinzione detto/dedotto esiste già nei dati**: la colonna `source` vale `chat` e `manual`
  per ciò che una persona ha dichiarato, `history-digest` / `brain` / `mayan` per ciò che HIRIS ha
  prodotto. **Non inventare un campo nuovo** — usare quello.
- **Il gate di uscita non si tocca.** `automatic_allows_sensitive()` governa cosa può raggiungere un
  backend cloud sui percorsi automatici. Nessuna modifica di questa fetta può allentarlo.
- **Fail-safe assoluto**: nessun percorso della memoria può impedire alla chat o al ragionatore di
  rispondere.
- **Questa fetta è anche pulizia** (`CLAUDE.md`): ciò che viene sostituito se ne va, insieme ai
  commenti e alle costanti che lo giustificavano.
- **Test**: pytest, funzioni module-level, `@pytest.mark.asyncio` esplicito sugli async, `tmp_path`
  per i DB, `store.close()` esplicito, output pristino. **Le suite lunghe si eseguono in primo
  piano**: in questo progetto quelle in background sono morte in silenzio più volte.
- **Attenzione ai test di cablaggio via `inspect.getsource`** su `server._on_startup`: se tocchi il
  wiring vanno aggiornati nello stesso commit.

---

## Struttura dei file

| File | Cosa cambia |
|---|---|
| `hiris/app/claude_runner.py` | `BASE_SYSTEM_PROMPT` acquisisce la regola sul ricordare; i due strumenti diventano uno |
| `hiris/app/tools/memory_tools.py` · `knowledge_tools.py` | fusione: un salvataggio, un richiamo |
| `hiris/app/tools/dispatcher.py` | i rami dei tool rimossi |
| `hiris/app/brain/knowledge_store.py` | ambito senza `chatbot_id`, niente scadenza automatica, lettura dei dichiarati |
| `hiris/app/api/handlers_chat.py` | il blocco dei dichiarati, sempre presente |
| `hiris/app/brain/reasoner_memory.py` | idem per il ragionatore proattivo |
| `tests/test_memoria_ricorda.py` (nuovo) | la prova end-to-end |

---

## Task 1: il prompt dice a HIRIS di ricordare

**Files:**
- Modify: `hiris/app/claude_runner.py` (`BASE_SYSTEM_PROMPT`)
- Test: `tests/test_base_prompt_memoria.py` (nuovo)

**Perché è la prima e la più importante.** Oggi `BASE_SYSTEM_PROMPT` nomina la memoria **una volta
sola**, per dire che lo strumento esiste. Le sue quattro «regole fondamentali» riguardano tutte il
*non inventare* e il *non dichiarare azioni mai eseguite*. **Nessuna dice quando salvare.** È la
causa radice misurata: 3 ricordi in quattro mesi.

C'è anche un'ironia da chiudere: quel prompt vieta di «dichiarare azioni mai eseguite», e **«preso
nota» è esattamente quello** — solo che il modello non lo classifica come tale.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_base_prompt_memoria.py`. Il test non può misurare il comportamento di un modello,
ma può pinnare che **l'istruzione esista e arrivi al modello su entrambi i backend**:

1. `BASE_SYSTEM_PROMPT` contiene un'istruzione esplicita a salvare ciò che l'utente dichiara —
   asserisci sul **nome dello strumento** e su un verbo dell'istruzione, non su una frase intera che
   il primo ritocco stilistico romperebbe;
2. l'istruzione dice al modello di **non dire di aver preso nota se non ha salvato** (chiude il
   percorso «preso nota»);
3. il prompt assemblato da `claude_runner` la contiene;
4. il prompt assemblato da `backends/openai_compat_runner.py` la contiene — **i due runner
   assemblano il system prompt separatamente**, e una regola che arriva solo a uno dei due è una
   regola che metà degli utenti non ha.

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `python -m pytest tests/test_base_prompt_memoria.py -q`

- [ ] **Step 3: Scrivi la regola**

Aggiungi a `BASE_SYSTEM_PROMPT` una regola fondamentale nuova. Deve dire, con parole tue ma senza
ambiguità:

- quando l'utente **dichiara** qualcosa di duraturo su di sé, sulla casa o su come vuole le cose —
  una preferenza, un vincolo, un guasto, una regola operativa — **salvalo**, senza chiedere il
  permesso;
- **non serve** che l'utente dica «ricordati che»: un'affermazione basta;
- **non salvare** ciò che è effimero (lo stato di adesso, una richiesta una-tantum) né ciò che puoi
  rileggere da Home Assistant quando serve;
- **non dire di aver preso nota se non hai chiamato lo strumento.**

Tieni il registro del prompt esistente: conciso, imperativo, in italiano, senza esempi lunghi.

- [ ] **Step 4: Esegui e verifica che passi**

Run: `python -m pytest tests/test_base_prompt_memoria.py tests/test_claude_runner.py -q`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(memoria): il prompt dice a HIRIS quando ricordare"
```

---

## Task 2: un solo strumento di salvataggio, uno di richiamo

**Files:**
- Modify: `hiris/app/tools/knowledge_tools.py`, `hiris/app/tools/memory_tools.py`
- Modify: `hiris/app/tools/dispatcher.py`, `hiris/app/claude_runner.py` (catalogo)
- Test: i file esistenti dei due tool, più le loro controparti

**Contesto.** `save_memory` e `save_knowledge` chiamano **la stessa funzione sulla stessa tabella**.
Le differenze — approvazione, ambito, scadenza — sono decisioni di prodotto già prese nel design, non
proprietà dei due strumenti. Restano due sole cose vere: i **campi strutturati** (data, importo,
categoria) che alcuni elementi hanno e altri no, e il **tipo**.

**Il risultato dev'essere un solo strumento di salvataggio** che accetta i campi strutturati come
**opzionali**, e **un solo strumento di richiamo**.

**Decisione di prodotto già presa** (design §2): si salva **subito**, `status='approved'`. Niente
coda.

**Attenzione — prima di scegliere quale nome sopravvive**, cerca ogni superficie su cui i due nomi
compaiono: catalogo del runner, lista dei tool a sola valutazione, livelli del gateway MCP, catalogo
mostrato nell'interfaccia, tabelle nei documenti, e i **template di Chatbot preconfigurati** (ce ne
sono che istruiscono il modello a usare strumenti per nome). Metti l'elenco completo nel rapporto
prima di toccare qualcosa.

- [ ] **Step 1: Censisci** — `grep -rn "save_memory\|save_knowledge\|recall_memory\|recall_knowledge" hiris/ tests/ docs/`
- [ ] **Step 2: Scrivi i test che falliscono** — un solo strumento salva sia una preferenza nuda sia
      una scadenza con data e importo; il richiamo li ritrova entrambi; i test dei due vecchi
      strumenti vengono **riscritti** sul nuovo, non cancellati
- [ ] **Step 3: Esegui e verifica che falliscano**
- [ ] **Step 4: Fondi i due strumenti**, aggiorna il dispatcher e il catalogo, rimuovi ciò che resta
      senza chiamanti
- [ ] **Step 5: Esegui i file mirati in primo piano**
- [ ] **Step 6: Commit** — `feat(memoria): un solo strumento per ricordare, uno per richiamare`

---

## Task 3: la memoria è di HIRIS, non del chatbot

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py` (ambito, migrazione)
- Modify: i chiamanti che passano `chatbot_id`
- Test: `tests/test_knowledge_store_chatbot.py` (esistente, da riscrivere), più i nuovi

**Contesto, con un costo già osservato.** I tre ricordi reali del sistema in produzione — chi è
l'amministratore della casa, come rispondere a «chi c'è in casa», **e il fatto che il modulo meteo
esterno è guasto** — sono legati a `chatbot_id='hiris-default'`. Il giorno in cui nasce un secondo
chatbot, quello non saprà del guasto e **ricomincerà a proporre soluzioni basate su sensori che non
esistono**.

**La decisione** (design §2): ciò che dici lo sa **HIRIS**, non il chatbot. Ogni elemento continua a
registrare **chi** l'ha detto — la colonna `owner` — e l'interfaccia lo mostrerà (fetta 3b).

**L'eccezione deliberata, da rispettare:** oggi `owner` serve anche a **nascondere** le cose agli
altri abitanti. Non degradare quella protezione:

> Ciò che riguarda la casa è di tutti e porta il nome di chi l'ha detto.
> **Ciò che è marcato `sensitivity='sensitive'` resta visibile solo a chi l'ha detto.**

- [ ] **Step 1: Scrivi i test che falliscono** — un ricordo salvato parlando col chatbot A è
      richiamabile parlando col chatbot B; **un elemento sensibile di un owner NON è visibile a un
      altro owner** (questa è la prova che conta: senza, la fetta degrada una protezione)
- [ ] **Step 2: Esegui e verifica che falliscano**
- [ ] **Step 3: Implementa** — togli `chatbot_id` dalle clausole di ambito in
      `_clausole_di_scope`, mantieni il filtro di riservatezza. **Scrivi una migrazione** che azzera
      `chatbot_id` sugli elementi esistenti di tipo memoria, così i tre ricordi reali diventano
      subito di tutta la casa. Testa la migrazione su un db che li contiene.
- [ ] **Step 4: Esegui in primo piano**, compreso `tests/test_knowledge_store_chatbot.py`
- [ ] **Step 5: Commit** — `feat(memoria): cio' che dici lo sa HIRIS, non il chatbot`

---

## Task 4: ciò che una persona ha detto entra sempre

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py` (una lettura dei dichiarati)
- Modify: `hiris/app/api/handlers_chat.py`, `hiris/app/brain/reasoner_memory.py`
- Test: nuovi, più i file di contesto esistenti

**Contesto.** *«Il modulo esterno è guasto»* non è un'informazione da recuperare quando la domanda le
somiglia: è una cosa che HIRIS deve **sapere sempre**, o continuerà a sbagliare proprio quando
nessuno gli ha chiesto dei sensori. Con tre righe — o trenta — non serve cercare: ci stanno tutte.

**La regola:**

> **Ciò che una persona ha dichiarato entra sempre nel contesto. Ciò che HIRIS ha dedotto si
> richiama.**

Duecento medie settimanali non stanno in un prompt; trenta fatti dichiarati da chi ci abita, sì.

**Usa `source`, non un campo nuovo**: `chat` e `manual` sono i dichiarati, `history-digest` / `brain`
/ `mayan` i dedotti. Verifica l'elenco completo dei valori prima di scrivere il filtro.

**Il limite va deciso e dichiarato**: quanti dichiarati al massimo, e cosa succede quando sono di
più (i più recenti? i più recenti per owner?). Scegli, scrivilo nel codice come costante nominata, e
spiega la scelta nel rapporto — un troncamento silenzioso su questa strada significa che HIRIS
dimentica una cosa che gli hai detto **senza dirlo a nessuno**.

- [ ] **Step 1: Scrivi i test che falliscono** — i dichiarati compaiono nel contesto della chat
      **anche senza embedder e senza che la domanda li somigli**; gli insight **non** vi compaiono;
      il limite è rispettato; con zero dichiarati il prompt è **byte-identico** a prima
- [ ] **Step 2: Esegui e verifica che falliscano**
- [ ] **Step 3: Implementa** su entrambe le superfici, chat e ragionatore proattivo
- [ ] **Step 4: Esegui in primo piano**
- [ ] **Step 5: Commit** — `feat(memoria): cio' che hai detto tu HIRIS lo sa sempre`

---

## Task 6: la memoria non evapora — *(buco del piano, scoperto durante l'esecuzione)*

**Files:**
- Modify: `hiris/app/tools/memory_tools.py` (dove si calcola `valid_until`)
- Modify: `hiris/app/brain/knowledge_store.py` (`purge_expired_chatbot`)
- Modify: `hiris/config.yaml` / `run.sh` se la conservazione diventa un'opzione
- Test: i file che coprono scadenza e purga

**Perché questa task esiste.** Il documento di progetto decide (§2 ③) che **la memoria non evapora**:
ciò che HIRIS sa della tua casa non deve svanire perché è passato un trimestre. Il piano lo dichiara
nella tabella dei file e **poi non lo implementa in nessuna task**. La Task 3 ha lasciato
correttamente `valid_until` in pace, motivando che «lo possiede la Task 4» — che non lo possiede.

E la Task 3 ha prodotto, come effetto collaterale documentato, un difetto che questa task deve
chiudere:

> **Righe immortali e invisibili.** Staccare un ricordo dal suo chatbot azzera `chatbot_id` ma
> **lascia `valid_until`**. Quando quella data passa, il filtro di ambito la **nasconde su ogni
> percorso di lettura** — e `purge_expired_chatbot`, che cerca per chatbot, non la trova più. La riga
> resta nel database per sempre, invisibile e impurgabile. Una riga **già scaduta** al momento del
> distacco sopravvive direttamente illeggibile.

**La decisione:** niente scadenza automatica. La conservazione diventa un'impostazione, **spenta di
default**.

- [ ] **Step 1: Censisci**

```bash
grep -rn "valid_until\|retention_days\|purge_expired\|MEMORY_RETENTION" hiris/ tests/ --include=*.py --include=*.yaml --include=*.sh
```

Metti l'elenco nel rapporto. Distingui i **due** significati che `valid_until` ha oggi: la scadenza
di conservazione dei ricordi, e il campo `valid_until` usato come **validità di un fatto** (una cosa
vera fino a una certa data). **Non sono la stessa cosa** e questa task tocca solo la prima.

- [ ] **Step 2: Scrivi i test che falliscono**

1. un ricordo salvato **non riceve** una scadenza automatica;
2. un ricordo salvato oggi è ancora leggibile e richiamabile **a distanza di anni** — simula
   spostando l'orologio, non aspettando;
3. **le righe già scadute che esistono adesso tornano leggibili** — è la bonifica del difetto delle
   righe immortali. Costruisci un db con una riga `kind='memory'`, `chatbot_id=NULL`, `valid_until`
   nel passato, e verifica che dopo la migrazione sia di nuovo visibile;
4. se implementi la conservazione come impostazione: con l'impostazione **spenta** (default) nulla
   scade; con un valore impostato, la purga funziona **e non tocca ciò che non è un ricordo**.

- [ ] **Step 3: Esegui e verifica che falliscano**

- [ ] **Step 4: Implementa**

Togli il calcolo automatico della scadenza al salvataggio. Scrivi una **migrazione** che azzera
`valid_until` sui ricordi esistenti — è ciò che riporta in vita le righe già scadute e quelle
immortali. Decidi cosa fare di `purge_expired_chatbot` ora che nessuno gli produce più lavoro: se
resta senza chiamanti utili, **esce** (questa fetta è anche pulizia), ma solo se il censimento lo
conferma morto.

**Attenzione:** se la conservazione diventa un'opzione dell'add-on, deve comparire **prima nella UI
dell'add-on** e poi come variabile d'ambiente — regola del repo. Una env var che `run.sh` non esporta
è di fatto una costante.

- [ ] **Step 5: Esegui in primo piano** i file mirati

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(memoria): cio' che HIRIS sa non evapora"
```

---

## Task 5: la prova, e la pulizia

**Files:**
- Create: `tests/test_memoria_ricorda.py`
- Modify: ciò che resta senza chiamanti

- [ ] **Step 1: Scrivi la prova end-to-end**

Col `NullEmbedder` **vero**. Un test solo che attraversa la fetta:

1. si salva una preferenza con il nuovo strumento, **senza approvazione**;
2. è richiamabile **da un altro chatbot**;
3. compare **da sola** nel contesto della chat successiva, senza che nessuno la cerchi;
4. compare anche nel contesto del ragionatore proattivo;
5. un `insight` presente nello stesso archivio **non** compare nel blocco dei dichiarati.

Più il caso che riproduce il bug originale in forma verificabile: **un elemento salvato non finisce
in `pending`** — cioè non finisce in un limbo invisibile.

**Se un passo fallisce, riportalo: non aggirarlo modificando la prova.**

- [ ] **Step 2: Pulizia** — rimuovi ciò che le task 2-4 hanno lasciato senza chiamanti: strumenti
      sostituiti, costanti e commenti orfani, rami morti. **Prova con un grep che ogni cosa
      cancellata sia davvero senza chiamanti**, e metti l'output nel rapporto.
- [ ] **Step 3: La suite intera, in primo piano** — `python -m pytest -q` poi `npm test`
- [ ] **Step 4: Commit**

---

## Verifica live (obbligatoria)

È l'unica che conta, ed è quella che ha trovato questo bug.

1. Bumpa la versione e aggiorna l'add-on. **Nessun fornitore di embedding configurato.**
2. In chat, **senza dire «ricordati che»**, afferma qualcosa: *«d'inverno il soggiorno sta bene a
   19.5»*. HIRIS deve **salvarlo di sua iniziativa** e dirlo.
3. Verifica che sia nel database:
   `docker exec app_6354e165_hiris python3 -c "import sqlite3;print(sqlite3.connect('/data/knowledge.db').execute(\"SELECT id,kind,status,owner,chatbot_id,substr(content,1,80) FROM knowledge_items WHERE source IN ('chat','manual') ORDER BY id DESC LIMIT 5\").fetchall())"`
   → deve esserci, `status='approved'`, `chatbot_id` vuoto.
4. **Apri una conversazione nuova** e chiedi qualcosa sul riscaldamento del soggiorno: deve tenerne
   conto **senza che tu glielo ricordi**.
5. Verifica il caso che costa davvero: chiedi qualcosa sulla temperatura esterna. HIRIS **non deve**
   proporre soluzioni basate su sensori esterni — sa da luglio che il modulo è guasto, e quel
   ricordo ora deve valere ovunque.
6. Niente peggiorato: resoconto delle 08:00, Dashboard, proposte.

## Cosa questa fetta NON fa

- **Non costruisce la pagina** che mostra ciò che HIRIS sa, e **non rimuove la coda di
  approvazione** — è la fetta **3b**. Fino ad allora la sezione «Memoria» resterà vuota: su questo
  sistema lo è sempre stata (zero righe `pending` in quattro mesi).
- **Non porta i dichiarati dentro il ritratto della casa** — era la fetta 2c, e questa decisione la
  rende più semplice.
- **Non tocca il digest storico**, che continua a produrre insight: la fetta cambia il loro **peso**,
  non la loro esistenza.
