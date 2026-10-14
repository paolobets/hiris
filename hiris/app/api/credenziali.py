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

**Perche' non bastava il segreto condiviso** (uscito il 22/09/2026). Era uno
solo per tutti i portatori, viveva in `/data`, finiva nei backup di Home
Assistant in chiaro (reperto C-4), e chi lo leggeva una volta era tutti, per
sempre. Una credenziale effimera non si mette in un backup: quando il backup si
apre e' gia' scaduta.

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

#: **Il ruolo che questa credenziale porta al cancello delle rotte**
#: (`admission.gesture_refusal`, Tappa 7): `lettore`, «una macchina che deve
#: misurare senza toccare» (`canali.RUOLI`). Il ponte chiama una rotta sola,
#: `POST /api/mcp`, che legge; cosa si fa DENTRO un turno lo decide il
#: soffitto del suo dispatcher -- quello della persona di un turno di chat,
#: quello del mestiere di un turno di sfondo -- non questa credenziale. Fino al
#: 07/10/2026 la credenziale non portava un ruolo e passava il confine senza
#: domande: le rotte di chi amministra la fermavano una per una
#: (`require_builder`, `_solo_amministratori`), le altre, comprese le
#: scritture della configurazione di HIRIS, no.
RUOLO_TURNO = "lettore"

#: Quanti BYTE casuali chiede a `secrets.token_urlsafe` (il nome dice bit, e
#: sbaglia): un segreto indovinabile non e' un segreto, e un contatore -- o un
#: identificatore di turno -- sarebbe prevedibile.
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


def durata_ponte_s(app) -> float:
    """Quanto vive una credenziale del ponte: il DOPPIO del turno piu' lungo
    ammesso (`ponte.scadenza_min`, letta da `models_store.bridge_deadline_min`).

    Un turno del ponte dura al piu' la sua scadenza, ma il worker ne chiede una
    a ogni giro di sondaggio -- ogni pochi secondi. Una per giro ne lascerebbe
    centinaia vive insieme; una per turno richiederebbe di sapere quando un
    turno comincia, che il worker non sa. Si riusa quindi fino a meta' vita: e
    il doppio e' cio' che fa si' che a meta' vita resti ancora un turno intero.

    Fino al 14/10/2026 erano dieci minuti fissi (`PONTE_S`): il doppio della
    scadenza PREDEFINITA, e meno di un turno quando la pagina Modelli la
    alzava oltre i cinque minuti (S-24). Col predefinito il numero e' lo
    stesso.

    **Cosa non copre, dichiarato.** La scadenza si legge adesso, il turno l'ha
    fissata all'accodamento (`deadline_ts`): un turno accodato prima che la
    scadenza si abbassasse puo' durare piu' di quanto la credenziale di adesso
    copre."""
    from ..models_store import bridge_deadline_min

    return 2 * 60.0 * bridge_deadline_min(app.get("models_config"))


def credenziale_ponte_viva(app, *, adesso: float) -> str:
    """La credenziale del ponte, coniata o riusata.

    Si rinnova a meta' vita e non a scadenza: una credenziale che scade mentre
    un turno la sta usando farebbe fallire quel turno, e un turno fallito per
    una scadenza e' un guasto che nessuno saprebbe leggere. La vita e'
    `durata_ponte_s`: a meta' ne resta un turno intero.
    """
    corrente = app.get("credenziale_ponte")
    if corrente is None:
        return ""
    durata_s = durata_ponte_s(app)
    if corrente.get("scade", 0) - adesso > durata_s / 2:
        return corrente["segreto"]
    segreto = conia(app["credenziali"], mestiere="ponte",
                    durata_s=durata_s, adesso=adesso)
    corrente["segreto"] = segreto
    corrente["scade"] = adesso + durata_s
    return segreto
