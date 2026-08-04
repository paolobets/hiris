# Come nasce un agente

**Data:** 4 agosto 2026
**Stato:** approvato — Atto 1 del Refactor 2.0, primo pezzo.
**Dipende da:** `2026-08-04-scope-hiris.md` (il contratto). Questo documento ne è l'applicazione:
dice *come* si costruisce l'unico esecutore del sistema.

---

## 0. Il problema, in una riga

Nello scope abbiamo tolto il semaforo per-azione e spostato l'autorizzazione **sull'agente**: si
approva un perimetro, non ogni gesto. Questo sposta tutto il peso su un unico momento — quello in
cui dici sì — e crea un rischio nuovo:

> **Approvare un perimetro deve essere una decisione, non un timbro.**

Se la schermata finale dice *«questo agente potrà toccare 40 entità e 12 servizi»*, premi sì senza
aver capito niente, e in quell'istante l'approvazione ha smesso di proteggerti. **La leggibilità del
perimetro non è un dettaglio d'interfaccia: dopo l'eliminazione del semaforo è l'unica difesa che
resta.** Tutto il resto di questo documento discende da qui.

---

## 1. Il principio della frase leggibile

> **Un perimetro che non sta in una frase è un errore di progettazione, non una scelta dell'utente.**

Se il sistema non sa dire *cosa farà* l'agente e *cosa potrà toccare* in qualcosa che si legge in
cinque secondi, **non deve chiedere di approvarlo: deve fare un'altra domanda.**

È questo che dà uno scopo alle domande di chiarimento. Non sono cortesia conversazionale: sono lo
strumento con cui il sistema stringe il perimetro fino a renderlo approvabile.

- *«Tieni d'occhio la casa»* → genera domande.
- *«Avvisami se la porta d'ingresso resta aperta la sera»* → non ne genera.

---

## 2. La nascita, in cinque momenti

### ① Parli
Scrivi l'obiettivo in chat, a parole tue. Nessun modulo, nessun passo numerato.

### ② Il sistema chiede ciò che manca
Domande **mirate e poche**, ciascuna con uno scopo dichiarabile: restringere il perimetro. Se una
domanda non stringe niente, non va fatta.

### ③ Il sistema costruisce
Il modello **propone** obiettivo, permessi, entità, servizi, freni e innesco — perché è lui che
capisce l'intento. Il codice **restringe** (§4).

### ④ Ti mostra e chiede «attivo?»
L'agente **nasce disattivato**. Sempre. Nessuna eccezione, nemmeno per gli agenti che il Brain
propone.

> *(Oggi è il contrario: il wizard crea l'entità **già attiva**. È una delle cose che il refactor
> ribalta.)*

### ⑤ Poi vive
Dentro il perimetro agisce. Fuori, si ferma (§6).

---

## 3. Anatomia del perimetro

Il perimetro è **tre cose insieme**, decise nello stesso momento.

| | Cosa fissa |
|---|---|
| **Permessi** | quali entità, quali servizi, quali fonti di conoscenza |
| **Freni** | ogni quanto può svegliarsi, quante volte al giorno, quanti token, entro quanto tempo conclude |
| **Stato** | attivo · sospeso · revocato |

**Perché i freni stanno qui.** Un'automazione che scatta cinquecento volte è gratis; **un agente che
si sveglia cinquecento volte costa cinquecento chiamate a un modello.** Il controllo di frequenza e
di spesa appartiene a chi spende.

**Perché lo stato è parte del contratto.** Ciò che si approva si deve poter disattivare. Non è un
extra: è metà del significato di «approvare».

---

## 4. Chi scrive il perimetro

> **Il modello propone. Il codice restringe.**

Il modello compone il perimetro perché capisce l'intento. Ma il modello ha letto nomi di entità,
attributi e — domani — documenti: **testo che ha scritto qualcun altro.** Non può essere l'ultima
parola su cosa gli è permesso toccare.

I massimali sono **applicati dal codice, non chiesti al modello**, e non sono aggirabili:

1. **Nessun dominio irreversibile concesso in automatico.** Serrature, allarmi, tapparelle, sirene,
   cancelli: il modello non li può inserire nel perimetro. Ci entrano solo se **l'utente li nomina
   esplicitamente** nella conversazione — e comunque a runtime chiedono (§6).
2. **Nessun jolly di dominio.** Il perimetro elenca **entità**, mai `light.*`. Un'area è ammessa,
   ma viene **risolta nel suo elenco di entità al momento dell'approvazione**: approvi ciò che vedi,
   non un'etichetta.
3. **Oltre l'ampiezza leggibile, il sistema chiede invece di proporre.** Quando il perimetro cresce
   oltre ciò che sta in una frase, non lo si allarga: si torna a ② e si fa una domanda.
4. **Solo servizi che le entità del perimetro supportano davvero.** Il perimetro dei servizi è
   derivato, non dichiarato.
5. **I freni hanno tetti che il modello non può alzare.** Può proporre valori più stretti dei
   massimali, mai più larghi.

L'invariante che ne esce, e che va difesa nei test:

> **Nessun percorso permette a un output di modello di ampliare il proprio perimetro.**
> Ampliare è sempre e solo un atto umano, e vale come una nuova approvazione.

---

## 5. I sensi dell'agente

La Legge II impone che l'agente sia autoconsistente: **ha i propri sensi**, non si appoggia a
un'automazione di Home Assistant che qualcuno potrebbe cancellare.

Ma i sensi di un agente non sono quelli di un'automazione, e la ragione è la Legge III:

> Un'automazione ha bisogno di un innesco **preciso**, perché dopo l'innesco non c'è nessuno che
> ragioni. **Un agente ragiona per definizione** — quindi gli basta essere svegliato *quando vale la
> pena guardare*. **La precisione sta nel giudizio, non nel trigger.**

### Le tre forme di risveglio

| Forma | Cos'è |
|---|---|
| **Interesse** | un insieme di entità o un'area: l'agente si sveglia quando lì qualcosa si muove |
| **Cadenza** | un orario o un intervallo |
| **Invocazione** | tu dalla chat, oppure il Brain |

L'invocazione dal Brain e quella dalla chat **oggi non esistono**: vanno costruite. Sono le due che
rendono l'impianto quello descritto nello scope.

### Il filtro deterministico viene prima

L'innesco grossolano ha un costo: un'area viva può svegliare un agente decine di volte l'ora. Prima
che il modello venga interpellato deve passare uno **strato deterministico e gratuito**:

1. il cambiamento è reale (non un ri-annuncio dello stesso stato);
2. il cooldown dell'agente è scaduto;
3. il tetto giornaliero non è esaurito.

Solo dopo si spende. **I freni non sono un limite alla potenza: sono ciò che rende sostenibile
l'innesco grossolano**, ed è per questo che vivono nel perimetro.

---

## 6. Il confine, a runtime

### Fuori perimetro: si ferma e riporta

L'agente che vuole qualcosa che non gli hai dato **non chiede**. Si ferma, e lascia un resoconto:
cosa voleva fare, perché, e cosa gli mancava.

Non chiede per una ragione precisa: **fuori banda non hai il contesto per decidere.** Una notifica
che ti raggiunge mentre sei al ristorante e ti domanda se un agente possa toccare una cosa in più è
una domanda a cui non puoi rispondere bene. Ampliare il perimetro è **una nuova approvazione**,
fatta quando hai davanti l'intero quadro.

Il resoconto è quindi una **superficie di prodotto**, non un log: è da lì che si riapre la
conversazione che ha creato l'agente.

### Dentro perimetro: l'irreversibilità chiede comunque

Un'azione **non annullabile** — serratura, allarme, cancello, garage — chiede conferma anche a un
agente approvato.

Non perché non ti fidi dell'agente: **perché non ti fidi del testo che l'agente ha letto oggi.** Una
luce accesa per sbaglio si spegne; una porta aperta alle tre di notte no. È l'unico criterio che
merita di sopravvivere all'esecuzione, ed è **binario**: reversibile o no.

> **Una sola domanda sopravvive a runtime, e solo dove il danno è irreparabile.**
> Il semaforo a quattro colori, i tre percorsi di conferma paralleli e il gate per-azione sono tutti
> assorbiti da questo più il perimetro.

---

## 7. Cosa questo sostituisce

| Sostituito | Con cosa |
|---|---|
| il wizard a quattro passi (tipo indovinato **contando le parole**, nessuna validazione, entità **creata già attiva**) | la nascita conversazionale, che finisce disattivata |
| il semaforo a quattro colori per dominio | i permessi del perimetro |
| i tre percorsi di conferma paralleli (chat / gateway / agente) | il resoconto fuori perimetro + la domanda sull'irreversibile |
| il cooldown e il tetto giornaliero nel motore di sorveglianza | i freni dentro il perimetro |
| la modalità regola | non esiste: se non ragiona è un'automazione HA |

---

## 8. Cosa questo documento non decide

- **Che aspetto ha la schermata di approvazione.** Il principio è fissato (una frase leggibile); la
  forma no.
- **I valori numerici** dei massimali e dei freni predefiniti.
- **Come si amplia un perimetro** in pratica: si riapre la conversazione originale, si modifica
  l'agente, o si crea una revisione da approvare?
- **Cosa sa il Brain** — il pezzo successivo dell'Atto 1, e il presupposto perché il Brain sappia
  proporre un agente sensato.
- **La migrazione** degli Agentbot esistenti.
