"""fetta E4 Task 4 ("un bot solo"): esce l'entita' Chatbot, nascono le
impostazioni della chat.

La mappa del prodotto (docs/design/2026-08-05-mappa-funzionalita.md) da' a
Chatbot il verdetto SEMPLIFICA: un solo bot esiste (seminato dal codice), non
serve un'entita' con un id -- serve la configurazione di UNA conversazione.
Dei ~20 campi del vecchio `Chatbot` (chatbot_engine.py, uscito con questo
task), il turno di chat ne leggeva sette; gli altri esistevano solo per
sostenere la molteplicita' (id, seed, migrazione agents.json, scheduler,
CRUD). Due dei sette letti erano gia' inerti in pratica -- `max_tokens`
(sempre soppiantato dal tetto CHAT_MAX_TOKENS di claude_runner.py) e
`require_confirmation` (l'impianto OTP che lo consumava e' uscito con la
fetta E2 Task 5) -- e diventano costanti dirette in handlers_chat.py invece
di campi qui.

I campi di oggi sono SETTE: `nome`, `system_prompt`, `response_mode`,
`thinking_budget`, `max_chat_turns`, `restrict_to_home`, `giorni_conservazione`
(quest'ultimo arrivato con la fetta "Modelli" (2.0), Task 12 -- vedi il suo
paragrafo qui sotto). Il settimo dei sei originali, `model`,
e' uscito con la fetta "la catena diventa l'unica verita'" (Task 4): era uno
SCAVALCO -- se valorizzato, `handlers_chat` lo passava a `LLMRouter.chat`,
che con un modello diverso da "auto" chiama `_route()` una volta sola,
saltando la catena della pagina Modelli e annullando ogni ripiego. Il modello
si sceglie per provider, in `models_config.json`, e la chat chiede sempre
"auto". Un file scritto da una versione precedente che porta ancora quella
chiave viene DICHIARATO nel log da `carica()`, non ignorato in silenzio (vedi
li' il perche' non si migra).

Il punto di questo modulo, non solo la sua forma: prima, se il chatbot
seminato da `_seed_default_chatbot()` mancava (id sbagliato, file corrotto,
mai girato l'avvio), `handlers_chat.py` degradava in silenzio a un
BASE_SYSTEM_PROMPT e SMETTEVA di persistere la cronologia -- senza dirlo a
nessuno. Con `ChatSettings` quel caso non e' piu' rappresentabile: i
default vivono nel codice (qui sotto), `carica()` non solleva mai e non
restituisce mai `None` -- "mancare" non e' uno stato che questo tipo puo'
assumere.
"""
import json
import logging
import os
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "impostazioni_chat.json"

# Permessi del file: solo il proprietario legge e scrive -- stesso valore e
# stessa motivazione di `token_interno.FILE_PERMISSIONS` (vedi `salva()` sotto).
_FILE_PERMISSIONS = 0o600

# Review finale fetta E3, Important #2: la versione precedente istruiva a
# chiamare `get_home_status()`/`get_area_entities()`, morti dalla E2 Task 8 --
# catturato dal vivo in un turno di chat reale. Riscritta sui due strumenti
# veri di oggi (casa/strumenti.py: cerca, guarda). Spostato qui invariato da
# `chatbot_engine.py::ChatbotEngine._DEFAULT_SYSTEM_PROMPT` (era li' righe
# 231-237).
#
# Fix della review totale della fetta "il ponte riceve il nucleo" (parita' A,
# I-1). Questo testo era scritto all'IMPERATIVO INCONDIZIONATO -- «Per
# scoprire cosa c'e' in casa USA `search` ... e `view`», «USA I TOOL per
# valori precisi» -- e arriva VERBATIM al ponte: `_build_system_prompt`
# (api/handlers_chat.py) lo mette in `context["system_prompt"]`, il job lo
# porta ad `agent/runner.py::_reason_chat`, e `agent/prompts.py::
# build_chat_messages` lo compone subito dopo BASE. Sul ponte quei due
# strumenti NON esistono (nessun `--mcp-config`, nessun `--allowedTools`:
# `_chat_claude_args`, pinnato da `test_argv_del_ponte_non_collega_nessuno_
# strumento`): era l'ULTIMO ordine ineseguibile rimasto in quel prompt.
#
# E' la stessa classe di difetto per cui, al Task 2 di questa fetta,
# `BASE_SYSTEM_PROMPT` e' stata spezzata in due meta' (claude_runner.py, il
# commento sopra `BASE_IDENTITA`): li' l'ordine falso ha smesso di essere
# EMESSO, qui restava emesso e affidato alla smentita che lo segue tre
# capoversi sotto (`prompts._GUIDE_WITHOUT_TOOLS`: «se il prompt qui sopra
# nomina degli strumenti ... quelle istruzioni non si applicano»). Con le
# parole di quel file: «un ordine non emesso e' una difesa, una frase che lo
# contraddice e' una speranza» -- e una speranza calibrata su UN modello, che
# l'abbonamento puo' cambiare sotto di noi.
#
# Il default e' NOSTRO, non dell'utente: riscritto in forma CONDIZIONALE, vera
# su ENTRAMBI i percorsi. Il sincrono non perde nulla (l'antecedente e' vero:
# di la' gli strumenti di casa/strumenti.py esistono davvero, e l'ordine
# di usarli e' lo stesso di prima); il ponte legge il ramo "altrimenti", che
# e' esattamente cio' che puo' fare -- rispondere col contesto e dichiarare
# cio' che non c'e'. I due nomi `search` e `view` restano SCRITTI: la guida
# del ponte li nomina per negarli, e `test_il_prompt_del_ponte_smentisce_gli_
# strumenti_nominati_dalla_persona` asserisce che il default continui a
# nominarli.
#
# Il riferimento alla "sezione CASA" e' uscito con l'imperativo: dal Task 1 di
# questa fetta il contesto della chat non e' piu' una sezione sola ma il
# NUCLEO INTERO (`compose_chat_context` -> `compose_briefing`), che compone
# «## La casa», «## Notevole adesso», «## Cio' che la casa fa gia' da sola»,
# «## Cio' che le persone hanno detto», «## Cio' che HIRIS ignora», piu' «##
# Sessioni precedenti». Nominare una sola sezione maiuscola che non esiste
# piu' con quel nome sarebbe la solita dichiarazione falsa al presente.
#
# COSA SUCCEDE SU UN'INSTALLAZIONE ESISTENTE (verificato, non presunto).
# Il predecessore che SI persisteva (`chatbots.json`, con il suo
# `_LEGACY_DEFAULT_PROMPTS` che riscriveva i default invecchiati) e' uscito
# alla fetta E4 Task 4, e con una decisione utente esplicita di NON migrare il
# prompt salvato -- si riparte coi default nel codice (il log di quel silenzio
# e' in server.py, `_chatbots_json_path`). Quindi: questo fix raggiunge ogni
# installazione che non abbia gia' un `impostazioni_chat.json` proprio, perche'
# il vecchio testo non e' persistito da nessuna parte.
#
# Aggiornamento fetta E5 Task 2: fino a quel task la frase qui sopra diceva
# «nessun codice di produzione scrive `impostazioni_chat.json`, `salva()` non
# ha nessun chiamante fuori dai test, e la superficie HTTP che lo scrivera' e'
# della fetta E5». Quella superficie ORA esiste --
# `api/handlers_impostazioni.py`, `PUT /api/chat-settings`, la pagina
# `#/impostazioni` -- quindi un `impostazioni_chat.json` sul disco non e' piu'
# necessariamente scritto a mano: puo' essere stato salvato dall'utente dalla
# pagina. Cio' che NON cambia e' la conclusione: un meccanismo alla
# `_LEGACY_DEFAULT_PROMPTS` (riconoscere per uguaglianza esatta un prompt
# vecchio e riscriverlo) NON serve e sarebbe dannoso -- sovrascrivere il
# prompt che l'utente ha scelto e' peggio del difetto che chiuderebbe. La via
# di ritorno al default esiste ed e' esplicita: si svuota il campo nella
# pagina (`handlers_impostazioni.valida`, `system_prompt` vuoto ->
# `DEFAULT_SYSTEM_PROMPT`), che e' una decisione dell'utente, non nostra.
#
# fetta «comandare» (Task 7): questo testo NON e' stato esteso a `execute`, ed
# e' una decisione, non una dimenticanza. Il testo qui sotto non e' FALSO --
# non dice da nessuna parte che HIRIS non agisce -- e' soltanto INCOMPLETO:
# nomina due strumenti a titolo di esempio in una condizionale («Se in questa
# conversazione hai gli strumenti `search` ... e `view` ..., usali per
# scoprire cosa c'e' in casa»), che resta vera parola per parola con cinque
# strumenti nel catalogo. Le tre ragioni per lasciarlo stare:
#
#   1. Questa e' la PERSONA, il campo che l'utente riscrive dalla pagina
#      Impostazioni. Le regole del PRODOTTO stanno in
#      `claude_runner.BASE_TOOL_RULES`, l'unico testo emesso esattamente
#      quando gli strumenti ci sono e su ENTRAMBI i percorsi -- ed e' li' che
#      il Task 6 ha messo `execute` con tutte le sue regole (gli id esatti,
#      raccontare cosa e' successo, l'ambiguita'). Scrivere le regole
#      dell'azione anche qui le renderebbe cancellabili dall'utente con una
#      modifica alla persona: una regola di sicurezza d'uso che sparisce
#      quando si personalizza il tono.
#   2. Il default raggiunge solo chi NON ha un `impostazioni_chat.json`
#      proprio. Cambiarlo creerebbe due popolazioni con personae diverse per
#      un testo che, sulla popolazione che l'ha salvato, non si aggiorna
#      comunque -- e la via per riallinearsi (svuotare il campo) e' gia' la
#      stessa in entrambi i casi.
#   3. Il ponte, sul ramo di degrado, deve poter SMENTIRE ogni strumento che
#      la persona nomina (`prompts._GUIDE_WITHOUT_TOOLS`, e il test
#      `test_il_prompt_del_ponte_smentisce_gli_strumenti_nominati_dalla_
#      persona`). Ogni nome aggiunto qui e' un nome in piu' da tenere
#      allineato di la': il conto delle dichiarazioni da mantenere a mano
#      cresce, ed e' proprio il difetto che questo task chiude.
#
# Cio' che questa fetta rende vero e non era vero prima e' la PRIMA riga --
# «Sei l'assistente principale per la gestione della smart home» -- che fino
# al Task 5 prometteva una gestione che il prodotto non poteva fare. Non c'e'
# stato bisogno di toccarla: e' diventata vera da sola.
DEFAULT_SYSTEM_PROMPT = (
    "Sei l'assistente principale per la gestione della smart home.\n"
    "Se in questa conversazione hai gli strumenti `search` (trova per nome un'area,"
    " un'entità o un dispositivo) e `view` (il dettaglio di una cosa sola, col suo"
    " stato), usali per scoprire cosa c'è in casa e per i valori precisi — temperature,"
    " stati correnti — invece di dedurli.\n"
    "Altrimenti rispondi con ciò che trovi nel contesto in fondo al prompt (la casa,"
    " ciò che le persone hanno detto, le sessioni precedenti): è uno snapshot di"
    " orientamento, non una lettura fatta adesso. Dichiara apertamente ciò che non c'è,"
    " invece di inventarlo."
)


# fetta "Modelli" (2.0), Task 12: `giorni_conservazione` si sposta qui da
# `history_retention_days` (opzione dell'add-on). Non e' aspetto, non e' una
# chiave, non e' rete -- e' una decisione sulla conversazione, come gli altri
# sei campi di questa classe.
#
# Il numero fa DUE lavori, e nessuno dei due era mai stato scritto da nessuna
# parte prima di questo task:
#   1. la potatura notturna (`server.py::_run_retention`, cron alle 3) cancella
#      dal disco i messaggi piu' vecchi di questo numero di giorni;
#   2. lo STESSO numero limita quanto `chat_store.load_context()` rilegge
#      della conversazione in corso -- abbassarlo non libera spazio, fa
#      DIMENTICARE PRIMA. Un file/opzione mai toccato non lo diceva: la
#      descrizione in `#/impostazioni` lo dichiara adesso.
# E `0` non cancella e non limita MAI niente: i due lettori di `chat_store`
# scrivono la stessa regola al contrario (`if days > 0` in `load_context`,
# `if retention_days <= 0: return 0` in `delete_old_messages`) -- il contrario
# di cio' che chiunque si aspetta da una "conservazione" messa a zero, e per
# questo va detto esplicitamente, non lasciato dedurre.
#
# **Versione A della migrazione, applicata a questo singolo campo** (la
# sorella maggiore, su tutto `models_config.json`, e' `migrazione_opzioni.py`
# del Task 6 -- questo campo non ci passa attraverso, perche' vive in un
# archivio diverso, `impostazioni_chat.json`): se il file non porta ancora la
# chiave, `carica()` la prende da `HISTORY_RETENTION_DAYS`, la variabile che
# `run.sh` esporta dall'opzione `history_retention_days` di `config.yaml`.
# Una volta sola per lettura del file (non un seed permanente: un file che GIA'
# porta la chiave, anche a `0`, vince sempre sull'opzione -- vedi
# `_giorni_da_ambiente` sotto), dichiarata nel log ESATTAMENTE quando il valore
# copiato non e' quello che i default del codice avrebbero comunque prodotto
# (stessa disciplina del blocco `if "model" in raw` qui sotto, e dello stesso
# "non annuncia se non c'e' niente da annunciare" imparato al debito F della
# migrazione di `models_config.json`, Task 6/7: un'installazione MAI toccata
# non deve leggere un log a ogni riavvio).
#
# **FATTO, versione B (3.0.0, 14 agosto 2026)**: `history_retention_days` e'
# uscita dallo schema dell'add-on, e `run.sh` non esporta piu'
# `HISTORY_RETENTION_DAYS`. Su un'installazione aggiornata dal Supervisor
# questo ramo non trova piu' niente da leggere -- e non deve trovarlo: il
# valore e' gia' sul disco, perche' l'avvio della 2.5.0 lo ha SCRITTO
# (`server._on_startup`, `il_file_non_porta_i_giorni`), non solo letto.
#
# La lettura resta, ed e' la stessa eccezione dichiarata per
# `migrazione_opzioni.semina` e `server._chain_as_it_was`: serve a
# un'installazione che salti la 2.5.0 e arrivi qui con l'ambiente ancora
# popolato dal vecchio `run.sh`. Via Supervisor non puo' succedere (le chiavi
# fuori schema vengono scartate prima che /data/options.json esista); in
# sviluppo si'. Esce con la fetta successiva, insieme alle altre due, quando
# nessuna installazione potra' piu' arrivare non seminata.
#
# Il censimento la elenchera' fra le «variabili lette e mai esportate da
# run.sh»: e' corretto, ed e' dichiarato nel rapporto del Task 13.
def _retention_days_from_environment(default: int) -> int:
    raw = os.environ.get("HISTORY_RETENTION_DAYS")
    if raw is None:
        return default
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return default
    if days != default:
        logger.info(
            "impostazioni_chat.json non specifica 'giorni_conservazione': "
            "arriva dall'opzione dell'add-on 'history_retention_days' (valore "
            "%d). Da ora si cambia dalla pagina Impostazioni chat -- governa "
            "sia la potatura notturna sia quanto HIRIS rilegge della "
            "conversazione in corso.",
            days,
        )
    return days


def file_lacks_retention_days(data_dir: str) -> bool:
    """`True` se `impostazioni_chat.json` non ha (ancora) la chiave
    `giorni_conservazione`, file assente o illeggibile compresi.

    Esiste perche' `carica()` LEGGE attraverso l'ambiente ma non SCRIVE, e
    `salva()` ha un solo chiamante di produzione: la PUT della pagina
    «Impostazioni chat». Un utente che quella pagina non la apre mai non
    produce mai la chiave sul disco -- e la versione B (3.0.0, che
    `history_retention_days` l'ha tolta dallo schema) troverebbe un ambiente
    muto e farebbe valere il default del codice, 90. Chi aveva messo 30 se lo ritrova a 90
    senza una riga che lo dica; chi aveva messo **0** -- «non cancellare mai»
    -- se lo ritrova a 90 e la potatura notturna delle 3 gli cancella le
    conversazioni piu' vecchie di novanta giorni. Per questo campo, la versione
    A senza una scrittura all'avvio non migra NIENTE: legge e basta.

    Il chiamante e' `server._on_startup`, subito dopo `carica()`."""
    path = os.path.join(data_dir, _SETTINGS_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return True
    return not isinstance(raw, dict) or "giorni_conservazione" not in raw


@dataclass
class ChatSettings:
    """La configurazione dell'unica conversazione che HIRIS sa avere.

    Ogni campo ha il proprio default nel codice -- non serve un seed
    all'avvio (`_seed_default_chatbot` non esiste piu') perche' un'istanza di
    questa classe e' gia' completa appena costruita, con `ChatSettings()`
    a zero argomenti."""
    name: str = "HIRIS"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    response_mode: str = "auto"
    thinking_budget: int = 0
    max_chat_turns: int = 0
    restrict_to_home: bool = False
    retention_days: int = 90

    @classmethod
    def load(cls, data_dir: str) -> "ChatSettings":
        """Non solleva mai e non restituisce mai `None`: un file assente,
        illeggibile o corrotto produce i default di sopra (dichiarato nel
        log, non un pass muto) -- mai uno stato "impostazioni mancanti" che
        il chiamante dovrebbe scoprire da solo.

        Task 12: file assente e file corrotto convergono sullo stesso `raw =
        {}` invece di due `return cls()` separati (com'era prima) -- e' cio'
        che permette a ENTRAMBI i casi di consultare `HISTORY_RETENTION_DAYS`
        per `giorni_conservazione` (`_giorni_da_ambiente` sopra), invece di
        far scomparire silenziosamente la versione A della migrazione ogni
        volta che il file non e' leggibile."""
        path = os.path.join(data_dir, _SETTINGS_FILE)
        raw: dict = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as exc:
                logger.error(
                    "Impostazioni chat illeggibili in %s (%s): uso i default nel codice.",
                    path, exc,
                )
                raw = {}
        if "model" in raw:
            # Silenzio dichiarato (fetta "la catena diventa l'unica verita'"):
            # il modello della chat scavalcava l'intera pagina Modelli --
            # sceglieva il provider da se' (`LLMRouter._route`), saltava la
            # catena e annullava il ripiego. Il campo e' uscito; il valore
            # salvato non viene migrato (non c'e' dove metterlo: il modello si
            # sceglie per provider, in `models_config.json`) ne' riscritto da
            # `salva()`, quindi sparira' dal file al primo salvataggio. A
            # differenza di `brain_model` in `load_models_config` -- che
            # sopravvive perche' `save_models_config` fa
            # lettura-modifica-scrittura -- qui NON si conserva: sarebbe
            # conservare una scelta che il prodotto non sa piu' eseguire.
            logger.info(
                "impostazioni_chat.json contiene 'model' (%r) di una versione "
                "precedente: non e' piu' letto -- la chat usa sempre la catena "
                "della pagina Modelli. Sparira' dal file al primo salvataggio.",
                raw.get("model"),
            )
        default = cls()
        # NOTA il contrasto deliberato con `thinking_budget`/`max_chat_turns`
        # due righe sopra: quelli usano `raw.get(k, 0) or 0`, che trasforma
        # ANCHE un valore presente ma falsy (0) nel ripiego -- corretto per
        # loro perche' il ripiego E' 0. Per `giorni_conservazione` il ripiego
        # (90) e' diverso dal valore-sentinella (0 = "non cancellare mai"):
        # lo stesso pattern trasformerebbe silenziosamente uno 0 scelto
        # dall'utente nel default. Qui si distingue "chiave assente" (versione
        # A: consulta l'ambiente) da "chiave presente" (vince sempre, 0
        # compreso) con un `in` esplicito, non con la verita' del valore.
        if "giorni_conservazione" in raw:
            value = raw.get("giorni_conservazione")
            retention_days = (
                default.retention_days if value is None else int(value)
            )
        else:
            retention_days = _retention_days_from_environment(default.retention_days)
        return cls(
            name=raw.get("nome", default.name),
            system_prompt=raw.get("system_prompt") or default.system_prompt,
            response_mode=raw.get("response_mode", default.response_mode),
            thinking_budget=int(raw.get("thinking_budget", 0) or 0),
            max_chat_turns=int(raw.get("max_chat_turns", 0) or 0),
            restrict_to_home=bool(raw.get("restrict_to_home", default.restrict_to_home)),
            retention_days=retention_days,
        )

    def save(self, data_dir: str) -> None:
        """Scrittura atomica e durevole: file temporaneo, `fsync`, `os.replace`.

        Un crash a meta' scrittura non deve mai lasciare un
        `impostazioni_chat.json` troncato che il prossimo avvio legge come
        JSON valido ma incompleto -- e queste sono le impostazioni con cui la
        chat riparte dopo un riavvio, cioe' l'unico stato che le sopravvive.

        fetta E5 Task 2: la disciplina e' allineata a quella di
        `token_interno._write_token`, che e' il precedente di questo ramo per
        un file di `/data` che deve sopravvivere ai riavvii. Tre differenze
        rispetto alla versione precedente (che era il semplice tmp+replace
        ereditato da `ChatbotEngine._save()`):

        1. **`flush` + `fsync` prima del `replace`**: senza, `os.replace` puo'
           pubblicare un nome che punta a contenuto non ancora sul disco -- su
           una perdita di alimentazione il file esiste, e' "valido" per il
           filesystem, ed e' vuoto. L'atomicita' del rename non e' durabilita'
           del contenuto: sono due garanzie distinte, e qui servono entrambe.
        2. **Permessi stretti alla creazione** (`os.open` con `_PERMESSI_FILE`,
           non un `chmod` dopo): il file contiene il prompt di sistema, cioe'
           testo che l'utente ha scritto. Come in `token_interno.py`, su Linux
           -- la piattaforma dell'add-on -- e' 0600; su Windows, dove gira solo
           la suite, i bit di gruppo/altri non esistono e la chiamata incide di
           fatto solo sul flag di sola lettura: e' il piu' stretto possibile
           *su questa piattaforma*, non un'illusione di isolamento.
        3. **Il temporaneo si rimuove se la scrittura fallisce**, invece di
           restare li' a sporcare `/data` dopo ogni errore.

        Solleva `OSError` se il disco non collabora: il chiamante HTTP
        (`api/handlers_impostazioni.handle_save_impostazioni`) la cattura e
        risponde dichiarando il guasto, invece di rispondere "salvato".
        """
        path = os.path.join(data_dir, _SETTINGS_FILE)
        tmp = path + ".tmp"
        data = {
            "nome": self.name,
            "system_prompt": self.system_prompt,
            "response_mode": self.response_mode,
            "thinking_budget": self.thinking_budget,
            "max_chat_turns": self.max_chat_turns,
            "restrict_to_home": self.restrict_to_home,
            "giorni_conservazione": self.retention_days,
        }
        os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
        with _save_lock:
            descriptor = os.open(
                tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_PERMISSIONS,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            os.replace(tmp, path)


# Stesso motivo del lock di modulo in ChatbotEngine (`_save_lock`, uscito con
# lei): due `salva()` concorrenti sullo stesso file non devono poter
# accavallare la scrittura del `.tmp` e l'`os.replace`.
_save_lock = threading.Lock()
