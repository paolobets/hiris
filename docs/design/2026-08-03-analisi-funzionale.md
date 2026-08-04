# HIRIS — Analisi funzionale

**Oggetto:** comportamento reale del codice di HIRIS sul branch `feat/coerenza`, HEAD `feb6e1e`.
**Data:** 3 agosto 2026.
**Metodo:** lettura del codice, non esecuzione. Ogni affermazione tecnica porta il riferimento
`file:riga`. Dove il codice e i suoi commenti divergono, la divergenza e' registrata come reperto e
non risolta a favore del commento. Dove due letture indipendenti dello stesso codice non
coincidono, sono riportate entrambe.

**Indice**

1. Che cos'e' HIRIS
2. Le aree di dominio
3. Piattaforma, sicurezza e integrazione
4. Le superfici
5. I sei flussi end-to-end
6. La superficie HTTP, endpoint per endpoint — 64 rotte piu' il mount statico
7. Il catalogo degli strumenti esposti al modello — 37 definizioni
8. Il ciclo di vita del processo — migrazioni, avvio, job periodici, spegnimento
9. Dove il sistema dice una cosa e ne fa un'altra — 181 voci sulle 201 del registro
10. Codice sospetto di essere inerte — 92 voci sulle 104 del registro
11. Cosa non siamo riusciti a stabilire — 111 reperti

Le sezioni 6, 7 e 8 sono censimenti: elencano per intero una superficie, senza commentarla. Sono
messe qui, prima dei reperti, perche' la revisione tecnica e quella di sicurezza lavorano su quegli
elenchi.

---

# 1. Che cos'e' HIRIS

HIRIS e' un add-on di Home Assistant che mette un modello linguistico dentro casa e gli da' le
chiavi. La promessa, letta dalle sue superfici, e' semplice da enunciare: *parli alla tua casa, e
la casa ti risponde e ti obbedisce; e quando cio' che le chiedi e' rischioso, si ferma e ti chiede
il permesso*.

Quella promessa si articola in cinque cose distinte.

**Una conversazione.** Si scrive a un Chatbot — una persona configurabile con un proprio prompt,
un proprio modello, un proprio perimetro — dalla pagina `/chat` dell'add-on o da una card Lovelace
dentro una dashboard di Home Assistant. Entrambe scrivono sullo stesso endpoint
(`hiris/app/server.py:2801` -> `hiris/app/api/handlers_chat.py:140`).

**Un assistente che agisce.** Il modello dispone di 37 strumenti (`hiris/app/claude_runner.py:181-219`)
e di un unico esecutore (`hiris/app/tools/dispatcher.py:235-786`): legge lo stato della casa,
accende e spegne, scrive automazioni, manda notifiche, programma azioni differite, ricorda.

**Un cervello che si muove da solo.** Una Sentinella osserva i cambi di stato e apre segnalazioni;
una scansione di salute ogni mezz'ora cerca batterie scariche, add-on fermi, automazioni rotte; una
revisione olistica quotidiana, spenta di fabbrica (`hiris/app/watcher/policy.py:31`), propone
automazioni e amplia da sola la copertura dei rilevatori.

**Regole proprie.** Gli Agentbot permettono di scrivere le proprie regole — «se questo, allora
quello» — sopra la stessa infrastruttura, con un ragionamento facoltativo del modello e, dalla
versione 1.1, una modalita' «obiettivo» in cui si scrive un traguardo a parole e un perimetro
dentro cui il modello puo' muoversi.

**Una memoria.** Cio' che si dice a HIRIS resta: memorie per-Chatbot, un «second brain di casa»
con una coda di approvazione umana, documenti importati da un archivio esterno, insight calcolati
dallo storico.

Sopra tutte e cinque c'e' la promessa che le tiene insieme, ed e' quella che l'utente compra: il
**contenimento**. Un semaforo a quattro colori — verde, giallo, rosso, spento — dichiara per ogni
categoria di dispositivi quanta autonomia si concede; cinque famiglie di dispositivi (serrature,
allarmi, tapparelle, sirene, porte da garage) sono negate comunque, qualunque colore si scelga
(`hiris/app/security/semaphore.py:79-81`, `141-146`); giallo e rosso non bloccano ma congelano, e
l'azione parte solo se un umano la sblocca entro cinque minuti
(`hiris/app/api/handlers_gateway_pending.py:58-85`); le scritture di configurazione verso Home
Assistant nascono come proposte in attesa di un clic (`hiris/app/proxy/proposal_store.py:17-32`);
e cio' che un Claude esterno puo' leggere della casa e' potato da una denylist che di norma copre
serrature, allarmi, telecamere, persone e localizzatori (`hiris/app/api/read_denylist.py:100-110`).

Questo e' cio' che HIRIS promette. Il resto di questo documento racconta cosa fa.

Tre fatti, dei molti registrati piu' avanti, bastano a inquadrare la distanza fra le due cose, e
vale la pena averli in mente leggendo tutto il resto.

Il primo: su un'installazione appena fatta il semaforo non e' verde ne' giallo — **e' spento su
tutto**. Il perimetro costruito all'avvio non contiene affatto le mappe dei tier
(`hiris/app/api/handlers_execute.py:76-91`) e, se l'utente non ha mai salvato la pagina Accessi
Gateway, la funzione che applica la policy esce senza toccare nulla
(`hiris/app/api/handlers_gateway_policy.py:269-270`): ogni azione di chat, task e Sentinella viene
negata con «Azione bloccata dal semaforo (off).» (`hiris/app/security/semaphore.py:152-153`). Il
sistema non e' rotto, e' chiuso, e non lo dice.

Il secondo: la conferma umana su cui poggia tutto il modello di sicurezza della chat **non e'
attivabile da nessuna interfaccia**. Lo step-up pretende una voce esplicita nella mappa
utente-canale privato (`hiris/app/api/handlers_gateway_policy.py:228-250`), e nessuna superficie
scrive quella mappa: la pagina Accessi Gateway invia soltanto il servizio di notifica globale
(`hiris/app/static/config/gateway-route.js:344-352`). Senza una modifica a mano del file su disco,
il modello dice «guarda il telefono» e sul telefono non arriva nulla.

Il terzo: la memoria, di fabbrica, non funziona. Il provider di embedding e' vuoto
(`hiris/config.yaml:69`), il sistema costruisce un motore fittizio che restituisce un vettore vuoto
(`hiris/app/backends/embeddings.py:203-205`), e poiche' quel motore e' comunque un oggetto gli
strumenti di memoria restano esposti al modello e falliscono a ogni chiamata
(`hiris/app/tools/dispatcher.py:229-233`).

HIRIS, in altre parole, e' un prodotto in cui le protezioni dichiarate esistono quasi tutte nel
codice, ma la loro tenuta dipende da configurazioni che l'interfaccia non permette di fare, e i
loro fallimenti sono quasi sempre muti verso la persona e rumorosi solo nei log. Chi lo usa vede
un assistente che risponde; cio' che non vede — se un comando sia partito davvero, se un ricordo
sia stato salvato, se una segnalazione sia rientrata o sia solo scomparsa dietro un errore di rete
— e' esattamente cio' che questo documento prova a rendere visibile.

---

# 2. Le aree di dominio

HIRIS non e' un unico programma con un unico comportamento: e' un insieme di motori che
condividono gli stessi archivi, lo stesso semaforo di sicurezza e — quasi sempre — lo stesso
esecutore di azioni, ma che partono da eventi diversi e finiscono su superfici diverse. Chi
usa il sistema incontra sette territori: la conversazione, gli strumenti che il modello puo'
usare, il cervello che agisce da solo, le regole che l'utente scrive, le azioni differite, la
coda di approvazione e la memoria. Questa sezione racconta ciascuno di essi dal punto di vista
di chi lo usa: da dove ci si entra, cosa succede passo per passo, cosa si vede a schermo e cosa
resta quando qualcosa non funziona.

---

### Chat e motore conversazionale

#### A cosa serve e da dove si entra

E' la superficie con cui si parla a HIRIS. Esistono due porte: la pagina `/chat` dell'add-on e
una card Lovelace da mettere in una dashboard di Home Assistant. Entrambe scrivono sullo stesso
endpoint, `POST /api/chat` (`server.py:2801` -> `api/handlers_chat.py:140`).
Chi passa dall'Ingress di Home Assistant entra senza alcun controllo di ruolo o di utente
(`middleware_internal_auth.py:76`); l'unico requisito formale e' l'header `X-Requested-With`
richiesto dalla protezione CSRF (`middleware_csrf.py:44`).

La conversazione avviene sempre "con" un Chatbot, cioe' una persona configurabile che porta con
se' un prompt di sistema, un perimetro di entita' e servizi, un elenco di strumenti concessi, un
modello e dei limiti. Il Chatbot si sceglie nella pagina; se l'id indicato non esiste si ricade
sul Chatbot predefinito `hiris-default` (`chatbot_engine.py:251`). Vale la pena sapere che il
motore non guarda mai se il Chatbot sia abilitato: la richiesta viene servita comunque
(`handlers_chat.py:160-166`), anche se la card Lovelace mostra un banner che dichiara il
contrario.

#### Il flusso principale: una domanda, una risposta

Il percorso ordinario e' sincrono e non in streaming (`static/chat/send.js:95`). Passo per passo:

1. Il server risolve chi sta parlando leggendo l'header `X-Remote-User-Id`; se manca, l'identita'
   diventa `home` (`handlers_chat.py:141`, `brain/identity.py:6`).
2. Il messaggio e' obbligatorio e non puo' superare i 4000 caratteri: oltre quella soglia la
   risposta e' un 413 (`handlers_chat.py:147-151`).
3. Se il Chatbot ha un tetto di turni per sessione e il tetto e' raggiunto, il modello non viene
   nemmeno interpellato: torna un 200 con `max_turns_reached` (`handlers_chat.py:176-184`), e la
   pagina scrive "Sessione completata. Avvia una nuova conversazione." disabilitando l'input.
4. Viene ricaricata la conversazione in corso. "In corso" ha un significato preciso: si prende
   solo la sessione attiva, dove per sessione si intende una sequenza di messaggi separati da
   meno di due ore l'uno dall'altro (`chat_store.py:159`); si scartano i turni classificati come
   tossici e si taglia a trenta coppie (`handlers_chat.py:222`). Poi si tiene solo la coda che
   sta in circa 6000 token stimati (`handlers_chat.py:227`).
5. Si compone il contesto. In testa finiscono i ricordi piu' simili alla domanda, recuperati per
   similarita' semantica (`handlers_chat.py:275-305`); poi i riassunti di al massimo tre sessioni
   chiuse (`handlers_chat.py:244-251`); poi la fotografia della casa prodotta dalla
   SemanticContextMap, che descrive le aree e approfondisce quelle nominate nella domanda
   (`handlers_chat.py:259-266`, `semantic_context_map.py:399-415`). I tre blocchi compaiono nel
   prompt con le intestazioni "## Memoria rilevante", "## Sessioni precedenti", "## Contesto
   casa" (`handlers_chat.py:308-315`).
6. Si leggono i parametri della persona: modello, limite di token, restrizioni, modalita' di
   risposta, budget di ragionamento (`handlers_chat.py:317-340`). Un dettaglio con conseguenze
   pratiche: il limite di token viene alzato d'ufficio a 16000 se il valore configurato e'
   inferiore (`handlers_chat.py:327-332`), quindi sotto quella soglia il campo dell'editor non
   cambia nulla in chat.
7. Si chiama il modello (`handlers_chat.py:419`) e parte il ciclo agentico descritto piu' avanti.
8. Alla fine, se la risposta non e' vuota ne' riconosciuta come tossica, si salvano insieme il
   turno dell'utente e quello dell'assistente (`handlers_chat.py:464-468`).

L'utente vede la bolla di risposta e, se ci sono stati strumenti, un blocco di debug espandibile
con l'elenco delle chiamate (`handlers_chat.py:470-495`). Non vede mai quale modello o quale
fornitore abbia risposto, ne' quanto sia costato.

#### Il ciclo degli strumenti

Quando il modello chiede di usare uno strumento, il motore entra in un ciclo che al massimo fa
dieci chiamate all'API (`claude_runner.py:754`). A ogni giro: si contano i token e si aggiorna il
file di consumo su disco (`claude_runner.py:776-797`); se il modello ha finito, si concatena il
testo e si esce (`claude_runner.py:799-801`); se ha chiesto uno strumento, la chiamata passa al
dispatcher con il perimetro del Chatbot e il risultato torna indietro come dato JSON
(`claude_runner.py:803-828`). I risultati vecchi vengono troncati a 300 caratteri per non gonfiare
il contesto (`claude_runner.py:98-121`). Se le dieci iterazioni finiscono senza conclusione, la
risposta all'utente e' la stringa "Max tool iterations reached." (`claude_runner.py:837`), che
viene anche salvata nello storico.

Le chiamate al fornitore hanno tre ritentativi con attese di 5, 15 e 45 secondi in caso di
sovraccarico o limite di richieste (`claude_runner.py:999-1010`).

#### La card Lovelace e lo streaming

La card chiede esplicitamente lo streaming (`hiris-chat-card.js:825-834`). Il server apre subito
una risposta a flusso e comincia a inoltrare gli eventi (`handlers_chat.py:347-378`). Qui il
comportamento cambia radicalmente a seconda del fornitore: sui backend compatibili con OpenAI lo
streaming e' reale, i pezzi di testo arrivano man mano (`openai_compat_runner.py:750-1031`); sul
backend Anthropic no — si attende l'intera risposta e solo dopo la si spezza in blocchi da 80
caratteri (`claude_runner.py:839-908`). Per l'utente la differenza e': con Anthropic non si vede
nulla per tutta la durata del turno, poi il testo appare a raffica. La card interrompe la lettura
dopo 30 secondi (`hiris-chat-card.js:822`), quindi un turno che usa parecchi strumenti puo' essere
troncato dal client con "Timeout — riprova".

Un altro dettaglio del percorso in streaming: con modello "auto" non c'e' nessuna ricaduta su un
secondo fornitore, si usa solo il primo della catena (`llm_router.py:240-246`). E se il flusso si
interrompe con un errore prima di produrre testo, non viene persistito nulla — nemmeno la domanda
dell'utente (`openai_compat_runner.py:784-796`).

#### La chat "via abbonamento"

Esiste un terzo percorso, attivo quando l'installazione e' configurata per far ragionare un
processo esterno su abbonamento invece che a consumo (`handlers_chat.py:193`). Qui la risposta non
e' immediata: il turno dell'utente viene salvato subito, il lavoro viene messo in coda con una
scadenza di cinque minuti e il server risponde 202 con un identificativo
(`handlers_chat.py:81-100`). Un lavoratore interno reclama il lavoro ogni tre secondi
(`agent/runner.py:200`), lancia il binario `claude` in modalita' non interattiva
(`agent/runner.py:123-159`) e restituisce il testo. Intanto la pagina interroga il server ogni
3,5 secondi per un massimo di cinque minuti (`static/chat/send.js:30-65`).

L'utente vede un segnaposto "HIRIS sta pensando…" e l'input bloccato. Tre cose vale la pena
sapere. Primo: se il lavoratore e' in modalita' di prova, la risposta consegnata e' letteralmente
"[mock] risposta di prova", senza alcuna indicazione che sia finta. Secondo: un errore del
processo esterno diventa un testo tipo "[errore runner rc=…]" o "[runner non disponibile]"
(`agent/runner.py:150,159`), che arriva all'utente come se fosse una risposta. Terzo: su questo
percorso il lavoro accodato contiene soltanto identificativo del Chatbot, storico e prompt di
sistema (`handlers_chat.py:66-100`) — niente contesto casa, niente memoria, niente strumenti
configurati; il lavoratore usa una lista di strumenti fissa propria (`agent/runner.py:25-32`).

C'e' anche un caso in cui schermo e cronologia divergono: una risposta giudicata tossica viene
scartata dallo storico (`server.py:2241-2247`) ma il polling continua a leggerla dalla coda e la
mostra comunque (`handlers_chat.py:135-137`).

#### Quale modello risponde

Se il Chatbot indica un modello preciso, l'instradamento avviene per prefisso del nome: `claude-*`
va ad Anthropic, `gpt-*` e `o1..o9` a OpenAI, `openrouter:*` a OpenRouter, e qualunque altra cosa
finisce a Ollama (`llm_router.py:219-224`). Il runner Ollama, pero', ha un modello fisso: ignora
il nome richiesto e usa sempre quello configurato localmente (`openai_compat_runner.py:403-408`).
Di conseguenza un nome di modello scritto male non produce un errore, produce una risposta da un
modello diverso.

Se il modello e' "auto", si prova la catena in ordine e, sul percorso non-streaming, si passa al
fornitore successivo a ogni fallimento (`llm_router.py:227-235`); esaurita la catena l'utente
legge "Tutti i provider AI non disponibili. Riprova tra poco." — stringa che viene salvata nello
storico come se fosse una risposta. Un ulteriore meccanismo di protezione apre un "circuito" dopo
tre errori di connessione consecutivi, sospendendo il fornitore per 60 secondi
(`openai_compat_runner.py:414-425`).

#### Cosa succede quando fallisce

Il repertorio degli esiti negativi visibili all'utente e' abbastanza uniforme: un testo nella
bolla dell'assistente. Nessun runner configurato produce un 503; il messaggio troppo lungo un 413;
la caduta di rete lato browser un "Errore di connessione. Riprova tra poco."
(`static/chat/send.js:122`). Sul percorso principale non esiste alcun timeout lato server: valgono
solo quelli delle librerie dei fornitori (`openai_compat_runner.py:213-217`).

Una conseguenza poco intuitiva riguarda la persistenza: quando la risposta viene scartata perche'
vuota o tossica, non viene salvato nulla — quindi si perde anche la domanda
(`handlers_chat.py:464-468`). Al contrario, i turni scartati dal contesto perche' tossici restano
contati nel conteggio dei turni della sessione (`chat_store.py:289`), per cui il tetto puo'
scattare prima di quanto mostri il contatore in pagina.

Infine, dopo due ore di pausa la conversazione riparte da zero a schermo, senza alcun avviso; il
modello continua pero' a ricevere i riassunti delle sessioni chiuse
(`static/chat/agents.js:131`, `chat_store.py:177-206`). Vale la pena sapere che quei "riassunti"
sono la concatenazione verbatim delle ultime tre coppie di turni, ciascun messaggio troncato a
120 caratteri: nessun modello viene interpellato per produrli (`chat_store.py:177-206`).

---

### Il catalogo degli strumenti esposti al modello

#### A cosa serve

E' la differenza fra "HIRIS mi risponde" e "HIRIS mi accende la luce". Il catalogo dichiara 37
strumenti (`claude_runner.py:181-219`) e un unico esecutore, il dispatcher
(`tools/dispatcher.py:235-786`), che traduce la richiesta del modello in letture di Home
Assistant, attuazioni, scritture negli archivi di HIRIS, notifiche e chiamate HTTP. Lo stesso
dispatcher serve quattro superfici diverse — la chat, gli agenti non conversazionali, l'API di
esecuzione usata dal gateway MCP e il percorso di approvazione — e a ciascuna viene dato un
sottoinsieme diverso.

#### Come si concedono gli strumenti

Nell'editor del Chatbot gli strumenti sono caselle da spuntare, con etichetta e descrizione
italiana (`static/config/templates.js:61-98`). La selezione finisce nel campo `allowed_tools`
della persona e a quel punto governa quali definizioni vengono dichiarate al modello
(`claude_runner.py:712`). Due comportamenti da conoscere: una selezione vuota equivale a "nessun
vincolo", cioe' al catalogo intero (`handlers_chat.py:230`); e la whitelist agisce solo su cosa
viene dichiarato, non su cosa viene eseguito — al momento del dispatch il nome dello strumento
viene passato cosi' com'e', senza riverificare che appartenga alla lista
(`claude_runner.py:808-820`). Il catalogo della UI conta inoltre 36 voci contro le 37 dichiarate:
manca `http_request`, che quindi puo' arrivare a un Chatbot solo per la via della selezione vuota.

Alcune esclusioni avvengono dinamicamente: `render_template` viene tolto se il Chatbot ha un
perimetro di entita' ma non una whitelist esplicita di strumenti; `http_request` viene tolto se non
sono configurati endpoint permessi; gli strumenti di memoria vengono tolti se manca l'archivio
(`claude_runner.py:712-727`).

#### Leggere lo stato della casa

Le letture partono dalla cache delle entita' alimentata dalla connessione WebSocket con Home
Assistant. La prima cosa che il dispatcher verifica e' che l'inventario sia pronto: se non lo e',
non legge nulla e restituisce un errore esplicito (`dispatcher.py:324-341`). Poi filtra il
risultato sul perimetro di entita' del chiamante (`dispatcher.py:66-75`).

Due strumenti gemelli si comportano diversamente quando il filtro svuota l'elenco: la lettura
degli stati restituisce una lista vuota, indistinguibile da "non esiste"
(`dispatcher.py:258-264`), mentre la lettura dello storico risponde con un errore di input
malformato (`tools/history_tools.py:38-47`). L'utente, e anche il modello, leggono in un caso un
silenzio e nell'altro un difetto della propria richiesta, mai un "fuori perimetro".

#### Attuare: il semaforo e la conferma

Il cuore della sicurezza e' il varco che precede ogni chiamata di servizio verso Home Assistant
(`dispatcher.py:182-221` -> `security/semaphore.py:126-160`). Funziona cosi':

- I bersagli dichiarati in forma di "target" vengono fusi nei dati una volta sola, cosi' le entita'
  giudicate sono esattamente quelle su cui si agira' (`security/semaphore.py:34-79`).
- Cinque famiglie di dispositivi sono sempre negate, comunque configurate: serrature, centrali di
  allarme, tapparelle, sirene, porte da garage.
- Per tutto il resto vale il colore assegnato nella pagina Permessi, preso nel valore peggiore fra
  i bersagli; un dominio non configurato vale "spento" e quindi nega.
- Bersagli collettivi — un'area, un dispositivo, un piano — vengono rifiutati in blocco quando la
  richiesta non e' gia' stata confermata da un umano (`dispatcher.py:433-435`).

Quando il verdetto e' "chiedi conferma", l'azione non parte: viene congelata cosi' com'e' e
all'utente arriva sul canale privato una notifica con un codice numerico di sei cifre
(`server.py:415-465`). Se non c'e' un'identita' reale o non c'e' un canale privato configurato, il
modello riceve semplicemente "Azione a rischio: richiede conferma." e la faccenda finisce li'
(`dispatcher.py:213-214`).

L'utente puo' approvare toccando la notifica oppure dettando il codice in chat. In entrambi i casi
viene rieseguita l'azione congelata, non ricostruita da capo (`handlers_gateway_pending.py:333-353`),
e la riesecuzione salta interamente il varco, denylist dei domini pericolosi compresa — una scelta
dichiarata nel codice (`dispatcher.py:423-427`). Il codice viene oscurato prima di finire nei log
e nel pannello di debug (`claude_runner.py:386-401`, `dispatcher.py:251-252`).

Non tutto cio' che tocca Home Assistant passa da questo varco: la creazione di eventi di calendario,
la creazione di script e scene, e l'invio di notifiche seguono strade proprie
(`dispatcher.py:566-578`, `dispatcher.py:637-655`, `dispatcher.py:346-350`).

#### Gli agenti non conversazionali

Sentinella e Agentbot chiamano il modello con una lista di strumenti dichiarata vuota
(`server.py:1710-1746`). Nel codice il restringimento e' scritto come "se c'e' una lista, usala":
una lista vuota non e' "una lista" in senso logico, quindi il restringimento non scatta e l'agente
riceve l'intero insieme di strumenti di sola valutazione (`claude_runner.py:966-968`). Quell'insieme
esclude le attuazioni dirette ma include `create_task` (`claude_runner.py:225-253`), cioe' la
possibilita' di programmare un'azione differita che verra' rigiudicata dal semaforo al momento
dello scatto.

#### La superficie dell'API di esecuzione e il gateway MCP

Chi possiede il token interno puo' chiamare `POST /api/execute` (`handlers_execute.py:147-363`).
Qui i filtri sono tre e in sequenza: una allowlist rigida di strumenti scritta nel codice, la
politica salvata dall'utente, e — per le letture — una denylist di entita' che di norma copre
serrature, allarmi, telecamere, persone e localizzatori (`read_denylist.py:67-73`). La denylist
agisce due volte: rifiuta con 403 una richiesta che nomina un'entita' coperta
(`handlers_execute.py:328-342`) e pota la risposta in uscita, dichiarando quante voci sono state
tolte (`handlers_execute.py:355-362`). Se uno strumento non ha un potatore registrato, la risposta
viene bloccata per intero.

Le attuazioni chieste da questa superficie non vengono eseguite direttamente quando il colore non
e' verde: diventano richieste in attesa, con notifica azionabile per il giallo e rinvio alla coda
interna per il rosso (`handlers_execute.py:236-253`).

C'e' un'eccezione con conseguenze pratiche: le richieste che arrivano dal client MCP interno
vengono marcate come "chat locale" e con quel marcatore saltano la denylist di lettura
(`mcp/local_client.py:40-41`, `read_denylist.py:75-84`). Il marcatore e' legato al trasporto, non
al Chatbot.

#### Cosa succede quando fallisce

Un errore dentro uno strumento diventa un messaggio generico verso il modello, "Strumento 'X' non
riuscito. Riprova piu' tardi.", con il dettaglio che resta solo nei log del server
(`dispatcher.py:780-786`); manca invece un campo obbligatorio, il messaggio lo nomina
(`dispatcher.py:768-779`). Uno strumento inesistente produce un errore testuale
(`dispatcher.py:760-767`). L'utente, in tutti questi casi, vede soltanto cio' che il modello
sceglie di raccontargli.

---

### Il Brain: cio' che HIRIS fa senza che nessuno chieda

#### A cosa serve e come si articola

Sono tre motori distinti che condividono lo stesso esecutore. La **Sentinella** osserva i cambi di
stato di Home Assistant e fa una ronda periodica. Il **cervello proattivo** fa a una certa ora una
revisione olistica della casa, si concede nuove coperture di rilevatore e propone automazioni.
L'**igiene** e' una scansione di salute ogni mezz'ora che produce le "Segnalazioni del Brain", piu'
il resoconto delle 08:00 e i solleciti sulle scadenze.

Per l'utente e' cio' che fa comparire notifiche persistenti in Home Assistant, notifiche sul
telefono, righe nella timeline, card nella Dashboard e proposte, senza che nessuno abbia premuto
nulla.

#### Il ciclo della Sentinella, passo per passo

Home Assistant emette un cambio di stato; il guardiano lo riceve (`watcher/guardian.py:46-84`) e lo
sottopone ai quattro rilevatori integrati: aperture, temperatura del frigo, consumo, batteria
(`detectors.py:69-74`). Alcuni rilevatori richiedono che la condizione persista per un certo numero
di minuti: in quel caso si apre un timer e non succede nulla finche' il tempo non e' passato
(`guardian.py:67-73`).

Se il segnale regge, si applica un doppio freno: una pausa di trenta minuti per la stessa chiave e
un tetto giornaliero di venti risvegli condiviso da tutti i rilevatori e tutte le entita'
(`wake.py:19-35`). Superati i freni, si raccoglie il contesto — nome amichevole dell'entita' e fino
a cinque frammenti di memoria (`server.py:1688-1707`) — e si chiede al modello un verdetto
(`reasoner.py:136-147`).

La risposta del modello viene letta cercando l'ultimo blocco JSON; se non e' interpretabile, il
verdetto predefinito e' "anomalia" (`reasoner.py:96-134`). Poi l'esecutore applica il semaforo
(`watcher/executor.py:6-36`):

- falso positivo: nulla;
- azione assente o senza entita': solo notifica;
- dominio pericoloso: solo allerta;
- colore verde **e** opzione di automatismo attiva: si esegue davvero e la notifica dice "(fatto)";
- verde senza opzione, oppure giallo: si salva una **proposta** di script;
- rosso o spento: solo allerta.

In ogni caso viene scritta una riga nella timeline (`server.py:1917-1921`).

Cosa vede l'utente: una notifica persistente in Home Assistant intitolata "HIRIS Sentinella"
(`server.py:1816-1819`) nei rami notifica/allerta/esecuzione, e una riga in "Eventi recenti".
Nel ramo "proposta", invece, non vede nulla: la proposta viene salvata e basta
(`sentinel_proposal.py:134-168`), e la si scopre solo aprendo la pagina Proposte. Il caso di
errore, paradossalmente, e' piu' visibile del caso riuscito.

#### La ronda e la revisione olistica

Ogni quindici minuti una ronda costruisce una fotografia composita della casa — presenza,
temperatura esterna, stato dell'allarme, previsioni meteo, salute di Home Assistant — e valuta
situazioni che nessun singolo rilevatore vedrebbe: "casa vuota e fa caldo", "casa vuota e allarme
disinserito" (`evaluator.py:31-59`, `snapshot.py:31-68`, `situations.py:40-43`). In queste
situazioni il bersaglio dell'azione non viene mai dal modello: viene sostituito con quello scritto
nella configurazione (`server.py:2100-2101`).

La revisione olistica e' il pezzo piu' ambizioso, ed e' spenta di fabbrica (`policy.py:31`). Quando
e' attiva, a un'ora prestabilita costruisce un inventario della casa (troncato a mille entita'),
recupera fino a cinque frammenti di memoria, e chiede al modello una revisione delle coperture
(`server.py:2256-2301`). Le proposte che tornano vengono divise in due tipi. Quelle di
"copertura" — abilita quel rilevatore su quell'entita' — vengono **applicate da sole**, senza
chiedere nulla, dopo aver validato e limitato i parametri, fino a un massimo di cinque per giro
(`suggestions.py:167-247`, `policy.py:230-280`). Quelle di "gestione", se sono davvero
configurazioni di automazione, diventano proposte in attesa di approvazione
(`suggestions.py:213-241`).

Il testo grezzo del ragionamento, privato del blocco JSON e limitato a 4000 caratteri, finisce nello
"Stream ragionamenti" della Dashboard (`server.py:2302-2307`). Questo e' l'unico scrittore di quel
registro: i ragionamenti della Sentinella per evento, delle situazioni, del resoconto e degli
Agentbot non ci finiscono mai.

Segue la **taratura automatica**: per il solo rilevatore di consumo (`learned_thresholds.py:97-99`),
si legge la linea di base dello storico degli ultimi quattordici giorni e si ricalcola la soglia,
con limiti relativi e assoluti e una isteresi del 15% per non muoverla per nulla
(`learned_thresholds.py:56-94`, `history/store.py:243-263`). Il valore precedente viene salvato in
un registro laterale la prima volta, cosi' la modifica resta annullabile (`policy.py:305-336`).
Poiche' la storicizzazione e' vuota per impostazione predefinita, questo meccanismo non tara mai
nulla finche' l'utente non la abilita esplicitamente.

Cosa vede l'utente: righe nella sezione "Suggerimenti del Brain" della pagina Agentbot, ciascuna con
un pulsante "Annulla" (`agentbot-route.js:422-480`). Vale la pena sapere che quelle righe non sono
suggerimenti in attesa di parere: sono modifiche gia' applicate, registrate a posteriori per poter
riusare quel pulsante.

#### Annullare cio' che il Brain ha fatto

Premendo "Annulla" (`handlers_suggestions.py:15-71`) il sistema distingue due casi: se la riga
riguarda una taratura, ripristina il valore precedente dallo snapshot; altrimenti rimuove l'entita'
dal rilevatore, ma **solo se** quella coppia risulta registrata come aggiunta dal Brain
(`policy.py:283-360`). E' l'unica garanzia che l'annullamento non tocchi mai una configurazione
fatta a mano dall'utente. Se il ripristino riesce, la riga diventa "Ignorato"; se fallisce, accanto
alla riga compare "Annullamento non riuscito.".

#### La scansione di salute e le segnalazioni

Ogni trenta minuti (`server.py:2405-2427`) HIRIS scarica tutti gli stati di Home Assistant, la mappa
delle aree, le automazioni e — se ne ha il permesso — l'elenco degli add-on, le informazioni
sull'host e gli aggiornamenti disponibili (`health_scan.py:224-306`). Su questi dati applica otto
controlli: entita' non disponibile da almeno due giorni, batteria sotto il 15%, automazione rotta,
dominio pericoloso lasciato verde, entita' senza area, add-on fermo, disco quasi pieno,
aggiornamenti in attesa (`health_checks.py`).

Il risultato viene riconciliato con quanto gia' noto: le nuove segnalazioni entrano, quelle risolte
si chiudono, quelle riaperte tornano attive, e quelle che l'utente ha esplicitamente ignorato
restano fuori per sempre (`advisory_store.py:78-166`). Solo le segnalazioni **gravi** producono una
notifica sul telefono, con un tetto di cinque notifiche per scansione e un riepilogo unico per le
restanti (`health_scan.py:150-221`). Batteria scarica ed entita' non disponibile sono classificate
come avvisi, non come guasti gravi: non producono mai una notifica.

Tutte le segnalazioni attive sono comunque visibili nella Dashboard sotto "Segnalazioni del Brain",
con i pulsanti "Ho capito" e "Ignora" (`dashboard.js:206-262`).

Il modo in cui questa scansione fallisce merita attenzione: ogni raccolta dati e' isolata, e un
fallimento lascia una lista vuota; ma una lista vuota viene interpretata dalla riconciliazione come
"problema rientrato", e chiude come risolte tutte le segnalazioni attive di quel controllo
(`advisory_store.py:155-165`). Un errore di rete verso il Supervisor si presenta quindi all'utente
come add-on tornati a posto.

#### Resoconto, solleciti, digest

Alle 08:00 parte il resoconto quotidiano: scadenze entro sette giorni, porte e finestre aperte in
quel momento, batterie scariche rilette dalle segnalazioni attive (`briefing.py:211-269`). Il testo
viene composto dal modello e, se il modello non risponde, si ripiega su un modello di testo
deterministico, cosi' il resoconto esce comunque (`briefing.py:464-479`). Se pero' qualcosa fallisce
piu' in alto, non parte nessuna notifica e l'utente non sa che il resoconto e' saltato
(`server.py:962-965`).

Ogni sei ore un secondo lavoro cerca le scadenze urgenti e ne manda una notifica per soglia
attraversata — scaduto, oggi, domani — marcando la coppia come vista solo dopo un invio riuscito
(`server.py:993-1024`, `reminders.py:79-112`). Alle 04:00, infine, un digest legge lo storico e
produce una frase per entita' — media settimanale o ore di attivita' con la variazione percentuale —
che rientrera' nei contesti della Sentinella e della revisione olistica
(`history_digest.py:110-147`).

#### Cosa succede quando fallisce

Il tratto ricorrente di quest'area e' che i fallimenti sono silenziosi verso l'utente e rumorosi
solo nei log. Un'eccezione nel giro delle situazioni aborta il giro intero, revisione olistica
compresa (`evaluator.py:32` il `try`, `51-57` il blocco olistico dentro lo stesso `try`, `58-59` il gestore). Un'eccezione nel blocco di revisione olistica viene registrata e si
prosegue (`server.py:2385-2386`). Una taratura applicata ma non registrata resta applicata e non e'
piu' annullabile dall'interfaccia (`cognitive_loop.py:224-228`).

Due casi si vedono invece eccome. Il primo: se nessun fornitore di modelli risponde, il ragionamento
produce testo vuoto, il verdetto predefinito e' "anomalia" e l'utente riceve una notifica persistente
intitolata "HIRIS Sentinella" il cui corpo e' letteralmente "(vuoto)" (`server.py:1741-1754`,
`reasoner.py:132-134`). Il secondo: nel ramo verde con automatismo, l'esecutore non guarda l'esito
della chiamata — la notifica dice "(fatto)" anche quando il dispatcher ha restituito un errore o
Home Assistant ha rifiutato (`watcher/executor.py:23-26`, `dispatcher.py:436-456`).

---

### Agentbot: le regole scritte dall'utente

#### A cosa serve e da dove si entra

Gli Agentbot permettono di scrivere le proprie regole sopra la stessa infrastruttura della
Sentinella. Un Agentbot ha un innesco — un evento su un'entita' oppure una pianificazione — un
ragionamento facoltativo, e un esito: una notifica o una chiamata di servizio. Dalla versione 1.1 lo
stesso oggetto ha una seconda modalita', "obiettivo", in cui al posto dell'azione dichiarata c'e' un
traguardo scritto in linguaggio naturale e un perimetro (entita', servizi, budget di token, scadenza)
dentro cui un turno di modello ragiona ed emette task.

Si entra dalla pagina `#/agentbots` del pannello di configurazione, dall'editor completo, oppure dal
wizard guidato che parte dalla missione scritta a parole (`static/config/create-wizard.js:632`). Un
Agentbot puo' anche nascere da una proposta scritta da un modello e approvata dall'utente
(`handlers_proposals.py:82-109`).

#### Il ciclo di vita di una regola

Al salvataggio, il pannello costruisce il payload da zero campo per campo
(`agentbot-editor.js:720`), il server toglie ogni identificativo dal corpo e passa tutto al
validatore (`handlers_agentbots.py:108`). Il salvataggio su file avviene sotto lock con scrittura
atomica (`agentbots.py:798`), poi i lavori pianificati vengono ri-registrati rileggendo il file da
disco e la cache in memoria viene aggiornata (`handlers_agentbots.py:75-90`, `server.py:569-661`).
L'effetto e' che una regola a evento nuova diventa viva subito, senza riavviare nulla.

Il validatore e' severo e reticente: circa trenta cause di rigetto distinte collassano tutte in una
sola stringa, "invalid agentbot" (`handlers_agentbots.py:127,154`), che l'editor mostra tale e quale
in una finestra di avviso. L'utente non sa se il problema sia la soglia, il cron, l'operatore o una
contraddizione di modalita'. Il caso piu' frequente e' proprio il wizard: gli operatori di confronto
numerico esistono nel modulo, ma la soglia viene inviata come testo, e il validatore accetta stringhe
solo per uguale e diverso (`create-wizard.js:420-424`, `agentbots.py:199-227`).

All'avvio, ogni regola memorizzata ma non piu' valida viene scartata dalla lettura con un avviso nei
log e sparisce dall'elenco senza alcuna segnalazione a schermo; il primo salvataggio successivo rende
la sparizione definitiva (`agentbots.py:784-794`).

#### Una regola a evento senza ragionamento

Cambio di stato -> il guardiano filtra le regole abilitate, a evento, in modalita' regola
(`handlers_agentbots.py:67-72`) -> confronta il valore, numericamente se entrambi i lati sono numeri,
altrimenti come testo (`detectors.py:83`) -> eventuale timer di durata -> pausa di trenta minuti e
tetto giornaliero di venti (`wake.py:10`) -> l'azione eseguita e' sempre e solo quella scritta nella
configurazione (`agentbot_runner.py:349-366`) -> il semaforo decide se notificare, proporre o agire,
esattamente come per la Sentinella.

Cosa vede l'utente: nel caso piu' comune — Permessi non ancora configurati, quindi colore "spento" —
soltanto una notifica persistente con il titolo fisso "HIRIS Sentinella". Il nome dell'Agentbot non
compare nel titolo. Nel ramo "proposta" non vede nulla finche' non apre la pagina Proposte.

#### Una regola a evento con ragionamento

Il percorso e' identico fino al risveglio; poi il prompt di sistema della Sentinella viene esteso con
il prompt scritto dall'utente, e il modello produce verdetto, gravita' e messaggio
(`agentbot_runner.py:281-348`). L'azione, se c'e', resta quella della configurazione: viene
sostituita dopo il ragionamento (`server.py:2101-2102`), e per un Agentbot di tipo "notifica" viene
azzerata del tutto prima dell'esecuzione (`server.py:2103-2111`).

Un effetto pratico da conoscere: in questo ramo il campo "Messaggio" scritto nell'editor non viene
usato. Il testo consegnato e' quello prodotto dal modello, o — se il modello sbaglia formato — il suo
testo grezzo troncato a 500 caratteri (`agentbot_runner.py:182-194`, `reasoner.py:126-133`).

#### Le regole pianificate e gli agenti-obiettivo

Le regole pianificate vengono registrate come lavori sullo scheduler condiviso, con il campo del
giorno della settimana rimappato dalla numerazione crontab standard a quella della libreria
(`agentbots.py:141`, `server.py:634-661`). Allo scatto, se c'e' una condizione, viene verificata
sullo stato corrente letto dalla cache; se non si puo' confermare — cache assente, entita' mai vista —
lo scatto viene saltato in silenzio (`server.py:499-542`). Per le pianificate la pausa di trenta
minuti non si applica: e' la cadenza stessa a fare da freno (`server.py:557-564`).

La modalita' obiettivo impone dei vincoli propri: obiettivo obbligatorio, azione vietata, innesco a
evento vietato, perimetro sempre materializzato, ragionamento sempre acceso
(`agentbots.py:568-731`). Il perimetro fissa entita' e servizi permessi, un budget di token e una
scadenza per esecuzione. Il modello legge la casa dentro il perimetro ed emette task; l'esito diretto
dell'esecuzione e' pero' sempre e solo una notifica, perche' l'azione viene azzerata prima
dell'esecuzione (`agentbot_runner.py:341-347`, `server.py:2103-2111`). Se il budget viene superato,
l'esecuzione si ferma prima di produrre effetti e in timeline compare una riga "interrotto:budget"
(`server.py:2087-2100`); se scade il tempo, "interrotto:scadenza" (`server.py:2055-2070`). Se il
consumo non e' misurabile — perche' il fornitore non restituisce i contatori — il tetto non scatta e
resta solo un avviso nei log, una volta per agente (`server.py:790-808`).

#### Cosa vede l'utente e cosa succede quando fallisce

L'elenco mostra nome, gravita' e stato attivo/disabilitato. L'editor ha una sezione "Eventi recenti":
chiede al server la timeline senza specificare un limite, riceve gli ultimi cinquanta eventi globali
della Sentinella e filtra lato client (`handlers_sentinel.py:41-48`, `agentbot-editor.js:488-515`).
In una casa attiva gli eventi dell'Agentbot escono da quella finestra e la pagina dichiara "nessun
evento registrato" mentre nel database ce ne sono.

Il campo "Severita'" e' un altro caso di configurazione che non cambia il comportamento: l'esecutore
non lo legge mai, e la colonna in cui finisce non viene mostrata da nessuna delle due timeline
(`watcher/executor.py:6-36`, `agentbot_runner.py:273`).

Il freno dei trenta minuti e' il fallimento piu' invisibile: una regola che riscatta entro quella
finestra viene soppressa senza registrare nulla — nessun evento, nessun log, nessun segnale a schermo
(`wake.py:21-22`). Il tetto giornaliero, al contrario, lascia una riga con esito "cap" a ogni scatto
oltre il ventesimo.

---

### Task pianificate

#### A cosa servono e chi le crea

Sono le azioni differite: "fra trenta minuti spegni", "alle 18:00 avvisami", "fra le 18 e le 20, se
l'umidita' scende sotto 40, irriga". Un task e' una tripletta — innesco, condizione facoltativa,
lista di azioni — persistita su `/data/tasks.json`, che sopravvive al riavvio dell'add-on e che allo
scatto ripassa dal semaforo (`task_engine.py`).

Li puo' creare il modello dalla chat, un agente in valutazione, il gateway MCP, e la Sentinella
quando esegue un'accensione con spegnimento programmato (`server.py:1857-1866`,
`watcher/off_task.py:38-50`). L'utente li vede in due posti: la pagina "Task pianificati" del
pannello di configurazione e il pannello laterale della chat, che si aggiorna da solo ogni trenta
secondi (`static/chat/tasks.js:64-107`).

#### Creazione

Alla creazione valgono tre filtri: il tipo di ogni azione deve essere fra chiamata di servizio,
notifica e creazione di un altro task (`dispatcher.py:14,460-464`); per le chiamate di servizio di
primo livello si verifica il **servizio** contro il perimetro, ma non l'entita'
(`dispatcher.py:483-487`); il motore verifica che l'innesco sia di un tipo noto e che la condizione
abbia la forma giusta (`task_engine.py:130-136`). Il task nasce con l'identita' del chiamante e con
i due perimetri congelati (`task_tools.py:95-101`).

Quando la richiesta arriva dal gateway c'e' un filtro in piu': vengono rifiutate alla creazione le
azioni di primo livello con bersaglio collettivo, senza entita' esplicita, o non verdi
(`handlers_execute.py:271-291`).

Un caso che vale la pena conoscere: se l'innesco ha un tipo valido ma un contenuto malformato — per
esempio "ritardo" senza il numero di minuti — la registrazione del lavoro fallisce, l'eccezione
viene solo scritta nei log, e il task resta salvato, restituito al modello come programmato e
mostrato all'utente come "In attesa" pur non potendo scattare mai (`task_engine.py:317-318`).

#### Lo scatto

Il motore mette il task in esecuzione, valuta la condizione contro la cache delle entita' (non
interroga Home Assistant), poi esegue le azioni in sequenza (`task_engine.py:366-423`). Per ogni
azione registra un esito. Alla fine il task diventa "eseguito" o "fallito".

Per una chiamata di servizio, l'azione ripassa da tutto il varco di sicurezza: fusione dei bersagli,
rifiuto dei bersagli collettivi, perimetro dei servizi, perimetro delle entita', semaforo
(`task_engine.py:438-506`). Se il verdetto e' "chiedi conferma", parte la stessa notifica con codice
a sei cifre verso il proprietario degli agenti.

I task a finestra oraria hanno una vita a se': un lavoro ricorrente li controlla ogni cinque minuti,
esegue al primo momento in cui la condizione e' vera dentro la finestra, e li dichiara scaduti al
primo controllo successivo alla fine della finestra (`task_engine.py:524-564`). Una finestra che
scavalca la mezzanotte non scade mai.

#### Cosa vede l'utente e cosa succede quando fallisce

L'utente vede l'elenco con lo stato tradotto e, per i task conclusi, la stringa grezza dell'esito —
per esempio `call_ha_service:skipped: deny_off (light.turn_on)` (`static/chat/tasks.js:15`). Il motore
non emette nessuna notifica propria: l'esito si scopre solo aprendo una delle due liste. Puo'
annullare un task in attesa da entrambe le superfici; nessuna delle due verifica la proprieta' del
task, e l'unica barriera dell'endpoint di cancellazione e' la presenza dell'header CSRF
(`handlers_tasks.py:36-43`).

Tre comportamenti si notano solo nell'uso. Primo: "eseguito" non significa "riuscito". Una chiamata
che Home Assistant rifiuta restituisce falso senza sollevare un errore, e viene registrata come
riuscita (`proxy/ha_client.py:186-196`, `task_engine.py:411-414`); un'azione fermata in attesa di
conferma umana produce una stringa che non comincia per "saltato" e viene anch'essa registrata come
riuscita, con il task che chiude "eseguito" mentre l'azione potrebbe non partire mai. Secondo: la
ricorrenza esiste davvero solo per le finestre orarie; per gli altri inneschi un task non "a colpo
singolo" torna in attesa ma nessun nuovo lavoro viene registrato, e resta in attesa per sempre
(`task_engine.py:430-433`). Terzo: il passaggio in esecuzione non viene salvato su disco, quindi se
il processo muore a meta' il task viene rischedulato come se non fosse mai partito e le azioni gia'
eseguite verrebbero rifatte (`task_engine.py:370-371,434`).

Sul riavvio, infine, il ciclo di lettura del file e' avvolto in un unico blocco protetto: un solo
record corrotto interrompe il caricamento e fa sparire tutti i task che lo seguono nel file, con un
solo messaggio di errore nei log (`task_engine.py:208-242`). La pulizia oraria rimuove i task conclusi
dopo sette giorni e non tocca mai quelli non conclusi (`task_engine.py:246-274`).

---

### Le proposte: la coda di approvazione umana

#### A cosa serve

E' il punto in cui HIRIS si ferma e chiede. Quando un modello vuole scrivere una configurazione su
Home Assistant o creare un Agentbot, non scrive: deposita una proposta in attesa su un archivio
dedicato (`proxy/proposal_store.py:17-32`). L'utente la vede in tre posti — il pannello Proposte della
chat, la pagina "Proposte automazione" del pannello di configurazione, e un'anteprima nella Dashboard —
e con "Attiva" fa avvenire la scrittura reale.

#### Da dove nascono

Le origini sono cinque: il modello in chat, con lo strumento che propone un'automazione
(`tools/proposal_tools.py:24-81`) o una plancia Lovelace (`tools/dashboard_tools.py:44-135`); l'API di
esecuzione, dove la creazione di configurazioni viene sempre intercettata e trasformata in proposta
invece di essere eseguita (`handlers_execute.py:295-311`); la Sentinella e gli Agentbot, che nel ramo
"proponi" confezionano uno script (`watcher/sentinel_proposal.py:70-131`); e la revisione olistica del
Brain, che propone automazioni (`server.py:2309-2337`).

Un'asimmetria da conoscere: la stessa creazione di script e scene, chiamata **dalla chat**, non passa
dalla coda — scrive subito su Home Assistant (`dispatcher.py:637-655`, `config_tools.py:104-111`). La
coda si applica al percorso dell'API di esecuzione, non a quello conversazionale.

La validazione alla creazione esiste solo per le automazioni: forma dell'oggetto, presenza di inneschi
e azioni, forma dell'identificativo (`proposal_tools.py:114-160`). Per le proposte di Agentbot la
configurazione viene salvata cosi' com'e' e la sua validita' si scopre solo al momento
dell'approvazione.

#### L'approvazione

Premendo "Attiva" si chiede una conferma nativa del browser, poi il server esegue il percorso adatto al
tipo (`handlers_proposals.py:36-123`):

- **Automazione**: viene scritta in Home Assistant e ricaricata. Se la proposta non porta un
  identificativo ma porta un nome che coincide in modo univoco con quello di un'automazione esistente,
  quella automazione viene **sovrascritta** (`proxy/ha_client.py:225-233,289-291`). Nessuna delle tre
  viste avvisa di questa possibilita' e non esiste alcuno snapshot da cui tornare indietro.
- **Script e scene**: vengono create e ricaricate (`config_tools.py:101-152`).
- **Plance Lovelace**: in modalita' creazione si crea la plancia e si salva la configurazione, con
  cancellazione di ripiego se il salvataggio fallisce; in modalita' sostituzione si legge **prima** la
  configurazione attuale, la si salva su disco come snapshot, e solo se lo snapshot e' andato a buon
  fine si sovrascrive (`config_tools.py:123-143`). Se la plancia non e' leggibile, l'operazione viene
  annullata senza toccare nulla.
- **Agentbot**: si toglie sempre l'identificativo, cosi' l'approvazione crea sempre un oggetto nuovo e
  non ne sovrascrive uno esistente; si valida, si salva, si registrano i lavori pianificati e si
  aggiorna la cache viva (`handlers_proposals.py:82-109`). L'Agentbot e' attivo dal momento
  dell'approvazione.

Esiste anche un ramo per i tipi non gestiti: la proposta viene marcata come applicata e la risposta e'
positiva, senza che nulla venga scritto in Home Assistant; l'unico segnale e' un avviso nei log
(`handlers_proposals.py:110-123`). A schermo l'utente vede "Proposta attivata", indistinguibile da
un'attivazione reale.

#### Rifiuto, invecchiamento, ripristino

Il rifiuto chiude la proposta in modo definitivo: non esiste alcun modo di riportarla in attesa
(`proposal_store.py:155-163`). Un lavoro orario archivia le proposte rimaste in attesa da piu' di sette
giorni e cancella dal database quelle archiviate da piu' di trenta (`proposal_store.py:165-185`).
L'archiviazione avviene senza alcun avviso: la proposta semplicemente perde i pulsanti e cambia
scheda.

Per le sole plance sostituite esiste una rete: fino a tre snapshot per plancia
(`proxy/dashboard_backups.py:17,116`), e un pulsante di ripristino. La striscia di ripristino compare
in modo prominente se lo snapshot ha meno di ventiquattr'ore, altrimenti in una sezione "Versioni
precedenti" (`static/chat/proposals.js:111-135`). La conferma avvisa esplicitamente che le modifiche
fatte dopo la sostituzione andranno perse. Lo snapshot viene consumato solo se il ripristino riesce e
solo se la configurazione riapplicata coincide con quella dello snapshot, per non bruciare la rete di
un'altra sostituzione avvenuta nel frattempo (`dashboard_backups.py:132-192`). Questa funzione esiste
solo nel pannello della chat: non c'e' ne' nella pagina Proposte ne' nella Dashboard.

#### Cosa succede quando fallisce

Se Home Assistant rifiuta la scrittura, la risposta e' un 502 e la proposta **resta in attesa**, quindi
ritentabile (`handlers_proposals.py:53-57`). Se la proposta non e' piu' valida — gia' gestita altrove,
o archiviata — la risposta e' un 409 e l'utente legge "Non e' piu' valida: probabilmente e' gia' stata
gestita altrove…" (`static/config/proposals-core.js:51-53`). Se la configurazione di un Agentbot non
supera la validazione, la risposta e' un 400 con "La configurazione proposta non e' valida." e non c'e'
alcun modo di correggerla dall'interfaccia.

Nessuna notifica accompagna la **creazione** di una proposta. L'unica volta in cui l'utente viene
avvisato in tempo reale e' quando la Sentinella **non riesce** a confezionarla
(`sentinel_proposal.py:151-167`).

---

### Memoria e knowledge base

#### A cosa serve

E' cio' che HIRIS ricorda fra una conversazione e l'altra, e vive tutto in un unico archivio,
`/data/knowledge.db` (`brain/knowledge_store.py:12-40`). Dentro convivono cinque cose diverse: le
memorie di lavoro che un Chatbot salva su richiesta ("ricordati che…"); il "second brain di casa",
cioe' fatti, preferenze, scadenze, spese e note che passano da una coda di approvazione umana; i
documenti provenienti da un archivio documentale esterno, spezzati in frammenti; gli insight
settimanali calcolati dallo storico; e le tracce delle azioni autonome del Brain.

Tutto viene indicizzato per similarita' semantica, il che ha una conseguenza pesante: **senza un
motore di embedding configurato, la memoria non funziona**. Di fabbrica il provider e' vuoto e il
sistema costruisce un motore fittizio che restituisce un vettore vuoto
(`backends/embeddings.py:203-205,24-25`, `config.yaml:69`); poiche' quel motore e' comunque un oggetto,
gli strumenti di memoria restano esposti al modello e falliscono a ogni chiamata.

#### "Ricordati che…"

Il modello chiama lo strumento di salvataggio; il dispatcher gli passa il proprietario risolto
dall'identita' della richiesta (o `home`) e l'identificativo del Chatbot (`dispatcher.py:596-603`). Il
contenuto non puo' superare i mille caratteri. Si calcola l'embedding e — questo e' il punto — se non
si riesce a calcolarlo **non si scrive nulla**, e il modello riceve un messaggio esplicito: il ricordo
non sarebbe piu' ritrovabile (`tools/memory_tools.py:123-162`). Se la retention e' configurata, il
ricordo nasce con una data di scadenza.

L'utente vede solo la frase del modello. Il pannello "Memoria" non mostra questo ricordo: quella coda
elenca esclusivamente cio' che e' in attesa di approvazione (`handlers_knowledge.py:36`). Non esiste
nessuna schermata che elenchi le memorie gia' salvate.

Il richiamo puo' avvenire in due modi. Esplicito, quando il modello chiede di cercare fra i ricordi:
si prendono al massimo venti risultati dello stesso proprietario e dello stesso Chatbot
(`memory_tools.py:180-212`). Automatico, a ogni singolo messaggio di chat: si calcola l'embedding della
domanda, si cercano i cinque ricordi piu' simili e li si mette in testa al contesto, preceduti da un
avviso che li marca come informazione e non come istruzione (`handlers_chat.py:272-305`). Non c'e'
nessuna soglia di similarita': i primi risultati entrano anche con punteggio zero, e dopo un cambio del
modello di embedding i vecchi ricordi continuano a essere restituiti con punteggio nullo, senza alcun
segnale (`backends/embeddings.py:219-227`).

#### La coda di approvazione

Quando il modello — dalla chat o dal gateway — vuole scrivere nel second brain di casa, la riga nasce in
attesa (`tools/knowledge_tools.py:107-122`). L'utente la trova nel pannello "Memoria", che si aggiorna
da solo ogni trenta secondi e mostra un contatore sulla voce di navigazione
(`static/chat/knowledge.js:287-305`). Ogni card mostra il tipo tradotto, la data, il titolo, il
contenuto, la scadenza, l'importo, la categoria e la provenienza, con due pulsanti: Approva e Scarta.
Se l'elemento e' marcato come sensibile, il testo non entra nemmeno nel DOM finche' non lo si chiede
esplicitamente (`knowledge.js:109-118,198-207`).

All'approvazione, se manca l'embedding lo si calcola in quel momento; se non ci si riesce non si
modifica niente e l'utente legge "La memoria non e' raggiungibile in questo momento"
(`handlers_knowledge.py:66-91`). Lo scarto cancella la riga e tutte le sue dipendenze — collegamenti e
frammenti di documento (`knowledge_store.py:208-226`).

Vale la pena sapere che l'endpoint di scarto non filtra sullo stato: chiamato direttamente cancella
qualunque riga leggibile dal chiamante, compresi documenti, insight e tracce del Brain, tutti scritti
con proprietario `home` (`handlers_knowledge.py:94-108`, `knowledge_store.py:228-234`). L'interfaccia
lo offre solo sulle righe in attesa, ma la regola non e' imposta dal server.

#### Documenti, insight, tracce

Se e' configurato un collegamento a un archivio documentale, un lavoro periodico scarica i documenti
etichettati, ne prende il testo riconosciuto, lo spezza in frammenti, calcola **tutti** gli embedding
prima di scrivere qualsiasi cosa, e solo allora salva (`brain/mayan_ingest.py:10-51`). Se la scrittura
dei frammenti fallisce, l'elemento viene rimosso. Questi documenti non passano dalla coda di
approvazione e non sono visibili in nessuna schermata.

Ogni notte alle 04:00 il digest storico riscrive un insight per entita' (`history_digest.py:110-147`);
qui, a differenza del resto dell'area, l'insight viene scritto anche senza vettore, quindi risulta
approvato ma non sara' mai ritrovabile dalla ricerca. Le tracce delle azioni autonome del Brain, invece,
seguono la regola rigorosa: se non si puo' calcolare il vettore non si scrive nulla
(`brain/brain_trace.py:32-49`), il che significa che con la configurazione di fabbrica le azioni
autonome avvengono senza lasciare traccia richiamabile.

#### Riservatezza

Il second brain distingue i contenuti "normali" da quelli sensibili. Quando il modello cerca e il
backend e' in cloud, i contenuti sensibili vengono pseudonimizzati: si sostituiscono i soli schemi
riconosciuti — IBAN, codice fiscale, numero di carta, email, telefono italiano
(`brain/privacy.py:75-81`) — registrando la corrispondenza in una mappa valida solo per quello scambio;
se il pseudonimizzatore non c'e', l'intero contenuto viene sostituito con "[contenuto sensibile non
disponibile]" (`tools/knowledge_tools.py:180-196`). Dopo la risposta, i segnaposto vengono riespansi
usando solo la mappa di quello scambio (`handlers_chat.py:453-458`). Nel percorso in streaming la
riespansione avviene solo sul testo accumulato e salvato: a schermo i segnaposto restano visibili
(`handlers_chat.py:395-405`).

Le stesse impostazioni si comportano in modo diverso su superfici diverse. Il resoconto quotidiano
nasconde i contenuti sensibili se la catena non e' interamente locale (`dispatcher.py:739`); la ricerca
nel second brain non applica quella stessa congiunzione e manda il contenuto pseudonimizzato
(`dispatcher.py:698-707`). E l'iniezione automatica dei ricordi in chat non legge affatto la
configurazione di accesso alla conoscenza: interroga sempre le sole memorie
(`handlers_chat.py:283-289`).

#### Scadenze e pulizia

Alle 03:00 vengono cancellate le memorie per-Chatbot scadute (`knowledge_store.py:438-451`). Tutto il
resto — knowledge approvata, documenti, insight, tracce — non scade e non viene mai potato. Un elemento
rimasto in attesa e mai approvato resta in coda per sempre. La cancellazione di un Chatbot, invece,
cancella tutte le sue memorie, di qualunque utente fossero (`handlers_chatbots.py:210-215`), senza che
nulla lo avvisi nell'interfaccia.

Le scadenze registrate come tali alimentano il resoconto delle 08:00 e i solleciti ogni sei ore, ma
solo quelle con proprietario `home`: cio' che un utente identificato ha salvato non entra mai in quelle
notifiche, che sono per costruzione un annuncio di casa (`briefing.py:62-69`, `reminders.py:89-93`).

#### Cosa succede quando fallisce

Il tratto distintivo di quest'area e' che i fallimenti della memoria sono quasi sempre **espliciti verso
il modello** e **muti verso l'utente**. Il modello riceve messaggi che distinguono "non ho trovato
nulla" da "non ho potuto controllare" (`memory_tools.py:187-194`). L'utente, invece, quando l'iniezione
automatica dei ricordi fallisce non vede nulla: la conversazione prosegue come se il ricordo non
esistesse (`handlers_chat.py:304-305`). L'unica eccezione e' la coda di approvazione, dove "non ho
potuto leggere la coda" resta distinto da "la coda e' vuota" (`handlers_knowledge.py:27-29`,
`knowledge.js:161-169`).

---

### Punti in cui due letture del codice divergono

Le mappe da cui questa sezione e' tratta sono state prodotte da agenti diversi che hanno letto lo stesso
codice. In un punto arrivano a conclusioni opposte, e la divergenza va registrata come tale.

**Il "Test Run" di un Chatbot dall'editor.** Il pulsante esiste nell'editor e chiama
`POST /api/chatbots/{id}/run`, che porta a `chatbot_engine.py` intorno alle righe 466-541.

- La mappa dell'area *chat* descrive un percorso funzionante: la persona viene recuperata (senza
  controllare se sia abilitata), si salta l'esecuzione se un'altra e' gia' in corso o se la persona e'
  in pausa per limite di richieste, si compone il prompt, si chiama il modello con un messaggio
  sintetico `[Agent trigger: unknown]`, e al ritorno si registrano gli strumenti chiamati, i token
  consumati e una riga nel registro delle esecuzioni; la pagina mostra "ESEGUITO" e il testo
  (`chatbot_engine.py:483-541,557-576`, `static/config/chatbot-editor.js:747`).
- La mappa dell'area *catalogo degli strumenti* sostiene invece che la chiamata non puo' riuscire: fra i
  parametri passati al modello c'e' `agent_id=chatbot.id`, che nessuno dei due runner accetta e che il
  router inoltra dopo aver rimosso soltanto `mode`; ogni backend solleva un errore di firma, il router
  lo scambia per un guasto del fornitore e passa al successivo, e all'utente arriva "Tutti i provider AI
  non disponibili. Riprova tra poco." (`chatbot_engine.py:520-541`, `llm_router.py:215-234`).

Le due letture citano gli stessi intervalli di righe e sono incompatibili: o il Test Run restituisce il
testo del modello, o restituisce sempre un messaggio di indisponibilita' del fornitore. Nessuno dei due
agenti ha eseguito il codice — entrambi lo dichiarano fra le proprie incertezze. La contraddizione
resta aperta e va risolta eseguendo il pulsante.

**Divergenze minori di riferimento.** Le stesse entita' sono citate con estremi di riga leggermente
diversi da mappe diverse: l'insieme degli strumenti di sola valutazione compare come
`claude_runner.py:225-253` in due mappe e come `claude_runner.py:225-244` in quella degli Agentbot; la
chiamata al modello dal percorso di chat compare come `handlers_chat.py:419` in una mappa e come
`handlers_chat.py:424` in un'altra. Sono scostamenti di pochi righe che non cambiano il comportamento
descritto — su cui le tre mappe concordano — ma indicano che i riferimenti puntuali vanno riverificati
prima di essere usati come citazioni definitive. Vale la pena notare che una delle mappe segnala lo
stesso fenomeno **dentro il codice**: un commento in `watcher/agentbot_runner.py:29-36` rimanda a righe
di `claude_runner.py` che nel file attuale contengono altro.

---

# 3. Piattaforma, sicurezza e integrazione

Questa sezione racconta la parte di HIRIS che non si vede: il meccanismo che decide se un comando
verso la casa parte o si ferma, la coda in cui i comandi restano appesi finche' un umano non dice
di si', la porta da cui un Claude esterno entra a comandare, il tessuto connettivo verso Home
Assistant, e infine il guscio HTTP e le opzioni dell'add-on che tengono insieme tutto il resto.

---

## Il semaforo: come HIRIS decide se un comando parte

### A cosa serve

Il semaforo e' il punto in cui HIRIS stabilisce, per ogni singola azione verso la casa, se puo'
partire da sola, se serve un gesto umano, o se e' vietata. E' l'unico posto in cui l'utente
dichiara quanta autonomia concede al sistema.

Il funzionamento e' quello di un'etichetta a quattro livelli — verde, giallo, rosso, spenta —
applicata a categorie di dispositivi (luci, clima, media, e cosi' via: la pagina ne mostra 22,
`handlers_gateway_policy.py:302-307`) e, se si vuole, a singole entita' con un override che batte
sempre il livello della categoria (`handlers_gateway_policy.py:158-164`). Verde significa
"fallo"; giallo e rosso significano "chiedimelo prima"; spenta significa "non toccare".

Sopra i quattro livelli sta una regola che nessun livello puo' sbloccare: una denylist assoluta di
domini considerati pericolosi — serrature, pannelli d'allarme, tapparelle, sirene e la voce
`garage_door` (`semaphore.py:79-81`). Su quei domini il verdetto arriva prima ancora di leggere il
tier (`semaphore.py:141-146`): il comando viene negato con "Dominio pericoloso bloccato dalla
denylist." Marcare quel dominio verde non lo rende eseguibile — lo rende soltanto verde in una
schermata.

Vale la pena registrare una stranezza dichiarata dal materiale: `garage_door` non corrisponde a un
dominio reale di Home Assistant e non compare fra le categorie configurabili
(`handlers_gateway_policy.py:50-73`); l'unico modo per farlo scattare sarebbe un `entity_id` che
inizia con `garage_door.` — e in `briefing.py:40` la stessa parola e' usata come device_class, che
e' un'altra cosa.

### Da dove si entra

Da una sola pagina: `#/gateway`, intitolata "Accessi Gateway" e sottotitolata "Cosa Claude (via il
gateway MCP) puo' comandare in casa" (`gateway-route.js:234-236`). Il titolo dice meno del vero: gli
stessi livelli salvati da quella pagina governano la chat (`dispatcher.py:199-200`), i task
differiti (`task_engine.py:479-480`), la Sentinella e gli Agentbot
(`server.py:1893-1898, 2112-2117, 2198-2203`) e la scansione di salute (`server.py:2407-2410`).
Non e' la pagina del gateway: e' la pagina che imposta l'autonomia di tutto.

### Cosa succede passo per passo

Quando l'utente preme Salva, il browser invia livelli, override per entita' e impostazioni
(`gateway-route.js:344-356`). Il server filtra le categorie a quelle note e ai quattro livelli
validi, pretende che gli override per entita' abbiano forma di `dominio.entita`, e valida il
servizio di notifica contro `^notify\.[A-Za-z0-9_]{1,64}$` (`handlers_gateway_policy.py:133-155`).
Poi scrive il file in modo atomico, su un temporaneo che viene rinominato
(`handlers_gateway_policy.py:97-102`), e infine ricalcola il perimetro operativo
(`handlers_gateway_policy.py:253-278`).

Il dettaglio che rende immediato il cambiamento e' che il perimetro non e' un file riletto ogni
volta: e' un dizionario vivo in memoria, e il salvataggio ne sostituisce il *contenuto* senza
sostituire l'oggetto (`handlers_gateway_policy.py:271-277`). Quello stesso oggetto e' tenuto per
riferimento dal dispatcher dei tool (`server.py:1653`) e dal motore dei task (`server.py:1333`):
un salvataggio, e chat, task, sentinella e gateway cambiano comportamento alla richiesta
successiva, senza riavvio.

All'atto di un comando, la sequenza e' sempre la stessa. Prima si normalizza il bersaglio, unendo
quello che sta in `data` con quello che sta in `target` (`dispatcher.py:422`). Poi si rifiuta
qualunque azione rivolta a un'area, a un dispositivo, a un'etichetta o a un piano invece che a
entita' nominate una per una (`dispatcher.py:433-435`): e' un rifiuto immediato, perche' su un
bersaglio di gruppo il semaforo non saprebbe quali entita' valutare. Poi si applica la regola vera
(`semaphore.py:123-160`): denylist dei domini pericolosi, quindi tier effettivo, dove fra piu'
entita' bersaglio vince la peggiore, e dove un dominio mai configurato vale "spenta". Solo dopo il
verdetto si applicano le liste di servizi ed entita' ammesse per quel chiamante
(`dispatcher.py:442-455`), e infine parte la chiamata verso Home Assistant con i dati normalizzati
(`dispatcher.py:456`).

### Cosa vede l'utente

Se e' verde, non vede nulla: la luce si accende. Se e' bloccato, in chat legge il messaggio del
semaforo — "Azione bloccata dal semaforo (off).", "Dominio pericoloso bloccato dalla denylist.",
"Azione a rischio: richiede conferma." Nella pagina Accessi Gateway, per ogni riga marcata
pericolosa compare un avviso che cambia col livello scelto (`gateway-route.js:45-51, 280-290`) e in
fondo un paragrafo riassuntivo (`gateway-route.js:329-335`).

C'e' anche un contatore, nell'editor Chatbot: chiedendo un riepilogo dell'autonomia
(`chatbot-editor.js:376-381`) l'utente vede una riga tipo "4 verde, 0 giallo, 0 rosso, 12 spenta,
2 sempre bloccato (dominio pericoloso), su 18 voci di scope". Il conteggio usa la stessa funzione
di tier dell'enforcement (`semaphore.py:109-120`), ma rilegge la policy dal disco invece che dal
dizionario vivo (`handlers_gateway_policy.py:344-353`), e i pattern con asterisco non possono mai
incrociare un override per singola entita': il conteggio mostra il livello del dominio anche quando
qualche entita' e' stata spenta a mano.

### Quando fallisce

Il caso piu' importante non e' un guasto, e' l'installazione appena fatta. Il perimetro costruito
all'avvio dalle variabili d'ambiente non contiene affatto le mappe dei tier
(`handlers_execute.py:76-91`), e se l'utente non ha mai salvato la pagina Accessi Gateway la
funzione che applica la policy salvata esce senza toccare nulla
(`handlers_gateway_policy.py:269-270`). Il risultato e' che ogni entita' risulta "spenta" e ogni
azione — di chat, di task, di sentinella — viene negata con "Azione bloccata dal semaforo (off.)"
(`semaphore.py:152-153`). Il sistema non e' rotto: e' chiuso, e non lo dice.

Se il file della policy diventa illeggibile, viene trattato come vuoto con un warning
(`handlers_gateway_policy.py:86-94`): il semaforo torna implicitamente a tutto spento.

### Tre implementazioni della stessa regola

Il modulo del semaforo si presenta come "la logica dei tier in un'unica funzione pura, applicata da
ogni superficie" (`semaphore.py:4-7`). Nei fatti le implementazioni sono tre. La funzione pura e'
usata dal dispatcher e dal motore dei task. L'esecutore della Sentinella importa la denylist e la
funzione di tier ma non chiama mai il gate, e decide da solo: verde piu' opzione accesa uguale
attua, verde o giallo uguale proponi, rosso o spento uguale allerta (`watcher/executor.py:19-27`).
E l'API del gateway fa un terzo pre-screening con una copia a mano del controllo sui domini
pericolosi (`handlers_execute.py:194-235`). Tre letture della stessa regola, che oggi coincidono
nell'esito ma vivono in tre posti.

Ci sono inoltre due scritture verso Home Assistant che dal percorso chat non passano affatto dal
semaforo: la creazione di script e scene (`dispatcher.py:637-655`) e la creazione di eventi di
calendario (`dispatcher.py:566-578`). Sulla prima l'unica rete e' un'istruzione testuale nel prompt
di sistema (`claude_runner.py:371-379`), che nessun controllo di codice fa rispettare.

---

## Quando serve un umano: la coda di approvazione e lo step-up

### A cosa serve

Giallo e rosso non bloccano: congelano. Il comando viene messo da parte esattamente com'era,
l'utente viene avvisato, e l'azione parte solo se qualcuno la sblocca entro cinque minuti.

### Il congelamento

Alla creazione, la richiesta riceve un identificativo casuale monouso, gli argomenti congelati cosi'
come sono, il tier, l'origine, un'etichetta del tipo `dominio.servizio`, una scadenza a 300 secondi
e lo stato "in attesa" (`handlers_gateway_pending.py:58-85`, TTL a riga 30). Nello stesso momento
il codice fa pulizia: butta via tutto cio' che non e' piu' in attesa o e' scaduto
(`handlers_gateway_pending.py:71-72`). La pulizia e' opportunistica — avviene solo alla creazione
della richiesta successiva — quindi in assenza di nuove richieste il file conserva a tempo
indeterminato le vecchie voci e con esse gli argomenti congelati.

C'e' una forzatura che vale la pena conoscere: se il tier calcolato e' giallo ma il dominio
richiesto, o il dominio di una qualunque entita' bersaglio, e' fra quelli pericolosi, il tier viene
riscritto a rosso prima di creare la richiesta (`handlers_execute.py:230-235`). La conseguenza
pratica e' che per serrature, allarme, tapparelle e sirene non esiste mai l'approvazione con un
tocco: quella e' riservata al giallo.

### Le tre vie per dire di si'

**Dalla inbox in HIRIS.** La pagina Accessi Gateway ospita una sezione "Da approvare"
(`gateway-route.js:103-140`) che elenca le richieste ancora vive, con un pallino colorato,
l'etichetta e un distintivo dell'origine. Il clic su Approva chiede prima una conferma del browser
(`gateway-route.js:186-189`), poi chiama il server. Qui c'e' l'unica guardia davvero stretta
dell'intero sistema: la richiesta viene accettata solo se l'autenticazione e' avvenuta come
"ingress" (o come modalita' di sviluppo senza token) — chi presenta soltanto il token del gateway
riceve 403 (`handlers_gateway_pending.py:292-311`). Il motivo e' dichiarato nel codice: se lo
stesso token bastasse anche ad approvare, un gateway compromesso potrebbe creare una richiesta
rossa e auto-approvarsela.

**Con un tocco sulla notifica del telefono.** Quando l'utente preme Approva sulla notifica, Home
Assistant emette un evento che HIRIS ascolta sul WebSocket (`ha_client.py:921`) e instrada al
gestore (`server.py:1243-1246`). Il gestore accetta solo azioni della forma
`HIRIS_GW:approve|reject:<identificativo>` (`handlers_gateway_pending.py:182-187`) e non verifica in
alcun modo quale utente o quale dispositivo abbia generato l'evento: l'unica prova e' la conoscenza
dell'identificativo. Questo percorso non attraversa nessun endpoint HTTP autenticato, quindi la
guardia descritta sopra non lo tocca.

**Con un codice di sei cifre dettato in chat.** E' il percorso dello step-up, riservato alle azioni
richieste dalla chat. Il gate restituisce "serve conferma", e il sistema prova a mandare all'utente
una notifica privata contenente l'azione, le entita' bersaglio e un codice
(`server.py:180-205, 415-467`). Se l'utente detta il codice, il modello chiama lo strumento di
conferma; il codice viene validato come esattamente sei cifre ASCII prima di qualunque confronto
(`server.py:394-396`), il confronto e' a tempo costante, e dopo tre tentativi sbagliati la richiesta
viene rifiutata per sempre (`handlers_gateway_pending.py:141-145`). Prima di generare un nuovo
codice il sistema invalida ogni altro codice vivo dello stesso utente
(`handlers_gateway_pending.py:156-179`), cosi' ce n'e' al massimo uno per volta. Il codice viene
oscurato nel flusso verso il client (`handlers_chat.py:477-482`) e nei log del dispatcher
(`dispatcher.py:251-252`).

### Cosa succede all'approvazione

In tutti e tre i casi l'identificativo viene consumato una volta sola
(`handlers_gateway_pending.py:107-117`) e il comando congelato viene rispedito al dispatcher con il
flag "gia' confermato" (`handlers_gateway_pending.py:334-353`). Quel flag salta l'intero blocco del
gate (`dispatcher.py:427`): niente guardia sui bersagli di gruppo, niente tier, niente denylist dei
domini pericolosi. E' deliberato e dichiarato (`dispatcher.py:423-426`): il contenimento non viene
piu' dalla regola, viene dal fatto che gli argomenti sono congelati. Vale la pena notare che il
codice dichiara di restringere la whitelist "all'azione approvata, nulla di piu' ampio"
(`handlers_gateway_pending.py:334-343`) mentre in concreto passa nessun filtro di entita' e
l'intero dominio come filtro di servizi (riga 346).

### Cosa vede l'utente

Per una richiesta gialla: una notifica intitolata "HIRIS - richiesta da Claude" con il testo
"Claude chiede: `dominio.servizio`. Approva o nega dalla notifica.", i pulsanti Approva e Nega, e un
pulsante "Apri HIRIS" se il percorso di ingress e' noto (`handlers_gateway_pending.py:190-203,
232-254`). Per una rossa, lo stesso testo ma senza pulsanti e con l'invito a confermare
manualmente. Per lo step-up di chat: in chat il messaggio "Ho bisogno della tua conferma: tocca
Conferma nella notifica sul telefono, oppure dimmi il codice che ti ho inviato"
(`dispatcher.py:215-219`), e sul telefono la notifica con il codice.

Se qualcosa va storto durante l'approvazione dalla inbox, l'utente vede un avviso con un messaggio
derivato dallo stato HTTP (`gateway-route.js:154-175`), incluso il caso piu' scomodo: "Comando
approvato ma NON eseguito su Home Assistant", con la precisazione che l'approvazione e' gia' stata
spesa e non e' riprovabile.

### Quando fallisce

La scadenza e' silenziosa: passati i cinque minuti la voce sparisce dalla lista, nessuna notifica
avvisa che l'occasione e' passata, e la riga verra' cancellata dal file alla creazione successiva.

Se la notifica non parte, il comando resta comunque in coda, ma la risposta al modello dice lo
stesso "Azione in attesa di approvazione - notifica inviata."
(`handlers_execute.py:246-252`), perche' il chiamante non guarda l'esito dell'invio.

Sul percorso del tocco sulla notifica l'esito viene proprio scartato (`server.py:1245`,
`handlers_gateway_pending.py:285-286`): un comando approvato dal telefono che poi fallisce su Home
Assistant non produce nessun segnale, ne' notifica ne' riga in inbox. Il percorso via interfaccia,
invece, quell'errore lo legge e lo dice.

Infine, lo step-up di chat ha due guardie che lo chiudono spesso. La prima e' l'identita': se la
richiesta non porta un utente riconosciuto (il valore di ripiego e' `home`), la funzione ritorna
subito senza creare nulla (`server.py:429-430`), e il modello puo' solo dire "Azione a rischio:
richiede conferma." senza offrire alcun modo di confermare (`dispatcher.py:213-214, 220`). La
seconda e' il canale: il codice pretende una voce esplicita nella mappa utente-servizio di notifica,
e rifiuta espressamente il servizio globale e le notifiche persistenti, perche' un codice segreto
non deve finire su una dashboard condivisa (`handlers_gateway_policy.py:228-250`). Il materiale
verifica che nessuna interfaccia scrive quella mappa: la pagina Accessi Gateway invia soltanto il
servizio di notifica globale (`gateway-route.js:344-352`). Senza una modifica a mano del file su
disco, lo step-up fallisce chiuso sempre.

Vale la pena registrare l'asimmetria: la stessa meta' del codice che giudica il canale globale
inadatto anche solo a portare un codice, lo usa per recapitare l'approvazione con un tocco delle
richieste gialle del gateway (`handlers_gateway_pending.py:226-227`).

---

## Il gateway MCP: la porta da cui Claude comanda la casa

### A cosa serve

E' la superficie con cui un Claude esterno — e la chat in-add-on quando gira via abbonamento — usa
HIRIS senza passare da un modello interno. Non e' una API generica: e' un elenco chiuso di strumenti
inoltrati a un unico endpoint dichiaratamente non-LLM, `POST /api/execute`
(`handlers_execute.py:147`, rotta `server.py:2839`).

### Chi puo' entrare

Solo chi presenta il token interno. Il controllo e' fatto due volte: una dal middleware generale e
una, indipendente, dentro l'handler, che fallisce chiuso se il token non e' configurato
(`handlers_execute.py:129-149`). L'interfaccia utente non basta: anche una richiesta gia'
riconosciuta come proveniente dall'ingress viene rifiutata se non porta il token.

Dentro il container esiste anche un secondo server, un server MCP in ascolto solo sul loopback
(`server.py:1108-1133`, bind a riga 1132). Quel server non ha autenticazione propria: chiunque
raggiunga il loopback lo puo' usare. L'unico gate previsto e' un interruttore d'emergenza
(`mcp/guard.py:20-25`) che nessun endpoint e nessuna pagina accende o spegne — il codice stesso lo
ammette a mezza voce ("nessun endpoint HTTP viene aggiunto qui", `server.py:1114-1120`). E' un
interruttore senza leva. Il registro di controllo che quel guard tiene in memoria — 200 voci con
nome dello strumento, esito e latenza (`mcp/guard.py:16-28`) — non e' letto da nessuno e si perde a
ogni riavvio.

### Le letture: la denylist di lettura

Il perimetro di scrittura e' il semaforo. Il perimetro di *lettura* e' una cosa diversa e con scopo
opposto: un elenco di entita' che non devono mai uscire verso il gateway remoto. Se l'opzione non e'
stata toccata, il valore di partenza e' protettivo e copre serrature, allarme, telecamere, persone e
tracciatori di dispositivo (`read_denylist.py:100-110`); se e' impostata a stringa vuota, l'elenco e'
vuoto. Lo script di avvio distingue i due casi guardando se la chiave esiste davvero nelle opzioni
(`run.sh:34-36`).

Il filtro agisce due volte. In ingresso, ogni valore degli argomenti che abbia forma di identificatore
di entita' viene confrontato con l'elenco, e se ne trova uno coperto la richiesta viene rifiutata con
403 e l'elenco delle entita' negate (`read_denylist.py:127-148`, `handlers_execute.py:335-342`). In
uscita, la risposta viene potata da un potatore specifico per quel tipo di strumento
(`read_denylist.py:395-405`): se il potatore ha tolto qualcosa, la risposta lo dichiara con un campo
che indica quanti elementi sono mostrati su quanti totali. Se la forma della risposta non e'
riconoscibile — una voce d'elenco senza identificatore, una mappa di aree con valori che non sono
liste — la risposta *intera* viene bloccata (`read_denylist.py:429-440`). E' un fail-closed: meglio
non dire nulla che dire troppo.

Due strumenti non vengono potati parzialmente ma tutto-o-niente: la configurazione di un'automazione
che nomini un'entita' coperta viene bloccata, e un task che la nomini cade per intero
(`read_denylist.py:321-361`). Un limite dichiarato: il recupero di conoscenza passa invariato,
perche' una denylist per entita' non intercetta il testo libero (`read_denylist.py:364-389`).

La chat in-add-on e' esentata di proposito. Il riconoscimento avviene con un segreto di processo
generato nuovo a ogni avvio e mai scritto su disco (`server.py:1194`), confrontato a tempo costante
con un'intestazione della richiesta (`handlers_execute.py:107-126`). Se il segreto manca o non
combacia, la chat viene trattata come remota e potata: si sbaglia dalla parte della prudenza.

Resta il fatto che la denylist vale solo dentro questo endpoint: la chat che usa direttamente il
dispatcher non ci passa mai, e un chatbot senza perimetro legge senza filtri serrature, telecamere e
tracciatori.

### Le scritture: cosa il gateway puo' e non puo' fare

Un comando verso la casa segue esattamente il percorso descritto nella sezione sul semaforo, con un
pre-screening in piu' fatto qui: bersaglio di gruppo rifiutato subito, entita' spenta rifiutata
subito, tier calcolato come il peggiore fra i bersagli (`handlers_execute.py:178-221`).

La creazione di task e' filtrata a monte: ogni azione di primo livello che chiami un servizio deve
avere entita' nominate e tutte verdi, altrimenti il task viene rifiutato con un messaggio
esplicativo (`handlers_execute.py:271-293`). Il filtro pero' non e' ricorsivo: le azioni di un task
annidato non vengono ispezionate, cosa che il codice dichiara apertamente
(`handlers_execute.py:255-270`, `mcp/tiers.py:71-92`). Il modello puo' quindi ricevere "task creato"
per un task che allo scatto non attuera' nulla, perche' ogni azione ripassera' comunque dal semaforo
(`task_engine.py:477`).

La creazione di configurazione in Home Assistant si comporta in due modi opposti secondo la porta
d'ingresso. Dal gateway non viene mai eseguita: diventa una proposta da rivedere nella pagina
Proposte, e la risposta e' "in attesa di approvazione" (`handlers_execute.py:295-311`). Dalla chat,
lo stesso nome di strumento scrive subito su Home Assistant (`dispatcher.py:637-655`). Stesso nome,
due comportamenti.

Due strumenti sfuggono al perimetro. L'invio di notifiche e' sempre esposto, fuori da ogni policy
(`handlers_execute.py:36`): chiunque abbia il token puo' notificare l'utente anche con il semaforo
interamente spento. E l'annullamento di un task non filtra per chi l'ha creato
(`dispatcher.py:509-514`, `task_tools.py:113-117`): il gateway puo' annullare qualunque task in
attesa, compresi quelli creati dall'utente dentro HIRIS.

### La chat via abbonamento

Quando l'abbonamento e' attivo e il token corrispondente presente, HIRIS scrive una piccola
configurazione MCP in `/tmp` con permessi ristretti (`agent/runner.py:47-65`) e lancia il CLI
`claude` limitandolo agli strumenti HIRIS (`agent/runner.py:24-36, 69-79`). Il modello passa dal
server MCP loopback, che rientra su `/api/execute` marcando le richieste come chat locale
(`handlers_execute.py:328`). Due conseguenze pratiche: le letture non vengono potate, e l'allowlist
del CLI e' piu' stretta di quella del server MCP — non include la cronologia eventi ne' le
segnalazioni (`agent/runner.py:26-33`), che quindi da quella chat non sono chiamabili.

### Quando fallisce

Se il token interno non e' configurato — ed e' il valore di fabbrica, `config.yaml:75` — ogni
chiamata riceve 401, incluse quelle del server MCP loopback che passa dallo stesso endpoint
(`mcp/local_client.py:47-51`). Il log di avvio dice comunque che il server MCP e' partito. Il
sintomo, per l'utente, e' un assistente che non riesce ne' a leggere ne' ad agire, senza
spiegazione.

Se la porta del server MCP e' occupata, il fallimento viene contenuto e loggato senza uccidere
l'add-on (`server.py:1070-1087`), e gli strumenti semplicemente non rispondono.

Se il file della coda diventa illeggibile, viene trattato come vuoto con un warning
(`handlers_gateway_pending.py:39-47`): ogni richiesta in volo diventa invisibile e non piu'
approvabile, senza che nulla lo dichiari.

---

## L'integrazione con Home Assistant

### A cosa serve

E' lo strato che rende HIRIS capace di sapere com'e' la casa e di cambiarla. Legge lo stato via
API REST, lo tiene aggiornato in tempo reale via WebSocket, ne mantiene un inventario in memoria e
uno snapshot di salute su disco, scrive configurazione (automazioni, script, scene, plance) solo
dietro approvazione, e parla all'utente con notifiche che sanno riaprire HIRIS.

### L'avvio

All'accensione l'add-on costruisce il client verso Home Assistant usando l'indirizzo interno del
Supervisor e il token del Supervisor (`server.py:1195-1203`). Poi copia la card Lovelace dentro la
cartella di configurazione di Home Assistant (`server.py:153-177`), interroga il Supervisor per
sapere il proprio indirizzo di ingress e lo scrive in un file accanto alla card
(`server.py:221-264`), e registra la card fra le risorse Lovelace cancellando le proprie versioni
vecchie (`server.py:291-381`).

Poi legge tutto lo stato della casa e lo riduce a una forma minimale — identificatore, stato, nome,
unita', dominio, classe (`entity_cache.py:77-94`) — alzando la bandiera "caricato" solo a lettura
completata (`entity_cache.py:121-134`). Carica il registro delle aree con due chiamate WebSocket
(`entity_cache.py:182-204`). Registra i propri ascoltatori e, quando il motore parte, apre il
WebSocket (`chatbot_engine.py:128-133`).

Ogni singolo passaggio di questa catena, se fallisce, produce un log e si prosegue. Se non trova la
cartella di configurazione di Home Assistant, la card non viene copiata e l'errore annuncia
esplicitamente che l'indirizzo dara' 404 (`server.py:159-167`). Se il Supervisor e' irraggiungibile,
il percorso di ingress resta ignoto e — conseguenza silenziosa — tutti i collegamenti profondi delle
notifiche vengono omessi (`notify_tools.py:41-43`). Se l'inventario non si carica, i quattro
strumenti che lo leggono rispondono con un messaggio che distingue "non ho potuto guardare" da "la
casa e' vuota" (`entity_cache.py:25-29`), e un lavoro periodico ritenta ogni due minuti
(`server.py:1026-1067`).

### Il flusso continuo

Il WebSocket sottoscrive tre tipi di evento: i cambi di stato, la creazione di nuove entita' e le
azioni sui pulsanti delle notifiche (`ha_client.py:919-921`). Cinque ascoltatori ricevono i cambi
di stato in sequenza: la cache, il monitor di salute, la cattura dello storico, il Guardian della
Sentinella e il sorvegliante degli arrivi (`server.py:1224, 1480, 1940-1942, 2517-2519`;
`health_monitor.py:135`). Ognuno e' avvolto singolarmente, cosi' che uno che va in errore non fermi
gli altri (`ha_client.py:931-951`).

C'e' un punto in cui questo tessuto puo' morire in silenzio. Se l'autenticazione del WebSocket non
riesce, la funzione registra un errore e ritorna, e il ciclo non riparte mai
(`ha_client.py:915-917`) — a differenza di una disconnessione qualunque, che riprova dopo dieci
secondi (`ha_client.py:954-956`). Da quel momento cache, salute, storico, Sentinella e — cosa piu'
importante — la ricezione dei tocchi Approva/Nega sono fermi, mentre tutti gli strumenti continuano
a rispondere dalla fotografia congelata senza dichiararlo.

Un secondo punto di deriva: la cache non toglie mai nulla. L'evento di rimozione viene ignorato
perche' arriva senza nuovo stato (`entity_cache.py:137-139`), quindi un'entita' cancellata da Home
Assistant resta nell'inventario fino al riavvio dell'add-on. Lo stesso evento e' invece letto dal
monitor di salute come un rientro, e la voce esce dalla lista dei non disponibili
(`health_monitor.py:229-234`): due componenti leggono lo stesso fatto in due modi opposti.

### La salute della casa

Il monitor rilegge tutto ogni trenta minuti e ricalcola le entita' non disponibili, poi tenta in
sequenza — ognuna indipendente — il registro degli errori, le integrazioni in stato anomalo, le
informazioni di sistema, gli aggiornamenti disponibili e la diagnostica interna
(`health_monitor.py:157-187`). Se c'e' il token del Supervisor aggiunge add-on, host e aggiornamenti
di sistema, e scrive quella sezione solo se ha davvero qualcosa dentro
(`health_monitor.py:192-210`). Tutto finisce in un file, riscritto anche a ogni singolo cambio di
stato della casa (`health_monitor.py:261-266`).

Il difetto e' che una lettura fallita non svuota la sezione: mantiene il valore precedente, e
l'unico segnale e' la data di aggiornamento, che viene aggiornata comunque
(`health_monitor.py:147`). Lo snapshot non distingue un dato fresco da uno vecchio.

Sopra al monitor gira una scansione che esegue otto controlli — entita' non disponibili, batterie
scariche, automazioni rotte, domini pericolosi lasciati verdi, entita' senza area, add-on fermi,
spazio disco, aggiornamenti — e li riconcilia in un archivio di segnalazioni
(`health_scan.py:285-296`). Per le sole gravi e nuove manda una notifica push, al massimo cinque per
scansione e con un silenzio di alcune ore sullo stesso problema, poi un riepilogo unico
(`health_scan.py:150-213`). Se l'invio dichiara di non essere riuscito, la segnalazione non viene
marcata come notificata e si ritenta al giro dopo (`health_scan.py:187-198`).

Su uno di quegli otto controlli il materiale registra un disallineamento: il titolo dice "dominio
pericoloso eseguibile senza conferma" (`health_checks.py:222-224`), ma un dominio pericoloso
impostato verde non e' eseguibile affatto sui percorsi non confermati, perche' il verdetto arriva
prima di leggere il tier. La segnalazione descrive un rischio che il codice non ha.

### Le scritture

Un'automazione nasce sempre come proposta (`dispatcher.py:616-636`) e viene scritta solo quando
l'utente preme Applica (`handlers_proposals.py:48-59`). Prima di scrivere si valida la forma —
servono innesco e azione, oppure un blueprint (`ha_client.py:214-216`) — e si risolve
l'identificativo con una cura notevole: se la lettura di Home Assistant fallisce, si distingue "non
ho potuto controllare" da "non esiste" e in nessuno dei due casi si scrive
(`ha_client.py:250-284`). Il ripiego sul nome amichevole vale solo se non e' stato dichiarato alcun
identificativo e solo se il nome corrisponde a una sola automazione
(`ha_client.py:285-288, 319-335`); altrimenti si conia un identificativo nuovo.

Dopo la scrittura si ricarica, perche' l'automazione sia attiva subito (`ha_client.py:311-316`). Se
il ricaricamento fallisce, pero', la funzione ritorna comunque un successo (`ha_client.py:312-317`):
l'utente legge "creata" su un'automazione che restera' inerte fino al riavvio di Home Assistant.

Le plance Lovelace hanno la protezione piu' accurata di tutto il sistema. In creazione, se il
salvataggio della configurazione fallisce, la plancia appena creata viene cancellata per riportare
tutto indietro (`ha_client.py:426-468`). In sostituzione, prima si legge la configurazione attuale e
se non e' leggibile la sostituzione e' annullata; poi si salva una copia di sicurezza e se anche
quella fallisce la sostituzione e' annullata; solo allora si sovrascrive
(`config_tools.py:123-143`). L'utente ha poi un pulsante Annulla che riapplica la copia e la consuma
solo se Home Assistant ha accettato (`handlers_dashboards.py:29-62`). L'unica falla dichiarata: senza
una cartella dati configurata, si logga un warning e si sovrascrive comunque
(`config_tools.py:140-142`).

Un difetto piu' vistoso sta all'applicazione delle proposte: un tipo di proposta non gestito viene
loggato e poi marcato comunque come applicato, restituendo successo (`handlers_proposals.py:110-123`).
Il commento nel codice dichiara che questo era esattamente il bug da evitare ("sembrava applicata ma
non cambiava nulla"); il difetto e' ancora li', con un log in piu'.

### Le notifiche e i collegamenti profondi

L'invio di notifiche ha quattro canali: le card persistenti di Home Assistant, la push mobile
tramite il servizio configurato, Apprise verso servizi esterni, e una chiamata verso Retro Panel
(`notify_tools.py:146-199`). Alla push viene sempre aggiunto un canale dedicato e, se il percorso di
ingress e' noto, due collegamenti profondi: uno relativo per Android e uno con schema
`homeassistant://navigate` per iOS (`notify_tools.py:53-77`). Toccando il corpo della notifica si
apre HIRIS invece della dashboard di Home Assistant.

Il limite di tutto questo strato e' che ogni invio restituisce solo un vero/falso: il chiamante non
sa mai perche' e' fallito, il motivo resta nel log. E senza percorso di ingress il collegamento
profondo viene omesso del tutto, senza errore e senza avviso.

### La presenza dentro Home Assistant via MQTT

Se un broker e' configurato, per ogni chatbot vengono pubblicati sette sensori tramite discovery
(`mqtt_publisher.py:219-231`), e subito dopo vengono ritirate le due entita' di comando dismesse
pubblicando un messaggio vuoto sui loro argomenti (`mqtt_publisher.py:232-234`). Una pulizia
una-tantum ritira anche lo schema precedente al rinominamento, e il segnaposto su disco viene scritto
solo dopo che le ritrattazioni sono davvero arrivate al broker (`mqtt_publisher.py:271-328`). Se la
libreria MQTT non e' installata il ciclo termina ma il publisher resta formalmente abilitato, quindi
continua ad accodare messaggi che nessuno drenera' mai (`mqtt_publisher.py:75-79`).

---

## La superficie HTTP e il ciclo di vita del server

### Che cos'e'

Il server e' il guscio: costruisce l'applicazione con tre middleware, registra 64 rotte piu' i file
statici, e nella funzione di avvio cabla praticamente tutto il resto di HIRIS — client Home
Assistant, cache, motore chatbot, motore task, MQTT, dodici archivi, dispatcher, Sentinella,
cervello, router dei modelli, server MCP interno, worker della chat via abbonamento — e registra
circa quindici lavori periodici.

### Il cancello unico

Ogni rotta, comprese la pagina principale, la pagina di configurazione, i file statici e persino
`/api/health`, passa dagli stessi due controlli. Il primo riconosce l'ingress di Home Assistant:
serve un'intestazione di percorso di ingress conforme al pattern *e* un indirizzo IP sorgente dentro
una rete dichiarata (`middleware_internal_auth.py:30-78`). Altrimenti serve il token interno,
confrontato a tempo costante (`middleware_internal_auth.py:79-98`). Il secondo e' un controllo
anti-CSRF che pretende un'intestazione su tutte le richieste non sicure verso l'API, esentando chi
presenta il token (`middleware_csrf.py:38-55`).

Qui il materiale registra due cose che vale la pena tenere insieme. La prima: l'etichetta "ingress"
e' quella su cui si regge l'intero modello di conferma umana — solo un "ingress" puo' approvare una
richiesta rossa. La seconda: quel riconoscimento e' fatto di un'intestazione piu' un indirizzo IP,
e la rete di partenza (`172.30.32.0/23` di fabbrica) e' la rete Docker in cui vivono *tutti* gli
add-on. La mappa della superficie HTTP ne trae che un altro add-on co-residente potrebbe costruire a
mano quell'intestazione e ottenere l'etichetta, quindi accesso a tutta l'API e la facolta' di
approvare le richieste che il token esplicitamente non ha. La stessa mappa dichiara di non aver
fatto la prova: e' una lettura del codice, non un esperimento.

C'e' anche un modo di sviluppo, attivabile via variabile d'ambiente non esposta come opzione, che
disabilita il requisito del token e produce l'etichetta "senza token"
(`middleware_internal_auth.py:80-91`). Quell'etichetta e' accettata dalla guardia delle approvazioni
esattamente come l'ingress: in quella modalita' chiunque raggiunga la porta puo' approvare una
richiesta rossa.

### Le intestazioni di sicurezza

Il terzo middleware aggiunge le intestazioni di sicurezza — niente sniffing dei tipi, politica dei
referrer, politica dei contenuti, permessi (`server.py:2756-2775`). Ma e' registrato per ultimo, il
che in questo framework significa che e' il piu' *interno*: le risposte 401 dell'autenticazione e
403 del controllo CSRF ritornano prima di raggiungerlo ed escono senza nessuna di quelle
intestazioni (`server.py:2779-2783`). Lo stesso vale per le risposte in streaming della chat, che
vengono preparate dentro l'handler prima che il middleware giri (`handlers_chat.py:356`).
L'intestazione contro l'inclusione in frame e' invece omessa di proposito, perche' l'ingress di Home
Assistant usa proprio un frame (commento a `server.py:2767`).

### Le due strade della chat

La chat "locale" e' sincrona: valida il messaggio (obbligatorio, massimo 4000 caratteri,
`handlers_chat.py:143-151`), risolve il chatbot, carica la cronologia dal server ignorando quella
mandata dal client, chiama il modello e persiste domanda e risposta
(`handlers_chat.py:342-468`). Se nessun modello e' configurato risponde 503 con un messaggio che
nomina solo la chiave API di Claude (`handlers_chat.py:215-219`), anche quando il problema riguarda
altri provider.

La chat "via abbonamento" e' asincrona: la richiesta viene accodata e il server risponde subito con
un identificativo di lavoro, mentre la pagina interroga periodicamente per la risposta
(`handlers_chat.py:66-100, 103-137`). Un worker dentro l'add-on preleva i lavori dalla coda ogni tre
secondi e lancia il CLI `claude` come sottoprocesso, con l'ambiente ripulito dalle chiavi API perche'
usi davvero l'abbonamento (`agent/runner.py:123-159, 219-237`). Due protezioni: una risposta gia' in
volo per la stessa conversazione produce un rifiuto con 409, e un tetto giornaliero produce un 429
(`handlers_chat.py:193-212`).

Il punto fragile e' lo stesso di tutto il resto: il worker parla a HIRIS via HTTP con il token
interno. Se il token e' vuoto — il valore di fabbrica — ogni prelievo riceve 401 e il ciclo registra
soltanto un errore ogni tre secondi (`agent/runner.py:200-201, 235-236`): il worker sembra avviato e
non lavora mai.

Lo stesso ponte serve anche i ragionamenti automatici: un runner esterno preleva un lavoro, ragiona
e consegna la decisione, che viene poi applicata attraverso lo stesso semaforo del resto del sistema
(`server.py:2182-2209`). Se il semaforo non e' mai stato configurato, quelle decisioni si fermano
all'allerta (`server.py:2198-2201`).

### I lavori periodici

Sullo scheduler girano, fra gli altri: la ricarica dell'inventario ogni due minuti, la pulizia dei
messaggi vecchi alle 03:00, la compattazione dello storico alle 03:30, il digest alle 04:00, la
potatura del registro dei ragionamenti alle 03:15, il resoconto giornaliero alle 08:00, i solleciti
ogni sei ore, l'azzeramento dei contatori della Sentinella a mezzanotte e un minuto, la ronda ogni
quindici minuti, la scansione di salute ogni trenta. Ognuno e' avvolto in modo che un guasto non
fermi lo scheduler.

Il materiale registra due sorprese qui. La prima: un commento nel codice afferma che esiste un solo
scheduler ("verificato: la funzione di avvio non ne crea mai un secondo", `server.py:485-494`),
mentre gli scheduler nel processo sono due — quello del motore chatbot e quello proprio del motore
dei task (`task_engine.py:100`). La seconda: la potatura della coda dei ragionamenti sta *dopo*
l'uscita anticipata del suo lavoro (`server.py:2443-2463`), quindi in una configurazione senza ponte
attivo non viene mai eseguita.

### Lo spegnimento

La chiusura ferma il worker attendendolo al massimo cinque secondi, cancella il server MCP, chiude i
client e i dieci archivi in ordine, poi ferma i due scheduler senza attendere i lavori in corso
(`server.py:2710-2753`). Ventuno chiusure su ventitre' sono difensive; le ultime due — il motore e
il client Home Assistant — accedono direttamente alla chiave (`server.py:2749-2750`), quindi se
l'avvio era fallito prima di impostarle, la chiusura solleva un errore che maschera quello originale.

---

## Le opzioni dell'add-on

### Come funziona la configurazione

Le opzioni della pagina Configurazione dell'add-on non vengono mai lette dal codice Python. Il
Supervisor le scrive in un file, lo script di avvio le traduce una a una in variabili d'ambiente
(`run.sh:3-95`), e l'applicazione le legge da li' — quasi tutte una sola volta, dentro la funzione
di avvio. La conseguenza pratica e' netta: **ogni cambio di opzione richiede il riavvio
dell'add-on**, e nulla nell'interfaccia lo ricorda. Due opzioni fanno eccezione al percorso normale
e vengono lette direttamente dal file con `jq`: l'elenco degli indirizzi Apprise, perche' e' una
lista, e la denylist di lettura, perche' occorre distinguere "chiave assente" da "stringa vuota"
(`run.sh:34-36, 41`).

Lo script fa due controlli pre-volo che producono solo avvisi: un controllo di forma sulla rete di
ingress (`run.sh:114-116`) e un avviso quando non risulta configurato nessun provider di modelli
(`run.sh:117-120`).

### I provider di modelli

Ogni provider ha un interruttore e una credenziale. La regola di attivazione ha due modi: se
*nessun* interruttore e' acceso, si e' in modalita' compatibile e conta solo la presenza della
credenziale; se anche uno solo e' acceso, tutti i provider richiedono interruttore *e* credenziale
(`model_activation.py:14-34`). L'effetto sorprendente e' che accendere il primo interruttore
qualunque spegne di colpo tutti gli altri provider che non sono stati esplicitamente accesi. La
descrizione lo dice, ma nessun log all'avvio lo segnala.

L'ordine di preferenza fra i backend viene dalla strategia scelta (`llm_router.py:55-66`), corretta
da un eventuale ordine manuale salvato dall'interfaccia e riconciliata con i provider realmente
attivi (`model_activation.py:37-79`).

### Opzioni che non fanno quello che dicono

Il materiale ne registra diverse, e sono comportamenti da conoscere prima di configurare:

Le tre opzioni che descrivono il perimetro del gateway (strumenti, entita', servizi ammessi) smettono
di avere qualunque effetto appena l'utente salva una volta la pagina Accessi Gateway, perche' quel
salvataggio svuota e riscrive in blocco il perimetro (`handlers_gateway_policy.py:269-277`). Nulla lo
comunica.

Le due opzioni che promettono di scegliere l'ordine dei backend per il ragionamento automatico e per
la chat non possono mai influenzare il routing: la catena riconciliata le sostituisce entrambe
(`llm_router.py:144-150`), e la catena e' sempre non vuota nella sola condizione in cui il router
viene costruito (`server.py:2601`). Il codice le marca "deprecato" nei commenti; il form no.

L'opzione che dovrebbe segnalare l'esposizione della porta di debug non e' letta da nessun codice
Python: produce cinque righe di avviso nel log in base al valore dell'opzione, non in base al mapping
di porta realmente attivo (`run.sh:95-105`). Si puo' avere la porta aperta senza avviso e l'avviso
senza porta aperta.

Il token interno e' descritto come "lascia vuoto per generarlo automaticamente", ma nessuna
generazione automatica esiste nel codice (`server.py:1165`). Con il valore di fabbrica il token resta
vuoto, ogni richiesta non-ingress riceve 401, e il client MCP loopback della chat in abbonamento non
puo' eseguire alcuno strumento.

L'avviso sulla rete di ingress promette che "l'app ignora le voci non parsabili e usa il default",
mentre il ripiego sul valore predefinito scatta solo se la lista risulta *vuota*
(`server.py:1170-1172`). Con un valore non vuoto e non parsabile, nessuna richiesta viene piu'
riconosciuta come ingress e — con il token vuoto — l'intera interfaccia, file statici compresi,
risponde 401.

L'opzione che sposta la porta del server MCP interno sposta davvero il server (`server.py:1124`), ma
il file di configurazione consegnato al CLI punta alla porta 8199 scritta a mano
(`agent/runner.py:55`): cambiando la porta la chat via abbonamento perde tutti gli strumenti, senza
controlli di coerenza ne' avvisi.

Il tetto giornaliero della Sentinella non e' globale ma per sorgente: eventi, situazioni, arrivi e
ogni singolo Agentbot hanno ciascuno il proprio budget pari al valore dell'opzione
(`wake.py:24`). Il tetto reale e' il valore moltiplicato per il numero di sorgenti attive.

L'opzione che fa eseguire alla Sentinella le azioni verdi da sola non copre i domini pericolosi: il
controllo sulla denylist precede il controllo del livello (`watcher/executor.py:19-23`).

L'opzione sui giorni di conservazione delle memorie viene impressa al momento della scrittura
(`memory_tools.py:135-139`): cambiarla non tocca i ricordi gia' salvati.

Due opzioni compaiono nel form senza alcuna traduzione in nessuna delle due lingue — la porta del
server MCP interno e il token dell'abbonamento (`config.yaml:93, 125`) — quindi l'utente vede la
chiave grezza senza nome ne' descrizione. La seconda e' proprio la credenziale citata per nome dalla
descrizione dell'interruttore dell'abbonamento.

Infine, il livello di log agisce sul processo Python ma non sul server MCP interno, fissato a
"warning" (`server.py:1132`), ne' sui log dello script di avvio.

---

## Dove le mappe si contraddicono

Tre punti in cui due letture dello stesso codice non coincidono. Non li risolvo: la divergenza e'
essa stessa un dato.

**L'esito dell'invio delle notifiche.** La mappa del semaforo e quella del gateway leggono la
funzione di invio come capace di fallire e dichiararlo: "ritorna False se il client Home Assistant
manca, se il servizio e' malformato o se la chiamata solleva"
(`handlers_gateway_pending.py:222-230, 252-254`), e ne concludono che il flag "codice inviato" sia
falso in quei casi. La mappa dell'integrazione con Home Assistant legge la stessa funzione al
contrario: ignora il valore di ritorno della chiamata di servizio e restituisce comunque un
successo, mentre la chiamata di servizio ritorna falso *senza sollevare* quando Home Assistant
risponde con un errore o quando il nome del servizio non passa la validazione
(`ha_client.py:187-196`) — quindi il flag "afferma il contrario del fatto". Le due letture concordano
sui casi macroscopici (client assente, servizio senza punto) e divergono sul caso piu' comune:
notifica accettata dal codice e rifiutata da Home Assistant. Sulle conseguenze pratiche invece
concordano, perche' nessun chiamante di produzione guarda quel flag (`dispatcher.py:213`,
`task_engine.py:494-497`).

**Quanti strumenti espone davvero il server MCP.** La mappa del gateway parla di "13 tool MCP"
(`mcp/tiers.py:21-129`) ma ne elenca quindici per nome nello stesso punto, e altrove dice che
l'allowlist del CLI e' limitata a tredici nomi (`agent/runner.py:24-36`). Le due cifre riguardano
probabilmente due elenchi diversi — quello esposto dal server e quello ammesso dal CLI, che la stessa
mappa dichiara piu' stretto (esclude cronologia eventi e segnalazioni) — ma il materiale non lo
distingue esplicitamente, e il numero resta ambiguo.

**Che cosa significa l'etichetta "ingress".** La mappa del semaforo e quella del gateway la trattano
come sinonimo di "un umano dentro l'interfaccia di HIRIS", ed e' su questa equivalenza che poggia la
guardia delle approvazioni (`handlers_gateway_pending.py:292-311`). La mappa della superficie HTTP
legge lo stesso controllo come "intestazione di forma giusta piu' indirizzo IP nella rete Docker
degli add-on" e ne trae che l'equivalenza non regge in presenza di altri add-on co-residenti
(`middleware_internal_auth.py:30-63`). Non e' un disaccordo sul codice — le due mappe descrivono le
stesse righe — ma sulla portata della garanzia; e la seconda dichiara di non aver verificato sul
campo la raggiungibilita' della porta fra container.

---

# 4. Le superfici: la pagina chat, la pagina di configurazione, la card Lovelace

HIRIS si mostra all'utente attraverso tre schermi diversi, costruiti con tre tecniche diverse e con tre
contratti diversi verso il server. La pagina chat e la pagina di configurazione sono due documenti HTML
distinti serviti dall'add-on: passare dall'una all'altra e' un cambio di pagina pieno, non una
transizione interna (`static/index.html:70`). La pagina chat non ha router: e' un unico
documento con tredici file JavaScript non modulari che si scambiano stato attraverso variabili globali
`window.HirisChat*` (`static/index.html:217-235`). La pagina di configurazione e' invece una
piccola applicazione a rotte hash, con un solo contenitore che viene riscritto da capo a ogni
navigazione (`static/config/main.js:162-278`). La card Lovelace, infine, non e' servita
dall'add-on: e' un file copiato dentro la cartella di Home Assistant e registrato come risorsa della
dashboard, e vive dentro il frontend di HA parlando con l'add-on attraverso l'Ingress del Supervisor
(`server.py:153-177`, `server.py:291-381`).

Nessuna delle tre e' un'interfaccia amministrativa protetta da ruoli: chi arriva alla pagina, arriva a
tutto. L'unico filtro e' il middleware interno, che in pratica ammette solo il passaggio dall'Ingress
del Supervisor, oppure una chiamata con il token interno, oppure un'installazione che ha
esplicitamente disattivato il controllo (`api/middleware_internal_auth.py:67`; la mappa della
card descrive lo stesso middleware come basato su `X-Ingress-Path` piu' il CIDR del Supervisor o sul
token interno, `api/middleware_internal_auth.py:30-98`, senza citare la variante senza token).

---

## La pagina chat

### A cosa serve e da dove si entra

E' la superficie quotidiana: si scrive al Chatbot, si legge la risposta, si sceglie dalla barra
laterale quale Chatbot e' attivo, e si accede a tre caselle di posta che occupano la stessa area
centrale della conversazione, in mutua esclusione con essa: le Task pianificate, le Proposte del Brain
e la coda della Memoria da confermare. La pagina e' servita su `GET /` come HTML statico
(`server.py:2794`, handler alle righe `2974-2982`), con un'impronta di versione applicata
agli asset per forzare l'aggiornamento della cache (`server.py:2960-2971`).

### L'avvio

Al caricamento, prima ancora di disegnare qualcosa, uno script in linea applica il tema salvato per
evitare lo sfarfallio (`static/index.html:12-22`), poi lo stato della pagina cattura i
riferimenti agli elementi e rilegge da `localStorage` quale Chatbot era attivo l'ultima volta,
ripiegando su quello predefinito (`static/chat/state.js:23-47`). Da li' parte una sequenza di
chiamate quasi tutte in parallelo (`static/chat/main.js:11-41`): la versione da mostrare
accanto al titolo, l'elenco dei Chatbot, la cronologia del Chatbot attivo, i contatori di utilizzo, il
saluto scelto in base all'ora del giorno (`static/chat/agents.js:70-79`), e infine
l'inizializzazione dei tre pannelli, che caricano subito i propri elenchi anche se l'utente non li ha
aperti, perche' servono a valorizzare i pallini numerici accanto alle voci di menu.

Chi apre la pagina vede, se non ha mai scritto, una schermata di benvenuto con logo, saluto e quattro
frasi pronte da cliccare (`static/index.html:162-167`); altrimenti vede le bolle della
conversazione salvata.

Il boot e' anche il punto in cui la pagina e' piu' fragile in silenzio. Se la chiamata di stato
fallisce, il numero di versione semplicemente non compare e nessuno lo dice
(`static/chat/main.js:19`). Se fallisce la lettura della cronologia, la chat resta vuota e
mostra la schermata di benvenuto: un guasto e' visivamente identico a "non c'e' ancora niente"
(`static/chat/agents.js:118-123`). L'unico indicatore rosso dell'intera pagina e' un pallino
di connessione che compare solo quando l'elenco dei Chatbot non si carica
(`static/chat/agents.js:104-105`, stile in `static/hiris-chat.css:168-174`).

C'e' inoltre una corsa reale fra due chiamate del boot: l'elenco dei Chatbot porta con se' il limite di
turni, ma non ricalcola il contatore, che invece viene disegnato solo dal ripristino della cronologia
(`static/chat/agents.js:90`). Se le due risposte arrivano nell'ordine sbagliato, il contatore
resta nascosto e l'input aperto finche' l'utente non invia qualcosa.

### Scrivere e ricevere: due percorsi diversi

Il messaggio parte in tre modi: dal bottone di invio (`static/chat/send.js:157`), premendo
Invio senza Shift (`static/chat/send.js:140-147`), oppure — ed e' un comportamento che
sorprende — nel momento in cui nel testo compare un a-capo, per esempio incollando un testo su piu'
righe o premendo Shift+Invio: il gestore dell'evento di input toglie gli a-capo e invia
(`static/chat/send.js:148-156`).

Da li' in poi la pagina non decide da sola quale percorso seguire: lo decide il server. La richiesta e'
sempre la stessa (`static/chat/send.js:95-99`), ma la risposta puo' essere immediata oppure
un accodamento.

Nel **percorso sincrono** la pagina svuota la casella di testo, blocca input e bottone, appende la
bolla dell'utente e mostra un indicatore animato di elaborazione
(`static/chat/messages.js:86-103`). Il server, nel frattempo, risolve il Chatbot, verifica il
limite di turni, ricarica la cronologia dalla propria memoria — ignorando quella eventualmente inviata
dal client — assembla memoria, riassunti delle sessioni precedenti e contesto della casa, chiama il
modello e persiste la coppia domanda/risposta (`api/handlers_chat.py:140-495`). La pagina
sostituisce l'indicatore con la bolla di risposta e, se il modello ha usato degli strumenti, aggiunge
sotto una riga di etichette cliccabili che li nominano
(`static/chat/messages.js:50-84`). I blocchi di ragionamento, che il server pure restituisce
(`api/handlers_chat.py:490-494`), non vengono letti ne' mostrati.

Nel **percorso ad abbonamento**, quando l'installazione lo prevede
(`api/handlers_chat.py:193`), il server persiste subito il turno dell'utente, mette il lavoro
in coda e risponde con un identificativo di lavorazione (`api/handlers_chat.py:66-100`). La
pagina allora crea una bolla segnaposto con il logo pulsante, la scritta "HIRIS sta elaborando" e un
cronometro che scorre (`static/chat/messages.js:105-134`), e comincia a interrogare il server
ogni tre secondi e mezzo, fino a un tetto di cinque minuti
(`static/chat/send.js:23-24`, `30-65`). Quando la risposta e' pronta, il segnaposto si
trasforma nel testo definitivo.

Qui il comportamento reale ha alcuni spigoli che vale la pena raccontare perche' l'utente li incontra.
Il primo: quasi tutti gli errori applicativi finiscono nella stessa bolla della risposta, con la
stringa tecnica in inglese del server — messaggio troppo lungo, chiave API non configurata, richiesta
non autorizzata — indistinguibili da una frase del modello (`static/chat/send.js:113`), e in
quei casi il server non ha persistito nulla, quindi dopo un aggiornamento della pagina sia la domanda
sia l'errore spariscono (`api/handlers_chat.py:145`, `149`, `151`, `218`). Il secondo:
se l'attesa supera i cinque minuti la pagina dichiara che la risposta non e' arrivata, ma il lavoro puo'
risolversi dopo, e la risposta "mai arrivata" ricompare al successivo caricamento della cronologia
(`static/chat/send.js:24`). Il terzo: l'identificativo del lavoro vive solo nella memoria
della pagina, quindi un aggiornamento del browser mentre si aspetta uccide l'attesa senza alcuna
riconciliazione.

### Il limite di turni

Sotto la casella di scrittura c'e' un contatore "N / M messaggi" che diventa rosso al limite, e al
limite compare una striscia che dichiara la sessione conclusa
(`static/chat/agents.js:5-13`, `15-29`, striscia in `static/index.html:182`). Il
conteggio della pagina sale di uno a ogni risposta ricevuta e, dopo un ricaricamento, viene ricalcolato
contando i messaggi dell'utente nella cronologia (`static/chat/agents.js:131`). Il server
verifica lo stesso limite prima di scrivere qualunque cosa
(`api/handlers_chat.py:176-184`), ma lo verifica sulla sola sessione attiva: dopo due ore di
inattivita' la sessione e' considerata chiusa e il conteggio riparte da zero
(`chat_store.py:69`). I due conteggi possono quindi divergere, e quando divergono comanda
quello locale: il server puo' rifiutare mentre la pagina lascia l'input aperto
(`static/chat/send.js:108-111`).

### Nuova conversazione e cambio di Chatbot

Il bottone "Nuova conv." chiede conferma e poi cancella la cronologia
(`static/chat/agents.js:32-57`). Quello che accade davvero e' piu' ampio del nome del
bottone: il server cancella tutte le sessioni di quel Chatbot e tutti i loro riassunti, cioe' anche la
memoria delle conversazioni passate che verrebbe reiniettata come contesto
(`chat_store.py:295-305`). Se la cancellazione fallisce, l'utente riceve un avviso nativo e
la chat resta com'era (`static/chat/agents.js:38-50`).

Il cambio di Chatbot dalla barra laterale svuota lo schermo, salva la scelta, riscrive il titolo e
richiede la cronologia del nuovo interlocutore, scartando la risposta se nel frattempo l'utente ha
cambiato di nuovo (`static/chat/agents.js:140-157`). Il titolo dell'intestazione viene
riscritto solo li': dopo un aggiornamento della pagina il Chatbot attivo viene ripristinato ma il
titolo torna a dire "HIRIS" (`static/chat/agents.js:150-151`). Anche la pastiglia con nome e
iniziale del Chatbot ha l'aspetto di un selettore — bordo che reagisce al passaggio del mouse, pallino
verde pulsante — ma non ha alcun gestore di clic: e' un'etichetta
(`static/hiris-chat.css:199`, `static/index.html:144-148`).

### Le tre caselle di posta

Le tre voci di menu si comportano allo stesso modo: nascondono la conversazione, la casella di
scrittura e il contatore, nascondono gli altri due pannelli e mostrano il proprio
(`static/chat/tasks.js:64-87`). Tutte e tre ricaricano il proprio elenco ogni trenta secondi
anche a pannello chiuso (`static/chat/tasks.js:105-106`,
`static/chat/proposals.js:309-310`, `static/chat/knowledge.js:304-305`).

**Task pianificate** mostra due elenchi, quelle attive e quelle recenti, con etichetta, stato tradotto
in italiano e una riga di dettaglio (`static/chat/tasks.js:7-26`, `28-43`); si puo' annullare
una task ancora in attesa, previa conferma (`static/chat/tasks.js:52-62`). Se la lettura
fallisce, pero', nessuna delle due liste viene scritta: restano i soli titoli di sezione, e un guasto e'
identico a un pannello che non ha ancora finito di caricare
(`static/chat/tasks.js:42`). L'intestazione dichiara "24h" ma il filtro e' per stato, non per
data: sotto quell'etichetta compare tutto cio' che il motore delle task tiene in memoria, cioe' una
settimana (`task_engine.py:19`).

**Proposte** elenca le proposte in attesa con tipo, data, nome, descrizione e motivo, e per una proposta
di plancia che sostituisce interamente un'altra plancia aggiunge un avviso esplicito
(`static/chat/proposals.js:43-69`). Accanto all'elenco compaiono le strisce di ripristino:
gli snapshot delle ultime ventiquattro ore sono in evidenza, i piu' vecchi finiscono sotto "Versioni
precedenti" (`static/chat/proposals.js:140-158`). Attivare o rifiutare chiede conferma, poi
sbiadisce la scheda e ne riscrive il nome con l'esito
(`static/chat/proposals.js:199`, `211-219`). Questa e' l'unica superficie di HIRIS in cui
gli errori vengono tradotti: lo stato HTTP diventa una frase italiana specifica — non e' piu' valida,
non trovata, servizio non disponibile, Home Assistant ha rifiutato, configurazione non valida
(`static/config/proposals-core.js:49-67`). Il ripristino di una plancia avverte
esplicitamente che le modifiche fatte dopo la sostituzione andranno perse
(`static/chat/proposals.js:236-238`).

**Memoria** e' la coda degli elementi che il modello ha deciso di ricordare e che non sono ancora
richiamabili. Ogni elemento mostra tipo, data, titolo, corpo, dettagli e provenienza; se e' marcato
come sensibile il contenuto non entra affatto nel documento: al suo posto compare un avviso e un
bottone "Mostra contenuto", e solo allora il testo viene inserito, come testo puro
(`static/chat/knowledge.js:109-118`, `198-207`). Approvare significa calcolare l'incorporamento
mancante e rendere l'elemento richiamabile; scartare significa cancellarlo davvero
(`api/handlers_knowledge.py:42-52`). Anche qui gli errori sono tradotti in italiano, con un
messaggio dedicato per "non e' piu' in attesa, forse e' gia' stato gestito"
(`static/chat/knowledge.js:215-216`). Questo pannello e' anche l'unico che distingue
esplicitamente "coda vuota" da "non ho potuto leggere"
(`static/chat/knowledge-core.js:32-41`) — distinzione che pero' sopravvive solo dentro il
pannello, perche' in caso di errore il pallino numerico viene portato a zero e a zero sparisce
(`static/hiris-chat.css:105`).

Vale la pena notare, perche' e' comportamento e non intenzione, che nell'intestazione esistono tre
bottoni con i rispettivi pallini numerici per le stesse tre caselle, con tanto di gestori registrati,
ma nessuno di essi e' visibile a nessuna larghezza di schermo
(`static/index.html:131-139`; regole in `static/hiris-chat.css:641`, `733`, `796` e
di nuovo `913`).

### Il resto della pagina

Il **wizard di primo avvio** compare solo se non esiste alcun Chatbot diverso da quello predefinito e
solo se il browser non porta gia' il segno di averlo visto
(`static/chat/onboarding.js:15-23`): due passi, nome obbligatorio e istruzioni facoltative,
poi crea il Chatbot e lo seleziona (`static/chat/onboarding.js:38-54`). Se la verifica
iniziale fallisce, il wizard semplicemente non appare e ci si riprova al caricamento successivo.

Il **tema** si inverte con un clic e viene ricordato nel browser
(`static/chat/theme.js:26-35`); in assenza di una scelta locale viene chiesto al server
(`static/config/api.js:27-44`), e se anche quella chiamata fallisce non succede nulla di
visibile.

Il **widget dei consumi** in fondo alla barra laterale mostra richieste, token in ingresso e in uscita e
costo, aggiornati ogni trenta secondi (`static/config/api.js:69-85`). Se il motore non e'
configurato il server risponde con un errore e i quattro valori restano dei trattini, per sempre e
senza spiegazione (`api/handlers_usage.py:7-8`).

Un dettaglio di funzionamento che si nota solo osservando: finche' la pagina resta aperta interroga il
server ogni trenta secondi per elenco Chatbot, consumi, task, proposte, copie di sicurezza delle plance
e coda della memoria, indipendentemente da cosa sia visibile.

---

## La pagina di configurazione

### Com'e' fatta e da dove si entra

La configurazione e' una pagina sola con un unico contenitore centrale che ogni rotta riscrive
integralmente. Il documento carica in ordine di dipendenza una ventina di script
(`static/config.html:179-236`); l'ultimo installa la protezione contro le modifiche non
salvate, monta la cornice — barra laterale e intestazione, clonate da due modelli — e registra le
tredici rotte (`static/config/main.js:283-289`, `162-278`). Non esiste alcuna procedura di
smontaggio: quando si lascia una rotta, il suo contenuto viene semplicemente sostituito
(`static/config/router.js:18-51`).

L'utente vede una barra laterale con nove voci e quattro pallini numerici che partono da un trattino e
si popolano poco dopo, un percorso di navigazione in alto, e il contenuto della rotta. I quattro
pallini — Chatbot, Proposte, Task, Segnalazioni — vengono calcolati **una volta sola**, al montaggio
della cornice (`static/config/main.js:96-134`, dentro `mountChrome()` a `:49-135`, chiamata una sola volta dal listener `DOMContentLoaded` a `:283-284`); solo la pagina Task risincronizza il proprio
(`static/config/tasks-route.js:116-121`). Attivare una proposta o archiviare una
segnalazione lascia quindi il numero fermo al valore letto all'apertura della pagina. E se una di
quelle quattro letture fallisce, il trattino resta li' senza messaggio e senza traccia nemmeno nella
console (`static/config/main.js:104`, `113`, `123`, `134`).

Digitare un indirizzo che non corrisponde a nessuna rotta porta a una pagina "Pagina non trovata" con
un collegamento alla Dashboard (`static/config/router.js:48-62`). Se invece una rotta esplode
durante il montaggio, l'errore finisce solo nella console e l'utente resta davanti a un contenitore
vuoto o al contenuto precedente, senza alcun messaggio
(`static/config/router.js:28-41`).

### La protezione contro le modifiche non salvate

Esiste un solo guardiano per tutta la pagina, installato all'avvio, che intercetta sia il cambio di
indirizzo sia la chiusura della finestra e chiede conferma quando c'e' del lavoro non salvato
(`static/config/main.js:42-47`, `static/config/editor-kit.js:414-454`). Il
comportamento reale, pero', dipende da chi dichiara di avere modifiche pendenti, e a dichiararlo sono
soltanto i due editor di entita': il wizard di creazione, il Gateway, la Storicizzazione e la policy
della Sentinella hanno moduli pieni di campi e si possono abbandonare perdendo tutto, senza che nulla
chieda nulla (verificato su tutta la cartella della configurazione).

C'e' anche il rovescio della medaglia. Il tracciamento delle modifiche aggancia qualunque campo dentro
il contenitore centrale, comprese le caselle di **ricerca** del selettore di entita', che non fanno
parte di cio' che si salva: digitare due lettere in una ricerca senza selezionare nulla accende il
bottone Salva e fa scattare la richiesta di conferma alla navigazione successiva
(`static/config/editor-kit.js:373`, `378-379`;
`static/config/entity-picker.js:19-24`). E nell'editor Agentbot il solo caricamento di una
regola esistente genera tre eventi sintetici su altrettanti menu a tendina gia' agganciati, quindi
l'editor si apre gia' considerato "modificato"
(`static/config/agentbot-editor.js:648-649`, `663`).

### La Dashboard

La Dashboard ha due volti. Se non esiste ancora nessun Chatbot mostra un onboarding con tre riquadri
di esempio (Energia, Rientro, Promemoria) e un bottone per creare un Chatbot vuoto: tutti e quattro i
percorsi portano allo stesso wizard, senza preselezionare alcun modello
(`static/config/dashboard.js:92-116`). In questo ramo del Brain non si vede nulla: ragionamenti,
segnalazioni e proposte non vengono nemmeno richiesti.

Se invece la casa e' popolata, la pagina mostra tre riquadri di supervisione e tre sezioni alimentate
da tre chiamate indipendenti: lo stream dei ragionamenti del Brain, le segnalazioni aperte e
un'anteprima delle prime proposte (`static/config/dashboard.js:353-373`). Un puntatore
salvato nel browser ricorda l'ultima visita e serve a marcare come nuovi gli elementi comparsi da
allora e a portare la vista sul piu' recente (`static/config/dashboard.js:39-76`). Ogni
sezione ha il proprio messaggio d'errore e il proprio messaggio di elenco vuoto; nessuna delle tre
offre un modo per riprovare.

Sulle segnalazioni si puo' agire con "Ho capito" e "Ignora"; la scheda sbiadisce e mezzo secondo dopo
l'elenco si ricarica (`static/config/dashboard.js:252-266`). Se l'operazione fallisce
l'utente riceve la parola "Errore" e nient'altro (`static/config/dashboard.js:262`) — il
contrario esatto di quanto fanno le proposte, che dalla stessa pagina usano la traduzione degli stati
HTTP. E se il ramo che cerca la riga da sbiadire non trova nulla, l'operazione e' riuscita ma sullo
schermo non accade assolutamente niente.

### Creare: la lista e il wizard

La lista dei Chatbot mostra per ogni riga un pallino di stato, il nome, il modello, l'ultima esecuzione
e una freccia verso il proprio editor (`static/config/chatbots-list.js:15-75`). Se la lettura
fallisce compare una frase, non un bottone.

Il wizard di creazione e' a quattro passi
(`static/config/create-wizard.js:255-264`, `298-317`, `351-596`, `715-721`). Al primo si
scrivono nome e missione, e il bottone di avanzamento resta spento finche' entrambi non sono
compilati. Al secondo la pagina propone da sola se si tratta di un Chatbot o di un Agentbot: la scelta
non passa da alcun modello, e' un conteggio di parole ricorrenti fatto in locale
(`static/config/create-wizard.js:109-127`), e la proposta viene marcata come suggerita e
preselezionata solo quando il margine e' netto. Il terzo passo cambia forma a seconda del tipo scelto;
il quarto e' un riepilogo, e da li' si crea l'entita', che nasce gia' attiva, e si viene portati
direttamente nel suo editor.

Prima dell'invio non esiste alcuna verifica locale: una pianificazione senza orario, un'entita' di
innesco vuota, un servizio non indicato passano tutti, e l'errore arriva dal server, mostrato con la
sua stringa grezza (`static/config/create-wizard.js:753`). Se la risposta non contiene
l'identificativo atteso, la pagina naviga verso un editor su un identificativo inesistente. Uscire dal
wizard e rientrarci azzera tutto, senza avviso
(`static/config/create-wizard.js:776`).

### Le rotte di gestione

**Proposte** ha due schede, "In attesa" e "Archivio", con due contatori
(`static/config/proposals-route.js:3-53`). Le righe mostrano tipo, data, descrizione e
motivo, e per plance, script e scene anche il blocco di configurazione proposto; nella scheda Archivio
non ci sono bottoni (`static/config/proposals.js:51-54`). Attivare o rifiutare sbiadisce la
riga, ne riscrive il nome con l'esito e dopo poco piu' di un secondo la fa sparire. Dopo l'azione,
pero', ne' i due contatori ne' il pallino della barra laterale vengono ricalcolati: puo' restare
scritto "In attesa 5" sopra quattro righe. Va detto di passaggio, perche' e' quello che l'utente
sperimenta: l'Archivio non contiene le proposte decise. Attivare scrive uno stato, rifiutare ne scrive
un altro, e "archiviata" e' invece lo stato che il ciclo di vita assegna alle proposte scadute per
inattivita' (`proxy/proposal_store.py:145-153`, `155-163`, `165-180`).

**Consumi** mostra i quattro totali con la data dell'ultimo azzeramento e, sotto, una riga per Chatbot
con esecuzioni, token e costo (`static/config/usage-route.js:15-108`). L'azzeramento globale
chiede conferma, dichiara l'operazione irreversibile e, se riesce, ridisegna l'intera pagina; se
fallisce mostra la parola "Errore" e non ridisegna nulla, lasciando l'utente senza modo di sapere se i
numeri a schermo siano ancora veri (`static/config/usage-route.js:111-119`).

**Modelli** e' la rotta piu' curata dell'intera area. Quattro sezioni — provider attivi, catena di
ripiego, assegnazione per entita', incorporamenti — con pallini di stato, avvisi per le credenziali
mancanti e un banner esplicito quando nessun provider e' attivo
(`static/config/models-route.js:695-750`). Non c'e' un bottone Salva: ogni cambiamento di
menu a tendina viene scritto subito, con le richieste messe in fila da un semaforo interno
(`static/config/models-route.js:202-213`), un segno di conferma che compare per poco piu' di
un secondo e, in caso di errore, il ritorno automatico del controllo al valore precedente. E' anche
l'unica rotta dell'area che offre dei veri bottoni "Riprova"
(`static/config/models-route.js:372-397`, `594-597`). Il riordino della catena avviene con
due frecce, e' immediato e viene confermato dalla nota che l'ordine si applica al riavvio dell'add-on;
se il salvataggio fallisce l'ordine precedente torna e compare un messaggio
(`static/config/models-route.js:459-498`).

**Task pianificate** offre otto filtri, un bottone di aggiornamento, righe che si espandono una alla
volta, la cancellazione di un task in attesa e la copia del blocco dati grezzo
(`static/config/tasks-route.js:143-226`). Due comportamenti meritano di essere raccontati.
Il primo: la funzione che legge i task trasforma qualunque guasto in una lista vuota
(`static/config/tasks-route.js:29`), quindi un server spento e una coda davvero vuota
producono la stessa identica schermata, e l'utente legge che non c'e' nulla. Il secondo: il bottone
"copia" non da' alcun segnale, ne' di riuscita ne' di fallimento
(`static/config/tasks-route.js:216-222`).

**Accessi Gateway** e' il semaforo: una riga per categoria di dispositivi, con il numero di dispositivi
coinvolti e un menu a quattro livelli, le categorie a zero dispositivi attenuate, un avviso che cambia
testo per le categorie che il server marca come pericolose, una casella di testo per le eccezioni per
singola entita' e un campo per il servizio di notifica
(`static/config/gateway-route.js:271-309`). In cima alla pagina c'e' la coda dei comandi in
attesa di approvazione, con un pallino di gravita', l'origine e i due bottoni
(`static/config/gateway-route.js:110-135`). Questa coda distingue correttamente "vuota" da
"non ho potuto leggerla" (`static/config/gateway-route.js:94-101`) e, sull'approvazione,
produce quattro messaggi diversi e specifici, compreso quello che spiega che un comando approvato ma
non eseguito non e' piu' riprovabile
(`static/config/gateway-route.js:154-175`). Ma la coda si aggiorna solo al montaggio della
pagina e dopo un'approvazione o un rifiuto: un comando che arriva mentre si sta guardando la pagina non
compare (`static/config/gateway-route.js:206`, `360`). E sul salvataggio della policy c'e' un
comportamento silenzioso importante: le righe di eccezione per entita' che non rispettano il formato
vengono scartate senza dirlo, la casella di testo non viene ridisegnata dai dati salvati, e accanto al
bottone resta scritto che il salvataggio e' riuscito
(`static/config/gateway-route.js:70-79`, `300-302`). Quella scritta di conferma, fra l'altro,
non ha alcun timer e resta a schermo anche mentre l'utente modifica altri campi.

**Storicizzazione** e' un modulo semplice — caselle per dominio, due liste di entita' e i giorni di
conservazione (`static/config/history-route.js:50-101`) — con la stessa conferma permanente
e lo stesso stile di errore generico. Se il numero di giorni non e' valido viene salvato novanta senza
dirlo, mentre il campo continua a mostrare quello che l'utente ha scritto
(`static/config/history-route.js:92`).

**Agentbot** raccoglie in una pagina sola la policy della Sentinella e l'osservabilita'
(`static/config/agentbot-route.js:485-499`). Le tre card di configurazione hanno un unico
bottone di salvataggio, e le due che non lo possiedono lo dichiarano per iscritto rimandando alla
prima; il salvataggio e' atomico sui tre blocchi, quindi toccare una sola card riscrive comunque anche
le altre due con quello che c'e' a schermo (`static/config/agentbot-route.js:98-129`). Sotto
ci sono l'elenco delle regole con il collegamento per crearne una nuova, gli eventi recenti e i
suggerimenti del Brain, ciascuno con la propria lettura indipendente e il proprio messaggio d'errore
(`static/config/agentbot-route.js:329-482`).

### Gli editor: il Chatbot

Aprire un Chatbot significa svuotare il contenitore, clonare il modello di pagina, azzerare lo stato di
"modificato", generare undici sezioni con il loro indice laterale e poi riempirle
(`static/config/chatbot-editor.js:836-872`, `63-75`). Le sezioni coprono istruzioni, modello,
ambito di entita', strumenti e azioni permesse, categorie di memoria, riepilogo dell'autonomia,
consumi, log delle esecuzioni e prova manuale.

L'**ambito** si compone con un selettore di entita': si digita, il selettore interroga il server dopo
trecento millisecondi di pausa, si sceglie da un elenco a discesa oppure si aggiunge un intero dominio
con una pastiglia (`static/config/entity-picker.js:64-107`). Quando la ricerca non trova
nulla l'elenco viene semplicemente nascosto, il che e' indistinguibile dal non aver ancora cercato
(`static/config/entity-picker.js:87`). Non c'e' alcuna verifica del testo: premendo Invio si
aggiunge qualunque stringa come schema (`static/config/entity-picker.js:105`).

Il **riepilogo dell'autonomia** e' la cosa piu' interessante di questa pagina dal punto di vista
dell'utente: prende le entita' dell'ambito, le manda al Gateway e restituisce quante di esse cadono in
ciascun livello del semaforo piu' quelle sempre bloccate perche' appartengono a un dominio pericoloso
(`static/config/chatbot-editor.js:368-395`). Si aggiorna a ogni modifica dell'ambito. Se
qualcosa va storto dice soltanto che non e' stato possibile leggere la policy, senza distinguere fra
errore di rete ed errore del server.

Il **salvataggio** e' l'unica azione dell'editor, e il suo unico segnale di riuscita e' il bottone
Salva che torna spento: nessun messaggio, nessuna marca temporale — ed e' una scelta dichiarata nel
markup (`static/config.html:144-148`). Se il server rifiuta, compare un avviso con la stringa
del server o il numero HTTP, e il bottone resta acceso
(`static/config/chatbot-editor.js:646`). Se invece e' la rete a cadere, non compare
assolutamente nulla: l'utente vede un clic che non produce effetti.

La **prova manuale** blocca il doppio avvio, riscrive la sezione con un banner e un riquadro di output,
porta la vista sulla sezione e attende con un limite di dieci minuti
(`static/config/chatbot-editor.js:666-716`). Al termine mostra l'esito evidenziato, oppure la
dicitura che non e' stato restituito alcun risultato, oppure l'errore; poi ricarica log e consumi, e se
quella ricarica fallisce non lo dice (`static/config/chatbot-editor.js:754-757`). Due cose
che l'utente ha diritto di sapere e che l'interfaccia non dice: la prova esegue davvero, con gli
strumenti e i servizi concessi al Chatbot, quindi puo' agire sui dispositivi
(`chatbot_engine.py:519-540`); e il limite di attesa del server e' meta' di quello annunciato
a schermo, quindi nella configurazione predefinita e' il server a interrompere per primo
(`chatbot_engine.py:28-34`).

Il **log delle esecuzioni** ha filtri, righe espandibili e bottoni di copia
(`static/config/log-row.js:18-66`, `118-124`). Il suo bottone di aggiornamento, pero', chiama
una funzione che non esiste e ripiega su una chiamata malformata: il risultato non e' un aggiornamento
ma la cancellazione del contenuto del modulo a schermo, con il nome che diventa vuoto e le caselle che
si svuotano (`static/config/log-row.js:56-65`,
`static/config/chatbot-editor.js:117`).

L'**eliminazione** chiede una conferma sobria, "Eliminare questo Chatbot?"
(`static/config/chatbot-editor.js:774`), mentre il server cancella anche le memorie a lungo
termine e l'intera cronologia di chat di quel Chatbot
(`api/handlers_chatbots.py:208-222`). Il bottone e' nascosto sul Chatbot predefinito
(`static/config/chatbot-editor.js:145-146`).

### Gli editor: l'Agentbot

L'editor Agentbot riusa lo stesso modello di pagina e la stessa barra di azioni, nascondendo la prova
manuale, e genera otto sezioni (`static/config/agentbot-editor.js:902-946`). Il controllo
centrale e' la modalita': "regola" oppure "obiettivo". In modalita' obiettivo sparisce la sezione
dell'azione e sparisce la scelta del tipo di innesco, e compare la nota che quella modalita' gira solo
su pianificazione (`static/config/agentbot-editor.js:596-620`, `246-249`). Il perimetro ha
due interruttori che distinguono "nessun limite" da "lista vuota"
(`static/config/agentbot-editor.js:394-406`).

Il salvataggio ha lo stesso silenzio dell'altro editor, e in piu' un difetto di comprensibilita': non
c'e' alcuna verifica locale, e quando il server rifiuta risponde con un messaggio unico e generico che
l'editor mostra alla lettera, senza indicare quale campo sia il problema
(`api/handlers_agentbots.py:127`, `154`).

La sezione di osservabilita' chiede la cronologia degli eventi della Sentinella e poi filtra sul posto
quelli generati da questa regola (`static/config/agentbot-editor.js:488-515`). Il server
restituisce pero' i cinquanta eventi piu' recenti in assoluto
(`api/handlers_sentinel.py:41-48`), quindi con piu' regole attive gli eventi di questa
possono essere fuori finestra e l'utente legge "nessun evento" pur avendone; e una risposta d'errore
viene trattata come elenco vuoto, quindi un guasto e' identico al silenzio. Gli eventi vengono mostrati
senza data e ora, benche' il dato ci sia (`sentinel_store.py:107`).

### La firma comune degli errori

C'e' una regola scritta in un punto del codice — mai la stringa tecnica del server verso l'utente, lo
stato HTTP diventa una frase italiana — e viene applicata dalle proposte
(`static/config/proposals-core.js:34-48`). Fuori dalle proposte, la pagina di configurazione
fa quattro cose diverse: mostra la stringa grezza del server (wizard,
`static/config/create-wizard.js:753`; editor,
`static/config/chatbot-editor.js:646`), mostra il numero HTTP nudo
(`static/config/tasks-route.js:214`), mostra la sola parola "Errore"
(`static/config/dashboard.js:262`, `static/config/usage-route.js:116`), oppure una
frase generica di mancato salvataggio (`static/config/gateway-route.js:355`,
`static/config/history-route.js:100`). Sui consumi per singolo Chatbot il fallimento non
produce nemmeno una riga di console (`static/config/usage.js:49-56`, `58-83`).

---

## La card Lovelace

### A cosa serve e come arriva nella dashboard

La card e' la chat di HIRIS incorporata dentro una dashboard di Home Assistant. Offre solo la
conversazione: scrivere, leggere, copiare o rigenerare una risposta, un interruttore per abilitare il
Chatbot e una pastiglia di stato. Rinuncia a tutto il resto — Proposte, Task, Memoria, cambio di
Chatbot, contatore turni, etichette degli strumenti chiamati, onboarding — e, punto centrale, **non
legge mai la cronologia dal server**: mostra una propria copia salvata nel browser.

Arrivarci e' una catena di tre passi eseguiti all'avvio dell'add-on. Prima il file della card viene
copiato dentro la cartella di configurazione di Home Assistant
(`server.py:153-177`). Poi l'add-on chiede al Supervisor il proprio indirizzo di Ingress e lo
scrive in un file accanto alla card, perche' la card possa scoprirlo da sola
(`server.py:221-264`). Infine si collega via WebSocket a Home Assistant, cancella le vecchie
registrazioni e registra la risorsa con la versione nell'indirizzo, cosi' che i browser ricarichino il
file a ogni aggiornamento (`server.py:291-381`).

Di tutta questa catena l'utente non vede nulla: esiti positivi, modalita' non supportate e fallimenti
finiscono solo nel registro dell'add-on. La card compare nel selettore delle card solo dopo un
ricaricamento dell'interfaccia di HA. E c'e' un caso in cui il risultato e' visibilmente rotto senza
spiegazione: se la copia del file fallisce, il boot prosegue lo stesso e la registrazione punta a un
file che non esiste (`server.py:176-177`).

### L'avvio della card e la sessione di Ingress

Al primo montaggio la card crea il proprio albero isolato, applica i fogli di stile una volta sola e
imposta i valori predefiniti (`static/hiris-chat-card.js:632-667`). La configurazione accetta
l'identificativo del Chatbot (con il nome vecchio ancora accettato per compatibilita'), lo slug
dell'add-on, il titolo, fino a sei suggerimenti e l'altezza
(`static/hiris-chat-card.js:683-701`).

Il punto delicato e' come la card raggiunge l'add-on. Alla prima assegnazione dell'oggetto di Home
Assistant apre una sessione di Ingress chiedendola a HA
(`static/hiris-chat-card.js:593-611`), e la rinnova ogni quattro minuti, su risposta non
autorizzata, e ogni volta che la scheda del browser torna visibile
(`static/hiris-chat-card.js:740-752`). L'indirizzo di base lo scopre leggendo il file
scritto dall'add-on, una volta sola per pagina
(`static/hiris-chat-card.js:561-574`). Se quella lettura fallisce, non viene mai piu'
ritentata per tutta la vita della pagina, e la card ripiega su un indirizzo costruito con lo slug
(`static/hiris-chat-card.js:770-774`) che, secondo il commento del server stesso, non puo'
funzionare perche' il Supervisor usa un token casuale e non lo slug
(`server.py:221-227`).

Ogni trenta secondi la card chiede l'elenco dei Chatbot per aggiornare stato e interruttore
(`static/hiris-chat-card.js:781-807`). Se la risposta non e' buona compare un banner rosso
con il codice; se il Chatbot configurato non e' nell'elenco compare "Chatbot non configurato" — ma la
casella di scrittura resta attiva, e il server, ricevendo un identificativo sconosciuto, ricade sul
Chatbot predefinito (`api/handlers_chat.py:161-166`): si vede un banner rosso e si ricevono
comunque risposte, da un altro interlocutore, salvate localmente sotto un identificativo inesistente.

### Inviare un messaggio: tre esiti possibili

La card e' l'unico client che chiede lo streaming
(`static/hiris-chat-card.js:830-833`). Il percorso normale e' quindi il flusso di eventi: la
card pubblica subito la bolla dell'utente e una bolla vuota dell'assistente, poi legge la risposta a
pezzi e la fa crescere (`static/hiris-chat-card.js:809-818`, `859-883`). L'utente vede tre
pallini animati finche' non arriva testo, poi il testo con un cursore lampeggiante; il bottone di invio
diventa un indicatore di attesa e la casella dichiara che sta elaborando. Al termine la conversazione
viene tagliata alle ultime sessanta bolle e salvata nel browser
(`static/hiris-chat-card.js:895-905`), mentre il server persiste la coppia nella propria
memoria (`api/handlers_chat.py:393-416`).

Il secondo esito e' l'accodamento: il server risponde con un identificativo di lavorazione e la card lo
riconosce, ferma il proprio timer e mostra la frase "HIRIS sta pensando" — una stringa statica, senza
cronometro e senza animazione, a differenza della pagina chat
(`static/hiris-chat-card.js:844-854`). Poi interroga ogni tre secondi e mezzo per un massimo
di cinque minuti (`static/hiris-chat-card.js:911-921`).

Il terzo esito e' una risposta semplice, che la card mostra cosi' com'e', o rimpiazza con "Nessuna
risposta" quando manca il campo atteso (`static/hiris-chat-card.js:884-888`). E' qui che
cade, per esempio, il limite di turni raggiunto: il server risponde con esito positivo e un corpo che
dichiara il limite (`api/handlers_chat.py:177-184`), e la card scrive "Nessuna risposta",
mentre la pagina chat riconosce lo stesso corpo e dice che la sessione e' completata
(`static/chat/send.js:108-111`).

Tre comportamenti di fallimento vanno raccontati perche' sono quelli che l'utente incontra davvero. Il
limite di trenta secondi non copre solo l'apertura della connessione ma l'intero consumo della
risposta (`static/hiris-chat-card.js:822`, `896`): una risposta lunga, tipicamente una che
usa strumenti, viene interrotta e il testo gia' ricevuto viene **sovrascritto** dal messaggio di
timeout (`static/hiris-chat-card.js:890-892`), mentre il server ha comunque consumato i
token. Un errore trasmesso dentro il flusso di eventi non viene marcato come errore, quindi arriva come
una normale risposta dell'assistente e come tale viene salvato nel browser
(`static/hiris-chat-card.js:876-879`). E ogni ridisegno della card — che avviene a ogni pezzo
di risposta e a ogni ciclo di aggiornamento da trenta secondi — ricrea la casella di scrittura: il
testo viene conservato, ma il fuoco e la posizione del cursore no, e la lista dei messaggi viene
riportata in fondo (`static/hiris-chat-card.js:1136`, `1207`). In pratica non si puo'
scrivere mentre arriva una risposta, ne' scorrere indietro.

### Stato, interruttore, pulizia

La pastiglia di stato dichiara "pronto", "in esecuzione" o "errore"
(`static/hiris-chat-card.js:1144`), ma nella pratica dice quasi sempre "pronto": gli stati
"in esecuzione" e "errore" sono popolati solo dalla prova manuale lanciata dall'editor di
configurazione (`chatbot_engine.py:496`, `591`), e conversare non li tocca mai.

L'interruttore ribalta subito l'aspetto e poi manda la modifica al server; se riesce compare in basso
un avviso con un "Annulla" valido cinque secondi
(`static/hiris-chat-card.js:969-1003`, `1005-1021`). Se non riesce, lo stato torna indietro
in silenzio, senza alcun messaggio (`static/hiris-chat-card.js:986-992`). L'avviso, per
inciso, e' posizionato in modo assoluto ma non ha un antenato posizionato dentro la card, quindi non e'
ancorato alla card (`static/hiris-chat-card.js:462-473`, `644-648`).

"Pulisci conversazione" chiede conferma con le stesse parole della pagina chat, ma fa una cosa
diversa: cancella la chiave del browser e nient'altro
(`static/hiris-chat-card.js:963-967`). La cronologia lato server resta e continua a essere
iniettata come contesto al turno successivo (`api/handlers_chat.py:222`), mentre la stessa
azione nella pagina chat cancella davvero sul server
(`static/chat/agents.js:37`).

"Copia" e "Rigenera" compaiono solo passando sopra una bolla dell'assistente
(`static/hiris-chat-card.js:359-364`). La copia mostra la conferma di riuscita anche quando
fallisce, perche' il ritorno positivo e quello negativo sono gestiti allo stesso modo
(`static/hiris-chat-card.js:1251`). La rigenerazione risale all'ultimo messaggio dell'utente,
elimina localmente la risposta e tutto cio' che segue, e rinvia
(`static/hiris-chat-card.js:950-961`): sul server, pero', e' un turno nuovo a tutti gli
effetti, che aggiunge una coppia alla cronologia e consuma il limite di turni
(`api/handlers_chat.py:411-415`, `464-468`).

### L'editor visuale della card

Aprendo "Modifica" sulla card, Home Assistant mostra un pannello con quattro campi: Chatbot, titolo,
suggerimenti iniziali (uno per riga, tagliati a sei) e altezza dell'area di conversazione
(`static/hiris-chat-card.js:1379-1406`). L'elenco dei Chatbot viene chiesto all'add-on
(`static/hiris-chat-card.js:1308-1330`); se non arriva, il campo degenera in una casella di
testo libera senza dire che l'elenco non e' stato caricato
(`static/hiris-chat-card.js:1352-1355`). C'e' un caso in cui l'editor mente in modo
silenzioso: se il Chatbot salvato non e' fra le opzioni, il browser mostra come selezionata la prima
opzione, ma nessun evento parte, quindi la configurazione resta sul valore vecchio mentre lo schermo ne
mostra un altro (`static/hiris-chat-card.js:1356-1366`, `1415-1423`). Manca inoltre qualunque
campo per lo slug dell'add-on, che pure viene letto dalla configurazione e usato sia per la scoperta
dell'indirizzo sia per la chiave locale della conversazione
(`static/hiris-chat-card.js:689`, `1310`, `53`): chi non usa lo slug predefinito deve
modificare la configurazione a mano.

### La conversazione salvata nel browser

La chiave e' costruita su slug e identificativo del Chatbot
(`static/hiris-chat-card.js:16`, `52-54`), e viene riletta solo quando quella coppia cambia
(`static/hiris-chat-card.js:697-699`). Il salvataggio avviene alla fine di ogni invio,
scartando le bolle ancora in streaming e conservando solo ruolo e testo — quindi anche le bolle
d'errore vengono salvate come risposte normali, e perdono il colore rosso al ricaricamento
(`static/hiris-chat-card.js:65-75`). Non c'e' scadenza e non c'e' mai sincronizzazione con il
server: su un altro dispositivo, o dopo aver cancellato i dati del sito, la card mostra una
conversazione vuota mentre il modello continua a ricevere tutta la storia
(`api/handlers_chat.py:222`).

Un ultimo dettaglio che si vede solo con due card sulla stessa dashboard: la chiave locale e' separata
per card, ma l'indirizzo di Ingress scoperto e il momento dell'ultimo rinnovo di sessione sono
variabili condivise da tutte le istanze presenti nella pagina
(`static/hiris-chat-card.js:559`, `590`), quindi due card con slug diversi usano l'indirizzo
scoperto dalla prima che parte (`static/hiris-chat-card.js:562`).

---

## Le tre superfici messe una accanto all'altra

La stessa azione ha significati diversi a seconda di dove la si compie. "Pulisci conversazione" nella
card tocca solo il browser; nella pagina chat cancella sul server tutte le sessioni e i riassunti di
quel Chatbot (`chat_store.py:295-305`). Il ripristino di una plancia sostituita esiste solo
nel pannello Proposte della chat (`static/chat/proposals.js:239`), mentre la pagina di
configurazione consente comunque di attivare la proposta che la sostituisce: le funzioni per elencare
e ripristinare le copie di sicurezza sono caricate anche li' ma nessuna vista le usa
(`static/config/proposals-core.js:95-109`). Le etichette degli strumenti chiamati esistono
solo nella pagina chat (`static/chat/messages.js:50-84`): chi usa la card non vede mai quali
strumenti sono stati usati sulla propria casa. Anche la creazione di un Chatbot ha due porte diverse e
non equivalenti: il wizard minimale della chat, a due passi con nome e istruzioni
(`static/chat/onboarding.js:38-54`), e quello a quattro passi della configurazione, che
deriva il tipo e compila i campi guidati (`static/config/create-wizard.js:715-756`).

Sul tema, le tre superfici seguono tre logiche: la pagina chat risolve preferenza locale, poi
configurazione del server, poi sistema (`static/config/api.js:27-44`); la configurazione usa
la stessa chiave locale con in piu' un parametro d'indirizzo che vale solo per la prima pittura e non
viene conservato (`static/config.html:12-26`); la card segue soltanto la preferenza del
sistema operativo, non quella di Home Assistant
(`static/hiris-chat-card.js:142-166`).

### Contraddizioni fra le letture delle mappe

Due punti vanno segnalati perche' due ricostruzioni indipendenti dello stesso meccanismo non
coincidono.

**Chi scrive la risposta differita nella memoria di chat.** La mappa della pagina chat colloca quella
scrittura nel consumatore della coda di ragionamento, indicando
`api/handlers_reasoning.py:34-53`. La mappa della card colloca la stessa scrittura in una
funzione del server, indicando `server.py:2211-2245`. Le due letture concordano sul
comportamento — la risposta non viene scritta dalla pagina ma da chi risolve il lavoro accodato — ma
indicano due punti di codice diversi. Non ho verificato quale delle due sia il punto effettivo, ne' se
si tratti di due anelli della stessa catena.

**Quando il percorso ad abbonamento sia attivo.** La mappa della pagina chat dichiara di non sapere
dove venga impostata la condizione che sceglie fra risposta immediata e accodamento, e di conseguenza
di non sapere quale dei due percorsi l'utente veda normalmente. La mappa della card indica invece due
punti precisi (`server.py:1412`, `2495-2499`), pur dichiarando di non aver ricostruito le
condizioni reali. La conseguenza pratica e' rilevante e va detta: nessuna delle due letture e' in grado
di dire quale sia il comportamento normale di invio di un messaggio in un'installazione reale.

Va inoltre registrata una lacuna che nessuna delle mappe chiude. La mappa della chat si chiede se
l'eliminazione di un Chatbot dalla pagina di configurazione ripulisca la preferenza locale che
ricorda il Chatbot attivo. La mappa degli editor descrive l'eliminazione come azzeramento dello stato
in memoria, ricarica dell'elenco e cambio di indirizzo
(`static/config/chatbot-editor.js:771-794`), e non menziona alcuna pulizia di quella chiave.
Se la lettura e' completa, la chat continuerebbe a puntare a un Chatbot che non esiste piu': nessuna
delle due mappe lo afferma, e la domanda resta aperta.

---

# 5. I sei flussi end-to-end, raccontati per intero

Questa sezione racconta che cosa succede davvero, dal primo gesto dell'utente all'ultimo effetto, in sei percorsi che attraversano tutto il prodotto. Non sono sei funzionalita' separate: sono sei modi diversi in cui le stesse parti di HIRIS — la chat, il dispatcher degli strumenti, il semaforo, la coda di conferma, il ponte verso Home Assistant, le pagine di configurazione — vengono composte. Per questo motivo lo stesso difetto compare in piu' di un racconto: non e' ripetizione, e' la stessa giuntura vista da sei angolazioni.

Una premessa vale per tutti e sei. Fra il modello e l'utente c'e' un filtro quasi opaco: quando uno strumento fallisce, il messaggio di errore torna **al modello**, non alla persona. Quello che l'utente legge e' la narrazione che il modello sceglie di fare di quell'errore. Il pannello di debug della chat mostra il nome dello strumento chiamato e i suoi argomenti (`handlers_chat.py:486-489`) ma **mai il risultato**. Nessuna delle superfici che descriviamo sotto colma questa distanza.

---

### 5.1 Il Brain che guarda la casa da solo

**A cosa serve.** E' l'unica parte di HIRIS che si muove senza che nessuno le chieda niente: ogni mezz'ora osserva lo stato della casa e, se trova qualcosa che non va, apre una «segnalazione». Serve a chi vuole accorgersi che una batteria e' scarica, un add-on e' fermo, il disco si sta riempiendo o un'automazione e' rotta, senza dover andare a controllare.

**Da dove si entra.** Da nessuna parte: non si entra, si viene raggiunti. Il giro periodico e' registrato all'avvio del server (`server.py:2424-2427`) con un intervallo letto da `HIRIS_HEALTH_SCAN_MINUTES`, variabile che l'add-on non esporta (`run.sh` non la contiene): nell'add-on vale sempre 30 minuti e non e' configurabile. Non esiste un interruttore «il Brain osserva si'/no»: il giro viene registrato incondizionatamente. Poiche' il trigger e' a intervallo puro, la **prima** scansione avviene mezz'ora dopo il riavvio: in quella finestra il Brain e' cieco e la Dashboard mostra una lista vuota.

**Il percorso.** Ogni giro raccoglie sei letture indipendenti — stati delle entita', cache locale, automazioni, mappa delle aree, add-on, informazioni di sistema — e ognuna, se fallisce, viene degradata a lista vuota con un semplice avviso a log (`brain/health_scan.py:237-285`). Sulle liste cosi' ottenute girano otto controlli (`brain/health_checks.py`), che producono candidati con una severita': entita' non disponibili da troppo tempo, batterie scariche, automazioni rotte o disabilitate, domini pericolosi lasciati «verdi» nel semaforo, entita' senza area, add-on fermi, disco pieno, aggiornamenti disponibili. I candidati vengono poi riconciliati contro il database delle segnalazioni (`brain/advisory_store.py:76-167`): quelle mai viste nascono, quelle gia' aperte vengono aggiornate, quelle risolte in passato vengono riaperte, quelle che l'utente aveva «ignorato» sono saltate per sempre (`advisory_store.py:152`).

Qui sta il comportamento che conviene conoscere prima di ogni altro. La riconciliazione chiude come «rientrata da sola» (`resolved_auto=1`) ogni segnalazione aperta che non compare piu' fra i candidati (`advisory_store.py:153-162`) — e non ha modo di sapere se il candidato manca perche' il problema e' finito o perche' la lettura corrispondente e' fallita. Se Home Assistant non risponde, **tutte** le segnalazioni sulle entita' si chiudono; se il Supervisor e' momentaneamente irraggiungibile, si chiudono tutte quelle sugli add-on. Trenta minuti dopo tornano, ma come nuove.

**Cosa vede l'utente.** Nella maggior parte dei casi: niente. La notifica push parte **solo** per le segnalazioni di severita' alta, e solo se sono nuove, riaperte o appena innalzate a quella severita' (`health_scan.py:150-155`), con un silenzio di dodici ore sullo stesso problema (`health_scan.py:41,161-163`). Batterie, entita' morte, automazioni spente, aggiornamenti: non generano mai un avviso. Una segnalazione grave produce **esattamente un push nella sua vita**: se resta aperta, ai giri successivi risulta solo «aggiornata» e non e' piu' candidata a nulla.

Nell'interfaccia le segnalazioni vivono in tre posti diversi. Un contatore nella barra laterale, calcolato una sola volta al caricamento della pagina e mai piu' aggiornato (`static/config/main.js:127-134`, montato a `main.js:283-288`). Una lista di card nella Dashboard, con i pulsanti «Ho capito» e «Ignora» (`static/config/dashboard.js:205-250`); il pulsante che porta a una correzione compare **solo** per il caso del dominio pericoloso verde (`dashboard.js:220-221`) — per gli altri sette controlli non c'e' alcuna azione se non prenderne atto. E infine la chat, dove HIRIS le riferisce soltanto se glielo si chiede (`tools/advisory_tools.py:59-97`).

C'e' una condizione in cui le due superfici si contraddicono in faccia all'utente: la Dashboard sceglie fra schermata di benvenuto e schermata piena **in base al numero di Chatbot configurati** (`dashboard.js:353-373`). Con zero Chatbot mostra l'onboarding e non interroga affatto le segnalazioni, mentre il contatore laterale continua a mostrarne il numero. Si riceve un push, si tocca, si arriva su una pagina di benvenuto.

**Quando fallisce.** Silenziosamente e per intero: l'involucro del giro periodico cattura qualunque eccezione e la scrive solo nel log dell'add-on (`server.py:2405-2422`). La Dashboard di un Brain morto e quella di una casa perfettamente sana sono identiche. Le due azioni disponibili hanno effetti asimmetrici: «Ho capito» toglie la segnalazione dalla lista e dal contatore, che filtrano lo stato `open`, ma la lascia visibile allo strumento di chat (`advisory_store.py:45`) — cioe' HIRIS in conversazione continua a citare un problema che la UI dichiara archiviato. «Ignora» e' terminale e senza ritorno: non esiste alcuna rotta che riporti una segnalazione allo stato aperto (`advisory_store.py:37`), e se lo stesso problema si ripresenta fra sei mesi quel riferimento e' morto. In entrambi i casi il contatore laterale resta al valore vecchio fino a un ricaricamento completo della pagina (`dashboard.js:259-265`).

Va detto di passaggio che esiste un secondo braccio del Brain, quello che ragiona in modo olistico e produce «suggerimenti» o proposte (`server.py:2256-2386`). E' spento di default (`watcher/policy.py:31`) e, quando acceso, gira una volta al giorno. Poiche' il percorso di scansione non scrive nulla nel registro dei ragionamenti, la sezione «Stream ragionamenti» della Dashboard resta permanentemente vuota su un'installazione predefinita, anche dopo quarantotto scansioni al giorno.

---

### 5.2 «Creami un'automazione»

**A cosa serve.** E' il gesto piu' naturale che si chiede a un assistente domestico: descrivere a parole un'automazione e ritrovarsela in Home Assistant.

**Da dove si entra.** Dalla chat, scrivendo la richiesta. Il fatto strutturale che governa tutto il resto e' che **nessuno strumento crea un'automazione**: l'unica strada e' `create_automation_proposal` (`tools/proposal_tools.py:84`), che salva una riga in SQLite e si ferma li'. L'automazione nasce in Home Assistant solo quando l'utente preme «Attiva» in una pagina diversa (`api/handlers_proposals.py:52`). Il flusso e' quindi spezzato in due transazioni scollegate, separate da minuti o da giorni.

**Il percorso, prima meta'.** Il messaggio parte, la casella di testo si blocca e compaiono tre puntini (`static/chat/send.js:82-99`). Il server valida (messaggio vuoto → 400, oltre 4000 caratteri → 413), risolve il Chatbot e — se `chatbot_id` non esiste — ricade sul default **senza dirlo a nessuno** (`handlers_chat.py:156-166`). Poi il modello lavora, con un catalogo di strumenti che nel caso predefinito e' **completo**: il Chatbot di default ha la lista dei permessi vuota (`chatbot_engine.py:233`) e la lista vuota viene tradotta in «nessun filtro» (`handlers_chat.py:230`). Quale strumento il modello scelga — una proposta, uno script, una task — non e' governato da nessuna istruzione di sistema: la sola guida e' il testo della descrizione dello strumento (`proposal_tools.py:26-30`).

Se la proposta viene salvata, il modello riceve una conferma con l'identificativo e la frase «L'utente puo' attivarla dalla sezione Proposte» (`proposal_tools.py:171-178`).

**Cosa vede l'utente.** La bolla di testo che il modello ha deciso di scrivere. Nessun elemento di interfaccia conferma che la proposta esista, tranne i «chip» degli strumenti chiamati — che sono un pannello di debug — e la voce «Proposte» nella barra laterale, il cui contatore si aggiorna con un giro ogni trenta secondi (`static/chat/proposals.js:309`). Nessuna notifica di alcun genere.

**Il percorso, seconda meta'.** Nella pagina Proposte la card mostra tipo, data, nome, descrizione, motivazione e due pulsanti (`chat/proposals.js:43-69`). **Non mostra la configurazione**: l'anteprima esiste per plance, script e scene, non per le automazioni (`static/config/proposals.js:33-41`), e l'endpoint di dettaglio che la restituirebbe non e' chiamato da nessun frontend (`handlers_proposals.py:25`). Il dato e' gia' nel payload della lista — semplicemente non viene disegnato. Si preme «Attiva» su condizioni e azioni che non si sono mai viste.

Alla conferma, HIRIS scrive su Home Assistant (`proxy/ha_client.py:205-317`). Il caso normale — «creami un'automazione», nessun identificativo indicato — passa da un ripiego per nome: se esiste gia' un'automazione il cui nome coincide, e il match e' unico, **quella viene sovrascritta** (`ha_client.py:285-288`). Il comportamento e' documentato nella descrizione dello strumento, cioe' detto al modello (`proposal_tools.py:53-59`), mai all'utente che approva. A differenza delle plance, qui non viene salvato nessuno snapshot.

**Quando fallisce.** In tre modi che l'utente non distingue.

Il primo: la scrittura riesce ma il ricaricamento delle automazioni no. Il codice tenta il ricaricamento, ignora il valore di ritorno e restituisce comunque successo (`ha_client.py:311-317`); e la funzione sottostante non solleva mai eccezioni, restituisce `False` (`ha_client.py:186-196`). L'utente legge «attivata» e non trova l'automazione nell'interfaccia di Home Assistant fino al riavvio.

Il secondo: il doppio clic. Il livello che parla col server considera «riuscito» lo stato HTTP e non il campo `ok` del corpo (`config/proposals-core.js:28-31`); poiche' la risposta e' comunque 200, due clic ravvicinati disegnano due volte «Proposta attivata» in verde mentre la scrittura su Home Assistant e' avvenuta due volte, la seconda passando dal ripiego per nome (`handlers_proposals.py:59`, `proposal_store.py:147-151`).

Il terzo: il tempo. Dopo sette giorni una proposta ancora in attesa viene archiviata, dopo trenta cancellata (`proposal_store.py:165-185`), senza alcun avviso; una proposta archiviata non e' piu' applicabile e la sua scheda non ha pulsanti. L'automazione chiesta la settimana prima e' semplicemente sparita.

In tutti i casi di errore reale, i messaggi costruiti con cura lato server — «non ho potuto verificare», «l'identificativo non esiste» — non arrivano mai a destinazione: il frontend traduce lo stato HTTP in quattro frasi generiche e mette il dettaglio in console (`proposals-core.js:49-67`). Dopo l'approvazione non c'e' alcun riscontro che l'automazione esista davvero, nessun collegamento a Home Assistant, e la chat non ne sa nulla: al turno successivo il modello, per sapere com'e' andata, deve andare a rileggere le automazioni.

---

### 5.3 L'azione rischiosa, la notifica, il tocco

**A cosa serve.** E' il meccanismo di sicurezza del prodotto: le azioni classificate come gialle o rosse nel semaforo non si eseguono subito, ma chiedono una conferma umana esplicita.

**Da dove si entra.** Da tre porte diverse, ed e' la prima cosa da sapere: **non esiste un solo flusso, ne esistono tre**, con tre esperienze utente distinte tutte chiamate «giallo». Dalla chat si passa dal semaforo del dispatcher e si ottiene una conferma privata con codice usa e getta (`tools/dispatcher.py:197`). Dal gateway MCP si passa da un controllo scritto a mano che non chiama la stessa funzione (`handlers_execute.py:181-235`) e si ottiene una notifica con i pulsanti Approva/Nega. Dagli Agentbot si passa da un terzo percorso ancora (`watcher/executor.py:22`) che non crea nessuna conferma e produce invece una proposta. Le task pianificate sono una quarta variante.

**Il percorso, dalla chat.** Il modello chiede l'azione; il bersaglio viene normalizzato; un'azione che punta a un'intera area o a un piano viene rifiutata prima di tutto il resto (`dispatcher.py:433-435`); poi interviene il semaforo (`security/semaphore.py:123-160`), che applica per prima la lista dei domini pericolosi — serrature, allarmi, tapparelle, sirene, garage — e poi il livello peggiore fra i bersagli. Se il verdetto e' «chiedi conferma», HIRIS crea una richiesta congelata con scadenza di cinque minuti e un codice a sei cifre, e la manda come notifica privata all'utente (`server.py:415-467`).

**Cosa vede l'utente.** In chat, la frase: «Ho bisogno della tua conferma: tocca "Conferma" nella notifica sul telefono, oppure dimmi il codice che ti ho inviato» (`dispatcher.py:215-219`). Sul telefono, in una installazione non manomessa a mano, **niente**.

Questa e' la caratteristica piu' importante del flusso, e va detta senza giri di parole. La notifica privata parte solo se esiste una mappatura fra l'identita' dell'utente e un servizio di notifica personale (`handlers_gateway_policy.py:228-250`). Quella mappatura non e' popolabile da nessuna superficie: non c'e' nell'opzione dell'add-on, la pagina Gateway salva soltanto il servizio globale (`static/config/gateway-route.js:348-352`), e nessun altro punto del codice la scrive. La descrizione dell'opzione dell'add-on rimanda a una sezione «Notify users» che non esiste nel prodotto (`translations/en.yaml:124`). Il risultato pratico: **su un'installazione di serie il percorso di conferma della chat non parte mai**. Il modello dice «guarda il telefono», e non c'e' nulla da guardare ne' nulla da confermare, perche' il codice a sei cifre vive solo dentro quel messaggio push e la coda lo nasconde (`handlers_gateway_pending.py:100`).

Anche quando la notifica parte, il codice non verifica che sia arrivata: la funzione di invio dichiara di restituire vero solo in caso di consegna riuscita (`handlers_gateway_pending.py:217-221`) ma restituisce vero ogni volta che la chiamata non solleva — e la chiamata non solleva mai, restituisce `False` (`proxy/ha_client.py:186-196`). E in ogni caso quel valore **non viene mai letto**: chi compone la risposta guarda solo se la richiesta e' stata creata (`dispatcher.py:213`).

**Il tocco.** Se la notifica arriva, i due pulsanti sono azionabili a telefono bloccato: non e' richiesta autenticazione (`handlers_gateway_pending.py:190-203`). Il tocco non e' legato all'utente destinatario — chi riceve la notifica approva, chiunque sia (`handlers_gateway_pending.py:278-288`), mentre la via del codice a sei cifre e' invece vincolata all'identita'. Due porte sulla stessa richiesta, con due contratti d'identita' diversi.

**L'esecuzione, e cosa si perde.** Una volta approvata, la richiesta viene eseguita saltando integralmente semaforo e guardia di gruppo (`dispatcher.py:423-441`), il che e' dichiaratamente voluto: la conferma umana autorizza esattamente quel comando. Ma sul percorso della chat i controlli del perimetro del Chatbot — quali entita' e quali servizi quella persona puo' toccare — stanno **dopo** il semaforo (`dispatcher.py:436` contro `442-455`), e un verdetto «chiedi conferma» ritorna prima di raggiungerli. All'approvazione l'esecuzione avviene senza alcun perimetro. Un'azione fuori dai confini del Chatbot, ma di livello giallo, genera una conferma e all'approvazione viene eseguita. E' esattamente l'ordine inverso a quello che il motore delle task ha adottato (`task_engine.py:459-476`), e a quello che nello stesso file hanno gia' gli altri tre strumenti che agiscono su Home Assistant.

**Quando fallisce.** L'esito reale dell'esecuzione si perde in tre passaggi consecutivi: la chiamata a Home Assistant restituisce `False` invece di sollevare, il dispatcher lo propaga cosi' com'e', e l'approvazione lo impacchetta come `{"ok": true, "result": false}` marcando la richiesta come «approvata» (`handlers_gateway_pending.py:264-266`). La pagina Approvazioni verifica il fallimento con una condizione che quel `false` non soddisfa (`gateway-route.js:196-197`): nessun avviso, la riga sparisce dalla coda e basta. In chat, il modello riceve la stessa forma e — istruito a non aggiungere cautele quando uno strumento e' andato a buon fine (`claude_runner.py:134-135`) — dira' che e' fatto.

Due dettagli completano il quadro. La coda «ad alta frizione» pensata per serrature e allarmi mostra soltanto il nome del comando e due pulsanti, mai l'entita' o il payload (`gateway-route.js:117-137`), pur avendo il dato gia' sul client. E la richiesta di conferma per gli strumenti diversi da `call_ha_service` produce etichette senza senso, perche' il messaggio e' costruito assumendo la forma di quello strumento: sul telefono si legge letteralmente «confermi "None.None" su (nessuna entita')?» (`server.py:449`, `server.py:202`).

---

### 5.4 «Ricordati che...»

**A cosa serve.** Dare a HIRIS una memoria: preferenze, fatti sulla casa, scadenze, cose da non ripetere ogni volta.

**Da dove si entra.** Dalla chat, con una frase qualunque. E qui il flusso si biforca prima ancora di cominciare, perche' esistono **due strumenti** per la stessa frase e nessuna regola che dica quale usare. Uno scrive subito, senza approvazione (`tools/memory_tools.py:110-113`); l'altro crea una proposta che l'utente deve approvare (`tools/knowledge_tools.py:120`). Il prompt di sistema nomina la memoria una volta sola, in un elenco di capacita', e non disambigua mai (`claude_runner.py:127-137`). Due file diversi dichiarano ciascuno, nei propri commenti, di essere «quello che il modello chiama quando l'utente dice ricordati che...» (`static/chat/knowledge.js:3-6` e `tools/memory_tools.py:116-118`): non possono essere entrambi veri, e nel codice non c'e' nulla che decida. I due esiti hanno cicli di vita, superfici di approvazione e percorsi di richiamo completamente diversi.

**Il percorso, ramo diretto.** Il ricordo viene trasformato in vettore semantico e, se il vettore non si puo' calcolare, **non viene scritto nulla** (`memory_tools.py:126-133`) — scelta corretta, perche' un ricordo senza vettore non sarebbe mai piu' ritrovabile. La riga nasce gia' approvata, con proprietario derivato dall'identita' dell'utente ingress o dal valore di ripiego `home`, legata al Chatbot corrente e con una scadenza a novanta giorni.

C'e' pero' una condizione da conoscere: HIRIS considera la memoria «disponibile» quando esiste un oggetto di embedding, e l'oggetto esiste sempre — anche nella forma vuota che restituisce liste vuote (`backends/embeddings.py:175-205`). Il default dell'add-on e' proprio questo caso (`config.yaml:68-70`), e con provider vuoto non viene emesso nemmeno un avviso a log (`embeddings.py:203-205`). Su un'installazione appena fatta, quindi, lo strumento viene annunciato al modello come disponibile e fallisce solo al momento della chiamata; e il pannello dei modelli mostra le variabili d'ambiente grezze, non la capacita' effettiva (`handlers_models.py:159-162`), quindi puo' dichiarare «configurato» una memoria completamente morta.

**Cosa vede l'utente.** Dipende interamente da come il modello racconta il risultato: l'errore torna come risultato di strumento senza alcuna marcatura di errore (`claude_runner.py:821-826`). E, cosa piu' rilevante, **non esiste nessuna superficie che elenchi i ricordi salvati**: le rotte disponibili sono quattro (`server.py:2833-2836`) e riguardano solo la coda delle proposte in attesa. Dopo «ricordati che...» non c'e' alcun modo di vedere, correggere o cancellare cio' che HIRIS ha memorizzato. Il pannello «Memoria» della chat esiste, fa polling ogni trenta secondi e ha persino l'etichetta giusta, ma mostra solo gli elementi in attesa — e un ricordo del ramo diretto nasce gia' approvato, quindi non ci comparira' mai.

**Il ritorno.** A ogni turno di chat, HIRIS cerca i ricordi piu' vicini alla domanda e li inserisce nel contesto (`handlers_chat.py:272-305`). Due caratteristiche cambiano molto l'esperienza. La prima: la ricerca **non ha soglia di somiglianza** (`brain/knowledge_store.py:301-303`), quindi con pochi ricordi in archivio tornano tutti a ogni domanda, qualunque sia l'argomento. La seconda: un vettore di dimensione diversa non e' un errore, vale zero (`backends/embeddings.py:219-227`); cambiare modello di embedding rende muti tutti i ricordi precedenti senza un avviso, e li lascia in coda ai risultati con punteggio nullo.

Il blocco di richiamo automatico chiede sempre e solo il tipo «memoria» (`handlers_chat.py:288`) e non consulta il livello di accesso alla conoscenza configurato sulla persona: un Chatbot impostato a «nessun accesso» riceve comunque i ricordi nel prompt. Quando il richiamo fallisce, l'eccezione e' inghiottita con un avviso a log (`handlers_chat.py:304-305`): l'utente riceve una risposta normale, da un assistente che ha semplicemente dimenticato tutto.

**Chi vede che cosa.** La scrittura usa l'identita' dell'utente ingress; la lettura pure, ma le due superfici di chat non sono equivalenti. Un ricordo scritto con identita' e riletto senza (per esempio da un pannello che non passa dall'ingress) **non torna**; scritto senza identita' e riletto con, torna a tutti gli utenti di casa (`dispatcher.py:600` contro `handlers_chat.py:141`, clausola a `knowledge_store.py:257`). L'isolamento fra utenti costruito con cura sull'archivio dei ricordi non esiste sull'archivio delle conversazioni, che contiene lo stesso testo in chiaro (`chat_store.py:80-94`).

**Il ramo dei percorsi proattivi.** Sentinella, briefing quotidiano e revisione olistica cercano nella memoria con un filtro che chiede esplicitamente il tipo «memoria» (`brain/reasoner_memory.py:29`) ma con un vincolo che nessun ricordo utente puo' soddisfare: la clausola si riduce a «Chatbot non impostato» (`knowledge_store.py:258`), mentre **tutti** gli scrittori di ricordi impostano sempre un Chatbot. In pratica i percorsi autonomi non vedono mai un ricordo dell'utente; l'unico tipo che davvero recuperano e' quello prodotto internamente dalla digestione delle conversazioni.

**Quando fallisce, e come finisce.** La scadenza a novanta giorni pulisce solo i ricordi del ramo diretto; quelli approvati a mano non scadono mai (`server.py:1512-1518`, `knowledge_store.py:438-451`). Cancellare una persona cancella tutti i ricordi legati a quella persona, compresi quelli salvati da altri utenti di casa attraverso di essa, e se la cancellazione fallisce l'API risponde comunque «eliminato» (`handlers_chatbots.py:207-221`). Non esiste alcuna cancellazione mirata di un singolo ricordo approvato.

Infine, il caso limite: in modalita' «chat via abbonamento» il turno esce dal server prima del richiamo, prima del modello locale e prima del dispatcher (`handlers_chat.py:193`), e il contesto trasmesso al runner esterno non contiene memoria. «Ricordati che...» in quella modalita' non salva nulla, senza errori e senza log.

---

### 5.5 La task pianificata

**A cosa serve.** Chiedere a voce qualcosa che deve succedere dopo: «spegni il boiler alle 22», «ricordamelo fra mezz'ora», «ogni sera fra le 22 e le 6, se la temperatura scende, accendi».

**Da dove si entra.** Dalla chat, da un agente o dal gateway. Il modello chiama lo strumento di creazione, il cui schema accetta come innesco e come azioni **qualunque dizionario**, senza sotto-campi obbligatori (`tools/task_tools.py:7-50`). Il dispatcher verifica che il tipo di azione sia fra quelli ammessi e, solo per le chiamate di servizio, controlla il perimetro dei servizi (`dispatcher.py:457-498`). Il motore verifica che l'innesco abbia un tipo noto e valida con cura la **condizione** (`task_engine.py:26-49, 122-154`), ma non valida nessun sotto-campo dell'innesco.

**Cosa vede l'utente.** «Task creato», detto dal modello, e una riga «In attesa» nella pagina Task e nel pannello della chat. Questa riga compare **anche quando la pianificazione e' fallita**: la registrazione del lavoro periodico avviene dentro un blocco che, in caso di errore, scrive una riga di log e prosegue (`task_engine.py:281-318`). Un innesco senza il campo dei minuti, un orario scritto «6pm», una data scritta «domani» producono tutti lo stesso esito: task creato, in attesa, **nessun lavoro pianificato**, mai eseguito, mai scaduto, mai raccolto dalla pulizia periodica. Resta a vita nel contatore.

**Lo scatto.** Quando il momento arriva, il motore valuta la condizione ed esegue le azioni in ordine. La classificazione dell'esito e' il punto in cui questo flusso si allontana di piu' da cio' che l'utente vede: **soltanto** una stringa che comincia per «skipped» e' considerata un non-successo; tutto il resto e' registrato come `:OK` (`task_engine.py:410-414`). Poiche' la chiamata a Home Assistant restituisce `False` invece di sollevare, un'azione rifiutata da Home Assistant — entita' inesistente, servizio sbagliato, errore 500 — risulta «Eseguito · call_ha_service:OK», con il segnaposto verde (`labels.js:49`). Lo stesso vale per le notifiche, che restituiscono `False` in sei punti diversi (`tools/notify_tools.py:131-199`): una task il cui unico scopo era avvisare puo' risultare eseguita senza che nessuna notifica sia partita.

**Il caso giallo.** Se l'azione tocca qualcosa di rischioso, il motore chiede la conferma con lo stesso meccanismo descritto in 5.3 — e quindi eredita lo stesso vicolo cieco: senza la mappatura utente-canale privato, che nessuna superficie popola, la conferma non parte e l'azione viene saltata (`task_engine.py:499-501`), lasciando come unica traccia un avviso a log. Se invece la conferma parte, la stringa restituita e' «pending: confirmation ...», che non comincia per «skipped» e quindi viene registrata come `:OK`: il task diventa «Eseguito», il lavoro periodico viene rimosso, e l'azione non e' mai avvenuta. Se nessuno tocca la notifica entro cinque minuti, la richiesta svanisce senza lasciare traccia da nessuna parte.

La conferma, poi, si presenta all'utente come se venisse da una conversazione: la richiesta e' creata con provenienza «chat» (`server.py:457`) e il messaggio push non nomina ne' l'etichetta del task ne' il suo identificativo (`server.py:180-205`). Si riceve, a un'ora arbitraria, la richiesta di confermare un'azione attribuita a una chat che non si e' avuta, senza alcun modo di risalire al task che l'ha generata.

**Altri comportamenti che vale la pena conoscere.** Un task marcato come non monouso ma con un innesco che scatta una volta sola torna in attesa dopo l'esecuzione e non scattera' mai piu', restando per sempre nel contatore (`task_engine.py:432-433`). Un innesco a finestra oraria malformato solleva a ogni tick, indefinitamente. Un rinvio «fra trenta minuti» riparte da zero a ogni riavvio dell'add-on, mentre una data gia' passata resta in attesa per sempre. Un'azione bloccata o in attesa di conferma non ferma le azioni successive, perche' la regola «interrompi in caso di fallimento» e' letta solo dentro la gestione delle eccezioni (`task_engine.py:419-421`): un task «accendi la caldaia, poi avvisa che e' accesa» manda subito l'avviso mentre l'accensione attende una conferma che potrebbe non arrivare.

**Quando fallisce.** Mai in modo visibile. Non esiste alcuna notifica di fallimento (`task_engine.py` non chiama l'invio notifiche fuori dal ramo azione), nessuna entita' in Home Assistant, nessuna voce nel Brain. Lo si scopre solo aprendo la pagina Task ed espandendo la riga, perche' il dettaglio dell'esito non compare nella riga chiusa (`tasks-route.js:62-65`); e dopo sette giorni la riga viene rimossa del tutto. Un task fermo in stato «in corso» non e' ne' cancellabile ne' raccoglibile, e nella UI il pulsante di annullamento non viene nemmeno disegnato.

Messo in fila, il caso peggiore attraversa cinque aree: si chiede in chat di spegnire il boiler alle 22, il boiler e' giallo, la creazione non guarda i livelli, il modello dice «fatto», alle 22 la conferma non parte perche' il canale non e' configurabile, l'azione viene saltata, il task diventa verde «Eseguito», nessuna notifica avvisa, e dopo sette giorni la riga sparisce. Il boiler e' rimasto acceso tutta la notte.

---

### 5.6 Lo stesso comando da fuori: il gateway MCP

**A cosa serve.** Permettere a un modello esterno — Claude su claude.ai, tramite il gateway — di agire sulla casa, con un perimetro deciso dalla pagina «Accessi Gateway».

**Da dove si entra.** Da una chiamata HTTP che arriva da fuori host, non dall'ingress. Il confronto con la chat e' il punto interessante, perche' «la chat» non e' un percorso solo ma due, e la differenza fra i due e' piu' grande di quella fra chat e gateway: la chat classica esegue nello stesso processo con il perimetro del Chatbot, mentre la chat via abbonamento esce, gira attorno e **rientra dallo stesso endpoint del gateway**, con il perimetro globale del semaforo e senza che il Chatbot c'entri piu' nulla. A distinguere le due cose e' un solo header (`handlers_execute.py:328`).

**Il percorso.** La richiesta esterna supera il middleware di autenticazione con un token condiviso, marcandosi come «token» invece che «ingress» — ed e' proprio quella singola parola a impedirle, piu' avanti, di auto-approvarsi le proprie richieste in attesa (`middleware_internal_auth.py:66-98`, `handlers_gateway_pending.py:292-311`). E' esente dal controllo anti-CSRF perche' presenta un token valido. Poi passa da un secondo controllo del token, deliberatamente indipendente, e da due allowlist: lo strumento deve essere fra quelli ammessi in assoluto e fra quelli concessi dalla policy (`handlers_execute.py:155-176`).

Qui c'e' una asimmetria che conviene capire bene: **in chat questo controllo non esiste**. L'elenco degli strumenti permessi a un Chatbot filtra soltanto cio' che viene mostrato al modello, non cio' che il dispatcher accetta di eseguire (`claude_runner.py:712`, contro `dispatcher.py:235-250` che non ha alcun parametro equivalente). Il perimetro degli strumenti della chat e' un **suggerimento**; quello del gateway e' un **controllo**.

Segue un pre-controllo del semaforo scritto appositamente per questo percorso (`handlers_execute.py:181-253`), che rifiuta i bersagli di gruppo, rifiuta i livelli spenti, forza a rosso il giallo sui domini pericolosi e, per giallo e rosso, crea una richiesta di approvazione con notifica. In chat questo passo non esiste: il suo equivalente vive dentro il semaforo del dispatcher e produce un'esperienza diversa. Poi, solo per il gateway, si applica la potatura delle entita' escluse dalla lettura, in ingresso e in uscita.

**Cosa vede l'utente.** Se il comando e' giallo, una notifica azionabile sul telefono: «Claude chiede: light.turn_off · Approva/Nega». Se e' rosso, una notifica informativa e una voce nella pagina Accessi Gateway. Il messaggio e' composto con dominio e servizio soltanto (`handlers_execute.py:238-245`): **l'entita' non compare**, per l'unica notifica del prodotto che si approva con un tocco. Il codice della chat spiega, in un commento esplicito, perche' il messaggio push **deve** mostrare l'entita' — un modello sotto attacco potrebbe chiedere un'azione su un'entita' di cui la conversazione non parla — e il percorso del gateway costruisce il messaggio altrove ignorando quel principio.

Il caso concreto che ne deriva: un dominio impostato a giallo, un comando senza entita' di destinazione, una notifica «Claude chiede: light.turn_off», un tocco, e l'azione parte a raggio di dominio. Lo stesso vale, in rosso, per le serrature: senza destinazione si usa il livello del dominio, la voce in coda mostra soltanto `lock.unlock` perche' non c'e' un target da mostrare, e all'approvazione l'esecuzione salta sia il semaforo sia il controllo che avrebbe preteso un'entita'.

**Un'inversione di cautela.** La notifica del gateway ricade sul servizio globale, il cui default e' la dashboard condivisa di Home Assistant (`handlers_gateway_policy.py:77`), e ottiene il tocco per approvare. La chat rifiuta esattamente quel canale — sia il servizio globale sia le notifiche persistenti — e senza un canale privato per utente fallisce chiudendo (`handlers_gateway_policy.py:228-250`, `server.py:441-448`). Il risultato e' che il richiedente remoto e automatico ottiene l'approvazione con un tocco, mentre l'utente umano e locale viene degradato a un messaggio d'errore generico.

**Quando fallisce.** In modi che il chiamante non puo' distinguere. Lo stesso endpoint risponde in tre forme diverse a tre tipi di «negato»: 403 con un errore per le allowlist, 200 con un esito negativo dentro un involucro per il semaforo, 200 con un errore generico per ogni guasto del dispatcher. Il client interno che HIRIS usa per il proprio MCP ne gestisce una sola (`mcp/local_client.py:47-51`): il ramo `resp.status != 200` sostituisce i messaggi diagnostici costruiti con cura con la frase «execute-API status 403» (`:50`), mentre le due forme che arrivano con stato 200 passano intatte da `:51` e non vengono riconosciute come negazioni. Peggio: il registro di audit dell'MCP interno cerca l'errore nella chiave sbagliata dell'involucro (`mcp/server.py:29`), quindi ogni azione negata — dal semaforo, dalla denylist, da Home Assistant — viene registrata come riuscita.

Sul fronte dell'utente, un'approvazione riuscita seguita da un'azione fallita produce lo stesso silenzio gia' visto in 5.3: il messaggio «Comando approvato ma NON eseguito», scritto apposta per questo caso, e' irraggiungibile perche' il fallimento arriva nella forma `false` e non nella forma prevista (`gateway-route.js:167-171, 196-197`), e il codice della richiesta e' gia' consumato. E dal lato remoto non c'e' alcuna via di ritorno: il gateway riceve «in attesa di approvazione» e poi nulla — approvato, rifiutato e scaduto sono indistinguibili, la voce sparisce e basta.

Infine, un effetto laterale che tocca i dati: l'etichetta di provenienza dichiarata dal chiamante viene validata solo nei caratteri ammessi (`handlers_execute.py:38-47`) e poi **riusata come identificatore del Chatbot** a valle (`handlers_execute.py:352`). Un'etichetta diventa cosi' una chiave di scoping della conoscenza: cio' che il gateway salva finisce in uno spazio, cio' che la chat via abbonamento salva in un altro, e cio' che la chat classica salva in un terzo.

---

### 5.7 Dove le due letture non coincidono

Due punti su cui il materiale raccolto si contraddice. Li registro entrambi senza sceglierne uno: la contraddizione e' essa stessa un dato.

**Se il ramo «chat via abbonamento» abbia strumenti oppure no.** Una lettura afferma che il contesto passato al runner esterno e' composto da tre soli campi e che quindi in quel ramo «non c'e' nessuna memoria, nessun tool» (`handlers_chat.py:94-98`). Un'altra lettura, sullo stesso ramo, descrive il runner che lancia il processo esterno con un elenco di strumenti MCP predefiniti — fra cui la creazione di proposte di automazione — che rientrano nel server attraverso l'endpoint di esecuzione (`agent/runner.py:25-32`, `mcp/local_client.py:35`). Le due affermazioni si conciliano se si intende che il *contesto trasmesso nel job* non contiene strumenti mentre il *processo esterno* ne ha comunque una propria lista, e che fra quella lista non ci sono strumenti di memoria; ma la prima lettura, presa alla lettera, dice qualcosa di piu' forte di quanto la seconda consenta. Chi legge deve sapere che il confine fra «il job non porta strumenti» e «quel ramo non puo' usare strumenti» non e' stato stabilito con certezza.

**Se la conoscenza scritta da fuori esista o no.** Una lettura riporta che l'MCP non espone alcuno strumento di memoria, con una ricerca testuale a supporto. Un'altra descrive nel dettaglio che cosa succede quando dal gateway arrivano richieste di salvataggio e richiamo della conoscenza — proprietario forzato a `home`, Chatbot derivato dall'etichetta di provenienza, sorgente marcata come «chat» (`dispatcher.py:681-707`, `knowledge_tools.py:119`). Anche qui la conciliazione probabile e' che «memoria» e «conoscenza» siano due famiglie distinte di strumenti e che solo la seconda attraversi quel confine; ma le due mappe usano lo stesso vocabolario per cose diverse, e questo di per se' descrive bene il prodotto: memoria e second brain sono un unico archivio con due porte, e la distinzione fra le due non e' leggibile ne' dai nomi ne' dalle interfacce.

**Una differenza che invece non e' una contraddizione, ma va detta.** I canali di notifica predefiniti sono tre, e diversi: il Brain manda i propri avvisi al servizio configurato in una impostazione con default `notify.notify` (`server.py:1311`); il gateway ricade sul servizio globale della pagina Accessi, con default `notify.persistent_notification` (`handlers_gateway_policy.py:77`); la conferma della chat rifiuta entrambi e pretende un canale privato per utente che nessuna superficie permette di impostare. Tre notifiche dello stesso prodotto, tre destinazioni diverse, e solo la terza e' quella che protegge le azioni pericolose.

---

# 6. La superficie HTTP, endpoint per endpoint

Questa sezione e' un censimento, non un commento: elenca per intero la superficie HTTP dell'add-on
— ogni rotta registrata, chi puo' chiamarla, cosa fa, cosa restituisce e con quali codici
fallisce — nell'ordine in cui le rotte sono raggruppate per funzione. La sezione 3 racconta
*come* funziona il guscio del server; questa dice *che cosa c'e'*. E' l'elenco su cui lavorano la
revisione tecnica e quella di sicurezza.

### Il conteggio

Verificato aprendo il file: in `server.py` le chiamate `app.router.add_*` sono **65** (righe
2792-2894), di cui **1 sola** e' il mount statico (`add_static`, server.py:2792). Gli endpoint veri
e propri, metodo piu' percorso, sono quindi **64** — lo stesso numero dichiarato alla sezione 3 —
e qui sono censiti tutti, piu' il mount statico per completezza: 65 voci. Tutte le registrazioni
stanno dentro `create_app()` (server.py:2778-2896).

### Chi puo' chiamare

Tre catene di middleware sono montate sull'applicazione intera
(server.py:2779-2783), quindi valgono per **ogni** rotta di questo censimento,
comprese `/`, `/config` e `/static/*`:

- `internal_auth_middleware` (`api/middleware_internal_auth.py:67`).
  Passa senza token se la richiesta e' Ingress genuino: header `X-Ingress-Path`
  che matcha `^/api/hassio_ingress/[A-Za-z0-9_\-]+(/.*)?$` **e** IP sorgente dentro
  le CIDR del Supervisor (default `172.30.32.0/23`) — middleware_internal_auth.py:13,
  17, 30-63. In quel caso imposta `request["auth_via"] = "ingress"` (riga 77).
  Altrimenti richiede `X-HIRIS-Internal-Token` uguale a `app["internal_token"]`
  (confronto `hmac.compare_digest`, riga 93) e imposta `auth_via = "token"` (riga 97).
  Senza token configurato: **401 `{"error": "unauthorized"}`** (riga 91), salvo
  `HIRIS_ALLOW_NO_TOKEN=1` che apre tutto e imposta `auth_via = "no_token"`
  (righe 20-22, 82-85).
- `csrf_middleware` (`api/middleware_csrf.py:39`). Solo su `/api/*` e solo
  per metodi non sicuri (POST/PUT/PATCH/DELETE — `_SAFE_METHODS` riga 23): serve
  l'header `X-Requested-With` non vuoto (riga 44), oppure un `X-HIRIS-Internal-Token`
  valido (righe 31-35, 46), oppure `HIRIS_ALLOW_NO_CSRF=1` (righe 26-28). Altrimenti
  **403 `{"error": "csrf_required"}`** (riga 55).
- `_security_headers` (server.py:2757): non blocca nulla, aggiunge CSP, nosniff,
  Referrer-Policy, Permissions-Policy, COOP, e `Cache-Control: no-cache` su
  `/static/` (righe 2764-2774).

Nel seguito "ingress + token" significa quindi: raggiungibile sia dalla UI HIRIS
dietro Ingress sia da un chiamante server-to-server con il token interno (gateway
MCP, client MCP locale in-addon, proxy Retro Panel — vedi la docstring di
middleware_csrf.py:11-14). Le **due sole eccezioni** a questa regola generale sono
segnalate esplicitamente: `/api/execute` (richiede il token anche se sei Ingress) e
le due rotte di approvazione dei pending (rifiutano il token, vogliono Ingress).

Codici di errore comuni non ripetuti voce per voce: **404** per percorso
inesistente e **405** per metodo non registrato (routing aiohttp), **500** per
eccezione non gestita nell'handler.

## 6.1 Pagine e diagnostica di base

### GET / — server.py:2794
- Handler: `_serve_index`, server.py:2974.
- Chi: ingress + token (nessun controllo aggiuntivo; il CSRF non tocca i GET).
- Cosa fa: serve `app["html_index"]` (la SPA) iniettando in ogni riferimento
  `static/*.js|css` un fingerprint di contenuto `?v=HASH` (`_inject_version`,
  server.py:2960; `_asset_fingerprint`, server.py:2911).
- Restituisce: `text/html` con `Cache-Control: no-store` (`_NO_CACHE`, server.py:2899).
- Errori: **503** con corpo testuale `"UI not yet available"` quando `html_index`
  non e' ancora caricata (server.py:2976-2977).

### GET /config — server.py:2795
- Handler: `_serve_config`, server.py:2985.
- Chi: ingress + token.
- Cosa fa: identico a `/` ma serve `app["html_config"]`, la pagina di configurazione.
- Restituisce: `text/html`, `no-store`.
- Errori: **503** `"UI not yet available"` (server.py:2987-2988).

### GET /static/{...} (mount) — server.py:2792
- Handler: static handler di aiohttp (`add_static`, `show_index=False`).
- Chi: ingress + token (il middleware di auth non esclude `/static`).
- Cosa fa: serve i file sotto `static`. Il build stamp dell'intera
  cartella e' calcolato all'avvio (`_compute_build_stamp`, server.py:2936) e
  memorizzato in `app["build_stamp"]` (server.py:2791).
- Errori: **404** file inesistente; nessun listing di directory.

### GET /api/health — server.py:2796
- Handler: `_handle_health`, server.py:2996.
- Chi: ingress + token.
- Cosa fa: liveness + identita' della build effettivamente in esecuzione.
- Restituisce: `{"status": "ok", "version": <read_version()>, "build": <build_stamp>}`.
- Errori: nessuno specifico.

### GET /api/status — server.py:2797
- Handler: `handle_status`, `api/handlers_status.py:6`.
- Chi: ingress + token.
- Cosa fa: legge `app["engine"]` e conta i chatbot totali e abilitati.
- Restituisce: `{"version": ..., "agents": {"total": N, "enabled": M}}`.
- Errori: nessuno specifico (se `app["engine"]` mancasse sarebbe un 500).

### GET /api/config — server.py:2798
- Handler: `handle_config`, `api/handlers_config.py:4`.
- Chi: ingress + token.
- Cosa fa: espone il solo tema dell'interfaccia.
- Restituisce: `{"theme": app["theme"] | "auto"}`.
- Errori: nessuno.

## 6.2 Chat

### POST /api/chat — server.py:2801
- Handler: `handle_chat`, `api/handlers_chat.py:140`.
- Chi: ingress + token; POST quindi soggetto a CSRF.
- Cosa fa: un turno di conversazione. Risolve il proprietario
  (`resolve_owner`, handlers_chat.py:141), sceglie il chatbot da
  `body["chatbot_id"]` con fallback retro-compatibile `body["agent_id"]`
  (riga 156) e, se non esiste, il chatbot di default (riga 164). Applica il tetto
  di turni per sessione (righe 176-184). Se `chat_via_subscription` e' attivo e la
  coda di ragionamento e' cablata, **non** chiama alcun runner: accoda un job
  `kind="chat"` (`_enqueue_chat_job`, handlers_chat.py:66-100) dopo aver persistito
  il turno utente. Altrimenti chiama il runner locale, in streaming SSE se
  `Accept: text/event-stream` o `body["stream"] is True` (righe 342-416), oppure in
  sincrono (righe 418-495), con iniezione di memoria RAG, riassunti delle sessioni
  passate e contesto casa (righe 244-315).
- Restituisce: sincrono `{"response": str, "debug": {"tools_called": [...],
  "thinking_blocks": [...]}}` (riga 495; il codice OTP di `confirm_pending` e'
  mascherato, righe 476-484); asincrono **202** `{"status": "pending",
  "job_id": ...}` (riga 100); streaming: `text/event-stream`.
- Errori: **400** JSON non valido (riga 145) o `message` vuoto (riga 149);
  **413** messaggio oltre 4000 caratteri (riga 151); **409** c'e' gia' una
  risposta in arrivo per quella conversazione (riga 205); **429** tetto
  giornaliero di messaggi raggiunto (riga 212); **503** nessun runner
  configurato (riga 218). Attenzione: il tetto di turni risponde **200** con
  `{"error": "max_turns_reached", ...}` (righe 180-184), non un 4xx.

### GET /api/chat/reply/{job_id} — server.py:2802
- Handler: `handle_chat_reply_poll`, handlers_chat.py:103.
- Chi: ingress + token.
- Cosa fa: polling della risposta di un job di chat accodato dal ramo
  "abbonamento"; legge la riga della `reasoning_queue`.
- Restituisce: `{"status": "pending"}`, `{"status": "done", "reply": ...}` oppure
  `{"status": "error", "message": "La risposta non e' arrivata in tempo. Riprova."}`
  per job `expired`/`failed` (righe 118-126) e per job `decided` senza reply
  (righe 127-134) — tutti con codice **200**.
- Errori: **503** coda non configurata (riga 111); **404** job inesistente (riga 114).

### GET /api/chatbots/{agent_id}/chat-history — server.py:2815
- Handler: `handle_get_chat_history`, `api/handlers_chat_history.py:15`.
- Chi: ingress + token.
- Cosa fa: legge lo storico persistito della conversazione (`load_history`).
- Restituisce: `{"messages": [...]}`.
- Errori: **400** `{"error": "invalid agent_id"}` se l'id non matcha
  `^[a-zA-Z0-9_-]{1,64}$` (handlers_chat_history.py:8, 19-20).

### DELETE /api/chatbots/{agent_id}/chat-history — server.py:2816
- Handler: `handle_clear_chat_history`, handlers_chat_history.py:26.
- Chi: ingress + token; DELETE quindi soggetto a CSRF.
- Cosa fa: cancella lo storico persistito di quel chatbot (`clear_history`).
- Restituisce: `{"ok": true}`.
- Errori: **400** id non valido (riga 29).

## 6.3 Chatbot (CRUD, esecuzione, consumi, anteprima contesto)

Validazione dell'id condivisa: `_CHATBOT_ID_RE` e `_check_chatbot_id`,
`api/handlers_chatbots.py:10-16` (400 `invalid agent_id`).
Validazione del corpo: `_validate_chatbot_payload`, handlers_chatbots.py:19-87
(nome, liste di permessi, `response_mode`, `thinking_budget`, `allowed_endpoints`,
`knowledge_access`).

### GET /api/chatbots — server.py:2803
- Handler: `handle_list_chatbots`, handlers_chatbots.py:90.
- Chi: ingress + token.
- Cosa fa: elenca i chatbot arricchendoli con lo stato
  (`engine.get_chatbot_status`) e con il consumo per-chatbot letto dal runner
  (righe 96-115); un errore nel calcolo del consumo viene loggato e degradato a
  budget 0, non propagato (righe 111-113).
- Restituisce: array JSON di oggetti chatbot con `status`, `budget_eur`, `usage`.
- Errori: nessuno specifico.

### POST /api/chatbots — server.py:2804
- Handler: `handle_create_chatbot`, handlers_chatbots.py:142.
- Chi: ingress + token (CSRF).
- Cosa fa: valida e crea il chatbot via `engine.create_chatbot`. Se il modello e'
  un id OpenRouter privo di supporto tool, rifiuta (`_validate_openrouter_model`,
  righe 120-139).
- Restituisce: **201** con il chatbot serializzato (`asdict`).
- Errori: **400** JSON non valido (riga 146), campo `name` mancante (riga 151),
  payload non valido (riga 154), modello OpenRouter senza tool (riga 157).

### GET /api/chatbots/{agent_id} — server.py:2805
- Handler: `handle_get_chatbot`, handlers_chatbots.py:164.
- Chi: ingress + token.
- Cosa fa: restituisce un singolo chatbot.
- Restituisce: oggetto chatbot.
- Errori: **400** id non valido; **404** `{"error": "Not found"}` (riga 171).

### PUT /api/chatbots/{agent_id} — server.py:2806
- Handler: `handle_update_chatbot`, handlers_chatbots.py:175.
- Chi: ingress + token (CSRF).
- Cosa fa: aggiorna il chatbot con le stesse validazioni della creazione.
- Restituisce: chatbot aggiornato.
- Errori: **400** id/JSON/payload/modello OpenRouter; **404** inesistente (riga 193).

### DELETE /api/chatbots/{agent_id} — server.py:2807
- Handler: `handle_delete_chatbot`, handlers_chatbots.py:197.
- Chi: ingress + token (CSRF).
- Cosa fa: cancella il chatbot e ripulisce i dati orfani: memorie a lungo termine
  (`knowledge_store.delete_by_chatbot`) e storico chat (`clear_history`), entrambi
  best-effort con log in caso di errore (righe 208-222).
- Restituisce: **204** senza corpo.
- Errori: **400** id non valido; **409** `Cannot delete default agent` (riga 204);
  **404** inesistente (riga 207).

### POST /api/chatbots/{agent_id}/run — server.py:2808
- Handler: `handle_run_chatbot`, handlers_chatbots.py:226.
- Chi: ingress + token (CSRF).
- Cosa fa: esegue subito il chatbot (`engine.run_chatbot`).
- Restituisce: `{"result": ...}`.
- Errori: **400** id non valido; **404** chatbot inesistente (riga 233).

### GET /api/chatbots/{agent_id}/usage — server.py:2812
- Handler: `handle_get_chatbot_usage`, handlers_chatbots.py:238.
- Chi: ingress + token.
- Cosa fa: consumo cumulato del singolo chatbot letto dal runner/router.
- Restituisce: `{"agent_id", "requests", "input_tokens", "output_tokens",
  "total_tokens", "cost_usd", "cost_eur", "last_run"}`.
- Errori: **400** id non valido; **404** chatbot inesistente (riga 244);
  **503** runner non configurato (riga 247).

### POST /api/chatbots/{agent_id}/usage/reset — server.py:2813
- Handler: `handle_reset_chatbot_usage`, handlers_chatbots.py:262.
- Chi: ingress + token (CSRF).
- Cosa fa: azzera i contatori di consumo di quel chatbot.
- Restituisce: `{"reset": true, "agent_id": ...}`.
- Errori: **400** id non valido; **404** inesistente (riga 268); **503** runner
  non configurato (riga 271).

### GET /api/chatbots/{agent_id}/context-preview — server.py:2814
- Handler: `handle_context_preview`, handlers_chatbots.py:276.
- Chi: ingress + token.
- Cosa fa: calcola l'output della `SemanticContextMap` con query vuota, filtrato
  dalle `allowed_entities` del chatbot: e' l'anteprima di cosa "vede" il chatbot.
- Restituisce: `{"context_str", "entity_count", "token_estimate"}`; se manca
  `context_map` o `entity_cache` restituisce **200** con i valori a zero (riga 289).
- Errori: **400** id non valido; **404** chatbot inesistente (riga 284).

## 6.4 Agentbot (CRUD utente)

Modulo `api/handlers_agentbots.py`; nessuna auth per rotta (docstring
righe 16-21), tutto delegato ai middleware. Ogni mutazione passa da
`validate_agentbot` e poi da `_apply_mutation` (righe 75-90), che ri-registra gli
scheduler e aggiorna la cache in memoria letta dal Guardian.

### GET /api/agentbots — server.py:2868
- Handler: `handle_list_agentbots`, handlers_agentbots.py:97.
- Chi: ingress + token.
- Cosa fa: serve la cache in memoria `app["user_agentbots"]`; se assente ricade
  sulla lettura da disco (`_store.load_agentbots`, righe 102-104).
- Restituisce: `{"agentbots": [...]}`.
- Errori: nessuno specifico.

### POST /api/agentbots — server.py:2869
- Handler: `handle_create_agentbot`, handlers_agentbots.py:108.
- Chi: ingress + token (CSRF).
- Cosa fa: rimuove qualunque `id` fornito dal client (riga 124, cosi' un id
  format-valido copiato non puo' sovrascrivere un Agentbot esistente), valida,
  fa upsert su disco, riapplica scheduler e cache.
- Restituisce: **201** `{"ok": true, "agentbot": {...}, "agentbots": [...]}`.
- Errori: **400** `invalid JSON` (riga 122) o `invalid agentbot` (riga 127).

### PUT /api/agentbots/{id} — server.py:2870
- Handler: `handle_update_agentbot`, handlers_agentbots.py:134.
- Chi: ingress + token (CSRF).
- Cosa fa: l'id del percorso e' autoritativo e sovrascrive `body["id"]` (riga 151);
  valida e fa upsert.
- Restituisce: `{"ok": true, "agentbot": {...}, "agentbots": [...]}`.
- Errori: **404** id inesistente (riga 141); **400** JSON non valido (riga 145),
  corpo non oggetto (riga 147), agentbot non valido (riga 154).

### DELETE /api/agentbots/{id} — server.py:2871
- Handler: `handle_delete_agentbot`, handlers_agentbots.py:160.
- Chi: ingress + token (CSRF).
- Cosa fa: cancella dal file e riapplica scheduler + cache.
- Restituisce: `{"ok": true, "agentbots": [...]}`.
- Errori: **404** id inesistente (riga 166).

## 6.5 Task engine

Modulo `api/handlers_tasks.py`. Ogni risposta porta l'alias deprecato
`chatbot_id` accanto ad `agent_id` (`_with_legacy_alias`, righe 5-10).

### GET /api/tasks — server.py:2817
- Handler: `handle_list_tasks`, handlers_tasks.py:13.
- Chi: ingress + token.
- Cosa fa: elenca i task filtrando per `?agent_id=` (fallback retro-compatibile
  `?chatbot_id=`, riga 20) e `?status=`.
- Restituisce: array di task; **array vuoto** se il task engine non e' cablato
  (riga 16) — cioe' "motore assente" e "nessun task" sono indistinguibili qui.
- Errori: nessuno specifico.

### GET /api/tasks/{task_id} — server.py:2818
- Handler: `handle_get_task`, handlers_tasks.py:26.
- Chi: ingress + token.
- Cosa fa: singolo task.
- Restituisce: oggetto task.
- Errori: **404** `{"error": "Not found"}` sia se manca il task engine (riga 29)
  sia se il task non esiste (riga 32).

### DELETE /api/tasks/{task_id} — server.py:2819
- Handler: `handle_cancel_task`, handlers_tasks.py:36.
- Chi: ingress + token (CSRF).
- Cosa fa: annulla il task.
- Restituisce: **204** senza corpo.
- Errori: **404** task engine assente (riga 39) o task inesistente/non
  annullabile (riga 42).

## 6.6 Inventario entita' e salute di Home Assistant

### GET /api/entities — server.py:2809
- Handler: `handle_list_entities`, `api/handlers_entities.py:47`.
- Chi: ingress + token.
- Cosa fa: inventario entita' dalla cache, filtrabile con `?domain=` e
  `?device_class=` (CSV, `_csv` riga 7) e `?q=` (sottostringa case-insensitive su
  entity_id e nome, `filter_entities` righe 11-44, tetto 1000 voci).
- Restituisce: `{"entities": [{"entity_id", "friendly_name", "domain",
  "device_class", "state"}, ...]}`.
- Errori: **503** con il corpo di `inventario_non_leggibile(cache)` e **senza** la
  chiave `entities` quando l'inventario non e' leggibile (righe 57-62): scelta
  deliberata perche' un elenco vuoto direbbe "casa senza entita'" invece di "non
  ho potuto guardare".

### GET /api/health/ha — server.py:2823
- Handler: `handle_get_ha_health`, `api/handlers_health.py:4`.
- Chi: ingress + token.
- Cosa fa: snapshot dello stato di salute di HA; `?sections=a,b` seleziona le
  sezioni (default `all`), senza cap sul numero di voci (`capped=False`, riga 12).
- Restituisce: lo snapshot dell'HealthMonitor.
- Errori: **503** `{"error": "HealthMonitor not initialized"}` (riga 7).

### POST /api/health/ha/refresh — server.py:2824
- Handler: `handle_refresh_ha_health`, handlers_health.py:16.
- Chi: ingress + token (CSRF).
- Cosa fa: forza un `refresh()` dell'HealthMonitor.
- Restituisce: `{"ok": true}`.
- Errori: **503** HealthMonitor non inizializzato (riga 19).

## 6.7 Consumi e costi globali

### GET /api/usage — server.py:2799
- Handler: `handle_usage`, `api/handlers_usage.py:5`.
- Chi: ingress + token.
- Cosa fa: legge i contatori dal `llm_router` (o dal `claude_runner`) e converte
  il costo in euro con `EUR_RATE` (riga 15).
- Restituisce: `{"total_requests", "input_tokens", "output_tokens",
  "total_tokens", "cost_usd", "cost_eur", "rate_limit_errors", "last_reset"}`.
- Errori: **503** `{"error": "runner not configured"}` (riga 8).

### POST /api/usage/reset — server.py:2800
- Handler: `handle_reset_usage`, handlers_usage.py:29.
- Chi: ingress + token (CSRF).
- Cosa fa: `runner.reset_usage()`.
- Restituisce: `{"reset": true, "last_reset": ...}`.
- Errori: **503** runner non configurato (riga 32).

## 6.8 Modelli e provider LLM

Modulo `api/handlers_models.py`. Nessuna credenziale esce mai: solo
booleani `has_credential` (`_config_has_credential`, righe 123-137;
`_enrich_provider`, righe 404-410).

### GET /api/models — server.py:2820
- Handler: `handle_list_models`, handlers_models.py:413.
- Chi: ingress + token.
- Cosa fa: costruisce l'elenco dei provider disponibili con i rispettivi modelli:
  Claude da lista statica (`_CLAUDE_MODELS`, righe 189-194); OpenAI interrogando
  `api.openai.com/v1/models` con timeout 5s e fallback statico
  (`_fetch_openai_models`, righe 204-222); OpenRouter con filtro live sulla
  capacita' tool e fallback ai preset (`_fetch_openrouter_models`, righe 291-346);
  Ollama via `{base}/api/tags` (righe 225-243).
- Restituisce: `{"providers": [{"id", "label", "models": [...], "active",
  "has_credential"}, ...]}`.
- Errori: nessuno specifico — i guasti verso i cataloghi esterni degradano su
  liste di fallback e restano solo nei log (righe 211, 221, 303, 345).

### GET /api/models/config — server.py:2821
- Handler: `handle_get_models_config`, handlers_models.py:154.
- Chi: ingress + token.
- Cosa fa: legge `models_config.json` (`load_models_config`, righe 36-57) e lo
  arricchisce con lo stato dei cinque provider, la strategia LLM e la
  configurazione embedding.
- Restituisce: `{"chain_order", "brain_model", "provider_models", "providers":
  [{"id","label","active","has_credential","toggle"}], "llm_strategy",
  "embeddings", "ollama_model"}`.
- Errori: nessuno specifico (file illeggibile = configurazione vuota, righe 41-43).

### PUT /api/models/config — server.py:2822
- Handler: `handle_save_models_config`, handlers_models.py:167.
- Chi: ingress + token (CSRF).
- Cosa fa: valida (solo backend noti in `chain_order`) e scrive in modo atomico
  (`save_models_config`, righe 60-78, `os.replace` su file temporaneo), poi
  aggiorna a caldo `app["models_config"]` (riga 174).
- Restituisce: `{"ok": true, **config_pulita}`.
- Errori: **400** `invalid JSON body` (riga 171).

## 6.9 Proposte

Modulo `api/handlers_proposals.py`.

### GET /api/proposals — server.py:2825
- Handler: `handle_list_proposals`, handlers_proposals.py:14.
- Chi: ingress + token.
- Cosa fa: elenca le proposte, filtro opzionale `?status=`
  (`pending|applied|rejected|archived`, riga 7).
- Restituisce: `{"proposals": [...]}`.
- Errori: **503** `ProposalStore not initialized` (riga 17); **400** stato non
  valido (riga 20).

### GET /api/proposals/{proposal_id} — server.py:2826
- Handler: `handle_get_proposal`, handlers_proposals.py:25.
- Chi: ingress + token.
- Restituisce: la proposta.
- Errori: **503** store non inizializzato (riga 28); **404** non trovata (riga 32).

### POST /api/proposals/{proposal_id}/apply — server.py:2827
- Handler: `handle_apply_proposal`, handlers_proposals.py:36.
- Chi: ingress + token (CSRF).
- Cosa fa: materializza la proposta secondo il tipo. `ha_automation`: crea
  l'automazione in HA e marca applicata solo se HA ha accettato (righe 48-59).
  `ha_dashboard|ha_script|ha_scene`: `apply_ha_config` (righe 60-74).
  `hiris_agent`: ricostruisce l'Agentbot dalla whitelist con
  `validate_agentbot` scartando l'`id` proposto dall'LLM, fa upsert e riapplica
  scheduler/cache (righe 82-109). Tipo non gestito: logga un warning e marca
  applicata **senza** effetti su HA (righe 116-123).
- Restituisce: `{"ok": true|false}` piu', a seconda del ramo, `automation_id`,
  `result` o `agentbot`.
- Errori: **503** store assente (riga 39) / client HA assente (righe 51, 63) /
  `data_dir` assente (riga 85); **409** proposta inesistente o non in stato
  `pending` (righe 44, 121); **502** HA ha rifiutato la scrittura (righe 56, 71);
  **400** config Agentbot non valida o non sicura (riga 100).

### POST /api/proposals/{proposal_id}/reject — server.py:2828
- Handler: `handle_reject_proposal`, handlers_proposals.py:126.
- Chi: ingress + token (CSRF).
- Cosa fa: marca la proposta rifiutata.
- Restituisce: `{"ok": true}`.
- Errori: **503** store assente (riga 129); **409** inesistente o non pendente
  (riga 134).

## 6.10 Plance (dashboard) e loro ripristino

Modulo `api/handlers_dashboards.py`. Nota di routing dichiarata in
server.py:2829-2830: `backups` e' un segmento fisso a un livello diverso da
`{url_path}/restore`, quindi le due rotte non sono ambigue.

### GET /api/dashboards/backups — server.py:2831
- Handler: `handle_list_dashboard_backups`, handlers_dashboards.py:13.
- Chi: ingress + token.
- Cosa fa: elenca gli snapshot ripristinabili; risposta di soli metadati, le
  configurazioni delle plance non escono da qui (docstring righe 20-22).
- Restituisce: `{"backups": [...]}` con `saved_at` per decidere quanto rendere
  prominente l'affordance "Annulla".
- Errori: **503** `{"error": "servizio non disponibile"}` se manca `data_dir`
  (riga 25).

### POST /api/dashboards/{url_path}/restore — server.py:2832
- Handler: `handle_restore_dashboard`, handlers_dashboards.py:29.
- Chi: ingress + token (CSRF).
- Cosa fa: riscrive in HA l'ultimo snapshot della plancia e poi consuma **quello
  stesso** snapshot (non "l'ultimo per posizione", righe 51-56), per non
  cancellare la via di ritorno di una sostituzione concorrente.
- Restituisce: `{"ok": true, "url_path": ...}`.
- Errori: **503** `ha_client` o `data_dir` assenti (riga 33); **404** nessuno
  snapshot per quella plancia (riga 38); **502** `Ripristino non riuscito: ...`
  quando HA rifiuta la scrittura — e lo snapshot resta al suo posto (righe 40-46).

## 6.11 Conoscenza (coda di approvazione dei ricordi)

Modulo `api/handlers_knowledge.py`. Ogni rotta risolve il proprietario
con `resolve_owner(request)` e opera **owner-scoped** (fix IDOR, righe 30-37,
60-66, 102-105): l'id di un altro proprietario si ferma con un 404 senza rivelare
l'esistenza dell'elemento.

### GET /api/knowledge/pending — server.py:2833
- Handler: `handle_list_pending`, handlers_knowledge.py:18.
- Chi: ingress + token.
- Cosa fa: elenca gli elementi in stato `pending` del proprietario piu' quelli
  condivisi (`home`), fuori dall'event loop (`run_in_executor`).
- Restituisce: `{"items": [...]}`.
- Errori: **503** `{"error": "knowledge store not configured", "items": []}` —
  la chiave `items` resta presente e vuota per non cambiare forma alla risposta,
  ma lo stato distingue "non ho potuto leggere" da "non c'e' nulla" (righe 20-29).

### POST /api/knowledge/{id}/approve — server.py:2834
- Handler: `handle_approve`, handlers_knowledge.py:41.
- Chi: ingress + token (CSRF).
- Cosa fa: approva l'elemento **calcolando l'embedding se manca**, perche' la
  ricerca filtra su `status='approved' AND embedding IS NOT NULL` e un'approvazione
  senza vettore lascerebbe l'elemento irraggiungibile (docstring righe 42-52).
- Restituisce: `{"ok": true}`.
- Errori: **503** store non configurato (riga 55) o embedding non calcolabile
  (`embedding unavailable: item not approved`, riga 85); **400** id non intero
  (riga 59); **404** elemento inesistente o di un altro proprietario (righe 68, 90).

### POST /api/knowledge/{id}/reject — server.py:2835
- Handler: `handle_reject`, handlers_knowledge.py:94.
- Chi: ingress + token (CSRF).
- Cosa fa: cancella l'elemento (owner-scoped).
- Restituisce: `{"ok": true}`.
- Errori: **503** store non configurato (riga 97); **400** id non intero (riga 101);
  **404** inesistente o di altro proprietario (riga 107).

### POST /api/knowledge — server.py:2836
- Handler: `handle_manual_add`, handlers_knowledge.py:111.
- Chi: ingress + token (CSRF).
- Cosa fa: inserisce a mano un elemento gia' `approved`, ma **solo** se
  l'embedding e' calcolabile; accetta `kind`, `title`, `amount`, `due_date`,
  `category`, `sensitivity`; `source` e' fissato a `"manual"` (righe 145-159).
- Restituisce: `{"id": <int>, "status": "approved"}`.
- Errori: **503** store non configurato (riga 121) o embedding non disponibile
  (`embedding unavailable: item not created`, riga 141); **400** JSON non valido
  (riga 125) o `content` vuoto (riga 128).

## 6.12 Semaforo del gateway: policy e riepilogo autonomia

Modulo `api/handlers_gateway_policy.py`. Categorie canoniche in
`GATEWAY_CATEGORIES` (righe 50-73); livelli validi `green|yellow|red|off`
(riga 75); persistenza in `gateway_policy.json` (righe 82-102, scrittura atomica).

### GET /api/gateway/policy — server.py:2844
- Handler: `handle_get_gateway_policy`, handlers_gateway_policy.py:281.
- Chi: ingress + token.
- Cosa fa: restituisce le categorie con il conteggio delle entita' per dominio
  (dalla cache, righe 286-291) e il flag `dangerous` calcolato **lato server** da
  `DANGEROUS_DOMAINS` (righe 293-307), unica fonte, per evitare il disallineamento
  che c'era nel frontend.
- Restituisce: `{"categories": [...], "levels": {...}, "valid_levels": [...],
  "settings": {"notify_service", "notify_users"}, "entities": {...}}`.
- Errori: nessuno specifico (file illeggibile = policy vuota, righe 90-94).

### POST /api/gateway/policy — server.py:2845
- Handler: `handle_save_gateway_policy`, handlers_gateway_policy.py:356.
- Chi: ingress + token (CSRF).
- Cosa fa: accetta `levels` (o `categories`), `settings`, `entities`; valida e
  salva (`save_categories`, righe 133-155: solo categorie note, livelli validi,
  entity_id che matchano `_ENTITY_RE`, servizi che matchano `^notify\.[A-Za-z0-9_]{1,64}$`),
  poi riapplica live la policy derivata mutando in loco `app["execute_policy"]`
  (`apply_saved_policy`, righe 253-278).
- Restituisce: `{"ok": true, "levels": {...}, "settings": {...},
  "execute_policy": {...}}`.
- Errori: **400** `invalid JSON body` (riga 360) o `levels must be an object`
  (riga 363).

### POST /api/gateway/autonomy-summary — server.py:2846
- Handler: `handle_autonomy_summary`, handlers_gateway_policy.py:317.
- Chi: ingress + token (CSRF). E' un POST solo perche' riceve in corpo la lista di
  entita' da valutare; e' di sola lettura.
- Cosa fa: conta, per una lista di entity_id (massimo 2000, riga 343), quante
  ricadono in ciascun livello effettivo, usando `summarize_autonomy` — la stessa
  funzione dell'enforcement, comprensiva di `DANGEROUS_DOMAINS` (docstring righe
  318-334: prima il conteggio veniva rifatto lato client senza la denylist, e
  mostrava come verdi domini che `gate_action` avrebbe sempre negato).
- Restituisce: `{"counts": {...}, "total": N}`.
- Errori: **400** `invalid JSON body` (riga 339) o `entities must be a list`
  (riga 342).

## 6.13 Approvazioni in sospeso del gateway (giallo/rosso)

Modulo `api/handlers_gateway_pending.py`. Nonce monouso con TTL 300s
(`PENDING_TTL_S`, riga 30; `take_pending`, righe 107-117).

### GET /api/gateway/pending — server.py:2878
- Handler: `handle_list_pending` (importato come `_gw_list_pending`,
  server.py:2874), handlers_gateway_pending.py:314.
- Chi: ingress + token. Proprio perche' il token del gateway basta a leggere qui,
  `list_pending` (righe 88-104) **spoglia** `otp` e `otp_attempts` dalle copie
  restituite: l'OTP e' il segreto di step-up che prova che ha digitato un umano,
  e non deve tornare al principale che si sta verificando.
- Cosa fa: elenca i pending ancora validi, ordinati per timestamp decrescente.
- Restituisce: `{"pending": [{"id","tool","inputs","tier","origin","label","ts",
  "expires","status","user"}, ...]}`.
- Errori: nessuno specifico.

### POST /api/gateway/pending/{nonce}/approve — server.py:2879
- Handler: `handle_approve_pending` (`_gw_approve_pending`), handlers_gateway_pending.py:318.
- Chi: **solo Ingress** (o modalita' dev `no_token`). `_require_human_auth`
  (righe 292-311) rifiuta l'autenticazione a solo token anche se ha gia' passato
  il middleware: il gateway detiene quel token per **creare** i pending via
  `/api/execute`, se bastasse anche ad approvarli potrebbe auto-approvarsi un
  rosso senza alcun umano.
- Cosa fa: consuma atomicamente il nonce ed esegue il comando trattenuto
  (`approve` righe 257-266 -> `execute_pending` righe 334-353, che dispaccia con
  `tier_confirmed=True` e whitelist ristretta al solo dominio approvato).
- Restituisce: `{"ok": true, "result": ...}`.
- Errori: **403** `forbidden: approval requires the HIRIS UI (ingress), not the
  service token` (riga 308). Nonce sconosciuto/scaduto/gia' gestito: **200** con
  `{"ok": false, "error": "richiesta non trovata, scaduta o gia' gestita"}`
  (riga 262), non un 404.

### POST /api/gateway/pending/{nonce}/reject — server.py:2880
- Handler: `handle_reject_pending` (`_gw_reject_pending`), handlers_gateway_pending.py:326.
- Chi: **solo Ingress** / `no_token`, stessa barriera `_require_human_auth`.
- Cosa fa: consuma il nonce e lo marca `rejected` senza eseguire nulla
  (`reject`, righe 269-275).
- Restituisce: `{"ok": true}`.
- Errori: **403** come sopra; **200** `{"ok": false, "error": "richiesta non
  trovata, scaduta o gia' gestita"}` per nonce non valido.

## 6.14 Execute API (la superficie che pilota il gateway MCP)

### POST /api/execute — server.py:2839
- Handler: `handle_execute`, `api/handlers_execute.py:147`.
- Chi: **solo chi presenta `X-HIRIS-Internal-Token`**. Oltre al middleware c'e' un
  controllo indipendente nell'handler (`_check_token`, righe 129-144, fail-closed
  se il token non e' configurato) proprio per non fidarsi del ramo Ingress: una
  richiesta Ingress senza token prende **401** qui. In pratica i chiamanti sono il
  gateway MCP remoto, il client MCP in-addon (`LocalExecuteClient`,
  `mcp/local_client.py:36-51`, che aggiunge l'header
  `X-HIRIS-Local-Chat` con il segreto di processo `app["local_execute_token"]`,
  server.py:1194) e il runner agente in-addon (`agent/runner.py:196`).
- Cosa fa, in ordine:
  1. Verifica il token e la presenza del dispatcher.
  2. Verifica che `tool` sia dentro il soffitto server-side `_HARD_EXECUTE_ALLOWED`
     (riga 30: `READ_TOOLS` + `PROPOSE_TOOLS` + `call_ha_service`, `create_task`,
     `send_notification`) e poi dentro la policy salvata, con `send_notification`
     sempre esposto (`_ALWAYS_EXPOSED`, riga 36).
  3. Per `call_ha_service`: blocca i target di gruppo area/device/label/floor
     (riga 187), blocca le entita' `off` (riga 196), e classifica il livello
     effettivo. Un dominio pericoloso che risultasse **giallo** viene forzato a
     **rosso** prima di creare il pending (righe 230-235): il giallo genera una
     notifica azionabile che si approva con un tocco, senza step-up.
     Giallo/rosso creano un pending e inviano la notifica, senza eseguire (righe 236-253).
  4. Per `create_task`: le azioni `call_ha_service` di **primo livello** devono
     avere target espliciti e tutti verdi (righe 271-293); i task annidati non sono
     ispezionati qui (nota righe 260-270, il task_engine ri-verifica al momento
     dello scatto).
  5. Per `create_ha_config`: non esegue mai, salva una proposta da approvare in
     HIRIS (righe 297-311).
  6. Denylist di lettura: sulle letture (e su `PRUNED_NON_READ_TOOLS`) rifiuta in
     ingresso le richieste che nominano entita' coperte (righe 329-342) e **pota**
     comunque il risultato in uscita (`prune_read_result`, righe 355-362), perche'
     omettere il parametro aggirerebbe il solo controllo in ingresso. Non si applica
     alla chat in-addon, riconosciuta dal segreto di processo e non dal campo
     `origin` che il chiamante potrebbe falsificare (`_is_local_chat`, righe 107-126).
  7. Dispaccia con le whitelist della policy per le azioni; per le letture
     `allowed_entities`/`allowed_services` restano `None` (righe 344-354).
- Restituisce: `{"result": ...}`; per i rami trattenuti `{"result": {"status":
  "pending_approval", "id"|"proposal_id": ..., "tier": ..., "message": ...}}`.
  I rifiuti "di merito" (target di gruppo, entita' bloccata, task non verde)
  tornano **200** con `{"result": {"ok": false, "error": "..."}}`.
- Errori: **401** `unauthorized` (riga 149); **503** dispatcher non disponibile
  (riga 153) o `ProposalStore non disponibile` (riga 301); **400** JSON non valido
  (riga 158), `tool required` (riga 163), `input must be an object` (riga 165);
  **403** tool fuori dall'allowlist rigida (riga 169), tool non esposto dalla
  policy (riga 175), entita' nella denylist di lettura (riga 339).

## 6.15 Storicizzazione (history policy)

Modulo `api/handlers_history_policy.py` — **mai citato nel documento**.
Decide quali entita' la `HistoryStore` registra; default vuoto, quindi opt-in
(docstring righe 1-4). Categorie in `HISTORY_CATEGORIES` (righe 18-32); ritenzione
limitata a [1, 365] giorni, default 90 (righe 15-16, 56).

### GET /api/history/policy — server.py:2851
- Handler: `handle_get_history_policy`, handlers_history_policy.py:90.
- Chi: ingress + token.
- Cosa fa: legge `history_policy.json` dal `data_dir` (`load_policy`, righe 40-58),
  scartando domini non validi e voci non stringa, e allega le categorie.
- Restituisce: `{"domains": {...}, "entities": [...], "exclude": [...],
  "retention_days": N, "categories": [{"id","label"}, ...]}`.
- Errori: nessuno specifico — file assente o illeggibile diventa policy vuota
  (righe 44-48).

### POST /api/history/policy — server.py:2852
- Handler: `handle_save_history_policy`, handlers_history_policy.py:95.
- Chi: ingress + token (CSRF).
- Cosa fa: ripulisce e scrive in modo atomico (`save_policy`, righe 61-77,
  `os.replace` su `.tmp`), poi applica la policy a caldo su `app["history_capture"]`
  se presente (righe 102-104).
- Restituisce: `{"ok": true, **policy_pulita}`.
- Errori: **400** `{"error": "invalid JSON body"}` (riga 99). Un corpo che non sia
  un oggetto non e' un errore: viene trattato come `{}` (riga 101).

## 6.16 Sentinella (policy e cronologia eventi)

Modulo `api/handlers_sentinel.py`.

### GET /api/sentinel/policy — server.py:2857
- Handler: `handle_get_sentinel_policy`, handlers_sentinel.py:8.
- Chi: ingress + token.
- Cosa fa: carica la configurazione dei rilevatori (`watcher.policy.load_policy`)
  e allega i metadati `SENTINEL_DETECTORS`.
- Restituisce: `{**policy, "detectors_meta": {...}}`.
- Errori: nessuno specifico.

### POST /api/sentinel/policy — server.py:2858
- Handler: `handle_save_sentinel_policy`, handlers_sentinel.py:15.
- Chi: ingress + token (CSRF).
- Cosa fa: valida e salva; se il Guardian espone `set_policy`, applica live
  (righe 29-31).
- Restituisce: `{"ok": true, **policy_pulita}`.
- Errori: **400** `{"error": "invalid JSON"}` (riga 20) e **400**
  `{"ok": false, "error": <PolicyValidationError>}` per valore di rilevatore
  malformato o fuori scala: non deve mai essere persistito ne' applicato (righe 24-28).

### GET /api/sentinel/timeline — server.py:2859
- Handler: `handle_sentinel_timeline`, handlers_sentinel.py:35.
- Chi: ingress + token.
- Cosa fa: ultimi eventi della sentinella; `?limit=` viene forzato dentro [1, 200]
  (righe 44-47) perche' SQLite tratta un LIMIT negativo come "illimitato"; un
  valore non numerico ricade su 50.
- Restituisce: `{"events": [...]}`; `{"events": []}` se lo store non e' cablato
  (riga 39).
- Errori: nessuno specifico.

## 6.17 Cervello: feed, ragionamenti, avvisi

Modulo `api/handlers_brain.py`.

### GET /api/brain/feed — server.py:2890
- Handler: `handle_brain_feed`, handlers_brain.py:10.
- Chi: ingress + token.
- Cosa fa: fonde in un unico flusso ragionamenti, avvisi, proposte pendenti e
  tracce di azione del cervello (`brain.feed.merge_feed`, righe 23-30);
  `?limit=` con tetto 200 (default 50), `?type=` come filtro.
- Restituisce: `{"items": [...]}`.
- Errori: nessuno specifico; ogni store assente contribuisce con una lista vuota.

### GET /api/brain/reasoning — server.py:2891
- Handler: `handle_brain_reasoning`, handlers_brain.py:34.
- Chi: ingress + token.
- Cosa fa: elenca le righe del `reasoning_log`; `?limit=` con tetto 200.
- Restituisce: `{"reasoning": [...]}`; `{"reasoning": []}` se il log non e' cablato
  (riga 37).
- Errori: nessuno specifico.

### GET /api/brain/advisories — server.py:2892
- Handler: `handle_list_advisories`, handlers_brain.py:45.
- Chi: ingress + token.
- Cosa fa: elenca gli avvisi, filtro `?status=` fra
  `open|acknowledged|resolved|dismissed` (riga 7).
- Restituisce: `{"advisories": [...]}`; lista vuota se lo store non c'e' (riga 48).
- Errori: **400** `{"error": "Invalid status: ..."}` (riga 51).

### POST /api/brain/advisories/{id}/ack — server.py:2893
- Handler: `handle_ack_advisory`, handlers_brain.py:69 (delega a `_set_status`,
  riga 55, con `"acknowledged"`).
- Chi: ingress + token (CSRF).
- Cosa fa: marca l'avviso come preso in carico.
- Restituisce: `{"ok": true}`.
- Errori: **503** `AdvisoryStore not initialized` (riga 58); **400** `{"ok": false}`
  se l'id non e' un intero (riga 62); **409** `{"ok": false, "error": "not found"}`
  se l'avviso non esiste (riga 65).

### POST /api/brain/advisories/{id}/dismiss — server.py:2894
- Handler: `handle_dismiss_advisory`, handlers_brain.py:73 (stesso `_set_status`
  con `"dismissed"`).
- Chi: ingress + token (CSRF).
- Cosa fa: archivia l'avviso come scartato.
- Restituisce: `{"ok": true}`.
- Errori: identici a `/ack`: **503**, **400**, **409**.

## 6.18 Suggerimenti del cervello

Modulo `api/handlers_suggestions.py`.

### GET /api/suggestions — server.py:2810
- Handler: `handle_list_suggestions`, handlers_suggestions.py:8.
- Chi: ingress + token.
- Cosa fa: elenca i suggerimenti registrati.
- Restituisce: `{"suggestions": [...]}`; lista vuota se lo store non e' cablato
  (riga 11).
- Errori: nessuno specifico.

### POST /api/suggestions/{id}/undo — server.py:2811
- Handler: `handle_undo_suggestion`, handlers_suggestions.py:15.
- Chi: ingress + token (CSRF).
- Cosa fa: annulla il suggerimento (`brain.suggestions.undo`), poi ricarica da
  disco la policy nel Guardian in esecuzione — senza questo passo il rilevatore
  continuerebbe a girare con il valore pre-undo fino al prossimo salvataggio o
  riavvio (righe 32-44) — e infine rimuove, best-effort, la traccia
  `brain-action` corrispondente cosi' che la chat smetta di citare un'azione non
  piu' valida (righe 46-67).
- Restituisce: `{"ok": true|false}`.
- Errori: **400** `{"ok": false}` se l'id non e' un intero (riga 19); **200**
  `{"ok": false}` se mancano store o `data_dir` (riga 24) — cioe' il guasto di
  cablaggio non e' distinguibile da un undo fallito.

## 6.19 Coda di ragionamento (ponte verso il consumatore esterno)

Modulo `api/handlers_reasoning.py`. E' la coppia di rotte che un
consumatore esterno (il ponte push, che gira fuori dall'addon) usa per prendere e
restituire i job; l'autenticazione e' quella generale, quindi in pratica il
**token interno**.

### POST /api/reasoning/claim — server.py:2883
- Handler: `handle_reasoning_claim`, handlers_reasoning.py:13.
- Chi: ingress + token (CSRF); nell'uso reale, token interno.
- Cosa fa: rivendica il prossimo job dalla coda (`q.claim`), con orologio
  iniettabile (`_now`, righe 9-10).
- Restituisce: `{"job": {...}}` oppure `{"job": null}` se non c'e' nulla — e
  **anche** `{"job": null}` se la coda non e' cablata (riga 16): i due casi non si
  distinguono.
- Errori: nessuno specifico.

### POST /api/reasoning/submit — server.py:2884
- Handler: `handle_reasoning_submit`, handlers_reasoning.py:20.
- Chi: ingress + token (CSRF); nell'uso reale, token interno.
- Cosa fa: consegna la decisione per un job (`job_id` + `nonce` + `decision`). Se
  il job e' `kind == "chat"`, la decisione **non** puo' attuare nulla in casa:
  scrive solo la risposta in `chat_store` tramite `submit_chat_reply`, fail-closed
  se mancano `chatbot_id` o `reply` (righe 34-55, con retro-compatibilita' sulla
  vecchia chiave `agent_id`). Altrimenti chiama `execute_decision` (righe 57-63).
- Restituisce: `{"ok": true, "outcome": "recorded" | "chat_reply_recorded" |
  "chat_reply_skipped" | "error" | <esito di execute_decision>}`.
- Errori: **503** `{"ok": false, "error": "queue unavailable"}` (riga 23);
  **400** `{"ok": false, "error": "invalid JSON"}` (riga 27); **409**
  `{"ok": false, "error": "invalid or expired"}` per job_id/nonce non validi o
  scaduti (riga 30). Un'eccezione di `execute_decision` non produce un 5xx: viene
  loggata e l'esito diventa `"error"` dentro una risposta 200 (righe 61-63).

## 6.20 Riepilogo del censimento

- 64 endpoint HTTP + 1 mount statico = **65 voci**, tutte da server.py:2792-2894.
- Moduli handler coinvolti: `handlers_status`, `handlers_config`,
  `handlers_usage`, `handlers_chat`, `handlers_chat_history`, `handlers_chatbots`,
  `handlers_entities`, `handlers_suggestions`, `handlers_tasks`, `handlers_models`,
  `handlers_health`, `handlers_proposals`, `handlers_dashboards`,
  `handlers_knowledge`, `handlers_execute`, `handlers_gateway_policy`,
  `handlers_history_policy`, `handlers_sentinel`, `handlers_agentbots`,
  `handlers_gateway_pending`, `handlers_reasoning`, `handlers_brain`
  (22 moduli), piu' i tre handler definiti direttamente in server.py
  (`_serve_index`, `_serve_config`, `_handle_health`).
- Moduli di supporto non registrati come rotte ma determinanti per la superficie:
  `middleware_internal_auth.py`, `middleware_csrf.py`, `read_denylist.py`
  (denylist e potatura delle letture usate da `/api/execute`).
- Asimmetrie di autorizzazione da tenere presenti: `/api/execute` e' l'unica rotta
  che **richiede** il token anche a un chiamante Ingress; le due rotte
  `/api/gateway/pending/{nonce}/approve|reject` sono le uniche che **rifiutano** il
  token e pretendono Ingress.

---

# 7. Il catalogo degli strumenti esposti al modello

Secondo censimento: i **37** strumenti che HIRIS puo' mettere davanti a un modello, uno per uno.
Per ciascuno: dove e' definito, che cosa **dichiara** di fare nella descrizione che il modello
legge, che cosa **fa davvero** nel dispatcher, quali superfici possono chiamarlo e quali filtri
attraversa. In coda, quindici reperti di disallineamento fra i cataloghi. La sezione 2 racconta il
catalogo come funzione del prodotto; questa lo elenca.

## 7.1 Metodo e perimetro

Il catalogo autorevole e' `ALL_TOOL_DEFS` (`claude_runner.py:181-219`): **37 voci**,
contate una a una sulla lista. Tutti gli altri elenchi sono sottoinsiemi o proiezioni:

| Catalogo | File:riga | Voci | Cosa decide |
|---|---|---|---|
| `ALL_TOOL_DEFS` | `claude_runner.py:181-219` | 37 | l'insieme totale che un runner puo' passare al modello |
| `EVALUATION_ONLY_TOOLS` | `claude_runner.py:225-253` | 18 | cio' che vede un agente non-chat (Sentinella / Agentbot) |
| `TOOLS` (MCP) | `mcp/tiers.py:21-129` | 15 | cio' che il server MCP registra (`mcp/server.py:37-41`) |
| `READ_TOOLS` | `api/handlers_gateway_policy.py:23-25` | 8 | letture sempre concesse al gateway |
| `PROPOSE_TOOLS` | `api/handlers_gateway_policy.py:45-46` | 5 | proposte sempre concesse al gateway |
| `_HARD_EXECUTE_ALLOWED` | `api/handlers_execute.py:30` | 16 | tetto rigido della execute-API (`READ_TOOLS ∪ PROPOSE_TOOLS ∪ {call_ha_service, create_task, send_notification}`) |
| `_ALWAYS_EXPOSED` | `api/handlers_execute.py:36` | 1 | `send_notification`, esposto anche fuori dalla policy salvata |
| `TOOLS` (UI) | `static/config/templates.js:61-98` | 36 | caselle del Designer, cioe' `allowed_tools` di un Chatbot |
| `_DEFAULT_CHAT_TOOLS` | `agent/runner.py:25-32` | 13 | cio' che vede la chat ad abbonamento (nomi MCP) |
| `_POTATORI` | `api/read_denylist.py:395-405` | 9 | forme di risposta note alla denylist di lettura (fail-closed) |
| `PRUNED_NON_READ_TOOLS` | `api/read_denylist.py:412` | 1 | `list_tasks`, potato pur non essendo una lettura |

### Le quattro superfici chiamanti

- **A — Chat locale (Chatbot).** `ALL_TOOL_DEFS` filtrato da `allowed_tools`
  (`claude_runner.py:712`; gemelli in `backends/openai_compat_runner.py:547` e `:835`).
  Tre sottrazioni successive: `render_template` se il bot non ha whitelist esplicita ma ha
  un perimetro di entita' (`claude_runner.py:722-723`), `http_request` se `allowed_endpoints`
  e' `None` (`:724-725`), `recall_memory`/`save_memory` se manca lo store o l'embedder
  (`:726-727`, condizione in `tools/dispatcher.py:229-233`).
- **B — Agente non-chat (Sentinella, Agentbot).** `run_with_actions` sostituisce
  `allowed_tools` con `EVALUATION_ONLY_TOOLS` (`claude_runner.py:966-968`).
- **C — Gateway MCP remoto.** Il modello vede i 15 `ToolDef` di `mcp/tiers.py`, ognuno
  inoltrato a `client.execute(t.hiris_tool, …)` (`mcp/server.py:28`), che finisce su
  `/api/execute` e li' passa due filtri: `_HARD_EXECUTE_ALLOWED` (`handlers_execute.py:167-169`)
  e la policy salvata `execute_policy["tools"]` (`:171-176`).
- **D — Chat ad abbonamento.** Stesso canale MCP di C, ma il CLI riceve solo
  `_DEFAULT_CHAT_TOOLS` (`agent/runner.py:25-32`), 13 nomi. Il ponte in-addon e'
  `LocalExecuteClient` (`mcp/local_client.py:36-51`), che marca la richiesta come locale
  per esentarla dalla denylist di lettura (`read_denylist.py`, header in `local_client.py:41`).

Il TaskEngine e' fuori da questo censimento: un task esegue solo i tre tipi di azione di
`_ALLOWED_TASK_ACTIONS` (`tools/dispatcher.py:14`), non i tool per nome.

## 7.2 Matrice di appartenenza

`AT` = `ALL_TOOL_DEFS`, `EV` = `EVALUATION_ONLY_TOOLS`, `MCP` = `mcp/tiers.py`,
`RD` = `READ_TOOLS`, `PR` = `PROPOSE_TOOLS`, `HE` = `_HARD_EXECUTE_ALLOWED`,
`JS` = `templates.js`, `CH` = `_DEFAULT_CHAT_TOOLS`.

| # | Tool | AT | EV | MCP | RD | PR | HE | JS | CH |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `get_entity_states` | ● | ● | ● | ● | | ● | ● | ● |
| 2 | `get_area_entities` | ● | ● | ● | ● | | ● | ● | ● |
| 3 | `get_home_status` | ● | ● | ● | ● | | ● | ● | ● |
| 4 | `get_entities_on` | ● | ● | | | | | ● | |
| 5 | `get_entities_by_domain` | ● | ● | | | | | ● | |
| 6 | `get_energy_history` | ● | ● | | | | | ● | |
| 7 | `get_history` | ● | ● | ● | ● | | ● | ● | ● |
| 8 | `get_weather_forecast` | ● | ● | | | | | ● | |
| 9 | `send_notification` | ● | | ● | | | ● | ● | ● |
| 10 | `get_ha_automations` | ● | ● | | | | | ● | |
| 11 | `get_automation_config` | ● | ● | ● | ● | | ● | ● | ● |
| 12 | `trigger_automation` | ● | | | | | | ● | |
| 13 | `toggle_automation` | ● | | | | | | ● | |
| 14 | `call_ha_service` | ● | | ● (`call_service`) | | | ● | ● | ● (`call_service`) |
| 15 | `create_task` | ● | ● | ● | | | ● | ● | ● |
| 16 | `list_tasks` | ● | ● | ● | | ● | ● | ● | ● |
| 17 | `cancel_task` | ● | ● | ● | | ● | ● | ● | ● |
| 18 | `get_calendar_events` | ● | ● | | | | | ● | |
| 19 | `set_input_helper` | ● | | | | | | ● | |
| 20 | `create_calendar_event` | ● | | | | | | ● | |
| 21 | `http_request` | ● | | | | | | | |
| 22 | `recall_memory` | ● | ● | | | | | ● | |
| 23 | `save_memory` | ● | | | | | | ● | |
| 24 | `get_ha_health` | ● | ● | | | | | ● | |
| 25 | `get_advisories` | ● | ● | ● | ● | | ● | ● | |
| 26 | `get_logbook` | ● | ● | ● | ● | | ● | ● | |
| 27 | `render_template` | ● | | | | | | ● | |
| 28 | `create_automation_proposal` | ● | | ● | | ● | ● | ● | ● |
| 29 | `create_ha_config` | ● | | | | ● | ● | ● | |
| 30 | `list_dashboards` | ● | | | | | | ● | |
| 31 | `get_dashboard_config` | ● | | | | | | ● | |
| 32 | `propose_dashboard` | ● | | | | | | ● | |
| 33 | `save_knowledge` | ● | | ● | | ● | ● | ● | ● |
| 34 | `recall_knowledge` | ● | | ● | ● | | ● | ● | ● |
| 35 | `link_knowledge` | ● | | | | | | ● | |
| 36 | `daily_briefing` | ● | | | | | | ● | |
| 37 | `confirm_pending` | ● | | | | | | ● | |

## 7.3 I quindici che il resto del documento non nomina mai

Verifica indipendente sul resto di questo documento, fatta prima che questa sezione fosse
aggiunta: cercando ciascuno dei 37 nomi, **esattamente 15 hanno zero occorrenze**. La sezione 1
dichiara 37 strumenti e il resto del documento ne discute 22.

`confirm_pending`, `get_calendar_events`, `get_dashboard_config`, `get_energy_history`,
`get_entities_by_domain`, `get_entities_on`, `get_ha_automations`, `get_ha_health`,
`get_home_status`, `get_weather_forecast`, `list_dashboards`, `propose_dashboard`,
`set_input_helper`, `toggle_automation`, `trigger_automation`.

Sono marcati **[MUTO]** nelle schede sotto. Il gruppo non e' casuale: contiene l'intera
superficie di attuazione diretta non-`call_ha_service` (`trigger_automation`,
`toggle_automation`, `set_input_helper`), l'intera superficie plance in lettura/proposta
(`list_dashboards`, `get_dashboard_config`, `propose_dashboard`) e l'unico tool che chiude
il ciclo dello step-up (`confirm_pending`).

## 7.4 Schede — letture di stato

### 1. `get_entity_states` — `tools/ha_tools.py:13-27`

- **Dichiara**: «Get current state of specific Home Assistant entities by ID.»
- **Fa davvero**: `tools/dispatcher.py:258-264` applica in cascata due filtri agli `ids`
  richiesti — prima `visible_entity_ids` (contesto semantico), poi `allowed_entities` per
  glob — e chiama `ha_tools.get_entity_states` (`ha_tools.py:69`). Le entita' fuori
  perimetro sono **scartate in silenzio**, non rifiutate.
- **Chi**: A, B, C, D.
- **Filtri**: perimetro entita' nel dispatcher; sul gateway anche la denylist di lettura in
  ingresso (`handlers_execute.py:328-333`) e la potatura in uscita
  (`read_denylist.py:397`, chiave `entities`).

### 2. `get_area_entities` — `tools/ha_tools.py:29-39`

- **Dichiara**: scopre aree e entita' assegnate, mappa `area_name -> [entity_ids]`, con
  `__no_area__` per le orfane.
- **Fa davvero**: `dispatcher.py:255-257` chiama il tool e poi `_filter_area_map`
  (`dispatcher.py:78-93`), che pota gli entity_id non permessi dentro ogni area e poi
  scarta le aree rimaste vuote.
- **Chi**: A, B, C, D. **Filtri**: perimetro entita'; potatore dedicato `_pota_aree`
  (`read_denylist.py:399`).

### 3. `get_home_status` — `tools/ha_tools.py:41-48` **[MUTO]**

- **Dichiara**: «compact summary of all useful home entities … first call to understand
  the current home state».
- **Fa davvero**: `dispatcher.py:324-329` verifica prima che l'inventario sia leggibile
  (`_cache_non_leggibile`, `dispatcher.py:223-227`) e in caso di guasto restituisce
  l'errore invece di una lista vuota; poi legge dalla cache (`ha_tools.py:140`) e filtra.
  **Non interroga HA**: e' un dump della `EntityCache`.
- **Chi**: A, B, C, D. E' il primo tool suggerito nei modelli preconfigurati
  (`templates.js:12, 18, 24, 30, 36`).

### 4. `get_entities_on` — `tools/ha_tools.py:50-54` **[MUTO]**

- **Dichiara**: tutte le entita' in stato `on`.
- **Fa davvero**: `dispatcher.py:330-335`, stesso guardiano dell'inventario, poi
  `ha_tools.py:157` sulla cache, poi `_filter_entities`.
- **Chi**: A, B soltanto. Assente da `mcp/tiers.py` e da `READ_TOOLS`: **irraggiungibile
  dal gateway e dalla chat ad abbonamento**.

### 5. `get_entities_by_domain` — `tools/ha_tools.py:56-66` **[MUTO]**

- **Dichiara**: tutte le entita' di un dominio.
- **Fa davvero**: `dispatcher.py:336-341`; `inputs["domain"]` e' letto con accesso nudo,
  quindi una chiamata senza `domain` cade nel ramo `KeyError` (`dispatcher.py:768-779`) e
  torna «Campo obbligatorio mancante».
- **Chi**: A, B soltanto.

### 6. `get_energy_history` — `tools/energy_tools.py:6-27` **[MUTO]**

- **Dichiara**: storico energia ultimi N giorni, record giornalieri compressi
  `{id, day, start, end, n}`, con l'invito a calcolare il delta da `start`/`end`.
- **Fa davvero**: `dispatcher.py:342-343` → `energy_tools.py:50`. **Nessun filtro di
  perimetro applicato**: `allowed_entities` non viene passato, a differenza di quasi tutte
  le altre letture. Le entita' sorgente sono scelte dalla `semantic_map`.
- **Chi**: A, B. Assente dal gateway.

### 7. `get_history` — `tools/history_tools.py:15-35`

- **Dichiara**: dati storici/serie temporali, «READ-only», bucket compressi per le
  numeriche e campioni sotto-campionati per le altre, «Never unbounded raw dumps».
- **Fa davvero**: `dispatcher.py:265-278` filtra gli `entity_ids` con `visible_entity_ids`
  e `allowed_entities`, poi `history_tools.get_history` (`:177`), che instrada fra recorder
  e statistiche sulla soglia `RECORDER_WINDOW_DAYS = 10` (`history_tools.py:11`) e applica
  i tetti `MAX_ENTITIES=20`, `MAX_DAYS=365`, `MAX_RAW_POINTS=500` (`:8-10`).
- **Chi**: A, B, C, D. Potatore `series` (`read_denylist.py:398`).

### 8. `get_weather_forecast` — `tools/weather_tools.py:9-29` **[MUTO]**

- **Dichiara**: previsioni per la posizione di casa, orarie fino a 48 h e giornaliere oltre.
- **Fa davvero**: `dispatcher.py:344-345` → chiamata HTTP esterna a Open-Meteo
  (`weather_tools.py:7`). E' l'unico tool di lettura che esce da casa e **non passa dal
  perimetro `allowed_endpoints`** di `http_request`.
- **Chi**: A, B. Assente da `mcp/tiers.py`; il test di sincronia lo dichiara come
  citazione lecita solo sul percorso locale
  (`tests/test_tools_catalog_sync.py:262-271`), e i modelli Clima e Irrigazione dicono
  esplicitamente cosa fare quando non c'e' (`templates.js:30, 36`).

### 9. `get_ha_health` — `tools/health_tools.py:4-51` **[MUTO]**

- **Dichiara**: report di salute strutturato, sette sezioni piu' `all`, dati in cache
  aggiornati via WebSocket e ogni 30 minuti; spiega la differenza fra `unavailable` (adesso)
  e le segnalazioni del Brain (oltre due giorni); «Read-only: this tool cannot start, stop
  or update anything».
- **Fa davvero**: `dispatcher.py:604-605` → `health_tools.py:54`, che e' quattro righe:
  se `health_monitor` e' `None` torna un errore, altrimenti `get_snapshot(sections or ["all"])`.
  **Nessun perimetro di entita'**: la sezione `unavailable` nomina entita' di tutta la casa.
- **Chi**: A, B. Assente da `mcp/tiers.py` e `READ_TOOLS`.

### 10. `get_advisories` — `tools/advisory_tools.py:59-98`

- **Dichiara**: la descrizione piu' lunga del catalogo (39 righe). Elenca le segnalazioni
  aperte del Brain, spiega i tre livelli di `severity`, e dedica meta' del testo a tre
  bandiere di parzialita' che il modello deve riferire all'utente: `truncated`,
  `evidence_truncated`, `filtered`. Chiude con «Sola lettura: questo tool non puo' chiudere,
  archiviare o modificare una segnalazione».
- **Fa davvero**: `dispatcher.py:606-615` normalizza `severity` vuota a `None` e passa
  `allowed_entities` dentro `get_advisories` (`advisory_tools.py:202`), che filtra le voci
  per perimetro (`_voce_nel_perimetro`, `:160`) e limita i campi esposti a
  `_CAMPI_ESPOSTI` (`advisory_tools.py:57`).
- **Chi**: A, B, C. **Non D** — vedi reperto R3.

### 11. `get_logbook` — `tools/diagnostics_tools.py:48-90`

- **Dichiara**: cronologia eventi HA per domande sul passato recente; `entity_id`
  facoltativo («omesso significa tutta la casa»); distingue esplicitamente `truncated`
  (finestra) da `filtered` (perimetro) e dice che i due `shown` contano cose diverse.
- **Fa davvero**: `dispatcher.py:279-317`. Qui vive un'asimmetria dichiarata nel codice
  (`dispatcher.py:284-288`): a differenza di `get_entity_states`/`get_history`, un
  `entity_id` fuori dal contesto visibile **rifiuta la chiamata** invece di scartarlo, perche'
  scartarlo equivarrebbe a chiedere il logbook dell'intera casa. Il commento a
  `:295-308` avverte anche che il rifiuto su `visible_entity_ids` e' aggirabile omettendo
  `entity_id`, ed e' voluto.
- **Chi**: A, B, C. **Non D** — reperto R3.

### 12. `render_template` — `tools/diagnostics_tools.py:92-116`

- **Dichiara**: valuta un template Jinja di HA; «Sola lettura: Home Assistant si limita a
  renderizzare, il template non puo' chiamare servizi ne' modificare stati»; tetto
  `MAX_TEMPLATE_LEN`.
- **Fa davvero**: `dispatcher.py:318-323` → `diagnostics_tools.py:244`. E' vero che non
  scrive, ma **nessun perimetro di entita' e' applicabile**: un template le legge tutte per
  costruzione (commento a `dispatcher.py:319-322`).
- **Chi**: solo A, e solo se concesso esplicitamente. E' l'unico tool escluso da tre
  cataloghi con tre motivazioni scritte a mano:
  `EVALUATION_ONLY_TOOLS` (`claude_runner.py:237-247`), `mcp/tiers.py:45-60`,
  `READ_TOOLS` (`handlers_gateway_policy.py:26-38`).
- **Filtri**: rimosso dai tool passati al modello se il bot non ha whitelist esplicita ma
  ha un perimetro di entita' (`claude_runner.py:722-723`; gemelli
  `openai_compat_runner.py:553-554` e `:839-840`). La casella nel Designer avvisa
  («Legge tutta la casa … Solo bot di chat», `templates.js:87`).

## 7.5 Schede — automazioni HA

### 13. `get_ha_automations` — `tools/automation_tools.py:3-7` **[MUTO]**

- **Dichiara**: elenca le automazioni HA col loro stato.
- **Fa davvero**: `dispatcher.py:351-352` → `automation_tools.py:35`, che inoltra a
  `ha.get_automations()`. **Nessun filtro**, nemmeno di perimetro.
- **Chi**: A, B. Assente dal gateway (che pero' espone `get_automation_config`, il quale
  nella sua descrizione dice «Use get_ha_automations first to list them» — vedi R15).

### 14. `get_automation_config` — `tools/automation_tools.py:53-69`

- **Dichiara**: legge la configurazione completa di un'automazione creata da UI; accetta
  entity_id, object_id o id numerico; «Returns an error for automations defined by hand in YAML».
- **Fa davvero**: `dispatcher.py:353-364` toglie il prefisso `automation.` e valida: gli id
  puramente numerici usano la via rapida, tutto il resto deve soddisfare
  `_AUTOMATION_ID_RE = ^[a-z0-9_]+$` (`dispatcher.py:11`), altrimenti errore — difesa contro
  SSRF/path-injection.
- **Chi**: A, B, C, D. Potatore dedicato (`read_denylist.py:402`).

### 15. `trigger_automation` — `tools/automation_tools.py:9-19` **[MUTO]**

- **Dichiara**: «Immediately trigger a Home Assistant automation by its ID.» Una riga, senza
  alcun accenno a conferme o semaforo.
- **Fa davvero**: `dispatcher.py:365-387`, catena di quattro controlli prima di attuare:
  regex sull'id, `allowed_services` su `automation.trigger`, `allowed_entities` su
  `automation.<id>`, e infine il **semaforo universale** `_gate` (`dispatcher.py:182-221`)
  se l'azione non e' gia' `tier_confirmed`. Solo allora `automation_tools.py:40` chiama
  `ha.call_service("automation", "trigger", …)`.
- **Chi**: solo A. Escluso da `EVALUATION_ONLY_TOOLS` per nome nel commento
  (`claude_runner.py:222-224`); assente da `mcp/tiers.py` e `_HARD_EXECUTE_ALLOWED`.

### 16. `toggle_automation` — `tools/automation_tools.py:21-32` **[MUTO]**

- **Dichiara**: abilita o disabilita un'automazione. Anche qui nessun accenno al gate.
- **Fa davvero**: `dispatcher.py:388-412`, identico al precedente ma il servizio verificato
  e' `automation.turn_on` o `automation.turn_off` a seconda di `enabled`, e il semaforo riceve
  il servizio corretto (`:407`).
- **Chi**: solo A. Stesse esclusioni di `trigger_automation`.

## 7.6 Schede — attuazione e conferma

### 17. `call_ha_service` — `claude_runner.py:139-151`

- **Nota**: e' l'unico tool d'azione la cui definizione **non** vive in `tools/`, ma dentro
  `claude_runner.py`.
- **Dichiara**: «Call a Home Assistant service to control devices (light, switch, climate,
  etc.)». Lo schema espone `domain`, `service`, `data` — **`target` non e' nello schema**,
  pur essendo letto dal dispatcher (`dispatcher.py:417`).
- **Fa davvero**: `dispatcher.py:413-456`, il ramo piu' difeso del file:
  1. `normalize_target` fonde `target` dentro `data` una volta sola (`:422`), cosi' le entita'
     valutate dal gate sono esattamente quelle inoltrate a HA;
  2. se il target e' per area/dispositivo/label → **rifiuto secco** (`:433-435`), perche' HA
     attuerebbe l'intero gruppo lato server scavalcando gli override per-entita';
  3. semaforo `_gate` (`:436-441`), saltato solo se `tier_confirmed`;
  4. `allowed_services` per glob (`:442-446`);
  5. `allowed_entities`, con il caso speciale «whitelist attiva ma nessun target» → rifiuto
     (`:447-455`).
- **Chi**: A, C, D. Escluso da `EVALUATION_ONLY_TOOLS` (`claude_runner.py:222-224`).
- **Sul gateway**: prima del dispatcher c'e' un secondo instradamento a tier in
  `handlers_execute.py:181-253`, che per giallo/rosso crea un pending e notifica invece di
  eseguire; un dominio pericoloso giallo viene **forzato a rosso** (`:230-235`).
- **Nome**: sul catalogo MCP si chiama `call_service` (`mcp/tiers.py:125`) — unico caso di
  divergenza di nome fra cataloghi.

### 18. `set_input_helper` — `tools/calendar_tools.py:118-138` **[MUTO]**

- **Nota**: definito nel modulo *calendario*, non in uno di attuazione.
- **Dichiara**: imposta il valore di un input helper HA (boolean/number/text/select).
  Nessun accenno al semaforo.
- **Fa davvero**: `dispatcher.py:522-565`. Controlla `value` presente, poi `allowed_services`
  contro le tre forme possibili del dominio (`turn_on`/`set_value`/`select_option`,
  `:533-541`), poi `allowed_entities`, poi risolve il servizio **prima** di attuare
  (`resolve_input_helper_service`, `calendar_tools.py:144`) per poter passare al semaforo il
  `domain.service` esatto (`dispatcher.py:559-564`). Il commento a `:546-551` dichiara la
  scelta di fallire localmente e non delegare la rivalidazione a valle.
- **Chi**: solo A. Citato per nome in `handlers_execute.py:20` come esempio di cio' che la
  execute-API non deve **mai** esporre.

### 19. `send_notification` — `tools/notify_tools.py:79-120`

- **Dichiara**: «Use THIS tool for ANY notification — do NOT call_ha_service on
  persistent_notification/notify»; quattro canali (`ha_persistent`, `ha_push`, `apprise`,
  `retropanel`); messaggio vuoto + `notification_id` per rimuovere una notifica persistente.
- **Fa davvero**: `dispatcher.py:346-350` → `notify_tools.py:123`. **Nessun gate, nessun
  perimetro**: il razionale e' che una notifica informa e non attua.
- **Chi**: A, C, D. **Non B**: escluso da `EVALUATION_ONLY_TOOLS`
  (`claude_runner.py:222-224`) per non far agire un agente reattivo su prompt injection.
- **Asimmetria**: sul gateway e' in `_ALWAYS_EXPOSED` (`handlers_execute.py:36`), quindi
  raggiungibile **anche senza** che la policy salvata lo elenchi. Un client MCP remoto puo'
  sempre notificare; un Agentbot locale non puo' mai.

### 20. `confirm_pending` — `claude_runner.py:166-179` **[MUTO]**

- **Nota**: seconda delle due definizioni che vivono in `claude_runner.py`.
- **Dichiara**: «Conferma un'azione a rischio in attesa fornendo il codice ricevuto sul
  telefono. Usa questo tool SOLO quando l'utente ti comunica il codice.» Unico input: `code`,
  «Codice OTP a 6 cifre».
- **Fa davvero**: `dispatcher.py:753-759` — se manca `confirm_executor` risponde «Conferma
  non disponibile», se il codice e' vuoto «Codice mancante», altrimenti delega. Il cablaggio
  e' `server.py:1636-1637` → `confirm_pending_execute` (`server.py:394-403`), che valida
  `code` come esattamente 6 cifre ASCII **prima** del confronto, chiama `verify_otp`, ed
  esegue la voce pending **congelata** — mai qualcosa ri-derivato dalla tool call. L'OTP
  sblocca l'azione, non puo' alterarla.
- **Chi**: solo A, e solo con `confirm_executor` cablato. Assente da tutti i cataloghi
  remoti; presente in `templates.js:97`.
- **Filtro extra**: il `code` e' oscurato in due punti prima di tornare al client —
  `_redact_stream_tool_calls` (`claude_runner.py:385-404`) sul percorso SSE e
  `handlers_chat.py:477-482` sul payload di debug. E' anche fra le chiavi redatte nei log
  del dispatcher (`dispatcher.py:251`, `_REDACT_KEYS` contiene `code`).
- **Contesto**: chiude il ciclo aperto da `_gate` quando il verdetto e' `confirm`
  (`dispatcher.py:205-219`). Senza `confirm_pending` lo step-up in chat non ha uscita.

## 7.7 Schede — task

### 21. `create_task` — `tools/task_tools.py:7-50`

- **Dichiara**: pianifica un task differito; quattro tipi di trigger (`delay`, `at_time`,
  `at_datetime`, `time_window`), condizione facoltativa, tre tipi di azione
  (`call_ha_service`, `send_notification`, `create_task` per il concatenamento).
- **Fa davvero**: `dispatcher.py:457-498`. Deny-by-default sui tipi di azione
  (`_ALLOWED_TASK_ACTIONS`, `dispatcher.py:14`), poi `allowed_services` sulle sole azioni
  `call_ha_service`. Il commento a `:465-482` dichiara un'**asimmetria voluta**: il servizio
  e' controllato qui, l'entita' **no** — un'azione fuori perimetro viene accettata alla
  creazione e rifiutata solo allo scatto da `task_engine._run_action`, per non duplicare il
  punto di enforcement. Il costo dichiarato e' un messaggio d'errore peggiore, non un confine
  piu' debole.
- **Chi**: A, B, C, D.
- **Sul gateway**: `handlers_execute.py:271-293` aggiunge un filtro che accetta solo azioni
  `call_ha_service` con entita' esplicite e **verdi**. Il commento a `mcp/tiers.py:71-92`
  documenta che quel filtro vale solo sul **primo livello**: un task annidato non e'
  ispezionato, e la scelta e' stata di correggere la promessa nella descrizione MCP
  (`tiers.py:93-102`) invece di rendere ricorsivo il filtro.

### 22. `list_tasks` — `tools/task_tools.py:52-69`

- **Dichiara**: elenca i task attivi e quelli conclusi nelle ultime 24 h; filtri per
  `agent_id` o `status`.
- **Fa davvero**: `dispatcher.py:499-508`. Accetta anche la vecchia chiave `chatbot_id`
  (`:506`) perche' un client MCP che l'avesse imparata non riceva in silenzio una lista
  **non** filtrata.
- **Chi**: A, B, C, D. Classificato `Tier.SCHEDULE` in `tiers.py:103` e `PROPOSE_TOOLS`
  (`handlers_gateway_policy.py:45`) pur essendo di fatto una lettura — per questo la
  denylist lo tratta a parte (`PRUNED_NON_READ_TOOLS`, `read_denylist.py:412`) con un
  potatore dedicato (`:404`).

### 23. `cancel_task` — `tools/task_tools.py:71-81`

- **Dichiara**: annulla un task pending; errore se gia' in esecuzione o concluso.
- **Fa davvero**: `dispatcher.py:509-515` → `task_tools.py:113`. Il commento a
  `mcp/tiers.py:105-109` dichiara un residuo noto e non chiuso: **non filtra per
  `agent_id`**, quindi dal gateway si puo' annullare anche un task creato dall'utente in
  HIRIS. Motivazione: e' un impedimento, non un'attuazione.
- **Chi**: A, B, C, D.

## 7.8 Schede — calendario

### 24. `get_calendar_events` — `tools/calendar_tools.py:9-35` **[MUTO]**

- **Dichiara**: prossimi eventi dai calendari HA. Meta' della descrizione e' un contratto
  sull'errore: se la risposta porta `error` e `unavailable_calendars`, l'elenco e' incompleto
  e il modello deve dire cosa non ha potuto controllare invece di dire che non c'e' nulla.
- **Fa davvero**: `dispatcher.py:516-521` → `calendar_tools.py:44`. La docstring (`:49-57`)
  racconta il difetto chiuso: prima un `[]` significava sia «nessun impegno» sia «non ho
  potuto leggere», e i calendari falliti erano saltati in silenzio.
- **Chi**: A, B. Assente dal gateway.

### 25. `create_calendar_event` — `tools/calendar_tools.py:215-268`

- **Dichiara**: crea un evento; distingue `datetime` da `allday` e avverte che per gli
  eventi allday `end_date` e' **esclusivo**.
- **Fa davvero**: `dispatcher.py:566-578`, che inoltra nove parametri. **Nessun perimetro,
  nessun semaforo**: e' l'unica scrittura verso HA che non passa da `_gate`, perche' non tocca
  un dispositivo.
- **Chi**: solo A. Escluso da `EVALUATION_ONLY_TOOLS` (non elencato) e da tutti i cataloghi
  remoti.

## 7.9 Schede — rete

### 26. `http_request` — `tools/http_tools.py:266-297`

- **Dichiara**: chiamata HTTP a un'API esterna; «Only URLs matching the agent's pre-approved
  allowed_endpoints can be called»; risposta troncata a 4 KB.
- **Fa davvero**: `dispatcher.py:579-586` → `http_tools.py:186`, con a monte una batteria di
  difese SSRF: validazione dell'endpoint (`:71`), match sull'allowlist (`:111`), risoluzione
  DNS e verifica dell'IP (`:132`, `:61`) contro il rebinding.
- **Chi**: **nessuna superficie configurabile**. Vedi reperto R1.

## 7.10 Schede — memoria e conoscenza

### 27. `recall_memory` — `tools/memory_tools.py:35-64`

- **Dichiara**: «Cerca nella memoria persistente **dell'agente** informazioni rilevanti da
  sessioni precedenti.»
- **Fa davvero**: `dispatcher.py:587-594` → **`KnowledgeStore`**, non la vecchia
  `MemoryStore`: `has_memory` (`dispatcher.py:229-233`) gate proprio sullo store unificato
  dopo Slice 3. Owner = `user_id or "home"`, scope = `chatbot_id or "hiris-default"`.
- **Chi**: A, B. **Non C/D**.

### 28. `save_memory` — `tools/memory_tools.py:66-93`

- **Dichiara**: salva nella memoria persistente dell'agente; i ricordi restano fino alla
  scadenza configurabile (90 giorni di default, illimitata a 0).
- **Fa davvero**: `dispatcher.py:595-603`, stesso store di `recall_memory`, con
  `retention_days` dal costruttore.
- **Chi**: solo A. Escluso da `EVALUATION_ONLY_TOOLS` con motivazione esplicita
  (`claude_runner.py:248`: rischio di scrittura da prompt injection via stato HA).

### 29. `save_knowledge` — `tools/knowledge_tools.py:8-30`

- **Dichiara**: «Proponi di salvare … Crea una proposta che l'utente approva.»
- **Fa davvero**: mantiene la promessa. `dispatcher.py:669-684` rifiuta in partenza se manca
  store **o** embedder (senza embedding l'elemento non sarebbe mai richiamabile:
  `knowledge_store.search` filtra su `embedding IS NOT NULL`), poi
  `handle_save_knowledge` (`knowledge_tools.py:82`) scrive con `status="pending"` (`:120`)
  e torna `{"id": …, "status": "pending"}`.
- **Chi**: A, C, D. `Tier.SCHEDULE` (`tiers.py:122`), in `PROPOSE_TOOLS`.

### 30. `recall_knowledge` — `tools/knowledge_tools.py:32-43`

- **Dichiara**: una riga — «Cerca nel second brain di casa fatti/preferenze rilevanti.»
- **Fa davvero**: molto piu' della riga. `dispatcher.py:685-707` passa sei parametri di
  riservatezza; `handle_recall_knowledge` (`knowledge_tools.py:126`) unisce item e chunk
  documentali, e per il contenuto sensibile diretto a un backend cloud applica lo
  pseudonimizzatore o, se assente, sostituisce con «[contenuto sensibile non disponibile]»
  (`:187-195`). Un guasto dell'embedding non torna mai `{"results": []}` ma un errore
  esplicito (`:149-151`), per non far dire al modello «non ho trovato nulla» quando la frase
  vera e' «non ho potuto controllare».
- **Chi**: A, C, D. **Non B** — vedi reperto R6.

### 31. `link_knowledge` — `tools/knowledge_tools.py:45-57`

- **Dichiara**: «Collega due item del second brain **(proposta)**.»
- **Fa davvero**: **non e' una proposta**. `dispatcher.py:708-714` verifica solo lo store
  (l'embedder non serve) e chiama `handle_link_knowledge` (`knowledge_tools.py:203-214`),
  che scrive subito il link con `source="inferred"` e torna `{"ok": True}`. Nessuno stato
  pending, nessuna coda di approvazione. Vedi reperto R8.
- **Chi**: solo A.

### 32. `daily_briefing` — `claude_runner.py:153-164` **[quasi muto: una sola occorrenza fuori da questa sezione]**

- **Nota**: terza definizione dentro `claude_runner.py`. Schema vuoto, nessun parametro.
- **Dichiara**: «Riepilogo del maggiordomo per oggi: scadenze imminenti dai documenti e
  stato notevole della casa (porte/finestre aperte, batterie scariche). Sola lettura.»
- **Fa davvero**: `dispatcher.py:715-752`, il ramo con il commento piu' lungo del file.
  `allow_sensitive` e' vero solo se **entrambi** i segnali lo permettono (config dell'agente
  **e** backend locale, `:739`) — fail-closed su ciascuno. Le batterie scariche arrivano
  dalle segnalazioni gia' prodotte dal Brain (`advisory_store`), non da un calcolo fatto qui.
  Restituisce il **render deterministico** `render_briefing_template(bundle)` (`:749`), non
  `compose_briefing`, perche' il modello di chat lo narra da se'. Senza store torna una frase
  di scusa, non un briefing vuoto.
- **Chi**: solo A.

## 7.11 Schede — proposte e configurazione HA

### 33. `create_automation_proposal` — `tools/proposal_tools.py:24-81`

- **Dichiara**: propone un'automazione dopo aver spiegato la scelta di instradamento
  (HA nativo vs agente HIRIS); «The proposal is saved as disabled/pending — the user must
  explicitly activate it». La descrizione di `config` e' un avviso lungo su cosa succede in
  approvazione: id numerico = garanzia, entity_id/object_id risolti **solo** al momento
  dell'approvazione, e — caveat dichiarato — un `alias` che coincide col nome di
  un'automazione esistente **sovrascrive quella** anche senza id.
- **Fa davvero**: `dispatcher.py:616-636` fa una validazione esplicita a monte dei cinque
  campi obbligatori (`:624-627`) perche' un accesso nudo `inputs[...]` finirebbe mascherato
  dall'except generico come «non riuscito», messaggio su cui il modello non puo' agire.
- **Chi**: A, C, D. `Tier.SCHEDULE` (`tiers.py:114`).

### 34. `create_ha_config` — `tools/config_tools.py:25-46`

- **Dichiara**: crea uno script o una scena HA; «Dalla chat viene creato **subito** su HA»;
  per le plance rimanda esplicitamente a `propose_dashboard`. Enum dello schema:
  `["script", "scene"]`.
- **Fa davvero**: due comportamenti diversi secondo la superficie.
  Da chat, `dispatcher.py:637-655` respinge `kind == "dashboard"` con un guard esplicito
  (`:647-650`, perche' lo schema «non e' una garanzia forte»), normalizza e **applica subito**
  via `apply_ha_config` (`config_tools.py:89`).
  Dalla execute-API, `handlers_execute.py:297-311` **non** applica: costruisce una proposta
  pending e la mette in coda all'operatore.
- **Chi**: A, C (come proposta). `PROPOSE_TOOLS` (`handlers_gateway_policy.py:46`),
  quindi `_HARD_EXECUTE_ALLOWED`. **Ma nessun `ToolDef` in `mcp/tiers.py` lo espone** — vedi
  reperti R2 e R9.

### 35. `list_dashboards` — `tools/dashboard_tools.py:18-26` **[MUTO]**

- **Dichiara**: elenca le plance esistenti con url_path e titolo; «Usalo prima di proporre
  una modifica».
- **Fa davvero**: `dispatcher.py:656-657`, **una riga**: `await self._ha.list_dashboards()`.
  Nessuna funzione intermedia in `dashboard_tools.py`, nessun filtro, nessun perimetro.
- **Chi**: solo A. Escluso da `EVALUATION_ONLY_TOOLS` con la motivazione «chat-only per
  coerenza» (`claude_runner.py:252`).

### 36. `get_dashboard_config` — `tools/dashboard_tools.py:28-42` **[MUTO]**

- **Dichiara**: legge viste e card di una plancia; «Usalo PRIMA di proporre una sostituzione,
  cosi' la nuova configurazione parte da quella attuale e non perdi contenuti».
- **Fa davvero**: `dispatcher.py:658-659`, una riga:
  `await self._ha.get_lovelace_config(inputs.get("url_path", ""))`. `url_path` mancante
  diventa stringa vuota invece di errore.
- **Chi**: solo A. Stessa esclusione di `list_dashboards`.

### 37. `propose_dashboard` — `tools/dashboard_tools.py:44-68` **[MUTO]**

- **Dichiara**: propone di creare o sostituire una plancia; «NON scrive su Home Assistant:
  salva una proposta che l'utente attiva dalla sezione Proposte»; avverte che
  `mode='replace'` sostituisce **interamente** la configurazione e che le viste da
  conservare vanno reincluse.
- **Fa davvero**: mantiene la promessa. `dispatcher.py:660-668` → `dashboard_tools.py:71`,
  fail-closed: `mode` non stringa → rifiuto senza `AttributeError` (`:85-87`), `url_path`
  senza trattino → rifiuto, `config` senza lista `views` → rifiuto. Il commento a `:90-96`
  spiega perche' e' **piu' stretto** di `HAClient.save_dashboard_config`: la forma a strategia e'
  accettata da HA ma non e' una plancia che il modello abbia davvero composto, quindi resta
  fuori. Tetto di 256 KB (`config_tools.py:23`).
- **Chi**: solo A. E' il sostituto obbligato di `create_ha_config` per le plance, ma **il
  resto del documento non lo nomina mai** pur discutendo `create_ha_config` otto volte.

## 7.12 Reperti — disallineamenti fra cataloghi

### R1 — `http_request`: nel catalogo padre, in nessun altro

`ALL_TOOL_DEFS` lo include (`claude_runner.py:202`); e' l'**unico** dei 37 assente da
`templates.js` (36 voci contro 37). E non e' solo un buco di UI: tutti e tre i punti di
costruzione della lista tool lo rimuovono se `allowed_endpoints` e' `None`
(`claude_runner.py:724-725`, `openai_compat_runner.py:555-556` e `:841-842`), e
`allowed_endpoints` **non ha alcuna superficie nel Designer** — si imposta solo via API
diretta. Il test lo dichiara come eccezione motivata
(`tests/test_tools_catalog_sync.py:24-34`). Conseguenza: nessun agente configurato da UI
potra' mai chiamarlo, e la casella, se ci fosse, sarebbe un placebo.

### R2 — `create_ha_config`: ammesso dalla execute-API, non esposto dall'MCP

E' in `PROPOSE_TOOLS` (`handlers_gateway_policy.py:46`), quindi in `_HARD_EXECUTE_ALLOWED`
(`handlers_execute.py:30`), e ha un **ramo dedicato** in `handlers_execute.py:297-311` che
lo trasforma in proposta. Ma leggendo `mcp/tiers.py:21-129` per intero, **nessun `ToolDef`
ha `hiris_tool = "create_ha_config"`**. Il ramo e' quindi irraggiungibile dal client MCP
servito da questo repo: resta accessibile solo a un chiamante diretto di `/api/execute` in
possesso dell'internal token.

### R3 — `get_advisories` e `get_logbook`: esposti dall'MCP, invisibili alla chat ad abbonamento

Entrambi sono `Tier.READ` in `mcp/tiers.py:36` e `:41` e in `READ_TOOLS`
(`handlers_gateway_policy.py:25`), ma **non compaiono** in `_DEFAULT_CHAT_TOOLS`
(`agent/runner.py:27-30`), che ne elenca 13 dei 15. Il commento a `agent/runner.py:22-24`
motiva l'esclusione dei soli tool ponte-reasoning, che pero' in `tiers.py` non esistono
affatto — quindi la differenza 15→13 non e' spiegata da quel commento. Effetto pratico: un
utente che chatta via abbonamento non puo' chiedere «ci sono problemi in casa?» ne' «cosa e'
successo ieri sera», mentre lo stesso modello via gateway remoto puo'.

### R4 — `get_ha_health`: in `EVALUATION_ONLY_TOOLS`, fuori da ogni catalogo remoto

Presente in `EVALUATION_ONLY_TOOLS` (`claude_runner.py:232`) e in `templates.js:84`, assente
da `mcp/tiers.py` e da `READ_TOOLS`. Il gateway ha `get_advisories` (le segnalazioni del
Brain) ma non il report di salute HA, benche' la descrizione stessa di `get_ha_health`
(`health_tools.py:9-17`) spieghi che i due **non sono lo stesso dato** e che solo
`unavailable` prova che un'entita' e' giu' adesso. Dal gateway quel controllo non e'
disponibile.

### R5 — `call_ha_service` vs `call_service`: unica divergenza di nome

`mcp/tiers.py:125` espone il tool come `call_service` mappandolo su `hiris_tool =
"call_ha_service"`. E' l'unico dei 37 con due nomi. Il rischio e' pinnato in
`tests/test_tools_catalog_sync.py:242-257`.

### R6 — `recall_memory` e' di valutazione, `recall_knowledge` no — stesso store

`recall_memory` e' in `EVALUATION_ONLY_TOOLS` (`claude_runner.py:231`, con il commento
«read-only — safe for non-chat agents»), `recall_knowledge` no. Dopo Slice 3 entrambi
leggono lo **stesso** `KnowledgeStore`: `dispatcher.py:229-233` lo dice esplicitamente
(«save_memory/recall_memory route into the unified KnowledgeStore»), e i due rami
(`:587-594` e `:685-707`) chiamano lo stesso oggetto. La distinzione fra i due cataloghi
riflette quindi una separazione che nel dispatcher non esiste piu'.

### R7 — `EVALUATION_ONLY_TOOLS` e' documentato «read-only» ma contiene tre scritture

`claude_runner.py:934` lo descrive come «restricted to read-only (`EVALUATION_ONLY_TOOLS`)
tools», e il commento del set (`:221-224`) dice «Excludes direct-execution tools». Il set
pero' include `create_task`, `list_tasks`, `cancel_task` (`:230`): `create_task` scrive sul
TaskEngine e puo' pianificare azioni `call_ha_service`, `cancel_task` rimuove un task
altrui. Il fatto che sia voluto e' documentato altrove — `watcher/agentbot_runner.py:37-43`
spiega che un Agentbot con perimetro passa le sue allow-list nel task — ma i due testi si
contraddicono su cosa sia «read-only».

### R8 — `link_knowledge` dichiara una proposta, scrive un fatto

La descrizione recita «Collega due item del second brain **(proposta)**»
(`knowledge_tools.py:47`). L'implementazione (`knowledge_tools.py:203-214`) chiama
`store.add_link(..., source="inferred")` e torna `{"ok": True}`: nessuno `status="pending"`,
nessuna coda. Il tool gemello `save_knowledge`, la cui descrizione fa la stessa promessa,
la **mantiene** (`:120`). La divergenza e' fra due tool definiti a dodici righe di distanza.

### R9 — Il guard sulle plance esiste in chat, non nella execute-API

`dispatcher.py:647-650` respinge `create_ha_config(kind="dashboard")` con la motivazione
esplicita che l'enum dello schema «non e' una garanzia forte». `handlers_execute.py:297-311`
chiama `normalize_config_inputs(inputs)` **senza** quel guard, e `VALID_KINDS` include
`"dashboard"` (`config_tools.py:10`, ramo di validazione a `:70-74`). Dalla execute-API una
plancia puo' quindi nascere come proposta `ha_dashboard` per una via che la chat ha chiuso.
Il gate umano regge (resta pending), ma la regola «le plance passano solo da
`propose_dashboard`» vale su una sola delle due superfici.

### R10 — `send_notification`: sempre esposto al gateway, mai agli agenti locali

`_ALWAYS_EXPOSED = frozenset({"send_notification"})` (`handlers_execute.py:36`) lo rende
raggiungibile dal gateway anche se la policy salvata non lo elenca. Lo stesso tool e' escluso
da `EVALUATION_ONLY_TOOLS` per nome (`claude_runner.py:222-224`) proprio per impedire a un
agente reattivo di agire su testo iniettato. Le due decisioni sono difendibili
separatamente; insieme dicono che il canale remoto e' piu' fidato del canale locale.

### R11 — `list_tasks` e' catalogato come proposta, trattato come lettura

`Tier.SCHEDULE` in `tiers.py:103` e dentro `PROPOSE_TOOLS`
(`handlers_gateway_policy.py:45`), ma `read_denylist.py:407-412` deve reintrodurlo a mano
(`PRUNED_NON_READ_TOOLS`) perche' la sua risposta porta fuori gli stessi identificativi delle
letture. Il potatore c'e' (`read_denylist.py:404`). E' un tool che sta nel catalogo sbagliato
e viene recuperato da un'eccezione dedicata.

### R12 — Riferimenti di riga sfasati in `watcher/agentbot_runner.py`

La docstring del modulo cita `claude_runner.py:210-222` per `EVALUATION_ONLY_TOOLS`
(`agentbot_runner.py:31`) e `claude_runner.py:894-896` per il non-restringimento dei tool
(`:29-30`). Aperte le righe: `EVALUATION_ONLY_TOOLS` e' a **225-253**, e **894-896** sono
`knowledge_allow_sensitive`/`knowledge_kinds`/`user_id`, tre kwarg passati a una chiamata di
streaming — non il filtro descritto. Il commento del set e' a 221-224, quindi il riferimento
sbagliato punta a cavallo fra commento e definizione. Il contenuto dell'affermazione resta
vero (`claude_runner.py:966-968`: `if allowed_tools:` e' falso su `[]`, quindi non restringe);
sono i puntatori a essere andati fuori sincrono.

### R13 — Il catalogo UI cita `render_template` come «Solo bot di chat», il backend lo impone solo a meta'

`templates.js:87` avverte «Solo bot di chat». Il backend pero' lo rimuove **solo** quando
`not allowed_tools and allowed_entities is not None` (`claude_runner.py:722-723`): un bot
di chat **senza** perimetro di entita' e senza whitelist esplicita riceve comunque
`render_template` insieme a tutto il resto. Il commento a `:713-721` lo dichiara scelta
consapevole («Chi NON ha perimetro vede gia' tutto»), ma l'etichetta della casella non lo
dice.

### R14 — Tre tool d'attuazione non nominano mai il semaforo nella loro descrizione

`trigger_automation` (`automation_tools.py:11`), `toggle_automation` (`:23`) e
`set_input_helper` (`calendar_tools.py:120-124`) si descrivono al modello come azioni
immediate e incondizionate. Tutti e tre passano invece da `_gate`
(`dispatcher.py:380-386`, `:405-411`, `:546-564`) e possono tornare
`confirmation_required`. `call_ha_service` e' nella stessa condizione
(`claude_runner.py:141`), mentre i tool MCP corrispondenti **lo dicono**
(`tiers.py:126-128`: «Azione gated dal semaforo: puo' tornare 'pending_approval'»). Il
catalogo locale e' meno onesto di quello remoto sullo stesso confine.

### R15 — `get_automation_config` sul gateway rimanda a un tool che il gateway non ha

La descrizione MCP di `get_automation_config` (`tiers.py:32-35`) dice «use
get_ha_automations to list them», ma `get_ha_automations` non e' fra i 15 `ToolDef` di
`tiers.py` ne' in `READ_TOOLS`. Il modello remoto riceve un'istruzione che non puo' eseguire.
La descrizione locale ha la stessa frase (`automation_tools.py:58`) ma li' il tool c'e'.

## 7.13 Sintesi numerica

- **37** definizioni in `ALL_TOOL_DEFS`; **3** vivono fuori da `tools/`
  (`call_ha_service`, `daily_briefing`, `confirm_pending`, tutte in `claude_runner.py`).
- **36** raggiungibili dal Designer; **1** (`http_request`) da nessuna UI.
- **18** disponibili a un agente non-chat; le altre **19** sono fuori da
  `EVALUATION_ONLY_TOOLS` (alcune restano comunque raggiungibili via MCP).
- **15** esposte via MCP, di cui **13** alla chat ad abbonamento.
- **16** ammesse dalla execute-API, di cui **1** (`create_ha_config`) senza alcun tool MCP
  che possa invocarla.
- **12** raggiungibili da una sola superficie (solo chat locale): `trigger_automation`,
  `toggle_automation`, `set_input_helper`, `create_calendar_event`, `save_memory`,
  `render_template`, `list_dashboards`, `get_dashboard_config`, `propose_dashboard`,
  `link_knowledge`, `daily_briefing`, `confirm_pending`. Di queste, **7 sono fra i 15 mai
  nominati** nel documento (`trigger_automation`, `toggle_automation`, `set_input_helper`,
  `list_dashboards`, `get_dashboard_config`, `propose_dashboard`, `confirm_pending`).
  A `http_request` non corrisponde alcuna superficie configurabile, e non e' nominato dalla
  UI ne' dai cataloghi remoti.

---

# 8. Il ciclo di vita del processo: migrazioni, avvio, job periodici, spegnimento

Terzo censimento: che cosa succede fra l'accensione e lo spegnimento dell'add-on. Le migrazioni di
schema degli archivi SQLite, i quaranta passi di `_on_startup` con il loro ramo d'errore uno per
uno, i job periodici registrati e su quale scheduler, e l'ordine esatto dello spegnimento. La
sezione 3 descrive il guscio; qui c'e' l'inventario, con la regola che ne emerge: cio' che parla
con il mondo esterno degrada e prosegue, cio' che apre un file locale o costruisce un archivio
SQLite abbatte il boot.

Il processo e' un unico eseguibile: `main.py:7-14` configura il logging e chiama
`web.run_app(create_app(), host="0.0.0.0", port=8099)`. `create_app` (`server.py:2778-2786`)
registra tre middleware, `_on_startup` come `app.on_startup` e `_on_cleanup` come `app.on_cleanup`.
Tutto il ciclo di vita sta in quei due agganci.

---

## 8.1 Le migrazioni

### 8.1.1 Il motore comune — `storage.py`

`connect()` (`storage.py:16-33`) apre ogni DB SQLite di HIRIS con le stesse PRAGMA: `journal_mode=WAL`
(`storage.py:29`), `synchronous=NORMAL` (`storage.py:30`), `foreign_keys=ON` (`storage.py:31`),
`busy_timeout=5000` (`storage.py:32`), `row_factory = sqlite3.Row` (`storage.py:28`), e crea la
directory genitore (`storage.py:26`).

`init_schema(conn, schema_sql, *, version, migrations)` (`storage.py:36-62`) e' l'unico versionatore.
La sequenza esatta:

1. `storage.py:49-51` — conta le tabelle utente PRIMA di toccare qualsiasi cosa (`pre_tables`).
2. `storage.py:52` — `conn.executescript(schema_sql)`: lo schema viene eseguito **sempre e per primo**,
   prima di ogni migrazione. E' la trappola documentata in `chat_store.py:96-104`.
3. `storage.py:53-55` — legge `PRAGMA user_version`. Se e' 0: DB senza tabelle prima del passo 2 =
   installazione fresca, si timbra direttamente `version` e **non gira nessuna migrazione**
   (`storage.py:55`); DB con tabelle ma `user_version==0` = archivio pre-versionamento, si assume
   baseline 1.
4. `storage.py:56-59` — esegue `migrations[k]` per ogni `k` da `current+1` a `version`. `migrations[k]`
   porta da `k-1` a `k`.
5. `storage.py:60-61` — `PRAGMA user_version = version` e `commit()`.

Due osservazioni sul motore, entrambe leggibili nelle righe citate:

- **Un buco nel dizionario `migrations` e' silenzioso.** `storage.py:57-59` fa
  `mig = (migrations or {}).get(target)` e `if mig is not None`: se manca la callable per un livello,
  il livello viene saltato senza log e la riga 60 timbra comunque `user_version = version`. Il DB
  risulta "migrato" senza che nulla sia stato trasformato. E' voluto per `AdvisoryStore` (vedi 8.1.5),
  ma vale per chiunque.
- **Nessuna transazione esplicita attorno alle migrazioni.** Non c'e' `BEGIN`/`ROLLBACK` in
  `storage.py:36-62`: il `commit()` e' uno solo, alla riga 61, dopo l'ultima migrazione.

**Se una migrazione solleva**: l'eccezione risale da `init_schema` al costruttore dello store, e da li'
a `_on_startup` — dove nessuno di questi costruttori e' avvolto in `try/except` (vedi 8.2). L'avvio
dell'add-on si interrompe.

### 8.1.2 `chat_store.py` — v1 → v2 (`chat_store.py:107-121`)

Cosa migra: rinomina la colonna `agent_id` in `chatbot_id` nella tabella `chat_messages`
(`chat_store.py:114-116`) e in `chat_sessions` (`chat_store.py:117-119`), e droppa i vecchi indici
`idx_msg_agent` / `idx_sess_agent` (`chat_store.py:120-121`), che SQLite non rinomina insieme alla
colonna.

Da quale formato: l'archivio scritto prima del rinominamento Agent → Chatbot (SP-4 Fase A).

E' idempotente: entrambi i rami sono guardati da `PRAGMA table_info` (`chat_store.py:114-115` e
`117-118`), i `DROP INDEX` sono `IF EXISTS`.

Nota di ordine: gli indici nuovi `idx_msg_chatbot`/`idx_sess_chatbot` sono deliberatamente **fuori**
da `_SCHEMA` e ricreati in `ChatStore.__init__` **dopo** `init_schema` (`chat_store.py:128-137`),
perche' `executescript(_SCHEMA)` gira prima della migrazione e su un DB v1 la colonna `chatbot_id`
non esiste ancora. Il motivo e' scritto per esteso in `chat_store.py:96-104`.

Serve ancora: si', per ogni installazione che abbia chattato prima del rinominamento. Su un DB fresco
non gira mai (`storage.py:55`).

### 8.1.3 `brain/knowledge_store.py` — v1 → v2 → v3 (`knowledge_store.py:68-79`)

- **v2** (`knowledge_store.py:68-71`): `ALTER TABLE knowledge_items ADD COLUMN lens TEXT`. Aggiunge lo
  scope per-agente alla memoria RAG (Slice 3). **Non e' guardata**: nessun controllo `table_info`
  prima dell'`ALTER`, a differenza della v3 poco sotto. Se la colonna esistesse gia', SQLite
  solleverebbe. Protetta solo da `user_version`.
- **v3** (`knowledge_store.py:74-79`): rinomina `lens` in `chatbot_id`. Guardata da `PRAGMA table_info`
  (`knowledge_store.py:77-79`), quindi idempotente.

Registrazione: `init_schema(..., version=3, migrations={2: _migrate_v2, 3: _migrate_v3})`
(`knowledge_store.py:86-89`).

Servono ancora: si', per gli archivi creati prima di Slice 3 e prima del rinominamento. Attenzione
alla catena: un archivio **pre-versionamento** (tabelle presenti, `user_version==0`) viene baselinato
a 1 da `storage.py:55` e quindi si prende **sia** la v2 sia la v3 — cioe' l'`ADD COLUMN lens` non
guardato.

### 8.1.4 `watcher/sentinel_store.py` — v1 → v2 (`sentinel_store.py:28-39`)

Cosa migra: `wake_counts` guadagna la colonna `scope` e la chiave primaria diventa `(scope, day)`.
SQLite non sa alterare una PRIMARY KEY in luogo, quindi si ricostruisce: rinomina in
`wake_counts_old`, crea la tabella nuova, copia le righe taggandole `scope='events'` (l'unico scope
esistente prima), droppa la vecchia (`sentinel_store.py:34-39`).

Da quale formato: il contatore risvegli con la sola colonna `day`.

**Non e' idempotente e non ha guardie**, a differenza di `chat_store._migrate_v2` e
`knowledge_store._migrate_v3`: e' un `executescript` di quattro istruzioni secche
(`sentinel_store.py:34-39`), senza `IF EXISTS` sul rename ne' controllo su `wake_counts_old`. Se il
blocco si interrompe a meta' — per esempio dopo il `RENAME` — il DB resta con `wake_counts_old`
presente; al riavvio `user_version` e' ancora 1, `executescript(_SCHEMA)` ricrea `wake_counts`
(`sentinel_store.py:5-25` via `storage.py:52`) e la migrazione riparte dal `RENAME TO wake_counts_old`,
che ora trova la tabella gia' li'. Non c'e' nulla nel codice letto che disinneschi questo caso.

Registrazione: `init_schema(self._conn, _SCHEMA, version=2, migrations={2: _migrate_v2})`
(`sentinel_store.py:46`).

### 8.1.5 Gli archivi senza migrazioni

- `brain/advisory_store.py:70` — `version=_VERSIONE_SCHEMA` con `_VERSIONE_SCHEMA = 2`
  (`advisory_store.py:35`) e **nessun** dizionario `migrations`. E' deliberato e motivato in
  `advisory_store.py:31-34`: la v2 aggiunge solo la tabella `advisory_notifications`
  (`advisory_store.py:25-28`), pura aggiunta che il `CREATE TABLE IF NOT EXISTS` copre da solo. E'
  esattamente il caso del "buco silenzioso" di 8.1.1, qui sfruttato come feature.
- A `version=1`, senza migrazioni, per costruzione: `history/store.py:127`, `brain/privacy.py:32`
  (vault), `brain/reasoning_log.py:32`, `reasoning/queue.py:33`, `proxy/proposal_store.py:49`,
  `brain/suggestions.py:47`, `proxy/knowledge_db.py:51`.

Totale archivi che passano da `init_schema`: 12 (`storage.py` a parte). Di questi, 3 hanno migrazioni
di schema vere (chat, knowledge, sentinel), 1 dichiara v2 senza migrazione (advisory), 8 sono a v1.

### 8.1.6 Le migrazioni che non sono migrazioni di schema

Quattro trasformazioni una-tantum vivono fuori da `init_schema`:

1. **Memorie legacy → KnowledgeStore** — `brain/memory_migration.py:32-126`, invocata a
   `server.py:1463`. Legge `<data_dir>/hiris_memory.db`, tabella `agent_memories`
   (`memory_migration.py:62-65`), e reinserisce ogni riga come item `kind="memory"`,
   `source="migrated"` (`memory_migration.py:96-107`). Le righe con embedding illeggibile passano
   comunque, con `embedding=None` (`memory_migration.py:73-82`). Il punto di commit e' il rename del
   DB legacy in `hiris_memory.db.migrated` (`memory_migration.py:110-111`): se il rename fallisce, le
   righe sono gia' salve ma un riavvio successivo puo' ri-migrarle e **duplicarle** — accettato e
   loggato come `logger.error` (`memory_migration.py:112-118`). L'idempotenza si regge su
   quell'unico marker (`memory_migration.py:56-57`).
   **Se solleva**: e' l'unica migrazione con una rete di sicurezza esplicita in `_on_startup` —
   `server.py:1462-1470` la avvolge in `try/except`, logga `logger.error` e prosegue il boot.
2. **Retrazione discovery MQTT vecchio schema** — `server.py:1349-1386`. Gira solo se MQTT e' attivo e
   il marker `<data_dir>/.mqtt_discovery_migrated_v2` non esiste (`server.py:1360-1361`). Ritira le
   entita' HA pubblicate sotto lo schema pre-rinominamento (`hiris_<id>` / `hiris/agents`) via
   `cleanup_legacy_discovery` (`server.py:1363-1366`). Il marker viene scritto **solo** se la coda di
   pubblicazione si e' davvero svuotata entro 30 s (`server.py:1375-1378`); su timeout il marker non
   si scrive e si riprova al prossimo boot (`server.py:1379-1384`). Il numero di versione nel nome del
   marker (`_v2`) e' il meccanismo per far rigirare la pulizia dopo un fix
   (`server.py:1354-1359`). **Se solleva**: `except Exception` a `server.py:1385-1386`, warning e si
   prosegue.
3. **`sentinel_lenses.json` → `agentbots.json`** — `watcher/agentbots.py:761-768`, dentro
   `load_agentbots`. Se il file nuovo non esiste e il vecchio si', `os.replace` atomico. Avvolta in
   `try/except` con warning (`agentbots.py:767-768`): un fallimento lascia il file legacy dov'e' e la
   lettura degrada a "file assente" → `[]` (`agentbots.py:773-774`).
4. **`chatbots.json` senza migrazione** — `chatbot_engine.py:139-146` scrive `schema_version: 4`, ma il
   commento alle righe 140-145 dichiara esplicitamente che **non c'e' migrazione in lettura**: un file
   v1/v2 ha semplicemente le chiavi obsolete ignorate dalla lista esplicita di campi in `_load()`.

---

## 8.2 `_on_startup` passo per passo — `server.py:1147-2694`

Circa 1550 righe, una sola funzione, nessun `try/except` che la avvolga. La regola generale che emerge
leggendola: **cio' che parla con il mondo esterno (Home Assistant, Supervisor, MQTT, Ollama, Mayan,
MCP) e' avvolto e degrada; cio' che apre un file locale o costruisce un archivio SQLite non lo e' e
abbatte il boot.**

Chi se ne accorge: nessuno automaticamente. Non c'e' un contatore di passi falliti, non c'e' una voce
in `/api/health` (`server.py:2996-2998` restituisce solo `status`, `version`, `build`). Le degradazioni
sono visibili **solo nel log dell'add-on**.

### 8.2.1 Sequenza

| # | Righe | Passo | Ramo di errore |
|---|-------|-------|----------------|
| 1 | 1152-1163 | Pre-carica `index.html` e `config.html` in memoria | `FileNotFoundError` → `logger.error`, `app[key] = ""`, prosegue. Conseguenza: `/` e `/config` rispondono 503 "UI not yet available" (`server.py:2974-2978`, `2985-2989`) |
| 2 | 1165-1194 | Token interno, CIDR ingress fidati, `execute_policy` da env, denylist di lettura, `local_execute_token` casuale | Nessuna guardia; sono parsing puri |
| 3 | 1195-1203 | `HAClient` + `await ha_client.start()` | `start()` crea solo la `ClientSession` (`proxy/ha_client.py:155-156`): non contatta HA, non puo' fallire per HA giu'. Se `HA_BASE_URL` non punta a `http://supervisor`, solo un warning (`server.py:1196-1197`) |
| 4 | 1205-1213 | Deploy della card in `www/`, scrittura `hiris-ingress.json`, registrazione risorsa Lovelace | Tutti e tre degradano: config dir assente → `logger.error` e `return` (`server.py:158-167`); Supervisor irraggiungibile → warning e `return` (`server.py:247-249`, `252-254`); WebSocket Lovelace → `except Exception` complessivo con warning (`server.py:379-380`) |
| 5 | 1215-1225 | `EntityCache`: `load` e `load_area_registry` | Entrambe avvolte singolarmente: `except Exception` → warning, prosegue (`server.py:1216-1223`). La cache resta `loaded=False`; e' il caso che il job n.1 di 8.3 esiste per recuperare |
| 6 | 1227-1246 | `data_dir`, `models_config`, policy gateway salvata, listener azioni notifica | Nessuna guardia su `load_models_config`/`apply_saved_policy` |
| 7 | 1248-1253 | `SemanticMap`: `load()` + `build_from_cache()` | **Non avvolti** (`server.py:1250-1251`): un'eccezione qui ferma l'avvio |
| 8 | 1255-1258 | `ChatbotEngine` + `await engine.start()` | **Non avvolto**. `start()` avvia lo scheduler APScheduler, apre il WebSocket HA e carica i chatbot (`chatbot_engine.py:128-133`). `start_websocket` crea solo un task (`ha_client.py:901-904`); il loop dentro riconnette da solo ogni 10 s (`ha_client.py:952-955`) e ritorna definitivamente solo se l'auth fallisce (`ha_client.py:915-917`) — silenziosamente, con un `logger.error` e nessuno che se ne accorga |
| 9 | 1260-1273 | `SupervisorClient`, solo se `SUPERVISOR_TOKEN` e' presente | Token assente → `logger.info` e la sezione supervisor dello stato di salute resta muta (`server.py:1270-1273`) |
| 10 | 1275-1282 | `HealthMonitor` + `await start()` | `start()` registra il job `health_monitor_poll` e fa un refresh immediato (`proxy/health_monitor.py:133-143`). Le singole letture dentro `refresh` sono guardate una per una (`health_monitor.py:157-167`), ma `add_job` no |
| 11 | 1284-1293 | `ProposalStore` (che registra il proprio job, `proposal_store.py:50-57`) e `KnowledgeDB` | Costruttori non avvolti: un `init_schema` che solleva ferma il boot |
| 12 | 1295-1301 | `SemanticContextMap`: `load()` + `build()` | **Non avvolti** (`server.py:1298-1299`) |
| 13 | 1303-1324 | Config notifiche (Apprise, RetroPanel), deep-link ingress, tema | `APPRISE_URLS` malformato → `except Exception` → lista vuota (`server.py:1308-1309`); slug non recuperabile → `None`, deep-link omesso (`server.py:1320-1323`, helper a `server.py:274-287`) |
| 14 | 1326-1337 | `TaskEngine` + `await start()` | `start()` avvia il proprio scheduler, carica i task e registra `task_engine_cleanup` (`task_engine.py:108-115`). Non avvolto |
| 15 | 1339-1347 | `MQTTPublisher.start()` | Host non configurato → `logger.info` e publisher disabilitato (`mqtt_publisher.py:36-38`); altrimenti solo un task di connessione (`mqtt_publisher.py:44`), niente rete sincrona |
| 16 | 1349-1386 | Retrazione discovery MQTT legacy (vedi 8.1.6, punto 2) | Avvolta, warning, prosegue |
| 17 | 1388-1438 | Lettura credenziali/provider, validazione `LOCAL_MODEL_URL`, `derive_active_providers` | URL Ollama invalido → `logger.error` e provider locale disattivato, non un crash (`server.py:1391-1397`) |
| 18 | 1440-1457 | Config RAG, `build_embedding_provider`, `KnowledgeStore` | Costruttori non avvolti |
| 19 | 1459-1470 | `migrate_agent_memories` (vedi 8.1.6, punto 1) | **L'unico** passo con `try/except` dichiaratamente anti-brick (`server.py:1459-1461`) |
| 20 | 1472-1485 | `HistoryStore`, `HistoryCapture` agganciata agli eventi di stato, `VaultStore`, `Pseudonymizer` | Non avvolti |
| 21 | 1487-1560 | Registrazione dei primi 4 job periodici (8.3, n. 1-4) | — |
| 22 | 1562-1612 | Mayan EDMS: client + job, solo se url+token+tag configurati | Config incompleta → `logger.debug` e funzione disattivata (`server.py:1608-1612`). Prima ingestione lanciata fire-and-forget (`server.py:1607`) |
| 23 | 1614-1659 | `AdvisoryStore`, adattatori step-up, `ToolDispatcher` | Non avvolti |
| 24 | 1661-1686 | `SentinelStore`, `SuggestionStore`, `ReasoningLog` | Non avvolti |
| 25 | 1688-1757 | Adattatori della Sentinella: `_gather_context`, `_llm_reason` | `_gather_context` non solleva mai (tre `return` di ripiego, `server.py:1697-1698`, `1706-1707`); `_llm_reason` cattura `RunnerBackendError` e degrada a verdetto vuoto (`server.py:1749-1754`) |
| 26 | 1759-1814 | Briefing quotidiano + solleciti urgenti: `ReminderSeen` singolo, adattatori, 2 job (8.3, n. 6-7) | — |
| 27 | 1816-1907 | Adattatori `_notify`, `_act`, `_propose`, `_on_wake` | `_on_wake` avvolge tutto: `except Exception` → `logger.exception`, `outcome="error"`, e l'evento viene comunque registrato (`server.py:1901-1907`) |
| 28 | 1909-1942 | Cache Agentbot, `Guardian`, listener di stato | `_load_agentbots` non solleva su file corrotto (`agentbots.py:775-777`) |
| 29 | 1944-1949 | Job azzeramento contatore Sentinella (8.3, n. 8) | — |
| 30 | 1951-2118 | Situazioni: snapshot, `_run_decision` con budget token e scadenza per esecuzione | La scadenza propria e' distinta da un `TimeoutError` altrui (`server.py:2055-2063`); la misura dei token e' fail-open con warning (`server.py:2071-2100`) |
| 31 | 2120-2154 | `_run_agentbot`, esposto su `app["run_agentbot"]` | — |
| 32 | 2156-2166 | `app["register_agentbot_schedules"]` + prima registrazione (vedi 8.3.3) | — |
| 33 | 2168-2254 | `ReasoningQueue`, `_execute_decision` (fail-closed sul verdetto, `server.py:2187-2188`), `_submit_chat_reply`, cap giornaliero chat | — |
| 34 | 2256-2398 | `_holistic_reason` (coverage review + auto-tune) e `SituationEvaluator` + job ronda (8.3, n. 9) | La coverage review e' interamente avvolta: `except Exception` → `logger.exception("coverage-review failed")` (`server.py:2375-2376`); il recupero memoria dentro ha la sua guardia (`server.py:2291-2292`); la cattura del ragionamento pure (`server.py:2306-2307`) |
| 35 | 2400-2467 | Job scansione salute, potatura log ragionamento, spazzata coda (8.3, n. 10-12) | — |
| 36 | 2469-2499 | Derivazione `_bridge_enabled` / `chat_via_subscription` (fail-safe `_chat_subscription_active`, `server.py:109-117`) | — |
| 37 | 2501-2519 | `ArrivalWatcher` + listener di stato | — |
| 38 | 2521-2644 | Costruzione dei runner LLM (Claude, OpenAI, Ollama, OpenRouter) e `LLMRouter` | Sonda di raggiungibilita' Ollama avvolta: `except Exception` → warning "le richieste al modello locale falliranno", boot prosegue (`server.py:2558-2583`). Se **nessun** runner e' costruibile, `app["llm_router"] = None` e si prosegue lo stesso (`server.py:2642-2644`) |
| 39 | 2646-2669 | Server MCP interno su 127.0.0.1 | `_run_internal_mcp` (`server.py:1070-1087`) contiene `SystemExit` — uvicorn chiama `sys.exit()` se non riesce a bindare, e senza questa cattura l'intero processo cadrebbe (`server.py:1071-1081`). `await _mcp_client.start()` a riga 2654 **non** e' avvolto |
| 40 | 2671-2694 | Worker chat-via-abbonamento, se `should_start_agent_worker()` (`server.py:1136-1144`) | Flag/token assenti → `logger.info` e worker non avviato (`server.py:2693-2694`) |

### 8.2.2 Cosa succede se `_on_startup` solleva

Non c'e' rete di sicurezza nel codice HIRIS: la funzione e' registrata nuda in
`app.on_startup.append(_on_startup)` (`server.py:2785`) e non ha `try/except` di livello superiore.
Un'eccezione in uno dei passi non avvolti (7, 8, 11, 12, 14, 18, 20, 23, 24, 39) interrompe l'avvio.

Da tenere d'occhio in quel caso: `_on_cleanup` accede a `app["engine"]` e `app["ha_client"]` con
**parentesi quadre dirette**, non `.get` (`server.py:2749-2750`), a differenza di tutte le righe sopra
di esse che usano `if "..." in app` o `.get`. Su un'app popolata solo a meta' quelle due righe
sollevano `KeyError` — l'errore di spegnimento maschererebbe l'errore d'avvio.

---

## 8.3 I job periodici

Gli scheduler in gioco sono **due** oggetti `AsyncIOScheduler` distinti:

- `engine._scheduler` — creato in `ChatbotEngine` e avviato da `chatbot_engine.py:128-129`. E' lo
  scheduler condiviso: ci finiscono i 12 job di `_on_startup`, i job per-Agentbot, il polling del
  monitor di salute e il ciclo di vita delle proposte.
- `task_engine._scheduler` — creato a `task_engine.py:100`, avviato a `task_engine.py:109`. Serve solo
  ai Task.

### 8.3.1 I 12 job registrati direttamente in `_on_startup`

| # | Id | Trigger | Registrazione | Callback |
|---|----|---------|---------------|----------|
| 1 | `hiris_entity_cache_reload` | interval 2 min, grazia 120 s | `server.py:1502-1507` | `_ricarica_inventario` (`server.py:1499-1500`) |
| 2 | `hiris_retention` | cron 03:00, grazia 3600 s | `server.py:1522-1530` | `_run_retention` (`server.py:1512-1520`) |
| 3 | `hiris_history_compact` | cron 03:30, grazia 3600 s | `server.py:1541-1545` | `_run_history_compact` (`server.py:1532-1539`) |
| 4 | `hiris_history_digest` | cron 04:00, grazia 3600 s | `server.py:1556-1560` | `_run_history_digest_job` (`server.py:1547-1554`) |
| 5 | `hiris_mayan_ingest` | interval `MAYAN_POLL_MINUTES` (min 5, default 60), grazia 300 s | `server.py:1598-1605` | `_run_mayan_ingest` (`server.py:1581-1596`) |
| 6 | `hiris_daily_briefing` | cron 08:00, grazia 3600 s | `server.py:1800-1804` | `_daily_briefing` (`server.py:1780-1783`) |
| 7 | `hiris_urgent_nudges` | interval 6 h, grazia 3600 s | `server.py:1810-1814` | `_urgent_nudges` (`server.py:1792-1798`) |
| 8 | `hiris_sentinel_reset` | cron 00:01, grazia 3600 s | `server.py:1947-1949` | `_reset_sentinel_counter` (`server.py:1944-1945`) |
| 9 | `hiris_sentinel_ronda` | interval `SENTINEL_RONDA_MINUTES` (default 15), grazia 300 s | `server.py:2395-2398` | `situation_evaluator.run_evaluation` |
| 10 | `hiris_health_scan` | interval `HIRIS_HEALTH_SCAN_MINUTES` (default 30), grazia 300 s | `server.py:2424-2427` | `_run_health_scan` (`server.py:2405-2422`) |
| 11 | `hiris_reasoning_prune` | cron 03:15, grazia 3600 s | `server.py:2435-2437` | `_run_reasoning_prune` (`server.py:2429-2433`) |
| 12 | `hiris_reasoning_sweep` | interval 2 min, grazia 120 s | `server.py:2465-2467` | `_reasoning_sweep` (`server.py:2443-2463`) |

Tutti e 12 con `replace_existing=True`.

**Dettaglio di ciascuno.**

1. **`hiris_entity_cache_reload`** — richiama `ricarica_inventario_entita` (`server.py:1026-1066`).
   Non fa nulla se la cache e' gia' viva (`server.py:1049-1050`); altrimenti ritenta `cache.load` e poi
   `load_area_registry`. Il perche' dei due minuti e del costo accettato e' scritto in
   `server.py:1487-1498`. **Se solleva**: non puo' — entrambe le chiamate sono avvolte
   (`server.py:1051-1055`, `1063-1066`) e la docstring dichiara "non solleva mai"
   (`server.py:1043-1045`).
2. **`hiris_retention`** — cancella i messaggi di chat piu' vecchi di `HISTORY_RETENTION_DAYS` (0 =
   illimitato, `chat_store.py:68`) e purga le memorie chatbot scadute
   (`knowledge_store.purge_expired_chatbot`, `knowledge_store.py:438`). **Se solleva**: `_run_retention`
   (`server.py:1512-1520`) **non ha alcun try/except**. L'eccezione finisce nel gestore d'errore di
   APScheduler; il job resta schedulato e riprova domani, ma la potatura di quella notte salta e la
   traccia e' solo nel log di `apscheduler.executors`.
3. **`hiris_history_compact`** — compatta lo storico secondo la policy su disco
   (`history/store.py:176`). **Se solleva**: la `compact` e' avvolta (`server.py:1536-1539`), ma
   `_load_history_policy(data_dir)` alla riga 1534 e' **fuori** dal `try` — una policy illeggibile
   sfugge alla guardia.
4. **`hiris_history_digest`** — `run_history_digest` su storico + knowledge + embedder
   (`server.py:1552`). **Se solleva**: `try/except Exception` → `logger.error` (`server.py:1553-1554`).
5. **`hiris_mayan_ingest`** — ingestione documenti da un tag Mayan EDMS
   (`server.py:1588-1592`). Esiste **solo** se `MAYAN_URL`, `MAYAN_TOKEN` e `MAYAN_TAG_ID > 0` sono
   configurati (`server.py:1570`). **Se solleva**: `try/except Exception` → `logger.error`
   (`server.py:1595-1596`). In piu' esce dalla porta di servizio se client/store/embedder mancano
   (`server.py:1585-1586`).
6. **`hiris_daily_briefing`** — un unico resoconto quotidiano al posto del vecchio spam per scadenza
   (`server.py:1759-1768`). **Se solleva**: impossibile — `run_daily_briefing` ha il corpo intero
   avvolto e lo dichiara: "this must NEVER raise into the scheduler" (`server.py:946-948`,
   `950-963`).
7. **`hiris_urgent_nudges`** — solleciti deduplicati per scadenze che diventano urgenti fra due
   briefing; e' un intervallo e non un cron proprio per questo (`server.py:1805-1809`). Il marcatore
   `ReminderSeen` e' un'unica istanza condivisa perche' il suo file sidecar non regge accessi
   concorrenti (`server.py:1769-1774`). **Se solleva**: `run_urgent_nudges`
   (`server.py:993-1023`) ha guardia esterna sulla query (`1009-1013`) e guardia per-elemento sulla
   notifica (`1016-1022`); un invio fallito **non** viene marcato come visto e si riprova al giro dopo.
8. **`hiris_sentinel_reset`** — `sentinel_store.reset_wakes(oggi)`, che e' una `DELETE FROM wake_counts
   WHERE day < ?` (`sentinel_store.py:97-100`): non azzera il contatore di oggi, cancella quelli dei
   giorni precedenti. **Se solleva**: `_reset_sentinel_counter` (`server.py:1944-1945`) **non ha
   try/except**.
9. **`hiris_sentinel_ronda`** — la ronda delle situazioni: valuta i rilevatori abilitati, e all'ora
   configurata lancia il giro olistico (`watcher/evaluator.py:31-57`). **Se solleva**: tutto il corpo
   di `run_evaluation` e' avvolto → `log.exception("situation evaluation failed")`
   (`evaluator.py:58-59`).
10. **`hiris_health_scan`** — 8 controlli in sola lettura (5 sulla casa, 3 via Supervisor) riconciliati
    nell'`AdvisoryStore`, con notifica push per le sole segnalazioni gravi nuove o riaperte, attivabile
    con `BRAIN_NOTIFY_HIGH` (`server.py:2400-2420`). **Se solleva**: `try/except Exception` →
    `logger.exception("health scan failed")` (`server.py:2421-2422`).
11. **`hiris_reasoning_prune`** — pota il log di cattura del ragionamento a max 500 righe / 30 giorni
    (`server.py:2431`). **Se solleva**: `try/except` → `logger.exception` (`server.py:2432-2433`).
12. **`hiris_reasoning_sweep`** — spazzata di fallback della coda del ponte push: esce subito se il
    ponte non e' attivo (`server.py:2444-2445`); i job non-`holistic` restano `expired` e li raccoglie
    il loro chiamante (`server.py:2448-2452`); poi pota la coda oltre i 7 giorni
    (`server.py:2463`). **Se solleva**: la guardia copre **solo** `_run_decision`
    (`server.py:2459-2462`); `reasoning_queue.sweep_expired` (riga 2447) e `reasoning_queue.prune`
    (riga 2463) sono scoperti.

### 8.3.2 I job registrati altrove sullo STESSO scheduler

13. **`health_monitor_poll`** — interval 30 min, `proxy/health_monitor.py:136-142`, registrato da
    `HealthMonitor.start()` che riceve `engine._scheduler` a `server.py:1278`. Chiama `refresh()`
    (`health_monitor.py:145`), che ha una guardia per sezione (`health_monitor.py:157-167`).
    Nessun `misfire_grace_time`.
14. **`proposal_store_lifecycle`** — interval 1 h, `proxy/proposal_store.py:50-57`, registrato dal
    costruttore stesso quando riceve `engine._scheduler` (`server.py:1286`). Applica il ciclo
    pending → archived (7 gg) → DELETE (30 gg), documentato in `proposal_store.py:40-43`.

### 8.3.3 `register_agentbot_schedules` — `server.py:569-661`

Non un job, ma il **registratore** dei job per-Agentbot. Chiamato a `server.py:2166` in avvio, ed
esposto su `app["register_agentbot_schedules"]` (`server.py:2165`) perche' i gestori CRUD lo
riinvochino dopo ogni salvataggio (`api/handlers_agentbots.py:81`), senza reimportare `server.py`.

Cosa fa, in ordine:
- Se lo scheduler non c'e', esce (`server.py:585-588`).
- Ricarica gli Agentbot dal disco e tiene solo gli abilitati con trigger di tipo `schedule`
  (`server.py:591-607`).
- Rimuove i job orfani con prefisso `hiris_agentbot_` (`server.py:496`, `612-620`): Agentbot
  cancellato, disabilitato o passato a un altro trigger. Ogni `remove_job` ha la sua guardia
  (`server.py:617-620`).
- Registra un job per Agentbot: `CronTrigger.from_crontab` se c'e' `cron` (`server.py:640-644`),
  `interval` se c'e' `interval_min` (`server.py:645-648`), altrimenti salta difensivamente
  (`server.py:649-654`). Grazia 3600 s, `replace_existing=True`.
- Il callback e' costruito da una factory per non far condividere a tutti i job l'ultimo Agentbot del
  ciclo (`server.py:625-632`).

**Se un Agentbot solleva in registrazione** (per esempio un cron valido come forma ma non come valore,
`hour=99`): `except Exception` → `logger.warning(... skipping)` e `continue`
(`server.py:655-661`) — gli altri vengono registrati comunque.

**Se un Agentbot solleva a runtime**: `_run_scheduled_agentbot` (`server.py:545-566`) e' avvolto
end-to-end → `logger.exception` (`server.py:565-566`), esplicitamente perche' un Agentbot rotto non
possa abbattere lo scheduler condiviso o i job fratelli (`server.py:548-550`). Chiama
`run_agentbot(..., cooldown_sec=0)`: la cadenza propria del job **e'** il suo limitatore, quindi il
cooldown Sentinella da ~30 min viene scavalcato (`server.py:558-564`).

### 8.3.4 Sull'altro scheduler

15. **`task_engine_cleanup`** — interval 1 h, `task_engine.py:112-114`, sullo scheduler proprio del
    TaskEngine. Rimuove i task terminali oltre la finestra (`task_engine.py:269-274`).
16. **Job per-Task**, id `task_<id>` — registrati da `_schedule_task` (`task_engine.py:278-318`): trigger
    `date` per `delay`/`at_time`/`at_datetime`, `interval` per `time_window`, e per `immediate` nessun
    job ma un `asyncio.create_task` con riferimento forte (`task_engine.py:309-314`). **Se la
    registrazione solleva**: `except Exception` → `logger.error("Failed to schedule task ...")`
    (`task_engine.py:317-318`).

### 8.3.5 Conteggio

12 job fissi in `_on_startup` (di cui 1, Mayan, condizionato dalla configurazione) + 2 registrati
altrove sullo stesso scheduler + 1 sullo scheduler del TaskEngine = **15 job periodici sempre o quasi
sempre presenti**, piu' N job per-Agentbot e N job per-Task, entrambi dinamici.

---

## 8.4 Lo spegnimento — `_on_cleanup`, `server.py:2697-2753`

Ordine esatto, e il perche' dove il codice lo dichiara:

1. **`agent_worker_task`** (`server.py:2710-2714`) — cancellato **per primo**, prima del produttore MCP,
   e con attesa **limitata a 5 s** via `asyncio.wait_for`. Il motivo e' scritto per esteso in
   `server.py:2699-2709`: un job gia' preso in carico puo' essere dentro un `run_in_executor` con
   `subprocess.run(timeout=300)` + `httpx` a 330 s, e cancellare il task esterno non interrompe un
   thread gia' bloccato nell'executor — un `await` non limitato bloccherebbe lo spegnimento per ~5
   minuti. `CancelledError` e `TimeoutError` sono entrambi soppressi (`server.py:2713`).
2. **`internal_mcp_task`** (`server.py:2715-2719`) — cancellato e atteso **senza** limite, sopprimendo
   `CancelledError`.
3. **`internal_mcp_client`** (`server.py:2720-2722`) — `await client.stop()`.
4. **`mayan_client`** (`server.py:2723-2724`) — `aclose()`, solo se esiste.
5. **`mqtt_publisher`** (`server.py:2725-2726`) — `stop()` cancella il task di connessione e attende
   (`mqtt_publisher.py:46-54`).
6. **Chiusura degli archivi SQLite**, uno per riga, ciascuno guardato da `if "..." in app`
   (`server.py:2727-2746`): `knowledge_db`, `knowledge_store`, `vault`, `proposal_store`,
   `history_store`, `sentinel_store`, `suggestion_store`, `reasoning_log`, `advisory_store`,
   `reasoning_queue`. Sono 10.
7. **`task_engine.stop()`** (`server.py:2747-2748`) — `scheduler.shutdown(wait=False)`
   (`task_engine.py:117-118`): non attende i job in corso.
8. **`app["engine"].stop()`** (`server.py:2749`) — anch'esso `shutdown(wait=False)`
   (`chatbot_engine.py:135-137`). **Accesso diretto con parentesi quadre**, non `.get`.
9. **`app["ha_client"].stop()`** (`server.py:2750`) — cancella il task WebSocket e chiude la sessione
   (`ha_client.py:158-162`). Anche qui accesso diretto.
10. **`supervisor_client.stop()`** (`server.py:2751-2752`) — solo se costruito.
11. **`close_all_stores()`** (`server.py:2753`) — chiude tutte le connessioni `ChatStore` del registro
    di modulo e svuota il registro (`chat_store.py:433-438`).

Cosa **non** viene chiuso esplicitamente: gli archivi non elencati al punto 6 e ogni task avviato con
`_spawn` (`server.py:96-106`) che non sia MCP o worker — non c'e' un giro finale su
`_background_tasks`.

Fragilita' gia' segnalata in 8.2.2: i punti 8 e 9 sono le uniche due righe di `_on_cleanup` che non
usano `.get` o `in app`. Se lo spegnimento viene invocato su un'app in cui `_on_startup` si e' fermato
prima del passo 8 della tabella (riga 1255-1258), sollevano `KeyError`.

Nessuno dei passi 1-11 e' avvolto individualmente: un'eccezione a un punto qualsiasi impedisce
l'esecuzione di tutti quelli successivi.

---

## 8.5 Riepilogo delle voci censite

| Sezione | Voci |
|---------|------|
| Migrazioni di schema con callable | 4 (`chat_store` v2, `knowledge_store` v2 e v3, `sentinel_store` v2) |
| Archivi che passano da `init_schema` | 12 |
| Migrazioni una-tantum fuori schema | 4 |
| Passi di `_on_startup` | 40 |
| Job periodici | 15 fissi (12 in `_on_startup` + 2 sullo scheduler condiviso + 1 sul TaskEngine) + 2 famiglie dinamiche (per-Agentbot, per-Task) |
| Registratori di job | 1 (`register_agentbot_schedules`) |
| Passi di spegnimento | 11 |

**Totale voci censite: 89.**

---

# 9. Dove il sistema dice una cosa e ne fa un'altra

Il registro raccolto durante l'analisi contiene **201 voci**; questa sezione ne presenta
**181**, numerate da 1 a 181 senza salti e senza ripetizioni. Qui non sono elencate nell'ordine in
cui sono state trovate, ma raggruppate per **tipo di danno** e ordinate dal danno maggiore al
minore: prima cio' che riguarda la sicurezza e le azioni che l'utente crede protette, poi la
perdita di dati, poi i casi in cui il sistema dichiara riuscito cio' che non e' avvenuto, poi la
configurazione senza effetto, poi le superfici che mostrano il falso, poi il contratto verso il
modello, infine la documentazione interna che descrive un prodotto diverso da quello che c'e'.

Dove due voci del registro sono lo stesso difetto visto da punti diversi, sono state unite e
l'unione e' dichiarata nel punto in cui avviene. Due voci del registro non hanno trovato posto
qui e sono elencate nella nota di riconciliazione in fondo alla sezione.

---

## 9.1 Le protezioni che non proteggono

Sono i reperti che riguardano il contenimento: cio' che l'utente crede protetto e non lo e', o cio'
che il sistema dichiara di impedire e non impedisce. Vanno letti per primi.

**1. La conferma umana della chat non e' attivabile da nessuna interfaccia.**
`handlers_gateway_policy.py:228-250` + `static/config/gateway-route.js:344-352`. Promette: lo
step-up con codice a sei cifre e' il meccanismo di conferma umana del progetto, quello che protegge
le azioni gialle e rosse chieste in chat e dalle task. Fa: pretende una voce esplicita in
`settings.notify_users[user]`, e nessuna interfaccia scrive quella mappa — la pagina Accessi
Gateway invia solo `notify_service`. Senza una modifica a mano di `/data/gateway_policy.json` lo
step-up fallisce chiuso **sempre**, e il modello restituisce solo «Azione a rischio: richiede
conferma.» senza alcun modo per l'utente di confermare. *Unita con* la voce gemella
`server.py:435-448` vs `handlers_execute.py:246-247`: la stessa meta' di codice che giudica il
canale globale inadatto anche solo a portare un codice segreto — «may be a family group or a shared
dashboard» — lo usa poi per recapitare l'approvazione **con un tocco** delle richieste gialle del
gateway (`handlers_gateway_pending.py:226-227`). Il richiedente remoto e automatico ottiene
l'approvazione facile; l'utente umano e locale viene degradato a un messaggio d'errore.

**2. L'approvazione salta l'intero varco di sicurezza, denylist compresa.**
`handlers_gateway_pending.py:334-343`. Promette: «Scope the whitelist to the approved action's own
domain/entity so approval can only run THIS command, nothing wider». Fa: `allowed_entities` e'
passato a `None` (riga 346) e `allowed_services` e' l'intero dominio (`{domain}.*`); e con
`tier_confirmed=True` il dispatcher salta l'intero blocco `427-441` — guardia sui bersagli
collettivi, `gate_action` e denylist dei domini pericolosi compresi. Il contenimento reale viene
dagli argomenti congelati, non dalla whitelist dichiarata.

**3. Chi ha il token del gateway puo' riscrivere il semaforo, che e' esattamente cio' che la
guardia delle approvazioni dichiara di impedire.** `handlers_gateway_pending.py:292-311`. Promette:
«if the same token were enough to APPROVE them too, a compromised/malicious gateway could create a
red-tier pending and immediately self-approve it». Fa: la guardia esiste solo su `approve` e
`reject`. `POST /api/gateway/policy` (`server.py:2845`, `handlers_gateway_policy.py:356`) e'
raggiungibile con il solo token interno — il middleware lo accetta e il controllo CSRF esenta
esplicitamente chi presenta il token (`middleware_csrf.py:46-47`). Basta marcare tutto verde per
ottenere lo stesso risultato senza creare alcun pending.

**4. L'etichetta «ingress», su cui poggia l'intero modello di conferma umana, e' un'intestazione
piu' un indirizzo IP nella rete Docker di tutti gli add-on.**
`middleware_internal_auth.py:30-63` + `handlers_gateway_pending.py:293-294`. Promette: `auth_via ==
'ingress'` significa «un umano nella UI di HIRIS». Fa: il controllo e' `X-Ingress-Path` di forma
corretta piu' IP sorgente dentro `172.30.32.0/23`, che e' la rete in cui vivono tutti gli add-on;
un add-on co-residente puo' costruire quell'intestazione a mano e ottenere accesso all'intera
superficie `/api` **e** la facolta' di approvare i pending gialli e rossi che il token
esplicitamente non ha. La raggiungibilita' della porta fra container non e' stata provata sul campo
(cfr. sezione 11).

**5. La whitelist degli strumenti di un Chatbot non e' un controllo, e' un suggerimento.**
`claude_runner.py:808-820` e `backends/openai_compat_runner.py:711-722`. Promette: la UI presenta
gli strumenti come caselle da spuntare, cioe' come una concessione esplicita
(`static/config/templates.js:61-98`). Fa: `allowed_tools` agisce solo su cio' che viene
**dichiarato** al modello (`claude_runner.py:712`); al dispatch il nome dello strumento e' passato
cosi' com'e', senza verificare che appartenga alla lista. Un modello che nomina uno strumento non
concesso lo esegue comunque. `tool_name_set` esiste (`openai_compat_runner.py:558`) ma serve solo a
rilevare tool-call trapelate nel testo. *Da leggere insieme al confronto in 5.6*: sul gateway lo
stesso controllo esiste davvero (`handlers_execute.py:155-176`); in chat no.

**6. Una selezione vuota di strumenti significa «tutti», e il Chatbot principale viene riazzerato a
ogni avvio.** `handlers_chat.py:230-232` + `chatbot_engine.py:230-247`. Promette: il dispatcher
documenta a lungo (`dispatcher.py:51-65`) che una lista vuota e' «una decisione, non un'omissione»,
cioe' `[]` = nega tutto. Fa: per gli strumenti la semantica e' rovesciata — `allowed_tools or None`
trasforma `[]` in `None`, che significa «nessun vincolo», cioe' il catalogo intero. E
`_seed_default_chatbot` (`chatbot_engine.py:245-247`) riazzera a `[]` la lista del Chatbot
predefinito a **ogni avvio**: la persona principale ha sempre tutti e 37 gli strumenti e qualunque
restrizione salvata su di essa viene cancellata. Lo stesso vale per `allowed_entities` e
`allowed_services`, che in chat non ricevono mai `[]`.

**7. Gli agenti non conversazionali ricevono l'intero insieme di strumenti di valutazione, non
nessuno.** `static/config/agentbot-editor.js:20-21` e `:434`; `create-wizard.js:25-28` e
`:488-495`. Promette: «Il ragionamento non ha mai accesso a tool: produce solo un verdetto
testuale». Fa: `claude_runner.py:966-968` fa `if allowed_tools: ...`, e una lista vuota e' falsa in
senso logico: il restringimento non scatta e il modello riceve l'intero `EVALUATION_ONLY_TOOLS`
(`claude_runner.py:225-253`) — `get_entity_states`, `get_history`, `get_logbook`, `recall_memory`,
`create_task`, `list_tasks`, `cancel_task`. Il contrario e' scritto esplicitamente nei commenti di
`server.py:1712-1717` e `agentbot_runner.py:27-36`: due file dello stesso repository dicono
l'opposto, e quello che l'utente legge e' quello sbagliato. *Unita con* il reperto gemello sul
Brain (`server.py:2258-2262`): il commento dichiara che la revisione olistica «non instrada nessuna
azione sulla casa», ma passa dalla stessa chiamata con `allowed_tools=[]` e riceve quindi anche
`create_task`; un task creato durante la revisione puo' poi attuare la casa. *E con*
`claude_runner.py:221-224`, la cui docstring dichiara che l'insieme «esclude gli strumenti di
esecuzione diretta per impedire che un'iniezione dallo stato di HA scateni azioni reali»: l'insieme
include `create_task`, che accetta azioni `call_ha_service` e `send_notification`
(`dispatcher.py:14`). L'invariante «nessuna azione reale» non vale alla lettera.

**8. Tre scritture verso Home Assistant non passano dal semaforo.** `dispatcher.py:186-188`
promette: «Semaforo universale — gate condiviso da OGNI superficie che attua su HA». Fa: l'elenco
fra parentesi nella docstring e' esatto, la parola «OGNI» no. Non passano da `_gate`:
`create_calendar_event` (`dispatcher.py:566-578`, chiama `calendar.create_event` senza gate, senza
`allowed_services`, senza `allowed_entities`, e non e' in `CONFIRMATION_COVERED_TOOLS`),
`create_ha_config` (`dispatcher.py:637-655`, scrive script e scene su HA direttamente),
`send_notification` (`dispatcher.py:346-350`, deliberato e documentato a
`notify_tools.py:132-137`). *Quattro voci del registro dicono questa stessa cosa da quattro
angolazioni* — `semaphore.py:4-7`, `dispatcher.py:637-655`, `dispatcher.py:566-578`,
`dispatcher.py:501-503` — e sono qui unite. Per `create_ha_config` dalla chat l'unica rete e'
un'istruzione testuale nel prompt di sistema (`claude_runner.py:371-379`), che nessun controllo di
codice fa rispettare; dal gateway lo stesso strumento diventa invece una proposta
(`handlers_execute.py:295-311`). Stesso nome, due comportamenti opposti.

**9. L'opzione «richiedi conferma» del Chatbot e' solo testo nel prompt.**
`claude_runner.py:371-379` + sezione «autonomia» di `chatbot-editor.js`. Promette: un interruttore
di sicurezza per Chatbot. Fa: aggiunge un blocco di testo al prompt di sistema
(`claude_runner.py:697-698`, `openai_compat_runner.py:532` e `821`). Nessun controllo di codice la
fa rispettare; il controllo vero e' il semaforo, che pero' non copre `create_ha_config`.

**10. La denylist di lettura e' esente per trasporto, non per Chatbot.**
`read_denylist.py:75-84` + `server.py:2652-2653` + `mcp/local_client.py:40-41`. Promette:
l'esenzione e' motivata come riservata alla «chat in-addon», dove «vale invece il perimetro del
Chatbot». Fa: il marcatore `X-HIRIS-Local-Chat` e' impostato su **ogni** chiamata di
`LocalExecuteClient`, che serve l'intero server MCP interno — descritto a `server.py:2646-2649`
come destinato anche a «un client LLM MCP-aware (es. Claude Desktop/Code via bridge locale)».
Qualunque client MCP che raggiunga quel loopback legge serrature, telecamere e localizzatori senza
denylist e, per le letture, con `allowed_entities=None` (`handlers_execute.py:347`).

**11. La denylist di lettura non esiste fuori dal gateway.** `read_denylist.py:1-13` promette: «un
elenco di entita' o domini che non escono MAI dal gateway». Fa: vale solo dentro `handle_execute`.
La chat in-add-on che usa direttamente il dispatcher non attraversa mai quel modulo: un Chatbot
senza perimetro legge senza filtri serrature, telecamere e `device_tracker`.

**12. Le letture dal gateway non riapplicano le whitelist.** `handlers_execute.py:1-7` promette:
«re-applies the per-tool entity/service whitelists before dispatching». Fa: per i `READ_TOOLS` la
chiamata passa `allowed_entities=None` e `allowed_services=None` (righe 344-354), come lo stesso
file spiega alle righe 313-317. Le letture vedono tutta la casa e sono contenute solo dalla
denylist.

**13. Un comando senza entita' bersaglio diventa un comando a raggio di dominio, e la conferma
umana non lo mostra.** `task_tools.py:20-21` vs `task_engine.py:463-505` promette: «call_ha_service
requires an explicit entity_id target and a green semaforo level». Fa: allo scatto un'azione senza
alcun `entity_id` non viene rifiutata — `gate_action` ricade sul tier del **dominio**
(`semaphore.py:150-151`) e, se il dominio e' verde, la chiamata parte senza filtro di entita', cioe'
su tutto il dominio; il ciclo del perimetro entita' (`:470-476`) non gira su una lista vuota. Il
percorso vivo del dispatcher ha invece un rifiuto esplicito per questo caso
(`dispatcher.py:449-451`); il motore dei task no. *Da leggere insieme al* reperto del gateway
(`handlers_execute.py:199-201`, registrato fra gli inerti e verificato **vivo**): senza entita'
bersaglio si usa il tier del dominio e si crea un pending giallo o rosso su una chiamata di
dominio; all'approvazione il comando arriva a Home Assistant come broadcast di dominio senza
filtro. *E con* il fatto che la notifica di approvazione del gateway e' composta con dominio e
servizio soltanto (`handlers_execute.py:238-245`): **l'entita' non compare**, per l'unica notifica
del prodotto che si approva con un tocco. Il commento del percorso di chat spiega esattamente
perche' il messaggio push *deve* mostrare l'entita'; il percorso del gateway costruisce il messaggio
altrove e ignora quel principio.

**14. Il tocco sulla notifica non e' legato a nessuna identita'.**
`handlers_gateway_pending.py:190-203` e `:278-288`. Promette: due porte sulla stessa richiesta. Fa:
i pulsanti sono azionabili senza che il codice richieda autenticazione, e il gestore non verifica
quale utente o quale dispositivo abbia generato l'evento: l'unica prova e' la conoscenza
dell'identificativo. La via del codice a sei cifre e' invece vincolata all'identita'. Due contratti
d'identita' diversi sulla stessa azione.

**15. La coda dei pending espone al gateway gli argomenti congelati di tutti, compresi quelli nati
in chat da un altro utente.** `handlers_gateway_pending.py:88-97`. Promette: la docstring di
`list_pending` si preoccupa esplicitamente del fatto che l'endpoint sia raggiungibile con lo stesso
token del gateway, e per questo toglie `otp` e `otp_attempts`. Fa: toglie solo quelli. Il gateway
riceve comunque il nonce, il tier, la label, l'identita' `user` e gli `inputs` congelati di **tutti**
i pending; `handle_list_pending` (`:314-315`) non chiama `_require_human_auth`.

**16. Annullare un task non richiede di esserne il proprietario.** `handlers_tasks.py:36-43` +
`middleware_csrf.py:38-55`. Promette: l'annullamento e' un'azione dell'utente sui propri task. Fa:
`DELETE /api/tasks/{id}` non verifica identita' ne' proprieta'; l'unica barriera e' la presenza di
un'intestazione `X-Requested-With` qualsiasi. *Unita con* `mcp/tiers.py:110-113`, la cui descrizione
letta dal modello dice «annulla un task HIRIS pianificato»: `cancel_task_tool` non riceve ne' usa
alcun `agent_id` (`dispatcher.py:509-514`, `task_tools.py:113-117`), quindi il gateway puo'
annullare qualunque task in attesa, compresi quelli creati dall'utente dentro HIRIS. Il limite e'
dichiarato nel sorgente (`tiers.py:105-109`) ma non nella descrizione esposta al modello.

**17. Lo «Scarta» della coda di memoria cancella qualunque riga leggibile.**
`handlers_knowledge.py:94-108` e `:41-91`. Promette: la rotta e' lo «Scarta» della coda di
approvazione, la UI la mostra solo sulle card in attesa e la conferma dice «Verra' eliminato
definitivamente» (`static/chat/knowledge.js:229`). Fa: `handle_reject` non filtra su `status` e
chiama `delete_item` su qualunque id; `_owner_allowed` accetta l'id se la riga e' dell'utente **o**
ha `owner='home'` (`knowledge_store.py:228-234`). Un POST diretto cancella quindi anche documenti
importati, insight, tracce del Brain e memorie di altri Chatbot, tutti scritti con `owner='home'`.
Simmetricamente `handle_approve` puo' «approvare» e riscrivere l'embedding di qualsiasi riga.

**18. Il pseudonimizzatore verso il cloud copre un solo strumento.** `claude_runner.py:522`
(`_is_cloud = True # Anthropic cloud — always pseudonymize sensitive content`). Promette: il
contenuto sensibile viene sempre pseudonimizzato verso il cloud. Fa: il flag `cloud` e' usato in due
punti soli del dispatcher — `recall_knowledge` (`dispatcher.py:705`) e la soglia `allow_sensitive`
del resoconto quotidiano (`dispatcher.py:739`). Il messaggio dell'utente, lo storico, il blocco
«Contesto casa» e il blocco delle memorie richiamate (`handlers_chat.py:294-303`) partono verso il
cloud senza alcuna pseudonimizzazione. *Unita con* `dispatcher.py:721-724`, che dichiara che
`allow_sensitive` di `daily_briefing` «rispecchia il modello di recall_knowledge: configurazione
dell'agente AND localita' del backend, fail-closed»: `recall_knowledge` non fa quella congiunzione
(riga 702), il briefing si' (riga 739). Le due superfici dello stesso interruttore si comportano in
modo opposto verso un backend cloud — il briefing nasconde, `recall_knowledge` manda.

**19. «Nessun accesso al second brain» non impedisce ai documenti di uscire, ne' alle memorie di
entrare nel prompt.** `knowledge_tools.py:156-169` promette: `kinds=[]` e' documentato come
«nessun accesso al second brain» (`chatbot-editor.js:30-32`, `knowledge_store.py:279-284`). Fa:
`handle_recall_knowledge` passa `kinds` a `store.search` ma **non** a `store.search_chunks` (righe
164-169), che non ha nemmeno quel parametro (`knowledge_store.py:402-403`): con `kinds=[]` i
frammenti dei documenti importati continuano a essere restituiti e fusi nel risultato. *Unita con*
`chatbot-editor.js:337-343` vs `memory_tools.py:204` e `handlers_chat.py:283-289`: il filtro
raggiunge solo `recall_knowledge`; `recall_memory` forza `kinds=['memory']` ignorando la
configurazione, e l'iniezione automatica dei ricordi in chat interroga lo store con
`kinds=['memory']` senza leggere affatto `knowledge_access`. *E con* `handlers_chat.py:275-290`:
quella stessa iniezione chiama `search` senza `allow_sensitive`, quindi la sezione «Consenti dati
sensibili» dell'editor su quel percorso non ha effetto ne' in un verso ne' nell'altro.

**20. La marcatura «dati non affidabili» non viene mai applicata al contesto che arriva davvero al
modello.** `chatbot_engine.py:378-401` vs `proxy/semantic_context_map.py:319-322`. Promette: il
progetto marca i dati provenienti da Home Assistant con i delimitatori «[INIZIO DATI NON AFFIDABILI
— fonte: Home Assistant]» / «[FINE DATI NON AFFIDABILI]». Fa: quella marcatura sta in
`_build_entity_context`, che nessun percorso di produzione chiama. Il contesto che finisce nel
prompt di chat viene dalla SemanticContextMap, che sanifica i valori ma non li racchiude in alcun
delimitatore: nel prompt compare come «## Contesto casa».

**21. Lo scoping per utente della memoria e' inerte su tre percorsi su quattro.**
`dispatcher.py:592,600,684,701`. Promette: il commento di `knowledge_store.search` (`:246-255`)
spiega che lo scoping per proprietario esiste «per impedire a due utenti HA diversi di vedere le
memorie l'uno dell'altro». Fa: `user_id` e' passato solo dal percorso di chat interattiva
(`handlers_chat.py:377,438`). Le esecuzioni programmate di un Chatbot
(`chatbot_engine.py:521-541`), il ragionatore proattivo (`server.py:1744-1748`) e il gateway MCP
(`handlers_execute.py:344-353`) non lo passano: tutto cio' che scrivono nasce `owner='home'`, cioe'
leggibile da chiunque. *Unita con* `brain/memory_migration.py:96-107`, che promette di non perdere
righe ed e' vero, ma porta tutte le righe migrate a `owner='home'` (riga 99): memorie che nel
vecchio archivio appartenevano a un agente diventano leggibili da qualunque utente di casa.

**22. L'invio di notifiche e l'annullamento di task sfuggono al perimetro del gateway, e il
perimetro degli Agentbot non copre le notifiche.** `handlers_execute.py:36` promette un perimetro;
fa: `send_notification` e' sempre esposto, fuori da ogni policy — chiunque abbia il token puo'
notificare l'utente con il semaforo interamente spento. *Unita con* `agentbot-editor.js:93-98`
(«Il perimetro limita sia cio' che l'agente puo' toccare sia cio' che puo' vedere»): in un task
un'azione `send_notification` non e' filtrata ne' da `allowed_entities` ne' da `allowed_services`
(`task_engine.py:507-512`, ammessa da `dispatcher.py:14`); un agente con `allowed_entities=[]`
(«nega tutto») puo' comunque far arrivare notifiche. *E con* `task_engine.py:507-512` vs `:463-476`:
il perimetro si applica solo alle azioni `call_ha_service`, mentre `send_notification` e
`create_task` lo attraversano senza controlli — un task con perimetro vuoto puo' notificare su
qualunque canale e generare altri task.

**23. Il tetto di autonomia degli agenti-obiettivo non e' letto da nessuno.**
`watcher/agentbots.py:56-61` promette: «max_tier e' il tetto che un Agentbot obiettivo puo'
raggiungere senza chiedere». Fa: il campo e' validato (`:510-514`), persistito (`:531`), restituito
dall'API — e nessun runtime lo legge. La ricerca su tutto `hiris/` trova solo la validazione, i
commenti e i test. *Compare due volte nel registro* (area Agentbot e area Semaforo) ed e' lo stesso
difetto.

**24. Il confinamento degli agenti-obiettivo non e' quello dichiarato.**
`watcher/agentbot_runner.py:8-26` promette: «The executed action is ALWAYS agentbot_action(agentbot)
— the Agentbot's own deterministic config. NEVER derived from the LLM's output». Fa: e' vero per il
campo `Decision.action`, ma in modalita' obiettivo l'attuazione reale passa dai task che il modello
crea liberamente via `create_task` (`dispatcher.py:457-498`), i cui dominio, servizio, entita' e
messaggio sono interamente scelti dal modello. Il confinamento e' il perimetro piu' il semaforo
all'esecuzione, non la determinatezza della configurazione.

**25. Il kill-switch del server MCP interno e' un interruttore senza leva.** `mcp/guard.py:8-14`
promette: «Kill-switch + audit in-memory per l'MCP interno», con `set_killed` che ferma gli
strumenti. Fa: `set_killed` non e' mai chiamato da alcun punto del codice di produzione (solo dai
test), e `guard.audit` non e' letto da nessuno — nessun endpoint, nessuna pagina, nessun log.
`server.py:1114-1120` lo ammette a mezza voce; la docstring della classe presenta il meccanismo come
attivo. *La stessa cosa e' registrata tre volte fra gli inerti* (`guard.py:20-25`, `:23-25`,
`:27-28`, `server.py:2660`).

**26. Le risposte 401 e 403 escono senza intestazioni di sicurezza.** `server.py:2779-2783` vs
`2756-2775`. Promette: l'elenco dei middleware suggerisce che ogni risposta esca con CSP, nosniff,
Referrer-Policy, Permissions-Policy, COOP. Fa: `_security_headers` e' l'ultimo della lista, quindi
il piu' interno (aiohttp costruisce la catena con `reversed`): le 401 dell'autenticazione e le 403
del controllo CSRF ritornano prima di raggiungerlo. Lo stesso vale per le risposte in streaming
della chat, preparate dentro l'handler prima che il middleware giri (`handlers_chat.py:356`).

**27. Il «fail-safe numero 1 del rilascio» non regge.** `server.py:109-119` vs `2491-2499`.
Promette: `_chat_subscription_active` e' descritta come il fail-safe che impedisce alla chat via
abbonamento di attivarsi se il ponte non e' genuinamente abilitato; «un `or` qui sarebbe una
regressione silenziosa». Fa: i due argomenti passati alla funzione sono entrambi derivati con un
`or _sub_first_class`. Quando l'abbonamento e' di prima classe la congiunzione e' vera per
costruzione, indipendentemente da `BRIDGE_ENABLED`. La funzione pura resta corretta; l'invariante
che la docstring rivendica no.

**28. Dettagli interni risalgono fino al prompt del modello.** `ha_client.py:302-310` vs
`375-385`. Promette: il commento stabilisce la regola «mai fare eco di `str(exc)` al chiamante (puo'
contenere host, path o dettagli di libreria)» e la applica a `create_automation`. Fa: `_post_config`,
usato da `create_script` e `create_scene`, ritorna `{'error': f'scrittura config fallita: {exc}'}`,
e lo stesso vale per `get_automation_config` (`ha_client.py:555-556`). Quel testo risale fino alla
risposta dello strumento, cioe' dentro il prompt del modello.

**29. Un endpoint locale con IP privato non e' configurabile, nonostante la documentazione lo
inviti.** `http_tools.py:148-151` e `266-273`. Promette: «use an explicit IP in allowed_endpoints to
permit local devices» e, nella descrizione dello strumento, «or local devices explicitly configured
by the admin». Fa: `validate_endpoint_entry` (`:85-90`) chiama `_check_ip` sugli host che sono
letterali IP, e `_DENY_NETS` include 10/8, 172.16/12, 192.168/16, 127/8. Verificato eseguendo la
funzione: `{'host':'192.168.1.50'}` solleva «is in denied range 192.168.0.0/16». Nessun dispositivo
locale e' raggiungibile per questa strada. E' l'unico reperto del registro verificato eseguendo il
codice.

**30. La segnalazione di salute che parla di sicurezza descrive un rischio che non esiste.**
`brain/health_checks.py:222-224`. Promette: «Dominio pericoloso eseguibile senza conferma: {dom}».
Fa: un dominio pericoloso impostato verde non e' eseguibile affatto sui percorsi non confermati,
perche' `gate_action` ritorna `deny_dangerous` prima di leggere il tier
(`semaphore.py:141-146`). *Compare due volte nel registro* (area Brain e area Semaforo).

**31. La pagina che imposta l'autonomia di tutto il prodotto si chiama «Accessi Gateway».**
`static/config/gateway-route.js:234-236`. Promette: «Cosa Claude (via il gateway MCP) puo' comandare
in casa». Fa: gli stessi livelli salvati da quella pagina governano la chat
(`dispatcher.py:199-200`), i task differiti (`task_engine.py:479-480`), la Sentinella e gli
Agentbot (`server.py:1893-1898, 2112-2117, 2198-2203`) e la scansione di salute
(`server.py:2407-2410`).

**32. Di fabbrica il semaforo nega tutto, e le opzioni che dovrebbero configurarlo non lo toccano.**
`handlers_execute.py:76-91` + `handlers_gateway_policy.py:269-270`. Promette:
`parse_execute_policy` e' presentata come la policy dell'add-on configurabile da variabili
d'ambiente. Fa: quel dizionario non contiene affatto `tiers` ne' `entity_tiers`; se l'utente non ha
mai salvato la pagina Accessi Gateway, `apply_saved_policy` esce senza toccare nulla e
`effective_tier` ritorna `off` per ogni entita'. Le opzioni `execute_api_entities` e
`execute_api_services` non hanno alcun effetto sul semaforo.

**33. Il default protettivo della denylist di lettura e' l'unica cosa che protegge le letture, e la
sua attivazione dipende da un dettaglio di `run.sh`.** `read_denylist.py:100-110` +
`run.sh:34-36`. Promette: un valore di partenza protettivo che copre serrature, allarme,
telecamere, persone e localizzatori. Fa: la distinzione fra «chiave assente» e «stringa vuota» e'
affidata a `jq`; se la chiave esiste sempre nelle opzioni scritte dal Supervisor, il default
protettivo non viene mai raggiunto. La condizione non e' stata verificata (cfr. sezione 11).

**34. Un'identita' scelta a piacere determina a chi arriva il codice di conferma.**
`brain/identity.py:6`. `resolve_owner` legge `X-Remote-User-Id` senza alcuna validazione, e per un
chiamante autenticato con il solo token interno non c'e' nulla nel codice che impedisca di
sceglierlo; l'unica occorrenza di quell'intestazione in tutto il repository e' la lettura. Non e'
stato verificato se il Supervisor la sovrascriva a monte (cfr. sezione 11): il reperto e' registrato
qui perche', se non lo facesse, determinerebbe a quale telefono arriva il codice a sei cifre.

---

## 9.2 Dati distrutti o persi senza avviso

**35. «Nuova conv.» cancella la memoria delle conversazioni passate.** `static/chat/agents.js:35`
vs `chat_store.py:295-305`. Promette: un bottone chiamato «Nuova conv.» con la conferma «Cancellare
la cronologia di questa conversazione?». Fa: `clear()` cancella **tutte** le sessioni di quel
Chatbot e tutti i loro riassunti, cioe' anche la memoria a lungo termine che
`handlers_chat.py:244-251` reinietta come «Sessioni precedenti». Non e' «questa conversazione» ed e'
molto piu' di «iniziarne una nuova».

**36. Eliminare un Chatbot distrugge i ricordi di tutti gli utenti di casa.**
`memory_tools.py:70-73` promette: «I ricordi restano disponibili nelle conversazioni successive fino
alla loro scadenza». Fa: restano disponibili solo con lo **stesso** Chatbot e lo **stesso**
proprietario (`knowledge_store.py:256-259`); cambiando Chatbot, o entrando come un altro utente di
Home Assistant, il ricordo e' invisibile; cancellando il Chatbot viene distrutto
(`handlers_chatbots.py:213`), compresi i ricordi salvati da altri utenti attraverso di esso. La
conferma a schermo dice soltanto «Eliminare questo Chatbot?»
(`static/config/chatbot-editor.js:774`), mentre il server cancella anche l'intera cronologia di chat
(`handlers_chatbots.py:208-222`). Se la cancellazione fallisce, l'API risponde comunque «eliminato».

**37. Approvare un'automazione puo' sovrascriverne una esistente, senza avviso e senza ritorno.**
`handlers_proposals.py:46-59` vs `ha_client.py:225-233, 289-291`. Promette: la UI presenta
l'attivazione come additiva («Attiva» / «Attivare questa proposta?»), e l'avviso di sostituzione
compare solo per le plance in modalita' sostituzione. Fa: quando la proposta non porta un
identificativo ma porta un nome che coincide in modo univoco con il nome amichevole di
un'automazione esistente, **quella automazione viene sovrascritta**. Nessuna delle tre viste
avvisa, non esiste anteprima della configurazione proposta e — a differenza delle plance — non
esiste alcuno snapshot da cui tornare indietro. Il comportamento e' documentato nella descrizione
dello strumento, cioe' detto al modello (`proposal_tools.py:53-59`), mai all'utente che approva.

**38. Le proposte in attesa invecchiano e scompaiono in silenzio.** `proposal_store.py:165-185` +
`static/config/proposals-route.js:9-10`. Promette: le due schede sono «In attesa» e «Archivio»,
come se l'archivio fosse una destinazione consultabile. Fa: una proposta non gestita viene
archiviata dopo sette giorni **senza alcun avviso**, perde i pulsanti
(`config/proposals.js:51-54`) e non e' piu' attivabile (409); dopo trenta giorni viene cancellata
dal database. Le proposte attivate e rifiutate non sono consultabili da nessuna scheda, pur essendo
conservate per sempre.

**39. Un errore di rete verso il Supervisor si presenta all'utente come problemi rientrati.**
`brain/health_scan.py:253-295` + `brain/advisory_store.py:155-165`. Promette: la scansione e'
dichiarata «di sola lettura», con ogni sorgente isolata in modo che un fallimento non rompa il giro.
Fa: un fallimento di lettura produce una lista vuota, e la riconciliazione interpreta l'assenza di
candidati come «problema rientrato»: chiude come risolte **tutte** le segnalazioni attive di quel
controllo.

**40. Un solo record corrotto fa sparire tutti i task che lo seguono.** `task_engine.py:208-242`.
Promette: i task in attesa sopravvivono al riavvio. Fa: il blocco protetto avvolge l'intero ciclo di
lettura; un solo record malformato interrompe il caricamento e tutti i task successivi nel file
spariscono, con un unico messaggio d'errore nei log e nessun avviso all'utente.

**41. Un task interrotto a meta' viene rieseguito da capo.** `task_engine.py:370-371` vs `:434`.
Promette: lo stato del task e' quello che si legge su disco. Fa: il passaggio a «in esecuzione» non
viene salvato; se il processo muore a meta', alla ripartenza il task viene rischedulato come se non
fosse mai partito e le azioni gia' eseguite verrebbero rifatte. *Unita con* `task_engine.py:234-238`:
un task `immediate` non eseguito viene marcato «saltato» al riavvio ma il cambio di stato non e'
seguito da un salvataggio, quindi sul file resta «in attesa».

**42. Una regola non piu' valida sparisce dall'elenco e il primo salvataggio la cancella.**
`watcher/agentbots.py:784-794`. Promette: il commento dice «Don't let a stored-but-now-invalid
Agentbot vanish silently». Fa: emette un avviso nei log e la scarta comunque; il primo salvataggio
successivo persiste la cancellazione. Verso l'utente la sparizione e' silenziosa: nessun campo nella
risposta dell'API, nessuna riga in timeline, nessuna indicazione a schermo. Un `PUT` su
quell'identificativo risponde 404 pur essendo la riga presente nel file.

**43. Salvare un Agentbot dall'editor cancella il messaggio di un'azione di servizio.**
Registrato fra gli inerti (`watcher/agentbots.py:355-357`) ma e' una perdita di dato:
`agentbot-editor.js:658` azzera il messaggio quando l'azione e' di tipo servizio e `buildPayload`
(`:782-790`) costruisce l'azione senza quella chiave, mentre `agentbot_message`
(`agentbot_runner.py:188-191`) lo leggerebbe. Ogni salvataggio dalla UI cancella silenziosamente un
messaggio presente su un'azione di servizio, per esempio creata da una proposta del modello.

**44. Un errore in chat cancella anche la domanda.** `handlers_chat.py:464-468`. Promette: il
commento dice che si salta la persistenza «cosi' il turno successivo non eredita uno storico
degradato. L'utente conserva l'errore visibile nella risposta corrente». Fa: il turno dell'utente e
quello dell'assistente sono salvati insieme, quindi scartare la risposta scarta anche la domanda:
dopo un errore la cronologia non conserva traccia del fatto che l'utente abbia chiesto qualcosa, e
il limite di turni non avanza.

**45. Una risposta giudicata non mostrabile viene comunque mostrata.** `handlers_chat.py:135-137`
vs `server.py:2241-2247`. Promette: il commento dice che una risposta tossica viene scartata perche'
«il turno successivo non deve ereditare uno storico avvelenato». Fa: viene scartata dallo storico ma
il polling la legge direttamente dalla riga di coda e la restituisce all'utente come conclusa.
L'utente vede un testo che il sistema ha classificato come non mostrabile e che non esiste nella sua
cronologia.

**46. La copia locale della card diverge dal server e nessuno le riconcilia.**
`hiris-chat-card.js:1170-1171` e `1222` promette: «pulisci conversazione» con la conferma
«Cancellare la cronologia di questa conversazione?». Fa: cancella solo la chiave del browser
(`:963-967`, `77-79`); la cronologia lato server resta e continua a essere iniettata come contesto
al turno successivo (`handlers_chat.py:222`), mentre la stessa azione nella pagina chat cancella
davvero sul server. *Unita con* `hiris-chat-card.js:56-63` e `697-699`, che promettono «chat
persistence» con idratazione della conversazione: la card non chiama mai
`GET api/chatbots/<id>/chat-history`, che pure esiste (`server.py:2815`,
`handlers_chat_history.py:15-23`). Su un browser nuovo la card mostra una conversazione vuota mentre
il modello riceve tutta la storia; cancellando i dati del sito la card «dimentica» senza che il
modello dimentichi.

**47. Rigenerare una risposta duplica la storia e consuma il limite di turni.**
`hiris-chat-card.js:950-961`. Promette: «rigenera» rifa' la stessa risposta. Fa: il server lo tratta
come un turno nuovo — `append_messages` aggiunge un'altra coppia alla cronologia
(`handlers_chat.py:411-415, 464-468`) e il conteggio dei turni cresce. Le bolle successive vengono
eliminate solo dalla copia locale.

**48. Un turno che scade dal punto di vista della pagina puo' risolversi dopo, e riappare.**
`static/chat/send.js:60` vs `handlers_reasoning.py:34-53`. Promette: «La risposta non e' arrivata in
tempo. Riprova.» dopo cinque minuti di attesa. Fa: il lavoro puo' ancora essere risolto dopo quel
momento e il consumatore scrive la risposta nell'archivio di chat: al caricamento successivo la
risposta «mai arrivata» compare, e un eventuale «riprova» dell'utente produce un secondo turno.

**49. Un ricordo che non si puo' vettorizzare viene comunque scritto, in un punto solo.**
`brain/history_digest.py:129-141`. Promette: tutto il resto dell'area rifiuta apertamente di
scrivere righe senza vettore, perche' «approvato» non e' «richiamabile»
(`memory_tools.py:114-120`, `knowledge_tools.py:87-96`, `handlers_knowledge.py:42-52`,
`brain_trace.py:5-10`). Fa: il digest storico scrive l'insight con embedding nullo quando il motore
manca o solleva — il fallimento e' un semplice messaggio di debug — e con stato «approvato». La riga
esiste, e' approvata, e la ricerca non la restituira' mai perche' filtra sull'embedding non nullo.

**50. Le azioni autonome del Brain non lasciano traccia con la configurazione di fabbrica.**
`brain/brain_trace.py:1-12` e `28-59` + `config.yaml:69` + `backends/embeddings.py:21-29, 205`.
Promette: «Every action the brain takes on its own must leave a trace ... recallable via
KnowledgeStore.search». Fa: con provider di embedding vuoto il motore fittizio restituisce un
vettore vuoto, `record_brain_action` registra un avviso e non scrive nulla; la taratura e la
copertura vengono comunque applicate. L'azione autonoma avviene senza traccia, e la chat non potra'
mai spiegare cosa ha fatto il Brain.

**51. Una taratura applicata ma non registrata non e' piu' annullabile.**
`brain/cognitive_loop.py:224-228` (descritto in sezione 2). E' la stessa radice del reperto
precedente vista dal lato dell'utente: il pulsante «Annulla» esiste solo per le righe registrate.

---

## 9.3 Il sistema dichiara riuscito cio' che non e' avvenuto

E' la famiglia piu' numerosa e la piu' insidiosa, perche' non produce un errore: produce una
conferma.

**52. La Sentinella dice «(fatto)» senza guardare l'esito.** `watcher/executor.py:23-26` +
`server.py:1821-1866` + `tools/dispatcher.py:436-456`. Promette: nel ramo verde con automatismo
l'esecutore notifica «<messaggio> (fatto)» e registra esito «act». Fa: `_act` ignora completamente
il valore di ritorno di `dispatch()`; il dispatcher puo' restituire un errore (semaforo, whitelist,
bersaglio collettivo) e `ha_client.call_service` puo' restituire falso senza sollevare: in tutti
questi casi la notifica dice comunque «(fatto)» e la timeline registra un'azione eseguita.

**53. Un task risulta «Eseguito» anche quando nulla e' partito.** `task_engine.py:411-414` vs
`:489-497`. Promette: il risultato del task deve dire la verita', e un'azione saltata viene
registrata come «skipped» (comportamento fissato da `tests/test_task_engine.py:623`). Fa:
un'azione fermata in attesa di conferma umana ritorna la stringa `pending: confirmation (...)`, che
non comincia per `skipped`: il ramo alternativo registra `call_ha_service:OK` e il task chiude
«eseguito». *Unita con* `task_engine.py:411-414` + `ha_client.py:186-196`: `call_service` ritorna
falso senza sollevare quando Home Assistant risponde con uno stato diverso da 200, e
`send_notification` ritorna falso su canale sconosciuto, messaggio vuoto o Apprise non configurato;
in entrambi i casi il valore finisce nello stesso ramo e viene registrato `:OK`. *E con*
`task_engine.py:422`: un task tutte le cui azioni sono state bloccate dal semaforo o dal perimetro
chiude comunque «eseguito»; non esiste uno stato «eseguito parzialmente» ne' «tutto bloccato».

**54. Il flag che dice se la notifica e' partita afferma il contrario del fatto, e nessuno lo
legge.** `handlers_gateway_pending.py:216-221` vs `249-254`. Promette: «Returns True iff
ha.call_service actually completed, False on any failure ... Callers that need to know whether the
push really reached HA (e.g. the chat step-up flow's otp_sent flag) can rely on this». Fa: ignora il
valore di ritorno e restituisce vero, mentre `call_service` ritorna falso senza sollevare quando HA
risponde non-200 o quando il nome del servizio non passa la validazione (`ha_client.py:187-196`).
*Unita con* `server.py:465-467` (due voci del registro, aree Integrazione e Semaforo): `otp_sent`
non ha alcun consumatore — `dispatcher.py:213` guarda solo `id`, `task_engine.py:494-497` guarda
solo la verita' del dizionario. Se la notifica non e' partita, il modello dice comunque all'utente
«tocca Conferma nella notifica sul telefono, oppure dimmi il codice che ti ho inviato».

**55. «Notifica inviata» anche quando non e' partita nulla.** `handlers_execute.py:246-252` con
`handlers_gateway_pending.py:206-254`. Promette: la risposta al modello dichiara «Azione in attesa
di approvazione — notifica inviata.». Fa: il chiamante ignora il valore di ritorno di `notify()`; il
messaggio lo dice anche quando non e' partito nulla, e il pending scadra' in silenzio dopo cinque
minuti.

**56. Una proposta di tipo non gestito viene marcata come applicata.** `handlers_proposals.py:110-123`.
Promette: il commento dichiara che con la validazione del tipo alla creazione «nessuna proposta nota
dovrebbe arrivare qui» e che non si ingoia piu' in silenzio; un secondo commento dichiara che questo
era esattamente il bug numero 2, «sembrava applicata ma non cambiava nulla». Fa: il ramo e'
raggiungibile per qualunque riga gia' in archivio con un tipo fuori dai quattro gestiti; marca la
proposta come applicata e risponde con successo senza toccare Home Assistant. Il difetto denunciato
dal commento e' ancora li', con un log in piu'. *Due voci del registro, unite.*

**57. Il campo che distingue «scritto e marcato» da «scritto e non marcato» non e' letto da
nessuna vista.** `handlers_proposals.py:58-59, 73-74, 108-109` + `static/config/proposals-core.js:28-31`.
Promette: l'handler ritorna `{'ok': bool(applied)}`. Fa: il campo viaggia con HTTP 200 e le tre
viste costruiscono l'esito dallo **stato HTTP**, quindi `ok=false` e' indistinguibile da un successo
pieno. Conseguenza pratica: due clic ravvicinati disegnano due volte «Proposta attivata» in verde
mentre la scrittura su Home Assistant e' avvenuta due volte, la seconda passando dal ripiego per
nome.

**58. Un'automazione «creata» puo' restare inerte fino al riavvio di Home Assistant.**
`ha_client.py:311-317`. Promette: il commento dichiara «Reload so the new automation becomes active
immediately». Fa: se il ricaricamento solleva, registra e ritorna comunque un successo; e la
funzione sottostante non solleva affatto su stati non-200, ritorna falso — falso che non viene
nemmeno guardato. L'utente legge «creata» e non trova l'automazione nell'interfaccia di Home
Assistant.

**59. Un comando approvato dal telefono che fallisce non produce alcun segnale.**
`handlers_gateway_pending.py:257-266` con `:278-288`. Promette: `approve` restituisce esito e
`resolve_pending` lo registra. Fa: `resolve_pending` marca «approvata» a prescindere dall'esito
reale del dispatch, e sul percorso del tocco il valore di ritorno viene scartato. Ne' notifica, ne'
log dedicato, ne' riga in inbox. Solo il percorso via interfaccia legge l'errore e lo dice. Il
messaggio «Comando approvato ma NON eseguito su Home Assistant», scritto apposta per questo caso,
resta irraggiungibile perche' il fallimento arriva nella forma `false` e non nella forma prevista
(`gateway-route.js:167-171, 196-197`).

**60. Il registro di controllo dell'MCP interno registra come riuscite le azioni negate.**
`mcp/server.py:29` (dal flusso 4.6): l'audit cerca l'errore nella chiave sbagliata dell'involucro,
quindi ogni azione negata — dal semaforo, dalla denylist, da Home Assistant — viene registrata come
riuscita.

**61. Il pulsante «Copia» della card conferma anche quando fallisce.**
`hiris-chat-card.js:1251`: il ritorno positivo e quello negativo sono gestiti allo stesso modo.

**62. La prova manuale del Chatbot dichiara «ESEGUITO» per una cosa che non e' la chat.**
`static/config/chatbot-editor.js:747`. Promette: «✓ ESEGUITO». Fa: il run invia alla persona un
messaggio finto `[Agent trigger: unknown]` (`chatbot_engine.py:507-508`), senza storico e senza
contesto casa: non riproduce l'esperienza di chat, e «ESEGUITO» descrive solo il fatto che una
risposta e' arrivata. Va letto insieme al fatto — registrato in sezione 4 — che la prova esegue
davvero, con gli strumenti concessi al Chatbot, quindi puo' agire sui dispositivi.

**63. Un difetto di firma si presenta all'utente come indisponibilita' del fornitore.**
`chatbot_engine.py:520-541` + `llm_router.py:215-234`. Promette: «Reachable from the manual "run"
API». Fa: la chiamata passa `agent_id=chatbot.id`, parola chiave che nessuno dei due runner accetta
(verificato con `inspect.signature`); il router la inoltra dopo aver rimosso solo `mode`, ogni
backend solleva un errore di tipo, il router lo scambia per un guasto del fornitore e restituisce
«Tutti i provider AI non disponibili. Riprova tra poco.». **Attenzione: questa e' una delle due
letture in conflitto** — l'altra descrive il Test Run come funzionante (cfr. fine della sezione 2 e
sezione 11).

**64. Quando nessun fornitore risponde, l'utente riceve una notifica il cui corpo e' «(vuoto)».**
`watcher/reasoner.py:132-134` + `server.py:1740-1742, 1751-1754` + `watcher/executor.py:13-15`.
Promette: il verdetto predefinito «anomalia» serve perche' «un modello che risponde male non deve
tradursi in silenzio» e «il testo grezzo diventa il messaggio». Fa: quando non c'e' alcun runner o
tutti i backend falliscono, il testo grezzo e' la stringa vuota: il messaggio diventa il letterale
«(vuoto)», recapitato come notifica persistente intitolata «HIRIS Sentinella», con la timeline che
registra un'anomalia.

**65. Gli errori tecnici del server arrivano all'utente come frasi dell'assistente.**
`static/chat/send.js:113`. Promette: le bolle con l'avatar HIRIS sono cio' che il Chatbot ha
risposto, e i moduli vicini dichiarano il principio opposto — «mai la stringa tecnica del backend
all'utente» (`config/proposals-core.js:34-48`, `chat/knowledge.js:209-213`). Fa: `data.response ||
data.error` trasforma ogni errore applicativo in una bolla di HIRIS con la stringa inglese del
backend: «message too long (max 4000 chars)», «Claude runner not configured — set CLAUDE_API_KEY»,
«csrf_required», «unauthorized», «Invalid JSON body». Sono indistinguibili da una risposta del
modello.

---

## 9.4 Configurazione che non ha l'effetto dichiarato

Sono i campi che l'utente compila credendo di cambiare qualcosa.

**66. Il tetto di token per Chatbot non ha effetto in chat.** `handlers_chat.py:327-332`. L'editor
espone `max_tokens` con default 4096 (`static/config/chatbot-editor.js:170`); in chat il valore
viene sempre alzato a 16000 se inferiore. Sotto quella soglia il campo non fa nulla. Ne ha invece
nella prova manuale, dove viene solo limitato verso l'alto (`chatbot_engine.py:259-263`).

**67. Le due opzioni che scelgono l'ordine dei backend non possono influenzare il routing.**
`config.yaml:51-52` (`automatic_policy`, `chat_policy`) vs `server.py:2620-2629` e
`llm_router.py:144-150`. Il router e' costruito sempre con una catena di modelli non vuota — la
catena riconciliata restituisce un elenco non vuoto ogni volta che almeno un provider e' attivo, ed
e' l'unica condizione in cui il router viene costruito (`server.py:2601`) — e `if model_chain:`
sostituisce **entrambe** le policy. Il codice le marca «deprecato» nei commenti
(`server.py:2626-2627`); il modulo di configurazione no. *Tre voci del registro (aree Opzioni,
Superficie HTTP, e un reperto fra gli inerti) sono lo stesso difetto, qui unite.*

**68. Le tre opzioni che descrivono il perimetro del gateway smettono di contare al primo
salvataggio della pagina.** `translations/en.yaml:85-91` / `it.yaml:85-91` vs
`handlers_gateway_policy.py:269-277`. Se esiste anche una sola categoria o entita' in
`/data/gateway_policy.json` — cioe' appena l'utente tocca la pagina Accessi Gateway —
`apply_saved_policy` svuota e riscrive il perimetro in blocco: i tre elenchi smettono di avere
qualsiasi effetto, all'avvio e a ogni salvataggio. Nulla lo dice all'utente.

**69. «Lascia vuoto per generarlo automaticamente» non genera nulla.** `translations/en.yaml:82` e
`it.yaml:82` vs `server.py:1165` e `handlers_execute.py:139`. Nessuna generazione automatica esiste:
con il valore di fabbrica (`config.yaml:75 = ""`) il token resta vuoto, il middleware nega ogni
richiesta non-ingress e `/api/execute` risponde sempre 401 — quindi il client MCP loopback della
chat via abbonamento non puo' eseguire alcuno strumento (`mcp/local_client.py:39, 47-50`).

**70. L'avviso sulla rete di ingress promette un ripiego che non c'e'.** `run.sh:114-116` vs
`server.py:1170-1172` e `middleware_internal_auth.py:52-57`. L'avviso dice: «l'app ignora le voci
non parsabili e usa il default». Fa: il ripiego scatta solo se la lista risulta **vuota**. Con un
valore non vuoto e non parsabile nessuna richiesta e' piu' riconosciuta come ingress e — con il
token vuoto — l'intera interfaccia, file statici compresi, risponde 401.

**71. Spostare la porta del server MCP interno rompe la chat via abbonamento.** `config.yaml:93` vs
`agent/runner.py:55`. Il server si sposta davvero (`server.py:1124`), ma il file di configurazione
consegnato al CLI punta a `http://127.0.0.1:8199/mcp` scritto a mano. Cambiando la porta la chat via
abbonamento perde tutti gli strumenti, senza controlli di coerenza ne' avvisi.

**72. L'avviso sull'esposizione della porta di debug guarda l'opzione, non la porta.**
`config.yaml:136-140` vs `run.sh:95-105`. Si puo' avere la porta aperta sulla LAN senza alcun
avviso, e l'avviso con la porta chiusa. (Le traduzioni, a differenza del commento, sono corrette.)

**73. Il pre-volo dichiara la chat inutilizzabile su installazioni che funzionano.**
`run.sh:117-120`. La condizione controlla `CHAT_VIA_SUBSCRIPTION` e ignora `PROVIDER_SUBSCRIPTION`
e `CLAUDE_CODE_OAUTH_TOKEN`, cioe' proprio il percorso abbonamento di prima classe
(`server.py:1140-1144`).

**74. Il tetto giornaliero della Sentinella non e' globale.** `translations/*.yaml:112`
(`sentinel_daily_cap`) vs `watcher/wake.py:24` e i `cap_scope` in `guardian.py:140`,
`evaluator.py:50`, `arrival.py:69`, `agentbot_runner.py:267-271`. Eventi, situazioni, arrivi e ogni
singolo Agentbot hanno ciascuno il proprio budget pari al valore dell'opzione: il tetto reale e' il
valore moltiplicato per il numero di sorgenti attive. La revisione olistica non usa affatto quel
valore, usa `per_day` della policy (`evaluator.py:57`).

**75. L'automatismo del verde non copre i domini pericolosi.** `translations/*.yaml:118`
(`sentinel_allow_green_auto`) vs `watcher/executor.py:19-23`. Il controllo sulla denylist precede
quello del livello: con un dominio pericoloso si notifica e basta, anche marcandolo verde e con
l'opzione accesa.

**76. La conservazione dei ricordi si applica solo alla scrittura e a un solo strumento.**
`translations/*.yaml:79` (`memory.retention_days`) vs `memory_tools.py:135-139`. Il valore viene
impresso come data di scadenza al momento della scrittura e solo da `save_memory`: cambiarlo non
tocca i ricordi gia' salvati, e non copre `save_knowledge`, i documenti importati, ne' le tracce del
cervello.

**77. Il numero di memorie rilevanti vale solo per l'iniezione automatica.**
`translations/*.yaml:76` (`memory.rag_k`) vs `knowledge_tools.py:152`. Lo strumento esplicito
`recall_knowledge` ignora l'opzione e usa `tool_input.get('k', 5)`.

**78. Il salvataggio dei modelli non e' «a caldo».** `handlers_models.py:174` (commento «hot-update
per la sessione corrente») vs `server.py:2525` e `2617`. L'ordine della catena e i modelli per
provider sono letti solo all'avvio: il router e i runner non vengono ricostruiti dopo il
salvataggio, quindi quei due campi hanno effetto solo dal riavvio successivo. Solo il modello del
Brain e' letto a runtime (`server.py:2297`). La riassegnazione della chiave contraddice inoltre la
nota di `handlers_gateway_policy.py:255-257`, che afferma che aiohttp vieta la riassegnazione dopo
l'avvio.

**79. Il campo «Severita'» di un Agentbot non cambia nulla.**
`static/config/agentbot-editor.js:210-218` e `agentbot-route.js:362`. L'esecutore non legge mai la
severita' (`executor.py:6-36`): diventa solo un suggerimento per il parser
(`agentbot_runner.py:273`) e finisce in una colonna che nessuna delle due timeline mostra. Non
cambia il canale, non cambia il titolo, non cambia il varco.

**80. Il campo «Messaggio» di un Agentbot non viene usato quando il ragionamento e' acceso.**
`static/config/agentbot-editor.js:456` e `:434`. L'unica funzione che legge il messaggio
configurato e' chiamata solo nel ramo senza modello (`agentbot_runner.py:352`); con il ragionamento
attivo il testo consegnato e' quello prodotto dal modello, o il suo testo grezzo troncato a 500
caratteri.

**81. Scegliere «Servizio HA» non significa che il servizio venga chiamato.**
`static/config/agentbot-editor.js:81` e `:446-471`. Con un dominio non configurato nella pagina
Permessi il livello vale «spento» e viene emessa solo una notifica; con verde o giallo viene salvata
una **proposta** di script e non parte nemmeno la notifica (`sentinel_proposal.py:168`); il servizio
viene chiamato davvero solo con verde **e** l'opzione di automatismo accesa (di fabbrica spenta,
`config.yaml:107`). Niente di questo e' detto nell'editor.

**82. Due opzioni compaiono nel modulo senza alcuna traduzione.** `config.yaml:93`
(`internal_mcp_port`) e `config.yaml:125` (`claude_code_oauth_token`): l'utente vede la chiave
grezza senza nome ne' descrizione, e la seconda e' proprio la credenziale citata per nome dalla
descrizione dell'interruttore dell'abbonamento.

**83. Il livello di log non copre tutto il processo.** `config.yaml:99`: agisce sul processo Python
ma non sul server MCP interno, fissato a «warning» (`server.py:1132`), ne' sui log dello script di
avvio.

**84. La proposta di un Agentbot nasce attiva, non disabilitata.** `tools/proposal_tools.py:27-30`
promette: «The proposal is saved as disabled/pending — the user must explicitly activate it». Fa:
all'applicazione la validazione mette `enabled=True` per default se il modello non ha scritto il
campo (`agentbots.py:652-657`), e la mutazione registra subito i lavori e rinfresca la cache.
L'Agentbot e' attivo dal momento dell'approvazione.

---

## 9.5 Superfici che mostrano il falso

**85. I «Suggerimenti del Brain» non sono suggerimenti.** `static/config/agentbot-route.js:422` +
`brain/suggestions.py:196-212` + `brain/cognitive_loop.py:207-223`. Le righe di copertura sono
modifiche **gia' applicate** alla policy senza chiedere nulla; le righe di taratura non sono nemmeno
suggerimenti, sono azioni dirette registrate a posteriori con lo stesso tipo proprio per riusare il
pulsante «Annulla» di quella lista.

**86. Lo «Stream ragionamenti» della Dashboard e' vuoto per sempre su un'installazione
predefinita.** `static/config/dashboard.js:157-160, 180` + `server.py:2302-2307`. L'unico scrittore
di quel registro e' la revisione olistica, che e' spenta di fabbrica (`policy.py:31`): nessun
ragionamento della Sentinella per evento, delle situazioni, del resoconto o degli Agentbot vi finisce
mai. La pagina dice «Il Brain non ha ancora ragionamenti registrati» dopo decine di ragionamenti al
giorno.

**87. La Sentinella, quando riesce, non dice nulla.** `watcher/sentinel_proposal.py:134-168` +
`watcher/executor.py:27-33`. Quando la proposta viene creata con successo non parte alcuna notifica:
l'anomalia rilevata resta muta e la si scopre solo aprendo la pagina Proposte. Il caso di errore e'
piu' visibile del caso riuscito.

**88. «Nessun evento registrato per questa regola» significa spesso il contrario.**
`static/config/agentbot-editor.js:83` e `:488-515`. La sezione chiama la timeline senza limite, il
backend restituisce gli ultimi cinquanta eventi **globali** (`handlers_sentinel.py:41-48`,
`sentinel_store.py:111-116`) e il filtro avviene lato client: in una casa attiva gli eventi
dell'Agentbot escono dalla finestra e la pagina dichiara che non ce ne sono mentre nel database ci
sono.

**89. Il freno di trenta minuti sopprime senza lasciare traccia.** `watcher/wake.py:21-22`. Un
Agentbot a evento marcato «Attiva» che riscatta entro il periodo di pausa viene soppresso senza
registrare nulla: nessuna riga negli eventi, nessun log, nessun segnale a schermo. Non e'
configurabile per Agentbot ne' visibile da nessuna parte.

**90. «Task recenti (24h)» copre una settimana.** `static/index.html:191` vs `chat/tasks.js:33` e
`task_engine.py:19`. L'API non filtra per data e il pannello divide solo per stato: sotto
quell'etichetta compare tutto cio' che il motore tiene in memoria, cioe' sette giorni.

**91. L'orario sotto ogni bolla e' l'ora del disegno, non del messaggio.**
`static/chat/messages.js:23-24` e `agents.js:128-130`. La cronologia ricaricata porta solo ruolo e
contenuto (`chat_store.py:263`) e viene marcata con l'ora del ricaricamento: dopo un aggiornamento
della pagina l'intera conversazione risulta avvenuta adesso.

**92. Il contatore dei turni della pagina si allontana da quello del server.**
`static/chat/send.js:117-119`. Viene incrementato anche quando la «risposta» e' un errore (409, 429,
400, 413, 503), mentre il server sui rami di errore non ha persistito nulla. *Il caso simmetrico —
il server rifiuta mentre la pagina lascia l'input aperto — e' descritto in sezione 4.*

**93. Un guasto del pannello Task e' visivamente identico a un pannello che sta caricando.**
`static/chat/tasks.js:28-43`. Se la lettura fallisce nessuna delle due liste viene scritta: restano i
soli titoli di sezione. Lo stesso vale nella pagina di configurazione, dove la funzione che legge i
task trasforma qualunque guasto in una lista vuota (`tasks-route.js:29`).

**94. Il pallino numerico delle Proposte resta al valore precedente dopo un errore.**
`static/chat/proposals.js:183-190`: la funzione che lo scrive e' chiamata solo nel ramo di successo,
quindi accanto a un pannello che dice «Errore nel caricamento delle proposte» resta il conteggio di
prima.

**95. La distinzione fra «coda vuota» e «non ho potuto leggerla» sopravvive solo dentro il
pannello.** `static/chat/knowledge.js:157-169`. Il commento dichiara che i due casi vanno detti in
modo diverso e che il pallino non deve mostrare un conteggio inventato; in caso di errore il pallino
viene portato a zero, e a zero il foglio di stile lo nasconde (`hiris-chat.css:105`): nella barra di
navigazione i due casi tornano identici.

**96. La pastiglia con il nome del Chatbot sembra un selettore e non lo e'.**
`static/hiris-chat.css:199` + `index.html:144-148`. Nessun gestore di clic e' registrato: e'
un'etichetta. Il pallino verde e' decorativo e pulsa sempre, anche quando l'indicatore di
connessione e' passato a «offline».

**97. Dopo un aggiornamento della pagina il titolo torna a dire «HIRIS».**
`static/chat/agents.js:150-151`: solo il cambio di Chatbot riscrive il titolo; al ricaricamento il
Chatbot attivo viene ripristinato e la pastiglia mostra il nome giusto, il titolo no.

**98. Un tipo di proposta sconosciuto viene mostrato con le entita' HTML in chiaro.**
`static/chat/proposals.js:44` e `57`: l'etichetta del tipo e' gia' costruita con l'escape e poi
ristampata con l'escape, quindi a schermo comparirebbero `&amp;` e `&lt;` invece dei caratteri.

**99. Il sottotitolo della pagina Proposte promette meno e attribuisce male.**
`static/config/proposals-route.js:7`: «Una proposta attivata genera una automation HA nativa. Le
proposte sono generate dal Brain HIRIS...». La stessa pagina elenca e attiva anche proposte di
plancia, script, scena e Agentbot, che non generano alcuna automazione; e le origini sono cinque,
non una.

**100. Le tre viste della stessa coda non mostrano le stesse informazioni.**
`watcher/sentinel_proposal.py:46-52` afferma che il pannello Proposte non mostra anteprima del
contenuto, e su quello fonda la scelta di caricare la descrizione di significato: e' vero per il
pannello della chat e per l'anteprima della Dashboard, ma la pagina Proposte della configurazione
mostra il blocco JSON per plance, script e scene (`config/proposals.js:33-41`). Per le automazioni
non lo mostra nessuno: si preme «Attiva» su condizioni e azioni mai viste.

**101. Il pannello «Memoria» non elenca la memoria.** `static/index.html:90-96` e `204-212` con
`handlers_knowledge.py:36`. Il commento HTML dice «Coda della memoria: cio' che HIRIS ha imparato e
non e' ancora richiamabile». Fa: mostra esclusivamente le righe in attesa. Cio' che HIRIS ha
effettivamente memorizzato — le memorie di `save_memory`, gia' approvate, la conoscenza approvata, i
documenti, gli insight — non e' visibile, ispezionabile ne' cancellabile da nessuna schermata.

**102. La card mostra un banner rosso e continua a rispondere, da un altro interlocutore.**
`hiris-chat-card.js:800`. Il compositore resta abilitato e il server, ricevendo un identificativo
sconosciuto, ricade sul Chatbot predefinito (`handlers_chat.py:161-166`): si vede «Chatbot non
configurato» e si ricevono comunque risposte, salvate localmente sotto un identificativo
inesistente.

**103. Il banner «Chatbot disabilitato. Le richieste sono in pausa.» non corrisponde a nulla lato
server.** `hiris-chat-card.js:1164` e `handlers_chat.py:160-166`. Nessun codice server legge
`Chatbot.enabled` per rifiutare una richiesta di chat, e anche `POST /api/chatbots/{id}/run` lo
ignora (`handlers_chatbots.py:226-235`). La pausa e' solo la casella di scrittura disabilitata
dentro quella card: la pagina chat e il gateway continuano a parlare con lo stesso Chatbot. *Due
voci del registro, unite.*

**104. La barra del budget della card non puo' mai comparire.** `hiris-chat-card.js:797` e
`1151-1162`: legge `agent.budget_limit_eur`, campo che non esiste piu' — il dataclass Chatbot lo ha
perso e l'elenco dei Chatbot non lo aggiunge. L'intero blocco non viene mai disegnato.

**105. La card cerca entita' MQTT con lo schema di nomi dismesso.** `hiris-chat-card.js:710-721`
legge `sensor.hiris_<id>_*` e `switch.hiris_<id>_enabled`; lo schema pubblicato oggi e'
`chatbot_<id>_<metric>` (`mqtt_publisher.py:147, 169, 230`) e quello vecchio viene attivamente
ritirato (`:271-310`). Il ramo non si attiva mai: si finisce sempre nel ripiego a interrogazione
HTTP.

**106. Il limite di trenta secondi della card cancella il testo gia' ricevuto.**
`hiris-chat-card.js:14, 822, 896`. Il controllo di interruzione copre l'intero consumo della
risposta, non solo l'apertura: ogni risposta che richieda piu' di trenta secondi complessivi —
tipico con gli strumenti — viene interrotta e il testo gia' ricevuto viene **sovrascritto** dal
messaggio di timeout, mentre il server ha comunque consumato i token.

**107. Un errore trasmesso dentro il flusso arriva come una normale risposta e resta salvato come
tale.** `hiris-chat-card.js:876-879`: il ramo dell'evento di errore non imposta il marcatore che
colora la bolla di rosso, e il filtro del salvataggio guarda solo se la bolla e' in streaming.

**108. Il limite di turni raggiunto diventa «Nessuna risposta».** `hiris-chat-card.js:884-888`: il
server risponde 200 con un corpo che dichiara il limite (`handlers_chat.py:177-184`); la card non
riconosce quel corpo, la pagina chat si' e dice «Sessione completata».

**109. La card interroga per cinque minuti anche quando il lavoro non esiste.**
`hiris-chat-card.js:911-946`: i corpi senza campo di stato — 404 «not found» e 503 «reasoning queue
not configured» — vengono trattati come «in corso».

**110. Non si puo' scrivere mentre arriva una risposta, ne' scorrere indietro.**
`hiris-chat-card.js:1136` e `1207`: ogni ridisegno riscrive il contenitore e ricrea la casella di
scrittura; il valore viene conservato, il fuoco e la posizione del cursore no, e la lista viene
riportata in fondo. Il ridisegno avviene a ogni pezzo di risposta e a ogni ciclo di aggiornamento da
trenta secondi.

**111. L'avviso «Annulla» della card non e' ancorato alla card.** `hiris-chat-card.js:462-473` e
`644-648`: e' posizionato in modo assoluto ma non ha un antenato posizionato dentro la card.

**112. La card segue il tema del sistema operativo, non quello di Home Assistant.**
`hiris-chat-card.js:142-166`. La pagina chat risolve invece preferenza locale, poi configurazione
del server, poi sistema.

**113. Due card sulla stessa dashboard condividono l'indirizzo scoperto dalla prima.**
`hiris-chat-card.js:50-51, 559, 590`: le chiavi locali sono separate per card, ma l'indirizzo di
ingress e il momento dell'ultimo rinnovo sono variabili di modulo.

**114. La card e' l'unico client che chiede lo streaming, ed e' quello meno resiliente.**
`hiris-chat-card.js:830-833`: il ramo in streaming del router non ha alcun ripiego fra fornitori
(«no fallback in streaming (as today): just the first pick», `llm_router.py:237-250`), mentre il
ramo non in streaming prova tutta la catena.

**115. Chi usa la card non vede mai quali strumenti sono stati usati sulla propria casa.**
`hiris-chat-card.js:875`: l'evento conclusivo trasporta l'elenco degli strumenti chiamati e il ramo
JSON pure, e la card scarta entrambi. La pagina chat li mostra come etichette cliccabili.

**116. L'editor visuale della card puo' mostrare un Chatbot e la card usarne un altro.**
`hiris-chat-card.js:1356-1366` e `1415-1423`: se l'identificativo salvato non e' fra le opzioni,
nessuna opzione risulta selezionata, il browser mostra la prima e nessun evento parte, quindi la
configurazione resta sul valore vecchio. *E manca* il campo per lo slug dell'add-on
(`:1379-1406`), che pure e' letto dalla configurazione e usato per la scoperta dell'indirizzo e per
la chiave locale.

**117. Il ripiego sull'indirizzo di ingress non puo' funzionare, e non viene mai ritentato.**
`hiris-chat-card.js:770-774` e `1312-1313`: il commento del server dichiara che il Supervisor usa un
token casuale, non lo slug (`server.py:221-227`); e la scoperta non ritenta mai dopo il primo
fallimento, quindi una singola lettura fallita al montaggio blocca la card sul ripiego impossibile
fino al ricaricamento della pagina.

**118. Se la copia della card fallisce, la risorsa viene registrata lo stesso.**
`server.py:176-177`: si registra `/local/<slug>/hiris-chat-card.js?v=<versione>`, che puntera' a un
file inesistente. L'utente vede una card rotta nella dashboard, non un messaggio.

**119. Il testo su piu' righe viene inviato mentre lo si incolla.** `static/chat/send.js:140-156`:
il gestore dell'evento di input considera qualunque a-capo comparso nel testo come intenzione di
invio, toglie gli a-capo e invia. Con Shift+Invio il messaggio parte lo stesso, appiattito su una
riga; anche incollare un testo su piu' righe lo invia subito.

**120. La pagina chat non chiede mai lo streaming e non mostra mai il ragionamento.**
`static/chat/send.js:82-129` vs `handlers_chat.py:342-416`: il backend espone uno streaming e
restituisce anche i blocchi di ragionamento (`:490-494`), che la pagina non legge.

**121. La chat via abbonamento ignora in silenzio quasi tutta la configurazione della persona.**
`handlers_chat.py:66-100`: il lavoro accodato porta solo identificativo del Chatbot, storico e
prompt di sistema. Il lavoratore usa una lista di strumenti fissa che include chiamata di servizio e
notifica (`agent/runner.py:25-32`) e un modello preso da una variabile d'ambiente
(`agent/runner.py:133`). Niente contesto casa, niente memoria, niente riassunti, niente perimetro.

**122. Il costo di tutto il traffico OpenRouter e' contabilizzato come zero.**
`backends/pricing.py:22-23`: i modelli non presenti in tabella ricadono su un prezzo nullo, e gli
identificativi OpenRouter arrivano gia' privati del prefisso e non compaiono mai in tabella.
Indistinguibile da Ollama, che e' davvero gratuito.

**123. Il consumo mostrato non comprende tutto il consumo.** `claude_runner.py:628-638` e
`openai_compat_runner.py:432-462`: `simple_chat` non incrementa nessun contatore e non salva il file
di consumo. Le chiamate di classificazione delle entita' (`llm_router.py:386-414`), che partono
all'avvio e dalla SemanticContextMap, sono invisibili; anche l'intera chat via abbonamento non tocca
alcun contatore.

**124. Un nome di modello scritto male non produce un errore, produce un altro modello.**
`llm_router.py:202-209` + `openai_compat_runner.py:403-405`: qualunque stringa che non cominci per
`claude-`, `gpt-`, `o1..o9` o `openrouter:` viene instradata al runner Ollama, che avendo un modello
fisso ignora completamente il nome richiesto.

**125. Con il backend Anthropic non c'e' streaming.** `claude_runner.py:839-908`: la docstring parla
di un generatore che emette righe di evento, e la card apre un lettore di flusso con il cursore
lampeggiante; il codice attende l'intera risposta e poi la taglia in blocchi da 80 caratteri —
comportamento che la docstring stessa ammette come «fase 1». *Due voci del registro (aree Chat e
Card), unite.* Per l'utente: non si vede nulla per tutta la durata del turno, e la card interrompe
comunque a trenta secondi.

**126. La condizione di un task puo' concludere «no» quando il dato non c'e'.**
`task_engine.py:329-333`: se la cache delle entita' e' assente la condizione ritorna vero e il task
esegue comunque; se lo stato e' `unavailable` o `unknown` un confronto numerico ricade in fondo e
ritorna falso, cioe' «condizione non soddisfatta» invece di «dato non disponibile», e il task viene
marcato saltato. Il fratello che valuta le condizioni degli Agentbot pianificati
(`server.py:499-540`) ha invece una guardia esplicita.

**127. La pagina Task attribuisce ai Chatbot task che non nascono da li'.**
`static/config/tasks-route.js:148` dice «Task asincrone schedulate dai Chatbot»: nascono anche dal
gateway MCP (`handlers_execute.py:348-351`), dalla Sentinella (`server.py:1859-1866`) e dagli
agenti, e per quelli la colonna mostra l'identificativo grezzo.

**128. Una richiesta di conferma nata da un task si presenta come se venisse da una chat.**
`server.py:457` con `task_engine.py:489-497`: l'origine e' scritta a mano come «chat» anche quando
la richiesta arriva dallo scatto di un task. Nell'inbox compare come se l'utente l'avesse appena
chiesta in conversazione, e nel pending non finisce alcun identificativo del task.

**129. La quantita' richiamabile dalla conoscenza non ha tetto.** `knowledge_tools.py:32-43` vs
`memory_tools.py:180`: `recall_knowledge` accetta `k` senza alcun limite superiore
(`knowledge_tools.py:152`), mentre il gemello `recall_memory` limita a 1..20. Un valore grande
scarica nel prompt tutto quello che l'archivio restituisce.

**130. I «riassunti delle sessioni precedenti» non sono riassunti.** `handlers_chat.py:243-251` con
`chat_store.py:177-206`: la chiusura di sessione concatena verbatim le ultime coppie di turni
troncate a lunghezza fissa. Nessun modello viene interpellato.

**131. Il collegamento fra due elementi del second brain e' dichiarato «proposta» e scrive subito.**
`knowledge_tools.py:45-48` e `:203-214`: il collegamento e' scritto immediatamente con origine
«inferred»; non esiste alcuno stato in attesa, nessuna coda, nessuna interfaccia. E il collegamento
non serve a nulla: l'unico lettore (`knowledge_store.py:362-377`) non ha chiamanti di produzione.
*Due voci del registro, unite.*

**132. Cio' che il modello scrive nel second brain non e' validato.**
`knowledge_tools.py:97-122`: il tipo e la sensibilita' dichiarano un insieme chiuso di valori nello
schema, ma arrivano grezzi all'archivio senza alcuna validazione — qualunque stringa diventa il tipo
della riga. Nessun tetto sulla lunghezza del contenuto (`save_memory` ne ha uno di mille caratteri),
nessuna validazione del formato della scadenza.

**133. Nel risultato del richiamo convivono due spazi di numerazione sotto la stessa chiave.**
`knowledge_tools.py:173-177` e `:196`: identificativi di elementi e identificativi di frammenti di
documento, due tabelle diverse, sotto la stessa chiave `id`. Un collegamento creato dal modello su
un identificativo di frammento viene scritto senza alcun controllo di esistenza
(`knowledge_store.py:349-360`: nessuna chiave esterna dichiarata).

**134. Gli strumenti di memoria restano esposti anche quando la memoria non puo' funzionare.**
`dispatcher.py:229-233` + `claude_runner.py:727` + `openai_compat_runner.py:558, 844`. Promette:
«save_memory/recall_memory route into the unified KnowledgeStore — gate tool exposure on that». Fa:
il controllo verifica che l'oggetto non sia nullo, ma il costruttore restituisce **sempre** un
oggetto: con provider vuoto (default di fabbrica) restituisce il motore fittizio, il cui calcolo
ritorna una lista vuota. Su un'installazione appena creata i due strumenti restano esposti e
falliscono a ogni chiamata, e la ricerca automatica non trova mai nulla, in silenzio.

**135. Le previsioni meteo non riguardano la posizione della casa.** `tools/weather_tools.py:11-16,
93-95` promette «Get weather forecast for the home location». Fa: la posizione non viene mai letta
da Home Assistant — sono due variabili d'ambiente e, in loro assenza, le coordinate fisse di Milano.
Il numero di ore non e' limitato in codice e finisce grezzo nell'indirizzo.

**136. La firma di lettura degli stati fa credere a una lettura mirata.** `ha_client.py:164-171`:
chiama `GET /api/states` senza parametri, cioe' l'intero stato della casa, e poi filtra in Python. Il
costo verso Home Assistant e' identico che si chieda una entita' o tutte.

**137. Una casa senza aree e una casa illeggibile si presentano allo stesso modo.**
`dispatcher.py:255-257` vs `entity_cache.py:10-29`: i messaggi che distinguono «non ho potuto
guardare» da «la casa e' vuota» esistono proprio perche' il difetto era sopravvissuto nei moduli
fratelli, ma `get_area_entities` non passa da quel controllo: con la cache non caricata ricade sulle
letture via WebSocket, dove qualunque errore diventa una lista vuota (`ha_client.py:861-864`), e lo
strumento risponde «questa casa non ha aree».

**138. Un'entita' cancellata da Home Assistant resta nell'inventario fino al riavvio.**
`entity_cache.py:136-147`: l'evento di rimozione arriva senza nuovo stato e viene ignorato. Lo stesso
evento e' letto dal monitor di salute come un rientro e la voce esce dalla lista dei non disponibili
(`health_monitor.py:229-234`): due componenti leggono lo stesso fatto in due modi opposti.

**139. Un fallimento di autenticazione del WebSocket uccide tutto in silenzio.**
`ha_client.py:906-917` e `952-956`: il ciclo e' scritto come riconnessione perpetua, ma su
autenticazione fallita registra un errore e ritorna, e il compito non viene mai piu' riavviato. Da
quel momento cache, salute, storico, Sentinella, sorvegliante degli arrivi e — soprattutto — la
ricezione dei tocchi Approva/Nega sono morti, mentre ogni strumento continua a rispondere dalla
fotografia congelata.

**140. Il nome amichevole di una nuova entita' non arriva mai.** `ha_client.py:897-899` e `942-951`
vs `proxy/semantic_map.py:183-188`: il ciclo passa il payload dell'evento del registro, non gli
attributi dell'entita', quindi l'etichetta ricade sempre sull'ultimo segmento
dell'identificativo. *Il reperto dipende dalla forma reale del payload di Home Assistant, non
verificata (cfr. sezione 11).*

**141. Il perimetro che svuota l'elenco produce due errori diversi.** `history_tools.py:38-47` via
`dispatcher.py:265-278`: se il filtro svuota la lista, la lettura dello storico risponde «entity_ids
must be a list of 1..20 ids», cioe' un errore di input malformato; il gemello che legge gli stati
(`dispatcher.py:258-264`) ritorna un elenco vuoto, indistinguibile da «non esiste». Ne' l'uno ne'
l'altro dice «fuori perimetro».

---

## 9.6 Il contratto verso il modello

Sono i casi in cui la descrizione che il modello legge non corrisponde a cio' che lo strumento fa.
Contano perche' il modello e' l'unica cosa che parla all'utente.

**142. Il catalogo della UI ha uno strumento in meno di quello reale.**
`static/config/templates.js:61-98`: 36 voci contro le 37 dichiarate, manca `http_request`. Un
Chatbot configurato con una selezione esplicita non puo' mai riceverlo, anche avendo endpoint
validi; lo riceve solo se la selezione e' vuota. Il test di sincronia controlla una sola direzione.

**143. Il modello non sa che esiste il campo su cui poggia tutto il gating.**
`claude_runner.py:139-151`: lo schema di `call_ha_service` dichiara solo dominio, servizio e dati,
mentre il dispatcher legge anche `target` (`dispatcher.py:417`) e ci costruisce sopra tutta la
normalizzazione dei bersagli. Il modello non e' informato dell'esistenza di `target`, che
`security/semaphore.py:14-24` tratta come vettore d'attacco noto.

**144. Gli strumenti MCP dichiarano parametri precisi e ne pubblicano uno generico.**
`mcp/tiers.py:21-129` + `mcp/server.py:22, 41`: tutti gli handler hanno la stessa firma e sono
registrati con la sola descrizione; lo schema pubblicato al modello ha un unico parametro generico.
La forma degli argomenti e' comunicata in prosa. *La traduzione effettiva in schema JSON non e'
stata verificata (cfr. sezione 11).*

**145. Uno strumento visibile puo' essere strutturalmente rifiutato.** `mcp/tiers.py:93-102` vs
`handlers_gateway_policy.py:40-46, 199-201`: `create_task` e' esposto come sempre disponibile, ma la
derivazione della policy lo aggiunge solo quando esiste almeno un dominio o un'entita' azionabile;
senza, l'endpoint risponde 403 «tool 'create_task' not exposed by execute-API policy».

**146. Uno strumento concesso dalla policy non e' esposto dal catalogo.**
`handlers_gateway_policy.py:45-46`: `create_ha_config` e' fra gli strumenti che «il gateway puo'
sempre raggiungere», ma nessuna voce di `mcp/tiers.py` lo espone: e' raggiungibile solo da chi parla
direttamente a `/api/execute` con il token interno. *Tre voci del registro dicono questa stessa
cosa* (aree Catalogo, Proposte e Semaforo), qui unite.

**147. Uno strumento dichiarato disponibile in chat e' irraggiungibile dalla chat via
abbonamento.** `mcp/tiers.py:45-60` e `handlers_gateway_policy.py:36-38`: su `render_template si
dichiara «In chat e agli agenti locali resta pienamente disponibile». E' vero per la chat con chiave
API, che dispaccia direttamente; non lo e' per la chat via abbonamento, che passa dal server MCP e
dove `render_template` non e' fra gli strumenti — cosi' come `get_logbook` e `get_advisories`, che
l'MCP espone e l'allowlist del CLI esclude (`agent/runner.py:26-33`).

**148. La descrizione dei task promette un elenco corto e ne restituisce uno lungo.**
`task_tools.py:54-58`: «Returns active tasks and recent completed tasks (in the last 24h)». Fa:
`list_tasks` (`task_engine.py:166-178`) ritorna **tutti** i task in memoria, senza distinzione e
senza finestra di 24 ore: lo storico e' quello dei sette giorni della pulizia.

**149. La descrizione dei task dichiara solo il verde, e giallo e rosso passano.**
`task_tools.py:20-21` vs `task_engine.py:489-497`: giallo e rosso non vengono rifiutati, producono
una richiesta di conferma al proprietario. La descrizione esposta al modello non lo dice; quella
MCP (`mcp/tiers.py:93-101`) si'.

**150. Gli inneschi documentati sono quattro, quelli accettati cinque.** `task_tools.py:12-17` vs
`task_engine.py:134`: esiste anche `immediate`, documentato nel dizionario del frontend
(`static/config/labels.js:76`) e assente dalla descrizione data al modello.

**151. «Oggi alle otto», chiesto alle nove, significa domani.** `task_tools.py:14` vs
`task_engine.py:291-292`: se l'orario e' gia' passato si somma un giorno. Il modello che promette
«lo faccio oggi alle 8» sta dicendo una cosa falsa.

**152. Due orologi diversi passati allo stesso scheduler.** `task_engine.py:283` vs `:290` e `:530`:
il ritardo calcola su un orario consapevole del fuso in UTC, mentre l'ora fissa e la finestra oraria
usano l'orario locale del container.

**153. Un errore di forma diventa un messaggio generico che il modello non puo' correggere.**
`task_engine.py:26-38`: la docstring dichiara che il chiamante «trasforma gia' un ValueError in una
risposta graziosa». Fa: l'errore finisce nell'eccezione generica del dispatcher
(`dispatcher.py:780-786`) e diventa «Strumento 'create_task' non riuscito. Riprova piu' tardi.»:
nessuna indicazione di quale campo fosse malformato. Il messaggio specifico esiste solo nei log.

**154. «Interrompi in caso di fallimento» vale solo per le eccezioni.** `task_engine.py:419-421`:
l'opzione e' letta solo nel ramo delle eccezioni. Un'azione bloccata dal semaforo, fuori perimetro,
con bersaglio collettivo o in attesa di conferma ritorna una stringa e non solleva: la catena
prosegue come se la prima fosse riuscita. L'opzione non e' documentata in alcuna descrizione di
strumento.

**155. «Ricorrente» significa ricorrente solo per le finestre orarie.** `task_engine.py:145` e
`:430-433`: per ritardo, ora fissa e data e ora il task torna in attesa ma nessun nuovo lavoro viene
registrato: resta in attesa per sempre, visibile nel contatore, senza mai riscattare.

**156. Un task che non potra' mai scattare viene restituito come programmato.**
`task_engine.py:317-318`: se la registrazione del lavoro solleva — ritardo senza minuti, orario non
parsabile, data non valida — l'eccezione viene solo registrata nei log; il task e' salvato,
restituito al modello come in attesa, mostrato all'utente come «In attesa» e non scattera' mai;
nemmeno la pulizia lo rimuove, perche' «in attesa» non e' uno stato terminale.

**157. La validazione delle proposte esiste per un tipo su due.** `tools/proposal_tools.py:114-160`:
la validazione di forma esiste solo per le automazioni; per le proposte di Agentbot la
configurazione non viene ispezionata affatto e la sua invalidita' si scopre solo all'applicazione,
con un 400, dopo che l'utente ha premuto «Attiva». E nulla viene mai «salvato come disabilitato»:
non esiste alcun oggetto disabilitato in Home Assistant, esiste solo una riga in un archivio.

**158. Il prompt che riceve un agente-obiettivo non parla di obiettivi.**
`static/config/agentbot-editor.js:38-45` e `:206` promettono «ragiona verso un traguardo ed emette
task». Fa: il prompt di sistema che arriva davvero e' quello della Sentinella
(`reasoner.py:12-19`) piu' i preamboli — e dice di valutare «un SINGOLO segnale di anomalia
domestica» e di concludere sempre con un blocco JSON. Niente gli dice che puo' creare task, che ha
un perimetro, ne' quale sia; `create_task` e' solo presente fra gli strumenti. Per un agente
pianificato senza condizione il messaggio utente e' letteralmente «Segnale: agentbot:<id> su -
Evidenza: {"entity_id": "-"}»: nessun dato sulla casa, va tutto letto dagli strumenti.

**159. Le istruzioni che il modello remoto legge descrivono garanzie che non esistono.**
`mcp/server.py:10-15`: «Letture sempre permesse» e «giallo = conferma su iPhone, rosso = conferma in
HIRIS». Fa: le letture sono rifiutate con 403 se nominano un'entita' coperta dalla denylist e le
risposte sono potate o bloccate del tutto; e per i domini pericolosi il giallo viene forzato a rosso
prima di creare la richiesta (`handlers_execute.py:230-235`), quindi non esiste alcuna conferma con
un tocco per serrature, allarme, tapparelle, sirene e cancelli — e il verde su quegli stessi domini
non viene eseguito ma negato. *Due voci del registro, unite.*

**160. Il wizard offre operatori che il validatore rifiuta.**
`static/config/create-wizard.js:420-424` e `:649`: la soglia e' inviata sempre come stringa, senza la
conversione che fa l'editor avanzato, e il validatore accetta stringhe solo per uguale e diverso
(`agentbots.py:199-227`). L'intero Agentbot viene rigettato e il wizard mostra «Errore nella
creazione: invalid agentbot» senza dire quale campo.

**161. Trenta cause di rigetto distinte collassano in una stringa.**
`handlers_agentbots.py:127` e `:154`. La documentazione del modulo (`agentbots.py:12-19`) descrive
una validazione per campo; l'editor mostra «invalid agentbot» in una finestra di avviso e l'utente
non sa se il problema sia la soglia, il cron, l'operatore o una contraddizione di modalita'.

---

## 9.7 Documentazione interna che descrive un altro prodotto

Sono commenti e docstring che raccontano una versione del codice che non esiste piu'. Non producono
un danno diretto all'utente, ma inducono in errore chi manutiene il sistema — e in almeno un caso
(il numero 7 di questa sezione) il commento sbagliato e' proprio quello che l'utente legge.

**162. «v1 supporta solo verde e spento; giallo e rosso arrivano in v2».**
`handlers_gateway_policy.py:1-10` (e la stessa affermazione a `:6-9`). I flussi giallo e rosso sono
implementati e vivi qui e ora: `handlers_execute.py:236-253` crea la richiesta e manda la notifica,
`handlers_gateway_pending.py:257-266` la esegue all'approvazione, il dispatcher instrada allo
step-up. *Tre voci del registro (aree Gateway, Integrazione, Semaforo), unite.*

**163. «yellow: an actionable iPhone notification» come regola generale.**
`handlers_gateway_pending.py:5-9`: vale solo per i domini non pericolosi; per gli altri il livello e'
gia' stato riscritto a rosso a monte. Il frontend lo dice all'utente
(`gateway-route.js:45-51`), la docstring del modulo che implementa il meccanismo no.

**164. «create_task e' escluso finche' non esiste un dominio verde».**
`handlers_gateway_policy.py:41-44`: la derivazione lo aggiunge quando il perimetro e' azionabile, e
diventa azionabile anche con sole categorie gialle o rosse (righe 183-187). Il varco che il commento
descrive resta chiuso, ma da un altro punto — il filtro per azione in `handlers_execute.py:289-293`.

**165. «allowed_entities e' applicato in esattamente UN posto».** `dispatcher.py:465-482`: il secondo
punto di applicazione esiste gia' ed e' su un altro percorso —
`handlers_execute.py:271-293` verifica alla creazione che ogni azione di primo livello sia verde per
entita'. Chat e gateway creano quindi task con regole diverse.

**166. «create_ha_config dal gateway MCP non e' mai eseguito direttamente».**
`handlers_execute.py:295-297`: il commento presuppone che il gateway possa chiamarlo; il nome non e'
nel catalogo MCP, quindi il ramo e' raggiungibile solo da chi parla direttamente all'endpoint con il
token interno.

**167. «La logica dei tier in un'unica funzione pura».** `security/semaphore.py:4-7`: le
implementazioni sono tre — la funzione pura usata dal dispatcher e dal motore dei task, l'esecutore
della Sentinella che importa la denylist e la funzione di tier ma decide da solo
(`watcher/executor.py:19-27`), e il pre-screening a mano dell'API di esecuzione
(`handlers_execute.py:194-235`).

**168. «Esiste un solo scheduler (verificato)».** `server.py:485-494`: nel processo ce ne sono due —
quello del motore dei Chatbot (`chatbot_engine.py:93`) e quello proprio del motore dei task
(`task_engine.py:100`). E il lavoro «due-reminders» citato dal commento non esiste piu'.

**169. «Tutto lo spegnimento e' difensivo».** `server.py:2697-2753`: ventuno chiusure su ventitre'
lo sono; le ultime due (`:2749-2750`) accedono direttamente alla chiave, quindi se l'avvio era
fallito prima di impostarle la chiusura solleva un errore che maschera quello originale.

**170. Il log d'avvio dichiara avviati due componenti che non possono funzionare.**
`server.py:2669` e `2692`: il server MCP interno e il lavoratore della chat via abbonamento parlano
a HIRIS via HTTP con il token interno, che di fabbrica e' vuoto; ogni loro chiamata riceve 401.
L'unico segnale e' un avviso ripetuto ogni tre secondi.

**171. Il lavoratore della chat via abbonamento puo' partire quando nulla verra' mai accodato.**
`server.py:1433-1438` vs `1136-1144`: le due funzioni che decidono derivano lo stato in due modi
diversi; in una configurazione precisa (Claude attivo, chat via abbonamento accesa, token presente,
ponte spento) nulla viene accodato ma il lavoratore parte comunque e interroga la coda ogni tre
secondi per sempre.

**172. L'endpoint di salute non e' utilizzabile come controllo di salute.** `server.py:2796`: passa
dagli stessi middleware di tutto il resto, quindi senza intestazione di ingress da un IP fidato e
senza token risponde 401. Il Dockerfile infatti non ne dichiara nessuno.

**173. Il percorso del file di ingress non e' quello dichiarato.** `server.py:221-228`: la docstring
dice `/homeassistant/www/{slug}/`, ma la ricerca prova prima `/config`; nel deployment standard il
file finisce in `/config/www/<slug>/`.

**174. La versione non e' letta all'import.** `version.py:4-5`: la lettura e' pigra e memorizzata
alla prima chiamata.

**175. Il riferimento incrociato dentro il codice punta a righe che contengono altro.**
`watcher/agentbot_runner.py:29-36` rimanda a `claude_runner.py:894-896` e `:210-222`; nel file
attuale l'insieme e' a `225-253` e il restringimento a `967-968`. Il ragionamento resta valido, i
riferimenti no.

**176. Un commento cita un file che non esiste piu'.** `brain/cognitive_loop.py:184-186` rimanda a
`sentinel-route.js`; la lista e il pulsante vivono in
`static/config/agentbot-route.js:422-480`.

**177. Un commento descrive uno stato del codice superato.** `static/config/api.js:53-63` afferma
che l'identificativo `usage-last-reset` non e' mai stato aggiunto alla pagina: esiste da
`index.html:116`.

**178. La stringa di invalidazione della cache Docker e' ferma a una versione vecchia.**
`Dockerfile:8-9` dice «update this string with each version bump» ed e' ferma a `HIRIS v0.9.7`
mentre `config.yaml:2` dichiara `1.1.0-beta.15`.

**179. «Gli unici strumenti che colpiscono Home Assistant a ogni chiamata».**
`tools/diagnostics_tools.py:9-11`: molti altri lo fanno — lettura dello storico, storico energia,
eventi di calendario, entita' di un'area in ripiego, elenco e configurazione delle plance. La frase
regge solo restringendo «questo filone» ai soli strumenti di salute.

**180. «Le notifiche non attuano mai dispositivi».** `tools/notify_tools.py:132-137`: per il canale
push il servizio chiamato viene dalla configurazione dell'add-on e non dal modello, quindi in pratica
la promessa tiene; ma l'affermazione e' garantita dalla configurazione, non dal percorso di codice.

**181. La taratura dichiara un «picco» che e' una media.** `brain/cognitive_loop.py:109-111` vs
`history/store.py:243-263`: il testo mostrato all'utente e salvato come traccia dice «picco di
consumo recente ~Y W», mentre il valore e' la media delle medie giornaliere degli ultimi quattordici
giorni.

---

### Nota di riconciliazione

Le voci numerate qui sono **181** a fronte delle **201** del registro. La differenza e' data dalle
unioni, dichiarate nel punto in cui avvengono, e da due voci del registro che non hanno trovato
posto qui: `hiris-chat-card.js:1379-1406` — l'editor visuale della card non espone `hiris_slug`,
che `setConfig` legge a `:689`, la scoperta dell'Ingress usa a `:1310` e le chiavi di `localStorage`
a `:53`, quindi chi non usa lo slug `hiris` deve modificare lo YAML a mano — e
`hiris-chat-card.js:786, 830, 919, 981, 1318`, l'intestazione `Authorization` che nessun handler
legge, quest'ultima trattata come inerte alla voce 39 della sezione 10.

Il conteggio delle unioni **non chiude** e non e' stato riverificato voce per voce: alcune voci del
registro risultano contate sia come unione dentro un'altra voce sia come voce autonoma, e lo
sbilancio minimo dimostrabile e' di sei voci numerate che non possono essere sostenute da una
testata di registro non gia' usata altrove. Le unioni piu' ampie dichiarate nel corpo riguardano la
docstring che descrive una versione v1 del semaforo, il kill-switch dell'MCP interno,
`create_ha_config` assente dal catalogo MCP, le due opzioni di ordinamento dei backend, il flag di
invio delle notifiche e il suo valore mai letto, l'insieme di strumenti concesso agli agenti non
conversazionali, le scritture verso Home Assistant fuori dal semaforo e il registro dell'esito dei
task: quell'elenco e' quello dichiarato dagli analisti e va riverificato prima di essere usato come
inventario.

---

# 10. Codice sospetto di essere inerte

Il registro contiene **104 voci**; questa sezione ne presenta **92**, numerate da 1 a 92 senza salti.
La differenza — dodici voci assorbite da nove fusioni, una voce presentata due volte, una voce
trattata altrove — e' spiegata per intero nella nota di riconciliazione in fondo alla sezione, che
va letta prima di usare questo elenco come lista di lavoro.

Le voci sono raggruppate per **grado di verifica raggiunto**, perche' il lotto D di questo progetto
cancellera' codice basandosi su questo elenco e una rimozione dedotta invece che verificata e' un
danno.

La separazione e' netta e va rispettata:

- **10.1 — Verificato senza chiamanti.** Per queste voci l'analista dichiara di aver fatto la ricerca
  e di averla trovata vuota (o limitata a definizione piu' test). Sono candidati difendibili alla
  rimozione. Attenzione comunque a due categorie: quelle il cui unico consumatore e' un test che
  **pinna l'inerzia** (rimuovendo il codice va rimosso anche il test, e va deciso se l'inerzia era
  voluta), e quelle che sono **inerti per scelta dichiarata** nei commenti, cioe' pezzi lasciati li'
  in attesa di un lavoro successivo.
- **10.2 — Sospetto non verificato, o verificato solo in parte.** Qui la ricerca non e' stata fatta,
  o e' stata fatta ma il ramo resta raggiungibile in condizioni che l'analista non ha potuto
  escludere. **Nessuna di queste voci autorizza una rimozione**: autorizzano una verifica.
- **10.3 — Sospetto smentito.** L'analista ha controllato e ha trovato il chiamante. Sono qui perche'
  *sembrano* morte e non lo sono: toccarle romperebbe qualcosa.

---

## 10.1 Verificato senza chiamanti — rimozione difendibile

**Configurazione validata, persistita e mai letta**

1. `watcher/agentbots.py:504-514` e `:531` — `perimeter.max_tier`: validato con un proprio spazio di
   valori, materializzato con default, persistito, restituito dall'API; nessun consumatore in
   `executor.py`, `task_engine.py`, `dispatcher.py`, `semaphore.py`. **Cautela:** due test pinnano
   proprio la sua inerzia (`tests/test_task_engine.py:1014`, `tests/test_agentbot_editor.py:109`), e
   la UI la dichiara non onorata nei commenti (`agentbot-editor.js:65, 382, 704`). *Voce doppia nel
   registro (aree Agentbot e Semaforo).*
2. `watcher/policy.py:26` — `situations.ronda_minutes`: definito, persistito, ricaricato; la cadenza
   reale viene da una variabile d'ambiente (`server.py:2396`). Un solo altro riferimento, in un
   test. *Voce doppia nel registro.*
3. `config.yaml:140` e `run.sh:95` — `debug_expose_port`: nessuna lettura lato Python; l'apertura
   reale della porta dipende dalla dichiarazione `ports` gestita dal Supervisor.
4. `config.yaml:51-52`, `run.sh:8` e `16`, `server.py:1402-1403` e `2626-2627` —
   `automatic_policy` / `chat_policy`: il ramo che le consuma (`llm_router.py:148-150`) e'
   irraggiungibile ogni volta che il router viene costruito. *Tre voci del registro (aree Chat, Opzioni e Superficie HTTP).*
5. `tools/http_tools.py:42` e `107` — `AllowedEndpoint.follow_redirects`: letto dalla configurazione
   e conservato, mentre la richiesta e' emessa con i redirect disattivati fissi (`:247`).
6. `brain/knowledge_store.py:29` e `:27` — colonne `valid_from` e `confidence`: scritte, mai lette;
   nessuna clausola, nessun ordinamento, nessun consumo lato interfaccia.

**Funzioni e metodi senza chiamanti**

7. `brain/knowledge_store.py:362-377` — `neighbors()`: unico lettore dei collegamenti fra elementi,
   cioe' dell'unico effetto dello strumento `link_knowledge`; nessun chiamante fuori dai test, e il
   dispatcher instrada per nome con catene di `if` letterali, quindi non c'e' invocazione dinamica.
8. `brain/knowledge_store.py:336-347` — `expenses_by_category()`: nessuna aggregazione delle spese
   viene mai calcolata, pur essendo `kind='expense'` accettato e la categoria «Spese» offerta dalla
   UI.
9. `proxy/knowledge_db.py:87-94` — `add_annotation()` e la tabella `entity_annotations`: le
   annotazioni sono **lette** e stampate nel contesto della chat
   (`semantic_context_map.py:376-380`), ma nessun codice di produzione le scrive: la riga «[Nota:
   ...]» non puo' mai comparire.
10. `proxy/knowledge_db.py:26-43` — tabelle `entity_correlations` e `query_patterns`: create a ogni
    avvio, mai nominate da alcuna query (file letto per intero).
11. `api/handlers_knowledge.py:111-161` e la rotta `POST /api/knowledge` (`server.py:2836`) —
    `handle_manual_add`: unico modo di inserire conoscenza gia' approvata senza passare dal modello;
    nessuna interfaccia lo usa e non e' raggiungibile dal gateway (`manual_add` non e' un nome di
    strumento).
12. `api/handlers_proposals.py:25-33` e la rotta `server.py:2826` — `handle_get_proposal`: nessuna
    vista chiama il dettaglio di una proposta; le liste portano gia' l'oggetto completo.
13. `api/handlers_gateway_policy.py:215-225` — `notify_service_for_user`: definita, citata nella
    docstring di `notify()` come esempio d'uso, mai importata dalla produzione. *Voce doppia nel
    registro.*
14. `chatbot_engine.py:378-401` — `_build_entity_context`: costruisce il blocco di contesto con i
    delimitatori di dati non affidabili; unici riferimenti la definizione e quattro test.
15. `chatbot_engine.py:101` e `:125-126` — `set_task_engine` e `self._task_engine`: assegnati e mai
    letti; la catena viva passa da `claude_runner.py:542-543` al dispatcher.
16. `api/handlers_brain.py:33` — `/api/brain/reasoning`: nessun chiamante nel frontend; il feed
    unificato produce anche voci di tipo proposta e segnalazione (`brain/feed.py:37-49`) che nessuna
    pagina chiede.

**Rami irraggiungibili o senza effetto**

17. `watcher/detectors.py:165-170` — il ramo che legge un override di severita' dalla
    configurazione: sul percorso Agentbot la configurazione e' sempre un dizionario vuoto
    (`guardian.py:115`, `server.py:538`), e la severita' viene comunque ricalcolata a valle.
18. `watcher/agentbot_runner.py:241` e `:368-372` — il valore di ritorno `woke`/`cooldown`/`cap`:
    entrambi i chiamanti lo scartano.
19. `watcher/situations.py:23` — il letterale `switch.x`: serve a derivare il dominio quando
    l'entita' non e' configurata, ma in quel caso l'azione cade sul ramo «senza entita'» e il
    dominio calcolato non viene mai usato.
20. `mqtt_publisher.py:145-182` — i rami `button` e `switch` di `_build_discovery_payload`: la
    pubblicazione costruisce i payload solo come sensori; i controlli sono stati dismessi e il
    residuo e' dichiarato nel commento.
21. `api/handlers_gateway_policy.py:138` — `full["version"] = 2`: scritto e mai consultato da alcuna
    lettura o migrazione.
22. `task_engine.py:321` — il tentativo di rimuovere un lavoro `task_expire_<id>` che non viene mai
    creato: la rimozione fallisce sempre e finisce in un blocco che registra a livello di debug.
23. `api/handlers_chat.py:385-388` e `hiris-chat-card.js:874` — la gestione dell'evento
    `discard_collected`: emesso solo dai backend compatibili con OpenAI, mai da Anthropic. Vivo per
    meta' delle installazioni. *Due voci del registro.*
24. `claude_runner.py:996` e `openai_compat_runner.py:1090` — il dizionario `structured` di
    `run_with_actions`: costruito come letterale e mai popolato; il commento dichiara che il parser
    che lo riempiva e' stato rimosso.
25. `chatbot_engine.py:644-650` — i campi `eval_status`, `notifica`, `params`, `action_taken` del
    registro delle esecuzioni: letterali nulli, tenuti solo per non rompere il disegno delle righe
    vecchie.
26. `chatbot_engine.py:466-467` — i parametri `context` e `trigger_fired`: nessun chiamante li passa
    piu', quindi il messaggio utente e' sempre `[Agent trigger: unknown]` e il campo del registro e'
    sempre «manuale».
27. `security/semaphore.py:126` — il parametro `service` di `gate_action`: obbligatorio e
    keyword-only, mai usato nel corpo; serve solo al chiamante per il log e per l'etichetta.
28. `static/config/proposals-route.js:37-44` — il ramo di ripiego per il caso in cui la funzione di
    caricamento non sia definita: gli script sono caricati staticamente prima del montaggio.
29. `static/chat/send.js:131` e `171` — `sendQuick`: gli unici chiamanti sono in un mockup non
    servito; nella pagina reale le chip usano il listener delegato.
30. `tools/memory_tools.py:5` — l'import di `Any` non usato.

**Superficie visibile ma non raggiungibile dall'utente**

31. `static/index.html:131-139` — i tre bottoni dell'intestazione con i rispettivi pallini numerici:
    nascosti come regola base e nascosti di nuovo dall'unica media query che li menziona. I loro
    gestori esistono e i pallini continuano a essere scritti.
32. `static/index.html:153` — `#conn-dot` nasce con testo e titolo «Connesso» ma e' visibile solo
    nello stato di anomalia.
33. `hiris-chat-card.js:666` — `_composerHeight`: inizializzato e mai piu' toccato.
34. `hiris-chat-card.js:1034` — la chiave `idle` senza alcuna regola di stile corrispondente: lo
    stato quasi sempre attivo usa lo stile base.
35. `hiris-chat-card.js:1034` e `1038` — la chiave `unavailable` e la classe `offline`: lo stato non
    e' mai prodotto dalla sorgente dati effettiva, che restituisce solo tre valori.
36. `hiris-chat-card.js:229` e `1144` — la pastiglia «in esecuzione»: popolata solo dalla prova
    manuale lanciata dall'editor; conversare non la tocca mai.
37. `hiris-chat-card.js:710-721` — il ramo che legge le entita' MQTT con lo schema di nomi dismesso:
    non si attiva, si finisce sempre nel ripiego a interrogazione HTTP. *Vedi la cautela in 10.2, voce 72.*
38. `hiris-chat-card.js:1041-1046`, `1151-1162`, `261-283` — l'intero sottosistema del budget:
    dipende da un campo che il dataclass ha perso.
39. `hiris-chat-card.js:776-779` e i cinque header `Authorization` che lo usano: nessun middleware o
    handler legge quell'intestazione.
40. `static/config/labels.js:47-55` — tre stati su sette mappano a stringa vuota: il chip resta senza
    colorazione. Difetto estetico dichiarato nel commento.
41. `static/config/proposals.js:120-128` — il ramo per un DOM in cui la riga non esiste: la funzione
    ora vive solo dove la riga c'e' sempre.

**Inerti per scelta dichiarata (rimuovere solo se si rinuncia al lavoro che presupponevano)**

42. `mcp/guard.py:20-25` — il kill-switch: `set_killed` non ha alcun attivatore; `server.py:1114-1120`
    dichiara che l'endpoint verra' dopo. *Due voci del registro (aree Gateway e Semaforo).*
43. `mcp/guard.py:18` e `27-28` piu' `server.py:2660` — il registro di controllo in memoria: fino a
    200 voci, nessun consumatore, perso a ogni riavvio. *Tre voci del registro.*
44. `tools/dispatcher.py:167-171` — `data_dir`: il commento dichiara che nessuno strumento lo legge
    piu' e che resta «per non rompere il cablaggio esistente».
45. `static/config/agentbot-editor.js:885-886` — il bottone «Test Run» nascosto per gli Agentbot:
    non esiste alcuna rotta «esegui ora» per loro.
46. `api/handlers_proposals.py:7` — i filtri `applied` e `rejected` accettati dal backend e non usati
    da alcuna superficie (la UI ha solo «in attesa» e «archivio»).
47. `proxy/dashboard_backups.py:195-237` e `132-192` — elenco e scarto degli snapshot: un solo
    consumatore ciascuno, e solo nel pannello della chat; ne' la pagina Proposte ne' l'anteprima
    della Dashboard li interrogano.
48. `tools/config_tools.py:169-176` — i valori di default che dichiarano l'origine MCP: l'unico
    chiamante che li usa e' quello del gateway; l'altro passa sempre entrambi i parametri.
49. `static/chat/onboarding.js:72`, `chat/theme.js:43`, `chat/sidebar.js:25` — funzioni esportate su
    `window` senza chiamanti esterni. Non e' codice morto, e' esposizione inerte.

**Difetti di igiene interna (non rimozioni, correzioni)**

50. `server.py:787` — `_AGENT_UNMEASURED_WARNED`: insieme globale che accumula chiavi e non viene
    mai svuotato; dopo il primo avviso per un agente, un guasto successivo resta muto per tutta la
    vita del processo.
51. `server.py:2443-2463` — la potatura della coda dei ragionamenti sta dopo l'uscita anticipata del
    suo lavoro: in una configurazione senza ponte attivo non viene mai eseguita. In quella
    configurazione, pero', nulla viene nemmeno accodato.
52. `api/handlers_chat.py:53-63` — `_bridge_on`: un varco che in produzione e' sempre vero, perche'
    la coda viene creata incondizionatamente. Serve solo ai test.
53. `server.py:1944-1949` — il lavoro chiamato «azzeramento del contatore» e' in realta' una
    potatura delle righe dei giorni passati: il contatore riparte da zero da solo al cambio di data.
54. `brain/learned_thresholds.py:97-99` — l'insieme dei rilevatori tarabili contiene un solo
    elemento, quindi il tetto di tarature per giro non puo' mai vincolare nulla.
55. `api/handlers_entities.py:11-12` e `42-43` — il limite di mille entita' nel percorso della
    revisione olistica, applicato senza alcun segnale: un suggerimento su un'entita' oltre la
    millesima verrebbe rifiutato come «non in inventario».
56. `brain/cognitive_loop.py:252-281` — l'intero percorso delle tracce delle azioni del Brain non
    produce nulla con la configurazione predefinita, e la sua assenza e' invisibile.
57. `BRAIN_SUGGEST_CAP`, `BRAIN_TUNE_CAP`, `HIRIS_HEALTH_SCAN_MINUTES` (`server.py:2331`, `2361`,
    `2425`) — lette dall'ambiente ma non esportate da `run.sh` ne' presenti in `config.yaml`: non
    sono configurabili dall'add-on.
58. `config.yaml:93` e `:125` — due opzioni senza traduzione in nessuna delle due lingue (confronto
    programmatico delle chiavi).
59. `static/config/chatbot-editor.js:710-713` — il commento allinea il timeout del frontend a un
    nome che non esiste in alcun file Python; il timeout reale ha un altro nome e non e' esportato.
60. `llm_router.py:288` — `simple_chat` sceglie fra Claude, OpenAI e Ollama e **omette OpenRouter**,
    a differenza della classificazione delle entita' che lo include: un'installazione con il solo
    OpenRouter attivo riceve «Nessun provider AI configurato» pur avendo un provider disponibile.
    Non e' inerzia, e' un difetto.
61. `chatbot_engine.py:36-43` e `421-464` — il meccanismo di attesa dopo un limite di richieste
    funziona, ma governa esclusivamente il pulsante di prova manuale, perche' la pianificazione
    autonoma dei Chatbot e' stata ritirata.
62. `security/semaphore.py:79-81` — `garage_door` non corrisponde a un dominio reale di Home
    Assistant e non e' fra le categorie configurabili: l'unico modo per farlo scattare sarebbe un
    identificativo di entita' che comincia per `garage_door.`.
63. `watcher/agentbots.py:358-362` — `off_after_min` viene validato e persistito anche su un'azione
    di notifica, dove non puo' avere effetto.
64. `watcher/guardian.py:22` e `54` — il ramo che legge la policy dal chiamante non viene mai preso,
    perche' l'override e' impostato subito dopo la costruzione e non torna mai nullo.
65. `tools/http_tools.py:192` e `236` — il parametro `agent_id` di `http_request` esiste solo per
    la riga di log: il dispatcher non lo passa (`tools/dispatcher.py:579-586`), quindi ogni riga di
    log della chiamata HTTP dice `agent=unknown`. La ricerca e' stata fatta su entrambi i file e
    nell'unica chiamata reale il parametro non compare.

---

## 10.2 Sospetto non verificato, o raggiungibile in condizioni non escluse — NON rimuovere

Per queste voci la ricerca non e' stata completata, oppure e' stata completata ma il ramo resta
raggiungibile da un percorso che l'analista non controlla (un client esterno, un modello che indovina
un valore, un archivio storico). **Rimuoverle sulla base di questo elenco sarebbe una rimozione
dedotta.**

66. `watcher/agentbots.py:43` e `:762-768` — la migrazione dal nome file precedente: nessun percorso
    di scrittura di quel nome esiste **nel repository attuale**, ma non e' stato stabilito se esista
    un'installazione che quel file lo abbia mai scritto. Rimuovendola si rompe l'aggiornamento di
    quelle installazioni, se esistono.
67. `task_engine.py:309-314` — il ramo dell'innesco `immediate`: nessun produttore nel codice lo
    scrive, ma **e' nella whitelist** di creazione, quindi un modello che lo indovina lo puo' usare, e
    il dizionario del frontend lo elenca fra i tipi reali. Non e' irraggiungibile.
68. `task_engine.py:419-421` — l'opzione «interrompi in caso di fallimento»: due sole occorrenze,
    entrambe nel motore, non documentata in alcuna descrizione di strumento e non scritta da alcun
    produttore — ma raggiungibile se il modello la inventa, e un test la esercita.
69. `tools/dispatcher.py:506` — l'alias `chatbot_id` per l'elenco dei task: il commento lo
    giustifica come compatibilita' verso «un client MCP esterno che ha imparato la vecchia chiave».
    E' per costruzione un ramo che nessun catalogo interno puo' attivare, **quindi non e' verificabile
    dal solo codice del repository**.
70. `static/chat/knowledge.js:47-55` — la mappa delle sette provenienze mentre la coda ne contiene in
    pratica una sola: l'analista dichiara di **non** aver verificato quali scrittori salvino in stato
    di attesa oltre a `save_knowledge`.
71. `static/chat/tasks.js:15` — il ramo che mostra risultato o errore: i campi esistono nella
    serializzazione, ma non e' stato verificato in quali stati vengano popolati, quindi non si puo'
    affermare quale dei tre rami si veda davvero.
72. `hiris-chat-card.js:710-721` (di nuovo, dal lato dell'incertezza) — non e' stato possibile
    stabilire, leggendo solo questo repository, quale identificativo di entita' Home Assistant generi
    davvero dalle pubblicazioni MQTT: non si puo' escludere al 100% che per certi nomi di Chatbot
    coincida per caso con quello che la card cerca. E se il broker non e' configurato, nessuna entita'
    esiste e il punto e' comunque privo di effetto.
73. `chat_store.py:34` — la stringa di errore fra i testi considerati tossici: non e' piu' raggiunta
    dal percorso corrente, ma **resta utile per le righe salvate da versioni precedenti**.
74. `api/handlers_execute.py:76-91` — `parse_execute_policy`: non e' del tutto inerte, il valore resta
    quando il file della policy e' assente o vuoto; diventa inerte non appena l'interfaccia Gateway
    viene usata una volta.
75. `config.yaml:99` — il livello di log **non e' inerte**, ha solo un effetto limitato: non tocca il
    server MCP interno ne' i log dello script di avvio.

---

## 10.3 Sospetto smentito — codice che sembra morto e non lo e'

Queste voci sono state controllate e il chiamante e' stato trovato. Sono qui perche' un lotto di
pulizia che le incontrasse le classificherebbe con ogni probabilita' come morte.

76. `tools/config_tools.py:70-74` — il ramo `kind='dashboard'` della normalizzazione: sembra
    irraggiungibile perche' lo schema ammette solo script e scene e il dispatcher rifiuta
    esplicitamente quel valore, ma e' chiamato dal percorso del gateway
    (`handlers_execute.py:303`) e la forma normalizzata e' riusata dall'applicazione delle proposte.
    *Due voci del registro.*
77. `tools/config_tools.py:123-143` — il ramo di sostituzione con snapshot: non raggiungibile dallo
    strumento di chat, **ma raggiunto** dall'applicazione delle proposte di plancia, dove la modalita'
    e' messa da chi propone.
78. `api/handlers_execute.py:297-311` — il ramo `create_ha_config`: non e' nel catalogo MCP, quindi
    il modello via gateway non puo' nominarlo, ma resta raggiungibile da qualsiasi chiamata
    autenticata con il token interno. **Non e' codice morto**: e' codice raggiungibile solo dal
    gateway remoto. *Tre voci del registro.*
79. `api/handlers_execute.py:199-201` — il ramo senza entita' bersaglio: **vivo**, e non e' contenuto
    da nulla oltre alla conferma umana (vedi reperto 13 della sezione 9).
80. `api/handlers_execute.py:255-270` — il filtro sulle azioni di un task: **vivo**, ma la sua
    copertura e' meta' di quella che il nome suggerisce, perche' non e' ricorsivo.
81. `tools/ha_tools.py:92-103` — il ramo di lettura diretta quando la cache e' assente: in produzione
    la cache c'e' sempre, ma il ramo resta raggiungibile per chiamanti diretti dello strumento, e la
    docstring lo dichiara come percorso legittimo mantenuto apposta.
82. `proxy/ha_client.py:371-373` — `_is_slug`: **vivo**, chiamato dalla creazione di script e scene.
    La sua regola e' pero' piu' permissiva della validazione a monte, perche' accetta caratteri
    Unicode non ASCII.
83. `proxy/ha_client.py:583-603` — `_health_value`: **vivo**, ma il valore che finisce nello snapshot
    puo' essere la parola «pending» invece di un dato.
84. `proxy/ha_client.py:640-641`, `666-668` — il ritaglio delle ore del registro eventi: non puo' mai
    attivarsi dal percorso reale perche' la validazione a monte rifiuta prima. E' dichiaratamente
    difensivo, non morto per errore.
85. `security/semaphore.py:160` — il ritorno finale «Tier non riconosciuto: bloccato per sicurezza»:
    irraggiungibile dai percorsi normali perche' i livelli sono filtrati a monte; resta raggiungibile
    se qualcuno costruisce il perimetro a mano. E' l'ultima rete di un fail-closed.
86. `proxy/entity_cache.py:172-180` — `get_all()`, `get_all_states()`, `all_states()`: **nessuno e'
    inerte** (rispettivamente una riga di log, la mappa semantica, le entita' e la scansione di
    salute), ma la duplicazione e' reale.
87. `server.py:2596-2599` — le quattro chiavi delle credenziali e del modello locale: **lette** da
    `handlers_models.py`. Il sospetto e' esplicitamente smentito.
88. `api/handlers_tasks.py:5-10` e `task_engine.py:218` — l'alias di retro-compatibilita': **letto**
    dal frontend (`tasks-route.js:42`) e pinnato da tre test.
89. `hiris-chat-card.js:669` e `1461` — l'elemento di configurazione e la registrazione dell'editor:
    **verificati attivi** da `tests/js/chat-card.test.mjs:52-56`.
90. `server.py:2802` — `GET /api/chat/reply/{job_id}`: non e' inerzia ma un buco di controllo —
    nessuna verifica che il lavoro chiesto appartenga al chiamante; l'unica barriera e' quella dei
    middleware, la stessa per tutti gli utenti.
91. `api/handlers_gateway_policy.py:120-130` — `settings.notify_users`: non e' inerte, e' il perno del
    canale privato; e' **non impostabile da alcuna interfaccia** (vedi reperto 1 della sezione 9).
    Rimuoverlo significherebbe rinunciare allo step-up; implementarlo significherebbe farlo
    funzionare.
92. `watcher/agentbots.py:355-357` — `action.message` su un'azione di servizio: il backend lo valida
    e lo persiste, e la funzione a valle lo **userebbe**; e' l'editor che lo cancella a ogni
    salvataggio (vedi reperto 43 della sezione 9). Il codice morto qui e' un dato perso, non un ramo
    da togliere.

---

### Nota di riconciliazione

Le voci numerate qui sono **92** a fronte delle **104** del registro, e il conto chiude:

- **dodici** voci del registro sono state assorbite da **nove** voci di questa sezione, dichiarate
  voce per voce (voci 1, 2, 4, 13, 23, 42, 43, 76, 78). Due di quelle dichiarazioni erano sbagliate
  nella taglia e sono state corrette: la voce 4 assorbe tre testate e non due, la voce 42 ne assorbe
  due e non tre.
- **una** voce del registro e' presentata due volte, alle voci 37 e 72: la stessa riga di
  `hiris-chat-card.js` sta sia fra i candidati alla rimozione sia fra i sospetti non verificabili, e
  lo sdoppiamento e' dichiarato in entrambe le direzioni.
- **una** voce del registro — `server.py:467`, la chiave `otp_sent` calcolata e restituita da
  `request_confirmation_stepup` e mai letta da nessun chiamante (`dispatcher.py:213` guarda solo
  `id`, `task_engine.py:494-497` solo la verita' del dizionario) — e' stata trattata alla voce 54
  della sezione 9 invece che qui. Chi lavora su questo elenco per il lotto D non la incontrera':
  va ripresa da li'.

`104 − 12 + 1 − 1 = 92`.

La voce 65 (`tools/http_tools.py:192` e `236`) era presente nel registro e mancava da questa
sezione: e' stata reinserita.

---

# 11. Cosa non siamo riusciti a stabilire

Il registro delle incertezze contiene **111 voci**. Sono qui raggruppate per **causa
dell'incertezza**, perche' la causa determina cosa serve per chiuderla: alcune si chiudono
eseguendo il codice, altre leggendo un altro repository, altre ancora solo osservando un'installazione
reale.

Vale una premessa che ricorre in dodici voci, una per ogni area analizzata, e che va detta una volta
sola: **nessun analista ha eseguito il sistema.** Tutte le affermazioni di questo documento derivano
dalla lettura del codice sul branch `feat/coerenza`. L'unica eccezione registrata e' la validazione
degli endpoint HTTP, verificata eseguendo la funzione (reperto 29 della sezione 9). Latenze,
contenuto effettivo delle risposte, comportamento reale dei fornitori e degli scheduler non sono
stati osservati.

---

## 11.1 Contraddizioni aperte fra due letture dello stesso codice

Sono le uniche incertezze che si chiudono **dentro** questo repository, e vanno chiuse per prime.

1. **Il «Test Run» di un Chatbot funziona o fallisce sempre?** La mappa dell'area chat descrive un
   percorso funzionante (`chatbot_engine.py:483-541, 557-576`); la mappa del catalogo degli
   strumenti sostiene che la chiamata non puo' riuscire perche' passa un parametro che nessun runner
   accetta, e che l'utente riceve sempre «Tutti i provider AI non disponibili»
   (`chatbot_engine.py:520-541`, `llm_router.py:215-234`). Le due letture citano gli stessi
   intervalli di righe e sono incompatibili. Si risolve premendo il pulsante.
2. **Chi scrive la risposta differita nella memoria di chat?** Una mappa indica
   `api/handlers_reasoning.py:34-53`, l'altra `server.py:2211-2245`. Concordano sul comportamento —
   la scrive chi risolve il lavoro accodato — ma indicano due punti diversi, e non e' stato
   stabilito se siano due anelli della stessa catena.
3. **Il ramo «chat via abbonamento» ha strumenti oppure no?** Una lettura afferma che il contesto
   passato al processo esterno ha tre soli campi e che quindi «non c'e' nessuna memoria, nessun
   tool» (`handlers_chat.py:94-98`); un'altra descrive il lavoratore che lancia il processo con una
   propria lista di strumenti MCP (`agent/runner.py:25-32`, `mcp/local_client.py:35`). Si conciliano
   se si intende che il *lavoro accodato* non porta strumenti mentre il *processo* ne ha una propria
   lista; ma la prima, presa alla lettera, dice qualcosa di piu' forte.
4. **La conoscenza scritta da fuori esiste o no?** Una lettura riporta che l'MCP non espone alcuno
   strumento di memoria; un'altra descrive in dettaglio cosa succede quando dal gateway arrivano
   richieste di salvataggio e richiamo (`dispatcher.py:681-707`, `knowledge_tools.py:119`). La
   conciliazione probabile e' che «memoria» e «conoscenza» siano due famiglie distinte e che solo la
   seconda attraversi quel confine — ma le due mappe usano lo stesso vocabolario per cose diverse, e
   questo di per se' descrive bene il prodotto.
5. **Che cosa fallisce davvero l'invio di una notifica?** Due mappe leggono la funzione come capace
   di fallire e dichiararlo (`handlers_gateway_pending.py:222-230, 252-254`), una terza la legge al
   contrario — ignora il valore di ritorno e restituisce comunque successo, mentre la chiamata
   sottostante ritorna falso senza sollevare (`ha_client.py:187-196`). Concordano sui casi
   macroscopici, divergono sul caso piu' comune: notifica accettata dal codice e rifiutata da Home
   Assistant. Sulle conseguenze pratiche concordano, perche' nessun chiamante di produzione guarda
   quel valore.
6. **Quanti strumenti espone davvero il server MCP?** Una mappa parla di 13 strumenti
   (`mcp/tiers.py:21-129`) ma ne elenca quindici per nome nello stesso punto, e altrove dice che
   l'allowlist del CLI e' limitata a tredici (`agent/runner.py:24-36`). Il numero resta ambiguo.
7. **Che cosa garantisce l'etichetta «ingress»?** Non e' un disaccordo sul codice — le mappe
   descrivono le stesse righe — ma sulla portata della garanzia: «un umano dentro l'interfaccia» per
   due mappe, «intestazione di forma giusta piu' IP nella rete Docker degli add-on» per la terza.
8. **Riferimenti puntuali divergenti.** Le stesse entita' sono citate con estremi di riga
   leggermente diversi da mappe diverse: l'insieme degli strumenti di sola valutazione come
   `claude_runner.py:225-253` e come `:225-244`; la chiamata al modello come `handlers_chat.py:419` e
   come `:424`. Sono scostamenti di poche righe che non cambiano il comportamento descritto, ma
   indicano che i riferimenti vanno riverificati prima di essere usati come citazioni definitive.
9. **L'eliminazione di un Chatbot ripulisce la preferenza locale della chat?** Una mappa se lo
   chiede, l'altra descrive l'eliminazione (`static/config/chatbot-editor.js:771-794`) e non
   menziona alcuna pulizia. Se la lettura e' completa, la chat continuerebbe a puntare a un Chatbot
   che non esiste piu'. Nessuna delle due lo afferma.

---

## 11.2 Cio' che non e' in questo repository

**Il gateway MCP remoto.** E' un progetto separato. Cinque voci del registro (aree Catalogo,
Proposte, Gateway, Semaforo, Memoria) dichiarano lo stesso limite: non e' possibile dire quali
strumenti invii davvero all'endpoint di esecuzione, quali etichette di origine dichiari, come
autentichi i propri client, se presenti o meno l'intestazione che esenta dalla denylist di lettura,
come gestisca la forma diversa delle risposte di errore, ne' se raggiunga `create_ha_config`. Tutto
cio' che questo documento dice della superficie remota deriva da **cosa `/api/execute` accetta**, non
da cosa il gateway manda.

**Home Assistant e il Supervisor.** Un gruppo di voci riguarda comportamenti che vivono fuori dal
codice di HIRIS e che nessuna lettura statica puo' chiudere:

- la forma reale del payload dell'evento `entity_registry_updated`: se contenesse il nome amichevole,
  il reperto 140 della sezione 9 non si manifesterebbe;
- se l'ingress sovrascriva sempre l'intestazione `X-Remote-User-Id` (`brain/identity.py:6`); **tre
  voci indipendenti** lo registrano, e la conseguenza e' pesante in due direzioni opposte: se
  quell'intestazione non arriva, tutto diventa `owner='home'` e l'intero scoping per utente e'
  inerte; se arriva e non e' sovrascritta, la sceglie il chiamante;
- se il servizio di notifica predefinito dei pending del gateway supporti le azioni: senza,
  i pulsanti Approva e Nega non comparirebbero e l'unica via resterebbe la pagina Approvazioni;
- se il tocco su «Approva» nella app Companion richieda lo sblocco del telefono
  (`handlers_gateway_pending.py:190-203` non imposta il campo relativo) e se Home Assistant
  restringa a monte chi puo' emettere l'evento corrispondente;
- il comportamento reale dei collegamenti profondi su iOS e Android
  (`notify_tools.py:29-50, 53-67` sono affermazioni dei commenti, non fatti leggibili nel codice);
- quale identificativo di entita' Home Assistant generi dalle pubblicazioni MQTT;
- se un flusso di eventi sopravviva all'attraversamento del proxy di ingress del Supervisor;
- quale politica di sicurezza dei contenuti Home Assistant applichi alle proprie dashboard, dove gira
  la card, che carica un foglio di stile da un dominio esterno (`hiris-chat-card.js:17`);
- la forma reale degli oggetti interni del frontend di Home Assistant letti dalla card
  (`hiris-chat-card.js:776-779`, `:772`).

**Le librerie.** Quattro comportamenti dipendono dalle versioni installate e non sono stati
verificati leggendone il sorgente:

- APScheduler: il valore predefinito del numero massimo di istanze concorrenti — da cui dipende
  l'affermazione, scritta in un commento (`server.py:2043`), che le esecuzioni di uno stesso
  agente-obiettivo non si sovrappongano — e il comportamento su un lavoro con data gia' passata al
  momento della registrazione, caso che si presenta a ogni riavvio per un task scaduto durante lo
  spegnimento (`task_engine.py:240`). Nel primo caso il task recupera, nel secondo resta in attesa
  per sempre: il codice di HIRIS non gestisce esplicitamente nessuno dei due;
- aiohttp: se la riassegnazione di una chiave dell'applicazione dopo l'avvio sollevi o produca solo
  un avviso (rilevante per `handlers_models.py:174`), e se ignori davvero le intestazioni impostate
  su una risposta in streaming gia' preparata (rilevante per il reperto 26 della sezione 9);
- FastMCP: come traduce esattamente la firma degli handler in schema JSON (rilevante per il reperto
  144);
- `jq`, non installato esplicitamente nel Dockerfile: se mancasse, l'elenco degli indirizzi Apprise
  diventerebbe sempre vuoto e la denylist di lettura cadrebbe sempre sul default. E `apprise`:
  se sollevi su indirizzi non validi, l'eccezione risalirebbe fino al blocco generico del
  dispatcher.

**Il deployment.** La raggiungibilita' effettiva della porta 8099 fra container nella rete del
Supervisor non e' stata provata: e' la prova che manca per trasformare il reperto 4 della sezione 9
da lettura di codice a fatto. Nella stessa famiglia: se la dichiarazione della porta impedisca solo
la pubblicazione verso l'host o anche il traffico fra container; quale fuso orario erediti il
container, da cui dipende l'effetto pratico dei due orologi del motore dei task; se le variabili
della posizione geografica siano esportate all'avvio; se il Supervisor scriva sempre i valori
predefiniti nelle opzioni, da cui dipende se il default protettivo della denylist sia mai realmente
raggiunto; se MQTT sia configurato negli ambienti reali.

---

## 11.3 Cio' che non abbiamo guardato

**Il comportamento normale, in senso proprio.** Due mappe indipendenti dichiarano di non sapere in
quali condizioni il percorso «chat via abbonamento» sia attivo (`server.py:1412`, `2495-2499`), e ne
traggono la conseguenza piu' scomoda di tutto il documento: **nessuna delle due letture e' in grado
di dire quale sia il comportamento normale di invio di un messaggio in un'installazione reale**, se
la risposta immediata o l'accodamento. Nella stessa famiglia: quale sia lo stato di attivazione
reale delle opzioni dell'abbonamento e del ponte, e quale identita' arrivi al dispatcher su quel
ramo — da cui dipende se lo step-up sia raggiungibile da li'.

**Aree lette solo in superficie.** Il registro dichiara esplicitamente i confini: 44 dei 64 handler
HTTP sono stati catalogati come punti d'ingresso senza seguirne i flussi interni; l'intera
validazione degli Agentbot (oltre 250 righe) non e' stata letta per intero, quindi non e' possibile
elencare tutte le forme che fanno fallire l'applicazione di una proposta; il dispatcher (786 righe)
e' stato letto sul semaforo, sul filtro dei servizi e sulla gestione degli errori, non strumento per
strumento; il modulo di frammentazione dei documenti e il client dell'archivio documentale non sono
stati aperti; le proprieta' di quattro archivi (segnalazioni, proposte, storico, snapshot delle
plance) sono riportate come dichiarate dai commenti dei moduli che li usano, non verificate; i
prompt di sistema non sono stati confrontati con le descrizioni degli strumenti.

**I test come fonte.** Piu' voci dichiarano di non aver ispezionato la suite se non per confermare
un punto specifico, e di **non** aver usato i test come fonte del comportamento. E' una scelta
metodologica corretta ma lascia aperta una possibilita': che qualche test documenti intenzioni o
vincoli che contraddicono cio' che e' stato dedotto.

**Concorrenza e integrita' dei file.** Nessuna delle voci sulla concorrenza e' stata verificata: due
mutazioni simultanee delle regole, con la registrazione dei lavori eseguita fuori dal lock; due
processi che scrivono la coda dei pending, che non usa alcun lock; la finestra di corsa fra
l'esecuzione di un task e la pulizia periodica; la divergenza possibile fra il perimetro visto dal
pre-screening e quello visto dal dispatch dentro la stessa richiesta, se la policy viene salvata nel
mezzo. In tutti questi casi l'analisi dice che *il codice non si difende*, non che il danno accada.

**Dettagli di comportamento non seguiti fino in fondo.** Un residuo di voci puntuali, elencate qui
perche' chi legge non le dia per risolte: se il dispatcher possa sollevare invece di restituire un
errore nel ramo della chiamata di servizio (cambierebbe l'esito del reperto 52); se l'archivio della
conoscenza tratti un vettore vuoto come nullo, da cui dipende se gli insight scritti senza vettore
siano o meno richiamabili; come venga popolato il modello del Brain e cosa succeda se punta a un
modello non attivo; quanto costi la ricerca semantica, che carica in memoria tutte le righe che
passano il filtro e calcola la similarita' in Python; se esista una potatura della tabella degli
eventi della Sentinella; se esista un percorso che rimuova entita' dalla cache all'infuori del
riavvio; se e come la coda delle approvazioni si aggiorni da sola mentre la pagina e' aperta; quanto
spesso scatti in pratica il blocco per forma di risposta non riconosciuta della denylist di lettura;
quali conseguenze abbia un'etichetta di origine scelta ad arte sul filtro dell'elenco dei task; se
esistano in produzione righe con un tipo di proposta non gestito; se qualche percorso scriva
direttamente nell'archivio delle proposte scavalcando la validazione; se un valore di sensibilita'
diverso dai due previsti arrivi mai davvero nei dati; se la migrazione dello schema del database
regga su un archivio creato prima della versione 2; se il copia negli appunti funzioni dentro un
albero isolato; come l'API di Anthropic tratti due messaggi consecutivi dello stesso ruolo,
situazione che si produce quando un turno resta senza risposta; se le risposte del modello contengano
markdown oltre ai tre costrutti che la pagina sa disegnare; e infine se esista una superficie, dentro
HIRIS, che segnali all'utente le opzioni incoerenti — token vuoto, porta spostata — perche' le rotte
di diagnostica non sono state lette tutte.

---

*Fine del documento.*
