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
    ponte.set_usage_logger(
        lambda provider, model, **kw: scritte.append((provider, model, kw)))
    try:
        yield scritte
    finally:
        ponte.set_usage_logger(None)


def _esito(usage=None, risultato=None):
    e = ponte.StreamOccurrence()
    e.usage = usage if usage is not None else {}
    e.result = risultato
    e.num_exchanges = 1
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


def test_due_modelli_nella_mappa_portano_OGNUNO_i_suoi_conteggi(registro):
    """Audit delle fondamenta, rilievo 2 -- il caso che nessuna prova vedeva.

    `modelUsage` e' «a map of model name to per-model token counts... useful
    when you run multiple models (for example, Haiku for subagents and Opus
    for the main agent)»: ogni modello porta i PROPRI numeri. Il ponte
    prendeva la prima chiave con `next(iter(...))` e le attaccava l'INTERO
    `usage` del turno -- un'attribuzione sbagliata e una somma sbagliata
    insieme. Misurato dal vivo l'08/09/2026: `/api/models/config` diceva «il
    prossimo messaggio va a Piano Claude Max, con sonnet» e
    `/api/usage/history` registrava 110 turni su 111 a `claude-haiku-4-5`.

    L'unica prova che c'era usava una mappa con UNA chiave sola, dove
    «prendi la prima» e «prendile tutte» danno lo stesso risultato: non
    poteva vedere niente.

    I nomi dei conteggi sono quelli veri della CLI, MISURATI il 09/09/2026 su
    un transcript di Claude Code (`~/.claude/projects/**/*.jsonl`, evento con
    `modelUsage`): `inputTokens`, `outputTokens`, `cacheReadInputTokens`,
    `cacheCreationInputTokens` -- camelCase, diversi da quelli del blocco
    `usage` di primo livello (`input_tokens`, snake_case).
    """
    ponte._logga_uso(
        _esito({"input_tokens": 999, "output_tokens": 999},
               risultato={"modelUsage": {
                   "claude-sonnet-4-6": {
                       "inputTokens": 100, "outputTokens": 20,
                       "cacheReadInputTokens": 5, "cacheCreationInputTokens": 3},
                   "claude-haiku-4-5": {
                       "inputTokens": 7, "outputTokens": 2,
                       "cacheReadInputTokens": 1, "cacheCreationInputTokens": 0},
               }}),
        "job-due-modelli")

    per_modello = {modello: kw for _p, modello, kw in registro}
    assert set(per_modello) == {"claude-sonnet-4-6", "claude-haiku-4-5"}, (
        "si registrano tutte le chiavi: non si sceglie un vincitore")
    assert per_modello["claude-sonnet-4-6"]["token_in"] == 100
    assert per_modello["claude-sonnet-4-6"]["token_out"] == 20
    assert per_modello["claude-sonnet-4-6"]["cache_read"] == 5
    assert per_modello["claude-sonnet-4-6"]["cache_write"] == 3
    assert per_modello["claude-haiku-4-5"]["token_in"] == 7
    assert per_modello["claude-haiku-4-5"]["token_out"] == 2
    assert 999 not in [kw["token_in"] for kw in per_modello.values()], (
        "l'`usage` del turno intero non appartiene a nessuno dei due modelli")


def test_una_mappa_a_una_chiave_sola_prende_i_conteggi_DELLA_CHIAVE(registro):
    """Il caso di ogni giorno, e il confine della cura: anche con un modello
    solo i numeri vengono dalla sua voce, non dal blocco `usage` del turno.

    Sono due letture diverse dello stesso turno -- la CLI puo' contare nel
    totale cio' che non attribuisce a nessun modello -- e finche' il codice
    prendeva il nome da una parte e i numeri dall'altra, nessuna prova poteva
    dire quale delle due fosse quella giusta."""
    ponte._logga_uso(
        _esito({"input_tokens": 999},
               risultato={"modelUsage": {"claude-opus-4-8": {
                   "inputTokens": 11, "outputTokens": 4}}}),
        "job-una-chiave")

    assert len(registro) == 1
    assert registro[0][1] == "claude-opus-4-8"
    assert registro[0][2]["token_in"] == 11
    assert registro[0][2]["token_out"] == 4


def test_senza_il_modello_vero_l_alias_si_dichiara_come_alias(registro):
    """Ripiego DICHIARATO: la pagina deve poter dire a chi legge che quel
    nome e' cio' che abbiamo chiesto, non cio' che abbiamo misurato."""
    ponte._logga_uso(_esito({"input_tokens": 1, "model": "opus"}), "job-4")

    assert registro[0][1] == "opus (alias)"


def test_senza_registro_il_ponte_logga_e_basta_come_prima():
    """Il percorso a processo separato (`main()`, il gateway esterno) non ha
    `/data`: li' il registro resta `None` e il turno non deve rompersi."""
    ponte.set_usage_logger(None)
    ponte._logga_uso(_esito({"input_tokens": 1}), "job-5")


def test_un_turno_senza_usage_non_scrive_niente(registro):
    ponte._logga_uso(_esito({}), "job-6")
    assert registro == []
