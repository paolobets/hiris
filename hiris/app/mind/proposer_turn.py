"""Il turno del **proponente** (`docs/design/2026-09-21-l-attuatore.md`, §2;
piano degli attori, strato 4, D12).

Fino al 06/10/2026 si chiamava attuatore: il nome nuovo e' D11 del piano degli
attori, strati 3-4.

**Propone con gli strumenti, e chiude con un esito per osservazione** (D12,
approvata il 03/10/2026). Riceve le osservazioni dell'analista che restano dopo
la sua indagine (quelle `spiegato` sono chiuse), i lettori dell'analista e lo
stesso `propose` della chat. L'officina compone e valida **dentro** il turno:
se rifiuta, il modello vede il perche' e corregge. Fino a qui l'intenzione
viaggiava nella risposta finale, e un rifiuto dell'officina arrivava dopo il
turno: la proposta si perdeva fino al giorno dopo (R0, M2: 2 su 2).

Il turno si chiude con un JSON: per ogni osservazione **«costruita»**, **«da
fare a mano»** (cosa e perche') o **«niente»** (perche'). L'identificativo di
una proposta costruita lo registra l'archivio delle costruzioni col turno
accanto (`ConstructionStore.proposed_in`), non lo scrive il modello: il
modello lo cita, e il codice accetta solo un id nato in questo turno. Cosi'
non puo' dichiarare una proposta che non c'e'.

Il modello dice cosa ha fatto, il codice **valida e rifiuta**: ogni esito
storto si dice, e l'osservazione resta aperta per il giro dopo; quelli buoni
si tengono. Non tocca la casa: `propose` compone e non scrive (il cancello
§7.1, `tests/test_mind_actuator_guards.py`).
"""
from __future__ import annotations

import logging

from ..steering import PROPOSER_SPECIES, SPECIES, read_json, refused_lines, refused_tool
from .analyst import evidence_of, observation_key
from .analyst_turn import READERS, AnalystDispatcher

logger = logging.getLogger(__name__)

#: La specie di turno, per il ponte e per il runner: una vista sulla
#: dichiarazione del mestiere. Fino al 06/10/2026 era «attuazione»: l'attore
#: si chiama proponente (D11 del piano degli attori, strati 3-4).
PROPOSAL_TURN_KIND = SPECIES[PROPOSER_SPECIES].kind

#: **Il tetto della risposta, dichiarato** (Tappa 6, Task 4; D3, approvata
#: il 05/10/2026). Fino a quel giorno questo mestiere non ne passava nessuno e
#: prendeva i 4.096 di fabbrica di `claude_runner.MAX_TOKENS`: lo stesso
#: numero, scelto da nessuno. Qui e' lo stesso valore SCRITTO -- il
#: comportamento non cambia, diventa visibile. **Non e' misurato**: per il
#: proponente non c'e' una misura, e il valore lo sceglie la misura dal vivo
#: della chiusura dello strato 4 (Task 4.8).
MAX_ANSWER_TOKENS = 4096

#: Lo strumento con cui propone: lo STESSO della chat, chiesto per nome alla
#: tabella degli strumenti (`home_space/tools.TOOLS`), mai ricopiato.
PROPOSE = "propose"

#: Gli esiti che il modello puo' dare a un'osservazione (D12).
BUILT = "costruita"
BY_HAND = "a_mano"
NOTHING = "niente"
OUTCOMES = (BUILT, BY_HAND, NOTHING)

#: Perche' una proposta da fare a mano si chiude `superata` (D24-1): la stessa
#: frase dal giro e dal «Rifalla», scritta una volta.
SUPERSEDED_WHY = "ora c'e' una proposta che HIRIS puo' costruire"

#: Dove gli esiti stanno nell'analisi: accanto alle osservazioni a cui
#: rispondono, uno per osservazione. «Costruita» e «da fare a mano» col solo id
#: della proposta (un riferimento, non una copia: testo, perche' e prova
#: vivono nel loro archivio), «niente» col perche', che non vive altrove.
#: Anche «da fare a mano» ci sta dal 06/10/2026: una proposta a mano in attesa
#: torna al turno (D24-1), e senza l'esito accanto il giro la richiederebbe a
#: ogni battito invece che una volta per analisi.
OUTCOMES_KEY = PROPOSER_SPECIES

SYSTEM = """Sei il proponente di HIRIS, un sistema che guarda una casa domotica.

L'analista ha gia' indagato: ti consegna le osservazioni che restano aperte.
Il tuo mestiere e' UNO: per ognuna, decidere **se c'e' qualcosa da proporre**.

Tre esiti, e nessun altro:

1. COSTRUITA -- e' un oggetto che Home Assistant sa tenere (un'automazione,
   uno script, una scena, un helper). Lo componi chiamando `propose`:
   l'officina lo valida contro questa casa e ti risponde con l'id della
   proposta, oppure ti dice perche' non va. Se non va, correggi e richiama.
   Nella risposta citi l'id che `propose` ti ha dato.
2. A MANO -- e' una cosa che deve fare una persona: molte cose utili non sono
   oggetti di Home Assistant, e proporle come tali le fa fallire.
3. NIENTE -- hai guardato e non c'e' niente da proporre. E' un esito
   legittimo, e va detto perche'.

Hai i lettori (search, related, history, mind) per guardare la casa prima di
proporre: un'automazione su un'entita' che non hai visto e' un'ipotesi.

**Non tocchi la casa.** `propose` non scrive niente: le proposte le decide
chi amministra la casa, una per una.

**Non inventare.** Se non hai potuto verificare qualcosa, dillo nel perche':
una proposta inventata e' peggio di nessuna proposta."""

ANSWER_CONTRACT = """Rispondi SOLO con un oggetto JSON di questa forma, con UN
esito per ogni osservazione dell'elenco:

{"esiti": [
  {"osservazione": <il numero dell'osservazione, come nell'elenco>,
   "esito": "costruita" | "a_mano" | "niente",
   "proposta_id": "<per costruita: l'id che `propose` ti ha dato>",
   "testo": "<per a_mano: cosa fare, in una frase>",
   "perche": "<per a_mano e niente: perche'>"}
]}

Un esito «costruita» senza una chiamata riuscita a `propose` in questo turno
viene rifiutato: l'id lo conosce l'officina, non si scrive a memoria. Fa
eccezione una proposta dell'elenco «gia' costruite», se c'e': quella si cita
col suo id, senza rifarla."""


def proposer_tools() -> list[dict]:
    """Il catalogo del turno: i lettori dell'analista (`analyst_turn.READERS`)
    piu' `propose`, con gli STESSI dizionari della chat (`KNOWLEDGE_TOOLS`,
    filtrati e non copiati). La definizione di `propose` si chiede alla
    tabella (voce del BACKLOG del 05/10, «La definizione di `propose` torna
    alla tabella degli strumenti»)."""
    from ..home_space.tools import KNOWLEDGE_TOOLS

    wanted = (*READERS, PROPOSE)
    admitted = [d for d in KNOWLEDGE_TOOLS if d["name"] in wanted]
    if len(admitted) != len(wanted):
        # Uno strumento rinominato nella chat svuoterebbe il catalogo IN
        # SILENZIO: si dichiara, come per l'analista.
        logger.error("catalogo del proponente incompleto: mancano %s",
                     sorted(set(wanted) - {d["name"] for d in admitted}))
    return admitted


class ProposerDispatcher(AnalystDispatcher):
    """Il guardiano del turno: il guardiano dell'analista -- i lettori, e la
    maschera dei nomi delle persone -- **meno `compute` e piu' `propose`**.

    Lo stesso oggetto risponde sulla catena (`proposer_round`) e sul ponte
    (`/api/mcp`, `steering.Species.guard`). Il dispatcher sotto e' quello
    della chat, firmato dal proponente (`create_tool_dispatcher(actor=...)`):
    l'officina scrive chi ha proposto, e con quale turno.
    """

    async def dispatch(self, name: str, arguments: dict | None) -> dict:
        if name == PROPOSE:
            # **Nessuno parla al proponente**: `frase` e' «la frase di chi ti
            # sta parlando, verbatim», e qualunque cosa ci scrivesse sarebbe
            # una citazione inventata, archiviata accanto alla proposta.
            asked = {k: v for k, v in (arguments or {}).items() if k != "frase"}
            return self._covered(
                await self._below.dispatch(name, self._uncovered(asked)))
        if name not in READERS:
            return refused_tool(
                name, doing="mentre propongo",
                instead="Se serve un oggetto di Home Assistant, proponilo con "
                        "`propose`; se serve una persona, scrivilo come «a_mano».")
        return await super().dispatch(name, arguments)


async def guard(app, exchange: str | None = None, *,
                kind: type[ProposerDispatcher] = ProposerDispatcher,
                refuse_high: bool = False,
                species: str = PROPOSER_SPECIES) -> ProposerDispatcher:
    """Il dispatcher di un turno del proponente, sulla catena e sul ponte.

    `exchange` e' l'identita' del turno (sulla catena la conia il giro, sul
    ponte e' `X-HIRIS-Turno`): l'officina la scrive accanto a ogni proposta, e
    da li' il giro rilegge quali sono nate nel turno.

    `kind` e `refuse_high` li cambia «Rendila automatica»
    (`automate_turn.guard`): lo stesso dispatcher firmato dal proponente, con
    davanti il suo guardiano, e l'officina che rifiuta il livello `alto`.

    `species` e' il mestiere che apre il turno, e da lui si chiede il soffitto
    (`steering.Species.ceiling`, decisione 13): la firma nella cronaca resta
    quella del proponente, che e' chi propone."""
    from ..api.handlers_chat import create_tool_dispatcher
    from ..home_space.house import House
    from ..home_space.privacy import PresenceMask

    store = app.get("home_space_store")
    house = House.read(store, app.get("entity_cache")) if store is not None else None
    below = create_tool_dispatcher(app, exchange=exchange, house=house,
                                   actor=PROPOSER_SPECIES, refuse_high=refuse_high,
                                   soffitto=SPECIES[species].ceiling())
    return kind(below, ha=None, house=None, timezone=None,
                presence=PresenceMask(house) if house is not None else None)


def outcomes_of(analysis: dict | None) -> list[dict]:
    """Gli esiti del proponente scritti accanto all'analisi."""
    return list(((analysis or {}).get(OUTCOMES_KEY)) or [])


def latest_decided(*sources: dict) -> dict[str, dict]:
    """Le proposte gia' fatte, dai due archivi, in un dizionario solo: per
    ogni impronta vince la piu' recente (`creata_ts`).

    Le proposte da fare a mano e quelle costruite vivono in due archivi
    (`mind/store.proposte`, `revisions.costruzioni`), con la stessa forma.
    Fino al 06/10/2026 si leggeva solo il primo, e una costruita non fermava
    niente: la stessa domanda con la stessa prova tornava all'officina a ogni
    giro (revisione indipendente, giro 24, D24-2).
    """
    merged: dict[str, dict] = {}
    for source in sources:
        for key, entry in (source or {}).items():
            if key not in merged or entry["creata_ts"] >= merged[key]["creata_ts"]:
                merged[key] = entry
    return merged


def already_answered(observation: dict, decided: dict) -> str | None:
    """Perche' questa domanda non va chiesta di nuovo, o `None` se va.

    `decided` e' `latest_decided` dei due archivi: per impronta, l'ultima
    proposta. **Una costruita in attesa non si duplica.** Una decisa vale
    finche' vale la prova contro cui e' stata decisa: a prova cambiata la
    domanda torna (S-26, scelta del proprietario del 06/10/2026). Una **da
    fare a mano in attesa torna al turno** (D24-1, stessa data): adesso il
    modello potrebbe costruirla, e se la costruisce quella a mano si chiude
    `superata`. Il motivo e' una frase: chi salta lo scrive nel registro,
    perche' una proposta potata in silenzio il 01/10/2026 e' costata una
    diagnosi (misura del Task 4.0 degli attori).

    **Una costruita scaduta senza risposta conta come decisa** (revisione,
    giro 61): a prova uguale non torna. E' la lettera di S-26, dove torna
    solo cio' che aspetta (D24-1) o cio' la cui prova e' cambiata, e il
    silenzio di chi amministra vale come risposta: riproporre ogni giorno la
    stessa bozza ignorata sarebbe la coda che cresce che S-26 toglie. Scelta
    del proprietario del 06/10/2026 («Resta cosi'»): una scaduta torna solo
    se la prova cambia.
    """
    entry = decided.get(observation_key(observation))
    if entry is None:
        return None
    if entry["aperta"]:
        return None if entry["a_mano"] else "ha gia' una proposta costruita in attesa"
    if entry["prova"] == evidence_of(observation):
        return "e' gia' stata decisa con la stessa prova"
    return None


def open_observations(analysis: dict | None, decided: dict,
                      skipped: list | None = None) -> list[dict]:
    """Le osservazioni che aspettano il proponente, nell'ordine dell'analisi.

    Restano fuori:
    - quelle **chiuse dall'indagine dell'analista** (`spiegato`): D1 del
      refactor, l'indagine e' sua, e cio' che ha spiegato non e' una
      domanda aperta;
    - quelle con un esito gia' scritto accanto a questa analisi: un giro
      chiede una volta per analisi;
    - quelle che `already_answered` salta (`decided`, da `latest_decided`).
      Una proposta rifiutata torna in coda solo se la prova cambia: e' cio'
      che la rotta delle proposte promette (`api/handlers_proposals.py`).

    `skipped`, se c'e', riceve `(impronta, motivo)` di ogni osservazione
    saltata da `already_answered`, per chi lo scrive nel registro.
    """
    done = {o.get("impronta") for o in outcomes_of(analysis)}
    seen = []
    for observation in (analysis or {}).get("osservazioni") or []:
        if not isinstance(observation, dict) or observation.get("spiegato"):
            continue
        key = observation_key(observation)
        if key in done:
            continue
        reason = already_answered(observation, decided)
        if reason is not None:
            if skipped is not None:
                skipped.append((key, reason))
            continue
        seen.append(observation)
    return seen


def build_question(observations, *, refused: list[str] | None = None,
                   presence=None, unbound=()) -> str | None:
    """La domanda intera, o `None` se non c'e' niente da chiedere.

    Le osservazioni si consegnano **numerate**, e il modello si riferisce a
    una col suo numero: ricopiarne il testo vorrebbe dire poterlo sbagliare.
    `refused` sono i problemi della risposta di prima (D10); `presence` copre
    i nomi delle persone, con la stessa numerazione del guardiano.
    `unbound` sono le proposte gia' costruite che nessun esito ha citato
    (`ConstructionStore.unbound`): si mostrano perche' il modello le citi
    invece di costruirle una seconda volta (revisione, giro 61).
    """
    rows = list(observations or [])
    if not rows:
        return None
    lines = ["Le osservazioni dell'analista rimaste aperte, numerate:"]
    for index, row in enumerate(rows):
        lines.extend(observation_lines(index, row))
    lines.append("")
    if unbound:
        lines.append("Le proposte gia' costruite in un turno di prima, che nessun "
                     "esito ha citato. Se una risponde a un'osservazione, citala "
                     "con «costruita» e il suo id, senza rifarla:")
        lines.extend(f"  {row['id']}: {row.get('anteprima') or row.get('chiave')}"
                     for row in unbound)
        lines.append("")
    lines.extend(refused_lines(refused))
    lines.append(ANSWER_CONTRACT)
    question = "\n".join(lines)
    return presence.mask(question) if presence is not None else question


def observation_lines(index: int, row: dict) -> list[str]:
    """Un'osservazione come la legge il proponente, col suo numero: la stessa
    forma per il giro e per il «Rifalla» (`mind/proposal_redo.py`)."""
    lines = [f"  [{index}] {row.get('nome') or row.get('soggetto')} · "
             f"{row.get('misura')}"
             + (f" ({row.get('chiave')})" if row.get("chiave") else ""),
             f"      cosa ha visto: {row.get('cosa')}"]
    if row.get("cosa_cambierebbe"):
        lines.append(f"      cosa cambierebbe: {row.get('cosa_cambierebbe')}")
    if row.get("da_riverificare"):
        lines.append(f"      da riverificare: {row.get('da_riverificare')}")
    base = row.get("base")
    lines.append(f"      si regge su {base} giorni di storia"
                 if base else "      non ha una storia dietro")
    return lines


def bridge_turn(observations, *, refused: list[str] | None = None,
                presence=None, unbound=()) -> dict | None:
    """Il turno da accodare al ponte, o `None` se non c'e' da chiedere: la
    stessa forma di `analyst_turn.bridge_turn`."""
    question = build_question(observations, refused=refused, presence=presence,
                              unbound=unbound)
    if question is None:
        return None
    return {"history": [{"role": "user", "content": question}],
            "system_prompt": SYSTEM,
            "istruzione": ANSWER_CONTRACT}


def _text(value) -> str | None:
    text = str(value or "").strip() if isinstance(value, str) else ""
    return text or None


def apply_outcomes(observations, answer: str, *, built=frozenset(),
                   truncated: bool = False, presence=None) -> dict:
    """Cosa si fa della risposta: si valida esito per esito.

    Torna `{"esiti": [...], "problemi": [...], "risposta": bool}`. Ogni esito
    buono porta l'impronta della sua osservazione (dal codice, non dal
    modello) e i campi del suo tipo. **Un esito storto non fa cadere gli
    altri**: si dice nei problemi, e la sua osservazione resta aperta per il
    giro dopo. Tutti i problemi si dicono insieme: dirne uno per giro
    costringerebbe a rieseguire il turno per scoprire il successivo.

    `built` sono gli id delle proposte nate in questo turno
    (`ConstructionStore.proposed_in`) e di quelle gia' costruite che nessun
    esito ha citato (`ConstructionStore.unbound`): un «costruita» con un id
    fuori da qui si rifiuta, e cosi' uno che un altro esito ha gia' citato.
    `presence` riporta agli id veri i segnaposto che il modello ha
    scritto nei testi.
    """
    # Il JSON lo cava il lettore unico (`steering.read_json`, D-11), come per
    # l'analista: un turno troncato non si legge (D2).
    data, reason = read_json(answer, shape=dict, what="un oggetto con gli esiti",
                             truncated=truncated)
    if data is None:
        return {"esiti": [], "problemi": [reason],
                "risposta": bool(str(answer or "").strip())}
    given = data.get("esiti")
    if not isinstance(given, list):
        return {"esiti": [], "risposta": True,
                "problemi": ["la risposta non porta un elenco `esiti`"]}

    rows = list(observations or [])
    problems: list[str] = []
    kept: dict[int, dict] = {}
    named: set[int] = set()
    cited: set[str] = set()
    for index, outcome in enumerate(given):
        if not isinstance(outcome, dict):
            problems.append(f"l'esito {index} non e' un oggetto")
            continue
        which = outcome.get("osservazione")
        if not isinstance(which, int) or isinstance(which, bool) \
                or not 0 <= which < len(rows):
            problems.append(
                f"l'esito {index} nomina l'osservazione {which!r}, che non e' "
                f"nell'elenco (ce ne sono {len(rows)})")
            continue
        if which in named:
            problems.append(f"l'osservazione {which} ha piu' di un esito")
            kept.pop(which, None)
            continue
        named.add(which)
        kind = outcome.get("esito")
        entry = {"impronta": observation_key(rows[which]), "esito": kind}
        if kind == BUILT:
            ident = outcome.get("proposta_id")
            if ident not in built:
                problems.append(
                    f"l'esito {index} dice «{BUILT}» con l'id {ident!r}, ma ne' "
                    "in questo turno ne' fra le gia' costruite c'e' una "
                    "proposta con quell'id: una proposta nasce chiamando "
                    "`propose`")
                continue
            if ident in cited:
                problems.append(f"l'esito {index} cita la proposta {ident!r}, "
                                "gia' citata da un altro esito: una proposta "
                                "risponde a una domanda sola")
                continue
            cited.add(ident)
            entry |= {"proposta_id": ident, "osservazione": rows[which]}
        elif kind == BY_HAND:
            what, why = _text(outcome.get("testo")), _text(outcome.get("perche"))
            if what is None or why is None:
                problems.append(f"l'esito {index} e' «{BY_HAND}» e vuole "
                                "`testo` e `perche`")
                continue
            entry |= {"testo": what, "perche": why, "osservazione": rows[which]}
        elif kind == NOTHING:
            why = _text(outcome.get("perche"))
            if why is None:
                problems.append(f"l'esito {index} e' «{NOTHING}» e vuole `perche`")
                continue
            entry["perche"] = why
        else:
            problems.append(f"l'esito {index} porta {kind!r}: gli esiti sono "
                            + ", ".join(OUTCOMES))
            continue
        kept[which] = entry
    missing = [n for n in range(len(rows)) if n not in named]
    if missing:
        problems.append("non hanno un esito le osservazioni "
                        + ", ".join(str(n) for n in missing))
    outcomes = [kept[n] for n in sorted(kept)]
    if presence is not None:
        outcomes = [{**o, **{k: presence.unmask(o[k]) for k in ("testo", "perche")
                             if k in o}} for o in outcomes]
    return {"esiti": outcomes, "problemi": problems, "risposta": True}
