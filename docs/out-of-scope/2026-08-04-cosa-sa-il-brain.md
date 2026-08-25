# Cosa sa il Brain

> ## 🗄 Annotazione — 25 agosto 2026: superato, spostato fuori scope
>
> Questo documento è un verbale del 4 agosto e non viene riscritto — si annota. È stato superato
> due volte: `docs/design/2026-08-05-la-conoscenza-di-hiris.md` ne ha ripreso il ritratto e la
> mappa semantica; `docs/design/2026-08-25-il-cervello-da-capo.md` dichiara in testa di superare
> e annullare **ogni documento sul Brain precedente**, questo compreso.
>
> **Cosa ne sopravvive**, ripreso come vincolante dal documento del 25 agosto
> (§ «La trappola, misurata e non opinata»):
>
> - la **misura** del §3: il RAG vettoriale del prodotto vecchio era *«un pedaggio pagato in
>   scrittura su dati che si leggono con una `WHERE` su una data»*;
> - la **regola** che ne discende: *«la memoria prende la forma del dato che contiene»*.
>
> Il resto — ritratto, delta, viste — descrive un Brain che non esiste e non è la base del
> prossimo.

**Data:** 4 agosto 2026
**Stato:** approvato — Atto 1 del Refactor 2.0, secondo pezzo.
**Dipende da:** `docs/design/2026-08-04-scope-hiris.md` (il contratto) ·
`docs/design/2026-08-04-come-nasce-un-agente.md`.

Lo scope dice che la conoscenza è **la fondazione**, e che è la parte messa peggio. Questo documento
dice che forma deve avere.

---

## 0. Il fatto da cui si parte

> **Oggi il Brain si sveglia ogni trenta minuti e ogni volta ricomincia da zero.**

Il ragionatore proattivo riceve *una entità alla volta* più cinque righe di fotografia — presenza,
temperatura esterna, meteo, allarme, salute di Home Assistant. Non riceve la mappa della casa, non
riceve lo storico, non ricorda cosa aveva visto mezz'ora prima. La mappa semantica delle entità
esiste ed è l'unico blocco di conoscenza pieno di fabbrica: **la riceve solo la chat.**

Questo non è «poco contesto». È che **un cervello senza continuità non impara: ricomincia.**
Imparare significa avere memoria di com'era e confrontarla con com'è. Senza, ogni risveglio è
amnesia, e nessuna quantità di ragionamento la compensa.

Lo strato di conoscenza non serve a scrivere prompt migliori. **Serve a trasformare l'osservazione
ripetuta in apprendimento** — ed è il presupposto perché il Brain sappia proporre un agente sensato
invece di proporre l'ovvio a chiunque.

---

## 1. Il ritratto

> **HIRIS mantiene un ritratto della casa: vivo, compatto, aggiornato di continuo — non ricostruito
> a ogni risveglio.**

Quattro contenuti.

| Contenuto | Cos'è |
|---|---|
| **Struttura** | aree, entità, che cosa sono e a cosa servono |
| **Stato notevole** | cosa è acceso, aperto, anomalo **adesso** — non tutto lo stato: quello che merita di essere detto |
| **Ciò che ha imparato** | abitudini, soglie apprese, preferenze dichiarate, scadenze, spese, correlazioni |
| **Cosa è cambiato** | il delta dall'ultimo risveglio |

### Perché il delta è il campo che conta

Un Brain che riceve *«com'è la casa»* ragiona. Un Brain che riceve *«com'è la casa, e queste sette
cose sono diverse da stamattina»* **si accorge**.

Il delta fa due lavori insieme: è il substrato dell'apprendimento — non c'è apprendimento senza un
prima e un dopo — ed è il **controllo del costo**, perché permette di spendere il ragionamento sul
cambiamento invece che sul totale. Una casa di trecento entità che ne muove sette non ha bisogno di
essere riletta per intero.

---

## 2. Un solo ritratto, viste diverse

Il ritratto è **ciò che HIRIS sa**. Non ha senso costruirne uno per il Brain, uno per la chat e uno
per gli agenti: sarebbe di nuovo un motore con tre nomi.

| Chi | Cosa vede |
|---|---|
| **Il Brain** | il ritratto intero — è il cervello della casa |
| **Un agente** | la fetta del proprio perimetro |
| **La chat** | secondo il Chatbot con cui stai parlando |

Questo chiude un'ambiguità che il prodotto si trascinava: oggi il perimetro di un agente governa in
modo confuso **lettura e azione insieme**, al punto che restringerlo alle entità azionabili
nasconderebbe i sensori di temperatura. Ora è esplicito e sono due cose distinte:

> **I permessi dicono cosa un agente può toccare. Le fonti di conoscenza dicono cosa può sapere.**

Entrambi stanno nel perimetro, entrambi si approvano insieme, ma non sono lo stesso elenco.

---

## 3. La memoria ha la forma del dato

### Cosa faceva davvero il RAG

Il motore vettoriale nasce ad aprile per **un** compito: la memoria di conversazione. *«Ricordati che
preferisco 21 gradi»* detto in chat, ritrovato dopo per somiglianza di significato. Testo libero,
senza struttura, recuperato per senso: il caso d'uso legittimo del RAG.

Poi la *memoria unificata* ha fuso tutto in un archivio solo, e oggi lo stesso motore porta **quattro
mestieri**:

| Contenuto | Come viene recuperato **davvero** | Il RAG serve? |
|---|---|---|
| memoria di conversazione | per similarità, primi 5 nel prompt | sì, ma sono poche decine di righe per Chatbot |
| **second brain** — scadenze, spese, obblighi, fatti | **SQL**: `due_date <= X ORDER BY due_date`, `SUM(amount) GROUP BY categoria` | **no** |
| **documenti** — OCR a pezzi | per similarità | **sì** — è l'unico corpus vero |
| **insight** — medie settimanali, ore di attività, variazioni % | per similarità | **no**, sono numeri derivati |

### La prova

La funzione che alimenta il resoconto delle 08:00 legge le scadenze così:

```sql
WHERE kind='obligation' AND status='approved'
  AND due_date IS NOT NULL AND due_date <= ?
ORDER BY due_date ASC
```

…e poi, sulla riga letta, **scarta esplicitamente l'embedding**.

La parte più preziosa del second brain — quella che ti dice che la bolletta scade fra tre giorni —
**non ha mai usato la ricerca vettoriale.** Ma per *scrivere* una scadenza l'embedder è obbligatorio:
senza, la scrittura viene rifiutata.

> **Si paga un pedaggio vettoriale in scrittura su dati che si leggono con una `WHERE` su una data.**
> Con la configurazione di fabbrica l'embedder manca, quindi le scadenze non si possono creare, e il
> resoconto delle 08:00 è vuoto per sempre.

### La regola

> **La memoria prende la forma del dato che contiene.**
>
> Una scadenza è una data. Una spesa è un numero con una categoria. Un'abitudine è una soglia. Si
> interrogano con una query, non con un coseno — e vivono **dentro il ritratto**, sempre presenti.
>
> **Nessun dato strutturato paga un pedaggio vettoriale per essere scritto o letto.**

Non è una preferenza architetturale: **tre mestieri su quattro non sono mai stati problemi da RAG**,
e ci sono finiti perché l'archivio esisteva già.

> ### ⚠️ Rettifica — 4 agosto 2026, dopo la fetta 2a
>
> Questo paragrafo diceva: *«il motore vettoriale resta vivo in un posto solo: i documenti»*, e da
> quello discendeva che la ricerca per somiglianza sarebbe stata **rimossa** dagli item nella fetta
> 2b. **Decisione dell'utente rovesciata prima di costruire la 2b: il vettore resta anche sugli
> item.**
>
> Chi configura un fornitore di embedding continua ad avere il richiamo per significato sui ricordi;
> chi non lo configura — cioè ogni installazione di fabbrica — ha i più recenti. La fetta 2a ha già
> reso questa una **regola sola dentro lo store**, non due configurazioni: *la ricerca confronta i
> significati quando può; quando non può, dà i più recenti*.
>
> **Il prezzo, dichiarato:** due comportamenti da mantenere e da testare, per sempre. È il costo che
> la scelta precedente evitava. Resta invece pienamente valido tutto il resto del paragrafo — nessun
> dato strutturato paga un pedaggio vettoriale, e le scadenze si leggono per data.
>
> Cosa questo cambia per le fette successive: la **2b** non è più la rimozione del vettore dagli
> item, ma **far affiorare la memoria da sola** anche senza vettore (vedi
> `2026-08-04-piano-memoria-fetta2b.md`).

### Conseguenze

- Il second brain e gli insight diventano **campi del ritratto**, interrogabili.
- La memoria di conversazione, essendo poche decine di righe per Chatbot, **entra in contesto senza
  cercare**.
- Il resoconto quotidiano e le scadenze **funzionano appena installi**, senza chiavi di terze parti.
- Gli embedding restano necessari **solo** se accendi l'importazione documentale.
- Muore un intero percorso rotto: le righe scritte con vettore nullo, irrecuperabili per costruzione
  perché la ricerca le esclude.

---

## 4. Cosa questo documento non decide

- **Come si mantiene aggiornato il ritratto** — cadenza, aggiornamento incrementale, calcolo del
  delta, cosa succede se una fonte non risponde. Sono scelte che maturano costruendo: vanno nel
  piano.
- **Quanto può essere grande** e come si tronca quando la casa è più grande del budget.
- **Quali fatti impara il Brain da solo** e quali gli vanno detti.
- **La migrazione** dei dati esistenti in `knowledge.db`, comprese le righe già scritte senza
  vettore.
- **Se il ritratto sostituisca anche la mappa semantica attuale** o la incorpori.

---

## Con questo l'Atto 1 è chiuso

I tre pezzi del COME: `come-nasce-un-agente` (la nascita e il perimetro), questo (la conoscenza), e
i sensi dell'agente — descritti nel primo. Il passo successivo non è più una specifica: è il **piano
di costruzione**, e il primo cantiere è questo, perché tutto il resto vi poggia sopra.
