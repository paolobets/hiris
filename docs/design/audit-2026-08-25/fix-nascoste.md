# Nascoste fuori dagli elenchi — sette luci mescolate in sala da pranzo

Ramo `fix/nascoste-fuori-dagli-elenchi`, da `2.0`. Bug trovato dal
proprietario usando il prodotto: ha chiesto a HIRIS le luci della sala da
pranzo, e `guarda("area", "sala_da_pranzo")` ha restituito sette luci
mescolate — tre lampade LIFX più una «lampadario fake», quattro delle sette,
che l'utente ha nascosto dalle proprie viste in Home Assistant e che HIRIS
non ha motivo di nominare quando nessuno gliele chiede esplicitamente.

Regola decisa dal proprietario: **«HIRIS non prende in considerazione le
entità nascoste, a meno che non gli vengano chieste esplicitamente.»**

---

## La misura del «prima», presa in produzione

Porta di debug `http://192.168.1.95:8099`, sola lettura, `POST /api/mcp`
(JSON-RPC, `tools/call`). Due chiamate, prima di toccare una riga di codice:

**`cerca(indice, "sala da pranzo")`** → l'area vera si chiama
`sala_da_pranzo`.

**`guarda("area", "sala_da_pranzo")`** → 64 entità nell'area, di cui sette
luci (`light.*`):

| entity_id | nome | nome_dedotto | nascosta | piattaforma |
|---|---|---|---|---|
| `light.lampadario_2` | — | Lampadario 2 | **true** | lifx |
| `light.lampadario_3` | — | Lampadario 3 | **true** | lifx |
| `light.lampadario` | — | Lampadario | **true** | lifx |
| `light.lampadario_sala_da_pranzo` | Lampadario sala da pranzo | — | false | group |
| `light.sala_pranzo_applique_...` | "" | Sala pranzo applique | false | ave_domina |
| `light.sala_pranzo_nicchia_...` | "" | Sala pranzo nicchia | false | ave_domina |
| `light.lampadario_fake_...` | "" | Lampadario fake | **true** | ave_domina |

Conferma esatta del racconto del proprietario: sette luci, quattro nascoste
(tre LIFX + «lampadario fake»), sei senza nome dichiarato nel registro
(`nome_dedotto` dallo specchio dello stato). Punto centrale della diagnosi:
**il campo `nascosta` era già presente e vero su ognuna delle quattro** —
`_arricchisci_entita` lo scriveva già prima di questa fetta — ma stare nella
STESSA lista di array (`entita`) non ha impedito che venissero elencate lo
stesso. Un dato presente non basta: la sua POSIZIONE nella struttura deve
escluderlo da chi legge solo «cosa c'è in questa stanza».

**`cerca(indice, "lampadario")`** → due candidati (`light.lampadario`,
dispositivo omonimo), nessuno dei due porta il campo `nascosta` — confermato
anche per una `light.lampadario` nascosta e trovata: `cerca` non dichiarava
affatto questo fatto.

Il «dopo» non si è potuto misurare in produzione (l'add-on gira ancora sul
codice vecchio finché non si rilascia): verificato con i test, sulla stessa
casa reale riprodotta come fixture (vedi sotto).

---

## Cosa ho cambiato

**`hiris/app/casa/anagrafe.py::gerarchia()`** — stessa forma delle
disabilitate: una terza chiave parallela, `entita_nascoste`, per ogni area
vera. Un'entità nascosta E disabilitata insieme resta fra le disabilitate
(non duplica il fatto in due chiavi) — stessa precedenza che `nucleo.py`
applicava già al proprio conteggio (`nascosta and not disabilitata`, riga
~1411). Effetto collaterale voluto: `nucleo._righe_casa` legge lo stesso
`area["entita"]`, quindi «La casa» smette anche lei di contare le nascoste
nei conteggi per dominio, allineandosi a «Notevole adesso» che le escludeva
già (vedi «Decisione sui conteggi» sotto).

**`hiris/app/casa/domande.py`**
- `_guarda_area`: le nascoste NON entrano più in `entita` (a differenza
  delle disabilitate, che restano dentro, marcate `disabilitata: true` —
  scelta consapevole, vedi sotto). Escono in `entita_nascoste`, presente
  solo quando non è vuota.
- `_guarda_dispositivo`: stessa forma. Non passa da `gerarchia()` (legge
  `casa["entita"]` grezzo, filtrato per `dispositivo_id`), quindi la
  partizione nascoste/non-nascoste è replicata qui con la stessa
  precedenza (nascosta e non disabilitata).
- `_guarda_entita` (il dettaglio di UNA entità sola): **invariato**. Non
  c'è un elenco da cui separarla — hai chiesto esplicitamente proprio lei —
  e continua a portare `nascosta: true` come campo, come già faceva.
- `cerca()`: i candidati di tipo `entita` guadagnano `nascosta: true`
  quando è vero (mai `nascosta: false`, per non aggiungere rumore a ogni
  candidato di una casa da 1226 entità). **Nessuna esclusione**: cercare
  «lampadario» deve continuare a trovare le lampade nascoste — escluderle
  vorrebbe dire rispondere «non esiste» di una cosa che c'è, la frase che
  questo prodotto non deve mai dire con sicurezza.
- Estratta `_righe_entita()`: il ciclo che arricchisce un elenco grezzo di
  entità (usato tre volte identico dentro `_guarda_area` prima di questa
  fetta — normali, disabilitate, e ora nascoste) diventa una funzione sola.
  Pulizia dovuta alla fetta, non un obiettivo a sé: la stessa
  duplicazione, lasciata, avrebbe generato una quarta copia.

**`hiris/app/casa/strumenti.py`** — `CERCA_TOOL_DEF` e `GUARDA_TOOL_DEF`
guadagnano la regola nuova nel testo che il modello legge davvero: che le
liste di `guarda` non contengono le nascoste (e dove trovarle se servono),
e che un candidato di `cerca` marcato nascosto non va proposto di sua
iniziativa ma nemmeno negato se la domanda lo riguarda. Con accenti veri,
per istruzione esplicita — unico punto del file che li usa, il resto dei
commenti resta nella disciplina «senza accenti» del progetto.

**`hiris/app/static/config/albero-route.js`** — non richiesto esplicitamente
dal compito, ma necessario per non rompere un consumatore diretto di
`gerarchia()` che esisteva già: la pagina di configurazione «Albero della
casa» (`GET /api/casa` → `gerarchia()`, senza passare da `guarda()`) legge
`area.entita`/`area.entita_disabilitate` per mostrare all'utente «cosa
HIRIS crede di sapere della stanza», con la regola esplicita (già nel suo
stesso docstring) di non far sparire niente. Senza questo aggiornamento, le
quattro luci nascoste sarebbero silenziosamente sparite anche da QUESTA
pagina di audit — non solo dal conteggio della chat, dove è voluto — senza
alcuna sezione che le rendesse conto, la stessa forma di silenzio non
dichiarato che il progetto vieta altrove. Ho aggiunto una sezione «Entità
nascoste», mirror di quella già esistente per le disabilitate, e il
conteggio nel sommario dell'area.

---

## Decisione sui conteggi (la parte che mi è stata chiesta di motivare)

**Le nascoste NON entrano nei conteggi**, né nella chiave `entita` di
`gerarchia()` (che alimenta anche `nucleo._righe_casa`, «La casa» del
digesto) né in nessun totale. Ho scelto la STESSA esclusione strutturale
delle disabilitate a livello di `gerarchia()`, ma con una differenza
deliberata su come `domande.guarda()` le espone al modello:

- le **disabilitate** restano dentro `entita`, marcate `disabilitata: true`
  — un impianto che esiste e non funziona è un fatto utile su una stanza
  («questa luce c'è ma non risponde»), e mischiarlo alla lista non rischia
  di far raccontare al modello qualcosa che l'utente non voleva sentire;
- le **nascoste** escono dalla lista che conta, in una chiave a parte
  (`entita_nascoste`) — perché la misura in produzione ha dimostrato che
  **marcare senza separare non basta**: il campo `nascosta` c'era già su
  ognuna delle quattro luci, ed è uscito lo stesso nella risposta che ha
  generato l'incidente. È la prova diretta che «il modello legge il dato e
  si ricorda di ignorarlo» è un piano che fallisce nel turno lungo; una
  struttura che non gliele mette davanti agli occhi nella lista principale
  no.

**Effetto collaterale sul digesto (`nucleo._righe_casa`, «La casa»):**
prima di questa fetta, «Notevole adesso» già escludeva le nascoste
(`if e.get("nascosta"): continue`, esplicito da tempo) ma «La casa» — che
legge `area["entita"]` dallo stesso albero — le contava ancora nei totali
per dominio. Le due sezioni si contraddicevano fra loro su una casa con
entità nascoste: una diceva «qui non conto le nascoste», l'altra le
contava senza dirlo. Spostare l'esclusione dentro `gerarchia()` (che
alimenta entrambe) chiude anche questa incoerenza, senza che fosse lo scopo
dichiarato del compito — l'ho scelto perché lasciare `gerarchia()` a metà
(nuova chiave per `domande.py`, vecchio comportamento per `nucleo.py`)
avrebbe prodotto la stessa forma di difetto che questa fetta chiude altrove:
due porte, due risposte sullo stesso fatto. Verificato con un test dedicato
(`test_le_entita_nascoste_non_si_contano_nemmeno_in_la_casa`).

**Cosa NON ho toccato:** il conteggio esplicito delle nascoste che il
digesto già scrive come avviso a parte («N entità nascoste in Home
Assistant: non entrano in "Notevole adesso" ... ma esistono e `guarda` le
riporta se gliele chiedi», `nucleo.py` righe ~1411-1419) legge
`casa.get("entita")` grezzo, non l'albero di `gerarchia()`: non serviva
cambiarlo, e la sua promessa («guarda le riporta se gliele chiedi») resta
vera con la nuova chiave `entita_nascoste` esattamente come lo era prima con
il campo `nascosta` inline.

---

## Test

**Rosso prima, verificato per intero.** Ho scritto tutti i test nuovi,
poi (`git stash` sui soli file di implementazione) confermato che 10 dei
15 falliscono contro il codice pre-fix — i restanti 5 verificano invarianti
che valgono anche prima (la precedenza disabilitata-su-nascosta a livello
`domande.py`, l'assenza di rumore quando non c'è niente da nascondere, la
raggiungibilità di un'entità singola), quindi non potevano essere rossi per
costruzione: sono comunque lock di regressione, non prove del difetto.

**Prova per mutazione**, su ognuno dei punti che contavano davvero:
- precedenza disabilitata-su-nascosta invertita in `gerarchia()` → due test
  (area via `domande.guarda`, e diretto su `anagrafe.gerarchia`) falliscono;
- stessa precedenza rimossa in `_guarda_dispositivo` (guardia locale,
  indipendente da `gerarchia()`) → il test dedicato al dispositivo fallisce,
  quello dell'area no (isolamento corretto: sono due implementazioni
  separate per una scelta esplicita — `_guarda_dispositivo` non passa da
  `gerarchia()`);
- guardia «solo quando non è vuota» tolta da `_guarda_area` → il test
  «senza nascoste non porta la chiave» fallisce;
- `cerca()` mutato per marcare `nascosta` su OGNI candidato invece che solo
  su chi lo è → il test dedicato fallisce;
- pagina di configurazione: sezione «Entità nascoste» e conteggio nel
  sommario rimossi (`git stash`) → il test JS dedicato fallisce sull'unica
  asserzione che dipende dal codice tolto.

**Il caso vero, non uno inventato più semplice.** La fixture usata nei test
nuovi di `test_domande.py` (`_casa_sala_da_pranzo`) riproduce esattamente i
sette dati misurati in produzione: sette luci, quattro nascoste (tre LIFX
+ «lampadario fake»), sei senza nome dichiarato con `nome_dedotto`, più un
pulsante visibile sullo stesso dispositivo delle lampade nascoste (per
esercitare la partizione di `_guarda_dispositivo` quando non tutto il
dispositivo è nascosto).

**Suite intera Python: 2574 passed, 1 skipped, 0 failed** (base 2559
passed, 1 skipped — la differenza sono i 15 test nuovi). Due test
pre-esistenti aggiornati perché la FORMA del prodotto è cambiata
deliberatamente, non per un difetto:
- `test_albero_verificabile.py::test_gerarchia_resta_pura_e_non_sa_niente_del_confronto`
  — asseriva l'insieme ESATTO delle chiavi di un'area; aggiornato con
  `entita_nascoste`.
- `test_da_quando.py::test_ogni_punto_di_guarda_che_emette_uno_stato_emette_anche_l_istante`
  — contava le occorrenze testuali di `"stato": stato.get(` nel sorgente
  (erano quattro); l'estrazione di `_righe_entita()` le ha portate a tre,
  perché due delle quattro liste che prima duplicavano lo stesso codice ora
  condividono una funzione sola — la protezione vera (che ogni occorrenza
  porti `da_quando` nelle righe vicine) resta intatta e continua a passare
  sulle tre occorrenze rimaste, che coprono oggi PIÙ punti logici di prima
  (`_righe_entita` serve area-visibili, area-disabilitate, area-nascoste E
  dispositivo-nascoste).

**Suite JS: 243 passed, 0 failed** (14 in `albero-route.test.mjs`, uno
nuovo). Nessun altro consumatore frontend di `gerarchia()`/`guarda()`
trovato (`dashboard.js` legge solo `casa.conteggi`, mai `casa.piani`).

---

## Dubbi per il coordinatore

- **La pagina di configurazione non era nel compito.** L'ho toccata perché
  senza aggiornarla la mia stessa modifica a `gerarchia()` avrebbe fatto
  sparire in silenzio le entità nascoste anche da una pagina che esiste
  apposta per non far sparire niente — mi è parso un rischio da non
  lasciare aperto, non un'estensione di scope decisa da me sul prodotto
  visibile in chat. Se il proprietario preferisce un trattamento diverso
  per quella pagina (per esempio nessuna sezione dedicata, solo il
  conteggio), è una modifica piccola da qui.
- **`_guarda_dispositivo` non condivide la funzione `gerarchia()`** per la
  partizione nascoste/disabilitate: ha sempre letto `casa["entita"]` grezzo
  (non l'albero), quindi ho replicato la stessa precedenza lì a mano invece
  di forzare un passaggio da `gerarchia()` che avrebbe cambiato anche il
  modo in cui risolve le disabilitate — fuori dallo scope di questa fetta.
  Le due implementazioni della stessa regola (nascosta-e-non-disabilitata)
  sono vicine nel file e commentate a vicenda, ma restano due copie: se un
  giorno la regola cambia, vanno cambiate in due punti.
- **Non ho tradotto in italiano i valori dentro `entita_nascoste`** oltre a
  quanto `_arricchisci_entita` già fa per ogni entità (stato_leggibile,
  classe, ecc.): stessa forma di ogni altra entità di `guarda`, nessuna
  differenza di trattamento voluta lì.
