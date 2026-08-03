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
_VALID_PROPOSAL_TYPES = frozenset({"ha_automation", "hiris_agent"})
# Alias comuni che gli LLM usano al posto dei valori canonici (root cause bug #2:
# il Chatbot ha proposto type='automation').
_PROPOSAL_TYPE_ALIASES = {"automation": "ha_automation", "agent": "hiris_agent"}

CREATE_AUTOMATION_PROPOSAL_TOOL_DEF = {
    "name": "create_automation_proposal",
    "description": (
        "Propose a new automation to the user. Use this after explaining your "
        "routing choice (HA native vs HIRIS agent). The proposal is saved as "
        "disabled/pending — the user must explicitly activate it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["ha_automation", "hiris_agent"]},
            "name": {"type": "string"},
            "description": {
                "type": "string",
                "description": "Human-readable explanation of what this does",
            },
            "config": {
                "type": "object",
                "description": (
                    "HA automation YAML dict (trigger/condition/action/mode/alias) "
                    "or HIRIS agent config dict. To MODIFY an existing automation, "
                    "INCLUDE its numeric 'id' (as returned by get_automation_config) "
                    "in this config. Its entity_id (e.g. 'automation.foo') or bare "
                    "object_id (e.g. 'foo') are ALSO accepted here, but are NOT "
                    "the same guarantee as the numeric id: they are looked up "
                    "against Home Assistant only when the user APPROVES the "
                    "proposal, not now. If at that point none of them resolves to "
                    "an existing automation, approval FAILS outright — nothing is "
                    "created or overwritten. To create a NEW automation, OMIT "
                    "'id' entirely. Caveat: if you omit 'id' but 'config' has an "
                    "'alias' matching the friendly_name of an automation that "
                    "already exists, approval overwrites THAT one instead of "
                    "creating a duplicate — this is deliberate (avoids duplicates "
                    "when re-proposing an edit without the id), but means the "
                    "alias alone decides the target: reuse the exact existing "
                    "name only when you mean to overwrite it."
                ),
            },
            "routing_reason": {
                "type": "string",
                "description": "Why this level was chosen over the alternative",
            },
            "automation_id": {
                "type": "string",
                "description": (
                    "Optional. The numeric unique id of an existing HA automation "
                    "to MODIFY — or its entity_id (e.g. 'automation.foo') or bare "
                    "object_id (e.g. 'foo') if you only have that (looked up at "
                    "approval time; approval fails if none resolves — see "
                    "'config' above for what that means). Alternative to putting "
                    "'id' inside config (this param wins if both are given). Omit "
                    "for a brand-new automation."
                ),
            },
        },
        "required": ["type", "name", "description", "config", "routing_reason"],
    },
}


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
