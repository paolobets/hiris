# MCP interno nell'addon + dismissione gateway .31 — Design

**Data:** 2026-07-26 · Repo: `hiris` (addon) + nuovo addon companion runner · Sotto-progetto **#2**.

## Obiettivo

Rendere la chat via abbonamento **self-contained sull'host HA** ed eliminare
completamente la dipendenza dal server `.31`. Fine del drift cross-repo, fine del
perimetro pubblico. Il connector Claude.ai pubblico viene **dismesso** (non serve:
la chat HIRIS basta).

**End-state:**
- L'**addon HIRIS** serve un endpoint **MCP interno** (i suoi stessi tool, in-process),
  autenticato dall'internal token, raggiungibile solo dalla rete interna HA.
- Il **runner** (`claude -p` + credenziali Max) diventa un **addon companion** sull'host
  HA, che raggiunge l'MCP interno via rete Supervisor (nessuna CF/OAuth/esposizione).
- `.31` liberato da tutto HIRIS (gateway, hiris-agent, cloudflared) e connector dismesso.

## Ordine SICURO (vincolante)

**Costruire e verificare il rimpiazzo PRIMA di smontare `.31`.** Il gateway `.31`
alimenta oggi la chat via abbonamento (verificata funzionante) e il connector: la
dismissione è l'**ultimo** passo, dopo che la chat gira end-to-end sull'host HA.

## Componenti

### C1 — MCP interno nell'addon HIRIS (`hiris`)
- L'addon fa girare, nello stesso processo, l'app aiohttp esistente **+** un server
  **FastMCP** su una **2ª porta interna** (stesso pattern del gateway per mcp+panel via
  `asyncio.gather`).
- I tool MCP chiamano il **dispatcher HIRIS in-process** (non `hiris.execute` via HTTP):
  niente hop, e il **catalogo tool è unico** = quelli che HIRIS già espone (il drift
  sparisce alla radice; non si duplica `tiers.py`).
- Il "poliziotto" essenziale (kill-switch, circuit-breaker, audit) va portato accanto
  al dispatcher o riusato da HIRIS; il **semaforo resta il gate delle azioni** (invariato).
- **Auth:** internal token (riuso `middleware_internal_auth`); l'endpoint MCP è
  raggiungibile solo dalla rete interna HA (nessun OAuth, nessuna porta pubblica).

### C2 — Runner come addon companion (`hiris-agent`, nuovo addon)
- Nuovo addon nel repo addon HIRIS (o repo dedicato): immagine con **node + Claude CLI**,
  polla la reasoning queue di HIRIS e lancia `claude -p` (riusa il codice `agent/` del
  gateway: `runner.py`, `prompts.py`, il wiring MCP fatto oggi).
- Raggiunge l'MCP interno dell'addon HIRIS via **rete Supervisor** (hostname addon +
  internal token), non più via CF/JWT di servizio.
- **Credenziali Max:** persistite in `/data` dell'addon; auth una-tantum via
  `claude setup-token` (vedi rischio R3).

### C3 — Dismissione `.31` (ops, ultimo passo)
- Stop+rimozione dei 3 container `hiris-mcp-gateway-*` su `.31`; rimozione tunnel/Access
  app/hostname pubblici (`mcp.ha-betarena.it`, `mcp-panel`, `hiris-internal` se non più
  usato) e del **connector Claude.ai**. Passi manuali su Cloudflare/Claude a carico
  dell'utente; io preparo lo script di stop/rimozione container.
- Backup dei segreti `.env`/chiavi prima della rimozione (non perderli).

## Rischi / fattibilità DA VALIDARE (spike prima del piano)

- **R1 — FastMCP dentro il processo addon:** verificare che FastMCP (uvicorn/Starlette)
  coesista con l'app aiohttp su una 2ª porta via `asyncio.gather` senza conflitti di
  event loop, e che i tool possano chiamare il dispatcher HIRIS in-process.
- **R2 — Rete addon↔addon:** verificare come il runner-addon raggiunge l'MCP dell'addon
  HIRIS (hostname sulla rete Supervisor / porta interna / internal token). Pattern noto
  (es. addon che parlano con l'addon MQTT), ma va confermato per ingress/porta interna.
- **R3 — Auth abbonamento in un addon:** `claude setup-token` è interattivo (gotcha già
  visto sul volume `.31`). Definire il flusso una-tantum nell'addon (exec/terminal) o il
  trasferimento creds; documentarlo. Per la community è uno step da power-user.

## Non-goal

- Nessuna esposizione pubblica / OAuth / connector (dismesso).
- Nessun modello permessi per-utente (è il sotto-progetto #1, indipendente).
- Nessuna gestione RetroPanel/integrazioni esterne (futuro).

## Test / verifica

- **C1:** unit sui tool MCP interni (chiamano il dispatcher, rispettano kill-switch/audit);
  il semaforo gate le azioni come oggi.
- **End-to-end (prima della dismissione):** chat via abbonamento con runner-addon +
  MCP interno → "che luci sono accese?" dati reali, azione verde esegue, gialla/rossa in
  attesa — **tutto sull'host HA, gateway `.31` spento in prova**.
- **C3:** dopo verifica, teardown `.31` + conferma che nulla di HIRIS resta lì.

## Rollout

1. C1 (MCP interno) → PR/review → bump addon.
2. C2 (addon runner) → build+auth → verifica end-to-end con `.31` **ancora acceso** come
   fallback.
3. Spegni `.31` (in prova) → ri-verifica end-to-end sull'host HA.
4. C3 dismissione definitiva `.31` + connector (con backup segreti).
