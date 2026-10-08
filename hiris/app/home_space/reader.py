"""Il lettore: i registri di Home Assistant diventano l'anagrafe, **senza una
copia in mezzo**.

L'anagrafe e' un dizionario di tabelle (`TABLES`). Chi la legge --
`queries.view`, `topology.hierarchy`, `briefing.compose()` -- sono funzioni
sopra quel dizionario: questo modulo ne e' il fornitore.

**Perche' senza copia.** Una copia su disco buttava via cio' che Home
Assistant dichiara:
`translation_key`, `unique_id`, `original_name`. E soprattutto **non poteva
tenere la classe**: `config/entity_registry/list` risponde con
`RegistryEntry.as_partial_dict` (`helpers/entity_registry.py`), che
`device_class` non ce l'ha — misurato il 10/09/2026 sulla casa vera,
**assente su 1.227 righe su 1.227**, e `classe` NULL su **1.229 entita' su
1.229** nell'anagrafe pubblicata. Ogni lettore che decideva su quel campo era
inerte in produzione, e la piu' costosa di quelle inerzie e' stato il bilancio
dell'energia: zero oggetti in cinque giorni su cinque.

**Il confine di sanificazione e' la costruzione.** Si sanifica qui, mentre
l'anagrafe si costruisce, cosi' che ogni lettore erediti la difesa senza
ripeterla (C-2, `proxy/_sanitize.py`): un posto solo.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

from ..proxy._sanitize import sanitize_ha_free_text, sanitize_ha_value
from ..storage import write_json_atomic
from .behavior import automation_active
from .topology import clean_text

#: Le sette tabelle che l'anagrafe espone, sempre tutte e sette. Chi legge ci
#: conta -- `hierarchy()` cerca `dispositivi` per risolvere le aree ereditate --
#: e una chiave mancante non e' una lista vuota: e' un `KeyError`.
TABLES = ("piani", "aree", "dispositivi", "entita", "etichette", "categorie",
          "integrazioni")

logger = logging.getLogger(__name__)

#: Il sistema di riferimento della casa e' l'unica cosa che sopravvive ai
#: riavvii, e sta in un file suo invece che in un archivio: e' un dizionario di
#: pochi campi che si scrive tutto insieme, e per quello SQLite sarebbe un
#: motore acceso per niente. Il nome e' inglese perche' e' un file nuovo (regola
#: del 04/09/2026); il suo contenuto parla la lingua dell'anagrafe, come sempre.
REFERENCE_FRAME_FILE = "reference_frame.json"


def clean_name(value):
    """Un nome/alias/titolo destinato all'anagrafe, sanificato al confine.

    C-2 (L1-sicurezza.md): un nome/alias/titolo e' testo che HIRIS non
    controlla (un dispositivo di rete ostile, un'integrazione compromessa, un
    ospite che rinomina qualcosa). Sanificare QUI, e non a valle, significa
    che ogni lettore dell'anagrafe (il nucleo, `search`, la pagina)
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
            "livello": row.get("level")}


def _area(row: dict) -> dict:
    """Un'area, con le due entita' che l'utente le ha dichiarato addosso.

    `temperature_entity_id`/`humidity_entity_id` dicono QUALE entita' e' la
    temperatura di quella stanza. Senza di esse HIRIS dovrebbe indovinare fra
    tutti i sensori dell'area quale intende chi chiede se fa caldo in
    soggiorno: e' il significato piu' dichiarato che esista, e costa zero
    chiamate.
    """
    return {"id": row["area_id"], "nome": clean_name(row.get("name")) or row["area_id"],
            "piano_id": row.get("floor_id"),
            "alias": clean_aliases(row.get("aliases")),
            "etichette": plain_list(row.get("labels")),
            "entita_temperatura": row.get("temperature_entity_id"),
            "entita_umidita": row.get("humidity_entity_id")}


def _device(row: dict) -> dict:
    """Un dispositivo, **come oggetto e non come identificatore opaco**.

    `nome` e' il nome da usare: quello scelto dall'utente se c'e', altrimenti
    quello proposto dall'integrazione.
    """
    return {"id": row["id"],
            "nome": clean_name(row.get("name_by_user") or row.get("name")),
            "produttore": clean_name(row.get("manufacturer")),
            "modello": clean_name(row.get("model")),
            "area_id": row.get("area_id"),
            "disabilitato": 1 if row.get("disabled_by") else 0,
            # CHI l'ha spento, col valore di Home Assistant (Tappa 3, Task 8,
            # 04/10/2026): `DeviceEntryDisabler` -- `user`, `integration`,
            # `config_entry`, `device` (`helpers/device_registry.py`, tag
            # 2026.9.4). Un'entita' spenta con `disabled_by: device` eredita
            # da qui la sua causa (`House.source`).
            "disabilitato_da": row.get("disabled_by") or None,
            "etichette": plain_list(row.get("labels"))}


def _label(row: dict) -> dict:
    return {"id": row["label_id"], "nome": clean_name(row.get("name")) or row["label_id"]}


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
            "origine": row.get("source"),
            # CHI l'ha spenta (Tappa 3, Task 8, 04/10/2026; B-25): fino a quel
            # giorno il lettore lo buttava. `ConfigEntryDisabler` ha un valore
            # solo, `user` (`config_entries.py`, tag 2026.9.4): un'istanza la
            # spegne solo il proprietario, e le sue entita' ricevono
            # `disabled_by: config_entry` -- la causa vera e' questa.
            "disabilitata_da": row.get("disabled_by") or None}


def _entity(row: dict) -> dict:
    """Una riga del registro delle entita', come l'anagrafe la espone.

    `classe` e `unita` sono **cio' che il registro dichiara**, e nient'altro
    (B-17, Tappa 3, Task 7, 04/10/2026). Fino a quel giorno l'anagrafe ci
    scriveva quelle dello specchio vivo AL MOMENTO della ricostruzione, e le
    teneva ferme fino alla ricostruzione dopo: un'unita' cambiata in Home
    Assistant arrivava all'osservatore e alle ricette solo dopo un evento di
    registro. La classe e l'unita' DI ADESSO le dice `House.kind_of`, che
    compone questa dichiarazione con lo specchio (`topology.live_first`, la
    viva vince). Il registro la classe quasi non la manda -- vedi il
    docstring del modulo -- e l'unita' la porta solo se l'utente l'ha forzata.
    """
    entity_id = row["entity_id"]
    return {
        "id": entity_id,
        # Il nome scelto dall'utente vince su quello che l'integrazione ha
        # proposto: e' il primo posto in cui HIRIS deve chiamare le cose come
        # le chiama lui.
        "nome": clean_name(row.get("name") or row.get("original_name")),
        # `translation_key` e' cio' che l'integrazione dichiara di se' --
        # `energy_generating_today`, non «Potenza autoconsumata» da
        # indovinare. `original_name` accanto a `nome`
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
        "classe": clean_text(row.get("device_class") or row.get("original_device_class")),
        "unita": clean_text(row.get("unit_of_measurement")),
        "disabilitata": 1 if row.get("disabled_by") else 0,
        "nascosta": 1 if row.get("hidden_by") else 0,
        # CHI l'ha spenta o nascosta, col valore di Home Assistant (Tappa 3,
        # Task 5, 04/10/2026): `user`, `integration`, `config_entry`,
        # `device`, `hass` per `disabled_by`; `user`, `integration` per
        # `hidden_by` (`RegistryEntryDisabler`/`RegistryEntryHider`, letti in
        # `helpers/entity_registry.py`). Fino a quel giorno il lettore riduceva
        # tutto a 1/0, e «spenta dal proprietario» e «spenta dall'integrazione»
        # non si distinguevano piu' in nessun punto. E' la causa che
        # `topology.visibility` porta accanto alla classe. I due booleani
        # restano finche' la Tappa 4 non decide la resa: `GET /api/home-space`
        # li espone, e toglierli e' un cambio di forma.
        "disabilitata_da": row.get("disabled_by") or None,
        "nascosta_da": row.get("hidden_by") or None,
        "alias": clean_aliases(row.get("aliases")),
        "etichette": plain_list(row.get("labels")),
        "categorie": clean_categories(row.get("categories")),
    }


def build_home_space(registries: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """L'anagrafe, costruita dai registri appena letti: solo da loro. Lo
    specchio dello stato non entra (B-17): cio' che e' vivo si chiede vivo,
    a `House`."""
    return {
        "piani": [_floor(p) for p in registries.get("piani", []) if p.get("floor_id")],
        "aree": [_area(a) for a in registries.get("aree", []) if a.get("area_id")],
        "dispositivi": [_device(d) for d in registries.get("dispositivi", []) if d.get("id")],
        "entita": [_entity(e)
                   for e in registries.get("entita", []) if e.get("entity_id")],
        "etichette": [_label(e) for e in registries.get("etichette", []) if e.get("label_id")],
        "categorie": [_category(c) for c in registries.get("categorie", [])
                      if c.get("category_id")],
        "integrazioni": [_integration(i) for i in registries.get("integrazioni", [])],
    }


def _carried_over(built: dict[str, list[dict]], previous: dict[str, list[dict]],
                  unavailable: list[str]) -> dict[str, list[dict]]:
    """L'anagrafe appena costruita, con le tabelle dei registri che non hanno
    risposto riprese da quella di prima (A-10).

    I nomi sono quelli di `HAClient.read_registries` e di `topology.rebuild`:
    una tabella intera (`aree`), gli alias delle entita' (`entita:alias`, il
    secondo giro `get_entries`), un ambito delle categorie
    (`categorie:script`). Gli altri (`sistema_di_riferimento`)
    non sono tabelle e non si toccano. Le righe
    riprese sono gia' nella forma dell'anagrafe: nessuna seconda costruzione.
    """
    result = dict(built)
    for name in unavailable:
        table, _, part = name.partition(":")
        if table not in TABLES or table not in previous:
            continue
        if not part:
            result[table] = list(previous[table])
        elif table == "entita" and part == "alias":
            known = {row["id"]: row.get("alias") for row in previous["entita"]}
            result["entita"] = [
                {**row, "alias": known[row["id"]]} if not row.get("alias") and known.get(row["id"])
                else row
                for row in result["entita"]]
        elif table == "categorie":
            result["categorie"] = list(result["categorie"]) + [
                row for row in previous["categorie"] if row.get("ambito") == part]
    return result


class HomeSpace:
    """L'anagrafe viva: tiene l'ultima lettura e la serve — `read()`,
    `reference_frame()`, `unavailable()`, `updated_at()`.

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

    Il comportamento e le plance si tengono allo stesso modo, in memoria
    (`hold_behavior`, `hold_dashboards`).
    """

    def __init__(self, data_dir: str, *, mirror=None) -> None:
        # Lo specchio dello stato: `behavior()` gli chiede se un'automazione
        # e' attiva al momento della lettura (A-12). Senza specchio la voce
        # non lo dice: e' un «non lo so», non un «spenta».
        self._mirror = mirror
        self._frame_path = os.path.join(data_dir, REFERENCE_FRAME_FILE)
        self._home_space: dict[str, list[dict]] = {}
        self._unavailable: list[str] = []
        self._unavailable_since: dict[str, str | None] = {}
        # **L'unica cosa dell'anagrafe che sopravvive ai riavvii**, e non e'
        # un'eccezione arbitraria: il fuso e' la cornice in cui e' scritto il
        # NOSTRO archivio, non una copia di un fatto di HA. La riparazione
        # d'avvio gira prima che Home Assistant abbia risposto, e senza il fuso
        # attribuirebbe gli episodi notturni al giorno sbagliato -- vedi
        # `_write_reference_frame`.
        self._reference_frame: dict = self._read_reference_frame()
        self._updated_at: str | None = None
        self._behavior_entries: list[dict] = []
        self._behavior_problems: list[str] = []
        self._unread_bodies: dict[str, str] = {}
        self._behavior_loaded_at: str | None = None
        # Il segno della replica conservata (G-16, Tappa 8): la ragione per
        # cui l'ultima rilettura NON ha sostituito cio' che si tiene. `None`
        # quando la replica e' quella dell'ultima rilettura.
        self._behavior_kept: str | None = None
        self._dashboard_entries: list[dict] = []
        self._unavailable_dashboards: list[str] = []
        self._dashboards_loaded_at: str | None = None
        self._dashboards_kept: str | None = None
        # La dashboard Energia (`home_space/energy.py`): letta alla prima
        # domanda dopo ogni ricostruzione, non a ogni domanda.
        self._energy: dict | None = None
        self._energy_current = False

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
        Assistant, e' **la cornice in cui e' scritto il nostro archivio**. Il
        grezzo e' fatto di istanti; senza il fuso non si sanno nemmeno
        dividere in giorni.

        Si scrive con `storage.write_json_atomic`: un riavvio a meta' scrittura
        lascerebbe altrimenti un file troncato, e un fuso illeggibile e' peggio
        di un fuso vecchio.
        """
        try:
            write_json_atomic(self._frame_path, frame)
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
        # Chi prende in consegna da qui non porta copie: un registro caduto e'
        # una tabella vuota, senza eta'. Le copie con la loro eta' le scrive
        # `hold_registries`, che sola le fa.
        self._unavailable_since = {name: None for name in self._unavailable}
        if reference_frame:
            self._reference_frame = reference_frame
            self._write_reference_frame(reference_frame)
        self._updated_at = datetime.now(UTC).isoformat(timespec="seconds")
        # Un giro nuovo dell'anagrafe: la dashboard Energia si rilegge alla
        # prossima domanda (`energy.energy_dashboard`).
        self._energy_current = False

    def hold_registries(self, registries: dict[str, list[dict]],
                        unavailable: list[str] | None = None,
                        reference_frame: dict | None = None) -> None:
        """Costruisce l'anagrafe dai registri appena letti e la prende in
        consegna. **E' l'unica porta**: la ricostruzione vera e ogni prova
        passano di qui, quindi una finta non puo' seminare una casa che il
        lettore non saprebbe produrre.

        **Un registro caduto non svuota la sua tabella** (A-10, Task 7 della
        Tappa 2, 03/10/2026): si tiene cio' che la ricostruzione precedente
        sapeva (`_carried_over`), e il nome resta in `unavailable` -- la
        tabella e' marcata come non riletta, e chi la dichiara incompleta
        continua a farlo. Fino a quel giorno un `get_entries` caduto toglieva
        dall'anagrafe TUTTI gli alias, e la ricerca smetteva di trovare cio'
        che il proprietario aveva chiamato a modo suo, per un comando fallito.
        """
        built = build_home_space(registries)
        previous_read, previous_since = self._updated_at, self._unavailable_since
        if previous_read is not None:
            built = _carried_over(built, self._home_space, unavailable or [])
        self.hold(built, unavailable, reference_frame)
        # **La copia porta il suo istante** (S-36, Tappa 8, Task 1,
        # 08/10/2026): l'ultima ricostruzione in cui quel registro ha
        # risposto. Caduto anche allora, resta l'istante di prima; mai letto,
        # `None`. Fino a quel giorno `unavailable` diceva «non riletta» e
        # taceva da quando: una copia di un'ora fa e una di tre giorni fa
        # erano la stessa riga.
        self._unavailable_since = {
            name: previous_since.get(name, previous_read)
            for name in self._unavailable}

    def hold_integrations(self, rows: list[dict]) -> None:
        """Le integrazioni appena annunciate da Home Assistant, al posto di
        quelle dell'ultima ricostruzione (A-11, 03/10/2026; dal Task 7 della
        Tappa 2 le annuncia l'iscrizione `config_entries/subscribe`, vedi
        `server.integration_follower`).

        **Perche'.** L'anagrafe si ricostruisce sugli eventi dei registri, e lo
        stato di un'integrazione (`loaded`, `setup_error`, `not_loaded`...)
        restava quello letto all'ultima ricostruzione: un'integrazione che
        smette di partire puo' non far nascere nessun evento di registro.
        L'iscrizione annuncia ogni cambio di stato di una voce: arriva qui, e
        il nucleo lo dice subito.

        Le righe passano dallo stesso costruttore della ricostruzione
        (`_integration`): stessa forma da tutte e due le porte. Una tabella
        nuova, non una modifica di quella tenuta: chi ha gia' letto l'anagrafe
        tiene la sua (vedi il docstring della classe, «di sola lettura»).

        **Un'anagrafe mai letta non nasce da qui**: senza le altre sei tabelle
        sarebbe una casa fatta di sole integrazioni, che i lettori leggerebbero
        come una casa vuota. La prima ricostruzione le legge da se'.
        """
        if self._updated_at is None:
            return
        self._home_space = {**self._home_space,
                            "integrazioni": [_integration(row) for row in rows]}
        self._unavailable = [name for name in self._unavailable if name != "integrazioni"]
        self._unavailable_since.pop("integrazioni", None)

    def read(self) -> dict[str, list[dict]]:
        """L'anagrafe intera. `{}` finche' nessuna lettura e' riuscita."""
        return self._home_space

    def updated_at(self) -> str | None:
        return self._updated_at

    def reference_frame(self) -> dict:
        return self._reference_frame

    def unavailable(self) -> list[str]:
        return list(self._unavailable)

    def unavailable_since(self) -> dict[str, str | None]:
        """Per ogni registro di `unavailable`, l'istante (ISO, UTC) della
        copia che l'anagrafe tiene al suo posto (`_carried_over`): l'ultima
        ricostruzione in cui aveva risposto. `None` se non ha mai risposto, e
        la tabella e' vuota. Vedi `hold_registries` (S-36)."""
        return dict(self._unavailable_since)

    # -- Il comportamento: tenuto a memoria come l'anagrafe, dal 10/09/2026.
    def hold_behavior(self, entries: list[dict], *, problems: list[str] | None = None,
                      unread_bodies: dict[str, str] | None = None) -> None:
        """Prende in consegna il comportamento appena letto da Home Assistant.

        `unread_bodies` mappa l'ENTITA' alla ragione per cui non se ne
        conosce il corpo: con la lettura dal vivo quello che puo' mancare e'
        il corpo di una singola automazione, e cosi' si sa **quale**.
        """
        self._behavior_entries = list(entries)
        self._behavior_problems = list(problems or [])
        self._unread_bodies = dict(unread_bodies or {})
        self._behavior_loaded_at = datetime.now(UTC).isoformat(timespec="seconds")
        self._behavior_kept = None

    def keep_behavior(self, reason: str) -> None:
        """La rilettura del comportamento NON ha sostituito la replica, e
        `reason` dice perche' (`behavior.reread`, le sue due guardie). Fino
        alla Tappa 8 (G-16) lo diceva solo il log, e il nucleo presentava la
        replica come se fosse fresca. Il segno resta finche' una rilettura
        buona non consegna (`hold_behavior`)."""
        self._behavior_kept = reason

    def behavior_kept(self) -> dict | None:
        """La replica conservata, come oggetto che si legge da solo: perche'
        (`motivo`) e di quando e' la replica che si tiene (`letto_il`, `None`
        se non si e' mai letta). `None` quando la replica e' quella
        dell'ultima rilettura."""
        if self._behavior_kept is None:
            return None
        return {"motivo": self._behavior_kept, "letto_il": self._behavior_loaded_at}

    def behavior(self) -> list[dict]:
        """Le voci del comportamento, con `attiva` e `nome` chiesti allo
        specchio ADESSO (A-12): la voce tenuta porta il corpo letto alla
        rilettura; lo stato e il nome hanno una casa sola, lo specchio, e una
        loro copia qui invecchierebbe fino a cinque minuti -- un'automazione
        spenta o rinominata in Home Assistant restava accesa, o col nome
        vecchio, fino alla rilettura.

        Senza la riga nello specchio (la voce e' sparita fra due riletture,
        o lo specchio non c'e') la voce resta quella letta: `attiva` manca, e
        il nome e' l'ultimo visto. Un «non lo so» non diventa «senza nome».
        Il nome dello specchio e' il `friendly_name` gia' sanificato al
        confine (`_to_minimal`); la stringa vuota e' «senza nome», `None`,
        come alla rilettura."""
        result = []
        for entry in self._behavior_entries:
            row = self._mirror.get(entry["id"]) if self._mirror is not None else None
            if row is None:
                result.append(entry)
                continue
            live = {**entry, "nome": row.get("name") or None}
            active = automation_active(entry["id"], row)
            if active is not None:
                live["attiva"] = active
            result.append(live)
        return result

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

    # -- Le plance: lette dal vivo (`behavior.reread_dashboards`) e tenute a
    # memoria come l'anagrafe e il comportamento.
    def hold_dashboards(self, entries: list[dict],
                        unavailable: list[str] | None = None) -> None:
        self._dashboard_entries = list(entries)
        self._unavailable_dashboards = list(unavailable or [])
        self._dashboards_loaded_at = datetime.now(UTC).isoformat(timespec="seconds")
        self._dashboards_kept = None

    def keep_dashboards(self, reason: str, unavailable: list[str] | None = None) -> None:
        """La rilettura delle plance NON ha sostituito la replica
        (`behavior.reread_dashboards`): il segno, come `keep_behavior`. I non
        disponibili sono quelli della lettura di ADESSO: fino alla Tappa 8
        restavano quelli della replica, e dicevano «tutto leggibile» proprio
        mentre niente lo era."""
        self._dashboards_kept = reason
        self._unavailable_dashboards = list(unavailable or [])

    def dashboards_kept(self) -> dict | None:
        """La replica conservata delle plance, nella forma di
        `behavior_kept`."""
        if self._dashboards_kept is None:
            return None
        return {"motivo": self._dashboards_kept, "letto_il": self._dashboards_loaded_at}

    def dashboards(self) -> list[dict]:
        return self._dashboard_entries

    def dashboards_loaded_at(self) -> str | None:
        return self._dashboards_loaded_at

    def unavailable_dashboards(self) -> list[str]:
        return list(self._unavailable_dashboards)

    # -- La dashboard Energia (`home_space/energy.py`, piano degli attori,
    # Task 2.2): un oggetto della casa suo, tenuto come le plance.
    def hold_energy(self, roles: list[dict] | None) -> None:
        """Prende in consegna i ruoli appena letti (`energy.declared_roles`);
        `None` e' una casa che una dashboard Energia non l'ha (`not_found`):
        «nessuna dashboard dichiarata», che non e' «non l'ho letta»."""
        self._energy = {"ruoli": list(roles or []), "dichiarata": roles is not None,
                        "letta_alle": datetime.now(UTC).isoformat(timespec="seconds")}
        self._energy_current = True

    def energy(self) -> dict | None:
        """L'ultima dashboard tenuta, o `None` se nessuna lettura e' riuscita."""
        return self._energy

    def energy_current(self) -> bool:
        """Se la dashboard tenuta e' stata letta in questo giro dell'anagrafe."""
        return self._energy_current

    def close(self) -> None:
        """Non c'e' niente da chiudere: l'anagrafe, il comportamento e le
        plance vivono in memoria, e la cornice e' un file che si apre e si
        chiude a ogni scrittura. Il metodo resta per chi lo chiama alla
        chiusura (`server.py`, le prove)."""
