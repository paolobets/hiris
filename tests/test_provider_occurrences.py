"""Cosa è successo davvero, per provider.

Oggi HIRIS butta via questa informazione: `LLMRouter.chat` logga «Backend …
failed, trying next» e va avanti, e i runner collassano ogni errore in
`RunnerBackendError("Errore temporary del servizio AI")` perdendo codice e
causa. È la ragione per cui il proprietario non ha mai saputo del credito
esaurito.

L'orologio è INIETTATO in ogni test: «3 minuti fa» è una cosa che si può
provare solo se il tempo non avanza da solo. E il registro non si azzera mai da
sé -- un esito vecchio resta vecchio, e la pagina ne dichiara l'età invece di
regalare una freschezza che la produzione non ha.
"""
import pytest

from hiris.app.model_resolution import occurrence_phrase
from hiris.app.provider_occurrences import (
    OccurrenceRegistry,
    error_family,
    family_from_code,
)


def _registro(t0=1000.0):
    adesso = [t0]
    return OccurrenceRegistry(clock=lambda: adesso[0]), adesso


def test_senza_osservazioni_non_si_afferma_niente():
    r, _ = _registro()
    assert r.occurrence("claude") is None


def test_un_successo_e_un_fatto_con_una_data():
    r, _t = _registro()
    r.successo("openrouter")
    e = r.occurrence("openrouter")
    assert e["tipo"] == "risposto" and e["quando"] == 1000.0 and e["da_quante"] == 1


def test_i_fallimenti_consecutivi_si_contano():
    """«Ha rifiutato LE ULTIME 40 RICHIESTE» dice una cosa che «ha rifiutato 3
    minuti fa» non dice: che non è un incidente, è lo stato."""
    r, t = _registro()
    for i in range(40):
        t[0] += 1
        r.fallimento("claude", family="credenziale", code=402,
                     message="credit balance too low", durata_s=0.4)
    e = r.occurrence("claude")
    assert e["da_quante"] == 40 and e["quando"] == 1040.0


def test_un_successo_azzera_il_conto_dei_rifiuti():
    r, _t = _registro()
    r.fallimento("claude", family="credenziale", code=402, message="x", durata_s=0.1)
    r.fallimento("claude", family="credenziale", code=402, message="x", durata_s=0.1)
    r.successo("claude")
    assert r.occurrence("claude") == {"tipo": "risposto", "famiglia": "", "codice": None,
                                 "messaggio": "", "quando": 1000.0, "da_quante": 1,
                                 "durata_s": 0.0}


def test_i_successi_consecutivi_si_contano_anche_loro():
    """`da_quante` è «richieste consecutive con lo stesso esito», non «rifiuti
    consecutivi»: se contasse solo i fallimenti, il campo direbbe una cosa per
    metà dei valori di `tipo` e niente per l'altra metà."""
    r, t = _registro()
    for _ in range(3):
        t[0] += 1
        r.successo("openrouter")
    assert r.occurrence("openrouter")["da_quante"] == 3


def test_un_rifiuto_DIVERSO_ricomincia_a_contare():
    """La frase composta è «ha rifiutato le ultime N richieste — <causa
    dell'ultima>»: se N contasse anche i rifiuti di un'altra famiglia, la causa
    verrebbe attribuita a richieste che l'hanno avuta diversa. Sarebbe
    un'affermazione più precisa di quanto il sistema sa -- la regola di questo
    prodotto, applicata a un contatore."""
    r, t = _registro()
    for _ in range(5):
        t[0] += 1
        r.fallimento("openai", family="modello", code=404, message="", durata_s=0.1)
    assert r.occurrence("openai")["da_quante"] == 5
    t[0] += 1
    r.fallimento("openai", family="credenziale", code=401, message="", durata_s=0.1)
    e = r.occurrence("openai")
    assert e["da_quante"] == 1 and e["famiglia"] == "credenziale" and e["codice"] == 401


def test_due_provider_non_si_confondono():
    r, _ = _registro()
    r.successo("openrouter")
    r.fallimento("claude", family="credenziale", code=402, message="x", durata_s=0.1)
    assert r.occurrence("openrouter")["tipo"] == "risposto"
    assert r.occurrence("claude")["tipo"] == "rifiutato"


def test_tutti_restituisce_una_voce_per_provider_osservato_e_nessuna_per_gli_altri():
    """`tutti()` è ciò che l'handler passa alla pagina. Un provider mai
    interrogato NON deve comparire: «non c'è niente da dire» e «ha risposto»
    sono due cose diverse, e la seconda si afferma solo dopo averla vista."""
    r, _ = _registro()
    r.successo("openrouter")
    assert set(r.occurrences()) == {"openrouter"}


def test_chi_legge_il_registro_non_lo_puo_riscrivere():
    """`esito()` e `tutti()` consegnano una copia. Un lettore che modificasse
    il dizionario ricevuto riscriverebbe la storia osservata dell'add-on da un
    handler HTTP."""
    r, _ = _registro()
    r.successo("claude")
    r.occurrence("claude")["tipo"] = "rifiutato"
    r.occurrences()["claude"]["da_quante"] = 99
    assert r.occurrence("claude") == {"tipo": "risposto", "famiglia": "", "codice": None,
                                 "messaggio": "", "quando": 1000.0, "da_quante": 1,
                                 "durata_s": 0.0}


def test_un_esito_vecchio_resta_vecchio_e_lo_dichiara():
    adesso = [1000.0]
    r = OccurrenceRegistry(clock=lambda: adesso[0])
    r.fallimento("claude", family="altro", code=400,
                 message="credit balance too low", durata_s=0.4)
    adesso[0] += 7200                      # due ore dopo, e NESSUNA nuova chiamata
    e = r.occurrence("claude")
    assert e["quando"] == 1000.0, "il registro non deve ringiovanire da solo"
    assert occurrence_phrase(e, position=1, now=adesso[0]) == (
        "ha rifiutato l’ultima richiesta — errore 400: «credit balance too low», 2 h fa")


@pytest.mark.parametrize("codice,attesa", [
    (400, "altro"), (401, "credenziale"), (402, "credenziale"), (403, "credenziale"),
    (404, "modello"), (429, "altro"), (500, "altro"), (None, "altro"),
])
def test_le_famiglie_d_errore_sono_tre_piu_una(codice, attesa):
    """Collassarle in «errore temporaneo» è ciò che fa il codice oggi, ed è la
    ragione per cui il proprietario non ha mai saputo del credito. Sono tre
    frasi diverse e tre azioni diverse per chi legge."""
    assert family_from_code(codice) == attesa


def _phrase_for(famiglia, codice):
    """La frase della pagina per un rifiuto di questa famiglia e codice."""
    r, _ = _registro()
    r.fallimento("claude", family=famiglia, code=codice, message="boh", durata_s=0.0)
    return occurrence_phrase(r.occurrence("claude"), position=1, now=1060.0)


@pytest.mark.parametrize("codice", [400, 401, 402, 403, 404, 429, 500, None])
def test_ogni_famiglia_che_nasce_da_un_codice_ha_il_suo_ramo(codice):
    """Una famiglia introdotta di soppiatto finirebbe nel ramo di scorta di
    `occurrence_phrase` senza che nessuno se ne accorga. Si chiede al ramo, non
    a un elenco: fino alla Tappa 7 T9 la prova guardava `FAMILIES`, una tupla
    che solo lei leggeva (voce M-81) -- `occurrence_phrase` decide per rami e
    non l'ha mai consultata, quindi l'elenco poteva dire il vero mentre la
    pagina scriveva la frase di scorta.

    Proprieta': una famiglia diversa da `altro` produce una frase diversa da
    quella di `altro` con lo stesso codice.

    Mutazione eseguita (07/10/2026): in `family_from_code`, il 404 restituisce
    `"modelli"` invece di `"modello"` -> rosso su `codice=404` (le due frasi
    coincidono: «ha rifiutato l'ultima richiesta — errore 404»). Ripristinato,
    `git diff hiris/app/provider_occurrences.py` senza la mutazione.

    `scaduto` non nasce da un codice HTTP: non c'e' nessuna risposta da cui
    prenderlo. La scrive a mano l'unico punto che la osserva
    (`handlers_chat._downgrade_to_chain`)."""
    famiglia = family_from_code(codice)
    assert famiglia != "scaduto"
    if famiglia != "altro":
        assert _phrase_for(famiglia, codice) != _phrase_for("altro", codice), (
            f"la famiglia «{famiglia}» del codice {codice} non ha un ramo suo"
        )


def test_una_scadenza_non_si_legge_come_un_rifiuto():
    """La ragione per cui la quinta famiglia esiste, scritta come frase: chi
    legge la riga del piano deve poter distinguere «non ha risposto» da «ha
    rifiutato». Sono due azioni diverse per chi guarda -- guardare se il worker
    del ponte gira, contro rifare la credenziale."""
    esito = {"tipo": "rifiutato", "famiglia": "scaduto", "codice": None,
             "messaggio": "nessuna risposta entro la scadenza del ponte",
             "quando": 1000.0, "da_quante": 3, "durata_s": 300.0}
    frase = occurrence_phrase(esito, position=1, now=1000.0 + 600)
    assert frase == "non ha risposto in tempo — le ultime 3 richieste, 10 min fa"
    assert "rifiutato" not in frase


def test_un_errore_di_connessione_e_irraggiungibile_non_altro():
    import httpx
    assert error_family(httpx.ConnectError("boom")) == "irraggiungibile"
    assert error_family(ConnectionError("boom")) == "irraggiungibile"


def test_le_due_sdk_dicono_irraggiungibile_nello_stesso_modo():
    """`openai` e `anthropic` hanno la stessa coppia di eccezioni con lo
    stesso significato. Riconoscerne una sola avrebbe fatto leggere «ha
    rifiutato l'ultima richiesta» a un Claude che non si era nemmeno
    raggiunto -- e Claude è il provider del caso del proprietario."""
    import anthropic
    import httpx
    import openai

    richiesta = httpx.Request("POST", "https://esempio/v1")
    assert error_family(anthropic.APIConnectionError(request=richiesta)) == "irraggiungibile"
    assert error_family(openai.APIConnectionError(request=richiesta)) == "irraggiungibile"


def test_famiglia_errore_legge_il_codice_quando_l_eccezione_ce_l_ha():
    """I runner sollevano da `anthropic.APIError` / `openai.APIError`, che
    portano `status_code`. Se `error_family` lo ignorasse, ogni errore d'API
    tornerebbe «altro» e una chiave rifiutata (401) non sarebbe distinguibile
    da un 500 -- cioè il difetto che questo modulo chiude, rientrato
    dall'unica porta che i runner usano. (Il 400 e' «altro» dal 06/10/2026,
    G39-2.)"""
    class _Api(Exception):
        status_code = 401

    class _Muta(Exception):
        pass

    assert error_family(_Api()) == "credenziale"
    assert error_family(_Muta()) == "altro"


def test_un_errore_di_connessione_resta_irraggiungibile_anche_col_codice():
    """Un `APIConnectionError` di openai porta `status_code` a `None`, ma
    un'eccezione di connessione con un codice addosso non è impossibile: la
    connessione VINCE sul codice, altrimenti Ollama spento si leggerebbe
    «errore temporaneo»."""
    import httpx

    class _ConnColCodice(httpx.ConnectError):
        status_code = 500

    assert error_family(_ConnColCodice("boom")) == "irraggiungibile"


# ── L'età, e i cinque stati ────────────────────────────────────────────────
#
# `_age` è la funzione che rende un'affermazione più precisa di quanto il
# sistema sa, se sbagliata: si guarda sui CONFINI, dove un `<` al posto di un
# `<=` sposta una frase di un'unità intera.


@pytest.mark.parametrize("secondi,attesa", [
    (0, "poco fa"),
    (59, "poco fa"),
    (60, "1 min fa"),
    (180, "3 min fa"),
    (3599, "59 min fa"),
    (3600, "1 h fa"),
    # 90 minuti: si arrotonda PER DIFETTO, perché «2 h fa» direbbe più di
    # quanto è passato.
    (5400, "1 h fa"),
    (7200, "2 h fa"),
    (86399, "23 h fa"),
    (86400, "ieri"),
    (172799, "ieri"),
    (172800, "2 giorni fa"),
])
def test_l_eta_sui_confini(secondi, attesa):
    from hiris.app.model_resolution import _age
    assert _age(secondi) == attesa


def test_un_orologio_che_va_all_indietro_non_produce_un_futuro():
    """`adesso` e `quando` vengono da due letture diverse dello stesso
    orologio, e su un sistema che si sincronizza con NTP la seconda può
    risultare PRIMA della prima. «fra 3 min» sarebbe una previsione, e questa
    pagina non ne fa."""
    from hiris.app.model_resolution import _age
    assert _age(-5) == "poco fa"


def test_le_frasi_dei_cinque_stati():
    a = 10_000.0
    assert occurrence_phrase(None, position=1, now=a) == (
        "nessuna osservazione da quando l’add-on è partito")
    assert occurrence_phrase(None, position=3, now=a) == (
        "nessun ripiego servito da quando l’add-on è partito")
    assert occurrence_phrase({"tipo": "risposto", "famiglia": "", "codice": None,
                        "messaggio": "", "quando": a - 180, "da_quante": 1,
                        "durata_s": 0.0}, position=2, now=a) == "ha risposto 3 min fa"
    assert occurrence_phrase({"tipo": "rifiutato", "famiglia": "altro", "codice": 400,
                        "messaggio": "credit balance too low", "quando": a - 180,
                        "da_quante": 40, "durata_s": 0.4}, position=1, now=a) == (
        "ha rifiutato le ultime 40 richieste — errore 400: «credit balance too low», 3 min fa")
    assert occurrence_phrase({"tipo": "rifiutato", "famiglia": "modello", "codice": 404,
                        "messaggio": "", "quando": a - 180, "da_quante": 1,
                        "durata_s": 0.2}, position=1, now=a) == (
        "il modello non esiste più (404), 3 min fa")
    assert occurrence_phrase({"tipo": "rifiutato", "famiglia": "irraggiungibile", "codice": None,
                        "messaggio": "", "quando": a - 7200, "da_quante": 3,
                        "durata_s": 5.0}, position=3, now=a) == (
        "non risponde all’indirizzo — ultimo tentativo 2 h fa")


def test_mai_provato_fuori_dalla_catena_non_e_un_ripiego_mancato():
    """Chi sta FUORI dalla catena non ha una posizione: «nessun ripiego
    servito» direbbe che è un anello di riserva, e non lo è. Stesso fatto,
    la frase di chi non è mai stato osservato."""
    assert occurrence_phrase(None, position=None, now=10_000.0) == (
        "nessuna osservazione da quando l’add-on è partito")


def test_una_chiave_rifiutata_non_e_un_credito_esaurito():
    """402 dice «i soldi sono finiti» (OpenRouter); 401 e 403 dicono «questa chiave non va
    bene». Sono due azioni diverse per chi legge -- ricaricare, oppure rifare
    la chiave -- e chiamarle tutte «credito esaurito» sarebbe un'ipotesi sulla
    causa, che è esattamente ciò che questo prodotto non fa."""
    a = 10_000.0

    def _f(codice):
        return occurrence_phrase({"tipo": "rifiutato", "famiglia": "credenziale",
                            "codice": codice, "messaggio": "", "quando": a - 180,
                            "da_quante": 1, "durata_s": 0.1}, position=1, now=a)

    assert _f(402) == "ha rifiutato l’ultima richiesta — credito esaurito (402), 3 min fa"
    assert _f(401) == "ha rifiutato l’ultima richiesta — la chiave non è accettata (401), 3 min fa"
    assert _f(403) == "ha rifiutato l’ultima richiesta — la chiave non è accettata (403), 3 min fa"


def test_la_famiglia_di_scorta_dice_il_codice_e_non_lo_interpreta():
    """«altro» è ciò che il sistema NON ha saputo classificare: un 500, un 429,
    un guasto senza codice. La frase riporta il numero e si ferma lì -- non
    inventa una causa, che è la regola nata il giorno in cui HIRIS mandò il
    proprietario a cercare un guasto del dispositivo che non c'era. Se il
    provider ha detto qualcosa, si cita (G39-2): e' la sua causa, non la
    nostra."""
    a = 10_000.0

    def _f(codice, quante=1, detto=""):
        return occurrence_phrase({"tipo": "rifiutato", "famiglia": "altro", "codice": codice,
                            "messaggio": detto, "quando": a - 180, "da_quante": quante,
                            "durata_s": 0.1}, position=1, now=a)

    assert _f(400) == "ha rifiutato l’ultima richiesta — errore 400, 3 min fa"
    assert _f(None) == "ha rifiutato l’ultima richiesta, 3 min fa"
    assert _f(400, detto="boom") == "ha rifiutato l’ultima richiesta — errore 400: «boom», 3 min fa"
    # Un 429 o un 5xx non e' un rifiuto (giro 43; RFC 6585 §4, RFC 9110
    # §15.6): la stessa regola per classe HTTP della chat.
    assert _f(500) == "non ha servito l’ultima richiesta — errore temporaneo 500, 3 min fa"
    assert _f(429, quante=7) == (
        "non ha servito le ultime 7 richieste — errore temporaneo 429, 3 min fa")
    assert _f(529, detto="Overloaded") == (
        "non ha servito l’ultima richiesta — errore temporaneo 529: «Overloaded», 3 min fa")
    assert _f(None, detto="boom") == "ha rifiutato l’ultima richiesta: «boom», 3 min fa"


def test_il_modello_inesistente_non_conta_le_richieste():
    """Quante volte HIRIS abbia chiesto un modello che non esiste non aggiunge
    niente: il fatto è che non esiste. Il conteggio serve dove distingue
    l'incidente dallo stato (il credito), non dove lo stato è ovvio."""
    a = 10_000.0
    assert occurrence_phrase({"tipo": "rifiutato", "famiglia": "modello", "codice": 404,
                        "messaggio": "", "quando": a - 3600, "da_quante": 12,
                        "durata_s": 0.2}, position=2, now=a) == (
        "il modello non esiste più (404), 1 h fa")
