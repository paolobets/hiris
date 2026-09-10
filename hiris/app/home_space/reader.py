"""Il lettore: i registri di Home Assistant diventano l'anagrafe, **senza una
copia in mezzo**.

Sostituisce `HomeSpaceStore.replace()`. Non e' un rifacimento dei lettori: la
forma che questo modulo produce e' **la stessa** che `HomeSpaceStore.read()`
produceva, perche' `queries.py` (`search`, `view`, `hierarchy`,
`_view_entity`, `_view_device`) non contiene nemmeno una riga di SQL — sono
funzioni pure sopra un dizionario, e `briefing.compose()` pure. Cambia il
fornitore del dizionario, non chi lo legge.

**Perche' esiste.** La copia buttava via cio' che Home Assistant dichiara:
`translation_key`, `unique_id`, `original_name`. E soprattutto **non poteva
tenere la classe**: `config/entity_registry/list` risponde con
`RegistryEntry.as_partial_dict` (`helpers/entity_registry.py`), che
`device_class` non ce l'ha — misurato il 10/09/2026 sulla casa vera,
**assente su 1.227 righe su 1.227**, e `classe` NULL su **1.229 entita' su
1.229** nell'anagrafe pubblicata. Ogni lettore che decideva su quel campo era
inerte in produzione, e la piu' costosa di quelle inerzie e' stato il bilancio
dell'energia: zero oggetti in cinque giorni su cinque.

**Il confine di sanificazione resta qui.** `replace()` era l'unico scrittore
dell'anagrafe e sanificava al momento della scrittura, cosi' che ogni lettore
ereditasse la difesa senza ripeterla (C-2, `proxy/_sanitize.py`). Tolta la
scrittura, il confine e' **la costruzione**: le stesse funzioni, nello stesso
punto del flusso, un posto solo.
"""
from __future__ import annotations

from ..proxy._sanitize import sanitize_ha_free_text, sanitize_ha_value
from .topology import actual_class, actual_unit


def clean_name(value):
    """Un nome/alias/titolo destinato all'anagrafe, sanificato al confine.

    C-2 (L1-sicurezza.md): un nome/alias/titolo e' testo che HIRIS non
    controlla (un dispositivo di rete ostile, un'integrazione compromessa, un
    ospite che rinomina qualcosa). Sanificare QUI, e non a valle, significa
    che ogni lettore dell'anagrafe (il nucleo, `guarda`, `cerca`, la pagina)
    eredita la difesa senza doverla ripetere -- un punto solo, non cinque.

    `None`/non-stringa passano invariati: un campo assente non deve diventare
    una stringa vuota che afferma "questo nome c'e' ed e' vuoto".

    Usa `sanitize_ha_value` (tetto 255): ogni campo che passa di qui e'
    `state`-shaped (friendly_name, titolo, alias) -- per `motivo`, che non lo
    e', vedi `clean_reason()`.
    """
    return sanitize_ha_value(value) if isinstance(value, str) else value


def clean_reason(value):
    """Il `motivo` per cui un'integrazione non e' partita, sanificato come
    `clean_name()` -- stessa fonte, stesso rischio -- ma con un tetto DIVERSO.

    `motivo` non e' uno `state`: e' la spiegazione di un guasto
    (`error_reason_translation_key`/`reason` di HA), HA non gli impone nessun
    tetto, e un motivo vero -- il riassunto di un'eccezione -- puo' onestamente
    superare 255 senza essere un attacco. Tetto 500.
    """
    return sanitize_ha_free_text(value) if isinstance(value, str) else value


def clean_aliases(value) -> list:
    """Gli ALIAS: testo scelto dall'utente o dall'integrazione, quindi ogni
    voce passa dal sanificatore. **Mai** per le liste di id (`labels`), che
    sono slug generati da HA e risolti altrove, dalla tabella delle etichette
    -- gia' sanificata alla propria sorgente."""
    return [clean_name(v) for v in value] if isinstance(value, list) else []


def plain_list(value) -> list:
    return list(value) if isinstance(value, list) else []


def clean_categories(value) -> dict:
    """L'assegnazione delle categorie e' `{ambito: category_id}` -- non una
    lista -- perche' un'entita' puo' stare in UNA categoria per ambito
    (`RegistryEntry.categories: dict[str, str]`, verificato in
    `helpers/entity_registry.py`). Appiattirla in una lista di id butterebbe
    via l'ambito, che fa parte dell'identita' della categoria.

    Chiavi e valori si costringono a stringa e le voci vuote cadono: cio' che
    entra qui viene dalla rete.
    """
    if not isinstance(value, dict):
        return {}
    return {str(k).strip(): str(v).strip() for k, v in value.items()
            if str(k).strip() and str(v).strip()}


def _floor(row: dict) -> dict:
    return {"id": row["floor_id"], "nome": clean_name(row.get("name")) or row["floor_id"],
            "livello": row.get("level"), "icona": row.get("icon")}


def _area(row: dict) -> dict:
    """Un'area, con le due entita' che l'utente le ha dichiarato addosso.

    `temperature_entity_id`/`humidity_entity_id` dicono QUALE entita' e' la
    temperatura di quella stanza. Senza di esse HIRIS dovrebbe indovinare fra
    tutti i sensori dell'area quale intende chi chiede se fa caldo in
    soggiorno: e' il significato piu' dichiarato che esista, e costa zero
    chiamate.
    """
    return {"id": row["area_id"], "nome": clean_name(row.get("name")) or row["area_id"],
            "piano_id": row.get("floor_id"), "icona": row.get("icon"),
            "alias": clean_aliases(row.get("aliases")),
            "etichette": plain_list(row.get("labels")),
            "entita_temperatura": row.get("temperature_entity_id"),
            "entita_umidita": row.get("humidity_entity_id")}


def _device(row: dict) -> dict:
    """Un dispositivo, **come oggetto e non come identificatore opaco**.

    `nome_utente` sta accanto a `nome` e non lo sostituisce: `nome` e' il nome
    da usare (quello scelto dall'utente se c'e', altrimenti quello proposto
    dall'integrazione), `nome_utente` dice **se l'utente l'ha rinominato** --
    misurato sulla casa vera il 10/09/2026: **13 dispositivi su 241**. Sono due
    fatti diversi, e uno solo dei due si puo' dedurre dall'altro.
    """
    return {"id": row["id"],
            "nome": clean_name(row.get("name_by_user") or row.get("name")),
            "nome_utente": clean_name(row.get("name_by_user")),
            "produttore": clean_name(row.get("manufacturer")),
            "modello": clean_name(row.get("model")),
            "area_id": row.get("area_id"),
            "disabilitato": 1 if row.get("disabled_by") else 0,
            "etichette": plain_list(row.get("labels"))}


def _label(row: dict) -> dict:
    return {"id": row["label_id"], "nome": clean_name(row.get("name")) or row["label_id"],
            "colore": row.get("color"), "icona": row.get("icon")}


def _category(row: dict) -> dict:
    """`ambito` lo mette `read_registries`: Home Assistant partiziona le
    categorie per ambito e non lo riporta nelle righe, quindi due categorie
    omonime in ambiti diversi sarebbero indistinguibili. Mai `None`: e' meta'
    dell'identita'."""
    return {"id": row["category_id"], "nome": clean_name(row.get("name")) or row["category_id"],
            "ambito": row.get("ambito") or ""}


def _integration(row: dict) -> dict:
    """Un'istanza di integrazione, col MOTIVO per cui non e' partita.

    `motivo` e' la risposta a «perche' la telecamera del giardino non
    risponde?». `origine` non descrive un guasto ma una decisione:
    `source: "ignore"` significa che il proprietario ha usato «ignora» sulla
    scoperta di quella integrazione.
    """
    return {"entry_id": row.get("entry_id"), "dominio": row.get("domain", ""),
            "titolo": clean_name(row.get("title")), "stato": row.get("state"),
            "motivo": clean_reason(row.get("reason")
                                   or row.get("error_reason_translation_key")),
            "origine": row.get("source")}


def _entity(row: dict, live_classes: dict, live_units: dict) -> dict:
    """Una riga del registro delle entita', come l'anagrafe la espone.

    `classe` e `unita` **non vengono dalla riga**: vengono dallo specchio vivo
    (`topology.actual_class`/`actual_unit`, che fanno vincere la viva). Sul
    campo e' l'unica fonte che esista per la classe -- vedi il docstring del
    modulo -- e per l'unita' e' quella che conta, perche' Home Assistant
    converte le unita' solo alla prima aggiunta del sensore.
    """
    entity_id = row["entity_id"]
    return {
        "id": entity_id,
        # Il nome scelto dall'utente vince su quello che l'integrazione ha
        # proposto: e' il primo posto in cui HIRIS deve chiamare le cose come
        # le chiama lui.
        "nome": clean_name(row.get("name") or row.get("original_name")),
        # I tre campi che la copia buttava. `translation_key` e' cio' che
        # l'integrazione dichiara di se' -- `energy_generating_today`, non
        # «Potenza autoconsumata» da indovinare -- ed e' la ragione per cui il
        # riconoscimento non era il problema. `original_name` accanto a `nome`
        # dice CHI ha chiamato cosi' questa cosa: l'integrazione o il
        # proprietario.
        "translation_key": row.get("translation_key"),
        "unique_id": row.get("unique_id"),
        "original_name": clean_name(row.get("original_name")),
        "area_id": row.get("area_id"),
        "dispositivo_id": row.get("device_id"),
        "piattaforma": row.get("platform"),
        "config_entry_id": row.get("config_entry_id"),
        # `categoria` (singolare) e' l'`entity_category` di Home Assistant --
        # `config` o `diagnostic`, deciso dall'INTEGRAZIONE -- e non c'entra
        # niente con `categorie` (plurale), la tassonomia dell'UTENTE.
        "categoria": row.get("entity_category"),
        "classe": actual_class(row.get("device_class") or row.get("original_device_class"),
                               live_classes.get(entity_id)),
        "unita": actual_unit(row.get("unit_of_measurement"), live_units.get(entity_id)),
        "disabilitata": 1 if row.get("disabled_by") else 0,
        "nascosta": 1 if row.get("hidden_by") else 0,
        "alias": clean_aliases(row.get("aliases")),
        "etichette": plain_list(row.get("labels")),
        "categorie": clean_categories(row.get("categories")),
    }


def build_home_space(registries: dict[str, list[dict]], *,
                     live_classes: dict[str, str] | None = None,
                     live_units: dict[str, str] | None = None) -> dict[str, list[dict]]:
    """L'anagrafe, costruita dai registri appena letti.

    `live_classes`/`live_units` sono le due mappe che `topology.live_mirror()`
    estrae gia' dallo specchio dello stato: si passano di qui invece di
    rileggere la cache, perche' la stessa domanda non deve avere due risposte
    a seconda della porta.
    """
    classes = live_classes or {}
    units = live_units or {}
    return {
        "piani": [_floor(p) for p in registries.get("piani", []) if p.get("floor_id")],
        "aree": [_area(a) for a in registries.get("aree", []) if a.get("area_id")],
        "dispositivi": [_device(d) for d in registries.get("dispositivi", []) if d.get("id")],
        "entita": [_entity(e, classes, units)
                   for e in registries.get("entita", []) if e.get("entity_id")],
        "etichette": [_label(e) for e in registries.get("etichette", []) if e.get("label_id")],
        "categorie": [_category(c) for c in registries.get("categorie", [])
                      if c.get("category_id")],
        "integrazioni": [_integration(i) for i in registries.get("integrazioni", [])],
    }
