# Product

## Register

product

## Users

**Primario — il tinkerer Home Assistant.** Adulto tecnico, già padrone di YAML, automazioni, integrazioni HA. Installa HIRIS come add-on, lo apre via Ingress sul desktop (1440px+), passa la maggior parte del tempo nell'**Agent Designer** a comporre agenti, scrivere system prompt, scegliere tool, definire trigger, controllare costi. Vuole controllo, densità, telemetria, niente paternalismo. Sa già cos'è un cron, un MQTT, un token.

**Secondario — chiunque viva nella casa.** Famiglia, ospiti, partner non tecnico. Non aprono mai l'Agent Designer: usano i **chat agent** da una card Lovelace o dal pannello chat di HIRIS. Chiedono in linguaggio naturale, ricevono risposte in linguaggio naturale. La superficie chat deve essere accessibile a tutti senza istruzioni.

**Contesto d'uso:** HA add-on aperto via Ingress, soprattutto da desktop in sessioni di lavoro lunghe (configurazione, debug, eval). La chat anche da mobile / Lovelace card.

## Product Purpose

HIRIS (Home Intelligent Reasoning & Integration System) è un **pannello di configurazione di agenti AI** per Home Assistant. L'utente costruisce un team di agenti specializzati — chat o autonomi, periodici o reattivi o cron-driven — ciascuno con system prompt, tool granted, budget, modello LLM, memoria. Una volta configurati gli agenti girano nel Python flow engine locale e chiamano il provider LLM scelto (Claude / OpenAI / Ollama) solo quando serve ragionare davvero.

Il successo è misurabile: l'utente apre l'Agent Designer, modifica un agente, lo testa nella sandbox, vede il costo e la latenza, lo deploya. La chat viene usata per parlare con i chat agent o per testare agenti autonomi. Niente dashboard di stato della casa, niente cruscotti di metriche: HA fa già quello.

## Brand Personality

**Tre parole:** preciso, tecnico, abitabile.

Il tono è quello dell'**Anthropic Workbench / OpenAI Playground / Claude Console** — uno spazio dove un adulto competente costruisce qualcosa di serio. Mono-leaning per il codice (system prompt, cron, tool refs), sans-serif raffinata per i comandi e le label. Densità informativa alta dove serve (sidebar agenti, telemetria), respiro generoso dove l'utente sta scrivendo (textarea del prompt, sandbox).

La palette esiste già nel repo: **iris** (viola petalo) come accento di brand, neutri tinted al viola in OKLCH, accenti semantici (ok / warn / err) sobri. Theme dual: chiaro per sessioni diurne, scuro per il workbench. Il dark non è un manifesto, è ergonomia.

Niente entusiasmo da SaaS, niente onboarding euforico, niente dashboard "ti mostro la tua casa." HIRIS rispetta il tempo del tinkerer: zero rumore, zero animazioni decorative, tutto ciò che si muove ha un significato (un agente sta girando, un costo sta salendo, un eval è cambiato).

## Anti-references

Cosa HIRIS non deve sembrare:

- **Editoriale / poetico / contemplativo.** Niente serif italic, niente "stanza che respira", niente pagina come carta di lettera. Quel registro è stato testato e rifiutato: HIRIS non è un assistente da accarezzare, è un workbench.
- **Dashboard di stato della casa.** Niente tile "Energia / Clima / Luci", niente metriche live della casa al centro della home. Quello lo fa Home Assistant. HIRIS configura agenti, non rende metriche.
- **SaaS marketing.** Niente hero gradient, niente "big number + small label + supporting stats", niente card grid identiche, niente onboarding in modale. Side-stripe borders vietati.
- **Voice assistant cute.** Niente bolle blu di iMessage, niente avatar tondo che pulsa con onde, niente "iris ti ascolta" con microfono animato. La chat è testo.
- **Generico Home Assistant cards UI.** Coerente con HA in densità e tipografia, ma con un'identità propria (palette iris, tipografia mono per il codice). L'utente deve riconoscere "questo è HIRIS, non un dashboard HA qualunque."

Anti-pattern visivi specifici da bandire (per absolute bans del design system):
- gradient text decorativo
- glassmorphism diffuso
- card identiche in griglia regolare
- modali come prima soluzione

## Design Principles

1. **Configurazione è scrittura.** Il fulcro dell'Agent Designer è il system prompt: textarea grande, monospaziata, con respiro. Tool / trigger / model sono al servizio del prompt, non lo nascondono.

2. **Telemetria dove serve la decisione.** Ogni agente mostra costo / latenza / eval / triggers recenti accanto alla sua configurazione, non in una pagina "Analytics" separata. Il tinkerer decide se cambiare modello o soglia *qui*, mentre edita.

3. **Sandbox è first-class.** Testare un agente è la stessa cosa che editarlo: REPL inline, scenari salvabili, output strutturato. Niente "deploy and pray".

4. **Densità dove c'è competenza, semplicità dove c'è famiglia.** L'Agent Designer è denso, mono, ricco. La chat è larga, sans, calma. Sono due UI diverse dello stesso prodotto, non lo stesso template ripetuto.

5. **Cost transparency permanente.** Il costo cumulativo di oggi e del mese è sempre visibile in alto, in mono, leggibile a colpo d'occhio. Niente sorprese di bolletta.

## Accessibility & Inclusion

- WCAG AA come minimo: contrasti ≥ 4.5:1 per testo body, ≥ 3:1 per UI ed eventuali large text.
- Operazioni full-keyboard: Agent Designer interamente navigabile da tastiera (sidebar, form, REPL). Comando palette `⌘K` per ricerca/azioni.
- Prefers-reduced-motion rispettato: pulse / blink disattivati, transizioni accorciate.
- Chat utilizzabile su mobile / Lovelace card, font ≥ 16px, target tap ≥ 44px.
- Theme dual chiaro/scuro con `prefers-color-scheme` di default; override manuale persistito.
- Niente comunicazione affidata al solo colore (status badge sempre con label testuale, non solo dot colorato).
