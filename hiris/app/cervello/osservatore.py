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

        L'osservatore gira per sempre e riceve ogni evento della casa:
        un'eccezione qui lo fermerebbe, e nessuno se ne accorgerebbe finche'
        qualcuno non chiedesse un mese di storia che non c'e'.
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
            quale = gamba(eid, nuovo.get("attributes"))
            if quale is None:
                return False
            vecchio = evento.get("old_state")
            # L'istante e' quello del CAMBIO, non della scrittura: `last_changed`
            # dice quando la casa e' cambiata, il nostro orologio quando l'abbiamo
            # saputo. Annotare il secondo sposterebbe ogni oggetto di quel tanto.
            quando = epoch_istante(nuovo.get("last_changed")) or self._adesso()
            self._archivio.annota(
                quando_ts=quando, fonte="entita", soggetto=str(eid),
                da=(vecchio or {}).get("state") if isinstance(vecchio, dict) else None,
                a=nuovo.get("state"))
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
            if str(i.get("state") or "").strip() == "loaded":
                continue
            ident = str(i.get("entry_id") or "").strip()
            if ident:
                aperte.add(f"integrazione:{ident}")

        adesso = self._adesso()
        scritti = 0
        for nata in sorted(aperte - self._condizioni):
            self._archivio.annota(quando_ts=adesso, fonte="sistema",
                                  soggetto=nata, da=None, a="aperto")
            self._viste[nata] = "buono stato"
            scritti += 1
        for finita in sorted(self._condizioni - aperte):
            self._archivio.annota(quando_ts=adesso, fonte="sistema",
                                  soggetto=finita, da="aperto", a="chiuso")
            scritti += 1
        self._condizioni = aperte
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
        """
        try:
            adesso = self._adesso()
            # La finestra e' quella intera che l'archivio puo' avere: da zero
            # (l'inizio dei tempi, per un archivio che comunque pota da solo)
            # a un istante appena oltre adesso -- la finestra di `cambi()' e'
            # semi-aperta e `a_ts` escluso, quindi un cambio scritto proprio
            # ora andrebbe perso senza quel margine.
            righe = self._archivio.cambi(da_ts=0.0, a_ts=adesso + 1.0)
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
        ultimo_stato: dict[str, str | None] = {}
        for c in righe:
            if not isinstance(c, dict) or c.get("fonte") != "sistema":
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
        """
        return sorted(
            ({"soggetto": s, "gamba": g, "provenienza": "pavimento"}
             for s, g in self._viste.items()),
            key=lambda o: (o["gamba"], o["soggetto"]))
