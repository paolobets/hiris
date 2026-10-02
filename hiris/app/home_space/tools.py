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

`history` passa per `home_space/house_history.py`; il genere della domanda lo
dice `genere`, un argomento esplicito. `calendar` legge ogni calendario
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
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import math
import os
import re
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import quote

from ..action.construction.advisor import STRUCTURES
from ..api.soffitto import ADMIN_READS_REFUSAL, ADMIN_SERVICES_REFUSAL, denies
from ..chat_thread import ChatThread, subject_key_for, without_thread
from ..memory.interpretation import VOCABULARY, validate
from ..memory.lookup_cache import LookupCache
from ..memory.resolver import STORE_KEY_PER_TYPE, costruisci_indice
from ..memory.store import MemoryStore
from ..proxy._sanitize import (
    sanitize_ha_free_text,
    sanitize_ha_value,
    sanitize_structure,
    sanitize_traceback,
)
from ..proxy.entity_cache import (
    automation_config_id,
    inventory_is_readable,
    unreadable_inventory_error,
)
from . import historian
from .appointments import read_appointment, sort_appointments
from .house_history import (
    ADMIN_KINDS,
    LEVELS,
    UNRESOLVED_RUNS,
    WINDOW_MAX_HOURS,
    Chosen,
    HistoryQuery,
    choose,
    empty_answer,
    error_rows,
    last_line,
    parse_query,
    run_detail,
    run_rows,
    state_rows,
    value_rows,
    value_surface,
)
from .house_history import KINDS as HISTORY_KINDS
from .house_query import KINDS, ORDERS, ROWS_MAX, parse_filters, query_house
from .queries import HA_LINK_TYPE
from .queries import related as _readable_links
from .queries import sanitized_memories as _sanitized_memories
from .queries import view as _view_detail
from .reader import HomeSpace
from .redaction import SecretSeal, home_assistant_folder
from .topology import live_mirror
from .type_judgments import TypeJudgments
from .type_vocabulary import REPO_JUDGMENTS

# I tipi di ancora che la memoria conosce, DERIVATI da
# `memory/interpretation.VOCABULARY["ancore"]` -- la fonte vera, non
# `STORE_KEY_PER_TYPE`: quella e' la mappa dei registri dell'anagrafe, un
# altro vocabolario con un altro scopo, anche quando i due elenchi
# coincidono. Ordinati perche' un frozenset non promette un ordine stabile
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


SEARCH_TOOL_DEF = {
    "name": "search",
    # La porta che interroga la casa (spec `2026-09-29-una-porta-sola-per-la-
    # casa.md` §2): dal 29/09/2026 fa anche il mestiere del dettaglio, che era
    # di un secondo strumento. La descrizione dice, in quest'ordine, a cosa
    # serve, i filtri, la profondita', cosa leggere SEMPRE nella risposta e
    # cosa non esce -- il resto (le ceste degli attributi, i comandi di
    # un'entita') lo dice la risposta stessa, non una descrizione da 13.000
    # caratteri pagata a ogni turno.
    "description": (
        "La porta che interroga la casa: per TROVARE, CONTARE, ELENCARE e "
        "FILTRARE le cose di casa, e per il DETTAGLIO di una cosa sola (con "
        "`riferimento`, l'id esatto). Tutti i filtri sono facoltativi e si "
        "combinano; senza nessuno, elenca le entita'.\n"
        "I filtri, e dove valgono:\n"
        "- `nome`: un nome, un alias o un pezzo di nome, confrontato anche per "
        "radice («rifiuti» trova «rifiuto»). Da solo cerca in TUTTI i generi.\n"
        "- `genere`: entita (predefinito), area, dispositivo, automazione, "
        "script, ricordo, integrazione.\n"
        "- `riferimento`: l'id esatto -- di entita', area, dispositivo, "
        "automazione o script; il numero di un ricordo; il dominio di "
        "un'integrazione. Da' il dettaglio completo; se non esiste, una voce "
        "`esiste: false` col `suggerimento`.\n"
        "- `tipo`: il dominio di Home Assistant (`light`, `sensor`, `switch`...); "
        "`automation` e `script` portano ad automazioni e script.\n"
        "- `stato`: `on`, `off`, `unavailable`, `unknown`, `home`...; per "
        "automazioni e script dice se sono abilitate.\n"
        "- `classe`: la classe del dispositivo (`battery`, `motion`, "
        "`temperature`...). Solo entita'.\n"
        "- `area`, `piano`: i nomi del nucleo; `area` «senza area» trova cio' "
        "che non ne ha una.\n"
        "- `integrazione`: la piattaforma (`tuya`, `reolink`...).\n"
        "- `fermo_da`, `cambiato_da`: una durata (`30d`, `2h`, `15m`); per "
        "automazioni e script conta l'ultima esecuzione.\n"
        "- `sopra`, `sotto`: un numero; solo entita' con uno stato numerico.\n"
        "- `in_esecuzione`: solo automazioni e script.\n"
        "- `includi_nascoste`, `includi_servizio`: di norma restano fuori le "
        "nascoste e le entita' di servizio (diagnostica, configurazione).\n"
        "- `ordina` (`nome`, `ultimo_cambio`, `valore`), `limite` (0-50; 0 da' "
        "solo i conti), `salta` (la pagina dopo).\n"
        "Per le aree valgono solo `nome` e `piano`; per i dispositivi `nome`, "
        "`area`, `piano`, `integrazione`. Un filtro che non vale per il genere "
        "chiesto torna un `errore`, mai un insieme intero.\n"
        "La profondita' la decide lo strumento, da quante voci trova: UNA -> "
        "`completa`, il dettaglio intero (stato, attributi, `comandi`, per "
        "un'automazione o uno script il corpo, per un'area le sue entita' -- "
        "al massimo 50, il resto nel suo `oltre`); "
        "fino a 10 -> `media`, con attributi e ultimo cambio; oltre -> "
        "`corta`, una riga per voce, al massimo 50.\n"
        "La risposta porta SEMPRE `trovate` (quante corrispondono) ed "
        "`escluse` (nascoste, servizio, disabilitate: cio' che NON ti ha "
        "dato). **Leggi sempre `escluse`**: se `escluse.nascoste` e' maggiore "
        "di zero e la domanda riguarda quelle cose, richiama con "
        "`includi_nascoste` -- «nessuna luce accesa» e' falso se le accese "
        "sono nascoste. **Un numero senza le escluse non e' un totale**: se "
        "rispondi con un conteggio e `escluse` non e' vuoto, di' anche quelle "
        "(la `nota` ti da' il totale). Se c'e' `oltre`, **prima restringi** con un filtro; "
        "scorri con `salta` solo se ti servono davvero tutte: ogni pagina e' "
        "un giro.\n"
        "Guarda `tipo` e l'id prima di concludere: «luci» puo' essere un "
        "`sensor` che le CONTA invece che una luce. Se piu' voci hanno lo "
        "stesso nome (due «Bagno» su piani diversi) scegli guardando la "
        "conversazione o chiedi a chi ti sta parlando: non prendere la prima.\n"
        "Una voce con `nascosta: true` esiste: la persona l'ha tolta dalle "
        "proprie viste in Home Assistant, non cancellata. Non proporla di tua "
        "iniziativa; se la domanda la riguarda, usala e dillo.\n"
        "Se compare `nome_dedotto` (una STRINGA, mai un booleano), quel testo "
        "E' il nome: non l'ha scelto chi vive qui, viene da cio' che Home "
        "Assistant mostra a schermo. Non concludere «senza nome».\n"
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
            "nome": {
                "type": "string",
                "description": "Un nome o un pezzo di nome (es. «bagno», «lavatrice»).",
            },
            "genere": {
                "type": "string",
                "enum": list(KINDS),
                "description": "Che cosa cercare; di norma entita.",
            },
            "riferimento": {
                "type": ["string", "integer"],
                "description": (
                    "L'id esatto della cosa, il numero di un ricordo o il "
                    "dominio di un'integrazione: da' il dettaglio completo."
                ),
            },
            "tipo": {
                "type": "string",
                "description": "Il dominio di Home Assistant: light, sensor, switch, automation...",
            },
            "stato": {
                "type": "string",
                "description": "Lo stato: on, off, unavailable, unknown, home...",
            },
            "classe": {
                "type": "string",
                "description": ("La classe del dispositivo: battery, motion, "
                                "temperature... Solo entita'."),
            },
            "area": {
                "type": "string",
                "description": "Il nome o l'id dell'area; «senza area» per cio' che non ne ha.",
            },
            "piano": {"type": "string", "description": "Il nome del piano."},
            "integrazione": {
                "type": "string",
                "description": "La piattaforma: tuya, reolink, hue...",
            },
            "fermo_da": {
                "type": "string",
                "description": "Fermo da almeno questa durata: 30d, 2h, 15m.",
            },
            "cambiato_da": {
                "type": "string",
                "description": "Cambiato entro questa durata: 30d, 2h, 15m.",
            },
            "sopra": {"type": "number", "description": "Stato numerico maggiore di."},
            "sotto": {"type": "number", "description": "Stato numerico minore di."},
            "in_esecuzione": {
                "type": "boolean",
                "description": "Solo automazioni e script in corsa (o ferme).",
            },
            "includi_nascoste": {
                "type": "boolean",
                "description": "Includi le entita' nascoste. Di norma no.",
            },
            "includi_servizio": {
                "type": "boolean",
                "description": "Includi le entita' di servizio. Di norma no.",
            },
            "ordina": {
                "type": "string",
                "enum": list(ORDERS),
                "description": "L'ordine delle voci; di norma per nome.",
            },
            "limite": {
                "type": "integer", "minimum": 0, "maximum": ROWS_MAX,
                "description": "Quante voci al massimo (0: solo i conti).",
            },
            "salta": {
                "type": "integer", "minimum": 0,
                "description": "Quante voci saltare: la pagina dopo.",
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
        "`gesto` e' «crea», «modifica» o «cancella». `dominio` e' «automation», "
        "«script» o «scene». Per modificare o cancellare serve `chiave` (l'id "
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
                       "description": "L'id o lo slug dell'oggetto da toccare "
                                      "(solo per modifica e cancella)."},
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
    "description": (
        "Cio' che e' successo in casa nel tempo: come sono cambiati gli stati, "
        "come sono andati i valori, come sono andate automazioni e script, "
        "cosa c'e' nel registro degli errori di Home Assistant. Una chiamata "
        "sola, anche per piu' cose insieme: scegli DI CHI con gli stessi "
        "filtri di `search` (`nome`, `riferimento`, `tipo`, `classe`, `area`, "
        "`piano`, `integrazione`, `includi_nascoste`, `includi_servizio`) e "
        "QUANDO con `ore` (le ultime N, predefinito 24) oppure con `da`/`a` "
        "(«oggi», «ieri» nel fuso della casa, o un istante ISO col fuso; senza "
        "`a` e' adesso) -- non tutti e due. "
        "`genere`: `stati` (predefinito) i cambi di stato; `valori` i numeri "
        "nel tempo; `esecuzioni` le partenze di automazioni e script; `errori` "
        "il registro, che accetta solo `integrazione` e `livello`. Un filtro "
        "che non vale per il genere torna `errore`, non viene ignorato. "
        "**La profondita' la decido io** dal numero di soggetti: uno -> "
        "`completa` (ogni cambio; la serie; le esecuzioni conservate, e con "
        "`esecuzione` = il `run_id` di una riga la traccia passo per passo); "
        "da 2 a 10 -> `media` (ogni cambio con l'id; una riga per serie; le "
        "ultime 3 esecuzioni di ognuna); oltre 10 -> `corta` (una riga per "
        "soggetto). "
        "Al massimo 50 `voci`: `salta` scorre le voci -- le righe nella "
        "completa e nella media, i soggetti nella corta. Con `oltre` ne restano: "
        "prima restringi (finestra piu' corta, un'area, un nome), scorri col "
        "suo `salta` solo se ti servono tutte; se `oltre` dice "
        "`salta_oltre_la_fine`, hai saltato oltre l'ultima e le voci ci sono. "
        "`trovate` non conta le escluse: `nota` dice il totale con le "
        "escluse, e se dai un numero di' anche quelle. "
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
        "Errori: `count` e' una causa sola ricomparsa N volte, non N episodi; "
        "conta per `livello`. Il registro tiene poche voci e si svuota a ogni "
        "riavvio di Home Assistant: un'assenza non prova niente. I messaggi "
        "arrivano sigillati: i segreti che conosco sono `<secret nome>`, e il "
        "testo che somiglia a un'istruzione e' filtrato. "
        "Esecuzioni ed errori solo per chi amministra Home Assistant."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "genere": {"type": "string", "enum": list(HISTORY_KINDS),
                       "description": "Cosa: stati (predefinito), valori, "
                                      "esecuzioni, errori."},
            "nome": {"type": "string",
                     "description": "Di chi, per nome o alias, come in `search`."},
            "riferimento": {"type": "string",
                            "description": "Di chi, per identificatore esatto (es. "
                                           "'sensor.camera_temperatura')."},
            "tipo": {"type": "string",
                     "description": "Il dominio di Home Assistant (light, sensor, "
                                    "automation, script...)."},
            "classe": {"type": "string",
                       "description": "La classe del dispositivo (temperature, "
                                      "energy, door...)."},
            "area": {"type": "string",
                     "description": "L'area, per nome o id; «senza area» per chi non "
                                    "ne ha."},
            "piano": {"type": "string", "description": "Il piano, per nome."},
            "integrazione": {"type": "string",
                             "description": "L'integrazione (es. zha). Per gli "
                                            "errori, chi ha scritto la voce."},
            "includi_nascoste": {"type": "boolean",
                                 "description": "Anche le entita' nascoste."},
            "includi_servizio": {"type": "boolean",
                                 "description": "Anche le entita' di configurazione e "
                                                "diagnostica."},
            "ore": {"type": "number", "maximum": WINDOW_MAX_HOURS,
                    "description": "Le ultime N ore, da adesso. Predefinito 24, al "
                                   "massimo 2160 (90 giorni). Non insieme a da/a."},
            "da": {"type": "string",
                   "description": "L'inizio: «oggi», «ieri» (la loro mezzanotte, nel "
                                  "fuso della casa) o un istante ISO col fuso."},
            "a": {"type": "string",
                  "description": "La fine: «oggi» (adesso), «ieri» (la mezzanotte che "
                                 "lo chiude) o un istante ISO col fuso. Senza, "
                                 "adesso. Vuole `da`."},
            "esecuzione": {"type": "string",
                           "description": "Solo con genere=esecuzioni e UNA "
                                          "automazione o script: il run_id di una "
                                          "riga, per la traccia passo per passo."},
            "livello": {"type": "string", "enum": list(LEVELS),
                        "description": "Solo con genere=errori."},
            "limite": {"type": "integer", "minimum": 0, "maximum": ROWS_MAX,
                       "description": "Quante voci al massimo (predefinito e tetto "
                                      "50); 0 da' solo i conteggi."},
            "salta": {"type": "integer", "minimum": 0,
                      "description": "Quante voci saltare: il valore di "
                                     "oltre.salta."},
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


CALENDAR_TOOL_DEF = {
    "name": "calendar",
    "description": (
        "**Non e' «agenda».** Quello sono gli impegni di HIRIS con se "
        "stesso; questi sono i PROSSIMI appuntamenti scritti da una persona "
        "sui calendari di questa casa -- risponde alla domanda «quali sono "
        "i miei prossimi appuntamenti?», «cosa ho in programma questa "
        "settimana?». Ogni "
        "impegno porta `titolo`, `inizio`, `fine`, `giornaliero` (vero se "
        "dura l'intera giornata) e, SOLO quando il calendario li ha scritti, "
        "`luogo`/`descrizione`; porta anche `calendario`, il NOME di chi lo "
        "tiene (es. 'Personale', 'Famiglia') -- fondendo piu' calendari in "
        "un unico elenco, sapere DA QUALE viene un impegno e' meta' della "
        "risposta. `giorni_avanti` (predefinito 30, tetto 365) e "
        "`giorni_indietro` (predefinito 0, tetto 365) scelgono la finestra: "
        "il passato resta a richiesta, perche' la domanda primaria e' sui "
        "PROSSIMI appuntamenti, non sui passati. "
        "**Un calendario dice SOLO cio' che ci e' scritto.** `impegni: []` "
        "significa che nella finestra chiesta non c'e' NESSUN impegno "
        "SEGNATO -- non che la casa sara' vuota, e non che non succedera' "
        "niente: chi ci vive puo' semplicemente non aver scritto niente sul "
        "calendario. E' NORMALE che l'elenco sia spesso vuoto: e' un fatto "
        "sul calendario, non un fatto sulla vita di chi lo tiene. "
        "**Un calendario che non riesco a leggere non sparisce.** Provo a "
        "leggere OGNI calendario di questa casa, uno per uno: quelli che "
        "riesco a leggere finiscono in `impegni`, quelli che NON riesco a "
        "leggere finiscono, per nome, in `non_letti` -- una chiave che "
        "esiste SOLO se ce n'e' almeno uno (i `non_letti` sono sempre un "
        "sottoinsieme dei `calendari_guardati` qui sotto: guardati e' "
        "«ho provato», non_letti e' «non ci sono riuscito»). Non solo "
        "Home Assistant che non risponde: anche un calendario che ha "
        "risposto bene ma con un evento che non so interpretare finisce "
        "qui, per lo stesso motivo -- non e' leggibile, qualunque sia la "
        "causa, e le cause non si confondono nel dirlo. Un elenco vuoto di "
        "impegni e un calendario NON letto sono due fatti diversi: "
        "confonderli direbbe «non hai impegni» con la sicurezza di chi ha "
        "guardato tutto, quando in realta' un calendario non e' stato "
        "letto. Se `non_letti` compare, dillo invece di tacerlo. "
        "`calendari_guardati` esce SEMPRE (anche vuoto): sono i nomi di "
        "TUTTI i calendari che ho provato a leggere in questa chiamata. "
        "Se e' vuoto, questa casa non ha nessun calendario -- non e' lo "
        "stesso fatto di «ho letto dei calendari e sono tutti vuoti»: "
        "guarda questa chiave, non solo `impegni`, prima di dire «non hai "
        "impegni». "
        "**`troncato: true` significa che almeno un calendario aveva PIU' "
        "impegni di quanti ne siano tornati** -- non concludere «non ci sono "
        "altri impegni». Non dice QUALE calendario e' stato tagliato, solo che "
        "ne e' successo almeno uno. Cio' che manca e' cio' che sta PIU' "
        "LONTANO dall'inizio della finestra chiesta -- che di solito e' "
        "ADESSO, quindi di solito manca cio' che e' piu' in la' nel futuro; "
        "ma se hai chiesto anche `giorni_indietro`, l'inizio della finestra "
        "e' nel passato, e cio' che manca potrebbe essere proprio i "
        "PROSSIMI appuntamenti, non i piu' lontani in assoluto."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "giorni_avanti": {
                "type": "number",
                "description": (
                    "Quanti giorni in avanti guardare, da adesso. "
                    "Predefinito 30, non 7: una finestra piu' corta "
                    "rischia di rispondere «niente» anche quando qualcosa "
                    "sta per arrivare. Il massimo e' 365."
                ),
            },
            "giorni_indietro": {
                "type": "number",
                "description": (
                    "Quanti giorni all'indietro guardare, da adesso. "
                    "Predefinito 0 (niente passato): usalo solo se ti viene "
                    "chiesto esplicitamente il passato. Il massimo e' 365."
                ),
            },
        },
        "required": [],
    },
}

KNOWLEDGE_TOOLS: list[dict] = [
    SEARCH_TOOL_DEF, RELATED_TOOL_DEF, REMEMBER_TOOL_DEF,
    FETCH_TOOL_DEF, EXECUTE_TOOL_DEF,
    PROMISE_TOOL_DEF, AGENDA_TOOL_DEF, CANCEL_TOOL_DEF,
    PROPOSE_TOOL_DEF, CONFIRM_TOOL_DEF,
    HISTORY_TOOL_DEF, CALENDAR_TOOL_DEF,
]

# I nomi che `dispatch()` accetta. Si DERIVANO dal catalogo qui sopra: erano
# quattro stringhe scritte a mano, cioe' un secondo elenco degli stessi nomi
# da tenere allineato -- esattamente la forma di difetto che questo ramo ha
# gia' pagato coi tre cataloghi divergenti dei trentaquattro strumenti. Con
# quelle scritte a mano, uno strumento nuovo nel catalogo sarebbe arrivato al
# modello (che legge `KNOWLEDGE_TOOLS`) e poi si sarebbe sentito
# rispondere «non e' fra quelli disponibili» dal dispatcher: il tipo di
# incoerenza che il modello non puo' ne' capire ne' aggirare.
_TOOL_NAMES = frozenset(d["name"] for d in KNOWLEDGE_TOOLS)

# Lo schema di OGNI strumento, per nome -- stessa ragione di `_TOOL_NAMES` qui
# sopra: si DERIVA dal catalogo invece di ricopiarlo. Usato da `_bad_arguments`
# per sapere, senza toccare i dodici gestori, quali argomenti uno strumento
# dichiara obbligatori (`input_schema["required"]`) e quali conosce affatto
# (`input_schema["properties"]`).
_TOOL_SCHEMA_PER_NAME = {d["name"]: d["input_schema"] for d in KNOWLEDGE_TOOLS}


def _quoted(names) -> str:
    """«a», «b», «c» -- la forma coi guillemet dei messaggi di questo modulo:
    un elenco leggibile, non un repr di lista Python."""
    return ", ".join(f"«{n}»" for n in names)


def _bad_arguments(name: str, arguments: dict[str, Any]) -> dict | None:
    """Il controllo unico sugli argomenti di uno strumento, usato da
    `ToolDispatcher.dispatch` PRIMA di chiamare qualunque gestore -- non nei
    dodici gestori, cosi' che uno strumento futuro nasca gia' protetto.

    Consuma `input_schema["required"]` e `input_schema["properties"]`, che
    ogni voce di `KNOWLEDGE_TOOLS` gia' dichiara: nessuna firma nuova, nessun
    secondo elenco da tenere allineato (la stessa ragione di `_TOOL_NAMES`).

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
    """
    schema = _TOOL_SCHEMA_PER_NAME[name]
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

    if not parts:
        return None
    return {"errore": f"«{name}»: " + "; ".join(parts) + "."}


#: I servizi del dominio `homeassistant` che Home Assistant concede a chi non
#: amministra. Verificato il 27/09/2026 su Core 2026.9.3,
#: `components/homeassistant/__init__.py`: `turn_on`, `turn_off`, `toggle`,
#: `update_entity` (e `save_persistent_states`) si registrano con
#: `hass.services.async_register`; `stop`, `restart`, `check_config`,
#: `reload_core_config`, `set_location`, `reload_custom_templates`,
#: `reload_config_entry` e `reload_all` con `async_register_admin_service`.
#: `save_persistent_states` resta fuori per decisione (fix round 1, M-1): e'
#: manutenzione del nucleo, non un comando di casa.
_HA_CORE_USER_SERVICES = frozenset({"turn_on", "turn_off", "toggle", "update_entity"})


#: Perche' il dettaglio non mostra il corpo di un'automazione a chi non amministra.
#: Verificato il 27/09/2026 su Core 2026.9.3 (fix round 1 del Task 2, L-2):
#: `automation/config` (`components/automation/__init__.py`) e'
#: `@websocket_api.require_admin`; `script/config` no, e il corpo degli
#: script resta visibile a tutti. Il nucleo della chat non porta i corpi --
#: solo il nome e se il corpo c'e' -- quindi il solo punto da chiudere e' qui.
_AUTOMATION_BODY_ADMIN_ONLY = ("Home Assistant mostra il corpo delle "
                               "automazioni solo agli amministratori: si sa "
                               "che c'e' e come si chiama, non cosa fa")

#: Quanti byte di identificatori (gia' codificati per l'URL, virgole
#: comprese) vanno in UNA richiesta a `/api/history/period`. Il server aiohttp
#: di Home Assistant, e il proxy del Supervisor che gli sta davanti, rifiutano
#: una riga di richiesta oltre 8.190 byte (`max_line_size`); il resto della
#: riga -- metodo, percorso, i due istanti, i parametri fissi -- sta sotto i
#: 200. 6.000 lascia margine anche a un percorso di base piu' lungo di
#: `/core`. Scelto, non misurato: la misura dal vivo e' la verifica
#: (30/09/2026, ~300 entita' vere superano il tetto in un pezzo solo).
_HISTORY_FILTER_MAX = 6000


def _history_chunks(entity_ids: list[str]) -> list[list[str]]:
    """Gli identificatori in pezzi che stanno ognuno sotto
    `_HISTORY_FILTER_MAX`, nell'ordine dato. Il costo di ognuno e' quello che
    `HAClient.history` gli fara' pagare: `quote(..., safe="")`, e `%2C` per la
    virgola che lo separa dal precedente. Un identificatore da solo piu' lungo
    del tetto fa un pezzo suo: rifiutarlo qui sarebbe tacerlo."""
    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0
    for ident in entity_ids:
        cost = len(quote(ident, safe=""))
        if current and size + len("%2C") + cost > _HISTORY_FILTER_MAX:
            chunks.append(current)
            current, size = [], 0
        size += cost + (len("%2C") if current else 0)
        current.append(ident)
    if current:
        chunks.append(current)
    return chunks


#: I separatori di un `chiave=valore`, delle virgolette e delle parentesi. Il
#: sigillo riconosce un segreto per impronta del valore ESATTO
#: (`redaction.SecretSeal.redact`): su un messaggio di registro intero non
#: combacia mai, perche' il segreto sta DENTRO la frase
#: («credenziali 'Zq9-...' rifiutate»).
_SEAL_NARROW_RE = re.compile(r"[\s'\"`=:,;()\[\]{}<>]+")
#: Anche i separatori di un indirizzo e di una query (`/`, `@`, `&`, `?`,
#: `#`, `|`, `\`), il punto e il `!`. Revisione del Task 7 (30/09/2026):
#: col solo elenco stretto quattro prove su un `secrets.yaml` vero passavano
#: in chiaro -- «rifiutato per Zq9-segreto-77.» (il punto a fine frase, la
#: forma piu' comune di un registro), `http://admin:hunter2@host`,
#: `token=X&y=1`, `X/retry`. Da solo pero' questo elenco spezzerebbe una
#: password che il punto o il `!` li contiene: per questo si provano tutte e
#: due le grane (`_sealed_token`).
_SEAL_BROAD_RE = re.compile(r"[\s'\"`=:,;()\[\]{}<>/&@?!.#|\\]+")
#: La punteggiatura che si toglie dai bordi di un pezzo: tutta, oppure tutta
#: tranne `!` e `?`, che in una password stanno spesso in fondo.
_SEAL_EDGES = ("'\"`.,;:!?()[]{}<>", "'\"`.,;:()[]{}<>")


def _sealed_token(token: str, seal) -> str:
    """Una parola (cio' che sta fra due spazi) col sigillo passato su ogni
    lettura plausibile di dove il segreto cominci e finisca: la parola
    intera, i pezzi fra i separatori stretti e quelli larghi, e ognuno anche
    senza la punteggiatura dei bordi. Una quindicina di impronte per parola,
    non una per ogni sottostringa: il sigillo tiene solo impronte, e cercare
    davvero una sottostringa vorrebbe il testo dei segreti in memoria.

    Il piu' lungo si sostituisce per primo: un segreto che ne contiene un
    altro non si spezza a meta'."""
    candidates = set()
    for piece in {token, *_SEAL_NARROW_RE.split(token), *_SEAL_BROAD_RE.split(token)}:
        candidates.add(piece)
        candidates.update(piece.strip(edges) for edges in _SEAL_EDGES)
    for candidate in sorted(candidates, key=len, reverse=True):
        if not candidate:
            continue
        sealed = seal.redact(candidate)
        if sealed != candidate:
            token = token.replace(candidate, sealed)
    return token


def _sealed_free_text(text, seal):
    """Il testo libero di un registro col sigillo passato tre volte: il testo
    intero, ogni riga, ogni parola (`_sealed_token`). Il prezzo e' quello gia'
    dichiarato dal sigillo: un pezzo innocente IDENTICO a un segreto viene
    oscurato. Resta fuori un segreto che contiene uno spazio, dentro una
    frase: il limite di un sigillo che tiene solo impronte, dichiarato qui e
    non taciuto.

    `seal` puo' essere `None` (un dispatcher costruito a meta' nei test del
    confine): il testo torna com'e'."""
    if seal is None or not isinstance(text, str):
        return text
    whole = seal.redact(text)
    if whole != text:
        return whole
    lines = []
    for line in text.split("\n"):
        sealed_line = seal.redact(line.strip())
        if sealed_line != line.strip():
            lines.append(sealed_line)
            continue
        lines.append(re.sub(r"\S+", lambda word: _sealed_token(word.group(0), seal), line))
    return "\n".join(lines)


class ToolDispatcher:
    """Collega i dodici strumenti agli archivi, alla porta, all'officina e al
    canale HA -- e non altro.

    Prende `home_space_store` e `memory_store` gia' costruiti dal chiamante
    (`create_app()` o l'equivalente nei test): questa classe non ne apre
    nessuno, e non li chiude -- non le appartengono.

    `dispatch()` e' l'unico punto d'ingresso e non solleva MAI: uno
    strumento sconosciuto, argomenti mancanti, o un guasto imprevisto
    diventano tutti un dizionario con la chiave `errore`, leggibile dal
    modello -- mai un'eccezione che gli spezza il turno.
    """

    def __init__(self, home_space_store: HomeSpace, memory_store: MemoryStore,
                 cache=None, actuator=None, lookup_cache: LookupCache | None = None,
                 ha=None, registry=None, agenda=None, workshop=None,
                 exchange: str | None = None, journal=None,
                 translations=None, knowledge=None,
                 judgments: TypeJudgments | None = None,
                 soffitto: dict | None = None,
                 subject: dict | None = None,
                 phrase: str | None = None,
                 thread: ChatThread | None = None) -> None:
        self._home_space = home_space_store
        # Il sigillo dei segreti si costruisce alla prima richiesta e si
        # ricorda: leggere `secrets.yaml` a ogni voce di registro sarebbe
        # un accesso al disco per riga.
        self._remembered_seal = None
        self._memory = memory_store
        # Il soffitto di chi ha aperto questo turno (invariante I-1). `None`
        # vuol dire che nessuna persona ha aperto il turno -- lo
        # schedulatore, una promessa che si sveglia, un turno del ponte che
        # non e' di chat -- e li' vale il
        # comportamento di ieri: il perimetro delle macchine e' l'invariante
        # dei canali esterni, e stringerlo qui a meta' spegnerebbe il gateway
        # senza che nessuno l'abbia deciso. **Dichiarato, non dedotto.**
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
        # Task B7: la cache del Lookup (`memory/lookup_cache.py`), di vita
        # LUNGA -- non nasce con questo dispatcher (che nasce a ogni turno,
        # vedi `handlers_chat.py::create_tool_dispatcher`) ma vive
        # accanto a `entity_cache` in `hiris/app/server.py` e arriva qui come
        # dipendenza. Default `None`: nessuna cache, `_remember` ricostruisce
        # l'indice ogni volta come faceva prima di questo
        # task -- ogni chiamante esistente (i test, e ogni altro punto del
        # prodotto che non la passa esplicitamente) non cambia comportamento.
        self._lookup_cache = lookup_cache
        # Il canale verso Home Assistant, per `related` e per cio' che dopo di
        # esso chiedera' un fatto MOMENTANEO (i legami non si archiviano --
        # vedi il docstring del modulo). In SOLA LETTURA come `_cache`: chi
        # scrive resta la porta, e questo attributo non le fa concorrenza.
        self._ha = ha
        # Il registro dei servizi (`action/registry.py::ServiceRegistry`), la
        # STESSA istanza che usa la porta -- non se ne apre un secondo, per la
        # stessa ragione di `_ha`: due registri sarebbero due opinioni
        # su cosa esiste, e potrebbero divergere. Serve a `promise` per
        # verificare un `fai` ADESSO (`_verify_now`). `None` e' legittimo e
        # NON passa da `_missing_resource` (che solleverebbe un errore
        # diverso, "l'archivio non e' caricato"): senza registro PRONTO --
        # assente o presente ma mai caricato da Home Assistant,
        # `_registry_not_ready()` -- il controllo RIFIUTA invece di tacere
        # (fix review Task 6 Rilievo 2): un `fai` mai verificato nascerebbe
        # con una promessa che dichiara "viene VERIFICATA adesso" senza
        # esserlo stata. (Il recapito scelto dal modello, che questo registro
        # verificava allo stesso modo, e' uscito con la fetta «il seguito
        # delle chat divise»: lo risolve il sistema al risveglio.)
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

    _RESOURCE_PER_TOOL: ClassVar[dict[str, tuple[str, ...]]] = {
        # Solo la casa: la memoria serve al dettaglio di un ricordo, e quello
        # lo dichiara da se' quando manca (`_full_detail_sync`). Rifiutare
        # «luci accese» perche' l'archivio dei ricordi non e' pronto sarebbe
        # un no a una domanda che non lo tocca (review finale, M5, 30/09/2026).
        "search": ("casa",),
        "related": ("ha",),
        "remember": ("casa", "memoria"), "fetch": ("memoria",),
        "execute": ("porta",),
        "promise": ("promesse",), "agenda": ("promesse",),
        "cancel": ("promesse",),
        "propose": ("officina",), "confirm": ("officina",),
        # Il canale, non la casa: gli errori si chiedono anche con la casa
        # non ancora caricata, e il gestore dice da se' quando gli serve.
        "history": ("ha",),
        "calendar": ("ha",),
    }

    def _missing_resource(self, name: str) -> str | None:
        """Quale archivio serve a questo strumento e non c'e'."""
        for which in self._RESOURCE_PER_TOOL.get(name, ()):
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
        arguments = arguments or {}
        # Gli archivi possono mancare: il chiamante puo' costruirci prima che
        # esistano. Senza questo controllo il modello riceve
        # «'NoneType' object has no attribute 'leggi'» -- un errore Python
        # travestito da risposta, mentre questo dispatcher promette messaggi
        # LEGGIBILI. Dire cosa manca e' anche l'unico modo perche' il modello
        # possa spiegarlo all'utente invece di riprovare all'infinito.
        missing = self._missing_resource(name)
        if missing is not None:
            return {"errore": f"«{name}» non e' disponibile: {missing}."}
        if name not in _TOOL_NAMES:
            # NON "non inventare nomi di tool": se il modello ha chiamato
            # questo nome, gliel'abbiamo dato NOI in un turno precedente (un
            # tool rimosso da un aggiornamento, o un refuso nostro nella
            # cronologia) -- accusarlo di essersi inventato uno strumento che
            # gli avevamo servito noi e' esattamente il difetto gia'
            # corretto una volta su questo ramo. Il messaggio resta un fatto
            # neutro: cosa esiste, non un rimprovero.
            available = ", ".join(sorted(_TOOL_NAMES))
            return {"errore": f"lo strumento «{name}» non e' fra quelli disponibili "
                              f"({available})."}
        # Task 1 di «rifiutare e importare» (§6b): un obbligatorio mancante e
        # un nome ignoto si rifiutano QUI, una volta sola per tutti e dodici
        # gli strumenti -- non nei gestori, che fino ad oggi lo facevano a
        # mano (quattro di loro) o non lo facevano affatto (un lettore
        # del tempo, uscito il 30/09/2026 con la storia, dichiarava un
        # obbligatorio e non lo controllava; un argomento sconosciuto veniva
        # ignorato in silenzio da ognuno). Vedi
        # `_bad_arguments` per le due discipline e perche' sono diverse.
        bad_arguments = _bad_arguments(name, arguments)
        if bad_arguments is not None:
            return bad_arguments
        handler = {
            "search": self._search,
            "related": self._related,
            "remember": self._remember,
            "fetch": self._recall,
            "execute": self._execute,
            "promise": self._promise,
            "agenda": self._list_agenda,
            "cancel": self._cancel,
            "propose": self._propose,
            "confirm": self._confirm,
            "history": self._history,
            "calendar": self._calendar,
        }[name]
        try:
            # `_execute`, `_related`, `_promise`, `_propose`, `_confirm`,
            # `_history`, `_calendar` e -- dal 29/09/2026 -- `_search` sono coroutine
            # (fanno rete, o -- `_promise` e `_search` -- possono scaldare il
            # registro dei servizi prima di verificarlo o di mostrarlo); gli
            # altri no. Si attende cio' che e' attendibile invece di
            # rendere `async` anche i gestori sincroni.
            occurrence = handler(arguments)
            if inspect.isawaitable(occurrence):
                occurrence = await occurrence
            return occurrence
        except Exception as error:
            # Rete di sicurezza finale: qualunque guasto imprevisto (un
            # archivio chiuso a meta', un tipo inatteso negli argomenti) si
            # dichiara qui invece di risalire -- vedi il docstring della
            # classe.
            # Minor #7 review finale: dichiararlo al MODELLO non bastava --
            # un archivio corrotto o un guasto ricorrente restava invisibile
            # all'operatore, che non ha altro modo di saperlo (il modello
            # riceve solo la stringa "errore", non uno stack). Loggato qui.
            logger.warning(
                "strumento «%s» ha sollevato %s: %s", name, type(error).__name__, error
            )
            return {"errore": f"lo strumento «{name}» ha incontrato un problema: {error}"}

    # -- search --------------------------------------------------------

    async def _search(self, arguments: dict[str, Any]) -> dict:
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
        # UNA lettura dello specchio, per le righe e per il dettaglio: due
        # letture in istanti diversi sarebbero la divergenza che `_mirror`
        # esiste per chiudere.
        mirror = self._mirror()
        mirror_loaded = mirror[6]

        def detail(kind: str, reference) -> dict:
            return self._full_detail_sync(kind, reference, mirror=mirror,
                                          translations=translations)

        response = query_house(self._home_space.read(), self._home_space.behavior(),
                               mirror[:6], filters, detail=detail,
                               unavailable=tuple(self._home_space.unavailable()))
        if "errore" in response:
            return response
        # Senza inventario leggibile ogni `stato: None` sarebbe ambiguo fra
        # «l'entita' non ha stato» e «non ho potuto guardare»: si dichiara.
        # Fix E1-③: `letto` (la lettura di QUESTA chiamata e' andata a buon
        # fine) va OR-ato con `inventory_is_readable` (cosa dichiara la cache
        # di se stessa), non sostituito. Sulla risposta e non sulla voce:
        # vale per ogni riga, a qualunque profondita'.
        if not mirror_loaded or not inventory_is_readable(self._cache):
            response["stato_non_letto"] = True
        if filters.name:
            self._declare_name_gaps(response, filters, mirror[1], mirror_loaded)
        elif filters.floor and "piani" in self._home_space.unavailable():
            # Una domanda per `piano` senza nome: col registro dei piani
            # caduto nessuna area ha un piano, e `trovate: 0` sarebbe un
            # silenzio non dichiarato (re-review della fetta, 30/09/2026).
            response["non_ho_potuto_guardare"] = [_fallen_stores_message(["piani"])]
        return response

    def _declare_name_gaps(self, response: dict, filters, reported_names: dict,
                           mirror_loaded: bool) -> None:
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
        entries = self._blind_spots(self._home_space.read(), mirror_loaded,
                                    reported_names, found_nothing=found_nothing)
        current_gap = any(not stable for _message, stable in entries)
        only_the_name = replace(filters, kind=None).only_by_name
        if (found_nothing and not any(response["escluse"].values())
                and only_the_name and not current_gap):
            response["nulla_riconosciuto"] = True
            response["suggerimento"] = _NOTHING_RECOGNIZED_SUGGESTION
        if entries:
            response["non_ho_potuto_guardare"] = [message for message, _s in entries]

    def _blind_spots(self, home_space: dict, mirror_loaded: bool,
                reported_names: dict[str, str] | None = None, *,
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
        fallen_stores = sorted(set(self._home_space.unavailable()) & _SEARCHED_STORES)
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


        unnamed = [e for e in home_space.get("entita") or []
                     if not (e.get("nome") or "").strip() and not e.get("disabilitata")]
        mirror_ok = mirror_loaded and inventory_is_readable(self._cache)
        if unnamed and not mirror_ok:
            message = (
                f"{len(unnamed)} entita' non hanno un nome nel registro di Home Assistant e "
                "lo specchio dello stato non e' leggibile: il ripiego sul nome che Home "
                "Assistant mostra non e' disponibile, quindi quelle entita' non sono "
                "cercabili per nome in questo momento.")
            entries.append((message, False))
        elif unnamed and mirror_ok:
            # Il caso PARZIALE: lo specchio e' leggibile (altrimenti il ramo
            # sopra avrebbe gia' parlato), ma per QUESTE entita' non porta un
            # friendly_name -- non sono cercabili per nome.
            unnamed_even_live = [e for e in unnamed
                               if not ((reported_names or {}).get(e["id"]) or "").strip()]
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

    def _full_detail_sync(self, kind: str, reference, *, mirror: tuple,
                          translations: dict) -> dict:
        """Il dettaglio completo di UNA cosa di casa -- quello che fino al
        29/09/2026 dava lo strumento `view`, oggi la voce di `search` quando
        l'insieme ne ha una sola (`house_query.query_house`, il suo `detail`).

        Sincrono apposta: `query_house` e' pura e lo chiama a meta' strada.
        Cio' che andava ATTESO -- il registro dei servizi, che fino all'08/09
        nessuno scaldava per chi leggeva (misurato dal vivo sulla 3.23.0: la
        chiave `comandi` mancava su tutte le entita' di una casa appena
        riavviata), e le parole degli stati -- l'ha gia' scaldato `_search`, e
        arriva qui come `translations`. Lo specchio e' la STESSA lettura delle
        righe (`mirror`), non una seconda.

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
        (state, reported_names, reported_units, reported_classes,
         reported_since_when, reported_attributes, _loaded) = mirror
        # Tutti i ricordi, non solo gli ultimi venti (il default di
        # `fetch()`): un ricordo vecchio ancorato a QUESTA cosa non deve
        # sparire dal suo stesso dettaglio solo perche' non e' fra i piu'
        # recenti -- stessa scelta di `handlers_home_space.handle_get_briefing`.
        memories = ([] if self._memory is None
                    else self._memory.fetch(limit=self._memory.count()))
        detail = _view_detail(self._home_space.read(), self._home_space.behavior(),
                              memories, state, kind, reference,
                              unavailable=tuple(self._home_space.unavailable()),
                              unread_bodies=self._home_space.unread_bodies(),
                              fallback_names=reported_names,
                              reported_units=reported_units,
                              reported_classes=reported_classes,
                              reported_since_when=reported_since_when,
                              reported_attributes=reported_attributes,
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
        if (kind == "automazione" and isinstance(detail, dict)
                and detail.get("corpo") is not None
                and self._ceiling_denies("amministrare")):
            detail = {**detail, "corpo": None,
                      "corpo_non_disponibile": _AUTOMATION_BODY_ADMIN_ONLY}
        return detail

    def _mirror(self, rows_out: list | None = None
                ) -> tuple[dict[str, str], dict[str, str], dict[str, str],
                           dict[str, str], dict[str, str], dict[str, dict], bool]:
        """Lo specchio vivo in UNA lettura:
        `(stato, nomi, unita, classi, da_quando, attributi, letto)`.

        Una lettura sola: la ricerca ha bisogno dei `friendly_name` e il
        dettaglio dello stato, e due metodi che chiamano `all_states()` a
        turno sarebbero due letture della stessa cosa in istanti diversi.

        `nomi` e' entity_id -> `friendly_name`, saltando i vuoti: la chiave
        "name" di `entity_cache._to_minimal` e' `friendly_name or ""`, e una
        stringa vuota non e' un nome, e' l'assenza di un nome.

        `classi` e' entity_id -> `device_class`, ed e' l'UNICA fonte che
        esista: il registro delle entita' non la manda affatto (vedi
        `topology.actual_class`).

        `unita` e' entity_id -> `unit_of_measurement`, saltando i vuoti, e
        arriva dalla STESSA lettura per la stessa ragione dei nomi: la
        conserva `_to_minimal` (`proxy/entity_cache.py`), e senza il modello
        riceverebbe `72` senza sapere
        se fossero gradi Celsius o Fahrenheit. Non basta il sistema di unita'
        della casa: Home Assistant converte **solo alla prima aggiunta del
        sensore**, quindi `unit_system` non descrive le entita' gia' presenti.

        `da_quando` e' entity_id -> `last_changed`, saltando i vuoti, e arriva
        dalla STESSA lettura per lo stesso motivo: senza, HIRIS saprebbe che
        in camera ci sono 22,4 gradi e non da quando. Costa un campo e zero
        chiamate a Home Assistant.

        `attributi` e' entity_id -> le ceste che
        `entity_cache.inherited_attributes` costruisce.

        `letto` e' False solo
        quando la lettura di QUESTA chiamata e' fallita davvero. Cache assente
        resta `True` -- non e' successo niente di male, e a dire che
        l'inventario non e' guardabile ci pensa `inventory_is_readable`.

        `rows_out`, se c'e', riceve le righe GREZZE della stessa lettura: la
        storia ci legge `state_class`, che lo specchio derivato non porta, e
        una seconda `all_states()` sarebbe la divergenza che questo metodo
        esiste per chiudere (revisione del Task 7, 30/09/2026)."""
        if self._cache is None or not hasattr(self._cache, "all_states"):
            return {}, {}, {}, {}, {}, {}, True
        try:
            # La lettura vera e' in `topology.live_mirror`, condivisa con chi
            # legge lo specchio da fuori dal dispatcher: qui restano solo la
            # difesa sulla cache assente e la semantica di `letto`.
            rows = self._cache.all_states()
            state, names, units, classes, since_when, attributes = live_mirror(rows)
        except Exception:
            return {}, {}, {}, {}, {}, {}, False
        if rows_out is not None:
            rows_out.extend(row for row in rows or [] if isinstance(row, dict))
        return state, names, units, classes, since_when, attributes, True

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

        # `aggiornata_il` decide sia "anagrafe letta?" sia la chiave della
        # cache sotto: letto una volta sola, nessun await fra le due letture
        # in questa funzione sincrona, quindi non possono mai disallinearsi.
        updated_at = self._home_space.updated_at()
        topology_loaded = updated_at is not None

        def _home_space_for_lookup() -> dict:
            # PIGRA apposta (fix review indipendente, Task B7): la chiave
            # basta a decidere un colpo a segno SENZA leggere l'anagrafe --
            # su un hit questa funzione non viene mai chiamata, e la lettura
            # SQL vera (+ json.loads per riga, quando l'anagrafe era su disco) non
            # si paga.
            return self._home_space.read() if topology_loaded else {}

        # Task B7, spazio "ricorda": MAI nomi di ripiego, e `aggiornata_il`
        # porta gia' la distinzione fra "anagrafe letta" e "non letta" --
        # `None` qui e un valore vero non sono mai la
        # stessa chiave, quindi l'indice della casa vuota (non letta) e quello
        # della casa piena non si confondono mai (memory/lookup_cache.py).
        if self._lookup_cache is not None:
            lookup = self._lookup_cache.get_lazy("ricorda", _home_space_for_lookup, updated_at)
        else:
            lookup = costruisci_indice(_home_space_for_lookup())
        if not topology_loaded:
            # L'anagrafe non e' mai stata letta: NESSUNA ancora si puo'
            # verificare, non solo quelle il cui registro e' caduto -- stessa
            # distinzione di `handlers_memory._unverifiable_types`.
            unverifiable_kinds = frozenset(_TETHER_TYPES)
        else:
            fallen_stores = set(self._home_space.unavailable())
            unverifiable_kinds = frozenset(
                kind for kind, key in STORE_KEY_PER_TYPE.items() if key in fallen_stores)

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
        _state, _names, reported_units, _classes, _since_when, _attributes, _loaded = self._mirror()
        cleaned, problems, corrections = validate(
            interpretation, lookup, unverifiable_kinds, reported_units)

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
        # `fetch`. Stessa funzione condivisa, un punto solo.
        return {"ricordi": _sanitized_memories(memories)}

    # -- execute -------------------------------------------------------

    async def _execute(self, arguments: dict[str, Any]) -> dict:
        """Non fa nulla: chiede alla porta.

        E' voluto. Tutta la logica -- verifica, chiamata, rilettura, registro
        -- vive in `action/actuator.py`, perche' domani lo schedulatore e il brain
        chiederanno alla STESSA porta senza passare da qui. Se un giorno questo
        metodo cresce, la logica sta migrando nel posto sbagliato.

        Le sole righe in piu' sono il soffitto (spec 2026-09-27, ruling
        R-2.10b e fix round 1, M-1), che la porta non conosce: chi ha il ruolo
        di sola lettura -- in Home Assistant il gruppo `system-read-only` --
        non comanda; e i servizi del dominio `homeassistant` che Home
        Assistant riserva agli amministratori non si chiamano per chi non lo
        e'. Il dominio e' universale per la porta (`action/verification.py`)
        e HIRIS chiama col proprio token di amministratore.
        """
        if self._ceiling_denies("comandare"):
            return {"errore": self._soffitto["perche"]}
        domain, _dot, service = str(arguments.get("servizio") or "").partition(".")
        if (domain == "homeassistant" and service not in _HA_CORE_USER_SERVICES
                and self._ceiling_denies("amministrare")):
            return {"errore": ADMIN_SERVICES_REFUSAL}
        return await self._actuator.execute(
            arguments, actor="chat", subject=self._subject)

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
        questa chiamata `_registry_not_ready()` rifiuterebbe SEMPRE, anche
        quando Home Assistant e' raggiungibile e pronto a rispondere.
        Difetto misurato dal vivo su 3.9.1: «verifica le temperature di ogni
        stanza e fra un'ora mandami il delta» rifiutato con «il registro dei
        servizi non e' ancora pronto», mentre le otto temperature erano appena
        state lette correttamente (da un'altra strada, non dal registro).

        Diversa dalla porta in un punto: qui un guasto non diventa un errore
        diverso da mostrare al modello -- degrada al rifiuto onesto gia'
        scritto in `_registry_not_ready()` ("non e' pronto"), perche' e' gia'
        la frase giusta per «non so ancora cosa questa casa sa fare»: una
        seconda frase per lo stesso fatto sarebbe un doppione.

        Senza registro (`None`, legittimo: `promise` non lo dichiara come
        archivio richiesto in `_RESOURCE_PER_TOOL`) o senza un canale HA
        vivo (`_ha` e' `None`, altrettanto legittimo per lo stesso
        motivo) non si tenta nemmeno: il registro non si puo' caricare senza
        un client a cui chiedere, e restare senza canale resta il rifiuto
        onesto di sempre -- non diventa "«promise» non e' disponibile"
        (quel messaggio e' di `_missing_resource`, per un'altra assenza:
        aggiungere "ha" a `_RESOURCE_PER_TOOL["promise"]` sarebbe
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

        from ..action.verification import verification
        from ..keeper.recipient import recipients_for

        if self._thread is None:
            return {"errore": _NO_THREAD_REFUSAL}

        verb = arguments.get("specie")
        # **Il soffitto di chi chiede vale anche per l'azione rimandata**
        # (ruling 2.7 della revisione di sicurezza): chi non puo' comandare
        # adesso non puo' farsi eseguire la stessa chiamata fra un'ora dallo
        # schedulatore, che al risveglio non ha piu' nessun soffitto da
        # guardare. Stesso `perche` di ogni altro rifiuto del soffitto. Un
        # `chiedi` resta permesso: legge e basta. Senza soffitto (`None`: i
        # percorsi interni) il comportamento e' quello di prima.
        if verb == "fai" and self._ceiling_denies("comandare"):
            return {"errore": self._soffitto["perche"]}

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
            refusal = self._verify_now(call, verification)
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
            recipients = await recipients_for(self._subject, self._ha)
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
        """
        target = (call or {}).get("bersaglio")
        if not isinstance(target, dict) or self._actuator is None:
            return None
        # Un bersaglio di sole entita' non ha niente da risolvere: il numero
        # sarebbe una copia di cio' che il modello ha gia' scritto, e al
        # risveglio non potrebbe essere cambiato.
        if set(target) <= {"entita"}:
            return None
        try:
            resolved = await self._actuator._resolve(target)
        except Exception:
            return None
        if not isinstance(resolved, dict) or resolved.get("errore"):
            return None
        found = resolved.get("entita") or []
        return len(found) if isinstance(found, list) else None

    def _list_agenda(self, arguments: dict[str, Any]) -> dict:
        """«Cosa mi hai promesso?»: la fondamenta n.4 applicata alle promesse
        -- quelle di CHI chiede, non della casa (spec 2026-09-26 §2).

        Il nome del metodo NON puo' essere `_promesse`: quell'attributo e'
        gia' l'archivio (vedi `__init__`). Due cose distinte, due nomi.
        """
        if self._thread is None:
            return {"errore": _NO_THREAD_REFUSAL}
        show_all = bool(arguments.get("tutte"))
        rows = self._agenda.list(thread=self._thread, solo_in_sospeso=not show_all)
        return {"promesse": [without_thread(r) for r in rows]}

    def _cancel(self, arguments: dict[str, Any]) -> dict:
        """Disdice una promessa di QUESTO filo. Un id di un altro filo riceve
        la stessa risposta di uno che non esiste (`AgendaStore.cancel`)."""
        import time as _time

        if self._thread is None:
            return {"errore": _NO_THREAD_REFUSAL}
        identifier = arguments.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            return {"errore": "«cancel» ha bisogno dell'`id` della promessa."}
        occurrence = self._agenda.cancel(identifier.strip(), thread=self._thread,
                                         now=_time.time())
        if "promessa" in occurrence:
            return {**occurrence, "promessa": without_thread(occurrence["promessa"])}
        return occurrence

    async def _propose(self, arguments: dict[str, Any]) -> dict:
        """Propone. Non scrive: lo fa `confirm`, e non nello stesso turno."""
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
            "frase": arguments.get("frase"),
        }
        return await self._workshop.propose(
            intent, actor="chat", exchange=self._exchange, now=_time.time(),
            thread=self._thread,
            reveal_before=not self._ceiling_denies("amministrare"))

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
        # Il soffitto (I-1): la porta della configurazione ha due lati, il clic
        # sulla pagina e questo strumento. Custodirne uno solo lascerebbe
        # spalancato l'altro -- e questo e' il piu' facile da attraversare,
        # perche' basta scrivere «conferma» in chat.
        if self._ceiling_denies("costruire"):
            return {"errore": self._soffitto["perche"]}
        occurrence = await self._workshop.apply(
            proposal_id, actor="chat", exchange=self._exchange,
            now=_time.time(), subject=self._subject,
            # B-5: il cancello sa dire «in mezzo c'e' stato un turno», non «in
            # mezzo c'e' stato un si'». La frase di questo turno va in cronaca
            # accanto all'atto, cosi' che «chi ha detto si'» abbia una
            # risposta invece di essere dedotto dal silenzio.
            confirm_phrase=self._phrase,
            # Task 7, spec §5: «confirm e' del filo». Il filo di QUESTO
            # turno, non quello della proposta -- l'officina confronta i due.
            thread=self._thread)
        # Punto 7 (residuo): `guasto_rete` e' interno (`Workshop._fallita`/
        # `_rete`) -- `handlers_constructions.py` lo toglie gia' sul percorso
        # HTTP (lo legge per scegliere 503 invece di 409, poi lo estrae dal
        # corpo). Qui, sul percorso chat, questo dizionario va DIRETTO al
        # modello: senza questa riga il flag ci arrivava integro, e «interno»
        # sarebbe stato vero da una sola delle due porte.
        occurrence.pop("guasto_rete", None)
        return occurrence

    def _verify_now(self, call: dict, verify) -> str | None:
        """Il rifiuto della verifica, o `None`. Sola lettura: non esegue niente.

        Non si risolvono i bersagli per aree o etichette: quella risoluzione
        chiede a Home Assistant e vive nella porta. Qui si verifica cio' che si
        puo' verificare senza rete -- il servizio esiste, l'entita' nominata
        esiste, i parametri appartengono a quel servizio -- che e' esattamente
        cio' che sbaglia il modello.

        Senza registro si RIFIUTA, non si tace piu' (fix review Task 6,
        Rilievo 2, deciso dal proprietario): e' la STESSA guardia di
        `action/actuator.py::_MUTE_REGISTRY` ("non so ancora cosa Home Assistant
        sa fare"), spostata al momento della promessa invece che
        dell'esecuzione -- due porte non devono rispondere in modo opposto
        alla stessa situazione. La frase e' diversa apposta: li' si sta
        eseguendo, qui si sta promettendo, e "riprova fra un momento" ha un
        senso diverso nei due casi. Tacere qui lascerebbe nascere un `fai`
        senza che il suo servizio sia mai stato verificato: `PROMISE_TOOL_DEF`
        dichiara al modello "viene VERIFICATA adesso" senza condizioni, e
        prima del cablaggio del Task 7 il registro e' SEMPRE `None` in
        produzione -- quindi il silenzio avrebbe reso quella frase falsa
        proprio ora, non in un caso limite futuro.

        Dal cablaggio del Task 7 c'e' un secondo caso, raggiungibile per la
        prima volta: all'avvio il registro esiste (non e' `None`, `server.py`
        lo costruisce sempre) ma e' ancora VUOTO -- mai caricato da Home
        Assistant. Lasciare proseguire fino a `verification()` produrrebbe «il
        dominio non esiste. Domini disponibili: .» -- la frase FALSA detta
        con sicurezza contro cui mette in guardia `action/actuator.py`
        (`_MUTE_REGISTRY`). Le due assenze raccontano lo stesso fatto («non so
        ancora cosa questa casa sa fare») e si riconoscono con lo STESSO
        criterio della porta -- si CHIEDE al registro (`domains()` vuoto), non
        si reinventa la regola in un secondo posto. Il criterio vive in
        `_registry_not_ready()` (review Task 7, Rilievo 1).

        Un terzo caso, trovato dalla review finale: uno specchio dello stato
        NON leggibile faceva tornare `None` (nessun rifiuto) invece di
        rifiutare -- la stessa dimenticanza del registro (Task 6) e del
        recapito (Task 7), sull'ultimo ingresso rimasto. Riusa la STESSA
        forma decisa li' -- si rifiuta, non si tace -- invece di scriverne
        una terza copia.
        """
        if self._registry_not_ready():
            return ("non posso ancora prometterlo: non so cosa questa casa sa "
                    "fare, perche' il registro dei servizi non e' pronto. "
                    "Riprova fra un momento.")
        states = self._state_readings()
        if not states:
            # Terza occorrenza dello stesso schema (review finale, rilievo
            # minore): il registro assente si rifiuta (Task 6), il recapito
            # non verificabile si rifiuta (Task 7), e uno specchio cieco deve
            # rifiutarsi allo stesso modo -- non tornare `None` in silenzio.
            # Prima di questo fix una `chiamata` nasceva SENZA che
            # `_verify_now` avesse potuto verificare l'entita' nominata,
            # mentre `PROMISE_TOOL_DEF` dichiara al modello, senza
            # condizioni, «viene VERIFICATA adesso». Stesso criterio di
            # `action/actuator.py::_BLIND_MIRROR` (`None` e `{}` insieme, di
            # proposito: una casa che davvero non ha nessuna entita' non ha
            # nemmeno l'entita' bersaglio, quindi non c'e' chiamata legittima
            # che questo rifiuto possa negare). Estratta in
            # `_blind_mirror_refusal()` (Task 2, R7): `_verify_comparison_targets`
            # fa la STESSA domanda, e una seconda stringa scritta a mano li'
            # sarebbe un doppione appena creato.
            return self._blind_mirror_refusal()
        verdict = verify(call, self._registry, states)
        if verdict.da_risolvere:
            return None  # bersaglio per area: lo risolvera' la porta, al momento
        return None if verdict.ok else verdict.reason

    def _blind_mirror_refusal(self) -> str:
        """Il rifiuto quando lo specchio dello stato non e' leggibile: "non
        so ancora", non un silenzio.

        Estratta (Task 2, spec R7) perche' `_verify_now` e
        `_verify_comparison_targets` fanno la STESSA domanda a
        `_state_readings()` -- una seconda stringa scritta a mano in un
        secondo posto sarebbe un doppione appena creato (fondamenta n.2),
        lo stesso rilievo gia' fatto per `_registry_not_ready`.
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
        states = self._state_readings()
        if not states:
            return self._blind_mirror_refusal()
        unknown = [str(e) for e in entities if e not in states]
        if unknown:
            return ("non posso prometterlo: {} non esiste in questa casa. "
                     "Usa «search» per trovare l'id esatto e ripeti la "
                     "richiesta.".format(", ".join(unknown)))
        return None

    def _registry_not_ready(self) -> bool:
        """«Non so ancora cosa questa casa sa fare»: il registro e' assente
        (`None`) o presente ma mai caricato da Home Assistant (`domains()`
        vuoto). Le due assenze si trattano uguali -- e' lo stesso criterio di
        `action/actuator.py::ActionActuator.execute` per la guardia `_MUTE_REGISTRY` --
        perche' senza domini non si puo' verificare NIENTE. Estratta qui
        (review Task 7, Rilievo 1) quando la interrogavano in due --
        `_verify_now` e la verifica del recapito scelto dal modello, uscita
        con la fetta «il seguito delle chat divise» -- e le due letture
        divergevano; resta una funzione perche' la domanda ha un nome.
        """
        return self._registry is None or not self._registry.domains()

    def _snapshot(self, entities: list) -> list[dict]:
        """I valori di partenza, presi ADESSO, con la loro unita'.

        Senza l'unita' e senza l'istante, «e' aumentata» non ha un termine di
        paragone e il modello se lo inventerebbe. E' la fondamenta n.1: il `72`
        che non si sa se sia Celsius o Fahrenheit.

        `stati` (da `_state_readings()`) e' la forma MINIMALE vera di
        `proxy/entity_cache.py::_to_minimal` -- non lo stato grezzo di Home
        Assistant. L'unita' vive li' nella chiave `unit` DI PRIMO LIVELLO,
        non dentro `attributes.unit_of_measurement` (quello e' HA grezzo, mai
        cio' che questo dispatcher vede): leggerla dagli attributi e' il
        difetto R6 -- l'istantanea nasceva SEMPRE senza unita' in produzione.
        `valore` invece era gia' corretto: legge `state`, che e' una chiave
        di primo livello identica in entrambe le forme.
        """
        import time as _time

        states = self._state_readings() or {}
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

    def _state_readings(self) -> dict[str, dict] | None:
        """Lo specchio dello stato vivo, GREZZO: entity_id -> `{state, attributes, ...}`.

        `_mirror()` ritorna mappe GIA' DERIVATE (nomi, unita', classi) per
        chi le vuole cosi'; qui serve invece la forma minima di
        `EntityCache.all_states()`, la stessa che legge
        `action/actuator.py::ActionActuator._states` per verificare una chiamata prima di
        eseguirla. La guardia (`inventory_is_readable`) e' la STESSA di
        `ActionActuator._states`: la regola «cache assente o mai
        caricata non e' un inventario leggibile» si paga in un posto solo,
        non in un terzo qui.

        `None` quando non si e' potuto guardare (cache assente, non caricata,
        o una lettura che solleva); non e' `{}`, che direbbe «guardato, casa
        vuota».
        """
        if not inventory_is_readable(self._cache):
            return None
        try:
            readings = self._cache.all_states()
        except Exception as error:
            logger.warning("specchio grezzo illeggibile (%s: %s)",
                           type(error).__name__, error)
            return None
        states: dict[str, dict] = {}
        for entry in readings or []:
            eid = entry.get("id") if isinstance(entry, dict) else None
            if eid:
                states[eid] = entry
        return states

    def _timezone(self) -> str | None:
        """Il fuso della casa, dalla stessa fonte del nucleo.

        `HomeSpace.reference_frame()` (`home_space/reader.py`) e' l'UNICO
        accessore: rileggere `get_config` per conto proprio qui sarebbe un
        secondo posto che sa lo stesso fatto, e i due potrebbero divergere il
        giorno in cui uno dei due cambia. Senza `home_space_store` (i test che
        costruiscono un dispatcher minimale) il fuso resta sconosciuto, e la
        promessa nasce comunque -- `fuso` e' un campo dichiarativo della
        promessa (spec §9.1), non un cancello che la blocca.
        """
        if self._home_space is None:
            return None
        return self._home_space.reference_frame().get("fuso")

    # -- il soffitto e il sigillo -----------------------------------------

    def _ceiling_denies(self, gesture: str) -> bool:
        """Il soffitto di questo turno nega questo gesto? L'unica domanda che
        gli strumenti fanno al soffitto -- la regola, sviluppo e turni senza
        persona compresi, e' `soffitto.denies`."""
        return denies(self._soffitto, gesture, self._subject)

    def _admin_reads_refusal(self) -> dict | None:
        """Il rifiuto delle letture che Home Assistant mostra ai soli
        amministratori -- dal 30/09/2026 i generi `esecuzioni` ed `errori` di
        `history` -- `None` se questo turno puo'.

        Verificato il 27/09/2026 su Core 2026.9.3: `system_log/list`
        (`components/system_log/__init__.py`), `trace/list` e `trace/get`
        (`components/trace/websocket_api.py`) sono `@websocket_api.require_admin`.
        HIRIS li chiama col proprio token di amministratore: senza questa
        domanda li leggerebbe per chiunque chatti (ruling R-2.25).
        """
        if self._ceiling_denies("amministrare"):
            return {"errore": ADMIN_READS_REFUSAL}
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
            folder = home_assistant_folder()
            self._remembered_seal = (
                SecretSeal.from_file(os.path.join(folder, "secrets.yaml"))
                if folder else SecretSeal({}, readable=False))
        return self._remembered_seal

    # -- la storia ------------------------------------------------------

    async def _history(self, arguments: dict[str, Any]) -> dict:
        """La storia della casa (spec `2026-09-30-la-storia.md`): chiama Home
        Assistant e passa cio' che ha letto a `house_history`, dove vivono la
        scelta, la profondita' e le righe.

        Dal 30/09/2026 sostituisce quattro gestori (`_trend`, `_happened`,
        `_system_log`, `_automation_trace`): quattro forme, misurate sulla
        v3.71.0 fra 3.600 e 35.000 caratteri a chiamata.

        **L'ordine dei controlli e' il contratto.** Prima gli argomenti (un
        errore si dice senza toccare niente); poi chi non amministra
        (`trace/list`, `trace/get`, `system_log/list` sono `require_admin`:
        rifiutati PRIMA di qualunque lettura, ruling R-2.25); poi la casa, che
        serve a ogni genere fuorche' agli errori.

        `choose` da' TUTTI i soggetti da leggere (vuoto solo con `limite` 0):
        la pagina si taglia dopo la lettura, dentro le funzioni delle righe
        (revisione del Task 3). Qui non si impagina niente."""
        import time as _time

        now = _time.time()
        query = parse_query(arguments, now=now, timezone=self._timezone())
        if isinstance(query, dict):
            return query
        if query.kind in ADMIN_KINDS:
            refusal = self._admin_reads_refusal()
            if refusal is not None:
                return refusal
        if query.kind == "errori":
            answer = await self._ha.system_log()
            if not isinstance(answer.get("voci"), list):
                return {"errore": answer.get("errore",
                                             "il registro di Home Assistant non ha risposto")}
            return error_rows(query, self._sealed_log(answer["voci"]))
        if self._home_space is None:
            return {"errore": "`history` non e' disponibile: la conoscenza della casa "
                              "non e' ancora stata caricata."}
        # UNA lettura dello specchio e UNA della casa per tutta la chiamata:
        # le righe grezze servono ai valori (`state_class`), la casa alle
        # chiavi degli script (revisione del Task 7).
        rows: list[dict] = []
        mirror = self._mirror(rows_out=rows)
        home = self._home_space.read()
        chosen = choose(query, home, self._home_space.behavior(),
                        mirror[:6], unavailable=tuple(self._home_space.unavailable()),
                        now=now)
        if isinstance(chosen, dict):
            return chosen
        if not chosen.subjects:
            return empty_answer(query, chosen)
        if query.kind == "esecuzioni":
            return await self._run_history(query, chosen, home)
        if query.kind == "valori":
            # La stessa guardia di `_state_readings`: da un inventario non
            # leggibile non si prende nemmeno lo `state_class`.
            readable = inventory_is_readable(self._cache)
            state_classes = {row.get("id"): row.get("state_class")
                             for row in rows if readable}
            response = await self._value_history(query, chosen, mirror, state_classes)
        else:
            response = await self._state_history(query, chosen, mirror)
        # Come in `search`: senza specchio leggibile lo stato di adesso e
        # l'unita' sarebbero `None` ambigui fra «non c'e'» e «non ho guardato».
        if "errore" not in response and (not mirror[6]
                                         or not inventory_is_readable(self._cache)):
            response["stato_non_letto"] = True
        return response

    async def _read_history(self, entity_ids: list[str], query: HistoryQuery) -> dict:
        """Lo storico di tutti i soggetti, A PEZZI (`_history_chunks`), uniti:
        `{"serie", "troncato"}` o `{"errore"}`.

        **Perche' a pezzi** (30/09/2026): `HAClient.history` mette gli
        identificatori nell'URL di `/api/history/period`, e con ~300 entita'
        vere la riga di richiesta supera gli 8.190 byte che il server aiohttp
        di Home Assistant (e del Supervisor) accetta. Un pezzo solo non e'
        una risposta lenta: e' nessuna risposta.

        `troncato` e' vero se Home Assistant ha tagliato in ALMENO un pezzo:
        il taglio e' per entita' (`MAX_HISTORY_POINTS`), e un pezzo non lo
        cambia. Un pezzo che non risponde e' un `errore` di tutti: una
        risposta con le serie di meta' casa si leggerebbe «l'altra meta' non
        e' cambiata» (Review Focus 5).

        Gli istanti passano col loro ISO intero, secondi e microsecondi: la
        finestra delle righe (`dal`, con un secondo di scarto) e' calcolata
        sugli stessi."""
        ha = self._ha
        start, end = query.start.isoformat(), query.end.isoformat()
        answers = await asyncio.gather(*(ha.history(chunk, start, end)
                                         for chunk in _history_chunks(entity_ids)))
        series: dict[str, list[dict]] = {}
        truncated = False
        for answer in answers:
            if not isinstance(answer, dict) or "serie" not in answer:
                return {"errore": (answer or {}).get(
                    "errore", "lo storico di Home Assistant non ha risposto")}
            series.update(answer["serie"])
            truncated = truncated or bool(answer.get("troncato"))
        return {"serie": series, "troncato": truncated}

    async def _state_history(self, query: HistoryQuery, chosen: Chosen,
                             mirror: tuple) -> dict:
        """Gli stati, dallo storico: le serie di tutti i soggetti, con la
        finestra esplicita («ieri» incluso). Il diario di Home Assistant non si
        usa piu': sa solo «N ore da adesso», un'entita' alla volta, e non
        registra i sensori numerici (decisione del piano, 30/09/2026)."""
        answer = await self._read_history([s.ident for s in chosen.subjects], query)
        if "errore" in answer:
            return answer
        return state_rows(query, chosen, answer["serie"], truncated=answer["troncato"],
                          acts=self._journal_acts(query), current=mirror[0])

    async def _value_history(self, query: HistoryQuery, chosen: Chosen,
                             mirror: tuple, known_classes: dict[str, str | None]) -> dict:
        """I valori: lo `state_class` dallo specchio decide la superficie
        (chiederlo al modello sarebbe chiedergli un fatto che abbiamo noi, spec
        «la storia» §3.1), e ogni superficie e' UNA lettura per tutte le serie
        che la usano. `known_classes` viene dalla STESSA lettura dello specchio
        di `mirror` (revisione del Task 7: una seconda `all_states()` poteva
        dare un'altra casa).

        `attributes` sono le ceste dello specchio (`mirror[5]`) com'erano:
        `value_rows` ci guarda se un `total` ha `last_reset` (revisione del
        Task 4)."""
        state_classes = {s.ident: known_classes.get(s.ident) for s in chosen.subjects}
        surfaces = {ident: value_surface(query, state_class)
                    for ident, state_class in state_classes.items()}
        detail_ids = [ident for ident, surface in surfaces.items() if surface == "dettaglio"]
        band_ids = [ident for ident, surface in surfaces.items() if surface == "oraria"]
        detail = (await self._read_history(detail_ids, query) if detail_ids
                  else {"serie": {}, "troncato": False})
        if "errore" in detail:
            return detail
        bands = (await self._ha.hourly_statistics(
            band_ids, query.start.isoformat(), query.end.isoformat()) if band_ids
            else {"serie": {}})
        if not isinstance(bands, dict) or "serie" not in bands:
            return {"errore": (bands or {}).get("errore", "Home Assistant non ha risposto")}
        return value_rows(query, chosen, detail=detail["serie"], bands=bands["serie"],
                          truncated=detail["troncato"], surfaces=surfaces,
                          units=mirror[2], state_classes=state_classes,
                          attributes=mirror[5])

    def _run_key(self, ident: str, registry: dict[str, dict]) -> tuple[str, str] | None:
        """La chiave con cui Home Assistant conserva le esecuzioni di `ident`,
        o `None` se non si risolve (e allora non si chiede: `trace/list` con
        una chiave sconosciuta torna `[]`, che si leggerebbe «mai partita» --
        docstring di `HAClient.traces`).

        - Un'automazione: l'id della CONFIGURAZIONE, dallo specchio
          (`automation_config_id`, la stessa risoluzione del vecchio
          `_automation_trace`). Una YAML senza `id:` non ne ha: `None`.
        - Uno script: la chiave di configurazione, che Home Assistant usa come
          `unique_id` e da cui fa l'`entity_id` (`script.<chiave>`, verificato
          alla fonte nel Task 6). Si prende l'`unique_id` del registro, perche'
          un'entita' RINOMINATA cambia l'`object_id` e non la chiave; senza
          voce di registro non c'e' rinomina possibile, e l'`object_id` E' la
          chiave."""
        domain, _, object_id = ident.partition(".")
        if domain == "automation":
            config_id = automation_config_id(self._cache, ident)
            return ("automation", config_id) if config_id else None
        unique_id = (registry.get(ident) or {}).get("unique_id")
        key = unique_id or object_id
        return ("script", str(key)) if key else None

    async def _run_history(self, query: HistoryQuery, chosen: Chosen,
                           home: dict) -> dict:
        """Le esecuzioni: la chiave di Home Assistant di ogni soggetto
        (`_run_key`), UNA raffica per tutti (`HAClient.traces`), le righe da
        `house_history`. Le chiavi irrisolte non si chiedono: vanno in
        `non_letti` dalle righe (Review Focus 4).

        **Senza inventario leggibile non si risolve nessuna automazione, e lo
        si dice prima**: «non trovo quell'automazione» su una casa non
        guardata darebbe la colpa all'identificatore (Task 6 di «le tracce e il
        log»).

        **Tutte e due le strade passano dal confine** (reperto B-1, 22/09/2026):
        `config` porta i segreti gia' risolti da Home Assistant, e l'innesco e'
        testo che scrive un dispositivo di rete."""
        if any(s.ident.startswith("automation.") for s in chosen.subjects):
            fault = unreadable_inventory_error(self._cache)
            if fault is not None:
                return {"errore": fault["error"]}
        # `home` e' la casa che `choose` ha gia' letto: la stessa, non una
        # seconda lettura.
        registry = {e.get("id"): e for e in home.get("entita") or []}
        keys = {s.ident: self._run_key(s.ident, registry) for s in chosen.subjects}
        ha = self._ha
        seal = self._seal()
        if query.run_id is not None:
            subject = chosen.subjects[0]
            key = keys[subject.ident]
            if key is None:
                return {"errore": f"«{subject.ident}»: {UNRESOLVED_RUNS}."}
            answer = await ha.trace(key[0], key[1], query.run_id)
            if not isinstance(answer, dict) or "traccia" not in answer:
                return {"errore": (answer or {}).get("errore",
                                                     "Home Assistant non ha risposto")}
            return run_detail(query, chosen,
                              sanitize_structure(answer["traccia"], seal=seal))
        wanted = [key for key in keys.values() if key is not None]
        answer = (await ha.traces(wanted)) if wanted else {"tracce": {}, "non_letti": {}}
        if not isinstance(answer, dict) or not isinstance(answer.get("tracce"), dict):
            return {"errore": (answer or {}).get("errore", "Home Assistant non ha risposto")}
        traces = {name: sanitize_structure(runs, seal=seal)
                  for name, runs in answer["tracce"].items()}
        return run_rows(query, chosen, traces=traces,
                        keys={ident: (f"{key[0]}.{key[1]}" if key else None)
                              for ident, key in keys.items()},
                        unread=answer.get("non_letti") or {})

    def _sealed_log(self, entries: list) -> list[dict]:
        """Le voci del registro, sigillate e filtrate PRIMA di diventare righe
        (reperto B-1, 22/09/2026): `message` ed `exception` arrivano da un
        componente qualunque, anche di terze parti.

        **Anche `exception` passa dal sigillo dei segreti**: col solo
        `sanitize_traceback`, una password
        rifiutata scritta nel messaggio dell'eccezione arriverebbe al fornitore
        del modello. Il sigillo guarda il testo PEZZO PER PEZZO
        (`_sealed_free_text`), perche' un segreto in un registro sta dentro una
        frase. Poi `sanitize_traceback` (il filtro delle istruzioni e il
        tetto).

        **Dell'eccezione si sigilla solo l'ultima riga** (revisione finale
        della fetta, M-3, 30/09/2026): `error_rows` porta solo quella
        (`house_history.last_line`, la stessa regola, importata), e sigillare
        parola per parola tutta la traccia costava una quindicina di impronte
        a parola per righe che non arrivano mai al modello. Le righe prima
        non si sigillano perche' si BUTTANO: la sicurezza e' la stessa."""
        seal = self._seal()
        sealed = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            plain = {key: value for key, value in entry.items() if key != "exception"}
            if isinstance(plain.get("message"), list):
                plain["message"] = [_sealed_free_text(m, seal) for m in plain["message"]]
            elif "message" in plain:
                plain["message"] = _sealed_free_text(plain["message"], seal)
            clean = sanitize_structure(plain, seal=seal)
            tail = last_line(entry["exception"]) if entry.get("exception") else None
            if tail is not None:
                clean["exception"] = sanitize_traceback(_sealed_free_text(tail, seal))
            sealed.append(clean)
        return sealed

    def _journal_acts(self, query: HistoryQuery) -> list[dict] | None:
        """Gli atti di HIRIS nella finestra, per dire «per mano di HIRIS».
        `None` -- non `[]` -- quando la cronaca non c'e' o non risponde: «non
        l'ha fatto HIRIS» e «non ho potuto guardare» hanno due facce diverse
        (fix F3 dell'onda finale del diario, 25/08/2026)."""
        if self._journal is None:
            return None
        try:
            return self._journal.list(from_ts=query.start.timestamp(),
                                      to_ts=query.end.timestamp())
        except Exception as error:
            logger.warning("cronaca illeggibile durante `history` (%s: %s)",
                           type(error).__name__, error)
            return None

    # -- i calendari ------------------------------------------------------

    async def _calendar(self, arguments: dict[str, Any]) -> dict:
        """I prossimi appuntamenti, fusi da OGNI calendario di questa casa.

        **Il cuore della fetta «i calendari»: la leggibilita' si verifica
        LEGGENDO, mai dallo stato.** Un calendario rotto e uno senza impegni
        hanno lo STESSO stato `off` in Home Assistant e tornerebbero lo
        STESSO elenco vuoto -- solo un tentativo di lettura li distingue.
        Percio' questo metodo prende l'elenco dei calendari (Task 1,
        `HAClient.calendars()`) e prova a leggere CIASCUNO (Task 1,
        `HAClient.calendar_events()`), uno per uno: nessun elenco dichiarato
        di calendari ammessi, nessuna decisione presa dallo stato. Un
        calendario che fallisce NON sparisce in silenzio: il suo `name`
        finisce in `non_letti`, che esce SOLO se c'e' almeno un calendario
        illeggibile -- se sparisse, «non hai impegni» sarebbe una bugia detta
        con la sicurezza di chi ha guardato tutto, ed e' il difetto che la
        fetta precedente («le tracce e il log») ha trovato tre volte.

        **Se l'elenco dei calendari stesso non arriva**, non c'e' niente da
        provare a leggere: si propaga il suo `errore` cosi' com'e' (un
        passthrough puro).

        **`calendari_guardati` esce SEMPRE, anche vuoto -- a differenza di
        `non_letti`/`troncato`, che tacciono quando non hanno niente da
        dire.** Senza di lui, zero calendari e due calendari letti e
        VUOTI sono indistinguibili: entrambi tornerebbero `{"impegni": []}`,
        e il modello direbbe «non hai impegni segnati» quando la verita'
        potrebbe essere «questa casa non ha calendari». E' la PROVA di cosa
        e' stato guardato, non un dato su cosa c'e' scritto: senza di essa
        la risposta non e' verificabile, quindi non e' condizionale come
        gli altri due.

        **Il fuso e' UNO SOLO, quello del dispatcher** (`self._timezone()`,
        `ToolDispatcher._timezone()` qui sopra, la stessa fonte di `_history`
        -- non se ne apre una seconda): serve due volte, una per calcolare `now` con
        `historian.home_space_zone` (nessun doppione: e' la stessa funzione
        che gestisce gia' un fuso non riconosciuto con un avviso e il
        ripiego su UTC) e una passata a `read_appointment` per ogni evento.
        Fondere impegni letti con fusi DIVERSI romperebbe l'ordinamento
        lessicografico di `sort_appointments` -- non succede, perche' il
        fuso e' unico per questa chiamata, ma e' il presupposto su cui quella
        fusione poggia, e va dichiarato invece di dato per scontato.

        **Il tetto sul testo libero vive QUI, non nel client.**
        `HAClient.calendar_events()` lascia `summary`/`description`/
        `location` grezzi apposta (il suo docstring lo dice: nessun
        consumatore prima di questo strumento) -- e' questo il punto in cui
        quel testo, scritto da una persona in un calendario condiviso, entra
        DAVVERO in un prompt. `titolo`/`luogo`/`descrizione` passano da
        `sanitize_ha_free_text`, la stessa strada dei fratelli (`motivo` di
        un'integrazione rotta), non una seconda. **Il NOME del calendario passa da
        `sanitize_ha_value`** (non `sanitize_ha_free_text`: e' un
        `friendly_name`, la stessa forma di `nome` per le altre entita', non testo
        libero senza tetto HA) -- e' `state.name` di
        `HAClient.calendars()`, scelto da una persona e potenzialmente
        condiviso (un Google Calendar puo' esserlo), quindi un vettore di
        testo iniettato quanto `summary`/`description`/`location`: sanificare
        tre campi su quattro e lasciare il quarto grezzo sarebbe la stessa
        fuga che l'audit di questo prodotto ha gia' pagato altrove
        (L1-sicurezza.md). Sanificato UNA volta, prima di finire sia in
        `calendario` sia in `non_letti` -- non due sanificazioni per due
        destinazioni dello stesso valore.

        **Ogni impegno porta `calendario`**, il nome (non l'`entity_id`) del
        calendario da cui viene: fondendo «Personale» e «Famiglia» in un
        unico elenco, sapere DA QUALE viene un impegno e' meta' della
        risposta -- perderlo fondendo prima di annotarlo sarebbe
        un'informazione che avevamo in mano e abbiamo buttato via.

        **`troncato` esce SOLO se almeno un calendario lo ha dichiarato**
        (`HAClient.calendar_events`, `MAX_CALENDAR_EVENTS`): un elenco
        tagliato non deve poter sembrare completo, stessa legge del client
        che lo genera -- propagarla in silenzio sarebbe ricreare lo stesso
        difetto un livello piu' in alto. Non dice quale calendario (vedi la
        `description` dello strumento).

        **Un evento che non si sa interpretare affonda il SUO calendario,
        non tutti quanti.** `read_appointment` puo' sollevare (un evento
        senza ne' `start.date` ne' `start.dateTime`, per esempio): senza una
        guardia qui, quell'eccezione risalirebbe fino alla rete di
        sicurezza di `dispatch`, e la risposta perderebbe INSIEME gli
        impegni gia' letti di questo calendario e quelli di ogni altro
        calendario gia' letto bene in questo stesso giro -- il guasto di
        UNO che costa il silenzio su TUTTI, l'esatto difetto opposto a
        quello che questa fetta cura. Un calendario il cui evento non si sa
        interpretare finisce quindi in `non_letti` come uno che non
        risponde -- e i suoi impegni GIA' raccolti in questo giro si
        scartano: un elenco parziale che si finge completo e' peggio di un
        elenco assente, la stessa legge di `add_label_to` in
        `proxy/ha_client.py` («non ho letto» non e' «non ce n'erano»).
        """
        import time as _time

        ahead = _clamp_days(arguments.get("giorni_avanti"),
                            default=DEFAULT_CALENDAR_DAYS_AHEAD,
                            ceiling=MAX_CALENDAR_DAYS_AHEAD)
        behind = _clamp_days(arguments.get("giorni_indietro"),
                             default=0, ceiling=MAX_CALENDAR_DAYS_BACK)
        ha = self._ha
        listing = await ha.calendars()
        if "errore" in listing:
            return listing
        calendars = listing.get("calendari")
        calendars = calendars if isinstance(calendars, list) else []

        timezone = self._timezone()
        zone = historian.home_space_zone(timezone)
        now = datetime.fromtimestamp(_time.time(), tz=zone)
        start = (now - timedelta(days=behind)).isoformat()
        end = (now + timedelta(days=ahead)).isoformat()

        appointments: list[dict] = []
        examined: list[str] = []
        unreadable: list[str] = []
        truncated = False
        for entry in calendars:
            if not isinstance(entry, dict):
                continue
            entity_id = entry.get("entity_id")
            if not entity_id:
                continue
            name = sanitize_ha_value(entry.get("name") or entity_id)
            examined.append(name)
            events = await ha.calendar_events(entity_id, start, end)
            if "errore" in events:
                unreadable.append(name)
                continue
            if events.get("troncato"):
                # Non gestito, DICHIARATO: se questo STESSO calendario viene
                # anche scartato qui sotto (un evento che non si sa
                # interpretare, `unreadable_event`), `truncated` resta vero
                # ma i suoi impegni finiscono comunque in `non_letti`, non in
                # `impegni` -- `troncato: true` sopravvivrebbe su un elenco
                # che non contiene piu' nessun impegno di QUESTO calendario.
                # Serve >MAX_CALENDAR_EVENTS eventi E un evento malformato
                # nello stesso calendario per innescarlo: visto, deciso di
                # non trattarlo (il caso e' cosi' raro da non giustificare
                # il costo di un secondo stato "troncato ma poi scartato").
                truncated = True
            calendar_appointments: list[dict] = []
            unreadable_event = False
            for raw_event in events.get("eventi") or []:
                try:
                    appointment = read_appointment(raw_event, timezone=timezone)
                except Exception as error:
                    logger.warning(
                        "calendario «%s»: un evento non si sa interpretare "
                        "(%s: %s) -- l'intero calendario finisce in non_letti",
                        name, type(error).__name__, error)
                    unreadable_event = True
                    break
                appointment["titolo"] = sanitize_ha_free_text(appointment["titolo"])
                if "luogo" in appointment:
                    appointment["luogo"] = sanitize_ha_free_text(appointment["luogo"])
                if "descrizione" in appointment:
                    appointment["descrizione"] = sanitize_ha_free_text(
                        appointment["descrizione"])
                appointment["calendario"] = name
                calendar_appointments.append(appointment)
            if unreadable_event:
                unreadable.append(name)
                continue
            appointments.extend(calendar_appointments)

        result: dict = {"impegni": sort_appointments(appointments),
                        "calendari_guardati": examined}
        if unreadable:
            result["non_letti"] = unreadable
        if truncated:
            result["troncato"] = True
        return result
