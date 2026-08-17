# I reperti della review — classificati

> Tre revisori indipendenti in parallelo, misurati sulle **quattro fondamenta**
> di `CLAUDE.md`, più una caccia alle prove che non possono fallire.
> **47 rilievi grezzi → 40 distinti** (sette erano lo stesso difetto trovato da
> due strade diverse).
>
> **29 chiusi**, **11 aperti** — aggiornato il 2026-08-17 dopo il giro di
> correzioni. Degli 11 aperti, **7 sono funzioni nuove** (leggere il calendario,
> le liste, i guasti che HA ha già diagnosticato): non sono correzioni, sono
> fette. Tre sono decisioni di prodotto, e una è una non-correzione dichiarata.

## Come sono classificati

Due assi, perché uno solo non basta a decidere l'ordine.

**Gravità — cosa succede quando scatta**

| | |
|---|---|
| **A** | **Risposta sbagliata detta con sicurezza.** Il peggio: l'utente non ha modo di accorgersene. |
| **B** | **Risposta mancante.** HIRIS tace, o dice «non lo so», su qualcosa che sa o potrebbe sapere. |
| **C** | **Lavoro sprecato o mina futura.** Costa e non rende, oppure oggi è allineato e domani diverge. |

**Impatto — quanto spesso**

| | |
|---|---|
| **1** | Sempre, su ogni casa. |
| **2** | In configurazioni comuni. |
| **3** | Solo su un cambiamento futuro, o su casi rari. |

`A1` è la peggiore combinazione che esista: **sbaglia sempre, e non si vede**.

---

## A1 — sbaglia sempre, e non si vede

### 1. ✅ La classe delle entità non arriva mai — *chiuso*

`config/entity_registry/list` risponde con `as_partial_dict`, che **non contiene
`device_class`**. Verificato sul sorgente di HA.

Quindi `_e_un_evento("binary_sensor", None, "on")` era **sempre falso**: nessun
sensore binario è mai entrato in «Notevole adesso». Allagamento, fumo,
monossido, finestra aperta: letti e mai detti. E le 28 voci di
`_SIGNIFICATO_CLASSE` — l'intera 3.4.0 — erano codice irraggiungibile.

Nessuna prova poteva vederlo: ogni finta scriveva `device_class` dentro la riga
del registro, cioè un campo che HA lì non mette.

### 2. ✅ Le etichette uscivano come slug — *chiuso*

`da_controllare` invece di «Da controllare»: una parola che l'utente non ha mai
scritto, che non cambia nemmeno rinominando l'etichetta, e che rendeva la
ricerca funzionante **solo** per le etichette di una parola sola senza maiuscole.

### 3. ✅ `guarda` rispondeva `on` senza dire cosa significa — *chiuso*

Il digesto traduceva «bagnato», `guarda` no. Ma `guarda` è la porta che il
modello usa quando la domanda è **precisa** — «c'è una perdita in bagno?» — e
quando il digesto ha tagliato. «Il sensore perdita è acceso» per una persona
significa «funziona».

### 4. ✅ L'unità di un ricordo ancorato a una stanza — *chiuso*

`deduci_unita` confrontava il solo `area_id` **proprio**, ma l'area ereditata
dal dispositivo è il caso normale. «In cucina non sotto i 20» si archiviava come
«da 20» nudo, per sempre, da tutte le porte.

### 5. ✅ `esegui` riporta `prima`/`dopo` senza unità

`azione/porta.py:209` scarta `unit` dalla voce dello specchio che ce l'ha.
Su un `climate` in °F: «adesso è a 21, in stanza ci sono 69.8» — senza scala. E
il modello non può nemmeno dedurla, perché il nucleo gli vieta esplicitamente di
applicare l'unità della casa a una singola entità.

### 6. ✅ `/api/entities` spaccia l'`entity_id` per nome

`handlers_entities.py:37` — `friendly_name` ripiega sull'`entity_id`. È la
disciplina opposta a quella che `costruisci_indice` dichiara e rispetta: «un id
tecnico non entra qui, né tale e quale né ingentilito».

---

## A2 — sbaglia in configurazioni comuni

### 7. ✅ Il vocabolario di `forza` in JS non è vincolato a quello Python — *perdita di dati*

`interpretazione.py:55` ha quattro valori; `memoria-route.js` li riscrive **due
volte**, e nessun test lega le liste.

Aggiungendo una quinta forza, la tendina della pagina Memoria non trova
l'opzione e **ricade su vuoto**. L'utente corregge «Detto da» e salva: la PATCH
manda `forza: null`. **La forza del ricordo viene cancellata da un'operazione che
non la riguardava** — e la memoria è l'unico archivio che non si ricostruisce da
nessuna parte.

### 8. ✅ Le due regex delle sentinelle del ponte divergono

`openai_compat_runner.py:136` tollera gli spazi iniziali, `chat_store.py:50` no.
`_purge_toxic_turns` gira in lettura proprio per ripulire le righe **già su
disco**: una riga avvelenata con uno spazio in testa non viene mai riconosciuta e
torna al modello **a ogni turno, per sempre**.

### 9. ✅ Le cinque sentinelle ricopiate a mano

`agent/runner.py` le emette, `chat_store.py:56-71` le ridigita tutte — compresa
quella che ha già una costante. Il commento dice che l'elenco è già andato fuori
sincrono una volta. La struttura che l'ha prodotto è intatta.

### 10. ✅ Lo stesso ricordo ha due forme secondo la porta

Piatto da `richiama`, annidato sotto `interpretazione` da `guarda` — che perde
anche `detto_il`. Il modello impara una forma dentro `guarda("area")` e poi
legge la forza su `guarda("ricordo")`: assente.

### 11. ✅ La pagina Memoria non sa nominare ciò che la chat nomina

`handlers_memoria.py:135` costruisce l'indice **senza** i nomi di ripiego, pur
leggendo già lo specchio vivo quattro righe sopra. In chat «Abat-jour sinistra»,
sulla pagina l'`entity_id` crudo.

### 12. ✅ «Il dominio di un entity_id» scritto sei volte, con due comportamenti

Su un id senza punto, `nucleo.py:380` restituisce l'id intero e `domande.py:55`
la stringa vuota. Il commento dichiara la parentela e **non è vera**. Il campo
`domain` esiste già nello specchio, e lo legge solo la rotta senza chiamanti.

---

## B1 — tace sempre, su qualcosa che sa già

### 13. ✅ `piattaforma` ed `etichette` da una porta su tre — *chiuso*

### 14. ✅ `guarda("dispositivo")` senza stato — *chiuso*

Usciva con l'unità di misura e nessun valore.

### 15. ✅ Lo specchio riletto a mano da `costruisci_nucleo` — *chiuso*

### 16. ✅ Una prova che non poteva fallire — *chiusa*

`test_una_casa_vuota_non_produce_un_nucleo_bugiardo` verificava solo che il
testo non fosse vuoto — cosa che non può essere falsa, perché i titoli di
sezione si scrivono sempre. Con un `_righe_casa()` che inventava «Cucina
fantasma: 5 luci» restavano verdi tutte e 41 le prove del file.

### 17. ✅ Gli alias delle entità sono sempre vuoti

Stessa causa della classe: `as_partial_dict` non manda `aliases`. La «spina
dorsale di `cerca`» regge **solo** per le aree, che invece li mandano davvero.

### 18. ✅ Le entità nascoste: il nucleo promette, `guarda` non può

Il digesto scrive «N entità nascoste … `guarda` le riporta se gliele chiedi».
`guarda` non espone `nascosta` né `categoria`. Alla domanda «quali?» il modello
o si contraddice o inventa.

### 19. ✅ Il nome della casa non arriva al modello

`location_name` entra nel sistema di riferimento e `_righe_sistema` non lo
stampa. La fetta A dichiara «esce da due porte»: sono una e mezza.

### 20. ✅ I ricordi entrano nel digesto senza il loro id

Il digesto dichiara «12 ricordi non inclusi» e **chiude l'unica strada per
leggerli**: `guarda` esige un id che nessuna porta ha mai stampato, `richiama`
esige un'ancora che quei ricordi non hanno.

### 21. ✅ `/api/entities` restituisce lo stato senza l'unità

Il consumatore dichiarato è l'MCP Gateway. Riceve `72` e non ha modo di sapere
in che scala.

### 22. ✅ `dispositivi.produttore` e `dispositivi.modello`: zero lettori

«Di che marca è la valvola del bagno? Devo ordinarne un'altra uguale.»

### 23. ✅ La tabella `integrazioni`: un comando WS a ogni ricostruzione, zero lettori

E HA manda anche `reason` e `error_reason_translation_key` — **il motivo per cui
un'integrazione non è partita** — che HIRIS non salva nemmeno. «Perché la
telecamera del giardino non risponde?»

### 24. ⬜ La tabella `categorie`: quattro comandi WS, zero lettori

E l'assegnazione per-entità arriva **gratis** dentro la risposta che HIRIS già
riceve, e non viene salvata.

### 25. ⬜ La tabella `plance`: una connessione WS per plancia, il modello non le vede mai

«Questa luce compare in qualche mia dashboard?»

### 26. ⬜ `/api/casa` espone tutto l'albero, nessuna pagina lo legge

Il payload più ricco che HIRIS produce esce verso nessuno: la pagina legge solo
i conteggi.

### 27. ⬜ Le icone e i colori: quattro colonne, zero lettori

`piani.icona`, `aree.icona`, `etichette.icona`, `etichette.colore`.

---

## B2 — non sa ancora, e potrebbe

Tutte verificate nel **sorgente** di Home Assistant, non nella documentazione.

### 28. ✅ `temperature_entity_id` / `humidity_entity_id` dell'area — *il migliore del gruppo*

Ogni area porta **quale entità è LA temperatura di quella stanza**, dichiarata
dall'utente. `config/area_registry/list` li manda **già**: costa zero chiamate.
Oggi HIRIS deve indovinare fra tutti i sensori — senza nemmeno poterli filtrare
per classe. «Fa caldo in soggiorno?»

### 29. ⬜ `repairs/list_issues` — i guasti che HA ha già diagnosticato

Severità, in quale versione si rompe, se è riparabile. È dipendenza di
`frontend`: c'è sempre. Oggi alla domanda «c'è qualcosa che non va in casa?»
HIRIS sa solo contare le entità non disponibili.

### 30. ⬜ `search/related` — chi tocca questa cosa

Calcolato da HA su **tutte** le automazioni, ovunque siano scritte. HIRIS legge
solo `automations.yaml` e `scripts.yaml`: non vede i pacchetti, gli `!include`,
le cartelle, le scene né i gruppi. «Perché si è accesa la luce del corridoio?» /
«Se cancello questa entità, cosa smette di funzionare?»

### 31. ✅ `config/entity_registry/get_entries` — il comando che manda ciò che manca

L'unica via per avere gli alias e le capacità in blocco. La classe è già
risolta dallo specchio; questo chiude il resto.

### 32. ✅ `state_class` — arriva a ogni avvio e `_to_minimal` lo butta

È già dentro gli attributi di ogni sensore. Dice a quali entità si può
applicare `statistics_during_period` **senza chiedere al recorder**. Serve alla
fetta della storia.

### 33. ⬜ `extract_from_target` / `get_services_for_target` — verificati disponibili

Accettano entità, dispositivo, area, piano, etichetta e rispondono con ciò che
è referenziato **e ciò che manca**. Oggi `azione/verifica.py` rifiuta qualunque
bersaglio che non sia un'entità: «spegni tutto in cucina» obbliga il modello a
raccogliere gli id a mano, e se ne perde uno HIRIS spegne quasi tutto
**dichiarando di aver spento tutto**.

### 34. ✅ Gli attributi del meteo: `_DOMAIN_ATTRS` non ha `weather`

Temperatura, umidità, vento e pressione sono attributi di stato e vengono
scartati. Chiedere l'entità meteo restituisce «sereno» e basta.

### 35. ⬜ Il calendario — `calendar/event/subscribe`

HIRIS conta i calendari e non ne legge un evento. «Giovedì sera sono a casa?» è
anche la condizione che serve per decidere il riscaldamento.

### 36. ⬜ `todo/item/list` — leggere la lista della spesa

HIRIS nomina il dominio in italiano, lo conta, e non ne legge una riga.

### 37. ⬜ La topologia dei dispositivi: `via_device_id`

È la sola cosa che spiega un guasto **di gruppo**: dieci lampadine Zigbee non
rispondono insieme perché il loro gateway è giù. Con la versione del firmware,
il tipo di voce e il numero di serie.

### 38. ⬜ Il corpo delle scene è raggiungibile

`GET /api/config/scene/config/{id}`, e il file è `scenes.yaml` — la stessa
strada con cui `comportamento.py` già legge gli altri due. Il rapporto del 16/08
diceva «nessun corpo per nessuna via»: la via c'è, ed è la più corta.

---

## C — mine per un cambiamento futuro

Oggi allineate. È il **prossimo** commit a farle esplodere.

### 39. ✅ «Il piano ha un token?» misurato in quattro punti

`server.py:560` (se il worker parte), `server.py:1316` (se entra nella catena),
`handlers_models.py:360` (cosa dichiara la pagina), `handlers_chat.py:253` (se il
turno si accoda). Tutte e quattro leggono l'ambiente.

Il giorno in cui il token va in archivio come è già successo per `ponte.attivo`,
si aggiorna il file della pagina — e la pagina dice «sei sul forfait» mentre la
chat **paga a token**. È la forma esatta del difetto chiuso a valle e mai a
monte. Il commento a `handlers_models.py:370` **descrive il difetto al presente
credendo di descriverne l'assenza**.

### 40. ✅ Le altre sei

| | |
|---|---|
| I predefiniti di `ponte`/`ollama` in 4-5 posti | il «debito F» già pagato una volta, riapribile dall'altro capo |
| I tre alias del piano: elenco in un modulo, riduttore in un altro | un quarto alias verrebbe archiviato come `sonnet` in silenzio |
| Il quartetto dei codici di credenziale in due moduli | un 429 verrebbe annunciato come «la credenziale non è accettata» |
| La regex dell'`entity_id` in due file | una delle due è una **guardia contro l'iniezione in URL**: allentarla «per riallineare» è una falla |
| La regola del tema scritta cinque volte | e **già divergente**: un ramo `?theme=` serve un chiamante che non esiste più |
| `get_area_registry` / `get_entity_registry` | seconda porta per un fatto che ne ha già una, viva solo nei test |

---

## L'osservazione che conta più dei singoli reperti

Il revisore dei doppioni l'ha detta meglio di come l'avrei detta io:

> **Nove reperti su dodici hanno la stessa forma: una fetta ha unificato una
> regola e ha saltato una porta.**

`specchio_vivo` ne ha unificate tre e ha saltato il nucleo. `unita_effettiva` ha
unificato l'unità e non la classe, che viene dalle **stesse due fonti**.
`decisione_modelli` ha unificato la *composizione* della decisione e non la
*misura* delle credenziali che la alimenta. I motivi del ripiego sono vincolati
al frontend, il vocabolario della forza no.

E l'altra, che riguarda gli strumenti:

> **`scripts/censimento.py` non vede niente di tutto questo**, e i suoi limiti
> dichiarati non lo ammettono. Dei cinque controlli che `CLAUDE.md` §«La review
> totale» elenca, **«doppioni divergenti» è l'unico che nessun comando copre.**


---

## Cosa resta aperto, e perché

Undici voci. **Sette sono funzioni nuove**, non difetti: HIRIS non sbaglia e
non tace su qualcosa che sa — non sa ancora, e per saperlo serve una fetta.

| # | | |
|---|---|---|
| 29 | `repairs/list_issues` | i guasti che HA ha già diagnosticato |
| 30 | `search/related` | «perché si è accesa la luce del corridoio?» |
| 33 | i bersagli per area/etichetta | oggi «spegni tutto in cucina» può spegnere quasi tutto **dichiarando di aver spento tutto** — è il più urgente dei sette |
| 35 | il calendario | «giovedì sera sono a casa?» |
| 36 | `todo/item/list` | «cosa devo comprare?» |
| 37 | `via_device_id` | spiega un guasto **di gruppo** |
| 38 | il corpo delle scene | la via c'è ed è la più corta |

E tre di conoscenza muta che valgono una decisione, non una correzione:

- **24 · `categorie`** — quattro comandi WS a ogni ricostruzione, zero lettori.
  Chiuderla significa decidere se le categorie entrano in `guarda` e in `cerca`,
  cioè se sono una tassonomia che HIRIS usa o solo un dato che replica.
- **25 · `plance`** e **26 · l'albero di `/api/casa`** — la conoscenza c'è e la
  strada per chiederla non esiste. Servono un tipo nuovo di `guarda` (per le
  plance) e una pagina (per l'albero): due decisioni di prodotto.

### Una non-correzione deliberata

**27 · le icone e i colori** (`piani.icona`, `aree.icona`, `etichette.icona`,
`etichette.colore`): zero lettori, confermato. **Restano.**

Toglierle vorrebbe dire una migrazione di schema — cioè un rischio vero, sul
percorso che ricostruisce la casa — per quattro colonne di testo che HA
ripopola a ogni lettura e che una pagina futura userebbe davvero. La regola
«se non esiste un modo per chiederlo è zavorra» vale, ma qui il costo del
rimedio supera il costo del difetto, e la scelta va dichiarata invece che
lasciata implicita: è l'unica voce di questo elenco che ho deciso di **non**
correggere.
