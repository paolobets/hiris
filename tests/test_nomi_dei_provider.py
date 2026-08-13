"""Un nome per provider, mai due.

Fino alla 2.4.1 l'abbonamento ne aveva tre -- «Abbonamento (Claude Max)»,
«Abbonamento Claude (subscription)», «Piano Claude Max» -- uno per ogni file
che aveva bisogno di nominarlo. Chi leggeva la pagina add-on, la pagina Modelli
e il registro vedeva tre cose e doveva capire da solo che erano la stessa.
Questo file impedisce che ne nasca un quarto.
"""
from pathlib import Path

import pytest

from hiris.app.decisione_modelli import NOMI

BASE = Path(__file__).resolve().parents[1] / "hiris"

NOMI_RITIRATI = (
    "Abbonamento (Claude Max)",
    "Abbonamento Claude (subscription)",
    "Claude (Anthropic API)",
    "Claude (Anthropic)",
    "Ollama (locale)",
    "Locale (Ollama)",
    "OpenRouter (200+ modelli)",
)

_SUPERFICI = (
    BASE / "app" / "api" / "handlers_models.py",
    BASE / "app" / "static" / "config" / "models-route.js",
)


def _righe_vive(percorso: Path) -> str:
    """Solo le righe non commentate: un commento che RACCONTA un nome ritirato
    non è quel nome vivo. Stesso criterio di
    `test_pagina_configurazione.test_chat_policy_e_uscita_da_tutti_e_cinque_i_posti`."""
    marcatore = "#" if percorso.suffix == ".py" else "//"
    return "\n".join(
        r for r in percorso.read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith(marcatore)
    )


@pytest.mark.parametrize("percorso", _SUPERFICI, ids=lambda p: p.name)
@pytest.mark.parametrize("ritirato", NOMI_RITIRATI)
def test_nessun_nome_ritirato_sopravvive(percorso, ritirato):
    assert ritirato not in _righe_vive(percorso), (
        f"{percorso.name} nomina ancora un provider con «{ritirato}»: "
        "il nome è uno solo e sta in decisione_modelli.NOMI"
    )


def test_i_cinque_nomi_sono_quelli_e_solo_quelli():
    assert NOMI == {
        "subscription": "Piano Claude Max",
        "claude": "Claude API",
        "openrouter": "OpenRouter",
        "openai": "OpenAI",
        "ollama": "Ollama (in casa)",
    }
