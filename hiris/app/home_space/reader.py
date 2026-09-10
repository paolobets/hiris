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

from datetime import UTC, datetime

from ..proxy._sanitize import sanitize_ha_free_text, sanitize_ha_value
from .store import HomeSpaceStore
from .topology import actual_class, actual_unit

#: Le sette tabelle che l'anagrafe espone, sempre tutte e sette. Chi legge ci
#: conta -- `hierarchy()` cerca `dispositivi` per risolvere le aree ereditate --
#: e una chiave mancante non e' una lista vuota: e' un `KeyError`.
TABLES = ("piani", "aree", "dispositivi", "entita", "etichette", "categorie",
          "integrazioni")


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


class HomeSpace:
    """L'anagrafe viva: tiene l'ultima lettura e la serve dalla superficie che
    i suoi chiamanti gia' usano — `read()`, `reference_frame()`,
    `unavailable()`, `updated_at()`. Nessuno di loro cambia una riga.

    **Cosa si perde, ed e' una scelta dichiarata** (spec §4). Prima l'anagrafe
    sopravviveva ai riavvii su disco, e con Home Assistant irraggiungibile
    HIRIS rispondeva ancora sulla struttura leggendo l'ultima copia buona.
    Senza copia non risponde: `updated_at()` resta `None` finche' una lettura
    non riesce. Vale poco — con HA giu' non puo' ne' guardare ne' agire — ma e'
    una scelta, non una scoperta, ed e' per questo che `updated_at()` a `None`
    e una casa vuota **non si confondono**: chi legge deve poter distinguere
    «non l'ho ancora letta» da «non ha aree».

    **L'anagrafe che `read()` restituisce e' di sola lettura**: e' l'oggetto
    tenuto, non una copia — copiarne 1.229 righe a ogni lettura costerebbe a
    ogni richiesta cio' che la lettura intera dei registri costa una volta.
    Verificato il 10/09/2026 con una ricerca su tutto `hiris/app`: **nessun
    chiamante la modifica**, tutti i lettori (`hierarchy`, `queries`,
    `briefing`) costruiscono dizionari nuovi.

    **Il vecchio archivio resta qui dentro, e per una ragione sola**:
    `comportamento` e `plance` non vengono dai registri di Home Assistant
    (vengono da `automations.yaml`/`scripts.yaml` e dalle plance) e non sono
    ancora state portate dal vivo. Sono l'unica ragione per cui `casa.db`
    esiste ancora. **Questa delega muore con la Fetta 1-bis**, e con lei il
    file.
    """

    def __init__(self, db_path: str = "/data/casa.db") -> None:
        self._behavior = HomeSpaceStore(db_path)
        self._home_space: dict[str, list[dict]] = {}
        self._unavailable: list[str] = []
        # **L'unica cosa dell'anagrafe che sopravvive ai riavvii**, e non e'
        # un'eccezione arbitraria: il fuso e' la cornice in cui e' scritto il
        # NOSTRO archivio, non una copia di un fatto di HA. La riparazione
        # d'avvio gira prima che Home Assistant abbia risposto, e senza il fuso
        # attribuirebbe gli episodi notturni al giorno sbagliato -- vedi
        # `HomeSpaceStore.remember_reference_frame`.
        self._reference_frame: dict = self._behavior.reference_frame()
        self._updated_at: str | None = None

    def hold(self, home_space: dict[str, list[dict]],
             unavailable: list[str] | None = None,
             reference_frame: dict | None = None) -> None:
        """Prende in consegna l'anagrafe appena letta.

        `reference_frame` vuoto o assente **non cancella quello di prima**:
        il fuso di ieri e' ancora il fuso giusto, e un riferimento cancellato
        farebbe leggere ogni temperatura senza sapere in che scala.

        `unavailable` sono i registri che non hanno risposto: si conservano
        accanto ai dati perche' una casa senza piani e un registro dei piani
        caduto producono la stessa lista vuota.
        """
        self._home_space = {table: list(home_space.get(table, ())) for table in TABLES}
        self._unavailable = list(unavailable or [])
        if reference_frame:
            self._reference_frame = reference_frame
            self._behavior.remember_reference_frame(reference_frame)
        self._updated_at = datetime.now(UTC).isoformat(timespec="seconds")

    def hold_registries(self, registries: dict[str, list[dict]],
                        unavailable: list[str] | None = None,
                        reference_frame: dict | None = None, *,
                        live_classes: dict[str, str] | None = None,
                        live_units: dict[str, str] | None = None) -> None:
        """Costruisce l'anagrafe dai registri appena letti e la prende in
        consegna. **E' l'unica porta**: la ricostruzione vera e ogni prova
        passano di qui, quindi una finta non puo' seminare una casa che il
        lettore non saprebbe produrre.
        """
        self.hold(build_home_space(registries, live_classes=live_classes,
                                   live_units=live_units),
                  unavailable, reference_frame)

    def read(self) -> dict[str, list[dict]]:
        """L'anagrafe intera. `{}` finche' nessuna lettura e' riuscita."""
        return self._home_space

    def updated_at(self) -> str | None:
        return self._updated_at

    def reference_frame(self) -> dict:
        return self._reference_frame

    def unavailable(self) -> list[str]:
        return list(self._unavailable)

    def close(self) -> None:
        self._behavior.close()

    # -- Il comportamento e le plance: delega pura, in uscita con la Fetta 1-bis.
    def replace_behavior(self, *args, **kwargs):
        return self._behavior.replace_behavior(*args, **kwargs)

    def behavior(self):
        return self._behavior.behavior()

    def behavior_loaded_at(self):
        return self._behavior.behavior_loaded_at()

    def behavior_problems(self):
        return self._behavior.behavior_problems()

    def unloaded_files(self):
        return self._behavior.unloaded_files()

    def replace_dashboards(self, *args, **kwargs):
        return self._behavior.replace_dashboards(*args, **kwargs)

    def dashboards(self):
        return self._behavior.dashboards()

    def dashboards_loaded_at(self):
        return self._behavior.dashboards_loaded_at()

    def unavailable_dashboards(self):
        return self._behavior.unavailable_dashboards()
