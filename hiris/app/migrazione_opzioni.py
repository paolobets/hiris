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

Le sette variabili d'ambiente lette qui sono quelle che `run.sh` esporta dalle
opzioni di `config.yaml` (`ponte.attivo`, `ponte.bridge_deadline_min`,
`ponte.chat_daily_cap`, `local_model.model`, `local_model.request_timeout`,
`hide_free_models`, `llm_strategy`): i nomi MAIUSCOLI non coincidono con i nomi
delle opzioni, quindi la catena si segue per intero -- config.yaml -> run.sh ->
qui -- o si copia la cosa sbagliata.

Questo modulo NON sposta nessun lettore di comportamento: `BRIDGE_ENABLED`,
`CHAT_DAILY_CAP`, `LOCAL_MODEL_NAME`, `OLLAMA_REQUEST_TIMEOUT` e
`HIRIS_HIDE_FREE_MODELS` continuano a governare come oggi (Task 7 e 10 spostano
i lettori). Qui si sposta soltanto la fonte di verita'.

Funzione PURA: `ambiente` e' un dizionario gia' letto, non `os.environ`.
"""
from __future__ import annotations


def _intero(valore, predefinito: int) -> int:
    """`run.sh` esporta stringhe, e un `bashio::config` su un campo vuoto torna
    "". Un ValueError qui fermerebbe l'add-on all'avvio: si ricade sul
    predefinito, che e' cio' che facevano gia' i lettori che sostituiamo
    (`int(os.environ.get("CHAT_DAILY_CAP", "50"))` e gemelli)."""
    try:
        return int(valore)
    except (TypeError, ValueError):
        return predefinito


def _bool(valore, predefinito: bool) -> bool:
    if isinstance(valore, bool):
        return valore
    if valore is None or valore == "":
        return predefinito
    return str(valore).strip().lower() in ("1", "true", "yes", "on")


# Il predefinito di ogni campo e' quello dell'OPZIONE da cui il campo viene:
# se i due non coincidono, un'installazione mai toccata sembra averla toccata.
# `strategia_ultima` valeva "" mentre `config.yaml` e `run.sh` dicono
# "balanced", quindi OGNI installazione -- anche nuova -- logga «Copiati:
# strategia_ultima» e il ramo «erano tutti ai predefiniti» e' morto in
# produzione: e' il debito F dichiarato dal Task 6, e si chiude decidendo il
# predefinito del campo. Il predefinito e' "balanced", come l'opzione.
_PREDEFINITI = {
    "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50},
    "ollama": {"modello": "", "timeout_s": 120},
    "nascondi_gratuiti": False,
    "strategia_ultima": "balanced",
}


def semina(archivio: dict, ambiente: dict, *, log) -> tuple[dict, list[str]]:
    """Riempie l'archivio con i valori delle opzioni dell'add-on, una volta.

    Restituisce `(archivio, chiavi_copiate)`. `chiavi_copiate` e' vuota sia
    quando la semina era gia' avvenuta sia quando non c'era niente da copiare:
    sono due casi diversi, e il log li distingue.
    """
    if archivio.get("seminato"):
        return archivio, []

    valori = {
        "ponte": {
            "attivo": _bool(ambiente.get("BRIDGE_ENABLED"), False),
            "scadenza_min": _intero(ambiente.get("BRIDGE_DEADLINE_MIN"), 5),
            "tetto_giornaliero": _intero(ambiente.get("CHAT_DAILY_CAP"), 50),
        },
        "ollama": {
            "modello": str(ambiente.get("LOCAL_MODEL_NAME") or ""),
            "timeout_s": _intero(ambiente.get("OLLAMA_REQUEST_TIMEOUT"), 120),
        },
        "nascondi_gratuiti": _bool(ambiente.get("HIRIS_HIDE_FREE_MODELS"), False),
        # Lo stesso ripiego di `run.sh` (`bashio::config 'llm_strategy'
        # 'balanced'`): un ambiente muto vale «balanced», non «niente». Senza,
        # un ambiente muto verrebbe contato come valore copiato.
        "strategia_ultima": str(ambiente.get("LLM_STRATEGY") or "balanced"),
    }

    copiate = [k for k, v in valori.items() if v != _PREDEFINITI[k]]
    archivio.update(valori)
    archivio["seminato"] = True

    if copiate:
        log.info(
            "Migrazione (versione A): i valori delle opzioni dell'add-on sono "
            "stati copiati nell'archivio di HIRIS, e da adesso si cambiano dalla "
            "pagina Modelli. Copiati: %s. Valori: ponte=%r, ollama=%r, "
            "nascondi_gratuiti=%r, strategia=%r.",
            ", ".join(sorted(copiate)), valori["ponte"], valori["ollama"],
            valori["nascondi_gratuiti"], valori["strategia_ultima"],
        )
    else:
        log.info(
            "Migrazione (versione A): nessun valore da copiare dalle opzioni "
            "dell'add-on -- erano tutti ai predefiniti. L'archivio di HIRIS e' "
            "adesso la fonte di queste decisioni."
        )
    return archivio, copiate


def semina_catena(archivio: dict, catena_di_oggi: list[str], *, log) -> tuple[dict, bool]:
    """Copia la catena EFFETTIVA di oggi nell'archivio, una volta sola.

    `catena_di_oggi` va calcolata dal chiamante con la vecchia regola ancora
    viva (`server._catena_com_era`, cioe' `reconcile_chain` sui provider
    derivati dai cinque interruttori): e' l'ultimo istante in cui quella regola
    esiste, ed e' l'unico modo di non far passare l'installazione del
    proprietario -- cinque interruttori a false, credenziali presenti -- da
    «due provider lavorano» a «zero provider». Qui si COPIA, non si ricalcola.

    Non guarda `seminato`: quella e' la semina delle OPZIONI (versione A del
    Task 6), che segna «ho gia' guardato config.yaml». La catena ha il proprio
    segno, ed e' se stessa: una `chain_order` non vuota e' la prova che
    qualcuno ha gia' deciso. Legarla a `seminato` significherebbe che un
    archivio seminato dal Task 6 ma con la catena ancora vuota non verrebbe
    MAI riempito -- ed e' esattamente l'archivio che questo rilascio trova.
    """
    if archivio.get("chain_order"):
        return archivio, False
    if not catena_di_oggi:
        log.info(
            "Migrazione della catena: non c'era nessun provider utilizzabile da "
            "copiare. La catena resta vuota, e la pagina Modelli lo dichiara."
        )
        return archivio, False
    archivio["chain_order"] = list(catena_di_oggi)
    log.info(
        "Migrazione della catena: la catena che HIRIS stava usando e' stata "
        "copiata nell'archivio e da adesso si riordina dalla pagina Modelli. "
        "Ordine copiato: %s.", " -> ".join(catena_di_oggi),
    )
    return archivio, True
