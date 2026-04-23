# SemanticContextMap — Unresolved Review Issues

> **Interno** — issue emerse durante le code review della feature SemanticContextMap (v0.3.0).
> Aggiornato 2026-04-23: cleanup pass applicato, chiuse le issue risolte o non applicabili.

---

## Task 1: KnowledgeDB

### Risolte
| # | Issue | Stato |
|---|---|---|
| T1-I2 | Nessun context manager (`__enter__`/`__exit__`) | ✅ Risolto — aggiunti `__enter__`/`__exit__` in commit `908eee3` |

### Chiuse (YAGNI / by-design)
| # | Issue | Motivazione chiusura |
|---|---|---|
| T1-I1 | Mancano `get_correlations()` e `get_top_query_patterns()` | Nessun consumer attuale; dati scritti per uso futuro. Aggiungere quando serve. |
| T1-I3 | `check_same_thread=False` senza `threading.Lock` | Sicuro per event loop single-thread aiohttp. Da rivedere solo se si aggiungono thread concorrenti. |

---

## Task 2: EntityCache extension

### Risolte
| # | Issue | Stato |
|---|---|---|
| T2-M1 | `_DOMAIN_ATTRS` usa `list` invece di `tuple` | ✅ Risolto — cambiato a `tuple` in commit `908eee3` |

### Chiuse (YAGNI / by-design / Phase 2)
| # | Issue | Motivazione chiusura |
|---|---|---|
| T2-I1 | `device_class` sempre presente anche come `None` | Design choice: schema uniforme. Omettere None aumenta complessità dei consumer senza beneficio reale. |
| T2-I2 | `color_mode` / `hs_color` omessi per le luci | Esplicitamente Phase 2. |
| T2-M2 | Fixture `test_entity_cache.py` usano vecchia shape (4 campi) | I test passano perché testano metodi che non guardano `domain`/`device_class`. Fixture stale ma non broken. |
| T2-M3 | `vacuum` e `fan` hanno copertura attributi limitata | Attributi aggiuntivi non usati da nessuna logica attuale. YAGNI. |

---

## Task 3: SemanticContextMap core

### Risolte
| # | Issue | Stato |
|---|---|---|
| T3-I1 | `_EXCLUDED_DOMAINS` non derivato da `NOISE_DOMAINS` | ✅ Risolto — aggiunto commento esplicativo in commit `908eee3` |
| T3-I2 | `entity_cache._states` acceduto come attributo privato | ✅ Risolto — aggiunto `EntityCache.get_all_states()`, `build()` aggiornato in commit `908eee3` |
| T3-M1 | 15 entity type non raggiungibili via `CONCEPT_TO_TYPES` | ✅ Risolto — aggiunti keyword italiani per tutti i 15 tipi mancanti in commit `908eee3` |

### Chiuse (test coverage — defer)
| # | Issue | Motivazione chiusura |
|---|---|---|
| T3-M2 | Nessun test per il path `knowledge_db` in `build()` | Coverage gap non critico. Da aggiungere in prossimo ciclo test. |

---

## Task 4: SemanticContextMap — format + get_context

### Risolte
| # | Issue | Stato |
|---|---|---|
| T4-I1 | `_format_overview` e `_format_detail` chiamano `datetime.now()` indipendentemente | ✅ Risolto — `now` catturato una volta in `get_context` e passato ai formatter in commit `908eee3` |
| T4-I2 | Ordinamento entity types in overview non deterministico | ✅ Risolto — `sorted(named[area].items())` in commit `908eee3` |
| T4-M1 | `"occupancy"` è dead branch in `_format_state` | ✅ Risolto — rimosso, check ridotto a `("motion", "presence")` in commit `908eee3` |
| T4-M3 | Skip silenzioso in `_format_detail` quando `get_state` restituisce None | ✅ Risolto — aggiunto `logger.debug` in commit `908eee3` |

### Chiuse (YAGNI / test coverage)
| # | Issue | Motivazione chiusura |
|---|---|---|
| T4-M2 | Nessun test per `add_entity` e `remove_entity` | Coverage gap non critico. Da aggiungere in prossimo ciclo test. |
| T4-M4 | Area matching substring-based (`a.lower() in q`) | Rischio futuro con aree dal nome brevissimo. Accettabile finché nessun utente usa nomi di area di 1-2 caratteri. |

---

## Task 7: claude_runner.py + ha_tools.py

### Chiuse (working-as-intended / by-design / pre-esistente)
| # | Issue | Motivazione chiusura |
|---|---|---|
| T7-I1 | `visible_entity_ids` empty frozenset semanticamente ambiguo | `frozenset()` → fallback a `allowed_entities` è il comportamento corretto: nessun match RAG = usa il filtro base. |
| T7-I2 | `run_with_actions` non propaga `visible_entity_ids` | By design: agenti proattivi/reattivi sono server-side e hanno accesso completo alle entità. |
| T7-I3 | `visible_entity_ids` non filtra gli altri 4 tool entity | Comportamento pre-esistente prima di questa feature. Tracciato per fix futuro (richiede modifica dell'architettura dei tool handler). |
