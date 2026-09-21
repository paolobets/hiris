"""Il SOFFITTO: quanto si concede a chi chiede (invariante I-1).

**Il principio, deciso dal proprietario il 21/09/2026**: *HIRIS non concede mai
piu' di quanto il chiamante gia' puo' in Home Assistant.* Ne' piu' ne' meno.

Meno sarebbe **teatro**: un utente non amministratore comanda gia' le sue entita'
dalla plancia, e impedirglielo dentro HIRIS non toglie un potere a nessuno --
aggiunge una frustrazione e una falsa sensazione di sicurezza.

Piu' e' quello che HIRIS fa **oggi**, ed e' il difetto che questo modulo chiude.
Verificato sul sorgente di Home Assistant il 21/09: il Supervisor proxa verso il
nucleo con la propria sessione privilegiata, e
`websocket_api/connection.py::context` costruisce il contesto **dall'utente
autenticato, ignorando il messaggio** -- nessuna delega, nessuna impersonazione.
Quindi HIRIS parla con HA da amministratore qualunque sia la persona che ha
scritto, e un non amministratore che passa di qui ottiene i poteri di HIRIS
invece dei propri.

**Dove sta la differenza, misurata.** Non nei servizi: `verification.py` dichiara
che i servizi di sistema (`homeassistant.restart`, `hassio.host_reboot`,
`recorder.purge`, `shell_command.*`) sono gia' irraggiungibili dalla porta,
perche' non dichiarano un bersaglio e un bersaglio vuoto e' sempre un rifiuto.
L'amplificazione vera e' **una sola porta**: la CONFIGURAZIONE. Un non
amministratore, via HIRIS, puo' far scrivere automazioni in casa -- cosa che Home
Assistant gli nega.

Da cui il soffitto: **una porta, due valori**. Nessun servizio elencato, niente
che invecchi a ogni rilascio di HA.
"""

from hiris.app.api.soffitto import consente

_AMMINISTRATORE = {"specie": "persona", "id": "u-1", "nome": "Paolo"}
_OSPITE = {"specie": "persona", "id": "u-9", "nome": "Ospite"}
_ANONIMO = {"specie": "persona", "id": None, "nome": None}
_INTEGRAZIONE = {"specie": "integrazione", "id": None, "nome": None}


def test_un_amministratore_costruisce():
    """Il caso del proprietario: non cambia niente di come usa HIRIS oggi.

    Mutazione: negare a tutti -- rossa (sarebbe il prodotto rotto per tutti,
    non messo in sicurezza)."""
    assert consente(_AMMINISTRATORE, amministratore=True)["costruire"] is True


def test_un_utente_qualunque_NON_costruisce_ma_tutto_il_resto_si():
    """Il cuore del principio. Comandare resta: la plancia glielo da' gia'.
    Costruire no: la plancia non glielo da'.

    Mutazione ESEGUITA: togliere la distinzione e negare anche `comandare` --
    rossa, ed e' la mutazione che descrive l'errore di disegno evitato."""
    esito = consente(_OSPITE, amministratore=False)

    assert esito["costruire"] is False
    assert esito["comandare"] is True, (
        "vietare a un utente di HA di comandare dalla chat cio' che comanda "
        "dalla plancia e' teatro, non sicurezza")
    assert esito["perche"], "un rifiuto senza motivo e' un ordine"


def test_un_ingress_ANONIMO_non_costruisce():
    """`X-Remote-User-Id` non e' garantito. «Non so chi sei» non e' «sei il
    proprietario»: si vale il grado piu' basso.

    Mutazione: trattare l'anonimo come amministratore -- rossa."""
    assert consente(_ANONIMO, amministratore=None)["costruire"] is False


def test_se_il_RUOLO_non_si_e_potuto_leggere_non_si_costruisce():
    """**Il verso del dubbio.** Se Home Assistant non ha risposto, il ruolo e'
    `None` -- e un guasto di rete non deve diventare un aumento di privilegi.

    Mutazione ESEGUITA: `amministratore or True` al posto del confronto --
    rossa."""
    esito = consente(_AMMINISTRATORE, amministratore=None)

    assert esito["costruire"] is False
    assert "non" in esito["perche"].lower()


def test_una_INTEGRAZIONE_tiene_oggi_il_soffitto_di_ieri_e_lo_dichiara():
    """Il gateway, il proxy di Retro Panel e il ponte portano un token, non una
    persona: `amministratore` non si applica e non si puo' dedurre.

    Oggi conservano il soffitto che avevano, **dichiarato e non dedotto**: il
    loro perimetro e' l'invariante successivo (i canali esterni, con credenziali
    non falsificabili), e stringerlo qui a meta' vorrebbe dire romperli adesso
    per una difesa che arriva dopo.

    Mutazione: fargli ereditare in silenzio il ramo delle persone -- rossa (un
    token diventerebbe una persona anonima, cioe' negato, e il gateway si
    spegnerebbe senza che nessuno l'abbia deciso)."""
    esito = consente(_INTEGRAZIONE, amministratore=None)

    assert esito["costruire"] is True
    assert esito["rinviato"] is True, (
        "il soffitto delle macchine e' una decisione rinviata, e va DETTA: "
        "un rinvio taciuto e' indistinguibile da una svista")


def test_ogni_gesto_conosciuto_ha_una_risposta():
    """Un soffitto che non nomina un gesto lo lascia passare in silenzio.
    L'insieme dei gesti e' chiuso, e ogni esito li copre tutti.

    Mutazione: aggiungere un gesto a `GESTI` e non rispondergli -- rossa."""
    from hiris.app.api.soffitto import GESTI

    for soggetto, ruolo in ((_AMMINISTRATORE, True), (_OSPITE, False),
                            (_ANONIMO, None), (_INTEGRAZIONE, None)):
        esito = consente(soggetto, amministratore=ruolo)
        for gesto in GESTI:
            assert gesto in esito, f"{gesto} senza risposta per {soggetto['specie']}"
            assert isinstance(esito[gesto], bool)
