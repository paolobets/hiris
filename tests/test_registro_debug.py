"""Il `debug` non porta il prompt nel registro (reperto C-2, 23/09/2026).

**Perché è un reperto, e perché conta di più distribuendo.** `main.py`
impostava il livello sul logger **radice**, senza pavimento per le librerie di
terze parti. Gli SDK installati (`anthropic`, `openai`, `httpx`) stampano in
`debug` le opzioni della richiesta, e quelle opzioni contengono **il corpo
intero**: prompt di sistema, nucleo della casa, ricordi, conversazione.

Il livello `debug` è **a un clic** nella pagina del Supervisor, e il registro è
esattamente il file che si incolla in una segnalazione. In un prodotto
distribuito «metti debug e mandami il log» è la prima cosa che si chiede a un
utente: il danno non è ipotetico, è la procedura normale di assistenza.

**La chiave non ci finisce** — le intestazioni di autenticazione non passano da
lì: il danno è la riservatezza dei dati della casa, non la credenziale.

**Cosa NON cambia**: il `debug` di HIRIS resta `debug`. Si mette un pavimento
alle librerie, non al prodotto — chi accende il debug lo accende per vedere cosa
fa HIRIS, non per leggere come `httpx` serializza un corpo.
"""
import logging

from hiris.app import main as main_module


def _livelli(monkeypatch, richiesto: str) -> dict:
    """Applica la configurazione dei registri e torna i livelli risultanti."""
    monkeypatch.setenv("LOG_LEVEL", richiesto)
    for nome in main_module.LIBRERIE_RUMOROSE:
        logging.getLogger(nome).setLevel(logging.NOTSET)
    logging.getLogger().setLevel(logging.WARNING)

    main_module.prepara_registri()

    return {nome: logging.getLogger(nome).getEffectiveLevel()
            for nome in main_module.LIBRERIE_RUMOROSE}


def test_in_DEBUG_le_librerie_restano_sopra_il_debug(monkeypatch):
    """**Il reperto C-2.** Gli SDK in `debug` stampano il corpo della
    richiesta, e il corpo e' la casa.

    Mutazione ESEGUITA: togliere il pavimento -- rossa."""
    livelli = _livelli(monkeypatch, "debug")

    for nome, livello in livelli.items():
        assert livello > logging.DEBUG, (
            f"«{nome}» in debug stampa il corpo della richiesta nel registro")


def test_ma_HIRIS_in_debug_resta_in_DEBUG(monkeypatch):
    """La contropartita, e non e' secondaria: chi accende il debug lo accende
    per vedere cosa fa HIRIS. Un pavimento che spegnesse anche il nostro
    renderebbe l'opzione inutile, e la si toglierebbe.

    Mutazione ESEGUITA: alzare il livello della radice -- rossa."""
    _livelli(monkeypatch, "debug")

    assert logging.getLogger("hiris.app.server").getEffectiveLevel() == logging.DEBUG


def test_l_elenco_delle_librerie_copre_i_CLIENT_che_parlano_coi_modelli(monkeypatch):
    """Non un elenco qualunque: i tre che portano il corpo sono i client HTTP e
    gli SDK dei fornitori. Se uno di loro uscisse dall'elenco, il buco
    tornerebbe da quella porta sola.

    Mutazione: togliere `httpx` -- rossa."""
    for atteso in ("httpx", "httpcore", "anthropic", "openai", "aiohttp"):
        assert atteso in main_module.LIBRERIE_RUMOROSE, (
            f"«{atteso}» parla coi modelli e non ha pavimento")


def test_senza_debug_le_librerie_non_hanno_un_livello_PROPRIO(monkeypatch):
    """Il caso normale: senza debug non c'e' niente da limitare.

    **Questa prova e' nata verde e non sapeva fallire**, e guardava la cosa
    sbagliata: chiedeva il livello EFFICACE, che in `info` vale `INFO` sia che
    la libreria segua la radice sia che sia stata inchiodata a `INFO`. I due
    casi sono diversi, e il secondo fa danno in `warning`: una libreria
    inchiodata a `INFO` continuerebbe a stampare i suoi avvisi mentre il
    proprietario ha chiesto silenzio.

    La proprieta' vera e' **che non le si tocchi**: senza debug la libreria non
    ha un livello suo e segue la radice, qualunque essa sia.

    Mutazione ESEGUITA: applicare il pavimento sempre (`if True`) -- rossa."""
    _livelli(monkeypatch, "info")

    for nome in main_module.LIBRERIE_RUMOROSE:
        assert logging.getLogger(nome).level == logging.NOTSET, (
            f"«{nome}» e' stato inchiodato anche senza debug: in «warning» "
            "continuerebbe a parlare")


def test_in_WARNING_le_librerie_TACCIONO_come_chiesto(monkeypatch):
    """Il danno concreto della mutazione qui sopra, detto dal verso dell'uso:
    chi mette `warning` vuole silenzio, e deve ottenerlo anche dalle librerie.

    Mutazione ESEGUITA: applicare il pavimento sempre -- rossa."""
    livelli = _livelli(monkeypatch, "warning")

    for nome, livello in livelli.items():
        assert livello == logging.WARNING, (
            f"«{nome}» parla a INFO mentre e' stato chiesto WARNING")


def test_un_livello_INVENTATO_non_fa_cadere_l_avvio(monkeypatch):
    """`LOG_LEVEL` viene da un'opzione dell'add-on: prima o poi qualcuno ci
    scrive qualcosa che non e' un livello, e l'add-on deve partire lo stesso.

    Mutazione: `getattr` senza ripiego -- rossa."""
    _livelli(monkeypatch, "verboso")

    assert logging.getLogger().getEffectiveLevel() == logging.INFO
