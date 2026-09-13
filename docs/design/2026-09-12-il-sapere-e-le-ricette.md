# Il sapere e le ricette — le misure di partenza della fetta 4

> Fetta 4 del piano «i tre attori» (`docs/superpowers/plans/2026-09-10-i-tre-attori.md`),
> spec `docs/design/2026-09-10-i-tre-attori.md` §7 e §8.
>
> **Si misura prima di progettare.** Tutti i numeri qui sotto sono presi il 12/09/2026 sulla casa
> vera (Home Assistant su `192.168.1.95`), non dedotti dal codice né copiati dalla spec. Dove la
> spec dà un numero diverso, la differenza è dichiarata.

## Misura 1 — `frontend/get_translations`, cosa risponde davvero

Tre categorie chieste sulla stessa connessione, lingua `it`:

| categoria | chiavi di primo livello |
|---|---|
| `entity_component` | **801** |
| `entity` | **1.730**, da **24 integrazioni** |
| `state` | **0** |

**`state` torna vuoto**, e vale la pena scriverlo: è una chiamata che non porta niente su questa
casa, e chi la aggiungesse «per completezza» pagherebbe un giro di rete per un dizionario vuoto.

`entity_component` porta il nome tradotto di ogni `device_class` per dominio, nella forma
`component.<dominio>.entity_component.<classe>.name`. `entity` porta il nome che **l'integrazione**
dà a una sua entità, nella forma `component.<integrazione>.entity.<dominio>.<translation_key>.name`.

## Misura 2 — `DEVICE_CLASS_MEANING`: quanto della casa non ha mai visto

`hiris/app/home_space/ha_vocabulary.py` porta **27 coppie scritte a mano**, copiate dai sorgenti di
Home Assistant al tag `2026.9.1`.

| dominio | coppie a mano | classi vive | **mai chieste** |
|---|---|---|---|
| `sensor` | 18 | **62** | **44** |
| `binary_sensor` | 0 | **28** | **28** |

Il piano prevedeva «43 delle 62 classi di `sensor`». Misurate oggi sono **44 su 62**: la tabella a
mano ne copre 18. Per `binary_sensor` la copertura è **zero**, e il piano non lo diceva.

**Perché conta e non è una questione di completezza.** Il censore considera «classificata» una
coppia che sta in `DEVICE_CLASS_MEANING`: finché la fonte è una lista a mano, le 44 classi che non
ci sono non vengono **mai chieste a nessuno**. Cambiata la fonte, il difetto si chiude da sé.

## Misura 3 — `_DIRECTION_BY_TRANSLATION_KEY`: quattordici righe, e cosa l'installazione dichiara

`hiris/app/proxy/ha_client.py:2013` porta **14 chiavi → 7 direzioni**, misurate il 27/08/2026
sull'integrazione `zcsazzurro`.

Misurato oggi: `zcsazzurro` dichiara **37 chiavi di nome entità** dentro questa installazione, e
**tutte e 14 quelle della tabella ci sono** — con il loro nome in italiano («Energia prodotta
oggi», «Potenza autoconsumata»). Ci sono anche i gemelli `_total` che la tabella **non conosce**
(`energy_generating_total`, `energy_charging_total`, …): sette chiavi in più che oggi HIRIS non sa
leggere.

**Quello che l'installazione NON dichiara è la direzione.** Dice «Energia prodotta oggi», non
«produzione». Il salto fra le due cose è un giudizio, ed è esattamente per questo che quelle 14
righe devono diventare **dati del sapere con una provenienza**, non una tabella nel codice: come
dato si correggono senza un rilascio, si vedono, e si esportano a chiunque abbia quell'inverter.

## Misura 4 — il vocabolario dei tipi, cosa diventa seme

`home_space/type_vocabulary.py`, interrogato:

| cosa | quante |
|---|---|
| domini dichiarati | 41 |
| coppie (dominio, classe) dichiarate | 35 |
| domini accendibili | 13 |
| tipi notevoli | 23 |
| stati di riposo | 16 |
| stati «non lo so» | 2 |

Porta già la disciplina della provenienza che la spec cita come precedente: `Asked`, `Imported`,
`Ours`, e `Field` è astratta — non si costruisce una riga senza dire da dove viene.

## Misura 5 — **il nome `knowledge.db` è già occupato, da un morto**

`hiris/app/server.py:3251`: un file `knowledge.db` esiste in `/data` sulle installazioni che hanno
attraversato la fetta «esce il documentale». Nessun codice lo legge o lo scrive più, e il server ne
dichiara l'incontro nel log invece di tacere — ma **il file resta su disco, intatto**, con lo schema
di un'altra cosa.

Il piano dice «crea `hiris/app/mind/knowledge.py`». Il modulo sì; **il file no**: aprire
`knowledge.db` sull'installazione del proprietario troverebbe le tabelle di un archivio documentale
morto, e il primo `CREATE TABLE IF NOT EXISTS` non direbbe niente. Il sapere vive in **`sapere.db`**,
un file suo, nella convenzione già usata da `osservazioni.db`, `memoria.db`, `promesse.db`.

Questa misura non era nel piano. È il genere di trappola che si vede solo guardando, ed è la ragione
per cui la regola di questo progetto è misurare prima.


## Misura 6 — i tre attributi fissi NON possono uscire, e perché

Il piano dice: *«I tre attributi fissi scelti a mano (`device_class`, `state_class`, `source_type`)
escono con questa fetta»*. **Non sono usciti, e la ragione è misurata, non una scorciatoia.**

| attributo | chi lo legge oggi | si può togliere? |
|---|---|---|
| `device_class` | `mind/facts._reading_aspect` → `type_vocabulary.aspect_of()`, che ne deriva la **gamba** di `sensor` e `binary_sensor`; `facts.aggregate_day` lo mette nel corpo di ogni episodio (`classe`) | **no**: senza, ogni episodio perde il genere e il rilevatore di fumo torna a leggersi «Acceso» |
| `source_type` | stesso `aspect_of()`, per `device_tracker` | **no**, stessa ragione |
| `state_class` | **nessuno**, dalla correzione del 27/08/2026 | tecnicamente sì, ma il suo docstring dichiara già perché resta: *«i 22 giorni di grezzo permettono di rifare il giudizio anche se un domani tornasse a servire»* |

Il piano e la spec §5.3 si contraddicono su questo punto: §5.3 dice che lo scope **deriva** da
dominio, `device_class` e `source_type`; §5.4 dice che quei tre escono. Non possono valere
entrambe. Ha ragione §5.3, perché è quella che descrive codice vivo e misurato.

**Cosa è uscito davvero, e vale di più**: il grezzo non conserva più *solo* tre attributi scelti a
mano. Ne conserva **quelli che il sapere dice valgano la pena per quel tipo**, e il cambio di uno di
quelli fa nascere una riga anche quando lo stato non si muove — che è la metà che rende
rispondibile l'esempio fondativo del cervello, «il riscaldamento parte alle 15:30, la casa è calda
alle 16:30».

## Misura 7 — il censore NON si chiude da sé, e va detto

Il piano dice: *«Il censore considera "classificata" una coppia che sta in `DEVICE_CLASS_MEANING` —
27 voci copiate a mano — ed è per questo che 43 delle 62 classi di `sensor` non sono mai state
chieste. Cambiata la fonte, il difetto si chiude da sé.»*

**Cambiare la fonte di `type_census.claimed_device_classes` chiuderebbe il censore, non il
difetto.** L'istantanea che il censore confronta viene dalla stessa lettura
(`state_translations.published_device_classes`): se anche ciò che si *rivendica* venisse da lì,
pubblicato e rivendicato sarebbero lo stesso insieme per costruzione, e quel controllo non potrebbe
più arrossire mai. È il difetto n.1 di questo progetto — una prova che non può fallire — applicato
a un cancello.

La distinzione che regge: **«Home Assistant lo documenta» non è «qualcuno l'ha guardato».** Un nome
tradotto («Potenza») è un fatto del fornitore; decidere cosa HIRIS debba farne è un giudizio. Il
censore continua a chiedere il secondo.

**Il difetto vero si è chiuso lo stesso, per un'altra strada**: le 44 classi di `sensor` e le 28 di
`binary_sensor` che il repo non nominava adesso **hanno un significato nel sapere**, importato
dall'installazione con la sua fonte e la sua versione. Non erano «non importanti»: erano quelle di
cui HIRIS non sapeva dire niente. Adesso lo sa dire.
