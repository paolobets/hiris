"""L'unico punto del prodotto che esegue qualcosa su Home Assistant.

E' l'invariante centrale della spec dell'azione: **una porta sola**. La chat
non chiama i servizi -- chiede qui. Lo schedulatore (fetta 3) e il brain
faranno lo stesso, senza che questo modulo cambi: per questo `esegui` prende
un'`origine` e non sa nulla di chi lo chiama.

Un secondo punto di scrittura SULLO STESSO CANALE e' un difetto, non
un'ottimizzazione: verifica, registro e -- il giorno in cui si affronteranno
le sicurezze -- i controlli si scrivono UNA volta e valgono per chiunque.

**Dalla fetta «costruire» i canali sono due, e le porte anche.** Questa e' la
porta dei SERVIZI. La configurazione -- automazioni, script, scene, helper --
passa da `azione/costruzione/officina.py`, che e' un modulo diverso perche' e'
un canale diverso: altra rotta di Home Assistant, altra verifica
(`validate_config` invece del registro dei servizi), altro «dopo» (un `reload`
e un'entita' che compare, non un `state_changed`). Le due porte condividono la
cronaca, l'`origine` e la forma del rifiuto. Non ci sono altre porte, e
aggiungerne una terza va discusso prima di scriverla.

Non solleva mai: ogni guasto diventa un dizionario con `errore`, perche' il
suo chiamante e' uno strumento che parla a un modello.

**I bersagli, e perche' il giro e' in due tempi.** «Spegni tutto in cucina»
obbligava il modello a chiamare `cerca`, raccogliere gli id a mano e passarli
tutti qui: se ne perdeva uno, HIRIS ne spegneva quattordici su quindici e
dichiarava di aver spento tutto. Dalla fetta «i bersagli» un'area, un piano,
un'etichetta o un dispositivo si passano come sono, e a dire cosa contengono
e' HOME ASSISTANT (`extract_from_target`). `verification()` e' pura e non puo'
chiederglielo: la porta risolve e RICHIAMA la verifica con l'elenco in mano,
cosi' la parte che dice di no resta una sola e la risoluzione non diventa un
secondo posto in cui si decide. Se quella domanda non arriva a destinazione,
il rifiuto lo dice -- `_NO_TARGET_RESOLVER` e `_target_not_resolved`
sono la terza guardia di questo modulo, con la stessa regola delle prime due:
un ingresso che non si e' potuto leggere non diventa mai un elenco piu' corto.

**I due ingressi vuoti.** `verification()` e' pura: non puo' distinguere «non
c'e'» da «non l'ho letto». Con un registro vuoto rifiuterebbe tutto dicendo
«Domini disponibili: .»; con lo specchio dello stato vuoto direbbe «l'entita'
non esiste in questa casa» di entita' che esistono. Sono la stessa cosa vista
due volte -- un ingresso vuoto che produce una frase falsa detta con
sicurezza -- e chiuderli e' compito di questa porta, che i due ingressi li
conosce. Le due guardie sono sotto, ciascuna col suo messaggio onesto.

**Da dove viene il «dopo», e perche' adesso si aspetta.** Questo e' il TERZO
tentativo sullo stesso difetto, e i primi due sono serviti a misurare cosa
NON c'e'. Il sintomo, su due case vere: HIRIS accende le luci **davvero**, e
poi racconta che non e' cambiato niente.

- **Primo tentativo: rileggere lo specchio** (`proxy/entity_cache.py`) nella
  riga subito dopo `await call_service`. Lo specchio e' alimentato dagli
  eventi `state_changed` del websocket, che arrivano su un'altra connessione
  e in un altro Task: quella rilettura legge cio' che c'era PRIMA. Non e' una
  gara che ogni tanto si perde -- si perde sempre.
- **Secondo tentativo: la lista dei cambiati che `call_service` restituisce**,
  cioe' gli stati che Home Assistant dichiara cambiati durante l'esecuzione
  del servizio. Sembrava la fonte autorevole -- li misura lui, nel momento
  giusto -- e su qualche impianto lo e'. Misurata sull'impianto vero: e' una
  lista **VUOTA**. Il log di produzione lo dice parola per parola: «la
  risposta di Home Assistant e' list, **0 voci utilizzabili**». E il ripiego
  sullo specchio riportava al difetto di partenza.

Conclusione misurata: **al ritorno di `call_service` non esiste nessuna fonte
che sappia gia' com'e' andata.** Ne' la risposta di Home Assistant, ne' lo
specchio. Resta una strada sola, ed e' aspettare che lo stato cambi davvero.

**Aspettare un segnale con una scadenza non e' dormire sperando.** Il commento
che stava qui vietava ogni attesa, e il divieto era giusto per la cosa che
vietava: una `sleep` indovina un tempo e spera. Non guarda niente -- se il
tempo indovinato e' corto racconta il falso con la stessa sicurezza di prima,
se e' lungo lo fa pagare a OGNI comando -- e trasforma un fatto in
un'ipotesi. Qui si aspetta un **evento preciso**: il `state_changed` delle
sole entita' bersaglio. L'attesa finisce nell'istante in cui l'ultima di esse
si e' fatta sentire, quindi un comando normale costa i millisecondi che Home
Assistant ci mette ad annunciarlo e non `STATE_WAIT_S`; la scadenza non e'
un tempo di attesa, e' un limite. E quando scade, l'esito **dichiara** di aver
aspettato e per quanto, invece di far passare il silenzio per una misura.
Quando HIRIS dice «non e' cambiato», adesso ha davvero guardato.

**L'ascolto si apre PRIMA della chiamata**, e non e' un dettaglio d'ordine:
l'annuncio puo' arrivare mentre `call_service` e' ancora sospesa -- su una
casa veloce arriva quasi sempre cosi' -- e un ascoltatore aperto dopo lo
avrebbe perso, ricreando lo stesso difetto in una forma piu' rara e molto piu'
difficile da vedere.

Le tre fonti del «dopo», in ordine di merito: **cio' che si e' sentito
annunciare** (misurato da Home Assistant DOPO il cambiamento, ed e' l'unico
che si e' aspettato apposta); **cio' che la chiamata ha riportato** (misurato
da lui durante l'esecuzione: vuoto su questo impianto, non su tutti); **lo
specchio**, che resta per mostrare l'ultimo valore noto invece di un `None`.
Per cio' che nessuna delle tre sa dire, si dichiara di non saperlo -- come
sempre in questo modulo.
"""
import asyncio
import logging
import time

from ..proxy.entity_cache import _to_minimal, inventario_leggibile
from .verifica import verification

logger = logging.getLogger(__name__)

# Quanto al massimo si aspetta l'annuncio, e perche' proprio questo numero.
#
# Non e' il tempo che un comando costa: e' il tempo oltre il quale si smette
# di aspettare e lo si dichiara. Un comando che funziona finisce appena
# l'ultima entita' bersaglio si e' fatta sentire -- decine di millisecondi su
# una casa locale -- e questo numero non lo tocca. Lo paga per intero solo chi
# non riceve nessun annuncio, cioe' proprio il caso in cui l'esito deve poter
# dire «ho aspettato, e non e' arrivato niente».
#
# **Due secondi** perche' il viaggio dell'annuncio e' breve e prevedibile -- il
# websocket verso Home Assistant e' gia' aperto, e sulla stessa macchina o
# sulla stessa LAN si misura in millisecondi -- mentre cio' che puo' tardare e'
# il DISPOSITIVO: una lampadina Zigbee o Z-Wave conferma tipicamente in
# 100-500 ms, e una mesh carica puo' arrivare vicino al secondo. Due secondi
# coprono quel caso con margine e restano sotto la soglia oltre la quale una
# chat sembra bloccata.
#
# Piu' corto ricomincerebbe a tagliare fuori proprio le case lente, cioe' a
# raccontare «non e' cambiato niente» di un comando riuscito: e' il difetto
# che questa attesa esiste per chiudere. Piu' lungo lo farebbe pagare a ogni
# comando che davvero non cambia niente (la luce gia' spenta, il termostato
# gia' a 21), che in una casa vera capita tutti i giorni.
STATE_WAIT_S = 2.0

# I due messaggi delle guardie. Nessuno dei due dice «non posso»: il rifiuto
# porta il motivo, e qui il motivo e' sempre lo stesso -- non ho guardato, e
# non lo spaccio per «non c'e'».
_MUTE_REGISTRY = ("non so ancora cosa Home Assistant sa fare: il registro dei "
                  "servizi e' vuoto. Non e' che questa casa non sappia fare "
                  "niente -- e' che non sono riuscito a leggerlo. Riprova fra poco.")
_BLIND_MIRROR = ("non vedo lo stato di questa casa: l'inventario delle entita' "
                   "non e' disponibile. Non posso dire se l'entita' esista, solo "
                   "che non ho potuto controllare. Riprova fra poco.")

# La terza guardia, e ha la stessa forma delle due sopra: un ingresso che non
# si e' potuto leggere non diventa mai un elenco piu' corto.
#
# **Chi lo dice non e' un dettaglio.** Un bersaglio per area, piano, etichetta
# o dispositivo lo risolve HOME ASSISTANT (`extract_from_target`). Se quella
# domanda non arriva a destinazione, HIRIS ha davanti due strade: indovinare
# quali entita' ci siano dentro -- che vuol dire spegnerne quattordici su
# quindici e dire di averle spente tutte, cioe' il difetto che questa fetta
# chiude -- oppure dirlo. Si dice.
_NO_TARGET_RESOLVER = ("questo collegamento con Home Assistant non sa risolvere "
                           "un bersaglio per area, piano, etichetta o dispositivo. "
                           "Passa gli id esatti in «bersaglio.entita»: non riduco "
                           "un'area a un elenco che mi sono immaginato.")


def _target_not_resolved(reason: str) -> str:
    return (f"non sono riuscito a chiedere a Home Assistant cosa contiene questo "
            f"bersaglio ({reason}). Non tiro a indovinare quali entita' ci siano "
            f"dentro -- non ho toccato niente. Riprova fra poco, oppure passa gli "
            f"id esatti in «bersaglio.entita».")


def _seconds(pending: float) -> str:
    """«2», non «2.0»; «0.05» resta «0.05». Il numero che l'avviso mostra
    all'utente e' lo stesso che la porta ha davvero aspettato, e si formatta
    in un posto solo perche' compare in piu' di una frase."""
    return f"{pending:g}"


# I tre avvisi dell'esito, e sono tre perche' i casi sono tre. Prima ce
# n'erano due, e quello che diceva «nessuno stato e' cambiato» ne copriva
# tre affermando una cosa che HIRIS non poteva sapere: che in casa non fosse
# cambiato niente. Da li' il modello ha tratto -- sulla casa vera -- la frase
# «probabile problema di comunicazione col dispositivo»: una diagnosi
# inventata, che ha mandato il proprietario a cercare un guasto inesistente
# mentre le luci erano spente. Un avviso e' un FATTO su cio' che HIRIS ha
# potuto vedere, mai un'ipotesi sulla causa.
#
# Due dei tre nominano la scadenza, e sono funzioni per questo: da quando la
# porta aspetta, il fatto non e' piu' «non ho visto niente» ma «ho guardato
# per TOT e non e' arrivato niente». Un avviso che tacesse il «per quanto»
# racconterebbe meno di cio' che la porta ha davvero fatto -- e la differenza
# fra le due frasi e' tutto cio' che questa correzione ha aggiunto.
def _not_seen(pending: float) -> str:
    return ("la chiamata e' partita, ma non sono riuscito a rileggere lo stato "
            f"dopo: ho aspettato {_seconds(pending)} secondi e Home Assistant non "
            "ha annunciato niente su queste entita', la chiamata non ha riportato "
            "niente e l'inventario interno non e' leggibile. Non so dire cosa sia "
            "cambiato")


def _no_change(pending: float) -> str:
    return ("la chiamata e' andata a buon fine, ho aspettato "
            f"{_seconds(pending)} secondi che Home Assistant annunciasse un "
            "cambiamento di stato su queste entita', e in quel tempo Home "
            "Assistant non ha riportato nessun cambiamento. E' un fatto su cio' "
            "che Home Assistant ha detto entro quel tempo, non una diagnosi del "
            "dispositivo: puo' voler dire che era gia' cosi', oppure che sta "
            "ancora muovendosi")


_CHANGED_NOT_SHOWABLE = ("Home Assistant ha riportato un cambiamento su queste "
                            "entita' -- annunciandolo, o dichiarandolo nella "
                            "chiamata -- ma fra i valori che HIRIS confronta non "
                            "ce n'e' nessuno diverso: il comando ha avuto effetto "
                            "su qualcosa che non so mostrare")

# Il quarto avviso, per il caso che i tre sopra non possono descrivere: un
# servizio senza `target` (`Verdict.no_target`, review finale, rilievo
# CRITICO ①). Per lui non esiste NESSUNO stato da rileggere -- zero entita',
# zero annunci da attendere -- e dire «entro N secondi Home Assistant non ha
# riportato cambiamenti» sarebbe una misura inventata su qualcosa che non si
# e' mai potuto misurare: e' precisamente la stessa disciplina di
# `_no_change`, applicata al caso in cui non c'e' NIENTE da
# guardare invece di qualcosa che non si e' mosso. Nessuna scadenza nominata:
# non se n'e' pagata nessuna (vedi `ActionActuator._call_no_target`).
_NO_STATE_TO_REREAD = ("la chiamata e' partita ed e' stata accettata: questo "
                             "servizio non ha un bersaglio, quindi non c'era "
                             "nessuno stato da rileggere.")


def _preview(verdict, resolved: dict) -> dict:
    """Cosa il bersaglio conteneva, e cosa di quello si tocca.

    C'e' solo quando il bersaglio e' stato risolto da Home Assistant: su un
    bersaglio di sole entita' non ci sarebbe niente da raccontare che
    `entita` non dica gia'.

    **Le sette voci sono tutte fatti, e nessuna e' un doppione dell'altra.**
    `chiesto` e' cio' che si e' domandato (nella forma di Home Assistant, che
    e' la forma in cui la domanda e' partita davvero); `risolte` cio' che lui
    ha risposto; `toccate` cio' su cui la chiamata parte. Fra la seconda e la
    terza ci sono le due esclusioni, ed e' li' che vive la differenza fra
    «ho spento tutto» e «ho spento le 9 luci delle 15 cose che ci sono in
    cucina»: senza dichiararle, un elenco piu' corto passerebbe per l'elenco
    intero. Aree e dispositivi chiudono il giro: dicono ATTRAVERSO cosa le
    entita' sono state trovate, che e' la sola cosa che permette di
    accorgersi che un'area conteneva un dispositivo che non ci si aspettava.

    Le chiavi ci sono sempre, anche vuote: un campo che compare a volte
    obbliga chi legge a distinguere «non e' successo» da «non me l'hanno
    detto», e qui i due casi coincidono con la lista vuota.
    """
    return {
        "chiesto": dict(verdict.target),
        "risolte": list(resolved.get("entita") or []),
        "toccate": list(verdict.entity),
        "escluse_altro_dominio": list(verdict.scartate),
        "escluse_senza_stato": list(verdict.sconosciute),
        "aree": list(resolved.get("aree") or []),
        "dispositivi": list(resolved.get("dispositivi") or []),
    }


def _fingerprint(entry) -> dict | None:
    """Cio' che di un'entita' si confronta prima e dopo: lo stato **e** gli
    attributi che lo specchio conserva.

    Il solo `state` non basta, e non era un caso di scuola: «metti il
    termostato a 21» chiama davvero `climate.set_temperature`, la casa cambia
    davvero, e `state` resta `heat` -- cambia `attributes.temperature`. Col
    confronto sul solo stato l'esito portava `cambiato: []`, il prompt
    insegna al modello a dire «e' riuscita ma nulla e' cambiato», e l'utente
    si sentiva raccontare una frase falsa con sicurezza. Vale per l'intera
    classe dei comandi parametrici -- temperatura, luminosita', posizione di
    una tapparella, volume, velocita' di un ventilatore -- cioe' per una casa
    vera tutti i giorni. **La casa vera ha poi confermato che questa parte
    funziona**: nella misura del termostato l'impronta aveva letto e riportato
    `temperature` con precisione (17.5). Sbagliata era la fonte, non lei.

    **Gli attributi sono quelli che lo specchio gia' conserva**
    (`entity_cache._DOMAIN_ATTRS`: `temperature`, `brightness`,
    `current_position`, `volume_level`, `percentage`...). Nessuno viene
    aggiunto qui: quell'elenco e' una decisione dell'inventario -- che lo
    tiene corto apposta, perche' lo legge tutto il prodotto -- non della
    porta. La conseguenza va detta invece di essere scoperta: un attributo
    che lo specchio non tiene (il colore di una luce, l'umidita' di un
    umidificatore) resta invisibile a questo confronto. Quel caso non e' piu'
    muto: se Home Assistant riporta un cambiamento che l'impronta non sa
    mostrare, l'esito lo dice con `_CHANGED_NOT_SHOWABLE` invece di
    lasciar credere che non sia successo niente.

    **Vale per tutte e tre le fonti, ed e' il motivo per cui sono
    confrontabili.** L'impronta si costruisce sempre sulla voce MINIMALE di
    `entity_cache._to_minimal`: quella dello specchio lo e' gia'; quella che
    arriva da `call_service` e quella che arriva dall'annuncio del websocket
    -- entrambe stati completi di Home Assistant -- ci passano attraverso in
    `_fingerprint_from_ha_state`. Senza quel passaggio i lati avrebbero insiemi di
    chiavi diversi e OGNI entita' risulterebbe cambiata: cioe' inventare, col
    verso opposto al difetto di prima. Passandoci, `prima` e `dopo` restano
    ricchi allo stesso modo -- per un clima portano `hvac_action` e
    `current_temperature` accanto a `temperature`, ed e' con quelli che il
    modello puo' dire non solo «da 17.5 a 19.5» ma anche «con 26.9 in stanza
    resta a riposo».

    `None` -- non `{}` -- quando dell'entita' non c'e' nessuna voce: e' la
    stessa distinzione «non ho guardato» / «ho guardato» del resto del
    modulo, ed e' cio' che il modello legge nel `dopo` di un'entita' che
    nessuna delle fonti ha saputo mostrare.
    """
    if not isinstance(entry, dict):
        return None
    fingerprint = {"state": entry.get("state")}
    # L'UNITA', che questa proiezione buttava: «adesso e' a 21, in stanza ci
    # sono 69.8» senza scala e' un numero, non un fatto -- e il modello non
    # puo' nemmeno dedurla, perche' il nucleo gli vieta esplicitamente di
    # applicare l'unita' della casa a una singola entita'. Sta nella voce
    # dello specchio (`entity_cache._to_minimal`) e costava solo il leggerla.
    unit = entry.get("unit")
    if isinstance(unit, str) and unit.strip():
        fingerprint["unit"] = unit.strip()
    attributes = entry.get("attributes")
    if isinstance(attributes, dict):
        # `state` non si lascia sovrascrivere da un attributo omonimo: la
        # chiave che dice lo stato dev'essere sempre quella.
        fingerprint.update({k: v for k, v in attributes.items() if k != "state"})
    return fingerprint


def _fingerprint_from_ha_state(reading) -> dict | None:
    """L'impronta di uno stato nella forma di Home Assistant (`entity_id`,
    `state`, `attributes` interi), da qualunque delle due bocche da cui
    arriva: il ritorno di `call_service` e l'annuncio del websocket.

    Una sola funzione per due ingressi, e non e' un risparmio di righe: se le
    due normalizzassero in modo anche solo leggermente diverso, un'entita'
    vista dall'una e un'altra vista dall'altra non sarebbero piu'
    confrontabili con lo stesso `prima`.

    Difensiva come i suoi ingressi, che sono forme di Home Assistant che
    nessuno ha scritto: cio' che non si sa leggere si SALTA -- l'entita'
    ricadra' sulla fonte successiva, e al peggio sull'onesto «non so dire
    cosa sia cambiato» -- invece di sollevare o di essere indovinato. `None`
    significa sempre e solo «non l'ho potuto leggere».
    """
    if not isinstance(reading, dict) or not reading.get("entity_id"):
        return None
    try:
        entry = _to_minimal(reading)
    except Exception as error:
        logger.warning("stato di Home Assistant illeggibile (%s: %s)",
                       type(error).__name__, error)
        return None
    return _fingerprint(entry)


def _reported_fingerprints(changed) -> dict[str, dict]:
    """Le impronte degli stati che Home Assistant dichiara cambiati.

    Ingresso: il ritorno di `HAClient.call_service`, cioe' una lista di stati
    COMPLETI di Home Assistant -- non le voci minimali dello specchio.

    **Su questo impianto e' vuota**, e la misura sta nel log di produzione:
    «0 voci utilizzabili». Resta perche' su altri impianti non lo e', ed e'
    l'unica fonte che non costa nessuna attesa: un'entita' che compare qui
    non si aspetta.
    """
    fingerprints: dict[str, dict] = {}
    for reading in changed or []:
        fingerprint = _fingerprint_from_ha_state(reading)
        if fingerprint is not None:
            fingerprints[reading["entity_id"]] = fingerprint
    return fingerprints


class _StateListener:
    """L'ascoltatore effimero delle sole entita' bersaglio: vive una
    chiamata, e alla fine viene tolto.

    Si aggancia a `HAClient.add_state_listener` -- lo stesso rubinetto che
    alimenta lo specchio (`EntityCache.on_state_changed`) -- e non apre una
    connessione propria: gli eventi arrivavano gia', il problema non e' mai
    stato riceverli, era guardare PRIMA che arrivassero.

    **Filtra sulle entita' bersaglio.** Una casa vera annuncia decine di
    cambiamenti al minuto che non dicono niente sul comando appena dato:
    contarli sarebbe la stessa invenzione di prima, col verso opposto.

    L'impronta si costruisce qui, dal `new_state` dell'evento, e non
    rileggendo lo specchio quando la sveglia suona: e' il valore che Home
    Assistant ha ANNUNCIATO, non l'ultimo che lo specchio ha memorizzato, e
    le due cose coincidono solo finche' nessuno le fa divergere.
    """

    def __init__(self, entity) -> None:
        self.udite: dict[str, dict] = {}
        self._bersagli = set(entity)
        # Chi si sta ancora aspettando. Parte da tutti e si restringe in
        # `attendi`: le entita' di cui `call_service` ha gia' detto qualcosa
        # non si aspettano.
        self._pending = set(entity)
        self._sveglia = asyncio.Event()

    def __call__(self, data) -> None:
        """Chiamata dal ciclo websocket, in modo sincrono e da un altro Task.

        Non solleva mai: un ascoltatore che esplode verrebbe soltanto loggato
        dal ciclo, e questa chiamata resterebbe appesa fino alla scadenza per
        un motivo che non ha niente a che vedere con la casa.
        """
        try:
            new = (data or {}).get("new_state")
            eid = new.get("entity_id") if isinstance(new, dict) else None
            if eid not in self._bersagli:
                return
            fingerprint = _fingerprint_from_ha_state(new)
            if fingerprint is None:
                return
            self.udite[eid] = fingerprint
            if self._pending and self._pending <= self.udite.keys():
                self._sveglia.set()
        except Exception as error:  # pragma: no cover - difesa, non un ramo
            logger.warning("annuncio di stato illeggibile (%s: %s)",
                           type(error).__name__, error)

    async def attendi(self, mancanti, deadline: float) -> bool:
        """Aspetta che `mancanti` si siano fatte sentire tutte, al massimo
        `scadenza` secondi. `True` se sono arrivate tutte in tempo.

        **Il controllo prima dell'attesa non e' un'ottimizzazione**: e' cio'
        che rende sicuro il caso in cui l'annuncio e' arrivato PRIMA, mentre
        `call_service` era ancora sospesa -- che su una casa veloce e' il
        caso normale. Fra il ritorno della chiamata e questa riga non c'e'
        nessun `await`, quindi nessun altro Task puo' infilarsi: o l'annuncio
        e' gia' in `udite` e si esce subito, o non e' ancora arrivato e sara'
        la sveglia a prenderlo.
        """
        self._pending = {e for e in mancanti if e in self._bersagli}
        if not self._pending or self._pending <= self.udite.keys():
            return True
        try:
            await asyncio.wait_for(self._sveglia.wait(), deadline)
        except TimeoutError:
            return False
        return True


class ActionActuator:
    def __init__(self, ha_client, registry, cache, journal=None) -> None:
        self._ha = ha_client
        self._registry = registry
        self._cache = cache
        # Il registro delle esecuzioni (`cronaca.py`). `None` e' legittimo e
        # non cambia niente per chi non lo passa: la porta scriveva gia' la
        # sua riga di log, e questa e' la stessa riga resa CHIEDIBILE.
        self._journal = journal

    def _states(self) -> dict[str, dict] | None:
        """Lo specchio dello stato vivo, o `None` se non l'ho potuto leggere.

        `None` non e' `{}`: uno significa «non ho guardato», l'altro «ho
        guardato e non c'era niente». E' precisamente la distinzione che
        `verification()` -- pura -- non puo' fare.

        Tre modi di non aver guardato, un solo esito: cache non cablata,
        cache mai caricata (`loaded is False`: cio' che ha dentro sono le
        entita' mosse dagli eventi, non la casa) e lettura che solleva.
        `inventario_leggibile` copre i primi due ed e' la stessa funzione che
        usa `casa/strumenti.py` -- duplicarne la regola era il modo in cui
        questo difetto e' gia' sopravvissuto altrove.

        La forma e' quella vera di `EntityCache.all_states()`: una lista di
        dizionari minimali con chiave `id` (non `entity_id`).
        """
        if not inventario_leggibile(self._cache):
            return None
        try:
            reading = self._cache.all_states()
        except Exception as error:
            logger.warning("specchio dello stato illeggibile (%s: %s)",
                           type(error).__name__, error)
            return None
        states: dict[str, dict] = {}
        for entry in reading or []:
            eid = entry.get("id") if isinstance(entry, dict) else None
            if eid:
                states[eid] = entry
        return states

    async def _resolve(self, target: dict) -> dict:
        """Cosa contiene questo bersaglio, chiesto a Home Assistant.

        Restituisce cio' che ha risposto (`ha_client.estrai_dal_bersaglio`),
        oppure `{"errore": "..."}` gia' scritto per il modello. Non ha una
        terza uscita, ed e' il punto: non esiste un ramo in cui un bersaglio
        non risolto diventi un elenco piu' corto.

        Il `getattr` non e' prudenza generica: la porta si costruisce con
        qualunque client (`ActionActuator.__init__` non ne dichiara il tipo), e
        uno che non sappia risolvere i bersagli deve produrre un rifiuto
        onesto invece di un `AttributeError` travestito da risposta.
        """
        estrai = getattr(self._ha, "estrai_dal_bersaglio", None)
        if not callable(estrai):
            logger.warning("questo client di Home Assistant non sa risolvere i "
                           "bersagli: solo le entita' nominate sono eseguibili")
            return {"errore": _NO_TARGET_RESOLVER}
        try:
            answer = await estrai(target)
        except Exception as error:
            logger.warning("bersaglio non risolto (%s: %s)",
                           type(error).__name__, error)
            return {"errore": _target_not_resolved(
                f"{type(error).__name__}: {error}")}
        if not isinstance(answer, dict):
            return {"errore": _target_not_resolved("risposta illeggibile")}
        if answer.get("errore"):
            return {"errore": _target_not_resolved(str(answer["errore"]))}
        return answer

    def _open_listen(self, listen) -> bool:
        """Aggancia l'ascoltatore effimero, o dichiara di non poterlo fare.

        Servono ENTRAMBI i metodi: un client che sa aggiungere e non sa
        togliere accumulerebbe un ascoltatore per ogni comando dato, per
        tutta la vita del processo -- una perdita silenziosa, cioe' il modo
        in cui una correzione diventa il difetto successivo.

        Non e' un ramo di comodo: e' l'unico esito onesto se un giorno questa
        porta venisse cablata su un client che non annuncia niente. Si
        prosegue con le altre due fonti e si scrive nel log che l'esito varra'
        meno, invece di rifiutare un comando legittimo.
        """
        add = getattr(self._ha, "add_state_listener", None)
        remove = getattr(self._ha, "remove_state_listener", None)
        if not callable(add) or not callable(remove):
            logger.warning("questo client di Home Assistant non annuncia i "
                           "cambiamenti di stato: l'esito potra' dire solo cio' "
                           "che la chiamata ha riportato")
            return False
        try:
            add(listen)
        except Exception as error:
            logger.warning("ascolto degli annunci non aperto (%s: %s)",
                           type(error).__name__, error)
            return False
        return True

    def _close_listen(self, listen) -> None:
        try:
            self._ha.remove_state_listener(listen)
        except Exception as error:
            logger.warning("ascolto degli annunci non chiuso (%s: %s)",
                           type(error).__name__, error)

    def _record(self, **fatti) -> str | None:
        """La riga di cronaca, se la cronaca c'e'. Non solleva MAI.

        Un registro che non si riesce a scrivere non deve poter trasformare
        un'azione riuscita in un errore: cio' che e' successo alla casa e'
        successo comunque, e tacerlo sarebbe peggio che non annotarlo.
        """
        if self._journal is None:
            return None
        try:
            return self._journal.log(now=time.time(), **fatti)
        except Exception as error:
            logger.warning("cronaca non scritta (%s: %s)",
                           type(error).__name__, error)
            return None

    async def _call_no_target(self, verdict, data: dict, actor: str) -> dict:
        """La chiamata di un servizio che non dichiara un target
        (`Verdict.no_target`): niente entita' da iniettare, niente
        stato da rileggere. Review finale, rilievo CRITICO ①.

        Non e' un caso limite delle tre fonti del «dopo» (vedi il docstring
        del modulo): e' un ramo a parte, perche' per un servizio senza
        bersaglio quelle tre fonti non hanno NIENTE su cui applicarsi -- zero
        entita', zero annunci possibili. Non si apre nemmeno l'ascolto -- e
        la ragione vera **non** e' il tempo: `_StateListener.attendi` esce
        subito quando non c'e' nessuna entita' da aspettare (`_pending`
        vuoto), quindi anche aprendolo la scadenza non si pagherebbe
        comunque (correzione della review indipendente, punto ②: qui prima
        c'era scritto il contrario). La ragione e' che per questo servizio
        non c'e' NESSUNO stato da osservare: registrare e subito dopo togliere
        un ascoltatore che non puo' mai sentire niente sarebbe un giro a
        vuoto, non una protezione da un costo. L'esito dice solo cio' che e'
        vero: la chiamata e' partita ed e' stata accettata, e non c'era
        nessuno stato da guardare -- mai «entro N secondi non e' cambiato
        niente», che sarebbe una misura inventata su qualcosa che non si e'
        mai potuto misurare.
        """
        service = f"{verdict.domain}.{verdict.service}"
        try:
            await self._ha.call_service(verdict.domain, verdict.service, data)
        except Exception as error:
            logger.warning("azione fallita [origine=%s] %s: %s",
                           actor, service, error)
            message = f"Home Assistant ha rifiutato la chiamata: {error}"
            execution_id = self._record(
                actor=actor, service=service, entity=[],
                executed=False, error=message)
            occurrence = {"eseguito": False, "errore": message}
            if execution_id is not None:
                occurrence["esecuzione_id"] = execution_id
            return occurrence

        logger.info("azione eseguita [origine=%s] %s -- nessun bersaglio: "
                    "niente stato da rileggere", actor, service)
        occurrence = {"eseguito": True, "servizio": service, "entita": [],
                 "prima": {}, "dopo": {}, "cambiato": [],
                 "avviso": _NO_STATE_TO_REREAD}
        execution_id = self._record(
            actor=actor, service=service, entity=[],
            executed=True, changed=[], notice=occurrence["avviso"])
        if execution_id is not None:
            occurrence["esecuzione_id"] = execution_id
        return occurrence

    async def execute(self, call: dict, *, actor: str) -> dict:
        try:
            await self._registry.ensure_fresh(self._ha)
        except Exception as error:
            return {"eseguito": False,
                    "errore": f"non riesco a leggere cosa Home Assistant sa fare "
                              f"({type(error).__name__}: {error})."}

        # Guardia (a). Il registro sa distinguere «mai letto» (`empty()`) da
        # «letto e vuoto», ma per chi deve agire i due casi valgono uguale:
        # senza domini non si puo' verificare niente, e lasciar proseguire
        # significherebbe far dire alla verifica «Domini disponibili: .».
        if not self._registry.domains():
            logger.warning("azione rifiutata [origine=%s]: registro dei servizi vuoto",
                           actor)
            return {"eseguito": False, "errore": _MUTE_REGISTRY}

        states_before = self._states()
        # Guardia (b). `None` e `{}` insieme, di proposito: una casa che
        # davvero non ha nessuna entita' non ha nemmeno l'entita' bersaglio,
        # quindi non c'e' chiamata legittima che questa guardia possa
        # rifiutare -- e in cambio non si nega mai un'entita' che esiste.
        if not states_before:
            logger.warning("azione rifiutata [origine=%s]: specchio dello stato non leggibile",
                           actor)
            return {"eseguito": False, "errore": _BLIND_MIRROR}

        verdict = verification(call, self._registry, states_before)
        # Il secondo tempo, e solo per i bersagli che lo chiedono: un
        # bersaglio di sole entita' non costa nessun giro di rete. La verifica
        # si rifa' INTERA con l'elenco in mano -- non si aggiunge un pezzo a
        # un verdetto gia' preso -- cosi' la parte che dice di no resta una.
        resolved = None
        if verdict.da_risolvere:
            resolved = await self._resolve(verdict.target)
            if resolved.get("errore"):
                logger.warning("azione rifiutata [origine=%s]: bersaglio %s non "
                               "risolto", actor, verdict.target)
                return {"eseguito": False, "errore": resolved["errore"]}
            verdict = verification(call, self._registry, states_before,
                                resolved=resolved)
        if not verdict.ok:
            logger.info("azione rifiutata [origine=%s]: %s", actor, verdict.reason)
            return {"eseguito": False, "errore": verdict.reason}

        # L'anteprima: cosa si toccherebbe, calcolata e detta PRIMA di
        # toccarlo. Nell'esito ci arriva in fondo, ma qui e' gia' un fatto --
        # e nel log lo e' anche quando la chiamata poi fallisce, che e'
        # l'unico momento in cui la si puo' confrontare con cio' che e'
        # successo davvero.
        preview = _preview(verdict, resolved) if resolved is not None else None
        if preview is not None:
            logger.info("azione: bersaglio %s risolto in %d entita' da toccare "
                        "(%d di altri domini, %d senza stato) [origine=%s]",
                        verdict.target, len(verdict.entity),
                        len(verdict.scartate), len(verdict.sconosciute), actor)

        data = dict(call.get("dati") or {})
        if verdict.no_target:
            # Niente da iniettare: `entity_id: []` direbbe una cosa diversa
            # da «questo servizio non ha bersaglio» (review finale, rilievo
            # CRITICO ①). Il resto della sequenza -- ascolto, attesa, le tre
            # fonti del «dopo» -- non si applica a un servizio che non ha
            # niente da rileggere, ed e' un ramo a parte apposta: vedi
            # `_call_no_target`.
            return await self._call_no_target(verdict, data, actor)
        data["entity_id"] = list(verdict.entity)

        # L'ascolto si apre PRIMA della chiamata (vedi il docstring del
        # modulo): l'annuncio puo' arrivare mentre `call_service` e' ancora
        # sospesa, e un ascoltatore aperto dopo lo perderebbe.
        #
        # La scadenza si legge UNA volta e poi si porta dietro: le frasi
        # dell'avviso e la riga di log devono nominare il numero che si e'
        # davvero aspettato, non uno riletto dopo.
        pending = STATE_WAIT_S
        listen = _StateListener(verdict.entity)
        listening = self._open_listen(listen)
        try:
            try:
                riportati = await self._ha.call_service(
                    verdict.domain, verdict.service, data)
            except Exception as error:
                logger.warning("azione fallita [origine=%s] %s.%s: %s",
                               actor, verdict.domain, verdict.service, error)
                message = f"Home Assistant ha rifiutato la chiamata: {error}"
                execution_id = self._record(
                    actor=actor,
                    service=f"{verdict.domain}.{verdict.service}",
                    entity=list(verdict.entity), executed=False, error=message)
                occurrence = {"eseguito": False, "errore": message}
                if execution_id is not None:
                    occurrence["esecuzione_id"] = execution_id
                return occurrence

            # Un'entita' di cui la chiamata ha gia' detto qualcosa non si
            # aspetta: quella misura e' presa durante l'esecuzione, cioe' nel
            # momento giusto per costruzione. Si aspettano le altre --
            # sull'impianto del proprietario, tutte.
            ha_fingerprints = _reported_fingerprints(riportati)
            if listening:
                await listen.attendi(
                    [e for e in verdict.entity if e not in ha_fingerprints], pending)
        finally:
            if listening:
                self._close_listen(listen)

        # Le tre fonti del «dopo», in ordine di merito.
        #
        # (1) L'annuncio che si e' sentito: misurato da Home Assistant DOPO
        #     il cambiamento, ed e' l'unico che si e' aspettato apposta.
        # (2) Cio' che la chiamata ha riportato: misurato da lui durante
        #     l'esecuzione. Vuoto sull'impianto del proprietario, non su tutti.
        # (3) Lo specchio, per le entita' di cui nessuna delle due ha detto
        #     niente. Non e' un doppione: e' cio' che permette di mostrare
        #     l'ultimo valore noto -- «non e' ancora cambiato» -- invece di un
        #     `None`, che vuol dire «non l'ho visto». Si legge ADESSO, dopo
        #     l'attesa, perche' nel frattempo puo' essersi mosso da solo.
        states_after = self._states()

        prima = {e: _fingerprint(states_before.get(e)) for e in verdict.entity}
        dopo: dict[str, dict | None] = {}
        for e in verdict.entity:
            fingerprint = listen.udite.get(e)
            if fingerprint is None:
                fingerprint = ha_fingerprints.get(e)
            if fingerprint is None and states_after is not None:
                fingerprint = _fingerprint(states_after.get(e))
            dopo[e] = fingerprint

        # `dopo` a `None` significa una cosa sola, e la stessa in tutto il
        # modulo: non l'ho potuto vedere. Un'entita' cosi' resta FUORI da
        # `cambiato` -- contarla direbbe che TUTTO e' cambiato, cioe'
        # inventare -- e produce l'avviso che lo dichiara.
        non_viste = [e for e in verdict.entity if dopo[e] is None]
        changed = [e for e in verdict.entity
                    if dopo[e] is not None and prima.get(e) != dopo[e]]
        # Le entita' di cui Home Assistant ha detto qualcosa, da una bocca o
        # dall'altra: e' la differenza fra «non ha detto niente» e «ha detto
        # che e' cambiato qualcosa che non so mostrare».
        annunciate = [e for e in verdict.entity if e in listen.udite]
        riportate_qui = [e for e in verdict.entity if e in ha_fingerprints]

        occurrence = {"eseguito": True,
                 "servizio": f"{verdict.domain}.{verdict.service}",
                 "entita": list(verdict.entity),
                 "prima": prima, "dopo": dopo, "cambiato": changed}
        if preview is not None:
            occurrence["bersaglio"] = preview
        if non_viste:
            occurrence["avviso"] = _not_seen(pending)
        elif changed:
            pass  # il caso normale: c'e' una differenza, e `prima`/`dopo` la mostrano
        elif annunciate or riportate_qui:
            # HA dice che qualcosa e' cambiato e l'impronta non lo mostra:
            # tipicamente un attributo fuori da `_DOMAIN_ATTRS` (il colore di
            # una luce). Dire «nessun cambiamento» qui sarebbe falso.
            occurrence["avviso"] = _CHANGED_NOT_SHOWABLE
        else:
            # Non e' un errore -- molti servizi legittimi non cambiano stato,
            # e una tapparella puo' non aver ancora finito -- ma tacerlo
            # sarebbe dire cosa e' stato CHIESTO invece di cosa e' SUCCESSO.
            # Cio' che si afferma e' solo cio' che si sa: che ENTRO LA
            # SCADENZA Home Assistant non ha riportato cambiamenti. Non che
            # la casa non sia cambiata, e tanto meno perche'.
            occurrence["avviso"] = _no_change(pending)
        logger.info("azione eseguita [origine=%s] %s su %s -- cambiati: %s "
                    "(annunciati %d, riportati dalla chiamata %d, attesi fino a %ss)",
                    actor, occurrence["servizio"], list(verdict.entity),
                    changed or ("sconosciuto" if non_viste else "nessuno"),
                    len(annunciate), len(riportate_qui), _seconds(pending))
        execution_id = self._record(
            actor=actor, service=occurrence["servizio"], entity=list(verdict.entity),
            executed=True, changed=changed, notice=occurrence.get("avviso"))
        if execution_id is not None:
            occurrence["esecuzione_id"] = execution_id
        return occurrence
