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

# L'unico bot esiste, non ha un id che lo distingua da altri -- questo e'
# usato solo come chiave transitoria della cronologia (chat_store.py) e del
# payload di compatibilita' (GET /api/chatbots, handlers_chatbots.py) finche'
# quella superficie non si smonta insieme al frontend (fetta E5).
ID_CHAT_DEFAULT = "hiris-default"

_FILE_IMPOSTAZIONI = "impostazioni_chat.json"

# Review finale fetta E3, Important #2: la versione precedente istruiva a
# chiamare `get_home_status()`/`get_area_entities()`, morti dalla E2 Task 8 --
# catturato dal vivo in un turno di chat reale. Riscritta sui due strumenti
# veri di oggi (casa/strumenti.py: cerca, guarda). Spostato qui invariato da
# `chatbot_engine.py::ChatbotEngine._DEFAULT_SYSTEM_PROMPT` (era li' righe
# 231-237).
DEFAULT_SYSTEM_PROMPT = (
    "Sei l'assistente principale per la gestione della smart home.\n"
    "Per scoprire cosa c'è in casa usa `cerca` (trova per nome un'area, un'entità o un"
    " dispositivo) e `guarda` (il dettaglio di una cosa sola, col suo stato).\n"
    "La sezione CASA in fondo al prompt è uno snapshot di orientamento:"
    " usa i tool per valori precisi come temperature e stati correnti."
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
        """Scrittura atomica tmp+replace, stessa disciplina di
        `ChatbotEngine._save()` (chatbot_engine.py, uscito con questo task):
        un crash a meta' scrittura non deve mai lasciare un
        `impostazioni_chat.json` troncato che il prossimo avvio legge come
        JSON valido ma incompleto."""
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
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)


# Stesso motivo del lock di modulo in ChatbotEngine (`_save_lock`, uscito con
# lei): due `salva()` concorrenti sullo stesso file non devono poter
# accavallare la scrittura del `.tmp` e l'`os.replace`.
_save_lock = threading.Lock()
