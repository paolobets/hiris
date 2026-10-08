"""Le parole degli stati: la lettura delle traduzioni, e il sapere che ne nasce.

Spostato da `server.py` l'08/10/2026 (Tappa 8, Task 1), senza cambiare una
riga di logica. Sta in `mind/` e non in `home_space/` perche' scrive nel
sapere col seme di `mind/seed.py`, e `home_space` non importa da `mind`
(`tests/test_confine_home_space.py`).
"""
from __future__ import annotations

import logging

from .seed import HOUSE_PRIORITY, meanings_from_translations

logger = logging.getLogger(__name__)


async def prime_state_translations(app) -> dict:
    """Scalda le traduzioni degli stati, e torna l'esito etichettato.

    **Perche' esiste, dall'08/09/2026.** Fino a quel giorno la prima lettura
    avveniva «alla prima pagina che ne ha bisogno», e la scelta era giusta:
    era una tabella che quella sessione poteva non chiedere mai. Poi le quattro
    tabelle scritte a mano di `home_space/topology.py` sono sparite (spec §6) e
    quelle parole sono diventate cio' con cui il NUCLEO rende ogni stato
    notevole -- cioe' qualcosa che serve a ogni turno di chat, dal primo. Una
    tabella caricata pigramente e' una tabella che il primo lettore trova
    vuota: e' la forma «stato condiviso caricato pigramente», e la domanda da
    farsi e' chi lo riempie. Lo riempie questa funzione.

    **Non solleva mai e non blocca l'avvio**: se Home Assistant non e' ancora
    pronto, l'esito dice «non lette» col motivo, il nucleo lo DICHIARA e mostra
    gli stati grezzi, e il giro periodico riprova. Un nucleo che dice «non ho
    letto le traduzioni» e' onesto; un avvio che non parte per una tabella di
    parole non lo sarebbe.

    **E SCRIVE NEL SAPERE**, il che non e' cio' che il nome promette e va detto
    (Fable 5.1, 13/09/2026): quando la lettura riesce, i significati delle
    classi che l'installazione pubblica entrano nell'archivio del sapere. Sta
    qui e non altrove perche' e' lo stesso dizionario -- nessuna lettura di
    rete in piu'.

    **Si semina solo quando la tabella e' NUOVA** (`appena_lette`, A-22,
    Tappa 8, Task 9, 08/10/2026). Fino a quel giorno il giro dei cinque minuti
    rifaceva `seed` sulla tabella gia' tenuta: non scriveva niente dopo la prima
    volta, ma ricalcolava tutto e faceva avanzare la versione del sapere, che a
    sua volta svuotava la memoria degli attributi dell'osservatore ogni cinque
    minuti. Una tabella che non e' cambiata non ha niente di nuovo da dire.

    **Il giro resta a intervallo**, ed e' una lettura del sorgente di Home
    Assistant, non una scelta (tag 2026.9.4, 08/10/2026): nessun evento dice
    «le traduzioni sono cambiate». `helpers/translation.py` le carica in una
    memoria che non scarica mai, componente per componente, e ascolta solo
    `core_config_updated` per la lingua nuova -- che qui arriva gia' con la
    ricostruzione dell'anagrafe (`mind/reconciliation.after_rebuild`). Il giro
    serve alla prima lettura fallita.
    """
    cache = app.get("state_translations")
    if cache is None:
        return {"lette": False,
                "motivo": "la lettura delle traduzioni non e' collegata a questa istanza"}
    store = app.get("home_space_store")
    frame = store.reference_frame() if store is not None else {}
    try:
        report = await cache.read(ha_version=frame.get("versione_ha"),
                                  language=frame.get("lingua"))
    except Exception as exc:
        report = {"lette": False, "motivo": f"{type(exc).__name__}: {exc}"}
    if not report.get("lette"):
        logger.info("traduzioni degli stati non lette: %s", report.get("motivo"))
        return report
    # **Il significato di ogni classe entra nel sapere, da qui.** E' lo stesso
    # dizionario che il nucleo usa per rendere gli stati: nessuna lettura di
    # rete in piu', e nessuna seconda tabella. Misurato il 12/09/2026: il repo
    # scriveva a mano il significato di 18 classi di `sensor` su 62 e di ZERO
    # su 28 di `binary_sensor` -- le altre non erano «meno importanti», erano
    # quelle di cui HIRIS non sapeva dire niente.
    #
    # Si scrivono con `seed`, non con `write`: dove il repo ha una FRASE
    # («la potenza ISTANTANEA, non un'energia») quella resta, e il NOME che HA
    # pubblica («Potenza») non la schiaccia.
    sapere = app.get("knowledge")
    if sapere is not None and report.get("appena_lette"):
        # **B2: senza versione o lingua non si importa niente.** La fonte di
        # una riga deve dire da quale versione e in che lingua viene: scrivere
        # «sconosciuta» sarebbe una citazione che non permette di controllare
        # nulla, cioe' la forma della motivazione falsa dentro il campo che
        # esiste per impedirla.
        version = frame.get("versione_ha")
        language = report.get("lingua") or frame.get("lingua")
        written = sapere.seed(meanings_from_translations(
            report.get("risorse") or {}, ha_version=version, language=language),
            priority=HOUSE_PRIORITY) if version and language else 0
        if written:
            logger.info(
                "sapere: %d significati di classe importati dalle traduzioni "
                "di questa installazione", written)
    return report
