"""L'istantanea della casa: anagrafe e specchio, letti UNA volta per turno
(R18; Tappa 3, Task 4, 04/10/2026).

**Il punto di giunzione** fra l'anagrafe (i registri: `HomeSpace.read()`) e
lo specchio (gli stati: `topology.read_mirror`). Fino a quel giorno ogni
porta se li rifaceva da se': misurato sulla casa sintetica, un turno di
chat col nucleo, tre `search` e una `history` costruiva la gerarchia dieci
volte e lo specchio cinque (`tests/test_casa_per_turno.py`). Una `search`
per nome ne costruiva tre (entita', aree, dispositivi), quattro se trovava
un'area.

**Vale un turno, o un giro di un attore, e basta.** Non si tiene mai in
`app[...]` e non passa al turno dopo: una casa vecchia di un turno e' il
difetto che R12 vieta (nessuna copia invecchia in silenzio). Chi la tiene
per un turno -- `ToolDispatcher`, che nasce a ogni turno -- la butta quando
la casa cambia sotto di lui: l'anagrafe ricostruita (un altro oggetto da
`HomeSpace.read()`), o un suo comando eseguito (vedi `ToolDispatcher`).

I metodi del §4.1 della spec arrivano un task alla volta: qui ci sono la
gerarchia, la scelta di «di chi» (`select`, l'ex `house_query.select_subjects`),
la VISIBILITA' con la causa (`visibility`) e l'IDENTITA' (`name`), dal Task 5, e
il dove (`where`), dal Task 6; il tipo (`kind_of`, `has_statistics`), dal
Task 7; cio' che gli attori compongono (`visible_entities`, `entities_of`,
`device_entities`, `device_ids`, `entity_ids`), dal Task 12; lo STATO e la
SALUTE della fonte (`source`), dal Task 8. Le regole stanno
in `topology` (`visibility`, `live_name`, `device_name`), che sta SOTTO questo
modulo: la gerarchia le applica e non puo' importare la casa.
"""
from __future__ import annotations

from dataclasses import replace

from ..memory.resolver import Lookup, costruisci_indice
from ..proxy.entity_cache import disclosable_attributes
from . import topology
from .ha_vocabulary import (
    CONFIG_ENTRY_LOADED,
    ENTITY_DISABLED_BY_CONFIG_ENTRY,
    ENTITY_DISABLED_BY_DEVICE,
    ENTITY_DISABLED_BY_USER,
    RESTORED_ATTRIBUTE,
    domain_of,
    has_statistics,
)
from .house_query import (
    _BEHAVIOR_KINDS,
    HouseFilters,
    Selection,
    _behavior_matches,
    _entity_matches,
)
from .topology import Mirror, read_mirror
from .type_vocabulary import STATE_UNAVAILABLE, STATE_UNKNOWN

#: La chiave di `escluse` per ogni classe del fuori (`topology.visibility`).
_EXCLUDED_KEY = {"disabilitata": "disabilitate", "nascosta": "nascoste",
                 "servizio": "servizio"}

#: Tre dei sette stati di `House.source` (D6), con un nome: quelli in cui
#: Home Assistant **non parla piu'** dell'entita' -- spenta (dal proprietario
#: o da Home Assistant) o sparita dagli stati. Le altre quattro parlano
#: ancora, o possono tornare a farlo da sole: `viva`, `senza_valore`,
#: `non_disponibile` (un riavvio la fa passare di li') e `integrazione_ferma`
#: (un'istanza che ritenta).
SOURCE_SWITCHED_OFF_BY_OWNER = "spenta_dal_proprietario"
SOURCE_SWITCHED_OFF_BY_HA = "spenta_da_home_assistant"
SOURCE_GONE = "sparita"
#: Chi chiede «questa fonte e' finita?» chiede questo insieme (la cronaca,
#: `mind/facts.build_episodes`, Task 1.4 degli attori, 05/10/2026): un
#: episodio di una fonte cosi' non restera' aperto aspettando una riga che
#: Home Assistant non scrivera' mai.
ENDED_SOURCE_STATES = frozenset({SOURCE_SWITCHED_OFF_BY_OWNER, SOURCE_SWITCHED_OFF_BY_HA,
                                 SOURCE_GONE})
#: Lo stato di una fonte che parla (`House.source`).
SOURCE_LIVE = "viva"
#: I SETTE stati della fonte (D6 del proprietario, 03/10/2026; Tappa 3, Task
#: 8), nell'ordine del docstring di `House.source`, che dice cosa vuol dire
#: ognuno. E' il vocabolario che le cause delle misure riusano (attori, Task
#: 1.2, B-26: `mind.operations.CAUSES`): una causa di misura che dica lo
#: stato della fonte con un'altra parola sarebbe una seconda copia. Che
#: `source` non ne produca altri lo prova `tests/test_fonte_della_casa.py`.
SOURCE_STATES = (SOURCE_LIVE, SOURCE_SWITCHED_OFF_BY_OWNER, SOURCE_SWITCHED_OFF_BY_HA,
                 "integrazione_ferma", "non_disponibile", "senza_valore", SOURCE_GONE)


class House:
    """L'anagrafe, lo specchio e i registri caduti di UN momento, con la
    gerarchia calcolata alla prima richiesta e tenuta.

    `home_space` e' l'oggetto che `HomeSpace.read()` ha restituito (non una
    copia: il lettore lo dichiara di sola lettura, e il dispatcher lo
    confronta per identita' per sapere se l'anagrafe e' stata ricostruita).
    """

    def __init__(self, home_space: dict, mirror: Mirror,
                 unavailable: tuple[str, ...] = (),
                 statistic_ids: frozenset[str] | set[str] | None = None) -> None:
        self.home_space = home_space
        self.mirror = mirror
        self.unavailable = tuple(unavailable)
        # Le entita' per cui Home Assistant tiene statistiche, lette dal giro
        # (`server.statistic_ids_for_round`); `None` = non lette (B-12).
        self.statistic_ids = None if statistic_ids is None else frozenset(statistic_ids)
        self._floors: list[dict] | None = None
        self._places: dict[str, tuple[dict, dict, dict]] | None = None
        self._device_index: dict[str, dict] | None = None
        self._entities: dict[str, dict] | None = None
        self._visible: list[str] | None = None
        self._by_device: dict[str, list[dict]] | None = None
        self._visible_set: frozenset[str] | None = None
        self._lookup: Lookup | None = None
        self._entry_index: dict[str, dict] | None = None

    @classmethod
    def read(cls, home_space_store, cache, statistic_ids=None) -> House:
        """La casa di adesso, dagli archivi vivi. Senza archivio, una casa
        vuota (non inventata): chi la legge lo dichiara, come faceva prima
        ciascuno per conto suo. `statistic_ids` e' la lettura del giro, se il
        giro l'ha fatta (B-12)."""
        if home_space_store is None:
            return cls({}, read_mirror(cache), statistic_ids=statistic_ids)
        return cls(home_space_store.read(), read_mirror(cache),
                   tuple(home_space_store.unavailable()), statistic_ids)

    def hierarchy(self) -> list[dict]:
        """L'albero piano -> area -> entita' di `topology.hierarchy`, con i
        registri caduti applicati. Calcolato una volta: chi lo riceve lo
        legge, non lo modifica (le porte costruiscono dizionari loro)."""
        if self._floors is None:
            self._floors = topology.hierarchy(self.home_space, self.unavailable)
        return self._floors

    def entity_entries(self) -> list[tuple[dict, dict, dict, str]]:
        """(voce, area, piano, dove) per ogni entita' dell'albero; `dove` e'
        `visibile`, `nascosta` o `disabilitata`."""
        out = []
        for floor in self.hierarchy():
            for area in floor.get("aree") or []:
                for key, where in (("entita", "visibile"),
                                   ("entita_nascoste", "nascosta"),
                                   ("entita_disabilitate", "disabilitata")):
                    for entry in area.get(key) or []:
                        if isinstance(entry, dict) and entry.get("id"):
                            out.append((entry, area, floor, where))
        return out

    def where(self, entity_id: str) -> dict | None:
        """DOVE sta un'entita' (spec §4.1; Tappa 3, Task 6, B-10, D3): area,
        se l'area e' ereditata dal dispositivo, piano, dispositivo e
        integrazione. `None` se il registro delle entita' non la conosce.

        **Compone, non decide.** Il posto viene dall'albero di `hierarchy()`,
        che lo calcola con `topology.actual_area` -- l'area propria, altrimenti
        quella del dispositivo: la regola di Home Assistant -- e che sa gia'
        dire «Dispositivi non letti» o «Aree non lette» quando un registro non
        ha risposto. Rifare qui quelle cause sarebbe una seconda copia della
        regola, la stessa che `observer.house_lines` ha (legge il solo
        `area_id` proprio: 194 entita' guardate su 324 senza area, cattura del
        01/10/2026) e che il Task 12 toglie.

        Ogni parte porta `id` e `nome` (atomicita': un id senza nome e' un
        frammento, un nome senza id e' un vicolo cieco per `search` e `view`).
        Una pseudo-area resta col suo id (`view("area", "__senza_area__")` la
        ritrova) e il piano allora tace: il contenitore «Fuori dalle aree»
        ripeterebbe solo che l'area non c'e'. `area_ereditata` e' vera solo
        quando l'area c'e', e' vera, e la voce non ne dichiara una propria.
        """
        place = self._entity_places().get(entity_id)
        if place is None:
            return None
        entry, area, floor = place
        pseudo = topology.is_pseudo_area(area.get("id"))
        device_id = entry.get("dispositivo_id")
        device = self._devices().get(device_id) if device_id else None
        return {
            "area": {"id": area.get("id"), "nome": area.get("nome")},
            "area_ereditata": not pseudo and not entry.get("area_id"),
            "piano": None if pseudo else {"id": floor.get("id"), "nome": floor.get("nome")},
            # Il nome col ripiego sull'id di `House.name` (A-16): lo stesso
            # dispositivo non ha due nomi a seconda della porta (fondamenta 3).
            "dispositivo": ({"id": device_id,
                             "nome": topology.device_name(device) if device else None}
                            if device_id else None),
            "integrazione": entry.get("piattaforma"),
        }

    def _entity_places(self) -> dict[str, tuple[dict, dict, dict]]:
        if self._places is None:
            self._places = {entry["id"]: (entry, area, floor)
                            for entry, area, floor, _w in self.entity_entries()}
        return self._places

    def _devices(self) -> dict[str, dict]:
        if self._device_index is None:
            self._device_index = {d["id"]: d for d in self.home_space.get("dispositivi") or []
                                  if isinstance(d, dict) and d.get("id")}
        return self._device_index

    def select(self, f, kinds: tuple[str, ...], behavior, *, now: float) -> Selection:
        """Le entita' e i comportamenti che passano i filtri, per i generi dati.

        Le disabilitate sono sempre fuori e contate; le nascoste e quelle di
        servizio fuori e contate, salvo `includi_nascoste`/`includi_servizio`.
        La riga di comportamento rappresenta gia' l'automazione: quando si
        cercano anche automazioni o script, la loro entita' di registro sarebbe
        un doppione e non si sceglie (solo quelle che il comportamento conosce:
        un'automazione che non c'e' resta un'entita').

        `search` e `history` scelgono con questa STESSA funzione (spec «la
        storia» §2): fino al 04/10/2026 era `house_query.select_subjects`,
        uscita col Task 13 quando la storia ha smesso di chiamarla."""
        entries = self.entity_entries()
        searching_behavior = any(k in _BEHAVIOR_KINDS for k in kinds)
        shadowed = {b.get("id") for b in behavior or []} if searching_behavior else set()
        excluded = {"nascoste": 0, "servizio": 0, "disabilitate": 0}
        # Le classi che questa porta conta (D7): le disabilitate mai, le
        # nascoste e quelle di servizio a richiesta. Un'entita' fuori per
        # piu' ragioni si conta sotto la PRIMA che la porta non ammette.
        admitted = ({"nascosta"} if f.include_hidden else set()) | (
            {"servizio"} if f.include_service else set())
        matched = []
        if "entita" in kinds:
            for entry, area, floor, where in entries:
                if entry["id"] in shadowed:
                    continue
                if not _entity_matches(f, entry, area, floor, self.mirror, now):
                    continue
                refused = next((cls for cls, _cause in topology.visibility_classes(entry)
                                if cls not in admitted), None)
                if refused is not None:
                    excluded[_EXCLUDED_KEY[refused]] += 1
                    continue
                matched.append((entry, area, where))
        places = {entry["id"]: (entry, area, floor) for entry, area, floor, _w in entries}
        behaving = []
        for kind in kinds:
            if kind in _BEHAVIOR_KINDS:
                behaving.extend(_behavior_matches(replace(f, kind=kind), behavior,
                                                  self.mirror, now, places))
        return Selection(matched, behaving, excluded)

    def _entity_index(self) -> dict[str, dict]:
        """Le voci dell'anagrafe per id, nell'ordine dell'anagrafe; una volta."""
        if self._entities is None:
            self._entities = {e["id"]: e for e in self.home_space.get("entita") or []
                              if isinstance(e, dict) and e.get("id")}
        return self._entities

    def _entity(self, entity_id: str) -> dict | None:
        """La voce dell'anagrafe di un'entita', per id."""
        return self._entity_index().get(entity_id)

    def visibility(self, entity_id: str) -> tuple[str, str | None] | None:
        """VISIBILITA' (§4.1): la classe di un'entita' con la sua causa --
        `("disabilitata", "user")`, `("servizio", "diagnostic")`,
        `("visibile", None)` -- dalla regola unica, `topology.visibility`.
        `None` per un id che l'anagrafe non conosce: non e' «visibile»."""
        entry = self._entity(entity_id)
        return None if entry is None else topology.visibility(entry)

    def name(self, kind: str, identifier: str) -> str | None:
        """IDENTITA' (§4.1): come si chiama una cosa della casa, per genere.

        Entita', automazioni e script col nome vivo (D1, `topology.live_name`):
        hanno tutti un `entity_id`, e il nome che Home Assistant mostra sta
        nello specchio per tutti e tre. Dispositivi col nome, altrimenti l'id
        (`topology.device_name`); aree e piani col nome dell'anagrafe, che il
        lettore riempie gia' con l'id quando manca. `None` per un dispositivo,
        un'area o un piano che l'anagrafe non conosce."""
        if kind in ("entita", *_BEHAVIOR_KINDS):
            entry = self._entity(identifier) or {}
            return topology.live_name(identifier, entry.get("nome"), self.mirror)
        table = {"dispositivo": "dispositivi", "area": "aree", "piano": "piani"}.get(kind)
        if table is None:
            raise ValueError(f"genere sconosciuto: {kind!r}")
        row = next((r for r in self.home_space.get(table) or []
                    if isinstance(r, dict) and r.get("id") == identifier), None)
        if row is None:
            return None
        return topology.device_name(row) if kind == "dispositivo" else row.get("nome")

    def kind_of(self, entity_id: str) -> dict | None:
        """TIPO (§4.1; Tappa 3, Task 7, B-17): il dominio, la classe e l'unita'
        di un'entita' **di adesso** -- dallo specchio di questa casa, col
        registro come ripiego (`topology.live_first`, la viva vince).

        Fino al 04/10/2026 l'anagrafe scriveva classe e unita' dello specchio
        al momento della ricostruzione e le teneva ferme: osservatore e
        ricette vedevano l'unita' dell'ultima ricostruzione, non quella che
        Home Assistant usa adesso. Ora l'anagrafe porta solo cio' che il
        registro dichiara, e il vivo si chiede qui. `None` per un id che ne'
        il registro ne' lo specchio conoscono."""
        entry = self._entity(entity_id)
        if entry is None and entity_id not in self.mirror.state:
            return None
        entry = entry or {}
        return {"dominio": domain_of(entity_id),
                "classe": topology.live_first(entry.get("classe"),
                                              self.mirror.classes.get(entity_id)),
                "unita": topology.live_first(entry.get("unita"),
                                             self.mirror.units.get(entity_id)),
                # Cio' che l'integrazione dichiara di se' (`energy_today`, non
                # «Potenza» da indovinare): fa parte del tipo, e l'osservatore
                # lo manda al modello (Task 12).
                "translation_key": entry.get("translation_key"),
                "statistiche": self.has_statistics(entity_id),
                # Da dove viene la risposta (atomicita'): l'elenco di Home
                # Assistant, o la regola del sorgente quando l'elenco manca.
                "statistiche_da": ("home_assistant" if self.statistic_ids is not None
                                   else "regola")}

    def has_statistics(self, entity_id: str) -> bool:
        """«Ha statistiche?» (B-12): l'elenco che Home Assistant tiene, se il
        giro l'ha letto; altrimenti la regola del sorgente sullo
        `state_class` di adesso (`ha_vocabulary.has_statistics`, la stessa
        che usa il watcher)."""
        return has_statistics(entity_id, self.mirror.state_classes.get(entity_id),
                              self.statistic_ids)

    def with_statistics(self, statistic_ids) -> House:
        """La STESSA istantanea (anagrafe, specchio, registri caduti), con
        l'elenco delle statistiche che il giro ha letto dopo averla aperta.
        Nessuna lettura nuova: chi la chiama ha gia' l'elenco in mano
        (`server.statistic_ids_for_round`, la lettura unica del giro)."""
        return House(self.home_space, self.mirror, self.unavailable, statistic_ids)

    def _instances(self) -> dict[str, dict]:
        if self._entry_index is None:
            self._entry_index = {i["entry_id"]: i for i in self.home_space.get("integrazioni") or []
                                 if isinstance(i, dict) and i.get("entry_id")}
        return self._entry_index

    def _switched_off_by(self, entry: dict, cause: str | None) -> str | None:
        """CHI ha spento davvero un'entita': il valore di `disabled_by`, o --
        quando e' `config_entry` o `device` -- quello dell'istanza o del
        dispositivo sopra di lei, da cui Home Assistant l'ha propagato (vedi il
        commento in `ha_vocabulary.py`). Un dispositivo spento a sua volta
        dalla sua istanza rimanda all'istanza dell'entita'. Se la catena non si
        legge (la voce sopra manca) resta il valore dell'entita', tranne
        `config_entry`, che vuol dire sempre il proprietario."""
        if cause == ENTITY_DISABLED_BY_DEVICE:
            device = self._devices().get(entry.get("dispositivo_id")) or {}
            cause = device.get("disabilitato_da") or cause
        if cause == ENTITY_DISABLED_BY_CONFIG_ENTRY:
            instance = self._instances().get(entry.get("config_entry_id")) or {}
            # Anche con l'istanza non letta la risposta e' una sola:
            # `ConfigEntryDisabler` ha un valore solo, `user`
            # (`homeassistant/config_entries.py` al tag 2026.9.4, letto il
            # 05/10/2026), e `config_entry` lo scrive Home Assistant solo sotto
            # un'istanza spenta.
            cause = instance.get("disabilitata_da") or ENTITY_DISABLED_BY_USER
        return cause

    def source(self, entity_id: str) -> dict | None:
        """LA FONTE (R11; Tappa 3, Task 8, B-25; decisione del proprietario D6
        «sette stati», 03/10/2026): perche' un'entita' parla o tace.

        `stato`, uno di sette:

        - `viva` -- c'e', con un valore;
        - `spenta_dal_proprietario` -- disabilitata, e chi l'ha spenta e' il
          proprietario (`disabled_by: user`, o l'istanza o il dispositivo
          sopra di lei spenti da lui);
        - `spenta_da_home_assistant` -- disabilitata da Home Assistant o
          dall'integrazione (`integration`, `hass`): «mai attivata»;
        - `integrazione_ferma` -- la sua istanza non e' caricata;
        - `non_disponibile` -- `unavailable`, anche con `restored: true` (la
          voce che nessuna integrazione ha aggiunto);
        - `senza_valore` -- `unknown`: raggiungibile, ma senza un valore
          (dopo un riavvio un sensore vivo resta cosi' per un po', e dirlo
          morto e' il difetto che lo strato 1 toglie);
        - `sparita` -- nel registro e non negli stati.

        Negli stati e non nel registro NON e' «sparita» (scostamento dalla
        lettera di D6, dichiarato nel rapporto del Task 8): un'entita' senza
        `unique_id` non entra mai nel registro, e sulla casa le tre che ci sono
        (`sun`, `zone`, `conversation`) sono vive. Si giudica dal suo stato.

        `causa` e' il valore di Home Assistant che lo dice: `disabled_by` per
        le spente, lo stato dell'istanza per l'integrazione ferma, `restored`
        o `unavailable`, `unknown`; `None` per viva e sparita. `spenta_da` e'
        chi ha spento davvero (la catena di `_switched_off_by`). `istanza`
        porta l'istanza, se l'entita' ne ha una che l'anagrafe conosce.

        **Con lo specchio non letto** lo stato vivo tace (`stato` e
        `negli_stati` `None`): non si dice «sparita» di chi non si e' potuto
        guardare. Cio' che sa il registro resta.

        `statistiche`: se Home Assistant tiene statistiche per lei, dall'elenco
        del giro; `None` se l'elenco non e' stato letto -- qui non si risponde
        con la regola del sorgente (`kind_of` lo fa, e dice da dove viene):
        «perche' tace» non si puo' spiegare con una deduzione.

        `None` per un id che ne' il registro ne' lo specchio conoscono."""
        entry = self._entity(entity_id)
        readable = self.mirror.readable
        in_states = entity_id in self.mirror.state
        if entry is None and not in_states:
            return None
        instance = None
        if entry is not None and entry.get("config_entry_id"):
            row = self._instances().get(entry["config_entry_id"])
            if row is not None:
                instance = {"id": row["entry_id"], "dominio": row.get("dominio"),
                            "stato": row.get("stato"),
                            "disabilitata_da": row.get("disabilitata_da")}
        state, cause, switched_off_by = None, None, None
        visibility = self.visibility(entity_id) if entry is not None else None
        if visibility is not None and visibility[0] == "disabilitata":
            cause = visibility[1]
            switched_off_by = self._switched_off_by(entry, cause)
            state = (SOURCE_SWITCHED_OFF_BY_OWNER if switched_off_by == ENTITY_DISABLED_BY_USER
                     else SOURCE_SWITCHED_OFF_BY_HA)
        elif instance is not None and instance["stato"] != CONFIG_ENTRY_LOADED:
            state, cause = "integrazione_ferma", instance["stato"]
        elif readable:
            value = self.mirror.state.get(entity_id)
            if not in_states:
                state = SOURCE_GONE
            elif value == STATE_UNAVAILABLE:
                restored = disclosable_attributes(
                    self.mirror.attributes.get(entity_id)).get(RESTORED_ATTRIBUTE)
                state = "non_disponibile"
                cause = RESTORED_ATTRIBUTE if restored is True else STATE_UNAVAILABLE
            elif value == STATE_UNKNOWN:
                state, cause = "senza_valore", STATE_UNKNOWN
            else:
                state = SOURCE_LIVE
        return {"stato": state, "causa": cause, "spenta_da": switched_off_by,
                "istanza": instance, "nel_registro": entry is not None,
                "negli_stati": in_states if readable else None,
                "statistiche": (self.has_statistics(entity_id)
                                if self.statistic_ids is not None else None)}

    # -- cio' che gli attori compongono (Tappa 3, Task 12; R13) -------------
    #
    # Fino al 04/10/2026 osservatore, ricette e giri del server scorrevano le
    # tabelle dell'anagrafe da se': chi guarda, di chi e' un'entita', quali
    # dispositivi ci sono. Ogni regola nuova della casa (il nome vivo, l'area
    # ereditata, il fuori) li lasciava indietro. Ora chiedono qui, e il
    # cancello `tests/test_attori_compongono.py` vieta che tornino a scorrere.

    def entity_ids(self) -> list[str]:
        """Ogni entita' che il registro conosce, nell'ordine dell'anagrafe:
        anche disabilitate, nascoste e di servizio. Per chi chiede a Home
        Assistant una cosa che vale per il registratore intero (la finestra
        della memoria, `cadence.measure_memory_window`), non per chi guarda."""
        return list(self._entity_index())

    def visible_entities(self) -> list[str]:
        """Le entita' che un attore guarda di suo: quelle che `select` senza
        filtri lascia dentro -- la regola del fuori, `topology.visibility_
        classes`: niente disabilitate, nascoste o di servizio --
        nell'ordine dell'anagrafe (l'ordine in cui il modello le leggeva
        fino a ieri; quale sia l'ordine giusto e' della resa, Tappa 4).

        L'osservatore la applicava chiamando `briefing.digest_visible_entity_
        ids`, le ricette non la applicavano affatto (B-03, D2)."""
        if self._visible is None:
            # `now` non conta: senza filtri sull'eta' `select` non lo legge.
            chosen = {entry["id"] for entry, _area, _where
                      in self.select(HouseFilters(), ("entita",), None, now=0.0).entities}
            self._visible = [eid for eid in self._entity_index() if eid in chosen]
        return self._visible

    def device_entities(self, device_id: str) -> list[dict]:
        """Le voci dell'anagrafe di un dispositivo, TUTTE -- disabilitate,
        nascoste e di servizio comprese -- nell'ordine dell'anagrafe (B-11):
        per la porta che le mostra separate e contate (`queries._view_device`).
        «Di chi e' un'entita'» si chiedeva in linea in due posti."""
        if self._by_device is None:
            self._by_device = {}
            for entry in self._entity_index().values():
                if entry.get("dispositivo_id"):
                    self._by_device.setdefault(entry["dispositivo_id"], []).append(entry)
        return self._by_device.get(device_id, [])

    def sibling_group(self, entity_id: str) -> tuple[str, str] | None:
        """Il gruppo di SORELLE di un'entita' con statistiche (piano degli
        attori, richiesta (4) alla Tappa 3; regola del dato fermo, proposta
        del 06/10/2026): `("dispositivo", id)` se sul suo dispositivo ci sono
        almeno due entita' con statistiche; altrimenti `("istanza",
        config_entry_id)`, l'istanza dell'integrazione che Home Assistant
        dichiara nel registro delle entita' -- non la piattaforma, che unisce
        cose senza legame. `None` se l'entita' non ha statistiche o se non ha
        ne' dispositivo ne' istanza.

        «Ha statistiche» e' la regola sola di `has_statistics` (B-12): l'elenco
        del giro se c'e', la regola del sorgente sullo `state_class` se manca.
        Fino al giro 7 della revisione (06/10/2026) qui serviva l'elenco, e il
        giorno in cui `recorder/list_statistic_ids` falliva il dato fermo
        spariva: il 30/09 sarebbe tornato zero con copertura 1.0 (G7-1).

        Misurato dallo sprint il 06/10/2026 sulle catture (03/09-03/10): senza
        il ripiego sull'istanza si perdevano gli 8 termometri del 29/09, otto
        dispositivi con un'entita' ciascuno fermi insieme."""
        if not self.has_statistics(entity_id):
            return None
        entry = self._entity(entity_id) or {}
        device_id = entry.get("dispositivo_id")
        if device_id and sum(1 for e in self.device_entities(device_id)
                             if self.has_statistics(e["id"])) >= 2:
            return ("dispositivo", device_id)
        if entry.get("config_entry_id"):
            return ("istanza", entry["config_entry_id"])
        return None

    def possible_siblings(self, entity_id: str) -> list[str]:
        """Le entita' che POTREBBERO stare nel gruppo di `sibling_group`, senza
        sapere chi ha statistiche: quelle del suo dispositivo e quelle della
        sua istanza, lei compresa, nell'ordine dell'anagrafe.

        Serve quando l'elenco delle statistiche non si e' letto (G7-1, la
        rimisura dello sprint su 413ce7a7): si chiedono le serie di tutte, e
        chi ha statistiche lo dice la risposta di Home Assistant
        (`server._report_ingredients`)."""
        entry = self._entity(entity_id) or {}
        device_id, instance = entry.get("dispositivo_id"), entry.get("config_entry_id")
        return [eid for eid, e in self._entity_index().items()
                if eid == entity_id
                or (device_id and e.get("dispositivo_id") == device_id)
                or (instance and e.get("config_entry_id") == instance)]

    def siblings(self, entity_id: str) -> list[str]:
        """Le entita' dello stesso gruppo di `sibling_group`, lei compresa,
        nell'ordine dell'anagrafe; `[]` se non ha un gruppo."""
        group = self.sibling_group(entity_id)
        if group is None:
            return []
        if group[0] == "dispositivo":
            candidates = [e["id"] for e in self.device_entities(group[1])]
        else:
            candidates = [eid for eid, e in self._entity_index().items()
                          if e.get("config_entry_id") == group[1]]
        return [eid for eid in candidates if self.sibling_group(eid) == group]

    def entities_of(self, device_id: str) -> list[str]:
        """Le entita' di un dispositivo che un attore guarda (B-03, B-11; D2
        «si'», decisione del proprietario del 03/10/2026): quelle di
        `device_entities` che la regola del fuori di `visible_entities` lascia
        dentro, nell'ordine dell'anagrafe."""
        if self._visible_set is None:
            self._visible_set = frozenset(self.visible_entities())
        return [entry["id"] for entry in self.device_entities(device_id)
                if entry["id"] in self._visible_set]

    def device_ids(self) -> list[str]:
        """I dispositivi del registro, nell'ordine dell'anagrafe (chi ruota
        su di loro, `recipe_turn.who_to_ask`, ruota su quest'ordine)."""
        return list(self._devices())

    def lookup(self) -> Lookup:
        """L'indice con cui la memoria verifica le sue ancore
        (`memory.resolver.costruisci_indice`), da QUESTA anagrafe, una volta
        per casa (A-13, Tappa 3, Task 12).

        Fino al 04/10/2026 si costruiva in tre posti con tre ingressi:
        `remember` in chat dietro una cache di vita lunga (`LookupCache`,
        con la data dell'anagrafe come chiave), le due rotte dei ricordi da
        capo a ogni richiesta. Ora viene dalla stessa istantanea del turno
        che da' lo specchio delle unita': l'indice e le unita' non possono
        guardare due anagrafi diverse. Un'anagrafe mai letta e' `{}`, e il
        suo indice e' vuoto -- come prima."""
        if self._lookup is None:
            self._lookup = costruisci_indice(self.home_space)
        return self._lookup
