# L'anagrafe dei tipi — una casa sola per ciò che HIRIS sa di Home Assistant

`spec · 07/09/2026 · HIRIS 3.22.3`

**Fonte della misura**: `.superpowers/sdd/tipi-di-entita/indagine-cosa-ha-pubblica.md` (fuori da
git), ricognizione del 07/09/2026 sulla casa vera — HA `2026.9.1`, 325 componenti caricati. Ogni
numero di questo documento viene da lì o da una verifica ripetuta qui.

---

## §1 · Il difetto, misurato

HIRIS non ha un elenco dei tipi di entità di Home Assistant. **Ne ha ventuno**, scritti a mano,
sparsi in sette moduli, più tre copie ricopiate nei test. Nessuno è derivato da HA, nessuno
concorda con gli altri, e ognuno invecchia per conto proprio.

Le tre che aprono il caso:

| lista | dove | quanti | decide |
|---|---|---|---|
| `aspect()` | `mind/baseline.py:133-200` | 7 rami di dominio | quali entità entrano nel pavimento dell'osservatore |
| `_FEATURE_NAMES` | `home_space/topology.py:673-757` | 18 domini | quali capacità si sanno decodificare |
| `_OPERABLE` | `mind/facts.py:92-94` | 10 domini, **2 raggiungibili** | quali «si accendono e si spengono» |

Le altre diciotto stanno in `mind/baseline.py` (8), `home_space/briefing.py` (6),
`home_space/topology.py` (5 fra traduzioni e severità), `home_space/historian.py`,
`proxy/entity_cache.py`, `mind/watcher.py`, `home_space/queries.py`, `action/verification.py` (2).
`ha_vocabulary.py` è l'unica **già nella forma giusta**: importa dichiarando fonte e versione.

**Il costo, sulla casa vera.** 30 domini presenti; HA ne dichiara 53 e li pubblica lui stesso.
Domini con entità vere di cui **nessuna** delle ventuno liste dice niente: `update` (53 entità),
`button` (70), `number` (35), `select` (19), `input_boolean` (11), `event`, `tag`, `script`,
`zone`, `image`. E **40 `device_class` di `sensor` su 62** non sono mai state nominate da nessuna
parte.

**Il costo, già materializzato.** Un censore scritto in un pomeriggio, girato **una volta**, ha
trovato quattro difetti che mesi di lettura umana non avevano visto:

| difetto | conseguenza |
|---|---|
| 5 stati di `water_heater` (`eco`, `electric`, `gas`, `heat_pump`, `high_demand`) né fra i riposi né fra gli ignoti, mentre il dominio è dichiarato accendibile | un boiler in `eco` apre un episodio **che non si chiude mai** |
| 3 stati di `lock` (`jammed`, `locking`, `unlocking`) nella stessa condizione | e `lock` il pavimento lo raggiunge davvero |
| `_CLASS_MEANING["damper"]` irraggiungibile | `damper` è una `CoverDeviceClass`, non una di `binary_sensor` |
| 5 domini con bit di capacità e nessuna tabella | `ai_task`, `assist_satellite`, `humidifier`, `lawn_mower`, `lock` |

Nessuno morde su questa casa — non ha né boiler né serrature né tosaerba. Tutti mordono il giorno
in cui il proprietario ne compra uno. **Ed è esattamente il difetto contro cui il commento di
`facts.py:85-91` metteva in guardia**: *«un dominio aggiunto a metà produce oggetti che non si
chiudono mai»*.

---

## §2 · Il soggetto dell'anagrafe: il tipo

Il proprietario ha imposto la forma, il 07/09:

> *«Non possono essere una lista sola dove si accede con 3 metriche per evitare sovrapposizioni?
> Ti ricordo le regole del progetto, le stiamo rispettando?»*

Una ricognizione aveva raccomandato di tenerle separate, *«perché rispondono a tre domande
diverse»*. **L'argomento non regge, e le fondamenta lo dicono in tre punti su quattro**: oggi
`light` vive in `_FEATURE_NAMES`, vive in `_OPERABLE` e **non** vive in `aspect()` — tre case per
lo stesso soggetto (*nessun doppione*), tre forme da tre porte (*consistenza*), nessuna che lo
interpreti da sola (*atomicità*).

> **L'errore da nominare: scambiare TRE DOMANDE per TRE CASE.** Le domande restano tre. Si
> rispondono da una riga sola, con tre metriche per accedervi.

**E il soggetto di quella riga non è il dominio: è il TIPO.** Metà delle ventuno liste non è
indicizzata per dominio ma per coppia — `_PRESENZA`, `_APERTURA`, `_COMFORT`, `_QUALITA_ARIA`,
`_ENERGIA`, `_SICUREZZA_BINARIA`, `_SICUREZZA_SENSORE`, `_CLASS_MEANING` parlano tutte di
`(dominio, device_class)`. Un'anagrafe per solo dominio non le conterrebbe, e ne nascerebbe una
ventiduesima lista accanto.

Quindi:

> **Un tipo è un dominio, oppure una coppia (dominio, `device_class`).**
> L'anagrafe ha una riga per tipo. I tipi con classe pendono dal loro dominio: una riga di
> `(sensor, energy)` non ripete ciò che la riga di `sensor` già dice — si collega, come vuole la
> seconda fondamenta.

---

## §3 · La forma della riga: provenienza per campo

Una riga mescola inevitabilmente **fatti del fornitore** e **giudizi nostri**. Confonderli
sarebbe il difetto ricorrente di questa codebase — *due cose diverse dette con una parola sola* —
alla sua scala più grande.

**Ogni campo dichiara da dove viene.** Tre provenienze, e non di più:

| provenienza | vuol dire | invecchia? |
|---|---|---|
| **`chiesto`** | letto da questa casa adesso (traduzioni, registro dei servizi) | **no**: è il dato di adesso |
| **`importato`** | copiato dal sorgente o dalla documentazione di HA, con la versione da cui viene | **sì**: si data e si sorveglia |
| **`nostro`** | un giudizio che HA non può darci | **no**, ma **può restare indietro rispetto a ciò che esiste** — ed è ciò che il censore misura |

Così un giudizio nostro non si può leggere come un fatto di Home Assistant, e viceversa. È la
prima fondamenta applicata al vocabolario: *un oggetto porta tutto ciò che serve a interpretarlo
da solo* — e «da dove viene questo» è parte dell'interpretazione.

### Le tre metriche

Sono le tre domande di prima, diventate tre modi di interrogare la stessa casa:

1. **«Serve all'obiettivo?»** → la gamba (`chi c'è`, `comfort`, `dispersione`, `energia`,
   `buono stato`, `sicurezza`) o `None`. Provenienza: **`nostro`**, sempre. Sostituisce `aspect()`
   e le sue otto liste satellite.
2. **«Cosa sa fare?»** → i bit di capacità decodificati. Provenienza **mista**: l'*esistenza* dei
   bit è `chiesto` (registro dei servizi), il loro *nome* è `importato` (sono `IntFlag` nel
   sorgente di HA, §4 C10).
3. **«Si accende e si spegne, e qual è il suo riposo?»** → `accendibile` più i suoi stati di
   riposo. L'*enumerazione* degli stati è `chiesto`; **quale sia il riposo è `nostro`** — nessuna
   API di HA lo dice, e non lo dirà mai.

---

## §4 · Cosa si chiede a HA, e cosa no

Misurato il 07/09/2026 sulla casa vera. **Un comando solo**, che HIRIS dalla 3.22.3 già manda:
`frontend/get_translations`, `category: "entity_component"` — **801 chiavi, 63.555 byte, 41 ms**,
nessun `@require_admin`, già tradotte nella lingua della casa.

| | conoscenza | HA la pubblica? | dove |
|---|---|---|---|
| C1 | elenco dei domini **caricati** | **sì** — 53 | `entity_component` |
| C3 | stati canonici per dominio | **sì** — 31 domini con enumerazione | `component.{dom}.entity_component._.state.{stato}` |
| C4 | stati per (dominio, classe) | **sì** | `…entity_component.{classe}.state.{stato}` |
| C5 | `device_class` per dominio, **col nome reso** | **sì** — `sensor` 62, `number` 58, `binary_sensor` 28 | stesse chiavi |
| C7 | valori legali di `state_class` | **sì** — 4 (uno più dei nostri 3) | `…state_attributes.state_class.state.*` |
| C9 | attributi di stato per dominio, coi valori legali | **sì** — 382 chiavi | idem |
| C11 | **esistenza** dei bit di capacità | **sì, parzialmente** | registro dei servizi, valori numerici |
| C13 | quali domini si accendono e si spengono | **sì — 16 domini** | `turn_on`+`turn_off`/`toggle` nel registro dei servizi |
| C19 | versione e lingua della casa | **sì** | `get_config` |
| C2 | elenco **esaustivo** delle piattaforme (non solo le caricate) | **no** | `generated/entity_platforms.py`, 45 voci |
| C6/C8 | il **significato** di una classe o di uno `state_class` | **no** | sorgente + documentazione |
| C10 | i **nomi** dei bit di capacità | **no** | `IntFlag` nel sorgente |
| C14 | **quale stato è «a riposo»** | **no** | giudizio nostro |
| C15 | traduzione di `unavailable`/`unknown` | **no** | resi grezzi prima di ogni gradino |
| C16/C18 | enumerazione di `EntityCategory` e `ConfigEntryState` | **no** | `const.py`, `config_entries.py` |

### Una frase del nostro codice è falsa, e va corretta

`mind/facts.py:14-27` afferma che HA *«non dichiara da nessuna parte quale dominio funziona come
un interruttore, quindi la lista va mantenuta a mano»*. **Lo dichiara**: il registro dei servizi
isola 16 domini con `turn_on` **e** `turn_off`, o `toggle`.

La derivazione **non coincide** con `_OPERABLE`, e sbaglia in **entrambi** i versi: perde
`vacuum` (che HA comanda con `start`/`stop`/`return_to_base`) e guadagna `automation`, `script`,
`input_boolean`, `camera`, `remote`, `siren`, `homeassistant` — dove `on` significa «abilitata»,
non «accesa», che è il difetto che `briefing._EVENT_DOMAINS` documenta di aver già pagato.

> **Quindi il derivato non sostituisce il giudizio: lo SORVEGLIA.** `accendibile` resta `nostro`,
> ma diventa un **sottoinsieme dichiarato** di ciò che HA dice accendibile, con le eccezioni
> **scritte e motivate** — una per `vacuum`, sette per le esclusioni.

### I tre silenzi della lettura

La lettura da HA può non riuscire, e allora vale la legge del prodotto: **chi produce il motivo
lo etichetta.** Il contratto esiste già in `proxy/state_translations.py:154-195` e va **esteso,
non reinventato**:

1. **«non ho potuto chiedere»** — con il motivo dichiarato da chi ha fallito.
2. **«ho chiesto e non c'è»** — il tipo esiste, quella conoscenza no.
3. **«ho chiesto una cosa che non esiste»** — `category` non è validata da HA: una categoria
   inesistente risponde **`success: true` con zero chiavi**. Misurato. Senza questo terzo caso,
   un refuso nella `category` farebbe dire a HIRIS *«questa casa non ha domini»*.

E una regola di prudenza già scelta altrove (`topology.rebuild()`): **un guasto non invalida la
tabella buona di prima.** Se `(versione_ha, lingua)` non sono cambiate, si continua a rispondere
con ciò che si ha — una tabella che c'è vale più di un vuoto dichiarato fresco.

---

## §5 · Il censore

È **la parte che risponde al mandato**, ed è una sola perché la casa è una sola.

> **`pubblicato` − `rivendicato dall'anagrafe` = `da decidere`.**
> Ciò che resta ha un nome, e obbliga qualcuno a decidere.

Gira su cinque materie: domini, `device_class` per dominio, stati per tipo, valori di
`state_class`, bit di capacità per dominio. **Costa zero chiamate nuove**: entrambe le fonti sono
già in cache, e il registro dei servizi si invalida già da sé su `service_registered` /
`service_removed` (`proxy/ha_client.py:68`, listener a `:2264-2413`). Un'integrazione installata
oggi entra nel confronto senza una riga di rete in più.

**Il censore non decide: obbliga a decidere.** Ogni voce che emerge va chiusa in uno dei due modi,
e non c'è un terzo:

- entra nell'anagrafe con il suo giudizio;
- resta fuori con un'**eccezione motivata e scritta**.

**E questo è il limite onesto del mandato.** Il proprietario ha chiesto che HIRIS *«se si accorge
che sono obsolete, le aggiorni»*. Accorgersene: sì, da solo. **Aggiornare il giudizio: no** — e
fingere il contrario produrrebbe una lista che *sembra* verificata e non lo è, che è peggio di
una lista dichiaratamente vecchia.

**Dove vive il censore.** È **una prova che fallisce**, non un rapporto che qualcuno deve
ricordarsi di leggere. Con un vincolo che va rispettato o la prova diventa un capriccio: la suite
gira **senza la casa**. Quindi il censore confronta l'anagrafe con un **istantaneo del pubblicato,
versionato nel repository e datato**, e una prova separata — che gira solo quando la casa è
raggiungibile — verifica che l'istantaneo non sia scaduto. Due prove, due fallimenti diversi:
*«l'anagrafe non copre ciò che HA pubblica»* e *«l'istantaneo non è più quello di questa casa»*.

---

## §6 · Cosa si cancella

**Quattro liste spariscono**, e sono un doppione **peggiore dell'originale**:

| lista | perché sparisce |
|---|---|
| `_STATE_TRANSLATION` (`topology.py:414-430`, 17 voci) | **cieca al dominio**: traduce `open` allo stesso modo su `lock` e su `cover`. HA no |
| `_CLASS_MEANING` (`:444-489`, 29 voci per 28 classi vere) | tutte e 28 pubblicate; la ventinovesima non esiste |
| `_READABLE_HVAC_MODE` (`:500-504`, 7 voci) | le stesse 7, pubblicate |
| `_READABLE_HVAC_ACTION` (`:510-514`, 7 voci) | HA ne pubblica **9**: ci mancano `defrosting` e `preheating` |

E tutte e quattro sono **in italiano fisso**, mentre HA risponde nella lingua della casa.

**Due vincoli sulla cancellazione**, e vanno rispettati o la cura peggiora il male:

1. **Si cancella solo se il consumatore sa dire «traduzioni non lette».** Una tabella a mano non
   fallisce mai; la rete sì. Il contratto etichettato del §4 è la condizione, non un contorno.
2. **`_CLASS_MEANING` porta una cosa che HA non dà**: la **coppia** acceso/spento tenuta insieme
   — `("bagnato", "asciutto")`. Si ricostruisce dalle due chiavi `.state.on` e `.state.off`, ma
   **va ricostruita, non assunta**.

---

## §7 · Cosa NON diventa importato, mai

**La gamba.** *«Questa entità serve all'obiettivo della casa»* è il giudizio più nostro che ci
sia, e nessuna enumerazione di HA lo potrà mai contenere.

Ma anche la gamba guadagna il censore: quando HA pubblica una `device_class` nuova su `sensor`,
la domanda *«serve a una delle sei gambe?»* deve essere **posta**. Oggi non lo è — e le 40 classi
di `sensor` mai nominate sono la misura di quanto non lo sia.

---

## §8 · L'analisi d'uso: chi legge l'anagrafe

Il proprietario ha chiesto di **estendere l'analisi all'utilizzo**. Non basta unificare le liste:
vanno guardati i **lettori**, perché è lì che una lista sbagliata diventa una frase sbagliata.

I lettori noti, da percorrere uno per uno durante la fetta:

| lettore | cosa legge oggi | cosa cambia |
|---|---|---|
| `mind/baseline.py::aspect` | L1, L4-L11 | interroga l'anagrafe con la metrica «gamba» |
| `mind/facts.py::genre_for` | L3, L12, L13 | metrica «accendibile + riposo» |
| `home_space/topology.py::decoded_capabilities` | L2 | metrica «capacità» |
| `home_space/topology.py::translate_state` e i suoi tre satelliti | L20-L23 | **spariscono**: legge le traduzioni chieste |
| `home_space/briefing.py` | L14-L19 | l'anagrafe, con i suoi giudizi |
| `proxy/entity_cache.py::_DOMAIN_ATTRS` | L26 | da valutare: è una scelta di *cosa conservare*, non di cosa esiste |
| `home_space/queries.py::LINK_NAME` | L28 | tipi di **riferimento**, non di entità: probabilmente resta fuori |
| `action/verification.py` | L29, L30 | giudizi sull'azione, non sul tipo |

**Per ogni lettore, la domanda è la stessa**: continua a dire il vero quando l'anagrafe dice «non
lo so»? Un lettore che oggi non può ricevere un «non lo so» — perché la sua lista non fallisce
mai — è un lettore che va preparato prima di togliergli la lista da sotto.

---

## §9 · Cosa non entra in questa fetta

| cosa | perché |
|---|---|
| **La luce accesa col sole alto** | è nel registro, e viene **dopo**: è un tipo che entra nel pavimento, e prima serve la casa dove metterlo |
| **L'analista** | sprint suo, dichiarato dal proprietario |
| Le colonne e le chiavi italiane | debito noto, si migrano in una fetta loro |
| `_DOMAIN_ATTRS`, `LINK_NAME`, i due di `verification.py` | si **valutano** (§8), non si assume che entrino |
| Riempire i giudizi mancanti sui domini nuovi | il censore li **nomina**; deciderli è lavoro del proprietario, non di questa fetta |

---

## §10 · Le prove

Ogni prova deve poter **fallire**. Dove sarebbe una tautologia, si dice e non si scrive.

1. **Un tipo ha una casa sola** — nessun dominio e nessuna coppia (dominio, classe) compare in due
   posti diversi del prodotto. Mutazione da uccidere: rimettere una delle ventuno liste accanto
   all'anagrafe.
2. **Ogni campo dichiara la sua provenienza**, e le provenienze sono tre. Un campo senza
   provenienza non passa.
3. **Il censore nomina ciò che non è coperto** — messo davanti a un istantaneo che contiene un
   dominio ignoto, lo nomina; messo davanti a uno coperto per intero, tace. **Due prove, non
   una**: una che passa perché non c'è niente da trovare non dimostra di saper trovare.
4. **Un dominio accendibile porta il suo riposo, nella stessa modifica** — la regola che oggi è
   una raccomandazione in un commento (`facts.py:85-91`) diventa una prova che fallisce. È il
   difetto dei 5 stati di `water_heater`, reso impossibile.
5. **Le eccezioni sono motivate** — `vacuum` fuori dalla derivazione di HA, e le sette esclusioni,
   portano una ragione scritta. Un'eccezione senza motivo non passa.
6. **I tre silenzi restano tre** fino al lettore: «non ho potuto chiedere», «ho chiesto e non
   c'è», «ho chiesto una cosa che non esiste» non collassano in un vuoto.
7. **Un guasto non invalida la tabella buona di prima** — a `(versione_ha, lingua)` invariate,
   una lettura fallita non svuota ciò che si ha.
8. **La coppia acceso/spento si ricostruisce** dalle due chiavi di HA, e la ricostruzione fallisce
   dichiarandolo quando una delle due manca.
9. **Le quattro tabelle cancellate non hanno più chiamanti** — né nel prodotto né nei test.
10. **L'istantaneo del pubblicato è datato**, e una prova che gira solo con la casa raggiungibile
    dice quando è scaduto.

E una prova che **non** si scrive: che il proprietario capisca. Quella la fa lui, sulla casa vera,
e senza di lei nessuna delle dieci sopra vale niente.

---

## §11 · Due decisioni prese durante la fetta 1

### `tipo` e `tipologia` non sono la stessa parola

Il nome «vocabolario dei tipi» sfiora `docs/design/2026-08-16-il-vocabolario-delle-tipologie.md`,
che esiste già e parla di *cosa una cosa è, e cosa significano i suoi valori* — nato da una
risposta sbagliata sul «Notevole adesso» del nucleo (300 elementi su 845, e HIRIS che sapeva
**che** due luci erano accese ma non **quali**).

**Non sono due vocabolari, e non sono due nomi per la stessa cosa:**

| | |
|---|---|
| **`tipo`** | la **chiave** della riga: un dominio, o una coppia (dominio, `device_class`) |
| **`tipologia`** | **un campo** di quella riga: cosa quella cosa **è** per chi legge — una luce, un sensore di porta, un rivelatore di fumo |

Il vocabolario delle tipologie è **la prima metà di questo**, costruita per un consumatore solo.
Alla **fetta 6** non si affianca: **si fonde**. La tipologia diventa un campo della riga del tipo,
con la sua provenienza, e il documento del 16/08 resta come verbale datato.

**Stessa sorte, e stessa ragione, per `ha_vocabulary.py`**: `DEVICE_CLASS_MEANING` è indicizzato
per `(dominio, classe)`, che è **esattamente la chiave di un tipo**. È il candidato dichiarato a
diventare un campo `meaning` con provenienza `importato`. Alla fetta 1 i due moduli restano
separati con il confine scritto in entrambi i docstring — nessun fatto vive di qua e di là — ma
la separazione è **provvisoria per decisione**, non per disegno.

### Gli stati che non appartengono a nessun tipo

`ABSENT_STATE_FORMS` (`""`, `"none"`) e `UNKNOWN_STATES` (`unavailable`, `unknown`) **attraversano
ogni tipo**: attribuirli a uno solo sarebbe una bugia. Non stanno su nessuna riga, portano la loro
provenienza, e una prova verifica che non esistano stati orfani.

**È una scelta, non un fatto**: la forma reggerebbe anche una riga «qualunque tipo». Si è preferito
non inventare un tipo che non esiste per ospitare qualcosa che è di tutti.

---

## §12 · Il requisito del proprietario: HIRIS eredita TUTTO

Dettato il 07/09/2026, dopo aver visto l'analisi degli attributi:

> *«Vorrei che di un'entità vengano ereditati da HIRIS tutti gli attributi, per capire fino in
> fondo cosa può fare e cosa sta facendo ora. A caratteri generali, proprio come HA può
> riconoscere e gestire quel dispositivo. Questo è il mio obiettivo, e così deve essere come
> requisito.»*

**È un requisito, non una preferenza.** E supera ogni raccomandazione precedente di questo
documento che vada in senso contrario.

### Il metro di accettazione

> **HIRIS deve poter capire di un dispositivo ciò che Home Assistant capisce, e poter fare ciò che
> Home Assistant sa fare con lui.**

È verificabile e non è un'opinione: si prende un'entità, si guarda cosa l'interfaccia di HA sa
dirne e sa farci, e si controlla che HIRIS non sia più povero. Se lo è, il difetto è nostro.

### La distinzione che rende il requisito realizzabile

**«Ereditare» e «scrivere nel contesto del modello» sono due cose diverse**, e confonderle è ciò
che aveva prodotto le tre esclusioni raccomandate dall'analisi:

| | regola |
|---|---|
| **Cosa HIRIS eredita e conserva** | **tutto, senza eccezioni.** 121 KB per le 835 entità dell'intera casa: il volume non è mai stato il problema |
| **Cosa finisce scritto nel testo che il modello riceve** | decisione a valle, che riguarda **una sola** famiglia |

Delle tre famiglie che l'analisi proponeva di escludere, **due non erano perdite di
informazione**: «ha già una porta propria» (il dato c'è, arriva da un'altra strada — era un
anti-doppione) e «presentazione» (`icon`, `entity_picture`: grafica, non capacità).

**La terza — credenziali e maniglie — è l'unica vera**, e nemmeno lei è un'eccezione al requisito:
HIRIS le eredita e le può usare. Il punto è che **una trascrizione di chat viene salvata su disco
e finisce nel registro**: un token della telecamera scritto lì dentro ci resta. Quindi nel testo
che va al modello compare *«questa entità porta un token di accesso»* invece del token — **il
fatto c'è, la chiave no**. È una scelta operativa, dichiarata, e il proprietario può ribaltarla.

### Le conseguenze sul disegno

1. **La lista degli ammessi per dominio (`_DOMAIN_ATTRS`) sparisce** come criterio di cosa
   conservare. Nove domini su trenta, e per quei nove i soli valori correnti, è l'opposto del
   requisito.
2. **Capacità e valori restano due cose diverse** — ma non perché una si tiene e l'altra no:
   perché HA stesso le separa (`<Dominio>EntityCapabilityAttribute` /
   `<Dominio>EntityStateAttribute`, `StrEnum` per dominio a `2026.9.1`) e perché rispondono a due
   domande diverse: *cosa può fare* e *com'è adesso*.
3. **Gli attributi di cui non conosciamo il significato escono lo stesso**, sotto un'etichetta
   loro. «Non so cosa sia» e «so cosa sia» non sono la stessa cosa, e nessuno dei due è «non
   esiste». Vale per gli attributi del costruttore — `ave_window_state` su un termostato AVE vuol
   dire «finestra aperta», ma **nessuna fonte pubblica lo dichiara**: l'integrazione non è in HA
   core, non è su GitHub, e l'unica AVE pubblica emette nomi diversi a ogni versione. Quel
   significato o lo dice il proprietario, o resta non interpretato — **mai indovinato**.
4. **Un `null` non è un'assenza di capacità.** Misurato: `light.alberello` consegna oggi
   `{'brightness': None}` — che si legge «questa luce non ha luminosità» mentre la luce è solo
   spenta. È peggio di non dire niente.

---

## §13 · L'altra metà del requisito: poter FARE ciò che HA sa fare

Il metro del §12 ha due gambe, e la seconda è *«poter fare ciò che Home Assistant sa fare con
lui»*. Il proprietario l'ha resa esplicita il 07/09:

> *«Anche il modello, quindi, con azione deve saper cambiare colore all'Alberello o abbassare la
> luminosità.»*

### Cosa c'è già, misurato

**Il meccanismo per agire esiste.** Lo strumento `execute` (`home_space/tools.py:677`) accetta un
campo `dati` coi parametri del servizio: `light.turn_on` con `{"rgb_color": [255,0,0]}` o
`{"brightness_pct": 30}` è già una chiamata legale, e `action/verification.py` controlla che il
parametro **appartenga** a quel servizio leggendo `fields` dal registro.

### Cosa Home Assistant pubblica, e chiude il cerchio

`GET /api/services` su questa casa, per `light.turn_on`:

```
parametri:  brightness_pct · brightness_step_pct · color_temp_kelvin
            effect · rgb_color · transition · additional_fields

color_temp_kelvin
   filter:    { attribute: { supported_color_modes: [color_temp, hs, xy, rgb, rgbw, rgbww] } }
   selector:  { color_temp: { unit: kelvin, min: 2000, max: 6500 } }
```

**La riga `filter` è la giuntura, e non la inventiamo noi**: è Home Assistant che dichiara a quali
entità quel parametro si applica, e lo fa guardando **esattamente l'attributo che il §12 recupera**
(`supported_color_modes`). Le due metà del requisito — sapere e fare — si incastrano su una chiave
che HA pubblica già.

### I tre buchi, e sono tutti di conoscenza, non di meccanismo

1. **Il modello non sa che quella luce fa colore.** Lo chiude il §12.
2. **Il modello non sa quali parametri accetta un servizio.** HIRIS **ha** il registro dei servizi,
   lo tiene in memoria e lo invalida sugli eventi — e **lo usa solo per rifiutare**. Nessuno
   strumento mostra al modello i parametri di `light.turn_on` coi loro limiti: lui li scopre
   sbagliando. *Sappiamo la risposta e la usiamo solo per dire di no.*
3. **Le capacità fini non si verificano prima di comandare**, ed è dichiarato in
   `action/verification.py:18` sotto «cosa NON verifica, di proposito»: *«le capacità fini
   (`supported_features`: questa luce si attenua?)»*. Con il `filter` di HA e gli attributi
   recuperati, quella rinuncia non è più necessaria.

### Una trappola misurata, che decide chi ha ragione fra due fonti

Il **selettore** di HA per `color_temp_kelvin` dichiara **2000–6500 K**. L'**Alberello** dichiara
`min_color_temp_kelvin: 1500`, `max_color_temp_kelvin: 9000`.

> **I limiti veri dell'entità sono più larghi di quelli generici del servizio.** Se il controllo si
> fermasse al selettore, HIRIS negherebbe una temperatura che quella lampadina sa fare davvero.
> **Vince l'entità**: il selettore descrive il campo di un cursore, non il dispositivo.

### Cosa deve saper fare, alla fine

| | |
|---|---|
| «cambia colore all'Alberello» | **funziona** |
| «abbassa la luminosità dell'Alberello» | **funziona** |
| «cambia colore alla presa della lavatrice» | **rifiutato da noi, con una frase che dice perché** — non da HA con un errore tecnico |
| «metti l'Alberello a 8000 K» | **funziona**, perché quella lampadina arriva a 9000, anche se il cursore generico si ferma a 6500 |

---

## §14 · Tre decisioni prese sull'eredità degli attributi

### Le chiavi della vista restano in italiano

Il vincolo «chiavi nuove in inglese» **non si applica qui**, e confermo la scelta dell'implementer.
La vista di `guarda` è italiana da sempre (`attributi`, `capacita`, `stato_leggibile`): quattro
chiavi inglesi in mezzo l'avrebbero resa bilingue. Vale la regola del progetto — **dominio in
italiano, confine nella lingua del sistema esterno** — e la vista verso il modello è dominio, non
confine. L'inglese resta obbligatorio per gli identificatori del codice e per le colonne nuove.

### `campo_di_manovra`, non `capacita`

`detail["capacita"]` esiste già e significa altro (i bit di `supported_features` resi in verbi).
Riusare la stessa parola sarebbe stato commettere *«due cose diverse dette con una parola sola»*
**nell'atto stesso di curarlo**.

### La regola che scioglie due esiti opposti

`number.mode` è stato tolto dalle capacità **contro** la classificazione di HA (due fonti
indipendenti); `alarm_control_panel.code_format` è stato lasciato dove HA lo mette, pur essendo
funzionalmente un limite. Stessa forma, esito opposto, e la regola che li distingue è scritta nel
codice:

> **Il fornitore comanda sulla classificazione finché non è smentito da una FONTE, non finché non
> è smentito dal nostro senso.**

---

## §15 · Cosa resta aperto dopo l'eredità

1. **Il nucleo non riceve le capacità aggregate**, quindi il modello **non sa di poter chiedere**.
   Una firma aggregata è **mappa**, non dettaglio, quindi non contraddice la decisione «la
   completezza va nel dettaglio». Si incrocia con la voce «Il nucleo è statico» del registro.

   > **CORREZIONE del 08/09, e l'errore era di chi scrive.** Questo punto diceva *«35 firme
   > distinte per 2.349 caratteri su un tetto di 6.000: ci stanno»*. **Confrontava l'aggiunta col
   > TETTO invece che con lo SPAZIO LIBERO**, che è quasi zero: il nucleo della casa vera pesa
   > **5.676 su 6.000** — misurato dal vivo — e **tronca già**, escludendo nove elementi notevoli.
   >
   > **SECONDA CORREZIONE, R4 della revisione del tratto v3.23.0..HEAD (08/09/2026, poche ore
   > dopo la prima)**: questo paragrafo diceva «sette elementi» e «~6 voci di comportamento su
   > 21» — due numeri che la fetta successiva, con la ricostruzione verificata riga per riga
   > contro il nucleo vivo del 3.23.0 (`.superpowers/sdd/tipi-di-entita/fetta-censore-report.md`
   > §A.2-A.3), ha smentito: sono **nove**, non sette, e **venti** voci di comportamento (non
   > 21), delle quali **sette** restano fuori. Il "~6 su 21" era la stima meno verificata delle
   > due, presa poche ore prima di quella piu' accurata; questa correzione allinea la spec alla
   > misura migliore, non il contrario.
   >
   > Ridotte a 671 caratteri (tenendo le enumerazioni e buttando i numeri: la firma è mappa, il
   > valore è dettaglio di `view`), le capacità entrano lo stesso — ma sfratterebbero **«Notevole
   > adesso» per intero** e sette voci di comportamento su venti. **La mappa delle stanze non
   > perde una riga**, perché le capacità stanno prima di `casa` nell'ordine di taglio e una
   > prova lo inchioda.
   >
   > **Deciso dal proprietario l'08/09: il tetto sale a 6.800**, così entrano entrambi e non si
   > perde niente. Costa ~200 token per turno, letti dalla cache — sul ponte, 5,6 milioni letti
   > contro 662 freschi.
   >
   > **Resta un rischio dichiarato e non chiuso**: alzare il tetto non impedisce che la PROSSIMA
   > sezione aggiunta sfratti «Notevole adesso» di nuovo, e in silenzio. Solo un minimo garantito
   > lo impedirebbe — come già ce l'ha la mappa delle stanze. Non è stato fatto: è una scelta, non
   > una dimenticanza.
2. ~~**`sensor.options` e `select.options` escono sotto la stessa etichetta**~~ — **CHIUSO dalla
   fetta dell'azione, 07/09/2026.** Erano *«cosa questa entità può assumere»* contro *«cosa le si
   può imporre»*: per chi legge una sfumatura, **per chi comanda la differenza fra un'azione
   possibile e una impossibile**. Separati alla fonte
   (`type_vocabulary._ASSUMABLE_ATTRIBUTES`, con la ragione scritta voce per voce), in due ceste
   diverse — `campo_di_manovra` e `valori_che_puo_assumere` — e i due insiemi sono disgiunti per
   costruzione, non per l'ordine con cui qualcuno li guarda. Rapporto:
   `.superpowers/sdd/tipi-di-entita/fetta-azione-report.md`.
