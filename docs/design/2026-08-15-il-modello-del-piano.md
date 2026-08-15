# Il modello del piano — e l'elenco che Anthropic pubblica davvero

**Data:** 2026-08-15 · **Ramo:** `2.0` · **Versione di partenza:** 3.1.0 (`5b79374`)
**Pagina toccata:** `#/models` · **Spec che questa continua:**
`2026-08-13-modelli-e-catena.md`, `2026-08-13-progetto-pagina-modelli.md`

---

## 0. I due fatti misurati che fanno esistere questa fetta

Non dedotti dal codice: letti sull'impianto vero il 15 agosto 2026, versione 3.1.0,
build `1532e48815f1`.

**(1) Il piano paga per il modello migliore e gira col più debole.**
`GET /api/models/config` restituisce `adesso.chi = "subscription"`, `adesso.modello = "haiku"`,
e `provider_models.claude = "claude-haiku-4-5-20251001"`. Il ponte è acceso, il Piano Claude Max
risponde per primo — con `haiku`, perché quel valore **non è suo**: è il modello di *Claude API*,
e `handlers_chat.py:383` lo compone in `modello_cli(resolve_model("auto", "chat",
provider_models["claude"]))`.

Un campo solo serve due economie opposte. Su Claude API si paga a token, e `haiku` è la scelta
frugale. Sul piano il modello **non costa niente in più**, e `opus` è la ragione per cui il piano
esiste. Il valore è giusto per uno e sbagliato per l'altro, e **non c'è modo di dire due cose
diverse.**

`GET /api/models?provider=subscription` risponde `"dove": []`. Il frontend calcola
`scrivibile = false` (`models-route.js:614`) e **disabilita i tre radio**. Non è un guasto: è la
decisione del Task 9, presa quando il modello del piano era davvero un effetto collaterale e un
controllo che non salva sarebbe stato peggio di un controllo spento. La decisione era corretta per
il prodotto di allora. Il difetto è a monte: **il piano non ha un valore proprio.**

**(2) La pagina dice una cosa falsa su Anthropic.**
`handlers_models.py:838` — *«Anthropic non espone un endpoint pubblico»* — e la provenienza che
l'utente legge — *«Anthropic non pubblica un elenco: questi sono i modelli che HIRIS conosce»*.

**`GET https://api.anthropic.com/v1/models` esiste.** Verificato sulla documentazione ufficiale
(`platform.claude.com/docs/en/api/models/list`), non dedotto: header `x-api-key` +
`anthropic-version`, paginato (`limit` 1–1000, default 20), ordinato dai più recenti, e ogni voce
porta `id`, `display_name`, `created_at`, `max_input_tokens` e `capabilities`. Vuole una **chiave
API**: non funziona col token del piano.

Quindi `_CLAUDE_MODELS` è una lista di tre nomi scritta a mano che invecchia da sola, presentata
come se fosse tutto ciò che esiste.

Le due cose stanno nello stesso pannello e sotto lo stesso contratto `(valori, fonte)`: chi tocca
una riapre comunque l'altra.

---

## 1. Il principio

**Il piano ha un modello suo.** Non derivato, non condiviso, non ricalcolato: un valore
nell'archivio, scelto dalla riga del piano, letto dal ponte.

E la derivazione non sparisce: **diventa una semina** (si esegue una volta, il giorno
dell'aggiornamento) **e un validatore** (riduce ai tre alias ciò che non lo è). La stessa funzione,
`modello_cli`, cambia mestiere invece di essere cancellata — e passa da due chiamanti a uno.

---

## 2. Il dato

`ponte.modello`: una stringa fra esattamente **tre** — `haiku` · `sonnet` · `opus`.

Vive in `ponte` e non in `provider_models`, per il precedente che il codice ha già:
il modello di Ollama sta in `ollama.modello`, e §0.6 del progetto chiama
`provider_models["ollama"]` *«un fantasma, non un doppione»*. Il piano è lo stesso caso, e c'è una
prova più forte: `_enqueue_chat_job` legge **già** `models_config["ponte"]["scadenza_min"]`
(`handlers_chat.py:335`) e `models_config["ponte"]["tetto_giornaliero"]` (`:250`). Il modello
diventa il terzo valore letto dallo stesso dizionario nello stesso punto.

**Alternative scartate.** `provider_models["subscription"]`: quel sacchetto contiene
*identificatori* (`claude-opus-4-7`, `gpt-4o`), il piano contiene un *alias* — la distinzione che
la pagina fa col carattere (`e_alias`) — e `_clean_provider_models` accetta qualunque stringa,
quindi servirebbe un `if k == "subscription"` dentro la funzione che esiste per non avere casi
particolari. Una chiave piatta `modello_del_piano`: terza forma per lo stesso concetto.

**Predefinito: `"sonnet"`, mai la stringa vuota.** Vuoto significherebbe «non so», e «non so» è la
porta da cui la regola *se non so niente allora fai come prima* è già rientrata **quattro volte**
in questa base di codice (`project_hiris_provider_e_catena`). Il campo nasce con un valore.

**Pulizia in `_pulisci_ponte`**, accanto ai due `_clamp_int` e con la loro stessa regola: un valore
fuori dai tre **si riporta dentro**, non fa fallire la PUT. Il riduttore è `modello_cli`, che qui
trova la sua unica casa.

---

## 3. La semina

**Segno proprio: `piano_seminato`**, in `_SEGNI_MIGRAZIONE` accanto a `seminato` e
`catena_seminata` — quindi fuori da `_CHIAVI_NOSTRE`, quindi **nessun client lo può rimettere a
`false`** con una PUT. La ragione è scritta nel codice esistente: un segno riscrivibile fa rigirare
la migrazione al riavvio successivo, e la migrazione ricopre le decisioni dell'utente.

All'avvio, se il segno manca:

```
ponte.modello = modello_cli(resolve_model("auto", "chat", provider_models["claude"]))
piano_seminato = True
```

cioè **la derivazione di oggi, calcolata l'ultima volta**. Sull'impianto del proprietario: `haiku`.
Niente cambia sotto di lui il giorno dell'aggiornamento; da lì in poi il valore è suo.

Il segno **si scrive sempre**, anche quando il valore coincideva col predefinito: è ciò che rende
la semina un evento che accade una volta e non una condizione che si rivaluta a ogni avvio.
**La guardia è il segno, non la forma del valore** — la lezione scritta per esteso in
`semina_catena`, dove regolarsi su «`chain_order` è vuota» faceva ripopolare al riavvio una catena
svuotata di proposito.

Il blocco vive in `server.py` accanto a quello di `semina_catena`, con un `save_models_config(...,
segni=True)` proprio. Due scritture su un avvio di aggiornamento invece di una: accettato, perché
fondere le due semine in un salvataggio solo le renderebbe una migrazione sola che può trovarsi a
metà, che è esattamente ciò che i segni distinti esistono per evitare.

A differenza di `semina_catena`, questa semina **non legge una regola in via di sparizione**:
`provider_models["claude"]` resta vivo (è il modello di Claude API). È il segno, e solo il segno,
a renderla irripetibile.

---

## 4. Chi legge, e chi smette di calcolare

**Un solo lettore vero.** `handlers_chat._enqueue_chat_job:383`:

```python
# prima
"model": modello_cli(resolve_model("auto", "chat", provider_models["claude"]))
# dopo
"model": models_config["ponte"]["modello"]
```

Nessun calcolo al momento del turno.

**Il lettore gemello.** `_modelli_in_uso["subscription"]` (`handlers_models.py:393`) legge **lo
stesso campo** invece di rifare la stessa composizione in un altro file. Si passa da *due calcoli
identici* a *un campo letto due volte* — e la firma di `_modelli_in_uso` guadagna il modello del
piano accanto a quello di Ollama, che è già lì per la stessa ragione.

**Il commento che diventa falso.** `handlers_models.py:838-844` giustifica oggi una scelta con
*«su un'installazione col solo Piano Claude Max questo è l'UNICO posto da cui si sceglie il modello
del piano»*. Da questa fetta è falso e va tolto — insieme al ramo che giustificava (§6).

**`modello_cli` scende a un chiamante**, `_pulisci_ponte`. Non si cancella: resta utile
esattamente per i casi che restano — un `models_config.json` scritto a mano, e il valore della
semina.

---

## 5. La pagina

Il disegno del Task 9 si incassa qui. La riga che accende tutto sta in `decisione_modelli`:

```python
_DOVE_SI_SCRIVE["subscription"] = ("ponte", "modello")   # era: ()
```

`dove` smette di essere vuoto → `scrivibile` diventa vero → i tre radio si abilitano,
`scegliModello` scrive `state.cfg.ponte.modello`, la PUT lo porta perché `ponte` è già in
`_CHIAVI_NOSTRE`, e la pagina rilegge. Verificato riga per riga: `models-route.js:614`, `:676-694`,
`:1010-1012`.

### 5.1 Il controllo che sembrerebbe funzionare — e il campo nuovo

Con `scrivibile` vero compare **anche il campo di testo libero**, perché nel pannello filtro e
campo sono la stessa cosa (`corpoPannello`, `models-route.js:557-570`). Sul piano vorrebbe dire
incollare `gpt-4o`, vederlo comparire come voce «scritto da te», salvarlo — e `_pulisci_ponte` lo
ridurrebbe a `sonnet` con un `log.warning` che nessuno legge.

**Un controllo abilitato che non fa quello che dice**: la cosa che il commento a
`models-route.js:614` dichiara di voler evitare, rientrata dalla porta opposta.

Nasce quindi un campo nel payload di `componi_pannello`:

> **`elenco_completo: bool`** — «questi sono tutti i valori che esistono, non c'è niente da
> cercare altrove». Vero per il piano, falso per gli altri quattro. Il filtro si disegna solo
> quando è falso.

**Non si deriva da `alias`**, benché oggi coincidano. `alias` dice *di che natura è il valore* (e
decide il carattere della riga); `elenco_completo` dice *se l'insieme è chiuso*. Sono due
affermazioni diverse che oggi capitano di essere entrambe vere sullo stesso provider, e un giorno
un provider potrebbe avere un elenco chiuso di identificatori veri. **Possono divergere, ed è
dichiarato.**

È **l'unica** riga di JavaScript che cambia meccanismo.

### 5.2 Le frasi

`spiegazione("subscription")` oggi dice *«Quale dei tre sia in uso segue il modello di Claude API,
e si sceglie lì»*. Diventa **falsa nel momento esatto in cui la fetta funziona**. Va riscritta su
ciò che resta vero: sono alias, seguono il modello corrente del piano invece di puntare a una
versione fissa, e sul piano il modello non costa di più.

I due literal di default `ponte: {attivo, scadenza_min, tetto_giornaliero}` in `models-route.js`
(`:140` e `:1011`) prendono `modello: 'sonnet'`. Contabilità, non meccanismo.

`provenienza(... "fissa")` resta vera com'è e non si tocca.

---

## 6. L'elenco vivo di Claude API — due casi particolari **tolti**

### 6.1 La quarta sorella

`_fetch_claude_models(api_key) -> tuple[list[str], str]`, con la forma esatta di
`_fetch_openai_models`:

- `GET https://api.anthropic.com/v1/models?limit=100`
- header `x-api-key: <chiave>` e `anthropic-version: 2023-06-01`
- `aiohttp.ClientTimeout(total=5)`
- 200 con voci → `([m["id"] for m in data["data"]], "viva")`, **nell'ordine che l'API dà** (più
  recenti per primi, lo dichiara la documentazione). Nessuna curatela: a differenza di OpenAI qui
  non c'è rumore da filtrare, e a differenza di OpenRouter l'elenco è corto.
- 200 con `data` vuoto (nessuna voce da mostrare), non-200, eccezione → `(_CLAUDE_MODELS,
  "riserva")` + `logger.warning`. Una risposta riuscita che non contiene nessun modello non è una
  lettura riuscita: la stessa regola già scritta in `_fetch_openai_models`.

`server.py` guadagna `app["claude_api_key"] = api_key` accanto a `app["openai_api_key"]` e
`app["openrouter_api_key"]` (`:1981-1982`): oggi quella chiave è una locale di `:1273` e non arriva
mai nell'app.

### 6.2 Due rami che si cancellano

**In `provenienza`**, il ramo `if provider_id == "claude"` sparisce. Cadendo nel percorso generico
produce già le due frasi giuste — serve solo una riga in `_OSPITI`:
`"claude": "api.anthropic.com"`.

**In `leggi`** (`handlers_models.py:838`), il ramo che dava a Claude un elenco **anche senza
chiave** perde la sua ragione, che era scritta lì: serviva al piano. Claude API diventa uguale a
OpenAI e OpenRouter — **senza chiave → `"assente"`**.

### 6.3 La perdita, dichiarata

Senza chiave API non si potranno più sfogliare i modelli di Claude API. Erano voci inerti (senza
chiave quel provider non entra in catena) e da questa fetta non servono più al piano. **Ma è una
capacità che oggi c'è e domani no**, e sta scritta qui perché non passi in silenzio.

---

## 7. Le prove

Ogni prova deve poter **produrre** il difetto che dice di impedire, e si convalida **per
mutazione**: si rompe di proposito il codice che difende e si verifica che cada. Undici prove nuove
e una riscritta.

**Il valore e la sua indipendenza**

1. `ponte.modello = "opus"` con `provider_models.claude = "claude-haiku-4-5-20251001"` → il job del
   ponte porta `"opus"`. *Mutazione:* rimetti la composizione vecchia.
2. La semina copia il valore vero **una volta sola**: archivio senza segno e
   `provider_models.claude` haiku → `ponte.modello == "haiku"` e `piano_seminato is True`; poi
   scegli `"opus"`, cambia Claude API in un opus, riavvia → resta `"opus"`. *Mutazione:* guardia
   sulla forma del valore invece che sul segno.
3. Una PUT con `piano_seminato: false` non tocca il disco. *Mutazione:* aggiungilo a
   `_CHIAVI_NOSTRE`.
4. Una PUT con `ponte.modello = "gpt-4o"` si riporta dentro ai tre e non fallisce. *Mutazione:*
   togli la riduzione da `_pulisci_ponte`.

**La pagina**

5. I tre radio del piano sono **abilitati**. *Mutazione:* rimetti `_DOVE_SI_SCRIVE["subscription"]`
   a `()`.
6. Il filtro **non** si disegna quando `elenco_completo` è vero, **sì** quando è falso.
   *Mutazione:* togli la guardia.
7. `spiegazione("subscription")` non nomina più Claude API. *Mutazione:* rimetti il testo vecchio.

**L'elenco vivo**

8. `_fetch_claude_models` nei quattro casi — 200 con voci (`"viva"`, ordine dell'API), 200 vuoto,
   non-200, timeout (tutti `"riserva"`) — con la stessa forma delle prove di `_fetch_openai_models`.
9. Senza chiave, `claude` risponde `"assente"` e il pannello dice «manca la chiave».
10. `provenienza("claude", "riserva")` nomina `api.anthropic.com`. *Mutazione:* togli la riga da
    `_OSPITI` e il testo nomina «Claude API».

**L'eredità**

11. `tests/test_modello_del_ponte.py` **si riscrive, non si cancella**: oggi inchioda la regola
    vecchia (`modello_cli` + `resolve_model` a monte), e va a inchiodare l'indipendenza e il
    validatore.
12. L'invariante `ALIAS_DEL_PIANO` ≡ ciò che il validatore accetta (oggi a
    `test_invarianti_modelli.py:317`) si estende al campo nuovo: le due liste non possono divergere.

**Cancelli di fine fetta:** suite Python e JS interamente verde in **foreground**, censimento a
**0 opzioni non lette**, e nessuna prova che passi ancora dopo la sua mutazione.

---

## 8. Cosa NON entra, e perché

1. **`display_name`, `created_at` e `capabilities`** che l'API di Anthropic ora restituisce.
   Portarli a schermo vuol dire cambiare la firma di `componi_pannello` da `valori: list[str]` a
   una lista di coppie, e quindi toccare **tutti e quattro** i lettori. Guadagno reale
   (`claude-opus-4-6` · «Claude Opus 4.6»), costo sparso: fetta sua.
2. **`claude_runner.py:362`**, `_THINKING_CAPABLE_PATTERNS`: indovina per sottostringa quali
   modelli reggono l'extended thinking, mentre `capabilities.thinking.supported` **lo dice**.
   È lo stesso difetto di famiglia — una lista scritta a mano al posto di un fatto leggibile — e va
   chiuso, ma non insieme a questo.
3. **La paginazione dell'elenco Anthropic.** `limit=100` su una prima pagina copre il catalogo
   reale con margine. Seguire `has_more` per un elenco che non arriva a cento voci sarebbe codice
   che non si può provare col vero.
4. **Un modello per il piano diverso da quello della chat** (per il resoconto, per la sentinella).
   Quei percorsi non girano in 2.0. Un secondo campo oggi sarebbe un'opzione senza lettori.
5. **Collassare i due rami di `_config_has_credential("claude")`** (`CLAUDE_API_KEY` in ambiente
   *oppure* `claude_runner is not None`). Sembrano equivalenti e probabilmente lo sono, ma
   «probabilmente» non basta per toccare una misura di credenziale: si annota, non si tocca.

---

## 9. Il metro della fetta, dal vivo

Non è verde la suite: è l'impianto. Dopo l'aggiornamento, sull'installazione vera:

1. `GET /api/models/config` → `ponte.modello` esiste e vale **`haiku`** (il valore seminato), e
   `adesso.modello` dice `haiku`. **Niente è cambiato sotto di lui.**
2. Nella pagina Modelli, riga **Piano Claude Max** → il modello si clicca, i tre radio sono
   **accendibili**, si sceglie `opus`, la pagina rilegge e la frase in cima dice *«…con opus, nel
   piano»*.
3. Un messaggio in chat, e nel log del ponte il comando porta `--model opus`.
4. `GET /api/models?provider=claude` → `"fonte": "viva"` e un elenco più lungo di tre nomi, con la
   provenienza che dice **«Letti da api.anthropic.com adesso.»**
5. Riavvio dell'add-on → `ponte.modello` è ancora `opus`. La semina non rigira.
