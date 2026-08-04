# Il ritratto della casa — Fetta 1: il Brain vede

> **Per chi esegue:** SOTTO-SKILL RICHIESTA — usa `superpowers:subagent-driven-development`
> (consigliata) oppure `superpowers:executing-plans` per implementare task per task.
> I passi usano caselle (`- [ ]`) per il tracciamento.

**Goal:** dare al Brain la casa — struttura, stato notevole e **cosa è cambiato** — al posto
dell'unica entità più cinque righe di fotografia che riceve oggi.

**Architettura:** un modulo di funzioni **pure** (`brain/portrait.py`) che compone e rende il
ritratto da fonti iniettate, più uno store SQLite (`brain/portrait_store.py`) che ricorda lo stato
notevole precedente ed è **l'unico scrittore** del delta, aggiornato da un job periodico dedicato.
Il ritratto entra nel prompt del ragionatore replicando esattamente il percorso già collaudato
della memoria: helper puro → helper module-level in `server.py` → chiave nel context → blocco
leggibile in `build_user_message`.

**Tech stack:** Python 3.11+, sqlite3 via `hiris/app/storage.py`, pytest + pytest-asyncio (strict).

## Vincoli globali

- **Nessuna nuova dipendenza.** Niente librerie esterne.
- **Fail-safe assoluto:** nessun percorso del ritratto può impedire al ragionatore di funzionare.
  Ogni innesto è in `try/except` e degrada a «niente ritratto», mai a un'eccezione.
- **Il ritratto è di sola lettura verso la casa.** Non chiama servizi, non attua, non propone.
- **Il notevole è discreto, non continuo:** i sensori numerici (temperatura, potenza, umidità)
  **non** entrano nello stato notevole né nel delta.
- **Tutte le stringhe che vengono da Home Assistant passano da**
  `hiris.app.proxy._sanitize.sanitize_ha_value` prima di finire in un prompt.
- **Timestamp** sempre `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` (lunghezza fissa,
  confronto lessicale == cronologico).
- **Store SQLite**: sempre `storage.connect()` + `storage.init_schema()`, `threading.Lock` attorno a
  ogni query, `close()` sotto lock.
- **Test**: pytest puro, funzioni module-level, `@pytest.mark.asyncio` esplicito su ogni test async,
  `tmp_path` per i DB (mai in-memory), `store.close()` a fine test, nomi dei test in inglese.
- **Attenzione ai test di cablaggio via `inspect.getsource`**: `tests/test_gather_context_memory.py`
  e `tests/test_coverage_wiring.py` leggono il sorgente di `server._on_startup`. Se tocchi
  `_gather_context` o `_holistic_reason` **quei test si rompono e vanno aggiornati nello stesso
  commit**.

---

## Struttura dei file

| File | Responsabilità |
|---|---|
| `hiris/app/brain/portrait.py` (nuovo) | funzioni pure: selezione del notevole, composizione del ritratto, resa testuale |
| `hiris/app/brain/portrait_store.py` (nuovo) | memoria dello stato notevole precedente + calcolo e conservazione del delta |
| `hiris/app/server.py` (modifica) | istanziazione dello store, job di osservazione, helper `_reason_portrait_context`, innesto in `_gather_context` e `_holistic_reason` |
| `hiris/app/watcher/reasoner.py` (modifica) | resa del blocco «Com'è la casa» nel messaggio |
| `hiris/app/brain/coverage_review.py` (modifica) | stesso blocco nel percorso olistico |
| `tests/test_portrait.py` (nuovo) | funzioni pure |
| `tests/test_portrait_store.py` (nuovo) | store e delta |
| `tests/test_portrait_wiring.py` (nuovo) | cablaggio via `inspect.getsource` |

---

## Task 1: lo store del notevole e del delta

**Files:**
- Create: `hiris/app/brain/portrait_store.py`
- Test: `tests/test_portrait_store.py`

**Interfaces:**
- Consumes: `hiris.app.storage.connect`, `hiris.app.storage.init_schema`
- Produces:
  ```python
  class PortraitStore:
      def __init__(self, db_path: str) -> None
      def observe(self, current: dict[str, str], *, now: str | None = None) -> list[dict]
      def last_changes(self) -> list[dict]
      def baseline(self) -> dict[str, dict]
      def close(self) -> None
  ```
  `observe` ritorna e persiste una lista di dict `{"entity_id": str, "was": str | None,
  "now": str, "since": str}`. `baseline()` ritorna `{entity_id: {"state": str, "since": str}}`.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_portrait_store.py`:

```python
"""PortraitStore: memoria dello stato notevole e calcolo del delta.

Convenzioni ereditate da tests/test_advisory_store.py: DB reale su tmp_path,
close() esplicito, timestamp passati espliciti per rendere i test deterministici.
"""
from hiris.app.brain.portrait_store import PortraitStore


def test_first_observation_reports_no_changes(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    changes = s.observe({"light.cucina": "on"}, now="2026-08-04T08:00:00Z")
    assert changes == []
    assert s.baseline() == {
        "light.cucina": {"state": "on", "since": "2026-08-04T08:00:00Z"}
    }
    s.close()


def test_changed_state_is_reported_and_since_resets(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"light.cucina": "on"}, now="2026-08-04T08:00:00Z")
    changes = s.observe({"light.cucina": "off"}, now="2026-08-04T09:00:00Z")
    assert changes == [{
        "entity_id": "light.cucina", "was": "on", "now": "off",
        "since": "2026-08-04T09:00:00Z",
    }]
    assert s.baseline()["light.cucina"]["since"] == "2026-08-04T09:00:00Z"
    s.close()


def test_unchanged_state_keeps_original_since(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"binary_sensor.porta": "on"}, now="2026-08-04T08:00:00Z")
    changes = s.observe({"binary_sensor.porta": "on"}, now="2026-08-04T09:00:00Z")
    assert changes == []
    assert s.baseline()["binary_sensor.porta"]["since"] == "2026-08-04T08:00:00Z"
    s.close()


def test_appeared_entity_is_a_change_with_was_none(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"light.a": "on"}, now="2026-08-04T08:00:00Z")
    changes = s.observe(
        {"light.a": "on", "lock.porta": "locked"}, now="2026-08-04T09:00:00Z"
    )
    assert changes == [{
        "entity_id": "lock.porta", "was": None, "now": "locked",
        "since": "2026-08-04T09:00:00Z",
    }]
    s.close()


def test_disappeared_entity_is_dropped_from_baseline_without_a_change(tmp_path):
    """Un'entità sparita non è un cambiamento di stato: è un buco di lettura.
    Segnalarla produrrebbe rumore a ogni riavvio di HA."""
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"light.a": "on", "light.b": "on"}, now="2026-08-04T08:00:00Z")
    changes = s.observe({"light.a": "on"}, now="2026-08-04T09:00:00Z")
    assert changes == []
    assert "light.b" not in s.baseline()
    s.close()


def test_last_changes_returns_the_most_recent_observation_only(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"light.a": "on"}, now="2026-08-04T08:00:00Z")
    s.observe({"light.a": "off"}, now="2026-08-04T09:00:00Z")
    assert [c["entity_id"] for c in s.last_changes()] == ["light.a"]
    s.observe({"light.a": "off"}, now="2026-08-04T10:00:00Z")
    assert s.last_changes() == []
    s.close()


def test_survives_reopen(tmp_path):
    path = str(tmp_path / "p.db")
    s = PortraitStore(path)
    s.observe({"light.a": "on"}, now="2026-08-04T08:00:00Z")
    s.close()
    s2 = PortraitStore(path)
    changes = s2.observe({"light.a": "off"}, now="2026-08-04T09:00:00Z")
    assert changes[0]["was"] == "on"
    s2.close()
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_portrait_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hiris.app.brain.portrait_store'`

- [ ] **Step 3: Scrivi l'implementazione minima**

Crea `hiris/app/brain/portrait_store.py`:

```python
"""Memoria dello stato notevole della casa, e del suo cambiamento.

Questo store e' l'UNICO scrittore del delta. Il delta risponde a "cosa e'
cambiato dall'ultima volta che HIRIS ha guardato", e per essere una risposta
sensata ha bisogno di un solo osservatore: se ogni consumatore aggiornasse la
linea di base, ciascuno vedrebbe solo cio' che e' cambiato dopo il precedente.
L'osservazione e' quindi un job dedicato (server.py), i consumatori LEGGONO.

Un'entita' SPARITA non produce un cambiamento: e' un buco di lettura, non un
fatto sulla casa, e segnalarla riempirebbe il delta a ogni riavvio di HA.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from ..storage import connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notable (
    entity_id TEXT PRIMARY KEY,
    state     TEXT NOT NULL,
    since     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS last_delta (
    entity_id TEXT PRIMARY KEY,
    was       TEXT,
    now_state TEXT NOT NULL,
    since     TEXT NOT NULL
);
"""

_VERSIONE_SCHEMA = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PortraitStore:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=_VERSIONE_SCHEMA)

    def observe(self, current: dict[str, str], *, now: str | None = None) -> list[dict]:
        """Confronta `current` con la linea di base, aggiorna entrambe le tabelle,
        ritorna i cambiamenti. Transazione unica con rollback esplicito."""
        ts = now or _now_iso()
        current = {str(k): str(v) for k, v in (current or {}).items()}
        with self._lock:
            try:
                prev = {
                    r["entity_id"]: {"state": r["state"], "since": r["since"]}
                    for r in self._conn.execute(
                        "SELECT entity_id, state, since FROM notable"
                    ).fetchall()
                }
                changes: list[dict] = []
                for eid, state in current.items():
                    old = prev.get(eid)
                    if old is None:
                        changes.append({"entity_id": eid, "was": None,
                                        "now": state, "since": ts})
                    elif old["state"] != state:
                        changes.append({"entity_id": eid, "was": old["state"],
                                        "now": state, "since": ts})
                # La primissima osservazione non e' un cambiamento: e' l'inizio.
                if not prev:
                    changes = []

                self._conn.execute("DELETE FROM notable")
                self._conn.executemany(
                    "INSERT INTO notable (entity_id, state, since) VALUES (?,?,?)",
                    [
                        (
                            eid,
                            state,
                            ts if (prev.get(eid) or {}).get("state") != state
                            else prev[eid]["since"],
                        )
                        for eid, state in current.items()
                    ],
                )
                self._conn.execute("DELETE FROM last_delta")
                self._conn.executemany(
                    "INSERT INTO last_delta (entity_id, was, now_state, since)"
                    " VALUES (?,?,?,?)",
                    [(c["entity_id"], c["was"], c["now"], c["since"]) for c in changes],
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return changes

    def last_changes(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT entity_id, was, now_state, since FROM last_delta"
                " ORDER BY entity_id"
            ).fetchall()
        return [
            {"entity_id": r["entity_id"], "was": r["was"],
             "now": r["now_state"], "since": r["since"]}
            for r in rows
        ]

    def baseline(self) -> dict[str, dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT entity_id, state, since FROM notable"
            ).fetchall()
        return {r["entity_id"]: {"state": r["state"], "since": r["since"]} for r in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_portrait_store.py -q`
Expected: PASS, 7 test

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/portrait_store.py tests/test_portrait_store.py
git commit -m "feat(ritratto): lo store del notevole e del delta"
```

---

## Task 2: cosa merita di essere detto

**Files:**
- Create: `hiris/app/brain/portrait.py`
- Test: `tests/test_portrait.py`

**Interfaces:**
- Consumes: la forma di stato di `EntityCache.all_states()` — dict con chiavi
  `id`, `state`, `name`, `unit`, `domain`, `device_class`, e `attributes` solo per alcuni domini.
  **Attenzione: la chiave è `id`, non `entity_id`.**
- Produces: `def notable_state(states: list[dict]) -> dict[str, str]`

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_portrait.py`:

```python
"""Il ritratto: funzioni pure di selezione, composizione e resa.

Il criterio che regge tutto: il notevole e' DISCRETO. Una porta e' aperta o
chiusa; una temperatura cambia sempre. Se i sensori numerici entrassero nel
notevole, il delta direbbe "tutto e' cambiato" a ogni giro -- cioe' niente.
"""
from hiris.app.brain.portrait import notable_state


def _s(eid, state, *, domain=None, device_class=None, name=None):
    return {
        "id": eid,
        "state": state,
        "name": name or eid,
        "unit": "",
        "domain": domain or eid.split(".")[0],
        "device_class": device_class,
    }


def test_discrete_domains_are_notable():
    out = notable_state([
        _s("light.cucina", "on"),
        _s("lock.ingresso", "locked"),
        _s("climate.salotto", "heat"),
        _s("alarm_control_panel.casa", "armed_away"),
    ])
    assert out == {
        "light.cucina": "on",
        "lock.ingresso": "locked",
        "climate.salotto": "heat",
        "alarm_control_panel.casa": "armed_away",
    }


def test_numeric_sensors_are_never_notable():
    out = notable_state([
        _s("sensor.temperatura", "21.4", device_class="temperature"),
        _s("sensor.potenza", "1230", device_class="power"),
        _s("sensor.umidita", "55", device_class="humidity"),
    ])
    assert out == {}


def test_binary_sensor_only_for_meaningful_classes():
    out = notable_state([
        _s("binary_sensor.porta", "on", device_class="door"),
        _s("binary_sensor.finestra", "off", device_class="window"),
        _s("binary_sensor.fumo", "off", device_class="smoke"),
        _s("binary_sensor.movimento", "on", device_class="motion"),
        _s("binary_sensor.presenza", "on", device_class="occupancy"),
    ])
    assert out == {
        "binary_sensor.porta": "on",
        "binary_sensor.finestra": "off",
        "binary_sensor.fumo": "off",
    }


def test_unreadable_states_are_skipped():
    out = notable_state([
        _s("light.a", "unavailable"),
        _s("light.b", "unknown"),
        _s("light.c", ""),
        _s("light.d", None),
        _s("light.e", "on"),
    ])
    assert out == {"light.e": "on"}


def test_malformed_rows_do_not_raise():
    out = notable_state([
        {"state": "on"},
        {"id": "light.a"},
        None,
        "non un dict",
        _s("light.ok", "on"),
    ])
    assert out == {"light.ok": "on"}


def test_state_is_clamped_and_sanitized():
    out = notable_state([_s("light.a", "on" + "x" * 500)])
    assert len(out["light.a"]) <= 120
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_portrait.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hiris.app.brain.portrait'`

- [ ] **Step 3: Scrivi l'implementazione minima**

Crea `hiris/app/brain/portrait.py`:

```python
"""Il ritratto della casa: cosa HIRIS sa, in forma componibile e resa.

Tutte le funzioni qui sono PURE: prendono dati, ritornano dati, non leggono
niente e non scrivono niente. Le fonti sono iniettate dal chiamante
(server.py), cosi' il ritratto e' interamente testabile senza Home Assistant.

IL NOTEVOLE E' DISCRETO. Una porta e' aperta o chiusa, una serratura e'
chiusa o aperta, un termostato scalda o no: sono fatti che cambiano di rado e
il cui cambiamento significa qualcosa. Una temperatura, una potenza,
un'umidita' cambiano di continuo: metterle nel notevole vorrebbe dire che a
ogni osservazione "e' cambiato tutto", che e' lo stesso che dire niente. I
numeri restano disponibili al ragionamento tramite gli strumenti di lettura;
non entrano nella memoria del cambiamento.
"""
from __future__ import annotations

from ..proxy._sanitize import sanitize_ha_value

# Domini il cui stato e' per natura discreto.
_NOTABLE_DOMAINS = frozenset({
    "light", "switch", "lock", "cover", "climate", "alarm_control_panel",
    "fan", "media_player", "person", "device_tracker", "valve", "water_heater",
    "vacuum",
})

# I binary_sensor entrano SOLO con queste classi: sono quelle il cui
# cambiamento e' un evento della casa. Volutamente ESCLUSE motion/occupancy:
# cambiano decine di volte l'ora e sommergerebbero il delta.
_NOTABLE_BINARY_CLASSES = frozenset({
    "door", "window", "garage_door", "opening",
    "smoke", "gas", "moisture", "problem", "safety", "tamper",
})

_UNREADABLE = frozenset({"unavailable", "unknown", ""})


def notable_state(states: list[dict]) -> dict[str, str]:
    """entity_id -> stato, per le sole entita' il cui stato merita memoria.

    `states` ha la forma di EntityCache.all_states(): la chiave dell'id e'
    ``id``, non ``entity_id``.
    """
    out: dict[str, str] = {}
    for raw in states or []:
        if not isinstance(raw, dict):
            continue
        eid = raw.get("id")
        state = raw.get("state")
        if not eid or not isinstance(state, str):
            continue
        if state.strip().lower() in _UNREADABLE:
            continue
        domain = raw.get("domain") or str(eid).split(".")[0]
        if domain == "binary_sensor":
            if (raw.get("device_class") or "") not in _NOTABLE_BINARY_CLASSES:
                continue
        elif domain not in _NOTABLE_DOMAINS:
            continue
        out[str(eid)] = sanitize_ha_value(state)
    return out
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_portrait.py -q`
Expected: PASS, 6 test

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/portrait.py tests/test_portrait.py
git commit -m "feat(ritratto): il notevole e' discreto, non continuo"
```

---

## Task 3: comporre il ritratto

**Files:**
- Modify: `hiris/app/brain/portrait.py`
- Test: `tests/test_portrait.py`

**Interfaces:**
- Consumes: `notable_state` (Task 2); `PortraitStore.baseline()` e `.last_changes()` (Task 1);
  la mappa aree di `EntityCache.get_area_map()` → `dict[str, list[str]]` con chiave speciale
  `"__no_area__"`.
- Produces:
  ```python
  def build_portrait(*, area_map: dict | None, states: list[dict],
                     baseline: dict, changes: list[dict]) -> dict
  ```
  Ritorna `{"aree": {area: {"acceso": [...], "aperto": [...], "allerta": [...]}},
  "cambiato": [...], "conteggi": {"entita": int, "aree": int}}`.
  **`allerta`** raccoglie i `binary_sensor` con classe `smoke`/`gas`/`moisture`/`problem`/
  `safety`/`tamper`: sono allarmi, non aperture, e nella resa vengono per primi.

- [ ] **Step 1: Scrivi il test che fallisce**

Aggiungi in fondo a `tests/test_portrait.py`:

```python
from hiris.app.brain.portrait import build_portrait


def test_build_groups_open_and_on_by_area():
    p = build_portrait(
        area_map={
            "Cucina": ["light.cucina", "binary_sensor.finestra_cucina"],
            "Ingresso": ["lock.ingresso"],
        },
        states=[
            _s("light.cucina", "on", name="Luce cucina"),
            _s("binary_sensor.finestra_cucina", "on",
               device_class="window", name="Finestra cucina"),
            _s("lock.ingresso", "locked", name="Serratura"),
        ],
        baseline={},
        changes=[],
    )
    assert p["aree"]["Cucina"]["acceso"] == ["Luce cucina"]
    assert p["aree"]["Cucina"]["aperto"] == ["Finestra cucina"]
    assert "Ingresso" not in p["aree"]
    assert p["conteggi"] == {"entita": 3, "aree": 2}


def test_build_reports_changes_with_friendly_names():
    p = build_portrait(
        area_map={"Cucina": ["light.cucina"]},
        states=[_s("light.cucina", "off", name="Luce cucina")],
        baseline={},
        changes=[{"entity_id": "light.cucina", "was": "on",
                  "now": "off", "since": "2026-08-04T09:00:00Z"}],
    )
    assert p["cambiato"] == [
        {"nome": "Luce cucina", "entity_id": "light.cucina",
         "was": "on", "now": "off", "since": "2026-08-04T09:00:00Z"}
    ]


def test_build_uses_since_from_baseline_for_open_things():
    p = build_portrait(
        area_map={"Cucina": ["binary_sensor.finestra"]},
        states=[_s("binary_sensor.finestra", "on",
                   device_class="window", name="Finestra")],
        baseline={"binary_sensor.finestra":
                  {"state": "on", "since": "2026-08-04T07:00:00Z"}},
        changes=[],
    )
    assert p["aree"]["Cucina"]["aperto"] == ["Finestra (da 2026-08-04T07:00:00Z)"]


def test_build_tolerates_missing_area_map():
    p = build_portrait(
        area_map=None,
        states=[_s("light.a", "on", name="Luce")],
        baseline={}, changes=[],
    )
    assert p["aree"] == {}
    assert p["conteggi"]["aree"] == 0


def test_build_never_raises_on_garbage():
    p = build_portrait(area_map={"X": None}, states=None,
                       baseline=None, changes=None)
    assert p["aree"] == {} and p["cambiato"] == []


def test_alarm_sensors_go_to_their_own_bucket_not_to_open():
    """Un rilevatore di fumo che scatta non e' una finestra socchiusa."""
    p = build_portrait(
        area_map={"Cucina": ["binary_sensor.fumo", "binary_sensor.finestra"]},
        states=[
            _s("binary_sensor.fumo", "on", device_class="smoke", name="Fumo"),
            _s("binary_sensor.finestra", "on",
               device_class="window", name="Finestra"),
        ],
        baseline={}, changes=[],
    )
    assert p["aree"]["Cucina"]["allerta"] == ["Fumo"]
    assert p["aree"]["Cucina"]["aperto"] == ["Finestra"]
    assert p["aree"]["Cucina"]["acceso"] == []


def test_an_area_with_only_an_alarm_is_still_reported():
    p = build_portrait(
        area_map={"Sottotetto": ["binary_sensor.allagamento"]},
        states=[_s("binary_sensor.allagamento", "on",
                   device_class="moisture", name="Allagamento")],
        baseline={}, changes=[],
    )
    assert p["aree"]["Sottotetto"]["allerta"] == ["Allagamento"]


def test_change_states_are_sanitized():
    """was/now sono stati di entita' HA: il vincolo globale vale anche qui."""
    p = build_portrait(
        area_map={}, states=[_s("light.a", "off", name="Luce")],
        baseline={},
        changes=[{"entity_id": "light.a", "was": "x" * 500,
                  "now": "y" * 500, "since": "2026-08-04T09:00:00Z"}],
    )
    assert len(p["cambiato"][0]["was"]) <= 120
    assert len(p["cambiato"][0]["now"]) <= 120


def test_change_with_no_previous_state_keeps_none():
    p = build_portrait(
        area_map={}, states=[_s("light.a", "on", name="Luce")],
        baseline={},
        changes=[{"entity_id": "light.a", "was": None,
                  "now": "on", "since": "2026-08-04T09:00:00Z"}],
    )
    assert p["cambiato"][0]["was"] is None
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_portrait.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_portrait'`

- [ ] **Step 3: Scrivi l'implementazione minima**

Aggiungi in fondo a `hiris/app/brain/portrait.py`:

```python
_ACCESO = frozenset({"on", "open", "heat", "cool", "heat_cool", "auto", "playing",
                     "cleaning", "unlocked"})
_APERTO_DOMINI = frozenset({"cover", "valve"})

# Un rilevatore di fumo che scatta NON e' un'apertura: e' un allarme, ed e' la
# cosa piu' importante che una casa possa dire. Queste classi hanno un secchio
# proprio, che nella resa viene per primo.
_ALLERTA_CLASSES = frozenset({"smoke", "gas", "moisture", "problem", "safety",
                              "tamper"})


def _meta(states: list[dict]) -> dict[str, dict]:
    """entity_id -> {"nome": str sanificato, "dc": device_class}."""
    out: dict[str, dict] = {}
    for raw in states or []:
        if isinstance(raw, dict) and raw.get("id"):
            out[str(raw["id"])] = {
                "nome": sanitize_ha_value(str(raw.get("name") or raw["id"])),
                "dc": str(raw.get("device_class") or ""),
            }
    return out


def build_portrait(*, area_map, states, baseline, changes) -> dict:
    """Compone il ritratto. Non solleva mai: ogni fonte assente degrada a vuoto."""
    meta = _meta(states)
    notable = notable_state(states or [])
    base = baseline if isinstance(baseline, dict) else {}

    aree: dict[str, dict] = {}
    for area, eids in (area_map or {}).items():
        if not isinstance(eids, (list, tuple)) or area == "__no_area__":
            continue
        acceso: list[str] = []
        aperto: list[str] = []
        allerta: list[str] = []
        for eid in eids:
            stato = notable.get(str(eid))
            if stato is None or stato.lower() not in _ACCESO:
                continue
            info = meta.get(str(eid)) or {}
            nome = info.get("nome") or str(eid)
            since = (base.get(str(eid)) or {}).get("since")
            etichetta = f"{nome} (da {since})" if since else nome
            dominio = str(eid).split(".")[0]
            if dominio == "binary_sensor" and info.get("dc") in _ALLERTA_CLASSES:
                allerta.append(etichetta)
            elif dominio in _APERTO_DOMINI or dominio == "binary_sensor":
                aperto.append(etichetta)
            else:
                acceso.append(etichetta)
        if acceso or aperto or allerta:
            aree[str(area)] = {"acceso": acceso, "aperto": aperto,
                               "allerta": allerta}

    cambiato = []
    for c in (changes or []):
        if not isinstance(c, dict) or not c.get("entity_id"):
            continue
        eid = str(c["entity_id"])
        was = c.get("was")
        now_ = c.get("now")
        cambiato.append({
            "nome": (meta.get(eid) or {}).get("nome") or eid, "entity_id": eid,
            # `was` e `now` sono stati di entita' HA come tutti gli altri: il
            # vincolo globale vale anche qui.
            "was": sanitize_ha_value(str(was)) if was is not None else None,
            "now": sanitize_ha_value(str(now_)) if now_ is not None else None,
            "since": c.get("since"),
        })

    return {
        "aree": aree,
        "cambiato": cambiato,
        "conteggi": {
            "entita": len(meta),
            "aree": len([a for a in (area_map or {}) if a != "__no_area__"]),
        },
    }
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_portrait.py -q`
Expected: PASS, 15 test

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/portrait.py tests/test_portrait.py
git commit -m "feat(ritratto): comporre aree, acceso, aperto e cambiato"
```

---

## Task 4: rendere il ritratto leggibile e limitato

**Files:**
- Modify: `hiris/app/brain/portrait.py`
- Test: `tests/test_portrait.py`

**Interfaces:**
- Consumes: l'output di `build_portrait` (Task 3)
- Produces: `def render_portrait(portrait: dict, *, max_chars: int = 1800) -> str`
  Ritorna `""` se non c'è niente da dire — il chiamante userà quel `""` per **non** aggiungere
  alcun blocco al prompt.

- [ ] **Step 1: Scrivi il test che fallisce**

Aggiungi in fondo a `tests/test_portrait.py`:

```python
from hiris.app.brain.portrait import render_portrait


def test_render_empty_portrait_is_empty_string():
    assert render_portrait({"aree": {}, "cambiato": [],
                            "conteggi": {"entita": 0, "aree": 0}}) == ""


def test_render_has_both_sections():
    txt = render_portrait({
        "aree": {"Cucina": {"acceso": ["Luce cucina"], "aperto": ["Finestra"]}},
        "cambiato": [{"nome": "Luce cucina", "entity_id": "light.cucina",
                      "was": "off", "now": "on", "since": "2026-08-04T09:00:00Z"}],
        "conteggi": {"entita": 42, "aree": 5},
    })
    assert "Com'e' la casa" in txt
    assert "Cucina" in txt and "Luce cucina" in txt and "Finestra" in txt
    assert "Cos'e' cambiato" in txt
    assert "off" in txt and "on" in txt


def test_render_omits_the_change_section_when_nothing_changed():
    txt = render_portrait({
        "aree": {"Cucina": {"acceso": ["Luce"], "aperto": []}},
        "cambiato": [], "conteggi": {"entita": 1, "aree": 1},
    })
    assert "Com'e' la casa" in txt
    assert "Cos'e' cambiato" not in txt


def test_render_is_bounded():
    aree = {f"Area{i}": {"acceso": [f"Luce {i}-{j}" for j in range(50)],
                         "aperto": []} for i in range(30)}
    txt = render_portrait({"aree": aree, "cambiato": [],
                           "conteggi": {"entita": 1500, "aree": 30}},
                          max_chars=500)
    assert len(txt) <= 500


def test_render_never_raises_on_garbage():
    assert render_portrait(None) == ""
    assert render_portrait({"aree": "non un dict"}) == ""


def test_render_puts_alarms_first():
    """Un rilevatore scattato e' la cosa piu' importante che la casa dica:
    non deve finire in fondo a una riga fra le luci accese."""
    txt = render_portrait({
        "aree": {
            "Cucina": {"acceso": ["Luce"], "aperto": ["Finestra"],
                       "allerta": ["Fumo"]},
            "Salotto": {"acceso": ["Lampada"], "aperto": [], "allerta": []},
        },
        "cambiato": [],
        "conteggi": {"entita": 4, "aree": 2},
    })
    assert txt.startswith("ALLERTA:")
    assert "- Cucina: Fumo" in txt
    assert txt.index("ALLERTA:") < txt.index("Com'e' la casa:")
    # l'allerta non viene ripetuta fra le aperture
    assert "aperto: Finestra" in txt and "aperto: Finestra, Fumo" not in txt


def test_render_omits_the_alarm_section_when_there_are_none():
    txt = render_portrait({
        "aree": {"Cucina": {"acceso": ["Luce"], "aperto": [], "allerta": []}},
        "cambiato": [], "conteggi": {"entita": 1, "aree": 1},
    })
    assert "ALLERTA" not in txt
    assert txt.startswith("Com'e' la casa:")


def test_render_with_only_an_alarm_has_no_empty_house_header():
    txt = render_portrait({
        "aree": {"Sottotetto": {"acceso": [], "aperto": [],
                                "allerta": ["Allagamento"]}},
        "cambiato": [], "conteggi": {"entita": 1, "aree": 1},
    })
    assert "ALLERTA:" in txt and "Allagamento" in txt
    assert "Com'e' la casa:" not in txt


def test_render_starts_with_the_change_section_when_it_is_the_only_one():
    txt = render_portrait({
        "aree": {},
        "cambiato": [{"nome": "Luce", "entity_id": "light.a",
                      "was": "on", "now": "off",
                      "since": "2026-08-04T09:00:00Z"}],
        "conteggi": {"entita": 1, "aree": 0},
    })
    assert txt.startswith("Cos'e' cambiato dall'ultima volta:")
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_portrait.py -q`
Expected: FAIL — `ImportError: cannot import name 'render_portrait'`

- [ ] **Step 3: Scrivi l'implementazione minima**

Aggiungi in fondo a `hiris/app/brain/portrait.py`:

```python
def render_portrait(portrait, *, max_chars: int = 1800) -> str:
    """Blocco leggibile per il prompt. Stringa vuota se non c'e' niente da dire.

    Il chiamante deve trattare "" come "nessun blocco": e' il contratto che
    tiene i prompt identici a prima quando il ritratto non e' disponibile.
    """
    try:
        p = portrait if isinstance(portrait, dict) else {}
        aree = p.get("aree")
        aree = aree if isinstance(aree, dict) else {}
        cambiato = p.get("cambiato")
        cambiato = cambiato if isinstance(cambiato, list) else []
        if not aree and not cambiato:
            return ""

        righe: list[str] = []

        # L'allerta viene PRIMA di tutto: un rilevatore che ha scattato e' la
        # cosa piu' importante che la casa possa dire, e non deve finire in
        # fondo a una riga fra le luci accese.
        allerte = [
            f"- {area}: " + ", ".join(str(x) for x in
                                      ((aree.get(area) or {}).get("allerta") or []))
            for area in sorted(aree)
            if (aree.get(area) or {}).get("allerta")
        ]
        if allerte:
            righe.append("ALLERTA:")
            righe.extend(allerte)
            righe.append("")

        casa: list[str] = []
        for area in sorted(aree):
            dati = aree.get(area) or {}
            parti: list[str] = []
            acceso = dati.get("acceso") or []
            aperto = dati.get("aperto") or []
            if acceso:
                parti.append("acceso: " + ", ".join(str(x) for x in acceso))
            if aperto:
                parti.append("aperto: " + ", ".join(str(x) for x in aperto))
            if parti:
                casa.append(f"- {area} — " + " · ".join(parti))
        # L'intestazione solo se ha qualcosa sotto: una casa in cui l'unica cosa
        # da dire e' un allarme non deve mostrare "Com'e' la casa:" a vuoto.
        if casa:
            righe.append("Com'e' la casa:")
            righe.extend(casa)

        if cambiato:
            if righe:
                righe.append("")
            righe.append("Cos'e' cambiato dall'ultima volta:")
            for c in cambiato:
                if not isinstance(c, dict):
                    continue
                nome = c.get("nome") or c.get("entity_id") or "?"
                was = c.get("was")
                da = f"da {was} " if was is not None else ""
                righe.append(f"- {nome}: {da}a {c.get('now')}")

        testo = "\n".join(righe)
        if len(testo) > max_chars:
            testo = testo[: max(0, max_chars - 1)].rstrip() + "…"
        return testo
    except Exception:
        return ""
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_portrait.py -q`
Expected: PASS, 24 test

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/portrait.py tests/test_portrait.py
git commit -m "feat(ritratto): resa leggibile e limitata"
```

---

## Task 5: l'osservazione periodica

**Files:**
- Modify: `hiris/app/server.py`
- Test: `tests/test_portrait_wiring.py` (nuovo)

**Interfaces:**
- Consumes: `PortraitStore` (Task 1), `notable_state` (Task 2), `EntityCache.all_states()`
- Produces: `app["portrait_store"]`; helper module-level
  `async def _osserva_la_casa(app) -> int` che ritorna il numero di cambiamenti registrati;
  job APScheduler `hiris_portrait_observe`.

**Nota per chi implementa:** `_osserva_la_casa` va scritta a **livello di modulo**, non dentro
`_on_startup`, esattamente come `_reason_memory_context` (`server.py:881`). È l'unico modo per
testarla passando un `dict` al posto dell'app.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_portrait_wiring.py`:

```python
"""Osservazione periodica e cablaggio del ritratto.

I test di cablaggio leggono il sorgente di _on_startup perche' gli helper
interni sono closure non raggiungibili: stessa convenzione di
tests/test_gather_context_memory.py.
"""
import inspect

import pytest

from hiris.app import server
from hiris.app.brain.portrait_store import PortraitStore


class _FakeCache:
    def __init__(self, states):
        self._states = states

    def all_states(self):
        return self._states


class _RaisingCache:
    def all_states(self):
        raise RuntimeError("cache boom")


@pytest.mark.asyncio
async def test_observation_records_changes(tmp_path):
    store = PortraitStore(str(tmp_path / "p.db"))
    app = {"portrait_store": store,
           "entity_cache": _FakeCache([
               {"id": "light.a", "state": "on", "name": "A",
                "domain": "light", "device_class": None, "unit": ""}
           ])}
    assert await server._osserva_la_casa(app) == 0
    app["entity_cache"] = _FakeCache([
        {"id": "light.a", "state": "off", "name": "A",
         "domain": "light", "device_class": None, "unit": ""}
    ])
    assert await server._osserva_la_casa(app) == 1
    assert store.last_changes()[0]["was"] == "on"
    store.close()


@pytest.mark.asyncio
async def test_observation_is_failure_safe(tmp_path):
    store = PortraitStore(str(tmp_path / "p.db"))
    assert await server._osserva_la_casa({"portrait_store": store,
                                          "entity_cache": _RaisingCache()}) == 0
    assert await server._osserva_la_casa({}) == 0
    assert await server._osserva_la_casa(None) == 0
    store.close()


def test_observation_job_is_registered():
    src = inspect.getsource(server._on_startup)
    assert "hiris_portrait_observe" in src
    assert "_osserva_la_casa(app)" in src
    assert 'app["portrait_store"]' in src
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_portrait_wiring.py -q`
Expected: FAIL — `AttributeError: module 'hiris.app.server' has no attribute '_osserva_la_casa'`

- [ ] **Step 3: Scrivi l'implementazione minima**

**3a.** In `hiris/app/server.py`, subito **dopo** la fine di `_reason_memory_context`
(cioè dopo la riga 917), aggiungi a livello di modulo:

```python
async def _osserva_la_casa(app) -> int:
    """Registra lo stato notevole della casa e ne calcola il cambiamento.

    E' l'UNICO scrittore della linea di base del ritratto: i consumatori
    leggono soltanto. Se aggiornasse la linea di base ogni consumatore,
    ciascuno vedrebbe solo cio' che e' cambiato dopo il precedente, e il
    delta smetterebbe di voler dire "dall'ultima volta che ho guardato".

    Non solleva mai: un'osservazione saltata e' un delta piu' vecchio, non un
    giro di scheduler perso.
    """
    try:
        store = app.get("portrait_store") if app is not None else None
        cache = app.get("entity_cache") if app is not None else None
        if store is None or cache is None or not hasattr(cache, "all_states"):
            return 0
        from .brain.portrait import notable_state
        changes = store.observe(notable_state(cache.all_states()))
        return len(changes)
    except Exception:
        logger.warning("_osserva_la_casa: osservazione fallita", exc_info=True)
        return 0
```

**3b.** In `_on_startup`, accanto agli altri store (subito **dopo** la riga che crea
`advisory_store`, intorno a `server.py:1622`), aggiungi:

```python
    from .brain.portrait_store import PortraitStore
    app["portrait_store"] = PortraitStore(os.path.join(data_dir, "portrait.db"))
    logger.info("PortraitStore ready")
```

**3c.** In `_on_startup`, accanto alla registrazione del job `hiris_health_scan`
(intorno a `server.py:2424-2427`), aggiungi:

```python
    async def _portrait_observe_job():
        try:
            n = await _osserva_la_casa(app)
            if n:
                logger.info("ritratto: %d cambiamenti registrati", n)
        except Exception:
            logger.warning("portrait observe job failed", exc_info=True)

    engine._scheduler.add_job(
        _portrait_observe_job, "interval",
        minutes=int(os.environ.get("HIRIS_PORTRAIT_OBSERVE_MINUTES", "15")),
        id="hiris_portrait_observe", replace_existing=True,
        misfire_grace_time=300,
    )
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_portrait_wiring.py -q`
Expected: PASS, 3 test

- [ ] **Step 5: Commit**

```bash
git add hiris/app/server.py tests/test_portrait_wiring.py
git commit -m "feat(ritratto): l'osservazione periodica, unico scrittore del delta"
```

---

## Task 6: il ritratto arriva al ragionatore per-evento

**Files:**
- Modify: `hiris/app/server.py` (helper module-level + `_gather_context`)
- Modify: `hiris/app/watcher/reasoner.py:41-62`
- Modify: `tests/test_gather_context_memory.py` (i test di cablaggio esistenti)
- Test: `tests/test_portrait_wiring.py`, `tests/test_sentinel_reasoner.py`

**Interfaces:**
- Consumes: `build_portrait`, `render_portrait` (Task 3-4), `PortraitStore` (Task 1)
- Produces: `def _portrait_context(app) -> str` (module-level in `server.py`);
  la chiave `"portrait"` nel dict di `_gather_context`; il blocco reso da `build_user_message`.

- [ ] **Step 1: Scrivi il test che fallisce**

Aggiungi in fondo a `tests/test_portrait_wiring.py`:

```python
from hiris.app.watcher.reasoner import build_user_message
from hiris.app.watcher.signals import WakeEvent


class _FakeCacheWithAreas(_FakeCache):
    def get_area_map(self):
        return {"Cucina": ["light.a"]}


def test_portrait_context_returns_rendered_block(tmp_path):
    store = PortraitStore(str(tmp_path / "p.db"))
    states = [{"id": "light.a", "state": "on", "name": "Luce",
               "domain": "light", "device_class": None, "unit": ""}]
    store.observe({"light.a": "on"}, now="2026-08-04T08:00:00Z")
    txt = server._portrait_context({"portrait_store": store,
                                    "entity_cache": _FakeCacheWithAreas(states)})
    assert "Com'e' la casa" in txt and "Luce" in txt
    store.close()


def test_portrait_context_is_failure_safe():
    assert server._portrait_context({}) == ""
    assert server._portrait_context(None) == ""
    assert server._portrait_context({"entity_cache": _RaisingCache()}) == ""


def test_user_message_renders_the_portrait_block():
    we = WakeEvent("battery", "sensor.b", "info", {"pct": 8}, 1.0)
    msg = build_user_message(we, {"friendly_name": "Batt",
                                  "portrait": "Com'e' la casa:\n- Cucina — acceso: Luce"})
    assert "Com'e' la casa:" in msg
    assert "portrait" not in msg  # estratta dal context, non finita nel json
    assert msg.index("Com'e' la casa:") < msg.index("Valuta e rispondi")


def test_user_message_is_unchanged_when_portrait_absent_or_empty():
    we = WakeEvent("battery", "sensor.b", "info", {"pct": 8}, 1.0)
    base = build_user_message(we, {"friendly_name": "Batt"})
    assert build_user_message(we, {"friendly_name": "Batt", "portrait": ""}) == base
    assert build_user_message(we, {"friendly_name": "Batt", "portrait": None}) == base


def test_long_portrait_survives_sanitization():
    """sanitize_ha_value tronca ogni valore a 120 caratteri. Se il ritratto
    passasse da _san insieme al resto del context arriverebbe al prompt mozzato
    alla prima riga, in silenzio. Va estratto PRIMA della sanificazione."""
    we = WakeEvent("battery", "sensor.b", "info", {"pct": 8}, 1.0)
    lungo = "Com'e' la casa:\n" + "\n".join(f"- Area{i} — acceso: Luce{i}"
                                            for i in range(60))
    assert len(lungo) > 1000
    msg = build_user_message(we, {"friendly_name": "Batt", "portrait": lungo})
    assert "Area59" in msg
    assert len(msg) > 1000


def test_gather_context_is_wired_to_the_portrait():
    src = inspect.getsource(server._on_startup)
    assert "_portrait_context(app)" in src
    assert '"portrait"' in src
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_portrait_wiring.py -q`
Expected: FAIL — `AttributeError: module 'hiris.app.server' has no attribute '_portrait_context'`

- [ ] **Step 3: Scrivi l'implementazione minima**

**3a.** In `hiris/app/server.py`, subito dopo `_osserva_la_casa`, aggiungi:

```python
def _portrait_context(app) -> str:
    """Il ritratto reso, pronto per il prompt. "" se non disponibile.

    Sincrona di proposito: legge solo la cache in memoria e lo store locale,
    nessun I/O verso Home Assistant.
    """
    try:
        store = app.get("portrait_store") if app is not None else None
        cache = app.get("entity_cache") if app is not None else None
        if store is None or cache is None or not hasattr(cache, "all_states"):
            return ""
        from .brain.portrait import build_portrait, render_portrait
        area_map = cache.get_area_map() if hasattr(cache, "get_area_map") else None
        return render_portrait(build_portrait(
            area_map=area_map, states=cache.all_states(),
            baseline=store.baseline(), changes=store.last_changes(),
        ))
    except Exception:
        logger.warning("_portrait_context: ritratto non disponibile", exc_info=True)
        return ""
```

**3b.** In `_on_startup`, sostituisci la `return` finale di `_gather_context`
(`server.py:1708`) con:

```python
        return {"friendly_name": friendly_name, "memory": mem,
                "portrait": _portrait_context(app)}
```

e sostituisci le due `return` di fallback (righe 1694 e 1707) con:

```python
            return {"friendly_name": wake.entity_id, "portrait": _portrait_context(app)}
```
```python
            return {"friendly_name": friendly_name, "portrait": _portrait_context(app)}
```

**3c.** In `hiris/app/watcher/reasoner.py`, **sostituisci** la riga 43
(`ctx = _san(dict(context or {}))`) con le quattro righe seguenti:

```python
    # ATTENZIONE: il ritratto va estratto PRIMA di _san. sanitize_ha_value
    # tronca ogni valore a 120 caratteri: un ritratto da ~1800 arriverebbe al
    # prompt mozzato alla prima riga, in silenzio e con i test verdi. E' gia'
    # sanificato alla fonte, stringa per stringa (brain/portrait.py: sia
    # notable_state sia _nomi passano da sanitize_ha_value).
    _raw_ctx = dict(context or {})
    portrait = _raw_ctx.pop("portrait", None)
    ctx = _san(_raw_ctx)
```

e subito dopo la riga `memory = ctx.pop("memory", None)` aggiungi:

```python
    portrait_block = ""
    if isinstance(portrait, str) and portrait.strip():
        # "" significa "nessun blocco": e' il contratto che tiene il messaggio
        # identico a prima quando il ritratto non c'e'.
        portrait_block = f"{portrait.strip()}\n\n"
```

e nella f-string di ritorno (righe 56-62) inserisci `{portrait_block}` **prima** di
`{memory_block}`:

```python
    return (
        f"Segnale: {wake.signal_kind} su {wake.entity_id}\n"
        f"Evidenza: {json.dumps(ev, ensure_ascii=False)}\n"
        f"Contesto: {json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"{portrait_block}"
        f"{memory_block}"
        "Valuta e rispondi con il blocco json richiesto."
    )
```

**3d.** In `tests/test_gather_context_memory.py`, il test di cablaggio
`test_gather_context_is_async_and_wired_to_memory_helper` asserisce `'"memory": mem' in src`.
Quella stringa **esiste ancora** nella nuova `return`, quindi il test continua a passare — ma
verifica eseguendolo, ed è il momento di aggiungere lì l'asserzione gemella se manca.

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_portrait_wiring.py tests/test_gather_context_memory.py tests/test_sentinel_reasoner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/server.py hiris/app/watcher/reasoner.py tests/test_portrait_wiring.py
git commit -m "feat(ritratto): il ragionatore per-evento vede la casa"
```

---

## Task 7: il ritratto arriva alla revisione olistica

**Files:**
- Modify: `hiris/app/brain/coverage_review.py:23-60`
- Modify: `hiris/app/server.py:2293` (il call site di `build_review_context`)
- Test: `tests/test_coverage_review_memory.py` (aggiunte), `tests/test_portrait_wiring.py`

**Interfaces:**
- Consumes: `_portrait_context` (Task 6)
- Produces: `build_review_context(..., portrait=None)` e il blocco corrispondente in
  `build_review_message`.

**Vincolo:** esiste un test di byte-identità
(`test_build_review_message_byte_identical_when_memory_absent_or_empty`). La chiave `portrait`
deve essere aggiunta al context **solo se non vuota**, altrimenti quel test si rompe.

- [ ] **Step 1: Scrivi il test che fallisce**

Aggiungi in fondo a `tests/test_coverage_review_memory.py`:

```python
def test_portrait_absent_keeps_context_and_message_identical():
    base_ctx = build_review_context({}, [], {})
    assert build_review_context({}, [], {}, portrait="") == base_ctx
    assert build_review_context({}, [], {}, portrait=None) == base_ctx
    assert "portrait" not in base_ctx
    assert build_review_message(base_ctx) == build_review_message(
        build_review_context({}, [], {}, portrait="")
    )


def test_portrait_present_is_rendered_before_the_instruction():
    ctx = build_review_context({}, [], {}, portrait="Com'e' la casa:\n- Cucina")
    assert ctx["portrait"] == "Com'e' la casa:\n- Cucina"
    msg = build_review_message(ctx)
    assert "Com'e' la casa:" in msg
    assert "portrait" not in msg
    assert msg.index("Com'e' la casa:") < msg.index("Proponi coperture")
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_coverage_review_memory.py -q`
Expected: FAIL — `TypeError: build_review_context() got an unexpected keyword argument 'portrait'`

- [ ] **Step 3: Scrivi l'implementazione minima**

**3a.** In `hiris/app/brain/coverage_review.py`, cambia la firma (riga 23) in:

```python
def build_review_context(snapshot, inventory, current_config, memory=None,
                         portrait=None) -> dict:
```

e subito **dopo** il blocco `if memory:` (riga 39), aggiungi:

```python
    if isinstance(portrait, str) and portrait.strip():
        # Solo-se-non-vuoto, come per `memory`: mantiene byte-identico il
        # messaggio quando il ritratto non e' disponibile (test di
        # byte-identita' in tests/test_coverage_review_memory.py).
        ctx["portrait"] = portrait.strip()
```

**3b.** In `build_review_message` (riga 42), dopo `memory = ctx.pop("memory", None)` aggiungi:

```python
    portrait = ctx.pop("portrait", None)
    portrait_block = ""
    if isinstance(portrait, str) and portrait.strip():
        portrait_block = f"{portrait.strip()}\n\n"
```

e nella `return` finale inserisci `portrait_block` **prima** di `memory_block`:

```python
    return ("Inventario + config attuale:\n" + json.dumps(ctx, ensure_ascii=False)
            + "\n\n" + portrait_block + memory_block
            + "Proponi coperture/gestioni col blocco json richiesto.")
```

**3c.** In `hiris/app/server.py:2293`, cambia il call site in:

```python
                _ctx = build_review_context(snapshot, _inventory, _current,
                                            memory=_mem,
                                            portrait=_portrait_context(app))
```

**3d.** Aggiungi in fondo a `tests/test_portrait_wiring.py`:

```python
def test_holistic_is_wired_to_the_portrait():
    src = inspect.getsource(server._on_startup)
    assert "portrait=_portrait_context(app)" in src
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_coverage_review_memory.py tests/test_coverage_wiring.py tests/test_portrait_wiring.py -q`
Expected: PASS

- [ ] **Step 5: Esegui la suite intera**

Run: `python -m pytest -q`
Expected: PASS, ~2090 test (i ~2071 esistenti più i nuovi). **Nessun test preesistente deve
fallire**: se `tests/test_gather_context_memory.py` o `tests/test_coverage_wiring.py` si rompono,
aggiornali nello stesso commit — leggono il sorgente di `_on_startup`, che hai modificato.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/brain/coverage_review.py hiris/app/server.py \
        tests/test_coverage_review_memory.py tests/test_portrait_wiring.py
git commit -m "feat(ritratto): la revisione olistica vede la casa e il suo cambiamento"
```

---

## Verifica live (obbligatoria prima di dire che funziona)

La suite verde non è una prova — è la regola non negoziabile di questo progetto.

1. Bumpa la versione in `hiris/config.yaml` e aggiorna l'add-on.
2. Nei log dell'add-on cerca `PortraitStore ready` all'avvio.
3. Dopo 15 minuti, accendi e spegni una luce; al giro successivo il log deve mostrare
   `ritratto: N cambiamenti registrati`.
4. Verifica che `/data/portrait.db` esista e contenga righe:
   `sqlite3 /data/portrait.db "SELECT COUNT(*) FROM notable;"`
5. Provoca un risveglio della Sentinella (abilita un rilevatore su un'entità che puoi muovere) e
   controlla nei log che il prompt contenga il blocco `Com'e' la casa:`.
6. Controlla che **niente sia peggiorato**: la chat risponde, il resoconto delle 08:00 parte, la
   Dashboard carica.

## Cosa questa fetta NON fa

- Non tocca la memoria, il RAG, il second brain, gli insight — è la **Fetta 2**.
- Non filtra il ritratto per perimetro d'agente — è la **Fetta 3**, e serve il perimetro
  dell'Atto 3.
- Non rimuove niente: `watcher/snapshot.py` e la mappa semantica restano dove sono. La potatura
  è l'**Atto 4**, e va fatta quando il sostituto è vivo e verificato.
