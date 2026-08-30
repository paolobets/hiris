"""Il registro dei servizi: cosa Home Assistant sa fare, in questa casa.

Non e' un catalogo scritto da noi -- e' lo specchio di `/api/services`. Per
questo copre le integrazioni installate dopo, senza che nessuno tocchi HIRIS:
e' l'invariante «verificare, non insegnare» della spec dell'azione.

Non solleva mai (tranne al primissimo caricamento, vedi `ensure_fresh`): un
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

La verifica arriva **fino ai parametri**, e non si ferma un livello sopra come
faceva prima della revisione della fetta: `fields` viene normalizzato qui
(`_fields`), cosi' che chi legge il registro trovi sempre o una mappa di nomi o
un `None` dichiarato, mai una forma da indovinare. Erano due difetti misurati,
non ipotesi: un `fields` che non fosse una mappa faceva risalire un `TypeError`
fino al modello (`unhashable type: 'dict'` come motivo di un rifiuto), e un
`fields` **a sezioni** -- la forma che Home Assistant >= 2024.6 manda per
parecchi domini core -- faceva rifiutare un parametro legittimo offrendo
`advanced_fields` come «uno di quelli veri».

**`target` non viene toccato, ed e' voluto** (review finale, rilievo CRITICO
①). A differenza di `fields`, che va appiattito per essere letto,
`_detail()` lo lascia esattamente come Home Assistant lo manda -- spreads
`**grezzo`, quindi la chiave sopravvive intera, `None` compreso -- perche' qui
serve il dato grezzo, non una sua interpretazione: e' `azione/verifica.py` a
decidere cosa significhi «un servizio senza `target`» (vedi
`verifica._declare_target`), non questo modulo. `servizio("light", "turn_on") ==
{"target": {}}` (con) e `servizio("light", "toggle") == {}` (senza -- la chiave non
compare affatto) sono ENTRAMBI casi gia' pinnati da un test (`tests/test_azione_registro.py::
test_un_servizio_senza_campi_non_ne_guadagna_uno_finto`).
"""
import logging
import time

logger = logging.getLogger(__name__)


def _fields(reading) -> dict | None:
    """I parametri di un servizio, appiattiti di un livello.

    Tre esiti, e il terzo e' il motivo per cui questa funzione esiste:

    - **forma piatta** -- `{"brightness_pct": {...}, "transition": {...}}`:
      resta com'e';
    - **forma a sezioni** (Home Assistant >= 2024.6) -- i campi avanzati
      stanno raggruppati: `{"advanced_fields": {"collapsed": true, "fields":
      {"rgbw_color": {...}}}}`. Letta piatta faceva due danni in una frase
      sola: rifiutava `rgbw_color`, che e' un parametro **vero**, e offriva al
      modello `advanced_fields` come parametro -- che il modello avrebbe
      provato, per un secondo rifiuto. Qui la sezione si apre e i suoi campi
      salgono di un livello. Appiattire e' **innocuo dove le sezioni non ci
      sono**: senza un `fields` annidato dentro, non c'e' niente da aprire.
      Un livello solo, di proposito: le sezioni di Home Assistant non si
      annidano, e scendere all'infinito trasformerebbe un parser in
      un'ipotesi.
    - **forma illeggibile** -- `fields` c'e' ma non e' una mappa: `None`.
      `None` NON e' `{}`, ed e' la stessa distinzione che questo modulo usa
      gia' per `servizio()` e `age_seconds()`: `{}` dice «letto: nessun
      parametro» e autorizza a rifiutare un parametro in piu', `None` dice
      «non l'ho potuto leggere» -- e su cio' che non si e' potuto misurare
      non si rifiuta.

    Cosa distingue una sezione da un campo: il valore e' una mappa che
    contiene a sua volta un `fields` che e' una mappa. Il descrittore di un
    campo (`selector`, `required`, `example`, `default`...) non ha un
    `fields`; una sezione ce l'ha per definizione, ed e' li' che stanno i
    nomi veri.
    """
    if not isinstance(reading, dict):
        return None
    piatti: dict = {}
    for name, detail in reading.items():
        internal = detail.get("fields") if isinstance(detail, dict) else None
        if isinstance(internal, dict):
            for nested_name, nested_detail in internal.items():
                if isinstance(nested_name, str):
                    piatti[nested_name] = nested_detail
        elif isinstance(name, str):
            piatti[name] = detail
    return piatti


def _detail(reading) -> dict:
    """Il dettaglio di un servizio, coi suoi `fields` gia' normalizzati.

    Un dettaglio che non e' un dizionario diventa `{}` -- «il servizio esiste,
    non sappiamo com'e' fatto» -- e non fa cadere il dominio intero. Un
    dettaglio senza `fields` resta tale e quale: aggiungere una chiave che
    Home Assistant non ha mandato sarebbe insegnare invece di specchiare.
    """
    if not isinstance(reading, dict):
        return {}
    if "fields" not in reading:
        return reading
    return {**reading, "fields": _fields(reading["fields"])}


class ServiceRegistry:
    def __init__(self, max_age_s: float = 300.0) -> None:
        self._per_domain: dict[str, dict[str, dict]] = {}
        self._caricato_a: float | None = None
        self._max_age_s = max_age_s
        # Il segno di «rileggi appena serve», messo da `invalidate()`. E' un
        # campo SUO e non un azzeramento di `_caricato_a`: quello significa
        # «mai letto» (vedi `empty()`), e fingerlo farebbe SOLLEVARE
        # `ensure_fresh` al primo rinfresco fallito invece di tenere il
        # registro vecchio -- cioe' il contrario esatto di cio' che quel
        # metodo dichiara di volere.
        self._da_rileggere = False

    async def refresh(self, ha_client) -> None:
        """Rilegge `/api/services` e **sostituisce** cio' che sapevamo.

        Sostituisce, non fonde: un'integrazione disinstallata deve sparire
        anche da qui, altrimenti il registro smetterebbe di essere lo
        specchio di HA e diventerebbe un archivio di cio' che un tempo era
        possibile.
        """
        reading = await ha_client.get_services()
        new: dict[str, dict[str, dict]] = {}
        for entry in reading or []:
            if not isinstance(entry, dict):
                continue
            domain = entry.get("domain")
            services = entry.get("services")
            if not isinstance(domain, str) or not isinstance(services, dict):
                continue
            new[domain] = {n: _detail(d)
                              for n, d in services.items() if isinstance(n, str)}
        self._per_domain = new
        self._caricato_a = time.monotonic()
        self._da_rileggere = False
        logger.info("registro servizi: %d domini, %d servizi",
                    len(new), sum(len(s) for s in new.values()))
        # Una risposta che c'era e da cui non si e' capito NIENTE e' l'unico
        # esito che il resto del prodotto non sa raccontare: l'utente si sente
        # dire «non sono riuscito a leggerlo, riprova fra poco» per sempre, e
        # nel log c'era solo un `INFO: 0 domini, 0 servizi` che assomiglia a
        # una casa senza servizi. E' il fallimento numero 1 del foglio delle
        # prove: qui diventa una diagnosi invece di un silenzio.
        if reading and not new:
            logger.warning("registro servizi: la risposta di /api/services non era "
                           "vuota (%s voci) ma non se ne e' capita nessuna -- la sua "
                           "forma non e' quella attesa (lista di {domain, services})",
                           len(reading) if isinstance(reading, list) else "?")

    async def ensure_fresh(self, ha_client) -> None:
        """Ricarica se serve. Un guasto NON svuota cio' che sapevamo.

        Un registro vecchio e' meno peggio di un registro assente: col primo
        HIRIS puo' ancora rifiutare un servizio che non esiste, col secondo
        non puo' verificare niente. Se il rinfresco fallisce si logga e si
        tiene il vecchio -- e `age_seconds()` resta grande, cosi' chi vuole
        saperlo puo' chiederlo.

        Al **primo** caricamento non c'e' nessun vecchio da proteggere:
        li' il guasto risale, perche' un registro mai caricato e un registro
        caricato e vuoto rispondono uguale a chi li interroga, e chi chiama
        deve poterli distinguere.
        """
        age = self.age_seconds()
        if age is not None and age < self._max_age_s and not self._da_rileggere:
            return
        try:
            await self.refresh(ha_client)
        except Exception as error:
            if self.empty():
                raise
            logger.warning("registro servizi: rinfresco fallito (%s: %s), "
                           "tengo quello di %.0fs fa",
                           type(error).__name__, error, age or 0.0)

    def invalidate(self) -> None:
        """«Rileggi appena serve», non «dimentica».

        Lo chiama chi ascolta `service_registered`/`service_removed`. Azzera
        solo l'ETA', non il contenuto: fra l'evento e la rilettura HIRIS deve
        poter ancora verificare qualcosa, e un registro assente e' peggio di
        uno vecchio -- la stessa ragione scritta in `ensure_fresh`, applicata
        al caso opposto.

        E non rilegge da se': installare un'integrazione emette una raffica di
        eventi, e una lettura per ognuno sarebbe una tempesta per un dato che
        serve solo al prossimo comando.
        """
        self._da_rileggere = True

    def service(self, domain: str, name: str) -> dict | None:
        """Il dettaglio di un servizio, o `None` se qui non esiste.

        Quando c'e', il suo `fields` -- se c'e' -- e' gia' normalizzato da
        `_fields`: o una mappa di nomi di parametro, o `None` («c'era, ma in
        una forma che non so leggere»). Chi lo interroga non deve piu'
        indovinare la forma, ed e' l'unico posto in cui quella forma va
        capita.
        """
        return self._per_domain.get(domain, {}).get(name)

    def domains(self) -> list[str]:
        return sorted(self._per_domain)

    def services_for(self, domain: str) -> list[str]:
        return sorted(self._per_domain.get(domain, {}))

    def age_seconds(self) -> float | None:
        """Da quanti secondi il registro e' quello che e'. `None` = mai letto."""
        if self._caricato_a is None:
            return None
        return time.monotonic() - self._caricato_a

    def empty(self) -> bool:
        """Vero finche' nessun caricamento e' mai riuscito.

        Non dice «zero servizi»: dice «mai letto». Un `/api/services` che
        rispondesse una lista vuota lascerebbe questo `False`.
        """
        return self._caricato_a is None
