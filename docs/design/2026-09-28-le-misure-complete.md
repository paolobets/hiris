# Le misure complete — il ponte si pesa, la batteria risponde, le pagine lo mostrano

`spec · 28/09/2026 · decisioni del proprietario prese in chat il 28/09/2026, disegno approvato a sezioni (1, 1-bis, 2)`

> **Come si legge dopo la costruzione.** Il disegno approvato resta com'era; dove il codice ha
> preso un'altra strada lo dice un paragrafo **«Cambiato durante la costruzione: …»** accanto alla
> sezione che cambia, con la ragione. Ciò che la fetta lascia fuori sta in §9 e, voce per voce, in
> `docs/BACKLOG.md`.

Chiude la voce del BACKLOG **«Ottimizzazione: base dati, chiamate e consumo di token»** nella sua
prima metà: non ottimizza niente, **rende decidibili** le leve. Lo sprint misure del 24/09/2026
(v3.66.0 → v3.67.1) aveva costruito i registri e dichiarato che servivano «giorni di uso vero»;
la verifica del 28/09/2026 (§1) ha mostrato che quei giorni non potevano rispondere, e perché.

Le domande dell'obiettivo, del proprietario, restano quelle del 24/09: **i dati che arrivano ai
modelli sono giusti e completi? quanti token? quanta latenza? serve un'altra tecnologia per la
conoscenza?** Più una, del 28/09: **quanto consumano davvero osservatore, analista e attuatore sul
ponte, e si possono ottimizzare anche loro?**

Nomi: identificatori e colonne in inglese, prosa e valori di dominio in italiano
(`feedback_hiris_colonne_inglese`).

---

## §0 · Le decisioni del proprietario (28/09/2026)

| # | Domanda | Decisione |
|---|---|---|
| 1 | Da dove viene il campione che chiude il tema | **La batteria delle 32 domande del 24/09**, rilanciata su catena e ponte dopo aver fatto misurare il ponte. Non si aspetta un uso vero che non arriva |
| 2 | Il ponte si misura per quali specie | **Tutte e sei**: chat, promessa, osservatore, analista, attuatore, ricette. «Altrimenti non so i veri consumi e se anche quei modelli possono essere ottimizzati» |
| 3 | Come si misura il ponte | **Token dallo stream + composizione misurata da HIRIS** (strada 1). Scartate: solo token (non dice *di cosa* è fatto il carico); un proxy fra CLI e Anthropic (si mette in mezzo all'autenticazione dell'abbonamento) |
| 4 | Le colonne dei token | **Anche sulla catena**: un registro solo, confrontabile riga per riga |
| 5 | Le pagine | **Consumi e Modelli mostrano i dati nuovi**, nella stessa fetta, **dopo** la batteria: prima si verifica che i numeri siano giusti, poi si mostrano |

---

## §1 · I fatti (misurati il 28/09/2026 sulla casa vera, v3.69.1, CLI del ponte 2.1.283)

**Perché le misure non sono arrivate — tre cause, nessuna è «non è passato abbastanza tempo».**

1. **Il ponte non scrive i carichi per giro, su una premessa falsa.** `agent/runner.py::_measure_turn`
   dichiara «i pesi per giro **non esistono** da questa parte» (e il CHANGELOG 3.67.0 lo ripete).
   Provato sulla CLI vera (`claude -p … --output-format stream-json --verbose`, un turno con uno
   strumento): **ogni evento `assistant` porta `message.usage`** — `input_tokens`,
   `cache_read_input_tokens`, `cache_creation_input_tokens` e `cache_creation.ephemeral_5m_input_tokens`
   / `ephemeral_1h_input_tokens`. Una chiamata all'API emette **più eventi con lo stesso
   `message.id`** (uno per blocco: `thinking`, `tool_use`, `text`) e lo stesso `usage`: il giro è
   il `message.id`, non l'evento. Il numero di `message.id` distinti coincide con `num_turns` (2 su
   2). `read_stream` legge quegli eventi per i `tool_use` e scarta `usage`.
   `output_tokens` per evento vale **1** (conteggio parziale dello streaming): il totale vero sta
   solo nell'evento `result`.
2. **L'uso vero nel registro è quasi zero.** 70 turni dal 24/09 14:16 al 28/09 13:39. Di 55 turni
   di chat: **40 dalla porta di sviluppo** (le prove), 13 senza soggetto (prima della 3.68.0, 25/09),
   **2 del proprietario**. Dal 26/09 pomeriggio nessuna chat. Tutti i 96 carichi sono del 24/09 —
   la sessione di prova sulla catena. Dal 25/09 tutto è passato sul ponte, cioè la strada muta.
3. **I rimedi della 3.67.x non sono mai stati misurati.** Le 32 domande del 24/09 hanno trovato
   quattro difetti, corretti nella 3.67.0/3.67.1; la batteria non è mai stata rilanciata. I 37
   turni della catena portano ancora `provider/model = ignoto`, scritti prima della correzione.

**Cosa i giorni sul ponte hanno detto lo stesso** (`/api/misure`, `/api/usage/history`):

- **`ToolSearch` apre 18 turni su 21 con strumenti**: la CLI carica gli strumenti MCP in differita,
  e ogni domanda paga un giro in più per cercarli. La chat sul ponte fa 3,3 giri di media.
- **La cache del ponte crolla sui giri di fondo**: 74% (24/09) → 66% → 62% → **16% (27/09)** →
  **7% (28/09)**. Il 27/09: 111.089 token scritti in cache, 21.159 riletti. La CLI scrive la cache
  con **durata 1 ora** (`ephemeral_1h`), e osservatore/analista/attuatore sono turni di un giro a
  distanza di un'ora o di un giorno: scrivono un prefisso che nessuno rilegge.
- **I giri di fondo sono lenti ma nessuno aspetta**: analista mediana 125 s (peggiore 178 s),
  osservatore 90–147 s, un giro solo, circa 11.000 token di uscita a turno.
- **La chat sul ponte resta più veloce della catena**: mediana 12,7 s contro 20,4 s.

**Dove si compone il carico del ponte** (letto nel codice):

- `agent/runner.py::_reason_chat` compone `system` e `user` con `prompts.build_chat_messages`
  (guida + nucleo = `contesto`, cronologia = `history`, istruzione della specie) e li passa nell'argv
  (`_chat_claude_args`: `--system-prompt`, `-p`). **Tutte e sei le specie passano di qui.**
- Conia `exchange_id` una volta per turno e lo manda come `X-HIRIS-Turno` su ogni chiamata a
  `/api/mcp` (`config_mcp`). `api/handlers_mcp.py::_count_round` già conta i giri per quell'identità.
- Il runner gira **nello stesso processo** del server, in un executor (`server.py:5566`); il gancio
  del registro è `server.py::_registra_turno_ponte`, che ha l'app in mano.

**`scripts/misure.py` ha due difetti propri**: «-3 mai chiamati» (conta `ToolSearch` e i nomi
prefissati `mcp__hiris__*` come se fossero strumenti del catalogo) e «un canale solo» per la chat,
che invece gira su entrambi (confronta i canali sui carichi, che il ponte non aveva).

**La batteria vive fuori dal repo**: `32-domande.md` e `venti_domande.py` sono nello scratchpad di
una sessione del 24/09. Lo stesso destino del documento di consegna, che stava in `%TEMP%`.

---

## §2 · Il registro, esteso (non un secondo registro)

`usage/store.py`, tabella **`payload`** — una riga per giro, com'è oggi. Si aggiungono:

| colonna | tipo | significato |
|---|---|---|
| `input_tokens` | INTEGER NULL | token nuovi del giro |
| `cache_read_tokens` | INTEGER NULL | token riletti dalla cache |
| `cache_write_tokens` | INTEGER NULL | token scritti in cache |
| `cache_ttl` | TEXT NULL | `5m`, `1h`, `misto` o NULL quando il provider non lo dice |

Tabella **`turn`**: si aggiunge **`output_tokens`** INTEGER NULL, il totale del turno.

**NULL, non zero**: una riga scritta prima di questa versione, o un provider che non dichiara la
cache, non ha il numero — e «non misurato» non è «zero» (la regola che `_measure_turn` già scrive:
«un'assenza è una risposta, uno zero è una bugia»). Le colonne carattere esistenti restano NOT NULL
e restano ciò che sono.

> **Cambiato durante la costruzione.** Un valore di token malformato (una stringa, un dizionario,
> un booleano dove serve un intero) diventa **NULL alla fonte**, non un'eccezione che fa cadere il
> turno: `usage/giro.py::_int_or_none` è il solo posto che legge un numero di token, per la catena
> e per lo stream del ponte insieme — un valore inatteso protegge tutti e tre i lettori con la
> stessa regola, invece di farlo tre volte.

Migrazione: `ALTER TABLE … ADD COLUMN`, nello stile delle migrazioni di `storage.init_schema`.
Conservazione invariata (30 giorni, `TURNS_RETENTION_S`). **Mai gli argomenti degli strumenti.**

---

> **Cambiato durante il piano (28/09/2026).** `payload` porta anche **`output_tokens`** (per giro:
> esatto sulla catena, NULL sul ponte) e **`cost_usd`** (per giro: il costo della catena, NULL sul
> ponte). Senza `cost_usd` per giro la pagina «Chi consuma» (§5) non potrebbe dare il costo per
> attore: il registro dei consumi è per modello e giorno, non per attore.
>
> **Aggiunto dal proprietario (28/09/2026): «la riga del costo».** `turn` porta **`list_cost_usd`**:
> quanto sarebbe costato il turno **a consumo**, come lo dichiara la CLI del ponte
> (`result.modelUsage[*].costUSD`, visto sul flusso vero: 0,0696 $ per un turno di due giri).
> **Non è un costo pagato** — sul ponte il turno è compreso nell'abbonamento — e per questo ha una
> colonna sua e non entra in `cost_usd`: due cose diverse, due colonne. «Chi consuma» (§5) lo mostra
> distinto dal pagato.

## §3 · La catena: i token accanto ai caratteri

Oggi la misura del giro scatta **prima** della chiamata (`claude_runner.py:1040`, gemello in
`backends/openai_compat_runner.py:777`): pesa il carico in caratteri e lo consegna al raccoglitore
della ContextVar (`_misura_corrente`). I token arrivano **dopo**, nell'`usage` della risposta, e
oggi vanno solo al registro dei consumi per modello.

Si aggiunge una **seconda consegna sullo stesso giro, dopo la risposta**, con i token. Lo stesso
raccoglitore, la stessa ContextVar — nessun secondo gancio. `steering.misura_turno` fonde le due
consegne dello stesso giro in una riga sola prima di scrivere.

- **Anthropic** (`claude_runner`): `input_tokens`, `cache_read_input_tokens`,
  `cache_creation_input_tokens`; il TTL da `usage.cache_creation` se c'è.
- **OpenAI-compatibili** (`openai_compat_runner`): i token nuovi e letti dalla cache come li
  dichiara il provider; `cache_write_tokens` e `cache_ttl` NULL quando il provider non li porta.
- `output_tokens` del turno = somma delle uscite dei giri, che sulla catena sono esatte.

---

## §4 · Il ponte: tre punti di cattura, un'identità

Il legame è **`exchange_id`**, già coniato una volta per turno.

**(1) All'avvio della CLI — la composizione.** Dove `_invoca` chiama `build_chat_messages`, si
pesano in caratteri: la guida (`system` meno il nucleo), il nucleo (`contesto`), la cronologia
(`history`), la domanda. Vanno sul **primo giro**: è ciò che HIRIS consegna alla CLI una volta.
Vale per tutte e sei le specie; le specie autosufficienti (`_SELF_CONTAINED_KINDS`) hanno nucleo
vuoto e lo dicono con uno zero vero (la casa sta nella loro domanda, non nel nucleo).

> **Cambiato durante il piano.** La composizione va su **ogni** giro, non sul primo: ogni chiamata
> all'API rispedisce il prompt di sistema e la conversazione, come sulla catena, e metterla solo sul
> primo giro farebbe sembrare il ponte più leggero per costruzione.

**(2) Su `/api/mcp` — le definizioni e i risultati.** La rotta accumula, per `X-HIRIS-Turno`:
i caratteri della risposta a `tools/list` (le definizioni che la CLI ha ricevuto) e, per ogni
`tools/call`, i caratteri del risultato. Lo stato vive accanto al contatore del tetto
(`_count_round`), con la stessa politica di scadenza.

> **Cambiato durante il piano.** Non nello stesso dizionario del contatore: quello lo tocca solo il
> thread del loop e non ha lock, mentre questo lo legge anche il thread dell'executor del ponte.
> Un archivio suo, `usage/bridge_loads.py::BridgeLoads`, con un lock. Una chiamata senza `X-HIRIS-Turno` non si
attribuisce a nessun turno e lo dichiara nel log (come già fa per il tetto).

> **Cambiato durante la costruzione.** Un errore JSON-RPC (chiamata malformata) non ha `result`: al
> modello arriva comunque il suo `error.message`, e `handlers_mcp.py::_annota_risultato` pesa quel
> testo invece di scrivere zero — zero direbbe che il modello non ha ricevuto niente, ed è falso.
> La misura non solleva: un guasto qui non toglie mai gli strumenti alla CLI, si logga e la
> chiamata risponde lo stesso.

> **Cambiato durante la costruzione.** Un turno **rifatto dopo un primo tentativo** (l'invocazione
> scartata e quella che ha risposto) non lega più i carichi MCP accumulati dalla prima alla riga
> scritta per la seconda: `_measure_turn` riceve un `exchange_id` vuoto quando il turno arriva da
> un ciclo già rilanciato, così l'annotazione orfana della prima invocazione resta orfana — esce
> dal tetto LRU di `BridgeLoads` — invece di attribuirsi a un turno che non l'ha ricevuta.

**(3) Alla lettura dello stream — i token di ogni giro.** `read_stream` raccoglie `message.usage`
**raggruppando per `message.id`**: un giro = una chiamata all'API. `StreamOccurrence` guadagna la
lista dei giri, nell'ordine. Da `result.usage` il totale dell'uscita.

> **Cambiato durante la costruzione.** Il conto dello stream come ripiego (§4, punto 3) vale
> **quando la CLI non dichiara `num_turns`**: `n_cli is not None else n_stream`. È un caso diverso
> dal disaccordo fra i due conti descritto sopra — lì entrambi i numeri esistono e non
> coincidono, e si scrivono comunque i giri dello stream col log che porta entrambi; qui la CLI
> tace del tutto, e mai uno zero che dica «nessun giro» di un turno che ne ha fatti.

**La scrittura.** `_measure_turn` passa al gancio la riga del turno **con l'`exchange_id`** e i
giri dello stream (token) e della composizione (caratteri del primo giro).
`server.py::_registra_turno_ponte` — che ha l'app — raccoglie dalla rotta MCP ciò che quel turno
ha accumulato (definizioni, risultati per chiamata), lo distribuisce sui giri e scrive `turn` +
`payload`. I risultati si accumulano giro per giro come sulla catena: ogni giro li rispedisce
tutti.

**Cosa si dichiara invece di inventarlo** (nel codice e nella pagina):

- **I caratteri dicono ciò che HIRIS ha fornito; i token dicono ciò che il modello ha ricevuto.**
  La CLI aggiunge il proprio contorno (il suo prompt di base, `ToolSearch`, i riepiloghi degli
  strumenti in differita). Lo scarto fra i due **è** la misura di quel contorno, e sul ponte è la
  sola che esista.
- **Le definizioni arrivano in differita.** Sul ponte non partono a ogni giro: arrivano quando
  `ToolSearch` le carica. Si registrano sul giro in cui `tools/list` è stata servita, non su tutti.
- **L'uscita esiste solo per turno** (§1, fatto 1).
- **Se il numero dei `message.id` non coincide con `num_turns`**, il turno si scrive coi giri
  dello stream e il disaccordo va nel log con entrambi i numeri: è un cambio di forma della CLI, e
  deve farsi vedere al primo turno.

**La legge che resta**: la misura non può far cadere un turno (la regola di `misura_turno` e di
`_measure_turn`). Un guasto del registro si logga e il proprietario ha la sua risposta.

> **Cambiato durante la costruzione.** Un turno del ponte che finisce in fallimento si registra ora
> con `outcome: "fallito"`, non più con l'esito di una risposta arrivata: prima della fetta, un
> guasto sul ponte poteva scrivere una riga che diceva «riuscito» su un turno che non lo era, e chi
> legge il registro non ha modo di saperlo se la parola stessa mente.

---

## §5 · Le pagine: i dati nuovi arrivano dove si guardano

Oggi Consumi e Modelli leggono solo `/api/usage` (totali per provider e modello, secchielli al
giorno). Il registro dei turni lo legge solo `/api/misure`, rotta temporanea di servizio.

**Una rotta di prodotto nuova, aggregata**, `GET /api/usage/actors?giorni=N`: per **attore × canale** — turni, giri medi, durata mediana, token nuovi/letti/scritti,
quota di cache che colpisce, token di uscita; sulla catena anche il costo in euro, dal registro dei
consumi. **Mai il soggetto**: aggrega, non elenca chi ha chiesto. Sta nel perimetro degli
amministratori come `/api/usage` (lista di ammissione della 3.69.0, da verificare nel piano).
`/api/misure` **non** diventa l'interfaccia delle pagine: resta temporanea ed esce (§8).

**Consumi — sezione nuova «Chi consuma».** Una riga per attore (chat, osservatore, analista,
attuatore, promessa, ricette), divisa per canale. Sul ponte, dove il costo è «Compreso», sono i
token a dire quanto si consuma del piano; la scrittura in cache si mostra distinta dalla lettura,
perché è lì che i giri di fondo pesano. Finestra: al massimo 30 giorni, e la pagina lo dice.

**Modelli — per ogni modello usato**: durata mediana del turno e giri medi, dal registro.

**Il disegno delle due sezioni si fa con `ux-ui-specialist` prima di scrivere**
(`feedback_hiris_frontend_uxui`), e rispetta le regole già scritte in `static/config/usage-route.js`
(i cinque stati del costo per tipografia, mai un trattino per un costo, i colori dei provider non
riusano `--ok/--warn/--err`). Verifica dal vivo col metodo senza browser (payload veri in jsdom).

---

## §6 · La batteria entra nel repo

> **Cambiato durante il piano.** Le domande e i criteri **non** stanno nello script: nominano
> stanze, luci e automazioni, e nel codice non entra nessun nome della casa. Stanno in un file del
> proprietario fuori dal repo (`~/.hiris-batteria.json`); lo script è generico e li legge.

`scripts/batteria_misure.py` — le **32 domande del 24/09, identiche** (il confronto prima/dopo
regge solo così), cronometrate dalla domanda alla risposta, attraverso la porta firmata
(`api/canali.py::materia_firmata`, importata come fa `scripts/misure.py`).

- **Le tre domande con effetti veri** — 21 (crea una promessa), 24 (salva un ricordo), 27 (accende
  la luce della taverna) — **non partono da sole**: lo script si ferma, chiede conferma, e dopo
  indica cosa rimettere a posto. Il proprietario serve solo per quelle tre.
- **Il criterio atteso si scrive PRIMA**, accanto a ogni domanda, preso dalla casa vera (es. «nomina
  Taverna 1 e Taverna 2»; «dice che l'antimosche è disabilitata, non guasta»). Le domande che solo
  il proprietario può giudicare («cosa ti ho detto sulle luci di servizio») sono marcate sue.
- **Tre esiti per risposta**: giusta · incompleta · sbagliata. Il giudizio si registra in un file
  di esiti accanto alla durata e agli identificativi dei turni, **fuori dal repo** (le risposte
  parlano della casa).
- **Due passate, stesso giorno, stessa casa**: catena e ponte, cambiando canale da Modelli. Il costo
  della catena è di pochi euro (24/09: circa €1,7 per 216 richieste).

---

## §7 · `scripts/misure.py`, corretto e completato

- **Il catalogo**: `ToolSearch` e gli altri strumenti propri della CLI non entrano nel conto dei
  «mai chiamati»; i nomi `mcp__hiris__*` rimasti nei turni vecchi si sbucciano alla lettura.
- **I canali**: il confronto legge i turni, non solo i carichi.
- **Una sezione token** per attore e canale: nuovi, letti, scritti (5 minuti e 1 ora distinti),
  quota di cache; lo scarto caratteri/token sul ponte.
- **Il giudizio della batteria**: giuste/incomplete/sbagliate per canale, e prima/dopo rispetto al
  24/09 dove il 24/09 ha il dato.
- **Le soglie restano quelle scritte prima** (`MINIMO_TURNI = 20`, `GIRI_LUNGHI = 5`). Non si
  abbassano per far quadrare i giri di fondo (§8).

---

## §8 · Cosa chiude il tema

Un documento di esito, `docs/design/<data della chiusura>-l-esito-delle-misure.md`, che risponde alle domande
dell'obiettivo **con i numeri**:

| domanda | come si risponde |
|---|---|
| i dati sono giusti e completi | esiti della batteria per canale + le ricerche ripetute («view di fila») |
| quanti token | per attore, canale e parte del carico (definizioni, guida, nucleo, cronologia, risultati, contorno della CLI) |
| quanta latenza | giri e durata per canale e attore |
| serve un'altra tecnologia | quanti errori della batteria vengono dal recupero e quanti dalla capienza |
| i giri di fondo si possono ottimizzare | i loro token e la loro cache dal primo giro dopo il rilascio |

Ogni leva prende un verdetto — **fare · non fare · rinviata con data** — e ogni «fare» diventa una
voce del BACKLOG con la sua misura prima/dopo. La rotta `/api/misure` esce (è dichiarata
temporanea «finché i verdetti non hanno deciso»); `scripts/misure.py` legge da `consumi.db` o dalla
rotta nuova.

**Il limite, dichiarato adesso.** Osservatore, analista e attuatore girano una volta al giorno (o
ogni ora a vuoto): la batteria non li tocca, e lo script chiede 20 turni per giudicare una specie.
I loro **consumi** si vedono dal primo giro dopo il rilascio; il loro **verdetto** porta la data in
cui avranno 20 turni, scritta nel documento di esito. Non si anticipa con quattro turni.

---

## §9 · Fuori da questa fetta

- **Qualunque ottimizzazione**: nessuna leva si tocca qui. Le fette escono dal documento di esito.
- **La risposta rifiutata dell'attuatore/analista sul ponte** (BACKLOG, 28/09): si decide coi numeri
  di questa fetta, in una fetta sua.
- **Il costo in euro del ponte**: l'abbonamento non espone il prezzo del turno; si mostrano i token.

---

## §10 · Prove

- **Stream vero come campione**: un NDJSON salvato dalla CLI 2.1.283 (un turno con uno strumento,
  due chiamate, più eventi per `message.id`), ripulito da ogni segreto, in `tests/fixtures/`.
  `read_stream` deve dare due giri coi loro token; una mutazione che raggruppa per evento invece
  che per `message.id` deve diventare rossa.
- **Un test per punto di cattura** (§4: composizione, rotta MCP, stream) e per la seconda consegna
  della catena (§3), **ognuno con una mutazione eseguita**.
- **NULL non è zero**: una riga vecchia e un provider senza cache restano NULL fino alla pagina.
- **La misura non fa cadere il turno**: un registro che solleva lascia la risposta intatta, su
  entrambe le strade.
- **Il soggetto non esce** dalla rotta aggregata.
- **Verifica dal vivo** dopo ogni rilascio (`feedback_plan_live_verify`): un turno di chat sul ponte
  e il giro orario dell'osservatore scrivono giri con token e caratteri; lo scarto caratteri/token
  è positivo e plausibile.

---

## §11 · L'ordine

1. **Rilascio delle misure** (§2, §3, §4) → verifica dal vivo su catena e ponte.
2. **Batteria e script** (§6, §7) — solo `scripts/`, nessun rilascio dell'add-on → le due passate.
3. **Rilascio delle pagine** (§5) → verifica dal vivo.
4. **Il documento di esito** (§8) e l'uscita di `/api/misure` (nel primo rilascio utile).
