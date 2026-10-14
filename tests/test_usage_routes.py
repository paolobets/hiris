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

from hiris.app.api import handlers_usage
from hiris.app.api.handlers_usage import (
    handle_reset_usage,
    handle_usage,
    handle_usage_history,
)
from hiris.app.home_space.reader import HOME_SPACE_KEY
from hiris.app.live_value import LiveValue
from hiris.app.llm_router import LLM_ROUTER_KEY
from hiris.app.startup import live_values
from hiris.app.steering import BRIDGE_ACTIVE_KEY
from hiris.app.usage.store import USAGE_KEY, UsageStore
from tests._anagrafe_finta import AnagrafeFinta

ROMA = "Europe/Rome"
T21 = 1787324400.0   # 21/08/2026 17:00
T22 = 1787410800.0   # 22/08/2026 17:00


class _Req:
    """Il minimo che i tre handler usano: `request.app` e `request.query`."""

    def __init__(self, app, query=None):
        self.app = app
        self.query = query or {}


def _archivio_casa(fuso):
    """Il minimo che `historian.house_timezone` legge: il fuso nella cornice
    dell'anagrafe vera. Sostituisce `app["fuso_casa"]` (riparazione-
    impoverisce-brief.md, appendice punto 7): quella chiave non la popolava
    nessun codice di produzione, solo una finta. La strada vera passa da
    `archivio_casa`, come ogni altra lettura del fuso nel prodotto."""
    return AnagrafeFinta(cornice={"fuso": fuso})


# Se `HomeSpace.reference_frame` cambia firma, questa riga cade invece
# di lasciare che il finto imiti un contratto che non esiste piu' (fetta «la
# rinomina», Task 8 -- la stessa classe di difetto gia' misurata nel Task 7).


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
        yield {**live_values(), USAGE_KEY: archivio, LLM_ROUTER_KEY: object(),
              HOME_SPACE_KEY: _archivio_casa(ROMA)}
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
    # D10a: il nome della pagina Modelli (era «API Anthropic»).
    assert sezione["label"] == "Claude API"
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
        "cost_is_number", "cost_is_floor", "cost_word",
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
        corpo = _corpo(_chiama(handle_usage, {**live_values(), USAGE_KEY: empty}))
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
        corpo = _corpo(_chiama(handle_usage,
                               {**live_values(),
                                USAGE_KEY: empty, BRIDGE_ACTIVE_KEY: LiveValue(True)}))
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
    # `_counters_out` le mappa a mano, e questa riga e' cio' che impedisce
    # alla mappa di tornare uno spread: una colonna aggiunta a
    # `consumo_giorno` che comparisse qui da sola fa rosso. `cost_state` c'e'
    # dal 05/10/2026 (C-08, Tappa 4, Task 5): il secchiello e la riga di
    # modello escono dallo stesso mappatore. La lettura del costo
    # (`cost_is_number`, `cost_is_floor`, `cost_word`) dal 13/10/2026, C-10:
    # la pagina non ricopia piu' gli stati del costo.
    assert set(secchiello) == {
        "requests", "token_in", "token_out", "cache_read", "cache_write",
        "rate_limit_errors", "cost_usd", "cost_eur", "cost_state",
        "cost_is_number", "cost_is_floor", "cost_word",
    }
    assert secchiello["requests"] == 1


def test_la_storia_senza_parametri_da_gli_ultimi_trenta_giorni(app):
    corpo = _corpo(_chiama(handle_usage_history, app))
    assert "from" in corpo and "to" in corpo
    assert isinstance(corpo["days"], list)


def test_dopo_mezzanotte_il_giorno_CORRENTE_e_quello_della_casa(app, monkeypatch):
    """Audit delle fondamenta, rilievo 10: due lettori, due definizioni di «giorno».

    I secchielli si scrivono con `historian.local_date` (il fuso della casa) e questa
    rotta calcolava `to` e `from` con `datetime.fromtimestamp(..., UTC)`.
    Alle 00:30 di Roma il turno appena fatto va nel secchiello del giorno
    NUOVO e il `to` predefinito era ancora quello vecchio: il giorno corrente
    spariva dal grafico e dalla tabella fra mezzanotte e le due (l'una
    d'inverno). La pagina chiama questa rotta senza parametri
    (`usage-route.js`), quindi e' il caso normale, non un caso limite.
    """
    just_after_midnight = 1787351400.0  # 22/08/2026 00:30 a Roma = 21/08 22:30 UTC
    app[USAGE_KEY].log("claude", "claude-sonnet-4-6", token_in=7,
                     cost_usd=0.1, cost_state="misurato", now=just_after_midnight)
    monkeypatch.setattr(handlers_usage.time, "time", lambda: just_after_midnight)

    corpo = _corpo(_chiama(handle_usage_history, app))

    assert corpo["to"] == "2026-08-22", (
        "a Roma e' gia' il 22: in UTC sarebbe il 21, e il secchiello di "
        "stanotte resterebbe fuori dall'intervallo")
    assert "2026-08-22" in [g["day"] for g in corpo["days"]], (
        "il consumo appena registrato deve stare nel grafico che lo mostra")


def test_senza_fuso_noto_la_storia_conta_in_UTC_e_non_inventa(tmp_path, monkeypatch):
    """Il ripiego dichiarato di `historian.local_date`: quando l'anagrafe non sa il fuso
    si conta in UTC -- da entrambe le parti. Cio' che non deve succedere e'
    che una parte ripieghi su UTC e l'altra sull'orologio del container."""
    archivio = UsageStore(str(tmp_path / "c.db"), read_timezone=lambda: "")
    try:
        just_after_midnight = 1787351400.0
        archivio.log("claude", "m", cost_state="misurato", now=just_after_midnight)
        app = {**live_values(), USAGE_KEY: archivio}
        monkeypatch.setattr(handlers_usage.time, "time", lambda: just_after_midnight)

        corpo = _corpo(_chiama(handle_usage_history, app))

        assert corpo["to"] == "2026-08-21", "in UTC e' ancora il 21"
        assert [g["day"] for g in corpo["days"]] == ["2026-08-21"]
    finally:
        archivio.close()


# ── l'ancora ────────────────────────────────────────────────────────────────

def test_azzerare_sposta_l_ancora_e_NON_cancella(app):
    risposta = _chiama(handle_reset_usage, app)
    assert risposta.status == 200
    corpo = _corpo(risposta)
    assert corpo["deleted"] is False
    assert corpo["last_reset"]

    dopo = _corpo(_chiama(handle_usage, app))
    assert dopo["total_requests"] == 0, "il pulsante deve portare a zero"
    assert app[USAGE_KEY].totali()["richieste"] == 2, "e la storia resta intera"


def test_azzerare_non_risponde_piu_409_su_un_archivio_vuoto(tmp_path):
    """Il 409 diceva «non c'e' niente da azzerare». Con l'archivio c'e'
    sempre un'ancora da spostare."""
    empty = UsageStore(str(tmp_path / "v.db"))
    try:
        assert _chiama(handle_reset_usage, {**live_values(), USAGE_KEY: empty}).status == 200
    finally:
        empty.close()


def test_l_interruttore_da_sempre_cambia_davvero_i_numeri(app):
    """La pagina ha un interruttore «da ultimo azzeramento / da sempre». Se il
    server ignorasse il parametro sarebbe un pulsante che non fa niente --
    difetto trovato rileggendo il proprio codice, non da un test caduto."""
    app[USAGE_KEY].sposta_anchor(T22 + 3600)

    da_anchor = _corpo(_chiama(handle_usage, app))
    da_sempre = _corpo(_chiama(handle_usage, app, {"from": "sempre"}))

    assert da_anchor["total_requests"] == 0, "dopo l'ancora non si e' consumato niente"
    assert da_sempre["total_requests"] == 2, "la storia intera c'e' ancora"


def test_il_secchiello_dice_lo_stato_del_costo_come_la_riga_di_modello(tmp_path):
    """C-08 (Tappa 4, Task 5): il secchiello di un giorno porta `cost_state`,
    con la stessa regola della riga di modello (`UsageStore._state_columns`):
    se anche un solo modello di quel provider, quel giorno, ha un costo
    ignoto, il secchiello lo e'. E i campi che le due righe hanno in comune
    escono uguali, perche' escono dallo stesso mappatore.

    Mutazioni eseguite: il secchiello senza `costo_stato` nell'archivio ->
    rossa (KeyError); la lettura che usa il solo `MIN` alfabetico -> rossa sul
    giorno misto (direbbe «gratuito»)."""
    archivio = UsageStore(str(tmp_path / "usage.db"), read_timezone=lambda: ROMA)
    # «gratuito» viene PRIMA di «non_noto» in ordine alfabetico: e' il caso
    # in cui il solo `MIN` sbaglierebbe.
    archivio.log("openrouter", "a/gratis:free", token_in=1, cost_usd=0.0,
                 cost_state="gratuito", now=T21)
    archivio.log("openrouter", "b/ignoto", token_in=1, cost_usd=None,
                 cost_state="non_noto", now=T21)
    archivio.log("claude", "claude-sonnet-4-6", token_in=1, cost_usd=0.1,
                 cost_state="misurato", now=T22)
    app = {**live_values(), USAGE_KEY: archivio, HOME_SPACE_KEY: _archivio_casa(ROMA)}
    try:
        corpo = _corpo(_chiama(handle_usage_history, app,
                               {"from": "2026-08-21", "to": "2026-08-22"}))
        riga = _corpo(_chiama(handle_usage, app, {"from": "sempre"}))
    finally:
        archivio.close()
    giorni = {g["day"]: g["per_provider"] for g in corpo["days"]}
    assert giorni["2026-08-21"]["openrouter"]["cost_state"] == "non_noto"
    assert giorni["2026-08-22"]["claude"]["cost_state"] == "misurato"

    modello = next(m for s in riga["sections"] for m in s["models"]
                   if m["model"] == "claude-sonnet-4-6")
    secchiello = giorni["2026-08-22"]["claude"]
    comuni = set(modello) & set(secchiello)
    assert comuni == set(secchiello)
    assert {k: modello[k] for k in comuni} == secchiello


@pytest.mark.parametrize("cost_eur", [None, 0, 0.0])
def test_il_pavimento_chiede_un_costo_sopra_lo_zero(cost_eur):
    """N155-3 (giro 155): un costo `non_noto` e' un pavimento («almeno
    questo») solo se c'e' un numero sopra lo zero. A zero direbbe «pagato di
    sicuro 0 EUR, piu' qualcosa». Mutazione del revisore, ora ESEGUITA
    (13/10/2026): `cost_eur is not None` -- rossa su 0."""
    floor = handlers_usage._COST_FLOOR
    assert handlers_usage._cost_reading(floor, cost_eur)["cost_is_floor"] is False
    assert handlers_usage._cost_reading(floor, 0.01)["cost_is_floor"] is True
