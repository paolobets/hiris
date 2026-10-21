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

**L'avviso si rilegge in Home Assistant** (richiesta del proprietario del
21/10/2026: la push toccata apre Home Assistant e sparisce, e il testo non si
ritrova piu'). Accanto alla push, chi avvisa tiene una notifica persistente
che dice com'e' la casa adesso (`align_notices`). Proposta:
`/mnt/project-files/analisi/2026-10-21-avvisi-persistenti-proposta.md`.
"""
from __future__ import annotations

import logging

from ..action.actuator import ACTUATOR_KEY
from ..action.registry import SERVICE_REGISTRY_KEY
from ..proxy._sanitize import truncate_with_marker
from ..proxy.ha_client import HA_CLIENT_KEY, notification_fingerprint
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
        # Il motivo e' quello della porta (Tappa 7 T1): il rifiuto di Home
        # Assistant col suo testo, o il guasto di trasporto detto come tale.
        # Un'eccezione non e' un esito della porta, e non se ne fabbrica uno.
        try:
            occurrence = await execute(delivery_call(service, message),
                                       actor=actor, subject=subject)
        except Exception as error:
            failures.append(f"{service} (guasto imprevisto: {type(error).__name__})")
            continue
        if not occurrence.get("eseguito"):
            error = truncate_with_marker(
                str(occurrence.get("errore") or "non è arrivata."), REASON_CAP)
            failures.append(f"{service} ({error})")
    return len(unique), failures


def arrived(report: dict) -> bool:
    """Se l'avviso di `notify_admins` e' arrivato ad almeno un telefono: una
    push partita e non mancata. `{"errore"}`, nessun telefono o tutte mancate
    non lo sono, e chi avvisa ritenta al giro dopo."""
    return report.get("push", 0) > len(report.get("mancate") or ())


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

    actuator = app.get(ACTUATOR_KEY)
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
            recipients = await recipients_for(subject, app.get(HA_CLIENT_KEY),
                                              app.get(SERVICE_REGISTRY_KEY))
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


#: La riga in fondo alla push quando la notifica persistente c'e': il tocco
#: apre Home Assistant e la push sparisce, e chi la legge sa dove ritrovarla.
#: Nessun `url` al tocco: non c'e' una rotta che apra il pannello delle
#: notifiche (documentazione dell'app Companion, letta il 21/10/2026).
NOTICE_HINT = "Lo trovi anche fra le notifiche di Home Assistant."


def notice_call(notice_id: str, title: str, text: str) -> dict:
    """La chiamata che scrive una notifica persistente, o la riscrive: con un
    `notification_id` gia' presente Home Assistant la SOSTITUISCE (evento
    `UPDATED`, letto in `persistent_notification/helpers.py` al tag 2026.9.4),
    quindi un id stabile non fa mai doppioni."""
    return {"servizio": "persistent_notification.create", "bersaglio": {},
            "dati": {"notification_id": notice_id, "title": title, "message": text}}


def withdrawal_call(notice_id: str) -> dict:
    """La chiamata che toglie una notifica persistente."""
    return {"servizio": "persistent_notification.dismiss", "bersaglio": {},
            "dati": {"notification_id": notice_id}}


async def align_notices(app, family: str, wanted: dict[str, tuple[str, str]], *,
                        actor: str) -> dict:
    """Le notifiche persistenti di una famiglia, allineate a `wanted`.

    `family` e' l'inizio degli id che chi chiama possiede
    (`hiris_stopped_integrations`, `hiris_proposal_`); `wanted` sono le
    notifiche che devono esserci, `{id: (titolo, testo)}`, ognuna con un id
    della famiglia. Quelle di Home Assistant con un id della famiglia che
    `wanted` non nomina si tolgono; quelle di `wanted` che mancano, o che
    dicono altro, si scrivono. Le altre non si toccano: una notifica gia'
    giusta non costa una riga di cronaca.

    **Cio' che c'e' lo dice Home Assistant**, a ogni chiamata
    (`HAClient.persistent_notifications`), e non un ricordo di HIRIS: le
    notifiche vivono solo nella memoria di Home Assistant, e un suo riavvio le
    cancella. Cosi' tornano al giro dopo il riavvio, senza un gancio che lo
    aspetti.

    Ogni scrittura passa dalla porta dei servizi (`actuator.execute`), come la
    push. Torna `{"allineate": [id], "mancate": ["id (motivo)"]}`, o
    `{"errore"}` quando non si sa cosa Home Assistant mostra: allora non si
    tocca niente. Non solleva per cio' che risponde Home Assistant: chi
    avvisa e' un giro che deve continuare. Solleva per un id di `wanted` fuori
    dalla famiglia, che non si toglierebbe mai: e' un errore di chi chiama,
    non un esito.
    """
    stray = [notice_id for notice_id in wanted if not notice_id.startswith(family)]
    if stray:
        raise ValueError(f"id fuori dalla famiglia {family!r}: {stray}")
    actuator = app.get(ACTUATOR_KEY)
    ha = app.get(HA_CLIENT_KEY)
    if actuator is None or ha is None:
        return {"errore": "nessuna porta dei servizi montata"}
    shown = await ha.persistent_notifications()
    if "errore" in shown:
        logger.warning("notifiche persistenti: non so cosa mostra Home Assistant "
                       "(%s) -- non tocco niente", shown["errore"])
        return {"errore": shown["errore"]}
    shown = shown["notifiche"]
    calls = [withdrawal_call(notice_id) for notice_id in shown
             if notice_id.startswith(family) and notice_id not in wanted]
    aligned = [notice_id for notice_id, (title, text) in wanted.items()
               if shown.get(notice_id) == notification_fingerprint(title, text)]
    calls += [notice_call(notice_id, title, text)
              for notice_id, (title, text) in wanted.items() if notice_id not in aligned]
    failures = []
    for call in calls:
        notice_id = call["dati"]["notification_id"]
        try:
            occurrence = await actuator.execute(call, actor=actor)
        except Exception as error:
            failures.append(f"{notice_id} (guasto imprevisto: {type(error).__name__})")
            continue
        if occurrence.get("eseguito"):
            aligned.append(notice_id)
        else:
            error = truncate_with_marker(
                str(occurrence.get("errore") or "non è arrivata."), REASON_CAP)
            failures.append(f"{notice_id} ({error})")
    if calls:
        logger.info("notifiche persistenti %s: %d chiamate, %d non riuscite",
                    family, len(calls), len(failures))
    return {"allineate": aligned, "mancate": failures}
