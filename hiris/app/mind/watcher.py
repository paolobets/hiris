"""L'osservatore: guarda il rubinetto dei cambi e annota, senza giudicare.

**Non apre un secondo rubinetto.** Si aggancia a `HAClient.add_state_listener`,
lo stesso che alimenta lo specchio delle entita': due sorgenti degli stessi
eventi sarebbero due cose che possono divergere.

**Non giudica niente.** Lascia passare cio' che lo scope ha deciso di guardare
(`store.is_watched`) e scrive il cambio cosi' com'e'.
Tutto il giudizio sta nell'aggregazione (`facts.py`), che e' rifacibile per
21 giorni; una decisione presa qui non si corregge piu'.
"""
from __future__ import annotations

import json
import logging
import time

from ..home_space.ha_vocabulary import (
    config_entry_is_healthy,
    config_entry_is_ignored,
    domain_of,
    has_statistics,
    is_entity_id,
)
from ..home_space.historian import instant_epoch
from ..home_space.redaction import home_assistant_seal, seal_free_text
from .knowledge import attributes_wanted_for

logger = logging.getLogger(__name__)

#: Il perche' di cio' che non e' un'entita': un problema di Home Assistant,
#: un'integrazione caduta, una voce del registro di errori, un'automazione in
#: errore. Non e' una decisione dell'osservatore -- e' la natura della cosa --
#: e sta scritto una volta perche' la pagina abbia una frase da mostrare
#: accanto a quelle righe come ne ha una accanto alle entita'.
_SYSTEM_REASON = "una condizione di sistema aperta si guarda finche' dura"

# Quali condizioni di una voce di configurazione NON siano un guasto lo dice
# `ha_vocabulary.config_entry_is_healthy`: e' vocabolario di Home Assistant
# (`ConfigEntryState`), e finche' l'elenco stava scritto qui ne esisteva un
# gemello in `home_space/briefing.py` che nessuno confrontava con questo. I due
# elencavano le due meta' della stessa enumerazione -- il guasto la' , il non
# guasto qui -- e si tenevano in piedi a vicenda senza che niente lo verificasse.
#
# **La differenza fra i due lettori resta, ed e' voluta**: qui una condizione
# che il vocabolario non conosce APRE un guasto, nel nucleo tace. Sbagliare
# costa cose diverse -- l'osservatore scrive nell'archivio, e un guasto non
# registrato e' perso per sempre; il nucleo parla al proprietario, e un falso
# allarme lo legge ogni giorno. La ragione per esteso sta accanto alle due
# funzioni in `ha_vocabulary.py`.
#
# **Effetto collaterale dichiarato** della correzione del 02/09 su `not_loaded`
# (che non e' un guasto ma lo stato INIZIALE): al primo giro dopo quella
# correzione `watch_system` non trovava piu' le otto voci nell'elenco che
# riceve, quindi le ha CHIUSE -- una riga «finito» ciascuna. Era il prezzo
# giusto (un guasto che non c'era smette di essere aperto), ma resta un evento
# scritto nell'archivio, e chi legge la storia di quel giorno deve saperlo.

# `source: "ignore"` e' una DECISIONE del proprietario, non un guasto: si
# scarta in qualunque stato, come nel nucleo. La domanda vive in
# `ha_vocabulary.config_entry_is_ignored` (B-14; Tappa 3, Task 8, 04/10/2026).

# Quanti giri consecutivi una condizione deve mancare prima di dirla finita.
#
# DUE, e i due errori non costano uguale. Il rilevatore gira ogni 10 minuti
# (`server.py`, `hiris_mind_conditions`), e `setup_retry` per costruzione
# RITENTA: un giro in cui HA non la elenca fra i problemi non significa che
# sia guarita. Misurato sulla casa il 03/09: quattro episodi per un solo
# guasto, coi tre buchi di esattamente un giro -- due giri li unificano
# tutti. Sbagliare per eccesso costa dieci minuti di ritardo nel dichiarare
# finito un guasto; sbagliare per difetto costa i cinquanta episodi che
# l'archivio porta oggi.
_ROUNDS_BEFORE_CLOSING = 2

# La forma canonica `dominio.oggetto` di un `entity_id`: una GUARDIA, la piu'
# STRETTA possibile, e la stessa del client (`ha_vocabulary.is_entity_id`,
# un'espressione sola dal 04/10/2026, B-24). La validazione va garantita A
# MONTE, qui, prima che un identificatore malformato possa entrare in
# `_marked_automations` e vivere li' dentro come se fosse un'automazione.
#
# Dal Task 6 il client non prende piu' un `entity_id` ma l'id di
# CONFIGURAZIONE, risolto dal collettore contro lo specchio: un
# identificatore malformato non ci arriverebbe comunque, perche' non si
# risolverebbe. Questa guardia resta perche' e' PRIMA -- l'insieme dei
# segnati e' cio' che il collettore rilegge a ogni cadenza, e tenerci dentro
# un identificatore che non e' un identificatore significherebbe un WARNING
# ogni due minuti, per sempre, su una cosa che non esiste.


def _text_or_none(value) -> str | None:
    """Un attributo di Home Assistant -> stringa per il grezzo, o `None`.

    Non inventa: un tipo inatteso (numero, lista, dict, stringa vuota)
    diventa `None`, non un `str(valore)` che scriverebbe testo spazzatura
    nella colonna."""
    return value if isinstance(value, str) and value.strip() else None


class Watcher:
    """Il rubinetto e le condizioni di sistema, verso l'archivio.

    `now` e' iniettabile perche' i test possano fissare l'orologio senza
    toccare il modulo `time`.
    """

    def __init__(self, store, *, now=time.time, knowledge=None) -> None:
        self._store = store
        self._now = now
        # Il sapere dice **quali attributi valga la pena tenere** per un tipo
        # (spec §5.4). E' FACOLTATIVO: senza, l'osservatore scrive come ha
        # sempre scritto e non tiene attributi. Un componente che si rompe
        # quando un altro manca non e' autonomo (quarta fondamenta), e questo
        # e' anche il caso vero di ogni prova che costruisce un osservatore
        # minimale.
        self._knowledge = knowledge
        # `(dominio, classe) -> attributi voluti`, tenuto in RAM.
        #
        # **Perche' una memoria e non due `SELECT` per evento.** La domanda si
        # farebbe PRIMA del filtro `da == a`, quindi anche sulle ~6.500 righe
        # al giorno che verranno scartate: due letture di sqlite ciascuna, per
        # una risposta che non cambia mai dentro un avvio. Il cancello
        # precedente -- `store.is_watched` -- ha il suo costo misurato accanto
        # (24 us su uno scope di 833 righe); questo non lo aveva, ed e' la
        # ragione per cui la memoria c'e' (revisione indipendente, 13/09/2026).
        #
        # **Vale finche' il sapere non cambia** (A-18, Tappa 3, Task 12): si
        # svuota quando la versione del sapere avanza (`KnowledgeStore.
        # version`). Fino al 04/10/2026 viveva quanto l'osservatore, e un
        # giudizio cambiato a caldo -- «per i termostati tieni anche
        # `hvac_action`» -- si vedeva solo al riavvio.
        self._wanted_cache: dict[tuple[str, str | None], tuple[str, ...]] = {}
        self._wanted_version: int | None = None
        # Le condizioni di sistema aperte all'ultimo giro. Serve a scrivere un
        # cambio quando NASCONO e quando FINISCONO, invece di riscriverle a
        # ogni passaggio del lavoro periodico. Vive solo in RAM: al riavvio
        # va ricostruito con `rebuild_conditions`, vedi sotto.
        self._conditions: set[str] = set()
        # Giri consecutivi in cui una condizione APERTA e' mancata
        # dall'elenco che arriva a `watch_system`, per soggetto. Vive accanto
        # a `self._conditions` e con la stessa sorte -- solo RAM, e non si
        # risemina al riavvio (`rebuild_conditions` non lo tocca): una
        # condizione vista aperta all'avvio e' aperta, zero giri mancati e'
        # il valore giusto. Un soggetto compare qui solo mentre e' mancante e
        # non ancora chiuso -- il ritorno della condizione lo toglie (il
        # contatore si azzera), la chiusura pure: non cresce senza limite.
        self._missing_rounds: dict[str, int] = {}
        # Le automazioni SEGNATE dall'evento (Task 4 di «le tracce e il
        # log»): gli `entity_id` cosi' come li ha dichiarati
        # `automation_triggered`, gia' passati da `is_entity_id` (vedi
        # `mark_automation`). Solo aggiunte, mai tolte: un'automazione che
        # ha scattato una volta resta interessante per sempre, e non c'e'
        # bisogno di "guarirla" dall'elenco. Vive solo in RAM e non si
        # risemina al riavvio: la raccolta delle tracce (`server.py`) la
        # rifara' da sola non appena l'automazione scattera' di nuovo --
        # diversamente da un guasto che DURA (sotto), qui non c'e' niente da
        # perdere restando vuoti fino al prossimo scatto.
        #
        # **Il nome non si tiene qui** (A-18, Tappa 3, Task 12, 04/10/2026).
        # Fino a quel giorno era un `entity_id -> nome` fissato al PRIMO
        # scatto, dal nome che l'evento porta: un'automazione rinominata in
        # Home Assistant restava col nome vecchio fino al riavvio. Ora il
        # nome lo dice la casa all'esito (`server.watch_automation_outcomes`
        # chiede `House.name`), e segue le rinomine.
        self._marked_automations: set[str] = set()
        # Le automazioni la cui ultima esecuzione VISTA e' un errore
        # (`watch_automation_outcome`, sotto): un sottoinsieme di soggetti
        # `automazione:` -- SEPARATO da `self._conditions` sopra, non lo
        # stesso insieme con un prefisso diverso mescolato dentro. La
        # ragione e' un'incompatibilita' vera, non una preferenza: il ciclo
        # dei "mancati" di `watch_system` (sotto) chiude ogni soggetto in
        # `self._conditions` che non ricompare nel SUO elenco (`open_now`,
        # costruito solo da problemi/integrazioni/voci di log) -- un
        # soggetto `automazione:` mescolato li' dentro sparirebbe da
        # `open_now` ad OGNI giro di `watch_system` (che non lo guarda mai)
        # e verrebbe chiuso da quel meccanismo dopo `_ROUNDS_BEFORE_CLOSING`
        # giri, indipendentemente da cosa dice davvero l'ultima traccia --
        # esattamente l'isteresi per assenza che questo verticale ha deciso
        # di NON usare (vedi il docstring di `watch_automation_outcome`).
        # Ricostruito da `rebuild_conditions` come `self._conditions`, dalla
        # STESSA lettura dell'archivio (filtrata per prefisso), per la
        # STESSA ragione: un'automazione rotta non deve dimenticare di
        # esserlo a ogni riavvio dell'add-on.
        self._automation_faults: set[str] = set()
        # Le entita' per cui Home Assistant tiene statistiche, dall'ultima
        # lettura buona di un giro (`hold_statistic_ids`); `None` finche'
        # nessun giro l'ha letta, e allora vale la regola del sorgente (B-12).
        self._statistic_ids: frozenset[str] | None = None

    # -- il rubinetto --------------------------------------------------

    def watch_reading(self, event) -> bool:
        """Il callback di `add_state_listener`. **Non solleva mai.**

        Non e' per fermare l'osservatore: il rubinetto vero (`ha_client.py`,
        `add_state_listener`) incapsula gia' ogni callback in try/except con
        `logger.exception`, quindi un'eccezione qui perderebbe **solo
        quell'evento**, non fermerebbe l'osservatore. Il try/except resta
        comunque la difesa giusta -- logga con contesto proprio (l'evento, il
        tipo di errore) invece del generico "callback raised" del rubinetto,
        e non dipende da un dettaglio di cablaggio che potrebbe cambiare.
        """
        try:
            if not isinstance(event, dict):
                return False
            eid = event.get("entity_id")
            new_state = event.get("new_state")
            if not eid or not isinstance(new_state, dict):
                # `new_state` a `None` e' un'entita' rimossa: non e' un cambio
                # da osservare, e' una cosa che non c'e' piu'.
                return False
            attributes = new_state.get("attributes")
            attributes = attributes if isinstance(attributes, dict) else {}
            # **Il cancello e' lo scope, non piu' il pavimento** (11/09/2026,
            # spec 5.1). Fino a ieri qui si chiedeva al vocabolario dei tipi a
            # quale gamba servisse l'entita': un giudizio scritto a mano una
            # volta, uguale per ogni casa, che nessuno rivedeva mai. Adesso si
            # chiede a cio' che l'osservatore ha DECISO per questa casa, con il
            # perche' scritto accanto e la possibilita' di ricredersi alla
            # cadenza di riconsiderazione (`mind/cadence.py`).
            #
            # **Chi non e' nello scope e' fuori**, che sia stato escluso o che
            # nessuno l'abbia mai considerato: in nessuno dei due casi qualcuno
            # ha deciso che pesa. Il contrario farebbe passare tutta la casa al
            # primo avvio, quando lo scope e' ancora vuoto.
            #
            # Costa **24 us** a evento (misurato l'11/09 su uno scope di 833
            # righe): una riga per chiave primaria, non un insieme da
            # ricostruire -- vedi `store.is_watched`.
            if not self._store.is_watched(str(eid)):
                return False
            old_state = event.get("old_state")
            da = old_state.get("state") if isinstance(old_state, dict) else None
            a = new_state.get("state")
            # **Non si scrive una riga dove `da == a`.** Home Assistant emette
            # `state_changed` anche per il cambio di un solo ATTRIBUTO, e
            # quella riga non dice niente su cosa e' successo in casa: lo
            # stato di partenza e quello d'arrivo sono lo stesso. Misurato
            # sulla casa vera il 10/09/2026: **6.503 righe al giorno su
            # 29.227**, di cui 6.446 dei soli otto termostati -- che di cambi
            # veri ne fanno **otto**, uno ciascuno in 24 ore.
            #
            # E sotto c'e' un secondo guasto, che questo filtro chiude per
            # forza: `last_changed` **non si muove** per un evento di solo
            # attributo (misurato: il 10/09 tutti e otto i termostati
            # portavano quello del 06/09), quindi quelle righe nascevano
            # datate a giorni prima e cadevano fuori dalla finestra del
            # giorno -- scritte, e mai lette da nessuno.
            #
            # **Dal 12/09/2026 il filtro ha un'eccezione, ed e' il punto della
            # spec §5.4**: se cambia un attributo che qualcuno ha deciso VALGA
            # LA PENA, quella riga dice qualcosa e va scritta. Lo stato di un
            # termostato e' `heat` e resta `heat` tutto il pomeriggio, mentre
            # `hvac_action` passa da `heating` a `idle` quando la casa e'
            # arrivata in temperatura -- ed e' esattamente il fatto che
            # l'esempio fondativo del cervello chiede.
            #
            # **Il guadagno misurato resta**: passa solo cio' che qualcuno ha
            # deciso che conta. Gli altri attributi -- l'icona, i
            # `supported_features`, il resto -- continuano a non far nascere
            # niente, e i 6.446 cambi al giorno degli otto termostati restano
            # fuori.
            wanted = self._wanted_attributes(str(eid), attributes)
            old_attributes = (old_state.get("attributes")
                              if isinstance(old_state, dict) else None)
            kept = {k: attributes[k] for k in wanted if k in attributes}
            if da == a and not self._wanted_changed(wanted, old_attributes, attributes):
                return False
            # **La prima delle due regole di scrittura della spec §5.3**,
            # dichiarata il 10/09/2026 e scritta il 16: *«cio' che Home
            # Assistant riassume gia' (`state_class`) non si registra a
            # campione: si legge dalle statistiche»*. Sono piu' corrette
            # (gestiscono gli azzeramenti) e durano piu' dei nostri 22 giorni;
            # copiarne ogni lettura e' scrivere due volte lo stesso fatto, e
            # la copia e' la peggiore delle due.
            #
            # **Misurato sulla casa vera il 15/09/2026**: il grezzo era il
            # TRIPLO di quanto la spec prometteva -- 13.945 righe al giorno
            # contro 4.951 -- perche' questa regola non c'era. Dei 146
            # soggetti guardati, **42 hanno statistiche**, e sono i piu'
            # loquaci. E **zero delle 44 voci di cronaca** del 14/09 venivano
            # da loro: non si perde niente di leggibile.
            #
            # **Chi ha statistiche lo dice Home Assistant** (B-12, Tappa 3,
            # Task 7, 04/10/2026): l'elenco `recorder/list_statistic_ids`
            # dell'ultimo giro che l'ha letto, e la regola del sorgente
            # (`ha_vocabulary.has_statistics`: un `sensor` con uno dei quattro
            # `state_class`) solo finche' nessun giro l'ha letto. Fino a quel
            # giorno qui c'era una formula sua -- `sensor.` e uno
            # `state_class` qualunque -- e un `sensor` che il recorder non
            # registra (escluso dal filtro, stato non numerico) si perdeva da
            # tutte e due le parti: non scritto qui, e senza statistiche la'.
            #
            # **Dopo il controllo degli attributi, non prima**: le statistiche
            # portano il NUMERO, non gli attributi (spec §5.4). Un attributo
            # che qualcuno ha deciso valga la pena dice qualcosa che nessuna
            # statistica direbbe, e passa anche qui.
            if (has_statistics(str(eid), attributes.get("state_class"), self._statistic_ids)
                    and not self._wanted_changed(wanted, old_attributes, attributes)):
                return False
            # L'istante e' quello del CAMBIO, non della scrittura: `last_changed`
            # dice quando la casa e' cambiata, il nostro orologio quando l'abbiamo
            # saputo. Annotare il secondo sposterebbe ogni oggetto di quel tanto.
            #
            # **E' `last_updated`, non `last_changed`, e la differenza morde
            # su una riga sola** (difetto trovato il 13/09/2026, e la sua
            # correzione semplificata dalla revisione su Fable lo stesso
            # giorno). `last_changed` NON si muove per un evento di solo
            # attributo -- e' scritto dieci righe sopra, misurato il 10/09 --
            # quindi una riga nata dal passaggio di `hvac_action` da `heating`
            # a `idle` nascerebbe datata all'ultimo cambio di STATO, giorni
            # prima, e cadrebbe fuori dalla finestra del giorno: scritta, e mai
            # letta da nessuno. Cioe' il guasto che il filtro chiudeva «per
            # forza», riaperto sulle stesse entita'.
            #
            # **Non serve un ramo**: per un cambio di stato vero Home Assistant
            # muove tutti e due insieme (`last_changed` si stacca da
            # `last_updated` solo quando cambia il solo attributo), quindi
            # `last_updated` e' l'istante giusto in entrambi i casi. La prima
            # correzione ne aveva scritti due, e la prova che li distingueva
            # non poteva fallire: costruiva un evento con i due istanti diversi
            # su un cambio di stato, che HA non manda mai.
            #
            # `proxy/entity_cache.py` sceglie il contrario per la
            # ragione opposta, e vale la pena leggerlo accanto a questo: li'
            # si vuole «da quando e' accesa», che un attributo non deve
            # spostare.
            when = instant_epoch(new_state.get("last_updated"))
            if when is None:
                # Ripiego dichiarato: `last_changed` sbaglia di giorni su una
                # riga di solo attributo, ma resta un istante che HA dichiara.
                when = instant_epoch(new_state.get("last_changed"))
            if when is None:
                # Qui mancano o sono illeggibili TUTTI E DUE gli istanti,
                # `last_updated` e `last_changed` (il messaggio nomina solo il
                # secondo). Se HA cambiasse il loro formato, ogni cambio
                # slitterebbe all'istante in cui
                # l'abbiamo saputo e nessuno se ne accorgerebbe. DEBUG e non
                # WARNING: capiterebbe per OGNI evento se gli istanti
                # mancassero sempre, e un WARNING per riga inonderebbe il
                # registro -- a DEBUG resta comunque disponibile a chi
                # diagnostica.
                logger.debug(
                    "osservatore: 'last_changed' mancante o illeggibile per "
                    "%s, uso l'orologio", eid)
                when = self._now()
            self._store.record(
                quando_ts=when, source="entita", subject=str(eid),
                da=da, a=a,
                device_class=_text_or_none(attributes.get("device_class")),
                state_class=_text_or_none(attributes.get("state_class")),
                source_type=_text_or_none(attributes.get("source_type")),
                # Il nome amichevole si SALVA qui, non si risolve dopo: fra
                # sei mesi l'entita' puo' non esistere piu' e il resoconto
                # resta (i `cambi` vivono 22 giorni, i resoconti finche'
                # l'utente non li cancella -- vedi `store.py::_migration_5`).
                # Costa zero: `attributes` e' gia' letto qui sopra e gia'
                # spremuto per le tre classi. E' la stringa che Home
                # Assistant ha GIA' composto (`helpers/entity.py:1161` ->
                # `entity_registry.py:592-603` @ `2026.9.1`), non una
                # ricomposta da noi da `name`/`original_name`/dispositivo.
                friendly_name=_text_or_none(attributes.get("friendly_name")),
                # Gli attributi voluti, come JSON. `None` -- non `"{}"` --
                # quando non ce n'e' nessuno: un dizionario vuoto scritto
                # direbbe «li abbiamo guardati e non c'erano», che e' un'altra
                # cosa dal non averli mai chiesti.
                attributes=json.dumps(kept, ensure_ascii=False) if kept else None)
            return True
        except Exception as error:
            logger.warning("osservatore: evento non annotato (%s: %s)",
                           type(error).__name__, error)
            return False

    def _wanted_attributes(self, entity_id: str, attributes: dict) -> tuple[str, ...]:
        """Quali attributi tenere per questa entita', secondo il sapere.

        Il tipo si compone dal dominio dell'`entity_id` e dalla `device_class`
        che l'entita' dichiara: e' la stessa coppia con cui il vocabolario dei
        tipi indicizza tutto il resto.
        """
        if self._knowledge is None:
            return ()
        domain = domain_of(entity_id)
        device_class = _text_or_none(attributes.get("device_class"))
        version = self._knowledge.version()
        if version != self._wanted_version:
            self._wanted_cache.clear()
            self._wanted_version = version
        cached = self._wanted_cache.get((domain, device_class))
        if cached is not None:
            return cached
        try:
            wanted = attributes_wanted_for(
                self._knowledge, domain=domain, device_class=device_class)
        except Exception as error:  # pragma: no cover - archivio irraggiungibile
            logger.debug("osservatore: attributi voluti non letti per %s (%s)",
                         entity_id, error)
            return ()
        self._wanted_cache[(domain, device_class)] = wanted
        return wanted

    @staticmethod
    def _wanted_changed(wanted, old_attributes, new_attributes) -> bool:
        """Se uno degli attributi VOLUTI e' cambiato fra le due letture.

        Solo quelli: confrontarli tutti farebbe nascere una riga per ogni
        icona che cambia, e il guadagno misurato del filtro tornerebbe
        indietro per intero.
        """
        if not wanted or not isinstance(old_attributes, dict):
            return False
        return any(old_attributes.get(k) != new_attributes.get(k) for k in wanted)

    # -- le automazioni --------------------------------------------------

    def mark_automation(self, entity_id: str) -> bool:
        """Segna un'automazione come scattata. **Non scrive niente**: e' il
        callback (indiretto: vedi il glue in `server.py::_on_startup`, che
        estrae `entity_id`/`name` da `event_data` di
        `AUTOMATION_TRIGGERED_EVENT`) di un evento che scatta all'INIZIO
        delle azioni, quando la traccia non e' ancora completa -- scrivere
        qui vorrebbe dire scrivere un esito che non esiste ancora (vedi
        `AUTOMATION_TRIGGERED_EVENT` in `proxy/ha_client.py` per la fonte).
        Il cambio vero -- se e quando arriva -- lo scrive
        `watch_automation_outcome`, dalla cadenza breve che rilegge le
        tracce di cio' che questo metodo ha segnato.

        **Garantisce a monte la forma `dominio.oggetto` dell'`entity_id`**
        (Task 4 di «le tracce e il log»). Un identificatore malformato
        arriverebbe da un evento HA genuino solo per un bug altrove; ma se
        arrivasse, resterebbe in `self._marked_automations` -- l'insieme che
        la cadenza breve di `server.py` rilegge OGNI due minuti -- e non c'e'
        nessun altro punto d'ingresso da cui filtrarlo dopo. Questo e'
        l'unico, quindi basta controllare qui.

        **Cosa NON e' piu' vero, dal Task 6.** Questa guardia era stata
        scritta perche' `HAClient.automation_traces()` (uscito il
        04/10/2026: il collettore legge con la raffica `HAClient.traces`) e
        lo `automation_trace()` singolare che la affiancava (uscito il
        30/09/2026) spaccavano l'`entity_id` sul primo punto: un
        identificatore malformato ci produceva un elenco vuoto silenzioso.
        Le tracce si chiedono per id di CONFIGURAZIONE, risolto dal
        collettore contro lo specchio (`proxy/entity_cache.
        automation_config_id`), e un identificatore malformato non si
        risolve. La guardia resta per la ragione detta sopra -- non
        sporcare l'insieme dei segnati -- non piu' per quella.

        **Il nome non si segna** (A-18, Tappa 3, Task 12): l'evento lo
        porta (`ATTR_NAME`), ma e' il nome di quell'istante. Lo dice la casa
        all'esito, quando si scrive (vedi il commento su
        `self._marked_automations` in `__init__`).

        Torna `True` se l'ha segnata, `False` se l'ha respinta (forma non
        valida) -- utile a chi chiama per accorgersi del rifiuto, non
        necessario a chi non se ne cura.
        """
        if not is_entity_id(entity_id):
            logger.warning(
                "osservatore: entity_id di automazione malformato, non "
                "segnato (%r)", entity_id)
            return False
        self._marked_automations.add(entity_id)
        return True

    def marked_automations(self) -> list[str]:
        """Le automazioni segnate finora, in ordine stabile -- cio' che la
        cadenza breve di `server.py` deve rileggere a ogni giro. Ordinata
        (non l'ordine di scoperta) perche' chi legge i log di due giri
        successivi possa confrontarli a colpo d'occhio."""
        return sorted(self._marked_automations)

    def watch_automation_outcome(self, entity_id: str, outcome: str, *,
                                   domain: str | None = None,
                                   title: str | None = None) -> bool:
        """L'ultimo esito noto di UN'esecuzione di un'automazione segnata,
        verso l'archivio. **Scrive un cambio solo per un esito in errore o
        per l'esito riuscito che chiude un errore aperto** -- non per
        `"finished"` quando non c'era niente da chiudere, e non per
        `"failed_conditions"` (ne' per qualunque altro valore che non sia
        `"error"` o `"finished"`) in nessun caso: **quest'ultima non e' un
        errore**, un'automazione che non agisce perche' la condizione e'
        falsa sta funzionando (la legge in testa al piano). `outcome` e' il
        valore GREZZO che HA scrive in `script_execution` sulla traccia
        (`ActionTrace.as_short_dict()`, verificato in `HAClient.
        traces()`); questo metodo legge e non giudica quali
        ALTRI valori esistano.

        **Il costo di «solo `error` apre», itemizzato (giro di correzioni,
        rilievo 4) -- non un principio, un elenco di cosa NON diventa mai
        un fatto.** Verificato alla fonte, `helpers/script.py`, tag
        `2026.9.0`: un `"aborted"` copre insieme, senza distinguerli
        (`as_short_dict` non porta altro che quella stringa),
        - **un `stop:` con `error: true`** (`_async_step_stop`,
          `CONF_ERROR`): l'AUTORE dell'automazione ha dichiarato
          esplicitamente che quel punto e' un errore, e non diventa un
          fatto lo stesso -- e' il caso piu' grave, perche' e' un giudizio
          gia' scritto da chi ha scritto l'automazione, non una nostra
          congettura, e questo metodo lo scarta comunque;
        - **una `condition:` falsa dentro la sequenza** (non la condizione
          di primo livello dell'automazione, gia' esclusa da
          `"failed_conditions"`, ma un passo `condition:` in mezzo alle
          azioni): `_ConditionFail` -> `"aborted"`, la STESSA stringa dello
          `stop: error: true` qui sopra -- «l'autore ha dichiarato un
          errore» e «una condizione era falsa» sono due fatti diversi che
          arrivano identici, e non c'e' modo di distinguerli da qui;
        - **un `wait_template` scaduto con `continue_on_timeout: false`**
          (`_async_handle_timeout`, default di `continue_on_timeout` e'
          `True`): un'attesa che non si e' mai avverata diventa `"aborted"`
          anche lei;
        - **un template di `repeat` (`until`/`while`) che non rende**
          (`_async_do_step_repeat`, `TemplateError`/`ValueError`
          intercettati): stessa sorte;
        - **la ricorsione vietata** per un'automazione in modalita'
          `restart`/`queued` che tenta di richiamare se stessa
          (`script_stack_cv`): `"disallowed_recursion_detected"`, un
          valore proprio (non `"aborted"`), ma comunque fuori da questo
          giudizio;
        - **il rifiuto di partire** per `mode: single` gia' in esecuzione
          (`"failed_single"`) o per il tetto di `max_runs` raggiunto in
          modalita' diversa da `restart` (`"failed_max_runs"`);
        - **`"cancelled"`**, per una run interrotta a meta' da un'altra:
          `_ScriptRun.async_run` lo scrive quando riprende dopo un passo e
          trova `self._stop` gia' impostato (`if self._stop.done():
          script_execution_set("cancelled"); break`). Due strade vere lo
          impostano -- `Script.async_run` per `mode: restart` con una run
          gia' in corso (`await self.async_stop(update_state=False,
          spare=run)`, la vecchia run cede il passo alla nuova) e
          `automation.turn_off` con `stop_actions` predefinito a vero
          (`AutomationEntity._async_disable` ->
          `self.action_script.async_stop()`) -- entrambe fermano
          un'esecuzione dall'ESTERNO, non un giudizio sul suo contenuto:
          rientra nello stesso scarto degli altri, non nella famiglia di
          `"aborted"`. Verificato alla fonte agli estremi della finestra
          supportata (`hiris/config.yaml:22`), tag `2024.7.0` e `2026.9.0`:
          stessa riga in entrambi.

        Nessuno di questi sette casi diventa un fatto: il piano di questo
        verticale discute solo `"finished"` e `"error"`, e un guasto non
        misurato non si inventa. **Chiude solo `"finished"`, mai
        `"aborted"`** non e' una scelta simmetrica di comodo: e' obbligata,
        perche' `"aborted"` mescola «la condizione era falsa» (funzionamento
        normale) e «l'autore ha dichiarato un errore» (un fatto mancato,
        dichiarato qui) -- trattarlo come chiusura rischierebbe di chiudere
        un episodio aperto sulla base di un segnale che potrebbe SIGNIFICARE
        l'esatto contrario.

        **Apre sull'errore, chiude sull'esito riuscito SUCCESSIVO della
        stessa automazione -- un'esecuzione riuscita chiude ma non apre
        mai.** Cosi' l'episodio ha una durata che vuol dire qualcosa
        («rotta da martedi'») invece di una riga per ogni esecuzione fallita
        (sessantaquattro esecuzioni riuscite al giorno sono il contesto, non
        fatti compiuti). Se un'automazione rotta non venisse piu' eseguita,
        l'episodio resta aperto per sempre: e' la verita' (non sappiamo se
        e' guarita), non un difetto.

        **`self._automation_faults` e non `self._conditions`.** Sono lo
        STESSO genere di bookkeeping di `watch_system` (quali soggetti
        `sistema` sono aperti ADESSO) ma un insieme separato apposta: vedi
        il commento su `self._automation_faults` in `__init__` per
        l'incompatibilita' vera con il ciclo dei "mancati" di
        `watch_system`, che chiuderebbe ogni `automazione:` dopo due giri
        solo perche' quel ciclo non lo guarda mai. **Non passa dall'isteresi
        per assenza**: quel meccanismo chiude cio' che sparisce dall'elenco
        del giro di `watch_system`, ma la raccolta delle tracce visita solo
        le automazioni SEGNATE (`marked_automations`), e l'assenza li'
        significa «non e' scattata», non «e' guarita» -- nessun conteggio
        di giri mancati per questo soggetto.

        `domain`/`title` viaggiano verso `store.record()` come per le altre
        condizioni di sistema, ma **solo sulla riga d'APERTURA** -- la
        chiusura non li porta, come gia' fa `watch_system` per le sue tre
        famiglie. `domain` resta `None` (a differenza di
        `problema:`/`integrazione:`, il dominio di un'automazione non
        varia mai -- e' sempre "automation", gia' nel prefisso del
        soggetto, e non aggiunge niente da scrivere due volte). `title`
        (giro di correzioni, rilievo 5) e' il nome dell'automazione che la
        casa da' all'esito (`House.name`, chiesto da
        `server.py::watch_automation_outcomes`; A-18) -- senza, il soggetto
        piu' raccontato dell'archivio sarebbe di nuovo un identificatore
        opaco.

        `outcome != "error" and outcome != "finished"` non tocca ne'
        l'archivio ne' `self._automation_faults`: torna `False` senza fare
        nulla, come un `outcome` gia' visto che non cambia lo stato.
        """
        subject = f"automazione:{entity_id}"
        if outcome == "error":
            if subject in self._automation_faults:
                return False
            self._store.record(quando_ts=self._now(), source="sistema",
                                  subject=subject, da=None, a=outcome,
                                  domain=domain, title=title)
            self._automation_faults.add(subject)
            return True
        if outcome == "finished":
            if subject not in self._automation_faults:
                return False
            self._store.record(quando_ts=self._now(), source="sistema",
                                  subject=subject, da=None, a="chiuso")
            self._automation_faults.discard(subject)
            return True
        return False

    # -- le condizioni di sistema --------------------------------------

    def watch_system(self, *, problems: list[dict] | None,
                       integrations: list[dict] | None,
                       log_entries: list[dict] | None) -> int:
        """Le condizioni di Home Assistant, nella STESSA forma dei cambi.

        Un'integrazione rotta non e' un cambio di stato di un'entita' -- ma il
        suo comparire e il suo sparire lo sono. Cosi' la riga del grezzo resta
        una sola, e l'oggetto che ne esce e' un guasto con la sua durata.

        Misurato sulla casa vera il 26/08: `repairs/list_issues` da' 4 problemi
        aperti, e `config_entries/get` da' 9 integrazioni non caricate su 53.
        `system_health/info` torna vuoto e non si usa.

        **`log_entries` NON ha un valore predefinito**, per lo STESSO motivo
        di `problems` e `integrations` qui sopra: nessuno dei tre e' `= None`.
        `None` qui e' trattato esattamente come `[]` (`for e in log_entries or
        []`) -- non «non l'ho letto», ma «nessuna condizione aperta», e dopo
        `_ROUNDS_BEFORE_CLOSING` giri questo METODO chiude tutto cio' che
        aveva aperto. Un default silenzioso trasformerebbe una dimenticanza
        del chiamante (un parametro non passato) nello stesso segnale di
        «ho guardato ed era tutto a posto» -- l'esatta bugia che questo
        meccanismo esiste per non dire. Costringere ogni chiamante a essere
        esplicito e' il prezzo, pagato una volta in `server.py::
        watch_system_conditions` e nei test.

        **Una voce del registro di errori (`HAClient.system_log()`, Task 1)
        e' una condizione che dura, come un *repair* o un'integrazione
        rotta**: compare, ricorre (HA la fa crescere di `count` invece di
        scriverne una seconda), sparisce. Il soggetto rispecchia la chiave
        con cui HA deduplica -- logger piu' posizione nel sorgente -- perche'
        «la stessa riga letta a due giri» deve restare lo stesso soggetto
        (vedi il commento accanto a `subject = f"log:..."` piu' sotto per la
        terza parte di quella chiave, la causa radice, che qui non e'
        esposta). La condizione (`a`) e' il LIVELLO cosi' come HA lo scrive
        (`"ERROR"`, `"WARNING"` -- **maiuscolo, non normalizzato**:
        `record.levelname`, verificato alla fonte): coerente con
        `setup_retry` qui sopra, la colonna porta la condizione vera, non
        una costante. `domain` e `title` portano il logger e la prima riga
        del messaggio, cosi' il grezzo resta autosufficiente anche quando la
        voce sara' uscita dall'elenco di HA. `count` non si scrive: e' un
        numero che HA continua a far crescere dentro il proprio
        `DedupStore`, e scriverlo sarebbe la fotografia di un contatore
        dentro un archivio che si scrive una volta sola -- cio' che questo
        metodo tiene e' la DURATA dell'episodio, non quante volte e' ricorso.

        **Un `log:` chiude anche quando NON e' guarito, e qui non e' ancora
        scritto -- lo e' gia' per la chat (giro di correzioni sul Task 7).**
        `HISTORY_TOOL_DEF` (`home_space/tools.py`, genere errori) dice all'analista che
        il registro di HA vive nella memoria di Home Assistant, non
        dell'add-on: un riavvio di HA lo svuota (riparte da zero), e porta
        comunque un TETTO di voci distinte (cinquanta per difetto,
        `DEFAULT_MAX_ENTRIES`) oltre il quale la piu' vecchia sparisce senza
        nessun riavvio. Questo metodo non lo dice mai: per lui un `log:` che
        sparisce dall'elenco che riceve e' identico a un `problema:` o
        un'`integrazione:` che sparisce, e passa dalla STESSA isteresi a due
        giri (sopra). La conseguenza vera: dopo un riavvio di Home Assistant
        (o quando il tetto delle cinquanta voci distinte espelle quella
        giusta), ogni condizione `log:` ancora aperta smette di comparire
        nell'elenco -- non perche' l'errore sia sparito, ma perche' HA ha
        dimenticato il proprio registro -- e dopo due giri (venti minuti)
        questo metodo la CHIUDE. Non e' una bugia nel codice: `"chiuso"`
        significa «sparita dall'elenco che HA manda», la stessa cosa per
        tutte e tre le famiglie, ed e' la verita' su CIO' CHE SAPPIAMO. Ma un
        lettore dell'archivio che vede un `fine` su un `log:` e conclude
        «guarito» sbaglia esattamente nel caso -- un riavvio di HA -- in cui
        e' meno probabile che sia vero: un riavvio non ripara il codice
        rotto che ha scritto quella riga, e la prossima ricorrenza aprira'
        un episodio NUOVO, non la continuazione di quello chiuso. La
        sfumatura e' scritta per chi legge lo strumento della chat
        (`tools.py`) e non per chi legge questo docstring: ora lo e' anche
        qui.

        **`quando_ts` alla nascita resta `now`, per un `log:` come per gli
        altri due.** La prima stesura di questa fetta usava `first_occurred`
        come istante di nascita ("l'episodio comincia quando HA dice che e'
        cominciato"): giusto in astratto, rotto contro `aggregate_day`, che
        legge solo la finestra del giorno e ignora in silenzio una `chiuso`
        senza apertura nel giorno. HA tiene le voci dall'ultimo suo riavvio
        -- sulla casa vera, giorni prima -- quindi una nascita scritta oggi
        con quell'istante non sarebbe mai stata aggregata, e la sua chiusura
        futura sarebbe caduta nel vuoto: un difetto pronto a scattare al
        primo deploy. `quando_ts` deve significare la STESSA cosa per ogni
        soggetto -- l'istante della riga nella NOSTRA linea del tempo --
        oppure la colonna smette di essere una colonna sola. `first_occurred`
        non si butta: prende una colonna propria in `cambi`
        (`store.py::_migration_4`) e arriva fino all'episodio accanto a
        `dominio`/`titolo` (`facts.py::aggregate_day`, chiave `comparso_ts`),
        cosi' un domani il lettore potra' avere «rilevato stamattina, va
        avanti dal 2» invece di una data sola. Verificato alla fonte
        (`homeassistant/components/system_log/__init__.py`, `LogEntry.
        __init__`: `self.first_occurred = self.timestamp = record.created`):
        e' un epoch in secondi, NON una stringa ISO-8601 -- non lo stesso
        formato di `last_changed` che `watch_reading` legge sopra, e va usato
        cosi' com'e', non attraverso `instant_epoch`.

        Le condizioni che non sono un guasto (`config_entry_is_healthy`) e le
        voci che il proprietario ha scelto di ignorare
        (`config_entry_is_ignored`) non contano: vedi i commenti accanto
        alla funzione e alla costante.

        **`open_now` porta la condizione vera, non solo il soggetto.** Prima
        qui si buttavano `domain`, `title` e `state` -- letti da questo stesso
        dizionario tre righe sopra per DECIDERE se un'integrazione e' un
        guasto, e poi scartati. Misurato sulla casa vera: il soggetto piu'
        raccontato dell'intero archivio (34 oggetti su 285 in nove giorni) era
        proprio un'integrazione, e nessuna riga diceva cosa si fosse rotto.
        Per i `problema:` (i *repairs*) non c'e' un titolo (verificato alla
        fonte su `ws_list_issues`, `components/repairs/websocket_api.py`: la
        riga porta `domain`, `issue_id`, `severity`, non un titolo) ne' uno
        stato graduato come per le integrazioni -- la condizione resta
        `"aperto"`, ed e' l'unica vera per un *repair*, non un ripiego.

        **`self._conditions` si aggiorna incrementalmente**, un soggetto alla
        volta dopo ogni `record` riuscita -- non in blocco alla fine. Se
        `record` solleva a meta', le righe gia' scritte devono restare
        ricordate: altrimenti il giro successivo le riscriverebbe con un
        istante piu' tardo, cioe' due aperture per lo stesso soggetto e una
        data di nascita ambigua per chi aggrega. Qui e' legittimo che
        l'eccezione propaghi -- il «mai sollevare» vale per `watch_reading` e
        per la ricostruzione, non per questo metodo, che gira dentro un lavoro
        periodico -- ma la memoria deve restare coerente con cio' che e' stato
        davvero scritto.

        **L'isteresi.** Il rilevatore gira ogni dieci minuti, e `setup_retry`
        per costruzione RITENTA: un giro in cui HA non elenca piu' una
        condizione fra i problemi non vuol dire che sia guarita. Misurato
        sulla casa vera il 03/09: quattro episodi per un solo guasto
        (`lifx / Abat-jour`), coi tre buchi di esattamente un giro -- era il
        nostro campionamento, non la casa. Una condizione non chiude piu' al
        primo giro in cui manca: serve `_ROUNDS_BEFORE_CLOSING` giri
        CONSECUTIVI di assenza (vedi il commento accanto alla costante per
        il perche' della soglia). Il contatore dei mancati
        (`self._missing_rounds`) si azzera appena la condizione ricompare --
        «assente due volte» non e' «assente due volte di seguito» -- e vive
        accanto a `self._conditions` con la stessa sorte: RAM, non
        riseminato al riavvio.

        **Il reset dei mancati gira PRIMA delle nuove aperture, non dopo.**
        E' pura RAM (un `dict.pop`) e non puo' fallire, a differenza di
        `record` nel ciclo delle nascite qui sotto -- se stesse dopo, un
        `record` che solleva per una condizione nata nello STESSO giro
        bloccherebbe il reset di una condizione diversa, gia' aperta, che in
        quel giro e' ricomparsa: il suo contatore resterebbe a quota vecchia,
        e un guasto missed-poi-tornato-poi-missed-di-nuovo si chiuderebbe
        dopo un solo mancato consecutivo, non due -- la stessa proprieta' che
        questo metodo esiste per garantire.
        """
        # {soggetto: (condizione, dominio, titolo, first_occurred)}. Il
        # soggetto resta l'IDENTITA' su cui girano `genre_for`,
        # `self._conditions` e `rebuild_conditions` (nessuno dei tre si tocca
        # qui): cambiarne la forma li romperebbe tutti e tre. Cio' che cambia
        # e' cosa si scrive nella colonna `a` quando quel soggetto nasce.
        # `first_occurred` e' `None` per un *repair* o un'integrazione (non
        # lo dichiarano mai) e l'epoch che HA dichiara per una voce di log --
        # va nella colonna omonima, MAI in `quando_ts` (vedi il docstring).
        open_now: dict[str, tuple[str, str | None, str | None, float | None]] = {}
        # Il sigillo dei segreti per i titoli delle voci di registro, qui
        # sotto: lo stesso della chat (`redaction.home_assistant_seal`), letto
        # una volta per giro -- uno ogni dieci minuti, quindi un
        # `secrets.yaml` cambiato vale dal giro dopo. Non solleva mai: senza
        # il file non sigilla niente, e il giro va avanti.
        seal = home_assistant_seal()
        for p in problems or []:
            if not isinstance(p, dict):
                continue
            domain = str(p.get("domain") or "").strip()
            which = str(p.get("issue_id") or "").strip()
            if domain and which:
                # Nessun titolo per un `problema:` -- vedi il docstring.
                open_now[f"problema:{domain}.{which}"] = ("aperto", domain, None, None)
        for i in integrations or []:
            if not isinstance(i, dict):
                continue
            # Stessa normalizzazione di `domain` e `title` qui sotto, non
            # una diversa: Home Assistant non manda mai uno `state` vuoto
            # (`as_json_fragment` lo emette sempre, verificato alla fonte) --
            # se arrivasse comunque malformato, `continue` lo scarta invece
            # di aprire una condizione VUOTA, che `rebuild_conditions` (che
            # considera aperto tutto cio' che non e' "chiuso" o vuoto) non
            # riconoscerebbe mai come aperta: scrittore e ricostruttore
            # devono dire la stessa cosa.
            state = _text_or_none(i.get("state"))
            if state is None:
                continue
            if config_entry_is_healthy(state):
                continue
            if config_entry_is_ignored(i.get("source")):
                continue
            ident = str(i.get("entry_id") or "").strip()
            if ident:
                open_now[f"integrazione:{ident}"] = (
                    state, _text_or_none(i.get("domain")), _text_or_none(i.get("title")), None)
        for entry in log_entries or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            level = _text_or_none(entry.get("level"))
            source = entry.get("source")
            source_file = source_line = None
            if isinstance(source, (list, tuple)) and len(source) == 2:
                source_file = _text_or_none(source[0])
                source_line = source[1]
            # Serve un logger, un livello e una posizione nel sorgente
            # leggibile -- senza uno dei tre non c'e' un'identita' stabile su
            # cui deduplicare, e aprire una condizione qui vorrebbe dire
            # aprirne una col soggetto sbagliato (o una nuova ogni giro).
            if not (name and level and source_file
                    and isinstance(source_line, int) and not isinstance(source_line, bool)):
                continue
            message = entry.get("message")
            # Il titolo passa dal sigillo dei segreti PRIMA di entrare
            # nell'archivio (Tappa 3, Task 0, 03/10/2026): e' testo libero
            # scritto da un componente qualunque, anche di terze parti, e da
            # qui arriva al resoconto del giorno e alla pagina
            # dell'osservatore. La regola e' quella della chat, una sola
            # (`redaction.seal_free_text`).
            title = (_text_or_none(seal_free_text(message[0], seal))
                     if isinstance(message, list) and message else None)
            raw_first_occurred = entry.get("first_occurred")
            # Verificato alla fonte (vedi il docstring del metodo):
            # `first_occurred` e' un epoch (`record.created`), non una
            # stringa ISO-8601 -- `bool` e' un sottotipo di `int` in Python
            # (`isinstance(True, int) is True`), e non e' un istante: senza
            # questa esclusione un `first_occurred` malformato a `True`
            # diventerebbe l'epoch fabbricato `1.0`, un istante che HA non
            # ha mai detto, invece di `None`.
            first_occurred = (float(raw_first_occurred)
                              if isinstance(raw_first_occurred, (int, float))
                              and not isinstance(raw_first_occurred, bool) else None)
            # Il soggetto rispecchia la chiave con cui HA deduplica -- logger
            # piu' posizione nel sorgente -- perche' «la stessa riga letta a
            # due giri» deve essere lo stesso soggetto. La terza parte della
            # chiave di HA (la causa radice) non e' esposta nel dizionario:
            # se due errori diversi dallo stesso punto collidessero, li
            # vedremmo come uno. Dichiarato, non ignorato.
            subject = f"log:{name}@{source_file}:{source_line}"
            open_now[subject] = (level, name, title, first_occurred)

        now = self._now()
        written = 0
        open_set = set(open_now)
        # Istantanea di cio' che era gia' aperto PRIMA di questo giro: i tre
        # casi (nasce, ricompare, manca) si decidono guardando lo stato con
        # cui il giro e' COMINCIATO, non `self._conditions` in corso di
        # mutazione sotto ai loro piedi.
        already_open = set(self._conditions)

        # Ricomparsa: gia' aperta E di nuovo nell'elenco di questo giro. Il
        # contatore dei mancati si azzera qui -- e' la differenza fra
        # «assente due volte» e «assente due volte DI SEGUITO». **Deve girare
        # PRIMA del ciclo delle nascite qui sotto**: e' pura RAM e non puo'
        # fallire, mentre quel ciclo chiama `record` e puo' sollevare a meta'
        # -- se il reset stesse dopo, un `record` che solleva per una
        # condizione nata in QUESTO STESSO giro bloccherebbe il reset di
        # un'altra condizione, gia' aperta, ricomparsa nello stesso giro (vedi
        # il docstring del metodo).
        for seen_again in already_open & open_set:
            self._missing_rounds.pop(seen_again, None)

        for born in sorted(open_set - already_open):
            condition, domain, title, first_occurred = open_now[born]
            # `a` porta la CONDIZIONE VERA, non la costante "aperto": e'
            # letteralmente lo stato verso cui la cosa e' passata, e
            # `setup_retry` non e' `setup_error`. La chiusura resta "chiuso".
            #
            # `quando_ts` e' SEMPRE `now`, anche per una voce di log: vedi il
            # docstring del metodo per il perche' (farlo significare altro
            # per un prefisso solo rompeva `aggregate_day`). `first_occurred`
            # viaggia nella sua colonna, non in `quando_ts`.
            self._store.record(
                quando_ts=now, source="sistema", subject=born, da=None,
                a=condition, domain=domain, title=title,
                first_occurred=first_occurred)
            self._conditions.add(born)
            written += 1

        for missing in sorted(already_open - open_set):
            rounds = self._missing_rounds.get(missing, 0) + 1
            if rounds < _ROUNDS_BEFORE_CLOSING:
                # Ancora dentro l'isteresi: resta aperta, si conta il giro.
                self._missing_rounds[missing] = rounds
                continue
            # `da=None`, non "aperto": la memoria in RAM (`self._conditions`)
            # tiene solo il SOGGETTO, non l'ultima condizione -- alla
            # chiusura non sappiamo piu' se era "aperto", "setup_retry" o
            # altro. `None` e' "non lo so", non una parola falsa; nessuno
            # legge `da` per le righe di sistema (ne' `rebuild_conditions`
            # ne' `facts.py`, che guardano solo `a`).
            self._store.record(quando_ts=now, source="sistema",
                                  subject=missing, da=None, a="chiuso")
            self._conditions.discard(missing)
            self._missing_rounds.pop(missing, None)
            written += 1
        return written

    def _reseal_archived_titles(self) -> None:
        """I titoli `log:` scritti prima che `watch_system` li sigillasse
        (fino alla 3.73.2), sigillati ora con la stessa regola
        (`redaction.seal_free_text`) -- decisione del proprietario del
        03/10/2026. Il registro dice **quanti**, mai quali: il valore di un
        titolo e' proprio cio' che non deve uscire. Tace quando non c'e'
        niente da sigillare, cioe' da ogni avvio dopo il primo.

        Non solleva mai, come `rebuild_conditions`: un archivio che non
        risponde lascia i titoli com'erano, non ferma l'avvio. Senza
        `secrets.yaml` non sigilla niente.
        """
        seal = home_assistant_seal()
        if not seal.readable:
            return
        try:
            rows, reports = self._store.reseal_titles(
                lambda text: seal_free_text(text, seal))
        except Exception as error:
            logger.warning("osservatore: titoli archiviati non sigillati (%s)",
                           type(error).__name__)
            return
        if rows or reports:
            logger.info("osservatore: sigillati i segreti in %d titoli archiviati "
                        "e %d resoconti", rows, reports)

    def rebuild_conditions(self) -> None:
        """Risemina `self._conditions` **e** `self._automation_faults` da
        cio' che l'archivio gia' sa (Task 4 di «le tracce e il log»: prima
        di quel task questo metodo riseminava solo `self._conditions`).

        **Perche' serve.** Ne' `self._conditions` ne' `self._automation_
        faults` sopravvivono al processo: al riavvio dell'add-on -- che
        succede a ogni aggiornamento, non in un caso limite -- entrambi
        ripartirebbero vuoti. Per `self._conditions` questo vorrebbe dire
        che `watch_system` scriverebbe di nuovo «aperto» per ogni guasto
        gia' aperto, come se fosse nato in quel momento. Per
        `self._automation_faults` il difetto e' diverso ma non meno vero:
        `watch_automation_outcome` vedrebbe un errore gia' aperto come
        assente, e (1) un esito riuscito successivo non chiuderebbe piu'
        l'episodio vecchio -- resterebbe aperto per sempre anche se
        l'automazione fosse guarita -- e (2) un errore successivo ne
        aprirebbe un SECONDO, un doppione mai chiuso del primo. La data
        d'inizio (e, per un'automazione, il fatto stesso che sia ancora
        rotta) e' l'unica informazione utile di un guasto che dura:
        sbagliarla non e' rumore, e' un fatto falso.

        Da chiamare **una volta, all'avvio**, prima che il rubinetto e il
        lavoro periodico comincino a girare.

        **Limite dichiarato, non una promessa.** Il grezzo vive 21 giorni (22
        con la guardia, vedi `mind/store.READING_RETENTION_S`). Una condizione
        aperta da piu' a lungo ha gia' perso la sua riga d'apertura con la
        potatura: qui verra' vista come nuova, e la data d'inizio (`quando_ts`)
        che l'oggetto porta sara' quella del ritrovamento, non quella vera. Non
        e' un difetto di questo metodo -- e' il pavimento dei grezzi, e chi
        legge l'oggetto deve saperlo. **Vale anche per `log:`**, da questa
        correzione: `quando_ts` alla nascita e' SEMPRE `now`, mai
        `first_occurred` (vedi il docstring di `watch_system`), quindi una
        voce di log ritrovata dopo la potatura non fa eccezione -- perde la
        stessa cosa che perde un *repair* o un'integrazione, non di piu'.
        `first_occurred`, la colonna a se' che HA continua a dichiarare a ogni
        giro finche' la voce resta nel suo registro, arriva invece fresco
        sulla nuova riga d'apertura: non e' perso, e' semplicemente diverso
        da `quando_ts`.

        **Non solleva mai.** Se l'archivio non risponde si riparte da vuoto,
        esattamente come al primissimo avvio: fermare l'avvio dell'add-on per
        questo sarebbe uno scambio peggiore.

        **Filtra `source="sistema"` NELLA query (D1 del giro di correzioni).**
        Senza, `readings()` col suo `LIMIT` teneva le righe piu' VECCHIE: sui
        320.000 cambi misurati per 22 giorni (spec §9②), dal quattordicesimo
        giorno di esercizio la ricostruzione smetteva di vedere gli ultimi
        otto -- proprio le righe che decidono l'ultimo stato di una
        condizione. Le righe di sistema sono qualche centinaio, non 320.000:
        filtrarle a monte, nella query, e' insieme la correzione del difetto e
        il modo di non caricare inutilmente tutto il resto in dizionari
        Python a ogni avvio.

        **Prima, il sigillo dei segreti sui titoli gia' archiviati**
        (`_reseal_archived_titles`, Tappa 3, Task 0): questo e' l'unico
        passo dell'avvio in cui l'osservatore rilegge il proprio archivio, e
        quelle righe sono sue.
        """
        self._reseal_archived_titles()
        try:
            # La finestra e' quella intera che l'archivio puo' avere: da zero
            # (l'inizio dei tempi, per un archivio che comunque pota da solo)
            # a `float('inf')` -- dice l'intenzione alla lettera, "nessun
            # estremo destro", invece di un `adesso + margine` arbitrario che
            # lascerebbe fuori in silenzio una riga con un istante piu' avanti
            # dell'orologio di questo processo. `readings()` lo accetta
            # (converte con `float(to_ts)`, e SQLite confronta `+Inf`
            # correttamente). Il `limit` e' esplicito e largo apposta: dice
            # al lettore che il tetto e' stato pensato per il volume delle
            # righe di SISTEMA, non ereditato dal default pensato per quello
            # delle entita'.
            rows = self._store.readings(from_ts=0.0, to_ts=float("inf"),
                                         source="sistema", limit=20_000)
        except Exception as error:
            logger.warning(
                "osservatore: stato di sistema non ricostruito, riparto da "
                "vuoto (%s: %s)", type(error).__name__, error)
            self._conditions = set()
            self._automation_faults = set()
            return

        # `readings()` torna dal piu' vecchio al piu' recente: scrivendo in
        # ordine in questo dict, l'ultima assegnazione per soggetto e' sempre
        # la piu' recente -- e' cosi' che si trova "l'ultimo stato" senza
        # dover ordinare a mano.
        #
        # Il filtro per fonte e' gia' entrato nella query (sopra): non si
        # ripete qui. Un secondo filtro Python "di scorta" maschererebbe la
        # regressione se quello nella query venisse tolto per errore -- ed e'
        # esattamente il difetto che questo metodo esiste per chiudere.
        last_state: dict[str, str | None] = {}
        for c in rows:
            if not isinstance(c, dict):
                continue
            subject = c.get("soggetto")
            if not subject:
                continue
            last_state[subject] = c.get("a")
        # **Al negativo, non al positivo.** Da Task 1, `a` porta la condizione
        # VERA dichiarata da HA (`setup_retry`, `setup_error`, ... per le
        # integrazioni; `"aperto"` resta l'unica per i `problema:`) -- e
        # l'insieme di tutte le condizioni possibili non e' enumerabile qui,
        # ne' e' compito di questo metodo conoscerlo. `"chiuso"` invece e' UNA
        # parola sola, e la scriviamo noi (vedi il commento sulla chiusura in
        # `watch_system`): e' lo stesso ragionamento di
        # `config_entry_is_healthy`, un elenco enumerabile di condizioni SANE
        # invece di uno (non enumerabile) di condizioni rotte. Un `state` vuoto o `None` -- una
        # riga che non dice niente -- non conta come aperta: non e' un fatto,
        # e' l'assenza di uno.
        #
        # **Il prefisso decide l'insieme, non due volte lo stesso filtro
        # sull'apertura** (Task 4): un `automazione:` aperto va in
        # `self._automation_faults`, ogni altro soggetto `sistema` aperto
        # (`problema:`/`integrazione:`/`log:`) va in `self._conditions` --
        # MAI mescolati, vedi il commento su `self._automation_faults` in
        # `__init__` per l'incompatibilita' vera col ciclo dei "mancati" di
        # `watch_system`.
        open_subjects = {s for s, state in last_state.items()
                         if state and state != "chiuso"}
        self._automation_faults = {s for s in open_subjects
                                   if s.startswith("automazione:")}
        self._conditions = open_subjects - self._automation_faults

    # -- la pagina -----------------------------------------------------

    def watching(self) -> list[dict]:
        """Cosa sta guardando, **perche'**, e **chi l'ha deciso**.

        Sono le tre cose da cui il proprietario puo' togliere qualcosa
        (spec 5.1 e 11, che non sono due pagine). `motivo` e' la ragione
        scritta quando la decisione e' stata presa; `autore` dice se e' stato
        l'osservatore, l'analista o il proprietario, ed e' cio' che rende la
        decisione rivedibile invece che subita.

        **Le entita' vengono dallo SCOPE, non da cio' che si e' visto
        passare.** Fino all'11/09/2026 questo elenco si riempiva osservando, e
        aveva un difetto che nessuno vedeva: un termostato acceso da giorni non
        produce cambi di stato e spariva dalla pagina che dichiara cosa si
        osserva -- cioe' proprio cio' che sta fermo. La decisione, invece, c'e'
        da prima dell'evento. Tenere anche il vecchio elenco accanto sarebbe un
        doppione che diverge alla prima entita' silenziosa.

        **Una fonte per famiglia, non una fonte sola per fatto.** Le condizioni
        di sistema (`problema:`/`integrazione:`/`log:`) vengono da
        `_conditions`, le automazioni rotte (`automazione:`) da
        `_automation_faults` -- separati apposta (vedi il commento in
        `__init__` e il docstring di `watch_automation_outcome`), e
        un'automazione con un errore aperto e' cosa sta guardando l'osservatore
        tanto quanto un'integrazione rotta.

        **Nessuna delle due famiglie di sistema passa dallo scope, e non e' una
        dimenticanza**: non sono entita', l'osservatore non le ha mai giudicate,
        e non c'e' niente da togliere -- una condizione aperta si guarda finche'
        dura. Il loro `autore` e' `None`: dire «observer» attribuirebbe a
        qualcuno una decisione che non ha preso.
        """
        entity = ({"soggetto": s, "motivo": v["motivo"], "autore": v["autore"],
                   "da_quando_ts": v["deciso_ts"]}
                  for s, v in self._store.scope().items() if v["dentro"])
        system = ({"soggetto": s, "motivo": _SYSTEM_REASON,
                   "autore": None, "da_quando_ts": None}
                  for s in self._conditions)
        automation = ({"soggetto": s, "motivo": _SYSTEM_REASON,
                       "autore": None, "da_quando_ts": None}
                      for s in self._automation_faults)
        return sorted([*entity, *system, *automation], key=lambda o: o["soggetto"])

    def hold_statistic_ids(self, reading) -> None:
        """L'elenco delle entita' con statistiche letto da un giro
        (`server.statistic_ids_for_round`), per `watch_reading` (B-12).

        Una lettura fallita -- la busta del guasto (D3), o `None` -- non
        sostituisce l'ultima buona: un guasto del websocket non deve far
        tornare il watcher alla regola, ne' fargli credere che nessuna
        entita' abbia statistiche (con l'insieme vuoto registrerebbe ogni
        `sensor`, il triplo delle righe misurato il 15/09/2026)."""
        if isinstance(reading, (set, frozenset)):
            self._statistic_ids = frozenset(reading)
