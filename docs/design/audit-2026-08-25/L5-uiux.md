# L5 — Audit UI/UX — HIRIS 2.0 (v3.12.1)

**Data**: 24 agosto 2026
**Metodo**: browser reale (Playwright, MCP), istanza LOCALE `http://127.0.0.1:8099` collegata alla
casa vera (15 aree, 240 dispositivi, 1224 entità). Autenticazione via header
`X-HIRIS-Internal-Token` impostato con `page.setExtraHTTPHeaders` prima di ogni navigazione.
**Viewport**: Desktop 1440×900, Mobile 390×844 (iPhone 12/13/14 di fascia comune).
**Pagine coperte**: 9/9, tutte via browser (nessuna revisione statica necessaria) —

| # | Pagina | URL |
|---|---|---|
| 1 | Chat | `/` |
| 2 | Cosa HIRIS sa | `/config#/` |
| 3 | Albero della casa | `/config#/albero` |
| 4 | Memoria | `/config#/memoria` |
| 5 | Promesse | `/config#/promesse` |
| 6 | Costruzioni | `/config#/costruzioni` |
| 7 | Impostazioni chat | `/config#/impostazioni` |
| 8 | Consumi | `/config#/usage` |
| 9 | Modelli | `/config#/models` |

Ogni pagina ha almeno uno screenshot desktop e uno mobile in `schermate/`. Per la Chat e per
l'Albero ho aggiunto scatti supplementari (stato d'attesa, errore, tema scuro, menu aperto) perché
lì si giocava il rilievo.

Nota di metodo: la console segnala 6 errori CORS costanti sui font Google — sono un artefatto del
mio harness di test (ho impostato l'header `X-HIRIS-Internal-Token` su *tutte* le richieste della
pagina, incluse quelle cross-origin verso `fonts.gstatic.com`; in uso reale via Ingress quell'header
non parte verso host esterni). Il fallback ai font di sistema funziona e il testo resta leggibile
in ogni schermata — non è un difetto del prodotto, lo dichiaro per trasparenza e lo scarto.

---

## Riepilogo rilievi

| Gravità | Conteggio |
|---|---|
| 🔴 Critical | 2 |
| 🟡 Important | 3 |
| 🔵 Minor | 2 |

---

## 🔴 Critical

### C1 — Sul telefono, «chiudere il menu» a volte ti porta altrove
**Pagina**: Chat · **Viewport**: Mobile (390×844) · **Visto**, non dedotto.

Aprendo il menu ☰ in alto a sinistra, il pannello laterale (`#sidebar`) scorre sopra l'header e
copre esattamente il punto dove stava il bottone hamburger. Il gesto naturale — ritoccare lo stesso
punto per richiudere, come si fa su quasi ogni app — non chiude nulla: sotto quel punto adesso c'è
il link «Configurazione» del pannello stesso (`<a href="config">`), verificato leggendo
`document.elementFromPoint(32, 30)` a menu aperto. Un tocco lì porta l'utente fuori dalla chat e
dentro la sezione di configurazione, senza preavviso.

C'è un modo per chiudere il menu — toccare l'area scura a destra del pannello (l'overlay) — ma
nella UI non esiste alcuna X o icona di chiusura visibile *dentro* il pannello: l'unica via
d'uscita coerente con l'aspettativa (ri-toccare l'icona) è quella che porta fuori strada.

Screenshot: `chat-mobile-sidebar-open.png` (il pannello copre l'hamburger), confrontare con
`chat-mobile-empty.png` (posizione originale del bottone).

**Perché è grave**: è il primo gesto che un utente compie su una superficie che nasce per il
telefono («Retro Panel»-style, dichiarato nel brief), e la conseguenza di un errore di tocco non è
"niente succede" ma "sei altrove". Viola controllo e libertà dell'utente (Nielsen #3) nel punto più
delicato: l'ingresso/uscita dalla navigazione.

**Correzione suggerita**: quando il pannello è aperto, il bottone hamburger dovrebbe restare sopra
(o trasformarsi in una X sempre cliccabile, come fa quasi ogni drawer mobile), oppure va aggiunta
un'icona di chiusura esplicita in cima al pannello stesso.

---

### C2 — L'Albero della casa non si può comprimere, e sul telefono rompe la pagina
**Pagina**: Albero della casa · **Viewport**: Desktop e Mobile · **Visto e misurato**.

La pagina rende **tutta** la gerarchia della casa (15 aree, 1224 entità) con elementi `<details
open>` — ogni piano, ogni area, ogni entità nasce già espansa, senza un «comprimi tutto» né una
ricerca/filtro. Misurato via `document.body.scrollHeight`:

- **Desktop**: 49.282 px di altezza pagina (circa 55 schermate di scroll continuo).
- **Mobile**: 70.154 px (circa 83 schermate).

Su mobile il problema è doppio: gli `id` lunghi delle entità (es.
`(binary_sensor.presence_sensor_fp2_2763_presence_sensor_1)`, 325px di larghezza) non vanno a capo,
e spingono **l'intera pagina** oltre il viewport — `document.documentElement.scrollWidth` risulta
669px su un viewport di 390px. Il risultato è una barra di scorrimento orizzontale sull'intera
pagina (visibile in fondo a `albero-mobile-fold.png`), non solo su un elemento interno: si scorre
in due direzioni per leggere un solo dispositivo.

Ho misurato con `getBoundingClientRect()` gli elementi che sforano il viewport mobile: sono tutti
`<span>` con l'entity_id fra parentesi, 15+ occorrenze solo nella prima schermata.

Screenshot: `albero-desktop-fold.png`, `albero-mobile-fold.png` (nota la barra grigia in basso),
`albero-desktop.png`/`albero-mobile.png` (screenshot fullPage, enormi per costruzione — la prova
visiva della lunghezza).

**Perché è grave**: per una casa con 1224 entità, trovare un singolo dispositivo significa scorrere
per minuti; sul telefono, in più, la pagina si comporta in un modo che nessun'altra pagina del
prodotto mostra (le altre 8 non hanno mai scroll orizzontale) — rompe sia l'usabilità sia la
coerenza. È esattamente la classe di difetto che il brief chiedeva di dare priorità: nasce su
schermo grande, sul telefono si spacca.

**Correzione suggerita**: `<details>` chiusi di default (aprire solo il primo livello, o nessuno);
uno spezzone di ricerca/filtro in cima (il pattern esiste già altrove nel prodotto, vedi Modelli);
e un `overflow-wrap: anywhere` (o `word-break: break-all`) sugli span dell'entity_id, così anche
senza risolvere l'espansione di default il telefono non sforerebbe più in orizzontale.

---

## 🟡 Important

### I1 — La chat non avvisa prima di far scrivere una domanda a vuoto
**Pagina**: Chat · **Viewport**: Desktop e Mobile · **Visto**.

Ho aperto la chat e mandato «Che temperatura fa in soggiorno?». Risposta in ~2 secondi: *"Nessun
provider AI configurato: HIRIS non ha ancora un modello a cui chiedere"*, con istruzioni precise
(dove mettere la chiave, quale pagina aprire, quale bottone premere). Il testo è ottimo — vedi
sotto, fra le cose fatte bene — ma **la schermata di benvenuto non lo dice prima**: i quattro chip
rapidi («Stato casa», «Temperatura camere»…) sono presentati come se fossero tutti utilizzabili
subito, identici a come apparirebbero con la catena configurata.

Confrontare `chat-desktop-empty.png` (nessun indizio) con `chat-desktop-after15s.png` (l'unico
modo per scoprirlo è aver già speso un turno).

**Perché è un problema**: la pagina Modelli (vedi screenshot `models-desktop.png`) dichiara già
esplicitamente in testa *"HIRIS non può ancora rispondere: la catena è vuota"* — l'informazione
esiste ed è pronta. La chat, che il brief stesso definisce «l'unica superficie», non la mostra
finché non hai già tentato e fallito. Viola la visibilità dello stato del sistema (Nielsen #1) sul
punto d'ingresso principale del prodotto.

**Correzione suggerita**: se `GET /api/models/config` (o equivalente) risulta a catena vuota,
mostrarlo in cima alla schermata di benvenuto della chat, non solo dopo il primo turno sprecato.

---

### I2 — L'errore «non posso risponderti» ha lo stesso aspetto di una risposta riuscita
**Pagina**: Chat · **Viewport**: Desktop e Mobile · **Visto**.

Nello stesso scambio di I1: il messaggio di errore compare nella stessa bolla bianca, stesso
bordo, stesso peso del testo, nessuna icona, nessun colore che userebbe la pagina Modelli per lo
stesso fatto (lì l'assenza di provider è in rosso, con un pallino d'errore). In chat, un fallimento
totale — HIRIS non ha proprio potuto chiedere a nessun modello — si presenta visivamente identico a
una risposta normale.

Screenshot: `chat-desktop-after15s.png`, `chat-mobile-error.png`.

**Perché è un problema**: il prodotto dichiara come principio di progetto — riportato nel brief di
questo stesso audit — che *"un elenco vuoto che significa «non ho potuto guardare» non deve
sembrare «non c'è niente»"*. Qui il testo rispetta la lettera del principio (è onesto e preciso),
ma la grafica no: chi legge di fretta, o chi si affida allo screen reader senza ascoltare tutta la
frase, non ha un segnale strutturale («questo non è andato a buon fine») distinto dal contenuto.
È lo scarto fra "il codice lo sa" (il testo lo dice benissimo) e "la grafica lo mostra" — lo stesso
scarto che l'audit dell'11/08 aveva già trovato sui colori di stato (vedi cosa-funziona-bene, quel
rilievo lì è stato corretto: qui è un caso nuovo, sulla bolla di chat).

**Correzione suggerita**: quando il turno termina in un errore non recuperabile (nessun provider,
errore di rete, timeout), la bolla di risposta dovrebbe portare un bordo o un'icona nel tono
`--err`/`--warn` già definito nel design system, coerente con come Modelli e Promesse segnalano già
gli stessi stati.

---

### I3 — Nessun modo di comprimere o cercare nell'Albero (effetto desktop di C2)
**Pagina**: Albero della casa · **Viewport**: Desktop · **Dedotto dal DOM, coerente con lo
screenshot**.

Separo questo dall'urgenza mobile di C2 perché su desktop la pagina non si rompe — scorre soltanto,
per quasi 50.000 pixel, senza un indice, senza un «torna su», senza un modo di restringere la vista
a un'area sola. La sidebar di navigazione della configurazione (Cosa HIRIS sa, Memoria, Promesse…)
resta fissa e visibile, quindi non ci si perde nel prodotto — ma dentro la pagina stessa, con 15
aree e centinaia di entità, non c'è nessun aiuto a orientarsi oltre lo scroll continuo del mouse.

**Correzione suggerita**: la stessa di C2 (chiusura di default + ricerca) risolve anche questo.

---

## 🔵 Minor

### M1 — Due controlli della chat sotto il tocco comodo consigliato
**Pagina**: Chat · **Viewport**: Mobile · **Misurato**: `#theme-toggle` e `#send-btn` sono 36×36px
(bottone Cancella la chat e menu ☰ sono invece a 44×40px, in linea con le linee guida). 36px è
comunque toccabile, ma sotto il minimo di 44×44 spesso citato da Apple HIG/Material — su un
bottone di invio, premuto ad ogni turno, vale la pena portarlo alla stessa misura degli altri.

### M2 — Il font-loading fallisce silenziosamente nei log della console
Non un difetto della UI in sé (vedi nota di metodo in testa al documento), ma segnalo che gli
errori CORS sui font compaiono ad ogni caricamento pagina nella console reale del browser
dell'utente finale se mai quell'header dovesse — per un cambiamento futuro — finire su richieste
cross-origin. Vale la pena un test end-to-end che verifichi che l'header interno resti confinato
alle richieste verso l'add-on stesso.

---

## ✅ Cosa funziona bene

- **Il testo dell'errore «nessun provider»** (I2) è impeccabile nel contenuto: dice cosa manca,
  dove andare, quale bottone premere, per entrambi i piani (abbonamento e a consumo). Non un errore
  generico — un errore che si può risolvere leggendolo una volta sola.
- **«Cosa HIRIS sa»** (`conoscenza-desktop.png`/`conoscenza-mobile.png`) è la pagina più matura del
  prodotto: dichiara esplicitamente cosa ha letto, quando, cosa ignora e perché (*"Di 20 voci HIRIS
  conosce solo il nome, non il corpo"*, *"File non letti, con la ragione"*), mostra perfino il testo
  verbatim che il modello vede a ogni turno. Si riorganizza bene su mobile: le card statistiche
  passano da griglia 4 colonne a colonna singola senza artefatti.
- **Gli stati vuoti di Memoria, Promesse e Costruzioni** sono coerenti fra loro: stessa struttura a
  card numerate (01/02), stesso tono di voce, e ognuno spiega concretamente *come* riempirsi
  (*"quando dici a HIRIS «ricordati che…», comparirà qui"*) invece di un generico "nessun dato".
- **Il correttivo al contrasto del tema chiaro** segnalato nell'audit dell'11/08 (`--text-3` a
  3.67:1, `--warn` a 2.04:1, sotto AA) risulta **corretto**: verificato in
  `hiris/app/static/hiris-theme.css`, dove i nuovi valori oklch sono accompagnati da un commento che
  dichiara esplicitamente il contrasto raggiunto. Non l'ho ricalcolato pixel per pixel, ma il testo
  in ogni screenshot di questo audit resta leggibile con margine, anche nelle sfumature più chiare
  (didascalie, timestamp).
- **Il tema scuro/chiaro** si mantiene coerente attraversando il confine SPA chat↔configurazione
  (localStorage condiviso, nessun flash del tema sbagliato al caricamento) — confrontare
  `chat-desktop-dark.png` e `models-desktop-dark.png`, stessa sessione.
- **La pagina Modelli** comunica con precisione *perché* ogni provider non è in catena («manca la
  chiave», «manca il token», «manca l'indirizzo») invece di un generico «non disponibile» — un buon
  esempio di "aiuta a riconoscere, diagnosticare, recuperare dall'errore" (Nielsen #9), e lo stesso
  linguaggio di stato (righe rosse, sezioni numerate) è già pronto per essere riusato in chat (vedi
  I2).
- **Il layout responsivo della SPA di configurazione** regge bene su 7 pagine su 8 (tutte tranne
  Albero): la sidebar diventa correttamente un pannello a scomparsa, i form si impilano, nessuno
  scroll orizzontale.

---

## File di riferimento

Referto: `C:\Work\Sviluppo\hiris\.superpowers\audit-2026-08-24\L5-uiux.md`
Screenshot: `C:\Work\Sviluppo\hiris\.superpowers\audit-2026-08-24\schermate\` (26 file)
