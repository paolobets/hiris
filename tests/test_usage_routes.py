"""Le tre rotte dei consumi: il riepilogo, la storia, l'ancora.

`GET /api/usage` resta la rotta LEGGERA. Non e' cortesia verso il passato: il
riquadro «Utilizzo» della chat la richiama a intervalli e legge `measured`,
`total_requests`, `input_tokens`, `output_tokens`, `cost_eur`, `last_reset`,
`messaggio`. Appesantirla con trenta giorni di serie storica farebbe pagare a
ogni giro della chat una domanda che la chat non fa -- da cui la seconda
rotta.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from hiris.app.api.handlers_usage import (
    handle_reset_usage,
    handle_usage,
    handle_usage_history,
)
from hiris.app.home_space.store import HomeSpaceStore
from hiris.app.usage.store import UsageStore
from tests._contracts import assert_stessa_firma

ROMA = "Europe/Rome"
T21 = 1787324400.0   # 21/08/2026 17:00
T22 = 1787410800.0   # 22/08/2026 17:00


class _Req:
    """Il minimo che i tre handler usano: `request.app` e `request.query`."""

    def __init__(self, app, query=None):
        self.app = app
        self.query = query or {}


class _ArchivioCasaFinto:
    """Il minimo che `_timezone_from_home_space_store` (`server.py`) legge:
    `reference_frame()`. Sostituisce `app["fuso_casa"]` (riparazione-
    impoverisce-brief.md, appendice punto 7): quella chiave non la popolava
    nessun codice di produzione, solo questa finta -- il difetto che questo
    progetto chiama «chi lo riempie?». La strada vera passa da
    `archivio_casa`, come ogni altra lettura del fuso nel prodotto."""

    def __init__(self, fuso):
        self._fuso = fuso

    def reference_frame(self):
        return {"fuso": self._fuso}


# Se `HomeSpaceStore.reference_frame` cambia firma, questa riga cade invece
# di lasciare che il finto imiti un contratto che non esiste piu' (fetta «la
# rinomina», Task 8 -- la stessa classe di difetto gia' misurata nel Task 7).
assert_stessa_firma(HomeSpaceStore.reference_frame, _ArchivioCasaFinto.reference_frame,
                     nome="reference_frame")


def _corpo(risposta):
    return json.loads(risposta.body.decode("utf-8"))


def _chiama(handler, app, query=None):
    return asyncio.run(handler(_Req(app, query)))


@pytest.fixture
def app(tmp_path):
    archivio = UsageStore(str(tmp_path / "consumi.db"), read_timezone=lambda: ROMA)
    archivio.log("claude", "claude-sonnet-4-6", token_in=100, token_out=10,
                      cache_read=40, cache_write=20, cost_usd=1.0,
                      cost_state="misurato", now=T21)
    archivio.log("openrouter", "un/modello", token_in=50, token_out=5,
                      cost_usd=None, cost_state="non_noto", now=T22)
    try:
        yield {"consumi": archivio, "llm_router": object(),
              "archivio_casa": _ArchivioCasaFinto(ROMA)}
    finally:
        archivio.close()


# ── il riepilogo ────────────────────────────────────────────────────────────

def test_i_campi_che_la_chat_legge_non_cambiano(app):
    corpo = _corpo(_chiama(handle_usage, app))
    for campo in ("measured", "total_requests", "input_tokens", "output_tokens",
                  "cost_usd", "cost_eur", "last_reset"):
        assert campo in corpo, (
            f"«{campo}» lo legge il riquadro della chat: toglierlo lo spegne")
    assert corpo["measured"] is True
    assert corpo["total_requests"] == 2


def test_input_tokens_in_cima_e_INCLUSIVO_della_cache(app):
    """Nelle righe `token_in` sono i token puri e la cache ha campi suoi; in
    cima resta la somma dei tre, che e' la quantita' che la pagina e la chat
    mostravano prima. Sommare la sola colonna pura farebbe CROLLARE il numero
    e sembrerebbe una perdita di dati."""
    corpo = _corpo(_chiama(handle_usage, app))
    assert corpo["input_tokens"] == 100 + 40 + 20 + 50


def test_il_totale_si_dichiara_un_pavimento_quando_manca_un_prezzo(app):
    corpo = _corpo(_chiama(handle_usage, app))
    assert corpo["partial_cost"] is True


def test_le_sezioni_ci_sono_solo_per_i_provider_usati(app):
    corpo = _corpo(_chiama(handle_usage, app))
    nomi = [s["provider"] for s in corpo["sections"]]
    assert nomi == ["claude", "openrouter"]
    assert "openai" not in nomi, "mai usato: e' un'assenza, non uno zero"


def test_una_sezione_porta_etichetta_nota_e_modelli(app):
    sezione = _corpo(_chiama(handle_usage, app))["sections"][0]
    assert sezione["label"] == "API Anthropic"
    assert sezione["note"]
    assert sezione["cost_eur"] > 0
    model = sezione["models"][0]
    assert model["model"] == "claude-sonnet-4-6"
    assert model["cost_state"] == "misurato"
    assert model["first_use"] == "2026-08-21"
    # L'INSIEME ESATTO delle chiavi di una riga di modello, non solo quelle
    # che questo test guarda. E' il confine fra le colonne di `usage/store`
    # e HTTP (`_model_out`): una colonna che uscisse da sola col suo nome
    # italiano, o una chiave che sparisse, si vede qui e in nessun altro
    # posto. Trovato con una batteria di mutazioni: `requests` non era
    # nominato da nessun test, e rimetterlo a `richieste` lasciava verdi
    # tutti e quattro i cancelli.
    assert set(model) == {
        "model", "requests", "token_in", "token_out", "cache_read",
        "cache_write", "cost_usd", "cost_eur", "cost_state",
        "rate_limit_errors", "first_use", "last_use",
    }
    assert model["requests"] == 1


def test_un_modello_senza_prezzo_esce_con_costo_NULLO(app):
    openrouter = _corpo(_chiama(handle_usage, app))["sections"][1]
    model = openrouter["models"][0]
    assert model["cost_state"] == "non_noto"
    assert model["cost_eur"] is None, (
        "0.0 direbbe «misurato, e non e' costato niente»: e' la bugia che "
        "l'intera fetta esiste per togliere")


def test_il_fuso_si_dichiara(app):
    corpo = _corpo(_chiama(handle_usage, app))
    assert corpo["timezone"] == ROMA
    assert corpo["timezone_known"] is True


# ── il caso vero di «non si misura» ─────────────────────────────────────────

def test_senza_provider_e_senza_righe_si_dichiara_che_non_si_misura(tmp_path):
    """L'unico caso rimasto: non e' mai stato usato niente e non c'e' niente
    che possa rispondere. Il ramo «abbonamento» ESCE -- l'abbonamento adesso
    si misura, e ha una sezione sua."""
    empty = UsageStore(str(tmp_path / "v.db"))
    try:
        corpo = _corpo(_chiama(handle_usage, {"consumi": empty}))
        assert corpo["measured"] is False
        assert corpo["reason"] == "nessun_provider"
        assert "provider" in corpo["message"].lower()
        for campo in ("total_requests", "input_tokens", "cost_eur"):
            assert corpo[campo] is None, "0 direbbe «misurato, e non hai consumato»"
    finally:
        empty.close()


def test_col_ponte_acceso_e_l_archivio_vuoto_i_consumi_SI_misurano(tmp_path):
    """Il ponte c'e' e puo' rispondere: zero e' un fatto misurato, non
    un'assenza di misura."""
    empty = UsageStore(str(tmp_path / "v.db"))
    try:
        corpo = _corpo(_chiama(handle_usage, {"consumi": empty, "ponte_attivo": True}))
        assert corpo["measured"] is True
        assert corpo["total_requests"] == 0
    finally:
        empty.close()


# ── la storia ───────────────────────────────────────────────────────────────

def test_la_storia_ha_una_rotta_sua_con_i_suoi_parametri(app):
    corpo = _corpo(_chiama(handle_usage_history, app,
                           {"from": "2026-08-21", "to": "2026-08-22"}))
    assert [g["day"] for g in corpo["days"]] == ["2026-08-21", "2026-08-22"]
    secchiello = corpo["days"][0]["per_provider"]["claude"]
    assert secchiello["cost_eur"] > 0
    # L'INSIEME ESATTO del secchiello. Prima di questa fetta questa rotta
    # faceva `{**riga_di_archivio, ...}` -- uno spread crudo -- e le colonne
    # uscivano su HTTP coi loro nomi senza che nessuno l'avesse deciso.
    # `_bucket_out` le mappa a mano, e questa riga e' cio' che impedisce alla
    # mappa di tornare uno spread: una colonna aggiunta a `consumo_giorno`
    # che comparisse qui da sola fa rosso.
    assert set(secchiello) == {
        "requests", "token_in", "token_out", "cache_read", "cache_write",
        "rate_limit_errors", "cost_usd", "cost_eur",
    }
    assert secchiello["requests"] == 1


def test_la_storia_senza_parametri_da_gli_ultimi_trenta_giorni(app):
    corpo = _corpo(_chiama(handle_usage_history, app))
    assert "from" in corpo and "to" in corpo
    assert isinstance(corpo["days"], list)


# ── l'ancora ────────────────────────────────────────────────────────────────

def test_azzerare_sposta_l_ancora_e_NON_cancella(app):
    risposta = _chiama(handle_reset_usage, app)
    assert risposta.status == 200
    corpo = _corpo(risposta)
    assert corpo["deleted"] is False
    assert corpo["last_reset"]

    dopo = _corpo(_chiama(handle_usage, app))
    assert dopo["total_requests"] == 0, "il pulsante deve portare a zero"
    assert app["consumi"].totali()["richieste"] == 2, "e la storia resta intera"


def test_azzerare_non_risponde_piu_409_su_un_archivio_vuoto(tmp_path):
    """Il 409 diceva «non c'e' niente da azzerare». Con l'archivio c'e'
    sempre un'ancora da spostare."""
    empty = UsageStore(str(tmp_path / "v.db"))
    try:
        assert _chiama(handle_reset_usage, {"consumi": empty}).status == 200
    finally:
        empty.close()


def test_l_interruttore_da_sempre_cambia_davvero_i_numeri(app):
    """La pagina ha un interruttore «da ultimo azzeramento / da sempre». Se il
    server ignorasse il parametro sarebbe un pulsante che non fa niente --
    difetto trovato rileggendo il proprio codice, non da un test caduto."""
    app["consumi"].sposta_anchor(T22 + 3600)

    da_anchor = _corpo(_chiama(handle_usage, app))
    da_sempre = _corpo(_chiama(handle_usage, app, {"from": "sempre"}))

    assert da_anchor["total_requests"] == 0, "dopo l'ancora non si e' consumato niente"
    assert da_sempre["total_requests"] == 2, "la storia intera c'e' ancora"
