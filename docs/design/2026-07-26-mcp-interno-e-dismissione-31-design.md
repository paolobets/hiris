# MCP interno nell'addon + dismissione gateway .31 — Design

**Data:** 2026-07-26 · Repo: `hiris` (addon) + nuovo addon companion runner · Sotto-progetto **#2**.

## Obiettivo

Rendere la chat via abbonamento **self-contained sull'host HA** ed eliminare
completamente la dipendenza dal server `.31`. Fine del drift cross-repo, fine del
perimetro pubblico. Il connector Claude.ai pubblico viene **dismesso** (non serve:
la chat HIRIS basta).

**End-state — TUTTO in un unico addon HIRIS (nessun componente esterno):**
- L'**addon HIRIS** serve un endpoint **MCP interno** (i suoi stessi tool, in-process),
  su **localhost**, raggiungibile solo dentro il container.
- Il **runner** (`claude -p` + credenziali Max) è un **componente interno dell'addon**
  (worker asyncio + subprocess `claude`), NON un addon separato. L'immagine dell'addon
  include **node + Claude CLI**; `claude -p` punta all'MCP su **localhost** (internal
  token / solo-loopback).
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

### C2 — Runner INTERNO all'addon HIRIS (nessun addon separato)
- L'immagine dell'addon HIRIS aggiunge **node + Claude CLI** (oltre a Python).
- Il consumer della reasoning queue diventa un **worker asyncio dentro l'addon** (avviato
  in `_on_startup`, accanto agli altri job): pesca i job `kind="chat"`, lancia `claude -p`
  come **subprocess** puntato all'MCP su **localhost**, e scrive la reply nel chat_store.
  Riusa la logica `agent/runner.py`+`prompts.py`+wiring MCP fatti oggi, portati in-addon.
- `claude -p` raggiunge l'MCP su **`http://127.0.0.1:<porta>/mcp`** (solo loopback nel
  container) — nessuna rete addon↔addon, nessun JWT di servizio, nessuna CF.
- **Credenziali Max:** in `/data` dell'addon; auth una-tantum (vedi R3).
- **Opzionalità:** il worker/subprocess parte solo se `chat_via_subscription` è attivo;
  gli utenti API-key non lo usano (ma node+CLI restano nell'immagine → vedi R2 bis).

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
- **R2 bis — node + Claude CLI nell'immagine addon:** l'immagine HIRIS (oggi Alpine +
  Python 3.14) deve includere node + `@anthropic-ai/claude-code`. Verificare peso
  immagine, compatibilità Alpine (o base image diversa), e che non rallenti il boot per
  gli utenti API-key che non usano il runner. Il subprocess `claude -p` gira come utente
  dell'addon con `CLAUDE_CONFIG_DIR` in `/data`.
- **R3 — Auth abbonamento dentro l'addon:** `claude setup-token` è interattivo (gotcha già
  visto sul volume `.31`). Definire il flusso una-tantum: un pulsante/step nella UI addon
  o un comando `docker exec … claude setup-token`, con creds persistite in `/data`. È il
  rischio più concreto per la distribuibilità (per la community è uno step power-user).

## Non-goal

- Nessuna esposizione pubblica / OAuth / connector (dismesso).
- Nessun modello permessi per-utente (è il sotto-progetto #1, indipendente).
- Nessuna gestione RetroPanel/integrazioni esterne (futuro).

## Test / verifica

- **C1:** unit sui tool MCP interni (chiamano il dispatcher, rispettano kill-switch/audit);
  il semaforo gate le azioni come oggi.
- **End-to-end (prima della dismissione):** chat via abbonamento con runner in-addon +
  MCP interno su localhost → "che luci sono accese?" dati reali, azione verde esegue,
  gialla/rossa in attesa — **tutto in un unico addon, gateway `.31` spento in prova**.
- **C3:** dopo verifica, teardown `.31` + conferma che nulla di HIRIS resta lì.

## Rollout

1. C1 (MCP interno su localhost) → PR/review → bump addon.
2. C2 (runner in-addon: node+CLI nell'immagine, worker asyncio, auth Max) → build+auth →
   verifica end-to-end con `.31` **ancora acceso** come fallback.
3. Spegni `.31` (in prova) → ri-verifica end-to-end su un unico addon.
4. C3 dismissione definitiva `.31` + connector (con backup segreti).
