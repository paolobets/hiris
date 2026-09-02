"""L'archivio dei consumi: un secchiello al giorno per modello."""
import pytest

from hiris.app.usage.store import UsageStore

ROMA = "Europe/Rome"
T1 = 1787324400.0   # 21/08/2026 17:00 a Roma
T2 = 1787326200.0   # 21/08/2026 17:30 a Roma
T3 = 1787410800.0   # 22/08/2026 17:00 a Roma


@pytest.fixture
def archivio(tmp_path):
    a = UsageStore(str(tmp_path / "consumi.db"), read_timezone=lambda: ROMA)
    yield a
    a.close()


def _righe(a):
    return [dict(r) for r in a._conn.execute(
        "SELECT * FROM consumo_giorno ORDER BY giorno, provider, modello")]


def test_due_chiamate_nello_stesso_giorno_sono_una_riga_sola(archivio):
    for now in (T1, T2):
        archivio.log("claude", "claude-sonnet-4-6", token_in=100,
                          token_out=10, cost_usd=0.5, cost_state="misurato",
                          now=now)
    righe = _righe(archivio)
    assert len(righe) == 1
    assert righe[0]["richieste"] == 2
    assert righe[0]["token_in"] == 200
    assert righe[0]["costo_usd"] == 1.0
    assert righe[0]["primo_ts"] == T1 and righe[0]["ultimo_ts"] == T2


def test_giorni_diversi_sono_secchielli_diversi(archivio):
    archivio.log("claude", "m", cost_state="misurato", cost_usd=1.0, now=T1)
    archivio.log("claude", "m", cost_state="misurato", cost_usd=1.0, now=T3)
    assert [r["giorno"] for r in _righe(archivio)] == ["2026-08-21", "2026-08-22"]


def test_lo_stato_degrada_e_non_si_rafforza(archivio):
    """OpenRouter che una volta porta `usage.cost` e una volta no."""
    archivio.log("openrouter", "m", cost_usd=0.5, cost_state="reale", now=T1)
    archivio.log("openrouter", "m", cost_usd=None, cost_state="non_noto", now=T2)
    riga = _righe(archivio)[0]
    assert riga["costo_stato"] == "non_noto"
    assert riga["costo_usd"] == 0.5, (
        "il costo gia' accumulato non si butta: la riga diventa un pavimento, "
        "non un vuoto -- «questo l'ho pagato di sicuro, piu' qualcosa che non so»")

    archivio.log("openrouter", "m", cost_usd=0.5, cost_state="reale", now=T2)
    assert _righe(archivio)[0]["costo_stato"] == "non_noto", (
        "una riga degradata non torna a dire «reale»")


def test_openai_e_openrouter_non_finiscono_sulla_stessa_riga(archivio):
    """`OpenRouterRunner` e' una sottoclasse di `OpenAICompatRunner`: senza un
    nome esplicito il consumo dell'uno finirebbe scritto sull'altro."""
    archivio.log("openai", "gpt-4o", cost_state="misurato", now=T1)
    archivio.log("openrouter", "gpt-4o", cost_state="reale", now=T1)
    assert {r["provider"] for r in _righe(archivio)} == {"openai", "openrouter"}


def test_un_archivio_appena_nato_e_vuoto_e_lo_dice(archivio):
    assert archivio.empty() is True
    archivio.log("claude", "m", cost_state="misurato", now=T1)
    assert archivio.empty() is False


def test_i_rifiuti_429_si_contano_sulla_riga_del_modello_che_li_ha_presi(archivio):
    """Oggi sono un numero solo per tutto il prodotto, e non dicono CHI sta
    rifiutando."""
    archivio.log("claude", "m", richieste=0, errori_rate_limit=1,
                      cost_state="non_noto", now=T1)
    riga = _righe(archivio)[0]
    assert riga["errori_rate_limit"] == 1
    assert riga["richieste"] == 0, "un rifiuto non e' una richiesta servita"


def test_senza_fuso_il_giorno_e_in_UTC_e_non_esplode(tmp_path):
    a = UsageStore(str(tmp_path / "c.db"), read_timezone=lambda: "")
    try:
        a.log("claude", "m", cost_state="misurato", now=1787351400.0)
        assert _righe(a)[0]["giorno"] == "2026-08-21"
    finally:
        a.close()


def test_un_fuso_che_solleva_non_ferma_la_scrittura(tmp_path):
    """L'anagrafe puo' non essere ancora stata letta: un consumo non si perde
    perche' non sappiamo in che giorno metterlo."""
    def _rotto():
        raise RuntimeError("archivio non pronto")

    a = UsageStore(str(tmp_path / "c.db"), read_timezone=_rotto)
    try:
        a.log("claude", "m", cost_state="misurato", now=T1)
        assert len(_righe(a)) == 1
    finally:
        a.close()
