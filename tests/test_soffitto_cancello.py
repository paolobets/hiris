"""Il cancello dell'invariante I-1: nessuna rotta mutante senza una decisione.

L'invariante dice che **ogni richiesta ha un soggetto e il soggetto sopravvive
fino all'atto**. Una difesa del genere non si rompe per un errore: si rompe per
una ROTTA NUOVA che nasce mesi dopo, scritta da chi non ha letto niente di
questa conversazione, e che nessuno collega al soffitto.

Quindi il cancello non verifica il codice di oggi -- lo verificano le prove
accanto -- ma **che nessuna rotta mutante esista senza che qualcuno abbia
deciso cosa farne**.

**L'elenco delle rotte si CHIEDE al router** (I-0, 21/09): una POST nuova
compare qui il giorno in cui nasce, non il giorno in cui qualcuno si ricorda di
aggiungerla. Cio' che resta scritto a mano e' la CLASSIFICAZIONE, che non
ricopia niente: enuncia la decisione, e chiude per difetto -- una rotta non
classificata fa diventare rosso questo file.
"""
import ast
import pathlib
import re

RADICE = pathlib.Path(__file__).resolve().parents[1]
_SERVER = RADICE / "hiris" / "app" / "server.py"

#: Le rotte mutanti che PASSANO dal soffitto, perche' toccano Home Assistant
#: in un modo che Home Assistant stesso negherebbe a chi non e' amministratore.
SOFFITTATE = {
    "POST /api/constructions/{id}/confirm":
        "scrive automazioni, script o scene in Home Assistant",
    "POST /api/constructions/{id}/restore":
        "riscrive o cancella l’oggetto: è la stessa scrittura di «applica»",
    "POST /api/chat":
        "il modello può chiamare «confirm», che è la stessa porta vista dal "
        "lato della conversazione: il soffitto viaggia nel dispatcher",
    "POST /api/services/approve":
        "dà a una macchina il diritto di parlare con HIRIS, e HIRIS parla con "
        "Home Assistant col proprio token di amministratore: approvare un "
        "servizio è scrivere un permesso che HA negherebbe a un non "
        "amministratore",
    "POST /api/services/revoke":
        "toglie quel permesso, e chi non può darlo non deve poterlo togliere: "
        "spegnere il pannello di casa d’altri è un gesto da amministratore "
        "quanto accenderlo",
    "POST /api/services/window/open":
        "apre l’unica superficie non autenticata di questo prodotto, per dieci "
        "minuti: esporla è un gesto da amministratore come scrivere "
        "un’automazione",
    "POST /api/services/window/close":
        "la richiude. Passa dallo stesso soffitto dell’apertura perché un "
        "estraneo che potesse chiuderla toglierebbe al proprietario "
        "l’accoppiamento che ha appena aperto",
}

#: Le rotte mutanti ESENTI, ognuna con la ragione per cui lo è. Non e' una
#: copia di niente: e' la decisione, scritta. Una rotta nuova non entra qui da
#: sola -- va messa a mano, ed e' li' che qualcuno deve pensarci.
ESENTI = {
    "POST /api/constructions/{id}/reject":
        "dire di no non scrive niente in Home Assistant, e chiuderlo dietro un "
        "permesso lascerebbe in coda per sempre, a chi non può costruire, una "
        "proposta che non vuole",
    "POST /api/proposals/{id}/reject":
        "stesso rifiuto, sull’archivio gemello delle proposte da fare a mano",
    "POST /api/proposals/{id}/done":
        "dichiara che l’ha fatta una persona FUORI da Home Assistant: HIRIS non "
        "scrive niente e non può verificarlo in nessun oggetto",
    "POST /api/proposals/{id}/redo":
        "rifà il testo di una proposta: non tocca la casa, e la proposta resta "
        "in attesa di una decisione che passerà dalle rotte sopra",
    "POST /api/agenda/read":
        "segna come letti degli esiti già mostrati: non tocca la casa",
    "DELETE /api/agenda/{id}":
        "disdice una promessa. Toglie un potere invece di darne uno, e vietarlo "
        "a chi non è amministratore vorrebbe dire che non può fermare ciò che "
        "ha messo in moto",
    "POST /api/mind/judgment":
        "corregge un giudizio nel sapere di HIRIS: scrive nel nostro archivio, "
        "mai in Home Assistant",
    "POST /api/mind/objective":
        "l’obiettivo dell’osservatore, nel nostro archivio",
    "DELETE /api/memories/{id}":
        "i ricordi sono di HIRIS, non di Home Assistant",
    "PATCH /api/memories/{id}":
        "correggere un ricordo tocca il sapere di HIRIS, non la casa: e chi non "
        "può correggere ciò che HIRIS ha capito di lui resta descritto male",
    "DELETE /api/chat/history":
        "la conversazione è di HIRIS",
    "PUT /api/chat-settings":
        "le impostazioni della chat sono di HIRIS",
    "PUT /api/models/config":
        "la catena dei modelli è di HIRIS, e non nomina nessuna entità",
    "POST /api/usage/reset":
        "azzera i contatori dei consumi, che sono nostri",
    "POST /api/mcp":
        "porta un token, non una persona: il suo perimetro è l’invariante dei "
        "canali esterni. Quando serve un turno di chat il soffitto è quello "
        "della persona del job, e viaggia nel dispatcher (`X-HIRIS-Chat`, "
        "tests/test_mcp_chat_chat_thread.py)",
    "POST /api/reasoning/claim":
        "il worker del ponte, che porta un token e non una persona — stesso "
        "rinvio di «/api/mcp»",
    "POST /api/reasoning/submit":
        "la consegna del turno dallo stesso worker del ponte: token e non "
        "persona, e il suo perimetro è l’invariante dei canali esterni",
    "POST /api/services/present":
        "**l’unica superficie che questo prodotto non può autenticare**, e "
        "deve esserlo: un servizio non ancora approvato non ha modo di "
        "autenticarsi. Non ha un soggetto da far passare da nessun soffitto — "
        "non autorizza niente, mette in coda una richiesta che il proprietario "
        "vedrà. La sua difesa è un’altra: esiste solo nei dieci minuti in cui "
        "la finestra è aperta, e il confine la rifiuta fuori di lì "
        "(`test_servizi_rotte.py`)",
}


def rotte_mutanti() -> set[str]:
    """Ogni rotta che scrive, DERIVATA dal router — mai elencata a mano."""
    sorgente = _SERVER.read_text(encoding="utf-8")
    trovate = {f"{metodo.upper()} {percorso}"
               for metodo, percorso in re.findall(
                   r'router\.add_(post|put|patch|delete)\("([^"]+)"', sorgente)}
    assert len(trovate) > 10, (
        f"ne ho derivate solo {len(trovate)}: la derivazione si è rotta, e un "
        "cancello che deriva male sembra vivo mentre non guarda più niente")
    return trovate


def test_ogni_rotta_mutante_e_CLASSIFICATA():
    """**Il cancello.** Una rotta nuova che scrive nasce oggi e nessuno la
    collega al soffitto: fra sei mesi e' un buco che nessun cancello vede.

    Qui non puo' succedere: la rotta compare da sola nell'insieme derivato, e
    finche' nessuno decide cosa farne questo file e' rosso.

    Mutazione ESEGUITA: aggiunta una `router.add_post("/api/prova", ...)` a
    `server.py` -- rossa, col nome della rotta nel messaggio.
    """
    classificate = set(SOFFITTATE) | set(ESENTI)
    indecise = rotte_mutanti() - classificate

    assert not indecise, (
        "rotte che scrivono e su cui nessuno ha deciso se passano dal "
        f"soffitto: {sorted(indecise)}. Non si aggiunge una riga a "
        "`ESENTI` per far tacere questo cancello: si guarda se quella rotta "
        "tocca Home Assistant in un modo che HA negherebbe a un non "
        "amministratore, e la ragione si scrive accanto")


def test_la_classificazione_non_nomina_rotte_che_NON_esistono():
    """La contropartita: una rotta cancellata lascerebbe qui una riga che
    descrive un mondo che non c'e' piu', e il prossimo lettore la crederebbe.

    Mutazione: lasciare in `ESENTI` una rotta rimossa da `server.py` -- rossa."""
    classificate = set(SOFFITTATE) | set(ESENTI)
    fantasmi = classificate - rotte_mutanti()

    assert not fantasmi, f"classificate ma inesistenti: {sorted(fantasmi)}"


def test_ogni_esenzione_porta_la_sua_RAGIONE():
    """Un'esenzione senza motivo e' indistinguibile da una dimenticanza, e fra
    sei mesi nessuno sapra' se quella rotta fu valutata o solo saltata.

    Mutazione: mettere una stringa vuota come ragione -- rossa."""
    for rotta, perche in {**SOFFITTATE, **ESENTI}.items():
        assert perche and len(perche) > 20, (
            f"«{rotta}» e' classificata senza una ragione leggibile")


def test_le_due_scritture_verso_home_assistant_passano_DAVVERO_dal_soffitto():
    """La classificazione dice cosa DOVREBBE passare dal soffitto; questa prova
    guarda se ci passa davvero, altrimenti sarebbe un elenco di buone
    intenzioni.

    Il punto unico e' `handlers_constructions._act`, da cui passano sia
    «applica» sia «rimetti com'era».

    Mutazione ESEGUITA: tolto `per_richiesta` da `_act` -- rossa.
    """
    sorgente = (RADICE / "hiris" / "app" / "api"
                / "handlers_constructions.py").read_text(encoding="utf-8")
    albero = ast.parse(sorgente)
    atto = next(n for n in ast.walk(albero)
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "_act")
    chiamate = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                for n in ast.walk(atto) if isinstance(n, ast.Call)}

    assert "per_richiesta" in chiamate, (
        "`_act` non interroga più il soffitto: le due scritture verso Home "
        "Assistant sono tornate a passare senza chiedere chi le chiede")
