"""Versione A della migrazione: dall'opzione dell'add-on all'archivio di HIRIS.

Il Supervisor scarta ogni chiave fuori schema (`AddonOptions.__call__`) PRIMA
di scrivere /data/options.json: non esiste nessun ripiego possibile in
`run.sh`, perche' la vecchia chiave non ci arriva nemmeno. Togliere un'opzione
dallo schema, da sola, fa sparire IN SILENZIO il valore dell'utente.

La rete e' questa: finche' le opzioni sono ancora nello schema, HIRIS legge dal
PROPRIO archivio e, quando l'archivio non e' ancora stato seminato, ci COPIA
dentro il valore dell'opzione -- una volta sola, dichiarandolo nel log. Un
avvio, e i valori sono al sicuro. Solo il rilascio DOPO toglie le opzioni.

Perche' la copia deve avvenire una volta sola: se si ripetesse a ogni avvio,
l'opzione dell'add-on continuerebbe a vincere sulla scelta fatta dalla pagina
Modelli, e la migrazione non finirebbe mai. `seminato` e' il segno che e'
avvenuta -- e va segnato ANCHE quando non c'era niente da copiare, altrimenti
un'installazione nuova ricomincerebbe a cercare opzioni che dopo la versione B
non esistono piu'.

Le sette variabili d'ambiente lette qui erano quelle che `run.sh` esportava
dalle opzioni di `config.yaml` (`ponte.attivo`, `ponte.bridge_deadline_min`,
`ponte.chat_daily_cap`, `local_model.model`, `local_model.request_timeout`,
`hide_free_models`, `llm_strategy`): i nomi MAIUSCOLI non coincidono con i nomi
delle opzioni, quindi la catena si segue per intero -- config.yaml -> run.sh ->
qui -- o si copia la cosa sbagliata.

**VERSIONE B (3.0.0, 14 agosto 2026): quelle sette opzioni sono USCITE**, e con
loro i sette `export` di `run.sh`. Nessuno di quei valori governa piu' niente
dall'ambiente: il ponte, i due tempi, il tetto, il modello di Ollama, il
filtro dei gratuiti e il preset vivono nell'archivio, e chi li legge lo legge
di li'.

Questo modulo resta, e resta l'unico posto che legge ancora quelle variabili.
Non e' un ripiego «se non so niente comportati come prima»: e' la migrazione, e
serve a un'installazione che salti la 2.5.0 e arrivi qui con l'ambiente ancora
popolato dal vecchio `run.sh`. Via Supervisor non puo' succedere (le chiavi
fuori schema vengono scartate PRIMA che /data/options.json esista, quindi
l'ambiente e' muto e la semina scrive i predefiniti su un archivio che pero' e'
gia' `seminato`, e quindi esce subito); in sviluppo si'. **Esce con la fetta
successiva**, insieme a `chat_settings._retention_days_from_environment`, quando nessuna
installazione potra' piu' arrivare non seminata.

`server._chain_as_it_was` era elencata qui accanto, e **non esce con loro**: con
gli interruttori tolti non copia piu' niente da nessuna parte, COMPONE la
catena di ogni installazione nuova, e cancellarla e basta la farebbe nascere
con la catena vuota e la chat muta. Va decisa -- vedi la sua docstring.

Funzione PURA: `ambiente` e' un dizionario gia' letto, non `os.environ`.
"""
from __future__ import annotations


def _integer(value, default: int) -> int:
    """`run.sh` esporta stringhe, e un `bashio::config` su un campo vuoto torna
    "". Un ValueError qui fermerebbe l'add-on all'avvio: si ricade sul
    predefinito, che e' cio' che facevano gia' i lettori che sostituiamo
    (`int(os.environ.get("CHAT_DAILY_CAP", "50"))` e gemelli)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# Il predefinito di ogni campo e' quello dell'OPZIONE da cui il campo viene:
# se i due non coincidono, un'installazione mai toccata sembra averla toccata.
# `strategia_ultima` valeva "" mentre `config.yaml` e `run.sh` dicono
# "balanced", quindi OGNI installazione -- anche nuova -- logga «Copiati:
# strategia_ultima» e il ramo «erano tutti ai predefiniti» e' morto in
# produzione: e' il debito F dichiarato dal Task 6, e si chiude decidendo il
# predefinito del campo. Il predefinito e' "balanced", come l'opzione.
_DEFAULTS = {
    "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50},
    "ollama": {"modello": "", "timeout_s": 120},
    "nascondi_gratuiti": False,
    "strategia_ultima": "balanced",
}

# Le sette variabili che `run.sh` esportava e che dalla versione B non esporta
# piu'. Servono a distinguere due casi che il log confondeva in una riga sola:
# «c'erano dei valori, e valevano il predefinito» e «non c'era NIENTE da
# leggere». Dalla 3.0.0 il secondo e' la condizione normale -- via Supervisor
# e' l'UNICA possibile -- e dire «erano tutti ai predefiniti» quando non si e'
# letto niente afferma piu' di cio' che il sistema sa. Su un archivio
# illeggibile quella riga era, insieme a quella della catena, l'unica cosa che
# l'utente leggeva mentre dodici sue decisioni sparivano.
_VARIABLES = ("BRIDGE_ENABLED", "BRIDGE_DEADLINE_MIN", "CHAT_DAILY_CAP",
              "LOCAL_MODEL_NAME", "OLLAMA_REQUEST_TIMEOUT",
              "HIRIS_HIDE_FREE_MODELS", "LLM_STRATEGY")


def environment_is_silent(environment: dict) -> bool:
    """Nessuna delle sette variabili porta un valore. `""` conta come muto:
    e' cio' che `bashio::config` restituisce per un campo vuoto, ed e' anche
    cio' che resta quando l'opzione non esiste piu'."""
    return not any(str(environment.get(n) or "").strip() for n in _VARIABLES)


def seed(store: dict, environment: dict, *, log) -> tuple[dict, list[str]]:
    """Riempie l'archivio con i valori delle opzioni dell'add-on, una volta.

    Restituisce `(archivio, chiavi_copiate)`. `chiavi_copiate` e' vuota sia
    quando la semina era gia' avvenuta sia quando non c'era niente da copiare:
    sono due casi diversi, e il log li distingue.
    """
    if store.get("seminato"):
        return store, []

    # I predefiniti si LEGGONO da `_DEFAULTS`, non si ridigitano qui: erano
    # gli stessi numeri scritti due volte nello stesso file (una nel
    # dizionario, una come argomento di `_integer`/`_bool`), piu' una terza
    # volta in `api/handlers_models._STORE_DEFAULTS`. E' esattamente la
    # struttura che ha prodotto il debito F -- `strategia_ultima` che valeva
    # `""` in una copia e `"balanced"` nell'altra, e ogni installazione, anche
    # nuova, che logga «Copiati: strategia_ultima» -- chiuso allora
    # ALLINEANDO le copie invece di toglierne una.
    _p = _DEFAULTS
    values = {
        "ponte": {
            "attivo": _bool(environment.get("BRIDGE_ENABLED"), _p["ponte"]["attivo"]),
            "scadenza_min": _integer(environment.get("BRIDGE_DEADLINE_MIN"),
                                     _p["ponte"]["scadenza_min"]),
            "tetto_giornaliero": _integer(environment.get("CHAT_DAILY_CAP"),
                                          _p["ponte"]["tetto_giornaliero"]),
        },
        "ollama": {
            "modello": str(environment.get("LOCAL_MODEL_NAME") or _p["ollama"]["modello"]),
            "timeout_s": _integer(environment.get("OLLAMA_REQUEST_TIMEOUT"),
                                  _p["ollama"]["timeout_s"]),
        },
        "nascondi_gratuiti": _bool(environment.get("HIRIS_HIDE_FREE_MODELS"),
                                   _p["nascondi_gratuiti"]),
        # Lo stesso ripiego di `run.sh` (`bashio::config 'llm_strategy'
        # 'balanced'`): un ambiente muto vale «balanced», non «niente». Senza,
        # un ambiente muto verrebbe contato come valore copiato.
        "strategia_ultima": str(environment.get("LLM_STRATEGY") or _p["strategia_ultima"]),
    }

    copied = [k for k, v in values.items() if v != _DEFAULTS[k]]
    store.update(values)
    store["seminato"] = True

    if copied:
        log.info(
            "Migrazione (versione A): i valori delle opzioni dell'add-on sono "
            "stati copiati nell'archivio di HIRIS, e da adesso si cambiano dalla "
            "pagina Modelli. Copiati: %s. Valori: ponte=%r, ollama=%r, "
            "nascondi_gratuiti=%r, strategia=%r.",
            ", ".join(sorted(copied)), values["ponte"], values["ollama"],
            values["nascondi_gratuiti"], values["strategia_ultima"],
        )
    elif environment_is_silent(environment):
        # Il caso normale dalla 3.0.0: le opzioni non esistono piu', quindi non
        # c'era NIENTE da leggere. Non si dice «erano tutti ai predefiniti»:
        # sarebbe un'affermazione sui valori dell'utente, e nessun valore
        # dell'utente e' stato letto. Se ci si arriva con un archivio che
        # ESISTEVA ma non si e' potuto leggere, la riga che lo dice l'ha gia'
        # scritta `_read_raw_store` (logger.error), e questa non la
        # contraddice piu'.
        log.info(
            "Migrazione (versione A): non c'era nessuna opzione dell'add-on da "
            "copiare -- sono uscite dallo schema con la 3.0.0. L'archivio di "
            "HIRIS e' la sola fonte di queste decisioni, e i campi che non "
            "aveva partono dai suoi predefiniti."
        )
    else:
        log.info(
            "Migrazione (versione A): nessun valore da copiare dalle opzioni "
            "dell'add-on -- erano tutti ai predefiniti. L'archivio di HIRIS e' "
            "adesso la fonte di queste decisioni."
        )
    return store, copied


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
        "Il Piano Claude Max ha adesso un modello suo: %s, cioe' quello che "
        "stava gia' usando (era un effetto del modello di Claude API). Da "
        "adesso si sceglie dalla riga del piano nella pagina Modelli, e "
        "cambiare il modello di Claude API non lo tocca piu'.%s",
        current_alias,
        "" if previous in (None, current_alias)
        else f" Il predefinito {previous!r} e' stato sostituito.",
    )
    return store, True
