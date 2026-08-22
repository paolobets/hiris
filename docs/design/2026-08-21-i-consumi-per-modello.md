# I consumi, per modello

**Data:** 21 agosto 2026 · **Ramo:** `2.0` · **Stato:** disegno approvato dal proprietario, piano da scrivere

---

## Il fatto da cui si parte

La pagina «Consumi» (`#/usage`) mostra quattro numeri: richieste, token IN, token OUT, costo. Sono
la **somma di tutto**. Non c'è modo di sapere quale modello abbia consumato che cosa — e nemmeno
quale *provider*, benché la separazione per provider **esista già nei dati e venga buttata via
nella somma** (`llm_router.py:313-336`: sei proprietà che sommano i contatori dei runner).

La richiesta del proprietario, 21 agosto 2026:

> *«Al momento vi è il consumo generale ma non è possibile capire su quale modello di AI li ho
> consumati. Vorrei inserire una sezione di dettaglio che per ogni modello utilizzato nel tempo
> (quindi al primo utilizzo si attiva anche il consumo) ne dia il dettaglio.»*

Sotto la richiesta ci sono **due difetti** che questa fetta non può aggirare, perché il dettaglio
per modello li porterebbe alla luce come cifre visibili invece che come approssimazioni nascoste
in un totale.

### Difetto 1 — il costo di OpenRouter è sempre zero

`_prezzo(model)` legge `backends/pricing.py`, che conosce dodici modelli: tre Claude e nove
OpenAI. Ogni identificativo OpenRouter (`anthropic/claude-sonnet-4-6`,
`meta-llama/llama-3.3-70b-instruct`, …) **non è nella tabella** e cade su `_default`, che vale
`{"input": 0.0, "output": 0.0}`. Quindi:

```python
# openai_compat_runner.py:426-430 — vale anche per OpenRouterRunner, che eredita
prices = _prezzo(model)                                   # -> _default, cioè zero
cost = (inp * prices["input"] + out * prices["output"]) / 1_000_000   # -> 0.0
self.total_cost_usd += cost                               # -> non cambia niente
```

Il costo totale che la pagina mostra **sotto-dichiara**, e non lo dice. Il proprietario usa
OpenRouter: è esattamente la sezione che gli interessa.

La cosa importante è che **la fonte vera esiste già**. La documentazione di OpenRouter
(*Usage Accounting*, verificata il 21/08/2026) dichiara che ogni risposta porta sempre, senza
parametri da attivare e anche in streaming (ultimo messaggio SSE):

| campo | significato |
|---|---|
| `usage.cost` | **quanto è stato addebitato davvero** sull'account |
| `usage.cost_details.upstream_inference_cost` | il costo del provider a monte |
| `usage.prompt_tokens` / `completion_tokens` | token col tokenizzatore nativo del modello |
| `usage.cached_tokens` / `cache_write_tokens` | cache letta e scritta |
| `usage.reasoning_tokens` | dove applicabile |

Non la leggiamo. Calcoliamo una stima da una tabella che non contiene il modello, e la stima è zero.

### Difetto 2 — i token dell'abbonamento esistono e nessuno può chiederli

La pagina dichiara, sul percorso abbonamento:

> *«Sul percorso abbonamento i consumi non si misurano: la chat gira sull'abbonamento Claude, che
> non espone né i token né il costo della singola risposta.»* — `api/handlers_usage.py:43-48`

È **vero sul costo e falso sui token**. Il ponte legge da ogni turno `input_tokens`,
`cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens` e `num_turns`
(`agent/runner.py:861-868`), e li scrive **in una riga di log** (`_logga_uso`, riga 992) che
nessuna porta del prodotto può interrogare.

È la fondamenta n.4 alla lettera: *se un dato c'è e nessuno può chiederlo, non esiste.*

---

## Le decisioni

Prese dal proprietario il 21 agosto 2026, in questo ordine.

| # | Domanda | Decisione |
|---|---|---|
| 1 | Cosa si conserva | **Totali per modello _e_ storia nel tempo**: archivio di consumi in `/data`, con grafico dell'andamento |
| 2 | Il costo quando un prezzo non c'è | **Cinque stati, mai uno zero per dire «non so»** — e per OpenRouter si legge il **costo reale** dalla risposta |
| 3 | Forma dell'archivio | **Un secchiello al giorno per modello**, non una riga per risposta: storia per sempre, nessuna ritenzione da governare |
| 4 | I contatori dei runner | **Escono.** L'archivio è l'unica casa. «Azzera» **sposta un'ancora** e non cancella niente |
| 5 | L'abbonamento (il ponte) | **Entra**: token misurati per modello, costo dichiarato *compreso nell'abbonamento* |

---

## 1. L'archivio — `/data/consumi.db`

Modulo nuovo `hiris/app/consumi/`, sul modello di `schedulatore/archivio.py`: `connect` e
`init_schema` da `storage.py`, un `threading.Lock`, schema versione 1.

```sql
CREATE TABLE IF NOT EXISTS consumo_giorno (
    giorno            TEXT    NOT NULL,   -- 'AAAA-MM-GG' nel FUSO DELLA CASA
    provider          TEXT    NOT NULL,   -- claude | openai | openrouter | ollama | ponte
    modello           TEXT    NOT NULL,   -- l'id vero, come l'ha chiesto il provider
    richieste         INTEGER NOT NULL DEFAULT 0,
    token_in          INTEGER NOT NULL DEFAULT 0,
    token_out         INTEGER NOT NULL DEFAULT 0,
    cache_lettura     INTEGER NOT NULL DEFAULT 0,
    cache_scrittura   INTEGER NOT NULL DEFAULT 0,
    costo_usd         REAL,               -- NULL = niente di noto. MAI 0 per dire «non so»
    costo_stato       TEXT    NOT NULL,   -- misurato|reale|gratuito|compreso|non_noto
    errori_rate_limit INTEGER NOT NULL DEFAULT 0,
    primo_ts          REAL    NOT NULL,
    ultimo_ts         REAL    NOT NULL,
    PRIMARY KEY (giorno, provider, modello)
);
CREATE INDEX IF NOT EXISTS idx_consumo_giorno ON consumo_giorno(giorno);
```

Cinque secchielli al giorno anche usando cinque modelli: **meno di duemila righe l'anno**. La
storia si tiene per sempre senza politica di ritenzione, senza crescita da sorvegliare e senza
dover mai cancellare dati dell'utente a scadenza.

### `token_in` sono i token di ingresso **puri**

Oggi la cache è nascosta dentro il totale: `claude_runner.py:961` fa
`total_input_tokens += inp + cache_creation + cache_read`, e i tre numeri diventano uno solo che
nessuno può più separare. Qui hanno tre colonne, perché costano prezzi diversi (`cache_write` e
`cache_read` hanno una tariffa propria in `pricing.py`) e perché la cache è il numero che dice se
il prefisso sta lavorando.

Conseguenza da non sbagliare in fase di somma: **il «Token IN» della pagina resta
`token_in + cache_lettura + cache_scrittura`**, cioè la stessa quantità di oggi. Sommare la sola
colonna `token_in` farebbe **crollare** il numero rispetto alla versione precedente, e sembrerebbe
una perdita di dati invece di un cambio di rappresentazione.

### Il giorno è quello della casa, non UTC

Il fuso lo sa già l'anagrafe: `ArchivioCasa.sistema_di_riferimento()` restituisce
`{fuso, valuta, lingua, paese, …}` — e **tace se non lo sa**, restituendo un dizionario senza la
chiave invece di inventarne uno (`casa/archivio.py:342-360`).

Quindi: se il fuso c'è, il giorno è quello della casa; se manca, è UTC **e la pagina lo dichiara**.
Un giorno senza il suo fuso è il `72` senza i gradi della fondamenta n.1: un frammento che chi
legge non può interpretare da solo.

### Lo stato del costo non può rafforzarsi

Lo stato è una funzione di `(provider, modello, risposta)`:

| stato | quando | `costo_usd` |
|---|---|---|
| `reale` | OpenRouter ha dichiarato `usage.cost` | il valore addebitato |
| `misurato` | il modello è in `pricing.py` (Claude API, OpenAI) | calcolato a listino |
| `gratuito` | Ollama locale, oppure modello con suffisso `:free` | `0.0` **dichiarato** |
| `compreso` | il ponte: l'abbonamento non espone il prezzo del turno | `NULL` |
| `non_noto` | nessun prezzo disponibile e nessun costo dichiarato | `NULL`, oppure la parte già nota se la riga è degradata (vedi sotto) |

Se in uno stesso giorno lo stesso modello produce chiamate di stato diverso — OpenRouter che una
volta porta `usage.cost` e una volta no — **la riga tiene lo stato più debole**. Una riga non può
mai affermare più della chiamata peggiore che contiene. La degradazione si scrive nel log: è rara,
e quando capita significa che un provider ha cambiato comportamento.

**Il costo già accumulato non si butta.** Una riga `non_noto` con `costo_usd` valorizzato non è
una contraddizione: significa *«questo l'ho pagato di sicuro, più qualcosa che non so»* — cioè
esattamente il **pavimento**, lo stesso concetto che il totale usa in cima alla pagina, applicato
a una scala più piccola. Un concetto solo, a due scale, invece di un sesto stato. Quindi:

- `non_noto` **con** `costo_usd` → la riga scrive `≥ € 0,0123`;
- `non_noto` **senza** `costo_usd` (`NULL`) → la riga scrive «Prezzo sconosciuto».

Ordine di forza, dal più debole: `non_noto` < `compreso` < `gratuito` < `misurato` < `reale`.
`reale` sta sopra `misurato` perché è un **fatto** — quanto è stato addebitato — e non una stima
da listino.

### `richieste` si chiama così anche per il ponte

Per il ponte sono turni. Il campo resta `richieste`: **stessa forma da tutte le porte**
(fondamenta n.3). È l'etichetta della pagina a dire «turni», non lo schema.

### L'ancora — «Azzera» che non cancella

```sql
CREATE TABLE IF NOT EXISTS ancora (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    da_ts REAL NOT NULL,
    da_giorno TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ancora_saldo (
    provider TEXT NOT NULL, modello TEXT NOT NULL,
    richieste INTEGER, token_in INTEGER, token_out INTEGER,
    cache_lettura INTEGER, cache_scrittura INTEGER, costo_usd REAL,
    errori_rate_limit INTEGER,
    PRIMARY KEY (provider, modello)
);
```

Premendo «Riparti da adesso» si scrive `da_ts = adesso` **e si fotografano i contatori del giorno
corrente** in `ancora_saldo` (`DELETE` + `INSERT … SELECT … WHERE giorno = oggi`).

I totali «da ultimo azzeramento» sono allora:

```
somma(giorni > da_giorno)  +  ( riga di oggi  −  saldo di oggi )
```

**Perché il saldo esiste.** Con secchielli giornalieri, un'ancora che fosse soltanto una data
lascerebbe in pagina, subito dopo l'azzeramento, il consumo già fatto stamattina — e il pulsante
sembrerebbe rotto. Il saldo non è un doppione di un fatto che vive altrove: è **la posizione
dell'ancora**, espressa nelle uniche coordinate che l'archivio possiede. Nessun altro posto la sa.

---

## 2. La misura — un solo scrittore, cinque bocche

Una funzione sola:

```python
registra(provider, modello, *, richieste=1, token_in, token_out,
         cache_lettura=0, cache_scrittura=0, costo_usd=None,
         costo_stato, errori_rate_limit=0, adesso)
```

UPSERT sulla chiave `(giorno, provider, modello)`: i contatori si sommano, `primo_ts` prende il
minimo, `ultimo_ts` il massimo, `costo_stato` degrada secondo l'ordine di forza.

Arriva ai runner **come callback iniettato** (`registra_consumo=`), esattamente come già fa
`leggi_modello`: il runner non conosce l'archivio, conosce una funzione. Per la regola non
negoziabile di `CLAUDE.md`, **il nuovo kwarg lo accettano entrambi** — `ClaudeRunner` e
`OpenAICompatRunner` — o i backend non-Claude si rompono in silenzio.

| Bocca | Punto d'innesto | Cosa cambia |
|---|---|---|
| Claude API | `claude_runner.py:957-971` | i token ci sono già; si aggiungono il nome del modello (`effective_model`, già in mano) e la scrittura. `costo_stato = misurato` |
| OpenAI | `openai_compat_runner.py:403-431` (`_track_usage`) | idem; il provider viene da un nuovo attributo `self.provider_nome` |
| **OpenRouter** | stesso punto | si legge **`usage.cost`** dalla risposta → `costo_stato = reale`. Se il campo manca: `non_noto`, mai zero |
| Ollama e `:free` | stesso punto | `costo_stato = gratuito`: uno zero **dichiarato** |
| **Ponte** | `agent/runner.py:992` (`_logga_uso`) | gli stessi numeri che oggi finiscono solo nel log vanno anche all'archivio. `costo_stato = compreso` |

`provider_nome` è un attributo di classe sovrascritto da `OpenRouterRunner` e impostato a
`"ollama"` quando `locale=True`. Serve perché `type(runner).__name__` **non distingue** OpenAI da
OpenRouter — il secondo è una sottoclasse del primo, e un consumo di OpenRouter finirebbe scritto
sulla riga di OpenAI. È lo stesso difetto che `_ordered_backends_con_nome` (`llm_router.py:161`)
è già stato scritto per evitare nel registro degli esiti, e per la stessa ragione.

I rifiuti 429 (`total_rate_limit_errors`, tre punti d'incremento) finiscono sulla riga del modello
che li ha presi. Oggi sono un numero solo, e non dicono **chi** sta rifiutando.

### Un punto che va verificato dal vivo, non letto

Per il ponte, il modello che HIRIS **chiede** è un alias (`agent/runner.py:1180`:
`model = context.get("model") or "sonnet"`), non un identificativo. La CLI pinnata
(`@anthropic-ai/claude-code@2.1.234`, `Dockerfile:34`) potrebbe dichiarare nell'evento `result` il
modello **vero**, e forse una ripartizione per-modello già pronta.

Non è verificato: la documentazione online rimbalza su una catena di redirect e i fixture dei test
(`tests/test_flusso_stream_json.py`, `test_strumenti_al_ponte.py`) sono **scritti a mano**, quindi
provano cosa il codice legge, non cosa la CLI emette.

**Primo task del piano:** un turno vero del ponte, si guardano le chiavi dell'evento `result`.
Vince quello che dice lui. Se il modello vero non c'è, si registra l'alias e la pagina lo dichiara
come alias invece di farlo passare per un identificativo.

---

## 3. L'API — due domande, due rotte

### `GET /api/usage` resta la rotta leggera

I campi attuali **non cambiano**. Non è cortesia verso il passato: il riquadro «Utilizzo» della
chat richiama questa rotta a intervalli (`static/config/api.js:102-124`) e legge `misurata`,
`total_requests`, `input_tokens`, `output_tokens`, `cost_eur`, `last_reset`, `messaggio`.
Appesantirla con trenta giorni di serie storica farebbe pagare a ogni giro della chat una domanda
che la chat non fa.

Si aggiunge solo il dettaglio già aggregato:

```json
{
  "misurata": true,
  "total_requests": 1204, "input_tokens": 8300000, "output_tokens": 412000,
  "cost_usd": 26.28, "cost_eur": 24.18,
  "costo_parziale": true,
  "fuso": "Europe/Rome", "fuso_noto": true,
  "rate_limit_errors": 3,
  "last_reset": "2026-07-14T09:22:00Z",
  "sezioni": [
    { "provider": "claude", "etichetta": "API Anthropic",
      "nota": "Costo calcolato sul listino Anthropic.",
      "costo_parziale": false, "costo_usd": 22.87, "costo_eur": 21.04,
      "richieste": 1181, "token_out": 408000,
      "token_in": 3650000, "cache_lettura": 4250000, "cache_scrittura": 310000,
      "modelli": [
        { "modello": "claude-sonnet-4-6", "richieste": 980,
          "token_in": 2600000, "token_out": 380000,
          "cache_lettura": 4200000, "cache_scrittura": 310000,
          "costo_usd": 20.78, "costo_eur": 19.12, "costo_stato": "misurato",
          "errori_rate_limit": 3,
          "primo_uso": "2026-08-02", "ultimo_uso": "2026-08-21" }
      ] }
  ]
}
```

`costo_parziale` è il campo che impedisce alla pagina di ricominciare a mentire, stavolta in
grande: se anche un solo modello è `non_noto`, **il totale non è il costo, è un pavimento**.

**Un solo nome per l'istante dell'ancora: `last_reset`.** Il nome è quello che la chat già legge,
il significato è nuovo — non «quando ho cancellato» ma «da quando conto». Chiamarlo `ancora` e
lasciare anche `last_reset` sarebbe stato lo stesso fatto in due case (fondamenta n.2), e prima o
poi una delle due avrebbe mentito. Cambia invece **l'etichetta** che la chat gli mette davanti:
non più «Azzerato il», ma «Conta da» (`static/config/api.js:118`).

**`token_in` è puro, `input_tokens` è inclusivo.** Nelle sezioni e nelle righe, `token_in` sono i
soli token d'ingresso e la cache ha i suoi due campi. In cima, `input_tokens` resta la somma di
tutti e tre, che è la quantità che la pagina e la chat mostrano oggi. Due nomi diversi perché sono
due quantità diverse: lo stesso nome per entrambe sarebbe la fondamenta n.3 violata da dentro la
stessa risposta.

### `GET /api/usage/storia?da=&a=`

Le righe giornaliere per il grafico. Ha una rotta propria perché è una **domanda diversa, con
parametri suoi**: un oggetto che si sa interrogare da solo (fondamenta n.4), non un allegato del
riepilogo. Default: ultimi 30 giorni.

### `POST /api/usage/reset`

Tiene il nome — i chiamanti esistono — e cambia significato: **sposta l'ancora**, risponde
`{"last_reset": …, "cancellato": false}` (stesso nome della rotta di lettura: un fatto, un nome).

Il `409` di oggi («azzerare un contatore che non esiste è una richiesta in conflitto con lo stato
della risorsa») **esce**: con l'archivio c'è sempre un'ancora da spostare.

`misurata: false` sopravvive per **un caso solo e vero**: nessun provider configurato e nessuna
riga nell'archivio, cioè non è mai stato usato niente. Il ramo «abbonamento» esce da lì insieme a
`_MSG_ABBONAMENTO`: l'abbonamento adesso si misura, e ha una sezione sua.

---

## 4. La pagina — `#/usage`

Disegnata con l'audit di `ux-ui-specialist` del 21/08/2026 (regola di `CLAUDE.md`: il frontend si
interpella prima di disegnare, non dopo).

```
Consumi                          [ da ultimo azzeramento │ da sempre ]  [Riparti da adesso]
                                            Non cancella niente: sposta solo il punto da cui contare.

  ≥ € 24,18            1.204 richieste          8,30M IN            412,0k OUT
  cifra minima — manca
  il prezzo di un modello

  Costo al giorno                                        [ 7 giorni │ 30 giorni ]
  €  ┤                    ▁▃█
     ┤            ▂▅██████████        ■ API Anthropic   ■ OpenRouter
     ┤   ▁▃▅█████████████████████
     └────┬─────────┬──────────┬──    23 lug → 21 ago · fuso Europe/Rome
        23 lug     6 ago     21 ago
  L'abbonamento non compare qui: non ha un costo da impilare. I suoi turni sono nel grafico sotto.

  Richieste al giorno
     ┤   ▂▄▆████▇█████▆████▇█████     ■ API Anthropic  ■ OpenRouter  ■ Abbonamento

  ▸ I numeri del grafico            ← <details class="usage-section">, tabella equivalente

  API Anthropic                                                            € 21,04
  Costo calcolato sul listino Anthropic.
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ claude-sonnet-4-6                                                   € 19,1183 │
  │ 980 richieste · 7,10M IN · 380,0k OUT · cache 4,20M letti / 310,0k scritti    │
  │ dal 02/08 al 21/08 · 3 rifiuti per limite di frequenza                        │
  └──────────────────────────────────────────────────────────────────────────────┘

  OpenRouter                                                                € 3,14
  Costo dichiarato da OpenRouter: è quanto è stato addebitato, non una stima.
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ anthropic/claude-sonnet-4-6                                          € 3,1402 │
  │ 18 richieste · 88,0k IN · 3,9k OUT · dal 19/08 al 21/08                       │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │ meta-llama/llama-3.3-70b-instruct:free                              Gratuito  │
  │ 5 richieste · 22,0k IN · 1,1k OUT · dal 20/08 al 20/08                        │
  └──────────────────────────────────────────────────────────────────────────────┘

  Abbonamento Claude                                    Compreso nell'abbonamento
  L'abbonamento non espone il prezzo del singolo turno. I token sì, e sono questi.
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ sonnet                                               Compreso nell'abbonamento│
  │ 128 turni · 2,10M IN · 94,0k OUT · cache 1,40M letti / 210,0k scritti         │
  └──────────────────────────────────────────────────────────────────────────────┘
```

### I cinque stati si distinguono per tipografia, non per pastiglie colorate

Non sono cinque varianti della stessa cosa: sono **due numeri veri e tre non-numeri di natura
diversa**. Cinque pastiglie colorate li appiattirebbero di nuovo, stavolta con più colore.

| stato | cosa compare | trattamento |
|---|---|---|
| `misurato` | `€ 19,1183` | `--text`, `tabular-nums` |
| `reale` | `€ 3,1402` | identico: sono entrambi numeri, e la differenza si dichiara altrove |
| `gratuito` | **Gratuito** | parola, `--text-2`. Mai `€ 0,00` |
| `compreso` | **Compreso nell'abbonamento** | `--text-3`: assenza neutra, niente da fare |
| `non_noto` | **Prezzo sconosciuto**, oppure `≥ € 0,0123` se una parte del costo è nota | `--warn-ink`: assenza che chiede attenzione |

**Mai `—` per un costo.** In questa pagina il trattino significa già «sto caricando»
(`fmtNum`/`fmtEuro` lo restituiscono su `null`, `config/api.js:20-30`), e riusarlo per «non lo so»
rifarebbe in piccolo lo stesso errore che questa fetta esiste per togliere.

La differenza fra `misurato` e `reale` **si dichiara una volta per sezione**, nella `.sc-desc`
sotto il titolo del provider — «costo calcolato sul listino» contro «costo dichiarato da
OpenRouter: è quanto è stato addebitato, non una stima» — e non riga per riga: i due stati non
convivono mai nella stessa sezione, perché è il provider a determinarli.

### Il totale-pavimento

`≥ € 24,18` da solo è criptico per chi apre la pagina dal telefono. Il simbolo resta, ma **sempre
accompagnato** dalla frase, nello stesso `.st-delta` del riquadro, in `--warn-ink`:
*«cifra minima — manca il prezzo di almeno un modello»*.

### Due grafici, non uno

- **Costo al giorno** — barre impilate, **solo API Anthropic e OpenRouter**. Il ponte non ha un
  costo da impilare, e la sua assenza si **dichiara in una riga sotto il grafico** invece di
  lasciarlo sparire in silenzio.
- **Richieste al giorno** — barre impilate, **tutti** i provider, ponte compreso. È il grafico che
  risponde a «quanto sto usando cosa» anche dove il costo non esiste.
- **Nessun terzo grafico per i token**: il dettaglio dei token vive già in ogni riga.

**I colori dei provider non riusano `--ok`/`--warn`/`--err`.** In HIRIS quei tre significano già
riuscito / incerto / fallito (le pastiglie di Modelli e Promesse): un provider colorato `--warn`
si leggerebbe come «in stato di allerta». Serve una **palette qualitativa nuova** — quattro
tinte, una per provider — dichiarata coi token del tema in `hiris-theme.css`, chiaro e scuro, e
verificata a **3:1 sul fondo** (soglia degli oggetti grafici non testuali, non 4,5:1 che vale per
il testo). La legenda non è solo colore: porta il nome del provider accanto al quadratino.

**Mobile.** Trenta barre giornaliere su un telefono via Ingress sono illeggibili: la risposta è un
interruttore **7 giorni / 30 giorni**, non uno scorrimento orizzontale del grafico.

**Accessibilità.** L'SVG porta `<title>` e `<desc>`, e sotto ogni grafico c'è
`<details class="usage-section">` — «I numeri del grafico» — con la **tabella equivalente**. È
qui che il CSS orfano `.usage-section` torna vivo: risolve l'accessibilità dell'SVG senza
inventare un secondo componente.

### Le sezioni per provider

**Aperte, tutte, sempre.** È una pagina a bassa frequenza di visita il cui unico scopo è la
trasparenza: nascondere il dettaglio dietro un clic la contraddice. Compaiono solo i provider che
hanno almeno una riga — è il «al primo utilizzo si attiva» del proprietario, e l'assenza di OpenAI
è un'**assenza**, non uno zero.

Ogni modello è una **card a tre righe**, con lo stesso markup a ogni ampiezza (non tabella che
diventa card):

```html
<div class="usage-model-row">
  <div class="umr-top">  <span class="umr-nome">claude-sonnet-4-6</span>
                         <span class="umr-costo">€ 19,1183</span></div>
  <div class="umr-meta"> 980 richieste · 7,10M IN · 380,0k OUT · cache 4,20M / 310,0k</div>
  <div class="umr-foot"> dal 02/08 al 21/08 · 3 rifiuti per limite di frequenza</div>
</div>
```

Il nome del modello va in **monospace**: è la convenzione già stabilita nella pagina Modelli per
alias e identificatori. I **rifiuti 429 compaiono solo se maggiori di zero** — omissione dello
stato-non-evento, convenzione ricorrente del prodotto.

### Il pulsante che non distrugge

Oggi è `btn btn-danger`, porta l'icona `↺` e la conferma dice *«L'operazione è irreversibile»*:
comunica distruzione. Il comportamento nuovo sposta un'ancora. **Vanno cambiati tutti e tre i
fronti insieme**, o il pulsante mente in un'altra direzione:

- classe **`.btn-ghost`** — il vocabolario HIRIS per le azioni leggere;
- nome **«Riparti da adesso»**, collocato **accanto all'interruttore** «da ultimo azzeramento │ da
  sempre», non isolato in fondo alla pagina: è la stessa domanda, *da quando conto*;
- **niente `window.confirm()`** — stesso principio di «disdici» nelle Promesse: un gesto non
  distruttivo e reversibile dall'interfaccia stessa (basta spostare l'interruttore su «da sempre»)
  non merita un blocco modale. Al suo posto una frase sempre visibile sotto il pulsante — *«Non
  cancella niente: sposta solo il punto da cui contare»* — e il riscontro immediato nei valori.

### Due difetti di formattazione, preesistenti, che questa fetta deve chiudere

Vivono in `fmtEuro` (`static/config/api.js:27-30`) e non sono cosmetici:

```javascript
function fmtEuro(n) {
  if (n == null) return '—';
  return '€ ' + Number(n).toFixed(2);   // ← due difetti in una riga
}
```

1. **`toFixed(2)` ricrea lo zero bugiardo a livello di riga.** Un modello che è costato tre
   decimillesimi di euro verrebbe scritto `€ 0.00`: esattamente la bugia che l'intera fetta esiste
   per togliere, rientrata dalla porta della formattazione. Le righe vogliono **fino a quattro
   decimali**; il totale ne tiene due.
2. **`toFixed` non conosce la lingua** e produce il separatore col **punto**: `€ 24.18` in una
   pagina dove la data accanto è formattata `toLocaleString('it-IT')`. Difetto preesistente, non
   introdotto qui — e questa è la fetta che lo incontra.

`fmtEuro` è **condivisa col riquadro della chat**: sistemarla la sistema in tutti e due i posti,
che è il punto di averla in `api.js` (fondamenta n.3).

---

## 5. Cosa esce — la fetta è anche pulizia

| Esce | Perché |
|---|---|
| `usage.json`, `usage_openai.json`, `usage_openrouter.json`, `usage_ollama.json` | seconda casa dello stesso fatto. **Importati una volta** come riga `(prima del dettaglio)` datata all'ultimo azzeramento, poi non più scritti. I file restano sul disco: mai dati dell'utente cancellati in silenzio |
| In **due** runner: `total_input_tokens`, `total_output_tokens`, `total_requests`, `total_cost_usd`, `total_rate_limit_errors`, `usage_last_reset`, `reset_usage`, `_load_usage`, `_save_usage`, `_save_lock` | ~180 righe, con i commenti storici su `per_agent` e sulla lettura-modifica-scrittura che li giustificavano |
| Le sei proprietà aggreganti di `LLMRouter` (`llm_router.py:313-345`) | sommavano ciò che non esiste più |
| `_MSG_ABBONAMENTO` e il ramo `abbonamento` di `_non_misurata` | l'abbonamento adesso si misura |
| `.usage-panel` in `hiris-config.css` (×2 blocchi) e `hiris-config-override.css` | orfano verificato: zero riferimenti in JS e in HTML |
| Il `window.confirm()` e la classe `btn-danger` della pagina, con la frase «L'operazione è irreversibile» | descrivono una distruzione che non avviene più |
| I test che difendono i contatori dei runner | anche i test si smontano, insieme a ciò che testavano |

`.usage-section` **non** esce: è CSS oggi orfano (reliquia della tabella «Per Chatbot» rimossa
alla fetta E5) che le nuove sezioni per provider riusano. Morto e scollegato non sono la stessa
cosa: il primo si toglie, il secondo si collega.

`_prezzo` e `pricing.py` **restano**: servono allo stato `misurato`.

---

## 6. Come si prova

TDD, con la disciplina che questo progetto ha già pagato: **la finta deve saper produrre il
difetto.** Una finta di OpenRouter senza `usage.cost` deve far comparire `non_noto`; se le tolgo
il campo e il test resta verde, quel test non vale niente. Si verifica per mutazione, non per
fiducia.

**Python**

- Archivio: UPSERT che somma, `primo_ts`/`ultimo_ts`, giorno calcolato nel fuso della casa (e in
  UTC quando l'anagrafe tace), stato che **degrada e non si rafforza**, ancora + saldo che porta
  davvero a zero senza cancellare una riga.
- Le cinque bocche: ogni runner scrive la riga giusta col provider giusto — in particolare
  OpenRouter **non** deve finire sulla riga di OpenAI.
- OpenRouter: `usage.cost` presente → `reale`; assente → `non_noto` con `costo_usd` a `NULL`.
- Le tre rotte: sezioni, storia, `misurata: false` nel solo caso vero, reset che sposta l'ancora.
- L'importazione dei quattro `usage_*.json`: una volta sola, idempotente, e i file restano.

**JavaScript** (`node --test` + jsdom, test comportamentali)

- Le sezioni compaiono solo per i provider usati (OpenAI mai usato → la sezione **non esiste**,
  non esiste a zero).
- I cinque stati del costo mostrano parole diverse; `non_noto` non mostra mai `€ 0,00` e non
  mostra mai `—`.
- `fmtEuro`: un costo di `0,0003` **non** diventa `€ 0,00` sulla riga, e il separatore decimale è
  la **virgola**. È il test che difende la fetta dal proprio rientro: la bugia che togliamo dai
  dati non deve tornare dalla formattazione.
- I due grafici con zero giorni non esplodono; l'interruttore 7/30 giorni cambia ciò che si vede.
- Il pulsante non apre nessun `confirm()`, e dopo il clic i valori cambiano da soli.
- Il riquadro «Utilizzo» della chat continua a funzionare con la risposta nuova.

**Poi**

- Bump di versione, o i client non si aggiornano.
- **Verifica live** sull'add-on vero (`192.168.1.95:8099`): la suite verde non è una prova. I bug
  di questo progetto emergono eseguendo, non leggendo.
- Review dell'intero ramo, non del solo diff: *cosa ho lasciato orfano?* — con
  `python scripts/censimento.py`.

---

## Cosa questa fetta NON fa

- **Non tiene un evento per risposta.** Non si potrà dire «quanto è costata questa
  conversazione». Il secchiello giornaliero risponde a tutto ciò che la pagina chiede, e non
  obbliga a decidere una ritenzione né a cancellare dati a scadenza.
- **Non aggiunge prezzi a `pricing.py`.** Una tabella di listino mantenuta a mano invecchia in
  silenzio; per OpenRouter il costo reale arriva dalla risposta, e dove non c'è si dice `non_noto`.
- **Non mostra il costo equivalente dell'abbonamento** (quanto sarebbe costato lo stesso traffico
  via API). Scartato dal proprietario insieme al rischio che portava: un euro mai pagato scritto
  accanto a euro pagati davvero.
- **Non tocca la scelta del modello né la catena**: quella è la pagina Modelli, e resta l'unica
  verità su chi risponde.
