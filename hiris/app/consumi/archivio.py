"""L'archivio dei consumi: l'UNICA casa di «quanto ho speso, e per cosa».

Un secchiello al giorno per `(provider, modello)`: cinque righe al giorno anche
usando cinque modelli, meno di duemila l'anno. La storia si tiene per sempre
senza una politica di ritenzione da governare e senza mai cancellare dati
dell'utente a scadenza.

Non legge l'orologio: lo riceve (`adesso=`), come l'archivio delle promesse e
come `casa/nucleo.componi`. E non legge il fuso alla costruzione ma a ogni
scrittura: la casa puo' cambiarlo (`core_config_updated`), e un fuso cotto qui
dentro sarebbe quello di quando l'add-on e' partito.
"""
from __future__ import annotations

import logging
import threading

from ..storage import connect, init_schema
from .vocabolario import giorno_locale, piu_debole

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS consumo_giorno (
    giorno            TEXT    NOT NULL,
    provider          TEXT    NOT NULL,
    modello           TEXT    NOT NULL,
    richieste         INTEGER NOT NULL DEFAULT 0,
    token_in          INTEGER NOT NULL DEFAULT 0,
    token_out         INTEGER NOT NULL DEFAULT 0,
    cache_lettura     INTEGER NOT NULL DEFAULT 0,
    cache_scrittura   INTEGER NOT NULL DEFAULT 0,
    costo_usd         REAL,
    costo_stato       TEXT    NOT NULL,
    errori_rate_limit INTEGER NOT NULL DEFAULT 0,
    primo_ts          REAL    NOT NULL,
    ultimo_ts         REAL    NOT NULL,
    PRIMARY KEY (giorno, provider, modello)
);
CREATE INDEX IF NOT EXISTS idx_consumo_giorno ON consumo_giorno(giorno);
CREATE TABLE IF NOT EXISTS ancora (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    da_ts REAL NOT NULL,
    da_giorno TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ancora_saldo (
    provider TEXT NOT NULL, modello TEXT NOT NULL,
    richieste INTEGER NOT NULL DEFAULT 0, token_in INTEGER NOT NULL DEFAULT 0,
    token_out INTEGER NOT NULL DEFAULT 0, cache_lettura INTEGER NOT NULL DEFAULT 0,
    cache_scrittura INTEGER NOT NULL DEFAULT 0, costo_usd REAL,
    errori_rate_limit INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, modello)
);
CREATE TABLE IF NOT EXISTS legacy_importati (percorso TEXT PRIMARY KEY);
"""

# I contatori che si sommano. Uno solo, perche' l'elenco scritto tre volte in
# tre query e' il modo in cui una colonna nuova entra in due su tre.
CAMPI = ("richieste", "token_in", "token_out", "cache_lettura",
         "cache_scrittura", "errori_rate_limit")


class ArchivioConsumi:
    def __init__(self, db_path: str, *, leggi_fuso=None) -> None:
        self._leggi_fuso = leggi_fuso
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _fuso(self) -> str:
        """Il fuso della casa, o «» se non si puo' sapere.

        Non solleva mai: un consumo non si perde perche' l'anagrafe non e'
        ancora stata letta. Si conta in UTC e lo si dichiara -- e' la stessa
        disciplina del nucleo, che tace sul fuso invece di inventarne uno.
        """
        try:
            return (self._leggi_fuso() if self._leggi_fuso else "") or ""
        except Exception as exc:
            logger.warning("fuso della casa non leggibile, si conta in UTC: %s", exc)
            return ""

    def vuoto(self) -> bool:
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM consumo_giorno LIMIT 1").fetchone() is None

    def registra(self, provider: str, modello: str, *, richieste: int = 1,
                 token_in: int = 0, token_out: int = 0,
                 cache_lettura: int = 0, cache_scrittura: int = 0,
                 costo_usd: float | None = None, costo_stato: str,
                 errori_rate_limit: int = 0, adesso: float) -> None:
        """Una chiamata entra nel secchiello del suo giorno.

        `richieste=0` e' il caso del rifiuto (429): si conta chi ha rifiutato,
        sulla riga del modello che l'ha preso, senza contarla come una
        richiesta servita.
        """
        giorno = giorno_locale(adesso, self._fuso())
        with self._lock:
            riga = self._conn.execute(
                "SELECT costo_usd, costo_stato FROM consumo_giorno "
                "WHERE giorno=? AND provider=? AND modello=?",
                (giorno, provider, modello)).fetchone()
            if riga is None:
                self._conn.execute(
                    "INSERT INTO consumo_giorno (giorno, provider, modello, "
                    "richieste, token_in, token_out, cache_lettura, "
                    "cache_scrittura, costo_usd, costo_stato, "
                    "errori_rate_limit, primo_ts, ultimo_ts) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (giorno, provider, modello, richieste, token_in, token_out,
                     cache_lettura, cache_scrittura, costo_usd, costo_stato,
                     errori_rate_limit, adesso, adesso))
            else:
                stato = piu_debole(riga["costo_stato"], costo_stato)
                if stato != riga["costo_stato"]:
                    logger.info(
                        "consumi: %s/%s del %s degrada da «%s» a «%s» -- il "
                        "provider ha cambiato comportamento",
                        provider, modello, giorno, riga["costo_stato"], stato)
                # I costi si sommano solo fra quelli NOTI. Una riga degradata
                # tiene cio' che ha gia' pagato e diventa un pavimento -- lo
                # stesso concetto del totale in cima alla pagina, a una scala
                # piu' piccola. Buttarlo direbbe «non ho speso niente», che e'
                # falso quanto lo zero da cui nasce la fetta.
                noti = [c for c in (riga["costo_usd"], costo_usd) if c is not None]
                self._conn.execute(
                    "UPDATE consumo_giorno SET richieste=richieste+?, "
                    "token_in=token_in+?, token_out=token_out+?, "
                    "cache_lettura=cache_lettura+?, cache_scrittura=cache_scrittura+?, "
                    "costo_usd=?, costo_stato=?, "
                    "errori_rate_limit=errori_rate_limit+?, "
                    "primo_ts=MIN(primo_ts, ?), ultimo_ts=MAX(ultimo_ts, ?) "
                    "WHERE giorno=? AND provider=? AND modello=?",
                    (richieste, token_in, token_out, cache_lettura,
                     cache_scrittura, sum(noti) if noti else None, stato,
                     errori_rate_limit, adesso, adesso,
                     giorno, provider, modello))
            self._conn.commit()

    # -- leggere -------------------------------------------------------
    #
    # `totali` NON ha una query propria: somma le sezioni. Due strade di
    # calcolo per lo stesso numero sono due strade libere di divergere, e
    # divergerebbero proprio su `costo_parziale` -- il campo che impedisce
    # alla pagina di spacciare un pavimento per un costo.

    def _dove(self, da: str) -> tuple[str, tuple]:
        return ("WHERE giorno >= ?", (da,)) if da else ("", ())

    def sezioni(self, *, da: str = "", da_ancora: bool = False) -> list[dict]:
        """Una voce per provider USATO, coi suoi modelli dentro.

        I provider mai usati non compaiono: e' un'ASSENZA, non uno zero -- ed
        e' il «al primo utilizzo si attiva» che il proprietario ha chiesto.
        """
        from .vocabolario import ETICHETTA, NOTA

        if da_ancora:
            da = self._giorno_ancora() or da
        dove, arg = self._dove(da)
        somme = ", ".join("SUM(%s) AS %s" % (c, c) for c in CAMPI)
        with self._lock:
            righe = self._conn.execute(
                "SELECT provider, modello, %s, SUM(costo_usd) AS costo_usd, "
                "MIN(costo_stato) AS uno_stato, "
                "SUM(CASE WHEN costo_stato='non_noto' THEN 1 ELSE 0 END) AS ignoti, "
                "MIN(giorno) AS primo_uso, MAX(giorno) AS ultimo_uso "
                "FROM consumo_giorno %s GROUP BY provider, modello "
                "ORDER BY provider, modello" % (somme, dove), arg).fetchall()

        per_provider: dict[str, dict] = {}
        for r in righe:
            sezione = per_provider.setdefault(r["provider"], {
                "provider": r["provider"],
                "etichetta": ETICHETTA.get(r["provider"], r["provider"]),
                "nota": NOTA.get(r["provider"], ""),
                "costo_usd": 0.0,
                "costo_parziale": False,
                "modelli": [],
                **{c: 0 for c in CAMPI},
            })
            for c in CAMPI:
                sezione[c] += r[c] or 0
            sezione["costo_usd"] += r["costo_usd"] or 0.0
            sezione["costo_parziale"] = sezione["costo_parziale"] or bool(r["ignoti"])
            sezione["modelli"].append({
                "modello": r["modello"],
                "costo_usd": r["costo_usd"],
                # `MIN(costo_stato)` e' alfabetico e non significa niente: se
                # anche un solo giorno e' ignoto, la riga lo e'. Si sceglie
                # esplicitamente invece di fidarsi dell'ordine delle lettere.
                "costo_stato": "non_noto" if r["ignoti"] else r["uno_stato"],
                "primo_uso": r["primo_uso"],
                "ultimo_uso": r["ultimo_uso"],
                **{c: r[c] or 0 for c in CAMPI},
            })
        if da_ancora:
            self._sottrai_saldo(per_provider)
        return list(per_provider.values())

    def totali(self, *, da: str = "", da_ancora: bool = False) -> dict:
        sezioni = self.sezioni(da=da, da_ancora=da_ancora)
        fuori = {c: sum(s[c] for s in sezioni) for c in CAMPI}
        fuori["costo_usd"] = sum(s["costo_usd"] or 0.0 for s in sezioni)
        # Se anche un solo modello e' senza prezzo, il totale non e' il costo:
        # e' un pavimento, e la pagina lo scrive con un «>=».
        fuori["costo_parziale"] = any(s["costo_parziale"] for s in sezioni)
        return fuori

    def storia(self, *, da: str, a: str) -> list[dict]:
        """Un secchiello per giorno e provider, per il grafico."""
        somme = ", ".join("SUM(%s) AS %s" % (c, c) for c in CAMPI)
        with self._lock:
            righe = self._conn.execute(
                "SELECT giorno, provider, %s, SUM(costo_usd) AS costo_usd "
                "FROM consumo_giorno WHERE giorno >= ? AND giorno <= ? "
                "GROUP BY giorno, provider ORDER BY giorno, provider"
                % somme, (da, a)).fetchall()
        giorni: dict[str, dict] = {}
        for r in righe:
            g = giorni.setdefault(r["giorno"],
                                  {"giorno": r["giorno"], "per_provider": {}})
            g["per_provider"][r["provider"]] = {
                "costo_usd": r["costo_usd"],
                **{c: r[c] or 0 for c in CAMPI},
            }
        return list(giorni.values())

    # -- l'ancora: azzerare senza cancellare ---------------------------

    def ancora(self) -> float:
        """L'istante da cui si conta, o `0.0` se non e' mai stata spostata."""
        with self._lock:
            r = self._conn.execute("SELECT da_ts FROM ancora WHERE id=1").fetchone()
        return r["da_ts"] if r else 0.0

    def _giorno_ancora(self) -> str:
        with self._lock:
            r = self._conn.execute("SELECT da_giorno FROM ancora WHERE id=1").fetchone()
        return r["da_giorno"] if r else ""

    def sposta_ancora(self, adesso: float) -> float:
        """«Riparti da adesso»: fissa il punto da cui contare. Non cancella nulla.

        Fotografa i contatori del giorno CORRENTE in `ancora_saldo`. Senza
        quella fotografia, un'ancora che fosse soltanto una data lascerebbe in
        pagina il consumo gia' fatto stamattina, e il pulsante sembrerebbe
        rotto proprio nel momento in cui lo si preme.

        Il saldo non e' un doppione di un fatto che vive altrove: e' la
        POSIZIONE dell'ancora, espressa nelle uniche coordinate che l'archivio
        possiede. Nessun altro posto la sa.
        """
        giorno = giorno_locale(adesso, self._fuso())
        colonne = ", ".join(CAMPI)
        with self._lock:
            self._conn.execute("DELETE FROM ancora_saldo")
            self._conn.execute(
                "INSERT INTO ancora_saldo (provider, modello, %s, costo_usd) "
                "SELECT provider, modello, %s, costo_usd "
                "FROM consumo_giorno WHERE giorno = ?" % (colonne, colonne),
                (giorno,))
            self._conn.execute(
                "INSERT INTO ancora (id, da_ts, da_giorno) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET da_ts=excluded.da_ts, "
                "da_giorno=excluded.da_giorno", (adesso, giorno))
            self._conn.commit()
        return adesso

    def _sottrai_saldo(self, per_provider: dict) -> None:
        """Toglie da ogni riga il valore che aveva all'istante dell'ancora.

        `max(0, ...)`: se una riga di saldo non trovasse piu' il suo modello --
        non dovrebbe succedere, i secchielli non si cancellano -- si preferisce
        uno zero a un numero negativo, che a schermo non vorrebbe dire niente.
        """
        with self._lock:
            saldi = self._conn.execute("SELECT * FROM ancora_saldo").fetchall()
        for s in saldi:
            sezione = per_provider.get(s["provider"])
            if sezione is None:
                continue
            for modello in sezione["modelli"]:
                if modello["modello"] != s["modello"]:
                    continue
                for c in CAMPI:
                    modello[c] = max(0, modello[c] - (s[c] or 0))
                if modello["costo_usd"] is not None and s["costo_usd"] is not None:
                    modello["costo_usd"] = max(0.0, modello["costo_usd"] - s["costo_usd"])
        # I totali di sezione si RICALCOLANO dai modelli, non si correggono a
        # parte: due strade per lo stesso numero divergono al primo caso limite.
        for sezione in per_provider.values():
            for c in CAMPI:
                sezione[c] = sum(m[c] for m in sezione["modelli"])
            sezione["costo_usd"] = sum(m["costo_usd"] or 0.0
                                       for m in sezione["modelli"])

    # -- i file di prima -----------------------------------------------

    def importa_legacy(self, percorsi: list[str], *, adesso: float) -> int:
        """I quattro `usage_*.json` entrano UNA volta, come una riga sola.

        Il totale ereditato non si puo' attribuire a un modello: nessuno lo ha
        mai registrato. Si dichiara -- modello `(prima del dettaglio)` --
        invece di spalmarlo su modelli che potrebbero non averlo speso.

        Datato all'ultimo azzeramento, che e' l'unica data vera che quei file
        portano. I file NON vengono cancellati: mai dati dell'utente rimossi in
        silenzio.
        """
        import json as _json
        import os
        from datetime import datetime

        _DAL_NOME = {"_openai": "openai", "_openrouter": "openrouter",
                     "_ollama": "ollama"}
        importati = 0
        for percorso in percorsi:
            if not os.path.exists(percorso):
                continue
            with self._lock:
                gia = self._conn.execute(
                    "SELECT 1 FROM legacy_importati WHERE percorso=?",
                    (percorso,)).fetchone()
            if gia:
                continue
            try:
                with open(percorso, encoding="utf-8") as f:
                    dati = _json.load(f)
            except Exception as exc:
                logger.warning("usage.json illeggibile (%s): %s -- saltato, e "
                               "il file resta dov'e'", percorso, exc)
                continue
            base = os.path.splitext(os.path.basename(percorso))[0]
            provider = next((p for suff, p in _DAL_NOME.items()
                             if base.endswith(suff)), "claude")
            quando = adesso
            try:
                quando = datetime.fromisoformat(
                    (dati.get("last_reset") or "").replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError):
                pass
            self.registra(
                provider, "(prima del dettaglio)",
                richieste=int(dati.get("total_requests") or 0),
                token_in=int(dati.get("total_input_tokens") or 0),
                token_out=int(dati.get("total_output_tokens") or 0),
                costo_usd=float(dati.get("total_cost_usd") or 0.0),
                costo_stato="misurato",
                errori_rate_limit=int(dati.get("total_rate_limit_errors") or 0),
                adesso=quando)
            with self._lock:
                self._conn.execute(
                    "INSERT OR IGNORE INTO legacy_importati (percorso) VALUES (?)",
                    (percorso,))
                self._conn.commit()
            importati += 1
            logger.info("consumi: importato %s come «(prima del dettaglio)» "
                        "sul provider %s", percorso, provider)
        return importati
