# I nomi delle tipologie, e il doppione della mappa aree

> Fette C e D di «chiudere la conoscenza a 360°».

## C — HIRIS parlava inglese quando non sapeva la parola

Il digesto conta le cose per tipo: «3 luci, 2 tapparelle». Il vocabolario ne
conosceva **17**. Tutto il resto usciva com'era: «4 water_heater», «2
lawn_mower», «3 input_number».

Non è un difetto estetico. È HIRIS che parla la lingua della macchina in un
prodotto che esiste per parlare quella di casa — e sono anche i tipi **meno
ovvi**, quelli in cui una parola inglese aiuta meno.

Adesso sono **63**, e non sono inventati:

- le **45 piattaforme** dichiarate da `homeassistant/generated/entity_platforms.py`,
  l'elenco che Home Assistant genera da sé;
- **18 domini** che piattaforme non sono ma esistono come entità in ogni casa
  vera: gli helper che l'utente crea dall'interfaccia (`input_*`, `counter`,
  `timer`, `schedule`) e le cose che HA crea da sé (`person`, `zone`, `sun`,
  `group`, `tag`, `plant`, `persistent_notification`).

Ognuno dei 63 è stato **verificato come componente vero** nel sorgente di Home
Assistant, uno per uno. Non ricordato.

Singolare e plurale sono dichiarati a mano perché l'italiano non fa il plurale
aggiungendo una lettera: «aspirapolvere» resta «aspirapolvere», «analisi» resta
«analisi». Dedurlo produrrebbe «aspirapolveres». È il motivo per cui il
vocabolario è una tabella e non una funzione.

Un dominio sconosciuto continua a uscire com'è: HA può aggiungerne uno domani, e
meglio «2 quantum_flux» che una riga che sparisce — un conteggio mancante è una
casa raccontata più piccola di com'è.

### Una parola che era già presa

`tag` (i bollini NFC) **non** si chiama «etichetta»: quella parola in HIRIS
significa già le label che l'utente scrive in Home Assistant — che dalla fetta B
escono da `guarda` e si cercano. Due significati per la stessa parola nella
stessa risposta è ciò che la consistenza vieta. Si chiama «tag NFC».

### Le prove che erano dalla parte del difetto

Quattro prove in `test_nucleo.py` asserivano `«Esterno: 4 valve»`. Non erano
sbagliate: **documentavano il difetto**, con l'inglese scritto nell'aspettativa.
Sono state aggiornate, non aggirate.

## D — il doppione: due mappe delle aree, una sbagliata e letta da nessuno

`EntityCache.load_area_registry()` faceva **due chiamate WebSocket a ogni avvio
e a ogni riconnessione** per costruire una mappa area → entità. Nessuno la
leggeva.

Non era nemmeno una mappa giusta:

- indicizzava per **nome** dell'area — due «Bagno» su piani diversi si fondevano
  in uno;
- ignorava l'area **ereditata dal dispositivo**, che in una casa vera è il caso
  normale, non l'eccezione.

`casa.anagrafe.gerarchia()` risponde alla stessa domanda per id, con
l'ereditarietà, e dichiarando quale registro non ha risposto.

Due risposte alla stessa domanda, una delle quali sbagliata e letta da nessuno.
**Nessun doppione.**

### Perché era rimasto

Il censimento segnalava l'**accessore** (`get_area_map`, zero letture di
produzione) ma il **caricatore** era chiamato davvero, due volte. Togliere l'uno
senza l'altro rompeva l'avvio, e una prima lettura del censimento aveva quasi
prodotto proprio quello. La nota nel codice diceva *«va deciso insieme, non a
metà»*. Adesso è stato deciso insieme: caricatore, accessore, campo, i due punti
di chiamata e le prove che provavano solo il morto.

### Una prova che non poteva più fallire

`test_un_registro_aree_rotto_non_annulla_la_ricarica` verificava che
l'inventario restasse caricato anche se il registro aree falliva. Tolto il
caricamento delle aree, quella prova passava **qualunque cosa fosse successo**.
È uscita: è il difetto n.1 del progetto, e vale anche quando a renderla vuota è
una pulizia legittima.
