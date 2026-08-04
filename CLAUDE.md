# HIRIS — contesto per Claude Code

## ⚠️ Leggi prima questo

HIRIS è in **Refactor 2.0** (dal 4 agosto 2026). Il prodotto è stato ri-scopato da zero e una parte
del codice esistente è **deliberatamente condannata**. Prima di scrivere qualunque riga:

| Domanda | Documento |
|---|---|
| Cosa **deve** fare HIRIS | `docs/design/2026-08-04-scope-hiris.md` — **il contratto** |
| Cosa **fa oggi** il codice | `docs/design/2026-08-03-analisi-funzionale.md` — con riferimenti `file:riga` |
| Che **stato tecnico** ha | `docs/design/2026-08-03-revisione-tecnica.md` |

Tutto ciò che sta in `docs/archive/` e in `docs/superpowers/_archivio-pre-refactor-2.0/` è **storia,
non specifica**: descrive il prodotto precedente. Non usarlo come fonte.

---

## Che cos'è HIRIS

> **HIRIS è l'intelligenza della casa.**
>
> Sa tutto ciò che della casa si può sapere — Home Assistant, i documenti, le fonti che verranno —
> impara da ciò che vede, e da quella conoscenza **costruisce le cose che servono a far funzionare
> la casa**: automazioni, script, scene, plance quando basta il determinismo; **agenti** quando
> serve giudizio.

Add-on standalone di Home Assistant, aperto via Ingress.

**HIRIS non è**: un cruscotto dello stato della casa (lo fa HA), un playground di LLM, un
sostituto di HA. È il suo livello di giudizio.

## Le tre leggi

Sono **criteri di ammissione**, non linee guida. Una funzione che ne viola una non entra — o esce.

1. **Sussidiarietà** — se Home Assistant lo sa fare, si crea un oggetto di Home Assistant.
   L'agente esiste solo dove serve **giudizio**. Ogni funzione deve saper rispondere a
   *«perché questo non è un'automazione HA?»*.
2. **Autoconsistenza** — automazione e agente sono oggetti **distinti e completi**; nessuno dei due
   dipende dall'altro. Corollario: **l'agente ha i propri sensi**.
3. **Ogni agente ragiona** — se non ragiona non è un agente: è un'automazione, e nasce in HA.

## L'impianto

**① Conoscenza** (fondazione, multi-fonte) → **② Brain** (legge tutto, impara e aggiorna la propria
memoria **da solo**, apre questioni e **propone**; non tocca la casa senza un sì) → **③ Agenti**
(unici esecutori, autosufficienti, nascono da un comando testuale o da una proposta del Brain,
attivi solo dopo un sì).

**La porta è la Chat**: si interroga il Brain e si **costruisce** con lui.

**Il perimetro** — ciò che si approva: **permessi** (cosa può toccare) + **freni** (frequenza,
budget, scadenza) + **stato** (attivo/sospeso/revocato).

## Ogni fetta è anche pulizia

Il Refactor 2.0 non è solo lavoro a feature: **è una fase di pulizia e ottimizzazione della
codebase.** HIRIS è cresciuto per accumulo — ogni sprint aggiungeva, nessuno toglieva. Il refactor
esiste per invertire quel verso, e una fetta che aggiunge senza togliere lo tradisce.

In ogni piano e in ogni task:

- **Il codice morto si cancella, non si documenta.** Nessun chiamante in produzione → esce. Git lo
  conserva.
- **Le funzioni doppie si unificano.** Due copie della stessa logica sono un difetto anche quando
  oggi coincidono; se governano riservatezza o sicurezza sono una falla, non uno stile.
- **Costanti e commenti orfani se ne vanno** insieme al codice che li giustificava.
- **Meglio togliere che aggiungere un ramo**: un comportamento solo, non due configurabili.

Nomina in chiaro nel piano ciò che verrà cancellato, così la cancellazione è rivedibile invece che
silenziosa.

## Cosa è condannato dal refactor

Se stai per estendere una di queste cose, **fermati e chiedi**:

| Condannato | Perché |
|---|---|
| **modalità regola** (agente senza ragionamento) | viola la Legge III |
| **rilevatori integrati come esecutori** (`watcher/detectors.py`) | violano la Legge I: sono automazioni HA di sei righe |
| **semaforo per-azione** (`security/semaphore.py`, 4 colori × N domini × 3 percorsi di conferma) | assorbito nei permessi del perimetro |
| **vocabolario** «Sentinella», «Agentbot», «Persona», «Lente» | resta **agente** |
| **il workbench come prodotto** (sandbox/eval/telemetria per-entità) | mai costruito; non è ciò che serve alla casa |

`PRODUCT.md` è **superato** su scopo, utenti e criteri di successo. Restano validi solo i suoi
capitoli su identità visiva e accessibilità.

---

## Stack

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.13 + aiohttp |
| LLM | Claude API · OpenAI · OpenRouter · Ollama locale · abbonamento Claude via runner in-addon |
| Frontend | JS moderno, **nessun build step** — `<script src>` con fingerprint per-file iniettato server-side |
| Integrazione HA | Supervisor Ingress, `SUPERVISOR_TOKEN` |
| Config | opzioni add-on (`hiris/config.yaml`) |
| Porta | 8099, solo interna, via Ingress |
| Persistenza | SQLite in `/data` + file JSON |

## Struttura reale

Verificala con `ls hiris/app/` — questa lista deriva dal codice, non da un piano.

```
hiris/                    # config.yaml, Dockerfile, run.sh, requirements.txt
└── app/
    ├── main.py           # factory aiohttp + run_app
    ├── server.py         # ~3000 righe: registrazione rotte E gran parte del wiring
    ├── claude_runner.py  # loop agentico Claude + orchestrazione tool
    ├── chatbot_engine.py · llm_router.py · task_engine.py · chat_store.py
    ├── model_activation.py · storage.py · mqtt_publisher.py · env_util.py · version.py
    ├── api/        (26 file) handlers_* — la superficie HTTP
    ├── tools/      (19)      i tool esposti al modello + dispatcher.py
    ├── brain/      (22)      health_scan, advisory_store, knowledge_store, coverage_review, briefing
    ├── proxy/      (11)      ha_client.py (il VERO client HA: REST+WS), semantic_context_map
    ├── watcher/    (17)      guardian, detectors, agentbots, evaluator, executor  ← area condannata
    ├── backends/   (7)       runner OpenAI-compat, embeddings, pricing
    ├── security/   (2)       semaphore.py                                        ← area condannata
    ├── mcp/ · history/ · reasoning/ · agent/
    └── static/     index.html · config.html · chat/*.js · config/*.js · hiris-chat-card.js
```

**Non esistono** (li citavano vecchi documenti): `app/routes.py`, `app/ha_client.py`,
`app/agent_engine.py`, `api/handlers_agents.py`.

---

## Come si lavora qui

### Test
```bash
python -m pytest -q          # ~2070 test
npm test                     # ~100 test frontend: node --test + jsdom
```
Il frontend ha **test comportamentali reali**, non solo `node --check`. Il `Dockerfile` copia solo
`app/`, `config.yaml` e `run.sh`: `package.json` e `node_modules` **non** entrano nell'immagine.

### Regole non negoziabili

- **Ogni push funzionale bumpa la versione**, altrimenti i client non si aggiornano.
- **Prima di affermare che qualcosa funziona: verifica live.** I bug di questo progetto emergono
  eseguendo, non leggendo. La suite verde non è una prova.
- **Conferma esplicita dell'utente** prima di ogni commit, push o tag.
- **Uno sprint è completo su tutta la codebase toccata**, non solo sul file d'ingresso.
- Un nuovo kwarg di `ClaudeRunner` deve essere accettato **anche** da `OpenAICompatRunner`, o i
  backend non-Claude si rompono in silenzio.
- Impostazione tecnica nuova: **prima nella UI dell'add-on**, poi come variabile d'ambiente. Una
  env var che `run.sh` non esporta è di fatto una costante.
- Frontend: interpellare l'agente `ux-ui-specialist` prima di disegnare.
- Mai `*/` dentro un commento a blocco JS: rompe il boot. Validare con `node --check`.

### Trappole note

- **Cache**: la shell HTML è `no-store`, gli asset sono fingerprintati per contenuto. Se un
  comportamento non cambia dopo un aggiornamento, il sospetto n.1 è Cloudflare o un container non
  ricostruito — non il codice. `/api/health` espone un `build` stamp per distinguere.
- `save_policy` ricostruisce da `DEFAULT_POLICY` e **strippa ogni chiave top-level sconosciuta**:
  lo stato del Brain vive in file sidecar, non nella policy.
- Molte funzioni sono **inerti di fabbrica** (semaforo spento, embedding vuoto, storico opt-in,
  documentale spento). Prima di dare la caccia a un bug, verifica che la funzione sia accesa.

---

## Procedura di rilascio

Da seguire **in ordine** quando l'utente chiede un rilascio.

**1. Raccogliere i commit**
```bash
git log $(git describe --tags --abbrev=0)..HEAD --oneline
```

**2. Proporre la versione** — `feat:` → minor · `BREAKING`/`!:` → major · solo `fix:`/`chore:`/
`docs:`/`test:` → patch. Mostrare all'utente e **attendere conferma**.

**3. Bozza CHANGELOG** in formato Keep-a-Changelog (`Added` ← feat · `Fixed` ← fix ·
`Changed` ← refactor/perf · `Removed`). **Attendere approvazione.**

**4. Aggiornare i file** — sezione approvata in cima a `CHANGELOG.md` sotto l'intestazione;
`hiris/config.yaml` → `version: "X.Y.Z"`.

**5. Eseguire lo script** — **solo Bash, mai PowerShell**
```bash
python scripts/release.py --version X.Y.Z
```

**6. Riportare l'output completo.** Uscita 0 → annunciare il rilascio. Diversa da 0 → mostrare il
passo fallito e **non ritentare automaticamente**.

> **Se lo script fallisce dopo aver già creato commit e tag**: non rilanciarlo (fallirebbe perché il
> tag esiste). Diagnosticare il passo specifico — push rifiutato →
> `git push origin master --tags`; `gh` mancante → creare la Release a mano su
> `https://github.com/paolobets/hiris/releases/new`.
