"""L'ACCOPPIAMENTO di un servizio (decisione del proprietario, 22/09/2026).

Fino a stamattina i servizi esterni si dichiaravano in un campo di testo nelle
opzioni dell'add-on: `nome:ruolo:chiave`, una riga per servizio. Il proprietario
l'ha respinto, e per tre ragioni che il campo di testo non puo' risolvere:

- **ogni modifica riavvia l'add-on** -- aggiungere un servizio spegne la casa
  per dieci secondi;
- **revocare significa editare un blob di testo**, invece di un gesto;
- e soprattutto: **non si vede mai quando un servizio si presenta la prima
  volta**. L'autorizzazione e' gia' data prima che il servizio esista.

Il terzo punto e' quello che rende «by design» questo disegno, e non e' la
crittografia: e' che **il primo contatto e' un evento che il proprietario vede e
approva**.

**La chiave privata non viaggia mai.** La genera il servizio, sulla sua
macchina, e non esce da li'; a HIRIS arriva solo la pubblica. Cio' che il
proprietario approva non e' una chiave, e' un **codice breve** che HIRIS gli
mostra e che il servizio mostra a sua volta: se coincidono, sta accoppiando
QUEL servizio e non qualcun altro che si e' messo in mezzo.

Il codice si **deriva** dalla chiave pubblica e non e' casuale -- e' cosi' che il
servizio puo' mostrarlo senza scambiare nient'altro con HIRIS.
"""
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hiris.app.api.servizi import ServiziStore


def _coppia():
    privata = Ed25519PrivateKey.generate()
    return privata, base64.b64encode(
        privata.public_key().public_bytes_raw()).decode("ascii")


@pytest.fixture()
def archivio(tmp_path):
    store = ServiziStore(str(tmp_path / "servizi.db"))
    try:
        yield store
    finally:
        store.close()


def test_un_servizio_che_si_presenta_resta_IN_ATTESA(archivio):
    """Presentarsi non e' essere autorizzati. Se bastasse, il primo contatto
    sarebbe l'autorizzazione e non ci sarebbe niente da approvare.

    Mutazione ESEGUITA: nascere «autorizzato» -- rossa."""
    _, pubblica = _coppia()

    riga = archivio.presenta(nome="Retro Panel", chiave=pubblica,
                             indirizzo="192.168.1.31", now_ts=100.0)

    assert riga["stato"] == "in_attesa"
    assert riga["ruolo"] is None, "un ruolo lo da' il proprietario, non il servizio"


def test_il_CODICE_si_deriva_dalla_chiave_e_non_e_casuale(archivio):
    """Il servizio deve poter mostrare lo stesso codice senza chiedere niente a
    HIRIS: se fosse casuale servirebbe un secondo scambio, e quel secondo
    scambio sarebbe il punto in cui qualcuno si mette in mezzo.

    Mutazione ESEGUITA: coniare il codice a caso -- rossa."""
    _, pubblica = _coppia()

    primo = archivio.presenta(nome="a", chiave=pubblica, indirizzo="x", now_ts=100.0)
    calcolato = ServiziStore.codice(pubblica)

    assert primo["codice"] == calcolato
    assert len(primo["codice"]) == 4 and primo["codice"].isdigit()


def test_due_chiavi_diverse_danno_codici_diversi(archivio):
    """Un codice che non distingue non distingue niente.

    Mutazione: derivarlo dal nome invece che dalla chiave -- rossa."""
    _, una = _coppia()
    _, altra = _coppia()

    assert ServiziStore.codice(una) != ServiziStore.codice(altra)


def test_presentarsi_DUE_volte_non_crea_due_righe(archivio):
    """Un servizio che riprova mentre aspetta non deve riempire la pagina: e'
    lo stesso servizio, e la pagina deve restare leggibile.

    Mutazione ESEGUITA: inserire a ogni presentazione -- rossa."""
    _, pubblica = _coppia()

    archivio.presenta(nome="Retro Panel", chiave=pubblica, indirizzo="x", now_ts=100.0)
    archivio.presenta(nome="Retro Panel", chiave=pubblica, indirizzo="x", now_ts=200.0)

    assert len(archivio.elenco()) == 1


def test_approvare_da_il_RUOLO_e_la_specie(archivio):
    """Il ruolo viaggia con la credenziale (decisione del 21/09), e la specie
    dice se e' una macchina o un luogo -- due cose diverse nella cronaca.

    Mutazione: approvare senza chiedere il ruolo -- rossa."""
    _, pubblica = _coppia()
    archivio.presenta(nome="Retro Panel", chiave=pubblica, indirizzo="x", now_ts=100.0)

    archivio.approva(pubblica, ruolo="utente", specie="luogo", now_ts=200.0)

    riga = archivio.elenco()[0]
    assert riga["stato"] == "autorizzato"
    assert riga["ruolo"] == "utente"
    assert riga["specie"] == "luogo"


def test_un_ruolo_SCONOSCIUTO_non_si_approva(archivio):
    """I ruoli sono un insieme chiuso: una parola nuova arriverebbe da una
    rotta, e diventerebbe un permesso che nessuna pagina sa disegnare.

    Mutazione: accettare qualunque stringa -- rossa."""
    _, pubblica = _coppia()
    archivio.presenta(nome="x", chiave=pubblica, indirizzo="x", now_ts=100.0)

    with pytest.raises(ValueError):
        archivio.approva(pubblica, ruolo="capo", specie="luogo", now_ts=200.0)


def test_solo_un_servizio_AUTORIZZATO_si_riconosce(archivio):
    """Il cuore: finche' non l'hai approvato, la sua firma non apre niente.

    Mutazione ESEGUITA: riconoscere anche quelli in attesa -- rossa (il primo
    contatto sarebbe l'autorizzazione)."""
    _, pubblica = _coppia()
    archivio.presenta(nome="x", chiave=pubblica, indirizzo="x", now_ts=100.0)

    assert archivio.autorizzato(pubblica) is None

    archivio.approva(pubblica, ruolo="lettore", specie="integrazione", now_ts=200.0)

    riconosciuto = archivio.autorizzato(pubblica)
    assert riconosciuto["ruolo"] == "lettore"
    assert riconosciuto["nome"] == "x"


def test_REVOCARE_toglie_l_accesso_subito(archivio):
    """Un clic, e la chiave smette di valere. Non si aspetta niente: revocare e
    poi aspettare sarebbe revocare domani.

    Mutazione ESEGUITA: segnare la revoca senza che `autorizzato` la guardi --
    rossa."""
    _, pubblica = _coppia()
    archivio.presenta(nome="x", chiave=pubblica, indirizzo="x", now_ts=100.0)
    archivio.approva(pubblica, ruolo="utente", specie="luogo", now_ts=200.0)

    archivio.revoca(pubblica, now_ts=300.0)

    assert archivio.autorizzato(pubblica) is None
    assert archivio.elenco()[0]["stato"] == "revocato"


def test_un_servizio_REVOCATO_che_si_ripresenta_resta_revocato(archivio):
    """Altrimenti revocare non servirebbe a niente: basterebbe ripresentarsi
    per tornare in coda, e la revoca diventerebbe un fastidio invece che una
    decisione.

    Mutazione ESEGUITA: `stato='in_attesa'` nell'UPDATE della ripresentazione
    -- rossa. **Non basta togliere il ramo `elif`**: quell'UPDATE non tocca
    `stato`, quindi cambiare la sola condizione lascia la prova verde. La
    prima mutazione tentata era quella, ed era una mutazione che non mutava
    niente -- misurata, non supposta."""
    _, pubblica = _coppia()
    archivio.presenta(nome="x", chiave=pubblica, indirizzo="x", now_ts=100.0)
    archivio.approva(pubblica, ruolo="utente", specie="luogo", now_ts=200.0)
    archivio.revoca(pubblica, now_ts=300.0)

    archivio.presenta(nome="x", chiave=pubblica, indirizzo="x", now_ts=400.0)

    assert archivio.elenco()[0]["stato"] == "revocato"
    assert archivio.autorizzato(pubblica) is None


def test_una_presentazione_mai_guardata_SCADE(archivio):
    """Chiunque possa raggiungere HIRIS puo' presentarsi. Senza scadenza la
    pagina si riempie di rumore, e una pagina piena di rumore e' una pagina che
    non si guarda piu'.

    Le AUTORIZZATE non scadono: quelle le hai decise tu.

    Mutazione ESEGUITA: potare anche le autorizzate -- rossa (un servizio vivo
    sparirebbe da solo)."""
    _, in_attesa = _coppia()
    _, viva = _coppia()
    archivio.presenta(nome="rumore", chiave=in_attesa, indirizzo="x", now_ts=100.0)
    archivio.presenta(nome="vera", chiave=viva, indirizzo="x", now_ts=100.0)
    archivio.approva(viva, ruolo="utente", specie="luogo", now_ts=110.0)

    quante = archivio.pota(now_ts=100.0 + ServiziStore.ATTESA_S + 1)

    assert quante == 1
    assert [r["nome"] for r in archivio.elenco()] == ["vera"]


def test_l_elenco_dice_TUTTO_quello_che_serve_a_decidere(archivio):
    """La pagina deve poter mostrare: chi dice di essere, da dove, quando, il
    codice da confrontare. Senza «da dove» e «quando» l'approvazione e' un si'
    dato al buio.

    Mutazione: non riportare l'indirizzo -- rossa."""
    _, pubblica = _coppia()
    archivio.presenta(nome="Retro Panel", chiave=pubblica,
                      indirizzo="192.168.1.31", now_ts=100.0)

    riga = archivio.elenco()[0]
    for campo in ("nome", "indirizzo", "codice", "visto_ts", "stato"):
        assert riga.get(campo) is not None, campo


# --- la FINESTRA di accoppiamento -------------------------------------------
#
# Decisione del proprietario, 22/09/2026: **dieci minuti, e fuori si rifiuta**.
#
# La rotta di presentazione e' l'unica superficie che questo prodotto non puo'
# autenticare -- un servizio che non hai ancora approvato non ha modo di
# autenticarsi, ed e' tutto il punto dell'accoppiamento. Invece di difenderla
# (tetti, limiti di ritmo, scadenze) si e' scelto di **non farla esistere**:
# esiste solo nei dieci minuti in cui l'hai aperta tu.
#
# Una difesa permanente invecchia; una porta chiusa no.

from hiris.app.api import servizi as mod


def test_la_finestra_nasce_CHIUSA():
    """Se nascesse aperta, «si apre quando lo dici tu» sarebbe falso al primo
    avvio -- e l'add-on riparte spesso.

    Mutazione ESEGUITA: nascere aperta -- rossa."""
    finestra = {}

    assert mod.finestra_aperta(finestra, adesso=100.0) is False


def test_aprirla_la_tiene_aperta_DIECI_minuti():
    """Il numero e' del proprietario, e sta scritto dove si applica.

    Mutazione: ignorare la durata -- rossa."""
    finestra = {}
    mod.apri_finestra(finestra, adesso=100.0)

    assert mod.finestra_aperta(finestra, adesso=100.0 + mod.FINESTRA_S - 1) is True
    assert mod.finestra_aperta(finestra, adesso=100.0 + mod.FINESTRA_S + 1) is False
    assert mod.FINESTRA_S == 600.0


def test_si_puo_CHIUDERE_prima():
    """Accoppiato il servizio, la finestra non deve restare aperta per i minuti
    che avanzano: chiuderla e' un gesto, e il gesto c'e'.

    Mutazione: non chiudere davvero -- rossa."""
    finestra = {}
    mod.apri_finestra(finestra, adesso=100.0)

    mod.chiudi_finestra(finestra)

    assert mod.finestra_aperta(finestra, adesso=101.0) is False


def test_quanto_manca_si_puo_DIRE():
    """La pagina deve poter mostrare il tempo che resta: una finestra che si
    apre senza dire quanto dura costringe a indovinare.

    Mutazione: tornare sempre zero -- rossa."""
    finestra = {}
    mod.apri_finestra(finestra, adesso=100.0)

    assert mod.finestra_resta(finestra, adesso=100.0) == pytest.approx(600.0)
    assert mod.finestra_resta(finestra, adesso=1000.0) == 0.0
    assert mod.finestra_resta({}, adesso=100.0) == 0.0


def test_il_contenitore_della_finestra_nasce_con_l_app():
    """Scrivere in `app[...]` a richiesta gia' servita e' deprecato in aiohttp 3
    e un errore in aiohttp 4 -- la stessa ragione dei contatori, dei ruoli, dei
    canali visti e delle credenziali.

    Mutazione: crearlo alla prima apertura -- rossa."""
    app = {}
    mod.prepara_finestra(app)

    assert app["finestra_servizi"] == {}
