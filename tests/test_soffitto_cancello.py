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
import pathlib

from tests._avvio import router_routes

RADICE = pathlib.Path(__file__).resolve().parents[1]

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
    "POST /api/proposals/{id}/automate":
        "fa comporre al modello un’automazione per la casa, e la paga: è un "
        "gesto sulla coda di chi costruisce (attori, Task 4.5)",
    "POST /api/mind/judgment":
        "corregge ciò che HIRIS ha capito della casa per tutti quelli che ci "
        "vivono: le correzioni al sapere sono di chi amministra (decisione 6)",
    "POST /api/mind/scope":
        "il togli e il rimetti del proprietario: una decisione con autore "
        "`owner`, che nessun attore può più scavalcare. Decide cosa HIRIS "
        "guarda per tutta la casa, quindi è di chi amministra come i giudizi "
        "(D9 degli attori, Task 3.7)",
    "POST /api/services/window/close":
        "la richiude. Passa dallo stesso soffitto dell’apertura perché un "
        "estraneo che potesse chiuderla toglierebbe al proprietario "
        "l’accoppiamento che ha appena aperto",
}

#: Le rotte mutanti ESENTI, ognuna con la ragione per cui lo è. Non e' una
#: copia di niente: e' la decisione, scritta. Una rotta nuova non entra qui da
#: sola -- va messa a mano, ed e' li' che qualcuno deve pensarci.
#:
#: **Sei ragioni riscritte il 27/09/2026** (spec 2026-09-27 §1 e §3): dicevano
#: «sono di HIRIS», sul presupposto -- falso -- che a `/config` arrivassero
#: solo amministratori. Una persona non amministratrice ci arrivava con due
#: chiamate WebSocket. Adesso la chiude il cancello al confine, perche' non
#: sono nella lista di ammissione (`api/admission.py`).
_CONFINE = ("a una persona che non amministra la chiude il cancello al confine: "
            "non è nella lista di ammissione (`api/admission.py`, spec "
            "2026-09-27 §3). Un servizio firmato come `utente` la raggiunge "
            "ancora, rischio dichiarato (security-constraints 5.9)")
ESENTI = {
    "POST /api/agenda/read":
        "segna come letti degli esiti già mostrati: non tocca la casa",
    "DELETE /api/agenda/{id}":
        "disdice una promessa. Toglie un potere invece di darne uno, e vietarlo "
        "a chi non è amministratore vorrebbe dire che non può fermare ciò che "
        "ha messo in moto",
    "POST /api/mind/objective":
        "l’obiettivo dell’osservatore non tocca Home Assistant, ma è "
        f"configurare HIRIS: {_CONFINE}",
    "DELETE /api/memories/{id}":
        "cancellare un ricordo non tocca Home Assistant, ma è correggere la "
        "memoria di tutta la casa, riservata agli amministratori (decisione 4 "
        f"del 27/09/2026): {_CONFINE}",
    "PATCH /api/memories/{id}":
        "correggere un ricordo non tocca Home Assistant, ma cambia ciò che "
        "HIRIS sa per tutti quelli che ci vivono (decisione 4 del 27/09/2026): "
        f"{_CONFINE}",
    "POST /api/chat/conversations":
        "chiude la conversazione aperta di chi chiede, nel suo filo: la "
        "conversazione è di HIRIS e di chi la fa, non tocca la casa",
    "POST /api/chat/conversations/{id}/resume":
        "riapre una conversazione del filo di chi chiede; l’id di un altro è "
        "un 404 (l’archivio lega id e filo): non tocca Home Assistant",
    "DELETE /api/chat/conversations/{id}":
        "cancella una conversazione del filo di chi chiede, e solo quella: "
        "vietarlo a chi non è amministratore gli impedirebbe di togliere le "
        "proprie parole",
    "PUT /api/chat-settings":
        "le impostazioni della chat non toccano Home Assistant, ma sono la "
        f"configurazione di HIRIS: {_CONFINE}",
    "PUT /api/models/config":
        "la catena dei modelli non nomina nessuna entità, ma decide chi paga "
        f"ogni turno: è configurazione. {_CONFINE}",
    "POST /api/usage/reset":
        "azzerare i contatori dei consumi non tocca Home Assistant, ma cancella "
        f"la misura del proprietario: {_CONFINE}",
    "POST /api/mcp":
        "porta un token, non una persona: il suo perimetro è l’invariante dei "
        "canali esterni. Quando serve un turno di chat il soffitto è quello "
        "della persona del job, e viaggia nel dispatcher (`X-HIRIS-Chat`, "
        "tests/test_mcp_chat_thread.py)",
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
    """Ogni rotta che scrive, DERIVATA dal router vero — mai elencata a mano,
    e mai letta dal testo di `server.py` (Tappa 1 dello sprint «Una fonte
    sola di verita'»: una rotta registrata altrove o in un'altra forma la
    regex non la vedeva, e il cancello restava verde)."""
    trovate = {rotta for rotta in router_routes()
               if rotta.split(" ", 1)[0] in ("POST", "PUT", "PATCH", "DELETE")}
    assert len(trovate) > 10, (
        f"ne ho derivate solo {len(trovate)}: la derivazione si è rotta, e un "
        "cancello che deriva male sembra vivo mentre non guarda più niente")
    return trovate


def test_ogni_rotta_mutante_e_CLASSIFICATA():
    """**Il cancello.** Una rotta nuova che scrive nasce oggi e nessuno la
    collega al soffitto: fra sei mesi e' un buco che nessun cancello vede.

    Qui non puo' succedere: la rotta compare da sola nell'insieme derivato, e
    finche' nessuno decide cosa farne questo file e' rosso.

    Mutazioni ESEGUITE, rosse col nome della rotta nel messaggio: aggiunta una
    `router.add_post("/api/prova", ...)` a `server.py`; aggiunta una
    `app.router.add_route("POST", "/api/prova", ...)`, che la regex di prima
    non vedeva (03/10/2026).
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


# --- il cancello di chi costruisce (spec 2026-09-26 §3) ----------------------

#: I prefissi delle rotte che sono di chi costruisce. **E' la decisione**
#: (spec 2026-09-26 §0, decisioni 5 e 6), non una copia: le rotte sotto questi
#: prefissi si CHIEDONO al router, e una rotta nuova sotto uno di essi entra
#: da sola nella verifica.
_BUILDER_PREFIXES = ("/api/constructions", "/api/proposals", "/api/mind/judgment",
                     "/api/mind/scope")

def builder_routes() -> set[str]:
    """`"METODO modello"`, DERIVATO dal router vero: ogni metodo, letture
    comprese -- la pagina e' di chi amministra anche quando guarda."""
    trovate = {rotta for rotta in router_routes()
               if rotta.split(" ", 1)[1].startswith(_BUILDER_PREFIXES)}
    for prefisso in _BUILDER_PREFIXES:
        assert any(r.split(" ", 1)[1].startswith(prefisso) for r in trovate), (
            f"nessuna rotta derivata sotto {prefisso}: la derivazione si è "
            "rotta, e un cancello che deriva male sembra vivo mentre non "
            "guarda più niente")
    return trovate


def test_ogni_rotta_di_chi_costruisce_chiede_AMMINISTRARE():
    """**Il cancello delle decisioni 5 e 6.** Ogni rotta registrata sotto
    `/api/constructions`, `/api/proposals`, `/api/mind/judgment` e
    `/api/mind/scope` chiede il gesto `amministrare` nella tabella delle rotte
    (`admission.ADMISSION`), che il confine chiede per ogni soggetto prima del
    gestore -- cioe' prima di qualunque archivio. Una rotta nuova sotto questi
    prefissi entra da sola in questa verifica. Fino al 07/10/2026 la prova
    guardava che la prima istruzione di ogni gestore fosse
    `soffitto.require_builder`, uscito col cancello unico (F-01, Tappa 7);
    la proprieta' e' la stessa, la forma no -- comprese le due scritture
    verso Home Assistant di `_act` (applica e rimetti com'era).

    Mutazioni ESEGUITE: la riga `POST /api/proposals/{id}/redo` col gesto
    `leggere` -- rossa col nome della rotta; aggiunta a `server.py` una
    `router.add_get("/api/proposals/prova", handle_get_pending)` -- rossa
    (senza riga, nessun gesto)."""
    from hiris.app.api.admission import ADMISSION

    gesti = {f"{r.method} {r.canonical}": r.gesture for r in ADMISSION}
    scoperte = sorted(rotta for rotta in builder_routes()
                      if gesti.get(rotta) != "amministrare")

    assert not scoperte, (
        f"rotte di chi costruisce senza il gesto `amministrare`: {scoperte}. La "
        "pagina Costruzioni, le proposte e i giudizi sono di chi amministra "
        "(spec 2026-09-26 §3)")


def test_la_derivazione_delle_rotte_di_chi_costruisce_VEDE_le_rotte_vere():
    """La prova che la derivazione non si e' rotta: le rotte che la spec
    nomina (§3) stanno fra quelle derivate. Se la forma delle registrazioni in
    `server.py` cambiasse, la regex non ne troverebbe piu' e la prova sopra
    sarebbe verde su un insieme vuoto.

    Mutazione ESEGUITA (03/10/2026, sulla derivazione dal router): tolte le
    GET da `builder_routes` -- rossa (le due GET mancano)."""
    derivate = set(builder_routes())

    assert {"GET /api/constructions", "GET /api/constructions/{id}",
            "POST /api/constructions/{id}/confirm",
            "POST /api/constructions/{id}/restore",
            "POST /api/constructions/{id}/reject",
            "POST /api/proposals/{id}/reject", "POST /api/proposals/{id}/done",
            "POST /api/proposals/{id}/redo", "POST /api/proposals/{id}/automate",
            "POST /api/mind/judgment"} <= derivate
