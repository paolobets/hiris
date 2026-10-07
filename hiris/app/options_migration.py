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

from .providers import SUBSCRIPTION


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
