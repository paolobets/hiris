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

Colmare i buchi di scrittura verso HA emersi dallo studio di `ha-mcp`: plance, categorie, etichette
(update e delete), aree e piani, zone, calendari con ricorrenze, gruppi e liste, i 17 helper a
config-flow, blueprint. Lo studio porta la chiamata esatta di ognuno, letta nel loro sorgente. **Non
e' una specifica**: il perimetro non e' stato scelto.

### La sicurezza

`origine: deciso dal proprietario il 04/09/2026` · `documento: docs/design/2026-09-04-la-sicurezza-il-seme.md`

Sprint a se', **dopo** quello dei comandi. Il reperto che lo apre: HIRIS non ha nessuna lista di
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

### Il prompt dell'obiettivo dell'osservatore

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
per servire `historian.produces_statistics` (`tools.py::_trend`, che legge
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

### «Cosa sto guardando» stampa i soggetti grezzi, gli episodi no

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

### `classe: null` esce, `unita` assente no: due chiavi mute trattate in modo diverso

`origine: batteria di prove funzionali in chat sulla casa vera, 07/09/2026` · `nessun documento`

`view` su `sensor.persons` (il caso di chiusura dello sprint «la conoscenza prende una forma»)
torna `classe: null` **esplicito**, mentre `unita` — assente allo stesso modo — **non compare**.

La legge del prodotto e' che **le chiavi che non hanno niente da dire non escono**, ed e' stata
fatta rispettare in tutta la fetta per `capacita`, `stato_presunto`, `luogo`, `descrizione`,
`mute_da`, `non_letti`. Qui due chiavi nella stessa condizione escono in due modi: chi legge puo'
concludere che `classe: null` **significhi** qualcosa (una classe dichiarata vuota?) mentre
l'assenza di `unita` significhi un'altra. E' precedente alla fetta -- ma e' la stessa legge, e ora
che le altre la rispettano l'eccezione si nota.

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

### L'analista — chi trasforma le osservazioni in qualcosa di funzionale

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

---

## Usciti

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

