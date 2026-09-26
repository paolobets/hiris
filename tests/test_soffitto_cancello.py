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
    # Dal 26/09/2026 (spec 2026-09-26 §3, decisioni 5 e 6) la pagina
    # Costruzioni, le proposte a mano e le correzioni al sapere sono di chi
    # costruisce: stavano in `ESENTI` perche' «non toccano Home Assistant», e
    # la ragione nuova non e' Home Assistant ma di chi sono.
    "POST /api/constructions/{id}/reject":
        "dire di no a una proposta è decidere cosa si costruisce in casa, e "
        "la coda delle proposte è di chi costruisce (decisione 5)",
    "POST /api/proposals/{id}/reject":
        "stesso rifiuto, sull’archivio gemello delle proposte da fare a mano: "
        "stessa pagina, stesso padrone",
    "POST /api/proposals/{id}/done":
        "chiude una proposta come applicata: è una decisione sulla coda, e la "
        "coda è di chi costruisce",
    "POST /api/proposals/{id}/redo":
        "fa rifare una proposta al modello, e la paga: è un gesto sulla coda "
        "di chi costruisce",
    "POST /api/mind/judgment":
        "corregge ciò che HIRIS ha capito della casa per tutti quelli che ci "
        "vivono: le correzioni al sapere sono di chi amministra (decisione 6)",
    "POST /api/services/window/close":
        "la richiude. Passa dallo stesso soffitto dell’apertura perché un "
        "estraneo che potesse chiuderla toglierebbe al proprietario "
        "l’accoppiamento che ha appena aperto",
}

#: Le rotte mutanti ESENTI, ognuna con la ragione per cui lo è. Non e' una
#: copia di niente: e' la decisione, scritta. Una rotta nuova non entra qui da
#: sola -- va messa a mano, ed e' li' che qualcuno deve pensarci.
ESENTI = {
    "POST /api/agenda/read":
        "segna come letti degli esiti già mostrati: non tocca la casa",
    "DELETE /api/agenda/{id}":
        "disdice una promessa. Toglie un potere invece di darne uno, e vietarlo "
        "a chi non è amministratore vorrebbe dire che non può fermare ciò che "
        "ha messo in moto",
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
        "tests/test_mcp_chat_thread.py)",
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
    «applica» sia «rimetti com'era». Dal 26/09/2026 chiede al cancello di
    tutta la pagina, `require_builder` (spec 2026-09-26 §3: «`_act` passa
    alla stessa funzione, una regola, non due»).

    Mutazione ESEGUITA: tolto `require_builder` da `_act` -- rossa.
    """
    sorgente = (RADICE / "hiris" / "app" / "api"
                / "handlers_constructions.py").read_text(encoding="utf-8")
    albero = ast.parse(sorgente)
    atto = next(n for n in ast.walk(albero)
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "_act")
    chiamate = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                for n in ast.walk(atto) if isinstance(n, ast.Call)}

    assert "require_builder" in chiamate, (
        "`_act` non interroga più il cancello: le due scritture verso Home "
        "Assistant sono tornate a passare senza chiedere chi le chiede")


# --- il cancello di chi costruisce (spec 2026-09-26 §3) ----------------------

#: I prefissi delle rotte che sono di chi costruisce. **E' la decisione**
#: (spec 2026-09-26 §0, decisioni 5 e 6), non una copia: le rotte sotto questi
#: prefissi si CHIEDONO al router, e una rotta nuova sotto uno di essi entra
#: da sola nella verifica.
_BUILDER_PREFIXES = ("/api/constructions", "/api/proposals", "/api/mind/judgment")

_API = RADICE / "hiris" / "app" / "api"


def builder_routes() -> dict[str, str]:
    """`"METODO percorso" -> nome del gestore`, DERIVATO dal router: ogni
    metodo, letture comprese -- la pagina e' di chi costruisce anche quando
    guarda."""
    sorgente = _SERVER.read_text(encoding="utf-8")
    trovate = {f"{metodo.upper()} {percorso}": gestore
               for metodo, percorso, gestore in re.findall(
                   r'router\.add_(get|post|put|patch|delete)\("([^"]+)",\s*(\w+)\)',
                   sorgente)
               if percorso.startswith(_BUILDER_PREFIXES)}
    for prefisso in _BUILDER_PREFIXES:
        assert any(r.split(" ", 1)[1].startswith(prefisso) for r in trovate), (
            f"nessuna rotta derivata sotto {prefisso}: la derivazione si è "
            "rotta, e un cancello che deriva male sembra vivo mentre non "
            "guarda più niente")
    return trovate


def _funzioni_api() -> dict[str, ast.AsyncFunctionDef]:
    funzioni = {}
    for percorso in _API.glob("handlers_*.py"):
        for nodo in ast.walk(ast.parse(percorso.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.AsyncFunctionDef):
                funzioni[nodo.name] = nodo
    return funzioni


def _first_statement(funzione: ast.AsyncFunctionDef) -> ast.stmt:
    corpo = funzione.body
    if (corpo and isinstance(corpo[0], ast.Expr)
            and isinstance(corpo[0].value, ast.Constant)):
        corpo = corpo[1:]  # la docstring
    return corpo[0]


def _chiama(istruzione: ast.stmt) -> set[str]:
    return {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            for n in ast.walk(istruzione) if isinstance(n, ast.Call)}


def _gate_comes_first(nome: str, funzioni: dict) -> bool:
    """La PRIMA istruzione del gestore chiama `require_builder` -- o delega
    subito a un aiutante di `api/` (`return await _act(...)`) la cui prima
    istruzione lo chiama. «Per prima» e non «da qualche parte»: il cancello
    deve venire prima di qualunque archivio (`store.scadi` scrive)."""
    prima = _first_statement(funzioni[nome])
    chiamate = _chiama(prima)
    if "require_builder" in chiamate:
        return True
    aiutanti = [c for c in chiamate if c in funzioni and c != nome]
    return (isinstance(prima, ast.Return) and len(aiutanti) == 1
            and "require_builder" in _chiama(_first_statement(funzioni[aiutanti[0]])))


def test_ogni_rotta_di_chi_costruisce_passa_PER_PRIMA_dal_cancello():
    """**Il cancello delle decisioni 5 e 6.** Ogni gestore registrato sotto
    `/api/constructions`, `/api/proposals` e `/api/mind/judgment` chiama
    `soffitto.require_builder` come prima cosa. Una rotta nuova sotto questi
    prefissi entra da sola in questa verifica.

    Mutazioni ESEGUITE: tolto `require_builder` da `handle_proposal_redo` --
    rossa col nome della rotta; spostato dopo `store.scadi` in
    `handle_get_constructions` -- rossa; aggiunta a `server.py` una
    `router.add_get("/api/proposals/prova", handle_get_pending)` -- rossa.
    """
    funzioni = _funzioni_api()
    scoperte = sorted(rotta for rotta, gestore in builder_routes().items()
                      if gestore not in funzioni
                      or not _gate_comes_first(gestore, funzioni))

    assert not scoperte, (
        f"rotte di chi costruisce senza il cancello davanti: {scoperte}. La "
        "pagina Costruzioni, le proposte e i giudizi sono di chi costruisce "
        "(spec 2026-09-26 §3): la prima istruzione del gestore è "
        "`require_builder`")


def test_la_derivazione_delle_rotte_di_chi_costruisce_VEDE_le_rotte_vere():
    """La prova che la derivazione non si e' rotta: le rotte che la spec
    nomina (§3) stanno fra quelle derivate. Se la forma delle registrazioni in
    `server.py` cambiasse, la regex non ne troverebbe piu' e la prova sopra
    sarebbe verde su un insieme vuoto.

    Mutazione ESEGUITA: `add_(post|put|patch|delete)` al posto di
    `add_(get|post|put|patch|delete)` nella regex -- rossa (le due GET
    mancano)."""
    derivate = set(builder_routes())

    assert {"GET /api/constructions", "GET /api/constructions/{id}",
            "POST /api/constructions/{id}/confirm",
            "POST /api/constructions/{id}/restore",
            "POST /api/constructions/{id}/reject",
            "POST /api/proposals/{id}/reject", "POST /api/proposals/{id}/done",
            "POST /api/proposals/{id}/redo", "POST /api/mind/judgment"} <= derivate
