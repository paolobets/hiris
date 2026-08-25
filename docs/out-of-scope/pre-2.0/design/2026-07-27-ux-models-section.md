# UX Design — Sezione "Modelli" (`#/models`)

**Data:** 2026-07-27 · Repo: `hiris` · Design contract per SP-2 (`docs/design/2026-07-27-spec-SP2-layer-modelli.md`)
Autore: ux-ui-specialist (design pass pre-implementazione, come richiesto dal §4 della spec).

Questo documento è il contratto di design che lo sviluppatore implementa alla lettera per
`hiris/app/static/config/models-route.js` (+ voce nav in `config.html`/nav template). Nessun
codice qui — solo layout, stati dei componenti, copy IT esatta, flussi di interazione,
stati vuoti/errore, accessibilità.

---

## 0. Decisioni chiave (in breve)

1. **Un solo pattern visivo**: riuso di `.section-card` (sc-header/sc-num/sc-title/sc-desc/sc-body)
   già usato in `tpl-agent-editor` — non un pattern nuovo. `#/models` è una pagina "long-form"
   come l'editor Chatbot, non una lista come `#/usage`.
2. **Niente bottone "Salva" globale.** Ogni controllo scrive subito (commit ottimistico
   on-change): toggle di reorder, tendina "modello di default" per-provider, tendina Brain,
   tendina per-Chatbot. Il motivo: i dati sono uno stato di configurazione corrente, non una
   bozza — coerente con la semantica di "riflesso" della sezione (§1 spec) e evita la
   domanda "ho salvato?" su una pagina con controlli eterogenei (alcuni boot-time, alcuni live).
3. **Distinzione boot-time vs live resa visibile con un'etichetta testuale piccola sotto al
   controllo**, non con un modale o un banner invasivo: `riapplicato al riavvio dell'addon`
   in `--text-3`, corsivo, 11px, presente SOLO sui controlli che mappano a `chain_order` e
   `provider_models`. I controlli live (Brain, per-Chatbot, in futuro per-Agentbot) non hanno
   alcuna etichetta — la sua assenza è essa stessa il segnale "questo è già effettivo".
4. **Navigazione:** nuova voce "Modelli" in sidebar, subito dopo "Consumi" e prima di "Task".
   Motivazione: "Consumi" e "Modelli" sono le due pagine "trasversali" (non list-di-entità) —
   una mostra stato/stat aggregati, l'altra configura il layer aggregato. Le pagine per-entità
   (Chatbot, Agentbot) restano raggruppate separatamente.
5. **Ordine catena = solo i provider "usabili"** (attivo + credenziale presente, §1.3 spec) sono
   riordinabili; i provider non usabili non appaiono nella lista di Parte 2 (sarebbe confuso
   riordinare qualcosa che non fa parte del failover). Il `chain_order` persistito include
   comunque tutte le entry note, per non perdere l'ordine relativo quando un provider spento
   torna attivo — vedi §2.4.
6. **Riordino via frecce ↑/↓ (icon-button), non drag-only** — operabile da tastiera, coerente
   col vincolo di accessibilità del brief. Drag opzionale come miglioria progressiva, mai
   l'unico modo.

---

## 1. Navigazione

Nuova voce in `tpl-side-nav`, tra `#/usage` e `#/tasks`:

```html
<a class="nav-item" href="#/models" data-route="models">
  <span class="nav-icon">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
      <rect x="4" y="4" width="16" height="6" rx="1.5"/>
      <rect x="4" y="14" width="16" height="6" rx="1.5"/>
      <circle cx="8" cy="7" r="0.8" fill="currentColor" stroke="none"/>
      <circle cx="8" cy="17" r="0.8" fill="currentColor" stroke="none"/>
    </svg>
  </span>
  <span class="nav-label">Modelli</span>
</a>
```

Nessun `nav-badge` (non c'è un conteggio significativo da mostrare — a differenza di Chatbot/
Proposte/Task). Breadcrumb (`page-chrome`) mostra `casa › Modelli`.

---

## 2. Wireframe ASCII (intera pagina)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ casa › Modelli                                              [☀/🌙]      │  page-chrome
├─────────────────────────────────────────────────────────────────────────┤
│ Modelli                                                                  │  page-title
│ Chi usa cosa: provider attivi, catena automatica e modello per entità.  │  page-subtitle
│                                                                           │
│ ┌─ 01 · Provider attivi ─────────────────────────────────────────────┐  │  section-card
│ │ Riflesso della configurazione dell'add-on. Per attivare/disattivare │  │
│ │ un provider vai su Impostazioni → Add-on → HIRIS → Configurazione.  │  │
│ │                                                                      │  │
│ │  ● Abbonamento (Claude Max)                    Attivo               │  │
│ │  ● Claude API                                   Attivo               │  │
│ │      Modello di default  [ Claude Opus 4.5        ▾ ]               │  │
│ │      riapplicato al riavvio dell'addon                              │  │
│ │  ○ OpenAI                                       Disattivato          │  │
│ │  ● OpenRouter                          ⚠ manca credenziale          │  │
│ │  ● Ollama (locale)                              Attivo               │  │
│ │      Modello: llama3.1:8b (fisso, da config add-on)                 │  │
│ │                                                                      │  │
│ │  ℹ I toggle vivono nella configurazione dell'add-on, non qui.       │  │
│ │    Attivarne uno da lì non riattiva gli altri provider oggi spenti  │  │
│ │    — vanno riattivati singolarmente se ti servono anche loro.       │  │
│ └──────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│ ┌─ 02 · Catena automatica ───────────────────────────────────────────┐  │
│ │ Ordine di failover quando un'entità è in "auto". Preset corrente:    │  │
│ │ Bilanciato. Riordina con le frecce.                                  │  │
│ │                                                                      │  │
│ │  1  Abbonamento (Claude Max)                        [↑] [↓]         │  │
│ │  2  Claude API                                       [↑] [↓]        │  │
│ │  3  Ollama (locale)                                  [↑] [↓]        │  │
│ │                                                                      │  │
│ │  riapplicato al riavvio dell'addon                                  │  │
│ └──────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│ ┌─ 03 · Assegnazione per entità ─────────────────────────────────────┐  │
│ │ Ogni entità usa "auto" (segue la catena) o un modello esplicito.    │  │
│ │                                                                      │  │
│ │  Chatbot                                                             │  │
│ │   Casa           [ auto                    ▾ ]                      │  │
│ │   Notifiche       [ Claude Opus 4.5          ▾ ]                     │  │
│ │   Turno notte      [ auto                    ▾ ]                     │  │
│ │                                                                      │  │
│ │  Brain                                                               │  │
│ │   Ragionamento core  [ auto                  ▾ ]                     │  │
│ │                                                                      │  │
│ │  Agentbot                                                            │  │
│ │   ℹ Il modello per singolo Agentbot si imposta nel suo editor.      │  │
│ │     Vai a Agentbot →                                                │  │
│ └──────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│ ┌─ 04 · Embeddings ───────────────────────────────────────────────────┐  │
│ │ Usati per RAG e memoria semantica — non fanno parte della catena     │  │
│ │ sopra e non sono assegnabili per entità.                             │  │
│ │                                                                      │  │
│ │  Provider: Ollama locale · Modello: nomic-embed-text                │  │
│ │  ℹ L'Abbonamento non fa embeddings.                                 │  │
│ └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

Nessun `anchor-nav` (rail indice a destra): a differenza dell'editor Chatbot (8 sezioni,
form lungo), qui sono solo 4 sezioni sempre visibili senza scroll eccessivo — l'indice
aggiungerebbe rumore senza valore di navigazione. Se in futuro si aggiungono sezioni,
riconsiderare.

---

## 3. Parte 1 — Provider attivi

### 3.1 Markup concettuale

`section-card` #1, `sc-num="01"`, `sc-title="Provider attivi"`.
`sc-desc`: **"Riflesso della configurazione dell'add-on. Per attivare o disattivare un
provider vai su **Impostazioni → Add-on → HIRIS → Configurazione**."**

Corpo: lista `.dash-list`-like (riuso pattern `dl-row`), una riga per provider, ordine fisso
(non l'ordine di catena): Abbonamento, Claude API, OpenAI, OpenRouter, Ollama — sempre in
quest'ordine, attivi o no, così la lista non "salta" quando lo stato cambia.

### 3.2 Riga provider — stati

Ogni riga ha: pallino di stato + label provider + badge di stato a destra. Se il provider è
attivo **e** ha una lista modelli non vuota (Claude/OpenAI/OpenRouter), sotto la riga compare
il picker "Modello di default" indentato.

| Stato | Pallino | Badge destra | Riga extra |
|---|---|---|---|
| Attivo, con credenziale, con modelli selezionabili | `●` verde (`--ok`) | `Attivo` (testo, `--ok`) | picker "Modello di default" + hint boot-time |
| Attivo, con credenziale, modello fisso (Ollama) | `●` verde | `Attivo` | riga statica: `Modello: <local_model.model> (fisso, da config add-on)` |
| Attivo, **manca credenziale** | `●` ambra (`--warn`) | `⚠ manca credenziale` (badge `--warn`/`--warn-tint`) | nessun picker (disabilitato); riga hint: `Aggiungi la chiave in Configurazione add-on per attivarlo davvero.` |
| Disattivato (`provider_X=false`) | `○` grigio (`--text-4`) | `Disattivato` (testo, `--text-3`) | nessuna riga extra |

Il colore non è mai l'unico segnale: pallino + testo badge sempre presenti insieme (WCAG
1.4.1, no color-only).

### 3.3 Picker "Modello di default" (§3.2b spec)

- `<label>` esplicita `Modello di default` legata via `for`/`id` al `<select>`.
- Opzioni = `providers[].models` del provider (da `GET /api/models`), etichette leggibili
  (es. `Claude Opus 4.5`, `Claude Sonnet 4.5`, `Claude Haiku 4.5` — non l'id tecnico grezzo se
  esiste un mapping label già nel backend; altrimenti l'id tecnico come fallback, es. `gpt-4.1`).
- Nessuna opzione "auto" qui: questo È il default che "auto" userà per quel provider — un
  "auto" ricorsivo non avrebbe senso in questo contesto.
- Valore iniziale = `provider_models[provider]` da `GET /api/models/config`; se vuoto/assente,
  mostrare il primo modello della lista come **placeholder disabilitato** `(usa il default
  interno)` senza forzare una scelta — selezionarne uno esplicitamente è opzionale.
- Sotto il picker: hint `riapplicato al riavvio dell'addon` (`--text-3`, 11px, corsivo).

### 3.4 Callout finale (nota toggle)

Box informativo a fondo sezione (stile "hint" pacato, non un alert rosso — è un chiarimento,
non un errore):

> **ℹ I toggle vivono nella configurazione dell'add-on, non qui.** Attivarne uno da lì non
> riattiva automaticamente gli altri provider oggi spenti — vanno riattivati singolarmente
> se ti servono anche loro attivi in parallelo.

### 3.5 Stati vuoto/errore

- **Nessun provider attivo** (tutti `○`): sotto la lista, banner:
  `Nessun provider attivo. HIRIS non può rispondere finché non ne attivi almeno uno nella
  configurazione dell'add-on.` — stile `.proposals-error`-like ma in `--warn` non `--err`
  (non è un errore di sistema, è uno stato di setup incompleto).
- **`GET /api/models` fallisce**: l'intera sezione mostra
  `Errore caricamento provider. [Riprova]` (bottone `.btn-ghost` piccolo che rilancia il fetch),
  stile analogo a `.proposals-error` di `usage-route.js`.

---

## 4. Parte 2 — Catena automatica

`section-card` #2, `sc-num="02"`, `sc-title="Catena automatica"`.
`sc-desc`: **"Ordine di failover quando un'entità è in 'auto'. Preset corrente: **{label
llm_strategy}**. Riordina con le frecce."**

Mappa label preset (`llm_strategy` → IT):
- `balanced` → **Bilanciato**
- `cost_first` → **Risparmio**
- `quality_first` → **Qualità massima**

### 4.1 Contenuto lista

Solo i provider **usabili** (attivo + credenziale, dalla stessa fonte di Parte 1), in ordine
di `chain_order` filtrato. Ogni riga: numero progressivo, label provider, due icon-button
`↑`/`↓`.

```html
<div class="chain-row" role="listitem">
  <span class="chain-num">1</span>
  <span class="chain-label">Abbonamento (Claude Max)</span>
  <button class="btn-icon-only" aria-label="Sposta su" disabled>...</button>
  <button class="btn-icon-only" aria-label="Sposta giù">...</button>
</div>
```

- Riga 1: `↑` sempre `disabled` (già in cima). Ultima riga: `↓` sempre `disabled`.
- `aria-label` include l'azione E il contesto: `Sposta "Claude API" su, posizione 2 di 3`
  (aggiornato dinamicamente) così uno screen reader annuncia l'effetto, non solo l'icona.
- Click `↑`/`↓` → swap ottimistico in UI, poi `PUT /api/models/config` con `chain_order`
  aggiornato (§5.1). Se il PUT fallisce, l'ordine torna indietro e appare un toast d'errore
  (§7).
- Sotto la lista: hint `riapplicato al riavvio dell'addon`.

### 4.2 Drag opzionale (progressive enhancement)

Se implementato, drag-handle a sinistra del numero, `aria-hidden` (il drag è solo un
acceleratore visivo — le frecce restano il meccanismo primario, sempre presenti e sempre
funzionanti anche con drag attivo). Non bloccare il rilascio della sezione sull'assenza del
drag: le frecce da sole soddisfano il requisito.

### 4.3 Persistenza dell'ordine per provider non-usabili (nota per lo sviluppatore)

`chain_order` persistito lato server può contenere provider che oggi non sono usabili (es.
`openrouter` con credenziale mancante). La UI **non li mostra** in Parte 2, ma quando invia
il `PUT`, deve ricostruire l'array completo: [nuovo ordine dei provider mostrati] +
[eventuali provider non mostrati, in coda, nel loro ordine relativo precedente] — così se
`openrouter` diventa usabile in futuro non "salta" in cima per un bug di troncamento lato
client.

### 4.4 Stati vuoto/errore

- **0 o 1 provider usabile**: nessun riordino ha senso. Mostrare la singola riga (se 1) senza
  frecce, o testo: `Nessun provider attivo e con credenziale — attivane almeno uno in Parte 1
  per definire una catena.` (0 provider). Le frecce non compaiono affatto (non "disabled",
  proprio assenti) quando c'è una sola riga o zero righe, per non suggerire un'azione
  possibile che non lo è.
- **Errore PUT reorder**: rollback visivo + toast `Errore salvataggio ordine. Riprova.`

---

## 5. Parte 3 — Assegnazione per entità

`section-card` #3, `sc-num="03"`, `sc-title="Assegnazione per entità"`.
`sc-desc`: **"Ogni entità usa 'auto' (segue la catena) o un modello esplicito."**

Tre `field-group` interni, separati da `border-top: 1px dashed` (pattern già in CSS):
**Chatbot**, **Brain**, **Agentbot**.

### 5.1 Chatbot (lista)

Una riga per Chatbot esistente (da `GET /api/agents`, stesso endpoint di `usage-route.js`),
ordinata come la lista Chatbot standard (abilitati prima, poi alfabetico — riuso criterio già
in `usage-route.js`).

```html
<div class="field" data-agent-id="...">
  <label for="model-agent-<id>">{nome Chatbot}</label>
  <select id="model-agent-<id>">
    <option value="auto">auto</option>
    <optgroup label="Claude API">
      <option value="claude:opus-4.5">Claude Opus 4.5</option>
      ...
    </optgroup>
    <optgroup label="OpenAI">...</optgroup>
    <optgroup label="OpenRouter">...</optgroup>
    <optgroup label="Ollama">
      <option value="ollama:llama3.1:8b">llama3.1:8b</option>
    </optgroup>
  </select>
</div>
```

Le `<optgroup>` esistono solo per provider **usabili**; un provider spento/senza credenziale
non compare affatto tra le opzioni (niente valori "morti" selezionabili). Se il Chatbot ha
già un `model` esplicito il cui provider è nel frattempo diventato non-usabile, l'opzione
corrente resta selezionata e visibile (per non perdere silenziosamente la scelta salvata) ma
con etichetta `{modello} (provider non attivo)` — segnalazione visiva, nessuna azione forzata.

**On change** → `PUT /api/agents/{id} {model: <valore>}` (endpoint già esistente per il
Chatbot, non `/api/models/config`). Nessun hint boot-time: è live.

### 5.2 Brain (singolo)

```html
<div class="field">
  <label for="model-brain">Ragionamento core</label>
  <select id="model-brain">... stesse opzioni auto + provider usabili ...</select>
</div>
```

**On change** → `PUT /api/models/config` con `brain_model` aggiornato (stesso oggetto di
Parte 2, vedi §7.2). Nessun hint boot-time: `brain_model` è live per spec.

### 5.3 Agentbot (riga informativa)

Non un controllo — un rimando, perché il campo vive nell'editor Agentbot (`#/sentinel`),
non qui (la novità SP-2 è renderlo scrivibile *là*, non duplicarlo qui):

```html
<div class="field-hint-block">
  <p>Il modello per singolo Agentbot si imposta nel suo editor, non qui.</p>
  <a class="btn btn-ghost btn-sm" href="#/sentinel">Vai a Agentbot →</a>
</div>
```

Facoltativo se il dato è a costo marginale: un contatore statico `{N} Agentbot configurati`
sopra il link (stesso stile `nav-badge`/`st-delta`), utile per contesto ma non essenziale —
non bloccare il rilascio se il conteggio richiede una chiamata API in più che non è già
disponibile altrove nella pagina.

### 5.4 Stati vuoto/errore

- **Nessun Chatbot configurato**: al posto della lista, `Nessun Chatbot configurato.` + link
  `.btn-ghost` a `#/agents` (`Crea il primo Chatbot →`).
- **Errore `PUT /api/agents/{id}`**: la tendina torna al valore precedente, badge d'errore
  inline accanto alla riga (icona `⚠` + tooltip `Salvataggio non riuscito`), non un toast
  globale — l'errore è localizzato alla riga.
- **Errore `PUT /api/models/config` (Brain)**: stesso trattamento localizzato sul field Brain.

---

## 6. Parte 4 — Embeddings

`section-card` #4, `sc-num="04"`, `sc-title="Embeddings"`.
`sc-desc`: **"Usati per RAG e memoria semantica — non fanno parte della catena sopra e non
sono assegnabili per entità."**

Corpo: riga informativa, sola lettura, nessun controllo editabile in SP-2 (spec §3.3: "solo
trasparenza in UI", nessun cambiamento funzionale al binario embeddings):

```
Provider: {embedding_provider}  ·  Modello: {embedding_model}
ℹ L'Abbonamento non fa embeddings.
```

- Se `embedding_provider`/`embedding_model` non configurati: `Non configurato — vedi
  local_model in Configurazione add-on.`
- La nota "l'Abbonamento non fa embeddings" è **sempre visibile**, indipendentemente da quale
  provider sia attivo — è un chiarimento strutturale (spec lo richiede esplicitamente), non
  uno stato condizionale.

**Nota per lo sviluppatore (assunzione da verificare in implementazione):** `embedding_
provider`/`embedding_model` non sono esplicitamente nel payload `GET /api/models` né in
`GET /api/models/config` per come descritti in spec §5. Va aggiunto un campo readonly a uno
dei due GET esistenti (preferibile: `GET /api/models`, dato che è già la fonte "stato
provider") — non introdurre un terzo endpoint per due stringhe statiche.

---

## 7. Flussi di interazione ed API

### 7.1 Mount pagina

1. `GET /api/models` → popola Parte 1 (stato provider, badge credenziale) e le liste modelli
   per i picker di Parte 1/2/3.
2. `GET /api/models/config` → popola Parte 2 (`chain_order`), Parte 3 Brain (`brain_model`),
   Parte 1 picker (`provider_models`).
3. `GET /api/agents` → popola Parte 3 Chatbot (riuso pattern già in `usage-route.js`).
4. Le tre fetch partono in parallelo (nessuna dipende dall'esito dell'altra per il rendering
   iniziale); ogni sezione ha il proprio stato di loading/errore indipendente (skeleton
   `Caricamento…` in `--text-3`, stesso pattern di `usage-per-agent-body`).

### 7.2 Stato locale unico per `/api/models/config`

Il client mantiene in memoria l'oggetto completo `{chain_order, brain_model,
provider_models}` dopo il GET iniziale. **Ogni** interazione che tocca uno di questi tre
campi (reorder frecce, picker default-provider, select Brain) modifica la copia locale e
invia **l'intero oggetto** via `PUT /api/models/config` — mai un PUT parziale. Questo evita
race condition tra controlli diversi che scrivono sullo stesso endpoint e mantiene un'unica
fonte di verità lato client.

Sequenza per singola interazione:
1. Aggiorna UI otticamente (nuovo ordine / nuovo valore selezionato).
2. `PUT /api/models/config` con l'oggetto aggiornato completo.
3. Successo → nessun feedback invasivo: un piccolo check `✓` che appare per 1.2s accanto al
   controllo toccato poi svanisce (stesso "linguaggio" del resto della SPA: silenzioso quando
   tutto va bene).
4. Fallimento → rollback del valore/ordine + badge inline `⚠ Salvataggio non riuscito` sul
   controllo interessato, che rimane visibile finché l'utente non ritenta con successo.

### 7.3 Chatbot per-entità

Ogni tendina Chatbot è indipendente: `PUT /api/agents/{id} {model}` diretto, stesso ciclo
ottimistico di §7.2 ma isolato per riga (un fallimento su un Chatbot non tocca gli altri).

### 7.4 Tabella riepilogo chiamate

| Controllo | Sezione | Endpoint | Verbo | Effetto |
|---|---|---|---|---|
| Picker "Modello di default" per-provider | 1 | `/api/models/config` | `PUT` (oggetto intero) | **boot-time** |
| Frecce riordino catena | 2 | `/api/models/config` | `PUT` (oggetto intero) | **boot-time** |
| Tendina Chatbot | 3 | `/api/agents/{id}` | `PUT` | live |
| Tendina Brain | 3 | `/api/models/config` | `PUT` (oggetto intero) | live |
| Link Agentbot | 3 | — (navigazione a `#/sentinel`) | — | — |
| Riga Embeddings | 4 | sola lettura | — | — |

---

## 8. Boot-time vs live — trattamento esplicito

Questo è il punto UX più delicato della sezione: due controlli identici nell'aspetto
(entrambi `<select>`) hanno tempistiche di effetto diverse, e l'utente non deve scoprirlo
per errore ("ho cambiato il modello ma la chat risponde ancora con l'altro").

**Regola di rendering:** ogni controllo boot-time (picker default-provider di Parte 1,
riordino di Parte 2) porta **sempre** sotto di sé la riga:

```
riapplicato al riavvio dell'addon
```

— `font-size: 11px`, `color: var(--text-3)`, `font-style: italic`, nessuna icona (per non
sembrare un warning: è un'informazione neutra, non un problema). I controlli live (Brain,
per-Chatbot) **non hanno questa riga, in nessuno stato** — l'assenza è il segnale.

Non usare un tooltip `title="..."` come unico veicolo di questa informazione: non è
scopribile su touch e non è letto di default dagli screen reader senza interazione
aggiuntiva. Il testo deve essere sempre nel DOM, visibile.

**Non serve** un banner globale "riavvia l'addon per applicare" in cima alla pagina: creerebbe
ansia da azione pendente su una sezione dove la maggior parte dei controlli è invece già
effettiva. La granularità per-controllo è più onesta e meno rumorosa.

---

## 9. Accessibilità (WCAG 2.1 AA)

- **Label esplicite**: ogni `<select>`/`<input>` ha un `<label for>` associato (mai solo
  placeholder o testo adiacente non collegato). ID pattern: `model-agent-<id>`,
  `model-brain`, `model-provider-<provider>`.
- **Riordino da tastiera**: le icon-button `↑`/`↓` sono `<button>` reali (mai `<div
  onclick>`), raggiungibili con Tab, attivabili con Invio/Spazio, con `aria-label`
  descrittivo e dinamico (§4.1). Nessuna dipendenza da drag-and-drop per completare l'azione.
- **Stato non solo a colore**: badge "manca credenziale", "Attivo", "Disattivato" sempre
  testo + pallino, mai colore isolato (§3.2).
- **Touch target ≥44×44px** per le icon-button di riordino su `pointer: coarse` (stesso
  pattern già in CSS per `.chip-remove`/`.ai-remove`/`#theme-toggle`, riusare l'idioma
  `@media (pointer: coarse) { min-width:44px; min-height:44px; margin: -Npx -Mpx; }`).
- **Contrasto**: badge ambra (`--warn`/`--warn-tint`) e verde (`--ok`/`--ok-tint`) già
  validati altrove nella SPA (eval-warn/eval-ok) — riusare gli stessi token, non inventarne
  di nuovi con contrasto non verificato.
- **Focus visibile**: i `<select>` ereditano `input:focus { box-shadow: 0 0 0 3px
  var(--accent-tint) }` già globale — nessuna sostituzione necessaria.
- **Annuncio esiti async**: il check `✓`/badge errore inline (§7.2) deve stare in un
  contenitore con `aria-live="polite"` per essere annunciato senza spostare il focus.

---

## 10. Riepilogo copy IT (per riferimento rapido dev)

| Chiave | Testo esatto |
|---|---|
| Titolo pagina | `Modelli` |
| Sottotitolo pagina | `Chi usa cosa: provider attivi, catena automatica e modello per entità.` |
| Titolo sez. 1 | `Provider attivi` |
| Desc sez. 1 | `Riflesso della configurazione dell'add-on. Per attivare o disattivare un provider vai su Impostazioni → Add-on → HIRIS → Configurazione.` |
| Badge attivo | `Attivo` |
| Badge disattivato | `Disattivato` |
| Badge credenziale mancante | `⚠ manca credenziale` |
| Hint credenziale mancante | `Aggiungi la chiave in Configurazione add-on per attivarlo davvero.` |
| Label picker default | `Modello di default` |
| Placeholder picker vuoto | `(usa il default interno)` |
| Riga Ollama fissa | `Modello: {model} (fisso, da config add-on)` |
| Callout toggle | `I toggle vivono nella configurazione dell'add-on, non qui. Attivarne uno da lì non riattiva automaticamente gli altri provider oggi spenti — vanno riattivati singolarmente se ti servono anche loro attivi in parallelo.` |
| Empty provider | `Nessun provider attivo. HIRIS non può rispondere finché non ne attivi almeno uno nella configurazione dell'add-on.` |
| Errore GET provider | `Errore caricamento provider.` + bottone `Riprova` |
| Titolo sez. 2 | `Catena automatica` |
| Desc sez. 2 | `Ordine di failover quando un'entità è in "auto". Preset corrente: {label}. Riordina con le frecce.` |
| Preset label | `Bilanciato` / `Risparmio` / `Qualità massima` |
| Hint boot-time | `riapplicato al riavvio dell'addon` |
| Empty catena (0 usabili) | `Nessun provider attivo e con credenziale — attivane almeno uno in Parte 1 per definire una catena.` |
| Errore reorder | `Errore salvataggio ordine. Riprova.` |
| Titolo sez. 3 | `Assegnazione per entità` |
| Desc sez. 3 | `Ogni entità usa "auto" (segue la catena) o un modello esplicito.` |
| Label gruppo | `Chatbot` / `Brain` / `Agentbot` |
| Label Brain | `Ragionamento core` |
| Etichetta modello provider spento | `{modello} (provider non attivo)` |
| Empty Chatbot | `Nessun Chatbot configurato.` + link `Crea il primo Chatbot →` |
| Rimando Agentbot | `Il modello per singolo Agentbot si imposta nel suo editor, non qui.` + link `Vai a Agentbot →` |
| Badge errore salvataggio riga | `⚠ Salvataggio non riuscito` |
| Titolo sez. 4 | `Embeddings` |
| Desc sez. 4 | `Usati per RAG e memoria semantica — non fanno parte della catena sopra e non sono assegnabili per entità.` |
| Riga embeddings | `Provider: {provider} · Modello: {model}` |
| Embeddings non configurato | `Non configurato — vedi local_model in Configurazione add-on.` |
| Nota abbonamento/embeddings | `L'Abbonamento non fa embeddings.` |

---

## 11. Assunzioni aperte per lo sviluppatore

1. `embedding_provider`/`embedding_model` (Parte 4) non sono esplicitamente nel payload dei
   due GET descritti in spec §5 — va aggiunto un campo readonly, preferibilmente a
   `GET /api/models` (§6).
2. Le **label leggibili** dei modelli (`Claude Opus 4.5` invece di un id tecnico grezzo) sono
   assunte disponibili o facilmente derivabili lato backend; se il backend espone solo id
   grezzi, il fallback è mostrare l'id as-is — non bloccare il rilascio per questo, ma
   segnalarlo come miglioria SP-4 se manca un mapping.
3. Il conteggio "N Agentbot configurati" in Parte 3 (§5.3) è facoltativo/a costo marginale:
   se non c'è già una chiamata disponibile che lo fornisce gratis nella pagina, ometterlo.
