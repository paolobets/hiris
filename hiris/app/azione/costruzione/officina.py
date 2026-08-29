"""L'unico punto del prodotto che scrive CONFIGURAZIONE su Home Assistant.

E' la sorella di `azione/porta.py`, e insieme a lei realizza l'invariante
riformulato dalla spec (§2.1): **un canale, una porta**. Quella esegue
servizi; questa scrive automazioni, script, scene e helper. I due canali sono
diversi in tutto -- rotta, verifica, «dopo» -- e condividono cio' che conta:
la cronaca, l'`origine`, la forma del rifiuto motivato.

Un terzo punto che scriva su Home Assistant fuori da queste due porte e' un
difetto, non un'ottimizzazione.

**Non solleva mai.** Ogni guasto diventa un dizionario con `errore`, perche' i
suoi chiamanti sono uno strumento che parla a un modello e una rotta HTTP.

**Dove vive la rete (ondata finale, punto 1).** Le primitive REST di
`HAClient` (`leggi_configurazione`, `salva_configurazione`,
`cancella_configurazione`) sollevano quello che rompe il trasporto -- e'
scritto nel loro stesso docstring, e resta vero: quella frase non cambia.
La guardia vive QUI, all'unico chiamante (`_rete`, sotto): un
`ClientConnectorError` o un timeout durante un'`applica` diventano
`{"errore": "Home Assistant non ha risposto: ...", "guasto_rete": True}`,
trattati esattamente come un rifiuto di Home Assistant -- gli helper appena
nati si disfano, la proposta non resta bloccata `in_corso`. Sono le due
frasi -- «solleva solo il trasporto» la' e «non solleva mai» qui -- che con
Home Assistant irraggiungibile durante un'`applica` non potevano restare
vere insieme finche' nessuno metteva la rete da nessuna delle due parti.

**Il giro, e perche' e' in due tempi.** `proponi` compone, valida contro
questa casa e ARCHIVIA una proposta: non tocca niente. `applica` scrive. In
mezzo ci deve stare un umano -- e il modo in cui questo modulo lo sa e' il
`turno`: una proposta non si conferma nel turno che l'ha creata. Se il turno
non e' identificabile, `applica` **rifiuta** invece di lasciar passare: un
cancello che non sa dire chi sta passando non e' un cancello.
"""
from __future__ import annotations

import logging

from ...casa.tempo import zona_casa
from ...proxy._sanitize import truncate_with_marker as _truncate
from . import composer
from .mestiere import consiglia

logger = logging.getLogger(__name__)

# L'etichetta con cui Home Assistant tiene la paternita' di cio' che HIRIS
# costruisce (spec §5). Vive nel registro di HA e non in una tabella nostra:
# e' un fatto che lui sa gia' tenere.
LABEL_NAME = "HIRIS"

# Le origini che sono, per costruzione, un essere umano che ha appena
# cliccato. Per loro la guardia del turno non si applica -- non c'e' nessun
# modello da trattenere.
HUMAN_ACTORS = ("pagina",)

OPERATIONS = ("crea", "modifica", "cancella")

# Le due forme dell'articolo -- indeterminativo per «crea», determinativo per
# «modifica»/«cancella» -- per i tre domini che questa fetta costruisce.
# Script e scena non prendono MAI l'apostrofo: iniziano per consonante.
# Automazione si', perche' inizia per vocale. «un'script», «l'script» e
# «un'scena» sono le forme sbagliate che comparivano in ogni anteprima --
# sotto gli occhi dell'utente, nel testo su cui decide (ondata finale, punto
# 7). La stessa distinzione (con l'apostrofo tipografico ’) vive in
# `ARTICOLO_DOMINIO`, `costruzioni-route.js`: non e' importata da li' (i due
# lati non condividono un modulo), ma la scelta grammaticale e' la stessa.
ARTICOLO_INDETERMINATIVO = {"automation": "un'automazione", "script": "uno script",
                            "scene": "una scena"}
ARTICOLO_DETERMINATIVO = {"automation": "l'automazione", "script": "lo script",
                          "scene": "la scena"}

# Gli stati interni (snake_case) tradotti per una frase rivolta all'utente.
# «applicata», «rifiutata» e «scaduta» sono gia' parole italiane leggibili
# cosi' come sono; «in_corso» no -- e' l'unico che il round 3 della review ha
# trovato a fuoriuscire grezzo in un messaggio d'errore. `.get(stato, stato)`
# tiene la mappa un ripiego, non un obbligo di completezza: uno stato nuovo
# non ancora tradotto resta comunque leggibile, solo con l'underscore.
STATE_READABLE = {
    "applicata": "applicata",
    "rifiutata": "rifiutata",
    "scaduta": "scaduta",
    "in_corso": "in corso",
}


def _state_readable(state: str) -> str:
    return STATE_READABLE.get(state, state)


# Punto 4 (residuo): il messaggio grezzo di `_rete` (sotto) finisce in quattro
# superfici, due permanenti -- `costruzioni.motivo`/`errore` nella cronaca in
# SQLite -- e la cattura larga toglie ogni garanzia sulla sua lunghezza: e'
# quella di QUALUNQUE eccezione, non solo di un guasto di trasporto breve.
#
# M1, terzo giro (correzioni-minori.md, audit-2026-08-25): questa era una
# TERZA copia dello stesso algoritmo gia' unificato da M1 in
# `_sanitize.py::truncate_with_marker` (con `ha_client.py::_truncate` come
# alias dello stesso oggetto) -- nessuno dei tre referti dell'audit l'aveva
# censita. Il commento che stava qui diceva che `_truncate` di `ha_client`
# era privata del modulo, quindi qui si duplicava la forma invece di
# importarla: quella ragione non esiste piu' da quando M1 ha reso
# `truncate_with_marker` pubblica in `_sanitize.py` proprio per essere
# condivisa. Il cap resta 300 -- e' una scelta di QUESTO modulo (il
# messaggio finisce, fra l'altro, nella cronaca permanente in SQLite),
# l'algoritmo e' quello condiviso.
_NETWORK_ERROR_CAP = 300


class Workshop:
    def __init__(self, ha, store, journal, *, read_timezone=None) -> None:
        self._ha = ha
        self._store = store
        self._journal = journal
        self._label_id: str | None = None
        # Una FUNZIONE e non un valore: all'avvio l'archivio della casa puo'
        # non esserci ancora, e il fuso va letto quando serve. Stesso pattern
        # gia' usato per UsageStore (server.py, costruzione di
        # `app["consumi"]`).
        self._read_timezone = read_timezone or (lambda: None)

    def _data(self, ts: float) -> str:
        """La data nel fuso della CASA. Senza, l'ora mostrata e' quella del
        container -- tipicamente UTC su un add-on, cioe' sbagliata per chi
        legge. `zona_casa` ricade su UTC quando il fuso non si sa, e non lo
        inventa mai."""
        import datetime
        return datetime.datetime.fromtimestamp(
            ts, zona_casa(self._read_timezone())).strftime("%d/%m/%Y %H:%M")

    # ---- proporre -------------------------------------------------------

    async def proponi(self, intent: dict, *, actor: str, exchange: str | None,
                      now: float) -> dict:
        operation = intent.get("gesto")
        domain = intent.get("dominio")
        if operation not in OPERATIONS:
            return {"errore": f"gesto sconosciuto: {operation}. Gesti: {', '.join(OPERATIONS)}."}
        if domain not in self._ha.DOMINI_CONFIGURABILI:
            return {"errore": (f"non so costruire «{domain}». So costruire: "
                               f"{', '.join(self._ha.DOMINI_CONFIGURABILI)}.")}
        form_reason = _invalid_form(intent)
        if form_reason is not None:
            return {"errore": form_reason}

        consiglio = consiglia({
            "richiesto": intent.get("richiesto"),
            "innesco": intent.get("innesco"),
            "passi": intent.get("azioni"),
            "stati": intent.get("stati"),
            "parametri": intent.get("parametri"),
            "riuso": intent.get("riuso"),
            "ricorrente": intent.get("ricorrente"),
        })
        if operation in ("crea", "modifica") and not consiglio["strutture"]:
            # L'unico caso in cui il mestiere non ha niente da dire e' proprio
            # quello in cui tace (`consiglia` torna col ritorno anticipato,
            # `dissenso: False`). Senza questo controllo il corpo composto
            # sotto avrebbe tre liste vuote, Home Assistant lo direbbe
            # «valido», e una conferma scriverebbe in casa un'automazione
            # inerte. Per `cancella` non si compone niente: il controllo non
            # si applica.
            return {"errore": consiglio["motivo"] or "non ho capito cosa costruire."}

        prima = None
        key = intent.get("chiave")
        if operation in ("modifica", "cancella"):
            if not key:
                return {"errore": f"per {operation} serve la chiave dell'oggetto da toccare."}
            loaded = await self._rete(self._ha.leggi_configurazione(domain, key))
            if loaded.get("assente"):
                # `leggi_configurazione` ha TRE forme (`corpo`, `errore`,
                # `assente`), non due: indicizzare `letto["corpo"]` su questo
                # ramo solleverebbe `KeyError` fuori dal modulo, raggiungibile
                # con argomenti perfettamente validi -- il modello propone una
                # modifica a un'automazione che l'utente ha cancellato nel
                # frattempo.
                return {"errore": f"non trovo piu' {domain}.{key} in casa tua: "
                                  "forse e' stato cancellato nel frattempo."}
            if "errore" in loaded:
                return {"errore": f"non ho potuto leggere com'e' adesso: {loaded['errore']}"}
            prima = loaded["corpo"]

        if operation == "cancella":
            dopo = None
        else:
            if operation == "crea":
                libera = await self._free_key(domain, intent)
                if "errore" in libera:
                    return libera
                key = libera["chiave"]
            composto = self._compose(intent, key)
            if "errore" in composto:
                return composto
            dopo, key = composto["corpo"], composto["chiave"]
            prova = await self._validate(domain, dopo)
            if prova is not None:
                return {"errore": prova}

        preview = self._preview(operation, domain, key, intent, prima, dopo,
                                    consiglio)
        occurrence = self._store.proponi(
            operation=operation, domain=domain, key=key, actor=actor,
            exchange=exchange, phrase=intent.get("frase"), prima=prima, dopo=dopo,
            helper=list(intent.get("helper") or []), preview=preview,
            now=now)
        if "errore" in occurrence:
            return occurrence
        return {"proposta_id": occurrence["id"], "anteprima": preview,
                "consiglio": consiglio}

    async def _free_key(self, domain: str, intent: dict) -> dict:
        """Una chiave che in questa casa non e' gia' occupata.

        **Un id gia' in uso non darebbe un errore: farebbe SOSTITUIRE la voce
        che c'era**, perche' `_write_value` di Home Assistant trova per `id` e
        rimpiazza. E' la stessa famiglia del danno misurato su
        `automations.yaml`, vista dall'altro lato, e l'unica difesa e' chiedere
        prima.

        Si distingue `assente` da `errore` (vedi `leggi_configurazione`): se
        Home Assistant non risponde **non si dichiara libera** nessuna chiave.
        """
        alias = intent.get("alias") or ""
        occupate: set[str] = set()
        if domain == "script":
            candidata = composer.slug_libero(alias, occupate)
        else:
            candidata = composer.nuovo_id(occupate, seme=_seme_da(intent))
        for _ in range(5):
            loaded = await self._rete(self._ha.leggi_configurazione(domain, candidata))
            if loaded.get("assente"):
                return {"chiave": candidata}
            if "errore" in loaded:
                return {"errore": ("non ho potuto verificare se l'identificatore e' "
                                   f"libero: {loaded['errore']}. Non scrivo alla cieca.")}
            occupate.add(candidata)
            if domain == "script":
                candidata = composer.slug_libero(alias, occupate)
            else:
                candidata = composer.nuovo_id(occupate, seme=int(candidata) + 1)
        return {"errore": "non sono riuscito a trovare un identificatore libero."}

    def _compose(self, intent: dict, key: str | None) -> dict:
        domain = intent["dominio"]
        alias = intent.get("alias") or ""
        descrizione = intent.get("descrizione") or ""
        if not alias:
            return {"errore": "serve un nome per l'oggetto da costruire."}
        if domain == "automation":
            ident = key or composer.nuovo_id(set(), seme=_seme_da(intent))
            return {"chiave": ident, "corpo": composer.compose_automation(
                id_=ident, alias=alias, descrizione=descrizione,
                innesco=intent.get("innesco") or [],
                conditions=intent.get("condizioni") or [],
                actions=intent.get("azioni") or [])}
        if domain == "script":
            slug = key or composer.slug_libero(alias, set())
            return {"chiave": slug, "corpo": composer.compose_script(
                alias=alias, descrizione=descrizione,
                passi=intent.get("azioni") or [],
                fields=intent.get("campi"))}
        # Una scena e' l'unico dominio che a valle NON viene validato da Home
        # Assistant (`parti_da_validare` restituisce {} di proposito): se uno
        # stato e' malformato o ripetuto, QUESTO e' l'ultimo posto in cui
        # qualcuno puo' accorgersene. `compose_scene` scarterebbe in silenzio.
        guai = composer.state_problems(intent.get("stati") or [])
        if guai:
            return {"errore": "non posso comporre la scena -- " + "; ".join(guai)}
        ident = key or composer.nuovo_id(set(), seme=_seme_da(intent))
        return {"chiave": ident, "corpo": composer.compose_scene(
            id_=ident, alias=alias, states=intent.get("stati") or [])}

    async def _validate(self, domain: str, body: dict) -> str | None:
        """`None` se va bene, altrimenti il motivo -- quello di Home Assistant."""
        parti = composer.parti_da_validare(domain, body)
        if not parti:
            return None
        occurrence = await self._ha.valida_config(**parti)
        if "errore" in occurrence:
            return f"non ho potuto far validare la configurazione: {occurrence['errore']}"
        guasti = [f"{key}: {entry.get('error')}"
                  for key, entry in occurrence.items()
                  if isinstance(entry, dict) and not entry.get("valid")]
        if guasti:
            return "Home Assistant rifiuta questa configurazione -- " + "; ".join(guasti)
        return None

    def _preview(self, operation, domain, key, intent, prima, dopo,
                   consiglio) -> str:
        # `.get(dominio, dominio)`, non un indice nudo: l'elenco dei domini
        # configurabili e' del client (`HAClient.DOMINI_CONFIGURABILI`), non
        # di queste tabelle locali (ARTICOLO_INDETERMINATIVO/DETERMINATIVO,
        # sopra) -- un quarto dominio aggiunto la' solleverebbe `KeyError` qui.
        righe = []
        if operation == "crea":
            # Punto 5 (residuo): la correzione dell'articolo (ondata finale,
            # punto 7) non toccava il participio -- «chiamata» concorda solo
            # con automazione e scena, e «uno script chiamata «X»» restava
            # sgrammaticato. «di nome» e' invariabile: non serve una terza
            # tabella di concordanze.
            righe.append(f"Creo {ARTICOLO_INDETERMINATIVO.get(domain, domain)} "
                         f"di nome «{intent.get('alias')}».")
        elif operation == "modifica":
            righe.append(f"Modifico {ARTICOLO_DETERMINATIVO.get(domain, domain)} "
                         f"«{(prima or {}).get('alias') or key}», "
                         "che esiste già in casa tua.")
            righe.append(f"Prima: {_compatta(prima)}")
            righe.append(f"Dopo: {_compatta(dopo)}")
        else:
            righe.append(f"Cancello {ARTICOLO_DETERMINATIVO.get(domain, domain)} "
                         f"«{(prima or {}).get('alias') or key}», "
                         "che esiste già in casa tua. Conservo com'era.")
        if intent.get("descrizione"):
            righe.append(f"A cosa serve: {intent['descrizione']}")
        for helper in intent.get("helper") or []:
            righe.append(f"Nasce anche un {helper.get('dominio')}: "
                         f"{(helper.get('dati') or {}).get('name')}")
        if consiglio.get("motivo"):
            # Prima finiva nell'anteprima solo in caso di dissenso: ma il
            # verdetto del mestiere e' un fatto utile anche quando concorda,
            # non solo quando litiga.
            righe.append(f"Nota: {consiglio['motivo']}.")
        righe.append("Non ho scritto niente: dimmi di procedere e lo faccio.")
        return "\n".join(righe)

    # ---- applicare ------------------------------------------------------

    async def applica(self, proposal_id: str, *, actor: str, exchange: str | None,
                      now: float) -> dict:
        proposal = self._store.read(proposal_id)
        if proposal is None:
            return {"errore": "non ho nessuna proposta con quell'identificatore."}
        if proposal["stato"] != "in_attesa":
            return {"errore": f"quella proposta e' gia' {_state_readable(proposal['stato'])}."}
        cancello = self._cancello(proposal, actor, exchange)
        if cancello is not None:
            return {"errore": cancello}

        # Rivendicazione atomica (spec §7): il controllo sullo stato appena
        # letto qui sopra non basta -- e' una lettura che una richiesta
        # concorrente (doppio clic sulla pagina, o pagina e chat insieme) puo'
        # gia' aver superato prima che questa arrivi a scrivere. La UPDATE
        # atomica `WHERE stato='in_attesa'` di `ConstructionStore.rivendica`
        # e' l'unico punto in cui chi arriva prima puo' davvero vincere.
        rivendicata = self._store.rivendica(proposal_id, now=now)
        if "errore" in rivendicata:
            return {"errore": "quella proposta e' gia' stata presa in carico da "
                              "un'altra richiesta."}

        domain, key, operation = proposal["dominio"], proposal["chiave"], proposal["gesto"]
        nati: list[tuple[str, str]] = []
        senza_id: list[str] = []
        for helper in proposal["helper"]:
            occurrence = await self._ha.crea_helper(helper.get("dominio"),
                                               helper.get("dati") or {})
            if "errore" in occurrence:
                note = await self._disfa(nati, senza_id)
                return self._fallita(proposal, now, actor,
                                     f"non sono riuscito a creare l'helper: "
                                     f"{occurrence['errore']}{note}")
            creato = occurrence.get("helper") or {}
            if creato.get("id"):
                nati.append((helper.get("dominio"), creato["id"]))
            else:
                # Creato, ma senza un id restituito: non entra in `nati` e
                # quindi non e' mai disfabile da questo modulo. Tacerlo
                # sarebbe la stessa spazzatura di un helper mai disfatto, in
                # una forma piu' subdola -- l'utente non saprebbe nemmeno che
                # c'e' qualcosa da controllare (spec §3.1).
                senza_id.append(str(helper.get("dominio")))

        if operation == "cancella":
            written = await self._rete(self._ha.cancella_configurazione(domain, key))
            riuscito = "cancellato" in written
        else:
            written = await self._rete(
                self._ha.salva_configurazione(domain, key, proposal["dopo"]))
            riuscito = "salvato" in written

        if not riuscito:
            note = await self._disfa(nati, senza_id)
            guasto_rete = written.get("guasto_rete", False)
            raw_error = written.get("errore", "")
            # Punto 2 (residuo): `_translate_rejection` cerca «404» come SOTTOSTRINGA
            # nuda su tutto il messaggio -- un guasto di rete puo' contenere
            # quella cifra per caso (una porta, un IP) e uscirebbe come una
            # spiegazione architetturale falsa («queste automazioni sono
            # gestite a mano...») invece che come cio' che e' davvero: Home
            # Assistant irraggiungibile. Il flag che l'ondata ha introdotto
            # due righe sopra distingue gia' i due casi -- non serve indovinare
            # dal testo.
            reason = raw_error if guasto_rete else _translate_rejection(
                raw_error, domain)
            return self._fallita(proposal, now, actor, reason + note,
                                 guasto_rete=guasto_rete)

        entity, notice = await self._reread(domain, key, operation)
        if operation == "crea":
            # L'etichetta dice CHI L'HA FATTO, e su una modifica non l'ha fatto
            # HIRIS (spec §5). Un oggetto scritto dal proprietario resta suo
            # anche dopo che HIRIS ci ha messo le mani: che ce le abbia messe
            # e' un fatto DIVERSO, e vive dove lo si puo' interrogare -- la
            # cronaca, l'archivio delle versioni, la pagina.
            for entity_id in entity:
                await self._label(entity_id)
        # Gli helper sono SEMPRE nati -- `crea_helper` non e' altro --
        # indipendentemente dal gesto sul dominio principale: una
        # `modifica` puo' portarsi dietro un helper nuovo tanto quanto un
        # `crea`. Spec §5, testuale: l'etichetta si applica «all'entita'
        # nata, helper compresi». Senza questa riga `_rileggi` (sopra)
        # filtra per `{dominio}.`, quindi un `input_boolean` nato da HIRIS
        # non riceveva mai l'etichetta -- e poiche' la paternita' vive nel
        # registro di Home Assistant e non in una tabella nostra (fondamenta
        # 2, spec §5), quella paternita' non esisteva da NESSUNA parte
        # (fondamenta 4: un dato che nessuno puo' chiedere non esiste).
        for domain_helper, helper_id in nati:
            await self._label(f"{domain_helper}.{helper_id}")

        execution_id = self._journal.log_construction(
            actor=actor, operation=operation, domain=domain, key=key,
            entity=entity, eseguito=True, now=now, notice=notice)
        occurrence_state = self._store.mark_applied(proposal_id, now=now,
                                                      execution_id=execution_id)
        if "errore" in occurrence_state:
            # Non ignorato: se la riga non e' piu' rivendicabile (un caso che
            # oggi non dovrebbe capitare, essendo appena stata rivendicata da
            # QUESTA chiamata) l'utente ha comunque avuto il suo risultato --
            # Home Assistant ha scritto -- e la traccia serve a chi legge il
            # log, non a cambiare l'esito verso l'utente.
            logger.warning("mark_applied non riuscita per %s: %s", proposal_id,
                           occurrence_state["errore"])
        return {"applicata": True, "esecuzione_id": execution_id,
                "entita": entity, "avviso": notice}

    def _cancello(self, proposal: dict, actor: str, exchange: str | None) -> str | None:
        """Il sì dell'umano, reso una guardia deterministica (spec §7).

        Il modello propone e il codice restringe: se `applica` fosse solo
        un'altra chiamata, il modello potrebbe concatenarla nello stesso turno
        e il sì dell'utente sparirebbe senza che nessuno se ne accorga.
        """
        if actor in HUMAN_ACTORS:
            # Qualunque valore di `origine` uguale a una voce di HUMAN_ACTORS
            # scavalca la guardia: se il Task 8 (o chi verra' dopo) sbagliasse
            # a inoltrare un'origine scelta dal modello come `pagina`, questa
            # riga e' l'unica traccia che ne resterebbe.
            logger.info("cancello scavalcato dall'origine umana %r per la proposta %s",
                       actor, proposal["id"])
            return None
        # Una proposta nata SENZA identita' di turno (il ramo sincrono della
        # chat, un'intestazione mancante -- casi normali) non e' confermabile
        # da un'origine non umana, qualunque turno arrivi dopo. La forma
        # precedente (`proposta["turno"] and proposta["turno"] == turno`)
        # restava FALSA quando il turno memorizzato era `None`, e lasciava
        # passare la prima conferma che capitava: la regola giusta e'
        # l'inversa, e la strada e' la stessa di un chiamante che oggi non
        # porta un turno -- la pagina.
        if not exchange or not proposal["turno"]:
            return ("non riesco a distinguere i turni, quindi non posso confermare da qui: "
                    "apri la pagina Costruzioni e conferma di la'.")
        if proposal["turno"] == exchange:
            return ("questa proposta e' nata in questo stesso turno: te l'ho mostrata, "
                    "ora dimmi tu se procedere.")
        return None

    async def _rete(self, call) -> dict:
        """Esegue una chiamata alle primitive REST di `HAClient`, catturando i
        guasti di TRASPORTO (ondata finale, punto 1).

        `leggi_configurazione`, `salva_configurazione` e
        `cancella_configurazione` sollevano quello che rompe il trasporto --
        e' scritto nel loro docstring (`proxy/ha_client.py`), e resta cosi':
        la guardia vive qui, all'unico chiamante, non li'. Senza di lei, un
        Home Assistant irraggiungibile durante un'`applica` salterebbe
        `_disfa` (spazzatura in casa dell'utente, spec §3.1), lascerebbe la
        riga bloccata `in_corso` fino al riavvio, e farebbe uscire un 500
        grezzo dalla pagina invece del contratto 404/409/503 dichiarato da
        `handlers_costruzioni.py`.

        Ritorna cio' che `chiamata` ritorna, oppure `{"errore": "Home
        Assistant non ha risposto: ...", "guasto_rete": True}` -- la stessa
        forma con cui l'officina dice ogni altro guasto, con in piu' il flag
        che distingue un guasto di rete da un rifiuto vero di Home Assistant.
        Il messaggio dell'eccezione e' troncato (punto 4, residuo): finisce in
        quattro superfici, due permanenti (`costruzioni.motivo`/`errore` nella
        cronaca in SQLite), e la cattura larga toglie ogni garanzia sulla sua
        lunghezza -- e' quella di QUALUNQUE eccezione, non solo di un guasto
        di trasporto breve.
        """
        try:
            return await call
        except Exception as exc:
            # Punto 3 (residuo): la cattura larga e' la scelta giusta (restringere
            # vorrebbe dire importare aiohttp qui, in un modulo deliberatamente
            # agnostico al trasporto), ma senza tipo ne' traceback un nostro
            # `TypeError` diventa indistinguibile, in log, da un guasto di rete
            # vero -- il difetto nascosto due volte. Stessa forma gia' usata da
            # `casa/strumenti.py` nella sua rete finale.
            logger.warning("chiamata verso Home Assistant non riuscita (%s): %s",
                           type(exc).__name__, exc, exc_info=True)
            return {"errore": (f"Home Assistant non ha risposto: "
                               f"{_truncate(str(exc), _NETWORK_ERROR_CAP)}"),
                    "guasto_rete": True}

    async def _disfa(self, nati: list[tuple[str, str]],
                     senza_id: list[str] | None = None) -> str:
        """Prova a disfare gli helper nati, e DICE cosa e' successo (spec §3.1).

        Senza questa disfatta ogni tentativo fallito lascia rifiuti in casa
        dell'utente -- ed e' il modo esatto in cui si accumula la spazzatura
        che nessuno cancella piu'. Ma disfare in silenzio non basta: se anche
        `cancella_helper` fallisce a sua volta, o un helper non e' mai entrato
        fra i disfabili (nessun `id` restituito alla creazione), tacerlo
        lascerebbe l'archivio dire «non e' successo niente» mentre in casa
        resta un orfano che nessuno pulira' piu'. Restituisce il pezzo di
        frase da appendere al motivo del rifiuto, o `""` se non c'e' niente
        da dire.
        """
        disfatti: list[str] = []
        rimasti: list[str] = []
        for domain, helper_id in reversed(nati):
            occurrence = await self._ha.cancella_helper(domain, helper_id)
            if "errore" in occurrence:
                logger.warning("helper %s.%s creato e NON disfatto: %s",
                               domain, helper_id, occurrence["errore"])
                rimasti.append(f"{domain}.{helper_id}")
            else:
                disfatti.append(f"{domain}.{helper_id}")
        pezzi: list[str] = []
        if disfatti:
            pezzi.append("ho tolto anche " + ", ".join(disfatti))
        if rimasti:
            pezzi.append("l'helper " + ", ".join(rimasti) +
                         " e' rimasto in casa tua, toglilo a mano")
        for domain in senza_id or []:
            pezzi.append(f"un helper {domain} e' stato creato ma senza un id "
                         "restituito: non posso disfarlo automaticamente, "
                         "controllalo a mano")
        return (" " + "; ".join(pezzi) + ".") if pezzi else ""

    def _fallita(self, proposal: dict, now: float, actor: str, reason: str, *,
                guasto_rete: bool = False) -> dict:
        execution_id = self._journal.log_construction(
            actor=actor, operation=proposal["gesto"], domain=proposal["dominio"],
            key=proposal["chiave"], entity=[], eseguito=False, now=now,
            error=reason)
        occurrence_state = self._store.mark_rejected(proposal["id"], now=now,
                                                      reason=reason)
        if "errore" in occurrence_state:
            logger.warning("mark_rejected non riuscita per %s: %s", proposal["id"],
                           occurrence_state["errore"])
        occurrence = {"errore": reason, "esecuzione_id": execution_id}
        if guasto_rete:
            # Distingue un guasto di TRASPORTO da un rifiuto vero di Home
            # Assistant (validazione, 400): `_agisci` (handlers_costruzioni.py)
            # legge questo flag per rispondere 503 invece di 409 -- la stessa
            # indisponibilita' che la GET dichiarerebbe (ondata finale, punto
            # 7, terza pulizia).
            occurrence["guasto_rete"] = True
        return occurrence

    async def _reread(self, domain: str, key: str,
                       operation: str) -> tuple[list[str], str | None]:
        """Cosa e' comparso davvero. Dire cosa e' successo, non cosa e' stato
        chiesto (spec §2.3)."""
        if operation == "cancella":
            return [], None
        try:
            states = await self._ha.get_states([])
        except Exception as exc:
            logger.debug("rilettura dopo la scrittura fallita: %s", exc)
            return [], ("ho scritto, ma non sono riuscito a rileggere lo stato: "
                        "controlla in Home Assistant.")
        trovate = []
        for state in states or []:
            eid = state.get("entity_id") or ""
            if not eid.startswith(f"{domain}."):
                continue
            attributes = state.get("attributes") or {}
            if attributes.get("id") == key or eid == f"{domain}.{key}":
                trovate.append(eid)
        if not trovate:
            return [], ("Home Assistant ha accettato la scrittura ma l'entita' non e' "
                        "ancora comparsa: potrebbe servire un riavvio, o la ricarica "
                        "non e' andata a buon fine.")
        return trovate, None

    async def _label(self, entity_id: str) -> None:
        if self._label_id is None and not await self._resolve_label():
            return
        occurrence = await self._ha.aggiungi_etichetta_a(entity_id, self._label_id)
        if "errore" not in occurrence:
            return
        # Il `label_id` in cache potrebbe non esistere piu' in Home Assistant
        # (etichetta cancellata a mano dopo la prima risoluzione): restare
        # muti fino al riavvio perderebbe la paternita' di ogni oggetto
        # successivo in silenzio. Si azzera la cache e si ritenta UNA volta.
        logger.warning("etichetta non applicata a %s (label_id=%s): %s -- riprovo "
                       "risolvendo l'etichetta da capo", entity_id, self._label_id,
                       occurrence["errore"])
        self._label_id = None
        if not await self._resolve_label():
            return
        occurrence = await self._ha.aggiungi_etichetta_a(entity_id, self._label_id)
        if "errore" in occurrence:
            logger.warning("etichetta non applicata a %s nemmeno al secondo tentativo: %s",
                           entity_id, occurrence["errore"])

    async def _resolve_label(self) -> bool:
        """Trova o crea il `label_id` di HIRIS in Home Assistant, aggiornando
        la cache dell'istanza. Restituisce True se una `label_id` valida e'
        nota dopo la chiamata."""
        response = await self._ha.elenca_etichette()
        if "errore" in response:
            logger.debug("etichette non lette: %s", response["errore"])
            return False
        for entry in response["etichette"]:
            if (entry.get("name") or "").strip().lower() == LABEL_NAME.lower():
                self._label_id = entry.get("label_id")
                break
        if self._label_id is None:
            creata = await self._ha.crea_etichetta(LABEL_NAME)
            if "errore" in creata:
                logger.debug("etichetta non creata: %s", creata["errore"])
                return False
            self._label_id = (creata.get("etichetta") or {}).get("label_id")
        return self._label_id is not None

    # ---- ripristinare ---------------------------------------------------

    async def ripristina(self, construction_id: str, *, actor: str,
                         exchange: str | None, now: float) -> dict:
        """Rimettere il «prima» e' un'ALTRA costruzione, e passa di qui.

        Non e' una scorciatoia che scrive diretta: valida come tutte le altre,
        e se nel frattempo quel corpo non e' piu' valido lo dice invece di
        scriverlo (spec §6).
        """
        row = self._store.read(construction_id)
        if row is None:
            return {"errore": "non ho nessuna costruzione con quell'identificatore."}
        if row["stato"] != "applicata":
            return {"errore": "quella costruzione non e' mai stata applicata: "
                              "non c'e' niente da rimettere."}
        prima = row["prima"]
        domain, key = row["dominio"], row["chiave"]
        if prima is None:
            # Ripristinare una CREAZIONE significa cancellare cio' che e' nato.
            intent_operation, dopo = "cancella", None
        else:
            intent_operation, dopo = "modifica", prima
            reason = await self._validate(domain, dopo)
            if reason is not None:
                return {"errore": f"non posso rimettere com'era: {reason}"}
        preview = (f"Rimetto l'oggetto {domain}.{key} com'era prima "
                     f"del {self._data(row['creata_ts'])}.")
        proposal = self._store.proponi(
            operation=intent_operation, domain=domain, key=key, actor=actor,
            exchange=exchange, phrase=f"ripristino di {construction_id}", prima=row["dopo"],
            dopo=dopo, helper=[], preview=preview, now=now)
        if "errore" in proposal:
            return proposal
        if actor in HUMAN_ACTORS:
            return await self.applica(proposal["id"], actor=actor, exchange=exchange,
                                      now=now)
        # Dalla chat il ripristino e' un giro in due tempi come tutto il
        # resto (spec §7): applicarlo subito con lo STESSO `turno` che ha
        # appena creato la proposta farebbe rifiutare SEMPRE dal cancello (e'
        # letteralmente lo stesso turno), e la riga resterebbe `in_attesa` a
        # bruciare un posto del tetto di 20 per sette giorni -- venti
        # tentativi bloccherebbero le proposte di tutto il prodotto.
        if not exchange:
            # Senza un turno riconoscibile questa proposta non sara' MAI
            # confermabile da un'origine non umana (`_cancello`, IMPORTANT 1
            # del round 2): l'unica strada e' la pagina, e l'anteprima
            # restituita deve dirlo -- lo stesso messaggio che `applica` da'
            # gia' in quel caso, non un'anteprima muta su un vicolo cieco.
            preview += ("\nSenza un turno riconoscibile non potro' confermare da "
                         "qui: apri la pagina Costruzioni e conferma di la'.")
        return {"proposta_id": proposal["id"], "anteprima": preview}


def _invalid_form(intent: dict) -> str | None:
    """Le forme che l'intento deve avere perche' il resto del modulo non
    sollevi. Il chiamante e' uno strumento riempito da un modello: un `alias`
    che arriva come dizionario o un `helper` che arriva come lista di
    stringhe non sono ipotesi remote, sono un modello che ha sbagliato la
    forma di un campo -- e vanno rifiutati con un motivo leggibile, non
    lasciati esplodere piu' sotto (`_seme_da` su un `alias` non hashabile con
    `TypeError: unhashable type`, `helper.get(...)` su una stringa con
    `AttributeError`).

    **`chiave` e `campi` (round 3 della review, IMPORTANT 6 chiuso solo a
    meta').** `"chiave": 1771` invece di `"1771"` e' l'errore di forma piu'
    probabile che un modello faccia su questo campo: essendo un intero
    truthy, arriva intatto a `HAClient._CHIAVE_RE.match(chiave or "")` (l'`or`
    sostituisce solo i valori falsy) e solleva `TypeError`. `campi` non
    testuale-a-dizionario arriva a `composer.compose_script`, che fa
    `dict(campi)` -- `ValueError` su una stringa, `TypeError` su un intero.
    """
    for field in ("alias", "descrizione", "frase", "chiave"):
        value = intent.get(field)
        if value is not None and not isinstance(value, str):
            return f"«{field}» deve essere testo, non {type(value).__name__}."
    for field in ("innesco", "condizioni", "azioni", "stati", "helper", "parametri"):
        value = intent.get(field)
        if value is not None and not isinstance(value, list):
            return f"«{field}» deve essere una lista, non {type(value).__name__}."
    fields = intent.get("campi")
    if fields is not None and not isinstance(fields, dict):
        return f"«campi» deve essere un dizionario, non {type(fields).__name__}."
    for entry in intent.get("helper") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("dominio"), str):
            return "ogni helper deve essere un dizionario con un «dominio» testuale."
    return None


def _seme_da(intent: dict) -> int:
    """Un seme per l'id, derivato dall'intento e non dall'orologio.

    L'orologio lo legge il chiamante (`adesso`), non le funzioni pure: qui
    serve solo un numero grande e stabile PER LA DURATA DI QUESTO PROCESSO.
    `hash()` su una tupla di stringhe e' salato per processo in Python (non
    e' la lunghezza del testo a determinarlo): lo stesso intento produce semi
    diversi fra un riavvio e l'altro, e non e' un problema, perche' la
    verifica di unicita' VERA la fa `forme.nuovo_id` contro gli id esistenti
    in QUESTA casa, e Home Assistant rifiuterebbe comunque un duplicato.
    """
    base = 1_700_000_000_000
    return base + abs(hash((intent.get("alias"), intent.get("frase")))) % 100_000_000


def _compatta(body: dict | None) -> str:
    if not body:
        return "(niente)"
    pezzi = []
    for key in ("alias", "name", "description"):
        if body.get(key):
            pezzi.append(str(body[key]))
    for key in ("triggers", "conditions", "actions", "sequence", "entities"):
        if body.get(key):
            pezzi.append(f"{key}: {len(body[key])}")
    return " · ".join(pezzi) if pezzi else "(vuoto)"


def _translate_rejection(error: str, domain: str) -> str:
    """Un presupposto d'ambiente non deve sembrare un guasto (spec §6).

    Se l'API di configurazione non c'e' o non governa quella struttura --
    automazioni scritte a mano, o in `packages/` -- Home Assistant risponde
    404. Dirlo come «404» costringerebbe l'utente a indovinare cosa e'
    successo.
    """
    # RULING 2 della scansione pre-volo: il nome del dominio va in ITALIANO --
    # e' una frase rivolta all'utente, e i vincoli globali lo impongono.
    plurale = {"automation": "automazioni", "script": "script",
               "scene": "scene"}.get(domain, domain)
    if "404" in error or "not found" in error.lower():
        return (f"queste {plurale} sono gestite a mano (o vivono in `packages/`): "
                "l'API di configurazione di Home Assistant non le governa, e non posso "
                "scriverle. Posso mostrarti il pezzo corretto da incollare.")
    return error
