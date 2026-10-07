"""Le due semine dell'archivio dei modelli: la catena e il modello del piano.

Qui viveva anche la semina delle OPZIONI dell'add-on (`seed`, «versione A»):
copiava nell'archivio di HIRIS, una volta sola, sette valori letti da
variabili d'ambiente che `run.sh` esportava dalle opzioni di `config.yaml`.
Quelle opzioni sono uscite dallo schema con la 3.0.0 (14 agosto 2026) e
`run.sh` non esporta piu' niente: la semina non aveva piu' niente da leggere,
ed e' uscita il 02/10/2026 con le sette letture d'ambiente. Il suo segno,
`seminato`, e' uscito dalla forma di `GET /api/models/config` col Task 10 della
Tappa 7 (M-80): nessuno lo scriveva ne' lo leggeva.

**La «migrazione come era» sta tutta qui** dal Task 10 della Tappa 7 (F-12):
la catena iniziale (`_initial_chain`, che in `server.py` si chiamava
`_chain_as_it_was`) e le due semine dell'avvio (`seed_at_startup`) vivevano in
`server._on_startup`; i segni sono lo schema dell'archivio
(`models_store._MIGRATION_FLAGS`).
"""
from __future__ import annotations

import logging

from .providers import CLAUDE, DEFAULT_PRESET, SUBSCRIPTION, chosen_model, get, preset

logger = logging.getLogger(__name__)


def seed_chain(store: dict, current_chain: list[str], *, log) -> tuple[dict, bool]:
    """Copia la catena EFFETTIVA di oggi nell'archivio, una volta sola.

    `current_chain` va calcolata dal chiamante con la vecchia regola ancora
    viva (`_initial_chain`, che fino al 02/10/2026 era `reconcile_chain` sui
    provider derivati dai cinque interruttori): e' l'ultimo istante in cui quella regola
    esiste, ed e' l'unico modo di non far passare l'installazione del
    proprietario -- cinque interruttori a false, credenziali presenti -- da
    «due provider lavorano» a «zero provider». Qui si COPIA, non si ricalcola.

    Ha un SEGNO PROPRIO, `catena_seminata`, distinto da quello del modello del
    piano (`piano_seminato`): sono due migrazioni diverse e un archivio puo'
    trovarsi a meta'. La versione precedente di questa funzione non aveva
    nessun segno e si regolava su «`chain_order` e' vuota», che e' il difetto:
    una `chain_order` vuota NON e' piu' «non ho ancora deciso». Da questa fetta
    e' una decisione, e la pagina Modelli la rende esprimibile in due click (la
    ✕ su ogni riga). Chi svuotava la catena di proposito -- il proprietario che
    toglie la chiave a credito zero e OpenRouter per restare sul piano che ha
    gia' pagato -- se la ritrovava ripopolata al riavvio successivo da
    `_chain_as_it_was` (oggi `_initial_chain`), cioe' dalla regola `legacy`
    (`not any(interruttori)`) che questa fetta ha tolto dal prodotto: con i
    cinque interruttori a false rientrava in catena OGNI provider con una
    credenziale, e la spesa a consumo ripartiva. Era la QUARTA porta di quella
    regola, e l'unica fuori dal router.

    Il segno si scrive SEMPRE, anche quando non c'era niente da copiare e anche
    quando la catena era gia' decisa: e' cio' che rende la migrazione un evento
    che accade una volta e non una condizione che si rivaluta a ogni avvio. Per
    questo il secondo valore di ritorno significa «c'e' qualcosa da
    persistere», non «ho copiato una catena».
    """
    if store.get("catena_seminata"):
        return store, False
    store["catena_seminata"] = True
    if store.get("chain_order"):
        # Una catena gia' decisa (l'ordine manuale di un'installazione
        # pre-2.5.0) non si tocca: si segna e basta.
        return store, True
    if not current_chain:
        log.info(
            "Catena iniziale: nessuna credenziale utilizzabile, quindi la "
            "catena nasce vuota. La pagina Modelli lo dichiara e dice il gesto."
        )
        return store, True
    store["chain_order"] = list(current_chain)
    # NON «la catena che HIRIS stava usando»: qui ci arriva anche
    # un'installazione nata ieri, che non stava usando niente e la cui catena
    # e' stata COMPOSTA adesso dalle credenziali presenti. Dichiarare una
    # storia che non c'e' stata e' l'invariante 3 violato in un punto che, da
    # questa versione, si esegue a OGNI installazione nuova. Si dice quindi
    # solo cio' che si sa: da dove viene l'ordine, e dove si cambia.
    log.info(
        "Catena iniziale scritta nell'archivio: composta con i provider di cui "
        "c'e' una credenziale, nell'ordine del preset. Da adesso si riordina "
        "dalla pagina Modelli. Ordine: %s.", " -> ".join(current_chain),
    )
    return store, True


def seed_subscription_model(store: dict, current_alias: str,
                            *, log) -> tuple[dict, bool]:
    """Copia nel campo nuovo l'alias che il piano sta usando ADESSO, una volta.

    `current_alias` lo calcola il chiamante con la derivazione di prima della
    3.2.0 (`cli_model` del modello di Claude API, o del suo automatico):
    e' la regola che la fetta «il modello del piano» ritira, e la si esegue
    un'ultima volta per non far cambiare comportamento all'installazione il
    giorno dell'aggiornamento. Qui si COPIA, non si ricalcola.

    Segno PROPRIO, `piano_seminato`, distinto da `seminato` (le opzioni) e da
    `catena_seminata` (la catena): sono tre migrazioni diverse e un archivio
    puo' trovarsi a due terzi.

    LA GUARDIA E' IL SEGNO, NON LA FORMA DEL VALORE. Regolarsi su «il campo
    vale ancora il predefinito» ricoprirebbe al riavvio successivo la scelta di
    chi ha scelto proprio `sonnet` -- lo stesso difetto che `seed_chain`
    documenta per la catena vuota, dove regolarsi sulla forma faceva ripopolare
    una catena svuotata di proposito.

    A differenza di `seed_chain` questa NON legge una regola in via di
    sparizione: `provider_models["claude"]` resta vivo, e' il modello di Claude
    API. E' il segno, e solo il segno, a rendere la semina irripetibile.

    Il secondo valore di ritorno significa «c'e' qualcosa da persistere», non
    «ho copiato un modello»: il segno si scrive SEMPRE, anche quando il valore
    coincideva col predefinito.
    """
    if store.get("piano_seminato"):
        return store, False
    store["piano_seminato"] = True
    bridge = dict(store.get("ponte") or {})
    previous = bridge.get("modello")
    bridge["modello"] = current_alias
    store["ponte"] = bridge
    log.info(
        "Il %s ha adesso un modello suo: %s, cioe' quello che "
        "stava gia' usando (era un effetto del modello di Claude API). Da "
        "adesso si sceglie dalla riga del piano nella pagina Modelli, e "
        "cambiare il modello di Claude API non lo tocca piu'.%s",
        SUBSCRIPTION.name, current_alias,
        "" if previous in (None, current_alias)
        else f" Il predefinito {previous!r} e' stato sostituito.",
    )
    return store, True


def _initial_chain(credentials: dict) -> list[str]:
    """La catena con cui nasce un archivio che non ha ancora la sua: **ogni
    provider a consumo di cui c'e' una credenziale**, nell'ordine del preset
    «balanced».

    In `server.py` si chiamava `_chain_as_it_was`, «com'era», perche' e' cio'
    che la regola pre-2.5 produceva sull'installazione del proprietario, ed e'
    per quello che e' nata: copiare
    la catena invece di far passare quell'impianto da «due provider lavorano» a
    «zero provider». Ma non e' piu' una copia della vecchia regola per intero.

    **Aveva un secondo ramo, ed e' uscito con la versione B.** La vecchia
    regola era in due tempi: `legacy = not any(interruttori)` -- nessuno dei
    cinque `provider_*` acceso, e allora contava la sola credenziale -- oppure,
    con almeno un interruttore acceso, contavano solo gli accesi. I cinque
    interruttori sono usciti dallo schema e `run.sh` non esporta piu' nessuno
    dei cinque `PROVIDER_*`: via Supervisor `legacy` era strutturalmente sempre
    vero e il secondo ramo era codice irraggiungibile. Tenerlo qui voleva dire
    tenere a schermo una regola che non puo' piu' girare -- e i test che la
    esercitavano difendevano uno stato che nessun utente puo' produrre.

    Resta quindi la sola regola di compatibilita', scritta per quello che e'.
    **E va DECISA, non ereditata** (G3 della revisione): non e' piu' una
    migrazione che si esaurisce, si esegue su ogni installazione nuova finche'
    qualcuno non decide che catena deve trovare chi installa HIRIS oggi. La
    fetta successiva non puo' limitarsi a cancellarla: senza, un'installazione
    nuova nasce con la catena vuota e la chat muta.

    **Due provider non ci entrano mai, qualunque credenziale abbiano.** Il
    piano non e' un membro della catena: sta in testa quando il ponte e'
    acceso, e quello lo dice `ponte.attivo`, non l'appartenenza. Ollama la
    vecchia regola lo voleva con l'indirizzo E il nome del modello, e il nome
    arrivava da una variabile d'ambiente che nessuna installazione riceve
    piu': chi lo vuole lo aggiunge dalla pagina Modelli.

    Fino al 02/10/2026 prendeva anche il preset e lo stato del ponte, letti
    da `LLM_STRATEGY` e `BRIDGE_ENABLED`: `run.sh` non le esporta dalla 3.0.0,
    e su ogni installazione valevano «balanced» e spento.
    """
    return [name for name in preset(DEFAULT_PRESET).order
            if get(name).chain_member and not get(name).needs_chosen_model
            and credentials.get(name)]


def seed_at_startup(app, data_dir: str, credentials: dict) -> None:
    """Le due semine dell'avvio, nell'ordine: la catena, poi il modello del
    piano. Ognuna guarda il SUO segno e si salva da se', e l'archivio in
    memoria (`app["models_config"]`) si rilegge dopo ciascuna: fondere le due
    in una scrittura sola le renderebbe una migrazione sola che puo' trovarsi
    a meta', che e' cio' che i segni distinti esistono per evitare.

    **Perche' restano tutte e due, su un add-on pubblico** (Tappa 7, Task 10,
    07/10/2026). Sulla casa del proprietario sono avvenute entrambe (misura 4,
    `GET /api/models/config` dal PC: `catena_seminata` e `piano_seminato`
    veri), ma una casa che non le ha mai fatte perderebbe qualcosa:

    - **la catena** si semina su OGNI installazione nuova: senza, nasce vuota
      e la chat resta muta finche' qualcuno non apre la pagina Modelli;
    - **il modello del piano** si semina su chi aggiorna da una versione
      precedente alla 3.2.0 (15/08/2026): senza, il piano passerebbe in
      silenzio da cio' che stava usando -- il modello di Claude API, per
      esempio `haiku` -- al predefinito `sonnet`.

    Fino al Task 10 i due blocchi stavano in linea in `server._on_startup`, e
    il modello del piano si derivava da `claude_runner.resolve_model`, uscita
    con `agent_type` (D11a): qui la stessa derivazione si chiede alla tabella
    dei provider (`chosen_model` di Claude API, o il suo automatico).
    """
    from .agent.runner import cli_model
    from .models_store import load_models_config, save_models_config

    seeds = (
        # La guardia e' il SEGNO, non la forma della catena: vedi `seed_chain`.
        lambda store: seed_chain(store, _initial_chain(credentials), log=logger),
        lambda store: seed_subscription_model(
            store, cli_model(chosen_model(CLAUDE, store) or CLAUDE.auto_model),
            log=logger),
    )
    for seed in seeds:
        store, to_save = seed(dict(app["models_config"]))
        if to_save:
            save_models_config(data_dir, store, flags=True)
            app["models_config"] = load_models_config(data_dir)
