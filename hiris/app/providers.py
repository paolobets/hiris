"""I provider dei modelli: quali esistono, come si chiamano, chi puo' rispondere.

**La tabella dei provider** (Tappa 7, Task 9; D8). Fino a qui i cinque id
-- `subscription`, `claude`, `openai`, `openrouter`, `ollama` -- vivevano in
tredici tabelle complete e una decina di elenchi parziali, in Python e in
JavaScript (contati nel codice il 07/10/2026): i nomi in `model_resolution` e
una seconda volta nei consumi, cinque ordini scritti a mano, sei definizioni di
«ha una credenziale», gli id validi della catena in tre moduli. Ogni fatto di
un provider ha qui una casa sola, e il resto la chiede.

Cosa vive qui, e cosa no:

- **un fatto per provider** sta in un campo della sua `Provider`: il nome, la
  natura, dove va il dato, cosa manca quando manca, la credenziale (una
  funzione), dove si scrive la scelta del modello, il modello automatico e
  l'elenco di riserva, i tempi con l'unita' nel nome, le parole dei consumi;
- **l'ordine fisso** e' l'ordine di `PROVIDERS`, e non un campo: un campo
  `posizione` accanto all'ordine della tupla sarebbero due ordini, e il
  giorno in cui divergessero nessuno saprebbe quale vale;
- **i tre preset** (`PRESETS`) sono le sole altre liste ordinate di provider:
  sono decisioni del prodotto («Risparmio» comincia da Ollama), non derivate;
- **le frasi composte** (la riga di stato, il riquadro «Adesso») restano in
  `model_resolution`, che le compone con i campi di qui.

**Le viste si chiedono a ogni chiamata** (`all_providers`, `ids`,
`chain_members`, ...), mai copiate in una costante al momento dell'import: e'
cio' che permette a un sesto provider aggiunto a `PROVIDERS` di comparire nella
pagina e nella catena senza toccare nessun altro modulo, e alla prova che lo
verifica di sostituire la tabella e vederlo arrivare.

Funzioni PURE come `model_resolution`, salvo `subscription_has_token`, che e' la
misura della credenziale del piano e legge l'ambiente apposta.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

# LA MISURA DELLA CREDENZIALE DEL PIANO, in un posto solo.
#
# «Il piano ha un token?» era scritta quattro volte, in quattro moduli, e
# governava quattro decisioni diverse: se il worker del ponte PARTE
# (`server.should_start_agent_worker`), se il piano ENTRA nella catena
# (`server._credentials`), cosa la pagina Modelli DICHIARA
# (`handlers_models._config_has_credential`), e se il turno si ACCODA
# (`steering._subscription_can_answer`).
#
# Oggi erano identiche. Il giorno in cui il token seguisse la strada che hanno
# gia' fatto `ponte.attivo`, `tetto_giornaliero` e `scadenza_min` -- da
# `config.yaml` all'archivio -- si aggiornerebbe il file della pagina, perche'
# e' il file della pagina. La pagina direbbe «Piano Claude Max, funziona, primo
# della catena»; il worker non partirebbe, e la chat ripiegherebbe su Claude
# API a consumo. L'utente pagherebbe a token credendo di essere sul forfait.
#
# Viveva in `model_resolution` fino al Task 9 della Tappa 7: e' la credenziale
# di un provider, e le credenziali stanno nella tabella.
SUBSCRIPTION_TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"


def subscription_has_token() -> bool:
    """Vero se la credenziale dell'abbonamento Claude c'e'.

    Solo la PRESENZA, mai il valore: chi chiama non deve poterlo stampare per
    sbaglio in un log o in una risposta.
    """
    return bool(os.environ.get(SUBSCRIPTION_TOKEN_VAR, "").strip())


def _subscription_token(_sources: Mapping[str, Any]) -> bool:
    return subscription_has_token()


def _value_at(key: str) -> Callable[[Mapping[str, Any]], bool]:
    """La credenziale che sta in una chiave dell'app (`app["claude_api_key"]`...).

    La scrive l'avvio (`server._on_startup`) una volta sola, ed e' la stessa
    che leggono la pagina Modelli e chi costruisce i runner: prima l'avvio
    guardava le variabili lette dall'ambiente e la pagina guardava -- per
    Claude API -- di nuovo l'ambiente OPPURE il runner costruito, cioe' due
    definizioni della stessa credenziale.
    """
    def present(sources: Mapping[str, Any]) -> bool:
        return bool(sources.get(key))
    return present


@dataclass(frozen=True)
class Provider:
    """Un provider, con tutto cio' che serve a interpretarlo da solo.

    I tempi portano l'unita' nel nome (`reply_timeout_s`): un `120` senza
    unita' e' un frammento, e ce n'erano quattro.
    """

    #: L'identificatore: catena, archivio dei modelli, registro degli esiti,
    #: consumi. Dal Task 9 (D9a) e' UNO anche per il piano: `subscription` e'
    #: il provider, `ponte` e' solo la strada (`steering.who_answers`).
    id: str
    #: Il nome a schermo: quello della pagina Modelli (D10a), detto uguale
    #: anche dai Consumi, dalla chat e dal registro.
    name: str
    #: Quattro categorie, non un prezzo: HIRIS non ha una fonte di listini, e
    #: un prezzo vecchio e' una bugia che sembra un servizio (progetto §12.1).
    nature: str
    #: Dove va il dato, e sotto quali condizioni (reperto C-5, 23/09/2026):
    #: un prodotto che manda i dati di casa a un fornitore terzo deve dirlo
    #: dove il gesto si fa.
    privacy: str
    #: Che cosa manca, quando manca: tre credenziali diverse (un token OAuth,
    #: una chiave, un indirizzo) e la parola le distingue.
    missing_reason: str
    #: La credenziale: una funzione delle FONTI (l'app, o un dizionario con le
    #: stesse chiavi). Solo la presenza, mai il valore.
    credential: Callable[[Mapping[str, Any]], bool]
    #: DOVE si scrive la scelta del modello, come percorso dentro l'archivio
    #: dei modelli (`models_config.json`). E' un dato e non una regola: la
    #: pagina lo applica alla cieca, senza sapere che il modello di Ollama non
    #: vive in `provider_models`.
    model_path: tuple[str, ...]
    #: Il modello che risponde quando nessuno ne ha scelto uno. `""` dove la
    #: scelta c'e' sempre (il piano nasce con un alias) o non c'e' un
    #: automatico (Ollama usa solo cio' che e' scaricato).
    auto_model: str = ""
    #: L'elenco che il pannello mostra quando la lettura viva fallisce,
    #: dichiarato come riserva dalla riga di provenienza.
    reserve_models: tuple[str, ...] = ()
    #: L'ospite che si interroga per l'elenco dei modelli: serve a nominare
    #: CHI non ha risposto.
    host: str = ""
    #: Il valore e' un ALIAS che segue il modello corrente (il piano) o un
    #: identificatore che punta a una cosa fissa (progetto §6.2).
    model_alias: bool = False
    #: Si governa da `chain_order`. Il piano no: sta in testa o fuori, e la sua
    #: presenza discende da `ponte.attivo` (decisione del proprietario, 13
    #: agosto).
    chain_member: bool = True
    #: Per RISPONDERE serve un modello scelto, oltre alla credenziale: Ollama,
    #: la cui credenziale e' il SOLO indirizzo (il modello e' una decisione).
    needs_chosen_model: bool = False
    #: Quanto si aspetta una risposta, in secondi, quando l'utente non ha
    #: scelto altro. Il numero e' quello di oggi (Ollama, 120): era scritto in
    #: quattro posti -- l'archivio, l'avvio due volte, la pagina -- e il runner.
    reply_timeout_s: int | None = None
    #: La parola con cui i Consumi contano le chiamate: il piano conta TURNI
    #: (la CLI non espone le richieste una per una), gli altri richieste.
    usage_unit: str = "richieste"
    #: La nota della sezione dei Consumi: la differenza fra `misurato` e
    #: `reale` si dichiara una volta per sezione, perche' la decide il provider.
    usage_note: str = ""
    #: Lo stato del costo FISSO del provider, quando non si calcola chiamata
    #: per chiamata: `compreso` (il piano non espone il prezzo del turno),
    #: `gratuito` (in casa). `""` dove il costo si calcola.
    cost_state: str = ""


SUBSCRIPTION = Provider(
    id="subscription",
    name="Piano Claude Max",
    nature="nel piano",
    # Il piano NON ha la frase di Claude API: le condizioni d'uso e di
    # conservazione del Piano Max sono diverse da quelle dell'API a consumo, e
    # una frase buona per tutti e due nasconderebbe proprio la differenza che
    # conta.
    privacy=("I tuoi messaggi e la conoscenza della casa passano da Anthropic "
             "(USA), sotto le condizioni d’uso e di conservazione del Piano "
             "Claude Max, diverse da quelle dell’API a consumo."),
    missing_reason="manca il token",
    credential=_subscription_token,
    # Dalla fetta «il modello del piano» il piano ha un campo suo: prima il
    # suo modello era un effetto di quello di Claude API, un campo solo per
    # due economie opposte.
    model_path=("ponte", "modello"),
    model_alias=True,
    chain_member=False,
    usage_unit="turni",
    usage_note=("L’abbonamento non espone il prezzo del singolo turno. I token "
                "si', e sono questi."),
    cost_state="compreso",
)

CLAUDE = Provider(
    id="claude",
    name="Claude API",
    nature="a consumo",
    privacy=("I tuoi messaggi e la conoscenza della casa passano da Anthropic "
             "(USA)."),
    missing_reason="manca la chiave",
    credential=_value_at("claude_api_key"),
    model_path=("provider_models", "claude"),
    auto_model="claude-sonnet-4-6",
    # La RISERVA: tre nomi scritti a mano che invecchiano, dichiarati come
    # tali. L'elenco vero si legge da `GET /v1/models` (verificato sulla
    # documentazione ufficiale il 15/08/2026). La voce «auto» non c'e': nell'
    # archivio «auto» e' la STRINGA VUOTA, e il pannello la offre da se'.
    reserve_models=("claude-haiku-4-5-20251001", "claude-sonnet-4-6",
                    "claude-opus-4-7"),
    host="api.anthropic.com",
    usage_note="Costo calcolato sul listino Anthropic.",
)

OPENROUTER = Provider(
    id="openrouter",
    name="OpenRouter",
    nature="a consumo",
    privacy=("I tuoi messaggi passano da OpenRouter (USA) e dal fornitore del "
             "modello che scegli."),
    missing_reason="manca la chiave",
    credential=_value_at("openrouter_api_key"),
    model_path=("provider_models", "openrouter"),
    # Pagante ma affidabile, e NON quello di OpenAI: su OpenRouter `gpt-4o`
    # non e' nemmeno un nome valido.
    auto_model="anthropic/claude-sonnet-4-6",
    # La RISERVA, e soltanto quella: cio' che si mostra quando openrouter.ai
    # non risponde. Verificato contro openrouter.ai il 22/08/2026: dei
    # precedenti undici nomi, SETTE erano stati ritirati o rinominati -- i
    # cinque `:free` e i due `anthropic/*`. Restano i quattro vivi. **Questa
    # lista invecchiera' di nuovo, ed e' accettato**: si vede solo quando la
    # lettura viva fallisce, e la riga di provenienza dichiara che viene dal
    # sorgente.
    reserve_models=("openrouter:openai/gpt-4o", "openrouter:openai/gpt-4.1",
                    "openrouter:google/gemini-2.5-flash",
                    "openrouter:mistralai/mistral-large"),
    host="openrouter.ai",
    usage_note=("Costo dichiarato da OpenRouter: e' quanto e' stato "
                "addebitato, non una stima."),
)

OPENAI = Provider(
    id="openai",
    name="OpenAI",
    nature="a consumo",
    privacy="I tuoi messaggi passano dai server di OpenAI (USA).",
    missing_reason="manca la chiave",
    credential=_value_at("openai_api_key"),
    model_path=("provider_models", "openai"),
    auto_model="gpt-4o",
    reserve_models=("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"),
    host="api.openai.com",
    usage_note="Costo calcolato sul listino OpenAI.",
)

OLLAMA = Provider(
    id="ollama",
    name="Ollama (in casa)",
    nature="in casa",
    privacy="Resta in casa tua: il tuo dato non esce dalla tua rete.",
    missing_reason="manca l’indirizzo",
    # La credenziale di Ollama e' il SOLO indirizzo: l'indirizzo e' cio' che
    # si custodisce, il modello e' cio' che si decide (vedi
    # `needs_chosen_model`).
    credential=_value_at("local_model_url"),
    model_path=("ollama", "modello"),
    needs_chosen_model=True,
    reply_timeout_s=120,
    usage_note="Modelli in casa: nessun costo.",
    cost_state="gratuito",
)

#: I provider, NELL'ORDINE FISSO: quello di «Fuori dalla catena», delle
#: sezioni dei Consumi e di ogni elenco in cui un ordine non significa niente
#: -- e quindi non puo' contraddire niente. E' l'ordine di ripiego di
#: `balanced`, con il piano subito dopo Claude API.
PROVIDERS: tuple[Provider, ...] = (CLAUDE, SUBSCRIPTION, OPENROUTER, OPENAI, OLLAMA)


@dataclass(frozen=True)
class Preset:
    """Un gesto che RIFA' la catena: non uno stato persistente da cui la catena
    si deriva (progetto §5.3)."""

    key: str
    name: str
    order: tuple[str, ...]


#: I tre preset di «Rifai la catena». Erano scritti due volte -- nel router
#: (`_STRATEGY_ORDER`) e nella pagina (`PRESET`) -- tenuti legati da una
#: prova che confrontava le due copie. Adesso la pagina li riceve.
PRESETS: tuple[Preset, ...] = (
    # Comincia dal piu' capace (Claude API), ma economizza sul ripiego
    # preferendo OpenRouter all'attacco dedicato di OpenAI, prima di finire su
    # Ollama.
    Preset("balanced", "Bilanciato",
           (CLAUDE.id, OPENROUTER.id, OPENAI.id, OLLAMA.id)),
    # Prima il gratuito in casa, poi il cloud economico, poi il cloud pieno.
    Preset("cost_first", "Risparmio",
           (OLLAMA.id, OPENROUTER.id, OPENAI.id, CLAUDE.id)),
    Preset("quality_first", "Qualità massima",
           (CLAUDE.id, OPENAI.id, OPENROUTER.id, OLLAMA.id)),
)

#: Il preset dell'opzione da cui viene `strategia_ultima` (`llm_strategy:
#: "balanced"` in config.yaml), e quello con cui nasce la catena di un
#: archivio che non ce l'ha.
DEFAULT_PRESET = PRESETS[0].key


# ── Le viste: si chiedono, non si copiano ──────────────────────────────────

def all_providers() -> tuple[Provider, ...]:
    """I provider nell'ordine fisso, letti ADESSO dalla tabella."""
    return PROVIDERS


def ids() -> tuple[str, ...]:
    """Gli id nell'ordine fisso."""
    return tuple(p.id for p in all_providers())


def get(provider_id: str) -> Provider | None:
    """Il provider con quell'id, o `None` se la tabella non lo conosce."""
    for p in all_providers():
        if p.id == provider_id:
            return p
    return None


def chain_members() -> tuple[str, ...]:
    """Gli id che si governano da `chain_order`, nell'ordine fisso: gli unici
    che l'archivio accetta in catena e gli unici che il router conosce."""
    return tuple(p.id for p in all_providers() if p.chain_member)


def preset(key: str) -> Preset | None:
    for p in PRESETS:
        if p.key == key:
            return p
    return None


def display_name(provider_id: str) -> str:
    """Il nome a schermo; l'id stesso per un provider che la tabella non
    conosce (un nome inventato sarebbe peggio)."""
    p = get(provider_id)
    return p.name if p else provider_id


def nature(provider_id: str) -> str:
    p = get(provider_id)
    return p.nature if p else ""


def privacy(provider_id: str) -> str:
    """Dove va il dato di chi usa questo provider. `""` se non si sa.

    Il vuoto attraversa, come per la natura: una frase approssimativa sulla
    privacy e' peggio del silenzio, perche' viene letta come una garanzia.
    """
    p = get(provider_id)
    return p.privacy if p else ""


def missing_reason(provider_id: str) -> str:
    p = get(provider_id)
    return p.missing_reason if p else "manca la credenziale"


def chosen_model(provider: Provider, store: Mapping[str, Any] | None) -> str:
    """La scelta del modello di questo provider, letta dove l'archivio la tiene
    (`model_path`). `""` quando non c'e'."""
    value: Any = store or {}
    for key in provider.model_path:
        value = value.get(key) if isinstance(value, Mapping) else None
    return value if isinstance(value, str) else ""


# ── La credenziale, e chi puo' rispondere ──────────────────────────────────

def credentials_present(sources: Mapping[str, Any]) -> dict[str, bool]:
    """Le credenziali, e nient'altro: per ogni provider, se la credenziale c'e'.

    **Una definizione sola** (Task 9). Erano sei: tre in `server.py`, una nella
    pagina Modelli (`_config_has_credential`, che per Claude API guardava
    l'ambiente OPPURE il runner costruito), una nello sterzo e una nel calcolo
    di chi risponde. `sources` e' l'app (o un dizionario con le stesse chiavi):
    la stessa misura all'avvio, nella pagina e in ogni altro lettore.

    La credenziale di Ollama e' il SOLO indirizzo. Prima era `url and model`,
    cioe' il NOME DEL MODELLO faceva parte del test di credenziale -- ma
    l'indirizzo e' cio' che si custodisce e il modello e' cio' che si decide.
    Chi puo' RISPONDERE si misura a parte (`can_answer_at_startup`).
    """
    return {p.id: bool(p.credential(sources)) for p in all_providers()}


def can_answer_at_startup(credentials: Mapping[str, bool],
                          store: Mapping[str, Any] | None) -> dict[str, bool]:
    """Chi può davvero RISPONDERE, all'avvio.

    Non è una seconda rappresentazione della
    credenziale: sono due fatti diversi, e per quattro provider su cinque
    coincidono. Per Ollama no -- l'indirizzo è ciò che si custodisce, il
    modello è ciò che si decide -- e la differenza è esattamente il buco che
    il Task 7 aveva dichiarato: con la sola credenziale, Ollama poteva finire
    in `model_chain` senza un runner dietro, cioè comparire come anello
    numerato in una pagina che descrive il runtime mentre
    `LLMRouter._ordered_backends_with_name` lo saltava in silenzio.
    """
    return {p.id: bool(credentials.get(p.id))
            and (not p.needs_chosen_model or bool(chosen_model(p, store)))
            for p in all_providers()}


def can_answer_now(backend_map: Mapping[str, Any],
                   store: Mapping[str, Any] | None) -> dict[str, bool]:
    """Chi può rispondere ADESSO: la stessa regola dell'avvio
    (`can_answer_at_startup`), RILETTA invece che ricordata.

    Un backend costruito, e -- per chi ne ha bisogno -- un
    modello scelto: il runner locale esiste con il solo indirizzo, ma senza
    un modello sarebbe un anello che `_ordered_backends_with_name` salta in silenzio
    mentre la pagina lo disegna numerato (il buco che il Task 9 ha chiuso).
    """
    answers = {}
    for name, backend in backend_map.items():
        p = get(name)
        answers[name] = backend is not None and (
            p is None or not p.needs_chosen_model or bool(chosen_model(p, store)))
    return answers


# ── L'appartenenza alla catena ─────────────────────────────────────────────
#
# Viveva in `model_activation.py` (51 righe, una funzione: voce M-26), che il
# Task 9 ha fuso qui. Fino alla 2.4.1 quel modulo derivava i provider ATTIVI da
# cinque interruttori dell'add-on incrociati con le credenziali, con la regola
# di compatibilita' `legacy = not any(toggles.values())`; con la catena come
# unica verita' l'ambiguita' non esiste, e restava questa sola funzione.

def providers_in_chain(chain_order: list[str] | None,
                       credentials: Mapping[str, bool]) -> list[str]:
    """L'ordine dell'utente, filtrato a chi ha una credenziale.

    Nessun accodamento, nessun ripiego su un ordine di strategia, nessun
    doppione. Una catena vuota resta vuota: e' uno stato leggibile, non un
    guasto da coprire. Chi diventa credenziato compare in «Fuori dalla
    catena», visibile, a un gesto di distanza: NIENTE entra in catena senza
    che qualcuno ce l'abbia messo.
    """
    inside: list[str] = []
    for provider_name in chain_order or []:
        if provider_name in inside:
            continue
        if credentials.get(provider_name):
            inside.append(provider_name)
    return inside


def outside_chain(answers: Mapping[str, bool], chain: list[str]) -> list[str]:
    """Chi puo' rispondere e NON sta in catena: HIRIS non lo consulta.

    Viveva in linea dentro `server._on_startup` (`_fuori`), con l'ordine fisso
    meno il piano scritto a mano una sesta volta.
    """
    return [pid for pid in chain_members() if answers.get(pid) and pid not in chain]



# ── Cio' che la pagina riceve invece di ricopiarlo ─────────────────────────

def page_payload() -> dict:
    """L'ordine fisso e i tre preset, per la pagina Modelli.

    Erano le due liste che `static/config/models-route.js` ricopiava
    (`FIXED_ORDER`, `PRESET`), tenute legate al Python da una prova che
    confrontava le stringhe. Le parole di ogni riga (nome, natura, dove va il
    dato) arrivano gia' sulla riga: qui viaggia solo cio' che la pagina non
    puo' leggere altrove.
    """
    return {
        "ordine_fisso": list(ids()),
        "preset": [{"chiave": p.key, "nome": p.name, "ordine": list(p.order)}
                   for p in PRESETS],
    }
