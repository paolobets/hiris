"""Chi risponde a questo turno: il ponte, o la catena.

**Una domanda sola, una casa sola.** Fino al 22 agosto 2026 la regola viveva
dentro `api/handlers_chat.handle_chat`, intrecciata con la persistenza del
turno e con la coda -- e il turno di una promessa, che quella funzione non la
attraversa mai, ne aveva per forza una seconda: andava dritto a `llm_router`,
dove il ponte non e' nemmeno un anello (`_VALID_BACKEND_NAMES` conosce claude,
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
from dataclasses import dataclass as _dataclass

from .api.handlers_models import _STORE_DEFAULTS
from .model_resolution import subscription_has_token

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
#: chiedendo». `mind/observer.py` e `mind/recipe_turn.py` passano tutti e due
#: `agent_type="observer"`, quindi misurando su quello l'osservatore e le
#: ricette sarebbero indistinguibili -- proprio la distinzione che il
#: proprietario vuole vedere.
SPECIE = frozenset({"analista", "attuatore", "chat", "osservatore",
                    "promessa", "ricette"})

#: **L'esito di un turno fermato dal tetto di token** (Tappa 6, D-58; D2).
#: Fino al 05/10/2026 il registro lo chiamava «riuscito»: misurato in
#: `docs/misure/2026-10-tappa-0.md`, 7 turni dell'analista su 8 si fermavano
#: al tetto, e nessuna riga lo diceva. Il segnale viene dal runner
#: (`last_truncated`), cioe' da cio' che il provider ha dichiarato -- mai dal
#: testo della risposta.
TRUNCATED = "troncato"

#: Cosa riceve il mestiere al posto delle decisioni, quando il turno e' stato
#: troncato (D2, approvata il 05/10/2026): **non si legge**. Un JSON tagliato a
#: meta' che per caso si chiude e' l'unico modo di inventare decisioni da una
#: risposta che il modello non ha finito -- e nessun nuovo tentativo: prima si
#: vede, poi il tetto si sceglie misurando (D3).
TRUNCATED_REASON = ("la risposta e' stata troncata al tetto di token: non "
                    "si legge una risposta che il modello non ha finito")

#: Una risposta vuota non e' un silenzio: e' un modello che non ha risposto.
NO_ANSWER_REASON = "il modello non ha risposto"

#: **Il freno** (Tappa 6, Task 3, passo 5): dopo questi turni troncati DI FILA
#: lo stesso mestiere si ferma e lo dice. **Il numero non c'e' ancora, e il
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


class TurnBraked(RuntimeError):
    """Il freno dei troncati ha fermato questo mestiere: il turno non parte."""


@_dataclass
class TurnOutcome:
    """Cio' che il turno sa di se' quando e' finito, consegnato dall'imbuto.

    `truncated` si legge DOPO il blocco `async with misura_turno(...)`: e' il
    segnale del runner, letto una volta sola qui invece che da ogni mestiere.
    """
    truncated: bool = False


def was_truncated(runner) -> bool:
    """Se l'ultima chiamata di QUESTO compito su `runner` e' stata troncata.

    Il segnale e' `last_truncated`, per chiamata come `last_tool_calls`
    (ContextVar condivisa da `ClaudeRunner`, `OpenAICompatRunner` e
    `LLMRouter`). Un runner che non lo espone non sa dirlo, e allora non si
    afferma niente: e' il caso delle finte nelle prove, non dei runner veri
    -- `tests/test_turno_troncato.py` pretende l'attributo da ognuno.
    """
    return bool(getattr(runner, "last_truncated", False))


_FENCE = _re.compile(r"```(?:json)?\s*(.*?)```", _re.DOTALL)
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
    """Se il freno dei troncati ferma `specie` adesso.

    Vero quando gli ultimi `TRUNCATION_BRAKE` turni registrati di quella
    specie sono TUTTI troncati. Spento (`None`), non legge nemmeno
    l'archivio. Senza archivio non c'e' niente da contare: non frena.
    """
    if TRUNCATION_BRAKE is None or specie not in BRAKED_SPECIES:
        return False
    if archivio is None:
        return False
    recenti = archivio.turns(limit=TRUNCATION_BRAKE, species=specie)
    return (len(recenti) >= TRUNCATION_BRAKE
            and all(t["outcome"] == TRUNCATED for t in recenti))


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
            "%s: gli ultimi %d turni si sono fermati al tetto di token -- il "
            "mestiere si ferma finche' il tetto non cambia", specie,
            TRUNCATION_BRAKE)
        raise TurnBraked(f"«{specie}»: {TRUNCATION_BRAKE} turni troncati di fila")
    stato = TurnOutcome()
    gettone = _posa_misura(
        lambda giro, pesi: carichi.setdefault(int(giro), {}).update(pesi))
    inizio = _time.perf_counter()
    esito = "riuscito"
    try:
        yield stato
    except Exception:
        esito = "fallito"
        raise
    finally:
        _togli_misura(gettone)
        durata_ms = int((_time.perf_counter() - inizio) * 1000)
        # **Il troncato si legge FUORI dalla scrittura dell'archivio**: il
        # mestiere ne ha bisogno anche quando nessuno misura (archivio
        # `None`), perche' e' cio' che gli impedisce di leggere una risposta
        # non finita (D2).
        stato.truncated = esito == "riuscito" and was_truncated(runner)
        if stato.truncated:
            esito = TRUNCATED
        try:
            if archivio is not None:
                chiamate = getattr(runner, "last_tool_calls", None) or []
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
                if esito == "riuscito" and giri >= MAX_GIRI:
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
