"""I caratteri non escono di casa (reperto D-7, 23/09/2026).

Le due pagine chiedevano i tre caratteri a `fonts.googleapis.com` **a ogni
apertura**. Tre conseguenze, e nessuna teorica:

- **rivela indirizzo e programma del proprietario a un terzo**: ogni apertura
  dice a Google che quella casa è sveglia, e a che ora;
- **l'add-on non è autosufficiente senza rete** — la casa in cui HIRIS serve di
  più è proprio quella con la rete giù;
- **la politica dei contenuti resta aperta verso l'esterno**: finché il foglio
  di stile può venire da fuori, `style-src` deve ammetterlo, e un permesso
  aperto per i caratteri è aperto e basta.

**Costa 138 KB nell'immagine.** È il prezzo, ed è scritto.

I file si scaricano **a mano** con `scripts/vendora_caratteri.py` e stanno nel
repository: scaricarli al build vorrebbe dire che due costruzioni della stessa
versione di HIRIS possono contenere due caratteri diversi — la stessa ragione
per cui la CLI del ponte è pinnata a una versione esatta.
"""
import pathlib

import pytest

RADICE = pathlib.Path(__file__).resolve().parents[1]
STATICI = RADICE / "hiris" / "app" / "static"
PAGINE = ("index.html", "config.html")


@pytest.mark.parametrize("pagina", PAGINE)
def test_nessuna_pagina_chiede_i_caratteri_a_un_TERZO(pagina):
    """**Il reperto.**

    Mutazione ESEGUITA: rimettere il `<link>` a Google -- rossa."""
    import re

    testo = (STATICI / pagina).read_text(encoding="utf-8")
    # Gli INDIRIZZI che la pagina va a prendere, non le parole che contiene:
    # il commento che spiega questa fetta nomina i due domini, e una prova che
    # cercasse la parola cadrebbe sulla spiegazione invece che sul difetto.
    chiesti = re.findall(r'(?:href|src)\s*=\s*"([^"]+)"', testo)

    for indirizzo in chiesti:
        for fornitore in ("fonts.googleapis.com", "fonts.gstatic.com"):
            assert fornitore not in indirizzo, (
                f"«{pagina}» chiede ancora qualcosa a {fornitore}")


@pytest.mark.parametrize("pagina", PAGINE)
def test_ogni_pagina_carica_il_foglio_DI_CASA(pagina):
    """Togliere il `<link>` e basta lascerebbe le pagine coi caratteri di
    ripiego del sistema: sarebbe una regressione, non una chiusura.

    Mutazione ESEGUITA: togliere il foglio -- rossa."""
    testo = (STATICI / pagina).read_text(encoding="utf-8")

    assert "hiris-fonts.css" in testo


def test_il_foglio_punta_a_file_CHE_ESISTONO():
    """Un `@font-face` che punta a un file assente non e' un errore visibile:
    la pagina ripiega in silenzio sul carattere di sistema, e il difetto si
    vede solo a occhio.

    Mutazione ESEGUITA: rinominare un file -- rossa."""
    import re

    foglio = (STATICI / "hiris-fonts.css").read_text(encoding="utf-8")
    percorsi = re.findall(r"url\(([^)]+)\)", foglio)

    assert percorsi, "il foglio non dichiara nessun carattere"
    for percorso in percorsi:
        assert not percorso.startswith("http"), (
            f"«{percorso}» viene ancora da fuori")
        assert (STATICI / percorso).exists(), f"manca il file «{percorso}»"


def test_la_politica_dei_contenuti_si_CHIUDE_verso_l_esterno():
    """La meta' che il reperto chiamava per nome: finche' il foglio poteva
    venire da fuori, `style-src` e `font-src` dovevano ammetterlo. Adesso non
    devono piu', e un permesso che non serve e' debito.

    Mutazione ESEGUITA: lasciare i domini nella politica -- rossa."""
    sorgente = (RADICE / "hiris/app/server.py").read_text(encoding="utf-8")
    inizio = sorgente.index("Content-Security-Policy")
    politica = sorgente[inizio:inizio + 700]

    assert "fonts.googleapis.com" not in politica
    assert "fonts.gstatic.com" not in politica
    assert "font-src 'self'" in politica


def test_le_LICENZE_viaggiano_coi_caratteri():
    """Ridistribuire un carattere sotto OFL si puo' -- e' il senso della
    licenza -- **a patto di portarsela dietro**. Un file di licenza mancante
    non si nota finche' non e' un problema legale.

    Mutazione ESEGUITA: togliere una licenza -- rossa."""
    licenze = list((STATICI / "fonts").glob("OFL-*.txt"))

    assert len(licenze) == 3, "tre famiglie, tre licenze"
    for licenza in licenze:
        assert "SIL Open Font License" in licenza.read_text(encoding="utf-8")


def test_il_PESO_di_cio_che_entra_nell_immagine_e_dichiarato():
    """Il prezzo di questa fetta, misurato. Se un giorno qualcuno aggiungesse
    il cirillico, questa prova lo costringe a rimisurarlo invece di scoprirlo
    dalla dimensione dell'immagine.

    Mutazione ESEGUITA: aggiungere un sottoinsieme -- rossa."""
    peso = sum(f.stat().st_size
               for f in (STATICI / "fonts").glob("*.woff2"))

    assert peso < 200 * 1024, (
        f"i caratteri pesano {peso // 1024} KB: sopra il tetto dichiarato di "
        "200 KB. Rimisura e riscrivi il prezzo, non alzare il numero.")
