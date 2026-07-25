# HIRIS Pre-1.0 Whole-Codebase Review — Prioritized Report

## 1. Executive Summary

**Overall health: not ready for 1.0.** The review surfaced **4 confirmed CRITICAL** and **13 confirmed HIGH** defects that survived adversarial verification, concentrated in exactly the subsystems that are supposed to be HIRIS's trust boundary: the yellow/red "semaforo" action-gating system, the MCP-gateway approval flow, and the tool-dispatch layer. Several of these are not edge cases — they are complete, low-effort bypasses of the human-in-the-loop safety model the product markets itself on (lock/alarm/siren step-up confirmation, per-entity overrides, PII pseudonymization).

**Counts by final_severity** (after adversarial verification of high/critical; medium/low are finder-reported and unverified):

| final_severity | count |
|---|---|
| critical | 4 |
| high | 15 *(13 unique after merging duplicates)* |
| medium | 23 |
| low | 12 |

**Single biggest risk:** `hiris/app/api/handlers_gateway_pending.py:272` — the yellow/red step-up approval endpoint is gated by the *same* internal token the machine principal (MCP gateway) already holds, so a compromised or malicious gateway client can create a pending lock/alarm/siren action and immediately self-approve it via a second API call, with zero human involvement. This defeats the entire "red tier requires manual approval in HIRIS" promise the module's own docstring makes. Runner-up: `proxy/ha_client.py:239`, a same-host SSRF/path-traversal primitive reachable from an unvalidated, LLM-steerable tool argument with no confirmation gate.

**Caveat on medium/low:** Everything in "Should Fix" and "Backlog" below is a finder report that was *not* independently re-verified — treat as a triage queue, not a confirmed defect list. Two exceptions are called out explicitly: the `requirements.txt` and `Dockerfile` infra findings were originally rated high by the finder but were *downgraded to medium/low after verification* (they're real but lower-impact than claimed) — these carry `verdict: confirmed/plausible` even though their final severity is medium/low.

---

## 2. MUST FIX before 1.0 (confirmed critical + high)

### CRITICAL

**1. [CRITICAL][confirmed] security-core / gateway-pending — `api/handlers_gateway_pending.py:272`**
Yellow/red step-up approvals are gated only by `X-HIRIS-Internal-Token` — the same credential the MCP gateway (the machine principal being step-up-gated) already holds.
*Failure:* Gateway calls `/api/execute` for a red-tier action (e.g. unlock front door) → gets back `{status: pending_approval, id: <nonce>}` → immediately POSTs `/api/gateway/pending/<nonce>/approve` with the same internal token → `execute_pending()` runs the command with `tier_confirmed=True`, bypassing the denylist. No human ever sees a notification. The nonce isn't even guarded — it's handed back in the execute response and exposed again via `list_pending`.
*Fix direction:* Approval must require a distinct, human-bound credential (the existing OTP-to-phone mechanism, or an ingress-session-authenticated request) — never accept the same internal service token used to *create* the pending item.

**2. [CRITICAL][confirmed] tools-dispatcher / automation — `tools/dispatcher.py:188`**
`trigger_automation` reaches HA's `automation.trigger` service without ever calling `gate_action()` — no tier check, no `DANGEROUS_DOMAINS` denylist. Reviewer corrected the reachability path: not exposed via the MCP-gateway execute API (hard-allowlisted out), but **is** part of the full tool set given to the main interactive chat agent (`ALL_TOOL_DEFS` in `claude_runner.py`), which by default has no `allowed_entities`/`allowed_services` restriction.
*Failure:* Chat agent (or a prompt-injected instruction) calls `trigger_automation` on a pre-existing HA automation whose internal action sequence unlocks a door / disarms the alarm. The identical raw `lock.unlock` call via `call_ha_service` would be hard-blocked; routed through an automation trigger it is completely invisible to the semaforo.
*Fix direction:* Resolve the automation's action sequence (or at minimum treat any `automation.trigger`/`automation.turn_on` call as opaque-dangerous) and route through `gate_action` before dispatch, or restrict `trigger_automation` to an explicit allowlist by default.

**3. [CRITICAL][confirmed] llm-runners-routing / concurrency — `claude_runner.py:471`**
`last_tool_calls`/`last_thinking_blocks` are unlocked instance attributes on a singleton `ClaudeRunner` shared by every interactive chat request *and* every scheduler-driven agent run on the same event loop. `chat()` resets them to `[]` then appends after `await` points with no locking.
*Failure:* An interactive chat and a background persona run overlap; one conversation's tool-call inputs (entity IDs, memory-recall content, HTTP payloads) leak into another conversation's `debug_payload`/SSE `done` event, or get silently wiped. The codebase's own `_running_agents` guard only prevents the *same* agent_id from re-entering — it does nothing for two different agents/chats overlapping. `llm_router.py`'s `last_tool_calls` property amplifies this by returning whichever registered runner has a non-empty list, independent of which one served the current call.
*Fix direction:* Make tool-call/thinking-block collection local to the `chat()` call (return value or a per-call context object), not shared mutable instance state; add a lock if instance state must be kept temporarily.

**4. [CRITICAL][confirmed] proxy-ha / SSRF — `proxy/ha_client.py:239`**
`get_automation_config()` builds the HA REST request URL from an unvalidated, LLM-supplied `automation_id`, unlike every sibling function (`get_calendar_events_range`, `trigger_automation`/`toggle_automation` in `dispatcher.py`) which validate with a strict regex first. Confirmed via yarl URL normalization that `automation_id="automation.x/../../config/core/config"` genuinely escapes the intended `/api/states/` prefix to reach `/api/config/core/config` on the local HA host with the full-privilege Bearer token. (Cross-host escape does not work — same-host only, and the traversal response isn't returned verbatim to the caller, so this is narrower than pure SSRF but still a real endpoint-confusion primitive with no confirmation gate.)
*Fix direction:* Apply the same `_AUTOMATION_ID_RE` validation used in `dispatcher.py`'s trigger/toggle branches before this function builds its URL; never string-concatenate unvalidated input into a request path.

---

### HIGH

**5. [HIGH][confirmed] security-core + server-orchestration / target-vs-data split — `tools/dispatcher.py:303` and `task_engine.py:355-368`**
The semaforo gate authorizes on `data.entity_id` **OR** `target.entity_id`, but the actual `call_service`/`call_ha_service` execution forwards only `data` — `target` is silently dropped in **two separate code paths** (live dispatch and the deferred task engine). A request scoped via `target` to a single green entity is gated correctly but executed as a domain-wide broadcast in HA, actuating sibling entities the user explicitly marked off (per-entity override bypass). The task-engine path additionally skips the area/device/label group-target fail-closed check entirely, since it only ever reads `data`.
*Fix direction:* Normalize `target` into `data` (or vice versa) once, immediately after tier gating and before both persistence (task creation) and execution, in a single shared helper used by both `dispatcher.py` and `task_engine.py`.

**6. [HIGH][confirmed] brain-cognitive / unvalidated LLM thresholds — `brain/suggestions.py:133`**
Auto-applied coverage suggestions forward LLM-chosen, completely unvalidated param values (`max_watt`, `max_temp_c`, `min_pct`, `open_minutes`) into a **shared** detector config with no type/range check, applied to ALL entities on that detector, not just the newly-added one. A malformed or adversarial value either neuters the detector (e.g. `max_watt: 999999`) or breaks it with a `TypeError` on every subsequent event.
*Fix direction:* Apply the same clamp/validation discipline already used for `apply_brain_tuning`'s `learned_threshold` path; never let LLM-authored suggestion params reach a shared detector config unvalidated.

**7. [HIGH][confirmed] brain-cognitive / PII cross-leak — `brain/privacy.py:128`**
`Pseudonymizer.detokenize` expands ANY `[TYPE_N]` token found in LLM output against a single home-global, sequentially-named, forever-growing vault with no owner/conversation scoping and no check that the token was actually sent to the model in the current exchange.
*Failure:* Any chat turn whose output happens to contain a matching bracket pattern (user-typed, model-hallucinated, or prompt-injected from a poisoned document) gets blindly expanded to real PII (IBAN, codice fiscale, card, email) — potentially pseudonymized in a *different* conversation by a *different* user — then displayed and permanently persisted in the current chat history.
*Fix direction:* Scope vault tokens by owner/conversation, and restrict `detokenize` to only tokens that were actually substituted into the outbound prompt for this exact turn.

**8. [HIGH][confirmed] watcher-sentinella / config type validation — `watcher/policy.py:142`**
`save_policy`/`load_policy` perform zero type validation on whitelisted detector keys. A malformed POST (string `entities`, string `max_watt`) is persisted and pushed live. String `entities` causes substring-match false positives in the guardian's entity filter; string `max_watt` raises `TypeError` inside the single broad `except` in `Guardian.on_state_changed`, silently aborting the rest of that event's detector loop **and all user-lens dispatch** for every real update of the configured entity.
*Fix direction:* Schema-validate the policy body (types + ranges) before `save_policy`/`set_policy`; reject malformed configs with a 4xx instead of accepting and applying live.

**9. [HIGH][confirmed] tools-dispatcher / automation gate gap — `tools/dispatcher.py:204`**
`toggle_automation` (enable/disable ANY automation, including security-relevant ones) is gated only by the optional `allowed_services`/`allowed_entities` allowlist — never by `gate_action`/`DANGEROUS_DOMAINS`. On the seeded default agent (`allowed_tools=[]`, empty allowlists), this is completely ungated out of the box. Same root cause family as finding #2.
*Fix direction:* Same as #2 — route through the semaforo, or explicitly deny-by-default and require operator opt-in.

**10. [HIGH][confirmed] tools-dispatcher / input-helper gate gap — `tools/calendar_tools.py:104`**
`set_input_helper` actuates `input_boolean`/`input_number`/`input_text`/`input_select` (commonly wired to real security automations — guest mode, vacation mode, alarm override) via `ha.call_service` with no `gate_action` call at all — only the optional allowlist applies. The identical underlying service call via `call_ha_service` is fail-closed and confirmable; via this tool it's fail-open. Same root cause family as #2/#9.
*Fix direction:* Same as #2/#9.

**11. [HIGH][confirmed] tools-dispatcher / allowlist bypass — `tools/ha_tools.py:150`**
`get_area_entities` returns the full area→entity_id map with no `allowed_entities` filtering, unlike every sibling read tool. Reachable via custom-agent/persona chat flows where `allowed_entities` is a genuine security boundary (e.g. a guest persona scoped to `light.*`) — this tool discloses every entity_id in the house, including `lock.*`, `alarm_control_panel.*`, `camera.*`, `person.*`, `device_tracker.*`, to that scoped agent.
*Fix direction:* Route through `_filter_entities(result, allowed_entities)` like `get_home_status`/`get_entities_on`/`get_entities_by_domain`.

**12. [HIGH][confirmed] tools-dispatcher / allowlist bypass — `tools/history_tools.py:177`**
`get_history` accepts attacker/agent-supplied `entity_ids` with no `allowed_entities`/`visible_entity_ids` filtering, unlike the parallel `get_entity_states` branch which filters the same kind of caller-supplied list. An entity-scoped agent can request full historical time-series (presence, lock state) for entities entirely outside its policy scope, and this tool is in `READ_TOOLS` (always available to the MCP gateway).
*Fix direction:* Apply the same `fnmatch` filter used in the `get_entity_states` branch.

**13. [HIGH][confirmed] llm-runners-routing / fallback dead — `llm_router.py:204`**
The documented automatic-mode fallback ("if the primary backend raises, try the next in the policy chain") never triggers for the most common failure classes, because `ClaudeRunner.chat()`/`OpenAICompatRunner.chat()` catch API errors (rate-limit, connection, timeout, persistent outage) internally and **return a friendly error string instead of raising**. Confirmed this defeats fallback for the Sentinella's own `run_with_actions` safety-monitoring call path — an Anthropic outage silently produces a generic error/degraded verdict instead of failing over to a configured, healthy local/other backend.
*Fix direction:* Re-raise (or return a sentinel the router checks) on API-error classes instead of swallowing to a string, so the router's `except Exception` loop actually engages.

**14. [HIGH][confirmed] server-orchestration / lifecycle leak — `task_engine.py:307`**
`_evaluate_condition()` is called with no try/except in `_execute_task`, outside the surrounding try/finally. A malformed `task.condition` (trivially reachable via the untyped `create_task` LLM tool schema) raises `KeyError`, which propagates past the `finally` block that would reset task status — the task is permanently stuck at `status='running'`, can never be cancelled (`cancel_task` requires `status=='pending'`), and is never cleaned up by `_cleanup()` (which only removes terminal statuses). Silent memory/state leak with no visible failure until restart.
*Fix direction:* Validate `condition` shape at `add_task()` time; wrap the `_evaluate_condition` call in `_execute_task` in the same try/finally that guarantees status cleanup.

**15. [HIGH][confirmed] server-orchestration / task leak — `server.py:849`**
`asyncio.create_task()` results are discarded with no stored reference for the HA notification-action listener that drives the step-up **approval flow** — the exact mechanism a user's phone-tap "Approve"/"Reject" relies on. Per asyncio's documented weak-reference semantics, a task with no external referrer can be garbage-collected mid-execution (real risk here since the handler genuinely awaits HTTP calls to HA). If collected mid-flight, a human's approval tap silently does nothing — no error, action just sits pending until timeout. Same discarded-task pattern recurs at lines 1088, 1363, 1712, 1803.
*Fix direction:* Store every `create_task()` result in a module-level/app-level strong-reference set with a `add_done_callback` to discard on completion (the standard asyncio pattern).

**16. [HIGH][confirmed] api-handlers / IDOR — `api/handlers_knowledge.py:9` (and duplicate report at line 14)**
The knowledge-approval API is completely owner-blind: `handle_list_pending` returns every user's pending items (full content, including `sensitivity='sensitive'` rows) with no owner filter, and `handle_approve`/`handle_reject` act on any integer item id with no ownership check — the store layer's `approve()`/`delete_item()` don't even accept an owner argument. Any authenticated household/ingress user can read, approve, or permanently delete another user's private second-brain items.
*Fix direction:* Thread `owner` through `list_items(status='pending', owner=...)` and add an ownership check (or `owner IN (caller, 'home')` clause) to `approve()`/`delete_item()`.

**17. [HIGH][confirmed] proxy-ha / sanitizer gap — `proxy/semantic_context_map.py:259`**
`_format_state()` for `entity_type=='climate'` embeds `attrs['current_temperature']`/`attrs['temperature']` directly into the LLM context string without calling `sanitize_ha_value()`, unlike every other field in the same function (state, hvac_mode, hvac_action, media_title, unit). A compromised/template climate integration can set these to injection text that reaches the prompt unfiltered.
*Fix direction:* Route both fields through `sanitize_ha_value()` like their siblings in the same function.

---

## 3. Should Fix (medium, unverified — each needs a quick confirm pass)

**security-core**
- `server.py:385` — Step-up OTP falls back to `notify.persistent_notification` (HA-wide, shared dashboard) when no per-user push service is configured — secret exposed on a shared surface instead of delivered privately.

**brain-cognitive** (5)
- `brain/briefing.py:54` (+ `reminders.py:89`) — Daily briefing/nudges query `upcoming_obligations()` without the owner filter → per-user obligations broadcast home-wide.
- `api/handlers_knowledge.py:14` — Duplicate report of the confirmed IDOR already listed in MUST FIX (#16); no separate action needed.
- `brain/suggestions.py:186` — Undo of an applied coverage suggestion only removes the entity, never restores the shared detector param it overwrote (contrast: `apply_brain_tuning` does snapshot).
- `brain/coverage_review.py:22` — Raw, unsanitized HA-health/error-log text embedded in the coverage-review LLM prompt (sibling bridge path sanitizes the same snapshot) — potential injection amplifier for finding #6.
- `tools/knowledge_tools.py:135` — Cloud-egress gate only pseudonymizes rows with sensitivity exactly `'sensitive'`; store treats any non-`'normal'` value as sensitive, so an unvalidated third sensitivity string reaches the cloud LLM verbatim.

**watcher-sentinella** (3)
- `watcher/lenses.py:155` — Present-but-invalid `attribute` field is silently dropped instead of rejecting the lens (violates the module's own documented fail-safe contract), rebinding the trigger to main state.
- `watcher/lenses.py:291` — Present-but-invalid `enabled` field (e.g. `"false"`, `0`) defaults to `True` — inverts the user's disable intent.
- `watcher/lenses.py:183` — No lower bound on `interval_min`; combined with `cooldown_sec=0` for scheduled lenses and an unbounded `events` table (no retention purge), a tiny interval can cause an event-loop hog and unbounded SQLite growth.

**llm-runners-routing** (2)
- `backends/openai_compat_runner.py:812` — `chat_stream()` never checks `finish_reason=='length'`; truncated streaming responses reach the client with no warning (non-streaming `chat()` does check).
- `backends/openai_compat_runner.py:402` — Connection-failure circuit breaker only guards `simple_chat()`; the main `chat()`/`chat_stream()` agentic loop never checks or trips it — a dead Ollama endpoint is retried at full timeout on every turn.

**server-orchestration**
- `task_engine.py:65` — `_cleanup()` registered as a sync APScheduler job (runs on a worker thread) mutating the unlocked `self._tasks` dict concurrently with the event-loop thread's `add_task()` — possible `RuntimeError: dictionary changed size during iteration`.

**proxy-ha** (2)
- `proxy/semantic_context_map.py:269` — `_format_state()` assumes `brightness`/`volume_level` are always numeric with no type check; `get_context()` has no try/except at either call site — one malformed attribute denies chat to all users.
- `proxy/_sanitize.py:16` — Injection regex only covers a small fixed EN/IT verb list (`ignore`/`ignora`/etc.) — misses `override`, `bypass`, `[INST]`, `<|system|>`, `###`, any other language.

**frontend-security** (2)
- `static/config/proposals.js:48` — Unescaped-quote id attribute construction can truncate the HTML attribute, breaking `getElementById('pr-'+id)` lookups in apply/reject.
- `static/index.html:674` — Same pattern for task ids, breaking `cancelTask()`.

**infra-config** (5) — *note: these carry `verdict: confirmed`, not unverified; downgraded from the finder's "high" to medium after review*
- `requirements.txt:1` — `aiohttp>=3.14.1` has no upper bound (only dependency in the file without one); latent risk of a silent breaking change on a future major-version pip resolve.
- `requirements.txt:5` — `aiomqtt>=2.0.0` unbounded; mitigated in practice by the broad exception handler around the MQTT connect loop (degrades the optional publisher, doesn't crash).
- `run.sh:20` — `jq` parse of `/data/options.json` has no error handling; malformed options silently disable Apprise notifications with no warning.
- `config.yaml:78` — `supervisor_ingress_cidr` has no schema-level CIDR format validation.
- `run.sh:82` — No pre-flight validation/log of required env vars before `exec`-ing the Python app; failures surface as cryptic runtime errors instead.

---

## 4. Backlog (low, unverified one-liners)

- `brain/mayan_ingest.py:28` — Transient embedder failure marks a document ingested anyway; `document_exists` skips it forever with no retry/repair pass.
- `watcher/policy.py:169` — `apply_brain_detector` writes the policy file *before* the brain registry (opposite of the crash-safe order `apply_brain_tuning` documents/uses) — crash between writes makes an auto-added entity un-undoable.
- `server.py:630` — A shape-valid but value-invalid cron (e.g. hour 25) is accepted with 201; scheduler registration fails silently, lens never runs, no status surfaced.
- `tools/dispatcher.py:499` — Catch-all handler returns `str(exc)` verbatim to the caller — potential internal-detail leak (paths, hostnames).
- `api/handlers_sentinel.py:35` — Negative `limit` query param bypasses the documented 200-row cap (SQLite treats negative `LIMIT` as unlimited).
- `proxy/ha_client.py:46` — `get_history`'s `filter_entity_id` is comma-joined into the query string with no `urllib.parse.quote()`; currently safe only because both call sites pre-validate with a regex.
- `static/config/agent-editor.js:374` — HTML "escaping" via `.replace(/[<>&]/g,'')` doesn't escape quotes — currently safe (text-context only) but a landmine if reused.
- `static/config/agent-form.js:97` — `highlightOutput()` regex-matches against already-HTML-escaped text; effectively dead code.
- `requirements.txt:9` — `apprise>=1.9.0` unbounded, but affects only an optional, explicitly-configured notification channel; failures are caught/logged.
- `Dockerfile` — No `USER` directive, container runs as root; standard (if not best-practice) for HA Supervisor add-ons using the bashio/s6 pattern, mitigated by Supervisor-level container isolation rather than in-container UID separation.

---

## 5. Looks Solid

- **frontend-security** — Only medium/low correctness issues (escaping edge cases in id attributes, dead code). No high/critical findings, no evidence of exploitable XSS in what was reviewed.
- **infra-config** — Every item the finder originally rated "high" was downgraded to medium or low on adversarial review (unpinned deps and root-container concerns are real but standard/low-impact for this add-on class, not active vulnerabilities). Worth a cleanup pass, not a blocker.

No partition returned **zero** findings — every area of the codebase surfaced at least one legitimate issue, which itself is a signal to keep this review cadence going into 1.0 rather than treating it as one-and-done.