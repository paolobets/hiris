"""I cancelli dei canali (spec 2026-09-21 §9).

Tre proprieta' che non si rompono per un errore, ma per il tempo: un canale
aggiunto mesi dopo da chi non ha letto niente di questo sprint, un ruolo nuovo
che nessuno mappa, e un ripiego temporaneo che nessuno si ricorda di togliere.

**Gli elenchi si chiedono** (I-0): i canali al modulo che li dichiara, i ruoli
alla tabella che li mappa, le rotte al router. Cio' che resta scritto a mano e'
la decisione, non la copia di un fatto.
"""
import ast
import datetime
import itertools
import pathlib
import re

from hiris.app.api import canali

RADICE = pathlib.Path(__file__).resolve().parents[1]
_CONFINE = RADICE / "hiris" / "app" / "api" / "middleware_internal_auth.py"


def test_ogni_canale_ha_una_specie_CONOSCIUTA():
    """Una specie sconosciuta finirebbe nella cronaca come una parola che
    nessun lettore sa interpretare -- e «integrazione» e «luogo» non sono
    sinonimi: una macchina non e' in nessun posto, un pannello si'.

    Mutazione: dare a un canale una specie inventata -- rossa."""
    for nome, riga in canali.CANALI.items():
        assert riga["specie"] in ("integrazione", "luogo"), (
            f"«{nome}»: specie {riga['specie']!r}")


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


def test_il_ripiego_al_token_ha_una_SCADENZA_dichiarata():
    """**Il cancello piu' scomodo di questo sprint, ed e' voluto.**

    Il token condiviso resta per una fetta perche' il gateway e il proxy di
    Retro Panel vivono in due repository separati (spec §8). Un ripiego del
    genere non si rompe: si dimentica. Fra sei mesi e' ancora li', e il
    segreto condiviso -- cioe' il difetto che questo invariante esiste per
    chiudere -- e' ancora vivo accanto alla difesa che avrebbe dovuto
    sostituirlo.

    **La misura decide quando chiudere PRIMA; questa data garantisce che non si
    chiuda MAI DOPO.** Non e' la fine della convivenza: e' il suo limite.

    Quando questa prova diventa rossa la risposta non e' spostare la data: e'
    guardare il registro. Se tace, si toglie il ripiego. Se parla, si sa
    esattamente quale integrazione manca -- ed e' quello il lavoro.
    """
    # `now(UTC)` e non `today()`: la data locale dipende dal fuso della
    # macchina che esegue il cancello, e un cancello che scatta un giorno
    # prima in Australia e' un cancello che scatta a caso.
    oggi = datetime.datetime.now(datetime.UTC).date()

    assert oggi <= canali.CONVIVENZA_SCADENZA, (
        f"la convivenza col token condiviso doveva chiudersi entro "
        f"{canali.CONVIVENZA_SCADENZA} e oggi è {oggi}. Guarda il registro "
        "dell’add-on: se la riga «convivenza:» tace, togli il ramo del token da "
        "`middleware_internal_auth` e questa costante. Se parla, dice quale "
        "integrazione non firma ancora. Spostare la data non è una risposta")


def test_il_ramo_del_token_e_ancora_li_finche_la_convivenza_dura():
    """La contropartita della prova qui sopra: se qualcuno togliesse il ripiego
    **prima** che le integrazioni sappiano firmare, le spegnerebbe in silenzio.

    Le due prove insieme dicono una cosa sola: il ripiego esiste, e ha una
    fine. Toglierlo e' un gesto deliberato che rende rossa questa, non una
    dimenticanza che non rende rossa nessuna.

    Mutazione ESEGUITA: tolto il ramo del token dal confine -- rossa."""
    sorgente = _CONFINE.read_text(encoding="utf-8")

    assert "convivenza:" in sorgente, (
        "il ramo del token condiviso non c’è più: se è voluto, togli anche "
        "`CONVIVENZA_SCADENZA` e questa prova, perché insieme dichiarano un "
        "ripiego che non esiste")


def test_il_confine_verifica_la_firma_PRIMA_di_guardare_il_token():
    """L'ordine conta, e non e' stile. Se il token si guardasse per primo, chi
    lo possiede non firmerebbe mai -- e la convivenza non finirebbe, perche'
    nessuno avrebbe motivo di aggiornare niente.

    Mutazione ESEGUITA: invertire i due rami -- rossa.
    """
    sorgente = _CONFINE.read_text(encoding="utf-8")
    albero = ast.parse(sorgente)
    confine = next(n for n in ast.walk(albero)
                   if isinstance(n, ast.AsyncFunctionDef)
                   and n.name == "internal_auth_middleware")
    corpo = ast.get_source_segment(sorgente, confine) or ""

    assert corpo.index("_canale(request)") < corpo.index("compare_digest"), (
        "il token si guarda prima della firma: chi ha il token non avrebbe "
        "nessun motivo di firmare, e la convivenza non finirebbe mai")


def test_le_intestazioni_della_firma_sono_le_STESSE_dei_due_lati():
    """Chi firma e chi verifica devono nominare le stesse intestazioni. Se
    divergessero, ogni firma legittima verrebbe rifiutata e il messaggio
    d'errore parlerebbe della firma invece che del nome di un'intestazione.

    Mutazione: rinominare `X-HIRIS-Firma` in un posto solo -- rossa."""
    sorgente = _CONFINE.read_text(encoding="utf-8")
    nominate = set(re.findall(r'"(X-HIRIS-[A-Za-z]+)"', sorgente))

    assert {"X-HIRIS-Canale", "X-HIRIS-Momento", "X-HIRIS-Unico",
            "X-HIRIS-Firma"} <= nominate, (
        f"il confine nomina {sorted(nominate)}: mancano intestazioni che la "
        "spec §6 dichiara")
