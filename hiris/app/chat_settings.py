"""Le impostazioni della chat: la configurazione dell'UNICA conversazione che
HIRIS sa avere.

Un bot solo, senza id. I campi stanno in `impostazioni_chat.json`: `nome`,
`system_prompt`, `response_mode`, `thinking_budget`, `max_chat_turns`,
`restrict_to_home`, `giorni_conservazione`. Il modello non e' fra questi: si
sceglie per provider, in `models_config.json`.

Il punto di questo modulo: i default vivono nel codice (qui sotto), e `load()`
non restituisce mai `None` -- un file assente o illeggibile produce i default.
"Mancare" non e' uno stato che questo tipo puo' assumere.
"""
import json
import logging
import os
from dataclasses import dataclass

from .storage import write_json_atomic

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "impostazioni_chat.json"

# Il default e' scritto in forma CONDIZIONALE («Se in questa conversazione hai
# lo strumento `search` ... Altrimenti ...»): resta vero sia in un turno che ha
# gli strumenti sia in uno che non li ha. Un ordine incondizionato di usare uno
# strumento che il turno non possiede sarebbe un ordine ineseguibile.
# `test_il_prompt_del_ponte_smentisce_gli_strumenti_nominati_dalla_persona`
# asserisce che il default continui a nominare `search`.
#
# Questa e' la PERSONA, il campo che l'utente riscrive dalla pagina
# Impostazioni: le regole del prodotto sull'uso degli strumenti stanno in
# `claude_runner.BASE_TOOL_RULES`, dove una modifica alla persona non le
# cancella.
#
# Il default raggiunge solo chi non ha salvato un prompt proprio. Un prompt
# salvato non si riscrive mai da qui: per tornare al default l'utente svuota
# il campo nella pagina (`api/handlers_settings.validate`).
DEFAULT_SYSTEM_PROMPT = (
    "Sei l'assistente principale per la gestione della smart home.\n"
    "Se in questa conversazione hai lo strumento `search` (trova per nome un'area,"
    " un'entità o un dispositivo; con `riferimento` dà il dettaglio di una cosa sola,"
    " col suo stato), usalo per scoprire cosa c'è in casa e per i valori precisi —"
    " temperature, stati correnti — invece di dedurli.\n"
    "Altrimenti rispondi con ciò che trovi nel contesto in fondo al prompt (la casa,"
    " ciò che le persone hanno detto, le sessioni precedenti): è uno snapshot di"
    " orientamento, non una lettura fatta adesso. Dichiara apertamente ciò che non c'è,"
    " invece di inventarlo."
)


# `giorni_conservazione` fa DUE lavori:
#   1. la potatura notturna (`ChatStore.prune`, dal lavoro delle 3) cancella
#      dal disco i messaggi piu' vecchi di questo numero di giorni;
#   2. lo STESSO numero limita quanto `chat_store.load_context()` rilegge
#      della conversazione in corso -- abbassarlo non libera spazio, fa
#      DIMENTICARE PRIMA.
# E `0` non cancella e non limita MAI niente: i due lettori di `chat_store`
# scrivono la stessa regola al contrario (`if days > 0` in `load_context`,
# `if days <= 0: return 0` in `ChatStore.prune`) -- il contrario
# di cio' che chiunque si aspetta da una "conservazione" messa a zero, e per
# questo va detto esplicitamente, non lasciato dedurre.
#
# Fino al 02/10/2026 un file senza la chiave la prendeva da
# `HISTORY_RETENTION_DAYS`, la variabile che `run.sh` esportava dall'opzione
# `history_retention_days`. L'opzione e' uscita dallo schema con la 3.0.0 e
# la variabile non arriva piu' da nessuno: un file senza la chiave vale il
# default, e l'avvio lo scrive (`file_lacks_retention_days`, qui sotto).


def file_lacks_retention_days(data_dir: str) -> bool:
    """`True` se `impostazioni_chat.json` non ha (ancora) la chiave
    `giorni_conservazione`, file assente o illeggibile compresi.

    Esiste perche' `load()` da' il default quando la chiave manca ma non lo
    SCRIVE, e `save()` ha un solo chiamante di produzione: la PUT della pagina
    «Impostazioni chat». Un utente che quella pagina non la apre mai non
    produrrebbe mai la chiave sul disco, e il file non direbbe quanto conserva.
    Nasce come meta' di una migrazione: fino alla 3.0.0 il valore arrivava da
    un'opzione dell'add-on, e chi aveva scelto **0** («non cancellare mai») se
    lo sarebbe ritrovato a 90 senza una scrittura all'avvio.

    Il chiamante e' `server._on_startup`, subito dopo `load()`."""
    path = os.path.join(data_dir, _SETTINGS_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return True
    return not isinstance(raw, dict) or "giorni_conservazione" not in raw


#: Quanti giorni di conversazione si conservano, finche' il proprietario non
#: ne sceglie un altro numero dalla pagina Impostazioni chat (0 = per sempre).
#: Una costante perche' lo leggono la dataclass qui sotto e i parametri di
#: `chat_store`, che fino alla Tappa 8 ricopiavano il 90 sei volte.
DEFAULT_RETENTION_DAYS = 90


@dataclass
class ChatSettings:
    """La configurazione dell'unica conversazione che HIRIS sa avere.

    Ogni campo ha il proprio default nel codice -- non serve un seed
    all'avvio, perche' un'istanza di questa classe e' gia' completa appena
    costruita, con `ChatSettings()` a zero argomenti."""
    name: str = "HIRIS"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    response_mode: str = "auto"
    thinking_budget: int = 0
    max_chat_turns: int = 0
    restrict_to_home: bool = False
    retention_days: int = DEFAULT_RETENTION_DAYS

    @classmethod
    def load(cls, data_dir: str) -> "ChatSettings":
        """Non restituisce mai `None`: un file assente, o che non e' JSON,
        produce i default di sopra (il secondo dichiarato nel log, non un
        pass muto) -- mai uno stato "impostazioni mancanti" che il chiamante
        dovrebbe scoprire da solo.

        File assente e file non-JSON convergono sullo stesso `raw = {}`: un
        solo percorso produce i default, non due.

        **Non solleva nemmeno su un file JSON valido ma di forma sbagliata**
        (S-19, Tappa 8): fino all'08/10/2026 una radice che non e' un oggetto
        dava `AttributeError` e un numero non convertibile `ValueError`, e
        l'avvio, che la chiama senza `try`, si fermava. Ora una radice storta
        vale i default, un numero storto il default del suo campo, e il log
        lo dice nominando il campo."""
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
        if not isinstance(raw, dict):
            logger.error(
                "Impostazioni chat in %s: la radice e' %s, non un oggetto: "
                "uso i default nel codice.", path, type(raw).__name__,
            )
            raw = {}
        default = cls()

        def number(key: str, value, fallback: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                logger.error(
                    "Impostazioni chat in %s: %s=%r non e' un numero: uso %r.",
                    path, key, value, fallback,
                )
                return fallback

        # NOTA il contrasto deliberato con `thinking_budget`/`max_chat_turns`
        # piu' sotto: quelli usano `raw.get(k, 0) or 0`, che trasforma
        # ANCHE un valore presente ma falsy (0) nel ripiego -- corretto per
        # loro perche' il ripiego E' 0. Per `giorni_conservazione` il ripiego
        # (90) e' diverso dal valore-sentinella (0 = "non cancellare mai"):
        # lo stesso pattern trasformerebbe silenziosamente uno 0 scelto
        # dall'utente nel default. Qui si distingue "chiave assente" (vale il
        # default) da "chiave presente" (vince sempre, 0 compreso) con un `in`
        # esplicito, non con la verita' del valore.
        if "giorni_conservazione" in raw:
            value = raw.get("giorni_conservazione")
            retention_days = (
                default.retention_days if value is None
                else number("giorni_conservazione", value, default.retention_days)
            )
        else:
            retention_days = default.retention_days
        return cls(
            name=raw.get("nome", default.name),
            system_prompt=raw.get("system_prompt") or default.system_prompt,
            response_mode=raw.get("response_mode", default.response_mode),
            thinking_budget=number("thinking_budget",
                                   raw.get("thinking_budget", 0) or 0,
                                   default.thinking_budget),
            max_chat_turns=number("max_chat_turns",
                                  raw.get("max_chat_turns", 0) or 0,
                                  default.max_chat_turns),
            restrict_to_home=bool(raw.get("restrict_to_home", default.restrict_to_home)),
            retention_days=retention_days,
        )

    def save(self, data_dir: str) -> None:
        """Scrittura atomica e durevole (`storage.write_json_atomic`).

        Un crash a meta' scrittura non deve mai lasciare un
        `impostazioni_chat.json` troncato che il prossimo avvio legge come
        JSON valido ma incompleto -- e queste sono le impostazioni con cui la
        chat riparte dopo un riavvio, cioe' l'unico stato che le sopravvive.

        Solleva `OSError` se il disco non collabora: il chiamante HTTP
        (`api/handlers_settings.handle_save_settings`) la cattura e
        risponde dichiarando il guasto, invece di rispondere "salvato".
        """
        write_json_atomic(os.path.join(data_dir, _SETTINGS_FILE), {
            "nome": self.name,
            "system_prompt": self.system_prompt,
            "response_mode": self.response_mode,
            "thinking_budget": self.thinking_budget,
            "max_chat_turns": self.max_chat_turns,
            "restrict_to_home": self.restrict_to_home,
            "giorni_conservazione": self.retention_days,
        })
