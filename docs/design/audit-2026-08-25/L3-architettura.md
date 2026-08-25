# L3 — Architettura e qualità del codice

Audit 360° HIRIS — 24 agosto 2026 · ramo `2.0`, versione 3.12.1, HEAD `b0d6c8e` (albero pulito)
Filone: architettura, doppioni, orfani, file grandi, struttura della suite, documentazione.
Metro: le quattro fondamenta (atomicità · nessun doppione · consistenza fra porte · autonomia funzionale).

---

## Giudizio d'insieme

**Questo codice è tenuto insieme, e da una disciplina che raramente si vede: le crepe che ho
trovato non stanno nel codice ma nelle frasi che lo descrivono.** La mappa reale (proxy →
casa/memoria/azione/schedulatore/consumi → api → server) coincide con quella dichiarata; i
cataloghi sono uno solo e derivato, non tre da allineare; i doppioni pericolosi del passato sono
stati pagati e chiusi, e quelli rimasti sono o dichiarati con la loro ragione o sorvegliati da
`scripts/doppioni.py`; la suite è mantenuta con lo stesso rigore del prodotto (i test si
demoliscono insieme a ciò che testavano, e i commenti dicono quando e perché). Il degrado da
accumulo di fette c'è, ma è concentrato in due punti prevedibili: **`server.py::_on_startup`,
una funzione di ~1.460 righe che nessuno può più tenere in testa**, e **il README, che è la
fonte viva dichiarata del prodotto e ha smesso di dire il vero proprio sulla frase di confine
(«nothing acts on its own... No schedule») da quando lo schedulatore delle promesse esiste.**
Il primo è rischio futuro; il secondo è una frase falsa oggi, nel documento che il progetto
stesso indica come verità — ed è il Critical di questo referto.

---

## Rilievi: 1 Critical · 3 High · 6 Medium · 4 Low

---

### CRITICAL

#### C1 — Il README dichiara un confine del prodotto che lo schedulatore ha superato da tre release

**Dove.** `README.md:63-71`, `README.md:416-421`.

**Cosa dice.**
- `:63-64`: *«hard boundary — **nothing acts on its own.** Every execution starts from a
  sentence you typed. No schedule, no trigger, no autonomous agent.»*
- `:66-71`: *«four APScheduler jobs are registered at startup — but every one of them is
  internal housekeeping: none of them speaks to you, and none of them touches the house.»*
- `:418-419` (What is *not* in 2.0 → Notifications): *«nothing that can reach you when you are
  not in the chat»*.

**Cosa fa il codice.** I job APScheduler sono **sette**, non quattro (`hiris/app/server.py:1828,
1845, 1860, 1871, 1925, 1954, 2224`): ai quattro elencati si aggiungono la rilettura dei
problemi HA (5 min), il confronto dell'albero (15 min) e **il battito dello schedulatore delle
promesse (15 secondi)**. Il battito **tocca la casa**: `Orologio._mantieni_fai`
(`hiris/app/schedulatore/orologio.py:66-77`) esegue servizi HA via `porta_azione.esegui`
quando una promessa matura — ore dopo la frase che l'ha creata, senza nessuno in chat. E
**ti raggiunge fuori dalla chat**: una promessa «chiedi» con recapito manda una notifica sul
canale `notify`/`persistent_notification` scelto (`orologio.py:112`,
`azione/verifica.py:159`). Tre affermazioni false nello stesso documento che PRODUCT.md
(annotazione del 24/08) indica come *l'unica* fonte per «cosa il prodotto fa davvero oggi» —
e lo stesso README documenta `prometti`/`promesse`/`disdici` nella tabella dei tredici
strumenti sessanta righe più sotto: il documento si contraddice da solo.

**Cosa costa.** È la frase di sicurezza del prodotto: un utente che la legge conclude che
HIRIS non farà mai niente mentre lui non guarda, e installa su quella base. È esattamente la
classe di errore che il README stesso ammette di aver già fatto una volta («earlier versions
of this README claimed otherwise, and the claim was resting on an accident», `:52-54`, sulle
notifiche) — e l'ha rifatta.

**Correzione minima.** Riscrivere il paragrafo `:63-71` così com'è oggi: sette job; il
battito esegue promesse mature (nate da una frase in chat, verificate alla nascita) e recapita
le «chiedi» sul canale scelto; aggiornare il bullet Notifications `:416-421` («HIRIS non ha un
canale proprio, ma una promessa con recapito usa i `notify.*` della tua installazione»).
Nessuna riga di codice da toccare.

---

### HIGH

#### H1 — `proxy/_sanitize.py`: un modulo di sicurezza morto il cui docstring dichiara al presente una protezione che non esiste

**Dove.** `hiris/app/proxy/_sanitize.py:1-7` («We strip them before composing the system
prompt or the context block so they cannot rewire the agent's instructions»);
`sanitize_ha_value` a `:83`.

**Il fatto.** Nessun chiamante di produzione: 13 occorrenze nei test, zero in `hiris/app`
(confermato anche da `scripts/censimento.py`). Friendly name, stati e nomi d'area arrivano al
nucleo e ai prompt **senza** alcuno stripping. L'assenza della sanificazione è una decisione
dichiarata («prima le strutture, poi le sicurezze», CLAUDE.md, istruzione del 7 agosto; debito
già censito come «sanitize irraggiungibile») — quella non è il difetto. Il difetto è doppio:
(a) il docstring parla al presente e afferma una difesa attiva — chi lo legge (o un modello che
lo legge) conclude che la prompt-injection da HA è mitigata; (b) il modulo vivo-ma-morto viola
la regola del progetto «il codice morto si cancella, non si documenta» (CLAUDE.md §Ogni fetta
è anche pulizia) — è sopravvissuto a più fette di pulizia perché i suoi 13 test lo fanno
sembrare vivo, il caso da manuale della review rovesciata.

**Cosa costa.** Una falsa sicurezza scritta in un file di sicurezza; e 13 test che difendono
un comportamento che il prodotto non ha (il «test orfano» che CLAUDE.md chiama il più
insidioso).

**Correzione minima.** Decidere in una riga: o si cancella il modulo con i suoi test (git lo
conserva, e la fetta-sicurezze lo riscriverà dai rischi veri), o si annota il docstring come
fa `embeddings.py` («inerte di fabbrica, nessun chiamante dalla 2.x, tornerà con la fase
sicurezze») e lo si aggiunge alle «Trappole note» di CLAUDE.md accanto all'embedder.

#### H2 — Il successo del ponte non viene mai registrato: la pagina Modelli può dire per sempre «non ha risposto» di un ponte che funziona

**Dove.** `registro.successo(...)` ha un solo chiamante: `hiris/app/llm_router.py:248` (il
ciclo della catena a consumo). Il percorso del ponte registra **solo** il fallimento per
scadenza (`hiris/app/api/handlers_chat.py:465`, famiglia `scaduto`);
`handle_reasoning_submit` (`api/handlers_reasoning.py`) non tocca `registro_esiti`.

**Il fatto.** Un turno del ponte servito con successo non produce nessun esito per
`subscription`. Poiché gli esiti **non scadono per scelta dichiarata**
(`esiti_provider.py:29-34`: «un esito di due ore fa RESTA lì»), dopo un solo turno scaduto la
pagina Modelli mostra «nessuna risposta entro la scadenza del ponte» a tempo indeterminato,
mentre il ponte serve ogni turno. È la violazione della fondamenta n.3 (consistenza fra
porte): la chat dimostra un fatto che la pagina nega — e la pagina è quella su cui si
decidono i soldi (è la ragione per cui `esiti_provider.py` esiste, dice il suo docstring).

**Nota.** Rilievo **già noto e aperto** nel progetto (il buco degli esiti del ponte); lo
riporto perché a questo giro è ancora lì, e perché la non-scadenza degli esiti lo aggrava:
senza successi registrati il registro può solo peggiorare, mai guarire.

**Correzione minima.** In `handle_reasoning_submit`, alla consegna di un risultato valido di
un job `kind="chat"`: `registro.successo("subscription")` — il punto simmetrico a
`handlers_chat.py:465`, dove il fatto («il piano ha risposto») è già avvenuto.

#### H3 — `server.py::_on_startup`: ~1.460 righe in una funzione sola. Il file ha superato il punto in cui si tiene in testa

**Dove.** `hiris/app/server.py:1067-2526`. Il file è 2.964 righe (1.465 di codice, 1.239 di
commento); CLAUDE.md lo dichiara ancora «~1.900 righe».

**Il fatto.** Dentro un'unica funzione vivono: lettura segreti, token interno, HA client,
registro servizi, entity cache, cache indice, cronaca, promesse, porta, costruzioni/officina,
models_config + due semine, archivio casa, consumi + import legacy, archivio memoria,
impostazioni chat, scheduler + 7 job definiti come closure (`_ricarica_inventario`,
`_rileggi_problemi`, `_battito`, `_run_retention`, `_reasoning_sweep`...), orologio,
reasoning queue, `_submit_chat_reply`, il cablaggio dei runner per provider
(`_modello_di`...), e la rimessa in vigore del ponte. Ogni fetta ha aggiunto un blocco; i
commenti-verbale (metà del file) tengono la storia leggibile, ma la *struttura* non ha più
giunture: una closure a riga 2180 può leggere una variabile nata a riga 1131, e solo la
lettura integrale lo esclude.

**Cosa costa.** Ogni fetta nuova paga un pedaggio crescente di rilettura; una dipendenza
d'ordine fra blocchi (ce ne sono già di dichiarate: «risana PRIMA di registrare il battito»,
`:1929-1934`) si difende solo con commenti, non con confini.

**Il taglio che propongo — confini precisi, quattro pezzi, zero cambi di comportamento:**
1. **`hiris/app/lovelace_disinstallazione.py`** ← righe 268-535 (`_ws_await`,
   `_e_risorsa_della_card`, `_deregistra_risorsa_card`, `_rimuovi_file_card`,
   `_disinstalla_card_lovelace`). Codice one-shot autoconsistente: usa solo `aiohttp` e il
   filesystem, nessun altro punto di `server.py` lo chiama se non l'avvio.
2. **`hiris/app/lavori_casa.py`** ← righe 541-937 (`ricarica_inventario_entita`,
   `rileggi_problemi_ha`, `giro_di_confronto_albero`, `programma_ricostruzione_anagrafe`,
   `programma_rilettura_plance`, `sentinella_comportamento`,
   `programma_rilettura_comportamento`). Sono già funzioni pure di (client, archivio, app):
   il confine esiste, manca solo il file.
3. **Il governo del ponte** (righe 111-250 e 938-1066: `_ponte_attivo`, `_avvisi_del_ponte`,
   `_catena_com_era`, `_governa_lavoratore_del_ponte`, `_ricalcola_catena`) →
   **`hiris/app/instradamento.py`**, dove la decisione «chi risponde» già vive: oggi la
   stessa domanda («il ponte è in gioco?») ha metà risposta in `server.py` e metà in
   `instradamento.py`.
4. **`_on_startup` spezzata in fasi nominate** chiamate in sequenza dalla funzione madre
   (`_apri_archivi(app)`, `_costruisci_azione(app)`, `_semina_modelli(app)`,
   `_registra_lavori(app, scheduler)`, `_rimetti_in_vigore(app)`): l'ordine resta esplicito
   in un punto solo, e ogni fase dichiara nel nome cosa tocca.

---

### MEDIUM

#### M1 — I riferimenti `file:riga` del README sono sistematicamente stantii, e due conteggi con loro

**Dove/fatti verificati.**
- `README.md:69`: inventario entità «`server.py:969-974`» → oggi è a `:1828`; la sentinella
  «`:980-985`» → oggi `:1871`. (Le righe 969-985 oggi sono `_governa_lavoratore_del_ponte`.)
- `README.md` (What it knows): «registry-update subscriptions live at
  `ha_client.py:26-31`» → a quelle righe c'è il doppione dichiarato di `_ENTITY_ID_RE`;
  «debounced rebuild at `server.py:403`» → riga dentro `_deregistra_risorsa_card`.
- `README.md:119`: «It has five sections (`nucleo.py:545-548,648`)» → le sezioni sono **sei**
  dalla fetta «come sta la casa» (`## Cosa non va in casa`, `nucleo.py:255,1612`), e a
  `:545-548` c'è il blocco delle unità di misura.
- `README.md:377`: «five live routes» → le rotte della SPA `/config` sono **otto**
  (`static/config/main.js:101-178`: `#/`, `#/albero`, `#/memoria`, `#/promesse`,
  `#/costruzioni`, `#/usage`, `#/models`, `#/impostazioni`) — mancano dalla tabella proprio
  le tre pagine delle fette più recenti (promesse, costruzioni, albero verificabile).
- «shared with the chat via `handlers_chat.py:317`» → a `:317` c'è il commento su chat_store.

**Cosa costa.** Il README è la fonte viva dichiarata: ogni riferimento sbagliato manda chi
verifica (utente, auditor, modello) nel punto sbagliato del codice, e un numero sbagliato
(«five sections», «five routes») è una frase falsa secondo il metro del progetto.

**Correzione minima.** Sostituire i `file:riga` con ancore a simboli, la grafia che il
codice stesso già usa (`server.py::_ponte_attivo`): i simboli sopravvivono alle fette, le
righe no. Aggiornare i due conteggi (6 sezioni, 8 rotte) e completare la tabella delle rotte.

#### M2 — CLAUDE.md, «Struttura reale... questa lista deriva dal codice»: mancano `consumi/` e i moduli delle ultime fette, e due numeri sono stantii

**Dove.** `CLAUDE.md:224-244` (albero), `:214` e `:252` (numeri).

**Fatti.** L'albero non contiene **`consumi/`** (fetta 3.10, `archivio.py` +
`vocabolario.py`), né `casa/tempo.py` (fetta 3.12), né i moduli di primo livello
`decisione_modelli.py` (1.052 righe), `instradamento.py`, `esiti_provider.py`,
`migrazione_opzioni.py`, `token_interno.py`. «server.py ~1.900 righe» → 2.964. «2.413 test +
1 skip» → 2.513 raccolti oggi. La frase «Verificala con `ls hiris/app/` — questa lista deriva
dal codice, non da un piano» rende ogni omissione una frase falsa per dichiarazione propria.

**Cosa costa.** CLAUDE.md è ciò che ogni sessione di lavoro legge per prima: un agente che si
fida dell'albero non sa che i consumi esistono come pacchetto, e i numeri stantii insegnano a
non fidarsi del resto del file.

**Correzione minima.** Riallineare l'albero a `ls hiris/app/` e togliere i due conteggi
puntuali (o sostituirli con «vedi `pytest --collect-only`») — un numero che invecchia a ogni
fetta non deve vivere in un documento di regole.

#### M3 — `ArchivioConsumi` è l'unico archivio SQLite che `_on_cleanup` non chiude

**Dove.** `hiris/app/server.py:2527-2572` chiude `reasoning_queue`, `archivio_casa`,
`archivio_memoria`, `promesse`, `cronaca`, `costruzioni` — con commenti che dichiarano la
disciplina («senza chiuderli un riavvio lascerebbe il file sqlite bloccato»). `app["consumi"]`
(`ArchivioConsumi`, `server.py:1272`, connessione aperta in `consumi/archivio.py:66`, `close()`
disponibile a `:70`) non compare. Nessun altro punto lo chiude.

**Cosa costa.** Il rischio dichiarato dagli stessi commenti (file bloccato al riavvio,
journal WAL non ripulito) applicato a 6 archivi su 7: la settima omissione è del tipo che si
vede solo il giorno in cui capita — e viola la consistenza della disciplina che il file
stesso enuncia.

**Correzione minima.** In `_on_cleanup`: `if "consumi" in app: app["consumi"].close()`.

#### M4 — La soglia dei test JS è tornata «un test che non può fallire»: pavimento 12, file 22

**Dove.** `tests/test_js_suite_wired.py:46` (`_MIN_JS_TEST_FILES = 12`); `tests/js/` contiene
**22** file `*.test.mjs`.

**Il fatto.** Il file stesso scrive la regola due volte: «la soglia resta ANCORATA AL
CONTEGGIO REALE, cioè massimamente stretta... chi aggiunge o toglie un file conta di nuovo» —
e documenta che questa deriva era **già successa** (soglia 8 coi file a 11) ed era stata
corretta con le stesse parole. Da allora dieci file sono entrati (promesse, costruzioni,
albero, formattazione-consumi...) senza riancorare: oggi si possono cancellare 10 file di
test in silenzio e la guardia non scatta. È il difetto n.1 dichiarato del progetto, dentro la
guardia nata per prevenirlo.

**Correzione minima.** `_MIN_JS_TEST_FILES = 22`. E poiché il pattern è al terzo giro,
valutare di **contare invece di ancorare**: fallire se il conteggio scende rispetto a un
manifest versionato dei nomi (un file d'elenco che il diff rende visibile), così la deriva
non può più essere silenziosa per costruzione.

#### M5 — `ha_client.statistiche`: il docstring dice «mai girata in produzione, forma non misurata» — smentito dal commit che gli sta sopra

**Dove.** `hiris/app/proxy/ha_client.py:1211-1212`: «**Mai girata in produzione** (spec
§7.1): la forma della risposta e' quella documentata, non quella misurata.»

**Il fatto.** Il commit `fc22cd2` (24/08, «i due traduttori sulle forme MISURATE, non su
quelle immaginate») dichiara che le verifiche §7.1-7.2 **sono state fatte sulla casa vera**:
`start` misurato come intero in millisecondi (e tradotto), 755 voci vere del logbook
misurate. La frase era la bandiera giusta finché era vera; ora insegna il contrario di ciò
che è successo — il prossimo sviluppatore o rifà la verifica dal vivo o, peggio, non si fida
del traduttore appena aggiustato.

**Correzione minima.** Aggiornare le due righe: «Forme misurate sulla casa vera il 24/08/2026
(verifiche §7.1-7.2, commit fc22cd2): `start` arriva in millisecondi ed è tradotto qui.»

#### M6 — `casa/strumenti.py` (1.874 righe): il catalogo e il mestiere delle promesse convivono col dispatcher. Il taglio

**Dove.** `hiris/app/casa/strumenti.py`. Righe 1-833: **tredici `*_TOOL_DEF`** e
`STRUMENTI_CONOSCENZA` (dati, non comportamento). Righe 834-1874: `DispatcherStrumenti`.
Dentro il dispatcher, le righe 1594-1837 (`_verifica_ora`, `_specchio_cieco_rifiuto`,
`_verifica_da_confrontare`, `_registro_non_pronto`, `_verifica_recapito`, `_istantanea`,
`_stati_grezzi`, `_fuso`) sono il mestiere della **promessa** (verifica alla nascita,
istantanea, recapito): parlano con `azione/verifica.py` e con il registro servizi, non con
gli archivi della casa.

**Il fatto.** Il file si tiene ancora in testa — il dispatcher è disciplinato, `dispatch()` è
l'unico ingresso, i nomi derivano dal catalogo — ma è al limite, e ogni strumento nuovo
(+2 nella sola fetta «tempo») allunga entrambe le metà. Il confine giusto esiste già nel
testo:
1. **`casa/strumenti_catalogo.py`** ← righe 1-833 (i 13 TOOL_DEF + `STRUMENTI_CONOSCENZA` +
   `_NOMI_STRUMENTI`). Solo dati; `handlers_mcp.py:81` e `agent/runner.py` importano già solo
   `STRUMENTI_CONOSCENZA` e non cambierebbero che l'import.
2. **Il blocco promesse (1594-1837)** → un collaboratore `VerificaPromessa` in
   `hiris/app/schedulatore/` (o `azione/`), costruito con `registro` + `stati_grezzi` e
   passato al dispatcher: `casa/` smette di conoscere il vocabolario dei recapiti
   (`_DOMINI_DI_RECAPITO` resta in `azione/verifica.py`, dove già vive).
   Il dispatcher scende sotto le 900 righe e ogni pezzo risponde alla domanda dello scope
   («a quale strato appartiene, e uno solo?»).

---

### LOW

#### L1 — `instradamento.py` importa un privato dello strato API

`hiris/app/instradamento.py:44`: `from .api.handlers_models import _PREDEFINITI_ARCHIVIO`.
Un modulo del nucleo dipende dalla superficie HTTP per un default di dominio (il tetto
giornaliero del ponte), e da un nome con underscore che `handlers_models` è libero di
rinominare. Correzione minima: spostare `_PREDEFINITI_ARCHIVIO` in `decisione_modelli.py`
(dove instradamento già attinge `piano_ha_il_token`) e importarlo da lì in entrambi.

#### L2 — `static/chat/agents.js`: il nome descrive un mondo uscito con la E4/E5

Il file (incluso da `index.html:125`) gestisce contatore turni, cronologia e nome
dell'assistente **unico**; il suo stesso commento di testa spiega che «non c'è più niente da
elencare». Chi cerca «agents» nel repo conclude che gli agenti esistano ancora nel frontend.
Correzione minima: rinominare in `sessione.js` (o `assistente.js`) + una riga in
`index.html`; il fingerprint per-file assorbe la cache.

#### L3 — `hiris-config-override.css`: lo strato-alias legacy→Iris è ancora vivo

413 righe che mappano il vecchio vocabolario di token sul design system, con l'istruzione di
auto-soppressione scritta nel proprio header («Or simpler: replace the inline style... and
remove the legacy blocks»). In `hiris-config.css` restano ~6 usi di token legacy
(`--surface-hover`...). Due nomi per lo stesso colore sono il doppione della fondamenta n.2
applicato al tema: un token cambiato nel theme e letto via alias stantio diverge in silenzio.
Correzione minima: migrare i 6 usi residui e cancellare l'override (o ridurlo agli alias
davvero usati, contati).

#### L4 — I reperti aperti degli strumenti propri del progetto

`scripts/censimento.py` (uscita 0, 35 reperti) e `scripts/doppioni.py` segnalano oggi:
`_ws_call` senza chiamanti (`ha_client.py:1190` — nota: convive con l'omonimo wrapper
`_ws_request` subito sopra, e il commento «back-compat» non dice più back-compat di cosa);
`/api/entities` esercitata solo dai test (`server.py:2671`); `estrai_dal_bersaglio`,
`get_config`, `loaded` solo-test; e **12 vocabolari chiusi Python↔JS** non presenti nel
registro dei doppioni dichiarati (a differenza dei 3 dichiarati con ragione). Con un frontend
senza build step lo specchio JS è strutturale — ma la regola del progetto prevede la
dichiarazione, e solo alcuni (promesse) hanno un test di parità. Correzione minima: una
passata di «o si cancella o si dichiara» su questi nomi, e la dichiarazione esplicita dei 12
vocabolari in `doppioni.py` o un test di parità ciascuno.

---

## Ciò che sembra un difetto e non lo è (verificato, con la ragione trovata nel codice)

- **`PRODUCT.md` descrive un prodotto che non esiste** — è il design del progetto: catena di
  annotazioni-verbale (10/08 → 12/08 → 23/08 → 24/08) aggiornata fino a *ieri* (tredici
  strumenti), con il rimando esplicito al README. È il documento più curato del repo, non il
  meno.
- **`/api/mcp` non è un secondo catalogo** — `handlers_mcp.py:247` *ri-forma*
  `STRUMENTI_CONOSCENZA` (una chiave rinominata), e `_NOMI_STRUMENTI` deriva dal catalogo
  (`strumenti.py:823-831`): la lezione dei tre cataloghi divergenti è stata applicata.
- **`_ENTITY_ID_RE` esiste due volte** (guardia stretta in `ha_client.py:31`, riconoscitore
  largo) — doppione dichiarato con la ragione scritta accanto («allinearle sarebbe una falla,
  non una pulizia»), e saltato da `doppioni.py` per dichiarazione.
- **`hiris/app/brain/` e `hiris/app/history/` esistono su disco** — contengono solo
  `__pycache__` non tracciato: il repo è pulito e CLAUDE.md dice il vero su git. (Un
  `git clean`/nota in `.gitignore` locale li toglie di mezzo, ma non è un difetto del ramo.)
- **Lo scope (`2026-08-04-scope-hiris.md`) descrive Brain e agenti che non esistono** — si
  dichiara da sé contratto sul futuro («non descrive l'esistente: è il metro»), e CLAUDE.md
  traccia onestamente dove sta il prodotto in quell'impianto («① c'è. ② e ③ no»).
- **Le 22 env var «lette e mai esportate da run.sh»** — limite dichiarato dello strumento:
  quasi tutte arrivano da Supervisor/Docker o sono scorciatoie dei test, e la regola di
  prodotto («prima nella UI dell'add-on») è scritta in CLAUDE.md.
- **La verifica delle promesse in `strumenti.py` non è un doppione di `azione/verifica.py`** —
  chiama la *stessa* `verifica()` e riusa le *stesse* guardie della porta
  (`_registro_non_pronto`, specchio cieco), con la genealogia dei tre casi scritta nei
  docstring. È mal *collocata* (M6), non duplicata.

---

## Nota sulla mappa (compito 1, esito)

La mappa costruita dal codice — `proxy/` (confine HA, traduzione delle chiavi al confine) →
`casa/`·`memoria/`·`azione/`·`schedulatore/`·`consumi/` (dominio) → `api/` (superficie) →
`server.py` (cablaggio) — coincide con la mappa dichiarata, con tre sole eccezioni, tutte già
elencate sopra: l'albero di CLAUDE.md incompleto (M2), l'inversione `instradamento → api`
(L1), e il fatto che `server.py` è più cablaggio di quanto un file solo possa portare (H3).
I due canali di scrittura dichiarati («un canale, una porta») sono rispettati: nessun punto
fuori da `azione/porta.py` e `azione/costruzione/officina.py` scrive verso Home Assistant.
