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

- `energy/get_prefs`: `manager.data` intero, `{"energy_sources",
  "device_consumption", "device_consumption_water"}`, la rete a campi singoli
  (`components/energy/data.py`, `websocket_api.py::ws_get_prefs`). Il suo
  ingresso, `energy_prefs`, la cattura ancora non lo prende (non e' in
  `casa.INPUTS`): lo da' la prova che lo chiede, e senza il comando resta non
  servito, come per ogni ingresso che manca.

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

## Le scritture si registrano, e non si eseguono

`call_service`, le tre primitive della configurazione (`read_configuration`
compresa: passa dallo stesso canale), gli helper, le etichette, il pannello:
il client vero le manda, la casa finta le REGISTRA in `calls` e risponde cio'
che la prova le ha detto di rispondere. Non esegue niente: una casa che
«ricorda» cio' che si e' salvato la scrive la prova, dentro la sua risposta.
Le scritture REST si nominano col metodo davanti al percorso (`"POST
/api/services/light/turn_on"`, `"DELETE /api/config/automation/config/1"`):
lo stesso percorso e' una lettura con `GET` e una scrittura con `POST`. Una
`GET` resta il percorso nudo.

**La forma delle risposte, letta sul tag `2026.9.4` il 04/10/2026**
(`helpers/http.py::HomeAssistantView.json_message`,
`components/config/view.py`, `components/api/__init__.py`):

- un rifiuto REST di Home Assistant e' `{"message": testo}` (piu' `"code"`
  quando c'e') con lo stato HTTP: `GET` di una chiave che non c'e' -> 404
  «Resource not found», `DELETE` di una chiave che non c'e' -> 400
  «Resource not found», un corpo non valido -> 400 «Message malformed: ...»;
  un servizio sconosciuto o dati non validi -> `HTTPBadRequest`, cioe' 400
  col corpo di testo «400: Bad Request», che non e' JSON. `Refused(stato)`
  senza testo e' quella forma; `Refused(stato, testo)` la prima;
- una scrittura di configurazione riuscita: `{"result": "ok"}`;
- `POST /api/services/<dominio>/<servizio>` riuscita: la lista degli stati
  cambiati durante la chiamata (senza `?return_response`, che il client non
  chiede).

## Le risposte nel tempo

- **Per argomento**: una risposta e' una funzione di cio' che e' stato
  chiesto (`extra` per un comando WS, il percorso per una `GET`, percorso e
  corpo per una scrittura), e puo' rendere `Refused(...)` o `SILENT` invece di
  un risultato: un rifiuto o un silenzio per quella domanda sola, anche dentro
  una raffica che per il resto risponde. `Silence(motivo)` e' il silenzio con
  un motivo suo (la connessione che cade con quel messaggio).
- **Per chiamata successiva**: `in_turn(a, b, ...)` risponde `a` alla prima
  domanda, `b` alla seconda; finita la sequenza solleva `UnservedCommand`.
- **Dopo un ritardo, o mai**: `delay={nome: secondi}` fa arrivare la risposta
  dopo quei secondi; `math.inf` non la fa arrivare mai; un `asyncio.Event` la
  trattiene finche' la prova non lo accende. Sul WebSocket vale il tetto
  `timeout` del vero `_ws_send`: oltre, la risposta e' `None` come dal vero
  (il tetto vale per la connessione intera, non per messaggio). Una `GET` o
  una scrittura non hanno tetto nel client: aspettano.
- **Gli annunci**: `announce(tipo, dati)` fa arrivare un evento del bus agli
  ascoltatori del client, dallo smistamento vero (`_dispatch_bus_event`), in
  modo sincrono: e' cio' che serve a far arrivare un `state_changed` DENTRO
  una chiamata. Il ciclo d'ascolto vero (`_listen`) si prova con
  `SilentConnection.push_event`.

Uso (dalle prove e dagli attrezzi):
    house = CasaFinta(inputs)                                   # gli ingressi
    house = CasaFinta(inputs, refuse={"repairs/list_issues":
                                      {"code": "unknown_command", "message": "..."},
                                      "/api/states": 500})
    house = CasaFinta(inputs, silence={"system_log/list"})
    house = CasaFinta(inputs, answers={"search/related": lambda extra: {...}})
    house = CasaFinta(inputs, answers={
        "POST /api/services/": lambda path, body: [],
        "frontend/get_translations": in_turn(SILENT, {"resources": {}})},
        delay={"/api/states": math.inf})
    house.calls, house.connections                             # cosa ha chiesto
"""
from __future__ import annotations

import asyncio
import http
import json
import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import aiohttp
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

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


class Refused:
    """Un rifiuto di Home Assistant per UNA domanda, reso da una risposta
    (`answers=`) o scritto in `refuse=`.

    Sul WebSocket `code` e' il codice d'errore (`"not_found"`) e `message` il
    testo: `{"success": false, "error": {"code", "message"}}`. Su REST `code`
    e' lo stato HTTP; con `message` il corpo e' `{"message": message}`
    (`json_message`), senza e' il testo di `HTTPBadRequest` e simili --
    «400: Bad Request», che non e' JSON."""

    def __init__(self, code, message: str = "") -> None:
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"Refused({self.code!r}, {self.message!r})"


class Silence:
    """Il silenzio per UNA domanda, reso da una risposta: sul WebSocket nessun
    messaggio (`None` dal vero `_ws_send`), su REST la connessione che cade --
    `aiohttp.ClientConnectionError` col motivo `reason`, che e' cio' che il
    chiamante vede risalire da una scrittura (il client non la avvolge)."""

    def __init__(self, reason: str = "casa finta: silenzio iniettato") -> None:
        self.reason = reason

    def __repr__(self) -> str:
        return f"Silence({self.reason!r})"


#: Il silenzio col motivo di sempre.
SILENT = Silence()


def in_turn(*replies) -> Callable:
    """Una risposta per chiamata successiva: la prima domanda riceve
    `replies[0]`, la seconda `replies[1]`. Ognuna e' un risultato, una
    funzione della domanda (chiamata con gli stessi argomenti), `Refused(...)`
    o `SILENT`. Finita la sequenza, la domanda in piu' solleva
    `UnservedCommand`: una prova che chiede piu' di quanto ha scritto lo deve
    vedere."""
    pending = list(replies)

    def reply(*asked):
        if not pending:
            raise UnservedCommand(
                "in_turn", f"la sequenza di {len(replies)} risposte e' finita")
        nxt = pending.pop(0)
        return nxt(*asked) if callable(nxt) else nxt
    return reply


async def _arrives(delay, timeout: float | None) -> bool:
    """Aspetta un ritardo iniettato: secondi, `math.inf` (mai) o un
    `asyncio.Event` (finche' non si accende). `False` se il tetto `timeout`
    scade prima."""
    if isinstance(delay, asyncio.Event):
        waiter = delay.wait()
    elif delay == math.inf:
        waiter = asyncio.Event().wait()
    else:
        waiter = asyncio.sleep(delay)
    if timeout is None:
        await waiter
        return True
    try:
        await asyncio.wait_for(waiter, timeout)
    except TimeoutError:
        return False
    return True


def listener_kinds() -> tuple[str, ...]:
    """I generi di ascoltatori del client vero: i suoi `add_<genere>_listener`.

    Chiesti a `HAClient`, non ricopiati: un genere nuovo entra da solo nelle
    prove che confrontano la casa finta col client vero."""
    return tuple(sorted(name.removeprefix("add_").removesuffix("_listener")
                        for name in dir(HAClient)
                        if name.startswith("add_") and name.endswith("_listener")))


#: La versione di Home Assistant il cui sorgente descrive i messaggi qui sotto:
#: viaggia nei messaggi dell'autenticazione come `ha_version`, come fa il vero.
HA_SOURCE_VERSION = "2026.9.4"

#: Cio' che Home Assistant scrive a un gettone che non riconosce
#: (`websocket_api/auth.py`, `async_handle`, righe 125-129 al tag 2026.9.4).
INVALID_TOKEN = "Invalid access token or password"

#: Il segno che chiude la connessione viva: dopo di lui l'iterazione finisce,
#: come quando Home Assistant chiude il websocket.
_DROPPED = object()


class _Text:
    """Un messaggio di testo del websocket, come aiohttp lo da' ad `async for`."""

    type = aiohttp.WSMsgType.TEXT

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class SilentConnection:
    """Il websocket di lunga vita di una casa ferma: chiede l'autenticazione,
    la accetta, conferma le iscrizioni, e poi tace -- una casa congelata non
    manda eventi finche' una prova non glieli fa mandare.

    E' la `ClientSession` su cui gira il codice VERO del client
    (`HAClient._ws_loop`): le iscrizioni, lo smistamento degli eventi,
    l'avviso «riconnessione» agli ascoltatori sono quelli di produzione, senza
    che qui se ne ricopi una riga. Le prove la danno anche al client vero, per
    confrontarlo con la casa finta sulla stessa connessione
    (`tests/test_costi_avvio.py`).

    **La forma dei messaggi, letta e non indovinata** (sorgente di Home
    Assistant al tag `2026.9.4`, letto il 03/10/2026):

    - l'autenticazione: `{"type": "auth_required", "ha_version"}`, poi
      `{"type": "auth_ok", "ha_version"}` oppure `{"type": "auth_invalid",
      "message"}`, e la connessione si chiude (`websocket_api/auth.py`:
      `AUTH_REQUIRED_MESSAGE`/`AUTH_OK_MESSAGE` righe 38-41,
      `auth_invalid_message` righe 44-46, il gettone sconosciuto righe
      125-129 con `raise Disconnect`);
    - un'iscrizione si conferma con `{"id", "type": "result", "success":
      true, "result": null}` (`commands.py`, `handle_subscribe_events`,
      `connection.send_result(msg["id"])` riga 220; `messages.py`,
      `result_message` righe 61-63);
    - un evento arriva con l'id DELL'ISCRIZIONE: `{"id", "type": "event",
      "event": {"event_type", "data", "origin", "time_fired", "context"}}`
      (`messages.py`, `cached_event_message` righe 123-139; `core.py`,
      `Event._as_dict` righe 1397-1412). Un evento a cui il client non si e'
      iscritto non arriva: `push_event` lo dice rendendo `False`;
    - `config_entries/subscribe` conferma, poi manda UN evento con l'elenco
      intero, `[{"type": null, "entry": ...}]`, e da li' un evento per ogni
      cambio, `[{"type": "added" | "removed" | "updated", "entry": ...}]`
      (`components/config/config_entries.py`, `config_entries_subscribe`
      righe 660-711; i tre valori: `ConfigEntryChange` in
      `homeassistant/config_entries.py` righe 224-229; la voce e'
      `ConfigEntry.as_json_fragment`, righe 658-685). Non chiede
      l'amministratore: nessun `require_admin` su quel comando.

    Cosa sa fare per le prove: `refuse_next_auth()` (il gettone rifiutato
    alla prossima connessione), `push_event(tipo, dati)` e
    `push_config_entry_change(cambio, voce)` (Home Assistant che parla),
    `drop()` (la connessione che cade), `core_state` (lo stato del nucleo che
    `get_config` dichiara: `RUNNING`, o `STARTING` per una casa in avvio).
    Registra `opened` (le connessioni
    aperte), `listening` (quelle arrivate in ascolto degli eventi) e `sent`
    (cio' che il client ha mandato dopo l'autenticazione, il gettone escluso:
    e' una credenziale). Un comando che non sa servire solleva
    `UnservedCommand` col suo nome.
    """

    def __init__(self) -> None:
        self._replies: list[dict] = []
        self._tasks_before: set[asyncio.Task] = set()
        self._auth_refusals: list[str] = []
        self._inbox: asyncio.Queue = asyncio.Queue()
        self._subscriptions: dict[str, int] = {}
        self._entries_subscription: int | None = None
        #: Acceso quando il client si mette in ascolto degli eventi.
        self.connected = asyncio.Event()
        #: I compiti nati fra l'apertura dell'ultima connessione e l'ascolto:
        #: i lavori che il client ha rimandato avvisando gli ascoltatori.
        self.deferred_work: set[asyncio.Task] = set()
        self.opened = 0
        self.listening = 0
        self.sent: list[dict] = []
        #: Lo stato del nucleo che `get_config` dichiara (`CoreState`, vedi
        #: `ha_client.STARTED_EVENT` per la fonte): una prova lo mette a
        #: `STARTING` per una casa che si sta ancora avviando.
        self.core_state = "RUNNING"

    # ── cio' che una prova fa fare a Home Assistant ─────────────────────────

    def refuse_next_auth(self, message: str = INVALID_TOKEN) -> None:
        """La prossima connessione si vede rifiutare il gettone."""
        self._auth_refusals.append(message)

    def push_event(self, event_type: str, data: dict) -> bool:
        """Home Assistant manda un evento del bus. `False` se il client non si
        e' iscritto a quel tipo: il vero non glielo manderebbe."""
        subscription = self._subscriptions.get(event_type)
        if subscription is None:
            return False
        self._inbox.put_nowait({
            "id": subscription, "type": "event",
            "event": {"event_type": event_type, "data": data, "origin": "LOCAL",
                      "time_fired": "2026-10-03T12:00:00+00:00",
                      "context": {"id": "01CASAFINTA", "parent_id": None,
                                  "user_id": None}}})
        return True

    def push_config_entry_change(self, change: str, entry: dict) -> bool:
        """Home Assistant annuncia un cambio di una voce di integrazione.
        `False` se il client non si e' iscritto a `config_entries/subscribe`."""
        if self._entries_subscription is None:
            return False
        self._inbox.put_nowait({"id": self._entries_subscription, "type": "event",
                                "event": [{"type": change, "entry": entry}]})
        return True

    def drop(self) -> None:
        """La connessione viva cade: l'ascolto del client finisce."""
        self._inbox.put_nowait(_DROPPED)

    # ── cio' che Home Assistant ha in casa ──────────────────────────────────

    def config_entries(self) -> list[dict]:
        """Le voci delle integrazioni dell'elenco iniziale. Una casa ferma
        senza ingressi non ne ha."""
        return []

    # ── il trasporto, visto dal client ──────────────────────────────────────

    def ws_connect(self, url, **kwargs):
        self.opened += 1
        refusal = self._auth_refusals.pop(0) if self._auth_refusals else None
        self._replies = [
            {"type": "auth_required", "ha_version": HA_SOURCE_VERSION},
            {"type": "auth_invalid", "message": refusal} if refusal is not None
            else {"type": "auth_ok", "ha_version": HA_SOURCE_VERSION}]
        # Una connessione nuova non porta niente della vecchia: ne' messaggi
        # in attesa, ne' iscrizioni.
        self._inbox = asyncio.Queue()
        self._subscriptions = {}
        self._entries_subscription = None
        self._tasks_before = asyncio.all_tasks()
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def receive_json(self):
        return self._replies.pop(0)

    async def send_json(self, payload):
        if payload.get("type") == "auth":
            return
        self.sent.append(payload)
        command = payload.get("type")
        if command == "subscribe_events":
            self._subscriptions[payload.get("event_type")] = payload["id"]
            self._confirm(payload["id"])
        elif command == "get_config":
            self._inbox.put_nowait({"id": payload["id"], "type": "result",
                                    "success": True,
                                    "result": {"state": self.core_state}})
        elif command == "config_entries/subscribe":
            entries = self.config_entries()
            self._entries_subscription = payload["id"]
            self._confirm(payload["id"])
            self._inbox.put_nowait({"id": payload["id"], "type": "event",
                                    "event": [{"type": None, "entry": entry}
                                              for entry in entries]})
        else:
            raise UnservedCommand(str(command), "la connessione di lunga vita non lo serve")

    def _confirm(self, subscription: int) -> None:
        self._inbox.put_nowait({"id": subscription, "type": "result",
                                "success": True, "result": None})

    def __aiter__(self):
        # Il client vero comincia ad ascoltare gli eventi solo DOPO essersi
        # iscritto e (alle riconnessioni) aver avvisato gli ascoltatori. Fra
        # `ws_connect` e qui non cede mai il passo al ciclo (la connessione
        # finta non fa I/O): i compiti nati nel frattempo sono tutti e soli i
        # lavori che gli ascoltatori hanno rimandato -- le riletture con
        # antirimbalzo.
        self.deferred_work = asyncio.all_tasks() - self._tasks_before
        self.listening += 1
        self.connected.set()
        return self

    async def __anext__(self):
        message = await self._inbox.get()
        if message is _DROPPED:
            raise StopAsyncIteration
        return _Text(message)

    async def close(self) -> None:
        return None


#: Un corpo che non e' JSON: quello di `HTTPBadRequest` e simili.
_NOT_JSON = object()


class _Response:
    """Una risposta HTTP finta: lo stato e il corpo, come li leggono il vero
    `_rest_get`, `_http_reason` e `call_service` (`json()`, `text()`,
    `raise_for_status()`). Arriva dopo `delay`, se ce n'e' uno."""

    def __init__(self, status: int, body=None, *, url: str = NOWHERE,
                 method: str = "GET", delay=None) -> None:
        self.status = status
        self.reason = http.HTTPStatus(status).phrase
        self._body = body
        self._delay = delay
        self.request_info = aiohttp.RequestInfo(
            URL(url), method, CIMultiDictProxy(CIMultiDict()), URL(url))

    @classmethod
    def refused(cls, refusal: Refused, **request) -> _Response:
        if refusal.message:
            return cls(int(refusal.code), {"message": refusal.message}, **request)
        return cls(int(refusal.code), _NOT_JSON, **request)

    async def json(self):
        if self._body is _NOT_JSON:
            raise aiohttp.ContentTypeError(self.request_info, (), status=self.status,
                                           message="Attempt to decode JSON with "
                                                   "unexpected mimetype: text/plain")
        return self._body

    async def text(self) -> str:
        if self._body is _NOT_JSON:
            return f"{self.status}: {self.reason}"
        return "" if self._body is None else json.dumps(self._body)

    def raise_for_status(self) -> None:
        """Come `aiohttp.ClientResponse.raise_for_status`: da 400 in su
        solleva `ClientResponseError` con lo stato e la sua frase."""
        if self.status >= 400:
            raise aiohttp.ClientResponseError(self.request_info, (), status=self.status,
                                              message=self.reason)

    async def __aenter__(self):
        if self._delay is not None:
            await _arrives(self._delay, None)
        return self

    async def __aexit__(self, *exc_info):
        return False


class _HouseSession(SilentConnection):
    """La sessione della casa finta: il websocket di lunga vita che tace, e le
    `GET` del vero `_rest_get` servite dagli ingressi. Una scrittura (`post`,
    `delete`) si registra e riceve la risposta che la prova ha iniettato;
    senza, solleva nominando metodo e percorso."""

    def __init__(self, house: CasaFinta) -> None:
        super().__init__()
        self._house = house
        #: Per ogni messaggio di `sent`, quante chiamate la casa aveva gia'
        #: ricevuto quando e' partito: dice cosa e' venuto prima, l'iscrizione
        #: o la lettura (D2 della Tappa 2).
        self.sent_after: list[int] = []

    async def send_json(self, payload):
        if payload.get("type") != "auth":
            self.sent_after.append(len(self._house.calls))
        return await super().send_json(payload)

    def config_entries(self) -> list[dict]:
        """L'elenco iniziale delle integrazioni: le voci che `config_entries/get`
        ha reso alla cattura (`registries.integrazioni`), la stessa forma
        (`ConfigEntry.as_json_fragment`). Senza quell'ingresso l'iscrizione non
        e' servita."""
        return self._house._input("config_entries/subscribe", "registries.integrazioni")

    def get(self, url: str, **kwargs):
        return self._house._rest_reply(self._house._house_path("GET", url))

    def post(self, url: str, **kwargs):
        return self._house._rest_write("POST", url, kwargs.get("json"))

    def delete(self, url: str, **kwargs):
        return self._house._rest_write("DELETE", url, kwargs.get("json"))


def _ok(result) -> dict:
    return {"type": "result", "success": True, "result": result}


def _refused(code, message) -> dict:
    return {"type": "result", "success": False, "error": {"code": code, "message": message}}


class CasaFinta(HAClient):
    """Home Assistant dagli ingressi, sotto il client vero.

    `inputs` ha la forma di `casa.read_inputs` (le chiavi di `casa.INPUTS`): un
    ingresso che manca rende non servito il comando che lo legge, e basta.
    `answers` aggiunge comandi WS o percorsi REST (`{nome: f(extra) ->
    result}`; per una `GET` `f(percorso)` -> corpo, per una scrittura
    (`"POST <percorso>"`, `"DELETE <percorso>"`) `f(percorso, corpo)` -> corpo;
    la chiave di un percorso vale anche come prefisso). Una risposta puo'
    rendere `Refused(...)` o `SILENT` per quella domanda sola, e
    `in_turn(...)` ne fa una sequenza. `refuse` li fa rifiutare sempre (WS:
    `{"code", "message"}` o `Refused`, il corpo d'errore di Home Assistant;
    REST: lo stato HTTP o `Refused`); `silence` li fa tacere (WS: nessuna
    risposta; REST: la connessione cade); `delay` fa arrivare la risposta
    tardi o mai (vedi il docstring del modulo).

    Registra `calls` -- `(comando o percorso, extra o corpo)` nell'ordine, le
    scritture REST col metodo davanti -- e `connections` -- `("ws", comandi)`
    per ogni `_ws_send`, `("rest", percorso)` per ogni richiesta HTTP.
    """

    def __init__(self, inputs: dict, *,
                 answers: dict[str, Callable] | None = None,
                 refuse: dict[str, object] | None = None,
                 silence=(),
                 delay: dict[str, object] | None = None) -> None:
        super().__init__(NOWHERE, "casa-finta")
        self._inputs = inputs
        self._answers = dict(answers or {})
        self._refuse = dict(refuse or {})
        self._silence = set(silence)
        self._delay = dict(delay or {})
        self._session = _HouseSession(self)
        # `ws_ready` NON si accende alla nascita (fino al Task 7 della Tappa 2
        # si'): lo accende il client vero quando la casa conferma l'iscrizione
        # agli stati, come in produzione. Acceso prima, l'avvio leggerebbe la
        # casa prima di essersi iscritto, e la prova dell'ordine (D2) non
        # vedrebbe niente.
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

    def announce(self, event_type: str, data: dict) -> None:
        """Home Assistant annuncia un evento del bus, e gli ascoltatori del
        client lo ricevono SUBITO: lo smista il codice vero
        (`_dispatch_bus_event`), senza il ciclo d'ascolto del websocket. E'
        cio' che serve per un annuncio che arriva DENTRO una chiamata; il ciclo
        vero si prova con `SilentConnection.push_event`.

        L'evento ha la forma di `Event._as_dict` (`core.py`, tag `2026.9.4`,
        vedi `SilentConnection`); per `state_changed` `data` e'
        `{"entity_id", "old_state", "new_state"}`."""
        self._dispatch_bus_event({
            "event_type": event_type, "data": data, "origin": "LOCAL",
            "time_fired": "2026-10-03T12:00:00+00:00",
            "context": {"id": "01CASAFINTA", "parent_id": None, "user_id": None}})

    def announce_state(self, new_state: dict | None, old_state: dict | None = None) -> None:
        """Un `state_changed`: lo stato nuovo (`None` per un'entita' tolta)."""
        entity_id = (new_state or old_state or {}).get("entity_id")
        self.announce("state_changed", {"entity_id": entity_id, "old_state": old_state,
                                        "new_state": new_state})

    def listeners(self, kind: str) -> list:
        """Gli ascoltatori di un genere (`listener_kinds()`) registrati adesso
        sul client vero: chi si e' iscritto e non si e' tolto."""
        if kind not in listener_kinds():
            raise ValueError(f"genere di ascoltatori sconosciuto: {kind}")
        return list(getattr(self, f"_{kind}_listeners"))

    async def _first_connection_settled(self) -> None:
        """Aspetta la prima connessione e i lavori che ha rimandato: e' li'
        che l'avvio e' finito davvero («avvio intero», D1 della Tappa 2). Si
        aspetta l'evento, non un tempo: l'antirimbalzo delle riletture e' di
        qualche secondo, e un `sleep` sarebbe o troppo corto o sprecato.

        Non c'e' niente da aspettare se il websocket non e' mai stato aperto,
        o se l'avvio ha smesso di aspettarlo (`reread_after_first_connection`:
        la casa non rispondeva) -- l'avvio e' finito senza. Se il ciclo del
        websocket e' morto -- un comando che la casa non serve
        (`UnservedCommand`) -- si solleva la sua eccezione invece di
        aspettare per sempre."""
        if self._ws_task is None:
            return
        if self._reread_at_first_connection and not self._session.connected.is_set():
            return
        connected = asyncio.ensure_future(self._session.connected.wait())
        done, _pending = await asyncio.wait({connected, self._ws_task},
                                            return_when=asyncio.FIRST_COMPLETED)
        if self._ws_task in done:
            connected.cancel()
            self._ws_task.result()
            return
        await asyncio.gather(*self._session.deferred_work, return_exceptions=True)

    # ── il trasporto ────────────────────────────────────────────────────────

    async def _ws_send(self, commands, timeout: float = 10.0) -> list[dict | None]:
        """Come il vero: nessun comando, nessuna connessione; N comandi, UNA
        connessione e N messaggi interi in ordine (`None` = senza risposta)."""
        if not commands:
            return []
        self.connections.append(("ws", tuple(msg_type for msg_type, _ in commands)))
        replies: list[dict | None] = []
        delays: list[tuple[int, object]] = []
        for msg_id, (msg_type, extra) in enumerate(commands, start=1):
            self.calls.append((msg_type, extra))
            reply = self._ws_reply(msg_type, extra)
            replies.append(None if reply is None else {"id": msg_id, **reply})
            if reply is not None and msg_type in self._delay:
                delays.append((msg_id - 1, self._delay[msg_type]))
        # Le risposte in ritardo si aspettano insieme, sotto il tetto del vero:
        # quella che non arriva in tempo e' `None`, come dal vero `_ws_send`.
        arrived = await asyncio.gather(*(_arrives(wait, timeout) for _i, wait in delays))
        for (index, _wait), came in zip(delays, arrived, strict=True):
            if not came:
                replies[index] = None
        return replies

    def _ws_reply(self, msg_type: str, extra: dict | None) -> dict | None:
        if msg_type in self._silence:
            return None
        if msg_type in self._refuse:
            return self._ws_wrap(self._refuse[msg_type])
        if msg_type in self._answers:
            return self._ws_wrap(self._answers[msg_type](extra), answered=True)
        if msg_type not in self._ws_served():
            raise UnservedCommand(msg_type)
        source, reply = self._ws_served()[msg_type]
        return reply(extra, self._input(msg_type, source))

    @staticmethod
    def _ws_wrap(outcome, *, answered: bool = False) -> dict | None:
        """Il messaggio per un esito iniettato: `SILENT` nessuno, un rifiuto
        la busta d'errore, ogni altro valore (di una risposta) il `result`."""
        if isinstance(outcome, Silence):
            return None
        if isinstance(outcome, Refused):
            return _refused(outcome.code, outcome.message)
        if not answered:
            return _refused(outcome.get("code"), outcome.get("message"))
        return _ok(outcome)

    def _rest_answer(self, key: str):
        """La risposta per `key` (un percorso, o `METODO percorso`): esatta, o
        la chiave piu' lunga che ne e' un prefisso."""
        method = key.split(" ", 1)[0] + " " if " " in key else ""
        return self._answers.get(key) or next(
            (f for name, f in sorted(self._answers.items(), key=lambda item: -len(item[0]))
             if name.startswith(f"{method}/") and key.startswith(name)), None)

    def _rest_outcome(self, key: str, asked: tuple, *, method: str, url: str):
        """L'esito di una richiesta REST, o `None` se nessuno l'ha iniettato:
        il silenzio fa cadere la connessione, un rifiuto e' lo stato (e il
        corpo) di Home Assistant, una risposta il corpo di un 200."""
        request = {"url": url, "method": method, "delay": self._delay.get(key)}
        if key in self._silence:
            raise aiohttp.ClientConnectionError(SILENT.reason)
        if key in self._refuse:
            refusal = self._refuse[key]
            return _Response.refused(refusal if isinstance(refusal, Refused)
                                     else Refused(refusal), **request)
        answer = self._rest_answer(key)
        if answer is None:
            return None
        outcome = answer(*asked)
        if isinstance(outcome, Silence):
            raise aiohttp.ClientConnectionError(outcome.reason)
        if isinstance(outcome, Refused):
            return _Response.refused(outcome, **request)
        return _Response(200, outcome, **request)

    def _rest_reply(self, path: str) -> _Response:
        self.connections.append(("rest", path))
        self.calls.append((path, None))
        bare = path.split("?", 1)[0]
        url = f"{self._base_url}{path}"
        response = self._rest_outcome(bare, (path,), method="GET", url=url)
        if response is not None:
            return response
        if bare not in self._REST_SERVED:
            raise UnservedCommand(bare)
        return _Response(200, self._input(bare, self._REST_SERVED[bare]), url=url,
                         delay=self._delay.get(bare))

    def _house_path(self, method: str, url: str) -> str:
        """Il percorso di una richiesta HTTP, tolto l'indirizzo della casa. Una
        richiesta che non porta l'indirizzo della casa (`base_url` del client)
        non arriverebbe a Home Assistant: non e' servita, e si nomina."""
        if not url.startswith(f"{self._base_url}/"):
            raise UnservedCommand(f"{method} {url}",
                                  f"non e' indirizzata alla casa ({self._base_url})")
        return url.removeprefix(self._base_url)

    def _rest_write(self, method: str, url: str, body) -> _Response:
        """Una scrittura REST: si REGISTRA (`calls`, `connections`) e si
        risponde cio' che la prova ha iniettato. Non si esegue niente."""
        path = self._house_path(method, url)
        key = f"{method} {path.split('?', 1)[0]}"
        self.connections.append(("rest", key))
        self.calls.append((key, body))
        response = self._rest_outcome(key, (path, body), method=method, url=url)
        if response is None:
            raise UnservedCommand(key, "e' una scrittura, e la casa finta non scrive: "
                                       "la risposta la inietta la prova (`answers=`)")
        return response

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
            if not isinstance(value, dict) or key not in value:
                raise UnservedCommand(command, f"manca l'ingresso `{source}`")
            value = value[key]
        return value

    def _ws_served(self) -> dict[str, tuple[str, Callable]]:
        """`{comando: (ingresso, risposta(extra, valore dell'ingresso))}`."""
        served: dict[str, tuple[str, Callable]] = {
            "get_config": ("ha_config", lambda extra, config: _ok(config)),
            "energy/get_prefs": ("energy_prefs", lambda extra, prefs: _ok(prefs)),
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

