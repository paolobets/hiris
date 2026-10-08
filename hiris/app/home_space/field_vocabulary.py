"""Il vocabolario dei campi: come si chiamano i fatti che escono (Tappa 9,
F2; piano della Tappa 4, D1, approvato dal proprietario il 05/10/2026).

Sono i nomi delle chiavi che HIRIS scrive quando rende un oggetto della casa
-- un'entita', un dispositivo, un'area, un'automazione, un ricordo -- verso il
modello e verso le pagine. Non sono identificatori Python: sono valori che
attraversano un confine, e restano italiani (CLAUDE.md, «il dominio in
italiano»). La resa (`render.py`) li scrive; il cancello R3
(`tests/test_resa_unica.py`) li chiede qui per riconoscere chi compone
un'entita' fuori dalla resa.

**Il glossario e questo modulo dicono la stessa cosa, e una prova li tiene
uguali.** `docs/GLOSSARIO.md`, «Il vocabolario dei campi», e' il registro dei
nomi che il proprietario ha approvato: non entra nell'immagine (il
`Dockerfile` copia solo `app/`), quindi il prodotto non puo' leggerlo. Questo
modulo e' la sua forma nel codice. `tests/test_vocabolario_dei_campi.py`
confronta le due, campo per campo e proprietario per proprietario: un campo
nuovo che entra da una parte sola fa arrossire la prova.

**Una costante per campo, no.** Il piano della Tappa 4 parlava di «una
costante col suo nome» per campo; la resa scrive le chiavi come letterali,
dentro l'unico modulo che le compone, e quaranta costanti che nessuno legge
sarebbero codice morto (il censimento le troverebbe). Il fatto vive qui una
volta, nella tabella `FIELDS`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    """Un campo: il fatto in una riga, la sua forma, e i generi che lo
    portano (`house_query.KINDS`, piu' `scena` e le parole per cio' che non e'
    un oggetto della casa: `casa`, `evento`, `misura`, `finestra`,
    `lettura`). `replaces` sono i nomi che questo campo ha tolto: restano
    qui perche' il cancello R3 riconosca chi torna a scriverli."""
    fact: str
    shape: str
    owners: frozenset[str]
    replaces: frozenset[str] = frozenset()


def _field(fact: str, shape: str, *owners: str, replaces: tuple[str, ...] = ()) -> Field:
    return Field(fact, shape, frozenset(owners), frozenset(replaces))


#: Ogni oggetto della casa con un nome che Home Assistant mostra.
_NAMED = ("entita", "dispositivo", "area", "integrazione", "automazione", "script", "scena")
#: Gli oggetti che stanno in un posto: un'area, un piano, un dispositivo.
_PLACED = ("entita", "dispositivo", "area", "automazione", "script", "scena")
#: I comportamenti con uno stato e un'ultima esecuzione.
_RUNNING = ("automazione", "script")

FIELDS: dict[str, Field] = {
    "id": _field("l'identificatore proprio dell'oggetto",
                 "stringa: l'entity_id per un'entita', l'id del registro di Home Assistant "
                 "per area, piano, dispositivo, comportamento; il dominio per "
                 "un'integrazione; l'id di HIRIS per un ricordo",
                 *_NAMED, "ricordo", replaces=("entita",)),
    "area": _field("l'area in cui sta", "{id, nome}", *_PLACED),
    "piano": _field("il piano in cui sta", "{id, nome}", *_PLACED),
    "dispositivo": _field("il dispositivo a cui appartiene", "{id, nome}", *_PLACED),
    "integrazione": _field("l'integrazione da cui un'entita' viene (la sua piattaforma)",
                           "{id, nome}: il dominio dell'integrazione e il titolo della "
                           "sua istanza", "entita", replaces=("piattaforma",)),
    "stato": _field("lo stato grezzo, la parola di Home Assistant",
                    "stringa, come la scrive Home Assistant", "entita", *_RUNNING, "scena",
                    replaces=("valore", "state")),
    "stato_leggibile": _field("lo stato in parole",
                              "stringa italiana; un produttore solo, topology.readable_state",
                              "entita"),
    "stato_non_reso": _field("perche' lo stato in parole manca quando la tabella delle "
                             "traduzioni non si e' letta", "{silenzio, motivo}", "entita"),
    "ultimo_cambio": _field("l'ultimo cambio di stato", "istante (ISO 8601 con l'offset "
                            "della casa)", "entita", *_RUNNING, "scena", replaces=("da_quando",)),
    "ultima_esecuzione": _field("l'ultima volta che e' girata", "istante", *_RUNNING),
    "quando": _field("l'istante di un evento o di una misura", "istante", "evento", "misura",
                     replaces=("quando_ts", "misurato_ts", "letta_alle", "deciso_ts",
                               "da_quando_ts")),
    "dal": _field("l'inizio di un intervallo", "istante", "finestra"),
    "al": _field("la fine di un intervallo", "istante", "finestra"),
    "genere": _field("il nostro genere di oggetto", "uno di house_query.KINDS",
                     *_NAMED, "ricordo", replaces=("tipo",)),
    "dominio": _field("il dominio di Home Assistant", "stringa di Home Assistant", "entita",
                      replaces=("tipo",)),
    "unita": _field("l'unita' dell'entita'", "stringa di Home Assistant", "entita",
                    replaces=("unit",)),
    "sistema_unita": _field("la cornice di riferimento della casa",
                            "il dizionario del sistema di unita' di Home Assistant", "casa",
                            replaces=("unita",)),
    "limiti": _field("i limiti di un comando", "dizionario minimo/massimo/passo, con l'unita",
                     "entita", replaces=("unita",)),
    "statistiche": _field("Home Assistant tiene le statistiche", "booleano", "entita",
                          replaces=("ha_statistiche",)),
    "volte": _field("quante volte", "intero", "evento", replaces=("count",)),
    "lette": _field("l'esito della lettura di un insieme", "booleano", "lettura",
                    replaces=("letto",)),
    "fuori": _field("perche' l'oggetto non e' fra i visibili",
                    "{classe, causa}; assente quando l'oggetto e' visibile",
                    "entita", "dispositivo",
                    replaces=("disabilitata", "nascosta", "disabilitata_da", "nascosta_da",
                              "disabilitato")),
    "attiva": _field("un'automazione accesa o spenta", "booleano", "automazione"),
    "fonte": _field("lo stato della fonte di un'entita' (House.source)",
                    "{stato, causa, ...}", "entita"),
    "codice": _field("la posizione nel codice, nelle righe d'errore della storia",
                     "stringa", "evento", replaces=("fonte",)),
    "ruolo_energia": _field("il ruolo dell'entita' nella dashboard Energia",
                            "uno dei ruoli letti da energy/get_prefs", "entita"),
    "nome": _field("il nome che Home Assistant mostra", "stringa", *_NAMED),
    "classe": _field("la classe dichiarata da Home Assistant (device_class)",
                     "stringa di Home Assistant", "entita"),
    "attributi": _field("gli attributi dello stato, filtrati, nelle loro ceste",
                        "dizionario di ceste", "entita"),
    "capacita": _field("cosa un'entita' sa fare, decodificato da supported_features",
                       "elenco di frasi", "entita"),
    "stato_presunto": _field("Home Assistant non legge lo stato, lo presume (assumed_state)",
                             "vero, solo quando lo e'", "entita"),
    "etichette": _field("le etichette scritte dal proprietario", "elenco «Nome (id: X)»",
                        *_PLACED),
    "categorie": _field("le categorie scritte dal proprietario", "{ambito: nome}",
                        "entita", "automazione", "script", "scena"),
    "regola": _field("la regola di misura di un'entita' di servizio", "frase", "entita"),
    "significato": _field("cosa significa la classe, dal sapere", "frase", "entita"),
    "membri": _field("di cosa e' fatto un gruppo, e cosa non e' di tutti",
                     "dizionario", "entita"),
    "comandi": _field("cosa si puo' chiedere a un'entita', con i limiti",
                      "{servizio: parametri}", "entita"),
}
