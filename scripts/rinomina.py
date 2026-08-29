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


@dataclass
class Collisione:
    """Due nomi ORIGINALI diversi che, nello stesso file, finirebbero sullo
    stesso inglese: `_fuso` e `fuso` diventano entrambi `timezone` senza il
    trattino basso a distinguerli. Fonderli sarebbe peggio di non rinominare
    -- un aiutante privato scambiato per l'interfaccia pubblica di
    qualcun altro, senza che nessuno lo sappia. Come un composto, si segnala
    e non si applica: lo strumento non indovina, chiede.
    """
    nomi: list[str]
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
        # I trattini bassi iniziali E finali sono convenzione Python
        # (privato; oppure evitare di ombreggiare una parola riservata, come
        # `tipo_`/`gamba_`): non parole da tradurre, si tolgono prima di
        # guardare le maiuscole e si rimettono identici alla fine. Senza,
        # `_fuso` (un aiutante privato) diventava `timezone` (interfaccia
        # pubblica) -- misurato su `consumi/store.py` (Task 4). Stessa
        # famiglia sul lato finale: `gamba_` (`cervello/oggetti.py`, evita
        # di ombreggiare la parola `gamba`) sarebbe diventato `aspect`,
        # perdendo il trattino che lo distingue dalla parola che ombreggia
        # -- trovato guardando se restasse una quarta variante di forma non
        # coperta, dopo maiuscole (round 1), costanti TUTTE MAIUSCOLE
        # (round 1) e prefisso privato (round 2).
        nucleo = nome.strip("_")
        prefisso = nome[:len(nome) - len(nome.lstrip("_"))]
        suffisso = nome[len(nome.rstrip("_")):]
        # La forma del nome originale si conserva: `Archivio` -> `Store`,
        # `archivio` -> `store`. Rinominare una classe in minuscolo romperebbe
        # la convenzione di Python piu' silenziosamente di quanto sembri.
        #
        # Ma `nucleo[:1].isupper()` da solo confonde una classe (`Archivio`,
        # PascalCase) con una costante di modulo (`ETICHETTA`, TUTTA
        # maiuscola): entrambe iniziano con una lettera maiuscola. Misurato
        # puntando lo strumento su `consumi/vocabolario.py` (Task 4): senza
        # `nucleo.isupper()`, `ETICHETTA` diventava `Label` invece di
        # `LABEL`, rompendo la convenzione delle costanti in silenzio.
        if nucleo[:1].isupper():
            parola = en.upper() if nucleo.isupper() else en.capitalize()
        else:
            parola = en
        return prefisso + parola + suffisso
    # Un composto in cui almeno un pezzo non e' deciso resta una proposta lo
    # stesso: il pezzo ignoto va guardato, non saltato. Una forma raggiunta
    # per alias (`costruzioni` -> lemma `costruzione` -> `construction`)
    # resta una proposta anche da sola: l'inglese del lemma non e' detto
    # abbia la stessa inflessione della forma originale (non e' sempre «+s»).
    suggerito = "_".join(t or p.lower() for t, p in zip(tradotti, pezzi))
    return Proposta(nome=nome, pezzi=[p.lower() for p in pezzi], suggerito=suggerito)


import argparse
import io
import subprocess
import tokenize

from _comune import file_py, rel


def riscrivi(sorgente: str, g: Glossario, ambito: str) -> tuple[str, list[Proposta | Collisione]]:
    """Il sorgente coi soli token NAME rinominati, piu' i composti (e le
    collisioni) da decidere.

    Si sostituisce sul TESTO alle posizioni dei token, da destra a sinistra:
    `tokenize.untokenize` rigenererebbe il file e ne perderebbe la
    formattazione, che qui e' contenuto -- i commenti allineati di questa
    codebase sono la sua parte migliore.
    """
    righe = sorgente.splitlines(keepends=True)
    inizi = [0]
    for r in righe:
        inizi.append(inizi[-1] + len(r))

    def offset(pos):
        riga, col = pos
        return inizi[riga - 1] + col

    grezzi, proposte = [], []
    visti = set()
    for t in tokenize.generate_tokens(io.StringIO(sorgente).readline):
        if t.type != tokenize.NAME:
            continue
        esito = classifica(t.string, g, ambito)
        if esito is None:
            continue
        if isinstance(esito, Proposta):
            if esito.nome not in visti:
                visti.add(esito.nome)
                proposte.append(esito)
            continue
        grezzi.append((offset(t.start), offset(t.end), t.string, esito))

    # Guardia sulle collisioni: se due nomi ORIGINALI diversi finirebbero
    # sullo stesso inglese in questo file, nessuno dei due si applica.
    # Fondere due identita' diverse senza che nessuno lo sappia e' peggio di
    # non rinominare -- lo stesso principio dei composti, applicato a un
    # difetto che un composto non copre (qui ogni singolo nome e' gia'
    # deciso; e' l'INCONTRO fra due nomi decisi che va guardato).
    nomi_per_nuovo: dict[str, set[str]] = {}
    for _, _, nome_originale, nuovo in grezzi:
        nomi_per_nuovo.setdefault(nuovo, set()).add(nome_originale)
    collisi = {nuovo: nomi for nuovo, nomi in nomi_per_nuovo.items() if len(nomi) > 1}
    for nuovo, nomi in collisi.items():
        chiave = (nuovo, tuple(sorted(nomi)))
        if chiave not in visti:
            visti.add(chiave)
            proposte.append(Collisione(nomi=sorted(nomi), suggerito=nuovo))

    cambi = [(i, j, nuovo) for i, j, _, nuovo in grezzi if nuovo not in collisi]

    fuori = sorgente
    for i, j, nuovo in sorted(cambi, reverse=True):
        fuori = fuori[:i] + nuovo + fuori[j:]
    return fuori, proposte


def _leggi_grezzo(f: Path) -> str:
    """Il sorgente coi SUOI fine-riga, non quelli di `leggi()` (`_comune.py`).

    `leggi()` legge in universal newlines implicito: va bene per chi la
    usa solo in lettura (`censimento.py`, `doppioni.py`), sbagliato qui, dove
    il testo si RISCRIVE sul disco. Non si tocca `_comune.py` per questo:
    e' condiviso con quei due strumenti, e a loro il comportamento attuale
    va bene -- leggere diversamente quando serve una garanzia che lui non
    da' non e' il doppione che il vincolo vieta.

    `newline=""` lascia intatti i fine-riga che ci sono, qualunque essi
    siano; senza, la scrittura successiva li tradurrebbe (su Windows, LF
    diventa CRLF) e cambierebbe OGNI riga del file, non solo quella
    dell'identificatore rinominato -- il contrario della prima guardia (un
    diff che contiene una cosa sola).
    """
    with open(f, encoding="utf-8-sig", errors="replace", newline="") as fh:
        return fh.read()


def _scrivi_grezzo(f: Path, testo: str) -> None:
    """Scrive senza tradurre i fine-riga: il gemello di `_leggi_grezzo`."""
    with open(f, "w", encoding="utf-8", newline="") as fh:
        fh.write(testo)


def applica(base: Path, ambito: str, *, scrivi: bool = True) -> list[Proposta | Collisione]:
    """Tutto il sottosistema, oppure un file solo. Un file illeggibile si
    riporta e si va avanti.

    Misurato: `file_py()` usa `rglob`, che su un percorso-file non trova
    nulla -- serve decidere l'elenco dei file all'inizio, non delegarlo
    tutto a `file_py`, o un `--percorso` a un file singolo elaborerebbe
    zero file senza errore: il difetto peggiore, perche' ha l'aspetto
    esatto di un successo.
    """
    file = [base] if base.is_file() else file_py(base)
    tutte: list[Proposta | Collisione] = []
    for f in file:
        sorgente = _leggi_grezzo(f)
        try:
            fuori, proposte = riscrivi(sorgente, g_corrente(), ambito)
        except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
            print(f"  ! {rel(f)}: non leggibile, saltato ({exc})")
            continue
        tutte.extend(proposte)
        if scrivi and fuori != sorgente:
            _scrivi_grezzo(f, fuori)
    return tutte


_G: Glossario | None = None


def g_corrente() -> Glossario:
    global _G
    if _G is None:
        _G = leggi_glossario()
    return _G


def _albero_pulito() -> bool:
    fuori = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True, check=False)
    return not fuori.stdout.strip()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Rinomina gli identificatori di un sottosistema.")
    p.add_argument("--percorso", required=True, help="es. hiris/app/consumi")
    p.add_argument("--ambito", required=True, help="il sottosistema, per gli omonimi: es. consumi")
    p.add_argument("--dry-run", action="store_true", help="non scrive, elenca soltanto")
    a = p.parse_args(argv)

    # Guardia 1: un diff da rivedere non deve mai mescolare la rinomina con
    # altro. E' l'unica cosa che rende leggibile un diff da migliaia di righe.
    if not a.dry_run and not _albero_pulito():
        print("albero sporco: la rinomina si applica solo su un albero pulito")
        return 1

    base = ROOT / a.percorso
    if not base.exists():
        print(f"percorso inesistente: {a.percorso}")
        return 1

    proposte = applica(base, a.ambito, scrivi=not a.dry_run)
    composti = [p for p in proposte if isinstance(p, Proposta)]
    collisioni = [p for p in proposte if isinstance(p, Collisione)]
    msg = f"{a.percorso} (ambito «{a.ambito}»): {len(composti)} composti da decidere"
    if collisioni:
        msg += f", {len(collisioni)} collisioni"
    print(msg)
    for pr in sorted(composti, key=lambda x: x.nome):
        print(f"  {pr.nome:38} pezzi={'+'.join(pr.pezzi):30} suggerito={pr.suggerito}")
    for c in sorted(collisioni, key=lambda x: x.suggerito):
        print(f"  COLLISIONE {'/'.join(c.nomi):30} -> suggerito={c.suggerito} "
              f"(nessuno dei due si applica)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


