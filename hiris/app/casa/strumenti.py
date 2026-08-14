"""Gli strumenti della chat -- da trentaquattro a cinque.

Il modello riceveva un catalogo di trentaquattro strumenti, che esisteva in
TRE copie divergenti (claude_runner.py, e altre due -- vedi
docs/design/2026-08-05-la-conoscenza-di-hiris.md), e ogni azione passava da
un semaforo che di fabbrica negava tutto in silenzio. Il catalogo dei
trentaquattro e il semaforo sono usciti per intero (fetta E2 Task 8 "escono
i trentaquattro"; fetta E3 Task 7 "esce la Sentinella intera, e il semaforo
che la E2 le aveva promesso") -- oggi non esistono piu' in nessuna forma.

Qui il modello ne riceve CINQUE. Quattro leggono e ricordano; il quinto,
`esegui`, fa succedere qualcosa in casa -- ed e' l'unico. Per un tratto della
2.0 questo modulo ne offriva quattro soli e diceva «la chat CONOSCE, non
agisce»: era vero allora, non lo e' piu' dalla fetta «comandare», che ha
ridato l'azione al prodotto con un progetto proprio, dopo che la conoscenza
si era fatta solida. La differenza fra i quattro e il quinto non e' di
importanza ma di verso: i quattro LEGGONO gli archivi e lo specchio dello
stato, `esegui` SCRIVE -- e scrive per una sola strada, la porta
(`azione/porta.py`), che verifica prima e rilegge dopo.

    cerca    -- trova qualcosa per nome o alias, dichiarando le ambiguita'
    guarda   -- il dettaglio di una cosa: un'area, un'entita', un'automazione
                col suo corpo, un ricordo
    ricorda  -- salva cio' che l'utente ha detto, con le ancore alla casa
    richiama -- i ricordi che riguardano una parte della casa
    esegui   -- chiama un servizio di Home Assistant, verificato prima e
                riletto dopo: l'unico strumento che tocca la casa

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

from .archivio import ArchivioCasa
from .domande import cerca as _cerca_candidati
from .domande import guarda as _guarda_dettaglio
from ..memoria.archivio import ArchivioMemoria
from ..proxy.entity_cache import inventario_leggibile
from ..memoria.interpretazione import valida
from ..memoria.riconoscitore import CHIAVE_ARCHIVIO_PER_TIPO, costruisci_indice

# I tre tipi di ancora che la memoria conosce (memoria/interpretazione.py,
# VOCABOLARIO["ancore"]), nello stesso ordine di CHIAVE_ARCHIVIO_PER_TIPO:
# e' l'ordine in cui `richiama` cerca quando il modello non specifica un
# `tipo` -- vedi `_richiama`.
_TIPI_ANCORA = tuple(CHIAVE_ARCHIVIO_PER_TIPO)

logger = logging.getLogger(__name__)


CERCA_TOOL_DEF = {
    "name": "cerca",
    "description": (
        "Trova nella casa un'area, un'entita' o un dispositivo a partire da un "
        "nome o alias scritto in linguaggio naturale (es. «il bagno», «la "
        "lavatrice», «il termostato del salotto»). Per ogni frammento di testo "
        "riconosciuto restituisce la lista COMPLETA dei candidati che quel nome "
        "puo' significare: se una sola voce lo usa la lista ha un elemento; se "
        "piu' voci si chiamano allo stesso modo (due «Bagno» su piani diversi, "
        "un alias che collide col nome vero di un'altra area) la lista ne ha "
        "piu' di uno e il risultato e' marcato `ambiguo` -- in quel caso scegli "
        "tu, guardando il resto della conversazione, o chiedi all'utente: non "
        "prendere semplicemente il primo della lista. "
        "Se il testo non nomina niente che la casa conosca, `trovati` e' una lista "
        "vuota: non e' un errore, significa che nessun nome o alias corrisponde. "
        "**Ma una lista vuota non basta a concludere che la cosa non esista**: se la "
        "risposta porta anche `non_ho_potuto_guardare`, quella lista dice che non si e' "
        "potuto guardare dappertutto, e il motivo e' scritto li' dentro -- non "
        "riprovare la stessa ricerca, leggi il motivo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "testo": {
                "type": "string",
                "description": (
                    "Il testo in cui cercare nomi di aree, entita' o dispositivi, "
                    "cosi' come l'ha scritto l'utente (es. 'quanto fa caldo in "
                    "soggiorno?')."
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
        "HIRIS dichiarato in `origine`, non un fatto sulla casa."
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
        "«dominio.servizio» (per esempio «light.turn_off») e `bersaglio.entita`, "
        "la lista degli id ESATTI delle entita' -- non nomi liberi: se hai solo "
        "un nome o un'area, usa prima `cerca` per ottenere gli id. "
        "`dati` porta i parametri del servizio, se ne servono. "
        "La chiamata viene VERIFICATA contro questa installazione prima di "
        "partire: se il servizio non esiste, se l'entita' non esiste, o se un "
        "parametro non appartiene a quel servizio, ricevi un errore che dice "
        "cosa esiste davvero -- usalo per correggerti invece di riprovare "
        "uguale. Dopo l'esecuzione lo stato viene RILETTO: `prima`, `dopo` e "
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
                "properties": {
                    "entita": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Gli id esatti delle entita' da toccare.",
                    },
                },
                "required": ["entita"],
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

STRUMENTI_CONOSCENZA: list[dict] = [
    CERCA_TOOL_DEF, GUARDA_TOOL_DEF, RICORDA_TOOL_DEF, RICHIAMA_TOOL_DEF,
    ESEGUI_TOOL_DEF,
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
    """Collega i cinque strumenti agli archivi e alla porta -- e non altro.

    Prende `archivio_casa` e `archivio_memoria` gia' costruiti dal chiamante
    (`create_app()` o l'equivalente nei test): questa classe non ne apre
    nessuno, e non li chiude -- non le appartengono.

    `dispatch()` e' l'unico punto d'ingresso e non solleva MAI: uno
    strumento sconosciuto, argomenti mancanti, o un guasto imprevisto
    diventano tutti un dizionario con la chiave `errore`, leggibile dal
    modello -- mai un'eccezione che gli spezza il turno.
    """

    def __init__(self, archivio_casa: ArchivioCasa, archivio_memoria: ArchivioMemoria,
                 cache=None, porta=None) -> None:
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

    _ARCHIVIO_PER_STRUMENTO = {
        "cerca": ("casa",), "guarda": ("casa", "memoria"),
        "ricorda": ("casa", "memoria"), "richiama": ("memoria",),
        "esegui": ("porta",),
    }

    def _archivio_mancante(self, nome: str) -> str | None:
        """Quale archivio serve a questo strumento e non c'e'."""
        for quale in self._ARCHIVIO_PER_STRUMENTO.get(nome, ()):
            if quale == "casa" and self._casa is None:
                return "la conoscenza della casa non e' ancora stata caricata"
            if quale == "memoria" and self._memoria is None:
                return "l'archivio della memoria non e' ancora stato caricato"
            if quale == "porta" and self._porta is None:
                return "il collegamento con Home Assistant non e' disponibile"
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
            "ricorda": self._ricorda,
            "richiama": self._richiama,
            "esegui": self._esegui,
        }[nome]
        try:
            # `_esegui` e' una coroutine (fa rete); gli altri quattro no. Si
            # attende cio' che e' attendibile invece di rendere `async` anche
            # i quattro sincroni: cambiare la loro firma avrebbe toccato
            # cinque gestori per un bisogno di uno solo.
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
        _, nomi_vivi, specchio_letto = self._specchio()
        indice = costruisci_indice(casa, nomi_vivi)
        risposta: dict = {"trovati": _cerca_candidati(indice, testo)}
        cecita = self._cecita(casa, specchio_letto)
        if cecita:
            risposta["non_ho_potuto_guardare"] = cecita
        return risposta

    def _cecita(self, casa: dict, specchio_letto: bool) -> list[str]:
        """Perche' `trovati` potrebbe essere vuoto SENZA che la cosa manchi.

        Invariante 4 della fetta: «non c'e' nessuna cosa con quel nome» e «non
        ho potuto guardare» oggi hanno la stessa faccia -- una lista vuota --
        e la seconda e' cio' che ha bruciato quattro giri di `cerca` sulle
        abat-jour. Da qui hanno due facce diverse.

        Solo fatti, e solo quando ci sono: la chiave non compare quando non
        c'e' niente da dichiarare. Un elenco vuoto che dice "nessun problema"
        e' esattamente la forma che questa funzione esiste per togliere."""
        motivi: list[str] = []
        caduti = sorted(set(self._casa.non_disponibili())
                        & set(CHIAVE_ARCHIVIO_PER_TIPO.values()))
        if caduti:
            motivi.append(
                f"registri non letti all'ultima ricostruzione dell'anagrafe: "
                f"{', '.join(caduti)}. Cio' che sta li' dentro non e' cercabile adesso, "
                "e potrebbe esistere lo stesso.")
        senza_nome = sum(1 for e in casa.get("entita") or []
                         if not (e.get("nome") or "").strip() and not e.get("disabilitata"))
        if senza_nome and not (specchio_letto and inventario_leggibile(self._cache)):
            motivi.append(
                f"{senza_nome} entita' non hanno un nome nel registro di Home Assistant e "
                "lo specchio dello stato non e' leggibile: il ripiego sul nome che Home "
                "Assistant mostra non e' disponibile, quindi quelle entita' non sono "
                "cercabili per nome in questo momento.")
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
        stato, _, letto = self._specchio()
        dettaglio = _guarda_dettaglio(casa, comportamento, ricordi, stato, tipo, riferimento,
                                      non_disponibili=non_disponibili,
                                      file_non_letti=file_non_letti)
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

    def _specchio(self) -> tuple[dict[str, str], dict[str, str], bool]:
        """Lo specchio vivo in UNA lettura: `(stato, nomi, letto)`.

        Sostituisce `_stato_vivo`, non gli si affianca: `cerca` ha bisogno dei
        `friendly_name` e `guarda` dello stato, e due metodi che chiamano
        `all_states()` a turno sarebbero due letture della stessa cosa in
        istanti diversi -- la stessa classe di divergenza che il nucleo chiude
        condividendo un solo albero.

        `nomi` e' entity_id -> `friendly_name`, saltando i vuoti: la chiave
        "name" di `entity_cache._to_minimal` e' `friendly_name or ""`, e una
        stringa vuota non e' un nome, e' l'assenza di un nome.

        `letto` conserva esattamente la semantica del fix E1-(3): False solo
        quando la lettura di QUESTA chiamata e' fallita davvero. Cache assente
        resta `True` -- non e' successo niente di male, e a dire che
        l'inventario non e' guardabile ci pensa `inventario_leggibile`."""
        stato: dict[str, str] = {}
        nomi: dict[str, str] = {}
        if self._cache is None or not hasattr(self._cache, "all_states"):
            return stato, nomi, True
        try:
            for e in self._cache.all_states():
                if not isinstance(e, dict):
                    continue
                entity_id = e.get("id")
                if not entity_id:
                    continue
                stato[entity_id] = e.get("state")
                nome = e.get("name")
                if isinstance(nome, str) and nome.strip():
                    nomi[entity_id] = nome.strip()
        except Exception:
            return {}, {}, False
        return stato, nomi, True

    # -- ricorda -----------------------------------------------------------

    def _ricorda(self, argomenti: dict[str, Any]) -> dict:
        testo = argomenti.get("testo")
        if not isinstance(testo, str) or not testo.strip():
            return {"errore": "«ricorda» richiede un «testo» non vuoto."}

        anagrafe_letta = self._casa.aggiornata_il() is not None
        indice = costruisci_indice(self._casa.leggi() if anagrafe_letta else {})
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
        pulita, problemi, correzioni = valida(interpretazione, indice, tipi_non_verificabili)

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
