"""I cancelli dei canali (spec 2026-09-21 §9).

Tre proprieta' che non si rompono per un errore, ma per il tempo: un canale
aggiunto mesi dopo da chi non ha letto niente di questo sprint, un ruolo nuovo
che nessuno mappa, e un ripiego temporaneo che nessuno si ricorda di togliere.

**Gli elenchi si chiedono** (I-0): i ruoli alla tabella che li mappa, le specie
al modulo che le possiede, le intestazioni al confine. Cio' che resta scritto a
mano e' la decisione, non la copia di un fatto.
"""
import ast
import itertools
import pathlib
import re

from hiris.app.api import canali

RADICE = pathlib.Path(__file__).resolve().parents[1]
_CONFINE = RADICE / "hiris" / "app" / "api" / "middleware_internal_auth.py"


def test_la_specie_di_RIPIEGO_e_una_specie_che_esiste():
    """Dal 22/09/2026 la specie di un servizio la decide il proprietario quando
    approva, e l'insieme chiuso vive in `servizi.SPECIE`. Ma una riga
    d'archivio senza specie c'e' comunque un ripiego, e quel ripiego finisce
    nella cronaca: se fosse una parola fuori dall'insieme, sarebbe una parola
    che nessun lettore sa interpretare -- e «integrazione» e «luogo» non sono
    sinonimi, una macchina non e' in nessun posto, un pannello si'.

    Mutazione ESEGUITA: ripiegare su «luogo» (che esiste) -- verde, come deve
    essere; ripiegare su «dispositivo» -- rossa."""
    from hiris.app.api import servizi

    assert canali.SPECIE_IGNOTA in servizi.SPECIE, (
        f"il ripiego è {canali.SPECIE_IGNOTA!r}, che non è una specie: "
        f"sono {', '.join(servizi.SPECIE)}")


def test_la_tabella_dei_ruoli_e_ORDINATA_dal_piu_largo_al_piu_stretto():
    """Non e' estetica: chi legge `PUO` deve poter vedere a colpo d'occhio che
    i permessi sono **annidati** -- cio' che puo' un `lettore` lo puo' anche un
    `utente`, e cio' che puo' un `utente` lo puo' anche un amministratore. Un
    ruolo che rompesse l'annidamento sarebbe un permesso che qualcuno ha e
    qualcuno piu' potente no, cioe' una regola che nessuno si aspetta.

    Mutazione ESEGUITA: dare a `lettore` un permesso che `utente` non ha --
    rossa."""
    scala = ["lettore", "utente", "amministratore"]
    for stretto, largo in itertools.pairwise(scala):
        for gesto, puo in canali.PUO[stretto].items():
            if puo:
                assert canali.PUO[largo][gesto], (
                    f"«{stretto}» può {gesto} ma «{largo}», che è più largo, no")


def test_il_segreto_condiviso_NON_PUO_TORNARE():
    """**Il cancello che ha sostituito quello della convivenza** (22/09/2026).

    Qui c'erano due prove gemelle: una diceva «il ripiego al token ha una
    scadenza», l'altra «il ramo del token e' ancora li' finche' la convivenza
    dura». Erano giuste finche' il ripiego esisteva. Adesso e' uscito, e
    lasciarle avrebbe dichiarato un ripiego che non c'e'.

    Cio' che resta da sorvegliare e' il verso opposto: **che non torni**. Un
    segreto condiviso e' la cosa piu' facile da riaggiungere -- tre righe, e
    risolve qualunque integrazione che non ha voglia di firmare. Il giorno in
    cui qualcuno le scrive, questa prova diventa rossa e lo costringe a
    passare di qui.

    Si guarda la FORMA, come per le porte di scrittura dell'attuatore: il
    comportamento non lo distinguerebbe da una credenziale legittima.

    Mutazione ESEGUITA: rimesso `hmac.compare_digest(...)` col token dell'app
    nel confine -- rossa.
    """
    sorgente = _CONFINE.read_text(encoding="utf-8")
    albero = ast.parse(sorgente)
    confine = next(n for n in ast.walk(albero)
                   if isinstance(n, ast.AsyncFunctionDef)
                   and n.name == "internal_auth_middleware")
    corpo = ast.get_source_segment(sorgente, confine) or ""

    assert "compare_digest" not in corpo, (
        "il confine confronta di nuovo un segreto: se e' una credenziale "
        "EFFIMERA il confronto sta in `api/credenziali.py`, non qui; se e' un "
        "segreto condiviso, e' il reperto A-5 che torna — uno per tutti i "
        "portatori, in chiaro nei backup, e nessun registro che dica quale "
        "integrazione ha chiamato")
    assert 'app.get("internal_token"' not in corpo and \
           'app["internal_token"]' not in corpo, (
        "il confine legge di nuovo un token condiviso dalle opzioni")


def test_restano_TRE_strade_e_si_chiamano_per_nome():
    """La contropartita del cancello qui sopra: togliere e basta non e' la
    proprieta' che si vuole. Le tre strade devono esserci tutte, o «l'abbiamo
    messo in sicurezza» vorrebbe dire «l'abbiamo spento».

    Mutazione ESEGUITA: tolto il ramo della credenziale di turno -- rossa (il
    ponte si spegnerebbe in silenzio)."""
    sorgente = _CONFINE.read_text(encoding="utf-8")

    for strada in ("_firmatario", "_is_supervisor_ingress", "credenziali"):
        assert strada in sorgente, f"manca la strada «{strada}»"


def test_le_intestazioni_della_firma_sono_le_STESSE_dei_due_lati():
    """Chi firma e chi verifica devono nominare le stesse intestazioni. Se
    divergessero, ogni firma legittima verrebbe rifiutata e il messaggio
    d'errore parlerebbe della firma invece che del nome di un'intestazione.

    Mutazione: rinominare `X-HIRIS-Firma` in un posto solo -- rossa."""
    sorgente = _CONFINE.read_text(encoding="utf-8")
    nominate = set(re.findall(r'"(X-HIRIS-[A-Za-z]+)"', sorgente))

    assert {"X-HIRIS-Servizio", "X-HIRIS-Momento", "X-HIRIS-Unico",
            "X-HIRIS-Firma"} <= nominate, (
        f"il confine nomina {sorted(nominate)}: mancano intestazioni che la "
        "spec §6 dichiara")
