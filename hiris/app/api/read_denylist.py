"""Denylist di lettura per il gateway MCP.

Gli strumenti di AZIONE che passano da `/api/execute` sono vincolati da una
whitelist derivata dai domini che l'utente ha marcato verdi nel semaforo. Gli
strumenti di LETTURA no, e per una ragione buona: quella whitelist e' derivata
dai domini AZIONABILI, quindi applicarla alle letture nasconderebbe ogni entita'
fuori da essi -- configurato il gateway per comandare le luci, non si potrebbe
piu' chiedere la temperatura. Il risultato pero' e' che ogni lettura vede tutta
la casa: `get_history` puo' restituire lo storico della serratura.

Questo modulo aggiunge il rovescio della whitelist: un elenco di entita' o
domini che non escono MAI dal gateway. Si elencano le poche cose sensibili
invece di enumerare tutta la casa, e non si nasconde nessun sensore.

DUE LATI, e il secondo e' quello che regge tutto
------------------------------------------------
Filtrare gli argomenti in ingresso NON BASTA. Diverse letture non prendono
affatto un'entita': `get_home_status` restituisce l'intera casa,
`get_logbook` senza `entity_id` elenca tutti gli eventi, `get_advisories`
porta identificativi dentro le evidenze, `get_area_entities` elenca per area.
Se il perimetro valesse solo sugli argomenti, basterebbe OMETTERE il parametro
per aggirarlo -- lo stesso difetto gia' trovato e chiuso su `get_logbook` lato
chat. Quindi:

1. in ingresso una richiesta che nomina un'entita' coperta viene RIFIUTATA
   (un errore e' diagnosticabile, un risultato vuoto no);
2. in uscita la risposta viene POTATA, dichiarando il taglio con la stessa
   convenzione `filtered: {shown, total}` gia' usata da `get_logbook` e
   `get_advisories`, cosi' il modello remoto sa che sta vedendo una parte.

FAIL-CLOSED SULLE FORME NON RICONOSCIUTE
----------------------------------------
La potatura deve conoscere la forma della risposta di ogni strumento, e
ciascuno ce l'ha diversa. Una forma che non si sa potare non viene lasciata
passare: si blocca e si registra nel log. Meglio un gateway che risponde "non
so filtrare questa risposta" di uno che fa uscire una serratura.

LIMITE DICHIARATO
-----------------
`recall_knowledge` restituisce testo libero della memoria, non entita'. Se un
appunto contiene un dato sensibile scritto a mano, nessuna denylist per entita'
puo' intercettarlo: quel caso NON e' coperto qui e non deve sembrarlo.
"""
from __future__ import annotations

import fnmatch
import logging
import re
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# Valore predefinito protettivo: la protezione non deve dipendere dal
# ricordarsi di configurarla. Copre i domini sensibili IN LETTURA -- serrature,
# pannelli d'allarme, telecamere, e le entita' di presenza (`person`,
# `device_tracker`) che rivelano quando la casa e' vuota.
#
# NON coincide con `security.semaphore.DANGEROUS_DOMAINS`, che riguarda
# l'AZIONE: una tapparella e' pericolosa da muovere ma innocua da leggere, una
# telecamera e' l'opposto. Sono due nozioni diverse ed e' giusto che restino
# separate: riusare quella costante qui accoppierebbe due elenchi che devono
# poter evolvere in direzioni opposte.
DEFAULT_READ_DENYLIST: tuple[str, ...] = (
    "lock.*",
    "alarm_control_panel.*",
    "camera.*",
    "person.*",
    "device_tracker.*",
)

# Marcatore delle letture della CHAT in-addon. La chat via abbonamento passa
# dall'MCP interno (loopback) e da li' rientra in `/api/execute` con lo stesso
# internal token del gateway: senza un discriminante la denylist -- pensata per
# la superficie REMOTA -- accecherebbe anche la chat locale, dove vale invece il
# perimetro del Chatbot. Il discriminante NON puo' essere il campo `origin`, che
# e' fornito dal chiamante e quindi falsificabile da chi tiene il token: e' un
# segreto di processo generato all'avvio (`app["local_execute_token"]`), che il
# solo `LocalExecuteClient` conosce. L'assenza del marcatore vale "remoto",
# quindi un anello rotto nel cablaggio protegge di piu', non di meno.
LOCAL_CHAT_HEADER = "X-HIRIS-Local-Chat"

# entity_id canonico (dominio.oggetto), come in diagnostics_tools e ha_client.
_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")

_MSG_BLOCCO = (
    "HIRIS non sa applicare la denylist di lettura alla risposta di {tool!r}: "
    "risposta bloccata per prudenza. Se serve davvero, aggiorna la denylist "
    "nelle opzioni dell'add-on o segnalalo all'amministratore di HIRIS."
)


class _FormaNonPotabile(Exception):
    """Forma di risposta che la potatura non sa trattare: si blocca."""


def parse_read_denylist(raw: str | None) -> list[str]:
    """Costruisce la denylist dal CSV di glob delle opzioni dell'add-on.

    `None` (variabile d'ambiente non esportata: un anello della catena di
    configurazione manca) vale il DEFAULT protettivo. Una stringa vuota vale
    invece l'elenco VUOTO: svuotare la denylist e' una decisione dell'utente e
    ripristina il comportamento precedente, quindi deve restare esprimibile.
    """
    if raw is None:
        return list(DEFAULT_READ_DENYLIST)
    return [p.strip() for p in raw.split(",") if p.strip()]


def is_denied(entity_id: Any, denylist: Sequence[str]) -> bool:
    """Vero se questo identificativo e' coperto dalla denylist.

    Denylist vuota -> nulla e' vietato (semantica opposta a quella di una
    whitelist vuota, dove nulla e' permesso: qui l'elenco enumera cio' che si
    nega, li' cio' che si concede).
    """
    if not denylist:
        return False
    if not isinstance(entity_id, str):
        return False
    return any(fnmatch.fnmatch(entity_id, pat) for pat in denylist)


def denied_entities_in_inputs(inputs: Any, denylist: Sequence[str]) -> list[str]:
    """Entita' vietate nominate esplicitamente negli argomenti della richiesta.

    Non si guardano chiavi note (`entity_id`, `entity_ids`, `ids`, ...) ma
    QUALUNQUE valore che abbia la forma di un entity_id: un nome di parametro
    dimenticato sarebbe un buco silenzioso, e i nomi dei parametri cambiano piu'
    spesso della forma di un identificativo. `automation_id` e' l'unico caso
    speciale, perche' arriva anche nella forma nuda ('apri_porta') che diventa
    entity_id solo col prefisso del dominio.
    """
    if not denylist or not isinstance(inputs, dict):
        return []
    candidati: list[str] = []
    for chiave, valore in inputs.items():
        if chiave == "automation_id" and isinstance(valore, str) and valore:
            candidati.append(valore if valore.startswith("automation.")
                             else f"automation.{valore}")
            continue
        for v in (valore if isinstance(valore, list) else [valore]):
            if isinstance(v, str) and _ENTITY_ID_RE.match(v):
                candidati.append(v)
    return sorted({c for c in candidati if is_denied(c, denylist)})


# ---------------------------------------------------------------------------
# Potatura per forma di risposta
# ---------------------------------------------------------------------------

def _id_di(voce: Any) -> str:
    if not isinstance(voce, dict):
        raise _FormaNonPotabile("voce dell'elenco non e' un oggetto")
    eid = voce.get("id", voce.get("entity_id"))
    if not isinstance(eid, str):
        raise _FormaNonPotabile("voce dell'elenco senza identificativo")
    return eid


def _pota_elenco(result: Any, denylist: Sequence[str], *, chiave: str) -> Any:
    """Elenco di entita' (`get_home_status`, `get_entity_states`, `get_history`).

    Il risultato di questi tool e' una LISTA nuda, che non ha dove ospitare la
    dichiarazione del taglio. Quando qualcosa viene tolto si passa a un oggetto
    {<chiave>: [...], filtered: {...}}: il cambio di forma avviene SOLO se c'e'
    un taglio da dichiarare, ed e' esso stesso la spiegazione del cambio. Senza
    tagli la lista esce identica, cosi' il caso normale resta il caso di prima.
    """
    if not isinstance(result, list):
        raise _FormaNonPotabile("atteso un elenco")
    tenute = [v for v in result if not is_denied(_id_di(v), denylist)]
    if len(tenute) == len(result):
        return result
    return {chiave: tenute, "filtered": {"shown": len(tenute), "total": len(result)}}


def _pota_aree(result: Any, denylist: Sequence[str]) -> Any:
    """Mappa area -> [entity_id] (`get_area_entities`).

    Si tolgono gli identificativi vietati dentro ogni area e poi le aree
    rimaste vuote: un'area presente ma vuota direbbe al modello "qui non c'e'
    niente", che e' falso.
    """
    if not isinstance(result, dict):
        raise _FormaNonPotabile("attesa una mappa area -> entita'")
    tenute: dict[str, list[str]] = {}
    letti = 0
    mostrati = 0
    for area, ids in result.items():
        if not isinstance(ids, list):
            raise _FormaNonPotabile("valore di un'area non e' un elenco")
        ammesse: list[str] = []
        for eid in ids:
            if not isinstance(eid, str):
                raise _FormaNonPotabile("identificativo di area non testuale")
            letti += 1
            if not is_denied(eid, denylist):
                ammesse.append(eid)
        mostrati += len(ammesse)
        if ammesse:
            tenute[area] = ammesse
    if mostrati == letti:
        return result
    return {"areas": tenute, "filtered": {"shown": mostrati, "total": letti}}


def _pota_logbook(result: Any, denylist: Sequence[str]) -> Any:
    """Cronologia degli eventi (`get_logbook`).

    Una voce SENZA `entity_id` -- avvio di Home Assistant, script, eventi di
    sistema -- non e' attribuibile a un'entita' vietata e resta. E' l'opposto
    della scelta che lo stesso tool fa sotto whitelist (li' una voce non
    verificabile si scarta), e non e' un'incoerenza: una whitelist enumera cio'
    che si concede, quindi cio' che non e' verificabile non e' concesso; una
    denylist enumera cio' che si nega, quindi cio' che non e' nominato non e'
    negato. Scartare qui ogni voce di sistema svuoterebbe la cronologia senza
    proteggere nulla.
    """
    if not isinstance(result, dict) or not isinstance(result.get("entries"), list):
        raise _FormaNonPotabile("atteso un oggetto con 'entries'")
    voci = result["entries"]
    tenute = []
    for v in voci:
        if not isinstance(v, dict):
            raise _FormaNonPotabile("voce di cronologia non e' un oggetto")
        if not is_denied(v.get("entity_id"), denylist):
            tenute.append(v)
    if len(tenute) == len(voci):
        return result
    potato = dict(result)
    potato["entries"] = tenute
    potato["count"] = len(tenute)
    potato["filtered"] = {"shown": len(tenute), "total": len(voci)}
    return potato


def _pota_advisories(result: Any, denylist: Sequence[str]) -> Any:
    """Segnalazioni del Brain (`get_advisories`).

    Due strade da chiudere: la segnalazione il cui `evidence.entity_id` e'
    un'entita' vietata (batteria della serratura), e la segnalazione di sistema
    la cui evidenza porta un CAMPIONE di identificativi di tutta la casa
    (`evidence.entities`). Restringere il campione non cambia il contratto: e'
    gia' un estratto, e il totale reale sta in `evidence.count`.
    """
    if not isinstance(result, dict) or not isinstance(result.get("advisories"), list):
        raise _FormaNonPotabile("atteso un oggetto con 'advisories'")
    voci = result["advisories"]
    tenute = []
    for v in voci:
        if not isinstance(v, dict):
            raise _FormaNonPotabile("segnalazione non e' un oggetto")
        evidenza = v.get("evidence")
        if not isinstance(evidenza, dict):
            tenute.append(v)
            continue
        if is_denied(evidenza.get("entity_id"), denylist):
            continue
        elencate = evidenza.get("entities")
        if isinstance(elencate, list):
            ammesse = [e for e in elencate if not is_denied(e, denylist)]
            if len(ammesse) != len(elencate):
                # Taglio DENTRO una voce che resta visibile: si dichiara sulla
                # voce, accanto a `evidence_truncated` che il tool usa per il
                # taglio di dimensione. Un solo `filtered` sulla risposta
                # confonderebbe due tagli diversi (quante voci vedi / quanti
                # identificativi vedi dentro una voce).
                v = {**v, "evidence": {**evidenza, "entities": ammesse},
                     "evidence_filtered": {"shown": len(ammesse),
                                           "total": len(elencate)}}
        tenute.append(v)
    if tenute == voci:
        return result
    potato = dict(result)
    potato["advisories"] = tenute
    potato["count"] = len(tenute)
    if len(tenute) != len(voci):
        potato["filtered"] = {"shown": len(tenute), "total": len(voci)}
    return potato


def _identificativi_annidati(nodo: Any, trovati: list[str]) -> None:
    if isinstance(nodo, dict):
        for v in nodo.values():
            _identificativi_annidati(v, trovati)
    elif isinstance(nodo, list):
        for v in nodo:
            _identificativi_annidati(v, trovati)
    elif isinstance(nodo, str) and _ENTITY_ID_RE.match(nodo):
        trovati.append(nodo)


def _pota_config_automazione(result: Any, denylist: Sequence[str]) -> Any:
    """Configurazione di un'automazione (`get_automation_config`).

    Non e' un elenco potabile: togliere un trigger o un'azione restituirebbe
    una configurazione DIVERSA da quella vera, e il modello la leggerebbe come
    autentica. Quindi o e' pulita o si blocca. La scansione e' ricorsiva e
    volutamente larga -- vale su qualunque stringa a forma di entity_id, ovunque
    si trovi -- perche' la struttura di un'automazione e' libera e un elenco di
    campi noti resterebbe indietro alla prima forma nuova.
    """
    if not isinstance(result, dict):
        raise _FormaNonPotabile("attesa una configurazione")
    trovati: list[str] = []
    _identificativi_annidati(result, trovati)
    if any(is_denied(e, denylist) for e in trovati):
        raise _FormaNonPotabile("la configurazione nomina un'entita' della denylist")
    return result


def _pota_conoscenza(result: Any, denylist: Sequence[str]) -> Any:
    """Memoria (`recall_knowledge`): testo libero, nessuna entita' da potare.

    Passa invariato, ed e' il LIMITE DICHIARATO del design: un appunto scritto a
    mano che contiene un dato sensibile non e' intercettabile da una denylist
    per entita'. Non e' una dimenticanza, ed e' esplicito qui perche' nessuno lo
    scambi per copertura. La forma si controlla comunque: se un giorno questo
    tool restituisse anche identificativi, la forma cambierebbe e si bloccherebbe.
    """
    if not isinstance(result, dict) or not isinstance(result.get("results"), list):
        raise _FormaNonPotabile("atteso un oggetto con 'results'")
    return result


# Registro delle forme note. Un tool di lettura assente da qui NON passa: e' la
# meta' fail-closed del meccanismo, e vale anche per gli strumenti che un domani
# venissero aggiunti a READ_TOOLS senza passare da questo file.
_POTATORI = {
    "get_home_status": lambda r, d: _pota_elenco(r, d, chiave="entities"),
    "get_entity_states": lambda r, d: _pota_elenco(r, d, chiave="entities"),
    "get_history": lambda r, d: _pota_elenco(r, d, chiave="series"),
    "get_area_entities": _pota_aree,
    "get_logbook": _pota_logbook,
    "get_advisories": _pota_advisories,
    "get_automation_config": _pota_config_automazione,
    "recall_knowledge": _pota_conoscenza,
}


def prune_read_result(tool: str, result: Any, denylist: Sequence[str]) -> Any:
    """Pota la risposta di uno strumento di lettura, o la blocca.

    Ritorna la risposta potata (invariata se non c'era nulla da togliere)
    oppure, quando la forma non e' trattabile, un `{"error": ...}` che dichiara
    il blocco. Non fa mai eco del dettaglio interno verso il chiamante: il
    motivo preciso resta nei log.
    """
    if not denylist:
        return result
    # Un tool di lettura che ha gia' fallito ritorna {"error": ...} e basta:
    # forma nota, niente da potare.
    if isinstance(result, dict) and set(result.keys()) == {"error"}:
        return result
    potatore = _POTATORI.get(tool)
    if potatore is None:
        logger.warning(
            "denylist di lettura: nessuna potatura nota per %r -- risposta bloccata", tool)
        return {"error": _MSG_BLOCCO.format(tool=tool)}
    try:
        return potatore(result, denylist)
    except _FormaNonPotabile as motivo:
        logger.warning(
            "denylist di lettura: forma inattesa nella risposta di %r (%s) -- "
            "risposta bloccata", tool, motivo)
        return {"error": _MSG_BLOCCO.format(tool=tool)}
