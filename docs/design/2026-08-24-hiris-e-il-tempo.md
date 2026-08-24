# HIRIS e il tempo

**Data:** 24 agosto 2026 · **Ramo:** `2.0` · **Stato:** disegno approvato dal proprietario, piano da scrivere

Nasce da una domanda che HIRIS non ha saputo reggere: *«dammi lo storico delle ultime 48 ore delle
temperature delle camere»*. La risposta — «non ho accesso ai dati storici» — era **onesta**: non ha
mentito, non poteva davvero rispondere. Il buco però è più largo della domanda che l'ha rivelato.

> **HIRIS conosce la casa solo al presente.** Non gli manca l'accesso allo storico: gli manca
> *qualunque* dimensione temporale.

---

## 0. Cosa chiede il proprietario

Tre risposte, date il 24 agosto, che hanno chiuso tre domande di disegno prima che diventassero
discussioni.

**Quali domande temporali.** *«Se HIRIS è un assistente virtuale deve conoscere tutte le dimensioni
di HA e poi in base al contesto sapere quali informazioni recuperare.»* Non si sceglie una domanda:
si espone la superficie temporale intera e si lascia che sia il contesto a decidere.

**Quanto storico.** *«Quello che HA mette a disposizione. Se chiedo la temperatura della camera da
letto un mese fa alle 14:32 e non sa recuperarla, mi risponde con l'informazione che possiede — per
esempio nella fascia dalle 14 alle 15 la temperatura era di 26,5 gradi.»*

Non è un parametro: è una regola di prodotto. **Dà la grana che ha, e dice qual è.** È la stessa
forma già adottata per la ricerca degradata — *confronta i significati quando può; quando non può,
dà i più recenti, e l'intestazione del blocco dice cosa contiene davvero*.

**Dove vive lo storico.** *«Deve leggere da HA sempre.»* Nessun archivio nostro. Chiuso.

E un vincolo sul metodo, dato insieme alle risposte: *«verifica sempre tutto l'ecosistema della app
per non creare doppioni o sovrapposizioni o informazioni non correlate; riferisciti sempre ai
principi di atomicità, consistenza e conformità.»* Il §2 è la risposta a quella richiesta.

---

## 1. L'analisi — cosa dà Home Assistant, e cosa HIRIS ne prende

Verificato sulla documentazione, non a memoria.

| | **storico dettagliato** | **statistiche a lungo termine** | **logbook** |
|---|---|---|---|
| cosa dà | ogni singolo cambio di stato | min/max/media **orari**; somma per i contatori | cosa è successo e **chi** l'ha causato |
| su quali entità | **qualunque** — luci, porte, sensori | **solo** sensori con `state_class` `measurement`, `total`, `total_increasing` | eventi |
| quanto indietro | `purge_keep_days`, **default 10 giorni** | più del dettaglio — **quanto, non verificato** (§7.3) | come lo storico |
| grana | esatta | oraria, ricalcolata ogni 5 minuti | evento |
| come si legge | `GET /api/history/period/<ts>` | WS `recorder/statistics_during_period` | `GET /api/logbook/<ts>` |
| nel client oggi | **manca** | c'è, **zero chiamanti** | c'è, **zero chiamanti** |

`measurement_angle` esiste come `state_class` ma **non** produce statistiche: è documentato e va
trattato come le entità senza classe.

**La faglia sta esattamente dove cade l'esempio del proprietario.** A un mese, il dettaglio non
esiste più; la fascia oraria sì. La frase che ha scritto lui — «nella fascia dalle 14 alle 15 la
temperatura era di 26,5 gradi» — **è** il comportamento corretto, non un ripiego.

**Cosa HIRIS ha già, e non sapeva di avere.** `state_class` è nella proiezione della cache
(`proxy/entity_cache.py`) da poco, con un commento che dice perché: *«è ciò che dice a quali entità
si può chiedere una statistica, senza doverlo domandare al recorder»*. Il mattone è posato.

**Cosa butta via.** `last_changed` arriva a ogni cambio di stato e la proiezione lo scarta. Oggi
HIRIS sa che in camera ci sono 22,4 °C e **non sa da quando**: non può nemmeno dire «quel valore è
fermo da tre ore».

**Perché il buco esiste.** Lo storico locale c'era — `HistoryStore`/`HistoryCapture`, `history.db`
— ed è uscito con la fetta «esce il documentale», per una ragione scritta e giusta: scriveva e
nessuno leggeva. Nessuno ha poi cablato quello di Home Assistant. Il reperto n.6 del rapporto sullo
scostamento (16 agosto) lo registra: *«`get_logbook`, `get_statistics`, `render_template` esistono
nel client e hanno zero chiamanti di produzione»*.

---

## 2. L'ecosistema — le sovrapposizioni, cercate prima di disegnare

### 2.1 Cosa ha già una dimensione temporale

**Vivo:** la **cronaca** (`azioni.db`), ogni atto di HIRIS con `quando_ts` e conservazione 90
giorni · le **promesse**, che portano una `istantanea` del momento in cui sono nate · i **consumi**,
un secchiello al giorno per provider e modello · i timestamp di lettura dell'anagrafe.

**Morto, e da non far tornare:** `history.db`, `portrait.db`, `knowledge.db`. Non sono solo
assenti: l'avvio li tratta come **residui da rimuovere**. Ricostruire un archivio storico nostro
non sarebbe una scelta nuova, sarebbe dissotterrare qualcosa che il prodotto ha già seppellito.
La decisione del proprietario lo esclude in partenza, e questo paragrafo esiste perché resti
escluso anche fra sei mesi.

### 2.2 Le tre sovrapposizioni

**① «Perché si è accesa la luce» ha due case possibili, e non sono un doppione.** Se l'ha accesa
un'automazione, la risposta è nel logbook. Se l'ha accesa **HIRIS**, la risposta è nella cronaca —
e il logbook direbbe soltanto «servizio chiamato», senza sapere che dietro c'era una frase in chat.
Sono **due fatti diversi**: *cosa è successo in casa* e *cosa ha fatto HIRIS*. Restano due case
(fondamenta 2), e si **uniscono al momento della lettura**.

**② «Cos'è cambiato» oggi non ha nessuna casa** — ce l'aveva, il *ritratto* teneva «cosa è
cambiato», ed è uscito. Il rischio è ricostruirlo per sbaglio: se per rispondere servisse una
fotografia salvata, avremmo reinventato `portrait.db`. **Non serve**: il confronto si deriva dalle
stesse superfici al momento della domanda.

**③ `last_changed` contro `quando_ts`.** Il primo dice quando è cambiata *la casa*; il secondo
quando ha agito *HIRIS*. «È accesa da due ore» e «l'ho accesa io due ore fa» hanno fonti e
certezze diverse, e non vanno mai fuse in una frase sola.

### 2.3 Il buco adiacente, che entra nella fetta

La cronaca ha `registra`, `registra_costruzione` e `leggi(id)`. **Nient'altro.** Non si può
chiedere «cosa hai fatto ieri», non c'è modo di filtrare per entità, e **nessuno strumento la
espone al modello**: si legge solo per identificatore, da una pagina. È scritta e muta —
fondamenta 4.

**Decisione del proprietario: entra.** Senza, alla domanda «perché si è accesa» HIRIS
risponderebbe «un'automazione o qualcuno» **anche quando è stato lui**, e il dato per rispondere
meglio ce l'ha in tabella.

---

## 3. Il fondamento

### 3.1 La scelta della superficie è del codice, non del modello

Scegliere fra dettaglio e statistiche **non è una questione di intenzione**: è una conseguenza
meccanica di quanto indietro si è chiesto e di che tipo è l'entità. Chiederlo al modello
significherebbe pretendere che conosca la politica di conservazione del recorder di *questa* casa.
Non può, e sbaglierebbe in silenzio.

Ciò che invece è una differenza di intenzione — *«quanto era caldo»* contro *«chi l'ha acceso»* —
resta al modello, ed è la ragione per cui gli strumenti sono due e non uno.

### 3.2 Dichiarare la grana

Ogni risposta porta con sé ciò che serve a interpretarla da sola (fondamenta 1): i valori, **l'unità
di misura**, **la grana davvero usata**, **la finestra davvero coperta**, e il motivo se ha
degradato. Una media oraria presentata come una misura è una frase vera che significa una cosa
falsa.

### 3.3 Quattro esiti, mai confusi

- *«in quella finestra il valore non è mai cambiato»*
- *«oltre dieci giorni di quell'entità non resta nulla: non è un sensore con statistiche»*
- *«non ho registrazioni per quell'entità — potrebbe essere esclusa dalla registrazione»*
  (Home Assistant permette di escludere entità dal recorder; per quelle lo storico è vuoto **per
  sempre**, e non lo sappiamo con certezza — quindi si dice così, non si afferma)
- *«Home Assistant non ha risposto»*

Un elenco vuoto che li rappresenta tutti e quattro è una frase falsa detta con sicurezza.

### 3.4 Il fuso è quello della casa

«Le ultime 48 ore» e «ieri alle 14» si risolvono nel fuso **della casa** — `Europe/Rome`, che
l'anagrafe adesso legge — mentre le statistiche tornano in UTC. La fetta dello schedulatore ha già
pagato un difetto di orologi diversi: la finestra si calcola nel fuso della casa, e le ore si
dicono in quello.

### 3.5 Il volume ha un tetto, e il tetto si dichiara

Una settimana di storico dettagliato su un sensore chiacchierone sono migliaia di punti.
Rovesciarli nel contesto del modello è la stessa famiglia di difetto dell'esaurimento di iterazioni
già pagato. Per le entità con statistiche il problema non si pone — sopra la soglia si passa alle
fasce orarie (§4.1) — ma **per le altre il dettaglio è l'unica fonte che esiste**: lì `andamento`
riassume di suo, e lo dichiara: *«4.127 cambi, riassunti in fasce orarie»*.
È la regola del §3.2 applicata per un motivo diverso — non la conservazione, la leggibilità.

---

## 4. I due strumenti

I nomi non sono `cronologia`: sarebbe a un passo da `cronaca`, e due parole simili per due cose
diverse sono un difetto che si paga sei mesi dopo.

### 4.1 `andamento` — un valore nel tempo

Riceve un riferimento e una finestra. La scelta della superficie è **deterministica**, e dipende
da due sole cose: quanto è lunga la finestra e se l'entità ha `state_class`.

| | **finestra ≤ soglia di grana** | **finestra > soglia** |
|---|---|---|
| **con** `state_class` | dettaglio — i cambi veri | **statistiche**, fasce orarie |
| **senza** `state_class` | dettaglio | dettaglio, riassunto se voluminoso (§3.5) |

Sopra la finestra si applica il taglio della conservazione: la parte oltre `purge_keep_days` non
esiste nel dettaglio. Se ne resta una porzione, si dà quella e si dichiara la finestra davvero
coperta; se non ne resta niente e l'entità non ha statistiche, risponde col secondo esito del §3.3.

**La soglia di grana è una costante con un nome, in `tempo.py`, e vale 24 ore.** Il numero è una
scelta, non una misura, e va detto: sotto la giornata «l'andamento» significa i cambi veri; sopra,
migliaia di punti sono illeggibili sia per il modello sia per chi legge la risposta, e le fasce
orarie che Home Assistant ha già calcolato sono migliori di un riassunto fatto da noi — oltre a
costare una chiamata invece di una chiamata più un riassunto.

**Conseguenza da guardare in faccia:** la domanda da cui questa fetta nasce — *le temperature delle
camere nelle ultime 48 ore* — cade **sopra** la soglia, e riceve fasce orarie, non i cambi. È la
risposta giusta (48 ore di cambi di quattro sensori non sono leggibili), è dichiarata, ed è
esattamente la forma descritta dal proprietario per l'esempio del mese fa. La verifica live §7.4
esiste per guardarla con i suoi occhi: se la volesse più fine, si alza la soglia — una costante.

La risposta porta valori, unità, grana, finestra coperta, ed eventuale motivo della degradazione.

### 4.2 `accaduto` — cosa è successo, e per mano di chi

Legge il logbook. Dove un atto è di HIRIS, **unisce al momento della lettura** la riga di cronaca
corrispondente.

L'archivio non duplica niente — si collega per identificatore (fondamenta 2) — ma la risposta è
intera: restituire un `esecuzione_id` che il modello non può risolvere rispetterebbe la lettera
della fondamenta 2 violando la 4.

Tre risposte oneste e distinte diventano possibili: *«l'ha accesa l'automazione X»* · *«l'ho accesa
io alle 18:04, me l'avevi chiesto in chat»* · *«l'ha accesa qualcuno, e non so chi: il logbook dice
solo che il servizio è stato chiamato»*.

### 4.3 Il quarto pezzo, che non è uno strumento

`last_changed` arriva già e viene buttato. *«Da quanto è accesa?»* costa **un campo e zero
chiamate** a Home Assistant: è il guadagno più economico della fetta.

**Dove deve comparire.** La fondamenta 3 vincola le **porte che restituiscono dati** — `guarda`,
`cerca`, `legami`: se il campo esce da una e non dall'altra è un difetto anche quando nessuna delle
due è sbagliata. Il **nucleo** è un'altra cosa: è prosa con un tetto di token, e omette molto per
costruzione. Un timestamp per ogni entità notevole è testo pagato a ogni turno, e resta fuori.

---

## 5. Dove vive il codice

```
casa/tempo.py        · NUOVO — sceglie la superficie e da' forma alla risposta.
                       Non archivia niente. La scelta e' pura: si prova senza rete.
proxy/ha_client.py   · lo storico dettagliato: primitiva NUOVA (fu tolta come orfana)
                       `get_statistics` e `get_logbook`: primo chiamante di produzione
azione/cronaca.py    · `elenca(da, a, entita)` accanto a `leggi(id)`
proxy/entity_cache.py· `last_changed` smette di essere buttato
casa/strumenti.py    · `andamento` e `accaduto`: il catalogo passa da 11 a 13
```

**Il commento che racconta la rimozione di `get_history` va corretto**: descriverebbe un fatto non
più vero. Filtrare la cronaca per entità richiede una scelta: oggi le entità vivono dentro
`entita_json`.

---

## 6. Le decisioni prese

**Il turno di una promessa li riceve.** `SOLA_LETTURA` ammette oggi `cerca`, `guarda`, `legami`,
`richiama`. `andamento` e `accaduto` **leggono e basta**: escluderli sarebbe la scelta opposta a
quella presa per `costruisci`, e per la ragione opposta. Una promessa che alle 17:00 confronta le
temperature con un'ora prima oggi deve portarsi dietro una fotografia scattata alla nascita; con
`andamento` può leggere.

**L'`istantanea` resta, ed è un doppione apparente — dichiarato.** Esiste *perché* non c'era uno
storico. Sono però due fatti diversi: l'istantanea è **ciò che HIRIS ha visto** alla nascita della
promessa, verbatim, e resta vera anche dopo che il recorder ha potato; `andamento` è **ciò che Home
Assistant ha registrato**. Qualcuno vorrà unificarle: questo paragrafo esiste perché la discussione
avvenga sui fatti.

**Il catalogo cresce, e con esso la caccia.** Undici strumenti diventano tredici. Ogni punto che dà
il catalogo per fisso va ricercato **col grep e non a memoria** — è la trappola che ha rotto il
prodotto nella 3.10.1 — e questa volta cercando anche la forma «strumenti sono *numero*», che
all'ultimo giro è sfuggita per l'ordine delle parole.

---

## 7. Le verifiche che nessun banco può dare

1. **La forma vera di `recorder/statistics_during_period`.** `get_statistics` **non ha mai girato
   in produzione**: la forma della risposta nei test è scritta a mano, cioè immaginaria. È la stessa
   trappola della fetta «comandare», dove la forma di `/api/services` era immaginaria e la spec
   disse «fermati se cade». **Si legge dalla casa vera prima di appoggiarci un ragionamento.**
2. **La forma vera del logbook**, per la stessa ragione — **compresi i campi `context_*`**
   (`context_entity_id`, `context_user_id`, ...), oggi scartati da `ha_client.diario`. È da lì che
   passa la paternità di un'automazione o di una persona quando la si potrà consegnare: la
   descrizione di `accaduto` promette oggi solo ciò che il codice consegna (revisione finale, F5) —
   HIRIS riconosce i propri atti, per il resto riporta il messaggio del diario così com'è — perché
   quella forma non è mai stata misurata. Aggiungere quei campi indovinandone la forma non
   manterrebbe comunque la promessa.
3. **I due confini su questa casa.** `purge_keep_days` è configurabile, e il default vale finché
   nessuno l'ha cambiato. E soprattutto: **quanto indietro arrivano davvero le statistiche.** Che
   sopravvivano alla potatura del dettaglio è certo — è il motivo per cui esistono — ma «per
   sempre» è una cosa che si dice spesso e che la documentazione del recorder non afferma. La
   §4.1 ci si appoggia: se il confine reale fosse più corto, l'esempio del proprietario (un mese
   fa alle 14:32) cadrebbe, e la degradazione dovrebbe dichiarare un terzo esito invece di un
   valore. **Si misura, non si assume.**
4. **Una domanda vera in chat**: le temperature delle camere nelle ultime 48 ore — la domanda da cui
   la fetta nasce — e una oltre il confine, per vedere la degradazione dichiarata.
5. **«Perché si è accesa»** su qualcosa che ha acceso HIRIS, per vedere l'unione con la cronaca.

---

## 8. Fuori scope, dichiarato

- **Nessun archivio storico nostro** (§2.1).
- **Cruscotto energia e analisi dei costi**: le statistiche `total_increasing` li abiliterebbero, e
  sono un'altra fetta.
- **`render_template`**: resta orfano per motivi suoi.
- **Autonomia**: HIRIS non decide di guardare indietro da solo.
- **Far sapere al modello quali entità hanno uno storico prima di chiederlo.** `state_class` è nella
  cache e potrebbe arrivare a `cerca` — sembra parte di questa fetta e non lo è: è la differenza fra
  rispondere bene a una domanda e cambiare ciò che l'utente sa di poter chiedere.

## 9. Pulizia — perché ogni fetta è anche pulizia

- Il commento sulla rimozione di `get_history` in `proxy/ha_client.py` diventa falso e va riscritto.
- Il reperto n.6 di `docs/design/2026-08-16-cosa-hiris-sa-di-home-assistant.md` viene chiuso da
  questa fetta: la riga va annotata, non lasciata a descrivere un buco che non c'è più.
- Il piano include la ricognizione con `scripts/censimento.py`: la fetta aggiunge un modulo, due
  strumenti e una primitiva, e ciò che lascia orfano non sta dentro il proprio diff.
- La review finale è **dell'intero ramo**, non del diff.
