"""L'osservatore: guarda il rubinetto dei cambi e annota, senza giudicare.

**Non apre un secondo rubinetto.** Si aggancia a `HAClient.add_state_listener`,
lo stesso che alimenta lo specchio delle entita': due sorgenti degli stessi
eventi sarebbero due cose che possono divergere.

**Non giudica niente.** Filtra col pavimento e scrive il cambio cosi' com'e'.
Tutto il giudizio sta nell'aggregazione (`facts.py`), che e' rifacibile per
21 giorni; una decisione presa qui non si corregge piu'.
"""
from __future__ import annotations

import logging
import re
import time

from ..home_space.historian import instant_epoch
from .baseline import aspect

logger = logging.getLogger(__name__)

# Stati che NON sono un guasto, e sono di due specie diverse.
#
# I due transitori del boot nascono e muoiono da soli in pochi secondi: se il
# primo giro del lavoro periodico cade durante il boot, trattarli come guasto
# scriverebbe una coppia di righe di rumore (nasce, finisce) per ogni
# integrazione della casa.
#
# **`not_loaded` si e' aggiunto il 02/09, ed e' lo STESSO difetto corretto in
# `home_space/briefing.py::_BROKEN_INTEGRATION_STATES` -- qui pero' non
# produceva una riga da leggere, produceva un FATTO nell'archivio.** La
# documentazione: «NOT_LOADED: The config entry has not been loaded. **This is
# the initial state when a config entry is created or when Home Assistant is
# restarted.**» (developers.home-assistant.io/docs/config_entries_index/).
# Non e' un errore, e' lo stato iniziale. Sulla casa vera erano otto
# condizioni aperte che non erano guasti.
#
# **Effetto collaterale dichiarato**: al primo giro dopo questa correzione
# `watch_system` non trova piu' quelle otto nell'elenco che riceve, quindi le
# CHIUDE -- una riga «finito» ciascuna, con la data di oggi. E' il prezzo
# giusto (un guasto che non c'era smette di essere aperto) ma resta un evento
# scritto nell'archivio, e chi legge la storia di quel giorno deve saperlo.
#
# Valori veri di `ConfigEntryState` (`homeassistant/config_entries.py`),
# RICOPIATI e non importati dal nucleo, per la stessa ragione di
# `baseline.py`: «cosa e' un guasto QUI» e «cosa racconta l'anagrafe» sono due
# domande diverse i cui elenchi possono divergere per ragioni proprie.
_HEALTHY_INTEGRATION_STATES = frozenset({
    "setup_in_progress", "unload_in_progress", "not_loaded"})

# `source: "ignore"` e' una DECISIONE del proprietario, non un guasto: Home
# Assistant lo scrive quando qualcuno usa «ignora» sulla scoperta di
# un'integrazione, e quella voce non si caricherà più per scelta sua
# (developers.home-assistant.io/docs/config_entries_config_flow_handler/).
# Si scarta in qualunque stato, come nel nucleo.
_IGNORED_INTEGRATION_SOURCE = "ignore"

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

# La forma canonica `dominio.oggetto` di un `entity_id`. DOPPIONE
# DICHIARATO con `proxy/ha_client.py::_ENTITY_ID_RE` (stessa espressione,
# stessa intenzione: una GUARDIA, la piu' STRETTA possibile) -- non
# importata perche' quella e' privata al suo modulo, e questo file non deve
# dipendere da un dettaglio interno del client HA per una guardia che gli
# appartiene comunque (Task 4 di «le tracce e il log»: «il client non valida
# i propri argomenti, come i fratelli» -- la validazione va garantita A
# MONTE, qui, prima che un identificatore possa mai raggiungere
# `automation_traces`/`automation_trace`). Un `entity_id` senza punto (o
# comunque malformato) passato la' produrrebbe un elenco vuoto silenzioso --
# «questa automazione non ha mai girato» detto per sbaglio -- non un errore
# che si vede.
_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")


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

    def __init__(self, store, *, now=time.time) -> None:
        self._store = store
        self._now = now
        # Cosa sta guardando, e per quale gamba. Si riempie osservando: e'
        # cio' che la pagina mostra, e non una lista dichiarata a mano che
        # potrebbe divergere da cio' che succede davvero.
        self._watched: dict[str, str] = {}
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
        # log»): `entity_id -> nome amichevole` (giro di correzioni,
        # rilievo 5 -- prima un `set`, solo l'entity_id). L'entity_id e'
        # cosi' come l'ha dichiarato `automation_triggered`, gia' passato da
        # `_ENTITY_ID_RE` (vedi `mark_automation`). Solo aggiunte, mai
        # tolte -- stessa sorte di `self._watched` sopra: un'automazione che
        # ha scattato una volta resta interessante per sempre, e non c'e'
        # bisogno di "guarirla" dall'elenco. Vive solo in RAM e non si
        # risemina al riavvio, come `self._watched`: la raccolta delle
        # tracce (`server.py`) la rifara' da sola non appena l'automazione
        # scattera' di nuovo -- diversamente da un guasto che DURA (sotto),
        # qui non c'e' niente da perdere restando vuoti fino al prossimo
        # scatto.
        #
        # **Il nome si fissa al PRIMO scatto e non si aggiorna piu'**
        # (`mark_automation` sotto): se l'automazione viene rinominata in
        # HA dopo essere gia' stata segnata, il nome vecchio resta fino al
        # prossimo riavvio dell'add-on (quando l'insieme riparte vuoto e il
        # prossimo scatto legge il nome nuovo). E' grezzo dichiarato, non un
        # difetto -- lo stesso compromesso di `rebuild_conditions`, che
        # perde la data d'inizio vera oltre i 21 giorni di potatura.
        self._marked_automations: dict[str, str | None] = {}
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
            which = aspect(eid, attributes)
            if which is None:
                return False
            old_state = event.get("old_state")
            # L'istante e' quello del CAMBIO, non della scrittura: `last_changed`
            # dice quando la casa e' cambiata, il nostro orologio quando l'abbiamo
            # saputo. Annotare il secondo sposterebbe ogni oggetto di quel tanto.
            when = instant_epoch(new_state.get("last_changed"))
            if when is None:
                # Ripiego muto fino a qui: se HA cambiasse formato di
                # `last_changed`, ogni cambio slitterebbe all'istante in cui
                # l'abbiamo saputo e nessuno se ne accorgerebbe. DEBUG e non
                # WARNING: capiterebbe per OGNI evento se `last_changed`
                # mancasse sempre, e un WARNING per riga inonderebbe il
                # registro -- a DEBUG resta comunque disponibile a chi
                # diagnostica.
                logger.debug(
                    "osservatore: 'last_changed' mancante o illeggibile per "
                    "%s, uso l'orologio", eid)
                when = self._now()
            self._store.record(
                quando_ts=when, source="entita", subject=str(eid),
                da=old_state.get("state") if isinstance(old_state, dict) else None,
                a=new_state.get("state"),
                device_class=_text_or_none(attributes.get("device_class")),
                state_class=_text_or_none(attributes.get("state_class")),
                source_type=_text_or_none(attributes.get("source_type")))
            self._watched[str(eid)] = which
            return True
        except Exception as error:
            logger.warning("osservatore: evento non annotato (%s: %s)",
                           type(error).__name__, error)
            return False

    # -- le automazioni --------------------------------------------------

    def mark_automation(self, entity_id: str, *, name: str | None = None) -> bool:
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
        (Task 4 di «le tracce e il log»): `HAClient.automation_traces()` e
        `HAClient.automation_trace()` non validano i propri argomenti, come
        i loro fratelli (`problems()`, `system_log()`...) -- spaccano
        `entity_id` sul primo punto e basta. Un identificatore senza punto
        (o comunque malformato) ci arriverebbe comunque da un evento HA
        genuino solo per un bug altrove; ma se ci arrivasse, produrrebbe un
        elenco vuoto silenzioso in quei due metodi -- «questa automazione
        non ha mai girato» detto per sbaglio, non un errore che si vede.
        Un `entity_id` respinto qui non entra MAI in `self._marked_
        automations`, quindi non raggiunge mai quei due metodi: e' l'unico
        punto d'ingresso (la cadenza di `server.py` legge solo cio' che
        questo metodo ha segnato), quindi basta controllare qui.

        **`name` (giro di correzioni, rilievo 5).** L'evento porta gia' il
        nome amichevole (`ATTR_NAME`, verificato alla fonte agli estremi
        della finestra supportata -- `automation/__init__.py`, tag
        `2024.7.0` e `2026.9.0`: `event_data = {ATTR_NAME: self.name,
        ATTR_ENTITY_ID: self.entity_id}`, sempre una stringa non vuota, il
        nome che l'utente vede in HA): non usarlo ripeterebbe esattamente
        il difetto che questo sprint esiste per chiudere -- il soggetto piu'
        raccontato dell'archivio era un identificatore opaco, senza che
        nessuna riga dicesse di che cosa si trattasse (vedi il docstring di
        `watch_system` sull'apertura di `open_now`, stessa lezione). Passa
        da `_text_or_none` come ogni testo grezzo che arriva da HA.
        **Si fissa alla PRIMA segnatura e non si aggiorna piu'** (vedi il
        commento su `self._marked_automations` in `__init__`): una
        chiamata successiva per un entity_id gia' segnato non tocca il nome
        gia' salvato, nemmeno se questa porta un nome diverso (rinominata)
        o `None` (un chiamante che non lo sa).

        Torna `True` se l'ha segnata, `False` se l'ha respinta (forma non
        valida) -- utile a chi chiama per accorgersi del rifiuto, non
        necessario a chi non se ne cura.
        """
        if not isinstance(entity_id, str) or not _ENTITY_ID_RE.match(entity_id):
            logger.warning(
                "osservatore: entity_id di automazione malformato, non "
                "segnato (%r)", entity_id)
            return False
        if entity_id not in self._marked_automations:
            self._marked_automations[entity_id] = _text_or_none(name)
        return True

    def marked_automations(self) -> list[str]:
        """Le automazioni segnate finora, in ordine stabile -- cio' che la
        cadenza breve di `server.py` deve rileggere a ogni giro. Ordinata
        (non l'ordine di scoperta) perche' chi legge i log di due giri
        successivi possa confrontarli a colpo d'occhio."""
        return sorted(self._marked_automations)

    def automation_title(self, entity_id: str) -> str | None:
        """Il nome amichevole segnato per `entity_id` da `mark_automation`,
        o `None` se non e' mai stata segnata o non portava un nome
        leggibile. E' cio' che la cadenza breve di `server.py` passa come
        `title=` a `watch_automation_outcome` -- vedi il docstring di
        `mark_automation` per da dove viene e perche' non si aggiorna."""
        return self._marked_automations.get(entity_id)

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
        automation_traces()`); questo metodo legge e non giudica quali
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
          modalita' diversa da `restart` (`"failed_max_runs"`).

        Nessuno di questi sei casi diventa un fatto: il piano di questo
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
        (giro di correzioni, rilievo 5) e' il nome amichevole segnato da
        `mark_automation` (`Watcher.automation_title(entity_id)`, che
        `server.py::watch_automation_outcomes` legge e passa qui) -- senza,
        il soggetto piu' raccontato dell'archivio sarebbe di nuovo un
        identificatore opaco.

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

        Gli stati che non sono un guasto (`_HEALTHY_INTEGRATION_STATES`) e le
        voci che il proprietario ha scelto di ignorare
        (`_IGNORED_INTEGRATION_SOURCE`) non contano: vedi i commenti accanto
        alle due costanti.

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
            if state == "loaded" or state in _HEALTHY_INTEGRATION_STATES:
                continue
            if str(i.get("source") or "").strip() == _IGNORED_INTEGRATION_SOURCE:
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
            title = (_text_or_none(message[0])
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
        con la guardia, vedi `archivio.READING_RETENTION_S`). Una condizione
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
        """
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
        # `watch_system`): e' lo stesso ragionamento di `_HEALTHY_INTEGRATION_
        # STATES` qui sopra, un elenco enumerabile di stati SANI invece di uno
        # (non enumerabile) di stati rotti. Un `state` vuoto o `None` -- una
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
        """Cosa sta guardando, e perche'.

        `provenienza` distingue cio' che e' nel **pavimento** (e non si toglie)
        da cio' che l'**obiettivo** ha aggiunto (e si puo' togliere). Oggi tutto
        e' pavimento: il prompt dell'obiettivo entra nella fetta successiva, e
        la terza provenienza -- «me l'ha chiesto l'analista» -- con lui.

        **Una fonte sola per fatto.** Le entita' vengono da `_watched`, le
        condizioni di sistema da `_conditions` -- non si semina `_watched` con
        le condizioni per rattoppare: sarebbe tenere in vita un doppione, e
        due risposte alla stessa domanda divergono (dopo un riavvio un
        guasto ricostruito sparirebbe da qui per sempre; all'opposto, una
        condizione chiusa scritta anche qui non verrebbe mai tolta).
        """
        entity = ({"soggetto": s, "gamba": g, "provenienza": "pavimento"}
                  for s, g in self._watched.items())
        system = ({"soggetto": s, "gamba": "buono stato", "provenienza": "pavimento"}
                   for s in self._conditions)
        return sorted([*entity, *system], key=lambda o: (o["gamba"], o["soggetto"]))
