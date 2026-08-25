# Fuori scope — l'unico archivio

**Questi documenti non valgono più. Sono qui perché spiegano *perché* il prodotto è com'è.**

Regola del proprietario: **si sposta, non si cancella** — la storia di perché una scelta fu presa
è spesso l'unica cosa che spiega il codice di oggi. Quello che deve sparire è la confusione, non
la memoria.

Il criterio **non è la data**. Un documento sta qui se vale almeno una di queste tre:

1. **descrive un prodotto che non esiste più** (il Brain vecchio, gli Agentbot, il semaforo, le
   proposte, il gateway, il RAG vettoriale, il Task Engine);
2. **è stato dichiarato superato** da un documento più recente;
3. **è un piano già eseguito**, il cui contenuto vive ormai nel codice e nel `CHANGELOG.md`.

> Chi cerca la verità corrente non è qui: sta in `CLAUDE.md` (le regole), `README.md` (cosa fa il
> prodotto), `docs/design/2026-08-04-scope-hiris.md` (il contratto) e nei documenti datati vivi di
> `docs/design/`.

## Aggiunti il 25 agosto su decisione del proprietario

| Documento | Cos'e' | Perche' non vale piu' |
|---|---|---|
| `2026-08-03-analisi-funzionale.md` | cosa faceva il codice, con `file:riga` | descriveva il prodotto **prima** della demolizione: quasi ogni riferimento punta a codice cancellato. **Tolto anche da `CLAUDE.md`**, dove era elencato fra i riferimenti vivi |
| `2026-08-03-revisione-tecnica.md` | lo stato tecnico di allora | stessa ragione, stessa data, stesso prodotto. **Tolto da `CLAUDE.md`** |
| `2026-08-04-come-nasce-un-agente.md` | lo strato ③, come nasce un agente | **mai costruito**, e il ripensamento del cervello del 25/08 lo travolge: il proprietario ha deciso che gli agenti «non serviranno piu'». Resta come storia di una strada non presa |


## Struttura — un archivio solo

`docs/archive/` è stato **assorbito qui dentro** come [`pre-2.0/`](pre-2.0/): due archivi senza
una differenza dichiarata sono peggio di uno, e questo progetto tratta i doppioni come difetti.

| Dove | Cosa contiene |
|---|---|
| `pre-2.0/` | Tutto ciò che descriveva HIRIS **prima del Refactor 2.0** (fino al 1° agosto 2026). Ha un proprio [README](pre-2.0/README.md) con il vocabolario abbandonato (Sentinella, Agentbot, semaforo, workbench) — leggilo prima di aprire quei file |
| questa cartella | Documenti **dell'era 2.0** superati da fette successive, più i tre della campagna «coerenza» che ha preceduto il refactor |

## Indice — cosa è, e perché non vale più

### La campagna «coerenza» (pre-refactor, sul ramo `feat/coerenza`)

| Documento | Cosa è | Perché non vale più |
|---|---|---|
| [2026-08-02-inventario-coerenza.md](2026-08-02-inventario-coerenza.md) | Inventario delle incoerenze di `1.1.0-beta.15`: difetti funzionali, vocabolario, superfici | Fotografa un prodotto (chatbot multipli, Brain, semaforo) che il Refactor 2.0 ha demolito; i difetti elencati sono chiusi o usciti col codice che li conteneva |
| [2026-08-02-design-coerenza.md](2026-08-02-design-coerenza.md) | Il piano del secondo e terzo lotto di coerenza su quell'inventario | Piano eseguito prima del refactor; il suo oggetto (i dieci difetti residui della 1.x) non esiste più |
| [2026-08-02-design-consolidamento.md](2026-08-02-design-consolidamento.md) | Lo sprint di consolidamento dei tre filoni 1.x (plance a proposta, salute sistema, denylist) | Tutti e tre i filoni consolidati sono usciti dal prodotto con le fette E2/E3 |

### Il Brain e la memoria della prima ora (era 2.0, superati)

| Documento | Cosa è | Perché non vale più |
|---|---|---|
| [2026-08-04-cosa-sa-il-brain.md](2026-08-04-cosa-sa-il-brain.md) | Atto 1 del refactor, secondo pezzo: che forma ha la conoscenza del Brain (ritratto, delta, memoria) | Superato due volte: `2026-08-05-la-conoscenza-di-hiris.md` ne ha ripreso ritratto e mappa semantica; il 25 agosto `2026-08-25-il-cervello-da-capo.md` **annulla ogni documento sul Brain**. ⚠️ **Ne sopravvivono due cose**, riprese come vincolanti dal documento nuovo (§ «La trappola, misurata e non opinata»): la **misura** che il RAG vettoriale era *«un pedaggio pagato in scrittura su dati che si leggono con una `WHERE` su una data»* (qui, §3) e la **regola** *«la memoria prende la forma del dato che contiene»* |
| [2026-08-04-piano-ritratto-fetta1.md](2026-08-04-piano-ritratto-fetta1.md) | Piano della fetta «il Brain vede»: `brain/portrait.py` + `brain/portrait_store.py` | La cartella `app/brain/` non esiste più (uscita con la 2.1.0); il ritratto è stato ridisegnato in `la-conoscenza-di-hiris` e vive in `casa/` |
| [2026-08-04-piano-memoria-fetta2a.md](2026-08-04-piano-memoria-fetta2a.md) | Piano: togliere il pedaggio vettoriale dalla **scrittura** dei ricordi | Eseguito sul prodotto 1.x; quella memoria (second brain, resoconto delle 08:00) è uscita. Il principio sopravvive come contratto in `la-conoscenza-di-hiris` §6 («la ricerca degrada ai più recenti») |
| [2026-08-04-piano-memoria-fetta2b.md](2026-08-04-piano-memoria-fetta2b.md) | Piano: i ricordi affiorano da soli (iniezione nel prompt, ragionatore proattivo) | Eseguito sul prodotto 1.x; il ragionatore proattivo non esiste più, l'iniezione in contesto è stata ricostruita da zero in `memoria/` |
| [2026-08-05-design-memoria-unica.md](2026-08-05-design-memoria-unica.md) | Design «una memoria sola»: memoria slegata dal singolo chatbot | I chatbot multipli non esistono più; la memoria 2.0 è stata costruita da `la-conoscenza-di-hiris` §6 (piano «la memoria ancorata alla casa», fetta dell'8 agosto), non da questo design |
| [2026-08-05-piano-memoria-unica-3a.md](2026-08-05-piano-memoria-unica-3a.md) | Piano esecutivo della memoria unica (fetta 3a) | Piano eseguito sulla 1.1.0-beta; sostituito dallo stesso percorso del design qui sopra |

### Inventari chiusi

| Documento | Cosa è | Perché non vale più |
|---|---|---|
| [2026-08-08-frontend-da-rifare.md](2026-08-08-frontend-da-rifare.md) | L'inventario del frontend rotto, prodotto dalla fetta E3 per la fetta E5 | **Chiuso**: tutte e quattordici le voci risolte (lo dichiara il `README.md` di progetto). Il residuo non-difetto è elencato in fondo al documento stesso |

## Cosa NON sta qui, e perché

- `docs/design/2026-08-04-scope-hiris.md` — **è tuttora il contratto del prodotto** (le tre leggi,
  i tre strati). Solo la sua sezione ② (il Brain) è superata, e lo dichiara un'annotazione nel
  documento stesso, che rimanda a `2026-08-25-il-cervello-da-capo.md`.
- `docs/design/2026-08-03-analisi-funzionale.md` e `2026-08-03-revisione-tecnica.md` — descrivono
  il codice pre-refactor, ma `CLAUDE.md` li elenca ancora fra i documenti di riferimento del
  refactor: sono la baseline della demolizione.
- `docs/design/2026-08-05-mappa-funzionalita.md` — l'ordine di demolizione, ancora citato da
  `CLAUDE.md`; le sue righe superate sono annotate nel documento stesso.
- I documenti datati dal 10 agosto in poi in `docs/design/` — sono le specifiche delle fette
  **pubblicate** o **in corso**: descrivono il comportamento corrente, e il codice li cita.
- `docs/prova-*.md` — i fogli della prova sul campo: `prova-la-2.0.md` è vivo (un test ne verifica
  i numeri), gli altri due sono citati da codice e test come origine delle misure.
