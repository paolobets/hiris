#!/usr/bin/env python3
"""HIRIS — la verifica dei componenti al rilascio.

`hiris/Dockerfile` porta scritta, per esteso, la disciplina del pin della CLI:
«le patch non arrivano piu' da sole [...] la riga va guardata a ogni giro di
rilascio». Non e' stata guardata ne' nella 3.0.0, ne' nella 3.1.0, ne' nella
3.2.0. **Una disciplina scritta non e' una disciplina eseguita**: una nota si
legge solo se qualcuno va a cercarla, e al momento del rilascio nessuno ci va.

Questo strumento non e' una nota: e' un cancello. Lo chiama `.githooks/pre-push`
quando il push contiene un bump di `hiris/config.yaml`, e il push non prosegue
finche' non gli si risponde.

Uso:
  python scripts/verifica_componenti.py                    # guarda e stampa
  python scripts/verifica_componenti.py --aggiorna         # azioni CI all'ultimo major
  python scripts/verifica_componenti.py --aggiorna --cli   # + il pin della CLI

Uscita: 0 se non c'e' niente da guardare, 1 se c'e'.

Spec: docs/design/2026-08-15-verifica-dei-componenti.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
TIMEOUT = 5          # come le `_fetch_*` di handlers_models: cinque secondi di pazienza
PACCHETTO_CLI = "@anthropic-ai/claude-code"


@dataclass(frozen=True)
class Scarto:
    """Una cosa da guardare. `motivo` non vuoto significa «non ho potuto
    controllare» -- che NON e' un via libera: e' uno scarto come gli altri."""
    componente: str
    scritto: str
    disponibile: str
    dove: str
    motivo: str = ""


def piu_vecchia(a: str, b: str) -> bool:
    """«a e' piu' vecchia di b», confrontando NUMERI e non stringhe.

    Lessicograficamente "2.1.9" > "2.1.10", che e' falso come versione -- ed e'
    l'unico caso in cui i due confronti differiscono, quindi l'unico che una
    prova puo' usare per distinguerli.

    Le lunghezze diverse si allineano con zeri: "2.1" e' piu' vecchia di
    "2.1.1", non uguale.
    """
    def pezzi(v: str) -> list[int]:
        return [int(p) for p in re.findall(r"\d+", v)]
    pa, pb = pezzi(a), pezzi(b)
    lunghezza = max(len(pa), len(pb))
    pa += [0] * (lunghezza - len(pa))
    pb += [0] * (lunghezza - len(pb))
    return pa < pb


def componi_scarti(letti: dict, registri: dict) -> list[Scarto]:
    """Cio' che e' scritto nei file, contro cio' che i registri hanno risposto.

    PURA: nessuna rete, nessun `os.environ`, nessun orologio, nessun
    filesystem. Chi la chiama porta i fatti gia' misurati -- stessa divisione di
    `app/decisione_modelli.py`, e per la stessa ragione: uno scarto si fabbrica
    passando due dizionari, quindi le prove possono PRODURRE il difetto invece
    di descriverlo.

    UN COMPONENTE ALLINEATO NON COMPARE. Un elenco che dice sempre qualcosa e'
    un elenco che si smette di leggere: e' il difetto che questo strumento
    esiste per chiudere, e non va reintrodotto in scala minore.
    """
    scarti: list[Scarto] = []

    # ── La CLI del ponte: pin ESATTO, quindi ogni patch conta ──────────────
    cli_letta = letti["cli"]
    cli_reg = registri.get("cli", {})
    if cli_reg.get("errore"):
        scarti.append(Scarto("CLI del ponte", cli_letta["versione"], "",
                             cli_letta["dove"], cli_reg["errore"]))
    elif piu_vecchia(cli_letta["versione"], cli_reg["versione"]):
        scarti.append(Scarto("CLI del ponte", cli_letta["versione"],
                             cli_reg["versione"], cli_letta["dove"]))

    # ── Le azioni CI: solo il MAJOR, perche' e' la forma con cui il workflow
    #    le riferisce (`@v6`). Confrontare la patch chiederebbe di riscriverlo
    #    in una forma che non usa.
    for nome, dati in sorted(letti["azioni"].items()):
        reg = registri.get("azioni", {}).get(nome, {})
        if reg.get("errore"):
            scarti.append(Scarto(nome, "v%d" % dati["major"], "", dati["dove"],
                                 reg["errore"]))
        elif dati["major"] < reg["major"]:
            scarti.append(Scarto(nome, "v%d" % dati["major"],
                                 "v%d" % reg["major"], dati["dove"]))

    # ── I TETTI Python, e NON i pavimenti ──────────────────────────────────
    # Un pavimento sta per definizione sotto l'ultima uscita: confrontarlo
    # produrrebbe uno scarto per OGNI dipendenza, a ogni rilascio, per sempre.
    # I tetti sono aperti (`<1.0.0`) e CI installa da zero, quindi CI prova
    # gia' l'ultima versione: il solo caso in cui un numero su PyPI cambia cio'
    # che gira e' un MAJOR NUOVO SOPRA IL TETTO -- che congela la dipendenza in
    # silenzio, con CI verde e immagine che si costruisce. Vedi spec §2.1.
    for nome, dati in sorted(letti["tetti"].items()):
        reg = registri.get("pypi", {}).get(nome, {})
        if reg.get("errore"):
            scarti.append(Scarto(f"{nome} (tetto)",
                                 "<%d.0.0" % dati["major_escluso"], "",
                                 dati["dove"], reg["errore"]))
            continue
        major_uscito = int(re.findall(r"\d+", reg["versione"])[0])
        if major_uscito >= dati["major_escluso"]:
            scarti.append(Scarto(
                "%s (il tetto <%d.0.0 esclude il major %d)"
                % (nome, dati["major_escluso"], major_uscito),
                "<%d.0.0" % dati["major_escluso"], reg["versione"],
                dati["dove"]))

    # ── I pavimenti contro cio' che e' INSTALLATO ──────────────────────────
    # Nessuna rete. E' il difetto misurato il 15/08/2026: `anthropic` 0.40.0
    # installato contro `>=0.87.0` dichiarato -- la suite locale provava
    # qualcosa di diverso da CI e dall'immagine, e nessun controllo lo diceva.
    for nome, dati in sorted(letti["pavimenti"].items()):
        installato = dati.get("installato")
        if not installato:
            continue
        if piu_vecchia(installato, dati["minimo"]):
            scarti.append(Scarto(
                f"{nome} installato sotto il pavimento dichiarato",
                installato, dati["minimo"], "ambiente di questo interprete"))

    return scarti


# ── Le forme, in un posto solo ─────────────────────────────────────────────
# Due espressioni, e ognuna e' un patto con un file. Se una smette di
# combaciare il valore diventerebbe vuoto e il controllo TACEREBBE: e' il modo
# in cui questo strumento potrebbe diventare inutile senza rompersi, quindi una
# lettura che non trova niente SOLLEVA invece di restituire vuoto.
_RE_CLI = re.compile(r"npm install -g " + re.escape(PACCHETTO_CLI) + r"@([\d.]+)")
_RE_AZIONE = re.compile(r"uses:\s*([\w.-]+/[\w.-]+)@v(\d+)")


def _versione_installata(nome: str):
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(nome)
    except PackageNotFoundError:
        return None


def leggi_i_file() -> dict:
    """Cio' che il repo dichiara. Nessuna rete."""
    dockerfile = RADICE / "hiris" / "Dockerfile"
    workflow = RADICE / ".github" / "workflows" / "tests.yml"
    requisiti = RADICE / "hiris" / "requirements.txt"

    trovata = _RE_CLI.search(dockerfile.read_text(encoding="utf-8"))
    if not trovata:
        raise SystemExit(
            f"Non trovo la riga del pin della CLI in {dockerfile}. Se la forma e' "
            "cambiata, aggiorna `_RE_CLI`: senza, questo controllo tacerebbe "
            "invece di rompersi.")
    cli = {"versione": trovata.group(1), "dove": "hiris/Dockerfile"}

    azioni: dict = {}
    for nome, major in _RE_AZIONE.findall(workflow.read_text(encoding="utf-8")):
        # Lo stesso `uses:` compare piu' volte (checkout in due job): vince il
        # major PIU' BASSO, perche' e' quello che va aggiornato.
        precedente = azioni.get(nome, {}).get("major")
        if precedente is None or int(major) < precedente:
            azioni[nome] = {"major": int(major),
                            "dove": ".github/workflows/tests.yml"}
    if not azioni:
        raise SystemExit(f"Nessun `uses:` trovato in {workflow}.")

    tetti: dict = {}
    pavimenti: dict = {}
    for riga in requisiti.read_text(encoding="utf-8").splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#"):
            continue
        nome = re.split(r"[><=!\s]", riga, maxsplit=1)[0]
        minimo = re.search(r">=\s*([\d.]+)", riga)
        massimo = re.search(r"<\s*(\d+)\.", riga)
        if minimo:
            pavimenti[nome] = {"minimo": minimo.group(1),
                               "installato": _versione_installata(nome)}
        # Nessun tetto -> nessun major da escludere. Inventarne uno
        # produrrebbe uno scarto permanente su una riga sana.
        if massimo:
            tetti[nome] = {"major_escluso": int(massimo.group(1)),
                           "dove": "hiris/requirements.txt"}
    return {"cli": cli, "azioni": azioni, "tetti": tetti, "pavimenti": pavimenti}


def _json(url: str) -> dict:
    richiesta = urllib.request.Request(url, headers={"User-Agent": "hiris-verifica"})
    with urllib.request.urlopen(richiesta, timeout=TIMEOUT) as risposta:
        return json.load(risposta)


def interroga_i_registri(letti: dict) -> dict:
    """Le tre letture vive. NON SOLLEVA MAI: un guasto diventa
    `{"errore": "<motivo>"}`, che a valle e' uno scarto.

    Gira dentro `git push`: un'eccezione qui non sarebbe un blocco leggibile,
    sarebbe un traceback in mezzo a un rilascio.

    Le tre rotte rispondono senza autenticazione -- verificato eseguendo il
    15/08/2026, non dedotto.
    """
    fuori: dict = {"cli": {}, "azioni": {}, "pypi": {}}
    try:
        fuori["cli"] = {"versione": _json(
            f"https://registry.npmjs.org/{PACCHETTO_CLI}/latest")["version"]}
    except Exception as exc:
        fuori["cli"] = {"errore": str(exc)}

    for nome in letti["azioni"]:
        try:
            tag = _json(
                f"https://api.github.com/repos/{nome}/releases/latest")["tag_name"]
            fuori["azioni"][nome] = {"major": int(re.findall(r"\d+", tag)[0])}
        except Exception as exc:
            fuori["azioni"][nome] = {"errore": str(exc)}

    for nome in letti["tetti"]:
        try:
            fuori["pypi"][nome] = {"versione": _json(
                f"https://pypi.org/pypi/{nome}/json")["info"]["version"]}
        except Exception as exc:
            fuori["pypi"][nome] = {"errore": str(exc)}
    return fuori


# ── Il cancello, e l'aggiornamento ─────────────────────────────────────────

def risposta_accettata(valore) -> bool:
    """Il valore ESATTO `"1"`, e nessun altro.

    Una variabile che accetta qualunque cosa non vuota si finisce per
    esportarla nel profilo, e allora il cancello resta aperto per sempre senza
    che nessuno lo decida.

    La regola vive QUI e non nell'hook: scriverla anche in shell metterebbe la
    stessa regola in due linguaggi, liberi di divergere -- che e' la forma di
    difetto che la pagina Modelli ha appena finito di togliere dal prodotto.
    """
    return valore == "1"


def aggiorna_azioni(letti: dict, registri: dict) -> list:
    """Porta le azioni CI all'ultimo major. NON tocca nient'altro, e le due
    astensioni hanno ragioni DIVERSE.

    `requirements.txt`: gli scarti Python non si correggono cambiando un
    numero. Un major sopra il tetto e' una DECISIONE (si alza e si prova, o si
    resta); un pacchetto installato sotto il pavimento si ripara
    nell'AMBIENTE, non nel file.

    `Dockerfile`: un confronto di numeri non puo' vedere la cosa che conta,
    cioe' se la CLI nuova smette di emettere `mcp_servers` nell'init -- nel
    qual caso HIRIS non si rompe, diventa CIECO. Quel controllo lo fa
    `sonda_strumenti` a runtime, dopo il deploy. Serve `--cli`.
    """
    percorso = RADICE / ".github" / "workflows" / "tests.yml"
    testo = percorso.read_text(encoding="utf-8")
    toccati = []
    for nome, dati in sorted(letti["azioni"].items()):
        reg = registri.get("azioni", {}).get(nome, {})
        if reg.get("errore") or dati["major"] >= reg["major"]:
            continue
        testo = testo.replace("%s@v%d" % (nome, dati["major"]),
                              "%s@v%d" % (nome, reg["major"]))
        toccati.append(nome)
    if toccati:
        percorso.write_text(testo, encoding="utf-8")
    return toccati


def aggiorna_cli(letti: dict, registri: dict):
    """La riga del `Dockerfile`, e solo su richiesta esplicita (`--cli`)."""
    reg = registri.get("cli", {})
    if reg.get("errore") or not piu_vecchia(letti["cli"]["versione"],
                                            reg["versione"]):
        return None
    percorso = RADICE / "hiris" / "Dockerfile"
    testo = percorso.read_text(encoding="utf-8")
    percorso.write_text(
        testo.replace("{}@{}".format(PACCHETTO_CLI, letti["cli"]["versione"]),
                      "{}@{}".format(PACCHETTO_CLI, reg["versione"])),
        encoding="utf-8")
    return reg["versione"]


def stampa(scarti: list) -> None:
    larghezza = max((len(s.componente) for s in scarti), default=0)
    for s in scarti:
        if s.motivo:
            print("  %-*s  non ho potuto controllare: %s"
                  % (larghezza, s.componente, s.motivo))
        else:
            print("  %-*s  %s -> %s   (%s)"
                  % (larghezza, s.componente, s.scritto, s.disponibile, s.dove))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aggiorna", action="store_true",
                   help="porta le azioni CI all'ultimo major")
    p.add_argument("--cli", action="store_true",
                   help="con --aggiorna: aggiorna anche il pin della CLI del ponte")
    args = p.parse_args(argv)

    # LA RISPOSTA SI LEGGE QUI, non nell'hook: vedi `risposta_accettata`.
    if not args.aggiorna and risposta_accettata(os.environ.get("HIRIS_COMPONENTI_OK")):
        print("verifica dei componenti: saltata su tua richiesta "
              "(HIRIS_COMPONENTI_OK=1)")
        return 0

    letti = leggi_i_file()
    registri = interroga_i_registri(letti)

    if args.aggiorna:
        toccati = aggiorna_azioni(letti, registri)
        nuova = aggiorna_cli(letti, registri) if args.cli else None
        if toccati:
            print("Azioni CI portate all'ultimo major: " + ", ".join(toccati))
        if nuova:
            print(f"CLI del ponte portata a {nuova} in hiris/Dockerfile")
        if not toccati and not nuova:
            print("Niente da aggiornare qui.")
        else:
            # Non si lancia la suite: lanciarla renderebbe l'aggiornamento
            # un'operazione unica che «e' andata bene», invece di due fatti
            # separati di cui il secondo puo' fallire.
            print("\nAdesso tocca alla suite:  python -m pytest tests/ -q")
        return 0

    scarti = componi_scarti(letti, registri)
    if not scarti:
        return 0

    print("\nIl rilascio si e' fermato: %d componenti da guardare.\n" % len(scarti))
    stampa(scarti)
    print("\nSe hai deciso di rilasciare cosi' com'e':")
    print("    HIRIS_COMPONENTI_OK=1 git push ...")
    print("Se vuoi aggiornare le azioni CI:")
    print("    python scripts/verifica_componenti.py --aggiorna")
    print("Se una dipendenza e' installata sotto il pavimento:")
    print("    python -m pip install -r hiris/requirements.txt --upgrade")
    return 1


if __name__ == "__main__":
    sys.exit(main())
