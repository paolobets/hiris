"""Le parole dei consumi: cinque stati del costo.

Il costo di una riga non e' sempre un numero, e i modi in cui puo' non esserlo
non sono lo stesso modo. Un modello in casa costa zero DAVVERO; l'abbonamento
non espone il prezzo del singolo turno; un modello fuori listino ha un prezzo
che noi non conosciamo. Appiattirli tutti su 0,00 e' la bugia da cui nasce
questa fetta, e la pagina Consumi la commetteva su due fronti insieme --
ogni identificativo OpenRouter e, misurato il 21/08/2026 sull'installazione
vera, anche `claude-opus-4-8`, che in `pricing.py` non c'e'.
"""
from __future__ import annotations

from ..backends.pricing import prezzo_noto
from ..providers import get

# Dal piu' DEBOLE al piu' forte. `reale` sta sopra `misurato` perche' e' un
# fatto -- quanto e' stato addebitato -- e non una stima da listino.
STATES: tuple[str, ...] = ("non_noto", "compreso", "gratuito", "misurato", "reale")

# I nomi delle sezioni (`LABEL`) e le loro note (`NOTE`) stavano qui, con
# nomi diversi da quelli della pagina Modelli («API Anthropic», «Abbonamento
# Claude») e il piano sotto la chiave `ponte`. Dalla Tappa 7 (Task 9, D9a e
# D10a) sono campi della tabella dei provider (`Provider.name`,
# `Provider.usage_note`), e il piano e' `subscription` anche qui.


def piu_debole(a: str, b: str) -> str:
    """Lo stato piu' debole fra due.

    Una riga non puo' mai affermare piu' della chiamata peggiore che contiene:
    se in uno stesso giorno lo stesso modello produce una chiamata col costo
    dichiarato e una senza, la riga dice `non_noto`, non `reale`.
    """
    return min(a, b, key=lambda s: STATES.index(s) if s in STATES else 0)


def cost_state_and_value(provider: str, model: str, *,
                  cost_dichiarato: float | None,
                  cost_da_listino: float | None) -> tuple[str, float | None]:
    """Lo stato del costo di UNA chiamata, e il costo che le corrisponde.

    `cost_dichiarato` e' quello che il provider ha detto di aver addebitato --
    OpenRouter lo mette in `usage.cost` a ogni risposta, sempre, anche in
    streaming. `cost_da_listino` e' quello che il runner ha calcolato dai
    prezzi in `pricing.py`, e vale solo se quel modello e' davvero in tabella:
    altrimenti e' lo zero del ripiego, che non significa «gratis».

    Lo stato FISSO di un provider -- `compreso` per il piano, `gratuito` per
    Ollama -- lo dice la tabella dei provider (`Provider.cost_state`).
    """
    fixed = getattr(get(provider), "cost_state", "")
    if fixed == "compreso":
        return "compreso", None
    if fixed == "gratuito" or model.endswith(":free"):
        return "gratuito", 0.0
    if cost_dichiarato is not None:
        return "reale", float(cost_dichiarato)
    if prezzo_noto(model):
        return "misurato", float(cost_da_listino or 0.0)
    return "non_noto", None

