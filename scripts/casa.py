#!/usr/bin/env python3
"""HIRIS casa — l'unica porta degli attrezzi verso la casa vera, di sola lettura.

## Perche' esiste

Gli attrezzi dello sprint «Una fonte sola di verita'» (la sonda di parita', la
fotografia delle porte, le batterie) lavorano sui dati veri della casa. Prima
ognuno se li andava a prendere a modo suo: la firma verso HIRIS era ricopiata
in un file dell'analisi, e la lettura WebSocket stava in un `ws.py` che il
01/10/2026 non esisteva gia' piu'. Tre attrezzi, tre modi di leggere: lo
stesso difetto che lo sprint caccia nel prodotto.

Qui c'e' UNA porta, e ha due regole.

1. **Legge e basta.** Verso HIRIS conosce un verbo solo, `GET`. Verso Home
   Assistant passa da `HAClient` -- il vero client del prodotto, non una sua
   copia -- e ne chiama solo i metodi di `READ_METHODS`. E' una lista di
   AMMISSIONE: chiude per difetto, e un metodo nuovo resta vietato finche'
   qualcuno non lo ammette per iscritto. La prova e' `tests/test_casa_script.py`.
2. **Non stampa e non salva segreti.** La chiave e il token non compaiono mai
   in un messaggio, nemmeno d'errore.
3. **I dati della casa non entrano nel repo.** Ogni file che porta nomi della
   casa si scrive fuori dall'albero del progetto: `outside_repo()` rifiuta un
   bersaglio che ci sta dentro, e tutti gli attrezzi passano di li'.

**Dichiarato**: `hiris_get` e `ha_get` fanno un `GET` a qualunque percorso gli
si dia. Che un `GET` del prodotto non abbia effetti e' una proprieta' del
prodotto, non di questa porta.

## La casa si dichiara da fuori, mai qui dentro

    HIRIS_URL          per esempio http://casa:8099
    HIRIS_KEY_FILE     la chiave del servizio firmato (~/.hiris-canale-sviluppo.key)
    HIRIS_HOUSE_URL    Home Assistant, per esempio http://casa:8123
    HIRIS_HOUSE_TOKEN_FILE   il token di HA (~/.ha-token); oppure il token
                             stesso in HIRIS_HOUSE_TOKEN

Gli ultimi sono gli stessi di `scripts/istantaneo_pubblicato.py`, che li
legge gia': si importano da li', non si riscrivono.

## Gli ingressi congelati

`cattura` salva in una cartella FUORI dal repo cio' che la casa dice adesso:
registri, stati, statistiche, corpi di automazioni e script, sistema di
riferimento, servizi, traduzioni degli stati, guasti, registro degli errori,
plance, e l'albero che HIRIS serve. La sonda e la fotografia girano su
quei file, non sul vivo: e' cio' che rende confrontabili un «prima» e un
«dopo». **Un ingresso monco non si salva**: una fotografia identica su dati a
meta' non proverebbe niente.

Uso:
  python scripts/casa.py cattura [--in ~/.hiris-sprint/ingressi/AAAA-MM-GG]
  python scripts/casa.py leggi hiris /api/health
  python scripts/casa.py leggi ha /api/config --in config.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_KEY_FILE = "~/.hiris-canale-sviluppo.key"
SPRINT_HOME = Path("~/.hiris-sprint").expanduser()
PRINTED_CHARS = 6000

#: I metodi di `HAClient` che questa porta puo' chiamare. Lista di AMMISSIONE:
#: ogni nome ha la sua ragione, e chi ne aggiunge uno la scrive.
READ_METHODS: dict[str, str] = {
    "read_registries": "l'anagrafe: aree, dispositivi, entita', integrazioni",
    "get_states": "lo specchio degli stati",
    "statistic_ids": "chi ha statistiche di lungo periodo",
    "behavior_configs": "i corpi di automazioni e script",
    "get_config": "il sistema di riferimento: fuso, versione, lingua",
    "get_services": "il registro dei servizi: cosa si puo' comandare",
    "get_translations": "le parole con cui Home Assistant rende uno stato",
    "problems": "i guasti che Home Assistant ha gia' diagnosticato",
    "system_log": "il registro degli errori",
    "read_dashboards": "le plance",
}

#: Gli INGRESSI: cio' che `capture` congela dalla casa e che sonda e
#: fotografia leggono. Un nome qui e' un file `<nome>.json` nella cartella e
#: una chiave nel dizionario di `read_inputs`. E' l'UNICO elenco: chi scrive e
#: chi legge lo chiedono a questa riga.
INPUTS = ("registries", "states", "statistic_ids", "behavior", "ha_config",
          "services", "translations", "problems", "system_log", "dashboards")
MANIFEST = "manifest"
HIRIS_TREE = "home-space"


def _hiris_url() -> str:
    url = os.environ.get("HIRIS_URL")
    if not url:
        raise SystemExit("casa: HIRIS non e' dichiarato. Serve HIRIS_URL "
                         "(per esempio http://casa:8099).")
    return url.rstrip("/")


def _key_file() -> str:
    return os.path.expanduser(os.environ.get("HIRIS_KEY_FILE") or DEFAULT_KEY_FILE)


def _house() -> tuple[str, str]:
    from istantaneo_pubblicato import DEFAULT_TOKEN_FILE, house_token, house_url
    url, token = house_url(), house_token()
    if not url or not token:
        raise SystemExit("casa: Home Assistant non e' dichiarato. Servono "
                         "HIRIS_HOUSE_URL e il token nel file "
                         f"{DEFAULT_TOKEN_FILE} (o HIRIS_HOUSE_TOKEN_FILE).")
    return url.rstrip("/"), token


def outside_repo(target: str | Path) -> Path:
    """Il percorso, se sta FUORI dall'albero del progetto; altrimenti rifiuta.

    Il repo e' pubblico: un ingresso, una fotografia o un rapporto portano i
    nomi di una casa, e un `--in` sbagliato li metterebbe a un `git add` di
    distanza dalla rete. Ogni attrezzo che scrive dati della casa passa di qui.
    """
    path = Path(target).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise SystemExit(f"casa: {path} sta dentro il repo, che e' pubblico. I dati "
                         f"della casa si scrivono fuori, per esempio sotto {SPRINT_HOME}.")
    return path


def read_inputs(folder: str | Path) -> dict:
    """Gli ingressi congelati, come dizionario `{nome: contenuto}`."""
    folder = Path(folder).expanduser()
    missing = [name for name in INPUTS if not (folder / f"{name}.json").exists()]
    if missing:
        raise SystemExit(f"casa: in {folder} mancano gli ingressi {missing}. La cartella "
                         "e' di una cattura piu' vecchia: rifalla con `casa.py cattura`.")
    return {name: json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
            for name in INPUTS}


def manifest_of(folder: str | Path) -> dict:
    return json.loads((Path(folder).expanduser() / f"{MANIFEST}.json")
                      .read_text(encoding="utf-8"))


def _fetch(request: urllib.request.Request, what: str) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=60) as answer:
            return answer.read()
    except urllib.error.HTTPError as error:
        # Codice e percorso, mai le intestazioni: li' dentro c'e' il segreto.
        raise SystemExit(f"casa: {what} ha risposto {error.code}") from None
    except urllib.error.URLError as error:
        raise SystemExit(f"casa: {what} non raggiungibile ({error.reason})") from None


def hiris_get(path: str) -> bytes:
    """Un `GET` firmato a HIRIS. La firma e' quella degli altri script."""
    from misure import intestazioni_firmate
    url = _hiris_url() + path
    return _fetch(urllib.request.Request(url, headers=intestazioni_firmate(_key_file(), url)),
                  f"HIRIS {path.split('?', 1)[0]}")


def ha_get(path: str) -> bytes:
    """Un `GET` a Home Assistant col token del file."""
    url, token = _house()
    request = urllib.request.Request(url + path,
                                     headers={"Authorization": f"Bearer {token}"})
    return _fetch(request, f"Home Assistant {path.split('?', 1)[0]}")


def _admitted(method: str) -> None:
    if method not in READ_METHODS:
        raise PermissionError(
            f"casa: `{method}` non e' fra i metodi di lettura ammessi "
            f"({', '.join(sorted(READ_METHODS))}). Questa porta legge e basta.")


async def ha_read(method: str, *args, url: str | None = None,
                  token_file: str | None = None):
    """Chiama UN metodo di lettura di `HAClient` sulla casa vera.

    Il rifiuto di un metodo fuori elenco arriva PRIMA di aprire qualunque
    connessione: non serve una casa raggiungibile per sentirsi dire di no.
    """
    _admitted(method)
    from hiris.app.proxy.ha_client import HAClient
    if url is None or token_file is None:
        url, token = _house()
    else:
        token = Path(token_file).expanduser().read_text(encoding="utf-8").strip()
    client = HAClient(url, token)
    await client.start()
    try:
        return await getattr(client, method)(*args)
    finally:
        await client.stop()


class _LiveHouse:
    """La casa vera dietro i soli metodi ammessi, su un client solo."""

    def __init__(self) -> None:
        from hiris.app.proxy.ha_client import HAClient
        self._client = HAClient(*_house())

    async def __aenter__(self):
        await self._client.start()
        return self

    async def __aexit__(self, *_):
        await self._client.stop()

    def __getattr__(self, method: str):
        _admitted(method)
        return getattr(self._client, method)


def _stop(reason: str) -> None:
    raise SystemExit(f"casa: cattura FERMATA, niente e' stato salvato. {reason}")


async def _read_all(house, hiris) -> dict[str, object]:
    registries, unread = await house.read_registries()
    if unread:
        _stop(f"Registri non letti: {', '.join(unread)}.")
    states = await house.get_states([])
    if isinstance(states, dict):
        _stop(f"Gli stati non sono stati letti: {states.get('errore')}.")
    if not states:
        _stop("Home Assistant non ha restituito nessuno degli stati.")
    statistics = await house.statistic_ids()
    if isinstance(statistics, dict):
        _stop(f"L'elenco delle statistiche non e' stato letto: {statistics.get('errore')}.")
    # Quali domini hanno un corpo lo dice il prodotto, non un elenco scritto qui.
    from hiris.app.home_space.behavior import BEHAVIOR_DOMAINS
    from hiris.app.proxy.state_translations import STATE_TRANSLATIONS_CATEGORY
    behaving = sorted(row["entity_id"] for row in states
                      if str(row.get("entity_id", "")).split(".")[0] in BEHAVIOR_DOMAINS)
    behavior = await house.behavior_configs(behaving) if behaving else {"configurazioni": {}}
    if "errore" in behavior:
        _stop(f"I corpi di automazioni e script non sono stati letti: {behavior['errore']}.")
    if behavior.get("non_letti"):
        _stop(f"{len(behavior['non_letti'])} corpi di automazioni o script non letti.")
    ha_config = await house.get_config()
    if "errore" in ha_config:
        _stop(f"Il sistema di riferimento non e' stato letto: {ha_config['errore']}.")
    if not ha_config:
        _stop("Il sistema di riferimento di Home Assistant e' vuoto.")
    language = ha_config.get("language")
    if not language:
        _stop("Home Assistant non dichiara la propria lingua.")
    words = await house.get_translations(language, STATE_TRANSLATIONS_CATEGORY)
    problems = await house.problems()
    system_log = await house.system_log()
    for name, answer in (("traduzioni", words), ("guasti", problems),
                         ("registro degli errori", system_log)):
        if "errore" in answer:
            _stop(f"Lettura non riuscita ({name}): {answer['errore']}.")
    # Una plancia non leggibile NON ferma la cattura: e' un fatto di questa
    # casa e non un guasto della lettura (misurato il 01/10/2026: la plancia
    # principale in modalita' automatica non ha un corpo da leggere, ed e' cio'
    # che vede anche il prodotto). Si salva l'elenco com'e'.
    dashboards, unread_dashboards = await house.read_dashboards()
    try:
        health = json.loads(hiris("/api/health"))
        home_space = json.loads(hiris("/api/home-space"))
    except ValueError:
        _stop("HIRIS ha risposto qualcosa che non e' JSON.")
    services = await house.get_services()
    if isinstance(services, dict):
        _stop(f"I servizi non sono stati letti: {services.get('errore')}.")
    read = {"registries": registries, "states": states,
            "statistic_ids": sorted(statistics), "behavior": behavior,
            "ha_config": ha_config, "services": services,
            "translations": {"language": language,
                             "category": STATE_TRANSLATIONS_CATEGORY, "report": words},
            "problems": problems, "system_log": system_log,
            "dashboards": {"entries": dashboards, "unavailable": unread_dashboards}}
    if set(read) != set(INPUTS):
        _stop(f"La cattura e l'elenco degli ingressi non coincidono: "
              f"{sorted(set(read) ^ set(INPUTS))}.")
    return {**read, HIRIS_TREE: home_space, "health": health}


async def capture(target: Path, *, house=None, hiris=None) -> dict:
    """Congela gli ingressi in `target` e restituisce il manifesto.

    Prima legge TUTTO, poi scrive: se una lettura manca la cartella non nasce.
    `house` e `hiris` si possono passare da fuori (le prove lo fanno); senza,
    sono la casa vera.
    """
    target = outside_repo(target)
    if target.exists():
        raise SystemExit(f"casa: {target} esiste gia'. Una cattura non si sovrascrive: "
                         "e' il «prima» di un confronto.")
    hiris = hiris or hiris_get
    if house is None:
        async with _LiveHouse() as live:
            read = await _read_all(live, hiris)
    else:
        read = await _read_all(house, hiris)

    registries = read["registries"]
    health = read.pop("health")
    manifest = {
        "catturata_ts": time.time(),
        "hiris": health.get("version"),
        "home_assistant": read["ha_config"].get("version"),
        "conti": {"entita": len(registries.get("entita", [])),
                  "dispositivi": len(registries.get("dispositivi", [])),
                  "aree": len(registries.get("aree", [])),
                  "stati": len(read["states"])},
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="cattura-", dir=target.parent))
    try:
        for name, content in {**read, MANIFEST: manifest}.items():
            (staging / f"{name}.json").write_text(
                json.dumps(content, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    capturing = commands.add_parser("cattura", help="congela gli ingressi fuori dal repo")
    capturing.add_argument("--in", dest="target", default=None)
    reading = commands.add_parser("leggi", help="un GET, a HIRIS o a Home Assistant")
    reading.add_argument("who", choices=("hiris", "ha"))
    reading.add_argument("path")
    reading.add_argument("--in", dest="target", default=None)
    args = parser.parse_args()

    if args.command == "cattura":
        target = Path(args.target).expanduser() if args.target else (
            SPRINT_HOME / "ingressi" / time.strftime("%Y-%m-%d"))
        manifest = asyncio.run(capture(target))
        tally = " · ".join(f"{name} {value}" for name, value in manifest["conti"].items())
        print(f"casa: ingressi congelati in {target}")
        print(f"      HIRIS {manifest['hiris']} · Home Assistant "
              f"{manifest['home_assistant']} · {tally}")
        return
    body = (hiris_get if args.who == "hiris" else ha_get)(args.path)
    if args.target:
        outside_repo(args.target).write_bytes(body)
        print(f"casa: {args.path} -> {args.target} ({len(body)} byte)")
        return
    try:
        print(json.dumps(json.loads(body), ensure_ascii=False, indent=1)[:PRINTED_CHARS])
    except ValueError:
        print(body[:PRINTED_CHARS].decode("utf-8", "replace"))


if __name__ == "__main__":
    main()
