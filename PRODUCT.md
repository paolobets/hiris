# Product

> ## 🗄 Documento storico — 10 agosto 2026
>
> **Questo documento descrive il prodotto pre-2.0, e non è più una fonte di verità su nulla.**
> È conservato come documento storico: si legge per sapere cosa HIRIS *voleva* essere prima del
> Refactor 2.0, non per sapere cosa fa oggi. Non è stato riscritto — un verbale non si riscrive,
> si annota — e questo blocco è l'annotazione.
>
> **La fonte viva è** [`docs/design/2026-08-04-scope-hiris.md`](docs/design/2026-08-04-scope-hiris.md),
> che dichiara esplicitamente di sostituire questo documento (§0, «Il documento sbagliato era
> quello, non il codice. Questo lo sostituisce»). Per cosa il prodotto fa *davvero* oggi, il
> `README.md`.
>
> **Cosa questo documento afferma e che non è più vero.** Tutto il corpo qui sotto parla al
> presente di cose uscite dal prodotto fra le fette E2, E3 ed E4: le tre entità **Chatbot ·
> Agentbot · Brain** (§ *Product Purpose*), il **semaforo** davanti alle azioni, le **proposte**
> del Brain, la **sandbox** come first-class e la **telemetria per-entità** come criteri di
> successo (§ *Design Principles* 2 e 3), il **budget token per-chatbot** (§ *Product Purpose*)
> e il costo cumulativo sempre a schermo (§ *Design Principles* 5), il **pannello di
> configurazione delle entità AI**
> come definizione stessa del prodotto (§ *Users*, § *Product Purpose*). HIRIS 2.0 è una
> riduzione al nucleo: **conosce e non agisce** — la conoscenza della casa più una chat per
> interrogarla, con quattro strumenti che leggono e ricordano, e nessuno che tocchi la casa.
>
> **Anche il blocco del 4 agosto qui sotto è superato**, su due punti verificati sul codice:
> (1) non è una supersessione *parziale* di tre sezioni — è l'intero documento a descrivere un
> prodotto che non esiste; (2) la frase «costruisce ciò che serve — oggetti standard di Home
> Assistant … **agenti** quando serve giudizio» descrive la visione dello scope, non la 2.0
> pubblicata, che non costruisce né oggetti HA né agenti. Resta qui sotto invariato, per lo
> stesso motivo per cui resta il corpo: è il verbale di quel giorno.
>
> Ciò che di questo documento resta utile è il **registro visivo e l'accessibilità** —
> *Brand Personality*, *Anti-references*, *Accessibility & Inclusion* — che descrivono un'identità
> grafica e dei vincoli d'uso, non un perimetro funzionale. Vanno comunque riletti contro il
> prodotto vero: nominano superfici (sandbox, editor Agentbot, telemetria per-entità) che non
> ci sono più.

> ## 🗄 Annotazione all'annotazione — 12 agosto 2026
>
> Il blocco del 10 agosto qui sopra è **anch'esso un verbale**, e non è stato riscritto: si
> annota, come tutti gli altri. Una sua frase ha smesso di essere vera. Diceva che HIRIS 2.0
> è *«una riduzione al nucleo: **conosce e non agisce** — la conoscenza della casa più una chat
> per interrogarla, con quattro strumenti che leggono e ricordano, e nessuno che tocchi la
> casa»*.
>
> Era vero il 10 agosto. Con la fetta **«comandare»** l'azione è rientrata: gli strumenti della
> chat sono **cinque**, e il quinto (`esegui`) chiama i servizi di Home Assistant passando da un
> unico punto che verifica prima e rilegge lo stato dopo (`hiris/app/azione/porta.py`). Ciò che
> resta vero, e che separa questa 2.0 dal prodotto descritto nel corpo del documento, è il resto:
> nessuna autonomia — ogni esecuzione nasce da una frase in chat — e nessun semaforo, che non è
> tornato con lei. Per cosa il prodotto fa davvero oggi, il `README.md`.

> ## 🗄 Annotazione — 23 agosto 2026
>
> Il blocco del 12 agosto qui sopra è a sua volta superato su un numero, per lo stesso motivo per
> cui lui stesso supera il 10: non si riscrive, si annota. Diceva che *«gli strumenti della chat
> sono **cinque**, e il quinto (`esegui`) chiama i servizi di Home Assistant»*.
>
> Era vero il 12 agosto. Da allora il catalogo è cresciuto per tappe, e dalla fetta **«costruire»**
> gli strumenti della chat sono **undici** (`hiris/app/casa/strumenti.py`). `esegui` continua a
> chiamare i servizi passando dalla stessa porta di allora (`hiris/app/azione/porta.py`);
> `costruisci` e `conferma`, in coppia, scrivono **configurazione** — automazioni, script, scene —
> passando da un secondo canale che verifica e rilegge come il primo ma non lo sostituisce, l'officina
> (`hiris/app/azione/costruzione/officina.py`). Questo tocca anche il blocco del 4 agosto qui
> sotto: dove dice che la 2.0 pubblicata «non costruisce né oggetti HA né agenti», la prima metà
> ha smesso di essere vera — HIRIS costruisce oggetti Home Assistant dalla fetta «costruire»; resta
> vero che non costruisce agenti. Per cosa il prodotto fa davvero oggi, il `README.md`.

> ## 🗄 Annotazione — 24 agosto 2026
>
> Il blocco del 23 agosto qui sopra è a sua volta superato su un numero, per lo stesso motivo per
> cui lui stesso supera il 12: non si riscrive, si annota. Diceva che *«dalla fetta «costruire»
> gli strumenti della chat sono **undici** (`hiris/app/casa/strumenti.py`)»*.
>
> Era vero il 23 agosto. Con la fetta **«HIRIS e il tempo»** gli strumenti della chat sono
> **tredici**. Gli ultimi due, `andamento` e `accaduto`, guardano INDIETRO nel tempo passando
> sempre da Home Assistant, senza un archivio proprio: come è andato un valore nel tempo (una
> temperatura, un consumo), e cosa è successo in casa e per mano di chi, quando si può dirlo. Ciò
> che resta vero è il resto del blocco del 23 agosto qui sopra: due canali di scrittura
> (`hiris/app/azione/porta.py` per i servizi, `hiris/app/azione/costruzione/officina.py` per la
> configurazione), nessuna autonomia, nessun semaforo. Per cosa il prodotto fa davvero oggi, il
> `README.md`.

> ## 🗄 Annotazione — 25 agosto 2026
>
> Il blocco del 24 agosto qui sopra è a sua volta superato su una parola, per lo stesso motivo per
> cui lui stesso supera il 23: non si riscrive, si annota. Diceva *«nessuna autonomia, nessun
> semaforo»*, come se le due cose fossero ancora vere insieme.
>
> Resta vero che non c'è un semaforo. Non è più vero, da tre fette (la fetta «schedulare»), che
> non ci sia autonomia: lo schedulatore delle promesse (`hiris/app/keeper/sweeper.py`,
> battito ogni 15 secondi) esegue una promessa `fai` da solo, ore dopo la frase che l'ha creata e
> senza nessuno in chat, passando dalla stessa porta di `esegui`; e una promessa `chiedi` con
> recapito manda una notifica sul canale `notify.*` scelto, fuori dalla chat. Non è un giudizio
> che nasce da solo — il *cosa* e il *quando* li ha decisi una frase dell'utente — ma è un'azione
> reale sulla casa e un messaggio reale che può arrivare mentre l'utente dorme, e chiamarlo
> «nessuna autonomia» senza qualificarlo è la stessa frase falsa che il README ha appena corretto
> (`README.md`, sezione «What HIRIS 2.0 is»). Per cosa il prodotto fa davvero oggi, il `README.md`.

> ## 🗄 Annotazione — 2 settembre 2026
>
> I blocchi qui sopra nominano gli strumenti della chat col loro nome di allora — `esegui`,
> `costruisci`, `conferma`, `andamento`, `accaduto`. **Non si riscrivono, si annotano**, per la
> stessa regola con cui il 24 agosto annota il 23: sono verbali, e un verbale dice cosa era vero il
> giorno in cui è stato scritto.
>
> Con la fetta **«la rinomina»** i quattordici nomi che il modello legge sono passati all'inglese, e
> chi provasse a chiamarne uno con la grafia di questi blocchi riceverebbe «non è fra quelli
> disponibili». La corrispondenza, una volta sola:
>
> `cerca`→`search` · `guarda`→`view` · `legami`→`related` · `ricorda`→`remember` ·
> `richiama`→`fetch` · `esegui`→`execute` · `prometti`→`promise` · `promesse`→`agenda` ·
> `disdici`→`cancel` · `costruisci`→`propose` · `conferma`→`confirm` · `andamento`→`trend` ·
> `accaduto`→`logbook` · `concludi`→`conclude` (il quattordicesimo vive solo nel turno di una
> promessa, non in chat).
>
> Ciò che **non** è cambiato, e va detto perché è la domanda che nasce guardando questa tabella:
> le descrizioni che il modello legge restano in italiano — il prodotto parla italiano — e così le
> chiavi degli argomenti. È cambiato il nome con cui lo strumento si chiama, non la lingua in cui
> parla. Le ragioni riga per riga stanno in `docs/GLOSSARIO.md`, «I nomi degli strumenti»; l'elenco
> vivo, con cosa fa ciascuno oggi, nel `README.md`.

> ## ⚠️ Documento parzialmente superato — 4 agosto 2026
>
> Le sezioni **Users**, **Product Purpose** e **Design Principles** sono **superate** dal
> **Refactor 2.0**: `docs/design/2026-08-04-scope-hiris.md`.
>
> Descrivevano HIRIS come *«un pannello di configurazione delle entità AI»* — un workbench con
> sandbox, eval e telemetria per-entità come criteri di successo. Quel prodotto non è mai stato
> costruito: mesi di sprint sono andati tutti verso l'assistente e il cervello proattivo, nessuno
> verso la sandbox. Il documento sbagliato era questo, non il codice.
>
> **HIRIS è l'intelligenza della casa**: sa tutto ciò che della casa si può sapere, impara, e
> costruisce ciò che serve — oggetti standard di Home Assistant quando basta il determinismo,
> **agenti** quando serve giudizio.
>
> **Restano pienamente validi** e non sono toccati dal refactor:
> **Brand Personality** · **Anti-references** · **Accessibility & Inclusion**.
>
> Le sezioni superate sono conservate qui sotto perché il registro visivo che ne discende
> (densità, tono, tipografia) resta corretto anche se la definizione di prodotto è cambiata.

## Register

product

## Users

**Primario — il tinkerer Home Assistant.** Adulto tecnico, già padrone di YAML, automazioni, integrazioni HA. Installa HIRIS come add-on, lo apre via Ingress sul desktop (1440px+), passa la maggior parte del tempo nel **pannello di configurazione** a comporre Chatbot e Agentbot, scrivere prompt/contratti, scegliere tool e permessi, definire trigger, controllare costi — e a rivedere le proposte del Brain (nuovi Agentbot, automazioni HA, modifiche di configurazione). Vuole controllo, densità, telemetria, niente paternalismo. Sa già cos'è un cron, un MQTT, un token.

**Secondario — chiunque viva nella casa.** Famiglia, ospiti, partner non tecnico. Non aprono mai il pannello di configurazione: usano i **Chatbot** da una card Lovelace o dal pannello chat di HIRIS. Chiedono in linguaggio naturale, ricevono risposte in linguaggio naturale. La superficie chat deve essere accessibile a tutti senza istruzioni.

**Contesto d'uso:** HA add-on aperto via Ingress, soprattutto da desktop in sessioni di lavoro lunghe (configurazione, debug, eval). La chat anche da mobile / Lovelace card.

## Product Purpose

HIRIS (Home Intelligent Reasoning & Integration System) è un **pannello di configurazione delle entità AI** di casa, attorno a un fulcro che ragiona ed evolve da solo: il **Brain**. Attorno al Brain vivono due tipi di entità, con comportamento inequivocabile:

- **Chatbot** — conversazionale, a interrogazione (chiedi → risponde). Prompt libero (persona/verticalità); legge HA liberamente, le azioni passano dal semaforo. Creato dall'utente.
- **Agentbot** — autonomo: agisce o segnala **da solo**, su un trigger (cron / interval / evento), senza che tu chieda. Contratto a **verdetto** (JSON); azione dichiarata; **niente tool liberi** (pilastro di sicurezza). Nasce da una **proposta del Brain** oppure creato a mano dall'utente.
- **Brain** — il fulcro: ragiona, traccia le abitudini della casa, e **propone** (nuovi Agentbot, automazioni HA, modifiche di configurazione HA·HIRIS, evoluzioni) — preferendo segnalare-e-chiedere piuttosto che agire di testa propria.

Il Chatbot ha tool/permessi granted, budget token, modello LLM configurabile e memoria (accesso al second brain via `knowledge_access`). L'Agentbot no: coerente con "niente tool liberi" due righe sopra, non ha tool/permessi granted, non ha un budget e non ha una memoria propria — l'unico dial AI è il modello del ragionamento (`reasoning.model`), usato solo se `reasoning.enabled` è attivo (di default non lo è: molti Agentbot restano deterministici, zero LLM). Una volta configurate, le entità girano nel Python flow engine locale e chiamano il provider LLM scelto (Claude / OpenAI / OpenRouter / Ollama locale — più l'Abbonamento Claude Max via runner in-addon, oggi disponibile per il Chatbot) solo quando serve ragionare davvero.

Il successo è misurabile: l'utente apre l'editor di un Chatbot o di un Agentbot, lo modifica, lo testa nella sandbox, vede il costo e la latenza, lo deploya — oppure revisiona una proposta del Brain e la approva o rifiuta. La chat viene usata per parlare con i Chatbot o per verificare cosa farebbe un Agentbot. Niente dashboard di stato della casa, niente cruscotti di metriche: HA fa già quello.

## Brand Personality

**Tre parole:** preciso, tecnico, abitabile.

Il tono è quello dell'**Anthropic Workbench / OpenAI Playground / Claude Console** — uno spazio dove un adulto competente costruisce qualcosa di serio. Mono-leaning per il codice (system prompt, cron, tool refs), sans-serif raffinata per i comandi e le label. Densità informativa alta dove serve (sidebar Chatbot/Agentbot, telemetria), respiro generoso dove l'utente sta scrivendo (textarea del prompt, sandbox).

La palette esiste già nel repo: **iris** (viola petalo) come accento di brand, neutri tinted al viola in OKLCH, accenti semantici (ok / warn / err) sobri. Theme dual: chiaro per sessioni diurne, scuro per il workbench. Il dark non è un manifesto, è ergonomia.

Niente entusiasmo da SaaS, niente onboarding euforico, niente dashboard "ti mostro la tua casa." HIRIS rispetta il tempo del tinkerer: zero rumore, zero animazioni decorative, tutto ciò che si muove ha un significato (un Chatbot sta rispondendo, un Agentbot sta agendo, un costo sta salendo, un eval è cambiato).

## Anti-references

Cosa HIRIS non deve sembrare:

- **Editoriale / poetico / contemplativo.** Niente serif italic, niente "stanza che respira", niente pagina come carta di lettera. Quel registro è stato testato e rifiutato: HIRIS non è un assistente da accarezzare, è un workbench.
- **Dashboard di stato della casa.** Niente tile "Energia / Clima / Luci", niente metriche live della casa al centro della home. Quello lo fa Home Assistant. HIRIS configura Chatbot e Agentbot, non rende metriche.
- **SaaS marketing.** Niente hero gradient, niente "big number + small label + supporting stats", niente card grid identiche, niente onboarding in modale. Side-stripe borders vietati.
- **Voice assistant cute.** Niente bolle blu di iMessage, niente avatar tondo che pulsa con onde, niente "iris ti ascolta" con microfono animato. La chat è testo.
- **Generico Home Assistant cards UI.** Coerente con HA in densità e tipografia, ma con un'identità propria (palette iris, tipografia mono per il codice). L'utente deve riconoscere "questo è HIRIS, non un dashboard HA qualunque."

Anti-pattern visivi specifici da bandire (per absolute bans del design system):
- gradient text decorativo
- glassmorphism diffuso
- card identiche in griglia regolare
- modali come prima soluzione

## Design Principles

1. **Configurazione è scrittura.** Il fulcro dell'editor è il prompt: libero per il Chatbot, a contratto-verdetto per l'Agentbot — in entrambi i casi una textarea grande, monospaziata, con respiro. Tool / trigger / model sono al servizio del prompt, non lo nascondono.

2. **Telemetria dove serve la decisione.** Ogni Chatbot e Agentbot mostra costo / latenza / eval accanto alla propria configurazione — sessioni recenti per il Chatbot, trigger recenti per l'Agentbot — non in una pagina "Analytics" separata. Il tinkerer decide se cambiare modello o soglia *qui*, mentre edita.

3. **Sandbox è first-class.** Testare un Chatbot o un Agentbot è la stessa cosa che editarlo: REPL inline, scenari salvabili, output strutturato. Niente "deploy and pray".

4. **Densità dove c'è competenza, semplicità dove c'è famiglia.** Il pannello di configurazione è denso, mono, ricco. La chat è larga, sans, calma. Sono due UI diverse dello stesso prodotto, non lo stesso template ripetuto.

5. **Cost transparency permanente.** Il costo cumulativo di oggi e del mese è sempre visibile in alto, in mono, leggibile a colpo d'occhio. Niente sorprese di bolletta.

## Accessibility & Inclusion

- WCAG AA come minimo: contrasti ≥ 4.5:1 per testo body, ≥ 3:1 per UI ed eventuali large text.
- Operazioni full-keyboard: pannello di configurazione interamente navigabile da tastiera (sidebar, form, REPL). Comando palette `⌘K` per ricerca/azioni.
- Prefers-reduced-motion rispettato: pulse / blink disattivati, transizioni accorciate.
- Chat utilizzabile su mobile / Lovelace card, font ≥ 16px, target tap ≥ 44px.
- Theme dual chiaro/scuro con `prefers-color-scheme` di default; override manuale persistito.
- Niente comunicazione affidata al solo colore (status badge sempre con label testuale, non solo dot colorato).
