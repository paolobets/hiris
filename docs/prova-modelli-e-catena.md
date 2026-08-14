# La prova sulla casa vera — la pagina Modelli e la catena

*Foglio scritto il 14 agosto 2026 per la **2.5.0**, la versione in cui la pagina Modelli
smette di essere vera riga per riga e falsa nel complesso, e il Piano Claude Max smette di
essere un bivio per diventare il primo anello di una catena. Si esegue in un'ora, su un
impianto Home Assistant vero, e serve a decidere se questa versione è pubblicabile — e se
la versione **successiva** si può cominciare.*

---

## Perché questo foglio esiste

Le prove automatiche di questa fetta sono **1590 in Python e 147 in JavaScript**, e non
provano niente di ciò che conta qui.

Questa versione tocca **come HIRIS sceglie a chi chiedere**, cioè la cosa che decide quanto
costa ogni messaggio. Le tre metà che nessun test di questo repo può vedere sono:

1. **Il layout.** Nessun browser ha mai reso il CSS di questa pagina. La suite JS gira su
   jsdom, che **non calcola il layout**: costruisce l'albero e legge il testo, e per quanto
   ne sa, sei colonne e sei blocchi sovrapposti sono la stessa cosa. Dalla 2.5.0 **tre** test
   Python aprono un `.css` (`tests/test_invarianti_modelli.py`, i primi di questo repo), ma
   provano che i **nomi** coincidano, che il testo semantico usi i token giusti e che i blocchi
   a tutta larghezza si dichiarino tali: **non che qualcosa si veda.** Chi salta la Prova 9
   perché «ci sono test sul CSS» sta saltando l'unica prova che c'è.
2. **Le risposte vere dei provider.** La classificazione degli errori — «credito esaurito
   (400)», «chiave rifiutata (401)», «troppe richieste (429)» — è scritta contro le risposte
   che *ci aspettiamo* da Anthropic e da OpenRouter. Nelle prove automatiche la risposta è
   una finta, e **una finta conferma sempre chi l'ha scritta**.
3. **La migrazione.** La copia delle opzioni dell'add-on nell'archivio di HIRIS avviene
   **una volta sola**, al primo avvio della 2.5.0, e nessun test può girare su un
   `/data/options.json` scritto dal Supervisor.

E c'è una quarta cosa, che non è una prova ma un **cancello**: la versione successiva
(quella che toglie le opzioni dalla configurazione dell'add-on) **non si può cominciare**
finché le prove 2 e 3 di questo foglio non sono passate dal vivo. Vedi il §**Cancello**, in
fondo, che è la parte più importante di questo documento.

---

## Cosa serve, prima di cominciare

1. **Un Home Assistant vero** con l'add-on HIRIS **2.5.0** installato e avviato.
2. **Il log dell'add-on aperto**: Impostazioni → Add-on → HIRIS → scheda **Log**. Le prove
   qui sotto citano le righe esatte da cercare, parola per parola. Il livello `info`
   (quello di default) basta.
3. **Accesso a `/data/models_config.json`** — dal Terminal add-on, o da
   `/addon_configs/…/`. Due prove leggono quel file e non c'è un altro modo.
4. **Un iPad o un telefono**, oltre al computer: metà delle prove di layout riguardano la
   larghezza sotto i 640px, dove la riga della catena si manda a capo su due righe.
5. **Un momento in cui puoi permetterti che la chat costi.** Tre di queste prove mandano
   messaggi veri, e almeno una li manda **apposta** a un provider a pagamento.

**Dove si guarda l'esito.** Tre posti, e vanno usati tutti e tre:

- **la pagina Modelli**: cosa HIRIS *dice* di stare per fare;
- **la chat**: cosa succede davvero, e la riga sotto la risposta che dichiara il ripiego;
- **il log**: l'unico posto in cui il motivo compare per intero.

Se pagina e log si contraddicono, **vale il log** — e quella contraddizione è la
segnalazione più importante che questo foglio possa produrre, perché l'intero senso di
questa versione è che la pagina smetta di dire una cosa mentre il prodotto ne fa un'altra.

---

## Prova 1 — Il caso concreto di oggi, a colpo d'occhio

**È il metro di questa fetta, non un esempio.** Tutto il resto esiste per rendere possibile
questa singola lettura.

L'impianto ha, in questo momento: una **chiave Claude API a credito zero**, un **Piano
Claude Max pagato e fermo**, un **OpenRouter a consumo** che sta rispondendo a tutto.

**Cosa fare.** Apri la pagina Modelli. Guarda la parte alta: il riquadro in cima **e le
prime due righe della sezione 01**. Non serve altro, e non serve aprire niente.

**Cosa si deve vedere.** In cima, prima di ogni sezione, un riquadro con **una frase in
corpo grande** e sotto una o due righe di diagnosi; subito sotto, la catena. Nella sostanza:

> **Il prossimo messaggio va a Claude API, con `claude-sonnet-4-6`, a consumo.**
>
> Il Piano Claude Max ha il token, lo paghi, ed è fuori dalla catena.
>
> **01 LA CATENA**
> 1. Claude API · `claude-sonnet-4-6` · a consumo — *ha rifiutato le ultime N richieste —
>    credito esaurito (400), M min fa*
> 2. OpenRouter · `anthropic/claude-sonnet-4-6` · a consumo — *ha risposto M min fa*

⚠️ **La frase in cima nomina Claude API, non OpenRouter, ed è corretta così**: dice chi
viene **provato per primo**, non chi finisce per rispondere. Chi risponde davvero è
OpenRouter, perché Claude rifiuta e il turno scende — e a dirlo è la **riga di stato di
Claude API**, dentro la catena. È un debito dichiarato di questa fetta (la frase in cima
non guarda ancora gli esiti osservati), **non un difetto da segnare qui**: si chiude
passando gli esiti a chi compone la frase, in una fetta sua.

**Cosa si deve poter dire in trenta secondi**, senza scorrere oltre la seconda riga della
catena e senza aprire niente:

- chi viene provato per primo, e che **sta rifiutando** — con da quante richieste e da
  quanto;
- che chi risponde **costa**;
- che c'è qualcosa di già pagato che non viene usato.

**Cosa si deve poter fare in pochi gesti**: accendere il ponte (oggi dalla configurazione
dell'add-on: `ponte.attivo` **da solo basta**; `provider_subscription` **solo se il token
del piano è già incollato** — vedi Prova 10 e m1) e togliere dalla catena la chiave
scarica, con la ✕ sulla sua riga.

**Che cosa la fa fallire.** Se per capire il caso serve leggere **tre sezioni** e metterle
insieme da soli, **la fetta ha fallito**, anche se ogni riga è corretta. Il riquadro più le
due righe della catena sono **una** lettura, e sono ciò che questa prova misura; una terza
sezione no. È l'unica prova che non ha una condizione meccanica: si decide guardandola.

---

## Prova 2 — La migrazione (versione A). ⚠️ **Da guardare PRIMA di qualunque altra cosa**

Al primo avvio della 2.5.0, HIRIS **copia una volta sola** i valori che avevi nella
configurazione dell'add-on dentro il suo archivio. Se questa copia sbaglia, ogni prova
successiva sta misurando un impianto diverso dal tuo — e la versione successiva, che toglie
quelle opzioni, non è più recuperabile.

**Cosa fare.** Subito dopo l'aggiornamento, prima di aprire la pagina Modelli, apri il log.

**Cosa si deve vedere — tre righe, e vanno copiate a mano nel rapporto:**

```
Migrazione (versione A): i valori delle opzioni dell'add-on sono stati copiati
nell'archivio di HIRIS, e da adesso si cambiano dalla pagina Modelli.
Copiati: … . Valori: ponte=…, ollama=…, nascondi_gratuiti=…, strategia=….

Migrazione della catena: la catena che HIRIS stava usando e' stata copiata
nell'archivio e da adesso si riordina dalla pagina Modelli. Ordine copiato: … .

Migrazione (versione A): 'giorni_conservazione' (…) e' stato scritto in
impostazioni_chat.json -- da adesso si cambia dalla pagina Impostazioni chat, e
l'opzione dell'add-on 'history_retention_days' non serve piu'.
```

> **Sono le righe della 2.5.0**, ed è contro la 2.5.0 che questa prova si esegue. **Dalla
> 3.0.0 le prime due sono riscritte**, perché dicevano più di ciò che il sistema sa: la
> prima affermava «erano tutti ai predefiniti» anche quando non c'era *niente da leggere*
> (dalla 3.0.0 le opzioni non esistono più, ed è la condizione normale), la seconda
> affermava «la catena che HIRIS stava usando» anche su un'installazione nata ieri, che non
> stava usando niente. Dalla 3.0.0 si leggono `Migrazione (versione A): non c'era nessuna
> opzione dell'add-on da copiare …` e `Catena iniziale scritta nell'archivio: … Ordine: …`.

**Cosa verificare, valore per valore:**

| Da guardare | Deve valere |
|---|---|
| `ponte=…` | `attivo` = com'era l'interruttore del ponte; `scadenza_min` = `ponte.bridge_deadline_min`; `tetto_giornaliero` = `ponte.chat_daily_cap` |
| `ollama=…` | `modello` = `local_model.model`; `timeout_s` = `local_model.request_timeout` |
| `Ordine copiato` | sull'impianto del proprietario deve essere **`claude -> openrouter`** — cioè la catena che HIRIS *stava già usando*, non una catena ricalcolata |

| terza riga | il numero fra parentesi = `history_retention_days` com'era, **`0` compreso** |

Poi apri `/data/models_config.json` e verifica che contenga `"seminato": true`,
`"catena_seminata": true` e la `chain_order` giusta; e `/data/impostazioni_chat.json`, che
deve contenere `"giorni_conservazione"` **col valore vero**.

**Che cosa la fa fallire.** Una `chain_order` **vuota** dopo la migrazione (l'impianto
passerebbe da «due provider lavorano» a «zero provider»). Una `chain_order` che contiene
un provider che non era in uso: la migrazione doveva **copiare**, non **inventare**. Un
valore che non corrisponde all'opzione: da quel momento la pagina Modelli comanda su un
numero diverso da quello che hai scelto tu.

**Riavvia una seconda volta.** Le **tre** righe **non devono ricomparire**: i due segni
`seminato`/`catena_seminata` e la chiave sul disco esistono per questo. Se ricompaiono, la
copia si rifà a ogni avvio e sovrascriverà per sempre ogni decisione presa dalla pagina.

**Poi svuota la catena e riavvia una terza volta.** Nella pagina Modelli togli **tutte** le
righe con la ✕, finché la sezione 01 non è vuota; riavvia l'add-on; riapri la pagina. **La
catena deve restare vuota**, e la riga della catena — «Migrazione della catena» sulla 2.5.0,
«Catena iniziale» dalla 3.0.0 — **non deve ricomparire**.
Se invece i provider tornano in catena da soli, la regola di compatibilità è rientrata
dalla porta della migrazione — e sull'impianto del proprietario significa che **la spesa a
consumo riparte da sola dopo ogni riavvio**. (Rimetti poi la catena che vuoi, con «Usa».)

---

## Prova 3 — Il ripiego vero, nelle sue due forme

**È la capacità nuova di questa versione, ed è quella che cambia il costo.** Va provata in
tutt'e due i modi, perché sono due percorsi di codice diversi.

**3a — Ripiego a monte (il piano non può nemmeno partire).** Togli
`claude_code_oauth_token` dalla configurazione dell'add-on, lasciando il ponte **acceso**.
Riavvia. Manda un messaggio.

- La risposta deve **arrivare**, e arrivare subito (non dopo cinque minuti).
- Sotto la risposta deve comparire, in tondo, una riga come:
  > *Il Piano Claude Max non ha un token con cui rispondere: ha risposto OpenRouter, a
  > consumo.*
- La pagina Modelli, in cima, deve dire che il ponte è acceso senza token e che **ogni
  turno passa alla catena — dal forfait al consumo**.

**3b — Ripiego a valle (il piano parte e non finisce).** Rimetti il token. Manda un
messaggio e lascia scadere il turno (il modo più semplice: rendi irraggiungibile ciò che
serve alla CLI, oppure manda una richiesta lunghissima). Alla scadenza:

- il turno deve **passare al successivo** invece di finire con un errore;
- la riga sotto la risposta deve dire *«non ha risposto in tempo»*, **non** *«ha
  rifiutato»*: il piano non ha rifiutato, non ha risposto, e sono due fatti diversi;
- la riga di stato del **piano**, nella pagina Modelli, deve riportarlo.

**Che cosa la fa fallire.** Una riga di ripiego che **non compare**: il proprietario ha
chiesto esplicitamente che il passaggio dal forfait al consumo si annunci **ogni volta**,
perché altrimenti si scopre a fine mese. Una riga che nomina il provider **sbagliato** (il
router ripiega, quindi «ha risposto il primo della catena» sarebbe falso proprio nel caso
che conta). Un turno che si perde.

**3c — Il tetto giornaliero.** Se riesci a raggiungerlo: l'errore **«Limite giornaliero di
messaggi chat raggiunto»** non deve più comparire. Quel turno deve ricevere una risposta —
**a pagamento** — e la riga deve dire *«ha raggiunto il suo tetto di messaggi per oggi»*.
Nel log deve esserci `Tetto giornaliero del ponte raggiunto (N messaggi): il turno passa
alla catena.`

---

## Prova 4 — Il riordino a caldo

**Cosa fare.** Nella pagina Modelli, sposta una riga con le frecce (per esempio: metti
OpenRouter sopra Claude API). **Non riavviare niente.** Manda un messaggio in chat.

**Cosa si deve vedere.** Il messaggio successivo deve andare al provider che adesso è
primo. Lo si verifica in due modi, e vanno usati tutti e due:

- la frase in cima alla pagina Modelli deve **già** nominare il nuovo primo;
- la riga di stato del provider che ha risposto deve aggiornarsi a **«ha risposto, ora»**.

**Che cosa la fa fallire.** Se ricaricando la pagina l'ordine **torna quello di prima**, la
scrittura a caldo non funziona e la funzione più visibile della pagina sembra rotta. Se la
frase in cima resta indietro, la pagina descrive il runtime vecchio.

---

## Prova 5 — Il cambio di modello a caldo, sui due percorsi

**È la prova del difetto §0.5**, il peggiore che il progetto abbia trovato: fino alla 2.4.1
il modello di Claude API aveva effetto **immediato** sul ponte e **solo al riavvio**
sull'API, e la didascalia diceva una cosa sola — cioè era **sbagliata**, non imprecisa.

**Cosa fare.**

1. Ponte **spento**. Clicca il modello nella riga di Claude API, scegline un altro, salva.
   Manda un messaggio. Il turno successivo deve usare **il nuovo modello**, senza riavvio.
2. Ponte **acceso**. Ripeti. Il turno successivo deve usare **l'alias corrispondente** sulla
   CLI dell'abbonamento (`sonnet` / `opus` / `haiku`), sempre senza riavvio.

**Cosa si deve vedere.** In tutt'e due i casi la riga mostra **subito** il modello nuovo, e
il turno successivo lo usa. Nessuna didascalia da nessuna parte deve dire «al riavvio»: se
la trovi, è la confessione di un invariante rotto, ed è uscita apposta.

**Che cosa la fa fallire.** Un riavvio necessario in uno dei due casi e non nell'altro. È
il difetto originale, e non è più tollerabile perché adesso i due percorsi sono la **stessa
riga della pagina**.

---

## Prova 6 — Ollama con l'indirizzo ma senza modello

Dalla 2.5.0 la credenziale di Ollama è **il solo indirizzo**. Un impianto con
`local_model.url` valorizzato e `model` vuoto — che prima non compariva — adesso cambia
comportamento, e la pagina lo deve **mostrare** invece di nasconderlo.

**Cosa fare.** Metti l'indirizzo di Ollama, lascia il modello vuoto, riavvia, apri la
pagina Modelli.

**Cosa si deve vedere.** La riga di Ollama esiste, è **credenziata**, e dice **che cosa gli
manca**. Non deve essere riordinabile, e non deve poter entrare in catena come se potesse
rispondere. Poi scegli un modello dal suo pannello: la riga deve diventare riordinabile e
la catena deve poterlo accogliere, **senza riavvio**.

**Che cosa la fa fallire.** Un Ollama in catena senza niente dietro: il turno andrebbe a un
provider che non può rispondere, e questa versione ha appena promesso che chi sta in catena
è chi risponde.

---

## Prova 7 — Gli esiti osservati, contro le risposte vere di Anthropic

**È l'unica prova possibile che la classificazione degli errori funzioni**, perché nelle
prove automatiche l'errore lo scriviamo noi.

**Cosa fare.** Lascia la chiave Claude a credito zero **in catena** e manda cinque o sei
messaggi nell'arco di qualche minuto. Poi apri la pagina Modelli.

**Cosa si deve vedere.** Sulla riga di Claude API, una riga di stato con la forma:

> ha rifiutato le ultime **N** richieste — **credito esaurito (400)**, **M min** fa

- **N** deve corrispondere ai messaggi che hai mandato (conta per **famiglia e codice**:
  se cambia la causa, il conteggio riparte);
- **il codice** deve essere quello vero. 400 e 402 sono «credito esaurito»; **401 e 403
  non lo sono** — sono «chiave rifiutata», e portano a fare una cosa diversa. Se la tua
  chiave scarica produce un 401 e la pagina scrive «credito esaurito», la classificazione
  ha fatto un'ipotesi sulla causa, che è precisamente ciò che questo prodotto ha smesso di
  fare;
- **M min fa** arrotonda sempre **per difetto** (90 minuti si leggono «1 h fa»).

**Cosa guardare col contorno dell'occhio:** il **pallino** della riga che rifiuta deve
essere **grigio-ambra**, non rosso. Una riga che non risponde deve *smettere di sembrare
attiva*, non diventare un allarme — ed è la traduzione grafica del ritiro della parola
«Attivo». Il nome, accanto, deve perdere peso.

**E una cosa da non aspettarsi.** Claude API **non ha nessuna protezione**: gli altri tre
provider, dopo tre errori di connessione, vengono saltati per un minuto; Claude viene
ritentato **integralmente a ogni turno**. Questa versione non gliene dà una. La prova qui è
soltanto che adesso **lo leggi**.

---

## Prova 8 — Il ponte acceso senza token, prima che un messaggio si perda

**Cosa fare.** Spegni il token del piano lasciando il ponte acceso. Apri la pagina Modelli
**prima** di mandare qualunque messaggio.

**Cosa si deve vedere.** La frase in cima deve dirlo **prima** che un messaggio si perda:
il ponte è acceso, manca il token, e ogni turno passa alla catena — dal forfait al consumo.
La gravità dev'essere quella di **uno spreco**, non di un guasto: HIRIS risponde, e ciò che
resta da dichiarare è un **costo**.

Poi manda un messaggio: deve **ripiegare subito** (vedi Prova 3a), non dopo cinque minuti.

**Se in catena non c'è nessuno**, invece, la frase deve dire che **HIRIS non può
rispondere** e che sotto il ponte non c'è nessuno a cui passare il turno — e quello **è** un
guasto.

---

## Prova 9 — Il CSS che nessun browser ha mai visto

Questa prova non ha una condizione meccanica: si guarda. Va fatta **due volte**, sul
computer e su un iPad in verticale (o un telefono), perché sotto i 640px la riga della
catena passa da sei colonne a due righe.

**Cosa guardare, punto per punto:**

| # | Che cosa | Che cosa deve succedere |
|---|---|---|
| 9.1 | Il riquadro **«Adesso»** in cima | Il testo più grande della pagina dopo il titolo. Fondo distinto dalle sezioni, nessun numero: non decide, dice |
| 9.2 | La **riga della catena** in largo | Sei colonne incolonnate: posizione, pallino, nome, modello, natura, azioni. Le due liste (in catena / fuori) devono risultare **incolonnate fra loro** |
| 9.3 | I **tre blocchi a tutta larghezza** — nota, riga di stato, pannello del modello | Devono occupare **tutta** la riga e rientrare sotto il nome. Se uno si schiaccia dentro una colonna, `grid-column: 1 / -1` non sta facendo effetto |
| 9.4 | Il **connettore** fra due righe | Tratteggio sopra, stesso rientro della nota. Deve leggersi come un *passaggio*, non come un confine |
| 9.5 | Il **pannello del modello** aperto | Si apre **dentro** la riga (espanso, non sovrapposto). L'elenco deve **scorrere** dentro il pannello, non allungare la pagina. Su iPad in verticale è dove morde di più |
| 9.6 | Sotto i **640px** | La riga va a capo su due righe: nome e azioni sopra, modello e natura sotto. **Non si nasconde niente.** La riga di stato e la nota devono restare leggibili |
| 9.7 | La **riga di ripiego** sotto una risposta in chat | In tondo, sotto la bolla e **non accanto**, incolonnata col testo del messaggio |
| 9.8 | La diagnosi «**fatto**» col ponte acceso | Grigia e in tondo, non ambra e non rossa: è un fatto, non un avviso |
| 9.9 | **Le aree toccabili** | Frecce, ✕ e il modello cliccabile devono essere prendibili col dito (44px) senza spostare le colonne |
| 9.10 | **Con un lettore di schermo** | Il riquadro «Adesso» è una regione viva e deve **annunciarsi quando arriva**, non quando compare il guscio. Il pannello del modello, invece, **non** è una regione viva: dichiara solo di essersi aperto (`aria-expanded`), perché annunciare undici voci a ogni tasto del filtro sarebbe peggio. È una **scelta**, non una svista, e questa è l'unica occasione di verificarla con un lettore vero |

**Che cosa la fa fallire.** Qualunque blocco che si accavalli, un pannello che allunghi la
pagina invece di scorrere, una colonna che salti sotto i 640px. Nessuna di queste cose può
essere vista da un test.

---

## Prova 10 — Ciò che questa versione **non** corregge (e che va guardato lo stesso)

Quattro cose che non sono difetti da segnalare: sono **limiti dichiarati**. Vanno guardate
per capire quanto mordono davvero sull'impianto vero, perché è quello che decide la fetta
successiva.

**10.1 — Il piano si legge tutto ma si corregge a metà.** Sulla riga del Piano Claude Max
**non** ci sono i bottoni «Usa» e ✕. Non è una dimenticanza: oggi il ponte si accende
dall'ambiente, e un bottone lì scriverebbe una richiesta che il server accetta con 200 e
**butta via**. Per metterlo in cima alla catena serve ancora accendere il ponte dalla
**configurazione dell'add-on** — e sono ancora **due** gli interruttori che lo fanno,
`ponte.attivo` e `provider_subscription`: basta uno dei due, ed è l'ultimo dei cinque
interruttori dei provider che decide ancora qualcosa. Da guardare anche questo: se il
proprietario, letto in cima che sta pagando due volte, trova la strada. Da guardare: **quanto è scomodo**, in pratica, per chi ha
appena letto in cima alla pagina che sta pagando due volte.

**10.2 — La riga di OpenRouter senza un modello scelto mostra `gpt-4o`.** Il ripiego
automatico di OpenRouter eredita la mappa di OpenAI, e `gpt-4o` **non è un identificatore
OpenRouter valido** (OpenRouter vuole `fornitore/modello`). La 2.5.0 lo rende **visibile**;
non lo corregge, e non doveva. Da guardare: **se in pratica morde** — basta scegliere un
modello perché sparisca — e se il proprietario lo scambia per un errore della pagina. Se
sì, è una fetta sua.

**10.3 — La scadenza del ponte sopra i cinque minuti.** Metti `ponte.bridge_deadline_min` a
**10**, rendi il piano irraggiungibile, manda un messaggio, e guarda. A cinque minuti il
browser scrive:

> Ho smesso di aspettare dopo cinque minuti. Se la risposta arriva, la trovi in questa
> conversazione ricaricando la pagina.

e il ripiego parte **dopo**, senza che tu lo veda. La risposta si ritrova ricaricando. Il
ripiego vive nella richiesta di poll, e la pagina della chat smette di chiedere a cinque
minuti fissi. **Con il predefinito (5) il caso è al confine e non si presenta.** Da
guardare: se questa forma è accettabile, oppure se il campo va fermato a 5, oppure se le due
costanti vanno legate. È la prova che serve per decidere, e non c'è modo di deciderlo da qui.

**10.4 — I tre numeri che restano fermi.** Dopo la migrazione, questi tre non si cambiano
più da nessuna parte:

| Opzione | Dove si vede | Dove si cambia |
|---|---|---|
| `ponte.bridge_deadline_min` | nel connettore sotto la riga del piano | **da nessuna parte** |
| `ponte.chat_daily_cap` | nella riga di stato del piano | **da nessuna parte** |
| `local_model.request_timeout` | nel connettore sotto la riga di Ollama | **da nessuna parte** |

**Cosa fare.** Cambia `ponte.bridge_deadline_min` nella configurazione dell'add-on,
riavvia, e verifica che il connettore nella pagina Modelli **continui a dire il numero di
prima**. È il comportamento atteso, ed è per questo che va guardato: conferma che il debito
è reale e misura quanto pesa. La pagina li **mostra** e non li fa cambiare, perché il
«campo» che li renderebbe modificabili non è stato costruito da nessun passo di questa
fetta.

---

## Prova 11 — Chi aveva fissato un modello in «Impostazioni chat»

Riguarda solo chi, prima di aggiornare, aveva scelto un modello diverso da «auto» in
«Impostazioni chat».

**Cosa fare.** Apri il log al primo avvio e cerca:

```
impostazioni_chat.json contiene 'model' (…) di una versione precedente: non e'
piu' letto -- la chat usa sempre la catena della pagina Modelli. Sparira' dal
file al primo salvataggio.
```

**Cosa si deve vedere.** La riga porta **il valore che c'era**. Quel valore **non viene
migrato** — non c'è dove metterlo, perché adesso il modello si sceglie per provider — e
sparisce dal file al primo salvataggio delle impostazioni.

**Che cosa fare dopo.** Aprire la pagina Modelli e **rimettere quella scelta** sulla riga
del provider giusto. È l'unica cosa che questa versione chiede di rifare a mano, ed è
scritta anche nel CHANGELOG.

---

## ⛔ Il cancello: le cinque precondizioni della versione successiva

**Questa non è una prova, è una condizione di rilascio.** La versione successiva toglie
quattordici opzioni dalla configurazione dell'add-on. Home Assistant scarta le chiavi fuori
schema **prima** che `/data/options.json` esista: se la rimozione arrivasse nello stesso
aggiornamento della copia, al primo avvio l'ambiente sarebbe già muto e HIRIS copierebbe
**i predefiniti** — cioè esattamente la perdita silenziosa che la copia esiste per evitare.

**Le cinque condizioni. Si leggono dal vivo, non si assumono.**

1. La **2.5.0** è **pubblicata** e **installata** sull'impianto del proprietario, e ha
   girato almeno un avvio completo.
2. Il log dell'add-on porta **le due righe della semina** — `Migrazione (versione A): …` e
   `Migrazione della catena: …` — **coi valori veri**, verificati uno per uno contro le
   opzioni (Prova 2).
3. `/data/models_config.json` contiene `"seminato": true`, `"catena_seminata": true`
   **e** la `chain_order` giusta.
4. `/data/impostazioni_chat.json` **esiste** e contiene `"giorni_conservazione"`, **col
   valore vero** — quello che avevi in `history_retention_days`, non il predefinito 90.

   *Perché è una condizione a sé e non un dettaglio della 3.* Questo campo vive in un
   **archivio diverso**, e le prime tre precondizioni guardano solo `models_config.json`:
   passerebbero tutte e tre con `impostazioni_chat.json` che quella chiave non l'ha mai
   vista. E la conseguenza non è un default sbagliato: chi aveva messo **`0`** («non
   cancellare mai») si ritroverebbe **90**, e la potatura notturna delle 3 comincerebbe a
   cancellare le conversazioni più vecchie di novanta giorni. Perdita di dato
   irreversibile.

   Nel log dell'add-on, al primo avvio, c'è la riga che lo dichiara:

   ```
   Migrazione (versione A): 'giorni_conservazione' (…) e' stato scritto in
   impostazioni_chat.json -- da adesso si cambia dalla pagina Impostazioni chat, e
   l'opzione dell'add-on 'history_retention_days' non serve piu'.
   ```

   Se al suo posto compare la riga che comincia con «**NON e' stato scritto su disco**», il
   cancello **resta chiuso**: si apre «Impostazioni chat» dentro HIRIS, si salva a mano, e
   si ricontrolla il file.

5. `/data/models_config.json` contiene **`"ponte": {"attivo": …}` col valore che stai
   usando davvero** — cioè `true` se oggi la chat passa dal Piano Claude Max.

   *Perché è una condizione a sé e non un dettaglio della 3.* Le prime tre nominano
   `seminato`, `catena_seminata` e `chain_order`, e **non nominano il campo la cui perdita è
   l'intera avvertenza della versione successiva**. E non è un dettaglio del formato: la
   copia della 2.5.0 avviene **una volta sola, al suo primo avvio**, mentre nella 2.5.0
   `app["ponte_attivo"]` si legge ancora **dall'ambiente**. Sono due orologi diversi. Delle
   quattordici opzioni, **due sole restavano vive dopo quel primo avvio** — `ponte.attivo` e
   `provider_subscription` — e sono precisamente le due il cui valore d'archivio può essere
   **più vecchio di quello che l'impianto sta usando**: chi ha acceso il ponte *dopo* quel
   primo avvio lo ha acceso nella 2.5.0 e non nell'archivio.

   Le altre dodici non hanno questo problema: nella 2.5.0 erano già lette dall'archivio, e
   una copia definitiva è quello che sono.

   Si legge da `GET /api/models/config`, che quel campo lo pubblica
   (`ponte: {attivo, scadenza_min, tetto_giornaliero}`) — lo stesso endpoint della 3. Se
   dice `false` mentre oggi la chat passa dal piano, il cancello **non resta chiuso**: la
   versione successiva si può pubblicare lo stesso, perché la riparazione è un click nella
   pagina Modelli e la versione stessa la dichiara in tre posti. Ma va **saputo prima**, non
   scoperto dalla fattura.

**Finché non ci sono tutte e cinque, la versione successiva non si comincia.** Non è una
formalità: è già costata una lezione su questo ramo.

### Come si è chiuso, il 14 agosto 2026

**Aperto con due condizioni verificate e due prese per parola del proprietario**, ed è
scritto qui perché un cancello che si apre senza dire come si è aperto non è un cancello.

- La 1 è verificata: la 2.5.0 è pubblicata e installata, **e contiene `c055310`** — cioè le
  tre chiusure critiche della revisione precedente, committate con lo stesso numero di
  versione. È la conferma che mancava alla revisione della 3.0.0, e con lei cade il rischio
  peggiore che il cancello copriva: `giorni_conservazione` **è stato scritto**, quindi chi
  aveva `0` non si ritrova `90` e la potatura notturna non comincia a cancellare.
- La 3 e la 4 sono confermate **dal proprietario**, che ha aperto `GET
  /api/models/config` e le impostazioni della chat e ha visto le chiavi. Non lette
  direttamente da chi ha scritto la 3.0.0.
- **La 5 è verificata, ed è passata:** `GET /api/models/config` sull'impianto del
  proprietario dice **`ponte.attivo` = `true`**. Il ponte era già acceso *prima* del primo
  avvio della 2.5.0, quindi la copia lo ha preso giusto. Su questo impianto la perdita del
  ponte **non avviene**, e non c'è nessun click da fare dopo l'aggiornamento.

  La precondizione è stata scritta **dopo** che la 3.0.0 era già stata composta, dalla
  revisione che l'ha esaminata: le prime quattro non nominavano il campo la cui perdita è
  l'intera avvertenza di quella versione. Resta qui perché il difetto è reale per chiunque
  abbia acceso il ponte dopo quel primo avvio, anche se il proprietario non è in quel caso.
- **La 2 non è verificata.** Il log consegnato copre due ore e **non contiene l'avvio**:
  25.858 righe del lavoratore del ponte, che interrogava la coda ogni tre secondi a
  livello `debug`, avevano spinto fuori il boot.

**Perché si è proceduto lo stesso.** Il rischio che il cancello previene è che la copia
prenda **i predefiniti** perché l'ambiente è già muto. Ma la 3.0.0 non era mai stata
pubblicata, quindi al momento della copia `run.sh` esportava ancora tutte le opzioni: la
copia **non poteva** aver preso predefiniti. Il cancello resta giusto come regola; la
condizione che rendeva pericoloso saltarlo non esisteva.

**E una conseguenza operativa che vale oltre questo cancello:** quelle 25.858 righe di
`debug` sono la ragione per cui una precondizione non si è potuta verificare. Dalla 3.0.0
il lavoratore del ponte **si ferma** quando il ponte si spegne (prima girava finché
l'add-on non veniva riavviato): il rumore c'è solo quando il ponte serve davvero.

---

## Come si riferisce l'esito

Per ogni prova, tre righe:

- **Passata / Fallita / Non eseguita** (e perché, se non eseguita);
- **cosa si è visto**, con le righe di log copiate **alla lettera** — non riassunte: nella
  fetta precedente il difetto vero è stato trovato solo perché il foglio chiedeva di
  copiare una riga di log che nessuno guardava;
- per le prove 9 e 10, **una fotografia**.

E una riga finale, che è quella che conta: **il caso della Prova 1 si legge a colpo
d'occhio, sì o no.**
