"""I token dell'abbonamento smettono di finire solo nel log.

Il ponte li LEGGE gia' da ogni turno (`_logga_uso`) e li scriveva in una riga
di log che nessuna porta del prodotto puo' interrogare: la fondamenta n.4 alla
lettera -- se un dato c'e' e nessuno puo' chiederlo, non esiste.
"""
from __future__ import annotations

import pytest

from hiris.app.agent import runner as ponte


@pytest.fixture
def registro():
    scritte: list[tuple] = []
    ponte.imposta_registro_consumi(
        lambda provider, model, **kw: scritte.append((provider, model, kw)))
    try:
        yield scritte
    finally:
        ponte.imposta_registro_consumi(None)


def _esito(usage=None, risultato=None):
    e = ponte.EsitoFlusso()
    e.usage = usage if usage is not None else {}
    e.risultato = risultato
    e.num_turni = 1
    return e


def test_il_ponte_registra_i_token_col_costo_COMPRESO(registro):
    ponte._logga_uso(_esito({
        "input_tokens": 2100, "output_tokens": 94,
        "cache_read_input_tokens": 1400, "cache_creation_input_tokens": 210,
    }), "job-1")

    provider, _modello, kw = registro[0]
    assert provider == "ponte"
    assert kw["token_in"] == 2100 and kw["token_out"] == 94
    assert kw["cache_read"] == 1400 and kw["cache_write"] == 210
    assert kw["cost_state"] == "compreso"
    assert kw["cost_usd"] is None, (
        "l'abbonamento non espone il prezzo del turno: 0,00 direbbe «gratis»")


def test_il_modello_VERO_dell_evento_result_vince_sull_alias(registro):
    """Cio' che e' successo batte cio' che abbiamo chiesto."""
    ponte._logga_uso(
        _esito({"input_tokens": 1, "model": "sonnet"},
               risultato={"model": "claude-sonnet-4-6"}), "job-2")

    assert registro[0][1] == "claude-sonnet-4-6"


def test_una_ripartizione_per_modello_da_il_nome_dalla_sua_chiave(registro):
    ponte._logga_uso(
        _esito({"input_tokens": 1},
               risultato={"modelUsage": {"claude-opus-4-8": {"inputTokens": 1}}}),
        "job-3")

    assert registro[0][1] == "claude-opus-4-8"


def test_senza_il_modello_vero_l_alias_si_dichiara_come_alias(registro):
    """Ripiego DICHIARATO: la pagina deve poter dire a chi legge che quel
    nome e' cio' che abbiamo chiesto, non cio' che abbiamo misurato."""
    ponte._logga_uso(_esito({"input_tokens": 1, "model": "opus"}), "job-4")

    assert registro[0][1] == "opus (alias)"


def test_senza_registro_il_ponte_logga_e_basta_come_prima():
    """Il percorso a processo separato (`main()`, il gateway esterno) non ha
    `/data`: li' il registro resta `None` e il turno non deve rompersi."""
    ponte.imposta_registro_consumi(None)
    ponte._logga_uso(_esito({"input_tokens": 1}), "job-5")


def test_un_turno_senza_usage_non_scrive_niente(registro):
    ponte._logga_uso(_esito({}), "job-6")
    assert registro == []
