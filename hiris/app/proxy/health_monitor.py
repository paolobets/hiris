from __future__ import annotations
import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Stati con cui Home Assistant dice "non ho un valore per questa entita'".
STATI_NON_DISPONIBILI = ("unavailable", "unknown")


def _parse_iso(v):
    if not v or not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def entita_non_disponibili(states):
    """Entita' che NON rispondono adesso, dalla lista completa degli stati.

    fetta E3 Task 6: viveva in `brain/health_checks.py` (unica derivazione
    del fatto "questa entita' non risponde", usata sia da questo monitor sia
    dal controllo `check_entity_unavailable` del Brain). Il Brain e il suo
    health_scan sono usciti con quel task -- questo era il solo altro
    lettore, e la funzione si sposta qui con lui invece di sparire: e' pura
    (nessun I/O, nessuna scrittura, mai solleva su voci malformate) e resta
    l'unica fonte di questo fatto per lo snapshot istantaneo.

    `since` viene da `last_changed` (o `last_updated`) normalizzato a UTC:
    la durata dell'assenza e' quella di Home Assistant, non l'istante in cui
    HIRIS se n'e' accorto. Vale None quando HA non porta un istante
    leggibile -- l'entita' non risponde lo stesso, ma da quanto non si sa.
    """
    out = []
    for s in states or []:
        if not isinstance(s, dict):
            continue
        if s.get("state") not in STATI_NON_DISPONIBILI:
            continue
        eid = s.get("entity_id") or ""
        if not eid:
            continue
        ts = _parse_iso(s.get("last_changed") or s.get("last_updated"))
        attributi = s.get("attributes")
        nome = (attributi or {}).get("friendly_name") if isinstance(attributi, dict) else None
        out.append({
            "entity_id": eid,
            "domain": eid.split(".", 1)[0] if "." in eid else "",
            "since": ts.astimezone(timezone.utc).strftime(_TS_FMT) if ts else None,
            "state": s.get("state"),
            "name": nome or eid,
        })
    return out

# Cap per sezione. Servono a proteggere il PROMPT dell'LLM: con molti problemi
# in casa una lista senza limite finirebbe intera nel contesto. Il taglio
# avviene in lettura (get_snapshot), non in scrittura: il file su disco e la
# dashboard di configurazione (get_snapshot(capped=False)) restano completi.
# Ogni sezione tagliata viene dichiarata in `truncated`, cosi' il modello puo'
# dire all'utente quanti problemi ci sono davvero.
MAX_UNAVAILABLE_ENTITIES = 25
MAX_INTEGRATION_ERRORS = 20
MAX_TOP_ERRORS = 10
MAX_UPDATES = 20
MAX_SYSTEM_HEALTH_DOMAINS = 20
MAX_ADDONS = 30
MAX_SUPERVISOR_UPDATES = 20


def _ha_contenuto(sezione: Any) -> bool:
    """True se la sezione ha almeno un valore non vuoto da mostrare.

    Serve alle sezioni composte (supervisor): `SupervisorClient` non solleva
    mai e degrada a `[]`/`{}`, quindi su un'installazione standalone la
    sezione varrebbe `{"addons": [], "disk": {}, "updates": []}` -- un dict
    truthy che farebbe comparire `addons: []` nello snapshot, da cui l'LLM
    concluderebbe "non hai add-on installati". Falso: il Supervisor
    semplicemente non c'e'. Se non c'e' nulla da dire la sezione non compare,
    coerentemente con `system_health` (che degrada a `{}`, gia' falsy).
    """
    return isinstance(sezione, dict) and any(bool(v) for v in sezione.values())


def errori_di_integrazione(voci: list[dict]) -> list[dict]:
    """Le sole integrazioni in errore, nella forma che la scansione di salute usa.

    Vive qui e non nel client perche' e' un giudizio del consumatore: il client
    riferisce cosa dice Home Assistant, non decide cosa interessa a chi chiede.
    """
    fuori_servizio = []
    for voce in voci:
        stato = voce.get("state", "")
        if stato in ("loaded", "not_loaded", "setup_in_progress"):
            continue
        fuori_servizio.append({
            "integration": voce.get("domain", "unknown"),
            "title": voce.get("title", ""),
            "state": stato,
            "error": voce.get("reason", ""),
        })
    return fuori_servizio


def _quando(voce: Any) -> str:
    """Istante di caduta di una entita' non disponibile, per l'ordinamento.

    Il formato `_TS_FMT` e' ordinabile lessicograficamente. Voci malformate
    (senza `since`, o non dict) finiscono in fondo con stringa vuota.
    """
    if not isinstance(voce, dict):
        return ""
    return voce.get("since") or ""


class HealthMonitor:
    """Mantiene uno snapshot aggregato dello stato di salute di HA.

    Aggiornamento ibrido:
    - WebSocket state_changed → unavailable entities in real-time
    - APScheduler ogni 30 min → full refresh di tutte le sezioni
    - Persistenza JSON su disco → sopravvive ai restart

    La sezione `unavailable` risponde a «cosa non risponde ADESSO», sempre
    da `entita_non_disponibili` qui sopra. fetta E3 Task 6: rispondeva anche
    a una seconda domanda -- «cosa e' rotto da giorni?», le segnalazioni
    persistenti del Brain (`brain/health_checks.check_entity_unavailable`,
    un FILTRO per durata sopra questa stessa lista) -- uscita con tutto il
    Brain che parlava. Questa sezione resta l'unica fonte del fatto.
    """

    def __init__(
        self,
        ha_client: Any,
        data_path: str,
        scheduler: Any,
        supervisor_client: Any = None,
    ) -> None:
        # `supervisor_client` e' opzionale: senza SUPERVISOR_TOKEN il server
        # non lo costruisce affatto e resta None. Anche quando c'e', se il
        # Supervisor risponde vuoto la sezione non compare (v. refresh).
        self._ha = ha_client
        self._data_path = data_path
        self._scheduler = scheduler
        self._supervisor = supervisor_client
        self._snapshot_data: dict = {
            "last_updated": None,
            "unavailable_entities": [],
            "integration_errors": [],
            "error_log_summary": {"errors": 0, "warnings": 0, "top_errors": []},
            "updates_available": [],
            "system_info": {},
            "system_health": {},
            "supervisor": {},
        }
        # Serialize concurrent _save_sync() between scheduler refresh and WS callbacks.
        self._save_lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(self._data_path)), exist_ok=True)
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._data_path):
            try:
                with open(self._data_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._snapshot_data.update(data)
                logger.debug("HealthMonitor: loaded snapshot from %s", self._data_path)
            except Exception as exc:
                logger.warning("HealthMonitor: failed to load snapshot: %s", exc)

    async def _save(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._save_sync)
        except RuntimeError:
            # No running loop (e.g. called from sync context) — save inline
            self._save_sync()

    def _save_sync(self) -> None:
        with self._save_lock:
            try:
                with open(self._data_path, "w", encoding="utf-8") as f:
                    json.dump(self._snapshot_data, f, ensure_ascii=False)
            except Exception as exc:
                logger.warning("HealthMonitor: failed to save snapshot: %s", exc)

    async def start(self) -> None:
        """Avvia il monitor: register WS hook, schedule polling, initial refresh."""
        self._ha.add_state_listener(self.on_state_changed)
        self._scheduler.add_job(
            self.refresh,
            "interval",
            minutes=30,
            id="health_monitor_poll",
            replace_existing=True,
        )
        await self.refresh()

    async def refresh(self) -> None:
        """Full refresh di tutte le sezioni dalla HA API."""
        updated: dict = {"last_updated": datetime.now(timezone.utc).strftime(_TS_FMT)}

        # Risemina della lista di chi non risponde adesso, dagli stati veri.
        # Serve in due direzioni che il solo ascolto degli eventi non copre:
        # una entita' gia' caduta prima che HIRIS partisse non ha mai generato
        # un evento (e mancava dalla lista mentre il Brain la segnalava), e una
        # rientrata mentre HIRIS era fermo puo' non cambiare piu' stato (e
        # restava nella lista per sempre). L'assegnazione e' immediata, non
        # rimandata a `updated`, cosi' un evento WebSocket che arrivasse
        # durante gli await successivi non verrebbe sovrascritto.
        try:
            stati = await self._ha.get_states([])
            self._snapshot_data["unavailable_entities"] = entita_non_disponibili(stati)
        except Exception as exc:
            # Una lettura fallita non cancella cio' che si sa gia'.
            logger.debug("HealthMonitor: get_states skipped (%s)", exc)

        try:
            updated["error_log_summary"] = await self._ha.get_error_log()
        except Exception as exc:
            logger.debug("HealthMonitor: get_error_log skipped (%s)", exc)

        try:
            updated["integration_errors"] = errori_di_integrazione(await self._ha.get_config_entries())
        except Exception as exc:
            logger.debug("HealthMonitor: get_config_entries skipped (%s)", exc)

        try:
            updated["system_info"] = await self._ha.get_system_info()
        except Exception as exc:
            logger.debug("HealthMonitor: get_system_info skipped (%s)", exc)

        try:
            updated["updates_available"] = await self._ha.get_updates()
        except Exception as exc:
            logger.debug("HealthMonitor: get_updates skipped (%s)", exc)

        try:
            updated["system_health"] = await self._ha.get_system_health()
        except Exception as exc:
            logger.debug("HealthMonitor: get_system_health skipped (%s)", exc)

        # Supervisor: tre letture in un unico blocco. Se una fallisce la
        # sezione intera mantiene il valore precedente, come per le altre
        # fonti. Senza Supervisor (installazione standalone) si salta.
        if self._supervisor is not None:
            try:
                sezione = {
                    "addons": await self._supervisor.get_addons(),
                    "disk": await self._supervisor.get_host_info(),
                    "updates": await self._supervisor.get_available_updates(),
                }
            except Exception as exc:
                logger.debug("HealthMonitor: supervisor skipped (%s)", exc)
            else:
                # Il client degrada a vuoto invece di sollevare: senza
                # Supervisor le tre letture tornano [], {}, []. Meglio non
                # scrivere affatto la sezione che scriverla vuota (v. _ha_contenuto).
                if _ha_contenuto(sezione):
                    updated["supervisor"] = sezione
                else:
                    logger.debug(
                        "HealthMonitor: supervisor senza dati, sezione omessa"
                    )

        self._snapshot_data.update(updated)
        await self._save()
        logger.debug("HealthMonitor: snapshot refreshed")

    def on_state_changed(self, event_data: dict) -> None:
        """Callback chiamato da ha_client._ws_loop per ogni state_changed.

        Tiene aggiornata fra un refresh e l'altro la lista di chi non risponde
        adesso. La voce la costruisce `entita_non_disponibili`, la stessa
        derivazione usata dal refresh: cosi' `since` e' sempre l'istante di
        Home Assistant e non quello in cui HIRIS ha visto l'evento (che dopo
        un riavvio farebbe sembrare appena avvenuta una caduta vecchia di
        giorni).
        """
        entity_id = event_data.get("entity_id", "")
        if not entity_id:
            return
        stato = event_data.get("new_state")
        # `new_state` assente significa entita' rimossa: nessuna voce, quindi
        # esce dalla lista come una rientrata.
        voci = entita_non_disponibili(
            [{**stato, "entity_id": entity_id}] if isinstance(stato, dict) else []
        )
        unavailable = self._snapshot_data["unavailable_entities"]

        if voci:
            voce = voci[0]
            esistente = next(
                (e for e in unavailable
                 if isinstance(e, dict) and e.get("entity_id") == entity_id),
                None,
            )
            if esistente is None:
                unavailable.append(voce)
                logger.debug("HealthMonitor: %s → unavailable", entity_id)
            elif voce["since"] and voce["since"] != esistente.get("since"):
                # L'entita' e' ricaduta senza che si sia visto il rientro (o la
                # voce arrivava da una versione precedente, senza `since`
                # attendibile): si aggiorna, non si duplica.
                esistente.update(voce)
        else:
            before = len(unavailable)
            self._snapshot_data["unavailable_entities"] = [
                e for e in unavailable
                if not isinstance(e, dict) or e.get("entity_id") != entity_id
            ]
            if len(self._snapshot_data["unavailable_entities"]) < before:
                logger.debug("HealthMonitor: %s → recovered", entity_id)

        # Persist state changes (fire-and-forget non-blocking save)
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._save_sync)
        except RuntimeError:
            self._save_sync()

    def get_snapshot(self, sections: list[str], capped: bool = True) -> dict:
        """Ritorna lo snapshot filtrato per sezioni richieste.

        Con `capped=True` (default, percorso LLM) ogni sezione a lista viene
        tagliata al proprio limite e il taglio viene dichiarato nella chiave
        `truncated`: `{"<sezione>": {"shown": N, "total": M}}`. Senza quella
        dichiarazione il modello concluderebbe che i problemi sono meno di
        quanti sono davvero.

        Con `capped=False` (dashboard di configurazione) non si taglia nulla:
        li' mostrare tutto ha senso e non costa token. Il dato interno non
        viene mai mutato dal troncamento: il file su disco resta completo.
        """
        want_all = "all" in sections
        result: dict = {}
        truncated: dict = {}

        def _cap(nome: str, valori: Any, limite: int) -> Any:
            """Taglia `valori` a `limite` e registra il totale reale.

            Unico punto di verita' per la regola di taglio: gestisce sia le
            liste sia i dizionari (system_health e' indicizzato per dominio).
            Lavora sempre su una copia, il dato interno non viene mutato.
            """
            if not capped:
                return valori
            if isinstance(valori, list):
                if len(valori) <= limite:
                    return valori
                truncated[nome] = {"shown": limite, "total": len(valori)}
                return valori[:limite]
            if isinstance(valori, dict):
                if len(valori) <= limite:
                    return valori
                truncated[nome] = {"shown": limite, "total": len(valori)}
                return dict(list(valori.items())[:limite])
            return valori

        if want_all or "unavailable" in sections:
            entita = self._snapshot_data["unavailable_entities"]
            if capped and isinstance(entita, list):
                # La lista e' mantenuta solo in append da on_state_changed e
                # sopravvive ai riavvii: e' quindi ordinata dalla caduta piu'
                # vecchia. Tagliando le prime N i dispositivi morti da mesi
                # occuperebbero stabilmente la finestra e una rottura appena
                # avvenuta non comparirebbe mai -- il verso sbagliato per un
                # cap che serve proprio a mostrare cosa conta. Ordiniamo per
                # `since` decrescente su una copia (sorted), cosi' le mostrate
                # sono le piu' recenti.
                entita = sorted(entita, key=_quando, reverse=True)
            result["unavailable"] = _cap(
                "unavailable", entita, MAX_UNAVAILABLE_ENTITIES
            )
            if "unavailable" in truncated:
                # Senza questo l'LLM sa quante ne mancano ma non QUALI vede.
                truncated["unavailable"]["order"] = "most_recent_first"
        if want_all or "integrations" in sections:
            result["integrations"] = _cap(
                "integrations",
                self._snapshot_data["integration_errors"],
                MAX_INTEGRATION_ERRORS,
            )
        if want_all or "logs" in sections:
            logs = self._snapshot_data["error_log_summary"]
            if capped and isinstance(logs, dict) and isinstance(logs.get("top_errors"), list):
                # Copia superficiale: i conteggi errors/warnings restano quelli
                # reali, si taglia solo l'elenco dei top errori.
                logs = dict(logs)
                logs["top_errors"] = _cap(
                    "logs.top_errors", logs["top_errors"], MAX_TOP_ERRORS
                )
            result["logs"] = logs
        if want_all or "updates" in sections:
            result["updates"] = _cap(
                "updates", self._snapshot_data["updates_available"], MAX_UPDATES
            )
        if want_all or "system" in sections:
            # Dizionario a chiavi fisse (versione, stato): non cresce, non si taglia.
            result["system"] = self._snapshot_data["system_info"]
        if want_all or "system_health" in sections:
            # Lettura difensiva: il file su disco puo' essere stato scritto da
            # una versione precedente o modificato a mano.
            health = self._snapshot_data.get("system_health")
            if isinstance(health, dict) and health:
                result["system_health"] = _cap(
                    "system_health", health, MAX_SYSTEM_HEALTH_DOMAINS
                )
        if want_all or "supervisor" in sections:
            supervisor = self._snapshot_data.get("supervisor")
            # Sezione composta: `{"addons": [], "disk": {}, "updates": []}` e'
            # truthy ma non ha nulla da dire (v. _ha_contenuto). Vale anche in
            # lettura, non solo in refresh: un file scritto da una versione
            # precedente puo' contenere la sezione vuota.
            if _ha_contenuto(supervisor):
                supervisor = dict(supervisor)
                supervisor["addons"] = _cap(
                    "supervisor.addons", supervisor.get("addons", []), MAX_ADDONS
                )
                supervisor["updates"] = _cap(
                    "supervisor.updates",
                    supervisor.get("updates", []),
                    MAX_SUPERVISOR_UPDATES,
                )
                result["supervisor"] = supervisor

        if truncated:
            result["truncated"] = truncated
        result["last_updated"] = self._snapshot_data.get("last_updated")
        return result
