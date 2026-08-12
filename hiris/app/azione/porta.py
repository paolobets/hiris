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
"""
import logging

from ..proxy.entity_cache import inventario_leggibile
from .verifica import verifica

logger = logging.getLogger(__name__)

# I tre messaggi delle guardie. Nessuno dei tre dice «non posso»: il rifiuto
# porta il motivo, e qui il motivo e' sempre lo stesso -- non ho guardato, e
# non lo spaccio per «non c'e'».
_REGISTRO_MUTO = ("non so ancora cosa Home Assistant sa fare: il registro dei "
                  "servizi e' vuoto. Non e' che questa casa non sappia fare "
                  "niente -- e' che non sono riuscito a leggerlo. Riprova fra poco.")
_SPECCHIO_CIECO = ("non vedo lo stato di questa casa: l'inventario delle entita' "
                   "non e' disponibile. Non posso dire se l'entita' esista, solo "
                   "che non ho potuto controllare. Riprova fra poco.")
_RILETTURA_CIECA = ("la chiamata e' partita, ma non sono riuscito a rileggere lo "
                    "stato: non so dire cosa sia cambiato")


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
    vera tutti i giorni.

    **Gli attributi sono quelli che lo specchio gia' conserva**
    (`entity_cache._DOMAIN_ATTRS`: `temperature`, `brightness`,
    `current_position`, `volume_level`, `percentage`...). Nessuno viene
    aggiunto qui: quell'elenco e' una decisione dell'inventario -- che lo
    tiene corto apposta, perche' lo legge tutto il prodotto -- non della
    porta. La conseguenza va detta invece di essere scoperta: un attributo
    che lo specchio non tiene (il colore di una luce, l'umidita' di un
    umidificatore) resta invisibile a questo confronto, e quel comando
    continuera' a portare l'avviso «nessuno stato e' cambiato». E' lo stesso
    avviso onesto-ma-parziale della tapparella lenta: dice il vero su cio'
    che HIRIS ha potuto guardare.

    **Perche' non la lista dei cambiati di `call_service`.** Home Assistant
    la restituisce, e chiuderebbe anche la corsa fra la rilettura e l'arrivo
    dell'evento websocket. E' stata scartata per due ragioni. La prima: e'
    una **seconda forma non misurata** della stessa risposta da cui vengono
    entrambi gli altri difetti chiusi in questa passata (`fields` a sezioni,
    `fields` non-mappa) -- lo specchio, invece, e' costruito da noi in
    `_to_minimal`, e confrontarlo con se stesso non presuppone niente. La
    seconda: metterebbe in `cambiato` entita' la cui differenza `prima` e
    `dopo` non possono mostrare, cioe' un racconto che si contraddice da
    solo. Resta un debito dichiarato, e la corsa e' sorvegliata dalla prova 2
    del foglio.

    `None` -- non `{}` -- quando dell'entita' non c'e' nessuna voce: e' la
    stessa distinzione «non ho guardato» / «ho guardato» del resto del
    modulo, ed e' cio' che il modello legge nel `dopo` di una rilettura
    cieca.
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
            await self._ha.call_service(verdetto.dominio, verdetto.servizio, dati)
        except Exception as errore:
            logger.warning("azione fallita [origine=%s] %s.%s: %s",
                           origine, verdetto.dominio, verdetto.servizio, errore)
            return {"eseguito": False,
                    "errore": f"Home Assistant ha rifiutato la chiamata: {errore}"}

        # La rilettura. Fra la chiamata e questa riga passano millisecondi: uno
        # stato lento (una tapparella che impiega venti secondi) risultera'
        # «non cambiato», e l'avviso dira' il vero -- in QUEL momento non era
        # cambiato. Nessuna attesa: una `sleep` arbitraria trasformerebbe un
        # fatto onesto in un'ipotesi.
        #
        # Cio' che si confronta e' l'IMPRONTA, non il solo `state`: vedi
        # `_impronta` qui sopra. `prima` e `dopo` portano al modello la stessa
        # cosa che il confronto guarda, cosi' `cambiato` e' sempre spiegabile
        # da loro due -- e il modello puo' dire «da 19 a 21» invece di «fatto».
        stati_dopo = self._stati()
        prima = {e: _impronta(stati_prima.get(e)) for e in verdetto.entita}
        dopo = {e: _impronta((stati_dopo or {}).get(e)) for e in verdetto.entita}
        # Se la rilettura non e' riuscita, `dopo` e' tutto `None` e il
        # confronto direbbe che TUTTO e' cambiato: sarebbe inventare. Si
        # dichiara di non saperlo.
        cieco = stati_dopo is None
        cambiato = [] if cieco else [e for e in verdetto.entita if prima.get(e) != dopo.get(e)]

        esito = {"eseguito": True,
                 "servizio": f"{verdetto.dominio}.{verdetto.servizio}",
                 "entita": list(verdetto.entita),
                 "prima": prima, "dopo": dopo, "cambiato": cambiato}
        if cieco:
            esito["avviso"] = _RILETTURA_CIECA
        elif not cambiato:
            # Non e' un errore -- molti servizi legittimi non cambiano stato --
            # ma tacerlo sarebbe dire cosa e' stato CHIESTO invece di cosa e'
            # SUCCESSO. Se l'utente ha chiesto di spegnere e la luce e' ancora
            # accesa, deve saperlo dal modello, non accorgersene dopo.
            esito["avviso"] = ("la chiamata e' andata a buon fine ma nessuno "
                               "stato e' cambiato")
        logger.info("azione eseguita [origine=%s] %s su %s -- cambiati: %s",
                    origine, esito["servizio"], list(verdetto.entita),
                    cambiato or ("sconosciuto" if cieco else "nessuno"))
        return esito
