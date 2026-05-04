# HIRIS — Modalità Completamente Locale (Zero Cloud)

> Versione: 0.9.2 · Aggiornato: 2026-05-04

Esegui HIRIS senza dipendenze cloud: tutta l'inferenza AI, gli embedding e i dati rimangono sulla tua rete locale.

---

## Panoramica

HIRIS supporta una modalità di funzionamento completamente offline. Configurato con un'istanza Ollama locale e un provider di embedding locale (model2vec), ogni componente gira sul tuo hardware:

| Componente | Opzione locale |
|-----------|---------------|
| Ragionamento AI (agentic loop) | Ollama |
| Classificazione semantica entità | Ollama (stessa istanza) |
| Embedding Memoria & RAG | model2vec (in-process, senza server) |
| Integrazione Home Assistant | HA WebSocket / REST (sempre locale) |
| Previsioni meteo | Open-Meteo (gratuito, senza chiave API) |

Non sono richieste chiavi API. Nessun dato lascia la tua rete domestica.

---

## Prerequisiti

- **Ollama** installato e raggiungibile dall'add-on HIRIS
  - Ollama deve essere sulla stessa rete locale di Home Assistant (o sullo stesso host)
  - Porta predefinita: `11434`
  - Verifica con: `curl http://<host-ollama>:11434/api/tags`
- **Un modello capace scaricato in Ollama** (vedi [Scegliere un modello](#scegliere-un-modello) qui sotto)
- Add-on HIRIS v0.6.x o successivo

---

## Scegliere un modello

L'agentic loop ha requisiti diversi rispetto a una semplice chat: il modello deve produrre in modo affidabile JSON per le tool call, seguire istruzioni multi-step e mantenere il contesto su più iterazioni.

### Raccomandazione principale — Qwen2.5:27b (24 GB+ VRAM / RAM)

```bash
ollama pull qwen2.5:27b
```

Qwen 2.5 27B è il modello open source più capace per tool use e output strutturato. Gestisce bene l'italiano e ha una finestra di contesto da 128 k token.

| Proprietà | Valore |
|-----------|--------|
| RAM richiesta | ~18 GB (quantizzazione Q4_K_M) |
| Finestra di contesto | 128 k token |
| Affidabilità tool call | Eccellente |
| Italiano | Buono |
| Tok/s (RTX 3090) | ~25 |

### Alternativa — Mistral Small 3.1 (16 GB VRAM / RAM)

```bash
ollama pull mistral-small3.1
```

Mistral Small 3.1 è la scelta migliore se la qualità della lingua italiana è prioritaria e hai meno di 24 GB di GPU/RAM. Ha un ottimo supporto multilingue e segue bene le istruzioni.

| Proprietà | Valore |
|-----------|--------|
| RAM richiesta | ~11 GB (quantizzazione Q4_K_M) |
| Finestra di contesto | 128 k token |
| Affidabilità tool call | Buona |
| Italiano | Eccellente |
| Tok/s (RTX 3090) | ~40 |

### Opzioni più leggere (8 GB VRAM)

Funzionano per compiti semplici, ma l'affidabilità delle tool call degrada su agenti complessi:

- `qwen2.5:7b` — buon compromesso, italiano discreto
- `llama3.2:3b` — molto veloce, capacità di ragionamento limitate

---

## Configurazione

```yaml
# Ollama per l'inferenza AI
local_model:
  url: http://192.168.1.10:11434
  model: qwen2.5:27b            # usato come default quando un agente ha model: auto

# Preferire il provider locale rispetto al cloud quando entrambi sono configurati
llm_strategy: cost_first

# Embedding locale — senza server, si installa correttamente su Alpine
memory:
  embedding_provider: model2vec
  embedding_model: minishlab/potion-base-8M
  rag_k: 5
  retention_days: 90

# Lascia vuoto — non richiesto per la modalità locale
claude_api_key: ""
openai_api_key: ""
```

Con `llm_strategy: cost_first`, quando un agente ha `model: auto` HIRIS instradi verso Ollama prima di provare qualsiasi provider cloud. Se non sono configurate chiavi cloud, Ollama è l'unico backend disponibile e l'instradamento è automatico indipendentemente dalla strategia.

---

## Impostare il modello per agente

Nel designer degli agenti HIRIS (Config UI):

1. Apri un agente (o creane uno nuovo)
2. Nel campo **Modello**, seleziona il modello Ollama dal dropdown — apparirà sotto il gruppo **Ollama** una volta configurato `local_model.url`
3. Salva l'agente

Il dropdown dei modelli viene popolato in tempo reale da `/api/models`, che interroga la tua istanza Ollama per i modelli disponibili. Puoi mescolare provider per agente: assegna un modello capace agli agenti chat per la qualità e un modello più leggero e veloce agli agenti monitor per ridurre la latenza sulle esecuzioni ad alta frequenza.

---

## Prestazioni attese vs Claude

| Aspetto | Claude Sonnet 4.6 | Qwen2.5:27b (locale) | Mistral Small 3.1 (locale) |
|---------|-------------------|---------------------|--------------------------|
| Affidabilità tool call | Eccellente | Buona | Buona |
| Ragionamento complesso | Eccellente | Buono | Discreto |
| Lingua italiana | Eccellente | Buona | Eccellente |
| Latenza (primo token) | 800–1200 ms | 200–600 ms | 150–400 ms |
| Throughput | 60–80 tok/s | 20–30 tok/s (RTX 3090) | 35–50 tok/s (RTX 3090) |
| Costo per esecuzione | ~€0.001–0.01 | Gratuito | Gratuito |
| Finestra di contesto | 200 k | 128 k | 128 k |

I valori di latenza per i modelli locali presuppongono inferenza su GPU dedicata. L'inferenza solo CPU è tipicamente 3–10× più lenta.

---

## Limitazioni note

**Affidabilità JSON tool call:** i modelli locali producono occasionalmente JSON malformato per le tool call, specialmente su modelli più piccoli o task multi-step complessi. HIRIS gestisce questi errori e li restituisce al modello come errore del tool — il loop riprova, ma i task complessi possono richiedere più iterazioni o fallire dopo il limite di 10.

**Saturazione della finestra di contesto:** con `rag_k: 5` e una lunga cronologia delle conversazioni, il contesto effettivo può raggiungere 8–15 k token. I modelli sotto i 14B parametri possono mostrare degradazione della qualità vicino a questo limite.

**Nessun fallback automatico:** se il modello locale non è disponibile (Ollama non raggiungibile), HIRIS non si sposterà automaticamente su un provider cloud a meno che non sia configurato anche `claude_api_key` o `openai_api_key`.

**Classificazione entità:** la Semantic Home Map usa lo stesso modello Ollama per le entità sconosciute. Su modelli più leggeri questo può produrre etichette di qualità inferiore, ma il classificatore basato su regole gestisce la maggior parte dei tipi di entità comuni senza assistenza LLM.
