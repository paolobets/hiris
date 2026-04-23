# HIRIS — Security Audit Report

> **Interno** — audit condotto il 2026-04-23.
> Agenti: `cybersec-auditor` (25 findings) + `penetration-tester` (14 findings).
> Stato: quick wins applicati in commit post-audit.

---

## Sommario rischi

| Severità | Totale | Applicati | Aperti |
|----------|--------|-----------|--------|
| CRITICAL | 2 | 1 | 1 |
| HIGH | 6 | 5 | 1 |
| MEDIUM | 10 | 3 | 7 |
| LOW | 7 | 0 | 7 |
| INFO | 5 | 0 | 5 |

---

## Finding applicati (quick wins)

| ID | Severità | Descrizione | Fix |
|----|----------|-------------|-----|
| SEC-001 | HIGH | Port 8099 esposta direttamente in `config.yaml` — bypassa Ingress auth | Rimosso `ports:` e `ports_description:` da `config.yaml` |
| SEC-004 | MEDIUM | `max_tokens` senza upper bound → DoS / costi illimitati | Cap a 8192 in `create_agent()` e `update_agent()` in `agent_engine.py` |
| SEC-007 | HIGH | Nessun limite lunghezza messaggio chat → prompt injection amplificata | Cap 4000 chars (HTTP 413) in `handlers_chat.py` |
| SEC-010 | HIGH | `domain`/`service` in `call_service` non validati → path injection URL | Regex `^[a-z][a-z0-9_]*$` in `ha_client.py:call_service()` |
| SEC-012 | MEDIUM | Errore Claude API esposto raw all'utente → info disclosure | Messaggio generico in `claude_runner.py`; dettaglio solo nel log server |
| SEC-014 | MEDIUM | `agent_id` da URL path non validato → path traversal possibile | Regex `^[a-zA-Z0-9_-]{1,64}$` in tutti i handler di `handlers_agents.py` |
| SEC-016 | MEDIUM | Security headers HTTP mancanti (X-Frame-Options, X-Content-Type-Options…) | Middleware `_security_headers` aggiunto in `server.py` |
| SEC-021 | MEDIUM | Cron job APScheduler senza `coalesce=True` → job accumulati dopo sleep/riavvio | `coalesce=True, misfire_grace_time=60` in `agent_engine.py` |
| SEC-022 | LOW | Chiavi sensibili nei log di tool call (non applicabile ora, ma prevenzione) | Redact keys (`api_key`, `token`, `password`, `secret`) in `_dispatch_tool` |

---

## Finding aperti — priorità alta

### SEC-002 (CRITICAL) — Prompt Injection / LLM01
**Descrizione:** Nessuna sanitizzazione dell'input utente prima dell'invio a Claude. Un attaccante può iniettare istruzioni nel prompt (`Ignora le precedenti istruzioni...`).

**Mitigazione suggerita:**
- Separare strutturalmente system prompt e user input (già fatto via API `messages[]`)
- Aggiungere check: `if any(s in message.lower() for s in ["ignora le istruzioni", "ignore previous", "jailbreak"])` → rifiutare o avvisare
- Considerare un layer di validazione LLM dedicato per messaggi ad alto rischio

**File:** `handlers_chat.py`, `claude_runner.py`
**Stima effort:** 2-4h

---

### SEC-003 (HIGH) — Default-allow su allowed_services vuoto
**Descrizione:** `agent.allowed_services = []` viene convertito a `None` in `handlers_chat.py` via `or None`, rendendo il check `if allowed_services:` in `_dispatch_tool` sempre falso → nessuna restrizione sui servizi HA.

**Decisione prodotto richiesta:** `[]` deve significare "deny all" o "unrestricted"?
- Attuale: `[]` → unrestricted (user-friendly ma insicuro)
- Secure: `[]` → deny all (breaking change per agenti esistenti)

**Proposta:** aggiungere campo `services_policy: "allowlist" | "open"` all'Agent e usarlo come discriminante.

**File:** `handlers_chat.py:66`, `claude_runner.py:491`
**Stima effort:** 1-2h + decisione prodotto

---

### PENTEST-001 (HIGH) — Bypass autenticazione via accesso diretto porta 8099
**Descrizione (validato dal pen tester):** Con `ports: 8099/tcp: 8099` nel config, chiunque sulla stessa rete poteva accedere direttamente alla API senza passare per l'Ingress di HA (che gestisce l'autenticazione).

**Stato:** ✅ Risolto da SEC-001 (rimosso `ports:`)

---

### PENTEST-003 (HIGH) — Tool call non autenticate lato server
**Descrizione:** I tool call HA (`call_ha_service`, `get_entity_states`) non verificano che il chiamante sia autenticato oltre il layer Ingress. In un contesto multi-tenant futuro questo è un rischio.

**Mitigazione:** Verificare `SUPERVISOR_TOKEN` ad ogni operazione sensibile; aggiungere middleware auth se si espone l'API fuori da Ingress.

**File:** `ha_client.py`, `claude_runner.py:_dispatch_tool`
**Stima effort:** 3-5h

---

## Finding aperti — priorità media

| ID | Descrizione | File | Effort |
|----|-------------|------|--------|
| SEC-005 | `system_prompt` non sanitizzato: può contenere injection da config agent | `handlers_chat.py` | 2h |
| SEC-006 | Rate limiting globale assente — possibile DoS via spam chat | `server.py` | 2h |
| SEC-008 | `get_history` invia `entity_ids` come query string non encoded | `ha_client.py` | 1h |
| SEC-009 | CORS non configurato — potenziale CSRF da browser | `server.py` | 1h |
| SEC-011 | `call_ha_service` accetta `data` dict senza validazione struttura | `claude_runner.py` | 2h |
| SEC-015 | Chat history file path: `safe_id` replace non è canonicalization completa | `chat_store.py` | 1h |
| PENTEST-002 | Nessun timeout su richieste HA → possibile hang indefinito | `ha_client.py` | 1h |

---

## Finding aperti — bassa priorità / future release

| ID | Descrizione |
|----|-------------|
| SEC-017 | `SUPERVISOR_TOKEN` non verificato se env var mancante |
| SEC-018 | Nessun audit log delle azioni HA eseguite (call_ha_service) |
| SEC-019 | `get_weather_forecast` fa fetch a Open-Meteo senza timeout/fallback |
| SEC-020 | Nessuna content-length max su richieste POST |
| SEC-023 | WebSocket HA non riconnette in caso di disconnessione |
| SEC-024 | `allowed_tools` whitelist non validata contro lista tool reale |
| SEC-025 | Nessuna rotazione del KnowledgeDB SQLite |
| PENTEST-004-014 | Ulteriori finding del pen tester a bassa priorità |

---

## Piano test sicurezza (CI/CD)

Vedi `tests/test_security.py` per il test suite automatizzato.

**Frequenza raccomandata:**
- Ad ogni PR: `tests/test_security.py` (fast, < 10s)
- Ad ogni release: audit manuale + run `pentest_hiris.sh` in ambiente staging
- Mensile: re-run cybersec-auditor su codice aggiornato

---

## Referenze

- OWASP LLM Top 10 2024: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- HA Add-on security: https://developers.home-assistant.io/docs/add-ons/security
- CVE tracking: nessuna dipendenza con CVE noti al 2026-04-23 (verificare con `pip-audit`)
