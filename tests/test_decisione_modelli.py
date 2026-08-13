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

from hiris.app.decisione_modelli import (componi_pannello,  # noqa: E402
                                         componi_topologia, e_alias,
                                         provenienza)

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
                         "modello": "claude-opus-4-7", "modello_alias": False,
                         "natura": "a consumo",
                         "manca": "", "nota": "",
                         "connettore": "se rifiuta, subito",
                         "connettore_nota": "",
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


def test_il_connettore_del_ponte_non_promette_un_ripiego_che_non_esiste():
    """La prova che vale piu' di tutte in questa funzione. Oggi il ponte non e'
    un anello: e' un bivio a monte del router, e alla scadenza il messaggio va
    perso -- non passa alla riga sotto. Un connettore che dicesse «se non
    risponde, si passa al successivo» sarebbe il difetto 3 ricomparso come
    didascalia: la pagina prometterebbe un ripiego che il prodotto non fa.
    Il giorno del ripiego (Task 14) cambia QUESTA stringa, e la pagina dice la
    cosa nuova senza essere toccata."""
    catena, _ = componi_topologia(chain_order=["claude"], credenziali=CRED,
                                  modelli=MOD, ponte_attivo=True,
                                  scadenza_ponte_min=5)
    piano = catena[0]
    assert piano["id"] == "subscription"
    assert piano["connettore"] == (
        "il ponte non ripiega: se non risponde entro 5 min il messaggio va perso")


def test_il_connettore_mostra_un_numero_solo_quando_quel_numero_e_una_decisione():
    """Progetto §5.1. Il tempo del ponte e il timeout di Ollama li ha scelti
    qualcuno; un rifiuto immediato non e' un numero e si dice a parole. Un tempo
    che nessuno ha scelto (i tre tentativi su un 429 di Claude, 5+15+45 secondi)
    non si inventa qui: lo raccontera' la riga di stato dopo che e' successo."""
    cred = dict(CRED, ollama=True)
    catena, _ = componi_topologia(chain_order=["claude", "ollama"],
                                  credenziali=cred, modelli=MOD,
                                  ponte_attivo=False, timeout_ollama_s=300)
    per_id = {r["id"]: r for r in catena}
    assert per_id["ollama"]["connettore"] == "se non risponde entro 300 s"
    assert per_id["claude"]["connettore"] == "se rifiuta, subito"


def test_sopra_i_cinque_minuti_il_connettore_dichiara_il_tetto_che_lo_schema_non_ha():
    """`scadenza_min` accetta 1..120, ma la chat smette di interrogare a
    CHAT_POLL_MAX_MS (5 minuti), una costante indipendente e non collegata:
    sopra i cinque il browser dichiara scaduta un'attesa che sul server e'
    ancora viva. Questa fetta DICHIARA e non risolve -- e' un fatto, non un
    divieto -- e lo dichiara accanto al numero, composto con lo stesso valore:
    due letture non potrebbero divergere."""
    sopra, _ = componi_topologia(chain_order=["claude"], credenziali=CRED,
                                 modelli=MOD, ponte_attivo=True,
                                 scadenza_ponte_min=7)
    assert "sopra i 5 minuti" in sopra[0]["connettore_nota"]
    assert "7 min" in sopra[0]["connettore"]

    sotto, _ = componi_topologia(chain_order=["claude"], credenziali=CRED,
                                 modelli=MOD, ponte_attivo=True,
                                 scadenza_ponte_min=5)
    assert sotto[0]["connettore_nota"] == "", (
        "sotto il tetto non succede niente: dirlo sempre sarebbe un avviso per "
        "uno stato che non c'e'"
    )


def test_chi_sta_fuori_dalla_catena_non_ha_un_dopo():
    _, fuori = componi_topologia(chain_order=["claude"], credenziali=CRED,
                                 modelli=MOD, ponte_attivo=False)
    for r in fuori:
        assert r["connettore"] == "", r["id"]
        assert r["connettore_nota"] == "", r["id"]


def test_quando_manca_la_credenziale_il_payload_dice_QUALE():
    """Sono tre credenziali diverse -- un token, una chiave, un indirizzo -- e
    la parola che le distingue e' un'affermazione sul prodotto: sta dove stanno
    le altre (i nomi del Task 5, le frasi di `componi_adesso`), non nella
    pagina. Scritta nella pagina sarebbe una seconda descrizione della regola
    di credenziale, in un altro linguaggio, libera di divergere da
    `_config_has_credential` senza che nessun test se ne accorga."""
    senza = {"claude": False, "openrouter": False, "openai": False,
             "ollama": False, "subscription": False}
    _, fuori = componi_topologia(chain_order=[], credenziali=senza, modelli=MOD,
                                 ponte_attivo=False)
    per_id = {r["id"]: r for r in fuori}
    assert per_id["subscription"]["manca"] == "manca il token"
    assert per_id["claude"]["manca"] == "manca la chiave"
    assert per_id["openrouter"]["manca"] == "manca la chiave"
    assert per_id["openai"]["manca"] == "manca la chiave"
    assert per_id["ollama"]["manca"] == "manca l'indirizzo"


def test_chi_ha_la_credenziale_non_dice_che_ne_manca_una():
    """`manca` e' vuoto quando non manca niente: la pagina disegna solo cio'
    che non e' vuoto, e non ha nessuna condizione da valutare."""
    catena, fuori = componi_topologia(chain_order=["claude", "openrouter"],
                                      credenziali=CRED, modelli=MOD,
                                      ponte_attivo=False)
    per_id = {r["id"]: r for r in catena + fuori}
    assert per_id["claude"]["manca"] == ""
    assert per_id["openrouter"]["manca"] == ""
    assert per_id["subscription"]["manca"] == ""   # ha il token, e' solo fuori


def test_il_piano_dice_perche_non_si_sposta_e_perche_non_si_mette_in_catena():
    """Una riga che non offre i gesti che offrono le altre deve dire perche':
    l'assenza di un gesto, senza una parola, si legge come un guasto. E la
    parola sta qui perche' la ragione e' una regola del prodotto -- il piano
    non e' un membro di `chain_order`, la sua presenza discende dal ponte -- e
    il giorno in cui la regola cambia (Task 13 e 14) cambia questa stringa, in
    un posto solo, senza che la pagina venga toccata."""
    dentro, _ = componi_topologia(chain_order=["claude"], credenziali=CRED,
                                  modelli=MOD, ponte_attivo=True)
    assert dentro[0]["id"] == "subscription"
    assert "In testa o fuori" in dentro[0]["nota"]

    _, fuori = componi_topologia(chain_order=["claude"], credenziali=CRED,
                                 modelli=MOD, ponte_attivo=False)
    piano = {r["id"]: r for r in fuori}["subscription"]
    assert "ponte" in piano["nota"], (
        "col token in mano e fuori dalla catena, la riga deve dire COME ci "
        "entra: e' il caso del proprietario, che paga e non usa"
    )


def test_gli_altri_quattro_non_portano_nessuna_nota():
    """La nota e' l'eccezione, non l'arredamento: quattro righe su cinque
    offrono tutti i gesti e non hanno niente da spiegare. Se la nota comparisse
    su tutte, la riga che conta non si distinguerebbe piu'."""
    catena, fuori = componi_topologia(chain_order=["claude", "openrouter"],
                                      credenziali=CRED, modelli=MOD,
                                      ponte_attivo=True)
    per_id = {r["id"]: r for r in catena + fuori}
    for pid in ("claude", "openrouter", "openai", "ollama"):
        assert per_id[pid]["nota"] == "", pid


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


# ---------------------------------------------------------------------------
# Il pannello del modello (progetto §6). Le parole stanno qui perche' sono
# affermazioni sul prodotto -- e due di loro sono destinate a cambiare: la
# provenienza dipende da un fatto misurato adesso, e `quando` tacera' con la
# scrittura a caldo (Task 10). Scritte nel frontend resterebbero a dire quella
# di ieri, e a schermo la frase ci sarebbe lo stesso.
# ---------------------------------------------------------------------------


def test_una_lettura_riuscita_nomina_chi_ha_risposto():
    assert provenienza("openrouter", "viva") == "Letti da openrouter.ai adesso."
    assert provenienza("openai", "viva") == "Letti da api.openai.com adesso."


def test_una_lettura_fallita_nomina_chi_NON_ha_risposto_e_dice_il_dubbio():
    riga = provenienza("openrouter", "riserva")
    assert "Elenco di riserva" in riga
    assert "openrouter.ai" in riga
    assert "potrebbe non esistere più" in riga


def test_ollama_dice_su_QUALE_macchina_sono_scaricati():
    """«in casa» e' una natura, e diventa concreta solo col nome della casa."""
    assert provenienza("ollama", "viva", indirizzo="http://192.168.1.42:11434") == (
        "Scaricati su http://192.168.1.42:11434 — letti adesso.")
    riga = provenienza("ollama", "riserva", indirizzo="http://192.168.1.42:11434")
    assert "192.168.1.42" in riga
    assert "chiave rifiutata" not in riga, "Ollama non ha una chiave da rifiutare"


def test_claude_dichiara_la_riserva_con_parole_proprie_e_mai_viva():
    """Anthropic non espone un endpoint pubblico di elenco: questa lista e'
    scritta a mano e invecchia come tutte le liste scritte a mano."""
    riga = provenienza("claude", "riserva")
    assert "Anthropic non pubblica un elenco" in riga
    assert "potrebbe non esistere più" in riga


def test_il_difetto_gemello_si_LEGGE_invece_di_essere_taciuto():
    """Sul ramo di riserva i preset tornano NON filtrati: i gratuiti
    ricompaiono anche con la casella spuntata. Non si corregge (filtrarli
    renderebbe la riserva una lista diversa da quella del sorgente, cioe' una
    terza cosa): si dichiara, dove l'utente sta guardando."""
    muta = provenienza("openrouter", "riserva", avviso_gratuiti=False)
    parlante = provenienza("openrouter", "riserva", avviso_gratuiti=True)
    assert "nascondi i gratuiti" not in muta
    assert "nascondi i gratuiti" in parlante
    assert "non ha effetto" in parlante


def test_il_pannello_di_openrouter_lo_dice_solo_quando_la_casella_e_spuntata():
    """La composizione intera, non la funzione isolata: e' li' che il fatto e
    la parola si incontrano."""
    acceso = componi_pannello(provider_id="openrouter", valori=[], fonte="riserva",
                              scelto="", nascondi_gratuiti=True)
    spento = componi_pannello(provider_id="openrouter", valori=[], fonte="riserva",
                              scelto="", nascondi_gratuiti=False)
    viva = componi_pannello(provider_id="openrouter", valori=[], fonte="viva",
                            scelto="", nascondi_gratuiti=True)
    assert "non ha effetto" in acceso["provenienza"]
    assert "non ha effetto" not in spento["provenienza"]
    assert "non ha effetto" not in viva["provenienza"], (
        "sulla lista VIVA la casella funziona: dirlo sarebbe falso"
    )


def test_i_gratuiti_si_riconoscono_nella_voce_e_non_nella_pagina():
    p = componi_pannello(
        provider_id="openrouter", fonte="viva", scelto="",
        valori=["openrouter:openai/gpt-4.1",
                "openrouter:google/gemma-3-27b-it:free"])
    assert [v["nota"] for v in p["modelli"]] == ["", "gratuito"]


def test_la_voce_auto_c_e_solo_dove_auto_esiste():
    """Ollama usa SEMPRE il modello scelto (`fixed_model` vince su ogni altro
    ramo di `_resolve_model`): una voce «scelto da HIRIS» li' prometterebbe una
    scelta che il runner non fa."""
    con = componi_pannello(provider_id="claude", valori=["claude-opus-4-7"],
                           fonte="riserva", scelto="",
                           auto_risolto="claude-sonnet-4-6")
    assert con["modelli"][0] == {"valore": "",
                                 "nota": "scelto da HIRIS: oggi claude-sonnet-4-6"}
    senza = componi_pannello(provider_id="ollama", valori=["llama3.1:8b"],
                             fonte="viva", scelto="llama3.1:8b")
    assert [v["valore"] for v in senza["modelli"]] == ["llama3.1:8b"]


def test_dove_si_scrive_e_un_percorso_e_il_piano_non_ne_ha_uno():
    assert componi_pannello(provider_id="ollama", valori=[], fonte="viva",
                            scelto="")["dove"] == ["ollama", "modello"]
    assert componi_pannello(provider_id="openai", valori=[], fonte="viva",
                            scelto="")["dove"] == ["provider_models", "openai"]
    assert componi_pannello(provider_id="subscription", valori=[], fonte="fissa",
                            scelto="opus")["dove"] == [], (
        "il modello del piano e' un effetto di quello di Claude API: un "
        "pannello che offrisse di scriverlo manderebbe una PUT che nessuno legge"
    )


def test_il_piano_e_l_unico_che_sceglie_un_ALIAS():
    assert e_alias("subscription") is True
    for pid in ("claude", "openai", "openrouter", "ollama"):
        assert e_alias(pid) is False, pid


def test_su_ollama_senza_modello_la_riga_dice_cosa_manca_e_non_offre_il_gesto():
    """Il buco dichiarato dal Task 7. La credenziale c'e' (l'indirizzo), il
    pallino resta acceso, e a mancare e' il modello: entrare in catena
    produrrebbe un anello che il router salta in silenzio."""
    cred = {**CRED, "ollama": True}
    _, fuori = componi_topologia(chain_order=["claude"], credenziali=cred,
                                 modelli={**MOD, "ollama": ""}, ponte_attivo=False)
    riga = {r["id"]: r for r in fuori}["ollama"]
    assert riga["ha_credenziale"] is True
    assert riga["manca"] == ""
    assert riga["riordinabile"] is False
    assert "il modello no" in riga["nota"]

    _, fuori = componi_topologia(chain_order=["claude"], credenziali=cred,
                                 modelli={**MOD, "ollama": "llama3.1:8b"},
                                 ponte_attivo=False)
    riga = {r["id"]: r for r in fuori}["ollama"]
    assert riga["riordinabile"] is True
    assert riga["nota"] == ""


def test_senza_indirizzo_la_riga_dice_QUELLO_e_non_il_modello():
    """Un impedimento alla volta, e il piu' esterno per primo: «manca il
    modello» sopra un Ollama che non ha nemmeno un indirizzo manderebbe a
    risolvere la cosa sbagliata."""
    _, fuori = componi_topologia(chain_order=[], credenziali=CRED,
                                 modelli={**MOD, "ollama": ""}, ponte_attivo=False)
    riga = {r["id"]: r for r in fuori}["ollama"]
    assert riga["manca"] == "manca l'indirizzo"
    assert riga["nota"] == ""
    assert riga["riordinabile"] is True
