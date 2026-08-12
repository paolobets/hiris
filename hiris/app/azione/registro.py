"""Il registro dei servizi: cosa Home Assistant sa fare, in questa casa.

Non e' un catalogo scritto da noi -- e' lo specchio di `/api/services`. Per
questo copre le integrazioni installate dopo, senza che nessuno tocchi HIRIS:
e' l'invariante «verificare, non insegnare» della spec dell'azione.

Non solleva mai (tranne al primissimo caricamento, vedi `assicura_fresco`): un
registro mai caricato, o caricato da una risposta malformata, risponde `None` a
chi lo interroga. Chi decide cosa dire all'utente e' la verifica, non questo
modulo.

Attenzione a come si legge `servizio()`: il suo `dict` vuoto significa «il
servizio esiste ma non ne conosciamo il dettaglio», che e' diverso da `None`
(«non esiste»). Chi lo interroga confronta con `is None`, mai con la verita'
booleana del risultato.

La forma di `/api/services` presa per buona qui e' una lista di
`{"domain": str, "services": {nome: dettaglio}}`. E' la forma **attesa**, non
ancora misurata su un'installazione vera: per questo ogni chiave e ogni tipo
sono verificati prima dell'uso e una voce che non torna viene saltata invece
di far cadere l'intero aggiornamento.
"""
import logging
import time

logger = logging.getLogger(__name__)


class RegistroServizi:
    def __init__(self, eta_massima_s: float = 300.0) -> None:
        self._per_dominio: dict[str, dict[str, dict]] = {}
        self._caricato_a: float | None = None
        self._eta_massima_s = eta_massima_s

    async def aggiorna(self, ha_client) -> None:
        """Rilegge `/api/services` e **sostituisce** cio' che sapevamo.

        Sostituisce, non fonde: un'integrazione disinstallata deve sparire
        anche da qui, altrimenti il registro smetterebbe di essere lo
        specchio di HA e diventerebbe un archivio di cio' che un tempo era
        possibile.
        """
        grezzo = await ha_client.get_services()
        nuovo: dict[str, dict[str, dict]] = {}
        for voce in grezzo or []:
            if not isinstance(voce, dict):
                continue
            dominio = voce.get("domain")
            servizi = voce.get("services")
            if not isinstance(dominio, str) or not isinstance(servizi, dict):
                continue
            nuovo[dominio] = {n: (d if isinstance(d, dict) else {})
                              for n, d in servizi.items() if isinstance(n, str)}
        self._per_dominio = nuovo
        self._caricato_a = time.monotonic()
        logger.info("registro servizi: %d domini, %d servizi",
                    len(nuovo), sum(len(s) for s in nuovo.values()))

    async def assicura_fresco(self, ha_client) -> None:
        """Ricarica se serve. Un guasto NON svuota cio' che sapevamo.

        Un registro vecchio e' meno peggio di un registro assente: col primo
        HIRIS puo' ancora rifiutare un servizio che non esiste, col secondo
        non puo' verificare niente. Se il rinfresco fallisce si logga e si
        tiene il vecchio -- e `eta_secondi()` resta grande, cosi' chi vuole
        saperlo puo' chiederlo.

        Al **primo** caricamento non c'e' nessun vecchio da proteggere:
        li' il guasto risale, perche' un registro mai caricato e un registro
        caricato e vuoto rispondono uguale a chi li interroga, e chi chiama
        deve poterli distinguere.
        """
        eta = self.eta_secondi()
        if eta is not None and eta < self._eta_massima_s:
            return
        try:
            await self.aggiorna(ha_client)
        except Exception as errore:
            if self.vuoto():
                raise
            logger.warning("registro servizi: rinfresco fallito (%s: %s), "
                           "tengo quello di %.0fs fa",
                           type(errore).__name__, errore, eta or 0.0)

    def servizio(self, dominio: str, nome: str) -> dict | None:
        """Il dettaglio di un servizio, o `None` se qui non esiste."""
        return self._per_dominio.get(dominio, {}).get(nome)

    def domini(self) -> list[str]:
        return sorted(self._per_dominio)

    def servizi_di(self, dominio: str) -> list[str]:
        return sorted(self._per_dominio.get(dominio, {}))

    def eta_secondi(self) -> float | None:
        """Da quanti secondi il registro e' quello che e'. `None` = mai letto."""
        if self._caricato_a is None:
            return None
        return time.monotonic() - self._caricato_a

    def vuoto(self) -> bool:
        """Vero finche' nessun caricamento e' mai riuscito.

        Non dice «zero servizi»: dice «mai letto». Un `/api/services` che
        rispondesse una lista vuota lascerebbe questo `False`.
        """
        return self._caricato_a is None
