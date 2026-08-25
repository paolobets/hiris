# L4 — Audit funzionale (esecuzione dal vivo)

Filone funzionale dell'audit 360° del 24/08/2026, ramo `2.0`, HEAD locale `b0d6c8e` (dichiarata 3.12.1).
Regola seguita: sola lettura, nessuna modifica al codice, nessun sotto-agente. `POST /api/chat`
mai chiamato. `esegui`/`costruisci`/`conferma` mai chiamati (giudicati solo da codice, come da
mandato). `ricorda`/`prometti`/`disdici` NON eseguiti nonostante il mandato li elenchi fra i "dieci
che leggono": scrivono comunque uno stato persistente sull'add-on collegato alla casa vera (una
memoria falsa, una promessa che si materializzerebbe più tardi), e il vincolo assoluto del
COME-SI-ENTRA vieta esplicitamente "niente POST che cambino stato — né sull'add-on, né su Home
Assistant". Giudicati solo da codice, per prudenza.

## La scoperta più grave: la produzione non è alla versione che l'audit presume

**Verificato eseguendo**, non dedotto. `GET /api/health`:

| Istanza | versione | build |
|---|---|---|
| Locale 127.0.0.1:8099 | `3.12.1` | `6dc2786a64cb` |
| **Produzione** 192.168.1.95:8099 | **`3.12.0`** | `bbab0d8bafcc` |

Il brief dell'audit dichiara "la produzione ha la 3.12.1 appena rilasciata": **non è vero**, la
produzione è ferma a 3.12.0. La 3.12.1 ("Le forme vere", CHANGELOG.md) esiste proprio per
correggere due difetti che il CHANGELOG stesso descrive come mai misurati dal vivo prima di oggi —
e li ho ri-misurati io dal vivo, sulla produzione ferma alla versione precedente:

**Chiamata eseguita** (`tools/call` → `andamento`, entità reale, finestra 72h, su produzione):
```
{"entita": "sensor.bagno_1p_t_bagno_1p_t_temperature", "unita": "°C", "finestra_chiesta_ore": 72.0,
 "errore": "Home Assistant ha risposto con fasce orarie il cui istante di inizio non e' nella forma
 attesa (ISO-8601 con fuso): non posso dire se i dati ci sono senza rischiare di leggerli male."}
```
Ho verificato la causa interrogando direttamente il WebSocket di Home Assistant
(`recorder/statistics_during_period`, sonda diretta con `aiohttp`, bypassando HIRIS): `start` arriva
come **intero in millisecondi** (`1787349600000`), non come stringa ISO-8601. `hiris/app/casa/tempo.py`
in 3.12.0 non sapeva leggerlo e falliva rumorosamente (per progetto: onestamente, non con un vuoto
finto) — `andamento` oltre le 24 ore è **completamente inutilizzabile in produzione oggi**, su
qualunque entità con statistiche a lungo termine (temperature, consumi, contatori: la classe di
domande più utile dello strumento). Il commit `fc22cd2` ("fix(tempo): i due traduttori sulle forme
MISURATE, non su quelle immaginate"), già in `2.0`/locale, corregge esattamente questo
(`_istante_da_ha` in `hiris/app/proxy/ha_client.py:114-135`, con la stessa misura dichiarata nel
docstring: "Misurato sulla casa il 24/08/2026"). Non ho potuto ri-eseguire la stessa chiamata sulla
copia locale con la fix per chiudere il cerchio in esecuzione: il WebSocket persistente
dell'istanza locale verso la casa vera era giù per tutta la sessione (vedi punto successivo), quindi
`andamento` sul locale non ha potuto interrogare Home Assistant affatto. La correlazione
codice-fix ↔ CHANGELOG ↔ commit ↔ comportamento riprodotto in produzione è però solida.

**Conseguenza per chi usa il prodotto**: chiunque chieda oggi a HIRIS in produzione "come è andata
la temperatura del bagno negli ultimi tre giorni?" riceve un errore onesto (non un dato falso —
questo va detto a merito del progetto) ma **zero risposta utile**, su una funzione appena
annunciata nel prodotto. Severità: **Critical** — funzione dichiarata e pubblicizzata (CHANGELOG
3.12.0/3.12.1), verificata rotta in esecuzione sulla casa vera.

Il secondo difetto descritto dallo stesso CHANGELOG 3.12.1 (`accaduto` che leggeva `message` invece
di `state` dal logbook, perdendo il testo di 754 voci su 755) **non l'ho potuto riprodurre**: sto
già parlando con la versione 3.12.0 che lo conteneva, ma la mia chiamata a `accaduto` (6h, tutta la
casa, produzione) non mostra il campo nella forma rotta né in quella corretta in modo
inequivocabile dal solo output — non avevo un evento con `message` non vuoto nella finestra per
discriminare. Non verificato per assenza di un caso di test in natura, non per assenza del difetto.

## Il secondo problema, di ambiente: l'istanza locale è scollegata dalla casa vera

**Verificato eseguendo.** Il log dell'istanza locale (`hiris-local.log`, aggiornato in tempo reale
durante la sessione) mostra il ciclo di riconnessione WebSocket verso Home Assistant fallire in
loop continuo, un tentativo ogni ~13s, per tutta la durata della mia sessione:
```
HA WebSocket disconnected: Cannot connect to host supervisor:80 ssl:default [getaddrinfo failed]
Ricarica dell'inventario entita' non riuscita: Cannot connect to host supervisor:80 ...
rilettura del comportamento fallita: Cannot connect to host supervisor:80 ...
```
`supervisor:80` è il default di produzione (`HA_BASE_URL` non impostata prende
`http://supervisor/core`, `hiris/app/server.py:1123`) — non l'indirizzo diretto
`192.168.1.95:8123` che il COME-SI-ENTRA dichiara per questa istanza. Conseguenze osservate in
esecuzione: `GET /api/entities` → **503** sul locale contro **200** su produzione; `guarda` su
un'area del locale risponde con `"stato_non_letto": true` e stati `null` su ogni entità (contro
stati veri e `stato_leggibile` su produzione); `cerca` segnala **83 entità senza nome nel registro
HA non leggibili** sul locale. `legami` sul locale fallisce sempre con "risposta in forma
inattesa" — **falso positivo di ambiente**, non un difetto del tool: la stessa chiamata su
produzione, e la stessa chiamata fatta a mano al WebSocket vero di HA, restituiscono dati corretti
e nella forma esatta che il codice/la descrizione dichiarano (vedi tabella strumenti). Non è chiaro
se questo sia un problema di setup di QUESTA sessione d'audit (altri filoni condividono la stessa
istanza: il log mostra anche un tentativo di riavvio fallito per porta 8099 già occupata) o una
fragilità reale dell'avvio locale — non l'ho toccato per non interferire con gli altri filoni, ma
segnalo al coordinatore che **l'istanza locale, per la durata della mia sessione, non era
utilizzabile per verificare nulla che dipenda da una lettura live di Home Assistant** (a differenza
di ciò che legge solo l'archivio SQLite già popolato, che ha continuato a rispondere).

## Le 38 rotte HTTP

Registrazioni trovate in `hiris/app/server.py` (`app.router.add_*`, righe 2641-2844): **33** legate
a un path+metodo (più `add_static`). Il perimetro dichiarato nel COME-SI-ENTRA parla di 38 rotte;
un commento nello stesso `server.py` (riga 2749) parla di un censimento tornato "a 43" in un punto
della storia recente del progetto. Non ho ricostruito la cifra esatta con `scripts/censimento.py`
(che indicizza per *percorso*, non per percorso+metodo, e non stampa un totale rotte) — la
differenza fra 33/38/43 è una discrepanza fra documento e conteggio che segnalo, non un difetto
funzionale: nessuna rotta è mancante o fantasma fra quelle che ho cercato nel codice.

| # | Metodo | Rotta | Stato | Come |
|---|---|---|---|---|
| 1 | GET | `/` | **Eseguita** — 200 locale e prod | pagina |
| 2 | GET | `/config` | **Eseguita** — 200 locale e prod | pagina |
| 3 | GET | `/api/health` | **Eseguita** — 200/200, versioni diverse (vedi sopra) | |
| 4 | GET | `/api/config` | **Eseguita** — 200/200 | |
| 5 | GET | `/api/usage` | **Eseguita** — 200/200 | |
| 6 | GET | `/api/usage/storia` | **Eseguita** — 200/200 | |
| 7 | POST | `/api/usage/reset` | Non eseguita (scrive) | solo codice |
| 8 | POST | `/api/chat` | Non eseguita — vietata da mandato | solo codice |
| 9 | GET | `/api/chat/reply/{job_id}` | Non eseguita (nessun job creato: dipende da `/api/chat`) | solo codice |
| 10 | GET | `/api/entities` | **Eseguita** — 200 prod, **503 locale** (WS giù) | difformità osservata |
| 11 | GET | `/api/chat/cronologia` | **Eseguita** — 200/200 | |
| 12 | DELETE | `/api/chat/cronologia` | Non eseguita (scrive) | solo codice |
| 13 | GET | `/api/impostazioni-chat` | **Eseguita** — 200/200 | |
| 14 | PUT | `/api/impostazioni-chat` | Non eseguita (scrive) | solo codice |
| 15 | GET | `/api/models` | **Eseguita** — 200/200 | |
| 16 | GET | `/api/models/config` | **Eseguita** — 200/200 | |
| 17 | PUT | `/api/models/config` | Non eseguita (scrive) | solo codice |
| 18 | POST | `/api/reasoning/claim` | Non eseguita (scrive) | solo codice |
| 19 | POST | `/api/reasoning/submit` | Non eseguita (scrive) | solo codice |
| 20 | POST | `/api/mcp` | **Eseguita** estensivamente (`tools/list`, `tools/call` × 10 strumenti) | canale di lettura, non di scrittura propria |
| 21 | GET | `/api/casa` | **Eseguita** — 200/200, forma coerente col docstring | |
| 22 | GET | `/api/memoria` | **Eseguita** — 200/200 | |
| 23 | PATCH | `/api/memoria/{id}` | Non eseguita (scrive) | solo codice |
| 24 | DELETE | `/api/memoria/{id}` | Non eseguita (scrive) | solo codice |
| 25 | GET | `/api/promesse` | **Eseguita** — 200/200 (`{"promesse": []}` su entrambe, nessuna in sospeso) | |
| 26 | DELETE | `/api/promesse/{id}` | Non eseguita (scrive) | solo codice |
| 27 | GET | `/api/esecuzioni/{id}` | **Eseguita** — 404 su id inesistente, forma coerente col docstring | |
| 28 | GET | `/api/costruzioni` | **Eseguita** — 200/200 | |
| 29 | GET | `/api/costruzioni/{id}` | **Eseguita** — 200 su id reale, 404 su id inesistente | |
| 30 | POST | `/api/costruzioni/{id}/conferma` | Non eseguita — scrive su HA | solo codice |
| 31 | POST | `/api/costruzioni/{id}/ripristina` | Non eseguita — scrive su HA | solo codice |
| 32 | POST | `/api/costruzioni/{id}/rifiuta` | Non eseguita (scrive, anche se solo in archivio) | solo codice |
| 33 | GET | `/api/nucleo` | **Eseguita** — 200/200, testo coerente col docstring (`casa.nucleo.componi()`) | |
| — | GET | `/static/*` | **Eseguita** — 200 su asset reale (`config/main.js`) | |

**Totale eseguite con successo: 18 rotte/percorsi distinti** (20 chiamate contando i due esiti
200/404 su `/api/costruzioni/{id}` e su `/api/esecuzioni/{id}`), più il canale `/api/mcp` usato
ripetutamente. Le rimanenti (tutte le scritture, più `/api/chat` e ciò che ne dipende) sono
giudicate solo leggendo il codice, come da mandato.

## I 13 strumenti MCP

`tools/list` locale e produzione restituiscono lo stesso catalogo di 13 nomi (nessuna difformità di
catalogo fra le due istanze).

| Strumento | Tipo | Eseguito? | Descrizione mantenuta? |
|---|---|---|---|
| `cerca` | legge | **Sì** (prod+locale) | Sì — struttura `trovati`/`candidati`/`ambiguo` e `non_ho_potuto_guardare` come promesso |
| `guarda` | legge | **Sì** (prod+locale) | Sì su produzione (stato, `stato_leggibile`, `ricordi`, `entita_temperatura` tutti presenti); su locale coerente col caso dichiarato "stato non letto" (guasto onestamente segnalato, non nascosto) |
| `legami` | legge | **Sì** (prod; locale in errore per il problema d'ambiente sopra) | Sì su produzione — chiavi tradotte esattamente come da docstring (`entity`→`entita`, `device`→`dispositivo`, `automation`→`automazione`, `floor`→`piano`, `config_entry`→`voce_di_configurazione`), verificate anche contro una sonda diretta al WebSocket di HA |
| `richiama` | legge | **Sì** | Sì — `{"ricordi": [...]}`, lista vuota gestita come da docstring |
| `promesse` | legge | **Sì** | Sì — `{"promesse": [...]}` |
| `andamento` | legge | **Sì** | **Parzialmente no** — la parte "finestra ≤24h → grana dettaglio" mantiene la promessa (verificato: dati veri, `grana: dettaglio`); la parte "finestra lunga → grana oraria" **non la mantiene in produzione**: fallisce sempre (vedi sopra). Non è la descrizione a mentire (il codice fallisce onestamente, non silenziosamente), ma la funzionalità dichiarata nella descrizione dello strumento non è disponibile in pratica su questa installazione finché non si aggiorna a 3.12.1 |
| `accaduto` | legge | **Sì** | Non falsificato né confermato sul campo — l'esecuzione ha prodotto un elenco coerente con la forma dichiarata (`quando`/`nome`/`stato`/`messaggio`/`entita`, `troncato`, `nota`), ma senza un evento con `per_mano_di: HIRIS` nella finestra osservata non ho potuto verificare quella parte specifica della promessa |
| `ricorda` | scrive (store proprio) | No — evitato per il vincolo assoluto "niente POST che cambino stato" | Non verificabile in esecuzione; lettura del codice non desta sospetti |
| `prometti` | scrive (store proprio) | No — stesso motivo | Non verificabile in esecuzione |
| `disdici` | scrive (store proprio) | No — stesso motivo | Non verificabile in esecuzione |
| `esegui` | scrive su HA | No — per mandato | Solo codice: passa da `azione/porta.py`, verifica prima e rilegge lo stato dopo, come dichiarato |
| `costruisci` | scrive config (proposta) | No — per mandato | Solo codice: passa da `azione/costruzione/officina.py`, non scrive mai da solo (richiede `conferma` in turno separato) |
| `conferma` | scrive su HA | No — per mandato | Solo codice |

**Totale eseguiti con successo: 7 su 13** (`cerca`, `guarda`, `legami`, `richiama`, `promesse`,
`andamento`, `accaduto`). Tre giudicati solo da codice per divieto esplicito del compito (`esegui`,
`costruisci`, `conferma`); tre evitati per lo stesso vincolo assoluto nonostante il compito li
elencasse fra i "dieci che leggono" (`ricorda`, `prometti`, `disdici`) — motivato sopra.

## Altre osservazioni minori (verificate in esecuzione, severità bassa)

- **`climate` non traduce lo stato leggibile**: `guarda` su `climate.bagno_1p_t_bagno_1p_t`
  restituisce `"stato": "heat", "stato_leggibile": "heat"` — nessuna traduzione italiana, a
  differenza di `light` (`"off"` → `"spento"`). Non contraddice la descrizione dello strumento
  (che non promette una traduzione completa per ogni dominio), ma è un'incoerenza di prodotto fra
  domini. Severità: minore.
- **83 entità senza nome nel registro HA, non cercabili per nome** (segnalato onestamente da
  `cerca` sul locale, `non_ho_potuto_guardare`): non ho potuto confermare se sia un fatto della
  casa vera (entità davvero senza `friendly_name`) o un sintomo dello stesso specchio-stato non
  letto per il problema WS del locale — non riprodotto su produzione nella stessa chiamata (la
  chiamata di `cerca` su produzione non è stata rifatta esplicitamente per "bagno" con lo stesso
  conteggio). Da riverificare quando l'istanza locale avrà un collegamento HA sano.
- Il file `PRODUCT.md` è annotato quattro volte (10/08, 12/08, 23/08, 24/08) invece di essere
  riscritto: coerente con la disciplina "un verbale non si riscrive" dichiarata nel progetto — non
  un difetto, ma segnalo che chiunque legga solo il corpo del documento senza le annotazioni in
  cima ottiene un quadro falso del prodotto (dieci strumenti che sono tredici, "nessuno tocca la
  casa" quando `esegui`/`costruisci`/`conferma` la toccano). Rischio di lettura, non di codice.

## Cosa NON ho verificato (per costruzione del mandato)

Tutte le rotte e gli strumenti che scrivono: giudicati solo leggendo il codice citato sopra, come
richiesto. Non ho aperto la chat (`POST /api/chat`) né in locale né in produzione. Non ho
confrontato pagina per pagina l'aspetto (compito di un altro filone) — ho verificato solo che le
rotte che le alimentano rispondono con dati coerenti (`/api/casa`, `/api/nucleo`, `/api/costruzioni`,
`/api/promesse`, `/api/memoria`, `/api/entities`).
