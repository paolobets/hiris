"""Il vocabolario dei consumi: gli stati del costo.

(Il giorno della casa, che qui si chiamava `local_day`, e' uscito con la
Tappa 3, Task 10: vive in `historian.local_date`, e le sue prove in
`tests/test_il_tempo_della_casa.py`.)

La regola che questo file difende e' una sola, e vale per tutte e cinque le
voci: **uno zero e' un'affermazione**. Dire «0,00 EUR» dove il prezzo non si
conosce e' lo stesso difetto a tre stati che l'archivio della casa e' stato
scritto per non commettere -- e nella pagina Consumi lo commetteva davvero:
`_prezzo` non conosce nessun identificativo OpenRouter, cade su `_default` =
0.0, e il totale sotto-dichiarava in silenzio.
"""
import pytest

from hiris.app.usage.vocabulary import (
    STATES,
    cost_state_and_value,
    piu_debole,
)


def test_l_ordine_di_forza_va_dal_piu_debole_al_piu_forte():
    assert STATES == ("non_noto", "compreso", "gratuito", "misurato", "reale")


@pytest.mark.parametrize("a,b,atteso", [
    ("reale", "non_noto", "non_noto"),
    ("misurato", "reale", "misurato"),
    ("gratuito", "gratuito", "gratuito"),
    ("compreso", "misurato", "compreso"),
])
def test_una_riga_non_puo_affermare_piu_della_chiamata_peggiore(a, b, atteso):
    assert piu_debole(a, b) == atteso
    assert piu_debole(b, a) == atteso, "l'ordine degli argomenti non conta"


def test_openrouter_col_costo_dichiarato_e_reale():
    stato, costo = cost_state_and_value("openrouter", "anthropic/claude-sonnet-4-6",
                                 cost_dichiarato=0.0031, cost_da_listino=0.0)
    assert stato == "reale"
    assert costo == 0.0031


def test_openrouter_senza_costo_dichiarato_e_non_noto_e_il_costo_e_None():
    """Il difetto da cui nasce l'intera fetta. Se questa finta smettesse di
    produrre `None` il test non varrebbe niente."""
    stato, costo = cost_state_and_value("openrouter", "un/modello-mai-visto",
                                 cost_dichiarato=None, cost_da_listino=0.0)
    assert stato == "non_noto"
    assert costo is None, "0.0 direbbe «misurato, e non e' costato niente»"


def test_un_modello_a_listino_e_misurato():
    stato, costo = cost_state_and_value("claude", "claude-sonnet-4-6",
                                 cost_dichiarato=None, cost_da_listino=1.25)
    assert stato == "misurato"
    assert costo == 1.25


def test_un_modello_claude_fuori_listino_e_non_noto():
    """Misurato sull'installazione vera il 21/08/2026: il modello scelto dal
    proprietario era `claude-opus-4-8`, che in `pricing.py` non c'e'. Anche la
    sezione Anthropic puo' avere righe senza prezzo -- non e' un caso
    esotico di OpenRouter."""
    stato, costo = cost_state_and_value("claude", "claude-opus-4-8",
                                 cost_dichiarato=None, cost_da_listino=0.0)
    assert stato == "non_noto"
    assert costo is None


@pytest.mark.parametrize("provider,model", [
    ("ollama", "qwen2.5:7b"),
    ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
])
def test_i_gratuiti_hanno_uno_zero_DICHIARATO(provider, model):
    stato, costo = cost_state_and_value(provider, model,
                                 cost_dichiarato=None, cost_da_listino=0.0)
    assert stato == "gratuito"
    assert costo == 0.0, "qui lo zero e' vero, e va detto come numero"


def test_il_piano_e_compreso_e_non_ha_un_costo():
    # D9a: il piano e' `subscription` anche nei consumi (era `ponte`).
    stato, costo = cost_state_and_value("subscription", "sonnet",
                                 cost_dichiarato=None, cost_da_listino=0.0)
    assert stato == "compreso"
    assert costo is None, (
        "l'abbonamento non espone il prezzo del turno: 0.0 direbbe «gratis», "
        "che e' un'altra cosa")

