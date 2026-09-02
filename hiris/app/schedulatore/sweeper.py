"""Il battito dello schedulatore: chi e' scaduto, chi si e' perso, chi si sveglia.

Non conosce ne' la chat, ne' il modello, ne' Home Assistant. Riceve due
funzioni al montaggio -- `execute` (la porta unica) e `interpreta` (il turno di
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

from .promise import TOLLERANZA_S, delay_reason

logger = logging.getLogger(__name__)

_SENZA_RECAPITO = ("avevo qualcosa da dirti e nessun modo per venire a cercarti: "
                   "nessun canale di notifica era stato scelto quando l'hai chiesta.")


class Sweeper:
    def __init__(self, store, *, execute, interpreta,
                 tolleranza_s: float = TOLLERANZA_S) -> None:
        self._store = store
        self._execute = execute
        self._interpreta = interpreta
        self._tolleranza = tolleranza_s

    async def batti(self, now: float) -> None:
        for promise in self._store.scadute(now):
            delay = now - promise["quando_ts"]
            # Il controllo del ritardo viene PRIMA della presa: una promessa
            # saltata non deve nemmeno passare per `in_corso`, o un guasto qui
            # in mezzo la lascerebbe fallita invece che saltata, cioe'
            # racconterebbe un'altra storia.
            if delay > self._tolleranza:
                self._store.concludi(promise["id"], state="saltata",
                                        reason=delay_reason(delay), now=now)
                logger.info("promessa %s saltata: %s", promise["id"],
                            delay_reason(delay))
                continue
            if not self._store.prendi(promise["id"], now=now):
                continue  # qualcun altro l'ha presa: mai due volte
            try:
                await self._keep(promise, now)
            except Exception as error:
                logger.warning("promessa %s: guasto imprevisto (%s: %s)",
                               promise["id"], type(error).__name__, error)
                self._store.concludi(
                    promise["id"], state="fallita", now=now,
                    reason=(
                        f"guasto imprevisto mentre la mantenevo "
                        f"({type(error).__name__}: {error})."
                    ),
                )

    async def _keep(self, promise: dict, now: float) -> None:
        if promise["specie"] == "fai":
            await self._keep_fai(promise, now)
        else:
            await self._keep_chiedi(promise, now)

    async def _keep_fai(self, promise: dict, now: float) -> None:
        occurrence = await self._execute(promise["chiamata"], actor="schedulatore")
        if occurrence.get("eseguito"):
            self._store.concludi(promise["id"], state="mantenuta", now=now,
                                    execution_id=occurrence.get("esecuzione_id"))
        else:
            self._store.concludi(
                promise["id"], state="fallita", now=now,
                reason=occurrence.get("errore") or "non e' andata, e non so dire perche'.",
                execution_id=occurrence.get("esecuzione_id"))

    async def _keep_chiedi(self, promise: dict, now: float) -> None:
        answer = await self._interpreta(promise)
        if answer.get("accodata"):
            # Il turno e' andato al piano: la promessa resta `in_corso` e sara'
            # la sua conclusione a chiuderla, minuti dopo. Qui non c'e' niente
            # da decidere -- e soprattutto non si aspetta: il battito prosegue
            # col resto del giro.
            return
        if "errore" in answer:
            self._store.concludi(promise["id"], state="fallita", now=now,
                                    reason=answer["errore"])
            return
        await self.concludi_chiedi(promise, answer, now=now)

    async def concludi_chiedi(self, promise: dict, answer: dict, *,
                              now: float) -> None:
        """Il SECONDO TEMPO di «mantieni»: la conclusione, da qualunque strada arrivi.

        Estratto da `_keep_chiedi` con la fetta «le promesse seguono la
        catena» (22/08/2026), senza cambiarne una riga di comportamento. Sul
        ramo sincrono la conclusione torna dal turno e si chiude subito, come
        sempre; sul ponte il turno gira altrove e per minuti, e a chiamare qui
        e' la rotta MCP quando il modello ha chiamato `conclude`.

        **Un solo punto conclude una promessa**, come `azione/porta.py` e'
        l'unico che esegue: un secondo sarebbe un difetto, non
        un'ottimizzazione -- due strade che decidono se notificare, e con
        quali parole, sono due strade libere di divergere sul gesto piu'
        visibile che il prodotto compie.
        """
        avvisare = bool(answer.get("avvisare"))
        text = answer.get("testo") or ""
        reason = None
        execution_id = None

        if avvisare and promise["recapito"]:
            # La notifica la manda LO SCHEDULATORE, dalla porta di tutti, sul
            # canale approvato alla nascita. Il modello ha prodotto un testo,
            # non una chiamata: non sceglie lui dove finisce.
            occurrence = await self._execute(
                {"servizio": promise["recapito"], "bersaglio": {},
                 "dati": {"message": text, "title": "HIRIS"}},
                actor="schedulatore")
            execution_id = occurrence.get("esecuzione_id")
            if not occurrence.get("eseguito"):
                reason = ("te l'ho scritto qui ma la notifica non e' partita: %s"
                          % (occurrence.get("errore") or "non so dire perche'."))
        elif avvisare:
            # Non si inventa un canale. La promessa e' mantenuta -- il testo
            # c'e' e si legge dalla pagina -- e dichiara la consegna mancata
            # invece di farla passare per riuscita.
            reason = _SENZA_RECAPITO

        # La nota del ripiego, quando c'e': il turno e' passato dal forfait al
        # consumo, e la promessa e' l'unico posto in cui l'utente puo'
        # leggerlo -- non ha una risposta in chat in cui metterla. Si accoda a
        # un motivo che ci fosse gia' (la notifica non partita, il recapito
        # mancante) invece di sostituirlo: sono due fatti diversi, e il primo
        # non smette di essere vero perche' e' arrivato il secondo.
        note = answer.get("nota") or ""
        if note:
            reason = (f"{reason} {note}") if reason else note

        self._store.concludi(promise["id"], state="mantenuta", now=now,
                                reason=reason, text=text, avvisare=avvisare,
                                execution_id=execution_id)
