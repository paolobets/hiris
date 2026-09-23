"""`vault.db` si decide, non si annuncia (reperto C-6d, 23/09/2026).

Il codice diceva, in una riga informativa all'avvio, che se quel file non è
vuoto contiene **«DATI PERSONALI IN CHIARO»** — la mappa PII↔token della
pseudonimizzazione, la cui cifratura a riposo è stata rinviata e mai fatta —
che nessun codice lo legge più, e che cancellarlo è sicuro.

**Una riga informativa fra centinaia di righe di avvio non è un modo di dire
una cosa a una persona.** E la persona non può decidere: per decidere
dovrebbe aprire un file SQLite dentro il contenitore dell'add-on.

Quindi HIRIS decide, ed è la decisione facile: un file che **nessuno legge**,
che **nessuna interfaccia svuota** e che contiene dati personali in chiaro è
solo un rischio. Si cancella, e si dice **cosa** è stato cancellato — non
«ho fatto pulizia», ma il nome del file, cosa conteneva e perché non serviva
più.
"""
import logging
import pathlib
import sqlite3

from hiris.app.server import decidi_vault


def _vault(tmp_path, *, righe: int) -> pathlib.Path:
    percorso = tmp_path / "vault.db"
    conn = sqlite3.connect(percorso)
    conn.execute("CREATE TABLE pii (token TEXT, value TEXT)")
    for i in range(righe):
        conn.execute("INSERT INTO pii VALUES (?,?)", (f"t{i}", f"Mario Rossi {i}"))
    conn.commit()
    conn.close()
    return percorso


def test_un_vault_con_dentro_qualcosa_si_CANCELLA(tmp_path):
    """**Il reperto.** Prima restava sul disco, ed entrava nei backup.

    Mutazione ESEGUITA: annunciare invece di cancellare -- rossa."""
    percorso = _vault(tmp_path, righe=3)

    decidi_vault(str(tmp_path))

    assert not percorso.exists()


def test_e_si_dice_COSA_e_stato_cancellato(tmp_path, caplog):
    """Cancellare dati di un utente in silenzio e' proibito dalle fondamenta di
    questo progetto. Non si dice «ho fatto pulizia»: si dice il nome del file,
    quante righe conteneva e perche' non serviva piu'.

    Mutazione ESEGUITA: cancellare senza dirlo -- rossa."""
    _vault(tmp_path, righe=3)

    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        decidi_vault(str(tmp_path))

    detto = " ".join(r.getMessage() for r in caplog.records)
    assert "vault.db" in detto
    assert "3" in detto, "non dice quanto conteneva"


def test_un_vault_VUOTO_se_ne_va_in_silenzio(tmp_path, caplog):
    """Non c'era niente dentro: non c'e' niente da raccontare, e un avviso
    allarmerebbe per nulla. Il rumore sano seppellisce quello vero.

    Mutazione ESEGUITA: avvisare sempre -- rossa."""
    percorso = _vault(tmp_path, righe=0)

    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        decidi_vault(str(tmp_path))

    assert not percorso.exists()
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_senza_il_file_non_succede_niente(tmp_path):
    """Il caso normale, che e' quello di quasi tutte le installazioni.

    Mutazione: sollevare quando il file non c'e' -- rossa."""
    decidi_vault(str(tmp_path))


def test_un_file_ILLEGGIBILE_non_fa_cadere_l_avvio(tmp_path, caplog):
    """Un file corrotto, o un permesso mancante: l'add-on deve partire lo
    stesso. Questa e' igiene, non una condizione di funzionamento.

    Mutazione ESEGUITA: togliere la rete -- rossa."""
    percorso = tmp_path / "vault.db"
    percorso.write_bytes(b"non sono un database")

    decidi_vault(str(tmp_path))
