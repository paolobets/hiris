"""Quale struttura serve davvero -- e perche'.

E' il punto in cui la **Legge I** smette di essere un principio e diventa
codice eseguibile. «Se Home Assistant lo sa fare, si crea un oggetto di Home
Assistant» e' sempre stato un criterio per decidere cosa NON mettere nel
prodotto; qui e' la funzione che, davanti a una richiesta, dice *questa e'
un'automazione* e la fa costruire.

**Consiglia, non blocca.** Se dissente da come la richiesta e' stata posta, lo
dichiara (`dissenso`) e l'anteprima porta le due letture: decide l'utente. Il
consiglio finisce nella cronaca, cosi' si puo' MISURARE quanto sbaglia invece
di crederlo.

Puro: nessuna rete, nessun archivio, nessun orologio. Si prova per intero
senza Home Assistant.
"""
from __future__ import annotations


def consiglia(intent: dict) -> dict:
    """`{"strutture": [...], "motivo": str, "dissenso": bool}`.

    `strutture` e' in ordine di composizione: quando sono due, l'automazione
    viene prima perche' e' lei a chiamare lo script.
    """
    innesco = intent.get("innesco") or []
    passi = intent.get("passi") or []
    states = intent.get("stati") or []
    parametri = intent.get("parametri") or []
    riuso = bool(intent.get("riuso"))
    ricorrente = bool(intent.get("ricorrente"))
    richiesto = intent.get("richiesto")

    strutture: list[str] = []
    reasons: list[str] = []

    if not innesco and not passi and not states:
        return {"strutture": [], "dissenso": False,
                "motivo": ("non ho capito cosa dovrebbe fare: non c'e' un innesco, "
                           "non c'e' una sequenza di passi e non ci sono stati da "
                           "ristabilire.")}

    if ricorrente and not innesco:
        # Il caso che previene il doppione con lo schedulatore. Va PRIMA del
        # ramo sull'innesco perche' una ricorrenza arriva spesso senza che il
        # modello abbia gia' composto il trigger orario.
        strutture.append("automazione")
        reasons.append("una ricorrenza e' un'automazione di Home Assistant, non una "
                      "promessa: le promesse servono per «fra un'ora, una volta»")
    elif innesco:
        strutture.append("automazione")
        reasons.append("c'e' un innesco, quindi e' un'automazione")

    if parametri:
        if "script" not in strutture:
            strutture.append("script")
        reasons.append("serve un parametro in ingresso, e le automazioni non ne "
                      "prendono: quella parte e' uno script con `fields`")
        if riuso and passi:
            reasons.append("inoltre la sequenza si riusa anche altrove, quindi lo script "
                          "puo' essere richiamato da altri posti")
    elif riuso and passi and "automazione" in strutture:
        strutture.append("script")
        reasons.append("la sequenza si riusa anche altrove, quindi vive in uno script "
                      "che l'automazione chiama")
    elif passi and not strutture:
        strutture.append("script")
        reasons.append("e' una sequenza che lanci tu, senza innesco: e' uno script")

    if states:
        strutture.append("scena")
        if len(strutture) == 1:
            # Solo scena, nessuna automazione o script
            reasons.append("sono stati da ristabilire insieme, senza innesco e senza "
                          "sequenza: e' una scena")
        else:
            # Scena accesa da automazione e/o script
            if "automazione" in strutture and "script" in strutture:
                reasons.append("gli stati vengono ristabiliti in una scena che automazione "
                              "e script accendono insieme")
            elif "automazione" in strutture:
                reasons.append("gli stati vengono ristabiliti in una scena che l'automazione "
                              "accende")
            else:
                reasons.append("gli stati vengono ristabiliti in una scena che lo script "
                              "accende")

    dissenso = bool(richiesto) and richiesto not in strutture
    if dissenso:
        reasons.append(f"hai chiesto «{richiesto}», e secondo me qui serve "
                      f"{' e '.join(strutture)}; dimmi tu")

    return {"strutture": strutture, "motivo": "; ".join(reasons), "dissenso": dissenso}
