# GLOSSARIO — come si chiamano le cose in HIRIS

Spec: `docs/design/2026-08-28-il-glossario.md`.

Questo documento non e' storia: e' la **regola**. Si consulta ogni volta che nasce un nome, e si
aggiorna quando nasce un concetto. Non porta una data di redazione perche' non e' la fotografia di
un giorno: e' vivo, e cambia quando cambia il codice.

**Stato di questo documento: l'elenco e' completo, nessuna colonna e' decisa.** Le colonne «che
cosa fa», «inglese» e «prova del lettore nuovo» sono lasciate vuote di proposito — le riempiono i
task successivi della stessa fetta. Una riga con la colonna vuota significa «non ancora deciso», non
«dimenticato».

## Come si legge

Il nome inglese non e' la traduzione della parola italiana: e' il nome di **cio' che la cosa fa**.
La colonna «che cosa fa» si scrivera', quando verra' riempita, **senza usare la parola italiana**,
perche' e' cosi' che si arrivera' al nome — non traducendo, rinominando.

Il criterio che separa i tre insiemi qui sotto e' **la natura della parola, non quanto e' usata**:
un concetto raro (`comprimari`) richiede tutto il giudizio che una parola frequente (`giorno`) non
richiede affatto.

## I concetti

Parole che il progetto ha **inventato**, o a cui ha dato un significato suo. Per spiegarle a
qualcuno bisogna raccontare come funziona HIRIS.

| italiano | che cosa fa | inglese | prova del lettore nuovo |
|---|---|---|---|
| anagrafe |  |  |  |
| archivio |  |  |  |
| ascolto |  |  |  |
| azione |  |  |  |
| caricatore |  |  |  |
| casa |  |  |  |
| catena |  |  |  |
| cervello |  |  |  |
| comportamento |  |  |  |
| comprimari |  |  |  |
| costruzione |  |  |  |
| cronaca |  |  |  |
| decisione |  |  |  |
| dispatcher |  |  |  |
| domande |  |  |  |
| esito |  |  |  |
| flusso |  |  |  |
| forme |  |  |  |
| gamba |  |  |  |
| grezzo |  |  |  |
| impostazioni |  |  |  |
| indice |  |  |  |
| instradamento |  |  |  |
| interpretazione |  |  |  |
| invocazione |  |  |  |
| lettura |  |  |  |
| memoria |  |  |  |
| mestiere |  |  |  |
| migrazione |  |  |  |
| notevole |  |  |  |
| nucleo |  |  |  |
| officina |  |  |  |
| oggetti |  |  |  |
| orologio |  |  |  |
| osservatore |  |  |  |
| osservazioni |  |  |  |
| pavimento |  |  |  |
| ponte |  |  |  |
| porta |  |  |  |
| promessa |  |  |  |
| registro |  |  |  |
| riconoscitore |  |  |  |
| rifiuto |  |  |  |
| ripiego |  |  |  |
| schedulatore |  |  |  |
| semaforo |  |  |  |
| servizi |  |  |  |
| spazio |  |  |  |
| stati |  |  |  |
| strumenti |  |  |  |
| tempo |  |  |  |
| turno |  |  |  |
| verdetto |  |  |  |
| verifica |  |  |  |
| versioni |  |  |  |
| vive |  |  |  |
| vocabolario |  |  |  |

> **`promessa`** e **`promesse`** (nei «Nomi degli strumenti», sotto) sono **due cose diverse**: la
> prima e' il concetto/modulo Python (il significato di «una promessa nel ponte»), la seconda e' la
> stringa che il modello legge come nome di uno strumento. Non e' un doppione mancato — sono
> deliberatamente due voci, con due grafie diverse perche' cosi' sono nel codice (singolare il
> concetto, plurale il nome dato al modello).

## Le parole ordinarie

Equivalenti diretti, che non perdono niente nella conversione. Nessun giudizio da fare, nessuna
prova del lettore nuovo: vanno in una tabella di conversione decisa una volta e applicata
meccanicamente.

| italiano | inglese |
|---|---|
| adesso |  |
| consumi |  |
| guarda |  |
| interno |  |
| modelli |  |
| opzioni |  |

> **`guarda`** compare **anche** fra i «Nomi degli strumenti» (sotto). Qui e' una parola ordinaria
> (o un nome di funzione qualunque); li' e' il nome di uno strumento esposto al modello — la stessa
> grafia, per due ragioni diverse, nella stessa lingua di partenza. Non e' un errore di copia:
> sono due voci a se', e ciascuna avra' la propria decisione.

## I nomi degli strumenti

**Non sono identificatori: sono dati.** Vivono come stringhe nella lista bianca di sicurezza
(`schedulatore/turno.py:38`), nell'etichetta `spazio` persistita nell'indice della memoria
(`memoria/cache_indice.py:27`) e nel testo del prompt (`casa/domande.py:386`,
`memoria/interpretazione.py:198`). Il nome si decide qui; **si applica in una fetta a se'**, con la
migrazione dei dati.

| italiano | che cosa fa | inglese |
|---|---|---|
| cerca |  |  |
| guarda |  |  |
| legami |  |  |
| ricorda |  |  |
| richiama |  |  |
| esegui |  |  |
| prometti |  |  |
| promesse |  |  |
| disdici |  |  |
| costruisci |  |  |
| conferma |  |  |
| andamento |  |  |
| accaduto |  |  |
