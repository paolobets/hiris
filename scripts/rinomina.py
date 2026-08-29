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

# La sezione «Parole scartate» porta DUE tabelle, e sono l'opposto l'una
# dell'altra: la prima sono parole che restano italiane per sempre, la
# seconda sono forme (singolare/plurale) gia' ricondotte a un lemma che HA
# una riga vera nel glossario. Il confine fra le due si legge
# dall'INTESTAZIONE, non dalla posizione ne' dal conteggio delle tabelle:
# se l'intestazione degli alias cambiasse e il lettore continuasse a cercare
# solo «dov'e' la seconda tabella», le sue righe finirebbero silenziosamente
# fra gli scarti -- il contrario del vero.
_INTESTAZIONE_SCARTI = "| parola uscita dallo script | perche' e' stata scartata |"
_INTESTAZIONE_ALIAS = "| forma uscita dallo script | lemma nel glossario |"


@dataclass
class Glossario:
    mappa: dict[str, str] = field(default_factory=dict)
    omonimi: dict[str, dict[str, str]] = field(default_factory=dict)
    scartate: set[str] = field(default_factory=set)
    alias: dict[str, str] = field(default_factory=dict)

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


def _scarti_e_alias(sezione: str) -> tuple[set[str], dict[str, str]]:
    """Le due tabelle della sezione «Parole scartate», tenute distinte
    dall'intestazione: se l'intestazione degli alias non si trova piu',
    `str.index` solleva `ValueError` invece di lasciar scivolare le sue
    righe nella tabella degli scarti veri -- fermarsi rumorosamente e'
    la stessa legge di `Glossario.per`, applicata alla lettura.
    """
    i_scarti = sezione.index(_INTESTAZIONE_SCARTI)
    i_alias = sezione.index(_INTESTAZIONE_ALIAS)
    blocco_scarti = sezione[i_scarti:i_alias]
    blocco_alias = sezione[i_alias:]

    scartate = set()
    for riga in blocco_scarti.splitlines():
        m = re.match(r"\| `?([a-z][a-z_']*)`? \|", riga)
        if m:
            scartate.add(m.group(1))

    alias = {}
    for riga in blocco_alias.splitlines():
        m = re.match(r"\| `([a-z][a-z_']*)` \| `([a-z][a-z_']*)` \|", riga)
        if m:
            alias[m.group(1)] = m.group(2)
    return scartate, alias


def leggi_glossario(percorso: Path | None = None) -> Glossario:
    testo = leggi(percorso or GLOSSARIO)
    g = Glossario()

    g.scartate, g.alias = _scarti_e_alias(_sezione(testo, _SCARTATE))

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
    per_alias = False
    tradotti = []
    for p in pezzi:
        chiave = p.lower()
        lemma = g.alias.get(chiave)
        if lemma is not None:
            per_alias = True
            tradotti.append(g.per(lemma, ambito))
        else:
            tradotti.append(g.per(chiave, ambito))
    if not any(tradotti):
        return None
    if len(pezzi) == 1 and not per_alias:
        en = tradotti[0]
        if en is None:
            return None
        # La forma del nome originale si conserva: `Archivio` -> `Store`,
        # `archivio` -> `store`. Rinominare una classe in minuscolo romperebbe
        # la convenzione di Python piu' silenziosamente di quanto sembri.
        return en.capitalize() if nome[:1].isupper() else en
    # Un composto in cui almeno un pezzo non e' deciso resta una proposta lo
    # stesso: il pezzo ignoto va guardato, non saltato. Una forma raggiunta
    # per alias (`costruzioni` -> lemma `costruzione` -> `construction`)
    # resta una proposta anche da sola: l'inglese del lemma non e' detto
    # abbia la stessa inflessione della forma originale (non e' sempre «+s»).
    suggerito = "_".join(t or p.lower() for t, p in zip(tradotti, pezzi))
    return Proposta(nome=nome, pezzi=[p.lower() for p in pezzi], suggerito=suggerito)


