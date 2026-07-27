# North-Star — Brain, Chatbot, Agentbot: entità AI e configurazione unificata

**Data:** 2026-07-27 · Repo: `hiris` · Documento **north-star** (visione + architettura + roadmap). I singoli sotto-progetti avranno spec/piano propri.

## Visione

HIRIS diventa un'app con un **fulcro**: il **Brain**, un cervello che ragiona ed
**evolve da solo** — osserva la casa, traccia le abitudini, e **propone**
soluzioni (nuovi Agentbot, automazioni HA, evoluzioni, modifiche di
configurazione di HA o di HIRIS stesso). Preferisce **segnalare un problema e
chiedere l'intervento** proponendo la soluzione, più che agire di testa propria.
Attorno al Brain vivono due tipi di entità AI, con nomi chiari e comportamento
inequivocabile.

Target utente: **prosumer Home Assistant**, con **disclosure progressiva**
(default semplici e chiari; controllo granulare in una sezione "Avanzate").

## Le tre entità (naming DEFINITIVO)

| Entità | Cosa fa | Come ragiona | Creazione |
|---|---|---|---|
| **Chatbot** | Conversa: **chiedi → risponde**. | Prompt libero (persona/verticalità); può usare i tool HA (letture libere, azioni gated dal semaforo). | **Utente** (persona/prompt specifico) |
| **Agentbot** | **Autonomo**: agisce/segnala **da solo**, senza che tu chieda. | Contratto a **verdetto** (JSON) su trigger; azione dichiarata. **Niente tool liberi** (pilastro di sicurezza). | **Brain propone** + **Utente** a mano |
| **Brain** | Fulcro: ragiona, traccia abitudini, **propone** (Agentbot / automazioni HA / config HA·HIRIS / evoluzioni), supervisiona la casa. | Ragionamento proattivo (oggi sentinella/holistic). | — (è il core) |

Rename da fare ovunque (codice/API/UI/docs): oggi "agente"=chat, "lente"=proattivo
→ **Chatbot**=chat, **Agentbot**=proattivo, **Brain**=cervello. (Chiude il debito
di naming emerso nell'analisi Agenti-vs-Lenti e nella mappa config; vedi
`docs/design/2026-07-27-analisi-agenti-vs-lenti.md` e
`docs/design/2026-07-27-mappa-config-agenti-lenti.md`.)

## Cosa condividono vs cosa resta distinto (dalla mappa config)

**Condiviso (cornice comune di config):** identità/attivo · **layer Modelli +
consumo** · selettore di **ambito** (entità/aree) · scala di **autonomia**
(conferma ↔ tier semaforo) · **accesso knowledge** · **osservabilità**.

**Distinto (il cuore):** contratto prompt (**conversazione** vs **verdetto JSON
senza tool** — sicurezza) · **trigger** (cron/interval/evento) vs **sessione
chat** · azione **dichiarata** vs **tool liberi**.

## Layer Modelli & Provider (condiviso)

Provider oggi supportati (via `LLMRouter`): **Claude API, OpenAI API, OpenRouter,
Ollama/locale**; più l'**Abbonamento** (Claude Max via runner in-addon — oggi
solo chat, v0.99.3).

Ridisegno con disclosure progressiva:
- **Semplice:** attivi i provider con un **toggle** (incluso Abbonamento). Con un
  solo provider → tutto `auto`. **Abbonamento attivo → Chatbot + Brain lo usano**
  (un toggle chiaro, che sostituisce i flag criptici `bridge_enabled` +
  `chat_via_subscription`).
- **Avanzate:** assegnazione **per-funzione** e override **per-Chatbot /
  per-Agentbot** (oggi il modello per-Agentbot **non esiste** ed è nascosto in un
  `AUTO_MODEL_MAP` — va reso visibile), + ordine di **failover**. Una **sola
  catena modello per entità** (basta la doppia `chat_policy`/`automatic_policy`
  per lo stesso agente).

Gli **embeddings** (RAG/memoria) restano un binario **separato** (l'abbonamento
non li fa) — dichiararlo esplicitamente nell'UI.

## Il Brain come fulcro (la home)

Vista centrale dell'app:
- **Stream dei ragionamenti** in chiaro (cosa osserva, cosa deduce) — trasparenza.
- **Abitudini** tracciate della casa/persone.
- **Feed proposte:** nuovi Agentbot / automazioni HA / modifiche config HA·HIRIS /
  evoluzioni — ognuna con **motivazione**, con **approva/rifiuta**.
- **Segnala-e-chiedi:** il Brain flagga un problema e propone la soluzione,
  chiedendo il tuo intervento (invece di agire).
- **Supervisione casa:** cosa è attivo, cosa sta succedendo.

Molto poggia su pezzi esistenti (ragionamento sentinella, proposte automazioni,
storico/second-brain): la mossa è **consolidarli** sotto il Brain.

## Creazione entità: duale

- **Brain propone** → utente **approva** → nasce un Agentbot (o si applica
  un'automazione/config).
- **Utente crea a mano:** Chatbot (persona/verticalità/prompt) e Agentbot.

Entrambi i percorsi passano dalla **stessa cornice di config** (coerenza).

## Cosa raddrizziamo (punti confusi dalla mappa)

- Modello per-Agentbot **visibile** (oggi assente/nascosto).
- **Una** catena modello per entità (no chat-vs-automatic doppia).
- Flag criptici → **toggle chiari** (abbonamento first-class).
- **Rename** Chatbot/Agentbot/Brain ovunque + `PRODUCT.md` (che descrive ancora
  trigger/agenti autonomi ritirati).
- **Osservabilità:** "perché questo Agentbot non è scattato" (cooldown/cap/
  condizione oggi invisibili) + copy stantia.
- Superficie **frammentata** (≥5 posti) → consolidata.

## Non-goal / vincoli

- **Semaforo invariato** come gate delle azioni; il contratto Agentbot
  **verdetto-JSON-senza-tool** resta (sicurezza) — non si unifica col Chatbot.
- Target **prosumer**: default semplici, granularità in "Avanzate" (non nascondere
  tutto, non esporre tutto).
- Nessuna esposizione pubblica nuova; embeddings fuori scope del layer modelli-chat.

## Roadmap (sotto-progetti, ognuno spec→piano→build)

- **SP-1 — Fondazione nomi & concetti:** rename Chatbot/Agentbot/Brain in
  codice/API/UI/docs + `PRODUCT.md`. Sblocca il resto (linguaggio comune).
- **SP-2 — Layer Modelli:** attivazione provider + **abbonamento first-class** +
  modello per-entità visibile + una catena per entità. *(Nota: estendere
  l'abbonamento al Brain/Agentbot esiste già via bridge — va reso un toggle
  chiaro.)*
- **SP-3 — Brain come fulcro (v1):** home del Brain — stream ragionamenti + feed
  proposte (approva/rifiuta) + segnala-e-chiedi. Consolida sentinella+proposte+storico.
- **SP-4 — Config entità unificata:** cornice comune Chatbot/Agentbot con
  disclosure progressiva + creazione manuale coerente.
- **SP-5 — Abitudini & osservabilità:** tracciamento abitudini + diagnosi
  "perché non è scattato".

**Ordine consigliato:** SP-1 (fondazione) → SP-2 (modelli) → SP-3 (Brain) →
SP-4 (config) → SP-5 (abitudini/osservabilità). Ogni SP è indipendente e
rilasciabile.
