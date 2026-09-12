# Le domande del proprietario

`raccolte l'11/09/2026 · sono il cancello del registro delle operazioni (spec 2026-09-10, §6)`

**Perché questo documento esiste.** La spec del 10/09 dice che il set delle operazioni *«non si
dimensiona a preventivo: si chiude con un test — è abbastanza ricco quando le quattro domande vere
del proprietario e il resoconto giornaliero si esprimono tutti senza aggiungerne una»*, e aggiunge
*«provato su quelle domande, sono quindici»*. **Quelle domande non erano scritte da nessuna
parte**: cercate in `docs/design/`, nei piani e nel backlog, non esistevano. Il criterio che decide
se il registro è completo viveva solo in una conversazione perduta — lo stesso modo in cui il
04/09/2026 è andata persa la lista degli argomenti dello sprint, ed è la ragione per cui esiste
`docs/BACKLOG.md`.

Sono state richieste di nuovo e **queste sono le parole del proprietario**, l'11/09/2026. Non sono
una parafrasi: contano perché sono sue.

---

## Le domande

Sono **sette**, non quattro: la spec ne prometteva quattro, e alla richiesta il
proprietario ne ha date sette. Il numero della spec era una memoria, non un
conteggio -- e le due in piu' sono quelle che reggono l'operazione altrimenti
orfana (vedi la 5 e la 6).

**1 · Il riscaldamento, l'effetto e le persone**

> *«Quando si accende il riscaldamento e porta la casa in temperatura, poi qualcuno è in casa o
> meno?»*

È l'esempio fondativo del documento del cervello (25/08/2026) posto dal lato che conta: non
*«quando parte»*, ma *«quando parte, e serviva a qualcuno?»*. Contiene tre cose diverse — un
episodio, il suo effetto misurato, e la presenza di una persona nello stesso intervallo — e la
risposta sta nello **scarto** fra le tre.

**2 · L'energia, e la stagione**

> *«La mia produzione energetica copre bene casa mia, o si può ottimizzare gestendo la diversa
> produzione per mese?»*

Due domande in una: *quanto copre* (un rapporto su un periodo) e *come cambia col mese* (lo stesso
rapporto confrontato fra periodi diversi). La seconda metà è quella che il resoconto giornaliero
esiste per rendere possibile: trenta giorni di misure in un prompt.

**3 · L'irrigazione e il prato**

> *«L'irrigazione sta gestendo bene il fabbisogno del prato per il periodo in cui siamo?»*

Qui la casa non contiene la risposta: il **fabbisogno del prato** non è un dato di Home Assistant.
È una domanda che mette insieme ciò che si misura (quanto si è irrigato, quando, con che tempo
faceva) e un sapere che viene da fuori. Serve a tenere onesto il confine fra le due cose.

**4 · Il comfort, quando conta**

> *«A livello di comfort la casa è sana quando c'è qualcuno in casa?»*

La stessa forma della prima: una grandezza (temperatura, umidità, anidride carbonica) **ristretta
ai periodi in cui una persona c'era**. Una media di ventiquattr'ore risponderebbe a un'altra
domanda.

**4-bis · Le automazioni**

> *«Le automazioni presenti rispondono alle esigenze della casa?»*

Posta dal proprietario come alternativa alla quarta, con un «oppure». Si tiene, perché chiede una cosa che nessuna
delle altre chiede: non *com'è andata la casa*, ma **se ciò che è stato costruito serve ancora**.

**5 · Le ore d'irrigazione, su una stagione**

> *«Dammi il totale delle ore irrigate tra maggio e settembre.»*

**6 · La CO2 di un piano**

> *«Dammi il livello di CO2 di tutto il piano terra.»*

Queste due sono arrivate dopo, e non sono un di piu': sono le uniche che
chiedono **piu' cose insieme** -- tutte le zone d'irrigazione, tutti i sensori
di un piano. Senza di loro `somma_entita`/`raggruppa_per` sarebbe l'unica
operazione del registro che nessuno ha chiesto, e per la regola che la spec si
e' data (*«le sei nuove nascono ciascuna da una domanda posta davvero, non da un
preventivo»*) andrebbe tolta.

La sesta introduce anche il **raggruppamento per la casa**: «tutto il piano
terra» non e' un elenco di entita', e' un ramo dell'anagrafe -- piano, area,
dispositivo. Il registro deve saperlo attraversare, o la domanda va riscritta a
mano ogni volta che si sposta un sensore.

**7 · I problemi**

> *«Dammi tutti i problemi emersi in casa.»*

Questa e' di un'altra specie, e serve proprio per quello. Non chiede di
**calcolare** niente: chiede di **elencare** cio' che e' successo -- le
condizioni di sistema aperte, le integrazioni in errore, le automazioni rotte,
che l'osservatore gia' registra come episodi di genere `guasto`.

E' la domanda che dice **dove finisce il mestiere del registro**. La risposta
non e' un'operazione nuova: e' la cronaca del resoconto giornaliero (spec §9),
letta un giorno alla volta. Al registro serve solo `episodio` -- aperto quando,
chiuso quando, o ancora aperto -- e `tempo_in_stato` per dire da quanto dura.

Tenerla fra le domande del cancello e' deliberato: una prova che dimostri che
**non tutte le domande si rispondono con un calcolo** vale quanto una che
dimostri il contrario. Il rischio opposto -- inventare un'operazione per ogni
domanda posta -- e' il modo in cui un registro «chiuso» smette di esserlo.

---

## Cosa queste domande chiedono al registro

Analisi preliminare, da verificare **scrivendo la prova** (è il cancello della Fetta 3): qui si
elenca cosa serve, non si conclude che basti.

| domanda | cosa deve saper fare il registro |
|---|---|
| 1 | `episodio` (il riscaldamento acceso) · `misure_durante` (la temperatura mentre scaldava) · `quando_succede` (a che ora capita di solito) · `quante_volte` · **la presenza come periodo**, non come misura |
| 2 | `somma_periodo` · `quota` (l'autosufficienza) · `differenza_fra` · `per_ora` (il profilo) · `confronto_periodi` (mese contro mese) · `tendenza` |
| 3 | `episodio` · `tempo_in_stato` · `quante_volte` · `somma_periodo` (i litri, dove si misurano) · `correlazione` (con pioggia e temperatura) · `confronto_periodi` |
| 4 | `media_min_max` **ristretta ai periodi di presenza** |
| 4-bis | `quante_volte` · `quando_succede` · l'effetto, cioè di nuovo `misure_durante` |
| 5 | `tempo_in_stato` · **`somma_entita`** (tutte le zone insieme) · un periodo di **cinque mesi** |
| 6 | **`raggruppa_per`** su un ramo dell'anagrafe (il piano), ridotto con **`media_entita`** |
| 7 | `episodio` · `tempo_in_stato` — **e nient'altro**: la risposta e' la cronaca, non un calcolo |

### La quinta domanda chiede una cosa che HIRIS oggi non può dare, ed è preziosa

*«Fra maggio e settembre»* sono cinque mesi. Il grezzo dell'osservatore dura
**22 giorni**, e l'irrigazione è un `binary_sensor`/`switch`: Home Assistant non
ne tiene statistiche, quindi oltre la sua finestra di **7,5 giorni** (misurata
l'11/09/2026) non resta nulla. La risposta onesta a quella domanda, oggi, è
**«non calcolabile, e perché»** — ed è esattamente il ramo di rifiuto che la
spec §6 prescrive:

> `rifiuta se   l'entità non ha statistiche · il periodo è fuori dalla memoria disponibile`

Per questo la quinta domanda è la più utile di tutte al cancello: è l'unica che
prova che il registro sappia **dire di no con una ragione**, invece di
restituire il totale delle tre settimane che ha e farlo passare per cinque
mesi. Quel difetto ha già un precedente pagato in questo progetto
(`_difference` con un punto solo che restituiva `0.0`).

### Il candidato sedicesimo, e perché forse non lo è

Tre domande su sette chiedono la stessa cosa: **restringere un calcolo ai periodi in cui qualcosa
era vero** — «mentre il riscaldamento era acceso», «mentre qualcuno era in casa». Sembra
un'operazione nuova, e probabilmente **non lo è**: se `episodio` restituisce delle finestre, e ogni
operazione accetta come periodo **un elenco di finestre** invece di un solo intervallo, la
restrizione è composizione, non un mattone in più.

Questa è una proprietà del disegno da decidere **prima** di scrivere le quindici, e la prova del
cancello è ciò che la mette alla prova.


## Cosa è cambiato scrivendo le operazioni (12/09/2026)

Questa tabella è stata scritta **prima** del registro, e tre righe non hanno retto alla prova:

1. **La domanda 1 ha fatto nascere un'operazione che non era prevista**, `dentro`: restringere una
   *misura* a un periodo è composizione (`misure_durante`), ma incrociare due *periodi* — «quanto ha
   scaldato mentre qualcuno era in casa» — è una forma che nessun'altra operazione aveva.

2. **La domanda 6 ha fatto nascere `media_entita`.** La prima stesura riduceva ogni gruppo con
   `somma_entita`, e il piano terra rispondeva **900 ppm** sommando 400 e 500: la somma di due
   concentrazioni non è una concentrazione. La riga qui sopra diceva `media_min_max`, che però
   lavora su una serie nel tempo, non su più entità nello stesso istante. Trovato dalla revisione
   indipendente del 12/09/2026.

3. **Come si riduce un gruppo non ha un valore per difetto.** Sommare e mediare sono due domande
   diverse, e nessuna delle due è «quella normale»: `raggruppa_per` pretende che chi chiama lo dica.

Le operazioni sono **diciotto**, non quindici: il numero non era un preventivo da rispettare, era
una previsione, e il cancello delle domande l'ha corretta in tutte e due le direzioni — due
operazioni salvate dall'essere cancellate come orfane (domande 5 e 6), due nate da domande che non
si scrivevano senza.
