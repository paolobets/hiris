"""La decisione già presa: chi risponde al prossimo messaggio, e perché.

Ogni test qui è una frase che la pagina dirà all'utente. Se una di queste
cade, la pagina ha ricominciato a essere vera riga per riga e falsa nel
complesso.
"""
import pytest

from hiris.app.decisione_modelli import FIXED_ORDER, compose_now, display_name, nature


def test_il_primo_della_catena_e_quello_che_risponde():
    d = compose_now(
        chain=["claude", "openrouter"],
        credentials={"claude": True, "openrouter": True, "subscription": False},
        models={"claude": "claude-opus-4-7", "openrouter": "anthropic/claude-sonnet-4-6"},
        bridge_active=False,
    )
    assert d["chi"] == "claude"
    assert d["via"] == "catena"
    assert d["frase"] == "Il prossimo messaggio va a Claude API, con claude-opus-4-7, a consumo."


def test_col_ponte_acceso_il_piano_prova_per_primo_e_la_catena_lo_segue():
    """Il ponte è un ANELLO dal Task 14: prova per primo, e se non risponde il
    turno passa al successivo. Il test si chiamava «e la catena non viene
    consultata», ed era vero -- il ponte era un bivio a monte del router. Un
    test che tiene il nome di ieri quando il comportamento è cambiato è una
    dichiarazione falsa nel posto peggiore."""
    d = compose_now(
        chain=["claude", "openrouter"],
        credentials={"claude": True, "openrouter": True, "subscription": True},
        models={"claude": "claude-opus-4-7", "subscription": "opus"},
        bridge_active=True,
        bridge_deadline_min=5,
    )
    assert d["chi"] == "subscription"
    assert d["via"] == "ponte"
    assert d["frase"] == "Il prossimo messaggio va a Piano Claude Max, con opus, nel piano."
    testi = [x["testo"] for x in d["diagnosi"]]
    assert testi == [
        ("Il ponte è acceso: il Piano Claude Max prova per primo, e se non "
        "risponde entro 5 minuti il turno passa al successivo della catena.")
    ], testi
    assert not any("non viene consultata" in t for t in testi), testi


def test_il_piano_pagato_e_fuori_dalla_catena_e_uno_spreco_dichiarato():
    """Il caso del proprietario: token presente, piano pagato, ponte spento.
    È la riga che costa di più, ed è quella che porta l'azione consigliata."""
    d = compose_now(
        chain=["claude", "openrouter"],
        credentials={"claude": True, "openrouter": True, "subscription": True},
        models={"claude": "claude-opus-4-7", "openrouter": "anthropic/claude-sonnet-4-6"},
        bridge_active=False,
    )
    spreco = [x for x in d["diagnosi"] if x["gravita"] == "spreco"]
    assert len(spreco) == 1
    assert spreco[0]["testo"] == (
        "Il Piano Claude Max ha il token, lo paghi, ed è fuori dalla catena."
    )


def test_lo_spreco_del_piano_porta_il_gesto_che_lo_ripara():
    """**Il bottone che il Task 14 non poteva costruire.**

    Il Task 14 lascio' `azione` a `None` su tutte le diagnosi, e aveva ragione:
    `ponte.attivo` veniva da `BRIDGE_ENABLED`, cioe' dall'ambiente, e una PUT su
    un valore letto dall'ambiente torna 200 e viene buttata via al riavvio --
    un bottone che sembra funzionare e non funziona, la trappola che questa
    fetta aveva gia' evitato due volte. Con la versione B `ponte.attivo` vive
    nell'archivio e la meta' che mancava e' arrivata.

    Il gesto e' un'ETICHETTA + un PERCORSO + un VALORE, non un tipo di comando:
    la pagina applica un valore a una posizione dell'archivio e rilegge, senza
    sapere che cosa sta accendendo. E' la stessa disciplina di `dove` nel
    pannello del modello (Task 9), ed e' cio' che tiene la topologia fuori dal
    frontend (invariante 2)."""
    d = compose_now(
        chain=["claude"],
        credentials={"claude": True, "subscription": True},
        models={"claude": "claude-opus-4-7"},
        bridge_active=False,
    )
    spreco = next(x for x in d["diagnosi"] if x["gravita"] == "spreco")
    assert spreco["azione"] == {
        "etichetta": "Mettilo primo",
        "dove": ["ponte", "attivo"],
        "valore": True,
    }


def test_col_ponte_acceso_il_gesto_e_quello_INVERSO():
    """L'altra direzione, e non e' simmetria di cortesia: togliendo
    `ponte.attivo` dalle opzioni dell'add-on si e' tolto l'UNICO modo che
    c'era di spegnere il ponte. Un interruttore che si accende e non si spegne
    e' peggio di nessun interruttore.

    Sta su una riga che non denuncia niente (`fatto`): il ponte acceso con dei
    provider sotto e' uno stato sano, e il gesto va dove sta il fatto che si
    vuole cambiare, non dove c'e' un guasto."""
    d = compose_now(
        chain=["claude"],
        credentials={"claude": True, "subscription": True},
        models={"claude": "claude-opus-4-7"},
        bridge_active=True,
    )
    fatto = next(x for x in d["diagnosi"] if x["gravita"] == "fatto")
    assert fatto["azione"] == {
        "etichetta": "Togli il piano dalla catena",
        "dove": ["ponte", "attivo"],
        "valore": False,
    }


def test_col_ponte_acceso_e_nessuno_sotto_non_si_offre_nessun_gesto():
    """Il terzo caso, che NON e' il secondo con un'altra parola: col ponte
    acceso e la catena vuota, spegnere il ponte lascerebbe HIRIS senza nessuno
    a cui chiedere. Offrire li' il gesto sarebbe consigliare di peggiorare, e
    un'azione che compare sempre e' un'azione che non significa niente."""
    d = compose_now(
        chain=[],
        credentials={"subscription": True},
        models={},
        bridge_active=True,
    )
    assert [x["azione"] for x in d["diagnosi"]] == [None]


def test_senza_token_del_piano_non_si_dichiara_nessuno_spreco():
    """La prova gemella della precedente: la diagnosi è un'affermazione su una
    cosa MISURATA (il token c'è), non un consiglio che si dà sempre."""
    d = compose_now(
        chain=["claude"],
        credentials={"claude": True, "subscription": False},
        models={"claude": "claude-opus-4-7"},
        bridge_active=False,
    )
    assert [x for x in d["diagnosi"] if x["gravita"] == "spreco"] == []


def test_catena_vuota_e_ponte_spento_lo_dice_invece_di_tacere():
    d = compose_now(chain=[], credentials={}, models={}, bridge_active=False)
    assert d["chi"] is None
    assert d["nome"] == "" and d["natura"] == "" and d["via"] == ""
    assert d["frase"] == "HIRIS non può ancora rispondere: la catena è vuota."
    assert [x["gravita"] for x in d["diagnosi"]] == ["guasto"]


def test_un_provider_senza_modello_noto_non_inventa_un_modello():
    d = compose_now(
        chain=["ollama"], credentials={"ollama": True}, models={"ollama": ""},
        bridge_active=False,
    )
    assert d["modello"] == ""
    assert d["frase"] == "Il prossimo messaggio va a Ollama (in casa), in casa."


def test_le_sette_chiavi_ci_sono_sempre():
    """Il frontend disegna quello che riceve: una chiave assente sarebbe un
    `undefined` a schermo."""
    for d in (
        compose_now(chain=[], credentials={}, models={}, bridge_active=False),
        compose_now(chain=["claude"], credentials={"claude": True},
                       models={"claude": "x"}, bridge_active=False),
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
    assert display_name(pid) == atteso


@pytest.mark.parametrize("pid,atteso", [
    ("subscription", "nel piano"), ("claude", "a consumo"),
    ("openrouter", "a consumo"), ("openai", "a consumo"), ("ollama", "in casa"),
])
def test_le_quattro_nature_e_non_un_prezzo(pid, atteso):
    """HIRIS non ha una fonte di prezzi e un prezzo vecchio è peggio di nessun
    prezzo. Le nature bastano per ordinare una catena (progetto §12.1)."""
    assert nature(pid) == atteso


def test_ponte_acceso_senza_token_risponde_la_catena_e_il_costo_si_dichiara():
    """Lo stato che passava in silenzio -- ponte acceso, worker che non parte
    (gli manca il token), ogni messaggio accodato e scaduto -- ha smesso di
    essere una perdita: dal Task 14 il turno scende alla catena nella stessa
    richiesta. Chi risponde è quindi il primo della catena, come col ponte
    spento.

    Ma resta un fatto che COSTA, e si dichiara: il piano non riceve niente e
    ogni turno si paga a consumo. È la stessa ragione per cui la chat annuncia
    ogni ripiego -- un passaggio silenzioso dal forfait al consumo si scopre a
    fine mese."""
    d = compose_now(
        chain=["claude"],
        credentials={"claude": True, "subscription": False},
        models={"claude": "claude-opus-4-7", "subscription": "sonnet"},
        bridge_active=True,
        bridge_deadline_min=5,
    )
    assert d["chi"] == "claude"
    assert d["via"] == "catena"
    assert d["frase"] == (
        "Il prossimo messaggio va a Claude API, con claude-opus-4-7, a consumo.")
    sprechi = [x for x in d["diagnosi"] if x["gravita"] == "spreco"]
    assert len(sprechi) == 1
    assert sprechi[0]["testo"] == (
        "Il ponte è acceso ma manca il token: nessun messaggio arriva al Piano "
        "Claude Max, e ogni turno passa alla catena — dal forfait al consumo."
    )


def test_ponte_acceso_senza_token_e_senza_catena_non_puo_rispondere_nessuno():
    """La prova gemella della precedente: senza il token il turno passa alla
    catena, ma se sotto non c'è nessuno non c'è nessun ripiego da fare."""
    d = compose_now(
        chain=[], credentials={"subscription": False}, models={},
        bridge_active=True, bridge_deadline_min=5,
    )
    assert d["chi"] is None
    assert d["frase"] == (
        "HIRIS non può rispondere: il ponte è acceso, manca il token del Piano "
        "Claude Max, e sotto di lui non c'è nessuno."
    )
    guasti = [x for x in d["diagnosi"] if x["gravita"] == "guasto"]
    assert len(guasti) == 1
    assert guasti[0]["testo"] == (
        "Il ponte è acceso ma manca il token: nessun messaggio arriva al Piano "
        "Claude Max, e in catena non c'è nessun altro a cui passarlo."
    )


def test_la_scadenza_dichiarata_e_quella_configurata_non_un_cinque_scritto_a_mano():
    """Il numero è quello che il turno subisce (`ponte.scadenza_min`, letto da
    `_enqueue_chat_job` a ogni accodamento), non un default scritto qui."""
    d = compose_now(
        chain=["claude"], credentials={"claude": True, "subscription": True},
        models={"subscription": "opus"},
        bridge_active=True, bridge_deadline_min=20,
    )
    assert "entro 20 minuti" in d["diagnosi"][0]["testo"]

    vuota = compose_now(
        chain=[], credentials={"subscription": True},
        models={"subscription": "opus"},
        bridge_active=True, bridge_deadline_min=20,
    )
    assert "entro 20 minuti" in vuota["diagnosi"][0]["testo"]


def test_col_token_presente_il_ponte_torna_a_essere_uno_che_risponde():
    """La prova gemella: la diagnosi non è un avviso che si dà sempre."""
    d = compose_now(
        chain=["claude"],
        credentials={"claude": True, "subscription": True},
        models={"subscription": "opus"},
        bridge_active=True,
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

def test_col_ponte_acceso_e_una_catena_sotto_non_c_e_nessuno_spreco_da_dichiarare():
    """La riga diceva «spreco»: li hai configurati e non li usa nessuno. Col
    ripiego non è più vero -- quei provider servono, il giorno in cui il piano
    non risponde -- e chiamarli spreco sarebbe una parola più larga del fatto,
    per giunta contro l'utente, che ha costruito la rete giusta. Resta un
    FATTO da dire (quanto si aspetta prima che la rete entri in funzione), e si
    dice in tondo."""
    d = compose_now(
        chain=["claude", "openrouter"],
        credentials={"claude": True, "openrouter": True, "subscription": True},
        models={"subscription": "opus"},
        bridge_active=True,
    )
    assert len(d["diagnosi"]) == 1
    assert d["diagnosi"][0]["gravita"] == "fatto"
    assert not [x for x in d["diagnosi"] if x["gravita"] in ("spreco", "guasto")]


def test_col_ponte_acceso_e_niente_sotto_non_c_e_nessuna_rete_ed_e_un_guasto():
    """Il piano risponde (il token c'è), ma sotto non c'è NIENTE: il giorno in
    cui il ponte non risponde, non risponde nessuno. La prova gemella della
    precedente -- una gravità costante ne fa cadere sempre una -- e la frase
    non promette un successivo che non esiste."""
    d = compose_now(
        chain=[],
        credentials={"subscription": True},
        models={"subscription": "opus"},
        bridge_active=True,
    )
    assert d["chi"] == "subscription"
    assert len(d["diagnosi"]) == 1
    assert d["diagnosi"][0]["gravita"] == "guasto"
    assert "passa al successivo" not in d["diagnosi"][0]["testo"]


# ---------------------------------------------------------------------------
# `compose_topology`: chi e' in catena, in che ordine, e chi ne sta fuori.
# La pagina riceve DUE liste gia' ordinate e non ne calcola nessuna: e'
# l'invariante 2 della spec, applicato alla forma della catena come il
# riquadro «Adesso» lo applica alla frase.
# ---------------------------------------------------------------------------

from hiris.app.decisione_modelli import (
    compose_panel,
    explanation,
    is_alias,
    provenance,
)
from hiris.app.decisione_modelli import compose_topology as _compose_topology


def compose_topology(**kw):
    """I due parametri del Task 11 (`occurrences`, `now`) sono OBBLIGATORI in
    produzione -- un valore di comodo lascerebbe passare in silenzio un
    chiamante che non li passa, e la pagina non direbbe mai niente sugli esiti.

    Qui hanno un valore di comodo perche' i test di questo blocco parlano di
    TOPOLOGIA (chi e' dentro, in che ordine, chi sta fuori) e non di esiti: un
    registro vuoto e un orologio fermo sono la condizione di un add-on appena
    partito, che e' la meno interessante per loro e la piu' onesta. Gli esiti
    hanno i loro test, in `tests/test_esiti_provider.py` e piu' sotto in
    questo stesso file.
    """
    kw.setdefault("occurrences", {})
    kw.setdefault("now", 1000.0)
    return _compose_topology(**kw)

CRED = {"claude": True, "openrouter": True, "openai": False,
        "ollama": False, "subscription": True}
MOD = {"claude": "claude-opus-4-7", "openrouter": "anthropic/claude-sonnet-4-6",
       "openai": "gpt-4o", "ollama": "", "subscription": "opus"}


def test_la_catena_porta_posizione_nome_modello_e_natura():
    catena, _ = compose_topology(chain_order=["claude", "openrouter"],
                                  credentials=CRED, models=MOD, bridge_active=False)
    assert [r["id"] for r in catena] == ["claude", "openrouter"]
    assert [r["posizione"] for r in catena] == [1, 2]
    assert catena[0] == {"id": "claude", "nome": "Claude API",
                         "modello": "claude-opus-4-7", "modello_alias": False,
                         "natura": "a consumo",
                         "manca": "", "nota": "",
                         "connettore": "se rifiuta, subito",
                         "connettore_nota": "",
                         "ha_credenziale": True, "posizione": 1,
                         # Task 11: il fatto grezzo e la frase che lo racconta.
                         # Qui il registro e' vuoto (add-on appena partito) e
                         # Claude e' PRIMO: «non l'hai ancora usato», che in
                         # prima posizione e' allarmante.
                         "esito": None,
                         "stato_testo": "non l'hai ancora usato",
                         "riordinabile": True}


def test_fuori_catena_ci_sta_tutto_il_resto_in_ordine_fisso():
    _, fuori = compose_topology(chain_order=["claude"], credentials=CRED,
                                 models=MOD, bridge_active=False)
    assert [r["id"] for r in fuori] == ["subscription", "openrouter", "openai", "ollama"]
    assert all(r["posizione"] is None for r in fuori)
    assert [r["ha_credenziale"] for r in fuori] == [True, True, False, False]


def test_col_ponte_acceso_il_piano_e_il_primo_della_catena_e_non_e_piu_fuori():
    catena, fuori = compose_topology(chain_order=["claude", "openrouter"],
                                      credentials=CRED, models=MOD, bridge_active=True)
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
    catena, fuori = compose_topology(chain_order=["claude", "openrouter"],
                                      credentials=CRED, models=MOD, bridge_active=True)
    per_id = {r["id"]: r for r in catena + fuori}
    assert per_id["subscription"]["riordinabile"] is False
    for pid in ("claude", "openrouter", "openai", "ollama"):
        assert per_id[pid]["riordinabile"] is True, pid


def test_il_connettore_del_ponte_dichiara_il_ripiego_adesso_che_esiste():
    """La riga che ha dimostrato perche' le parole stanno nel backend.

    Fino al Task 14 questo test si chiamava «non promette un ripiego che non
    esiste» e pretendeva «il ponte non ripiega: se non risponde entro 5 min il
    messaggio va perso» -- che era vero, e per questo era giusto scriverlo. Il
    ripiego adesso c'e': e' cambiata QUESTA stringa, in Python, e la pagina
    disegna un anello senza che nessuno tocchi il frontend. Nessun test di
    `tests/js/` e' cambiato con lei, ed e' la prova che il progetto §11.1
    chiedeva."""
    catena, _ = compose_topology(chain_order=["claude"], credentials=CRED,
                                  models=MOD, bridge_active=True,
                                  bridge_deadline_min=5)
    piano = catena[0]
    assert piano["id"] == "subscription"
    assert piano["connettore"] == "se non risponde entro 5 min"
    assert "va perso" not in piano["connettore"]


def test_col_ripiego_il_piano_e_un_anello_e_la_catena_continua_sotto_di_lui():
    """Il piano in posizione 1, e la catena numerata sotto di lui: e' cosi' che
    si legge un ANELLO invece di un bivio. Il disegno non e' cambiato col
    Task 14 (era gia' una riga in posizione 1); e' cambiata la frase che sta
    fra lui e la riga sotto, e questo test tiene insieme le due cose -- una
    posizione senza il connettore giusto sarebbe di nuovo una pagina vera riga
    per riga e falsa nel complesso."""
    catena, fuori = compose_topology(chain_order=["claude", "openrouter"],
                                      credentials=CRED, models=MOD,
                                      bridge_active=True, bridge_deadline_min=5)
    assert [r["id"] for r in catena] == ["subscription", "claude", "openrouter"]
    assert [r["posizione"] for r in catena] == [1, 2, 3]
    assert catena[0]["connettore"] == "se non risponde entro 5 min"
    assert "subscription" not in [r["id"] for r in fuori]


def test_il_connettore_mostra_un_numero_solo_quando_quel_numero_e_una_decisione():
    """Progetto §5.1. Il tempo del ponte e il timeout di Ollama li ha scelti
    qualcuno; un rifiuto immediato non e' un numero e si dice a parole. Un tempo
    che nessuno ha scelto (i tre tentativi su un 429 di Claude, 5+15+45 secondi)
    non si inventa qui: lo raccontera' la riga di stato dopo che e' successo."""
    cred = dict(CRED, ollama=True)
    catena, _ = compose_topology(chain_order=["claude", "ollama"],
                                  credentials=cred, models=MOD,
                                  bridge_active=False, ollama_timeout_s=300)
    per_id = {r["id"]: r for r in catena}
    assert per_id["ollama"]["connettore"] == "se non risponde entro 300 s"
    assert per_id["claude"]["connettore"] == "se rifiuta, subito"


def test_sopra_i_cinque_minuti_il_connettore_dichiara_il_tetto_che_lo_schema_non_ha():
    """`scadenza_min` accetta 1..120, ma la chat smette di interrogare a
    CHAT_POLL_MAX_MS (5 minuti), una costante indipendente e non collegata:
    sopra i cinque il browser dichiara scaduta un'attesa che sul server e'
    ancora viva. Questa fetta DICHIARA e non risolve -- e' un fatto, non un
    divieto -- e lo dichiara accanto al numero, composto con lo stesso valore:
    due letture non potrebbero divergere.

    Il Task 14 lo ha reso PIU' caro, non meno: il ripiego vive nella rotta di
    poll, quindi sopra i cinque minuti non arriva nessun poll dopo la scadenza
    e il turno non passa al successivo affatto. La nota diceva «la risposta la
    trovi ricaricando» -- vero allora (il worker del ponte poteva ancora
    rispondere), falso adesso per il ripiego, che non avviene."""
    sopra, _ = compose_topology(chain_order=["claude"], credentials=CRED,
                                 models=MOD, bridge_active=True,
                                 bridge_deadline_min=7)
    assert sopra[0]["connettore_nota"] == (
        "sopra i 5 minuti la chat smette di aspettare prima della scadenza, e "
        "il turno non passa al successivo")
    assert "7 min" in sopra[0]["connettore"]

    sotto, _ = compose_topology(chain_order=["claude"], credentials=CRED,
                                 models=MOD, bridge_active=True,
                                 bridge_deadline_min=5)
    assert sotto[0]["connettore_nota"] == "", (
        "sotto il tetto non succede niente: dirlo sempre sarebbe un avviso per "
        "uno stato che non c'e'"
    )


def test_chi_sta_fuori_dalla_catena_non_ha_un_dopo():
    _, fuori = compose_topology(chain_order=["claude"], credentials=CRED,
                                 models=MOD, bridge_active=False)
    for r in fuori:
        assert r["connettore"] == "", r["id"]
        assert r["connettore_nota"] == "", r["id"]


def test_quando_manca_la_credenziale_il_payload_dice_QUALE():
    """Sono tre credenziali diverse -- un token, una chiave, un indirizzo -- e
    la parola che le distingue e' un'affermazione sul prodotto: sta dove stanno
    le altre (i nomi del Task 5, le frasi di `compose_now`), non nella
    pagina. Scritta nella pagina sarebbe una seconda descrizione della regola
    di credenziale, in un altro linguaggio, libera di divergere da
    `_config_has_credential` senza che nessun test se ne accorga."""
    senza = {"claude": False, "openrouter": False, "openai": False,
             "ollama": False, "subscription": False}
    _, fuori = compose_topology(chain_order=[], credentials=senza, models=MOD,
                                 bridge_active=False)
    per_id = {r["id"]: r for r in fuori}
    assert per_id["subscription"]["manca"] == "manca il token"
    assert per_id["claude"]["manca"] == "manca la chiave"
    assert per_id["openrouter"]["manca"] == "manca la chiave"
    assert per_id["openai"]["manca"] == "manca la chiave"
    assert per_id["ollama"]["manca"] == "manca l'indirizzo"


def test_chi_ha_la_credenziale_non_dice_che_ne_manca_una():
    """`manca` e' vuoto quando non manca niente: la pagina disegna solo cio'
    che non e' vuoto, e non ha nessuna condizione da valutare."""
    catena, fuori = compose_topology(chain_order=["claude", "openrouter"],
                                      credentials=CRED, models=MOD,
                                      bridge_active=False)
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
    dentro, _ = compose_topology(chain_order=["claude"], credentials=CRED,
                                  models=MOD, bridge_active=True)
    assert dentro[0]["id"] == "subscription"
    assert "In testa o fuori" in dentro[0]["nota"]

    _, fuori = compose_topology(chain_order=["claude"], credentials=CRED,
                                 models=MOD, bridge_active=False)
    piano = {r["id"]: r for r in fuori}["subscription"]
    assert "ponte" in piano["nota"], (
        "col token in mano e fuori dalla catena, la riga deve dire COME ci "
        "entra: e' il caso del proprietario, che paga e non usa"
    )


@pytest.mark.parametrize("ponte", [True, False])
def test_la_riga_del_piano_manda_DOVE_il_gesto_esiste_davvero(ponte):
    """Il giorno previsto e' arrivato, e la stringa e' cambiata col fatto.

    Fino alla 2.5.0 le due note del piano dicevano «il ponte si accende (o si
    spegne) in Configurazione add-on», ed era vero: `ponte.attivo` era
    un'opzione dell'add-on. Con la versione B non lo e' piu', e una nota che
    mandasse ancora li' manderebbe a cercare un campo che non esiste --
    esattamente il difetto del messaggio di primo avvio che il Task 15 ha
    chiuso, in un altro posto.

    Il commento sopra `nota()` prometteva che sarebbe cambiata «senza che la
    pagina venga toccata»: questo test e' la prova che la promessa e' stata
    mantenuta, e la rete che impedisce alla stringa vecchia di tornare."""
    catena, fuori = compose_topology(chain_order=["claude"], credentials=CRED,
                                      models=MOD, bridge_active=ponte)
    piano = {r["id"]: r for r in catena + fuori}["subscription"]
    assert "Configurazione add-on" not in piano["nota"], piano["nota"]
    assert "riquadro in cima" in piano["nota"], (
        "la nota non dice piu' dove sta il gesto: l'utente resta con una riga "
        "che spiega la regola e nessun modo di applicarla"
    )


def test_gli_altri_quattro_non_portano_nessuna_nota():
    """La nota e' l'eccezione, non l'arredamento: quattro righe su cinque
    offrono tutti i gesti e non hanno niente da spiegare. Se la nota comparisse
    su tutte, la riga che conta non si distinguerebbe piu'."""
    catena, fuori = compose_topology(chain_order=["claude", "openrouter"],
                                      credentials=CRED, models=MOD,
                                      bridge_active=True)
    per_id = {r["id"]: r for r in catena + fuori}
    for pid in ("claude", "openrouter", "openai", "ollama"):
        assert per_id[pid]["nota"] == "", pid


def test_un_subscription_finito_in_chain_order_non_conta():
    """`chain_order` porta solo i quattro backend del router. La presenza del
    piano in testa discende da `ponte.attivo`, non dall'appartenenza: se
    qualcuno scrivesse `subscription` nella catena, non deve succedere niente."""
    catena, fuori = compose_topology(chain_order=["subscription", "claude"],
                                      credentials=CRED, models=MOD, bridge_active=False)
    assert [r["id"] for r in catena] == ["claude"]
    assert "subscription" in [r["id"] for r in fuori]


def test_un_subscription_in_chain_order_non_si_sdoppia_col_ponte_acceso():
    """Il caso gemello del precedente, ed e' quello che morde: col ponte acceso
    il piano viene messo in testa, e se `chain_order` lo portasse ANCORA
    comparirebbe due volte in catena -- due righe per lo stesso provider, cioe'
    la seconda rappresentazione dello stato, in miniatura e a schermo."""
    catena, fuori = compose_topology(chain_order=["subscription", "claude"],
                                      credentials=CRED, models=MOD, bridge_active=True)
    assert [r["id"] for r in catena] == ["subscription", "claude"]
    assert [r["posizione"] for r in catena] == [1, 2]
    assert "subscription" not in [r["id"] for r in fuori]


def test_un_provider_in_chain_order_senza_credenziale_finisce_fuori_non_in_catena():
    """È la stessa regola di `providers_in_chain`, vista dal lato della pagina:
    non esiste una riga «in catena ma non può» -- sarebbe la seconda
    rappresentazione dello stato che questa fetta toglie."""
    catena, fuori = compose_topology(chain_order=["ollama", "claude"],
                                      credentials=CRED, models=MOD, bridge_active=False)
    assert [r["id"] for r in catena] == ["claude"]
    assert "ollama" in [r["id"] for r in fuori]


def test_una_catena_vuota_lascia_tutti_e_cinque_fuori():
    catena, fuori = compose_topology(chain_order=[], credentials=CRED,
                                      models=MOD, bridge_active=False)
    assert catena == []
    assert [r["id"] for r in fuori] == list(FIXED_ORDER)


def test_nessuna_riga_porta_la_parola_vietata():
    """Invariante 3: «Attivo» significa «interruttore acceso e credenziale
    presente» e si legge «funziona». Non deve rientrare da nessuna porta --
    nemmeno da un campo del payload."""
    catena, fuori = compose_topology(chain_order=["claude"], credentials=CRED,
                                      models=MOD, bridge_active=True)
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
    assert provenance("openrouter", "viva") == "Letti da openrouter.ai adesso."
    assert provenance("openai", "viva") == "Letti da api.openai.com adesso."


def test_una_lettura_fallita_nomina_chi_NON_ha_risposto_e_dice_il_dubbio():
    riga = provenance("openrouter", "riserva")
    assert "Elenco di riserva" in riga
    assert "openrouter.ai" in riga
    assert "potrebbe non esistere più" in riga


def test_ollama_dice_su_QUALE_macchina_sono_scaricati():
    """«in casa» e' una natura, e diventa concreta solo col nome della casa."""
    assert provenance("ollama", "viva", address="http://192.168.1.42:11434") == (
        "Scaricati su http://192.168.1.42:11434 — letti adesso.")
    riga = provenance("ollama", "riserva", address="http://192.168.1.42:11434")
    assert "192.168.1.42" in riga
    assert "chiave rifiutata" not in riga, "Ollama non ha una chiave da rifiutare"


def test_claude_api_nomina_l_ospite_come_gli_altri_due():
    """Qui si asseriva che la provenienza di Claude API avesse parole PROPRIE,
    e quelle parole dicevano all'utente che Anthropic non pubblicherebbe nessun
    elenco. E' falso -- `GET /v1/models` esiste, verificato sulla
    documentazione ufficiale il 15/08/2026 -- e il ramo che le componeva e'
    uscito con la fetta «il modello del piano».

    Il percorso generico produce gia' le due frasi giuste: serviva solo una
    riga in `_OSPITI`. Un caso particolare cancellato, non uno aggiunto."""
    riga = provenance("claude", "riserva")
    assert "api.anthropic.com" in riga
    assert "potrebbe non esistere più" in riga
    assert provenance("claude", "viva") == "Letti da api.anthropic.com adesso."


def test_il_difetto_gemello_si_LEGGE_invece_di_essere_taciuto():
    """Sul ramo di riserva i preset tornano NON filtrati: i gratuiti
    ricompaiono anche con la casella spuntata. Non si corregge (filtrarli
    renderebbe la riserva una lista diversa da quella del sorgente, cioe' una
    terza cosa): si dichiara, dove l'utente sta guardando."""
    muta = provenance("openrouter", "riserva", free_models_notice=False)
    parlante = provenance("openrouter", "riserva", free_models_notice=True)
    assert "nascondi i gratuiti" not in muta
    assert "nascondi i gratuiti" in parlante
    assert "non ha effetto" in parlante


def test_il_pannello_di_openrouter_lo_dice_solo_quando_la_casella_e_spuntata():
    """La composizione intera, non la funzione isolata: e' li' che il fatto e
    la parola si incontrano."""
    # L'elenco deve CONTENERE un gratuito, o l'avviso sarebbe una riga falsa
    # su cio' che l'utente ha davanti (fetta OpenRouter, 22/08/2026: la
    # riserva e' stata potata dei nomi morti, che erano tutti `:free`).
    con_free = ["openrouter:a/b:free", "openrouter:c/d"]
    acceso = compose_panel(provider_id="openrouter", values=con_free,
                              source="riserva", chosen="", hide_free_models=True)
    spento = compose_panel(provider_id="openrouter", values=con_free,
                              source="riserva", chosen="", hide_free_models=False)
    viva = compose_panel(provider_id="openrouter", values=con_free,
                            source="viva", chosen="", hide_free_models=True)
    assert "non ha effetto" in acceso["provenienza"]
    assert "non ha effetto" not in spento["provenienza"]
    assert "non ha effetto" not in viva["provenienza"], (
        "sulla lista VIVA la casella funziona: dirlo sarebbe falso"
    )


def test_i_gratuiti_si_riconoscono_nella_voce_e_non_nella_pagina():
    p = compose_panel(
        provider_id="openrouter", source="viva", chosen="",
        values=["openrouter:openai/gpt-4.1",
                "openrouter:google/gemma-3-27b-it:free"])
    assert [v["nota"] for v in p["modelli"]] == ["", "gratuito"]


def test_la_voce_auto_c_e_solo_dove_auto_esiste():
    """Ollama usa SEMPRE il modello scelto (`fixed_model` vince su ogni altro
    ramo di `_resolve_model`): una voce «scelto da HIRIS» li' prometterebbe una
    scelta che il runner non fa."""
    con = compose_panel(provider_id="claude", values=["claude-opus-4-7"],
                           source="riserva", chosen="",
                           auto_resolved="claude-sonnet-4-6")
    assert con["modelli"][0] == {"valore": "",
                                 "nota": "scelto da HIRIS: oggi claude-sonnet-4-6"}
    senza = compose_panel(provider_id="ollama", values=["llama3.1:8b"],
                             source="viva", chosen="llama3.1:8b")
    assert [v["valore"] for v in senza["modelli"]] == ["llama3.1:8b"]


def test_dove_si_scrive_e_un_percorso_e_ANCHE_il_piano_ne_ha_uno():
    """Qui si asseriva che il piano avesse `dove == []`, con la ragione scritta
    accanto: «il suo modello e' un effetto di quello di Claude API, un pannello
    che offrisse di scriverlo manderebbe una PUT che nessuno legge». Era vera,
    ed era il difetto -- un campo solo per due economie opposte, e il piano del
    proprietario girava con `haiku`.

    Questa e' la riga che accende i tre radio: con `dove` vuoto il frontend
    calcola `scrivibile = false` e li disabilita."""
    assert compose_panel(provider_id="ollama", values=[], source="viva",
                            chosen="")["dove"] == ["ollama", "modello"]
    assert compose_panel(provider_id="openai", values=[], source="viva",
                            chosen="")["dove"] == ["provider_models", "openai"]
    assert compose_panel(provider_id="subscription", values=[], source="fissa",
                            chosen="opus")["dove"] == ["ponte", "modello"]


def test_solo_il_piano_dichiara_l_elenco_completo():
    """`elenco_completo` e `alias` rispondono a due domande diverse e oggi
    coincidono: `alias` dice di che NATURA e' il valore (e decide il carattere
    della riga), `elenco_completo` dice se c'e' altro da cercare fuori
    dall'elenco -- cioe' se il pannello deve offrire un campo dove incollare un
    identificatore. Possono divergere il giorno in cui un provider avesse un
    insieme chiuso di identificatori veri: per questo sono due campi."""
    piano = compose_panel(provider_id="subscription", values=[],
                             source="fissa", chosen="opus")
    assert piano["elenco_completo"] is True
    for pid in ("claude", "openai", "openrouter", "ollama"):
        voce = compose_panel(provider_id=pid, values=["x"], source="viva",
                                chosen="x")
        assert voce["elenco_completo"] is False, pid


def test_la_spiegazione_del_piano_non_manda_piu_a_claude_api():
    """Diventerebbe falsa nel momento esatto in cui la fetta funziona: il
    modello del piano non segue piu' quello di Claude API, e mandare li'
    sarebbe mandare a cambiare il valore sbagliato."""
    testo = explanation("subscription")
    assert "Claude API" not in testo
    assert testo, "e non diventa vuota: la forma del pannello va spiegata comunque"


def test_il_piano_e_l_unico_che_sceglie_un_ALIAS():
    assert is_alias("subscription") is True
    for pid in ("claude", "openai", "openrouter", "ollama"):
        assert is_alias(pid) is False, pid


def test_su_ollama_senza_modello_la_riga_dice_cosa_manca_e_non_offre_il_gesto():
    """Il buco dichiarato dal Task 7. La credenziale c'e' (l'indirizzo), il
    pallino resta acceso, e a mancare e' il modello: entrare in catena
    produrrebbe un anello che il router salta in silenzio."""
    cred = {**CRED, "ollama": True}
    _, fuori = compose_topology(chain_order=["claude"], credentials=cred,
                                 models={**MOD, "ollama": ""}, bridge_active=False)
    riga = {r["id"]: r for r in fuori}["ollama"]
    assert riga["ha_credenziale"] is True
    assert riga["manca"] == ""
    assert riga["riordinabile"] is False
    assert "il modello no" in riga["nota"]

    _, fuori = compose_topology(chain_order=["claude"], credentials=cred,
                                 models={**MOD, "ollama": "llama3.1:8b"},
                                 bridge_active=False)
    riga = {r["id"]: r for r in fuori}["ollama"]
    assert riga["riordinabile"] is True
    assert riga["nota"] == ""


def test_senza_indirizzo_la_riga_dice_QUELLO_e_non_il_modello():
    """Un impedimento alla volta, e il piu' esterno per primo: «manca il
    modello» sopra un Ollama che non ha nemmeno un indirizzo manderebbe a
    risolvere la cosa sbagliata."""
    _, fuori = compose_topology(chain_order=[], credentials=CRED,
                                 models={**MOD, "ollama": ""}, bridge_active=False)
    riga = {r["id"]: r for r in fuori}["ollama"]
    assert riga["manca"] == "manca l'indirizzo"
    assert riga["nota"] == ""
    assert riga["riordinabile"] is True


# ---------------------------------------------------------------------------
# La riga di stato: l'ultimo esito osservato, su ogni riga (Task 11)
#
# E' cio' che chiude il caso del proprietario per intero: senza, la pagina sa
# dire «Claude e' primo» ma non «e sta rifiutando da quaranta richieste».
# L'orologio e' un parametro in ogni prova qui sotto.
# ---------------------------------------------------------------------------

ADESSO = 10_000.0
CREDITO_FINITO = {"tipo": "rifiutato", "famiglia": "credenziale", "codice": 400,
                  "messaggio": "credit balance too low", "quando": ADESSO - 180,
                  "da_quante": 40, "durata_s": 0.4}
HA_RISPOSTO = {"tipo": "risposto", "famiglia": "", "codice": None,
               "messaggio": "", "quando": ADESSO - 180, "da_quante": 1,
               "durata_s": 0.0}


def test_il_caso_del_proprietario_si_legge_sulla_riga():
    """La sua chiave Claude e' a credito zero, l'API risponde `400 credit
    balance too low`, e per giorni la pagina l'ha mostrata come funzionante
    mentre OpenRouter serviva ogni turno al posto suo. Adesso le due righe
    dicono due cose diverse, ed e' la verita' misurata."""
    catena, _ = _compose_topology(
        chain_order=["claude", "openrouter"], credentials=CRED, models=MOD,
        bridge_active=False, now=ADESSO,
        occurrences={"claude": CREDITO_FINITO, "openrouter": HA_RISPOSTO})
    righe = {r["id"]: r for r in catena}
    assert righe["claude"]["stato_testo"] == (
        "ha rifiutato le ultime 40 richieste — credito esaurito (400), 3 min fa")
    assert righe["openrouter"]["stato_testo"] == "ha risposto 3 min fa"


def test_il_fatto_grezzo_viaggia_accanto_alla_frase():
    """La pagina disegna diverso cio' che ha rifiutato -- pallino grigio-ambra,
    nome che perde peso -- e per farlo legge `esito.tipo`, non il testo.
    Dedurre una regola da una frase e' come ricostruirla."""
    catena, _ = _compose_topology(
        chain_order=["claude"], credentials=CRED, models=MOD,
        bridge_active=False, now=ADESSO, occurrences={"claude": CREDITO_FINITO})
    assert catena[0]["esito"] == CREDITO_FINITO


def test_chi_non_e_stato_osservato_porta_esito_None_e_non_un_finto_successo():
    catena, fuori = _compose_topology(
        chain_order=["claude", "openrouter"], credentials=CRED, models=MOD,
        bridge_active=False, now=ADESSO, occurrences={"claude": CREDITO_FINITO})
    righe = {r["id"]: r for r in catena + fuori}
    assert righe["openrouter"]["esito"] is None
    assert righe["openrouter"]["stato_testo"] == "non è mai servito ripiegare qui"


def test_mai_provato_dice_due_cose_diverse_in_prima_e_in_seconda_posizione():
    """Stesso fatto -- nessuna osservazione -- due frasi. In testa e'
    allarmante (chi dovrebbe rispondere a ogni messaggio non ha mai risposto a
    nessuno), in seconda e' la notizia buona (il ripiego non e' mai servito).
    UNA regola sola, ed e' la posizione."""
    catena, _ = _compose_topology(
        chain_order=["claude", "openrouter"], credentials=CRED, models=MOD,
        bridge_active=False, now=ADESSO, occurrences={})
    assert [r["stato_testo"] for r in catena] == [
        "non l'hai ancora usato", "non è mai servito ripiegare qui"]


def test_senza_credenziale_e_senza_osservazioni_la_riga_di_stato_tace():
    """La riga dice gia' «manca la chiave», che e' la spiegazione COMPLETA di
    perche' non e' mai stata interrogata. «Non l'hai ancora usato» sotto
    sarebbe la stessa cosa detta due volte, la seconda con meno
    informazione."""
    _, fuori = _compose_topology(
        chain_order=["claude"], credentials=CRED, models=MOD,
        bridge_active=False, now=ADESSO, occurrences={})
    riga = {r["id"]: r for r in fuori}["openai"]
    assert riga["ha_credenziale"] is False
    assert riga["manca"] == "manca la chiave"
    assert riga["stato_testo"] == "" and riga["esito"] is None


def test_un_esito_sopravvive_alla_credenziale_tolta():
    """Togliere la chiave a un provider non cancella cosa aveva risposto:
    quella riga E' STATA interrogata davvero, e il fatto resta. Tacere qui
    sarebbe cancellare un'osservazione per una ragione di configurazione."""
    senza = {**CRED, "openrouter": False}
    _, fuori = _compose_topology(
        chain_order=["claude"], credentials=senza, models=MOD,
        bridge_active=False, now=ADESSO,
        occurrences={"openrouter": dict(CREDITO_FINITO, famiglia="irraggiungibile",
                                  codice=None, da_quante=2)})
    riga = {r["id"]: r for r in fuori}["openrouter"]
    assert riga["stato_testo"] == (
        "non risponde all'indirizzo — ultimo tentativo 3 min fa")


def test_l_eta_della_riga_cresce_col_solo_passare_del_tempo():
    """Nessuna nuova chiamata, nessuna nuova osservazione: cambia SOLO
    l'orologio del chiamante, e la riga lo dichiara. E' la prova che il
    registro non ringiovanisce da solo, vista dal punto in cui la pagina la
    legge."""
    def _riga(adesso):
        catena, _ = _compose_topology(
            chain_order=["claude"], credentials=CRED, models=MOD,
            bridge_active=False, now=adesso, occurrences={"claude": CREDITO_FINITO})
        return catena[0]["stato_testo"]

    assert _riga(ADESSO).endswith("3 min fa")
    assert _riga(ADESSO + 7200).endswith("2 h fa")
    assert _riga(ADESSO + 86400 * 3).endswith("3 giorni fa")


def test_anche_il_piano_ha_la_sua_riga_di_stato():
    """Il piano e' un provider come gli altri per cio' che riguarda cosa e'
    successo: se il ponte ha risposto, la riga lo dice. La sua eccezione e'
    solo dove si entra in catena, non cosa si e' osservato."""
    catena, _ = _compose_topology(
        chain_order=["claude"], credentials=CRED, models=MOD,
        bridge_active=True, now=ADESSO, occurrences={"subscription": HA_RISPOSTO})
    assert catena[0]["id"] == "subscription"
    assert catena[0]["stato_testo"] == "ha risposto 3 min fa"


def test_i_due_parametri_nuovi_sono_obbligatori():
    """Con un valore di comodo, un chiamante che se ne dimenticasse
    produrrebbe una pagina che non dice MAI niente sugli esiti -- e nessun
    test se ne accorgerebbe. E' la forma di guasto peggiore che questa fetta
    conosca, ed e' la ragione per cui il Task 14 dipende da questo."""
    with pytest.raises(TypeError):
        _compose_topology(chain_order=["claude"], credentials=CRED,
                           models=MOD, bridge_active=False)


# ── La nota del ripiego (Task 14) ─────────────────────────────────────────
#
# Non e' un test sul codice: e' un test sulle PAROLE. Il ripiego si annuncia
# ogni volta (decisione del proprietario, 13 agosto), e cio' che la riga dice
# e' l'unica cosa che l'utente vedra' mai di tutta questa fetta.

from hiris.app.decisione_modelli import downgrade_note


def test_la_nota_dice_cosa_e_successo_e_chi_ha_risposto():
    assert downgrade_note(reason="scadenza", who_answered="openrouter") == (
        "Il Piano Claude Max non ha risposto in tempo: ha risposto OpenRouter, "
        "a consumo.")


def test_i_tre_motivi_sono_tre_fatti_diversi():
    """Tre fatti osservati, non una diagnosi: «non ha risposto in tempo» non e'
    «non ha un token», e chi legge fa due cose diverse."""
    assert "non ha un token" in downgrade_note(
        reason="manca il token", who_answered="claude")
    assert "tetto di messaggi per oggi" in downgrade_note(
        reason="tetto giornaliero", who_answered="claude")
    assert "non ha risposto in tempo" in downgrade_note(
        reason="scadenza", who_answered="claude")


@pytest.mark.parametrize("motivo", ["scadenza", "manca il token", "tetto giornaliero"])
def test_la_nota_non_diagnostica_e_non_allarma(motivo):
    """Stessa disciplina degli avvisi di `esegui` (`azione/porta.py`): un
    avviso e' un FATTO su cio' che HIRIS ha potuto vedere, mai un'ipotesi sulla
    causa. Una parola di troppo qui e il modello -- che rilegge la cronologia --
    la trasforma in una diagnosi inventata: e' successo davvero, il giorno in
    cui HIRIS, davanti a un comando riuscito, si invento' un guasto del
    dispositivo e mando' il proprietario a cercarlo."""
    testo = downgrade_note(reason=motivo, who_answered="openrouter")
    for vietata in ("attenzione", "errore", "problema", "probabilmente", "forse",
                    "sembra", "potrebbe", "verifica", "controlla"):
        assert vietata not in testo.lower(), (vietata, testo)


def test_la_natura_di_chi_risponde_e_sempre_dichiarata():
    """E' l'unica parte della nota che riguarda i soldi, ed e' la ragione per
    cui la nota esiste."""
    for pid, attesa in (("openrouter", "a consumo"), ("ollama", "in casa"),
                        ("claude", "a consumo"), ("openai", "a consumo")):
        assert attesa in downgrade_note(reason="scadenza", who_answered=pid), pid


def test_di_un_provider_che_non_si_conosce_non_si_dichiara_la_natura():
    """La prova gemella del silenzio. Senza la natura la nota perderebbe la
    meta' per cui esiste, e «ha risposto pinco, .» sarebbe una riga rotta che
    parla di soldi: meglio non scriverla. Stessa regola di
    `_who_answered_note` quando non sa chi ha risposto."""
    assert downgrade_note(reason="scadenza", who_answered="pinco") == ""


def test_un_motivo_che_non_e_un_fatto_osservato_non_si_annuncia():
    """La seconda meta' della stessa regola. Un motivo fuori tabella
    produrrebbe, con un ripiego del tipo «se non so niente, comportati come
    prima», una frase generica su un ripiego di cui non si sa il perche': si
    tace, e il test che lega le due estremita' (`_piano_puo_rispondere` ->
    `_DOWNGRADE_REASONS`) sta in test_chat_subscription_path.py."""
    assert downgrade_note(reason="boh", who_answered="openrouter") == ""


def test_la_nota_nomina_il_piano_con_il_nome_che_ha_in_tutto_il_prodotto():
    """Un nome per provider, mai due (Task 5). La nota non se ne inventa uno
    suo: se `DISPLAY_NAMES` cambiasse, cambierebbe anche qui."""
    testo = downgrade_note(reason="scadenza", who_answered="openrouter")
    assert testo.startswith("Il " + display_name("subscription") + " ")
    assert display_name("openrouter") in testo


def test_l_avviso_sui_gratuiti_segue_il_CONTENUTO_dell_elenco():
    """Fetta OpenRouter (22/08/2026). L'avviso «la casella non ha effetto,
    l'elenco di riserva li contiene comunque» era calcolato da una condizione
    che lo INDOVINAVA: openrouter + riserva + casella spuntata. Vero finche' la
    riserva conteneva cinque `:free`; falso dal momento in cui e' stata potata
    dei nomi morti, che erano tutti gratuiti. Una riga che dice il falso su
    cio' che si sta guardando e' il difetto n.1 di questo prodotto."""
    from hiris.app.decisione_modelli import compose_panel

    con_gratuiti = compose_panel(
        provider_id="openrouter", values=["openrouter:a/b:free", "openrouter:c/d"],
        source="riserva", chosen="", hide_free_models=True)
    senza = compose_panel(
        provider_id="openrouter", values=["openrouter:c/d"],
        source="riserva", chosen="", hide_free_models=True)

    assert "non ha effetto" in con_gratuiti["provenienza"], (
        "l'elenco ne contiene uno: l'avviso e' vero e va detto")
    assert "non ha effetto" not in senza["provenienza"], (
        "l'elenco non ne contiene: l'avviso sarebbe una riga falsa su cio' "
        "che l'utente ha davanti")
