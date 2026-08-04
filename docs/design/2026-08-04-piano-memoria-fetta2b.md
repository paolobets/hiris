# La memoria — Fetta 2b: HIRIS si ricorda da solo

> **Per chi esegue:** SOTTO-SKILL RICHIESTA — usa `superpowers:subagent-driven-development`
> (consigliata) oppure `superpowers:executing-plans`. I passi usano caselle (`- [ ]`).

**Goal:** chiudere il divario fra *«HIRIS ricorda»* e *«HIRIS si ricorda»*. La fetta 2a ha fatto sì
che i ricordi vengano **scritti** su ogni installazione; questa fa sì che **affiorino da soli**,
senza che qualcuno debba chiederli.

**Architettura:** i due consumatori automatici della memoria — l'iniezione nel prompt di chat e la
memoria del ragionatore proattivo — oggi **saltano** quando manca il vettore di query. Vengono
collegati al percorso di recency che la 2a ha già costruito dentro lo store. E il blocco che finisce
nel prompt **cambia nome secondo cosa contiene davvero**.

**Tech stack:** Python 3.11+, pytest + pytest-asyncio (strict).

## Il problema, in una riga

> Dopo la 2a, su un'installazione di serie HIRIS **scrive** i ricordi e non li fa **mai** affiorare.
> Si raggiungono solo chiedendoli esplicitamente con uno strumento.

Due punti li saltano, entrambi con la stessa forma — calcolano il vettore e se è vuoto si arrendono:

- `hiris/app/api/handlers_chat.py` (~`:275-292`) — l'iniezione `## Memoria rilevante` nel prompt:
  `if query_vec:` … altrimenti il blocco non compare;
- `hiris/app/brain/reasoner_memory.py::relevant_memory` (~`:44-50`) — `if not emb: return []`, che
  lascia senza memoria **sia** il ragionatore per-evento **sia** la revisione olistica.

Saltare era la scelta prudente finché non esisteva un'alternativa. Ora esiste.

## Il vincolo che decide la qualità del risultato

> **Un blocco che contiene i più recenti non può chiamarsi «Memoria rilevante».**

Sarebbe la stessa bugia che la 2a ha appena tolto dagli strumenti: il modello legge «rilevante», e lo
riferisce all'utente come tale. Il blocco **cambia intestazione secondo cosa contiene davvero** —
*rilevante* quando i significati sono stati confrontati, *ultimi ricordi* quando no.

Questo è anche il motivo per cui `relevant_memory` non può più ritornare solo una lista: deve dire
**come** l'ha ottenuta.

## Vincoli globali

- **Nessuna nuova dipendenza.**
- **Fail-safe assoluto.** Nessun percorso della memoria può impedire alla chat o al ragionatore di
  funzionare: ogni innesto degrada a «nessun blocco», mai a un'eccezione. `relevant_memory` non
  solleva mai — quella proprietà va conservata.
- **Nessuna regressione per chi HA un embedder funzionante**: stesso ordinamento, stessa
  intestazione, stesso numero di frammenti di oggi. Va pinnato, non dedotto.
- **Gli stessi filtri di riservatezza sulle due strade.** La 2a li ha unificati in
  `KnowledgeStore._clausole_di_scope`: il percorso di recency vi passa già. Non aggiungere qui una
  seconda porta — usa `store.search(query_vec=...)` e lascia degradare lo store, non chiamare
  `recent()` direttamente dai consumatori.
- **Il gate di uscita resta.** `relevant_memory` riceve `allow_sensitive` da
  `automatic_allows_sensitive()` (vero solo se l'intera catena automatica è locale). La degradazione
  **non deve toccarlo**: un ricordo sensibile non può raggiungere un backend cloud solo perché
  l'embedder manca.
- **Questa fetta è anche pulizia** (`CLAUDE.md`, «Ogni fetta è anche pulizia»): commenti e costanti
  che giustificavano il salto se ne vanno con esso. Se trovi altro codice senza chiamanti nell'area,
  **segnalalo, non allargare la task.**
- **Test**: pytest puro, funzioni module-level, `@pytest.mark.asyncio` esplicito sugli async,
  `tmp_path` per i DB, `store.close()` esplicito, output pristino.
- **Attenzione ai test di cablaggio via `inspect.getsource`**: `tests/test_gather_context_memory.py`
  e `tests/test_coverage_wiring.py` leggono il sorgente di `server._on_startup`. Se tocchi
  `_gather_context` o `_holistic_reason`, quei test si rompono e vanno aggiornati **nello stesso
  commit**.

---

## Struttura dei file

| File | Cosa cambia |
|---|---|
| `hiris/app/brain/reasoner_memory.py` | degrada invece di arrendersi, e dice **come** ha ottenuto i frammenti |
| `hiris/app/server.py` | `_reason_memory_context` e `_gather_context` portano il «come» |
| `hiris/app/watcher/reasoner.py` | l'intestazione del blocco segue il contenuto |
| `hiris/app/brain/coverage_review.py` | stessa intestazione, percorso olistico |
| `hiris/app/api/handlers_chat.py` | l'iniezione degrada, e l'intestazione segue il contenuto |
| `tests/test_memoria_affiora_senza_embedder.py` (nuovo) | la prova end-to-end |

---

## Task 1: la memoria degrada, e dichiara come

**Files:**
- Modify: `hiris/app/brain/reasoner_memory.py`
- Test: `tests/test_reasoner_memory.py` (esistente, da estendere)

**Interfaces:**
- Produces: `relevant_memory(...)` non ritorna più `list[str]` ma anche l'informazione su **come** ha
  ottenuto i frammenti. Scegli tu la forma — una tupla `(frammenti, per_significato)` o un piccolo
  oggetto — ma **decidila guardando i tre call site**, e mettila nel rapporto: le task 2, 3 e 4 ci si
  appoggiano.

**Contesto.** Oggi la funzione fa `emb = await embedder.embed(query_text)` e se il risultato è falsy
ritorna `[]`. Deve invece chiamare `store.search(query_vec=emb or [], ...)` e lasciare degradare lo
store — che con un vettore vuoto dà i più recenti, con **gli stessi filtri**.

Non chiamare `recent()` direttamente: lo store è l'unico posto dove quella scelta vive, ed è ciò che
garantisce che i due percorsi non divergano mai.

- [ ] **Step 1: Scrivi i test che falliscono**

Estendi `tests/test_reasoner_memory.py` con quattro casi:
1. **nessun embedder** (`None`) → ritorna i frammenti più recenti, e dichiara che **non** sono per
   significato;
2. **embedder che ritorna `[]`** → identico al caso 1;
3. **embedder che solleva** → identico, senza propagare l'eccezione;
4. **embedder funzionante** → ordina per somiglianza **come oggi**, e dichiara che sono per
   significato.

Più due che pinnano ciò che non deve cambiare: il **tetto di caratteri** e il **limite di frammenti**
valgono anche sul percorso degradato; e `allow_sensitive=False` **nasconde i sensibili anche quando
si degrada**.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `python -m pytest tests/test_reasoner_memory.py -q`

- [ ] **Step 3: Implementa**

Rimuovi la resa; passa `emb or []` allo store; restituisci anche il «come». Aggiorna la docstring:
oggi spiega perché ci si arrende, e quella spiegazione non è più vera.

- [ ] **Step 4: Esegui e verifica che passino**

Run: `python -m pytest tests/test_reasoner_memory.py -q`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(memoria): il ragionatore non si arrende piu' senza vettore"
```

---

## Task 2: il prompt del ragionatore dice la verità

**Files:**
- Modify: `hiris/app/server.py` (`_reason_memory_context`, `_gather_context`)
- Modify: `hiris/app/watcher/reasoner.py` (`build_user_message`)
- Test: `tests/test_gather_context_memory.py`, `tests/test_sentinel_reasoner.py`

**Interfaces:**
- Consumes: la forma di ritorno decisa nella Task 1.

**Contesto.** La catena è: `relevant_memory` → `_reason_memory_context` → `_gather_context` mette la
chiave `"memory"` nel context → `build_user_message` la estrae e rende il blocco
`Cosa so di rilevante:`.

Il «come» deve percorrere la stessa catena, e `build_user_message` deve sceglierne l'intestazione:
**`Cosa so di rilevante:`** quando i significati sono stati confrontati, **`Ultimi ricordi:`** (o una
formulazione equivalente che tu giudichi più chiara per il modello) quando no.

**Attenzione a due trappole già pagate su questo file:**
- `build_user_message` sanifica il context **prima** dei `pop`, e `sanitize_ha_value` **tronca a 120
  caratteri**. I frammenti di memoria oggi sopravvivono perché sono corti; il flag booleano non ne
  risente. Non spostare nulla nel context che non sopporti quel troncamento.
- `_gather_context` ha **tre** `return`, due dei quali sono rami di fallimento. Il «come» deve
  arrivare in modo coerente su tutti e tre, e il ramo di fallimento non deve poter sollevare.

- [ ] **Step 1: Scrivi i test che falliscono**

- il messaggio del ragionatore porta `Ultimi ricordi:` quando la memoria è degradata, e
  `Cosa so di rilevante:` quando no;
- **byte-identico a oggi** quando la memoria è vuota o assente (nessun blocco, nessuna riga in più);
- il test di cablaggio su `inspect.getsource(server._on_startup)` riflette la nuova catena.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `python -m pytest tests/test_gather_context_memory.py tests/test_sentinel_reasoner.py -q`

- [ ] **Step 3: Implementa**

- [ ] **Step 4: Esegui e verifica che passino**

Run: `python -m pytest tests/test_gather_context_memory.py tests/test_sentinel_reasoner.py tests/test_portrait_wiring.py -q`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(memoria): l'intestazione del blocco segue cio' che il blocco contiene"
```

---

## Task 3: la revisione olistica, stessa verità

**Files:**
- Modify: `hiris/app/brain/coverage_review.py` (`build_review_context`, `build_review_message`)
- Modify: `hiris/app/server.py` (il call site dentro `_holistic_reason`)
- Test: `tests/test_coverage_review_memory.py`, `tests/test_coverage_wiring.py`

**Contesto.** Il percorso olistico ha la sua copia del blocco memoria, con la stessa intestazione
`Cosa so di rilevante:`. Deve seguire la stessa regola.

**Vincolo:** esiste un test di **byte-identità** che pretende che il messaggio sia invariato quando la
memoria è assente o vuota. La chiave del «come» va aggiunta al context **solo quando serve**, con la
stessa disciplina già usata per `memory` e per `portrait`.

- [ ] **Step 1: Scrivi i test che falliscono**
- [ ] **Step 2: Esegui e verifica che falliscano**
- [ ] **Step 3: Implementa**
- [ ] **Step 4: Esegui**

Run: `python -m pytest tests/test_coverage_review_memory.py tests/test_coverage_wiring.py -q`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(memoria): anche la revisione olistica dice come ha ottenuto i ricordi"
```

---

## Task 4: la chat si ricorda da sola

**Files:**
- Modify: `hiris/app/api/handlers_chat.py` (~`:275-292`)
- Test: il file di test che copre l'iniezione (cercalo: `grep -rln "Memoria rilevante" tests/`)

**Contesto.** È il punto che l'utente sente di più: oggi, senza embedder, HIRIS in chat non ricorda
**nulla** di ciò che gli hai detto in passato, a meno che il modello non decida di chiamare uno
strumento.

Stessa forma delle task precedenti: passa `query_vec or []` allo store e lascia degradare;
l'intestazione del blocco segue il contenuto (`## Memoria rilevante` ↔ `## Ultimi ricordi`).

**Attenzione:** questo punto chiama `store.search(...)` **senza** `allow_sensitive`, quindi eredita
`False` — i ricordi sensibili non entrano nel prompt di chat. È un comportamento pre-esistente e
**non va cambiato in questa task**: se ti sembra sbagliato, segnalalo nel rapporto.

- [ ] **Step 1: Scrivi i test che falliscono**

Almeno: senza embedder il blocco **compare** con l'intestazione degradata; con embedder compare con
quella di sempre; con memoria vuota **non compare affatto** e il prompt resta identico a oggi.

- [ ] **Step 2: Esegui e verifica che falliscano**
- [ ] **Step 3: Implementa**
- [ ] **Step 4: Esegui**

Run: `python -m pytest tests/test_handlers_chat.py -q` (o il file che copre l'iniezione)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(memoria): in chat HIRIS ricorda anche senza embedder"
```

---

## Task 5: la prova — un ricordo affiora da solo

**Files:**
- Create: `tests/test_memoria_affiora_senza_embedder.py`

**Contesto.** Le task 1-4 sono state verificate ognuna per conto suo. Questa verifica **la cosa per
cui la fetta esiste**, in un test solo: con il `NullEmbedder` **vero** — quello di produzione — un
ricordo salvato in chat **compare da solo** nel contesto del turno successivo, senza che nessuno lo
chieda, e con l'intestazione che dice la verità su cosa sia.

Aggiungi il gemello per il ragionatore proattivo: lo stesso ricordo raggiunge il suo prompt.

E il non-regresso: con un embedder funzionante entrambi si comportano come oggi.

- [ ] **Step 1: Scrivi la prova**

Usa `from hiris.app.backends.embeddings import NullEmbedder`, non un finto.

- [ ] **Step 2: Esegui**

Run: `python -m pytest tests/test_memoria_affiora_senza_embedder.py -q`

**Se fallisce, hai trovato un buco che le quattro task precedenti non hanno chiuso: riportalo, non
aggirarlo modificando la prova.**

- [ ] **Step 3: La suite intera, in primo piano**

Run: `python -m pytest -q` poi `npm test`. **Non lanciarle in background:** in questa fetta le
esecuzioni in background sono morte in silenzio più volte, lasciando risultati non confermati.

- [ ] **Step 4: Commit**

```bash
git commit -m "test(memoria): un ricordo salvato in chat affiora da solo, senza embedder"
```

---

## Verifica live (obbligatoria)

1. Bumpa la versione e aggiorna l'add-on. **Non configurare alcun provider di embedding.**
2. In chat: «ricordati che preferisco 21 gradi in salotto».
3. Approva il ricordo nella pagina Memoria.
4. **Apri una conversazione nuova** e chiedi qualcosa di attinente al riscaldamento. HIRIS deve
   tenerne conto **senza** che tu glielo ricordi.
5. Nei log dell'add-on, verifica che il prompt contenga il blocco con l'intestazione **degradata** —
   non «Memoria rilevante».
6. Configura un embedder (OpenAI o Ollama) e ripeti: l'intestazione deve tornare quella di sempre.
7. Controlla che niente sia peggiorato: resoconto delle 08:00, Dashboard, proposte.

## Cosa questa fetta NON fa

- **Non tocca la ricerca vettoriale sugli item.** Decisione dell'utente del 4 agosto, che ribalta la
  specifica: chi ha un embedder mantiene il richiamo per significato. Vedi la rettifica in
  `2026-08-04-cosa-sa-il-brain.md`.
- **Non porta scadenze e insight dentro il ritratto** — è la fetta 2c.
- **Non cambia la riservatezza del blocco di chat**: i ricordi sensibili restano fuori dal prompt di
  chat, come oggi.
