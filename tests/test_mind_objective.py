"""L'obiettivo: testo libero, datato, e con una storia che conta.

**Perche' la storia non e' un di piu'** (spec §11, conseguenza 1). Se l'obiettivo
cambia, i resoconti scritti prima rispondono a un'altra domanda: chi legge
trenta giorni di misure deve **sapere** che al giorno 20 la domanda e'
cambiata, o legge una tendenza dove c'e' un cambio di domanda.

**Perche' vive nell'archivio dell'osservatore** e non in uno suo: e' cio' che
governa quel che l'osservatore raccoglie, e il resoconto giornaliero dovra'
mettere accanto a ogni giornata l'obiettivo che valeva allora. Stesso file,
una query sola -- e `ATTACH` in questo prodotto non compare mai.
"""
import os

import pytest

from hiris.app.mind.store import ObservationsStore

DEFAULT = "ottimizzare la casa e renderla confortevole"


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


def test_il_default_esiste_gia_e_non_si_inventa(archivio):
    """Su una casa appena installata l'obiettivo non e' vuoto: e' quello deciso
    dal proprietario il 25/08/2026. Un obiettivo vuoto renderebbe lo scope una
    domanda senza criterio -- e l'osservatore la porrebbe lo stesso, al
    modello, senza dire rispetto a cosa.

    Mutazione che la uccide: tornare `None` finche' nessuno ha scritto niente.
    """
    assert archivio.objective()["testo"] == DEFAULT
    assert archivio.objective()["scritto_ts"] is None


def test_scrivere_un_obiettivo_lo_data(archivio):
    archivio.set_objective("tenere la casa calda e spendere poco", when_ts=1000.0)

    corrente = archivio.objective()
    assert corrente["testo"] == "tenere la casa calda e spendere poco"
    assert corrente["scritto_ts"] == 1000.0


def test_la_storia_conserva_quello_di_prima(archivio):
    """**Il punto per cui questa tabella esiste.** Non basta sapere qual e'
    l'obiettivo adesso: serve sapere quale valeva il giorno che si sta
    leggendo.

    Mutazione che la uccide: sostituire invece di accodare -- la storia
    avrebbe una riga sola e nessun resoconto potrebbe piu' dire a quale
    domanda rispondeva.
    """
    archivio.set_objective("primo", when_ts=1000.0)
    archivio.set_objective("secondo", when_ts=2000.0)

    storia = archivio.objective_history()
    assert [v["testo"] for v in storia] == ["secondo", "primo"]
    assert archivio.objective()["testo"] == "secondo"


def test_quale_obiettivo_valeva_quel_giorno(archivio):
    """La domanda che il resoconto porra' a ogni giornata. Un giorno PRIMA del
    primo obiettivo scritto vale il default: la casa c'era comunque, e
    l'osservatore guardava.

    Mutazione che la uccide: tornare sempre l'obiettivo corrente -- trenta
    giorni di misure sembrerebbero rispondere tutti alla stessa domanda.
    """
    archivio.set_objective("primo", when_ts=1000.0)
    archivio.set_objective("secondo", when_ts=2000.0)

    assert archivio.objective_at(500.0)["testo"] == DEFAULT
    assert archivio.objective_at(1500.0)["testo"] == "primo"
    assert archivio.objective_at(2500.0)["testo"] == "secondo"
    assert archivio.objective_at(2000.0)["testo"] == "secondo"   # il confine e' incluso


def test_riscrivere_lo_stesso_testo_non_sporca_la_storia(archivio):
    """Salvare due volte la stessa frase non e' un cambio d'obiettivo: se lo
    fosse, la pagina che mostra «da quando guardo questa cosa» direbbe che tutto
    e' cambiato ogni volta che qualcuno ha premuto «salva» senza toccare
    niente."""
    archivio.set_objective("uguale", when_ts=1000.0)
    archivio.set_objective("uguale", when_ts=2000.0)

    assert len(archivio.objective_history()) == 1
    assert archivio.objective()["scritto_ts"] == 1000.0


def test_un_obiettivo_vuoto_non_cancella_quello_che_c_era(archivio):
    """Stessa dottrina del sistema di riferimento: un campo svuotato per errore
    non deve poter togliere l'unica manopola del prodotto. Si rifiuta, e chi
    chiama lo sa."""
    archivio.set_objective("qualcosa", when_ts=1000.0)

    assert archivio.set_objective("   ", when_ts=2000.0) is False
    assert archivio.objective()["testo"] == "qualcosa"


def test_senza_istante_si_usa_l_orologio(archivio):
    """Il ramo che nessuna delle prove sopra esercitava, perche' tutte passano
    `when_ts`: in produzione l'istante non lo passa nessuno -- lo scrive chi
    salva dalla pagina -- e un `NameError` qui lascerebbe il proprietario senza
    poter cambiare l'unica manopola del prodotto.

    Mutazione che la uccide: togliere l'import dell'orologio."""
    import time

    prima = time.time()
    assert archivio.set_objective("scritto adesso") is True
    scritto = archivio.objective()["scritto_ts"]

    assert scritto is not None
    assert prima - 1 <= scritto <= time.time() + 1
