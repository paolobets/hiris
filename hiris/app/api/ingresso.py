"""Come si sa che una richiesta viene DAVVERO dall'ingress del Supervisor.

Reperti A-2 e A-3 del registro dei rischi (spec 2026-09-21), chiusi il 22/09.

Fino a oggi la risposta era: `X-Ingress-Path` combacia con un'espressione
regolare **e** l'indirizzo sorgente sta in `172.30.32.0/23`. Il secondo
controllo sembra stretto e non lo e': quel `/23` non e' l'indirizzo del proxy,
e' **la rete Docker in cui vive ogni add-on installato**. Qualunque add-on
vicino manda l'intestazione e ottiene `/api/*` per intero senza conoscere nessun
segreto -- e se il tunnel che pubblica la casa gira come add-on (Cloudflared,
Tailscale: il caso normale), il suo indirizzo e' li' dentro.

**La strada che sembrava giusta e NON si puo' percorrere.** Il Supervisor ha
una rotta per questo -- `POST /ingress/validate_session`, corpo
`{"session": "<valore>"}` -- e il biscotto arriva davvero all'add-on
(`_init_header()` filtra dodici intestazioni e il biscotto non e' fra quelle).
Sembrava la risposta, ed e' stata rilasciata nella 3.60.0.

**Non e' chiamabile da un add-on.** Il Supervisor ha risposto **403** al primo
tentativo vero, e la sorgente dice perche': in
`supervisor/api/middleware/security.py` le due rotte `/ingress/session` e
`/ingress/validate_session` non combaciano con nessuna delle liste permissive
-- il solo schema che le somiglia e' `/ingress/[-_A-Za-z0-9]+/.*`, che pretende
uno slug in mezzo -- quindi cadono nel controllo finale, dove passa soltanto
Home Assistant Core. **Nessun ruolo di add-on la apre**, e non e' una cosa che
si aggiusta con un permesso in `config.yaml`.

**La lezione, scritta qui perche' non si ripeta**: era stata verificata
l'esistenza della rotta, il suo contratto e il percorso del biscotto -- tutto
vero -- e **non** che il nostro chiamante avesse il diritto di chiamarla. Una
verifica che si ferma un gradino prima di «e io, posso?» e' una verifica che
non ha verificato la cosa che serviva.

## Cosa si fa invece: **l'indirizzo esatto del proxy, risolto**

A inoltrare l'ingress e' il Supervisor, e il suo nome nella rete Docker e'
`supervisor`. Risolvendolo si ottiene **un solo indirizzo**, e quello si fida:
non la rete Docker intera, dove vive ogni add-on installato.

**Si risolve, non si ricopia.** Scrivere `172.30.32.2/32` in una costante
sarebbe un fatto copiato, che diventa falso il giorno in cui quell'indirizzo
cambia -- e quel giorno l'ingress smetterebbe di funzionare senza dire perche'.
Chiederlo al risolutore lo tiene vero da solo.

E **se la risoluzione non riesce** si torna alle reti configurate, dichiarandolo
nel registro: senza quel ripiego un guasto del risolutore chiuderebbe il
proprietario fuori dal suo pannello -- che e' esattamente quello che la 3.60.0
ha fatto, e non deve poter succedere di nuovo per una via diversa.
"""
from __future__ import annotations

import ipaddress
import logging

logger = logging.getLogger(__name__)

#: La rete Docker del Supervisor, e il default dell'add-on. **E' piu' larga del
#: necessario e lo dichiariamo**: ci vive ogni add-on installato. A renderla
#: accettabile e' la sessione, non lei.
RETE_PREDEFINITA = "172.30.32.0/23"

#: Il prefisso piu' largo che si accetta. Il proxy del Supervisor e' **uno**:
#: un `/8`, anche privato, sono sedici milioni di indirizzi, e chi lo scrive
#: crede di aver ristretto mentre ha aperto.
PREFISSO_MINIMO = 16

#: Il nome con cui il Supervisor si fa trovare nella rete Docker. E' lui a
#: inoltrare l'ingress, quindi e' il suo indirizzo -- e nessun altro -- che va
#: creduto.
SUPERVISOR = "supervisor"


def reti_fidate(testo: str) -> tuple[list, list[str]]:
    """Le reti fidate lette dalle opzioni — `(reti, rifiuti)`.

    **Un campo vuoto e un campo sbagliato non sono la stessa cosa.** Vuoto vuol
    dire «non ho deciso», e allora decide il prodotto col suo default.
    Sbagliato vuol dire «ho deciso, e ho deciso una cosa che non si può fare»:
    lì non si ripiega su niente, perché ripiegare sul default largo vorrebbe
    dire che scrivere male **allarga** il perimetro invece di stringerlo — il
    proprietario crede di aver ristretto, e ha aperto.

    Ogni rifiuto nomina la voce e dice perché: un rifiuto che non nomina la
    voce costringe a indovinare quale delle tre righe è quella sbagliata.
    """
    voci = [v.strip() for v in str(testo or "").split(",") if v.strip()]
    if not voci:
        return [ipaddress.ip_network(RETE_PREDEFINITA)], []

    reti, rifiuti = [], []
    for voce in voci:
        try:
            rete = ipaddress.ip_network(voce, strict=False)
        except (ValueError, TypeError):
            rifiuti.append(
                f"«{voce}» non è una rete scritta in forma indirizzo/prefisso, "
                f"per esempio {RETE_PREDEFINITA}")
            continue
        if not rete.is_private:
            rifiuti.append(
                f"«{voce}» è una rete pubblica: il proxy del Supervisor vive "
                "nella rete interna di Docker, quindi un indirizzo pubblico lì "
                "non può essere lui")
            continue
        if rete.prefixlen < PREFISSO_MINIMO:
            rifiuti.append(
                f"«{voce}» comprende {rete.num_addresses} indirizzi: è più "
                f"larga di un /{PREFISSO_MINIMO}, e il proxy del Supervisor è "
                "uno solo")
            continue
        reti.append(rete)
    return reti, rifiuti


def indirizzo_proxy(risolutore=None) -> str:
    """L'indirizzo del Supervisor, **risolto** — stringa vuota se non si può.

    È lui a inoltrare l'ingress: fidarsi di quel solo indirizzo invece che
    della rete Docker intera è la differenza fra «il proxy» e «ogni add-on
    installato».

    Torna una stringa vuota invece di sollevare: fuori dal Supervisor quel nome
    non esiste, ed è normale.
    """
    import socket

    risolvi = risolutore or socket.gethostbyname
    try:
        return str(risolvi(SUPERVISOR) or "")
    except Exception:
        return ""


def perimetro_fidato(testo: str, risolutore=None) -> tuple[list, list[str], str]:
    """Le reti da credere — `(reti, rifiuti, come)`.

    **L'indirizzo risolto vince su tutto**: se il Supervisor risponde al suo
    nome, si crede quel solo indirizzo. Le voci scritte nelle opzioni restano
    per chi ha un impianto fuori dall'ordinario, e valgono quando la
    risoluzione non riesce.

    `come` è ciò che il registro dichiara all'avvio: chi legge deve poter
    sapere **quanto è largo** il perimetro di oggi senza andarlo a dedurre.
    """
    import ipaddress as _ip

    indirizzo = indirizzo_proxy(risolutore)
    if indirizzo:
        try:
            rete = _ip.ip_network(f"{indirizzo}/32", strict=False)
            return [rete], [], f"l’indirizzo del Supervisor, risolto: {indirizzo}"
        except (ValueError, TypeError):
            pass

    reti, rifiuti = reti_fidate(testo)
    return reti, rifiuti, (
        "le reti scritte nelle opzioni (il nome «supervisor» non si è risolto): "
        + ", ".join(str(r) for r in reti) if reti
        else "nessuna rete: il nome «supervisor» non si è risolto e le opzioni "
             "non hanno nessuna voce valida")
def prepara_ingresso(app) -> None:
    """Qui nasceva la cache delle sessioni verificate col Supervisor.

    È uscita con la verifica che la riempiva: `validate_session` è riservata a
    Home Assistant Core, quindi quella cache non avrebbe mai avuto niente da
    ricordare. La funzione resta, vuota e dichiarata, perché `server.py` la
    chiama e perché il posto dove i contenitori nascono è uno solo.
    """
