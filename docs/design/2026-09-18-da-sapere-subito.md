# «Da sapere subito» — il giudizio che dice cosa merita la prima riga

`spec · 18/09/2026 · fetta piccola, precede la pagina dell'osservatore`

Nasce da un difetto trovato **misurando** mentre si scriveva la spec della pagina
(`2026-09-18-la-pagina-dell-osservatore.md`): il criterio «cosa è fuori dal solito» non ha nel
sapere una parola sua, e quella che sembrava servire ne dice un'altra.

---

## §1 · Il fatto, misurato il 18/09/2026 sulla casa vera (3.49.0)

La pagina nuova deve mettere in cima «ciò che esce dal solito», e la decisione del proprietario è che
**il criterio lo dice il sapere**, non il codice. Provato contro i giudizi veri, sulla cronaca del
17/09 (75 voci):

| Lettura del criterio | Voci in banda |
|---|---|
| «stato di lavoro **oppure** tipo `notevole: si`» | **71 su 75** |
| restringendo `notevole` alle sole coppie | 18 |
| restringendo anche ai tipi non accendibili | 10 |

**Perché 71.** `notevole: si` nel seme sono **23 righe**, e **10 sono domini interi** — `light`,
`switch`, `cover`, `fan`, `lock`, `media_player`, `remote`, `siren`, `vacuum`, `valve`. Trentacinque
accensioni di luce finiscono in banda.

**La causa non è un errore di calcolo: è una parola che dice due cose.** `notevole` oggi risponde a
*«vale la pena raccontarlo nel riassunto?»* — è così che la usa `home_space/briefing._is_event` — e
la pagina avrebbe voluto usarla per *«è una cosa che devo sapere subito?»*. Una luce accesa è la
prima e non la seconda.

È la regola del proprietario — **due cose diverse dette con UNA parola si separano alla fonte, mai a
valle** — applicata al **dato** invece che al codice.

---

## §2 · Il giudizio nuovo

**Campo:** `da_sapere_subito`. **Tre forme del valore** (decisione del proprietario, 18/09/2026,
dopo la revisione finale): `si`, `no`, oppure **l'elenco degli stati che contano** — con l'assenza
della riga che vale `no`.

| valore | cosa dice |
|---|---|
| `si` | vale la regola del §3: il lavoro, il riposo, il ripiego, «indecidibile vale no» |
| `no` | niente di questo tipo va saputo subito |
| `["jammed"]` | **solo** questi stati entrano in banda, e nient'altro: la regola del §3 non si applica |

Un elenco **vuoto** si rifiuta — direbbe `no` in un secondo modo — e le **forme dell'assenza** non
ci stanno dentro, per la stessa ragione per cui non stanno in un `riposo`: sarebbero una voce morta.

**Perché una terza forma, misurato sulle sedici righe del seme.** Quindici stanno bene col solo
`si`: l'allarme ha un `lavoro` di **un solo** stato (`triggered`), i tredici `binary_sensor` e la
sirena non dichiarano nessun `lavoro` e la regola usa il loro riposo. **La serratura no.** Per
`lock`, `lavoro` significa «sta operando» — `locking`, `opening`, `unlocking`, `unlocked`, `open` —
e `jammed` non è né un lavoro né il riposo (`locked`). Col solo `si`, **ogni sblocco sarebbe la
prima riga e l'inceppamento no**: l'esatto contrario di ciò che serve.

È **la malattia di questa fetta trovata una seconda volta**, e stavolta dentro `lavoro`: per
l'allarme quella parola vuol dire «è successo», per la serratura «si sta muovendo». Non la si cura
qui (separare `lavoro` è una fetta sua, e `lavoro` ha un altro lettore, la ragione italiana che la
cronaca mostra): si smette di **appoggiarcisi** dove non deve. Il seme porta quindi `lock` →
`da_sapere_subito: ["jammed"]` e quindici `si`.

**Domanda a cui risponde:** *«quando una cosa di questo tipo esce dal suo riposo, il proprietario
deve saperlo subito?»* Non «vale la pena raccontarlo» (`notevole`), non «che genere di fatto è»
(`genere`).

**Il nome inglese non si decide in questa fetta**: il glossario vuole che una riga nasca con
l'italiano e che l'inglese si scelga in un passaggio successivo. La riga entra in
`docs/GLOSSARIO.md` con la colonna inglese vuota.

**Il seme: sedici tipi** (decisione del proprietario, 18/09/2026) — i dodici di genere `sicurezza`
più i quattro sensori di apertura:

`alarm_control_panel` · `lock` · `siren` · `binary_sensor.smoke` · `binary_sensor.gas` ·
`binary_sensor.carbon_monoxide` · `binary_sensor.heat` · `binary_sensor.cold` ·
`binary_sensor.moisture` · `binary_sensor.tamper` · `binary_sensor.problem` ·
`binary_sensor.safety` · `binary_sensor.door` · `binary_sensor.window` · `binary_sensor.opening` ·
`binary_sensor.garage_door`

Il seme passa da **99 a 115 celle**.

---

## §3 · La regola che decide, e il difetto che ha già evitato

Una voce di cronaca **entra in banda** se:

1. è un **guasto o un avviso** di un soggetto tecnico (`genere: guasto`); **oppure**
2. il suo tipo ha `da_sapere_subito` con un **elenco di stati** e il suo stato è **uno di quelli**.
   È il **primo ramo**, prima di ogni altro: l'elenco dice già cosa conta, e niente di ciò che
   segue — lavoro, riposo, ripiego — si applica. Messo dopo il lavoro, rimetterebbe in banda ogni
   sblocco di serratura, che è esattamente il caso per cui l'elenco esiste; **oppure**
3. il suo tipo ha `da_sapere_subito: si` **e** il suo stato è un **lavoro** per quel tipo
   (`working_of`); se quel tipo non ha nessun giudizio `lavoro`, vale lo stato che **non è riposo e
   non è una forma dell'assenza**; e se quel tipo non ha **né lavoro né riposo**, la risposta è
   **no**.

**Il riposo si chiede prima all'entità, poi al tipo** (revisione finale, I-2), esattamente come fa
la cronaca (`mind/facts._is_on` → `resting_of(dominio, classe, entity_id)`): `riposo` si corregge
anche per una singola entità, e una regola che lo chiedesse solo al tipo direbbe «notizia» su un
fatto che la cronaca chiama «riposo». `lavoro` e `da_sapere_subito` restano invece coppia →
dominio: `judgments._LEVELS` non li ammette su un'entità.

**«Indecidibile vale no»** (decisione del proprietario, revisione finale, I-1). Per sapere quando
una cosa esce dal suo riposo bisogna sapere qual è il riposo. Senza né lavoro né riposo, il ripiego
«non è un riposo» applicato a un riposo vuoto renderebbe notizia **ogni** stato non assente — `off`
compreso, cioè lo **spegnimento**. Meglio una notizia in meno che una banda piena di spegnimenti.
**Vale per il solo `si`**: per un elenco non c'è niente da decidere — l'elenco dice già quali stati
contano — e un tipo con l'elenco non ha bisogno né di riposo né di lavoro.
**La cura sta nella regola**, non alla porta: la porta rifiuta un `si` scritto su un tipo così
(vedi §5), ma quel rifiuto non protegge l'invariante — si può scrivere il riposo, poi il `si`, poi
togliere il riposo (ritorno al seme, oppure `riposo: '[]'`, che il lettore accetta) e restare con
un `si` orfano.

**La seconda metà della condizione 2 non è un dettaglio: è un difetto già trovato.** Con la prima
stesura — «esce dal riposo» — `alarm_control_panel` in `disarmed` entrava in banda **tutti e otto i
giorni misurati**, perché «disinserito» non è fra i riposi (che sono gli stati armati) e non è un
lavoro. L'allarme disinserito è la normalità della casa, e sarebbe stata la prima riga della pagina
ogni mattina.

---

## §4 · Cosa produce, misurato su otto giorni (10-17/09)

| giorno | voci di cronaca | in banda |
|---|---|---|
| 10/09 | 13 | **0** |
| 11/09 | 25 | 5 |
| 12/09 | 53 | **0** |
| 13/09 | 60 | 10 |
| 14/09 | 42 | 4 |
| 15/09 | 46 | 4 |
| 16/09 | 73 | 8 |
| 17/09 | 75 | 6 |

Totale **37 righe in otto giorni, tutte guasti**: in questa casa, nella settimana misurata, **non è
scattato niente** — nessun fumo, nessun allagamento, nessun allarme. Due giorni su otto mostrano
«niente da dire», che è il caso più importante da disegnare bene.

**Rimisurato dal vivo il 18/09/2026 dopo la terza forma del valore** (`lock → ["jammed"]`), sugli
stessi otto giorni e sulla casa vera: **gli stessi identici numeri**, 0·5·0·10·4·4·8·6 = **37 su
387 voci**, tutte guasti.

E la ragione è onesta, perché senza dirla il numero uguale sembrerebbe dire che la modifica non
serve: **in quegli otto giorni non c'è una sola voce di `lock`**. Le uniche voci dei domini «da
sapere subito» sono **otto `alarm_control_panel disarmed`**, correttamente fuori banda tutti e otto
i giorni (§3, il difetto già trovato). La casa misurata **non ha serrature in cronaca**, ed è la
stessa ragione per cui la spec del 16/09 §12 metteva «il genere per stato (`lock=jammed`)» fuori
perimetro: *«nessun caso in casa (0 serrature)»*. La forma nuova si giudica quindi sul
**ragionamento**, non su questo campione: col solo `si`, `lock/unlocked` sarebbe entrato in banda e
`lock/jammed` no — e questo si legge nei giudizi, non nei giorni.

---

## §5 · Il perimetro di questa fetta

**Dentro:**
- il campo `da_sapere_subito` nel vocabolario dei tipi e nel seme (16 righe);
- la porta di scrittura che lo accetta e lo rifiuta come gli altri campi (`mind/judgments`), con il
  ritorno al seme — **più un rifiuto suo**: `si` su un tipo **senza riposo né lavoro** non si
  scrive, e la ragione dice di scrivere prima `riposo` o `lavoro`. **Solo `si`**: a un elenco di
  stati quel rifiuto non si applica, perché l'elenco dice già cosa conta. È una cortesia che spiega il
  problema a chi scrive, non la garanzia: quella è la regola del §3 («indecidibile vale no»), che
  regge anche sul `si` orfano che la porta non può impedire;
- il campo esposto da `/api/mind/knowledge` insieme agli altri giudizi;
- la riga nel glossario, con l'inglese vuoto;
- le prove, comprese quelle che fissano i sedici tipi del seme e la regola del §3.

**Fuori, dichiarato:**
- **la banda** e tutto ciò che la disegna: è la fetta della pagina;
- **scrivere il valore dalla pagina**: oggi l'editor in riga della sezione 04 corregge solo
  `genere`. Fino alla pagina nuova, il valore di `da_sapere_subito` si scrive **dalla rotta**
  (`POST /api/mind/judgment`). Il **ritorno al seme è già in pagina** per qualunque riga corretta,
  di qualunque campo. È un limite temporaneo e dichiarato, non un difetto;
- **separare `notevole`** nei suoi due sensi: questa fetta ne aggiunge uno nuovo e non tocca quello
  esistente, che resta la parola del riassunto. Va a backlog;
- **separare `lavoro`** nei suoi due sensi — «è successo» per l'allarme, «si sta muovendo» per la
  serratura. La terza forma del valore (§2) fa sì che `da_sapere_subito` **non ci si appoggi** dove
  non deve; non lo cura, e `lavoro` ha un secondo lettore (la ragione italiana che la cronaca
  mostra). Va a backlog accanto a `notevole`, che è la stessa malattia.

---

## §6 · L'impronta, e i giorni da rifare

`da_sapere_subito` **non entra nella cronaca** e **non cambia l'impronta dei giudizi**: la banda si
calcola in lettura (spec della pagina, §3). **Verificato leggendo il codice il 18/09** (corretto di
nuovo durante il Task 4, che ha trovato la citazione precedente gia' scivolata — vedi il backlog,
«Le citazioni per numero di riga marciscono»): l'impronta si costruisce sui soli campi
`CHRONICLE_FIELDS = (genere, riposo)` e dal metodo `chronicle_fingerprint`, entrambi in
`home_space/type_judgments.py`, quindi un campo nuovo non la sposta. Il rilascio di questa fetta
**non fa rifare nessun giorno**, e la verifica dal vivo deve confermarlo: l'impronta dopo il
rilascio resta quella di oggi, `9692e12830c90fd0`.

Se cambiasse, sarebbe il segno che il campo è finito dove non doveva.

---

## §7 · Cosa apre la terza forma del valore

La spec del 16/09 (`2026-09-16-il-giudizio-dei-tipi.md`, §12) mise **«il genere per stato
(`lock=jammed`)»** fuori perimetro con due frasi: *«nessun caso in casa (0 serrature)»* e **«sarà un
campo separato, non un formato dentro `genere`»**.

**Questa fetta apre la strada a quella, e va detto perché è il guadagno vero della scelta del
proprietario.** Quello che mancava non era l'idea: era la **forma**. Un giudizio il cui valore
**nomina degli stati** non era mai esistito in HIRIS — il vocabolario, la porta, la regola, la
pagina e il glossario conoscevano `si`/`no`, liste di stati (`riposo`), mappe stato → frase
(`lavoro`) e mappe di limiti, ma nessun campo che dicesse «questi stati, e solo questi». Ora esiste,
ed è provato da un capo all'altro: il letterale del seme lo scrive, `_parse` lo legge e ne rifiuta
le forme storte, la regola lo consulta per primo, la porta lo accetta senza chiedergli riposo né
lavoro, la pagina lo rende leggibile («solo: jammed»).

**Conferma anche il ruling**: il giudizio per stato è un **campo separato**, non un formato infilato
dentro `genere` — è esattamente com'è nato qui.

**Cosa resta da fare, e non fingiamo che sia già fatto.** «Il genere per stato» ha bisogno di una
**mappa** stato → genere (`{"jammed": "guasto"}`), non di un insieme: la forma qui è più semplice di
quella che servirà. Ciò che si eredita è il percorso — dove si scrive il seme, dove si valida, dove
si decide l'ordine dei rami, come lo si mostra senza tradurre gli stati — e la certezza che il
percorso regge. La mappa la scriverà la sua fetta.
