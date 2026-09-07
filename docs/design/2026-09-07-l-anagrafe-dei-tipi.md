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
