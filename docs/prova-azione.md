# La prova sulla casa vera

*Foglio scritto il 12 agosto 2026 per la **2.2.0**, la versione in cui HIRIS smette di
sapere soltanto e comincia a fare. Si esegue in mezz'ora, su un impianto Home Assistant
vero, e serve a decidere se questa versione è pubblicabile.*

---

## Perché questo foglio esiste

Le prove automatiche di HIRIS sono verdi. Non provano niente di ciò che conta qui.

Questa versione poggia su una promessa — **«verificare, non insegnare»**: HIRIS non ha
un catalogo di cose possibili scritto da noi, chiede a Home Assistant cosa sa fare *in
questa casa* e verifica ogni chiamata contro quella risposta. Una promessa del genere si
prova solo dove c'è una casa: nelle prove automatiche la risposta di Home Assistant è
una finta, e una finta conferma sempre chi l'ha scritta.

**C'è una cosa che nessuno ha mai misurato**, e va detta prima di tutto il resto: la
**forma** della risposta di `/api/services`. Il codice che la legge è stato scritto su
una forma *attesa* — una lista di `{"domain": ..., "services": {...}}` — e non su una
forma *osservata*. Nessuno dei passi che hanno costruito questa versione ha toccato un
impianto reale (un tentativo su `192.168.1.95:8123` si è fermato su un `401`). Se quella
forma è diversa da come la immaginiamo, **non è una prova che fallisce: è tutta la
versione da rileggere**. Per questo è la prova numero 1, e va fatta prima delle altre
sette.

---

## Cosa serve, prima di cominciare

1. **Un Home Assistant vero** con l'add-on HIRIS 2.2.0 installato e avviato, e la chat
   che risponde (una delle strade del §2 di `prova-la-2.0.md`).
2. **Il log dell'add-on aperto**: Impostazioni → Add-on → HIRIS → scheda **Log**. È lì
   che si vede la verità, e le prove qui sotto citano le righe esatte da cercare. Il
   livello `info` (quello di default) basta: non serve `debug`.
3. **Un token di lunga durata** di Home Assistant, per la sola prova 1 (profilo utente →
   in fondo → «Token di accesso a lunga durata»).
4. **Tre entità sacrificabili**: una luce, una presa e — se ce l'hai — una tapparella.
   Quello che tocchiamo qui succede davvero.

**Dove si guarda l'esito.** Tre posti, e vanno usati tutti e tre:

- **la chat**: cosa HIRIS *dice*;
- **le targhette sotto la risposta**: se ha chiamato `esegui` e con quali argomenti —
  cioè cosa ha *fatto*, che è un'altra cosa da quello che dice;
- **il log**: la riga `azione eseguita ...` o `azione rifiutata ...`, che è l'unico
  posto in cui compare il motivo esatto del rifiuto, parola per parola.

Se chat e log si contraddicono, **vale il log** — e quella contraddizione è la
segnalazione più importante che questo foglio possa produrre.

---

## Prova 1 — La forma di `/api/services` (**questa prima delle altre**)

**Cosa fare.** Da un terminale sulla stessa rete:

```bash
curl -s -H "Authorization: Bearer IL_TUO_TOKEN" \
  http://IL_TUO_HA:8123/api/services | head -c 600
```

**Cosa deve succedere.** Una **lista** JSON, e ogni voce un oggetto con esattamente
queste due chiavi in cima:

```json
[{"domain": "homeassistant", "services": {"turn_off": {}, "turn_on": {}}}]
```

Cioè: `domain` è una **stringa**, `services` è un **oggetto** i cui nomi sono i servizi
di quel dominio. Se dentro il dettaglio di un servizio c'è una chiave `fields` con i
parametri, la prova 5 funzionerà; se non c'è, leggi la nota alla prova 5.

Poi, in HIRIS, chiedi in chat una qualunque azione (basta *«spegni la luce della
cucina»*) e cerca nel log:

```
registro servizi: 42 domini, 517 servizi
```

I numeri saranno i tuoi, ma **devono essere entrambi diversi da zero e plausibili** per
la tua casa. Il registro si carica pigramente, al primo tentativo di azione: prima di
quella frase in chat quella riga nel log non c'è, e non è un guasto.

**Come si riconosce il fallimento.** Tre modi, in ordine di gravità:

- **`registro servizi: 0 domini, 0 servizi`** con un `/api/services` che invece ha
  risposto pieno. È **il** fallimento: la forma è diversa da quella attesa, il lettore
  salta ogni voce invece di lamentarsi, e HIRIS rifiuterà ogni azione dicendo *«non so
  ancora cosa Home Assistant sa fare»*. **Fermati qui**: le prove da 2 a 8 non hanno più
  niente da dire, e va riletto il lettore del registro (`hiris/app/azione/registro.py`)
  con la forma vera in mano. Allega l'output del `curl`.
- **In chat compare «non riesco a leggere cosa Home Assistant sa fare (...)»** con un
  nome di errore fra parentesi: la lettura non è nemmeno partita (rete, token, HA non
  ancora pronto). Diverso dal caso sopra e meno grave: è un guasto di collegamento, non
  di forma.
- **La risposta del `curl` non è una lista** (per esempio è un oggetto `{"light": {}}`).
  Stesso esito del primo caso, ma qui lo sai prima ancora di aprire HIRIS.

---

## Prova 2 — Un comando che funziona

**Cosa fare.** Con una luce **accesa**, in chat: *«spegni la luce della cucina»*
(il nome vero della tua).

**Cosa deve succedere.** La luce si spegne davvero. HIRIS risponde dicendo che l'ha
spenta. Nel log:

```
azione eseguita [origine=chat] light.turn_off su ['light.cucina'] -- cambiati: ['light.cucina']
```

Nota che HIRIS non ti ha chiesto l'`entity_id`: gli hai dato un nome, e lui ha cercato
prima. Le targhette sotto la risposta lo mostrano — di solito un `cerca` seguito da un
`esegui`.

**Come si riconosce il fallimento.**

- La luce si spegne ma la riga di log dice `cambiati: nessuno`, oppure HIRIS aggiunge
  l'avviso «nessuno stato e' cambiato» quando invece è cambiato: la rilettura non vede
  ciò che è successo.
- HIRIS dichiara di aver spento e **la luce resta accesa**, senza nessun avviso. È il
  difetto peggiore possibile di questa versione: dire cosa è stato chiesto invece di cosa
  è successo.
- Nessuna targhetta `esegui` e una risposta del tipo «non posso agire»: lo strumento non
  è arrivato al modello. Salta alla prova 8, che è la stessa cosa vista sull'altro
  percorso.

---

## Prova 3 — Un servizio che non esiste

**Cosa fare.** In chat: *«chiama il servizio `light.fai_il_caffe` sulla luce della
cucina»* — un servizio inventato, in un dominio che esiste.

**Cosa deve succedere.** Non succede niente in casa, e nel log compare:

```
azione rifiutata [origine=chat]: «light.fai_il_caffe» non esiste. I servizi di «light» sono: toggle, turn_off, turn_on, ...
```

**Il rifiuto porta l'elenco di quelli veri**: è ciò che permette al modello di
correggersi da solo, e infatti può darsi che nella stessa risposta HIRIS ti dica «quel
servizio non esiste, quelli disponibili sono...» oppure che riprovi con quello giusto.
Entrambi gli esiti vanno bene; quello che deve esserci è la riga di log.

**Come si riconosce il fallimento.** Un rifiuto **muto** («non posso», «si è verificato
un errore») senza l'elenco dei servizi veri. Oppure — molto peggio — nessun rifiuto: una
chiamata partita verso Home Assistant per un servizio inesistente significa che la
verifica non è sul percorso.

---

## Prova 4 — Il dominio incrociato

**Cosa fare.** In chat: *«spegni la presa del salotto usando `light.turn_off`»* — un
servizio di `light` su un'entità `switch.*`.

**Cosa deve succedere.** Rifiuto, **con il motivo esatto**:

```
azione rifiutata [origine=chat]: «light.turn_off» non si applica a «switch.presa_salotto», che e' del dominio «switch».
```

**Come si riconosce il fallimento.** La chiamata parte lo stesso (e Home Assistant la
ignora in silenzio: è il caso peggiore, perché HIRIS potrebbe raccontarti un successo che
non c'è stato), oppure il rifiuto non nomina il dominio vero dell'entità.

**Attenzione a un falso allarme**: `homeassistant.turn_off` sulla stessa presa **deve
funzionare** — quel dominio è universale apposta. Se anche quello viene rifiutato, non è
questa prova che fallisce: leggi la nota su `_DOMINI_UNIVERSALI` in fondo.

---

## Prova 5 — Un parametro inventato

**Cosa fare.** In chat: *«spegni la luce della cucina con `brightness_pct` 50»* —
`turn_off` non ha la luminosità. In alternativa, qualunque parametro palesemente
inventato (`colore_del_mercoledi`).

**Cosa deve succedere.** Rifiuto che **elenca i parametri veri** di quel servizio:

```
azione rifiutata [origine=chat]: «brightness_pct» non e' un parametro di «light.turn_off». Quelli veri sono: flash, transition.
```

Se il servizio non accetta nessun parametro, il rifiuto lo dice in quel modo: *«non
accetta parametri, e ne hai passato ...»*.

**Come si riconosce il fallimento.**

- Il parametro **passa** e la chiamata parte: la verifica dei parametri non funziona.
- Il rifiuto dice *«non accetta parametri»* per un servizio che invece ne ha (per esempio
  `light.turn_on`, che ha almeno `brightness_pct`). È il segnale che il dettaglio dei
  servizi arriva **senza** la chiave `fields`, o con quei parametri in un posto diverso:
  torna alla prova 1, guarda nell'output del `curl` la voce di `light.turn_on` e
  segnalala. È lo stesso rischio della prova 1 — una forma assunta e non misurata — in
  una sua piega più profonda.

---

## Prova 6 — Una cosa che si muove lentamente

**Cosa fare.** Con una tapparella ferma, in chat: *«apri la tapparella della camera»*.

**Cosa deve succedere.** La tapparella **comincia a muoversi**, e HIRIS aggiunge
l'avviso che la chiamata e' riuscita **ma nessuno stato e' cambiato**.

**Quell'avviso, qui, è corretto.** HIRIS rilegge lo stato pochi millisecondi dopo aver
chiamato, e in quel momento la tapparella era ancora dov'era. Non aspetta apposta:
un'attesa arbitraria trasformerebbe un fatto in un'ipotesi.

**Come si riconosce il fallimento.** Nessun fallimento tecnico, ma **due cose da
annotare**, perché è a questo che serve la prova:

- **quanto è fastidiosa** quella frase in una casa vera. Se ogni tapparella e ogni valvola
  termostatica produce un avviso che sembra un errore, l'avviso è un difetto d'uso anche
  se dice il vero;
- **come la racconta HIRIS**. Deve dirti che il comando è partito e che nell'immediato non
  era ancora cambiato niente — non «non è successo niente», che sarebbe falso.

È il materiale che decide se nella prossima versione valga la pena rileggere lo stato una
seconda volta, in ritardo. Scrivilo, non lasciarlo alla memoria.

---

## Prova 7 — Un'integrazione installata **dopo**

**Cosa fare.** Con l'add-on **già avviato** (e senza riavviarlo), installa in Home
Assistant un'integrazione nuova che porti servizi propri — va bene qualcosa di innocuo,
per esempio *Lista della spesa* o *Local To-do*. Poi, in chat, chiedi a HIRIS di usarne
un servizio (*«aggiungi il pane alla lista della spesa»*).

**Cosa deve succedere.** HIRIS **la vede**, senza riavvii e senza aggiornamenti. È la
prova che «verificare invece di insegnare» mantiene la promessa: nessun catalogo scritto
a mano avrebbe potuto conoscere un'integrazione installata due minuti fa.

**Un tempo di attesa c'è, ed è previsto**: il registro dei servizi si rinfresca quando ha
più di **cinque minuti** e qualcuno tenta un'azione. Quindi il primo tentativo subito dopo
l'installazione può ancora rifiutare. **Riprova dopo cinque minuti**: al secondo giro deve
andare. Nel log si vede la riga `registro servizi: N domini, M servizi` ricomparire con
`M` più grande di prima.

**Come si riconosce il fallimento.** Dopo cinque minuti e un secondo tentativo, HIRIS
continua a dire che quel servizio non esiste. Guarda il log: se compare `registro servizi:
rinfresco fallito (...), tengo quello di ...s fa`, il rinfresco sta fallendo e HIRIS sta
lavorando su una fotografia vecchia — che è meglio di niente, ma non è la promessa.

---

## Prova 8 — La stessa cosa dal percorso in abbonamento

**Cosa fare.** Cambia percorso: nella configurazione dell'add-on passa alla **Strada A**
del §2 di `prova-la-2.0.md` (abbonamento Claude Max), riavvia l'add-on, e **rifai la prova
2** — spegnere una luce vera — più una qualunque delle prove di rifiuto (la 3 è la più
rapida).

Che tu sia davvero sull'altro percorso lo riconosci dall'attesa: dopo due minuti la chat
dice *«Puoi anche chiudere: se arriva, la risposta finisce nella cronologia»*, mentre sul
percorso diretto dice *«Tieni aperta questa pagina...»*.

**Cosa deve succedere.** **Esattamente le stesse cose.** La luce si spegne, il log scrive
la stessa riga `azione eseguita [origine=chat] ...`, il servizio inventato viene rifiutato
con lo stesso elenco. I due percorsi ricevono gli strumenti dallo stesso catalogo, e
questa prova è ciò che verifica che quel «lo stesso» sia vero fuori dalle prove
automatiche.

**Come si riconosce il fallimento.** Su questo percorso HIRIS risponde che non può agire,
oppure non chiama nessuno strumento, oppure nel log compare *«lo strumento «esegui» non e' fra quelli
disponibili»*. Significa che il catalogo unico si è sdoppiato da qualche parte,
ed è precisamente il difetto che questa versione ha cercato di impedire.

---

## Due controlli che si fanno dopo, non durante

### A. Il ricordo che contiene degli `entity_id` (dieci secondi, dopo qualche giorno)

Quando una tua frase ammette più letture — *«accendi il bagno»*, e in bagno ci sono due
luci e uno scaldasalviette — HIRIS agisce sulla lettura più naturale e te lo dice. Se lo
correggi, ti proporrà di **ricordare la tua preferenza**. Qui c'è la regola che va
sorvegliata, e il segnale è preciso.

**Cosa guardare.** Dopo qualche giorno d'uso, apri la pagina **Memoria** nella
configurazione di HIRIS e scorri i ricordi.

**Cosa deve succedere.** I ricordi nati da una correzione devono essere **preferenze
scritte a parole**: *«quando dico di accendere una stanza senza specificare altro, di
solito intendo le luci»*.

**Come si riconosce il fallimento.** Se un ricordo **contiene degli `entity_id`** —
qualcosa come *«accendi il bagno = light.bagno_1, light.bagno_2»* — il modello ha salvato
una **sostituzione** invece di una **preferenza**, e la regola non ha funzionato. Non è un
difetto cosmetico: da quel momento quella frase non potrà più significare altro (non
potrai più intendere il riscaldamento con le stesse parole) e non varrà per nessun'altra
stanza. Cancella il ricordo dalla pagina Memoria e **segnalalo con la frase esatta**: è il
testo del prompt che va corretto, non il ricordo.

### B. `_DOMINI_UNIVERSALI` ha dentro una cosa sola

C'è una lista, in `hiris/app/azione/verifica.py`, dei domini i cui servizi si applicano a
entità di **qualunque** dominio. Oggi contiene solo `homeassistant`, ed è stata lasciata
così di proposito: gli altri candidati (`group`, alcuni servizi di `automation`, e chissà
cos'altro in una casa con integrazioni che noi non abbiamo) non sono stati aggiunti al
buio, perché indovinarli sarebbe stato lo stesso difetto che questa versione elimina —
scrivere a mano un catalogo invece di misurarlo.

**È quindi la prima cosa che ci aspettiamo si rompa su una casa vera**, e si riconosce da
un rifiuto di questa forma su una chiamata che invece sarebbe legittima:

```
azione rifiutata [origine=chat]: «group.set» non si applica a «light.cucina», che e' del dominio «light».
```

**Se lo vedi, annota il servizio esatto.** Non è un guasto da aggirare: è esattamente il
dato che serve per allargare quella lista con dei nomi *osservati*.

---

## Cosa segnalare, e come

Per ogni prova che fallisce servono tre cose, e sono sempre le stesse: **la frase che hai
scritto in chat**, **cosa ti ha risposto HIRIS** e **le righe di log** attorno a quel
momento (`registro servizi: ...`, `azione eseguita ...`, `azione rifiutata ...`, `azione
fallita ...`).

Per la prova 1 aggiungi l'output del `curl`: è l'unico pezzo di questo foglio che non
possiamo ricostruire da soli.

E se la prova 1 fallisce, le altre non servono: **è quella che decide se questa versione
sta in piedi.**
