# HIRIS — Sprint di consolidamento

Data: 2026-08-02 · Stato: design approvato dall'utente

## Perché

Tre filoni consegnati di fila (plance a proposta, visione/salute del sistema,
denylist di lettura) hanno lasciato dietro di sé un debito misurato: venti
rilievi minori registrati nei registri di lavoro, follow-up dichiarati nei
design, e — emerso da una caccia sistematica — una quantità di codice che non
serve più a nessuno.

Prima di aprire la Fase 3 degli agenti si chiude tutto questo. L'ordine è per
danno, non per comodità: prima ciò che **produce risultati sbagliati**, poi ciò
che **inganna chi legge il codice**, infine i cadaveri.

## Lotto 1 — Ciò che sbaglia

### 1.1 `save_knowledge` è rotto end-to-end

Sette scrittori popolano la knowledge base. Sei salvano come **approvato**
(documenti Mayan, riassunti storici, memorie, tracce del Brain, migrazione).
Uno solo salva come **in attesa**: il tool `save_knowledge`
(`tools/knowledge_tools.py:71`), che è quello che l'LLM usa quando l'utente
chiede di ricordare qualcosa.

La ricerca — l'unico modo per richiamare un'informazione — filtra
`status='approved'` (`brain/knowledge_store.py:217`). E gli endpoint di
approvazione (`/api/knowledge/pending`, `.../approve`, `.../reject`, registrati
in `server.py`) **non hanno alcuna interfaccia**.

Quindi: l'utente dice «ricordati che la caldaia va revisionata a ottobre», il
Chatbot risponde «salvato», e quel dato **non sarà mai richiamabile**. Nessun
errore, nessun log: solo un ricordo che non torna. È lo stesso schema del bug
delle proposte di luglio — qualcosa che *dichiara* di aver funzionato e non ha
funzionato.

**Rimedio (scelta utente):** una coda di approvazione nella pagina chat,
accanto a Proposte e Task, dove le altre inbox già vivono. Gli endpoint
esistono: manca la superficie. Chi approva vede cosa HIRIS ha imparato e
decide.

### 1.2 Proposte autonome con una configurazione che non è un'automazione

Due percorsi creano proposte di tipo `ha_automation` con un contenuto che
automazione non è: la Sentinella (`server.py:1800`,
`config={"suggested_action": ...}`) e la coverage-review del Brain
(`server.py:2232`, `config=c`, il suggerimento grezzo).

All'approvazione, `ha_client.create_automation` accetta **qualunque dizionario
non vuoto**, gli conia un identificativo e lo scrive in Home Assistant.
L'utente approva e ottiene un'automazione senza trigger né azione — o un
errore, a seconda di quanto è permissiva l'API.

**Rimedio:** i due siti devono produrre una proposta il cui tipo corrisponde a
ciò che contengono davvero, e `create_automation` deve rifiutare una
configurazione che non ha la forma minima di un'automazione. La difesa va
messa in entrambi i posti: chi propone e chi applica.

### 1.3 I modelli preconfigurati istruiscono verso uno strumento inesistente

`static/config/templates.js`, righe 12/18/24/30/36: tutti e cinque i modelli
(Energia, Sicurezza, Presenza, Clima, Irrigazione) dicono al modello di
chiamare `search_entities(...)` — **11 occorrenze**, strumento rimosso da
tempo. Ogni bot creato da un preset spreca un tentativo su qualcosa che non
esiste.

Il catalogo degli strumenti nello stesso file è già stato allineato e protetto
da un test; i **testi** no.

**Rimedio:** sostituire con gli strumenti reali, ed estendere il test perché
verifichi anche i testi — non solo il catalogo — così il buco si chiude per
sempre.

### 1.4 `parse_decision` esiste in due versioni con default opposti

`agent/runner.py:77` e `watcher/reasoner.py:64` interpretano la stessa risposta
dell'LLM. In caso di dubbio la prima classifica «falso positivo», la seconda
«anomalia»: due decisioni opposte sullo stesso input, con troncamenti diversi.

**Rimedio:** una sola implementazione, con il comportamento in caso di dubbio
scelto esplicitamente e documentato. Se le due semantiche servono davvero
entrambe, deve essere un parametro dichiarato, non una divergenza silenziosa.

### 1.5 «Entità non disponibile» calcolata due volte con criteri diversi

`proxy/health_monitor.py:186-206` la mantiene in tempo reale (soglia
istantanea); `brain/health_checks.py:48` la ricalcola sullo snapshot con soglia
a due giorni. L'utente legge due verità diverse a seconda di dove guarda — lo
stesso identico difetto delle batterie appena chiuso.

**Rimedio:** una sola nozione. Nello stesso giro va **decisa** la soglia
batteria residua (`health_checks.py:71` a 15 contro `watcher/detectors.py:49`
dalla policy): unificarla o dichiarare per iscritto perché diverge.

## Lotto 2 — Ciò che inganna

### 2.1 Test che non testano

Dodici test chiamano una funzione e verificano solo che non sollevi, senza
alcuna asserzione di effetto (`test_chat_store.py:65`,
`test_event_agentbots.py:270`, `test_mqtt_publisher.py` ×3,
`test_lovelace_registration.py` ×3, `test_release_script.py` ×4). Un test così
resta verde qualunque cosa la funzione faccia.

Cinque file in `tests/static/` (`test_drawer.html` e simili) sembrano test ma
**non vengono mai eseguiti**: non c'è né un runner di browser né un passo di
CI che li raccolga.

**Rimedio:** dare a ciascuno un'asserzione di effetto, o eliminarlo. Per i file
HTML: dichiararli per ciò che sono (strumenti manuali) o rimuoverli.

### 2.2 Le guide utente descrivono un prodotto che non esiste più

`configuration-guide.md` e la gemella italiana documentano **15 opzioni su 52**
e dichiarano una versione di metà luglio. Le tabelle degli strumenti sono a
26 su 37 (`come-funziona.md`, `how-it-works.md`) e a 22 su 37
(`architettura.md`, `architecture.md`). Alcune intestazioni mentono anche sulla
data. Tre documenti non sono nell'elenco che l'automazione di rilascio
aggiorna, e lo strumento di controllo lo segnala già da sé.

**Rimedio:** riallineare tabelle e opzioni, correggere le intestazioni, e
aggiungere i documenti mancanti all'elenco versionato — così il disallineamento
non ricomincia da capo alla prossima release.

## Lotto 3 — I cadaveri

### 3.1 Codice senza chiamanti

Quattordici fra funzioni e metodi non sono chiamati da nessuna parte in
`hiris/app/`. Fra questi, un caso che vale la pena notare: le annotazioni della
knowledge base hanno un **lettore** (`semantic_context_map.py`) ma **nessuno
scrittore** — quindi non possono mai restituire nulla.

Nel frontend: `permessi.js` è un file di dieci righe **tutte commento**,
caricato dalla pagina di configurazione; `switchProposalsTab`
(`static/config/proposals.js:119`) non è chiamata da nessuno e manipola
identificatori che non esistono più — se qualcuno la chiamasse, fallirebbe.

`.smoke-test/` contiene fixture con campi eliminati da tempo e non è eseguito
da nulla.

### 3.2 Parametri e opzioni inerti

`ToolDispatcher` accetta `data_dir` e lo assegna senza mai leggerlo; lo stesso
per `self._embedder`, che duplica un attributo già presente. Tre chiavi
`app[...]` sono scritte e mai rilette.

Due **opzioni pubbliche** — `automatic_policy` e `chat_policy` — non hanno più
alcun effetto da quando esiste la catena dei modelli: l'utente le configura e
non succede nulla. Vanno rimosse dalla configurazione, dallo script di avvio e
dalle traduzioni. Nello stesso giro vanno aggiunte le traduzioni mancanti per
due opzioni esistenti, che oggi l'utente vede come chiavi grezze.

### 3.3 Duplicazioni

Ottantacinque righe di contabilità di token e costi sono copiate **identiche**
fra i due runner (`claude_runner.py:515-594` e
`backends/openai_compat_runner.py:258-337`): ogni correzione va applicata due
volte o diverge. È il duplicato più grande del repo.

Minori: `_is_finite_number` in quattro copie, `_nel_perimetro` in due (più una
variante nel dispatcher), e alcune coppie di helper temporali.

### 3.4 Una migrazione da un formato morto

`chat_store.migrate_from_json` importa un formato abbandonato ad **aprile** e
gira a ogni avvio.

**Da non toccare:** le tre migrazioni di fine luglio (`agents.json`,
`sentinel_lenses.json`, memoria) sono recenti e vanno tenute; si rimuoveranno
tutte insieme più avanti, in un «taglio del ponte» annunciato nelle note di
rilascio.

## Criterio trasversale

Ogni rimozione deve essere **verificata**, non dedotta: qualcosa può essere
chiamato per nome, registrato in una tabella, o raggiunto dinamicamente. Dove
il dubbio resta, si tiene e si documenta.

Ogni intervento del Lotto 1 richiede un test che fallisca prima e passi dopo.
Il Lotto 3 richiede che la suite resti verde: è la sua unica prova.

## Fuori scope

- La Fase 3 degli agenti.
- Le tre migrazioni recenti.
- La promozione a opzione delle manopole oggi leggibili solo da variabile
  d'ambiente: vanno decise, non fatte di corsa.
