# Costruire in Home Assistant

**Data:** 22 agosto 2026 · **Ramo:** `2.0` · **Stato:** disegno approvato dal proprietario, piano da scrivere

**Supera** la §4 («Fetta 2 — Costruire») di `docs/design/2026-08-12-azione-design.md`. Quella
sezione era stata scritta senza leggere il sorgente di Home Assistant: **tre delle sue premesse non
reggono ai fatti**, **una questione che lasciava aperta si chiude**, e **tre affermazioni si
confermano — ora con la prova**. Tutte al §1.3. Restano validi di quella spec i quattro invarianti
del §2 — riformulato il primo, come dice il §2.1 qui sotto.

---

## 0. Cosa chiede il proprietario

Parole sue, 22 agosto 2026: HIRIS deve saper **creare e configurare Home Assistant** — automazioni,
script, scenari, plance — **correggere errori**, e **capire da solo se serve un'automazione o uno
script (o tutti e due)**. Deve sapere come ci si integra e come si interagisce con HA, e in
particolare con **il suo**. La funzione dev'essere **richiamabile dagli altri oggetti di HIRIS**,
non deve creare oggetti che si sovrappongono a quelli esistenti, e il codice dev'essere coerente
col resto del progetto.

Istruzione esplicita sul metodo, stessa data: *«tutto quanto deciso per gli argomenti trattati qui
non ha più valore, va tutto rivalutato»* — prima si analizzano Home Assistant e la sua
documentazione, poi si propone. Questa specifica nasce da quell'analisi.

---

## 1. L'analisi — cosa dicono davvero Home Assistant e questa casa

### 1.1 Due canali di scrittura, di natura diversa

È il fatto che decide la forma dell'intera feature. Verificato sul sorgente di
`home-assistant/core@dev`, non sulla documentazione pubblica — che di questi endpoint **non parla
affatto**: `developers.home-assistant.io/docs/api/rest` non documenta nessuna rotta di
configurazione.

| | **Canale A — HA valida e scrive lui** | **Canale B — leggi, fondi, riscrivi** |
|---|---|---|
| Cosa | automazione, script, scena | plance (Lovelace) |
| Come | `POST/DELETE /api/config/{automation\|script\|scene}/config/{chiave}` | WS `lovelace/config/save` |
| Sorgente | `components/config/view.py` — `"/api/config/{component}/{config_type}/{config_key}"` | `components/lovelace/websocket.py` |
| Chi scrive il file | **Home Assistant** — `_write_value` trova per `id` e **sostituisce**, altrimenti aggiunge | il chiamante, passando **l'intera** configurazione |
| Validazione | il validatore vero del dominio (`async_validate_config_item`, `PLATFORM_SCHEMA`) → `400` col motivo | **nessuna** |
| Dopo | `post_write_hook`: `reload` del dominio; su DELETE toglie l'entità dal registro | sostituzione secca |
| Permesso | `@require_admin` su GET, POST e DELETE | admin |
| Chiave | automazione e scena: `id` (UUID generato se assente) · script: slug (`cv.slug`) | `url_path` |

**Conseguenza che va detta per intero.** Il danno misurato sull'`automations.yaml` di questa casa —
la voce accodata quattro volte, resa invisibile dalle ancore `&id001` di PyYAML, registrato in
memoria come regola per la fetta di costruzione — **non può ripetersi sul canale A**, perché HIRIS
non serializza nessuno YAML: lo scrive Home Assistant, e lo scrive trovando-per-id-e-sostituendo.
Le sei regole di quella memoria non spariscono: **diventano il motivo per cui non si torna mai a
scrivere quei file in proprio.** Se un giorno qualcuno proporrà «facciamo prima a scrivere il
file», la risposta è quella memoria.

### 1.2 Esiste la prova a vuoto

WS `validate_config` (`components/websocket_api/commands.py`) accetta `triggers`, `conditions`,
`actions` e risponde, per ciascuna chiave, `{"valid": true|false, "error": ...}`. **Non salva
niente.** Accanto ci sono `test_condition`, `subscribe_condition` e `render_template`.

È la leva più importante trovata dall'analisi: rende possibile *comporre → far dire a questa casa
se è valido → mostrare → scrivere solo dopo il sì*, senza che un tentativo sbagliato costi una
scrittura. La spec vecchia si accontentava di «li valida HA al salvataggio»: si può fare meglio.

### 1.3 Cosa della spec del 12 agosto non regge

| Diceva | Il fatto |
|---|---|
| «l'idioma della casa: **assente**» | **Falso oggi.** I corpi di automazioni e script sono nel nucleo (`casa/nucleo.py::_righe_comportamento`, sezione *«Ciò che la casa fa già da sola»*) e in `guarda`/`cerca`. Da **usare**, non da costruire. |
| «gli artefatti li valida HA **al salvataggio**» | Si valida **prima**, senza salvare (§1.2). |
| «l'automazione **nasce disabilitata**» come banco di prova | Sostituito dall'anteprima validata + il gesto (§3). Un oggetto rifiutato non lascia **niente** in HA, che è meglio di un oggetto spento che sembra un guasto. |
| «come si riconosce un artefatto HIRIS?» — **questione aperta** | **Chiusa**: l'etichetta nel registro etichette di HA (§5). |
| «l'API di configurazione è la strada» — **presupposto** | **Confermata** sul sorgente e su questa casa (tutte le voci `origine: file`). Resta un presupposto d'ambiente: il codice deve **accorgersene**, non assumerlo (§6). |
| «la plancia sta fuori» | **Confermata, e ora con la prova**: `lovelace/config/save` sostituisce l'intera configurazione. Non era un'opinione. |
| «i costruttori costruiscono, non inoltrano» | **Resta, rafforzata** (§4.2). |

### 1.4 Il diritto di scrivere

`components/hassio/__init__.py` crea l'utente del Supervisor con
`hass.auth.async_create_system_user(HASSIO_USER_NAME, group_ids=[GROUP_ID_ADMIN])`: **è un
amministratore**, e le rotte del canale A sono `@require_admin`. Il sorgente lo dice; **la casa
vera deve confermarlo** (§9, prova ①). Finché non è confermato, nessun ragionamento si appoggia a
questo.

### 1.5 Questa casa, misurata il 22 agosto 2026

Letta da `GET /api/casa` sull'add-on vivo (3.10.2):

- Home Assistant **2026.8.3** · 1227 entità · 241 dispositivi · 15 aree · 3 piani · 53 integrazioni.
- **18 automazioni + 2 script, tutte `origine: file`** → gestite dall'editor UI: il canale A è
  aperto *su questa casa*.
- **7 plance, tutte `modalita: storage`** → scrivibili, ma solo per intero.
- **0 etichette, 0 categorie** → il registro etichette di HA è libero.
- Lo schema in uso è quello **moderno**: `triggers:`/`conditions:`/`actions:` al plurale, con
  `trigger: numeric_state` dentro. Un modello che scrive alla vecchia maniera verrebbe rifiutato —
  e la prova a vuoto lo prende prima che costi qualcosa.

---

## 2. Il fondamento

### 2.1 Un canale, una porta

L'invariante del prodotto diceva: *«un unico punto scrive su Home Assistant»*, e il docstring di
`azione/porta.py` aggiunge che **un secondo punto di scrittura è un difetto, non
un'ottimizzazione**. Quella porta esegue **servizi**. Costruire scrive **configurazione**: altro
canale HTTP, altra verifica (`validate_config` invece del registro dei servizi), altro «dopo» (un
`reload` e un'entità che compare, non un `state_changed`). L'invariante si riformula **in chiaro**,
non si aggira:

> **Un canale, una porta.** Per ogni canale di scrittura verso Home Assistant esiste **un unico
> modulo** che lo attraversa. Oggi sono due: i **servizi** (`azione/porta.py`) e la
> **configurazione** (`azione/costruzione/officina.py`). Ciò che i due canali condividono — la
> cronaca, l'`origine`, la forma dell'esito e del rifiuto motivato — vive **una volta sola** e ha
> la **stessa forma da entrambi** (fondamenta 3). Un terzo punto che scriva su HA fuori da queste
> due porte è un difetto.

Va scritto in `CLAUDE.md` e nel docstring di `porta.py`, col motivo. Un invariante cambiato in
silenzio è peggio di un invariante cambiato.

### 2.2 Verificare, non insegnare

Nessun catalogo di sintassi da mantenere allineato. La verità sulla forma di un'automazione la dà
`validate_config` di **questa** installazione, e in più HIRIS ha sotto gli occhi **18 esempi veri**
scritti dal proprietario. Un'integrazione installata fra sei mesi funziona senza che nessuno tocchi
HIRIS.

### 2.3 Dire cosa è successo, non cosa è stato chiesto

Dopo la scrittura si **rilegge**: l'entità è comparsa? con quale `entity_id`? Se il `reload` è
riuscito ma l'entità non c'è, si dichiara. Vale la legge del prodotto — dichiarare ciò che non si
sa invece di fingerlo.

### 2.4 I costruttori costruiscono, non inoltrano

Un costruttore che riceve lo YAML già scritto dal modello e lo gira a Home Assistant non è un
imbuto: è un tubo con un bel nome. **Ogni forma si compone dai parametri.** Il modello produce
l'intenzione, non l'artefatto.

### 2.5 Il rifiuto porta il motivo

Mai «non posso». Sempre: *«questa struttura è gestita a mano, non posso scriverla»*, *«HA rifiuta
questo innesco: …»*, *«l'entità X non esiste in questa casa»*.

---

## 3. I tre gesti

Decisione del proprietario: **il gesto decide** quanto controllo serve. Non una regola sola per
tutto.

**Creare** — sette momenti, ognuno dei quali può fermarsi dicendo perché:

1. **Il mestiere** (§4.1) — serve un'automazione, uno script, una scena, o due cose insieme?
2. **La composizione** (§4.2) — `forme.py` compone dai parametri.
3. **La prova a vuoto** — `validate_config` su questa casa. Se cade, il motivo torna al modello,
   che si corregge su un fatto e non su un ricordo. **Tetto: due giri**, poi ci si ferma e lo si
   dice. Un tetto senza dichiarazione è un silenzio.
4. **L'anteprima** — in italiano: cosa fa scattare la cosa, su quali entità (**coi nomi veri**),
   cosa fa, **cosa non fa**, e quali helper nascerebbero insieme a lei.
5. **Il sì** (§7) → `POST /api/config/…`; HA valida col validatore vero e **scrive lui il file**;
   `reload`.
6. **La rilettura** (§2.3) e l'etichetta (§5).
7. **La cronaca** — una riga: origine, cosa, esito. **La stessa tabella dei comandi**: un atto è lo
   stesso fatto qualunque sia l'origine (fondamenta 3).

**Modificare** — si legge il corpo attuale (già disponibile in `casa/comportamento.py`), si compone
il nuovo, prova a vuoto, si mostra il **confronto prima/dopo**, si esige il **sì esplicito**, si
archivia il «prima» (§6), si scrive.
**Se l'oggetto l'ha scritto il proprietario, HIRIS lo dice a chiare lettere prima di toccarlo.**
Regola posta dal proprietario, e vale a maggior ragione quando sarà il Brain a proporre di far
evolvere un'automazione esistente.

**Cancellare** — sì esplicito, copia conservata (§6), `DELETE` — che toglie anche l'entità dal
registro.

**Il perimetro di ciò che HIRIS può toccare è pieno**: tutte le automazioni, gli script e le scene
della casa, non solo i propri. Decisione del proprietario, motivata sul futuro: il Brain proporrà
di far evolvere ciò che esiste già. Il contrappeso non è un recinto, è **la dichiarazione
esplicita** più il confronto prima/dopo più la copia.

### 3.1 Gli helper, e il caso scomodo

Nel perimetro della fetta: `input_boolean`, `input_number`, `input_select`, `input_text`,
`input_datetime`, `timer`, `counter`, `schedule`. Senza di loro metà delle automazioni utili si
ferma a un passo dalla fine.

Sono un **secondo canale** (comandi WS per dominio), e questo va dichiarato: il taglio per canale
non è puro, ed è una deroga presa con gli occhi aperti perché un helper senza la sua automazione
non serve a niente.

**L'ordine, e la disfatta.** Prima il sì, poi gli helper, poi l'automazione. Se l'automazione viene
rifiutata a quel punto, **l'officina disfa gli helper appena creati e lo dichiara**. Senza questa
regola ogni tentativo fallito lascia rifiuti in casa del proprietario — ed è il modo esatto in cui
si accumula la spazzatura che nessuno cancella più.

---

## 4. I moduli

```
azione/
  porta.py         · esegue servizi                        (resta com'è)
  registro.py      · cosa HA sa fare (i servizi)           (resta)
  verifica.py      · i controlli sui comandi, pura         (resta)
  cronaca.py       · ogni atto, ogni origine               (ESTESA: anche le costruzioni)
  costruzione/
    officina.py    · la porta del canale configurazione: valida → scrive → rilegge → registra
    forme.py       · compone automazione/script/scena/helper DAI PARAMETRI
    mestiere.py    · pura: quale struttura serve, e perché
    versioni.py    · il «prima», e il ritorno indietro
proxy/ha_client.py · primitive nude, un solo chiamante ciascuna:
                     valida_config · salva_configurazione · cancella_configurazione · crea_helper
                     · crea_etichetta · applica_etichetta
```

Le primitive stanno in `ha_client.py` e non in un client nuovo: **il client di Home Assistant è
uno** (fondamenta 2). È lo stesso pattern già adottato per `call_service` — primitiva nuda, un solo
chiamante.

### 4.1 `mestiere.py` — il consiglio, e la Legge I che diventa codice

Riceve l'intenzione strutturata e risponde con la struttura **e il motivo**:

| Se… | allora |
|---|---|
| c'è un innesco («quando…», «se…») | **automazione** |
| nessun innesco, una sequenza che lanci tu | **script** |
| nessun innesco, nessuna sequenza: stati da ristabilire insieme | **scena** |
| un innesco **e** una sequenza che serve anche altrove | **automazione + script** (l'automazione chiama lo script) |
| serve un parametro in ingresso | **script** (le automazioni non prendono parametri; gli script sì, con `fields`) |
| «ogni giorno alle 7» | **automazione** con innesco orario, **non** una promessa dello schedulatore |

L'ultima riga previene un doppione vero: lo schedulatore serve per *«fra un'ora, una volta»*; una
**ricorrenza** è un'automazione HA. Senza la regola scritta, i due oggetti si sovrappongono.

**La Legge I si applica anche a HIRIS.** «Se HA lo sa fare, si crea un oggetto di HA» è stata
finora un criterio per decidere cosa *non* mettere nel prodotto. `mestiere.py` è il punto in cui
smette di essere un principio e diventa codice eseguibile.

Il mestiere **consiglia, non blocca**: se dissente da come è stata posta la richiesta, l'anteprima
porta le due letture col motivo e decide l'utente. **Il consiglio finisce nella cronaca**, così si
può misurare quanto sbaglia invece di crederlo.

### 4.2 `forme.py` — la composizione

Una funzione per struttura, dai parametri. L'`id` di automazioni e scene lo genera HIRIS e lo
**verifica assente** prima; per gli script la chiave è uno slug e va verificata la collisione.

Ogni automazione composta porta `alias`, `mode` e una `description` **che dice l'intenzione** — la
frase da cui è nata.

*Sembra un doppione della cronaca, e non lo è.* Un'automazione è un **oggetto di Home Assistant** e
deve reggersi da sola **lì dentro**: è la fondamenta 1 applicata all'oggetto che stiamo creando.
Chi la aprirà nell'editor fra sei mesi deve capirla senza HIRIS. La cronaca porta un fatto diverso:
chi, quando, com'è andata.

---

## 5. La paternità sta in Home Assistant

Si crea **una volta** l'etichetta `HIRIS` (`config/label_registry/create`) e la si applica
all'entità nata, helper compresi (`config/entity_registry/update`). La si vede in HA, ci si filtra,
e resta anche se HIRIS sparisce. **Nessun registro interno di «cose mie»**: sarebbe un doppione di
un fatto che HA sa già tenere (fondamenta 2).

**Su un oggetto scritto dal proprietario e modificato da HIRIS l'etichetta NON si mette.**
L'etichetta dice *chi l'ha fatto*, e non l'ha fatto lui. Che HIRIS ci abbia messo le mani è un
fatto diverso, e vive dove lo si può interrogare: la cronaca, l'archivio delle versioni, la pagina.

---

## 6. Il ritorno indietro

`/data/costruzioni.db`. Una riga per atto: identificatore (dominio + chiave), gesto, **stato**
(§7 — una proposta è un atto non ancora applicato), corpo **prima**, corpo **dopo**, quando,
origine, e il **collegamento** alla riga di cronaca — per identificatore, mai copiando
(fondamenta 2).

Due regole:

1. **Rimettere il «prima» è un'altra costruzione**, e passa dalla stessa officina, validazione
   compresa. Se nel frattempo un'entità è sparita e quel corpo non è più valido, **lo dice** invece
   di scriverlo.
2. **L'ultima versione precedente di ogni oggetto non scade mai.** Lo storico più vecchio si pota;
   quella no. Home Assistant non tiene storico: quella riga è l'unica copia esistente al mondo, e
   potarla a 90 giorni come le esecuzioni sarebbe cancellare un backup.

**Il presupposto d'ambiente si rileva, non si assume.** Se l'API risponde che quella struttura non
è modificabile — automazioni gestite a mano, o in `packages/` — HIRIS dice *«queste automazioni
sono gestite a mano, non posso scriverle»*, invece di fallire in un modo che sembra un guasto.

---

## 7. In chat, e il cancello che è l'umano

Due strumenti nuovi: **`costruisci`** produce una **proposta** (validata, con l'anteprima) e **non
scrive niente**; **`conferma`** la applica.

Il punto delicato: se confermare è soltanto un'altra chiamata, **il modello può concatenarla da
solo** nello stesso turno, e il sì dell'utente sparisce. Quindi il codice restringe:

> **Una proposta non può essere confermata nel turno che l'ha creata.** Serve un messaggio umano in
> mezzo. Quel messaggio **è** il sì.

Non è una convenzione di prompt: è una guardia deterministica, la stessa forma di *«il modello
propone, il codice restringe»* già adottata altrove nel prodotto.

**Trappola nota, da non ripagare.** Un catalogo di strumenti che cambia per contesto ha già rotto
questo prodotto una volta (3.10.1: `nomi_mcp()`, `--allowedTools`, la sonda e `verifica_init`
ancorati al catalogo della chat). I due strumenti nuovi vanno aggiunti cercando **tutti** i punti
che lo assumono fisso — col `grep`, non a memoria. Il turno di una promessa (`SOLA_LETTURA`)
**non** li riceve.

**Dove vive una proposta.** Nello **stesso archivio degli atti** (§6), con uno stato — `in_attesa`,
`applicata`, `rifiutata`, `scaduta` — e non in una tabella propria: una proposta e l'atto che ne
nasce sono lo stesso oggetto in due momenti, e separarli creerebbe due case per un fatto solo
(fondamenta 2). È anche ciò che permette a una proposta di sopravvivere alla chiusura della chat e
al riavvio dell'add-on — la stessa correzione già imposta dal proprietario per le promesse: *la
verità vive nell'archivio, non nella conversazione*.

**Tetti dichiarati:** al massimo **20 proposte in attesa**; una proposta **scade dopo 7 giorni** (la
casa cambia, e un'anteprima vecchia descrive entità che potrebbero non esserci più — applicarla
sarebbe una scrittura decisa su un mondo che non esiste). Alla scadenza lo stato lo dice; non
sparisce in silenzio.

### 7.1 Richiamabile dagli altri oggetti

`officina.costruisci(intento, origine)` — stessa filosofia di firma di `esegui`, e la fondamenta 4.
Per un chiamante che non è la chat — il Brain di domani — non c'è nessun umano davanti: la proposta
resta **in attesa** e compare nella pagina come «da approvare».

**Un solo meccanismo serve la chat di oggi e il Brain di domani**, e non si costruisce oggi niente
del Brain.

---

## 8. La pagina «Costruzioni»

Voce di menu accanto a Promesse. Tre cose: le **proposte in attesa** col sì/no · **ciò che HIRIS ha
costruito** (gesto, quando, origine, etichetta) · il **confronto prima/dopo** con il **ripristino**.

Rotte: `GET /api/costruzioni` · `GET /api/costruzioni/{id}` · `POST /api/costruzioni/{id}/conferma`
· `POST /api/costruzioni/{id}/ripristina`.

Disegno con l'agente `ux-ui-specialist`, come impone il contratto. Senza questa pagina l'archivio
delle versioni sarebbe uno stato che solo un `curl` può vedere — la fondamenta 4 violata.

---

## 9. Le verifiche che nessun banco può dare

La fetta **non è pubblicabile** senza, sulla casa vera:

1. **Una POST vera sul canale di configurazione.** È lì che si dimostra che l'add-on è davvero
   amministratore *attraverso il proxy del Supervisor*. Il sorgente lo dice (§1.4); se questa prova
   cade, **ci si ferma**: cade l'intera fetta, non un dettaglio.
2. **La forma di `validate_config` sulla 2026.8.3** — cosa risponde davvero su valido e su non
   valido.
3. **Un'automazione creata da HIRIS che scatta davvero.**
4. **Una modifica a un oggetto scritto dal proprietario, e il ritorno indietro.**
5. **Un helper nato e disfatto** dopo un rifiuto dell'automazione.

Le altre prove — i rifiuti, i tetti, la guardia del turno — le copre il banco.

---

## 10. Cosa resta fuori, dichiarato

- **Le plance** — canale B, rischio diverso: **fetta propria**.
- **Diagnosi e correzione degli errori** — `trace/list` e `trace/get` (che HIRIS **oggi non legge
  affatto**, ed è la fonte più ricca su *perché* un'automazione è fallita), il flusso di
  riparazione `POST /api/repairs/issues/fix` (un data-entry flow multi-passo, non una chiamata),
  `/api/error_log`. **Fetta propria**, la terza.
- **Aree, piani, dispositivi, integrazioni, blueprint** — nessuno dei due canali, e nessuno è stato
  chiesto.
- **Le automazioni in `packages/`** — l'API non le governa: HIRIS lo rileva e lo dice (§6).
- **Le sicurezze** — resta valida la sequenza decisa dal proprietario: prima la capacità.

## 11. Pulizia — perché ogni fetta è anche pulizia

- La **§4 di `2026-08-12-azione-design.md`** va marcata **superata** da questa specifica, con il
  rimando alla tabella del §1.3.
- Il piano include la ricognizione con `scripts/censimento.py`: la fetta aggiunge molto, e ciò che
  lascia orfano non sta dentro il proprio diff.
- La review finale è **dell'intero ramo**, non del diff — la regola della review rovesciata.
