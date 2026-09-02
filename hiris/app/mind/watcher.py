"""L'osservatore: guarda il rubinetto dei cambi e annota, senza giudicare.

**Non apre un secondo rubinetto.** Si aggancia a `HAClient.add_state_listener`,
lo stesso che alimenta lo specchio delle entita': due sorgenti degli stessi
eventi sarebbero due cose che possono divergere.

**Non giudica niente.** Filtra col pavimento e scrive il cambio cosi' com'e'.
Tutto il giudizio sta nell'aggregazione (`facts.py`), che e' rifacibile per
21 giorni; una decisione presa qui non si corregge piu'.
"""
from __future__ import annotations

import logging
import time

from ..home_space.historian import instant_epoch
from .baseline import aspect

logger = logging.getLogger(__name__)

# Stati transitori del boot di Home Assistant: nascono e muoiono da soli in
# pochi secondi, non sono un guasto. Se il primo giro del lavoro periodico
# cade durante il boot, trattarli come guasto scriverebbe una coppia di righe
# di rumore (nasce, finisce) per ogni integrazione della casa. Stessi valori
# di `home_space/briefing.py::_BROKEN_INTEGRATION_STATES` (verificati su
# `ConfigEntryState`, `homeassistant/config_entries.py`), che pero' non li
# elenca perche' li esclude gia' per costruzione -- RICOPIATI, non importati,
# per la stessa ragione di `baseline.py`: «cosa e' un guasto QUI» e «cosa
# racconta l'anagrafe» sono due domande diverse i cui elenchi possono
# divergere in futuro per ragioni proprie.
_TRANSIENT_INTEGRATION_STATES = frozenset({"setup_in_progress", "unload_in_progress"})


def _text_or_none(value) -> str | None:
    """Un attributo di Home Assistant -> stringa per il grezzo, o `None`.

    Non inventa: un tipo inatteso (numero, lista, dict, stringa vuota)
    diventa `None`, non un `str(valore)` che scriverebbe testo spazzatura
    nella colonna."""
    return value if isinstance(value, str) and value.strip() else None


class Watcher:
    """Il rubinetto e le condizioni di sistema, verso l'archivio.

    `now` e' iniettabile perche' i test possano fissare l'orologio senza
    toccare il modulo `time`.
    """

    def __init__(self, store, *, now=time.time) -> None:
        self._store = store
        self._now = now
        # Cosa sta guardando, e per quale gamba. Si riempie osservando: e'
        # cio' che la pagina mostra, e non una lista dichiarata a mano che
        # potrebbe divergere da cio' che succede davvero.
        self._watched: dict[str, str] = {}
        # Le condizioni di sistema aperte all'ultimo giro. Serve a scrivere un
        # cambio quando NASCONO e quando FINISCONO, invece di riscriverle a
        # ogni passaggio del lavoro periodico. Vive solo in RAM: al riavvio
        # va ricostruito con `rebuild_conditions`, vedi sotto.
        self._conditions: set[str] = set()

    # -- il rubinetto --------------------------------------------------

    def watch_reading(self, event) -> bool:
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
            if not isinstance(event, dict):
                return False
            eid = event.get("entity_id")
            new_state = event.get("new_state")
            if not eid or not isinstance(new_state, dict):
                # `new_state` a `None` e' un'entita' rimossa: non e' un cambio
                # da osservare, e' una cosa che non c'e' piu'.
                return False
            attributes = new_state.get("attributes")
            attributes = attributes if isinstance(attributes, dict) else {}
            which = aspect(eid, attributes)
            if which is None:
                return False
            old_state = event.get("old_state")
            # L'istante e' quello del CAMBIO, non della scrittura: `last_changed`
            # dice quando la casa e' cambiata, il nostro orologio quando l'abbiamo
            # saputo. Annotare il secondo sposterebbe ogni oggetto di quel tanto.
            when = instant_epoch(new_state.get("last_changed"))
            if when is None:
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
                when = self._now()
            self._store.record(
                quando_ts=when, source="entita", subject=str(eid),
                da=old_state.get("state") if isinstance(old_state, dict) else None,
                a=new_state.get("state"),
                device_class=_text_or_none(attributes.get("device_class")),
                state_class=_text_or_none(attributes.get("state_class")),
                source_type=_text_or_none(attributes.get("source_type")))
            self._watched[str(eid)] = which
            return True
        except Exception as error:
            logger.warning("osservatore: evento non annotato (%s: %s)",
                           type(error).__name__, error)
            return False

    # -- le condizioni di sistema --------------------------------------

    def watch_system(self, *, problems: list[dict] | None,
                       integrations: list[dict] | None) -> int:
        """Le condizioni di Home Assistant, nella STESSA forma dei cambi.

        Un'integrazione rotta non e' un cambio di stato di un'entita' -- ma il
        suo comparire e il suo sparire lo sono. Cosi' la riga del grezzo resta
        una sola, e l'oggetto che ne esce e' un guasto con la sua durata.

        Misurato sulla casa vera il 26/08: `repairs/list_issues` da' 4 problemi
        aperti, e `config_entries/get` da' 9 integrazioni non caricate su 53.
        `system_health/info` torna vuoto e non si usa.

        Gli stati transitori del boot (`_TRANSIENT_INTEGRATION_STATES`) non
        contano come guasto: vedi il commento accanto alla costante.

        **`self._conditions` si aggiorna incrementalmente**, un soggetto alla
        volta dopo ogni `record` riuscita -- non in blocco alla fine. Se
        `record` solleva a meta', le righe «aperto» gia' scritte devono
        restare ricordate: altrimenti il giro successivo le riscriverebbe con
        un istante piu' tardo, cioe' due «aperto» per lo stesso soggetto e una
        data di nascita ambigua per chi aggrega. Qui e' legittimo che
        l'eccezione propaghi -- il «mai sollevare» vale per `watch_reading` e
        per la ricostruzione, non per questo metodo, che gira dentro un lavoro
        periodico -- ma la memoria deve restare coerente con cio' che e' stato
        davvero scritto.
        """
        open_conditions: set[str] = set()
        for p in problems or []:
            if not isinstance(p, dict):
                continue
            domain = str(p.get("domain") or "").strip()
            which = str(p.get("issue_id") or "").strip()
            if domain and which:
                open_conditions.add(f"problema:{domain}.{which}")
        for i in integrations or []:
            if not isinstance(i, dict):
                continue
            state = str(i.get("state") or "").strip()
            if state == "loaded" or state in _TRANSIENT_INTEGRATION_STATES:
                continue
            ident = str(i.get("entry_id") or "").strip()
            if ident:
                open_conditions.add(f"integrazione:{ident}")

        now = self._now()
        written = 0
        for born in sorted(open_conditions - self._conditions):
            self._store.record(quando_ts=now, source="sistema",
                                  subject=born, da=None, a="aperto")
            self._conditions.add(born)
            written += 1
        for ended in sorted(self._conditions - open_conditions):
            self._store.record(quando_ts=now, source="sistema",
                                  subject=ended, da="aperto", a="chiuso")
            self._conditions.discard(ended)
            written += 1
        return written

    def rebuild_conditions(self) -> None:
        """Risemina `self._conditions` da cio' che l'archivio gia' sa.

        **Perche' serve.** `self._conditions` vive solo in RAM: al riavvio
        dell'add-on -- che succede a ogni aggiornamento, non in un caso
        limite -- quel set ripartirebbe vuoto, e `watch_system` scriverebbe
        di nuovo «aperto» per ogni guasto gia' aperto, come se fosse nato in
        quel momento. La data d'inizio e' l'unica informazione utile di un
        guasto che dura: sbagliarla non e' rumore, e' un fatto falso.

        Da chiamare **una volta, all'avvio**, prima che il rubinetto e il
        lavoro periodico comincino a girare.

        **Limite dichiarato, non una promessa.** Il grezzo vive 21 giorni (22
        con la guardia, vedi `archivio.READING_RETENTION_S`). Una condizione
        aperta da piu' a lungo ha gia' perso la sua riga d'apertura con la
        potatura: qui verra' vista come nuova, e la data d'inizio che
        l'oggetto porta sara' quella del ritrovamento, non quella vera. Non e'
        un difetto di questo metodo -- e' il pavimento dei grezzi, e chi legge
        l'oggetto deve saperlo.

        **Non solleva mai.** Se l'archivio non risponde si riparte da vuoto,
        esattamente come al primissimo avvio: fermare l'avvio dell'add-on per
        questo sarebbe uno scambio peggiore.

        **Filtra `source="sistema"` NELLA query (D1 del giro di correzioni).**
        Senza, `readings()` col suo `LIMIT` teneva le righe piu' VECCHIE: sui
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
            # dell'orologio di questo processo. `readings()` lo accetta
            # (converte con `float(to_ts)`, e SQLite confronta `+Inf`
            # correttamente). Il `limit` e' esplicito e largo apposta: dice
            # al lettore che il tetto e' stato pensato per il volume delle
            # righe di SISTEMA, non ereditato dal default pensato per quello
            # delle entita'.
            rows = self._store.readings(from_ts=0.0, to_ts=float("inf"),
                                         source="sistema", limit=20_000)
        except Exception as error:
            logger.warning(
                "osservatore: stato di sistema non ricostruito, riparto da "
                "vuoto (%s: %s)", type(error).__name__, error)
            self._conditions = set()
            return

        # `readings()` torna dal piu' vecchio al piu' recente: scrivendo in
        # ordine in questo dict, l'ultima assegnazione per soggetto e' sempre
        # la piu' recente -- e' cosi' che si trova "l'ultimo stato" senza
        # dover ordinare a mano.
        #
        # Il filtro per fonte e' gia' entrato nella query (sopra): non si
        # ripete qui. Un secondo filtro Python "di scorta" maschererebbe la
        # regressione se quello nella query venisse tolto per errore -- ed e'
        # esattamente il difetto che questo metodo esiste per chiudere.
        last_state: dict[str, str | None] = {}
        for c in rows:
            if not isinstance(c, dict):
                continue
            subject = c.get("soggetto")
            if not subject:
                continue
            last_state[subject] = c.get("a")
        self._conditions = {s for s, state in last_state.items() if state == "aperto"}

    # -- la pagina -----------------------------------------------------

    def watching(self) -> list[dict]:
        """Cosa sta guardando, e perche'.

        `provenienza` distingue cio' che e' nel **pavimento** (e non si toglie)
        da cio' che l'**obiettivo** ha aggiunto (e si puo' togliere). Oggi tutto
        e' pavimento: il prompt dell'obiettivo entra nella fetta successiva, e
        la terza provenienza -- «me l'ha chiesto l'analista» -- con lui.

        **Una fonte sola per fatto.** Le entita' vengono da `_watched`, le
        condizioni di sistema da `_conditions` -- non si semina `_watched` con
        le condizioni per rattoppare: sarebbe tenere in vita un doppione, e
        due risposte alla stessa domanda divergono (dopo un riavvio un
        guasto ricostruito sparirebbe da qui per sempre; all'opposto, una
        condizione chiusa scritta anche qui non verrebbe mai tolta).
        """
        entity = ({"soggetto": s, "gamba": g, "provenienza": "pavimento"}
                  for s, g in self._watched.items())
        system = ({"soggetto": s, "gamba": "buono stato", "provenienza": "pavimento"}
                   for s in self._conditions)
        return sorted([*entity, *system], key=lambda o: (o["gamba"], o["soggetto"]))
