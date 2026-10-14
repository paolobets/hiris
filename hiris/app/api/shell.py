"""Il **guscio** dell'add-on: le due pagine HTML, le impronte degli asset e le
intestazioni di sicurezza di ogni risposta.

Spostato da `server.py` alla Chiusura dello sprint (F8 passo 5, 14/10/2026),
con un commit di solo spostamento: `server.py` registra e avvia, non ospita.
L'unica riga adattata e' la cartella `static/`, che da qui sta un livello
sopra (`os.path.dirname` due volte invece di una). Si calcola una volta sola,
in `_STATIC_DIR`: la leggono le pagine, le impronte e `create_app` (N164-1).
"""
import hashlib
import logging
import os
import re

from aiohttp import web

from ..version import read_version

logger = logging.getLogger(__name__)


def _read_static_pages(app) -> None:
    """Sincrona di proposito: gira una volta sola all'avvio, prima che l'app
    serva qualcosa. Sta fuori dalla coroutine perche' `open()` dentro una
    funzione async e' un difetto anche quando qui non lo e' -- e una regola
    con un'eccezione «tanto lo so io» e' una regola che non vale piu'."""
    for fname, key in (("index.html", "html_index"), ("config.html", "html_config")):
        path = os.path.join(_STATIC_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                app[key] = f.read()
        except FileNotFoundError:
            logger.error("Static %s missing at %s", fname, path)
            app[key] = ""


@web.middleware
async def _security_headers(request: web.Request, handler) -> web.Response:
    response = await handler(request)
    # Static assets are content-fingerprinted (?v=HASH via _inject_version), so a
    # changed file always gets a fresh URL. As defence-in-depth against the HA
    # Ingress proxy / heuristic browser caching serving a stale copy under an old
    # URL, force revalidation: "no-cache" allows storing but requires a
    # conditional request (304 when unchanged) before the cached copy is reused.
    if request.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-cache")
        # Task B8 punto 5: se il client chiede un asset con un ?v=<impronta>
        # che non corrisponde all'impronta ATTUALE di quel file, il server sa
        # in quel momento che quel client ha un guscio vecchio -- e' cosi'
        # che il difetto misurato (bottone del guscio HTML mancante mentre i
        # testi del backend erano gia' aggiornati) sarebbe stato diagnosticato
        # subito invece che scoperto un giorno dopo. Non cambia cosa viene
        # servito: il file resta quello, si aggiunge solo la riga di log.
        asked = request.query.get("v")
        if asked:
            rel_path = request.path.lstrip("/")  # "static/chat/main.js"
            attuale = _asset_fingerprint(rel_path, "")
            if attuale and asked != attuale:
                logger.warning(
                    "Asset richiesto con impronta stantia: %s (chiesta=%s, attuale=%s) "
                    "-- il client ha un guscio HTML vecchio",
                    rel_path, asked, attuale,
                )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # X-Frame-Options omesso: HA Ingress carica l'UI in un iframe
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        # **Chiusa verso l'esterno** (reperto D-7, 23/09/2026). I due domini
        # dei caratteri sono usciti insieme ai `<link>` che li chiamavano: un
        # permesso che non serve piu' e' debito, e finche' restava scritto
        # qui un foglio di stile poteva ancora arrivare da fuori.
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; img-src 'self' data:; connect-src 'self'",
    )
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return response


_NO_CACHE = {"Cache-Control": "no-store"}


# Per-file content fingerprints for cache-busting. Keyed by asset path
# relative to the static dir; value is (mtime, short-sha1). Hashing a given
# file happens at most once per change (invalidated by mtime).
_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


_ASSET_FP_CACHE: dict[str, tuple[float, str]] = {}


# Matches local asset refs like  src="static/config/main.js"  /  href="static/hiris.css"
# External URLs (https://…) and query-stringed refs are left untouched.
_ASSET_REF_RE = re.compile(r'(src|href)="(static/[^"?]+\.(?:js|css))"')


def _asset_fingerprint(rel_path: str, fallback: str) -> str:
    """Return a short content hash for a static asset, cached by mtime.

    Because the fingerprint is derived from the file's actual bytes, ANY edit
    changes the query string and forces browsers (and the HA Ingress proxy) to
    re-fetch — no manual version bump required. Falls back to the app version
    string if the file can't be read (keeps old behaviour as a floor)."""
    # rel_path is like "static/config/main.js"; strip the "static/" mount prefix.
    abs_path = os.path.join(_STATIC_DIR, rel_path[len("static/"):])
    try:
        mtime = os.path.getmtime(abs_path)
    except OSError:
        return fallback
    cached = _ASSET_FP_CACHE.get(rel_path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        with open(abs_path, "rb") as f:
            digest = hashlib.sha1(f.read()).hexdigest()[:10]
    except OSError:
        return fallback
    _ASSET_FP_CACHE[rel_path] = (mtime, digest)
    return digest


def _compute_build_stamp(static_dir: str) -> str:
    """Hash breve del contenuto di TUTTI gli asset frontend: cambia se e solo se
    un file del frontend cambia. Esposto in /api/health e mostrato in UI, cosi'
    si verifica CON CERTEZZA quale build sta girando davvero -- distingue
    "cache del browser/CDN" da "container addon non ricostruito" nel giro di
    live-verify (prima non c'era modo di saperlo). Deterministico: root e file
    in ordine, il path relativo entra nell'hash insieme al contenuto."""
    h = hashlib.sha1()
    try:
        for root, _dirs, files in sorted(os.walk(static_dir)):
            for name in sorted(files):
                p = os.path.join(root, name)
                rel = os.path.relpath(p, static_dir).replace(os.sep, "/")
                try:
                    with open(p, "rb") as f:
                        h.update(rel.encode("utf-8"))
                        h.update(hashlib.sha1(f.read()).digest())
                except OSError:
                    continue
    except OSError:
        return "unknown"
    return h.hexdigest()[:12]


def _inject_version(html: str, version: str, build_stamp: str = "") -> str:
    """Append a per-file content fingerprint (?v=HASH) to local static asset
    URLs so browsers bust cache whenever a file's content actually changes.

    Replaces the previous single global ?v=VERSION scheme, which only busted
    caches on a release version bump and left stale JS/CSS in place during any
    edit that didn't change config.yaml's version field.

    Task B8: se `build_stamp` e' dato, dichiara anche da quale build il guscio
    e' nato -- una `<meta name="hiris-build" content="...">` in `<head>`, col
    valore che l'app ha gia' (`app["build_stamp"]`, calcolato una sola volta in
    create_app()): questa funzione non lo ricalcola. E' la meta' che mancava
    perche' `static/chat/main.js` (e ora anche il boot della configurazione)
    potessero confrontare "da quale build sono nato" con "quale build gira
    davvero" (GET api/health) invece di limitarsi a mostrarli affiancati senza
    che nessuno li leggesse."""
    def _repl(m: "re.Match[str]") -> str:
        attr, path = m.group(1), m.group(2)
        return f'{attr}="{path}?v={_asset_fingerprint(path, version)}"'

    html = _ASSET_REF_RE.sub(_repl, html)
    if build_stamp:
        html = html.replace(
            "</head>",
            f'  <meta name="hiris-build" content="{build_stamp}">\n</head>',
            1,
        )
    return html


def _serve_shell(key: str):
    """Il gestore che serve un guscio HTML, letto all'avvio sotto `key`
    (`_read_static_pages`).

    **Una funzione per i due gusci** (C-29, Tappa 4): fino al 05/10/2026
    `_serve_index` e `_serve_config` erano la stessa funzione con la chiave
    cambiata -- due copie libere di divergere alla prima intestazione aggiunta
    a una sola."""
    async def serve(request: web.Request) -> web.Response:
        html = request.app.get(key) or ""
        if not html:
            return web.Response(text="UI not yet available", status=503)
        return web.Response(
            text=_inject_version(html, read_version(), request.app.get("build_stamp", "")),
            content_type="text/html",
            headers=_NO_CACHE,
        )
    return serve
