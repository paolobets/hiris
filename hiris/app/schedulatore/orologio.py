"""Il battito dello schedulatore: chi e' scaduto, chi si e' perso, chi si sveglia.

Non conosce ne' la chat, ne' il modello, ne' Home Assistant. Riceve due
funzioni al montaggio -- `esegui` (la porta unica) e `interpreta` (il turno di
`chiedi`) -- e non sa da dove vengano. E' la stessa disciplina che ha reso
riusabile `azione/porta.py`, ed e' il motivo per cui questo modulo si prova
per intero con due finte.

`batti()` non solleva MAI: un guasto su una promessa diventa il suo motivo, e
le altre del giro vengono mantenute lo stesso. Un battito che muore a meta'
lascerebbe promesse `in_corso` che al riavvio diventano fallite -- un difetto
che si vede solo il giorno in cui capita.
"""
from __future__ import annotations

import logging

from .promessa import TOLLERANZA_S, motivo_ritardo

logger = logging.getLogger(__name__)

_SENZA_RECAPITO = ("avevo qualcosa da dirti e nessun modo per venire a cercarti: "
                   "nessun canale di notifica era stato scelto quando l'hai chiesta.")


class Orologio:
    def __init__(self, archivio, *, esegui, interpreta,
                 tolleranza_s: float = TOLLERANZA_S) -> None:
        self._archivio = archivio
        self._esegui = esegui
        self._interpreta = interpreta
        self._tolleranza = tolleranza_s

    async def batti(self, adesso: float) -> None:
        for promessa in self._archivio.scadute(adesso):
            ritardo = adesso - promessa["quando_ts"]
            # Il controllo del ritardo viene PRIMA della presa: una promessa
            # saltata non deve nemmeno passare per `in_corso`, o un guasto qui
            # in mezzo la lascerebbe fallita invece che saltata, cioe'
            # racconterebbe un'altra storia.
            if ritardo > self._tolleranza:
                self._archivio.concludi(promessa["id"], stato="saltata",
                                        motivo=motivo_ritardo(ritardo), adesso=adesso)
                logger.info("promessa %s saltata: %s", promessa["id"],
                            motivo_ritardo(ritardo))
                continue
            if not self._archivio.prendi(promessa["id"], adesso=adesso):
                continue  # qualcun altro l'ha presa: mai due volte
            try:
                await self._mantieni(promessa, adesso)
            except Exception as errore:
                logger.warning("promessa %s: guasto imprevisto (%s: %s)",
                               promessa["id"], type(errore).__name__, errore)
                self._archivio.concludi(
                    promessa["id"], stato="fallita", adesso=adesso,
                    motivo=(
                        f"guasto imprevisto mentre la mantenevo "
                        f"({type(errore).__name__}: {errore})."
                    ),
                )

    async def _mantieni(self, promessa: dict, adesso: float) -> None:
        if promessa["specie"] == "fai":
            await self._mantieni_fai(promessa, adesso)
        else:
            await self._mantieni_chiedi(promessa, adesso)

    async def _mantieni_fai(self, promessa: dict, adesso: float) -> None:
        esito = await self._esegui(promessa["chiamata"], origine="schedulatore")
        if esito.get("eseguito"):
            self._archivio.concludi(promessa["id"], stato="mantenuta", adesso=adesso,
                                    esecuzione_id=esito.get("esecuzione_id"))
        else:
            self._archivio.concludi(
                promessa["id"], stato="fallita", adesso=adesso,
                motivo=esito.get("errore") or "non e' andata, e non so dire perche'.",
                esecuzione_id=esito.get("esecuzione_id"))

    async def _mantieni_chiedi(self, promessa: dict, adesso: float) -> None:
        risposta = await self._interpreta(promessa)
        if risposta.get("accodata"):
            # Il turno e' andato al piano: la promessa resta `in_corso` e sara'
            # la sua conclusione a chiuderla, minuti dopo. Qui non c'e' niente
            # da decidere -- e soprattutto non si aspetta: il battito prosegue
            # col resto del giro.
            return
        if "errore" in risposta:
            self._archivio.concludi(promessa["id"], stato="fallita", adesso=adesso,
                                    motivo=risposta["errore"])
            return
        await self.concludi_chiedi(promessa, risposta, adesso=adesso)

    async def concludi_chiedi(self, promessa: dict, risposta: dict, *,
                              adesso: float) -> None:
        """Il SECONDO TEMPO di «mantieni»: la conclusione, da qualunque strada arrivi.

        Estratto da `_mantieni_chiedi` con la fetta «le promesse seguono la
        catena» (22/08/2026), senza cambiarne una riga di comportamento. Sul
        ramo sincrono la conclusione torna dal turno e si chiude subito, come
        sempre; sul ponte il turno gira altrove e per minuti, e a chiamare qui
        e' la rotta MCP quando il modello ha chiamato `concludi`.

        **Un solo punto conclude una promessa**, come `azione/porta.py` e'
        l'unico che esegue: un secondo sarebbe un difetto, non
        un'ottimizzazione -- due strade che decidono se notificare, e con
        quali parole, sono due strade libere di divergere sul gesto piu'
        visibile che il prodotto compie.
        """
        avvisare = bool(risposta.get("avvisare"))
        testo = risposta.get("testo") or ""
        motivo = None
        esecuzione_id = None

        if avvisare and promessa["recapito"]:
            # La notifica la manda LO SCHEDULATORE, dalla porta di tutti, sul
            # canale approvato alla nascita. Il modello ha prodotto un testo,
            # non una chiamata: non sceglie lui dove finisce.
            esito = await self._esegui(
                {"servizio": promessa["recapito"], "bersaglio": {},
                 "dati": {"message": testo, "title": "HIRIS"}},
                origine="schedulatore")
            esecuzione_id = esito.get("esecuzione_id")
            if not esito.get("eseguito"):
                motivo = ("te l'ho scritto qui ma la notifica non e' partita: %s"
                          % (esito.get("errore") or "non so dire perche'."))
        elif avvisare:
            # Non si inventa un canale. La promessa e' mantenuta -- il testo
            # c'e' e si legge dalla pagina -- e dichiara la consegna mancata
            # invece di farla passare per riuscita.
            motivo = _SENZA_RECAPITO

        # La nota del ripiego, quando c'e': il turno e' passato dal forfait al
        # consumo, e la promessa e' l'unico posto in cui l'utente puo'
        # leggerlo -- non ha una risposta in chat in cui metterla. Si accoda a
        # un motivo che ci fosse gia' (la notifica non partita, il recapito
        # mancante) invece di sostituirlo: sono due fatti diversi, e il primo
        # non smette di essere vero perche' e' arrivato il secondo.
        nota = risposta.get("nota") or ""
        if nota:
            motivo = (f"{motivo} {nota}") if motivo else nota

        self._archivio.concludi(promessa["id"], stato="mantenuta", adesso=adesso,
                                motivo=motivo, testo=testo, avvisare=avvisare,
                                esecuzione_id=esecuzione_id)
