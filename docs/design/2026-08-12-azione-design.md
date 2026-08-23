# L'azione torna in HIRIS — specifica

*Nata dal brainstorming del 12 agosto 2026, dopo la pubblicazione della 2.0.1.*

## 0. Il punto di partenza, e cosa lo cambia

HIRIS 2.0 **conosce e non agisce**. L'azione era uscita con la fetta E2, insieme al semaforo, agli
Agentbot e alle notifiche. Questa specifica la riporta dentro — ma con una premessa che cambia la
natura del problema, e che va letta prima di tutto il resto:

> **C'e' sempre un umano che chiede.** Nessuna azione nasce da sola: la origina una frase in chat.
> L'autonomia sara' il *brain*, piu' avanti, ed e' un altro problema con un'altra specifica.

Ne segue una conseguenza che ha riorientato l'intero progetto a meta' del brainstorming: il rischio
**non e'** che HIRIS faccia qualcosa di sua iniziativa alle tre di notte. Il rischio e' che **faccia
male la cosa che gli e' stata chiesta**. Non e' un problema di *contenimento*, e' un problema di
**competenza**. Serve un artigiano, non una gabbia.

**Sequenza decisa dal proprietario:** prima si costruisce la capacita', **poi** si applica la
sicurezza. Le due si progettano separate. Questa specifica non porta cancelli.

**Ordine delle fette, deciso:** **comandare → costruire → schedulare.**

## 1. I quattro strati del «come si fa»

La domanda che ha aperto il brainstorming era: *come fa HIRIS a sapere cosa fare?* Non e' una cosa
sola. Sono quattro, e vengono da posti diversi.

| strato | cos'e' | da dove viene | oggi |
|---|---|---|---|
| **meccanismo** | cosa e' tecnicamente possibile: quali servizi esistono, quali parametri accettano, cosa supporta questa entita' | `/api/services` di Home Assistant + attributi di capacita' | **assente** |
| **idioma della casa** | come *questa* casa fa le cose: quali entita' si toccano insieme, con che valori, come si nominano | automazioni, script e scene gia' scritti dall'utente | **assente** (le automazioni si conoscono **solo per nome**) |
| **intenzione** | cosa vuol dire una frase qui dentro: «buonanotte» significa spegnere tutto tranne il corridoio | i ricordi (`ricorda` / `richiama`) | **esiste** |
| **mestiere** | quale struttura serve: una cosa che si ripete e' un'automazione, una sequenza che invochi e' uno script, un insieme di stati e' una scena | il modello + l'idioma della casa | parziale |

**Cosa legge HIRIS oggi da Home Assistant** (verificato): `/api/config`, `/api/states`, e i registri
(aree, dispositivi, entita') via websocket. **Non legge `/api/services`.**

**Sul mestiere, una precisazione onesta.** Il modello conosce bene i *concetti* di Home Assistant.
Sulla **sintassi corrente** e' inaffidabile, per una ragione strutturale: gli schemi di HA cambiano
(`service:` → `action:` dentro le automazioni, le chiavi al plurale), e un modello ha letto
soprattutto configurazioni **vecchie**. Puo' scrivere con assoluta sicurezza una sintassi che questa
installazione rifiuta. **Non e' un problema, se non si insegna ma si verifica** — vedi §2.

Nessuno dei quattro strati richiede che si scriva e si mantenga un catalogo: il meccanismo lo
dichiara HA, l'idioma lo insegna la casa, l'intenzione la dichiara l'utente, il mestiere ce l'ha il
modello e lo corregge HA.

## 2. Il fondamento — invarianti che valgono per tutte e tre le fette

### 2.1 Una porta sola

Esiste **un unico punto** in tutto il sistema che esegue qualcosa su Home Assistant. La chat non
chiama i servizi: **chiede a quella porta**. Lo schedulatore idem. Il brain, domani, idem.

Verifica, registro e — quando si vorra' — le sicurezze si scrivono **una volta** e valgono per
chiunque. Due porte significano che una delle due verra' dimenticata.

*(Stessa forma dell'unico punto d'uscita `_reply` gia' adottato per la redazione dei segreti.)*

### 2.2 Verificare, non insegnare

Nessun catalogo da tenere allineato. Il modello propone; **prima** di agire si controlla contro
**questa** installazione:

- **per i comandi** — il servizio esiste? l'entita' lo supporta? il parametro e' ammesso? (registro
  dei servizi + attributi di capacita');
- **per gli artefatti** — li **valida Home Assistant** al salvataggio, e l'errore torna indietro col
  motivo: il modello si corregge su un fatto della tua installazione, non su un ricordo.

Conseguenza voluta: **un'integrazione installata fra sei mesi funziona senza che nessuno tocchi
HIRIS.**

### 2.3 Dire cosa e' successo, non cosa e' stato chiesto

Dopo aver agito, HIRIS **rilegge lo stato**. «L'ho spenta» solo se e' spenta. Se la chiamata e'
partita e la luce e' ancora accesa, lo dichiara. E' la legge del prodotto — *dichiarare cio' che non
sa invece di fingerlo* — applicata all'azione.

### 2.4 I costruttori costruiscono, non inoltrano

Vale dalla fetta 2, si fissa qui perche' e' **la scorciatoia che verra' in mente a chiunque
implementi di fretta**: un costruttore che riceve lo YAML gia' scritto dal modello e lo gira a Home
Assistant **non e' un imbuto, e' un tubo con un bel nome**. Ogni costruttore compone dai
**parametri**.

### 2.5 Il rifiuto porta il motivo

Quando HIRIS non fa una cosa, dice **perche'**: «questo servizio non esiste», «questa luce non si
attenua». Mai «non posso».

## 3. Fetta 1 — Comandare

HIRIS acquista un quinto strumento accanto a `cerca`, `guarda`, `ricorda`, `richiama`: **`esegui`**.

**Cosa entra:**
1. **lettura del registro dei servizi** (`/api/services`) — oggi assente. Cache con invalidazione:
   le integrazioni si installano a caldo;
2. **la porta unica** (§2.1) con la **verifica prima della chiamata** (§2.2);
3. **la rilettura dopo** (§2.3);
4. **il registro di cio' che e' stato fatto**: una riga leggibile per esecuzione — cosa, su cosa,
   esito.

**Cosa vede l'utente:** cosa ha fatto, su cosa, com'e' andata; e quando rifiuta, il motivo vero.

**Cosa NON c'e', dichiarato:** nessun artefatto, nessuna schedulazione, nessuna autonomia.

**Nota sui permessi:** `hiris/config.yaml` dichiara gia' `hassio_api: true` e
`homeassistant_api: true`. **Il potere di agire c'e' gia'** e non va chiesto nulla di nuovo
all'utente — fatto da sapere, non da festeggiare.

## 4. Fetta 2 — Costruire

> **SUPERATA** dalla spec `docs/design/2026-08-22-costruire-in-home-assistant.md` (22 agosto 2026).
> Questa sezione era stata scritta senza leggere il sorgente di Home Assistant: tre delle sue
> premesse non reggono ai fatti, una questione che lasciava aperta si è chiusa, e tre affermazioni
> si sono confermate — la tabella dei perché è al §1.3 della nuova spec. Resta storia, non
> specifica.

**Nel perimetro: automazione, script, scena.** La **plancia resta fuori** (§4.3).

### 4.1 I costruttori

Uno per struttura, **unici a scrivere** su Home Assistant, e costruiscono dai parametri (§2.4).
Il modello produce **l'intenzione**, non l'artefatto.

### 4.2 Le tre regole della fetta

- **Le automazioni nascono disabilitate.** Non e' un cancello: e' il **banco di prova**. Si legge, si
  fa partire a mano, si mette in servizio quando convince — come chi la scrive a mano.
- **Prima di sovrascrivere, si salva cio' che c'era.** Home Assistant **non tiene storico**: la
  versione precedente esiste solo se HIRIS se l'e' messa via. E' il componente che rende possibile
  **«annulla» detto a voce**.
- **E consiglia.** Quando la richiesta arriva nella forma sbagliata — un'automazione per qualcosa che
  e' uno script — lo dice e propone. Poi fa cio' che l'utente decide.

### 4.3 Perche' la plancia sta fuori

L'API di Home Assistant per salvare una dashboard **non modifica: riscrive l'intera
configurazione**. Non esiste «aggiungi questa card». Un errore li' non sbaglia una card: **cancella
mesi di lavoro**. E' l'unica struttura dove il costruttore deve **leggere, fondere e riscrivere**
invece che comporre: problema diverso, fetta propria.

### 4.4 L'errore del prodotto precedente, da non ripetere

La HIRIS pre-2.0 aveva `create_ha_config`, che dalla chat **scriveva subito** script e scene su Home
Assistant — ed era **esattamente l'unica cosa che il semaforo non copriva**. La cosa irreversibile
passava senza controllo mentre l'accensione di una luce ne aveva uno. Non fu una svista: fu il
risultato del non aver separato **comandare** (immediato, reversibile dicendo il contrario) da
**costruire** (persistente, agisce da solo, si annulla solo andandolo a cercare).

## 5. Fetta 3 — Schedulare

**Un magazzino con un orologio.** Non decide, non interpreta, **non sa chi gli ha scritto**: tiene
*cosa* e *quando*, e al momento giusto passa dalla **porta di tutti** (§2.1). Oggi ci scrive la chat;
domani un altro attore, senza che lo schedulatore cambi.

**Tre condizioni vincolanti:**

1. **Persistito su disco.** L'add-on si riavvia — aggiornamenti, riavvii di HA, guasti. «Fra un'ora»
   non deve svanire in silenzio.
2. **Se salta, lo dichiara.** Cio' che doveva succedere alle 14 e non e' successo si registra come
   **non eseguito, con il motivo**. **Mai recuperato in ritardo** fingendo che vada bene: una luce
   che si accende alle 19 perche' doveva accendersi alle 14 e' peggio di una luce spenta.
3. **Si vede.** Un posto dove guardare cosa e' in sospeso e annullarlo. Promesse che HIRIS tiene e
   non mostra sarebbero **stato invisibile** — il difetto che il ramo 2.0 ha appena finito di
   togliere da tutto il resto.

**Perche' non un'automazione di Home Assistant.** Fare «accendi fra un'ora» creando un'automazione
vera riempie la configurazione dell'utente di **automazioni usa-e-getta che nessuno cancella**.

## 6. Cosa resta fuori, e perche'

- **La plancia** — §4.3. Fetta propria.
- **L'autonomia (il brain)** — HIRIS non decide *quando* agire. Altra specifica.
- **Le sicurezze** — decisione del proprietario: prima la capacita'. Vedi
  `project_hiris_debiti_sicurezza_2_0` in memoria: il testo dei ricordi entra verbatim nel prompt di
  sistema, `proxy/_sanitize.py` e' irraggiungibile. **Innocuo finche' HIRIS non agisce; da affrontare
  quando si affronteranno le sicurezze.**
- **L'integrazione documentale (Mayan)** — gia' decisa fuori: esce con una fetta dedicata prima di
  questa (l'archivio di conoscenza scrive e nessuno legge; e `translations` dichiara all'utente una
  protezione che oggi e' falsa).

## 7. Le verifiche che nessun banco puo' dare

**La fetta 1 non e' pubblicabile senza un giro sulla casa vera.** Verificare i servizi contro il
registro e' precisamente cio' che nessuna suite verde puo' provare: la prima volta che HIRIS spegne
una luce dev'essere **una luce vera, con il proprietario davanti**.

Idem per la fetta 2 (una configurazione rifiutata da *questa* installazione) e per la 3 (un riavvio
dell'add-on con qualcosa in sospeso).

## 8. Questioni aperte — dichiarate, non risolte

1. **`automation.trigger` esegue un'automazione disabilitata?** Risulta di si': «disabilitata»
   impedisce ai *trigger* di scattare, non l'esecuzione su richiesta. **Da verificare sulla versione
   di HA in uso** prima di appoggiarci qualsiasi ragionamento (oggi non ci si appoggia niente:
   «disabilitata» e' un banco di prova, non un cancello — §4.2).
2. ~~L'API di configurazione delle automazioni funziona se l'utente le gestisce a mano in YAML?~~
   **CHIUSA (12 agosto, dal proprietario): «per ora le gestisco tutte con la UI di HA».** Quindi
   automazioni, script e scene stanno nei file gestiti dall'editor, e
   `/api/config/automation/config/<id>` — la stessa API che usa quell'editor — e' la strada.

   **Ma resta un presupposto, e va trattato come tale.** Vale *oggi* e per *questa* casa: chi
   gestisce le automazioni a mano in YAML (o le tiene in `packages/`) non ha quell'API, e i
   costruttori non possono scrivere. Quindi **il costruttore non deve dare per scontato l'impianto:
   deve accorgersene.** Se l'API risponde che quella struttura non e' modificabile, HIRIS lo dice —
   «queste automazioni sono gestite a mano, non posso scriverle» — invece di fallire in un modo che
   sembra un guasto. E' la legge §2.5 applicata a un presupposto d'ambiente.
3. **Come si riconosce un artefatto creato da HIRIS?** Serve per modificare i propri senza toccare
   quelli scritti a mano dal proprietario. Convenzione da decidere (prefisso? etichetta? registro
   interno?).
4. **Dove vive la faccia dello schedulatore?** Una nuova voce di menu, o dentro una pagina esistente.
5. **«Testare» un'automazione vuol dire eseguirla davvero.** In Home Assistant non esiste una prova a
   vuoto: le luci si accendono sul serio. «Testa» ed «esegui» sono la stessa azione con due
   intenzioni diverse — da tenere presente in come lo si racconta all'utente.

## 9. Fuori portata di questa specifica

Ogni fetta avra' il suo piano d'implementazione. Questa specifica fissa **il fondamento, l'ordine e i
confini**; non decide nomi di funzioni, forme di API interne, ne' schemi di dati.
