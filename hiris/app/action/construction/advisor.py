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

# Le TRE strutture che Home Assistant sa costruire -- e l'UNICA casa del
# vocabolario di `richiesto`. Non e' un elenco di comodo: e' cio' che rende
# `richiesto` un campo CHIUSO invece di una frase.
#
# Il rilievo che l'ha fatta nascere (audit delle fondamenta, 08/09/2026):
# `richiesto` era descritto al modello come «cosa ha chiesto l'utente», cioe'
# testo libero, e confrontato qui sotto con un'appartenenza. Sulla casa vera
# la costruzione applicata `automation.1784125482111029` porta scritto «hai
# chiesto "correzione errori di configurazione dell'automazione esistente", e
# secondo me qui serve automazione; dimmi tu»: il consigliere dissentiva da
# se stesso, e la cronaca -- che esiste per MISURARE quanto il mestiere
# sbaglia -- ha registrato un dissenso falso.
#
# Due cose diverse dette con una parola sola, e si separano ALLA FONTE:
# «quale delle tre strutture» e' questo campo, «cosa ha detto la persona» e'
# `frase`. Lo schema dello strumento dichiara l'enumerazione
# (`home_space/tools.py`, PROPOSE_TOOL_DEF) e la porta la impone
# (`workshop._invalid_form`): una normalizzazione di stringhe piu' furba
# avrebbe spostato il buco -- «correzione errori ... dell'automazione
# esistente» CONTIENE la parola giusta e non e' una richiesta di struttura.
STRUCTURES: tuple[str, ...] = ("automazione", "script", "scena")


def consiglia(intent: dict) -> dict:
    """`{"strutture": [...], "motivo": str, "dissenso": bool}`.

    `strutture` e' in ordine di composizione: quando sono due, l'automazione
    viene prima perche' e' lei a chiamare lo script.

    `richiesto` e' una delle tre parole di `STRUCTURES`, o niente. Chi chiama
    dalla produzione passa dalla porta, che rifiuta il resto; questa funzione
    e' pura e non si fida lo stesso -- un valore fuori vocabolario non e' una
    struttura, quindi non c'e' niente da cui dissentire. Tacere e' l'unica
    risposta vera: inventare un disaccordo con una frase e' il difetto, e
    provare a indovinare quale struttura quella frase intendesse sarebbe lo
    stesso difetto con piu' passaggi.
    """
    innesco = intent.get("innesco") or []
    passi = intent.get("passi") or []
    states = intent.get("stati") or []
    parametri = intent.get("parametri") or []
    riuso = bool(intent.get("riuso"))
    ricorrente = bool(intent.get("ricorrente"))
    requested = intent.get("richiesto")

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
        reasons.append("una ricorrenza e' un’automazione di Home Assistant, non una "
                      "promessa: le promesse servono per «fra un’ora, una volta»")
    elif innesco:
        strutture.append("automazione")
        reasons.append("c’e' un innesco, quindi e' un’automazione")

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
                      "che l’automazione chiama")
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
                reasons.append("gli stati vengono ristabiliti in una scena che l’automazione "
                              "accende")
            else:
                reasons.append("gli stati vengono ristabiliti in una scena che lo script "
                              "accende")

    dissenso = requested in STRUCTURES and requested not in strutture
    if dissenso:
        reasons.append(f"hai chiesto «{requested}», e secondo me qui serve "
                      f"{' e '.join(strutture)}; dimmi tu")

    return {"strutture": strutture, "motivo": "; ".join(reasons), "dissenso": dissenso}
