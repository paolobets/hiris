# HIRIS — contesto per Claude Code

## ⚠️ Leggi prima questo

HIRIS è in **Refactor 2.0** (dal 4 agosto 2026). Il prodotto è stato ri-scopato da zero e una parte
del codice esistente è **deliberatamente condannata**. Prima di scrivere qualunque riga:

| Domanda | Documento |
|---|---|
| Cosa **deve** fare HIRIS | `docs/design/2026-08-04-scope-hiris.md` — **il contratto** |
| Cosa **c'è dentro**, e cosa ne resta | `docs/design/2026-08-05-mappa-funzionalita.md` — **l'ordine di demolizione** |
| Come si conosce la casa | `docs/design/2026-08-05-la-conoscenza-di-hiris.md` |
| Cosa **fa oggi** il codice, in dettaglio | `docs/design/2026-08-03-analisi-funzionale.md` — con `file:riga`. **Descrive**; la mappa **decide** |
| Che **stato tecnico** ha | `docs/design/2026-08-03-revisione-tecnica.md` |

Il lavoro del Refactor 2.0 vive sul ramo **`2.0`**. Non un repository nuovo: la mappa ha chiesto di
**cancellare**, non di riscrivere — e cancellare si verifica con i test esistenti, ricostruire no.

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

## Le quattro fondamenta — come sono fatti gli oggetti

Le tre leggi qui sopra dicono **cosa entra** nel prodotto. Queste dicono **com'è fatto ciò che
entra**: sono un asse diverso, e valgono per ogni dato, ogni struttura e ogni fetta — passata,
presente e futura. Decise dal proprietario il 17 agosto 2026, come **fondamenta indiscusse**.

Ogni review — di codice, di disegno, di spec — le verifica. Una violazione non è un'opinione di
stile: è un difetto.

**1. Atomicità — un oggetto porta tutto ciò che serve a interpretarlo da solo.**
Un valore senza la sua unità e senza il suo significato non è un oggetto: è un frammento. Chi lo
riceve deve poterlo leggere **senza andare a cercare altrove** cosa voglia dire.
> *Pagata:* HIRIS leggeva `72` e non sapeva se fossero gradi Celsius o Fahrenheit. L'unità c'era —
> letta in due punti diversi — e si fermava prima di arrivare a chi doveva leggerla.

**2. Nessun doppione — ogni fatto ha una sola casa.**
Gli oggetti si collegano **per identificatore**, mai copiando i dati. Se due posti sanno la stessa
cosa, prima o poi uno dei due mente, e non si saprà quale.
> *Pagata tre volte in un giorno:* la mappa area→entità costruita con due chiamate WebSocket mentre
> `gerarchia()` la faceva già, e meglio · `PRICING.get(model, PRICING["_default"])` scritto in linea
> in due runner con la funzione che lo fa ferma e inutilizzata · la regola di «notevole» in
> `buildDisplayChain` e `reconcile_chain`, che è stata **il meccanismo** con cui la pagina Modelli
> poteva essere vera riga per riga e falsa nel complesso.

**3. Consistenza — la stessa cosa ha la stessa forma da tutte le porte.**
Un'entità vista da `guarda`, da `cerca` o dal nucleo è la stessa entità, con gli stessi campi e gli
stessi nomi. Un campo che compare da una porta e non dall'altra è un difetto anche quando nessuna
delle due è sbagliata.
> *Pagata:* `nome_dedotto` usciva solo da `_guarda_entita` e non da area e dispositivo (rilievo I1);
> `nome_dedotto` era una **stringa** in un posto e un **booleano** in un altro (I2).

**4. Autonomia funzionale — ogni oggetto ha la sua funzionalità, richiamabile dagli altri.**
Se un dato c'è e nessuno può chiederlo, **non esiste**. Un oggetto deve saper vivere da solo, ed
essere letto e interpretato in autonomia.
> *Pagata:* le **etichette** sono lette dai registri, salvate in tabella e arrivano fino all'albero
> delle aree — e non compaiono in nessuna risposta. La piattaforma di un'entità idem: zero lettori.

### Come si verificano

Davanti a un dato nuovo, o a una struttura che si tocca, si risponde a quattro domande:

1. Chi lo riceve può interpretarlo **senza sapere altro**?
2. Questo fatto **vive già** da qualche altra parte?
3. Ha la **stessa forma** da tutte le porte da cui si può guardare?
4. Esiste un modo per **chiederlo**?

## L'impianto

**① Conoscenza** (fondazione, multi-fonte) → **② Brain** (legge tutto, impara e aggiorna la propria
memoria **da solo**, apre questioni e **propone**; non tocca la casa senza un sì) → **③ Agenti**
(unici esecutori, autosufficienti, nascono da un comando testuale o da una proposta del Brain,
attivi solo dopo un sì).

**Dove sta oggi il prodotto in quell'impianto.** ① c'è. ② e ③ no. Dalla fetta «comandare»
(agosto 2026) la **chat** esegue: chiede a `hiris/app/azione/porta.py`, che verifica la chiamata
contro l'installazione, la esegue e rilegge lo stato. Non è ③ — non c'è nessun agente, nessuna
autonomia, nessun perimetro da approvare — è la chat che fa una cosa sola quando gliela chiedi.
Quando ② e ③ arriveranno, **quella porta resta l'unica**: chi vuole agire chiede a lei. Un secondo
punto di scrittura è un difetto, non un'ottimizzazione.

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

### Prima le strutture, poi le sicurezze

**Istruzione dell'utente, 7 agosto 2026:** *«creiamo le strutture e poi applichiamo le sicurezze. Una
volta terminato di creare le basi andiamo a individuare i rischi e creare le sicurezze. Non ereditiamo
queste dalla versione precedente.»*

Le protezioni della `1.x` — filtri di riservatezza, ambito per proprietario, `sensitivity`, coda di
approvazione, semaforo — sono state costruite per **un altro prodotto**: uno con un Brain che
produceva duecento insight, chatbot multipli e un gateway esposto verso l'esterno. Portarle avanti
significa portarsi dietro **il modello di minaccia di quel prodotto**, e smettere di cercare i rischi
veri del nuovo. `sensitivity` lo ammette per iscritto: nasce da un'epoca in cui la memoria era
per-chatbot.

Quindi: **si costruisce la struttura nuda, e le difese si derivano dopo, dai rischi che la struttura
nuova ha davvero.**

**La distinzione che questa regola NON autorizza a saltare:** un comportamento scritto nel contratto
non è un'eredità. La ricerca che degrada ai più recenti senza embedder, ciò che una persona ha detto
che entra sempre in contesto, la memoria che non evapora — stanno in
`docs/design/2026-08-05-la-conoscenza-di-hiris.md`, e sono **cosa costruiamo**, non cosa ereditiamo.

### La review totale — a ogni sviluppo

In un progetto di demolizione **la domanda della review si rovescia**. Una review normale chiede
*«ciò che hai aggiunto è corretto?»*. Qui si chiede: **«cosa hai lasciato orfano?»**

Le righe morte non stanno **dentro** il diff. Stanno altrove, e ci sono arrivate perché la modifica
ha tolto il loro ultimo chiamante. Guardare il diff non le trova: **ogni sviluppo si chiude con una
review dell'intero ramo**, non del solo diff della fetta.

Cerca cinque cose:

| | |
|---|---|
| **Senza chiamanti** | funzioni, rotte HTTP, tabelle, opzioni dell'add-on, variabili d'ambiente |
| **Scritte e mai lette** | tabelle che si riempiono e nessuno interroga |
| **Configurabili solo a parole** | opzioni lette dal codice che nessuna interfaccia può cambiare |
| **Doppioni divergenti** | due funzioni che fanno la stessa cosa con logiche diverse |
| **Test orfani** | asserzioni che difendono un comportamento che abbiamo deciso di togliere |

L'ultimo è il più insidioso: i test sono **più grandi dell'applicazione**. Demolire il codice senza
demolire i test significa difendere con centinaia di asserzioni ciò che si è appena deciso di
rimuovere, e pagarne il prezzo a ogni fetta successiva. **Anche i test si smontano**, insieme a ciò
che testavano.

Fatta a occhio su 43.000 righe questa regola non è eseguibile: usa `python scripts/censimento.py`,
che la rende un comando invece di una buona intenzione.

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
    ├── server.py         # ~1.900 righe: registrazione rotte E gran parte del wiring
    ├── claude_runner.py  # loop agentico Claude + orchestrazione tool
    ├── llm_router.py · chat_store.py · impostazioni_chat.py · model_activation.py
    ├── config.py · storage.py · env_util.py · version.py
    ├── api/        (14 file) handlers_* — la superficie HTTP
    ├── casa/       (8)       anagrafe, archivio, comportamento, nucleo, domande, strumenti
    ├── azione/     (4)       porta.py — l'UNICO punto che esegue — verifica.py, registro.py
    ├── backends/   (7)       runner OpenAI-compat, embeddings, pricing
    ├── memoria/    (4)       archivio, interpretazione, riconoscitore
    ├── proxy/      (4)       ha_client.py (il VERO client HA: REST+WS), entity_cache, _sanitize
    ├── agent/      (3)       runner.py (il ponte push) + prompts.py
    ├── reasoning/  (2)
    └── static/     index.html · config.html · chat/*.js · config/*.js
```

**Non esistono più** (li citano vecchi documenti e i commenti storici del codice):
`app/routes.py`, `app/ha_client.py`, `app/agent_engine.py`, `api/handlers_agents.py`,
e — dopo le tre fette di demolizione del 2.0 — `app/chatbot_engine.py`, `app/task_engine.py`,
`app/mqtt_publisher.py`, e le cartelle `tools/`, `watcher/`, `security/`, `mcp/`.
Dalla fetta «esce il documentale» (2.1.0) non esistono più nemmeno le cartelle `app/brain/` e
`app/history/`, né `api/handlers_knowledge.py` e `api/handlers_history_policy.py`: l'integrazione
documentale (Mayan), l'archivio di conoscenza (`knowledge.db`), la cattura dello storico
(`history.db`) e la pseudonimizzazione (`privacy.py`, `vault.db`) sono uscite insieme — nessuna
aveva più un consumatore vivo. La conoscenza vive in `casa/` (l'anagrafe, il nucleo) e in
`memoria/` (ciò che le persone hanno detto).
Dalla fetta E5 (Task 5) non esiste più nemmeno `static/hiris-chat-card.js`, la card Lovelace:
è uscita per intero — file, copia dentro Home Assistant, registrazione della risorsa — e tornerà
riscritta da zero come ultimo passo, quando il prodotto sarà completo. Al suo posto `server.py`
tiene solo la **disinstallazione** (`_disinstalla_card_lovelace`), perché quelle scritture
stavano nella configurazione dell'utente, non dentro l'add-on.
La tabella «Cosa è condannato» qui sopra resta valida come **regola**, ma i percorsi che cita
(`watcher/detectors.py`, `security/semaphore.py`) sono ormai riferimenti storici: quelle aree
sono uscite con le fette E2 ed E3.

---

## Come si lavora qui

### Test
```bash
python -m pytest -q          # 1.207 test + 1 skip (2.0 @ riserve della fetta «comandare» chiuse)
npm test                     # 92 test frontend: node --test + jsdom
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
- Alcune funzioni sono **inerti di fabbrica**. Prima di dare la caccia a un bug, verifica che la
  funzione sia accesa. Caso limite di questa regola: dalla 2.1.0 l'embedder è inerte **sempre** —
  le opzioni `memory.*` si leggono, ma nessun percorso chiama più `embed()`.

---

## Il cancello del rilascio

`.githooks/pre-push` ferma ogni push che contiene un bump di `hiris/config.yaml` finché non hai
guardato i componenti: la **CLI del ponte** (pin esatto, quindi le patch non arrivano da sole), le
**azioni CI**, un **major nuovo sopra un tetto** di `requirements.txt` (che congelerebbe una
dipendenza in silenzio) e i **pacchetti installati sotto i pavimenti dichiarati**.

**Va attivato una volta per clone:**
```bash
git config core.hooksPath .githooks
```
Non lo fa nessuno script da sé: un repo che si riconfigura il git al primo comando è una sorpresa.

Per guardare senza pushare: `python scripts/verifica_componenti.py`
Per aggiornare le azioni CI: `… --aggiorna` (la CLI del ponte richiede anche `--cli`).
Per rilasciare comunque: `HIRIS_COMPONENTI_OK=1 git push …` — il valore accettato è **esattamente
`1`**.

Nasce da un fatto: la disciplina del pin era già scritta nel `Dockerfile` e non è stata eseguita
in **nessuna** delle release 3.0.0, 3.1.0 e 3.2.0. Una disciplina scritta non è una disciplina
eseguita. Spec: `docs/design/2026-08-15-verifica-dei-componenti.md`.

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
