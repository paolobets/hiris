"""Le colonne dei token: il registro sa dire QUANTO, non solo DI COSA.

Spec `docs/design/2026-09-28-le-misure-complete.md` §2. Le colonne nascono
NULL, e NULL resta cio' che non e' stato misurato: una riga del 24/09 non ha i
token, e dire zero sarebbe affermare che quel giro non e' costato niente.
"""
import sqlite3

from hiris.app.usage.store import TOKEN_COLUMNS, UsageStore


def _archivio(tmp_path):
    return UsageStore(str(tmp_path / "consumi.db"))


def test_un_giro_porta_i_suoi_token(tmp_path):
    """Mutazione ESEGUITA: non passare `cache_write_tokens` all'INSERT -- rossa."""
    a = _archivio(tmp_path)
    ident = a.log_turn(species="chat", provider="subscription", model="m",
                       channel="ponte", duration_ms=10, iterations=1,
                       tools=[], outcome="riuscito", now=1000.0,
                       output_tokens=623)
    a.log_payload(ident, iteration=1, tools_chars=100, guide_chars=10,
                  core_chars=5, history_chars=7, results_chars=0, now=1000.0,
                  input_tokens=18, output_tokens=None,
                  cache_read_tokens=46812, cache_write_tokens=30878,
                  cache_ttl="1h", cost_usd=None)

    giro = a.payloads(ident)[0]
    assert giro["input_tokens"] == 18
    assert giro["cache_read_tokens"] == 46812
    assert giro["cache_write_tokens"] == 30878
    assert giro["cache_ttl"] == "1h"
    assert giro["output_tokens"] is None
    assert a.turns()[0]["output_tokens"] == 623


def test_il_costo_a_listino_del_ponte_sta_in_una_colonna_SUA(tmp_path):
    """«Quanto sarebbe costato a consumo» non e' «quanto ho pagato»: due
    cose, due colonne. Il ponte non paga per turno.

    Mutazione ESEGUITA: scrivere il valore in `cost_usd` dei giri -- rossa."""
    a = _archivio(tmp_path)
    ident = a.log_turn(species="analista", provider="subscription", model="m",
                       channel="ponte", duration_ms=1, iterations=1, tools=[],
                       outcome="riuscito", now=1000.0, list_cost_usd=0.0695702)
    assert a.turns()[0]["list_cost_usd"] == 0.0695702
    a.log_payload(ident, iteration=1, tools_chars=0, guide_chars=1,
                  core_chars=1, history_chars=1, results_chars=0, now=1000.0)
    assert a.payloads(ident)[0]["cost_usd"] is None


def test_cio_che_non_si_passa_resta_NULL_e_non_zero(tmp_path):
    """Mutazione ESEGUITA: default `0` invece di `None` per `input_tokens` -- rossa."""
    a = _archivio(tmp_path)
    ident = a.log_turn(species="chat", provider="p", model="m", channel="catena",
                       duration_ms=1, iterations=1, tools=[], outcome="riuscito",
                       now=1000.0)
    a.log_payload(ident, iteration=1, tools_chars=1, guide_chars=1,
                  core_chars=1, history_chars=1, results_chars=0, now=1000.0)

    giro = a.payloads(ident)[0]
    assert all(giro[c] is None for c in TOKEN_COLUMNS)
    assert a.turns()[0]["output_tokens"] is None
    assert a.turns()[0]["list_cost_usd"] is None


def test_l_archivio_VERO_alla_versione_1_si_migra_senza_toccare_le_righe(tmp_path):
    """La casa vera ha `consumi.db` alla versione 1 con 96 giri del 24/09.

    Mutazione ESEGUITA: togliere `2: _migration_2` dal dizionario -- rossa
    (init_schema solleva «manca la migrazione»).
    Mutazione ESEGUITA: aggiungere le colonne solo a `payload` -- rossa."""
    percorso = str(tmp_path / "consumi.db")
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE turn (id TEXT PRIMARY KEY, ts REAL NOT NULL,
            species TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
            channel TEXT NOT NULL, subject_json TEXT,
            duration_ms INTEGER NOT NULL, iterations INTEGER NOT NULL,
            tools TEXT NOT NULL, outcome TEXT NOT NULL);
        CREATE TABLE payload (turn_id TEXT NOT NULL, iteration INTEGER NOT NULL,
            ts REAL NOT NULL, tools_chars INTEGER NOT NULL,
            tools_sent INTEGER NOT NULL DEFAULT 0, guide_chars INTEGER NOT NULL,
            core_chars INTEGER NOT NULL, history_chars INTEGER NOT NULL,
            results_chars INTEGER NOT NULL, prefix_hash TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (turn_id, iteration));
        INSERT INTO turn VALUES ('vecchio', 9e9, 'chat', 'p', 'm', 'catena',
            NULL, 1, 1, '[]', 'riuscito');
        INSERT INTO payload VALUES ('vecchio', 1, 9e9, 45388, 16, 6915, 7655,
            18090, 0, 'abc');
        PRAGMA user_version = 1;
    """)
    conn.commit()
    conn.close()

    a = UsageStore(percorso)

    giro = a.payloads("vecchio")[0]
    assert giro["tools_chars"] == 45388
    assert all(giro[c] is None for c in TOKEN_COLUMNS)
    assert a.turns()[0]["output_tokens"] is None
    assert a.turns()[0]["list_cost_usd"] is None
    # e la riga nuova si scrive coi token
    ident = a.log_turn(species="chat", provider="p", model="m", channel="ponte",
                       duration_ms=1, iterations=1, tools=[], outcome="riuscito",
                       now=9e9, output_tokens=5)
    assert {t["id"]: t for t in a.turns()}[ident]["output_tokens"] == 5
