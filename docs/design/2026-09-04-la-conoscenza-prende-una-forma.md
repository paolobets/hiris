# La conoscenza prende una forma

*Specifica · 04/09/2026 · lo sprint dopo «i menu esecutivi» (3.21.1)*

> **Stato**: specifica. Perimetro e strada sono decisi dal proprietario; le misure sono state
> prese sulla casa vera il 04/09 prima di scrivere una riga di disegno. Ciò che non è stato
> misurato è dichiarato tale, e non è stato progettato.

---

## §0 · Da dove viene

Non da un'idea: da tre verifiche fatte dal vivo nella stessa giornata, ognuna delle quali doveva
confermare qualcosa e ha invece trovato altro.

1. **«Analizziamo cosa estrae l'osservatore.»** Nove giorni di archivio, 285 oggetti. Il
   protagonista più raccontato della casa è la stringa `integrazione:01K2CK4GG287VKK18M5J788MRQ`.
2. **«Quanto tempo la casa è rimasta vuota ieri?»** Risposta: «mai». La risposta giusta —
   otto ore e mezza — era già scritta nell'archivio dell'osservatore da quella notte.
3. **«Qual è lo stato della casa?»** Quattro affermazioni, di cui due senza fonte e una che
   chiama integrazione un dispositivo.

I tre episodi sembravano difetti diversi. Non lo sono: **sono la stessa cosa, vista da tre
lati.** Nessuno dei tre è un errore del modello.

> **La tesi di questo sprint.** La conoscenza di HIRIS è ampia e non ha forma. Sono elenchi
> **senza relazioni, senza tempo, senza natura e senza provenienza**. Ogni errore misurato oggi
> nasce da una di queste quattro mancanze, non dal ragionamento che ci sta sopra.

Questa fetta prende **la prima delle quattro** — l'appartenenza — e la porta fino in fondo
attraverso tutti i lettori. Le altre tre restano nel registro (`docs/BACKLOG.md`), dichiarate.

---

## §1 · La prova che dice quando è finito

Una domanda sola, e non se ne discute dopo:

> **«Quali entità non rispondono, e di quale integrazione sono?»**

| | |
|---|---|
| **Oggi** | 95 secondi, quindici chiamate, si ferma a **48 su 74**, e il giardino resta invisibile |
| **Dopo** | **una** chiamata, **74 su 74**, e lo stato della casa nomina l'irrigazione ferma |

Il numero «95 secondi / 48 su 74» non è una stima: è ciò che HIRIS ha fatto il 04/09 quando gli
è stato chiesto il dettaglio delle entità mute. Ha aperto le aree una per una, ed è arrivato a
metà dichiarando di non farcela sulle due più grandi.

Il tema finale (§7) ha una sua prova, perché è l'unico pezzo che non serve a rispondere a questa:

> **«Cosa sa fare questa entità, e quanto è certo il suo stato?»**
> Oggi non c'è risposta: nessuno dei due campi viene mai letto.

---

## §2 · Il referto — cosa è stato misurato

Tutto ciò che segue è stato letto dalla casa vera o dal codice, il 04/09/2026. Serve perché
**una spec che non porta i numeri che l'hanno motivata invecchia senza che nessuno se ne
accorga**.

### 2.1 L'osservatore, nove giorni (26/08 → 03/09)

285 oggetti, **47 protagonisti distinti** su 1221 entità.

| genere | oggetti | |
|---|---:|---|
| energia | 149 (52%) | i 17 sensori di **un solo** inverter, ogni giorno |
| presenza | 58 (20%) | due persone e i loro due telefoni |
| guasto | 50 (17%) | in 7 giorni su 9, **un solo protagonista distinto** |
| funzionamento | 24 (8%) | |
| sicurezza | 4 (1%) | |
| **comfort** | **0** | e il pavimento ne guarda **25 soggetti** |

### 2.2 I quattro guasti di ieri, e la griglia che li ha fatti quattro

```
03:07 ──> 08:46      buco 10 min
08:56 ──> 15:26      buco 10 min
15:36 ──> 22:16      buco 10 min
22:26 ──> ancora aperto
```

`server.py:2646`: `trigger="interval", minutes=10`. **Ogni confine è esattamente un giro del
rilevatore.** Non è la casa che sfarfalla: è il nostro campionamento senza isteresi. Un solo giro
in cui HA non elenca l'integrazione fra i problemi — cosa che `setup_retry` fa per costruzione,
perché *ritenta* — chiude l'episodio.

### 2.3 Il corpo di un guasto non dice cosa sia il guasto

```json
[1071] integrazione:01K2CK4GG287VKK18M5J788MRQ   15:36 -> 22:16
{ "stato": "aperto", "comprimari": [], "misure": {} }
```

`"stato": "aperto"` su un episodio **chiuso alle 22:16**. Non è una svista: `facts.py:725` scrive
la costante `"aperto"` alla nascita e `facts.py:712` la ricopia alla chiusura. Ogni oggetto di
guasto in archivio dice `aperto`, sempre.

E `watcher.py:191`, che decide cosa finisce in archivio:

```python
ident = str(i.get("entry_id") or "").strip()
if ident:
    open_conditions.add(f"integrazione:{ident}")
```

Il dizionario `i` **ha** `domain`, `title` e `state`; il codice li legge tre righe sopra per
decidere se è un guasto, poi tiene solo l'`entry_id`. **Non è un dato che manca: è un dato che si
getta.** La stessa correzione è già stata fatta nel briefing e non nell'osservatore — lo dichiara
il docstring di `briefing.py::_integrations_notice`: *«HIRIS salvava lo stato, buttava il motivo…
poteva solo contare le entità non disponibili e non sapere perché»*.

### 2.4 La ricerca è una ricerca di nomi

| interrogazione | risultato |
|---|---|
| `search "persone"` | **solo** `sensor.persons` — e `ambiguo: false` |
| `search "presenza"` | **zero risultati** |
| `search "chi c'è in casa"` | estrae «casa» → `weather.forecast_casa` |
| `search "hydrawise"` | **zero risultati** |
| `search "sonos"` | **zero risultati** (13 entità hanno quella piattaforma) |
| `search "paolo"` | `person.paolo_bettinelli` ✓ |

Le persone si raggiungono **solo se sai già che si chiamano Paolo e Marta**.

### 2.5 `view` consegna i segnali, non la regola

```json
{ "id": "sensor.persons", "nome": "Persone", "stato": "2",
  "classe": null, "categoria": "diagnostic", "piattaforma": "spook",
  "da_quando": "2026-09-02T17:54:47+00:00" }
```

Quattro segnali che quello non è un conteggio di presenza — e nessuno di essi è una regola da
nessuna parte. Restava il nome.

**La risposta giusta era a una chiamata di distanza**: `logbook(entita="person.paolo_bettinelli",
ore=36)` → `not_home` 06:08 UTC, `home` 16:17 UTC = **08:08→18:17 locali**, gli stessi minuti che
l'osservatore aveva già in archivio.

### 2.6 Gli strumenti non rifiutano

`logbook` dichiara `required: ["ore"]` nello schema e **non lo verifica**: chiamato senza `ore`
non solleva, sceglie una finestra; con un nome di argomento inventato lo ignora in silenzio e
restituisce l'intera casa invece dell'entità chiesta.

### 2.7 Lo stato della casa, quattro affermazioni

Su 5670 caratteri di briefing:

| frase della risposta | occorrenze nel briefing |
|---|---|
| «**nessun allarme attivo**» | **0** |
| «in funzione **regolare**» (18 automazioni) | **0** |

La seconda HIRIS **non può** saperla: non legge le tracce. E ha taciuto la riga in cui il
briefing dichiara sé stesso incompleto: *«Il nucleo superava il tetto di 6000 caratteri: 3
elementi notevoli non inclusi»*.

### 2.8 «Un'integrazione: Abat-jour»

```json
{ "tipo": "dispositivo", "nome": "Abat-jour",
  "produttore": "LIFX", "modello": "LIFX Mini Color" }
```

L'anagrafe di HIRIS lo classifica **dispositivo**. Il briefing legge il *titolo del config entry*
— che per LIFX è uno per lampadina — e lo chiama integrazione. Venti minuti dopo, nella stessa
conversazione: *«Abat-jour, che risulta spento non non disponibile»*.

### 2.9 Le entità mute, per piattaforma

999 entità percorse in 16 aree.

| piattaforma | entità | `unavailable` | `unknown` | % muta |
|---|---:|---:|---:|---:|
| **hydrawise** | 30 | **24** | 0 | **80%** |
| mobile_app | 66 | 38 | 2 | 61% |
| lifx | 14 | 0 | 7 | 50% |
| tuya | 22 | 10 | 0 | 45% |
| alexa_devices | 44 | 0 | 13 | 30% |
| matter | 45 | 8 | 5 | 29% |
| reolink | 296 | 0 | 31 | 10% |

E la firma che conta:

```
binary_sensor.giardino_cucina_irrigazione   da_quando: 14:00:17.891654
binary_sensor.giardino_siepe_irrigazione    da_quando: 14:00:17.892119
```

**Tutte e 24 nello stesso millisecondo.**

### 2.10 Lo schema, e i campi mai letti

```sql
entita(id, nome, area_id, dispositivo_id, piattaforma, categoria, classe, unita, …)
dispositivi(id, nome, produttore, modello, area_id, …)
integrazioni(dominio, titolo, stato, motivo, origine)   -- nessuna chiave
```

`init_schema(..., version=6)`.

Campi che Home Assistant manda e che il codice **non nomina mai** (conteggio su tutto
`hiris/app`): `supported_features` **0** · `assumed_state` **0** · `options` **0** ·
`config_entry_id` **0** · `unique_id` **0** · `has_entity_name` **0**. Con una sola citazione:
`capabilities`, `entity_category`, `original_device_class`, `hidden_by`, `original_name`,
`platform`.

---

## §3 · L'appartenenza

L'appartenenza **non è una cosa sola: sono due livelli, e costano in modo molto diverso.**
Entrano entrambi, in quest'ordine, **nello stesso rilascio** (decisione del proprietario).

### 3.1 Il livello del dominio — il dato c'è già

`entita.piattaforma` vale `hydrawise` per tutte e 24 le entità dell'irrigazione. **La prova del
§1 si supera con una query sola su una colonna che è già in archivio.** Non manca il dato: manca
chi lo legge.

Tre correzioni, in ordine di costo crescente:

**a · La frase.** `integrazioni` porta `dominio` e `titolo` sulla stessa riga. Il briefing legge
`titolo` e scrive «un'integrazione: Abat-jour». Diventa: **«il dispositivo *Abat-jour*
dell'integrazione *LIFX*»**. Costo: una riga, nessuna migrazione, si prova sulla casa lo stesso
giorno. È il primo lavoro della fetta proprio perché è il più piccolo che si può verificare dal
vivo.

**b · La ricerca impara la piattaforma** e il titolo dell'integrazione. Chiude `search
"hydrawise"` → 0 e `search "sonos"` → 0.

**c · `view` accetta `tipo: "integrazione"`** e risponde con dominio, stato, motivo, e le sue
entità **con quante rispondono e da quando**. È la chiamata che oggi non esiste, e che sostituisce
i 95 secondi di giro delle aree.

### 3.2 Il livello dell'istanza — non esiste

`integrazioni` non ha chiave: dieci lampadine LIFX sono dieci righe con lo stesso `dominio` e
`titolo` diversi. `entita` non ha `config_entry_id` (mai citato, §2.10).

Si aggiunge `integrazioni.entry_id` come chiave e `entita.config_entry_id`: **migrazione additiva
6 → 7**, dello stesso genere di `esito_letto_ts` della fetta precedente. Serve a dire «*questa*
lampadina» invece di «LIFX», e a sapere quali entità cadono quando cade un config entry preciso.

### 3.3 L'ordine, e perché

Prima §3.1 intero e **provato dal vivo**, poi §3.2. Se il tempo stringe, la fetta è **utile a
metà** invece che **rotta a metà**: il livello del dominio da solo supera la prova del §1 e fa
sparire tre dei quattro errori del §2.

---

## §4 · La salute di un'integrazione — niente soglia

**La definizione che il registro portava era sbagliata.** Diceva: *«la salute di un'integrazione
è quante delle sue entità rispondono»*. Come indicatore va bene; come **regola** no, e i numeri
del §2.9 lo dimostrano:

- **mobile_app 61% muta** — è un telefono che dorme, torna da solo in minuti;
- **tuya 45%** — sono le luci di Natale, staccate, ed è settembre;
- **lifx 50% `unknown`** — lampadine spente.

Qualunque soglia che prenda hydrawise all'80% passa a un soffio da mobile_app al 61%.

### I due segnali che distinguono

**① La sincronia.** Un'integrazione che cade porta giù **tutte** le sue entità nello stesso
istante (§2.9: stesso millisecondo). Un dispositivo spento ne porta giù una. È una firma, non una
soglia.

**② La durata.** Il telefono torna in minuti, l'irrigazione è ferma da ore, le luci di Natale da
mesi. La stessa percentuale significa cose opposte a durate diverse — e **la durata è ciò che
l'osservatore sa già misurare**.

### Cosa dichiara HIRIS

Nessun verdetto «rotta / sana». Il codice calcola i fatti, il modello dice la frase:

> **hydrawise — 24 entità su 30 non rispondono, tutte dalle 14:00 di oggi.**

Vera senza inventare nessun numero magico. È la stessa disciplina del §6, applicata al briefing
invece che agli strumenti.

### Correzione del 04/09, misurata durante l'implementazione — leggila prima di usare la sincronia

La prima stesura diceva: *«il briefing la mette fra gli avvisi quando c'è la sincronia, non quando
c'è una percentuale»*. **Quella frase non è sicura e va rifatta prima che qualcuno la implementi.**
Due misure, entrambe sulle 997 entità vere della casa.

**① «Stesso istante» non esiste.** La regola chiedeva un istante *identico*, e i timestamp veri
differiscono nei microsecondi (`14:00:17.891654` contro `.892119`): come specificata, la firma
**non sarebbe scattata mai**, e sarebbe uscito un campo morto — verde in ogni prova. Serve una
tolleranza sull'**ampiezza** fra il primo e l'ultimo istante, e le due classi si separano da sole:

| | ampiezza fra la prima e l'ultima entità muta |
|---|---|
| fritz · spook · ave_domina · alexa · hydrawise · tuya · lifx · matter | **1 → 108 ms** |
| mobile_app · reolink | **10,8 ore** |

Cinque ordini di grandezza. L'implementazione usa **2 secondi**, con questi numeri scritti accanto
alla costante.

**② E qui viene la parte che smonta la regola: la sincronia non prova un guasto.** Con la
tolleranza attiva `mute_da` esce per cinque piattaforme, e **quattro riportano lo stesso istante,
`2026-09-02T17:54`**: tuya (le luci di Natale, staccate da mesi), lifx, matter, alexa. Non sono
quattro guasti simultanei: è la firma di un **riavvio** che ha ri-datato tutto insieme.

Il *dato* resta onesto — «sono diventate mute insieme» è vero. È la *deduzione* «quindi
l'integrazione è caduta» a essere falsa, e un briefing che la facesse annuncerebbe quattro guasti
inesistenti a ogni riavvio di Home Assistant. È lo stesso difetto degli «otto falsi allarmi su
nove» che questo prodotto ha già pagato una volta.

### ③ Il discriminante esiste, e la casa lo pubblica già — indicazione del proprietario, 04/09

Il paragrafo qui sopra si fermava a «serve capire cosa significhi `da_quando` dopo un riavvio». Il
proprietario ha indicato la strada in una frase: **ci sono sensori che dicono da quanto Home
Assistant si è riavviato.** Cercato sulla casa vera, e c'è:

```
sensor.uptime   stato: 2026-09-02T17:54:44+00:00   classe: uptime   piattaforma: uptime
```

Lo stato **è l'istante in cui Home Assistant è partito**. Confrontando ogni `mute_da` con quello,
il confondente smette di essere insormontabile e diventa una sottrazione:

| piattaforma | scarto dall'avvio | lettura |
|---|---:|---|
| lifx | **+0,51 s** | è il riavvio |
| tuya | **+0,84 s** | è il riavvio |
| matter | **−17,8 s** | è il riavvio (spegnimento) |
| alexa_devices | **+28,4 min** | dubbio: non si afferma |
| **hydrawise** | **+47,1 ore** | **guasto vero, indipendente dall'avvio** |

Cinque piattaforme, tre classi, e l'unica che il proprietario sa essere davvero rotta —
l'irrigazione — è l'unica lontana dall'avvio. **La regola diventa scrivibile:** un `mute_da` che
cade nei pressi dell'istante di avvio non è un guasto, è il riavvio; lontano da quello, è un
guasto; nella zona di mezzo **si dichiara il dubbio invece di scegliere**.

**Due cose da chiudere prima di implementarla**, e nessuna delle due è un dettaglio:

1. **La semantica di `sensor.uptime` va verificata sulla documentazione**, non dedotta dalla
   coincidenza — per quanto schiacciante. È la legge del progetto, ed è il §7.
2. **Quel sensore può non esserci.** L'integrazione *Uptime* è opzionale: su una casa che non
   l'ha, il discriminante non esiste. La risposta onesta lì non è «allora è un guasto»: è
   **tornare a non affermare**, esattamente come nella zona di mezzo. Una regola che si comporta
   bene solo dove il sensore c'è è una regola che mente altrove.

**La lezione di metodo, che vale oltre questa regola.** Il difetto è stato trovato eseguendo, non
leggendo; e il rimedio non è arrivato né dal codice né dalla documentazione, ma da **chi la casa la
abita**. Il tema finale (§7) resta necessario — serve a sapere *cosa significa* ciò che leggiamo —
ma non è sufficiente: alcune cose le sa solo il proprietario, e vanno chieste.

**Cosa NON cambia:** i conti (`entita_totali`, `entita_mute`, `entita_disabilitate`) e `mute_da`
sono **fatti**, si producono e si mostrano. Ciò che si sospende è solo il **verdetto** che il
briefing ne trarrebbe.

### Due cose dichiarate, non decise

1. **74 o 148?** Il briefing dice «74 entità non rispondono»; percorrendo le aree se ne contano
   **148** includendo gli `unknown`. Sono due domande diverse e oggi nessuno dice quale sta
   rispondendo. **La risposta dovrà dire cosa conta.**
2. **`unavailable` non è `unknown`.** È esattamente il genere di affermazione su Home Assistant
   che su questo progetto **si verifica sulla documentazione prima di diventare una regola**
   (§7). Non si deduce.

---

## §5 · Il guasto: nome, condizione, durata

Due correzioni nella **stessa funzione**, `watcher.py::watch_system`, ed è la ragione per cui
stanno nella stessa fetta.

**a · Il soggetto porta il nome e la condizione.** Non più il solo `entry_id`: il dominio, il
titolo e **quale** guasto sia — `setup_retry` e `setup_error` non sono la stessa cosa. Il dato è
già nel dizionario che la funzione sta leggendo.

**b · L'isteresi.** Un solo giro senza la condizione **non** chiude l'episodio: ne servono
**due consecutivi**, cioè venti minuti. Il numero è scelto e non lasciato aperto, e la ragione va
scritta accanto alla regola — come si è fatto per i contrasti in `hiris-theme.css` e per il
pallino a barra stretta. La ragione è questa: i quattro episodi del §2.2 hanno **tutti e tre** i
buchi di esattamente un giro, quindi due giri li unificano tutti; e il prezzo di sbagliare per
eccesso è **dieci minuti di ritardo** nel dichiarare finito un guasto, mentre il prezzo di
sbagliare per difetto è l'archivio di oggi — cinquanta episodi per un guasto solo. I due errori
non costano uguale, e la soglia sta dalla parte che costa meno.

**c · `stato` nel corpo.** Oggi è la costante `"aperto"` anche a episodio chiuso (§2.3). O porta
la condizione vera, o esce: un campo che non varia mai non è un fatto, è rumore che contraddice i
timestamp accanto.

### La domanda di continuità, e la risposta

Cambiare la forma del soggetto rompe la continuità col grezzo già scritto: in archivio ci sono
**22 giorni** di righe `integrazione:<entry_id>`.

**Si convive, non si migra.** Il grezzo è per costruzione effimero (22 giorni, poi `pota()` lo
cancella) e la sua legge è «scrivi il grezzo, giudica dopo»: riscriverne il passato violerebbe
proprio quella legge. Le righe vecchie restano leggibili come sono; le nuove portano di più;
entro tre settimane la forma vecchia è uscita da sola. Ciò che invece **deve** reggere subito è
`rebuild_conditions()`, che risemina al riavvio: deve riconoscere entrambe le forme, o al primo
aggiornamento ogni guasto aperto rinasce come nuovo.

---

## §6 · Gli strumenti rifiutano invece di indovinare

Non è un difetto: è una linea di condotta ripetuta in tre posti indipendenti (§2.4, §2.5, §2.6).
Davanti all'incertezza il prodotto risponde con sicurezza invece di rifiutare.

**a · `search` distingue «unico» da «certo».** Un candidato solo non è un candidato giusto. Il
campo `ambiguo` oggi dice `false` quando la lista ha un elemento; deve dire quanto quel candidato
è **forte**, e sotto una certa forza la risposta onesta è «non ho capito cosa cerchi», non un
riferimento.

**b · Gli argomenti obbligatori si verificano.** `logbook` dichiara `required: ["ore"]` e non lo
controlla; un argomento con un nome ignoto viene ignorato in silenzio. Entrambi diventano un
errore che **nomina il campo**, come già fanno `view` e `search` («*«view» richiede «tipo» e
«riferimento»*»).

**c · `view` porta la regola insieme al segnale.** Che una `categoria: diagnostic` non sia una
misura, e che un `da_quando` di due giorni non possa essere un valore istantaneo, oggi non è
scritto da nessuna parte. Dove quella regola viene presa è il §7.

---

## §7 · Le specifiche di Home Assistant si importano — il tema finale

> «Per ogni stato va capito cosa rappresenta e se ci sono altri metadati o parametri che
> permettono di capire di più. Per migliorare i ragionamenti serve sapere cosa stiamo guardando
> in profondità.» — il proprietario, 04/09

Chiude lo sprint perché è la voce che lo rende **duraturo**: le altre correggono ciò che
sbagliamo oggi, questa toglie la ragione per cui lo sbagliavamo.

### Due nature di sapere, e confonderle è il motivo per cui non è stato fatto

**① Ciò che è di *questa* casa — si legge a runtime.** `supported_features` (cosa un'entità sa
fare), `assumed_state` (HA dichiara «questo stato lo **suppongo**»), `capabilities`, `options`,
`entity_category`. Sono già nelle risposte che riceviamo, costano zero chiamate in più, e sono
veri per definizione perché li dichiara l'installazione stessa. Oggi: **zero citazioni** (§2.10).

> `assumed_state` è il reperto più amaro dello sprint: **stiamo progettando la certezza del dato
> mentre il fornitore ce la sta già mandando.**

**② Ciò che è del *vocabolario* — si importa dalla documentazione.** Cosa significhi
`device_class: moisture` (bagnato/asciutto, **non** «umidità»), quali stati ha un `valve`, cosa
distingue `unavailable` da `unknown`. Questo HA non lo manda: lo documenta.

### Come si importa

Il precedente è già in casa e funziona: `briefing.py:69` porta un elenco *«copiato da
`homeassistant/generated/entity_platforms.py`»*, sorvegliato da `tests/test_domain_vocabulary.py`.
Non si deduce e non si indovina: **si importa, si dichiara la fonte, e una prova si accorge
quando diverge.** Questo tema estende quel gesto dai domini a stati, classi, categorie, capacità
e attributi.

### Come si accorge di essere invecchiato

Il briefing già dichiara in cima `Home Assistant 2026.9.0`. Il vocabolario importato porta
scritto **da quale versione viene**, e il confronto con la versione viva diventa un fatto
misurabile: quando la casa supera la versione del vocabolario, qualcuno lo dice — invece di
scoprirlo da un briefing che sbaglia.

### Cosa chiude

Su `sensor.persons` la catena si chiude: diagnostica, nessuna classe, nessuna unità, stato fermo
da due giorni → **non è una misura**, e il modello lo **legge** invece di dedurlo dal nome.

---

## §8 · Le tracce e il log — la fonte nuova

Sta **in coda per conseguenza della strada**, non per importanza: è una fonte nuova, e nasce
sopra un'appartenenza già rifatta invece che accanto a una da rifare.

`trace/list`, `trace/get`, `trace/contexts` e `system_log/list` — tutti WS, tutti
`require_admin`. Misurato il 30-31/08: 72 tracce su 16 automazioni, 1 `error`, **un'automazione
rotta davvero mai segnalata**; 17 voci di log, 11 WARNING e 6 ERROR.

**Una fonte sola, due lettori** — lo strumento della chat **e** l'osservatore. È la regola che
l'osservatore ha già scritta nel proprio docstring: «non apre un secondo rubinetto», perché due
sorgenti degli stessi eventi possono divergere.

**Le due trappole già pagate**, che decidono il lavoro e non si vedono nella documentazione:

- **Le tracce hanno una finestra.** HA ne conserva 5 per automazione: alla sesta esecuzione la
  prima non esiste più. Decide se si può guardare a cadenza o si devono seguire mentre accadono.
- **Il log arriva già giudicato.** `system_log/list` consegna righe raggruppate da HA con `count`
  e `first_occurred`. Rompe la legge dell'osservatore «scrivi il grezzo, giudica dopo»: o si
  accetta e **si scrive perché**, o si legge più in basso.

Questa fonte è anche ciò che rende dicibile «18 automazioni in funzione regolare» — la frase che
oggi HIRIS dice senza poterla sapere (§2.7).

---

## §9 · La pulizia

`proxy/ha_client.py::get_error_log()` ha i test e **zero chiamanti vivi**. Punta a
`/api/error_log`, che su HA 2026.8.3 risponde **404**, e **inghiotte il 404 restituendo
`{"errors": 0, "warnings": 0}`**: collegarlo com'è farebbe dire a HIRIS «zero errori» su una casa
che ne ha 6+11. È lo zero che afferma.

**Si cancella il metodo e si cancellano i suoi test.** Non è una migrazione: il vecchio punta a un
endpoint che non esiste più e mente quando non lo trova, quindi non c'è niente da salvare. Ogni
fetta è anche pulizia.

---

## §10 · L'ordine dei lavori

La strada è **una spina alla volta, verticale**: l'appartenenza portata fino in fondo attraverso
tutti i lettori, e solo dopo il resto.

| # | Lavoro | Si prova dal vivo |
|---|---|---|
| 1 | §3.1a — la frase: dominio + titolo | subito, sul briefing vero |
| 2 | §3.1b — la ricerca impara la piattaforma | `search "hydrawise"` |
| 3 | §3.1c — `view tipo: "integrazione"` | la prova del §1, livello dominio |
| 4 | §4 — la salute: sincronia e durata, niente soglia | l'irrigazione compare fra gli avvisi |
| 5 | §5 — il guasto: nome, condizione, isteresi | un episodio al posto di quattro |
| 6 | §3.2 — l'istanza: migrazione 6 → 7 | «*questa* lampadina» |
| 7 | §6 — gli strumenti rifiutano | `logbook` senza `ore` → errore |
| 8 | §7 — le specifiche importate | «cosa sa fare, quanto è certo» |
| 9 | §8 — tracce e log, due lettori | l'automazione rotta viene nominata |
| 10 | §9 — la pulizia | la suite resta verde con un metodo in meno |

Ogni riga è verificabile sulla casa vera lo stesso giorno in cui è scritta. È deliberato: su
questo progetto **cinque difetti su sei escono eseguendo, non leggendo**.

---

## §11 · Le prove

Ogni prova deve poter **fallire**: la finta deve saper produrre il difetto che la prova cerca.
Dove una prova sarebbe una tautologia, si dice e non si scrive.

1. **La frase non chiama integrazione un dispositivo** — con un config entry `lifx` di titolo
   «Abat-jour», il testo nomina il dominio **e** il titolo. Mutazione da uccidere: quella che
   stampa il solo titolo, cioè il codice di oggi.
2. **La ricerca trova per piattaforma** — `search "hydrawise"` torna le entità di quella
   piattaforma. Mutazione: l'indice di oggi, che risponde vuoto.
3. **Un candidato solo non è un candidato certo** — con un solo risultato debole, `ambiguo` non è
   `false`. È la prova che il caso `sensor.persons` non aveva.
4. **La salute non ha soglia** — su un'istantanea con mobile_app al 61% e hydrawise all'80%,
   **solo** hydrawise produce un avviso, e lo produce per la **sincronia**. La mutazione da
   uccidere è quella che verrebbe scritta per prima: una percentuale.
5. **Un episodio per condizione** — una condizione che sparisce per un solo giro e torna resta
   **un** episodio. Mutazione: il codice di oggi, che ne fa due.
6. **Il corpo di un guasto non contraddice i suoi timestamp** — un episodio chiuso non dice
   `"stato": "aperto"`.
7. **`rebuild_conditions` riconosce la forma vecchia** — un archivio con righe
   `integrazione:<entry_id>` e righe nuove: al riavvio nessun guasto aperto rinasce come nuovo.
   È l'unica prova che tocca ciò che succede **sulla casa del proprietario** al primo avvio dopo
   l'aggiornamento.
8. **Gli argomenti obbligatori si verificano** — `logbook` senza `ore` torna un errore che nomina
   il campo; un argomento ignoto non viene ingoiato in silenzio.
9. **La migrazione 6 → 7 è additiva e idempotente** — girarla due volte non solleva e non cambia
   i conti; un archivio nuovo nasce già con le colonne, cioè `_SCHEMA` è stato aggiornato insieme
   alla migrazione e non solo lei.
10. **Il vocabolario dichiara la sua fonte** — la tabella importata porta la versione di HA da cui
    viene, e una prova la confronta con quella dichiarata dalla casa.
11. **`get_error_log` non esiste più** — né il metodo né i suoi test.

E una prova che **non** si scrive: che l'utente capisca. Quella la fa il proprietario, sulla casa
vera, e senza di lei nessuna delle undici sopra vale niente.

---

## §12 · Cosa NON entra

| Cosa | Perché |
|---|---|
| **Il tempo** (spina 2) — le quattro fotografie a 4h30 di distanza | È la spina successiva. Resta nel registro |
| **La natura** (spina 3) — diagnostico e misura con la stessa forma | §7 ne posa le fondamenta; la cura completa viene dopo |
| **La provenienza** (spina 4) — letto / detto / dedotto indistinguibili | Il caso Viola. È la spina che chiude il ciclo, ed è sua |
| **Il comfort che non produce niente** — 25 soggetti, 0 oggetti in 9 giorni | Trovato misurando, non ancora capito: **serve una sonda, non una spec** |
| L'energia senza unità (52% della conoscenza) | Tocca «Il vocabolario del dato», in attesa |
| I comandi verso HA · la sicurezza | Invariati, dove erano |

**Una cosa va detta sull'ultima riga della tabella**: le tre spine rimaste non sono un residuo,
sono il resto del lavoro. Questa fetta ne fa **una su quattro**, e la fa intera.
