"""L'unico punto del prodotto che scrive CONFIGURAZIONE su Home Assistant.

E' la sorella di `action/actuator.py`, e insieme a lei realizza l'invariante
riformulato dalla spec (§2.1): **un canale, una porta**. Quella esegue
servizi; questa scrive automazioni, script, scene e helper. I due canali sono
diversi in tutto -- rotta, verifica, «dopo» -- e condividono cio' che conta:
la cronaca, l'`origine`, la forma del rifiuto motivato.

Un terzo punto che scriva su Home Assistant fuori da queste due porte e' un
difetto, non un'ottimizzazione.

**Non solleva mai.** Ogni guasto diventa un dizionario con `errore`, perche' i
suoi chiamanti sono uno strumento che parla a un modello e una rotta HTTP.

**Dove vive la rete (ondata finale, punto 1).** Le primitive REST di
`HAClient` (`read_configuration`, `save_configuration`,
`delete_configuration`) sollevano quello che rompe il trasporto -- e'
scritto nel loro stesso docstring, e resta vero: quella frase non cambia.
La guardia vive QUI, all'unico chiamante (`_rete`, sotto): un
`ClientConnectorError` o un timeout durante un'`apply` diventano
`{"errore": "Home Assistant non ha risposto: ...", "guasto_rete": True}`,
trattati esattamente come un rifiuto di Home Assistant -- gli helper appena
nati si disfano, la proposta non resta bloccata `in_corso`. Sono le due
frasi -- «solleva solo il trasporto» la' e «non solleva mai» qui -- che con
Home Assistant irraggiungibile durante un'`apply` non potevano restare
vere insieme finche' nessuno metteva la rete da nessuna delle due parti.

**Il giro, e perche' e' in due tempi.** `propose` compone, valida contro
questa casa e ARCHIVIA una proposta: non tocca niente. `apply` scrive. In
mezzo ci deve stare un umano -- e il modo in cui questo modulo lo sa e' il
`turno`: una proposta non si conferma nel turno che l'ha creata. Se il turno
non e' identificabile, `apply` **rifiuta** invece di lasciar passare: un
cancello che non sa dire chi sta passando non e' un cancello.
"""
from __future__ import annotations

import logging

from ...chat_thread import ChatThread
from ...home_space.historian import home_space_zone
from ...proxy._sanitize import truncate_with_marker as _truncate
from . import composer
from .advisor import STRUCTURES, consiglia

logger = logging.getLogger(__name__)

# L'etichetta con cui Home Assistant tiene la paternita' di cio' che HIRIS
# costruisce (spec §5). Vive nel registro di HA e non in una tabella nostra:
# e' un fatto che lui sa gia' tenere.
LABEL_NAME = "HIRIS"

# Le origini che sono, per costruzione, un essere umano che ha appena
# cliccato. Per loro la guardia del turno non si applica -- non c'e' nessun
# modello da trattenere.
HUMAN_ACTORS = ("pagina",)

#: Il rifiuto di una proposta nata nel turno che la vorrebbe confermare.
#: Scritto una volta sola perche' lo danno DUE porte -- il cancello, e il
#: lettore che sceglie la proposta quando l'utente non l'ha nominata -- e
#: due frasi diverse per lo stesso rifiuto insegnerebbero al modello che
#: sono due casi diversi.
_BORN_THIS_TURN = ("questa proposta e' nata in questo stesso turno: te l’ho "
             "mostrata, ora dimmi tu se procedere.")

#: Il rifiuto di un id che non esiste -- e, dal Task 7 «confirm resta nel
#: filo», anche di un id che esiste ma appartiene al filo di qualcun altro
#: (spec §5, decisione 4: si legge solo il proprio filo, e un rifiuto non
#: nomina mai la proposta di un altro). Una sola costante per i due casi: dal
#: lato di chi chiede sono indistinguibili PER COSTRUZIONE, e due testi
#: diversi lascerebbero trapelare che una proposta con quell'id esiste
#: davvero, solo altrove.
_UNKNOWN_ID = "non ho nessuna proposta con quell’identificatore."

#: Fix round 1 (Task 7): quando la scelta implicita di QUESTO filo non trova
#: niente, ma esistono proposte `in_attesa` ORFANE (`subject_key IS NULL`:
#: nate prima della fetta, o dall'attuatore) -- il difetto del 23/09/2026
#: regredito. Dire «dimmi cosa vuoi e te la propongo» farebbe RIPROPORRE una
#: cosa che esiste gia', bruciando un posto sotto il tetto per un doppione.
#: Non le nomina (decisione 4): dice solo che una pagina le mostra.
_ORPHANS_ELSEWHERE = ("ci sono proposte in sospeso che non sono nate in questa "
                     "conversazione: si confermano dalla pagina Costruzioni.")

OPERATIONS = ("crea", "modifica", "cancella")

# Le due forme dell'articolo -- indeterminativo per «crea», determinativo per
# «modifica»/«cancella» -- per i tre domini che questa fetta costruisce.
# Script e scena non prendono MAI l'apostrofo: iniziano per consonante.
# Automazione si', perche' inizia per vocale. «un'script», «l'script» e
# «un'scena» sono le forme sbagliate che comparivano in ogni anteprima --
# sotto gli occhi dell'utente, nel testo su cui decide (ondata finale, punto
# 7). La stessa distinzione (con l'apostrofo tipografico ’) vive in
# `DOMAIN_ARTICLE`, `constructions-route.js`: non e' importata da li' (i due
# lati non condividono un modulo), ma la scelta grammaticale e' la stessa.
ARTICOLO_INDETERMINATIVO = {"automation": "un’automazione", "script": "uno script",
                            "scene": "una scena"}
ARTICOLO_DETERMINATIVO = {"automation": "l’automazione", "script": "lo script",
                          "scene": "la scena"}

# Gli stati interni (snake_case) tradotti per una frase rivolta all'utente.
# «applicata», «rifiutata» e «scaduta» sono gia' parole italiane leggibili
# cosi' come sono; «in_corso» no -- e' l'unico che il round 3 della review ha
# trovato a fuoriuscire grezzo in un messaggio d'errore. `.get(stato, stato)`
# tiene la mappa un ripiego, non un obbligo di completezza: uno stato nuovo
# non ancora tradotto resta comunque leggibile, solo con l'underscore.
READABLE_STATE = {
    "applicata": "applicata",
    "rifiutata": "rifiutata",
    "scaduta": "scaduta",
    "in_corso": "in corso",
}


def _readable_state(state: str) -> str:
    return READABLE_STATE.get(state, state)


#: Quanto si conserva della frase che conferma (B-5). La cronaca la rilegge
#: `logbook`, che la porta al modello: un muro di testo incollato in chat
#: diventerebbe carico a ogni turno, per i novanta giorni della conservazione.
#: Un sì sta in poche parole; quel che eccede non aggiunge niente alla domanda
#: a cui questo campo risponde («chi ha detto sì?»).
PHRASE_MAX = 240


def _add_phrase(subject: dict | None, phrase: str | None) -> dict | None:
    """Il soggetto con dentro la frase che ha confermato — **una copia**.

    Il dizionario che arriva dal confine vive quanto la richiesta e lo leggono
    anche altri: scriverci dentro sarebbe un effetto a distanza su un oggetto
    di qualcun altro.

    **L'assenza e' un fatto, e non si finge.** Una conferma dalla pagina non
    porta nessuna frase perche' il clic *e'* il si'; una promessa notturna e
    un servizio via MCP non hanno nessuna persona che parli. In tutti e tre i
    casi la chiave non c'e' -- e «non c'e'» non e' `""`, che si leggerebbe
    come «ha detto niente».

    E la frase nasce anche **senza** soggetto: sono due fatti indipendenti, e
    legarli perderebbe quello che c'e' per colpa di quello che manca.
    """
    detto = (phrase or "").strip()
    if not detto:
        return subject
    if len(detto) > PHRASE_MAX:
        # Il taglio **si dichiara**: senza il marcatore, quella sembrerebbe la
        # frase intera, e chi legge la cronaca giudicherebbe su meta' di cio'
        # che e' stato detto.
        detto = detto[:PHRASE_MAX] + "…"
    return {**(subject or {}), "confirm_phrase": detto}


# Punto 4 (residuo): il messaggio grezzo di `_rete` (sotto) finisce in quattro
# superfici, due permanenti -- `costruzioni.motivo`/`errore` nella cronaca in
# SQLite -- e la cattura larga toglie ogni garanzia sulla sua lunghezza: e'
# quella di QUALUNQUE eccezione, non solo di un guasto di trasporto breve.
#
# M1, terzo giro (revisione di agosto 2026): questa era una
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


def _same_thread(proposal: dict, thread: ChatThread) -> bool:
    """Vero se `proposal` e' nata esattamente nel filo `thread`. Il
    chiamante garantisce `thread` non `None` -- vedi `_thread_may_confirm`
    e `Workshop._only_pending`, che decidono loro cosa fare di `None`."""
    return (proposal.get("subject_key") == thread.subject_key
            and proposal.get("entry_point") == thread.entry_point)


def _thread_may_confirm(proposal: dict, thread: ChatThread | None) -> bool:
    """Vero se questo filo puo' confermare `proposal` PER ID (spec §5).

    **`thread=None` non restringe.** E' il valore che passano i chiamanti
    interni -- la pagina (`handlers_constructions.py`, che mostra e conferma
    proposte di OGNI filo: e' la vista dell'amministratore, non una
    conversazione) e il ramo di `restore` che l'origine umana applica subito
    (sotto) -- e per loro vale il comportamento di sempre: nessuna
    restrizione nuova. E' lo stesso principio gia' in vigore per il
    soffitto (`self._soffitto is None` vuol dire «nessuna persona ha aperto
    questo turno», non «nessuno puo' fare niente»).

    **Nata senza filo** (`subject_key` `None`: prima della fetta «le chat
    divise», o da un attore che non ne porta uno -- l'attuatore) resta
    confermabile da chiunque nomini l'id, come prima di questa fetta.

    **Entrambi presenti**: devono combaciare esattamente, o il rifiuto e' lo
    stesso di un id inesistente (`_UNKNOWN_ID`) -- per non nominare la
    proposta di un altro filo (decisione 4)."""
    if thread is None or proposal.get("subject_key") is None:
        return True
    return _same_thread(proposal, thread)


class Workshop:
    def __init__(self, ha, store, journal, *, read_timezone=None) -> None:
        self._ha = ha
        self._store = store
        self._journal = journal
        self._label_id: str | None = None
        # Una FUNZIONE e non un valore: all'avvio l'archivio della casa puo'
        # non esserci ancora, e il fuso va letto quando serve. Stesso pattern
        # gia' usato per UsageStore (server.py, costruzione di
        # `app["usage"]`).
        self._read_timezone = read_timezone or (lambda: None)

    def _data(self, ts: float) -> str:
        """La data nel fuso della CASA. Senza, l'ora mostrata e' quella del
        container -- tipicamente UTC su un add-on, cioe' sbagliata per chi
        legge. `home_space_zone` ricade su UTC quando il fuso non si sa, e non lo
        inventa mai."""
        import datetime
        return datetime.datetime.fromtimestamp(
            ts, home_space_zone(self._read_timezone())).strftime("%d/%m/%Y %H:%M")

    # ---- proporre -------------------------------------------------------

    async def propose(self, intent: dict, *, actor: str, exchange: str | None,
                      now: float, thread: ChatThread | None = None) -> dict:
        operation = intent.get("gesto")
        domain = intent.get("dominio")
        if operation not in OPERATIONS:
            return {"errore": f"gesto sconosciuto: {operation}. Gesti: {', '.join(OPERATIONS)}."}
        if domain not in self._ha.CONFIGURABLE_DOMAINS:
            return {"errore": (f"non so costruire «{domain}». So costruire: "
                               f"{', '.join(self._ha.CONFIGURABLE_DOMAINS)}.")}
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
            loaded = await self._rete(self._ha.read_configuration(domain, key))
            if loaded.get("assente"):
                # `read_configuration` ha TRE forme (`corpo`, `errore`,
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
        occurrence = self._store.propose(
            operation=operation, domain=domain, key=key, actor=actor,
            exchange=exchange, phrase=intent.get("frase"), prima=prima, dopo=dopo,
            helper=list(intent.get("helper") or []), preview=preview,
            now=now, thread=thread)
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

        Si distingue `assente` da `errore` (vedi `read_configuration`): se
        Home Assistant non risponde **non si dichiara libera** nessuna chiave.
        """
        alias = intent.get("alias") or ""
        occupate: set[str] = set()
        if domain == "script":
            candidata = composer.available_slug(alias, occupate)
        else:
            candidata = composer.new_id(occupate, seme=_seme_da(intent))
        for _ in range(5):
            loaded = await self._rete(self._ha.read_configuration(domain, candidata))
            if loaded.get("assente"):
                return {"chiave": candidata}
            if "errore" in loaded:
                return {"errore": ("non ho potuto verificare se l'identificatore e' "
                                   f"libero: {loaded['errore']}. Non scrivo alla cieca.")}
            occupate.add(candidata)
            if domain == "script":
                candidata = composer.available_slug(alias, occupate)
            else:
                candidata = composer.new_id(occupate, seme=int(candidata) + 1)
        return {"errore": "non sono riuscito a trovare un identificatore libero."}

    def _compose(self, intent: dict, key: str | None) -> dict:
        domain = intent["dominio"]
        alias = intent.get("alias") or ""
        descrizione = intent.get("descrizione") or ""
        if not alias:
            return {"errore": "serve un nome per l'oggetto da costruire."}
        if domain == "automation":
            ident = key or composer.new_id(set(), seme=_seme_da(intent))
            return {"chiave": ident, "corpo": composer.compose_automation(
                id_=ident, alias=alias, descrizione=descrizione,
                innesco=intent.get("innesco") or [],
                conditions=intent.get("condizioni") or [],
                actions=intent.get("azioni") or [])}
        if domain == "script":
            slug = key or composer.available_slug(alias, set())
            return {"chiave": slug, "corpo": composer.compose_script(
                alias=alias, descrizione=descrizione,
                passi=intent.get("azioni") or [],
                fields=intent.get("campi"))}
        # Una scena e' l'unico dominio che a valle NON viene validato da Home
        # Assistant (`parts_to_validate` restituisce {} di proposito): se uno
        # stato e' malformato o ripetuto, QUESTO e' l'ultimo posto in cui
        # qualcuno puo' accorgersene. `compose_scene` scarterebbe in silenzio.
        guai = composer.state_problems(intent.get("stati") or [])
        if guai:
            return {"errore": "non posso comporre la scena -- " + "; ".join(guai)}
        ident = key or composer.new_id(set(), seme=_seme_da(intent))
        return {"chiave": ident, "corpo": composer.compose_scene(
            id_=ident, alias=alias, states=intent.get("stati") or [])}

    async def _validate(self, domain: str, body: dict) -> str | None:
        """`None` se va bene, altrimenti il motivo -- quello di Home Assistant."""
        parts = composer.parts_to_validate(domain, body)
        if not parts:
            return None
        occurrence = await self._ha.validate_config(**parts)
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
        # configurabili e' del client (`HAClient.CONFIGURABLE_DOMAINS`), non
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
                         "che esiste già in casa tua. Conservo com’era.")
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

    async def apply(self, proposal_id: str | None, *, actor: str,
                      exchange: str | None, now: float,
                      subject: dict | None = None,
                      confirm_phrase: str | None = None,
                      thread: ChatThread | None = None) -> dict:
        """`confirm_phrase` e' **la frase su cui l'oggetto e' nato** (B-5).

        Il cancello qui sotto sa dire «in mezzo c'e' stato un turno». Non sa
        dire «in mezzo c'e' stato un si'», e non puo': `confirm` e' uno
        strumento del modello, quindi turno N propone, turno N+1 l'utente
        scrive «grazie» e l'oggetto viene scritto. Il proprietario ha scelto
        di **registrare** invece di vietare: l'autoconferma resta possibile e
        smette di essere invisibile.

        **Non e' la `frase` di una proposta**, che e' la frase che ha CHIESTO
        la costruzione. Questa e' quella che l'ha CONFERMATA: due fatti
        diversi, due parole diverse.

        **`thread` e' del CONFERMANTE, non della proposta** (Task 7, spec
        §5). `None` e' legittimo e NON restringe: e' cosi' che chiamano
        `handlers_constructions.py` (un clic sulla pagina vede tutto) e il
        ripristino interno (`restore`, sotto, quando lo chiama la pagina) --
        nessuno dei due porta un filo di chat da confrontare. Solo il ramo
        che passa da `home_space/tools.py::ToolDispatcher._confirm` porta un
        `thread` vero, ed e' li' che la restrizione morde.
        """
        if not proposal_id:
            proposal_id, reason = self._only_pending(exchange, thread)
            if proposal_id is None:
                return {"errore": reason}
        proposal = self._store.read(proposal_id)
        if proposal is None or not _thread_may_confirm(proposal, thread):
            # **Stesso testo per «non esiste» e «e' di un altro filo»**
            # (decisione 4, spec §5): un rifiuto non deve far capire che una
            # proposta con quell'id esiste, solo altrove -- vedi `_UNKNOWN_ID`.
            return {"errore": _UNKNOWN_ID}
        if proposal["stato"] != "in_attesa":
            return {"errore": f"quella proposta e' gia' {_readable_state(proposal['stato'])}."}
        cancello = self._cancello(proposal, actor, exchange)
        if cancello is not None:
            return {"errore": cancello}
        subject = _add_phrase(subject, confirm_phrase)

        # Rivendicazione atomica (spec §7): il controllo sullo stato appena
        # letto qui sopra non basta -- e' una lettura che una richiesta
        # concorrente (doppio clic sulla pagina, o pagina e chat insieme) puo'
        # gia' aver superato prima che questa arrivi a scrivere. La UPDATE
        # atomica `WHERE stato='in_attesa'` di `ConstructionStore.claim`
        # e' l'unico punto in cui chi arriva prima puo' davvero vincere.
        claimed = self._store.claim(proposal_id, now=now)
        if "errore" in claimed:
            return {"errore": "quella proposta e' gia' stata presa in carico da "
                              "un’altra richiesta."}

        domain, key, operation = proposal["dominio"], proposal["chiave"], proposal["gesto"]
        nati: list[tuple[str, str]] = []
        senza_id: list[str] = []
        for helper in proposal["helper"]:
            occurrence = await self._ha.create_helper(helper.get("dominio"),
                                               helper.get("dati") or {})
            if "errore" in occurrence:
                note = await self._disfa(nati, senza_id)
                return self._fallita(proposal, now, actor,
                                     f"non sono riuscito a creare l’helper: "
                                     f"{occurrence['errore']}{note}", subject=subject)
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
            written = await self._rete(self._ha.delete_configuration(domain, key))
            riuscito = "cancellato" in written
        else:
            written = await self._rete(
                self._ha.save_configuration(domain, key, proposal["dopo"]))
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
                                 guasto_rete=guasto_rete, subject=subject)

        entity, notice = await self._reread(domain, key, operation)
        if operation == "crea":
            # L'etichetta dice CHI L'HA FATTO, e su una modifica non l'ha fatto
            # HIRIS (spec §5). Un oggetto scritto dal proprietario resta suo
            # anche dopo che HIRIS ci ha messo le mani: che ce le abbia messe
            # e' un fatto DIVERSO, e vive dove lo si puo' interrogare -- la
            # cronaca, l'archivio delle versioni, la pagina.
            for entity_id in entity:
                await self._label(entity_id)
        # Gli helper sono SEMPRE nati -- `create_helper` non e' altro --
        # indipendentemente dal gesto sul dominio principale: una
        # `modifica` puo' portarsi dietro un helper nuovo tanto quanto un
        # `create`. Spec §5, testuale: l'etichetta si applica «all'entita'
        # nata, helper compresi». Senza questa riga `_reread` (sopra)
        # filtra per `{dominio}.`, quindi un `input_boolean` nato da HIRIS
        # non riceveva mai l'etichetta -- e poiche' la paternita' vive nel
        # registro di Home Assistant e non in una tabella nostra (fondamenta
        # 2, spec §5), quella paternita' non esisteva da NESSUNA parte
        # (fondamenta 4: un dato che nessuno puo' chiedere non esiste).
        #
        # E l'`entity_id` su cui va si LEGGE, non si compone da
        # `{dominio}.{id di archivio}`: sono due spazi di identificatori con
        # due insiemi di collisioni, e il perche' per esteso -- con le fonti
        # di Home Assistant al tag -- sta in `_helper_entities`.
        labelable, unmatched = await self._helper_entities(nati)
        for entity_id in labelable:
            await self._label(entity_id)
        if unmatched:
            # Si DICE, come si dice l’helper rimasto indietro in `_disfa`: la
            # paternita' di quell'oggetto non esiste da nessuna parte, e un
            # silenzio qui e' la stessa spazzatura invisibile.
            lost = ", ".join(unmatched)
            unlabelled = ("non ho trovato nel registro di Home Assistant "
                          f"l’entita' nata da {lost}: quell’oggetto non porta "
                          "l’etichetta HIRIS, e da qui non risulta mio.")
            notice = f"{notice} {unlabelled}" if notice else unlabelled

        execution_id = self._journal.log_construction(
            actor=actor, operation=operation, domain=domain, key=key,
            entity=entity, executed=True, now=now, notice=notice, subject=subject)
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

    def _only_pending(self, exchange: str | None,
                      thread: ChatThread | None) -> tuple[str | None, str]:
        """Quale proposta l'utente sta confermando, quando non l'ha nominata.

        **Il difetto che chiude** (23/09/2026, misurato sulla casa vera): il
        `proposta_id` nasce in un risultato di strumento, la cronologia della
        chat porta solo testo, e nessuno strumento elenca le pendenti --
        quindi al turno dopo l'id non esiste piu' da nessuna parte e il
        modello riproponeva, bruciando un terzo turno a ogni costruzione.

        **Solo il filo di chi conferma** (Task 7, spec §5), quando `thread`
        c'e'. Le righe di un ALTRO filo, o senza filo (`subject_key IS
        NULL`: prima della fetta, o un attore che non ne porta uno), non
        entrano MAI in questa scelta -- `_same_thread` le esclude. Restano
        confermabili, quelle senza filo, ma solo NOMINANDOLE per id
        (`_thread_may_confirm`, sopra `apply`): qui la domanda e' un'altra,
        «quale delle TUE proposte», e il rifiuto non deve mai far sapere che
        ne esistono di un altro filo (decisione 4).

        **`thread=None` non restringe**, stessa regola di `_thread_may_confirm`
        qui sopra: e' il valore dei chiamanti interni (mai di una chat vera,
        che il suo filo lo calcola sempre -- vedi `create_tool_dispatcher`),
        e per loro la scelta implicita resta quella di sempre, sulla casa
        intera.

        **Solo `in_attesa`**, non `pending_only`: una proposta `in_corso` la
        sta applicando qualcun altro adesso, e sceglierla vorrebbe dire due
        `apply` in corsa sulla stessa riga.

        **Solo gli altri turni.** La guardia del consenso non si aggira per la
        porta di servizio: una proposta nata in QUESTO turno non deve
        diventare confermabile solo perche' l'utente non l'ha nominata. E il
        rifiuto dice la cosa vera -- «te l'ho appena mostrata» invece di «non
        hai niente in sospeso», che sarebbe falso e rimanderebbe il modello a
        riproporla ancora.

        **Con piu' d'una, il rifiuto E' l'elenco.** Sceglierne una a caso
        applicherebbe una cosa che nessuno ha chiesto; rifiutare senza
        nominarle lascerebbe il modello nello stesso vicolo cieco di prima.
        Cosi' invece l'elenco costa zero quando non serve e arriva esatto
        quando serve -- e un elenco che vive in un rifiuto non e' una
        diciassettesima definizione di strumento pagata a ogni turno.

        **Le orfane non fanno riproporre (fix round 1, Task 7).** Quando la
        scelta di QUESTO filo e' vuota ma esistono proposte `in_attesa`
        SENZA filo altrove -- il caso normale di chi usa HIRIS appena
        aggiornato, o di una proposta dell'attuatore -- dire «dimmi cosa
        vuoi e te la propongo» e' il difetto del 23/09/2026 che tornerebbe
        indietro: il modello riproporrebbe una cosa che esiste gia',
        bruciando un posto sotto il tetto per un doppione. Il rifiuto
        rimanda alla pagina, senza nominarle (`_ORPHANS_ELSEWHERE`).
        """
        all_pending = [r for r in self._store.list(pending_only=True)
                      if r["stato"] == "in_attesa"]
        pending = [r for r in all_pending
                  if thread is None or _same_thread(r, thread)]
        confirmable = [r for r in pending if r["turno"] != exchange]
        if len(confirmable) == 1:
            return confirmable[0]["id"], ""
        if not confirmable:
            if pending:
                return None, _BORN_THIS_TURN
            if thread is not None and any(
                    r.get("subject_key") is None for r in all_pending):
                return None, _ORPHANS_ELSEWHERE
            return None, ("non hai nessuna proposta in sospeso da confermare: "
                          "dimmi cosa vuoi e te la propongo.")
        lines = "\n".join(
            f"- {r['id']}: {r['gesto']} {r['dominio']} «{r['chiave']}»"
            for r in confirmable)
        return None, ("ci sono piu' proposte in sospeso e non so quale "
                      f"intendi. Dimmi l'identificatore:\n{lines}")

    def _cancello(self, proposal: dict, actor: str, exchange: str | None) -> str | None:
        """Il sì dell'umano, reso una guardia deterministica (spec §7).

        Il modello propone e il codice restringe: se `apply` fosse solo
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
            return _BORN_THIS_TURN
        return None

    async def _rete(self, call) -> dict:
        """Esegue una chiamata alle primitive REST di `HAClient`, catturando i
        guasti di TRASPORTO (ondata finale, punto 1).

        `read_configuration`, `save_configuration` e
        `delete_configuration` sollevano quello che rompe il trasporto --
        e' scritto nel loro docstring (`proxy/ha_client.py`), e resta cosi':
        la guardia vive qui, all'unico chiamante, non li'. Senza di lei, un
        Home Assistant irraggiungibile durante un'`apply` salterebbe
        `_disfa` (spazzatura in casa dell'utente, spec §3.1), lascerebbe la
        riga bloccata `in_corso` fino al riavvio, e farebbe uscire un 500
        grezzo dalla pagina invece del contratto 404/409/503 dichiarato da
        `handlers_constructions.py`.

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
            # `home_space/tools.py` nella sua rete finale.
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
        `delete_helper` fallisce a sua volta, o un helper non e' mai entrato
        fra i disfabili (nessun `id` restituito alla creazione), tacerlo
        lascerebbe l'archivio dire «non e' successo niente» mentre in casa
        resta un orfano che nessuno pulira' piu'. Restituisce il pezzo di
        frase da appendere al motivo del rifiuto, o `""` se non c'e' niente
        da dire.
        """
        disfatti: list[str] = []
        rimasti: list[str] = []
        for domain, helper_id in reversed(nati):
            occurrence = await self._ha.delete_helper(domain, helper_id)
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
            pezzi.append("l’helper " + ", ".join(rimasti) +
                         " e' rimasto in casa tua, toglilo a mano")
        for domain in senza_id or []:
            pezzi.append(f"un helper {domain} e' stato creato ma senza un id "
                         "restituito: non posso disfarlo automaticamente, "
                         "controllalo a mano")
        return (" " + "; ".join(pezzi) + ".") if pezzi else ""

    def _fallita(self, proposal: dict, now: float, actor: str, reason: str, *,
                guasto_rete: bool = False, subject: dict | None = None) -> dict:
        execution_id = self._journal.log_construction(
            actor=actor, operation=proposal["gesto"], domain=proposal["dominio"],
            key=proposal["chiave"], entity=[], executed=False, now=now,
            error=reason, subject=subject)
        occurrence_state = self._store.mark_rejected(proposal["id"], now=now,
                                                      reason=reason)
        if "errore" in occurrence_state:
            logger.warning("mark_rejected non riuscita per %s: %s", proposal["id"],
                           occurrence_state["errore"])
        occurrence = {"errore": reason, "esecuzione_id": execution_id}
        if guasto_rete:
            # Distingue un guasto di TRASPORTO da un rifiuto vero di Home
            # Assistant (validazione, 400): `_act` (handlers_constructions.py)
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
            return [], ("Home Assistant ha accettato la scrittura ma l’entita' non e' "
                        "ancora comparsa: potrebbe servire un riavvio, o la ricarica "
                        "non e' andata a buon fine.")
        return trovate, None

    async def _helper_entities(self, born: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
        """L’`entity_id` VERO di ogni helper appena nato, LETTO dal registro
        delle entita'. Restituisce `(trovati, non trovati)`.

        **Perche' non si compone.** Fino all' 09/09/2026 qui c'era
        `f"{dominio}.{id_di_archivio}"`, e sono due spazi di identificatori
        diversi che coincidono per fortuna, non per costruzione. Fonti lette
        al tag `2026.9.1`:

        - `helpers/collection.py::IDManager.generate_id` -- l'id di ARCHIVIO
          e' `slugify(nome)` con un suffisso `_2` deciso guardando le
          collezioni di quel dominio (YAML e storage insieme: si spartiscono
          un `IDManager`);
        - `input_boolean/__init__.py::from_storage` -- non imposta nessun
          `entity_id`, a differenza di `from_yaml`;
        - `helpers/entity_registry.py` -- l'`entity_id` lo genera il registro
          come `dominio.slugify(nome)`, con un suffisso deciso guardando il
          REGISTRO e la macchina degli stati.

        Due basi uguali, due insiemi di collisione diversi. Basta un
        `entity_id` rinominato a mano dall'utente perche' divergano: l'id di
        archivio `vacanza` resta occupato, l'`input_boolean.vacanza` no, e
        l'helper successivo nasce con id `vacanza_2` ed entita'
        `input_boolean.vacanza`. L'etichetta sarebbe finita su un'entita'
        inesistente -- o, peggio, su quella di qualcun altro.

        **Come si legge.** Dal registro delle entita', per `platform` e
        `unique_id`: per tutti e otto i domini di `HAClient.HELPER_DOMAINS`
        `collection.sync_entity_lifecycle(hass, DOMAIN, DOMAIN, ...)` passa il
        dominio come piattaforma, e l'entita' prende come `unique_id` l'id
        della collezione (`config[CONF_ID]`) -- verificato al tag su tutti e
        otto. Misurato dal vivo il 09/09/2026 sulla casa del proprietario
        (sola lettura, `config/entity_registry/list`): 11 voci di helper, ognuna
        con `platform` e `unique_id`, e `entity_id == platform.unique_id` su
        tutte -- la coincidenza che l'audit chiama fortuna.

        Si passa da `read_registries`, che e' la porta unica dei registri:
        `get_entity_registry` era gia' uscita una volta perche' emetteva lo
        stesso comando WS che quella manda gia' (review dei doppioni, 17/08).
        Rifarne una seconda per un helper sarebbe la stessa fondamenta 2
        violata due volte.
        """
        if not born:
            return [], []
        composti = [f"{domain}.{helper_id}" for domain, helper_id in born]
        try:
            registries, unavailable = await self._ha.read_registries()
        except Exception as exc:
            logger.warning("registro delle entita' non letto dopo la nascita di %s "
                           "(%s: %s): nessuna etichetta applicata",
                           composti, type(exc).__name__, exc)
            return [], composti
        if "entita" in (unavailable or []):
            logger.warning("registro delle entita' non disponibile dopo la nascita "
                           "di %s: nessuna etichetta applicata", composti)
            return [], composti
        per_unico: dict[tuple[str, str], str] = {}
        for row in registries.get("entita") or []:
            platform, unique = row.get("platform"), row.get("unique_id")
            entity_id = row.get("entity_id")
            if platform and unique is not None and entity_id:
                per_unico[(platform, str(unique))] = entity_id
        found: list[str] = []
        missing: list[str] = []
        for domain, helper_id in born:
            entity_id = per_unico.get((domain, str(helper_id)))
            if entity_id:
                found.append(entity_id)
            else:
                # Non si ripiega sul composto: sarebbe rimettere in piedi
                # l'ipotesi che questa funzione esiste per togliere.
                logger.warning("helper %s.%s creato ma senza voce nel registro "
                               "delle entita': etichetta non applicata",
                               domain, helper_id)
                missing.append(f"{domain}.{helper_id}")
        return found, missing

    async def _label(self, entity_id: str) -> None:
        if self._label_id is None and not await self._resolve_label():
            return
        occurrence = await self._ha.add_label_to(entity_id, self._label_id)
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
        occurrence = await self._ha.add_label_to(entity_id, self._label_id)
        if "errore" in occurrence:
            logger.warning("etichetta non applicata a %s nemmeno al secondo tentativo: %s",
                           entity_id, occurrence["errore"])

    async def _resolve_label(self) -> bool:
        """Trova o crea il `label_id` di HIRIS in Home Assistant, aggiornando
        la cache dell'istanza. Restituisce True se una `label_id` valida e'
        nota dopo la chiamata."""
        response = await self._ha.list_labels()
        if "errore" in response:
            logger.debug("etichette non lette: %s", response["errore"])
            return False
        for entry in response["etichette"]:
            if (entry.get("name") or "").strip().lower() == LABEL_NAME.lower():
                self._label_id = entry.get("label_id")
                break
        if self._label_id is None:
            creata = await self._ha.create_label(LABEL_NAME)
            if "errore" in creata:
                logger.debug("etichetta non creata: %s", creata["errore"])
                return False
            self._label_id = (creata.get("etichetta") or {}).get("label_id")
        return self._label_id is not None

    # ---- ripristinare ---------------------------------------------------

    async def restore(self, construction_id: str, *, actor: str,
                         exchange: str | None, now: float, subject: dict | None = None) -> dict:
        """Rimettere il «prima» e' un'ALTRA costruzione, e passa di qui.

        Non e' una scorciatoia che scrive diretta: valida come tutte le altre,
        e se nel frattempo quel corpo non e' piu' valido lo dice invece di
        scriverlo (spec §6).
        """
        row = self._store.read(construction_id)
        if row is None:
            return {"errore": "non ho nessuna costruzione con quell’identificatore."}
        if row["stato"] != "applicata":
            return {"errore": "quella costruzione non e' mai stata applicata: "
                              "non c’e' niente da rimettere."}
        prima = row["prima"]
        domain, key = row["dominio"], row["chiave"]
        if prima is None:
            # Ripristinare una CREAZIONE significa cancellare cio' che e' nato.
            intent_operation, dopo = "cancella", None
        else:
            intent_operation, dopo = "modifica", prima
            reason = await self._validate(domain, dopo)
            if reason is not None:
                return {"errore": f"non posso rimettere com’era: {reason}"}
        preview = (f"Rimetto l’oggetto {domain}.{key} com’era prima "
                     f"del {self._data(row['creata_ts'])}.")
        proposal = self._store.propose(
            operation=intent_operation, domain=domain, key=key, actor=actor,
            exchange=exchange, phrase=f"ripristino di {construction_id}", prima=row["dopo"],
            dopo=dopo, helper=[], preview=preview, now=now)
        if "errore" in proposal:
            return proposal
        if actor in HUMAN_ACTORS:
            # **`subject` va inoltrato**, e per una fetta non lo e' stato: il
            # parametro arrivava fin qui e si fermava, quindi ogni ripristino
            # scriveva in cronaca una riga senza soggetto -- mentre la nota di
            # chiusura di A-1 dichiarava che il filo arriva «fino all'atto:
            # `execute`, `apply`, `restore`». Misurato il 23/09/2026 su un
            # ripristino vero, guardando la riga che ne era uscita: nessuna
            # prova lo vedeva, perche' provavano il `Journal` da solo.
            #
            # Disfare e' l'atto su cui «chi e' stato?» pesa di piu': toglie
            # qualcosa che c'era.
            return await self.apply(proposal["id"], actor=actor, exchange=exchange,
                                      now=now, subject=subject)
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
            # restituita deve dirlo -- lo stesso messaggio che `apply` da'
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
    truthy, arriva intatto a `HAClient._KEY_RE.match(chiave or "")` (l'`or`
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
    # **`richiesto` e' un vocabolario CHIUSO, non una frase** (audit delle
    # fondamenta, rilievo 5). Risponde a «quale delle tre strutture ti ha
    # chiesto», e «cosa ha detto la persona» ha gia' un campo suo, `frase`.
    # Finche' i due fatti sono stati una parola sola, il modello ci ha scritto
    # dentro la richiesta dell'utente -- misurato sulla casa vera, costruzione
    # applicata `automation.1784125482111029` -- e il consigliere e' finito a
    # dissentire da se stesso in un'anteprima che il proprietario ha
    # approvato.
    #
    # Si RIFIUTA, non si normalizza: il motivo dice al modello dove va quel
    # testo, e lui corregge. Una normalizzazione piu' furba sposterebbe il
    # buco invece di chiuderlo -- la frase misurata contiene la parola
    # «automazione» e non e' una richiesta di struttura.
    requested = intent.get("richiesto")
    if requested is not None and requested != "" and requested not in STRUCTURES:
        return (f"«richiesto» accetta solo {', '.join(STRUCTURES)}: dice quale "
                f"delle tre strutture ti ha chiesto l'utente, non cosa ti ha "
                f"detto. La sua frase va in «frase».")
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
    verifica di unicita' VERA la fa `composer.new_id` contro gli id esistenti
    in QUESTA casa, e Home Assistant rifiuterebbe comunque un duplicato.
    """
    base = 1_700_000_000_000
    return base + abs(hash((intent.get("alias"), intent.get("frase")))) % 100_000_000


#: Fin dove si scende dentro un corpo che si annida. Il corpo puo' arrivare dal
#: modello: senza un limite, uno annidato all'infinito bloccherebbe l'anteprima
#: invece di produrla -- cioe' impedirebbe di proporre invece di impedire di
#: sbagliare. Cinquanta livelli sono molti piu' di quanti ne abbia una
#: automazione vera (un `choose` dentro un `repeat` dentro un `choose` ne fa
#: sei) e molti meno di quanti ne servano a fare danno.
_MAX_DEPTH = 50


def services_named(body: dict | None) -> list[str]:
    """I servizi che questo corpo CHIAMA, nell'ordine in cui compaiono.

    **Il reperto B-4**: l'anteprima diceva `alias · triggers: 1 · actions: 2`,
    cioe' conteggi, e in nessun punto dell'interfaccia il proprietario vedeva
    le azioni che stava approvando. Uno `shell_command` dentro il corpo passa
    `validate_config` -- e' valido -- e crea un oggetto permanente che chiama
    un servizio che `execute` non avrebbe potuto chiamare.

    Non e' una restrizione: il si' c'era gia', era **disinformato**.

    **`action` e' due cose, e si distinguono per il TIPO.** Home Assistant usa
    quella parola per il nome del servizio dentro un passo (dal 2024.8, dove
    prima c'era `service:`) e -- prima di `actions:` -- per la lista dei passi.
    Una stringa col punto e' un servizio, una lista e' un elenco: la posizione
    cambia da una versione all'altra di HA, il tipo no.

    Si **deduplica** (un'automazione che accende dieci luci chiama dieci volte
    lo stesso servizio, e dirlo dieci volte renderebbe illeggibile la riga che
    deve farsi leggere) e si tiene **l'ordine del corpo**: si legge nell'ordine
    in cui le cose succedono.
    """
    found: list[str] = []

    def walk(node, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if (key in ("service", "action")
                        and isinstance(value, str) and "." in value):
                    if value not in found:
                        found.append(value)
                    continue
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(body or {}, 0)
    return found


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
    # **Cosa chiamera'** (reperto B-4, 22/09/2026). I conteggi restano: non
    # erano sbagliati, erano insufficienti -- dicono la dimensione della
    # modifica, che e' un fatto utile accanto ai nomi.
    #
    # Se non chiama niente -- una scena -- non si scrive l'etichetta: «Chiama:»
    # seguito da niente sarebbe rumore che insegna a saltare la riga.
    called = services_named(body)
    if called:
        pezzi.append("chiama: " + ", ".join(called))
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
    plural = {"automation": "automazioni", "script": "script",
               "scene": "scene"}.get(domain, domain)
    if "404" in error or "not found" in error.lower():
        return (f"queste {plural} sono gestite a mano (o vivono in `packages/`): "
                "l’API di configurazione di Home Assistant non le governa, e non posso "
                "scriverle. Posso mostrarti il pezzo corretto da incollare.")
    return error
