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

from . import forme
from .mestiere import consiglia

logger = logging.getLogger(__name__)

# L'etichetta con cui Home Assistant tiene la paternita' di cio' che HIRIS
# costruisce (spec §5). Vive nel registro di HA e non in una tabella nostra:
# e' un fatto che lui sa gia' tenere.
NOME_ETICHETTA = "HIRIS"

# Le origini che sono, per costruzione, un essere umano che ha appena
# cliccato. Per loro la guardia del turno non si applica -- non c'e' nessun
# modello da trattenere.
ORIGINI_UMANE = ("pagina",)

_GESTI = ("crea", "modifica", "cancella")

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
_STATO_LEGGIBILE = {
    "applicata": "applicata",
    "rifiutata": "rifiutata",
    "scaduta": "scaduta",
    "in_corso": "in corso",
}


def _stato_leggibile(stato: str) -> str:
    return _STATO_LEGGIBILE.get(stato, stato)


# Punto 4 (residuo): il messaggio grezzo di `_rete` (sotto) finisce in quattro
# superfici, due permanenti -- `costruzioni.motivo`/`errore` nella cronaca in
# SQLite -- e la cattura larga toglie ogni garanzia sulla sua lunghezza: e'
# quella di QUALUNQUE eccezione, non solo di un guasto di trasporto breve.
# Rispecchia `_truncate`/`_TRUNC_MARK` di `proxy/ha_client.py` (la stessa
# convenzione, introdotta li' per "il messaggio d'errore di HA, che puo'
# includere un traceback intero"): e' privata di quel modulo, quindi si
# duplica la FORMA qui, non si promuove l'helper.
_TRUNC_MARK_RETE = " [troncato]"
_CAP_ERRORE_RETE = 300


def _tronca_errore_rete(testo: str) -> str:
    """Tronca `testo` a `_CAP_ERRORE_RETE` caratteri, marcatore incluso."""
    if len(testo) <= _CAP_ERRORE_RETE:
        return testo
    if _CAP_ERRORE_RETE <= len(_TRUNC_MARK_RETE):
        return testo[:max(0, _CAP_ERRORE_RETE)]
    return testo[:_CAP_ERRORE_RETE - len(_TRUNC_MARK_RETE)] + _TRUNC_MARK_RETE


class Officina:
    def __init__(self, ha, archivio, cronaca) -> None:
        self._ha = ha
        self._archivio = archivio
        self._cronaca = cronaca
        self._label_id: str | None = None

    # ---- proporre -------------------------------------------------------

    async def proponi(self, intento: dict, *, origine: str, turno: str | None,
                      adesso: float) -> dict:
        gesto = intento.get("gesto")
        dominio = intento.get("dominio")
        if gesto not in _GESTI:
            return {"errore": f"gesto sconosciuto: {gesto}. Gesti: {', '.join(_GESTI)}."}
        if dominio not in self._ha.DOMINI_CONFIGURABILI:
            return {"errore": (f"non so costruire «{dominio}». So costruire: "
                               f"{', '.join(self._ha.DOMINI_CONFIGURABILI)}.")}
        motivo_forma = _forma_invalida(intento)
        if motivo_forma is not None:
            return {"errore": motivo_forma}

        consiglio = consiglia({
            "richiesto": intento.get("richiesto"),
            "innesco": intento.get("innesco"),
            "passi": intento.get("azioni"),
            "stati": intento.get("stati"),
            "parametri": intento.get("parametri"),
            "riuso": intento.get("riuso"),
            "ricorrente": intento.get("ricorrente"),
        })
        if gesto in ("crea", "modifica") and not consiglio["strutture"]:
            # L'unico caso in cui il mestiere non ha niente da dire e' proprio
            # quello in cui tace (`consiglia` torna col ritorno anticipato,
            # `dissenso: False`). Senza questo controllo il corpo composto
            # sotto avrebbe tre liste vuote, Home Assistant lo direbbe
            # «valido», e una conferma scriverebbe in casa un'automazione
            # inerte. Per `cancella` non si compone niente: il controllo non
            # si applica.
            return {"errore": consiglio["motivo"] or "non ho capito cosa costruire."}

        prima = None
        chiave = intento.get("chiave")
        if gesto in ("modifica", "cancella"):
            if not chiave:
                return {"errore": f"per {gesto} serve la chiave dell'oggetto da toccare."}
            letto = await self._rete(self._ha.leggi_configurazione(dominio, chiave))
            if letto.get("assente"):
                # `leggi_configurazione` ha TRE forme (`corpo`, `errore`,
                # `assente`), non due: indicizzare `letto["corpo"]` su questo
                # ramo solleverebbe `KeyError` fuori dal modulo, raggiungibile
                # con argomenti perfettamente validi -- il modello propone una
                # modifica a un'automazione che l'utente ha cancellato nel
                # frattempo.
                return {"errore": f"non trovo piu' {dominio}.{chiave} in casa tua: "
                                  "forse e' stato cancellato nel frattempo."}
            if "errore" in letto:
                return {"errore": f"non ho potuto leggere com'e' adesso: {letto['errore']}"}
            prima = letto["corpo"]

        if gesto == "cancella":
            dopo = None
        else:
            if gesto == "crea":
                libera = await self._chiave_libera(dominio, intento)
                if "errore" in libera:
                    return libera
                chiave = libera["chiave"]
            composto = self._componi(intento, chiave)
            if "errore" in composto:
                return composto
            dopo, chiave = composto["corpo"], composto["chiave"]
            prova = await self._valida(dominio, dopo)
            if prova is not None:
                return {"errore": prova}

        anteprima = self._anteprima(gesto, dominio, chiave, intento, prima, dopo,
                                    consiglio)
        esito = self._archivio.proponi(
            gesto=gesto, dominio=dominio, chiave=chiave, origine=origine,
            turno=turno, frase=intento.get("frase"), prima=prima, dopo=dopo,
            helper=list(intento.get("helper") or []), anteprima=anteprima,
            adesso=adesso)
        if "errore" in esito:
            return esito
        return {"proposta_id": esito["id"], "anteprima": anteprima,
                "consiglio": consiglio}

    async def _chiave_libera(self, dominio: str, intento: dict) -> dict:
        """Una chiave che in questa casa non e' gia' occupata.

        **Un id gia' in uso non darebbe un errore: farebbe SOSTITUIRE la voce
        che c'era**, perche' `_write_value` di Home Assistant trova per `id` e
        rimpiazza. E' la stessa famiglia del danno misurato su
        `automations.yaml`, vista dall'altro lato, e l'unica difesa e' chiedere
        prima.

        Si distingue `assente` da `errore` (vedi `leggi_configurazione`): se
        Home Assistant non risponde **non si dichiara libera** nessuna chiave.
        """
        alias = intento.get("alias") or ""
        occupate: set[str] = set()
        if dominio == "script":
            candidata = forme.slug_libero(alias, occupate)
        else:
            candidata = forme.nuovo_id(occupate, seme=_seme_da(intento))
        for _ in range(5):
            letto = await self._rete(self._ha.leggi_configurazione(dominio, candidata))
            if letto.get("assente"):
                return {"chiave": candidata}
            if "errore" in letto:
                return {"errore": ("non ho potuto verificare se l'identificatore e' "
                                   f"libero: {letto['errore']}. Non scrivo alla cieca.")}
            occupate.add(candidata)
            if dominio == "script":
                candidata = forme.slug_libero(alias, occupate)
            else:
                candidata = forme.nuovo_id(occupate, seme=int(candidata) + 1)
        return {"errore": "non sono riuscito a trovare un identificatore libero."}

    def _componi(self, intento: dict, chiave: str | None) -> dict:
        dominio = intento["dominio"]
        alias = intento.get("alias") or ""
        descrizione = intento.get("descrizione") or ""
        if not alias:
            return {"errore": "serve un nome per l'oggetto da costruire."}
        if dominio == "automation":
            ident = chiave or forme.nuovo_id(set(), seme=_seme_da(intento))
            return {"chiave": ident, "corpo": forme.componi_automazione(
                id_=ident, alias=alias, descrizione=descrizione,
                innesco=intento.get("innesco") or [],
                condizioni=intento.get("condizioni") or [],
                azioni=intento.get("azioni") or [])}
        if dominio == "script":
            slug = chiave or forme.slug_libero(alias, set())
            return {"chiave": slug, "corpo": forme.componi_script(
                alias=alias, descrizione=descrizione,
                passi=intento.get("azioni") or [],
                campi=intento.get("campi"))}
        # Una scena e' l'unico dominio che a valle NON viene validato da Home
        # Assistant (`parti_da_validare` restituisce {} di proposito): se uno
        # stato e' malformato o ripetuto, QUESTO e' l'ultimo posto in cui
        # qualcuno puo' accorgersene. `componi_scena` scarterebbe in silenzio.
        guai = forme.problemi_stati(intento.get("stati") or [])
        if guai:
            return {"errore": "non posso comporre la scena -- " + "; ".join(guai)}
        ident = chiave or forme.nuovo_id(set(), seme=_seme_da(intento))
        return {"chiave": ident, "corpo": forme.componi_scena(
            id_=ident, alias=alias, stati=intento.get("stati") or [])}

    async def _valida(self, dominio: str, corpo: dict) -> str | None:
        """`None` se va bene, altrimenti il motivo -- quello di Home Assistant."""
        parti = forme.parti_da_validare(dominio, corpo)
        if not parti:
            return None
        esito = await self._ha.valida_config(**parti)
        if "errore" in esito:
            return f"non ho potuto far validare la configurazione: {esito['errore']}"
        guasti = [f"{chiave}: {voce.get('error')}"
                  for chiave, voce in esito.items()
                  if isinstance(voce, dict) and not voce.get("valid")]
        if guasti:
            return "Home Assistant rifiuta questa configurazione -- " + "; ".join(guasti)
        return None

    def _anteprima(self, gesto, dominio, chiave, intento, prima, dopo,
                   consiglio) -> str:
        # `.get(dominio, dominio)`, non un indice nudo: l'elenco dei domini
        # configurabili e' del client (`HAClient.DOMINI_CONFIGURABILI`), non
        # di queste tabelle locali (ARTICOLO_INDETERMINATIVO/DETERMINATIVO,
        # sopra) -- un quarto dominio aggiunto la' solleverebbe `KeyError` qui.
        righe = []
        if gesto == "crea":
            # Punto 5 (residuo): la correzione dell'articolo (ondata finale,
            # punto 7) non toccava il participio -- «chiamata» concorda solo
            # con automazione e scena, e «uno script chiamata «X»» restava
            # sgrammaticato. «di nome» e' invariabile: non serve una terza
            # tabella di concordanze.
            righe.append(f"Creo {ARTICOLO_INDETERMINATIVO.get(dominio, dominio)} "
                         f"di nome «{intento.get('alias')}».")
        elif gesto == "modifica":
            righe.append(f"Modifico {ARTICOLO_DETERMINATIVO.get(dominio, dominio)} "
                         f"«{(prima or {}).get('alias') or chiave}», "
                         "che esiste già in casa tua.")
            righe.append(f"Prima: {_compatta(prima)}")
            righe.append(f"Dopo: {_compatta(dopo)}")
        else:
            righe.append(f"Cancello {ARTICOLO_DETERMINATIVO.get(dominio, dominio)} "
                         f"«{(prima or {}).get('alias') or chiave}», "
                         "che esiste già in casa tua. Conservo com'era.")
        if intento.get("descrizione"):
            righe.append(f"A cosa serve: {intento['descrizione']}")
        for helper in intento.get("helper") or []:
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

    async def applica(self, proposta_id: str, *, origine: str, turno: str | None,
                      adesso: float) -> dict:
        proposta = self._archivio.leggi(proposta_id)
        if proposta is None:
            return {"errore": "non ho nessuna proposta con quell'identificatore."}
        if proposta["stato"] != "in_attesa":
            return {"errore": f"quella proposta e' gia' {_stato_leggibile(proposta['stato'])}."}
        cancello = self._cancello(proposta, origine, turno)
        if cancello is not None:
            return {"errore": cancello}

        # Rivendicazione atomica (spec §7): il controllo sullo stato appena
        # letto qui sopra non basta -- e' una lettura che una richiesta
        # concorrente (doppio clic sulla pagina, o pagina e chat insieme) puo'
        # gia' aver superato prima che questa arrivi a scrivere. La UPDATE
        # atomica `WHERE stato='in_attesa'` di `ArchivioCostruzioni.rivendica`
        # e' l'unico punto in cui chi arriva prima puo' davvero vincere.
        rivendicata = self._archivio.rivendica(proposta_id, adesso=adesso)
        if "errore" in rivendicata:
            return {"errore": "quella proposta e' gia' stata presa in carico da "
                              "un'altra richiesta."}

        dominio, chiave, gesto = proposta["dominio"], proposta["chiave"], proposta["gesto"]
        nati: list[tuple[str, str]] = []
        senza_id: list[str] = []
        for helper in proposta["helper"]:
            esito = await self._ha.crea_helper(helper.get("dominio"),
                                               helper.get("dati") or {})
            if "errore" in esito:
                nota = await self._disfa(nati, senza_id)
                return self._fallita(proposta, adesso, origine,
                                     f"non sono riuscito a creare l'helper: "
                                     f"{esito['errore']}{nota}")
            creato = esito.get("helper") or {}
            if creato.get("id"):
                nati.append((helper.get("dominio"), creato["id"]))
            else:
                # Creato, ma senza un id restituito: non entra in `nati` e
                # quindi non e' mai disfabile da questo modulo. Tacerlo
                # sarebbe la stessa spazzatura di un helper mai disfatto, in
                # una forma piu' subdola -- l'utente non saprebbe nemmeno che
                # c'e' qualcosa da controllare (spec §3.1).
                senza_id.append(str(helper.get("dominio")))

        if gesto == "cancella":
            scritto = await self._rete(self._ha.cancella_configurazione(dominio, chiave))
            riuscito = "cancellato" in scritto
        else:
            scritto = await self._rete(
                self._ha.salva_configurazione(dominio, chiave, proposta["dopo"]))
            riuscito = "salvato" in scritto

        if not riuscito:
            nota = await self._disfa(nati, senza_id)
            guasto_rete = scritto.get("guasto_rete", False)
            errore_grezzo = scritto.get("errore", "")
            # Punto 2 (residuo): `_traduci_rifiuto` cerca «404» come SOTTOSTRINGA
            # nuda su tutto il messaggio -- un guasto di rete puo' contenere
            # quella cifra per caso (una porta, un IP) e uscirebbe come una
            # spiegazione architetturale falsa («queste automazioni sono
            # gestite a mano...») invece che come cio' che e' davvero: Home
            # Assistant irraggiungibile. Il flag che l'ondata ha introdotto
            # due righe sopra distingue gia' i due casi -- non serve indovinare
            # dal testo.
            motivo = errore_grezzo if guasto_rete else _traduci_rifiuto(
                errore_grezzo, dominio)
            return self._fallita(proposta, adesso, origine, motivo + nota,
                                 guasto_rete=guasto_rete)

        entita, avviso = await self._rileggi(dominio, chiave, gesto)
        if gesto == "crea":
            # L'etichetta dice CHI L'HA FATTO, e su una modifica non l'ha fatto
            # HIRIS (spec §5). Un oggetto scritto dal proprietario resta suo
            # anche dopo che HIRIS ci ha messo le mani: che ce le abbia messe
            # e' un fatto DIVERSO, e vive dove lo si puo' interrogare -- la
            # cronaca, l'archivio delle versioni, la pagina.
            for entity_id in entita:
                await self._etichetta(entity_id)
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
        for dominio_helper, helper_id in nati:
            await self._etichetta(f"{dominio_helper}.{helper_id}")

        esecuzione_id = self._cronaca.registra_costruzione(
            origine=origine, gesto=gesto, dominio=dominio, chiave=chiave,
            entita=entita, eseguito=True, adesso=adesso, avviso=avviso)
        esito_stato = self._archivio.segna_applicata(proposta_id, adesso=adesso,
                                                      esecuzione_id=esecuzione_id)
        if "errore" in esito_stato:
            # Non ignorato: se la riga non e' piu' rivendicabile (un caso che
            # oggi non dovrebbe capitare, essendo appena stata rivendicata da
            # QUESTA chiamata) l'utente ha comunque avuto il suo risultato --
            # Home Assistant ha scritto -- e la traccia serve a chi legge il
            # log, non a cambiare l'esito verso l'utente.
            logger.warning("segna_applicata non riuscita per %s: %s", proposta_id,
                           esito_stato["errore"])
        return {"applicata": True, "esecuzione_id": esecuzione_id,
                "entita": entita, "avviso": avviso}

    def _cancello(self, proposta: dict, origine: str, turno: str | None) -> str | None:
        """Il sì dell'umano, reso una guardia deterministica (spec §7).

        Il modello propone e il codice restringe: se `applica` fosse solo
        un'altra chiamata, il modello potrebbe concatenarla nello stesso turno
        e il sì dell'utente sparirebbe senza che nessuno se ne accorga.
        """
        if origine in ORIGINI_UMANE:
            # Qualunque valore di `origine` uguale a una voce di ORIGINI_UMANE
            # scavalca la guardia: se il Task 8 (o chi verra' dopo) sbagliasse
            # a inoltrare un'origine scelta dal modello come `pagina`, questa
            # riga e' l'unica traccia che ne resterebbe.
            logger.info("cancello scavalcato dall'origine umana %r per la proposta %s",
                       origine, proposta["id"])
            return None
        # Una proposta nata SENZA identita' di turno (il ramo sincrono della
        # chat, un'intestazione mancante -- casi normali) non e' confermabile
        # da un'origine non umana, qualunque turno arrivi dopo. La forma
        # precedente (`proposta["turno"] and proposta["turno"] == turno`)
        # restava FALSA quando il turno memorizzato era `None`, e lasciava
        # passare la prima conferma che capitava: la regola giusta e'
        # l'inversa, e la strada e' la stessa di un chiamante che oggi non
        # porta un turno -- la pagina.
        if not turno or not proposta["turno"]:
            return ("non riesco a distinguere i turni, quindi non posso confermare da qui: "
                    "apri la pagina Costruzioni e conferma di la'.")
        if proposta["turno"] == turno:
            return ("questa proposta e' nata in questo stesso turno: te l'ho mostrata, "
                    "ora dimmi tu se procedere.")
        return None

    async def _rete(self, chiamata) -> dict:
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
            return await chiamata
        except Exception as exc:
            # Punto 3 (residuo): la cattura larga e' la scelta giusta (restringere
            # vorrebbe dire importare aiohttp qui, in un modulo deliberatamente
            # agnostico al trasporto), ma senza tipo ne' traceback un nostro
            # `TypeError` diventa indistinguibile, in log, da un guasto di rete
            # vero -- il difetto nascosto due volte. Stessa forma gia' usata da
            # `casa/strumenti.py` nella sua rete finale.
            logger.warning("chiamata verso Home Assistant non riuscita (%s): %s",
                           type(exc).__name__, exc, exc_info=True)
            return {"errore": f"Home Assistant non ha risposto: {_tronca_errore_rete(str(exc))}",
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
        for dominio, helper_id in reversed(nati):
            esito = await self._ha.cancella_helper(dominio, helper_id)
            if "errore" in esito:
                logger.warning("helper %s.%s creato e NON disfatto: %s",
                               dominio, helper_id, esito["errore"])
                rimasti.append(f"{dominio}.{helper_id}")
            else:
                disfatti.append(f"{dominio}.{helper_id}")
        pezzi: list[str] = []
        if disfatti:
            pezzi.append("ho tolto anche " + ", ".join(disfatti))
        if rimasti:
            pezzi.append("l'helper " + ", ".join(rimasti) +
                         " e' rimasto in casa tua, toglilo a mano")
        for dominio in senza_id or []:
            pezzi.append(f"un helper {dominio} e' stato creato ma senza un id "
                         "restituito: non posso disfarlo automaticamente, "
                         "controllalo a mano")
        return (" " + "; ".join(pezzi) + ".") if pezzi else ""

    def _fallita(self, proposta: dict, adesso: float, origine: str, motivo: str, *,
                guasto_rete: bool = False) -> dict:
        esecuzione_id = self._cronaca.registra_costruzione(
            origine=origine, gesto=proposta["gesto"], dominio=proposta["dominio"],
            chiave=proposta["chiave"], entita=[], eseguito=False, adesso=adesso,
            errore=motivo)
        esito_stato = self._archivio.segna_rifiutata(proposta["id"], adesso=adesso,
                                                      motivo=motivo)
        if "errore" in esito_stato:
            logger.warning("segna_rifiutata non riuscita per %s: %s", proposta["id"],
                           esito_stato["errore"])
        esito = {"errore": motivo, "esecuzione_id": esecuzione_id}
        if guasto_rete:
            # Distingue un guasto di TRASPORTO da un rifiuto vero di Home
            # Assistant (validazione, 400): `_agisci` (handlers_costruzioni.py)
            # legge questo flag per rispondere 503 invece di 409 -- la stessa
            # indisponibilita' che la GET dichiarerebbe (ondata finale, punto
            # 7, terza pulizia).
            esito["guasto_rete"] = True
        return esito

    async def _rileggi(self, dominio: str, chiave: str,
                       gesto: str) -> tuple[list[str], str | None]:
        """Cosa e' comparso davvero. Dire cosa e' successo, non cosa e' stato
        chiesto (spec §2.3)."""
        if gesto == "cancella":
            return [], None
        try:
            stati = await self._ha.get_states([])
        except Exception as exc:
            logger.debug("rilettura dopo la scrittura fallita: %s", exc)
            return [], ("ho scritto, ma non sono riuscito a rileggere lo stato: "
                        "controlla in Home Assistant.")
        trovate = []
        for stato in stati or []:
            eid = stato.get("entity_id") or ""
            if not eid.startswith(f"{dominio}."):
                continue
            attributi = stato.get("attributes") or {}
            if attributi.get("id") == chiave or eid == f"{dominio}.{chiave}":
                trovate.append(eid)
        if not trovate:
            return [], ("Home Assistant ha accettato la scrittura ma l'entita' non e' "
                        "ancora comparsa: potrebbe servire un riavvio, o la ricarica "
                        "non e' andata a buon fine.")
        return trovate, None

    async def _etichetta(self, entity_id: str) -> None:
        if self._label_id is None and not await self._risolvi_etichetta():
            return
        esito = await self._ha.aggiungi_etichetta_a(entity_id, self._label_id)
        if "errore" not in esito:
            return
        # Il `label_id` in cache potrebbe non esistere piu' in Home Assistant
        # (etichetta cancellata a mano dopo la prima risoluzione): restare
        # muti fino al riavvio perderebbe la paternita' di ogni oggetto
        # successivo in silenzio. Si azzera la cache e si ritenta UNA volta.
        logger.warning("etichetta non applicata a %s (label_id=%s): %s -- riprovo "
                       "risolvendo l'etichetta da capo", entity_id, self._label_id,
                       esito["errore"])
        self._label_id = None
        if not await self._risolvi_etichetta():
            return
        esito = await self._ha.aggiungi_etichetta_a(entity_id, self._label_id)
        if "errore" in esito:
            logger.warning("etichetta non applicata a %s nemmeno al secondo tentativo: %s",
                           entity_id, esito["errore"])

    async def _risolvi_etichetta(self) -> bool:
        """Trova o crea il `label_id` di HIRIS in Home Assistant, aggiornando
        la cache dell'istanza. Restituisce True se una `label_id` valida e'
        nota dopo la chiamata."""
        elenco = await self._ha.elenca_etichette()
        if "errore" in elenco:
            logger.debug("etichette non lette: %s", elenco["errore"])
            return False
        for voce in elenco["etichette"]:
            if (voce.get("name") or "").strip().lower() == NOME_ETICHETTA.lower():
                self._label_id = voce.get("label_id")
                break
        if self._label_id is None:
            creata = await self._ha.crea_etichetta(NOME_ETICHETTA)
            if "errore" in creata:
                logger.debug("etichetta non creata: %s", creata["errore"])
                return False
            self._label_id = (creata.get("etichetta") or {}).get("label_id")
        return self._label_id is not None

    # ---- ripristinare ---------------------------------------------------

    async def ripristina(self, costruzione_id: str, *, origine: str,
                         turno: str | None, adesso: float) -> dict:
        """Rimettere il «prima» e' un'ALTRA costruzione, e passa di qui.

        Non e' una scorciatoia che scrive diretta: valida come tutte le altre,
        e se nel frattempo quel corpo non e' piu' valido lo dice invece di
        scriverlo (spec §6).
        """
        riga = self._archivio.leggi(costruzione_id)
        if riga is None:
            return {"errore": "non ho nessuna costruzione con quell'identificatore."}
        if riga["stato"] != "applicata":
            return {"errore": "quella costruzione non e' mai stata applicata: "
                              "non c'e' niente da rimettere."}
        prima = riga["prima"]
        dominio, chiave = riga["dominio"], riga["chiave"]
        if prima is None:
            # Ripristinare una CREAZIONE significa cancellare cio' che e' nato.
            intento_gesto, dopo = "cancella", None
        else:
            intento_gesto, dopo = "modifica", prima
            motivo = await self._valida(dominio, dopo)
            if motivo is not None:
                return {"errore": f"non posso rimettere com'era: {motivo}"}
        anteprima = (f"Rimetto l'oggetto {dominio}.{chiave} com'era prima "
                     f"del {_data(riga['creata_ts'])}.")
        proposta = self._archivio.proponi(
            gesto=intento_gesto, dominio=dominio, chiave=chiave, origine=origine,
            turno=turno, frase=f"ripristino di {costruzione_id}", prima=riga["dopo"],
            dopo=dopo, helper=[], anteprima=anteprima, adesso=adesso)
        if "errore" in proposta:
            return proposta
        if origine in ORIGINI_UMANE:
            return await self.applica(proposta["id"], origine=origine, turno=turno,
                                      adesso=adesso)
        # Dalla chat il ripristino e' un giro in due tempi come tutto il
        # resto (spec §7): applicarlo subito con lo STESSO `turno` che ha
        # appena creato la proposta farebbe rifiutare SEMPRE dal cancello (e'
        # letteralmente lo stesso turno), e la riga resterebbe `in_attesa` a
        # bruciare un posto del tetto di 20 per sette giorni -- venti
        # tentativi bloccherebbero le proposte di tutto il prodotto.
        if not turno:
            # Senza un turno riconoscibile questa proposta non sara' MAI
            # confermabile da un'origine non umana (`_cancello`, IMPORTANT 1
            # del round 2): l'unica strada e' la pagina, e l'anteprima
            # restituita deve dirlo -- lo stesso messaggio che `applica` da'
            # gia' in quel caso, non un'anteprima muta su un vicolo cieco.
            anteprima += ("\nSenza un turno riconoscibile non potro' confermare da "
                         "qui: apri la pagina Costruzioni e conferma di la'.")
        return {"proposta_id": proposta["id"], "anteprima": anteprima}


def _forma_invalida(intento: dict) -> str | None:
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
    testuale-a-dizionario arriva a `forme.componi_script`, che fa
    `dict(campi)` -- `ValueError` su una stringa, `TypeError` su un intero.
    """
    for campo in ("alias", "descrizione", "frase", "chiave"):
        valore = intento.get(campo)
        if valore is not None and not isinstance(valore, str):
            return f"«{campo}» deve essere testo, non {type(valore).__name__}."
    for campo in ("innesco", "condizioni", "azioni", "stati", "helper", "parametri"):
        valore = intento.get(campo)
        if valore is not None and not isinstance(valore, list):
            return f"«{campo}» deve essere una lista, non {type(valore).__name__}."
    campi = intento.get("campi")
    if campi is not None and not isinstance(campi, dict):
        return f"«campi» deve essere un dizionario, non {type(campi).__name__}."
    for voce in intento.get("helper") or []:
        if not isinstance(voce, dict) or not isinstance(voce.get("dominio"), str):
            return "ogni helper deve essere un dizionario con un «dominio» testuale."
    return None


def _seme_da(intento: dict) -> int:
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
    return base + abs(hash((intento.get("alias"), intento.get("frase")))) % 100_000_000


def _compatta(corpo: dict | None) -> str:
    if not corpo:
        return "(niente)"
    pezzi = []
    for chiave in ("alias", "name", "description"):
        if corpo.get(chiave):
            pezzi.append(str(corpo[chiave]))
    for chiave in ("triggers", "conditions", "actions", "sequence", "entities"):
        if corpo.get(chiave):
            pezzi.append(f"{chiave}: {len(corpo[chiave])}")
    return " · ".join(pezzi) if pezzi else "(vuoto)"


def _data(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")


def _traduci_rifiuto(errore: str, dominio: str) -> str:
    """Un presupposto d'ambiente non deve sembrare un guasto (spec §6).

    Se l'API di configurazione non c'e' o non governa quella struttura --
    automazioni scritte a mano, o in `packages/` -- Home Assistant risponde
    404. Dirlo come «404» costringerebbe l'utente a indovinare cosa e'
    successo.
    """
    # RULING 2 della scansione pre-volo: il nome del dominio va in ITALIANO --
    # e' una frase rivolta all'utente, e i vincoli globali lo impongono.
    plurale = {"automation": "automazioni", "script": "script",
               "scene": "scene"}.get(dominio, dominio)
    if "404" in errore or "not found" in errore.lower():
        return (f"queste {plurale} sono gestite a mano (o vivono in `packages/`): "
                "l'API di configurazione di Home Assistant non le governa, e non posso "
                "scriverle. Posso mostrarti il pezzo corretto da incollare.")
    return errore
