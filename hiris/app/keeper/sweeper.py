"""Il battito dello schedulatore: chi e' scaduto, chi si e' perso, chi si sveglia.

Non conosce ne' la chat, ne' il modello, ne' Home Assistant. Riceve le sue
funzioni al montaggio -- `execute` (la porta unica), `interpreta` (il turno di
`chiedi`), e dalla fetta «il seguito delle chat divise» il recapito, la riga
nel filo e il soffitto -- e non sa da dove vengano. E' la stessa disciplina che
ha reso riusabile `action/actuator.py`, ed e' il motivo per cui questo modulo
si prova per intero con delle finte.

`batti()` non solleva MAI: un guasto su una promessa diventa il suo motivo, e
le altre del giro vengono mantenute lo stesso. Un battito che muore a meta'
lascerebbe promesse `in_corso` che al riavvio diventano fallite -- un difetto
che si vede solo il giorno in cui capita.
"""
from __future__ import annotations

import logging

from ..chat_thread import subject_from_thread
from ..proxy._sanitize import sanitize_ha_value, truncate_with_marker
from .outcome import write_line
from .promise import (
    MAX_SERVICES_PER_PROMISE,
    REASON_CAP,
    TOLLERANZA_S,
    delay_reason,
    delivery_call,
    failure_message,
    kept_message,
    outcome_message,
    push_message,
)

logger = logging.getLogger(__name__)

# Una promessa ORFANA -- nata prima delle promesse divise e mai adottata dal
# proprietario -- non ha un filo: non si sa di chi e'. L'esito resta nella
# riga (e nella pagina, a chi la adotta), ma non si scrive in nessuna chat e
# non si cerca nessun telefono: un filo inventato sarebbe la chat di
# qualcun altro (vincolo 3.2).
_ORPHAN_REASON = ("questa promessa è di prima delle chat divise e non è mai "
                  "stata adottata: non so di chi è, quindi l’esito resta solo "
                  "qui, nella pagina «Impegni».")
# E un `fai` orfano NON agisce (extra 2 del Task 3): un'azione sulla casa a
# scadenza parte a nome di chi l'ha chiesta, e il soffitto di nessuno non si
# puo' rivalutare.
_ORPHAN_FAI_REASON = ("questa promessa è di prima delle chat divise e non è "
                      "mai stata adottata: non so di chi è, e un’azione sulla "
                      "casa non parte a nome di nessuno.")
# Cosa legge la chat quando il battito si rompe su una promessa. Il motivo
# nell'archivio porta il tipo e il testo dell'eccezione (per chi indaga); la
# riga nella chat no -- e' testo interno, e la chat e' di una persona.
_UNEXPECTED_FAILURE = "un guasto imprevisto mentre la mantenevo."
# Il recapito non si e' potuto chiedere (un collaboratore che solleva:
# `recipients_for` per contratto non lo fa, ma il battito non si fida).
_RECIPIENTS_FAILED = "non sono riuscito a sapere a quale telefono mandarlo."


class Sweeper:
    def __init__(self, store, *, execute, interpreta, recipients,
                 write_to_thread, ceiling,
                 tolleranza_s: float = TOLLERANZA_S) -> None:
        """I collaboratori arrivano al montaggio, e l'orologio non sa da dove:

        - `execute(call, *, actor, subject)`: la porta unica (azioni e push);
        - `interpreta(promise)`: il turno di un `chiedi`;
        - `recipients(subject) -> Recipients`: il recapito di chi ha chiesto,
          risolto AL RISVEGLIO (`keeper/recipient.py::recipients_for`);
        - `write_to_thread(thread, content, *, quoted) -> bool`: una riga di
          HIRIS nel filo (`chat_store.append_assistant_line`, che filtra i
          veleni -- anche nel testo del modello citato, `quoted`);
        - `ceiling(subject) -> dict`: il soffitto di chi ha chiesto, riletto
          al risveglio (`api/soffitto.py::ceiling_at_wake`).

        Tutti obbligatori, apposta: un default «niente» farebbe di un
        montaggio dimenticato un esito che non arriva a nessuno, in silenzio.
        """
        self._store = store
        self._execute = execute
        self._interpreta = interpreta
        self._recipients = recipients
        self._write = write_to_thread
        self._ceiling = ceiling
        self._tolleranza = tolleranza_s

    async def batti(self, now: float) -> None:
        for promise in self._store.scadute(now):
            delay = now - promise["quando_ts"]
            # Il controllo del ritardo viene PRIMA della presa: una promessa
            # saltata non deve nemmeno passare per `in_corso`, o un guasto qui
            # in mezzo la lascerebbe fallita invece che saltata, cioe'
            # racconterebbe un'altra storia.
            if delay > self._tolleranza:
                closed = self._store.concludi(
                    promise["id"], state="saltata", reason=delay_reason(delay),
                    now=now)
                logger.info("promessa %s saltata: %s", promise["id"],
                            delay_reason(delay))
                if closed:
                    self._tell(promise,
                               failure_message(promise, delay_reason(delay)))
                continue
            if not self._store.prendi(promise["id"], now=now):
                continue  # qualcun altro l'ha presa: mai due volte
            try:
                await self._keep(promise, now)
            except Exception as error:
                logger.warning("promessa %s: guasto imprevisto (%s: %s)",
                               promise["id"], type(error).__name__, error)
                closed = self._store.concludi(
                    promise["id"], state="fallita", now=now,
                    reason=(
                        f"guasto imprevisto mentre la mantenevo "
                        f"({type(error).__name__}: {error})."
                    ),
                )
                if closed:
                    self._tell(promise,
                               failure_message(promise, _UNEXPECTED_FAILURE))

    def _tell(self, promise: dict, content: str, *,
              quoted: str | None = None) -> bool:
        """Una riga nel filo di chi ha chiesto; `False` se non c'e' filo o la
        riga non e' entrata. `quoted` e' il testo del modello citato dentro
        `content`, che il filtro dei veleni deve vedere da solo. La guardia
        vive in `outcome.write_line`, la stessa delle strade fuori
        dall'orologio: qui si passa solo lo scrittore montato."""
        return write_line(self._write, promise, content, quoted=quoted)

    async def _keep(self, promise: dict, now: float) -> None:
        if promise["specie"] == "fai":
            await self._keep_fai(promise, now)
        else:
            await self._keep_chiedi(promise, now)

    async def _keep_fai(self, promise: dict, now: float) -> None:
        thread = promise.get("thread")
        if thread is None:
            self._store.concludi(promise["id"], state="fallita", now=now,
                                 reason=_ORPHAN_FAI_REASON)
            return
        # La cronaca nomina CHI l'aveva chiesta (ruling 2.7): il soggetto si
        # ricostruisce dal filo della promessa -- specie e id, senza nome.
        subject = subject_from_thread(thread)
        # **Il soffitto si rivaluta al risveglio** (extra 2 del Task 3): alla
        # nascita chi chiedeva poteva comandare, ma in trenta giorni un
        # servizio puo' essere declassato o revocato. Chi oggi non puo'
        # comandare non comanda la casa a scadenza: stesso `perche` di ogni
        # altro rifiuto del soffitto, e la porta non vede niente.
        ceiling = await self._ceiling(subject)
        if not ceiling.get("comandare"):
            reason = ceiling.get("perche") or "oggi non puoi comandare la casa."
            if self._store.concludi(promise["id"], state="fallita", now=now,
                                    reason=reason):
                self._tell(promise, failure_message(promise, reason))
            return
        occurrence = await self._execute(
            promise["chiamata"], actor="schedulatore", subject=subject)
        if occurrence.get("eseguito"):
            # **Il bersaglio e' ancora quello di allora?** (reperto B-6,
            # 22/09/2026). Fra la nascita e adesso possono essere passati
            # trenta giorni, e «le luci di sopra» puo' essere diventata
            # un'altra cosa. Non si rifiuta niente -- l'azione e' gia' andata,
            # ed era una richiesta di chi l'ha chiesta -- si DICHIARA, perche'
            # chi legge l'esito non deve andare a contare.
            #
            # `toccate` viene dall'anteprima che la porta produce gia': non si
            # risolve una seconda volta.
            notice = target_changed(
                promise.get("entities_at_birth"),
                len((occurrence.get("anteprima") or {}).get("toccate") or [])
                if occurrence.get("anteprima") else None)
            closed = self._store.concludi(
                promise["id"], state="mantenuta", now=now,
                execution_id=occurrence.get("esecuzione_id"), reason=notice)
            # Il racconto nel filo (spec §2.4), da campi limitati: la frase
            # tagliata e l'avviso del bersaglio, testo di HIRIS (vincolo 3.7).
            # Nessuna push: un `fai` non ha mai notificato, e l'azione si vede
            # in casa.
            if closed:
                self._tell(promise, kept_message(promise, notice))
        else:
            error = (occurrence.get("errore")
                     or "non e' andata, e non so dire perche'.")
            closed = self._store.concludi(
                promise["id"], state="fallita", now=now, reason=error,
                execution_id=occurrence.get("esecuzione_id"))
            # L'errore viene da Home Assistant (o dalla porta che lo riporta):
            # nella chat entra ripulito come ogni valore di HA, poi tagliato.
            if closed:
                self._tell(promise,
                           failure_message(promise, sanitize_ha_value(error)))

    async def _keep_chiedi(self, promise: dict, now: float) -> None:
        answer = await self._interpreta(promise)
        if answer.get("accodata"):
            # Il turno e' andato al piano: la promessa resta `in_corso` e sara'
            # la sua conclusione a chiuderla, minuti dopo. Qui non c'e' niente
            # da decidere -- e soprattutto non si aspetta: il battito prosegue
            # col resto del giro.
            return
        if "errore" in answer:
            # Il motivo puo' citare cio' che il modello aveva risposto al posto
            # di concludere (`exchange._senza_conclusione`): quella citazione,
            # `excerpt`, passa dal filtro dei veleni da sola.
            if self._store.concludi(promise["id"], state="fallita", now=now,
                                    reason=answer["errore"]):
                self._tell(promise, failure_message(promise, answer["errore"]),
                           quoted=answer.get("excerpt") or None)
            return
        await self.concludi_chiedi(promise, answer, now=now)

    async def concludi_chiedi(self, promise: dict, answer: dict, *,
                              now: float) -> None:
        """Il SECONDO TEMPO di «mantieni»: la conclusione, da qualunque strada arrivi.

        Estratto da `_keep_chiedi` con la fetta «le promesse seguono la
        catena» (22/08/2026). Sul ramo sincrono la conclusione torna dal
        turno e si chiude subito; sul ponte il turno gira altrove e per
        minuti, e a chiamare qui e' la rotta MCP quando il modello ha
        chiamato `conclude`.

        **Un solo punto conclude una promessa**, come `action/actuator.py` e'
        l'unico che esegue: un secondo sarebbe un difetto, non
        un'ottimizzazione -- due strade che decidono se notificare, e con
        quali parole, sono due strade libere di divergere sul gesto piu'
        visibile che il prodotto compie. Dalla fetta «il seguito delle chat
        divise» (spec 2026-09-26 §2.4) qui si decide anche DOVE torna
        l'esito: nel filo di chi l'ha chiesta, e ai suoi telefoni.
        """
        avvisare = bool(answer.get("avvisare"))
        text = answer.get("testo") or ""
        # La nota del ripiego, quando c'e': il turno e' passato dal forfait al
        # consumo, e la promessa e' il posto in cui si legge.
        note = answer.get("nota") or ""

        # Si conclude PRIMA di consegnare: le consegne aspettano la rete, e
        # nel frattempo la promessa deve gia' risultare chiusa -- un secondo
        # `conclude` arrivato in quella finestra la trova non piu' in sospeso
        # e non riconsegna. `concludi` e' guardato sullo stato: se la
        # promessa era gia' conclusa (una scadenza, un `conclude` ripetuto)
        # qui non si consegna niente.
        if not self._store.concludi(promise["id"], state="mantenuta", now=now,
                                    reason=note or None, text=text,
                                    avvisare=avvisare):
            logger.info("promessa %s: gia' conclusa, nessuna consegna",
                        promise["id"])
            return

        if promise.get("thread") is None:
            delivery_reason = _ORPHAN_REASON
        else:
            # L'esito nel filo, sempre: e' la risposta a cio' che quella
            # persona ha chiesto, anche quando la condizione non si e'
            # verificata (`avvisare=false` decide solo se disturbarla).
            self._tell(promise, outcome_message(promise, text), quoted=text)
            delivery_reason = (await self._push(promise, text)
                               if avvisare else None)

        # Il motivo della consegna e la nota del ripiego sono due fatti
        # diversi, e il primo non smette di essere vero perche' e' arrivato il
        # secondo: si accodano.
        # Seconda scrittura, solo il motivo: com'e' andata la consegna si sa
        # dopo la chiusura, e `concludi` (guardato) non riscrive una promessa
        # conclusa.
        if delivery_reason:
            reason = f"{delivery_reason} {note}" if note else delivery_reason
            self._store.set_reason(promise["id"], reason)

    async def _push(self, promise: dict, text: str) -> str | None:
        """Una push a ogni servizio del recapito di chi ha chiesto; il motivo
        da scrivere nella promessa, o `None` se sono arrivate tutte.

        Il recapito si risolve QUI, al risveglio (spec §2.4): se nel frattempo
        la persona si e' collegata in Home Assistant, funziona gia'. Il
        soggetto viene dal filo -- specie e id -- mai dal nome, dal modello o
        dalla vecchia colonna `recapito` (vincolo 3.3).
        """
        subject = subject_from_thread(promise.get("thread"))
        try:
            recipients = await self._recipients(subject)
        except Exception as error:
            logger.warning("promessa %s: recapito non risolto (%s)",
                           promise["id"], type(error).__name__)
            return _RECIPIENTS_FAILED
        # Deduplicati in ordine stabile (extra 5: `recipients_for` gia' non
        # ne produce, qui non ci si fida) e al piu' `MAX_SERVICES_PER_PROMISE`
        # (ruling 3.4): il resto si conta nel log, non si spinge.
        services = list(dict.fromkeys(recipients.services))
        if not services:
            logger.info("promessa %s: nessun servizio a cui notificare",
                        promise["id"])
            return recipients.reason
        if len(services) > MAX_SERVICES_PER_PROMISE:
            logger.warning("promessa %s: %d servizi, ne notifico %d",
                           promise["id"], len(services), MAX_SERVICES_PER_PROMISE)
            services = services[:MAX_SERVICES_PER_PROMISE]

        message = push_message(text)
        failures = []
        for service in services:
            # Ogni push passa dalla porta unica, con la verifica vera
            # (vincolo 3.1). Un servizio che fallisce si DICHIARA e non si
            # devia su un altro (vincolo 3.5): scegliere un ripiego sarebbe
            # decidere al posto di chi ha configurato i suoi dispositivi.
            try:
                occurrence = await self._execute(
                    delivery_call(service, message), actor="schedulatore",
                    subject=subject)
            except Exception as error:
                occurrence = {"eseguito": False, "errore": (
                    f"guasto imprevisto ({type(error).__name__}).")}
            if not occurrence.get("eseguito"):
                error = truncate_with_marker(
                    str(occurrence.get("errore") or "non è arrivata."), REASON_CAP)
                failures.append(f"{service} ({error})")
        # Nei log id e conteggi: il testo e la frase sono di chi ha chiesto
        # (vincolo 3.6).
        logger.info("promessa %s: notifica a %d servizi, %d non arrivate",
                    promise["id"], len(services), len(failures))
        if not failures:
            return None
        return "la notifica non è arrivata a " + "; ".join(failures)


def target_changed(at_birth, now) -> str | None:
    """Se il bersaglio di una promessa non copre piu' le stesse entita', **la
    frase che lo dice** (reperto B-6, 22/09/2026). `None` se non e' cambiato.

    Fra la nascita e il risveglio possono passare trenta giorni: «spegni le
    luci di sopra» puo' essere tre lampadine quando lo prometti e undici quando
    parte -- una stanza nuova, un dispositivo aggiunto -- e chi legge l'esito
    deve poterlo sapere senza andare a contare.

    **Si dichiara in tutti e due i versi.** Piu' entita' e' il caso che
    preoccupa; meno entita' e' il caso che inganna -- una promessa che tocca
    una lampadina invece di tre ha fatto un terzo del lavoro, e tacerlo la fa
    sembrare riuscita.

    Se alla nascita non c'era un numero -- nessun bersaglio da risolvere, o una
    promessa nata prima del 22/09/2026 -- non c'e' niente da confrontare, e
    inventare un avviso sarebbe rumore.
    """
    if at_birth is None or now is None:
        return None
    if int(at_birth) == int(now):
        return None
    return (f"attenzione: quando l’hai promesso il bersaglio copriva "
            f"{at_birth} entità, adesso ne copre {now}. Ho eseguito su "
            "quelle di adesso — se non è ciò che volevi, la casa è cambiata da "
            "quando l’hai chiesto.")
