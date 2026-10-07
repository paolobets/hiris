"""La consegna di una push: un testo a ogni servizio di un recapito, dalla
porta unica dei servizi (`action/actuator.py`).

Due chiamanti, una regola: l'esito di una promessa a chi l'ha chiesta
(`sweeper.Sweeper._push`) e l'avviso agli amministratori per una proposta
`alto` del proponente (`notify_admins`; D14 del piano degli attori, strati
3-4, approvata dal proprietario il 06/10/2026). Fino a quel giorno il ciclo
viveva solo nell'orologio delle promesse; scriverne un secondo per l'avviso
sarebbe stato il doppione che la fondamenta 2 vieta.

**Il servizio lo sceglie il sistema, mai il modello**: arriva dal recapito
(`recipient.recipients_for`), e la chiamata ha la forma unica di
`promise.delivery_call`.
"""
from __future__ import annotations

import logging

from ..proxy._sanitize import truncate_with_marker
from .promise import MAX_SERVICES_PER_PROMISE, REASON_CAP, delivery_call, push_message
from .recipient import recipients_for

logger = logging.getLogger(__name__)


async def deliver(services, text, *, execute, actor: str,
                  subject: dict | None) -> tuple[int, list[str]]:
    """Una push a ogni servizio, nell'ordine, al piu' `MAX_SERVICES_PER_PROMISE`.

    Torna `(quanti, mancate)`: quante push sono partite verso la porta, e per
    ognuna che non e' arrivata la riga `servizio (motivo)`. Non solleva: un
    servizio che fallisce si DICHIARA e non si devia su un altro (vincolo 3.5
    della spec delle promesse) -- scegliere un ripiego sarebbe decidere al
    posto di chi ha configurato i suoi dispositivi.
    """
    # Deduplicati in ordine stabile (extra 5: `recipients_for` gia' non ne
    # produce, qui non ci si fida) e al piu' `MAX_SERVICES_PER_PROMISE`
    # (ruling 3.4): il resto si conta nel log, non si spinge.
    unique = list(dict.fromkeys(services))
    if len(unique) > MAX_SERVICES_PER_PROMISE:
        logger.warning("consegna: %d servizi, ne notifico %d",
                       len(unique), MAX_SERVICES_PER_PROMISE)
        unique = unique[:MAX_SERVICES_PER_PROMISE]
    message = push_message(text)
    failures = []
    for service in unique:
        # Ogni push passa dalla porta unica, con la verifica vera (vincolo 3.1).
        try:
            occurrence = await execute(delivery_call(service, message),
                                       actor=actor, subject=subject)
        except Exception as error:
            occurrence = {"eseguito": False, "errore": (
                f"guasto imprevisto ({type(error).__name__}).")}
        if not occurrence.get("eseguito"):
            error = truncate_with_marker(
                str(occurrence.get("errore") or "non è arrivata."), REASON_CAP)
            failures.append(f"{service} ({error})")
    return len(unique), failures


async def notify_admins(app, text: str, *, actor: str) -> dict:
    """L'avviso a chi amministra la casa (D14): una push a ogni amministratore
    di Home Assistant, sui suoi telefoni.

    Chi amministra lo dice Home Assistant (`api/soffitto.administrators`, la
    stessa lettura del cancello al confine); i telefoni li dice il recapito
    delle promesse, persona per persona. Torna il resoconto
    `{"amministratori", "push", "mancate"}`, o `{"errore"}` quando non si sa
    chi amministra. Non solleva: chi avvisa e' un giro che deve continuare.
    """
    from ..api.soffitto import administrators

    actuator = app.get("action_actuator")
    if actuator is None:
        return {"errore": "nessuna porta dei servizi montata"}
    admins = await administrators(app)
    if admins is None:
        logger.warning("avviso agli amministratori: non so chi sono "
                       "(utenti di Home Assistant non letti)")
        return {"errore": "utenti di Home Assistant non letti"}
    sent, failures, unreachable = 0, [], []
    for subject in admins:
        try:
            recipients = await recipients_for(subject, app.get("ha_client"),
                                              app.get("service_registry"))
        except Exception as error:
            unreachable.append(f"{subject['id']} ({type(error).__name__})")
            continue
        if not recipients.services:
            unreachable.append(f"{subject['id']} ({recipients.reason})")
            continue
        count, missed = await deliver(recipients.services, text,
                                      execute=actuator.execute, actor=actor,
                                      subject=subject)
        sent += count
        failures.extend(missed)
    # Nei log id e conteggi, mai il testo: e' la proposta, non un fatto del
    # registro (vincolo 3.6 delle promesse).
    logger.info("avviso agli amministratori: %d amministratori, %d push, %d non "
                "arrivate, %d senza telefono", len(admins), sent, len(failures),
                len(unreachable))
    return {"amministratori": len(admins), "push": sent,
            "mancate": failures, "senza_telefono": unreachable}
