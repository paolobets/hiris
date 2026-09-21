"""I canali esterni e la loro credenziale (spec 2026-09-21 «i canali e i ruoli»).

Fino al 21/09/2026 quattro portatori -- il ponte, il gateway MCP su un'altra
macchina, il proxy di Retro Panel e la porta di sviluppo -- presentavano **lo
stesso segreto condiviso**. Un segreto condiviso non e' un'identita': e' una
parola d'ordine, e chi la sente una volta e' tutti. Compromessa una qualunque
delle quattro strade, l'unica mossa era cambiare il token e romperle tutte
insieme -- e nessun registro poteva dire QUALE integrazione avesse chiamato.

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
import datetime
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

#: Il LIMITE della convivenza col token condiviso (spec §8).
#:
#: Non e' la sua fine: la fine la decide una **misura** -- quando la riga
#: «convivenza:» del registro tace per qualche giorno, il ripiego esce. Questa
#: data garantisce che non si chiuda mai DOPO, perche' un ripiego del genere
#: non si rompe, si dimentica: fra sei mesi sarebbe ancora li', accanto alla
#: difesa che avrebbe dovuto sostituirlo.
#:
#: Quando il cancello che la custodisce diventa rosso, la risposta non e'
#: spostarla: e' guardare il registro.
CONVIVENZA_SCADENZA = datetime.date(2026, 10, 31)

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

#: I canali che ESISTONO. Il ruolo e la chiave li mette il proprietario nelle
#: opzioni; che un nome sia un canale lo decide questo elenco, ed e' una lista
#: di **ammissione**: non ricopia niente, enuncia il cancello.
CANALI = {
    "sviluppo": {
        "specie": "integrazione",
        "perche": ("la porta 8099, aperta solo durante una diagnostica: serve a "
                   "misurare la casa vera prima di progettare, che è il metodo "
                   "di questo prodotto. Il proprietario le ha dato il ruolo "
                   "«lettore» il 21/09/2026: legge, non comanda"),
    },
    "gateway": {
        "specie": "integrazione",
        "perche": ("il gateway MCP su un'altra macchina, che porta a HIRIS le "
                   "richieste di un client esterno: è fuori dal perimetro "
                   "dell'add-on, quindi il rischio lì non è l'utente ma chi si "
                   "mette in mezzo"),
    },
    "retropanel": {
        "specie": "luogo",
        "perche": ("il pannello fisico di casa: nessuno si autentica davanti a "
                   "un pannello in corridoio, ma si sa DOVE è — ed è "
                   "un'informazione vera, diversa da «anonimo»"),
    },
}

#: I metodi che non cambiano niente. Un `lettore` fa questi e basta.
_SICURI = frozenset({"GET", "HEAD", "OPTIONS"})


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


def leggi_registrazioni(testo: str | None) -> dict[str, dict]:
    """Le registrazioni dalle opzioni dell'add-on: `nome:ruolo:chiave`, una per riga.

    Una riga storta **si salta e non ferma le altre**: sarebbe un errore di
    battitura che spegne un'integrazione che non c'entra. Ma si dichiara nel
    registro, perché una riga saltata in silenzio è indistinguibile da una riga
    che non è mai stata scritta.
    """
    lette: dict[str, dict] = {}
    for riga in (testo or "").splitlines():
        pulita = riga.strip()
        if not pulita or pulita.startswith("#"):
            continue
        pezzi = pulita.split(":", 2)
        if len(pezzi) != 3 or not all(p.strip() for p in pezzi):
            logger.warning(
                "canali: la riga %r non ha la forma «nome:ruolo:chiave» — "
                "saltata, le altre restano", pulita[:40])
            continue
        nome, ruolo, chiave = (p.strip() for p in pezzi)
        lette[nome] = {"ruolo": ruolo, "chiave": chiave}
    return lette


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


def riconosci(*, canale: str, momento, unico: str, firma: str, metodo: str,
              percorso: str, corpo: bytes, registrate: dict, visti: dict,
              adesso: float) -> tuple[dict | None, str | None]:
    """Chi è questo canale, se la sua firma regge — `({canale, ruolo, specie}, None)`.

    Si chiama «riconosci» e non «verifica» perché **torna un'identità**, non un
    sì o un no: chi legge il nome deve sapere che a valle avrà un soggetto, non
    un booleano.

    **Tre rifiuti, e ognuno dice quale dei tre manca**: il canale non è
    dichiarato nel codice; non ha una registrazione; la registrazione non ha un
    ruolo valido. Un rifiuto che non dice cosa fare è un ordine.
    """
    dichiarato = CANALI.get(str(canale or ""))
    if dichiarato is None:
        return None, (f"«{canale}» non è un canale dichiarato: una firma valida "
                      "non basta, il perimetro di un'integrazione si decide "
                      "prima di darle accesso")

    riga = registrate.get(canale)
    if not riga:
        return None, (f"«{canale}» è dichiarato ma non registrato: manca la sua "
                      "chiave pubblica nelle opzioni dell’add-on")

    ruolo = riga.get("ruolo")
    if ruolo not in RUOLI:
        return None, (f"«{canale}» ha il ruolo {ruolo!r}, che non esiste: i "
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

    chiave = _chiave(riga.get("chiave"))
    if chiave is None:
        return None, (f"la chiave pubblica di «{canale}» non si legge: "
                      "dev’essere una chiave Ed25519 in base64")

    try:
        chiave.verify(base64.b64decode(str(firma or ""), validate=True),
                      materia_firmata(metodo, percorso, quando, unico, corpo))
    except InvalidSignature:
        return None, "la firma non corrisponde a questa richiesta"
    except Exception:
        # Base64 storto, lunghezza sbagliata, tipo inatteso: sul percorso di
        # ogni richiesta un'eccezione spegnerebbe l'add-on invece di negare un
        # accesso.
        return None, "la firma non si è potuta leggere"

    visti[unico] = adesso
    return {"canale": canale, "ruolo": ruolo,
            "specie": dichiarato["specie"]}, None


def prepara_canali(app) -> None:
    """I contenitori dei canali nascono quando l'app si compone.

    Scrivere in `app[...]` a richiesta già servita è deprecato in aiohttp 3 e un
    errore in aiohttp 4 — la stessa ragione per cui nascono qui i contatori dei
    giri di strumento e la cache dei ruoli.
    """
    app["canali_visti"] = {}
    app["canali_registrati"] = leggi_registrazioni(app.get("canali_testo"))
    if app["canali_registrati"]:
        logger.info("canali: registrati %s",
                    ", ".join(f"{n} ({r['ruolo']})"
                              for n, r in sorted(app["canali_registrati"].items())))

