"""Le due semine che girano ancora: la catena e il modello del piano.

Qui viveva anche la semina delle OPZIONI dell'add-on (`seed`, «versione A»):
copiava nell'archivio di HIRIS, una volta sola, sette valori letti da
variabili d'ambiente che `run.sh` esportava dalle opzioni di `config.yaml`.
Quelle opzioni sono uscite dallo schema con la 3.0.0 (14 agosto 2026) e
`run.sh` non esporta piu' niente: la semina non aveva piu' niente da leggere,
ed e' uscita il 02/10/2026 con le sette letture d'ambiente. Sulla casa del
proprietario la copia era avvenuta da tempo (`seminato` vero, misurato quel
giorno). Il segno `seminato` resta nella forma di `GET /api/models/config` e
negli archivi che gia' lo portano, ma nessuno lo scrive ne' lo legge piu':
toglierlo cambia la forma di una rotta, e si fa quando quel cambio e'
dichiarato.

Restano `seed_chain` e `seed_subscription_model`, che non sono migrazioni
compiute: girano su ogni installazione nuova (vedi `server._chain_as_it_was`).
"""
from __future__ import annotations

import logging

from .providers import CLAUDE, DEFAULT_PRESET, SUBSCRIPTION, get, preset

logger = logging.getLogger(__name__)


def seed_chain(store: dict, current_chain: list[str], *, log) -> tuple[dict, bool]:
    """Copia la catena EFFETTIVA di oggi nell'archivio, una volta sola.

    `current_chain` va calcolata dal chiamante con la vecchia regola ancora
    viva (`server._chain_as_it_was`, cioe' `reconcile_chain` sui provider
    derivati dai cinque interruttori): e' l'ultimo istante in cui quella regola
    esiste, ed e' l'unico modo di non far passare l'installazione del
    proprietario -- cinque interruttori a false, credenziali presenti -- da
    «due provider lavorano» a «zero provider». Qui si COPIA, non si ricalcola.

    Ha un SEGNO PROPRIO, `catena_seminata`, distinto da `seminato` (che e' la
    semina delle OPZIONI, versione A del Task 6): sono due migrazioni diverse e
    un archivio puo' trovarsi a meta'. La versione precedente di questa
    funzione non aveva nessun segno e si regolava su «`chain_order` e' vuota»,
    che e' il difetto: una `chain_order` vuota NON e' piu' «non ho ancora
    deciso». Da questa fetta e' una decisione, e la pagina Modelli la rende
    esprimibile in due click (la ✕ su ogni riga). Chi svuotava la catena di
    proposito -- il proprietario che toglie la chiave a credito zero e
    OpenRouter per restare sul piano che ha gia' pagato -- se la ritrovava
    ripopolata al riavvio successivo da `_chain_as_it_was`, cioe' dalla regola
    `legacy` (`not any(interruttori)`) che questa fetta ha tolto dal prodotto:
    con i cinque interruttori a false rientrava in catena OGNI provider con una
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

    `current_alias` lo calcola il chiamante con la derivazione ancora viva
    (`cli_model(resolve_model("auto", "chat", provider_models["claude"]))`):
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


def _chain_as_it_was(credentials: dict) -> list[str]:
    """La catena con cui nasce un archivio che non ha ancora la sua: **ogni
    provider a consumo di cui c'e' una credenziale**, nell'ordine del preset
    «balanced».

    Si chiama ancora «com'era» perche' e' cio' che la regola pre-2.5 produceva
    sull'installazione del proprietario, ed e' per quello che esiste: copiare
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


def seed_at_startup(app, data_dir: str, _credentials: dict) -> None:
    """Le due semine dell'avvio, nell'ordine: la catena, poi il modello del piano."""
    from .api.handlers_models import load_models_config, save_models_config

    # ── La catena iniziale di un archivio che non ce l'ha ────────────────
    # Nata come seconda meta' della migrazione: la catena che HIRIS stava
    # usando copiata nell'archivio PRIMA che la derivazione dai cinque
    # interruttori sparisse. Senza quella copia, l'installazione del
    # proprietario -- cinque interruttori a false, credenziali presenti --
    # sarebbe passata da «due provider lavorano» a «zero provider».
    # Con la versione B i cinque interruttori NON esistono piu' e `run.sh` non
    # esporta piu' i cinque `PROVIDER_*`: qui non si copia piu' niente da
    # nessuna parte, si COMPONE una catena dalle credenziali presenti. E' la
    # sola regola di compatibilita' rimasta, e a differenza delle altre letture
    # di migrazione non si esaurisce: gira su ogni installazione nuova. Va
    # DECISA dalla fetta successiva, non ereditata (G3) -- e cancellarla e
    # basta farebbe nascere ogni installazione nuova con la catena vuota.
    # La guardia e' il SEGNO, non la forma della catena: una `chain_order`
    # vuota, da questa fetta, e' una decisione esprimibile in due click, e
    # regolarsi su di lei faceva ripopolare al riavvio una catena svuotata di
    # proposito. Vedi `seed_chain`.
    from .options_migration import seed_chain
    if not app["models_config"].get("catena_seminata"):
        _current_chain = _chain_as_it_was(_credentials)
        _arch, _da_salvare = seed_chain(dict(app["models_config"]),
                                        _current_chain, log=logger)
        if _da_salvare:
            save_models_config(data_dir, _arch, flags=True)
            app["models_config"] = load_models_config(data_dir)

    # La TERZA semina: il modello del Piano Claude Max. Fino alla 3.1.0 era un
    # effetto collaterale di `provider_models["claude"]` -- un campo solo per
    # due economie opposte, e l'impianto del proprietario girava sul piano col
    # modello scelto per non spendere sull'API. Da questa fetta e' un valore
    # suo, e qui si esegue un'ULTIMA volta la derivazione che se ne va, perche'
    # il giorno dell'aggiornamento niente cambi sotto l'utente.
    #
    # Salvataggio proprio e non fuso con quello della catena: fondere le due
    # semine in una scrittura sola le renderebbe una migrazione sola che puo'
    # trovarsi a meta', che e' esattamente cio' che i segni distinti esistono
    # per evitare.
    from .options_migration import seed_subscription_model
    if not app["models_config"].get("piano_seminato"):
        from .agent.runner import cli_model
        from .claude_runner import resolve_model
        _current_alias = cli_model(resolve_model(
            "auto", "chat",
            app["models_config"].get("provider_models", {}).get(CLAUDE.id, ""),
        ))
        _arch_p, _da_salvare_p = seed_subscription_model(
            dict(app["models_config"]), _current_alias, log=logger)
        if _da_salvare_p:
            save_models_config(data_dir, _arch_p, flags=True)
            app["models_config"] = load_models_config(data_dir)
