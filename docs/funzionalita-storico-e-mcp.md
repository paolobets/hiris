# HIRIS — Storico, MCP e proposte (funzionalità avanzate)

Panoramica delle funzionalità introdotte nelle release 0.15–0.21. Per le basi vedi
`come-funziona.md` e `guida-configurazione.md`; per la sicurezza `sicurezza.md`.

---

## 1. Storico dei dati e analisi (`get_history`)

HIRIS può analizzare l'andamento nel tempo delle entità, non solo lo stato corrente.
Modello **ibrido a tre livelli**, dietro un unico strumento `get_history`:

1. **Recente** — recorder di Home Assistant (ultimi ~10 giorni).
2. **Trend lunghi numerici** — Long-Term Statistics di HA (mesi/anni; temperature,
   umidità, potenza, energia).
3. **Storico proprietario** — un archivio locale di HIRIS (`history.db`) per le
   entità che **scegli tu**, anche oltre la retention di HA.

L'output è sempre **compresso** (medie/min/max/durate giornaliere), così l'AI ragiona
su trend e non su migliaia di punti. Esempi d'uso (chat o Claude): *"andamento
temperatura del salotto nell'ultima settimana"*, *"consumo energia del mese"*,
*"quante ore è stata accesa la pompa"*.

## 2. Storicizzazione (cosa registrare)

In *Configurazione → Storicizzazione* scegli **quali entità** HIRIS conserva nel suo
archivio: per categoria (sensori, presenza, clima, valvole/irrigazione, dispositivi…)
più allowlist/exclude puntuali e la **retention** dei dati grezzi.

- **Opt-in**: di default **nulla** viene storicizzato finché non abiliti tu.
- I dati grezzi sono potati dopo la retention; i **riepiloghi giornalieri** restano
  per sempre (compatti) → analisi a lungo periodo senza far crescere il DB.
- I dati di **presenza/sicurezza** sono privacy-sensibili: puoi escluderli, e nel
  second brain sono marcati `sensitive`.

## 3. Insight settimanali nel "second brain"

Un job notturno distilla lo storico in **insight testuali** salvati nella knowledge
base (es. *"negli ultimi 7 giorni il consumo medio è +12% rispetto alla settimana
precedente"*). Sono **ricercabili** dall'AI (`recall_knowledge`), deterministici e a
costo zero (regole, niente chiamate LLM). Un riepilogo per entità, aggiornato ogni
notte (non si accumula).

## 4. Gateway MCP — Claude pilota HIRIS

Puoi collegare **Claude (claude.ai)** a HIRIS tramite un connettore MCP:
- **Una tantum**: aggiungi il connettore in Claude → *Settings → Connectors* (OAuth +
  Cloudflare Access). Non si ricollega ad ogni chat: al massimo lo **attivi** nella
  conversazione.
- Claude usa gli stessi strumenti curati (stato casa, storico, azioni gated dal
  semaforo, proposte, task). Il gateway include **istruzioni d'uso** e **prompt
  rapidi** ("Briefing casa", "Analisi consumi", "Comfort stanze", "Presenza &
  sicurezza", "Cosa è cambiato").
- Sicurezza: vedi `sicurezza.md` — le azioni passano dal semaforo server-side, l'AI
  non può cambiarsi i permessi.

Vedere anche la lettura della **configurazione di un'automazione** (`get_automation_config`):
HIRIS/Claude può mostrare il YAML di un'automazione **creata da UI** in HA.

## 5. Proposte di automazione (proponi → attiva)

L'AI **non crea** automazioni da sola: le **propone**. Flusso:
1. Chiedi (chat o Claude): *"crea un'automazione che…"* → l'AI salva una **proposta**
   (non passa dal semaforo, è solo una proposta).
2. La trovi in *Configurazione → Proposte* con descrizione e configurazione.
3. Quando **tu** clicchi **Attiva**, HIRIS **scrive davvero** l'automazione in Home
   Assistant (config API + reload). Se HA rifiuta la config, la proposta resta in
   attesa (ritentabile).

> Rivedi sempre la configurazione di una proposta prima di attivarla: una volta
> attiva, è un'automazione HA reale che gira secondo le proprie regole.

## 6. Task pianificati

Via Claude/MCP, i task possono contenere **solo azioni verdi** (vincolati ai domini/
entità verdi del semaforo). L'annullamento di un task (`cancel_task`) richiede
**sempre** la tua conferma. Nella chat HIRIS (assistente fidato) i task non hanno
questa restrizione.
