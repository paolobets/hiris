"""I consumi del piano passano da `ponte` a `subscription` (Tappa 7, T9, D9a).

`subscription` e' il provider -- catena, archivio dei modelli, registro degli
esiti -- e fino al Task 9 i consumi lo chiamavano `ponte`, il nome della
strada. Due nomi per una cosa: la pagina Consumi e la pagina Modelli non si
potevano incrociare senza una tabella di traduzione in piu'.

La migrazione si prova su un archivio di prova alla versione 4, scritto come
lo scriveva la versione di prima: righe `ponte` nei secchielli e nel saldo
dell'ancora, e -- il caso che obbliga a fondere invece di rinominare -- una
riga gia' sotto `subscription` per lo stesso giorno e modello, che e' cio' che
trova un archivio tornato indietro di una versione e poi riaggiornato.
"""
import logging
import sqlite3

from hiris.app.usage import store as store_module
from hiris.app.usage.store import UsageStore

# Istanti fissi e lontani dal 1970, scelti a mano: non sono misure.
T1 = 1_790_000_000.0
T2 = 1_790_000_600.0
T3 = 1_790_001_200.0


def _archivio_v4(path, righe, saldi=()):
    """Un archivio alla versione 4: lo schema di oggi (la 5 non cambia
    tabelle) e `user_version = 4`."""
    conn = sqlite3.connect(path)
    conn.executescript(store_module._SCHEMA)
    for r in righe:
        conn.execute(
            "INSERT INTO consumo_giorno (giorno, provider, modello, richieste, "
            "token_in, token_out, cache_lettura, cache_scrittura, costo_usd, "
            "costo_stato, errori_rate_limit, primo_ts, ultimo_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", r)
    for s in saldi:
        conn.execute(
            "INSERT INTO ancora_saldo (provider, modello, richieste, token_in, "
            "token_out, cache_lettura, cache_scrittura, costo_usd, "
            "errori_rate_limit) VALUES (?,?,?,?,?,?,?,?,?)", s)
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    conn.close()


def _righe(path, tabella):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    out = [dict(r) for r in conn.execute(f"SELECT * FROM {tabella} ORDER BY 1, 2")]
    conn.close()
    return out


def _apri(path):
    UsageStore(str(path)).close()


def test_le_righe_del_piano_passano_a_subscription_e_si_fondono_con_la_gemella(
        tmp_path, caplog):
    """Mutazioni eseguite (07/10/2026), ognuna rossa per la ragione giusta e
    ripristinata (`git diff hiris/app/usage/store.py` senza la mutazione):
    - il ramo della gemella tolto da `_migration_5` (sempre `UPDATE ... SET
      provider`) -> rosso, `sqlite3.IntegrityError: UNIQUE constraint failed`;
    - lo stato della riga fusa preso dalla riga `ponte` invece del piu' debole
      dei due -> rosso, `'compreso' == 'non_noto'`;
    - tolto il `logger.info` -> rosso, la riga del registro non c'e'."""
    db = tmp_path / "consumi.db"
    _archivio_v4(db, [
        # (giorno, provider, modello, richieste, in, out, cache_l, cache_s,
        #  costo, stato, errori, primo, ultimo)
        ("2026-09-20", "ponte", "claude-opus-4-7", 3, 100, 10, 5, 1, None,
         "compreso", 0, T1, T2),
        ("2026-09-21", "ponte", "claude-opus-4-7", 2, 50, 5, 0, 0, None,
         "compreso", 1, T2, T3),
        # La gemella: lo stesso giorno e modello, gia' sotto `subscription`.
        ("2026-09-21", "subscription", "claude-opus-4-7", 1, 7, 3, 0, 0, None,
         "non_noto", 0, T1, T2),
        # Un altro provider non si tocca.
        ("2026-09-21", "claude", "claude-opus-4-7", 4, 40, 4, 0, 0, 0.5,
         "misurato", 0, T1, T3),
    ], saldi=[
        ("ponte", "claude-opus-4-7", 1, 10, 1, 0, 0, None, 0),
    ])

    with caplog.at_level(logging.INFO, logger=store_module.logger.name):
        _apri(db)

    righe = {(r["giorno"], r["provider"]): r for r in _righe(db, "consumo_giorno")}
    assert not [k for k in righe if k[1] == "ponte"]
    solo = righe[("2026-09-20", "subscription")]
    assert (solo["richieste"], solo["token_in"], solo["costo_stato"]) == (3, 100, "compreso")
    fusa = righe[("2026-09-21", "subscription")]
    assert (fusa["richieste"], fusa["token_in"], fusa["token_out"],
            fusa["errori_rate_limit"]) == (3, 57, 8, 1)
    assert fusa["costo_usd"] is None
    assert fusa["costo_stato"] == "non_noto", "si fonde verso il piu' debole"
    assert (fusa["primo_ts"], fusa["ultimo_ts"]) == (T1, T3)
    assert righe[("2026-09-21", "claude")]["richieste"] == 4

    saldi = _righe(db, "ancora_saldo")
    assert [(s["provider"], s["richieste"]) for s in saldi] == [("subscription", 1)]

    riga = [r.getMessage() for r in caplog.records if "consumi: il piano passa" in r.getMessage()]
    assert riga == [("consumi: il piano passa da «ponte» a «subscription» -- "
                     "2 righe di consumo_giorno e 1 di ancora_saldo spostate")]


def test_la_migrazione_e_idempotente_e_rigira_dopo_un_ritorno_indietro(tmp_path, caplog):
    """Una seconda apertura non fa niente e non dice niente. Un archivio che
    torna alla versione 4 -- la versione vecchia lo ritimbra e riscrive
    `ponte` -- rigira la migrazione al ritorno, e la riga nuova si fonde con
    quella gia' migrata."""
    db = tmp_path / "consumi.db"
    _archivio_v4(db, [("2026-09-20", "ponte", "opus", 2, 10, 1, 0, 0, None,
                       "compreso", 0, T1, T2)])
    _apri(db)
    prima = _righe(db, "consumo_giorno")

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=store_module.logger.name):
        _apri(db)
    assert _righe(db, "consumo_giorno") == prima
    assert "il piano passa" not in caplog.text

    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO consumo_giorno (giorno, provider, modello, richieste, "
        "token_in, token_out, cache_lettura, cache_scrittura, costo_usd, "
        "costo_stato, errori_rate_limit, primo_ts, ultimo_ts) "
        "VALUES ('2026-09-20', 'ponte', 'opus', 1, 5, 1, 0, 0, NULL, 'compreso', 0, ?, ?)",
        (T2, T3))
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    conn.close()
    _apri(db)
    [riga] = _righe(db, "consumo_giorno")
    assert (riga["provider"], riga["richieste"], riga["token_in"]) == ("subscription", 3, 15)
    assert (riga["primo_ts"], riga["ultimo_ts"]) == (T1, T3)


def test_la_pagina_consumi_chiama_il_piano_come_la_pagina_modelli(tmp_path):
    """D10a: i Consumi si allineano ai nomi della pagina Modelli, e la sezione
    del piano dice da se' che conta turni e che il costo e' compreso."""
    from hiris.app.providers import SUBSCRIPTION

    s = UsageStore(str(tmp_path / "consumi.db"))
    s.log(SUBSCRIPTION.id, "opus", token_in=10, cost_state="compreso", now=T1)
    [sezione] = s.sezioni()
    s.close()
    assert sezione["etichetta"] == SUBSCRIPTION.name
    assert sezione["unita"] == "turni"
    assert sezione["compreso"] is True
