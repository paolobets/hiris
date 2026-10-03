"""Il sigillo dei segreti sui titoli d'errore che l'osservatore archivia.

**Perche' esiste** (Tappa 3, Task 0; trovato 10 del piano, anticipato dal
proprietario il 03/10/2026). `Watcher.watch_system` scrive nell'archivio la
prima riga del messaggio di una voce del registro di Home Assistant come
`title` della condizione `log:`. La chat legge lo stesso registro e lo sigilla
(`ToolDispatcher._sealed_log`); l'osservatore no. Un'integrazione che scrive
nel registro la password rifiutata la lasciava in chiaro nell'archivio
(`observations.db`, ventidue giorni), e da li' nel resoconto del giorno e
nella pagina dell'osservatore, che il titolo lo cita.

Le prove passano dalla porta di produzione: il sigillo si trova nella
cartella di Home Assistant come lo trova la chat, non viene iniettato.
"""
import os

import pytest

from hiris.app.home_space import redaction
from hiris.app.mind.facts import aggregate_day
from hiris.app.mind.store import ObservationsStore
from hiris.app.mind.watcher import Watcher

G = "2026-08-24"
MIDNIGHT = 1787522400.0   # 2026-08-23T22:00:00+00:00 = 24/08 00:00 +02:00
NINE_AM = MIDNIGHT + 9 * 3600
SECRET = "Zq9-segreto-77"


@pytest.fixture()
def house_with_secrets(tmp_path, monkeypatch):
    """Una cartella di Home Assistant finta, con un `secrets.yaml` vero, nel
    posto in cui `redaction.home_assistant_folder` la cerca."""
    folder = tmp_path / "config"
    folder.mkdir()
    (folder / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
    (folder / "secrets.yaml").write_text(f"nas_password: {SECRET}\n", encoding="utf-8")
    monkeypatch.setattr(redaction, "_FOLDERS", (str(folder),))
    return folder


@pytest.fixture()
def archive(tmp_path):
    store = ObservationsStore(os.path.join(str(tmp_path), "o.db"))
    yield store
    store.close()


def _log_entry(message: str) -> dict:
    return {"name": "homeassistant.components.synology_dsm", "level": "ERROR",
            "count": 1, "first_occurred": NINE_AM - 60,
            "source": ["components/synology_dsm/common.py", 112],
            "message": [message]}


def test_il_segreto_nel_titolo_non_entra_nell_archivio_ne_nel_resoconto(
        house_with_secrets, archive):
    """Il segreto sta DENTRO la frase, col punto a fine frase: la forma piu'
    comune di un registro. Ne' la riga dell'archivio ne' il resoconto del
    giorno (che la pagina dell'osservatore cita) lo contengono; il segnaposto
    c'e', e il resto della frase resta leggibile.

    Rossa prima della correzione: il titolo arrivava in chiaro nella riga.
    Mutazioni ESEGUITE, tutte rosse sulla prima asserzione, con la password
    in chiaro nel titolo archiviato: togliere la chiamata al sigillo in
    `watch_system`; passare al sigillo `None` invece di
    `redaction.home_assistant_seal()`; in `redaction.seal_free_text` sigillare
    solo il testo intero (niente riga, niente parola)."""
    watcher = Watcher(archive, now=lambda: NINE_AM)
    watcher.watch_system(problems=[], integrations=[],
                         log_entries=[_log_entry(f"login rifiutato per {SECRET}.")])

    rows = archive.readings(from_ts=MIDNIGHT, to_ts=MIDNIGHT + 86400, source="sistema")
    assert SECRET not in str(rows)
    assert rows[0]["title"] == "login rifiutato per <secret nas_password>."

    aggregate_day(store=archive, day=G, timezone="Europe/Rome")
    report = archive.report(G)
    assert SECRET not in str(report)
    assert "<secret nas_password>" in str(report)


def test_un_titolo_senza_segreti_resta_com_e(house_with_secrets, archive):
    """Il sigillo non cambia cio' che segreto non e': la fotografia di un
    archivio senza segreti nei titoli resta identica."""
    watcher = Watcher(archive, now=lambda: NINE_AM)
    watcher.watch_system(problems=[], integrations=[],
                         log_entries=[_log_entry("Timeout leggendo il NAS")])
    rows = archive.readings(from_ts=MIDNIGHT, to_ts=MIDNIGHT + 86400, source="sistema")
    assert rows[0]["title"] == "Timeout leggendo il NAS"


def test_senza_cartella_di_home_assistant_il_giro_non_si_ferma(tmp_path, monkeypatch,
                                                              archive):
    """Un sigillo che non si puo' costruire non ferma l'osservatore: si
    archivia come oggi (meno protezione, non nessun giro), come in chat."""
    monkeypatch.setattr(redaction, "_FOLDERS", (str(tmp_path / "manca"),))
    watcher = Watcher(archive, now=lambda: NINE_AM)
    assert watcher.watch_system(problems=[], integrations=[],
                                log_entries=[_log_entry("Timeout")]) == 1


# -- le righe gia' archiviate -------------------------------------------------
#
# Decisione del proprietario, 03/10/2026: i titoli archiviati PRIMA della
# correzione li sigilla l'add-on stesso all'avvio, e nel registro scrive solo
# quanti ne ha sigillati, mai i valori. L'aggancio e' `rebuild_conditions`, che
# l'avvio chiama una volta prima del primo giro.


def _archive_old_title(archive, title: str) -> None:
    """Una condizione `log:` scritta com'era prima della correzione: titolo in
    chiaro nella riga, e il resoconto del giorno che lo cita."""
    archive.record(quando_ts=NINE_AM, source="sistema",
                   subject="log:homeassistant.components.synology_dsm@common.py:112",
                   da=None, a="ERROR", domain="homeassistant.components.synology_dsm",
                   title=title, first_occurred=NINE_AM - 60)
    aggregate_day(store=archive, day=G, timezone="Europe/Rome")


def test_all_avvio_i_titoli_gia_archiviati_si_sigillano(house_with_secrets, archive,
                                                        caplog):
    """Riga dell'archivio e resoconto, gia' scritti in chiaro, escono
    sigillati dall'avvio; il registro dice quanti, e non contiene il segreto.

    Mutazioni ESEGUITE, ognuna rossa: togliere la chiamata da
    `rebuild_conditions` (il segreto resta nella riga); sigillare solo le
    righe e non i resoconti (il segreto resta nel resoconto); spostare in
    avanti `scritto_ts` dei resoconti sigillati (le impronte cambiano);
    scrivere nel registro i titoli letti prima del sigillo (il segreto e' nel
    registro)."""
    _archive_old_title(archive, f"login rifiutato per {SECRET}.")
    assert SECRET in str(archive.report(G))
    stamps_before = archive.report_stamps()

    with caplog.at_level("INFO", logger="hiris.app.mind.watcher"):
        Watcher(archive, now=lambda: NINE_AM).rebuild_conditions()

    rows = archive.readings(from_ts=MIDNIGHT, to_ts=MIDNIGHT + 86400, source="sistema")
    assert SECRET not in str(rows)
    assert rows[0]["title"] == "login rifiutato per <secret nas_password>."
    report = archive.report(G)
    assert SECRET not in str(report)
    assert "<secret nas_password>" in str(report)
    # Sigillare non e' rifare il giorno: l'istante del resoconto non cambia,
    # e il giro dell'analista non si sveglia per questo.
    assert archive.report_stamps() == stamps_before
    log = caplog.text
    assert SECRET not in log
    assert "1 titoli" in log and "1 resoconti" in log


def test_il_secondo_avvio_non_trova_niente_e_tace(house_with_secrets, archive, caplog):
    """Il sigillo di un testo gia' sigillato non lo cambia: dal secondo avvio
    non c'e' niente da sigillare, e il registro non dice niente.

    Mutazione ESEGUITA: scrivere nel registro anche quando i conti sono zero
    -- rossa."""
    _archive_old_title(archive, f"login rifiutato per {SECRET}.")
    Watcher(archive, now=lambda: NINE_AM).rebuild_conditions()
    caplog.clear()
    with caplog.at_level("INFO", logger="hiris.app.mind.watcher"):
        Watcher(archive, now=lambda: NINE_AM).rebuild_conditions()
    assert "titoli" not in caplog.text


def test_le_condizioni_si_ricostruiscono_anche_dopo_il_sigillo(house_with_secrets,
                                                               archive):
    """Il sigillo non disturba il compito vero di `rebuild_conditions`: la
    condizione aperta torna aperta, e il giro dopo non la riscrive."""
    _archive_old_title(archive, f"login rifiutato per {SECRET}.")
    watcher = Watcher(archive, now=lambda: NINE_AM)
    watcher.rebuild_conditions()
    entry = _log_entry(f"login rifiutato per {SECRET}.")
    entry["source"] = ["common.py", 112]
    assert watcher.watch_system(problems=[], integrations=[], log_entries=[entry]) == 0
