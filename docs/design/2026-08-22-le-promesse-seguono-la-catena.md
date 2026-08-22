# Le promesse seguono la catena

**Data:** 22 agosto 2026 · **Ramo:** `2.0` · **Stato:** disegno approvato dal proprietario, piano da scrivere

---

## Il fatto da cui si parte

HIRIS ha **due regole diverse su chi risponde**, e nessuna delle due sa dell'altra.

La chat sceglie in un punto solo — `api/handlers_chat.py:727-766`: se il ponte è acceso *e* il
piano può rispondere, il turno va in coda (`kind="chat"`) e lo serve l'abbonamento; altrimenti
scende alla catena dei provider, **dichiarando il ripiego**. Il turno di una promessa quella
decisione non la incontra mai: `schedulatore/turno.py::interpreta_promessa` chiede a
`app["llm_router"]`, e nel router il ponte non è un anello — `_VALID_BACKEND_NAMES` conosce
`claude`, `openai`, `openrouter`, `ollama`.

**Decisione del proprietario, 21 agosto 2026, parole sue:**

> *«Perché il ponte non serve le promesse? Il comportamento deve essere unico per applicazione,
> quindi anche le promesse seguono la gerarchia dei modelli definita.»*

È la fondamenta n.3 — *la stessa cosa ha la stessa forma da tutte le porte* — applicata alla
domanda più importante che il prodotto si pone a ogni turno. Due regole sullo stesso fatto sono un
doppione, e prima o poi una delle due mente.

### Come si è visto

La sera del 21 agosto, provando dal vivo la 3.9.3 su una casa che gira **interamente sul Piano
Claude Max**:

| anello della catena | esito misurato |
|---|---|
| Piano Claude Max (ponte) | *«non l'hai ancora usato»* — serve la chat, non le promesse |
| Claude API `claude-opus-4-8` | rifiutata, **400**, *«credito esaurito»* |
| OpenRouter `mistralai/mistral-large` | rifiutata, **429** |

La chat funzionava perfettamente. Le promesse fallivano tutte. Il proprietario aveva un
abbonamento sano davanti e HIRIS non poteva usarlo per la cosa che gli aveva chiesto — e **niente
in nessuna pagina lo diceva**.

---

## Le decisioni

| # | Domanda | Decisione |
|---|---|---|
| 1 | Chi aspetta, se il ponte ci mette minuti | **Nessuno.** Lo Schedulatore accoda e prosegue; la promessa si conclude quando il ponte consegna |
| 2 | Le promesse contano nel tetto giornaliero del piano | **Sì.** Il tetto è «quanto uso il piano al giorno», e una promessa lo usa come un messaggio |

La prima regge la regola **mai in ritardo** (tolleranza 120 s): un battito che aspettasse dieci
minuti farebbe marcare *saltate* le altre promesse dello stesso giro. La seconda tiene onesto un
numero che l'utente ha messo per non sfondare il piano, non per limitare una superficie sola.

---

## 1. Una decisione sola su chi risponde

La regola esce da `handle_chat` e diventa una funzione sua:

```python
# hiris/app/instradamento.py
def chi_risponde(app) -> tuple[str, str]:
    """`("ponte", "")` oppure `("catena", motivo)`. Il motivo non è mai vuoto
    quando si ripiega: è ciò che il chiamante dichiara a chi legge."""
```

Non è un refactor di cortesia. Finché quella regola vive dentro la chat, la promessa **non può
che averne una seconda**: è la struttura a costringerla, non una svista.

`handle_chat` non cambia comportamento. Tiene le sue due guardie proprie — «una risposta in volo
per questa conversazione» (che è una proprietà della *conversazione*, non del piano) e il turno
persistito prima dell'accodamento — e poi chiede alla funzione dove mandare il turno.

`interpreta_promessa` chiama la stessa funzione. Quando risponde `"catena"`, il turno prosegue
com'è oggi, sincrono, su `llm_router`, e **il motivo del ripiego finisce nella promessa**: chi
legge la pagina deve poter sapere che quel turno è costato a consumo invece che a forfait.

Il tetto giornaliero smette di contare solo `kind='chat'`: conta i turni del piano, di qualunque
specie. Una riga di SQL in `reasoning/queue.py`, e il numero torna a dire quello che promette.

## 2. Il turno di promessa sul ponte

**Il job.** Lo Schedulatore accoda `kind="promessa"`. La colonna esiste già, e
`agent/runner.py:1416` ha già il ramo `if kind == "chat"` con un log dichiarato per gli altri: era
un'estensione prevista, non una forzatura. Il contesto porta `id` della promessa, `frase`,
`domanda`, `istantanea` e il nucleo — composto **dalla stessa funzione** del percorso sincrono, mai
da una seconda composizione destinata a divergere.

**Come la rotta sa che questo turno è una promessa.** Non può saperlo da `X-HIRIS-Turno`:
quell'identità la **conia il runner del ponte**, per turno, dopo che il job è già in coda — l'add-on
non ce l'ha al momento dell'accodamento, e una tabella di corrispondenza andrebbe riempita da chi
non la conosce.

La strada giusta è quella che il token interno percorre già: `agent/runner.py::config_mcp`
costruisce la `--mcp-config` con gli **header** che ogni `tools/call` riporterà indietro. Per un job
`kind="promessa"` il runner aggiunge `X-HIRIS-Promessa: <id>`, preso dal contesto del job. La rotta
lo legge e **verifica**: la promessa deve esistere e essere `in_corso`, altrimenti l'intestazione
non vale niente e il turno resta quello ordinario. Non è un'autenticazione — quella resta il token
interno, come dice già la docstring di `handlers_mcp` — è ciò che dice *quale* turno sta parlando.

Vale la stessa disciplina di redazione del token: l'id di una promessa non è un segreto, ma
l'header viaggia nell'`argv` del sottoprocesso insieme al token, e la funzione che reda i segreti
nell'eco della CLI resta l'unica strada per cui quell'`argv` possa finire in un log.

**Gli strumenti.** Sul ponte gli strumenti passano da `POST /api/mcp`, che oggi serve
`STRUMENTI_CONOSCENZA` e dispaccia con `costruisci_dispatcher_strumenti(app)`. Diventa
**consapevole del turno**. Per un turno che porta un `X-HIRIS-Promessa` valido:

- `tools/list` restituisce `strumenti_promessa()` — i quattro lettori più `concludi`;
- `tools/call` dispaccia attraverso `DispatcherPromessa`, che rifiuta tutto ciò che non è in
  `SOLA_LETTURA`.

**Gli stessi due oggetti del ramo sincrono, non copie.** È ciò che rende l'elenco di *ammissione*
vero su entrambe le strade: uno strumento nuovo che scrive non entra da solo in nessuna delle due.

**La conclusione.** Quando il modello chiama `concludi`, la conclusione si registra **sulla
promessa**, non nel testo della risposta. Il `submit` del job è soltanto il segnale «il turno è
finito»: se arriva senza che `concludi` sia stato chiamato, la promessa fallisce col motivo che
porta ciò che il modello ha detto al suo posto — la forma costruita il 21 agosto (v3.9.3), che
esiste proprio per non lasciare opaco questo caso.

## 3. `mantieni` a due tempi

`Orologio._mantieni_chiedi` si spezza:

- **accodare** — chiede a `chi_risponde`; se è il ponte, mette il job in coda e lascia la promessa
  `in_corso`; se è la catena, fa quello che fa oggi;
- **concludere** — riceve `{avvisare, testo}` e chiude la promessa.

Il secondo tempo **è già scritto**: la parte che notifica dalla porta, gestisce il recapito
mancante (`_SENZA_RECAPITO`) e chiude la promessa vive in `orologio.py:83-108`. Diventa un metodo
chiamato da due punti — il ritorno sincrono della catena e la consegna del ponte. **Un solo punto
che conclude una promessa**, come `azione/porta.py` è l'unico che esegue: un secondo sarebbe un
difetto, non un'ottimizzazione.

**Scadenza.** Se il job supera `scadenza_min` (oggi 10 minuti) la promessa fallisce dichiarando
l'attesa. Non resta appesa: una promessa `in_corso` per sempre è peggio di una fallita, perché non
si vede.

## 4. Cosa peggiora, e va detto adesso

La finestra in cui una promessa è `in_corso` passa da **secondi a minuti**.

`ArchivioPromesse.risana()` è deliberatamente conservativo: al riavvio marca *fallita* ogni
promessa `in_corso` e **non la ripete** — *«non so se fosse già partita: una luce accesa due volte
è innocua, una serranda no»*. Oggi quella finestra è così stretta che non capita quasi mai; dopo
questa fetta capiterà a ogni aggiornamento dell'add-on che cada su una promessa in volo.

Per un `chiedi` la cautela è persino eccessiva — non ha eseguito niente, ripeterlo sarebbe
innocuo — ma è una regola **dichiarata e uniforme**, e questa fetta non la tocca. Rilassarla
richiede distinguere `fai` da `chiedi` dentro `risana`, ed è una decisione sua, da prendere
guardando un caso vero.

## 5. Come si prova

**Unità e integrazione.** `chi_risponde` con le sue quattro combinazioni (ponte spento · piano
senza token · tetto pieno · tutto acceso); `/api/mcp` che per un turno di promessa serve
`concludi` e **rifiuta `esegui`** — con la finta che sa eseguirlo, o il test non può fallire;
il tetto che conta entrambe le specie; `mantieni` a due tempi, con la conclusione che arriva
dopo, da un altro punto.

**La prova che conta**, e che il 21 agosto non era eseguibile: la promessa **«8 stanze + delta +
notifica» riesce sul Piano Claude Max**, senza nessuna chiave API viva. Più i due contorni: a
tetto pieno ripiega sulla catena e lo dichiara nella promessa; con la catena morta fallisce
dicendo perché.

La suite verde non è una prova. Questa fetta nasce da tre difetti che nessun test aveva visto.

---

## Cosa questa fetta NON fa

- **Non tocca `risana`.** La finestra si allarga e la regola resta com'è, dichiarata.
- **Non dà al ponte gli strumenti che scrivono.** `SOLA_LETTURA` vale su entrambe le strade: un
  turno che gira senza nessuno davanti non tocca la casa, da qualunque provider passi.
- **Non introduce una priorità fra chat e promesse** sul tetto. Sarebbe una seconda regola da
  tenere allineata — cioè esattamente ciò che questa fetta esiste per togliere.
- **Non cambia la catena né la pagina Modelli.** L'ordine degli anelli resta l'unica verità su chi
  risponde; questa fetta fa solo in modo che le promesse la leggano.
