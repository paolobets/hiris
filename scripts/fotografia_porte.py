#!/usr/bin/env python3
"""HIRIS fotografia delle porte — cio' che esce oggi da ogni porta, fermato.

## Perche' esiste

E' la garanzia 4 dello sprint «Una fonte sola di verita'» (spec §5): prima di
toccare una regola si salva cio' che esce da ogni porta sui dati veri; dopo, o
e' identico o la differenza e' quella dichiarata. «Pura sostituzione» vuol
dire: la fotografia non cambia.

## Perche' a freddo

Fra un «prima» e un «dopo» presi dal vivo la casa cambia: una luce si accende
e la fotografia differisce senza che il codice c'entri. Quindi gli ingressi si
congelano UNA volta (`scripts/casa.py cattura`) e il codice del prodotto gira
su quelli, con un orologio fermo. Stessi ingressi, stesso orologio: l'uscita
deve essere identica byte per byte, e ogni differenza e' del codice.

## La casa la monta l'avvio vero del prodotto

La casa e' `CasaFinta` (`scripts/casa_finta.py`): il client VERO di Home
Assistant, col solo trasporto sostituito, che risponde dagli ingressi
congelati nella forma grezza di Home Assistant (Tappa 2, Task 4, 03/10/2026:
prima era `FrozenHouse`, che imitava i metodi pubblici a mano). L'app si monta
chiamando `server._on_startup`, cioe' l'avvio vero: archivi, giudizi dei
tipi, traduzioni, registro dei servizi, guasti, tutto cablato come in
produzione, in una cartella dati temporanea. Il nucleo esce da
`compose_briefing` e gli strumenti da `create_tool_dispatcher`, gli unici due
punti in cui il prodotto li costruisce. **Il cablaggio non e' ricopiato qui**:
una prima versione montava a mano cinque oggetti e lasciava fuori giudizi e
traduzioni, e una modifica che toccava solo quelli avrebbe dato «0
differenze» (rilievo I1 della revisione del 01/10/2026).

Una porta che comincia a chiedere a Home Assistant qualcosa che gli ingressi
non hanno si vede: `CasaFinta` solleva `UnservedCommand` col nome del comando,
e non e' un'eccezione che il prodotto possa inghiottire -- lo scatto si
ferma.

## Cosa NON fotografa, dichiarato

- `history`, `calendar` e `related`: chiedono a Home Assistant storico,
  eventi e legami, che gli ingressi non portano.
- Gli strumenti che scrivono (`execute`, `promise`, `propose`, `confirm`,
  `remember`, `cancel`): non si chiamano.
- Le rotte che leggono gli archivi di HIRIS in `/data` (resoconti, sapere,
  agenda): `forme`, dal vivo. Qui gli archivi nascono VUOTI: i ricordi, le
  promesse e il sapere imparato dalla casa vera non ci sono, c'e' il seme.
- Il confronto dell'albero con Home Assistant (`extract_from_target`) e il
  Supervisor: gli ingressi non li portano, e l'avvio li trova muti.
- I CORPI di automazioni e script: il prodotto li consegna solo se riesce a
  leggere `secrets.yaml` per sigillarli, e a freddo la cartella di
  configurazione di Home Assistant non c'e'. Lo scatto li vede tutti «senza
  corpo disponibile» (misurato il 01/10/2026: 19 su 19), la produzione no.
- I prompt di sistema si compongono DENTRO `chat()` dei runner, in linea: qui
  si fotografano i testi fissi che li compongono, non la composizione.

## Le forme, dal vivo

Le rotte che leggono gli archivi di HIRIS non si rifanno a freddo: i loro dati
stanno in `/data` dentro il container. Di quelle `forme` salva la FORMA della
risposta -- chiavi, tipi, lunghezze degli elenchi -- prima e dopo un rilascio.
Una forma non porta valori: ne' nomi della casa, ne' credenziali -- e nemmeno
le CHIAVI, quando sono identificatori della casa (un dizionario indicizzato
per `entity_id` diventa `{"*": forma}`). Le rotte si chiedono a `server.py`,
non si elencano qui: una rotta `GET` nuova entra da sola nella fotografia,
cioe' viene chiamata. E' una scelta: un `GET` e' una lettura.

Uso:
  python scripts/fotografia_porte.py scatta --ingressi <cartella> --in foto.json
  python scripts/fotografia_porte.py forme --in forme.json
  python scripts/fotografia_porte.py confronta prima.json dopo.json
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import casa
from casa_finta import NOWHERE, CasaFinta

from hiris.app import claude_runner, server
from hiris.app.agent import prompts as bridge_prompts
from hiris.app.api import handlers_chat, handlers_home_space
from hiris.app.home_space import briefing, house_query, queries, topology
from hiris.app.home_space.house import House
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS
from hiris.app.mind import actuator_turn, analyst_turn, observer, recipe_turn

DIFFERENCES_SHOWN = 200
STARTUP_TIMEOUT_S = 120
SAMPLED_ENTITIES = 5
BUSIEST_DOMAINS = 5

#: Le porte dello scatto. Chi ne aggiunge una la aggiunge QUI e in `shoot`.
PORTS = ("albero", "visibili", "nucleo", "schede", "selezioni", "osservatore",
         "ricette", "strumenti", "catalogo", "prompt")



#: Le rotte `GET` che `forme` NON chiede. Lista di AMMISSIONE al contrario:
#: ogni esclusione col suo perche'; una rotta nuova entra da sola.
EXCLUDED_ROUTES: dict[str, str] = {}


def live_routes(app=None, *, excluded=None) -> tuple[str, ...]:
    """Le rotte `GET` dell'API, chieste al router vero dell'app.

    Dal router e non dal sorgente di `server.py` (03/10/2026, Tappa 1 dello
    sprint «Una fonte sola di verita'»): quando le rotte usciranno da
    `server.py` la fotografia continuera' a vederle, invece di vederne meno e
    restare «identica». Solo quelle sotto `/api/` e senza un segnaposto nel
    percorso: le pagine HTML non hanno una forma JSON, e una rotta con `{id}`
    vuole un id vero della casa. `excluded=()` restituisce tutto, per chi
    verifica le esclusioni.
    """
    app = app if app is not None else server.create_app()
    skipped = EXCLUDED_ROUTES if excluded is None else excluded
    routes = {route.resource.canonical for route in app.router.routes()
              if route.resource is not None and route.method == "GET"}
    return tuple(sorted(route for route in routes
                        if route.startswith("/api/") and "{" not in route
                        and route not in skipped))


#: Oltre questo numero di chiavi un dizionario non e' un oggetto con dei
#: campi: e' una tabella indicizzata da qualcosa della casa.
RECORD_KEY_LIMIT = 40
ANY_KEY = "*"


def _is_identifier(key: str) -> bool:
    """Una chiave che e' un identificatore della casa, non il nome di un campo:
    `sensor.x`, `integrazione:y`, un id esadecimale lungo."""
    return ("." in key or ":" in key or "/" in key
            or (len(key) >= 20 and all(c in "0123456789abcdef-" for c in key.lower())))


def _merge(first, second):
    """L'unione di due forme. Ricorsiva e SIMMETRICA: le stesse righe in un
    altro ordine danno la stessa forma. Due tipi diversi nello stesso posto
    diventano un insieme ordinato dei due (`["NoneType", "str"]`)."""
    if first is None:
        return second
    if second is None:
        return first
    if isinstance(first, dict) and isinstance(second, dict):
        return {key: _merge(first.get(key), second.get(key))
                for key in sorted(set(first) | set(second))}
    kinds: set[str] = set()
    for one in (first, second):
        if isinstance(one, list):
            kinds |= set(one)
        else:
            kinds.add(one if isinstance(one, str) else json.dumps(one, sort_keys=True))
    return sorted(kinds) if len(kinds) > 1 else kinds.pop()


def shape(value):
    """La forma di una risposta: i tipi al posto dei valori.

    Di un elenco: quante righe, e l'UNIONE delle forme di tutte le righe -- un
    campo che compare solo in alcune e' una differenza di forma anche lui. Un
    elenco vuoto ha `di: null`: confrontato con uno pieno non dice niente
    (`without_lengths` lo sa).
    """
    if isinstance(value, dict):
        keys = [str(key) for key in value]
        if len(keys) > RECORD_KEY_LIMIT or any(_is_identifier(key) for key in keys):
            merged = None
            for item in value.values():
                merged = _merge(merged, shape(item))
            return {ANY_KEY: merged}
        return {str(key): shape(item) for key, item in value.items()}
    if isinstance(value, list):
        merged = None
        for item in value:
            merged = _merge(merged, shape(item))
        return {"elenco": len(value), "di": merged}
    return type(value).__name__


def live_shapes(fetch) -> dict:
    """Per ogni rotta di `live_routes()`: la forma, o il motivo per cui non c'e'.

    `fetch(percorso) -> bytes` e' la porta di sola lettura (`casa.hiris_get`);
    una rotta che rifiuta (per esempio perche' vuole un parametro) si registra
    col suo rifiuto: anche quello e' cio' che esce da quella porta."""
    shapes = {}
    for route in live_routes():
        try:
            shapes[route] = shape(json.loads(fetch(route)))
        except SystemExit as refusal:
            shapes[route] = {"rifiuto": str(refusal).rsplit(" ", 1)[-1]}
        except ValueError:
            shapes[route] = {"rifiuto": "non JSON"}
    return shapes


#: I metodi del client che la casa congelata NON ha. Lista di AMMISSIONE:
#: ogni voce col suo perche'. Il prodotto li chiede con
#: `getattr(ha_client, nome, None)` e, se mancano, tace senza affermare
#: niente: e' la forma che dichiara «questa casa non risponde a questo».
UNCAPTURED: dict[str, str] = {
    "extract_from_target": (
        "il confronto dell'albero con Home Assistant: la risposta dipende dal "
        "bersaglio e la cattura non la congela. Con `FrozenHouse` di prima il "
        "primo giro falliva intero e non scriveva niente; con la sola casa "
        "finta che TACE (`silence=`) il giro si chiude e il nucleo dice «su 3 "
        "aree il confronto non si e' potuto fare» -- misurato il 03/10/2026, "
        "4 differenze nello scatto della casa vera. Una casa congelata non e' "
        "una casa che tace: e' una casa a cui questa domanda non si fa"),
}


class FrozenHouse(CasaFinta):
    """Home Assistant fermo al momento della cattura: `CasaFinta` sugli
    ingressi congelati (Tappa 2, Task 4, 03/10/2026), meno i metodi di
    `UNCAPTURED`. Tutto il resto e' il client vero."""


for _name in UNCAPTURED:
    setattr(FrozenHouse, _name, None)


@contextlib.contextmanager
def frozen_clock(clock: float):
    """L'orologio fermo: chi legge `time.time()` durante lo scatto legge `clock`."""
    with mock.patch("time.time", return_value=clock):
        yield


#: Cio' che l'avvio legge dall'ambiente e che lo scatto deve fissare: la
#: cartella dei dati e i due indirizzi verso cui non si deve uscire.
def _environment(data_dir: str) -> dict[str, str]:
    return {"HIRIS_DATA_DIR": data_dir,
            "USAGE_DATA_PATH": str(Path(data_dir) / "usage.json"),
            "HA_BASE_URL": NOWHERE,
            "HIRIS_ALLOW_NO_TOKEN": "1"}


@contextlib.asynccontextmanager
async def mounted(inputs: dict, data_dir: str, house_class=None):
    """L'app del prodotto, avviata davvero su una casa congelata.

    Consegnata dopo l'avvio INTERO: `_on_startup`, la prima connessione del
    websocket e le riletture che quella ha rimandato.

    `house_class` e' la classe messa al posto di `HAClient`, costruita con la
    firma di `HAClient` (le prove ne passano una che conta o che ricorda);
    senza, e' `FrozenHouse` sugli `inputs`.
    """
    def frozen(base_url=None, token=None):
        return FrozenHouse(inputs)

    with mock.patch.dict(os.environ, _environment(data_dir)), \
            mock.patch.object(server, "HAClient", house_class or frozen):
        app = server.create_app()
        # Zitto SOLO mentre l'avvio e lo spegnimento girano: chi usa l'app nel
        # mezzo (le prove con `caplog`) deve vedere i log di `hiris.*` al
        # livello di sempre, o un «non logga X» sarebbe verde a vuoto.
        quiet = logging.getLogger("hiris")
        level = quiet.level
        try:
            quiet.setLevel(logging.CRITICAL)
            try:
                await asyncio.wait_for(server._on_startup(app), timeout=STARTUP_TIMEOUT_S)
                # L'avvio intero: anche la prima connessione e cio' che ha
                # rimandato. Un'app consegnata prima avrebbe le riletture
                # della prima connessione in volo mentre la si usa.
                await asyncio.wait_for(app["ha_client"]._first_connection_settled(),
                                       timeout=STARTUP_TIMEOUT_S)
            finally:
                quiet.setLevel(level)
            yield app
        finally:
            quiet.setLevel(logging.CRITICAL)
            try:
                await asyncio.wait_for(server._on_cleanup(app), timeout=STARTUP_TIMEOUT_S)
            finally:
                quiet.setLevel(level)


def _ordered(value):
    """Tutto cio' che e' un insieme diventa una lista ordinata: l'ordine di un
    insieme non e' un fatto della casa."""
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, dict):
        return {str(key): _ordered(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_ordered(item) for item in value]
    return value


def _cards(home_space: dict, entries: list, mirror) -> dict:
    cards: dict[str, dict] = {}
    references = (
        [("entita", entity["id"]) for entity in home_space["entita"]]
        + [("dispositivo", device["id"]) for device in home_space["dispositivi"]]
        + [("area", area["id"]) for area in home_space["aree"]]
        + [("integrazione", platform) for platform in sorted(
            {entity["piattaforma"] for entity in home_space["entita"]
             if entity.get("piattaforma")})])
    for kind, reference in references:
        cards[f"{kind}:{reference}"] = queries.view(
            House(home_space, mirror), entries, [], kind, reference)
    return cards


def _selections(home_space: dict, entries: list, mirror, clock: float) -> dict:
    wanted = {"senza filtri": {},
              "con nascoste e servizio": {"include_hidden": True, "include_service": True}}
    for area in home_space["aree"]:
        wanted[f"area:{area['id']}"] = {"area": area["nome"]}
    for platform in sorted({entity["piattaforma"] for entity in home_space["entita"]
                            if entity.get("piattaforma")}):
        wanted[f"integrazione:{platform}"] = {"platform": platform}
    selections = {}
    for label, filters in wanted.items():
        selection = House(home_space, mirror).select(
            house_query.HouseFilters(**filters), ("entita",), entries, now=clock)
        selections[label] = {"entita": [entry["id"] for entry, _area, _where
                                        in selection.entities],
                             "escluse": selection.excluded}
    return selections


def _tool_calls(home_space: dict) -> dict[str, tuple[str, dict]]:
    """Le chiamate fisse agli strumenti di lettura. Le entita' campione sono
    prese IN POSIZIONE FISSA dall'anagrafe ordinata per id: stessi ingressi,
    stesse chiamate."""
    calls: dict[str, tuple[str, dict]] = {"search()": ("search", {})}
    for area in home_space["aree"]:
        calls[f"search(area={area['id']})"] = ("search", {"area": area["nome"]})
    domains: dict[str, int] = {}
    for entity in home_space["entita"]:
        domain = entity["id"].split(".", 1)[0]
        domains[domain] = domains.get(domain, 0) + 1
    busiest = sorted(domains, key=lambda name: (-domains[name], name))[:BUSIEST_DOMAINS]
    for domain in busiest:
        calls[f"search(tipo={domain})"] = ("search", {"tipo": domain})
    ordered = sorted(home_space["entita"], key=lambda entity: entity["id"])
    positions = sorted({round(index * (len(ordered) - 1) / (SAMPLED_ENTITIES - 1))
                        for index in range(SAMPLED_ENTITIES)}) if ordered else []
    for position in positions:
        entity = ordered[position]
        calls[f"search(riferimento=#{position})"] = (
            "search", {"riferimento": entity["id"]})
        calls[f"fetch(riferimento=#{position})"] = (
            "fetch", {"riferimento": entity["id"]})
        if entity.get("nome"):
            calls[f"search(nome=#{position})"] = ("search", {"nome": entity["nome"]})
    return calls


def _fixed_texts() -> dict:
    texts = {
        "claude_runner.BASE_IDENTITY": claude_runner.BASE_IDENTITY,
        "claude_runner.BASE_TOOL_RULES": claude_runner.BASE_TOOL_RULES,
        "agent.prompts._GUIDE_WITH_TOOLS": bridge_prompts._GUIDE_WITH_TOOLS,
        "agent.prompts._GUIDE_WITHOUT_TOOLS": bridge_prompts._GUIDE_WITHOUT_TOOLS,
        "mind.observer.SYSTEM": observer.SYSTEM,
        "mind.recipe_turn.SYSTEM": recipe_turn.SYSTEM,
        "mind.analyst_turn.SYSTEM": analyst_turn.SYSTEM,
        "mind.actuator_turn.SYSTEM": actuator_turn.SYSTEM,
    }
    return {name: {"caratteri": len(text), "testo": text} for name, text in texts.items()}


async def _shoot(inputs: dict, clock: float, data_dir: str) -> dict:
    async with mounted(inputs, data_dir) as app:
        return await _ports(app, clock)


async def _ports(app, clock: float) -> dict:
    store, cache = app["home_space_store"], app["entity_cache"]
    home_space, entries = store.read(), store.behavior()
    mirror = topology.live_mirror(cache.all_states())
    text, summary = handlers_home_space.compose_briefing(app)
    dispatcher = handlers_chat.create_tool_dispatcher(app)
    answers = {}
    for label, (name, arguments) in _tool_calls(home_space).items():
        answers[label] = await dispatcher.dispatch(name, arguments)
    catalog = {tool["name"]: {"caratteri": len(json.dumps(tool, ensure_ascii=False)),
                              "definizione": tool} for tool in KNOWLEDGE_TOOLS}
    return {
        "albero": topology.hierarchy(home_space),
        "visibili": briefing.digest_visible_entity_ids(home_space),
        "nucleo": {"caratteri": len(text), "testo": text, "riepilogo": summary},
        "schede": _cards(home_space, entries, mirror),
        "selezioni": _selections(home_space, entries, mirror, clock),
        "osservatore": observer.house_lines(home_space),
        "ricette": {device["id"]: recipe_turn.device_lines(home_space, device["id"])
                    for device in home_space["dispositivi"]},
        "strumenti": answers,
        "catalogo": catalog,
        "prompt": _fixed_texts(),
    }


def shoot(inputs: dict, *, clock: float) -> dict:
    """Lo scatto: ogni porta di `PORTS` sugli ingressi dati, a orologio fermo.

    Passa da JSON e torna: cio' che si confronta e' cio' che si salverebbe.
    """
    with tempfile.TemporaryDirectory(prefix="fotografia-") as data_dir, frozen_clock(clock):
        raw = asyncio.run(_shoot(inputs, clock, data_dir))
    return json.loads(json.dumps(_ordered(raw), ensure_ascii=False, sort_keys=True,
                                 default=str))


def _walk(first, second, path: str, out: list[str], shapes_only: bool = False) -> None:
    if shapes_only and _unknown_rows(first, second):
        return
    if isinstance(first, dict) and isinstance(second, dict):
        for key in sorted(set(first) | set(second)):
            here = f"{path}.{key}" if path else str(key)
            if key not in first:
                out.append(f"{here}: assente -> presente")
            elif key not in second:
                out.append(f"{here}: presente -> assente")
            else:
                _walk(first[key], second[key], here, out, shapes_only)
        return
    if isinstance(first, list) and isinstance(second, list):
        if len(first) != len(second):
            out.append(f"{path}: {len(first)} voci -> {len(second)} voci")
            return
        for index, (one, other) in enumerate(zip(first, second, strict=True)):
            _walk(one, other, f"{path}[{index}]", out, shapes_only)
        return
    if first != second:
        out.append(f"{path}: {_brief(first)} -> {_brief(second)}")


def _brief(value) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= 80 else text[:77] + "..."


def without_lengths(value):
    """Una forma senza le lunghezze degli elenchi: fra un «prima» e un «dopo»
    presi dal vivo la casa aggiunge righe, e quello non e' un cambio di forma."""
    if isinstance(value, dict):
        return {key: without_lengths(item) for key, item in value.items()
                if not (key == "elenco" and "di" in value)}
    return value


def _unknown_rows(first, second) -> bool:
    """Uno dei due e' la forma di un elenco VUOTO: delle sue righe non si sa
    niente, e «niente» contro «qualcosa» non e' un cambio di forma."""
    return any(isinstance(one, dict) and set(one) == {"di"} and one["di"] is None
               for one in (first, second))


def compare(first: dict, second: dict, *, shapes_only: bool = False) -> list[str]:
    """Una riga per differenza: dove, e da cosa a cosa. Oltre
    `DIFFERENCES_SHOWN` righe l'ultima dice quante ne restano: una differenza
    taciuta sarebbe una fotografia che mente.

    `shapes_only` vale per le fotografie dal vivo (`forme`): confronta chiavi e
    tipi e non quante righe ha un elenco."""
    if shapes_only:
        first, second = without_lengths(first), without_lengths(second)
    found: list[str] = []
    _walk(first, second, "", found, shapes_only)
    if len(found) <= DIFFERENCES_SHOWN:
        return found
    hidden = len(found) - DIFFERENCES_SHOWN
    return found[:DIFFERENCES_SHOWN] + [
        f"... e altre {hidden} differenze ({len(found)} in tutto)"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    shooting = commands.add_parser("scatta", help="fotografa le porte a freddo")
    shooting.add_argument("--ingressi", required=True)
    shooting.add_argument("--in", dest="target", required=True)
    shaping = commands.add_parser("forme", help="le forme delle rotte, dal vivo")
    shaping.add_argument("--in", dest="target", required=True)
    comparing = commands.add_parser("confronta", help="esce 1 se due fotografie differiscono")
    comparing.add_argument("first")
    comparing.add_argument("second")
    comparing.add_argument("--forme", action="store_true",
                           help="due fotografie dal vivo: non conta le righe degli elenchi")
    args = parser.parse_args()

    if args.command == "scatta":
        clock = float(casa.manifest_of(args.ingressi)["catturata_ts"])
        photo = shoot(casa.read_inputs(args.ingressi), clock=clock)
        target = casa.outside_repo(args.target)
        target.write_text(json.dumps(photo, ensure_ascii=False, sort_keys=True),
                          encoding="utf-8")
        for port in PORTS:
            print(f"  {port:12} {len(json.dumps(photo[port], ensure_ascii=False)):>9,} caratteri")
        print(f"fotografia: {target}")
        return
    if args.command == "forme":
        target = casa.outside_repo(args.target)
        casa.hiris_get("/api/health")  # senza una casa dichiarata ci si ferma QUI
        shapes = live_shapes(casa.hiris_get)
        target.write_text(json.dumps(shapes, ensure_ascii=False, sort_keys=True, indent=1),
                          encoding="utf-8")
        refused = sorted(route for route, found in shapes.items() if "rifiuto" in found)
        print(f"forme: {len(shapes)} rotte in {target}; rifiutate: {refused or 'nessuna'}")
        return
    first, second = (json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
                     for path in (args.first, args.second))
    differences = compare(first, second, shapes_only=args.forme)
    for line in differences:
        print(line)
    print(f"fotografia: {len(differences)} differenze" if differences
          else "fotografia: 0 differenze")
    sys.exit(1 if differences else 0)


if __name__ == "__main__":
    main()
