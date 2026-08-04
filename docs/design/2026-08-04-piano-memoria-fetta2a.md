# La memoria — Fetta 2a: smettere di rifiutare i ricordi

> **Per chi esegue:** SOTTO-SKILL RICHIESTA — usa `superpowers:subagent-driven-development`
> (consigliata) oppure `superpowers:executing-plans` per implementare task per task.
> I passi usano caselle (`- [ ]`) per il tracciamento.

**Goal:** togliere il pedaggio vettoriale dalla scrittura, così che il second brain si riempia
appena installi — e il resoconto delle 08:00, che oggi è **vuoto per sempre** su ogni installazione
di serie, funzioni.

**Architettura:** una regola sola, applicata **dentro lo store** perché nessun chiamante debba
crescere un ramo — *la ricerca confronta i significati quando può; quando non può, dà i più
recenti*. Sopra quella regola, i cinque punti che oggi rifiutano di scrivere smettono di farlo.

**Tech stack:** Python 3.11+, sqlite3 via `hiris/app/storage.py`, pytest + pytest-asyncio (strict).

## Il problema, in tre fatti verificati

1. **Cinque percorsi di scrittura rifiutano senza embedding** (`save_knowledge`, `save_memory`,
   l'aggiunta manuale, l'approvazione, la traccia del Brain) — e di fabbrica l'embedder **non è
   configurato**: `build_embedding_provider("")` costruisce un `NullEmbedder` che ritorna `[]`.
2. **Altri tre scrivono righe con embedding nullo e non se ne curano** (digest storico, migrazione,
   importazione documentale), e la ricerca le esclude per costruzione
   (`embedding IS NOT NULL`). Metà del sistema paga un pedaggio che l'altra metà ignora.
3. **Il resoconto delle 08:00 legge le scadenze con SQL puro**
   (`WHERE kind='obligation' AND due_date <= ? ORDER BY due_date`) e **scarta l'embedding dalla riga
   letta** — ma per scrivere quella scadenza l'embedding è obbligatorio. Si paga un pedaggio
   vettoriale in scrittura su dati che si leggono per data, e il risultato è che non si scrivono mai.

## Vincoli globali

- **Nessuna nuova dipendenza.**
- **Nessun percorso deve regredire per chi HA un embedder configurato.** Con un vettore valido tutto
  si comporta esattamente come oggi. Questo è verificabile e va verificato.
- **La degradazione è una regola sola, non una configurazione**: vive dentro
  `KnowledgeStore.search`, non nei chiamanti. Nessun chiamante acquisisce un `if`.
- **Non si tocca `search_chunks`.** I documenti sono l'unico corpus vero e restano vettoriali.
- **Non si tocca il filtro `kinds` né `allow_sensitive`**: la degradazione applica gli stessi
  identici filtri della ricerca vettoriale. Un percorso che perde un filtro di riservatezza sarebbe
  una falla, non una degradazione.
- **Store SQLite**: `threading.Lock` attorno a ogni query, come tutto il resto del file.
- **Test**: pytest puro, funzioni module-level, `@pytest.mark.asyncio` esplicito sugli async,
  `tmp_path` per i DB (mai in-memory), `store.close()` a fine test, nomi in inglese, output pristino.
- **Questa fetta è anche pulizia.** Il Refactor 2.0 non aggiunge soltanto: il codice morto si
  cancella, le funzioni doppie si unificano, le costanti e i commenti orfani se ne vanno insieme a
  ciò che li giustificava. Vedi `CLAUDE.md`, sezione «Ogni fetta è anche pulizia». Se mentre lavori
  trovi altro codice senza chiamanti nell'area che stai toccando, **segnalalo nel rapporto** — non
  allargare la task di tua iniziativa.
- **~190 test sono esposti** su 19 file. I più a rischio: `tests/test_knowledge_store.py`,
  `tests/test_knowledge_tools.py`, `tests/test_memory_tools_guasti.py`,
  `tests/test_handlers_knowledge.py`, `tests/test_brain_trace.py`. Diversi di essi **asseriscono
  oggi che la scrittura viene rifiutata**: quelle asserzioni descrivono il difetto che stiamo
  togliendo e vanno riscritte per pinnare il comportamento nuovo, **non cancellate**.

---

## Struttura dei file

| File | Cosa cambia |
|---|---|
| `hiris/app/brain/knowledge_store.py` | nuovo `recent()`; `search()` delega quando non c'è vettore |
| `hiris/app/tools/knowledge_tools.py` | `save_knowledge` non rifiuta più |
| `hiris/app/tools/memory_tools.py` | `save_memory` non rifiuta più |
| `hiris/app/api/handlers_knowledge.py` | aggiunta manuale e approvazione non rifiutano più |
| `hiris/app/brain/brain_trace.py` | la traccia del Brain non rifiuta più |
| `tests/test_knowledge_store_recent.py` (nuovo) | la regola della degradazione |
| test esistenti sopra elencati | asserzioni di rifiuto → asserzioni di scrittura |

---

## Task 1: la regola — significati quando si può, recenti quando non si può

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py`
- Test: `tests/test_knowledge_store_recent.py` (nuovo)

**Interfaces:**
- Produces:
  ```python
  def recent(self, *, k: int = 5, owner: str | None = None,
             chatbot_id: str | None = None, allow_sensitive: bool = False,
             kinds: list[str] | str | None = None) -> list[dict]
  ```
  Stessa forma di ritorno di `search` (dict per riga, senza il blob `embedding`), ordinati per
  `created_at DESC, id DESC`. E `search` delega a `recent` quando `query_vec` è vuoto.

**Contesto per chi implementa:** leggi `search` (intorno a `knowledge_store.py:236-311`) prima di
scrivere. Costruisce `clauses`/`params`, esegue la SELECT, poi calcola il coseno in Python. Le
clausole di filtro — owner, chatbot_id, sensitivity, kinds, status — sono la parte che devi
**condividere**, non duplicare: estraile in un helper privato usato da entrambi. Duplicarle sarebbe
il difetto peggiore possibile qui, perché una delle due copie governa la riservatezza.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_knowledge_store_recent.py`:

```python
"""La regola della degradazione: significati quando si puo', recenti quando no.

Vive DENTRO lo store apposta: nessun chiamante deve crescere un ramo, e i
filtri di riservatezza devono essere gli stessi identici su entrambi i
percorsi -- un percorso che ne perde uno non e' una degradazione, e' una falla.
"""
import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore


def _store(tmp_path):
    return KnowledgeStore(str(tmp_path / "k.db"))


def _add(s, content, **kw):
    return s.add_item(kind=kw.pop("kind", "note"), content=content, **kw)


def test_recent_returns_newest_first(tmp_path):
    s = _store(tmp_path)
    _add(s, "primo")
    _add(s, "secondo")
    _add(s, "terzo")
    got = [r["content"] for r in s.recent(k=3)]
    assert got == ["terzo", "secondo", "primo"]
    s.close()


def test_recent_honours_k(tmp_path):
    s = _store(tmp_path)
    for i in range(5):
        _add(s, f"n{i}")
    assert len(s.recent(k=2)) == 2
    s.close()


def test_recent_hides_sensitive_unless_allowed(tmp_path):
    s = _store(tmp_path)
    _add(s, "normale", sensitivity="normal")
    _add(s, "riservato", sensitivity="sensitive")
    assert [r["content"] for r in s.recent(k=5)] == ["normale"]
    assert set(r["content"] for r in s.recent(k=5, allow_sensitive=True)) == {
        "normale", "riservato"
    }
    s.close()


def test_recent_filters_kinds_and_treats_empty_list_as_deny_all(tmp_path):
    s = _store(tmp_path)
    _add(s, "un fatto", kind="fact")
    _add(s, "una nota", kind="note")
    assert [r["content"] for r in s.recent(k=5, kinds=["fact"])] == ["un fatto"]
    assert s.recent(k=5, kinds=[]) == []
    assert len(s.recent(k=5, kinds="all")) == 2
    s.close()


def test_recent_scopes_by_owner_and_chatbot(tmp_path):
    s = _store(tmp_path)
    _add(s, "di casa", owner="home")
    _add(s, "di paolo", owner="paolo")
    _add(s, "del bot", owner="home", chatbot_id="bot-1")
    got = set(r["content"] for r in s.recent(k=9, owner="paolo"))
    assert "di paolo" in got and "di casa" in got
    assert "del bot" not in got
    s.close()


def test_recent_only_approved(tmp_path):
    s = _store(tmp_path)
    _add(s, "approvato", status="approved")
    _add(s, "in attesa", status="pending")
    assert [r["content"] for r in s.recent(k=5)] == ["approvato"]
    s.close()


def test_recent_includes_rows_without_embedding(tmp_path):
    """E' il punto di tutto: la ricerca vettoriale le esclude per costruzione."""
    s = _store(tmp_path)
    _add(s, "senza vettore")
    assert [r["content"] for r in s.recent(k=5)] == ["senza vettore"]
    s.close()


def test_recent_never_returns_the_embedding_blob(tmp_path):
    s = _store(tmp_path)
    _add(s, "x", embedding=[1.0, 0.0])
    assert "embedding" not in s.recent(k=1)[0]
    s.close()


def test_search_without_a_query_vector_degrades_to_recent(tmp_path):
    """Il NullEmbedder ritorna [] -- questo e' il caso di fabbrica."""
    s = _store(tmp_path)
    _add(s, "vecchio")
    _add(s, "nuovo")
    assert [r["content"] for r in s.search(query_vec=[], k=2)] == ["nuovo", "vecchio"]
    s.close()


def test_search_with_a_query_vector_still_ranks_by_meaning(tmp_path):
    """Chi HA un embedder non deve perdere niente."""
    s = _store(tmp_path)
    _add(s, "lontano", embedding=[0.0, 1.0])
    _add(s, "vicino", embedding=[1.0, 0.0])
    got = [r["content"] for r in s.search(query_vec=[1.0, 0.0], k=2)]
    assert got[0] == "vicino"
    s.close()


def test_degraded_search_applies_the_same_filters(tmp_path):
    """Una degradazione che perde un filtro di riservatezza e' una falla."""
    s = _store(tmp_path)
    _add(s, "normale", sensitivity="normal")
    _add(s, "riservato", sensitivity="sensitive")
    assert [r["content"] for r in s.search(query_vec=[], k=5)] == ["normale"]
    s.close()
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_knowledge_store_recent.py -q`
Expected: FAIL — `AttributeError: 'KnowledgeStore' object has no attribute 'recent'`

- [ ] **Step 3: Scrivi l'implementazione**

In `hiris/app/brain/knowledge_store.py`:

**3a.** Estrai le clausole di filtro condivise in un helper privato. Prendi le clausole **esattamente
come sono oggi** dentro `search` — owner/chatbot_id, `allow_sensitive`, `kinds` (compresa la
sentinella deny-all per la lista vuota), `status='approved'` — e spostale qui **senza cambiarne
la semantica**. L'unica clausola che NON entra nell'helper è `embedding IS NOT NULL`, perché è
l'unica specifica del percorso vettoriale:

```python
    def _clausole_di_scope(
        self, *, owner: str | None, chatbot_id: str | None,
        allow_sensitive: bool, kinds: list[str] | str | None,
    ) -> tuple[list[str], dict]:
        """Filtri condivisi da search() e recent().

        Stanno qui, e non duplicati nei due metodi, perche' governano la
        riservatezza: due copie che divergono sono una falla, non un difetto
        di stile.
        """
        clauses: list[str] = ["status='approved'"]
        params: dict = {}
        # ... sposta qui, invariate, le clausole che oggi sono dentro search():
        #     owner/chatbot_id, sensitivity, kinds
        return clauses, params
```

**3b.** Riscrivi `search` in modo che usi l'helper, aggiunga `embedding IS NOT NULL` per conto
proprio, e **deleghi** quando non ha con cosa confrontare:

```python
        if not query_vec:
            # Regola unica: la ricerca confronta i significati quando puo';
            # quando non puo' -- nessun embedder configurato, quindi nessun
            # vettore di query -- da' i piu' recenti. Il default di fabbrica
            # e' il NullEmbedder, che ritorna [], quindi questo e' il percorso
            # NORMALE, non un caso limite.
            return self.recent(
                k=k, owner=owner, chatbot_id=chatbot_id,
                allow_sensitive=allow_sensitive, kinds=kinds,
            )
```

**3c.** Scrivi `recent`, che usa l'helper e ordina per `created_at DESC, id DESC` (l'`id` rompe la
parità quando due righe hanno lo stesso timestamp, cosa normale visto che `created_at` ha
risoluzione al secondo). Rimuovi il blob `embedding` da ogni riga restituita, come fa già `get_item`.

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_knowledge_store_recent.py tests/test_knowledge_store.py tests/test_knowledge_store_chatbot.py -q`
Expected: PASS — 11 nuovi più i ~29 esistenti, che **non devono cambiare**.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/knowledge_store.py tests/test_knowledge_store_recent.py
git commit -m "feat(memoria): significati quando si puo', recenti quando non si puo'"
```

---

## Task 2: gli strumenti smettono di rifiutare

**Files:**
- Modify: `hiris/app/tools/knowledge_tools.py` (il rifiuto è intorno a `:103-105`)
- Modify: `hiris/app/tools/memory_tools.py` (il rifiuto è intorno a `:131-133`)
- Test: `tests/test_knowledge_tools.py`, `tests/test_memory_tools_guasti.py` (esistenti, da riscrivere)

**Interfaces:**
- Consumes: `KnowledgeStore.add_item` accetta già `embedding=None` — la colonna è nullable.
- Produces: nessuna firma cambia. Cambia il comportamento: si scrive comunque.

**Contesto per chi implementa:** entrambi i file hanno la stessa forma —
`emb = await embedder.embed(...)` dentro un try, poi `if not emb: return {"error": ...}`. Va tolto
**solo il rifiuto**, non il tentativo: se un embedder c'è e funziona, il vettore si calcola e si
salva esattamente come oggi. Le costanti di errore che restano orfane vanno rimosse, non lasciate.

- [ ] **Step 1: Riscrivi i test esistenti**

In `tests/test_memory_tools_guasti.py` e `tests/test_knowledge_tools.py` ci sono test che oggi
asseriscono il **rifiuto**. Cercali (asseriscono su `error` nel risultato). **Non cancellarli**:
riscrivili perché pinnino il comportamento nuovo. Ogni test riscritto deve verificare tre cose:

1. senza embedder utile, il salvataggio **riesce** e non ritorna `error`;
2. la riga è davvero nel database, recuperabile con `store.recent(...)`;
3. con un embedder che funziona, il vettore **viene comunque salvato** (nessuna regressione).

Aggiungi anche il caso che oggi non esiste: **l'embedder solleva** — il salvataggio deve riuscire
lo stesso, senza vettore, senza propagare l'eccezione.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `python -m pytest tests/test_memory_tools_guasti.py tests/test_knowledge_tools.py -q`
Expected: FAIL — i test riscritti si aspettano un salvataggio che il codice ancora rifiuta.

- [ ] **Step 3: Togli i due rifiuti**

In `hiris/app/tools/knowledge_tools.py` e `hiris/app/tools/memory_tools.py`: elimina il blocco
`if not emb: ... return {"error": ...}` e passa `embedding=emb or None` alla scrittura. Lascia il
`try/except` attorno alla chiamata `embed()` — un embedder che solleva non deve impedire di
ricordare. Rimuovi le costanti di messaggio d'errore rimaste senza chiamanti.

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_memory_tools_guasti.py tests/test_knowledge_tools.py tests/test_memory_alias_unified.py tests/test_kinds_egress.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/tools/knowledge_tools.py hiris/app/tools/memory_tools.py \
        tests/test_memory_tools_guasti.py tests/test_knowledge_tools.py
git commit -m "feat(memoria): salvare un ricordo non richiede piu' un vettore"
```

---

## Task 3: l'interfaccia smette di rifiutare

**Files:**
- Modify: `hiris/app/api/handlers_knowledge.py` (rifiuti intorno a `:81-85` e `:138-141`)
- Test: `tests/test_handlers_knowledge.py` (esistente, da riscrivere)

**Interfaces:**
- Consumes: `KnowledgeStore.approve(item_id, embedding=...)` — verifica leggendo la firma se
  `embedding` è opzionale; se non lo è, rendilo tale.
- Produces: nessuna rotta nuova. `POST /api/knowledge` e
  `POST /api/knowledge/{id}/approve` smettono di rispondere `503`.

**Contesto per chi implementa:** questo è il punto che rende il difetto *visibile all'utente*. Oggi
la pagina Memoria mostra un elemento in attesa e il pulsante «Approva» risponde `503`: l'utente vede
la cosa che HIRIS ha imparato e **non può tenerla**. Dopo questa task l'approvazione funziona
sempre; se un vettore si può calcolare lo si salva, altrimenti la riga viene approvata senza.

- [ ] **Step 1: Riscrivi i test esistenti**

In `tests/test_handlers_knowledge.py` ci sono test che asseriscono `status == 503`. Riscrivili perché
asseriscano `200` e che la riga risulti approvata. Aggiungi il caso: **approvare una riga che non ha
un vettore e non può averne uno riesce**, ed è il caso che oggi lascia l'utente bloccato.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `python -m pytest tests/test_handlers_knowledge.py -q`
Expected: FAIL — i test si aspettano 200 dove il codice risponde ancora 503.

- [ ] **Step 3: Togli i due rifiuti**

Elimina i due blocchi `if not emb: return web.json_response({...}, status=503)` in
`handle_approve` e `handle_manual_add`; passa il vettore quando c'è, `None` quando non c'è. Rimuovi
le costanti di messaggio rimaste orfane.

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_handlers_knowledge.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/api/handlers_knowledge.py tests/test_handlers_knowledge.py
git commit -m "feat(memoria): approvare un ricordo riesce sempre"
```

---

## Task 4: la traccia del Brain smette di rifiutare

**Files:**
- Modify: `hiris/app/brain/brain_trace.py` (i due rifiuti sono intorno a `:32` e `:42`)
- Test: `tests/test_brain_trace.py` (esistente, da riscrivere)

**Contesto per chi implementa:** `record_brain_action` è ciò che rende **annullabile** una modifica
che il Brain si è fatto da solo. Oggi, senza embedder, la traccia non viene scritta — quindi la
modifica resta applicata e **non è più annullabile dall'interfaccia**. Non è una perdita di comodità:
è la rete di sicurezza dell'auto-configurazione che scompare in silenzio.

Nota che qui i rifiuti sono **due**: uno su `embedder is None` e uno su `not emb`. Vanno tolti
entrambi. Il primo è l'unico caso in tutto il codice in cui `embedder is None` è controllato per
rifiutare una scrittura.

- [ ] **Step 1: Riscrivi i test esistenti**

In `tests/test_brain_trace.py`, i test che asseriscono `record_brain_action(...) is None` senza
embedder vanno riscritti: la traccia deve essere scritta, e `remove_brain_action` deve poterla
ritrovare e togliere. Copri entrambi: `embedder=None` e un embedder che ritorna `[]`.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `python -m pytest tests/test_brain_trace.py -q`
Expected: FAIL

- [ ] **Step 3: Togli i due rifiuti**

Scrivi la traccia con `embedding=emb or None`, mantenendo il `try/except` attorno a `embed()` e la
logica di delete-then-add che supera la traccia precedente.

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_brain_trace.py tests/test_cognitive_loop.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/brain_trace.py tests/test_brain_trace.py
git commit -m "feat(memoria): l'annullamento resta possibile anche senza vettore"
```

---

## Task 5: la prova che serviva — il resoconto funziona a scatola chiusa

**Files:**
- Test: `tests/test_memoria_senza_embedder.py` (nuovo)

**Interfaces:**
- Consumes: tutto quanto sopra, più `brain/briefing.py::build_briefing_bundle` e
  `KnowledgeStore.upcoming_obligations`.

**Contesto per chi implementa:** le task 1-4 sono state verificate ognuna per conto suo. Questa è
l'unica che verifica **la cosa per cui esiste la fetta**, end-to-end e in un test solo: su
un'installazione senza alcun embedder configurato, una scadenza salvata dalla chat **arriva** al
resoconto delle 08:00. Oggi quel percorso è rotto in due punti diversi — la scrittura viene
rifiutata, e anche se non lo fosse l'approvazione risponderebbe 503 — e nessun test esistente
attraversa entrambi.

- [ ] **Step 1: Scrivi il test end-to-end**

Crea `tests/test_memoria_senza_embedder.py`. Usa il `NullEmbedder` **vero**
(`from hiris.app.backends.embeddings import NullEmbedder`), non un finto: è quello che gira in
produzione di fabbrica, ed è tutto il punto del test.

Il percorso da coprire, in un unico test:

1. `handle_save_knowledge` con `kind="obligation"`, una `due_date` entro pochi giorni, e un
   `NullEmbedder` → **riesce**, nessun `error`;
2. la riga risulta `pending` (è la coda di approvazione, non cambia);
3. approvarla via `handle_approve` → **200**, e la riga diventa `approved`;
4. `KnowledgeStore.upcoming_obligations(before=...)` la **trova**;
5. `build_briefing_bundle(...)` la include fra le scadenze.

Aggiungi un secondo test che pinna il non-regresso: **con un embedder che funziona lo stesso
percorso funziona ancora**, e la riga ha un vettore.

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `python -m pytest tests/test_memoria_senza_embedder.py -q`
Expected: PASS se le task 1-4 sono complete. **Se fallisce, hai trovato un buco che le quattro task
precedenti non hanno chiuso — riportalo, non aggirarlo modificando il test.**

- [ ] **Step 3: Esegui la suite intera**

Run: `python -m pytest -q` poi `npm test`
Expected: PASS su entrambe. Nessun test preesistente deve fallire. Attenzione ai file elencati nei
vincoli globali: se qualcuno di essi asserisce ancora un rifiuto che non avviene più, riscrivilo —
descriveva il difetto, non il contratto.

- [ ] **Step 4: Commit**

```bash
git add tests/test_memoria_senza_embedder.py
git commit -m "test(memoria): una scadenza salvata in chat arriva al resoconto, senza embedder"
```

---

## Task 6: i richiami smettono di rifiutare — *(buco del piano, scoperto in Task 2)*

**Files:**
- Modify: `hiris/app/tools/memory_tools.py` (il rifiuto è a `:183-185`)
- Modify: `hiris/app/tools/knowledge_tools.py` (il rifiuto è a `:135`)
- Test: `tests/test_memory_tools_guasti.py`, `tests/test_knowledge_tools.py`

**Perché questa task esiste.** La Task 1 ha messo la degradazione **dentro lo store** proprio perché
nessun chiamante dovesse crescere un ramo. Il piano dava per scontato che bastasse. Non bastava:
**due chiamanti su quattro si fermano prima di entrare nello store.** `handle_recall_memory` e
`handle_recall_knowledge` calcolano il vettore di query e, se è vuoto, ritornano un errore senza mai
chiamare `search`. Risultato: dopo le Task 2-4 HIRIS **scrive** ma non **richiama** — cioè
esattamente lo stato «salvato ma non ritrovabile» che questo piano dichiara di voler evitare.

**Il messaggio di errore di oggi era corretto, e ora non lo è più.** Dice: *«non posso dire che non
ci sia nulla, solo che non ho potuto controllare»*. Era vero quando l'unico modo di controllare era
il confronto dei significati. Ora un modo c'è.

**Ma il risultato degradato deve dichiararsi degradato.** Se il richiamo restituisce i più recenti e
li presenta come i più pertinenti, il modello dirà all'utente una cosa falsa. Il ritorno deve portare
un segnale esplicito che il confronto dei significati non è avvenuto, e il modello deve poterlo
riferire.

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi a `tests/test_memory_tools_guasti.py` e `tests/test_knowledge_tools.py`, uno per file:

1. **senza embedder utile, il richiamo riesce** e restituisce le righe più recenti invece di un
   errore — e il risultato porta il segnale di degradazione;
2. **con un embedder che funziona**, il richiamo si comporta esattamente come oggi: ordina per
   somiglianza e **non** porta il segnale di degradazione;
3. **l'embedder solleva** → il richiamo riesce lo stesso, degradato, senza propagare l'eccezione;
4. un test che pinna che il richiamo degradato **applica gli stessi filtri** — una riga sensibile non
   deve comparire a chi non può vederla. È la stessa invariante della Task 1, verificata qui dal lato
   del chiamante.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `python -m pytest tests/test_memory_tools_guasti.py tests/test_knowledge_tools.py -q`
Expected: FAIL — i richiami ritornano ancora `error`.

- [ ] **Step 3: Togli i due rifiuti e dichiara la degradazione**

In entrambi i file: elimina il blocco `if not query_vec: return {"error": ...}` e passa
`query_vec or []` a `store.search(...)`, che degrada da sé. Mantieni il `try/except` attorno a
`embed()`.

Aggiungi al dizionario di ritorno una chiave che dice che il confronto dei significati non è
avvenuto — scegli un nome coerente con le altre chiavi già presenti in quel ritorno, e **documenta
nella descrizione del tool** (l'`input_schema`/description che il modello legge) cosa significa, così
il modello sa di dover dire «questi sono i più recenti, non ho potuto confrontare i significati».

Rimuovi le costanti di errore rimaste senza chiamanti, e il commento che le spiegava.

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_memory_tools_guasti.py tests/test_knowledge_tools.py tests/test_memory_alias_unified.py tests/test_kinds_egress.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/tools/memory_tools.py hiris/app/tools/knowledge_tools.py \
        tests/test_memory_tools_guasti.py tests/test_knowledge_tools.py
git commit -m "fix(memoria): richiamare non richiede piu' un vettore, e il degradato lo dichiara"
```

---

## Task 7: pulizia — togliere ciò che non ha chiamanti

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py`
- Modify: `tests/test_knowledge_store.py`

**Perché.** Il Refactor 2.0 è anche una fase di pulizia: HIRIS è cresciuto per accumulo e questa è
l'occasione per invertire il verso nell'area che stiamo toccando. Il censimento dello store ha
trovato due metodi **scritti, testati e mai chiamati in produzione**.

**Cosa si cancella, in chiaro:**

| Cosa | Dove | Prova |
|---|---|---|
| `KnowledgeStore.expenses_by_category` | `knowledge_store.py` (~:336) | unico riferimento: `tests/test_knowledge_store.py` |
| `KnowledgeStore.neighbors` | `knowledge_store.py` (~:362) | unico riferimento: `tests/test_knowledge_store.py` |

Git li conserva: se un giorno servirà una vista delle spese o dei collegamenti, si riscrive contro il
bisogno reale invece di ereditare una firma indovinata mesi prima.

**Attenzione:** `add_link` **resta** — ha un chiamante vivo (il tool `link_knowledge`). Si cancella
solo `neighbors`, cioè la lettura che nessuno fa.

**E i residui raccolti dalle review delle altre task**, tutti nella stessa area:

| Cosa | Dove | Perché |
|---|---|---|
| ramo morto `if item_id is not None` | `brain/cognitive_loop.py` (~:273) | `record_brain_action` non può più ritornare `None`: la condizione è sempre vera |
| commento orfano che rimanda a un blocco cancellato | `tools/knowledge_tools.py` (~:60-61) | il «gemello sopra» a cui rimanda non esiste più |
| commento al plurale su una costante sola | `tools/memory_tools.py` (~:16-18) | dice «i messaggi», ne è rimasto uno |
| **la descrizione di `recall_knowledge` non dice che in modalità degradata i documenti non vengono consultati** | `tools/knowledge_tools.py`, campo `description` | `search_chunks` è solo vettoriale e viene **saltato**: il modello deve saperlo, o dirà «questi sono i più recenti» tacendo che l'archivio non è stato aperto. **Una frase.** Questa fetta esiste per smettere di dire cose non vere: vale anche qui |

- [ ] **Step 1: Verifica tu stesso che siano morti**

Prima di cancellare, provalo — non fidarti di questo piano:

```bash
grep -rn "expenses_by_category\|neighbors" hiris/ tests/ --include=*.py
```

Ogni occorrenza deve essere nella definizione o nei test. **Se trovi un chiamante in produzione,
fermati e riportalo**: il piano è sbagliato e la cancellazione non si fa.

- [ ] **Step 2: Cancella i due metodi e i loro test**

Togli le due definizioni e le funzioni di test che le coprivano. Un test che copre codice cancellato
non è copertura persa: è copertura che non ha più un oggetto.

- [ ] **Step 3: Esegui la suite**

Run: `python -m pytest -q`
Expected: PASS. Il conteggio scende di quanti test hai tolto — è atteso, dillo nel rapporto.

- [ ] **Step 4: Commit**

```bash
git add hiris/app/brain/knowledge_store.py tests/test_knowledge_store.py
git commit -m "refactor(memoria): via due letture che nessuno chiamava"
```

---

## Task 8: via i collegamenti che nessuno legge — *(scoperta della Task 7)*

**Perché.** Cancellare `neighbors` nella Task 7 ha reso visibile una cosa che prima era nascosta:
**`neighbors` era l'unico lettore della tabella `knowledge_links`.** Tolto quello, resta in piedi una
catena intera che non porta da nessuna parte:

> il tool **`link_knowledge`** esposto al modello → `handle_link_knowledge` → `add_link` → una
> tabella che **nessuno interroga**.

Il modello può spendere token per collegare fra loro i ricordi, e nulla consumerà mai quei
collegamenti. È una funzione morta con una superficie viva — la specie peggiore, perché sembra
funzionante. **Decisione dell'utente: via tutto.**

**Sui dati:** la tabella viene cancellata, e con lei gli eventuali collegamenti già creati. Non è una
perdita: non erano letti da nulla. Git conserva il codice; se un giorno servirà una vista dei
collegamenti si riscriverà contro il bisogno vero, non contro una firma indovinata mesi prima.

**Files:**
- Modify: `hiris/app/tools/knowledge_tools.py` (definizione del tool + `handle_link_knowledge`)
- Modify: `hiris/app/tools/dispatcher.py` (import + il ramo `link_knowledge`)
- Modify: `hiris/app/brain/knowledge_store.py` (`add_link`, lo schema, la pulizia in `delete_item`,
  la versione di schema + migrazione)
- Modify: i test che vi fanno riferimento

- [ ] **Step 1: Trova ogni occorrenza — non fidarti di questo elenco**

```bash
grep -rn "link_knowledge\|add_link\|knowledge_links\|idx_kl_" hiris/ tests/ docs/ --include=*.py --include=*.js --include=*.md
```

Un tool esposto al modello può comparire in più posti di quanti ne nomini un piano: il catalogo dei
tool del runner, la lista dei tool a sola valutazione, i livelli del gateway MCP, il catalogo mostrato
nell'interfaccia, le tabelle nella documentazione. **Cercali tutti prima di toccare qualsiasi cosa**,
e metti l'elenco completo nel rapporto.

- [ ] **Step 2: La migrazione di schema**

Questa è la parte da fare bene. Nel file dello store:

- togli `CREATE TABLE knowledge_links` e i suoi due indici da `_SCHEMA`;
- alza la **versione di schema** al numero successivo;
- aggiungi la migrazione corrispondente al dizionario `migrations`, che esegue
  `DROP TABLE IF EXISTS knowledge_links`.

Verifica leggendo `hiris/app/storage.py::init_schema` che il meccanismo faccia quello che ti aspetti
in **entrambi** i casi: database nuovo (la tabella non nasce e la versione viene stampata direttamente)
e database esistente alla versione precedente (la migrazione gira e la tabella sparisce). Scrivi un
test per ciascuno dei due casi — una migrazione non testata è una scommessa sul riavvio dell'utente.

- [ ] **Step 3: Togli la catena**

Rimuovi il tool, il gestore, il ramo del dispatcher, `add_link`, e la riga di pulizia
`DELETE FROM knowledge_links` dentro `delete_item`. Nessun moncone, nessun commento-lapide.

Aggiorna i test che citano la tabella (ce n'è almeno uno che asserisce la sua presenza nello schema:
deve diventare un'asserzione di **assenza**) e quelli che esercitavano il tool.

- [ ] **Step 4: Esegui tutto, in primo piano**

```
python -m pytest -q
npm test
```
Il conteggio scende: dillo, con i numeri prima e dopo.

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(memoria): via i collegamenti fra ricordi, che nessuno leggeva"
```

---

## Verifica live (obbligatoria prima di dire che funziona)

La suite verde non è una prova.

1. Bumpa la versione e aggiorna l'add-on. **Non configurare alcun provider di embedding** — è il
   caso che stiamo riparando.
2. In chat: «ricordati che la revisione della caldaia scade il 15 ottobre».
3. Apri **Memoria** nella chat: l'elemento deve comparire fra quelli in attesa.
4. Approvalo. Deve riuscire — oggi risponde `503`.
5. Verifica che sia nel database:
   `sqlite3 /data/knowledge.db "SELECT kind,status,due_date,content FROM knowledge_items ORDER BY id DESC LIMIT 3;"`
6. Attendi il resoconto delle 08:00 (o chiedi in chat il briefing giornaliero): la scadenza deve
   comparire.
7. Controlla che **niente sia peggiorato** per chi un embedder ce l'ha: se ne configuri uno, il
   richiamo per somiglianza deve continuare a funzionare come prima.

## Cosa questa fetta NON fa

- **Non toglie la ricerca vettoriale dagli item.** Chi ha un embedder continua ad avere il
  confronto dei significati. Toglierlo è la **fetta 2b**, e la recency costruita qui diventerà lì
  l'unica strada — niente viene costruito due volte.
- **Non porta scadenze e insight dentro il ritratto** — è la **fetta 2c**.
- **Non bonifica le righe già scritte** con vettore nullo: dopo questa fetta sono raggiungibili dal
  percorso recency, il che è già il grosso del recupero. Un re-embed vero non esiste e non serve.
- **Non tocca i documenti.** Restano vettoriali, e sono l'unico posto dove il vettore si guadagna
  il suo costo.
