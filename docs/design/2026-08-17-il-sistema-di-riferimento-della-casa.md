# Il sistema di riferimento della casa

> Fetta A di «chiudere la conoscenza a 360°».
> Misurata con le **quattro fondamenta** di `CLAUDE.md`.

## Il difetto

Un valore senza il suo sistema di riferimento non è un dato: è un numero.

`72` non vuol dire niente finché non si sa se sono gradi Celsius o Fahrenheit.
«Domani alle 8» non vuol dire niente senza il fuso. «Costa 40» non vuol dire
niente senza la valuta.

HIRIS leggeva la casa intera — piani, aree, dispositivi, entità, automazioni —
e non leggeva **la scala su cui è disegnata**. Home Assistant la dichiara, in
un comando solo, e HIRIS non lo chiamava.

## Cosa entra, e cosa no

Da `get_config` (WS `handle_get_config`, forma `Config.as_dict()` in
`homeassistant/core_config.py` — verificata alla fonte, non a memoria):

| Entra | Sotto il nome | Perché |
|---|---|---|
| `time_zone` | `fuso` | senza, ogni orario è ambiguo |
| `unit_system` | `unita` | le otto misure con cui ragiona la casa |
| `currency` | `valuta` | «costa 40» |
| `language` | `lingua` | la lingua in cui l'utente ha scritto i nomi |
| `country` | `paese` | festività, formati, fornitori |
| `location_name` | `nome` | la casa ha un nome proprio |
| `version` | `versione_ha` | nessuno in HIRIS sapeva su che HA gira |

| **Non** entra | Perché |
|---|---|
| `components` | è l'elenco delle integrazioni: l'anagrafe **ce l'ha già** nella tabella `integrazioni`. Fondamenta 2. |
| `latitude`/`longitude` | non serve a nessuna domanda di oggi. Un dato del genere non si tiene «per ogni evenienza» |
| `state` | è **momentaneo**. In un archivio che si rilegge di rado mentirebbe poche ore dopo — ed è peggio che non saperlo. Chi vuol sapere se HA è su lo chiede a HA, non a una fotografia di ieri |

Le otto chiavi di `unit_system` (`length`, `area`, `mass`, `pressure`,
`temperature`, `volume`, `wind_speed`, `accumulated_precipitation`) sono state
verificate **una per una** in `homeassistant/const.py`. Non è pedanteria: è la
stessa verifica che, se fatta prima, avrebbe evitato `co` al posto di
`carbon_monoxide` — un allarme monossido sparito in silenzio.

## Dove vive, e perché lì

**Nell'anagrafe, in `meta`.** Il sistema di riferimento è una proprietà della
casa quanto le sue aree. Un secondo posto da tenere aggiornato sarebbe un
secondo posto da cui leggere una versione diversa della stessa verità.

Da lì esce da **due porte, con la stessa forma**: `/api/casa`
(`sistema_di_riferimento`) e il nucleo (due righe in testa a «La casa»). Se il
modello lo leggesse nel digesto e la pagina no, sarebbero due case diverse a
seconda della porta da cui entri.

## La trappola, e la prova che la tiene chiusa

**Le unità della casa non sono l'unità di un'entità.**

Home Assistant converte **all'ingresso dell'entità**, non alla lettura: una
casa metrica può contenere benissimo un sensore in Fahrenheit, e un sensore
senza unità — un indice, un contatore — non è «gradi» solo perché la casa è
metrica. Chi usasse `unita.temperature` come ripiego scriverebbe un'unità sotto
un numero che non ce l'ha, e chi legge non avrebbe modo di accorgersene.

È scritto tre volte, dove serve: nel docstring di `sistema_di_riferimento`, in
quello di `_righe_sistema`, e **nel nucleo stesso** — la riga finisce con
*«ogni entità porta la propria: se manca, manca — non è questa»*, perché anche
il modello che legge può fare da solo l'errore che il codice non fa più.

E c'è una prova che il difetto lo sa **produrre**:
`test_le_unita_della_casa_non_diventano_l_unita_di_un_entita` passa dal
dispatcher — non dal nucleo — perché è lì che il difetto nascerebbe davvero.
Provata per mutazione: con il ripiego dentro, fallisce; senza, passa.

> Una prima versione di questa prova stava sul nucleo e **non poteva fallire**:
> il digesto stampa stati tradotti («acceso», «bagnato»), mai un numero con la
> sua unità. È il difetto n.1 di questo progetto, ed è ricomparso qui.

## La parola già presa

La prima stesura chiamava questo oggetto `riferimento`. Ma `riferimento` in
HIRIS **significa già un'altra cosa**, ovunque: è l'identificativo della cosa
che guardi (`guarda(tipo, riferimento)`, le ancore dei ricordi,
`Indice.verifica`). Due significati per una parola sola è esattamente ciò che
la fondamenta «consistenza» vieta.

Ha ceduto il nuovo arrivato: `sistema_di_riferimento`.

## Quando si rilegge

`core_config_updated` (verificato: `EVENT_CORE_CONFIG_UPDATE` in
`homeassistant/const.py`) entra in `EVENTI_ANAGRAFE`, **non** in una quarta
famiglia di ascoltatori tutta per un evento solo. Cambiare fuso o passare da
metrico a imperiale cambia il significato di ogni valore che HIRIS legge:
senza, HIRIS ragionerebbe per sempre col riferimento di quando è partito.

## Cosa non cancella

Una lettura fallita **non azzera** il sistema di riferimento precedente —
stessa dottrina con cui l'anagrafe non si sostituisce quando tutti i registri
sono caduti. Il fuso di ieri è ancora il fuso giusto; un riferimento
cancellato farebbe leggere ogni temperatura senza sapere in che scala.

Il silenzio si dichiara con il meccanismo che esiste già: `sistema_di_riferimento`
finisce in `non_disponibili`, la stessa lista con cui l'anagrafe dichiara ogni
altro registro caduto. Nessun meccanismo nuovo per dire la stessa cosa.

## Le quattro domande

- **Chi lo riceve può interpretarlo senza sapere altro?** Sì: il nucleo dichiara
  fuso, valuta, lingua e unità prima di ogni numero che seguirà.
- **Questo fatto vive già da qualche altra parte?** No — ed è per questo che
  `components` è rimasto fuori: quello sì.
- **Ha la stessa forma da tutte le porte?** Sì: `/api/casa` e il nucleo leggono
  lo stesso `ArchivioCasa.sistema_di_riferimento()`.
- **Esiste un modo per chiederlo?** Sì, due.
