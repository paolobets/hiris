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
NOME_FILE_TOKEN = "internal_token"

# 32 byte di entropia da `secrets.token_urlsafe` -> 256 bit, resi in ~43
# caratteri URL-safe. Robustezza adeguata a un segreto condiviso: il confronto
# a valle e' `hmac.compare_digest`, quindi la lunghezza non e' un problema.
BYTE_ENTROPIA = 32

# Permessi del file: solo il proprietario legge e scrive. Su Linux (la
# piattaforma dell'add-on) e' esattamente 0600; su Windows -- dove gira solo la
# suite di test -- il bit di gruppo/altri non esiste e la chiamata incide di
# fatto solo sul flag di sola-lettura: e' il piu' stretto possibile *su questa
# piattaforma*, non un'illusione di isolamento.
PERMESSI_FILE = 0o600


def percorso_token(data_dir: str) -> str:
    """Dove vive il token generato."""
    return os.path.join(data_dir, NOME_FILE_TOKEN)


def _leggi_token(percorso: str) -> str:
    """Rilegge il token da un avvio precedente. `""` se il file non c'e'
    ancora (primo avvio) o se e' vuoto. Gli altri errori di I/O risalgono:
    un file presente ma illeggibile non deve essere confuso con «non c'e'» --
    sovrascriverlo cambierebbe il segreto sotto ai lavori gia' in coda."""
    try:
        with open(percorso, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _scrivi_token(percorso: str, token: str) -> None:
    """Scrive il token in modo atomico e con i permessi piu' stretti possibili.

    Atomico (file temporaneo + `os.replace`) perche' un token troncato a meta'
    da un'interruzione sarebbe peggio di un token assente: verrebbe riletto al
    riavvio successivo come se fosse valido. I permessi si impostano sul
    temporaneo *alla creazione* (`os.open` con il modo), non dopo la
    pubblicazione: cosi' il segreto non esiste mai, nemmeno per un istante, con
    permessi larghi."""
    directory = os.path.dirname(percorso) or "."
    os.makedirs(directory, exist_ok=True)
    temporaneo = f"{percorso}.tmp"
    descrittore = os.open(temporaneo, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PERMESSI_FILE)
    try:
        with os.fdopen(descrittore, "w", encoding="utf-8") as f:
            f.write(token + "\n")
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            os.unlink(temporaneo)
        except OSError:
            pass
        raise
    os.replace(temporaneo, percorso)


def _pubblica(token: str) -> str:
    """Rende il token visibile a chi lo legge dall'ambiente **al momento della
    chiamata**, non all'import: `agent/runner.py::build_headers` fa
    `os.environ.get("INTERNAL_TOKEN", "")` a ogni giro del ponte, e senza
    questa riga un token generato solo dentro `app["internal_token"]`
    lascerebbe il guasto identico a prima (il worker manderebbe l'header
    vuoto e continuerebbe a prendersi 401)."""
    os.environ["INTERNAL_TOKEN"] = token
    return token


def prepara_token_interno(data_dir: str) -> str:
    """Risolve il token interno dell'add-on e lo pubblica in `os.environ`.

    Restituisce il token da mettere in `app["internal_token"]`, o `""` se non
    e' stato possibile averne uno -- e in quel caso il rifiuto-per-default del
    middleware resta in piedi, dichiarato nel log.
    """
    configurato = os.environ.get("INTERNAL_TOKEN", "").strip()
    if configurato:
        # Il token dell'utente vince sempre: nessuna generazione, nessuna
        # scrittura su disco. Si ripubblica il valore ripulito dagli spazi
        # perche' un header HTTP viene comunque consegnato senza spazi ai
        # bordi: senza questa normalizzazione il worker manderebbe un valore
        # che non combacia con quello in `app` e si prenderebbe 401.
        logger.info(
            "Token interno: uso quello configurato nell'opzione internal_token "
            "dell'add-on. Nessuna generazione, nessuna scrittura in %s.",
            percorso_token(data_dir),
        )
        return _pubblica(configurato)

    percorso = percorso_token(data_dir)
    try:
        esistente = _leggi_token(percorso)
    except OSError as exc:
        logger.error(
            "Token interno: il file %s esiste ma non e' leggibile (%s: %s). "
            "NON ne genero un altro sopra -- invaliderebbe i lavori gia' in "
            "coda. HIRIS resta senza token interno: ogni richiesta non-ingress "
            "continua a essere NEGATA (401) e il ponte della chat via "
            "abbonamento non potra' lavorare. Rimedio: correggi i permessi del "
            "file, oppure valorizza a mano l'opzione internal_token.",
            percorso, type(exc).__name__, exc,
        )
        return _pubblica("")

    if esistente:
        logger.info(
            "Token interno: riletto da %s, dove un avvio precedente lo aveva "
            "generato. Invariato fra i riavvii, quindi i lavori rimasti in coda "
            "restano validi. Il valore non compare nei log.",
            percorso,
        )
        return _pubblica(esistente)

    token = secrets.token_urlsafe(BYTE_ENTROPIA)
    try:
        _scrivi_token(percorso, token)
    except OSError as exc:
        logger.error(
            "Token interno: generato, ma la scrittura in %s e' fallita (%s: %s). "
            "NON lo tengo solo in memoria: cambierebbe a ogni riavvio e "
            "invaliderebbe i lavori in coda, in silenzio. HIRIS resta senza "
            "token interno: ogni richiesta non-ingress continua a essere NEGATA "
            "(401) e il ponte della chat via abbonamento non potra' lavorare. "
            "Rimedio: verifica che la directory dei dati dell'add-on sia "
            "scrivibile, oppure valorizza a mano l'opzione internal_token.",
            percorso, type(exc).__name__, exc,
        )
        return _pubblica("")

    logger.info(
        "Token interno: l'opzione internal_token e' vuota, ne ho generato uno "
        "nuovo (%d bit da secrets) e l'ho scritto in %s con permessi %s. "
        "Sopravvive ai riavvii: al prossimo avvio verra' riletto da li', non "
        "rigenerato. Il valore non compare nei log.",
        BYTE_ENTROPIA * 8, percorso, oct(PERMESSI_FILE),
    )
    return _pubblica(token)
