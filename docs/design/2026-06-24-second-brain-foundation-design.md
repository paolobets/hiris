# Second Brain — Fondazione (design)

- **Data:** 2026-06-24
- **Stato:** Design approvato (Sezioni 1–7) — pronto per il piano d'implementazione
- **Ambito:** la *fondazione dati persistente* del "second brain" di HIRIS. I domini applicativi (pasti, finanze, scadenze, ecc.) sono consumatori successivi, ciascuno con il proprio ciclo spec→piano.

---

## 1. Contesto e obiettivo

HIRIS deve evolvere da assistente domotico a **assistente di casa con un cervello persistente**: oltre alla struttura di Home Assistant, deve conoscere abitudini, preferenze, scadenze, finanze e documenti, e ragionarci sopra (cosa cucinare, quando pagare la TARI, come risparmiare dagli estratti conto).

Oggi HIRIS ha solo **recupero vettoriale piatto, che scade, per-agente** (`memory_store`) e una conoscenza entità-centrica (`knowledge_db`). Manca una base di conoscenza **persistente, per-persona, multi-tipo e collegata**.

Questo documento progetta **solo la fondazione**: il substrato dati su cui i domini si costruiranno. Si progetta coerente; si implementa incrementale.

### Obiettivi
- Conoscenza **persistente** (la memoria *resta*; niente TTL forzato).
- **Per-persona** (utente HA) con fallback condiviso `home`.
- Modello **ibrido**: vettore (recall) + strutturato (query/aggregazioni/promemoria) + grafo (collegamenti).
- Popolamento **ibrido-con-conferma** (HIRIS propone, l'utente approva) + inserimento manuale.
- **Privacy a strati** per i dati sensibili, rispettando il multi-modello/multi-agente di HIRIS.
- Riuso massimo del codice esistente; filosofia "orchestra, non reinventare".

### Non-obiettivi (questa fondazione)
- Le app di dominio (pianificatore pasti, analisi finanziaria, ecc.).
- Vision/OCR proprietari (deleghiamo a Mayan).
- Un secondo motore di *ragionamento* (resta il `llm_router` esistente).

---

## 2. Decisioni chiave (decision log)

| # | Decisione | Motivazione |
|---|---|---|
| D1 | **Approccio A**: store unico `sqlite` di knowledge-item tipizzati + grafo + chunk | Modello ibrido su cui converge la ricerca 2025-26; generalizza ciò che esiste; sqlite-nativo come il resto |
| D2 | **Persistenza di default** (niente `expires_at` forzato; `valid_until` opzionale) | "La memoria resta" è il principio del second brain |
| D3 | **Per-persona = utente HA** (header ingress / `hass.user`) | Identità automatica reale, senza nuova infrastruttura |
| D4 | **Embedding locali** (model2vec, già presente) | Indicizzazione offline → grande vantaggio di privacy |
| D5 | **Privacy a strati**, non un proiettile d'argento | La leva più forte è *non* mandare il grezzo (estrazione + aggregati + pseudonimizzazione) |
| D6 | **Routing privacy = trasformazione, NON scelta provider** | HIRIS è multi-modello: si applica il **modello dell'agente selezionato**; niente forzatura su API. Porta abbonamento **aperta** |
| D7 | **Brain condiviso tra agenti**, con **accesso per-agente** sui sensibili | È il cervello *di casa*; ma un monitor non deve vedere gli estratti conto |
| D8 | **Documenti via connettore Mayan** (192.168.1.31:8090) | Risolve l'OCR, tiene i doc in locale (privacy), filosofia "orchestra" |
| D9 | Vector search **brute-force** ora; `sqlite-vec` solo se scala | A scala domestica brute-force è millisecondi; evita dipendenza nativa arch-specifica |

---

## 3. Architettura

Nuovo sottosistema **`brain`** (separato da `knowledge_db`, che resta dedicato alle classificazioni entità HA). Espone una `KnowledgeStore` sqlite-nativa.

Tre modalità di conoscenza nello stesso store:
- **Vettore** — recall semantico (model2vec) su item e chunk documentali.
- **Strutturato** — colonne tipizzate (`amount`, `due_date`, `category`) per query/aggregazioni/promemoria.
- **Grafo** — collegamenti tipizzati tra item (generalizza `entity_correlations`).

**Flusso dati:** ingest (chat / manuale / Mayan / agenti) → proposta (`pending`, l'utente conferma) → store (persistente) → retrieval (vettore + strutturato + grafo) → iniezione nel contesto LLM (con lo strato privacy applicato all'egress).

**Aggancio ai moduli esistenti:** `embeddings` (vettori locali), `task_engine`/`agent_engine` (promemoria scadenze), `llm_router` (routing per-item + egress privacy + cloud-vs-locale), `semantic_context_map` (iniezione nel prompt), pattern `proposal_store`/`handlers_proposals` (loop conferma), nuovo connettore Mayan (documenti).

**Moduli previsti:**
- `brain/knowledge_store.py` — `KnowledgeStore` (items, links, document_chunks).
- `brain/privacy.py` — pseudonimizzatore + redactor + vault.
- `brain/retriever.py` — retrieval ibrido.
- `brain/mayan_client.py` — connettore REST a Mayan (con circuit-breaker).
- tool LLM: `save_knowledge`, `recall_knowledge`, `link_knowledge`.

---

## 4. Modello dati

### 4.1 `knowledge_items` (nodo centrale)

```
knowledge_items
  id           INTEGER PK
  kind         TEXT     -- fact | preference | obligation | expense | note | document
  owner        TEXT     -- 'home' (condiviso) | <ha_user_id>  (per-persona)
  title        TEXT     -- etichetta breve
  content      TEXT     -- testo umano (embeddato e mostrato)
  data         TEXT     -- JSON: campi per kind (currency, recurrence, ...)
  amount       REAL     NULL  -- colonna promossa (spese)
  due_date     TEXT     NULL  -- colonna promossa ISO (scadenze → task_engine)
  category     TEXT     NULL  -- colonna promossa (raggruppamenti/grafici)
  embedding    BLOB     NULL  -- vettore locale (vec_to_blob)
  sensitivity  TEXT     -- 'normal' | 'sensitive'  (governa il routing privacy)
  source       TEXT     -- chat | manual | mayan | agent
  source_ref   TEXT     NULL  -- es. id documento Mayan, id sessione chat
  confidence   REAL     DEFAULT 1.0
  status       TEXT     -- 'pending' | 'approved'  (loop ibrido-con-conferma)
  valid_from   TEXT     NULL
  valid_until  TEXT     NULL  -- finestra di validità opzionale (NON un TTL)
  created_at   TEXT
  updated_at   TEXT
-- indici: (owner), (kind), (due_date), (status), (category)
```

Note di progetto:
- **JSON `data` + colonne promosse**: i campi che si interrogano/aggregano/ordinano (`amount`, `due_date`, `category`) sono colonne reali; il resto sta nel JSON. Interrogare dentro il JSON è lento e fragile.
- **`owner`** realizza il per-persona con fallback `home`.
- **`sensitivity`** è il trigger dello strato privacy (vedi §5).
- **`status`** ospita il loop: `pending` (proposto) → `approved` (recuperabile).

### 4.2 `knowledge_links` (grafo)

```
knowledge_links
  id          INTEGER PK
  src_id      INTEGER  -- FK knowledge_items.id
  dst_id      INTEGER  -- FK knowledge_items.id
  relation    TEXT     -- about | belongs_to | paid_for | related | mentions | recurs_as
  weight      REAL     DEFAULT 1.0
  source      TEXT     -- inferred (LLM) | manual | mayan_tag
  created_at  TEXT
-- unique(src_id, dst_id, relation); indici su src_id, dst_id
```

Archi diretti/tipizzati/pesati. Abilitano retrieval **multi-hop** (1-hop in v1) = GraphRAG-lite. Link inferiti dall'LLM nascono `pending` come gli item.

### 4.3 `document_chunks` (testo OCR locale, riferito a Mayan)

```
document_chunks
  id            INTEGER PK
  item_id       INTEGER  -- FK knowledge_items.id (nodo kind='document')
  mayan_doc_id  TEXT     -- provenienza
  chunk_index   INTEGER
  content       TEXT     -- chunk di testo OCR
  embedding     BLOB     -- vettore locale (model2vec)
  created_at    TEXT
-- indice su item_id
```

HIRIS **non** archivia i binari: il documento è un `knowledge_items` con `kind='document'`, `source='mayan'`, `source_ref=<id>`; i chunk OCR (embeddati in locale) vivono qui.

### 4.4 `pseudonym_vault` (mappa PII↔token, locale)

```
pseudonym_vault
  id          INTEGER PK
  token       TEXT   -- [PERSONA_1], [IBAN_1], [CONTO_1]
  value_hash  TEXT   -- HMAC-SHA256(valore) per lookup
  value_enc   BLOB   -- valore reale, cifrato a riposo (chiave locale)
  pii_type    TEXT   -- person | iban | card | email | phone | codice_fiscale
  created_at  TEXT
-- unique(value_hash); index(token)
```

Mai inviato. La de-tokenizzazione delle risposte avviene in locale.

### 4.5 Convenzioni store
- sqlite con `CREATE TABLE IF NOT EXISTS` + `schema_version` (pattern esistente).
- Lock di scrittura come negli store già induriti (`memory_store._mu`, `_save_lock`).
- Serializzazione vettori e cosine riusati da `backends/embeddings.py`.

---

## 5. Privacy & sicurezza

Difesa **a strati** (nessun singolo "passaggio anonimo"):

1. **Strato 0 — provider**: i dati via **API Anthropic** non sono usati per training (ritenzione 7 giorni; ZDR enterprise). L'API è più privata dell'abbonamento *consumer*. La scelta del provider resta per-agente (D6).
2. **Strato 1 — minimizzazione**: parsing documenti in locale → record strutturati → al modello vanno **aggregati/cifre derivate**, mai il grezzo.
3. **Strato 2 — pseudonimizzazione reversibile**: PII → token stabili (vault), il modello ragiona sui token, **de-tokenizzazione locale** della risposta.
4. **Strato 3 — redaction backstop**: recognizer regex IT (IBAN, codice fiscale, carta, email, telefono) come rete.
5. **Strato 4 — a riposo**: `value_enc` cifrato con chiave locale; SQLCipher (DB intero) **differito + documentato**; auth-gate già presente.

### Pipeline di egress (la correzione D6)
Quando si assembla il prompt per un agente, per ogni item `sensitive` iniettato:
- **minimizza → pseudonimizza → redaction**, *poi* invia al **modello dell'agente selezionato** (qualunque backend);
- **condizionata sul target**: il `llm_router` espone se il modello è **cloud o locale** → se locale si può inviare in chiaro, se cloud si trasforma;
- al ritorno, **de-tokenizzazione locale**.

Vive in `brain/privacy.py`, invocato al confine d'iniezione contesto, guidato da `sensitivity` + backend risolto dell'agente.

---

## 6. Accesso multi-agente & identità

- **Identità utente HA**: leggi `X-Remote-User-Id`/`X-Remote-User-Name` (header ingress del pannello) e `hass.user` (card) → risolvi `owner` per i nuovi item; filtra il retrieval per owner (item della persona + `home`). Piccola aggiunta al layer auth (oggi gestisce solo `X-Ingress-Path`).
- **Accesso per-agente**: il brain è **condiviso** di default, ma i `sensitive` hanno accesso per-agente via una policy **`knowledge_access`** sull'agente, nello spirito di `allowed_tools`/`allowed_entities`. Forma concreta:
  ```
  knowledge_access = {
    allow_sensitive: bool,        # default false — può recuperare item sensitive
    kinds: list[str] | "all",     # default "all" — quali kind può recuperare
  }
  ```
  Default: gli agenti accedono al `normal` di tutti i `kind`; solo agenti con `allow_sensitive: true` recuperano i `sensitive`.
- **Filtro di retrieval**: `(owner) AND (knowledge_access dell'agente) AND status='approved'`.

---

## 7. Retrieval ibrido

`brain/retriever.py`, dato query + contesto agente:
- **Vettore**: cosine su `knowledge_items` + `document_chunks` (brute-force, model2vec), filtrato per owner + accesso + `approved`.
- **Strutturato**: SQL per query tipizzate (prossime `due_date`, aggregazioni spese per `category`/mese) — usato dai domini e dall'LLM via tool.
- **Grafo**: espansione **1-hop** dai risultati vettoriali via `knowledge_links`.
- **Merge/rank** → blocco di contesto; l'**egress privacy** (§5) si applica a questo blocco prima del prompt.

---

## 8. Integrazioni

- **Mayan** (`brain/mayan_client.py`): client REST (token), **circuit-breaker** (degrado se .31 giù). Scoped a un **cabinet/tag "HIRIS"** = l'utente cura cosa entra. Pipeline: nuovo doc → OCR via API → chunk → embed locale → item `kind='document'` → opzionale estrazione record strutturati (su testo pseudonimizzato) come proposte `pending`. **Sync v1: polling**; webhook/workflow dopo. **Mai** le feature AI-cloud di Mayan sui sensibili.
- **Task-engine (promemoria)**: job periodico su `kind='obligation' AND due_date` in avvicinamento → notifica via `task_engine`/`agent_engine`.
- **Loop ibrido-con-conferma**: tool `propose_knowledge` (fratello della proposta-automazioni); UI che estende `handlers_proposals`/pannello per approvare/modificare/rifiutare i `pending`. Inserimento manuale = scrittura diretta `approved`.
- **Tool LLM**: `save_knowledge` (proponi), `recall_knowledge` (query semantica+strutturata), `link_knowledge` (proponi link). Gated dal `knowledge_access` dell'agente.

---

## 9. Scope v1 vs Differito

### v1 (la fondazione)
- `KnowledgeStore` (items + links + document_chunks, sqlite, schema_version, lock).
- Embed locale + retrieval vettoriale brute-force.
- `owner` per-persona (lettura identità HA).
- `sensitivity` + `pseudonym_vault` + redactor regex + egress consapevole-del-modello (cloud/locale).
- Policy `knowledge_access` per-agente.
- Tool `save`/`recall`/`link` + loop `pending`/`approve` + UI minima.
- Connettore Mayan (polling, OCR, chunk+embed locale) scoped a tag/cabinet.
- Hook promemoria su `due_date`.

### Differito (Fase 2+)
- Template di estrazione strutturata per banca.
- `sqlite-vec` (solo se la scala lo impone).
- SQLCipher (cifratura DB intera).
- Webhook/workflow Mayan (push) al posto del polling.
- Export markdown / graph-view per navigabilità umana (la "faccia di C").
- Ragionamento di grafo multi-hop ricco.
- PII via NER (oltre i regex).
- Menu-immagine / vision.

---

## 10. Test

- **Store**: CRUD, filtri `owner`/`sensitivity`, vector search, traversata link.
- **Privacy** (percorso a più alto rischio → copertura prioritaria): round-trip token↔valore, recognizer IT, de-tokenizzazione, egress condizionato cloud/locale.
- **Accesso**: un agente con/senza `knowledge_access` vede/non vede i `sensitive`.
- **Mayan client**: API mockata + comportamento del circuit-breaker.
- **Promemoria**: hook su `due_date` schedula via task-engine.
- Stile `pytest` esistente; nessuna regressione sulla suite attuale.

---

## 11. Rischi & questioni aperte

- **Qualità OCR** su estratti conto scansionati → estrazione strutturata meno affidabile; mitigazione: template per banca (Fase 2) o estrazione assistita da LLM su testo pseudonimizzato.
- **Dipendenza da .31/Mayan** per le feature documentali → degrado controllato via circuit-breaker; le funzioni non-documentali restano operative.
- **Detection PII non garantita** (regex) → è uno strato *aggiuntivo*, non unico; default conservativo `sensitive` nel dubbio.
- **Chiave di cifratura del vault**: gestione/rotazione da definire (env / HA secrets).
- **Stato condiviso del runner sotto concorrenza** (già noto, diagnostico) → indipendente da questa fondazione, ma da tenere presente per il retrieval concorrente.
