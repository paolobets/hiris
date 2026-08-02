# HIRIS — Coerenza: secondo e terzo lotto

Data: 2026-08-02 · Stato: design approvato dall'utente
Inventario di riferimento: `docs/design/2026-08-02-inventario-coerenza.md`

## Perché

Il primo lotto ha chiuso cinque percorsi che producevano risultati sbagliati.
Tre audit sistematici (esperienza d'uso, testi, codice morto) hanno poi mostrato
che quel difetto — **dire una cosa e farne un'altra** — non era finito: ne
restano dieci, alcuni gemelli di quelli appena corretti. Attorno c'è il debito
vero: vocabolario incoerente, superfici che non si somigliano, documentazione
ferma a luglio, cadaveri.

Si chiude tutto prima della Fase 3.

## Decisioni prese con l'utente

1. **La chat è la superficie dove si decide.** Tutte e cinque le code che
   chiedono una decisione — proposte, memoria, task, segnalazioni del Brain,
   comandi del gateway — devono essere raggiungibili dalla chat, con lo stesso
   aspetto e le stesse regole. La configurazione resta il posto dove si ispeziona
   e si filtra.
2. **Le code sono raggiungibili in un tocco su telefono.** I tre bottoni oggi
   invisibili vanno fatti vivere, in una barra propria — non nell'intestazione,
   che era stata svuotata di proposito.

## Lotto A — I difetti funzionali

Ordine per danno. Ognuno richiede un test che fallisca prima e passi dopo.

### A1 · `save_memory` dichiara un successo che non c'è
`tools/memory_tools.py:95-98`. Se l'embedding fallisce il ricordo viene scritto
comunque e il modello riceve `saved: True`, ma la ricerca filtra sulla presenza
dell'embedding: quel ricordo non sarà **mai** richiamabile. È il difetto chiuso
in beta.15 per `save_knowledge`, vivo nel tool gemello — quello che l'utente
incontra dicendo «ricordati che...». Va allineato: fallire apertamente invece di
riuscire a vuoto. Nello stesso giro va sanato `handle_manual_add`
(`api/handlers_knowledge.py`), che ha la stessa forma su un percorso solo-API.

### A2 · HIRIS accusa il modello di inventarsi uno strumento che gli ha dato lui
`tools/dispatcher.py:663, 674`. Senza store, `recall_knowledge` e
`link_knowledge` cadono nel ramo finale: «Tool 'X' non esiste. Non inventare nomi
di tool.» Il modello smette di usarlo per tutta la conversazione. I gemelli
`recall_memory`/`save_memory` (`:566`, `:574`) gestiscono correttamente lo stesso
caso: allinearli.

### A3 · «Non ho trovato nulla» al posto di «non ho potuto guardare»
Quattro punti: `tools/knowledge_tools.py:128-132`, `tools/calendar_tools.py:58-63`
(anche i singoli calendari che falliscono sono saltati in silenzio),
`tools/dispatcher.py:312-319`, `llm_router.py:278-282`. Un elenco vuoto e un
guasto devono essere distinguibili — dal modello e quindi dall'utente.

### A4 · Il filtro «eseguiti» dei task non trova mai nulla
`static/config/tasks-route.js:25-30, 158`: interroga lo stato `executed`, il
motore scrive `done`. Contatore sempre zero. Da correggere insieme a C1, perché
è lo stesso dizionario.

### A5 · «Conferma richiesta» copre un solo strumento su cinque
`claude_runner.py:346-352` nomina solo `call_ha_service`. Restano fuori
`trigger_automation`, `toggle_automation`, `set_input_helper` e
`create_ha_config`, che scrive subito su HA. O si estende la copertura, o
l'opzione dichiara cosa copre — la prima è ciò che l'utente si aspetta.

### A6 · Due strumenti dichiarano un gate di conferma che non esiste
`mcp/tiers.py:65-73`: `create_task` e `cancel_task` sono descritti come
«richiede conferma», ma il gateway li dispaccia direttamente. O si costruisce il
gate, o si toglie la promessa. **Una rete dichiarata e assente è peggio di
nessuna rete**, perché il modello agisce con meno cautela.

### A7 · Cancellare la conversazione non chiede conferma
`static/chat/agents.js:31`, irreversibile. La card Lovelace la chiede per la
stessa azione: allineare alla card.

### A8 · La coda del gateway approva senza conferma e tace sugli errori
`static/config/gateway-route.js:79-80, 99`: si approva un comando su casa propria
senza conferma; il `catch` è muto; non esiste stato vuoto.

### A9 · Un errore ogni trenta secondi nella chat
`static/config/api.js:63-65`: `loadUsage` scrive su un elemento assente nella
chat. Da sanare insieme alla decisione sul widget dei consumi (vedi D4).

### A10 · Il gateway offre «verde» dove non avrà mai effetto
`static/config/gateway-route.js:18`: serrature, allarme, sirene e tapparelle sono
negati **prima** della lettura del tier. L'editor dei Chatbot già avvisa: portare
lo stesso avviso qui. Va spiegato anche che l'approvazione esplicita scavalca il
divieto — è la regola dichiarata, ma l'interfaccia non la racconta.

## Lotto B — Ciò che HIRIS dice

### B1 · Un solo dizionario di etichette
Stati e tipi mostrati grezzi in inglese in quattro punti (task nella chat,
suggerimenti inclusi `recorded`, severità delle segnalazioni, «Nessuna proposta
pending»). Serve un dizionario condiviso fra le superfici, che copra anche i tipi
di trigger — dove la vista di configurazione ne elenca tre che **non esistono**
e ne manca quattro che esistono.

### B2 · Un verbo per ogni azione
Oggi quattro parole per «no» (Rifiuta, Scarta, Ignora) e tre per «sì» (Approva,
Attiva, «Ho capito»). Vanno scelte e applicate ovunque. «Ho capito» su una
segnalazione non dice cosa succede: va sostituito con un'azione vera.

### B3 · Le descrizioni degli strumenti in italiano
Ventitré su trentasette sono in inglese mentre il prompt chiede al modello di
rispondere in italiano. Nello stesso giro vanno corrette le promesse false
trovate: `list_tasks` che dichiara 24 ore e ne restituisce 168, `at_time` che
dice «oggi» ed è «oggi o domani», `http_request` che promette i dispositivi
locali che la deny-list blocca, `link_knowledge` che dice «(proposta)» e scrive
subito, i limiti non dichiarati e i valori silenziosamente clampati.

### B4 · I prompt non si contraddicono
`claude_runner.py:136` dice «rispondi nella lingua dell'utente»,
`agent/prompts.py:24` «SEMPRE in italiano», e sul percorso via abbonamento
arrivano insieme. Inoltre il prompt di base dichiara «accesso completo alla casa»
**prima** del filtro degli strumenti: un Chatbot ristretto promette all'utente
azioni che non può compiere.

### B5 · Un'unica descrizione per strumento
Lo stesso strumento è descritto diversamente nei tre cataloghi, con divergenze
sostanziali (uno dichiara capacità che l'altro tace). Vanno allineate le
descrizioni, non le riformulazioni.

## Lotto C — Le superfici

### C1 · Le cinque code, stesse regole
Il pannello della memoria è il più corretto dei tre nella chat: classe distinta
per l'errore, messaggio italiano per stato HTTP, badge azzerato quando non si è
potuto leggere, ricarica dopo un 404. Va portato negli altri, e le regole comuni
vanno estese a tutte e cinque: conferma proporzionata al danno, stato vuoto,
stato di caricamento, badge che si aggiorna anche dopo un'azione.

### C2 · Le code raggiungibili dalla chat
Segnalazioni del Brain e coda del gateway oggi vivono solo nella configurazione:
vanno rese raggiungibili dalla chat, secondo la decisione presa.

### C3 · Una sola card proposta
Tre superfici mostrano insiemi di campi diversi. Va usato un componente solo, con
l'insieme della chat (descrizione intera, motivo solo se c'è, data), e va tolto
il troncamento muto a due righe della pagina di configurazione. Il ripristino di
una plancia deve essere raggiungibile da dove si approva.

### C4 · Le code su telefono
I tre bottoni vanno fatti vivere in una barra propria, e le due code nuove
aggiunte. Oggi il pannello aperto su schermo largo non ha né titolo né uscita:
va mostrato sempre.

### C5 · Aree di tocco nella configurazione
La regola dei 44 pixel esiste nella chat e manca nel config: va copiata, non
inventata. Elementi cliccabili che non sono bottoni vanno resi tali.

### C6 · Badge della configurazione aggiornati
Oggi sono calcolati una sola volta al caricamento.

## Lotto D — Cadaveri e documentazione

### D1 · Codice senza chiamanti
Quattordici funzioni, `permessi.js`, `drawer.js`, `popover.js`,
`switchProposalsTab`, `midTruncate`, `formatTokens`, la route `settings`, il
parametro `data_dir` del dispatcher, `.smoke-test/`. Per le annotazioni della
knowledge base — lettore senza scrittore — va deciso se collegarle o rimuoverle.

### D2 · Duplicazioni
Ottantacinque righe di contabilità token identiche fra i due runner (ogni
correzione va applicata due volte o diverge). `_is_finite_number` in quattro
copie, `_nel_perimetro` in due più una variante.

### D3 · Opzioni inerti e traduzioni mancanti
`automatic_policy` e `chat_policy` non hanno più effetto: vanno rimosse da
configurazione, script di avvio e traduzioni. Due opzioni non hanno traduzione, e
una è citata da un'altra descrizione come se esistesse. Alcune descrizioni
raccontano un comportamento diverso da quello reale.

### D4 · Test che non testano
Dodici test verificano solo che una chiamata non sollevi. Cinque file in
`tests/static/` sembrano test e non vengono mai eseguiti.

### D5 · Documentazione
`configuration-guide.md` e la gemella documentano 15 opzioni su 52; le tabelle
degli strumenti sono a 26 e 22 su 37; tre documenti non sono nell'elenco che
l'automazione di rilascio aggiorna.

### D6 · Una migrazione da un formato morto ad aprile
`chat_store.migrate_from_json`, eseguita a ogni avvio. **Da non toccare** invece
le tre migrazioni di fine luglio: si rimuoveranno insieme più avanti, in un
taglio annunciato.

## Criterio trasversale

Ogni rimozione va **verificata**, non dedotta: qualcosa può essere chiamato per
nome o raggiunto dinamicamente. Dove il dubbio resta, si tiene e si documenta.
Il Lotto A richiede test che falliscano prima; il Lotto D richiede che la suite
resti verde — è la sua unica prova.

## Decisioni ancora aperte

Da prendere quando il lavoro le incontra, non ora:
- cosa fa «Rifiuta» su una proposta (se archivia, la conferma è rumore);
- il nome di «task» e il verbo per annullarla;
- se i pannelli della chat debbano essere indirizzabili (oggi il tasto Indietro
  esce dalla chat invece di chiudere il pannello);
- quanto della card Lovelace risalire nella chat (rigenera, copia, budget,
  avviso in linea);
- il widget dei consumi nella chat: collegarlo, ridurlo o toglierlo.

## Fuori scope

La Fase 3 degli agenti. Le tre migrazioni recenti.
