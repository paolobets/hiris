"""La decisione già presa: chi risponde al prossimo messaggio, e perché.

Ogni test qui è una frase che la pagina dirà all'utente. Se una di queste
cade, la pagina ha ricominciato a essere vera riga per riga e falsa nel
complesso.
"""
import pytest

from hiris.app.decisione_modelli import ORDINE_FISSO, componi_adesso, natura, nome


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


def test_ponte_acceso_senza_token_non_e_qualcuno_che_risponde():
    """Lo stato che oggi passa in silenzio: il ponte è acceso, il worker che
    risponde NON parte (gli manca il token), ogni messaggio viene accodato e
    scade. La pagina non deve dire che «il piano risponde»: non risponde
    nessuno."""
    d = componi_adesso(
        catena=["claude"],
        credenziali={"claude": True, "subscription": False},
        modelli={"claude": "claude-opus-4-7", "subscription": "sonnet"},
        ponte_attivo=True,
        scadenza_ponte_min=5,
    )
    assert d["chi"] is None
    assert d["frase"] == (
        "HIRIS non può rispondere: il ponte è acceso e manca il token del "
        "Piano Claude Max."
    )
    guasti = [x for x in d["diagnosi"] if x["gravita"] == "guasto"]
    assert len(guasti) == 1
    assert guasti[0]["testo"] == (
        "Il ponte è acceso ma manca il token: ogni messaggio viene accodato e "
        "scade dopo 5 minuti senza risposta."
    )


def test_la_scadenza_dichiarata_e_quella_configurata_non_un_cinque_scritto_a_mano():
    d = componi_adesso(
        catena=[], credenziali={"subscription": False}, modelli={},
        ponte_attivo=True, scadenza_ponte_min=20,
    )
    assert "dopo 20 minuti" in d["diagnosi"][0]["testo"]


def test_col_token_presente_il_ponte_torna_a_essere_uno_che_risponde():
    """La prova gemella: la diagnosi non è un avviso che si dà sempre."""
    d = componi_adesso(
        catena=["claude"],
        credenziali={"claude": True, "subscription": True},
        modelli={"subscription": "opus"},
        ponte_attivo=True,
    )
    assert d["chi"] == "subscription"
    assert not [x for x in d["diagnosi"]
                if "manca il token" in x["testo"]]


# ── Il debito del Task 1, chiuso qui ──────────────────────────────────────
# Il ternario `"guasto" if not catena else "spreco"` del ramo del ponte era
# l'unico comportamento di questo file che nessun test toccava: il Task 1 lo
# dichiarò sopravvissuto alla prova per mutazione (costante `"spreco"`: 29
# test verdi). È la differenza fra «hai una cosa rotta» e «hai una cosa che
# paghi e non usi», e sotto sta due colori diversi a schermo
# (`--err-ink` / `--warn-ink`): le due prove qui sotto sono gemelle, e una
# costante al posto del ternario ne fa cadere sempre una.

def test_col_ponte_acceso_e_una_catena_sotto_lo_scavalco_e_uno_spreco():
    d = componi_adesso(
        catena=["claude", "openrouter"],
        credenziali={"claude": True, "openrouter": True, "subscription": True},
        modelli={"subscription": "opus"},
        ponte_attivo=True,
    )
    assert len(d["diagnosi"]) == 1
    assert d["diagnosi"][0]["gravita"] == "spreco"


def test_col_ponte_acceso_e_niente_sotto_non_c_e_nessuna_rete_ed_e_un_guasto():
    """Il piano risponde (il token c'è), ma sotto non c'è NIENTE: il giorno in
    cui il ponte non risponde, non risponde nessuno. Lo stesso testo, un
    colore diverso, perché il fatto misurato è diverso."""
    d = componi_adesso(
        catena=[],
        credenziali={"subscription": True},
        modelli={"subscription": "opus"},
        ponte_attivo=True,
    )
    assert d["chi"] == "subscription"
    assert len(d["diagnosi"]) == 1
    assert d["diagnosi"][0]["gravita"] == "guasto"


# ---------------------------------------------------------------------------
# `componi_topologia`: chi e' in catena, in che ordine, e chi ne sta fuori.
# La pagina riceve DUE liste gia' ordinate e non ne calcola nessuna: e'
# l'invariante 2 della spec, applicato alla forma della catena come il
# riquadro «Adesso» lo applica alla frase.
# ---------------------------------------------------------------------------

from hiris.app.decisione_modelli import componi_topologia  # noqa: E402

CRED = {"claude": True, "openrouter": True, "openai": False,
        "ollama": False, "subscription": True}
MOD = {"claude": "claude-opus-4-7", "openrouter": "anthropic/claude-sonnet-4-6",
       "openai": "gpt-4o", "ollama": "", "subscription": "opus"}


def test_la_catena_porta_posizione_nome_modello_e_natura():
    catena, _ = componi_topologia(chain_order=["claude", "openrouter"],
                                  credenziali=CRED, modelli=MOD, ponte_attivo=False)
    assert [r["id"] for r in catena] == ["claude", "openrouter"]
    assert [r["posizione"] for r in catena] == [1, 2]
    assert catena[0] == {"id": "claude", "nome": "Claude API",
                         "modello": "claude-opus-4-7", "natura": "a consumo",
                         "ha_credenziale": True, "posizione": 1,
                         "riordinabile": True}


def test_fuori_catena_ci_sta_tutto_il_resto_in_ordine_fisso():
    _, fuori = componi_topologia(chain_order=["claude"], credenziali=CRED,
                                 modelli=MOD, ponte_attivo=False)
    assert [r["id"] for r in fuori] == ["subscription", "openrouter", "openai", "ollama"]
    assert all(r["posizione"] is None for r in fuori)
    assert [r["ha_credenziale"] for r in fuori] == [True, True, False, False]


def test_col_ponte_acceso_il_piano_e_il_primo_della_catena_e_non_e_piu_fuori():
    catena, fuori = componi_topologia(chain_order=["claude", "openrouter"],
                                      credenziali=CRED, modelli=MOD, ponte_attivo=True)
    assert catena[0]["id"] == "subscription"
    assert catena[0]["posizione"] == 1
    assert [r["posizione"] for r in catena] == [1, 2, 3]
    assert "subscription" not in [r["id"] for r in fuori]


def test_il_piano_non_e_riordinabile_e_gli_altri_quattro_si():
    """Il piano può stare in testa o fuori, e basta. Non è una scelta grafica:
    metterlo secondo richiederebbe che la forma della risposta HTTP cambi a
    seconda di dove la catena si rompe. Il campo viaggia nel payload perché la
    pagina non offra un riordino che il backend rifiuterebbe -- che è
    esattamente il difetto che questa fetta esiste per chiudere."""
    catena, fuori = componi_topologia(chain_order=["claude", "openrouter"],
                                      credenziali=CRED, modelli=MOD, ponte_attivo=True)
    per_id = {r["id"]: r for r in catena + fuori}
    assert per_id["subscription"]["riordinabile"] is False
    for pid in ("claude", "openrouter", "openai", "ollama"):
        assert per_id[pid]["riordinabile"] is True, pid


def test_un_subscription_finito_in_chain_order_non_conta():
    """`chain_order` porta solo i quattro backend del router. La presenza del
    piano in testa discende da `ponte.attivo`, non dall'appartenenza: se
    qualcuno scrivesse `subscription` nella catena, non deve succedere niente."""
    catena, fuori = componi_topologia(chain_order=["subscription", "claude"],
                                      credenziali=CRED, modelli=MOD, ponte_attivo=False)
    assert [r["id"] for r in catena] == ["claude"]
    assert "subscription" in [r["id"] for r in fuori]


def test_un_subscription_in_chain_order_non_si_sdoppia_col_ponte_acceso():
    """Il caso gemello del precedente, ed e' quello che morde: col ponte acceso
    il piano viene messo in testa, e se `chain_order` lo portasse ANCORA
    comparirebbe due volte in catena -- due righe per lo stesso provider, cioe'
    la seconda rappresentazione dello stato, in miniatura e a schermo."""
    catena, fuori = componi_topologia(chain_order=["subscription", "claude"],
                                      credenziali=CRED, modelli=MOD, ponte_attivo=True)
    assert [r["id"] for r in catena] == ["subscription", "claude"]
    assert [r["posizione"] for r in catena] == [1, 2]
    assert "subscription" not in [r["id"] for r in fuori]


def test_un_provider_in_chain_order_senza_credenziale_finisce_fuori_non_in_catena():
    """È la stessa regola di `provider_in_catena`, vista dal lato della pagina:
    non esiste una riga «in catena ma non può» -- sarebbe la seconda
    rappresentazione dello stato che questa fetta toglie."""
    catena, fuori = componi_topologia(chain_order=["ollama", "claude"],
                                      credenziali=CRED, modelli=MOD, ponte_attivo=False)
    assert [r["id"] for r in catena] == ["claude"]
    assert "ollama" in [r["id"] for r in fuori]


def test_una_catena_vuota_lascia_tutti_e_cinque_fuori():
    catena, fuori = componi_topologia(chain_order=[], credenziali=CRED,
                                      modelli=MOD, ponte_attivo=False)
    assert catena == []
    assert [r["id"] for r in fuori] == list(ORDINE_FISSO)


def test_nessuna_riga_porta_la_parola_vietata():
    """Invariante 3: «Attivo» significa «interruttore acceso e credenziale
    presente» e si legge «funziona». Non deve rientrare da nessuna porta --
    nemmeno da un campo del payload."""
    catena, fuori = componi_topologia(chain_order=["claude"], credenziali=CRED,
                                      modelli=MOD, ponte_attivo=True)
    for r in catena + fuori:
        assert "attivo" not in " ".join(str(v) for v in r.values()).lower()
        assert "active" not in set(r.keys())
