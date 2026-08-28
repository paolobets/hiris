# GLOSSARIO — come si chiamano le cose in HIRIS

Spec: `docs/design/2026-08-28-il-glossario.md`.

Questo documento non e' storia: e' la **regola**. Si consulta ogni volta che nasce un nome, e si
aggiorna quando nasce un concetto. Non porta una data di redazione perche' non e' la fotografia di
un giorno: e' vivo, e cambia quando cambia il codice.

**Stato di questo documento: l'elenco e' completo, nessuna colonna e' decisa.** Le colonne «che
cosa fa», «inglese» e «prova del lettore nuovo» sono lasciate vuote di proposito — le riempiono i
task successivi della stessa fetta. Una riga con la colonna vuota significa «non ancora deciso», non
«dimenticato».

**Aggiornato il 28/08 durante l'esecuzione, dopo una review:** la prima stesura aveva tre insiemi.
La review ha trovato un quarto insieme che la spec non aveva visto (`genere` e altre parole che
vivono come **valori** dentro costanti, non come nomi di modulo o classe) — vedi «I valori di
dominio» in fondo, e §4④ di `docs/design/2026-08-28-il-glossario.md`.

## Come si legge

Il nome inglese non e' la traduzione della parola italiana: e' il nome di **cio' che la cosa fa**.
La colonna «che cosa fa» si scrivera', quando verra' riempita, **senza usare la parola italiana**,
perche' e' cosi' che si arrivera' al nome — non traducendo, rinominando.

Il criterio che separa gli insiemi qui sotto e' **la natura della parola, non quanto e' usata**: un
concetto raro (`comprimari`) richiede tutto il giudizio che una parola frequente (`giorno`) non
richiede affatto.

## Parole scartate durante l'estrazione

Una regola esclusa non e' silenzio, e' una decisione scritta. Lo script di estrazione (Step 1 del
piano) ha fatto uscire tre parole che **non richiedono nessuna decisione di rinomina**, perche' sono
gia' nella lingua di destinazione o sono una sigla, e sono state tolte a mano dall'elenco:

| parola uscita dallo script | perche' e' stata scartata |
|---|---|
| `backend` | e' gia' inglese — frammento del nome di un file dentro `backends/` (il modulo plurale e' gia' filtrato, il singolare sfugge come pezzo di un altro nome di file) |
| `sanitize` | e' gia' inglese, usata cosi' com'e' nel codice |
| `yaml` | e' una sigla di formato, non si traduce |

Lo script ha anche fatto uscire tre coppie singolare/plurale della stessa parola. Nel glossario
resta **un solo lemma per coppia** — la forma scelta e' quella data dalla spec come esempio certo
in §4①:

| forma uscita dallo script | lemma nel glossario |
|---|---|
| `costruzioni` | `costruzione` |
| `esiti` | `esito` |
| `gambe` | `gamba` |

## I concetti

Parole che il progetto ha **inventato**, o a cui ha dato un significato suo. Per spiegarle a
qualcuno bisogna raccontare come funziona HIRIS.

Sette di queste righe (`genere`, `specie`, `famiglia`, `gesto`, `direzione`, `segno`, `origine`)
non vengono dallo script di Step 1: sono le **etichette** delle costanti di dominio scoperte dalla
review (vedi «I valori di dominio», in fondo). Sono due decisioni distinte sulla stessa riga di
codice: il **valore** (`'funzionamento'`) e' un dato che vive in «I valori di dominio»; la **parola**
che lo classifica (`genere`) e' un concetto e vive qui.

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
| direzione |  |  |  |
| dispatcher |  |  |  |
| domande |  |  |  |
| esito |  |  |  |
| famiglia |  |  |  |
| flusso |  |  |  |
| forme |  |  |  |
| gamba |  |  |  |
| genere |  |  |  |
| gesto |  |  |  |
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
| origine |  |  |  |
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
| segno |  |  |  |
| semaforo |  |  |  |
| servizi |  |  |  |
| spazio |  |  |  |
| specie |  |  |  |
| stati |  |  |  |
| strumenti |  |  |  |
| tempo |  |  |  |
| turno |  |  |  |
| verdetto |  |  |  |
| verifica |  |  |  |
| versioni |  |  |  |
| vive |  |  |  |
| vocabolario |  |  |  |

> **`promessa`** (qui) e **`promesse`** (nei «Nomi degli strumenti», sotto) sono **due cose
> diverse**: la prima e' il concetto/modulo Python (il significato di «una promessa nel ponte»), la
> seconda e' la stringa che il modello legge come nome di uno strumento. Il brief che ha guidato
> questo task usa «guarda e promesse compaiono due volte» come scorciatoia per descrivere questa
> coppia insieme al caso di `guarda` — ma a differenza di `guarda` (stessa identica grafia in due
> sezioni), qui **le grafie sono diverse**: singolare (`promessa`) per il concetto, plurale
> (`promesse`) perche' cosi' e' scritta la stringa nel codice (`schedulatore/turno.py:38`, la lista
> bianca di sicurezza). Non e' un doppione mancato ne' un dedup fatto a meta': sono deliberatamente
> due voci, con due grafie diverse perche' cosi' sono nel codice.

> **`origine` e `segno`: perche' sono qui e non fra le parole ordinarie, e perche' il glossario
> vince sulla spec.** Il §4② di `docs/design/2026-08-28-il-glossario.md` elenca `origine` come
> esempio di parola ordinaria ("non entra"). Quella `origine` non e' questa: l'esempio della spec
> era un elenco a campione scritto prima di guardare il codice, mentre la voce qui viene
> dall'estrazione vera di `ORIGINI_UMANE` (vedi «I valori di dominio», in fondo) — non e' il
> sostantivo generico "origine di qualcosa", e' la parola che classifica un valore persistito (se
> un'azione l'ha fatta un umano), e per questo porta un significato costruito da HIRIS, non un
> equivalente diretto. Una regola ribaltata e' comunque una decisione scritta: questa nota lo e'.
> Stesso ragionamento, dedotto con lo stesso criterio, per `segno` (da `_SEGNI_MIGRAZIONE`): i
> valori che classifica (`seminato`, `catena_seminata`, `piano_seminato`) sono marcatori specifici
> del progetto, non un sostantivo generico.

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

## I valori di dominio

**Aggiunto il 28/08 durante l'esecuzione: la spec non li aveva visti.** Emersi dalla review del
Task 1, che ha trovato `genere` — un concetto vero, assente dalla prima stesura perche' non e' mai
nome di modulo ne' di classe.

Esiste uno strato di vocabolario che vive **come valore**, non come identificatore: tassonomie di
dominio dichiarate come costanti Python e **persistite nei database** (`genere TEXT NOT NULL` in
`cervello/archivio.py:91` e `azione/cronaca.py:65`, `specie TEXT NOT NULL` in
`schedulatore/archivio.py:34`). **Sono dati, esattamente come i 13 nomi degli strumenti** qui sopra:
il nome si decide qui, si applica in una fetta che sa gestire la migrazione di cio' che e' gia'
scritto — non con la rinomina degli identificatori.

La parola che classifica ciascuna costante (`genere`, `specie`, `famiglia`, `gesto`, `direzione`,
`segno`, `origine`) e' un'altra cosa — un **identificatore**, quindi un concetto: e' gia' in «I
concetti», sopra.

| costante | valori | dove vive | valori — inglese |
|---|---|---|---|
| `GENERI` | funzionamento · presenza · energia · guasto · sicurezza · bilancio | `cervello/oggetti.py:44`; colonna `genere` in `cervello/archivio.py:91` e `azione/cronaca.py:65` |  |
| `GAMBE` | chi c'e' · comfort · dispersione · energia · buono stato · sicurezza | `cervello/pavimento.py:21` — i nomi delle sei gambe del pavimento dell'osservatore |  |
| `SPECIE` | fai · chiedi | `schedulatore/promessa.py:21`; colonna `specie` in `schedulatore/archivio.py:34` |  |
| `STATI_CONCLUSI` | mantenuta · saltata · disdetta · fallita | `schedulatore/promessa.py:22` — stato concluso delle promesse |  |
| `STATI_SOSPESO` | in_attesa · in_corso | `azione/costruzione/versioni.py:36` e `schedulatore/promessa.py:34` — definita due volte, stesso valore |  |
| `DIREZIONI_BILANCIO` | produzione · autoconsumo · immissione · prelievo · carica · scarica · consumo | `cervello/oggetti.py:71` — le direzioni del bilancio energia dell'osservatore |  |
| `FAMIGLIE` | credenziale · modello · irraggiungibile · scaduto · altro | `esiti_provider.py:63` — famiglie di esito dei provider LLM |  |
| `_GESTI` | crea · modifica · cancella | `azione/costruzione/officina.py:56` — i gesti sulle costruzioni |  |
| `_TIPI_COMPORTAMENTO` | automazione · script | `casa/domande.py:68` — i tipi di comportamento della casa |  |
| `ORIGINI_UMANE` | pagina | `azione/costruzione/officina.py:54` — l'origine di un'azione quando e' un umano a farla |  |
| `_SEGNI_MIGRAZIONE` | seminato · catena_seminata · piano_seminato | `api/handlers_models.py:94` — i segni lasciati da una migrazione gia' avvenuta |  |
| `_LEGAMI_COMPRIMARI` | entita · automazione · scena · script | `server.py:807` — i tipi di comprimari a cui una promessa puo' legarsi |  |

> Perche' `tipo` non compare come riga nuova per `_TIPI_COMPORTAMENTO`: non e' mai uscito
> dall'estrazione (Step 1/2), e col criterio del §4② sarebbe comunque una **parola ordinaria** — un
> sostantivo generico ("type"), cosi' come negli esempi certi del brief — non un concetto da
> aggiungere. Perche' `legame`/`comprimari` non generano una nuova voce per `_LEGAMI_COMPRIMARI`: la
> costante enumera **tipi di comprimari**, e sia `legami` (nomi degli strumenti) sia `comprimari`
> (concetti) sono gia' voci a se' — non serve una terza parola.
