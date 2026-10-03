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
