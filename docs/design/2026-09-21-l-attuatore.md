# L'attuatore — il terzo attore, e cosa vuol dire «creare le soluzioni»

`spec · 21/09/2026 · il terzo attore del cervello (25/08/2026)`

Nasce da un rifiuto. Il 20/09 il ponte «Fanne una proposta» della pagina dell'osservatore (§5 di
`2026-09-18-la-pagina-dell-osservatore.md`) è stato bocciato dal proprietario su **tutte e quattro**
le obiezioni possibili: *mi sposta dalla pagina · devo fare io il lavoro · è finta, non c'è
l'attuatore · la proposta rischia di essere sbagliata*. Le prime due chiedevano di costruire di
più, le altre due di non costruire affatto — e avevano ragione insieme, perché la cosa che le
soddisfa tutte e quattro è **l'attuatore vero**, non un ponte.

Ogni decisione qui sotto è sua, presa il 20 e il 21/09 una domanda alla volta; ogni numero è
misurato sulla casa vera in quei giorni. Dove un numero non è misurato, lo si dice.

---

## §0 · Le decisioni, e chi le ha prese

| # | Domanda | Decisione del proprietario |
|---|---|---|
| 1 | Che mestiere fa | **Tutti e tre**: indaga (sola lettura), ripara HIRIS, propone |
| 2 | «Crea le soluzioni» vuol dire costruire? | **No**: molte cose non sono oggetti di HA. **Segnala cosa andrebbe fatto e perché**, e tu decidi |
| 3 | Gli esiti di una proposta | **Tre**: crea · rifiuta · **«sì, l'ho applicata, ma fuori da HA»** |
| 4 | Dove vivono le proposte | **In «Proposte», tutte insieme.** La differenza è un campo: chi la applica |
| 5 | Quando propone | **Da solo, dopo l'analista**, una volta al giorno |
| 6 | Riparare una ricetta rotta | **Da solo, e lo dice.** È lo stesso atto che il giro notturno fa già |
| 7 | Dopo un rifiuto | Chiude e resta visibile; **torna solo se cambia la prova**, mai a tempo |
| 8 | «Non così» | **«Rifalla» apre un testo** con le richieste di modifica e ripete il turno, **senza limiti** |
| 9 | Come si costruisce | **Un quarto turno**, gemello dell'analista |

---

## §1 · Le misure (20-21/09/2026, casa vera)

1. **Le otto osservazioni che l'analista ha davvero scritto** (15 e 16/09), lette una per una:
   **indagare o verificare 5**, **riparare HIRIS stesso 3**, **cambiare come si comporta la casa
   1**, **costruire un'automazione 0**.
2. L'unica della terza categoria — *«spostare i consumi più flessibili nelle ore di produzione
   solare»* — **non è costruibile**: non ha un innesco né un gesto, è un consiglio a una persona.
3. `workshop.propose` vuole un'**intenzione strutturata** (`gesto`, `dominio`, `innesco`, `azioni`,
   `stati`, `parametri`) e `consiglia()` la rifiuta se non ha abbastanza struttura. L'analista
   scrive **prosa**. Fra le due c'è un salto che **solo un turno di modello** può fare.
4. **L'analista gira ogni 60 minuti e scrive una analisi al giorno**; la domanda pesa ~35.000 token
   (misurati il 15/09 su venti giorni e 146 serie).
5. **Il campo `cosa_cambierebbe` ha un lettore solo** in tutta l'applicazione: la scheda «Cosa
   fare», che lo stampa.
6. Le proposte costruibili vivono nella tabella `costruzioni`, le cui colonne —
   `gesto`, `dominio`, `chiave`, `prima_json`, `dopo_json`, `anteprima` — **parlano tutte di un
   oggetto che HIRIS sa scrivere**, con sopra la macchina dell'officina (scadenza, `claim`,
   applicazione, ripristino).
7. Costo stimato del turno dell'attuatore: **10-20.000 token**, cioè ~0,10 € al giorno sulla catena
   attuale e zero sul Piano Max. **Stimato, non misurato**: si misura alla prima settimana.

---

## §2 · Il mestiere: tre gesti, in quest'ordine

**1. Indaga** — sola lettura. Cinque osservazioni su otto sono domande: *«il sensore era fermo?»*,
*«a che ore è avvenuto il prelievo?»*. Prima di proporre qualunque cosa, l'attuatore va a vedere —
statistiche orarie, storia, stato del dispositivo — e **scrive cosa ha trovato accanto
all'osservazione**. Spesso l'indagine *è* la risposta: «il sensore ha ripreso da solo il 16, niente
da fare». In quel caso chiude lì e non propone niente. **Una coda che non si riempie è il primo
obiettivo di questa fetta**, non un effetto collaterale.

**2. Ripara** — scrive **solo** nel sapere di HIRIS. Quando una misura non si calcola più perché la
ricetta non regge contro il registro delle operazioni, riscrive la ricetta e **lo dichiara**. È
l'unico caso in cui l'attuatore scrive senza chiedere, e la ragione è che **è lo stesso atto che il
giro notturno delle ricette fa già senza chiedere a nessuno**: non è un potere nuovo, è lo stesso
potere applicato a una riga che esiste già ed è rotta.

> **Il difetto che questo gesto chiude**: `devices_to_ask` salta i dispositivi che una ricetta ce
> l'hanno già. Una ricetta che esiste ma **non si esegue più** non viene quindi mai riscritta da
> nessuno — ed è esattamente ciò di cui l'analista si lamenta da due giorni. È la stessa forma che
> il prodotto ha già pagato tre volte: *la porta salta chi ha già una risposta, anche quando la
> risposta è rotta*.

**3. Propone** — non scrive niente. Decide se la cosa è un oggetto che Home Assistant sa tenere —
allora passa da `costruisci`, e la proposta porta l'anteprima e il diff — oppure è una cosa che fa
una persona, e allora è un **consiglio** con il suo perché. In entrambi i casi la proposta finisce
in «Proposte».

**Quando non ce la fa, lo dice**: «ho guardato e non so cosa proporre per questa» resta scritto
accanto all'osservazione. Il silenzio sarebbe indistinguibile da «non l'ho guardata».

---

## §3 · La proposta: due forme, tre esiti, e il «Rifalla»

**Due forme, due archivi, una pagina.** «Un posto solo dove si decide» è una promessa sulla
**pagina**, non sulla tabella:

- le proposte **costruibili** continuano a nascere da `costruisci` e a vivere in `costruzioni`, con
  anteprima e diff; cambia solo `origine`, che dirà `attuatore` invece del turno di chat;
- le proposte **da fare a mano** vivono in un archivio gemello e piccolo: *cosa fare*, *perché*
  (l'osservazione che l'ha generata, col suo numero e la sua base), *chi la applica*, *stato*,
  *impronta*, e il filo dei giri;
- «Proposte» le mostra **in un elenco solo**, con l'etichetta che dice chi la applica — «la scrivo
  io in HA» / «la fai tu» — e il pallino somma le due code.

Infilare una frase in prosa dentro una tabella di diff vorrebbe dire riempire cinque colonne di
finti valori e avere una riga su cui metà della macchina dell'officina non si applica: è il
doppione per forma che le fondamenta vietano.

**I tre esiti**, per entrambe le forme:

| esito | cosa fa | chi lo può dare |
|---|---|---|
| **Crea** | scrive in HA, come oggi: turno separato, conferma esplicita, anteprima davanti | solo le costruibili |
| **Rifiuta** | chiude la proposta; resta visibile in «Cosa fare» col segno e la data | entrambe |
| **Fatto fuori da HA** | chiude la proposta **come applicata**, dichiarando che non è stato HIRIS a farlo e che non può verificarlo nell'oggetto | entrambe |

Il terzo esito non è una sfumatura: per il **verificatore**, che un domani dovrà misurare se
l'obiettivo si è mosso, «l'ho fatto io» e «lo hai fatto tu» sono due prove diverse.

**«Rifalla»**. Accanto a «Rifiuta» c'è un secondo comando: apre **un campo di testo** con le tue
richieste di modifica, e il turno si rifà con quelle davanti. **Non ha limiti**: la si può far
rifare finché va bene. Ogni giro resta attaccato alla proposta — la forma scartata e ciò che hai
chiesto — così il modello vede il filo intero e non ripropone quello che hai appena rifiutato.

> È una conversazione, ma **su quella proposta e su niente altro**, dentro la pagina: che è poi
> l'unica cosa che il ponte alla chat sapeva fare, fatta bene.

---

## §4 · Il ritmo, e perché non serve un tetto

**Una volta al giorno, sull'analisi completa.** L'attuatore si aggancia allo stesso battito orario
dell'analista e non fa niente finché non trova (a) l'analisi di oggi scritta e (b) nessuna
attuazione già fatta **per quell'analisi**. La disciplina che l'analista applica a sé — *un giorno
ha un'analisi sola* — diventa **un'analisi ha un'attuazione sola**. Parte quando l'analisi è
finita, qualunque ora sia, e mai due volte.

Il riferimento è **l'analisi**, non il giorno, e non è un dettaglio: dalla 3.55.0 un'analisi si
rifà quando cambia il suo fondamento, e un'attuazione fatta sull'analisi vecchia dev'essere
rifatta su quella nuova.

**Niente tetto di proposte.** Se l'attuatore gira una volta al giorno su un'analisi intera, il
tetto è già il numero di osservazioni di quel giorno (tre o cinque, misurate). Un tetto in più
sarebbe una manopola che risolve un problema che il ritmo ha già risolto.

**L'anti-ripetizione.** Ogni proposta porta **l'impronta dell'osservazione** che l'ha generata —
soggetto, misura, chiave, innesco — e **la forza della prova**: base di giorni, scostamento,
innesco. L'attuatore salta un'osservazione la cui impronta ha già una proposta in qualunque stato,
**a meno che la prova non sia cambiata**: una base che passa da 3 giorni a 19, uno scostamento che
peggiora, un innesco diverso.

> È la stessa regola che il sapere usa già per i rifiuti delle ricette: *«un rifiuto non è
> definitivo: vale finché vale il registro contro cui è stato deciso»*. Non scade a tempo, perché il
> tempo non è una prova: riproporre la stessa cosa con gli stessi dati è insistere, non informare.

**Conseguenza dichiarata**: se rifiuti e la prova non cambia, HIRIS non te lo ripropone. Il problema
resta comunque visibile in «Cosa fare», perché l'analista continua a scriverlo finché dura.

---

## §5 · Gli strumenti, e il confine

Tre cerchi concentrici, e il confine è dichiarato dal 25/08: *«l'attuatore non guadagna un canale di
scrittura suo»*.

| gesto | cosa può toccare |
|---|---|
| **indagare** | **sola lettura**: statistiche orarie, storia, stato, `view`, `search`. Niente scritture, da nessuna parte |
| **riparare** | **solo il sapere di HIRIS** (le ricette), che il modello già scrive da solo ogni notte |
| **proporre** | `costruisci`, che **non scrive in casa**: compone, valida contro questa casa, e restituisce un'anteprima con un `proposta_id` |

**La scrittura in casa resta dov'è oggi**: un turno diverso da quello che ha proposto, con il sì del
proprietario, dalla pagina «Proposte». L'attuatore è il punto in cui il cervello tocca la casa, ed è
**l'unico**: la sicurezza del cervello si concentra su un attore solo invece di essere spalmata su
quattro.

---

## §6 · Dove vive

- `mind/actuator.py` — il codice che **decide senza modello**: quali osservazioni saltare
  (impronta e prova), come si legge un'indagine, come si distingue il costruibile dal consiglio.
- `mind/actuator_turn.py` — la forma del turno: la domanda, la risposta ammessa, la validazione.
  Gemello di `analyst_turn.py`, e come quello **rifiuta una risposta storta invece di correggerla**.
- `server.py` — `actuator_round(app)`, agganciato al battito orario, con la regola *un'analisi, una
  attuazione*.
- L'archivio gemello delle proposte da fare a mano: tabella nuova in `osservazioni.db`, accanto
  all'analisi — non in `costruzioni`, per la ragione della §3.
- Le rotte: la lettura unificata per la pagina «Proposte», i tre esiti, e il «Rifalla».

---

## §7 · Le prove, e i tre cancelli

La parte che **decide** è codice puro: si prova in Python, senza modello, come `apply_analysis`. Il
**giro** si prova per intero, come `analyst_round` dalla 3.55.0 — *un'analisi, un'attuazione*; una
analisi rifatta, un'attuazione nuova; nessuna analisi, nessun turno. Il **filo del «Rifalla»** si
prova sul contenuto: il giro secondo vede la forma scartata e la richiesta, e non ripropone la
stessa cosa.

Tre cancelli, perché sono le cose che si rompono in silenzio:

1. **L'attuatore non scrive mai in casa.** Una prova che fallisce se compare una chiamata di
   scrittura verso Home Assistant che non passi da `costruisci`. Senza un cancello, il confine del
   25/08 resta una promessa.
2. **Le due forme non si mescolano negli archivi**: una proposta non costruibile non entra in
   `costruzioni`, e una costruibile non entra nell'archivio gemello. Si leggono insieme, si
   archiviano separate.
3. **Un'analisi non genera due attuazioni**, nemmeno se il giro parte due volte nello stesso minuto.

E i cancelli che il progetto già pretende: nessun testo del server scritto come HTML, il fuoco
governato, nessuna emoji, e le prove che asseriscono la **proprietà** e non il fatto.

---

## §8 · Come si misura se funziona — e quando si spegne

I numeri della prima settimana, **dichiarati adesso e non scelti dopo**:

1. **quante osservazioni chiuse dall'indagine senza proporre niente** — deve essere alto: cinque su
   otto sono domande, e rispondere è meglio che proporre;
2. **proposte fatte / accettate / rifiutate / fatte fuori da HA** — il tasso di accettazione è la
   misura vera della qualità, e la quarta voce dice quanto del valore sta fuori dalla portata di HA;
3. **quante volte «Rifalla», e quanti giri prima del sì** — se servono tre giri a proposta, il
   difetto è nel prompt;
4. **quante ricette riparate da sole, e se le misure sono tornate a calcolarsi** — questa è
   oggettiva: la copertura torna o non torna;
5. **il costo in token al giorno**, contro i 10-20.000 stimati.

**Il criterio di fallimento, scritto prima di cominciare**: se dopo **due settimane** il rifiuto è
l'esito dominante, l'attuatore **si spegne** — non si ritocca il prompt all'infinito. Un attore che
propone cose che non vuoi è rumore, e il rumore sano è quello che seppellisce la rotta.

---

## §9 · Fuori perimetro, dichiarato

- **Il verificatore**, quarto attore: misura se l'obiettivo si è mosso e sorveglia gli altri tre. È
  una fetta sua, e il terzo esito di questa (§3) esiste perché lui possa distinguere le prove.
- **L'attuatore che sceglie da sé dove intervenire**, senza passare dall'analista.
- **Cambiare l'analista perché produca intenzioni costruibili**: oggi scrive prosa, e va bene —
  zero osservazioni su otto sono costruibili, e forzarlo a scrivere intenzioni gli farebbe
  inventare struttura che non ha.
- **La voce**, che è la seconda metà dello sprint dei comandi.

---

## §10 · L'ordine

1. L'archivio gemello delle proposte, e la lettura unificata per la pagina.
2. I tre esiti in «Proposte», e il «Rifalla» col suo filo.
3. `mind/actuator.py`: la parte che decide, senza modello, con le sue prove.
4. Il turno e il giro, con la regola *un'analisi, un'attuazione*.
5. I tre cancelli della §7.
6. La verifica dal vivo sulla casa, e la prima settimana di misure della §8.
