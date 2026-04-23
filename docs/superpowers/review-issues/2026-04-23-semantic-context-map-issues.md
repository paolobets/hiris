# SemanticContextMap — Unresolved Review Issues

> **Interno** — issue emerse durante le code review della feature SemanticContextMap (v0.3.0) che non sono state risolte in-task. Da riaffrontare in un prossimo ciclo di cleanup.

---

## Task 1: KnowledgeDB

### Important
| # | Issue | File | Note |
|---|---|---|---|
| T1-I1 | Mancano i metodi `get_correlations(entity_id)` e `get_top_query_patterns(limit)` | `knowledge_db.py` | I dati vengono scritti ma non letti via API pubblica. Il plan corrente non li usa, ma chi accede a `_conn` direttamente nei test rischia di diventare un pattern nelle produzioni future. |
| T1-I2 | Nessun context manager (`__enter__`/`__exit__`) | `knowledge_db.py` | In caso di eccezione prima di `close()` la connessione SQLite resta aperta (file lock su Windows). |
| T1-I3 | `check_same_thread=False` senza `threading.Lock` | `knowledge_db.py` | Sicuro per l'event loop single-thread di aiohttp, ma latente con agenti concorrenti futuri. |

---

## Task 2: EntityCache extension

### Important
| # | Issue | File | Note |
|---|---|---|---|
| T2-I1 | `device_class` è sempre presente nel dict, anche come `None` | `entity_cache.py` | Scelta progettuale (schema uniforme); potrebbe essere omesso quando None per ridurre payload. |
| T2-I2 | `color_mode` / `hs_color` omessi per le luci | `entity_cache.py` | Impedisce a SemanticContextMap di distinguere bulbi RGB da CT-only. Rinviato a Phase 2. |

### Minor
| # | Issue | File | Note |
|---|---|---|---|
| T2-M1 | `_DOMAIN_ATTRS` usa `list` invece di `tuple` | `entity_cache.py` | Liste non mutate; tuple sarebbe più idiomatico. |
| T2-M2 | Fixture in `test_entity_cache.py` usano la vecchia shape (4 campi) | `tests/test_entity_cache.py` | Passano perché i metodi testati non guardano `domain`/`device_class`, ma i fixture sono stale. |
| T2-M3 | `vacuum` e `fan` hanno copertura attributi limitata | `entity_cache.py` | `vacuum` manca `status`/`fan_speed`; `fan` manca `direction`/`oscillating`. |

---

## Task 3: SemanticContextMap core

### Important
| # | Issue | File | Note |
|---|---|---|---|
| T3-I1 | `_EXCLUDED_DOMAINS` non derivato da `NOISE_DOMAINS` di `entity_cache.py` | `semantic_context_map.py` | Le due liste possono divergere se si aggiungono domini noise. Aggiungere commento o costruire come `frozenset(NOISE_DOMAINS \| {...})`. |
| T3-I2 | `entity_cache._states` acceduto come attributo privato | `semantic_context_map.py:124` | Aggiungere `get_all_states() -> dict[str, dict]` su `EntityCache` per esporre una superficie pubblica. |

### Minor
| # | Issue | File | Note |
|---|---|---|---|
| T3-M1 | 15 entity type non raggiungibili via `CONCEPT_TO_TYPES` | `semantic_context_map.py` | `battery`, `co2`, `connectivity`, `current`, `fan`, `gas`, `illuminance`, `moisture`, `pm25`, `pressure`, `smoke`, `vibration`, `voltage`, `water`, `water_heater`. L'utente che chiede "co2" o "ventilatore" non otterrà match. |
| T3-M2 | Nessun test per il path `knowledge_db` in `build()` | `tests/test_semantic_context_map.py` | Path user-override e save_classification non coperti. |

---

## Task 4: SemanticContextMap — format + get_context

### Important
| # | Issue | File | Note |
|---|---|---|---|
| T4-I1 | `_format_overview` e `_format_detail` chiamano `datetime.now()` indipendentemente | `semantic_context_map.py` | Il timestamp "agg. HH:MM" può differire di un secondo tra le due sezioni. Fix: catturare `now` una volta in `get_context` e passarlo. |
| T4-I2 | Ordinamento entity types in overview non deterministico | `semantic_context_map.py:217` | `named[area].items()` itera in insertion order; potrebbe variare tra restart. Usare `sorted(named[area].items())`. |

### Minor
| # | Issue | File | Note |
|---|---|---|---|
| T4-M1 | `"occupancy"` è dead branch in `_format_state` | `semantic_context_map.py:185` | `ENTITY_TYPE_SCHEMA` mappa `occupancy` → entity_type `"motion"`, quindi il check `entity_type in ("motion", "occupancy", "presence")` non raggiunge mai `"occupancy"`. |
| T4-M2 | Nessun test per `add_entity` e `remove_entity` | `tests/test_semantic_context_map.py` | Guard per domini esclusi e tipo "other" non coperti. |
| T4-M3 | Skip silenzioso in `_format_detail` quando `get_state` restituisce None | `semantic_context_map.py:251` | Aggiungere `logger.debug` per rilevare desync cache/map. |
| T4-M4 | Area matching substring-based (`a.lower() in q`) | `semantic_context_map.py` | Area corta come `"a"` matcherebbe sempre; futuro rischio con nomi area abbreviati. |

---

## Task 7: claude_runner.py + ha_tools.py

### Important
| # | Issue | File | Note |
|---|---|---|---|
| T7-I1 | `visible_entity_ids` empty frozenset semanticamente ambiguo | `claude_runner.py` | `frozenset()` è falsy → fallback a `allowed_entities` corretto per ora, ma `None` (parametro default) vs `frozenset()` (da handler senza match RAG) sono indistinguibili nel dispatch. Considerare sentinel `None` = "non impostato" vs `frozenset()` = "zero entità visibili". |
| T7-I2 | `run_with_actions` non propaga `visible_entity_ids` | `claude_runner.py` | Per agenti proattivi/reattivi, il filtro RAG viene silenziosamente ignorato. Non impatta Phase 1 (solo chat usa context_map), ma latente. |
| T7-I3 | `visible_entity_ids` non filtra `get_area_entities`, `get_home_status`, `get_entities_on`, `get_entities_by_domain` | `claude_runner.py` | Il filtro si applica solo a `get_entity_states`. Un agente con `allowed_entities` ristretto può ricevere entità fuori scope via questi tool. Comportamento pre-esistente (non regredito), ma semanticamente incoerente col claim "unified permission boundary". Fix: applicare filtro sui risultati prima del return nei 4 tool. |
