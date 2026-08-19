"""L'unico punto del prodotto che esegue qualcosa su Home Assistant.

E' l'invariante centrale della spec dell'azione: **una porta sola**. La chat
non chiama i servizi -- chiede qui. Lo schedulatore (fetta 3) e il brain
faranno lo stesso, senza che questo modulo cambi: per questo `esegui` prende
un'`origine` e non sa nulla di chi lo chiama.

Un secondo punto di scrittura verso Home Assistant e' un difetto, non
un'ottimizzazione: verifica, registro e -- il giorno in cui si affronteranno
le sicurezze -- i controlli si scrivono UNA volta e valgono per chiunque.

Non solleva mai: ogni guasto diventa un dizionario con `errore`, perche' il
suo chiamante e' uno strumento che parla a un modello.

**I bersagli, e perche' il giro e' in due tempi.** «Spegni tutto in cucina»
obbligava il modello a chiamare `cerca`, raccogliere gli id a mano e passarli
tutti qui: se ne perdeva uno, HIRIS ne spegneva quattordici su quindici e
dichiarava di aver spento tutto. Dalla fetta «i bersagli» un'area, un piano,
un'etichetta o un dispositivo si passano come sono, e a dire cosa contengono
e' HOME ASSISTANT (`extract_from_target`). `verifica()` e' pura e non puo'
chiederglielo: la porta risolve e RICHIAMA la verifica con l'elenco in mano,
cosi' la parte che dice di no resta una sola e la risoluzione non diventa un
secondo posto in cui si decide. Se quella domanda non arriva a destinazione,
il rifiuto lo dice -- `_BERSAGLIO_SENZA_CANALE` e `_bersaglio_non_risolto`
sono la terza guardia di questo modulo, con la stessa regola delle prime due:
un ingresso che non si e' potuto leggere non diventa mai un elenco piu' corto.

**I due ingressi vuoti.** `verifica()` e' pura: non puo' distinguere «non
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
Assistant ci mette ad annunciarlo e non `ATTESA_STATO_S`; la scadenza non e'
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
from .verifica import verifica

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
ATTESA_STATO_S = 2.0

# I due messaggi delle guardie. Nessuno dei due dice «non posso»: il rifiuto
# porta il motivo, e qui il motivo e' sempre lo stesso -- non ho guardato, e
# non lo spaccio per «non c'e'».
_REGISTRO_MUTO = ("non so ancora cosa Home Assistant sa fare: il registro dei "
                  "servizi e' vuoto. Non e' che questa casa non sappia fare "
                  "niente -- e' che non sono riuscito a leggerlo. Riprova fra poco.")
_SPECCHIO_CIECO = ("non vedo lo stato di questa casa: l'inventario delle entita' "
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
_BERSAGLIO_SENZA_CANALE = ("questo collegamento con Home Assistant non sa risolvere "
                           "un bersaglio per area, piano, etichetta o dispositivo. "
                           "Passa gli id esatti in «bersaglio.entita»: non riduco "
                           "un'area a un elenco che mi sono immaginato.")


def _bersaglio_non_risolto(motivo: str) -> str:
    return (f"non sono riuscito a chiedere a Home Assistant cosa contiene questo "
            f"bersaglio ({motivo}). Non tiro a indovinare quali entita' ci siano "
            f"dentro -- non ho toccato niente. Riprova fra poco, oppure passa gli "
            f"id esatti in «bersaglio.entita».")


def _secondi(attesa: float) -> str:
    """«2», non «2.0»; «0.05» resta «0.05». Il numero che l'avviso mostra
    all'utente e' lo stesso che la porta ha davvero aspettato, e si formatta
    in un posto solo perche' compare in piu' di una frase."""
    return f"{attesa:g}"


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
def _non_visto(attesa: float) -> str:
    return ("la chiamata e' partita, ma non sono riuscito a rileggere lo stato "
            f"dopo: ho aspettato {_secondi(attesa)} secondi e Home Assistant non "
            "ha annunciato niente su queste entita', la chiamata non ha riportato "
            "niente e l'inventario interno non e' leggibile. Non so dire cosa sia "
            "cambiato")


def _nessun_cambiamento(attesa: float) -> str:
    return ("la chiamata e' andata a buon fine, ho aspettato "
            f"{_secondi(attesa)} secondi che Home Assistant annunciasse un "
            "cambiamento di stato su queste entita', e in quel tempo Home "
            "Assistant non ha riportato nessun cambiamento. E' un fatto su cio' "
            "che Home Assistant ha detto entro quel tempo, non una diagnosi del "
            "dispositivo: puo' voler dire che era gia' cosi', oppure che sta "
            "ancora muovendosi")


_CAMBIATO_NON_MOSTRABILE = ("Home Assistant ha riportato un cambiamento su queste "
                            "entita' -- annunciandolo, o dichiarandolo nella "
                            "chiamata -- ma fra i valori che HIRIS confronta non "
                            "ce n'e' nessuno diverso: il comando ha avuto effetto "
                            "su qualcosa che non so mostrare")


def _anteprima(verdetto, risolto: dict) -> dict:
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
        "chiesto": dict(verdetto.bersaglio),
        "risolte": list(risolto.get("entita") or []),
        "toccate": list(verdetto.entita),
        "escluse_altro_dominio": list(verdetto.scartate),
        "escluse_senza_stato": list(verdetto.sconosciute),
        "aree": list(risolto.get("aree") or []),
        "dispositivi": list(risolto.get("dispositivi") or []),
    }


def _impronta(voce) -> dict | None:
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
    mostrare, l'esito lo dice con `_CAMBIATO_NON_MOSTRABILE` invece di
    lasciar credere che non sia successo niente.

    **Vale per tutte e tre le fonti, ed e' il motivo per cui sono
    confrontabili.** L'impronta si costruisce sempre sulla voce MINIMALE di
    `entity_cache._to_minimal`: quella dello specchio lo e' gia'; quella che
    arriva da `call_service` e quella che arriva dall'annuncio del websocket
    -- entrambe stati completi di Home Assistant -- ci passano attraverso in
    `_impronta_da_stato_ha`. Senza quel passaggio i lati avrebbero insiemi di
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
    if not isinstance(voce, dict):
        return None
    impronta = {"state": voce.get("state")}
    # L'UNITA', che questa proiezione buttava: «adesso e' a 21, in stanza ci
    # sono 69.8» senza scala e' un numero, non un fatto -- e il modello non
    # puo' nemmeno dedurla, perche' il nucleo gli vieta esplicitamente di
    # applicare l'unita' della casa a una singola entita'. Sta nella voce
    # dello specchio (`entity_cache._to_minimal`) e costava solo il leggerla.
    unita = voce.get("unit")
    if isinstance(unita, str) and unita.strip():
        impronta["unit"] = unita.strip()
    attributi = voce.get("attributes")
    if isinstance(attributi, dict):
        # `state` non si lascia sovrascrivere da un attributo omonimo: la
        # chiave che dice lo stato dev'essere sempre quella.
        impronta.update({k: v for k, v in attributi.items() if k != "state"})
    return impronta


def _impronta_da_stato_ha(grezzo) -> dict | None:
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
    if not isinstance(grezzo, dict) or not grezzo.get("entity_id"):
        return None
    try:
        voce = _to_minimal(grezzo)
    except Exception as errore:
        logger.warning("stato di Home Assistant illeggibile (%s: %s)",
                       type(errore).__name__, errore)
        return None
    return _impronta(voce)


def _impronte_riportate(cambiati) -> dict[str, dict]:
    """Le impronte degli stati che Home Assistant dichiara cambiati.

    Ingresso: il ritorno di `HAClient.call_service`, cioe' una lista di stati
    COMPLETI di Home Assistant -- non le voci minimali dello specchio.

    **Su questo impianto e' vuota**, e la misura sta nel log di produzione:
    «0 voci utilizzabili». Resta perche' su altri impianti non lo e', ed e'
    l'unica fonte che non costa nessuna attesa: un'entita' che compare qui
    non si aspetta.
    """
    impronte: dict[str, dict] = {}
    for grezzo in cambiati or []:
        impronta = _impronta_da_stato_ha(grezzo)
        if impronta is not None:
            impronte[grezzo["entity_id"]] = impronta
    return impronte


class _AscoltoStati:
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

    def __init__(self, entita) -> None:
        self.udite: dict[str, dict] = {}
        self._bersagli = set(entita)
        # Chi si sta ancora aspettando. Parte da tutti e si restringe in
        # `attendi`: le entita' di cui `call_service` ha gia' detto qualcosa
        # non si aspettano.
        self._attese = set(entita)
        self._sveglia = asyncio.Event()

    def __call__(self, dati) -> None:
        """Chiamata dal ciclo websocket, in modo sincrono e da un altro Task.

        Non solleva mai: un ascoltatore che esplode verrebbe soltanto loggato
        dal ciclo, e questa chiamata resterebbe appesa fino alla scadenza per
        un motivo che non ha niente a che vedere con la casa.
        """
        try:
            nuovo = (dati or {}).get("new_state")
            eid = nuovo.get("entity_id") if isinstance(nuovo, dict) else None
            if eid not in self._bersagli:
                return
            impronta = _impronta_da_stato_ha(nuovo)
            if impronta is None:
                return
            self.udite[eid] = impronta
            if self._attese and self._attese <= self.udite.keys():
                self._sveglia.set()
        except Exception as errore:  # pragma: no cover - difesa, non un ramo
            logger.warning("annuncio di stato illeggibile (%s: %s)",
                           type(errore).__name__, errore)

    async def attendi(self, mancanti, scadenza: float) -> bool:
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
        self._attese = {e for e in mancanti if e in self._bersagli}
        if not self._attese or self._attese <= self.udite.keys():
            return True
        try:
            await asyncio.wait_for(self._sveglia.wait(), scadenza)
        except (asyncio.TimeoutError, TimeoutError):
            return False
        return True


class PortaAzione:
    def __init__(self, ha_client, registro, cache, cronaca=None) -> None:
        self._ha = ha_client
        self._registro = registro
        self._cache = cache
        # Il registro delle esecuzioni (`cronaca.py`). `None` e' legittimo e
        # non cambia niente per chi non lo passa: la porta scriveva gia' la
        # sua riga di log, e questa e' la stessa riga resa CHIEDIBILE.
        self._cronaca = cronaca

    def _stati(self) -> dict[str, dict] | None:
        """Lo specchio dello stato vivo, o `None` se non l'ho potuto leggere.

        `None` non e' `{}`: uno significa «non ho guardato», l'altro «ho
        guardato e non c'era niente». E' precisamente la distinzione che
        `verifica()` -- pura -- non puo' fare.

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
            grezzo = self._cache.all_states()
        except Exception as errore:
            logger.warning("specchio dello stato illeggibile (%s: %s)",
                           type(errore).__name__, errore)
            return None
        stati: dict[str, dict] = {}
        for voce in grezzo or []:
            eid = voce.get("id") if isinstance(voce, dict) else None
            if eid:
                stati[eid] = voce
        return stati

    async def _risolvi(self, bersaglio: dict) -> dict:
        """Cosa contiene questo bersaglio, chiesto a Home Assistant.

        Restituisce cio' che ha risposto (`ha_client.estrai_dal_bersaglio`),
        oppure `{"errore": "..."}` gia' scritto per il modello. Non ha una
        terza uscita, ed e' il punto: non esiste un ramo in cui un bersaglio
        non risolto diventi un elenco piu' corto.

        Il `getattr` non e' prudenza generica: la porta si costruisce con
        qualunque client (`PortaAzione.__init__` non ne dichiara il tipo), e
        uno che non sappia risolvere i bersagli deve produrre un rifiuto
        onesto invece di un `AttributeError` travestito da risposta.
        """
        estrai = getattr(self._ha, "estrai_dal_bersaglio", None)
        if not callable(estrai):
            logger.warning("questo client di Home Assistant non sa risolvere i "
                           "bersagli: solo le entita' nominate sono eseguibili")
            return {"errore": _BERSAGLIO_SENZA_CANALE}
        try:
            risposta = await estrai(bersaglio)
        except Exception as errore:
            logger.warning("bersaglio non risolto (%s: %s)",
                           type(errore).__name__, errore)
            return {"errore": _bersaglio_non_risolto(
                f"{type(errore).__name__}: {errore}")}
        if not isinstance(risposta, dict):
            return {"errore": _bersaglio_non_risolto("risposta illeggibile")}
        if risposta.get("errore"):
            return {"errore": _bersaglio_non_risolto(str(risposta["errore"]))}
        return risposta

    def _apri_ascolto(self, ascolto) -> bool:
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
        aggiungi = getattr(self._ha, "add_state_listener", None)
        togli = getattr(self._ha, "remove_state_listener", None)
        if not callable(aggiungi) or not callable(togli):
            logger.warning("questo client di Home Assistant non annuncia i "
                           "cambiamenti di stato: l'esito potra' dire solo cio' "
                           "che la chiamata ha riportato")
            return False
        try:
            aggiungi(ascolto)
        except Exception as errore:
            logger.warning("ascolto degli annunci non aperto (%s: %s)",
                           type(errore).__name__, errore)
            return False
        return True

    def _chiudi_ascolto(self, ascolto) -> None:
        try:
            self._ha.remove_state_listener(ascolto)
        except Exception as errore:
            logger.warning("ascolto degli annunci non chiuso (%s: %s)",
                           type(errore).__name__, errore)

    def _annota(self, **fatti) -> str | None:
        """La riga di cronaca, se la cronaca c'e'. Non solleva MAI.

        Un registro che non si riesce a scrivere non deve poter trasformare
        un'azione riuscita in un errore: cio' che e' successo alla casa e'
        successo comunque, e tacerlo sarebbe peggio che non annotarlo.
        """
        if self._cronaca is None:
            return None
        try:
            return self._cronaca.registra(adesso=time.time(), **fatti)
        except Exception as errore:
            logger.warning("cronaca non scritta (%s: %s)",
                           type(errore).__name__, errore)
            return None

    async def esegui(self, chiamata: dict, *, origine: str) -> dict:
        try:
            await self._registro.assicura_fresco(self._ha)
        except Exception as errore:
            return {"eseguito": False,
                    "errore": f"non riesco a leggere cosa Home Assistant sa fare "
                              f"({type(errore).__name__}: {errore})."}

        # Guardia (a). Il registro sa distinguere «mai letto» (`vuoto()`) da
        # «letto e vuoto», ma per chi deve agire i due casi valgono uguale:
        # senza domini non si puo' verificare niente, e lasciar proseguire
        # significherebbe far dire alla verifica «Domini disponibili: .».
        if not self._registro.domini():
            logger.warning("azione rifiutata [origine=%s]: registro dei servizi vuoto",
                           origine)
            return {"eseguito": False, "errore": _REGISTRO_MUTO}

        stati_prima = self._stati()
        # Guardia (b). `None` e `{}` insieme, di proposito: una casa che
        # davvero non ha nessuna entita' non ha nemmeno l'entita' bersaglio,
        # quindi non c'e' chiamata legittima che questa guardia possa
        # rifiutare -- e in cambio non si nega mai un'entita' che esiste.
        if not stati_prima:
            logger.warning("azione rifiutata [origine=%s]: specchio dello stato non leggibile",
                           origine)
            return {"eseguito": False, "errore": _SPECCHIO_CIECO}

        verdetto = verifica(chiamata, self._registro, stati_prima)
        # Il secondo tempo, e solo per i bersagli che lo chiedono: un
        # bersaglio di sole entita' non costa nessun giro di rete. La verifica
        # si rifa' INTERA con l'elenco in mano -- non si aggiunge un pezzo a
        # un verdetto gia' preso -- cosi' la parte che dice di no resta una.
        risolto = None
        if verdetto.da_risolvere:
            risolto = await self._risolvi(verdetto.bersaglio)
            if risolto.get("errore"):
                logger.warning("azione rifiutata [origine=%s]: bersaglio %s non "
                               "risolto", origine, verdetto.bersaglio)
                return {"eseguito": False, "errore": risolto["errore"]}
            verdetto = verifica(chiamata, self._registro, stati_prima,
                                risolto=risolto)
        if not verdetto.ok:
            logger.info("azione rifiutata [origine=%s]: %s", origine, verdetto.motivo)
            return {"eseguito": False, "errore": verdetto.motivo}

        # L'anteprima: cosa si toccherebbe, calcolata e detta PRIMA di
        # toccarlo. Nell'esito ci arriva in fondo, ma qui e' gia' un fatto --
        # e nel log lo e' anche quando la chiamata poi fallisce, che e'
        # l'unico momento in cui la si puo' confrontare con cio' che e'
        # successo davvero.
        anteprima = _anteprima(verdetto, risolto) if risolto is not None else None
        if anteprima is not None:
            logger.info("azione: bersaglio %s risolto in %d entita' da toccare "
                        "(%d di altri domini, %d senza stato) [origine=%s]",
                        verdetto.bersaglio, len(verdetto.entita),
                        len(verdetto.scartate), len(verdetto.sconosciute), origine)

        dati = dict(chiamata.get("dati") or {})
        dati["entity_id"] = list(verdetto.entita)

        # L'ascolto si apre PRIMA della chiamata (vedi il docstring del
        # modulo): l'annuncio puo' arrivare mentre `call_service` e' ancora
        # sospesa, e un ascoltatore aperto dopo lo perderebbe.
        #
        # La scadenza si legge UNA volta e poi si porta dietro: le frasi
        # dell'avviso e la riga di log devono nominare il numero che si e'
        # davvero aspettato, non uno riletto dopo.
        attesa = ATTESA_STATO_S
        ascolto = _AscoltoStati(verdetto.entita)
        in_ascolto = self._apri_ascolto(ascolto)
        try:
            try:
                riportati = await self._ha.call_service(
                    verdetto.dominio, verdetto.servizio, dati)
            except Exception as errore:
                logger.warning("azione fallita [origine=%s] %s.%s: %s",
                               origine, verdetto.dominio, verdetto.servizio, errore)
                messaggio = f"Home Assistant ha rifiutato la chiamata: {errore}"
                esecuzione_id = self._annota(
                    origine=origine,
                    servizio=f"{verdetto.dominio}.{verdetto.servizio}",
                    entita=list(verdetto.entita), eseguito=False, errore=messaggio)
                esito = {"eseguito": False, "errore": messaggio}
                if esecuzione_id is not None:
                    esito["esecuzione_id"] = esecuzione_id
                return esito

            # Un'entita' di cui la chiamata ha gia' detto qualcosa non si
            # aspetta: quella misura e' presa durante l'esecuzione, cioe' nel
            # momento giusto per costruzione. Si aspettano le altre --
            # sull'impianto del proprietario, tutte.
            impronte_ha = _impronte_riportate(riportati)
            if in_ascolto:
                await ascolto.attendi(
                    [e for e in verdetto.entita if e not in impronte_ha], attesa)
        finally:
            if in_ascolto:
                self._chiudi_ascolto(ascolto)

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
        stati_dopo = self._stati()

        prima = {e: _impronta(stati_prima.get(e)) for e in verdetto.entita}
        dopo: dict[str, dict | None] = {}
        for e in verdetto.entita:
            impronta = ascolto.udite.get(e)
            if impronta is None:
                impronta = impronte_ha.get(e)
            if impronta is None and stati_dopo is not None:
                impronta = _impronta(stati_dopo.get(e))
            dopo[e] = impronta

        # `dopo` a `None` significa una cosa sola, e la stessa in tutto il
        # modulo: non l'ho potuto vedere. Un'entita' cosi' resta FUORI da
        # `cambiato` -- contarla direbbe che TUTTO e' cambiato, cioe'
        # inventare -- e produce l'avviso che lo dichiara.
        non_viste = [e for e in verdetto.entita if dopo[e] is None]
        cambiato = [e for e in verdetto.entita
                    if dopo[e] is not None and prima.get(e) != dopo[e]]
        # Le entita' di cui Home Assistant ha detto qualcosa, da una bocca o
        # dall'altra: e' la differenza fra «non ha detto niente» e «ha detto
        # che e' cambiato qualcosa che non so mostrare».
        annunciate = [e for e in verdetto.entita if e in ascolto.udite]
        riportate_qui = [e for e in verdetto.entita if e in impronte_ha]

        esito = {"eseguito": True,
                 "servizio": f"{verdetto.dominio}.{verdetto.servizio}",
                 "entita": list(verdetto.entita),
                 "prima": prima, "dopo": dopo, "cambiato": cambiato}
        if anteprima is not None:
            esito["bersaglio"] = anteprima
        if non_viste:
            esito["avviso"] = _non_visto(attesa)
        elif cambiato:
            pass  # il caso normale: c'e' una differenza, e `prima`/`dopo` la mostrano
        elif annunciate or riportate_qui:
            # HA dice che qualcosa e' cambiato e l'impronta non lo mostra:
            # tipicamente un attributo fuori da `_DOMAIN_ATTRS` (il colore di
            # una luce). Dire «nessun cambiamento» qui sarebbe falso.
            esito["avviso"] = _CAMBIATO_NON_MOSTRABILE
        else:
            # Non e' un errore -- molti servizi legittimi non cambiano stato,
            # e una tapparella puo' non aver ancora finito -- ma tacerlo
            # sarebbe dire cosa e' stato CHIESTO invece di cosa e' SUCCESSO.
            # Cio' che si afferma e' solo cio' che si sa: che ENTRO LA
            # SCADENZA Home Assistant non ha riportato cambiamenti. Non che
            # la casa non sia cambiata, e tanto meno perche'.
            esito["avviso"] = _nessun_cambiamento(attesa)
        logger.info("azione eseguita [origine=%s] %s su %s -- cambiati: %s "
                    "(annunciati %d, riportati dalla chiamata %d, attesi fino a %ss)",
                    origine, esito["servizio"], list(verdetto.entita),
                    cambiato or ("sconosciuto" if non_viste else "nessuno"),
                    len(annunciate), len(riportate_qui), _secondi(attesa))
        esecuzione_id = self._annota(
            origine=origine, servizio=esito["servizio"], entita=list(verdetto.entita),
            eseguito=True, cambiato=cambiato, avviso=esito.get("avviso"))
        if esecuzione_id is not None:
            esito["esecuzione_id"] = esecuzione_id
        return esito
