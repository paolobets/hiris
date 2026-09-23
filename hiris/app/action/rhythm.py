"""Il freno di RITMO sulle azioni (reperto B-3 del registro dei rischi).

**Non e' una difesa contro un attacco: e' contro un incidente.** Il seme dello
sprint lo dice per esteso -- il modo piu' probabile in cui un agente domestico
fa danno non e' l'attacco, e' il **circolo**. Una tapparella riaperta cento
volte rompe un motore, e HIRIS ha schedulatore e promesse: percorsi che agiscono
**senza nessuno davanti allo schermo**.

**Il permesso non si tocca** (decisione del proprietario, 21/09/2026: una lista
di servizi castrerebbe HIRIS e non seguirebbe le versioni di Home Assistant).
Il ritmo e' un'altra cosa: non limita **cosa** HIRIS puo' fare, limita **quante
volte di fila sulla stessa cosa**.

**Per ENTITA', mai globale.** Una casa che spegne dieci luci diverse in un
minuto sta facendo il suo lavoro; un freno globale la fermerebbe, ed e'
esattamente il modo in cui questo intervento puo' fare danno invece di
evitarlo.

**Si dichiara.** Un rifiuto muto insegna che il prodotto e' rotto; un rifiuto
che dice «mi sono fermato, ecco quante volte in quanti secondi, questo e' un
circolo» insegna dov'e' il difetto vero -- che sta quasi sempre in
un'automazione, non qui.
"""
from __future__ import annotations

#: Quante azioni sulla STESSA entita', dentro `WINDOW_S`, prima di fermarsi.
#:
#: **Il numero e' PROVVISORIO, ed e' generoso apposta.** Il registro chiede una
#: soglia misurata sulla cronaca -- ci sono novanta giorni di storia vera -- e
#: quella misura il 22/09/2026 non era ottenibile: nessuna rotta HTTP espone la
#: cronaca, e l'accesso diretto alla macchina non c'era. Si e' scelto quindi un
#: numero che prende i circoli (che fanno centinaia di giri) e **non puo'**
#: prendere un uso legittimo: venti comandi sulla stessa entita' in un minuto
#: non li produce nessuna persona e nessuna automazione sana.
#:
#: Si stringera' quando la fetta della misura avra' guardato i novanta giorni.
#: Una soglia provvisoria che nessuno dichiara diventa definitiva per
#: dimenticanza: per questo la parola «provvisoria» e' pinnata da una prova.
THRESHOLD = 20

#: La finestra che scorre. Dieci azioni in un minuto sono un circolo; dieci in
#: un giorno sono una casa che vive.
WINDOW_S = 60.0

#: Oltre quante entita' ricordate si pota. Gira su ogni azione di ogni origine:
#: ricordare ogni entita' per sempre sarebbe una perdita di memoria su un
#: percorso caldo.
_MAX_REMEMBERED = 40


def too_often(seen: dict, entity, *, now: float) -> str | None:
    """`None` se si puo' procedere, altrimenti **la frase che dice perché no**.

    `visto` e' il contenitore dei moments recenti per entita': lo tiene chi
    chiama, cosi' questa funzione non ha stato suo e si prova senza montare
    niente.
    """
    if not entity or not isinstance(entity, str):
        # Un'azione senza bersaglio esiste -- un servizio di sistema -- e
        # questo freno sta sul percorso di ogni azione: sollevare qui
        # spegnerebbe l'attuatore invece di frenare un circolo.
        return None

    _prune(seen, now)
    moments = [q for q in seen.get(entity, []) if now - q <= WINDOW_S]
    if len(moments) >= THRESHOLD:
        seen[entity] = moments
        return (f"mi fermo su «{entity}»: sono {len(moments)} comandi in "
                f"{int(WINDOW_S)} secondi, e oltre {THRESHOLD} non e' un uso, e' "
                "un circolo. Non ho eseguito. Guarda cosa lo sta ripetendo — di "
                "solito e' un'automazione che si riaccende da sola — e quando "
                "l'hai fermato riprovo senza problemi.")
    moments.append(now)
    seen[entity] = moments
    return None


def _prune(seen: dict, now: float) -> None:
    for entity in [e for e, moments in seen.items()
                   if not moments or now - max(moments) > WINDOW_S]:
        del seen[entity]
    if len(seen) <= _MAX_REMEMBERED:
        return
    # Se restano troppe entita' ANCORA dentro la finestra, si tengono le piu'
    # recenti: un circolo e' recente per costruzione, e cio' che si perde e'
    # il conteggio di qualcosa che non stava girando.
    by_recency = sorted(seen.items(), key=lambda kv: -max(kv[1]))
    seen.clear()
    seen.update(dict(by_recency[:_MAX_REMEMBERED]))
