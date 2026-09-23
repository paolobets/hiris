"""Dove va il tuo dato, detto nella pagina dove accendi il provider (C-5a).

**Perché la traduzione dell'add-on non basta.** Le quattro credenziali hanno
la loro riga di `PRIVACY:` in `translations/*.yaml`, e il Piano Max l'ha presa
il 21/09. Ma la pagina del Supervisor dove quelle righe si leggono è il posto
dove si **incolla una chiave**, non quello dove si **decide chi risponde**:
quella decisione — la catena, il ponte acceso — si prende nella pagina Modelli
di HIRIS, che è un'altra pagina, e fino a oggi lì non c'era scritto niente.

Chi accende il piano dalla pagina Modelli non è mai passato dalla riga di
privacy, e un prodotto distribuito in Europa che manda i dati di casa a un
fornitore terzo deve dirlo **dove il gesto si fa**.

**La frase arriva dal payload**, come ogni altra affermazione sul prodotto in
questa pagina: `models-route.js` non compone frasi, e un `if (id ===
'subscription')` nel frontend sarebbe la regola del prodotto scritta una
seconda volta in un'altra lingua.
"""
import pathlib

from hiris.app import model_resolution as mr

RADICE = pathlib.Path(__file__).resolve().parents[1]


def test_ogni_provider_dichiara_dove_va_il_dato():
    """Tutti e cinque, nessuno escluso: un elenco in cui uno tace si legge come
    «di quello non si sa», che e' la cosa peggiore da dire sulla privacy.

    Mutazione ESEGUITA: togliere una voce -- rossa."""
    for pid in mr.FIXED_ORDER:
        assert mr.privacy(pid), f"«{pid}» non dice dove va il dato"


def test_il_piano_dichiara_le_SUE_condizioni_di_conservazione():
    """Il fatto che distingue il piano dall'API a consumo, ed e' il fatto che
    conta: **le condizioni d'uso e di conservazione del Piano Max sono diverse
    da quelle dell'API**. Un «passa da Anthropic» buono per tutti e due
    nasconderebbe proprio la differenza.

    Mutazione ESEGUITA: dare al piano la frase di Claude API -- rossa."""
    frase = mr.privacy("subscription")

    assert "conservazione" in frase
    assert "divers" in frase.lower()
    assert frase != mr.privacy("claude")


def test_Ollama_dice_che_NON_esce():
    """L'altra meta', e non e' un dettaglio: chi sceglie Ollama lo sceglie per
    questo, e vederselo scritto e' la ragione per cui la riga esiste.

    Mutazione ESEGUITA: dare a Ollama una frase qualunque -- rossa."""
    frase = mr.privacy("ollama")

    assert "non esce" in frase.lower()


def test_la_frase_viaggia_nella_RIGA_della_catena():
    """Non in una nota a pie' di pagina: nella riga del provider, dove sta il
    gesto che lo accende.

    Mutazione ESEGUITA: togliere la chiave dalla riga -- rossa."""
    catena, fuori = mr.compose_topology(
        chain_order=["claude"],
        credentials={"claude": True, "subscription": True},
        models={"claude": "claude-opus-4-7"},
        bridge_active=True,
        occurrences={},
        now=0.0,
    )
    per_id = {r["id"]: r for r in catena + fuori}

    assert per_id["subscription"]["privacy"] == mr.privacy("subscription")
    assert per_id["claude"]["privacy"] == mr.privacy("claude")


def test_la_pagina_DISEGNA_la_frase_e_non_la_compone():
    """La regola di questo file: nessuna affermazione sul prodotto scritta in
    JavaScript. La pagina legge `privacy` dal payload; se lo componesse qui,
    domani direbbe una cosa diversa dal backend senza che nessuno lo veda.

    Mutazione ESEGUITA: togliere l'uso di `privacy` dalla pagina -- rossa."""
    sorgente = (RADICE / "hiris/app/static/config/models-route.js").read_text(
        encoding="utf-8")

    assert "data.privacy" in sorgente
    assert "row-privacy" in sorgente
    for parola in ("Anthropic", "conservazione", "OpenRouter (USA)"):
        assert parola not in sorgente, (
            f"«{parola}» e' un'affermazione sul prodotto scritta nella pagina")
