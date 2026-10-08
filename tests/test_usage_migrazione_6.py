"""La versione 6 dei consumi (Tappa 8, Task 5): le colonne che nessuno
leggeva escono, il soggetto di un turno diventa la sua chiave (A-17), e i
ripieghi si fotografano all'ancora come i consumi (G-22).

Le migrazioni si provano su un archivio alla versione 5 con le righe
com'erano, due volte: la prima apertura migra, la seconda non cambia niente."""
import json
import sqlite3

from hiris.app.chat_thread import new_subject
from hiris.app.usage import store as store_module
from hiris.app.usage.store import SCHEMA_VERSION, UsageStore

ROMA = "Europe/Rome"
# Istanti scelti a mano, lontani dal 1970: non sono misure.
STAMATTINA = 1_790_060_400.0   # 22/09/2026 09:00 a Roma
AZZERAMENTO = 1_790_067_600.0  # 22/09/2026 11:00 a Roma
STASERA = 1_790_089_200.0      # 22/09/2026 17:00 a Roma

_V5 = """
CREATE TABLE consumo_giorno (
    giorno TEXT NOT NULL, provider TEXT NOT NULL, modello TEXT NOT NULL,
    richieste INTEGER NOT NULL DEFAULT 0, token_in INTEGER NOT NULL DEFAULT 0,
    token_out INTEGER NOT NULL DEFAULT 0, cache_lettura INTEGER NOT NULL DEFAULT 0,
    cache_scrittura INTEGER NOT NULL DEFAULT 0, costo_usd REAL,
    costo_stato TEXT NOT NULL, errori_rate_limit INTEGER NOT NULL DEFAULT 0,
    primo_ts REAL NOT NULL, ultimo_ts REAL NOT NULL,
    PRIMARY KEY (giorno, provider, modello));
CREATE INDEX idx_consumo_giorno ON consumo_giorno(giorno);
CREATE TABLE turn (
    id TEXT PRIMARY KEY, ts REAL NOT NULL, species TEXT NOT NULL,
    provider TEXT NOT NULL, model TEXT NOT NULL, channel TEXT NOT NULL,
    subject_json TEXT, duration_ms INTEGER NOT NULL, iterations INTEGER NOT NULL,
    tools TEXT NOT NULL, outcome TEXT NOT NULL, output_tokens INTEGER,
    list_cost_usd REAL, tool_args TEXT, problems TEXT);
CREATE INDEX idx_turn_ts ON turn(ts DESC);
"""

_PAOLO = {"specie": "persona", "id": "u-42", "nome": "Paolo", "utente": "paolo",
          "ruolo": None}


def _archivio_v5(path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_V5)
    conn.executescript(store_module._SCHEMA)
    conn.execute(
        "INSERT INTO consumo_giorno VALUES ('2026-09-22','claude','opus',3,30,3,0,0,"
        "0.5,'misurato',0,?,?)", (STAMATTINA, STASERA))
    for ident, soggetto in (("chat", json.dumps(_PAOLO)), ("notte", None),
                            ("storto", "{non json")):
        conn.execute(
            "INSERT INTO turn(id,ts,species,provider,model,channel,subject_json,"
            "duration_ms,iterations,tools,outcome) "
            "VALUES(?,?,'chat','claude','opus','catena',?,1,1,'[]','riuscito')",
            (ident, STAMATTINA, soggetto))
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()


def test_la_versione_6_toglie_gli_istanti_e_fa_chiave_il_soggetto(tmp_path):
    """Mutazione ESEGUITA (08/10/2026): il soggetto non travasato nella
    chiave -- rossa, il turno di Paolo resta senza CHI."""
    path = str(tmp_path / "consumi.db")
    _archivio_v5(path)
    for _apertura in range(2):
        consumi = UsageStore(path, read_timezone=lambda: ROMA)
        try:
            giorni = {r[1] for r in consumi._conn.execute(
                "PRAGMA table_info(consumo_giorno)")}
            assert not giorni & {"primo_ts", "ultimo_ts"}
            [sezione] = consumi.sezioni()
            assert (sezione["richieste"], sezione["costo_usd"]) == (3, 0.5)
            turni = {t["id"]: t for t in consumi.turns()}
            assert turni["chat"]["subject"] == new_subject("persona", ident="u-42")
            assert turni["notte"]["subject"] is None
            assert turni["storto"]["subject"] is None
            colonne = {r[1] for r in consumi._conn.execute("PRAGMA table_info(turn)")}
            assert "subject_json" not in colonne and "subject_key" in colonne
            assert consumi._conn.execute(
                "PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        finally:
            consumi.close()


def test_riparti_da_adesso_toglie_anche_i_ripieghi_di_stamattina(tmp_path):
    """G-22: i consumi partono dall'ISTANTE dell'ancora, e i ripieghi pure.
    Fino all'08/10/2026 si filtravano per GIORNO, e i due di stamattina,
    prima dell'azzeramento, restavano contati.

    Mutazione ESEGUITA (08/10/2026): `sposta_anchor` senza la fotografia dei
    ripieghi -- rossa, `('analista', 3) != ('analista', 1)`."""
    consumi = UsageStore(str(tmp_path / "consumi.db"), read_timezone=lambda: ROMA)
    try:
        consumi.log_fallback("analista", "tetto giornaliero", now=STAMATTINA)
        consumi.log_fallback("analista", "tetto giornaliero", now=STAMATTINA + 60)
        consumi.log_fallback("ricette", "manca il token", now=STAMATTINA)
        consumi.sposta_anchor(AZZERAMENTO)
        consumi.log_fallback("analista", "tetto giornaliero", now=STASERA)

        dopo = consumi.fallbacks(from_anchor=True)
        assert [(r["agent"], r["count"]) for r in dopo] == [("analista", 1)]
        # «Da sempre» li conta tutti: la fotografia non cancella niente.
        sempre = {(r["agent"], r["count"]) for r in consumi.fallbacks()}
        assert sempre == {("analista", 3), ("ricette", 1)}
    finally:
        consumi.close()
