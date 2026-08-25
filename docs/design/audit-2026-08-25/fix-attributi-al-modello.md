# Attributi al modello — il termostato «heat» che non stava scaldando

Ramo `fix/attributi-al-modello`, da `2.0`. Bug trovato dal proprietario
usando il prodotto: ha chiesto in chat se il riscaldamento fosse attivo, e
HIRIS ha risposto SÌ, citando due termostati «in modalità riscaldamento
("heat")» — falso, erano `hvac_action: idle`, cioè fermi, con target 17 e
temperatura reale 25.

Un giro di commit: test (rosso) → implementazione (verde), sulla catena
`entity_cache._to_minimal` → `anagrafe.specchio_vivo` → `casa/domande.guarda`
(e i tre chiamanti di produzione di `specchio_vivo` che condividono lo
stesso anello: `strumenti.py::_specchio`, `handlers_casa.py`,
`handlers_memoria.py`).

---

## La diagnosi, come l'ho verificata

Il compito arrivava con la diagnosi già fatta. L'ho riletta sul sorgente
invece di fidarmene, riga per riga:

1. **`entity_cache.py::_to_minimal`** raccoglie davvero gli attributi giusti.
   `_DOMAIN_ATTRS["climate"]` contiene `hvac_mode`, `hvac_action`,
   `current_temperature`, `temperature`, `preset_mode`, e la funzione li
   mette in `result["attributes"]` quando sono presenti. Confermato con un
   test isolato (`_to_minimal(_RAW_TERMOSTATO)["attributes"]["hvac_action"]
   == "idle"`) — vero **prima** di ogni mia modifica.
2. **`anagrafe.py::specchio_vivo`** (riga ~200, versione pre-fix) faceva
   `stato[entity_id] = e.get("state")` e basta: nessuna riga leggeva
   `e.get("attributes")`. Confermato costruendo lo specchio dallo stesso
   dizionario che `_to_minimal` produce e osservando che il quinto valore
   restituito (`da_quando`, l'ultimo esistente prima di questa fetta) non
   aveva alcun gemello per gli attributi.
3. Ho ricostruito **la catena intera** con lo stato grezzo vero (`hvac_mode:
   heat`, `hvac_action: idle`, `current_temperature: 25.2`, `temperature:
   17`) e chiamato `guarda(..., "entita", "climate.matrimoniale")` sul
   codice pre-fix: il risultato era `{"stato": "heat", "stato_leggibile":
   "heat", ...}`, senza traccia di `hvac_action` né delle temperature — la
   stessa forma misurata dal proprietario in produzione. Questa prova (il
   test `test_c_guarda_su_un_entita_non_dice_piu_solo_heat`, provata anche
   contro il codice pre-fix con `git stash`) è quella che ho usato per
   confermare la diagnosi prima di scrivere una riga di correzione: 8 dei 9
   test nuovi falliscono sul codice non modificato, uno solo (quello che
   verifica il solo `_to_minimal`) passava già.

Confermato anche il secondo strato del difetto: `guarda` prometteva la
traduzione italiana dello stato ma per `climate` restituiva `heat` così
com'è (già a verbale come rilievo minore, `L4-funzionale.md`, sezione
"Altre osservazioni minori"). Con `hvac_action` presente ma non tradotto in
una frase onesta, il difetto sarebbe rimasto a metà chiuso: il modello legge
la prima frase disponibile, e se quella dice ancora «heat» il resto del
dizionario non lo salva.

---

## Cosa ho cambiato

**`hiris/app/proxy/entity_cache.py`** — solo il commento sopra la riga del
meteo, che affermava un fatto falso («senza questa riga `guarda` su
un'entità `weather` rispondeva "sereno" e basta»): quella riga non è mai
arrivata a `guarda` fino a questa fetta, il difetto vero era un anello più
in là. Riscritto per descrivere il mondo di dopo.

**`hiris/app/casa/anagrafe.py`**
- `specchio_vivo` restituisce ora **sei** dizionari, non cinque:
  `(stato, nomi, unita, classi, da_quando, attributi)`. `attributi` è
  `entity_id -> e.get("attributes")`, saltando i dizionari vuoti — la stessa
  disciplina degli altri campi ("un dizionario vuoto non è un'assenza di
  attributi dichiarata, è rumore").
- `traduci_stato` guadagna due parametri opzionali, `dominio` e
  `hvac_action`, e per `dominio == "climate"` delega a
  `_stato_leggibile_climate`: separa l'IMPOSTAZIONE (`hvac_mode`, il valore
  di `stato`) dal FUNZIONAMENTO (`hvac_action`). Un termostato impostato su
  riscaldamento e fermo diventa `"impostato su riscaldamento, fermo"`; se
  sta scaldando, `"impostato su riscaldamento, sta scaldando"`; senza
  `hvac_action` noto, `"impostato su riscaldamento"` — dichiara solo ciò
  che si sa davvero, non inventa né "fermo" né "sta scaldando". Nessun
  chiamante esistente si rompe: i due parametri sono opzionali e il nucleo
  (che chiama `traduci_stato(valore, classe)` senza di loro) si comporta
  come prima — e non ne aveva comunque bisogno, vedi sotto.

**`hiris/app/casa/domande.py`**
- `_arricchisci_entita` guadagna `attributi_vivi` e lo usa per calcolare uno
  `stato_leggibile` onesto **su ogni ramo che elenca entità** (area,
  dispositivo, entità singola): `stato_leggibile` era già un campo
  presente ovunque, e per un termostato mentiva ovunque allo stesso modo —
  correggerlo in un solo ramo avrebbe lasciato la stessa domanda con due
  risposte diverse a seconda della porta (fondamenta 3).
- `_guarda_entita` è l'**unico** ramo che allega anche il dizionario
  `attributi` grezzo per intero (`dettaglio["attributi"] = ...`), dopo aver
  chiamato `_arricchisci_entita`. `_guarda_area` e `_guarda_dispositivo`
  ricevono `attributi_vivi` (serve loro per lo `stato_leggibile` onesto) ma
  non lo copiano mai nell'output di lista.
- `guarda()` guadagna il parametro `attributi_vivi` e lo inoltra ai tre rami.

**`hiris/app/casa/strumenti.py`** — `_specchio()` ritorna ora una 7-tupla
(`..., attributi, letto`), e il ramo `_guarda` passa `attributi_vivi` a
`guarda()`. I due chiamanti che non usano gli attributi (`_cerca`,
`_ricorda`) aggiungono solo il placeholder di scarto nell'unpack.

**`hiris/app/api/handlers_casa.py`** e **`handlers_memoria.py`** — solo
l'unpack aggiornato alla nuova arietà di `specchio_vivo`; né il digesto
(`GET /api/nucleo`) né la pagina dei ricordi leggono `attributi_vivi`, per
scelta (vedi sotto).

---

## Decisione 1 — il confine liste/dettaglio

**Il blob `attributi` grezzo esce SOLO da `guarda("entita", ...)`, mai dalle
liste di `guarda("area", ...)` e `guarda("dispositivo", ...)`.** Un'area
può elencare venti entità: mettere dentro ognuna anche `hvac_mode`,
`current_temperature`, `preset_mode` eccetera gonfierebbe la risposta di un
dato che nessuno ha chiesto per la singola cosa — il modello ha chiesto
"cosa c'è in camera", non "dammi ogni attributo di ogni entità di
camera". Il dettaglio di UNA entità è il momento in cui il modello ha già
ristretto la domanda a quella cosa precisa, ed è lì che l'informazione si
paga.

Il confine però NON si applica a `stato_leggibile`: quel campo esisteva
già su ogni ramo (non è un dato nuovo che aggiungo alle liste), e per un
termostato era falso ovunque allo stesso modo. Confinare la correzione al
solo dettaglio avrebbe lasciato `guarda("area", "camera")` rispondere
ancora `stato_leggibile: "heat"` per lo stesso termostato che
`guarda("entita", ...)` descrive onestamente — la stessa domanda con due
risposte diverse a seconda della porta, esattamente il difetto che le
fondamenta del progetto vietano. Per questo `_arricchisci_entita` riceve
`attributi_vivi` su tutti e tre i rami (lo usa solo per leggere
`hvac_action`, un valore, non per esporre il dizionario intero), mentre
solo `_guarda_entita` lo ripropone come chiave a sé. Ho verificato questa
scelta con due test che si controllano a vicenda
(`test_f_un_area_NON_porta_gli_attributi_di_ogni_entita` e
`test_g_un_area_porta_comunque_lo_stato_leggibile_onesto`): il primo
cadrebbe se qualcuno esponesse il blob anche lì, il secondo se qualcuno
"risolvesse" il primo semplicemente non passando `attributi_vivi` affatto.

## Decisione 2 — la forma dello stato leggibile

`"impostato su {modo}, {azione}"` quando `hvac_action` è noto e diverso da
"spento" (`"impostato su riscaldamento, fermo"`, `"impostato su
riscaldamento, sta scaldando"`); `"impostato su {modo}"` quando
`hvac_action` non è disponibile; `"spento"` nudo quando il modo è `off`
(coerente con `_TRADUZIONE_STATO["off"] == "spento"` per tutti gli altri
domini). Ho scelto "impostato su" come prefisso esplicito invece di, per
esempio, tradurre solo il modo e lasciare l'azione a un campo separato:
**la prima frase è quella che il modello legge**, ed è quella che nella
chat vera ha portato alla risposta sbagliata — doveva bastare da sola a non
suggerire un funzionamento non confermato. "Fermo"/"sta scaldando" e non,
per esempio, "non sta scaldando"/"sta scaldando": `hvac_action` ha più di
due valori (`idle`, `heating`, `cooling`, `drying`, `fan`, `preheating`,
`off`), e una traduzione binaria avrebbe perso l'informazione che un
deumidificatore o un ventilatore stanno facendo qualcos'altro.

Il caso "senza `hvac_action`" (integrazione che non lo manda) resta
volutamente parziale — "impostato su riscaldamento" e basta — invece di
dedurre un funzionamento dal confronto fra temperatura reale e target:
dedurlo sarebbe stata un'interpretazione di HIRIS spacciata per un fatto di
Home Assistant, la stessa categoria di errore che ha generato il bug.

## Perché il nucleo resta invariato

Decisione del proprietario, verificata prima di applicarla: `climate` non
entra mai in "Notevole adesso" (`nucleo.py::_e_un_evento`, dominio non
presente in `_DOMINI_EVENTO`), quindi `traduci_stato` per un termostato non
viene mai chiamato dal digesto in pratica — passargli `dominio`/
`hvac_action` sarebbe stato un parametro morto. La firma resta comunque
retrocompatibile (entrambi opzionali, default `None`) nel caso quella
condizione cambi in futuro.

---

## Test

`tests/test_attributi_al_modello.py`, 9 test, pinnano la catena intera con
il caso vero (`hvac_mode: heat`, `hvac_action: idle`, temperatura 25.2,
target 17) da `_to_minimal` fino a `guarda`: contro il codice pre-fix 8 dei
9 cadono (l'unico che passa già verifica solo `_to_minimal`, che non era
mai stato il problema). Inclusi: la prova per mutazione che uno
`stato_leggibile` hardcoded a "fermo" non basterebbe (serve leggere
`hvac_action` davvero, verificato con `hvac_action: heating`), il confine
liste/dettaglio nei due sensi, e il comportamento senza `attributi_vivi`
(retrocompatibile, non torna "heat" nudo).

Aggiornati per la nuova arietà di `specchio_vivo`/`_specchio()` (5→6 e
6→7 valori): `tests/test_classe_viva.py`, `tests/test_da_quando.py`,
`tests/test_strumenti_conoscenza.py`. In `test_classe_viva.py` ho anche
corretto il docstring di `test_lo_specchio_tiene_gli_attributi_del_meteo`,
che affermava lo stesso tipo di cosa falsa del commento in
`entity_cache.py` ("guarda su un'entità weather rispondeva sereno e
basta") pur testando solo `_to_minimal` — non l'ho toccato perché il
compito lo richiedesse esplicitamente, ma perché l'ho trovato riscrivendo
il commento gemello, e lasciarlo così avrebbe significato lasciare in piedi
esattamente il difetto che questa fetta chiude altrove.

Suite intera: **2559 passed, 1 skipped, 0 failed** (base 2550 passed, 1
skipped — la differenza sono i 9 test nuovi).

---

## Dubbi per il coordinatore

- **`preset_mode` e le altre chiavi di `_DOMAIN_ATTRS` non tradotte**: il
  blob `attributi` esce grezzo (inglese, valori enum di Home Assistant) sul
  dettaglio di un'entità. È coerente con come escono già `hvac_mode`
  eccetera prima di questa fetta (mai tradotti, solo mai arrivati), ma se il
  proprietario si aspetta che ANCHE i valori dentro `attributi` diventino
  italiano leggibile (`preset_mode: "home"` → "in casa"), quella è una
  fetta diversa: qui ho tradotto solo `stato_leggibile`, il campo che ha
  causato l'incidente, non l'intero dizionario.
- **Non ho toccato `nucleo.py`** per scelta esplicita del proprietario
  (paragrafo sopra), ma se in futuro `_DOMINI_EVENTO` guadagnasse `climate`
  (un termostato che passa a "sta scaldando" potrebbe legittimamente
  meritare una riga in "Notevole adesso"), la chiamata a `traduci_stato` a
  riga ~758 di `nucleo.py` andrebbe aggiornata a passare `dominio_di(...)`
  e l'`hvac_action` — la firma è già pronta a riceverli.
- **Il meteo (`weather`) e gli altri domini di `_DOMAIN_ATTRS`** (luce,
  tapparella, media_player, aspirapolvere, boiler, valvola) ora escono tutti
  dal dettaglio di `guarda("entita", ...)`, non solo il clima: era la stessa
  causa (lo stesso `specchio_vivo` che buttava `attributes` per intero), e
  il rimedio è per costruzione lo stesso per ogni dominio della tabella.
  Non ho scritto un test dedicato per ciascuno (il meteo lo copre
  indirettamente `test_classe_viva.py`, gli altri restano provati solo a
  livello di `_to_minimal`) — se serve la stessa garanzia end-to-end anche
  per loro, è un'estensione naturale di `test_attributi_al_modello.py`.
