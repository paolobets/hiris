"""L'esito «scartato» nel registro dei turni, e il freno che lo conta (D10
del piano degli attori, Task 3.6 Passo 3, approvata il 06/10/2026). Fino
all'08/10/2026 la parola era «rifiutata», e il file si chiamava
`test_esito_rifiutata.py`: la Tappa 8 (D4, `usage` alla 6) le ha dato la
parola che non dice anche il «no» dell'utente (rilievo N100-1).

Fino a qui una risposta che il mestiere rifiutava -- un JSON leggibile con
dentro un id che non c'e' -- restava «riuscito» nel registro: il freno della
Tappa 6 contava i soli troncati, e un analista che sbaglia ogni giro non lo
fermava nessuno. A differenza del troncato, il rifiuto non lo sa il runner:
lo sa il mestiere DOPO il turno, e lo scrive sulla riga gia' registrata --
sulla catena con l'id del `TurnOutcome`, sul ponte con quello che il runner
mette nella decisione del job.

I problemi del rifiuto stanno sulla stessa riga, nella colonna `problems`
(scelta del proprietario del 06/10/2026, «Si', con la colonna»), e il giro
che riprova li rilegge con `steering.refused_problems`.

Qui le parti comuni; il collegamento dei giri dell'analista sta in
`tests/test_analista_rifiutato.py`.
"""
from __future__ import annotations

import pytest

from conftest import SCADENZA_LONTANA
from hiris.app import steering
from hiris.app.agent import runner as ponte
from hiris.app.usage.store import UsageStore


@pytest.fixture()
def consumi(tmp_path):
    archivio = UsageStore(str(tmp_path / "consumi.db"))
    yield archivio
    archivio.close()


def _turno(archivio, specie, esito, now):
    return archivio.log_turn(species=specie, provider="claude", model="m",
                             channel="catena", duration_ms=1, iterations=1,
                             tools=[], outcome=esito, now=now)


def test_il_rifiuto_si_scrive_sulla_riga_del_turno(consumi):
    """Una riga per turno: l'esito si corregge dove vive."""
    ident = _turno(consumi, "analista", "riuscito", 1_758_000_000.0)
    steering.declare_refused(consumi, ident)
    righe = consumi.turns()
    assert [r["outcome"] for r in righe] == [steering.REFUSED]


def test_i_PROBLEMI_del_rifiuto_stanno_sulla_riga(consumi):
    """La colonna e' la scelta del proprietario del 06/10/2026 («Si', con la
    colonna»): il giro dopo, sulla catena come sul ponte, li rilegge da qui.

    Mutazione ESEGUITA (06/10/2026): `declare_refused` che non passa i
    problemi -- rossa (la colonna resta vuota)."""
    ident = _turno(consumi, "analista", "riuscito", 1_758_000_000.0)
    steering.declare_refused(consumi, ident, ["il rimetti 1 vuole `id`"])
    riga = consumi.turns()[0]
    assert riga["problems"] == ["il rimetti 1 vuole `id`"]
    assert steering.refused_problems(consumi, "analista") == [
        "il rimetti 1 vuole `id`"]


def test_un_turno_RIUSCITO_dopo_supera_i_problemi_di_prima(consumi):
    """Solo l'ultimo turno conta: dopo una risposta buona, i problemi di
    quella rifiutata non tornano nella domanda.

    Mutazione ESEGUITA (06/10/2026): `refused_problems` che cerca l'ultimo
    rifiutato invece dell'ultimo turno -- rossa."""
    ident = _turno(consumi, "analista", "riuscito", 1_758_000_000.0)
    steering.declare_refused(consumi, ident, ["vecchio"])
    _turno(consumi, "analista", "riuscito", 1_758_000_100.0)
    assert steering.refused_problems(consumi, "analista") == []


def test_i_problemi_sono_di_UN_mestiere(consumi):
    ident = _turno(consumi, "analista", "riuscito", 1_758_000_000.0)
    steering.declare_refused(consumi, ident, ["x"])
    _turno(consumi, "osservatore", "riuscito", 1_758_000_100.0)
    assert steering.refused_problems(consumi, "analista") == ["x"]
    assert steering.refused_problems(consumi, "osservatore") == []
    assert steering.refused_problems(None, "analista") == []


def test_un_turno_mai_rifiutato_ha_la_colonna_VUOTA(consumi):
    _turno(consumi, "analista", "riuscito", 1_758_000_000.0)
    assert consumi.turns()[0]["problems"] is None


def test_un_archivio_alla_versione_3_si_migra(tmp_path):
    """Mutazione ESEGUITA (06/10/2026): togliere `4: _migration_4` dal
    dizionario -- rossa (init_schema solleva)."""
    import sqlite3
    percorso = str(tmp_path / "consumi.db")
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE turn (id TEXT PRIMARY KEY, ts REAL NOT NULL,
            species TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
            channel TEXT NOT NULL, subject_json TEXT,
            duration_ms INTEGER NOT NULL, iterations INTEGER NOT NULL,
            tools TEXT NOT NULL, outcome TEXT NOT NULL,
            output_tokens INTEGER, list_cost_usd REAL, tool_args TEXT);
        INSERT INTO turn VALUES ('vecchio', 9e9, 'analista', 'p', 'm', 'catena',
            NULL, 1, 1, '[]', 'riuscito', NULL, NULL, NULL);
        PRAGMA user_version = 3;
    """)
    conn.commit()
    conn.close()
    archivio = UsageStore(percorso)
    try:
        assert archivio.turns()[0]["problems"] is None
        steering.declare_refused(archivio, "vecchio", ["p"])
        assert archivio.turns()[0]["problems"] == ["p"]
    finally:
        archivio.close()


@pytest.mark.parametrize("esito", ["fallito", steering.TRUNCATED])
def test_un_turno_che_NON_e_riuscito_non_diventa_rifiutato(consumi, esito):
    """G31-1 (giro 31 della revisione, 06/10/2026): sulla catena la frase del
    router arriva al mestiere come risposta, il mestiere la rifiuta, e il
    giro dopo direbbe al modello che la sua risposta non era accettata
    quando nessuno aveva risposto. Si corregge solo un turno riuscito.

    Mutazione ESEGUITA (06/10/2026): `declare_refused` senza `only_from` --
    rossa («fallito» diventa «rifiutata»)."""
    ident = _turno(consumi, "analista", esito, 1_758_000_000.0)
    steering.declare_refused(consumi, ident, ["non e' un JSON"])
    riga = consumi.turns()[0]
    assert riga["outcome"] == esito
    assert riga["problems"] is None
    assert steering.refused_problems(consumi, "analista") == []


def test_senza_archivio_o_senza_id_non_succede_niente(consumi):
    _turno(consumi, "analista", "riuscito", 1_758_000_000.0)
    steering.declare_refused(None, "x")
    steering.declare_refused(consumi, None)
    steering.declare_refused(consumi, "")
    assert consumi.turns()[0]["outcome"] == "riuscito"


def test_un_id_che_non_c_e_non_tocca_le_altre_righe(consumi):
    _turno(consumi, "analista", "riuscito", 1_758_000_000.0)
    assert consumi.set_outcome("mai-esistito", steering.REFUSED) is False
    assert consumi.turns()[0]["outcome"] == "riuscito"


def test_un_archivio_rotto_non_fa_cadere_il_giro():
    class _Rotto:
        def set_outcome(self, *a, **k):
            raise OSError("disco pieno")

    steering.declare_refused(_Rotto(), "x")


def test_il_freno_conta_anche_i_RIFIUTATI(consumi, monkeypatch):
    """Mutazione ESEGUITA (06/10/2026): `brake_engaged` che conta i soli
    troncati -- rossa (due rifiutati non frenano)."""
    monkeypatch.setattr(steering, "TRUNCATION_BRAKE", 2)
    _turno(consumi, "analista", steering.TRUNCATED, 1_758_000_000.0)
    _turno(consumi, "analista", steering.REFUSED, 1_758_000_100.0)
    assert steering.brake_engaged(consumi, "analista") is True

    _turno(consumi, "analista", "riuscito", 1_758_000_200.0)
    assert steering.brake_engaged(consumi, "analista") is False


def test_il_freno_e_ancora_SPENTO(consumi):
    """N lo misura T9: nessun numero nuovo per i rifiutati."""
    assert steering.TRUNCATION_BRAKE is None
    for i in range(10):
        _turno(consumi, "analista", steering.REFUSED, 1_758_000_000.0 + i)
    assert steering.brake_engaged(consumi, "analista") is False


class _ProcessoFinto:
    returncode = 1
    stdout = ""
    stderr = "la CLI non e' stata lanciata: e' una prova"


def test_sul_ponte_la_decisione_porta_la_riga_del_suo_turno(monkeypatch):
    """Chi raccoglie la risposta del ponte, minuti dopo, deve poter scrivere
    «scartato» sulla riga giusta: il runner gliela consegna nella decisione.

    Mutazione ESEGUITA (06/10/2026): `_measure_turn` che non torna l'id --
    rossa (`turn_id` assente)."""
    monkeypatch.setattr(ponte.subprocess, "run",
                        lambda argv, *a, **kw: _ProcessoFinto())
    ponte.set_turn_logger(lambda riga: "riga-7")
    try:
        decisione = ponte.reason(
            {"kind": "proposta", "deadline_ts": SCADENZA_LONTANA, "job_id": "ja",
             "context": {"model": "sonnet", "system_prompt": "sei l'attuatore",
                         "history": [{"role": "user", "content": "x"}],
                         "istruzione": "Rispondi SOLO con un oggetto JSON."}},
            "live", client=object(), base_url="http://127.0.0.1:8099")
    finally:
        ponte.set_turn_logger(None)
    assert decisione["turn_id"] == "riga-7"


def test_il_gancio_del_server_torna_l_id_della_riga(consumi):
    """`server._registra_turno_ponte`: l'id che il runner consegna e' quello
    della riga scritta, non un nome nuovo."""
    from hiris.app import server

    registra = server._registra_turno_ponte(consumi)
    ident = registra({"species": "analista", "channel": "ponte",
                      "provider": "subscription", "model": "m",
                      "duration_ms": 1, "iterations": 1, "tools": [],
                      "outcome": "riuscito"})
    assert consumi.turns()[0]["id"] == ident
