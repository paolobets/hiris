"""Gli strumenti della chat: il catalogo che il modello riceve
(`KNOWLEDGE_TOOLS`) e chi li esegue (`ToolDispatcher`).

    search   -- la porta che interroga la casa: trova, conta, elenca, filtra,
                e con `riferimento` da' il dettaglio di una cosa sola
    related  -- chi tocca questa cosa, secondo Home Assistant
    remember -- salva cio' che l'utente ha detto, con le ancore alla casa
    fetch    -- i ricordi che riguardano una parte della casa
    execute  -- chiama un servizio di Home Assistant, verificato prima e
                riletto dopo: tocca la casa SUBITO
    promise  -- mette da parte un `fai` (verificato subito) o un `chiedi`
                (con l'istantanea di partenza) per un istante futuro
    agenda   -- cosa e' ancora in sospeso, o com'e' andata
    cancel   -- annulla una promessa non ancora mantenuta
    propose  -- propone di creare, modificare o cancellare una
                configurazione: non scrive, restituisce un'anteprima con un
                `proposta_id`
    confirm  -- applica una proposta, in un turno diverso da quello che l'ha
                creata
    history  -- legge INDIETRO nel tempo: stati, valori, esecuzioni, errori
    calendar -- gli impegni dei calendari di questa casa

**Chi scrive, e per quale porta.** `execute` scrive sul canale dei SERVIZI,
per una sola strada: la porta (`action/actuator.py`), che verifica prima e
rilegge dopo. Non e' l'unica via allo stesso effetto: `promise` con specie
`fai` scrive lo stesso servizio dalla STESSA porta, solo piu' tardi -- lo
schedulatore (`keeper/`) lo chiama quando la promessa matura, senza un turno
del modello in quel momento. Cio' che si puo' verificare contro questa
installazione si verifica ALLA NASCITA della promessa, non al momento di
mantenerla: vedi `ToolDispatcher._promise`.

`propose` e `confirm`, in coppia, sono l'unica strada che scrive
CONFIGURAZIONE -- automazioni, script, scene. Sono due apposta: `propose`
compone e fa validare contro QUESTA casa (mai uno YAML scritto a mano),
`confirm` scrive -- e in mezzo deve starci un umano, riconosciuto dal TURNO e
non da un campo che il modello potrebbe compilare da solo. Vedi
`action/construction/workshop.py` per il giro intero e la guardia.

`history` passa per `home_space/house_history.py`; che cosa si chiede lo
dice `cosa`, un argomento esplicito. `calendar` legge ogni calendario
(`HAClient.calendars()`/`calendar_events()`) e compone gli impegni
(`home_space/appointments.py`) in un unico elenco ordinato; un calendario che
non riesce a leggere finisce in `non_letti`, perche' la leggibilita' si
verifica LEGGENDO, non dallo stato (un calendario rotto e uno senza impegni
tornano lo stesso elenco vuoto).

**Perche' `related` e' uno strumento e non un campo del dettaglio.**

1. **I legami sono MOMENTANEI.** Un'automazione nuova cambia i legami di una
   luce nell'istante in cui viene salvata. Quindi si CHIEDONO quando servono,
   e non si tengono da nessuna parte: ne' nell'anagrafe, ne' nel nucleo.
2. **Il dettaglio non chiama la rete** (`queries.view`). Per infilarci i
   legami servirebbe un giro WebSocket a ogni richiesta di dettaglio -- anche
   per un ricordo, che con Home Assistant non c'entra nulla.
3. **Sono due domande, non due campi dello stesso fatto.** Il dettaglio porta
   il CORPO (cosa fa quell'automazione); `related` porta i LEGAMI (chi nomina
   questa entita', calcolato da Home Assistant su tutto cio' che ha
   caricato).
4. **Il guasto avrebbe due padroni.** Il dettaglio promette `esiste`. Un
   legame non letto e' il guasto di un ALTRO canale: dentro il dettaglio
   diventerebbe una chiave d'errore accanto a un `esiste: true`, e il modello
   non saprebbe a quale delle due domande si riferisce. Separati, ciascuno
   dichiara il proprio -- e `related` dichiara il suo con un `errore`, mai
   con un elenco vuoto.

`remember` salva davvero (vedi `ToolDispatcher._remember`): un «preso nota»
senza una scrittura e' il difetto da cui questo modulo e' nato.

`ToolDispatcher` collega gli strumenti all'anagrafe (`home_space/reader.py`),
alla memoria (`memory/store.py`) e all'indice dei nomi (`memory/resolver.py`),
nella forma che il modello puo' chiamare.

`dispatch()` non solleva MAI: restituisce sempre un dizionario, e in caso di
guasto una chiave `errore` leggibile dal modello -- un'eccezione che risale
fino al runner gli spezzerebbe il turno.

**Ogni strumento e' una riga della tabella `TOOLS`** (in fondo al modulo,
Tappa 5): definizione, gestore, archivi, filo, permessi del soffitto e
maschera. Il catalogo (`KNOWLEDGE_TOOLS`) e cio' che `dispatch` controlla
prima del gestore si chiedono alla riga.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from ..action.construction.advisor import STRUCTURES
from ..action.construction.stakes import CHOSEN_BY_MODEL as STAKES_CHOSEN_BY_MODEL
from ..api.soffitto import ADMIN_READS_REFUSAL, ADMIN_SERVICES_REFUSAL, denies
from ..chat_thread import ChatThread, subject_key_for, without_thread
from ..memory.interpretation import VOCABULARY, validate
from ..memory.resolver import STORE_KEY_PER_TYPE
from ..memory.store import MemoryStore
from ..proxy._sanitize import sanitize_ha_value
from ..proxy.entity_cache import states_by_id
from . import historian
from .appointments import merge_calendars, readable_calendars
from .energy import energy_dashboard
from .ha_vocabulary import HA_LINK_TYPE
from .house import House
from .house_history import KINDS as HISTORY_KINDS
from .house_history import (
    LEVELS,
    WINDOW_MAX_HOURS,
    parse_query,
    read_errors,
    read_history,
)
from .house_query import (
    KINDS,
    ORDERS,
    ROWS_MAX,
    depth_for,
    parse_filters,
    query_house,
)
from .privacy import (
    ADMIN_ONLY_HISTORY_KINDS,
    HA_CORE_USER_SERVICES,
    cover_reserved_body,
)
from .queries import related as _readable_links
from .queries import sanitized_memories as _sanitized_memories
from .queries import view as _view_detail
from .reader import HomeSpace
from .redaction import home_assistant_seal
from .topology import Mirror, visibility
from .type_judgments import TypeJudgments
from .type_vocabulary import REPO_JUDGMENTS

# I tipi di ancora che la memoria conosce, DERIVATI da
# `memory/interpretation.VOCABULARY["ancore"]`, che a sua volta li chiede
# all'anagrafe (`resolver.STORE_KEY_PER_TYPE`): un'ancora vale solo se
# `Lookup.verify()` la sa verificare, quindi i due elenchi non «coincidono»
# -- sono lo stesso fatto, e dalla Tappa 3 (Task 9, B-51) si scrive una
# volta. Ordinati perche' un frozenset non promette un ordine stabile
# fra due letture, ed e' l'ordine in cui `fetch` cerca quando il modello non
# specifica un `tipo` -- vedi `_recall`.
_TETHER_TYPES = tuple(sorted(VOCABULARY["ancore"]))

# Il suggerimento per una ricerca per nome che non riconosce niente
# (`ToolDispatcher._declare_name_gaps`): «nessun nome combacia» non e' «questa
# cosa non esiste».
# **Un divieto, non piu' un consiglio** (24/09/2026). Questo testo diceva
# gia' «non e' detto che la cosa non esista», e il modello, interrogato a
# vuoto, lo ripeteva fedelmente. Ma quando aveva un COMPITO da portare a
# casa -- «accendi la luce della taverna» -- rispondeva «in Home Assistant
# non c'e' nessuna stanza ne' luce chiamata taverna», cioe' esattamente la
# frase che la vecchia ricerca per nome dichiarava di non voler mai dire.
# Misurato su tutte e due le strade, catena e ponte: non era il modello.
#
# Il resto era un consiglio inservibile: «riprova col nome esatto» lo si da'
# a chi il nome esatto ce l'ha, e chi cerca non ce l'ha mai. Al suo posto
# c'e' cio' che il modello puo' davvero fare adesso.
_NOTHING_RECOGNIZED_SUGGESTION = (
    "Nessun nome dichiarato in questa casa contiene questo testo, ne' per "
    "intero ne' come parola. **Non rispondere che la cosa non esiste: non "
    "lo sai.** «search» guarda i nomi, non l'inventario, e una cosa puo' "
    "esistere con un nome che non somiglia a quello che hai cercato. "
    "Prima di concludere: cerca la STANZA in cui la cosa dovrebbe stare e "
    "chiama «search» con il `riferimento` di quell'area per vedere cosa "
    "contiene davvero, o filtra per `area`; se conosci gia' il "
    "`riferimento` della cosa, chiedilo diretto."
)

#: I registri dell'anagrafe che la porta legge per rispondere: aree, entita' e
#: dispositivi (i nomi) e i PIANI, perche' `piano` e' un filtro della porta
#: (`house_query._place_matches`, `_area_rows`, `_device_rows`). Col registro
#: dei piani caduto `search(piano=...)` trova zero e deve dirlo (spec §2.4:
#: il silenzio si dichiara sempre). Le etichette no: la porta non le cerca.
_SEARCHED_STORES = frozenset(STORE_KEY_PER_TYPE.values()) | {"piani"}


def _fallen_stores_message(stores: list[str]) -> str:
    return (f"registri non letti all'ultima ricostruzione dell'anagrafe: "
            f"{', '.join(stores)}. Cio' che sta li' dentro non e' cercabile "
            "adesso, e potrebbe esistere lo stesso.")


logger = logging.getLogger(__name__)


# Tappa 5, Task 5 (06/10/2026; B-32, D-68): cio' che `search` e `history`
# hanno in comune si scrive una volta sola. Prima le stesse proprieta'
# stavano in due schemi con parole diverse («Includi le entita' nascoste. Di
# norma no.» / «Anche le entita' nascoste.»), e la regola della profondita'
# in due prose con le soglie scritte a mano («fino a 10», «da 2 a 10»),
# mentre la soglia vera e' una e la applica `house_query.depth_for` per
# entrambe. Le differenze vere restano in chiaro accanto a
# ciascuno schema: `riferimento` (un ricordo ha un numero, la storia no) e
# `integrazione` (per gli errori e' chi ha scritto la voce).
_SUBJECT_FILTERS = {
    "nome": {
        "type": "string",
        "description": ("Un nome, un alias o un pezzo di nome, confrontato anche "
                        "per radice («rifiuti» trova «rifiuto»)."),
    },
    "tipo": {
        "type": "string",
        "description": "Il dominio di Home Assistant: light, sensor, switch, automation...",
    },
    "classe": {
        "type": "string",
        "description": "La classe del dispositivo: battery, motion, temperature, energy...",
    },
    "area": {
        "type": "string",
        "description": "Il nome o l'id dell'area; «senza area» per cio' che non ne ha.",
    },
    "piano": {"type": "string", "description": "Il nome del piano."},
    "integrazione": {
        "type": "string",
        "description": "La piattaforma: tuya, reolink, zha...",
    },
    "includi_nascoste": {
        "type": "boolean",
        "description": "Anche le entita' nascoste, che di norma restano fuori.",
    },
    "includi_servizio": {
        "type": "boolean",
        "description": ("Anche le entita' di servizio (diagnostica, "
                        "configurazione), che di norma restano fuori."),
    },
    "limite": {
        "type": "integer", "minimum": 0, "maximum": ROWS_MAX,
        "description": f"Quante voci al massimo (predefinito e tetto {ROWS_MAX}); "
                       "0 da' solo i conti.",
    },
    "salta": {
        "type": "integer", "minimum": 0,
        "description": "Quante voci saltare: il `salta` di `oltre`, la pagina dopo.",
    },
}


def _depth_rule(complete: str, medium: str, short: str) -> str:
    """La regola della profondita' detta al modello, una volta per tutte e due
    le porte (D-68). La soglia si CHIEDE a `depth_for`, che la applica (B-30:
    la costante la legge lei sola): il testo non puo' dire 10 mentre la
    regola fa 12."""
    medium_max = max(n for n in range(2, ROWS_MAX + 1) if depth_for(n) == "media")
    return (f"**La profondita' la decido io**, da quante voci trovo: una -> "
            f"`completa` ({complete}); fino a {medium_max} -> `media` "
            f"({medium}); oltre -> `corta` ({short}). ")


# Come si leggono i conti e le pagine: la busta delle due porte e' una
# (`house_query.envelope`, `page_rows`), e la frase che la spiega pure.
_COUNT_RULE = (
    "`trovate` conta cio' che corrisponde, `escluse` cio' che NON ti ho dato "
    "(nascoste, servizio, disabilitate). **Un numero senza le escluse non e' "
    "un totale**: se dai un conteggio e `escluse` non e' vuoto, di' anche "
    "quelle (la `nota` ha il totale); se la domanda riguarda proprio quelle, "
    "richiama con `includi_nascoste` -- «nessuna luce accesa» e' falso se le "
    "accese sono nascoste. Con `oltre` ne restano: **prima restringi** con un "
    "filtro, scorri col suo `salta` solo se ti servono tutte (ogni pagina e' "
    "un giro); `salta_oltre_la_fine` vuol dire che hai saltato oltre "
    "l'ultima, e le voci ci sono. "
)


SEARCH_TOOL_DEF = {
    "name": "search",
    # La porta che interroga la casa (spec `2026-09-29-una-porta-sola-per-la-
    # casa.md` §2): dal 29/09/2026 fa anche il mestiere del dettaglio, che era
    # di un secondo strumento. Dal 06/10/2026 (Tappa 5, Task 5) la descrizione
    # non ripete cio' che dice lo schema: dice dove vale ogni filtro, la
    # profondita', cosa leggere SEMPRE nella risposta e cosa non esce.
    "description": (
        "La porta che interroga la casa: per TROVARE, CONTARE, ELENCARE e "
        "FILTRARE le cose di casa, e per il DETTAGLIO di una cosa sola (con "
        "`riferimento`, l'id esatto). Tutti i filtri sono facoltativi e si "
        "combinano; senza nessuno elenca le entita', `nome` da solo cerca in "
        "tutti i generi.\n"
        "Dove valgono: per le aree solo `nome` e `piano`; per i dispositivi "
        "`nome`, `area`, `piano`, `integrazione`; `classe`, `sopra` e `sotto` "
        "solo per le entita'; `in_esecuzione` solo per automazioni e script, e "
        "per loro `stato` dice se sono abilitate e `fermo_da_ore`/`cambiato_da_ore` "
        "contano l'ultima esecuzione. Un filtro che non vale per il genere "
        "chiesto torna un `errore`, mai un insieme intero.\n"
        + _depth_rule(
            "il dettaglio intero: stato, attributi, `comandi`, il corpo di "
            "un'automazione o di uno script, le entita' di un'area -- al "
            f"massimo {ROWS_MAX}, il resto nel suo `oltre`",
            "attributi e ultimo cambio",
            f"una riga per voce, al massimo {ROWS_MAX}")
        + "\n" + _COUNT_RULE + "\n"
        "Guarda `tipo` e l'id prima di concludere: «luci» puo' essere un "
        "`sensor` che le CONTA invece che una luce. Se piu' voci hanno lo "
        "stesso nome (due «Bagno» su piani diversi) scegli guardando la "
        "conversazione o chiedi a chi ti sta parlando: non prendere la prima.\n"
        "Una voce con `nascosta: true` esiste: la persona l'ha tolta dalle "
        "proprie viste in Home Assistant, non cancellata. Non proporla di tua "
        "iniziativa; se la domanda la riguarda, usala e dillo.\n"
        "Le posizioni di persone e dispositivi che si spostano non escono: di "
        "una persona sai solo se e' in casa (`home`) o fuori (`not_home`). "
        "Credenziali e indirizzi di rete non escono mai.\n"
        "Una ricerca per `nome` senza nessuna voce porta `nulla_riconosciuto`: "
        "nessun nome combacia, MAI «la cosa non esiste» -- segui il "
        "`suggerimento`. `non_ho_potuto_guardare` dice cosa non si e' potuto "
        "leggere; `stato_non_letto`, che gli stati non si sono potuti "
        "leggere. Per sapere CHI tocca una cosa usa `related`."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            **_SUBJECT_FILTERS,
            "genere": {
                "type": "string",
                "enum": list(KINDS),
                "description": "Che cosa cercare; di norma entita.",
            },
            "riferimento": {
                "type": ["string", "integer"],
                "description": (
                    "L'id esatto (di entita', area, dispositivo, automazione "
                    "o script), il numero di un ricordo o il dominio di "
                    "un'integrazione: da' il dettaglio completo; se non esiste, "
                    "una voce `esiste: false` col `suggerimento`."
                ),
            },
            "stato": {
                "type": "string",
                "description": "Lo stato: on, off, unavailable, unknown, home...",
            },
            "fermo_da_ore": {
                "type": "number", "minimum": 0,
                "description": "Fermo da almeno N ore.",
            },
            "cambiato_da_ore": {
                "type": "number", "minimum": 0,
                "description": "Cambiato nelle ultime N ore.",
            },
            "sopra": {"type": "number", "description": "Stato numerico maggiore di."},
            "sotto": {"type": "number", "description": "Stato numerico minore di."},
            "in_esecuzione": {
                "type": "boolean",
                "description": "Solo automazioni e script in corsa (o ferme).",
            },
            "ordina": {
                "type": "string",
                "enum": list(ORDERS),
                "description": "L'ordine delle voci; di norma per nome.",
            },
        },
    },
}

# I tipi che `related` accetta, nel vocabolario di HIRIS. DERIVATI dalla
# tabella di `queries.py` -- che e' anche quella con cui si traduce verso
# Home Assistant -- invece di riscritti qui: un elenco a mano nella
# descrizione e un altro nel gestore sarebbero due vocabolari, e il primo a
# divergere sarebbe quello che legge il modello.
_OUR_LINK_TYPES = tuple(sorted(HA_LINK_TYPE))

RELATED_TOOL_DEF = {
    "name": "related",
    "description": (
        "CHI tocca una cosa della casa, secondo Home Assistant: quali "
        "automazioni, script, scene, gruppi o persone la nominano, e dove quella "
        "cosa sta (area, dispositivo, piano, integrazione). Serve per due domande "
        "che senza questo strumento non hanno risposta: «perche' si e' accesa la "
        "luce del corridoio?» e -- prima di proporre di cancellare o cambiare "
        "qualcosa -- «se tolgo questa, cosa smette di funzionare?». "
        "Richiede `tipo` (uno fra: " + ", ".join(_OUR_LINK_TYPES) + ") e "
        "`riferimento`, l'identificatore ESATTO (usa `search` se hai solo un nome). "
        "Lo calcola Home Assistant su TUTTO cio' che ha caricato, ovunque sia "
        "scritto -- pacchetti, `!include`, cartelle, scene, gruppi -- mentre "
        "`search` con `riferimento` legge due soli file: qui i legami sono "
        "completi, ma non c'e' il CORPO. Le due cose non si sostituiscono: per "
        "sapere COSA FA un'automazione che trovi qui, aprila con `search` e il "
        "suo `riferimento`. "
        "**Come si legge la risposta.** `related` e' un dizionario tipo -> "
        "identificatori. Per un'entita' mescola chi la USA (automazione, script, "
        "scena, gruppo, persona) con dove STA (area, dispositivo, piano, "
        "integrazione, etichetta): se la domanda e' «cosa smette di funzionare», "
        "guarda i primi -- un'area non smette di funzionare perche' le togli una "
        "luce. Per un'area, invece, le entita' elencate sono cio' che l'area "
        "CONTIENE. I tipi usano gli stessi nomi di `search`, quindi un "
        "riferimento letto qui si passa a `search` cosi' com'e' -- ma il "
        "dettaglio si apre solo per area, entita, dispositivo, automazione e "
        "script: sugli altri "
        "risponde `non_so_guardare`, che significa «non lo so aprire», MAI «non "
        "esiste». "
        "Un `related` vuoto significa che Home Assistant non conosce nessun legame "
        "per questa cosa. Se invece non ha potuto rispondere ricevi `errore`, che "
        "non e' la stessa cosa: NON concludere che non la tocca nessuno."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "description": "Che cosa e' la cosa di cui vuoi i legami: uno fra "
                               + ", ".join(_OUR_LINK_TYPES) + ".",
            },
            "riferimento": {
                "type": "string",
                "description": (
                    "L'identificatore esatto della cosa, cosi' come lo conosce "
                    "Home Assistant (l'entity_id, l'id dell'area, del "
                    "dispositivo, dell'automazione...). Non un nome libero."
                ),
            },
        },
        "required": ["tipo", "riferimento"],
    },
}

# Niente `detto_da` nello schema (fetta "le chat divise", Task 6, decisione 5):
# l'autore non e' piu' un'ipotesi che il modello compila -- `_remember` lo
# deriva dal SOGGETTO del turno (`self._subject`). Fix round 1: un modello
# che lo manda comunque non viene "ignorato" -- lo schema non lo conosce
# piu', quindi il cancello sugli argomenti sconosciuti (`_bad_arguments`,
# in `dispatch()`) RIFIUTA l'intera chiamata prima che `_remember` la veda.
REMEMBER_TOOL_DEF = {
    "name": "remember",
    "description": (
        "Salva qualcosa che una persona ha detto sulla casa -- una preferenza, "
        "un divieto, un fatto, una regola -- cosi' che HIRIS se ne ricordi "
        "davvero nelle conversazioni future, invece di dire 'preso nota' e "
        "dimenticarlo. `testo` si salva sempre, per intero e senza riscriverlo: "
        "e' l'unica cosa qui dentro che e' la verita', tutto il resto e' "
        "un'interpretazione facoltativa che puoi anche omettere del tutto (una "
        "frase come «mi piace il caffe'» non ha ne' forza ne' ancore, e non e' "
        "un errore). Puoi aggiungere `forza` (preferenza, divieto, fatto o "
        "regola), un valore o intervallo (`grandezza` + `minimo`/`massimo`, es. "
        "una temperatura), `condizioni` (ora, giorno, presenza, sole, meteo, "
        "stagione) e `ancore` -- a quali aree, entita' o dispositivi si "
        "riferisce, nominando il loro identificatore esatto (usa `search` per "
        "trovarlo, non inventarlo). Un'ancora che non esiste davvero nella casa "
        "NON viene scritta -- ma il ricordo si salva comunque, per intero: la "
        "risposta lo dichiara in `problemi`, cosi' sai cosa e' stato scartato e "
        "perche'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "testo": {
                "type": "string",
                "description": (
                    "La frase cosi' come l'ha detta la persona -- "
                    "non riassunta, non riscritta."
                ),
            },
            "forza": {
                "type": "string",
                "description": (
                    "Una di: preferenza, divieto, fatto, regola. "
                    "Ometti se non e' chiaro."
                ),
            },
            "grandezza": {
                "type": "string",
                "description": (
                    "La grandezza a cui si riferisce un valore o intervallo, nel "
                    "linguaggio di Home Assistant (es. 'temperature', "
                    "'humidity'). Ometti se il ricordo non parla di un valore misurabile."
                ),
            },
            "minimo": {
                "type": "number",
                "description": "Il valore, o l'estremo minimo di un intervallo.",
            },
            "massimo": {
                "type": "number",
                "description": "L'estremo massimo di un intervallo, se ce n'e' uno.",
            },
            "condizioni": {
                "type": "array",
                "description": "Quando vale questo ricordo. Ometti se vale sempre.",
                "items": {
                    "type": "object",
                    "properties": {
                        "tipo": {
                            "type": "string",
                            "description": "ora, giorno, presenza, sole, meteo o stagione.",
                        },
                        "valore": {
                            "type": "string",
                            "description": (
                                "Il valore di quella condizione, "
                                "nel linguaggio di Home Assistant."
                            ),
                        },
                    },
                    "required": ["tipo", "valore"],
                },
            },
            "ancore": {
                "type": "array",
                "description": (
                    "A quali parti della casa si riferisce questo ricordo. Ometti "
                    "se non si riferisce a nessuna parte precisa (es. 'mi piace il caffe''')."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "tipo": {"type": "string", "description": "area, entita o dispositivo."},
                        "riferimento": {
                            "type": "string",
                            "description": (
                                "L'identificatore esatto (usa `search` per trovarlo, "
                                "non inventarlo)."
                            ),
                        },
                        "nome_visto": {
                            "type": "string",
                            "description": (
                                "Il nome con cui la persona l'ha nominata nella frase, "
                                "se diverso."
                            ),
                        },
                    },
                    "required": ["tipo", "riferimento"],
                },
            },
        },
        "required": ["testo"],
    },
}

FETCH_TOOL_DEF = {
    "name": "fetch",
    "description": (
        "I ricordi gia' salvati che riguardano una parte della casa -- un'area, "
        "un'entita' o un dispositivo -- dato il suo identificatore esatto "
        "(`riferimento`; usa `search` per trovarlo se hai solo un nome). Serve a "
        "rispondere a domande come 'cosa mi hai gia' detto sulla cucina?' senza "
        "dover rileggere ogni ricordo uno per uno. Se `tipo` non e' specificato, "
        "cerca fra tutti e tre i tipi di ancora (area, entita', dispositivo); "
        "specificalo solo se lo sai gia' con certezza. Se nessun ricordo e' "
        "ancorato a quel riferimento, `ricordi` e' una lista vuota: non "
        "significa che la casa non ha ricordi, significa solo che nessuno di "
        "quelli salvati nomina proprio questa parte -- prova `fetch` senza "
        "ancore su una parte piu' ampia, o chiedi a chi ti sta parlando."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "riferimento": {
                "type": "string",
                "description": "L'identificatore esatto di un'area, entita' o dispositivo.",
            },
            "tipo": {
                "type": "string",
                "description": "area, entita o dispositivo -- ometti per cercare su tutti e tre.",
            },
        },
        "required": ["riferimento"],
    },
}

EXECUTE_TOOL_DEF = {
    "name": "execute",
    "description": (
        "Chiama un servizio di Home Assistant per far succedere qualcosa nella "
        "casa: accendere, spegnere, impostare. Richiede `servizio` nella forma "
        "«dominio.servizio» (per esempio «light.turn_off») e un `bersaglio`. "
        "Il bersaglio si scrive in due modi, e il secondo e' quello giusto per "
        "«tutto in cucina»: `entita` con gli id ESATTI, oppure `aree`, `piani`, "
        "`etichette` o `dispositivi` con i loro id -- e in quel caso e' Home "
        "Assistant a dire cosa contengono. NON risolvere un'area a mano con "
        "`search` per poi elencarne le entita': se te ne sfugge una tocchi quasi "
        "tutto e credi di aver toccato tutto. Puoi combinarli. "
        "`dati` porta i parametri del servizio, se ne servono. "
        "La chiamata viene VERIFICATA contro questa installazione prima di "
        "partire: se il servizio non esiste, se l'entita' non esiste, se l'area "
        "o l'etichetta che hai nominato non esistono, o se un "
        "parametro non appartiene a quel servizio, ricevi un errore che dice "
        "cosa esiste davvero -- usalo per correggerti invece di riprovare "
        "uguale. La verifica arriva fino alle CAPACITA' di quell'entita': un "
        "parametro che il servizio ha ma che Home Assistant non offre a "
        "questa entita' (il colore su una luce che fa solo acceso/spento, la "
        "transizione su una che non la sa fare) viene rifiutato qui, con la "
        "ragione detta. Per non arrivarci, guarda l'entita' con `search` e il suo "
        "`riferimento`: sotto `comandi` c'e' cosa accetta davvero, coi limiti "
        "veri del dispositivo. "
        "Con un bersaglio risolto l'esito porta anche `bersaglio`, che "
        "dice cosa conteneva (`risolte`), su cosa la chiamata e' partita "
        "(`toccate`) e cosa e' rimasto fuori perche' di un altro dominio o "
        "senza stato: se `toccate` e' piu' corto di `risolte`, dillo a chi ti sta parlando "
        "invece di dichiarare che hai fatto tutto. "
        "Dopo l'esecuzione lo stato viene RILETTO: `prima`, `dopo` e "
        "`cambiato` dicono cosa e' successo per davvero. Se `cambiato` e' vuoto "
        "arriva un `avviso`: la chiamata e' riuscita ma nulla e' cambiato, e "
        "va detto a chi ti sta parlando invece di dichiarare un successo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "servizio": {
                "type": "string",
                "description": "«dominio.servizio», per esempio «light.turn_off».",
            },
            "bersaglio": {
                "type": "object",
                "description": (
                    "Cosa toccare. Almeno una fra `entita`, `aree`, `piani`, "
                    "`etichette` e `dispositivi`; si possono combinare."
                ),
                "properties": {
                    "entita": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Gli id esatti delle entita' da toccare.",
                    },
                    "aree": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Gli id delle aree: il servizio tocca cio' che Home "
                            "Assistant dice esserci dentro, e a cui si applica."
                        ),
                    },
                    "piani": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Gli id dei piani, con tutte le loro aree.",
                    },
                    "etichette": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Gli id delle etichette (`label_id`): tutto cio' che le "
                            "porta, entita', dispositivi o aree. Si danno per id, "
                            "cosi' come li conosce Home Assistant: nessuno "
                            "strumento trasforma il NOME di un'etichetta nel suo "
                            "id, quindi non indovinarlo e non ricavarlo dal nome, "
                            "sono slug che nessuno scrive a memoria."
                        ),
                    },
                    "dispositivi": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Gli id dei dispositivi, con le loro entita'."
                        ),
                    },
                },
            },
            "dati": {
                "type": "object",
                "description": (
                    "I parametri del servizio, se ne servono (per esempio "
                    "`brightness_pct`). Solo i parametri veri di quel servizio: "
                    "uno inventato fa rifiutare la chiamata."
                ),
            },
        },
        "required": ["servizio", "bersaglio"],
    },
}

PROMISE_TOOL_DEF = {
    "name": "promise",
    "description": (
        "Metti da parte qualcosa da fare, o da guardare, PIU' TARDI: «alle 17 "
        "accendi lo studio», «fra un'ora verifica la temperatura e se e' "
        "aumentata avvisami», «fra due ore dimmi se posso aprire le finestre». "
        "Due specie. `fai`: un'azione, e vuole `chiamata` nella stessa forma di "
        "«execute» -- viene VERIFICATA adesso contro questa installazione, quindi "
        "un servizio o un'entita' che non esistono te li dico subito, non fra due "
        "ore. `chiedi`: a quell'ora guardi tu e rispondi, e vuole `domanda`; se la "
        "richiesta e' un CONFRONTO («se e' aumentata») elenca in `da_confrontare` "
        "le entita' da misurare ADESSO, o piu' tardi non avrai con cosa "
        "confrontare. `quando` e' un istante ISO-8601 col fuso: risolvilo tu da "
        "«fra un'ora» o «alle 17», e riporta in `quando_detto` le parole della "
        "persona. Un istante gia' passato viene rifiutato. La promessa e' di chi "
        "te la chiede: l'esito torna a lei, e come avvisarla lo decide HIRIS, "
        "non tu -- se non c'e' un modo, il risultato te lo dice e tu glielo "
        "riferisci. Quando ne prendi una dillo alla persona, e dille che la "
        "ritrova nella pagina «Impegni». "
        "NON usare questo strumento per qualcosa che si ripete ogni giorno: "
        "quella e' un'automazione di Home Assistant, dillo alla persona."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "specie": {"type": "string", "description": "«fai» oppure «chiedi»."},
            "frase": {
                "type": "string",
                "description": "La frase della persona, cosi' come l'ha detta -- non riassunta.",
            },
            "quando": {
                "type": "string",
                "description": "L'istante in ISO-8601 col fuso, es. «2026-08-19T17:00:00+02:00».",
            },
            "quando_detto": {
                "type": "string",
                "description": "Come l'ha detto la persona: «fra un'ora», «alle 17».",
            },
            "chiamata": {
                "type": "object",
                "description": (
                    "Solo per «fai»: `servizio`, `bersaglio` e `dati`, "
                    "come in «execute»."
                ),
            },
            "domanda": {
                "type": "string",
                "description": "Solo per «chiedi»: cosa devi guardare e a cosa devi rispondere.",
            },
            "da_confrontare": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Solo per «chiedi»: gli id delle entita' il cui valore va "
                    "misurato ADESSO, per poterlo confrontare piu' tardi."
                ),
            },
        },
        "required": ["specie", "frase", "quando"],
    },
}

# Le promesse sono di chi le chiede (spec 2026-09-26 §2): un turno che nessuno
# ha aperto -- un job del ponte di prima di questa versione, un percorso
# interno -- non ha un filo, e una promessa nata li' non avrebbe a chi tornare.
# Si rifiuta e lo si dice, per `promise`, `agenda` e `cancel` insieme.
_NO_THREAD_REFUSAL = ("le promesse sono di chi le chiede, e questo turno non "
                      "l'ha aperto nessuno: non posso prenderne, elencarle o "
                      "disdirle da qui.")

# La riga che precede il motivo di `Recipients.reason` nel risultato di un
# `chiedi` senza strada (spec §2, «Nascita»): l'esito arrivera' comunque in
# chat, e' la notifica che manca.
_NO_RECIPIENT_NOTICE = "te lo dico qui in chat, senza notifica: "

AGENDA_TOOL_DEF = {
    "name": "agenda",
    "description": (
        "Cosa HIRIS ha promesso: cio' che e' ancora in sospeso e, se chiedi lo "
        "storico, com'e' andata -- mantenuta, saltata (col ritardo misurato), "
        "disdetta o fallita col motivo. Usalo quando la persona chiede «cosa hai "
        "in programma?», «l'hai fatto?», o prima di disdire qualcosa, per avere "
        "l'identificatore giusto invece di indovinarlo. "
        "**Non e' il calendario della persona.** Questi sono impegni DI HIRIS "
        "con se stesso -- azioni o domande che ha preso in carico lui stesso, "
        "verificate contro questa casa quando sono nate. Per gli appuntamenti che una "
        "persona ha scritto su un calendario di Home Assistant («cosa ho in "
        "programma questa settimana?», nel senso comune della parola) usa "
        "«calendar», non questo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tutte": {
                "type": "boolean",
                "description": (
                    "Vero per vedere anche quelle gia' concluse. "
                    "Ometti per le sole in sospeso."
                ),
            },
        },
    },
}

CANCEL_TOOL_DEF = {
    "name": "cancel",
    "description": (
        "Annulla una promessa che non e' ancora stata mantenuta. Serve il suo "
        "`id`: prendilo da «agenda», non inventarlo. Una promessa gia' "
        "mantenuta, saltata o disdetta non si annulla -- te lo dico invece di "
        "fingere di averlo fatto."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "L'identificatore della promessa."}},
        "required": ["id"],
    },
}

PROPOSE_TOOL_DEF = {
    "name": "propose",
    "description": (
        "PROPONE di creare, modificare o cancellare un'automazione, uno script "
        "o una scena in Home Assistant. **Non scrive niente**: compone, fa "
        "validare la configurazione a QUESTA casa e restituisce un'anteprima "
        "con un `proposta_id`. Per farla diventare vera serve `confirm`, e "
        "**non nello stesso turno**: mostra l'anteprima a chi ti sta parlando, digli che "
        "la proposta resta in attesa nella pagina «Proposte», e aspetta che sia "
        "chi ti sta parlando a dire di procedere. "
        "Per modificare o cancellare serve `chiave` (l'id "
        "dell'automazione o della scena, lo slug dello script): la trovi con "
        "`search` (col suo `riferimento` se lo hai gia'). "
        "Componi con i PARAMETRI, non scrivendo YAML: `innesco`, `condizioni`, "
        "`azioni` per un'automazione; `azioni` per uno script; `stati` per una "
        "scena. Usa lo schema moderno di Home Assistant (`trigger:`, `action:` "
        "dentro le voci). Se la validazione fallisce ricevi il motivo VERO di "
        "Home Assistant: correggiti su quello. "
        "Se servono helper che non esistono, elencali in `helper`: nascono "
        "insieme all'oggetto, e se l'oggetto viene rifiutato vengono disfatti. "
        "Se quello che chiedi ha la forma sbagliata -- un'automazione per una "
        "cosa che e' uno script -- l'anteprima te lo dice: riferiscilo "
        "a chi ti sta parlando invece di ignorarlo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "gesto": {"type": "string",
                      "description": "crea, modifica o cancella."},
            "dominio": {"type": "string",
                        "description": "automation, script o scene."},
            "chiave": {"type": "string",
                       "description": "Solo per modifica e cancella."},
            "alias": {"type": "string", "description": "Il nome dell'oggetto."},
            "descrizione": {"type": "string",
                            "description": "A cosa serve, in italiano: finisce "
                                           "dentro l'oggetto e la legge chi lo "
                                           "aprira' in Home Assistant."},
            "innesco": {"type": "array", "items": {"type": "object"},
                        "description": "I trigger dell'automazione."},
            "condizioni": {"type": "array", "items": {"type": "object"},
                           "description": "Le condizioni dell'automazione."},
            "azioni": {"type": "array", "items": {"type": "object"},
                       "description": "Le azioni dell'automazione o i passi dello script."},
            "stati": {"type": "array", "items": {"type": "object"},
                      "description": "Per una scena: gli stati da ristabilire, "
                                     "ognuno con `entity_id`."},
            "campi": {"type": "object",
                      "description": "Per uno script parametrico: i `fields`."},
            "parametri": {"type": "array", "items": {"type": "string"},
                          "description": "I nomi dei parametri in ingresso, se ce ne sono."},
            "riuso": {"type": "boolean",
                      "description": "true se la sequenza serve anche altrove."},
            "ricorrente": {"type": "boolean",
                           "description": "true se e' una cosa che si ripete "
                                          "(«ogni giorno alle 7»)."},
            # Vocabolario CHIUSO, e l'enumerazione viene dalla sua unica casa
            # (`action/construction/advisor.STRUCTURES`). Questo campo dice
            # QUALE delle tre strutture l'utente ha chiesto; cosa ha DETTO va
            # in «frase». Finche' la descrizione diceva «cosa ha chiesto
            # l'utente» il modello ci scriveva dentro la richiesta per esteso,
            # e il consigliere dissentiva da se stesso -- misurato sulla casa
            # vera (audit delle fondamenta, rilievo 5).
            "richiesto": {"type": "string", "enum": list(STRUCTURES),
                          "description": "Solo se chi ti sta parlando ha nominato, di "
                                         "sua iniziativa, una delle tre strutture, con "
                                         "quella parola. Serve a dirti se non sono "
                                         "d'accordo. La sua frase va in «frase», "
                                         "non qui: se non ha nominato nessuna "
                                         "struttura, ometti questo campo."},
            "helper": {"type": "array", "items": {"type": "object"},
                       "description": "Gli helper da creare insieme: ognuno con "
                                      "`dominio` e `dati`."},
            # Il livello (attori, strato 4, D13): l'enumerazione viene dalla
            # sua casa (`action/construction/stakes.py`) e porta solo cio' che
            # il modello puo' scegliere. «alto» non c'e': lo impone l'officina
            # (`stakes.impose`). La descrizione non ricopia QUANDO: fino al
            # 07/10/2026 diceva «su serrature e allarme», e la regola nuova
            # sui servizi scritti come modello l'aveva gia' resa incompleta
            # (revisione, giro 73). Piu' corta, e non invecchia.
            "livello": {"type": "string", "enum": list(STAKES_CHOSEN_BY_MODEL),
                        "description": "«alto» lo impone il codice, non tu."},
            "frase": {"type": "string",
                      "description": "La frase di chi ti sta parlando da cui nasce, "
                                     "verbatim."},
        },
        "required": ["gesto", "dominio"],
    },
}

CONFIRM_TOOL_DEF = {
    "name": "confirm",
    "description": (
        "Applica una proposta creata da `propose`: da qui in poi la cosa "
        "esiste davvero in Home Assistant. "
        "**Chiamalo SOLO dopo che chi ti sta parlando ha detto di procedere**, in un "
        "turno successivo a quello in cui hai mostrato l'anteprima: se lo chiami nello "
        "stesso turno viene rifiutato, ed e' voluto -- il suo si' non e' "
        "una cosa che puoi dare per scontata. "
        "L'esito dice cosa e' nato davvero (`entita`) e, se qualcosa non torna, "
        "un `avviso`: riferiscilo invece di dichiarare un successo pieno. "
        "**Il `proposta_id` puoi ometterlo**: senza, applico l'unica proposta "
        "in sospeso nata in un turno precedente. Se ce ne fosse piu' d'una te "
        "le elenco invece di sceglierne una."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            # **Dichiarato ma NON obbligatorio** (23/09/2026). Finche' era
            # `required`, il modello che non aveva l'id non poteva chiamare
            # `confirm` affatto -- e l'id non ce l'ha mai, perche' nasce in un
            # risultato di strumento e la cronologia della chat porta solo
            # testo. Misurato sulla casa vera: riproponeva, la proposta nasceva
            # nel turno della conferma, il cancello la rifiutava, e ogni
            # costruzione costava tre turni invece di due.
            #
            # Resta dichiarato perche' chi l'id ce l'ha -- la pagina, e il
            # modello quando l'utente lo nomina -- deve poterlo passare: e'
            # l'unico modo di essere precisi quando ce n'e' piu' d'una.
            "proposta_id": {"type": "string",
                            "description": "L'identificatore restituito da "
                                           "`propose`. Facoltativo: senza, "
                                           "applico l'unica in sospeso."},
        },
    },
}

# `history` (fetta «la storia», spec `docs/design/2026-09-30-la-storia.md`,
# 30/09/2026) sostituisce `trend`, `logbook`, `system_log` e
# `automation_trace`: quattro forme di domanda e di risposta, 7.449 caratteri
# di definizioni su 34.842 del catalogo (21%), rispediti a ogni giro sulla
# catena. Le prudenze delle quattro descrizioni restano, accorciate (§3):
# «per mano di HIRIS» e' probabile; una traccia che manca non e' «andata
# bene»; `count: 12` e' una causa sola; una fascia oraria non e' una misura
# puntuale; il registro arriva sigillato.
#
# Giro del Task 7 (ruling del controllore, 30/09/2026): i Task 3-5 hanno
# dato alla risposta chiavi che la prima stesura di questa descrizione non
# nominava -- `salta` che scorre voci diverse secondo la profondita', `oltre`
# che dice anche «oltre la fine», `nota` col totale delle escluse, `conti`,
# `ore_senza_valore`, `consumato_non_calcolato`, `non_lette_in_tutto`, `dal`,
# `al` (la coda delle fasce orarie, revisione finale della fetta).
# Una chiave che il modello non sa leggere e' una chiave che non esiste. Il
# testo resta sotto i tre quarti delle quattro descrizioni uscite
# (`tests/test_history_tool.py` lo misura). Al modello lo strumento si
# chiama `history`, mai «storia».
HISTORY_TOOL_DEF = {
    "name": "history",
    # Tappa 5, Task 5 (06/10/2026): il parametro che sceglie la domanda si
    # chiama `cosa`, non piu' `genere` (D3, C-65): `genere` in `search` e' il
    # genere di un oggetto, qui era tutt'altro. I filtri comuni, la
    # profondita' e la lettura dei conti vengono da `_SUBJECT_FILTERS`,
    # `_depth_rule` e `_COUNT_RULE`, come per `search`.
    "description": (
        "Cio' che e' successo in casa nel tempo: come sono cambiati gli stati, "
        "come sono andati i valori, come sono andate automazioni e script, "
        "cosa c'e' nel registro degli errori di Home Assistant. Una chiamata "
        "sola, anche per piu' cose insieme: DI CHI con gli stessi filtri di "
        "`search`, QUANDO con `ore` oppure con `da`/`a` -- non tutti e due. "
        "`cosa`: `stati` (predefinito) i cambi di stato; `valori` i numeri "
        "nel tempo; `esecuzioni` le partenze di automazioni e script; `errori` "
        "il registro, che accetta solo `integrazione` e `livello`. Un filtro "
        "che non vale per `cosa` torna `errore`, non viene ignorato. "
        + _depth_rule(
            "ogni cambio; la serie; le esecuzioni conservate, e con "
            "`esecuzione` = il `run_id` di una riga la traccia passo per passo",
            "ogni cambio con l'id; una riga per serie; le ultime 3 esecuzioni "
            "di ognuna",
            "una riga per soggetto")
        + f"Al massimo {ROWS_MAX} `voci`: `salta` scorre le righe nella "
        "completa e nella media, i soggetti nella corta. "
        + _COUNT_RULE +
        "`finestra` e' il periodo DAVVERO coperto: con `chiesta_da` e "
        "`troncata` mancano i dati piu' vecchi -- dillo. `dal` su una riga: "
        "quella serie, o le esecuzioni conservate, cominciano dopo l'inizio; "
        "`al`: le sue fasce finiscono li', l'ora in corso non e' ancora "
        "compilata. "
        "`nessuna_registrazione` non vuol dire «non e' mai cambiato». Un "
        "`errore` vuol dire che Home Assistant non ha risposto: non concludere "
        "niente sulla casa. "
        "Valori: primo, ultimo, minimo, massimo, media e consumato sono "
        "`conti` fatti da me sulla finestra, non misure di Home Assistant. "
        "`ore_senza_valore` sono le ore senza un numero (es. unavailable), "
        "fuori dalla media. `consumato` c'e' solo per i contatori; "
        "`consumato_non_calcolato` dice perche' manca. `grana: dettaglio` sono "
        "i cambi veri (entro le 24 ore, o per chi non ha statistiche); "
        "`grana: oraria` sono fasce di un'ora: una fascia non e' un punto, di' "
        "«fra le 14 e le 15», non «alle 14». "
        "Stati: `per_mano_di: HIRIS` e' probabile (un mio atto nello stesso "
        "istante): dillo come probabile; senza, chi sia stato non lo so. "
        "`cronaca_non_letta`: non ho potuto controllare i miei atti. Di chi si "
        "sposta dico solo `home` o `not_home`. "
        "Esecuzioni: `esito` com'e' finita, `guasto` l'errore. Home Assistant "
        "ne conserva poche: una che manca NON e' andata bene. `non_letti` "
        "nomina chi non ho potuto leggere -- non e' «mai partita» -- e "
        "`non_lette_in_tutto` le conta su tutte le pagine. "
        "Errori: `volte` e' una causa sola ricomparsa N volte, non N episodi; "
        "conta per `livello`. Il registro tiene poche voci e si svuota a ogni "
        "riavvio di Home Assistant: un'assenza non prova niente. I messaggi "
        "arrivano sigillati: i segreti che conosco sono `<secret nome>`, e il "
        "testo che somiglia a un'istruzione e' filtrato. "
        "Esecuzioni ed errori solo per chi amministra Home Assistant."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            **_SUBJECT_FILTERS,
            "cosa": {"type": "string", "enum": list(HISTORY_KINDS),
                     "description": "Che cosa chiedere; di norma stati."},
            "riferimento": {"type": "string",
                            "description": "L'id esatto (es. "
                                           "'sensor.camera_temperatura')."},
            "integrazione": {
                **_SUBJECT_FILTERS["integrazione"],
                "description": (_SUBJECT_FILTERS["integrazione"]["description"]
                                + " Per gli errori, chi ha scritto la voce."),
            },
            "ore": {"type": "number", "maximum": WINDOW_MAX_HOURS,
                    "description": "Le ultime N ore, da adesso. Predefinito 24. "
                                   "Non insieme a da/a."},
            "da": {"type": "string",
                   "description": "L'inizio: «oggi», «ieri» (la loro mezzanotte, nel "
                                  "fuso della casa) o un istante ISO col fuso."},
            "a": {"type": "string",
                  "description": "La fine: «oggi» (adesso), «ieri» (la mezzanotte che "
                                 "lo chiude) o un istante ISO col fuso. Senza, "
                                 "adesso. Vuole `da`."},
            "esecuzione": {"type": "string",
                           "description": "Solo con cosa=esecuzioni e UNA "
                                          "automazione o script: il run_id di una "
                                          "riga, per la traccia passo per passo."},
            "livello": {"type": "string", "enum": list(LEVELS),
                        "description": "Solo con cosa=errori."},
        },
    },
}

# I tetti sulla finestra di «calendar». **Tetto SCELTO, non misurato** --
# a differenza del 30 predefinito qui sotto, che e' una misura sulla casa
# vera. Oltre un ANNO in ciascuna direzione la domanda non e' piu' sui
# PROSSIMI appuntamenti ma una scansione del calendario -- la stessa soglia
# concettuale dei 90 giorni che la storia ammette per un valore nel tempo
# (`house_history`, anch'essi scelti e non misurati), spostata piu' in la' perche'
# un calendario vive per natura su questa scala: un impegno come «Ferie
# estive» o «Anniversario» (`home_space/appointments.py`) e' proprio
# annuale.
MAX_CALENDAR_DAYS_AHEAD = 365
MAX_CALENDAR_DAYS_BACK = 365
# Misurato sulla casa vera il 06/09/2026 (`HAClient.calendar_events`): sette
# giorni avanti danno ZERO eventi su ENTRAMBI i calendari, trenta ne danno
# cinque. Un predefinito di sette risponderebbe quasi sempre "niente impegni",
# anche quando qualcosa sta per arrivare -- e' la ragione del numero, non un
# valore di comodo. Il passato resta a RICHIESTA (`giorni_indietro`,
# predefinito 0): la domanda per cui questo strumento esiste e' sui
# PROSSIMI appuntamenti, non sui passati.
DEFAULT_CALENDAR_DAYS_AHEAD = 30


def _clamp_days(raw, *, default: float, ceiling: float) -> float:
    """Qualunque cosa -> un numero di giorni fra 0 e `ceiling`.

    Contratto totale (NaN, stringhe, numeri fuori scala diventano tutti il
    default, mai un'eccezione) e minimo a 0 apposta: qui 0 e' un valore
    LEGITTIMO -- e' il default di `giorni_indietro`, "niente passato" -- e
    alzarlo a 1 (come faceva `normalize_hours`, uscita il 30/09/2026 con gli
    strumenti del tempo) trasformerebbe "niente passato" in
    "un giorno di passato" a ogni chiamata senza l'argomento esplicito.
    """
    try:
        number = float(raw)
    except Exception:
        return default
    if math.isnan(number):
        return default
    return min(float(ceiling), max(0.0, number))


def _days_beyond(raw, ceiling: float) -> bool:
    """Un numero di giorni chiesto oltre il tetto. Cio' che non e' un numero
    lo ferma gia' `dispatch` contro il `type` dello schema."""
    return (isinstance(raw, int | float) and not isinstance(raw, bool)
            and not math.isnan(raw) and raw > ceiling)


def _days_said(raw) -> str:
    """Il numero chiesto, come lo si ridice: `400`, non `400.0`."""
    return str(int(raw)) if float(raw).is_integer() else str(raw)


CALENDAR_TOOL_DEF = {
    "name": "calendar",
    # Tappa 5, Task 5 (06/10/2026): la descrizione dice cio' che lo schema non
    # dice -- da 3.050 caratteri, che ripetevano finestra, predefiniti e tetti
    # gia' scritti nelle proprieta', a meno di un terzo, coi fatti di prima.
    "description": (
        "I PROSSIMI appuntamenti scritti dalle persone sui calendari di questa "
        "casa («cosa ho in programma questa settimana?»). Non e' `agenda`, che "
        "sono gli impegni di HIRIS. Ogni impegno porta `titolo`, `dal`, `al` "
        "(escluso: il primo giorno o istante che non ne fa parte), `giornaliero` "
        "(tutto il giorno), `calendario` (il nome di chi lo tiene: i calendari "
        "si fondono in un elenco) e, se scritti, `luogo` e `descrizione`. "
        "**Un calendario dice solo cio' che ci e' scritto**: `impegni: []` "
        "vuol dire nessun impegno segnato nella finestra, non una casa vuota, "
        "ed e' normale. `calendari_guardati` c'e' sempre: i calendari che ho "
        "provato a leggere; vuoto vuol dire che la casa non ne ha. "
        "`non_letti` c'e' solo se qualcuno non l'ho potuto leggere, per "
        "qualunque causa: dillo, e non dire «non hai impegni» se un calendario "
        "manca. `troncato: true`: almeno un calendario aveva piu' impegni di "
        "quelli tornati, e mancano i piu' lontani dall'inizio della finestra "
        "-- con `giorni_indietro` possono essere proprio i prossimi."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "giorni_avanti": {
                "type": "number",
                "description": (
                    "Quanti giorni in avanti guardare, da adesso. "
                    f"Predefinito {DEFAULT_CALENDAR_DAYS_AHEAD}, non 7: una finestra piu' corta "
                    "rischia di rispondere «niente» anche quando qualcosa "
                    f"sta per arrivare. Il massimo e' {MAX_CALENDAR_DAYS_AHEAD}."
                ),
            },
            "giorni_indietro": {
                "type": "number",
                "description": (
                    "Quanti giorni all'indietro guardare, da adesso. "
                    "Predefinito 0 (niente passato): usalo solo se ti viene "
                    f"chiesto esplicitamente il passato. Il massimo e' {MAX_CALENDAR_DAYS_BACK}."
                ),
            },
        },
        "required": [],
    },
}

def _quoted(names) -> str:
    """«a», «b», «c» -- la forma coi guillemet dei messaggi di questo modulo:
    un elenco leggibile, non un repr di lista Python."""
    return ", ".join(f"«{n}»" for n in names)


#: Come si dice al modello, in italiano, ogni `type` di JSON Schema che il
#: catalogo usa. E' la traduzione del confine fra lo schema e la frase del
#: rifiuto, scritta qui una volta: i tipi sono quelli di JSON Schema, non nostri.
_TYPE_WORDS = {
    "string": "un testo", "integer": "un intero", "number": "un numero",
    "boolean": "vero o falso", "object": "un oggetto", "array": "un elenco",
}


def _has_type(value: Any, json_type: str) -> bool:
    """`value` e' del `type` di JSON Schema? Un booleano non e' un numero
    (in Python lo e'); un numero con la virgola e parte decimale zero e' un
    intero, come per JSON Schema."""
    if json_type == "boolean":
        return isinstance(value, bool)
    if isinstance(value, bool):
        return False
    if json_type == "integer":
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if json_type == "number":
        return isinstance(value, (int, float))
    if json_type == "string":
        return isinstance(value, str)
    if json_type == "object":
        return isinstance(value, dict)
    if json_type == "array":
        return isinstance(value, list)
    return True


def _wrong_value(key: str, value: Any, schema: dict) -> str | None:
    """Cosa non va in un valore rispetto al suo schema (`type`, `enum`,
    `minimum`, `maximum`), o `None`. Un `null` e' un argomento omesso: lo
    giudica `required`."""
    if value is None:
        return None
    declared = schema.get("type")
    types = declared if isinstance(declared, list) else [declared] if declared else []
    if types and not any(_has_type(value, json_type) for json_type in types):
        words = " o ".join(_TYPE_WORDS.get(json_type, json_type) for json_type in types)
        return f"{_quoted([key])} vuole {words}"
    allowed = schema.get("enum")
    if allowed is not None and value not in allowed:
        return f"{_quoted([key])} vale uno fra {_quoted(allowed)}, non {_quoted([value])}"
    # `minimum` e `maximum` di JSON Schema (B-33, 08/10/2026): una durata e'
    # un numero con l'unita' nel nome, e il suo intervallo lo dice lo schema.
    # Scritti a rovescio (`not value >= ...`) perche' NaN non passi.
    if "minimum" in schema and not value >= schema["minimum"]:
        return f"{_quoted([key])} vale almeno {schema['minimum']}"
    if "maximum" in schema and not value <= schema["maximum"]:
        return f"{_quoted([key])} vale al massimo {schema['maximum']}"
    return None


def _bad_arguments(name: str, arguments: dict[str, Any]) -> dict | None:
    """Il controllo unico sugli argomenti di uno strumento, usato da
    `ToolDispatcher.dispatch` PRIMA di chiamare qualunque gestore -- non nei
    dodici gestori, cosi' che uno strumento futuro nasca gia' protetto.

    Consuma `input_schema["required"]` e `input_schema["properties"]`, che
    ogni riga di `TOOLS` gia' dichiara nella sua definizione: nessuna firma
    nuova, nessun secondo elenco da tenere allineato.

    Due discipline DIVERSE, con due frasi diverse -- non una sola
    «argomenti non validi» che le confonde:

    - un obbligatorio ASSENTE, o presente ma `null`: `required` di JSON
      Schema guarda in linea di principio solo la PRESENZA della chiave, ma
      nessuna proprieta' di questo catalogo ammette `null` come valore
      vero (vedi `input_schema["properties"]` di ognuna: sempre un tipo
      concreto), quindi un `null` esplicito su un obbligatorio e' la STESSA
      assenza scritta in un altro modo -- trattarlo da "presente" lascerebbe
      passare un `{"riferimento": null}` che ogni gestore dovrebbe fermare
      per conto suo. Un valore non-`null` ma comunque vuoto (`""`) resta fuori
      da questa disciplina apposta: uno strumento che lo vuole non vuoto lo
      controlla gia' da se', come fa `_search` con `testo` o `_history` con
      `esecuzione` -- un controllo che questa funzione non duplica;
    - un nome che lo schema non conosce affatto: ignorarlo in silenzio
      lascerebbe il modello convinto di aver chiesto una cosa che in realta'
      non e' mai stata letta.

    **Le due si dicono INSIEME quando accadono insieme**, non a turni
    separati: il caso che ha motivato questo intero task -- il modello
    scrive `orario` invece di `ore` -- accende ENTRAMBE le condizioni
    (`ore` manca, `orario` e' ignoto). Riportarne una sola per turno
    costringerebbe il modello a due correzioni quando una basterebbe: prima
    aggiungerebbe `ore` senza sapere che `orario` va tolto, e lo scoprirebbe
    solo al turno dopo.

    Restituisce `None` quando gli argomenti vanno bene -- anche per uno
    strumento come `agenda`, che non dichiara `required` affatto (nessun
    obbligatorio: un dizionario vuoto e' una chiamata legittima).

    **E il valore di ogni argomento noto** (Tappa 5, Task 3, D-40): il suo
    `type` e il suo `enum`, letti dallo schema. Fino al 05/10/2026 il
    vocabolario lo rivalidava a mano ogni parser (`genere`, `ordina`,
    `livello`), e il tipo nessuno: `"false"` per un booleano diventava vero.
    Lo schema e' la fonte: nessuna lista di valori ricopiata qui. Si guarda
    il primo livello delle proprieta'; dentro gli oggetti annidati
    (`bersaglio`, `ancore`) valida chi li riceve.
    """
    if not isinstance(arguments, dict):
        return {"errore": f"«{name}»: gli argomenti vanno dati come un oggetto "
                          "(nome: valore), non come "
                          f"{_TYPE_WORDS.get(_json_type_of(arguments), 'un valore')}."}
    schema = _TOOL_PER_NAME[name].definition["input_schema"]
    allowed = schema.get("properties", {})
    required = schema.get("required", [])

    missing = [field for field in required
               if field not in arguments or arguments[field] is None]
    unknown = [key for key in arguments if key not in allowed]

    parts = []
    if missing:
        verb = "manca" if len(missing) == 1 else "mancano"
        every_required = f" (obbligatori: {_quoted(required)})" if len(required) > 1 else ""
        parts.append(f"{verb} {_quoted(missing)}{every_required}")
    if unknown:
        every_allowed = f" (argomenti validi: {_quoted(sorted(allowed))})" if allowed else ""
        parts.append(f"non conosco {_quoted(unknown)}{every_allowed}")
    parts.extend(wrong for key, value in arguments.items() if key in allowed
                 for wrong in [_wrong_value(key, value, allowed[key])] if wrong)

    if not parts:
        return None
    return {"errore": f"«{name}»: " + "; ".join(parts) + "."}


def _json_type_of(value: Any) -> str | None:
    """Il `type` di JSON Schema di un valore, per dire cosa e' arrivato."""
    return next((json_type for json_type in _TYPE_WORDS if _has_type(value, json_type)), None)


def _reserved_core_service(arguments: dict[str, Any]) -> bool:
    """La chiamata di `execute` e' un servizio del dominio `homeassistant` che
    Home Assistant riserva agli amministratori (`privacy.HA_CORE_USER_SERVICES`)?
    Il dominio e' universale per la porta (`action/verification.py`) e HIRIS
    chiama col proprio token di amministratore: senza questa domanda chiunque
    chatti riavvierebbe Home Assistant."""
    domain, _dot, service = str(arguments.get("servizio") or "").partition(".")
    return domain == "homeassistant" and service not in HA_CORE_USER_SERVICES


def _asks_admin_reads(arguments: dict[str, Any]) -> bool:
    """La chiamata di `history` chiede una `cosa` che Home Assistant mostra ai
    soli amministratori (`privacy.ADMIN_ONLY_HISTORY_KINDS`: esecuzioni ed
    errori, con la fonte in Home Assistant scritta li')?"""
    return arguments.get("cosa") in ADMIN_ONLY_HISTORY_KINDS


def _promises_an_action(arguments: dict[str, Any]) -> bool:
    """La promessa e' un `fai`? **Il soffitto di chi chiede vale anche per
    l'azione rimandata** (ruling 2.7 della revisione di sicurezza): chi non
    puo' comandare adesso non puo' farsi eseguire la stessa chiamata fra
    un'ora dallo schedulatore, che al risveglio non ha piu' nessun soffitto da
    guardare. Un `chiedi` resta permesso: legge e basta."""
    return arguments.get("specie") == "fai"


@dataclass(frozen=True)
class Permission:
    """Un gesto del soffitto (`api/soffitto`) che una chiamata richiede.

    `applies`: quando la richiede, dagli argomenti; `None` = sempre.
    `refusal`: la frase del rifiuto; `None` = il `perche` del soffitto, come
    ogni altro rifiuto del soffitto."""
    gesture: str
    applies: Callable[[dict[str, Any]], bool] | None = None
    refusal: str | None = None


@dataclass(frozen=True)
class Tool:
    """Una riga della tabella degli strumenti (`TOOLS`, Tappa 5, Task 2):
    tutto cio' che serve a servire uno strumento, dichiarato una volta.

    - `definition`: cio' che va al modello (`*_TOOL_DEF`);
    - `handler`: il metodo di `ToolDispatcher` che lo serve;
    - `resources`: gli archivi senza cui non si puo' servire
      (`ToolDispatcher._missing_resource`);
    - `needs_thread`: serve il filo di chi ha aperto il turno (le promesse
      sono di chi le chiede, spec 2026-09-26 §2);
    - `permissions`: i gesti del soffitto che la chiamata richiede;
    - `mask`: il gesto senza il quale la risposta esce COPERTA dove Home
      Assistant mostra il dato ai soli amministratori. Non e' un rifiuto: il
      gestore riceve `masked` e copre la parte che compone lui;
    - `read_only`: lo strumento legge e basta -- non scrive in Home
      Assistant, ne' nella memoria, ne' nell'agenda, ne' nell'officina. Le
      letture della stessa risposta partono insieme, le altre una alla volta
      (`reads_only`, Tappa 7 T10, D15a). Si dichiara per riga, e chiude per
      difetto: uno strumento nuovo e' una scrittura finche' qualcuno non
      scrive che legge. Non si deduce da `permissions`: `cancel` scrive
      senza chiedere nessun gesto, e `history` legge
      chiedendone uno.

    Il soffitto si chiede in `ToolDispatcher.dispatch`, una volta, dalla riga:
    fino al 05/10/2026 lo chiedevano sette punti dentro i gestori (D-23)."""
    definition: dict
    handler: Callable[..., Any]
    resources: tuple[str, ...] = ()
    needs_thread: bool = False
    permissions: tuple[Permission, ...] = ()
    mask: str | None = None
    read_only: bool = False

    @property
    def name(self) -> str:
        return self.definition["name"]


class ToolDispatcher:
    """Collega gli strumenti della tabella (`TOOLS`) agli archivi, alla porta,
    all'officina, al canale HA e alle letture del cervello -- e non altro.

    Prende `home_space_store` e `memory_store` gia' costruiti dal chiamante
    (`create_app()` o l'equivalente nei test): questa classe non ne apre
    nessuno, e non li chiude -- non le appartengono.

    `dispatch()` e' l'unico punto d'ingresso e non solleva MAI: uno
    strumento sconosciuto, argomenti mancanti, o un guasto imprevisto
    diventano tutti un dizionario con la chiave `errore`, leggibile dal
    modello -- mai un'eccezione che gli spezza il turno.
    """

    def __init__(self, home_space_store: HomeSpace, memory_store: MemoryStore,
                 cache=None, actuator=None,
                 ha=None, registry=None, agenda=None, workshop=None,
                 exchange: str | None = None, journal=None,
                 translations=None, knowledge=None,
                 judgments: TypeJudgments | None = None,
                 soffitto: dict | None = None,
                 subject: dict | None = None,
                 phrase: str | None = None,
                 thread: ChatThread | None = None,
                 house: House | None = None,
                 mind=None, actor: str = "chat",
                 refuse_high: bool = False) -> None:
        self._home_space = home_space_store
        # Se `propose` deve rifiutare una proposta di livello `alto` invece di
        # archiviarla (`Workshop.propose`). Vero solo per «Rendila
        # automatica» (attori, Task 4.5): un'automazione su serrature o
        # allarme agirebbe senza chiedere, e quelle chiedono sempre
        # (decisione del proprietario del 03/10/2026, ribadita il 06/10).
        self._refuse_high = refuse_high
        # CHI agisce in questo turno, per la cronaca e per l'officina: la chat,
        # o il mestiere di sfondo che ha il dispatcher sotto il suo guardiano
        # (il proponente, attori Task 4.2). Fino al 06/10/2026 era il
        # letterale «chat» in tre gestori, e una proposta del proponente
        # sarebbe uscita firmata dalla chat.
        self._actor = actor
        # Le letture del cervello (`mind/view.MindView`, Tappa 5, Task 8):
        # lo scope, l'obiettivo, i resoconti, le analisi. Arrivano GIA'
        # costruite, come il sapere e la cronaca: `home_space` non importa da
        # `mind` (`tests/test_confine_home_space.py`). `None` e' legittimo
        # come per gli altri archivi: `mind` dichiara un errore.
        self._mind = mind
        # L'istantanea della casa di QUESTO turno (`house.House`, R18): una
        # lettura dell'anagrafe e una dello specchio, la gerarchia calcolata
        # una volta, per il nucleo e per ogni strumento. Il chiamante la passa
        # quando l'ha gia' letta per il nucleo (`handlers_chat`); senza, il
        # dispatcher la legge alla prima richiesta. Si butta quando la casa
        # cambia sotto il turno: vedi `_turn_house`.
        self._house = house
        # Il sigillo dei segreti si costruisce alla prima richiesta e si
        # ricorda: leggere `secrets.yaml` a ogni voce di registro sarebbe
        # un accesso al disco per riga.
        self._remembered_seal = None
        self._memory = memory_store
        # Il soffitto di questo turno (invariante I-1): quello di chi l'ha
        # aperto, o quello dichiarato dal suo mestiere (decisione 13,
        # `steering.Species.ceiling`). L'unico costruttore del prodotto
        # (`create_tool_dispatcher`) rifiuta `None`; qui arriva solo dalle
        # prove che costruiscono il dispatcher a mano.
        self._soffitto = soffitto
        # CHI ha aperto questo turno. Viaggia accanto al soffitto e non dentro:
        # il soffitto dice cosa si concede, il soggetto dice a chi -- e la
        # cronaca ha bisogno del secondo anche quando il primo ha detto di si'.
        self._subject = subject
        # **La frase di QUESTO turno** (B-5): quella su cui una conferma nasce.
        # Non e' la `frase` di una proposta, che e' la frase che ha CHIESTO la
        # costruzione -- questa e' quella che la CONFERMA. `None` per le
        # promesse e per un turno MCP che non e' di chat, dove non c'e'
        # nessuna persona che parli, ed e' il fatto giusto: la cronaca dira'
        # che nessuno ha detto niente. Un turno di chat del ponte porta
        # persona, soffitto e frase del job (`handlers_mcp._call_tool`).
        self._phrase = phrase
        # Il FILO di chi ha aperto questo turno (fetta «le chat divise», Task
        # 7, spec §5 "confirm e' del filo"): la coppia (soggetto, ingresso)
        # calcolata UNA volta dal chiamante (`create_tool_dispatcher`), non
        # dedotta qui da `_subject`, che porta specie/nome ma non l'ingresso.
        # `None` e' legittimo come per `_soffitto`: nessuna persona ha aperto
        # questo turno (promessa, osservatore) o il job e' precedente a
        # questa versione -- e in quel caso `Workshop.apply` non restringe
        # (vedi il suo docstring).
        self._thread = thread
        # Il sapere (`mind/knowledge.py`): cio' che HIRIS ha capito, con la
        # provenienza. Ne esce il SIGNIFICATO della classe di un'entita'
        # sul dettaglio di `search` (`queries._class_meaning`). `None` e'
        # legittimo.
        self._knowledge = knowledge
        # Lo specchio dello stato vivo. E' la STESSA `entity_cache` da cui
        # il nucleo prende "notevole adesso": una sola fonte, un solo
        # specchio. La cache resta in SOLA LETTURA anche adesso che `execute`
        # esiste: chi scrive e' la porta (`action/actuator.py`), che chiama
        # Home Assistant e poi RILEGGE da qui -- lo specchio non si aggiorna
        # a mano per far tornare i conti. Prima della fetta «comandare» la
        # ragione scritta qui era «conosce, non agisce»: era una proprieta'
        # del prodotto, oggi e' una proprieta' di QUESTO attributo.
        self._cache = cache
        # La porta dell'azione (`action/actuator.py`), l'unico punto del prodotto
        # che esegue. `None` e' legittimo: il dispatcher e' SEMPRE costruibile
        # (contratto della classe), e senza porta `execute` dichiara un errore
        # invece di sollevare -- come gli altri quattro fanno senza archivi.
        self._actuator = actuator
        # Il canale verso Home Assistant, per `related` e per cio' che dopo di
        # esso chiedera' un fatto MOMENTANEO (i legami non si archiviano --
        # vedi il docstring del modulo). In SOLA LETTURA come `_cache`: chi
        # scrive resta la porta, e questo attributo non le fa concorrenza.
        self._ha = ha
        # Il registro dei servizi (`action/registry.py::ServiceRegistry`), la
        # STESSA istanza che usa la porta -- non se ne apre un secondo, per la
        # stessa ragione di `_ha`: due registri sarebbero due opinioni
        # su cosa esiste, e potrebbero divergere. Serve a `search` (i
        # comandi di un'entita') e al recapito di un `chiedi`. Un `fai` NON
        # si verifica piu' qui: lo verifica la porta (`ActionActuator.verify`,
        # Tappa 7 T1, E-13), con la stessa guardia del registro muto con cui
        # esegue. `None` e' legittimo e NON passa da `_missing_resource`.
        self._registry = registry
        # L'archivio delle promesse (`keeper/store.py`). `None` e'
        # legittimo come per la porta: i tre strumenti dichiarano un errore
        # leggibile invece di sollevare.
        self._agenda = agenda
        # L'officina (`action/construction/workshop.py`), l'unico punto che
        # scrive CONFIGURAZIONE. Sorella della porta, non sua sostituta: sono
        # due canali diversi (spec «un canale, una porta»). `None` e'
        # legittimo come per la porta: i due strumenti dichiarano un errore.
        self._workshop = workshop
        # L'identita' di QUESTO turno. Serve alla guardia dell'officina: una
        # proposta non si conferma nel turno che l'ha creata. Senza identita'
        # l'officina rifiuta di applicare dalla chat e indica la pagina --
        # un cancello che non sa chi sta passando non e' un cancello.
        self._exchange = exchange
        # La cronaca degli atti (`action/journal.py`), la STESSA istanza che
        # riceve l'officina -- non una seconda apertura dello stesso file
        # SQLite. Serve a `history` per dire «l'ho fatto io» accanto a un cambio
        # che Home Assistant non firma. `None` e'
        # legittimo e NON passa da `_missing_resource`: senza cronaca lo
        # strumento risponde lo stesso, perdendo l'attribuzione e non la
        # risposta -- che e' una degradazione, non un guasto.
        self._journal = journal
        # Le traduzioni degli stati di Home Assistant
        # (`proxy/state_translations.StateTranslations`), la STESSA istanza che
        # legge il nucleo: le parole con cui uno stato si rende sono una sola
        # tabella, non una per porta. `None` e' legittimo -- il dettaglio risponde
        # lo stesso, con `stato_non_reso` al posto di `stato_leggibile` e il
        # motivo dentro. E' una degradazione dichiarata, non un guasto.
        self._translations = translations
        # L'istantanea dei giudizi sui tipi (spec 2026-09-16 §3): la STESSA
        # istanza che legge il nucleo, `app["type_judgments"]`
        # (`handlers_chat.py::create_tool_dispatcher`). `None` e' legittimo
        # come per gli altri archivi -- il dispatcher e' SEMPRE costruibile --
        # e ricade sul solo seme del repo (`REPO_JUDGMENTS`): la stessa
        # degradazione dichiarata di `_translations` qui sopra, MAI un
        # dettaglio che solleva perche' nessuno gli ha passato l'istantanea.
        self._judgments = judgments if judgments is not None else REPO_JUDGMENTS

    def _missing_resource(self, tool: Tool) -> str | None:
        """Quale archivio serve a questo strumento (`Tool.resources`) e non
        c'e'."""
        for which in tool.resources:
            if which == "casa" and self._home_space is None:
                return "la conoscenza della casa non e' ancora stata caricata"
            if which == "memoria" and self._memory is None:
                return "l'archivio della memoria non e' ancora stato caricato"
            if which == "porta" and self._actuator is None:
                return "il collegamento con Home Assistant non e' disponibile"
            if which == "ha" and self._ha is None:
                # Distinto dal messaggio della porta apposta: li' manca
                # l'oggetto che ESEGUE, qui il canale a cui CHIEDERE. Sono due
                # assenze diverse, e un utente che legge la risposta del
                # modello deve poter capire quale delle due sta guardando.
                return "non c'e' un collegamento vivo con Home Assistant a cui chiederli"
            if which == "promesse" and self._agenda is None:
                return "l'archivio delle promesse non e' ancora stato caricato"
            if which == "officina" and self._workshop is None:
                return ("non posso costruire: l'officina non e' disponibile "
                        "(Home Assistant non e' raggiungibile, o l'add-on e' appena partito)")
        return None

    async def dispatch(self, name: str, arguments: dict[str, Any] | None) -> dict:
        try:
            return await self._serve(name, arguments or {})
        except Exception as error:
            # Rete di sicurezza finale: qualunque guasto imprevisto (un
            # archivio chiuso a meta', un tipo inatteso negli argomenti) si
            # dichiara qui invece di risalire -- vedi il docstring della
            # classe. Dal 05/10/2026 (Tappa 5, Task 3, D-41) dentro la rete
            # stanno anche la riga, gli archivi e gli argomenti: con
            # `arguments=5` il controllo degli argomenti sollevava FUORI.
            # Minor #7 review finale: dichiararlo al MODELLO non bastava --
            # un archivio corrotto o un guasto ricorrente restava invisibile
            # all'operatore, che non ha altro modo di saperlo (il modello
            # riceve solo la stringa "errore", non uno stack). Loggato qui.
            logger.warning(
                "strumento «%s» ha sollevato %s: %s", name, type(error).__name__, error
            )
            return {"errore": f"lo strumento «{name}» ha incontrato un problema: {error}"}

    async def _serve(self, name: str, arguments: Any) -> dict:
        """Il giro di `dispatch`, nell'ordine che e' il contratto: la riga,
        gli archivi, gli argomenti, il filo e il soffitto, il gestore."""
        # Gli archivi possono mancare: il chiamante puo' costruirci prima che
        # esistano. Senza questo controllo il modello riceve
        # «'NoneType' object has no attribute 'leggi'» -- un errore Python
        # travestito da risposta, mentre questo dispatcher promette messaggi
        # LEGGIBILI. Dire cosa manca e' anche l'unico modo perche' il modello
        # possa spiegarlo all'utente invece di riprovare all'infinito.
        tool = _TOOL_PER_NAME.get(name)
        missing = None if tool is None else self._missing_resource(tool)
        if missing is not None:
            return {"errore": f"«{name}» non e' disponibile: {missing}."}
        if tool is None:
            # NON "non inventare nomi di tool": se il modello ha chiamato
            # questo nome, gliel'abbiamo dato NOI in un turno precedente (un
            # tool rimosso da un aggiornamento, o un refuso nostro nella
            # cronologia) -- accusarlo di essersi inventato uno strumento che
            # gli avevamo servito noi e' esattamente il difetto gia'
            # corretto una volta su questo ramo. Il messaggio resta un fatto
            # neutro: cosa esiste, non un rimprovero.
            available = ", ".join(sorted(_TOOL_PER_NAME))
            return {"errore": f"lo strumento «{name}» non e' fra quelli disponibili "
                              f"({available})."}
        # Task 1 di «rifiutare e importare» (§6b): un obbligatorio mancante e
        # un nome ignoto si rifiutano QUI, una volta sola per tutti
        # gli strumenti -- non nei gestori, che fino ad oggi lo facevano a
        # mano (quattro di loro) o non lo facevano affatto (un lettore
        # del tempo, uscito il 30/09/2026 con la storia, dichiarava un
        # obbligatorio e non lo controllava; un argomento sconosciuto veniva
        # ignorato in silenzio da ognuno). Vedi
        # `_bad_arguments` per le due discipline e perche' sono diverse.
        bad_arguments = _bad_arguments(name, arguments)
        if bad_arguments is not None:
            return bad_arguments
        refusal = self._refusal(tool, arguments)
        if refusal is not None:
            return refusal
        # La maschera (`Tool.mask`): il soffitto si chiede QUI, una volta,
        # e il gestore riceve la risposta -- copre la parte di risposta
        # che Home Assistant mostra solo a chi amministra, dove la compone.
        options = ({"masked": self._ceiling_denies(tool.mask)}
                   if tool.mask is not None else {})
        # Alcuni gestori sono coroutine (fanno rete, o scaldano il registro
        # dei servizi prima di verificarlo o di mostrarlo); gli altri no. Si
        # attende cio' che e' attendibile invece di rendere `async` anche i
        # gestori sincroni.
        occurrence = tool.handler(self, arguments, **options)
        if inspect.isawaitable(occurrence):
            occurrence = await occurrence
        return occurrence

    # -- search --------------------------------------------------------

    async def _search(self, arguments: dict[str, Any], *, masked: bool) -> dict:
        """La porta che interroga la casa (spec `2026-09-29-una-porta-sola-
        per-la-casa.md` §2): i filtri entrano, un insieme di voci esce, e la
        profondita' la decide `house_query.query_house` da quante sono.

        **Coroutine dal 29/09/2026**, per la stessa ragione per cui lo era il
        dettaglio che assorbe: quando la voce e' una sola esce il dettaglio
        completo, e quello di un'entita' porta i `comandi` dal registro dei
        servizi -- un registro che si carica PIGRAMENTE (vedi
        `_ensure_registry_fresh`). Si scalda qui, PRIMA di sapere quante voci
        usciranno: `query_house` e' pura e sincrona, e non puo' aspettare a
        meta' strada. Il costo e' quello dichiarato dal registro: un giro per
        invalidazione, non uno per ricerca.

        Solo quando un'ENTITA' puo' uscire -- nessun `genere`, o `entita`:
        e' l'unico dettaglio che legge il registro (`queries._view_entity` ->
        `commands_for`), come lo scaldava il vecchio dettaglio. Scaldarlo per
        un ricordo o per un'area sarebbe un giro di rete per un dato che quel
        ramo non guarda.
        """
        filters = parse_filters(arguments)
        if isinstance(filters, dict):
            return filters
        if filters.kind in (None, "entita"):
            await self._ensure_registry_fresh()
        translations = await self._read_translations()
        # UNA casa, per le righe e per il dettaglio: due letture in istanti
        # diversi sarebbero la divergenza che l'istantanea esiste per chiudere.
        house = self._turn_house()
        mirror = house.mirror

        def detail(kind: str, reference) -> dict:
            return self._full_detail_sync(kind, reference, house=house,
                                          translations=translations, masked=masked)

        response = query_house(house, self._home_space.behavior(), filters,
                               detail=detail, timezone=self._timezone())
        if "errore" in response:
            return response
        # Senza inventario leggibile ogni `stato: None` sarebbe ambiguo fra
        # «l'entita' non ha stato» e «non ho potuto guardare»: si dichiara.
        # Fix E1-③: la lettura di QUESTA chiamata e cio' che la cache dichiara
        # di se stessa, composti in `read_mirror` (A-25). Sulla risposta e non
        # sulla voce: vale per ogni riga, a qualunque profondita'.
        if not mirror.readable:
            response["stato_non_letto"] = True
        if filters.name:
            self._declare_name_gaps(response, filters, house)
        elif filters.floor and "piani" in house.unavailable:
            # Una domanda per `piano` senza nome: col registro dei piani
            # caduto nessuna area ha un piano, e `trovate: 0` sarebbe un
            # silenzio non dichiarato (re-review della fetta, 30/09/2026).
            response["non_ho_potuto_guardare"] = [_fallen_stores_message(["piani"])]
        return response

    def _declare_name_gaps(self, response: dict, filters, house: House) -> None:
        """Cio' che una ricerca per NOME non ha potuto guardare, e il divieto
        di concludere «non esiste» (24/09/2026) quando nessun nome combacia.

        Sopravvive alla porta nuova (29/09/2026) perche' il difetto che chiude
        non dipende dalla forma della risposta: `trovate: 0` su un nome e'
        «nessun nome combacia», non «la cosa non c'e'». Vale solo per le
        domande per NOME: su «luci accese: 0» non c'e' nessun nome da non aver
        riconosciuto, e `escluse` dice gia' cosa manca.

        `nulla_riconosciuto` esce solo se non c'e' NIENTE: ne' voci, ne'
        escluse -- una cosa nascosta che combacia e' un nome riconosciuto -- e
        nessun filtro oltre al nome e al genere, che potrebbe essere lui ad
        aver svuotato l'insieme. Le due guardie su `_blind_spots` (guasto di
        adesso contro limite stabile) sono quelle di prima: vedi il suo
        docstring."""
        found_nothing = response["trovate"] == 0
        entries = self._blind_spots(house, found_nothing=found_nothing)
        current_gap = any(not stable for _message, stable in entries)
        only_the_name = replace(filters, kind=None).only_by_name
        if (found_nothing and not any(response["escluse"].values())
                and only_the_name and not current_gap):
            response["nulla_riconosciuto"] = True
            response["suggerimento"] = _NOTHING_RECOGNIZED_SUGGESTION
        if entries:
            response["non_ho_potuto_guardare"] = [message for message, _s in entries]

    def _blind_spots(self, house: House, *,
                     found_nothing: bool = True) -> list[tuple[str, bool]]:
        """Perche' una ricerca per nome potrebbe non trovare SENZA che la cosa
        manchi.

        «Non c'e' nessuna cosa con quel nome» e «non ho potuto guardare»
        avrebbero la stessa faccia -- zero voci. Da qui ne hanno due.

        Solo fatti, e solo quando ci sono: l'elenco e' vuoto quando non c'e'
        niente da dichiarare.

        Ogni voce e' `(messaggio, stabile)`, perche' i motivi non sono tutti
        dello STESSO genere di dubbio. Un registro non letto, un corpo non
        letto o lo specchio giu' sono un guasto DI ADESSO (`stabile=False`):
        la casa non e' stata guardata per intero, e `nulla_riconosciuto`
        (`_declare_name_gaps`) sarebbe falso se lo dicesse. Le entita' senza
        nome ne' nel registro ne' nello specchio sono un limite STABILE
        (`stabile=True`) che riguarda ALTRE entita': la ricerca ha guardato
        tutti i nomi dichiarati, e tacere `nulla_riconosciuto` per questo
        motivo spegnerebbe la dichiarazione su ogni ricerca senza esito non
        appena una sola entita' porta quel limite. Il chiamante decide da
        questa etichetta, non indovinandola dal testo del messaggio.

        `found_nothing`: il limite stabile non si risolve riprovando, quindi
        senza questo cancello uscirebbe a ogni `search`, comprese quelle
        riuscite -- un'assenza dichiarata SEMPRE smette di essere un segnale.
        Si riporta solo quando serve a spiegare una ricerca senza esito. I
        guasti di adesso NON hanno questo cancello: un registro caduto puo'
        nascondere altri omonimi anche quando questa ricerca ha gia' trovato
        qualcosa."""
        entries: list[tuple[str, bool]] = []
        # I registri che la porta legge (`_SEARCHED_STORES`). Fino al
        # 30/09/2026 c'erano anche le «etichette», perche' la vecchia ricerca
        # le offriva come candidati; la porta non le cerca, e un loro registro
        # caduto non nasconde niente a chi cerca (review finale, M3). I
        # «piani» restano: `piano` e' un filtro della porta.
        fallen_stores = sorted(set(house.unavailable) & _SEARCHED_STORES)
        if fallen_stores:
            entries.append((_fallen_stores_message(fallen_stores), False))
        # Il comportamento non passa da `unavailable()` -- la sua fonte non
        # e' un registro dell'anagrafe -- e ha un segnale di incompletezza
        # suo: `unread_bodies()`, le entita' di cui non si conosce il corpo.
        # E' un guasto di adesso: un corpo non letto nasconde cio' che
        # quell'automazione fa, sia che Home Assistant non abbia risposto,
        # sia che i segreti non si siano potuti controllare.
        unread_bodies = self._home_space.unread_bodies()
        if unread_bodies:
            message = (
                f"di {len(unread_bodies)} fra automazioni e script non si conosce "
                "il corpo: cosa fanno non e' cercabile adesso, e potrebbe "
                "riguardare proprio cio' che stai cercando.")
            entries.append((message, False))


        mirror = house.mirror
        # D7: le disabilitate non si cercano; ogni altra classe si'.
        unnamed = [e for e in house.home_space.get("entita") or []
                     if not (e.get("nome") or "").strip()
                     and visibility(e)[0] != "disabilitata"]
        if unnamed and not mirror.readable:
            message = (
                f"{len(unnamed)} entita' non hanno un nome nel registro di Home Assistant e "
                "lo specchio dello stato non e' leggibile: il ripiego sul nome che Home "
                "Assistant mostra non e' disponibile, quindi quelle entita' non sono "
                "cercabili per nome in questo momento.")
            entries.append((message, False))
        elif unnamed:
            # Il caso PARZIALE: lo specchio e' leggibile (altrimenti il ramo
            # sopra avrebbe gia' parlato), ma per QUESTE entita' non porta un
            # friendly_name -- non sono cercabili per nome.
            unnamed_even_live = [e for e in unnamed
                                 if not (mirror.names.get(e["id"]) or "").strip()]
            # E' un fatto stabile (`True`): si dichiara solo quando serve a
            # spiegare una ricerca senza esito, vedi il docstring.
            if unnamed_even_live and found_nothing:
                message = (
                    f"{len(unnamed_even_live)} entita' di questa casa non hanno un nome ne' nel "
                    "registro di Home Assistant ne' nello specchio dello stato (lo specchio si "
                    "legge, ma non porta un nome per queste): e' un limite stabile di quelle "
                    "entita', non un guasto di questa ricerca -- ripetere la stessa ricerca non "
                    "cambia nulla, serve rinominarle in Home Assistant.")
                entries.append((message, True))
        return entries

    # -- il dettaglio completo, la voce di `search` quando e' una sola ----

    def _full_detail_sync(self, kind: str, reference, *, house: House,
                          translations: dict, masked: bool) -> dict:
        """Il dettaglio completo di UNA cosa di casa -- quello che fino al
        29/09/2026 dava lo strumento `view`, oggi la voce di `search` quando
        l'insieme ne ha una sola (`house_query.query_house`, il suo `detail`).

        Sincrono apposta: `query_house` e' pura e lo chiama a meta' strada.
        Cio' che andava ATTESO -- il registro dei servizi, che fino all'08/09
        nessuno scaldava per chi leggeva (misurato dal vivo sulla 3.23.0: la
        chiave `comandi` mancava su tutte le entita' di una casa appena
        riavviata), e le parole degli stati -- l'ha gia' scaldato `_search`, e
        arriva qui come `translations`. La casa e' la STESSA delle righe
        (`house`), non una seconda lettura.

        Il filtro di riservatezza NON si applica qui: lo applica
        `query_house` a ogni voce che esce, in un punto solo.
        """
        # I ricordi hanno un id numerico (MemoryStore, AUTOINCREMENT), e
        # `parse_filters` rende ogni riferimento un testo. Un riferimento non
        # convertibile non e' un errore da sollevare -- e' lo stesso "non l'ho
        # trovato" degli altri tipi.
        if kind == "ricordo" and self._memory is None:
            return {"esiste": False, "tipo": "ricordo", "riferimento": reference,
                    "non_disponibile": True,
                    "motivo": "l'archivio della memoria non e' ancora stato caricato"}
        if kind == "ricordo" and not isinstance(reference, int):
            try:
                reference = int(reference)
            except (TypeError, ValueError):
                return {"esiste": False, "tipo": "ricordo", "riferimento": reference}
        # Tutti i ricordi, non solo gli ultimi venti (il default di
        # `fetch()`): un ricordo vecchio ancorato a QUESTA cosa non deve
        # sparire dal suo stesso dettaglio solo perche' non e' fra i piu'
        # recenti -- stessa scelta di `handlers_home_space.handle_get_briefing`.
        memories = ([] if self._memory is None
                    else self._memory.fetch(limit=self._memory.count()))
        detail = _view_detail(house, self._home_space.behavior(),
                              memories, kind, reference,
                              unread_bodies=self._home_space.unread_bodies(),
                              # Il registro dei servizi: con lui il dettaglio
                              # di UNA entita' dice anche cosa le si puo'
                              # CHIEDERE, coi limiti veri (spec §13). `None`
                              # e' legittimo -- la lettura non deve fallire
                              # perche' l'azione non e' cablata.
                              registry=self._registry,
                              translations=translations,
                              # Il sapere: cosa significa la classe di
                              # un'entita'. `None` e' legittimo.
                              knowledge=self._knowledge,
                              # L'istantanea dei giudizi (spec §3): mai `None`
                              # qui -- `__init__` l'ha gia' ricaduta sul seme.
                              judgments=self._judgments)
        if self._memory is None and isinstance(detail, dict) and "ricordi" in detail:
            # I ricordi ancorati a questa cosa non si sono potuti leggere: si
            # dice, invece di un `ricordi: []` che direbbe «nessuno».
            del detail["ricordi"]
            detail["ricordi_non_letti"] = ("l'archivio della memoria non e' "
                                           "ancora stato caricato")
        # Il corpo di automazioni e scene solo a chi amministra: la regola e la
        # sua ragione vivono in `privacy.cover_reserved_body`, che chiama anche
        # la rotta `GET /api/home-space`. Il nucleo della chat non porta i
        # corpi -- solo il nome e se il corpo c'e'. Il soffitto lo chiede
        # `dispatch`, una volta, dalla riga (`Tool.mask`).
        if isinstance(detail, dict) and masked:
            detail = cover_reserved_body(detail, kind=kind)
        return detail

    def _turn_house(self) -> House:
        """La casa di questo turno (`house.House`): letta alla prima
        richiesta e tenuta, cosi' nucleo, `search` e `history` guardano la
        STESSA casa e la gerarchia si costruisce una volta (R18).

        Si rilegge in due casi, e solo in quelli. (1) L'anagrafe e' stata
        ricostruita a meta' turno: `HomeSpace.read()` restituisce un oggetto
        nuovo a ogni ricostruzione, e il confronto e' per identita' -- una
        casa con l'anagrafe di prima sarebbe la copia che invecchia in
        silenzio (R12). (2) Un comando di questo turno e' andato a segno
        (`_execute`, `_confirm` la buttano): lo stato che ha cambiato deve
        vedersi alla domanda dopo."""
        if self._house is None or self._house.home_space is not self._home_space.read():
            self._house = House.read(self._home_space, self._cache)
        return self._house

    def _mirror(self) -> Mirror:
        """Lo specchio della casa di questo turno (`_turn_house`), con
        `readable` gia' composto da `topology.read_mirror` (A-25). Cosa porta
        ogni campo, e perche', sta in `topology.live_mirror`."""
        return self._turn_house().mirror

    # -- legami --------------------------------------------------------

    async def _related(self, arguments: dict[str, Any]) -> dict:
        """Chiede a Home Assistant chi tocca questa cosa, e non lo salva.

        Non lo salva ed e' una scelta, non una dimenticanza: i legami sono
        MOMENTANEI quanto lo stato -- un'automazione salvata un minuto fa li
        cambia -- e una tabella riletta di rado mentirebbe poche ore dopo. E'
        la stessa ragione per cui `state` sta fuori dal sistema di riferimento
        (`home_space.topology.reference_frame`). Quindi si chiede quando
        serve, e la risposta vive il tempo di un turno.

        Qui dentro c'e' solo il collegamento: la traduzione dei tipi e la
        forma della risposta stanno in `queries.related`, che e' pura e si
        prova senza rete.
        """
        kind = arguments.get("tipo")
        reference = arguments.get("riferimento")
        # Gli obbligatori li controlla `dispatch()` (`_bad_arguments`), da
        # `RELATED_TOOL_DEF["input_schema"]["required"]`.
        ha_kind = HA_LINK_TYPE.get(kind)
        if ha_kind is None:
            # Fermato QUI, prima della rete, e con l'elenco dei tipi veri:
            # mandarlo comunque a Home Assistant produrrebbe un rifiuto suo,
            # che arriva al modello come «errore» generico e non gli insegna
            # niente. Stessa scelta di `_recall` con le ancore.
            available = ", ".join(_OUR_LINK_TYPES)
            return {"errore": f"«{kind}» non e' un tipo di cui Home Assistant sappia "
                              f"i legami ({available})."}
        response = await self._ha.related(ha_kind, str(reference))
        return _readable_links(response, kind, reference)

    # -- remember ----------------------------------------------------------

    def _remember(self, arguments: dict[str, Any]) -> dict:
        text = arguments.get("testo")
        if not isinstance(text, str) or not text.strip():
            return {"errore": "«remember» richiede un «testo» non vuoto."}

        # L'indice dalla casa del turno (A-13, Tappa 3, Task 12): la stessa
        # istantanea dello specchio delle unita' qui sotto, costruito una
        # volta per casa. Un'anagrafe mai letta e' `{}`, e il suo indice e'
        # vuoto. Quali ancore non si possono verificare -- tutte, con
        # l'anagrafe mai letta; quelle del registro caduto, altrimenti -- lo
        # dice la stessa casa (`House.unverifiable_tether_kinds`, G-21): la
        # regola era scritta qui e in `handlers_memory`.
        house = self._turn_house()
        lookup = house.lookup()
        unverifiable_kinds = house.unverifiable_tether_kinds()

        interpretation = {
            "forza": arguments.get("forza"),
            "grandezza": arguments.get("grandezza"),
            "minimo": arguments.get("minimo"),
            "massimo": arguments.get("massimo"),
            "ancore": arguments.get("ancore") or [],
            "condizioni": arguments.get("condizioni") or [],
        }
        # Il CANCELLO (memory/interpretation.py): scarta cio' che non
        # regge (un'ancora inventata, una forza fuori vocabolario) e lo
        # DICHIARA in `problemi` -- non lo lascia passare in silenzio, e non
        # butta via l'intero ricordo per questo. E' la differenza con
        # `handlers_memory.handle_patch_memory`, che invece RIFIUTA
        # un'intera correzione se `problemi` non e' vuota: li' si sta
        # correggendo un ricordo gia' esistente e l'utente puo' riprovare,
        # qui si sta salvando per la prima volta cio' che qualcuno ha detto
        # -- e "preso nota, ma senza salvare niente" e' esattamente il
        # difetto da cui e' nato questo modulo (vedi il docstring in cima).
        # Le unita' VIVE: il registro di Home Assistant non le manda (le riempie
        # solo se l'utente le ha forzate a mano), quindi senza questo la
        # deduzione dell'unita' di un ricordo non e' mai scattata.
        cleaned, problems, corrections = validate(
            interpretation, lookup, unverifiable_kinds, self._mirror())

        # L'autore viene dal SOGGETTO del turno (decisione 5, Task 6), mai da
        # un argomento del modello -- `arguments.get("detto_da")` non si legge
        # nemmeno piu' (lo schema qui sopra non lo chiede). Fix round 1: un
        # modello che lo mandi comunque non arriva neppure a questo metodo --
        # `dispatch()` rifiuta l'intera chiamata PRIMA, perche' lo schema non
        # conosce piu' quell'argomento (`_bad_arguments`). Il nome e'
        # controllato dall'utente (arriva dall'intestazione dell'ingress di
        # Home Assistant) e finisce nel nucleo a OGNI turno futuro
        # (briefing.py) -- sanificato con `sanitize_ha_value`, la stessa
        # porta di "Chi ti sta parlando" (handlers_chat.py::_who_is_speaking,
        # Task 5), prima di archiviarlo.
        subject_name = (self._subject or {}).get("nome")
        memory_id = self._memory.remember(
            text,
            detto_da=sanitize_ha_value(subject_name) if subject_name else None,
            said_by=subject_key_for(self._subject) if self._subject else None,
            ancore=cleaned["ancore"], conditions=cleaned["condizioni"],
            modality=cleaned["forza"], grandezza=cleaned["grandezza"],
            minimum=cleaned["minimo"], maximum=cleaned["massimo"], unit=cleaned["unita"],
        )
        return {"salvato": True, "id": memory_id, "problemi": problems, "correzioni": corrections}

    # -- fetch ---------------------------------------------------------

    def _recall(self, arguments: dict[str, Any]) -> dict:
        reference = arguments.get("riferimento")
        # Il controllo «"riferimento" e' obbligatorio» viveva QUI fino al
        # giro di correzioni sul Task 1 di «rifiutare e importare» (§6b):
        # tolto perche' `dispatch()` lo fa gia' PRIMA di chiamare questo
        # gestore (`_bad_arguments`, che ora tratta un obbligatorio presente
        # ma `None` come assente -- non solo un obbligatorio del tutto
        # mancante), e il messaggio non diceva niente di piu' di quello
        # centrale. Provato in positivo, non per assenza di rosso:
        # `test_a_required_argument_present_but_null_is_missing_too`
        # (`tests/test_knowledge_tools.py`) passa `riferimento: None` a
        # `fetch` e vede il rifiuto centrale.
        kind = arguments.get("tipo")
        # Fix E1-②: un `tipo` fuori dal vocabolario delle ancore ("stanza",
        # o "entita'" con l'accento -- plausibilissimo per un modello
        # italiano che non lo sta copiando da uno schema) finiva silenzioso
        # in `per_tether(tipo, riferimento)`, che semplicemente non trova
        # mai nulla per un tipo che nessuna ancora usa: il risultato era
        # `{"ricordi": []}`, indistinguibile da "nessun ricordo riguarda
        # questa cosa" -- proprio quando invece il ricordo esiste. `queries.view`
        # con un tipo ignoto almeno risponde `esiste: False`; qui si
        # dichiara l'errore invece, cosi' un input non valido resta
        # distinguibile da "non ti ho detto niente".
        if kind is not None and kind not in _TETHER_TYPES:
            available = ", ".join(_TETHER_TYPES)
            return {"errore": f"«{kind}» non e' un tipo di ancora valido per «fetch» "
                              f"({available})."}
        kinds = (kind,) if kind else _TETHER_TYPES

        # Il modello puo' non sapere se «cucina» e' un'area o un dispositivo
        # (o, in teoria, un'entita'): senza `tipo` si cerca su tutti e tre e
        # si uniscono i risultati, invece di pretendere che lo specifichi
        # sempre -- una ricerca che fallisce solo perche' il tipo indovinato
        # era sbagliato sarebbe un "non ho trovato niente" bugiardo.
        seen: set[int] = set()
        memories: list[dict] = []
        for t in kinds:
            for memory in self._memory.per_tether(t, reference):
                if memory["id"] in seen:
                    continue
                seen.add(memory["id"])
                memories.append(memory)
        memories.sort(key=lambda r: r["id"], reverse=True)
        # C-2/I1 (review indipendente 25/08/2026): `per_tether` legge
        # l'archivio direttamente, non passa da `queries.view` -- senza
        # questa riga il testo uscirebbe filtrato dal dettaglio e grezzo da
        # `fetch`. Stessa funzione condivisa, un punto solo -- e con la casa
        # del turno le ancore portano `nome_attuale` ed `esiste` (G-21).
        return {"ricordi": _sanitized_memories(memories, self._turn_house())}

    # -- execute -------------------------------------------------------

    async def _execute(self, arguments: dict[str, Any]) -> dict:
        """Non fa nulla: chiede alla porta.

        E' voluto. Tutta la logica -- verifica, chiamata, rilettura, registro
        -- vive in `action/actuator.py`, perche' domani lo schedulatore e il brain
        chiederanno alla STESSA porta senza passare da qui. Se un giorno questo
        metodo cresce, la logica sta migrando nel posto sbagliato.

        Il soffitto, che la porta non conosce, lo chiede `dispatch` dalla
        riga di `execute` (`Tool.permissions`, spec 2026-09-27, ruling
        R-2.10b e fix round 1, M-1): chi ha il ruolo di sola lettura -- in
        Home Assistant il gruppo `system-read-only` -- non comanda; e i
        servizi del dominio `homeassistant` che Home Assistant riserva agli
        amministratori non si chiamano per chi non lo e'
        (`_reserved_core_service`).
        """
        outcome = await self._actuator.execute(
            arguments, actor=self._actor, subject=self._subject)
        # Un comando puo' aver cambiato la casa: la domanda dopo, in questo
        # stesso turno, la rilegge invece di guardare lo specchio di prima
        # (`_turn_house`). Anche su un rifiuto: costa una lettura, e decidere
        # qui cosa ha toccato Home Assistant sarebbe indovinarlo.
        self._house = None
        return outcome

    # -- le promesse -----------------------------------------------------

    async def _read_translations(self) -> dict:
        """L'esito etichettato delle traduzioni, scaldandole se serve.

        **Il motivo lo dichiara chi ha fallito.** Senza cache cablata, senza
        sistema di riferimento (la casa non ha ancora detto la propria lingua)
        o con la lettura caduta, si torna un esito «non lette» col motivo --
        mai un dizionario vuoto che il chiamante dovrebbe interpretare.

        La coppia `(versione_ha, lingua)` viene dal sistema di riferimento che
        l'anagrafe ha gia' distillato da `Config.as_dict()`
        (`home_space.topology.reference_frame`): non una seconda lettura verso
        Home Assistant, e non una seconda idea di «lingua della casa».
        """
        if self._translations is None:
            return {"lette": False,
                    "motivo": "la lettura delle traduzioni non e' collegata a "
                              "questo dispatcher"}
        frame = self._home_space.reference_frame()
        try:
            return await self._translations.read(
                ha_version=frame.get("versione_ha"), language=frame.get("lingua"))
        except Exception as error:
            return {"lette": False, "motivo": f"{type(error).__name__}: {error}"}

    async def _ensure_registry_fresh(self) -> None:
        """Scalda il registro dei servizi prima di leggerlo o di verificare.

        **Due chiamanti, non uno**: `_promise` (che VERIFICA una chiamata
        prima di prometterla) e `_search` (che MOSTRA i comandi di
        un'entita'). Senza il secondo, il dettaglio uscirebbe senza la chiave
        `comandi` su tutte le entita' di una casa appena riavviata: chi legge
        ha lo stesso bisogno di chi esegue.

        Stessa forma di `action/actuator.py::ActionActuator.execute`: un
        `try/except` attorno a `ensure_fresh`, perche' il registro si
        carica PIGRAMENTE alla prima azione ESEGUITA (`server.py`, commento
        sulla scelta) -- un add-on appena avviato che non ha ancora eseguito
        nessuna azione arriva qui con un registro presente ma VUOTO, e senza
        questa chiamata la vista uscirebbe senza comandi, anche quando Home
        Assistant e' raggiungibile e pronto a rispondere.
        Difetto misurato dal vivo su 3.9.1: «verifica le temperature di ogni
        stanza e fra un'ora mandami il delta» rifiutato con «il registro dei
        servizi non e' ancora pronto», mentre le otto temperature erano appena
        state lette correttamente (da un'altra strada, non dal registro).

        Diversa dalla porta in un punto: qui un guasto non diventa un errore
        da mostrare al modello -- si registra e basta; chi verifica un `fai`
        e' la porta, che ha il suo rifiuto per il registro muto.

        Senza registro (`None`, legittimo: `promise` non lo dichiara come
        archivio richiesto nella sua riga, `Tool.resources`) o senza un canale HA
        vivo (`_ha` e' `None`, altrettanto legittimo per lo stesso
        motivo) non si tenta nemmeno: il registro non si puo' caricare senza
        un client a cui chiedere, e restare senza canale resta il rifiuto
        onesto di sempre -- non diventa "«promise» non e' disponibile"
        (quel messaggio e' di `_missing_resource`, per un'altra assenza:
        aggiungere "ha" alle risorse della riga di `promise` sarebbe
        proprio quello scambio).
        """
        if self._registry is None:
            return
        channel = self._ha
        if channel is None:
            return
        try:
            await self._registry.ensure_fresh(channel)
        except Exception as error:
            logger.warning(
                "rinfresco del registro servizi fallito (%s: %s): chi verifica "
                "degrada al rifiuto onesto, chi legge vede una vista senza "
                "«comandi»", type(error).__name__, error)

    async def _promise(self, arguments: dict[str, Any]) -> dict:
        """Il modello propone, il codice restringe (spec §9.1).

        Tutto si verifica ADESSO: la chiamata contro questa installazione, il
        valore di partenza. Un rifiuto alle 17 sarebbe arrivato quando non
        c'e' piu' nessuno a correggerlo. `quando_ts` e i tetti (30 giorni, 50
        in sospeso per filo, il totale della casa) restano a
        `keeper/promise.validate` / `AgendaStore.create`: sono verifiche sulla FORMA
        della promessa, non su questa installazione, e vivono gia' li'.

        **La promessa e' del filo di questo turno** (fetta «il seguito delle
        chat divise», spec 2026-09-26 §2), e il filo viene dal chiamante
        (`self._thread`), mai dagli argomenti: `_bad_arguments` rifiuta
        qualunque chiave che lo schema non conosce, e lo schema non conosce
        ne' il filo ne' il recapito. Il recapito non lo sceglie piu' il
        modello: si risolve al risveglio dal soggetto (`keeper/recipient.py`);
        qui lo si guarda solo per dire SUBITO, a chi chiede un `chiedi`, se
        una notifica non potra' arrivargli e perche'.

        Coroutine perche' scalda il registro (`_ensure_registry_fresh`) e
        chiede il recapito a Home Assistant: il dispatcher attende gia' ogni
        gestore awaitable (`dispatch`, `inspect.isawaitable`).
        """
        import time as _time

        from ..keeper.recipient import recipients_for

        # Il filo e il soffitto (un `fai` vuole `comandare`) li ha gia'
        # chiesti `dispatch` alla riga di `promise`.
        verb = arguments.get("specie")
        await self._ensure_registry_fresh()

        when = historian.instant_epoch(arguments.get("quando"))
        if when is None:
            return {"errore": ("non ho capito quando: dammi un istante come "
                               "«2026-08-19T17:00:00+02:00».")}

        data = {
            "specie": verb,
            "frase": arguments.get("frase") or "",
            "quando_ts": when,
            "quando_detto": arguments.get("quando_detto"),
            "fuso": self._timezone(),
        }

        if verb == "fai":
            call = arguments.get("chiamata")
            if not isinstance(call, dict):
                return {"errore": "una promessa «fai» ha bisogno di `chiamata`."}
            refusal = await self._verify_now(call)
            if refusal is not None:
                return {"errore": refusal}
            data["chiamata"] = call
            # **Quante entita' tocca, contate ADESSO** (reperto B-6,
            # 22/09/2026). Su un bersaglio per area la verifica alla nascita si
            # fermava prima -- «lo risolvera' la porta, al momento» -- quindi
            # la promessa nasceva senza che nessuno sapesse cosa avrebbe
            # toccato, e poteva risvegliarsi trenta giorni dopo su una casa
            # diversa.
            #
            # Non e' una restrizione e non rifiuta niente: se la risoluzione
            # non riesce, il numero resta `None` e la promessa nasce lo stesso.
            # Rifiutare qui toglierebbe una funzione che il proprietario usa,
            # per una misura che serve a INFORMARE.
            data["entities_at_birth"] = await self._count_target(call)
        else:
            to_compare = arguments.get("da_confrontare") or []
            refusal = self._verify_comparison_targets(to_compare)
            if refusal is not None:
                return {"errore": refusal}
            data["domanda"] = arguments.get("domanda")
            data["istantanea"] = self._snapshot(to_compare)

        occurrence = self._agenda.create(data, thread=self._thread, now=_time.time())
        if "errore" in occurrence:
            return occurrence
        result = {"promessa": without_thread(occurrence["promessa"])}
        if verb == "chiedi":
            # Solo per sapere SE una strada c'e': la notifica partira' al
            # risveglio, dal recapito risolto allora (se nel frattempo la
            # persona si collega, funziona gia'). Il motivo e' un testo di
            # HIRIS (`Recipients.reason`), lo stesso che leggera' la pagina.
            recipients = await recipients_for(self._subject, self._ha,
                                              self._registry)
            if not recipients.services:
                result["avviso"] = f"{_NO_RECIPIENT_NOTICE}{recipients.reason}"
        return result

    async def _count_target(self, call: dict) -> int | None:
        """Quante entita' copre il bersaglio di `call`, adesso — o `None`.

        **`None` non e' zero.** `None` dice «non si applica o non l'ho potuto
        contare»; `0` direbbe «nessuna entita'», che e' un fatto diverso e che
        al risveglio produrrebbe un confronto falso.

        Non sollevare mai: questa misura serve a informare, e un guasto qui non
        deve impedire di promettere.

        **Il conto lo fa la porta** (S-20, Tappa 4; E-13, Tappa 7 T1):
        `ActionActuator.verify` traduce il bersaglio con la verifica e lo
        risolve come al risveglio. Fino al 05/10/2026 qui partiva il
        bersaglio del modello com'era, la risoluzione falliva, e il numero
        restava `None` su ogni promessa; fino al 07/10/2026 la traduzione si
        rifaceva qui e la risoluzione si chiedeva a un metodo privato della
        porta.
        """
        target = (call or {}).get("bersaglio")
        if not isinstance(target, dict) or self._actuator is None:
            return None
        # Un bersaglio di sole entita' non ha niente da risolvere: il numero
        # sarebbe una copia di cio' che il modello ha gia' scritto, e al
        # risveglio non potrebbe essere cambiato.
        if set(target) <= {"entita"}:
            return None
        # La risoluzione la fa la porta (`verify`, E-13): la traduzione del
        # bersaglio e' la sua, la stessa del risveglio. Il conto e' `risolte`,
        # cio' che il bersaglio COPRE, anche quando la verifica poi rifiuta.
        try:
            answer = await self._actuator.verify(call)
        except Exception:
            return None
        found = (answer.get("bersaglio") or {}).get("risolte")
        return len(found) if isinstance(found, list) else None

    def _list_agenda(self, arguments: dict[str, Any]) -> dict:
        """«Cosa mi hai promesso?»: la fondamenta n.4 applicata alle promesse
        -- quelle di CHI chiede, non della casa (spec 2026-09-26 §2).

        Il nome del metodo NON puo' essere `_promesse`: quell'attributo e'
        gia' l'archivio (vedi `__init__`). Due cose distinte, due nomi.
        """
        show_all = bool(arguments.get("tutte"))
        rows, left = self._agenda.page(thread=self._thread, solo_in_sospeso=not show_all)
        answer: dict = {"promesse": [without_thread(r) for r in rows]}
        if left > 0:
            # C-39: le promesse che la pagina non mostra si dichiarano, nella
            # forma di `oltre` delle altre risposte (`restano`). Niente
            # `salta`: lo strumento non ha un argomento per la pagina dopo.
            answer["oltre"] = {"restano": left}
        return answer

    def _cancel(self, arguments: dict[str, Any]) -> dict:
        """Disdice una promessa di QUESTO filo. Un id di un altro filo riceve
        la stessa risposta di uno che non esiste (`AgendaStore.cancel`)."""
        import time as _time

        identifier = arguments.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            return {"errore": "«cancel» ha bisogno dell'`id` della promessa."}
        occurrence = self._agenda.cancel(identifier.strip(), thread=self._thread,
                                         now=_time.time())
        if "promessa" in occurrence:
            return {**occurrence, "promessa": without_thread(occurrence["promessa"])}
        return occurrence

    async def _propose(self, arguments: dict[str, Any], *, masked: bool) -> dict:
        """Propone. Non scrive: lo fa `confirm`, e non nello stesso turno.
        `masked`: chi propone non amministra, e il «prima» di un'automazione
        o di una scena non si mostra (`Workshop.propose`, `reveal_before`)."""
        import time as _time
        intent = {
            "gesto": arguments.get("gesto"),
            "dominio": arguments.get("dominio"),
            "chiave": arguments.get("chiave"),
            "alias": arguments.get("alias"),
            "descrizione": arguments.get("descrizione") or "",
            "innesco": arguments.get("innesco") or [],
            "condizioni": arguments.get("condizioni") or [],
            "azioni": arguments.get("azioni") or [],
            "stati": arguments.get("stati") or [],
            "campi": arguments.get("campi"),
            "parametri": arguments.get("parametri") or [],
            "riuso": bool(arguments.get("riuso")),
            "ricorrente": bool(arguments.get("ricorrente")),
            "richiesto": arguments.get("richiesto"),
            "helper": arguments.get("helper") or [],
            "livello": arguments.get("livello"),
            "frase": arguments.get("frase"),
        }
        return await self._workshop.propose(
            intent, actor=self._actor, exchange=self._exchange, now=_time.time(),
            thread=self._thread,
            reveal_before=not masked, refuse_high=self._refuse_high)

    async def _confirm(self, arguments: dict[str, Any]) -> dict:
        """Applica una proposta gia' creata da `propose`. La guardia del
        turno (non si conferma nel turno che ha proposto) vive nell'officina:
        qui si passa `self._turno`, la stessa identita' coniata una volta per
        turno dal chiamante (`api/handlers_chat.py`/`api/handlers_mcp.py`)."""
        import time as _time
        # **L'id puo' mancare, e nel caso normale manca sempre**: nasce in un
        # risultato di strumento e la cronologia della chat porta solo testo,
        # quindi al turno della conferma il modello non ce l'ha. Chi lo manda
        # lo passa; chi non ce l'ha lascia decidere all'officina, che sceglie
        # l'unica in sospeso di un altro turno o elenca le candidate.
        proposal_id = (arguments or {}).get("proposta_id")
        proposal_id = (proposal_id.strip()
                       if isinstance(proposal_id, str) else None)
        occurrence = await self._workshop.apply(
            proposal_id, actor=self._actor, exchange=self._exchange,
            now=_time.time(), subject=self._subject,
            # B-5: il cancello sa dire «in mezzo c'e' stato un turno», non «in
            # mezzo c'e' stato un si'». La frase di questo turno va in cronaca
            # accanto all'atto, cosi' che «chi ha detto si'» abbia una
            # risposta invece di essere dedotto dal silenzio.
            confirm_phrase=self._phrase,
            # Task 7, spec §5: «confirm e' del filo». Il filo di QUESTO
            # turno, non quello della proposta -- l'officina confronta i due.
            thread=self._thread)
        # Come dopo `execute`: una configurazione applicata cambia la casa,
        # e la casa di questo turno si rilegge alla prossima domanda.
        self._house = None
        return occurrence

    async def _verify_now(self, call: dict) -> str | None:
        """Il rifiuto della verifica, o `None`. Sola lettura: non esegue niente.

        **La verifica e' quella della porta** (`ActionActuator.verify`, E-09 ed
        E-13, Tappa 7, Task 1, 07/10/2026). Fino a quel giorno qui si
        ricomponevano a mano le guardie del registro vuoto e dello specchio
        cieco, con frasi diverse da quelle della porta, e si chiamava
        `verification()` da se': due porte che rispondevano in due modi alla
        stessa situazione. Le frasi ora sono quelle della porta.

        Non si risolvono i bersagli per aree o etichette (`resolve=False`):
        quella risoluzione chiede a Home Assistant, e una promessa nasce anche
        se in quel momento non risponde -- la porta la risolve al risveglio.
        Si verifica cio' che si puo' verificare senza rete -- il servizio
        esiste, l'entita' nominata esiste, i parametri appartengono a quel
        servizio -- che e' esattamente cio' che sbaglia il modello.

        Senza porta si RIFIUTA, non si tace (fix review Task 6, Rilievo 2,
        deciso dal proprietario): `PROMISE_TOOL_DEF` dichiara al modello
        «viene VERIFICATA adesso» senza condizioni.
        """
        if self._actuator is None:
            return ("non posso prometterlo: il collegamento con Home Assistant "
                    "non e' disponibile, e non posso verificare la chiamata.")
        answer = await self._actuator.verify(call, resolve=False)
        return answer.get("errore")

    def _blind_mirror_refusal(self) -> str:
        """Il rifiuto quando lo specchio dello stato non e' leggibile: "non
        so ancora", non un silenzio.

        Oggi la chiede solo `_verify_comparison_targets`: il `fai` lo
        verifica la porta (Tappa 7 T1), con il suo rifiuto per lo specchio
        cieco.
        """
        return ("non posso ancora prometterlo: non vedo lo stato di "
                "questa casa, l'inventario delle entita' non e' "
                "disponibile. Riprova fra un momento.")

    def _verify_comparison_targets(self, entities: list) -> str | None:
        """Il rifiuto se `to_compare` nomina un riferimento che lo
        specchio non conosce, o `None`. Sola lettura, come `_verify_now`.

        Lista vuota -> `None` SUBITO, senza toccare lo specchio: un `chiedi`
        senza `to_compare` resta legittimo (spec R7, requisito 2) --
        nessuna istantanea e' stata chiesta, quindi non c'e' niente da
        verificare, e non c'e' motivo di rifiutare un `chiedi` sulla sola
        base che lo specchio non e' pronto quando nessuno lo interroga.

        Specchio non leggibile -> stesso rifiuto di `_verify_now`
        (`_blind_mirror_refusal`, requisito 3): "non lo so ancora" si
        rifiuta, non si tace -- senza sapere cosa esiste non si puo' dire
        che un riferimento NON esiste, e lasciare nascere la promessa
        renderebbe falsa la dichiarazione di `PROMISE_TOOL_DEF` («viene
        VERIFICATA adesso»).

        Uno specchio leggibile ma senza il riferimento -> il rifiuto vero
        (requisito 1): oggi (prima di questo fix) `_snapshot` lasciava
        nascere la promessa con `valore: null` e la nota "non esisteva
        quando l'hai chiesto" -- il danno matura fra un'ora, quando nessuno
        puo' piu' correggere. «Il modello propone, il codice restringe»
        (spec §9.1), gia' applicato al `fai` (`_verify_now`): un `chiedi`
        non puo' rispondere diversamente alla stessa domanda solo perche'
        e' l'altra specie.
        Il motivo nomina il riferimento (cosa non esiste) e la strada per
        correggersi (pattern `action/verification.py:430-432`: «usa "search"...»).
        """
        if not entities:
            return None
        states = states_by_id(self._cache)
        if not states:
            return self._blind_mirror_refusal()
        unknown = [str(e) for e in entities if e not in states]
        if unknown:
            return ("non posso prometterlo: {} non esiste in questa casa. "
                     "Usa «search» per trovare l'id esatto e ripeti la "
                     "richiesta.".format(", ".join(unknown)))
        return None

    def _snapshot(self, entities: list) -> list[dict]:
        """I valori di partenza, presi ADESSO, con la loro unita'.

        Senza l'unita' e senza l'istante, «e' aumentata» non ha un termine di
        paragone e il modello se lo inventerebbe. E' la fondamenta n.1: il `72`
        che non si sa se sia Celsius o Fahrenheit.

        `stati` (da `states_by_id()`) e' la forma MINIMALE vera di
        `proxy/entity_cache.py::_to_minimal` -- non lo stato grezzo di Home
        Assistant. L'unita' vive li' nella chiave `unit` DI PRIMO LIVELLO,
        non dentro `attributes.unit_of_measurement` (quello e' HA grezzo, mai
        cio' che questo dispatcher vede): leggerla dagli attributi e' il
        difetto R6 -- l'istantanea nasceva SEMPRE senza unita' in produzione.
        `valore` invece era gia' corretto: legge `state`, che e' una chiave
        di primo livello identica in entrambe le forme.
        """
        import time as _time

        states = states_by_id(self._cache) or {}
        now = _time.time()
        measurements = []
        for identifier in entities:
            state = states.get(identifier)
            if state is None:
                measurements.append({"entita": identifier, "valore": None, "unita": None,
                               "misurato_ts": now,
                               "nota": "non esisteva quando l'hai chiesto"})
                continue
            measurements.append({"entita": identifier, "valore": state.get("state"),
                           "unita": state.get("unit") or None,
                           "misurato_ts": now})
        return measurements

    def _timezone(self) -> str | None:
        """Il fuso della casa, dall'unico lettore (`historian.house_timezone`).

        Senza `home_space_store` (i test che costruiscono un dispatcher
        minimale) il fuso resta sconosciuto, e la promessa nasce comunque --
        `fuso` e' un campo dichiarativo della promessa (spec §9.1), non un
        cancello che la blocca.
        """
        return historian.house_timezone(self._home_space)

    # -- il soffitto e il sigillo -----------------------------------------

    def _ceiling_denies(self, gesture: str) -> bool:
        """Il soffitto di questo turno nega questo gesto? L'unica domanda che
        gli strumenti fanno al soffitto -- la regola, sviluppo e turni senza
        persona compresi, e' `soffitto.denies`."""
        return denies(self._soffitto, gesture, self._subject)

    def _refusal(self, tool: Tool, arguments: dict[str, Any]) -> dict | None:
        """Il rifiuto di questa chiamata prima del gestore, o `None`: il filo,
        poi il soffitto, chiesti alla riga (`Tool.needs_thread`,
        `Tool.permissions`). Fino al 05/10/2026 il filo si chiedeva in tre
        gestori (D-42) e il soffitto in sette punti dentro i gestori (D-23):
        uno strumento nuovo nasceva senza permesso finche' qualcuno non se ne
        ricordava.

        L'ordine e' quello che i gestori avevano: il filo prima del soffitto
        (`promise`: una promessa senza filo non ha a chi tornare, con
        qualunque soffitto)."""
        if tool.needs_thread and self._thread is None:
            return {"errore": _NO_THREAD_REFUSAL}
        for permission in tool.permissions:
            if permission.applies is not None and not permission.applies(arguments):
                continue
            if self._ceiling_denies(permission.gesture):
                return {"errore": permission.refusal or self._soffitto["perche"]}
        return None

    def _seal(self):
        """Il sigillo dei segreti, costruito una volta per questo dispatcher.

        Fino al 22/09/2026 `SecretSeal` aveva **un solo chiamante**
        (`home_space/behavior.py`): il sigillo esisteva, era ottimo, e copriva
        una porta su quattro. Qui copre le altre due.

        Si costruisce PIGRAMENTE e si ricorda: leggere `secrets.yaml` a ogni
        voce di registro sarebbe un accesso al disco per riga. E un guasto non
        solleva -- `SecretSeal.from_file` non solleva mai, per disegno -- ma
        produce un sigillo `readable=False`, che non sigilla niente: meno
        protezione, non nessuna, e il resto del confine vale comunque.
        """
        if self._remembered_seal is None:
            self._remembered_seal = home_assistant_seal()
        return self._remembered_seal

    # -- la storia ------------------------------------------------------

    async def _history(self, arguments: dict[str, Any]) -> dict:
        """La storia della casa (spec `2026-09-30-la-storia.md`): compone le
        letture di `house_history` (`read_history`, `read_errors`) e mette il
        permesso SOPRA di loro.

        Dal 30/09/2026 sostituisce quattro gestori (`_trend`, `_happened`,
        `_system_log`, `_automation_trace`): quattro forme, misurate sulla
        v3.71.0 fra 3.600 e 35.000 caratteri a chiamata. Dal 04/10/2026
        (Tappa 3, Task 13) le letture non sono piu' metodi di questo oggetto:
        non dipendono dalla persona, e un attore le chiama senza un turno.
        Qui resta cio' che dalla persona dipende.

        **L'ordine dei controlli e' il contratto.** Chi non amministra e'
        rifiutato da `dispatch` PRIMA di qualunque lettura (la riga di
        `history`, `Tool.permissions`: `trace/list`, `trace/get`,
        `system_log/list` sono `require_admin`, ruling R-2.25); qui gli
        argomenti (un errore si dice senza toccare niente); poi la casa, che
        serve a ogni genere fuorche' agli errori -- per loro la casa del turno
        non si costruisce."""
        import time as _time

        now = _time.time()
        query = parse_query(arguments, now=now, timezone=self._timezone())
        if isinstance(query, dict):
            return query
        if query.kind == "errori":
            return await read_errors(self._ha, query, seal=self._seal())
        if self._home_space is None:
            return {"errore": "`history` non e' disponibile: la conoscenza della casa "
                              "non e' ancora stata caricata."}
        # UNA casa per tutta la chiamata, la stessa del turno.
        return await read_history(self._ha, query, self._turn_house(),
                                  self._home_space.behavior(), cache=self._cache,
                                  seal=self._seal(), journal=self._journal, now=now)

    # -- i calendari ------------------------------------------------------

    async def _calendar(self, arguments: dict[str, Any]) -> dict:
        """I prossimi appuntamenti, fusi da OGNI calendario di questa casa.

        Qui resta la COMPOSIZIONE (R13, Tappa 5): la finestra chiesta, le due
        letture da Home Assistant e il fuso. Leggere gli eventi, nominare i
        calendari illeggibili e fondere gli impegni e' di
        `appointments.merge_calendars`, che e' puro e dice perche'.

        **Se l'elenco dei calendari stesso non arriva**, non c'e' niente da
        provare a leggere: si propaga il suo `errore` cosi' com'e' (un
        passthrough puro).

        **Il fuso e' UNO SOLO, quello del dispatcher** (`self._timezone()`,
        la stessa fonte di `_history` -- non se ne apre una seconda): serve
        due volte, una per calcolare `now` con `historian.home_space_zone`
        (nessun doppione: e' la stessa funzione che gestisce gia' un fuso non
        riconosciuto con un avviso e il ripiego su UTC) e una passata a
        `merge_calendars`, che la passa a `read_appointment` per ogni evento.
        Fondere impegni letti con fusi DIVERSI romperebbe la prima chiave
        di `sort_appointments`, il giorno della casa -- non succede, perche' il
        fuso e' unico per questa chiamata, ma e' il presupposto su cui quella
        fusione poggia, e va dichiarato invece di dato per scontato.
        """
        import time as _time

        # Oltre il tetto si RIFIUTA, non si taglia (B9, approvata il
        # 05/10/2026; B-33): come `history` oltre i 90 giorni. Tagliato in
        # silenzio, il modello credeva di aver letto la finestra chiesta.
        too_far = [f"{key} arriva al massimo a {ceiling} giorni (chiesti {_days_said(value)})"
                   for key, ceiling in (("giorni_avanti", MAX_CALENDAR_DAYS_AHEAD),
                                        ("giorni_indietro", MAX_CALENDAR_DAYS_BACK))
                   for value in [arguments.get(key)]
                   if _days_beyond(value, ceiling)]
        if too_far:
            return {"errore": "«calendar»: " + "; ".join(too_far)
                    + ". Restringi la finestra."}
        ahead = _clamp_days(arguments.get("giorni_avanti"),
                            default=DEFAULT_CALENDAR_DAYS_AHEAD,
                            ceiling=MAX_CALENDAR_DAYS_AHEAD)
        behind = _clamp_days(arguments.get("giorni_indietro"),
                             default=0, ceiling=MAX_CALENDAR_DAYS_BACK)
        ha = self._ha
        listing = await ha.calendars()
        if "errore" in listing:
            return listing
        calendars = readable_calendars(listing)

        timezone = self._timezone()
        zone = historian.home_space_zone(timezone)
        now = datetime.fromtimestamp(_time.time(), tz=zone)
        start = (now - timedelta(days=behind)).isoformat()
        end = (now + timedelta(days=ahead)).isoformat()

        # Tutti insieme (A-34, Tappa 2): l'attesa e' quella del calendario
        # piu' lento, non la somma. `gather` rende nell'ordine chiesto, cioe'
        # quello di Home Assistant: `calendari_guardati` e `non_letti` non
        # dipendono da chi risponde prima. `calendar_events` non solleva.
        answers = await asyncio.gather(*(ha.calendar_events(entry["entity_id"], start, end)
                                         for entry in calendars))
        return merge_calendars(calendars, answers, timezone=timezone)


    # -- cio' che il cervello guarda (R8) ---------------------------------

    async def _read_mind(self, arguments: dict[str, Any]) -> dict:
        """Cio' che il cervello guarda e ha capito (Tappa 5, Task 8; R8): la
        STESSA lettura che la pagina riceve dalle rotte di
        `api/handlers_mind.py`, perche' tutte e due chiamano `MindView`
        (fondamenta 3). Quale lettura, lo dice `cosa`, e la tabella
        `MIND_READINGS` dice chi la serve: l'`enum` dello schema si deriva da
        lei, e un valore nuovo e' una riga sola.

        `giorno` sceglie un giorno solo, e vale per resoconti e analisi: con le
        altre letture si rifiuta invece di essere ignorato, come ogni filtro
        che non vale (`history`)."""
        what = arguments["cosa"]
        reading = MIND_READINGS[what]
        if arguments.get("giorno") is not None and not reading.by_day:
            daily = ", ".join(sorted(key for key, row in MIND_READINGS.items() if row.by_day))
            return {"errore": f"«giorno» vale solo per {daily}, non per «{what}»."}
        return await reading.serve(self, arguments.get("giorno"))

    def _mind_missing(self, *, store: bool = True) -> dict | None:
        """Cosa manca alle letture del cervello, o `None`: le letture stesse
        (un dispatcher costruito senza), o l'archivio. Un archivio assente non
        e' un archivio vuoto -- la rotta risponde 503, qui un `errore`."""
        if self._mind is None:
            return {"errore": "le letture del cervello non sono collegate."}
        if store and self._mind.store is None:
            return {"errore": "l'archivio del cervello non e' disponibile."}
        return None

    async def _mind_scope(self, _day) -> dict:
        missing = self._mind_missing(store=False)
        if missing is not None:
            return missing
        scope = self._mind.scope()
        if scope is None:
            return {"errore": "l'osservatore non e' disponibile: l'add-on e' partito senza di lui."}
        return scope

    async def _mind_objective(self, _day) -> dict:
        return self._mind_missing() or {"obiettivo": self._mind.objective()}

    async def _mind_reports(self, day: str | None) -> dict:
        missing = self._mind_missing()
        if missing is not None:
            return missing
        if not day:
            return {"resoconti": self._mind.reports()}
        found = self._mind.report(day)
        if found is None:
            # La stessa risposta della rotta: un giorno mai aggregato non e'
            # un giorno vuoto, e si dice quando il resoconto si scrivera'.
            return {"errore": f"il giorno {day} non e' stato aggregato",
                    "ora_notturna": self._mind.nightly_time()}
        return {"resoconto": found}

    async def _mind_analyses(self, day: str | None) -> dict:
        missing = self._mind_missing()
        if missing is not None:
            return missing
        if not day:
            return {"analisi": self._mind.analyses()}
        found = self._mind.analysis(day)
        if found is None:
            return {"errore": f"il giorno {day} non e' stato analizzato"}
        return {"analisi": found}

    async def _mind_energy(self, _day) -> dict:
        """La dashboard Energia (`home_space/energy.py`, piano degli attori,
        strato 2): cio' che il proprietario ha dichiarato a Home Assistant su
        chi e' rete, sole, batteria. E' della casa, non del cervello -- per
        questo non passa da `MindView` -- ma e' la stessa domanda «su cosa
        ragiona HIRIS», e il cervello la legge prima di scrivere una ricetta.

        `ha_statistiche` resta `None`: l'elenco delle statistiche lo chiede il
        giro delle ricette, e qui «non l'ho chiesto» si dice com'e'."""
        if self._ha is None or self._home_space is None:
            return {"errore": "la dashboard Energia si legge da Home Assistant, "
                              "e il collegamento o la casa non ci sono."}
        dashboard = await energy_dashboard(self._ha, self._home_space, self._turn_house())
        if dashboard is None:
            return {"errore": "la dashboard Energia non e' stata letta: Home Assistant "
                              "non ha risposto."}
        return {"energia": dashboard}


# La tabella degli strumenti: UNA riga per strumento. Il catalogo che il
# modello riceve, i nomi che `dispatch` accetta, i gestori, gli archivi e il
# soffitto si chiedono a lei -- erano tre tabelle scritte a mano (D-39) e
# sette domande al soffitto dentro i gestori (D-23). L'ordine e' quello del
# catalogo che il modello legge.
@dataclass(frozen=True)
class MindReading:
    """Una lettura dello strumento `mind`: chi la serve, e se accetta un
    `giorno`."""
    serve: Callable[..., Any]
    by_day: bool = False


#: Le letture dello strumento `mind`, per `cosa`. **E' la tabella del
#: parametro**: l'`enum` di `MIND_TOOL_DEF` si chiede a lei, e il gestore la
#: legge (piano della Tappa 5, Task 8, passo 5: «una riga nella tabella del
#: parametro, nessun modulo nuovo»).
MIND_READINGS: dict[str, MindReading] = {
    "scope": MindReading(ToolDispatcher._mind_scope),
    "obiettivo": MindReading(ToolDispatcher._mind_objective),
    "resoconti": MindReading(ToolDispatcher._mind_reports, by_day=True),
    "analisi": MindReading(ToolDispatcher._mind_analyses, by_day=True),
    "energia": MindReading(ToolDispatcher._mind_energy),
}

MIND_TOOL_DEF = {
    "name": "mind",
    "description": (
        "Cio' che il cervello di HIRIS guarda e ha capito, in sola lettura. "
        "`cosa`: `scope` cosa guarda, perche' e cosa ha lasciato fuori; "
        "`obiettivo` la domanda della casa; `resoconti` le misure dei giorni; "
        "`analisi` le osservazioni dell'analista; `energia` la dashboard "
        "Energia di Home Assistant."),
    "input_schema": {
        "type": "object",
        "properties": {
            "cosa": {"type": "string", "enum": list(MIND_READINGS)},
            "giorno": {"type": "string",
                       "description": "AAAA-MM-GG: un giorno solo, per resoconti e analisi."},
        },
        "required": ["cosa"],
    },
}

TOOLS: tuple[Tool, ...] = (
    # Solo la casa: la memoria serve al dettaglio di un ricordo, e quello lo
    # dichiara da se' quando manca (`_full_detail_sync`). Rifiutare «luci
    # accese» perche' l'archivio dei ricordi non e' pronto sarebbe un no a una
    # domanda che non lo tocca (review finale, M5, 30/09/2026).
    Tool(SEARCH_TOOL_DEF, ToolDispatcher._search, resources=("casa",),
         mask="amministrare", read_only=True),
    Tool(RELATED_TOOL_DEF, ToolDispatcher._related, resources=("ha",),
         read_only=True),
    # Un ricordo entra nel nucleo di ogni turno, di ogni persona, e ci resta:
    # non e' una scrittura nel proprio filo, e chi legge soltanto non la fa
    # (G83-1, giro 83; Paolo, 07/10/2026).
    Tool(REMEMBER_TOOL_DEF, ToolDispatcher._remember, resources=("casa", "memoria"),
         permissions=(Permission("comandare"),)),
    Tool(FETCH_TOOL_DEF, ToolDispatcher._recall, resources=("memoria",),
         read_only=True),
    Tool(EXECUTE_TOOL_DEF, ToolDispatcher._execute, resources=("porta",),
         permissions=(Permission("comandare"),
                      Permission("amministrare", applies=_reserved_core_service,
                                 refusal=ADMIN_SERVICES_REFUSAL))),
    Tool(PROMISE_TOOL_DEF, ToolDispatcher._promise, resources=("promesse",),
         needs_thread=True,
         permissions=(Permission("comandare", applies=_promises_an_action),)),
    Tool(AGENDA_TOOL_DEF, ToolDispatcher._list_agenda, resources=("promesse",),
         needs_thread=True, read_only=True),
    Tool(CANCEL_TOOL_DEF, ToolDispatcher._cancel, resources=("promesse",),
         needs_thread=True),
    Tool(PROPOSE_TOOL_DEF, ToolDispatcher._propose, resources=("officina",),
         mask="amministrare"),
    # La porta della configurazione ha due lati, il clic sulla pagina e
    # questo strumento: custodirne uno solo lascerebbe spalancato l'altro
    # (I-1), il piu' facile da attraversare -- basta scrivere «conferma». Lo
    # stesso gesto della pagina (`admission.ADMISSION`), dal 07/10/2026
    # `amministrare`: `costruire` aveva lo stesso valore per ogni ruolo (F-03).
    Tool(CONFIRM_TOOL_DEF, ToolDispatcher._confirm, resources=("officina",),
         permissions=(Permission("amministrare"),)),
    # Il canale, non la casa: gli errori si chiedono anche con la casa non
    # ancora caricata, e il gestore dice da se' quando gli serve.
    Tool(HISTORY_TOOL_DEF, ToolDispatcher._history, resources=("ha",),
         permissions=(Permission("amministrare", applies=_asks_admin_reads,
                                 refusal=ADMIN_READS_REFUSAL),),
         read_only=True),
    Tool(CALENDAR_TOOL_DEF, ToolDispatcher._calendar, resources=("ha",),
         read_only=True),
    # Nessun permesso, come `search` e `history` (D6 del piano): le stesse
    # cose sono gia' visibili nella pagina del cervello a chiunque entri.
    # Nessun archivio nella riga: ogni lettura dice da se' cosa le manca
    # (`_mind_missing`), e l'energia non passa dalle letture del cervello.
    Tool(MIND_TOOL_DEF, ToolDispatcher._read_mind, read_only=True),
)

# Le viste sulla tabella. Il catalogo che il modello riceve si DERIVA: un
# elenco scritto a mano accanto alla tabella sarebbe la seconda copia degli
# stessi nomi, e il primo a divergere sarebbe quello che legge il modello --
# uno strumento arrivato al modello e sconosciuto al dispatcher, il tipo di
# incoerenza che il modello non puo' ne' capire ne' aggirare.
KNOWLEDGE_TOOLS: list[dict] = [tool.definition for tool in TOOLS]
_TOOL_PER_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}


def reads_only(name: str) -> bool:
    """Lo strumento `name` legge e basta (`Tool.read_only`)? Un nome che la
    tabella non conosce -- `compute` dell'analista, `conclude` della
    promessa, un refuso del modello -- e' una scrittura: chiude per difetto."""
    tool = _TOOL_PER_NAME.get(name)
    return tool is not None and tool.read_only
