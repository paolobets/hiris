"""Gli strumenti della chat -- da trentaquattro a cinque.

Il modello riceveva un catalogo di trentaquattro strumenti, che esisteva in
TRE copie divergenti (claude_runner.py, e altre due -- vedi
docs/design/2026-08-05-la-conoscenza-di-hiris.md), e ogni azione passava da
un semaforo che di fabbrica negava tutto in silenzio. Il catalogo dei
trentaquattro e il semaforo sono usciti per intero (fetta E2 Task 8 "escono
i trentaquattro"; fetta E3 Task 7 "esce la Sentinella intera, e il semaforo
che la E2 le aveva promesso") -- oggi non esistono piu' in nessuna forma.

Qui il modello ne riceveva SEI, dalla fetta «lo schedulatore» (Task 6) ne
riceve NOVE, e dalla fetta «costruire» (Task 9) ne riceve UNDICI. Cinque
leggono e ricordano; `esegui` fa succedere qualcosa in casa SUBITO -- ed e'
l'unico strumento che scrive nella casa (i servizi, non la configurazione);
`costruisci` e `conferma`, in coppia, sono l'unica strada che scrive
CONFIGURAZIONE -- automazioni, script, scene -- e lo fanno in due tempi
apposta (vedi piu' sotto). Per un tratto della 2.0
questo modulo ne offriva quattro soli e diceva «la chat CONOSCE, non
agisce»: era vero allora, non lo e' piu' dalla fetta «comandare», che ha
ridato l'azione al prodotto con un progetto proprio, dopo che la conoscenza
si era fatta solida. La differenza fra i quattro e il quinto non e' di
importanza ma di verso: i quattro LEGGONO gli archivi e lo specchio dello
stato, `esegui` SCRIVE -- e scrive per una sola strada, la porta
(`azione/porta.py`), che verifica prima e rilegge dopo.

    cerca    -- trova qualcosa per nome o alias, dichiarando le ambiguita'
    guarda   -- il dettaglio di una cosa: un'area, un'entita', un'automazione
                col suo corpo, un ricordo
    legami   -- chi tocca questa cosa, secondo Home Assistant
    ricorda  -- salva cio' che l'utente ha detto, con le ancore alla casa
    richiama -- i ricordi che riguardano una parte della casa
    esegui   -- chiama un servizio di Home Assistant, verificato prima e
                riletto dopo: l'unico strumento che tocca la casa

Tre vengono dallo Schedulatore (`schedulatore/`, spec §9.1) e fanno nascere,
leggere e disdire una PROMESSA -- «alle 17 accendi lo studio», «fra un'ora
dimmi se e' aumentata»: qualcosa da fare o da guardare piu' tardi, non adesso.
La differenza con `esegui` non e' di importanza ma di QUANDO: `esegui` agisce
ora, `prometti` mette da parte un'azione o una domanda per un istante futuro,
e tutto cio' che si puo' verificare contro questa installazione (il servizio
esiste, l'entita' esiste, il canale di notifica esiste) si verifica ALLA
NASCITA, non al momento di mantenerla -- vedi `DispatcherStrumenti._prometti`.

    prometti -- mette da parte un `fai` (verificato subito) o un `chiedi`
                (con l'istantanea di partenza) per un istante futuro
    promesse -- cosa e' ancora in sospeso, o com'e' andata
    disdici  -- annulla una promessa non ancora mantenuta

Gli ultimi due vengono dalla fetta «costruire» (spec
`docs/design/2026-08-22-costruire-in-home-assistant.md`) e scrivono
CONFIGURAZIONE -- non un servizio, non uno stato: un'automazione, uno script
o una scena che prima non esisteva, o che smette di esistere. La differenza
con `esegui` non e' di importanza ma di NATURA: `esegui` chiama qualcosa che
gia' esiste, questi due fanno esistere o smettere di esistere qualcosa. Ed e'
per questo che sono DUE e non uno: `costruisci` compone e fa validare contro
QUESTA casa (mai uno YAML scritto a mano), `conferma` scrive -- e in mezzo
deve starci un umano, riconosciuto dal TURNO e non da un campo che il modello
potrebbe compilare da solo. Vedi `azione/costruzione/officina.py` per il
giro intero e la guardia.

    costruisci -- propone (crea, modifica, cancella): non scrive, restituisce
                  un'anteprima con un `proposta_id`
    conferma   -- applica una proposta, in un turno diverso da quello che
                  l'ha creata

**Perche' `legami` e' uno strumento e non un campo di `guarda`.** E' la
decisione di questa fetta, e ha quattro ragioni che tirano tutte dalla stessa
parte.

1. **I legami sono MOMENTANEI, e non vanno in archivio.** Sono la stessa
   sostanza di `state`, tenuto fuori dal sistema di riferimento per iscritto
   (`casa/anagrafe.sistema_di_riferimento`): «in un archivio che si rilegge
   di rado mentirebbe poche ore dopo, ed e' peggio che non saperlo». Un'
   automazione nuova cambia i legami di una luce nell'istante in cui viene
   salvata. Quindi si CHIEDONO quando servono, e non si salvano da nessuna
   parte: ne' in `casa.db`, ne' nell'anagrafe, ne' nel digesto del nucleo.
2. **`guarda` e' pura e non fa I/O** (vedi il suo docstring in `domande.py`).
   Per infilarci i legami bisognerebbe che `_guarda` facesse un giro
   WebSocket PRIMA di ogni chiamata -- anche per `guarda("ricordo", 3)`, che
   con Home Assistant non c'entra nulla. Un costo di rete pagato da ogni
   domanda per servirne una.
3. **Sono due domande, non due campi dello stesso fatto.** `guarda` porta il
   CORPO (cosa fa quell'automazione, letto dai file); `legami` porta i
   LEGAMI (chi nomina questa entita', calcolato da Home Assistant su tutto
   cio' che ha caricato). Il piano della fetta lo dice in chiaro: confonderli
   rifarebbe la confusione fra «dichiarato» e «dedotto» che questo progetto
   paga da sempre. Due risposte separate sono cio' che li tiene distinti.
4. **Il guasto avrebbe due padroni.** `guarda` promette `esiste`, letto dagli
   archivi. Un legame non letto e' il guasto di un ALTRO canale: dentro
   `guarda` diventerebbe una chiave d'errore accanto a un `esiste: true`, e
   il modello non saprebbe a quale delle due domande si riferisce. Separati,
   ciascuno dichiara il proprio -- e `legami` dichiara il suo con un
   `errore`, mai con un elenco vuoto.

`ricorda` e' il motivo per cui questo modulo esiste: l'utente aveva scritto
in chat *"d'inverno il soggiorno ideale e' 19.5"*, e HIRIS aveva risposto
"preso nota" -- SENZA salvare niente, perche' il vecchio dispatcher non
chiamava mai `ArchivioMemoria.ricorda()`. Qui sotto, `ricorda` salva davvero
(vedi `DispatcherStrumenti._ricorda`).

Le due funzioni pure che fanno il lavoro vero -- `cerca()` e `guarda()` --
vivono gia' in `domande.py`, e non si riscrivono qui: `DispatcherStrumenti`
e' solo il punto che le collega agli archivi (`casa/archivio.py`,
`memoria/archivio.py`) e all'indice (`memoria/riconoscitore.py`), nella
forma che il modello puo' chiamare.

`dispatch()` non solleva MAI: restituisce sempre un dizionario, e in caso di
guasto una chiave `errore` leggibile dal modello -- un'eccezione che risale
fino al runner gli spezzerebbe il turno, ed e' esattamente il tipo di
silenzio (una risposta persa invece di una dichiarata) che questo ramo ha
gia' pagato piu' volte in altri moduli.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any

from .anagrafe import specchio_vivo
from .archivio import ArchivioCasa
from .domande import TIPO_LEGAME_HA
from .domande import cerca as _cerca_candidati
from .domande import guarda as _guarda_dettaglio
from .domande import legami as _legami_leggibili
from ..memoria.archivio import ArchivioMemoria
from ..proxy.entity_cache import inventario_leggibile
from ..memoria.cache_indice import CacheIndice
from ..memoria.interpretazione import VOCABOLARIO, valida
from ..memoria.riconoscitore import CHIAVE_ARCHIVIO_PER_TIPO, costruisci_indice

# I tipi di ancora che la memoria conosce, DERIVATI da
# `memoria/interpretazione.VOCABOLARIO["ancore"]` -- la fonte vera, non
# `CHIAVE_ARCHIVIO_PER_TIPO`. Ordinati (come fa gia' `interpretazione.py`
# per il proprio messaggio d'errore) perche' un frozenset non promette un
# ordine stabile fra due letture, ed e' l'ordine in cui `richiama` cerca
# quando il modello non specifica un `tipo` -- vedi `_richiama`.
#
# T7 (R2): prima di questo task le due fonti coincidevano per coincidenza
# (`_ARCHIVI` aveva solo i tre tipi che sono anche ancore valide), e
# derivare da `CHIAVE_ARCHIVIO_PER_TIPO` sembrava innocuo. Da quando
# `_ARCHIVI` include anche "piano" -- un registro dell'anagrafe vero, ma
# NON un tipo di ancora che `ricorda` possa mai scrivere -- le due cose
# sono tornate a essere quello che sono sempre state: due vocabolari
# diversi con scopi diversi. Se fossero rimaste legate, `richiama`
# avrebbe accettato silenziosamente `tipo="piano"` (nessun errore, solo
# una lista di ricordi sempre vuota, perche' nessuna ancora di quel tipo
# puo' esistere) al posto del messaggio che insegna i tipi validi -- lo
# stesso genere di secondo vocabolario silenzioso che R9 denuncia altrove.
_TIPI_ANCORA = tuple(sorted(VOCABOLARIO["ancore"]))

logger = logging.getLogger(__name__)


CERCA_TOOL_DEF = {
    "name": "cerca",
    "description": (
        "Trova nella casa un'area, un'entita', un dispositivo, un piano, "
        "un'automazione, uno script o un'etichetta a partire da un nome o alias "
        "scritto in linguaggio naturale (es. «il bagno», «la lavatrice», «il "
        "termostato del salotto», «il piano di sotto», «la sveglia del mattino», "
        "«da controllare»). Per ogni "
        "frammento di testo riconosciuto restituisce la lista COMPLETA dei candidati che quel nome "
        "puo' significare: se una sola voce lo usa la lista ha un elemento; se "
        "piu' voci si chiamano allo stesso modo (due «Bagno» su piani diversi, "
        "un alias che collide col nome vero di un'altra area) la lista ne ha "
        "piu' di uno e il risultato e' marcato `ambiguo` -- in quel caso scegli "
        "tu, guardando il resto della conversazione, o chiedi all'utente: non "
        "prendere semplicemente il primo della lista. "
        "Ogni candidato porta il `nome` con cui la casa lo conosce e, per le entita', "
        "il `dominio` (`light`, `sensor`, `switch`, ...): **guarda il dominio prima di "
        "concludere**, perche' «luci» puo' corrispondere a un `sensor` che CONTA le luci "
        "invece che a una luce. Se compare anche `nome_dedotto` (una STRINGA, mai un "
        "booleano -- la stessa forma in `guarda`), il nome che vedi in `nome` non l'ha "
        "scelto chi vive in questa casa: viene dedotto da cio' che Home Assistant mostra "
        "a schermo, e i due campi portano lo stesso testo. "
        "Un candidato di tipo `piano` NON si passa a `guarda`, che non sa aprire un "
        "piano da solo: serve a `esegui(piani=...)`, per agire su tutte le aree di "
        "quel piano insieme. `automazione` e `script` invece si passano a `guarda` "
        "esattamente come `area`/`entita`/`dispositivo`. "
        "Un candidato di tipo `etichetta` NEMMENO si passa a `guarda` (non e' una "
        "cosa che si apre in dettaglio): il suo `riferimento` E' il `label_id` che "
        "`esegui(bersaglio.etichette=[...])` pretende -- fino ad ora nessuna porta lo "
        "faceva uscire per un'etichetta che nessuna entita' ancora porta; da «cerca» "
        "sul suo NOME si arriva al `label_id` con una chiamata sola. "
        "Se il testo non nomina niente che la casa conosca, `trovati` e' una lista "
        "vuota: non e' un errore, significa che nessun nome o alias corrisponde. "
        "**Ma una lista vuota non basta sempre a concludere che la cosa non esista**: "
        "quando e' vuota per un motivo diverso, la risposta porta anche "
        "`non_ho_potuto_guardare` (MAI insieme a candidati gia' trovati) con la lista "
        "dei motivi. Ognuno e' o un guasto DI ADESSO (un registro non letto, lo "
        "specchio dello stato giu': ha senso riprovare piu' tardi) o un limite STABILE "
        "di alcune entita' di questa casa (nessun nome ne' nel registro ne' nello stato "
        "vivo: riprovare la stessa ricerca non cambia nulla, serve rinominarle in Home "
        "Assistant) -- il testo del motivo dice quale dei due e'. In nessuno dei due "
        "casi concludere che la cosa non esiste."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "testo": {
                "type": "string",
                "description": (
                    "Il testo in cui cercare nomi di aree, entita', dispositivi, piani, "
                    "automazioni, script o etichette, cosi' come l'ha scritto l'utente "
                    "(es. 'quanto fa caldo in soggiorno?')."
                ),
            },
        },
        "required": ["testo"],
    },
}

GUARDA_TOOL_DEF = {
    "name": "guarda",
    "description": (
        "Il dettaglio di UNA cosa sola della casa: un'area con le sue entita' e "
        "i loro stati, un'entita' con il suo stato e la sua classe, "
        "un'automazione o uno script con il corpo che li definisce, un "
        "dispositivo con le entita' che gli appartengono, oppure un ricordo con "
        "la sua interpretazione (forza, ancore, condizioni). Richiede `tipo` "
        "('area', 'entita', 'dispositivo', 'automazione', 'script' o 'ricordo') "
        "e `riferimento`: l'identificatore ESATTO della cosa (l'id di area/"
        "entita'/dispositivo, l'id dell'automazione o script, il numero del "
        "ricordo) -- non un nome libero. Se hai solo un nome, usa prima `cerca`. "
        "Restituisce SEMPRE la chiave `esiste`: quando e' `false` il resto non "
        "e' inventato -- nessuna lista di entita' o corpo che potrebbe passare "
        "per un fatto sulla casa invece che per 'non trovato'. Anche quando "
        "esiste, un dettaglio puo' mancare (`corpo: null` per un'automazione "
        "scritta a mano di cui non abbiamo letto il file): e' un limite di "
        "HIRIS dichiarato in `origine`, non un fatto sulla casa. Un'entita' -- "
        "da sola, o dentro le liste di un'area o di un dispositivo -- puo' "
        "avere `nome: null` e portare invece `nome_dedotto` (una STRINGA, mai "
        "un booleano -- la stessa forma in `cerca`): quel testo E' il nome, "
        "solo non scelto da chi vive in questa casa ma letto da cio' che Home "
        "Assistant mostra a schermo. Non concludere «senza nome» quando "
        "`nome_dedotto` c'e'. "
        "Questo strumento porta il CORPO di una cosa -- cosa fa quell'automazione, "
        "cosa contiene quell'area -- non i suoi legami: per sapere CHI tocca una "
        "cosa (e quindi cosa smetterebbe di funzionare se la cancellassi) usa "
        "`legami`, che e' una domanda diversa e una risposta diversa."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "description": "'area', 'entita', 'dispositivo', 'automazione', 'script' o 'ricordo'.",
            },
            "riferimento": {
                "type": ["string", "integer"],
                "description": (
                    "L'identificatore esatto della cosa da guardare: l'id di "
                    "area/entita'/dispositivo o di automazione/script cosi' "
                    "come lo conosce Home Assistant, oppure il numero di un "
                    "ricordo (visto in `guarda`/`richiama`)."
                ),
            },
        },
        "required": ["tipo", "riferimento"],
    },
}

# I tipi che `legami` accetta, nel vocabolario di HIRIS. DERIVATI dalla
# tabella di `domande.py` -- che e' anche quella con cui si traduce verso
# Home Assistant -- invece di riscritti qui: un elenco a mano nella
# descrizione e un altro nel gestore sarebbero due vocabolari, e il primo a
# divergere sarebbe quello che legge il modello.
_TIPI_LEGAME_NOSTRI = tuple(sorted(TIPO_LEGAME_HA))

LEGAMI_TOOL_DEF = {
    "name": "legami",
    "description": (
        "CHI tocca una cosa della casa, secondo Home Assistant: quali "
        "automazioni, script, scene, gruppi o persone la nominano, e dove quella "
        "cosa sta (area, dispositivo, piano, integrazione). Serve per due domande "
        "che senza questo strumento non hanno risposta: «perche' si e' accesa la "
        "luce del corridoio?» e -- prima di proporre di cancellare o cambiare "
        "qualcosa -- «se tolgo questa, cosa smette di funzionare?». "
        "Richiede `tipo` (uno fra: " + ", ".join(_TIPI_LEGAME_NOSTRI) + ") e "
        "`riferimento`, l'identificatore ESATTO (usa `cerca` se hai solo un nome). "
        "Lo calcola Home Assistant su TUTTO cio' che ha caricato, ovunque sia "
        "scritto -- pacchetti, `!include`, cartelle, scene, gruppi -- mentre "
        "`guarda` legge due soli file: qui i legami sono completi, ma non c'e' il "
        "CORPO. Le due cose non si sostituiscono: per sapere COSA FA "
        "un'automazione che trovi qui, aprila con `guarda`. "
        "**Come si legge la risposta.** `legami` e' un dizionario tipo -> "
        "identificatori. Per un'entita' mescola chi la USA (automazione, script, "
        "scena, gruppo, persona) con dove STA (area, dispositivo, piano, "
        "integrazione, etichetta): se la domanda e' «cosa smette di funzionare», "
        "guarda i primi -- un'area non smette di funzionare perche' le togli una "
        "luce. Per un'area, invece, le entita' elencate sono cio' che l'area "
        "CONTIENE. I tipi usano gli stessi nomi di `cerca` e `guarda`, quindi un "
        "riferimento letto qui si passa a `guarda` cosi' com'e' -- ma `guarda` sa "
        "aprire solo area, entita, dispositivo, automazione e script: sugli altri "
        "risponde `non_so_guardare`, che significa «non lo so aprire», MAI «non "
        "esiste». "
        "Un `legami` vuoto significa che Home Assistant non conosce nessun legame "
        "per questa cosa. Se invece non ha potuto rispondere ricevi `errore`, che "
        "non e' la stessa cosa: NON concludere che non la tocca nessuno."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "description": "Che cosa e' la cosa di cui vuoi i legami: uno fra "
                               + ", ".join(_TIPI_LEGAME_NOSTRI) + ".",
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

RICORDA_TOOL_DEF = {
    "name": "ricorda",
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
        "riferisce, nominando il loro identificatore esatto (usa `cerca` per "
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
                "description": "La frase cosi' come l'ha detta la persona -- non riassunta, non riscritta.",
            },
            "detto_da": {
                "type": "string",
                "description": "Chi ha detto questa frase, se lo sai. Ometti se non lo sai.",
            },
            "forza": {
                "type": "string",
                "description": "Una di: preferenza, divieto, fatto, regola. Ometti se non e' chiaro.",
            },
            "grandezza": {
                "type": "string",
                "description": (
                    "La grandezza a cui si riferisce un valore o intervallo, nel "
                    "linguaggio di Home Assistant (es. 'temperature', "
                    "'humidity'). Ometti se il ricordo non parla di un valore misurabile."
                ),
            },
            "minimo": {"type": "number", "description": "Il valore, o l'estremo minimo di un intervallo."},
            "massimo": {"type": "number", "description": "L'estremo massimo di un intervallo, se ce n'e' uno."},
            "condizioni": {
                "type": "array",
                "description": "Quando vale questo ricordo. Ometti se vale sempre.",
                "items": {
                    "type": "object",
                    "properties": {
                        "tipo": {"type": "string", "description": "ora, giorno, presenza, sole, meteo o stagione."},
                        "valore": {"type": "string", "description": "Il valore di quella condizione, nel linguaggio di Home Assistant."},
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
                            "description": "L'identificatore esatto (usa `cerca` per trovarlo, non inventarlo).",
                        },
                        "nome_visto": {
                            "type": "string",
                            "description": "Il nome con cui la persona l'ha nominata nella frase, se diverso.",
                        },
                    },
                    "required": ["tipo", "riferimento"],
                },
            },
        },
        "required": ["testo"],
    },
}

RICHIAMA_TOOL_DEF = {
    "name": "richiama",
    "description": (
        "I ricordi gia' salvati che riguardano una parte della casa -- un'area, "
        "un'entita' o un dispositivo -- dato il suo identificatore esatto "
        "(`riferimento`; usa `cerca` per trovarlo se hai solo un nome). Serve a "
        "rispondere a domande come 'cosa mi hai gia' detto sulla cucina?' senza "
        "dover rileggere ogni ricordo uno per uno. Se `tipo` non e' specificato, "
        "cerca fra tutti e tre i tipi di ancora (area, entita', dispositivo); "
        "specificalo solo se lo sai gia' con certezza. Se nessun ricordo e' "
        "ancorato a quel riferimento, `ricordi` e' una lista vuota: non "
        "significa che la casa non ha ricordi, significa solo che nessuno di "
        "quelli salvati nomina proprio questa parte -- prova `richiama` senza "
        "ancore su una parte piu' ampia, o chiedi all'utente."
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

ESEGUI_TOOL_DEF = {
    "name": "esegui",
    "description": (
        "Chiama un servizio di Home Assistant per far succedere qualcosa nella "
        "casa: accendere, spegnere, impostare. Richiede `servizio` nella forma "
        "«dominio.servizio» (per esempio «light.turn_off») e un `bersaglio`. "
        "Il bersaglio si scrive in due modi, e il secondo e' quello giusto per "
        "«tutto in cucina»: `entita` con gli id ESATTI, oppure `aree`, `piani`, "
        "`etichette` o `dispositivi` con i loro id -- e in quel caso e' Home "
        "Assistant a dire cosa contengono. NON risolvere un'area a mano con "
        "`cerca` per poi elencarne le entita': se te ne sfugge una tocchi quasi "
        "tutto e credi di aver toccato tutto. Puoi combinarli. "
        "`dati` porta i parametri del servizio, se ne servono. "
        "La chiamata viene VERIFICATA contro questa installazione prima di "
        "partire: se il servizio non esiste, se l'entita' non esiste, se l'area "
        "o l'etichetta che hai nominato non esistono, o se un "
        "parametro non appartiene a quel servizio, ricevi un errore che dice "
        "cosa esiste davvero -- usalo per correggerti invece di riprovare "
        "uguale. Con un bersaglio risolto l'esito porta anche `bersaglio`, che "
        "dice cosa conteneva (`risolte`), su cosa la chiamata e' partita "
        "(`toccate`) e cosa e' rimasto fuori perche' di un altro dominio o "
        "senza stato: se `toccate` e' piu' corto di `risolte`, dillo all'utente "
        "invece di dichiarare che hai fatto tutto. "
        "Dopo l'esecuzione lo stato viene RILETTO: `prima`, `dopo` e "
        "`cambiato` dicono cosa e' successo per davvero. Se `cambiato` e' vuoto "
        "arriva un `avviso`: la chiamata e' riuscita ma nulla e' cambiato, e "
        "va detto all'utente invece di dichiarare un successo."
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
                            "porta, entita', dispositivi o aree. Si prendono da "
                            "«cerca» sul NOME dell'etichetta (il candidato di tipo "
                            "«etichetta» porta il suo id), o da «guarda», dove "
                            "compaiono accanto al nome di ogni etichetta -- mai da "
                            "solo, sono slug che nessuno scrive a memoria."
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

PROMETTI_TOOL_DEF = {
    "name": "prometti",
    "description": (
        "Metti da parte qualcosa da fare, o da guardare, PIU' TARDI: «alle 17 "
        "accendi lo studio», «fra un'ora verifica la temperatura e se e' "
        "aumentata avvisami», «fra due ore dimmi se posso aprire le finestre». "
        "Due specie. `fai`: un'azione, e vuole `chiamata` nella stessa forma di "
        "«esegui» -- viene VERIFICATA adesso contro questa installazione, quindi "
        "un servizio o un'entita' che non esistono te li dico subito, non fra due "
        "ore. `chiedi`: a quell'ora guardi tu e rispondi, e vuole `domanda`; se la "
        "richiesta e' un CONFRONTO («se e' aumentata») elenca in `da_confrontare` "
        "le entita' da misurare ADESSO, o piu' tardi non avrai con cosa "
        "confrontare. `quando` e' un istante ISO-8601 col fuso: risolvilo tu da "
        "«fra un'ora» o «alle 17», e riporta in `quando_detto` le parole della "
        "persona. Un istante gia' passato viene rifiutato. `recapito` e' il "
        "servizio notify con cui venirla a cercare (usa «cerca» per trovarne uno "
        "vero): senza, la risposta resta solo nella pagina delle promesse. "
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
                "description": "Solo per «fai»: `servizio`, `bersaglio` e `dati`, come in «esegui».",
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
            "recapito": {
                "type": "string",
                "description": "Il servizio notify con cui avvisare, es. «notify.mobile_app_x».",
            },
        },
        "required": ["specie", "frase", "quando"],
    },
}

PROMESSE_TOOL_DEF = {
    "name": "promesse",
    "description": (
        "Cosa HIRIS ha promesso: cio' che e' ancora in sospeso e, se chiedi lo "
        "storico, com'e' andata -- mantenuta, saltata (col ritardo misurato), "
        "disdetta o fallita col motivo. Usalo quando la persona chiede «cosa hai "
        "in programma?», «l'hai fatto?», o prima di disdire qualcosa, per avere "
        "l'identificatore giusto invece di indovinarlo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tutte": {
                "type": "boolean",
                "description": "Vero per vedere anche quelle gia' concluse. Ometti per le sole in sospeso.",
            },
        },
    },
}

DISDICI_TOOL_DEF = {
    "name": "disdici",
    "description": (
        "Annulla una promessa che non e' ancora stata mantenuta. Serve il suo "
        "`id`: prendilo da «promesse», non inventarlo. Una promessa gia' "
        "mantenuta, saltata o disdetta non si annulla -- te lo dico invece di "
        "fingere di averlo fatto."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "L'identificatore della promessa."}},
        "required": ["id"],
    },
}

COSTRUISCI_TOOL_DEF = {
    "name": "costruisci",
    "description": (
        "PROPONE di creare, modificare o cancellare un'automazione, uno script "
        "o una scena in Home Assistant. **Non scrive niente**: compone, fa "
        "validare la configurazione a QUESTA casa e restituisce un'anteprima "
        "con un `proposta_id`. Per farla diventare vera serve `conferma`, e "
        "**non nello stesso turno**: mostra l'anteprima all'utente e aspetta "
        "che sia lui a dire di procedere. "
        "`gesto` e' «crea», «modifica» o «cancella». `dominio` e' «automation», "
        "«script» o «scene». Per modificare o cancellare serve `chiave` (l'id "
        "dell'automazione o della scena, lo slug dello script): la trovi con "
        "`cerca` o `guarda`. "
        "Componi con i PARAMETRI, non scrivendo YAML: `innesco`, `condizioni`, "
        "`azioni` per un'automazione; `azioni` per uno script; `stati` per una "
        "scena. Usa lo schema moderno di Home Assistant (`trigger:`, `action:` "
        "dentro le voci). Se la validazione fallisce ricevi il motivo VERO di "
        "Home Assistant: correggiti su quello. "
        "Se servono helper che non esistono, elencali in `helper`: nascono "
        "insieme all'oggetto, e se l'oggetto viene rifiutato vengono disfatti. "
        "Se quello che chiedi ha la forma sbagliata -- un'automazione per una "
        "cosa che e' uno script -- l'anteprima te lo dice: riferiscilo "
        "all'utente invece di ignorarlo."
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
            "richiesto": {"type": "string",
                          "description": "Cosa ha chiesto l'utente: automazione, "
                                         "script o scena. Serve a dirti se non "
                                         "sono d'accordo."},
            "helper": {"type": "array", "items": {"type": "object"},
                       "description": "Gli helper da creare insieme: ognuno con "
                                      "`dominio` e `dati`."},
            "frase": {"type": "string",
                      "description": "La frase dell'utente da cui nasce, verbatim."},
        },
        "required": ["gesto", "dominio"],
    },
}

CONFERMA_TOOL_DEF = {
    "name": "conferma",
    "description": (
        "Applica una proposta creata da `costruisci`: da qui in poi la cosa "
        "esiste davvero in Home Assistant. "
        "**Chiamalo SOLO dopo che l'utente ha detto di procedere**, in un turno "
        "successivo a quello in cui hai mostrato l'anteprima: se lo chiami nello "
        "stesso turno viene rifiutato, ed e' voluto -- il si' dell'utente non e' "
        "una cosa che puoi dare per scontata. "
        "L'esito dice cosa e' nato davvero (`entita`) e, se qualcosa non torna, "
        "un `avviso`: riferiscilo invece di dichiarare un successo pieno."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "proposta_id": {"type": "string",
                            "description": "L'identificatore restituito da `costruisci`."},
        },
        "required": ["proposta_id"],
    },
}

STRUMENTI_CONOSCENZA: list[dict] = [
    CERCA_TOOL_DEF, GUARDA_TOOL_DEF, LEGAMI_TOOL_DEF, RICORDA_TOOL_DEF,
    RICHIAMA_TOOL_DEF, ESEGUI_TOOL_DEF,
    PROMETTI_TOOL_DEF, PROMESSE_TOOL_DEF, DISDICI_TOOL_DEF,
    COSTRUISCI_TOOL_DEF, CONFERMA_TOOL_DEF,
]

# I nomi che `dispatch()` accetta. Si DERIVANO dal catalogo qui sopra: erano
# quattro stringhe scritte a mano, cioe' un secondo elenco degli stessi nomi
# da tenere allineato -- esattamente la forma di difetto che questo ramo ha
# gia' pagato coi tre cataloghi divergenti dei trentaquattro strumenti. Con
# quelle scritte a mano, uno strumento nuovo nel catalogo sarebbe arrivato al
# modello (che legge `STRUMENTI_CONOSCENZA`) e poi si sarebbe sentito
# rispondere «non e' fra quelli disponibili» dal dispatcher: il tipo di
# incoerenza che il modello non puo' ne' capire ne' aggirare.
_NOMI_STRUMENTI = frozenset(d["name"] for d in STRUMENTI_CONOSCENZA)


class DispatcherStrumenti:
    """Collega gli undici strumenti agli archivi, alla porta, all'officina e al
    canale HA -- e non altro.

    Prende `archivio_casa` e `archivio_memoria` gia' costruiti dal chiamante
    (`create_app()` o l'equivalente nei test): questa classe non ne apre
    nessuno, e non li chiude -- non le appartengono.

    `dispatch()` e' l'unico punto d'ingresso e non solleva MAI: uno
    strumento sconosciuto, argomenti mancanti, o un guasto imprevisto
    diventano tutti un dizionario con la chiave `errore`, leggibile dal
    modello -- mai un'eccezione che gli spezza il turno.
    """

    def __init__(self, archivio_casa: ArchivioCasa, archivio_memoria: ArchivioMemoria,
                 cache=None, porta=None, cache_indice: CacheIndice | None = None,
                 ha=None, registro=None, promesse=None, officina=None,
                 turno: str | None = None) -> None:
        self._casa = archivio_casa
        self._memoria = archivio_memoria
        # Lo specchio dello stato vivo. E' la STESSA `entity_cache` da cui
        # il nucleo prende "notevole adesso": una sola fonte, un solo
        # specchio. La cache resta in SOLA LETTURA anche adesso che `esegui`
        # esiste: chi scrive e' la porta (`azione/porta.py`), che chiama
        # Home Assistant e poi RILEGGE da qui -- lo specchio non si aggiorna
        # a mano per far tornare i conti. Prima della fetta «comandare» la
        # ragione scritta qui era «conosce, non agisce»: era una proprieta'
        # del prodotto, oggi e' una proprieta' di QUESTO attributo.
        self._cache = cache
        # La porta dell'azione (`azione/porta.py`), l'unico punto del prodotto
        # che esegue. `None` e' legittimo: il dispatcher e' SEMPRE costruibile
        # (contratto della classe), e senza porta `esegui` dichiara un errore
        # invece di sollevare -- come gli altri quattro fanno senza archivi.
        self._porta = porta
        # Task B7: la cache dell'Indice (`memoria/cache_indice.py`), di vita
        # LUNGA -- non nasce con questo dispatcher (che nasce a ogni turno,
        # vedi `handlers_chat.py::costruisci_dispatcher_strumenti`) ma vive
        # accanto a `entity_cache` in `hiris/app/server.py` e arriva qui come
        # dipendenza. Default `None`: nessuna cache, `_cerca`/`_ricorda`
        # ricostruiscono l'indice ogni volta come facevano prima di questo
        # task -- ogni chiamante esistente (i test, e ogni altro punto del
        # prodotto che non la passa esplicitamente) non cambia comportamento.
        self._cache_indice = cache_indice
        # Il canale verso Home Assistant, per `legami` e per cio' che dopo di
        # esso chiedera' un fatto MOMENTANEO (i legami non si archiviano --
        # vedi il docstring del modulo). In SOLA LETTURA come `_cache`: chi
        # scrive resta la porta, e questo attributo non le fa concorrenza.
        self._ha = ha
        # Il registro dei servizi (`azione/registro.py::RegistroServizi`), la
        # STESSA istanza che usa la porta -- non se ne apre un secondo, per la
        # stessa ragione di `_canale_ha`: due registri sarebbero due opinioni
        # su cosa esiste, e potrebbero divergere. Serve a `prometti` per
        # verificare un `fai` ADESSO (`_verifica_ora`) e un `recapito`
        # (`_verifica_recapito`). `None` e' legittimo e NON passa da
        # `_archivio_mancante` (che solleverebbe un errore diverso, "l'archivio
        # non e' caricato"): senza registro PRONTO -- assente o presente ma mai
        # caricato da Home Assistant, `_registro_non_pronto()` -- i due
        # controlli RIFIUTANO invece di tacere (fix review Task 6 Rilievo 2 per
        # `_verifica_ora`, esteso a `_verifica_recapito` da review Task 7
        # Rilievo 1): un `fai` o un recapito mai verificati nascerebbero con
        # una promessa che dichiara "viene VERIFICATA adesso" senza esserlo
        # stata.
        self._registro = registro
        # L'archivio delle promesse (`schedulatore/archivio.py`). `None` e'
        # legittimo come per la porta: i tre strumenti dichiarano un errore
        # leggibile invece di sollevare.
        self._promesse = promesse
        # L'officina (`azione/costruzione/officina.py`), l'unico punto che
        # scrive CONFIGURAZIONE. Sorella della porta, non sua sostituta: sono
        # due canali diversi (spec «un canale, una porta»). `None` e'
        # legittimo come per la porta: i due strumenti dichiarano un errore.
        self._officina = officina
        # L'identita' di QUESTO turno. Serve alla guardia dell'officina: una
        # proposta non si conferma nel turno che l'ha creata. Senza identita'
        # l'officina rifiuta di applicare dalla chat e indica la pagina --
        # un cancello che non sa chi sta passando non e' un cancello.
        self._turno = turno

    _ARCHIVIO_PER_STRUMENTO = {
        "cerca": ("casa",), "guarda": ("casa", "memoria"),
        "legami": ("ha",),
        "ricorda": ("casa", "memoria"), "richiama": ("memoria",),
        "esegui": ("porta",),
        "prometti": ("promesse",), "promesse": ("promesse",),
        "disdici": ("promesse",),
        "costruisci": ("officina",), "conferma": ("officina",),
    }

    def _canale_ha(self):
        """Il canale vivo verso Home Assistant -- uno solo, mai un secondo.

        `legami` chiede a Home Assistant un fatto che non esiste in nessun
        archivio (chi tocca cosa, ADESSO), quindi gli serve il client. Aprirne
        uno qui sarebbe un secondo canale verso la stessa casa: la fondamenta
        «nessun doppione» vale anche per le connessioni, e due websocket che
        si autenticano da soli sono due cose che possono divergere.

        Il canale arriva da fuori (`ha=`), dall'unico costruttore del
        dispatcher (`api/handlers_chat.py::costruisci_dispatcher_strumenti`),
        ed e' lo stesso oggetto che riceve la porta dell'azione.

        C'e' stato per poco un ripiego che leggeva `porta._ha` -- l'attributo
        privato di un altro oggetto -- perche' quella fetta non poteva toccare
        il costruttore. E' durato il tempo di aggiungere una riga la', ed e'
        uscito: un modulo che conosce le parti private di un altro e' un
        accoppiamento che nessun test dichiara, e si scopre il giorno in cui
        l'altro cambia nome a un campo.

        `None` quando il canale non c'e', e chi chiama lo DICHIARA: uno
        strumento che tace perche' non ha la connessione e uno che tace perche'
        non c'e' nessun legame direbbero la stessa cosa.
        """
        return self._ha

    def _archivio_mancante(self, nome: str) -> str | None:
        """Quale archivio serve a questo strumento e non c'e'."""
        for quale in self._ARCHIVIO_PER_STRUMENTO.get(nome, ()):
            if quale == "casa" and self._casa is None:
                return "la conoscenza della casa non e' ancora stata caricata"
            if quale == "memoria" and self._memoria is None:
                return "l'archivio della memoria non e' ancora stato caricato"
            if quale == "porta" and self._porta is None:
                return "il collegamento con Home Assistant non e' disponibile"
            if quale == "ha" and self._canale_ha() is None:
                # Distinto dal messaggio della porta apposta: li' manca
                # l'oggetto che ESEGUE, qui il canale a cui CHIEDERE. Sono due
                # assenze diverse, e un utente che legge la risposta del
                # modello deve poter capire quale delle due sta guardando.
                return "non c'e' un collegamento vivo con Home Assistant a cui chiederli"
            if quale == "promesse" and self._promesse is None:
                return "l'archivio delle promesse non e' ancora stato caricato"
            if quale == "officina" and self._officina is None:
                return ("non posso costruire: l'officina non e' disponibile "
                        "(Home Assistant non e' raggiungibile, o l'add-on e' appena partito)")
        return None

    async def dispatch(self, nome: str, argomenti: dict[str, Any] | None) -> dict:
        argomenti = argomenti or {}
        # Gli archivi possono mancare: il chiamante puo' costruirci prima che
        # esistano. Senza questo controllo il modello riceve
        # «'NoneType' object has no attribute 'leggi'» -- un errore Python
        # travestito da risposta, mentre questo dispatcher promette messaggi
        # LEGGIBILI. Dire cosa manca e' anche l'unico modo perche' il modello
        # possa spiegarlo all'utente invece di riprovare all'infinito.
        mancante = self._archivio_mancante(nome)
        if mancante is not None:
            return {"errore": f"«{nome}» non e' disponibile: {mancante}."}
        if nome not in _NOMI_STRUMENTI:
            # NON "non inventare nomi di tool": se il modello ha chiamato
            # questo nome, gliel'abbiamo dato NOI in un turno precedente (un
            # tool rimosso da un aggiornamento, o un refuso nostro nella
            # cronologia) -- accusarlo di essersi inventato uno strumento che
            # gli avevamo servito noi e' esattamente il difetto gia'
            # corretto una volta su questo ramo. Il messaggio resta un fatto
            # neutro: cosa esiste, non un rimprovero.
            disponibili = ", ".join(sorted(_NOMI_STRUMENTI))
            return {"errore": f"lo strumento «{nome}» non e' fra quelli disponibili "
                              f"({disponibili})."}
        gestore = {
            "cerca": self._cerca,
            "guarda": self._guarda,
            "legami": self._legami,
            "ricorda": self._ricorda,
            "richiama": self._richiama,
            "esegui": self._esegui,
            "prometti": self._prometti,
            "promesse": self._promesse_elenco,
            "disdici": self._disdici,
            "costruisci": self._costruisci,
            "conferma": self._conferma,
        }[nome]
        try:
            # `_esegui`, `_legami`, `_prometti`, `_costruisci` e `_conferma`
            # sono coroutine (fanno rete, o -- `_prometti` -- possono
            # scaldare il registro dei servizi prima di verificare); gli
            # altri sei no. Si attende cio' che e' attendibile invece di
            # rendere `async` anche i sei sincroni: cambiare la loro firma
            # avrebbe toccato undici gestori per un bisogno di cinque.
            esito = gestore(argomenti)
            if inspect.isawaitable(esito):
                esito = await esito
            return esito
        except Exception as errore:
            # Rete di sicurezza finale: qualunque guasto imprevisto (un
            # archivio chiuso a meta', un tipo inatteso negli argomenti) si
            # dichiara qui invece di risalire -- vedi il docstring della
            # classe.
            # Minor #7 review finale: dichiararlo al MODELLO non bastava --
            # un archivio corrotto o un guasto ricorrente restava invisibile
            # all'operatore, che non ha altro modo di saperlo (il modello
            # riceve solo la stringa "errore", non uno stack). Loggato qui.
            logger.warning(
                "strumento «%s» ha sollevato %s: %s", nome, type(errore).__name__, errore
            )
            return {"errore": f"lo strumento «{nome}» ha incontrato un problema: {errore}"}

    # -- cerca ---------------------------------------------------------

    def _cerca(self, argomenti: dict[str, Any]) -> dict:
        testo = argomenti.get("testo")
        if not isinstance(testo, str) or not testo.strip():
            return {"errore": "«cerca» richiede un «testo» non vuoto."}
        casa = self._casa.leggi()
        # T7 (R2): automazioni e script, dalla stessa fonte che alimenta
        # `guarda` (`ArchivioCasa.comportamento()`), non dall'anagrafe --
        # senza indicizzarli qui, nessuna sequenza di chiamate produceva mai
        # il loro id, e `guarda("automazione", ...)` restava irraggiungibile
        # per chi partiva da un nome. Letto eagerly come `casa`: `_cerca`
        # non ha niente da rimandare (a differenza di `_ricorda`, che non lo
        # passa affatto -- il comportamento non e' un tipo di ancora).
        comportamento = self._casa.comportamento()
        _, nomi_vivi, _unita, _classi, specchio_letto = self._specchio()
        # Task B7: con la cache, l'indice si RIUSA finche' l'anagrafe
        # (`aggiornata_il()`), il comportamento (`comportamento_letto_il()`,
        # T7) e i nomi vivi di ripiego non cambiano -- vedi
        # `memoria/cache_indice.py` per la chiave. Spazio "cerca", diverso da
        # "ricorda": qui si passano SEMPRE i nomi di ripiego, `_ricorda` no,
        # e sulla stessa casa i due indici hanno contenuti diversi.
        if self._cache_indice is not None:
            indice = self._cache_indice.ottieni(
                "cerca", casa, self._casa.aggiornata_il(), nomi_vivi,
                comportamento, self._casa.comportamento_letto_il())
        else:
            indice = costruisci_indice(casa, nomi_vivi, comportamento)
        trovati = _cerca_candidati(indice, testo)
        risposta: dict = {"trovati": trovati}
        # N2 (ri-review): il ramo strutturale di `_cecita` (I3, sotto) si
        # accende su OGNI casa sana che abbia entita' senza nome ne' nel
        # registro ne' nello specchio -- sull'impianto vero, un fatto
        # STABILE (376 entita'), non un guasto di QUESTA ricerca. La chiave
        # esiste per spiegare un `trovati` vuoto che potrebbe nascondere
        # qualcosa (vedi il docstring di `_cecita`): non ha niente da
        # spiegare quando la ricerca ha gia' trovato cio' che cercava, e
        # dichiararla comunque la rende permanente -- un'assenza dichiarata
        # SEMPRE smette di essere un segnale (la stessa invariante 4 che
        # questo ramo esiste per rispettare, rivoltata contro se stessa).
        cecita = self._cecita(casa, specchio_letto, nomi_vivi, trovati_vuoti=not trovati)
        if cecita:
            risposta["non_ho_potuto_guardare"] = cecita
        return risposta

    def _cecita(self, casa: dict, specchio_letto: bool,
                nomi_vivi: dict[str, str] | None = None, *,
                trovati_vuoti: bool = True) -> list[str]:
        """Perche' `trovati` potrebbe essere vuoto SENZA che la cosa manchi.

        Invariante 4 della fetta: «non c'e' nessuna cosa con quel nome» e «non
        ho potuto guardare» oggi hanno la stessa faccia -- una lista vuota --
        e la seconda e' cio' che ha bruciato quattro giri di `cerca` sulle
        abat-jour. Da qui hanno due facce diverse.

        Solo fatti, e solo quando ci sono: la chiave non compare quando non
        c'e' niente da dichiarare. Un elenco vuoto che dice "nessun problema"
        e' esattamente la forma che questa funzione esiste per togliere.

        `trovati_vuoti` (N2, ri-review): il ramo strutturale piu' sotto
        (entita' senza nome ne' nel registro ne' nello specchio) descrive un
        fatto STABILE della casa -- sull'impianto vero non si risolve mai da
        solo, quindi senza questo cancello si accenderebbe a ogni singola
        `cerca`, comprese quelle riuscite: un'assenza dichiarata SEMPRE
        smette di essere un segnale (la stessa invariante 4 qui sopra,
        rivoltata contro se stessa). Riportato solo quando serve DAVVERO a
        spiegare un `trovati` vuoto -- mai accanto a candidati trovati."""
        motivi: list[str] = []
        # Fix finale ① (2026-08-20): `CHIAVE_ARCHIVIO_PER_TIPO` e' apposta
        # SENZA "etichette" (non e' un tipo di ancora, vedi il commento su
        # `_ARCHIVI` in memoria/riconoscitore.py -- allargarla rifarebbe il
        # secondo vocabolario che R9 denuncia). Ma "etichette" e' comunque
        # una tabella vera di `_TABELLE` (casa/archivio.py) che PUO' cadere
        # in `non_disponibili()`, e da T8 (R2) `cerca` indicizza le
        # etichette stesse come candidati: un registro etichette caduto
        # merita lo stesso motivo dei registri di `CHIAVE_ARCHIVIO_PER_TIPO`,
        # aggiunta qui invece che nella mappa che serve a un altro scopo.
        caduti = sorted(set(self._casa.non_disponibili())
                        & (set(CHIAVE_ARCHIVIO_PER_TIPO.values()) | {"etichette"}))
        if caduti:
            motivi.append(
                f"registri non letti all'ultima ricostruzione dell'anagrafe: "
                f"{', '.join(caduti)}. Cio' che sta li' dentro non e' cercabile adesso, "
                "e potrebbe esistere lo stesso.")
        # Fix finale ① (2026-08-20): il comportamento (automazioni/script)
        # non passa MAI da `non_disponibili()` -- la sua fonte e' un file
        # YAML riletto a una cadenza propria (`ArchivioCasa.comportamento()`),
        # non un registro dell'anagrafe, col proprio segnale di
        # incompletezza (`file_non_letti()`). `_guarda` lo legge gia' per lo
        # stesso motivo (vedi `_guarda` qui sotto, `_dettaglio_non_trovato`
        # in domande.py); `_cerca` non lo leggeva affatto, quindi un file di
        # comportamento non letto restituiva 'trovati': [] nudo per un nome
        # di automazione/script che poteva essere scritto proprio li'.
        file_non_letti = self._casa.file_non_letti()
        if file_non_letti:
            motivi.append(
                f"file di automazioni/script non letti: "
                f"{', '.join(sorted(file_non_letti))}. Cio' che c'e' scritto li' dentro "
                "non e' cercabile adesso, e potrebbe esistere lo stesso.")

        senza_nome = [e for e in casa.get("entita") or []
                     if not (e.get("nome") or "").strip() and not e.get("disabilitata")]
        specchio_ok = specchio_letto and inventario_leggibile(self._cache)
        if senza_nome and not specchio_ok:
            motivi.append(
                f"{len(senza_nome)} entita' non hanno un nome nel registro di Home Assistant e "
                "lo specchio dello stato non e' leggibile: il ripiego sul nome che Home "
                "Assistant mostra non e' disponibile, quindi quelle entita' non sono "
                "cercabili per nome in questo momento.")
        elif senza_nome and specchio_ok:
            # I3 (review finale), invariante 4 sul caso PARZIALE: lo specchio
            # e' leggibile (altrimenti il ramo sopra avrebbe gia' parlato),
            # ma per QUESTE entita' non porta un friendly_name -- il registro
            # taciuto e lo specchio senza voce sono lo stesso "non cercabile
            # per nome", solo con la seconda meta' della causa diversa. Il
            # registro della campagna l'aveva annotato ("376 senza stato
            # vivo, da dichiarare") ma nessuna fetta l'aveva scritto: senza
            # questo ramo, quelle entita' restano "trovati": [] nudo,
            # indistinguibile da "non esistono".
            senza_nome_vivo = [e for e in senza_nome
                               if not ((nomi_vivi or {}).get(e["id"]) or "").strip()]
            # trovati_vuoti: vedi il docstring -- questo fatto e' stabile
            # (non si risolve riprovando la ricerca), quindi si dichiara
            # solo quando serve a spiegare un `trovati` vuoto, mai a fianco
            # di candidati gia' trovati.
            if senza_nome_vivo and trovati_vuoti:
                motivi.append(
                    f"{len(senza_nome_vivo)} entita' di questa casa non hanno un nome ne' nel "
                    "registro di Home Assistant ne' nello specchio dello stato (lo specchio si "
                    "legge, ma non porta un nome per queste): e' un limite stabile di quelle "
                    "entita', non un guasto di questa ricerca -- ripetere la stessa ricerca non "
                    "cambia nulla, serve rinominarle in Home Assistant.")
        return motivi

    # -- guarda ----------------------------------------------------------

    def _guarda(self, argomenti: dict[str, Any]) -> dict:
        tipo = argomenti.get("tipo")
        riferimento = argomenti.get("riferimento")
        if not tipo or riferimento is None:
            return {"errore": "«guarda» richiede «tipo» e «riferimento»."}
        # I ricordi hanno un id numerico (ArchivioMemoria, AUTOINCREMENT):
        # il modello puo' passarlo come stringa (i JSON tool-call spesso lo
        # fanno). Un riferimento non convertibile non e' un errore da
        # sollevare -- e' lo stesso "non l'ho trovato" degli altri tipi.
        if tipo == "ricordo" and not isinstance(riferimento, int):
            try:
                riferimento = int(riferimento)
            except (TypeError, ValueError):
                return {"esiste": False, "tipo": "ricordo", "riferimento": riferimento}

        casa = self._casa.leggi()
        non_disponibili = tuple(self._casa.non_disponibili())
        comportamento = self._casa.comportamento()
        file_non_letti = self._casa.file_non_letti()
        # Tutti i ricordi, non solo gli ultimi venti (il default di
        # `richiama()`): un ricordo vecchio ancorato a QUESTA cosa non deve
        # sparire dal suo stesso dettaglio solo perche' non e' fra i piu'
        # recenti -- stessa scelta di `handlers_casa.handle_get_nucleo`.
        ricordi = self._memoria.richiama(limite=self._memoria.conta())
        # `guarda()` (domande.py) e' pura: lo stato glielo passa il chiamante.
        # Si legge dalla stessa `entity_cache` del nucleo, nella forma che usa
        # lei (chiave "id", non "entity_id").
        stato, nomi_vivi, unita_vive, classi_vive, letto = self._specchio()
        dettaglio = _guarda_dettaglio(casa, comportamento, ricordi, stato, tipo, riferimento,
                                      non_disponibili=non_disponibili,
                                      file_non_letti=file_non_letti,
                                      nomi_di_ripiego=nomi_vivi,
                                      unita_vive=unita_vive,
                                      classi_vive=classi_vive)
        # Senza inventario leggibile ogni `stato: None` sarebbe ambiguo fra
        # «l'entita' non ha stato» e «non ho potuto guardare»: si dichiara.
        # Fix E1-③: `letto` (la lettura di QUESTA chiamata e' andata a buon
        # fine) va OR-ato con `inventario_leggibile` (cosa dichiara la
        # cache di se stessa), non sostituito -- una cache che si dichiara
        # `loaded` ma il cui `all_states()` solleva davvero e' comunque
        # "non letto" qui.
        if isinstance(dettaglio, dict) and (not letto or not inventario_leggibile(self._cache)):
            dettaglio["stato_non_letto"] = True
        return dettaglio

    def _specchio(self) -> tuple[dict[str, str], dict[str, str], dict[str, str],
                                 dict[str, str], bool]:
        """Lo specchio vivo in UNA lettura: `(stato, nomi, unita, classi, letto)`.

        Sostituisce `_stato_vivo`, non gli si affianca: `cerca` ha bisogno dei
        `friendly_name` e `guarda` dello stato, e due metodi che chiamano
        `all_states()` a turno sarebbero due letture della stessa cosa in
        istanti diversi -- la stessa classe di divergenza che il nucleo chiude
        condividendo un solo albero.

        `nomi` e' entity_id -> `friendly_name`, saltando i vuoti: la chiave
        "name" di `entity_cache._to_minimal` e' `friendly_name or ""`, e una
        stringa vuota non e' un nome, e' l'assenza di un nome.

        `classi` e' entity_id -> `device_class`, ed e' l'UNICA fonte che
        esista: il registro delle entita' non la manda affatto (vedi
        `anagrafe.classe_effettiva`).

        `unita` e' entity_id -> `unit_of_measurement`, saltando i vuoti, e
        arriva dalla STESSA lettura per la stessa ragione dei nomi: la
        conserva `_to_minimal` (`proxy/entity_cache.py`) e prima di questa
        fetta nessuno la rileggeva, cosi' il modello riceveva `72` senza sapere
        se fossero gradi Celsius o Fahrenheit. Non basta il sistema di unita'
        della casa: Home Assistant converte **solo alla prima aggiunta del
        sensore**, quindi `unit_system` non descrive le entita' gia' presenti.

        `letto` conserva esattamente la semantica del fix E1-(3): False solo
        quando la lettura di QUESTA chiamata e' fallita davvero. Cache assente
        resta `True` -- non e' successo niente di male, e a dire che
        l'inventario non e' guardabile ci pensa `inventario_leggibile`."""
        if self._cache is None or not hasattr(self._cache, "all_states"):
            return {}, {}, {}, {}, True
        try:
            # La lettura vera e' in `anagrafe.specchio_vivo`, condivisa con chi
            # legge lo specchio da fuori dal dispatcher: qui restano solo la
            # difesa sulla cache assente e la semantica di `letto`.
            stato, nomi, unita, classi = specchio_vivo(self._cache.all_states())
        except Exception:
            return {}, {}, {}, {}, False
        return stato, nomi, unita, classi, True

    # -- legami --------------------------------------------------------

    async def _legami(self, argomenti: dict[str, Any]) -> dict:
        """Chiede a Home Assistant chi tocca questa cosa, e non lo salva.

        Non lo salva ed e' una scelta, non una dimenticanza: i legami sono
        MOMENTANEI quanto lo stato -- un'automazione salvata un minuto fa li
        cambia -- e una tabella riletta di rado mentirebbe poche ore dopo. E'
        la stessa ragione per cui `state` sta fuori dal sistema di riferimento
        (`casa/anagrafe.sistema_di_riferimento`). Quindi si chiede quando
        serve, e la risposta vive il tempo di un turno.

        Qui dentro c'e' solo il collegamento: la traduzione dei tipi e la
        forma della risposta stanno in `domande.legami`, che e' pura e si
        prova senza rete.
        """
        tipo = argomenti.get("tipo")
        riferimento = argomenti.get("riferimento")
        if not tipo or not riferimento:
            return {"errore": "«legami» richiede «tipo» e «riferimento»."}
        tipo_ha = TIPO_LEGAME_HA.get(tipo)
        if tipo_ha is None:
            # Fermato QUI, prima della rete, e con l'elenco dei tipi veri:
            # mandarlo comunque a Home Assistant produrrebbe un rifiuto suo,
            # che arriva al modello come «errore» generico e non gli insegna
            # niente. Stessa scelta di `_richiama` con le ancore.
            disponibili = ", ".join(_TIPI_LEGAME_NOSTRI)
            return {"errore": f"«{tipo}» non e' un tipo di cui Home Assistant sappia "
                              f"i legami ({disponibili})."}
        risposta = await self._canale_ha().legami(tipo_ha, str(riferimento))
        return _legami_leggibili(risposta, tipo, riferimento)

    # -- ricorda -----------------------------------------------------------

    def _ricorda(self, argomenti: dict[str, Any]) -> dict:
        testo = argomenti.get("testo")
        if not isinstance(testo, str) or not testo.strip():
            return {"errore": "«ricorda» richiede un «testo» non vuoto."}

        # `aggiornata_il` decide sia "anagrafe letta?" sia la chiave della
        # cache sotto: letto una volta sola, nessun await fra le due letture
        # in questa funzione sincrona, quindi non possono mai disallinearsi.
        aggiornata_il = self._casa.aggiornata_il()
        anagrafe_letta = aggiornata_il is not None

        def _casa_per_indice() -> dict:
            # PIGRA apposta (fix review indipendente, Task B7): la chiave
            # basta a decidere un colpo a segno SENZA leggere l'anagrafe --
            # su un hit questa funzione non viene mai chiamata, e la lettura
            # SQL vera (+ json.loads per riga di `ArchivioCasa.leggi()`) non
            # si paga. A differenza di `_cerca`, dove `casa` serve comunque a
            # `_cecita()` piu' sotto e non c'e' niente da rimandare.
            return self._casa.leggi() if anagrafe_letta else {}

        # Task B7, spazio "ricorda": MAI nomi di ripiego (a differenza di
        # "cerca"), e `aggiornata_il` porta gia' la distinzione fra "anagrafe
        # letta" e "non letta" -- `None` qui e un valore vero non sono mai la
        # stessa chiave, quindi l'indice della casa vuota (non letta) e quello
        # della casa piena non si confondono mai (memoria/cache_indice.py).
        if self._cache_indice is not None:
            indice = self._cache_indice.ottieni_pigro("ricorda", _casa_per_indice, aggiornata_il)
        else:
            indice = costruisci_indice(_casa_per_indice())
        if not anagrafe_letta:
            # L'anagrafe non e' mai stata letta: NESSUNA ancora si puo'
            # verificare, non solo quelle il cui registro e' caduto -- stessa
            # distinzione di `handlers_memoria._tipi_non_verificabili`.
            tipi_non_verificabili = frozenset(_TIPI_ANCORA)
        else:
            caduti = set(self._casa.non_disponibili())
            tipi_non_verificabili = frozenset(
                tipo for tipo, chiave in CHIAVE_ARCHIVIO_PER_TIPO.items() if chiave in caduti)

        interpretazione = {
            "forza": argomenti.get("forza"),
            "grandezza": argomenti.get("grandezza"),
            "minimo": argomenti.get("minimo"),
            "massimo": argomenti.get("massimo"),
            "ancore": argomenti.get("ancore") or [],
            "condizioni": argomenti.get("condizioni") or [],
        }
        # Il CANCELLO (memoria/interpretazione.py): scarta cio' che non
        # regge (un'ancora inventata, una forza fuori vocabolario) e lo
        # DICHIARA in `problemi` -- non lo lascia passare in silenzio, e non
        # butta via l'intero ricordo per questo. E' la differenza con
        # `handlers_memoria.handle_patch_memoria`, che invece RIFIUTA
        # un'intera correzione se `problemi` non e' vuota: li' si sta
        # correggendo un ricordo gia' esistente e l'utente puo' riprovare,
        # qui si sta salvando per la prima volta cio' che qualcuno ha detto
        # -- e "preso nota, ma senza salvare niente" e' esattamente il
        # difetto da cui e' nato questo modulo (vedi il docstring in cima).
        # Le unita' VIVE: il registro di Home Assistant non le manda (le riempie
        # solo se l'utente le ha forzate a mano), quindi senza questo la
        # deduzione dell'unita' di un ricordo non e' mai scattata.
        _stato, _nomi, unita_vive, _classi, _letto = self._specchio()
        pulita, problemi, correzioni = valida(
            interpretazione, indice, tipi_non_verificabili, unita_vive)

        id_ricordo = self._memoria.ricorda(
            testo, detto_da=argomenti.get("detto_da"),
            ancore=pulita["ancore"], condizioni=pulita["condizioni"],
            forza=pulita["forza"], grandezza=pulita["grandezza"],
            minimo=pulita["minimo"], massimo=pulita["massimo"], unita=pulita["unita"],
        )
        return {"salvato": True, "id": id_ricordo, "problemi": problemi, "correzioni": correzioni}

    # -- richiama ------------------------------------------------------

    def _richiama(self, argomenti: dict[str, Any]) -> dict:
        riferimento = argomenti.get("riferimento")
        if riferimento is None:
            return {"errore": "«richiama» richiede un «riferimento»."}
        tipo = argomenti.get("tipo")
        # Fix E1-②: un `tipo` fuori dal vocabolario delle ancore ("stanza",
        # o "entita'" con l'accento -- plausibilissimo per un modello
        # italiano che non lo sta copiando da uno schema) finiva silenzioso
        # in `per_ancora(tipo, riferimento)`, che semplicemente non trova
        # mai nulla per un tipo che nessuna ancora usa: il risultato era
        # `{"ricordi": []}`, indistinguibile da "nessun ricordo riguarda
        # questa cosa" -- proprio quando invece il ricordo esiste. `guarda`
        # con un tipo ignoto almeno risponde `esiste: False`; qui si
        # dichiara l'errore invece, cosi' un input non valido resta
        # distinguibile da "non ti ho detto niente".
        if tipo is not None and tipo not in _TIPI_ANCORA:
            disponibili = ", ".join(_TIPI_ANCORA)
            return {"errore": f"«{tipo}» non e' un tipo di ancora valido per «richiama» "
                              f"({disponibili})."}
        tipi = (tipo,) if tipo else _TIPI_ANCORA

        # Il modello puo' non sapere se «cucina» e' un'area o un dispositivo
        # (o, in teoria, un'entita'): senza `tipo` si cerca su tutti e tre e
        # si uniscono i risultati, invece di pretendere che lo specifichi
        # sempre -- una ricerca che fallisce solo perche' il tipo indovinato
        # era sbagliato sarebbe un "non ho trovato niente" bugiardo.
        visti: set[int] = set()
        ricordi: list[dict] = []
        for t in tipi:
            for ricordo in self._memoria.per_ancora(t, riferimento):
                if ricordo["id"] in visti:
                    continue
                visti.add(ricordo["id"])
                ricordi.append(ricordo)
        ricordi.sort(key=lambda r: r["id"], reverse=True)
        return {"ricordi": ricordi}

    # -- esegui --------------------------------------------------------

    async def _esegui(self, argomenti: dict[str, Any]) -> dict:
        """Non fa nulla: chiede alla porta.

        E' voluto. Tutta la logica -- verifica, chiamata, rilettura, registro
        -- vive in `azione/porta.py`, perche' domani lo schedulatore e il brain
        chiederanno alla STESSA porta senza passare da qui. Se un giorno questo
        metodo cresce, la logica sta migrando nel posto sbagliato.
        """
        return await self._porta.esegui(argomenti, origine="chat")

    # -- le promesse -----------------------------------------------------

    async def _assicura_registro_fresco(self) -> None:
        """Scalda il registro dei servizi prima di verificare, se puo'.

        Stessa forma di `azione/porta.py::Porta.esegui` (righe ~598-604): un
        `try/except` attorno a `assicura_fresco`, perche' il registro si
        carica PIGRAMENTE alla prima azione ESEGUITA (`server.py`, commento
        sulla scelta) -- un add-on appena avviato che non ha ancora eseguito
        nessuna azione arriva qui con un registro presente ma VUOTO, e senza
        questa chiamata `_registro_non_pronto()` rifiuterebbe SEMPRE, anche
        quando Home Assistant e' raggiungibile e pronto a rispondere.
        Difetto misurato dal vivo su 3.9.1: «verifica le temperature di ogni
        stanza e fra un'ora mandami il delta» rifiutato con «il registro dei
        servizi non e' ancora pronto», mentre le otto temperature erano appena
        state lette correttamente (da un'altra strada, non dal registro).

        Diversa dalla porta in un punto: qui un guasto non diventa un errore
        diverso da mostrare al modello -- degrada al rifiuto onesto gia'
        scritto in `_registro_non_pronto()` ("non e' pronto"), perche' e' gia'
        la frase giusta per «non so ancora cosa questa casa sa fare»: una
        seconda frase per lo stesso fatto sarebbe un doppione.

        Senza registro (`None`, legittimo: `prometti` non lo dichiara come
        archivio richiesto in `_ARCHIVIO_PER_STRUMENTO`) o senza un canale HA
        vivo (`_canale_ha()` e' `None`, altrettanto legittimo per lo stesso
        motivo) non si tenta nemmeno: il registro non si puo' caricare senza
        un client a cui chiedere, e restare senza canale resta il rifiuto
        onesto di sempre -- non diventa "«prometti» non e' disponibile"
        (quel messaggio e' di `_archivio_mancante`, per un'altra assenza:
        aggiungere "ha" a `_ARCHIVIO_PER_STRUMENTO["prometti"]` sarebbe
        proprio quello scambio).
        """
        if self._registro is None:
            return
        canale = self._canale_ha()
        if canale is None:
            return
        try:
            await self._registro.assicura_fresco(canale)
        except Exception as errore:
            logger.warning(
                "prometti: rinfresco del registro servizi fallito (%s: %s), "
                "resta il rifiuto onesto", type(errore).__name__, errore)

    async def _prometti(self, argomenti: dict[str, Any]) -> dict:
        """Il modello propone, il codice restringe (spec §9.1).

        Tutto si verifica ADESSO: la chiamata contro questa installazione, il
        canale di notifica, il valore di partenza. Un rifiuto alle 17 sarebbe
        arrivato quando non c'e' piu' nessuno a correggerlo. `quando_ts` e i
        due tetti (30 giorni, 50 in sospeso) restano a `promessa.valida` /
        `archivio.crea`: sono verifiche sulla FORMA della promessa, non su
        questa installazione, e vivono gia' li'.

        Coroutine (non piu' sincrona) da quando questo metodo scalda il
        registro (`_assicura_registro_fresco`, sopra): il dispatcher gia'
        sapeva attendere un gestore awaitable (`dispatch`, `inspect.
        isawaitable`), quindi renderlo `async` non ha toccato nessun
        chiamante -- tutti passano gia' da `dispatch("prometti", ...)`,
        sempre atteso.
        """
        import time as _time

        from ..azione.verifica import verifica

        await self._assicura_registro_fresco()

        quando = _istante(argomenti.get("quando"))
        if quando is None:
            return {"errore": ("non ho capito quando: dammi un istante come "
                               "«2026-08-19T17:00:00+02:00».")}

        specie = argomenti.get("specie")
        dati = {
            "specie": specie,
            "frase": argomenti.get("frase") or "",
            "quando_ts": quando,
            "quando_detto": argomenti.get("quando_detto"),
            "fuso": self._fuso(),
            "recapito": argomenti.get("recapito") or None,
        }

        if specie == "fai":
            chiamata = argomenti.get("chiamata")
            if not isinstance(chiamata, dict):
                return {"errore": "una promessa «fai» ha bisogno di `chiamata`."}
            rifiuto = self._verifica_ora(chiamata, verifica)
            if rifiuto is not None:
                return {"errore": rifiuto}
            dati["chiamata"] = chiamata
        else:
            da_confrontare = argomenti.get("da_confrontare") or []
            rifiuto = self._verifica_da_confrontare(da_confrontare)
            if rifiuto is not None:
                return {"errore": rifiuto}
            dati["domanda"] = argomenti.get("domanda")
            dati["istantanea"] = self._istantanea(da_confrontare)

        if dati["recapito"]:
            rifiuto = self._verifica_recapito(dati["recapito"])
            if rifiuto is not None:
                return {"errore": rifiuto}

        return self._promesse.crea(dati, adesso=_time.time())

    def _promesse_elenco(self, argomenti: dict[str, Any]) -> dict:
        """«Cosa mi hai promesso?»: la fondamenta n.4 applicata alle promesse.

        Il nome del metodo NON puo' essere `_promesse`: quell'attributo e'
        gia' l'archivio (vedi `__init__`). Due cose distinte, due nomi.
        """
        tutte = bool(argomenti.get("tutte"))
        return {"promesse": self._promesse.elenca(solo_in_sospeso=not tutte)}

    def _disdici(self, argomenti: dict[str, Any]) -> dict:
        import time as _time

        ident = argomenti.get("id")
        if not isinstance(ident, str) or not ident.strip():
            return {"errore": "«disdici» ha bisogno dell'`id` della promessa."}
        return self._promesse.disdici(ident.strip(), adesso=_time.time())

    async def _costruisci(self, argomenti: dict[str, Any]) -> dict:
        """Propone. Non scrive: lo fa `conferma`, e non nello stesso turno."""
        import time as _time
        intento = {
            "gesto": argomenti.get("gesto"),
            "dominio": argomenti.get("dominio"),
            "chiave": argomenti.get("chiave"),
            "alias": argomenti.get("alias"),
            "descrizione": argomenti.get("descrizione") or "",
            "innesco": argomenti.get("innesco") or [],
            "condizioni": argomenti.get("condizioni") or [],
            "azioni": argomenti.get("azioni") or [],
            "stati": argomenti.get("stati") or [],
            "campi": argomenti.get("campi"),
            "parametri": argomenti.get("parametri") or [],
            "riuso": bool(argomenti.get("riuso")),
            "ricorrente": bool(argomenti.get("ricorrente")),
            "richiesto": argomenti.get("richiesto"),
            "helper": argomenti.get("helper") or [],
            "frase": argomenti.get("frase"),
        }
        return await self._officina.proponi(
            intento, origine="chat", turno=self._turno, adesso=_time.time())

    async def _conferma(self, argomenti: dict[str, Any]) -> dict:
        """Applica una proposta gia' creata da `costruisci`. La guardia del
        turno (non si conferma nel turno che ha proposto) vive nell'officina:
        qui si passa `self._turno`, la stessa identita' coniata una volta per
        turno dal chiamante (`api/handlers_chat.py`/`api/handlers_mcp.py`)."""
        import time as _time
        proposta_id = (argomenti or {}).get("proposta_id")
        if not isinstance(proposta_id, str) or not proposta_id.strip():
            return {"errore": "serve il `proposta_id` che ti ha dato `costruisci`."}
        esito = await self._officina.applica(
            proposta_id.strip(), origine="chat", turno=self._turno, adesso=_time.time())
        # Punto 7 (residuo): `guasto_rete` e' interno (`Officina._fallita`/
        # `_rete`) -- `handlers_costruzioni.py` lo toglie gia' sul percorso
        # HTTP (lo legge per scegliere 503 invece di 409, poi lo estrae dal
        # corpo). Qui, sul percorso chat, questo dizionario va DIRETTO al
        # modello: senza questa riga il flag ci arrivava integro, e «interno»
        # sarebbe stato vero da una sola delle due porte.
        esito.pop("guasto_rete", None)
        return esito

    def _verifica_ora(self, chiamata: dict, verifica) -> str | None:
        """Il rifiuto della verifica, o `None`. Sola lettura: non esegue niente.

        Non si risolvono i bersagli per aree o etichette: quella risoluzione
        chiede a Home Assistant e vive nella porta. Qui si verifica cio' che si
        puo' verificare senza rete -- il servizio esiste, l'entita' nominata
        esiste, i parametri appartengono a quel servizio -- che e' esattamente
        cio' che sbaglia il modello.

        Senza registro si RIFIUTA, non si tace piu' (fix review Task 6,
        Rilievo 2, deciso dal proprietario): e' la STESSA guardia di
        `azione/porta.py::_REGISTRO_MUTO` ("non so ancora cosa Home Assistant
        sa fare"), spostata al momento della promessa invece che
        dell'esecuzione -- due porte non devono rispondere in modo opposto
        alla stessa situazione. La frase e' diversa apposta: li' si sta
        eseguendo, qui si sta promettendo, e "riprova fra un momento" ha un
        senso diverso nei due casi. Tacere qui lascerebbe nascere un `fai`
        senza che il suo servizio sia mai stato verificato: `PROMETTI_TOOL_DEF`
        dichiara al modello "viene VERIFICATA adesso" senza condizioni, e
        prima del cablaggio del Task 7 il registro e' SEMPRE `None` in
        produzione -- quindi il silenzio avrebbe reso quella frase falsa
        proprio ora, non in un caso limite futuro.

        Dal cablaggio del Task 7 c'e' un secondo caso, raggiungibile per la
        prima volta: all'avvio il registro esiste (non e' `None`, `server.py`
        lo costruisce sempre) ma e' ancora VUOTO -- mai caricato da Home
        Assistant. Lasciare proseguire fino a `verifica()` produrrebbe «il
        dominio non esiste. Domini disponibili: .» -- la frase FALSA detta
        con sicurezza contro cui mette in guardia `azione/porta.py`
        (`_REGISTRO_MUTO`). Le due assenze raccontano lo stesso fatto («non so
        ancora cosa questa casa sa fare») e si riconoscono con lo STESSO
        criterio della porta -- si CHIEDE al registro (`domini()` vuoto), non
        si reinventa la regola in un secondo posto. Il criterio vive in
        `_registro_non_pronto()`, condiviso con `_verifica_recapito`: sono la
        STESSA domanda («so gia' cosa questa casa sa fare?»), fatta da due
        strumenti diversi -- una seconda copia della condizione sarebbe un
        doppione appena creato (review Task 7, Rilievo 1).

        Un terzo caso, trovato dalla review finale: uno specchio dello stato
        NON leggibile faceva tornare `None` (nessun rifiuto) invece di
        rifiutare -- la stessa dimenticanza del registro (Task 6) e del
        recapito (Task 7), sull'ultimo ingresso rimasto. Riusa la STESSA
        forma decisa li' -- si rifiuta, non si tace -- invece di scriverne
        una terza copia.
        """
        if self._registro_non_pronto():
            return ("non posso ancora prometterlo: non so cosa questa casa sa "
                    "fare, perche' il registro dei servizi non e' pronto. "
                    "Riprova fra un momento.")
        stati = self._stati_grezzi()
        if not stati:
            # Terza occorrenza dello stesso schema (review finale, rilievo
            # minore): il registro assente si rifiuta (Task 6), il recapito
            # non verificabile si rifiuta (Task 7), e uno specchio cieco deve
            # rifiutarsi allo stesso modo -- non tornare `None` in silenzio.
            # Prima di questo fix una `chiamata` nasceva SENZA che
            # `_verifica_ora` avesse potuto verificare l'entita' nominata,
            # mentre `PROMETTI_TOOL_DEF` dichiara al modello, senza
            # condizioni, «viene VERIFICATA adesso». Stesso criterio di
            # `azione/porta.py::_SPECCHIO_CIECO` (`None` e `{}` insieme, di
            # proposito: una casa che davvero non ha nessuna entita' non ha
            # nemmeno l'entita' bersaglio, quindi non c'e' chiamata legittima
            # che questo rifiuto possa negare). Estratta in
            # `_specchio_cieco_rifiuto()` (Task 2, R7): `_verifica_da_confrontare`
            # fa la STESSA domanda, e una seconda stringa scritta a mano li'
            # sarebbe un doppione appena creato.
            return self._specchio_cieco_rifiuto()
        verdetto = verifica(chiamata, self._registro, stati)
        if verdetto.da_risolvere:
            return None  # bersaglio per area: lo risolvera' la porta, al momento
        return None if verdetto.ok else verdetto.motivo

    def _specchio_cieco_rifiuto(self) -> str:
        """Il rifiuto quando lo specchio dello stato non e' leggibile: "non
        so ancora", non un silenzio.

        Estratta (Task 2, spec R7) perche' `_verifica_ora` e
        `_verifica_da_confrontare` fanno la STESSA domanda a
        `_stati_grezzi()` -- una seconda stringa scritta a mano in un
        secondo posto sarebbe un doppione appena creato (fondamenta n.2),
        lo stesso rilievo gia' fatto per `_registro_non_pronto`.
        """
        return ("non posso ancora prometterlo: non vedo lo stato di "
                "questa casa, l'inventario delle entita' non e' "
                "disponibile. Riprova fra un momento.")

    def _verifica_da_confrontare(self, entita: list) -> str | None:
        """Il rifiuto se `da_confrontare` nomina un riferimento che lo
        specchio non conosce, o `None`. Sola lettura, come `_verifica_ora`.

        Lista vuota -> `None` SUBITO, senza toccare lo specchio: un `chiedi`
        senza `da_confrontare` resta legittimo (spec R7, requisito 2) --
        nessuna istantanea e' stata chiesta, quindi non c'e' niente da
        verificare, e non c'e' motivo di rifiutare un `chiedi` sulla sola
        base che lo specchio non e' pronto quando nessuno lo interroga.

        Specchio non leggibile -> stesso rifiuto di `_verifica_ora`
        (`_specchio_cieco_rifiuto`, requisito 3): "non lo so ancora" si
        rifiuta, non si tace -- senza sapere cosa esiste non si puo' dire
        che un riferimento NON esiste, e lasciare nascere la promessa
        renderebbe falsa la dichiarazione di `PROMETTI_TOOL_DEF` («viene
        VERIFICATA adesso»).

        Uno specchio leggibile ma senza il riferimento -> il rifiuto vero
        (requisito 1): oggi (prima di questo fix) `_istantanea` lasciava
        nascere la promessa con `valore: null` e la nota "non esisteva
        quando l'hai chiesto" -- il danno matura fra un'ora, quando nessuno
        puo' piu' correggere. «Il modello propone, il codice restringe»
        (spec §9.1), gia' applicato al `fai` (`_verifica_ora`) e al
        recapito (`_verifica_recapito`): un `chiedi` non puo' rispondere
        diversamente alla stessa domanda solo perche' e' la terza specie.
        Il motivo nomina il riferimento (cosa non esiste) e la strada per
        correggersi (pattern `azione/verifica.py:430-432`: «usa "cerca"...»).
        """
        if not entita:
            return None
        stati = self._stati_grezzi()
        if not stati:
            return self._specchio_cieco_rifiuto()
        sconosciuti = [str(e) for e in entita if e not in stati]
        if sconosciuti:
            return ("non posso prometterlo: %s non esiste in questa casa. "
                     "Usa «cerca» per trovare l'id esatto e ripeti la "
                     "richiesta." % ", ".join(sconosciuti))
        return None

    def _registro_non_pronto(self) -> bool:
        """«Non so ancora cosa questa casa sa fare»: il registro e' assente
        (`None`) o presente ma mai caricato da Home Assistant (`domini()`
        vuoto). Le due assenze si trattano uguali -- e' lo stesso criterio di
        `azione/porta.py::Porta.esegui` per la guardia `_REGISTRO_MUTO` --
        perche' senza domini non si puo' verificare NIENTE, ne' un `fai` ne'
        un recapito. Estratta qui (review Task 7, Rilievo 1) perche'
        `_verifica_ora` e `_verifica_recapito` la interrogavano entrambe, e la
        prima la scriveva mentre la seconda restava ferma al vecchio
        `is None`: due letture della stessa domanda che potevano divergere --
        e infatti divergevano, la seconda rifiutava un recapito ESISTENTE con
        «non esiste in questa casa» invece di dire che non lo sapeva ancora.
        """
        return self._registro is None or not self._registro.domini()

    def _verifica_recapito(self, servizio: str) -> str | None:
        """Il rifiuto della verifica su un recapito, o `None`.

        Senza registro pronto si RIFIUTA (allineato a `_verifica_ora`, non
        piu' al silenzio di prima -- review Task 7, Rilievo 1): un recapito
        che HIRIS non ha potuto verificare non fallisce rumorosamente quando
        la promessa matura, fa si' che la risposta non arrivi a nessuno --
        il modo peggiore in cui una promessa puo' rompersi, perche' nessuno
        se ne accorge finche' non manca all'appuntamento.
        """
        if self._registro_non_pronto():
            return ("non posso ancora prometterlo con questo recapito: non so "
                    "cosa questa casa sa fare, perche' il registro dei "
                    "servizi non e' pronto. Riprova fra un momento.")
        if "." not in servizio:
            return "«%s» non e' un servizio: serve «notify.qualcosa»." % servizio
        dominio, nome = servizio.split(".", 1)
        if self._registro.servizio(dominio, nome) is None:
            return ("«%s» non esiste in questa casa: cerca un servizio notify "
                    "vero prima di promettere di usarlo." % servizio)
        return None

    def _istantanea(self, entita: list) -> list[dict]:
        """I valori di partenza, presi ADESSO, con la loro unita'.

        Senza l'unita' e senza l'istante, «e' aumentata» non ha un termine di
        paragone e il modello se lo inventerebbe. E' la fondamenta n.1: il `72`
        che non si sa se sia Celsius o Fahrenheit.

        `stati` (da `_stati_grezzi()`) e' la forma MINIMALE vera di
        `proxy/entity_cache.py::_to_minimal` -- non lo stato grezzo di Home
        Assistant. L'unita' vive li' nella chiave `unit` DI PRIMO LIVELLO,
        non dentro `attributes.unit_of_measurement` (quello e' HA grezzo, mai
        cio' che questo dispatcher vede): leggerla dagli attributi e' il
        difetto R6 -- l'istantanea nasceva SEMPRE senza unita' in produzione.
        `valore` invece era gia' corretto: legge `state`, che e' una chiave
        di primo livello identica in entrambe le forme.
        """
        import time as _time

        stati = self._stati_grezzi() or {}
        adesso = _time.time()
        misure = []
        for ident in entita:
            stato = stati.get(ident)
            if stato is None:
                misure.append({"entita": ident, "valore": None, "unita": None,
                               "misurato_ts": adesso,
                               "nota": "non esisteva quando l'hai chiesto"})
                continue
            misure.append({"entita": ident, "valore": stato.get("state"),
                           "unita": stato.get("unit") or None,
                           "misurato_ts": adesso})
        return misure

    def _stati_grezzi(self) -> dict[str, dict] | None:
        """Lo specchio dello stato vivo, GREZZO: entity_id -> `{state, attributes, ...}`.

        `_specchio()` ritorna mappe GIA' DERIVATE (nomi, unita', classi) per
        chi le vuole cosi'; qui serve invece la forma minima di
        `EntityCache.all_states()`, la stessa che legge
        `azione/porta.py::Porta._stati` per verificare una chiamata prima di
        eseguirla. La guardia (`inventario_leggibile`) e' la STESSA di
        `_specchio` e di `Porta._stati`: la regola «cache assente o mai
        caricata non e' un inventario leggibile» si paga in un posto solo,
        non in un terzo qui.

        `None` quando non si e' potuto guardare (cache assente, non caricata,
        o una lettura che solleva); non e' `{}`, che direbbe «guardato, casa
        vuota».
        """
        if not inventario_leggibile(self._cache):
            return None
        try:
            grezzo = self._cache.all_states()
        except Exception as errore:
            logger.warning("specchio grezzo illeggibile (%s: %s)",
                           type(errore).__name__, errore)
            return None
        stati: dict[str, dict] = {}
        for voce in grezzo or []:
            eid = voce.get("id") if isinstance(voce, dict) else None
            if eid:
                stati[eid] = voce
        return stati

    def _fuso(self) -> str | None:
        """Il fuso della casa, dalla stessa fonte del nucleo.

        `ArchivioCasa.sistema_di_riferimento()` (`casa/archivio.py`) e' l'UNICO
        accessore: rileggere `get_config` per conto proprio qui sarebbe un
        secondo posto che sa lo stesso fatto, e i due potrebbero divergere il
        giorno in cui uno dei due cambia. Senza `archivio_casa` (i test che
        costruiscono un dispatcher minimale) il fuso resta sconosciuto, e la
        promessa nasce comunque -- `fuso` e' un campo dichiarativo della
        promessa (spec §9.1), non un cancello che la blocca.
        """
        if self._casa is None:
            return None
        return self._casa.sistema_di_riferimento().get("fuso")


def _istante(grezzo) -> float | None:
    """Un ISO-8601 col fuso -> epoch. `None` se non si legge.

    Un istante SENZA fuso viene rifiutato: «alle 17» di quale fuso? E' la
    stessa regola dell'unita' di misura applicata al tempo.
    """
    from datetime import datetime

    if not isinstance(grezzo, str) or not grezzo.strip():
        return None
    try:
        momento = datetime.fromisoformat(grezzo.strip())
    except ValueError:
        return None
    if momento.tzinfo is None:
        return None
    return momento.timestamp()
