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

Il punto di questo modulo, non solo la sua forma: prima, se il chatbot
seminato da `_seed_default_chatbot()` mancava (id sbagliato, file corrotto,
mai girato l'avvio), `handlers_chat.py` degradava in silenzio a un
BASE_SYSTEM_PROMPT e SMETTEVA di persistere la cronologia -- senza dirlo a
nessuno. Con `ImpostazioniChat` quel caso non e' piu' rappresentabile: i
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

_FILE_IMPOSTAZIONI = "impostazioni_chat.json"

# Permessi del file: solo il proprietario legge e scrive -- stesso valore e
# stessa motivazione di `token_interno.PERMESSI_FILE` (vedi `salva()` sotto).
_PERMESSI_FILE = 0o600

# Review finale fetta E3, Important #2: la versione precedente istruiva a
# chiamare `get_home_status()`/`get_area_entities()`, morti dalla E2 Task 8 --
# catturato dal vivo in un turno di chat reale. Riscritta sui due strumenti
# veri di oggi (casa/strumenti.py: cerca, guarda). Spostato qui invariato da
# `chatbot_engine.py::ChatbotEngine._DEFAULT_SYSTEM_PROMPT` (era li' righe
# 231-237).
#
# Fix della review totale della fetta "il ponte riceve il nucleo" (parita' A,
# I-1). Questo testo era scritto all'IMPERATIVO INCONDIZIONATO -- «Per
# scoprire cosa c'e' in casa USA `cerca` ... e `guarda`», «USA I TOOL per
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
# capoversi sotto (`prompts._GUIDA_SENZA_STRUMENTI`: «se il prompt qui sopra
# nomina degli strumenti ... quelle istruzioni non si applicano»). Con le
# parole di quel file: «un ordine non emesso e' una difesa, una frase che lo
# contraddice e' una speranza» -- e una speranza calibrata su UN modello, che
# l'abbonamento puo' cambiare sotto di noi.
#
# Il default e' NOSTRO, non dell'utente: riscritto in forma CONDIZIONALE, vera
# su ENTRAMBI i percorsi. Il sincrono non perde nulla (l'antecedente e' vero:
# di la' i quattro strumenti di casa/strumenti.py esistono davvero, e l'ordine
# di usarli e' lo stesso di prima); il ponte legge il ramo "altrimenti", che
# e' esattamente cio' che puo' fare -- rispondere col contesto e dichiarare
# cio' che non c'e'. I due nomi `cerca` e `guarda` restano SCRITTI: la guida
# del ponte li nomina per negarli, e `test_il_prompt_del_ponte_smentisce_gli_
# strumenti_nominati_dalla_persona` asserisce che il default continui a
# nominarli.
#
# Il riferimento alla "sezione CASA" e' uscito con l'imperativo: dal Task 1 di
# questa fetta il contesto della chat non e' piu' una sezione sola ma il
# NUCLEO INTERO (`componi_contesto_chat` -> `costruisci_nucleo`), che compone
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
# `api/handlers_impostazioni.py`, `PUT /api/impostazioni-chat`, la pagina
# `#/impostazioni` -- quindi un `impostazioni_chat.json` sul disco non e' piu'
# necessariamente scritto a mano: puo' essere stato salvato dall'utente dalla
# pagina. Cio' che NON cambia e' la conclusione: un meccanismo alla
# `_LEGACY_DEFAULT_PROMPTS` (riconoscere per uguaglianza esatta un prompt
# vecchio e riscriverlo) NON serve e sarebbe dannoso -- sovrascrivere il
# prompt che l'utente ha scelto e' peggio del difetto che chiuderebbe. La via
# di ritorno al default esiste ed e' esplicita: si svuota il campo nella
# pagina (`handlers_impostazioni.valida`, `system_prompt` vuoto ->
# `DEFAULT_SYSTEM_PROMPT`), che e' una decisione dell'utente, non nostra.
DEFAULT_SYSTEM_PROMPT = (
    "Sei l'assistente principale per la gestione della smart home.\n"
    "Se in questa conversazione hai gli strumenti `cerca` (trova per nome un'area,"
    " un'entità o un dispositivo) e `guarda` (il dettaglio di una cosa sola, col suo"
    " stato), usali per scoprire cosa c'è in casa e per i valori precisi — temperature,"
    " stati correnti — invece di dedurli.\n"
    "Altrimenti rispondi con ciò che trovi nel contesto in fondo al prompt (la casa,"
    " ciò che le persone hanno detto, le sessioni precedenti): è uno snapshot di"
    " orientamento, non una lettura fatta adesso. Dichiara apertamente ciò che non c'è,"
    " invece di inventarlo."
)


@dataclass
class ImpostazioniChat:
    """La configurazione dell'unica conversazione che HIRIS sa avere.

    Ogni campo ha il proprio default nel codice -- non serve un seed
    all'avvio (`_seed_default_chatbot` non esiste piu') perche' un'istanza di
    questa classe e' gia' completa appena costruita, con `ImpostazioniChat()`
    a zero argomenti."""
    nome: str = "HIRIS"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    model: str = "auto"
    response_mode: str = "auto"
    thinking_budget: int = 0
    max_chat_turns: int = 0
    restrict_to_home: bool = False

    @classmethod
    def carica(cls, data_dir: str) -> "ImpostazioniChat":
        """Non solleva mai e non restituisce mai `None`: un file assente,
        illeggibile o corrotto produce i default di sopra (dichiarato nel
        log, non un pass muto) -- mai uno stato "impostazioni mancanti" che
        il chiamante dovrebbe scoprire da solo."""
        path = os.path.join(data_dir, _FILE_IMPOSTAZIONI)
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as exc:
            logger.error(
                "Impostazioni chat illeggibili in %s (%s): uso i default nel codice.",
                path, exc,
            )
            return cls()
        default = cls()
        return cls(
            nome=raw.get("nome", default.nome),
            system_prompt=raw.get("system_prompt") or default.system_prompt,
            model=raw.get("model", default.model),
            response_mode=raw.get("response_mode", default.response_mode),
            thinking_budget=int(raw.get("thinking_budget", 0) or 0),
            max_chat_turns=int(raw.get("max_chat_turns", 0) or 0),
            restrict_to_home=bool(raw.get("restrict_to_home", default.restrict_to_home)),
        )

    def salva(self, data_dir: str) -> None:
        """Scrittura atomica e durevole: file temporaneo, `fsync`, `os.replace`.

        Un crash a meta' scrittura non deve mai lasciare un
        `impostazioni_chat.json` troncato che il prossimo avvio legge come
        JSON valido ma incompleto -- e queste sono le impostazioni con cui la
        chat riparte dopo un riavvio, cioe' l'unico stato che le sopravvive.

        fetta E5 Task 2: la disciplina e' allineata a quella di
        `token_interno._scrivi_token`, che e' il precedente di questo ramo per
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
        path = os.path.join(data_dir, _FILE_IMPOSTAZIONI)
        tmp = path + ".tmp"
        data = {
            "nome": self.nome,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "response_mode": self.response_mode,
            "thinking_budget": self.thinking_budget,
            "max_chat_turns": self.max_chat_turns,
            "restrict_to_home": self.restrict_to_home,
        }
        os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
        with _save_lock:
            descrittore = os.open(
                tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _PERMESSI_FILE,
            )
            try:
                with os.fdopen(descrittore, "w", encoding="utf-8") as f:
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
