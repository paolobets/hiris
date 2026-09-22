# I canali e i ruoli — chi parla con HIRIS, e quanto gli si concede

`spec · 21/09/2026 · invariante I-2 dello sprint sicurezza`

Nasce dal registro dei rischi dello stesso giorno (`2026-09-21-sicurezza-esposizioni.md`) e dalle
decisioni che il proprietario ha preso una alla volta il 21/09. Copre **tutti e sette** gli ingressi
di HIRIS, dentro e fuori Home Assistant, perché progettare la sicurezza di un ingresso alla volta è
il modo in cui restano i buchi fra l'uno e l'altro.

Presuppone I-0 (*un cancello chiede il suo elenco, non lo ricopia*) e I-1 (*ogni richiesta ha un
soggetto*), già vivi.

---

## §0 · Le tre decisioni che hanno formato questa spec

**1. Non si limitano i servizi.** *«Non vorrei limitare i servizi, così castriamo HIRIS e non segue
la versione.»* Una lista di servizi invecchia a ogni rilascio di Home Assistant, e si aggira
comunque scrivendo il servizio dentro il corpo di un'automazione. Il bersaglio era sbagliato: **il
pericolo non è il servizio, è che il modello sia stato convinto da un testo letto in casa** —
`lock.unlock` chiesto dal proprietario è il prodotto che funziona, lo stesso `lock.unlock` suggerito
da una riga di registro è l'attacco, e nessuna lista li distingue.

**2. HIRIS non è più stretto di Home Assistant.** Un utente non amministratore comanda già le sue
entità dalla plancia: impedirglielo dentro HIRIS non toglie un potere a nessuno. Ciò che va chiuso è
il verso opposto — HIRIS **amplifica**, perché parla con HA col proprio token, che è amministratore.

**3. Il ruolo viaggia con la credenziale.** *«Quando si rilascia il token per configurare quei
dispositivi gli si assegna anche un permesso: esempio ruolo admin, ruolo user, così non gestisce
automazioni e altro, quindi comanda.»* È la decisione che fa collassare il disegno: il ruolo non si
deduce da dove sta un dispositivo — **lo si dichiara quando lo si registra**.

---

## §1 · I fatti su Home Assistant, verificati il 21/09/2026

Regola del progetto: su HA non si ipotizza. Ogni riga qui sotto è stata letta sulla documentazione
per sviluppatori o sul sorgente, non dedotta.

| Fatto | Dove |
|---|---|
| `panel_admin` (default `true`) nasconde **la voce di menu**, non difende l'URL: *«Make the menu entry only available to users in the admin group»* | doc add-on |
| Il proxy di ingress **non ha nessun controllo di ruolo**: l'unico requisito è `if not self.sys_ingress.validate_session(session)` | `supervisor/api/ingress.py` |
| Il proxy aggiunge `X-Remote-User-Id`, `X-Remote-User-Name`, `X-Remote-User-Display-Name` da `session_data.user`, e **filtra via le stesse intestazioni in ingresso** | `supervisor/api/ingress.py::_init_header` |
| Il Supervisor proxa verso il nucleo **con la propria sessione privilegiata**: le chiamate di un add-on sono attribuite a un utente di sistema amministratore | `supervisor/api/proxy.py` |
| `context(msg)` costruisce il contesto **dall'utente autenticato, ignorando il messaggio**: nessuna delega, nessuna impersonazione | `websocket_api/connection.py` |
| HA fa rispettare i permessi per entità **su `call.context.user_id`**, dentro la macchina delle chiamate: `if not user.is_admin: entity_perms = user.permissions.check_entity` | `helpers/service.py` |
| `config/auth/list` è `@websocket_api.require_admin` e restituisce `group_ids`, **non** `is_admin` | `components/config/auth.py` |
| `admin_only` **non è mai esposto ai client** nelle descrizioni dei servizi | `helpers/service.py` |
| `ConversationInput` porta `context`, `device_id`, `satellite_id`: **con la voce non c'è una persona, c'è un dispositivo** | `components/conversation/models.py` |
| `config/label_registry/create` richiede admin — la porta che HIRIS usa già, e la prova indiretta che la sua connessione abbia i diritti per `config/auth/list` | `components/config/label_registry.py` |

**Resta da misurare dal vivo**, e va fatto al primo rilascio: che `config/auth/list` risponda davvero
nell'add-on. Se non rispondesse, il ruolo sarebbe illeggibile e — per il verso del dubbio — nessuno
potrebbe costruire, **nemmeno il proprietario**. Il registro lo dichiara con la conseguenza scritta
per esteso.

---

## §2 · Il modello: tre domande, e vale il minore

Ogni richiesta che arriva a HIRIS risponde a tre domande. Il soffitto è **il minore** delle tre
risposte — mai la somma, mai la più generosa.

```
1. DA DOVE arriva   →  il canale, e con quale credenziale prova di essere lui
2. CHI c'è dietro   →  la specie del soggetto, e la sua identità quando c'è
3. QUALE RUOLO ha   →  amministratore · utente · lettore
```

La terza è quella che decide, ed è nuova solo nella **provenienza**: per una persona il ruolo lo dice
Home Assistant, per tutto il resto lo dice **la registrazione**. Da cui **una sola funzione** che
decide il soffitto, con quattro sorgenti diverse per il suo ingresso — invece di quattro funzioni
che si somigliano e divergono al primo cambiamento (fondamenta 2).

---

## §3 · Le quattro specie di soggetto

| specie | chi è | come lo si sa | esempi |
|---|---|---|---|
| **persona** | un utente di Home Assistant, identificato | sessione HA, `X-Remote-User-Id` | pannello ingress · card lovelace · Assist **scritto** |
| **luogo** | nessuno si è autenticato, ma si sa **dove** | il dispositivo, il satellite, il pannello | Retro Panel · Assist **parlato** |
| **integrazione** | una macchina | firma Ed25519 | gateway MCP · porta di sviluppo |
| **nessuno** | HIRIS per conto suo | — | schedulatore · osservatore · analista · attuatore · ponte |

**`luogo` è la specie che il quadro intero ha fatto emergere**, e non era nel disegno iniziale. Non è
«anonimo»: un anonimo è qualcuno di cui non si sa niente, un luogo è **qualcuno che è fisicamente in
casa** — informazione vera, diversa, e che vale la pena tenere distinta. Un pannello in corridoio e
un altoparlante in cucina sono la stessa cosa, e trattarli come due casi sarebbe il doppione per
forma.

**Il soggetto esiste sempre.** «Non so chi sei» produce una persona anonima, non l'assenza di un
soggetto: un campo mancante e un campo vuoto si confondono al primo lettore distratto, due parole
diverse no. (Già vivo da I-1.)

---

## §4 · I tre ruoli

Il vocabolario è **quello di Home Assistant**, non uno nostro: `amministratore` e `utente`
corrispondono a ciò che HA chiama admin e non-admin, così un proprietario che conosce HA non deve
imparare un secondo sistema. `lettore` è il terzo, e serve a un caso che HA non ha: una macchina che
deve **misurare senza toccare**.

| ruolo | legge | comanda | costruisce | chi lo ha |
|---|:--:|:--:|:--:|---|
| **amministratore** | ✓ | ✓ | ✓ | il proprietario dal pannello · un pannello di fiducia |
| **utente** | ✓ | ✓ | ✗ | Retro Panel · altoparlante · un familiare in HA |
| **lettore** | ✓ | ✗ | ✗ | una macchina che deve **misurare senza toccare** |

**Perché `costruire` è la sola cosa riservata, e non i servizi di sistema.** I servizi di sistema
(`homeassistant.restart`, `hassio.host_reboot`, `recorder.purge`, `shell_command.*`) sono **già
irraggiungibili** dalla porta: non dichiarano un bersaglio, e un bersaglio vuoto è sempre un rifiuto
(`action/verification.py`). L'unica amplificazione vera è la scrittura della configurazione. Una
porta, due valori — e niente che invecchi a ogni rilascio di HA.

**Il ruolo di un turno senza soggetto** (schedulatore, osservatore, analista, attuatore) non si
dichiara qui: lo decide il **mestiere** di quel turno, custodito dai cancelli che già esistono
(`_SELF_CONTAINED_KINDS`, `SOLA_LETTURA` delle promesse, il cancello dell'attuatore).

---

## §5 · I sette ingressi

| # | ingresso | credenziale | specie | ruolo da | stato |
|---|---|---|---|---|---|
| 1 | **pannello ingress** | sessione HA + IP del proxy | persona | `config/auth/list` | ✅ I-1 |
| 2 | **card lovelace** | sessione ingress creata dal browser | persona | `config/auth/list` | da costruire |
| 3 | **Assist scritto** | `context.user_id` da HA | persona | `config/auth/list` | da costruire |
| 4 | **Assist parlato** | `device_id` / `satellite_id` | luogo | registrazione | da costruire |
| 5 | **Retro Panel** | firma Ed25519 | luogo | registrazione | I-2 fetta 2 |
| 6 | **porta 8099** | firma Ed25519 | integrazione | registrazione (`lettore`) | I-2 fetta 1 |
| 7 | **ponte** | credenziale effimera per turno | nessuno | il mestiere del turno | I-2 fetta 3 |

**Nota sull'ingresso 2.** `panel_admin: true` nasconde la voce di menu ai non amministratori, ma una
card su una plancia **la vedono tutti**. Costruirla significa esporre HIRIS a chi oggi non lo apre:
è una decisione di prodotto, non un dettaglio d'interfaccia. Il soffitto di I-1 regge (comandare sì,
costruire no), e va detto invece che scoperto.

**Nota sull'ingresso 7.** Il ponte non è un canale di rete: gira dentro il container. Una chiave a
vita lunga tornerebbe nella riga di comando del sottoprocesso, che è il reperto C-3 — leggibile per
300 secondi da qualunque processo. Per lui la risposta è una credenziale **effimera**, legata al
turno e senza valore fuori di esso.

---

## §6 · La credenziale di un canale

### Perché asimmetrica

`/data` finisce nei backup di Home Assistant, che sono in chiaro se l'utente non gli mette una
password (reperto C-4). Con **un segreto per canale**, chi legge un backup può impersonare quel
canale. Con una **chiave pubblica**, non ottiene niente.

È questa la differenza fra «segreto» e «non falsificabile», ed è la ragione per cui la credenziale è
una coppia di chiavi e non un secondo token: l'integrazione tiene la privata, **HIRIS non tiene
nessuna chiave che serva a firmare**.

Costo: `cryptography` diventa una dipendenza di produzione. Misurato il 21/09 su PyPI: esistono
wheel `musllinux_1_2_aarch64` e `musllinux_1_2_x86_64`, cioè entrambe le architetture che HIRIS
dichiara — **nessuna compilazione** in fase di costruzione dell'immagine.

### Cosa viaggia

```
X-HIRIS-Servizio: <chiave pubblica, base64>
X-HIRIS-Momento:  <secondi>
X-HIRIS-Unico:    <valore irripetibile>
X-HIRIS-Firma:    <firma, base64>
```

**Porta la chiave, non il nome** (22/09). La chiave pubblica *è* l'identità del servizio: un nome
sarebbe una seconda rappresentazione dello stesso fatto, e due rappresentazioni divergono. Il nome
resta — ma è un'etichetta per il proprietario, e non riconosce nessuno.

E la materia firmata, che le due parti devono condividere e che vive **scritta una volta sola**:

```
metodo ⏎ percorso ⏎ momento ⏎ unico ⏎ impronta-sha256(corpo)
```

**La firma copre la richiesta, non l'identità.** Firmare la sola identità lascerebbe cambiare ciò
che la richiesta chiede tenendo buona la firma, e lascerebbe valere per una scrittura una firma nata
per una lettura.

### Le tre difese contro «qualcuno in mezzo»

1. **La finestra**, in entrambi i versi. Una firma intercettata non vale per sempre; e controllare
   solo il passato lascerebbe che un orologio avanti di un'ora allarghi la finestra di un'ora,
   cioè lascerebbe **al chiamante** il compito di deciderla.
2. **Il valore irripetibile**, ricordato per la durata della finestra. Senza, dentro la finestra una
   richiesta intercettata e rimandata identica sarebbe ancora valida.
3. **L'approvazione** (§7): una firma perfetta di una chiave che il proprietario non ha approvato
   viene rifiutata. E il **codice a quattro cifre** dell'accoppiamento difende il primo contatto,
   che è l'unico momento in cui «qualcuno in mezzo» avrebbe qualcosa da guadagnare.

### Cosa non fa

Non sostituisce TLS e non lo finge: la riservatezza del contenuto resta del trasporto. Questa
credenziale risponde a *chi sei* e *questa richiesta è intatta*, non a *chi può leggerla*.

---

## §7 · L'accoppiamento: il primo contatto è un evento che si approva

**Rifatto il 22/09/2026.** La prima stesura metteva chiave e ruolo in un campo di testo delle
opzioni dell'add-on. Il proprietario l'ha respinta per tre ragioni che quel campo non può risolvere:

- **ogni modifica riavvia l'add-on** — aggiungere un servizio spegne la casa per dieci secondi;
- **revocare significa editare un blob di testo**, invece di compiere un gesto;
- e soprattutto **non si vede mai quando un servizio si presenta la prima volta**: l'autorizzazione
  è già data prima che il servizio esista.

Il terzo punto è ciò che rende «by design» questo disegno, e non è la crittografia: è che **il primo
contatto è un evento che il proprietario vede e approva**.

### Il giro intero

| passo | chi | cosa |
|---|---|---|
| 1 | proprietario | apre la **finestra di accoppiamento**, che dura **dieci minuti** |
| 2 | servizio | genera la propria coppia di chiavi — **la privata non esce da lì, mai** |
| 3 | servizio | `POST /api/services/present` con la pubblica e un nome |
| 4 | HIRIS | mette una riga **in attesa** e torna un **codice di quattro cifre** derivato dalla chiave |
| 5 | proprietario | confronta quel codice con quello che il servizio mostra sul proprio schermo |
| 6 | proprietario | **approva**, scegliendo il **ruolo** (§4) e la **specie** |
| 7 | proprietario | può **revocare** in qualunque momento, e vale subito |

### Le tre decisioni che reggono il disegno

**La rotta di presentazione è l'unica superficie che questo prodotto non può autenticare**, e deve
esserlo: un servizio non ancora approvato *non ha modo* di autenticarsi. Invece di difenderla per
sempre — tetti sul numero di righe, limiti di ritmo, scadenze — si è scelto di **non farla
esistere**: il confine la esenta solo nei dieci minuti della finestra, e fuori di lì risponde 401
come qualunque altra. Una difesa permanente invecchia; una porta chiusa no.

**Il codice si deriva dalla chiave**, e non è casuale: così il servizio può mostrarlo senza scambiare
nient'altro con HIRIS. Un codice casuale richiederebbe un secondo scambio, e quel secondo scambio
sarebbe esattamente il punto in cui qualcuno si mette in mezzo. Quattro cifre non sono un segreto e
non devono esserlo: non difendono da chi indovina, difendono da chi si è messo in mezzo — che non
può far coincidere il proprio codice con quello che il servizio vero mostra sul suo schermo.

**Qui non vive nessun segreto.** Una chiave pubblica non lo è, e un codice derivato da essa nemmeno:
l'archivio dei servizi si può leggere per intero senza che ne esca niente di utile a nessuno. È la
stessa proprietà del §6, vista dal lato dell'archivio invece che da quello del backup.

### Chiude per difetto

Una chiave mai approvata: rifiutata, **anche con una firma perfetta**. Un servizio revocato che si
ripresenta: resta revocato, o ribussare annullerebbe la revoca. Una riga senza ruolo valido:
rifiutata, perché un ruolo che manca erediterebbe in silenzio qualcosa deciso dal codice invece che
dal proprietario. Ognuno dei rifiuti dice cosa manca: un rifiuto che non dice cosa fare è un ordine.

**Il campo di testo è uscito.** Due posti in cui si dichiara la stessa cosa sono la fondamenta 2
violata — ed è proprio ciò che questo progetto vieta.

### Cosa questo non difende

Chiunque possa raggiungere HIRIS nei dieci minuti della finestra può mettere una riga in coda. Non
ottiene niente — una riga in attesa non autorizza nulla — ma **può sporcare la pagina**. La difesa
non è un tetto: è che quelle righe scadono da sole in 24 ore, e che la finestra la apre una persona
per il tempo che serve a un accoppiamento.

---

## §8 · La convivenza è finita, e l'ha decisa una misura

**Chiusa il 22/09/2026.** Il gateway MCP e il proxy di Retro Panel vivevano in due repository
separati, e un taglio netto li avrebbe spenti: per una fetta HIRIS ha accettato **la firma oppure
il token**, e chi usava ancora il token si faceva misurare.

La fine la doveva decidere una misura e non una data, ed è andata così: il registro dell'add-on ha
smesso di nominare chiunque non firmasse — le due integrazioni erano inattive, il gateway è un
progetto chiuso, e la porta di sviluppo si è accoppiata e firma. Il ripiego è uscito **prima** della
data limite che lo custodiva, che è il verso giusto.

Con lui sono usciti: l'opzione `internal_token` dalla pagina dell'add-on, la sua variabile
d'ambiente, il modulo che lo generava e conservava, l'esenzione del CSRF, il punto d'ingresso del
worker come processo a sé (`main()`, che nessuno avviava) e la funzione che leggeva il segreto
dall'ambiente.

**Restano tre strade, e ognuna dice chi è**: la firma di un servizio approvato, l'ingress con la
sessione che il Supervisor riconosce, la credenziale di turno del ponte. Chi non ne ha nessuna
riceve un 401 che **dice cosa fare** — farsi accoppiare dalla pagina Servizi — perché
un'integrazione non aggiornata non deve passare il pomeriggio a leggere il registro.

### Cosa sorveglia il cancello, adesso

Il cancello della convivenza aveva una data e un ramo da custodire; tutti e due sono spariti col
ripiego. Al loro posto ne vive uno **nel verso opposto**: che il segreto condiviso **non torni**. È
la cosa più facile da riaggiungere — tre righe, e risolve qualunque integrazione che non ha voglia
di firmare — quindi il cancello guarda la **forma** del confine, non il comportamento, che non la
distinguerebbe da una credenziale legittima.

E accanto, la contropartita: le **tre strade devono esserci tutte**. Togliere e basta non è la
proprietà che si vuole — sarebbe «l'abbiamo spento», non «l'abbiamo messo in sicurezza».

---

## §9 · I cancelli

Ognuno **chiede il suo elenco** invece di ricopiarlo (I-0), e ognuno arriva con la sua mutazione
eseguita.

1. **Il confine esenta un percorso solo, e legato alla finestra.** Una seconda riga nell'esenzione
   sarebbe una seconda superficie non autenticata, e non deve poter nascere per distrazione: il
   cancello guarda la **forma** del confine, non solo il comportamento, perché l'esenzione potrebbe
   restare mentre il controllo della finestra sparisce.
2. **I ruoli sono un insieme chiuso**, e la tabella del §4 li copre tutti: un ruolo nuovo che nessuno
   ha mappato non è «permesso», è un ruolo su cui nessuno ha deciso.
3. **La materia firmata è una sola.** Se chi firma e chi verifica divergessero, ogni firma legittima
   verrebbe rifiutata e nessuno capirebbe perché.
4. **Nessuna rotta mutante senza una decisione** — già vivo da I-1, e si estende: la classificazione
   dirà anche quale ruolo serve.
5. **Il ripiego al token è temporaneo e si vede.** Una prova che fallisce quando il ramo del ripiego
   sopravvive a una data dichiarata: un rinvio senza scadenza è un rinvio che non finisce.

---

## §10 · Le fette

| | Cosa | Repository | Stato |
|---|---|---|---|
| **1** | Il meccanismo (firma, finestra, valore irripetibile) e i cancelli | solo HIRIS | ✅ **fatta il 21/09** |
| **1b** | **L'accoppiamento** (§7): archivio dei servizi, finestra di dieci minuti, codice a quattro cifre, approvazione e revoca dalla pagina — e il campo di testo esce | solo HIRIS | ✅ **fatta il 22/09** |
| **2** | Retro Panel si accoppia e firma | due repository | da fare |
| **3** | **Il perimetro**: il token esce, i CIDR si validano, la sessione di ingress si verifica col Supervisor (A-2, A-3, A-5) | solo HIRIS | ✅ **fatta il 22/09** |

Gli ingressi 2, 3 e 4 del §5 — card lovelace, Assist scritto, Assist parlato — **non esistono
ancora**: questa spec dichiara il loro posto nel modello perché nascano già dentro, invece di essere
messi in sicurezza dopo. La loro costruzione è una fetta di prodotto, non di sicurezza.

---

## §11 · Cosa resta fuori, dichiarato

- ~~**La cronaca non registra ancora chi.**~~ **Fatto nella fetta 1**: una colonna sola
  (`soggetto_json`) per tutte e quattro le specie, aggiunta e non riscritta — le righe di ieri
  restano con `soggetto` a `NULL`, che è ciò che sono. Il filo arriva dal confine fino all'atto:
  `execute`, `apply`, `restore` e i loro rami di fallimento.
- **Cosa resta fuori davvero:** Con questa spec il soggetto diventa anche «quale
  integrazione» e «quale luogo»: la colonna si aggiunge **una volta sola**, nella fetta 1, invece di
  due volte.
- **Le promesse non portano ancora chi le ha chieste.** Una promessa nata da una frase del
  proprietario ed eseguita tre giorni dopo si registra come «schedulatore», che è vero e
  insufficiente: la risposta piena sarebbe «la promessa che X ha fatto martedì». Serve una colonna
  nell'archivio delle promesse, ed è una fetta sua.
- **Il soffitto per area.** Un luogo potrebbe comandare solo le entità della sua area — HIRIS sa già
  risolvere aree e piani, quindi il dato c'è. Il proprietario ha scelto il ruolo, che è più semplice
  e più prevedibile; le due cose **si compongono** (ruolo `utente` *e* solo l'area ingresso) e il
  disegno non lo impedisce. Fuori adesso perché non serve adesso.
- **La marcatura del contenuto non fidato** (B-2 del registro) resta l'unica decisione di disegno
  aperta dello sprint, ed è un invariante suo.
- **TLS e il trasporto**: non è questa spec.

---

## §12 · Le decisioni, e chi le ha prese

Tutte del proprietario, il 21/09/2026, una domanda alla volta.

| # | Domanda | Decisione |
|---|---|---|
| 1 | Si limitano i servizi? | **No**: castrerebbe HIRIS e non seguirebbe la versione di HA |
| 2 | Quanto stringe HIRIS per un utente non amministratore? | **Solo ciò che HA già gli nega**: costruire |
| 3 | Chi decide il ruolo di un servizio? | **Il proprietario, caso per caso, al momento dell'approvazione** |
| 4 | Come si passa dal segreto condiviso alle chiavi? | **Convivenza dichiarata e misurata**, poi si chiude |
| 5 | `cryptography` in produzione? | **Sì, e lo vedo come un plus** |
| 6 | Il soffitto di un luogo? | **Il ruolo si assegna quando si rilascia la credenziale**: admin, utente |

E il 22/09/2026, dopo aver visto la fetta 1 dal vivo:

| # | Domanda | Decisione |
|---|---|---|
| 7 | I servizi si dichiarano in un campo di testo? | **No: una sezione in configurazione**, con approvazione alla prima presentazione e revoca |
| 8 | La chiave privata la genera chi? | **Il servizio, e non viaggia mai** |
| 9 | Quanto resta aperto l'accoppiamento? | **Dieci minuti. Chiusa la finestra si rifiuta** |

### Il ruolo non si scrive qui, e non è una dimenticanza

**Chiarito dal proprietario il 22/09/2026**, dopo aver accoppiato il primo servizio dal vivo:

> «Decido io quale ruolo concedo. In questo caso a Claude posso dare il ruolo amministratore anche
> per farmi aiutare a fare cose o verifiche approfondite — non mi legherei su quell'argomento.»

La prima stesura di questa spec assegnava un ruolo a un servizio per nome: «la porta di sviluppo è
`lettore`». **Quella riga è uscita**, ed è giusto che sia uscita: era una decisione presa una volta
e scritta in un documento, mentre la decisione vera si prende **ogni volta che si approva**, e
dipende da cosa quel servizio deve fare *oggi*.

Una specifica che assegna un ruolo per nome fa due danni. Invecchia in silenzio — il giorno in cui
il proprietario decide diversamente, il documento dice il falso e nessun cancello se ne accorge. E
scavalca il disegno: **il ruolo viaggia con la credenziale** (decisione 6) proprio perché non stia
scritto da nessun'altra parte.

Quindi: qui si scrive **cosa può ognuno dei tre ruoli** (§4). **Chi ha quale ruolo** vive in un
posto solo — l'archivio dei servizi, dove l'ha messo il proprietario approvando — e si legge dalla
pagina «Servizi», mai da un documento.
