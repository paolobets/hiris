"""Riconoscere di quale parte della casa parla una frase.

La semantica NON la fa questo modulo. Il modello, che ha la casa in
contesto, e' quello che capisce che "in salotto fa freddo" parla dell'area
"soggiorno" anche se l'utente non ha mai scritto quell'alias: e' esattamente
il principio della specifica -- il modello propone l'ancora nominando il suo
identificatore, e questo modulo restringe:

- `Lookup.verify(tipo, riferimento)` e' il CANCELLO: controlla che
  l'identificatore che il modello ha nominato esista davvero, con quel
  tipo, nell'anagrafe. Se non esiste, l'ancora non si scrive.

Il confronto dei nomi che usa la porta della casa (`name_matches`, con il
suo normalizzatore e le parole funzionali dell'italiano) stava qui fino alla
Tappa 3, Task 9 (B-51): nessuno in `memory/` lo usava, e ora vive in
`home_space/reference.py`, accanto a chi lo chiama.

Fino alla 3.72.2 c'era anche `Lookup.find(frase)`, la «rete» che riconosceva
nomi e alias dentro una frase. Nessun chiamante di produzione la usava piu'
(voce M-08 del registro), ed e' uscita con la Tappa 0 dello sprint «Una fonte
sola di verita'» insieme all'indice dei termini e ai nomi di ripiego, che
servivano solo a lei.

Niente fuzzy, niente embedding: un sinonimo che l'utente non ha dichiarato
non e' un sinonimo, e HIRIS non ha un embedder.
"""
from __future__ import annotations

# Tipi che l'indice riconosce, nello spazio di nomi di `Lookup.verify()`: stessa
# forma dei termini che il modello vede quando la casa gli e' data in
# contesto, cosi' l'ancora che nomina "area" o "entita" e' gia' la chiave
# con cui si cerca qui.
#
# I PIANI (e le ETICHETTE come candidati di se stesse) ci sono stati dal T7
# (R2, docs/design/2026-08-20-i-riferimenti.md) al 30/09/2026: servivano alla
# vecchia ricerca per nome, che doveva produrre l'id di un piano per
# `execute(piani=...)`. Da «una porta sola per la casa» il piano e' un FILTRO
# della porta (`house_query`), e l'unico lettore rimasto di questo indice e'
# `remember`, che ancora solo aree, entita' e dispositivi: un candidato che nessuno puo' usare e'
# codice morto, ed e' uscito (review finale, M3).
#
# Automazioni e script NON entrano qui, apposta: vengono dal comportamento
# (`HomeSpace.behavior()`, in `home_space/reader.py`), una fonte diversa (non
# un registro di Home Assistant) con un proprio
# segnale di incompletezza (`unread_bodies()`, non `unavailable()`)
# e un proprio campo `tipo` PER VOCE -- una lista sola contiene sia le
# automazioni sia gli script, a differenza di `_ARCHIVI` dove ogni chiave
# e' UN tipo solo. Mescolarli qui avrebbe fatto sembrare "automazione" un
# registro dell'anagrafe che puo' comparire in `unavailable()`, cosa
# che non fa mai -- e avrebbe allargato `STORE_KEY_PER_TYPE`, e con lei i
# tipi di ancora della memoria, a tipi che `Lookup.verify()` non sa
# verificare.
#
# QUESTA tupla e' il vocabolario delle ancore: `memory/interpretation.
# VOCABULARY["ancore"]` e `_TETHER_TYPES` in home_space/tools.py la chiedono
# a `STORE_KEY_PER_TYPE` invece di riscriverla (Tappa 3, Task 9, B-51).
# Fino al 29/09/2026 `costruisci_indice()` le indicizzava per conto suo, per
# la vecchia ricerca per nome (`queries.search`); uscita quella, nessun
# chiamante le chiedeva piu' -- la porta della casa (`home_space/
# house_query.py`) confronta i nomi da se' -- e il parametro e' uscito con
# lei.
_ARCHIVI = (("aree", "area"), ("entita", "entita"), ("dispositivi", "dispositivo"))

# Stessa mappa di _ARCHIVI, capovolta: dato il tipo di un'ancora, la chiave
# del registro che l'anagrafe usa per quel tipo. Pubblica perche' serve a chi
# deve sapere se QUEL registro specifico ha risposto all'ultima lettura
# (`HomeSpace.unavailable()`), non solo se l'anagrafe intera e' stata
# letta -- vedi handlers_memory.py.
STORE_KEY_PER_TYPE: dict[str, str] = {type: key for key, type in _ARCHIVI}


class Lookup:
    """L'anagrafe di una casa, pronta per verificare un'ancora e per elencare
    le voci di un tipo. Si costruisce con `costruisci_indice()`."""

    def __init__(self, per_type: dict[str, dict[str, dict]]) -> None:
        self._per_type = per_type

    def verify(self, type: str, reference: str) -> dict | None:
        """L'oggetto dell'anagrafe se `reference` esiste con quel `type`,
        altrimenti None.

        E' il punto in cui "il modello propone, il codice restringe"
        diventa codice: un'ancora che il modello si e' inventata non entra.
        Nessuna somiglianza qui -- tipi diversi sono spazi di nomi diversi,
        e un id di entita' passato come area non deve passare.
        """
        return self._per_type.get(type, {}).get(reference)

    def tutti(self, type: str) -> list[dict]:
        """Tutte le voci dell'anagrafe di un tipo — aree, entita' o dispositivi.

        Serve a chi deve DEDURRE qualcosa dalla casa invece che verificarla:
        per esempio l'unita' di misura di un'area, che si ricava dall'entita'
        di quell'area la cui classe combacia con la grandezza.
        """
        return list(self._per_type.get(type, {}).values())


def costruisci_indice(home_space: dict) -> Lookup:
    """L'indice di una casa: le voci di aree, entita' e dispositivi, per tipo
    e per identificatore."""
    per_type: dict[str, dict[str, dict]] = {}
    for store_key, type in _ARCHIVI:
        registry = per_type.setdefault(type, {})
        for entry in home_space.get(store_key) or []:
            reference = entry.get("id")
            if reference is not None:
                registry[reference] = entry
    return Lookup(per_type)
