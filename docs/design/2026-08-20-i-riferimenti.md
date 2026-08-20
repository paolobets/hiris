# I riferimenti — la casa che si lascia trovare

> Fetta di riparazione, nata da un incidente vero (2026-08-20): «verifica le temperature
> per ogni stanza, ricontrolla fra un'ora e notificami il delta» — il turno è morto
> esaurendo le iterazioni, senza né temperature né promessa.
> Tre audit indipendenti (contesto vs strumenti · percorsi misurati · errori che non
> insegnano) hanno mappato la famiglia intera. Misurata con le **quattro fondamenta**.

## 0. La diagnosi, in una frase

Non era un guasto solo: era la **somma di tre fatti** — gli id assenti dal contesto,
`guarda` senza batch, un tetto che conta i round-trip senza che nessun prompt insegni
le chiamate parallele — più un bug vero trovato per strada. Otto stanze richiedono
esattamente 10 round-trip minimi contro un tetto di 10, **senza il giro finale per
scrivere la risposta**: la richiesta muore anche a esecuzione perfetta.

## 1. I reperti (tutti misurati, non dedotti)

### R1 — Il contesto mostra nomi, gli strumenti pretendono id
L'albero della casa (`casa/nucleo.py::_righe_casa`) rende le **aree** col solo nome
(`_nome_area_visualizzato`, id solo per le pseudo-aree); i **piani** col solo nome,
sempre; le **automazioni/script** («Cosa la casa fa già da sola», `_righe_comportamento`)
col solo nome. Ogni strumento pretende l'id esatto e vieta di indovinarlo.
I **ricordi** sono il controesempio virtuoso: escono già come `[#id] nome`.

### R2 — Tre vicoli ciechi assoluti
Nessuna sequenza di chiamate, di nessuna lunghezza, produce mai questi riferimenti:
- **piani**: `cerca` non li indicizza (`memoria/riconoscitore.py`, tupla `_ARCHIVI`);
  `esegui(piani=…)` è promesso dal prompt (`claude_runner.py:264-266`) e inesercitabile;
- **automazioni/script**: nominati nel nucleo, `guarda` vuole il loro id, `cerca` non
  li indicizza;
- **etichette**: il `label_id` non esce da NESSUNA porta — `guarda` le mostra col nome
  per scelta deliberata (`domande.py:319-320`) — eppure `esegui(etichette=…)` lo pretende.

### R3 — L'aritmetica del tetto
`MAX_TOOL_ITERATIONS = 10` (`claude_runner.py:348`, fisso; nell'altro runner via env,
e su Ollama **5**). Il ciclo conta i **round-trip**, e l'ultimo serve al modello per
scrivere la risposta: per N cose da guardare una a una servono N+2 giri. A N=8 fa 10:
zero margine. Il codice **già processa** più tool_use nella stessa risposta in un solo
giro — ma nessun prompt lo insegna. Il turno della promessa condivide lo stesso tetto:
un `chiedi` su 8 sensori muore `fallita`, senza notifica, in silenzio.

### R4 — L'esaurimento è muto e in inglese
Al tetto: `return "Max tool iterations reached."` (`claude_runner.py:981`,
`openai_compat_runner.py:875`) — inglese, hardcoded, **zero log**. Nel percorso
streaming è peggio: il generatore esce senza evento d'errore né testo
(`openai_compat_runner.py:978-1157`) — un «done» vuoto. Il caso gemello (taglio per
token) ha già il suo messaggio italiano fatto bene (`_TRUNCATION_NOTICE`). Difetto
documentato nell'analisi funzionale del 3 agosto, mai chiuso.

### R5 — Gli errori non insegnano
`guarda` con un nome al posto dell'id risponde `{"esiste": false}` **nudo**
(`domande.py:347-348, 403-404, 451`): indistinguibile da «non esiste davvero», nessun
invito a `cerca`. È il meccanismo diretto dell'incidente. `ricorda` con un'ancora
sbagliata la scarta dentro `problemi` ma risponde `salvato: true`. Il pattern giusto
**esiste già** in `esegui` (`azione/verifica.py:430-432`: «Usa "cerca"… e ripeti il
comando»): va esteso, non inventato.

### R6 — BUG: l'unità dell'istantanea è sempre None in produzione
`casa/strumenti.py::_istantanea` (righe 1309-1311) legge
`attributi.get("unit_of_measurement")` — ma la cache vera (`proxy/entity_cache.py::
_to_minimal`, riga 100) mette l'unità nella chiave **`unit` di primo livello**, e in
`attributes` solo gli extra di dominio. Quindi ogni istantanea di un `chiedi` nasce
**senza unità**: il `72` senza scala, la fondamenta ① violata nel percorso costruito
per proteggerla. Il test di guardia passa perché il suo doppio `_CacheFinta` riproduce
la forma HA **grezza** invece di quella minimale vera: è il **decimo test che non può
fallire** di questo progetto.

### R7 — `prometti` accetta riferimenti inesistenti
Un `da_confrontare` con un nome sbagliato **non viene rifiutato**: la promessa nasce
con `valore: null` e la nota «non esisteva quando l'hai chiesto». Il danno è differito
a quando nessuno può più correggere. Viola «il modello propone, il codice restringe»,
già deciso due volte dal proprietario (registro assente, recapito).

### R8 — Nessuna guida al batch, nessun log del girare in tondo
Il prompt non dice mai «più nomi in UNA chiamata `cerca`» (la capacità c'è:
`Indice.trova` risolve tutti i frammenti di una frase — misurato: 8 su 8 in una
chiamata). E un turno che brucia iterazioni su rifiuti identici **non lascia traccia
nei log**: l'unico warning scatta sulle eccezioni, mai sui rifiuti.

### R9 — Un secondo vocabolario a mano
`nucleo.py::_STATI_ATTIVI/_DOMINI_EVENTO/_CLASSI_EVENTO` (righe 158-190) è una lista
di tipologie mantenuta a mano **senza** il test che la pinna alla fonte HA — lo stesso
rischio già pagato con `carbon_monoxide`/`co`, mentre `_SIGNIFICATO_CLASSE` in
anagrafe è già pinnata.

## 2. Le decisioni prese (proprietario, 2026-08-20)

- **Il tetto**: si insegna il parallelismo nel prompt **e** `MAX_TOOL_ITERATIONS`
  sale a **50** (chat e promessa, entrambi i runner; il rapporto Ollama resta
  proporzionato). Il messaggio di esaurimento resta necessario — più raro, non inutile.
- «Notevole adesso» **resta coi nomi**: 15 id a ogni turno costano più di quel che
  rendono; il batch di `cerca` li copre.
- Le etichette si risolvono facendo uscire il `label_id` **come dato accessorio**
  da `cerca`/`guarda` — non stampandolo nel nucleo (la scelta di leggibilità di
  `domande.py` resta).

## 3. Gli interventi — due lotti

### Lotto 1 — ciò che è rotto oggi
1. **R6** — `_istantanea` legge `unit` dalla forma minimale vera; `_CacheFinta`
   corretta perché riproduca `_to_minimal` (e la mutazione che prima passava ora
   deve fallire).
2. **R7** — `prometti` rifiuta un `da_confrontare` che lo specchio non conosce,
   col motivo che insegna («usa "cerca"…»). Un `chiedi` senza `da_confrontare`
   resta legittimo.
3. **R5** — i rifiuti di `guarda` (3 punti) e `ricorda` (ancora scartata) adottano
   il pattern di `esegui`: cosa non esiste + come trovarlo. `ricorda` continua a
   salvare (il testo è la verità) ma il campo `problemi` insegna.
4. **R1** — l'id accanto al nome nell'albero: **aree**, **piani**,
   **automazioni/script**, con UNA forma sola — `Nome (id: X)`, la convenzione che le
   pseudo-aree usavano gia'. I ricordi restano `[#id]`: id numerici interni di HIRIS,
   non slug di Home Assistant (deciso in implementazione, T4). Costo misurato:
   +1104 caratteri su un nucleo da 20 aree/40 automazioni.
5. **R3+R8** — nel prompt (`BASE_REGOLE_STRUMENTI` e `_GUIDA_CON_STRUMENTI`):
   «più nomi → UNA chiamata `cerca`» e «più letture indipendenti → chiamale in
   parallelo nella stessa risposta». Tetto a 50.
6. **R4** — messaggio di esaurimento in italiano sul modello di `_TRUNCATION_NOTICE`
   (dice cosa è successo e consiglia di spezzare la richiesta), `logger.warning`
   con il conto delle iterazioni, e nello stream un evento che dichiara il taglio
   invece del «done» muto.

### Lotto 2 — i vicoli ciechi strutturali
7. **R2** — `cerca` impara piani, automazioni e script (nuovi tipi nell'indice del
   riconoscitore, stessi campi dei candidati attuali).
8. **R2** — il `label_id` esce come dato accessorio dalle etichette in `cerca`/`guarda`.
9. **R9** — il vocabolario di `nucleo.py` pinnato con un test contro la fonte HA,
   come `_SIGNIFICATO_CLASSE`.

## 4. Come si prova

La regola resta: **la finta deve saper produrre il difetto**, mutazione eseguita.
In particolare:
- il test dell'unità usa un doppio che riproduce `_to_minimal` **vero** (il difetto
  R6 deve poter rinascere e venire colto);
- il conteggio dei round-trip: un test che monti il runner con un dispatcher finto
  e verifichi che N chiamate parallele nella stessa risposta consumano UNA iterazione;
- l'esaurimento: il messaggio italiano compare, il warning è nei log, lo stream
  emette l'evento;
- i nuovi tipi di `cerca`: un piano/automazione si risolve per nome e il candidato
  porta l'id vero;
- verifica live (spec §13.1 dello Schedulatore, riusata): la richiesta incidente
  («temperature per stanza + delta fra un'ora») deve completarsi sulla casa vera.

## 5. Fuori da questa fetta
- id nel «Notevole adesso» (deciso: no).
- Qualunque nuovo strumento di batch per `guarda`: prima si misura quanto rende il
  parallelismo insegnato; se non basta, sarà una fetta sua con la sua spec.
- La sanificazione (`_sanitize` scollegato): debito noto, fuori perimetro.
