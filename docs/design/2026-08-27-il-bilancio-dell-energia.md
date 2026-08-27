# Il bilancio dell'energia — la prima forma che non è un episodio

**27 agosto 2026** · Fetta del cervello, dopo «l'osservatore» (3.13.1)

---

## 0. Il fatto misurato che apre tutto

La prima notte di memoria di HIRIS ha prodotto **24 episodi**. **Undici vengono dallo stesso
apparecchio** — l'inverter con accumulo — e ognuno dice una frazione priva di senso da sola:

```
potenza_prodotta            da 20 a 20
energia_importata_oggi      da 0,21 a 0,22
energia_esportata_oggi      da 10,57 a 10,58
energia_autoconsumata_oggi  da 6,0 a 5,99      ← un contatore che sale, sceso
potenza_esportata           da 10 a 0
…
```

Undici «cose compiute» che messe in fila **non raccontano niente**. Il fatto vero era **uno**:
com'è andata ieri l'energia di questa casa.

E c'è un secondo fatto, misurato lo stesso giorno: **Home Assistant ha già la curva della giornata**
— statistiche **orarie**, 24 punti, per tutti e otto i sensori di energia dell'impianto, conservate
**oltre i nostri 22 giorni**.

```
04:00  0,00 kWh     10:00   9,71
07:00  1,17         13:00  19,79  →  16:00  23,63
```

## 1. La domanda giusta, e il metro

> **Non «cosa possiamo salvare», ma «quale frase utile deve permettere».**
> Se un dato non serve a nessuna frase che HIRIS potrà mai dire, non va salvato.

Per l'efficienza di una casa col fotovoltaico, le frasi plausibili sono di quattro tipi:

- «sposta la lavatrice all'una: in quella fascia immetti in rete»
- «il riscaldamento parte alle 15:30 e a quell'ora stai già prelevando»
- «la batteria finisce alle 22 e poi prelevi tutta la notte»
- «da tre giorni produci metà della media»

Tutte e quattro hanno bisogno delle stesse tre cose, e di nient'altro.

## 2. Cosa si salva, e con quale grana

| | Cosa | Perché serve |
|---|---|---|
| **Il bilancio** | sei totali del giorno: prodotta, autoconsumata, immessa, prelevata, caricata, scaricata | risponde a «com'è andata» |
| **La forma** | gli stessi valori **ora per ora** | è l'unica cosa che permette di dire **quando** spostare qualcosa |
| **I momenti** | prima e ultima ora di produzione; il picco e a che ora; quando la batteria ha finito di scaricare; quota di autoconsumo e di autosufficienza | è ciò su cui si ragiona, invece di rileggere la curva |

**Correzione della review (punto 1, 27/08/2026): sono SETTE, non sei.** La stesura originale escludeva
`consumo` come «ridondante con autoconsumo+prelievo» — un'assunzione, non un fatto misurato, e su
questa casa è falsa (§0 di questa correzione ha i numeri: `autoconsumata` esclude la batteria, quindi
autoconsumo+prelievo perde la scarica, oltre metà del consumo vero). Il consumo è un dato MISURATO che
l'integrazione porta già (`energia_consumata_oggi`): buttarlo via per dedurlo da una somma che non
torna produceva un numero falso ogni notte su `quota_autosufficienza`. Il consumo è il settimo totale,
letto e non derivato, e le quote si calcolano su quello — vedi `hiris/app/cervello/oggetti.py`,
`DIREZIONI_BILANCIO` e `_momenti_bilancio`.

**La grana è l'ora**, e per due ragioni che coincidono:

1. **è la grana delle decisioni** — il consiglio utile è «nel primo pomeriggio», non «alle 13:47»;
2. **è la grana che HA già calcola** — non la inventiamo, la leggiamo.

Ogni cambio sarebbero migliaia di punti che non permettono **nessuna frase in più**. Il solo totale
del giorno non permette nessuna delle quattro frasi. Fanno **~150 numeri al giorno, 2-3 KB**.

### Cosa NON si salva

- le letture istantanee come episodi a sé: la potenza è il **ritmo**, utile solo come curva;
- i contatori **totali di vita** (`totale_*`): il loro delta giornaliero è già nei `*_oggi`;
- una direzione **inventata**: se non si sa, il campo non c'è.

## 3. La forma: perché l'episodio è lo stampo sbagliato

Un **episodio** ha protagonista, inizio e fine: perfetto per «riscaldamento acceso 15:30 → 17:05».

**La produzione non accade dalle 6 alle 20: è una quantità con una forma.** Forzarla nello stampo
dell'episodio è precisamente ciò che ha prodotto gli undici frammenti.

> **È il GENERE a decidere la forma, e la forma decide chi è il protagonista.**

Non si sceglie fra dispositivo ed entità in astratto — la domanda era mal posta, e la risposta cambia
per genere:

| Genere | Forma | Protagonista |
|---|---|---|
| funzionamento | episodio | l'**entità** (il termostato acceso) |
| presenza | episodio | la **persona** — che dispositivo non è |
| guasto | condizione con durata | l'integrazione o il problema |
| **bilancio** (nuovo) | **quantità con una forma, un giorno** | il **dispositivo** (l'impianto) |

Le 15 entità dell'impianto non sono 15 protagonisti: sono **le dimensioni di un bilancio solo**.

## 4. La fonte: chi ha già questo dato meglio di noi?

**Ogni genere porta con sé anche la sua fonte**, e la domanda va fatta per ciascuno.

| | HA lo tiene? | Quindi |
|---|---|---|
| presenza | **tre giorni** | lo dobbiamo osservare noi — è il motivo per cui il cervello esiste |
| guasti | **no** | li dobbiamo osservare noi |
| **energia** | **sì, orario, oltre i nostri 22 giorni** | **lo leggiamo, non lo ricostruiamo** |

**Questo corregge una frase della spec dell'osservatore** (§9③), che dice che le statistiche di HA
non sostituiscono questa memoria: **vero per la presenza, falso per l'energia.**

E c'è una ragione in più, misurata: il nostro grezzo ha sbagliato l'azzeramento del contatore la
**prima notte** (`da 6,0 a 5,99` su un contatore che sale). **HA quel problema lo risolve già
correttamente** nel campo `sum` delle sue statistiche. Leggere è insieme più economico e **più
corretto**.

### La forma esatta, misurata il 27/08/2026

`recorder/statistics_during_period` con `period: "hour"`, `types: ["sum","state"]` →
per ogni `statistic_id`, **24 punti** con `start`, `end`, `state` (il valore a fine ora) e `sum` (il
cumulato che gestisce gli azzeramenti). Verificato sull'impianto vero.

## 5. Cosa cambia nel prodotto

1. **Nasce il genere `bilancio`**: un oggetto al giorno per dispositivo, costruito **leggendo le
   statistiche orarie di HA**, non aggregando il grezzo.
2. **Le entità che entrano in un bilancio smettono di produrre episodi propri.** Il bilancio le
   sostituisce: undici frammenti diventano un oggetto.
3. **Le direzioni** (`produzione`, `prelievo`, `immissione`, `carica`, `scarica`, `consumo`,
   `autoconsumo`) — già costruite, dichiarate dalla dashboard Energia o dedotte
   dall'integrazione — dicono **quale entità è quale dimensione** del bilancio.
4. **Il traffico di rete esce dall'energia.** `state_class: total_increasing` **da solo** non basta
   più: serve una classe di energia dichiarata. Misurato: `sensor.betarena_gb_inviati` — i gigabyte
   del router — era archiviato come energia. Non è restringere il pavimento: è **smettere di
   derivare una cosa che HA non dichiara**.
5. **I numeri si arrotondano.** Oggi la pagina mostra `+0.010000000000000009`.

## 6. Le domande lasciate aperte, con la loro ragione

- **L'energia deve restare nel pavimento?** Se HA la tiene meglio, osservarne ogni cambio aggiunge
  migliaia di righe grezze al giorno. Il grezzo però dà la correlazione **istantanea** con gli altri
  episodi («il termostato è partito mentre prelevavi»), che l'ora non dà. **Si tiene, e si decide
  con i numeri veri** dopo una settimana: quante righe al giorno costa, e se qualche ragionamento le
  ha davvero usate.
- **Le altre gambe** — presenza, comfort, dispersione, sicurezza, acqua — vanno passate **una per
  una** con le stesse tre domande: *quale frase utile deve permettere*, *con che grana*, *chi ha già
  quel dato*. Questa fetta fa **solo l'energia**, e stabilisce il metodo.
- **L'irrigazione** (32 entità, oggi **zero** osservate) e la gamba «acqua» restano fuori da qui:
  misurate, scritte, e da fare con lo stesso ragionamento.
