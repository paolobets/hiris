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


# --- A-2 · ci si fida dell'INDIRIZZO del proxy, risolto ---------------------

def test_l_indirizzo_del_proxy_si_RISOLVE_e_si_crede_solo_quello():
    """**Il reperto A-2.** La rete predefinita non e' l'indirizzo del proxy: e'
    la rete Docker dove vive ogni add-on installato, e se il tunnel che
    pubblica la casa gira come add-on -- il caso normale -- il suo indirizzo e'
    li' dentro.

    Risolvendo il nome «supervisor» si ottiene UN indirizzo, e si crede quello.

    Mutazione ESEGUITA: ignorare l'indirizzo risolto e tenere le opzioni --
    rossa."""
    reti, rifiuti, come = ingresso.perimetro_fidato(
        "172.30.32.0/23", risolutore=lambda _nome: "172.30.32.2")

    assert [str(r) for r in reti] == ["172.30.32.2/32"]
    assert rifiuti == []
    assert "172.30.32.2" in come


def test_si_risolve_il_nome_GIUSTO():
    """Il nome non e' una scelta nostra: e' quello con cui il Supervisor si fa
    trovare nella rete Docker, lo stesso di `http://supervisor/core`.

    Mutazione: risolvere un altro nome -- rossa."""
    chiesti = []
    ingresso.perimetro_fidato("", risolutore=lambda nome: chiesti.append(nome) or "10.0.0.1")

    assert chiesti == ["supervisor"]


def test_se_il_nome_NON_SI_RISOLVE_si_torna_alle_opzioni():
    """**La riga che la 3.60.0 non aveva, e per cui ha chiuso il proprietario
    fuori dal suo pannello.** Un guasto nella verifica non deve spegnere
    l'unica strada che il proprietario ha per entrare in casa propria.

    Mutazione ESEGUITA: nessun ripiego -- rossa, ed e' il difetto vero
    rilasciato il 22/09/2026."""
    def risolutore_guasto(_nome):
        raise OSError("questo nome qui non esiste")

    reti, rifiuti, come = ingresso.perimetro_fidato("172.30.32.0/23",
                                                   risolutore=risolutore_guasto)

    assert [str(r) for r in reti] == ["172.30.32.0/23"]
    assert rifiuti == []
    assert "opzioni" in come


def test_e_il_registro_DICE_quanto_e_largo_il_perimetro():
    """Chi legge il registro deve sapere di quanto ci si sta fidando oggi senza
    andarlo a dedurre: un indirizzo solo, o una rete intera.

    Mutazione: tornare sempre la stessa frase -- rossa."""
    _, _, stretto = ingresso.perimetro_fidato("", risolutore=lambda _n: "172.30.32.2")
    _, _, largo = ingresso.perimetro_fidato(
        "172.30.32.0/23", risolutore=lambda _n: (_ for _ in ()).throw(OSError()))

    assert stretto != largo
    assert "Supervisor" in stretto and "opzioni" in largo


def test_un_indirizzo_STORTO_non_fa_cadere_l_avvio():
    """Se il risolutore torna qualcosa che non e' un indirizzo, si ripiega
    invece di impedire l'avvio.

    Mutazione: costruire la rete senza difendersi -- rossa."""
    reti, _, _ = ingresso.perimetro_fidato("172.30.32.0/23",
                                          risolutore=lambda _n: "non-un-indirizzo")

    assert [str(r) for r in reti] == ["172.30.32.0/23"]


def test_la_verifica_della_sessione_NON_ESISTE_piu():
    """**Il cancello di questo difetto.** `POST /ingress/validate_session` e'
    riservato a Home Assistant Core: in
    `supervisor/api/middleware/security.py` quella rotta non combacia con
    nessuna lista permissiva e cade nel controllo finale, che nega. Il
    Supervisor ha risposto **403** e la 3.60.0 ha chiuso il proprietario fuori
    dal proprio pannello.

    Rimetterla e' la cosa piu' naturale del mondo per chi legge la spec del
    Supervisor e si ferma un gradino prima di «e io, posso?».

    Mutazione ESEGUITA: rimessa la chiamata -- rossa."""
    import ast
    import pathlib as _p

    sorgente = _p.Path(ingresso.__file__).read_text(encoding="utf-8")

    # **Si guardano le STRINGHE VIVE, non il testo**: i docstring nominano
    # quella rotta apposta -- e' li' che la lezione sta scritta -- e cercare la
    # parola renderebbe il cancello impossibile da soddisfare senza cancellare
    # la memoria del difetto.
    letterali = [n.value for n in ast.walk(ast.parse(sorgente))
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    vive = [t for t in letterali if chr(10) not in t]

    assert not any("supervisor/" in t or "validate_session" in t for t in vive), (
        "questo modulo torna a comporre un indirizzo verso il Supervisor: "
        "`/ingress/validate_session` e' riservato a Home Assistant Core, "
        "risponde 403 a un add-on, e l'ingress smette di funzionare per tutti")
