# BACKLOG — gli argomenti in attesa di uno sprint

Questo documento non e' storia: e' il **registro**. Ci si scrive quando nasce un argomento, ci si
legge quando si sceglie cosa fare. Non porta una data di redazione perche' non e' la fotografia di
un giorno: e' vivo.

**Sta in git, e non e' un accidente.** Il progetto aveva gia' avuto una `docs/ROADMAP.md`: e' stata
tolta dal tracciamento e messa in `.gitignore` il 30/04/2026 (commit `8c4d615d`), e oggi non esiste
piu' nemmeno sul disco. Un registro che git non vede e' un registro che nessuna sessione puo'
leggere, e sparisce senza che nessuno se ne accorga. Questo file non ha quella scusa: se una voce
non c'e', e' perche' nessuno ce l'ha scritta.

## Come ci si scrive

**Quando il proprietario dice «inseriamo per il prossimo sprint», la voce entra qui, subito**,
prima di continuare il discorso. Non in un appunto, non in una risposta in chat, non nella memoria
di una sessione: qui. Una voce annotata altrove e' una voce persa — ed e' gia' successo.

Una voce e' **atomica**: si deve capire cosa chiede senza andare a cercare altrove. Se il dettaglio
merita un documento, la voce lo nomina; se il documento non esiste, la voce dice «nessun documento»
e si porta dentro tutto cio' che serve a ricostruirla.

Ogni voce dichiara **da dove viene**. La provenienza non e' cortesia: distingue cio' che il
proprietario ha chiesto da cio' che e' emerso misurando, e le due cose non hanno lo stesso peso
quando si sceglie.

## Come si legge

Le voci stanno in tre stati, e lo stato e' **la sezione in cui la voce si trova** — non una colonna
che puo' restare indietro rispetto ai fatti.

| Stato | Vuol dire |
|---|---|
| **In attesa** | Nessuno l'ha ancora scelta. E' il magazzino da cui si pesca. |
| **Scelto** | Entra nello sprint in corso. |
| **Uscito** | Chiuso da un rilascio, che la voce nomina. Il dettaglio sta nel CHANGELOG. |

Una voce non si cancella quando esce: si sposta. Un backlog che dimentica cosa ne e' stato delle sue
voci non sa dire se il lavoro procede.

---

## Scelti — sprint in corso

**Sprint aperto il 04/09/2026 — «la conoscenza prende una forma».**

Perimetro e strada decisi dal proprietario. La strada e' **una spina alla volta, verticale**:
si prende l'appartenenza e la si porta fino in fondo attraverso tutti i lettori — anagrafe,
ricerca, osservatore, briefing, strumenti — e solo dopo si passa oltre. Le tracce e il log
stanno in coda **per conseguenza della strada**: sono una fonte nuova, e nascono sopra
un'appartenenza gia' rifatta invece che accanto a una da rifare.

**La prova che dice quando e' finito**, e non se ne discute:

> **«Quali entita' non rispondono, e di quale integrazione sono?»**
> Oggi: 95 secondi, quindici chiamate, si ferma a 48 su 74, e il giardino resta invisibile.
> Dopo: una chiamata, 74 su 74, e lo stato della casa nomina l'irrigazione ferma.

**La specifica dello sprint è `docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`**: le voci qui sotto restano il
registro (cosa e perché), la spec porta il disegno (come). Sono in ordine di lavorazione.

**Stato al 04/09/2026 — il piano 1 «l'appartenenza» è su `master` (`eec94198`, CI verde.)**
Ha chiuso: la ricerca trova per piattaforma; `view tipo: integrazione` risponde **in una
chiamata** con quante entità non rispondono, quante hanno stato ignoto, quante sono disabilitate
e da quando; il briefing non chiama più «integrazione» il titolo di una voce di configurazione;
l'anagrafe ha il livello dell'istanza (migrazione 6 → 7).

**Nessuna voce passa ancora in «Usciti», ed è deliberato: quello stato lo dà un RILASCIO**, e la
versione non è stata toccata. È il momento in cui si vede perché i tre stati sono distinti — il
lavoro è su `master`, ma la casa non ce l'ha.

Resta al **piano 2**: il guasto nell'osservatore (nome, condizione, isteresi), la regola del
riavvio — sbloccata da `sensor.uptime`, vedi spec §4 ③ — e la cancellazione di `get_error_log()`.

### La conoscenza non ha spina dorsale — le quattro mancanze

`origine: il proprietario, 04/09/2026, dalla verifica «qual e' lo stato della casa?»` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

**La copertura non e' il problema**: 1221 entita', 242 dispositivi, 53 integrazioni, piani, aree,
comportamenti, plance, i ricordi del proprietario. Il problema e' che sono **elenchi senza
relazioni, senza tempo e senza provenienza**. Ognuna delle quattro mancanze qui sotto e' stata
misurata sulla casa vera il 04/09, e ognuna spiega errori veri.

**1 · L'appartenenza.** Il percorso entita' → dispositivo → integrazione non e' percorribile.
- Il briefing dice «un'**integrazione** non sta funzionando: **Abat-jour**». Abat-jour e' un
  **dispositivo** — lo dichiara l'anagrafe di HIRIS stessa (`tipo: dispositivo`,
  `produttore: "LIFX"`, `modello: "LIFX Mini Color"`). Sta leggendo il *titolo del config entry*,
  che per LIFX e' uno per lampadina, e lo chiama integrazione. Il campo `domain` = `lifx` e' nella
  stessa struttura, tre righe sopra nel codice.
- Nella **stessa conversazione**, venti minuti dopo, dice: «Abat-jour, che risulta *spento* non
  *non disponibile*». Due letture diverse della stessa cosa nello stesso dialogo.
- `search "hydrawise"` → **zero risultati**.
- Chiesto il dettaglio delle 74 entita' mute, ci ha messo **95 secondi**, ha aperto le aree una
  per una, ed e' arrivato a **48 su 74** dichiarando di non farcela sulle due piu' grandi. E'
  una sola giunzione, pagata con quindici chiamate.

**2 · Il tempo.** La «fotografia» sono **quattro fotografie di momenti diversi**, presentate come
una: anagrafe `13:59:15`, comportamento `13:59:14`, confronto `13:49:21`, plance **`09:34:27`** —
quattro ore e mezza prima. Tutti questi istanti sono nel dato; **nessuno arriva alla risposta**. La
domanda del proprietario — «come ho la certezza che nulla e' variato da allora?» — non ha risposta
perche' non esiste la domanda.

**3 · La natura.** Un diagnostico, un interruttore di configurazione e una misura reale arrivano
al modello con la stessa forma. `sensor.persons` letto come presenza (li' `categoria: diagnostic`
c'era e nessuno l'ha guardata); gli interruttori di AdGuard riportati «accesi» accanto al forno e
alla lavastoviglie — e li' va detto che **`categoria` e' `null`**: HA non li distingue, l'unico
indizio e' `piattaforma: adguard` e l'area «Configurazione». Quella correzione va **dedotta**, non
letta: e' piu' difficile della prima, e non e' lo stesso difetto.

**4 · La provenienza.** Cio' che HIRIS ha letto da Home Assistant, cio' che il proprietario gli ha
detto e cio' che ha dedotto arrivano indistinguibili. Vedi il caso Viola in «Come HIRIS interpreta
le entita' di Home Assistant»: prima afferma senza fonte, poi rinnega una fonte che ha davanti.

**Nessuna delle quattro e' un errore del modello: sono tutte forma del dato.** Questa voce e' il
livello sotto ai sintomi raccolti nelle altre — e ha un legame stretto con «Il vocabolario del
dato», che il 03/09 era stata rimandata come fetta di rinomina e non lo e' piu'.

**Due difetti minori trovati insieme, che non meritano una voce loro:** la risposta sullo stato
della casa ha affermato «nessun allarme attivo» e «18 automazioni in funzione regolare» — nessuna
delle due frasi compare nel briefing (zero occorrenze di «regolar» e di «nessun allarme» in 5670
caratteri), e la seconda HIRIS non puo' saperla, perche' non legge le tracce. E ha taciuto la
riga in cui il briefing dichiara se stesso incompleto: «Il nucleo superava il tetto di 6000
caratteri: 3 elementi notevoli non inclusi».

### La piattaforma non e' cercabile

`origine: misurato sulla casa vera il 02/09/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

`view` restituisce gia' `"piattaforma": "hydrawise"`, ma `search` indicizza solo nome, area e
dispositivo. Non si puo' chiedere «cosa espone l'integrazione Sonos», ne' «l'irrigazione funziona».
Misurato: `search "sonos"` → **0 risultati**, mentre HA ha 13 entita' con piattaforma `sonos` — si
chiamano «Sala da pranzo».

### La salute di un'integrazione non e' il suo stato

`origine: misurato sulla casa vera il 02/09/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

Un'integrazione `loaded` con **tutte** le entita' morte oggi e' invisibile. Sulla casa: 162 entita'
su 827 (19,6%) sono `unavailable` o `unknown`, comprese tutte e 16 quelle dell'irrigazione
(Hydrawise risponde 403, 40 errori nel log). Ma `hydrawise` e' `loaded`, quindi non compare fra i
guasti, e il briefing non nomina mai «non disponibile». L'irrigazione e' ferma e HIRIS non lo
direbbe. La salute di un'integrazione e' **quante delle sue entita' rispondono**, non il suo `state`.

**Rimisurato il 04/09**, e i numeri di riferimento sono questi: **74 entita' non rispondono su
1221**, e l'irrigazione ne porta **24** — verificato entita' per entita'
(`binary_sensor.giardino_*_irrigazione` e `valve.giardino_*` sono `unavailable`,
`piattaforma: hydrawise`). Il briefing dice «74 entita' non rispondono» e si ferma li': nessun
nome, nessun raggruppamento, nessuna integrazione nominata.

### Il soggetto di un guasto porta il nome e la condizione, non l'identificativo

`origine: il proprietario, 04/09/2026, dopo la sonda sull'osservatore` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

`mind/watcher.py:191` tiene solo l'`entry_id`: il soggetto scritto in archivio e'
`integrazione:01K2CK4GG287VKK18M5J788MRQ`. Il dizionario dell'integrazione **ha** `domain`,
`title` e `state`, e il codice li legge tre righe sopra per decidere se e' un guasto — poi li
scarta. Non e' un dato che manca: e' un dato che si getta.

Misurato sulla casa il 04/09: quel ULID e' **il protagonista piu' frequente dell'intero
archivio**, 34 oggetti su 285 in nove giorni. Nessuno di quegli oggetti dice cosa si sia rotto,
ne' se sia `setup_retry` o `setup_error` — che non sono la stessa cosa. Il corpo, per giunta,
dice sempre `"stato": "aperto"` anche a episodio chiuso, perche' `facts.py:725` scrive quella
costante alla nascita e `close()` la ricopia (`facts.py:712`).

Sta nella stessa funzione dove va messa l'isteresi — vedi «Un episodio per condizione, non
venticinque»: sono due correzioni nello stesso punto del codice, e senza questa le altre voci
della fetta producono oggetti veri e comunque illeggibili.

**Una domanda di disegno da sciogliere prima**: cambiare la forma del soggetto rompe la
continuita' col grezzo gia' scritto (22 giorni di righe con la forma vecchia). Si migra, si
convive, o il nome viaggia in una colonna accanto invece che dentro il soggetto?

### Un episodio per condizione, non venticinque

`origine: misurato sulla casa vera il 02/09/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

L'osservatore apre un episodio nuovo a ogni sfarfallio: **25 episodi di guasto per una sola
integrazione** (`lifx / Abat-jour`, `setup_retry`), e cinque aperti contemporaneamente per la stessa
cosa. Una condizione che va e viene dovrebbe essere un episodio finche' non finisce: il genere
decide la forma, e la forma di una condizione e' la **durata**.

### Come HIRIS interpreta le entita' di Home Assistant — il caso `sensor.persons`

`origine: il proprietario, 04/09/2026, da una chat reale` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

Alla domanda **«quanto tempo la casa ieri e' rimasta vuota?»** HIRIS ha risposto **«mai»**. La
risposta giusta, che l'archivio dell'osservatore aveva gia' scritta quella notte, era **circa
otto ore e mezza**: Paolo fuori 08:08→18:17, Marta 06:39→16:39.

Cosa e' andato storto, nell'ordine in cui e' successo:

1. Ha scelto **`sensor.persons`** — entita' `diagnostic` dell'integrazione *spook* — e ne ha
   dedotto il significato **dal nome**. Non conta chi e' in casa: sta fermo su `2` dal 02/09.
2. Ha presentato la deduzione come un fatto («nessun cambiamento registrato»), senza notare che
   uno stato che non cambia mai non e' una misura di presenza.
3. Corretto dal proprietario, ha tappato il buco con **Viola**: «Viola piu' qualcun altro
   presente». **Viola non e' inventata** — il briefing porta a ogni turno, sotto «Cio' che le
   persone hanno detto», la frase del proprietario stesso: *«in casa vivono anche marta mi
   moglie e viola nostra figlia»*; e in casa c'e' l'area «Cameretta Viola». Inventata era la sua
   **presenza** di ieri, dedotta per far quadrare il numero 2.
4. Poi, alla contestazione, **ha rinnegato una fonte che aveva davanti**: «era una mia
   supposizione, non un dato verificato». Non lo era: era una dichiarazione registrata del
   proprietario, presente nel suo contesto in quel medesimo istante.

I punti 3 e 4 sono **due difetti opposti**, e il secondo e' il piu' grave: prima afferma cio'
che non sa, poi nega cio' che sa. In mezzo c'e' la stessa mancanza — **HIRIS non distingue le
proprie fonti**: cio' che ha letto da Home Assistant, cio' che il proprietario gli ha detto e
cio' che ha dedotto arrivano al modello indistinguibili, e quando qualcuno alza la voce cedono
tutte e tre insieme.
4. La spiegazione finale — «probabilmente conta il numero totale di entita' person» — e' **essa
   stessa una supposizione**, dichiarata tale ma mai verificata.

Il punto che lega questa voce alla fetta A: **la risposta esatta esisteva gia'** negli oggetti
dell'osservatore, con quegli orari precisi al minuto. La chat non li ha interrogati. E' la
stessa legge di «una fonte sola, due lettori», guardata dall'altro capo — qui il secondo lettore
non legge affatto.

**Misurato sulla casa vera il 04/09, e la causa non e' il modello.**

`search` e' una ricerca di **nomi**, non di concetti — ed e' sicura di se' quando sbaglia:

| interrogazione | cosa torna |
|---|---|
| `search "persone"` | **solo** `sensor.persons`, e dichiara `ambiguo: false` |
| `search "presenza"` | **zero risultati** — mentre la gamba «chi c'e'» ne guarda 11 |
| `search "chi c'e' in casa"` | estrae la parola «casa» e offre `weather.forecast_casa` |
| `search "paolo"` | `person.paolo_bettinelli` |

Cioe': le due persone si raggiungono **solo se sai gia' che si chiamano Paolo e Marta**. Chi
chiede «chi c'e' in casa» riceve un candidato solo, quello sbagliato, marcato come non ambiguo.
E' la stessa lacuna di «La piattaforma non e' cercabile», vista dall'altro lato: l'indice non
porta ne' il dominio ne' il significato.

`view` **aveva gia' tutti i segnali** per non cascarci, e nessuno di essi e' una regola da
nessuna parte: `"categoria": "diagnostic"` · `"piattaforma": "spook"` · `"classe": null` ·
`"da_quando"` di **due giorni prima**. Uno stato fermo da due giorni non puo' essere un
conteggio di presenza, e niente in cio' che il modello riceve lo dice.

**La risposta giusta era a una chiamata di distanza**: `logbook(entita="person.paolo_bettinelli",
ore=36)` restituisce `not_home` alle 06:08 UTC e `home` alle 16:17 UTC del 03/09 — cioe'
08:08→18:17 locali, gli stessi minuti che l'osservatore aveva gia' scritto quella notte.

**E c'e' un terzo posto dove il sistema preferisce rispondere invece di rifiutare**: `logbook`
dichiara `required: ["ore"]` nello schema ma **non lo verifica**. Chiamato senza `ore`, o con
nomi di parametro inventati, non solleva: restituisce una finestra a caso, e con `entita`
sbagliata restituisce l'intera casa. Un modello che sbaglia il nome di un argomento riceve dati
plausibili sulla cosa sbagliata invece di un errore.

### Gli strumenti rifiutano invece di indovinare

`origine: il proprietario, 04/09/2026 — «aggiungi tutto il tema»` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

Non e' un difetto: e' **una linea di condotta ripetuta in tre posti indipendenti**, misurati
sulla casa vera il 04/09. Davanti all'incertezza il prodotto risponde con sicurezza invece di
rifiutare.

1. **`search` dichiara `ambiguo: false` su un candidato solo e sbagliato.** `search "persone"`
   torna il solo `sensor.persons` e lo marca come non ambiguo; `search "presenza"` torna zero;
   `search "chi c'e' in casa"` estrae la parola «casa» e offre `weather.forecast_casa`. Le
   persone si raggiungono **solo se sai gia' che si chiamano Paolo e Marta**. Un candidato solo
   non e' la stessa cosa di un candidato certo, e oggi il campo non li distingue.
2. **`logbook` dichiara `required: ["ore"]` e non lo verifica.** Chiamato senza `ore` non
   solleva: sceglie una finestra. Con un nome di argomento inventato lo ignora in silenzio e
   restituisce l'intera casa invece dell'entita' chiesta. Un modello che sbaglia un nome riceve
   dati plausibili sulla cosa sbagliata al posto di un errore.
3. **`view` consegna i segnali e non la regola.** `categoria: diagnostic`, `classe: null` e un
   `da_quando` di due giorni prima erano tutti li'; niente, in cio' che il modello riceve, dice
   che una diagnostica non e' una misura o che uno stato fermo da giorni non puo' essere un
   valore istantaneo.

Il quarto anello — il modello che inventa una persona che non esiste — e' il **sintomo** di
questi tre, non la causa, ed e' l'unico che il proprietario ha potuto vedere.

Ha un legame stretto con «Come HIRIS interpreta le entita' di Home Assistant»: quella voce e' il
caso che l'ha fatto emergere, questa e' la regola che ne esce.

### I calendari si importano, e HIRIS li sa leggere

`origine: il proprietario, 04/09/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

**Richiesta**: importare anche i calendari, e che HIRIS li possa leggere.

**Misurato sulla casa vera il 04/09, e il primo fatto è che la capacità c'era e l'abbiamo tolta.**
`proxy/ha_client.py:1173-1180` lo dichiara per esteso: `get_calendars` e
`get_calendar_events_range` sono **uscite** nella fetta «escono i trentaquattro» (E2, Task 8),
orfane a cascata perché il loro unico chiamante — `tools/calendar_tools.get_calendar_events` —
era uscito a sua volta. Il commento chiude con «nessuna garanzia persa», ed era vero allora:
nessuno le chiamava. Adesso c'è chi le chiamerebbe.

**Cosa c'è sulla casa**, e quanto poco HIRIS ne sa:

| | |
|---|---|
| `calendar.famiglia` · `calendar.personale` | piattaforma `caldav`, due calendari veri |
| `view calendar.famiglia` restituisce | `stato: "on"`, `stato_leggibile: **"acceso"**` |
| `search "calendario"` · `"calendar"` · `"eventi"` · `"agenda"` | **zero risultati, tutte e quattro** |

Due difetti distinti, e il secondo è più insidioso del primo:

1. **Gli eventi non si leggono affatto.** Un calendario, per HIRIS, è una lampadina con due
   stati. Non sa che c'è dentro, né quando, né per chi.
2. **«Acceso» è una traduzione falsa.** Per Home Assistant un'entità `calendar` sta a `on`
   quando **un evento è in corso**, non quando è «accesa». Dire «acceso» a un modello non è
   generico: è **sbagliato**, e lo porta a ragionare su un interruttore invece che su un
   impegno. È lo stesso difetto di `sensor.persons` letto come conteggio di presenza, e
   ricadrà sotto il tema finale dello sprint (§7): **cosa significa uno stato va importato
   dalla documentazione, non dedotto.**

E i due calendari sono raggiungibili **solo se sai già che si chiamano «Famiglia» e
«Personale»** — la stessa lacuna delle persone, sul dominio invece che sulla piattaforma.

**Dove sta nello sprint**: con «le tracce e il log», in coda. Sono la stessa forma di lavoro —
una **fonte nuova** che nasce sopra un'appartenenza già rifatta — e vale anche qui la regola che
il proprietario ha già dato per le tracce: **una fonte sola, due lettori**, lo strumento della
chat *e* l'osservatore. Un calendario che sa dire «domani nessuno è in casa dalle 9 alle 18» è
esattamente ciò che manca a un osservatore che oggi ha tre giorni di storia della presenza.

**Da decidere quando si progetta**: quanto avanti si guarda (un giorno? una settimana?), se gli
eventi si conservano o si rileggono ogni volta, e come si dichiara ciò che il calendario **non**
dice — un calendario vuoto non significa «nessuno ha impegni», significa «nessuno l'ha scritto».

### Le tracce delle automazioni e il log di sistema

`origine: deciso dal proprietario il 31/08/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

Due fonti nuove di HA, e devono essere disponibili **a entrambi i lettori**: lo strumento della chat
E l'osservatore. Una fonte sola, due lettori — l'osservatore «non apre un secondo rubinetto», perche'
due sorgenti degli stessi eventi possono divergere. Le chiamate sono `trace/list`, `trace/get`,
`trace/contexts` e `system_log/list`, tutte WS e tutte `require_admin`.

Misurato sulla casa il 30-31/08: 72 tracce su 16 automazioni, 64 `finished`, 7 `failed_conditions`,
1 `error` — e un'automazione rotta davvero, mai segnalata al proprietario; 17 voci di log, 11
WARNING e 6 ERROR.

Due trappole gia' pagate, che decidono il lavoro e non si vedono nella documentazione:
**le tracce hanno una finestra** (HA ne conserva 5 per automazione, poi la sesta cancella la prima —
decide se si puo' guardare a cadenza o si devono seguire mentre accadono); e **il log arriva gia'
giudicato**, perche' `system_log/list` consegna righe raggruppate da HA con `count` e
`first_occurred`, il che rompe la legge dell'osservatore «scrivi il grezzo, giudica dopo».

### `get_error_log()` si cancella

`origine: deciso dal proprietario il 31/08/2026` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

`proxy/ha_client.py::get_error_log()` ha i test e **zero chiamanti vivi**. Punta a
`/api/error_log`, che su HA 2026.8.3 risponde 404, e **inghiotte il 404 restituendo
`{"errors": 0, "warnings": 0}`**: collegarlo com'e' farebbe dire a HIRIS «zero errori» su una casa
che ne ha 6+11. E' lo zero che afferma. Non e' una migrazione — il vecchio punta a un endpoint che
non esiste piu' e mente quando non lo trova: si cancella il metodo e si cancellano i suoi test.

### Le specifiche di Home Assistant si importano dalla documentazione — il tema finale

`origine: il proprietario, 04/09/2026 — «questo e' il tema finale di questo sprint»` · `documento: docs/design/2026-09-04-la-conoscenza-prende-una-forma.md`

**Richiesta testuale**: «vanno importate e capite le specifiche di HA con la documentazione; per
ogni stato va capito cosa rappresenta e se ci sono altri metadati o parametri che permettono di
capire di piu'. Per migliorare i ragionamenti serve sapere cosa stiamo guardando in profondita' e
capire bene per ogni oggetto le sue caratteristiche.»

E' la voce che chiude lo sprint perche' e' quella che lo rende **duraturo**: le altre otto
correggono cio' che sbagliamo oggi, questa toglie la ragione per cui lo sbagliavamo. Vale la legge
del progetto: **mai un'ipotesi su Home Assistant — prima la documentazione, poi le API vere**.

**Misurato il 04/09: quanti campi che HA manda nel registro delle entita' il codice non nomina
mai.** Conteggio delle occorrenze in tutto `hiris/app`:

| campo di HA | citazioni | cosa ci perdiamo |
|---|---:|---|
| `supported_features` | **0** | cosa un'entita' **sa fare** (una luce che cambia colore, una tapparella che si ferma a meta') |
| `assumed_state` | **0** | HA dichiara «questo stato lo **suppongo**, non l'ho verificato» — ed e' la provenienza, che stiamo cercando altrove |
| `options` | **0** | i valori ammessi di un `select` |
| `config_entry_id` | **0** | l'appartenenza all'istanza (vedi la spina n. 1) |
| `unique_id` · `has_entity_name` | **0** | |
| `capabilities` · `entity_category` · `original_device_class` · `hidden_by` · `original_name` · `platform` | **1 ciascuno** | letti in un punto solo, non conservati come caratteristiche |

`assumed_state` merita una riga sua: **Home Assistant dichiara gia' quando non e' sicuro di uno
stato**, e HIRIS non lo legge mai. Stiamo progettando la certezza del dato mentre il fornitore ce
la sta gia' mandando.

**Il precedente da seguire c'e' gia' in casa**: `briefing.py:69` porta un elenco «copiato da
`homeassistant/generated/entity_platforms.py`», sorvegliato da `tests/test_domain_vocabulary.py`.
Cioe' non si deduce e non si indovina: si importa, si dichiara da dove viene, e una prova si
accorge quando diverge. Questa voce estende quel gesto dai domini a **stati, classi, categorie,
capacita' e attributi**.

Da decidere quando si progetta: cosa si importa a mano e cosa si legge a runtime; dove vive
(tabella generata nel repo o nell'anagrafe); e come si accorge di essere invecchiato quando HA
cambia versione.

---

## In attesa

> **Avvertenza sulla prima stesura (04/09/2026).** Il proprietario aveva chiesto di annotare una
> lista di argomenti per il prossimo sprint, e quella lista **non e' stata salvata da nessuna
> parte**: cercata in tutto il repository, nelle cartelle ignorate, nelle issue e nelle milestone di
> GitHub, non esiste. Le voci qui sotto **non sono quella lista**: sono ricostruite dai documenti
> del repository e da cio' che e' stato misurato sulla casa vera. La lista del proprietario va
> reinserita da lui, e queste voci vanno lette come un fondo di magazzino, non come una sua scelta.

### I comandi verso Home Assistant

`origine: deciso dal proprietario il 04/09/2026` · `documento: docs/design/2026-09-04-i-comandi-verso-home-assistant.md`

Colmare i buchi di scrittura verso HA emersi dallo studio di `ha-mcp`: plance, categorie, etichette
(update e delete), aree e piani, zone, calendari con ricorrenze, gruppi e liste, i 17 helper a
config-flow, blueprint. Lo studio porta la chiamata esatta di ognuno, letta nel loro sorgente. **Non
e' una specifica**: il perimetro non e' stato scelto.

### La sicurezza

`origine: deciso dal proprietario il 04/09/2026` · `documento: docs/design/2026-09-04-la-sicurezza-il-seme.md`

Sprint a se', **dopo** quello dei comandi. Il reperto che lo apre: HIRIS non ha nessuna lista di
servizi vietati. Cio' che oggi rende irraggiungibili `homeassistant.restart`, `hassio.host_reboot`,
`recorder.purge`, `shell_command.*` e' un accidente di forma — quei servizi non dichiarano un
`target`, e un bersaglio vuoto e' sempre stato un rifiuto. La difesa non e' progettata: e'
incidentale, e cade tutta insieme il giorno in cui quella condizione si allarga.

### La scheda della proposta dentro la chat

`origine: il proprietario, segnalata il 03/09/2026` · `documento: docs/design/2026-09-03-i-menu-esecutivi.md §6.4`

L'anteprima con Approva e Rifiuta li' dove la frase la annuncia, senza cambiare pagina. Il
proprietario l'ha voluta segnalata, non fatta allora. Costa **rimettere `tools_called` nella
risposta della chat**, tolto il 17/08.

### Il vocabolario del dato

`origine: il proprietario, rimandata il 03/09/2026` · `documento: docs/design/2026-09-03-i-menu-esecutivi.md §7`

La lingua del database, i valori di dominio e le chiavi dei record fra motore e pagina: **una fetta
sola**, perche' sono la stessa cosa. Rinominare i fatti che ci sono costa la riscrittura di ogni
query che li nomina — al contrario di aggiungere un fatto che manca, che costa una migrazione
additiva e reversibile.


**Decisione del proprietario, 04/09/2026, presa durante lo sprint dell'appartenenza:**
«tutte le nuove colonne nei db vanno in inglese; poi migreremo tutto in inglese in uno
sprint futuro per sanare anche questo problema». **Questa voce e' quello sprint.**

Da qui in avanti quindi: le colonne **nuove** nascono in inglese (le prime sono
`entita.config_entry_id` e `integrazioni.entry_id`, 04/09), e quelle italiane accanto
sono **debito dichiarato**, non un modello da imitare. Nessuna colonna esistente si
rinomina fuori da questa fetta: la migrazione si fa una volta, tutta insieme, o si
resta con un archivio meta' e meta' -- che e' peggio di entrambe le scelte coerenti.

Lo stesso vale per le **chiavi delle risposte** (`entita_totali`, `entita_mute`,
`mute_da`, `entita_disabilitate`, `elenco_incompleto`, `entita_stato_ignoto`): sono
un altro strato dallo stesso problema, e si convertono qui.

### La gamba «acqua» dell'osservatore

`origine: dichiarata nella spec dell'osservatore, mai fatta` · `documento: docs/design/2026-08-26-l-osservatore.md`

32 entita' di irrigazione, **zero osservate**. La gamba e' progettata e non fatta: `valve`+`water` e
`sensor`+`water` — che oggi finirebbe nell'energia, ed e' una risorsa diversa.

### Il prompt dell'obiettivo dell'osservatore

`origine: dichiarata nella spec dell'osservatore, mai fatta` · `documento: docs/design/2026-08-26-l-osservatore.md`

Non esiste ancora: il pavimento e' fisso, e il prompt dovra' solo allargarlo. E' il motivo per cui
**8 domini su 10** fra quelli elencati come funzionanti (luci, interruttori, ventilatori, media
player, valvole...) oggi non producono nessun oggetto — il pavimento non li lascia passare.

### `build.yaml` dichiara una licenza che non e' la nostra

`origine: rilevato il 10/08/2026` · `nessun documento`

`hiris/build.yaml:9` dichiara `org.opencontainers.image.licenses: "MIT"`, etichetta che finisce
nell'immagine Docker pubblicata, mentre `LICENSE` dice «PROPRIETARY SOFTWARE LICENSE». Da sanare
prima di un rilascio.

---

## Usciti

*Nessuno ancora: il registro nasce oggi, 04/09/2026.*
