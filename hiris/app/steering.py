"""Chi risponde a questo turno: il ponte, o la catena.

**Una domanda sola, una casa sola.** Fino al 22 agosto 2026 la regola viveva
dentro `api/handlers_chat.handle_chat`, intrecciata con la persistenza del
turno e con la coda -- e il turno di una promessa, che quella funzione non la
attraversa mai, ne aveva per forza una seconda: andava dritto a `llm_router`,
dove il ponte non e' nemmeno un anello (`providers.chain_members()` conosce claude,
openai, openrouter, ollama).

Non era una svista di chi ha scritto lo Schedulatore: era la struttura a
imporlo. Il difetto si e' visto dal vivo il 21/08/2026 su una casa che gira
INTERAMENTE sul Piano Claude Max -- chat perfetta, promesse tutte fallite su
due chiavi API esaurite, e l'abbonamento sano li' accanto che le promesse non
potevano usare, senza che nessuna pagina lo dicesse.

Da qui in poi le due porte chiedono alla stessa funzione, e una terza porta
che nascesse domani non potrebbe inventarsene una terza senza accorgersene.

## Le due ragioni per cui si scende alla catena non sono la stessa cosa

- **Il ponte non e' in gioco** -- spento, o coda non cablata. Non c'e' nessun
  ripiego da dichiarare: e' la configurazione che l'utente ha scelto.
  Annunciarlo a ogni turno direbbe che sta perdendo qualcosa che non ha mai
  avuto. Motivo vuoto.
- **Il ponte c'e' e non puo' rispondere** -- niente token, o tetto pieno.
  Quello e' un ripiego vero, dal forfait al consumo, e **si annuncia ogni
  volta** (decisione del proprietario, 13 agosto): un passaggio silenzioso a
  un provider a pagamento si scopre a fine mese.

Il motivo e' una **chiave** di `model_resolution._DOWNGRADE_REASONS`, mai una
frase: la frase la compone `downgrade_note`, e un motivo fuori vocabolario non
produce un errore -- produce silenzio, cioe' esattamente il prelievo non
annunciato che la regola esiste per evitare.

`_bridge_on` e `_subscription_can_answer` vivono QUI e non piu' in
`handlers_chat`: sono pezzi della stessa decisione, e lasciarle di la' avrebbe
reso circolare l'import (la chat chiama questo modulo, questo modulo chiamava
la chat).
"""
from __future__ import annotations

import contextlib as _contextlib
import json as _json
import logging
import re as _re
import time as _time
from collections.abc import Callable as _Callable
from dataclasses import dataclass as _dataclass
from dataclasses import field as _field
from typing import NamedTuple as _NamedTuple

from .models_store import _STORE_DEFAULTS, bridge_deadline_min
from .providers import subscription_has_token
from .reasoning.queue import PRIORITY_BACKGROUND, PRIORITY_CHAT

logger = logging.getLogger(__name__)


def _bridge_on(app) -> bool:
    """Se il ponte della coda di ragionamento e' cablato in questa app.

    `server._on_startup` crea `app["reasoning_queue"]` sempre; `ponte.attivo`
    (nell'archivio) governa la spazzata e `app["bridge_active"]`, non
    l'esistenza dell'oggetto coda. Quindi la presenza della chiave e' il
    segnale giusto -- ed e' anche il modo in cui i test entrano e escono dal
    ramo senza toccare la configurazione.
    """
    return app.get("reasoning_queue") is not None


def _subscription_can_answer(app) -> tuple[bool, str]:
    """Il piano puo' servire un turno adesso? E, se no, con quali parole.

    Le due condizioni sono quelle che fino alla 2.4.1 facevano finire il turno
    con un errore: il token assente (senza cui il lavoratore del ponte non
    parte affatto, e il messaggio finirebbe in una coda che nessuno serve) e il
    tetto giornaliero pieno.

    Il tetto si legge dall'ARCHIVIO (`ponte.tetto_giornaliero`), dove l'utente
    lo cambia: quella che si cambia dev'essere quella che il turno subisce.
    """
    if not subscription_has_token():
        return False, "manca il token"
    ceiling = int(
        (app.get("models_config") or {})
        .get("ponte", {})
        .get("tetto_giornaliero",
             _STORE_DEFAULTS["ponte"]["tetto_giornaliero"]))
    if app["reasoning_queue"].count_exchanges_today() >= ceiling:
        logger.warning(
            "Tetto giornaliero del ponte raggiunto (%d turni): il turno passa "
            "alla catena.", ceiling)
        return False, "tetto giornaliero"
    return True, ""


#: Il tetto di giri di strumento. **Si importa, non si ricopia**: il numero
#: vive in `claude_runner`, che e' chi lo fa rispettare, e una seconda
#: costante qui direbbe «esaurito» a un turno che non lo e' il giorno in cui
#: qualcuno alza il tetto di la'.
from .claude_runner import MAX_TOOL_ITERATIONS as MAX_GIRI
from .claude_runner import posa_misura as _posa_misura
from .claude_runner import togli_misura as _togli_misura

#: **Le specie di turno di HIRIS**, in un posto solo: `misura_turno` rifiuta
#: una specie che non sta qui.
#:
#: **Non e' `agent_type`**, e la differenza morde. `agent_type` risponde a
#: «quale modello scelgo» (`AUTO_MODEL_MAP`); questa risponde a «chi sta
#: chiedendo». Fino al 07/10/2026 `mind/observer.py` e `mind/recipe_turn.py`
#: passavano tutti e due `agent_type="observer"`, quindi misurando su quello
#: l'osservatore e le ricette sarebbero stati indistinguibili -- proprio la
#: distinzione che il proprietario vuole vedere.
#:
#: **La specie dell'attuatore ha un nome, e si importa** (C-28, Tappa 4 dello
#: sprint «Una fonte sola di verita'»): fino al 05/10/2026 «attuatore» era
#: scritto come letterale in cinque punti di `server.py` e `agent/runner.py`,
#: e un refuso in uno di loro avrebbe fatto rifiutare la misura a
#: `misura_turno` -- o, nel registro del ponte, contato i turni dell'attuatore
#: sotto un nome che nessuna pagina conosce. `tests/test_specie_attuatore.py`
#: tiene il letterale qui e solo qui.
#:
#: **E le altre, tranne `chat`** (A21, approvata dal proprietario il
#: 05/10/2026): la stessa cura per l'analista, l'osservatore, le ricette e la
#: promessa, che restavano letterali. `chat` no: e' anche un `agent_type` e un
#: `kind` della coda, e un nome solo per tre parole non le distinguerebbe.
#:
#: **Dal 06/10/2026 l'attuatore si chiama proponente** (D11 del piano degli
#: attori, strati 3-4, approvata dal proprietario il 06/10/2026): il nome
#: «attuatore» era anche quello di `action/actuator.py`, la porta dei servizi
#: verso la casa, cioe' l'unica cosa che questo attore non fa. Le righe gia'
#: archiviate nei consumi restano «attuatore»: sono storia, e non si
#: riscrivono.
PROPOSER_SPECIES = "proponente"
ANALYST_SPECIES = "analista"
OBSERVER_SPECIES = "osservatore"
PROMISE_SPECIES = "promessa"
RECIPES_SPECIES = "ricette"
#: **«Rendila automatica»** (attori, strato 4, Task 4.5; D15, decisa dal
#: proprietario il 06/10/2026): il turno del proponente che, su richiesta di
#: chi amministra, compone un'automazione da una proposta fatta a mano. E' un
#: mestiere suo, e non il giro orario del proponente, perche' la coda del
#: ponte li distingue per `kind`: con lo stesso, la raccolta di uno leggerebbe
#: la risposta dell'altro, e la guardia «un turno in volo» li fermerebbe a
#: vicenda. Le proposte che nascono qui le firma comunque il proponente.
AUTOMATE_SPECIES = "automatizza"


def _chat_tools() -> list[dict]:
    """Gli strumenti della chat: tutta la tabella (`home_space/tools.TOOLS`).
    Chiesti a ogni turno, non copiati all'import: la tabella e' di la'."""
    from .home_space.tools import KNOWLEDGE_TOOLS

    return list(KNOWLEDGE_TOOLS)


def _promise_tools() -> list[dict]:
    """Gli strumenti della promessa: l'elenco d'ammissione di
    `keeper/exchange.SOLA_LETTURA` piu' `conclude` (`promise_tools`)."""
    from .keeper.exchange import promise_tools

    return promise_tools()


def _analyst_tools() -> list[dict]:
    """Gli strumenti dell'analista: i lettori di `analyst_turn.READERS` piu'
    `compute` (D5 del piano degli attori, Task 3.6)."""
    from .mind.analyst_turn import analyst_tools

    return analyst_tools()


async def _analyst_guard(app, exchange: str | None = None):
    """Il guardiano dell'analista (`analyst_turn.guard`), lo stesso sulla
    catena e sul ponte."""
    from .mind.analyst_turn import guard

    return await guard(app, exchange)


def _proposer_tools() -> list[dict]:
    """Gli strumenti del proponente: i lettori dell'analista piu' `propose`
    (D12 del piano degli attori, Task 4.2)."""
    from .mind.proposer_turn import proposer_tools

    return proposer_tools()


async def _proposer_guard(app, exchange: str | None = None):
    """Il guardiano del proponente (`proposer_turn.guard`), lo stesso sulla
    catena e sul ponte."""
    from .mind.proposer_turn import guard

    return await guard(app, exchange)


async def _automate_guard(app, exchange: str | None = None):
    """Il guardiano di «Rendila automatica» (`automate_turn.guard`), lo
    stesso sulla catena e sul ponte."""
    from .mind.automate_turn import guard

    return await guard(app, exchange)


@_dataclass(frozen=True)
class Species:
    """**La dichiarazione di un mestiere** (Tappa 6, Task 7): cio' che il turno
    di un mestiere e', in un posto solo. Tutto il resto si chiede a lei.

    - `name`: il nome nel registro dei turni (`misura_turno`) e nei ripieghi;
    - `kind`: il nome del job nella coda del ponte. Fino al 06/10/2026 viveva
      due volte, nel modulo che accoda (`observer.SCOPE_TURN_KIND`, ...) e
      nel lavoratore che serve (`agent/runner._SCOPE_KIND`, ...);
    - `catalog`: chi dice le DEFINIZIONI degli strumenti del turno, o `None`
      per un mestiere **autosufficiente** -- la domanda porta gia' tutto, e il
      turno non deve poter agire. E' l'elenco d'ammissione degli strumenti:
      la catena lo pretende in `chain_turn`; il ponte ci compone
      `--allowedTools`, la sonda e `verify_init`, e `/api/mcp` lo serve al
      turno che si fa riconoscere (`X-HIRIS-Lavoro`). Fino al 06/10/2026
      (attori, Task 3.6) il ponte conosceva due cataloghi soli, chat e
      promessa: un terzo mestiere con strumenti avrebbe ricevuto quello della
      chat, `execute` compreso;
    - `guard`: per un mestiere di sfondo con strumenti, chi costruisce il suo
      dispatcher -- `await guard(app, exchange)` -- con davanti il guardiano
      che lascia passare solo il catalogo. `None` per chat e promessa, che
      il ponte serve con il soggetto e il soffitto dei loro job;
    - `priority`: la precedenza sulla coda del ponte (D4 della Tappa 6);
    - `gestures`: per un mestiere di sfondo con strumenti, i gesti del suo
      soffitto (`api/soffitto.GESTI`) -- **la decisione 13** della spec
      2026-10-01 (Tappa 7, Task 7). Il guardiano lo passa al dispatcher
      (`ceiling()`), e un dispatcher senza soffitto non si costruisce piu'.
      `None` per chat e promessa, il cui soffitto e' quello della persona
      che li ha aperti.

    Il tetto di token non sta qui: lo dichiara ogni turno accanto alla sua
    domanda (Tappa 6, Task 4), e `chain_turn` lo pretende per nome.
    """
    name: str
    kind: str
    catalog: _Callable[[], list[dict]] | None
    priority: int
    guard: _Callable | None = None
    gestures: frozenset[str] | None = None

    def __post_init__(self) -> None:
        # Un guardiano senza gesti costruirebbe un dispatcher senza soffitto:
        # e' esattamente il «tutto» che la decisione 13 ha tolto.
        if (self.guard is None) != (self.gestures is None):
            raise ValueError(f"mestiere {self.name!r}: un guardiano porta i suoi "
                             "gesti, e i gesti un guardiano")

    def ceiling(self) -> dict:
        """Il soffitto dichiarato di questo mestiere, nella forma di tutti gli
        altri (`soffitto.declared_ceiling`)."""
        from .api.soffitto import declared_ceiling

        if self.gestures is None:
            raise ValueError(f"il mestiere {self.name!r} non dichiara un soffitto: "
                             "lo porta la persona che apre il turno")
        return declared_ceiling(self.gestures)

    @property
    def self_contained(self) -> bool:
        return self.catalog is None

    def catalog_for_turn(self) -> list[dict]:
        """Le definizioni degli strumenti ammessi in un turno di questo mestiere."""
        return [] if self.catalog is None else self.catalog()

    def tools_for_turn(self) -> tuple[str, ...]:
        """I nomi degli strumenti ammessi in un turno di questo mestiere."""
        return tuple(d["name"] for d in self.catalog_for_turn())


#: **Cosa puo' un attore** (decisione 13 della spec 2026-10-01, D5 della
#: Tappa 7): leggere e amministrare si', comandare no. Al livello di chi
#: amministra perche' cio' che gli attori producono lo legge solo chi
#: amministra, e l'analista per spiegare un cambio ha bisogno del corpo
#: dell'automazione; `amministrare` e' anche il gesto di `propose`, che il
#: proponente ha gia' (la proposta aspetta il si'). Comandare no: un attore
#: non tocca la casa.
_ACTOR_GESTURES = frozenset({"leggere", "amministrare"})

#: I sette mestieri. **La precedenza**: la sola decisione presa e' «la chat
#: passa avanti» (spec §4.3), quindi due valori, quelli della coda.
SPECIES = {s.name: s for s in (
    Species("chat", "chat", _chat_tools, PRIORITY_CHAT),
    Species(PROMISE_SPECIES, "promessa", _promise_tools, PRIORITY_BACKGROUND),
    Species(OBSERVER_SPECIES, "scope", None, PRIORITY_BACKGROUND),
    Species(RECIPES_SPECIES, "ricetta", None, PRIORITY_BACKGROUND),
    Species(ANALYST_SPECIES, "analisi", _analyst_tools, PRIORITY_BACKGROUND,
            guard=_analyst_guard, gestures=_ACTOR_GESTURES),
    Species(PROPOSER_SPECIES, "proposta", _proposer_tools, PRIORITY_BACKGROUND,
            guard=_proposer_guard, gestures=_ACTOR_GESTURES),
    # Gli stessi strumenti del proponente: e' il suo mestiere, su una
    # proposta sola. Cambia il guardiano.
    Species(AUTOMATE_SPECIES, "automatizza", _proposer_tools, PRIORITY_BACKGROUND,
            guard=_automate_guard, gestures=_ACTOR_GESTURES),
)}

def refused_tool(name: str, *, doing: str, instead: str) -> dict:
    """Il rifiuto di uno strumento fuori dal catalogo di un mestiere di
    sfondo: una frase sola per il guardiano della promessa
    (`keeper/exchange.PromiseDispatcher`) e per quello dell'analista
    (`mind/analyst_turn.AnalystDispatcher`). Cambia solo cio' che il turno
    sta facendo, e cosa fare invece."""
    return {"errore": (f"«{name}» non e' disponibile {doing}: qui posso "
                       f"guardare e rispondere, non toccare la casa. {instead}")}


def compose_base(tools) -> str:
    """**Il compositore** (Tappa 6, Task 7; R18): l'identita' di HIRIS, e le
    regole sugli strumenti che `tools` (i NOMI degli strumenti del turno)
    puo' usare.

    Un turno senza strumenti riceve la sola identita': zero caratteri di
    regole. Uno con alcuni strumenti riceve le regole che parlano SOLO di
    quelli, e quelle che non ne nominano nessuno (`claude_runner.TOOL_RULES`):
    dal 06/10/2026 (attori, Task 4.2) una regola che nomina anche uno
    strumento del turno non basta -- il proponente ha `propose` e non
    `confirm`, e la regola della chat gli diceva di mostrare l'anteprima a chi
    gli parla, fermarsi e confermare dopo. Con
    tutti gli strumenti -- la chat -- il blocco e' quello di sempre, byte per
    byte.

    La chiamano la catena (`ClaudeRunner.chat`, `OpenAICompatRunner.chat`) e
    il ponte (`agent/prompts.build_chat_messages`): un turno identico compone
    la stessa cosa da entrambe le parti. Fino al 06/10/2026 erano tre
    composizioni, e la catena dava le regole a tutti.
    """
    from .claude_runner import BASE_IDENTITY, TOOL_RULES

    names = set(tools or ())
    if not names:
        return BASE_IDENTITY
    return BASE_IDENTITY + "".join(
        text for about, text in TOOL_RULES if not about or set(about) <= names)


#: I nomi dei mestieri: una vista sulle dichiarazioni.
SPECIE = frozenset(SPECIES)

#: Come il ponte chiama i mestieri (il `kind` del job) e come li chiama il
#: registro: una vista sulle dichiarazioni. Fino al 06/10/2026 era una tabella
#: scritta in `agent/runner.py`, accanto a due altre liste degli stessi job
#: (`RAGIONABILI`, `_SELF_CONTAINED_KINDS`).
JOB_SPECIES = {s.kind: s.name for s in SPECIES.values()}

#: **L'esito di un turno fermato dal tetto di token** (Tappa 6, D-58; D2).
#: Fino al 05/10/2026 il registro lo chiamava «riuscito»: misurato in
#: `docs/misure/2026-10-tappa-0.md`, 7 turni dell'analista su 8 si fermavano
#: al tetto, e nessuna riga lo diceva. Il segnale viene dal runner
#: (`last_truncated`), cioe' da cio' che il provider ha dichiarato -- mai dal
#: testo della risposta.
TRUNCATED = "troncato"

#: L'esito di un turno andato a buon fine, per quanto ne sa l'imbuto. E'
#: l'unico che `declare_refused` corregge (G31-1, giro 31 della revisione,
#: 06/10/2026): un «fallito» non ha risposto, e riscriverlo «rifiutata»
#: direbbe al giro dopo che il modello ha sbagliato quando non ha parlato.
SUCCEEDED = "riuscito"

#: **L'esito di una risposta con uno strumento «scappato»** (B22, approvata il
#: 05/10/2026; D-58, seconda meta'): la chiamata a uno strumento arrivata
#: come testo, che l'utente legge come `TOOL_LEAK_USER_MSG`. Fino a quel
#: giorno il registro la chiamava «riuscito». Il segnale e' `last_tool_leaked`
#: del runner, per chiamata come `last_truncated`.
TOOL_LEAKED = "strumento_scappato"

#: **L'esito di una risposta che il mestiere ha rifiutato** (D10 del piano
#: degli attori, approvata il 06/10/2026): il modello ha finito, ma cio' che
#: ha detto non passa la validazione del mestiere. Fino a quel giorno il
#: registro la chiamava «riuscito». A differenza di `TRUNCATED` non lo sa il
#: runner: lo sa il mestiere, dopo il turno, e lo scrive sulla riga gia'
#: registrata (`declare_refused`).
REFUSED = "rifiutata"

#: Cosa riceve il mestiere al posto delle decisioni, quando il turno e' stato
#: troncato (D2, approvata il 05/10/2026): **non si legge**. Un JSON tagliato a
#: meta' che per caso si chiude e' l'unico modo di inventare decisioni da una
#: risposta che il modello non ha finito -- e nessun nuovo tentativo: prima si
#: vede, poi il tetto si sceglie misurando (D3).
TRUNCATED_REASON = ("la risposta e' stata troncata al tetto di token: non "
                    "si legge una risposta che il modello non ha finito")

#: Una risposta vuota non e' un silenzio: e' un modello che non ha risposto.
NO_ANSWER_REASON = "il modello non ha risposto"

#: **Il freno** (Tappa 6, Task 3, passo 5): dopo questi turni troncati o
#: rifiutati DI FILA (`BRAKE_OUTCOMES`, D10) lo stesso mestiere si ferma e lo
#: dice. **Il numero non c'e' ancora, e il
#: freno e' spento**: «un numero non misurato non si scrive», e N si sceglie
#: dalle misure dal vivo della chiusura (T9) -- i troncati per mestiere,
#: contati da questo stesso registro. `None` = spento.
TRUNCATION_BRAKE: int | None = None

#: Chi il freno puo' fermare. **La chat no**, ed e' una scelta, non una
#: dimenticanza: ha una persona davanti che vede la troncatura
#: (`claude_runner._TRUNCATION_NOTICE`) e decide da se'. Il freno esiste per i
#: mestieri che girano da soli, di notte, e che senza di lui si troncherebbero
#: a ogni giro senza che nessuno guardi.
BRAKED_SPECIES = SPECIE - {"chat"}


#: Gli esiti che il freno conta: un turno che non ha dato niente da leggere.
#: Il troncato perche' il modello non ha finito, il rifiutato perche' ha
#: finito male (D10). Uno strumento «scappato» no: la chat e' l'unica a
#: produrlo, e la chat non si frena.
BRAKE_OUTCOMES = frozenset({TRUNCATED, REFUSED})


class TurnBraked(RuntimeError):
    """Il freno ha fermato questo mestiere (troppi turni troncati o rifiutati
    di fila, `BRAKE_OUTCOMES`): il turno non parte."""


@_dataclass
class TurnOutcome:
    """Cio' che il turno sa di se' quando e' finito, consegnato dall'imbuto.

    `truncated` si legge DOPO il blocco `async with misura_turno(...)`: e' il
    segnale del runner, letto una volta sola qui invece che da ogni mestiere.
    `tool_calls` le chiamate di strumento del turno, `{tool, input}`, dalla
    stessa lettura che le scrive nel registro dei turni: un mestiere che le
    attacca alla sua risposta (l'analista, «letture», Task 3.5) non le
    rilegge dal runner per conto suo.

    `turn_id` e' l'id della riga che l'imbuto ha scritto nel registro dei
    turni (`UsageStore.log_turn`), `None` se nessuno misura o se la scrittura
    e' fallita: chi vuole annotare poi quel turno lo collega per
    identificatore, non per istante.

    `answered` e' `False` quando il turno non ha avuto risposta da nessun
    modello: il router ha restituito la sua frase per l'utente
    (`LLMRouter.last_unanswered`), e il registro scrive «fallito». Si legge
    anche senza archivio, come `truncated`. Lo legge `chain_answer`.
    """
    truncated: bool = False
    tool_calls: list = _field(default_factory=list)
    turn_id: str | None = None
    answered: bool = True


def chain_answer(answer, turn: TurnOutcome) -> str:
    """La risposta di un turno sulla catena, o `""` se nessun modello ha
    risposto -- la stessa forma di `reasoning.queue.turn_answer` sul ponte.

    **La frase del router non e' una risposta** (rilievo G29-1, 06/10/2026).
    Quando tutti i backend rifiutano, il router consegna una frase per
    l'utente (l'errore dell'ultimo backend, o «Tutti i provider AI non
    disponibili...»): e' per la chat, che la mostra. Un mestiere di sfondo
    che la leggeva come risposta del modello scriveva conclusioni su un
    guasto -- le ricette un «non capito», che toglie il dispositivo dalle
    domande per sempre.
    """
    return answer if turn.answered else ""


def was_truncated(runner) -> bool:
    """Se l'ultima chiamata di QUESTO compito su `runner` e' stata troncata.

    Il segnale e' `last_truncated`, per chiamata come `last_tool_calls`
    (ContextVar condivisa da `ClaudeRunner`, `OpenAICompatRunner` e
    `LLMRouter`). Un runner che non lo espone non sa dirlo, e allora non si
    afferma niente: e' il caso delle finte nelle prove, non dei runner veri
    -- `tests/test_turno_troncato.py` pretende l'attributo da ognuno.
    """
    return bool(getattr(runner, "last_truncated", False))


def was_tool_leaked(runner) -> bool:
    """Se l'ultima chiamata di QUESTO compito su `runner` ha risposto con uno
    strumento «scappato» come testo (B22). Un runner che non lo espone non sa
    dirlo, e non si afferma niente -- come `was_truncated`."""
    return bool(getattr(runner, "last_tool_leaked", False))


# L'etichetta della staccionata si legge in qualunque maiuscolo: i vecchi
# lettori dell'analista e dell'attuatore accettavano ```JSON, e il lettore unico
# non deve leggere meno di loro (revisione cloud, giro 2, G2-1).
_FENCE = _re.compile(r"```(?:json)?\s*(.*?)```", _re.DOTALL | _re.IGNORECASE)
_BRACKETS = {list: ("[", "]"), dict: ("{", "}")}


def read_json(answer, *, shape: type, what: str,
              truncated: bool = False) -> tuple[list | dict | None, str | None]:
    """**Il lettore unico** delle risposte JSON dei mestieri (D-11): `(dato,
    ragione)` -- o esce il dato della forma chiesta, o esce perche' no. Mai
    un'eccezione: un guasto di forma non deve fermare il giro.

    Fino al 05/10/2026 i lettori erano cinque (osservatore, ricette, analista,
    attuatore, «Rifalla»), e due tolleranze diverse: l'analista rifiutava
    «Ecco l'analisi: {...}», che le ricette leggevano. Qui vive la piu' larga
    delle due -- la staccionata, poi la ricerca per parentesi -- e i mestieri
    tengono solo la validazione della propria forma.

    - `shape`: `list` o `dict`, la forma del valore JSON che il mestiere
      chiede;
    - `what`: come il mestiere chiama quella forma, per la ragione del
      rifiuto («un elenco di decisioni»);
    - `truncated`: il segnale del runner (`TurnOutcome.truncated`). Un turno
      troncato **non si legge** (D2): `TRUNCATED_REASON`.
    """
    if truncated:
        return None, TRUNCATED_REASON
    text = str(answer or "").strip()
    if not text:
        return None, NO_ANSWER_REASON
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    else:
        opening, closing = _BRACKETS[shape]
        start, end = text.find(opening), text.rfind(closing)
        if start != -1 and end > start:
            text = text[start:end + 1]
    try:
        parsed = _json.loads(text)
    except (ValueError, TypeError) as error:
        return None, (f"la risposta non e' un JSON leggibile "
                      f"({type(error).__name__})")
    if not isinstance(parsed, shape):
        return None, f"la risposta non e' {what}"
    return parsed, None


def brake_engaged(archivio, specie: str) -> bool:
    """Se il freno ferma `specie` adesso.

    Vero quando gli ultimi `TRUNCATION_BRAKE` turni registrati di quella
    specie sono TUTTI troncati o rifiutati (`BRAKE_OUTCOMES`). Spento (`None`), non legge nemmeno
    l'archivio. Senza archivio non c'e' niente da contare: non frena.
    """
    if TRUNCATION_BRAKE is None or specie not in BRAKED_SPECIES:
        return False
    if archivio is None:
        return False
    recenti = archivio.turns(limit=TRUNCATION_BRAKE, species=specie)
    return (len(recenti) >= TRUNCATION_BRAKE
            and all(t["outcome"] in BRAKE_OUTCOMES for t in recenti))


def declare_refused(archivio, turn_id: str | None,
                    problems: list[str] | None = None) -> None:
    """Scrive `REFUSED` sulla riga di un turno gia' registrato, con i
    `problems` della risposta (D10; la colonna e' la scelta del proprietario
    del 06/10/2026, «Si', con la colonna»).

    Lo chiama il mestiere che ha rifiutato la risposta, con l'id della riga:
    sulla catena da `TurnOutcome`, sul ponte dalla decisione del job
    (`runner._measure_turn`). Una riga sola per turno -- l'esito si corregge
    dove vive, non si scrive un secondo fatto accanto. **Solo su un turno
    `SUCCEEDED`** (G31-1): un «fallito» o un «troncato» restano quello che
    sono. **Non solleva**, come
    `misura_turno`: un registro rotto non deve far cadere il giro. Senza
    archivio o senza id non c'e' niente da scrivere."""
    if archivio is None or not turn_id:
        return
    try:
        archivio.set_outcome(turn_id, REFUSED, list(problems or []),
                             only_from=SUCCEEDED)
    except Exception as error:  # guasto dell'archivio
        logger.warning("registro dei turni: l'esito «%s» del turno %s non si "
                       "e' potuto scrivere (%s: %s)", REFUSED, turn_id,
                       type(error).__name__, error)


def refused_problems(archivio, specie: str) -> list[str]:
    """I problemi dell'ultimo turno di `specie`, se e' stato rifiutato; `[]`
    altrimenti (D10). Il giro che riprova li rimette nella domanda, sulla
    catena come sul ponte: il modello vede perche' la risposta di prima non
    e' passata. Solo l'ULTIMO turno: un turno riuscito in mezzo dice che i
    problemi di prima sono superati. **Non solleva**, come `declare_refused`."""
    if archivio is None:
        return []
    try:
        recenti = archivio.turns(limit=1, species=specie)
    except Exception as error:  # guasto dell'archivio
        logger.warning("registro dei turni: i problemi di «%s» non si sono "
                       "potuti leggere (%s: %s)", specie,
                       type(error).__name__, error)
        return []
    if not recenti or recenti[0]["outcome"] != REFUSED:
        return []
    return list(recenti[0].get("problems") or [])


def refused_lines(problems: list[str] | None) -> list[str]:
    """Le righe della domanda che riportano i `problems` di una risposta
    rifiutata (D10), o nessuna. Una frase sola per i mestieri che riprovano
    (l'analista, il proponente): la stessa correzione si chiede con le stesse
    parole."""
    if not problems:
        return []
    return [("La tua risposta precedente non e' stata accettata, per "
             "questi motivi. Rispondi di nuovo evitandoli:"),
            *(f"- {problem}" for problem in problems), ""]


@_contextlib.asynccontextmanager
async def misura_turno(archivio, runner, *, specie: str, canale: str,
                       provider: str = "", modello: str = "",
                       soggetto: dict | None = None):
    """Misura un turno di modello: quanto e' durato, quanti giri, quali
    strumenti, e di cosa era fatto il carico a ogni giro.

    **Un imbuto solo**, come `declare_downgrade` qui sotto e per la stessa
    ragione: la dichiarazione copiata a mano in sei posti e' rimasta indietro
    in tre. I chiamanti dichiarano la SPECIE e basta; come si misura lo decide
    questo punto.

    **Perche' esiste** (misurato sulla casa vera, 23/09/2026): «quali luci sono
    accese in casa adesso?» ha impiegato 69 secondi per 35 token di risposta, e
    non c'era modo di sapere perche' -- il registro dell'add-on dice soltanto
    che la richiesta HTTP e' durata 69 secondi. Il moltiplicatore e' il giro di
    strumento: ognuno rispedisce l'intero carico al modello, fino a cinquanta.

    **Non cambia comportamento**, e non deve poterlo cambiare: se la misura
    fallisce, il turno prosegue. Un registro che fa cadere il giro
    dell'analista sarebbe peggio del buco che chiude.

    Il turno si registra **anche quando fallisce**, ed e' il caso piu'
    interessante: un giro che esaurisce le iterazioni e' quello che ha speso
    di piu' senza dare niente.

    **Consegna un `TurnOutcome`** (`async with ... as turno`): dopo il blocco,
    `turno.truncated` dice se il provider ha fermato la risposta al tetto. E'
    l'unica cosa che l'imbuto restituisce al mestiere, e la restituisce perche'
    il mestiere ne ha bisogno per non leggere (D2). Il turno troncato si
    registra con l'esito `TRUNCATED`.
    """
    if specie not in SPECIE:
        # **Qui, non nell'archivio**: il vocabolario vive in questo modulo, e
        # la regola sta dove sta il vocabolario. Solleva invece di scrivere
        # una riga con un nome inventato: due nomi per lo stesso attore
        # renderebbero il registro inservibile proprio sulla domanda per cui
        # esiste -- «chi spende cosa».
        raise ValueError(f"«{specie}» non e' una specie di turno: sono "
                         f"{', '.join(sorted(SPECIE))}")
    # **Un giro, piu' consegne** (spec «le misure complete» §3). Il runner
    # consegna i caratteri PRIMA della chiamata e i token DOPO la risposta:
    # sono lo stesso giro, e diventano una riga sola. Un dizionario per
    # giro, fuso per chiave -- non una lista, che conterebbe due giri dove
    # ce n'e' uno.
    carichi: dict[int, dict] = {}
    # **Per chiamata, non per oggetto.** Il runner e' costruito una volta
    # nell'app e vive quanto l'add-on: un gancio posato su di lui farebbe
    # finire il carico della chat del proprietario dentro la misura del giro
    # notturno dell'analista, se i due si accavallano. E' la stessa cura che
    # `claude_runner` si era gia' data per `last_tool_calls`.
    if brake_engaged(archivio, specie):
        # **Il freno, PRIMA di misurare**: il turno non parte, quindi non c'e'
        # nessun turno da registrare. Lo si dice nel registro dell'add-on, e
        # l'eccezione arriva al giro del mestiere, che la scrive come ogni
        # giro che non e' partito.
        logger.warning(
            "%s: gli ultimi %d turni sono stati troncati al tetto di token o "
            "rifiutati -- il mestiere si ferma finche' qualcuno non guarda",
            specie, TRUNCATION_BRAKE)
        raise TurnBraked(f"«{specie}»: {TRUNCATION_BRAKE} turni troncati o "
                         "rifiutati di fila")
    stato = TurnOutcome()
    gettone = _posa_misura(
        lambda giro, pesi: carichi.setdefault(int(giro), {}).update(pesi))
    inizio = _time.perf_counter()
    esito = SUCCEEDED
    try:
        yield stato
    except Exception:
        esito = "fallito"
        raise
    finally:
        _togli_misura(gettone)
        durata_ms = int((_time.perf_counter() - inizio) * 1000)
        # **Una frase del router non e' una risposta.** Quando nessun backend
        # risponde il router non solleva: restituisce una frase per l'utente
        # (`LLMRouter.last_unanswered`). Senza questa riga il turno si
        # registrava `riuscito` -- 61 turni dell'analista in tre giorni,
        # misurati sulla casa vera il 05/10/2026.
        if esito == SUCCEEDED and getattr(runner, "last_unanswered", False):
            esito = "fallito"
            stato.answered = False
        # **Il troncato si legge FUORI dalla scrittura dell'archivio**: il
        # mestiere ne ha bisogno anche quando nessuno misura (archivio
        # `None`), perche' e' cio' che gli impedisce di leggere una risposta
        # non finita (D2).
        stato.truncated = esito == SUCCEEDED and was_truncated(runner)
        stato.tool_calls = list(getattr(runner, "last_tool_calls", None) or [])
        if stato.truncated:
            esito = TRUNCATED
        elif esito == SUCCEEDED and was_tool_leaked(runner):
            esito = TOOL_LEAKED
        try:
            if archivio is not None:
                chiamate = stato.tool_calls
                strumenti = [c["tool"] for c in chiamate]
                # Gli argomenti, alla stessa posizione dei nomi (spec §7):
                # `log_turn` li riduce e maschera le credenziali.
                argomenti = [c.get("input") or {} for c in chiamate]
                # **I giri li conta la misura stessa.** Un contatore
                # sull'oggetto runner sarebbe una seconda verita' sullo stesso
                # numero -- e per giunta condivisa fra turni paralleli, che e'
                # il difetto che la ContextVar esiste per non avere. Il gancio
                # scatta DUE volte per giro (i caratteri prima della chiamata,
                # i token dopo la risposta), ma entrambe le consegne cadono
                # sulla stessa chiave: i giri sono le chiavi distinte di
                # `carichi`, non le volte che il gancio ha scattato.
                giri = len(carichi)
                if esito == SUCCEEDED and giri >= MAX_GIRI:
                    esito = "esaurito"
                adesso = _time.time()
                # **Chi ha risposto si MISURA, non si deduce.** Il
                # chiamante lo passa quando lo sa; altrimenti lo dice il
                # runner di se' (`provider_name`), che e' l'unico a saperlo
                # davvero. Leggere `model_chain[0]` direbbe «ha risposto il
                # primo della catena», che e' falso proprio nel caso
                # interessante -- quello in cui il primo non ha risposto.
                chi = (provider or getattr(runner, "provider_name", "")
                       or "ignoto")
                # L'uscita del turno e' la somma dei giri SOLO se ogni giro
                # l'ha dichiarata: una somma su buchi direbbe un numero
                # piu' piccolo del vero, con l'aria di essere esatto.
                # Il modello, come il provider: chi chiama lo passa quando lo
                # sa, altrimenti lo dice il runner consegnando i token del
                # giro -- l'ultimo giro e' quello che ha risposto. Fino alla
                # 3.70.0 la chat (che non lo passa) scriveva «ignoto» su
                # ogni turno della catena (misurato dal vivo il 29/09).
                dichiarati = [m for _, p in sorted(carichi.items())
                              if (m := p.pop("model", None))]
                modello = modello or (dichiarati[-1] if dichiarati else "")
                uscite = [p.get("output_tokens") for p in carichi.values()]
                uscita = (sum(uscite) if uscite and
                          all(u is not None for u in uscite) else None)
                ident = archivio.log_turn(
                    species=specie, provider=chi,
                    model=modello or "ignoto", channel=canale,
                    subject=soggetto,
                    duration_ms=durata_ms, iterations=giri,
                    tools=strumenti, outcome=esito, now=adesso,
                    output_tokens=uscita, tool_args=argomenti)
                stato.turn_id = ident
                for giro, pesi in sorted(carichi.items()):
                    if "tools_chars" not in pesi:
                        # Un giro coi soli token: la consegna dei caratteri
                        # non c'e' stata. Non si inventano caratteri a zero.
                        logger.warning(
                            "misura del turno «%s»: il giro %d ha i token ma "
                            "non la composizione -- riga non scritta",
                            specie, giro)
                        continue
                    archivio.log_payload(ident, iteration=giro, now=adesso,
                                         **pesi)
        except Exception as errore:  # pragma: no cover - guasto dell'archivio
            logger.warning("la misura del turno «%s» non si e' potuta "
                           "scrivere (%s: %s)", specie,
                           type(errore).__name__, errore)


def declare_downgrade(app, *, agent: str, reason: str,
                      now: float | None = None) -> None:
    """Un giro e' passato dal forfait al consumo: lo si dichiara.

    **Un imbuto solo, e non e' pedanteria.** La regola del proprietario (13
    agosto) e' che il ripiego si annuncia ogni volta. Finche' la dichiarazione
    e' stata una riga di `logger` copiata a mano in sei posti, tre copie su sei
    sono rimaste indietro: analista, attuatore e ricette scrivevano nel
    registro e basta -- e quei tre girano di notte, senza nessuno davanti allo
    schermo. E' il difetto che questo modulo dichiara chiuso per la DOMANDA
    («chi risponde?») e che era ancora aperto per la RISPOSTA («e allora
    dillo»).

    **Il motivo vuoto non e' un ripiego** e non si scrive: il ponte spento e'
    la configurazione che il proprietario ha scelto, e contarlo riempirebbe la
    pagina di righe che dicono «sto usando quello che hai scelto».

    Non solleva mai: sta sul percorso dei giri automatici, e una dichiarazione
    che facesse cadere il giro dell'analista sarebbe peggio del difetto che
    chiude.
    """
    if not reason:
        return
    logger.warning(
        "%s: il piano non puo' servire questo giro (%s): si scende alla "
        "catena. Il costo cambia -- dal forfait al consumo.", agent, reason)
    store = app.get("usage")
    if store is None:
        return
    try:
        store.log_fallback(agent, reason,
                           now=_time.time() if now is None else now)
    except Exception as error:  # pragma: no cover - guasto dell'archivio
        logger.warning("il ripiego di «%s» non si e' potuto scrivere (%s: %s)",
                       agent, type(error).__name__, error)


def who_answered(app) -> str:
    """Il backend che ha risposto DAVVERO, misurato. `""` se non si sa.

    **Si misura, non si deduce.** La tentazione e' leggere `model_chain[0]`,
    cioe' «ha risposto il primo della catena»: sarebbe falso proprio nel caso
    che conta, perche' il router RIPIEGA -- il primo puo' aver fallito e aver
    risposto il secondo. Si legge quindi il registro degli esiti, che il ciclo
    di ripiego aggiorna per nome di backend dopo ogni chiamata, e si prende il
    primo della catena il cui ultimo esito e' un successo.

    **Va chiamata DOPO la chiamata al modello**, mai prima: prima misurerebbe
    l'esito del turno precedente.

    Vive qui e non piu' in `handlers_chat` perche' e' una meta' della stessa
    decisione di `who_answers`, e perche' adesso la chiedono due porte: una
    regola che vale solo se il chiamante se la ricorda non e' una regola.
    """
    registry = app.get("occurrence_registry")
    if registry is None:
        return ""
    for name in (app.get("model_chain") or []):
        occurrence = registry.occurrence(name)
        if occurrence and occurrence["tipo"] == "risposto":
            return name
    return ""


def bridge_model(app) -> str:
    """Il modello che il proprietario ha scelto per il ponte: un alias della
    CLI (`ponte.modello`, gia' validato all'ingresso del campo da
    `handlers_models._clean_subscription_model`).

    **Lo porta ogni turno che si accoda, non solo la chat** (decisione 11
    della spec, Tappa 6 Task 4). Fino al 05/10/2026 solo
    `handlers_chat._enqueue_chat_job` lo metteva nel job, e il lavoratore
    ripiegava su «sonnet» per tutti gli altri: la scelta del proprietario
    valeva per meta' dei turni del piano. Il predefinito e' quello di
    `_STORE_DEFAULTS`, l'unico: non se ne scrive un secondo qui.
    """
    return ((app.get("models_config") or {}).get("ponte", {}).get("modello")
            or _STORE_DEFAULTS["ponte"]["modello"])


def who_answers(app) -> tuple[str, str]:
    """`("ponte", "")` oppure `("catena", motivo)`.

    Il motivo e' vuoto quando non c'e' nessun ripiego da dichiarare, ed e' una
    chiave di `_DOWNGRADE_REASONS` quando ce n'e' uno. Vedi il docstring del
    modulo per la distinzione, che non e' una sfumatura: e' la differenza fra
    una configurazione e un prelievo.
    """
    if not (app.get("bridge_active") and _bridge_on(app)):
        return "catena", ""
    can, reason = _subscription_can_answer(app)
    if not can:
        return "catena", reason
    return "ponte", ""


# -- la partenza unica (Tappa 6, Task 7; R4, D-35) ------------------------------

def chain_runner(app):
    """Il runner della catena: il router, o il runner Claude se il router non
    c'e'. `None` se non c'e' nessun modello a cui chiedere.

    **Una lettura sola** (D-35). Fino al 06/10/2026 la stessa espressione era
    scritta in nove punti, fra `server.py`, la chat, la promessa, il
    «Rifalla» e la pagina dei consumi.
    """
    return app.get("llm_router") or app.get("claude_runner")


class Start(_NamedTuple):
    """Chi risponde a un turno, e con cosa: la strada (`"ponte"` o
    `"catena"`), il motivo del ripiego, e il runner della catena (`None` sul
    ponte, o se non c'e' nessun modello). Si spacchetta come una tupla."""
    route: str
    downgrade: str
    runner: object | None


def start(app, species: str) -> Start:
    """**La partenza di un turno**: chiede `who_answers`, sceglie il runner
    della catena e, se il turno parte davvero sulla catena, dichiara il
    ripiego (`declare_downgrade`).

    E' la sequenza che i giri del cervello e la promessa scrivevano a mano,
    ognuno nel suo ordine. Il ripiego si dichiara solo se c'e' un runner: un
    giro che non parte non e' passato dal forfait al consumo.
    """
    route, downgrade = who_answers(app)
    runner = chain_runner(app) if route == "catena" else None
    if runner is not None:
        declare_downgrade(app, agent=species, reason=downgrade)
    return Start(route, downgrade, runner)


async def chain_turn(runner, species: str, *, usage, max_tokens: int,
                     soggetto: dict | None = None, modello: str = "",
                     tools: list[dict] | None = None,
                     **chat) -> tuple[object, TurnOutcome]:
    """**Un turno sulla catena**: l'unico posto del prodotto che chiama
    `runner.chat` (R4; `tests/test_un_turno.py` lo cerca nel sorgente).
    Torna la risposta e l'esito del turno (`TurnOutcome`).

    - **Il tetto si dichiara sempre**: `max_tokens` non ha un predefinito, e
      ogni mestiere passa il suo (Tappa 6, Task 4).
    - **Gli strumenti sono un elenco d'ammissione**: un turno puo' avere solo
      quelli che la dichiarazione del suo mestiere ammette, e un mestiere
      autosufficiente nessuno. Un turno fuori elenco non parte: solleva,
      come `misura_turno` per una specie sconosciuta.
    - **Si misura sempre**, con `misura_turno`, sul canale «catena».
    """
    # Una specie sconosciuta la rifiuta `misura_turno`, qui sotto, col suo
    # vocabolario.
    if tools is not None and species in SPECIES:
        asked = {d["name"] for d in tools}
        allowed = set(SPECIES[species].tools_for_turn())
        if not asked <= allowed:
            raise ValueError(f"«{species}» non ammette gli strumenti "
                             f"{', '.join(sorted(asked - allowed))}")
    async with misura_turno(usage, runner, specie=species, canale="catena",
                            soggetto=soggetto, modello=modello) as turn:
        answer = await runner.chat(max_tokens=max_tokens, tools=tools, **chat)
    return answer, turn


def enqueue_turn(app, species: str, wake: dict, context: dict, *,
                 thread=None, now: float | None = None,
                 priority: int | None = None) -> tuple[str, int]:
    """**Un turno sul ponte**: l'unico posto che accoda. Torna l'id del job e
    i minuti che il turno ha per avere risposta.

    Dalla dichiarazione del mestiere vengono il `kind` del job e la
    precedenza; dall'archivio il modello del proprietario (`bridge_model`,
    decisione 11) e la scadenza (`bridge_deadline_min`). Fino al 06/10/2026
    ognuno dei sei accodamenti le scriveva a mano. `now` serve a chi annota
    l'accodamento con lo stesso istante del job.

    `priority` scavalca quella del mestiere per un turno che una persona
    aspetta davanti alla pagina: «Rifalla» e' un turno del proponente con la
    precedenza della chat (attori, Task 4.4, scelta del proprietario del
    06/10/2026: la ragione di D4, «la chat passa avanti», e' chi aspetta).
    """
    declared = SPECIES[species]
    deadline_min = bridge_deadline_min(app.get("models_config"))
    now = _time.time() if now is None else now
    job_id = app["reasoning_queue"].enqueue(
        declared.kind, wake, {**context, "model": bridge_model(app)},
        now + deadline_min * 60, now=now, thread=thread,
        priority=declared.priority if priority is None else priority)
    return job_id, deadline_min


def turn_in_flight(app, kind: str, *, wake_key: str | None = None) -> bool:
    """Se un turno di quella specie sta gia' aspettando una risposta dal piano.

    **La coda e' l'unico posto in cui questo fatto vive.** Tenere il `job_id`
    anche altrove -- su `app`, in un archivio -- sarebbe un doppione ai sensi
    della fondamenta 2, e per giunta uno che non sopravvive a un riavvio,
    mentre il job si'.

    **Uno SCADUTO non e' in volo**, e questa riga e' costata cinque giorni di
    silenzio. Misurato sulla casa il 21/09/2026: l'analista non scriveva
    un'analisi dal 16, coi resoconti tutti archiviati. Il 17 un suo turno era
    stato accodato al ponte; poi il ponte e' stato spento, e la spazzata delle
    scadenze gira **solo a ponte acceso** -- quel turno e' rimasto `pending`
    per sempre. La guardia dell'analista guardava soltanto «c'e' una
    risposta?», e ha risposto «in volo» a ogni giro, per sempre.

    Lo scope e le ricette avevano la riga giusta da settimane, ciascuno nella
    propria copia: **tre guardie, e una nata senza**. Adesso e' una sola, e
    chi la legge legge anche il perche'.

    Sta qui, accanto a `enqueue_turn`, dal 06/10/2026 (attori, Task 4.2): il
    giro del proponente vive fuori da `server.py`, e la guardia deve essere la
    stessa per tutti i giri.

    `wake_key` guarda solo i turni con quella chiave nella sveglia: il giro
    del proponente e i suoi «Rifalla» stanno nella stessa specie, e un
    rifacimento in volo non deve fermare il giro orario (attori, Task 4.4).
    """
    queue = app.get("reasoning_queue")
    if queue is None:
        return False
    turn = queue.latest(kind, wake_key=wake_key)
    if turn is None:
        return False
    return (turn["status"] in ("pending", "claimed")
            and turn["deadline_ts"] > _time.time())


#: Quanto si aspetta prima di richiedere, dopo una risposta vuota.
#:
#: **Un'ora, e il numero viene da un conto.** Una risposta vuota da un ponte
#: che SA ragionare quella specie non e' piu' un rifiuto istantaneo: vuol dire
#: che la CLI non ha risposto, e quel giro e' costato. Richiedere a ogni
#: passaggio dell'anello sarebbero **144 turni al giorno** contro il tetto
#: giornaliero del piano: un ponte rotto svuoterebbe da solo la quota, e da
#: li' in poi ogni turno -- chat compresa -- passerebbe ai provider a
#: pagamento.
#:
#: Un'ora sono 24 tentativi al giorno nel caso peggiore, e un solo giro di
#: attesa quando il guasto e' passato.
#:
#: Dal 06/10/2026 frena anche l'analista, dopo una risposta vuota, fallita o
#: rifiutata: il suo giro e' orario, quindi un'ora vuol dire un tentativo ogni
#: due giri, e la sua domanda pesa ~35.000 token.
RETRY_HOLD_S = 3600.0


def too_soon_to_ask_again(app, kind: str, *, wake_key: str | None = None) -> bool:
    """Se l'ultimo turno di quella specie e' finito senza risposta utile da
    meno di un'ora. `wake_key` restringe ai turni con quella chiave nella
    sveglia, come `turn_in_flight`."""
    queue = app.get("reasoning_queue")
    turn = queue.latest(kind, wake_key=wake_key) if queue else None
    if turn is None:
        return False
    deciso = turn.get("decided_ts") or turn.get("created_ts") or 0
    return (_time.time() - deciso) < RETRY_HOLD_S
