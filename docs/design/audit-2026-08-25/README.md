# Audit a 360° — HIRIS 3.12.1

**Date:** 24–25 agosto 2026 · **Ramo:** `2.0` · **Perimetro:** ~30.000 righe di Python in 81 file,
5.800 di JS in 21, 38 rotte HTTP, 13 strumenti, 160 file di test, 11 dipendenze.

Nasce da una domanda del proprietario, alla fine della fase 1 del refactor: *«capire se nel tempo
abbiamo creato falle»*. Non è la review di una fetta: è la domanda su cosa sia successo
all'**insieme** mentre le fette si accumulavano.

---

## Il verdetto, in un paragrafo

Il codice **è tenuto insieme, non si sta sfaldando**. La mappa reale coincide con quella
dichiarata, i cataloghi sono uno solo e derivato, i doppioni pericolosi sono chiusi o dichiarati
con la ragione accanto, e la scansione delle dipendenze non ha trovato **nessuna CVE aperta**. Il
degrado da accumulo è concentrato in due punti: una funzione di avvio troppo lunga (rischio
futuro, non difetto di oggi) e — soprattutto — **le frasi**. Il giudizio del filone architettura,
riportato per intero perché è la sintesi migliore dell'intero audit:

> **Le crepe stanno nelle frasi, non nel codice.**

Tre dei quattro Critical erano affermazioni false: il README dichiarava un confine del prodotto
che lo schedulatore aveva superato da tre release, e il modulo di sicurezza prometteva una
protezione che non esisteva. Il quarto era una difesa mancante.

## Come è stato fatto

Cinque filoni indipendenti, in parallelo, tutti in **sola lettura** e con l'ordine esplicito di
**refertare e non correggere**. Ogni filone aveva lo stesso metro — le quattro fondamenta del
progetto, il difetto n.1 (i test che non possono fallire), e la regola che una frase falsa è un
difetto quanto una funzione sbagliata.

Due filoni hanno lavorato **sul sistema vero**: quello funzionale interrogando l'add-on in
produzione e Home Assistant, quello UI/UX con un browser reale su un'istanza locale collegata
alla casa (1224 entità), a due viewport, con 26 screenshot. È la scelta che ha prodotto i
risultati più utili: gli scarti fra ciò che il codice dichiara e ciò che il sistema risponde non
si vedono leggendo.

| | Cosa ha guardato | Esito |
|---|---|---|
| **L1** | Sicurezza applicativa | 2 Critical · 3 Important · 3 Minor |
| **L2** | CVE e catena di fornitura | **0 CVE** · 4 rilievi di processo |
| **L3** | Architettura e codice morto | 1 Critical · 3 High · 6 Medium · 4 Low |
| **L4** | Funzionale, sulla casa vera | 1 Critical (schieramento) · 1 ambientale · 1 minore |
| **L5** | UI/UX desktop e mobile | 2 Critical · 3 Important · 2 Minor |

I referti completi sono i file accanto a questo. Gli screenshot (12 MB) restano fuori dal
repository: vivono nella cartella di lavoro dell'audit.

---

## Cosa è stato corretto

Su decisione del proprietario: **solo i Critical**, ognuno con test, prova per mutazione e review
indipendente. Tre giri di correzione sulla sicurezza, due sulla UI, ognuno seguito da una review
che ha trovato altro — e ogni volta il rilievo nuovo era della stessa famiglia di quello chiuso.

**Sicurezza — il sanitizzatore era codice morto.** `_sanitize.py` esisteva per difendere
dall'iniezione di istruzioni nel prompt del modello, e aveva **zero chiamanti di produzione**
mentre il suo docstring dichiarava una protezione attiva. Adesso è cablato su tutte le vie per cui
testo esterno entra nel contesto: lo specchio degli stati, l'anagrafe, i ricordi (da un punto
solo, condiviso fra le tre porte), il diario, lo storico, e il nome delle automazioni. Il
troncamento che applicava — 120 caratteri, silenzioso — è stato alzato al tetto vero di Home
Assistant e **dichiarato** con un marcatore.

**Documentazione — il README mentiva sul confine del prodotto.** Dichiarava quattro lavori
periodici e «nessuno tocca la casa»: sono sette, e uno esegue servizi e manda notifiche fuori
dalla chat. Corretto nel README, in `PRODUCT.md`, in `docs/prova-la-2.0.md`, nella descrizione
dell'add-on nello store (`config.yaml` — la prima cosa che una persona legge) e in due docstring
del codice, più un'annotazione datata sul documento di design che citava la frase cancellata.

**UI — due difetti sul telefono.** Sulla chat il pannello laterale copriva l'hamburger che
l'aveva aperto: il gesto istintivo per chiudere **portava altrove**, attivando il link nascosto
sotto. E l'albero della casa nasceva tutto espanso — 70.000 pixel su mobile — ed era l'unica
pagina del prodotto che sfondava lo schermo in orizzontale (670 px su un viewport di 390).
Adesso: zero scorrimento orizzontale a entrambe le viewport, 1.785 px di altezza, e
l'identificatore più lungo della casa (93 caratteri) va a capo **senza troncamento** — la
condizione che tiene utile quella pagina a chi ci cerca un id.

---

## Cosa NON è stato corretto, e perché

**La decisione parcheggiata dal proprietario: `esegui`.** Tocca la casa senza cancello di consenso
e senza lista nera — il consenso esiste solo sulle costruzioni. Con un'iniezione riuscita, la
strada arriva a serratura, allarme, apricancello e riavvio di Home Assistant. Non è un bug: è una
scelta di prodotto, e cambiarla cambia l'uso quotidiano. Resta scritta nel referto L1 con la
sequenza d'attacco misurata.

**E un'informazione emersa dopo**, che al momento della decisione non c'era. La domanda posta al
revisore finale era: con il sanitizzatore cablato, la difesa è completa?

> «Non è più un colabrodo, ma "completa" sarebbe una frase falsa. Il filtro è una **denylist
> regex**: ferma le frasi note, non l'iniezione in sé. Un'esca formulata fuori dai pattern passa
> da ogni porta sanificata. La completezza raggiunta è del **cablaggio**, non della **difesa**:
> è mitigazione seria, non un confine.»

Il cablaggio riduce l'esposizione; non sostituisce il confine.

**I minori differiti**, tutti a verbale nei referti: i due troncatori duplicati (`_sanitize` e
`ha_client._truncate` — stesso algoritmo, stessa costante in due file); il tetto unico di 255
caratteri su campi che non sono `state`; i falsi positivi del filtro su frasi italiane legittime;
il corpo YAML del comportamento, lasciato fuori con una ragione vera (lo scrive il proprietario o
passa dal consenso umano); `_on_startup` da spezzare, con i confini di taglio già scritti in L3;
la mancanza di un «espandi tutto» sull'albero desktop; `.drawer` in `hiris-config.css`, codice
morto mai referenziato.

---

## Cosa resta da provare sulla casa

1. **`esegui` e `costruisci` non sono stati esercitati**: l'audit era in sola lettura, e nessuno
   ha acceso niente per curiosità. I tre strumenti che scrivono sono stati giudicati **solo
   leggendo il codice**.
2. **La paternità nel diario.** I campi che la portano — `context_domain`, `context_service`,
   `context_user_id` — sono stati **misurati e trovati**, ma non sono ancora consegnati al
   modello: la descrizione di `accaduto` promette oggi solo ciò che il codice fa.
3. **Il pin della CLI** (`2.1.241`) non è mai stato verificato nel container: si legge nella riga
   «init del ponte», campo `cli=`.

---

## Una cosa sul metodo, perché si ripeta

Ogni review dopo una correzione ha trovato **un difetto della stessa famiglia di quello chiuso**:
la correzione della sovrapposizione ha reintrodotto una sovrapposizione (la X sopra il logo); il
file guarito da una frase falsa ne ha guadagnata una nuova, due volte; il sanitizzatore cablato
per chiudere una fondamenta 3 l'ha rotta altrove, lasciando lo stesso dato sanificato da una
porta e grezzo da un'altra.

Non è sfortuna: **chi corregge guarda il punto, non la classe.** Vale come istruzione per la
prossima volta — dopo aver chiuso un difetto, cercare i suoi fratelli è più produttivo che
verificare tre volte la chiusura.
