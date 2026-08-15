"""L'elenco dei modelli di Claude API, letto invece che indovinato.

Fino alla 3.1.0 `handlers_models` diceva «Anthropic non espone un endpoint
pubblico», e la pagina lo ripeteva all'utente con parole sue: «Anthropic non
pubblica un elenco: questi sono i modelli che HIRIS conosce».

**E' falso.** `GET https://api.anthropic.com/v1/models` esiste -- verificato
sulla documentazione ufficiale il 15 agosto 2026, non dedotto: header
`x-api-key` + `anthropic-version`, paginato (`limit` 1-1000), ordinato dai piu'
recenti, e ogni voce porta `id`, `display_name`, `created_at` e `capabilities`.
Vuole una CHIAVE API: col token del piano non risponde.

`_CLAUDE_MODELS` resta come RISERVA -- una lista di tre nomi scritta a mano che
invecchia da sola -- e da questa fetta si dichiara per quello che e' invece di
presentarsi come tutto cio' che esiste.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiris.app.api import handlers_models
from hiris.app.decisione_modelli import provenienza

# Le due finte vivono gia' in `test_handlers_models_openrouter.py`: si riusano
# invece di riscriverne di nuove. Due finte che fingono la stessa cosa sono la
# seconda rappresentazione in miniatura, e divergono come tutte le seconde
# rappresentazioni.
from tests.test_handlers_models_openrouter import (  # noqa: E402
    _mock_che_solleva, _mock_openrouter_response,
)
# La fixture `client` (app vera via `create_app()`), la stessa che
# `tests/test_models_api.py` importa. Serve alla prova sulla chiave assente.
from tests.test_api import client  # noqa: F401,E402


def _mock_risposta_con_stato(stato: int):
    """L'unica finta che manca di la': `_mock_openrouter_response` inchioda
    `status=200`, e qui serve un 401 -- il caso di gran lunga piu' probabile su
    questa rotta, perche' la chiave c'e' ma puo' essere sbagliata o revocata."""
    response_cm = MagicMock()
    response_cm.__aenter__ = AsyncMock(return_value=MagicMock(
        status=stato, json=AsyncMock(return_value={"error": "x"})))
    response_cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=response_cm)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    return session_cm


# ── Le quattro letture ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_una_lettura_riuscita_si_dichiara_viva_e_tiene_l_ordine():
    """L'ordine e' quello dell'API -- i piu' recenti per primi, lo dichiara la
    documentazione -- e non si riordina. Riordinare qui sarebbe una curatela
    che nessuno ha chiesto, e nasconderebbe qual e' il modello nuovo."""
    payload = {"data": [{"id": "claude-opus-4-7"},
                        {"id": "claude-sonnet-4-6"},
                        {"id": "claude-haiku-4-5-20251001"}]}
    with patch("aiohttp.ClientSession", return_value=_mock_openrouter_response(payload)):
        modelli, fonte = await handlers_models._fetch_claude_models("sk-test")
    assert fonte == "viva"
    assert modelli == ["claude-opus-4-7", "claude-sonnet-4-6",
                       "claude-haiku-4-5-20251001"]


@pytest.mark.asyncio
async def test_un_200_vuoto_non_e_una_lettura_riuscita():
    """La stessa regola gia' scritta per OpenAI: «viva» su un elenco vuoto
    sarebbe una parola piu' larga del fatto."""
    with patch("aiohttp.ClientSession",
               return_value=_mock_openrouter_response({"data": []})):
        modelli, fonte = await handlers_models._fetch_claude_models("sk-test")
    assert fonte == "riserva"
    assert modelli == handlers_models._CLAUDE_MODELS


@pytest.mark.asyncio
async def test_una_chiave_rifiutata_dichiara_la_riserva():
    """Il caso vero: la chiave c'e' -- quindi il provider ha un elenco, quindi
    il pannello prova a leggerlo -- ma e' sbagliata o senza credito."""
    with patch("aiohttp.ClientSession", return_value=_mock_risposta_con_stato(401)):
        modelli, fonte = await handlers_models._fetch_claude_models("sk-sbagliata")
    assert fonte == "riserva"
    assert modelli == handlers_models._CLAUDE_MODELS


@pytest.mark.asyncio
async def test_una_rete_che_cade_dichiara_la_riserva():
    with patch("aiohttp.ClientSession", return_value=_mock_che_solleva()):
        modelli, fonte = await handlers_models._fetch_claude_models("sk-test")
    assert fonte == "riserva"
    assert modelli == handlers_models._CLAUDE_MODELS


# ── La provenienza: due rami cancellati, non uno aggiunto ──────────────────

def test_la_provenienza_nomina_l_ospite_che_non_ha_risposto():
    """«Non ho potuto leggere» senza il nome di chi non ha risposto e' meno di
    quanto il sistema sa. Qui viveva un ramo `if provider_id == "claude"` con
    una frase propria che diceva il falso: e' USCITO, e il percorso generico
    produce gia' le due frasi giuste. L'unica cosa che serviva era una riga in
    `_OSPITI`."""
    riga = provenienza("claude", "riserva")
    assert "api.anthropic.com" in riga
    assert "non ho potuto leggere" in riga.lower()


def test_e_quando_la_lettura_riesce_lo_dice():
    assert provenienza("claude", "viva") == "Letti da api.anthropic.com adesso."


@pytest.mark.asyncio
async def test_senza_chiave_claude_api_non_ha_nessun_elenco_da_leggere(client):
    """Uguale a OpenAI e a OpenRouter da questa fetta. Il ramo che dava a
    Claude un elenco anche senza chiave serviva al piano -- la ragione era
    scritta accanto -- e il piano ha un campo suo adesso.

    E' una PERDITA dichiarata: senza chiave non si sfogliano piu' i modelli di
    Claude API. Erano voci inerti (senza chiave quel provider non entra in
    catena), ma la perdita e' vera e questo test la inchioda invece di
    lasciarla scoprire a qualcuno."""
    client.app["claude_api_key"] = ""
    resp = await client.get("/api/models?provider=claude")
    assert resp.status == 200
    voce = (await resp.json())["providers"][0]
    assert voce["id"] == "claude"
    assert voce["fonte"] == "assente"
    assert voce["modelli"] == []
    assert voce["provenienza"] == provenienza("claude", "assente")
    assert "manca la chiave" in voce["provenienza"]


def test_la_frase_falsa_su_anthropic_non_si_dice_piu_da_nessuna_parte():
    """Non deve poter rientrare per riscrittura distratta. E' una affermazione
    su un fornitore, e questa fetta esiste anche perche' era sbagliata."""
    import pathlib
    radice = pathlib.Path(handlers_models.__file__).parent.parent
    for sorgente in radice.rglob("*.py"):
        testo = sorgente.read_text(encoding="utf-8")
        assert "Anthropic non pubblica un elenco" not in testo, sorgente
        assert "non espone un endpoint pubblico" not in testo, sorgente
