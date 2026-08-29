#!/usr/bin/env python3
"""Il rinominatore: porta all'inglese GLI IDENTIFICATORI, e nient'altro.

**Il confine e' strutturale, non promesso.** Si lavora sui soli token di tipo
NAME: commenti, stringhe e docstring non sono «da evitare», sono fuori
portata per costruzione. E' il mandato del proprietario -- «solo ed
esclusivamente cio' che e' codice» -- reso una proprieta' del meccanismo
invece che una precauzione che qualcuno puo' dimenticare.

**Non indovina.** Sui nomi composti l'inglese inverte l'ordine delle parole
(`unita_vive` non e' `unit_reported`, e' `reported_units`), ci sono
preposizioni che spariscono (`nomi_di_ripiego`) e sigle di confine da non
tradurre (`ha_credenziale`: quel `ha` e' Home Assistant). Quindi propone e si
ferma: e' la legge del glossario applicata alla rinomina, «una riga senza
prova non e' decisa».
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comune import ROOT, leggi

GLOSSARIO = ROOT / "docs" / "GLOSSARIO.md"

# Le tre tabelle che portano una coppia italiano -> inglese, con la posizione
# della colonna inglese. I «valori di dominio» NON sono qui: il glossario li
# ha rinviati di proposito, con la ragione scritta.
_TABELLE = (
    ("## I concetti", 2),
    ("## Le parole ordinarie", 1),
    ("## I nomi degli strumenti", 2),
)
_SCARTATE = "## Parole scartate durante l'estrazione"


@dataclass
class Glossario:
    mappa: dict[str, str] = field(default_factory=dict)
    omonimi: dict[str, dict[str, str]] = field(default_factory=dict)
    scartate: set[str] = field(default_factory=set)

    def per(self, parola: str, ambito: str) -> str | None:
        """L'inglese di una parola nel sottosistema dato.

        Un omonimo fuori dai sottosistemi che il glossario nomina restituisce
        `None`: meglio non rinominare che rinominare col significato
        dell'altra riga.
        """
        if parola in self.scartate:
            return None
        if parola in self.omonimi:
            return self.omonimi[parola].get(ambito)
        return self.mappa.get(parola)


def _sezione(testo: str, titolo: str) -> str:
    i = testo.index(titolo)
    resto = testo[i + len(titolo):]
    j = resto.find("\n## ")
    return resto if j < 0 else resto[:j]


def leggi_glossario(percorso: Path | None = None) -> Glossario:
    testo = leggi(percorso or GLOSSARIO)
    g = Glossario()

    for riga in _sezione(testo, _SCARTATE).splitlines():
        m = re.match(r"\| `?([a-z][a-z_']*)`? \|", riga)
        if m:
            g.scartate.add(m.group(1))

    for titolo, colonna in _TABELLE:
        for riga in _sezione(testo, titolo).splitlines():
            if not riga.startswith("|") or riga.startswith("|---"):
                continue
            celle = [c.strip() for c in riga.strip("|").split("|")]
            if len(celle) <= colonna:
                continue
            it, en = celle[0], celle[colonna]
            if it in ("italiano", "costante") or not re.fullmatch(r"[a-z_]+", en):
                continue
            m = re.fullmatch(r"([a-z][a-z_']*)(?: \((\w+)\))?", it)
            if not m:
                continue
            parola, ambito = m.group(1), m.group(2)
            if parola in g.scartate:
                continue
            if ambito:
                # Un omonimo esce dalla mappa piatta anche se ci era gia'
                # entrato da una riga senza parentesi: la mappa piatta
                # risponderebbe con una sola delle due letture.
                g.mappa.pop(parola, None)
                g.omonimi.setdefault(parola, {})[ambito] = en
            elif parola not in g.omonimi:
                g.mappa[parola] = en
    return g


@dataclass
class Proposta:
    """Un composto: lo strumento sa cosa contiene, non come si dice in inglese."""
    nome: str
    pezzi: list[str]
    suggerito: str


def spezza(nome: str) -> list[str]:
    """I pezzi di un identificatore, senza i trattini bassi di convenzione."""
    return [p for p in re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", nome) if p]


def classifica(nome: str, g: Glossario, ambito: str):
    """`str` da applicare, `Proposta` da confermare, o `None` da lasciar stare."""
    pezzi = spezza(nome)
    tradotti = [g.per(p.lower(), ambito) for p in pezzi]
    if not any(tradotti):
        return None
    if len(pezzi) == 1:
        en = tradotti[0]
        if en is None:
            return None
        # La forma del nome originale si conserva: `Archivio` -> `Store`,
        # `archivio` -> `store`. Rinominare una classe in minuscolo romperebbe
        # la convenzione di Python piu' silenziosamente di quanto sembri.
        return en.capitalize() if nome[:1].isupper() else en
    # Un composto in cui almeno un pezzo non e' deciso resta una proposta lo
    # stesso: il pezzo ignoto va guardato, non saltato.
    suggerito = "_".join(t or p.lower() for t, p in zip(tradotti, pezzi))
    return Proposta(nome=nome, pezzi=[p.lower() for p in pezzi], suggerito=suggerito)


