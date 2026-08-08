from __future__ import annotations
import logging
from typing import Any

from ..proxy.ha_client import is_automation_config, is_automation_id_candidate

logger = logging.getLogger(__name__)

# Tipi che QUESTO tool puo' creare. Un tipo fuori da questo set e' rifiutato
# alla creazione invece di essere salvato e perso in silenzio nel ramo
# "status-only" dell'apply (marca applied senza toccare HA, bug #2).
# Volutamente PIU' STRETTO dei tipi che handle_apply_proposal sa applicare
# (che include anche ha_dashboard/ha_script/ha_scene, per le proposte gia'
# salvate): create_automation_proposal non valida nulla di specifico per le
# plance, quindi accettare qui 'ha_dashboard' sarebbe una scorciatoia per
# saltare la validazione fail-closed di propose_dashboard (formato url_path,
# presenza delle viste, limite di dimensione, titolo obbligatorio). Le plance
# si propongono SOLO con propose_dashboard.
# fetta E3 Task 3: "hiris_agent" (e il suo alias "agent") sono usciti insieme
# all'intero strato Agentbot -- handle_apply_proposal non sa piu' materializzarlo
# (watcher.agentbots e' cancellato), quindi accettarlo qui alla creazione
# produrrebbe solo una proposta destinata a un vicolo cieco dichiarato.
_VALID_PROPOSAL_TYPES = frozenset({"ha_automation"})
# Alias comuni che gli LLM usano al posto dei valori canonici (root cause bug #2:
# il Chatbot ha proposto type='automation').
_PROPOSAL_TYPE_ALIASES = {"automation": "ha_automation"}

# `CREATE_AUTOMATION_PROPOSAL_TOOL_DEF` e' uscita in fetta E2 Task 8: non
# nominata da `EVALUATION_ONLY_TOOLS` (crea una proposta -- chat-only, vedi il
# commento su quel catalogo in claude_runner.py), e la chat nuova non passa
# piu' da un catalogo di trentaquattro (STRUMENTI_CONOSCENZA, quattro
# strumenti che conoscono la casa e basta -- casa/strumenti.py). La funzione
# sotto resta: la chiama davvero la Sentinella (server.py, ramo delle
# proposte di automazione), non e' orfana.


async def create_automation_proposal(
    proposal_store: Any,
    proposal_type: str,
    name: str,
    description: str,
    config: dict,
    routing_reason: str,
    automation_id: str | None = None,
) -> dict:
    if proposal_store is None:
        return {"error": "ProposalStore not available"}
    # Bug #2: normalizza gli alias di tipo e rifiuta i tipi sconosciuti. Il
    # Chatbot aveva proposto type='automation' (non 'ha_automation') -> l'apply
    # cadeva nel ramo status-only che NON scrive in HA (l'automazione "sembrava
    # applicata" ma non cambiava). Meglio fallire forte alla creazione.
    proposal_type = (proposal_type or "").strip()
    proposal_type = _PROPOSAL_TYPE_ALIASES.get(proposal_type, proposal_type)
    if proposal_type not in _VALID_PROPOSAL_TYPES:
        return {"error": (f"Tipo proposta non valido: {proposal_type!r}. "
                          f"Usa uno di: {', '.join(sorted(_VALID_PROPOSAL_TYPES))}. "
                          "Per proporre una plancia Lovelace usa il tool "
                          "propose_dashboard.")}
    # Bug #2 (overwrite vs duplicato): l'id nel config e' load-bearing all'apply
    # (create_automation vi sovrascrive l'automazione con quell'id). Precedenza:
    # automation_id esplicito > id gia' presente nel config (che l'LLM copia
    # leggendo l'automazione con get_automation_config). Se NESSUNO dei due c'e'
    # -> automazione NUOVA (nessun id, apply ne conia uno). Contratto invertito
    # rispetto a prima (che strippava l'id senza automation_id, rompendo il caso
    # "modifica"): ORA per creare una NUOVA automazione l'LLM deve OMETTERE l'id.
    cfg = config
    if proposal_type == "ha_automation":
        # Bug live-verify #3: prima di qui il tipo era validato ma la FORMA
        # no -- una config senza trigger/azioni (o un id palesemente non
        # risolvibile) veniva salvata cosi' com'e' e falliva solo all'apply,
        # con un 502 verso l'utente al posto di un errore azionabile per il
        # modello che l'ha scritta. Questo percorso (dalla chat) era anche
        # l'unico dei tre a non avere is_automation_config. M-3: la
        # coverage-review passa gia' da qui (Brain, server.py._mk_proposal);
        # la Sentinella NO -- propone uno SCRIPT (sentinel_proposal), non
        # un'automazione, e non passa mai da is_automation_config: e' fuori
        # perimetro per costruzione, non "gia' coperta".
        if not isinstance(cfg, dict) or not is_automation_config(cfg):
            return {"error": (
                "config automazione non valida: servono i trigger e le azioni "
                "(oppure use_blueprint). Per modificare un'automazione "
                "esistente leggi la sua config con get_automation_config e "
                "modificala; per crearne una nuova scrivi trigger e azioni.")}
        _id = automation_id or cfg.get("id")
        if _id:
            _id = str(_id)
            # C-2: il gate qui deve rifiutare SOLO cio' che l'apply
            # (create_automation) rifiuterebbe di sicuro. create_automation
            # accetta tre forme per un id fornito (numerico, entity_id,
            # object_id nudo -- lo stesso contratto di get_automation_config,
            # che il messaggio d'errore sotto cita come fonte del valore
            # giusto): prima di is_automation_id_candidate questo gate ne
            # riconosceva solo due, rifiutando proposte che l'apply avrebbe
            # applicato. Non si duplica qui la RISOLUZIONE (che serve
            # get_automations, quindi l'accesso a HA, e resta in
            # create_automation): si valida solo la FORMA, con lo stesso
            # predicato che usa create_automation.
            if not is_automation_id_candidate(_id):
                return {"error": (
                    f"id automazione non valido: {_id!r}. Per una automazione "
                    "nuova ometti 'id'; per modificarne una esistente usa "
                    "l'id numerico che torna da get_automation_config, oppure "
                    "l'entity_id (es. 'automation.nome_automazione') o "
                    "l'object_id nudo (es. 'nome_automazione').")}
            cfg = {**cfg, "id": _id}
        elif "id" in cfg:
            # M-1: un id FALSY (es. {"id": 0}) salta il ramo "if _id" sopra e
            # verrebbe persistito cosi' com'e' -- la proposta salvata
            # mostrerebbe un id che pero' all'apply si comporta come assente
            # (create_automation fa `automation_id or config.get("id") or ""`:
            # 0 e' falsy, quindi aid diventa ""). Si normalizza qui: la chiave
            # sparisce invece di restare a mentire nella proposta salvata.
            cfg = {k: v for k, v in cfg.items() if k != "id"}
    try:
        pid = await proposal_store.save(
            {
                "type": proposal_type,
                "name": name,
                "description": description,
                "config": cfg,
                "routing_reason": routing_reason,
            }
        )
        return {
            "proposal_id": pid,
            "status": "pending",
            "message": (
                f"Proposta '{name}' salvata. "
                "L'utente può attivarla dalla sezione Proposte."
            ),
        }
    except Exception as exc:
        # Never echo str(exc) back to the caller (same policy as the
        # dispatcher's own catch-all, dispatcher.py's bottom except): it can
        # leak internal detail (e.g. a raw sqlite3.OperationalError with a
        # file path). Log server-side, return a generic-but-useful message.
        logger.exception("create_automation_proposal: save failed")
        return {"error": "Impossibile salvare la proposta. Riprova più tardi."}
