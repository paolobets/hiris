"""La pulizia totale del 23/10/2026: quattro archivi messi da parte, una volta.

**La decisione del proprietario**, 22/10/2026: ripartire con osservazioni,
sapere, chat e ricordi vuoti (Fase P dello sprint «Il giro snello e il Brain
leggibile»). Il 23/10/2026 ha scelto che lo faccia HIRIS all'avvio, perche'
dal suo PC non si arriva a `/data` dell'add-on.

Ogni prova qui lavora su archivi SQLite veri, in WAL, con scritture ancora nel
diario: e' il caso della casa, e copiare il solo `.db` le perderebbe.

**A scadenza**: escono con `conservazione.accantona_archivi`, nella release
dopo.
"""
import json
import pathlib
import sqlite3
from collections import namedtuple

import pytest

from hiris.app import conservazione
from hiris.app.conservazione import ARCHIVI_ACCANTONATI, CARTELLA_ACCANTONATI, accantona_archivi

_RIGHE = {"osservazioni.db": 5, "sapere.db": 3, "chat_history.db": 7,
          "memoria.db": 2}


def _archivio(cartella: pathlib.Path, nome: str, righe: int) -> sqlite3.Connection:
    """Un archivio in WAL con le righe ancora nel diario: la connessione resta
    APERTA e senza checkpoint, cosi' il `.db` da solo non le contiene."""
    conn = sqlite3.connect(cartella / nome)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE voci (id INTEGER PRIMARY KEY, testo TEXT)")
    conn.executemany("INSERT INTO voci (testo) VALUES (?)",
                     [(f"{nome} {i}",) for i in range(righe)])
    conn.commit()
    return conn


@pytest.fixture
def casa(tmp_path):
    connessioni = [_archivio(tmp_path, nome, n) for nome, n in _RIGHE.items()]
    estraneo = sqlite3.connect(tmp_path / "promesse.db")
    estraneo.execute("CREATE TABLE estranea (x)")
    estraneo.commit()
    estraneo.close()
    (tmp_path / "options.json").write_text('{"theme": "auto"}', encoding="utf-8")
    assert (tmp_path / "memoria.db-wal").stat().st_size > 0, (
        "la prova non mette righe nel diario: non guarderebbe il WAL")
    yield tmp_path
    for conn in connessioni:
        conn.close()


def _righe(percorso: pathlib.Path) -> int:
    conn = sqlite3.connect(percorso)
    try:
        return conn.execute("SELECT COUNT(*) FROM voci").fetchone()[0]
    finally:
        conn.close()


def test_le_copie_sono_fedeli_e_gli_originali_se_ne_vanno(casa):
    """Il caso della casa. Mutazione ESEGUITA: copiare il `.db` con
    `shutil.copy2` invece dell'API di backup -- rossa, la copia perde le righe
    che stavano nel diario."""
    accantona_archivi(str(casa), attiva=True)

    cartella = casa / CARTELLA_ACCANTONATI
    for nome, n in _RIGHE.items():
        assert _righe(cartella / nome) == n, nome
        for compagno in ("", "-wal", "-shm"):
            assert not (casa / (nome + compagno)).exists(), nome + compagno
    manifesto = json.loads((cartella / "MANIFESTO.json").read_text(encoding="utf-8"))
    assert {n: a["righe"]["voci"] for n, a in manifesto["archivi"].items()} == _RIGHE


def test_nient_altro_di_data_si_tocca(casa):
    prima = (casa / "promesse.db").read_bytes()

    accantona_archivi(str(casa), attiva=True)

    assert (casa / "promesse.db").read_bytes() == prima
    assert (casa / "options.json").read_text(encoding="utf-8") == '{"theme": "auto"}'
    assert set(_RIGHE) == set(ARCHIVI_ACCANTONATI)


def test_spenta_non_fa_niente(casa):
    accantona_archivi(str(casa), attiva=False)

    assert not (casa / CARTELLA_ACCANTONATI).exists()
    assert all((casa / nome).exists() for nome in ARCHIVI_ACCANTONATI)


def test_fatta_una_volta_non_si_ripete(casa):
    """L'opzione puo' restare accesa: gli archivi rinati dopo la pulizia non
    si toccano. Mutazione ESEGUITA: togliere il controllo del manifesto --
    rossa, il secondo avvio (con la cartella che c'e' gia') rifaceva la
    rimozione."""
    accantona_archivi(str(casa), attiva=True)
    rinato = _archivio(casa, "memoria.db", 1)
    rinato.close()

    accantona_archivi(str(casa), attiva=True)

    assert _righe(casa / "memoria.db") == 1
    assert _righe(casa / CARTELLA_ACCANTONATI / "memoria.db") == _RIGHE["memoria.db"]


def test_una_copia_che_non_torna_lascia_tutti_gli_originali(casa, monkeypatch):
    """Tutto o niente. Mutazione ESEGUITA: togliere il confronto delle righe
    in `_copia_verificata` -- rossa, gli originali sparivano con una copia
    monca."""
    vero = conservazione._conta_righe
    chiamate = []

    def monca(conn):
        righe = vero(conn)
        chiamate.append(1)
        # Due letture per archivio, l'originale e poi la copia: la sesta e'
        # la copia di `chat_history.db`, il terzo. Le manca una riga.
        if len(chiamate) == 6:
            righe = {t: r - 1 for t, r in righe.items()}
        return righe

    monkeypatch.setattr(conservazione, "_conta_righe", monca)
    accantona_archivi(str(casa), attiva=True)

    assert not (casa / CARTELLA_ACCANTONATI).exists()
    assert not (casa / ".accantonati-in-corso").exists()
    for nome, n in _RIGHE.items():
        assert _righe(casa / nome) == n, nome


def test_senza_spazio_non_tocca_niente(casa, monkeypatch):
    Uso = namedtuple("Uso", "total used free")
    monkeypatch.setattr(conservazione.shutil, "disk_usage",
                        lambda _percorso: Uso(10, 10, 0))

    accantona_archivi(str(casa), attiva=True)

    assert not (casa / CARTELLA_ACCANTONATI).exists()
    assert all((casa / nome).exists() for nome in ARCHIVI_ACCANTONATI)


def test_un_avvio_interrotto_dopo_le_copie_si_completa(casa, monkeypatch):
    """L'avvio si ferma fra il rename e il manifesto: le copie ci sono e sono
    verificate, gli originali anche. Il giro dopo li toglie e scrive il
    manifesto, invece di rifare le copie sopra quelle buone."""
    monkeypatch.setattr(conservazione, "_togli_originali",
                        lambda _d: (_ for _ in ()).throw(OSError("spento")))
    accantona_archivi(str(casa), attiva=True)
    assert (casa / CARTELLA_ACCANTONATI).is_dir()
    assert not (casa / CARTELLA_ACCANTONATI / "MANIFESTO.json").exists()
    monkeypatch.undo()

    accantona_archivi(str(casa), attiva=True)

    cartella = casa / CARTELLA_ACCANTONATI
    assert (cartella / "MANIFESTO.json").exists()
    assert not any((casa / nome).exists() for nome in ARCHIVI_ACCANTONATI)
    assert _righe(cartella / "osservazioni.db") == _RIGHE["osservazioni.db"]


def test_un_archivio_che_non_c_e_non_ferma_gli_altri(tmp_path):
    """La casa di chi installa oggi: nessun archivio. La pulizia si segna fatta
    e non fa rumore di errore."""
    conn = _archivio(tmp_path, "sapere.db", 3)
    conn.close()

    accantona_archivi(str(tmp_path), attiva=True)

    manifesto = json.loads(
        (tmp_path / CARTELLA_ACCANTONATI / "MANIFESTO.json").read_text(encoding="utf-8"))
    assert list(manifesto["archivi"]) == ["sapere.db"]
    assert not (tmp_path / "sapere.db").exists()


@pytest.mark.asyncio
async def test_l_avvio_la_fa_prima_che_un_archivio_si_apra(casa):
    """L'app avviata davvero, con l'opzione accesa: ogni archivio rinasce
    vuoto accanto alla copia. Se la pulizia girasse dopo l'apertura di un
    archivio, il file aperto verrebbe tolto da sotto all'archivio vivo e non
    rinascerebbe. Mutazione ESEGUITA: spostare la chiamata dopo
    `_open_knowledge` in `startup._on_startup` -- rossa, `sapere.db` manca."""
    from tests._avvio import started_with

    async with started_with(casa, {"HIRIS_PULIZIA_TOTALE": "true"}):
        for nome in ARCHIVI_ACCANTONATI:
            assert (casa / nome).exists(), f"{nome} non e' rinato"
            conn = sqlite3.connect(casa / nome)
            try:
                tabelle = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'")}
            finally:
                conn.close()
            assert "voci" not in tabelle, f"{nome} porta ancora le righe di prima"
            assert _righe(casa / CARTELLA_ACCANTONATI / nome) == _RIGHE[nome]
