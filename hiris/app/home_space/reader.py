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

import json
import logging
import os
from datetime import UTC, datetime

from ..proxy._sanitize import sanitize_ha_free_text, sanitize_ha_value
from .topology import actual_class, actual_unit

#: Le sette tabelle che l'anagrafe espone, sempre tutte e sette. Chi legge ci
#: conta -- `hierarchy()` cerca `dispositivi` per risolvere le aree ereditate --
#: e una chiave mancante non e' una lista vuota: e' un `KeyError`.
TABLES = ("piani", "aree", "dispositivi", "entita", "etichette", "categorie",
          "integrazioni")

logger = logging.getLogger(__name__)

#: Il sistema di riferimento della casa e' l'unica cosa che sopravvive ai
#: riavvii, e sta in un file suo invece che in un archivio: e' un dizionario di
#: sei campi che si scrive tutto insieme, e per quello SQLite era un motore
#: acceso per niente. Il nome e' inglese perche' e' un file nuovo (regola del
#: 04/09/2026); il suo contenuto parla la lingua dell'anagrafe, come sempre.
REFERENCE_FRAME_FILE = "reference_frame.json"


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

    def __init__(self, data_dir: str = "/data") -> None:
        self._frame_path = os.path.join(data_dir, REFERENCE_FRAME_FILE)
        self._home_space: dict[str, list[dict]] = {}
        self._unavailable: list[str] = []
        # **L'unica cosa dell'anagrafe che sopravvive ai riavvii**, e non e'
        # un'eccezione arbitraria: il fuso e' la cornice in cui e' scritto il
        # NOSTRO archivio, non una copia di un fatto di HA. La riparazione
        # d'avvio gira prima che Home Assistant abbia risposto, e senza il fuso
        # attribuirebbe gli episodi notturni al giorno sbagliato -- vedi
        # `HomeSpaceStore.remember_reference_frame`.
        self._reference_frame: dict = self._read_reference_frame()
        self._updated_at: str | None = None
        self._behavior_entries: list[dict] = []
        self._behavior_problems: list[str] = []
        self._unread_bodies: dict[str, str] = {}
        self._behavior_loaded_at: str | None = None
        self._dashboard_entries: list[dict] = []
        self._unavailable_dashboards: list[str] = []
        self._dashboards_loaded_at: str | None = None

    def _read_reference_frame(self) -> dict:
        """La cornice, dal file suo. `{}` se non c'e' o non si legge: chi legge
        deve poter fare `.get("fuso")` senza sapere prima se c'e' mai stata una
        lettura, e il «non lo so» si dichiara con la chiave che manca."""
        try:
            with open(self._frame_path, encoding="utf-8") as f:
                value = json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as error:
            logger.warning("sistema di riferimento non letto (%s: %s)",
                           type(error).__name__, error)
            return {}
        return value if isinstance(value, dict) else {}

    def _write_reference_frame(self, frame: dict) -> None:
        """Scrive la cornice, e **solo quella**.

        E' l'unica cosa dell'anagrafe che sopravvive ai riavvii, e non e'
        un'eccezione arbitraria: il fuso non e' la copia di un fatto di Home
        Assistant, e' **la cornice in cui e' scritto il nostro archivio**. I
        22 giorni di grezzo sono istanti; senza il fuso non si sanno nemmeno
        dividere in giorni.

        Si scrive di fianco e si sposta: un riavvio a meta' scrittura
        lascerebbe altrimenti un file troncato, e un fuso illeggibile e' peggio
        di un fuso vecchio.
        """
        temporary = self._frame_path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(frame, f, ensure_ascii=False)
            os.replace(temporary, self._frame_path)
        except Exception as error:
            logger.warning("sistema di riferimento non scritto (%s: %s)",
                           type(error).__name__, error)

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
            self._write_reference_frame(reference_frame)
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

    # -- Il comportamento: tenuto a memoria come l'anagrafe, dal 10/09/2026.
    def hold_behavior(self, entries: list[dict], *, problems: list[str] | None = None,
                      unread_bodies: dict[str, str] | None = None) -> None:
        """Prende in consegna il comportamento appena letto da Home Assistant.

        **`unread_bodies` sostituisce `file_non_letti`, e non e' una
        rinomina.** Quello mappava il NOME DI UN FILE alla ragione per cui non
        si era letto; questo mappa l'ENTITA' alla ragione per cui non se ne
        conosce il corpo -- e sono la stessa domanda («cosa mi sta
        sfuggendo?») posta alla fonte giusta. Con la lettura dal vivo un file
        non c'e' piu': quello che puo' mancare e' il corpo di una singola
        automazione, e adesso si sa **quale**.

        Da qui viene anche `senza_corpo`, che prima era un conteggio a parte
        ricavato dai corpi nulli: due campi per un fatto solo sono due campi
        che possono divergere.
        """
        self._behavior_entries = list(entries)
        self._behavior_problems = list(problems or [])
        self._unread_bodies = dict(unread_bodies or {})
        self._behavior_loaded_at = datetime.now(UTC).isoformat(timespec="seconds")

    def behavior(self) -> list[dict]:
        return self._behavior_entries

    def behavior_loaded_at(self) -> str | None:
        return self._behavior_loaded_at

    def behavior_problems(self) -> list[str]:
        return list(self._behavior_problems)

    def unread_bodies(self) -> dict[str, str]:
        """Le entita' di cui HIRIS non conosce il corpo, e **perche'**.

        E' la dichiarazione di punto cieco che il prodotto fa al modello: chi
        cerca un'automazione per nome deve poter sapere che cio' che quella
        automazione FA potrebbe esistere senza essere cercabile adesso.
        """
        return dict(self._unread_bodies)

    # -- Le plance: gia' lette dal vivo (`behavior.reread_dashboards`), da
    # oggi anche tenute a memoria come l'anagrafe e il comportamento.
    def hold_dashboards(self, entries: list[dict],
                        unavailable: list[str] | None = None) -> None:
        self._dashboard_entries = list(entries)
        self._unavailable_dashboards = list(unavailable or [])
        self._dashboards_loaded_at = datetime.now(UTC).isoformat(timespec="seconds")

    def dashboards(self) -> list[dict]:
        return self._dashboard_entries

    def dashboards_loaded_at(self) -> str | None:
        return self._dashboards_loaded_at

    def unavailable_dashboards(self) -> list[str]:
        return list(self._unavailable_dashboards)

    def close(self) -> None:
        """Non c'e' piu' niente da chiudere: l'anagrafe, il comportamento e le
        plance vivono in memoria, e la cornice e' un file che si apre e si
        chiude a ogni scrittura. Il metodo resta perche' i suoi chiamanti sono
        decine e non hanno nessuna ragione di sapere che l'archivio sotto non
        c'e' piu'."""
