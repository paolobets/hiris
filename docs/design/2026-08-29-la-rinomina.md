# La rinomina — il codice passa all'inglese

**Fetta successiva a «il glossario» (28/08).** Il glossario ha deciso *come si chiamano le cose*;
questa fetta le chiama così.

---

## 1. Il mandato, con le parole del proprietario

> «A me interessa in inglese **il codice scritto**, non i commenti: quelli in italiano vanno
> benissimo. Quindi solo ed esclusivamente ciò che è codice.»

E prima, il problema che ha generato tutto:

> «L'importante è che nella codebase ci siano mescolanze tra lingue, un po' italiano un po' inglese.»

Il difetto erano i **nomi** — `ArchivioMemoria` accanto a `ChatStore` — non la prosa. Questa fetta
cura quello e nient'altro.

### Il confine, reso strutturale invece che promesso

Lo strumento lavora **solo sui token di tipo nome**. Commenti e stringhe non li tocca *per
costruzione*: non è una precauzione che si può dimenticare, è una proprietà del meccanismo.

Restano quindi in italiano, e non per omissione:

- **I commenti e le docstring.** Sono la cosa migliore di questa codebase. *«Lo zero che afferma»*,
  *«il pin garantisce la RIPRODUCIBILITA', non che la versione funzioni»*, *«None resta None, uno
  zero al suo posto sarebbe la bugia della fetta»*: nella sola giornata del 28/08 questi commenti
  hanno fatto trovare due difetti veri e ne hanno **impedito uno** — una correzione sbagliata,
  fermata perché il commento accanto spiegava la decisione che stava per essere ribaltata.
- **Le frasi che HIRIS dice al proprietario.** Il prodotto parla italiano. Tradurle sarebbe un
  difetto, non una coerenza.

---

## 2. Le misure, prima di progettare

Prese il 29/08 sulla codebase reale.

### Quanto è grande

| | file | righe |
|---|---|---|
| Python (`hiris/app`) | 87 | 34.122 |
| JavaScript (`hiris/app/static`) | 22 | 6.948 |
| Test | 172 | **54.329** |

**I test sono la superficie più grande di tutte** — più di codice e frontend messi insieme. Vanno
rinominati anche loro, ed è il fatto che decide il rischio (§6).

### Dove cadono le occorrenze delle parole del glossario

196 parole del glossario, cercate nel Python:

| | occorrenze | |
|---|---|---|
| Stringhe e docstring | 24.563 | 47% |
| **Identificatori** | **15.884** | **31%** |
| Commenti | 11.103 | 21% |
| Altro | 337 | 1% |

**Il 68% è prosa.** Il perimetro del mandato taglia i due terzi del lavoro apparente — ed è ciò che
rende questa fetta possibile invece che un rifacimento.

### La forma degli identificatori, che decide il metodo

I due numeri qui sotto contano cose diverse e vanno letti insieme: **15.884** sono le *occorrenze di
parole del glossario* dentro identificatori, **8.252** sono gli *identificatori* che ne contengono
almeno una. La differenza sta tutta nei composti, che valgono due o tre parole ciascuno.

Su 8.252 identificatori:

- **5.511 sono una parola sola** → meccanici
- **2.741 sono composti** → richiedono giudizio

I composti rompono la sostituzione cieca in tre modi distinti, tutti misurati:

1. **L'inglese inverte l'ordine.** `unita_vive` non è `unit_reported`: è `reported_units`. L'italiano
   mette l'aggettivo dopo, l'inglese prima. Una sostituzione pezzo per pezzo produce parole inglesi
   in ordine italiano.
2. **Ci sono preposizioni.** `nomi_di_ripiego`: quel `di` non è una parola del glossario, e in
   inglese sparisce del tutto.
3. **Ci sono sigle di confine.** `sanitize_ha_value` (`casa/archivio.py:109`, 29 siti): quel `ha`
   è *Home Assistant*, e resta `ha` — non si traduce e non si espande. Lo stesso vale per
   `ha_client` (109 siti), `ha_base_url`, `ha_config_dir`, `_ha_channel`,
   `_fingerprint_from_ha_state`.
   **Il contro-esempio va letto insieme, ed è la parte istruttiva** (corretto il 31/08: fino a
   quel giorno questa riga portava `ha_credenziale` come esempio del caso *Home Assistant*, ed
   era falso). In `ha_credenziale` (`decisione_modelli.py:653,717,736,755`) quel `ha` è il
   **verbo** — «il provider ha una credenziale», `ha_credenziale = bool(credenziali.get(pid))`
   — e infatti il gemello già inglese si chiama `_config_has_credential`
   (`api/handlers_models.py:369`), non `ha_credential`. La stessa sigla è *Home Assistant* in
   dieci nomi su dodici e il verbo negli altri due (`ha_credenziale`, `piano_ha_il_token`):
   nessuna regola meccanica separa i due casi, li separa solo la lettura di ciò che sta
   intorno. Un documento che avvertiva di non innescare la trappola l'aveva armata: chi apriva
   `decisione_modelli.py` leggendo questa riga avrebbe scritto `ha_credential`.

I composti più frequenti, per dare la misura: `archivio_casa` (41), `esecuzione_id` (32),
`classi_vive` (29), `unita_vive` (29), `dispositivo_id` (26), `nomi_di_ripiego` (25).

**Dei tre modi, uno solo si può meccanizzare, e dal 31/08 c'è un cancello che lo fa** — il
secondo: `tests/test_preposizioni_italiane.py` vieta una preposizione, un articolo o una
congiunzione italiana dentro un identificatore, su tutto il Python del progetto, con
l'istantanea dei 224 casi noti che cala mano a mano che i sottosistemi si convertono. Il primo
(l'ordine) **non** si meccanizza: richiede di sapere quale pezzo è la testa del nome, cioè il
significato e non la forma, e il suo unico controllo resta la lettura — vedi
«Due difetti di composizione, e solo uno si può meccanizzare» in `docs/GLOSSARIO.md`. Il terzo
(le sigle) nemmeno: lo dice la riga qui sopra.

---

## 3. Lo strumento — `scripts/rinomina.py`

Il primo deliverable non è codice rinominato: è **il rinominatore**. La ragione è quella che questa
sessione ha già pagato tre volte in un giorno — *lo strumento di misura sbaglia più del giudizio*: un
grep case-sensitive che ha dichiarato «zero occorrenze» dove ce n'erano tre, un conteggio di token
scambiato per un conteggio di chiamate, uno script che confronta token esatti e quindi non poteva
vedere `read`/`reading`. Un rinominatore con i suoi test, provato per mutazione, è verificabile; un
`sed` da 15.900 sostituzioni no.

### Cosa fa

Legge `docs/GLOSSARIO.md` e un **sottosistema** (mai l'intera codebase in un colpo solo). Per ogni
token di tipo nome lo spezza su `_` e su camelCase, poi:

| caso | azione |
|---|---|
| una parola sola, nel glossario | **applica** |
| composto | **propone e si ferma** |
| nessun pezzo nel glossario | non tocca |

Per i composti scrive un file di proposta — nome attuale, pezzi riconosciuti, inglese suggerito — che
un secondo passaggio applica **solo dopo conferma**. È la legge del glossario applicata alla
rinomina: *una riga senza prova non è decisa, è un'opinione*. Lo strumento non indovina l'ordine
delle parole: lo chiede.

### Le quattro guardie

1. **Rifiuta di girare su un albero sporco.** Un diff da rivedere non deve mai mescolare la rinomina
   con altro.
2. **È idempotente.** Rigirarlo non cambia nulla. Senza questa proprietà non si può ri-applicare
   dopo una correzione senza rileggere tutto.
3. **Rispetta le parole di confine.** Le righe che il glossario dichiara di Home Assistant o dei
   provider — `entity`, `state`, `unit`, `domain`, `model`, `tool`, `token` — sono in un elenco
   intoccabile, letto dal glossario e non scritto a mano nello strumento.
4. **Risolve gli omonimi per sottosistema.** `ancora` è `tether` in `memory/` e `anchor` in
   `consumi/`; `piano` è `floor` in `casa/` e `subscription` altrove. Lo strumento lo sa **solo
   perché gli si dice dove sta lavorando**, ed è il motivo per cui non esiste una modalità
   «rinomina tutto».

Test propri, provati per mutazione: rimesso il difetto, devono fallire.

---

## 4. Le fette e i rilasci

Ordine dal più piccolo, perché il primo sottosistema serve a **provare lo strumento**, non a
risparmiare tempo.

| # | cosa | dimensione | note |
|---|---|---|---|
| 1 | lo strumento + cancellare `brain/` e `history/` | — | nessuna rinomina ancora |
| 2 | `consumi/` | 3 file, 462 righe | **il più piccolo: prova lo strumento da capo a fondo** |
| 3 | `keeper/` + `memory/` | 10 file, 2.083 righe | → **rilascio** |
| 4 | `mind/` | 5 file, 1.624 righe | |
| 5 | `azione/` | 10 file, 3.052 righe | |
| 6 | `casa/` | 9 file, 7.368 righe | il più grande fra i sottosistemi |
| 7 | i moduli alla radice, `server.py`, il frontend JS | 3.818 righe di solo `server.py` (elenco sotto) | → **rilascio** |
| 8 | le 14 rotte HTTP e i campi JSON, col frontend che le chiama | 14 rotte | un commit solo, le due sponde insieme |
| 9 | `api/` | 17 file, 4.609 righe | **mancava da questa tabella** -- vedi la nota sotto |
| 10 | `agent/` | 3 file, 2.181 righe | **mancava da questa tabella** |
| 11 | `proxy/` | 4 file, 2.494 righe | **mancava da questa tabella** |
| 12 | `backends/` | 7 file, 1.637 righe | **mancava da questa tabella** |
| 13 | `reasoning/` | 2 file, 345 righe | **mancava da questa tabella** |
| 14 | le 14 rotte HTTP e i campi JSON, col frontend che le chiama | 14 rotte | un commit solo, le due sponde insieme |
| 15 | i 13 nomi degli strumenti | 13 nomi | → **rilascio**, con verifica dal vivo |

**Corretto il 31/08, durante il Task 9 (`api/`), dopo un rilievo della review: cinque sottosistemi
su undici non erano in questa tabella, e non per svista -- per un criterio sbagliato applicato con
coerenza.** Le fette 2-6 elencano i sottosistemi col NOME DI CARTELLA italiano (`consumi`,
`schedulatore`, `memoria`, `cervello`, `azione`, `casa`), e la fetta 7 i moduli di radice. I cinque
con nome di cartella INGLESE -- `api/`, `agent/`, `proxy/`, `backends/`, `reasoning/` -- non
comparivano da nessuna parte: **11.266 righe, un terzo del Python del progetto, classificate per il
nome del contenitore invece che per cio' che contengono.** E' la stessa classe di difetto che
questa fetta esiste per curare, applicata al piano della fetta stessa.

Che l'assunzione fosse falsa e' misurato, non temuto: `reasoning/queue.py` ha quattro metodi
PUBBLICI ancora italiani (`reclama_scaduto`, `risolvi_ripiego`, `fallisci_ripieghi_bloccati`,
`count_turni_oggi`) chiamati da `api/handlers_chat.py`, `api/handlers_reasoning.py`,
`keeper/exchange.py`, `instradamento.py` e `server.py`; `backends/` porta 30 identificatori che
il glossario di oggi tocca (`_codice_di`, `_modello_scelto`, `registra_consumo`, `famiglia_errore`,
`stato_circuito`, ...). Le due cartelle sono inglesi di nome e miste di contenuto.

**Le fette 8 e 9 originali sono diventate 14 e 15**: le rotte e i nomi degli strumenti restano per
ultimi, e per le stesse ragioni scritte sotto. `api/` porta il numero 9 perche' e' la fetta che si
sta convertendo mentre questa riga viene scritta -- non era numerata affatto, e i suoi rapporti la
chiamano «Task 9».

**FATTO il 02/09 — i nomi dei file.** I sei moduli qui sotto e i sei file di rotta del
frontend hanno preso il nome inglese con un `git mv` per linguaggio: `instradamento.py` ->
`steering.py`, `impostazioni_chat.py` -> `chat_settings.py`, `decisione_modelli.py` ->
`model_resolution.py`, `esiti_provider.py` -> `provider_occurrences.py`, `migrazione_opzioni.py`
-> `options_migration.py`, `token_interno.py` -> `internal_token.py`; e
`albero|costruzioni|impostazioni|memoria|osservatore|promesse-route.js` ->
`tree|constructions|settings|memory|watcher|agenda-route.js`. **Le righe qui sotto restano coi
nomi di allora perche' sono l'elenco di quel giorno.**

**I moduli italiani alla radice** (fetta 7), per non lasciarli impliciti: `instradamento.py`,
`impostazioni_chat.py`, `decisione_modelli.py`, `esiti_provider.py`, `migrazione_opzioni.py`,
`token_interno.py`, piu' `chat_store.py` e `storage.py` che hanno gia' un nome inglese ma
contengono identificatori italiani.

**`brain/` e `history/` sono vuote** — contengono solo `__pycache__`. Sono gusci morti di moduli
cancellati, e vanno via nella fetta 1: in questo progetto ogni fetta è anche pulizia.

### Perché gli strumenti stanno per ultimi e da soli

Sono **dati che il modello legge**, non codice che i test coprono. Cambiarli cambia il comportamento
di HIRIS in un modo che nessuna suite verde può smentire. La loro verifica è dal vivo, con gli
strumenti costruiti il 28/08: `GET /api/health` e un turno di chat vero.

### Perché le rotte si possono fare, e il database no

Le rotte hanno **un solo consumatore, il frontend, che viaggia dentro la stessa immagine**: cambiano
insieme, in un commit, e non può esistere un client vecchio che parla con un server nuovo. Il gateway
MCP non le chiama; il ponte usa rotte già inglesi.

Il database no, e non per prudenza: **misurato il 29/08, 11 tabelle su 24 e 60 nomi di colonna su
102 non hanno un inglese deciso.** (Le colonne sono 138 contando ogni coppia tabella-colonna, 102
contando i nomi distinti: e' su questi ultimi che si decide, perche' lo stesso nome ricorre in piu'
tabelle e va deciso una volta sola.) Il glossario ha nominato 80 concetti, 118 parole ordinarie e 13
strumenti; le tabelle e le colonne non le ha mai toccate, esattamente come aveva rinviato di
proposito i valori di dominio. **Non si può rinominare ciò che non è stato nominato.**

---

## 5. La trappola che può rompere qualcosa in silenzio

**Gli accessi dinamici.** `app["archivio_casa"]` è una stringa: lo strumento, giustamente, non la
tocca — ma il modulo che quella chiave nomina cambia nome. Sono **41 occorrenze solo per quella
chiave**, e ce ne sono altre (`getattr`, chiavi di dizionario, `**kwargs`).

Il cancello non le vede e i test le vedono **solo se il percorso è coperto**. È l'unico punto di
questa fetta in cui si può rompere qualcosa senza che niente diventi rosso.

**Regola: ogni fetta di sottosistema cerca esplicitamente i propri accessi dinamici e li tratta a
mano, prima di dichiararsi finita.** Il report della fetta elenca quelli trovati e dove.

---

## 6. La rete, e dove non arriva

Cancello (`ruff` + `oxlint`) su ogni commit, 2.845 test, CI su Linux, e verifica dal vivo dopo ogni
rilascio.

**Ma i test vengono rinominati anche loro**, ed è onesto dire cosa questo significa. Una suite verde
dopo la rinomina dimostra che **non è rimasto niente di incoerente**: un riferimento cambiato di qua
e non di là esplode subito, ed è esattamente il difetto più probabile su 15.900 modifiche.

Non dimostra che il nome scelto sia **buono**. Quello lo dimostrano il glossario — dove ogni nome è
già passato per la prova del lettore nuovo — e la revisione del diff, sottosistema per sottosistema.
Confondere le due cose sarebbe credere di aver provato la qualità dei nomi avendo provato solo la
loro coerenza.

---

## 7. Cosa resta fuori, e perché — decisioni scritte, non silenzi

| | perché |
|---|---|
| **Commenti e docstring** | il mandato del proprietario; e sono ciò che rende la codebase leggibile |
| **Le frasi rivolte al proprietario** | il prodotto parla italiano |
| **Il database (24 tabelle, 138 colonne)** | **oggi impossibile**: 60 nomi di colonna su 102 non sono mai stati decisi. Serve prima una fetta di vocabolario. E quel giorno servirà una ragione migliore della coerenza, perché il rischio è la memoria di una casa vera |
| **I valori di dominio (~40 costanti)** | già rinviati dal glossario, con la ragione scritta lì |

---

## 8. Quando questa fetta è finita

- Nessun identificatore italiano in `hiris/app`, `tests/` e `hiris/app/static` — **misurato**, con lo
  stesso script che ha prodotto i numeri del §2, che deve restituire zero occorrenze in posizione di
  nome
- Cancello verde, 2.845 test verdi, CI verde su Linux
- `GET /api/health` risponde, `ponte.cli` è popolato, un turno di chat va a buon fine sulla casa vera
- Il glossario aggiornato dove la rinomina ha scoperto che un nome non reggeva: **la prova vera di un
  nome è usarlo**, e ciò che si scopre applicandolo torna nel documento
