"""L'istantanea dei giudizi sui tipi: cio' che HIRIS giudica di un tipo o di
un'entita', letto dal sapere e congelato.

**Puro.** Riceve righe e risponde: non apre archivi, non legge la rete, non ha
stato globale. Chi la costruisce dall'archivio e chi la sostituisce dopo una
scrittura e' la porta unica `mind/judgments.py` (spec 2026-09-16 §4).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from types import MappingProxyType

Row = tuple[str, str, str, str]

GENRE_FIELD = "genere"
RESTING_FIELD = "riposo"
WORKING_FIELD = "lavoro"
NOTABLE_FIELD = "notevole"
OPERABLE_FIELD = "accendibile"
PARAMETER_LIMITS_FIELD = "limiti_parametri"
#: «Quando una cosa di questo tipo esce dal suo riposo, il proprietario deve
#: saperlo subito?» (spec `2026-09-18-da-sapere-subito.md` §2). **Non e'
#: `notevole`**, che risponde a «vale la pena raccontarlo nel riassunto?» -- e'
#: cosi' che la usa `home_space/briefing._is_event`, ed e' per questo che una
#: luce accesa e' `notevole` e non e' da sapere subito. Misurato il 18/09/2026:
#: leggendo `notevole` come criterio della banda, 71 voci di cronaca su 75
#: finivano in prima pagina, 35 delle quali accensioni di luce.
#:
#: **Il nome inglese non e' deciso** (regola del glossario: una riga nasce con
#: l'italiano e l'inglese si sceglie in un passaggio successivo). Quando lo
#: sara', la rinomina e' un commit di sola rinomina.
DA_SAPERE_SUBITO_FIELD = "da_sapere_subito"
JUDGMENT_FIELD_NAMES = frozenset({
    GENRE_FIELD, RESTING_FIELD, WORKING_FIELD, NOTABLE_FIELD, OPERABLE_FIELD,
    PARAMETER_LIMITS_FIELD, DA_SAPERE_SUBITO_FIELD})
CHRONICLE_FIELDS = (GENRE_FIELD, RESTING_FIELD)
NO_GENRE = "nessuno"
_SUBJECT_KINDS = ("tipo", "entita")
_YES_NO = {"si": True, "no": False}
# Le due forme di un limite di parametro (spec §2).
_LIMIT_KEY_SETS = (frozenset({"min", "max"}), frozenset({"options"}))


class JudgmentError(ValueError):
    def __init__(self, rows: tuple[Row, ...], reasons: tuple[str, ...]) -> None:
        super().__init__("; ".join(reasons))
        self.rows = rows
        self.reasons = reasons


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(inner) for key, inner in value.items()})
    return value


def _unpack(row) -> Row:
    parts = tuple(row)
    if len(parts) != 4:
        raise ValueError(f"una riga ha quattro parti, questa ne ha {len(parts)}")
    if not all(isinstance(part, str) for part in parts):
        raise TypeError("le quattro parti di una riga sono testo")
    return parts


def _as_tuple(row) -> tuple:
    try:
        return tuple(row)
    except TypeError:
        return (row,)


def _check_parameter_limits(parsed: dict) -> None:
    for parameter, limit in parsed.items():
        if not isinstance(limit, dict):
            raise TypeError(f"il limite di {parameter!r} e' un oggetto JSON")
        if frozenset(limit) not in _LIMIT_KEY_SETS:
            raise ValueError(f"il limite di {parameter!r} ha chiavi {sorted(limit)}: "
                             "ammesse min+max oppure options")
        if not all(isinstance(attribute, str) for attribute in limit.values()):
            raise TypeError(f"gli attributi del limite di {parameter!r} sono testo")


_DA_SAPERE_SUBITO_FORME = ("atteso si/no oppure un elenco JSON di stati "
                           "(es. [\"jammed\"]), trovato {value!r}")


def _parse_da_sapere_subito(value: str, absent_forms: frozenset[str]):
    """Le **tre** forme del valore (spec `2026-09-18-da-sapere-subito.md` §2):
    `si`, `no`, oppure **l'elenco degli stati che contano**.

    Perche' una terza forma. Misurato il 18/09/2026 sulle sedici righe del
    seme: quindici stanno bene col solo `si` -- l'allarme ha un `lavoro` di UN
    solo stato (`triggered`), i tredici `binary_sensor` e la sirena non hanno
    `lavoro` e usano il riposo. **La serratura no**: per lei `lavoro` significa
    «sta operando» (`locking`, `opening`, `unlocking`, `unlocked`, `open`) e
    `jammed` non e' ne' lavoro ne' riposo. Col solo `si` la regola avrebbe
    fatto entrare in banda **ogni sblocco** e lasciato fuori
    **l'inceppamento**: l'esatto contrario di cio' che serve. E' la stessa
    malattia della fetta -- **una parola che dice due cose** -- trovata dentro
    `lavoro`, che per l'allarme vuol dire «e' successo» e per la serratura «sta
    muovendosi».

    Torna `True`/`False` per `si`/`no`, un `frozenset` per l'elenco: la forma
    del valore **e'** la risposta alla domanda «quale ramo della regola», e chi
    legge non deve ricostruirla da un flag a parte.

    Un elenco **vuoto** si rifiuta: direbbe `no` in un secondo modo, e
    `da_sapere_subito()` tornerebbe un insieme falso -- la riga sarebbe
    accettata e la casa non cambierebbe. Le **forme dell'assenza** si
    rifiutano come nel riposo: la regola le tratta come «non e' una notizia»
    prima di ogni altra cosa, e dentro l'elenco sarebbero una voce morta.
    """
    if value in _YES_NO:
        return _YES_NO[value]
    try:
        parsed = json.loads(value)
    except ValueError:
        raise ValueError(_DA_SAPERE_SUBITO_FORME.format(value=value)) from None
    if not isinstance(parsed, list) or not all(isinstance(s, str) for s in parsed):
        raise ValueError(_DA_SAPERE_SUBITO_FORME.format(value=value))
    if not parsed:
        raise ValueError("l'elenco degli stati da sapere subito e' vuoto: "
                         "«nessuno stato conta» si scrive `no`")
    dentro = absent_forms & set(parsed)
    if dentro:
        raise ValueError(f"le forme dell'assenza {sorted(dentro)} non sono uno stato "
                         "da sapere subito")
    return frozenset(parsed)


def _parse(field: str, value: str, genres: frozenset[str], absent_forms: frozenset[str]):
    if field == GENRE_FIELD:
        if value != NO_GENRE and value not in genres:
            raise ValueError(f"genere fuori elenco: {value!r}")
        return value
    if field in (NOTABLE_FIELD, OPERABLE_FIELD):
        if value not in _YES_NO:
            raise ValueError(f"atteso si/no, trovato {value!r}")
        return _YES_NO[value]
    if field == DA_SAPERE_SUBITO_FIELD:
        return _parse_da_sapere_subito(value, absent_forms)
    parsed = json.loads(value)
    if field == RESTING_FIELD:
        if not isinstance(parsed, list) or not all(isinstance(s, str) for s in parsed):
            raise ValueError("il riposo e' una lista di stati")
        if absent_forms & set(parsed):
            raise ValueError(f"le forme dell'assenza {sorted(absent_forms & set(parsed))} "
                             "non sono un riposo")
        return frozenset(parsed)
    if not isinstance(parsed, dict):
        raise TypeError(f"`{field}` e' un oggetto JSON")
    if field == WORKING_FIELD:
        if not all(isinstance(reason, str) for reason in parsed.values()):
            raise TypeError("la ragione di ogni stato di lavoro e' testo")
    else:
        _check_parameter_limits(parsed)
    return _freeze(parsed)


def _canonical(value):
    """La forma dell'impronta: il testo per `genere`, la lista ordinata per
    `riposo`. Una differenza solo tipografica nel JSON non la cambia."""
    return sorted(value) if isinstance(value, frozenset) else value


class TypeJudgments:
    # `_absent`: le forme dell'assenza con cui questa istantanea e' nata. Fino
    # al 18/09/2026 `from_rows` le riceveva, le usava per validare il riposo e
    # le BUTTAVA -- e la regola di «da sapere subito» (spec §3) ne ha bisogno.
    # Tenerle non e' uno stato in piu': e' un dato che ci era gia' stato dato, e
    # ridichiararlo altrove sarebbe il secondo elenco degli stessi stati che
    # `test_un_tipo_ha_una_casa_sola` boccia.
    __slots__ = ("_absent", "_by_key", "_rows")

    def __init__(self, by_key: Mapping, rows: tuple[Row, ...],
                 absent: Iterable[str] = ()) -> None:
        object.__setattr__(self, "_by_key", MappingProxyType(dict(by_key)))
        object.__setattr__(self, "_rows", rows)
        object.__setattr__(self, "_absent", frozenset(absent))

    def __setattr__(self, name, value):
        raise AttributeError("un'istantanea dei giudizi non si modifica: se ne costruisce un'altra")

    def __delattr__(self, name):
        raise AttributeError("un'istantanea dei giudizi non si modifica: se ne costruisce un'altra")

    @classmethod
    def from_rows(cls, rows: Iterable[Row], *, genres: Iterable[str],
                  absent_forms: Iterable[str]) -> TypeJudgments:
        """`genres` e `absent_forms` arrivano da chi chiama, come dati: i generi
        ammessi e le forme dell'assenza di stato (`none`, il vuoto: spec §5, non
        sono il riposo di nessuno) hanno la loro casa altrove -- le seconde in
        `type_vocabulary.ABSENT_STATE_FORMS` -- e questo modulo non importa dal
        repo. Ripeterle qui in un letterale sarebbe un secondo elenco degli
        stessi stati, che `test_un_tipo_ha_una_casa_sola` boccia."""
        allowed = frozenset(genres)
        absent = frozenset(absent_forms)
        by_key: dict = {}
        rows_by_key: dict[tuple[str, str, str], list[Row]] = {}
        bad, reasons = [], []
        for row in rows:
            try:
                kind, subject, field, value = _unpack(row)
                if kind not in _SUBJECT_KINDS:
                    raise ValueError(f"genere di soggetto non ammesso: {kind!r}")
                if field not in JUDGMENT_FIELD_NAMES:
                    raise ValueError(f"`{field}` non e' un giudizio")
                parsed = _parse(field, value, allowed, absent)
            except (ValueError, TypeError) as error:
                bad.append(_as_tuple(row))
                reasons.append(f"{_as_tuple(row)!r}: {error}")
                continue
            key = (kind, subject, field)
            by_key[key] = parsed
            rows_by_key.setdefault(key, []).append((kind, subject, field, value))
        for key, same in rows_by_key.items():
            if len(same) > 1:
                bad.extend(same)
                reasons.append(f"{'/'.join(key)}: chiave doppia, {len(same)} righe")
        if bad:
            raise JudgmentError(tuple(bad), tuple(reasons))
        kept = sorted(row for same in rows_by_key.values() for row in same)
        return cls(by_key, tuple(kept), absent)

    def _lookup(self, field, domain, device_class=None, entity_id=None):
        keys = []
        if entity_id:
            keys.append(("entita", entity_id, field))
        if device_class:
            keys.append(("tipo", f"{domain}.{device_class}", field))
        keys.append(("tipo", domain, field))
        for key in keys:
            if key in self._by_key:
                return self._by_key[key]
        return None

    def genre_of(self, entity_id: str, device_class: str | None) -> str | None:
        domain = str(entity_id).split(".")[0]
        genre = self._lookup(GENRE_FIELD, domain, device_class, entity_id)
        return None if genre in (None, NO_GENRE) else genre

    def resting_of(self, domain, device_class=None, entity_id=None) -> frozenset[str]:
        return self._lookup(RESTING_FIELD, domain, device_class, entity_id) or frozenset()

    def working_of(self, domain, device_class=None) -> Mapping[str, str]:
        return self._lookup(WORKING_FIELD, domain, device_class) or MappingProxyType({})

    def is_notable(self, domain, device_class=None) -> bool:
        return bool(self._lookup(NOTABLE_FIELD, domain, device_class))

    def da_sapere_subito(self, domain, device_class=None):
        """Il **giudizio scritto** su questo tipo, nella forma in cui e'
        scritto: `True`/`False` per `si`/`no`, un `frozenset` di stati per
        l'elenco, `False` se la riga non c'e' (l'assenza e' una risposta).
        Coppia, poi dominio -- come `is_notable`, e per la stessa ragione:
        `binary_sensor` dice «no» in generale e «si'» sulle classi che lo
        meritano.

        **Il campo, non la regola**: se quello stato *in questo momento* sia da
        sapere subito lo dice `stato_da_sapere_subito` (spec §3, poche righe
        sotto), che a questa risposta aggiunge il lavoro, il riposo e le forme
        dell'assenza.

        Un elenco vuoto non esiste (`_parse_da_sapere_subito` lo rifiuta),
        quindi **ogni valore che dice «si'», in qualunque forma, e' vero** per
        chi si limita a chiedere `if judgments.da_sapere_subito(...)`.
        """
        return self._lookup(DA_SAPERE_SUBITO_FIELD, domain, device_class) or False

    def stato_da_sapere_subito(self, domain, device_class, state,
                               entity_id=None) -> bool:
        """**La regola della banda** (spec `2026-09-18-da-sapere-subito.md` §3):
        questo tipo va saputo subito **e** questo stato e' il fatto.

        **Il giudizio dice ELENCO?** Allora entra in banda **solo** uno degli
        stati che nomina, e nient'altro: niente lavoro, niente riposo, nessun
        ripiego. E' il primo ramo, prima di ogni altro. Nasce dalla serratura
        (decisione del proprietario, 18/09/2026): per `lock`, `lavoro` vuol dire
        «sta operando» e `jammed` non e' ne' lavoro ne' riposo, quindi col solo
        `si` sarebbe entrato **ogni sblocco** e non l'inceppamento. Con
        `da_sapere_subito: ["jammed"]` entra l'inceppamento e basta.

        **Il giudizio dice `si`?** Allora due modi, e il secondo e' il ripiego
        del primo:

        - se il tipo ha un giudizio `lavoro`, il fatto e' uno **stato di
          lavoro**. E' il caso dell'allarme: `triggered` si', `disarmed` no;
        - se non ce l'ha, vale lo stato che **non e' riposo e non e' una forma
          dell'assenza**. E' il caso dei rilevatori: `binary_sensor.smoke` non
          dichiara nessun lavoro, e `on` e' il fatto.

        **Senza lavoro E senza riposo la risposta e' `False`: indecidibile vale
        no** (ruling del controller, revisione finale, I-1). Per sapere quando
        una cosa esce dal suo riposo bisogna sapere qual e' il riposo: col
        ripiego «non e' un riposo» applicato a un riposo vuoto, ogni stato non
        assente -- `off` compreso, cioe' lo **spegnimento** -- sarebbe una
        notizia. `judgments._check` rifiuta gia' un `si` scritto su un tipo
        cosi', ma quel rifiuto non protegge l'invariante: si puo' scrivere il
        riposo, poi il `si`, poi togliere il riposo (ritorno al seme, oppure
        `riposo: '[]'`, che `_parse` accetta) e restare con un `si` orfano.
        **La cura sta qui, alla fonte**; il rifiuto resta come cortesia che
        spiega il problema a chi scrive. Meglio una notizia in meno che una
        banda piena di spegnimenti.

        **La seconda meta' della condizione non e' un dettaglio: e' un difetto
        gia' trovato.** Con la prima stesura -- «esce dal riposo» --
        `alarm_control_panel` in `disarmed` entrava in prima pagina tutti e otto
        i giorni misurati: «disinserito» non e' fra i riposi (che sono gli stati
        armati) e non e' un lavoro. L'allarme disinserito e' la normalita' di
        una casa.

        **`entity_id` e' facoltativo e si consulta PRIMA del tipo** (revisione
        finale, I-2): `judgments._LEVELS` ammette `riposo` su un'entita' e la
        cronaca lo onora (`mind/facts._is_on` lo passa a `resting_of`). Senza
        questo parametro una correzione per entita' valeva per la cronaca e non
        per la banda: sullo stesso fatto la cronaca diceva «riposo» e la regola
        diceva «notizia». `lavoro` e `da_sapere_subito` restano coppia ->
        dominio, perche' `_LEVELS` non li ammette su un'entita'.

        **Qui non c'e' nessun elenco di tipi ne' di generi**: ci sono tre
        letture dei giudizi. Correggere il giudizio cambia la risposta, dalla
        lettura successiva e senza rilascio.

        **Presuppone una voce di cronaca gia' filtrata**: `unavailable` e
        `unknown` non arrivano mai da li', perche' `mind/facts.py:592` li salta
        prima di scriverla (`unknown_states()`: «non lo so», non un riposo ne'
        un fatto sulla casa). Se questo metodo li ricevesse comunque, un tipo
        senza `lavoro` li leggerebbe come «non e' un riposo» e li farebbe
        entrare in banda: e' una condizione d'uso di questo metodo, non un
        controllo che fa da solo.

        **Gli stati dell'elenco si confrontano come si confronta il riposo**:
        normalizzato lo stato che arriva, non l'elenco scritto. E' la stessa
        disciplina di `resting_of` (`facts._is_on` normalizza lo stato e lo
        cerca nell'insieme cosi' com'e' stato scritto): un secondo modo di
        trattare un elenco di stati sarebbe lo scostamento che questa fetta
        esiste per evitare. Chi scrive `["Jammed"]` scrive una riga che non
        morde, esattamente come chi lo scrive in un riposo.

        Lo stato si confronta **normalizzato come lo confronta `mind/facts.py`
        alla riga 594** (spazi tolti, minuscolo): due letture della stessa
        lista non devono poter divergere su `"None"` contro `"none"`. Questa
        normalizzazione copre anche `state=None` (il metodo e' pubblico):
        `str(None).strip().lower()` e' `"none"`, gia' una forma dell'assenza --
        nessun `or ""` in piu' serve, e tenerlo sarebbe un secondo modo di dire
        la stessa cosa (scelta dichiarata, revisione giro 1, MINOR 4).
        """
        quali = self.da_sapere_subito(domain, device_class)
        if not quali:
            return False
        stato = str(state).strip().lower()
        if isinstance(quali, frozenset):
            # **Il ramo dell'elenco viene PRIMA di tutti gli altri**: l'elenco
            # dice gia' quali stati contano, e il resto della regola -- lavoro,
            # riposo, ripiego -- non si applica. Metterlo dopo il lavoro
            # rimetterebbe in banda ogni sblocco di serratura, che e'
            # esattamente il caso per cui l'elenco esiste.
            return stato in quali
        if stato in self._absent:
            return False
        lavoro = self.working_of(domain, device_class)
        if lavoro:
            return stato in lavoro
        riposo = self.resting_of(domain, device_class, entity_id)
        if not riposo:
            return False
        return stato not in riposo

    def operable_domains(self) -> frozenset[str]:
        return frozenset(subject for (kind, subject, field), value in self._by_key.items()
                         if kind == "tipo" and field == OPERABLE_FIELD
                         and "." not in subject and value)

    def parameter_limits(self, domain, parameter) -> Mapping[str, str] | None:
        per_domain = self._lookup(PARAMETER_LIMITS_FIELD, domain)
        return None if per_domain is None else per_domain.get(parameter)

    def rows(self) -> tuple[Row, ...]:
        return self._rows

    def chronicle_fingerprint(self) -> str:
        relevant = sorted([kind, subject, field, _canonical(value)]
                          for (kind, subject, field), value in self._by_key.items()
                          if field in CHRONICLE_FIELDS)
        payload = json.dumps(relevant, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
