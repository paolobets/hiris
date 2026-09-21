"""Il SOFFITTO: quanto si concede a chi chiede (spec 2026-09-21, §2 e §4).

**Il principio, del proprietario**: *HIRIS non concede mai piu' di quanto il
chiamante gia' puo' in Home Assistant.* Ne' piu' ne' meno.

Meno sarebbe **teatro**: un utente non amministratore comanda gia' le sue entita'
dalla plancia, e impedirglielo dentro HIRIS non toglie un potere a nessuno.
Piu' e' quello che HIRIS faceva: parla con HA col proprio token, che e'
amministratore, quindi non restringeva -- **amplificava**.

**La forma, dopo la decisione del 21/09 sui canali.** Il ruolo non si deduce da
dove arriva una richiesta: **viaggia con la credenziale**. Per una persona lo
dice Home Assistant (`config/auth/list`), per un canale lo dice la registrazione,
per un turno senza soggetto lo dice il suo mestiere. Quattro sorgenti, **una
funzione sola** che decide -- invece di quattro funzioni che si somigliano e
divergono al primo cambiamento (fondamenta 2).

**Il grado piu' basso non e' «niente».** Chi e' passato dall'ingress di Home
Assistant *e' comunque un utente di HA*, quindi comanda: il grado piu' basso
compatibile con l'essere passati di li' e' `utente`, non `lettore`. Trattare un
ruolo illeggibile come «non puo' niente» spegnerebbe la chat a chi ha tutto il
diritto di usarla, per un guasto di rete.
"""
import pytest

from hiris.app.api.soffitto import consente

_PERSONA = {"specie": "persona", "id": "u-1", "nome": "Paolo"}
_ANONIMO = {"specie": "persona", "id": None, "nome": None}
_CANALE = {"specie": "integrazione", "id": "gateway", "nome": "gateway"}
_LUOGO = {"specie": "luogo", "id": "retropanel", "nome": "Retro Panel"}


@pytest.mark.parametrize("ruolo,legge,comanda,costruisce", [
    ("amministratore", True, True, True),
    ("utente", True, True, False),
    ("lettore", True, False, False),
])
def test_i_tre_ruoli_decidono_tutto(ruolo, legge, comanda, costruisce):
    """La tabella della spec §4, pinnata sul soffitto e non solo sul modulo dei
    canali: sono due lettori dello stesso fatto, e devono dire la stessa cosa.

    Mutazione ESEGUITA: dare `costruire` a «utente» -- rossa."""
    esito = consente(_PERSONA, ruolo=ruolo)

    assert esito["leggere"] is legge
    assert esito["comandare"] is comanda
    assert esito["costruire"] is costruisce


def test_un_utente_qualunque_NON_costruisce_ma_comanda():
    """Il cuore del principio, detto sul caso vero. Comandare resta: la plancia
    glielo da' gia'. Costruire no: la plancia non glielo da'.

    Mutazione ESEGUITA: negare anche `comandare` -- rossa, ed e' la mutazione
    che descrive l'errore di disegno evitato."""
    esito = consente(_PERSONA, ruolo="utente")

    assert esito["costruire"] is False
    assert esito["comandare"] is True, (
        "vietare a un utente di HA di comandare dalla chat cio' che comanda "
        "dalla plancia e' teatro, non sicurezza")
    assert esito["perche"], "un rifiuto senza motivo e' un ordine"


def test_il_ruolo_ILLEGGIBILE_vale_utente_non_lettore():
    """**Il grado piu' basso compatibile con l'essere passati da HA.** Se Home
    Assistant non ha risposto, chi sta chiedendo e' comunque un utente che ha
    superato l'ingress: negargli di comandare per un guasto di rete gli
    toglierebbe cio' che la plancia gli da' comunque.

    Ma costruire no: quello resta chiuso finche' non si sa.

    Mutazione ESEGUITA: ripiegare su `lettore` -- rossa (la chat si spegne per
    un guasto)."""
    esito = consente(_PERSONA, ruolo=None)

    assert esito["comandare"] is True
    assert esito["costruire"] is False
    assert "non" in esito["perche"].lower()


def test_un_ingress_ANONIMO_comanda_ma_non_costruisce():
    """`X-Remote-User-Id` non e' garantito: con provider di autenticazione non
    nativi puo' mancare. Chi e' senza identita' ha comunque una sessione di HA
    valida, quindi vale `utente`.

    Mutazione: trattare l'anonimo come amministratore -- rossa."""
    esito = consente(_ANONIMO, ruolo=None)

    assert esito["comandare"] is True
    assert esito["costruire"] is False


def test_un_CANALE_vale_il_ruolo_della_sua_registrazione():
    """Il gateway, il Retro Panel, la porta di sviluppo: il ruolo gliel'ha dato
    il proprietario quando li ha registrati, e non si deduce da nient'altro.

    Mutazione ESEGUITA: far ereditare a un canale il ramo delle persone --
    rossa (un canale «lettore» comanderebbe)."""
    assert consente(_CANALE, ruolo="utente")["comandare"] is True
    assert consente(_CANALE, ruolo="utente")["costruire"] is False
    assert consente(_CANALE, ruolo="lettore")["comandare"] is False
    assert consente(_LUOGO, ruolo="amministratore")["costruire"] is True


def test_un_CANALE_senza_ruolo_non_puo_niente():
    """Qui il verso del dubbio e' l'opposto di quello delle persone, e la
    differenza e' il fatto che li' distingue: una persona ha comunque superato
    l'ingress di Home Assistant, una macchina senza ruolo **non ha superato
    niente**.

    Mutazione ESEGUITA: dare `utente` anche a un canale senza ruolo -- rossa."""
    esito = consente(_CANALE, ruolo=None)

    assert esito["leggere"] is False
    assert esito["comandare"] is False
    assert esito["costruire"] is False


def test_un_ruolo_INVENTATO_ricade_dove_ricade_uno_MANCANTE():
    """I ruoli sono un insieme chiuso, e una parola fuori dall'insieme non e'
    un permesso. Ma «fuori dall'insieme» e «mancante» sono lo stesso fatto --
    *non ho un ruolo valido per costui* -- e devono avere lo stesso esito, o
    esisterebbero due strade per la stessa condizione.

    Quindi vale l'asimmetria fra le specie, non una terza regola: per una
    persona `utente` (ha comunque superato l'ingress), per una macchina niente
    (non ha superato niente).

    Mutazione ESEGUITA: trattare la parola inventata come un ruolo valido --
    rossa."""
    persona = consente(_PERSONA, ruolo="capo")
    assert persona["comandare"] is True
    assert persona["costruire"] is False
    assert persona == consente(_PERSONA, ruolo=None)

    macchina = consente(_CANALE, ruolo="capo")
    assert macchina["comandare"] is False
    assert macchina == consente(_CANALE, ruolo=None)


def test_ogni_esito_risponde_a_TUTTI_i_gesti():
    """Un soffitto che non nomina un gesto lo lascia passare in silenzio.
    L'insieme e' chiuso, e ogni esito li copre tutti.

    Mutazione: aggiungere un gesto a `GESTI` e non rispondergli -- rossa."""
    from hiris.app.api.soffitto import GESTI

    for soggetto in (_PERSONA, _ANONIMO, _CANALE, _LUOGO):
        for ruolo in (*("amministratore", "utente", "lettore"), None, "capo"):
            esito = consente(soggetto, ruolo=ruolo)
            for gesto in GESTI:
                assert isinstance(esito.get(gesto), bool), (
                    f"{gesto} senza risposta per {soggetto['specie']}/{ruolo}")
