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

**Campo:** `da_sapere_subito`. Valori: `si` / `no`, con l'assenza che vale `no`.
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
2. il suo tipo ha `da_sapere_subito: si` **e** il suo stato è un **lavoro** per quel tipo
   (`working_of`); se quel tipo non ha nessun giudizio `lavoro`, vale lo stato che **non è riposo e
   non è una forma dell'assenza**.

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

---

## §5 · Il perimetro di questa fetta

**Dentro:**
- il campo `da_sapere_subito` nel vocabolario dei tipi e nel seme (16 righe);
- la porta di scrittura che lo accetta e lo rifiuta come gli altri campi (`mind/judgments`), con il
  ritorno al seme;
- il campo esposto da `/api/mind/knowledge` insieme agli altri giudizi;
- la riga nel glossario, con l'inglese vuoto;
- le prove, comprese quelle che fissano i sedici tipi del seme e la regola del §3.

**Fuori, dichiarato:**
- **la banda** e tutto ciò che la disegna: è la fetta della pagina;
- **correggere il campo dalla pagina**: oggi la sezione 04 corregge solo `genere`. Fino alla pagina
  nuova, `da_sapere_subito` si corregge **dalla rotta** (`POST /api/mind/judgment`). È un limite
  temporaneo e dichiarato, non un difetto;
- **separare `notevole`** nei suoi due sensi: questa fetta ne aggiunge uno nuovo e non tocca quello
  esistente, che resta la parola del riassunto. Va a backlog.

---

## §6 · L'impronta, e i giorni da rifare

`da_sapere_subito` **non entra nella cronaca** e **non cambia l'impronta dei giudizi**: la banda si
calcola in lettura (spec della pagina, §3). **Verificato leggendo il codice il 18/09**: l'impronta
si costruisce sui soli campi `CHRONICLE_FIELDS = (genere, riposo)`
(`home_space/type_judgments.py:26` e `chronicle_fingerprint`, `:196`), quindi un campo nuovo non la
sposta. Il rilascio di questa fetta **non fa rifare nessun giorno**, e la verifica dal vivo deve
confermarlo: l'impronta dopo il rilascio resta quella di oggi, `9692e12830c90fd0`.

Se cambiasse, sarebbe il segno che il campo è finito dove non doveva.
