# HIRIS — Guida alla Configurazione

> Versione: 0.6.12 · Aggiornato: 2026-04-29

Questa guida copre le due aree di configurazione che richiedono una configurazione esterna prima di funzionare:
**Notifiche (Apprise)** e **Memoria & RAG**.
Tutte le altre opzioni (chiavi API, selezione modello, livello log, tema) sono auto-esplicative dall'interfaccia dell'add-on.

---

## Indice

1. [Notifiche (Apprise)](#1-notifiche-apprise)
   - [Come funziona](#come-funziona)
   - [Telegram](#telegram-consigliato)
   - [ntfy (push self-hosted)](#ntfy-push-self-hosted)
   - [Gotify](#gotify)
   - [Email](#email)
   - [Discord](#discord)
   - [WhatsApp (Twilio)](#whatsapp-twilio)
   - [Più canali contemporaneamente](#più-canali-contemporaneamente)
   - [Verificare la configurazione](#verificare-la-configurazione)
2. [Memoria & RAG](#2-memoria--rag)
   - [Come funziona](#come-funziona-1)
   - [Opzione A — Embeddings OpenAI](#opzione-a--embeddings-openai-più-semplice)
   - [Opzione B — Embeddings Ollama (locale, gratuito)](#opzione-b--embeddings-ollama-locale-gratuito)
   - [Opzione C — model2vec (locale, senza server)](#opzione-c--model2vec-locale-senza-server)
   - [Disabilitare il RAG](#disabilitare-il-rag)
   - [Parametri di ottimizzazione](#parametri-di-ottimizzazione)

---

## 1. Notifiche (Apprise)

### Come funziona

HIRIS usa [Apprise](https://github.com/caronc/apprise) per inviare notifiche tramite 80+ servizi.
Configuri uno o più **URL Apprise** nelle impostazioni dell'add-on — ogni URL punta a un canale di consegna.

Quando un agente chiama `send_notification(message, channel="apprise")`, HIRIS invia il messaggio a **tutti gli URL configurati** simultaneamente.

> **Nota:** se `apprise_urls` è vuoto, le notifiche usano il servizio push di Home Assistant (`notify.notify`).

---

### Telegram (consigliato)

Telegram è l'opzione più semplice e affidabile per le notifiche domestiche.

**Passo 1 — Crea un bot**

1. Apri Telegram e avvia una chat con [@BotFather](https://t.me/BotFather)
2. Invia `/newbot` e segui le istruzioni
3. Copia il **Bot Token** (formato: `1234567890:ABCDef-ghijklmno`)

**Passo 2 — Ottieni il tuo Chat ID**

1. Invia qualsiasi messaggio al tuo nuovo bot
2. Visita: `https://api.telegram.org/bot<TUO_TOKEN>/getUpdates`
3. Trova `"chat":{"id": 987654321}` nel JSON — è il tuo **Chat ID**

**Passo 3 — Configura HIRIS**

```yaml
apprise_urls:
  - tgram://1234567890:ABCDef-ghijklmno/987654321
```

Per una **chat di gruppo**, usa il Chat ID del gruppo (numero negativo, es. `-100987654321`):

```yaml
apprise_urls:
  - tgram://1234567890:ABCDef-ghijklmno/-100987654321
```

---

### ntfy (push self-hosted)

[ntfy](https://ntfy.sh) è un servizio di push notification open-source. Puoi usare la versione hosted gratuita o installarlo in autonomia.

**Usando ntfy.sh (hosted, gratuito)**

```yaml
apprise_urls:
  - ntfy://ntfy.sh/mie-notifiche-hiris
```

Sostituisci `mie-notifiche-hiris` con qualsiasi nome topic univoco. Iscriviti allo stesso topic nell'app mobile ntfy.

**Con istanza ntfy self-hosted**

```yaml
apprise_urls:
  - ntfys://ntfy.tuodominio.it/mio-topic
```

Usa `ntfy://` per HTTP o `ntfys://` per HTTPS.

**Con autenticazione**

```yaml
apprise_urls:
  - ntfys://utente:password@ntfy.tuodominio.it/mio-topic
```

---

### Gotify

[Gotify](https://gotify.net) è un server di notifiche self-hosted.

1. Crea un'applicazione nell'interfaccia web di Gotify e copia il **token dell'app**
2. Configura HIRIS:

```yaml
apprise_urls:
  - gotifys://gotify.tuodominio.it/TuoTokenApp
```

Usa `gotify://` per HTTP o `gotifys://` per HTTPS.

---

### Email

**Gmail (con App Password)**

1. Abilita l'autenticazione a 2 fattori sul tuo account Google
2. Genera una [App Password](https://myaccount.google.com/apppasswords) per "Mail"
3. Configura:

```yaml
apprise_urls:
  - mailtos://tuoindirizzo@gmail.com:AppPassword@smtp.gmail.com/destinatario@esempio.com
```

**SMTP generico**

```yaml
apprise_urls:
  - mailtos://utente:password@smtp.tuodominio.it:587/destinatario@esempio.com
```

---

### Discord

1. Nel tuo server Discord: **Impostazioni → Integrazioni → Webhook → Nuovo Webhook**
2. Copia l'URL del webhook (formato: `https://discord.com/api/webhooks/ID/TOKEN`)
3. Configura:

```yaml
apprise_urls:
  - discord://WebhookID/WebhookToken
```

---

### WhatsApp (Twilio)

Richiede un account [Twilio](https://www.twilio.com) con WhatsApp abilitato.

```yaml
apprise_urls:
  - twilio://AccountSID:AuthToken@+1415xxxxxxx/+39333xxxxxxx
```

Dove `+1415xxxxxxx` è il tuo numero WhatsApp Twilio e `+39333xxxxxxx` è il destinatario.

---

### Più canali contemporaneamente

Puoi configurare più canali contemporaneamente — tutti riceveranno ogni notifica:

```yaml
apprise_urls:
  - tgram://BotToken/ChatID
  - ntfys://ntfy.tuodominio.it/hiris
  - mailtos://utente:pass@smtp.tuodominio.it/boss@esempio.com
```

---

### Verificare la configurazione

Dopo aver salvato la configurazione dell'add-on, chiedi a HIRIS in chat:

> "Inviami una notifica di test"

HIRIS chiamerà `send_notification` e dovresti ricevere il messaggio su tutti i canali configurati entro pochi secondi.

Se non arriva nulla, controlla il log dell'add-on (**Supervisor → HIRIS → Log**) per messaggi di errore Apprise.

---

## 2. Memoria & RAG

### Come funziona

HIRIS salva i ricordi delle conversazioni in un database **SQLite** locale (`/config/hiris/memory.db`).
Ogni memoria è salvata come testo insieme a un **vettore embedding** — una rappresentazione numerica del suo significato.

Quando tu o un agente inviate un messaggio, HIRIS automaticamente:
1. Converte il messaggio in un embedding
2. Cerca nel database le **k memorie più simili** (similarità coseno)
3. Inietta le memorie rilevanti nel prompt AI come contesto aggiuntivo

Questo permette a HIRIS di ricordare preferenze, fatti ed eventi passati tra conversazioni separate.

**Senza un provider di embedding configurato**, i tool di memoria (`save_memory`, `recall_memory`) funzionano comunque ma la ricerca semantica è disabilitata — vengono restituiti solo risultati per parola chiave esatta. L'iniezione RAG è effettivamente disattivata.

---

### Opzione A — Embeddings OpenAI (più semplice)

Usa la stessa chiave API OpenAI già configurata per il modello principale.

**Requisiti:** `openai_api_key` deve essere impostata.

**Modello consigliato:** `text-embedding-3-small` — veloce, economico (~$0.02/1M token), ottima qualità.

**Configurazione:**

```yaml
memory:
  embedding_provider: openai
  embedding_model: text-embedding-3-small
  rag_k: 5
  retention_days: 90
```

**Modelli alternativi:**

| Modello | Costo | Note |
|---------|-------|------|
| `text-embedding-3-small` | $0.02/1M token | ✅ Consigliato |
| `text-embedding-3-large` | $0.13/1M token | Qualità superiore, più lento |
| `text-embedding-ada-002` | $0.10/1M token | Legacy, evita per nuove installazioni |

---

### Opzione B — Embeddings Ollama (locale, gratuito)

Esegue gli embeddings interamente sull'hardware locale. Nessun costo API, nessun dato lascia la rete.

**Requisiti:** Ollama deve essere raggiungibile dall'add-on HIRIS (stessa rete).
Deve essere impostato anche `local_model.url` (HIRIS lo riusa come URL base per Ollama).

**Passo 1 — Scarica un modello di embedding in Ollama**

```bash
ollama pull nomic-embed-text
```

Altre buone opzioni:
- `mxbai-embed-large` — qualità superiore, più grande (670 MB)
- `all-minilm` — molto veloce e leggero (23 MB)

**Passo 2 — Configura HIRIS**

```yaml
local_model:
  url: http://192.168.1.10:11434   # il tuo host Ollama
  model: ""                        # opzionale: imposta anche un modello chat locale

memory:
  embedding_provider: ollama
  embedding_model: nomic-embed-text
  rag_k: 5
  retention_days: 90
```

> **Importante:** `local_model.url` è usato sia per i modelli chat Ollama che per gli embeddings Ollama.
> Non è necessario impostare `local_model.model` solo per usare gli embeddings Ollama.

---

### Opzione C — model2vec (locale, senza server)

Esegue gli embedding direttamente in-process senza nessun server, nessuna chiave API e nessuna chiamata esterna.
**Questa è l'opzione locale consigliata per gli add-on Home Assistant** — è l'unica soluzione di embedding completamente locale compatibile con Alpine Linux (la base di tutti gli add-on HA).

**Requisiti:** nessuno — il modello viene scaricato da HuggingFace Hub al primo avvio e messo in cache in `/config/hiris/models/huggingface/`. Gli avvii successivi sono istantanei.

**Primo avvio:** HIRIS scarica il modello (~30 MB per il default). Questo avviene una volta sola.

**Configurazione:**

```yaml
memory:
  embedding_provider: model2vec
  embedding_model: minishlab/potion-base-8M
  rag_k: 5
  retention_days: 90
```

Lascia `embedding_model` vuoto per usare il default (`minishlab/potion-base-8M`) automaticamente.

**Modelli disponibili:**

| Modello | Dimensione | Qualità (MTEB) | Note |
|---------|------------|----------------|------|
| `minishlab/potion-base-8M` | ~30 MB | 51.1 | ✅ Consigliato — veloce e compatto |
| `minishlab/potion-base-32M` | ~120 MB | 52.1 | Qualità superiore, più grande |

> **Nota tecnica:** model2vec usa embedding statici (distillati) implementati in Python puro.
> Tutte le dipendenze (`numpy`, `tokenizers`, `safetensors`) hanno wheel `musllinux_1_2`,
> rendendolo l'unica opzione di embedding locale che funziona sugli add-on HA senza modifiche.

---

### Disabilitare il RAG

Lascia `embedding_provider` vuoto per disabilitare completamente la ricerca semantica nella memoria.
I tool di memoria restano disponibili ma il recupero usa solo corrispondenza per parola chiave.

```yaml
memory:
  embedding_provider: ""
  embedding_model: ""
  rag_k: 5
  retention_days: 90
```

---

### Parametri di ottimizzazione

| Parametro | Default | Guida |
|-----------|---------|-------|
| `rag_k` | 5 | Numero di memorie iniettate per richiesta. Aumenta a 10 per agenti con storia ricca; riduci a 2-3 per risparmiare token. |
| `retention_days` | 90 | Le memorie più vecchie di questo valore vengono eliminate automaticamente alle 03:00 UTC. Imposta 0 per conservare per sempre (sconsigliato — lo store cresce senza limiti). |
| `history_retention_days` | 90 | Conservazione della cronologia messaggi delle conversazioni, indipendente dalle memorie vettoriali. |

**Configurazioni tipiche:**

```yaml
# Uso minimo di token
memory:
  embedding_provider: openai
  embedding_model: text-embedding-3-small
  rag_k: 3
  retention_days: 30

# Contesto ricco per utenti avanzati
memory:
  embedding_provider: openai
  embedding_model: text-embedding-3-large
  rag_k: 10
  retention_days: 365
```
