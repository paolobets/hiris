# BACKLOG — gli argomenti in attesa di uno sprint

Questo documento non e' storia: e' il **registro**. Ci si scrive quando nasce un argomento, ci si
legge quando si sceglie cosa fare. Non porta una data di redazione perche' non e' la fotografia di
un giorno: e' vivo.

**Sta in git, e non e' un accidente.** Il progetto aveva gia' avuto una `docs/ROADMAP.md`: e' stata
tolta dal tracciamento e messa in `.gitignore` il 30/04/2026 (commit `8c4d615d`), e oggi non esiste
piu' nemmeno sul disco. Un registro che git non vede e' un registro che nessuna sessione puo'
leggere, e sparisce senza che nessuno se ne accorga. Questo file non ha quella scusa: se una voce
non c'e', e' perche' nessuno ce l'ha scritta.

## Come ci si scrive

**Quando il proprietario dice «inseriamo per il prossimo sprint», la voce entra qui, subito**,
prima di continuare il discorso. Non in un appunto, non in una risposta in chat, non nella memoria
di una sessione: qui. Una voce annotata altrove e' una voce persa — ed e' gia' successo.

Una voce e' **atomica**: si deve capire cosa chiede senza andare a cercare altrove. Se il dettaglio
merita un documento, la voce lo nomina; se il documento non esiste, la voce dice «nessun documento»
e si porta dentro tutto cio' che serve a ricostruirla.

Ogni voce dichiara **da dove viene**. La provenienza non e' cortesia: distingue cio' che il
proprietario ha chiesto da cio' che e' emerso misurando, e le due cose non hanno lo stesso peso
quando si sceglie.

## Come si legge

Le voci stanno in tre stati, e lo stato e' **la sezione in cui la voce si trova** — non una colonna
che puo' restare indietro rispetto ai fatti.

| Stato | Vuol dire |
|---|---|
| **In attesa** | Nessuno l'ha ancora scelta. E' il magazzino da cui si pesca. |
| **Scelto** | Entra nello sprint in corso. |
| **Uscito** | Chiuso da un rilascio, che la voce nomina. Il dettaglio sta nel CHANGELOG. |

Una voce non si cancella quando esce: si sposta. Un backlog che dimentica cosa ne e' stato delle sue
voci non sa dire se il lavoro procede.

---

## Scelti — sprint in corso

### «Rifalla» manda davvero il giro sul ponte — aperta il 23/09/2026

`origine: il proprietario, durante la fetta 7 dello sprint sicurezza` · `rilascio: v3.64.0`

Con la 3.64.0 il bottone **«Rifalla»** dell'osservatore ha smesso di essere l'unica porta verso un
modello che non dichiarava chi risponde: adesso **lo dice**, con parole sue — «il piano non ha
fallito, e' la porta che risponde subito mentre il piano risponde in differita».

Dichiararlo non e' mandarcelo. Su una casa che gira sul Piano Max ogni «Rifalla» resta **a
consumo**, e ora si sa. Mandarlo davvero sul ponte e' una fetta sua e costa due cose: il bottone
**smetterebbe di rispondere subito** (il ponte risponde in differita) e la pagina dovrebbe
**interrogare** invece di ricevere. E' un cambio di come si comporta un bottone, non un
aggiustamento.

**Questa voce e' nata con un debito**: la decisione fu presa il 23/09 e dichiarata scritta qui,
e qui non c'era — il commit della 3.64.0 tocco' `docs/BACKLOG.md` per il solo rimando della CLI.
Se ne e' accorto il conto dei reperti fatto per chiudere lo sprint. Una decisione rimandata e non
tracciata e' la specie che torna.

### Retro Panel si accoppia e firma — FUORI dallo sprint sicurezza, aperta il 23/09/2026

`origine: la fetta 2 di docs/design/2026-09-21-i-canali-e-i-ruoli.md` · `due repository`

**Non chiude nessun rischio, e per questo esce dallo sprint.** La convivenza col segreto condiviso
e' finita su una MISURA e non su una data — il registro dell'add-on ha smesso di nominare chiunque
non firmasse — e da allora la porta e' chiusa per tutti. Quel che manca non e' una difesa, e' una
**capacita'**: finche' Retro Panel non si accoppia, non puo' piu' parlare con HIRIS.

Cosa serve: Retro Panel genera una coppia Ed25519 (la privata **non viaggia mai**), si presenta
nella finestra di dieci minuti che il proprietario apre dalla pagina Servizi, e il proprietario
approva il suo ruolo confrontando il codice a quattro cifre. Poi firma come firma la porta di
sviluppo: `X-HIRIS-Servizio` (la chiave pubblica, che e' l'identita'), `X-HIRIS-Momento`,
`X-HIRIS-Unico`, `X-HIRIS-Firma`, sul contratto di `api/canali.py::materia_firmata`.

### L'opzione `canali` e' rimasta nelle opzioni salvate dell'add-on — aperta il 23/09/2026

`origine: misurata sul registro della casa vera, 23/09/2026`

A ogni avvio il Supervisor scrive:

    WARNING [supervisor.apps.options] Option 'canali' does not exist in the schema for HIRIS

E' il **campo di testo dei canali** uscito dallo schema con la fetta 1b, quando i servizi hanno
smesso di dichiararsi in un'opzione e hanno cominciato a nascere da un accoppiamento approvato. Lo
schema non lo dichiara piu'; le opzioni **salvate** su questa casa si', e il Supervisor lo ignora e
tira dritto.

Non e' un'esposizione — quel valore non lo legge piu' nessuno. E' la **stessa specie di cosa** che
ha rotto l'aggiornamento della 3.64.0: un valore che chi lo legge non riconosce, dentro un avviso
che nessuno guarda. Si chiude togliendolo dalle opzioni dell'add-on nella pagina di
configurazione di HA — non c'e' niente da cambiare nel codice.

### `vault.db` e' stato cancellato senza poter dire cosa conteneva — aperta il 23/09/2026

`origine: misurata sul registro della casa vera, 23/09/2026` · `rilascio che l'ha prodotta: v3.64.1`

Al primo avvio dopo l'aggiornamento:

    [INFO] app.server: vault.db non si e' potuto leggere prima di cancellarlo
                       (OperationalError: no such table: pii)

Il codice si comporta bene: non trovando la tabella attesa **cancella lo stesso** — nessuno lo
leggeva piu' — e dichiara di non aver potuto contare invece di affermare uno zero che nessuno ha
misurato. Il lato di sicurezza e' a posto: quel file conteneva dati personali in chiaro e non c'e'
piu'.

Resta un difetto piccolo e vero: la riga di conferma esce **solo se il conteggio riesce**, quindi
il registro dice che non l'ha letto e **non dice che l'ha cancellato**. Chi legge lo deduce
dall'assenza di un errore, che non e' dire. E il file ora non c'e' piu': **cosa contenesse non lo
sapremo**, quindi la meta' informativa di quella fetta su questa casa non e' piu' verificabile.

### Zittire un'integrazione NUOVA dalla pagina — aperta il 20/09/2026

Con la 3.53.0 il proprietario corregge le **sei righe di `impalcatura` che il seme porta**, dalla
scheda «Cosa ho capito». Quello che non può ancora fare è **aggiungere una riga nuova**: se domani
una settima integrazione comincia a riempire il primo piano di rumore, il modulo di aggiunta di
quella pagina scrive solo `genere` e solo su un tipo o un'entità.

**Cosa serve**: il modulo di aggiunta impara il terzo genere di soggetto (`integrazione`) e il
campo da scrivere invece di darlo per scontato. La porta (`POST /api/mind/judgment`) è già
generica e accetta la riga: il buco è solo nella pagina.

**L'alternativa, più vicina a dove nasce il fastidio**: un comando sulla riga stessa del primo
piano — «non svegliarmi per questa» — che scrive lo stesso giudizio. Costa una scrittura nella
scheda «Il giorno», che oggi legge e basta.

### I soggetti tecnici raggruppati per integrazione — **USCITA con la v3.54.0**, resta `volte`

È il **terzo punto della §3** di `docs/design/2026-09-18-la-pagina-dell-osservatore.md`, l'unico
rimasto fuori dalla 3.52.0: «il raggruppamento dei soggetti tecnici per integrazione, con `volte` e
**la finestra** a cui quel numero si riferisce — un numero di volte senza finestra non significa
niente».

**Non serve al primo piano** (che raggruppa la cronaca di UN giorno, e la finestra è quel giorno):
serve alla scheda «L'osservatore», e vive sull'altra rotta, `GET /api/mind/watching`. Misurato il
18/09 sulla casa: **39 soggetti tecnici su 153**, da **30 logger distinti** che sono **23
integrazioni** una volta raggruppati. Oggi la pagina li elenca uno per uno, col percorso del
sorgente in chiaro, e non dice mai quante volte una condizione è ricorsa.

**Fatto il 20/09 con la 3.54.0**: la rotta arricchisce le voci tecniche con `integrazione` e
`nome`, usando `mind/report.integration_of` — la stessa regola del primo piano, in un posto solo.
La pagina raggruppa e mostra «Hassio — 6 voci», col percorso del sorgente solo nel dettaglio.

**Resta `volte` e la sua finestra**, e non è un dettaglio: la riga dice quante VOCI DI REGISTRO
distinte ha quell'integrazione, non **quante volte** una condizione è ricorsa — che è il numero che
la §3 chiedeva («un numero di volte senza finestra non significa niente»). Quella rotta non porta
nessun contatore: va deciso su quale finestra si conta (il grezzo dura 22 giorni) e chi la conta.
Finché non c'è, la pagina non dice un numero che non ha.

### La fusione dei quattro composer — aperta il 24/09/2026

`origine: il proprietario, domanda del 23/09/2026` · `misurato durante la fetta delle misure`

Ciò che il modello vede è composto in **quattro posti**: `claude_runner.chat` (API Anthropic),
`OpenAICompatRunner.chat` e `.chat_stream` (catena stile OpenAI), e `agent/prompts.build_chat_messages`
(il ponte, in sottoprocesso).

**Tre delle quattro esistono per una ragione vera**: sono protocolli diversi — Anthropic vuole
`system` come lista di blocchi con `cache_control`, OpenAI un solo messaggio di sistema e caching
implicito per prefisso, il ponte un argv e una cronologia. **La quarta no**: `chat` e `chat_stream`
sono lo stesso protocollo, e compongono la stessa cosa due volte perché una risposta scorre e
l'altra no.

**Sono già divergiti**, e non è un'ipotesi: `tests/test_composition_order.py` esiste perché
l'invariante «persona < modificatori < contesto» era dichiarata in `claude_runner` e **violata nei
due punti di `openai_compat`** — il file li chiama «il punto violato n.1» e «n.2». Corretto, e oggi
inchiodato da cinque prove.

La conseguenza sulle tre domande del proprietario: **ogni leva sui token andrebbe applicata quattro
volte**, o funzionerebbe su un canale e non sugli altri.

Il disegno: un `componi(specie, casa, strumenti, cronologia) → pezzi` che produce le parti
**neutre**, e quattro adattatori sottili che le mettono nella forma del loro protocollo. Così la
regola vive una volta e i canali smettono di poter divergere.

**Non prima delle misure.** La colonna `turn.channel` del registro esiste apposta: dopo qualche
giorno dirà se il ponte e la catena stanno davvero mandando la stessa cosa, e se sono già scivolati
la fusione diventa urgente invece che desiderabile.

### La chat è una sola per costruzione — aperta il 24/09/2026

`origine: il proprietario, fondamenta del 24/09/2026` · `misurato: hiris/app/chat_store.py`

Oggi HIRIS riceve input da **una chat sola**, e lo schema lo dà per scontato:

    chat_sessions(session_id, started_at, last_msg_at, summary)
    chat_messages(id, session_id, role, content, timestamp)

Nessuna colonna per **chi** né per **quale sistema**. E la sessione attiva si sceglie così:

    SELECT session_id FROM chat_sessions WHERE summary IS NULL
    ORDER BY last_msg_at DESC LIMIT 1

**L'ultima che ha parlato, chiunque fosse.** Il giorno in cui Retro Panel manda un messaggio
mentre il proprietario sta chattando, i due finiscono nella stessa sessione e ognuno legge la
cronologia dell'altro come propria.

Non è un limite dichiarato: è un'assunzione implicita, e va resa esplicita o tolta. Perché HIRIS
riceva input da chat diverse per utente e per sistema, la sessione va chiavata su **(soggetto,
origine)** e `load_context` deve leggere quella del chiamante.

**Il registro dei turni è già pronto per quel giorno**: `turn.subject_json` porta chi ha chiesto,
con la stessa forma del soggetto della cronaca. Quando la seconda chat arriverà, le misure sapranno
già distinguerle — invece di scoprire allora che non possono.

### `chatbots.json` resta finché non lo guardi — aperta il 24/09/2026

`origine: decisione del proprietario, 24/09/2026`

La 3.66.0 cancella **dieci** archivi dismessi su undici. `chatbots.json` no: contiene il prompt
personalizzato che il proprietario aveva salvato sul bot di default, e il registro d'avvio dice da
mesi che non viene migrato. Si guarda cosa c'è dentro, poi si decide.

Il criterio scritto con la fetta è: **un archivio si cancella quando è morto E quando qualcuno ha
deciso** — non per la sola prima metà.

### ~~La CLI del ponte sale alla 2.1.278 nel prossimo rilascio~~ — **USCITA** con la v3.66.0

Il cancello (`scripts/verifica_componenti.py`) ha fermato il rilascio della **v3.51.0** su
`2.1.276 -> 2.1.278` (pin in `hiris/Dockerfile`). La 3.51.0 è uscita con `HIRIS_COMPONENTI_OK=1`,
**dichiarato qui e nel rilascio**, perché quella versione porta la cornice della pagina
dell'osservatore: far salire lì una dipendenza non provata spedirebbe un cambiamento sotto il
changelog di qualcun altro. Regola del proprietario del 07/09/2026.

**Cosa fare nel rilascio successivo**: `python scripts/verifica_componenti.py --aggiorna`,
l'annotazione nel `Dockerfile` nella forma che la regola chiede (data, uscite saltate, piano di
ripiego), la suite intera, e poi la prova che il pin arriva davvero dentro il container —
`GET /api/health` deve rispondere `ponte.cli: "2.1.278"`. Il ripiego dichiarato resta la
**2.1.276**, l'ultima di cui esista una lettura vera.

**Rimandata di nuovo il 22/09/2026, con la v3.59.0** (`HIRIS_COMPONENTI_OK=1`, dichiarato qui e nel
rilascio): quella versione porta l'accoppiamento dei servizi, ed è una fetta di sicurezza — far
salire lì una dipendenza non provata è esattamente ciò che la regola vieta.

**Ma la voce va letta come sta scritta adesso**: «nel prossimo rilascio» è stato scritto il
20/09 e da allora sono passati **otto rilasci** (3.51.0 → 3.59.0). Una voce che dice «il
prossimo» per otto volte non sta rimandando: sta dicendo il falso, e il rimando è diventato il
comportamento predefinito invece che una decisione. Il prossimo rilascio che **non** porti una
fetta di sicurezza la prende, oppure si dichiara qui che la 2.1.276 è il pin scelto e il cancello
si riancora — non c'è una terza risposta onesta.

**Rimandata una decima volta il 23/09/2026, con la v3.64.0** — e questa volta con una data
d'arrivo, non con un «prossimo». La 3.64.0 chiude la **fetta 7**, l'ultima dello sprint sicurezza:
vale la stessa regola (una dipendenza non provata non sale sotto il changelog di una fetta di
sicurezza), e la condizione scritta qui sopra — «il prossimo rilascio che **non** porti una fetta
di sicurezza» — da adesso è **verificabile**, perché lo sprint è chiuso e il rilascio successivo è
la fetta delle misure, che per costruzione non cambia comportamento.

La CLI oggi disponibile è la **2.1.280** (non più la 2.1.278 di questa voce: nel frattempo ne sono
uscite altre due). Il ripiego dichiarato resta la **2.1.276**, l'ultima di cui esista una lettura
vera da `GET /api/health`.

**Rimandata un'undicesima volta il 23/09/2026, con la v3.65.0** — e va detto che è l'undicesima,
non nascosto sotto la regola. La 3.65.0 è la **fetta 8**, l'ultima dello sprint sicurezza (B-5),
quindi la regola scritta qui sopra vale ancora alla lettera: una dipendenza non provata non sale
sotto il changelog di una fetta di sicurezza. Ma la condizione «il prossimo rilascio che NON porti
una fetta di sicurezza» adesso è esigibile davvero: **lo sprint è chiuso**, non restano fette di
sicurezza da fare, e il rilascio successivo è la fetta delle misure.

**Se la fetta delle misure non la prende, questa voce non si rimanda una dodicesima volta: si
chiude dichiarando la 2.1.276 come pin scelto, e il cancello si riancora lì.**

**CHIUSA il 24/09/2026 con la v3.66.0, e la fetta delle misure l'ha presa.** Da 2.1.276 a
**2.1.281**: quattro uscite saltate (277, 278, 279, 280), che è il prezzo di undici rimandi — più
si aspetta, più grande è il salto che si prende in una volta. Il cancello dei componenti tace per
la prima volta da undici rilasci: **questo push non porta `HIRIS_COMPONENTI_OK=1`**.

Il ripiego dichiarato è la **2.1.276**, l'ultima ad aver girato davvero su questa casa. Il passo 4
resta aperto: la 2.1.281 va letta dentro il container con `GET /api/health`, campo `ponte.cli`,
dopo un turno di chat.

### La CLI del ponte e' salita alla 2.1.267 — CHIUSA il 10/09/2026

**Aperta e chiusa nello stesso giorno.** Il cancello
(`scripts/verifica_componenti.py`) ha segnalato `2.1.266 -> 2.1.267` durante il rilascio della
v3.24.0, che e' uscita con `HIRIS_COMPONENTI_OK=1`; questa voce diceva «entra nel rilascio
successivo». Il proprietario ha poi deciso di alzarla **subito**, dentro la v3.24.1: pin,
annotazione nel `Dockerfile` (data, uscite, piano di ripiego) e suite intera, nell'ordine che la
regola chiede.

**Anche il passo 4 e' saldato, lo stesso giorno.** `GET /api/health` il 10/09/2026 alle 20:21,
add-on sulla 3.24.1, ha risposto `ponte.cli: "2.1.267"`: il pin arriva davvero dentro il
container. E' la prima volta che la verifica non slitta «al prossimo giro» -- era rimasta in
sospeso per due salti di fila. Il ripiego dichiarato nel `Dockerfile` resta la **2.1.263**,
l'ultima versione precedente di cui esista una lettura vera; la 2.1.266 e' stata scavalcata
prima di girare e non si nomina come ripiego.

**Lo sprint «la conoscenza prende una forma» è CHIUSO con la v3.22.0 (07/09/2026).** Sette
delle sue dieci voci sono passate in «Usciti», ognuna col suo commit: la piattaforma
cercabile, la salute di un'integrazione, il soggetto e la durata di un guasto, i calendari,
le tracce e il log, il vocabolario importato.

**Correzione del 07/09**: l'intestazione precedente diceva *«Nessuna voce passa ancora in
Usciti [...] il lavoro è su `master`, ma la casa non ce l'ha»*. Era vero il 04/09 e falso da
tre rilasci. Un registro che resta indietro rispetto ai fatti è esattamente il difetto che
questo documento dichiara di non voler avere — e ci è cascato lo stesso, per quattro giorni.

**Dello sprint chiuso restano qui tre voci lavorate in parte**, e due chiedono la stessa cosa:
**`search` non distingue ancora un candidato UNICO da un candidato CERTO.**
`memory/resolver.py:233` è ancora un conteggio, e la nozione di candidato *debole* non esiste
da nessuna parte, né nel prodotto né nelle prove. È la **prova numero 3 delle undici** che la
specifica dichiara necessarie a chiudere lo sprint (§11), e non è mai stata scritta. Non
risulta nemmeno una decisione di rinunciarci: è lavoro rimasto indietro, non una scelta.
Chiuderlo vuol dire prima **definire cosa rende debole un candidato** — è una definizione,
non una correzione.

**Lo sprint aperto oggi è un altro: i rilievi del collaudo di usabilità del 07/09**, sette
voci, in fondo a questa sezione. Cinque sono già su `master` in locale e **non ancora
rilasciate**: lo stato «Uscito» lo dà un rilascio, non un commit.

**Due dei sette rilievi non erano quello che dicevano**, e la misura lo ha mostrato prima che
qualcuno ci lavorasse sopra: l'Albero non nasce lungo, e tre delle otto «parole nostre» non
sono sullo schermo. In compenso la stessa misura ha trovato **205 entità che sparivano** da
una pagina che esiste per non far sparire niente.

### La conoscenza non ha spina dorsale — le quattro mancanze

`origine: il proprietario, 04/09/2026, dalla verifica «qual e' lo stato della casa?»` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

**La copertura non e' il problema**: 1221 entita', 242 dispositivi, 53 integrazioni, piani, aree,
comportamenti, plance, i ricordi del proprietario. Il problema e' che sono **elenchi senza
relazioni, senza tempo e senza provenienza**. Ognuna delle quattro mancanze qui sotto e' stata
misurata sulla casa vera il 04/09, e ognuna spiega errori veri.

**1 · L'appartenenza.** Il percorso entita' → dispositivo → integrazione non e' percorribile.
- Il briefing dice «un'**integrazione** non sta funzionando: **Abat-jour**». Abat-jour e' un
  **dispositivo** — lo dichiara l'anagrafe di HIRIS stessa (`tipo: dispositivo`,
  `produttore: "LIFX"`, `modello: "LIFX Mini Color"`). Sta leggendo il *titolo del config entry*,
  che per LIFX e' uno per lampadina, e lo chiama integrazione. Il campo `domain` = `lifx` e' nella
  stessa struttura, tre righe sopra nel codice.
- Nella **stessa conversazione**, venti minuti dopo, dice: «Abat-jour, che risulta *spento* non
  *non disponibile*». Due letture diverse della stessa cosa nello stesso dialogo.
- `search "hydrawise"` → **zero risultati**.
- Chiesto il dettaglio delle 74 entita' mute, ci ha messo **95 secondi**, ha aperto le aree una
  per una, ed e' arrivato a **48 su 74** dichiarando di non farcela sulle due piu' grandi. E'
  una sola giunzione, pagata con quindici chiamate.

**2 · Il tempo.** La «fotografia» sono **quattro fotografie di momenti diversi**, presentate come
una: anagrafe `13:59:15`, comportamento `13:59:14`, confronto `13:49:21`, plance **`09:34:27`** —
quattro ore e mezza prima. Tutti questi istanti sono nel dato; **nessuno arriva alla risposta**. La
domanda del proprietario — «come ho la certezza che nulla e' variato da allora?» — non ha risposta
perche' non esiste la domanda.

**3 · La natura.** Un diagnostico, un interruttore di configurazione e una misura reale arrivano
al modello con la stessa forma. `sensor.persons` letto come presenza (li' `categoria: diagnostic`
c'era e nessuno l'ha guardata); gli interruttori di AdGuard riportati «accesi» accanto al forno e
alla lavastoviglie — e li' va detto che **`categoria` e' `null`**: HA non li distingue, l'unico
indizio e' `piattaforma: adguard` e l'area «Configurazione». Quella correzione va **dedotta**, non
letta: e' piu' difficile della prima, e non e' lo stesso difetto.

**4 · La provenienza.** Cio' che HIRIS ha letto da Home Assistant, cio' che il proprietario gli ha
detto e cio' che ha dedotto arrivano indistinguibili. Vedi il caso Viola in «Come HIRIS interpreta
le entita' di Home Assistant»: prima afferma senza fonte, poi rinnega una fonte che ha davanti.

**Nessuna delle quattro e' un errore del modello: sono tutte forma del dato.** Questa voce e' il
livello sotto ai sintomi raccolti nelle altre — e ha un legame stretto con «Il vocabolario del
dato», che il 03/09 era stata rimandata come fetta di rinomina e non lo e' piu'.

**Due difetti minori trovati insieme, che non meritano una voce loro:** la risposta sullo stato
della casa ha affermato «nessun allarme attivo» e «18 automazioni in funzione regolare» — nessuna
delle due frasi compare nel briefing (zero occorrenze di «regolar» e di «nessun allarme» in 5670
caratteri), e la seconda HIRIS non puo' saperla, perche' non legge le tracce. E ha taciuto la
riga in cui il briefing dichiara se stesso incompleto: «Il nucleo superava il tetto di 6000
caratteri: 3 elementi notevoli non inclusi».

### Come HIRIS interpreta le entita' di Home Assistant — il caso `sensor.persons`

`origine: il proprietario, 04/09/2026, da una chat reale` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

Alla domanda **«quanto tempo la casa ieri e' rimasta vuota?»** HIRIS ha risposto **«mai»**. La
risposta giusta, che l'archivio dell'osservatore aveva gia' scritta quella notte, era **circa
otto ore e mezza**: Paolo fuori 08:08→18:17, Marta 06:39→16:39.

Cosa e' andato storto, nell'ordine in cui e' successo:

1. Ha scelto **`sensor.persons`** — entita' `diagnostic` dell'integrazione *spook* — e ne ha
   dedotto il significato **dal nome**. Non conta chi e' in casa: sta fermo su `2` dal 02/09.
2. Ha presentato la deduzione come un fatto («nessun cambiamento registrato»), senza notare che
   uno stato che non cambia mai non e' una misura di presenza.
3. Corretto dal proprietario, ha tappato il buco con **Viola**: «Viola piu' qualcun altro
   presente». **Viola non e' inventata** — il briefing porta a ogni turno, sotto «Cio' che le
   persone hanno detto», la frase del proprietario stesso: *«in casa vivono anche marta mi
   moglie e viola nostra figlia»*; e in casa c'e' l'area «Cameretta Viola». Inventata era la sua
   **presenza** di ieri, dedotta per far quadrare il numero 2.
4. Poi, alla contestazione, **ha rinnegato una fonte che aveva davanti**: «era una mia
   supposizione, non un dato verificato». Non lo era: era una dichiarazione registrata del
   proprietario, presente nel suo contesto in quel medesimo istante.

I punti 3 e 4 sono **due difetti opposti**, e il secondo e' il piu' grave: prima afferma cio'
che non sa, poi nega cio' che sa. In mezzo c'e' la stessa mancanza — **HIRIS non distingue le
proprie fonti**: cio' che ha letto da Home Assistant, cio' che il proprietario gli ha detto e
cio' che ha dedotto arrivano al modello indistinguibili, e quando qualcuno alza la voce cedono
tutte e tre insieme.
4. La spiegazione finale — «probabilmente conta il numero totale di entita' person» — e' **essa
   stessa una supposizione**, dichiarata tale ma mai verificata.

Il punto che lega questa voce alla fetta A: **la risposta esatta esisteva gia'** negli oggetti
dell'osservatore, con quegli orari precisi al minuto. La chat non li ha interrogati. E' la
stessa legge di «una fonte sola, due lettori», guardata dall'altro capo — qui il secondo lettore
non legge affatto.

**Misurato sulla casa vera il 04/09, e la causa non e' il modello.**

`search` e' una ricerca di **nomi**, non di concetti — ed e' sicura di se' quando sbaglia:

| interrogazione | cosa torna |
|---|---|
| `search "persone"` | **solo** `sensor.persons`, e dichiara `ambiguo: false` |
| `search "presenza"` | **zero risultati** — mentre la gamba «chi c'e'» ne guarda 11 |
| `search "chi c'e' in casa"` | estrae la parola «casa» e offre `weather.forecast_casa` |
| `search "paolo"` | `person.paolo_bettinelli` |

Cioe': le due persone si raggiungono **solo se sai gia' che si chiamano Paolo e Marta**. Chi
chiede «chi c'e' in casa» riceve un candidato solo, quello sbagliato, marcato come non ambiguo.
E' la stessa lacuna di «La piattaforma non e' cercabile», vista dall'altro lato: l'indice non
porta ne' il dominio ne' il significato.

`view` **aveva gia' tutti i segnali** per non cascarci, e nessuno di essi e' una regola da
nessuna parte: `"categoria": "diagnostic"` · `"piattaforma": "spook"` · `"classe": null` ·
`"da_quando"` di **due giorni prima**. Uno stato fermo da due giorni non puo' essere un
conteggio di presenza, e niente in cio' che il modello riceve lo dice.

**La risposta giusta era a una chiamata di distanza**: `logbook(entita="person.paolo_bettinelli",
ore=36)` restituisce `not_home` alle 06:08 UTC e `home` alle 16:17 UTC del 03/09 — cioe'
08:08→18:17 locali, gli stessi minuti che l'osservatore aveva gia' scritto quella notte.

**E c'e' un terzo posto dove il sistema preferisce rispondere invece di rifiutare**: `logbook`
dichiara `required: ["ore"]` nello schema ma **non lo verifica**. Chiamato senza `ore`, o con
nomi di parametro inventati, non solleva: restituisce una finestra a caso, e con `entita`
sbagliata restituisce l'intera casa. Un modello che sbaglia il nome di un argomento riceve dati
plausibili sulla cosa sbagliata invece di un errore.

### Gli strumenti rifiutano invece di indovinare

`origine: il proprietario, 04/09/2026 — «aggiungi tutto il tema»` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

Non e' un difetto: e' **una linea di condotta ripetuta in tre posti indipendenti**, misurati
sulla casa vera il 04/09. Davanti all'incertezza il prodotto risponde con sicurezza invece di
rifiutare.

1. **`search` dichiara `ambiguo: false` su un candidato solo e sbagliato.** `search "persone"`
   torna il solo `sensor.persons` e lo marca come non ambiguo; `search "presenza"` torna zero;
   `search "chi c'e' in casa"` estrae la parola «casa» e offre `weather.forecast_casa`. Le
   persone si raggiungono **solo se sai gia' che si chiamano Paolo e Marta**. Un candidato solo
   non e' la stessa cosa di un candidato certo, e oggi il campo non li distingue.
2. **`logbook` dichiara `required: ["ore"]` e non lo verifica.** Chiamato senza `ore` non
   solleva: sceglie una finestra. Con un nome di argomento inventato lo ignora in silenzio e
   restituisce l'intera casa invece dell'entita' chiesta. Un modello che sbaglia un nome riceve
   dati plausibili sulla cosa sbagliata al posto di un errore.
3. **`view` consegna i segnali e non la regola.** `categoria: diagnostic`, `classe: null` e un
   `da_quando` di due giorni prima erano tutti li'; niente, in cio' che il modello riceve, dice
   che una diagnostica non e' una misura o che uno stato fermo da giorni non puo' essere un
   valore istantaneo.

Il quarto anello — il modello che inventa una persona che non esiste — e' il **sintomo** di
questi tre, non la causa, ed e' l'unico che il proprietario ha potuto vedere.

Ha un legame stretto con «Come HIRIS interpreta le entita' di Home Assistant»: quella voce e' il
caso che l'ha fatto emergere, questa e' la regola che ne esce.

### L'Osservatore mostra i nomi e gli stati di Home Assistant, non i nostri

**FATTA, non ancora rilasciata** — commit `e1bfe8da` (il nome si salva col cambio) e
`b68bda11` (lo stato si rende alla lettura). Provata a secco su archivio e tabella veri:
**69 righe su 69 oggi inglesi diventano italiane**.

`origine: revisione di usabilita' sull'interfaccia vera, casa vera, v3.22.1, 07/09/2026` · `documento: docs/collaudo.md`

Le righe di «Cosa e' successo» portano l'`entity_id` grezzo e lo stato in inglese
(`on`, `off`, `not_home`, `heat`). Il proprietario non chiama cosi' le sue cose: in HA
ogni entita' ha un **nome amichevole**, e ogni stato ha una traduzione che HA stesso
pubblica. Si leggono quelli.

**La trappola**: il nome amichevole puo' mancare. Quando manca si mostra l'`entity_id` e
**si dice che e' quello** — non si inventa un nome, e non si tace la riga. E' la stessa
distinzione che questo ramo ha gia' pagato quattro volte: «non c'e' un nome» e «non ho
potuto leggerlo» sono due fatti diversi.

### La lunghezza dell'Albero su schermo stretto

**RILIEVO CADUTO, e al suo posto ne è uscito uno vero.** Misurato: all'apertura la
pagina è alta **1.784 px**, non 35.576 — quel numero era lo stato in cui il recensore
l'aveva messa aprendo le aree. Ma la stessa misura ha scoperto che **205 entità su 1223
non comparivano affatto**: chiuso con `60aa334c`. Resta **una decisione del proprietario,
rinviata a dopo la verifica dal vivo** — vedi «Due aree dell'Albero sono enormi quando
le si apre», in attesa.

`origine: revisione di usabilita' sull'interfaccia vera, casa vera, v3.22.1, 07/09/2026` · `documento: docs/collaudo.md`

**Misurato a 375 px: l'Albero e' alto 35.576 px** — quasi cento schermate da scorrere per
arrivare in fondo. Tre cause, tutte viste: gli episodi ripetuti non sono raggruppati, non
c'e' una ricerca, e nessuna sezione si chiude.

E' un difetto della casa **vera**, non della casa di prova: cresce con il numero di
entita', quindi peggiora da solo. Qualunque forma si scelga va provata su una casa piena,
non su un campione.

### Modelli e Consumi si contraddicono sull'abbonamento

**FATTA, non ancora rilasciata** — commit `84230ee0`. Misurato: Modelli mentiva. Il
ponte non passa dal router, quindi nessuno scriveva mai un successo per `subscription`.
Corretti **due** punti: il collegamento mancante, e la frase, che pronunciava un fatto
sul mondo («non l'hai ancora usato») partendo da un'assenza di osservazione.

`origine: revisione di usabilita' sull'interfaccia vera, casa vera, v3.22.1, 07/09/2026` · `documento: docs/collaudo.md`

La pagina **Modelli** dice del ponte «non l'hai ancora usato»; **Consumi**, nella stessa
sessione e sullo stesso ponte, ne conta **98 turni**. Una delle due sbaglia, e il
proprietario le vede tutte e due.

**Prima si indaga, poi si corregge.** Non si sa ancora quale delle due fonti sia quella
giusta: correggere quella sbagliata renderebbe *coerente una bugia*. La voce chiede una
misura — chi scrive il contatore, chi lo legge, e perche' i due non si vedono — prima di
chiedere una correzione.

### Le parole nostre invece che le sue

**FATTA IN PARTE** — commit `4e6b36ff`. Misurato: **tre delle otto parole non erano
sullo schermo**. `ponte` è già «Abbonamento Claude», `view` e `casa ›` non esistono
come testo, «Categorie» è vocabolario di Home Assistant e non nostro. Corrette `nucleo`
→ «Cosa vede il modello a ogni turno», «Forza» → «Natura», «Grandezza» → «Cosa misura».
**Resta**: «bersaglio» e i nomi degli strumenti vivono nei messaggi d'errore rivolti al
MODELLO (`action/actuator.py`), che il modello può ripetere in chat. È un'altra cura,
non un cambio di etichetta.

`origine: revisione di usabilita' sull'interfaccia vera, casa vera, v3.22.1, 07/09/2026` · `documento: docs/collaudo.md`

Escono sullo schermo parole che sono **nomi interni**, non parole del proprietario:
`nucleo`, `view`, `ponte`, «Forza», «Grandezza», «bersaglio», «Categorie», e la briciola
`casa ›`.

Vale la regola gia' scritta nel glossario: **si rinomina per funzione, non si traduce**, e
il metro e' la **prova del lettore nuovo**. E' lo stesso lavoro della rinomina chiusa con
i sei rilasci 3.15.0→3.20.0, su cio' che quella non aveva raggiunto: l'interfaccia.

### Accessibilita': nessun titolo in otto rotte su nove, e bersagli sotto i 44 px

**FATTA IN PARTE** — commit `4e6b36ff`. I titoli c'erano ma non erano marcati: 24
`page-title` da `div` a `h1`, con una prova generica sulle rotte registrate che
arrossisce se una rotta nuova se ne dimentica. **Restano i bersagli tattili sotto i
44 px**, mai misurati uno per uno.

`origine: revisione di usabilita' sull'interfaccia vera, casa vera, v3.22.1, 07/09/2026` · `documento: docs/collaudo.md`

**In otto rotte su nove non esiste nessun `h1`–`h4`.** Chi naviga con uno screen reader non
ha nessuna struttura su cui saltare: la pagina e' un muro di testo senza appigli. E
diversi bersagli tattili stanno **sotto i 44 px**, la soglia sotto la quale un dito non
colpisce piu' quello che voleva.

Nessuna delle due cose si vede guardando lo schermo da seduti: si vedono misurando, ed
entrambe sono state misurate.

### La Memoria dichiara «Nessuna struttura riconosciuta» sopra la struttura che ha riconosciuto

**FATTA, non ancora rilasciata** — commit `4e6b36ff`. Separata alla fonte la struttura
stretta (grandezza + intervallo) da quella larga (+ ancore e condizioni): la frase resta
vera guardando l'intera card.

`origine: revisione di usabilita' sull'interfaccia vera, casa vera, v3.22.1, 07/09/2026` · `documento: docs/collaudo.md`

Il pannello scrive di non aver riconosciuto niente, e subito sotto mostra cio' che ha
riconosciuto. E' la forma gia' incontrata quattro volte in questo ramo — **due cose
diverse dette con una parola sola** — e si cura come le altre: **separando alla fonte**,
cioe' facendo etichettare il motivo a chi lo produce, invece di indovinarlo a valle.

### Apostrofi ASCII nel testo composto dal server

**DA FARE, e il perimetro non è quello che questa voce diceva.** Misurato: **513
elisioni in 42 file** (esclusi i docstring), ma **204 stanno in `home_space/tools.py`**,
che legge il MODELLO, non il proprietario. Il codice usa già `è` **477 volte** e `’`
**mai una**: l'incoerenza è dentro la stessa frase. «Si corregge in un posto solo» è
falso — il confine fra testo per il proprietario e testo per il modello va deciso file
per file.

`origine: revisione di usabilita' sull'interfaccia vera, casa vera, v3.22.1, 07/09/2026` · `documento: docs/collaudo.md`

Il testo che il server compone usa `'` dove l'italiano vuole `’`. In interfaccia si legge
come una svista tipografica **ripetuta**, e viene dal server, non dal frontend: e' li' che
va corretto, in un posto solo.

---

## In attesa

> **Avvertenza sulla prima stesura (04/09/2026).** Il proprietario aveva chiesto di annotare una
> lista di argomenti per il prossimo sprint, e quella lista **non e' stata salvata da nessuna
> parte**: cercata in tutto il repository, nelle cartelle ignorate, nelle issue e nelle milestone di
> GitHub, non esiste. Le voci qui sotto **non sono quella lista**: sono ricostruite dai documenti
> del repository e da cio' che e' stato misurato sulla casa vera. La lista del proprietario va
> reinserita da lui, e queste voci vanno lette come un fondo di magazzino, non come una sua scelta.

### Le cinque cose che la fetta dei giudizi ha dichiarato fuori perimetro

`origine: spec «il giudizio dei tipi» §12, dichiarate il 16/09/2026, scritte qui il 17/09/2026 (3.49.0)` · `docs/design/2026-09-16-il-giudizio-dei-tipi.md` §12

Non sono dimenticanze: sono cinque confini scritti prima di cominciare, e restano fuori perche'
ognuno porta una decisione che la fetta non voleva prendere di corsa.

1. **L'osservatore che propone un genere per un'entita'.** Una sua scelta sarebbe `dedotto`, e la
   regola che non si negozia dice che *una deduzione non diventa mai un fatto*: servirebbe la
   forma di una proposta (chi la conferma, dove si vede, cosa accade se nessuno risponde). Oggi il
   genere lo porta il seme del repo, oppure lo scrive il proprietario.
2. **Lo strumento della chat per correggere un giudizio.** Chi scriverebbe sarebbe il modello che
   interpreta le parole del proprietario, cioe' un autore in piu' su righe che oggi hanno un autore
   solo. La porta di scrittura e' una (`mind/judgments.write_judgment`), quindi la fetta e' piccola;
   la domanda che la trattiene e' se una frase detta valga come una correzione fatta a mano nella
   pagina.
3. **Il genere che dipende dallo stato** (`lock` in `jammed` e' un guasto, non un funzionamento).
   **Nessun caso in questa casa: 0 serrature.** Quando servira' sara' un **campo separato**, non un
   formato dentro `genere`: questa e' la parte gia' decisa. Ha un appuntamento anche in «Gli undici
   stati che non sono ne' riposo ne' acceso», dove `lock` in `jammed` aspetta la stessa fetta: si
   fanno insieme.
4. **L'uscita di `source_type` dal grezzo** — vive nella sua voce, «I tre attributi fissi del grezzo
   non sono usciti», che il 17/09/2026 ha registrato la perdita del suo ultimo lettore.
5. **I sei apparati di rete come `presenza`.** Un `nessuno` sulle loro entita' li toglierebbe dalla
   cronaca, ma **nessuno di loro e' guardato oggi**: e' una scrittura che non cambierebbe niente
   finche' l'obiettivo non li sceglie.

### Una coppia dichiarata senza giudizio: il censore non sa chiederne il genere

`origine: revisione del Task 8 della fetta dei giudizi, 17/09/2026` · `docs/design/2026-09-16-il-giudizio-dei-tipi.md` §5

**Il fatto, misurato il 17/09/2026.** Il vocabolario dichiara **22 coppie** `dominio`/`device_class`
che non portano nessun giudizio: esistono come perimetro, e nessuna riga dice che genere di fatto ne
nasca. Il censore ha sei domande aperte (che coprono 115 voci) e **nessuna e' questa**: chi legge la
pagina del sapere non scopre mai che quelle 22 coppie sono rivendicate e mute.

**Cosa servirebbe:** una settima domanda aperta in `home_space/type_census.OPEN_QUESTIONS`, «coppia
dichiarata senza giudizio», con la sua voce nella pagina. E' piccola, e la sua utilita' va misurata
prima: se molte di quelle coppie meritano davvero `nessuno`, la domanda diventerebbe rumore -- e
«se una cosa funziona non va segnalata» vale anche per le domande.

### Una riga del seme ritirata da un rilascio futuro resta in vigore per sempre

`origine: giro di correzioni 1 del Task 11 della fetta dei giudizi, 17/09/2026` · `docs/design/2026-09-16-il-giudizio-dei-tipi.md` §8

**Il fatto.** `knowledge.seed()` scrive e corregge, **non cancella** (ed e' la sua promessa: un seme
che cancellasse porterebbe via anche cio' che la casa ha imparato). Quindi il giorno in cui una riga
sparisse da `type_vocabulary.judgment_seed_rows()`, sulle installazioni gia' avviate resterebbe sul
disco: `mind/judgments.judgment_listing` la mostrerebbe come `da: altro` -- ne' il seme ne' il
proprietario la rivendicano -- e l'istantanea continuerebbe a leggerla. Correggere il repo
ripara una riga sbagliata; **ritirarla non la toglie a nessuno**. Nessun caso oggi: nessuna riga e'
mai stata ritirata dal seme dei giudizi.

**Cosa servirebbe.** Un modo di dire «questa terna non e' piu' del seme» che tolga la riga **solo**
se nessuno l'ha toccata -- la stessa lettura dal valore che `seed` fa gia' (`seeded_value`), al
contrario. Non si e' costruito adesso perche' **cancellare righe del seme e' una decisione del
proprietario**, non un effetto collaterale di un aggiornamento: una cancellazione automatica a fine
sprint sarebbe esattamente il tipo di scrittura silenziosa che la porta unica esiste per impedire.
Dichiarato nel codice accanto a `mind/seed.judgment_seed`.

### Le due mancanze della lingua delle ricette: il periodo e l'elenco di misure

`origine: verifica dal vivo della 3.34.0, 14/09/2026` · `docs/design/2026-09-10-i-tre-attori.md` §6-§7

**Il fatto, misurato.** Delle diciotto operazioni del registro, **dieci non sono raggiungibili da
una ricetta** (dalla 3.35.0 lo dichiarano, e il catalogo non le offre più). Erano nove:
`primo_ultimo_differenza` è uscita da `RECIPE_SHAPES` con la 3.37.0 e nessuno aveva aggiornato il
conto — ricontate il 15/09/2026. Non per un divieto: per
una mancanza della lingua. Dentro una ricetta esistono due sole sorgenti — `@entita` dà una serie,
`$passo` dà una misura — e quelle nove ne vogliono altre.

| chi resta fuori | cosa vuole |
|---|---|
| `episodio` | le letture grezze, e `is_on` (una funzione) |
| `tempo_in_stato` · `quante_volte` · `quando_succede` · `dentro` | un `Period` |
| `misure_durante` | letture **e** un `Period` |
| `somma_entita` · `media_entita` | un **elenco** di misure in un solo ingresso |
| `raggruppa_per` | una **mappa** di misure |

**Le due mancanze, separate perché hanno cure diverse.**

**(1) Il periodo non attraversa i passi.** `episodio` *produce* un periodo, ma lo restituisce
dentro un `Measurement` — e `$passo` consegna il `Measurement`, non il `Period` che sta dentro.
Quindi anche se `episodio` diventasse scrivibile (voce sua, qui sopra), `tempo_in_stato($acceso)`
riceverebbe una misura e morirebbe su `.duration_s`. Da decidere: se un ingresso `$passo` debba
consegnare il **valore** invece del risultato, e allora cosa ne è della copertura; oppure se le
operazioni che oggi prendono un `Period` nudo debbano prendere un `Result` e spacchettarlo loro.
La seconda è più piccola e non tocca la lingua.

**(2) Un elenco di misure non si sa scrivere.** `somma_entita` vuole *molte* misure come **un**
ingresso; una ricetta sa scrivere `inputs: ["$a", "$b"]`, che il motore consegna come **due**
argomenti posizionali. Serve una forma per dire «questi, tutti insieme»: un ingresso che sia una
lista di riferimenti, o un'operazione `insieme($a, $b, ...)` che ne faccia un elenco.

**Cosa costa non farlo.** «Il totale di tutte le zone d'irrigazione», «quanto è stato acceso»,
«quante volte è partito», «succede di notte?» — sono le domande 1, 3 e 5 della spec §7, e **nessuna
ricetta le sa esprimere**. Il modello può chiedere solo somme, medie, quote e tendenze su serie.

**Nota di metodo.** Questa voce esiste perché il registro ha smesso di mentire, non perché
qualcosa si sia rotto: le nove non erano mai state usabili, e prima non lo diceva nessuno. Il
modello ci è cascato al primo tentativo.

### «Quanto è stato acceso» nessuna ricetta la sa chiedere: `episodio` resta fuori

`origine: verifica dal vivo della 3.33.4, 14/09/2026` · `docs/design/2026-09-10-i-tre-attori.md` §6-§7

**Il fatto.** `episodio` è nel registro delle operazioni e **non si può scrivere in una ricetta**
(`in_recipes=False`, dalla 3.34.0): vuole `is_on`, cioè una **funzione** che dice quali stati siano
riposo, e un dato non porta funzioni. Con lei restano fuori dalla portata delle ricette anche le
tre operazioni che le stanno sopra — `tempo_in_stato`, `quante_volte`, `dentro` — perché prendono
un `Period`, e l'unica cosa che produce un `Period` è `episodio`.

**Perché conta.** Sono quattro operazioni su diciotto, e non quattro qualunque: rispondono a
*«quanto è stato acceso»*, *«quante volte è partito»*, *«succede di notte?»*. Il modello le ha
volute subito — la **prima ricetta che abbia mai scritto**, il 14/09/2026, nominava `episodio` —
e non è un caso: per un termostato o una pompa è la domanda naturale. Oggi il catalogo non gliele
offre più, quindi non le sbaglia più; ma non le può nemmeno chiedere.

**Cosa costa non farlo.** Ogni dispositivo che si misura a tempo acceso (termostati, pompe,
ventole, la lavatrice) resta senza misure nel resoconto: ha una cronaca — l'episodio c'è — ma
nessun numero che si legga in serie su trenta giorni. E i tre inneschi dell'analista lavorano
**tutti** sulle misure.

**Quanto costa, misurato.** Sulla casa vera il 15/09/2026, col sapere finalmente
interrogabile: dei **52 dispositivi** che pesano, **18** hanno ricevuto un rifiuto ragionato del
modello, e in almeno uno il modello dice esattamente questo — *«una luce ha senso da misurare per
capire quanto resta accesa e con quale intensità»*: **voleva** misurarlo, e la lingua delle ricette
non gliel'ha permesso. Nel resoconto del 14 le misure a tempo acceso rifiutano tutte: `tempo_acceso`
0 su 4, `tempo_irrigazione_totale` 0 su 4. Non è una mancanza teorica.

**Cosa servirebbe.** Rendere `is_on` esprimibile come dato. Il riposo non è un giudizio nostro: il
vocabolario dei tipi lo sa già per ogni classe, ed è quello che `aggregate_day` interroga oggi. Una
ricetta potrebbe scrivere `params: {"soggetto": "climate.x"}` e lasciare che il motore risolva il
riposo dal vocabolario — cioè la stessa strada già percorsa per le direzioni dell'energia, che
erano codice e sono diventate righe del sapere. Da decidere: se il riposo lo porti il parametro,
il sapere, o l'entità stessa; e cosa fa una ricetta su un tipo di cui il riposo non si conosce
(rifiutare, immagino: è l'unica risposta onesta).

**Attenzione a non riaprire il buco.** Qualunque sia la strada, `in_recipes` deve restare una
dichiarazione **senza valore di fabbrica**: è ciò che ha impedito al difetto del 14/09 di tornare
alla prossima operazione nuova.

### ~~Le ricette si scrivono su entità che non possono avere statistiche~~ — CHIUSA il 15/09/2026 (3.47.0)

**Chiusa dai due lati insieme**, come la voce diceva che andava fatto: il rifiuto ora dice la sua
vera ragione, e la domanda al modello dice **prima** quali entità abbiano una serie — cosi' le
ricette nuove non nascono piu' contro una fonte che non esiste. Resta da vedere dal vivo quante
delle 31 ricette gia' scritte cambino esito: quelle vecchie restano dove sono, e le loro misure
diranno la ragione giusta invece di «la serie e' vuota».

**Com'era scritta quando era aperta:**

### Le ricette si scrivono su entità che non possono avere statistiche: 18 rifiuti al giorno, per sempre

`origine: verifica dal vivo della 3.46.0, 15/09/2026` · `docs/design/2026-09-10-i-tre-attori.md` §6-§7

**Il fatto, misurato.** Le ricette leggono **solo** `HAClient.hourly_statistics()`
(`server.py::_report_ingredients`), e Home Assistant produce statistiche orarie solo per le entità
che dichiarano uno `state_class`. Chiesto a Home Assistant il 15/09/2026 con
`recorder/list_statistic_ids`: **130 entità con statistiche su 1206, tutte `sensor`** — nessuno
`switch`, `light`, `valve`, `binary_sensor`.

Nel resoconto del 14/09, **18 rifiuti su 28 sono su 10 dispositivi che non hanno nemmeno
un'entità con statistiche**: lavastoviglie, abat-jour, l'irrigazione, uno Shelly. Per loro il
modello ha scritto una ricetta valida, il motore la esegue ogni notte, e ogni notte la serie
arriva vuota. Non è un caso limite: è **il 64% dei rifiuti** del giorno.

**Perché il modello ci casca.** Il catalogo gli mostra il dispositivo con tutte le sue entità e le
operazioni disponibili. **Non gli dice quali entità sappiano produrre una serie.** Vede
`switch.lavastoviglie` e scrive «quanto è stata accesa»: è la domanda giusta sul dispositivo
giusto, contro una fonte che per quell'entità non esiste.

**Attenzione — questo cambia la voce «quanto è stato acceso» qui sopra.** Rendere `episodio`
scrivibile in una ricetta **non basterebbe**: anche con la lingua a posto, `@switch.lavastoviglie`
non porta niente da leggere. Servono tutte e due le cose — l'operazione esprimibile *e* una fonte
per le entità non numeriche, che è la **storia** (`history/period`), non le statistiche. Quella
storia HIRIS la legge già, per la cronaca: misurato lo stesso giorno,
`light.abat_jour_sinistra` aveva cinque punti di storia per il 14/09.

**Questa voce e la voce «I due rifiuti della spec §6» sono lo stesso problema da due lati.** La
spec §6 elenca fra i «rifiuta se» di un'operazione proprio *«l'entità non ha statistiche»*, e
nessuna delle diciotto operazioni lo dichiara: è a backlog dal 12/09/2026, prima che la casa
producesse un solo numero. Se ci fosse, i 18 rifiuti di oggi direbbero **la loro vera ragione**
invece di «la serie è vuota» — e il modello, a cui il rifiuto torna, saprebbe di aver puntato una
fonte che per quell'entità non esiste. **Le due voci si fanno insieme, o la seconda riscrive la
prima.**

**Da decidere.** Se dire al modello quali entità abbiano una serie (il sapere lo saprebbe: è un
fatto che HA dichiara, come le unità), oppure se il motore debba scegliere la fonte in base
all'entità — statistiche dove ci sono, storia dove no. La seconda risponde anche alla voce qui
sopra; la prima è più piccola e si può fare subito.

**Nota di metodo, scomoda.** Questa voce esiste perché la prima diagnosi era **sbagliata**: avevo
letto la *storia* di quella luce, visto cinque punti, e concluso che l'operazione ricevesse punti
non numerici. Storia e statistiche sono due fonti diverse e solo la seconda viene letta. La
correzione in `operations._reject_for_coverage` resta — dire «vuota» di una serie piena sarebbe
falso — ma ha **zero occorrenze** su questa casa, e la sua docstring lo dichiara.

### ~~Il sapere non ha una porta~~ — CHIUSA il 15/09/2026 (3.45.0), e ha trovato tre cose

`origine: verifica dal vivo della 3.45.0, 15/09/2026`

La porta (`GET /api/mind/knowledge`, sezione 04 dell'osservatore) è viva. **Nelle prime ore ha
mostrato tre difetti**, tutti chiusi nella 3.46.0 e tutti invisibili finché nessuno poteva
chiedere: 18 rifiuti ragionati archiviati come «non capito» con una frase nostra che le prove
accanto smentivano; il riassunto lungo quanto il dato (14 righe da uno su 19); e — cercando la
causa — i nomi dei dispositivi risolti da una porta del cervello su quattro.

**Nota di metodo.** Nessuno dei tre si sarebbe visto leggendo il codice: si sono visti guardando
246 righe di sapere vero. È la ragione per cui la porta viene prima della fetta che ci lavora
sopra.

**Com'era scritta quando era aperta** (13/09/2026), che e' cio' contro cui si e' misurata:


`origine: verifica dal vivo della 3.31.0, 13/09/2026` · `docs/design/2026-09-10-i-tre-attori.md` §8

**Il fatto.** Il sapere (`sapere.db`) contiene le direzioni dell'energia, ~177 significati di
classe, gli attributi che valgono la pena e le ricette dei dispositivi. Si legge da tre posti --
`energy_directions` (le direzioni), `guarda` sul dettaglio di un'entita' (il significato),
l'osservatore (gli attributi) -- e da **nessuna pagina**. Non c'e' nessuna rotta HTTP che lo
serva.

**Perche' conta.** La quarta fondamenta dice che *«se un dato c'e' e nessuno puo' chiederlo, non
esiste»*. Qui il dato si puo' chiedere alla chat, e non e' poco, ma «cosa HIRIS ha capito della mia
casa, con quale provenienza, e cosa non ha capito» e' esattamente la domanda che il proprietario si
fa guardando la pagina dell'Osservatore -- e oggi quella pagina mostra solo cosa HIRIS GUARDA, non
cosa ha CAPITO.

**Cosa costa non farlo.** Le righe `verifica = non_capito` -- i dispositivi di cui il modello non
ha saputo scrivere una ricetta -- sono invisibili. Sono precisamente cio' che il proprietario
potrebbe risolvere in dieci secondi («quello e' il contatore dell'acqua»), e nessuno gliele mostra.

**Cosa servirebbe.** Una rotta che serva il sapere raggruppato per soggetto, e una sezione della
pagina che lo renda con la provenienza accanto a ogni riga. E' piccola, e va fatta insieme alla
resa del resoconto (fetta 5), che tocca la stessa pagina.

### ~~La regola 1 della spec §5.3~~ — SCRITTA il 16/09/2026

**Chiusa lo stesso giorno in cui e' nata questa voce.** Il filtro c'e'
(`mind/watcher.py`): un `sensor` con `state_class` non si registra piu' a campione. Due
precisazioni che la misura ha imposto: vale per il **solo dominio `sensor`** (Home Assistant
calcola le statistiche di lungo periodo per quello soltanto -- 130 entita', tutte `sensor`), e
scatta **dopo** il controllo degli attributi della §5.4, perche' le statistiche portano il numero
e non gli attributi. Quattro mutazioni eseguite, quattro uccise.

**Cosa si perde: niente di leggibile** -- dei 146 soggetti guardati 42 hanno statistiche, e zero
delle 44 voci di cronaca del 14/09 venivano da loro. **Il numero nuovo del volume si misura dal
vivo al primo giorno pieno dopo il rilascio**: finche' non e' misurato, qui non si scrive.

**Com'era scritta quando era aperta:**

### La regola 1 della spec §5.3 non e' mai stata scritta: il grezzo e' il triplo di quanto promesso

`origine: revisione indipendente dello sprint, 15/09/2026` · `docs/design/2026-09-10-i-tre-attori.md` §5.3

**Il fatto, misurato oggi.** La spec §5.3 dichiara due regole di scrittura. La seconda (`da != a`)
c'e' (`mind/watcher.py:265`). **La prima non esiste**: *«chi ha `state_class` non si registra a
campione»* -- cioe' non copiamo nel grezzo le entita' per cui Home Assistant tiene gia' le
statistiche. `watcher.py:315` scrive `state_class` nella riga e **non filtra mai su di esso**.

**Cosa costa, col numero.** La spec promette un calo dell'**83%**, «da 29.227 a 4.951 righe al
giorno», e lo scrive due volte (§5.3 e §14). Dal vivo (`GET /api/mind/watching`, volume):

| giorno | righe |
|---|---|
| 09/09 | 22.905 |
| 11/09 | 11.544 |
| 13/09 | 18.520 |
| 14/09 | 16.677 |
| 15/09 | 13.945 |

Cioe' **−43% ÷ −60%**, non −83%: circa **tre volte** le righe promesse, ogni giorno, sul disco
dell'utente. E `api/handlers_mind.py:98` dice ancora «la spec promette −83%».

**Perche' non e' stato fatto.** Il piano la rimandava «alla Fetta 5»
(`docs/superpowers/plans/2026-09-10-i-tre-attori.md:758`). La Fetta 5 e' uscita con la 3.32.0
**senza**, il piano non ha un «Fetta 5 — ESITO», e fino a oggi non ne esisteva nemmeno una voce di
backlog: era sparita fra le maglie.

**Attenzione prima di farla.** Le entita' con `state_class` sono quelle che il resoconto legge
dalle statistiche -- non dal grezzo -- quindi toglierle dal grezzo non dovrebbe togliere nessuna
misura. Ma la **cronaca** nasce dal grezzo (`mind/facts.aggregate_day`): va misurato **prima** cosa
sparirebbe dalla cronaca, o si scopre dopo il rilascio di aver reso muto qualcosa che si vedeva.

### ~~Il genere di un episodio nasce ancora dalla gamba, e finche' e' cosi' gambe e generi restano~~ — CHIUSA il 17/09/2026 (3.49.0)

**Chiusa costruendo il sostituto**, che e' la sola strada che la voce ammetteva: il genere
dell'episodio non nasce piu' dalla gamba, lo chiede all'**istantanea dei giudizi**
(`mind/facts.genre_for` -> `TypeJudgments.genre_of`), e i giudizi sono righe del sapere che la casa
puo' correggere. Le gambe sono **cancellate**: `ASPECT`, `ASPECT_GUARD`, `ASPECTS`, `aspect_of`, i
campi `aspect` e `aspect_guard` (43 celle) e con loro `is_operable`, `operable_domains`,
`resting_states_of`, `resting_states`, `working_states_of`, `is_notable`, `notable_types`,
`parameter_limits`; `tests/test_home_space_gamba.py` e' eliminato e le sue prove sono tradotte sui
giudizi. Il rilevatore di fumo che la voce difendeva non torna a leggersi «Acceso»: nel seme e' una
riga `genere` `sicurezza`, e una prova la fissa.

**La misura che rendeva la sostituzione sicura** (spec §1, misura 7): ripassate 52.123 righe di
storia di Home Assistant su 304 entita' dei tipi con genere, dal 09/09 al 16/09, chiedendo il
riposo al tipo invece che all'unione di tutti i riposi -- **0 righe cambiano esito**.

**Un cambio di comportamento dichiarato, non un effetto collaterale**: `none` non e' piu' un
riposo. Su 6 apparati di rete, 200 righe `none` in una settimana non apriranno piu' un'assenza e
non chiuderanno piu' un episodio.

**Cosa resta da fare, ed e' il Task 12 del piano**: la verifica dal vivo in casa dopo il rilascio,
col confronto fra le cronache salvate prima e quelle rifatte dopo.

**Com'era scritta quando era aperta:**

### Il genere di un episodio nasce ancora dalla gamba, e finche' e' cosi' gambe e generi restano

`origine: revisione indipendente dello sprint, 15/09/2026; decisa il 16/09/2026` · `docs/design/2026-09-10-i-tre-attori.md` §13

**Deciso il 16/09/2026, e la spec e' stata corretta di conseguenza**: §13 dichiarava distrutte le
gambe e i sei generi, e girano ogni notte. La misura dice perche' non si possono togliere adesso:
`mind/facts._reading_aspect` ricava la **gamba** da `device_class`/`source_type`, e dalla gamba
nasce il **genere** dell'episodio. Senza un sostituto, un rilevatore di fumo scattato torna a
leggersi «Acceso» -- cioe' la cronaca perde proprio cio' che la rende leggibile.

La riga di §13 era vera per meta': il giudizio di **rilevanza** e' passato all'osservatore, come
prometteva. Il secondo lavoro delle gambe -- dare un genere -- quella riga non l'aveva visto.

**Cosa servirebbe per toglierle davvero:** che il genere nasca dal **sapere**, come e' successo
alle direzioni dell'energia (erano codice, sono righe). E' parente stretto della voce qui sotto sul
vocabolario-seme, e va fatta con quella: sono lo stesso movimento -- il giudizio del repo diventa
una riga che la casa puo' correggere.

**Nel frattempo la spec non mente piu'**: le due righe di §13 dicono «RESTANO», con la ragione.

### ~~§13 dice di cancellare le gambe e i sei generi~~ — com'era scritta quando era aperta

`origine: revisione indipendente dello sprint, 15/09/2026` · `docs/design/2026-09-10-i-tre-attori.md` §13

**Il fatto.** La spec §13 elenca fra cio' che si distrugge **le gambe** (`ASPECTS`, `aspect_of` e le
loro righe) e **`genre_for` coi sei generi**. Nessuno dei due e' uscito:
`home_space/type_vocabulary.py:520` e `:1614` per le gambe, `mind/facts.py:69` e `:130` per i
generi, invocati dentro `aggregate_day` a ogni aggregazione notturna. Perfino una prova lo dava per
fatto: `tests/test_home_space_gamba.py:15-19` dice «muore con i sei generi, nella Fetta 5».

**Perche' sono ancora li', e non e' una dimenticanza.** `mind/facts._reading_aspect` usa
`device_class` e `source_type` per derivare la gamba di ogni `sensor` e `binary_sensor`, e la gamba
decide il **genere** dell'episodio, che decide come si legge la cronaca. Toglierli senza un
sostituto vorrebbe dire che un rilevatore di fumo scattato torna a leggersi «Acceso» -- e' la
stessa ragione gia' scritta nella voce «I tre attributi fissi del grezzo non sono usciti».

**Da decidere dal proprietario, ed e' una riga di specifica:** o si costruisce il sostituto (il
genere dal sapere invece che dalla gamba, che e' parente stretto della voce del vocabolario-seme
qui sotto), **oppure la §13 va corretta** per dire che gambe e generi RESTANO, e perche'. Oggi la
spec dichiara distrutto cio' che gira, ed e' una bugia scritta accanto al codice.

### ~~Il vocabolario dei tipi non e' ancora un seme del sapere~~ — CHIUSA il 17/09/2026 (3.49.0)

**Chiusa con un terzo disegno, che questa voce non aveva visto** (correzione del 17/09/2026, dopo
la revisione a 360 gradi: la prima stesura di questa chiusura diceva «il primo dei due disegni», ed
era falsa -- la spec §0 li ha **confrontati e scartati entrambi**, per ragioni misurate). Il disegno
scelto dal proprietario e' l'**istantanea immutabile** (disegno «C»): i giudizi si leggono dal
sapere una volta sola e si consegnano ai lettori come un oggetto fermo, invece di spostare i lettori
sull'archivio (letture SQLite nel percorso caldo) o di fare del modulo il confine (uno stato
condiviso caricato pigramente in un modulo oggi puro). **Misura del 16/09/2026**: non
sette moduli e undici porte, ma **7 moduli e 17 porte** (`action/verification`,
`home_space/briefing`, `home_space/queries`, `home_space/topology`, `home_space/type_census`,
`mind/facts`, `proxy/entity_cache` -- la voce elencava `action/registry`, che lo cita soltanto, e
non aveva visto `proxy/entity_cache`).

**E i lettori dei GIUDIZI sono quattro, non sette** (spec §3, D4): `home_space/briefing`
(`notevole`, `lavoro`), `home_space/queries` (`limiti_parametri`), `home_space/type_census`
(`riposo`, `lavoro`, `accendibile`) e `mind/facts` (`genere`, `riposo`). Gli altri tre leggono
**fatti di Home Assistant** o `assumable_attributes`, che non sono giudizi nostri e per decisione
D1 restano codice accanto alla tabella importata che correggono.

**Cosa si carica adesso all'avvio**: `mind/seed.judgment_seed` semina **99 celle** dal letterale --
26 `genere`, 23 `notevole`, 18 `riposo` (16 piu' le 2 `home` nuove su `person` e `device_tracker`),
13 `accendibile`, 10 `limiti_parametri`, 9 `lavoro` -- con provenienza `nostro` e autore «seme del
repo» (conteggio rieseguito il 17/09/2026: 99). La regola del seme che esisteva gia' («nessuno l'ha
toccata si legge dal valore») e' cio' che permette di **tornare al seme** dopo una correzione.

**Il doppione senza lettori, che la seconda fondamenta vieta, non e' nato**: cio' che e' diventato
sapere e' uscito dal letterale nello stesso movimento (Task 8 del piano: **tredici nomi**
cancellati fra costanti, porte e un aiutante privato -- `ASPECT`, `ASPECT_GUARD`, `ASPECTS`,
`aspect_of`, `_text`, `is_operable`, `operable_domains`, `resting_states_of`, `resting_states`,
`working_states_of`, `is_notable`, `notable_types`, `parameter_limits` -- e **43 celle** di gamba e
guardia), e cio' che resta codice -- `capability_names`, `capability_attributes`,
`state_attributes` (68 celle `importato`), `capability_attributes_dropped`, `assumable_attributes`
-- resta con le sue 12 prove ancorate al sorgente.

**La promessa del §8 e' mantenuta**: la casa scrive sopra il giudizio del repo, da una porta sola
(`POST /api/mind/judgment`) e dalla pagina del sapere, nella sezione «Le tue correzioni».

**Com'era scritta quando era aperta:**

### Il vocabolario dei tipi non e' ancora un seme del sapere

`origine: fetta 4 «il sapere e le ricette», 12-13/09/2026` · `docs/design/2026-09-10-i-tre-attori.md` §8

**Il fatto.** La spec dice: *«Il repo diventa il seme. Le 76 righe del vocabolario dei tipi e le 14
delle direzioni si caricano all'avvio con la loro provenienza.»* Le 14 direzioni si caricano
(`mind/seed.direction_seed`), le righe del vocabolario dei tipi **no**.

**Perche' non e' stato fatto, e non e' una dimenticanza.** Seminarle senza spostare anche i LETTORI
produrrebbe un doppione: la stessa cosa in `home_space/type_vocabulary.py` e nel sapere, con nessuno
che legge la seconda copia. E' precisamente cio' che la seconda fondamenta vieta, e il seme
diventerebbe un file che nessuno interroga.

**Cosa servirebbe.** Spostare i lettori — `mind/facts.genre_for`, `mind/watcher`, `home_space/
type_census` — a interrogare il sapere invece del letterale, e solo allora seminare. E' una fetta
sua, e non piccola: quelle righe decidono il genere di ogni oggetto e il perimetro dello scope,
cioe' due delle cose piu' load-bearing del prodotto.

**Quanto e' grande, misurato il 15/09/2026 chiudendo lo sprint.** `type_vocabulary` non ha tre
lettori: ne ha **sette moduli** (`action/verification`, `home_space/briefing`, `home_space/queries`,
`home_space/topology`, `home_space/type_census`, `mind/facts`, piu' `action/registry` che lo cita) e
espone **undici porte** — `capability_names`, `is_notable`, `working_states_of`,
`resting_states_of`, `unknown_states`, `declared_domains`, `declared_pairs`, `parameter_limits`,
`aspect_of`, `operable_domains`, `ABSENT_STATE_FORMS`. Il file e' di **1984 righe**.

**Due disegni possibili, e la scelta e' del proprietario:**

1. **Spostare i lettori** (quello che questa voce diceva): sette moduli cambiano, e per un po'
   convivono due verita'. E' la strada pulita e la piu' cara.
2. **Fare del modulo stesso il confine**: `type_vocabulary` legge il sapere dove una riga c'e' e il
   letterale dove non c'e'. Nessun lettore cambia, nessun doppione senza lettore, e la casa puo'
   scrivere sopra il giudizio del repo — che e' l'intera promessa del §8. Il prezzo e' che un
   modulo oggi **puro** prenderebbe una dipendenza da un archivio, cioe' esattamente lo «stato
   condiviso caricato pigramente» che ci ha gia' morso altrove.

**Perche' non e' stato fatto nello sprint che la chiedeva**: seminare senza decidere fra le due
lascerebbe un archivio che nessuno interroga, e il §8 esiste per il contrario. La fetta e' pronta
per essere pianificata, non per essere improvvisata a fine giornata.

**Cosa si guadagna quando si fa.** La casa potra' scrivere sopra il giudizio del repo — «da me
questo tipo si comporta cosi'» — che e' l'intera promessa del §8, e oggi vale solo per le direzioni
e per i significati.

### I tre attributi fissi del grezzo non sono usciti

`origine: fetta 4, 13/09/2026, misurato leggendo il codice` · `docs/design/2026-09-12-il-sapere-e-le-ricette.md` misura 6

**Aggiornata il 17/09/2026 (3.49.0): `source_type` ha perso il suo ultimo lettore.** Con la gamba
e' uscito `_reading_aspect`, che era l'unico a leggerlo: oggi `source_type` si **scrive** nel grezzo
(`mind/watcher.py`, `mind/store.py`) e **nessuno lo legge** -- misurato con un grep su tutto
`hiris/app`: le sole altre occorrenze sono due commenti e la riga che lo elenca fra gli **attributi
di stato** del `device_tracker` (`type_vocabulary.py:1525`, tabella `importato`: «com'e' adesso»
secondo Home Assistant -- non una lista di scarti, come diceva la prima stesura di questa nota, e la
revisione del 17/09 l'ha corretta). Il genere dell'episodio adesso lo chiede
all'istantanea dei giudizi, non alle classi. `device_class` invece resta letto: `genre_for` lo usa
come secondo termine del soggetto (la coppia `dominio`/`device_class`) e finisce nel corpo di ogni
episodio.

**Quindi la voce si restringe a due colonne**, e per entrambe la domanda e' la stessa: `state_class`
non ha lettori dal 27/08/2026, `source_type` non ne ha piu' dal 17/09/2026. La ragione scritta per
tenerle («i 22 giorni permettono di rifare il giudizio se un domani tornasse a servire») ora vale
per due colonne invece di una: o si conferma, o escono insieme.

**Com'era scritto il fatto quando la gamba c'era ancora.** Il piano prevedeva che `device_class`,
`state_class` e `source_type` uscissero dal grezzo con la fetta 4. Non sono usciti: `device_class` e
`source_type` li leggeva `mind/facts._reading_aspect` per derivare la **gamba** di ogni `sensor` e
`binary_sensor`, e `device_class` finisce nel corpo di ogni episodio. Toglierli significherebbe che
un rilevatore di fumo scattato torna a leggersi «Acceso».

**La spec si contraddiceva su questo punto**: §5.3 dice che lo scope *deriva* da dominio,
`device_class` e `source_type`; §5.4 dice che quei tre escono. Non possono valere entrambe, e
vinceva §5.3 perche' descriveva codice vivo e misurato. **Dal 17/09/2026 la contraddizione si
restringe a `device_class`**: il perimetro si compone da dominio e `device_class`
(`mind/watcher._wanted_attributes`, chiave `(domain, device_class)`), e `source_type` **non entra
nel perimetro**: nel grezzo ci arriva solo perche' `mind/watcher` lo scrive in colonna, e nessuno lo
rilegge.

**Cosa e' cambiato lo stesso**: il grezzo non conserva piu' *solo* tre attributi scelti a mano.
Conserva quelli che il sapere dice valgano la pena per quel tipo, e il cambio di uno di quelli fa
nascere una riga anche quando lo stato non si muove.

**Cosa resta da decidere.** `state_class` non lo legge nessuno dal 27/08/2026. Resta nel grezzo con
una ragione scritta («i 22 giorni permettono di rifare il giudizio se un domani tornasse a
servire»): o quella ragione si conferma e la voce si chiude, o la colonna esce.

### ~~I due rifiuti della spec §6~~ — CHIUSA il 16/09/2026: il primo fatto, il secondo dichiarato non applicabile

`origine: revisione indipendente della fetta 3, 12/09/2026` · `docs/design/2026-09-10-i-tre-attori.md` §6

**Il fatto.** La spec elenca fra i «rifiuta se» di un'operazione due casi: *«l'entita' non ha
statistiche»* e *«il periodo e' fuori dalla memoria disponibile»*. Nessuna delle diciotto voci di
`hiris/app/mind/operations.py` li dichiara, e nessuna li produce: il registro sa rifiutare per
copertura, per unita' incompatibili, per troppi pochi punti — **non per un periodo che l'archivio
non copre affatto**.

**CHIUSO il 15/09/2026 (3.47.0) il primo dei due: «l'entita' non ha statistiche».** Otto
operazioni lo dichiarano (`Operation.refuses_when`), `HAClient.statistic_ids()` legge il registro
delle statistiche di Home Assistant, `Recipe.run(without_statistics=...)` lo produce per il passo
che nomina quell'entita' -- non per l'intera ricetta -- e la domanda al modello dice **prima** di
scrivere quali entita' abbiano una serie e quali no. `None` e non insieme vuoto quando la lettura
fallisce: affermare «nessuna entita' ha statistiche» farebbe rifiutare tutto il resoconto.

**IL SECONDO RESTA, e non e' piu' una svista: e' una decisione da prendere.** «Il periodo e' fuori
dalla memoria disponibile» ha **zero occorrenze misurate** su questa casa, e per due ragioni
indipendenti: (a) HIRIS non chiede mai un giorno prima del suo grezzo — `_write_missing_reports`
si ferma a `oldest_reading_ts()`, e la ragione e' scritta li'; (b) le statistiche di lungo periodo
di Home Assistant non si potano come gli stati. Misurato il 15/09/2026 su questa casa: le
statistiche piu' vecchie sono di **luglio 2026**, e cio' che sembrava «periodo fuori memoria» era
in realta' **tre entita' iscritte al registro delle statistiche che non hanno mai registrato
niente** (l'albero di Natale, le luci di Natale, la gestione carichi) — che e' un terzo caso
ancora, e «la serie e' vuota» lo dice gia' bene.

**DECISO il 16/09/2026: si scrive nella spec, non si costruisce.** La §6 ora porta l'annotazione
col numero -- zero occorrenze, le due ragioni indipendenti, e il terzo caso (tre entita' iscritte
al registro che non hanno mai registrato niente) per cui «la serie e' vuota» e' gia' la frase
giusta. Costruire un rifiuto per un caso che non accade costerebbe una lettura per entita' a ogni
giro: **non si fa finche' una misura non lo chiede**. Se il proprietario la vede diversamente, e'
una riga di specifica da riscrivere, non codice da disfare.

**AGGIORNAMENTO 15/09/2026 — il primo dei due ha adesso un numero, misurato sulla casa vera.**
Home Assistant tiene statistiche orarie per **130 entita' su 1206, tutte `sensor`**
(`recorder/list_statistic_ids`): nessuno `switch`, `light`, `valve`, `binary_sensor`. Nel resoconto
del 14/09, **18 rifiuti su 28** sono su dieci dispositivi che non hanno nemmeno un'entita' con
statistiche, e dicono «la serie e' vuota» — vero, e inutile: non dice a chi legge (ne' al modello,
a cui il rifiuto torna) che quella fonte per quell'entita' **non esistera' mai**. Vedi la voce
«Le ricette si scrivono su entita' che non possono avere statistiche»: e' lo stesso problema visto
dal lato del dato.

**Perche' non entra nella fetta 3.** Tutti e due chiedono di sapere fin dove arriva la memoria:
i 22 giorni del grezzo (`archivio.READING_RETENTION_S`) e le statistiche che Home Assistant tiene
per quell'entita' (`ha_vocabulary.produces_statistics`). E' conoscenza della casa, e il registro
deve saper calcolare e basta — la stessa ragione per cui `quando_succede` riceve il fuso gia'
risolto e `raggruppa_per` riceve la chiave da fuori.

**Cosa costa oggi.** La domanda vera del proprietario *«dammi il totale delle ore irrigate tra
maggio e settembre»* riceve il rifiuto giusto **solo se chi compone la ricetta lo costruisce a
mano**. Se qualcuno dimentica il controllo, il registro somma le tre settimane che ha e le
consegna come cinque mesi: e' il difetto fondativo di questa fetta, lasciato fuori dal cancello.
`tests/test_mind_operations.py::test_domanda_5_...` lo dichiara nel suo docstring.

**Cosa servirebbe.** Un ingresso comune — il periodo chiesto e l'orizzonte davvero disponibile per
quell'entita' — che il chiamante risolve e che un'operazione (o un controllo all'ingresso della
ricetta, fetta 4) confronta prima di calcolare qualunque cosa.

### Il grezzo butta l'unita' di misura, e l'oggetto di energia resta senza

`origine: misurato leggendo il codice il 12/09/2026, durante l'estrazione delle operazioni (fetta 3)` · `docs/design/2026-09-10-i-tre-attori.md`

**Il fatto.** La tabella `cambi` (`hiris/app/mind/store.py`) registra di ogni cambio
`device_class`, `state_class`, `source_type`, `domain`, `title`, `friendly_name` — e **non**
`unit_of_measurement`, che Home Assistant dichiara per ogni entita' e che HIRIS legge gia' altrove
(`home_space/reader.py`, colonna `unita`). E' la tesi della spec dei tre attori applicata a un
attributo che nessuna fetta ha ancora raccolto: *«Home Assistant dichiara gia' tutto, la copia lo
butta»*.

**Cosa costa oggi.** L'oggetto di genere `energia` che `mind/facts.aggregate_day` scrive ogni notte
porta `valore_iniziale`, `valore_finale` e `differenza` — **tre numeri senza unita'**. Il corpo tace
invece di inventare (difeso da
`tests/test_mind_facts.py::test_un_energia_NON_dichiara_un_unita_che_nessuno_ha_registrato`, e il
registro delle operazioni riceve `UNKNOWN_UNIT`), ma tacere e' la risposta meno peggio, non quella
giusta: quel contatore puo' essere in Wh, in kWh o in m3, e chi legge l'oggetto fra tre settimane
non ha modo di saperlo. La prima fondamenta lo dice alla lettera — *«un valore senza la sua unita'
non e' un oggetto: e' un frammento»*.

**Cosa servirebbe.** Una colonna `unit` sul grezzo (in inglese, come le altre nuove), scritta
dall'osservatore al momento del cambio come si fa gia' per `friendly_name` — **non risolta dopo
dall'anagrafe**, per la stessa ragione del nome: gli oggetti vivono piu' a lungo dei cambi, e
un'entita' rinominata o sparita non direbbe piu' niente. Poi l'oggetto di energia la porta, e il
registro riceve l'unita' vera al posto della sentinella.

### La persona e il suo telefono sono lo stesso fatto, scritto due volte

`origine: misurato sulla casa vera l'11/09/2026, durante la verifica dal vivo della 3.26.0` · `nessun documento`

**Il fatto, contato.** Sui 15 giorni con episodi di presenza (27/08 -> 10/09) l'osservatore ha
prodotto **108 episodi** di genere `presenza`: **54 da `person.*` e 54 da `device_tracker.*`**. Le
coppie con lo **stesso inizio e la stessa fine** sono **54 su 54 -- il 100%**. Lo scarto fra i due
istanti ha mediana **0,000 s** e massimo **0,001 s**: e' lo stesso fatto scritto due volte, e quel
millisecondo e' il momento in cui Home Assistant riscrive la persona dopo il suo tracciatore.

Esempio vero del 10/09: `person.marta` 16:21:15 -> 17:13:57 «Fuori casa», e
`device_tracker.iphone_di_marta` 16:21:15 -> 17:13:57 «Fuori casa».

**Home Assistant lo dichiara, e non va dedotto da nessun nome.** `components/person/__init__.py`
(HA `2026.9.1`, versione letta dalla casa vera) alle righe `632-652` mette su ogni entita' `person`
l'attributo **`device_trackers`** -- l'elenco dei suoi tracciatori -- e **`source`**, quale di essi
sta fornendo la posizione adesso. Alle righe `520-577` la persona **si iscrive** ai cambi di stato
dei propri tracker e ne ricalcola il proprio: **il tracciatore e' l'ingresso, la persona e' il
fatto.** Sulla casa vera l'attributo e' valorizzato su **2 entita' `person` su 2**
(`person.marta` -> `["device_tracker.iphone_di_marta"]`; `person.paolo_bettinelli` ->
`["device_tracker.iphone_bet", "device_tracker.ipad_mini"]`).

Nei **registri** il legame non c'e': `person.marta` ha `device_id: null` e nessuna voce di
dispositivo lo nomina. Vive solo negli attributi dello stato -- che e' esattamente la fonte
dichiarativa di cui parla il corollario di `CLAUDE.md`: *quando HA ha una fonte dichiarativa, quella
e' la risposta*.

**Dove HIRIS lo perde, e il punto in cui fa piu' male.** `server.py::build_companions` interroga
`search/related` con `item_type="entity"`. Chiesto su `person.marta`, Home Assistant **non**
risponde il tracciatore (asimmetria verificata nel sorgente: `components/search/__init__.py:396-401`
risolve «esiste anche come persona» solo quando `entry_point=False`). Ma chiesto **sul
tracciatore**, HA risponde `{"person": ["person.marta"]}` (`:415-416`) -- **e HIRIS lo scarta**,
perche' `_COMPANION_TYPES` elenca `entita`, `automazione`, `scena`, `script` e non `persona`. Il
legame arriva, una volta, dal verso giusto, e viene buttato sulla soglia.

Il grezzo non lo porta (`mind/watcher.py:248-260` conserva quattro attributi scelti a mano, e
`device_trackers`/`source` non sono fra loro) e l'anagrafe nemmeno: nel payload di
`GET /api/home-space` -- 649 KB -- le occorrenze di `device_trackers` sono **0**.

**Perche' non basta lasciarlo allo scope.** Con lo scope attivo il doppione sparira'
probabilmente da solo, ma **per la ragione sbagliata**: Home Assistant marca
`device_tracker.iphone_di_marta` come `entity_category: diagnostic`, e le entita' di servizio
restano fuori per decisione del proprietario del 10/09. Sparirebbe perche' «di servizio», non
perche' HIRIS abbia capito che e' l'ingresso della persona -- e su una casa dove il tracciatore non
fosse marcato cosi', tornerebbe intero.

**Perche' non e' materia del sapere (§8) ne' delle ricette (§7).** Non e' una deduzione da
archiviare: e' un attributo che HA mantiene, e copiarlo in una riga di sapere sarebbe la seconda
fondamenta violata di nuovo. E le ricette raggruppano **per dispositivo**, mentre `person.marta`
un dispositivo non ce l'ha.

**La cosa piu' piccola che lo chiuderebbe**, da valutare quando la voce si sceglie: il lettore
porta sulla riga `person` dell'anagrafe il campo `tracciatori`, letto da
`attributes.device_trackers` dello specchio vivo -- **la stessa porta da cui arrivano gia' `classe`
e `unita`** (`home_space/reader.py`, `topology.actual_class`/`actual_unit`) -- e
`facts.aggregate_day` non fa protagonista di un episodio di `presenza` un `device_tracker` che
compaia fra i tracciatori di una persona. Una fonte sola, risolta a ogni lettura e mai copiata;
nessun archivio nuovo, nessuna chiamata di rete in piu', nessuna deduzione del modello.

### L'avviso sul gruppo misto arriva solo a chi GUARDA il gruppo

`origine: la fetta dei gruppi, 09/09/2026` · `.superpowers/sdd/tipi-di-entita/fetta-gruppi-report.md` §8.4

Dalla fetta dei gruppi il dettaglio di un'entita' porta `membri`, e quando un gruppo dichiara una
capacita' che non tutti i suoi membri hanno lo dice: `membri.capacita_non_di_tutti`. Home Assistant
su un gruppo dichiara l'**unione** delle capacita' dei membri
(`components/group/light.py:283-295`, `:263-273`, `:250-261`, `:319-328` al tag `2026.9.1`),
accetta il comando e lo applica **solo a chi puo'**, in silenzio.

**Il buco che resta**: quell'avviso esce **solo** da `guarda` sul dettaglio di quella entita' --
stessa disciplina di `attributi` e di `comandi`, e per la stessa ragione (un'area con venti cose
non deve portarsi dietro l'analisi di ognuna). Quindi se il modello chiede «cambia colore al
lampadario» **senza guardarlo prima**, il comando parte, HA lo applica a una luce su tre, e la
frase che l'avrebbe detto non l'ha letta nessuno.

**Dove va chiuso**: nell'ESITO dell'azione (`action/actuator`), non nella vista -- e' il verso
opposto della catena, quindi una fetta sua con il suo changelog. Il dato per farlo c'e' gia': i
membri sono nella cesta `members` dello specchio, e `queries.group_membership` e' pura.

**Sulla casa vera non morde oggi**: l'unico gruppo delle 841 entita'
(`light.lampadario_sala_da_pranzo`) ha tre membri con capacita' identiche, misurato il 09/09/2026.
Morde il giorno in cui il proprietario mette una luce a colore accanto a due prese.

### HIRIS per gli utenti non-admin di Home Assistant

`origine: il proprietario, 05/09/2026, brainstorming` · `nessun documento`

**Il bersaglio**: gli utenti HA **non amministratori**, che oggi l'add-on non lo vedono nemmeno.
La distribuzione ad altre case e' l'orizzonte dichiarato, non il problema di questa voce.

**Il fatto che governa tutto**, e va letto prima di ogni disegno: HIRIS parla con Home Assistant
usando il **token del Supervisor**, non i permessi di chi sta chattando. Via ingress HA inoltra
l'identita' ma **non applica i ruoli**. Quindi oggi *vedere l'add-on equivale ad avere pieni
poteri sulla casa*, aggirando il modello di permessi di HA.

**Verificato alla fonte il 05/09** (non dedotto):

| | |
|---|---|
| `panel_admin` | «Make the menu entry only available to users in the admin group», default `true`. Governa **la voce di menu** |
| header inoltrati dal Supervisor (`supervisor/api/ingress.py`) | `X-Remote-User-ID`, `X-Remote-User-Name`, `X-Remote-User-Display-Name` |
| header sul **ruolo** | **nessuno**: il Supervisor non dice se l'utente e' amministratore |
| `config/auth/list` (`components/config/auth.py`) | esiste, torna `group_ids`, ed e' `@websocket_api.require_admin` |

**Deciso in brainstorming:**
1. **Poteri uguali per tutti**, e li stabilisce la fetta sicurezza — non questa.
2. **Una conversazione privata per persona.** Oggi ce n'e' **una sola per tutta la casa**
   (`chat_messages(session_id, role, content, timestamp)`: nessun autore, nessun agente). Un
   modello che legge un thread con tre autori indistinguibili ragiona su un interlocutore che non
   esiste: e' la quarta spina — la provenienza — a un secondo livello. I **ricordi** un autore
   gia' ce l'hanno («detto da Paolo»); le conversazioni no.
3. **La cucitura e' quella che il prodotto ha gia'**: «Da fare» (Impegni, Proposte) e «La casa» a
   tutti, «Configurazione» ai soli admin. Non «chat contro pannello»: un non-admin che chiede di
   costruire qualcosa creerebbe una proposta **che non potrebbe vedere ne' approvare**, e la chat
   gli direbbe «ti aspetta nella pagina Proposte» — la frase aggiunta il 04/09 per chiudere il
   difetto «non sai dove» — indicando una porta che per lui non esiste.

**Bloccato, e su decisione del proprietario:** *come* HIRIS sappia chi e' amministratore. Le due
strade sono `config/auth/list` (verita' di HA, ma un'API riservata chiamata col token del
Supervisor che scarica **tutti** gli utenti con le loro `credentials` per una domanda su uno) o un
elenco esplicito nella configurazione dell'add-on. **Si decide con la fetta sicurezza.**

**Conseguenza pratica, ed e' il motivo per cui questa voce non e' pronta a diventare una fetta:**
senza il ruolo non si puo' scrivere `panel_admin: false`, perche' aprirebbe anche
«Configurazione». Finche' la sicurezza non arriva, **i non-admin non raggiungono HIRIS** — e
costruire ora i thread privati sarebbe costruire per utenti che non possono ancora entrare. Lo
stesso genere di lavoro senza chiamanti che questo progetto ha gia' cancellato due volte
(`get_error_log`, i calendari).

**Il documento del 26/07** (`docs/design/2026-07-26-chat-tutta-la-casa-design.md`, sul ramo
`analysis`/`feat/chat-household`, mai fuso) resta utile per l'inquadramento ma **tre dei suoi
cinque fatti sono superati** dal refactor 2.0: `resolve_owner` non esiste piu' (uscito come
orfano), la cronologia non e' piu' per agente ma unica, e il semaforo per-azione e' fra le cose
che lo scope 2.0 dichiara assorbite.

### I comandi verso Home Assistant

`origine: deciso dal proprietario il 04/09/2026` · `documento: docs/design/2026-09-04-i-comandi-verso-home-assistant.md`

> **16/09/2026 — questo sprint e' la SECONDA meta' di quello in corso.** Il proprietario ha deciso
> l'ordine: prima si chiude §8/§13 della spec dei tre attori (il vocabolario come seme e il genere
> dal sapere), poi si apre questo. E questo sprint porta dentro una richiesta nuova, che ha una
> voce sua qui sotto: **HIRIS come assistente vocale di Home Assistant**.

Colmare i buchi di scrittura verso HA emersi dallo studio di `ha-mcp`: plance, categorie, etichette
(update e delete), aree e piani, zone, calendari con ricorrenze, gruppi e liste, i 17 helper a
config-flow, blueprint. Lo studio porta la chiamata esatta di ognuno, letta nel loro sorgente. **Non
e' una specifica**: il perimetro non e' stato scelto.

### HIRIS come assistente VOCALE di Home Assistant

`origine: deciso dal proprietario il 16/09/2026` · `entra nello sprint dei comandi, e vuole un'analisi sua`

**Cosa ha chiesto il proprietario:** che HIRIS sia disponibile come **assistente vocale di Home
Assistant**. E' una feature nuova e importante, e **prima di progettarla serve un'analisi
approfondita**: entra nello sprint dei comandi (qui sopra), non lo sostituisce.

**Cosa e' gia' misurato, il 16/09/2026, e cosa no.** Sulla casa vera (`GET /api/states`, 850
entita'):

| | |
|---|---|
| entita' `conversation` | **1** -- `conversation.home_assistant`, l'agente integrato. Nessun agente personalizzato |
| `assist_satellite` · `tts` · `stt` · `wake_word` | **0 ciascuno** |
| `media_player` | 7, fra cui **Echo Cucina**: oggi la voce di questa casa passa da Alexa, non da Assist |

E dal lato nostro: il vocabolario dei tipi **conosce gia'** `conversation` (col bit `CONTROL = 1`,
letto dal sorgente di HA `2026.9.1`) e `assist_satellite`; non conosce `stt` ne' `tts`.

**La domanda che l'analisi deve sciogliere per prima, e non si indovina.** HIRIS e' un **add-on**:
un container separato che parla con Home Assistant dalle API. Gli agenti di conversazione di HA,
per quanto ne sappiamo oggi, sono **integrazioni** (custom component) che registrano un'entita'
`conversation`. **Se un add-on possa esporre un agente di conversazione, e con quale meccanismo, e'
esattamente cio' che va verificato sulla documentazione e sul sorgente PRIMA di disegnare
qualunque cosa** -- e' la regola «mai ipotesi su Home Assistant: prima la doc, poi le API vere», e
qui la risposta cambia l'intera forma della fetta:

- se serve un **custom component** accanto all'add-on, nasce un secondo artefatto da distribuire,
  aggiornare e versionare, ed e' una decisione di prodotto prima che tecnica;
- se basta il **websocket** (registrare un agente, o intercettare le frasi di
  `conversation.process`), resta tutto dentro l'add-on;
- se nessuna delle due, la strada e' un'altra ancora (una `intent_script`? un `sentence trigger`
  che chiama HIRIS?) e va misurata.

**Le altre cose da stabilire nell'analisi, nessuna delle quali si indovina:**

1. **Cosa risponde.** Il cervello di HIRIS oggi ragiona per turni lunghi (l'analista scrive cinque
   osservazioni su trenta giorni). Una risposta vocale ha un budget di **secondi**. Va deciso se
   l'assistente vocale sia una porta sul sapere gia' calcolato -- che e' veloce -- o un turno di
   modello, che non lo e'.
2. **Chi parla.** Su questa casa non ci sono satelliti: senza un `assist_satellite` o un
   `tts`/`stt` configurato, un agente di conversazione si puo' provare solo dalla chat di Assist.
   Va misurato **prima** se il proprietario voglia comprare un satellite, usare il telefono
   (l'app companion ha Assist), o passare da Alexa -- perche' la terza strada e' un'altra fetta
   ancora.
3. **Cosa puo' FARE.** Un assistente vocale che risponde e basta e' meta' prodotto; uno che
   comanda ricade dentro lo sprint dei comandi e **dentro la sicurezza** (lo sprint dopo): oggi
   cio' che rende irraggiungibili i servizi pericolosi e' un accidente di forma, non una difesa.
   Una voce che comanda senza quella difesa e' la combinazione peggiore.
4. **Le frasi.** HA ha un suo vocabolario di intenti gia' fatto. Va stabilito se HIRIS lo estenda
   o lo sostituisca: sostituirlo vorrebbe dire rifare cose che HA fa gia' bene, ed e' la prima
   legge del prodotto (sussidiarieta').

**16/09/2026, brainstorming ripartito da zero.** Il proprietario ha scelto le situazioni che
contano: **(a)** chiedere a HIRIS dal telefono, dentro l'app di HA, a testo o a voce; **(d)**
comandare la casa con frasi libere; **(c)** HIRIS che avvisa da solo; e **poi** usare l'assistente
dal **Retro Panel** («lo vediamo poi»). Verificato sul sorgente di HA lo stesso giorno: un add-on
puo' essere agente di conversazione di Assist senza custom component (Wyoming, programma *handle*,
`discovery: [wyoming]`; precedente ufficiale OHF-Voice `script-agent`), e la pipeline con
`prefer_local_intents` fa provare prima le frasi e gli intenti locali di HA e passa all'agente solo
cio' che HA non capisce (`assist_pipeline/default_pipeline.py`). Vincolo gia' noto per il Retro
Panel: gira su iOS 12, dove l'input vocale del browser non c'e' -- da li' sara' testo.

**L'ordine, deciso dal proprietario il 16/09/2026: (a) e (d) insieme, poi (c).** E **dopo, la
sicurezza costruita sull'intero scenario, per disegno** («finito andremo a costruire tutta la
sicurezza avendo l'intero scenario e applicando una security by design»). Punto aperto da portargli
al rilascio: fra questa fetta e lo sprint della sicurezza, i comandi via Assist restano accesi o
spenti di fabbrica?

**Chi risponde e come, deciso il 16/09/2026.** HIRIS **e'** l'agente di Assist (Wyoming, non
strumenti per un altro modello), e **ogni frase e' un turno completo** di HIRIS, identico alla
chat: stesso cervello, strumenti, mani. Misurato quel giorno, un campione: un turno di chat semplice
(una domanda sulla temperatura) dura **14,8 s** dall'invio alla risposta (202 in 0,5 s, poi la coda
del ponte). **Per dopo, deciso dal proprietario:** a fetta fatta si indaga se e come **velocizzare
sia le risposte vocali sia la chat** -- con le misure dell'uso vero, non prima.

**La conversazione, decisa il 16/09/2026: un filo per ogni conversazione di Assist**
(`conversation_id`), separato dalla chat della pagina -- perche' il proprietario **vuole
introdurre la divisione delle chat per utente**, e questa e' la stessa strada. Oggi
`chat_store.py` ha un filo solo (sessioni chiuse dal silenzio, riassunti). Vincolo misurato sul
sorgente di HA (`wyoming/conversation.py`): a un agente Wyoming arrivano solo `conversation_id`,
`device_id`, `satellite_id` -- **non l'utente**. La divisione per utente dovra' dire da dove
ricava chi parla (per esempio il dispositivo); vedi anche la voce «HIRIS per gli utenti non-admin
di Home Assistant».

**Chi prova per primo, deciso il 16/09/2026: prima HA, poi HIRIS.** La pipeline usa
`prefer_local_intents`: frasi personalizzate e intenti locali di HA prima, HIRIS solo per cio' che
HA non capisce (verificato in `assist_pipeline/default_pipeline.py`). Limite dichiarato: i comandi
che fa HA non passano da HIRIS, quindi non entrano nella sua cronaca delle azioni ne' nel filo.

**Il primo avvio, deciso il 16/09/2026.** HIRIS si annuncia (discovery Wyoming); il proprietario
**conferma in HA** (passo che HIRIS non puo' saltare); poi, **su sua richiesta**, un pulsante nella
pagina di HIRIS crea la pipeline «HIRIS» con le scelte decise (prima HA, italiano) attraverso
`assist_pipeline/pipeline/create` (verificato nel sorgente: `create`, `update`, `list`, `delete`,
`set_preferred`). La pipeline di serie non si tocca e **non diventa predefinita** se non lo sceglie
lui.

**La voce, decisa il 16/09/2026: Whisper e Piper in casa**, in locale, cosi' la voce funziona da
ogni dispositivo (Android e altoparlanti compresi). Misurato quel giorno: host `generic-x86-64`,
HAOS 18.2, 90,8 GB liberi, **nessun add-on vocale installato** (11 add-on). CPU e RAM non lette.
Verificato sul sorgente delle app e di HA: la pipeline non taglia una risposta sotto i **300 s**
(`assist_pipeline/const.py`), e da iPhone esiste anche la trascrizione sul telefono (Companion,
Labs, iOS 17+). Da misurare dopo l'installazione: quanto aggiunge la trascrizione su questo host, e
quanto e' accurata in italiano con il modello di partenza.

**Da NON fare prima dell'analisi:** scrivere codice. Questa voce esiste perche' la richiesta non
vada persa, non perche' il perimetro sia chiaro -- come per la voce dei comandi qui sopra, **il
perimetro non e' ancora stato scelto**.

### ~~La sicurezza~~ — **USCITA**: lo sprint c'e' stato, dal 21 al 23/09/2026

`origine: deciso dal proprietario il 04/09/2026` · `documento: docs/design/2026-09-21-sicurezza-esposizioni.md`

**Chiusa il 23/09/2026 con la v3.65.0.** Otto fette, venticinque reperti in quattro classi, tutti
con una nota: chiusi, o **ritirati con la misura accanto**. Il registro dei rischi e la tabella
delle fette stanno nei due documenti del 21/09; il racconto, rilascio per rilascio, nel CHANGELOG
(3.55.0 → 3.65.0).

E il reperto che apriva questa voce ha avuto una risposta che non e' quella che si aspettava: **la
lista di servizi vietati non e' stata scritta, ed e' deliberato**. Una lista di divieto e'
aggirabile per costruzione — un `shell_command` dentro il corpo di un'automazione passa
`validate_config` ed e' un oggetto permanente che chiama cio' che `execute` non avrebbe potuto
chiamare. Al suo posto: l'anteprima dice **quali servizi il corpo chiama** e quali **compaiono**
rispetto a prima (B-4), c'e' un freno di ritmo **per entita'** (B-3), e la cronaca registra la
frase su cui una conferma e' nata (B-5). Si e' scelto di **rendere visibile** invece di vietare,
perche' il divieto lo si aggira e la visibilita' no.

La forma originale della voce, com'era quando era aperta:

> Sprint a se', **dopo** quello dei comandi. Il reperto che lo apre: HIRIS non ha nessuna lista di
servizi vietati. Cio' che oggi rende irraggiungibili `homeassistant.restart`, `hassio.host_reboot`,
`recorder.purge`, `shell_command.*` e' un accidente di forma — quei servizi non dichiarano un
`target`, e un bersaglio vuoto e' sempre stato un rifiuto. La difesa non e' progettata: e'
incidentale, e cade tutta insieme il giorno in cui quella condizione si allarga.

### La scheda della proposta dentro la chat

`origine: il proprietario, segnalata il 03/09/2026` · `documento: docs/design/2026-09-03-i-menu-esecutivi.md §6.4`

L'anteprima con Approva e Rifiuta li' dove la frase la annuncia, senza cambiare pagina. Il
proprietario l'ha voluta segnalata, non fatta allora. Costa **rimettere `tools_called` nella
risposta della chat**, tolto il 17/08.

### Il vocabolario del dato

`origine: il proprietario, rimandata il 03/09/2026` · `documento: docs/design/2026-09-03-i-menu-esecutivi.md §7`

La lingua del database, i valori di dominio e le chiavi dei record fra motore e pagina: **una fetta
sola**, perche' sono la stessa cosa. Rinominare i fatti che ci sono costa la riscrittura di ogni
query che li nomina — al contrario di aggiungere un fatto che manca, che costa una migrazione
additiva e reversibile.

**Decisione del proprietario, 04/09/2026, presa durante lo sprint dell'appartenenza:**
«tutte le nuove colonne nei db vanno in inglese; poi migreremo tutto in inglese in uno
sprint futuro per sanare anche questo problema». **Questa voce e' quello sprint.**

Da qui in avanti quindi: le colonne **nuove** nascono in inglese (le prime sono
`entita.config_entry_id` e `integrazioni.entry_id`, 04/09), e quelle italiane accanto
sono **debito dichiarato**, non un modello da imitare. Nessuna colonna esistente si
rinomina fuori da questa fetta: la migrazione si fa una volta, tutta insieme, o si
resta con un archivio meta' e meta' -- che e' peggio di entrambe le scelte coerenti.

Lo stesso vale per le **chiavi delle risposte** (`entita_totali`, `entita_mute`,
`mute_da`, `entita_disabilitate`, `elenco_incompleto`, `entita_stato_ignoto`): sono
un altro strato dallo stesso problema, e si convertono qui.

### La gamba «acqua» dell'osservatore

`origine: dichiarata nella spec dell'osservatore, mai fatta` · `documento: docs/design/2026-08-26-l-osservatore.md`

32 entita' di irrigazione, **zero osservate**. La gamba e' progettata e non fatta: `valve`+`water` e
`sensor`+`water` — che oggi finirebbe nell'energia, ed e' una risorsa diversa.

### ~~Il prompt dell'obiettivo dell'osservatore~~ — CHIUSA il 15/09/2026

**Chiusa dallo sprint «i tre attori», e la sua premessa non esiste più.** L'obiettivo è il prompt:
`mind/observer.build_question(objective, lines)` glielo mette davanti, `mind/cadence` fa
riconsiderare lo scope quando cambia, il resoconto di ogni giorno porta quello di ALLORA, e
l'analista lo legge. E **il pavimento — «fisso», che questa voce voleva allargare — è stato
cancellato l'11/09/2026**: al suo posto c'è la cadenza (spec §5.2). Resta aperta la voce sua, «Otto
domini su dieci in `_OPERABLE` non possono arrivare», che parla di un'altra cosa.


`origine: dichiarata nella spec dell'osservatore, mai fatta` · `documento: docs/design/2026-08-26-l-osservatore.md`

Non esiste ancora: il pavimento e' fisso, e il prompt dovra' solo allargarlo. E' il motivo per cui
**8 domini su 10** fra quelli elencati come funzionanti (luci, interruttori, ventilatori, media
player, valvole...) oggi non producono nessun oggetto — il pavimento non li lascia passare.

### `build.yaml` dichiara una licenza che non e' la nostra

`origine: rilevato il 10/08/2026` · `nessun documento`

`hiris/build.yaml:9` dichiara `org.opencontainers.image.licenses: "MIT"`, etichetta che finisce
nell'immagine Docker pubblicata, mentre `LICENSE` dice «PROPRIETARY SOFTWARE LICENSE». Da sanare
prima di un rilascio.

### `_ENTITY_ID_RE` vive in quattro copie

`origine: rilevata nel giro di correzioni del Task 5 di «le tracce e il log», 05/09/2026` ·
`nessun documento`

Stessa espressione (`^[a-z][a-z0-9_]*\.[a-z0-9_]+$`), stessa intenzione — una guardia sulla forma
`dominio.oggetto` di un `entity_id`, la piu' stretta possibile — duplicata a mano quattro volte,
ognuna dichiarata "DOPPIONE" nel proprio commento invece di importata: `proxy/ha_client.py:36`
(la prima), `home_space/behavior.py:45` (indipendente, un'espressione diversa nello scopo ma
identica nel testo), `mind/watcher.py:82` (Task 4 di questa stessa fetta) e
`home_space/tools.py:188` (Task 5, questo giro; il rimando diceva `:352`, corretto nel Task 6 --
`:352` e' dentro lo schema di `view`, non la guardia). Non si unifica adesso: ogni fetta che
l'ha scritta aveva una ragione dichiarata per non importarla da un'altra (modulo diverso,
accoppiamento non voluto), e unificarle tutte e quattro e' un lavoro suo, con la sua verifica — non un effetto
collaterale di un giro di correzioni. Ma quattro copie della stessa guardia, scoperte una alla
volta invece che in un colpo solo, sono il tipo di cosa che questo registro esiste per non
lasciar perdere.

### `home_space/behavior.py` ipotizza un `id` di automazione intero, e la fonte dice `str`

`origine: rilevata dal giro di correzioni del Task 6 di «le tracce e il log», 05/09/2026` ·
`nessun documento`

`home_space/behavior.py:161-164` porta il commento «`None` e' l'unica assenza: un id intero `0`
(numerazione a mano da zero) e' un id vero, non un id mancante», e di conseguenza scrive
`key = str(attribute_id) if attribute_id is not None else ""`.

**L'id intero non esiste.** Lo schema di Home Assistant e' `CONF_ID: str` — con accanto, nel
sorgente, il commento `# str on purpose` — in `components/automation/config.py`, sia in
`_MINIMAL_PLATFORM_SCHEMA` sia in `PLATFORM_SCHEMA`; verificato sui tag rilasciati `2024.7.0`
(righe 47 e 60) e `2026.9.0` (righe 48 e 70), non su `dev`. Un `id: 0` non quotato in YAML **non
supera lo schema**: voluptuous tratta il tipo nudo `str` come un controllo di istanza, e
`PLATFORM_SCHEMA(config)` solleva. Quindi `attributes["id"]`, quando c'e', e' sempre una
stringa — che e' il fatto che serve qui.

**Cosa NON e' stato tracciato fino in fondo**, e va detto invece di essere presunto: dove
finisce quell'automazione dopo il rifiuto. `_async_validate_config_item` ripiega su
`_minimal_config`, che pero' rivalida con `_MINIMAL_PLATFORM_SCHEMA` — dove `CONF_ID: str` c'e'
di nuovo — quindi il ripiego solleva a sua volta, e chi raccolga quell'eccezione piu' a monte
non e' stato verificato. Chi chiude questa voce non ha bisogno di saperlo (basta il tipo), ma
non scriva la fine della storia senza averla letta.

E' un'**ipotesi su Home Assistant mai verificata alla fonte** — la specie di difetto che il
prodotto ha una regola apposta per non commettere — sopravvissuta perche' il codice che ne
deriva e' innocuo: `str()` su una stringa e' l'identita', e il ramo dell'intero non si esercita
mai. Non e' quindi un guasto, e' una **frase falsa dentro il codice**, che il prossimo lettore
prendera' per vera e usera' per decidere qualcosa.

Debito PRECEDENTE a questa fetta: il Task 6 lo ha trovato mentre verificava la stessa fonte per
un'altra ragione (l'id di configurazione come chiave delle tracce) e **non ha toccato
`behavior.py`**, che non era nel suo perimetro. Chi lo chiude tolga il ramo dell'intero e citi
`CONF_ID: str` coi due tag, invece di limitarsi a correggere il commento: un `str()` difensivo
che nessuna fonte giustifica e' l'altra meta' della stessa ipotesi.

### Il collettore delle tracce tiene tre pezzi di stato su `app`, e sono un oggetto che non esiste

`origine: dichiarata dall'implementer del Task 6 di «le tracce e il log», 05/09/2026` ·
`nessun documento`

La cadenza che raccoglie le tracce delle automazioni ha accumulato, una fetta alla volta, tre
voci separate nel dizionario dell'applicazione: `automation_traces_boot_ts` (l'istante d'avvio
del processo, per non rileggere cio' che e' successo mentre HIRIS era spento),
`automation_trace_cursors` (i `run_id` gia' visti per automazione, che rendono la raccolta
idempotente) e `automation_trace_unresolved` (le automazioni per cui l'avviso e' gia' stato
detto una volta). Le tre nascono in momenti diversi, si leggono insieme, e nessuna ha senso
senza le altre due: sono lo stato di **un** collettore, tenuto in tre posti perche' nessuna
fetta ha avuto motivo di fermarsi a costruirlo.

Non e' un guasto — funziona, ed e' provato — ma e' la forma che rende facile il prossimo
difetto: chi aggiunge la quarta voce non ha niente che gli ricordi le altre tre, e chi svuota
una sola al riavvio rompe un invariante che nessuna firma dichiara. Chi la chiude raccolga le
tre in un oggetto con le sue prove, invece di aggiungerne una quarta accanto.

Vale la stessa disciplina della voce sulle quattro copie di `_ENTITY_ID_RE`: si nomina adesso
perche' e' stato visto adesso,
e si chiude in una fetta sua, non come effetto collaterale di un giro di correzioni.

### `troncato`: stessa chiave, due semantiche di presenza in `ha_client.py`

`origine: il coordinatore del Task 1 di «i calendari», 06/09/2026` · `nessun documento`

`HAClient.history()` e `HAClient.logbook()` dichiarano `"troncato": bool` **sempre**, anche a
falso — e' la loro scelta esplicita, motivata solo dalla coerenza reciproca fra i due ("non due
modi di dire la stessa cosa", si legge nel docstring di `history()`). `HAClient.calendar_events()`,
aggiunto dallo stesso task, dichiara la stessa identica cosa — un elenco tagliato dal tetto
(`MAX_HISTORY_POINTS`/`MAX_LOGBOOK_ENTRIES`/`MAX_CALENDAR_EVENTS`) — ma con la chiave `"troncato"`
che esce **solo quando il taglio e' avvenuto**, stessa disciplina di
`elenco_incompleto`/`mute_da`/`entita_stato_ignoto` in `home_space/queries.py` ("le chiavi che non
hanno niente da dire non escono").

Non e' un errore: e' la scelta **giusta** per `calendar_events()` (la legge del prodotto — un fatto
che non c'e' non deve parlare — e' piu' generale del "sempre" dei due fratelli), ed e' stata
verificata e confermata durante la revisione del task che l'ha introdotta. Ma nello stesso file,
sotto lo stesso nome di chiave, convivono oggi due semantiche di presenza diverse per lo stesso
concetto ("questo elenco e' stato tagliato"): chi legge `"troncato" in risposta` per un metodo e
"il valore di `risposta['troncato']`" per un altro sta leggendo due contratti diversi con lo stesso
nome.

**Chi chiude questa voce**: allinei `history()` e `logbook()` alla disciplina omit-quando-falso di
`calendar_events()` (non il contrario: e' quella piu' generale). **Nessun consumatore si rompe**:
gli unici chiamanti di produzione leggono con `risposta.get("troncato")`, che torna `None` sia
quando la chiave manca sia quando vale `False` — verificato prima di scrivere questa voce, non
assunto.

### Il calendario come contesto per interpretare la casa

`origine: il coordinatore del Task 3 di «i calendari», 06/09/2026` · `nessun documento`

La fetta «i calendari» chiude con la LETTURA: lo strumento `calendar` (`home_space/tools.py`)
risponde a «quali sono i miei prossimi appuntamenti?», fondendo gli impegni di ogni calendario di
questa casa. Non fa — deliberatamente — l'uso piu' ricco di questa fonte: «il riscaldamento e'
rimasto spento perche' eravate in ferie dal 17 al 30 agosto» e' un'AGGREGAZIONE (calendario +
stato della casa nello stesso periodo), non una lettura, e non poteva nascere prima che il lettore
esistesse — cio' che questa fetta ha appena costruito.

Il materiale c'e' gia': il passato denso (misurato il 06/09/2026, `HAClient.calendar_events`, 297
eventi su una finestra di quattro anni, 91 nel calendario «Personale», 206 in «Famiglia») e' esattamente
dove sta l'informazione che spiegherebbe un'assenza prolungata o un consumo fuori norma.
`read_appointment`/`sort_appointments` (`home_space/appointments.py`) gia' fanno la parte pura
(un evento grezzo -> un impegno leggibile, piu' calendari -> un elenco ordinato): l'aggregazione
mancante e' un consumatore nuovo di quelle stesse funzioni, dal lato dell'osservatore (`mind/`), non
un terzo modo di leggere i calendari.

**Da decidere quando si progetta**: quale FINESTRA di passato l'osservatore deve guardare per
correlare un impegno con un pavimento (l'intera durata dell'evento? un margine attorno?), e come si
dichiara l'incertezza quando un calendario e' rotto proprio nel periodo che si vuole spiegare — la
stessa disciplina di `non_letti` nello strumento della chat, vista dal lato dell'osservatore.

### Scrittura e conservazione degli eventi di calendario — misurate come non necessarie

`origine: il coordinatore del Task 3 di «i calendari», 06/09/2026` · `nessun documento`

Due capacita' che Home Assistant espone e che questa fetta ha lasciato fuori di proposito, non per
dimenticanza — misurate, non assunte:

- **Scrivere sul calendario** (`calendar/event/create`, esposto da HA): non serve a nulla di cio'
  che e' stato chiesto («leggere i calendari», «rispondere sui prossimi appuntamenti»), ed
  espandere il perimetro senza una richiesta e' la stessa disciplina gia' applicata altrove in
  questo prodotto (spec §1, «il meccanismo lo dichiara HA, non lo indoviniamo noi» — qui vale al
  contrario: non si costruisce un meccanismo che nessuno ha chiesto).
- **Conservare gli eventi in un archivio proprio**: misurato come rischio, non solo come lavoro in
  piu'. Una copia diverge il giorno in cui un evento viene spostato dal telefono — HIRIS
  continuerebbe a rispondere sulla versione vecchia finche' qualcosa non la rileggesse, ed e' lo
  stesso difetto per cui l'archivio storico proprio (`history.db`) e' uscito dal prodotto. Se un
  giorno servisse una cache (per costo di rete, non per verita'), va invalidata da un evento vero
  di Home Assistant, non da un timer — vedi `home_space/topology.py` per la stessa scelta gia'
  fatta sui registri della casa.

Nessuna delle due e' bloccata da un lavoro a monte: sono scartate come **scelte**, non rinviate come
**dipendenze**. Riaprirle richiede una richiesta nuova, non solo tempo libero in uno sprint.

### `non_disponibile` (singolare, su `view`) non e' descritto da nessuna parte

`origine: rilevata nel giro di correzioni del Task 2 di «gli strumenti rifiutano invece di
indovinare», 06/09/2026` · `nessun documento`

`view` puo' rispondere con la chiave `non_disponibile: True` (singolare, su un'area/entita'/
dispositivo/automazione/script non trovato quando un registro o un file non e' stato letto per
intero -- `queries.py::_not_found_detail`/`_view_behavior`) -- ma **nessuna tool description ne'
nessun documento la spiega al modello**. Il plurale `non_disponibili` (i registri dell'anagrafe
caduti) e' documentato in piu' punti; questo singolare no, e il modello riceve la chiave senza che
nessuno gli abbia detto che significa «non ho potuto controllare, potrebbe esistere lo stesso» e non
«non esiste». Misurato leggendo il codice durante le correzioni sui punti ciechi di `search`/`view`
(Task 2): non e' un difetto di comportamento -- il valore e' corretto -- e' un buco di
documentazione dello stesso genere che il Task 2 ha appena chiuso per gli altri campi nuovi
(`nulla_riconosciuto`, `solo_una_parte`, poi tolto).

### 24 entita' in tre domini senza fonte per `supported_features`

`origine: misurata dal Task 3 di «gli strumenti rifiutano invece di indovinare», 06/09/2026 --
aggiornata lo stesso giorno dopo una review indipendente, e di nuovo il 07/09/2026 (Task 5,
review finale del ramo, per far tornare il rimando di `topology.py`)` · `nessun documento`

**Aggiornamento (stessa giornata del Task 3):** la voce nasceva come "22 entita' in otto domini
senza fonte": una review indipendente ha misurato che CINQUE di quegli otto domini (`siren` 4,
`todo` 4, `alarm_control_panel` 1, `calendar` 2, `remote` 2 -- 13 entita') hanno in realta' una
fonte stabile e identica sui due tag (`2024.7.0`/`2026.9.1`) -- lo stesso lavoro delle altre
tabelle, semplicemente non ancora fatto. Verificate e chiuse nella stessa fetta
(`topology._FEATURE_NAMES`). Un sesto, `conversation` (1 entita'), e' un caso diverso -- il suo
`ConversationEntityFeature` non esiste a `2024.7.0` e nasce prima di `2026.9.1` -- chiuso comunque,
la nascita di un bit dentro la finestra supportata non e' un problema per la decodifica (vedi il
commento in `topology.py`).

Restano FUORI, confermato su entrambi i tag (nessuna traccia di un `EntityFeature`, non "non ancora
controllato"): `device_tracker` (4 entita'), `switch` (4 entita') e `button` (16 entita' --
verificato fin dalla prima consegna del Task 3, `__init__.py`/`const.py` di entrambi i tag: nessun
`ButtonEntityFeature` esiste, ne' a `2024.7.0` ne' a `2026.9.1`). Diversamente dai sei chiusi sopra,
per questi tre non c'e' "lo stesso lavoro delle altre" da fare -- il dominio non ha bit da
decodificare. Restano qui non perche' ci sia lavoro pendente, ma perche' un lettore futuro che si
chiede "perche' `switch` (o `button`) non ha capacita'?" trovi la risposta gia' misurata invece di
doverla rimisurare -- ed e' la stessa ragione per cui `topology.py`, accanto al conteggio "24
restano fuori per mancanza di fonte", rimanda proprio qui.

### `state_class` non arriva mai a `view` -- solo a `trend`

`origine: misurata dal Task 5 di «rifiutare e importare», 07/09/2026, durante il giro di
correzioni della review indipendente` · `nessun documento`

`entity_cache._to_minimal` conserva `state_class` (`measurement`/`total`/`total_increasing`) come
chiave DI PRIMO LIVELLO del dizionario minimale -- non dentro `attributes` (`_DOMAIN_ATTRS`) --
per servire `ha_vocabulary.produces_statistics` (`tools.py::_trend`, che legge
`self._state_readings()` direttamente). `topology.live_mirror`, il proiettore condiviso da
`view`/`cerca`/il nucleo, NON porta questa chiave: il suo sesto dizionario (`attributi`) e'
costruito solo da `e.get("attributes")`, e `state_class` non ci vive. Risultato: `view`
(`queries.py`) non puo' mai citare `ha_vocabulary.STATE_CLASS_MEANING` su un'entita' -- quel
vocabolario (Task 4) resta importato ma irraggiungibile da questa porta, mentre `_trend` lo
consulta gia' (indirettamente, via `produces_statistics`) da un'altra.

Non e' un buco nel comportamento di `_trend` (funziona, ed e' quello che il capitolato chiedeva
di leggere): e' un buco di CONOSCENZA gemello a quelli che il Task 3 ha chiuso per
`supported_features`/`assumed_state`/`entity_category` -- un fatto che Home Assistant dichiara e
che una sola porta (`_trend`) legge, mentre l'altra (`view`) non puo'. Non l'ho chiuso di mia
iniziativa nel Task 5: la regola che quel task doveva citare (diagnostica + nessuna classe +
nessuna unita') non ha bisogno di `state_class`, e aggiungerlo a `live_mirror` solo per "poterlo
citare" senza un secondo consumatore reale sarebbe stata una porta nuova senza un dato che la
attraversa davvero -- la stessa disciplina per cui `capacita'`/`stato_presunto` sono entrati SOLO
quando la decodifica produceva qualcosa.

### ~~«Cosa sto guardando» stampa i soggetti grezzi, gli episodi no~~ — CHIUSA il 15/09/2026

**Chiusa dalla riscrittura della pagina dell'osservatore.** `describeWatchedSubject` esiste, è
condivisa, e la lista di «cosa sto guardando» ci passa (`watcher-route.js:407`) come già facevano
gli episodi — con in più un avviso per il gruppo, detto una volta, quando tutte le voci sotto sono
identificatori e non nomi.


`origine: collaudo col browser della v3.22.1, 07/09/2026` · `nessun documento`

Nella pagina dell'osservatore le **due liste sono rese in due modi diversi**, e una sola e' stata
corretta. `hiris/app/static/config/watcher-route.js:257` scrive `v.soggetto` **tale e quale**:

```
integrazione:01K2CK4GG287VKK18M5J788MRQ
log:aioamazondevices@components/alexa_devices/coordinator.py:192
log:homeassistant.components.hydrawise@helpers/update_coordinator.py:481
```

Le righe **826** e **885** della stessa pagina — gli **episodi** — passano invece da
`protagonistName()`, la funzione corretta durante la fetta «le tracce e il log» proprio perche' un
prefisso tecnico non resti a schermo. Due elenchi sulla stessa pagina, uno corretto e uno no: e' la
forma ricorrente dell'**elenco incompleto**, e nessuna prova poteva vederlo — e' resa, e si vede
solo aprendo il gruppo in un browser vero.

**Il difetto e' precedente alla fetta, ma la fetta lo ha reso molto piu' visibile**: quel gruppo
aveva due voci, ora ne ha **diciannove**, di cui **diciassette sono percorsi di file**.

`protagonistName(o)` non si puo' riusare com'e': lavora su un episodio, che porta `titolo` e
`dominio`; una voce di «cosa sto guardando» porta solo `{soggetto, gamba, provenienza}`. Serve una
resa che parta dal **solo soggetto** — «registro: `aioamazondevices`», «un'integrazione non
caricata» — e la si condivide con `protagonistName` invece di scriverne una seconda.

### Il README documenta sei rotte che non esistono

`origine: collaudo col browser della v3.22.1, 07/09/2026` · `nessun documento`

`README.md:427-437` elenca nove rotte del pannello: sei hanno il **nome sbagliato**. Il prodotto
vivo usa `#/tree`, `#/memory`, `#/agenda`, `#/constructions`, `#/watcher`, `#/settings`; il README
dice `#/albero`, `#/memoria`, `#/promesse`, `#/costruzioni`, `#/osservatore`, `#/impostazioni`.
Solo `#/`, `#/models` e `#/usage` combaciano. La riga di `#/promesse` parla inoltre di «promesse»,
nome sostituito da **«Impegni»** nella v3.21.0.

E' il residuo di una rinomina che ha toccato il codice e non il documento — verificato aprendo il
pannello col browser e confrontando gli `href` veri con la tabella.

### Il nome di un'automazione rotta e' gia' in memoria, e «cosa sto guardando» non lo usa

`origine: review indipendente del fix per E2, 07/09/2026` · `nessun documento`

E' l'**opposto simmetrico** del difetto appena chiuso in «"Cosa sto guardando" stampa i soggetti
grezzi, gli episodi no» (sopra): li' un prefisso tecnico veniva stampato perche' nessuno sapeva
tradurlo dal solo soggetto — qui il nome leggibile **esiste gia' in memoria** e non arriva alla
pagina.

`hiris/app/mind/watcher.py:148` (`self._marked_automations: dict[str, str | None]`) tiene, per
ogni automazione che ha scattato almeno una volta, `entity_id -> nome amichevole` (il nome che
`automation_triggered` ha dichiarato al primo scatto — vedi `mark_automation`, linea 229).
`self._automation_faults` (linea 167, un `set[str]` dei soli `entity_id` con un errore aperto) e'
un **sottoinsieme delle chiavi** dello stesso dizionario: ogni automazione guasta e' anche
un'automazione marcata, e il suo nome amichevole e' li', pronto.

Ma `watching()` (linea 868) costruisce il soggetto di un'automazione guasta cosi':

```python
automation = ({"soggetto": s, "gamba": "buono stato", "provenienza": "pavimento"}
              for s in self._automation_faults)
```

`s` e' l'`entity_id` grezzo (poi prefissato `automazione:` da chi chiama) — `self.
_marked_automations.get(s)` non viene mai consultato. Il frontend (`describeWatchedSubject`,
`watcher-route.js`) rende quindi sempre `"Automazione: automation.spegni_luci_notte"`, mai il nome
che il proprietario avrebbe letto in Home Assistant. Non e' un nome inventato — la legge di
non-invenzione (§E2) e' rispettata — ma e' un nome **trattenuto**: disponibile a costo zero, mai
passato.

**Non toccato in questo giro**: la correzione tocca il contratto di `watching()` (un campo
nuovo, o un soggetto arricchito) e i suoi due lettori (`describeWatchedSubject` **e**
`protagonistName`, per coerenza con gli episodi guasto che citano un'automazione) — un cambio di
forma dei dati, non una resa, e merita la sua fetta.

### Il conteggio per aree perde le entita' senza area, e la vista di un'area e' troppo grande

`origine: batteria di prove funzionali in chat sulla casa vera, 07/09/2026` · `nessun documento`

Alla domanda «quante luci ho in casa, e quante sono accese adesso?» il modello ha risposto
**«Totale luci in casa: 43»** — le luci sono **50** — e «accese ora: almeno 1», mentre erano **7**.

**Due difetti, non uno.**

**① Il totale e' detto come totale, ma e' un totale PARZIALE.** Il modello ha iterato **per area**,
e le entita' **senza area** non appartengono a nessuna: sette luci sono rimaste fuori dal
conteggio senza che niente lo dichiarasse. La frase «Totale luci in casa: 43» e' l'unico punto in
cui quella risposta afferma piu' di quanto sapesse — tutto il resto era dichiarato con cura.
Serve che chi conta per aree sappia **quante cose restano fuori dalle aree**, o che la via per
contare una specie di entita' non passi dalle aree.

**② La vista di un'area e' troppo grande perche' il modello la legga.** Parole sue: *«le 4 luci
dell'area Telecamere non sono riuscito a verificarle in questo giro (**la risposta dello strumento
per quell'area era troppo grande da leggere**)»*. E' la stessa famiglia della ripetizione della
regola su un dispositivo con 53 sensori, corretta il 07/09 restringendo `regola` alla vista di una
singola entita': **una vista d'insieme che cresce con la casa finche' non e' piu' usabile**.
Va misurato quanto pesa `view` su un'area vera prima di decidere la cura.

**Cio' che ha funzionato**, e va detto perche' e' meta' del reperto: il modello **non ha inventato
niente**. Ha detto «almeno 1» invece di «1», ha dichiarato quante ne aveva verificate (39 su 43),
ha nominato l'area che non e' riuscito a leggere **e il perche'**, e si e' offerto di ricontrollarla.

### Due aree dell'Albero sono enormi quando le si apre

`origine: misura del 07/09/2026 durante il collaudo` · `documento: indagine-albero-lungo.md (fuori da git)`

**Decisione rinviata dal proprietario**, che vuole guardarla dal vivo prima di scegliere.

I numeri, riprodotti sui dati veri: la pagina all'apertura sta a **1.784 px**; con tutte e
16 le aree aperte arriva a **81.941 px**, e due aree sole ne fanno il **56%** — «Telecamere»
(288 righe) e «Senza area» (376). A 375 px il ritorno a capo quasi raddoppia il costo per
riga (69,6 px contro 37,5), ma **non è la causa**: anche a 1280 px restano circa 140
schermate di roba aperta. È quantità, non larghezza.

Le forme possibili: un troncamento con «mostra altre» sulle sole aree oltre le ~100 righe,
una ricerca lato client (i dati sono già tutti scaricati, zero chiamate in più), o niente.
**Non è un difetto**: è una casa grande resa per intero.

### Otto domini su dieci in `_OPERABLE` non possono arrivare

`origine: verifica del 07/09/2026, nata da un reperto laterale di un'indagine` · `nessun documento`

`mind/facts.py:92-94` elenca dieci domini che «si accendono e si spengono», e accanto mantiene
a mano la tabella dei loro stati di riposo. Ma `baseline.aspect()` — che decide **quali**
entità entrano nell'archivio — ammette solo `person`, `lock`/`alarm_control_panel`/`siren`,
`device_tracker` con `source_type: gps`, `climate`, `cover` e alcune classi di
`binary_sensor`/`sensor`.

Dei dieci ne possono arrivare **due**: `climate` e `cover`. Gli altri otto — `switch`,
`light`, `fan`, `media_player`, `vacuum`, `valve`, `humidifier`, `water_heater` — sono
mantenuti per entità che non arriveranno mai.

**La domanda non è tecnica**: o quella lista si pota, o il pavimento si allarga perché una
luce accesa da sei ore è davvero qualcosa che il proprietario vuole sapere. La prima è
pulizia, la seconda è prodotto — e la decide lui, non il codice.

### `_logga_uso` potrebbe contare come riuscito un turno fallito

`origine: dubbio lasciato dall'implementer dell'abbonamento, 07/09/2026` · `documento: task-6-report.md (fuori da git)`

Il collegamento del successo del ponte al registro degli esiti è stato messo in
`server.py::_submit_chat_reply`, **dopo** il filtro che scarta le cinque sentinelle d'errore —
proprio perché `agent/runner.py::_logga_uso` gira **prima** del controllo su `rc`/`has_result`.

Ne segue un sospetto che riguarda **Consumi**, non il ponte: se un turno fallisce ma porta
comunque un `usage` non vuoto, `_logga_uso` lo conta lo stesso. In quel caso il numero dei
turni di Consumi sarebbe gonfio.

**Non verificato**: accertarlo richiede un turno di chat vero, che costa denaro. E non si
corregge un numero prima di aver misurato di quanto sbaglia.

### L'anagrafe dei tipi di entità — HIRIS smette di tenere liste a mano

`origine: il proprietario, 07/09/2026` · `documento: indagine-cosa-ha-pubblica.md (in corso, fuori da git)`

**Scelta dal proprietario come lavoro successivo al rilascio della 3.22.3**, con parole sue:

> *«È importante che HIRIS conosca tutte le tipologie di entità possibili in HA e, se ci sono, le
> sappia interpretare. Se oggi ci sono liste manuali e HA le fornisce, facciamo in modo che HIRIS
> le recuperi e, se si accorge che sono obsolete, le aggiorni — questo per tutto.»*

**Il difetto, misurato il 07/09.** HIRIS non ha un elenco dei tipi di entità: ne ha **tre**,
scritti a mano, che non concordano fra loro, e **nessuno dei tre è derivato da Home Assistant**.

| lista | dove | quanti | cosa decide |
|---|---|---|---|
| `aspect()` | `mind/baseline.py` | 7 rami di dominio | quali entità entrano nell'archivio |
| `_FEATURE_NAMES` | `home_space/topology.py` | 18 domini | quali capacità sa decodificare |
| `_OPERABLE` | `mind/facts.py` | 10 domini (**2 raggiungibili**) | quali si accendono e si spengono |

Sulla casa vera ci sono **30 domini**; Home Assistant ne dichiara **53** e li pubblica lui stesso
(`frontend/get_translations`, `category: "entity_component"` — la chiamata che la v3.22.3 ha
appena imparato a fare). Domini presenti in casa di cui **nessuna** delle tre liste dice niente:
`update` (53 entità), `button` (70), `number` (35), `select` (19), `input_boolean` (11), `event`,
`tag`, `script`, `zone`, `image`.

Gli otto domini orfani di `_OPERABLE` non erano un caso isolato: erano **il sintomo** di questo.

**Il disegno, corretto dal proprietario il 07/09** dopo che una ricognizione aveva
raccomandato di tenere le liste separate:

> *«Ma non possono essere una lista sola dove si accede con 3 metriche per evitare
> sovrapposizioni? Ti ricordo le regole del progetto.»*

**Ha ragione, e le fondamenta lo dicono in tre punti su quattro.** Oggi `light` vive in
`_FEATURE_NAMES`, vive in `_OPERABLE` e **non** vive in `aspect()`: tre case per lo stesso
soggetto (**nessun doppione**), tre forme da tre porte (**consistenza**), e nessuna che lo
interpreti da sola (**atomicità**). La raccomandazione di tenerle separate scambiava **tre
domande per tre case**: le domande restano tre — cosa esiste, cosa sa fare, se serve
all'obiettivo — ma si rispondono da **una riga sola per dominio, con tre metriche per
accedervi**.

**E il guadagno non è solo di forma**: con una casa sola il censore diventa **uno** — un
dominio pubblicato da HA che non ha una riga viene nominato, e basta. Con tre liste
servirebbero tre censori, e il primo che qualcuno dimentica di scrivere ricrea il buco di oggi.

**Una cosa sta dentro la riga, non fuori**: la riga mescola fatti **importati** da HA e
**giudizi nostri** — *«questa entità serve all'obiettivo della casa»* HA non potrà mai dircelo.
Quindi **ogni campo dichiara da dove viene**. Una casa sola, provenienza per campo: così un
giudizio nostro non si può leggere come un fatto di Home Assistant.

**Ed è questa la parte che rende la voce viva** invece di un file da aggiornare a mano: un
dominio che HA ha e che **nessuna nostra lista ha mai classificato deve poter essere nominato**.
Sapere che «la casa è più nuova del vocabolario» — cosa che `ha_vocabulary.py` sa già fare — non
basta: non dice **cosa** è cambiato. La differenza è fra «le liste sono aggiornate» e «le liste
non possono più derivare in silenzio».

**Cosa la ricognizione del 07/09 ha misurato, e cambia le dimensioni del lavoro:**

- **Le liste non sono tre: sono ventuno** nel prodotto, più tre copie fissate nei test.
- **HA pubblica quasi tutto**, con un comando solo che la v3.22.3 già fa: 53 domini caricati,
  stati canonici per dominio, `device_class` per dominio (62 su `sensor`, 58 su `number`, 28
  su `binary_sensor`), valori legali di `state_class` — 801 chiavi, 63 KB, **41 ms**, già
  tradotti nella lingua della casa.
- **I nomi dei bit di `supported_features` no** — restano `IntFlag` nel sorgente — ma i
  **valori numerici** li pubblica il registro dei servizi: abbastanza per **denunciare** un bit
  che non sappiamo nominare, non per nominarlo.
- **Un commento nel nostro codice è falso**: `facts.py:14-27` afferma che HA non dichiara da
  nessuna parte quali domini si accendono e si spengono. Lo dichiara: `turn_on` +
  `turn_off`/`toggle` nel registro dei servizi isolano **16 domini**. La derivazione non
  coincide con `_OPERABLE` (perde `vacuum`, guadagna `automation`, `script`, `input_boolean`,
  `camera`, `remote`, `siren`), quindi **sorveglia** invece di sostituire.
- **Quattro tabelle di traduzione in `topology.py` vanno cancellate**: traducono a mano ciò che
  ora scarichiamo già tradotto, e lo fanno peggio (`_STATE_TRANSLATION` è cieca al dominio,
  `_READABLE_HVAC_ACTION` non ha `defrosting`).

**E il censore, girato una volta sola il 07/09, ha già trovato difetti veri** — nessuno dei
quali morde su questa casa, che non ha né boiler né serrature né tosaerba, ma tutti latenti:

| difetto | conseguenza |
|---|---|
| 5 stati di `water_heater` (`eco`, `electric`, `gas`, `heat_pump`, `high_demand`) né fra i riposi né fra gli ignoti | un boiler in `eco` apre un episodio **che non si chiude mai** |
| 3 stati di `lock` (`jammed`, `locking`, `unlocking`) nella stessa condizione | e `lock` l'archivio lo raggiunge davvero |
| `_CLASS_MEANING["damper"]` irraggiungibile | `damper` è una classe di `cover`, non di `binary_sensor` |
| 5 domini con bit di capacità e nessuna tabella | `ai_task`, `assist_satellite`, `humidifier`, `lawn_mower`, `lock` |

È esattamente il difetto contro cui il commento di `facts.py` metteva in guardia — *«un dominio
aggiunto a metà produce oggetti che non si chiudono mai»* — trovato da una macchina in un giro
solo, dopo mesi in cui nessuna persona l'aveva visto.

**La forma esiste già in casa**: `home_space/ha_vocabulary.py` importa le specifiche di HA
dichiarando la fonte e la versione da cui vengono. Quello che manca è estenderla a tutto e
renderla capace di accorgersi.

**Una legge da rispettare nel disegno**: quando la lettura da HA non riesce, *«non ho potuto
chiedere»* e *«non c'è»* sono **due fatti diversi**, e chi produce il motivo lo etichetta.

### ~~L'analista — chi trasforma le osservazioni in qualcosa di funzionale~~ — CHIUSA il 15/09/2026

**Fatta dallo sprint «i tre attori»** (spec del 10/09, §10). L'analista gira, legge trenta giorni
di misure, e sulla casa vera ha prodotto **cinque osservazioni** con gli inneschi 1 e 3 della spec
— il secondo, «stabile e costa», non è mai comparso, ed è l'esempio che la spec porta come il più
prezioso — il perché di ciascuna e cosa cambierebbe. Non scrive numeri: nomina la misura, e il codice ci attacca
il valore — è ciò che impedisce a un modello di inventare una cifra. Resta sotto, come voce sua,
il testo con cui il proprietario l'ha chiesta.


`origine: il proprietario, 07/09/2026` · `nessun documento`

**Sprint suo, dichiarato tale dal proprietario.** Non è una correzione e non entra in nessuna
fetta in corso.

> *«Mettere insieme le letture dell'osservatore spetterà all'analista, che avrà proprio questo
> compito: analizzare le letture dell'osservatore per raggruppare informazioni, creare tendenze,
> e trasformare in qualcosa di funzionale un'osservazione dettagliata e più estesa possibile.»*

**Perché adesso**: l'osservatore è vivo in produzione e scrive. Fin qui il lavoro è stato tutto
sul **leggere meglio** — l'appartenenza, la salute senza soglia, il guasto con nome e condizione,
le tracce, i calendari, i nomi e gli stati. Nessuno però **legge ciò che l'osservatore ha
scritto**: gli episodi si accumulano e restano un elenco.

Questa voce è il lettore che manca. E ha una conseguenza sul resto del registro: **osservare di
più ha senso solo se qualcuno poi mette insieme** — quindi ogni fetta che allarga il pavimento
(vedi «La luce accesa col sole alto») ha il suo valore vero **qui**, non dove nasce.

### La luce accesa col sole alto

`origine: il proprietario, 07/09/2026, rispondendo alla domanda sui domini orfani di _OPERABLE` · `nessun documento`

**Criterio dettato dal proprietario**, parole sue:

> *«Una luce accesa da sei ore sì, se fuori non c'è buio; altrimenti ci può stare.»*

**È un discriminante, non una soglia** — la stessa forma già scelta per la salute delle
integrazioni, dove una percentuale fu scartata a favore di `sensor.uptime`. E la casa ce l'ha
già: **`sun.sun`** esiste e vale `above_horizon` / `below_horizon`. Una entità sola, gratis.
Ci sono anche 4 sensori di illuminamento, ma sono **interni**: misurano la stanza, non il fuori.

**Il perimetro si restringe da sé.** Misurato sulla casa vera: `light` **43 entità attive** (50
in tutto), `switch` 149, `media_player` 7, `valve` 4, e `fan`/`vacuum`/`humidifier`/
`water_heater` **zero**. Il criterio parla di luci, e un interruttore non ha niente a che fare
col buio fuori: il pavimento crescerebbe di **~43 entità**, non di 203.

**La durata non va dichiarata**: l'archivio trasforma già in episodio ciò che dura, quindi «da
sei ore» viene da sé senza un numero scritto a mano.

**La forma nuova che serve, ed è il costo vero.** Oggi l'archivio apre un episodio guardando
**una** entità. Questo criterio è una **congiunzione di due stati** — la luce accesa *e* il sole
sopra l'orizzonte — e ne segue che l'episodio deve nascere **all'alba** per una luce già accesa
da prima, non nell'istante in cui la si accende. Non è difficile, ma è una forma che
l'osservatore non ha, e va disegnata invece che infilata.

**Ordine deciso**: viene **dopo** «L'anagrafe dei tipi di entità». Aggiungere `light` al
pavimento prima di quella vorrebbe dire scrivere la **quarta** lista a mano invece di toglierne
tre.

### Il nucleo è statico, e il proprietario chiede se non sia povero

`origine: il proprietario, 07/09/2026, discutendo la completezza degli attributi` · `nessun documento`

> *«Il nucleo va bene crearlo per passare qualcosa che non sia tutta la casa ai modelli, ci
> permette di risparmiare token — ma se non è dinamico in base al quesito, non credi sia povero
> di informazioni?»*

**I numeri, misurati sul ponte il 07/09** (105 turni), che vanno letti prima di progettare:

| | |
|---|---|
| token in **freschi** | **662** in totale, su 105 turni — sei per turno |
| token letti **dalla cache** | **5.603.549** |
| token **scritti** in cache | 1.914.948 |

**Il 99,99% del contesto non si paga a ogni turno: si rilegge.** Ed è possibile *proprio perché* è
identico. Un contesto che cambia a ogni domanda non si rilegge: si riscrive, e la riscrittura
costa più di una lettura fresca.

**Ma il proprietario ha ragione sul difetto, e sbaglia bersaglio chi risponde «lasciamolo
statico».** Il nucleo non è povero di dettagli: **tronca**, e il codice lo dichiara misurandolo
(`briefing.py:277`) — *«citando tutti i nomi sopravvivono 7 aree su 20 invece di 17»*.

> Il difetto vero non è «non sa che il termostato arriva a 40 gradi»: è **«non sa che quel
> termostato esiste»**, e allora non può nemmeno andarlo a cercare. HIRIS ha sedici strumenti: il
> compito del nucleo non è contenere la casa, è darne una **mappa** abbastanza buona da far capire
> cosa vale la pena chiedere. Un nucleo che tronca tredici aree su venti non fallisce come
> riassunto: fallisce come mappa.

**Due cose da sapere prima di scrivere una riga:**

1. **La cache dipende da DOVE sta il pezzo che cambia.** I ~53.000 token riletti a ogni turno non
   sono il nucleo (≈1.500): il grosso è il prompt di sistema più le descrizioni dei sedici
   strumenti. Un'appendice variabile messa **in coda**, dopo tutto ciò che è stabile, invalida solo
   se stessa. Dinamico *in coda* costa quasi niente; dinamico *in testa* costa dieci volte tanto.
2. **Scegliere il contesto dalla domanda è recupero, e il nostro recupero è debole.** È la stessa
   lacuna ancora aperta in «Scelti»: `search` non distingue un candidato **unico** da uno
   **certo**. Un recupero che sbaglia consegna al modello un contesto **sbagliato e sicuro di sé**,
   e il modello non sa cosa gli manca — peggio di un contesto generico, che almeno si dichiara
   tale.

**La forma proposta**, non decisa: due strati. Una **mappa stabile in testa**, completa su *cosa
esiste e dove*, mai troncata sulle aree — è ciò che rende possibile chiedere, ed è ciò che la cache
rilegge gratis. E un'**appendice variabile in coda**, scelta sulla domanda, che porta il dettaglio
e **dichiara di essere una selezione**, così il modello sa che sotto c'è altro.

**E la misura che va fatta prima**: quante volte il modello sbaglia o gira a vuoto perché il nucleo
era povero? Le tracce e il log ci sono dalla v3.22.0 — **si può guardare invece di supporre**. Se
il modello compensa già bene con gli strumenti, il lavoro vero è solo smettere di troncare la
mappa; se si perde, l'appendice serve davvero.

**Il collegamento con «Il vocabolario dei tipi», dichiarato per non lasciarlo al caso**: rendere
completi gli attributi aumenta la pressione sul tetto dei 6.000 caratteri. La decisione presa è
che **la completezza va nel dettaglio di una entità, non nel nucleo** — altrimenti la prima persona
che ci lavora la prende per caso.

**Si incrocia con «L'analista»**: è lui che dovrebbe decidere *cosa* mettere in quell'appendice.

### `chat_stream` vive solo per i test

`origine: audit delle fondamenta, «sotto la soglia dei dieci» n.8, 09/09/2026` · `nessun documento`

Tre metodi -- `ClaudeRunner.chat_stream`, `OpenAICompatRunner.chat_stream`, `LLMRouter.chat_stream`
-- e la rotta SSE di `api/handlers_chat.py::handle_chat` (dietro `Accept: text/event-stream` o
`{"stream": true}`) non hanno **nessun** lettore di produzione: nessun file in `static/` manda
quell'header o quel campo (grep, zero occorrenze), il ponte (il canale della CLI di Claude Code)
ha una strada sua e non passa mai da `LLMRouter.chat()`/`.chat_stream()`, e
`docs/design/2026-08-05-mappa-funzionalita.md` dichiara che la pagina chat "funziona, senza
streaming" e che questo TIENE. Vivono per i test: **12 file** `.py`, rimisurato il 09/09/2026 (`grep -rl
chat_stream tests/`) -- `test_base_prompt_memory.py`, `test_base_prompt_split.py`,
`test_chat_briefing.py`, `test_chat_sse.py`, `test_claude_runner.py`, `test_composition_order.py`,
`test_llm_router_policies.py`, `test_model_invariants.py`, `test_openai_compat_runner.py`,
`test_runner_catalog.py`, `test_runner_parity.py` e tre soli marginali.

**La decisione (fondamenta 4) e' fra due strade, nessuna delle due presa qui:**

1. **Cancellare** -- il metodo su tre runner, la rotta SSE, e i 12 file di prova che lo esercitano
   (alcuni solo di striscio, altri -- `test_chat_sse.py`, `test_openai_compat_runner.py`,
   `test_runner_catalog.py` -- a fondo). E' un lavoro con la sua verifica, non l'effetto
   collaterale di una correzione sotto soglia.
2. **Collegare** -- dargli un lettore vero (streaming reale nella pagina chat), che e' una
   FUNZIONALITA' NUOVA contraria a quanto la mappa delle funzionalita' dichiara oggi, e che
   richiederebbe prima di chiudere un gap reale: `LLMRouter.chat_stream` non ripiega su un secondo
   backend come fa `chat()` (commento originale: "no fallback in streaming (as today)") e non
   scrive mai nel registro degli esiti (`.successo`/`.fallimento`) che lo stesso modulo alimenta
   per ogni turno sincrono -- collegarlo com'e' oggi farebbe mentire la pagina Consumi su ogni
   turno in streaming.

Chi sceglie questa voce per uno sprint decide fra le due, con la sua verifica.

### Gli undici stati che non sono né riposo né acceso

`origine: il proprietario, 09/09/2026, dopo la misura della fetta «le sei liste»` · `documento: docs/design/2026-09-07-l-anagrafe-dei-tipi.md §17`

**Il fatto misurato**: undici stati che questa casa pubblica non sono riposi **e** non sono fra
quelli che il nucleo annuncia — `cover`/`valve` in `opening`/`closing`, `lock` in
`locking`/`unlocking`/`opening`/`jammed`, `media_player` in `paused`/`buffering`, `vacuum` in
`paused`. **Dieci degli undici il vocabolario li dichiara già «sta funzionando»**: non è un buco
di conoscenza, è un disaccordo fra due giudizi del prodotto.

**Deciso dal proprietario**: si annunciano **solo quelli che significano qualcosa**, tipo per tipo,
con la ragione scritta. Non tutti (gonfierebbero un riassunto che tronca già) e non nessuno.

**La selezione proposta e il criterio che la governa** — *si annuncia ciò che farebbe alzare dalla
sedia, non ciò che è tecnicamente «in funzionamento»*:

| stato | annuncio | perché |
|---|---|---|
| `lock` in `locking` / `unlocking` / `opening` | **sì** | vuol dire che **qualcuno è alla porta**: è una notizia mentre accade |
| `vacuum` in `paused` | **sì** | un robot fermo a metà lavoro di solito è **bloccato**, non a riposo |
| `cover` / `valve` in `opening` / `closing` | no | dura secondi: quando lo si legge è già finito, e l'archivio lo registra comunque |
| `media_player` in `paused` | no | non è una notizia: è qualcuno andato in cucina |
| `media_player` in `buffering` | no | rumore tecnico |
| `lock` in `jammed` | **è un guasto** | deciso il 08/09; aspetta la fetta «il genere che dipende dallo stato» |

**Costo**: piccolo. La misura del disaccordo è già pinnata da
`tests/test_notable_states_complement.py`, che arrossisce se il divario cambia.

### Una quarta sede dei prefissi «non è un'entità»

`origine: trovata durante la chiusura del rilievo 10, 09/09/2026` · `nessun documento`

I quattro prefissi che dicono «questo soggetto non è un'entità» erano scritti in **tre** posti nel
Python, ora unificati in `mind.facts.NOT_ENTITY_PREFIXES`. Ma ce n'è una **quarta**, mai nominata
dall'audit: `hiris/app/static/config/watcher-route.js` li duplica.

È un doppione **attraverso il confine dei linguaggi**, che nessuno dei due cancelli sui doppioni
guarda. Lasciata aperta perché fuori dal perimetro di quella chiusura.

### ~~Il sapere di HIRIS — il catalogatore, il resoconto, le porzioni~~ — CHIUSA il 15/09/2026

**Fatta a metà, e va detto quale metà.** Il disegno del 09/09 è stato sostituito il 10/09
(`docs/design/2026-09-10-i-tre-attori.md`): il catalogatore non sopravvive come attore, **il
pavimento esce** (`mind/baseline.py` cancellato con la 3.26.0), e nascono il registro delle
operazioni, le ricette e il resoconto giornaliero. **Le gambe NON sono uscite**: `ASPECTS` e
`aspect_of` vivono in `home_space/type_vocabulary.py`, `GENRES` e `genre_for` in `mind/facts.py`, e
girano ogni notte dentro `aggregate_day`. Quando ho marcato questa voce chiusa, il 15/09, ho
ripetuto «gambe e pavimento escono» come se fosse un fatto: non lo era, e l'ha trovato la revisione
indipendente lo stesso giorno. Vedi la voce nuova «§13 dice di cancellare le gambe e i generi».
Tutte e tre vivono in produzione, col sapere interrogabile da una pagina. Le tre mancanze del
09/09 sono chiuse: la casa per ciò che HIRIS deduce è `sapere.db`, il resoconto giornaliero
esiste e ne nascono le tendenze, e le porzioni sono le tre forme di `GET /api/mind/report`.
Il testo originale resta sotto: è la cronaca di come ci si è arrivati.


`origine: il proprietario, 09/09/2026, discutendo l'impianto solare` · `documento: docs/design/2026-09-09-il-sapere-di-hiris.md`

**Sprint successivo, dichiarato fondamentale dal proprietario**, con il permesso esplicito di
**distruggere e ricostruire** se il disegno lo richiede.

**Il vincolo nuovo che cambia tutti gli altri: HIRIS verrà distribuito ad altri utenti.**

Tre attori: il **catalogatore** (cos''e questa cosa — dedotto dal modello, verificato sulla
documentazione di HA), l'**analista** (mi serve per la domanda dell'obiettivo?), l'**osservatore**
(raccoglie ci'o che gli 'e stato detto — esiste gi'a e gira).

**Le tre mancanze misurate il 09/09**: non c''e una casa per ci'o che HIRIS deduce (la quarta
provenienza non ha un tetto); non esiste il **resoconto giornaliero** da cui nascono le tendenze;
e HIRIS **non sa prendere porzioni** — il modello riceve un testo fisso di 6.800 caratteri, e sotto
non c''e niente da cui pescare.

**E il vocabolario dei tipi 'e un file nel repository**: non esiste nessun posto dove una singola
casa scriva ci'o che HIRIS ha imparato. Su questa casa funziona perch'e il proprietario risponde;
**quello non si distribuisce**.

Il caso che ha fatto emergere tutto: **otto entit'a dell'impianto solare con otto ruoli diversi e
un solo `device_class`** (`power`), indistinguibili dal consumo di una presa.

Tutto il resto — misure, decisioni gi'a prese, domande in pausa, sospesi — sta nel documento.

**AGGIORNAMENTO 10/09/2026 — il disegno e' cambiato, la spec e'
`docs/design/2026-09-10-i-tre-attori.md`.** Misurando sulla casa vera e' emerso che **il problema non
e' il riconoscimento**: Home Assistant dichiara gia' quasi tutto (100% delle entita' ha un
`unique_id`, 64% un `translation_key`, il 99% dei dispositivi il produttore), e il difetto e' che
`casa.db` ne conserva una **copia impoverita** che butta `translation_key`, `unique_id`,
`original_name` e il dispositivo come oggetto. Di conseguenza: il catalogatore **non sopravvive come
attore** (restano due attori e una lettura), **gambe e pavimento escono**, e nascono il **registro
delle operazioni**, le **ricette** e il **resoconto giornaliero**. Il documento del 09/09 resta
valido come cronaca di come ci si e' arrivati; **la specifica e' quella del 10/09**.

### Separare `notevole` nei suoi due sensi: «vale la pena raccontarlo» e «e' da sapere subito»

`origine: la fetta «da sapere subito», 18/09/2026` · `documento: docs/design/2026-09-18-da-sapere-subito.md §1`

**Il fatto.** `notevole` risponde oggi a una sola domanda -- *«vale la pena raccontarlo nel
riassunto?»* (`home_space/briefing._is_event`) -- e il nome non lo dice: sembra rispondere anche a
*«e' una cosa da sapere subito?»*. Misurato il 18/09/2026 contro la cronaca vera del 17/09 (75
voci): leggendo il criterio come «stato di lavoro oppure tipo `notevole: si`» finiscono in banda
**71 voci su 75**, e **35 sono accensioni di luce** -- perche' 10 dei 23 `notevole: si` del seme
sono domini interi (`light`, `switch`, `cover`, `fan`, `lock`, `media_player`, `remote`, `siren`,
`vacuum`, `valve`).

**Questa fetta non ha toccato `notevole`**: ha aggiunto un giudizio nuovo, `da_sapere_subito`, che
risponde alla seconda domanda, e ha lasciato `notevole` esattamente dove stava -- resta la parola
del riassunto. Separare i due sensi **alla fonte**, dentro `notevole` stesso, e' un lavoro suo, con
la sua migrazione: le 23 righe del seme che oggi portano `notevole: si` andrebbero riesaminate una
per una, non travasate in blocco su un nome nuovo.

### Separare `lavoro` nei suoi due sensi: «e' successo» e «si sta muovendo»

`origine: la fetta «da sapere subito», 18/09/2026 — trovata decidendo la terza forma del valore` · `documento: docs/design/2026-09-18-da-sapere-subito.md §2`

**Il fatto.** E' la stessa malattia della voce qui sopra, trovata una seconda volta nella stessa
giornata e dentro un'altra parola. `lavoro` dice **due cose diverse** a seconda del tipo:

- per `alarm_control_panel`, `lavoro: {"triggered": ...}` significa **«e' successo»** -- un solo
  stato, il fatto che si vuole sapere;
- per `lock`, `lavoro: {"locking", "opening", "unlocking", "unlocked", "open"}` significa **«sta
  operando»** -- cinque stati, di cui quattro sono transizioni e nessuno e' il guasto. Il guasto
  della serratura, `jammed`, **non e' un lavoro**, e non e' nemmeno il riposo (`locked`).

Misurato: chi legge `lavoro` come «il fatto notevole» -- ed e' cosi' che la regola di
`da_sapere_subito` lo leggeva nella sua prima stesura -- fa entrare in banda **ogni sblocco di
serratura** e lascia fuori **l'inceppamento**.

**Cosa ha fatto questa fetta, e cosa NON ha fatto.** Ha smesso di **appoggiarsi** a `lavoro` dove
non doveva: `da_sapere_subito` porta ora una terza forma del valore, l'elenco degli stati che
contano, e `lock` la usa (`["jammed"]`). **Non ha curato `lavoro`**, e non poteva: quella parola ha
un secondo lettore, la **ragione italiana** che la cronaca mostra accanto all'episodio
(`working_of(...)[stato]`), e le nove righe del seme andrebbero riesaminate una per una -- non
travasate in blocco, esattamente come per `notevole`.

**Cosa servirebbe.** Decidere se «sta operando» e' un giudizio suo (un campo separato, come questa
fetta ha fatto per «da sapere subito») oppure se le due letture convivono per costruzione, e in tal
caso scriverlo dove oggi non e' scritto. Prima si misura quante righe del seme sono di che genere:
oggi sono nove in tutto.

### Normalizzare gli stati ALLA SCRITTURA (elenco e riposo): `["Jammed"]` non avvisa mai, e nessuno lo dice

`origine: la ri-revisione finale della fetta «da sapere subito», 18/09/2026 — misurato eseguendo` · `documento: docs/design/2026-09-18-da-sapere-subito.md §3`

**Il fatto, misurato.** Gli stati si confrontano **normalizzando quello che arriva** (`.strip()
.lower()`, `TypeJudgments.stato_da_sapere_subito` e `mind/facts._is_on`) e lasciando **com'e'
scritto** l'elenco dell'archivio. Chi scrive una maiuscola ottiene una riga che non morde:

| riga scritta | cosa succede |
|---|---|
| `da_sapere_subito: ["Jammed"]` su `lock` | `jammed` → **False**: l'inceppamento non avvisa MAI |
| `riposo: ["Off"]` su `light` (con `da_sapere_subito: si`) | `off` → **True**: lo spegnimento entra in banda |

**La differenza e' il punto, ed e' la ragione per cui vale la pena curarlo.** Nel riposo la svista
fallisce **forte**: uno stato di troppo entra in prima pagina, chi guarda lo vede e si chiede
perche'. Nell'elenco fallisce **muta**: la cosa che si voleva sapere subito non arriva, e nessuno
puo' accorgersi di cio' che non e' successo. In piu' **la pagina la mostra come giusta** -- «solo:
Jammed» si legge esattamente come «solo: jammed».

**Perche' oggi e' cosi'.** Non e' una svista: e' coerenza deliberata col riposo (dichiarata nel
docstring della regola). Un elenco normalizzato e un riposo non normalizzato sarebbero **due modi di
trattare la stessa cosa**, cioe' lo scostamento che questa fetta esiste per evitare. Per questo la
cura non e' «normalizzare l'elenco»: e' **normalizzare tutti e due, e alla scrittura**.

**Cosa servirebbe.** Abbassare gli stati a minuscole in `_parse` (riposo, lavoro, elenco del campo
nuovo) -- oppure rifiutare una maiuscola alla porta con una ragione, che e' la scelta piu' onesta
perche' non cambia in silenzio cio' che il proprietario ha scritto. Da decidere insieme, perche'
tocca tre campi e le righe gia' scritte nell'archivio.

### Una cortesia in meno alla porta: `da_sapere_subito: ["locked"]` su `lock` si scrive, e il RIPOSO diventa notizia

`origine: la ri-revisione finale della fetta «da sapere subito», 18/09/2026 — misurato eseguendo` · `documento: docs/design/2026-09-18-da-sapere-subito.md §2`

**Il fatto, misurato.** Il riposo di `lock` e' `["locked"]`. Scrivendo `da_sapere_subito:
["locked"]` la porta **accetta**, e `stato_da_sapere_subito("lock", None, "locked")` torna **True**:
lo stato di riposo del tipo diventa una notizia. E' l'opposto della domanda a cui il campo risponde
-- *«quando una cosa di questo tipo esce dal suo riposo»* -- scritto in una riga che nessuno ferma.

**Perche' non e' un difetto di questa fetta.** Nessun elenco del seme lo fa, la regola e' coerente
con se stessa (l'elenco dice cosa conta, e chi l'ha scritto ha detto `locked`) e la porta non ha mai
avuto il compito di impedire una correzione *sbagliata*, solo una *incoerente*. E' esattamente la
stessa classe del rifiuto «`si` senza riposo ne' lavoro»: **una cortesia**, non una garanzia.

**Cosa servirebbe.** Una riga in `mind/judgments._check`: se l'elenco interseca il `riposo` gia'
dichiarato per quel soggetto, rifiuto motivato («`locked` e' il riposo di `lock`: non puo' essere
anche cio' che ti fa sapere subito»). **Da valutare nella fetta della pagina**, insieme all'editor
in riga: e' li' che il proprietario scrivera' questo campo per la prima volta con le mani, ed e' li'
che una cortesia serve davvero -- oggi ci si arriva solo da `curl`.

### Correggere `da_sapere_subito` dalla pagina del sapere, non solo dalla rotta

`origine: la fetta «da sapere subito», 18/09/2026 — limite dichiarato in perimetro, spec §5` · `documento: docs/design/2026-09-18-da-sapere-subito.md §5`

**Il fatto.** Il giudizio nuovo compare nella pagina del sapere (sezione 04) con la sua riga e il
suo gruppo, e **il ritorno al seme si fa gia' dalla pagina**: il comando «Torna al seme» vale per
qualunque riga corretta, di qualunque campo. Cio' che manca e' **scrivere un valore nuovo**, che
oggi si fa **solo dalla rotta** (`POST /api/mind/judgment`, a mano o da script): l'editor in riga
della sezione 04 tocca solo `genere`. Non e' un difetto di questa fetta: e' un limite dichiarato
finche' la pagina dell'osservatore non lo dispone.

**Cosa servirebbe.** Estendere l'editor in riga della sezione 04 a `da_sapere_subito` (il ritorno
al seme c'e' gia'). Arriva naturalmente con la fetta della pagina
dell'osservatore (`docs/superpowers/plans/2026-09-18-la-pagina-dell-osservatore.md`), che da questa
dipende.

### Le citazioni per numero di riga marciscono: si cita per nome

`origine: la fetta «da sapere subito», 18/09/2026, misurato durante il Task 4` · `nessun documento`

**Il fatto.** In una sola giornata, tre citazioni per numero di riga sono scivolate: una nel
README — **localizzata col `grep` durante la revisione finale**, perche' una voce sulle citazioni non
verificabili non puo' contenerne una: e' `hiris/app/model_activation.py:37-78` (sezione «AI
providers», sull'ordine della catena), e quel file **ha 51 righe in tutto**; la funzione che intende
citare e' `providers_in_chain`. E' la citazione piu' marcia possibile, quella che punta oltre la
fine del file, e nessun cancello la vede — e la spec di questa stessa fetta (§6) **due volte** — la
prima quando il documento e' nato
citando `chronicle_fingerprint` a `:261`, la seconda perche' il numero vero, verificato con `grep`
durante il Task 4, e' `:277`: il file si e' spostato sotto la citazione senza che nessuno la
riguardasse. La seconda volta e' la piu' significativa: **e' scivolata dentro il giro che la stava
correggendo**, perche' una riga scritta a mano non si autoverifica e nessun cancello la controlla.

**La cura proposta.** Citare per **nome** — funzione, costante, prova — e lasciare il numero di
riga solo dove il nome non basta (un intervallo, una regione senza un nome proprio). Un nome
sopravvive a un refactor che sposta il codice; un numero no. Non e' una regola nuova nel merito — il
glossario gia' segue «Le citazioni fra backtick seguono il codice» — e' la sua estensione ai numeri
di riga, che oggi nessuna sezione del genere dichiara.

### Il controllo di completezza n. 1 del GLOSSARIO non si esegue: `IndexError` su una riga piu' larga della sua intestazione

`origine: la fetta «da sapere subito», 18/09/2026 — scoperto dall'implementer del Task 4, riaperto dalla revisione finale (I-5)` · `documento: docs/GLOSSARIO.md, «Controlli di completezza», controllo n. 1`

**Il fatto.** Il primo dei tre controlli meccanici del glossario — «nessuna cella vuota, in nessuna
tabella del documento» — **solleva `IndexError` e non arriva mai in fondo**. Il documento pero'
dichiara il numero come «eseguito il 18/09/2026», e il numero e' vero: e' stato misurato con una
versione tollerante dello stesso comando, non con quello scritto.

La riga che lo ferma e' in «Parole scartate durante l'estrazione»: `` | `compreso` | 2 | `` (con uno
spazio finale). `r.strip('|').split('|')` ne ricava **tre** celle -- l'ultima vuota, prodotta dallo
spazio -- mentre l'intestazione di quella tabella ne ha **due**, e `header[i]` va fuori indice sulla
cella vuota. E' una riga **preesistente**, non di questa fetta: il controllo non e' mai stato
eseguito cosi' com'e' scritto da quando quella riga esiste.

**Perche' conta piu' del suo IndexError.** Un controllo che si rompe a meta' non e' un controllo che
avvisa: e' un controllo che **tace su tutto cio' che viene dopo il punto in cui si e' rotto**. La
tabella incriminata sta alla riga ~718 di un documento di ~3700: il comando, come scritto, non ha
mai visto quattro quinti del glossario. E il documento dichiarava «eseguito» — la motivazione
scritta accanto al numero era vera nella sostanza e falsa nel metodo.

**La cura proposta.** Non toccare la riga (togliere lo spazio farebbe passare *quel* caso e
lascerebbe il difetto): rendere il controllo **robusto** alla larghezza -- ignorare le celle oltre
l'intestazione, oppure nominarle `colonna N` -- e, gia' che si e' li', farlo **fallire con un
messaggio** invece che con una traccia, dicendo riga e tabella. Vale anche per i controlli n. 2 e
n. 3, che spezzano le righe allo stesso modo. Fetta piccola, tutta dentro il glossario.

---

## Usciti

### `classe: null` esce, `unita` assente no: due chiavi mute trattate in modo diverso — **USCITA con la v3.23.2**

`chiusa il 09/09/2026, commit 200be41d`

`origine: batteria di prove funzionali in chat sulla casa vera, 07/09/2026` · `nessun documento`

`view` su `sensor.persons` (il caso di chiusura dello sprint «la conoscenza prende una forma»)
torna `classe: null` **esplicito**, mentre `unita` — assente allo stesso modo — **non compare**.

La legge del prodotto e' che **le chiavi che non hanno niente da dire non escono**, ed e' stata
fatta rispettare in tutta la fetta per `capacita`, `stato_presunto`, `luogo`, `descrizione`,
`mute_da`, `non_letti`. Qui due chiavi nella stessa condizione escono in due modi: chi legge puo'
concludere che `classe: null` **significhi** qualcosa (una classe dichiarata vuota?) mentre
l'assenza di `unita` significhi un'altra. E' precedente alla fetta -- ma e' la stessa legge, e ora
che le altre la rispettano l'eccezione si nota.

**Chiusa dall'audit delle fondamenta (rilievo sotto soglia n.11).** La causa era il pre-seme:
`_entity_rows`, `_view_entity` e i `device_entities` di `_view_device` (`home_space/queries.py`)
costruivano il dizionario di partenza con `"classe": e.get("classe")` -- quasi sempre vuoto, perche'
il registro delle entita' non manda la classe -- prima che `_enrich_entity` avesse la possibilita' di
scriverla SOLO quando c'e' una classe vera (come gia' faceva per `unita`). Rimossi i tre pre-semi:
`_enrich_entity` resta la porta unica che decide se la chiave compare, per `classe` come per
`unita`, `categoria` e `nascosta`.


### La piattaforma non e' cercabile — **USCITA con la v3.22.0**

`chiusa il 04/09/2026, commit 61c9a975 e 55405672, rilasciata in v3.22.0`

`origine: misurato sulla casa vera il 02/09/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

`view` restituisce gia' `"piattaforma": "hydrawise"`, ma `search` indicizza solo nome, area e
dispositivo. Non si puo' chiedere «cosa espone l'integrazione Sonos», ne' «l'irrigazione funziona».
Misurato: `search "sonos"` → **0 risultati**, mentre HA ha 13 entita' con piattaforma `sonos` — si
chiamano «Sala da pranzo».

### La salute di un'integrazione non e' il suo stato — **USCITA con la v3.22.0**

`chiusa il 04-05/09/2026, commit 681eeece, 3658ecf4, 1d9b55f0, f025e15a, a41dcd64, rilasciata in v3.22.0`

`origine: misurato sulla casa vera il 02/09/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

Un'integrazione `loaded` con **tutte** le entita' morte oggi e' invisibile. Sulla casa: 162 entita'
su 827 (19,6%) sono `unavailable` o `unknown`, comprese tutte e 16 quelle dell'irrigazione
(Hydrawise risponde 403, 40 errori nel log). Ma `hydrawise` e' `loaded`, quindi non compare fra i
guasti, e il briefing non nomina mai «non disponibile». L'irrigazione e' ferma e HIRIS non lo
direbbe. La salute di un'integrazione e' **quante delle sue entita' rispondono**, non il suo `state`.

**Rimisurato il 04/09**, e i numeri di riferimento sono questi: **74 entita' non rispondono su
1221**, e l'irrigazione ne porta **24** — verificato entita' per entita'
(`binary_sensor.giardino_*_irrigazione` e `valve.giardino_*` sono `unavailable`,
`piattaforma: hydrawise`). Il briefing dice «74 entita' non rispondono» e si ferma li': nessun
nome, nessun raggruppamento, nessuna integrazione nominata.

### Il soggetto di un guasto porta il nome e la condizione, non l'identificativo — **USCITA con la v3.22.0**

`chiusa il 05/09/2026, commit 570b43e5 e 143c9ab2, rilasciata in v3.22.0`

`origine: il proprietario, 04/09/2026, dopo la sonda sull'osservatore` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

`mind/watcher.py:191` tiene solo l'`entry_id`: il soggetto scritto in archivio e'
`integrazione:01K2CK4GG287VKK18M5J788MRQ`. Il dizionario dell'integrazione **ha** `domain`,
`title` e `state`, e il codice li legge tre righe sopra per decidere se e' un guasto — poi li
scarta. Non e' un dato che manca: e' un dato che si getta.

Misurato sulla casa il 04/09: quel ULID e' **il protagonista piu' frequente dell'intero
archivio**, 34 oggetti su 285 in nove giorni. Nessuno di quegli oggetti dice cosa si sia rotto,
ne' se sia `setup_retry` o `setup_error` — che non sono la stessa cosa. Il corpo, per giunta,
dice sempre `"stato": "aperto"` anche a episodio chiuso, perche' `facts.py:725` scrive quella
costante alla nascita e `close()` la ricopia (`facts.py:712`).

Sta nella stessa funzione dove va messa l'isteresi — vedi «Un episodio per condizione, non
venticinque»: sono due correzioni nello stesso punto del codice, e senza questa le altre voci
della fetta producono oggetti veri e comunque illeggibili.

**Una domanda di disegno da sciogliere prima**: cambiare la forma del soggetto rompe la
continuita' col grezzo gia' scritto (22 giorni di righe con la forma vecchia). Si migra, si
convive, o il nome viaggia in una colonna accanto invece che dentro il soggetto?

### Un episodio per condizione, non venticinque — **USCITA con la v3.22.0**

`chiusa il 05/09/2026, commit 805b1004, rilasciata in v3.22.0`

`origine: misurato sulla casa vera il 02/09/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

L'osservatore apre un episodio nuovo a ogni sfarfallio: **25 episodi di guasto per una sola
integrazione** (`lifx / Abat-jour`, `setup_retry`), e cinque aperti contemporaneamente per la stessa
cosa. Una condizione che va e viene dovrebbe essere un episodio finche' non finisce: il genere
decide la forma, e la forma di una condizione e' la **durata**.

### I calendari si importano, e HIRIS li sa leggere — **USCITA con la v3.22.0**

`chiusa il 05-06/09/2026, commit 1f9be22c, 8a6a5de8, 8f4d206a, fca730e4, 1c150795, ecfcaee3, rilasciata in v3.22.0`

`origine: il proprietario, 04/09/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

**Richiesta**: importare anche i calendari, e che HIRIS li possa leggere.

**Misurato sulla casa vera il 04/09, e il primo fatto è che la capacità c'era e l'abbiamo tolta.**
`proxy/ha_client.py:1173-1180` lo dichiara per esteso: `get_calendars` e
`get_calendar_events_range` sono **uscite** nella fetta «escono i trentaquattro» (E2, Task 8),
orfane a cascata perché il loro unico chiamante — `tools/calendar_tools.get_calendar_events` —
era uscito a sua volta. Il commento chiude con «nessuna garanzia persa», ed era vero allora:
nessuno le chiamava. Adesso c'è chi le chiamerebbe.

**Cosa c'è sulla casa**, e quanto poco HIRIS ne sa:

| | |
|---|---|
| `calendar.famiglia` · `calendar.personale` | piattaforma `caldav`, due calendari veri |
| `view calendar.famiglia` restituisce | `stato: "on"`, `stato_leggibile: **"acceso"**` |
| `search "calendario"` · `"calendar"` · `"eventi"` · `"agenda"` | **zero risultati, tutte e quattro** |

Due difetti distinti, e il secondo è più insidioso del primo:

1. **Gli eventi non si leggono affatto.** Un calendario, per HIRIS, è una lampadina con due
   stati. Non sa che c'è dentro, né quando, né per chi.
2. **«Acceso» è una traduzione falsa.** Per Home Assistant un'entità `calendar` sta a `on`
   quando **un evento è in corso**, non quando è «accesa». Dire «acceso» a un modello non è
   generico: è **sbagliato**, e lo porta a ragionare su un interruttore invece che su un
   impegno. È lo stesso difetto di `sensor.persons` letto come conteggio di presenza, e
   ricadrà sotto il tema finale dello sprint (§7): **cosa significa uno stato va importato
   dalla documentazione, non dedotto.**

E i due calendari sono raggiungibili **solo se sai già che si chiamano «Famiglia» e
«Personale»** — la stessa lacuna delle persone, sul dominio invece che sulla piattaforma.

**Dove sta nello sprint**: con «le tracce e il log», in coda. Sono la stessa forma di lavoro —
una **fonte nuova** che nasce sopra un'appartenenza già rifatta — e vale anche qui la regola che
il proprietario ha già dato per le tracce: **una fonte sola, due lettori**, lo strumento della
chat *e* l'osservatore. Un calendario che sa dire «domani nessuno è in casa dalle 9 alle 18» è
esattamente ciò che manca a un osservatore che oggi ha tre giorni di storia della presenza.

**Da decidere quando si progetta**: quanto avanti si guarda (un giorno? una settimana?), se gli
eventi si conservano o si rileggono ogni volta, e come si dichiara ciò che il calendario **non**
dice — un calendario vuoto non significa «nessuno ha impegni», significa «nessuno l'ha scritto».

### Le tracce delle automazioni e il log di sistema — **USCITA con la v3.22.0**

`chiusa il 05/09/2026, commit d499e767, 532e9d99, a832d856, 14a3f1f4, 6bf815f4, rilasciata in v3.22.0`

`origine: deciso dal proprietario il 31/08/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

Due fonti nuove di HA, e devono essere disponibili **a entrambi i lettori**: lo strumento della chat
E l'osservatore. Una fonte sola, due lettori — l'osservatore «non apre un secondo rubinetto», perche'
due sorgenti degli stessi eventi possono divergere. Le chiamate sono `trace/list`, `trace/get`,
`trace/contexts` e `system_log/list`, tutte WS e tutte `require_admin`.

Misurato sulla casa il 30-31/08: 72 tracce su 16 automazioni, 64 `finished`, 7 `failed_conditions`,
1 `error` — e un'automazione rotta davvero, mai segnalata al proprietario; 17 voci di log, 11
WARNING e 6 ERROR.

Due trappole gia' pagate, che decidono il lavoro e non si vedono nella documentazione:
**le tracce hanno una finestra** (HA ne conserva 5 per automazione, poi la sesta cancella la prima —
decide se si puo' guardare a cadenza o si devono seguire mentre accadono); e **il log arriva gia'
giudicato**, perche' `system_log/list` consegna righe raggruppate da HA con `count` e
`first_occurred`, il che rompe la legge dell'osservatore «scrivi il grezzo, giudica dopo».

### Le specifiche di Home Assistant si importano dalla documentazione — il tema finale — **USCITA con la v3.22.0**

`chiusa il 04-07/09/2026, commit f761b3c1 e 56d05989, rilasciata in v3.22.0`

`origine: il proprietario, 04/09/2026 — «questo e' il tema finale di questo sprint»` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

**Richiesta testuale**: «vanno importate e capite le specifiche di HA con la documentazione; per
ogni stato va capito cosa rappresenta e se ci sono altri metadati o parametri che permettono di
capire di piu'. Per migliorare i ragionamenti serve sapere cosa stiamo guardando in profondita' e
capire bene per ogni oggetto le sue caratteristiche.»

E' la voce che chiude lo sprint perche' e' quella che lo rende **duraturo**: le altre otto
correggono cio' che sbagliamo oggi, questa toglie la ragione per cui lo sbagliavamo. Vale la legge
del progetto: **mai un'ipotesi su Home Assistant — prima la documentazione, poi le API vere**.

**Misurato il 04/09: quanti campi che HA manda nel registro delle entita' il codice non nomina
mai.** Conteggio delle occorrenze in tutto `hiris/app`:

| campo di HA | citazioni | cosa ci perdiamo |
|---|---:|---|
| `supported_features` | **0** | cosa un'entita' **sa fare** (una luce che cambia colore, una tapparella che si ferma a meta') |
| `assumed_state` | **0** | HA dichiara «questo stato lo **suppongo**, non l'ho verificato» — ed e' la provenienza, che stiamo cercando altrove |
| `options` | **0** | i valori ammessi di un `select` |
| `config_entry_id` | **0** | l'appartenenza all'istanza (vedi la spina n. 1) |
| `unique_id` · `has_entity_name` | **0** | |
| `capabilities` · `entity_category` · `original_device_class` · `hidden_by` · `original_name` · `platform` | **1 ciascuno** | letti in un punto solo, non conservati come caratteristiche |

`assumed_state` merita una riga sua: **Home Assistant dichiara gia' quando non e' sicuro di uno
stato**, e HIRIS non lo legge mai. Stiamo progettando la certezza del dato mentre il fornitore ce
la sta gia' mandando.

**Il precedente da seguire c'e' gia' in casa**: `briefing.py:69` porta un elenco «copiato da
`homeassistant/generated/entity_platforms.py`», sorvegliato da `tests/test_domain_vocabulary.py`.
Cioe' non si deduce e non si indovina: si importa, si dichiara da dove viene, e una prova si
accorge quando diverge. Questa voce estende quel gesto dai domini a **stati, classi, categorie,
capacita' e attributi**.

Da decidere quando si progetta: cosa si importa a mano e cosa si legge a runtime; dove vive
(tabella generata nel repo o nell'anagrafe); e come si accorge di essere invecchiato quando HA
cambia versione.

### La CLI del ponte sale alla 2.1.263 nel prossimo rilascio — **USCITA con la v3.22.2**

`chiusa il 07/09/2026, commit f98ce698, rilasciata in v3.22.2`

`origine: decisione del proprietario, 07/09/2026` · `nessun documento`

**Regola dichiarata dal proprietario**: un avanzamento **di patch** della CLI del ponte puo'
viaggiare insieme a un aggiornamento; **quando il cancello lo segnala, entra nel rilascio
successivo**. Non si alza al volo dentro un rilascio che parla d'altro.

Il 07/09, durante il rilascio della **v3.22.0**, `scripts/verifica_componenti.py` ha fermato il
push segnalando `@anthropic-ai/claude-code` **2.1.260 → 2.1.263** (`hiris/Dockerfile:76`). Il
rilascio e' andato avanti con `HIRIS_COMPONENTI_OK=1`, dichiarato: quella v3.22.0 conteneva tre
fette di prodotto, e far salire una dipendenza non provata sotto quel changelog avrebbe spedito un
cambiamento che nessuno aveva verificato.

**Cosa fare al prossimo rilascio**: `python scripts/verifica_componenti.py --aggiorna`, poi la
suite intera, poi il rilascio. Il Dockerfile (`:38-70`) porta gia' la forma di questa annotazione
per il salto precedente (2.1.251 → 2.1.260 del 04/09) **col piano di ripiego scritto accanto**: si
segue quella, compresa la riga «se la nuova desse problemi si torna alla precedente».

### `get_error_log()` si cancella — **USCITA con la v3.15.0**

`chiusa il 31/08/2026, commit c6d05912, rilasciata in v3.15.0`

**Questa voce era gia' chiusa quando il registro e' nato**, e il registro se n'e' accorto
il 05/09 mentre si scriveva il piano 2: `grep get_error_log` su `hiris/` e `tests/` non
trova piu' niente. Il metodo e i suoi 20 righe di prove sono usciti insieme --
«l'endpoint non esiste piu' e il metodo rispondeva zeri» dice il commit.

Era nata da un ricordo del 31/08 che registrava la **decisione**; la decisione era stata
eseguita lo stesso giorno. E' il primo caso in cui il registro corregge se stesso, ed e'
il motivo per cui una voce dichiara sempre da dove viene: una decisione ricordata non e'
un lavoro da fare.

