"""L'osservatore: guarda il rubinetto dei cambi e annota, senza giudicare.

**Non apre un secondo rubinetto.** Si aggancia a `HAClient.add_state_listener`,
lo stesso che alimenta lo specchio delle entita': due sorgenti degli stessi
eventi sarebbero due cose che possono divergere.

**Non giudica niente.** Filtra col pavimento e scrive il cambio cosi' com'e'.
Tutto il giudizio sta nell'aggregazione (`oggetti.py`), che e' rifacibile per
21 giorni; una decisione presa qui non si corregge piu'.
"""
from __future__ import annotations

import logging
import time

from ..casa.tempo import epoch_istante
from .pavimento import gamba

logger = logging.getLogger(__name__)

# Stati transitori del boot di Home Assistant: nascono e muoiono da soli in
# pochi secondi, non sono un guasto. Se il primo giro del lavoro periodico
# cade durante il boot, trattarli come guasto scriverebbe una coppia di righe
# di rumore (nasce, finisce) per ogni integrazione della casa. Stessi valori
# di `casa/nucleo.py::_STATI_INTEGRAZIONE_ROTTA` (verificati su
# `ConfigEntryState`, `homeassistant/config_entries.py`), che pero' non li
# elenca perche' li esclude gia' per costruzione -- RICOPIATI, non importati,
# per la stessa ragione di `pavimento.py`: «cosa e' un guasto QUI» e «cosa
# racconta l'anagrafe» sono due domande diverse i cui elenchi possono
# divergere in futuro per ragioni proprie.
_STATI_INTEGRAZIONE_TRANSITORI = frozenset({"setup_in_progress", "unload_in_progress"})


def _testo_o_none(valore) -> str | None:
    """Un attributo di Home Assistant -> stringa per il grezzo, o `None`.

    Non inventa: un tipo inatteso (numero, lista, dict, stringa vuota)
    diventa `None`, non un `str(valore)` che scriverebbe testo spazzatura
    nella colonna."""
    return valore if isinstance(valore, str) and valore.strip() else None


class Osservatore:
    """Il rubinetto e le condizioni di sistema, verso l'archivio.

    `adesso` e' iniettabile perche' i test possano fissare l'orologio senza
    toccare il modulo `time`.
    """

    def __init__(self, archivio, *, adesso=time.time) -> None:
        self._archivio = archivio
        self._adesso = adesso
        # Cosa sta guardando, e per quale gamba. Si riempie osservando: e'
        # cio' che la pagina mostra, e non una lista dichiarata a mano che
        # potrebbe divergere da cio' che succede davvero.
        self._viste: dict[str, str] = {}
        # Le condizioni di sistema aperte all'ultimo giro. Serve a scrivere un
        # cambio quando NASCONO e quando FINISCONO, invece di riscriverle a
        # ogni passaggio del lavoro periodico. Vive solo in RAM: al riavvio
        # va ricostruito con `ricostruisci_condizioni`, vedi sotto.
        self._condizioni: set[str] = set()

    # -- il rubinetto --------------------------------------------------

    def guarda_cambio(self, evento) -> bool:
        """Il callback di `add_state_listener`. **Non solleva mai.**

        Non e' per fermare l'osservatore: il rubinetto vero (`ha_client.py`,
        `add_state_listener`) incapsula gia' ogni callback in try/except con
        `logger.exception`, quindi un'eccezione qui perderebbe **solo
        quell'evento**, non fermerebbe l'osservatore. Il try/except resta
        comunque la difesa giusta -- logga con contesto proprio (l'evento, il
        tipo di errore) invece del generico "callback raised" del rubinetto,
        e non dipende da un dettaglio di cablaggio che potrebbe cambiare.
        """
        try:
            if not isinstance(evento, dict):
                return False
            eid = evento.get("entity_id")
            nuovo = evento.get("new_state")
            if not eid or not isinstance(nuovo, dict):
                # `new_state` a `None` e' un'entita' rimossa: non e' un cambio
                # da osservare, e' una cosa che non c'e' piu'.
                return False
            attributi = nuovo.get("attributes")
            attributi = attributi if isinstance(attributi, dict) else {}
            quale = gamba(eid, attributi)
            if quale is None:
                return False
            vecchio = evento.get("old_state")
            # L'istante e' quello del CAMBIO, non della scrittura: `last_changed`
            # dice quando la casa e' cambiata, il nostro orologio quando l'abbiamo
            # saputo. Annotare il secondo sposterebbe ogni oggetto di quel tanto.
            quando = epoch_istante(nuovo.get("last_changed"))
            if quando is None:
                # Ripiego muto fino a qui: se HA cambiasse formato di
                # `last_changed`, ogni cambio slitterebbe all'istante in cui
                # l'abbiamo saputo e nessuno se ne accorgerebbe. DEBUG e non
                # WARNING: capiterebbe per OGNI evento se `last_changed`
                # mancasse sempre, e un WARNING per riga inonderebbe il
                # registro -- a DEBUG resta comunque disponibile a chi
                # diagnostica.
                logger.debug(
                    "osservatore: 'last_changed' mancante o illeggibile per "
                    "%s, uso l'orologio", eid)
                quando = self._adesso()
            self._archivio.annota(
                quando_ts=quando, fonte="entita", soggetto=str(eid),
                da=vecchio.get("state") if isinstance(vecchio, dict) else None,
                a=nuovo.get("state"),
                device_class=_testo_o_none(attributi.get("device_class")),
                state_class=_testo_o_none(attributi.get("state_class")),
                source_type=_testo_o_none(attributi.get("source_type")))
            self._viste[str(eid)] = quale
            return True
        except Exception as errore:
            logger.warning("osservatore: evento non annotato (%s: %s)",
                           type(errore).__name__, errore)
            return False

    # -- le condizioni di sistema --------------------------------------

    def guarda_sistema(self, *, problemi: list[dict] | None,
                       integrazioni: list[dict] | None) -> int:
        """Le condizioni di Home Assistant, nella STESSA forma dei cambi.

        Un'integrazione rotta non e' un cambio di stato di un'entita' -- ma il
        suo comparire e il suo sparire lo sono. Cosi' la riga del grezzo resta
        una sola, e l'oggetto che ne esce e' un guasto con la sua durata.

        Misurato sulla casa vera il 26/08: `repairs/list_issues` da' 4 problemi
        aperti, e `config_entries/get` da' 9 integrazioni non caricate su 53.
        `system_health/info` torna vuoto e non si usa.

        Gli stati transitori del boot (`_STATI_INTEGRAZIONE_TRANSITORI`) non
        contano come guasto: vedi il commento accanto alla costante.

        **`self._condizioni` si aggiorna incrementalmente**, un soggetto alla
        volta dopo ogni `annota` riuscita -- non in blocco alla fine. Se
        `annota` solleva a meta', le righe «aperto» gia' scritte devono
        restare ricordate: altrimenti il giro successivo le riscriverebbe con
        un istante piu' tardo, cioe' due «aperto» per lo stesso soggetto e una
        data di nascita ambigua per chi aggrega. Qui e' legittimo che
        l'eccezione propaghi -- il «mai sollevare» vale per `guarda_cambio` e
        per la ricostruzione, non per questo metodo, che gira dentro un lavoro
        periodico -- ma la memoria deve restare coerente con cio' che e' stato
        davvero scritto.
        """
        aperte: set[str] = set()
        for p in problemi or []:
            if not isinstance(p, dict):
                continue
            dominio = str(p.get("domain") or "").strip()
            quale = str(p.get("issue_id") or "").strip()
            if dominio and quale:
                aperte.add(f"problema:{dominio}.{quale}")
        for i in integrazioni or []:
            if not isinstance(i, dict):
                continue
            stato = str(i.get("state") or "").strip()
            if stato == "loaded" or stato in _STATI_INTEGRAZIONE_TRANSITORI:
                continue
            ident = str(i.get("entry_id") or "").strip()
            if ident:
                aperte.add(f"integrazione:{ident}")

        adesso = self._adesso()
        scritti = 0
        for nata in sorted(aperte - self._condizioni):
            self._archivio.annota(quando_ts=adesso, fonte="sistema",
                                  soggetto=nata, da=None, a="aperto")
            self._condizioni.add(nata)
            scritti += 1
        for finita in sorted(self._condizioni - aperte):
            self._archivio.annota(quando_ts=adesso, fonte="sistema",
                                  soggetto=finita, da="aperto", a="chiuso")
            self._condizioni.discard(finita)
            scritti += 1
        return scritti

    def ricostruisci_condizioni(self) -> None:
        """Risemina `self._condizioni` da cio' che l'archivio gia' sa.

        **Perche' serve.** `self._condizioni` vive solo in RAM: al riavvio
        dell'add-on -- che succede a ogni aggiornamento, non in un caso
        limite -- quel set ripartirebbe vuoto, e `guarda_sistema` scriverebbe
        di nuovo «aperto» per ogni guasto gia' aperto, come se fosse nato in
        quel momento. La data d'inizio e' l'unica informazione utile di un
        guasto che dura: sbagliarla non e' rumore, e' un fatto falso.

        Da chiamare **una volta, all'avvio**, prima che il rubinetto e il
        lavoro periodico comincino a girare.

        **Limite dichiarato, non una promessa.** Il grezzo vive 21 giorni (22
        con la guardia, vedi `archivio.CONSERVAZIONE_CAMBI_S`). Una condizione
        aperta da piu' a lungo ha gia' perso la sua riga d'apertura con la
        potatura: qui verra' vista come nuova, e la data d'inizio che
        l'oggetto porta sara' quella del ritrovamento, non quella vera. Non e'
        un difetto di questo metodo -- e' il pavimento dei grezzi, e chi legge
        l'oggetto deve saperlo.

        **Non solleva mai.** Se l'archivio non risponde si riparte da vuoto,
        esattamente come al primissimo avvio: fermare l'avvio dell'add-on per
        questo sarebbe uno scambio peggiore.

        **Filtra `fonte="sistema"` NELLA query (D1 del giro di correzioni).**
        Senza, `cambi()` col suo `LIMIT` teneva le righe piu' VECCHIE: sui
        320.000 cambi misurati per 22 giorni (spec §9②), dal quattordicesimo
        giorno di esercizio la ricostruzione smetteva di vedere gli ultimi
        otto -- proprio le righe che decidono l'ultimo stato di una
        condizione. Le righe di sistema sono qualche centinaio, non 320.000:
        filtrarle a monte, nella query, e' insieme la correzione del difetto e
        il modo di non caricare inutilmente tutto il resto in dizionari
        Python a ogni avvio.
        """
        try:
            # La finestra e' quella intera che l'archivio puo' avere: da zero
            # (l'inizio dei tempi, per un archivio che comunque pota da solo)
            # a `float('inf')` -- dice l'intenzione alla lettera, "nessun
            # estremo destro", invece di un `adesso + margine` arbitrario che
            # lascerebbe fuori in silenzio una riga con un istante piu' avanti
            # dell'orologio di questo processo. `cambi()` lo accetta
            # (converte con `float(a_ts)`, e SQLite confronta `+Inf`
            # correttamente). Il `limite` e' esplicito e largo apposta: dice
            # al lettore che il tetto e' stato pensato per il volume delle
            # righe di SISTEMA, non ereditato dal default pensato per quello
            # delle entita'.
            righe = self._archivio.cambi(da_ts=0.0, a_ts=float("inf"),
                                         fonte="sistema", limite=20_000)
        except Exception as errore:
            logger.warning(
                "osservatore: stato di sistema non ricostruito, riparto da "
                "vuoto (%s: %s)", type(errore).__name__, errore)
            self._condizioni = set()
            return

        # `cambi()` torna dal piu' vecchio al piu' recente: scrivendo in
        # ordine in questo dict, l'ultima assegnazione per soggetto e' sempre
        # la piu' recente -- e' cosi' che si trova "l'ultimo stato" senza
        # dover ordinare a mano.
        #
        # Il filtro per fonte e' gia' entrato nella query (sopra): non si
        # ripete qui. Un secondo filtro Python "di scorta" maschererebbe la
        # regressione se quello nella query venisse tolto per errore -- ed e'
        # esattamente il difetto che questo metodo esiste per chiudere.
        ultimo_stato: dict[str, str | None] = {}
        for c in righe:
            if not isinstance(c, dict):
                continue
            soggetto = c.get("soggetto")
            if not soggetto:
                continue
            ultimo_stato[soggetto] = c.get("a")
        self._condizioni = {s for s, stato in ultimo_stato.items() if stato == "aperto"}

    # -- la pagina -----------------------------------------------------

    def osservate(self) -> list[dict]:
        """Cosa sta guardando, e perche'.

        `provenienza` distingue cio' che e' nel **pavimento** (e non si toglie)
        da cio' che l'**obiettivo** ha aggiunto (e si puo' togliere). Oggi tutto
        e' pavimento: il prompt dell'obiettivo entra nella fetta successiva, e
        la terza provenienza -- «me l'ha chiesto l'analista» -- con lui.

        **Una fonte sola per fatto.** Le entita' vengono da `_viste`, le
        condizioni di sistema da `_condizioni` -- non si semina `_viste` con
        le condizioni per rattoppare: sarebbe tenere in vita un doppione, e
        due risposte alla stessa domanda divergono (dopo un riavvio un
        guasto ricostruito sparirebbe da qui per sempre; all'opposto, una
        condizione chiusa scritta anche qui non verrebbe mai tolta).
        """
        entita = ({"soggetto": s, "gamba": g, "provenienza": "pavimento"}
                  for s, g in self._viste.items())
        sistema = ({"soggetto": s, "gamba": "buono stato", "provenienza": "pavimento"}
                   for s in self._condizioni)
        return sorted([*entita, *sistema], key=lambda o: (o["gamba"], o["soggetto"]))
