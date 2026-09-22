"""I canali esterni e la loro credenziale (spec 2026-09-21 «i canali e i ruoli»).

Fino al 21/09/2026 quattro portatori -- il ponte, il gateway MCP su un'altra
macchina, il proxy di Retro Panel e la porta di sviluppo -- presentavano **lo
stesso segreto condiviso**. Un segreto condiviso non e' un'identita': e' una
parola d'ordine, e chi la sente una volta e' tutti. Compromessa una qualunque
delle quattro strade, l'unica mossa era cambiare il token e romperle tutte
insieme -- e nessun registro poteva dire QUALE integrazione avesse chiamato.

**Il 22/09/2026 quel segreto e' uscito del tutto** (fetta 3 dello sprint
sicurezza). La convivenza doveva finire su una MISURA e non su una data, ed e'
finita cosi': il registro dell'add-on ha smesso di nominare chiunque non
firmasse.

**Perche' una coppia di chiavi e non un secondo segreto** (spec §6). `/data`
finisce nei backup di Home Assistant, in chiaro se l'utente non gli mette una
password (reperto C-4 del registro dei rischi). Con un segreto per canale, chi
legge un backup impersona quel canale; con una chiave **pubblica** non ottiene
niente, perche' qui non c'e' nessuna chiave che serva a firmare. E' questa la
differenza fra «segreto» e «non falsificabile».

**La firma copre la richiesta, non l'identita'**: metodo, percorso, momento,
valore irripetibile, impronta del corpo. Firmare la sola identita' lascerebbe
cambiare cio' che la richiesta chiede tenendo buona la firma, e lascerebbe
valere per una scrittura una firma nata per una lettura.

**Tre posti, separati apposta** (spec §7): la chiave pubblica e il ruolo stanno
nelle opzioni dell'add-on, perche' sono la decisione del proprietario su quel
dispositivo; **che il canale esista** sta qui nel codice. Un nome non dichiarato
e' rifiutato anche con una firma perfetta, cosi' aggiungere un'integrazione
costringe a decidere il suo perimetro invece di fargli ereditare tutto.

**Cosa questa credenziale NON fa**: non sostituisce TLS e non lo finge. Risponde
a *chi sei* e *questa richiesta e' intatta*, non a *chi puo' leggerla*.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger(__name__)

#: Quanto puo' essere lontano il momento di una richiesta, in entrambi i versi.
#:
#: **In entrambi**, e non solo nel passato: guardare solo indietro lascerebbe
#: che un orologio avanti di un'ora allarghi la finestra di un'ora, cioe'
#: lascerebbe **al chiamante** il compito di deciderla.
FINESTRA_S = 30.0

#: Il vocabolario dei ruoli, e **non e' nostro**: `amministratore` e `utente`
#: sono cio' che Home Assistant chiama admin e non-admin, cosi' chi conosce HA
#: non deve imparare un secondo sistema. `lettore` e' il terzo e serve a un caso
#: che HA non ha: una macchina che deve **misurare senza toccare**.
RUOLI = ("amministratore", "utente", "lettore")

#: Cosa concede ogni ruolo. `utente` e' quello che il proprietario ha descritto
#: il 21/09: «cosi' non gestisce automazioni e altro, quindi comanda».
#:
#: `costruire` e' la sola cosa riservata, e non i servizi di sistema: quelli
#: sono gia' irraggiungibili dalla porta perche' non dichiarano un bersaglio, e
#: un bersaglio vuoto e' sempre un rifiuto (`action/verification.py`).
PUO = {
    "amministratore": {"leggere": True, "comandare": True, "costruire": True},
    "utente": {"leggere": True, "comandare": True, "costruire": False},
    "lettore": {"leggere": True, "comandare": False, "costruire": False},
}

#: I metodi che non cambiano niente. Un `lettore` fa questi e basta.
_SICURI = frozenset({"GET", "HEAD", "OPTIONS"})

#: Che cosa e' un servizio a cui nessuno ha scritto la specie. **Una macchina**,
#: che e' il caso comune e quello che concede meno: un `luogo` dice alla cronaca
#: che la richiesta viene da un posto della casa, e affermarlo senza saperlo
#: sarebbe scrivere nella cronaca una cosa non vera.
SPECIE_IGNOTA = "integrazione"


def materia_firmata(metodo: str, percorso: str, momento: float, unico: str,
                    corpo: bytes) -> bytes:
    """Cosa si firma — il contratto fra chi firma e chi verifica.

    Scritto **una volta sola**: se le due parti divergessero, ogni firma
    legittima verrebbe rifiutata e nessuno capirebbe perché.

    Il momento si scrive come intero di secondi, non come decimale: due
    linguaggi diversi formattano un decimale in modi diversi, e la firma
    fallirebbe per una cifra.
    """
    return "\n".join((
        str(metodo).upper(),
        str(percorso),
        str(int(momento)),
        str(unico),
        hashlib.sha256(corpo or b"").hexdigest(),
    )).encode("utf-8")


def consente_metodo(ruolo: str, metodo: str) -> bool:
    """Se quel ruolo può usare quel metodo HTTP.

    Il verso del dubbio: un ruolo sconosciuto nega tutto. Una parola nuova non
    è un permesso — è un ruolo su cui nessuno ha deciso.
    """
    puo = PUO.get(ruolo)
    if puo is None:
        return False
    return True if puo["comandare"] else str(metodo).upper() in _SICURI


def _chiave(grezza: str) -> Ed25519PublicKey | None:
    """La chiave pubblica dal testo che il proprietario ha incollato.

    Torna `None` invece di sollevare: prima o poi qualcuno incollerà male, e un
    errore di battitura nella pagina del Supervisor non deve spegnere l'add-on.
    """
    try:
        return Ed25519PublicKey.from_public_bytes(
            base64.b64decode(str(grezza or ""), validate=True))
    except Exception:
        return None


def _pota(visti: dict, adesso: float) -> None:
    """I valori irripetibili fuori dalla finestra non servono più a nessuno.

    Senza questa riga sarebbe una perdita di memoria su un percorso che gira a
    ogni richiesta; e un valore scaduto non può comunque passare, perché il suo
    momento è già fuori finestra.
    """
    for unico in [u for u, quando in visti.items()
                  if adesso - quando > FINESTRA_S * 2]:
        del visti[unico]


def riconosci(*, chiave: str, momento, unico: str, firma: str, metodo: str,
              percorso: str, corpo: bytes, servizi, visti: dict,
              adesso: float) -> tuple[dict | None, str | None]:
    """Quale servizio ha firmato, se la firma regge — `({servizio, ruolo, specie}, None)`.

    Si chiama «riconosci» e non «verifica» perché **torna un'identità**, non un
    sì o un no: chi legge il nome deve sapere che a valle avrà un soggetto, non
    un booleano.

    Torna `servizio` e non `canale`: il canale è la strada, il servizio è chi ci
    parla dentro, e chiamarli con la stessa parola li farebbe confondere al
    primo lettore nuovo.

    **Ogni rifiuto dice cosa manca**: la chiave non appartiene a un servizio
    autorizzato; il servizio non ha un ruolo valido; il momento è fuori
    finestra; il valore irripetibile è già stato servito; la firma non regge.
    Un rifiuto che non dice cosa fare è un ordine.
    """
    # **Un servizio si identifica con la sua chiave pubblica**, che e' la sua
    # identita': un nome sarebbe una seconda rappresentazione dello stesso
    # fatto, e due rappresentazioni divergono. Il nome resta, ma e' un'etichetta
    # per il proprietario -- non serve a riconoscere nessuno.
    #
    # E **lo dice l'archivio, non un elenco nel codice**: dal 22/09/2026 un
    # servizio esiste quando il proprietario l'ha approvato, e l'approvazione
    # E' la dichiarazione. Un rilascio non c'entra piu' niente.
    autorizzato = servizi.autorizzato(chiave) if servizi is not None else None
    if autorizzato is None:
        return None, ("questa chiave non appartiene a nessun servizio "
                      "autorizzato: presentati quando il proprietario apre "
                      "l’accoppiamento, e fatti approvare")
    ruolo = autorizzato.get("ruolo")
    if ruolo not in RUOLI:
        return None, (f"il servizio ha il ruolo {ruolo!r}, che non esiste: i "
                      f"ruoli sono {', '.join(RUOLI)}")

    try:
        quando = float(momento)
    except (TypeError, ValueError):
        return None, "il momento della richiesta non è un numero"
    if abs(adesso - quando) > FINESTRA_S:
        return None, ("il momento della richiesta è troppo lontano da adesso: "
                      f"la finestra è di {int(FINESTRA_S)} secondi, in entrambi "
                      "i versi")

    _pota(visti, adesso)
    if not str(unico or "").strip():
        return None, "manca il valore irripetibile della richiesta"
    if unico in visti:
        return None, ("questa richiesta è già stata servita: un valore "
                      "irripetibile vale una volta sola")

    pubblica = _chiave(chiave)
    if pubblica is None:
        return None, ("la chiave pubblica non si legge: dev’essere una chiave "
                      "Ed25519 in base64")

    try:
        pubblica.verify(base64.b64decode(str(firma or ""), validate=True),
                      materia_firmata(metodo, percorso, quando, unico, corpo))
    except InvalidSignature:
        return None, "la firma non corrisponde a questa richiesta"
    except Exception:
        # Base64 storto, lunghezza sbagliata, tipo inatteso: sul percorso di
        # ogni richiesta un'eccezione spegnerebbe l'add-on invece di negare un
        # accesso.
        return None, "la firma non si è potuta leggere"

    visti[unico] = adesso
    return {"servizio": autorizzato["nome"], "ruolo": ruolo,
            "specie": autorizzato.get("specie") or SPECIE_IGNOTA}, None


def prepara_canali(app) -> None:
    """Il contenitore dei valori gia' visti nasce quando l'app si compone.

    Non c'e' piu' nessuna registrazione da leggere: dal 22/09/2026 i servizi
    vivono nell'archivio (`api/servizi.py`) e nascono da un accoppiamento
    approvato dal proprietario, non da un campo di testo nelle opzioni.
    """
    app["canali_visti"] = {}
