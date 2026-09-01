"""Il token interno dell'add-on: generato quando l'utente lascia vuota l'opzione.

**Perche' questo file esiste.** `hiris/config.yaml` ha `internal_token: ""` come
default, e le descrizioni dell'opzione promettevano per iscritto «Lascia vuoto
per generarlo automaticamente» -- ma **nessuno nel repo generava niente**.
Risultato, con la configurazione predefinita: `run.sh` esportava
`INTERNAL_TOKEN=""`, `server.py` lo metteva in `app["internal_token"]`, e
`middleware_internal_auth` negava con 401 **ogni** richiesta non-ingress
(rifiuto-per-default). L'unico componente del prodotto che chiama la propria
API in modo non-ingress e' il worker del ponte della chat
(`agent/runner.py::build_headers`, che legge `os.environ["INTERNAL_TOKEN"]`):
il suo `claim` falliva con 401 ogni ~3 secondi all'infinito, la CLI `claude`
non veniva invocata mai, e dopo la scadenza l'utente leggeva solo «La risposta
non e' arrivata in tempo. Riprova.» -- indistinguibile da un problema di rete.

**Cosa fa ora il prodotto**, cioe' cio' che gia' prometteva: se il campo e'
vuoto genera un segreto con `secrets` della libreria standard e lo **conserva
in `/data`** (`HIRIS_DATA_DIR`), cosi' che **sopravviva ai riavvii** -- un token
diverso a ogni boot invaliderebbe i lavori gia' in coda, che vengono claimati
dopo il riavvio.

**Cio' che NON cambia:** il rifiuto-per-default. Il token dell'utente vince
sempre; e se generare o scrivere fallisce **non si degrada in «nessun token»
aperto**: si dichiara l'errore nel log e si continua a negare (si torna `""`,
che per il middleware significa 401 su tutto cio' che non e' ingress). Meglio
rotto e detto che aperto e taciuto.

**Il valore del token non finisce MAI nel log** -- ne' quello generato, ne'
quello riletto, ne' quello configurato a mano.
"""
from __future__ import annotations

import logging
import os
import secrets

logger = logging.getLogger(__name__)

# Il nome del file dentro la directory dei dati dell'add-on (`/data` in
# produzione). Sta li' e non in `/config` perche' `/data` e' privato
# dell'add-on e persiste fra i riavvii e gli aggiornamenti.
TOKEN_FILE_NAME = "internal_token"

# 32 byte di entropia da `secrets.token_urlsafe` -> 256 bit, resi in ~43
# caratteri URL-safe. Robustezza adeguata a un segreto condiviso: il confronto
# a valle e' `hmac.compare_digest`, quindi la lunghezza non e' un problema.
ENTROPY_BYTES = 32

# Permessi del file: solo il proprietario legge e scrive. Su Linux (la
# piattaforma dell'add-on) e' esattamente 0600; su Windows -- dove gira solo la
# suite di test -- il bit di gruppo/altri non esiste e la chiamata incide di
# fatto solo sul flag di sola-lettura: e' il piu' stretto possibile *su questa
# piattaforma*, non un'illusione di isolamento.
FILE_PERMISSIONS = 0o600


# fetta "il ponte riceve gli strumenti" (parita' B, Task 3, fix round 2):
# l'alfabeto ammesso per il token interno. Fino a questo giro NESSUNO validava
# l'opzione `internal_token`, che `hiris/config.yaml` espone come `password`
# libera: qualunque cosa l'utente scrivesse entrava in circolo dopo un solo
# `.strip()`. Non era teorico -- un token con CR/LF/NUL fa sollevare il client
# HTTP con IL VALORE DENTRO il messaggio d'errore, e quel messaggio finisce nel
# log dell'add-on (`agent/runner.py::sonda_strumenti`, riprodotto contro un
# listener vero: LocalProtocolError, Illegal header value, col valore dentro).
#
# La regola e' la piu' piccola che chiude il difetto, non la piu' severa che si
# possa scrivere: si rifiuta cio' che NON e' consegnabile in un header HTTP --
# i caratteri di controllo (0x00-0x1F e 0x7F) e tutto cio' che sta fuori
# dall'ASCII. Restano ammessi lo spazio interno (i bordi li toglie gia'
# `.strip()`) e OGNI carattere stampabile, virgolette e backslash compresi:
# sono header-safe, spezzavano soltanto la REDAZIONE del token nei log, e quel
# fronte si chiude dove si manifesta (`agent/runner.py::forme_del_token`, che
# reda anche la forma JSON-escaped). Rifiutarli anche qui avrebbe respinto
# configurazioni legittime che oggi funzionano.
def invalid_token_reason(token: str) -> str | None:
    """`None` se il token puo' circolare, altrimenti il PERCHE' -- **senza mai
    nominarne il valore**, che e' la promessa in cima a questo file.

    Si dice la categoria del carattere e la sua posizione: e' cio' che serve a
    chi deve correggere l'opzione, e non e' entropia del segreto (un token non
    e' costruito con dei ritorni a capo). Del carattere non-ASCII non si stampa
    nemmeno il codice: li' un codepoint sarebbe un pezzo di segreto."""
    for position, character in enumerate(token):
        code = ord(character)
        # I controlli PRIMA del non-ASCII: 0x7F (DEL) e' un carattere di
        # controllo, non un carattere fuori ASCII, e chiamarlo cosi' manderebbe
        # chi legge il log a cercare un accento che non c'e'.
        if code < 0x20 or code == 0x7F:
            name = {
                0x00: "un byte NUL",
                0x09: "una tabulazione",
                0x0A: "un a-capo (LF)",
                0x0D: "un ritorno a capo (CR)",
            }.get(code, f"un carattere di controllo (0x{code:02X})")
            return f"{name} in posizione {position}"
        if code > 0x7F:
            return f"un carattere non-ASCII in posizione {position}"
    return None


def token_path(data_dir: str) -> str:
    """Dove vive il token generato."""
    return os.path.join(data_dir, TOKEN_FILE_NAME)


def _read_token(path: str) -> str:
    """Rilegge il token da un avvio precedente. `""` se il file non c'e'
    ancora (primo avvio) o se e' vuoto. Gli altri errori di I/O risalgono:
    un file presente ma illeggibile non deve essere confuso con «non c'e'» --
    sovrascriverlo cambierebbe il segreto sotto ai lavori gia' in coda."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _write_token(path: str, token: str) -> None:
    """Scrive il token in modo atomico e con i permessi piu' stretti possibili.

    Atomico (file temporaneo + `os.replace`) perche' un token troncato a meta'
    da un'interruzione sarebbe peggio di un token assente: verrebbe riletto al
    riavvio successivo come se fosse valido. I permessi si impostano sul
    temporaneo *alla creazione* (`os.open` con il modo), non dopo la
    pubblicazione: cosi' il segreto non esiste mai, nemmeno per un istante, con
    permessi larghi."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temporary = f"{path}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_PERMISSIONS)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            f.write(token + "\n")
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    os.replace(temporary, path)


def _publish(token: str) -> str:
    """Rende il token visibile a chi lo legge dall'ambiente **al momento della
    chiamata**, non all'import: `agent/runner.py::build_headers` fa
    `os.environ.get("INTERNAL_TOKEN", "")` a ogni giro del ponte, e senza
    questa riga un token generato solo dentro `app["internal_token"]`
    lascerebbe il guasto identico a prima (il worker manderebbe l'header
    vuoto e continuerebbe a prendersi 401)."""
    os.environ["INTERNAL_TOKEN"] = token
    return token


def prepare_internal_token(data_dir: str) -> str:
    """Risolve il token interno dell'add-on e lo pubblica in `os.environ`.

    Restituisce il token da mettere in `app["internal_token"]`, o `""` se non
    e' stato possibile averne uno -- e in quel caso il rifiuto-per-default del
    middleware resta in piedi, dichiarato nel log.
    """
    configured = os.environ.get("INTERNAL_TOKEN", "").strip()
    if configured:
        # fix round 2: prima di tutto, l'alfabeto. Un token non consegnabile in
        # un header non deve entrare in circolo: non autenticherebbe niente
        # (ogni richiesta del ponte fallirebbe prima di partire) e, peggio, il
        # client HTTP solleva con IL VALORE DENTRO il messaggio, che finisce nel
        # log dell'add-on -- quello che si incolla in una segnalazione.
        # Rifiuto-per-difetto, come ogni altro ramo di guasto di questo file:
        # si torna "" e il middleware continua a negare. Mai un pass muto.
        reason = invalid_token_reason(configured)
        if reason is not None:
            logger.error(
                "Token interno: l'opzione internal_token contiene %s e NON e' "
                "utilizzabile come intestazione HTTP. Non lo metto in circolo: "
                "non autenticherebbe nulla, e il messaggio d'errore del client "
                "porterebbe il valore del token dentro il log dell'add-on. "
                "HIRIS resta senza token interno: ogni richiesta non-ingress "
                "continua a essere NEGATA (401) e il ponte della chat via "
                "abbonamento non potra' lavorare. Rimedio: usa un valore di "
                "solo testo stampabile (o lascia l'opzione VUOTA e lascia che "
                "HIRIS ne generi uno). Il valore configurato non compare in "
                "questo log.",
                reason,
            )
            return _publish("")
        # Il token dell'utente vince sempre: nessuna generazione, nessuna
        # scrittura su disco. Si ripubblica il valore ripulito dagli spazi
        # perche' un header HTTP viene comunque consegnato senza spazi ai
        # bordi: senza questa normalizzazione il worker manderebbe un valore
        # che non combacia con quello in `app` e si prenderebbe 401.
        logger.info(
            "Token interno: uso quello configurato nell'opzione internal_token "
            "dell'add-on. Nessuna generazione, nessuna scrittura in %s.",
            token_path(data_dir),
        )
        return _publish(configured)

    path = token_path(data_dir)
    try:
        existing = _read_token(path)
    except OSError as exc:
        logger.error(
            "Token interno: il file %s esiste ma non e' leggibile (%s: %s). "
            "NON ne genero un altro sopra -- invaliderebbe i lavori gia' in "
            "coda. HIRIS resta senza token interno: ogni richiesta non-ingress "
            "continua a essere NEGATA (401) e il ponte della chat via "
            "abbonamento non potra' lavorare. Rimedio: correggi i permessi del "
            "file, oppure valorizza a mano l'opzione internal_token.",
            path, type(exc).__name__, exc,
        )
        return _publish("")

    if existing:
        # Stesso gate: il file di `/data` e' scritto da noi con un valore
        # urlsafe, ma e' un file di testo su un volume che l'utente puo'
        # aprire. Un file corretto a mano non deve poter aggirare la
        # validazione dell'opzione.
        reason = invalid_token_reason(existing)
        if reason is not None:
            logger.error(
                "Token interno: il token riletto da %s contiene %s e NON e' "
                "utilizzabile come intestazione HTTP -- il file e' stato "
                "modificato a mano, o si e' corrotto. NON ne genero un altro "
                "sopra: invaliderebbe i lavori gia' in coda. HIRIS resta senza "
                "token interno: ogni richiesta non-ingress continua a essere "
                "NEGATA (401). Rimedio: cancella quel file per farne rigenerare "
                "uno, oppure valorizza a mano l'opzione internal_token. Il "
                "valore letto non compare in questo log.",
                path, reason,
            )
            return _publish("")
        logger.info(
            "Token interno: riletto da %s, dove un avvio precedente lo aveva "
            "generato. Invariato fra i riavvii, quindi i lavori rimasti in coda "
            "restano validi. Il valore non compare nei log.",
            path,
        )
        return _publish(existing)

    token = secrets.token_urlsafe(ENTROPY_BYTES)
    try:
        _write_token(path, token)
    except OSError as exc:
        logger.error(
            "Token interno: generato, ma la scrittura in %s e' fallita (%s: %s). "
            "NON lo tengo solo in memoria: cambierebbe a ogni riavvio e "
            "invaliderebbe i lavori in coda, in silenzio. HIRIS resta senza "
            "token interno: ogni richiesta non-ingress continua a essere NEGATA "
            "(401) e il ponte della chat via abbonamento non potra' lavorare. "
            "Rimedio: verifica che la directory dei dati dell'add-on sia "
            "scrivibile, oppure valorizza a mano l'opzione internal_token.",
            path, type(exc).__name__, exc,
        )
        return _publish("")

    logger.info(
        "Token interno: l'opzione internal_token e' vuota, ne ho generato uno "
        "nuovo (%d bit da secrets) e l'ho scritto in %s con permessi %s. "
        "Sopravvive ai riavvii: al prossimo avvio verra' riletto da li', non "
        "rigenerato. Il valore non compare nei log.",
        ENTROPY_BYTES * 8, path, oct(FILE_PERMISSIONS),
    )
    return _publish(token)
