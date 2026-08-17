# Ciò che l'anagrafe sa e non dice

> Fetta B di «chiudere la conoscenza a 360°».
> Misurata con le **quattro fondamenta** di `CLAUDE.md`.

## Il difetto

Tre fatti che HIRIS legge da Home Assistant, scrive nel proprio archivio a ogni
ricostruzione, e poi **non fa uscire da nessuna porta**.

Non è codice morto: il dato c'è ed è giusto. È **conoscenza muta**, che è
peggio — costa la lettura e non rende niente, e chi guarda il database si
convince che HIRIS lo sappia dire.

È la fondamenta dell'**autonomia funzionale** letta al contrario: *se non
esiste un modo per chiederlo, non è conoscenza, è zavorra.*

## I tre

### 1. `piattaforma` — zero lettori

L'integrazione che fornisce l'entità: `hue`, `zwave_js`, `template`, `mqtt`.
Scritta a ogni ricostruzione, letta da nessuno.

«Questa luce è una Hue o un template?» è una domanda che si fa davvero — per
capire perché una cosa non risponde, o cosa le si può chiedere. Adesso `guarda`
su un'entità la dice.

### 2. `etichette` — la tassonomia dell'utente, muta

Le etichette sono **il significato più dichiarato che esista in quella casa**:
non dedotto, non comprato, scritto a mano dall'utente in Home Assistant.
«inverno», «da controllare», «piano di sotto».

HIRIS le leggeva, le salvava, le metteva perfino nell'albero di `gerarchia()` —
e mai in una risposta. Un'etichetta che non porta a niente costringe l'utente a
ripetere a parole ciò che aveva già dichiarato una volta.

Adesso escono da `guarda` (entità, area, dispositivo) **e** entrano nell'indice
di `cerca`: «le cose etichettate inverno» è una domanda che funziona.

Non diventano il *nome* di niente: entrano fra i termini che `trova()`
riconosce, e il nome resta quello che era. È la stessa disciplina di
`nome_dedotto` — dichiarato e dedotto restano due fatti diversi.

### 3. `deduci_unita` — una deduzione che non è mai scattata

Leggeva l'unità dal **registro**. Home Assistant riempie quel campo solo se
l'utente ha forzato l'unità a mano: misurato **NULL su 842 entità su 842**.

Quindi la funzione non ha mai dedotto niente in produzione — e non aveva modo
di dirlo. Adesso legge dallo **specchio dello stato**, che l'unità ce l'ha
davvero.

## Due regole che erano scritte due volte

Chiudere il terzo punto ne ha scoperti due di questi.

**«L'unità viva vince su quella del registro»** — perché HA converte solo alla
prima aggiunta del sensore — era scritta a mano in `domande._con_nome_dedotto`
e stava per esserlo di nuovo in `deduci_unita`. Due copie di una decisione che
nessuno tiene allineate: **la stessa forma di difetto** che ha reso la pagina
Modelli vera riga per riga e falsa nel complesso. Adesso è
`anagrafe.unita_effettiva`, in un posto solo.

**La lettura dello specchio** viveva solo dentro `casa/strumenti.py`. Chi stava
altrove — la correzione di un ricordo dalla pagina — o rileggeva la cache per
conto suo, o faceva a meno di ciò che ci sta dentro: la stessa domanda avrebbe
avuto **due risposte a seconda della porta**, l'unità dedotta in chat e non
dedotta dalla pagina. Adesso è `anagrafe.specchio_vivo`, e le due porte la
chiamano entrambe.

## Le quattro domande

- **Chi lo riceve può interpretarlo senza sapere altro?** Sì: `piattaforma` ed
  `etichette` sono parole complete, non codici da risolvere altrove.
- **Questo fatto vive già da qualche altra parte?** No — e le due *regole* che
  vivevano in due posti sono state riportate a uno.
- **Ha la stessa forma da tutte le porte?** Adesso sì: chat e pagina deducono
  l'unità dalla stessa fonte. Prima no.
- **Esiste un modo per chiederlo?** Adesso per tutti e tre. Prima per nessuno.

## Cosa NON è cambiato

Nessuna chiave compare a vuoto: `piattaforma` ed `etichette` appaiono solo
quando ci sono. `etichette: []` su ogni cosa sarebbe rumore in ogni risposta e
— peggio — indistinguibile da un registro delle etichette caduto. Stessa
disciplina di `unita`.
