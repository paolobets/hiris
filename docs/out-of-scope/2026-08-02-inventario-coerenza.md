# HIRIS — Inventario delle incoerenze

Data: 2026-08-02 · Base: `1.1.0-beta.15` · Esito di due audit sistematici
(esperienza d'uso e testi) più la caccia al codice morto.

Questo documento è l'inventario, non il piano. Serve a decidere cosa fare e in
che ordine, e a non perdere ciò che è stato trovato.

## A. Difetti funzionali, non incoerenze

Sono percorsi che **non fanno ciò che dicono**. Ordine per danno.

**A1 — `save_memory` dichiara un successo che non c'è.** `tools/memory_tools.py:95-98`
Se il calcolo dell'embedding fallisce, il ricordo viene scritto lo stesso e il
modello riceve `saved: True`. Ma la ricerca filtra anche sulla presenza
dell'embedding: quel ricordo **non sarà mai richiamabile**. È esattamente il
difetto chiuso in beta.15 per `save_knowledge` — vivo nel tool gemello, che è
quello che l'utente incontra dicendo «ricordati che...» a un Chatbot. Le note di
rilascio della beta.15 si intitolano «La memoria funziona davvero» e coprono
entrambi.

**A2 — HIRIS accusa il modello di inventarsi uno strumento che gli ha dato lui.**
`tools/dispatcher.py:663, 674`
Quando lo store della conoscenza non è configurato, `recall_knowledge` e
`link_knowledge` cadono nel ramo finale, che risponde: «Tool 'recall_knowledge'
non esiste. Non inventare nomi di tool.» Il modello smette di usarlo per il
resto della conversazione. `recall_memory` e `save_memory` gestiscono lo stesso
caso correttamente (`:566`, `:574`): la correzione è allinearli.

**A3 — «Non ho trovato nulla» al posto di «non ho potuto guardare».** Quattro punti:
`tools/knowledge_tools.py:128-132` (memoria semantica giù → «non ho trovato
nulla»), `tools/calendar_tools.py:58-63` («non hai impegni» quando HA non
risponde), `tools/dispatcher.py:312-319` («la casa è vuota» a cache non
popolata), `llm_router.py:278-282` (stringa vuota trattata come risposta del
modello). È la stessa classe già corretta per la coda della memoria.

**A4 — Il filtro «eseguiti» dei task non trova mai nulla.**
`static/config/tasks-route.js:25-30, 158`
L'etichetta e il filtro usano lo stato `executed`; il motore scrive `done`
(`task_engine.py:422`). Il chip filtra su uno stato che non esiste: risultato
sempre vuoto, contatore sempre zero. E `done`, `skipped`, `expired`, `running`
cadono nel fallback e compaiono in inglese.

**A5 — «Conferma richiesta» copre un solo strumento.** `claude_runner.py:346-352`
Il prompt che impone la conferma nomina solo `call_ha_service`. Restano fuori
`trigger_automation`, `toggle_automation`, `set_input_helper` e
`create_ha_config`, che scrive **subito** su HA. L'utente attiva un interruttore
che promette più di quanto copre.

**A6 — Due strumenti dichiarano una conferma che non esiste.** `mcp/tiers.py:65-73`
`create_task` e `cancel_task` sono descritti come «richiede conferma (gate di
sicurezza)», ma `handlers_execute.py` li dispaccia direttamente. Una rete di
sicurezza dichiarata e assente è peggio di nessuna rete: il modello agisce con
meno cautela.

**A7 — Cancellare la conversazione non chiede conferma.** `static/chat/agents.js:31`
È irreversibile. La card Lovelace, per la stessa identica azione, la chiede
(`hiris-chat-card.js:1222`).

**A8 — La coda del gateway approva comandi senza conferma e tace sugli errori.**
`static/config/gateway-route.js:79-80, 99`
Si approva un comando su casa propria senza alcuna conferma; se la richiesta
fallisce, il `catch` è muto e non c'è stato vuoto.

**A9 — Un errore ogni trenta secondi nella pagina chat.** `static/config/api.js:63-65`
`loadUsage` scrive su un elemento che nella chat non esiste: solleva a ogni
ciclo, inghiottito da un `catch`. Nella chat non si sa da quando contano i numeri.

**A10 — Tre bottoni che non compaiono mai.** `static/index.html:130-138` +
`hiris-chat.css:639, 731, 794, 910`
`#mobile-task-btn`, `#mobile-proposals-btn`, `#mobile-knowledge-btn` sono
nascosti sia nella regola di base sia nella media query. Nessuna condizione li
mostra. Attorno a loro vivono ~15 punti di codice inerte (badge, classe attiva,
listener) e tre blocchi CSS mai applicati.

## B. Ciò che l'interfaccia offre e non ha effetto

**B1 — Il gateway offre «verde» per domini sempre bloccati.**
`static/config/gateway-route.js:18`
Serrature, allarme, sirene e tapparelle si possono marcare «verde (esegui
subito)», ma `security/semaphore.py:141-146` li nega **prima** di leggere il
tier: quella scelta non ha mai effetto. L'editor dei Chatbot invece avvisa
(`chatbot-editor.js:388-393`). Nota: marcandoli rosso l'azione passa dopo
l'approvazione umana — non è un'inversione difettosa ma la regola dichiarata
(la conferma esplicita autorizza quel comando), che però l'interfaccia non spiega.

**B2 — Due opzioni pubbliche senza alcun effetto.** `automatic_policy` e
`chat_policy` in `config.yaml`: da quando esiste la catena dei modelli non
governano più nulla.

## C. Vocabolario e presentazione

**C1 — Stati mostrati grezzi in inglese** in quattro punti: task nella chat
(`chat/tasks.js:25`), suggerimenti (`agentbot-route.js:443`, incluso `recorded`),
severità delle segnalazioni (`dashboard.js:225`, `INFO/WARN/HIGH`), e
«Nessuna proposta **pending**» (`dashboard.js:293`).

**C2 — Quattro parole per «no»**: Rifiuta (proposte, gateway), Scarta (memoria),
Ignora (segnalazioni). E tre per «sì»: Approva, Attiva, «Ho capito».

**C3 — «Task»**: «Task pianificati» / «Task», femminile in chat e maschile nel
config, «Annulla» contro «Cancella».

**C4 — «Chatbot» contro «assistente»**: l'onboarding non ha ricevuto il rename.

**C5 — «Plancia» nei testi, «dashboard» nelle etichette di tipo**, con tre
formulazioni diverse.

**C6 — Ventitré descrizioni di strumenti su trentasette sono in inglese**, mentre
il prompt chiede al modello di rispondere in italiano.

**C7 — Prompt che si contraddicono sulla lingua**: `claude_runner.py:136`
(«nella lingua dell'utente») contro `agent/prompts.py:24` («SEMPRE in italiano»),
entrambi presenti sul percorso via abbonamento.

## D. Le tre superfici non si somigliano

I tre pannelli della chat (task, proposte, memoria) dichiarano lo stesso schema
ma divergono su: guardie sui nodi, gestione dell'errore di caricamento,
distinzione fra vuoto ed errore, interpretazione dell'esito HTTP, feedback
immediato, azzeramento della navigazione. **Il pannello della memoria è il più
corretto dei tre** ed è il modello da portare negli altri due.

Le proposte compaiono in tre superfici con tre insiemi di campi, tre messaggi di
lista vuota, tre comportamenti dopo l'azione, e il ripristino di una plancia
esiste **solo** in chat benché si possa approvare da tutte e tre.

Cinque code della stessa natura (proposte, memoria, task, segnalazioni, gateway)
vivono in posti diversi con contratti diversi; due non hanno conferme, una non
ha né stato vuoto né gestione dell'errore.

I badge del config sono calcolati **una sola volta al caricamento**: approvi
cinque proposte e il badge continua a dirne cinque.

## E. Aree di tocco e accessibilità

La regola dei 44 pixel esiste nella chat e manca nel config (pagina Proposte,
riquadri della dashboard, filtri dei task, tutta la pagina del gateway).
Elementi cliccabili che non sono bottoni: il selettore di chatbot, i suggerimenti
del selettore di entità, le righe espandibili dei log e dei task.

## F. Documentazione

`configuration-guide.md` e la gemella italiana documentano **15 opzioni su 52**
e dichiarano una versione di metà luglio. Le tabelle degli strumenti sono a 26 e
22 su 37. Tre documenti non sono nell'elenco che l'automazione di rilascio
aggiorna. Due opzioni non hanno traduzione, e una di queste è **citata da
un'altra descrizione** come se esistesse.

## G. Cadaveri

Quattordici funzioni senza chiamanti (fra cui una feature — le annotazioni della
knowledge base — con un lettore e **nessuno scrittore**). `permessi.js` (dieci
righe, tutte commento), `drawer.js` e `popover.js` (mai istanziati),
`switchProposalsTab` (manipola identificatori che non esistono più),
`midTruncate`, `formatTokens`, la route `settings`. Il parametro `data_dir` del
dispatcher, assegnato e mai letto. Ottantacinque righe di contabilità token
**identiche** fra i due runner. `_is_finite_number` in quattro copie. Una
migrazione da un formato morto ad aprile, eseguita a ogni avvio.

## Decisioni di prodotto necessarie

Non hanno una risposta oggettivamente giusta:

1. **Un'unica inbox o cinque code?** Oggi cinque code della stessa natura sono
   sparse fra chat e configurazione. O si accorpano, o si dichiara che la chat è
   la superficie d'azione e la configurazione quella d'ispezione — e allora la
   memoria deve avere una vista di configurazione, e segnalazioni e gateway un
   accesso dalla chat.
2. **I tre bottoni per schermi stretti: rimuovere o far vivere?**
3. **Cosa fa «Rifiuta» su una proposta?** Se archivia, la conferma è rumore; se
   elimina, il testo deve dirlo.
4. **Il nome di «task»** e il verbo per annullarla.
5. **I pannelli della chat devono essere indirizzabili?** Oggi il tasto Indietro
   esce dalla chat invece di chiudere il pannello.
6. **Quanto della card Lovelace risalire nella chat?** Rigenera, copia, budget,
   avviso in linea e annulla-azione esistono solo nella card, che è la superficie
   più povera.
7. **Il widget dei consumi nella chat**: collegarlo, ridurlo o toglierlo.
