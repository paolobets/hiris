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
