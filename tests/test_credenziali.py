"""Le credenziali EFFIMERE del ponte (spec 2026-09-21 §5, ingresso 7).

Il ponte non e' un canale di rete: gira dentro il container. Dargli una coppia
di chiavi a vita lunga rimetterebbe una chiave nella riga di comando del
sottoprocesso -- il reperto C-3 del registro dei rischi, leggibile per trecento
secondi da qualunque processo. Per lui la risposta e' un'altra: **una
credenziale che vale per quel turno e per niente altro**.

Due portatori, e sono meno esotici di come sembrano:

- il **worker**, che e' HIRIS che chiama se stesso su `127.0.0.1` per prendere
  e consegnare i turni;
- il **sottoprocesso `claude`**, che chiama `/api/mcp` con cio' che gli arriva
  in `--mcp-config`.

Entrambi vivono quanto un turno. Quindi la credenziale muore col turno, e cio'
che resta nella riga di comando dopo non apre piu' niente.

**Perche' non si riusa il segreto condiviso.** Quello e' uno solo per tutti i
portatori, vive in `/data`, finisce nei backup di Home Assistant in chiaro, e
chi lo legge una volta e' tutti per sempre. Una credenziale effimera non si
mette in un backup: quando il backup si apre, e' gia' scaduta.
"""

import pytest

from hiris.app.api import credenziali


@pytest.fixture()
def vive():
    contenitore = {}
    return contenitore


def test_una_credenziale_coniata_si_riconosce(vive):
    """Mutazione: non registrarla al conio -- rossa."""
    segreto = credenziali.conia(vive, mestiere="ponte", durata_s=60, adesso=100.0)

    riconosciuta = credenziali.riconosci(vive, segreto, adesso=101.0)

    assert riconosciuta is not None
    assert riconosciuta["mestiere"] == "ponte"


def test_una_credenziale_SCADUTA_non_vale_piu(vive):
    """E' tutto il punto: cio' che resta nella riga di comando dopo il turno
    non deve aprire niente.

    Mutazione ESEGUITA: non guardare la scadenza -- rossa."""
    segreto = credenziali.conia(vive, mestiere="ponte", durata_s=60, adesso=100.0)

    assert credenziali.riconosci(vive, segreto, adesso=100.0 + 61) is None


def test_un_segreto_MAI_coniato_non_vale(vive):
    """Mutazione: tornare un mestiere predefinito quando non si trova -- rossa."""
    assert credenziali.riconosci(vive, "inventato", adesso=100.0) is None
    assert credenziali.riconosci(vive, "", adesso=100.0) is None
    assert credenziali.riconosci(vive, None, adesso=100.0) is None


def test_due_credenziali_non_si_somigliano(vive):
    """Prevedibile vorrebbe dire indovinabile. Sono 256 bit da `secrets`, come
    il token interno.

    Mutazione: coniarle da un contatore -- rossa."""
    fatte = {credenziali.conia(vive, mestiere="ponte", durata_s=60, adesso=100.0)
             for _ in range(50)}

    assert len(fatte) == 50
    assert all(len(s) > 30 for s in fatte)


def test_il_confronto_e_a_TEMPO_COSTANTE(vive):
    """Un confronto che esce al primo carattere diverso dice quanto ci si e'
    avvicinati, e con abbastanza tentativi il segreto si ricostruisce.

    Si guarda la FORMA, come per le porte di scrittura dell'attuatore: la
    proprieta' non si puo' misurare da un test, ma l'assenza della funzione
    giusta si'.

    Mutazione ESEGUITA: `==` al posto di `compare_digest` -- rossa."""
    import pathlib
    sorgente = pathlib.Path(credenziali.__file__).read_text(encoding="utf-8")

    assert "compare_digest" in sorgente
    assert "segreto ==" not in sorgente and "== segreto" not in sorgente


def test_le_credenziali_scadute_non_si_accumulano(vive):
    """Il worker ne conia una a ogni giro: tenerle per sempre sarebbe una
    perdita di memoria su un percorso che gira ogni pochi secondi.

    Mutazione: non potare mai -- rossa."""
    for n in range(100):
        credenziali.conia(vive, mestiere="ponte", durata_s=1, adesso=100.0 + n)

    credenziali.conia(vive, mestiere="ponte", durata_s=60, adesso=1000.0)

    assert len(vive) < 10, f"le scadute sono rimaste: {len(vive)}"


def test_si_puo_REVOCARE_un_mestiere_intero(vive):
    """Quando il ponte si spegne, le sue credenziali smettono di valere subito:
    aspettare la scadenza vorrebbe dire che spegnere il ponte non spegne
    davvero il suo accesso.

    Mutazione ESEGUITA: non revocare allo spegnimento -- rossa."""
    uno = credenziali.conia(vive, mestiere="ponte", durata_s=600, adesso=100.0)
    due = credenziali.conia(vive, mestiere="altro", durata_s=600, adesso=100.0)

    credenziali.revoca(vive, mestiere="ponte")

    assert credenziali.riconosci(vive, uno, adesso=101.0) is None
    assert credenziali.riconosci(vive, due, adesso=101.0) is not None


def test_il_contenitore_nasce_quando_l_app_si_compone():
    """Scrivere in `app[...]` a richiesta gia' servita e' deprecato in aiohttp 3
    e un errore in aiohttp 4 -- la stessa ragione per cui nascono li' i
    contatori dei giri di strumento, la cache dei ruoli e i canali visti.

    Mutazione: creare il contenitore alla prima richiesta -- rossa."""
    app = {}
    credenziali.prepara_credenziali(app)

    assert app["credenziali"] == {}
