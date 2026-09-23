"""I giri automatici dichiarano quando sono passati a consumo (C-5c, 23/09/2026).

**Il difetto.** Il passaggio dal forfait al consumo si annunciava su chat,
promesse e osservatore. Su **analista, attuatore e ricette** finiva solo nel
registro — e quei tre girano da soli, di notte, senza nessuno davanti allo
schermo. I ~35.000 token dell'analista possono passare a consumo, e lo si
scopre dalla bolletta.

**Perché non basta alzare il livello del log.** Il registro non è un posto
dove il proprietario guarda: è il posto dove si guarda quando si sospetta già
qualcosa. La regola del 13/08 dice che il ripiego **si annuncia**, e annunciare
vuol dire in una pagina.

**Dove va, e perché lì.** Nell'archivio dei consumi, che è già «l'UNICA casa
di *quanto ho speso, e per cosa*», e quindi nella pagina Consumi: il ripiego è
un fatto sui soldi, e la pagina dei soldi è dove il proprietario va a
chiederselo. Una riga per `(giorno, agente, motivo)`: un agente che ripiega
duecento volte in un giorno e uno che ripiega una volta sono due storie
diverse, e una riga sola non le distinguerebbe.

**Un imbuto solo.** Tutte le porte passano da `steering.declare_downgrade`:
finché la dichiarazione era una riga di `logger` copiata in sei posti, tre
copie su sei sono rimaste indietro. È il difetto che `steering.py` dichiara
chiuso per la DOMANDA («chi risponde?») e che era ancora aperto per la
RISPOSTA («e allora dillo»).
"""
import pytest

from hiris.app import steering
from hiris.app.usage.store import UsageStore


@pytest.fixture()
def consumi(tmp_path):
    store = UsageStore(str(tmp_path / "consumi.db"))
    try:
        yield store
    finally:
        store.close()


def test_un_ripiego_si_scrive_e_si_rilegge(consumi):
    """Mutazione ESEGUITA: non scrivere -- rossa."""
    consumi.log_fallback("analista", "tetto giornaliero", now=1_758_000_000.0)

    righe = consumi.fallbacks()

    assert len(righe) == 1
    assert righe[0]["agent"] == "analista"
    assert righe[0]["reason"] == "tetto giornaliero"
    assert righe[0]["count"] == 1


def test_due_giri_dello_STESSO_agente_si_contano(consumi):
    """Duecento ripieghi in un giorno e uno solo sono due storie diverse: e'
    il numero, non il fatto, a dire se c'e' un problema.

    Mutazione ESEGUITA: sovrascrivere invece di sommare -- rossa."""
    consumi.log_fallback("analista", "tetto giornaliero", now=1_758_000_000.0)
    consumi.log_fallback("analista", "tetto giornaliero", now=1_758_000_060.0)

    righe = consumi.fallbacks()

    assert len(righe) == 1
    assert righe[0]["count"] == 2
    assert righe[0]["last_ts"] == 1_758_000_060.0


def test_agenti_diversi_restano_righe_diverse(consumi):
    """Sapere CHE si e' ripiegato non basta: serve sapere chi, perche' e' quello
    che si va a spegnere o a limitare.

    Mutazione ESEGUITA: chiave senza l'agente -- rossa."""
    consumi.log_fallback("analista", "tetto giornaliero", now=1_758_000_000.0)
    consumi.log_fallback("attuatore", "tetto giornaliero", now=1_758_000_000.0)

    assert {r["agent"] for r in consumi.fallbacks()} == {"analista", "attuatore"}


def test_motivi_diversi_restano_righe_diverse(consumi):
    """«manca il token» si risolve incollando un token; «tetto giornaliero» si
    risolve alzando un numero. Sommarli direbbe una cosa sola dove ce ne sono
    due, e nessuna delle due azioni.

    Mutazione ESEGUITA: chiave senza il motivo -- rossa."""
    consumi.log_fallback("analista", "tetto giornaliero", now=1_758_000_000.0)
    consumi.log_fallback("analista", "manca il token", now=1_758_000_000.0)

    assert len(consumi.fallbacks()) == 2


def test_l_imbuto_SCRIVE_e_non_solo_registra(consumi):
    """**Il reperto.** Tutte le porte passano di qui: una dichiarazione copiata
    in sei posti resta indietro in tre, ed e' successo.

    Mutazione ESEGUITA: `declare_downgrade` che scrive solo nel log -- rossa."""
    app = {"usage": consumi}

    steering.declare_downgrade(app, agent="analista", reason="tetto giornaliero",
                               now=1_758_000_000.0)

    assert consumi.fallbacks()[0]["agent"] == "analista"


class _Spia:
    """Un archivio che registra di essere stato chiamato, e nient'altro.

    Serve a distinguere «non si e' scritto» da «non si e' nemmeno provato»:
    con l'archivio VERO le due guardie -- quella dell'imbuto e quella dello
    store -- si coprono a vicenda, e togliendone una la prova resta verde.
    """

    def __init__(self):
        self.chiamate = []

    def log_fallback(self, agente, motivo, *, now):
        self.chiamate.append((agente, motivo, now))


def test_senza_MOTIVO_l_imbuto_non_TOCCA_nemmeno_l_archivio():
    """Il ponte spento non e' un ripiego: e' la configurazione scelta. Contarlo
    riempirebbe la pagina di righe che dicono «sto usando quello che hai
    scelto», e la renderebbe illeggibile proprio quando serve.

    **Questa prova e' nata verde e non sapeva fallire.** Guardava `ripieghi()`
    sull'archivio vero: togliendo la guardia dall'imbuto, la scrittura arrivava
    allo store, che ha la SUA guardia e la rifiutava lo stesso -- due difese
    che si coprono a vicenda e nessuna delle due dimostrabile. Adesso guarda se
    l'imbuto ha *provato*, che e' la proprieta' che gli appartiene.

    Mutazione ESEGUITA: togliere `if not reason` dall'imbuto -- rossa."""
    spia = _Spia()

    steering.declare_downgrade({"usage": spia}, agent="analista", reason="",
                               now=1_758_000_000.0)

    assert spia.chiamate == []


def test_ANCHE_l_archivio_da_solo_rifiuta_un_motivo_vuoto(consumi):
    """L'altra meta' della stessa coppia, provata dove vive: chi scrivesse
    nell'archivio senza passare dall'imbuto non deve poter sporcare la pagina.

    **Anche questa e' nata verde**, per lo stesso motivo al contrario: la prova
    passava dall'imbuto, che filtrava prima. Si chiama lo store diretto.

    Mutazione ESEGUITA: togliere `if not agente or not motivo` -- rossa."""
    consumi.log_fallback("analista", "", now=1_758_000_000.0)
    consumi.log_fallback("", "tetto giornaliero", now=1_758_000_000.0)

    assert consumi.fallbacks() == []


def test_senza_ARCHIVIO_l_imbuto_non_prova_e_non_si_LAMENTA(caplog):
    """L'add-on puo' essere partito a meta'. Una dichiarazione che facesse
    cadere il giro dell'analista sarebbe peggio del difetto che chiude.

    **Nata verde anche questa**: senza archivio la chiamata falliva dentro il
    `try`, che la inghiottiva -- quindi «non solleva» era vero con la guardia e
    senza. La differenza vera e' il RUMORE: senza guardia, ogni ripiego di una
    casa senza archivio scriverebbe un avviso di guasto che guasto non e', e
    il rumore sano seppellisce quello vero.

    Mutazione ESEGUITA: togliere `if store is None` -- rossa."""
    import logging

    with caplog.at_level(logging.WARNING, logger="hiris.app.steering"):
        steering.declare_downgrade({}, agent="analista",
                                   reason="tetto giornaliero",
                                   now=1_758_000_000.0)

    assert not [r for r in caplog.records if "non si e' potuto scrivere" in r.message]


def test_i_TRE_giri_automatici_passano_dall_imbuto():
    """La meta' che conta: non basta che l'imbuto esista, devono usarlo i tre
    che prima tacevano.

    **Questa prova guarda il SORGENTE** e non il comportamento, e lo dichiara:
    far girare analista, attuatore e ricette per davvero chiede una casa intera
    e un modello: una prova che li simulasse proverebbe la finta. Il rischio
    che resta e' una chiamata scritta e mai raggiunta, e lo copre la verifica
    dal vivo.

    Mutazione ESEGUITA: togliere la chiamata dall'analista -- rossa."""
    import pathlib
    sorgente = (pathlib.Path(__file__).resolve().parents[1]
                / "hiris/app/server.py").read_text(encoding="utf-8")

    for agente in ("analista", "attuatore", "ricette", "osservatore"):
        assert f'declare_downgrade(app, agent="{agente}"' in sorgente, (
            f"«{agente}» ripiega ancora in silenzio")
