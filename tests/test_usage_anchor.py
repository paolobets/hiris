"""«Riparti da adesso» sposta un'ancora, e non cancella niente.

Con secchielli giornalieri un'ancora che fosse soltanto una DATA lascerebbe in
pagina, subito dopo l'azzeramento, il consumo gia' fatto stamattina -- e il
pulsante sembrerebbe rotto. Il saldo e' la POSIZIONE dell'ancora, espressa
nelle uniche coordinate che l'archivio possiede.
"""
import json

import pytest

from hiris.app.usage.store import UsageStore

ROMA = "Europe/Rome"
MATTINA = 1787292000.0     # 21/08/2026 08:00
POMERIGGIO = 1787324400.0  # 21/08/2026 17:00
DOMANI = 1787410800.0      # 22/08/2026 17:00


@pytest.fixture
def archivio(tmp_path):
    a = UsageStore(str(tmp_path / "consumi.db"), read_timezone=lambda: ROMA)
    yield a
    a.close()


def test_azzerare_porta_i_totali_a_zero_senza_cancellare_niente(archivio):
    archivio.log("claude", "m", richieste=5, token_in=500, cost_usd=2.0,
                      cost_state="misurato", now=MATTINA)

    archivio.sposta_anchor(POMERIGGIO)

    assert archivio.totali(from_anchor=True)["richieste"] == 0, (
        "il pulsante deve portare a zero: e' cio' che chi lo preme si aspetta")
    assert archivio.totali()["richieste"] == 5, "e la storia deve restare intera"


def test_dopo_l_ancora_il_consumo_nuovo_si_conta(archivio):
    archivio.log("claude", "m", richieste=5, cost_usd=2.0,
                      cost_state="misurato", now=MATTINA)
    archivio.sposta_anchor(POMERIGGIO)
    archivio.log("claude", "m", richieste=2, cost_usd=1.0,
                      cost_state="misurato", now=POMERIGGIO)

    assert archivio.totali(from_anchor=True)["richieste"] == 2
    assert archivio.totali(from_anchor=True)["costo_usd"] == 1.0
    assert archivio.totali()["richieste"] == 7


def test_l_ancora_vale_anche_sui_giorni_successivi(archivio):
    archivio.log("claude", "m", richieste=5, cost_state="misurato", now=MATTINA)
    archivio.sposta_anchor(POMERIGGIO)
    archivio.log("claude", "m", richieste=3, cost_state="misurato", now=DOMANI)
    assert archivio.totali(from_anchor=True)["richieste"] == 3


def test_dopo_l_ancora_l_abbonamento_non_afferma_ancora_zero(archivio):
    """La SECONDA strada per il totale di sezione (audit, rilievo 6).

    `_sottrai_saldo` ricalcola i totali di sezione dai modelli, e li
    ricalcolava con `sum(costo_usd or 0.0)`: dopo un azzeramento la sezione
    dell'abbonamento diceva `0.0` mentre senza ancora diceva `null` -- lo
    stesso fatto in due forme a seconda di un pulsante. Il commento accanto
    a quella somma dichiarava gia' il rischio («due strade per lo stesso
    numero divergono al primo caso limite») e la somma non lo rispettava."""
    archivio.log("ponte", "claude-haiku-4-5", token_in=80,
                      cost_usd=None, cost_state="compreso", now=MATTINA)
    archivio.sposta_anchor(POMERIGGIO)
    archivio.log("ponte", "claude-haiku-4-5", token_in=40,
                      cost_usd=None, cost_state="compreso", now=POMERIGGIO)

    sezione = archivio.sezioni(from_anchor=True)[0]
    assert sezione["token_in"] == 40, "l'ancora ha tolto il consumo di stamattina"
    assert sezione["costo_usd"] is None, (
        "l'abbonamento non ha un costo di turno: uno zero lo affermerebbe, "
        "e lo affermerebbe SOLO dopo un azzeramento")
    assert archivio.totali(from_anchor=True)["costo_parziale"] is True


def test_senza_ancora_da_ancora_e_da_sempre_coincidono(archivio):
    archivio.log("claude", "m", richieste=4, cost_state="misurato", now=MATTINA)
    assert archivio.totali(from_anchor=True) == archivio.totali()
    assert archivio.anchor() == 0.0


def test_l_ancora_si_ricorda_quando_e_stata_spostata(archivio):
    archivio.sposta_anchor(POMERIGGIO)
    assert archivio.anchor() == POMERIGGIO


def test_le_sezioni_da_ancora_non_mostrano_cio_che_e_prima(archivio):
    archivio.log("claude", "m", richieste=5, cost_state="misurato", now=MATTINA)
    archivio.sposta_anchor(POMERIGGIO)
    archivio.log("openrouter", "x", richieste=1, cost_usd=0.5,
                      cost_state="reale", now=POMERIGGIO)

    sezioni = archivio.sezioni(from_anchor=True)
    per_nome = {s["provider"]: s for s in sezioni}
    assert per_nome["openrouter"]["richieste"] == 1
    assert per_nome["claude"]["richieste"] == 0, (
        "il consumo di stamattina e' prima dell'ancora")


# --- i file vecchi entrano una volta sola ------------------------------------

def test_i_file_usage_di_prima_entrano_una_volta_sola(archivio, tmp_path):
    vecchio = tmp_path / "usage.json"
    vecchio.write_text(json.dumps({
        "total_input_tokens": 8300000, "total_output_tokens": 412000,
        "total_requests": 1204, "total_cost_usd": 26.28,
        "total_rate_limit_errors": 3, "last_reset": "2026-07-14T09:22:00+00:00",
    }), encoding="utf-8")

    quanti = archivio.importa_legacy([str(vecchio)], now=POMERIGGIO)
    assert quanti == 1
    assert archivio.importa_legacy([str(vecchio)], now=POMERIGGIO) == 0, (
        "importare due volte raddoppierebbe la spesa dell'utente")

    t = archivio.totali()
    assert t["richieste"] == 1204 and t["costo_usd"] == 26.28
    sezione = archivio.sezioni()[0]
    assert sezione["provider"] == "claude"
    assert sezione["modelli"][0]["modello"] == "(prima del dettaglio)", (
        "il totale ereditato non si puo' attribuire a un modello: dirlo e' "
        "meglio che spalmarlo su modelli che potrebbero non averlo speso")


def test_il_provider_si_deduce_dal_nome_del_file(archivio, tmp_path):
    for nome, atteso in (("usage_openai.json", "openai"),
                         ("usage_openrouter.json", "openrouter"),
                         ("usage_ollama.json", "ollama")):
        (tmp_path / nome).write_text(
            json.dumps({"total_requests": 1, "total_cost_usd": 0.0}), encoding="utf-8")
        archivio.importa_legacy([str(tmp_path / nome)], now=POMERIGGIO)

    assert {s["provider"] for s in archivio.sezioni()} == {
        "openai", "openrouter", "ollama"}


def test_un_file_che_non_esiste_non_e_un_guasto(archivio, tmp_path):
    assert archivio.importa_legacy([str(tmp_path / "mai-esistito.json")],
                                   now=POMERIGGIO) == 0


def test_un_file_illeggibile_si_dichiara_e_non_ferma_gli_altri(archivio, tmp_path):
    rotto = tmp_path / "usage.json"
    rotto.write_text("{non e' json", encoding="utf-8")
    buono = tmp_path / "usage_openai.json"
    buono.write_text(json.dumps({"total_requests": 7}), encoding="utf-8")

    assert archivio.importa_legacy([str(rotto), str(buono)], now=POMERIGGIO) == 1
    assert archivio.totali()["richieste"] == 7
