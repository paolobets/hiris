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
            scarti.append(Scarto(nome, f"v{dati['major']}", "", dati["dove"],
                                 reg["errore"]))
        elif dati["major"] < reg["major"]:
            scarti.append(Scarto(nome, f"v{dati['major']}",
                                 f"v{reg['major']}", dati["dove"]))

    # ── L'immagine di base: fissata per impronta, quindi lo scarto e' «si e'
    #    mossa». Non c'e' un numero di versione da confrontare -- la domanda
    #    e' se l'etichetta che le corrisponde punti ancora li'.
    for arch, dati in sorted(letti.get("basi", {}).items()):
        reg = registri.get("basi", {}).get(arch, {})
        nome = f"immagine di base ({arch})"
        if reg.get("errore"):
            scarti.append(Scarto(nome, dati["impronta"][:19], "",
                                 dati["dove"], reg["errore"]))
        elif reg.get("impronta") and reg["impronta"] != dati["impronta"]:
            scarti.append(Scarto(nome, dati["impronta"][:19],
                                 reg["impronta"][:19], dati["dove"]))

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
                                 f"<{dati['tetto']}", "",
                                 dati["dove"], reg["errore"]))
            continue
        # «uscita >= tetto» detto con l'unico confronto di versioni che il file
        # gia' possiede: non ne serve un secondo.
        if not piu_vecchia(reg["versione"], dati["tetto"]):
            scarti.append(Scarto(
                f"{nome} (il tetto <{dati['tetto']} esclude la {reg['versione']})",
                f"<{dati['tetto']}", reg["versione"],
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
# `[^@]*` fra `-g` e il pacchetto: dal 22/09/2026 c'e' `--ignore-scripts` in
# mezzo (reperto D-4), e un cancello che pretende la forma di ieri tace invece
# di rompersi -- che e' il modo in cui una verifica smette di verificare.
#: `  aarch64: "ghcr.io/home-assistant/aarch64-base-python@sha256:..."`
#: I tipi di manifesto che si accettano. Senza, il registro risponde con un
#: manifesto tradotto e l'impronta che torna non e' quella che `build.yaml`
#: scrive.
_MANIFESTI = ("application/vnd.oci.image.index.v1+json, "
              "application/vnd.docker.distribution.manifest.list.v2+json, "
              "application/vnd.docker.distribution.manifest.v2+json")
_RE_BASE = re.compile(
    r'^\s*(\w+):\s*"ghcr\.io/([^"@]+)@(sha256:[0-9a-f]{64})"')
_RE_CLI = re.compile(
    r"npm install -g [^@]*" + re.escape(PACCHETTO_CLI) + r"@([\d.]+)")

# Due forme, e la prima e' quella nuova: dal 22/09/2026 le azioni sono fissate
# per IMPRONTA (reperto D-5), con l'etichetta nel commento accanto perche'
# resti leggibile -- e perche' questo cancello possa continuare a leggerla.
# Senza la prima alternativa non troverebbe piu' nessuna azione e direbbe
# «tutto a posto» guardando il vuoto.
_RE_AZIONE = re.compile(
    r"uses:\s*([\w.-]+/[\w.-]+)@(?:[0-9a-f]{40}\s*#\s*v(\d+)|v(\d+))")


def _versione_installata(nome: str):
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(nome)
    except PackageNotFoundError:
        return None


def leggi_i_file(requisiti=None) -> dict:
    """Cio' che il repo dichiara. Nessuna rete.

    `requisiti` esiste per **una prova**, e non e' una concessione: la
    proprieta' «una riga senza tetto non produce un tetto» e' del LETTORE, non
    dell'elenco di oggi. Fino al 22/09/2026 la si provava puntando a
    `model2vec`, che un tetto non ce l'aveva; quella libreria e' uscita
    (reperto D-2) e oggi ogni riga un tetto ce l'ha. Legare la prova a quale
    pacchetto per caso ne e' sprovvisto vorrebbe dire ritrovarla rossa il
    giorno in cui qualcuno gliene mette uno -- cioe' rossa su un
    miglioramento. Cosi' invece la prova chiede al lettore vero, su righe
    scritte apposta, senza ricopiarne la logica.
    """
    dockerfile = RADICE / "hiris" / "Dockerfile"
    workflow = RADICE / ".github" / "workflows" / "tests.yml"
    # DUE file dal 21/09/2026: la produzione e lo sviluppo si sono separati
    # quando `cryptography` e' entrata nell'immagine. Si leggono entrambi,
    # perche' un pavimento o un tetto sbagliato su `ruff` o su `pytest` rompe
    # il cancello esattamente come uno su `aiohttp` -- e leggerne uno solo
    # avrebbe fatto sparire in silenzio quattro righe dalla sorveglianza.
    requisiti = requisiti or [RADICE / "hiris" / "requirements.txt",
                              RADICE / "hiris" / "requirements-dev.txt"]

    # **L'immagine di base, per impronta** (reperto D-3, 23/09/2026). Si legge
    # l'etichetta dal commento SOPRA la riga: e' l'unica cosa che dice quale
    # Python ci sia dentro, e senza di lei non si saprebbe nemmeno quale
    # etichetta interrogare per sapere se la base si e' mossa.
    basi: dict = {}
    righe_build = (RADICE / "hiris" / "build.yaml").read_text(
        encoding="utf-8").splitlines()
    for indice, riga in enumerate(righe_build):
        trovata_base = _RE_BASE.search(riga)
        if not trovata_base:
            continue
        precedente = righe_build[indice - 1].strip() if indice else ""
        etichetta = precedente.lstrip("# ").strip() if precedente.startswith("#") else ""
        basi[trovata_base.group(1)] = {
            "repository": trovata_base.group(2),
            "impronta": trovata_base.group(3),
            "etichetta": etichetta,
            "dove": "hiris/build.yaml",
        }
    if not basi:
        raise SystemExit(
            f"Non trovo nessuna immagine di base fissata per impronta in "
            f"{RADICE / 'hiris' / 'build.yaml'}. Se la forma e' cambiata, "
            "aggiorna `_RE_BASE`: senza, questo controllo tacerebbe invece di "
            "rompersi.")

    trovata = _RE_CLI.search(dockerfile.read_text(encoding="utf-8"))
    if not trovata:
        raise SystemExit(
            f"Non trovo la riga del pin della CLI in {dockerfile}. Se la forma e' "
            "cambiata, aggiorna `_RE_CLI`: senza, questo controllo tacerebbe "
            "invece di rompersi.")
    cli = {"versione": trovata.group(1), "dove": "hiris/Dockerfile"}

    azioni: dict = {}
    for nome, per_impronta, per_etichetta in _RE_AZIONE.findall(
            workflow.read_text(encoding="utf-8")):
        major = per_impronta or per_etichetta
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
    # `relative_to` solo quando il file STA dentro il repo: una prova che
    # passa un elenco scritto altrove non deve far sollevare il lettore.
    def _dove(percorso):
        try:
            return percorso.relative_to(RADICE).as_posix()
        except ValueError:
            return percorso.name

    righe = [(riga.strip(), _dove(percorso))
             for percorso in requisiti
             for riga in percorso.read_text(encoding="utf-8").splitlines()]
    for riga, dove in righe:
        if not riga or riga.startswith(("#", "-r ")):
            continue
        nome = re.split(r"[><=!\s]", riga, maxsplit=1)[0]
        minimo = re.search(r">=\s*([\d.]+)", riga)
        # Il tetto si legge INTERO, non solo il major. Un pacchetto 0.x non ha
        # ancora un major, quindi il suo tetto sano sta sul minor (`<0.17.0`):
        # leggendo le sole cifre prima del primo punto si otteneva 0, e ogni
        # uscita 0.x lo violava. E' lo scarto permanente su una riga sana che il
        # commento qui sotto voleva evitare -- il caso 0.x era sfuggito.
        massimo = re.search(r"<\s*([\d.]+)", riga)
        if minimo:
            pavimenti[nome] = {"minimo": minimo.group(1),
                               "installato": _versione_installata(nome)}
        # Nessun tetto -> nessun major da escludere. Inventarne uno
        # produrrebbe uno scarto permanente su una riga sana.
        if massimo:
            tetti[nome] = {"tetto": massimo.group(1), "dove": dove}
    return {"cli": cli, "azioni": azioni, "tetti": tetti,
            "pavimenti": pavimenti, "basi": basi}


def _json(url: str) -> dict:
    richiesta = urllib.request.Request(url, headers={"User-Agent": "hiris-verifica"})
    with urllib.request.urlopen(richiesta, timeout=TIMEOUT) as risposta:
        return json.load(risposta)


def _impronta_viva(repository: str, etichetta: str) -> str:
    """L'impronta che OGGI sta dietro quell'etichetta su ghcr.io.

    Non c'e' una «ultima versione» da confrontare come per npm o PyPI:
    un'immagine fissata per impronta si e' mossa quando l'etichetta che le
    corrisponde punta altrove. La domanda giusta e' quella, e la risposta e'
    un'intestazione.

    Il registro di GitHub vuole un gettone anche per le immagini pubbliche, e
    lo da' a chiunque lo chieda: due chiamate, nessuna credenziale.
    """
    gettone = _json(
        f"https://ghcr.io/token?scope=repository:{repository}:pull"
        "&service=ghcr.io")["token"]
    richiesta = urllib.request.Request(
        f"https://ghcr.io/v2/{repository}/manifests/{etichetta}",
        headers={
            "Authorization": f"Bearer {gettone}",
            "User-Agent": "hiris-verifica",
            # Senza questo il registro risponde con un manifesto tradotto, e
            # l'impronta che torna non e' quella che `build.yaml` scrive.
            "Accept": _MANIFESTI,
        })
    with urllib.request.urlopen(richiesta, timeout=TIMEOUT) as risposta:
        impronta = risposta.headers.get("Docker-Content-Digest")
    if not impronta:
        raise RuntimeError("il registro non ha dichiarato l'impronta")
    return impronta


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

    for arch, dati in letti.get("basi", {}).items():
        try:
            fuori.setdefault("basi", {})[arch] = {
                "impronta": _impronta_viva(dati["repository"], dati["etichetta"])}
        except Exception as exc:
            fuori.setdefault("basi", {})[arch] = {"errore": str(exc)}

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
        testo = testo.replace(f"{nome}@v{dati['major']}",
                              f"{nome}@v{reg['major']}")
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
            print(f"  {s.componente:<{larghezza}}  non ho potuto controllare: {s.motivo}")
        else:
            print(f"  {s.componente:<{larghezza}}  {s.scritto} -> {s.disponibile}   ({s.dove})")


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

    print(f"\nIl rilascio si e' fermato: {len(scarti)} componenti da guardare.\n")
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
