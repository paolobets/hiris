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

        consiglio = consiglia({
            "richiesto": intento.get("richiesto"),
            "innesco": intento.get("innesco"),
            "passi": intento.get("azioni"),
            "stati": intento.get("stati"),
            "parametri": intento.get("parametri"),
            "riuso": intento.get("riuso"),
            "ricorrente": intento.get("ricorrente"),
        })

        prima = None
        chiave = intento.get("chiave")
        if gesto in ("modifica", "cancella"):
            if not chiave:
                return {"errore": f"per {gesto} serve la chiave dell'oggetto da toccare."}
            letto = await self._ha.leggi_configurazione(dominio, chiave)
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
            letto = await self._ha.leggi_configurazione(dominio, candidata)
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
        nomi = {"automation": "automazione", "script": "script", "scene": "scena"}
        righe = []
        if gesto == "crea":
            righe.append(f"Creo un'{nomi[dominio]} chiamata «{intento.get('alias')}».")
        elif gesto == "modifica":
            righe.append(f"Modifico l'{nomi[dominio]} «{(prima or {}).get('alias') or chiave}», "
                         "che esiste gia' in casa tua.")
            righe.append(f"Prima: {_compatta(prima)}")
            righe.append(f"Dopo: {_compatta(dopo)}")
        else:
            righe.append(f"Cancello l'{nomi[dominio]} «{(prima or {}).get('alias') or chiave}», "
                         "che esiste gia' in casa tua. Conservo com'era.")
        if intento.get("descrizione"):
            righe.append(f"A cosa serve: {intento['descrizione']}")
        for helper in intento.get("helper") or []:
            righe.append(f"Nasce anche un {helper.get('dominio')}: "
                         f"{(helper.get('dati') or {}).get('name')}")
        if consiglio.get("dissenso"):
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
            return {"errore": f"quella proposta e' gia' {proposta['stato']}."}
        cancello = self._cancello(proposta, origine, turno)
        if cancello is not None:
            return {"errore": cancello}

        dominio, chiave, gesto = proposta["dominio"], proposta["chiave"], proposta["gesto"]
        nati: list[tuple[str, str]] = []
        for helper in proposta["helper"]:
            esito = await self._ha.crea_helper(helper.get("dominio"),
                                               helper.get("dati") or {})
            if "errore" in esito:
                await self._disfa(nati)
                return self._fallita(proposta, adesso, origine,
                                     f"non sono riuscito a creare l'helper: {esito['errore']}")
            creato = esito.get("helper") or {}
            if creato.get("id"):
                nati.append((helper.get("dominio"), creato["id"]))

        if gesto == "cancella":
            scritto = await self._ha.cancella_configurazione(dominio, chiave)
            riuscito = "cancellato" in scritto
        else:
            scritto = await self._ha.salva_configurazione(dominio, chiave, proposta["dopo"])
            riuscito = "salvato" in scritto

        if not riuscito:
            await self._disfa(nati)
            return self._fallita(proposta, adesso, origine,
                                 _traduci_rifiuto(scritto.get("errore", ""), dominio))

        entita, avviso = await self._rileggi(dominio, chiave, gesto)
        if gesto == "crea":
            # L'etichetta dice CHI L'HA FATTO, e su una modifica non l'ha fatto
            # HIRIS (spec §5). Un oggetto scritto dal proprietario resta suo
            # anche dopo che HIRIS ci ha messo le mani: che ce le abbia messe
            # e' un fatto DIVERSO, e vive dove lo si puo' interrogare -- la
            # cronaca, l'archivio delle versioni, la pagina.
            for entity_id in entita:
                await self._etichetta(entity_id)

        esecuzione_id = self._cronaca.registra_costruzione(
            origine=origine, gesto=gesto, dominio=dominio, chiave=chiave,
            entita=entita, eseguito=True, adesso=adesso, avviso=avviso)
        self._archivio.segna_applicata(proposta_id, adesso=adesso,
                                       esecuzione_id=esecuzione_id)
        return {"applicata": True, "esecuzione_id": esecuzione_id,
                "entita": entita, "avviso": avviso}

    def _cancello(self, proposta: dict, origine: str, turno: str | None) -> str | None:
        """Il sì dell'umano, reso una guardia deterministica (spec §7).

        Il modello propone e il codice restringe: se `applica` fosse solo
        un'altra chiamata, il modello potrebbe concatenarla nello stesso turno
        e il sì dell'utente sparirebbe senza che nessuno se ne accorga.
        """
        if origine in ORIGINI_UMANE:
            return None
        if not turno:
            return ("non riesco a distinguere i turni, quindi non posso confermare da qui: "
                    "apri la pagina Costruzioni e conferma di la'.")
        if proposta["turno"] and proposta["turno"] == turno:
            return ("questa proposta e' nata in questo stesso turno: te l'ho mostrata, "
                    "ora dimmi tu se procedere.")
        return None

    async def _disfa(self, nati: list[tuple[str, str]]) -> None:
        """Gli helper nati per un'automazione che non e' nata.

        Senza questa disfatta ogni tentativo fallito lascia rifiuti in casa
        dell'utente -- ed e' il modo esatto in cui si accumula la spazzatura
        che nessuno cancella piu' (spec §3.1).
        """
        for dominio, helper_id in reversed(nati):
            esito = await self._ha.cancella_helper(dominio, helper_id)
            if "errore" in esito:
                logger.warning("helper %s.%s creato e NON disfatto: %s",
                               dominio, helper_id, esito["errore"])

    def _fallita(self, proposta: dict, adesso: float, origine: str, motivo: str) -> dict:
        esecuzione_id = self._cronaca.registra_costruzione(
            origine=origine, gesto=proposta["gesto"], dominio=proposta["dominio"],
            chiave=proposta["chiave"], entita=[], eseguito=False, adesso=adesso,
            errore=motivo)
        self._archivio.segna_rifiutata(proposta["id"], adesso=adesso, motivo=motivo)
        return {"errore": motivo, "esecuzione_id": esecuzione_id}

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
        if self._label_id is None:
            elenco = await self._ha.elenca_etichette()
            if "errore" in elenco:
                logger.debug("etichette non lette: %s", elenco["errore"])
                return
            for voce in elenco["etichette"]:
                if (voce.get("name") or "").strip().lower() == NOME_ETICHETTA.lower():
                    self._label_id = voce.get("label_id")
                    break
            if self._label_id is None:
                creata = await self._ha.crea_etichetta(NOME_ETICHETTA)
                if "errore" in creata:
                    logger.debug("etichetta non creata: %s", creata["errore"])
                    return
                self._label_id = (creata.get("etichetta") or {}).get("label_id")
        if self._label_id:
            esito = await self._ha.aggiungi_etichetta_a(entity_id, self._label_id)
            if "errore" in esito:
                logger.debug("etichetta non applicata a %s: %s", entity_id, esito["errore"])

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
        return await self.applica(proposta["id"], origine=origine, turno=turno,
                                  adesso=adesso)


def _seme_da(intento: dict) -> int:
    """Un seme per l'id, derivato dall'intento e non dall'orologio.

    L'orologio lo legge il chiamante (`adesso`), non le funzioni pure: qui
    serve solo un numero grande e stabile, e la lunghezza del testo
    dell'intento con un'ancora fissa lo da' senza far diventare questo modulo
    dipendente dal tempo. La verifica di unicita' vera la fa
    `forme.nuovo_id` contro gli id esistenti, e Home Assistant rifiuterebbe
    comunque un duplicato.
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
