"""I CANALI e la loro credenziale (spec 2026-09-21 «i canali e i ruoli», §6-§7).

Fino al 21/09/2026 quattro portatori -- il ponte, il gateway MCP su un'altra
macchina, il proxy di Retro Panel e la porta di sviluppo -- presentavano **lo
stesso segreto condiviso**. Un segreto condiviso non e' un'identita': e' una
parola d'ordine, e chi la sente una volta e' tutti. Compromessa una qualunque
delle quattro strade l'unica mossa era cambiare il token e romperle tutte
insieme, e nessun registro poteva dire QUALE integrazione avesse chiamato.

**Perche' asimmetrica** (spec §6): `/data` finisce nei backup di Home Assistant,
in chiaro se l'utente non gli mette una password. Con un segreto per canale, chi
legge un backup impersona quel canale; con una chiave **pubblica** non ottiene
niente. E' questa la differenza fra «segreto» e «non falsificabile».

**La firma copre la richiesta, non l'identita'**: metodo, percorso, momento,
valore irripetibile, impronta del corpo. Firmare la sola identita' lascerebbe
cambiare cio' che la richiesta chiede tenendo buona la firma.

**Chi sia il canale lo dice l'archivio dei servizi** (22/09/2026), non un campo
di testo nelle opzioni: un servizio esiste quando il proprietario l'ha
approvato, e l'approvazione E' la dichiarazione. Qui si prova cosa fa `canali`
con la risposta dell'archivio; che l'archivio risponda bene lo provano
`test_servizi.py` e `test_servizi_rotte.py`.
"""
import base64
import hashlib
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hiris.app.api import canali
from hiris.app.api.servizi import ServiziStore

from ._contracts import assert_stessa_firma


def _coppia():
    privata = Ed25519PrivateKey.generate()
    return privata, base64.b64encode(
        privata.public_key().public_bytes_raw()).decode("ascii")


class _Archivio:
    """L'archivio dei servizi, ridotto all'UNICA cosa che `canali` gli chiede.

    Il vero vive in SQLite e ha sei metodi; su questo percorso ne serve uno, e
    una finta di un metodo dice a chi legge esattamente quanto `canali` dipende
    dall'archivio. Che la firma combaci con quella vera lo pinna
    `test_la_finta_combacia_con_l_archivio_vero`.
    """

    def __init__(self, righe: dict | None = None) -> None:
        self._righe = righe or {}

    def autorizzato(self, chiave: str) -> dict | None:
        return self._righe.get(chiave)


def _servizi(pubblica, *, nome="sviluppo", ruolo="lettore", specie="integrazione"):
    return _Archivio({pubblica: {"nome": nome, "ruolo": ruolo, "specie": specie,
                                 "chiave": pubblica, "stato": "autorizzato"}})


def _firma(privata, *, chiave=None, metodo="GET", percorso="/api/entities",
           momento=None, unico="u-1", corpo=b""):
    momento = time.time() if momento is None else momento
    if chiave is None:
        chiave = base64.b64encode(
            privata.public_key().public_bytes_raw()).decode("ascii")
    materia = canali.materia_firmata(metodo, percorso, momento, unico, corpo)
    return {"chiave": chiave, "momento": momento, "unico": unico,
            "firma": base64.b64encode(privata.sign(materia)).decode("ascii"),
            "metodo": metodo, "percorso": percorso, "corpo": corpo}


def _verifica(servizi, visti=None, adesso=None, **richiesta):
    return canali.riconosci(
        servizi=servizi, visti={} if visti is None else visti,
        adesso=time.time() if adesso is None else adesso, **richiesta)


# --- la firma ---------------------------------------------------------------

def test_una_firma_valida_da_il_canale_e_il_suo_RUOLO():
    """Il caso normale. Da qui il registro puo' dire QUALE integrazione ha
    chiamato -- cosa che prima non poteva -- e con quale perimetro.

    Mutazione: accettare senza verificare -- rossa."""
    privata, pubblica = _coppia()

    esito, motivo = _verifica(_servizi(pubblica), **_firma(privata))

    assert motivo is None, motivo
    assert esito["servizio"] == "sviluppo"
    assert esito["ruolo"] == "lettore"


def test_la_SPECIE_arriva_dall_archivio_e_non_si_inventa():
    """Una macchina e un pannello appeso al muro sono due fatti diversi nella
    cronaca, e chi lo decide e' il proprietario quando approva.

    Mutazione ESEGUITA: mettere sempre «integrazione» -- rossa."""
    privata, pubblica = _coppia()

    esito, _ = _verifica(_servizi(pubblica, specie="luogo"), **_firma(privata))

    assert esito["specie"] == "luogo"


def test_la_firma_di_un_ALTRA_chiave_non_passa():
    """Il cuore: la chiave che HIRIS tiene non serve a firmare, serve a
    verificare. Chi legge il disco di HIRIS -- o un backup -- non ottiene
    niente di utile.

    Mutazione ESEGUITA: confrontare le chiavi invece delle firme -- rossa."""
    _, pubblica = _coppia()
    altra, _ = _coppia()

    esito, motivo = _verifica(_servizi(pubblica),
                              **_firma(altra, chiave=pubblica))

    assert esito is None and motivo


def test_il_CORPO_e_dentro_la_firma():
    """Firmare la sola identita' lascerebbe cambiare cio' che la richiesta
    chiede tenendo buona la firma.

    Mutazione ESEGUITA: togliere l'impronta del corpo da `materia_firmata` --
    rossa."""
    privata, pubblica = _coppia()
    richiesta = _firma(privata, metodo="POST", percorso="/api/chat",
                       corpo=b'{"message": "che ore sono"}')
    richiesta["corpo"] = b'{"message": "spegni tutto"}'

    esito, _ = _verifica(_servizi(pubblica, ruolo="utente"), **richiesta)

    assert esito is None, "il corpo e' cambiato e la firma regge ancora"


def test_anche_il_PERCORSO_e_dentro_la_firma():
    """Una firma nata per una lettura non deve valere per una scrittura.

    Mutazione: firmare solo il corpo -- rossa."""
    privata, pubblica = _coppia()
    richiesta = _firma(privata, percorso="/api/entities")
    richiesta["percorso"] = "/api/usage/reset"

    esito, _ = _verifica(_servizi(pubblica), **richiesta)

    assert esito is None


def test_la_materia_firmata_e_UNA_sola():
    """Il contratto fra chi firma e chi verifica, scritto una volta. Se
    divergesse, ogni firma legittima verrebbe rifiutata e nessuno capirebbe
    perche'.

    Mutazione: cambiare l'ordine dei campi -- rossa (nessuna firma verifica
    piu')."""
    materia = canali.materia_firmata("POST", "/api/chat", 1758470000.0, "u-9",
                                     b"ciao")

    assert b"POST" in materia and b"/api/chat" in materia
    assert b"1758470000" in materia and b"u-9" in materia
    assert hashlib.sha256(b"ciao").hexdigest().encode() in materia


# --- le tre difese contro «qualcuno in mezzo» -------------------------------

def test_una_richiesta_VECCHIA_non_passa():
    """Una firma intercettata non deve valere per sempre.

    Mutazione: togliere la finestra -- rossa."""
    privata, pubblica = _coppia()
    adesso = time.time()

    esito, motivo = _verifica(
        _servizi(pubblica), adesso=adesso,
        **_firma(privata, momento=adesso - canali.FINESTRA_S - 1))

    assert esito is None
    assert "momento" in motivo.lower()


def test_una_richiesta_dal_FUTURO_non_passa():
    """La finestra vale in entrambi i versi: guardare solo il passato
    lascerebbe che un orologio avanti di un'ora allarghi la finestra di un'ora,
    cioe' lascerebbe **al chiamante** il compito di deciderla.

    Mutazione ESEGUITA: controllare solo il passato -- rossa."""
    privata, pubblica = _coppia()
    adesso = time.time()

    esito, _ = _verifica(
        _servizi(pubblica), adesso=adesso,
        **_firma(privata, momento=adesso + canali.FINESTRA_S + 60))

    assert esito is None


def test_la_STESSA_richiesta_non_si_RIGIOCA():
    """**Il «qualcuno in mezzo».** Dentro la finestra, una richiesta
    intercettata e rimandata identica sarebbe ancora valida: e' il valore
    irripetibile a impedirlo.

    Mutazione ESEGUITA: non ricordare gli `unico` gia' visti -- rossa."""
    privata, pubblica = _coppia()
    richiesta = _firma(privata)
    visti = {}

    primo, _ = _verifica(_servizi(pubblica), visti=visti, **richiesta)
    secondo, motivo = _verifica(_servizi(pubblica), visti=visti, **richiesta)

    assert primo is not None
    assert secondo is None, "la stessa richiesta e' passata due volte"
    assert motivo


def test_i_valori_gia_visti_non_crescono_per_sempre():
    """Ricordare ogni valore per sempre sarebbe una perdita di memoria su un
    percorso che gira a ogni richiesta. Fuori dalla finestra un valore non puo'
    piu' servire a nessuno, perche' il suo momento e' gia' scaduto.

    Mutazione: non potare mai -- rossa."""
    privata, pubblica = _coppia()
    adesso = time.time()
    visti = {f"vecchio-{n}": adesso - canali.FINESTRA_S * 4 for n in range(50)}

    _verifica(_servizi(pubblica), visti=visti, adesso=adesso,
              **_firma(privata, momento=adesso))

    assert len(visti) < 10, f"i valori scaduti sono rimasti: {len(visti)}"


# --- chi e' autorizzato lo dice l'ARCHIVIO ----------------------------------

def test_una_chiave_MAI_APPROVATA_non_passa_nemmeno_con_la_firma_giusta():
    """**La proprieta' che tiene in piedi l'accoppiamento.** Se bastasse una
    firma valida, il primo contatto sarebbe l'autorizzazione e non ci sarebbe
    niente da approvare.

    Mutazione ESEGUITA: fidarsi della sola firma -- rossa."""
    privata, _ = _coppia()

    esito, motivo = _verifica(_Archivio(), **_firma(privata))

    assert esito is None
    assert "autorizzat" in motivo.lower()
    assert "accoppiamento" in motivo.lower(), (
        "il rifiuto non dice cosa fare: un rifiuto che non dice cosa fare è "
        "un ordine")


def test_un_servizio_SENZA_ARCHIVIO_non_passa():
    """Se l'archivio non c'è — avvio a metà, prova scritta male — il verso del
    dubbio è negare, non fidarsi.

    Mutazione ESEGUITA: accettare quando `servizi` è `None` -- rossa."""
    privata, _ = _coppia()

    esito, motivo = _verifica(None, **_firma(privata))

    assert esito is None and motivo


def test_un_servizio_autorizzato_senza_RUOLO_non_passa():
    """Una riga guasta nell'archivio non deve ereditare un permesso in
    silenzio: quel qualcosa sarebbe deciso dal codice invece che dal
    proprietario.

    Mutazione ESEGUITA: ripiegare su «utente» quando il ruolo manca -- rossa."""
    privata, pubblica = _coppia()

    esito, motivo = _verifica(
        _Archivio({pubblica: {"nome": "sviluppo", "ruolo": None}}),
        **_firma(privata))

    assert esito is None
    assert "ruolo" in motivo.lower()


def test_un_ruolo_SCONOSCIUTO_non_passa():
    """I ruoli sono un insieme chiuso: una parola nuova non e' un permesso, e'
    un ruolo su cui nessuno ha deciso.

    Mutazione: accettare qualunque stringa come ruolo -- rossa."""
    privata, pubblica = _coppia()

    esito, motivo = _verifica(_servizi(pubblica, ruolo="capo"), **_firma(privata))

    assert esito is None
    assert "ruolo" in motivo.lower()


def test_una_firma_STORTA_non_fa_cadere_la_verifica():
    """Questa funzione sta sul percorso di ogni richiesta: un'eccezione qui
    spegnerebbe l'add-on invece di negare un accesso.

    Mutazione: lasciar propagare l'eccezione -- rossa."""
    _, pubblica = _coppia()
    for guasta in ("", "non-base64!!", base64.b64encode(b"corta").decode()):
        esito, motivo = _verifica(
            _servizi(pubblica), chiave=pubblica, momento=time.time(),
            unico="u-x", firma=guasta, metodo="GET", percorso="/api/entities",
            corpo=b"")
        assert esito is None and motivo


def test_una_CHIAVE_storta_non_fa_cadere_la_verifica():
    """La chiave arriva da fuori, in un'intestazione: prima o poi arrivera'
    scritta male, e per sbaglio o apposta.

    Mutazione: costruire la chiave senza difendersi -- rossa."""
    privata, _ = _coppia()
    for guasta in ("", "non-base64!!", base64.b64encode(b"corta").decode()):
        esito, motivo = _verifica(_servizi(guasta),
                                  **_firma(privata, chiave=guasta))
        assert esito is None and motivo


def test_la_finta_combacia_con_l_archivio_vero():
    """Una finta che si scosta dal vero rende verdi prove che col vero
    sarebbero rosse: e' il difetto n.1 di questo progetto, sotto un'altra
    forma.

    Mutazione ESEGUITA: cambiare il nome del parametro nella finta -- rossa."""
    assert_stessa_firma(ServiziStore.autorizzato, _Archivio.autorizzato,
                        nome="ServiziStore.autorizzato contro _Archivio")


# --- i tre ruoli ------------------------------------------------------------

@pytest.mark.parametrize("ruolo,legge,comanda,costruisce", [
    ("amministratore", True, True, True),
    ("utente", True, True, False),
    ("lettore", True, False, False),
])
def test_i_tre_ruoli_dicono_esattamente_questo(ruolo, legge, comanda, costruisce):
    """La tabella della spec §4, pinnata. `utente` e' quello che il
    proprietario ha descritto: «cosi' non gestisce automazioni e altro, quindi
    comanda».

    Mutazione ESEGUITA: dare `costruire` a «utente» -- rossa."""
    puo = canali.PUO[ruolo]

    assert puo["leggere"] is legge
    assert puo["comandare"] is comanda
    assert puo["costruire"] is costruisce


def test_ogni_ruolo_dichiarato_e_MAPPATO():
    """Un ruolo che esiste nel vocabolario ma che nessuno ha mappato non e'
    «permesso»: e' un ruolo su cui nessuno ha deciso.

    Mutazione: aggiungere un ruolo a `RUOLI` e non mapparlo -- rossa."""
    assert set(canali.PUO) == set(canali.RUOLI)
    for ruolo, puo in canali.PUO.items():
        for gesto in ("leggere", "comandare", "costruire"):
            assert isinstance(puo.get(gesto), bool), f"{ruolo} non dice {gesto}"


def test_i_ruoli_sono_gli_STESSI_in_tutte_e_due_le_case():
    """`canali` decide cosa concede un ruolo, `servizi` quali ruoli si possono
    approvare: due elenchi degli stessi valori divergerebbero al primo che se
    ne aggiunge uno, e il ruolo approvato non aprirebbe niente.

    Mutazione ESEGUITA: aggiungere un ruolo a uno solo dei due -- rossa."""
    from hiris.app.api import servizi

    assert tuple(canali.RUOLI) == tuple(servizi.RUOLI)


# --- il soffitto del metodo -------------------------------------------------

@pytest.mark.parametrize("metodo,passa", [
    ("GET", True), ("HEAD", True), ("OPTIONS", True),
    ("POST", False), ("PUT", False), ("PATCH", False), ("DELETE", False)])
def test_un_LETTORE_legge_e_basta(metodo, passa):
    """La porta di sviluppo, decisa dal proprietario: misurare la casa vera
    prima di progettare resta possibile, comandare no.

    Mutazione ESEGUITA: far passare qualunque metodo -- rossa."""
    assert canali.consente_metodo("lettore", metodo) is passa


def test_gli_altri_due_ruoli_scrivono():
    """Il contrario: un soffitto che negasse a tutti sarebbe il prodotto rotto,
    non messo in sicurezza.

    Mutazione: negare sempre -- rossa."""
    for ruolo in ("amministratore", "utente"):
        for metodo in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            assert canali.consente_metodo(ruolo, metodo) is True


def test_un_ruolo_sconosciuto_NEGA_tutto():
    """Il verso del dubbio anche qui.

    Mutazione: ripiegare su «amministratore» -- rossa."""
    for metodo in ("GET", "POST"):
        assert canali.consente_metodo("inventato", metodo) is False
