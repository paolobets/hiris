"""L'immagine di base è fissata per IMPRONTA (reperto D-3, 23/09/2026).

`build.yaml` la nominava per **etichetta** (`3.13-alpine3.21`), che è un nome
mobile: l'etichetta viene rispinta ogni volta che la base cambia, quindi due
costruzioni della **stessa versione di HIRIS** possono contenere due CPython
diversi, due OpenSSL diversi, due musl diversi. Quando qualcosa si rompe fra
una consegna e l'altra non c'è un colpevole leggibile — ed è lo stesso difetto
che la CLI del ponte aveva prima del pin alla versione esatta.

**Cosa costa, detto per intero**: le patch della base non arrivano più da
sole, comprese quelle di sicurezza. Aggiornarla diventa un atto deliberato di
chi rilascia. È il prezzo del pin, ed è la ragione per cui la riga va guardata
a ogni giro — `scripts/verifica_componenti.py` la guarda.

**L'etichetta resta scritta accanto**, nel commento: un'impronta da sola non
dice a nessuno quale versione di Python ci sia dentro.
"""
import pathlib
import re

import yaml

RADICE = pathlib.Path(__file__).resolve().parents[1]
BUILD = RADICE / "hiris" / "build.yaml"

IMPRONTA = re.compile(r"@sha256:[0-9a-f]{64}$")


def _immagini() -> dict:
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))["build_from"]


def test_ogni_architettura_e_fissata_per_impronta():
    """**Il reperto.**

    Mutazione ESEGUITA: togliere l'impronta da un'architettura -- rossa."""
    immagini = _immagini()

    assert set(immagini) == {"aarch64", "amd64"}
    for arch, riferimento in immagini.items():
        assert IMPRONTA.search(riferimento), (
            f"«{arch}» e' ancora fissata per etichetta: due costruzioni della "
            "stessa versione possono contenere due basi diverse")


def test_le_due_architetture_NON_condividono_l_impronta():
    """Ogni architettura ha la sua immagine: la stessa impronta su tutte e due
    vorrebbe dire che qualcuno ha copiato una riga sull'altra, e una delle due
    costruzioni fallirebbe -- o peggio, girerebbe sull'architettura sbagliata.

    **Questa prova e' nata verde e non sapeva fallire.** Confrontava i due
    riferimenti INTERI, che differiscono sempre -- il nome del repository
    contiene l'architettura (`aarch64-base-python` contro `amd64-base-python`)
    -- quindi copiare un'impronta sull'altra la lasciava verde. La proprieta'
    vera sta nelle impronte, non nelle stringhe che le contengono.

    Mutazione ESEGUITA: copiare un'impronta sull'altra -- rossa."""
    impronte = {arch: IMPRONTA.search(riferimento).group(0)
                for arch, riferimento in _immagini().items()}

    assert impronte["aarch64"] != impronte["amd64"], (
        "le due architetture hanno la stessa impronta: una delle due "
        "costruzioni fallira', o girera' sull'architettura sbagliata")


def test_l_ETICHETTA_resta_leggibile_accanto_all_impronta():
    """Un'impronta da sola non dice a nessuno quale Python ci sia dentro. Chi
    legge `build.yaml` fra sei mesi deve poter capire cosa sta aggiornando
    senza interrogare un registro.

    Mutazione ESEGUITA: togliere il commento con l'etichetta -- rossa."""
    testo = BUILD.read_text(encoding="utf-8")

    assert testo.count("3.13-alpine3.21") >= 2, (
        "l'etichetta non e' scritta accanto a tutte e due le impronte")


def test_il_cancello_del_rilascio_GUARDA_questa_riga():
    """Il prezzo del pin e' che le patch non arrivano da sole: senza qualcuno
    che guardi, «fissato per impronta» diventa «fermo da un anno».

    Mutazione ESEGUITA: togliere l'immagine dai componenti sorvegliati --
    rossa."""
    sorgente = (RADICE / "scripts/verifica_componenti.py").read_text(
        encoding="utf-8")

    assert "build.yaml" in sorgente
    assert "base-python" in sorgente

