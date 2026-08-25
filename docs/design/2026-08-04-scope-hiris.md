# HIRIS — Scope

**Data:** 4 agosto 2026
**Stato:** approvato — definisce il **COSA**. Il *come* e *con quali strumenti* seguiranno in documenti propri.
**Vale su:** branch `feat/coerenza`, HEAD `feb6e1e`.

---

## 0. Perché esiste questo documento

HIRIS è cresciuto per accumulo. Ogni sprint ha aggiunto un motore, una pagina, un vocabolario;
nessuno ha mai tolto. Il risultato è un sistema in cui la stessa cosa ha tre nomi, la stessa
promessa ha tre percorsi diversi, e le protezioni dichiarate esistono nel codice ma sono spente,
inerti o non configurabili dall'interfaccia.

Il documento fondativo precedente — `PRODUCT.md` — descrive HIRIS come *«un pannello di
configurazione delle entità AI»*, con la frase esplicita *«niente dashboard di stato della casa»*.
Il codice ha votato diversamente: ogni sprint degli ultimi mesi è andato verso l'assistente e verso
il cervello proattivo, nessuno verso la sandbox e gli eval che `PRODUCT.md` chiama «il successo
misurabile». **Il documento sbagliato era quello, non il codice.** Questo lo sostituisce.

Questo documento decide **cosa** HIRIS deve fare. Non descrive l'esistente: è il metro con cui
l'esistente verrà giudicato, riga per riga.

---

## 1. Che cos'è HIRIS

> **HIRIS è l'intelligenza della casa.**
>
> Sa tutto ciò che della casa si può sapere — Home Assistant, i documenti, le fonti che verranno —
> impara da ciò che vede, e da quella conoscenza **costruisce le cose che servono a far funzionare
> la casa**: automazioni, script, scene, plance quando basta il determinismo; **agenti** quando
> serve giudizio.

Tre conseguenze immediate di questa frase:

- HIRIS **non è un cruscotto**. Non mostra lo stato della casa: quello lo fa Home Assistant, meglio.
- HIRIS **non è un playground di LLM**. Non si costruiscono bot per il gusto di costruirli: si
  costruisce ciò che serve alla casa.
- HIRIS **non è un sostituto di Home Assistant**. Ne è il livello di giudizio. HA resta il motore.

---

## 2. Le tre leggi

Sono criteri di ammissione, non linee guida. Una funzione che ne viola una non entra — o esce.

### Legge I — Sussidiarietà

> **Se Home Assistant lo sa fare, si crea un oggetto di Home Assistant.
> L'agente esiste solo dove serve giudizio.**

Ogni funzione di HIRIS deve rispondere alla domanda *«perché questo non è un'automazione HA?»*.
Se non c'è una risposta, la funzione è debito.

La distinzione è quella data dall'autore del prodotto e vale come definizione:
**l'agente valuta informazioni e contesti; l'automazione non lo sa fare.**

### Legge II — Autoconsistenza

> **Automazione e agente sono oggetti distinti e completi.
> Nessuno dei due dipende dall'altro.**

Non esiste l'automazione che innesca un agente, né l'agente che si appoggia a un'automazione. Una
dipendenza fra i due sistemi è fragile per costruzione: basta cancellare l'oggetto in HA perché
l'oggetto in HIRIS diventi un morto che nessuno sveglia, in silenzio.

Corollario: **l'agente ha i propri sensi.** Osserva la casa da sé, ha il proprio orologio, la
propria memoria, la propria azione, i propri limiti.

### Legge III — Ogni agente ragiona

> **Se non ragiona, non è un agente: è un'automazione, e deve nascere in Home Assistant.**

Non esistono agenti deterministici. Un innesco che porta a un'azione dichiarata senza alcuna
valutazione è, per definizione, un'automazione — e va creata dove le automazioni vivono.

---

## 3. I tre strati e la porta

### ① Conoscenza — la fondazione

HIRIS mantiene **una rappresentazione viva della casa**, alimentata da più fonti:

- **Home Assistant** — entità, aree, stati, storico, eventi
- **Il sistema documentale** — documenti, scadenze, obblighi
- **Le fonti future** — l'architettura deve accoglierne di nuove senza riprogettazione

Non è una cache: è **ciò che HIRIS sa**, e cresce. Impara le abitudini, ricorda ciò che gli viene
detto, correla ciò che vede.

> **Questo strato è oggi il più debole del sistema, ed è il primo cantiere.** Il Brain non riceve
> mai la mappa della casa; la ricerca semantica è inerte per configurazione predefinita; la
> knowledge base non si riempie mai. Vedi l'Appendice A.

### ② Brain — il cervello

> ## 🗄 Annotazione — 25 agosto 2026: questa sezione è superata
>
> Il proprietario ha deciso che il cervello va **rifatto da capo**:
> `docs/design/2026-08-25-il-cervello-da-capo.md` dichiara in testa di superare e annullare questa
> sezione ②, comprese le sue due «regole dure», che non si danno più per acquisite. Il resto dello
> scope — le tre leggi, gli strati ① e ③, la porta — resta il contratto. La sezione qui sotto
> non viene riscritta: è il verbale del 4 agosto.

Legge **tutta** la conoscenza, ragiona, **impara e aggiorna la propria memoria da solo**.

Il Brain **apre questioni**: propone l'oggetto giusto per il problema che ha visto — un'automazione,
uno script, una scena, una plancia, o un agente. L'utente risponde.

Due regole dure:

- **Il Brain non tocca la casa senza un sì.** Ciò che vuole cambiare fuori da sé passa da una
  proposta.
- **Ma il Brain impara liberamente.** Aggiornare la propria memoria, le proprie correlazioni, ciò
  che ha capito della casa **non richiede approvazione**: è il suo mestiere. Il cancello è sul
  *toccare*, non sul *pensare*.

### ③ Agenti — gli esecutori

**Gli unici esecutori intelligenti**, e autosufficienti: sensi propri, giudizio proprio, azione
propria, limiti propri.

Nascono in due modi:

| Origine | Come |
|---|---|
| **L'utente** | un **comando testuale** — si descrive a parole ciò che si vuole, e il sistema costruisce l'agente: deriva permessi, entità, servizi, limiti |
| **Il Brain** | una **proposta**, perché ha visto qualcosa nella conoscenza |

In **entrambi** i casi, finita la costruzione, il sistema chiede: **attivo?**
Nulla si attiva senza un sì esplicito.

### La porta — la Chat

Non è un prodotto separato: è **come si parla al Brain**. Si interroga, si comanda, si **costruisce**
insieme — agenti e oggetti di Home Assistant — e si approva.

Un'unica conversazione, con un'unica intelligenza che conosce la casa.

---

## 4. Gli oggetti che HIRIS costruisce

| Se serve… | HIRIS crea | Vive in |
|---|---|---|
| reagire a una condizione, in modo deterministico | **automazione HA** | Home Assistant |
| una sequenza di azioni | **script HA** | Home Assistant |
| uno stato della casa da richiamare | **scena HA** | Home Assistant |
| mostrare qualcosa | **plancia HA** | Home Assistant |
| **valutare informazioni e contesto prima di decidere** | **agente** | HIRIS |

La regola di scelta è la Legge I: *standard finché basta, agente quando serve giudizio.*

---

## 5. Il perimetro — ciò che si approva

Non si approva un'azione: si approva **un perimetro**, una volta sola, nel momento in cui si ha il
contesto per deciderlo — cioè quando l'agente nasce.

Il perimetro è **tre cose insieme**:

| | Cosa fissa |
|---|---|
| **Permessi** | quali entità, quali servizi, quali fonti di conoscenza l'agente può toccare |
| **Freni** | ogni quanto può partire, quante volte al giorno, quanti token può spendere, entro quanto tempo deve concludere |
| **Stato** | attivo · sospeso · revocato |

**Perché i freni stanno qui e non altrove.** Un'automazione che scatta cinquecento volte è gratis;
**un agente che parte cinquecento volte costa cinquecento chiamate a un modello.** Il controllo di
frequenza e di spesa appartiene a chi spende — l'agente — non al motore che lo sveglia.

**Perché lo stato è parte del contratto.** Ciò che si approva si deve poter disattivare. Non è un
extra dell'interfaccia: è metà del significato di «approvare».

---

## 6. Cosa esce di scena

| Esce | Perché | Dove va |
|---|---|---|
| **La modalità regola** (agente senza ragionamento) | viola la Legge III | diventa un'automazione HA |
| **I rilevatori integrati come esecutori** (porta aperta, frigo caldo, consumo, batteria) | sono automazioni HA di sei righe: violano la Legge I | HIRIS li **propone** come automazioni |
| **Il semaforo per-azione** (quattro colori × N domini × tre percorsi di conferma) | chiede la domanda giusta nel momento sbagliato, a un utente senza contesto | **assorbito** nei permessi del perimetro |
| **Il vocabolario «Sentinella» e «Agentbot»** | tre nomi per una cosa sola | resta **agente** |
| **Il workbench come prodotto** (sandbox, eval, telemetria per-entità di `PRODUCT.md`) | mai costruito in mesi di sviluppo; non è ciò che serve alla casa | la configurazione torna a essere *impostazioni* |

Ciò che **non** esce, e va invece **spostato**: i freni (cooldown, tetto giornaliero, budget di
token, scadenza). Sono l'unica capacità reale che Home Assistant non ha nativamente. Migrano dal
motore di sorveglianza **dentro il perimetro dell'agente**.

---

## 7. Il criterio di ammissione

Ogni funzione esistente, e ogni funzione futura, si giudica con quattro domande in quest'ordine.
La prima risposta negativa la condanna.

1. **Serve alla casa?** — se serve solo a configurare HIRIS, non è il prodotto: è un'impostazione.
2. **Perché non è un oggetto di Home Assistant?** *(Legge I)*
3. **È autoconsistente, o dipende da un oggetto che vive altrove?** *(Legge II)*
4. **A quale strato appartiene** — conoscenza, Brain, agente, chat — **e uno solo?**

Una funzione che non sa dire a quale strato appartiene è la definizione stessa del debito che questo
documento chiude.

---

## 8. Cosa questo documento NON decide

Deliberatamente fuori scope qui, da definire nel **COME**:

- **Come nasce un agente da una frase** — quali domande fa il sistema, come deriva permessi ed
  entità, come si presenta il perimetro da approvare, cosa si vede prima di dire sì.
- **Cosa sa il Brain, esattamente** — quali blocchi di conoscenza riceve, quando, con quali limiti
  di dimensione e di riservatezza.
- **Come l'agente osserva** — quale superficie di innesco, quali condizioni sa esprimere, se e come
  compone più segnali.
- **Come si migra l'esistente** — cosa si riscrive, cosa si spegne, cosa si cancella, in quale
  ordine, e cosa succede alle configurazioni già in uso.
- **Cosa resta della sicurezza a runtime** — se, oltre al perimetro, sopravviva una domanda
  sull'irreversibilità delle azioni. *(Questione aperta: la superficie di iniezione non si
  restringe con questo scope, si allarga — ogni fonte di conoscenza nuova è testo che il modello
  legge.)*

---

## Appendice A — I reperti che hanno motivato questo scope

Verificati sul codice il 3-4 agosto 2026. Non sono un elenco di bug: sono le prove che il problema
era di scope e non di implementazione.

**Lo strato di conoscenza è quasi tutto inerte di fabbrica.**

- Il **Brain non riceve mai la mappa della casa**. Il ragionatore proattivo vede *una entità alla
  volta* più cinque righe di fotografia (presenza, temperatura esterna, meteo, allarme, salute HA).
  Il cervello che dovrebbe conoscere tutta la casa è la parte del sistema che ne sa meno.
- La **mappa semantica delle entità** è l'unico blocco di conoscenza pieno di fabbrica — e la riceve
  **solo la chat**.
- Il fornitore di **embedding è vuoto di default**: si costruisce un motore fittizio che restituisce
  vettori vuoti. Il blocco «Memoria rilevante» sparisce **in silenzio**, e poiché quel motore è
  comunque un oggetto, i tool di memoria **restano esposti al modello e falliscono a ogni chiamata**.
- Il **digest notturno scrive righe con embedding nullo**, che la ricerca esclude per costruzione:
  scrive conoscenza irrecuperabile.
- **Storico**: cattura opt-in, spenta. **Documentale**: spento.

**Le protezioni dichiarate non sono attivabili.**

- Su un'installazione appena fatta **il semaforo è spento su tutto**: ogni azione viene negata,
  e il sistema non lo dice.
- La **conferma umana della chat non è configurabile da nessuna interfaccia**: pretende una mappa
  utente→canale privato che nessuna superficie scrive. Il modello dice «guarda il telefono» e sul
  telefono non arriva nulla.

**Gli inneschi che servono alla visione non esistono; quelli che esistono duplicano HA.**

- **Il Brain non può far partire un agente.** Il codice lo dichiara in un commento; non è
  implementato.
- **Non esiste un «fallo adesso»** dalla chat, né webhook, né MQTT in ingresso (dichiarato
  *outbound-only*), né innesco da fonte documentale.
- Le uniche due sorgenti d'innesco reali sono **Home Assistant e l'orologio** — entrambe cose che
  Home Assistant fa nativamente meglio.
- L'unica capacità che HA non ha nativamente è il **controllo di frequenza e di spesa**: cooldown
  persistente, tetto giornaliero, budget di token, scadenza.

**Il prodotto ha tre nomi per una cosa sola.** Brain, Sentinella e Agentbot non sono tre macchine:
condividono un unico gancio LLM, un unico esecutore, un unico gate, un unico scheduler. La
sovrapposizione non era nel motore — era nel linguaggio del prodotto.

---

## Riferimenti

- `docs/design/2026-08-03-analisi-funzionale.md` — comportamento reale del codice, con riferimenti
  puntuali. Descrive l'esistente; questo documento decide il voluto.
- `docs/design/2026-08-03-revisione-tecnica.md`
- `PRODUCT.md` — **superato da questo documento** per quanto riguarda scopo, utenti e criteri di
  successo. Restano validi i capitoli su identità visiva e accessibilità.
