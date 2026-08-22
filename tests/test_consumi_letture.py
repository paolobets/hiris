"""Cosa l'archivio sa rispondere: i totali, le sezioni, la storia."""
import pytest

from hiris.app.consumi.archivio import ArchivioConsumi

ROMA = "Europe/Rome"
T21 = 1787324400.0   # 21/08/2026 17:00
T22 = 1787410800.0   # 22/08/2026 17:00


@pytest.fixture
def archivio(tmp_path):
    a = ArchivioConsumi(str(tmp_path / "consumi.db"), leggi_fuso=lambda: ROMA)
    a.registra("claude", "claude-sonnet-4-6", token_in=100, token_out=10,
               cache_lettura=40, costo_usd=1.0, costo_stato="misurato", adesso=T21)
    a.registra("claude", "claude-sonnet-4-6", token_in=100, token_out=10,
               costo_usd=1.0, costo_stato="misurato", adesso=T22)
    a.registra("openrouter", "un/modello", token_in=50, token_out=5,
               costo_usd=None, costo_stato="non_noto", adesso=T22)
    yield a
    a.close()


def test_i_totali_sommano_tutto_e_dichiarano_di_essere_un_pavimento(archivio):
    t = archivio.totali()
    assert t["richieste"] == 3
    assert t["token_in"] == 250
    assert t["costo_usd"] == 2.0
    assert t["costo_parziale"] is True, (
        "c'e' una riga senza prezzo: il totale non e' il costo, e' un minimo")


def test_senza_righe_non_note_il_totale_non_e_parziale(tmp_path):
    a = ArchivioConsumi(str(tmp_path / "c.db"), leggi_fuso=lambda: ROMA)
    try:
        a.registra("claude", "m", costo_usd=1.0, costo_stato="misurato", adesso=T21)
        assert a.totali()["costo_parziale"] is False
    finally:
        a.close()


def test_le_sezioni_esistono_solo_per_i_provider_usati(archivio):
    nomi = [s["provider"] for s in archivio.sezioni()]
    assert nomi == ["claude", "openrouter"], (
        "OpenAI non e' mai stato usato: e' un'ASSENZA, non uno zero")


def test_una_sezione_porta_i_suoi_modelli_col_primo_e_l_ultimo_uso(archivio):
    claude = archivio.sezioni()[0]
    assert claude["etichetta"] == "API Anthropic"
    assert claude["nota"].startswith("Costo calcolato")
    assert claude["costo_usd"] == 2.0
    assert claude["costo_parziale"] is False
    m = claude["modelli"][0]
    assert m["modello"] == "claude-sonnet-4-6"
    assert m["richieste"] == 2 and m["cache_lettura"] == 40
    assert m["costo_stato"] == "misurato"
    assert m["primo_uso"] == "2026-08-21" and m["ultimo_uso"] == "2026-08-22"


def test_una_sezione_con_una_riga_ignota_si_dichiara_parziale(archivio):
    openrouter = archivio.sezioni()[1]
    assert openrouter["costo_parziale"] is True
    assert openrouter["modelli"][0]["costo_stato"] == "non_noto"


def test_da_un_giorno_in_poi_si_conta_solo_da_li(archivio):
    assert archivio.totali(da="2026-08-22")["richieste"] == 2


def test_la_storia_da_un_secchiello_per_giorno_e_provider(archivio):
    giorni = archivio.storia(da="2026-08-21", a="2026-08-22")
    assert [g["giorno"] for g in giorni] == ["2026-08-21", "2026-08-22"]
    assert giorni[1]["per_provider"]["openrouter"]["richieste"] == 1
    assert giorni[0]["per_provider"]["claude"]["costo_usd"] == 1.0


def test_la_storia_fuori_intervallo_e_vuota_e_non_esplode(archivio):
    assert archivio.storia(da="2026-01-01", a="2026-01-31") == []
