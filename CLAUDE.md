# HIRIS — contesto per Claude Code

## ⚠️ Leggi prima questo

Il **Refactor 2.0 è concluso**: non è più un cantiere, è il prodotto. Resta in piedi la sua regola
più dura — una parte del codice esistente è **deliberatamente condannata** (tabella «Cosa è
condannato dal refactor», più sotto: se stai per estenderne una voce, **fermati e chiedi**).
Prima di scrivere qualunque riga:

| Domanda | Documento |
|---|---|
| Cosa **deve** fare HIRIS | `docs/design/2026-08-04-scope-hiris.md` — **il contratto** |
| Cosa **c'è dentro**, e cosa ne resta | `docs/design/2026-08-05-mappa-funzionalita.md` — **l'ordine di demolizione** |
| Come si conosce la casa | `docs/design/2026-08-05-la-conoscenza-di-hiris.md` |
| Cosa **aspetta** uno sprint | `docs/BACKLOG.md` — **il registro degli argomenti** |

**Quando il proprietario dice «inseriamo per il prossimo sprint», la voce entra in
`docs/BACKLOG.md` subito**, prima di continuare il discorso — non in un appunto, non in una
risposta in chat, non nella memoria di una sessione. Un argomento annotato altrove è un argomento
perso: è già successo, e la lista andata persa il 04/09/2026 è la ragione per cui quel registro
esiste. Uno sprint nuovo si apre **scegliendo dal backlog**, non ripartendo da zero.

**C'è un ramo solo: `master`** — è quello che l'add-on legge e da cui escono le release. Il ramo
`2.0` è stato cancellato il 4 settembre 2026, quando la sua punta e quella di `master` erano lo
stesso commit: un ramo di lavoro che coincide con quello pubblicato non separa più niente, è
un'etichetta che mente. Nessuno degli attrezzi dipendeva da quella separazione —
`scripts/release.py` pusha `HEAD:master` da qualunque worktree, e il cancello pre-push riconosce il
rilascio dal **contenuto** di `hiris/config.yaml`, non dal nome del ramo.

Tutto ciò che sta in `docs/out-of-scope/` (compreso `docs/out-of-scope/pre-2.0/`, l'ex
`docs/archive/`) e in `docs/superpowers/_archivio-pre-refactor-2.0/` è **storia,
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
> `hierarchy()` la faceva già, e meglio · `PRICING.get(model, PRICING["_default"])` scritto in linea
> in due runner con la funzione che lo fa ferma e inutilizzata · la regola di «notevole» in
> `buildDisplayChain` e `reconcile_chain`, che è stata **il meccanismo** con cui la pagina Modelli
> poteva essere vera riga per riga e falsa nel complesso.

**3. Consistenza — la stessa cosa ha la stessa forma da tutte le porte.**
Un'entità vista da `view`, da `search` o dal nucleo è la stessa entità, con gli stessi campi e gli
stessi nomi. Un campo che compare da una porta e non dall'altra è un difetto anche quando nessuna
delle due è sbagliata.
> *Pagata:* `nome_dedotto` usciva solo da `_view_entity` e non da area e dispositivo (rilievo I1);
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
(agosto 2026) la **chat** esegue: chiede a `hiris/app/action/actuator.py`, che verifica la chiamata
contro l'installazione, la esegue e rilegge lo stato. Non è ③ — non c'è nessun agente, nessuna
autonomia, nessun perimetro da approvare — è la chat che fa una cosa sola quando gliela chiedi.
**Un canale, una porta.** Per ogni canale di scrittura verso Home Assistant esiste **un unico
modulo** che lo attraversa. Oggi sono due: i **servizi** (`action/actuator.py`, dalla fetta
«comandare») e la **configurazione** (`azione/construction/workshop.py`, dalla fetta «costruire»).
Sono canali diversi in tutto — rotta, verifica, «dopo» — e condividono ciò che conta: la cronaca,
l'`origine` e la forma del rifiuto motivato, che vivono **una volta sola** e hanno la **stessa
forma da entrambi**. Un terzo punto che scriva su Home Assistant fuori da queste due porte è un
difetto, non un'ottimizzazione. Spec: `docs/design/2026-08-22-costruire-in-home-assistant.md` §2.1.

**Non si scrive mai `automations.yaml`, `scripts.yaml` o `scenes.yaml` in proprio.** Scrive Home
Assistant, attraverso l'API di configurazione, trovando la voce per `id` e sostituendola. È questa
proprietà che rende impossibile ripetere il danno misurato sulla casa del proprietario: la voce
accodata quattro volte, resa invisibile dalle ancore YAML di PyYAML.

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

`PRODUCT.md` è **interamente storico** — lo dichiara da sé, nel blocco del 10 agosto in cima al
file: non descrive un prodotto in tre sezioni superate, descrive un prodotto che non esiste più
punto e basta. Anche i suoi capitoli su identità visiva e accessibilità vanno riletti contro il
prodotto vero, non presi per buoni: nominano superfici (sandbox, editor Agentbot, telemetria
per-entità) che non ci sono più.

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
    ├── server.py         # 3.570 righe: registrazione rotte E gran parte del wiring
    ├── claude_runner.py  # loop agentico Claude + orchestrazione tool
    ├── llm_router.py · chat_store.py · chat_settings.py · model_activation.py
    ├── config.py · storage.py · env_util.py · version.py
    ├── api/        (16 file) handlers_* — la superficie HTTP
    ├── casa/       (8)       anagrafe, archivio, comportamento, nucleo, domande, strumenti
    ├── azione/     (5)       porta.py — i SERVIZI, l'unica porta sul canale — verifica.py,
    │                         registro.py, cronaca.py; costruzione/ (4) — officina.py, l'unica
    │                         porta sul canale della CONFIGURAZIONE — composer.py, mestiere.py,
    │                         versioni.py (fetta «costruire»)
    ├── backends/   (7)       runner OpenAI-compat, embeddings, pricing
    ├── memoria/    (4)       archivio, interpretazione, resolver
    ├── proxy/      (4)       ha_client.py (il VERO client HA: REST+WS), entity_cache, _sanitize
    ├── agent/      (3)       runner.py (il ponte push) + prompts.py
    ├── keeper/     (5)       promise, store, sweeper, exchange — le promesse dell'utente
    ├── reasoning/  (2)
    └── static/     index.html · config.html · chat/*.js · config/*.js
```

`server.py` era dichiarato «~1.900 righe» — già falso prima della fetta «l'osservatore» (2026-08-26),
di più dopo. Misurato con `wc -l hiris/app/server.py` il 26 agosto: **3.570**. Verifica di nuovo
prima di fidartene: è un numero che invecchia da solo, non un fatto che questo file possa custodire.

**Non esistono più** (li citano vecchi documenti e i commenti storici del codice):
`app/routes.py`, `app/ha_client.py`, `app/agent_engine.py`, `api/handlers_agents.py`,
e — dopo le tre fette di demolizione del 2.0 — `app/chatbot_engine.py`, `app/task_engine.py`,
`app/mqtt_publisher.py`, e le cartelle `tools/`, `watcher/`, `security/`, `mcp/`.
Dalla fetta «esce il documentale» (2.1.0) non esistono più nemmeno le cartelle `app/brain/` e
`app/history/`, né `api/handlers_knowledge.py` e `api/handlers_history_policy.py`: l'integrazione
documentale (Mayan), l'archivio di conoscenza (`knowledge.db`), la cattura dello storico
(`history.db`) e la pseudonimizzazione (`privacy.py`, `vault.db`) sono uscite insieme — nessuna
aveva più un consumatore vivo. La conoscenza vive in `home_space/` (l'anagrafe, il nucleo) e in
`memory/` (ciò che le persone hanno detto).
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
python -m pytest -q          # 2.413 test + 1 skip
npm test                     # 242 test frontend: node --test + jsdom
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

### Su Home Assistant non si ipotizza mai: prima la documentazione, poi le API vere

**Regola non negoziabile, dal proprietario il 26 agosto 2026.**

Prima di scrivere, correggere o *giudicare* qualunque cosa che riguardi un'integrazione con Home
Assistant o una lettura da Home Assistant — la forma di una risposta, i valori ammessi di un campo,
gli stati di un dominio, cosa un'entita' dichiara — l'ordine e' questo, e non ammette scorciatoie:

1. **Non si ipotizza.** Nemmeno «quasi certamente», nemmeno «di solito e' cosi'». Un'ipotesi su un
   sistema esterno scritta in un commento diventa un fatto per chi legge dopo.
2. **Si interroga la documentazione ufficiale** — `developers.home-assistant.io`, o direttamente il
   sorgente di Home Assistant / del Supervisor quando la documentazione tace.
3. **Poi si interroga Home Assistant vero**, perche' **per noi e' fattibile**: la casa e' raggiungibile,
   le API REST e WebSocket sono aperte, i token stanno su disco fuori dai repo
   (`~/.ha-token` per HA, `~/.hiris-debug-token` per l'add-on). Vedi «Come si entra» nelle note di
   debug live.
4. **Si scrive nel codice cosa e' stato misurato e quando.** «Misurato il 26/08/2026» accanto a un
   valore vale piu' di qualunque ragionamento.

**Perche' e' una regola e non un consiglio.** In una sola fetta questa mancanza e' costata:
- una funzione **completamente inerte in produzione** — chiedeva un tipo di legame col nome italiano
  mentre HA accetta solo quello inglese, e la richiesta veniva rifiutata **prima di toccare la rete**;
- un mandato che dichiarava «il container e' probabilmente in UTC, quindi le nostre frasi sull'orario
  sono false» — smentito leggendo il sorgente del Supervisor, che imposta **sempre** `TZ`;
- l'aggregazione che etichettava **l'energia prodotta dall'impianto solare come «consumo»**, perche'
  Home Assistant usa `device_class: energy` per la produzione **e** per il prelievo, e la distinzione
  vera vive nella configurazione della **dashboard Energia** (`energy/get_prefs`) — una fonte che
  nessuno aveva pensato di interrogare.

Il corollario: **quando HA ha una fonte dichiarativa, quella e' la risposta.** Aree, dispositivi,
legami, classi, e la dashboard Energia sono cose che HA **sa gia'**: indovinarle dai nomi delle
entita' funziona su un impianto e si rompe sul successivo.

### Cosa rende buono un test (affinamento del 26 agosto)

Il difetto n.1 di questo progetto e' «i test che non possono fallire», e la disciplina che lo
contrasta e' **prima il test rosso, poi il codice**. Ma la regola nasconde la sua stessa ragione, e
serve dirla per intero perche' altrimenti si applica dove non serve e si salta dove serve:

> **Il valore di un test non e' il rosso storico: e' il suo potere discriminante.** L'evidenza che
> serve e' che **esista uno stato difettoso plausibile del programma sotto cui quel test fallisce, e
> che quello stato sia stato prodotto e osservato.**

Il rosso del TDD e' solo **il modo piu' comodo** di ottenere quell'evidenza quando il difetto c'e'
gia'. Quando il codice e' gia' giusto e manca soltanto la sorveglianza, la **mutazione eseguita** e'
la stessa evidenza fabbricata a comando — e a volte e' piu' forte del rosso naturale, perche' la
mutazione si sceglie: si rompe **il peggioramento semantico esatto** invece di un guasto incidentale.

Un test nato verde vale meno **solo se il rosso non e' mai stato visto**. Le due condizioni che
rendono la moneta buona, e che vanno entrambe verificate:

1. il rosso arriva **per la ragione giusta** — si legge il messaggio d'errore, non solo il colore;
2. il ripristino e' **verificato** (`git status`), non assunto.

**Corollario, imparato quattro volte in una notte: le mutazioni si ESEGUONO, non si deducono.** Una
mutazione dichiarata e mai eseguita puo' essere **inerte** (un'altra difesa la scherma), o **rossa
per la ragione sbagliata** (un errore di sintassi introdotto dall'estrazione invece del difetto
vero). In entrambi i casi la frase «questa mutazione arrossisce» e' una prova che non prova.

**E un numero non misurato non si scrive** — ne' in un test, ne' in un commento, ne' in un rapporto,
ne' in un registro di lavoro. Un numero scritto in un registro viene ricopiato in un mandato, e li'
diventa un fatto: e' successo, ed era falso.

### Come si scrive il codice

**La lingua: il dominio in italiano, il confine nella lingua del sistema esterno.**

I concetti nostri sono in italiano e restano tali — «pavimento», «gamba», «comprimari», «grezzo»,
«promessa», «notevole». Non sono traduzioni di concetti inglesi: *sono* i concetti, nati in italiano.
Rinominarli non li renderebbe più chiari.

Ma **qualunque valore che viaggia verso un sistema esterno porta il nome vero di quel sistema, mai
tradotto**: Home Assistant, SQL, HTTP, le librerie. `"entity"`, non `"entita"`. `device_class`, non
`classe_dispositivo`.

> **La riga operativa: una stringa letterale italiana non attraversa mai un confine.** Se la vedi
> dentro una chiamata verso l'esterno, è un difetto — non uno stile.

E **la traduzione fra i due mondi vive in un posto solo per confine**, con i suoi test. Una seconda
copia della tabella di traduzione è un doppione ai sensi della fondamenta 2.

*Perché è una regola e non un consiglio:* il 26 agosto la funzione che costruisce i comprimari è
stata scritta chiedendo a Home Assistant un legame di tipo `"entita"`. HA conosce solo `"entity"`, e
**rifiutava la richiesta prima di toccare la rete**. Stessa riga, altri due errori identici: leggeva
la risposta in una busta italiana che il client non produce, e filtrava chiavi italiane su chiavi
inglesi. Risultato: la funzione era **completamente inerte in produzione** e il lavoro notturno
«riusciva» loggando oggetti costruiti che uscivano tutti vuoti. Tre errori, un errore solo: una
parola italiana mandata dove serviva la parola del sistema esterno.

**Le best practice sono un cancello, non un'aspirazione.**

«Seguire le buone pratiche» senza uno strumento che le verifichi non è una regola: è un auspicio.
Quindi valgono solo quelle **controllate automaticamente**, e ciò che non è controllato non si
pretende.

Lo stato al 26 agosto: **il progetto non ha nessun linter** — né `ruff`, né `flake8`, né `black`, né
`mypy` — e niente di tutto ciò gira nel CI. Va colmato, e il debito è dichiarato qui invece che
sottinteso.

Quando entrerà, entra **così**: configurazione in `pyproject.toml`, esecuzione nel CI accanto alla
suite, e appartenenza al cancello del rilascio come la suite verde. Un linter che si può ignorare non
serve a niente.

### Il debito dichiarato: la rinomina in inglese

**Deciso il 26 agosto dal proprietario, da fare a sviluppo fermo, mai durante una fetta.**

Gli identificatori — funzioni, metodi, parametri — vanno portati in inglese, per interoperabilità e
per allineamento alle convenzioni. Il vocabolario **di dominio** resta discutibile caso per caso: una
`gamba` tradotta in `leg` perde significato, un `aggrega_giorno` tradotto in `aggregate_day` non perde
niente.

Due condizioni, perché una rinomina di massa è l'operazione che rompe le cose in silenzio:

1. **Solo con la suite verde e il linter già in piedi**, mai insieme a un cambio di comportamento.
2. **Un commit di sola rinomina**, verificabile: se il diff contiene una riga di logica, non è una
   rinomina.

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
