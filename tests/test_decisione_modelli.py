"""La decisione già presa: chi risponde al prossimo messaggio, e perché.

Ogni test qui è una frase che la pagina dirà all'utente. Se una di queste
cade, la pagina ha ricominciato a essere vera riga per riga e falsa nel
complesso.
"""
import pytest

from hiris.app.decisione_modelli import componi_adesso, natura, nome


def test_il_primo_della_catena_e_quello_che_risponde():
    d = componi_adesso(
        catena=["claude", "openrouter"],
        credenziali={"claude": True, "openrouter": True, "subscription": False},
        modelli={"claude": "claude-opus-4-7", "openrouter": "anthropic/claude-sonnet-4-6"},
        ponte_attivo=False,
    )
    assert d["chi"] == "claude"
    assert d["via"] == "catena"
    assert d["frase"] == "Il prossimo messaggio va a Claude API, con claude-opus-4-7, a consumo."


def test_col_ponte_acceso_risponde_il_piano_e_la_catena_non_viene_consultata():
    """Il ponte NON è un anello: `handlers_chat.handle_chat` dirotta prima di
    prendere il router, e la catena non viene consultata mai. La frase deve
    dire quello, non l'ordine della catena."""
    d = componi_adesso(
        catena=["claude", "openrouter"],
        credenziali={"claude": True, "openrouter": True, "subscription": True},
        modelli={"claude": "claude-opus-4-7", "subscription": "opus"},
        ponte_attivo=True,
    )
    assert d["chi"] == "subscription"
    assert d["via"] == "ponte"
    assert d["frase"] == "Il prossimo messaggio va a Piano Claude Max, con opus, nel piano."
    testi = [x["testo"] for x in d["diagnosi"]]
    assert any("la catena qui sotto non viene consultata" in t for t in testi), testi


def test_il_piano_pagato_e_fuori_dalla_catena_e_uno_spreco_dichiarato():
    """Il caso del proprietario: token presente, piano pagato, ponte spento.
    È la riga che costa di più, ed è quella che porta l'azione consigliata."""
    d = componi_adesso(
        catena=["claude", "openrouter"],
        credenziali={"claude": True, "openrouter": True, "subscription": True},
        modelli={"claude": "claude-opus-4-7", "openrouter": "anthropic/claude-sonnet-4-6"},
        ponte_attivo=False,
    )
    spreco = [x for x in d["diagnosi"] if x["gravita"] == "spreco"]
    assert len(spreco) == 1
    assert spreco[0]["testo"] == (
        "Il Piano Claude Max ha il token, lo paghi, ed è fuori dalla catena."
    )


def test_senza_token_del_piano_non_si_dichiara_nessuno_spreco():
    """La prova gemella della precedente: la diagnosi è un'affermazione su una
    cosa MISURATA (il token c'è), non un consiglio che si dà sempre."""
    d = componi_adesso(
        catena=["claude"],
        credenziali={"claude": True, "subscription": False},
        modelli={"claude": "claude-opus-4-7"},
        ponte_attivo=False,
    )
    assert [x for x in d["diagnosi"] if x["gravita"] == "spreco"] == []


def test_catena_vuota_e_ponte_spento_lo_dice_invece_di_tacere():
    d = componi_adesso(catena=[], credenziali={}, modelli={}, ponte_attivo=False)
    assert d["chi"] is None
    assert d["nome"] == "" and d["natura"] == "" and d["via"] == ""
    assert d["frase"] == "HIRIS non può ancora rispondere: la catena è vuota."
    assert [x["gravita"] for x in d["diagnosi"]] == ["guasto"]


def test_un_provider_senza_modello_noto_non_inventa_un_modello():
    d = componi_adesso(
        catena=["ollama"], credenziali={"ollama": True}, modelli={"ollama": ""},
        ponte_attivo=False,
    )
    assert d["modello"] == ""
    assert d["frase"] == "Il prossimo messaggio va a Ollama (in casa), in casa."


def test_le_sette_chiavi_ci_sono_sempre():
    """Il frontend disegna quello che riceve: una chiave assente sarebbe un
    `undefined` a schermo."""
    for d in (
        componi_adesso(catena=[], credenziali={}, modelli={}, ponte_attivo=False),
        componi_adesso(catena=["claude"], credenziali={"claude": True},
                       modelli={"claude": "x"}, ponte_attivo=False),
    ):
        assert set(d) == {"chi", "nome", "modello", "natura", "via", "frase", "diagnosi"}


@pytest.mark.parametrize("pid,atteso", [
    ("subscription", "Piano Claude Max"),
    ("claude", "Claude API"),
    ("openrouter", "OpenRouter"),
    ("openai", "OpenAI"),
    ("ollama", "Ollama (in casa)"),
])
def test_un_nome_per_provider_mai_due(pid, atteso):
    """Oggi coesistono «Abbonamento (Claude Max)», «Abbonamento Claude
    (subscription)» e «Piano Claude Max»: tre nomi per una cosa, uno per ogni
    file. Da qui in poi il nome è uno, e sta qui."""
    assert nome(pid) == atteso


@pytest.mark.parametrize("pid,atteso", [
    ("subscription", "nel piano"), ("claude", "a consumo"),
    ("openrouter", "a consumo"), ("openai", "a consumo"), ("ollama", "in casa"),
])
def test_le_quattro_nature_e_non_un_prezzo(pid, atteso):
    """HIRIS non ha una fonte di prezzi e un prezzo vecchio è peggio di nessun
    prezzo. Le nature bastano per ordinare una catena (progetto §12.1)."""
    assert natura(pid) == atteso
