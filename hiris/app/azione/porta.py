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

**I due ingressi vuoti.** `verifica()` e' pura: non puo' distinguere «non
c'e'» da «non l'ho letto». Con un registro vuoto rifiuterebbe tutto dicendo
«Domini disponibili: .»; con lo specchio dello stato vuoto direbbe «l'entita'
non esiste in questa casa» di entita' che esistono. Sono la stessa cosa vista
due volte -- un ingresso vuoto che produce una frase falsa detta con
sicurezza -- e chiuderli e' compito di questa porta, che i due ingressi li
conosce. Le due guardie sono sotto, ciascuna col suo messaggio onesto.

**Da dove viene il «dopo», e perche' non e' piu' lo specchio.** Il primo
difetto trovato dal vivo di questa fetta, alla prima prova sulla prima casa
vera, e' stato questo: ogni comando RIUSCITO veniva raccontato come «nulla e'
cambiato». Due misure, due domini, un solo sintomo -- due abat-jour spenti
davvero (`state` da `on` a `off`) e un termostato portato davvero a 19.5
(`attributes.temperature` da 17.5) -- entrambi riletti col valore di PRIMA.

La causa non era il confronto, che funzionava (vedi `_impronta`): era la
FONTE. Lo specchio interno (`proxy/entity_cache.py`) e' alimentato dagli
eventi `state_changed` del websocket, che arrivano su un'altra connessione e
in un altro Task; rileggerlo nella riga subito dopo `await call_service`
legge cio' che c'era prima. Non e' una gara che ogni tanto si perde: si perde
quasi sempre, e l'invariante che questa fetta esiste per garantire -- dire
cosa e' SUCCESSO, non cosa e' stato CHIESTO -- produceva l'esatto opposto.

La fonte del «dopo» e' quindi **il ritorno di `call_service`**: gli stati che
Home Assistant dichiara cambiati DURANTE l'esecuzione del servizio, misurati
da lui, nel momento giusto. Lo specchio resta come ripiego per le entita' di
cui HA non ha detto niente. E per cio' che nessuna delle due fonti sa dire,
si dichiara di non saperlo -- come sempre in questo modulo.
"""
import logging

from ..proxy.entity_cache import _to_minimal, inventario_leggibile
from .verifica import verifica

logger = logging.getLogger(__name__)

# I due messaggi delle guardie. Nessuno dei due dice «non posso»: il rifiuto
# porta il motivo, e qui il motivo e' sempre lo stesso -- non ho guardato, e
# non lo spaccio per «non c'e'».
_REGISTRO_MUTO = ("non so ancora cosa Home Assistant sa fare: il registro dei "
                  "servizi e' vuoto. Non e' che questa casa non sappia fare "
                  "niente -- e' che non sono riuscito a leggerlo. Riprova fra poco.")
_SPECCHIO_CIECO = ("non vedo lo stato di questa casa: l'inventario delle entita' "
                   "non e' disponibile. Non posso dire se l'entita' esista, solo "
                   "che non ho potuto controllare. Riprova fra poco.")

# I tre avvisi dell'esito, e sono tre perche' i casi sono tre. Prima ce
# n'erano due, e quello che diceva «nessuno stato e' cambiato» ne copriva
# tre affermando una cosa che HIRIS non poteva sapere: che in casa non fosse
# cambiato niente. Da li' il modello ha tratto -- sulla casa vera -- la frase
# «probabile problema di comunicazione col dispositivo»: una diagnosi
# inventata, che ha mandato il proprietario a cercare un guasto inesistente
# mentre le luci erano spente. Un avviso e' un FATTO su cio' che HIRIS ha
# potuto vedere, mai un'ipotesi sulla causa.
_NON_VISTO = ("la chiamata e' partita, ma non sono riuscito a rileggere lo stato "
              "dopo: Home Assistant non ha riportato niente su queste entita' e "
              "l'inventario interno non e' leggibile. Non so dire cosa sia cambiato")
_NESSUN_CAMBIAMENTO = ("la chiamata e' andata a buon fine e Home Assistant non ha "
                       "riportato nessun cambiamento di stato. E' un fatto su cio' "
                       "che Home Assistant ha detto adesso, non una diagnosi del "
                       "dispositivo: puo' voler dire che era gia' cosi', oppure che "
                       "sta ancora muovendosi")
_CAMBIATO_NON_MOSTRABILE = ("Home Assistant ha riportato un cambiamento su queste "
                            "entita', ma fra i valori che HIRIS confronta non ce n'e' "
                            "nessuno diverso: il comando ha avuto effetto su qualcosa "
                            "che non so mostrare")


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

    **Vale per entrambe le fonti, ed e' il motivo per cui le due sono
    confrontabili.** L'impronta si costruisce sempre sulla voce MINIMALE di
    `entity_cache._to_minimal`: quella dello specchio lo e' gia'; quella che
    arriva da `call_service` -- uno stato completo di Home Assistant -- ci
    passa attraverso in `_impronte_riportate`. Senza quel passaggio i due
    lati avrebbero insiemi di chiavi diversi e OGNI entita' risulterebbe
    cambiata: cioe' inventare, col verso opposto al difetto di prima.
    Passandoci, `prima` e `dopo` restano ricchi allo stesso modo -- per un
    clima portano `hvac_action` e `current_temperature` accanto a
    `temperature`, ed e' con quelli che il modello puo' dire non solo «da
    17.5 a 19.5» ma anche «con 26.9 in stanza resta a riposo».

    `None` -- non `{}` -- quando dell'entita' non c'e' nessuna voce: e' la
    stessa distinzione «non ho guardato» / «ho guardato» del resto del
    modulo, ed e' cio' che il modello legge nel `dopo` di un'entita' che
    nessuna delle due fonti ha saputo mostrare.
    """
    if not isinstance(voce, dict):
        return None
    impronta = {"state": voce.get("state")}
    attributi = voce.get("attributes")
    if isinstance(attributi, dict):
        # `state` non si lascia sovrascrivere da un attributo omonimo: la
        # chiave che dice lo stato dev'essere sempre quella.
        impronta.update({k: v for k, v in attributi.items() if k != "state"})
    return impronta


def _impronte_riportate(cambiati) -> dict[str, dict]:
    """Le impronte degli stati che Home Assistant dichiara cambiati.

    Ingresso: il ritorno di `HAClient.call_service`, cioe' una lista di stati
    COMPLETI di Home Assistant (`entity_id`, `state`, `attributes`, ...) --
    non le voci minimali dello specchio. `_to_minimal` e' quindi obbligatorio
    e non decorativo: e' cio' che rende le due fonti confrontabili (vedi
    `_impronta`).

    Difensiva come il suo ingresso: e' una forma di Home Assistant che nessuno
    aveva mai misurato (`proxy/ha_client._cambiati_da` la dichiara nel log al
    primo uso). Una voce che `_to_minimal` non sa digerire viene SALTATA, non
    indovinata e non fatta esplodere: l'entita' che porta ricadra' sullo
    specchio, e al peggio sull'onesto «non so dire cosa sia cambiato».
    """
    impronte: dict[str, dict] = {}
    for grezzo in cambiati or []:
        if not isinstance(grezzo, dict) or not grezzo.get("entity_id"):
            continue
        try:
            voce = _to_minimal(grezzo)
        except Exception as errore:
            logger.warning("stato riportato da call_service illeggibile (%s: %s)",
                           type(errore).__name__, errore)
            continue
        impronta = _impronta(voce)
        if impronta is not None:
            impronte[grezzo["entity_id"]] = impronta
    return impronte


class PortaAzione:
    def __init__(self, ha_client, registro, cache) -> None:
        self._ha = ha_client
        self._registro = registro
        self._cache = cache

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
        if not verdetto.ok:
            logger.info("azione rifiutata [origine=%s]: %s", origine, verdetto.motivo)
            return {"eseguito": False, "errore": verdetto.motivo}

        dati = dict(chiamata.get("dati") or {})
        dati["entity_id"] = list(verdetto.entita)
        try:
            # Il ritorno NON si butta: sono gli stati che Home Assistant ha
            # visto cambiare mentre il servizio girava. Buttarlo e rileggere
            # lo specchio e' esattamente il difetto misurato sulla prima casa
            # vera (vedi il docstring del modulo).
            riportati = await self._ha.call_service(
                verdetto.dominio, verdetto.servizio, dati)
        except Exception as errore:
            logger.warning("azione fallita [origine=%s] %s.%s: %s",
                           origine, verdetto.dominio, verdetto.servizio, errore)
            return {"eseguito": False,
                    "errore": f"Home Assistant ha rifiutato la chiamata: {errore}"}

        # Le due fonti del «dopo», in ordine di merito.
        #
        # (1) Cio' che HA ha riportato: misurato da lui, durante l'esecuzione.
        #     Nessuna gara da vincere -- e' il momento giusto per costruzione.
        # (2) Lo specchio, per le sole entita' di cui HA non ha detto niente.
        #     Non e' un doppione della (1) ne' un rattoppo alla gara: e' cio'
        #     che resta quando HA non riporta nulla (un servizio che non
        #     cambia stato, un dispositivo lento), e serve a distinguere «non
        #     e' cambiato» da «non l'ho visto». Nessuna attesa, in nessuno dei
        #     due casi: una `sleep` arbitraria trasformerebbe un fatto in
        #     un'ipotesi, e adesso non ci sarebbe nemmeno il pretesto.
        impronte_ha = _impronte_riportate(riportati)
        stati_dopo = self._stati()

        prima = {e: _impronta(stati_prima.get(e)) for e in verdetto.entita}
        dopo: dict[str, dict | None] = {}
        for e in verdetto.entita:
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
        riportate_qui = [e for e in verdetto.entita if e in impronte_ha]

        esito = {"eseguito": True,
                 "servizio": f"{verdetto.dominio}.{verdetto.servizio}",
                 "entita": list(verdetto.entita),
                 "prima": prima, "dopo": dopo, "cambiato": cambiato}
        if non_viste:
            esito["avviso"] = _NON_VISTO
        elif cambiato:
            pass  # il caso normale: c'e' una differenza, e `prima`/`dopo` la mostrano
        elif riportate_qui:
            # HA dice che qualcosa e' cambiato e l'impronta non lo mostra:
            # tipicamente un attributo fuori da `_DOMAIN_ATTRS` (il colore di
            # una luce). Dire «nessun cambiamento» qui sarebbe falso.
            esito["avviso"] = _CAMBIATO_NON_MOSTRABILE
        else:
            # Non e' un errore -- molti servizi legittimi non cambiano stato,
            # e una tapparella puo' non aver ancora finito -- ma tacerlo
            # sarebbe dire cosa e' stato CHIESTO invece di cosa e' SUCCESSO.
            # Cio' che si afferma e' solo cio' che si sa: che Home Assistant
            # non ha riportato cambiamenti. Non che la casa non sia cambiata,
            # e tanto meno perche'.
            esito["avviso"] = _NESSUN_CAMBIAMENTO
        logger.info("azione eseguita [origine=%s] %s su %s -- cambiati: %s "
                    "(Home Assistant ne ha riportati %d)",
                    origine, esito["servizio"], list(verdetto.entita),
                    cambiato or ("sconosciuto" if non_viste else "nessuno"),
                    len(riportate_qui))
        return esito
