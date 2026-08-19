"""Il turno che si sveglia per una promessa «chiedi»: guarda, e risponde.

Non e' autonomia -- il QUANDO l'ha deciso l'utente -- ma e' un modello che
gira SENZA NESSUNO DAVANTI, e questo cambia cosa gli si mette in mano.

Il catalogo qui e' un ELENCO DI AMMISSIONE (`SOLA_LETTURA`), non di esclusione.
Con un elenco di esclusione, uno strumento nuovo che scrive entrerebbe qui da
solo il giorno in cui qualcuno lo aggiunge alla chat, e nessuno se ne
accorgerebbe. Il verso di questa derivazione e' una questione di sicurezza, non
di stile.

`concludi` esiste SOLO in questo catalogo: dalla chat non si vede, perche' li'
a concludere e' la risposta all'utente. E' l'unico modo in cui questo turno
puo' finire, ed e' cio' che rende il SILENZIO un fatto dichiarato invece di
un'assenza da interpretare.
"""
from __future__ import annotations

import logging

from ..casa.strumenti import STRUMENTI_CONOSCENZA

logger = logging.getLogger(__name__)

# I quattro che leggono e basta. Non `esegui` (tocca la casa), non `ricorda`
# (scrive nella memoria, che entra verbatim nel prompt di sistema), non
# `prometti`/`disdici` (un turno che si da' appuntamenti da solo e' autonomia
# costruita per sbaglio).
SOLA_LETTURA = ("cerca", "guarda", "legami", "richiama")

CONCLUDI_TOOL_DEF = {
    "name": "concludi",
    "description": (
        "Chiudi questa promessa dicendo cosa hai trovato. E' l'UNICO modo in cui "
        "questo turno puo' finire: se non lo chiami, chi ti ha svegliato non "
        "sapra' cosa dire alla persona. `avvisare` dice se c'e' qualcosa per cui "
        "valga la pena disturbarla: mettilo a `false` quando la condizione che ti "
        "era stata chiesta NON si e' verificata -- non e' un fallimento, e' la "
        "risposta giusta, e viene comunque registrata. `testo` e' cio' che le "
        "diresti: una o due frasi, con i numeri veri e le loro unita', non un "
        "riassunto vago. Non puoi toccare la casa da qui: se la risposta implica "
        "un'azione, dilla come proposta e sara' la persona a decidere."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "avvisare": {
                "type": "boolean",
                "description": "Se c'e' qualcosa da dire adesso alla persona.",
            },
            "testo": {
                "type": "string",
                "description": "Cosa hai trovato, in una o due frasi, coi numeri veri.",
            },
        },
        "required": ["avvisare", "testo"],
    },
}


def strumenti_promessa() -> list[dict]:
    """Il catalogo di questo turno, DERIVATO da quello della chat.

    Le definizioni sono gli STESSI dizionari di `STRUMENTI_CONOSCENZA`, non
    copie: una descrizione migliorata li' vale anche qui, senza che nessuno se
    ne debba ricordare.
    """
    ammessi = [d for d in STRUMENTI_CONOSCENZA if d["name"] in SOLA_LETTURA]
    if len(ammessi) != len(SOLA_LETTURA):
        # Un nome ammesso che non esiste piu' nel catalogo della chat (un
        # rinomino) svuoterebbe questo catalogo IN SILENZIO, lasciando il turno
        # cieco. Si dichiara.
        trovati = {d["name"] for d in ammessi}
        logger.error("catalogo della promessa incompleto: mancano %s",
                     sorted(set(SOLA_LETTURA) - trovati))
    return ammessi + [CONCLUDI_TOOL_DEF]


class DispatcherPromessa:
    """Il guardiano del turno: lascia scendere solo i lettori, e tiene `concludi`.

    Sta DAVANTI a `DispatcherStrumenti` invece di modificarlo, per non mettere
    nel dispatcher della chat uno strumento che li' non deve esistere.
    """

    def __init__(self, sotto) -> None:
        self._sotto = sotto
        self.conclusione: dict | None = None

    async def dispatch(self, nome: str, argomenti: dict | None) -> dict:
        argomenti = argomenti or {}
        if nome == "concludi":
            avvisare = argomenti.get("avvisare")
            testo = argomenti.get("testo")
            if not isinstance(avvisare, bool) or not isinstance(testo, str):
                return {"errore": ("«concludi» vuole `avvisare` (vero o falso) e "
                                   "`testo` (cosa hai trovato).")}
            self.conclusione = {"avvisare": avvisare, "testo": testo}
            return {"concluso": True}
        if nome not in SOLA_LETTURA:
            return {"errore": ("«%s» non e' disponibile mentre mantengo una "
                               "promessa: qui posso guardare e rispondere, non "
                               "toccare la casa. Se serve un'azione, dilla nel "
                               "testo e decidera' la persona." % nome)}
        return await self._sotto.dispatch(nome, argomenti)


async def interpreta_promessa(app, promessa: dict) -> dict:
    """Sveglia il modello per una promessa «chiedi». Non solleva mai.

    Ritorna `{"avvisare": bool, "testo": str}` oppure `{"errore": str}`. Un
    turno che finisce senza chiamare `concludi` e' un errore dichiarato, non un
    «forse e' andata bene».
    """
    from ..api.handlers_casa import costruisci_nucleo
    from ..api.handlers_chat import costruisci_dispatcher_strumenti

    runner = app.get("llm_router") or app.get("claude_runner")
    if runner is None:
        return {"errore": "non c'era nessun modello a cui chiedere."}

    dispatcher = DispatcherPromessa(costruisci_dispatcher_strumenti(app))
    try:
        # Lo STESSO nucleo della chat (`costruisci_nucleo`), non una
        # composizione parallela: due contesti che descrivono la stessa casa
        # sono due verita' che divergono.
        nucleo, _riepilogo = costruisci_nucleo(app)
    except Exception as errore:
        logger.warning("nucleo non componibile per la promessa %s (%s: %s)",
                       promessa["id"], type(errore).__name__, errore)
        nucleo = ""

    try:
        await runner.chat(
            user_message=_domanda(promessa),
            system_prompt=_prompt_di_sistema(),
            context_str=nucleo,
            conversation_history=[],
            model="auto",
            max_tokens=2000,
            agent_type="promessa",
            thinking_budget=0,
            strumenti=strumenti_promessa(),
            dispatcher=dispatcher,
        )
    except Exception as errore:
        logger.warning("turno della promessa %s fallito (%s: %s)",
                       promessa["id"], type(errore).__name__, errore)
        return {"errore": "il modello non ha risposto (%s)." % type(errore).__name__}

    if dispatcher.conclusione is None:
        return {"errore": "il turno non ha concluso: non so cosa dirti."}
    return dispatcher.conclusione


def _prompt_di_sistema() -> str:
    return (
        "Stai mantenendo una promessa: qualcuno ti ha chiesto, tempo fa, di "
        "guardare qualcosa a quest'ora e di dirgli com'e' andata. Adesso non c'e' "
        "nessuno davanti allo schermo.\n"
        "Guarda con gli strumenti che hai, poi chiama SEMPRE «concludi». Se la "
        "condizione che ti era stata chiesta non si e' verificata, concludi con "
        "avvisare=false: e' la risposta giusta, non un fallimento.\n"
        "Non puoi toccare la casa da qui. Se cio' che hai trovato richiede "
        "un'azione, scrivila come proposta nel testo."
    )


def _domanda(promessa: dict) -> str:
    """La domanda, con l'istantanea di partenza accanto.

    L'istantanea porta valore, unita' e istante della misura: senza, «e'
    aumentata» non ha un termine di paragone e il modello se lo inventerebbe.
    """
    righe = ["Me l'hai chiesto cosi': «%s»." % promessa["frase"],
             "Quello che devi guardare: %s" % promessa["domanda"]]
    for misura in promessa.get("istantanea") or []:
        righe.append(
            "Quando me l'hai chiesto, %s era %s%s (misurato allora, non adesso)."
            % (misura.get("entita"), misura.get("valore"),
               (" " + misura["unita"]) if misura.get("unita") else ""))
    return "\n".join(righe)
