"""Quanto scrive l'osservatore, al giorno.

**Perche' e' un numero del prodotto e non una diagnostica.** La Fetta 1 della
spec dei tre attori promette **-83%** di righe grezze -- da 29.227 a 4.951 al
giorno, misurate sulla casa vera il 10/09/2026 -- e la promessa e' la
contropartita onesta dello scope: si guarda meno, e questo e' quanto costa
cio' che si guarda. Verificato l'11/09: **nessuna porta lo esponeva**.
`readings()` esiste, ma da fuori non c'era modo di contare le righe di una
giornata senza tirarsele giu' tutte -- 14.600 righe per sapere che sono
14.600.

**Si contano in SQL, non in Python.** `readings()` ha un tetto di 200.000
righe: contare la lunghezza della lista che torna darebbe un numero giusto
finche' il tetto non scatta, e **sbagliato in silenzio** proprio sulla
giornata piu' rumorosa -- quella che si guarda per capire se il filtro
funziona.
"""
import os

import pytest

from hiris.app.mind.store import ObservationsStore

GIORNO = 86400.0


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


def _scrivi(archivio, quando, soggetto="sensor.x", fonte="entita"):
    archivio.record(quando_ts=quando, source=fonte, subject=soggetto,
                    da="1", a="2", device_class=None, state_class=None,
                    source_type=None, friendly_name=None)


def test_su_un_archivio_vuoto_si_conta_zero_non_niente(archivio):
    """Zero righe e' un fatto misurato: la giornata c'e' stata e non ha
    prodotto niente. Diverso da «non lo so», che questa porta non dice mai
    perche' la domanda le arriva sempre."""
    assert archivio.readings_count(from_ts=0.0, to_ts=GIORNO) == 0


def test_si_contano_le_righe_della_finestra_e_solo_quelle(archivio):
    """La finestra e' semi-aperta come in `readings()`: `from_ts` incluso,
    `to_ts` escluso. Due estremi inclusivi conterebbero due volte il cambio
    di mezzanotte, e i giorni adiacenti non tornerebbero mai.

    Mutazione che la uccide: `<=` al posto di `<` sull'estremo destro.
    """
    _scrivi(archivio, 999.0)          # prima
    _scrivi(archivio, 1000.0)         # dentro, sul bordo incluso
    _scrivi(archivio, 1500.0)         # dentro
    _scrivi(archivio, 2000.0)         # sul bordo escluso: fuori

    assert archivio.readings_count(from_ts=1000.0, to_ts=2000.0) == 2


def test_si_puo_contare_una_sola_famiglia(archivio):
    """Le entita' e le condizioni di sistema sono due volumi diversi con due
    storie diverse: sulla casa vera le seconde sono poche centinaia su 22
    giorni, le prime centinaia di migliaia. Sommarle nasconderebbe il -83%,
    che riguarda le entita'."""
    _scrivi(archivio, 1000.0, "sensor.x", "entita")
    _scrivi(archivio, 1100.0, "sensor.y", "entita")
    _scrivi(archivio, 1200.0, "problema:sonos.x", "sistema")

    assert archivio.readings_count(from_ts=0.0, to_ts=GIORNO) == 3
    assert archivio.readings_count(from_ts=0.0, to_ts=GIORNO, source="entita") == 2
    assert archivio.readings_count(from_ts=0.0, to_ts=GIORNO, source="sistema") == 1


def test_il_conto_non_ha_il_tetto_di_readings(archivio):
    """**Il difetto che questa porta esiste per non avere.** `readings()`
    tronca a 200.000 righe: contare la lunghezza della sua lista darebbe il
    numero giusto finche' il tetto non scatta, e uno sbagliato in silenzio
    proprio sulla giornata piu' rumorosa -- quella che si guarda per capire
    se il filtro funziona.

    Qui il tetto e' finto (tre righe, limite due) perche' la prova resti
    veloce: la proprieta' e' la stessa, e con 200.001 righe vere non
    girerebbe mai.

    Mutazione che la uccide: implementare `readings_count` come
    `len(self.readings(...))`.
    """
    for i in range(3):
        _scrivi(archivio, 1000.0 + i)

    assert len(archivio.readings(from_ts=0.0, to_ts=GIORNO, limit=2)) == 2
    assert archivio.readings_count(from_ts=0.0, to_ts=GIORNO) == 3
