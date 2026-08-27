"""La forma di una promessa -- e l'unico posto in cui si decide com'e' fatta.

Puro: nessun I/O, nessun orologio letto qui dentro (`adesso` arriva sempre da
fuori, o i test dovrebbero inseguire il tempo vero). Chi salva e' l'archivio,
chi la sveglia e' l'orologio: qui c'e' solo cosa puo' nascere e come si legge.

`serializza()` e' l'unica forma della promessa, e vale sia per lo strumento del
modello sia per la rotta HTTP. Sono due porte sulla stessa cosa, e la
fondamenta n.3 chiede che ne esca la stessa cosa: due funzioni sarebbero due
verita' che divergono al primo campo aggiunto da una parte sola.

Le chiavi in uscita ci sono SEMPRE, anche a `None`. Una chiave che compare per
un `fai` e sparisce per un `chiedi` obbligherebbe chi legge a sapere gia' di
che specie sta parlando -- cioe' a interpretare il dato con qualcosa che il
dato non porta.
"""
from __future__ import annotations

import json

SPECIE = ("fai", "chiedi")
STATI_CONCLUSI = ("mantenuta", "saltata", "disdetta", "fallita")
# L'insieme «in sospeso» -- la sua UNICA casa (review finale, rilievo ②).
# Prima viveva scritto a mano in due punti di `archivio.py` (due `WHERE
# stato IN (...)` SQL letterali) e una terza volta in
# `static/config/promesse-route.js::STATI_SOSPESO`, senza niente che li
# legasse: uno stato non conclusivo aggiunto qui un domani sarebbe sparito
# in silenzio dalla sezione azionabile della pagina, senza che niente
# fallisse -- precisamente il rischio che la spec §12 nomina per la fetta
# successiva (i lavori di sistema, «la specie e' un campo, non un `if`»).
# `tests/js/promesse-route-vocabolario.test.mjs` lega questo insieme al
# JavaScript: e' quello che rende la divergenza NON silenziosa
# (`scripts/doppioni.py`, `_costanti_gia_legate`).
STATI_SOSPESO = ("in_attesa", "in_corso")

# La tolleranza: oltre questa, una promessa scaduta non si mantiene piu' --
# si dichiara `saltata`. Una sola, non configurabile per promessa (spec §7).
# Copre il caso vero per cui esiste: un aggiornamento dell'add-on che cade
# sopra l'orario.
TOLLERANZA_S = 120
# I due tetti (spec §9.1.6): non si promette oltre 30 giorni, e non stanno in
# sospeso piu' di 50 promesse. Servono perche' un modello che va in circolo non
# deve poter riempire il disco.
ORIZZONTE_S = 30 * 86400
TETTO_IN_SOSPESO = 50
# Quanto si conserva una promessa CONCLUSA (spec §8.1). Un registro che cresce
# per sempre su una scheda SD e' un guasto rimandato. E' una politica di
# QUESTO strato (lo Schedulatore), indipendente da quella della cronaca delle
# esecuzioni (`azione/cronaca.py::CONSERVAZIONE_ESECUZIONI_S`, nello strato
# sotto): oggi vale lo stesso numero, 90 giorni, ma sono due fatti distinti --
# per quanto si conserva una PROMESSA conclusa, per quanto si conserva
# un'ESECUZIONE -- che possono divergere in futuro senza che l'uno debba
# inseguire l'altro.
CONSERVAZIONE_S = 90 * 86400

_CHIAVI = (
    "id", "specie", "frase", "quando_ts", "quando_detto", "fuso", "chiamata",
    "domanda", "istantanea", "recapito", "stato", "motivo", "esecuzione_id",
    "testo", "avvisare", "nata_ts", "risvegliata_ts",
)


def valida(dati: dict, *, adesso: float) -> str | None:
    """Il motivo per cui questa promessa non puo' nascere, o `None`.

    Ritorna una frase da mostrare all'utente, non un codice: chi la riceve e'
    uno strumento che parla a un modello, che a sua volta la deve poter
    spiegare a una persona.
    """
    specie = dati.get("specie")
    if specie not in SPECIE:
        return ("una promessa e' «fai» (un'azione) o «chiedi» (una domanda a cui "
                f"rispondere piu' tardi): «{specie}» non e' ne' l'una ne' l'altra.")

    frase = dati.get("frase")
    if not isinstance(frase, str) or not frase.strip():
        return ("serve la frase con cui l'hai chiesto, cosi' com'e': e' cio' che "
                "rende la promessa leggibile anche fra sei mesi.")

    quando = dati.get("quando_ts")
    if not isinstance(quando, (int, float)) or isinstance(quando, bool):
        return "serve un momento preciso in cui mantenerla."
    if quando <= adesso:
        return ("quel momento e' gia' passato: intendevi domani? Dimmelo e la "
                "rifaccio.")
    if quando > adesso + ORIZZONTE_S:
        return ("non tengo promesse oltre 30 giorni: e' il tetto che HIRIS si "
                "e' dato.")

    if specie == "fai":
        chiamata = dati.get("chiamata")
        if not isinstance(chiamata, dict) or not chiamata.get("servizio"):
            return "una promessa «fai» ha bisogno del servizio da chiamare."
    else:
        domanda = dati.get("domanda")
        if not isinstance(domanda, str) or not domanda.strip():
            return "una promessa «chiedi» ha bisogno della domanda a cui rispondere."
    return None


def _carica(grezzo):
    """Un campo JSON dell'archivio, o `None`. Non solleva mai.

    Una riga scritta male non deve rendere illeggibile TUTTA la promessa: la
    frase e lo stato restano veri anche se `chiamata` non si riapre.
    """
    if not grezzo:
        return None
    try:
        return json.loads(grezzo)
    except (ValueError, TypeError):
        return None


def serializza(riga) -> dict:
    """L'unica forma di una promessa. Stesse chiavi, sempre."""
    fuori = {
        "id": riga["id"],
        "specie": riga["specie"],
        "frase": riga["frase"],
        "quando_ts": riga["quando_ts"],
        "quando_detto": riga["quando_detto"],
        "fuso": riga["fuso"],
        "chiamata": _carica(riga["chiamata_json"]),
        "domanda": riga["domanda"],
        "istantanea": _carica(riga["istantanea_json"]),
        "recapito": riga["recapito"],
        "stato": riga["stato"],
        "motivo": riga["motivo"],
        "esecuzione_id": riga["esecuzione_id"],
        "testo": riga["testo"],
        "avvisare": None if riga["avvisare"] is None else bool(riga["avvisare"]),
        "nata_ts": riga["nata_ts"],
        "risvegliata_ts": riga["risvegliata_ts"],
    }
    assert set(fuori) == set(_CHIAVI)  # la forma e' una sola, e si controlla qui
    return fuori


def motivo_ritardo(ritardo_s: float) -> str:
    """Cio' che si e' MISURATO, non una causa inventata (spec §7).

    HIRIS non sa perche' era ferma. Sa di quanto e' in ritardo, e dice solo
    quello.
    """
    minuti = int(ritardo_s // 60)
    if minuti < 1:
        return "scaduta da meno di un minuto quando l'orologio l'ha vista -- non eseguita."
    return f"scaduta da {minuti} minuti quando l'orologio l'ha vista -- non eseguita."
