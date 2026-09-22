"""Le credenziali EFFIMERE (spec 2026-09-21 «i canali e i ruoli», §5).

Il ponte non e' un canale di rete: gira **dentro il container**. Dargli una
coppia di chiavi a vita lunga rimetterebbe una chiave nella riga di comando del
sottoprocesso -- il reperto C-3 del registro dei rischi, leggibile per trecento
secondi da qualunque processo. Per lui la risposta e' un'altra: **una
credenziale che vale per quel turno e per niente altro**.

Due portatori, meno esotici di come sembrano:

- il **worker**, che e' HIRIS che chiama se stesso su `127.0.0.1` per prendere
  e consegnare i turni;
- il **sottoprocesso `claude`**, che chiama `/api/mcp` con cio' che gli arriva
  in `--mcp-config`.

Entrambi vivono quanto un turno, quindi la credenziale muore col turno -- e cio'
che resta nella riga di comando dopo non apre piu' niente.

**Perche' non basta il segreto condiviso.** Quello e' uno solo per tutti i
portatori, vive in `/data`, finisce nei backup di Home Assistant in chiaro
(reperto C-4), e chi lo legge una volta e' tutti, per sempre. Una credenziale
effimera non si mette in un backup: quando il backup si apre e' gia' scaduta.

**Perche' qui un segreto al portatore va bene, e per i canali no.** Un canale
esterno vive su un'altra macchina e la sua credenziale deve sopravvivere a
riavvii e a backup: li' serve una chiave che HIRIS non possieda. Il ponte vive
nello stesso processo che conia, per il tempo di un turno: il segreto non
attraversa nessun confine che non attraversi gia' il resto.
"""
from __future__ import annotations

import hmac
import logging
import secrets

logger = logging.getLogger(__name__)

#: Quanti bit. Gli stessi del token interno: un segreto indovinabile non e' un
#: segreto, e un contatore -- o un identificatore di turno -- sarebbe prevedibile.
_BIT = 32


def conia(vive: dict, *, mestiere: str, durata_s: float, adesso: float) -> str:
    """Una credenziale nuova per quel mestiere, valida per `durata_s` secondi.

    Le scadute si potano qui: chi conia e' anche chi passa piu' spesso, e il
    worker ne chiede una a ogni giro. Tenerle per sempre sarebbe una perdita di
    memoria su un percorso che gira ogni pochi secondi.
    """
    _pota(vive, adesso)
    segreto = secrets.token_urlsafe(_BIT)
    vive[segreto] = {"mestiere": mestiere, "scade": adesso + float(durata_s)}
    return segreto


def riconosci(vive: dict, segreto: str | None, *, adesso: float) -> dict | None:
    """Cosa apre questa credenziale — o `None` se non apre niente.

    Il confronto è **a tempo costante**: uscire al primo carattere diverso
    direbbe quanto ci si è avvicinati, e con abbastanza tentativi il segreto si
    ricostruisce.
    """
    if not segreto:
        return None
    for candidato, riga in list(vive.items()):
        if hmac.compare_digest(candidato, str(segreto)):
            return None if riga["scade"] <= adesso else riga
    return None


def revoca(vive: dict, *, mestiere: str) -> int:
    """Spegne tutte le credenziali di un mestiere, subito.

    Quando il ponte si spegne il suo accesso deve spegnersi con lui: aspettare
    la scadenza vorrebbe dire che spegnere il ponte non spegne davvero niente.
    """
    scadute = [s for s, riga in vive.items() if riga["mestiere"] == mestiere]
    for s in scadute:
        del vive[s]
    return len(scadute)


def _pota(vive: dict, adesso: float) -> None:
    for segreto in [s for s, riga in vive.items() if riga["scade"] <= adesso]:
        del vive[segreto]


def prepara_credenziali(app) -> None:
    """Il contenitore nasce quando l'app si compone, non alla prima richiesta.

    Scrivere in `app[...]` a richiesta già servita è deprecato in aiohttp 3 e un
    errore in aiohttp 4 — la stessa ragione per cui nascono lì i contatori dei
    giri di strumento, la cache dei ruoli e i valori già visti dei canali.
    """
    app["credenziali"] = {}
    # La credenziale del ponte IN CORSO. Sta in un contenitore suo perche' il
    # worker ne chiede una a ogni giro (ogni pochi secondi) e coniarne una
    # nuova ogni volta ne lascerebbe centinaia vive insieme: si riusa finche'
    # e' a meta' vita, e si rinnova dopo.
    app["credenziale_ponte"] = {}


#: Quanto vive una credenziale del ponte, e perche' non e' «un turno esatto».
#:
#: Un turno del ponte dura minuti, ma il worker ne chiede una a ogni giro di
#: sondaggio -- ogni pochi secondi. Una per giro ne lascerebbe centinaia vive
#: insieme; una per turno richiederebbe di sapere quando un turno comincia, che
#: il worker non sa. Dieci minuti e' il compromesso: piu' della scadenza di un
#: turno del ponte (`ponte.bridge_deadline_min`, dieci di default) e infinitamente
#: meno di «per sempre», che e' cio' che era prima.
PONTE_S = 600.0


def credenziale_ponte_viva(app, *, adesso: float) -> str:
    """La credenziale del ponte, coniata o riusata.

    Si rinnova a meta' vita e non a scadenza: una credenziale che scade mentre
    un turno la sta usando farebbe fallire quel turno, e un turno fallito per
    una scadenza e' un guasto che nessuno saprebbe leggere.
    """
    corrente = app.get("credenziale_ponte")
    if corrente is None:
        return ""
    if corrente.get("scade", 0) - adesso > PONTE_S / 2:
        return corrente["segreto"]
    segreto = conia(app["credenziali"], mestiere="ponte",
                    durata_s=PONTE_S, adesso=adesso)
    corrente["segreto"] = segreto
    corrente["scade"] = adesso + PONTE_S
    return segreto
