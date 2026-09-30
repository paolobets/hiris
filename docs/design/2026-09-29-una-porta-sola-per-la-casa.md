# Una porta sola per leggere la casa — `search` interroga, `view` esce, lo specchio non invecchia

`spec · 29/09/2026 · decisioni del proprietario prese in chat il 29/09/2026, disegno approvato a sezioni (1, 2, 3, nucleo, riservatezza)`

> **Come si legge dopo la costruzione.** Il disegno approvato resta com'era; dove il codice ha
> preso un'altra strada lo dice un paragrafo **«Cambiato durante la costruzione: …»** accanto alla
> sezione che cambia, con la ragione.

Nasce dalla batteria delle 28 domande del 29/09/2026 (fetta «le misure complete», fase 2), fatta
sulla casa vera sulle due strade. Sulle 24 domande giudicabili il **ponte** ha dato 13 giuste · 5
incomplete · 6 sbagliate, la **catena** 15 · 2 · 7. Le sbagliate comuni alle due strade sono le
stesse cinque (4, 6, 18, 28, 31): il difetto non è del modello né della strada.

Il proprietario ha dubitato delle prime correzioni proposte — cinque toppe, una per sintomo — e
aveva ragione: nessuna toccava la causa che le accomuna. Questa spec è la strada che ne è uscita.

---

## §0 · Le decisioni del proprietario (29/09/2026)

| # | Domanda | Decisione |
|---|---|---|
| 1 | Toppe o domanda strutturata | **Domanda strutturata alla casa** (strada B), dopo uno spike che l'ha provata sui dati veri (§1) |
| 2 | Uno strumento nuovo o `search` | **Pochi strumenti intelligenti e configurabili**: niente strumento nuovo. «Con un nuovo strumento l'AI come decide?» |
| 3 | `search` e `view` separati o uniti | **Uniti in una porta sola** (`search`), con la profondità decisa dallo strumento |
| 4 | Dettaglio medio | **Fino a 10 voci** |
| 5 | Riepiloghi | **Nessun riepilogo fatto da HIRIS**: le voci con i loro attributi, i conti li fa il modello. Si dichiara solo ciò che NON è stato dato (§2.4) |
| 6 | Entità nascoste | **Escluse per default**, incluse con `includi_nascoste` — e sempre contate fra le escluse |
| 7 | Paginazione | Sì, come valvola: `oltre` + `salta`, più `limite` |
| 8 | Lo specchio | **Nella fetta**: senza, la porta restituisce un insieme completo ma falso |
| 9 | Il nucleo | **Resta, cambia mestiere**: porta ciò che è stabile, non lo stato del momento (§5) |
| 10 | Riservatezza | Credenziali **mai**, nemmeno nel dettaglio completo. Posizione della casa sì. Persone e dispositivi che si spostano: **solo in casa / fuori casa**. In **tutte** le profondità (§3) |
| 11 | Sequenza | Questa fetta: **leggere la casa**. Poi **la storia** (`trend`, `logbook`, `automation_trace`, `system_log`) con la stessa forma. Poi relazioni e promesse se i numeri lo giustificano. Gli strumenti che **scrivono** restano separati apposta |

---

## §1 · I fatti (misurati il 29/09/2026, v3.70.0)

**Le cinque cause**, ognuna con la riga di codice e la prova dal vivo (memoria
`project_hiris_dati_corretti`):

1. **Le luci di servizio accese sono NASCOSTE** (`is_hidden_entity`) e senza area.
   `digest_visible_entity_ids` (`home_space/briefing.py:815`) le toglie dal nucleo, `view(area)` le
   sposta in `entita_nascoste` e la descrizione dello strumento dice «non proporle mai». Lo specchio
   le ha giuste (`on`): non è lo specchio.
2. **`view(area)` non ha un tetto.** Telecamere: 287 entità (120 disabilitate con stato vuoto),
   ~64.000 caratteri; «senza area» ~126.000. Sul ponte oltre il limite della CLI (25.000 token per
   risultato MCP, documentazione di Claude Code), che lo sostituisce con un rimando a un file che il
   modello non può leggere.
3. **«68» contro 97 non disponibili**: un filtro voluto ma non dichiarato nella frase
   (`briefing.py:866-893`), più **lo specchio stantio dopo un riavvio di Home Assistant**
   (`proxy/entity_cache.py:626`, residuo dichiarato): 15 entità diverse da HA dopo il riavvio delle
   09:11.
4. **`search` confronta parole intere** (`memory/resolver.py:197-212`): «rifiuti» e
   «indifferenziata» danno zero; «rifiuto» dà tutte e cinque.
5. **Il nucleo taglia le automazioni dalla coda** (tetto 6.800, `briefing.py:1786`): 12 su 17, fra
   le escluse le due più vecchie. Il commento «20 su 20» (`briefing.py:1773`) è falso.

**La causa comune.** Il modello ha due porte: `search` trova **per nome**, `view` apre **un
contenitore**. Non può chiedere alla casa «tutte le luci accese», «tutte le automazioni», «ciò che
non risponde»: ogni domanda di scansione cammina area per area. `view` è chiamata 195 volte in 30
giorni; oggi 24 turni su 56 l'hanno usata, in media 4,6 volte, 14 turni tre volte o più.

**Lo spike** (scratchpad, buttato; filtro per dominio e stato sull'anagrafe + la fotografia degli
stati, nascoste e senza area comprese):

| domanda | oggi ponte | oggi catena | domanda strutturata |
|---|---|---|---|
| #4 luci accese | 6 giri, 140.899 car., 270k token, **sbagliata** | 140.075 car., 43 s, **sbagliata** | **318 car., giusta** |
| #6 non rispondono | 10.083 car., sbagliata | 17.544 car., 86 s | 97 = 66 visibili + 21 di servizio + 10 nascoste |
| #31 automazioni ferme | 194k token, sbagliata | 19.464 car., sbagliata | **17 su 17** ordinate, 2.466 car. |

Lo spike **non** prova che il modello scelga i filtri: lo prova solo la batteria dal vivo (§9).

**Taglie con i default decisi** (nascoste, di servizio, disabilitate fuori): automazioni 17, luci
43, switch 26, soggiorno 32, cucina 9 — una pagina da 50. Non disponibili 66, Telecamere 63 — due.
Senza area 145, sensori 158 — tre o quattro. Tutta la casa 400.

---

## §2 · `search`: la porta che interroga la casa

`view` esce. `search` resta col suo nome (il modello lo conosce, guida e nucleo lo nominano) e
cambia mestiere: da «trova un riferimento per nome» a «restituisci l'insieme che corrisponde ai
filtri». **Un riferimento singolo è un insieme di una voce**: una forma di risposta sola, e
l'ambiguità di oggi («due Bagno») è un insieme di due voci, marcato come oggi.

### §2.1 · I generi

`genere`: `entita` (predefinito) · `area` · `dispositivo` · `automazione` · `script` · `ricordo` ·
`integrazione` — tutto ciò che `view` sapeva aprire. I filtri valgono dove hanno senso, e la
descrizione lo dice per ciascuno.

> **Cambiato durante la costruzione: i dispositivi si trovano per nome (29/09/2026).** La vecchia
> `search` trovava un dispositivo dal nome («la lavatrice»); perderlo sarebbe stato una regressione
> contro «tutto ciò che `view` sapeva aprire». Una domanda solo di `nome` restituisce quindi anche
> righe `dispositivo` (id, nome, genere, area), oltre a quelle delle entità e delle aree.

> **Cambiato durante la costruzione: `riferimento` da solo arriva a ricordo e integrazione, e uno
> che non esiste lo dice (30/09/2026).** Una domanda fatta del solo `riferimento` che nessuna riga
> prende (`house_query._only_the_reference`, `_missing_reference`) non si ferma a `trovate: 0`:
> senza genere un numero va al ricordo e il dominio di una piattaforma nota va all'integrazione;
> con il genere risponde il dettaglio di `queries.view`, che trova anche le pseudo-aree come
> `__senza_area__`. Se non c'è nulla risponde `esiste: False` con un `suggerimento` (oppure
> `non_disponibile`, se è caduto uno dei registri aree, entità, dispositivi, integrazioni, perché
> «non esiste» sarebbe falso). `trovate` vale 0 per ogni voce che dice `esiste: False`. Una cosa
> che un'entità, un'area o un dispositivo prendono vince sempre; con altri filtri accanto,
> `trovate: 0` resta la risposta onesta.

### §2.2 · I filtri — tutti facoltativi, combinabili

| parametro | valori | note |
|---|---|---|
| `nome` | testo | confronto per frammento **e per radice** («rifiuti» trova «rifiuto», «indifferenziata» trova «Indifferenziato»); sostituisce `testo` |
| `tipo` | il dominio di HA (`light`, `sensor`, `automation`…) | elenco chiuso, dalla casa |
| `stato` | `on`, `off`, `unavailable`, `unknown`, `home`… | per le automazioni: abilitata o no |
| `classe` | la `device_class` (`battery`, `motion`, `temperature`…) | solo entità |
| `area`, `piano` | i nomi del nucleo | `area="senza area"` è un valore valido |
| `integrazione` | la piattaforma (`tuya`, `reolink`…) | |
| `fermo_da`, `cambiato_da` | durata (`30d`, `2h`) | per automazioni e script conta l'ultima esecuzione |
| `sopra`, `sotto` | numero | solo stati numerici |
| `in_esecuzione` | vero/falso | solo automazioni e script (`current > 0`) |
| `includi_nascoste`, `includi_servizio` | vero/falso, default falso | |
| `ordina` | `nome` · `ultimo_cambio` · `valore` | |
| `limite` | 0–50, default 50 | `limite=0` → solo `trovate` ed `escluse` |
| `salta` | intero | la pagina successiva |

**Non** entrano: le **etichette** (0 entità le usano in questa casa: peso nella descrizione senza
uso), e «cosa tocca un'automazione» (già servito da `related` e dal dettaglio completo).

> **Cambiato durante la costruzione: un filtro che non vale si dice, non si lascia cadere
> (29-30/09/2026).** La spec diceva «solo entità» per `classe`, `sopra`, `sotto` e non diceva cosa
> succede a chi li usa altrove; ma §2.4 vieta il filtro taciuto. Con un genere di comportamento
> (`automazione`, `script`) `classe`, `sopra` e `sotto` rispondono `{"errore": ...}`; lo stesso
> vale per ogni filtro fuori dall'elenco del genere (`house_query._FILTERS_BY_KIND`: aree e
> dispositivi, ricordi e integrazioni hanno il loro), compreso `in_esecuzione` senza genere. Il
> messaggio nomina i filtri validi. `includi_nascoste`, `includi_servizio`, `ordina`, `limite` e
> `salta` non sono filtri e non danno mai errore. Per gli stessi generi `area`, `piano` e
> `integrazione` valgono davvero: le automazioni li prendono dalla voce dell'anagrafe con lo stesso
> id, i dispositivi dall'albero delle aree.

> **Cambiato durante la costruzione: `nome` confronta anche gli alias (30/09/2026).** Il confronto
> per frammento e per radice guarda il nome e gli alias di un'entità e di un'area
> (`_any_name_matches`); l'anagrafe non dà alias ai dispositivi.

> **Cambiato durante la costruzione: «luce» e «luci» si trovano (30/09/2026).** La radice di
> `memory/resolver.py` tagliava le parole corte: «luce» non trovava «Luci». Ora una parola di 4
> lettere che finisce in vocale si confronta intera e cambia solo nella coppia singolare/plurale
> (`_NUMBER_PAIRS`: -a/-e, -e/-i, -o/-i). Costo dichiarato: la regola conosce la grammatica, non il
> significato, quindi «casi» trova anche «case» e «sale» anche «sala».

### §2.3 · La profondità, decisa dallo strumento

| voci trovate | ogni voce porta | peso massimo |
|---|---|---|
| **1** | il dettaglio completo di oggi di `view` (attributi, capacità; per un'automazione inneschi e azioni) — con il filtro di §3 | come oggi per una cosa |
| **2–10** | id, nome, area, stato, attributi di stato, ultimo cambio; per automazioni e script ultima esecuzione, modalità, in esecuzione — con il filtro di §3 | ~10.000 car. |
| **oltre 10** | id, nome, area, stato, ultimo cambio: una riga | 50 righe, ~6.000 car. |

Il tetto sta **nella regola**, non in un taglio a valle: nessuna risposta supera la soglia che tiene
il ponte sotto i 25.000 token, per costruzione.

> **Cambiato durante la costruzione: il dettaglio completo ha un tetto di 50 righe (30/09/2026).**
> La riga «1 voce = il dettaglio di oggi» reintroduceva la causa 2 di §1: un'area da 287 entità
> apriva ~94.000 caratteri, e la «soglia» stava in una prova che usava un dettaglio finto. Il
> dettaglio completo di un'area, di un dispositivo e di un'integrazione (le mute) tiene le righe
> annidate (`entita`, poi `entita_nascoste`, le visibili per prime) a `queries.ROWS_MAX` = 50 **in
> tutto**; il resto esce in `oltre` (`{"entita": n, "entita_nascoste": m, "suggerimento": ...}`)
> con l'invito a restringere con `search`. `entita_mute` resta il numero intero. Misurato sulla
> casa di prova (Telecamere 287 entità): 20.800 caratteri per l'area, 21.500 per dispositivo e
> integrazione. **`BRIDGE_CEILING_CHARS` (30.000) è dunque un limite sulle righe, non sui
> caratteri**: è la soglia con cui i cancelli misurano, non una garanzia; 50 righe molto ricche
> arrivano a ~32.700 caratteri (~13.000 token), sotto i 25.000 del ponte con un margine di circa il
> doppio.

### §2.4 · La risposta — sempre la stessa forma

```
trovate:    quante voci corrispondono ai filtri
escluse:    { nascoste: 2, servizio: 21, disabilitate: 120 }   ← cosa NON e' stato dato, e perche'
profondita: completa | media | corta
voci:       [ ... ]
oltre:      quante restano dopo il limite, e come chiederle (salta=…)
```

**Nessun riepilogo** (decisione 5): niente «4 accese, 3 spente». `escluse` non è un riepilogo, è la
dichiarazione di ciò che manca: senza, «nessuna luce accesa» tornerebbe a essere una risposta falsa
data con sicurezza — con i default decisi, «luci accese» trova 0 voci visibili e **2 nascoste**.

La descrizione dice: «se `oltre` è maggiore di zero, **restringi** con un filtro; scorri con
`salta` solo se ti servono davvero tutte» — ogni pagina è un giro, e le pagine lette restano nella
cronologia.

> **Cambiato durante la costruzione: le disabilitate si contano dappertutto (29-30/09/2026).**
> La regola «disabilitate sempre escluse e contate» valeva per la ricerca; il dettaglio di un
> dispositivo le elencava, marcate. Ora area, dispositivo e integrazione le tolgono da `entita` e
> da `entita_nascoste` e le contano in `entita_disabilitate` (una disabilitata e nascosta insieme
> resta fra le disabilitate); `disabilitato` del dispositivo resta. Anche i dispositivi disabilitati
> escono dalle righe della ricerca e si contano sotto `disabilitate`.

> **Cambiato durante la costruzione: i registri caduti si dichiarano anche per il piano
> (30/09/2026).** `non_ho_potuto_guardare` non vale solo per una domanda con `nome`: una domanda
> con `piano` (senza `nome`) dichiara il registro dei piani caduto, altrimenti un `trovate: 0`
> sarebbe una risposta falsa data con sicurezza. Le etichette non si dichiarano: la porta non le
> filtra (`_SEARCHED_STORES`).

> **Cambiato durante la costruzione: la memoria serve solo al dettaglio del ricordo
> (30/09/2026).** `search` non aspetta più la memoria per rispondere a una domanda di soli filtri:
> senza memoria il ricordo risponde `esiste: False, non_disponibile: True`, e gli altri dettagli
> escono con `ricordi_non_letti` invece di un `ricordi: []` che direbbe «nessuno».

---

## §3 · Il filtro di riservatezza — in tutte le profondità

Oggi lo specchio tiene **tutti** gli attributi (`entity_cache.py:366`, «nessun attributo
sparisce»), e `view` li consegna per una voce: sulla casa vera 18 entità portano coordinate GPS e 67
un indirizzo IP o MAC. Con risposte a più voci diventerebbero raccoglibili in blocco verso i modelli
cloud. Decisione 10:

- **Credenziali**: mai, in nessuna profondità (la cesta `CREDENTIALS` dello specchio non esce).
- **Posizione della casa** (`zone.home`, latitudine e longitudine): **sì** — serve a sole, meteo,
  orari.
- **Persone e dispositivi che si spostano** (`person`, `device_tracker`): **niente coordinate**
  (`latitude`, `longitude`, `gps_accuracy`), niente `in_zones`, e lo **stato ridotto a in casa /
  fuori casa** — il nome di una zona («Lavoro») direbbe già dove sono.
- **Identificativi di rete** (`ip`, `mac`, `host_name`): fuori (confermato dal proprietario in
  revisione, 29/09/2026).

È una **stretta** rispetto a oggi. Il filtro vive in **un punto solo** (la porta, non lo specchio:
lo specchio serve anche a chi agisce e a chi verifica) e ha la sua prova.

> **Cambiato durante la costruzione: le altre zone perdono le coordinate (29/09/2026).** Il
> proprietario: «la posizione di casa sì»; le altre zone rivelerebbero dove vanno le persone. Solo
> `zone.home` tiene `latitude` e `longitude` (`privacy.HOME_ZONE`); ogni altra `zone.*` le perde.

> **Cambiato durante la costruzione: chi si sposta lo decide il vocabolario (29/09/2026).**
> `privacy.MOVING_DOMAINS` non è un insieme scritto a mano né letto dal quadro dei giudizi caricato
> a runtime: deriva dal vocabolario statico dei tipi (`type_vocabulary`, genere `presenza`, cioè
> `person` e `device_tracker`). Una porta che dipendesse da un quadro caricato pigramente sarebbe
> aperta finché non si carica; un dominio aggiunto a `presenza` è redatto da solo.

> **Cambiato durante la costruzione: il filtro scende nelle righe annidate (30/09/2026).** Il
> primo filtro rediggeva solo la voce di primo livello: il dettaglio di un'area o di un dispositivo
> porta `entita` e `entita_nascoste`, e lì una persona in «Palestra» o un telefono in «Lavoro»
> uscivano interi. `privacy.redact_row` ora è ricorsiva sulle liste di dizionari (il punto di
> redazione resta uno), e quando lo stato di chi si sposta si riduce a `not_home` escono con lui
> `stato_leggibile` e `stato_non_reso`, che potevano ripeterlo.

---

## §4 · `view` esce ovunque

Consumatori misurati nel codice: `home_space/tools.py` (il catalogo), `home_space/queries.py`,
`home_space/briefing.py` (il nucleo la nomina), `keeper/exchange.py:59` (`SOLA_LETTURA`, i cerchi
di strumenti degli attori). Più guida, descrizioni e prove. Un cancello verifica che nessun elenco
di strumenti nomini più `view`. **Il gateway MCP su .31 non conta**: decisione del proprietario in
revisione (29/09/2026), «da non più calcolare, lo eliminiamo» — non è un consumatore da
preservare, e la sua dismissione è un lavoro a parte.

I non amministratori (3.69.0) sono limitati per strumento, non per entità: `search` resta fra quelli
di sola lettura, nessun cambio di permessi.

---

## §5 · Il nucleo cambia mestiere

Oggi 6.523 caratteri in sette sezioni. Il nucleo ha reso possibili risposte giuste **senza
strumenti** (#9, #10, #19, #20; sulla catena anche #12 e #30) — e una sbagliata con sicurezza su
**tutte e due** le strade (#18, «come sta la casa»: ha preso per buona la fotografia).

**La regola: il nucleo porta ciò che è stabile, non lo stato del momento.**

| sezione | car. | esito |
|---|---|---|
| La casa (riferimento, ora, unità, piani, aree) | 2.948 | **resta**: è il vocabolario dei filtri |
| Cosa non va in casa | 266 | **resta** |
| Notevole adesso | 118 | **esce**: è la fotografia che ha prodotto il «68» e il falso allarme |
| Cosa si può chiedere alle cose | 579 | **resta**: serve per agire |
| Ciò che la casa fa da sola | 1.281 | **resta, intera**; se non ci stesse, dichiara quante mancano e `search(genere=automazione)` |
| Ciò che le persone hanno detto | 835 | **resta** |
| Ciò che HIRIS ignora | 490 | **resta, aggiornata**: `search` e `includi_nascoste`, non `view` |

Il commento falso a `briefing.py:1773` si corregge. `mind/observer.py:98` usa la stessa funzione
del digesto: l'osservatore va riletto contro questa regola nella costruzione.

> **Cambiato durante la costruzione: con «Notevole adesso» esce anche il codice che lo serviva
> (29/09/2026).** Il proprietario, «il codice morto va eliminato»: la sezione usciva dal nucleo e
> con lei i quattro parametri di `compose` che nessuno leggeva più, il calcolo lato chiamante in
> `handlers_home_space.compose_briefing` e `TypeJudgments.is_notable`, il cui unico lettore era
> quella sezione. **Resta un residuo, aperto in BACKLOG:** il campo `notevole` del giudizio di tipo
> (seme, API, pagina dei giudizi, `watcher-sapere.js`) non ha più un lettore.

---

## §6 · Lo specchio si risincronizza a ogni riconnessione

`ha_client._ws_loop` avvisa già a ogni riconnessione registro dei servizi, anagrafe e plance
(`proxy/ha_client.py:2590-2605`). Lo specchio degli stati è il quarto, e non era avvisato.

- A ogni riconnessione: `EntityCache.load` (esiste).
- Gli eventi arrivati **durante** la rilettura si applicano **dopo**: una fotografia più vecchia non
  li sovrascrive.
- `loaded` resta vero solo dopo una lettura completa.
- Il residuo dichiarato a `entity_cache.py:626` esce.

> **Cambiato durante la costruzione: la rilettura parte anche alla prima connessione, e le
> riletture si mettono in fila (30/09/2026).** `ha_client` avvisa «riconnessione» a ogni
> connessione riuscita, la prima compresa (`server.py`, ascoltatore `specchio-riconnessione`):
> all'avvio si legge e poi si rilegge, e la rilettura chiude la finestra fra `load` e
> `subscribe`, come fa l'anagrafe. Due riconnessioni ravvicinate non si sovrappongono:
> `EntityCache.reload` è serializzata da un `asyncio.Lock` (`_reload_lock`), e il tampone degli
> eventi si chiude in un `finally`, quindi una rilettura cancellata non lo lascia aperto.

---

## §7 · Il registro dei turni salva gli argomenti

Oggi salva solo i nomi degli strumenti: non si è potuto verificare quale ricerca avesse perso
l'Indifferenziato. Per chiudere (§9) serve vedere se il modello usa i filtri. Gli argomenti di ogni
chiamata entrano nel registro locale delle misure (`consumi.db`), sulle due strade, passati dallo
stesso filtro di §3; restano in casa come il resto del registro, con la sua retention.

> **Cambiato durante la costruzione: «lo stesso filtro» sono due insiemi e una funzione
> (29-30/09/2026).** `compact_tool_args` (`usage/store.py`) maschera i segreti di una chiamata di
> servizio (`code`, `pin`, `password`, `token`, `user_code`, `alarm_code`, `lock_code`…) con un
> insieme suo, `entity_cache.SERVICE_CALL_SECRETS`, unito agli attributi dello specchio in
> `CALL_ARGUMENT_SECRETS`; la funzione di controllo (`is_credential`) è una sola e le regole sul
> valore sono comuni. Non si è usata una lista unica perché un attributo di stato che si chiama
> `code` (Tuya) non deve sparire dallo specchio. Le posizioni (`latitude`, `longitude`…) si
> tolgono con `privacy.POSITION_ATTRIBUTES`, la stessa fonte di §3. **Il testo libero non si
> maschera**: il filtro guarda la chiave e la forma del valore, e il limite è dichiarato nel
> docstring e fissato da una prova.

---

## §8 · Fuori da questa fetta

- **La storia** (`trend`, `logbook`, `automation_trace`, `system_log`): la fetta successiva, stessa
  forma.
- `related`, `fetch`, promesse, calendario, ricordi (`remember`): restano.
- **Gli strumenti che agiscono** (`execute`, `propose`, `confirm`): separati apposta, per sempre — i
  cancelli di sicurezza si reggono sulla separazione fra leggere e scrivere.
- **L5 — il `ToolSearch` spento sul ponte** (`ENABLE_TOOL_SEARCH=false`): una prova misurata a
  parte. Si cambia una cosa alla volta.
- Gli strumenti che la batteria non tocca restano come sono.

---

## §9 · Come si chiude

**Prima**: esce la **3.70.1** (giri del ponte, modello della catena, batteria): i numeri del «dopo»
devono essere affidabili. Poi questa fetta esce come **3.71.0**, e si rilancia **la stessa
batteria** (28 domande + le 4 con effetti) sulle due strade, giudicata coi criteri scritti prima.

È chiusa se:

1. nessuna delle cinque cause di §1 si ripresenta;
2. le domande **4, 6, 12, 18, 28, 30, 31, 32** non sono più sbagliate su nessuna strada;
3. **zero chiamate a `view`**, e il registro mostra che le domande di scansione usano i filtri;
4. la #4 scende **sotto i 50.000 token** (oggi 270.000 sul ponte);
5. la latenza mediana non peggiora su nessuna strada;
6. dopo un riavvio di Home Assistant, specchio e `/api/states` coincidono.

Se il modello non sceglie i filtri e continua a scandire, lo dice la batteria (criterio 3): si
corregge la descrizione di `search` prima del rilascio stabile.

---

## §10 · Prove

- La porta come **funzione pura**, su un'anagrafe e stati finti costruiti come quelli veri: nascoste
  escluse e contate; senza area; disabilitate; le tre profondità a 1, 10 e 11 voci; il limite di 50
  con `oltre` e `salta`; `limite=0`; filtri combinati; il confronto per radice.
- **Cancello del peso**: su un'anagrafe da 300 entità nessuna risposta supera la soglia del ponte.
- **Cancello della riservatezza**: coordinate di persone e dispositivi, identificativi di rete e
  credenziali non escono in nessuna profondità; `zone.home` sì; lo stato di una persona è solo in
  casa / fuori casa.
- **Cancello della scrittura**: la porta non raggiunge nessuna chiamata che scrive su Home Assistant.
- **Cancello di `view`**: nessun elenco di strumenti la nomina.
- **Lo specchio**: una riconnessione con eventi arrivati durante la rilettura; nessuno si perde.
- Ogni prova con la **mutazione eseguita** e vista rossa.
