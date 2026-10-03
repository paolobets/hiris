#!/usr/bin/env python3
"""HIRIS casa finta — il client vero di Home Assistant, col trasporto sostituito.

## Perche' esiste

Le prove e gli attrezzi avevano una casa finta per ogni bisogno: `FrozenHouse`
nella fotografia delle porte, `CountingHouse` nel contatore d'avvio, `_House`
nelle prove della cattura, e decine di classi nelle prove del prodotto. Ognuna
imitava a mano i METODI PUBBLICI di `HAClient`: la forma della risposta, il
filtro di `get_states`, gli errori erano scritti una seconda volta, e potevano
mentire -- misurato il 03/10/2026, diciassette finte ignoravano il filtro e
quattro sollevavano dove il vero non solleva (piano della Tappa 2, T-01, T-04).

`CasaFinta` E' un `HAClient` (decisione D8 del proprietario, 03/10/2026). Non
imita nessun metodo: sostituisce solo il TRASPORTO -- l'invio WebSocket
`_ws_send` e la sessione HTTP su cui il vero `_rest_get` fa le sue `GET` -- e
risponde con i messaggi GREZZI di Home Assistant, ricostruiti dagli ingressi
(quelli che `scripts/casa.py cattura` congela dalla casa, o quelli sintetici
delle prove). Forma, filtro e busta d'errore sono quelli del codice vero per
costruzione, e un metodo nuovo del client arriva qui per ereditarieta': non
c'e' un elenco di metodi da tenere allineato.

## La forma dei messaggi: letta, non indovinata

Ogni messaggio grezzo e' ricostruito da cio' che il client estrae (il suo
sorgente dice quale chiave legge di ogni risposta) e dalla fonte di Home
Assistant, letta sul tag `2026.9.4` il 03/10/2026:

- la busta WebSocket: `websocket_api/messages.py` -- `result_message`
  `{"id", "type": "result", "success": true, "result"}`, `error_message`
  `{"id", "type": "result", "success": false, "error": {"code", "message"}}`;
- `automation/config`, `script/config`: `{"config": raw_config}`, e per
  un'entita' che non c'e' `not_found` / «Entity not found»
  (`automation/__init__.py`, `script/__init__.py`, `websocket_config`);
- `lovelace/config`: per una plancia senza corpo `config_not_found` / «No
  config found.», per un percorso sconosciuto `config_not_found` / «Unknown
  config specified: <percorso>» (`lovelace/websocket.py`);
- `config/entity_registry/list` manda `as_partial_dict`, SENZA `aliases`;
  `config/entity_registry/get_entries` manda `{entity_id: extended_dict |
  None}`, e `extended_dict` e' la riga parziale piu' `aliases`
  (`helpers/entity_registry.py`, `config/entity_registry.py`).

**Cio' che gli ingressi non portano, dichiarato.** Gli ingressi sono cio' che i
metodi del client hanno RESTITUITO, non i messaggi interi. Dove il client
scarta qualcosa, qui non c'e':

- `recorder/list_statistic_ids`: solo `statistic_id` per riga (Home Assistant
  manda anche unita', fonte, nome: il client li scarta);
- `get_entries`: la riga e i suoi `aliases`, senza `capabilities`,
  `device_class`, `original_device_class`, `original_icon` (il client legge
  solo gli alias);
- `repairs/list_issues`: le voci IGNORATE dall'utente non ci sono (il client le
  scarta prima di restituire);
- `lovelace/config` di una plancia senza corpo: quale dei due rifiuti di Home
  Assistant sia arrivato non e' negli ingressi (il client li legge uguali).

## Un comando non servito solleva, e non si inghiotte

Un comando che gli ingressi non portano solleva `UnservedCommand` col suo
nome. **Non e' un `Exception`**, di proposito: il prodotto non si fida di Home
Assistant e avvolge molte letture in `except Exception`; li' una finta che
manca diventerebbe «Home Assistant non ha risposto», e una prova verde per la
ragione sbagliata (piano della Tappa 2, «Cosa guardare in revisione», 2).
Chi vuole il silenzio lo inietta (`silence=`), e allora e' il silenzio vero.

Uso (dalle prove e dagli attrezzi):
    house = CasaFinta(inputs)                                   # gli ingressi
    house = CasaFinta(inputs, refuse={"repairs/list_issues":
                                      {"code": "unknown_command", "message": "..."},
                                      "/api/states": 500})
    house = CasaFinta(inputs, silence={"system_log/list"})
    house = CasaFinta(inputs, answers={"search/related": lambda extra: {...}})
    house.calls, house.connections                             # cosa ha chiesto
"""
from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import aiohttp

from hiris.app.proxy.ha_client import HAClient

#: Un indirizzo che rifiuta subito: chi parla con Home Assistant o col
#: Supervisor senza passare dal client (voce E-06 del registro) non deve ne'
#: uscire sulla rete ne' aspettare un DNS. La porta 9 e' «discard».
NOWHERE = "http://127.0.0.1:9"

#: Cio' che `CasaFinta` ridefinisce sopra `HAClient`. Lista di AMMISSIONE: un
#: metodo in piu' sovrascritto e' un pezzo di client che la finta smette di
#: provare, e va scritto qui con la ragione (`tests/test_casa_finta.py`).
TRANSPORT: dict[str, str] = {
    "_ws_send": "l'unico invio WebSocket: qui risponde dagli ingressi",
    "start": ("apre la sessione HTTP vera; qui la sessione e' quella finta, "
              "data alla nascita, e `start` non la sostituisce"),
}


class UnservedCommand(BaseException):
    """Un comando, o un percorso, che la casa finta non sa servire.

    `BaseException` e non `Exception`: vedi il docstring del modulo. Porta il
    nome di cio' che e' stato chiesto in `command`."""

    def __init__(self, command: str, reason: str = "") -> None:
        super().__init__(
            f"la casa finta non serve `{command}`"
            + (f": {reason}" if reason else
               ": gli ingressi non lo portano. Lo si aggiunge con `answers=`, "
               "`refuse=` o `silence=`, o la prova chiede qualcosa di nuovo"))
        self.command = command


def listener_kinds() -> tuple[str, ...]:
    """I generi di ascoltatori del client vero: i suoi `add_<genere>_listener`.

    Chiesti a `HAClient`, non ricopiati: un genere nuovo entra da solo nelle
    prove che confrontano la casa finta col client vero."""
    return tuple(sorted(name.removeprefix("add_").removesuffix("_listener")
                        for name in dir(HAClient)
                        if name.startswith("add_") and name.endswith("_listener")))


class SilentConnection:
    """Il websocket di una casa ferma: chiede l'autenticazione, la accetta, e
    poi tace -- una casa congelata non manda eventi.

    E' la `ClientSession` su cui gira il codice VERO del client
    (`HAClient._ws_loop`): cosi' la prima connessione fa cio' che fa in
    produzione -- l'iscrizione agli eventi e l'avviso «riconnessione» agli
    ascoltatori -- senza che qui se ne ricopi una riga. Le prove la danno
    anche al client vero, per confrontarlo con la casa finta sulla stessa
    connessione (`tests/test_costi_avvio.py`).
    """

    def __init__(self) -> None:
        self._replies: list[dict] = []
        self._tasks_before: set[asyncio.Task] = set()
        #: Acceso quando il client ha finito di avvisare gli ascoltatori della
        #: connessione e si mette in ascolto degli eventi.
        self.connected = asyncio.Event()
        #: I compiti nati mentre il client avvisava gli ascoltatori.
        self.deferred_work: set[asyncio.Task] = set()

    def ws_connect(self, url, **kwargs):
        self._replies = [{"type": "auth_required"}, {"type": "auth_ok"}]
        self._tasks_before = asyncio.all_tasks()
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def receive_json(self):
        return self._replies.pop(0)

    async def send_json(self, payload):
        return None

    def __aiter__(self):
        # Il client vero comincia ad ascoltare gli eventi solo DOPO aver
        # avvisato gli ascoltatori della connessione. Fra `ws_connect` e qui
        # non cede mai il passo al ciclo (la connessione finta non fa I/O):
        # i compiti nati nel frattempo sono tutti e soli i lavori che gli
        # ascoltatori hanno rimandato -- le riletture con antirimbalzo.
        self.deferred_work = asyncio.all_tasks() - self._tasks_before
        self.connected.set()
        return self

    async def __anext__(self):
        await asyncio.Event().wait()
        raise StopAsyncIteration

    async def close(self) -> None:
        return None


class _Response:
    """Una risposta HTTP finta: lo stato e il corpo JSON, come li legge il
    vero `_rest_get`."""

    def __init__(self, status: int, body=None) -> None:
        self.status = status
        self._body = body

    async def json(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _HouseSession(SilentConnection):
    """La sessione della casa finta: il websocket di lunga vita che tace, e le
    `GET` del vero `_rest_get` servite dagli ingressi. Una scrittura (`post`,
    `delete`) non e' servita: solleva nominando il percorso."""

    def __init__(self, house: CasaFinta) -> None:
        super().__init__()
        self._house = house

    def get(self, url: str, **kwargs):
        return self._house._rest_reply(url.removeprefix(self._house._base_url))

    def _write(self, url: str, **kwargs):
        path = url.removeprefix(self._house._base_url)
        self._house.calls.append((path, kwargs.get("json")))
        raise UnservedCommand(path, "e' una scrittura, e la casa finta non scrive")

    post = delete = _write


def _ok(result) -> dict:
    return {"type": "result", "success": True, "result": result}


def _refused(code, message) -> dict:
    return {"type": "result", "success": False, "error": {"code": code, "message": message}}


class CasaFinta(HAClient):
    """Home Assistant dagli ingressi, sotto il client vero.

    `inputs` ha la forma di `casa.read_inputs` (le chiavi di `casa.INPUTS`): un
    ingresso che manca rende non servito il comando che lo legge, e basta.
    `answers` aggiunge comandi WS o percorsi REST (`{nome: f(extra) ->
    result}`; per un percorso `f(percorso)` -> corpo, e la chiave vale anche
    come prefisso); `refuse` li fa rifiutare (WS: `{"code", "message"}`, il
    corpo d'errore di Home Assistant; REST: lo stato HTTP); `silence` li fa
    tacere (WS: nessuna risposta; REST: la connessione cade).

    Registra `calls` -- `(comando o percorso, extra)` nell'ordine -- e
    `connections` -- `("ws", comandi)` per ogni `_ws_send`, `("rest",
    percorso)` per ogni `GET`.
    """

    def __init__(self, inputs: dict, *,
                 answers: dict[str, Callable] | None = None,
                 refuse: dict[str, object] | None = None,
                 silence=()) -> None:
        super().__init__(NOWHERE, "casa-finta")
        self._inputs = inputs
        self._answers = dict(answers or {})
        self._refuse = dict(refuse or {})
        self._silence = set(silence)
        self._session = _HouseSession(self)
        # Acceso dalla nascita, come lo era in `FrozenHouse`: chi aspetta il
        # nucleo di Home Assistant (`panel_visibility`) non aspetta una casa
        # che c'e' gia'. La prima connessione lo riaccende comunque.
        self.ws_ready.set()
        self.calls: list[tuple[str, object]] = []
        self.connections: list[tuple[str, object]] = []

    async def start(self) -> None:
        return None

    def mute(self, *commands: str) -> None:
        """Da qui in poi questi comandi (o percorsi REST) tacciono, come
        `silence=` alla nascita: per la casa che smette di rispondere a meta'
        prova."""
        self._silence.update(commands)

    def unmute(self, *commands: str) -> None:
        """Da qui in poi questi comandi tornano a rispondere: Home Assistant
        che si riprende dopo un silenzio."""
        self._silence.difference_update(commands)

    async def _first_connection_settled(self) -> None:
        """Aspetta la prima connessione e i lavori che ha rimandato: e' li'
        che l'avvio e' finito davvero («avvio intero», D1 della Tappa 2). Si
        aspetta l'evento, non un tempo: l'antirimbalzo delle riletture e' di
        qualche secondo, e un `sleep` sarebbe o troppo corto o sprecato.
        Un websocket mai aperto non ha niente da aspettare."""
        if self._ws_task is None:
            return
        await self._session.connected.wait()
        await asyncio.gather(*self._session.deferred_work, return_exceptions=True)

    # ── il trasporto ────────────────────────────────────────────────────────

    async def _ws_send(self, commands, timeout: float = 10.0) -> list[dict | None]:
        """Come il vero: nessun comando, nessuna connessione; N comandi, UNA
        connessione e N messaggi interi in ordine (`None` = senza risposta)."""
        if not commands:
            return []
        self.connections.append(("ws", tuple(msg_type for msg_type, _ in commands)))
        replies: list[dict | None] = []
        for msg_id, (msg_type, extra) in enumerate(commands, start=1):
            self.calls.append((msg_type, extra))
            reply = self._ws_reply(msg_type, extra)
            replies.append(None if reply is None else {"id": msg_id, **reply})
        return replies

    def _ws_reply(self, msg_type: str, extra: dict | None) -> dict | None:
        if msg_type in self._silence:
            return None
        if msg_type in self._refuse:
            error = self._refuse[msg_type]
            return _refused(error.get("code"), error.get("message"))
        if msg_type in self._answers:
            return _ok(self._answers[msg_type](extra))
        if msg_type not in self._ws_served():
            raise UnservedCommand(msg_type)
        source, reply = self._ws_served()[msg_type]
        return reply(extra, self._input(msg_type, source))

    def _rest_reply(self, path: str) -> _Response:
        self.connections.append(("rest", path))
        self.calls.append((path, None))
        bare = path.split("?", 1)[0]
        if bare in self._silence:
            raise aiohttp.ClientConnectionError("casa finta: silenzio iniettato")
        if bare in self._refuse:
            return _Response(int(self._refuse[bare]))
        answer = self._answers.get(bare) or next(
            (f for key, f in sorted(self._answers.items(), key=lambda item: -len(item[0]))
             if key.startswith("/") and bare.startswith(key)), None)
        if answer is not None:
            return _Response(200, answer(path))
        if bare not in self._REST_SERVED:
            raise UnservedCommand(bare)
        return _Response(200, self._input(bare, self._REST_SERVED[bare]))

    # ── cio' che gli ingressi servono ───────────────────────────────────────

    #: I percorsi REST, e l'ingresso che porta il loro corpo.
    _REST_SERVED: ClassVar[dict[str, str]] = {"/api/states": "states",
                                              "/api/services": "services"}

    def served(self) -> set[str]:
        """I comandi WS e i percorsi REST che questa casa sa servire: dagli
        ingressi che ha, piu' le risposte aggiunte."""
        sources = {**{name: source for name, (source, _reply)
                      in self._ws_served().items()}, **self._REST_SERVED}
        return set(self._answers) | {name for name, source in sources.items()
                                     if source.split(".", 1)[0] in self._inputs}

    def _input(self, command: str, source: str):
        """L'ingresso `source` (`nome` o `nome.chiave`), o il comando non e'
        servito."""
        if source.split(".", 1)[0] not in self._inputs:
            raise UnservedCommand(command, f"manca l'ingresso `{source}`")
        value = self._inputs
        for key in source.split("."):
            value = value[key]
        return value

    def _ws_served(self) -> dict[str, tuple[str, Callable]]:
        """`{comando: (ingresso, risposta(extra, valore dell'ingresso))}`."""
        served: dict[str, tuple[str, Callable]] = {
            "get_config": ("ha_config", lambda extra, config: _ok(config)),
            "recorder/list_statistic_ids": ("statistic_ids", lambda extra, ids: _ok(
                [{"statistic_id": identifier} for identifier in ids])),
            "repairs/list_issues": ("problems.problemi",
                                    lambda extra, issues: _ok({"issues": issues})),
            "system_log/list": ("system_log.voci", lambda extra, rows: _ok(rows)),
            "frontend/get_translations": ("translations", self._translations),
            "automation/config": ("behavior.configurazioni", self._behavior),
            "script/config": ("behavior.configurazioni", self._behavior),
            "lovelace/dashboards/list": ("dashboards", self._dashboard_list),
            "lovelace/config": ("dashboards", self._dashboard_config),
            "config/entity_registry/get_entries": ("registries.entita",
                                                   self._extended_entries),
        }
        # I registri si chiedono alla tabella del client, non si ricopiano.
        for key, msg_type, _extra in HAClient._REGISTRIES:
            served[msg_type] = (f"registries.{key}",
                                self._categories if key == "categorie" else
                                self._entities if key == "entita" else
                                lambda extra, rows: _ok(rows))
        return served

    @staticmethod
    def _entities(extra, rows):
        # `as_partial_dict` non porta gli alias: viaggiano con le voci estese
        # (`_extended_entries`).
        return _ok([{name: value for name, value in row.items() if name != "aliases"}
                    for row in rows])

    @staticmethod
    def _categories(extra, rows):
        scope = (extra or {}).get("scope")
        return _ok([{name: value for name, value in row.items() if name != "ambito"}
                    for row in rows if row.get("ambito") == scope])

    @staticmethod
    def _extended_entries(extra, rows):
        by_id = {row.get("entity_id"): row for row in rows}
        found = {}
        for entity_id in (extra or {}).get("entity_ids", []):
            row = by_id.get(entity_id)
            found[entity_id] = None if row is None else {
                **{name: value for name, value in row.items() if name != "aliases"},
                "aliases": list(row.get("aliases") or [])}
        return _ok(found)

    @staticmethod
    def _translations(extra, held):
        asked = ((extra or {}).get("language"), (extra or {}).get("category"))
        if asked != (held["language"], held["category"]):
            raise UnservedCommand(
                "frontend/get_translations",
                f"chieste per {asked}, gli ingressi le portano per "
                f"({held['language']}, {held['category']})")
        return _ok({"resources": held["report"]["risorse"]})

    @staticmethod
    def _behavior(extra, known):
        entity_id = (extra or {}).get("entity_id")
        if entity_id not in known:
            return _refused("not_found", "Entity not found")
        return _ok({"config": known[entity_id]})

    @staticmethod
    def _dashboards(held: dict) -> tuple[list[dict], dict]:
        listing = [{name: value for name, value in entry.items() if name != "config"}
                   for entry in held["entries"] if entry.get("url_path") is not None]
        configs = {entry.get("url_path"): entry.get("config") for entry in held["entries"]}
        if None not in configs:
            raise UnservedCommand(
                "lovelace/config", "gli ingressi non portano la plancia principale, "
                "che il client chiede sempre: non vengono da `read_dashboards`")
        rebuilt = [path or "principale" for path, config in configs.items()
                   if not isinstance(config, dict)]
        if list(held["unavailable"]) != rebuilt:
            # «elenco: ...» o un percorso duplicato: il messaggio che li ha
            # prodotti non e' ricostruibile dagli ingressi.
            raise UnservedCommand(
                "lovelace/dashboards/list",
                f"le plance non disponibili degli ingressi ({held['unavailable']}) "
                "non si ricostruiscono dalle plance")
        return listing, configs

    def _dashboard_list(self, extra, held):
        return _ok(self._dashboards(held)[0])

    def _dashboard_config(self, extra, held):
        path = (extra or {}).get("url_path")
        configs = self._dashboards(held)[1]
        if path not in configs:
            return _refused("config_not_found", f"Unknown config specified: {path}")
        if not isinstance(configs[path], dict):
            return _refused("config_not_found", "No config found.")
        return _ok(configs[path])

