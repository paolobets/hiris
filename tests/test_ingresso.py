"""Come si sa che una richiesta viene DAVVERO dall'ingress del Supervisor.

Reperti A-2 e A-3 del registro dei rischi (`docs/design/2026-09-21-sicurezza-esposizioni.md`).

Fino al 22/09/2026 la risposta era: l'intestazione `X-Ingress-Path` combacia con
un'espressione regolare **e** l'indirizzo sorgente sta in `172.30.32.0/23`. Il
secondo controllo sembra stretto e non lo e': quel `/23` non e' l'indirizzo del
proxy, e' **la rete Docker in cui vive ogni add-on installato**. Qualunque
add-on vicino manda l'intestazione e ottiene `/api/*` per intero senza conoscere
nessun segreto — e se il tunnel che pubblica la casa gira come add-on
(Cloudflared, Tailscale: il caso normale), il suo indirizzo e' li' dentro.

**La risposta vera e' il biscotto di sessione**, e si chiede al Supervisor se
quella sessione esiste. Verificato il 22/09 sulla sorgente del Supervisor, non
supposto:

- `supervisor/api/__init__.py` registra `web.post("/ingress/validate_session",
  api_ingress.validate_session)`;
- `handler()` legge la sessione da `request.cookies.get(COOKIE_INGRESS, "")`,
  dove `COOKIE_INGRESS = "ingress_session"`;
- `_init_header()` filtra dodici intestazioni prima di inoltrare e **il biscotto
  non e' fra quelle**: arriva all'add-on.

Un add-on vicino puo' falsificare `X-Ingress-Path` e puo' trovarsi nel `/23`.
Non puo' avere un biscotto di sessione che il Supervisor riconosce senza averlo
rubato a una persona.
"""
import pytest

from hiris.app.api import ingresso

# --- A-3 · le reti fidate si validano, e un rifiuto si NOMINA ---------------

def test_una_rete_privata_e_stretta_passa():
    """Il caso normale: il default dell'add-on.

    Mutazione: rifiutare tutto -- rossa (l'ingress smetterebbe di funzionare)."""
    reti, rifiutate = ingresso.reti_fidate("172.30.32.0/23")

    assert [str(r) for r in reti] == ["172.30.32.0/23"]
    assert rifiutate == []


def test_TUTTO_INTERNET_non_e_una_rete_fidata():
    """**Il reperto A-3.** `0.0.0.0/0` passava in silenzio, e chi ce lo scriveva
    apriva `/api/*` a chiunque sapesse scrivere un'intestazione.

    Mutazione ESEGUITA: accettare qualunque prefisso -- rossa."""
    reti, rifiutate = ingresso.reti_fidate("0.0.0.0/0")

    assert reti == []
    assert len(rifiutate) == 1
    assert "0.0.0.0/0" in rifiutate[0]


@pytest.mark.parametrize("larga", ["10.0.0.0/8", "0.0.0.0/0", "172.16.0.0/12"])
def test_una_rete_piu_larga_di_16_si_rifiuta_anche_se_privata(larga):
    """Privata non vuol dire stretta: un `/8` privato sono sedici milioni di
    indirizzi, e il proxy del Supervisor e' UNO.

    Mutazione: guardare solo `is_private` -- rossa."""
    reti, rifiutate = ingresso.reti_fidate(larga)

    assert reti == []
    assert rifiutate


def test_una_rete_PUBBLICA_si_rifiuta_anche_se_stretta():
    """Un indirizzo pubblico non puo' essere il proxy del Supervisor, che vive
    nella rete Docker: se ce n'e' uno scritto, e' un errore o e' un attacco.

    Mutazione ESEGUITA: guardare solo la larghezza -- rossa."""
    reti, rifiutate = ingresso.reti_fidate("8.8.8.8/32")

    assert reti == []
    assert rifiutate


def test_una_voce_STORTA_non_fa_cadere_l_avvio():
    """La scrive una persona nella pagina del Supervisor: prima o poi qualcuno
    scrivera' male, e un errore di battitura non deve impedire l'avvio.

    Mutazione: lasciar propagare `ValueError` -- rossa."""
    reti, rifiutate = ingresso.reti_fidate("non-un-cidr, 172.30.32.0/23")

    assert [str(r) for r in reti] == ["172.30.32.0/23"]
    assert len(rifiutate) == 1


def test_ogni_rifiuto_dice_QUALE_voce_e_PERCHE():
    """Un rifiuto che non nomina la voce costringe a indovinare quale delle tre
    righe e' quella sbagliata.

    Mutazione ESEGUITA: rifiutare in silenzio -- rossa."""
    _, rifiutate = ingresso.reti_fidate("0.0.0.0/0, 8.8.8.8/32, zzz")

    assert len(rifiutate) == 3
    assert all(len(r) > 20 for r in rifiutate)
    unite = " ".join(rifiutate)
    assert "0.0.0.0/0" in unite and "8.8.8.8/32" in unite and "zzz" in unite


def test_se_TUTTE_le_voci_sono_rifiutate_non_si_ripiega_sul_default():
    """**La meta' del reperto che si dimentica.** Ripiegare sul default largo
    quando ogni voce e' sbagliata vorrebbe dire che scrivere male allarga il
    perimetro invece di stringerlo: il proprietario crede di aver ristretto, e
    ha aperto.

    Mutazione ESEGUITA: ripiegare sul default -- rossa."""
    reti, rifiutate = ingresso.reti_fidate("0.0.0.0/0")

    assert reti == [], "un campo tutto sbagliato ha prodotto una rete fidata"
    assert rifiutate


def test_un_campo_VUOTO_e_diverso_da_un_campo_sbagliato():
    """Vuoto vuol dire «non ho deciso», e allora decide il prodotto col suo
    default. Sbagliato vuol dire «ho deciso, e ho deciso una cosa che non si
    puo' fare»: li' non si ripiega su niente.

    Mutazione: trattarli allo stesso modo -- rossa in un verso o nell'altro."""
    reti, rifiutate = ingresso.reti_fidate("")

    assert [str(r) for r in reti] == [ingresso.RETE_PREDEFINITA]
    assert rifiutate == []


# --- A-2(b) · la sessione si chiede al Supervisor ---------------------------

class _Supervisor:
    """Il Supervisor, ridotto all'unica domanda che gli facciamo.

    Il vero risponde 200 a una sessione che conosce e 401 a una che non
    conosce (`supervisor/api/ingress.py::validate_session`, letto il 22/09).
    """

    def __init__(self, conosce=(), stato=None, cade=False):
        self.conosce = set(conosce)
        self.stato = stato
        self.cade = cade
        self.chiamate = []

    async def __call__(self, sessione):
        self.chiamate.append(sessione)
        if self.cade:
            raise OSError("il Supervisor non risponde")
        if self.stato is not None:
            return self.stato == 200
        return sessione in self.conosce


@pytest.fixture()
def app():
    contenitore = {}
    ingresso.prepara_ingresso(contenitore)
    return contenitore


@pytest.fixture()
def supervisor(monkeypatch):
    def installa(finto):
        async def chiedi(sessione):
            return await finto(sessione)
        monkeypatch.setattr(ingresso, "_domanda_supervisor", chiedi)
        return finto
    return installa


@pytest.mark.asyncio
async def test_una_sessione_CONOSCIUTA_dal_supervisor_passa(app, supervisor):
    """Il caso normale: il proprietario ha aperto HIRIS dalla plancia.

    Mutazione: rifiutare sempre -- rossa (la pagina smetterebbe di aprirsi)."""
    supervisor(_Supervisor(conosce={"s-vera"}))

    assert await ingresso.sessione_valida(app, "s-vera", adesso=100.0) is True


@pytest.mark.asyncio
async def test_una_sessione_INVENTATA_non_passa(app, supervisor):
    """**Il reperto A-2.** E' cio' che ha in mano un add-on vicino: puo'
    falsificare l'intestazione e puo' stare nella rete fidata, ma non puo'
    avere un biscotto che il Supervisor riconosce.

    Mutazione ESEGUITA: fidarsi del solo biscotto senza chiederlo -- rossa."""
    supervisor(_Supervisor(conosce={"s-vera"}))

    assert await ingresso.sessione_valida(app, "inventata", adesso=100.0) is False


@pytest.mark.asyncio
async def test_SENZA_biscotto_non_si_chiede_nemmeno(app, supervisor):
    """Chi non porta un biscotto non e' passato dal proxy: non c'e' niente da
    chiedere, e chiederlo sarebbe una chiamata di rete per ogni richiesta
    diretta.

    Mutazione: chiedere comunque -- rossa."""
    finto = supervisor(_Supervisor(conosce={"s-vera"}))

    for vuoto in ("", "   ", None):
        assert await ingresso.sessione_valida(app, vuoto, adesso=100.0) is False
    assert finto.chiamate == []


@pytest.mark.asyncio
async def test_se_il_supervisor_NON_RISPONDE_si_rifiuta(app, supervisor):
    """**Il verso del dubbio, e qui costa qualcosa dirlo.** Ripiegare sul
    controllo della rete quando il Supervisor tace vorrebbe dire riaprire
    esattamente il buco che questa verifica chiude, e riaprirlo proprio nel
    momento in cui qualcosa non va.

    E non e' severita' gratuita: una richiesta arrivata ATTRAVERSO il proxy
    dimostra che il Supervisor era vivo un istante prima.

    Mutazione ESEGUITA: ripiegare su `True` -- rossa."""
    supervisor(_Supervisor(cade=True))

    assert await ingresso.sessione_valida(app, "s-vera", adesso=100.0) is False


@pytest.mark.asyncio
async def test_una_risposta_INATTESA_si_rifiuta(app, supervisor):
    """500, 403, una pagina di errore: tutto cio' che non e' 200 e' «no».

    Mutazione: trattare come valido tutto cio' che non e' 401 -- rossa."""
    supervisor(_Supervisor(stato=500))

    assert await ingresso.sessione_valida(app, "s-vera", adesso=100.0) is False


@pytest.mark.asyncio
async def test_l_esito_si_RICORDA_per_non_chiedere_a_ogni_richiesta(app, supervisor):
    """Una chiamata di rete a ogni richiesta della pagina sarebbe un costo su
    un percorso che gira decine di volte al minuto.

    Mutazione ESEGUITA: non ricordare -- rossa (due chiamate)."""
    finto = supervisor(_Supervisor(conosce={"s-vera"}))

    for _ in range(5):
        await ingresso.sessione_valida(app, "s-vera", adesso=100.0)

    assert finto.chiamate == ["s-vera"]


@pytest.mark.asyncio
async def test_anche_un_NO_si_ricorda(app, supervisor):
    """Altrimenti chi bussa con biscotti inventati fa interrogare il Supervisor
    una volta per bussata: il rifiuto diventerebbe un amplificatore.

    Mutazione: ricordare solo i sì -- rossa."""
    finto = supervisor(_Supervisor(conosce={"s-vera"}))

    for _ in range(5):
        await ingresso.sessione_valida(app, "inventata", adesso=100.0)

    assert finto.chiamate == ["inventata"]


@pytest.mark.asyncio
async def test_il_ricordo_SCADE(app, supervisor):
    """Una sessione revocata deve smettere di valere in fretta: ricordarne
    l'esito per piu' di un minuto vorrebbe dire servirne una morta per una
    frazione apprezzabile della sua vita, che dura quindici minuti.

    Mutazione ESEGUITA: ricordare per sempre -- rossa."""
    finto = supervisor(_Supervisor(conosce={"s-vera"}))

    await ingresso.sessione_valida(app, "s-vera", adesso=100.0)
    await ingresso.sessione_valida(app, "s-vera", adesso=100.0 + ingresso.RICORDO_S + 1)

    assert len(finto.chiamate) == 2


@pytest.mark.asyncio
async def test_i_ricordi_non_crescono_per_sempre(app, supervisor):
    """Chi bussa con un biscotto diverso ogni volta riempirebbe la memoria di
    un percorso che gira a ogni richiesta.

    Mutazione: non potare mai -- rossa."""
    supervisor(_Supervisor(conosce=set()))

    for n in range(200):
        await ingresso.sessione_valida(app, f"finta-{n}", adesso=100.0 + n)
    await ingresso.sessione_valida(app, "ultima", adesso=1000.0)

    assert len(app["sessioni_ingress"]) < 10


@pytest.mark.asyncio
async def test_senza_il_token_del_supervisor_non_si_prova_NEMMENO(monkeypatch):
    """Fuori dal Supervisor e' normale e la richiesta non e' di ingress;
    dentro, e' un guasto dell'add-on. In tutti e due i casi non si finge di
    aver verificato.

    **Si guarda la domanda, non l'esito, e la prima stesura era verde per la
    ragione sbagliata**: `sessione_valida` inghiotte qualunque eccezione e
    torna `False`, quindi togliendo la guardia sul token la prova restava verde
    -- passava perche' la chiamata di rete falliva, non perche' la guardia
    c'era. Misurato con la mutazione, non supposto. Qui si chiede alla
    funzione che NON inghiotte, e si pretende che la rete non venga nemmeno
    toccata.

    Mutazione ESEGUITA: `if False:` al posto della guardia sul token -- rossa
    (la finta della rete si fa sentire)."""
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    class _NessunaRete:
        def __init__(self, *a, **k):
            raise AssertionError(
                "ha provato a chiamare il Supervisor senza averne il token")

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", _NessunaRete)

    assert await ingresso._domanda_supervisor("s-vera") is False


@pytest.mark.asyncio
async def test_e_chi_chiama_vede_un_NO_non_un_guasto(app, monkeypatch):
    """La contropartita: il rifiuto deve arrivare al confine come un «no»
    ordinario, non come un'eccezione che spegne la richiesta.

    Mutazione: sollevare invece di tornare `False` -- rossa."""
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    assert await ingresso.sessione_valida(app, "s-vera", adesso=100.0) is False


def test_il_nome_del_biscotto_e_quello_del_SUPERVISOR():
    """Il nome non e' una scelta nostra: lo decide
    `supervisor/api/ingress.py::COOKIE_INGRESS`, e se divergesse HIRIS non
    troverebbe mai nessuna sessione e rifiuterebbe ogni ingress senza dire
    perche'.

    Mutazione: rinominarlo -- rossa."""
    assert ingresso.BISCOTTO == "ingress_session"
