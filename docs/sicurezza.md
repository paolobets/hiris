# HIRIS — Modello di sicurezza e setup sicuro

Questo documento spiega come HIRIS protegge la tua casa quando colleghi un'AI
(la chat interna o Claude via MCP) al controllo dei dispositivi, e come configurarlo
in modo sicuro. È la lettura consigliata **prima** di esporre il gateway MCP.

## In una frase

HIRIS non si fida dell'AI: ogni **azione** sui dispositivi è autorizzata
**server-side** da un "semaforo" che decidi tu. Le **letture** sono libere, le
**azioni** passano dal semaforo, e l'AI **non può cambiare i propri permessi**.

---

## 1. Il semaforo (traffic-light)

Il semaforo governa **solo le azioni dirette sui dispositivi** (il tool
`call_ha_service`: accendi luce, imposta clima, apri tapparella, …). Le letture
(stato casa, storico, ecc.) sono sempre permesse.

Quattro livelli, impostabili in *Configurazione → Accessi Gateway*:

| Livello | Comportamento |
|---|---|
| 🟢 **Verde** | esegue subito |
| 🟡 **Giallo** | trattiene e invia una **notifica azionabile su iPhone** (Approva/Nega) |
| 🔴 **Rosso** | trattiene; **conferma manuale solo dentro HIRIS** (Approvazioni) |
| ⚪ **Off** | bloccato del tutto |

### Per dominio e per entità
- **Per dominio**: scegli il livello per categoria (Luci, Clima, Serrature, …).
- **Per entità** (avanzato, dal riquadro "Override per entità"): una singola entità
  **batte** il livello del suo dominio. Esempi:
  - dominio *Interruttori* verde, ma `switch.cancello off` → il cancello resta bloccato;
  - dominio *Interruttori* off, ma `switch.lampada_studio green` → solo quella lampada è comandabile.

### Cosa NON aggira il semaforo
- Un'azione **schedulata in un task** può contenere **solo azioni verdi**: non puoi
  usare un task per eseguire al volo un'azione gialla/rossa/off (verificato e blindato).
- Una `call_ha_service` **senza entità target** (broadcast) con whitelist attiva è
  **rifiutata** (niente azioni "a tappeto").
- L'AI **non ha alcuno strumento** per modificare il semaforo, applicare proposte o
  spegnere il kill-switch: quei comandi vivono solo nella UI/pannello, dietro
  autenticazione.

---

## 2. Raccomandazione principale (la difesa più importante)

**Tieni NON-verdi i domini e le entità sensibili.** Anche se una prompt-injection
(es. il nome di un sensore manipolato) convincesse l'AI a tentare un'azione
pericolosa, il semaforo la trattiene se non è verde.

Da tenere **giallo/rosso/off** salvo necessità:
- `lock` (serrature), `alarm_control_panel` (allarme), `cover` (garage/tapparelle
  critiche), `siren`, `valve` (gas/acqua), e qualsiasi `switch`/`script` collegato a
  carichi pericolosi (caldaia, cancello, pompe).

Usa gli **override per-entità** per fare eccezioni mirate (es. dominio off ma una
singola lampada verde) invece di rendere verde un intero dominio eterogeneo.

---

## 3. Il gateway MCP (Claude dal cloud)

Il gateway permette a Claude (claude.ai) di pilotare HIRIS. Punti chiave di sicurezza:
- **Connessione**: OAuth una tantum; l'autorizzazione del connettore è protetta da
  **Cloudflare Access** (policy email). Non si ricollega ad ogni chat.
- **Trasporto**: HIRIS non è esposto sulla LAN; il gateway lo raggiunge via tunnel
  Cloudflare con service token. La porta API HIRIS resta chiusa.
- **Il gateway è un "poliziotto"**: rate-limit + **circuit breaker** (auto-kill se
  un loop impazzisce) + audit con provenienza. **HIRIS è il decisore** (semaforo +
  allowlist server-side).
- **Tetto hard**: l'execute-API di HIRIS può eseguire **solo** un insieme chiuso di
  tool; nessun tool fuori lista è raggiungibile, qualunque cosa sia configurata.
- **Isolamento**: Claude non può leggere/scrivere segreti, cambiare la policy del
  semaforo, né disattivare kill-switch/breaker.

> Nota: le **letture** (stati, storico, config automazioni) vanno comunque al modello
> nel cloud. Non inserire segreti nelle automazioni; ricorda che lo storico di
> presenza/sicurezza è leggibile (puoi escluderlo da *Storicizzazione*).

---

## 4. Proposte e task

- **Automazioni**: l'AI non le crea mai da sola — **propone**. Le trovi in
  *Configurazione → Proposte*; quando **tu** clicchi *Attiva*, HIRIS scrive davvero
  l'automazione in Home Assistant (config API + reload). Rivedi sempre la proposta
  prima di attivarla.
- **Task**: via MCP l'AI può creare task pianificati **solo con azioni verdi**
  (vincolati ai domini/entità verdi). `cancel_task` richiede **sempre** la tua
  conferma (per non disattivare in silenzio un task di sicurezza).

---

## 5. Dati e backup

I dati vivono in `/data` dell'add-on, in DB SQLite separati:
`knowledge.db`, `history.db`, `proposals.db`, `hiris_memory.db`, **`vault.db`**
(contiene segreti dello pseudonimizzatore), `chat`, ecc. Da v0.20.0 i DB usano
**WAL** (resilienza a crash/black-out) e **versioning schema** con migrazioni sicure
sugli aggiornamenti dell'add-on.

**Backup/restore**: gli **snapshot di Home Assistant** includono `/data` → fai
snapshot regolari. Poiché `vault.db` contiene segreti, **proteggi gli snapshot**
(storage cifrato / accesso ristretto). Per ripristinare: ripristina lo snapshot HA;
HIRIS riapre i DB e applica eventuali migrazioni automaticamente.

---

## 6. Checklist "primo avvio sicuro"

1. Imposta un **`internal_token`** robusto nelle opzioni dell'add-on.
2. NON esporre la porta API sulla LAN (`debug_expose_port` off) salvo diagnostica.
3. In *Accessi Gateway*: parti con tutto **off**, poi rendi **verdi solo** i domini a
   basso rischio (es. Luci); tieni serrature/allarme/cancello **giallo/rosso**.
4. Usa gli **override per-entità** per le eccezioni puntuali.
5. Configura il **servizio notifica** (es. `notify.iphone_bet`) per il flusso giallo.
6. Se usi il gateway MCP: verifica che `/authorize` sia protetto da Cloudflare Access
   (policy email) e che il pannello sia dietro autenticazione.
7. Abilita **snapshot HA** periodici e proteggili.

---

*Per l'architettura generale vedi `architettura.md`; per la configurazione completa
`guida-configurazione.md`.*
