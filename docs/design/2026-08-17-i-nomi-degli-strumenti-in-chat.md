# I nomi degli strumenti in chat — verifica del 17 agosto 2026

Revisione tecnica su richiesta del proprietario, ramo `2.0`, `v3.4.0`
(`hiris/config.yaml:2`). Nessun file di prodotto e' stato modificato: questo
documento e' l'unico artefatto.

**Il fatto riportato.** «Le etichette dei metodi chiamati non erano state tolte
dalla scrittura in chat e loggate al livello di debug? Oggi ho fatto una domanda
e mi sono stati scritti nuovamente.»

---

## 1. In una frase

I nomi ricompaiono, arrivano dalla riga di targhette che il frontend disegna
sotto la risposta (`debug.tools_called` -> `appendDebug`, `messages.js:131`), e
**non e' mai stato deciso di toglierli**: la decisione scritta dice l'opposto —
il CHANGELOG della `2.0.0` li annuncia all'utente come una funzione
(`CHANGELOG.md:1227`) e il commit `63bb131` dell'11 agosto li ha **aggiunti**
apposta al ramo del ponte, che e' il ramo di chi usa l'abbonamento.

---

## 2. La catena, dal modello allo schermo

Percorso del **ponte** (abbonamento; e' quello che il proprietario percorre
quando la chat via abbonamento e' attiva):

| # | Dove | Cosa fa | Il nome sopravvive? |
|---|------|---------|---------------------|
| 1 | `hiris/app/agent/runner.py:736` `leggi_flusso` | legge l'NDJSON di `claude --output-format stream-json` | — |
| 2 | `hiris/app/agent/runner.py:787-789` | per ogni blocco `tool_use` accoda `{"tool": nome, "input": ...}` in `esito.tools_called`. Il nome e' **grezzo, mai normalizzato**, per scelta dichiarata nel commento | **si', col nome e con gli argomenti** |
| 3 | `hiris/app/agent/runner.py:1141` (`_reply` dentro `_reason_chat`, `:984`) | `{"reply": ..., "tools_called": _reda_struttura(tools_called_turno, *forme)}`. `_reda_struttura` (`:325`) redige **solo il token interno**, non i nomi | si' |
| 4 | `hiris/app/api/handlers_chat.py:610-611` | `if "tools_called" in decision: payload["debug"] = {"tools_called": decision["tools_called"]}` sulla risposta di `GET api/chat/reply/<job_id>` | si' |
| 5 | `hiris/app/static/chat/send.js:64-65` | dentro `pollChatReply`: `if (data.debug && data.debug.tools_called && ...) appendDebug(...)` | si' |
| 6 | `hiris/app/static/chat/messages.js:131-165` | crea una `.debug-row` con una targhetta per chiamata; il nome finisce in `<span class="tc-name">` (`:143`) | **si', a schermo** |
| 7 | `hiris/app/static/chat/messages.js:158` | al click sulla targhetta si apre un pannello che stampa `nome(argomentiJSON)` — cioe' **anche gli argomenti**, che per `ricorda` sono il testo del ricordo e per `esegui`/`cerca` sono gli id delle entita' | si' |
| 8 | `hiris/app/static/hiris-chat.css:385-422` | `.tool-chip` e' sempre visibile: nessuna media query, nessun `display:none`, **nessun interruttore di debug** che la nasconda | si' |

Percorso **sincrono** (catena a consumo / Ollama), identico dal punto 4 in poi:

- `hiris/app/api/handlers_chat.py:992` legge `runner.last_tool_calls`;
  `:1004-1006` compone `[{"tool": ..., "input": ...}]`; `:1010-1013` lo mette in
  `payload["debug"]["tools_called"]`.
- `hiris/app/static/chat/send.js:183-184` chiama lo stesso `appendDebug`.

**Cosa NON porta i nomi.** Il testo della risposta del ponte e' `result.result`
del solo evento finale (`runner.py:834-836`): nessuno concatena gli eventi
`tool_use` dentro la reply. Il log del turno riporta **conteggi**, non nomi
(`runner.py:912`, «strumenti risolti=%d», e `_server_dichiarati` che espone il
nome del *server* MCP e il suo stato, non gli strumenti).

---

## 3. La causa piu' probabile

**Causa A — le targhette di `appendDebug`, aggiunte al ramo del ponte l'11
agosto. E' la piu' probabile.**

Prova diretta: commit `63bb131` (2026-08-11, «chore: il conto della fetta E5»)
aggiunge dodici righe a `hiris/app/static/chat/send.js`, e sono esattamente le
righe 56-65 di oggi. Il commento aggiunto dal commit dice perche':

> «il ramo del ponte (202 -> job_id) e' l'UNICO che un tester con l'abbonamento
> percorre, ed era l'unico che NON mostrava gli strumenti usati […] nessuno li
> leggeva: la cosa costruita perche' una scrittura di `ricorda` fosse
> OSSERVABILE non era osservabile proprio sul percorso che la produce.»

Questo spiega il ricordo del proprietario **e** il fatto di oggi con un solo
fatto: fino al 10 agosto, su abbonamento, le targhette **non comparivano** — non
perche' fossero state tolte, ma perche' quel ramo non le aveva mai lette. Il
ramo sincrono le rendeva da sempre (`60aa2c7`, 19 aprile 2026, «debug tool
log»). L'11 agosto i due rami sono stati pareggiati, e da quel giorno anche
l'abbonamento le mostra.

Verifica storica, per escludere una rimozione dimenticata: `git log -S
"appendDebug" --all -- hiris/app/static/` restituisce quattro commit — `60aa2c7`
(introduzione), `e2ad4c3` (2026-07-29, estrazione del JS in file separati),
`63bb131` (aggiunta al ramo del ponte), `fbd663f` (2026-08-14, aggiunta di
`appendNota` accanto). **Nessuno di questi toglie la chiamata.** Non esiste in
tutta la storia del ramo un commit che rimuova i nomi degli strumenti dalla
chat.

**Causa B — il modello che nomina lo strumento dentro la prosa della risposta.
Possibile, indipendente dalla A, e non e' un difetto di codice.**

Nessun prompt del prodotto **ordina** al modello di annunciare quale strumento
sta usando: ho letto per intero `hiris/app/agent/prompts.py`,
`hiris/app/claude_runner.py:249-306` (`BASE_REGOLE_STRUMENTI`) e
`hiris/app/impostazioni_chat.py:155-166` (`DEFAULT_SYSTEM_PROMPT`), e una
istruzione del tipo «di' quale strumento stai usando» non c'e'. Ma tutti e tre
**nominano gli strumenti in backtick** e gli chiedono di raccontare:

- `prompts.py:113-132` (`_GUIDA_SENZA_STRUMENTI`): «Se il prompt qui sopra
  nomina degli strumenti (per esempio `cerca`, `guarda`, `ricorda`, `richiama`,
  `esegui`)…»
- `prompts.py:199-213` (`_GUIDA_CON_STRUMENTI`): nomina cinque volte la forma
  `mcp__hiris__cerca`, `mcp__hiris__guarda`, `mcp__hiris__ricorda`,
  `mcp__hiris__richiama`, `mcp__hiris__esegui`.
- `claude_runner.py:249-306`: «Dopo aver eseguito racconta cosa e' SUCCESSO»,
  «chiama prima cerca e usa gli id che ti risponde», «`esegui` vuole gli id
  ESATTI».
- `impostazioni_chat.py:157`: «Se in questa conversazione hai gli strumenti
  `cerca` … e `guarda` …, usali».

Un modello a cui si nominano i suoi strumenti in backtick e a cui si chiede di
raccontare cosa e' successo li ripete facilmente in prosa; e `messages.js:16`
rende i backtick come `<code>` con sfondo e bordo, cioe' con un aspetto molto
simile a una targhetta. Da qui l'ambiguita' della segnalazione.

**Cosa distingue A da B, e si vede a occhio nudo sullo schermo:**

- se i nomi stanno in una **riga separata sotto la bolla**, in pastiglie
  arrotondate monospaziate con un'icona a fulmine, cliccabili -> e' la **causa
  A** (`.debug-row .tool-chip`, `messages.js:141-146`,
  `hiris-chat.css:385-408`);
- se i nomi stanno **dentro il testo della risposta**, in un riquadro grigio in
  linea con la frase -> e' la **causa B** (`<code>` prodotto da `formatContent`,
  `messages.js:16`), e allora il posto da guardare sono i prompt, non il
  frontend.

**Causa C — la chiamata a strumento «trapelata come testo». Improbabile qui, ma
esiste.** `hiris/app/backends/openai_compat_runner.py:146-161`
(`detect_leaked_tool_call`) intercetta il caso in cui certe rotte Mistral/Hermes
su OpenRouter emettono `nomestrumento` seguito da un separatore non-ASCII
invece di una vera `tool_call`; il turno viene scartato (`:1062-1074`, evento
SSE `discard_collected`, letto in `handlers_chat.py:907`). Questa difesa vale
**solo per il runner OpenAI-compat**: il ponte (`agent/runner.py`) e
`claude_runner.py` non hanno un equivalente. E' comunque un caso stretto —
richiede il carattere non-ASCII subito dopo l'identificatore (`_TOOL_LEAK_RE`,
`openai_compat_runner.py:136`) — e non produce la forma «sto usando lo
strumento X».

---

## 4. I log: cosa si scrive, a che livello

**Non esiste nessun log a livello `debug` delle invocazioni di strumento sul
ponte.** Cercando `logger.debug`/`log.debug` in tutto `hiris/` si trovano 18
occorrenze e nessuna riguarda una chiamata a strumento riuscita. In particolare,
`leggi_flusso` (`runner.py:736-835`) raccoglie l'intera lista `tools_called` e
**non la logga mai**.

Quello che si scrive davvero:

| `file:riga` | Livello | Cosa contiene |
|---|---|---|
| `hiris/app/casa/strumenti.py:450` | `warning` | nome dello strumento + tipo e testo dell'eccezione. **Solo se il gestore solleva.** |
| `hiris/app/api/handlers_mcp.py:368` | **`info`** | nome dello strumento + la stringa `errore` restituita dal dispatcher. **Quel testo puo' contenere dati di casa** (id di entita', nomi di aree, frammenti di frase), perche' e' composto dai gestori in `casa/strumenti.py` e `azione/porta.py`. E' il punto piu' esposto dei tre. |
| `hiris/app/api/handlers_mcp.py:330` | `warning` | nome dello strumento (chiamata senza `X-HIRIS-Turno`). |
| `hiris/app/api/handlers_mcp.py:342` | `warning` | nome dello strumento + id del turno (tetto raggiunto). |
| `hiris/app/claude_runner.py:942` | `debug` | nome dello strumento richiesto senza dispatcher — **ramo sincrono soltanto**, e solo nel caso degradato. |
| `hiris/app/agent/runner.py:912` | `info` | `init` del ponte: **conteggio** degli strumenti risolti e nomi dei *server* MCP. Nessun nome di strumento. |

**Nessuno di questi logga gli argomenti in modo sistematico**; il rischio dati di
casa e' concentrato in `handlers_mcp.py:368`, dove il messaggio d'errore viaggia
intero a livello `info`.

**Cosa NON si scrive e servirebbe.** Manca del tutto una riga per turno, a
livello `debug`, che elenchi gli strumenti chiamati dal ponte con i loro esiti.
Oggi quell'informazione **esiste solo a schermo**: se le targhette venissero
tolte, la tracciabilita' di una scrittura di `ricorda` sparirebbe con loro — e'
esattamente il rilievo I-7 della review di parita' B, citato in `send.js:18-22`.
Lo stato che il proprietario ricorda («via dalla chat, dentro i log a debug»)
**non e' mai esistito in nessuna versione**: nel prodotto di oggi i nomi vanno a
schermo e non vanno nei log.

---

## 5. Le prove mancanti

**Non esiste nessun test che inchiodi «i nomi degli strumenti non compaiono nel
testo dell'utente».** Ho cercato in `tests/` e `tests/js/`: l'unico test che
tocca la resa delle targhette e' `tests/js/chat-page.test.mjs:173-198`, ed e' una
**coppia che pinna l'opposto**:

- `:173` «via ponte (202): gli strumenti usati compaiono anche sul ramo del
  polling» — asserisce `chips.length === 1` e
  `chips[0].textContent === 'ricorda'`;
- `:189` «via ponte (202): senza strumenti non compare nessuna riga vuota» —
  asserisce che senza `tools_called` non nasce nessuna `.debug-row`.

Il commento sopra la coppia (`:149-158`) dichiara la ragione: renderle era
l'obiettivo.

Il test che avrebbe colto una *regressione* — cioe' un test che afferma
l'assenza — non c'e' e **non poteva esserci**, perche' contraddirebbe la
decisione scritta. Detto altrimenti: qui non e' passata inosservata una
regressione; e' che la decisione ricordata non e' quella presa. La lacuna vera,
se una c'e', e' un'altra: il ramo **sincrono** non ha nessun test JS sulle
targhette (l'unico riferimento a `.tool-chip` in tutta `tests/js/` e' quello del
ramo del ponte), quindi se qualcuno le togliesse da `send.js:183-184` la suite
resterebbe verde.

---

## 6. Cosa NON toccare

1. **La catena `tools_called`, dal punto 1 al punto 5 della tabella, e'
   deliberata e portante.** Il docstring in cima ad `agent/runner.py:55-62` la
   dichiara «l'unica cosa che rende osservabile una scrittura che non doveva
   avvenire», con le sicurezze fuori dall'UAT per decisione del proprietario.
   `handlers_chat.py:600-609` ripete la stessa motivazione. Tagliarla lascerebbe
   `ricorda` ed `esegui` senza nessuna traccia, ne' a schermo ne' nei log.

2. **La promessa e' pubblica.** `CHANGELOG.md:1227`, sotto
   `## [2.0.0] — HIRIS conosce e non agisce (2026-08-11)`: «Le targhette sotto
   la risposta ti mostrano quali strumenti ha usato davvero.» Toglierle rende
   falso un CHANGELOG gia' pubblicato.

3. **Il nome grezzo non va normalizzato.** `runner.py:783-788` lo dice: il nome
   si accoda com'e' proprio per rendere visibile il caso «il modello ha chiamato
   uno strumento che non gli abbiamo dato».

4. **Un delta che invece merita di essere guardato** (non e' il colpevole, ma e'
   una dichiarazione oggi falsa): `CHANGELOG.md:4291` dichiarava
   «`debug.tools_called` response redacted to tool names only» come mitigazione
   di prompt injection. **Oggi non e' piu' vero**: il payload porta anche
   `input` (`handlers_chat.py:1004-1006` e `runner.py:1141`), il frontend lo
   incolla in `data-args` (`messages.js:141`) e lo stampa al click
   (`messages.js:158`). L'unica redazione applicata sul ponte e'
   `_reda_struttura`, che copre il **token interno** e nient'altro
   (`runner.py:325-344`). E' uno scarto rispetto a una decisione di sicurezza
   scritta, e va deciso di proposito, non lasciato com'e' per inerzia.

---

## Cosa non ho potuto verificare

- **Quale delle due cause abbia prodotto il fatto di oggi.** Non ho la
  schermata ne' il testo della risposta: la distinzione della sezione 3 (riga di
  pastiglie sotto la bolla, contro riquadro grigio dentro la frase) e'
  l'osservazione che chiude la questione, e va fatta sullo schermo del
  proprietario.
- **Non ho eseguito la suite** ne' il prodotto: la revisione e' su codice,
  storia git e documentazione.
- **Non ho ispezionato installazioni live** (`.95`) ne' i log dell'add-on: il
  livello `log_level` effettivo dell'add-on (`hiris/config.yaml:221`,
  `list(debug|info|warning|error)`) e' una scelta d'installazione che da qui non
  si legge.
